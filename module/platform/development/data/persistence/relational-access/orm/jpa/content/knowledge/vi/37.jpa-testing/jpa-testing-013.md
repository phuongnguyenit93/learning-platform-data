# Đánh giá khác biệt cơ sở dữ liệu nhúng và môi trường mục tiêu

> **Module:** Data Persistence Relational Access ORM JPA  
> **Chương:** Kiểm thử JPA  
> **Bài học:** Đánh giá khác biệt cơ sở dữ liệu nhúng và môi trường mục tiêu

Một dự án Jakarta Persistence (JPA) thường dùng H2 hoặc HSQLDB để chạy repository tests nhanh. Database nhúng khởi động trong JVM, không cần cài PostgreSQL hay MySQL và có thể tạo lại schema mỗi lần test. Nhờ đó, vòng phản hồi của lập trình viên ngắn hơn.

Nhưng **một bài kiểm thử JPA chạy xanh trên database nhúng không tự chứng minh cùng ánh xạ, câu SQL, dữ liệu và transaction sẽ hoạt động giống hệt trên database production**. Cùng một entity `PaymentRecord` có thể lưu thành công trên H2 nhưng thất bại với PostgreSQL vì schema migration chưa cập nhật, khác kiểu `NUMERIC`, lỗi tên cột, dialect-specific SQL, constraint, sequence hoặc transaction isolation. Ngược lại, cũng có trường hợp H2 từ chối cú pháp mà PostgreSQL hỗ trợ; lỗi test khi ấy không nhất thiết chỉ ra lỗi của ứng dụng trên hệ thống mục tiêu.

Bài này hướng dẫn đánh giá **khoảng cách giữa môi trường kiểm thử bằng DB nhúng và DBMS triển khai thật**, cách nhận diện rủi ro, thiết kế test matrix và kiểm tra bằng Testcontainers/migrations mà vẫn giữ lợi ích của các tests nhanh.

**Ý chính:** Database nhúng rất có giá trị khi câu hỏi là **“mapping và repository logic cơ bản có hoạt động không?”**; database mục tiêu cần thiết khi câu hỏi là **“SQL dialect, dữ liệu, constraints, giao dịch, locking và schema thật có hoạt động đúng trên hệ thống sẽ triển khai không?”**. Đừng bắt mọi test sử dụng database nặng, nhưng cũng đừng lấy H2 làm bằng chứng cho tất cả đặc tính PostgreSQL/MySQL/Oracle/SQL Server.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **embedded database**, **in-memory database**, **database server** và **database container**.
2. Giải thích vì sao H2/HSQLDB/Derby có giá trị trong JPA test nhưng không giống database mục tiêu.
3. Biết SQLite có đặc điểm embedded riêng và không mặc nhiên có JPA dialect/support giống H2.
4. Phân biệt **khác biệt dialect** và **khác biệt runtime/transaction engine**.
5. Nhận diện rủi ro từ `@GeneratedValue`, sequence, identity, kiểu dữ liệu và naming rules.
6. Hiểu precision/scale của `BigDecimal` có thể được kiểm khác nhau trên các DBMS.
7. Hiểu thời gian, múi giờ, `Instant`, `OffsetDateTime` và timestamp mappings cần test ở hệ mục tiêu.
8. Nhận biết khác biệt collation, case sensitivity, Unicode và unique constraints.
9. Hiểu null semantics, boolean/enum và native SQL không phải lúc nào cũng portable.
10. Đánh giá JSON, arrays, UUID, CLOB/BLOB và vendor-specific SQL.
11. Phân biệt `hibernate.hbm2ddl.auto=create-drop` và versioned schema migrations.
12. Hiểu vì sao H2 compatibility mode không biến H2 thành PostgreSQL/MySQL thật.
13. Viết mapping smoke tests nhanh và tests chạy trên PostgreSQL Testcontainers.
14. Kiểm chứng dữ liệu bằng `persist → flush → clear → find`.
15. Kiểm thử database constraints bằng negative test trên DBMS mục tiêu.
16. Thiết kế test thực sự xác minh optimistic locking/transaction isolation với nhiều contexts.
17. Hiểu lock behavior, deadlocks và concurrency không được mô phỏng đầy đủ trong embedded tests.
18. Kiểm thử SQL native queries, DDL và migration syntax theo dialect thật.
19. Phân biệt correctness tests với performance/plan tests.
20. Không dùng benchmark H2 để dự đoán index/query performance trên production.
21. Tổ chức CI theo các tầng unit, embedded JPA, target-DB integration và migration/upgrade.
22. Chọn bộ fixture dữ liệu đại diện cho các khác biệt quan trọng.
23. Hiểu rủi ro `@DataJpaTest` tự thay datasource bằng embedded database.
24. Dùng `@AutoConfigureTestDatabase(replace = NONE)` hoặc cơ chế tương đương khi cần target DB.
25. Xây risk-based test matrix và báo cáo rõ điều H2 đã chứng minh/chưa chứng minh.
26. Thiết kế cách chạy tests độc lập, ổn định và không đụng dữ liệu production.
27. Xác định khi nào cần kiểm tra trên staging/production-like topology ngoài containers.
28. Trình bày được chiến lược kiểm thử JPA đáng tin cậy cho một dự án thực tế.

---

## 2. Đừng đồng nhất “embedded” và “in-memory”

Các thuật ngữ thường bị dùng như nhau dù không đồng nghĩa.

| Thuật ngữ | Đặc điểm | Ví dụ |
|---|---|---|
| Embedded database | Engine được nhúng vào tiến trình ứng dụng/test, có thể không cần một server riêng | H2 embedded, HSQLDB embedded, SQLite |
| In-memory database | Dữ liệu chính nằm trong bộ nhớ trong một chế độ vận hành | H2 `jdbc:h2:mem:...`, HSQLDB mem |
| File-backed embedded DB | Engine vẫn nhúng nhưng dữ liệu có thể tồn tại trong file | H2 file mode, SQLite file |
| Server DBMS | Engine chạy ở tiến trình/server độc lập, nhiều clients kết nối mạng | PostgreSQL, MySQL, Oracle, SQL Server |
| Containerized server DB | Server DBMS thật chạy trong container dùng cho test | PostgreSQL Testcontainers |
| Production-like database | Cùng engine/version/config/schema tương đối sát môi trường đích | Postgres container hoặc staging Postgres |
| Mock/Fake repository | Mô phỏng giao diện lưu trữ, không chạy DB engine | In-memory Map fake |

### 2.1. Ví dụ H2 in-memory

```properties
spring.datasource.url=jdbc:h2:mem:jpa_test
```

Database tồn tại trong phạm vi lifecycle/connection semantics của H2 và cấu hình tương ứng. Cần lưu ý những options như `DB_CLOSE_DELAY` khi có nhiều connections/context trong test.

### 2.2. H2 file-backed vẫn là H2

```properties
spring.datasource.url=jdbc:h2:file:./build/testdb
```

Một file database có thể tồn tại qua lần chạy, nhưng SQL dialect, constraint engine và transaction behavior vẫn là H2, **không biến thành PostgreSQL**.

### 2.3. PostgreSQL trong container không phải database nhúng

`PostgreSQLContainer<?>` khởi động một **PostgreSQL server thật** trong container, nối bằng JDBC qua network/port mapping. Nó khác H2 in-memory về architecture lẫn SQL behavior. Container hỗ trợ kiểm thực hơn nhưng tốn startup/resources hơn.

### 2.4. SQLite không phải H2

SQLite embedded thường lưu một file, có typing/locking/DDL semantics riêng. Việc dùng SQLite với Hibernate/JPA cần JDBC driver và Hibernate dialect/provider support phù hợp phiên bản, không nên giả định nó là test substitute portable cho mọi ứng dụng JPA.

---

## 3. Hai mục tiêu kiểm thử khác nhau

### 3.1. Khi dùng database nhúng

Một bộ test H2 có thể rất hữu ích để nhanh chóng phát hiện:

- Entity không được scan/đăng ký.
- Thiếu `@Id` hoặc mapping không hợp lệ.
- JPQL attribute name sai.
- Repository methods phát query không như dự kiến.
- Cascading persist cơ bản bị cấu hình nhầm.
- `@Embedded` round-trip với các types thông thường.
- Bất biến Java và data access logic cơ bản.
- Phân trang/sorting/filtering ở mức logic đơn giản.

### 3.2. Khi cần database mục tiêu

Các nhu cầu phải được kiểm ở DBMS mục tiêu hoặc môi trường thật tương ứng:

- Native SQL/PostgreSQL `ON CONFLICT`, JSONB, arrays, functions.
- MySQL `AUTO_INCREMENT`/collation/implicit DDL commits.
- PostgreSQL sequences và enum/check constraints.
- Oracle identity/sequence/string/null semantics.
- SQL Server IDENTITY, rowversion, datetime handling.
- Transaction isolation/row locks/deadlocks.
- Index creation/online DDL và plans.
- Schema migrations từ version đã triển khai.
- Precision, timezone, Unicode/collation quan trọng.
- Database-specific error codes/concurrency behavior.

### 3.3. Không phải “càng thật càng tốt” cho mọi test

Nếu test `Money.plus` thuần Java, khởi động một Postgres container chỉ tăng độ trễ và yếu tố có thể fail không liên quan. Mỗi test nên dùng môi trường **nhẹ nhất vẫn chứng minh được điều nó hứa kiểm tra**.

---

## 4. Sơ đồ ranh giới của một test

```text
                     MÃ ỨNG DỤNG
               domain model / service
                          |
                          v
                     JPA PROVIDER
              entity mapping + JPQL
                          |
                 JDBC + dialect SQL
                          |
           +--------------+-------------+
           |                            |
           v                            v
      H2 IN MEMORY                POSTGRESQL SERVER
      quick feedback               actual DB engine
           |                            |
           v                            v
   Cùng mã JPA có thể             SQL, constraints,
   chạy hợp lệ ở H2               locks, schema riêng
           |                            |
           +--------------+-------------+
                          |
                          v
             SO SÁNH HỢP ĐỒNG TEST
       Điều gì đã được kiểm chứng?
       Điều gì chỉ được giả định?
```

Điểm sai thường gặp là **test trên H2 nhưng gọi kết quả là “đã kiểm thử PostgreSQL”**. Hãy ghi rõ engine, version, schema source và các ranh giới chưa được kiểm tra.

---

## 5. SQL dialect: cùng JPQL, SQL sinh ra có thể khác

JPA cho phép viết:

```jpql
SELECT p
FROM PaymentRecord p
WHERE p.status = :status
ORDER BY p.createdAt DESC, p.id DESC
```

Provider chuyển query thành SQL theo dialect đã cấu hình.

### 5.1. Khác biệt cú pháp

Một số DBMS dùng `LIMIT/OFFSET`, số khác dùng `FETCH FIRST`/`OFFSET FETCH` hoặc kỹ thuật khác tùy version. Hibernate Dialect chọn SQL tương ứng.

### 5.2. Khác biệt DDL

Identity column có thể dùng:

