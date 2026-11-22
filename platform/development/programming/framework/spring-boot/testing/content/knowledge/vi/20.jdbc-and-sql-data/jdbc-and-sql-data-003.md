# @JooqTest và cấu hình DSLContext trong Spring Boot Testing

## 1. Bài học này giải quyết vấn đề gì?

Khi ứng dụng dùng **jOOQ** để truy vấn SQL bằng Java DSL, một bài unit test chỉ mock `DSLContext` thường không phát hiện được lỗi SQL dialect, tên cột, kiểu dữ liệu, ràng buộc database hoặc cấu hình transaction. Ngược lại, khởi động toàn bộ ứng dụng bằng `@SpringBootTest` cho mọi truy vấn nhỏ có thể làm test chậm và phụ thuộc các bean không liên quan.

Spring Boot cung cấp **`@JooqTest`**, một *test slice* tập trung vào hạ tầng truy cập dữ liệu qua jOOQ. Nó cấu hình `DSLContext`, DataSource và những thành phần cần thiết cho jOOQ, nhưng **không tự scan mọi `@Component`/`@Repository` hoặc `@ConfigurationProperties` của ứng dụng**. Nó dùng DataSource đã được cấu hình theo mặc định; nếu muốn thay bằng embedded database, cần chọn rõ `@AutoConfigureTestDatabase`. Các test `@JooqTest` mặc định chạy trong Spring-managed transaction và rollback khi method kết thúc.

Bài tập trung đúng vào đề mục **“@JooqTest và cấu hình DSLContext”**, thuộc nhóm **JDBC và dữ liệu SQL**. Bạn sẽ học:

- Phân biệt `@JooqTest`, `@JdbcTest`, `@DataJpaTest` và `@SpringBootTest`.
- Hiểu `DSLContext` chứa những cấu hình gì: `DataSource`/`ConnectionProvider`, `SQLDialect`, `Settings`, transaction provider, listener providers.
- Dùng `@AutoConfigureTestDatabase` để chọn H2, giữ database thật khi cần, và tránh vô tình ghi vào production.
- Cấu hình `spring.jooq.sql-dialect`, `DefaultConfigurationCustomizer` và import collaborator cần kiểm thử.
- Viết Java 17+ với Spring Boot 3.3.5, jOOQ DSL (không cần code generator) và một test suite H2 có SQL schema thật.
- Test truy vấn SELECT/INSERT/UPDATE/DELETE, bind parameters, mapping, result order, lỗi unique/CHECK constraint và transaction rollback.
- Biết khi nào H2 chưa đủ, cần database migration và Testcontainers theo đúng dialect thực tế.

**Phiên bản ví dụ:** Java 17+, Spring Boot **3.3.5**, jOOQ 3.19.x do Spring Boot BOM quản lý, H2. Đây là stack được cố định cho tính tái hiện, không phải khẳng định phiên bản mới nhất; import của Spring Boot 4 và jOOQ version mới có thể khác.

## 2. jOOQ là gì và DSLContext đóng vai trò nào?

jOOQ (*Java Object Oriented Querying*) giúp biểu diễn SQL bằng Java fluent API. Thay vì nối chuỗi SQL:

```java
String sql = "select * from books where isbn = '" + input + "'";
```

có nguy cơ SQL injection, jOOQ cho phép xây query với typed `Field<T>` và **bind values**:

```java
dsl.select(ISBN, TITLE)
   .from(BOOKS)
   .where(ISBN.eq(input))
   .fetch();
```

Đoạn này là **snippet**; `DSLContext dsl`, `Field<String> ISBN/TITLE` và `Table<?> BOOKS` được định nghĩa đầy đủ trong project ở phần sau.

`DSLContext` là điểm bắt đầu để xây dựng, render và thực thi SQL. Nó giữ tham chiếu đến `org.jooq.Configuration`, trong đó có:

| Thành phần | Ý nghĩa | Điều nên test |
| --- | --- | --- |
| `SQLDialect` | Quy tắc cú pháp và khả năng hỗ trợ SQL của DB | H2 trong test, PostgreSQL trong production thì không giả định giống nhau |
| `ConnectionProvider` | Cách jOOQ lấy và trả JDBC connections | Kết nối tới DataSource test, không phải production |
| `TransactionProvider` | Phối hợp transaction qua jOOQ/Spring | DML của test tham gia transaction đúng |
| `Settings` | Render SQL, tên identifier, bind values và nhiều cấu hình khác | Customizer có được áp dụng không |
| `ExecuteListenerProvider` | Quan sát lifecycle thực thi query | Instrumentation/logging khi thật sự cần |
| `RecordMapperProvider` | Quy tắc chuyển Record thành Java object | Mapping custom có hoạt động không |

Khi Spring Boot tạo bean `DSLContext`, nó lấy `DataSource` từ Spring context, thiết lập provider và quyết định dialect. Vì vậy test cần **inject bean này**, không tùy tiện thay bằng `DSL.using("...")` tự tạo nếu mục tiêu là kiểm tra cấu hình Spring.

### Mô hình chạy test

```text
JUnit Jupiter
     |
     v
@JooqTest (Spring TestContext, transaction, jOOQ slice)
     |
     +---- DataSource (H2, được chọn minh bạch)
     |
     +---- jOOQ Configuration
     |       SQLDialect.H2
     |       Settings từ DefaultConfigurationCustomizer
     |       Spring-aware connection / transaction
     |
     +---- DSLContext bean
     |       |
     |       +---- BookQueries (được @Import rõ)
     |
     +---- schema SQL bằng @Sql BEFORE_TEST_CLASS
     |
     v
SELECT / INSERT / UPDATE / DELETE
     |
     v
H2 database (test method rollback)
```

jOOQ **không phải ORM giống JPA/Hibernate**. Một lời gọi `insertInto(...).execute()` thực thi câu SQL rõ ràng, không đợi JPA dirty checking/flush. Trả về jOOQ `Record` cũng khác managed entity với persistence context của JPA.

## 3. @JooqTest so với các test slices khác

| Annotation | Trọng tâm | Bean thường có sẵn | Khi dùng |
| --- | --- | --- | --- |
| `@JooqTest` | jOOQ + SQL/DataSource | `DSLContext`, JDBC infrastructure, transaction | Test SQL DSL, jOOQ repository/DAO |
| `@JdbcTest` | JDBC thuần | `JdbcTemplate`, DataSource, transaction | Test SQL qua JDBC/JdbcTemplate |
| `@DataJpaTest` | ORM/JPA | EntityManager, JPA repositories, TestEntityManager | Test entity mapping, JPQL, JPA repositories |
| `@SpringBootTest` | Nhiều thành phần ứng dụng | Full application context tùy cấu hình | Integration/service use case qua nhiều layers |
| JUnit thuần + mock | Logic Java không có DB | Không có DB thật | Test validation, branching, orchestration |

`@JooqTest` **không tự dựng REST controller, web server hoặc mọi service bean**. Nó cũng không cung cấp `MockMvc` để test HTTP. Nếu cần kiểm chứng API toàn tuyến, dùng một integration test rộng hơn và chỉ giữ số lượng cần thiết.

Spring Boot 3.3 khẳng định `@JooqTest` sử dụng DataSource hiện có theo mặc định (khác kỳ vọng phổ biến từ một số test slices) và rollback test transaction. Vì vậy, **không được chủ quan cho rằng database luôn là in-memory** chỉ vì nhìn thấy `@JooqTest`.

### Khi nào cần @Import?

Giả sử:

```java
@Repository
public class BookQueries {
    public BookQueries(DSLContext dsl) { ... }
}
```

Đây chỉ là snippet chữ ký. Trong production, `@Repository` được component scan. Nhưng `@JooqTest` giới hạn việc scan; nếu cần test `BookQueries`, hãy import rõ:

```java
@JooqTest
@Import(BookQueries.class)
class BookQueriesJooqTest { ... }
```

Cấu hình thực hành sẽ import cả `BookQueries` và `JooqConfig`. Việc import một bean cụ thể **không biến test thành full application test**. Nếu bean đó cần nhiều collaborator khác, chủ động quyết định import hay mock dependency để giữ phạm vi test.

## 4. Cấu hình DataSource: khác biệt quyết định độ an toàn