```sql
-- PostgreSQL:
id BIGINT GENERATED BY DEFAULT AS IDENTITY
```

hoặc:

```sql
-- MySQL:
id BIGINT AUTO_INCREMENT
```

Một mapping Java dùng `@GeneratedValue(strategy=IDENTITY)` không tự xác nhận DDL của mọi target DBMS chính xác chỉ vì nó chạy trên H2.

### 5.3. Khi nào JPQL portable?

JPQL tránh nhiều chi tiết SQL dialect và thường tăng khả năng di chuyển. Tuy nhiên:

- Function support có thể phụ thuộc provider/DB.
- Column types/constraints vẫn khác.
- Generated SQL có thể khác đáng kể.
- Query planner khác.
- Isolation và locking ngoài ngôn ngữ JPQL.

**Cùng JPQL syntax hợp lệ** không chứng minh cùng hiệu năng hay transaction semantics.

---

## 6. H2 compatibility mode: hữu ích nhưng có giới hạn

H2 có chế độ tương thích cú pháp như:

```properties
spring.datasource.url=jdbc:h2:mem:testdb;MODE=PostgreSQL
```

Nó có thể giúp H2 chấp nhận hoặc xử lý một số cú pháp/semantics gần PostgreSQL hơn trong phạm vi mà H2 hỗ trợ.

### 6.1. Nó *không* làm gì?

Nó không biến H2 thành PostgreSQL engine với cùng:

- MVCC implementation và row locks.
- Server-side cursors/JDBC PostgreSQL driver.
- Catalog, extensions, roles, grants.
- JSONB internals và operators toàn diện.
- WAL, replication hoặc vacuum behavior.
- Index/DDL locking/online DDL.
- Query optimizer và statistics.
- Collation/ICU configuration.
- Transaction isolation corner cases.

### 6.2. Một test pass có thể che lỗi thật

Ví dụ một native SQL query vô tình dùng feature mà H2 mode cho phép nhưng production schema/collation/extension khác. Kết quả functional nhỏ đúng không chứng minh deployment đúng.

### 6.3. Một test fail cũng có thể là false negative

PostgreSQL chấp nhận cú pháp native `CREATE INDEX CONCURRENTLY` hoặc `ON CONFLICT` phù hợp, nhưng H2 không mô phỏng chính xác hoặc từ chối. Đừng viết lại SQL PostgreSQL đúng thành cú pháp sai chỉ để mọi test H2 xanh.

### 6.4. Quy tắc sử dụng mode

Dùng compatibility mode để thuận tiện cho tests ít phụ thuộc vendor. Khi test một feature đặc thù PostgreSQL, chạy trên PostgreSQL thật.

---

## 7. H2 version ảnh hưởng kết quả test

Không nên chỉ nói “H2” mà bỏ qua version. Các phiên bản H2 có thay đổi đáng kể về SQL parsing, typing và compatibility behavior.

### 7.1. Cảnh báo test dependency upgrade

Một project nâng H2 nhưng không nâng Hibernate dialect hoặc test scripts có thể gặp lỗi trước đây chưa có. Đây không nhất thiết là lỗi production DB.

### 7.2. Pin dependency versions trong CI

Dùng dependency management/lockfiles phù hợp để test reproducible. Ghi H2 version trong bug report.

### 7.3. Không lấy “trước đây H2 cho phép” làm chuẩn correctness

H2 permissive behavior ở một phiên bản cũ có thể đã che một vấn đề schema hoặc JPQL từ lâu. Hãy đối chiếu với contract của DBMS mục tiêu.

---

## 8. Identity, sequence và generated identifiers

Entity:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

### 8.1. Tác động đến SQL

H2, PostgreSQL, MySQL và SQL Server có cú pháp/hành vi IDENTITY khác nhau. Với `GenerationType.SEQUENCE`, database cần sequence phù hợp hoặc provider-managed generator.

### 8.2. AUTO không có nghĩa mọi DB dùng cùng strategy

`GenerationType.AUTO` cho provider lựa chọn strategy dựa trên môi trường/dialect, có thể khác giữa embedded và target database.

### 8.3. Batch INSERT behavior cũng có thể khác

IDENTITY thường yêu cầu sinh ID qua INSERT; sequence cho phép provider có một số cơ hội cấp ID trước khi INSERT và batching khác. Test trên H2 không cho phép kết luận JDBC batch performance trên PostgreSQL/MySQL.

### 8.4. Các tình huống cần test

- Persist entity và nhận non-null ID.
- `persist → flush → clear → find` theo generated ID.
- Không hard-code ID=1.
- Sequence allocation giữa nhiều sessions nếu quan trọng.
- Constraint violation tại thời điểm persist/flush/commit.
- Bulk insert/parent-child cascade với strategy đã chọn.
- Schema migrations thực sự tạo sequence/identity columns.

---

## 9. BigDecimal, NUMERIC, DECIMAL và precision

Trong JPA:

```java
@Column(
    name = "amount",
    nullable = false,
    precision = 19,
    scale = 2)
private BigDecimal amount;
```

### 9.1. Những gì annotation mô tả

Nó gợi ý/khai báo metadata SQL numeric precision và scale cho provider/schema generation. Việc database thực thi giới hạn, round/truncate/error ra sao phụ thuộc column DDL thật và DBMS.

### 9.2. H2 và PostgreSQL không đồng nhất hoàn toàn

Một số corner cases về scale, overflow, numeric casts hoặc parameter binding có thể khác. Một test lưu `12.50` trên H2 chưa chứng minh production xử lý đúng các giá trị sát giới hạn hoặc scale vượt mức.

### 9.3. Giá trị cần thử

| Ca test | Điều cần xác minh |
|---|---|
| 0.00 | Zero representation |
| 12.50 | Giá trị và scale sau round-trip |
| 99999999999999999.99 (nếu quá giới hạn) | DB từ chối/behavior theo precision |
| 12.345 | Quy tắc làm tròn hoặc từ chối |
| Giá trị âm | Domain và CHECK constraint nếu yêu cầu |
| NULL | Nullability |
| Arithmetic/query filters | Comparison/binding semantics |

Với NUMERIC(19,2), precision gồm **tổng 19 chữ số**, scale 2; vì vậy giá trị quá 17 chữ số ở phần nguyên có thể vượt giới hạn. Chọn số biên hợp lệ/không hợp lệ dựa trên quy tắc ấy.

### 9.4. BigDecimal equals vs compareTo

`new BigDecimal("12.50").equals(new BigDecimal("12.5"))` là false vì scale khác, trong khi `compareTo` coi bằng nhau về trị số. Test phải quyết định contract đòi scale cố định hay chỉ giá trị bằng nhau, không vô tình làm test phụ thuộc driver scale khi không cần.

---

## 10. Timestamp, Instant và timezone

Các kiểu Java thường gặp:

- `LocalDate`.
- `LocalDateTime`.
- `Instant`.
- `OffsetDateTime`.
- `ZonedDateTime` (yêu cầu mapping cụ thể).

### 10.1. Rủi ro mapping

- PostgreSQL `timestamp with time zone` và `timestamp without time zone` có semantics khác.
- MySQL `TIMESTAMP` và `DATETIME` có hành vi timezone/conversion khác.
- JDBC driver có thể chuyển theo JVM/session timezone.
- Precision của fractional seconds có thể khác.
- Một số DBMS không giữ original offset, chỉ lưu/chuẩn hóa instant.
- Session settings và daylight saving transitions tạo corner cases.

### 10.2. Unit test không đủ

`Instant.parse(...)` trong Java là domain/JDK behavior. Muốn chứng minh DB lưu đúng, phải persist/flush/clear/find trên target DB.

### 10.3. Fixture biên

```java
Instant winter = Instant.parse(
    "2026-01-15T00:00:00Z");

Instant nearMidnight = Instant.parse(
    "2026-11-15T23:59:59.123456Z");
```

Test nên so theo precision được contract cho phép, tránh assert nanoseconds khi cột database lưu microseconds.

### 10.4. Không suy từ H2 timestamp behavior

H2 có thể pass khi chạy trên laptop timezone +07 nhưng PostgreSQL production session ở UTC có semantics khác. Kiểm target DB cùng driver/session timezone/config.

---

## 11. EnumType.STRING và native enum

Mapping portable:

```java
@Enumerated(EnumType.STRING)
@Column(name = "status", length = 20)
private PaymentStatus status;
```

### 11.1. H2 thường lưu chuỗi dễ dàng

Một mapping smoke test có thể chứng minh Java enum round-trip.

### 11.2. Target DB có thể có ràng buộc thêm

- PostgreSQL CHECK hoặc native enum type.
- MySQL ENUM column.
- Database migration đã định nghĩa allowed values.
- Collation/case-sensitivity của cột.

### 11.3. Đổi enum cần test dữ liệu cũ

Nếu enum Java `SETTLED` đổi thành `COMPLETED` nhưng database còn `SETTLED`, app mới có thể fail đọc rows cũ. Embedded create-drop test không chứa legacy values nên không phát hiện. Cần migration upgrade test.

### 11.4. ORDINAL rất nhạy với reorder

Thêm/reorder Java enum constants có thể đổi semantic values của database nếu dùng ORDINAL. Nếu contract lưu trạng thái rõ ràng, STRING thường dễ kiểm soát hơn, nhưng vẫn cần migration khi rename values.

---

## 12. UUID, JSON, arrays và custom types

Không phải mọi SQL type đều có cùng representation.

### 12.1. UUID

PostgreSQL có native `uuid`; H2 có UUID support nhưng drivers/DDL/dialect choices vẫn có thể khác. MySQL thường biểu diễn UUID bằng CHAR/BINARY theo thiết kế. Test round-trip và schema ở target khi UUID là primary/foreign key quan trọng.

### 12.2. JSON

PostgreSQL `jsonb` có operators/indexes đặc thù. Một test H2 lưu JSON string có thể kiểm JSON serialization logic nhưng không xác minh:

- Query JSON paths.
- `jsonb` containment operators.
- GIN indexes.
- JSON constraint/functions.
- Database-level sort/comparison.

### 12.3. Arrays

PostgreSQL arrays và JDBC array binding khác nhiều DBMS. H2 có thể hỗ trợ array theo cách riêng nhưng không bảo đảm entity converter/native queries portable.

### 12.4. LOB/CLOB/BLOB

Row width, streaming, driver buffering, encoding và transaction lifetime khác nhau giữa DBMS. Với file/LOB lớn, test target DB/driver quan trọng hơn mapping smoke trên H2.

### 12.5. Custom types/converters

`AttributeConverter` thuần Java có thể được unit test cho convert-to/from-database-column; nhưng provider có thực sự áp converter và lưu đúng SQL type/column thì phải test JPA integration.

---

## 13. Identifiers: chữ hoa/thường, quoting và reserved words

Giả sử:

```java
@Table(name = "Order")
@Column(name = "User")
```

Tùy dialect, `ORDER`/`USER` có thể là reserved words, hoặc identifier folding/quoting khác nhau.

### 13.1. Database object naming có thể khác

- PostgreSQL thường fold unquoted identifiers về lowercase.
- Các DBMS khác có rules về case, catalog/schema, quoted names và filesystem settings khác.
- Hibernate physical naming strategies có thể biến `createdAt` thành `created_at`.

### 13.2. H2 có thể che/làm lộ lỗi riêng

`MODE=PostgreSQL` hoặc `DATABASE_TO_LOWER` có thể thay behavior của H2, nhưng không bảo đảm hoàn toàn giống PostgreSQL catalog/case rules.

### 13.3. Quy tắc thực hành

- Dùng tên bảng/cột rõ, tránh reserved words.
- Có naming strategy thống nhất.
- Schema migrations và mappings phải dùng cùng physical names.
- Test startup với `ddl-auto=validate` trên target DB.
- Với native SQL, test trực tiếp trên target.

---

## 14. Collation, case sensitivity và UNIQUE

Ví dụ emails:

```text
Alice@example.com
alice@example.com
```

Hai chuỗi có được coi là trùng trong database UNIQUE không? Câu trả lời phụ thuộc column collation/type/index/expression và DBMS.

### 14.1. PostgreSQL

Một cột `VARCHAR` thông thường với unique index có semantics khác với collation không phân biệt hoa/thường hoặc `citext` extension. Nếu muốn case-insensitive uniqueness, phải thiết kế explicit.

### 14.2. MySQL

Collation mặc định thường có thể case-insensitive tùy cài đặt/schema/column. Hai giá trị có thể bị coi là duplicate mà H2 test không tái hiện giống.

### 14.3. Unicode và normalization

Vietnamese diacritics, normalization forms, Turkish dotted/dotless I và accents có thể cho kết quả khác giữa collations. `LOWER(...)` không nhất thiết là chuẩn normalization hoàn chỉnh cho mọi ngôn ngữ.

### 14.4. Test trên target DB

- Insert hai giá trị chỉ khác case.
- Thử accents/Unicode.
- Kiểm unique violation đúng.
- Thử LIKE/ILIKE/LOWER theo query.
- Ghi collation/index configuration.
- Không giả định Java `String.equalsIgnoreCase` tương đương SQL collation.

---

## 15. NULL semantics và sort order

SQL có logic ba trị: TRUE, FALSE, UNKNOWN. `NULL = NULL` không cho TRUE; phải dùng `IS NULL` khi kiểm null.

Nhưng DBMS có khác biệt trong:

- Default ordering của NULL khi `ORDER BY ASC/DESC`.
- `NULLS FIRST/LAST` syntax/support.
- Unique constraints với NULL values.
- Empty string vs NULL ở một số engines.
- Indexing nullable columns.

### 15.1. Một test sorting trên H2 có thể xanh nhưng production khác

Nếu trang dữ liệu sort `ORDER BY shipped_at` và nhiều rows chưa shipped (NULL), thứ tự mặc định có thể khác theo DBMS.

### 15.2. Cần hợp đồng sort rõ

Nếu UX yêu cầu null last:

```jpql
ORDER BY
  CASE WHEN p.shippedAt IS NULL THEN 1 ELSE 0 END,
  p.shippedAt ASC,
  p.id ASC
```

Đây là ví dụ JPQL ý tưởng cho entity có `shippedAt` mapped; DB SQL có thể có `NULLS LAST` nhưng muốn portable phải cân nhắc provider/query support và test trên target.

### 15.3. Empty string khác NULL

Một số DBMS có semantics đặc biệt với chuỗi rỗng; Oracle là ví dụ quen thuộc nơi empty character strings thường được xử lý như NULL trong nhiều trường hợp. Không suy quy tắc này từ H2/MySQL/PostgreSQL.

---

## 16. Boolean types và binding

Trong Java:

```java
@Column(name = "active", nullable = false)
private boolean active;
```

Database có thể dùng:

- PostgreSQL `boolean`.
- MySQL `BOOLEAN` alias/representation theo engine/version.
- Một số systems dùng `BIT`/`NUMBER`/`CHAR` mapping.

### 16.1. JPQL tăng tính portable

```jpql
SELECT p
FROM PaymentRecord p
WHERE p.active = true
```

Provider sẽ dịch literal/binding theo dialect. Nhưng native SQL `WHERE active = TRUE` có thể không portable nguyên xi.

### 16.2. Test mapping và native queries riêng

Một JPQL mapping test pass trên H2 chưa chứng minh native SQL query của ứng dụng dùng boolean syntax đúng trên target.

### 16.3. NULLability matters

Primitive `boolean` không chứa null trong Java, nhưng database column nullable có thể chứa NULL do legacy writes. Nếu mapping vào primitive, data semantics có thể gây vấn đề khi đọc. Migration/data tests nên kiểm null legacy.

---

## 17. Database constraints: nơi H2 thường không đủ bằng chứng

Một ứng dụng thực tế cần:

- PRIMARY KEY.
- FOREIGN KEY.
- UNIQUE.
- NOT NULL.
- CHECK.
- DEFAULT.
- Generated columns.
- Partial/expression indexes.
- Deferrable constraints khi DB hỗ trợ.

### 17.1. Kiểm thử JPA round-trip không phải constraint test

Nếu insert một PaymentRecord hợp lệ rồi đọc lại, bạn chưa chứng minh DB từ chối amount âm hoặc external_ref trùng.

### 17.2. Negative DB tests

Thử trực tiếp dữ liệu vi phạm và kiểm đúng constraint/root cause trên target DB.

### 17.3. Các DBMS không cùng hỗ trợ mọi constraint

Ví dụ CHECK constraints ở các phiên bản MySQL cũ không luôn được enforce như các phiên bản mới; H2 có thể enforce theo cách khác. Chọn engine/version sát production.

### 17.4. FK có thể bị tắt ở một số môi trường

Đừng suy database engine hiện tại luôn enforce FK nếu schema/test configuration cho phép disable. SQLite cần chú ý cấu hình enforcement của foreign keys; các engine khác có flags/options riêng.

---

## 18. Transaction isolation: môi trường nhúng dễ bỏ sót race

Một nghiệp vụ:

```text
Thread A: SELECT balance = 100
Thread B: SELECT balance = 100
Thread A: UPDATE balance = 70
Thread B: UPDATE balance = 40
```

Kết quả phụ thuộc locking, isolation, update predicates và optimistic versioning.

### 18.1. H2 và PostgreSQL có engines khác nhau

Ngay cả khi cả hai hỗ trợ READ COMMITTED, internal MVCC, lock acquisition, timeout và snapshot behavior có thể khác.

### 18.2. MySQL InnoDB thường khác PostgreSQL

Default isolation, gap locks/next-key locks, deadlock detection và phantom/locking reads khác theo DBMS/config. Không kết luận concurrency correctness từ một H2 test tuần tự.

### 18.3. Test hai sessions/transactions

Để kiểm optimistic locking/lost update hoặc locking:

1. Seed và commit data.
2. Tạo EntityManagers/transactions độc lập.
3. Load cùng data.
4. Điều khiển thứ tự operations và commits.
5. Assert conflict/state cuối.
6. Rollback cleanup.
7. Lặp với target DBMS/version.

### 18.4. Unit tests vẫn cần nhưng không đủ

Domain unit test có thể chứng minh `withdraw(30)` không cho balance âm. Nhưng không thể chứng minh database isolation không để hai transactions vượt hạn mức.

---

## 19. @Version và optimistic locking

```java
@Version
private long version;
```

### 19.1. Functional mapping test

Persist/modify entity, flush và kiểm version state như một phần của mapping. Thời điểm increment có thể phụ thuộc provider/flush.

### 19.2. Concurrency test

Hai persistence contexts cùng load version V0, một transaction commit update, transaction còn lại cố update dữ liệu stale — kỳ vọng optimistic conflict.

### 19.3. Không dùng một EntityManager

Persistence context duy trì identity map, nên hai `find` trong cùng context có thể trả cùng object. Không tạo hai phiên bản stale độc lập.

### 19.4. DB target quan trọng

Row locks, transaction visibility và exception wrapping có thể khác. Test trên H2 có thể chứng minh basic provider semantics nhưng không đủ cho production concurrency policy.

---

## 20. Pessimistic locks và SKIP LOCKED

JPA hỗ trợ một số lock modes như `PESSIMISTIC_WRITE`. SQL sinh ra, lock timeout và supported features khác nhau giữa DBMS.

### 20.1. Test trên H2 không chứng minh production lock behavior

H2 có thể chấp nhận syntax hoặc behavior riêng nhưng không tái hiện PostgreSQL row-level locks/skip-locked semantics hoặc MySQL next-key locks giống hệt.

### 20.2. Các ca cần target DB

- Two writers cố update cùng row.
- Lock timeout.
- Deadlock/rollback.
- Pessimistic lock modes.
- `SELECT ... FOR UPDATE` native query.
- `SKIP LOCKED` consumer queues.
- Phạm vi lock của JOINs.
- Transaction cancellation.

### 20.3. Không kiểm concurrency chỉ với test tuần tự

Concurrency test nên đồng bộ bằng barriers/latches và có timeout tránh suite treo. Nhưng cần xác định cách các transactions bắt đầu/commit độc lập và không dùng chung một EntityManager giữa threads.

---

## 21. Transactional DDL và migration engine

Một migration:

```sql
ALTER TABLE payment_records ADD COLUMN source VARCHAR(20);
UPDATE payment_records SET source = 'WEB' WHERE source IS NULL;
ALTER TABLE payment_records ALTER COLUMN source SET NOT NULL;
```

Cú pháp ví dụ trên thiên về PostgreSQL, không portable nguyên vẹn.

### 21.1. PostgreSQL

Nhiều DDL statements có transactional semantics, nhưng có ngoại lệ như `CREATE INDEX CONCURRENTLY` không chạy trong transaction block thông thường.

### 21.2. MySQL

Nhiều DDL operations có implicit commit/atomic DDL behavior riêng theo version; không mặc định một migration nhiều statements rollback giống PostgreSQL.

### 21.3. H2

H2 có cách xử lý transaction/schema DDL riêng, không thể chứng minh rollback/partial migration state trên PostgreSQL/MySQL bằng cách chạy H2.

### 21.4. Cần kiểm trên target DB

Migration engine, schema history, schema state sau failure và khả năng khôi phục phải được kiểm tra theo DBMS/version production.

---

## 22. Hibernate create-drop không thay migrations

Một test H2 thường dùng:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:testdb
  jpa:
    hibernate:
      ddl-auto: create-drop
```

Nó tạo schema từ mappings hiện tại, thích hợp disposable test DB.

Nhưng production có thể dùng:

```text
db/migration/
  V1__create_payment_records.sql
  V2__add_payment_source.sql
  V3__create_payment_indexes.sql
```

### 22.1. Lỗi phổ biến

Developer thêm field mới `source` vào entity; H2 create-drop tự tạo cột, integration test xanh. Nhưng Flyway migration chưa thêm cột vào PostgreSQL production, ứng dụng mới fail.

### 22.2. Migration-aligned test

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
```