### 4.1. Mặc định JooqTest dùng database đã cấu hình

Nếu project có:

```properties
spring.datasource.url=jdbc:postgresql://db.internal:5432/store
```

thì chỉ dùng `@JooqTest` **không đủ** để khẳng định test đã đổi sang H2. Với database đã có cấu hình, tài liệu Boot hướng dẫn dùng `@AutoConfigureTestDatabase` khi muốn thay nó bằng embedded database.

### 4.2. Cố ý dùng H2 trong demo

```java
@JooqTest(properties = "spring.jooq.sql-dialect=H2")
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.ANY)
class BookQueriesJooqTest { ... }
```

Ở project mẫu có `com.h2database:h2` trong test runtime classpath. `Replace.ANY` diễn tả việc thay DataSource cho test bằng embedded database khi auto-configuration phù hợp. Trong Boot 3.3, `AutoConfigureTestDatabase` ở package `org.springframework.boot.test.autoconfigure.jdbc`.

**Lưu ý:** việc ép dialect H2 chỉ đúng vì thực tế dùng H2. Property `spring.jooq.sql-dialect=H2` **không biến PostgreSQL thành H2**, cũng không tự thay JDBC URL. Sai dialect có thể gây SQL fail hoặc tạo cú pháp sai.

### 4.3. Giữ database đúng hệ quản trị

Khi cần test PostgreSQL/MySQL thật hoặc Testcontainers:

```java
@JooqTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgreSqlJooqTest { ... }
```

Đây là snippet chiến lược, chưa có cấu hình Testcontainers/DataSource nên không phải test độc lập. `Replace.NONE` giữ DataSource được cung cấp, ví dụ qua `@DynamicPropertySource` hoặc `@ServiceConnection`. Lúc ấy cần đảm bảo migrations/schema và lifecycle container được cấu hình chính xác. Không bật `Replace.NONE` rồi trỏ vào production database.

### 4.4. Quy tắc thực tế

- CRUD SQL đơn giản, logic mapping, bind variables: H2 thường đủ nhanh.
- PostgreSQL `ON CONFLICT`, JSONB, arrays, advisory locks, CTE/locking đặc thù: test với PostgreSQL.
- MySQL collation/`ON DUPLICATE KEY`, transaction isolation, auto-increment: test với MySQL tương ứng.
- Schema migration: chạy đúng Flyway/Liquibase scripts trong môi trường test nếu hệ thống sử dụng chúng.
- Không dùng H2 `MODE=PostgreSQL` như bằng chứng mọi PostgreSQL semantics sẽ giống nhau.

## 5. Cấu hình DSLContext và SQLDialect

Spring Boot auto-configures `DSLContext` khi có jOOQ và DataSource. Một bean có thể được inject:

```java
@Autowired
DSLContext dsl;
```

`DSLContext.configuration().dialect()` trả dialect mà jOOQ đang dùng, ví dụ `SQLDialect.H2` trong demo. Dialect ảnh hưởng render SQL, pagination, return generated values, upsert, boolean expressions và mức tương thích với database.

### 5.1. Tự phát hiện dialect hay ép property?

Thông thường Boot dò SQL dialect dựa trên DataSource; nếu không nhận ra thì có thể dùng `DEFAULT`. Có thể override:

```properties
spring.jooq.sql-dialect=H2
```

Khi dùng H2 test thì property minh bạch. Với PostgreSQL ở production, phải để Boot detect đúng hoặc chỉ định `POSTGRES` nếu edition jOOQ và version đang dùng hỗ trợ. Edition open-source jOOQ chỉ hỗ trợ tập dialect phù hợp; không giả định mọi dialect thương mại có sẵn.

### 5.2. DefaultConfigurationCustomizer

Trong Boot 3.3, có thể tạo Spring bean `DefaultConfigurationCustomizer`. Boot gọi callback trước khi xây dựng jOOQ `Configuration` bean. Đây là cách thêm `Settings`/listeners mà không thay toàn bộ DSLContext:

```java
@Bean
DefaultConfigurationCustomizer customizer() {
    return configuration ->
        configuration.settings().setRenderFormatted(true);
}
```

Đây là snippet đặt bên trong `@Configuration`; file đầy đủ có ở phần project. `renderFormatted` ảnh hưởng **cách render SQL cho việc đọc/log/debug**, không làm SQL trở nên an toàn hơn hoặc thay thế bind variables.

### 5.3. Không tự tạo một DSLContext khác khi không cần

Nếu bạn gọi:

```java
DSLContext another = DSL.using(SQLDialect.H2);
```

một mình, context đó có dialect nhưng **không có DataSource/ConnectionProvider cần thiết để thực thi query**. Nó vẫn có ích để render SQL thuần, nhưng không tương đương bean Boot đã kết nối tới H2. Khi test SQL integration, inject `DSLContext` được Spring cung cấp.

Tạo `org.jooq.Configuration` hoặc `DSLContext` bean thủ công có thể ghi đè auto-configuration; chỉ làm vậy khi cần ownership đầy đủ đối với connection, dialect, transaction provider hoặc listeners. Test phải xác minh bean thực được sử dụng sau customization.

## 6. Cấu trúc project mẫu

Bài thực hành dùng Spring Boot 3.3.5, Java 17 và H2; bảng SQL được tạo bằng một script thuộc **test resources**. Không cần sinh source từ schema bằng jOOQ code generator, nhờ vậy bạn có thể học `@JooqTest` ngay. Trong sản phẩm, jOOQ **code generation** rất đáng dùng vì tạo typed Tables/Fields theo schema thật; phần 17 giải thích thêm.

```text
jooq-slice-example/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/jooq/
│   ├── JooqLearningApplication.java
│   ├── BookSql.java
│   ├── BookRow.java
│   ├── BookQueries.java
│   └── JooqConfig.java
├── src/test/java/com/example/jooq/
│   └── BookQueriesJooqTest.java
└── src/test/resources/
    └── jooq-schema.sql
```

### 6.1. settings.gradle

```groovy
rootProject.name = 'jooq-slice-example'
```

### 6.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jooq'

    testRuntimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

`spring-boot-starter-jooq` mang theo jOOQ, Spring JDBC/transaction và auto-configuration cần thiết. `spring-boot-starter-test` mang JUnit Jupiter và Spring Boot Test. `h2` chỉ có ở test runtime của ví dụ, bảo đảm các test có embedded database mà không cần khởi động một DB ngoài.

**Để chạy `bootRun` ngoài test**, cần cấu hình DataSource/runtime DB riêng vì H2 ở đây chỉ là test runtime dependency. Bài này chủ đích tập trung vào `gradle test`, không thiết kế một production datasource.

### 6.3. Application root

Tạo `src/main/java/com/example/jooq/JooqLearningApplication.java`:

```java
package com.example.jooq;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JooqLearningApplication {

    public static void main(String[] args) {
        SpringApplication.run(JooqLearningApplication.class, args);
    }
}
```

Lớp này ở package cha của các component/test, giúp Spring tìm primary configuration. `@JooqTest` chỉ sử dụng những phần bean/config được slice cho phép, không vì có `@SpringBootApplication` mà auto-load mọi REST/service bean.

## 7. Bảng SQL tạo riêng cho test

Tạo `src/test/resources/jooq-schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS catalog_books (
    id BIGINT NOT NULL PRIMARY KEY,
    isbn VARCHAR(32) NOT NULL UNIQUE,
    title VARCHAR(160) NOT NULL,
    price_cents INTEGER NOT NULL
        CHECK (price_cents >= 0),
    active BOOLEAN NOT NULL
);
```

Ta cố ý dùng ID **do test cung cấp** để assert dễ hiểu và tránh phụ thuộc identity/sequence behavior. `price_cents` là số nguyên theo minor currency units, không dùng `double` cho tiền. Unique ISBN và CHECK price không âm giúp test lỗi database một cách có ý nghĩa.

Schema được nạp bằng Spring Test `@Sql` với `ExecutionPhase.BEFORE_TEST_CLASS` (hỗ trợ trong Spring Framework 6.1/Boot 3.3):

```java
@Sql(
    scripts = "/jooq-schema.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS)
```