Schema do migrations tạo; Hibernate validate một phần mapping/schema compatibility. Đừng cho Hibernate `update` tự sửa cột trong test nhằm chứng minh migrations.

### 22.3. Fresh-install khác upgrade-path

Fresh install: áp tất cả migrations từ database rỗng. Upgrade: bắt đầu từ schema version cũ có data rồi áp pending migrations. Cả hai cần được kiểm riêng khi production đã có dữ liệu.

---

## 23. Native SQL: rủi ro phụ thuộc vendor cao

Ví dụ PostgreSQL:

```sql
INSERT INTO payment_records (
    external_ref, amount, status, created_at, version
) VALUES (
    ?, ?, ?, ?, 0
)
ON CONFLICT (external_ref)
DO UPDATE SET status = EXCLUDED.status;
```

### 23.1. H2 MODE=PostgreSQL chưa đủ

Nó có thể mô phỏng vài cú pháp nhưng không chứng minh constraint target, locking conflicts và atomic behavior giống PostgreSQL thật.

### 23.2. MySQL dùng chiến lược upsert khác

`INSERT ... ON DUPLICATE KEY UPDATE` có cú pháp và behavior riêng. Không nên viết một native query rồi chạy H2 mà tuyên bố nó portable.

### 23.3. Test native SQL ở nơi nó sẽ chạy

Dùng target DB integration tests với cả trường hợp insert mới và conflict, nhiều transactions nếu atomicity quan trọng, kiểm state cuối và error behavior.

### 23.4. Khi có thể, dùng JPQL/Criteria

JPA giúp giảm phụ thuộc SQL dialect cho nhiều truy vấn. Tuy nhiên không ép mọi vendor-specific feature vào JPQL nếu semantics hoặc hiệu năng không phù hợp; chỉ cần tách đúng provider-specific integration suite.

---

## 24. JSON, partial indexes và views

PostgreSQL:

```sql
CREATE INDEX idx_payments_metadata
ON payment_records
USING GIN (metadata);
```

hoặc:

```sql
CREATE UNIQUE INDEX uq_active_ref
ON payment_records (external_ref)
WHERE archived_at IS NULL;
```

Đây là những đặc tính engine/index nâng cao; migration và native SQL tests phải chạy trên PostgreSQL. H2 không tái hiện đầy đủ GiST/GIN, JSONB và partial index behavior.

### 24.1. DDL phát sinh từ annotation chưa đủ

`@Index` JPA chỉ mô tả một số indexes thông thường. Một database-specific index cần migration SQL hoặc tooling chuyên biệt.

### 24.2. View/function/trigger

Nếu query qua view hoặc dựa vào database function/trigger, test phải bao gồm definitions trong migration. Hibernate schema validation không bảo đảm phát hiện mọi thiếu sót/khác biệt ở đây.

---

## 25. SQL query planner khác nhau

Cùng JPQL:

```jpql
SELECT p
FROM PaymentRecord p
WHERE p.status = :status
ORDER BY p.createdAt DESC
```

có thể dịch ra SQL tương đương về kết quả, nhưng DBMS chọn execution plan khác:

- Sequential scan.
- Index scan.
- Bitmap scan.
- Nested loop/hash/merge join.
- Sort/hash aggregate.
- Parallel plan.
- Temporary disk spilling.

### 25.1. H2 benchmark không dự báo PostgreSQL performance

H2 chạy in-process, ít data, cache khác, không có network overhead giống server DBMS. Một câu SELECT nhanh trên H2 không chứng minh Postgres dùng index tốt.

### 25.2. Performance test phải có dữ liệu đại diện

Một query với 10 rows không phản ánh plan cho 10 triệu rows. Cần đủ cardinality, skew/distribution, indexes, statistics, concurrency và row width phù hợp.

### 25.3. EXPLAIN trên target DB

Ví dụ PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, external_ref
FROM payment_records
WHERE status = 'SETTLED'
ORDER BY created_at DESC;
```

`EXPLAIN ANALYZE` thực thi câu truy vấn; chỉ chạy ở môi trường/khối lượng được phép. Với DBMS khác, dùng công cụ/SQL EXPLAIN tương ứng.

### 25.4. Đo cả DB và application

SQL count, rows, network bytes, latency p95/p99, entity hydration, heap/GC, connection pool và lock waits đều có thể ảnh hưởng request.

---

## 26. Connection pools và môi trường thực thi

H2 in-memory thường tránh network round-trip, server authentication và TCP failures.

Target DBMS có thể có:

- Connection pool limits.
- TLS/SSL authentication.
- Proxy/load balancer.
- Connection acquisition timeout.
- Database failover.
- Server-side prepared statements.
- Socket timeouts.
- Replication lag/read replicas.
- Transaction session settings.

### 26.1. Mapping test không phải operational test

Một repository query pass trên H2 không chứng minh retry/failover behavior hoặc pool exhaustion của production.

### 26.2. Container tests giúp được gì?

Chúng có networked DBMS và JDBC driver thật, nên phát hiện nhiều vấn đề connection/dialect hơn. Nhưng topology vẫn có thể khác production, ví dụ không có PgBouncer/replicas/TLS policies.

### 26.3. Staging hoặc specialized tests

Để đánh giá failover, pool, read/write routing, replicas và TLS, cần môi trường/công cụ gần production hơn một container đơn lẻ.

---

## 27. Hình thức test thay đổi theo câu hỏi

| Mục tiêu | H2/HSQLDB nhanh | Target DB container | Staging/prod-like |
|---|---|---|---|
| Domain arithmetic | Không cần DB | Không cần | Không cần |
| Entity boot + simple CRUD | Tốt | Tốt | Không cần thường xuyên |
| JPQL attribute names | Tốt | Tốt | Ít cần |
| Cascade/orphan baseline | Có ích | Nên có representative tests | Không thường xuyên |
| Native PostgreSQL query | Không đủ | **Cần** | Tùy mức rủi ro |
| JSONB/GIN/partial index | Không đủ | **Cần** | Nên rehearsal lớn |
| DB timezone/precision | Một phần | **Cần** | Khi sản phẩm nhạy cảm |
| Unique/collation | Không đủ nếu khác DB | **Cần** | Nếu production ICU/collation đặc biệt |
| @Version conflict | Một phần | **Cần** | Nếu concurrency cao |
| Deadlock/locking | Không đủ | **Cần** | Nếu load/topology quan trọng |
| Flyway fresh install | Có thể smoke | **Cần** | Deployment rehearsal |
| Migration với dữ liệu cũ | Chưa đủ | **Cần** | Large-data rehearsal |
| Query plan/latency | Không đại diện | Có ích | **Cần** nếu tối ưu production |
| Backup/failover | Không phù hợp | Hạn chế | **Cần** |

---

## 28. Đừng để @DataJpaTest âm thầm thay datasource

Spring Boot `@DataJpaTest` tối ưu cho JPA slice. Tùy Spring Boot version và auto-configuration, test datasource có thể được thay bằng embedded DB nếu có dependency phù hợp.

### 28.1. Vấn đề

Bạn viết test với PostgreSQLContainer nhưng không kiểm Spring datasource cuối cùng; framework có thể dùng H2 thay thế ở một số cấu hình. Kết quả test xanh nhưng **không hề chạy trên PostgreSQL**.

### 28.2. Bảo vệ cấu hình

Một cách phổ biến:

```java
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
```

### 28.3. Test phải báo rõ target

Có thể dùng JDBC metadata:

```java
String productName =
    connection.getMetaData().getDatabaseProductName();

assertEquals("PostgreSQL", productName);
```

Code này đặt ở integration test có `DataSource` và resource cleanup phù hợp. Nó giúp xác minh thực sự nối vào PostgreSQL, không phải đoán từ cấu hình.

### 28.4. Kiểm version

```java
String version =
    connection.getMetaData().getDatabaseProductVersion();
```

Ghi version và driver metadata trong test diagnostics khi behavior nhạy với phiên bản.

---

## 29. Entity mẫu cho case study PaymentRecord

```java
package demo.payments;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "payment_records")
public class PaymentRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
        name = "external_ref",
        nullable = false,
        unique = true,
        length = 80)
    private String externalRef;

    @Column(
        name = "amount",
        nullable = false,
        precision = 19,
        scale = 2)
    private BigDecimal amount;

    @Enumerated(EnumType.STRING)
    @Column(
        name = "status",
        nullable = false,
        length = 20)
    private PaymentStatus status;

    @Column(
        name = "created_at",
        nullable = false)
    private Instant createdAt;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected PaymentRecord() {}

    public PaymentRecord(
            String externalRef,
            BigDecimal amount,
            Instant createdAt) {

        if (externalRef == null
            || externalRef.isBlank()) {
            throw new IllegalArgumentException(
                "Reference required");
        }

        Objects.requireNonNull(amount);
        Objects.requireNonNull(createdAt);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Amount must not be negative");
        }

        this.externalRef = externalRef.trim();
        this.amount = amount;
        this.createdAt = createdAt;
        this.status = PaymentStatus.NEW;
    }

    public void settle() {
        if (status != PaymentStatus.NEW) {
            throw new IllegalStateException(
                "Only NEW payments can settle");
        }
        status = PaymentStatus.SETTLED;
    }

    public Long getId() { return id; }
    public String getExternalRef() {
        return externalRef;
    }
    public BigDecimal getAmount() { return amount; }
    public PaymentStatus getStatus() {
        return status;
    }
    public Instant getCreatedAt() {
        return createdAt;
    }
    public long getVersion() { return version; }
}
```

Enum:

```java
package demo.payments;

public enum PaymentStatus {
    NEW,
    SETTLED,
    FAILED
}
```

### 29.1. Hai lớp trách nhiệm

- Constructor/`settle`: domain rules, có thể unit test không database.
- Annotations: identity, unique column, NUMERIC precision, enum string, timestamp và optimistic lock; phải test provider/schema.

### 29.2. Bài này dùng PostgreSQL làm môi trường mục tiêu minh họa

Thay bằng MySQL/Oracle/SQL Server thì migration SQL, JDBC driver, test container và query/constraint cases phải thay tương ứng. Không copy PostgreSQL DDL làm SQL portable cho mọi DBMS.

---

## 30. PostgreSQL migration cho PaymentRecord

Ví dụ `V1__create_payment_records.sql`:

```sql
CREATE TABLE payment_records (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    external_ref VARCHAR(80) NOT NULL,
    amount NUMERIC(19, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT uq_payment_records_external_ref
        UNIQUE (external_ref),

    CONSTRAINT ck_payment_records_amount
        CHECK (amount >= 0),

    CONSTRAINT ck_payment_records_status
        CHECK (status IN ('NEW', 'SETTLED', 'FAILED'))
);

CREATE INDEX idx_payment_records_status_created
    ON payment_records(status, created_at, id);
```

### 30.1. Vì sao explicit schema migrations?

Nó quản lý những đặc tính mà domain Java không tự kiểm soát: SQL types, CHECK constraints, indexes và schema history.

### 30.2. Hibernate validate còn giới hạn

`spring.jpa.hibernate.ddl-auto=validate` là guardrail hữu ích, nhưng không thay negative tests cho CHECK/UNIQUE hay kiểm index/collation.

### 30.3. Rủi ro timestamp mapping

Target dialect/provider có thể ánh xạ `Instant` thành một biến thể timestamp. SQL migration ở đây là minh họa dự kiến; muốn khẳng định mapping hoàn toàn tương thích phải chạy provider thực tế với DDL tương ứng và xử lý các type mismatches nếu xuất hiện.

### 30.4. Không dùng CHECK demo làm quy tắc chung mọi payment domain

Thực tế có thể cần refunds/negative adjustments và statuses khác. Constraints phải phản ánh business rules cụ thể, không sao chép máy móc.

---

## 31. Test mapping trên H2: giá trị và giới hạn

```java
@DataJpaTest(properties = {
    "spring.jpa.hibernate.ddl-auto=create-drop",
    "spring.flyway.enabled=false"
})
class PaymentRecordH2Test {

    @PersistenceContext
    EntityManager em;

    @Test
    void basicRoundTrip() {
        PaymentRecord payment =
            new PaymentRecord(
                "REF-001",
                new BigDecimal("12.50"),
                Instant.parse("2026-11-15T03:00:00Z")
            );

        em.persist(payment);
        em.flush();

        Long id = payment.getId();
        em.clear();

        PaymentRecord loaded =
            em.find(PaymentRecord.class, id);

        assertNotNull(loaded);
        assertEquals(
            "REF-001",
            loaded.getExternalRef());
        assertEquals(
            0,
            loaded.getAmount().compareTo(
                new BigDecimal("12.50")));
    }
}
```

### 31.1. Điều kiện

Test này cần Spring Data JPA, test dependencies, H2 JDBC trên test classpath, entity scanning phù hợp. Đoạn code minh họa bỏ qua imports và project-specific config.

### 31.2. H2 test đã chứng minh gì?

- Hibernate boot mapping.
- Entity persist và find được trên H2.
- Basic fields round-trip.
- Provider phát SQL hợp lệ cho H2.
- L1 context không che kết quả sau clear ở mức cơ bản.

### 31.3. Chưa chứng minh gì?

- Flyway PostgreSQL migration đầy đủ.
- NUMERIC/timestamp edge behavior trên PostgreSQL.
- Case-sensitive uniqueness/collation trên PostgreSQL.
- PostgreSQL CHECK/partial index.
- Production lock/isolation/deadlock behavior.
- Native SQL PostgreSQL.
- Query plans trên production.
- JDBC network/connection pool behavior.

Nhãn test nên thể hiện **H2 smoke**, không gọi nó là “PostgreSQL integration proof”.

---

## 32. PostgreSQL Testcontainers với Spring Data JPA

Một test slice trên DBMS mục tiêu:

```java
package demo.payments;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.junit.jupiter.api.Test;

import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;

import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.math.BigDecimal;
import java.time.Instant;

import static org.junit.jupiter.api.Assertions.*;

@DataJpaTest(properties = {
    "spring.jpa.hibernate.ddl-auto=validate",
    "spring.flyway.enabled=true"
})
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class PaymentRecordPostgresTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void registerDb(
            DynamicPropertyRegistry registry) {

        registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl);
        registry.add(
            "spring.datasource.username",
            postgres::getUsername);
        registry.add(
            "spring.datasource.password",
            postgres::getPassword);
    }

    @PersistenceContext
    EntityManager em;

    @Test
    void schemaFromMigrationsSupportsRoundTrip() {
        PaymentRecord payment =
            new PaymentRecord(
                "PG-REF-001",
                new BigDecimal("12.50"),
                Instant.parse("2026-11-15T03:00:00Z")
            );

        em.persist(payment);
        em.flush();

        Long id = payment.getId();
        em.clear();

        PaymentRecord loaded =
            em.find(PaymentRecord.class, id);

        assertNotNull(loaded);
        assertEquals(
            PaymentStatus.NEW,
            loaded.getStatus());
        assertEquals(
            "PG-REF-001",
            loaded.getExternalRef());
        assertEquals(
            0,
            loaded.getAmount().compareTo(
                new BigDecimal("12.50")));
    }
}
```

### 32.1. Dependencies

Cần Spring Data JPA, test starter, PostgreSQL JDBC driver, Testcontainers JUnit5/PostgreSQL, Flyway và PostgreSQL database support module tương ứng version nếu Flyway version yêu cầu.

### 32.2. Vì sao validate?

Provider không tự sửa schema. Nếu entity yêu cầu column chưa có trong migrations, startup validation có cơ hội phát hiện mismatch.

### 32.3. Vì sao không create-drop?

Vì mục tiêu là **kiểm thử PostgreSQL schema được sinh bởi migrations**, không phải xem Hibernate có thể tự dựng schema giống metadata.

### 32.4. Cần chọn container version phù hợp production

`postgres:16` chỉ là ví dụ. Nếu production là phiên bản PostgreSQL khác, pin version tương ứng; cập nhật image theo policy và kiểm lại migrations.

---

## 33. Xác minh test thực sự chạy PostgreSQL

Cấu hình có thể bị ghi đè bởi test profiles/auto-configuration; hãy đo chính datasource.

```java
@Autowired
DataSource dataSource;

@Test
void usesPostgreSqlNotH2() throws SQLException {
    try (Connection connection =
             dataSource.getConnection()) {

        DatabaseMetaData meta =
            connection.getMetaData();

        assertEquals(
            "PostgreSQL",
            meta.getDatabaseProductName());
    }
}
```

Imports:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

import org.springframework.beans.factory.annotation.Autowired;
```

### 33.1. Vì sao cần?

Nếu test lỡ dùng H2, một functional assertion vẫn có thể pass nhưng mục tiêu đánh giá khác biệt đã thất bại.

### 33.2. Không đọc connection URL làm bằng chứng duy nhất

Driver metadata/schema/database product name giúp xác nhận runtime target. Với môi trường phức tạp, có thể ghi cả database version/schema name/config liên quan.

### 33.3. Không trộn javax.sql với javax.persistence

`javax.sql.DataSource` là Java SE JDBC API, vẫn dùng trong ứng dụng Jakarta Persistence. Entity annotations ở Java mới nằm trong `jakarta.persistence.*`; hai namespace không có cùng quy tắc chuyển đổi.

---

## 34. @ServiceConnection là lựa chọn khác, không bắt buộc

Một số phiên bản Spring Boot hỗ trợ `@ServiceConnection` tích hợp Testcontainers:

```java
@Container
@ServiceConnection
static PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16");
```

### 34.1. Không trộn hai kiểu wiring thiếu chủ đích

Có thể dùng `@DynamicPropertySource` hoặc `@ServiceConnection` theo version/stack. Không tự đặt cả hai để rồi khó xác định property precedence.

### 34.2. Version-dependent

`@ServiceConnection` không có ở mọi Spring Boot version; cần đúng module/test classpath và auto-configuration. Nếu project đang ở version cũ, `@DynamicPropertySource` thường là lựa chọn dễ minh họa.

### 34.3. Không cần đổi toàn bộ project chỉ vì một annotation

Mục tiêu là **target DB thực sự được sử dụng**, không phải chọn cách đẹp nhất theo cú pháp.

---

## 35. Test constraint thực tế, không chỉ ORM round-trip

Ví dụ PostgreSQL CHECK amount:

```sql
INSERT INTO payment_records (
    external_ref, amount, status, created_at, version
) VALUES (
    'BAD-AMOUNT',
    -1.00,
    'NEW',
    CURRENT_TIMESTAMP,
    0
);
```

Database phải từ chối do `ck_payment_records_amount`.

### 35.1. Vì sao không tạo qua entity constructor?

Constructor PaymentRecord đã chặn amount âm. Nếu mục tiêu là **database constraint**, dùng JDBC/native SQL từ test DB để bypass domain validation.

### 35.2. Negative tests cần kiểm đúng lỗi

Không chỉ assert bất kỳ `RuntimeException`, vì lỗi có thể do thiếu cột/connection/permission. Dựa vào SQLState, constraint name hoặc exception root cause của JDBC/provider theo stack.

### 35.3. PostgreSQL transaction sau lỗi

Một transaction có SQL error thường phải rollback trước khi dùng tiếp. Tổ chức negative tests trong transactions riêng; đừng tiếp tục chạy nhiều assertions trên cùng failed transaction.

### 35.4. UNIQUE và case sensitivity

Thử hai external references khác nhau ở case:

```text
Pay-ABC
pay-abc
```

Kỳ vọng cần phụ thuộc schema business design: case-sensitive hay case-insensitive uniqueness. Không viết test chung với expected result không dựa vào collation/index thực tế.

---

## 36. Generated IDs và transaction test

Với `GenerationType.IDENTITY`:

1. Persist payment.
2. Flush nếu cần.
3. Assert ID non-null.
4. Không assert ID=1.
5. Clear persistence context.
6. Find theo ID.
7. Tạo transaction khác để kiểm commit visibility nếu đó là contract.
8. Test multiple inserts/unique conflict theo DBMS.

### 36.1. Sequence behavior không tự so từ H2

Nếu project dùng SEQUENCE, PostgreSQL sequence advance không rollback giống dữ liệu transaction; không kỳ vọng IDs luôn liên tục. H2 cũng có riêng semantics; kiểm application contract (unique generated ID, referential integrity) thay vì implementation detail không cần.

### 36.2. JDBC batching tùy strategy

Nếu dự án cần bulk throughput, benchmark target DB với identity/sequence strategy và Hibernate batching settings thật. H2 microbenchmark có thể dẫn tới kết luận sai.

---

## 37. Thử precision và timestamp boundaries trên PostgreSQL

### 37.1. Precision

Seed:

```text
amount = 0.00
amount = 12.50
amount = 99999999999999999.99 (giá trị sát giới hạn NUMERIC(19,2))
```

Lưu ý giá trị có 17 chữ số phần nguyên và 2 chữ số thập phân là biên theo precision 19/scale 2; nếu vượt số chữ số phần nguyên, database phải có behavior theo constraint type. Test rounding/overflow chỉ sau khi domain constructor cho phép fixture liên quan hoặc dùng SQL trực tiếp.

### 37.2. Timestamp

Test Instant quanh giờ UTC/ngày:

```java
Instant t = Instant.parse(
    "2026-11-15T23:59:59.123456Z");
```

So sánh sau persist/clear/find theo microsecond precision của cột; đừng assert nanoseconds nếu DB không lưu tương ứng.

### 37.3. Session/JVM timezone

Chạy test với timezone config đã biết; khi timezone là domain contract, thử các JVM/session timezone hoặc offsets đại diện. Ghi rõ expected Instant semantics.

### 37.4. Đừng để H2 quyết định production type

DDL target là nguồn thật khi production dùng migrations; Hibernate generated H2 DDL có thể khác.

---