Script chạy **trước các test methods**, không được chèn vào mỗi test transaction để tạo table lặp đi lặp lại. Ta đặt tên `jooq-schema.sql` thay vì `schema.sql` mặc định để tránh bị Spring Boot basic SQL initializer tự động chạy script trước khi `@Sql` thực thi. Nếu project dùng Flyway/Liquibase, nên để tool migrations chuẩn bị schema thay vì pha trộn nhiều cơ chế DDL.

**Quan trọng:** H2 DDL và transaction semantics khác PostgreSQL; không đặt CREATE/DROP TABLE trong từng test method rồi kỳ vọng DDL luôn rollback. Các test chỉ thay đổi **hàng dữ liệu** trong transaction, còn schema được chuẩn bị trước class.

## 8. Khai báo typed Table và Field không cần code generation

Tạo `src/main/java/com/example/jooq/BookSql.java`:

```java
package com.example.jooq;

import org.jooq.Field;
import org.jooq.Table;
import org.jooq.impl.DSL;
import org.jooq.impl.SQLDataType;

public final class BookSql {

    public static final Table<?> BOOKS =
            DSL.table(DSL.unquotedName("catalog_books"));

    public static final Field<Long> ID =
            DSL.field(DSL.unquotedName("id"), SQLDataType.BIGINT);

    public static final Field<String> ISBN =
            DSL.field(DSL.unquotedName("isbn"),
                    SQLDataType.VARCHAR(32));

    public static final Field<String> TITLE =
            DSL.field(DSL.unquotedName("title"),
                    SQLDataType.VARCHAR(160));

    public static final Field<Integer> PRICE_CENTS =
            DSL.field(DSL.unquotedName("price_cents"),
                    SQLDataType.INTEGER);

    public static final Field<Boolean> ACTIVE =
            DSL.field(DSL.unquotedName("active"),
                    SQLDataType.BOOLEAN);

    private BookSql() {
    }
}
```

**Vì sao dùng `DSL.unquotedName`?** H2 thường lưu identifiers tạo bằng DDL không quote theo quy tắc case folding. jOOQ mặc định có thể quote identifiers, biến `"catalog_books"` thành một tên phân biệt hoa/thường. Dùng `unquotedName` cho bảng và cột test giúp tên SQL phù hợp DDL `CREATE TABLE catalog_books`. Khi chuyển sang production với generated jOOQ types, nên dùng tên do code generator tạo thay vì gõ literal.

**Vì sao dùng typed Field?** `Field<Integer> PRICE_CENTS` hỗ trợ `eq(int)`, `add(int)`, binding đúng type. Nếu bạn chỉ dùng `DSL.field("price_cents")` kiểu không rõ, code có thể mất lợi ích type checking hoặc gặp lỗi cast/mapping.

**Giới hạn của cách thủ công:** nếu schema đổi tên field/kiểu, các constants không tự được tạo lại, nên lỗi có thể chỉ xuất hiện lúc chạy test. Production thường chạy jOOQ codegen từ schema/migrations để có bảng và trường Java được sinh ra tương thích.

## 9. DTO cho kết quả truy vấn

Tạo `src/main/java/com/example/jooq/BookRow.java`:

```java
package com.example.jooq;

public record BookRow(
        long id,
        String isbn,
        String title,
        int priceCents,
        boolean active
) {
}
```

Đây là **read/write data object** Java 17, không phải JPA `@Entity`. Nó không có persistence context/dirty checking. Khi `BookQueries` đọc SQL, nó tạo `BookRow` mới; sửa object record không tự phát UPDATE. Muốn đổi dữ liệu, phải chạy câu SQL UPDATE có chủ đích.

## 10. Lớp truy vấn thực sử dụng DSLContext từ Spring

Tạo `src/main/java/com/example/jooq/BookQueries.java`:

```java
package com.example.jooq;

import java.util.List;
import java.util.Optional;

import org.jooq.DSLContext;
import org.jooq.Record;
import org.springframework.stereotype.Repository;

import static com.example.jooq.BookSql.ACTIVE;
import static com.example.jooq.BookSql.BOOKS;
import static com.example.jooq.BookSql.ID;
import static com.example.jooq.BookSql.ISBN;
import static com.example.jooq.BookSql.PRICE_CENTS;
import static com.example.jooq.BookSql.TITLE;

@Repository
public class BookQueries {

    private final DSLContext dsl;

    public BookQueries(DSLContext dsl) {
        this.dsl = dsl;
    }

    public int insert(BookRow book) {
        return dsl.insertInto(
                        BOOKS, ID, ISBN, TITLE, PRICE_CENTS, ACTIVE)
                .values(
                        book.id(), book.isbn(), book.title(),
                        book.priceCents(), book.active())
                .execute();
    }

    public Optional<BookRow> findById(long id) {
        return dsl.select(
                        ID, ISBN, TITLE, PRICE_CENTS, ACTIVE)
                .from(BOOKS)
                .where(ID.eq(id))
                .fetchOptional(BookQueries::toBookRow);
    }

    public Optional<BookRow> findByIsbn(String isbn) {
        return dsl.select(
                        ID, ISBN, TITLE, PRICE_CENTS, ACTIVE)
                .from(BOOKS)
                .where(ISBN.eq(isbn))
                .fetchOptional(BookQueries::toBookRow);
    }

    public List<BookRow> findActiveByTitlePrefix(String prefix) {
        return dsl.select(
                        ID, ISBN, TITLE, PRICE_CENTS, ACTIVE)
                .from(BOOKS)
                .where(ACTIVE.isTrue())
                .and(TITLE.like(prefix + "%"))
                .orderBy(ID.asc())
                .fetch(BookQueries::toBookRow);
    }

    public int rename(long id, String newTitle) {
        return dsl.update(BOOKS)
                .set(TITLE, newTitle)
                .where(ID.eq(id))
                .execute();
    }

    public int addPriceCents(long id, int delta) {
        return dsl.update(BOOKS)
                .set(PRICE_CENTS, PRICE_CENTS.add(delta))
                .where(ID.eq(id))
                .execute();
    }

    public int deactivate(long id) {
        return dsl.update(BOOKS)
                .set(ACTIVE, false)
                .where(ID.eq(id))
                .execute();
    }

    public int deleteById(long id) {
        return dsl.deleteFrom(BOOKS)
                .where(ID.eq(id))
                .execute();
    }

    public int countActive() {
        return dsl.fetchCount(BOOKS, ACTIVE.isTrue());
    }

    private static BookRow toBookRow(Record record) {
        return new BookRow(
                record.get(ID),
                record.get(ISBN),
                record.get(TITLE),
                record.get(PRICE_CENTS),
                record.get(ACTIVE));
    }
}
```

### 10.1. Truy vấn có bind parameters

`ISBN.eq(isbn)` không nối trực tiếp input của người dùng vào SQL text. jOOQ tạo SQL có bind parameter `?` (khi dùng prepared statements/default settings) rồi gắn giá trị riêng. Điều này hạn chế SQL injection tại vị trí **value** của biểu thức và cho phép JDBC driver xử lý type.

**Tuy nhiên:** nếu bạn dùng `DSL.field(String)` chứa raw SQL do client đưa vào, `DSL.sql(String)` với nội dung untrusted, hoặc tự nối `ORDER BY` vào plain SQL, jOOQ không thể tự bảo đảm an toàn. Identifier động phải đến từ allowlist/table metadata đáng tin cậy, không lấy tự do từ client.

### 10.2. Vấn đề wildcard khi dùng LIKE

`TITLE.like(prefix + "%")` diễn giải `%` và `_` theo SQL LIKE syntax. Ví dụ demo chỉ truyền prefix tĩnh `Spring`. Trong API có input thật, nếu muốn **literal prefix**, phải escape wildcard characters theo dialect và chỉ rõ `ESCAPE` semantics, hoặc chọn một query khác. Bind parameter giải quyết SQL injection nhưng **không tự làm LIKE wildcard thành literal**.

### 10.3. Mapping jOOQ Record thành Java record

`Record.get(Field<T>)` trả đúng Java type theo Field declaration. `toBookRow` tạo DTO, không phải một managed entity. Nếu database column có thể null nhưng Java record dùng primitive `int/boolean`, unboxing null gây lỗi; ví dụ DDL đặt `NOT NULL` để các trường đó an toàn. Trong hệ thống thật hãy để schema/Java nullable contract khớp nhau.

### 10.4. Kiểm tra affected row count

`insert(...).execute()` thường trả số hàng bị tác động (1 cho insert đơn trong demo); `rename(...)`, `addPriceCents(...)`, `deactivate(...)` và `deleteById(...)` trả 1 nếu đúng một hàng được thay đổi, 0 nếu không match primary key. Một test nên assert số lượng hàng ảnh hưởng, **không chỉ** kiểm tra query không ném exception.

## 11. Cấu hình jOOQ customizer trong ứng dụng

Tạo `src/main/java/com/example/jooq/JooqConfig.java`:

```java
package com.example.jooq;

import org.springframework.boot.autoconfigure.jooq.DefaultConfigurationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class JooqConfig {

    @Bean
    DefaultConfigurationCustomizer jooqCustomizer() {
        return configuration ->
                configuration.settings()
                        .setRenderFormatted(true);
    }
}
```

`DefaultConfigurationCustomizer` của Spring Boot 3.3 được áp dụng khi auto-configure jOOQ. Test sẽ assert:

```java
assertEquals(Boolean.TRUE,
        dsl.configuration().settings().isRenderFormatted());
```

Đây là assertion trên **cấu hình của injected DSLContext**, không phải một object `Settings` mới tạo trong test. Dùng `Boolean.TRUE.equals(...)` hoặc `assertEquals(Boolean.TRUE, ...)` vì getter trả `Boolean`.

**Không lẫn lộn:**
- Cấu hình `spring.jooq.sql-dialect` chọn cách jOOQ render SQL cho DB.
- `DefaultConfigurationCustomizer` chỉnh `org.jooq.Configuration` (ví dụ Settings, listener providers).
- `@Import(JooqConfig.class)` ở test slice làm bean tùy biến có mặt.
- `@Import(BookQueries.class)` làm DAO/repository muốn test có mặt dù slice không scan regular components.

### Có nên chỉnh renderQuotedNames trong project thật?

jOOQ có `RenderQuotedNames` và `RenderNameCase` cho identifiers. Việc đặt `RenderQuotedNames.NEVER` có thể làm mất tính phân biệt hoa/thường hoặc khiến reserved word bị lỗi. Demo dùng `DSL.unquotedName` cho tên cụ thể và chỉ tùy biến **renderFormatted**, để không âm thầm thay quy tắc quoting toàn hệ thống.

## 12. Bộ test @JooqTest đầy đủ

Tạo `src/test/java/com/example/jooq/BookQueriesJooqTest.java`:

```java
package com.example.jooq;

import java.util.List;

import javax.sql.DataSource;

import org.jooq.DSLContext;
import org.jooq.SQLDialect;
import org.jooq.conf.ParamType;
import org.jooq.exception.DataAccessException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jooq.JooqTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static com.example.jooq.BookSql.BOOKS;
import static com.example.jooq.BookSql.ID;
import static com.example.jooq.BookSql.ISBN;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JooqTest(properties = "spring.jooq.sql-dialect=H2")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
@Import({BookQueries.class, JooqConfig.class})
@Sql(
        scripts = "/jooq-schema.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS)
class BookQueriesJooqTest {

    @Autowired
    DSLContext dsl;

    @Autowired
    DataSource dataSource;

    @Autowired
    BookQueries books;

    @BeforeEach
    void cleanRowsWithinTransaction() {
        dsl.deleteFrom(BOOKS).execute();
    }

    private static BookRow book(
            long id, String isbn, String title,
            int priceCents, boolean active) {
        return new BookRow(
                id, isbn, title, priceCents, active);
    }

    @Test
    void createsDslContextWithH2DialectAndCustomizer() {
        assertNotNull(dsl);
        assertNotNull(dataSource);
        assertEquals(SQLDialect.H2, dsl.configuration().dialect());
        assertEquals(Boolean.TRUE,
                dsl.configuration().settings().isRenderFormatted());
    }

    @Test
    void jooqTestRunsInsideSpringTransaction() {
        assertTrue(
                TransactionSynchronizationManager
                        .isActualTransactionActive());
    }

    @Test
    void insertsAndFindsByPrimaryKey() {
        BookRow input =
                book(101L, "ISBN-101", "Spring Basics", 2500, true);

        assertEquals(1, books.insert(input));

        BookRow loaded = books.findById(101L).orElseThrow();
        assertEquals(input, loaded);
    }

    @Test
    void findsByIsbnAndReturnsEmptyForMissing() {
        BookRow input =
                book(102L, "ISBN-102", "SQL Queries", 3100, true);
        books.insert(input);

        assertEquals(input,
                books.findByIsbn("ISBN-102").orElseThrow());

        assertTrue(books.findByIsbn("ISBN-NOT-FOUND").isEmpty());
        assertTrue(books.findById(999999L).isEmpty());
    }

    @Test
    void filtersActiveBooksAndSortsById() {
        BookRow a = book(
                202L, "ISBN-202", "Spring Data", 2900, true);
        BookRow b = book(
                201L, "ISBN-201", "Spring Testing", 3400, true);
        BookRow inactive = book(
                203L, "ISBN-203", "Spring Archive", 1000, false);
        BookRow other = book(
                204L, "ISBN-204", "Java Basics", 2000, true);

        books.insert(a);
        books.insert(b);
        books.insert(inactive);
        books.insert(other);

        List<BookRow> result =
                books.findActiveByTitlePrefix("Spring");

        assertEquals(List.of(b, a), result);
    }

    @Test
    void updatesTitleAndReportsAffectedRow() {
        books.insert(book(
                301L, "ISBN-301", "Before", 1000, true));

        assertEquals(1, books.rename(301L, "After"));
        assertEquals("After",
                books.findById(301L)
                        .orElseThrow().title());
    }

    @Test
    void addsPriceUsingTypedSqlExpression() {
        books.insert(book(
                302L, "ISBN-302", "Price", 5000, true));

        assertEquals(1, books.addPriceCents(302L, 250));
        assertEquals(5250,
                books.findById(302L)
                        .orElseThrow().priceCents());
    }

    @Test
    void updateOfMissingRowChangesNothing() {
        assertEquals(0, books.rename(999L, "Absent"));
        assertEquals(0, books.addPriceCents(999L, 50));
        assertEquals(0, books.deactivate(999L));
    }

    @Test
    void deactivatesRowAndExcludesItFromCount() {
        books.insert(book(
                401L, "ISBN-401", "Active", 4000, true));
        books.insert(book(
                402L, "ISBN-402", "Inactive", 4000, false));

        assertEquals(1, books.countActive());
        assertEquals(1, books.deactivate(401L));
        assertEquals(0, books.countActive());
        assertFalse(books.findById(401L)
                .orElseThrow().active());
    }

    @Test
    void deletesOneRowButKeepsAnother() {
        books.insert(book(
                501L, "ISBN-501", "Delete me", 1900, true));
        books.insert(book(
                502L, "ISBN-502", "Keep me", 1900, true));

        assertEquals(1, books.deleteById(501L));
        assertEquals(0, books.deleteById(501L));
        assertTrue(books.findById(501L).isEmpty());
        assertTrue(books.findById(502L).isPresent());
    }

    @Test
    void queryBindsValueRatherThanConcatenatingSql() {
        var query = dsl.select(ID)
                .from(BOOKS)
                .where(ISBN.eq("ISBN-601"));

        assertTrue(
                query.getSQL(ParamType.INDEXED).contains("?"));
        assertEquals(
                List.of("ISBN-601"), query.getBindValues());
    }

    @Test
    void jdbcAndJooqSeeSameTransactionalRows() {
        books.insert(book(
                701L, "ISBN-701", "Shared DS", 2100, true));

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        Integer count = jdbc.queryForObject(
                "select count(*) from catalog_books where isbn = ?",
                Integer.class,
                "ISBN-701");

        assertEquals(1, count);
    }

    @Test
    void duplicateIsbnIsRejectedByDatabase() {
        books.insert(book(
                801L, "ISBN-DUP", "First", 100, true));

        assertThrows(DataAccessException.class,
                () -> books.insert(book(
                        802L, "ISBN-DUP", "Second", 100, true)));
    }

    @Test
    void negativePriceIsRejectedByDatabase() {
        assertThrows(DataAccessException.class,
                () -> books.insert(book(
                        901L, "ISBN-901", "Invalid", -1, true)));
    }
}
```