## 38. Kiểm thử migrations trên target DB

Tối thiểu nên có:

**Fresh install:**

```text
Empty PostgreSQL container
        |
        v
Run all Flyway/Liquibase migrations
        |
        v
JPA validate
        |
        v
Persist/read representative entities
        |
        v
Check important constraints
```

**Upgrade path:**

```text
Schema V1 + representative legacy data
        |
        v
Apply pending V2/V3 migrations
        |
        v
Check data backfill / column transformations
        |
        v
JPA validate new mapping
        |
        v
Read/update old and new rows
```

### 38.1. Test H2 create-drop không thay hai paths này

Nó tạo ngay schema mới, không có legacy rows hoặc lịch sử DDL.

### 38.2. Không chỉnh versioned migration đã chạy production

Nếu migration V2 có sai cần sửa, thường tạo V3/V4 tiếp theo thay vì sửa V2 đã áp dụng trong môi trường chia sẻ, để history/checksum nhất quán.

### 38.3. Đánh giá data migration bằng assertions

Chẳng hạn thêm `source NOT NULL` cho payment cũ: cần backfill trước, kiểm không mất records, kiểm app old/new compatibility. Không thể suy từ entity annotation `nullable=false`.

---

## 39. Tạo chiến lược test theo mức rủi ro

Một bộ test nhiều tầng:

```text
                   CODE CHANGE
                       |
                       v
             UNIT TEST - NO DATABASE
              fast domain logic tests
                       |
                       v
           EMBEDDED JPA MAPPING SMOKE
           H2/HSQLDB CRUD, JPQL basics
                       |
                       v
         TARGET DB INTEGRATION TESTS
          PostgreSQL Testcontainers
          types, constraints, JPQL,
           native SQL, transactions
                       |
                       v
            MIGRATION INTEGRATION
          fresh install + old upgrade
                       |
                       v
          STAGING/PERFORMANCE REHEARSAL
          locks, indexes, concurrency,
         real row volumes, topology
```

### 39.1. Không nhất thiết mọi PR chạy toàn bộ staging

Fast suites có thể chạy mọi commit; target DB integration run trong CI; heavy data/migration/performance suites theo merge/release hoặc rủi ro. Nhưng critical target DB tests nên được chạy trước deploy.

### 39.2. Đừng bỏ target DB vì container startup chậm

Có thể tái sử dụng container trong test suite, chia schema, dùng cached images/CI workers; vẫn phải giữ isolation và tránh state leakage.

### 39.3. Đừng chạy production database làm test data

Dùng disposable DB/container, isolated schemas hoặc staging datasets đã ẩn danh/an toàn. Negative constraint tests và schema drops không được tác động production.

---

## 40. Phân lớp ca kiểm thử

| Loại ca | H2 | PostgreSQL container | Ghi chú |
|---|---|---|---|
| Simple persist/find | Có | Có representative | Chạy nhanh trên H2 |
| Named JPQL query | Có | Có nếu quan trọng | Validate dialect/SQL |
| DTO projection | Có | Có representative | Constructor/types |
| Cascade + orphan | Có | Có rủi ro cao | Real FK/DDL |
| Numeric precision | Có smoke | **Bắt buộc nếu nghiệp vụ nhạy** | Boundary values |
| Timestamp + timezone | Có smoke | **Bắt buộc khi nhạy** | Driver/DB semantics |
| Enum STRING | Có | Có với migrations | Legacy enum values |
| Unique/collation | Hạn chế | **Bắt buộc** | Case/Unicode |
| JSONB native query | Không đáng tin | **Bắt buộc** | Vendor-specific |
| @Version concurrency | Có basic | **Bắt buộc theo policy** | Two transactions |
| Pessimistic lock | Hạn chế | **Bắt buộc** | Lock levels |
| Flyway migrations | Không đủ | **Bắt buộc** | SQL dialect thật |
| Query plan/performance | Không đại diện | Có ích | Staging large data |
| Failover/replication | Không | Container riêng chưa đủ | Dedicated environment |

---

## 41. Viết test report chính xác

Một test run record nên ghi:

```text
Test suite: PaymentRecordPostgresTest
ORM provider: Hibernate <version>
JDBC driver: PostgreSQL JDBC <version>
DBMS: PostgreSQL <version>
Schema source: Flyway migrations V1..Vn
ddl-auto: validate
Transaction strategy: Spring @DataJpaTest rollback
Fixtures: 100 payment records + boundary cases
Scenarios: roundtrip, CHECK, UNIQUE, enum, timestamp
Pass/Fail: ...
Known gaps:
  - No 10m-row query performance
  - No failover/recovery test
  - No production-specific collation rehearsal
```

### 41.1. Không diễn giải quá mức

“100 H2 repository tests passed” là một kết quả có giá trị. Nhưng “100 H2 tests chứng minh Postgres production sẵn sàng” là tuyên bố vượt bằng chứng.

### 41.2. Ghi cấu hình quan trọng

Hibernate version, dialect, JDBC driver, SQL migrations, timezone, collation, isolation, container image tag và feature flags là những yếu tố có thể làm test thay đổi.

---

## 42. Khi nào một H2 test tạo false positive?

Ví dụ:

1. Mapping mới dùng column `payment_source`.
2. Test H2 cấu hình `ddl-auto=create-drop`.
3. Hibernate tạo column mới từ metadata.
4. Entity persist/read lại thành công.
5. Migration production chưa thêm `payment_source`.
6. PostgreSQL `ddl-auto=validate` fail hoặc SQL INSERT báo column missing.

H2 test xanh vì nó chỉ kiểm **schema do ORM hiện tại tự sinh**. Thiếu migration vẫn là bug.

Trường hợp khác:

1. H2 collation cho phép hai emails khác case.
2. Production MySQL collation coi chúng duplicate.
3. Một unit/integration test H2 giả định có thể insert cả hai.
4. Production phát unique violation.

**Giải pháp:** Test những khác biệt có rủi ro cao trên target DB và xác nhận schema source.

---

## 43. Khi nào một H2 test tạo false negative?

Ví dụ:

1. Ứng dụng dùng PostgreSQL-native JSONB operator.
2. Native SQL query hoạt động trên PostgreSQL.
3. H2 không parse hoặc mô phỏng đủ.
4. H2 test fail.
5. Developer nghĩ SQL production sai.

Trong trường hợp này, H2 là môi trường **không có khả năng chứng minh** feature cần test.

### 43.1. Không sửa feature đúng để chiều H2

Nếu SQL PostgreSQL cần GIN/jsonb operators, giữ integration test trên PostgreSQL. Domain unit/simple repository tests khác vẫn có thể dùng H2.

### 43.2. Tách profiles/suites rõ ràng

`PaymentH2SmokeTest` và `PaymentPostgresNativeSqlTest` có mục đích khác nhau. Không nhất thiết bắt một test chạy trên mọi engine nếu yêu cầu thật có chủ đích phụ thuộc vendor.

---

## 44. Sai khác do test setup, không phải DB engine

Không phải mọi failure giữa H2/Postgres đều do SQL dialect.

Có thể là:

- H2 test dùng `create-drop` nhưng PostgreSQL test dùng migrations.
- Hai suites khác test fixtures.
- `spring.jpa.hibernate.ddl-auto` khác.
- Một nơi bật `show_sql` hay global naming strategy khác.
- Timezone/JVM locale khác.
- H2 test chạy single thread, Postgres chạy concurrent.
- Test transaction rollback vs commit.
- H2 test có caching enabled, Postgres test disabled.
- PostgreSQL driver version khác production.

### 44.1. So sánh công bằng

Để đánh giá khác biệt DBMS, cố giữ cùng entity code, business rules, fixture values và assertions khi có thể. Ghi rõ các configs cố ý khác nhau vì mục đích test.

### 44.2. Nhưng đừng ép configs sai để “công bằng”

PostgreSQL migration SQL không nên chuyển sang H2-generated schema nếu mục tiêu là chứng minh production migration. Một số khác biệt là **chủ đích và cần thiết**.

---

## 45. Cách chọn test fixtures đại diện

Một data set chỉ có 1 payment với `amount=10.00` không phát hiện nhiều vấn đề. Bổ sung:

- Amount 0, số gần precision boundary, scale ngoài policy.
- Long externalRef gần giới hạn 80 ký tự.
- NULL/empty strings nếu legacy paths có.
- Hai reference chỉ khác case.
- Reference có dấu tiếng Việt/Unicode.
- Timestamps trước/sau nửa đêm UTC, fractional seconds.
- Enum values mới/cũ.
- Duplicates cần UNIQUE constraint.
- FK references hợp lệ/không hợp lệ.
- Records cùng sort key để kiểm tie-breaker.
- Nhiều transactions ghi cùng row.
- Bảng lớn nếu performance cần kiểm.

### 45.1. Không chỉ dùng happy path

Các ranh giới/giá trị sai giúp bộc lộ khác biệt engine hơn một bản ghi thông thường.

### 45.2. Không đưa PII thật vào CI

Dữ liệu đại diện có thể được tạo/synthetic hoặc anonymized theo policy. Không copy production database chứa thông tin nhạy cảm vào developer laptop/test logs.

---

## 46. Test lifecycle và cleanup

### 46.1. H2 in-memory

Database có thể biến mất khi connections đóng hoặc process dừng tùy cấu hình. Các đặc tính như `DB_CLOSE_DELAY` ảnh hưởng việc dữ liệu sống qua nhiều connections. Một suite vô tình dùng chung DB name có thể gây test contamination.

### 46.2. PostgreSQLContainer

Static container thường được share giữa test methods trong class; container có lifecycle theo JUnit/Testcontainers annotations. Spring test transaction rollback có thể giữ test data cô lập, nhưng committed fixtures/independent transactions cần cleanup rõ.

### 46.3. Chạy tests song song

Nếu nhiều classes dùng cùng container/schema và cùng business keys, có race. Phân isolation theo database/schema/test names hoặc transaction reset strategy; không assume rollback giải quyết mọi cross-transaction writes.

### 46.4. Avoid destructive test outside disposable DB

`ddl-auto=create-drop`, `TRUNCATE` và negative constraints phải chạy trên database được tạo riêng cho test. Có guardrails về credentials/environment.

---

## 47. Kiểm thử transaction rollback thực tế

Một test đơn giản chỉ ghi entity và nhìn trạng thái trước khi commit không chứng minh rollback.

Kịch bản:

```text
Tx A:
  insert PaymentRecord
  attempt second operation -> fails
  rollback

Tx B:
  query by external_ref
  should return no committed payment from Tx A
```

### 47.1. Spring @DataJpaTest mặc định rollback

Điều này có lợi nhưng cũng khiến một số scenarios không thực sự commit. Để kiểm visibility/rollback across transactions, dùng explicit transactions hoặc `TransactionTemplate`, `TestTransaction` theo setup.

### 47.2. Sau SQL failure, không dùng cùng transaction

Đặc biệt PostgreSQL transaction error state cần rollback. Kiểm result cuối ở context mới.

### 47.3. DB isolation khác test local sequential