**Theo source có 14 phương thức `@Test`**, mỗi phương thức có mục tiêu độc lập. Chúng là **ví dụ dự kiến có thể chạy** trên project Boot 3.3.5/H2 khi thiết lập file đúng như trên; chưa có execution report thực tế của Gradle trong bài, nên không tuyên bố “14 PASS” đã xảy ra.

### Vì sao @Sql BEFORE_TEST_CLASS?

`jooq-schema.sql` được tạo một lần trước khi các method cần bảng `catalog_books`. Không có dữ liệu cố định trong script. Mỗi test dùng `@BeforeEach` xóa rows trong test transaction và tự tạo fixture, trong khi test transaction mặc định rollback khi kết thúc.

`@Sql(ExecutionPhase.BEFORE_TEST_CLASS)` là tính năng Spring TestContext 6.1. Nếu một project cũ dùng phiên bản Spring Framework khác không hỗ trợ phase này, hãy chuẩn bị schema bằng Flyway/Liquibase hoặc SQL init đúng lifecycle; không copy annotation rồi đoán nó được hỗ trợ.

### Vì sao @Import BookQueries và JooqConfig?

`@JooqTest` không scan regular components. `@Import` thêm **chính xác những beans test cần**:

- `BookQueries`: đối tượng đang được kiểm thử, được inject `DSLContext`.
- `JooqConfig`: bean `DefaultConfigurationCustomizer` để xác minh cấu hình cũng có mặt trong test slice.

Nếu bỏ `@Import(BookQueries.class)` trong project mà slice không nhận bean này, test có thể fail với `NoSuchBeanDefinitionException`. Không khắc phục bằng cách đổi toàn bộ test sang `@SpringBootTest` nếu phạm vi đang chỉ cần jOOQ.

## 13. Phân tích từng nhóm test

### 13.1. Context, dialect và customizer

`createsDslContextWithH2DialectAndCustomizer` assert trực tiếp:

- Có `DSLContext` từ Spring Boot.
- Có `DataSource` được inject.
- Dialect là `SQLDialect.H2`.
- `isRenderFormatted()` bằng `Boolean.TRUE`.

Một test chỉ assert `dsl != null` chưa chứng minh cấu hình đúng. Nếu config `JooqConfig` không được import, assertion format có thể fail hoặc không có giá trị mong muốn, trong khi truy vấn SQL vẫn chạy.

**Không kiểm tra chi tiết SQL formatted bằng so sánh cả một multiline string** nếu không có contract cần thiết: whitespace/keyword style thay đổi giữa jOOQ versions. Assertion trên `Settings` ổn định và phản ánh đúng property đang test.

### 13.2. SELECT/INSERT và mapping

`insertsAndFindsByPrimaryKey` insert `BookRow` rồi đọc lại. Assertions trên `record.equals` kiểm tra id, isbn, title, priceCents và active, chứ không chỉ kiểm tra count.

`findsByIsbnAndReturnsEmptyForMissing` kiểm tra `Optional<BookRow>` với một khóa tồn tại và hai khóa không tồn tại. Dùng `fetchOptional` của jOOQ nên absent row được chuyển thành `Optional.empty()`.

**Không đánh đồng:** `fetchOne()` có thể trả null, `fetchOptional()` trả Optional, `fetchSingle()` có semantics bắt buộc đúng một hàng. Chọn đúng API và test trường hợp 0/nhiều rows theo contract truy vấn.

### 13.3. Filter/ORDER BY

`filtersActiveBooksAndSortsById` đưa vào 4 records theo ID không tăng dần; chỉ 2 row có `active=true` và title bắt đầu bằng `Spring`. Query có `orderBy(ID.asc())`, nên expected list là ID 201 trước 202. Nếu thiếu `ORDER BY`, thứ tự SQL result **không được bảo đảm** dù H2 có thể tình cờ trả theo primary key.

### 13.4. UPDATE và delete row count

`updatesTitleAndReportsAffectedRow`, `addsPriceUsingTypedSqlExpression` và `deletesOneRowButKeepsAnother` assert returned affected row count. Truy vấn update:

```java
dsl.update(BOOKS)
   .set(PRICE_CENTS, PRICE_CENTS.add(delta))
   .where(ID.eq(id))
   .execute();
```

làm phép cộng tại database, không phải tải record về Java rồi cộng và ghi lại; có ý nghĩa khi bạn muốn một statement cập nhật. Nhưng đây **không thay thế** biện pháp kiểm soát concurrency hoặc tránh overflow nếu domain cho phép delta tùy ý.

Với missing ID, SQL UPDATE/DELETE ảnh hưởng 0 row, và test kiểm tra trường hợp này. Nếu API nghiệp vụ cần trả 404, lớp service/controller phải chuyển 0 affected rows thành lỗi thích hợp; DAO không tự phát HTTP status.

### 13.5. Bind parameter

`queryBindsValueRatherThanConcatenatingSql` dựng một query chưa cần chạy, inspect `getSQL(ParamType.INDEXED)` và `getBindValues()`:

- Rendered SQL chứa placeholder `?`.
- Bind value list chứa `"ISBN-601"`.

Đây là **kiểm tra cách dựng query theo mode indexed binding**, không phải penetration test toàn diện. Nếu cấu hình `Settings` đổi `StatementType.STATIC_STATEMENT`, hành vi execute khác có thể cần test riêng. Đừng tự nối input vào `DSL.sql(...)` hoặc dynamic identifiers chỉ vì một test có `?` đã PASS.

### 13.6. Hai API cùng DataSource và transaction

`jdbcAndJooqSeeSameTransactionalRows` insert qua jOOQ rồi dùng `new JdbcTemplate(dataSource)` SELECT. Spring JDBC và Spring Boot jOOQ auto-configuration được thiết kế để phối hợp trên cùng Spring-managed DataSource/transaction. Test chứng minh hai API thấy cùng hàng **trong transaction hiện tại**.

Nó **không chứng minh đã commit**. Một JDBC connection ở transaction khác có thể không nhìn thấy insert chưa commit tùy isolation level. `@JooqTest` rollback sau mỗi test nên dữ liệu không tồn tại bên ngoài test trừ khi cấu hình transaction bị thay đổi.

### 13.7. Database constraint failures

`duplicateIsbnIsRejectedByDatabase` và `negativePriceIsRejectedByDatabase` cố tình làm H2 trả lỗi unique/check constraint. Lỗi được jOOQ bọc thành `org.jooq.exception.DataAccessException`, nên test kiểm tra exception tại jOOQ boundary.

Sau một SQL constraint violation, một transaction có thể rơi vào trạng thái cần rollback; **không thực hiện tiếp các query như thể transaction chắc chắn vẫn lành**. Mỗi negative test riêng giúp transaction rollback dọn dẹp. Với database production khác H2, kiểm tra SQLState/root cause nếu cần phân biệt unique/check violations một cách chính xác.

## 14. Transaction semantics của @JooqTest

Theo Spring Boot 3.3, `@JooqTest` được chú thích `@Transactional` và test-managed transaction được rollback theo mặc định. Điều đó tạo isolation thuận tiện:

```text
JUnit test 1
    BEGIN (Spring TestContext)
    INSERT id=101
    SELECT id=101  -> thấy row trong cùng transaction
    ROLLBACK

JUnit test 2
    BEGIN
    INSERT id=101  -> thường không conflict với test 1 đã rollback
    ROLLBACK
```

`@BeforeEach` cũng chạy trong framework-managed transaction của test theo lifecycle thông thường. Nó xóa dữ liệu nếu có trong context test, nhưng không làm table DDL tồn tại nếu chưa chạy schema script. Vì vậy ta chuẩn bị schema trước lớp test.

### Flush và commit của jOOQ không giống JPA

jOOQ thực thi statement khi gọi `execute()`/`fetch()`, không có JPA persistence context/dirty checking để cần `EntityManager.flush()`. Nhưng query được thực thi **trong transaction** chưa chắc commit. Đây là lý do test thấy row không đồng nghĩa dữ liệu bền vững sau test.