Để đánh giá target semantics cần chạy concurrent transactions có kiểm soát, không chỉ gọi hai methods nối tiếp trong cùng thread/context.

---

## 48. Kiểm thử migration từ legacy schema

Giả sử V1 của PaymentRecord chưa có `source`. Release mới thêm `source NOT NULL`.

### 48.1. Fresh install

Tạo database trống và áp tất cả migrations. Pass không nói gì về dữ liệu V1 cũ.

### 48.2. Upgrade

1. Áp V1.
2. Insert legacy payments với amount/status/timestamps đại diện.
3. Áp V2 thêm cột `source` nullable/default theo chiến lược.
4. Backfill legacy rows.
5. Verify no NULLs và business values đúng.
6. Áp V3 constraint.
7. Boot Hibernate mappings mới với validate.
8. Read/update legacy rows.
9. Kiểm schema history/checksums.

### 48.3. H2 không thay migration engine mục tiêu

Nếu SQL V2/V3 chứa PostgreSQL `ALTER TABLE` hoặc index operations, run upgrade trên PostgreSQL container. Nếu target là MySQL, dùng MySQL engine/version tương ứng.

---

## 49. Kiểm thử lỗi runtime trên target driver

Các lỗi có thể khác:

- SQLState codes.
- Constraint violation cause/constraint name.
- Query timeout behavior.
- Lock timeout/deadlock exceptions.
- Connection interruption.
- Generated key retrieval.
- Batch statement error reporting.

### 49.1. Tránh viết error mapping chỉ dựa H2

Nếu ứng dụng ánh xạ PostgreSQL unique violation sang HTTP 409, unit test mapping exception có thể hữu ích; integration test trên PostgreSQL chứng minh actual driver exception được chuyển đúng.

### 49.2. Không ép mọi provider exception giống nhau

Spring `DataIntegrityViolationException` có thể wrap driver exceptions; JPA `PersistenceException` và Hibernate exceptions cũng khác. Test theo contract và root cause phù hợp, không khẳng định stack trace portable.

---

## 50. Kiểm thử dữ liệu và performance khác nhau

Functional test trả lời “kết quả có đúng không?”. Performance test trả lời “có đủ nhanh/tốn ít resources trên workload mục tiêu không?”.

### 50.1. Embedded test phù hợp functional basics

Một H2 test 100 rows có thể chứng minh JPQL filter trả đúng Orders.

### 50.2. Target DB performance cần khác

- Dữ liệu đại diện.
- Indexes thực tế.
- Statistics đã cập nhật.
- SQL plans.
- Query timings.
- Network overhead.
- Concurrent queries.
- Connection pool.
- N+1/row multiplication.
- Cache warm/cold.

### 50.3. Không assert latency tuyệt đối bằng unit test

Một test “query < 50ms” có thể flaky trên CI. Dùng profiling/performance regression suites có methodology, p95/p99 thresholds và môi trường đủ kiểm soát.

---

## 51. Bài thực hành A — H2 smoke test

1. Cấu hình H2 in-memory trong test profile.
2. Cho Hibernate tạo schema disposable.
3. Tạo PaymentRecord hợp lệ.
4. Persist, flush, clear, find.
5. Assert status/amount/ID.
6. Chạy JPQL filter.
7. Ghi database product/driver name.
8. Liệt kê những gì bài test chưa chứng minh cho PostgreSQL.

---

## 52. Bài thực hành B — Compatibility mode

1. Chạy H2 ở default mode.
2. Chạy H2 `MODE=PostgreSQL`.
3. Thử một số SQL syntax differences.
4. Quan sát identifier case/column names.
5. Thử JSON/cast/function usage nếu test environment hỗ trợ.
6. Đánh dấu những feature không được mô phỏng.
7. Chạy cùng native query trên PostgreSQL.
8. So sánh semantics, không chỉ syntax.
9. Kết luận mode có giá trị và giới hạn gì.

---

## 53. Bài thực hành C — PostgreSQL Testcontainers

1. Thêm Testcontainers PostgreSQL/JUnit.
2. Khởi động `PostgreSQLContainer` cùng version family production.
3. Gắn datasource qua `@DynamicPropertySource`.
4. Tắt test datasource auto-replacement.
5. Chạy Flyway migrations.
6. Bật `ddl-auto=validate`.
7. Persist/flush/clear/find.
8. Assert DB product name là PostgreSQL.
9. Ghi JDBC driver/DB version.
10. So sánh với H2 test.

---

## 54. Bài thực hành D — NUMERIC precision/scale

1. Mapping amount BigDecimal NUMERIC(19,2).
2. Test amount 12.50.
3. Test amount có 17 chữ số phần nguyên và 2 decimal digits.
4. Test amount vượt precision.
5. Test amount với 3 decimal digits.
6. So sánh Java BigDecimal.equals vs compareTo.
7. Chạy trên H2 và PostgreSQL.
8. Ghi nơi làm tròn, từ chối hoặc báo lỗi.
9. Thống nhất business policy và DB constraint.

---

## 55. Bài thực hành E — Timezone

1. Mapping `Instant createdAt`.
2. Seed timestamp có fractional seconds.
3. Test với JVM timezone UTC.
4. Thử timezone Asia/Ho_Chi_Minh.
5. Persist/flush/clear/find.
6. So sánh Instant đúng tới precision mong đợi.
7. Đọc SQL column/DB session timezone.
8. So sánh H2 và PostgreSQL.
9. Ghi cách kiểm offset/normalization.
10. Không bỏ qua daylight-saving corner cases khi sản phẩm liên quan.

---

## 56. Bài thực hành F — Collation và UNIQUE

1. Tạo UNIQUE external_ref trên PostgreSQL.
2. Insert `Pay-ABC`.
3. Insert `pay-abc`.
4. Ghi behavior theo collation hiện tại.
5. Thiết kế case-insensitive uniqueness nếu nghiệp vụ cần.
6. Thử Unicode/accent variants.
7. Chạy tests trên H2/MySQL nếu có.
8. So sánh khác biệt.
9. Kiểm root cause khi unique violation.
10. Không suy Java casefold bằng SQL collation.

---

## 57. Bài thực hành G — Enum và native types

1. Persist enum `PaymentStatus.NEW` qua STRING mapping.
2. Đọc raw SQL representation.
3. Thử giá trị legacy không còn trong enum Java.
4. Ghi behavior đọc.
5. Thiết kế data migration/transitional code.
6. Thử CHECK constraint chỉ cho allowed values.
7. Nếu dùng PostgreSQL native enum, test dialect/migration khác.
8. Không chỉ test H2 create-drop.

---

## 58. Bài thực hành H — Concurrency và locking

1. Seed/commit PaymentRecord.
2. Mở hai EntityManagers.
3. Load cùng version.
4. Transaction A update và commit.
5. B update stale entity.
6. Assert optimistic conflict.
7. Test PESSIMISTIC_WRITE nếu ứng dụng cần.
8. Đo lock timeout/deadlock theo DBMS.
9. So sánh H2 và PostgreSQL.
10. Kiểm final committed state.

---

## 59. Bài thực hành I — Native SQL upsert

1. Viết PostgreSQL `ON CONFLICT`.
2. Test insert mới.
3. Test update khi conflict.
4. Test transaction rollback.
5. Thử concurrent upserts nếu rủi ro cao.
6. Chạy trên PostgreSQL container.
7. Thử H2 compatibility mode để thấy giới hạn.
8. Không làm mất SQL production đúng chỉ để qua H2.
9. Xác định API/repository boundary cho native query.

---

## 60. Bài thực hành J — Migration gap

1. Tạo H2 mapping test với create-drop.
2. Thêm JPA field `source`.
3. Quan sát test H2 vẫn xanh.
4. Tạo PostgreSQL migration suite với validate.
5. Cố tình không có migration thêm source.
6. Quan sát suite fail.
7. Bổ sung Flyway migration.
8. Test fresh install.
9. Test upgrade từ V1 có dữ liệu cũ.
10. Ghi nguyên nhân false positive.

---

## 61. Bài thực hành K — Query plans

1. Tạo nhiều PaymentRecords trên PostgreSQL.
2. Tạo index phù hợp status/created_at.
3. Chạy EXPLAIN/EXPLAIN ANALYZE an toàn.
4. Ghi rows, scan, sort và buffers.
5. Thử query khi chưa có index trong database disposable.
6. So sánh query latency.
7. Chạy cùng logic trên H2.
8. Giải thích vì sao không suy Postgres plan từ H2.
9. Đo p95/p99 nếu có load test.

---

## 62. Bài thực hành L — Test matrix theo rủi ro

1. Liệt kê toàn bộ entity mappings.
2. Đánh dấu basic fields, relationships, converters.
3. Liệt kê native SQL/features vendor-specific.
4. Liệt kê constraints, data migrations, concurrency requirements.
5. Xếp rủi ro theo mức ảnh hưởng dữ liệu và khả năng lỗi.
6. Chọn unit tests không DB.
7. Chọn H2 fast tests.
8. Chọn PostgreSQL container tests.
9. Chọn upgrade/staging tests.
10. Đặt CI gates phù hợp.
11. Ghi known gaps và owner.

---

## 63. Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| H2 pass, PostgreSQL báo missing column | ORM create-drop che thiếu migration | Flyway + validate |
| JPQL pass trên H2, native SQL fail Postgres | Dialect/schema khác | Test native trên target |
| JSONB operator fail H2 | H2 không hỗ trợ hoàn toàn | PostgreSQL integration |
| Unique violation khác giữa DBs | Collation/case behavior | Thiết kế constraint rõ |
| BigDecimal scale khác | Numeric mapping/DB conversion | Boundary test trên target |
| Timestamp lệch giờ | Timezone/session/JDBC mismatch | Chuẩn hóa/test Instant |
| ID behavior khác | IDENTITY/SEQUENCE strategy | Test target ID generation |
| Optimistic conflict không xuất hiện | Test dùng cùng EM/tx hoặc version mapping sai | Hai contexts/transactions |
| Pessimistic lock test khác | Engine/isolation khác | Target concurrency suite |
| H2 không hiểu DDL PostgreSQL | Vendor-specific syntax | Không ép migration chạy H2 |
| Testcontainers chạy nhưng datasource vẫn H2 | @DataJpaTest replacement/config | NONE + metadata assert |
| Hibernate validate pass nhưng CHECK thiếu | Validate giới hạn phạm vi | DB negative tests |
| PostgreSQL negative test làm các SQL sau lỗi | Transaction aborted | Rollback/context mới |
| CI test flaky bởi parallel DB usage | Shared schema/business keys | Isolation/fixtures |
| H2 nhanh, production query chậm | Query plan/data volume/network khác | EXPLAIN + staging |
| Test database biến mất giữa contexts | H2 in-memory lifecycle | DB_CLOSE_DELAY/config |
| PostgreSQL container không start | Docker/image/env issue | CI/Testcontainers diagnostics |
| Flyway checksum mismatch | Sửa migration đã áp | New version/reconcile history |
| App startup fail sau deploy | Migration chưa chạy hoặc sai order | Deployment gate/validate |
| SQL error code mapping sai | JDBC driver/vendor exceptions khác | Target error-path tests |