**Đừng nhầm `DSLContext.transaction(...)` với Spring TestContext transaction:**
- Spring-managed transaction trong `@JooqTest` đã tồn tại.
- jOOQ có API transaction riêng qua `Configuration` và `TransactionProvider`; cần biết khi nào dùng scope `dsl.transaction(configuration -> ...)` và cách phối hợp với Spring.
- Tránh mở transaction/nested transaction thủ công trong một test chỉ muốn CRUD; nếu cần kiểm thử commit/savepoint, thiết kế riêng và kiểm tra semantics của provider/database.

### Tắt rollback/transaction khi nào?

Có thể dùng Spring Test `@Rollback(false)` hoặc `@Commit` trong một test có lý do, hoặc `@Transactional(propagation = NOT_SUPPORTED)` để tắt test-managed transaction trong tình huống đặc biệt. Nhưng việc này khiến dữ liệu test có thể tồn tại sau method và yêu cầu cleanup rõ ràng. Với H2 demo, **giữ rollback mặc định** là an toàn và nhanh nhất.

**Không chạy `@Rollback(false)` hoặc `Replace.NONE` trên database production** trong quá trình học nếu chưa chắc database được cô lập.

## 15. Cấu hình DSLContext nâng cao

### 15.1. Listener lifecycle

jOOQ hỗ trợ `ExecuteListener` và `ExecuteListenerProvider` để đo thời gian, log query, quan sát lỗi và số statement. Spring Boot có thể đưa listener providers vào `Configuration` được auto-configure.

Snippet minh họa, không phải file trong demo:

```java
@Bean
DefaultConfigurationCustomizer customizer() {
    return config -> {
        config.settings().setRenderFormatted(true);
    };
}
```

Nếu cần listener, thêm bean/provider có lifecycle phù hợp và test rằng listener quan sát đúng statement. **Không dùng logger SQL làm bằng chứng duy nhất của query result**; logs có thể thay format theo phiên bản. Khi log binds, che dữ liệu nhạy cảm.

### 15.2. Thay Settings bằng customizer hay bean riêng?

Một `DefaultConfigurationCustomizer` cho phép chỉnh bean `DefaultConfiguration` Boot đang tạo. Nếu bạn tự khai báo `org.jooq.Configuration` bean, Boot có thể bỏ qua phần auto-config tương ứng; khi đó hãy chịu trách nhiệm thiết lập `ConnectionProvider`, `SQLDialect` và transaction integration đúng.

Trong bài tập, không cần custom DSLContext bean. Việc test cấu hình hiệu quả nhất là inject bean mà controller/repository thực sự sẽ dùng và assert những properties quan trọng.

### 15.3. Settings render SQL, không phải SQL injection policy

Các settings như `renderFormatted`, `renderQuotedNames`, `renderNameCase`, `statementType`, `paramType` có tác động khác nhau. Chỉ đặt renderQuotedNames/statementType khi hiểu rõ kết quả và có tests bảo vệ. Một thay đổi để SQL “đẹp” không nên làm identifiers khác case hoặc chuyển binds thành inline literals ngoài ý muốn.

### 15.4. DefaultConfigurationCustomizer và thứ tự bean initialization

Customizer được gọi trong quá trình Boot dựng jOOQ configuration, trước khi inject DSLContext vào repository. Nếu trong test bạn gọi:

```java
dsl.configuration().settings().setRenderFormatted(true);
```

thì bạn **đang chỉnh runtime config trong test**, không kiểm tra registration từ production config. Demo tránh cách đó và assert customizer đã chạy tự nhiên thông qua `@Import(JooqConfig.class)`.

### 15.5. @TestConfiguration thay cho @Import config production

Nếu muốn một customizer **chỉ tồn tại trong test**, có thể dùng `@TestConfiguration` nested static class với `@Bean DefaultConfigurationCustomizer` rồi `@Import`. Cách này phù hợp để ép schema mapping hoặc listeners phục vụ test; nhưng khác với kiểm tra cấu hình production đang có. Bài này import `JooqConfig` thật để chứng minh đúng cấu hình đã định nghĩa.

## 16. Database initialization: schema.sql, @Sql, Flyway và Liquibase

Có nhiều cơ chế chuẩn bị database trước test, nên **chọn một cơ chế có chủ đích**.

| Cơ chế | Phù hợp khi | Lưu ý |
| --- | --- | --- |
| `@Sql("/jooq-schema.sql")` | Một số bảng demo/test nhỏ | Lựa chọn execution phase và transaction cho DDL |
| `schema.sql` / `spring.sql.init.mode` | Project đơn giản muốn Boot init SQL khi context start | Cẩn thận không chạy lại trùng migrations |
| Flyway/Liquibase | Project có schema migration versioned | Dùng migration thật để tránh lệch production |
| Testcontainers + migration | SQL dialect/constraints/locking quan trọng | Cần Docker/test environment |
| Tự tạo table bằng `DSLContext` | DDL là chủ đề test, sandbox riêng | Tránh chạy DDL trong transaction của test tùy tiện |

### Tại sao dùng @Sql BEFORE_TEST_CLASS trong bài?

- Test class chỉ cần một table và không có migration phức tạp.
- Script `jooq-schema.sql` nằm trong test classpath và được chạy trước methods.
- Mỗi test tự tạo dữ liệu, không lệ thuộc file `data.sql` hoặc thứ tự test.
- DML được rollback, DDL không cần rollback trong từng test.

Nếu một test class khác dùng cùng database/schema trong Spring context cache, tên bảng/schema và khả năng chạy song song cần được quản lý rõ. `CREATE TABLE IF NOT EXISTS` trong demo giúp script an toàn hơn khi một table đã có; trong môi trường migration production, không dùng `IF NOT EXISTS` như cách che một schema sai phiên bản.

### DDL của H2 khác database khác

H2 chấp nhận `BOOLEAN` và `CHECK(price_cents >= 0)` trong demo. PostgreSQL có thể hỗ trợ cú pháp tương tự, nhưng enum, generated identities, JSON, array, operator và transaction semantics vẫn khác. Test với H2 không đủ xác nhận mọi SQL của application chạy đúng trên database production.

## 17. Code generation và typed jOOQ schema

Một trong những thế mạnh của jOOQ là **code generator** đọc database schema và sinh Java classes như `Tables.BOOKS` hoặc `BOOKS.ISBN`. Bài demo dùng `BookSql` thủ công để không bắt người học cấu hình generator ngay, nhưng trong ứng dụng thực việc codegen giúp:

- Phát hiện thay đổi schema/đổi tên cột ngay khi biên dịch (nếu code được regenerate).
- Có type metadata và generated keys/records giúp query khó sai kiểu hơn.
- Hạn chế lỗi quote/case/naming do string constants.
- Dễ join tables, fetch record và map fields.

Một pipeline thông thường:

```text
Flyway/Liquibase migrations
    ↓
Temporary schema / database cho codegen
    ↓
jOOQ code generator
    ↓
Generated Tables, Fields, Records
    ↓
BookQueries dùng typed generated API
    ↓
@JooqTest + database schema tương ứng
```

Cần đồng bộ phiên bản schema test với version generated code. Nếu generated class tham chiếu column chưa tồn tại trong H2 test, query sẽ lỗi dù Java compile. Đừng kiểm tra một generated DSL trên schema cũ rồi cho rằng type safety đã bảo vệ runtime compatibility.

**jOOQ edition:** khả năng dialect/codegen cho một số database và tính năng có thể phụ thuộc bản open-source hoặc thương mại. Dùng dialect/license tương thích với dự án; ví dụ H2 thông thường phù hợp open-source edition.

## 18. Chọn các assertion có ý nghĩa

Một test SQL tốt thường có:

1. **Arrange:** tạo dữ liệu qua đúng DataSource test.
2. **Act:** gọi chính query cần kiểm thử, không lặp lại cùng implementation ở test để tự xác nhận.
3. **Assert:** kiểm tra giá trị, số row, thứ tự, kiểu dữ liệu và nhánh lỗi.
4. **Isolation:** không phụ thuộc dữ liệu còn lại của test khác.
5. **Dialect:** test chạy đúng DB/dialect so với điều đang muốn chứng minh.

Một số assertions mẫu:

```java
assertEquals(1, books.insert(book));
assertEquals(book, books.findById(book.id()).orElseThrow());
assertEquals(0, books.rename(999L, "missing"));
assertTrue(books.findByIsbn("unknown").isEmpty());
```

Đây là snippet cần đặt trong class test có biến `books` và `book` phù hợp. Chỉ assert “không ném exception” thường quá yếu: một UPDATE có điều kiện sai có thể chạm 0 hàng mà không có lỗi.

### Assert SQL render vs assert thực thi SQL

`getSQL(ParamType.INDEXED)` và `getBindValues()` kiểm tra query construction. Chúng hữu ích để chứng minh client input được bind đúng, nhưng **không chứng minh database có bảng/cột hay query trả đúng row**. Vì vậy vẫn cần tests thực thi trên H2 cho INSERT/SELECT/UPDATE/DELETE.

Ngược lại, test thực thi SELECT có thể PASS khi writer chèn fixture sai cách khiến WHERE không được exercise đủ. Chọn dữ liệu phân biệt: active/inactive, đúng/sai prefix, ID không theo thứ tự insert. Đây là lý do test `filtersActiveBooksAndSortsById` có bốn records khác nhau.

## 19. Khi nào cần Testcontainers và @DynamicPropertySource?

Khi domain SQL phụ thuộc Postgres/MySQL feature, H2 chỉ nên là unit-ish integration filter. Hướng tiếp cận:

- Khởi động database container đúng loại.
- Chạy migration thật của ứng dụng.
- Truyền JDBC URL, username và password vào Spring context bằng `@DynamicPropertySource` hoặc `@ServiceConnection` phù hợp.
- Dùng `@JooqTest` với `@AutoConfigureTestDatabase(replace = NONE)`.
- Đảm bảo `SQLDialect` được Boot phát hiện đúng hoặc cấu hình chính xác.
- Dọn rows/schema theo transaction và container lifecycle; không liên kết tới production.

Snippet chiến lược:

```java
@JooqTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgresJooqTest {
    @Autowired DSLContext dsl;
}
```

Chưa có Testcontainers setup nên đây **không phải project runnable độc lập**. Khi tạo test thật, cần thêm dependencies, container annotation/lifecycle, driver và dynamic properties. Nếu database driver hiện có và Boot có thể detect dialect, không nhất thiết ép property bằng hardcoded value.

**Một hạn chế của @JooqTest:** regular components không được scan. Nếu DAO production cần một query listener, custom converter hoặc service bean không được slice tự load, cần import đúng collaborators hoặc dùng integration test rộng hơn để kiểm chứng tương tác.

## 20. Chống SQL injection khi cấu hình DSLContext

jOOQ fluent DSL dùng `Field<T>` và bind values giúp tránh string-concatenation injection cho **giá trị**. Nhưng cần phân biệt:

### 20.1. Giá trị do người dùng nhập

An toàn hơn:

```java
dsl.select(ISBN)
   .from(BOOKS)
   .where(ISBN.eq(userInput));
```

Giá trị `userInput` được jOOQ bind theo cách dựng query phù hợp.

Không an toàn khi tự ghép raw SQL:

```java
dsl.resultQuery(
    "select isbn from catalog_books where isbn = '"
    + userInput + "'");
```

Đây là **phản ví dụ**. `resultQuery(String)` cho phép plain SQL; nếu chuỗi chứa input do người dùng kiểm soát thì có thể SQL injection. Nếu cần raw SQL, dùng placeholder và bind values:

```java
dsl.resultQuery(
    "select isbn from catalog_books where isbn = ?",
    userInput);
```

### 20.2. Table/column names động

SQL parameter placeholders **không thay thế tên bảng/cột**. Nếu API cho phép sort field từ query parameter, dùng allowlist map một số giá trị công khai như `"title"`, `"price"` sang typed `Field<?>` đã định nghĩa. Không đưa tên cột từ client vào `DSL.field(String)`/plain SQL template nếu chưa validate.

### 20.3. LIKE patterns

Bind value không loại bỏ wildcard semantics của SQL LIKE. Người dùng nhập `%` hoặc `_` có thể làm bộ lọc rộng hơn. Nếu contract yêu cầu literal prefix, escape wildcard thích hợp và test case chứa ký tự đặc biệt.

### 20.4. Không log dữ liệu nhạy cảm

jOOQ query logging và `ExecuteListener` có thể truy cập SQL/binds. Đừng bật logging raw credentials, token, PII hoặc thông tin nhạy cảm vào CI logs. Khi cần debug, dùng redaction và query metrics không chứa dữ liệu cá nhân.

## 21. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `No qualifying bean of type DSLContext` | Thiếu starter-jooq/DataSource hoặc context không phải jOOQ slice | Kiểm tra dependencies, @JooqTest, JDBC driver |
| `No qualifying bean of type BookQueries` | @JooqTest không scan regular @Repository | `@Import(BookQueries.class)` |
| `@JooqTest` đụng DB ngoài | Mặc định giữ configured DataSource | Dùng `@AutoConfigureTestDatabase(replace=ANY)` khi cần H2 |
| Wrong dialect | `spring.jooq.sql-dialect` sai hoặc không detect | Assert `dsl.configuration().dialect()` |
| Customizer không chạy trong slice | `JooqConfig` không được import | `@Import(JooqConfig.class)` hoặc test config rõ |
| `Table not found` | Chưa tạo schema, @Sql file sai đường dẫn | Kiểm tra jooq-schema.sql và @Sql execution phase |
| `Column not found` | Sai case/quoted identifier hoặc schema mismatch | `DSL.unquotedName`/generated fields, kiểm tra DDL |
| `NoSuchBeanDefinitionException` cho service | Slice cố ý loại bean không liên quan | Import/mock dependency cần thiết hoặc full test |
| `DataAccessException` khi INSERT | Unique/CHECK/FK constraint hoặc lỗi SQL | Đọc SQLState/root cause; test exception riêng |
| DML test để lại dữ liệu | Tắt rollback, dùng connection ngoài transaction | Giữ @Transactional mặc định và Spring-aware DataSource |
| Test PASS riêng, FAIL cả suite | Shared schema/static data/context cache | Cô lập fixture, cleanup đúng transaction |
| Query trả sai thứ tự | Không có ORDER BY | `orderBy(...)` tường minh |
| LIKE lọc quá rộng | Input chứa %/_ | Escape wildcard theo contract |
| Test `?` nhưng SQL vẫn rủi ro | Plain SQL khác có ghép raw input | Bảo vệ mọi query construction path |
| H2 PASS nhưng PostgreSQL FAIL | Dialect/SQL/schema khác | Testcontainers database đúng loại |
| Test báo SQL formatted sai | Mapper dùng Settings khác hoặc config không import | Assert `dsl.configuration().settings()` |
| Class không tìm thấy @SpringBootConfiguration | Test nằm ngoài package hierarchy | Đặt test dưới package chính hoặc chỉ định config phù hợp |
| Test DDL rollback khác kỳ vọng | H2 DDL auto-commit | Chuẩn bị schema trước test methods |
| Cannot determine suitable driver | H2 không ở test runtime hoặc DataSource sai | Kiểm tra dependency/connection settings |
| Java compile fail ở package @JooqTest | Dùng import Boot 4 vào Boot 3 | Dùng `org.springframework.boot.test.autoconfigure.jooq.JooqTest` |

### Chẩn đoán có trình tự

1. Xem root cause từ test report, không chỉ `Failed to load ApplicationContext`.
2. Xác nhận version Boot/jOOQ, test JDK và H2 driver.
3. Assert `dsl != null`, `dataSource != null`, SQL dialect và customizer.
4. Xác nhận `jooq-schema.sql` được thực thi trước test.
5. Kiểm tra `BOOKS`/`ID`/`ISBN` Field metadata có khớp DDL.
6. Tạo đúng một fixture, SELECT lại bằng jOOQ.
7. Kiểm tra transaction active và rollback behavior.
8. Nếu lỗi chỉ trên production DB, thử đúng dialect bằng Testcontainers.
9. Loại bỏ phụ thuộc vào thứ tự test hoặc shared mutable state.
10. Đọc SQL/binds an toàn khi cần, không đổi expected values để che lỗi.