---

## 64. Checklist trước khi tuyên bố “đã kiểm thử JPA”

| Câu hỏi | Cần trả lời rõ |
|---|---|
| Test dùng DBMS nào? | H2/PG/MySQL/... |
| DBMS/driver version? | Có ghi |
| Embedded hay in-memory? | Không đánh đồng |
| Schema được tạo bằng cách nào? | create-drop hay migration |
| Hibernate/JPA provider version? | Có ghi |
| SQL dialect thực tế? | Có ghi |
| Test DB có cùng engine target không? | Nếu claim target compatibility |
| Datasource có bị Spring thay? | Đã xác minh |
| Entity CRUD round-trip có flush/clear? | Có |
| Generated IDs có kiểm? | Có |
| Precision/scale biên đã kiểm? | Nếu liên quan |
| Timestamp/timezone đã kiểm? | Nếu liên quan |
| UUID/JSON/array/native types? | Target DB test |
| Collation/Unicode/case handling? | Target DB test |
| Nullable/UNIQUE/CHECK/FK? | Negative tests |
| Migrations fresh-install? | Có |
| Migrations upgrade từ legacy data? | Nếu production có data |
| ORM không auto-fix schema trong migration suite? | Có |
| Two-transaction locking/conflict tests? | Nếu concurrency quan trọng |
| SQL query plans/performance đã đo? | Nếu có SLA |
| Test data phân bố đại diện? | Có |
| CI environment reproducible? | Version pin |
| Test isolation/cleanup? | Có |
| Không dùng production DB cho destructive tests? | Có |
| Limitations/known gaps được ghi? | Có |

---

## 65. Các ngộ nhận cần tránh

### 65.1. “In-memory và embedded là một”

Không. Một DB nhúng có thể file-backed; một server DBMS cũng có caches/memory components. Đặc điểm triển khai và lưu trữ là hai trục khác nhau.

### 65.2. “H2 MODE=PostgreSQL tức là đang kiểm PostgreSQL”

Không. Chế độ tương thích cú pháp không cung cấp engine, JDBC driver, isolation, index và extension semantics của PostgreSQL.

### 65.3. “Nếu JPQL portable thì kết quả luôn giống nhau trên mọi DB”

Không tuyệt đối. Database data types, collation, NULL ordering, functions, constraints và transaction semantics vẫn có thể khác.

### 65.4. “Mapping create-drop pass nghĩa migration đúng”

Không. ORM có thể tự tạo column mà Flyway migration production chưa có.

### 65.5. “Hibernate validate kiểm mọi constraint/index”

Không. Cần DB-specific constraints/index assertions.

### 65.6. “Một integration test trên H2 chứng minh concurrency”

Không. Transaction isolation và locking của H2 không đại diện tất cả DBMS.

### 65.7. “Testcontainers quá chậm nên không cần”

Không nhất thiết. Có thể giữ các unit/H2 tests nhanh, còn target tests có chọn lọc trong CI.

### 65.8. “Đã dùng PostgreSQLContainer nên chắc chắn test kết nối PostgreSQL”

Không nếu datasource bị auto-replacement/misconfiguration. Kiểm runtime metadata.

### 65.9. “Native SQL nên đổi thành H2-compatible để tests pass”

Không khi feature đúng là vendor-specific. Test SQL trên engine được thiết kế chạy.

### 65.10. “Cứ tạo 10 rows thì đủ kiểm query performance”

Không. Cardinality/plan/locking có thể thay đổi mạnh theo dữ liệu.

### 65.11. “Rollback mặc định của @DataJpaTest chứng minh actual commit behavior”

Không. Một số lỗi chỉ xuất hiện tại commit hoặc transaction khác.

### 65.12. “BigDecimal chạy ở Java nên SQL precision không quan trọng”

Không. NUMERIC precision/scale và JDBC mapping cần kiểm ở DB target.

### 65.13. “String unique trên H2 sẽ giống MySQL collations”

Không. Collation/case sensitivity có thể khác.

### 65.14. “Timestamp UTC ở Java bảo đảm không lệch tại DB”

Không. Column type, driver/session timezone và precision quan trọng.

### 65.15. “Có một DB target container là đã mô phỏng production hoàn toàn”

Không. Replicas, TLS, load, stats, data distribution, failover và network topology có thể khác.

### 65.16. “Một H2 failure có nghĩa code production sai”

Không nhất thiết. H2 có thể không hiểu SQL/dialect feature target hỗ trợ.

---

## 66. Câu hỏi ôn tập

1. Embedded database khác in-memory database ở đâu?
2. H2 file mode có trở thành PostgreSQL không?
3. PostgreSQLContainer có thật sự chạy DB engine PostgreSQL không?
4. Vì sao không dùng một loại DB cho tất cả tests?
5. Domain unit test cần database trong trường hợp nào?
6. JPA smoke test trên H2 chứng minh được gì?
7. H2 test chưa chứng minh được điều gì cho production?
8. H2 compatibility mode có giới hạn gì?
9. Vì sao provider sinh SQL khác theo dialect?
10. IDENTITY khác SEQUENCE ở điểm nào?
11. Generated ID có nên assert bằng 1 không?
12. NUMERIC(19,2) có bao nhiêu chữ số phần nguyên tối đa?
13. BigDecimal.equals khác compareTo thế nào?
14. Timestamp with time zone khác timestamp without time zone về mục đích?
15. Vì sao cần test timezone và precision trên target DB?
16. Java EnumType.STRING có tự tạo CHECK constraint hoàn chỉnh không?
17. Rename enum value cần migration data khi nào?
18. Vì sao H2 không đủ kiểm PostgreSQL JSONB?
19. UUID/native arrays cần test mapping nào?
20. Tên bảng/cột có thể khác nhau theo DBMS vì sao?
21. Collation ảnh hưởng UNIQUE thế nào?
22. Vì sao 'Alice' và 'alice' có thể khác kết quả ở H2 và MySQL?
23. NULL ordering có mặc định giống nhau trên mọi DB không?
24. SQL empty string có luôn tương đương NULL không?
25. Boolean column mappings có portable ở native SQL không?
26. Vì sao CHECK constraints cần negative DB test?
27. Một Java constructor từ chối amount âm có chứng minh DB CHECK không?
28. READ COMMITTED trên hai DBMS có nhất thiết hành xử như nhau không?
29. Vì sao concurrency test cần hai EntityManagers?
30. Pessimistic locking cần test trên engine nào?
31. PostgreSQL CREATE INDEX CONCURRENTLY có transaction restriction gì?
32. MySQL DDL rollback giống PostgreSQL không?
33. Native UPSERT PostgreSQL nên test ở đâu?
34. Vì sao query plan H2 không đoán được PostgreSQL plan?
35. @DataJpaTest có thể thay datasource khi nào?
36. Cách ngăn datasource replacement?
37. Cách chứng minh runtime database product là PostgreSQL?
38. Vì sao migrate + validate tốt hơn create-drop khi kiểm production schema?
39. Fresh install và upgrade-path test khác nhau thế nào?
40. Vì sao một H2 test có thể false positive?
41. Vì sao một H2 test có thể false negative?
42. Khi nào một PostgreSQL container vẫn chưa đủ?
43. Phải ghi những version/config nào vào test report?
44. Negative constraint test cần cleanup transaction thế nào?
45. Vì sao không dùng production DB cho test schema/constraints?
46. Làm sao giữ test suite nhanh nhưng vẫn kiểm dialect-specific behavior?
47. Kiểm thử connection pool/failover thuộc lớp nào?
48. SQL EXPLAIN ANALYZE cần lưu ý điều gì?
49. Bảng risk-based test matrix có ích gì?
50. Hãy thiết kế ba bộ test cho PaymentRecord: thuần Java, H2 mapping smoke và PostgreSQL migrations/concurrency, với danh sách assertions và known gaps.

---

## 67. Tổng kết

| Cần kiểm | Nguồn bằng chứng hợp lý |
|---|---|
| Domain logic/BigDecimal arithmetic | Unit Java, không DB |
| Basic JPA bootstrap/repository CRUD | Embedded DB nhanh |
| Provider mapping gần deployment | Target DB container |
| PostgreSQL/MySQL/Oracle-specific SQL | Đúng DBMS mục tiêu |
| NUMERIC/timezone/UUID/JSON behavior | Target driver + DB |
| UNIQUE/FK/CHECK/collation | Negative DB integration |
| Concurrency/locks/isolation | Multi-transaction target DB |
| Production schema compatibility | Migrations + Hibernate validate |
| Old-data upgrades | Upgrade-path integration |
| Query plan/index performance | Target DB với dữ liệu đủ đại diện |
| Failover/replication/topology | Staging/specialized environment |

### Sơ đồ quyết định cuối bài

```text
             CẦN KIỂM THỬ JPA / DATABASE
                            |
                            v
                Chỉ kiểm Java domain rule?
                     /               \
                   CÓ                KHÔNG
                    |                   |
                    v                   v
              UNIT TEST          Có phụ thuộc SQL/
              KHÔNG DB          provider/relationship?
                                  /         \
                                KHÔNG       CÓ
                                  |          |
                                  v          v
                             Fake/mock    BASIC CRUD?
                             khi phù hợp    /       \
                                          CÓ       KHÔNG
                                           |         |
                                           v         v
                                       H2 smoke   TARGET DB
                                           |      integration
                                           |         |
                                           v         v
                                 Có migration/native SQL,
                                   locks/types/collation?
                                           |
                                          CÓ
                                           |
                                           v
                                     PostgreSQL/
                                     MySQL/... thật
                                     trong container
                                           |
                                           v
                                 Có production-scale,
                                failover/online DDL?
                                    /           \
                                  CÓ            KHÔNG
                                   |              |
                                   v              v
                                Staging        CI đủ
                                rehearsal     theo risk
                                           |
                                           v
                                   Ghi known gaps,
                                engine/version/config
```

**Nguyên tắc cuối bài:** DB nhúng như H2 giúp kiểm tra nhanh mapping và repository behavior trong nhiều tình huống, nhưng kết quả không được gán cho một DBMS khác mà chưa có bằng chứng. Khác biệt giữa embedded và target database có thể nằm ở **SQL dialect, data types, precision, timezone, collation, constraints, generated IDs, transaction isolation, locking, DDL và optimizer**. Thiết kế kiểm thử JPA tốt không chọn một database duy nhất cho mọi câu hỏi: dùng **unit tests không DB** cho domain rules, **embedded smoke tests** cho phản hồi nhanh, **Testcontainers với DBMS mục tiêu** cho mapping/SQL/migrations/concurrency và **staging/rehearsal** cho rủi ro quy mô lớn. Trước khi nói “test đã pass”, luôn hỏi thêm: **pass trên engine nào, schema được tạo bằng gì, phiên bản/cấu hình nào, và những điều gì vẫn chưa được chứng minh?**