## 22. Chạy test và kết quả mong đợi

Trong project ví dụ có **14 phương thức `@Test`** tại `BookQueriesJooqTest`.

Chạy bằng Gradle Wrapper (nếu project có wrapper):

```bash
./gradlew test --tests 'com.example.jooq.BookQueriesJooqTest'
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu bạn chưa tạo Gradle Wrapper mà đã cài Gradle tương thích:

```bash
gradle test
```

Không có stdout nghiệp vụ cố định: JUnit và Gradle xuất báo cáo test dựa trên môi trường. Mở:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

để kiểm tra số test thực sự chạy, số PASS/FAIL/SKIPPED và stack trace. Những từ “14 test” trong bài chỉ nói **số method khai báo trong source**, không phải kết quả chạy đã được đo trong một môi trường Gradle cụ thể.

### Kết quả thực hành cần đạt

- Có một Spring-managed `DSLContext` liên kết với H2 DataSource test.
- `SQLDialect.H2` được xác nhận.
- `DefaultConfigurationCustomizer` đã áp dụng `renderFormatted=true`.
- `BookQueries` được nạp vào `@JooqTest` qua `@Import`.
- Queries CRUD/mapping/filtered ordering và bind parameters chạy đúng.
- Các lỗi unique/CHECK constraint được bắt tại jOOQ boundary.
- Transaction test active và rollback mặc định bảo vệ fixture isolation.

Nếu một assertion fail, không được mặc nhiên thay expected cho qua. Phân biệt lỗi cấu hình DataSource/dialect, lỗi DDL/schema, lỗi DAO query và lỗi test fixture.

## 23. Checklist QA trước khi merge

- [ ] Test đang dùng `@JooqTest` đúng phạm vi, không khởi động full application nếu chỉ cần jOOQ?
- [ ] Spring Boot và jOOQ versions đã được chốt trong dependency/BOM?
- [ ] Đã có `DSLContext` bean từ Spring, không dùng một DSLContext tự tạo không kết nối?
- [ ] DataSource test có được xác nhận, không đụng DB production?
- [ ] Nếu cần embedded DB, đã chọn `@AutoConfigureTestDatabase` rõ ràng?
- [ ] `SQLDialect` đúng với DB thực tế, không chỉ property tùy tiện?
- [ ] Những `DefaultConfigurationCustomizer` hoặc listeners cần test có được import?
- [ ] DAO/repository cần kiểm tra có mặt bằng `@Import` nếu slice không scan?
- [ ] Schema có được tạo bằng `@Sql`/migration đúng thời điểm?
- [ ] Query dùng typed Fields/generated jOOQ table và bind variables cho user input?
- [ ] Có assertions cho returned rows, mapping và affected row counts?
- [ ] Thứ tự kết quả có `ORDER BY` khi contract yêu cầu?
- [ ] Có positive và negative cases (not-found, zero affected, constraints)?
- [ ] Constraint error có test riêng, không tiếp tục dùng transaction sau SQL failure?
- [ ] Có nhận biết transaction rollback mặc định và phạm vi visibility?
- [ ] Không coi H2 là bằng chứng cho SQL dialect/locking của production?
- [ ] Có test PostgreSQL/MySQL Testcontainers khi query dùng feature đặc thù?
- [ ] SQL schema/migrations và jOOQ codegen output có đồng bộ?
- [ ] Test không dựa vào thứ tự methods hoặc shared/static fixture?
- [ ] Có kiểm tra report thực thay vì chỉ đếm `@Test` trong source?

## 24. Bài tập thực hành

1. Bỏ `@Import(BookQueries.class)`, chạy test và phân biệt lỗi bean scan với lỗi `DSLContext`.
2. Bỏ `@Import(JooqConfig.class)`, giữ assertion `isRenderFormatted()`; giải thích vì sao configuration test không còn chứng minh customizer.
3. Bỏ `@AutoConfigureTestDatabase` khi project có DataSource PostgreSQL và nêu rủi ro truy cập DB ngoài.
4. Thử cấu hình sai `spring.jooq.sql-dialect` (ví dụ POSTGRES khi đang dùng H2). So sánh SQL rendering và lỗi, không coi property là cách đổi DB.
5. Đổi `BookSql.BOOKS` từ `DSL.unquotedName` thành `DSL.name`, quan sát case-sensitive quoted identifier trên H2.
6. Trong `filtersActiveBooksAndSortsById` bỏ `orderBy`, giải thích tại sao không còn hợp đồng thứ tự.
7. Thêm một query `findByPriceRange` có hai bind values và viết test các boundary values.
8. Thử chèn hai ISBN giống nhau trong một test riêng, xác định exception type/root cause từ H2.
9. Thử giá trị price âm và bảo vệ `CHECK` constraint.
10. Kiểm tra `getBindValues()` khi input chứa dấu nháy đơn; giải thích vì sao parameterization quan trọng.
11. Viết một truy vấn `COUNT(*)` bằng jOOQ rồi so sánh với `JdbcTemplate` dùng cùng transaction.
12. Thử thêm một `@Service` không được import và giải thích vì sao `@JooqTest` không tự scan nó.
13. Dùng `@TestConfiguration` tạo một test-only `DefaultConfigurationCustomizer` và kiểm tra khác biệt so với import config production.
14. Tạo một integration test PostgreSQL Testcontainers với `Replace.NONE` để so sánh H2 về schema/dialect.
15. Dùng Flyway migrations để tạo bảng, bỏ `@Sql` và xác nhận schema giống production.
16. Thêm jOOQ code generation và thay `BookSql` thủ công bằng generated Tables/Fields.
17. Chạy `gradle test` và xác nhận số phương thức test thực thi, không chỉ đếm method.
18. Khi dùng SQL logging, kiểm tra có ẩn các bind values chứa PII/secrets không.

## 25. Tài liệu tham khảo

- [Spring Boot 3.3 — Auto-configured jOOQ Tests](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@JooqTest`, giới hạn component scan, DSLContext bean, DataSource và rollback mặc định.
- [Spring Boot 3.3 — SQL Databases / Using jOOQ](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html): `DSLContext`, `spring.jooq.sql-dialect` và `DefaultConfigurationCustomizer`.
- [Spring Boot 3.3 — JooqTest Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jooq/JooqTest.html): annotation APIs của Boot 3.x.
- [jOOQ 3.19 — DSLContext](https://www.jooq.org/doc/3.19/manual/sql-building/dsl-context/): cấu trúc `Configuration` và DSLContext.
- [jOOQ 3.19 — SQL Identifier Naming](https://www.jooq.org/doc/3.19/manual/sql-building/names/): quoting, case-sensitive identifiers, `DSL.unquotedName`.
- [jOOQ 3.19 — Custom Settings](https://www.jooq.org/doc/3.19/manual/sql-building/dsl-context/custom-settings/): `Settings`, SQL rendering configuration.
- [Spring Framework — Transactional Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback và test-managed transaction.
- [Spring Framework — Executing SQL Scripts with @Sql](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): SQL script lifecycle, execution phase và transaction.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html): schema.sql/data.sql, Flyway/Liquibase, init mode.

## 26. Kết luận

**`@JooqTest` là công cụ test slice dành cho jOOQ, không phải full application context.** Nó cung cấp Spring-managed `DSLContext` với DataSource, dialect và transaction integration. Với Boot 3.3, database hiện có được dùng theo mặc định; **muốn thay bằng H2 cần lựa chọn `@AutoConfigureTestDatabase`**. Test transaction mặc định rollback sau mỗi phương thức.

Để kiểm tra cấu hình đúng, hãy assert `dsl.configuration().dialect()` và những `Settings` quan trọng; đưa production `DefaultConfigurationCustomizer`/DAO vào slice bằng `@Import` khi cần. Kiểm tra hành vi SQL bằng fixtures có đủ phân biệt, returned rows, row counts, bind values, thứ tự và constraint failures. H2 phù hợp cho vòng phản hồi nhanh, nhưng khi semantics phụ thuộc database vendor, hãy kiểm thử thêm bằng migration và Testcontainers trên đúng loại database.
