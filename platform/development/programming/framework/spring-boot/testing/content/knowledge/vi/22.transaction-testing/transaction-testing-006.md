# Flush để quan sát lỗi SQL trước khi transaction kết thúc — Spring Boot testing

## 1. Vấn đề thực tế: test xanh dù SQL chưa được gửi đi

Trong Spring Data JPA, đoạn code sau trông như đã kiểm tra được việc tạo một bản ghi:

```java
repository.save(new BookingRecord("BK-100", "Mai"));
```

Nhưng `save` **không phải là lời cam kết đã thực thi đủ SQL và database đã chấp nhận bản ghi**. JPA có **persistence context**: thay đổi object có thể được lưu ở bộ nhớ của `EntityManager` và chỉ được đồng bộ thành SQL khi ORM quyết định flush, hoặc khi lập trình viên gọi `flush()`.

Nếu test đang nằm trong transaction mà Spring TestContext **rollback** ngay sau method, một số thay đổi chưa được flush có thể không bao giờ được gửi thành SQL. Kết quả là assertion chỉ kiểm tra object Java sẽ xanh, trong khi production commit về sau lại thất bại vì unique constraint, NOT NULL, foreign key, chiều dài cột hoặc một lỗi SQL khác.

Một cách chủ động để test gặp lỗi sớm:

```java
repository.save(new BookingRecord("BK-100", "Mai"));
repository.flush(); // Yêu cầu ORM gửi pending SQL xuống database.
```

Hoặc:

```java
repository.saveAndFlush(
        new BookingRecord("BK-100", "Mai"));
```

**Nhưng `flush()` không phải `commit()`.** Database có thể đã thực thi SQL trong transaction, còn thay đổi vẫn chưa được commit và có thể rollback. Hơn nữa, một số constraint được cấu hình **deferred until commit** sẽ không nhất thiết phát lỗi ngay ở flush.

Bài này tập trung vào **kiểm thử giao dịch**: khi nào nên flush, quan sát lỗi SQL ở đâu, cách viết negative test ít flaky và giới hạn bằng chứng mà flush cung cấp.

## 2. Kết quả học tập

Sau bài, bạn có thể:

1. Giải thích `persistence context`, dirty checking, SQL action queue và cơ chế flushing của JPA/Hibernate.
2. Phân biệt `save`, `persist`, `merge`, `flush`, `saveAndFlush`, `clear`, `commit` và `rollback`.
3. Nhận biết transaction rollback mặc định của `@DataJpaTest` và lý do phải flush trước khi test kết thúc.
4. Dựng một ví dụ Java 17 + Spring Boot 3.3 + Spring Data JPA + H2 có khóa chính `SEQUENCE`, không dựa vào INSERT sớm của `IDENTITY`.
5. Kiểm tra INSERT đang chờ bằng JDBC query trực tiếp, rồi quan sát nó sau `EntityManager.flush()`.
6. Viết test bắt lỗi **unique constraint** từ database bằng `JpaRepository.flush()` hoặc `saveAndFlush()`.
7. Viết test cho UPDATE do dirty checking gây lỗi ở flush, không chỉ test INSERT.
8. Hiểu vì sao một JPQL/native query có thể kích hoạt **automatic flush** trong `FlushMode.AUTO`.
9. Phân biệt lỗi JPA validation, lỗi SQL, Spring exception translation và constraint deferred until commit.
10. Biết khi nào test cần **commit thật**, database vendor thật, nhiều transactions, hoặc cleanup riêng.
11. Tránh tiếp tục dùng transaction/persistence context đã hỏng sau một lỗi SQL.
12. Viết assertions dựa vào trạng thái quan sát được, không đoán số lượng SQL hay thời điểm INSERT tuyệt đối trong mọi ID strategy.

## 3. Sơ đồ một transaction và thời điểm phát hiện lỗi

```text
JUnit test method, @DataJpaTest
          |
          v
Spring TestContext mở test-managed transaction
          |
          v
repository.save(entity) / entityManager.persist(entity)
          |
          +--> Entity trở thành managed
          +--> Hibernate có thể xếp pending INSERT/UPDATE/DELETE
          +--> Không có bảo đảm mọi SQL đã chạy
          |
          v
entityManager.flush() / repository.flush()
          |
          +--> Hibernate dirty checking + SQL execution
          +--> Database có thể kiểm tra NOT NULL / UNIQUE / FK
          +--> Có thể ném lỗi ngay tại flush
          |
          +--> CHƯA commit
          |
          v
Assertion của JUnit
          |
          v
Spring TestContext rollback transaction sau @Test
```

Nếu **không** gọi explicit flush, Hibernate có thể tự flush trước một query hoặc trước commit tùy flush mode. Nhưng một test-managed transaction chỉ rollback khi method kết thúc có thể không đi qua commit. Không nên trông chờ Hibernate sẽ nhất định thực thi tất cả pending SQL ở một thời điểm nào đó trước khi test bị rollback.

Quan trọng hơn, **không phải mọi `save` đều hoãn INSERT**. Khi dùng `GenerationType.IDENTITY`, Hibernate thường phải INSERT sớm để lấy khóa ID từ database. Vì vậy ví dụ chính dùng `SEQUENCE` để minh họa một trường hợp INSERT có thể được xếp hàng đến flush. Tính chính xác đến từng SQL statement phụ thuộc provider, ID generator, flush mode, query, cascade và configuration thực tế.

## 4. Phân biệt các thao tác hay bị xem là giống nhau

| Thao tác | Điều nó thường làm | Điều nó không bảo đảm |
| --- | --- | --- |
| `EntityManager.persist(entity)` | Đưa new entity vào persistence context, lên lịch persist | SQL INSERT đã hoàn tất |
| `JpaRepository.save(entity)` | Persist hoặc merge tùy entity mới/cũ và chiến lược nhận biết | Commit hoặc SQL đã được kiểm tra hết |
| `JpaRepository.saveAndFlush(entity)` | Save rồi yêu cầu flush persistence context | Transaction đã commit |
| `JpaRepository.flush()` | Yêu cầu flush mọi pending changes của persistence context gắn với repository transaction | Chỉ flush đúng một entity vừa save |
| `EntityManager.flush()` | Đồng bộ pending thay đổi với database trong transaction | Rollback/commit |
| `TestEntityManager.persistAndFlush(entity)` | Persist entity rồi explicit flush cho JPA test | Spring exception type luôn giống repository proxy |
| `EntityManager.clear()` | Detach toàn bộ managed entities khỏi persistence context | Xóa database rows |
| `EntityManager.refresh(entity)` | Reload state của managed entity từ database | Flush mọi pending changes trước đó trong mọi provider/mode |
| `Transaction.commit()` | Kết thúc transaction thành công, thường flush còn pending trước commit | Các change khác ngoài transaction sẽ rollback theo |
| `Transaction.rollback()` | Hủy những thay đổi thuộc transaction đó | Hoàn tác changes đã commit bởi transaction khác |

**Nhớ ngắn gọn:** `save` thay đổi **JPA state**; `flush` đồng bộ **SQL trong transaction**; `commit` làm giao dịch **hoàn tất**.

### 4.1. `save()` có thể gọi `persist()` hoặc `merge()`

Spring Data JPA xác định entity có mới hay không dựa vào version, ID, `Persistable.isNew()` hoặc cơ chế nhận diện tương ứng. Với entity mới, repository thường gọi `EntityManager.persist`; với entity đã có, repository có thể gọi `merge`.

Với `merge`, object trả về có thể là **managed instance khác** object ban đầu. Do đó, nên dùng giá trị trả từ `repository.save(...)` khi cần làm việc với entity managed, không mặc định biến truyền vào luôn là object managed sau lệnh save.

Bài mẫu dùng `@GeneratedValue(SEQUENCE)` giúp Spring Data nhận diện new entity theo `id == null` và minh họa INSERT hoãn rõ ràng.

### 4.2. `flush()` không chỉ tác động một entity

Khi gọi `repository.flush()`, Hibernate có thể flush **tất cả pending changes** thuộc persistence context: những INSERT, UPDATE, DELETE và collection changes đã được xếp. Vì vậy một exception từ flush có thể đến từ **một entity khác** với entity ngay trước lệnh `flush()`.

Đừng khẳng định “lỗi này chắc chắn do dòng save cuối cùng” chỉ dựa vào vị trí lệnh flush. Để khoanh vùng, dùng fixture nhỏ, flush ở mốc rõ ràng và đọc root cause SQL/constraint name.

## 5. Flush trong Hibernate: mặc định AUTO và ngoại lệ

Hibernate, JPA provider thường gặp của Spring Boot 3.3, có flush mode mặc định kiểu **AUTO**. Theo tài liệu Hibernate, pending SQL có thể được flush:

- Trước khi transaction commit.
- Trước một JPQL/HQL query có liên quan tới các tables đang có pending changes.
- Trước một số native SQL queries, tùy cách bootstrap Hibernate và các synchronized query spaces.
- Khi ứng dụng gọi `EntityManager.flush()`, `Session.flush()` hoặc `JpaRepository.flush()` tường minh.

Vì vậy **không nói** “SQL chỉ chạy ở commit”. Nó có thể chạy ở nhiều thời điểm, kể cả trước query hoặc sớm do ID generation.

### 5.1. JPQL query có thể kích hoạt flush

Ví dụ minh họa:

```java
entityManager.persist(new BookingRecord(
        "BK-200", "An"));

// Một JPQL query liên quan bảng booking_records
// có thể kích hoạt AUTO flush trước khi query chạy.
long number = repository.count();
```

Trong Hibernate AUTO, một query trên bảng có pending changes thường khiến ORM flush để kết quả query phù hợp state. Vì thế test kiểu `save(); repository.count();` đôi khi **vô tình kiểm tra được INSERT** nhưng dựa vào auto flush không nói lên ý định của test.

Nếu mục tiêu rõ là “buộc database đánh giá lỗi SQL trước khi kiểm tra kết quả”, dùng `flush()` tường minh. Việc assert thời điểm flush theo từng query/provider có thể giòn; trọng tâm là database invariant.

### 5.2. FlushModeType.COMMIT

`jakarta.persistence.FlushModeType.COMMIT` yêu cầu provider hoãn flushing đến commit khi có thể. Nhưng JPA không bảo đảm pending changes luôn hiển thị cho mọi queries trước commit dưới mode này. Một explicit `flush()` vẫn hữu ích nếu test cần quan sát SQL tại một checkpoint.

### 5.3. FlushModeType.AUTO

`AUTO` là kiểu mặc định thường được dùng. Nó giúp đồng bộ state trước những queries cần nhìn thấy pending changes. Tuy nhiên, **không phải AUTO nghĩa là flush ở mọi query**. Hibernate có thể dựa vào query spaces/table overlap để tránh flush không cần thiết.

### 5.4. Hibernate MANUAL và read-only transactions

Hibernate còn có flush mode provider-specific như `MANUAL`; một số đường xử lý read-only có thể giảm dirty checking/flushing. Trong Spring, `@Transactional(readOnly=true)` chủ yếu là hint/optimization và có thể được Hibernate hỗ trợ bằng read-only session behavior.

Đừng sử dụng read-only transaction rồi cố viết entity và đo kết quả không có flush như một business rule. Nếu test cần ghi/kiểm tra constraints, dùng transaction có khả năng ghi và explicit flush.

### 5.5. Native queries

Native SQL query có thể kích hoạt flush khác JPQL tùy bootstrap API và synchronized query spaces. Do đó, đoạn `entityManager.createNativeQuery("select ...")` không phải một phương pháp di động giữa mọi JPA provider để chứng minh “chưa flush”.

Trong ví dụ thực hành, dùng **JdbcTemplate** để quan sát rows đã gửi xuống H2. Nó chạy JDBC trực tiếp, không yêu cầu Hibernate thực hiện JPA auto flush trước câu query; ta vẫn phải giữ ý thức JDBC query cùng transaction có thể thấy những changes đã flush nhưng chưa commit.

## 6. Vì sao test rollback có thể che lỗi SQL?

Với Spring Boot 3.3:

```java
@DataJpaTest
class BookingRepositoryTest {
    @Autowired BookingRepository repository;

    @Test
    void weakTest() {
        BookingRecord value =
                repository.save(new BookingRecord(
                        "BK-300", "Mai"));

        assertNotNull(value);
    }
}
```

Đây là **mẫu chống đối chiếu**, chưa phải một test đầy đủ độc lập. `assertNotNull(value)` chỉ xác nhận repository trả object. Nếu transaction sau đó rollback mà không flush, SQL INSERT/constraint có thể chưa được database đánh giá.

Test chặt hơn:

```java
repository.save(new BookingRecord("BK-300", "Mai"));
repository.flush();

// Có thể thêm JdbcTemplate query hoặc reload sau clear.
```

**Không nhầm:** test-managed rollback là ưu điểm về isolation. Vấn đề không phải “hãy tắt rollback”, mà là **chủ động flush trước assertion để buộc đường SQL chạy** khi đó là phần muốn kiểm tra.

### 6.1. Điều gì xảy ra nếu exception nổ sau khi @Test kết thúc?

Nếu test **commit** transaction, provider có thể flush và ném exception tại commit. Nhưng với `@DataJpaTest` mặc định, Spring rollback test-managed transaction; không có nghĩa mọi pending SQL sẽ được thực thi để phát hiện constraint.

Ngay cả khi exception xuất hiện ở teardown/commit của một test configuration khác, lỗi cũng khó khoanh vùng hơn so với `assertThrows(..., repository::flush)` ngay tại bước gây dữ liệu vi phạm.

### 6.2. Đừng ép flush ở mọi dòng

Flush quá nhiều lần trong production có thể:

- Tăng số lượt JDBC/database round trips.
- Phá cơ hội batch các INSERT/UPDATE.
- Làm thứ tự thực thi SQL khác tối ưu của Hibernate.
- Gây lock/contention sớm hơn.
- Khiến service chậm mà chưa chắc cải thiện correctness.

Trong test, explicit flush hữu ích tại **checkpoint quan sát**, không phải một quy tắc gọi sau mọi setter/save.

## 7. Những SQL errors nên test với flush

Các tình huống phù hợp:

| Rủi ro | Điểm có thể phát lỗi | Kiểm thử |
| --- | --- | --- |
| Unique constraint | INSERT/UPDATE SQL (hoặc commit nếu deferred) | Lưu hai business keys trùng, explicit flush |
| Foreign key constraint | INSERT/UPDATE/DELETE (hoặc commit nếu deferred) | Tạo reference sai; flush với dữ liệu vendor test |
| NOT NULL constraint | ORM validation hoặc database SQL | Dùng input null, xem lỗi phát ở tầng nào |
| Column length/precision | JPA/driver/database | Test dữ liệu vượt giới hạn, flush |
| CHECK constraint | Database statement/commit | Tạo giá trị vi phạm, flush, tùy engine |
| SQL type conversion | JDBC/driver | Test input không hợp lệ và mapping |
| Unsupported SQL dialect | SQL execution | Chạy repository native query trên đúng vendor |
| Lazy batch of writes | Flush hoặc commit | Cố ý flush để thấy lỗi trước rollback |
| Trigger logic | Statement hoặc transaction/commit | Test vendor database với trigger thật |
| Deferred constraint | **Commit**, không nhất thiết flush | Test commit hoặc `SET CONSTRAINTS IMMEDIATE` khi hỗ trợ |

**Không phải mọi lỗi validation là SQL error.** Nếu Bean Validation hoặc Hibernate nullability checks từ chối entity trước khi JDBC gửi statement, test vẫn có thể đúng nhưng bạn phải gọi nó là **ORM/validation rejection**, không nói đã kiểm tra database constraint nếu SQL chưa được gửi.

## 8. Dự án Java 17 + Spring Boot 3.3.0 + JPA + H2

Để minh họa **INSERT có thể được hoãn cho đến flush**, ta dùng entity với `GenerationType.SEQUENCE` thay vì `IDENTITY`. Hibernate có thể lấy giá trị ID từ sequence khi persist nhưng **không cần INSERT entity ngay**. Thí nghiệm so sánh trực tiếp qua JdbcTemplate trước và sau explicit flush.

Dự án gồm:

- Spring Boot application class.
- JPA entity `BookingRecord` với unique business code và sequence generator.
- `BookingRepository extends JpaRepository`.
- Một `@DataJpaTest` class có **5 methods**: INSERT defer/flush, duplicate khi flush, duplicate khi saveAndFlush, dirty-check UPDATE khi flush, reload sau clear.

Tất cả test dùng **H2 in-memory** để chạy độc lập; phần sau nói rõ khi nào phải đổi sang PostgreSQL Testcontainers.

### 8.1. Cây thư mục

```text
jpa-flush-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/flush/
    │   ├── FlushLabApplication.java
    │   ├── BookingRecord.java
    │   └── BookingRepository.java
    └── test/java/example/flush/
        └── BookingRepositoryFlushTest.java
```

### 8.2. `settings.gradle`

```groovy
rootProject.name = 'jpa-flush-lab'
```

### 8.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

BOM của Boot 3.3.0 cung cấp Hibernate/JPA/Spring Data/JUnit versions tương thích; H2 chỉ được đưa vào **test runtime**. Khi đưa ứng dụng vào production, phải cấu hình datasource/driver production riêng, không coi `bootRun` của lab là deployment hoàn chỉnh.

### 8.4. `FlushLabApplication.java`

**`src/main/java/example/flush/FlushLabApplication.java`:**

```java
package example.flush;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FlushLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(FlushLabApplication.class, args);
    }
}
```

Đặt application/entity/repository/test trong package `example.flush` để Spring Boot slice tìm primary configuration và scan đúng JPA entities/repositories.

### 8.5. `BookingRecord.java`

**`src/main/java/example/flush/BookingRecord.java`:**

```java
package example.flush;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "booking_records",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_booking_code",
                columnNames = "booking_code")
)
@SequenceGenerator(
        name = "booking_id_gen",
        sequenceName = "booking_id_seq",
        allocationSize = 1
)
public class BookingRecord {
    @Id
    @GeneratedValue(
            strategy = GenerationType.SEQUENCE,
            generator = "booking_id_gen")
    private Long id;

    @Column(name = "booking_code", nullable = false, length = 64)
    private String bookingCode;

    @Column(name = "customer_name", nullable = false, length = 100)
    private String customerName;

    protected BookingRecord() {
        // JPA requires a no-args constructor.
    }

    public BookingRecord(String bookingCode, String customerName) {
        this.bookingCode = bookingCode;
        this.customerName = customerName;
    }

    public Long getId() {
        return id;
    }

    public String getBookingCode() {
        return bookingCode;
    }

    public String getCustomerName() {
        return customerName;
    }

    public void changeBookingCode(String newCode) {
        this.bookingCode = newCode;
    }
}
```

Các lựa chọn có chủ đích:

- `@SequenceGenerator` + `GenerationType.SEQUENCE`: có thể lấy ID qua sequence mà chưa INSERT row.
- `uk_booking_code`: database unique constraint, giúp negative tests buộc SQL thất bại.
- `@Column(nullable=false)`: mô tả schema và hỗ trợ provider nullability checks; ví dụ tập trung **unique**, tránh lẫn lỗi Bean Validation/NOT NULL.
- `changeBookingCode(...)`: thay đổi một **managed entity** để Hibernate dirty checking sinh UPDATE ở flush.
- Entity không có `@Version` hay business service, giữ rõ hiện tượng flush.
- Không dự đoán ID luôn là 1; sequence có thể tăng qua các transactions dù rollback.

### 8.6. `BookingRepository.java`

**`src/main/java/example/flush/BookingRepository.java`:**

```java
package example.flush;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookingRepository
        extends JpaRepository<BookingRecord, Long> {

    Optional<BookingRecord> findByBookingCode(String code);
}
```

`JpaRepository` cung cấp `save`, `saveAndFlush`, `flush`, `findById` và `delete`. Derived method `findByBookingCode` giúp kiểm tra dữ liệu sau khi clear persistence context.

## 9. Test runnable: quan sát INSERT và constraint ngay tại flush

**`src/test/java/example/flush/BookingRepositoryFlushTest.java`:**

```java
package example.flush;

import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(
        showSql = false,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop"
)
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY,
        connection = EmbeddedDatabaseConnection.H2
)
class BookingRepositoryFlushTest {
    @Autowired
    BookingRepository repository;

    @Autowired
    EntityManager entityManager;

    @Autowired
    JdbcTemplate jdbc;

    private long rowCount(String code) {
        Long count = jdbc.queryForObject(
                """
                SELECT COUNT(*)
                  FROM booking_records
                 WHERE booking_code = ?
                """,
                Long.class,
                code);

        assertNotNull(count);
        return count;
    }

    @Test
    void sequenceInsertAppearsInJdbcOnlyAfterFlush() {
        BookingRecord pending = new BookingRecord(
                "PENDING-1", "Mai");

        entityManager.persist(pending);

        assertNotNull(pending.getId());

        // Direct JDBC does not ask JPA to auto-flush the context.
        assertEquals(0L, rowCount("PENDING-1"));

        entityManager.flush();

        // Same test transaction sees its executed SQL write.
        assertEquals(1L, rowCount("PENDING-1"));
    }

    @Test
    void repositoryFlushReportsDuplicateUniqueKey() {
        repository.saveAndFlush(
                new BookingRecord("DUP-FLUSH", "Mai"));

        repository.save(
                new BookingRecord("DUP-FLUSH", "An"));

        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.flush());

        // Do not continue querying in a failed transaction.
    }

    @Test
    void saveAndFlushReportsDuplicateAtCallSite() {
        repository.saveAndFlush(
                new BookingRecord("DUP-CALL", "Mai"));

        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(
                        new BookingRecord("DUP-CALL", "An")));
    }

    @Test
    void dirtyCheckingUpdateFailsDuringFlush() {
        repository.saveAndFlush(
                new BookingRecord("CODE-FIRST", "Mai"));

        BookingRecord second = repository.saveAndFlush(
                new BookingRecord("CODE-SECOND", "An"));

        // No repository.save(second) is needed:
        // second is a managed entity in this transaction.
        second.changeBookingCode("CODE-FIRST");

        assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.flush());
    }

    @Test
    void flushThenClearCanReloadDatabaseState() {
        BookingRecord saved = repository.saveAndFlush(
                new BookingRecord("RELOAD-1", "Linh"));

        Long savedId = saved.getId();

        entityManager.clear();

        BookingRecord reloaded = repository
                .findByBookingCode("RELOAD-1")
                .orElseThrow();

        assertEquals(savedId, reloaded.getId());
        assertEquals("Linh", reloaded.getCustomerName());
        assertTrue(rowCount("RELOAD-1") == 1L);
    }
}
```

### 9.1. Kết quả test số 1: `persist` ≠ SQL INSERT đã xuất hiện

`sequenceInsertAppearsInJdbcOnlyAfterFlush` chủ đích dùng:

1. Entity ID `SEQUENCE` để Hibernate có thể nhận ID trước INSERT.
2. `entityManager.persist(pending)`: entity trở thành managed, ID được cấp từ sequence.
3. `JdbcTemplate` truy vấn trực tiếp bảng `booking_records` trong **cùng test-managed transaction**, không gọi JPQL repository query nên không yêu cầu Hibernate auto flush.
4. Trước explicit flush, count kỳ vọng bằng 0 trong cấu hình của lab.
5. `entityManager.flush()` yêu cầu Hibernate gửi INSERT.
6. Sau flush, JDBC trong cùng transaction đọc được row với count bằng 1.
7. Test kết thúc; Spring TestContext rollback, vì vậy row **không được commit**.

**Phạm vi kết luận:** đây là demonstration cho Hibernate/Spring Boot 3.3 + H2 + `SEQUENCE` và transaction bình thường. Không biến nó thành định luật “persist luôn không phát SQL trước flush”. Với `IDENTITY`, provider thường cần INSERT sớm để lấy generated ID.

### 9.2. Kết quả test số 2: Save trước, lỗi tại `flush()`

`repositoryFlushReportsDuplicateUniqueKey`:

- Row thứ nhất `DUP-FLUSH` được `saveAndFlush`, SQL INSERT được thực thi trong transaction nhưng chưa commit.
- Row thứ hai cùng business code được `save` (với SEQUENCE, SQL insert có thể nằm trong action queue).
- `repository.flush()` gửi pending INSERT.
- H2 database phát unique violation, Spring exception translation ở repository proxy thường chuyển thành `DataIntegrityViolationException`.
- `assertThrows` kiểm tra lỗi xảy ra **tại checkpoint flush**, không chờ rollback/test teardown.

Nếu dùng `@GeneratedValue(IDENTITY)`, second `save` có thể phát lỗi sớm khi INSERT để lấy ID. Khi đó assertion bắt lỗi ở flush sẽ không còn ổn định; đó là lý do lab dùng `SEQUENCE`.

### 9.3. Kết quả test số 3: `saveAndFlush` gói hai bước

`saveAndFlushReportsDuplicateAtCallSite` kiểm tra:

```java
assertThrows(
        DataIntegrityViolationException.class,
        () -> repository.saveAndFlush(
                new BookingRecord("DUP-CALL", "An")));
```

Nó thường dễ đọc hơn `save` + `flush` khi muốn gắn lỗi SQL với thao tác save của một entity mới. Nhưng nhớ rằng `saveAndFlush` có thể flush **cả những pending changes khác** trong persistence context, không chỉ entity vừa truyền vào.

### 9.4. Kết quả test số 4: UPDATE do dirty checking

Với entity **managed**, bạn không cần gọi `repository.save(second)` sau mỗi setter:

```java
second.changeBookingCode("CODE-FIRST");
repository.flush();
```

Hibernate dirty checking nhận thấy `bookingCode` thay đổi, sinh SQL UPDATE tại flush. Unique constraint từ chối vì `CODE-FIRST` đã thuộc row thứ nhất. Test chứng minh SQL error không chỉ xuất hiện ở INSERT mà còn có thể ở UPDATE khi state của entity thay đổi.

Lưu ý: gọi setter trên một **detached object** sau `entityManager.clear()` sẽ không tự động xếp UPDATE như managed entity; cần reattach/merge có chủ đích để test.

### 9.5. Kết quả test số 5: Flush rồi clear để kiểm tra thật

`entityManager.clear()` loại managed entities khỏi first-level cache. Repository sau đó query theo business code để load lại một entity. Kết hợp `flush` và `clear` giúp tránh test chỉ kiểm tra object Java trong memory.

Tuy nhiên, ở một ứng dụng có second-level cache hoặc custom query cache, cần kiểm tra cấu hình cache nếu mục tiêu là chứng minh round-trip SQL cụ thể.

### 9.6. Vì sao có cả `EntityManager.flush()` và `JpaRepository.flush()`?

- `EntityManager.flush()` là JPA API trực tiếp. Exception thường là JPA/Hibernate exception hoặc wrapper phù hợp, không nhất thiết cùng type với repository exception.
- `JpaRepository.flush()` là lời gọi qua Spring Data repository proxy, có cơ chế exception translation của Spring; test thường có thể assert `DataIntegrityViolationException`.
- `TestEntityManager.flush()`/`persistAndFlush()` thuận tiện trong `@DataJpaTest`, nhưng không nên mặc định exception type luôn giống repository proxy ở mọi đường gọi.

Lab dùng `EntityManager` trong test “quan sát SQL”, còn negative tests dùng `JpaRepository.flush()` để có Spring data-access exception phù hợp.

## 10. Chạy toàn bộ ví dụ

Với JDK 17, Gradle Wrapper tương thích (ví dụ Gradle 8.5) và dependencies tải được:

```bash
./gradlew test
./gradlew test --tests example.flush.BookingRepositoryFlushTest
./gradlew test --tests example.flush.BookingRepositoryFlushTest.sequenceInsertAppearsInJdbcOnlyAfterFlush
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.flush.BookingRepositoryFlushTest
```

Dự kiến **5 phương thức test pass** trong class này nếu có đúng JDK/Gradle/dependencies. Các negative tests **pass khi exception đúng được bắt bởi `assertThrows`**. Không có stdout nghiệp vụ cố định; Gradle thường báo `BUILD SUCCESSFUL` khi tasks thành công.

**Không khẳng định các test đã được thực thi trong bài viết này**: kết quả là expected behavior cho ví dụ code. Trong project thật, nên chạy tại CI để xác nhận Hibernate/H2 versions đang sử dụng.

### 10.1. Đọc log SQL khi cần

Bài mẫu đặt `showSql=false` để log gọn. Khi debug, có thể bật trong test configuration:

```properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Đây là cấu hình **tham khảo** cho Hibernate 6 trong Boot 3.3. Không bật bind logging trên môi trường có password/PII hoặc secrets, vì bound parameter logs có thể chứa dữ liệu nhạy cảm. Tên logger khác nhau giữa các phiên bản Hibernate.

Khi bật log, quan sát trình tự:

```text
select next value for booking_id_seq
...   (chưa có insert booking_records, ở checkpoint trước flush)
insert into booking_records ...
...   (ở flush)
```

Đây là **minh họa thứ tự SQL**, không phải stdout chính xác: tên SQL expression, cú pháp sequence, bind parameters và số lượng statements phụ thuộc Hibernate dialect/config.

## 11. Bẫy `GenerationType.IDENTITY`: INSERT có thể chạy sớm

Một ví dụ thường gây hiểu lầm:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Với `IDENTITY`, database phát sinh ID khi INSERT. Hibernate thường cần gửi INSERT ngay trong `persist`/`save` để biết ID, nhất là khi transaction đang active và không có deferred identity mode.

Vì vậy test:

```java
repository.save(duplicateEntity);
assertThrows(
        DataIntegrityViolationException.class,
        repository::flush);
```

có thể **fail tại dòng save trước khi tới assertThrows**. Không phải bug của `flush()`; đó là ID generator ảnh hưởng thời điểm SQL.

**Cách viết test tốt:**

- Nếu muốn test **database từ chối duplicate**, dùng `assertThrows(..., () -> repository.saveAndFlush(...))`; với một số IDENTITY provider, exception vẫn có thể nổ trong save bên trong lambda nên được bắt.
- Nếu muốn minh họa **SQL deferred to flush**, chọn `SEQUENCE` hoặc một chiến lược/provider đảm bảo thao tác tương ứng có thể chờ flush.
- Không khẳng định tuyệt đối “JPA luôn flush SQL chỉ khi commit” hay “save không bao giờ chạm DB”.

## 12. Unique/NOT NULL và khác biệt ORM validation

Một trường:

```java
@Column(nullable = false)
private String customerName;
```

có thể làm Hibernate kiểm tra nullability **trước khi** phát SQL INSERT. Nếu test truyền null và thấy exception, đừng gọi ngay đó là lỗi NOT NULL **từ database**. Cần xem root cause/log SQL và đúng phase.

Nếu dùng Jakarta Bean Validation:

```java
@NotBlank
@Column(nullable = false)
private String customerName;
```

đoạn snippet cần dependency `spring-boot-starter-validation` và import `jakarta.validation.constraints.NotBlank`. Bean Validation có thể chạy ở lifecycle callback như pre-persist/pre-update, từ chối entity trước SQL.

Vì mục tiêu chính của bài là **lỗi SQL tại flush**, runnable test dùng **unique constraint thực ở H2** thay vì chỉ assert validation annotation.

### 12.1. Column length

`@Column(length=64)` thường được Hibernate dùng để tạo DDL. Việc DB từ chối chuỗi dài quá 64 phụ thuộc engine/schema thực và validation/provider. Không xem một H2 test thành bằng chứng hoàn chỉnh rằng MySQL/PostgreSQL xử lý Unicode/string length giống nhau.

### 12.2. Foreign key constraints

Khi entity có `@ManyToOne` với foreign key, một insert/reference sai có thể phát lỗi khi SQL được flush. Nhưng:

- ORM có thể sắp thứ tự INSERTs để giữ FK đúng.
- Cascades có thể tự persist referenced entity.
- Một số DB cho phép deferred foreign keys chỉ check ở commit.
- H2, PostgreSQL và MySQL khác nhau về DDL/constraint enforcement.

Nếu FK là invariant quan trọng, test trên database vendor thật với cấu hình FK production và assert lỗi tại checkpoint hợp lý.

## 13. PostgreSQL deferred constraints: flush chưa chắc là đủ

Đây là caveat bắt buộc khi nói về lỗi SQL. PostgreSQL hỗ trợ constraints `DEFERRABLE INITIALLY DEFERRED`. Với một unique constraint được defer đến cuối transaction, việc gọi `flush` có thể **gửi INSERT/UPDATE thành công** nhưng constraint chỉ bị kiểm tra **khi COMMIT**.

Ví dụ SQL **PostgreSQL-only**, không chạy trên H2 lab:

```sql
CREATE TABLE reservation_codes (
    id bigint PRIMARY KEY,
    public_code text NOT NULL,
    CONSTRAINT uk_reservation_codes
        UNIQUE (public_code)
        DEFERRABLE INITIALLY DEFERRED
);
```

Trong transaction:

```sql
BEGIN;
INSERT INTO reservation_codes(id, public_code)
VALUES (1, 'DUP');
INSERT INTO reservation_codes(id, public_code)
VALUES (2, 'DUP');

-- Cả hai statements có thể hoàn tất
-- khi unique constraint đang deferred.
COMMIT;  -- Violation được phát hiện tại đây.
```

**Không tuyên bố `flush()` bắt được mọi lỗi SQL.** Nó thường buộc statement execution, nhưng điểm kiểm tra constraint còn phụ thuộc DB DDL. Với constraints deferred, cần test transaction **commit thật** hoặc chuyển constraint sang IMMEDIATE trong transaction test khi hợp đồng cho phép.

Ví dụ PostgreSQL:

```sql
SET CONSTRAINTS uk_reservation_codes IMMEDIATE;
```

Lệnh này yêu cầu PostgreSQL kiểm tra deferred constraint ngay khi chuyển mode; nó có thể fail nếu dữ liệu đang vi phạm. Không coi nó là lệnh JPA portable. Nếu bạn cần bảo vệ behavior ở commit, test vendor-specific sẽ chính xác hơn H2.

### 13.1. Tại sao TestTransaction quan trọng?

Spring Test hỗ trợ `TestTransaction` cho test-managed transaction, ví dụ điều khiển explicit commit:

```java
repository.saveAndFlush(
        new BookingRecord("COMMIT-1", "Mai"));

TestTransaction.flagForCommit();
TestTransaction.end();

// Test-managed transaction đã kết thúc.
// Dữ liệu có thể đã commit; cần cleanup riêng.
```

**Đây là snippet nâng cao, không phải code trong class runnable ở mục 9.** Cần import `org.springframework.test.context.transaction.TestTransaction` và một test đang thực sự chạy trong test-managed transaction. Khi commit thật, dữ liệu không còn được rollback tự động sau test như before; cần database ephemeral/cleanup có kiểm soát.

Đối với một transaction commit ném exception, test harness có thể cần bao quanh `TestTransaction.end()` trong `assertThrows` và đảm bảo transaction reset/cleanup tương ứng. Đừng tiếp tục chạy SQL trong transaction đã thất bại.

## 14. Flush không commit: visibility trong transaction khác

Sau `flush`, JDBC cùng transaction có thể nhìn thấy các rows vừa được viết. Nhưng với isolation thông thường như `READ_COMMITTED`, một connection ở **transaction khác** chưa được nhìn thấy những rows đó cho đến commit.

```text
Transaction T1                      Transaction T2
--------------                      --------------
persist(row)
flush() -> INSERT đã chạy
                                    SELECT row -> chưa thấy
commit()
                                    SELECT row -> thấy sau commit
```

Đây là **sơ đồ tư duy** trong điều kiện isolation READ_COMMITTED và không có các behavior đặc biệt; mức isolation/snapshot/locking có thể thay đổi kết quả quan sát. Một test chỉ query bằng cùng `EntityManager` sau flush không chứng minh một transaction khác sẽ đọc được dữ liệu.

Khi nghiệp vụ yêu cầu visibility sau commit:

- Dùng một commit thật trong test được cô lập.
- Mở transaction/connection thứ hai với isolation đúng mục tiêu.
- Quan sát trạng thái ở transaction thứ hai.
- Cleanup dữ liệu đã commit.
- Nếu cần concurrency/deadlock/locking, dùng synchronization primitives thay cho sleep cố định.

**Không tự suy luận từ `flush()` rằng API HTTP khác đã thấy row.**

## 15. @DataJpaTest vs @SpringBootTest: transactions và server side effects

### 15.1. @DataJpaTest

Trong ví dụ, `@DataJpaTest`:

- Tạo Spring JPA slice.
- Cấp test-managed transaction mỗi method theo mặc định.
- Rollback sau method.
- Không mở HTTP server.
- Có thể dùng embedded H2 database.

Test flush giúp đánh giá SQL trước khi rollback.

### 15.2. @SpringBootTest với MockMvc

Với:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
@Transactional
class BookingMockHttpTest {
    // MockMvc request thường chạy trong test thread
    // và có thể tham gia test-managed transaction.
}
```

Đây là snippet cấu hình, không phải test class runnable của lab. Với synchronous MockMvc request, controller/service repository có thể chạy trong transaction của test. Nhưng nếu code tạo async thread hoặc `REQUIRES_NEW` transaction, những side effects đó có thể nằm ngoài rollback.

### 15.3. @SpringBootTest RANDOM_PORT

Với:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class BookingLiveHttpTest {
    // Test client gửi HTTP qua socket tới server thread.
}
```

Server request thường chạy trên thread/transaction khác với JUnit method. `@Transactional` ở test thread **không tự rollback** các DB commits do HTTP request server-side. Phải cleanup dữ liệu theo luồng integration.

Nếu service gọi `flush()` rồi trả HTTP 201, transaction commit có thể vẫn fail ở thời điểm sau flush do deferred constraint hoặc logic commit; HTTP test cần kiểm tra status/state sau request thật, không chỉ unit assertion trong service.

## 16. Spring exception translation và vị trí đặt assertThrows

Khi Hibernate/JDBC phát unique constraint violation:

- JDBC có thể ném `SQLException` hoặc subclass vendor-specific.
- Hibernate có thể wrap thành `org.hibernate.exception.ConstraintViolationException`.
- JPA có thể wrap trong `jakarta.persistence.PersistenceException`.
- Spring Data `@Repository` proxy có cơ chế exception translation, thường chuyển thành `org.springframework.dao.DataIntegrityViolationException`.
- Trong một số trường hợp, lỗi xuất hiện ở transaction commit thay vì repository method nên wrapper/type và stack location có thể khác.

Ví dụ test ổn định khi dùng repository proxy:

```java
assertThrows(
        DataIntegrityViolationException.class,
        () -> repository.saveAndFlush(
                new BookingRecord("DUP-CALL", "An")));
```

Nếu gọi `entityManager.flush()` trực tiếp thay vì qua repository, cần hiểu **type exception khác**. Không copy `assertThrows(DataIntegrityViolationException.class, entityManager::flush)` rồi coi thất bại là vì DB không enforce unique constraint.

### 16.1. Không bắt quá rộng

```java
assertThrows(Exception.class, () -> repository.flush());
```

Có thể pass vì một lỗi bất kỳ — thậm chí lỗi cấu hình/connection. Với test constraint, assert Spring data exception phù hợp rồi, nếu cần, kiểm tra root cause/constraint name một cách không giòn.

### 16.2. Vì sao không bắt Exception rồi tiếp tục sử dụng transaction?

Sau một constraint violation:

- Hibernate Session/persistence context có thể không còn phù hợp để tiếp tục sử dụng.
- PostgreSQL đánh dấu transaction bị aborted; các SQL tiếp theo có thể bị từ chối cho đến rollback.
- Spring transaction interceptor có thể đánh dấu rollback-only.
- Test code tiếp tục thực thi SQL có thể tạo lỗi thứ cấp và che nguyên nhân ban đầu.

**Cách an toàn:** trong một negative test, chỉ setup fixture, thực hiện action gây lỗi, assert exception, rồi kết thúc method để Spring rollback. Không cố “sửa” entity trong cùng transaction sau exception và tiếp tục kiểm tra như bình thường.

## 17. Flush giúp debug test, nhưng không phải một công cụ validation tổng quát

Có những lỗi không được phát hiện bằng flush:

- HTTP content negotiation hoặc JSON serialization sai.
- Business rule mà service không implement.
- Async event chưa được gửi.
- External HTTP gateway failure.
- Database trigger chạy lúc commit hoặc constraint deferred.
- Transaction commit timeout/serialization conflict chỉ phát khi commit.
- Dữ liệu persistence được ghi đúng nhưng API response sai.
- Domain validation không được kích hoạt.

Test nên được phân tầng: unit cho rule Java, JPA slice cho mapping/SQL, full integration cho transaction/service/HTTP/external effects khi cần. Đừng dùng `repository.flush()` như chiếc “nút test mọi thứ”.

## 18. Hibernate batching và hiệu năng

Hibernate có thể batch JDBC statements khi cấu hình `hibernate.jdbc.batch_size`. Điều này có thể thay đổi thời điểm gửi SQL thực và lỗi:

- Nhiều pending INSERTs có thể được gửi cùng một flush.
- Một lỗi ở giữa batch có thể làm whole batch fail.
- Stack trace có thể chỉ vào `BatchUpdateException` hoặc SQL batch processing.
- Ordering của SQL có thể khác thứ tự Java gọi `persist`.
- `IDENTITY` ID generation thường hạn chế JDBC insert batching vì cần generated keys.

Với test correctness:

1. Tạo fixture tối thiểu.
2. Gọi flush tại checkpoint.
3. Assert invariant/exceptions.
4. Không assert thứ tự SQL statements nếu contract không yêu cầu.
5. Nếu phải test batching performance, dùng test riêng với log/metrics và data volume phù hợp.

Trong production, **không** thêm flush sau mỗi save chỉ để test pass. Làm thế có thể phá batching và làm tăng round trips.

## 19. Bulk JPQL update/delete và persistence context

Spring Data JPA `@Modifying` queries hay `deleteAllInBatch` có thể bypass normal dirty checking/persistence context synchronization. Ví dụ:

```java
@Modifying(
        flushAutomatically = true,
        clearAutomatically = true
)
@Query(
        "update BookingRecord b " +
        "set b.customerName = :name " +
        "where b.bookingCode = :code"
)
int updateCustomerName(
        @Param("code") String code,
        @Param("name") String name);
```

Đây là **repository method snippet** cho phần mở rộng, không thuộc interface runnable ở mục 8. Cần imports Spring Data `@Modifying`, `@Query`, `@Param` và transaction phù hợp.

- `flushAutomatically=true` yêu cầu flush pending changes trước query.
- `clearAutomatically=true` clear persistence context sau modifying query để tránh managed entities stale.
- Bulk update có thể bỏ qua JPA entity callbacks/dirty checking behavior của từng instance.
- Clear khi có unflushed changes có thể làm mất changes; vì vậy cấu hình các flags có chủ đích.

Test bulk mutation cần đối chiếu DB state sau flush/clear và biết rằng `@Modifying` không đồng nghĩa commit.

### 19.1. Delete ordering và FK

Một test tạo parent/child rồi gọi delete có thể gặp FK violation tại flush nếu cascade/orphan removal/ordering không đúng. Hibernate cố sắp hành động hợp lệ nhưng chỉ có database thật mới enforce constraint cuối cùng. Với DB có deferred FK, lỗi có thể bị trì hoãn đến commit.

## 20. Nếu muốn test trên PostgreSQL thật

H2 rất tiện cho lab, nhưng không thay PostgreSQL về:

- Deferred constraints.
- SQL dialect/indexes.
- Timestamp/precision/collation.
- Foreign key/unique/partial index behavior.
- Transaction isolation/locking/deadlocks.
- Trigger execution.
- Serialization failures khi commit.
- Error codes/wrapping theo driver.

Khi test yêu cầu vendor-specific behavior, dùng PostgreSQL Testcontainers hoặc một test database thật được cô lập. Với Spring Boot 3.3, `@DataJpaTest` có thể thay test datasource bằng H2 nếu không cấu hình replacement rõ.

Mẫu **minh họa** khi có PostgreSQL Testcontainers và dependency phù hợp:

```java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class BookingPostgresTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Đoạn này **không có trong project runnable ở mục 8**, cần `spring-boot-testcontainers`, Testcontainers PostgreSQL/JUnit Jupiter, PostgreSQL JDBC driver, Docker và các imports đúng. Khi có container, vẫn phải assert actual database product name để tránh pass nhầm H2; đồng thời chạy schema/migrations thực nếu đó là mục tiêu.

**Không** gắn `replace=NONE` trong CI khi datasource có thể vô tình trỏ production; chỉ dùng với test credentials/URI an toàn.

## 21. Hai kiểu test khác nhau: constraint hiện tại và commit-time constraint

### Kiểu A — constraint check ở SQL execution/flush

```java
repository.saveAndFlush(existing);
assertThrows(
        DataIntegrityViolationException.class,
        () -> repository.saveAndFlush(duplicate));
```

Điều này thích hợp với nhiều NOT DEFERRABLE unique/FK/CHECK constraints được database kiểm tra ở statement execution.

### Kiểu B — constraint chỉ check ở commit

```text
BEGIN
  INSERT row 1
  INSERT row 2 gây duplicate dưới deferred unique
  FLUSH: SQL đã được gửi, constraint vẫn có thể chưa fail
COMMIT: database kiểm tra deferred unique và phát lỗi
```

Trường hợp này cần **thực hiện commit** trong môi trường database phù hợp. Nếu test mặc định rollback, test có thể không đi qua mốc constraint được đánh giá. H2 demo không thay thế được PostgreSQL DEFERRABLE test.

### 21.1. TestTransaction với @AfterTransaction

Spring Test có callback `@AfterTransaction` để quan sát trạng thái sau khi kết thúc test-managed transaction. Nhưng callback này không tự biến một transaction rollback thành commit; nó chỉ chạy sau khi transaction đã kết thúc. Muốn kiểm tra committed visibility phải chủ động cấu hình commit hoặc điều khiển `TestTransaction`, sau đó cleanup.

**Không** dùng `@Commit` hoặc `@Rollback(false)` đại trà trong shared test database: chúng có thể để lại dữ liệu qua các test methods.

## 22. Debug flush bằng một phép đo đơn giản

Khi nghi một negative test xanh sai do chưa chạy SQL, đặt ba câu hỏi:

1. Entity đang managed, detached hay transient?
2. SQL đã thực thi chưa? Vì IDENTITY, JPQL query hoặc JDBC call nào đã trigger flush?
3. Constraint được DB kiểm tra tại statement execution hay commit?

Có thể tổ chức test theo kiểu:

```java
// ARRANGE: tạo dữ liệu đúng trước.
repository.saveAndFlush(existing);

// ACT + ASSERT: buộc DB đánh giá dữ liệu vi phạm.
assertThrows(DataIntegrityViolationException.class,
        () -> repository.saveAndFlush(duplicate));

// Kết thúc test, để framework rollback.
```

Đây là code pattern, không phải class độc lập. Nó dễ review hơn một test lưu hàng loạt rồi chỉ assert object count mà không biết SQL đã được gửi.

### 22.1. Đọc root cause

Nếu error message là `constraint violation`, kiểm tra:

- Constraint name từ schema/migration.
- SQL statement nào đang chạy.
- JDBC vendor error code/SQLState.
- Exception wrapper ở repository/JPA.
- Dữ liệu fixture nào làm duplicate/invalid.
- Transaction isolation và DDL deferred status.

Không đổi expected exception sang `RuntimeException` chỉ để test xanh.

### 22.2. Lỗi khi schema chưa có

Nếu test fail `Table not found`, nguyên nhân có thể là `ddl-auto`/Flyway/Liquibase chưa tạo schema, không phải do flush “sai”. Bài mẫu dùng `spring.jpa.hibernate.ddl-auto=create-drop` trên H2 ephemeral để tạo bảng/unique constraint. Đừng copy `create-drop` sang database có dữ liệu cần giữ.

### 22.3. Khi lỗi “Transaction is marked rollback-only”

Một negative test đã gây SQL exception, transaction có thể bị đánh dấu rollback-only. Khi có thêm repository operation sau `assertThrows`, bạn có thể nhận `UnexpectedRollbackException` hoặc lỗi driver khác. Hãy dừng method sau assertion và để test-managed rollback xử lý.

## 23. Các anti-pattern đáng tránh

### 23.1. Assert object trả về từ save là đủ

`assertNotNull(repository.save(entity))` không chứng minh SQL đã được database chấp nhận. Thêm explicit flush và assertion database invariant khi SQL là mục tiêu.

### 23.2. Coi flush là commit

`repository.flush()` **không** bảo đảm durability/visibility ngoài transaction. Để test committed data, cần commit thực và transaction/connection độc lập.

### 23.3. Coi flush luôn là chỗ nổ exception

Với `IDENTITY` SQL có thể chạy trong `save`; với deferred constraint lỗi có thể phát tại commit. Thiết kế test theo actual behavior của generator/database.

### 23.4. Bắt mọi Exception

`assertThrows(Exception.class, ... )` quá rộng: test có thể xanh vì missing table, null pointer hoặc network failure. Khi có thể, assert `DataIntegrityViolationException`/invariant có ý nghĩa.

### 23.5. Sau lỗi SQL lại tiếp tục query

Đây là tình trạng không an toàn với Hibernate persistence context và PostgreSQL aborted transactions. Kết thúc negative test, để rollback, dùng test khác cho thao tác tiếp theo.

### 23.6. Bật readOnly rồi mong dirty changes được lưu

`@Transactional(readOnly=true)` là optimization hint với behavior provider-specific. Test write phải dùng transaction có thể ghi và SQL flush phù hợp.

### 23.7. Dùng flush sau từng save trong production

Thường phá JDBC batching/tăng latency. Chỉ dùng nơi có yêu cầu kỹ thuật rõ, không copy mọi flush của test sang business service.

### 23.8. Dùng H2 để bảo đảm deferred PostgreSQL constraint

H2 không tái hiện đầy đủ PostgreSQL DEFERRABLE behavior. Test vendor-specific tại PostgreSQL.

### 23.9. Dùng @DirtiesContext để rollback

`@DirtiesContext` loại application context khỏi cache, không tự undo committed rows của database. Dùng transactions/cleanup hoặc database ephemeral.

## 24. Bảng chẩn đoán nhanh

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Save không lỗi nhưng flush lỗi unique | INSERT được hoãn | Assert tại flush, test DB unique constraint |
| Save đã ném unique violation | IDENTITY hoặc auto flush sớm | Bọc đúng call site, không mặc định lỗi chỉ ở flush |
| Negative test pass dù không có SQL log | Có thể chưa flush, hoặc log bị tắt | Flush explicit, kiểm tra DB/log khi cần |
| `flush` không ném lỗi nhưng commit lỗi | Deferred constraints/commit-time checks | Test commit với vendor DB, cleanup |
| `entityManager.flush()` ném Hibernate exception | Đi trực tiếp JPA API | Phân biệt với Spring repository exception translation |
| `repository.flush()` ném `DataIntegrityViolationException` | SQL constraint bị từ chối | Assert type/root cause hợp đồng |
| `EntityManager.clear()` làm mất thay đổi | Đã clear trước flush hoặc detached state | Flush trước clear nếu muốn giữ thay đổi |
| Query trước flush đã thấy dữ liệu | Hibernate AUTO flush hoặc first-level cache | Không suy luận SQL timing từ một query JPA |
| JDBC query cùng transaction thấy row sau flush | SQL đã được gửi nhưng chưa commit | Đúng dự kiến; kiểm tra transaction khác nếu cần visibility |
| Test rollback nhưng ID tăng giữa runs | Sequence/identity counters không nhất thiết rollback | Không assert ID cố định |
| Test H2 pass nhưng PostgreSQL fail | Dialect/constraints/isolation khác | Dùng PostgreSQL Testcontainers |
| Test fail `Table not found` | Schema/migration thiếu | Kiểm tra `ddl-auto`/migrations |
| Test fail chỉ khi chạy suite | Shared state/context/transaction | Unique fixtures, rollback/cleanup |
| Spring Boot slice thiếu service | `@DataJpaTest` không scan service thường | `@Import` nhỏ hoặc full context |
| Test HTTP RANDOM_PORT còn data sau run | Server transaction khác JUnit transaction | Dọn committed rows, không trông chờ rollback test thread |

## 25. Bài tập thực hành

### Bài 1 — Quan sát pending INSERT

Chạy `sequenceInsertAppearsInJdbcOnlyAfterFlush`. Đặt log trước/after flush và so sánh JDBC count 0→1. Giải thích vì sao `pending.getId() != null` không chứng minh row đã được INSERT.

### Bài 2 — Bỏ flush có chủ đích

Trong test duplicate, tạm bỏ `repository.flush()` và chỉ assert hai Java objects. Test còn buộc DB đánh giá unique constraint không? Sửa bằng `saveAndFlush` hoặc explicit flush trước khi kết thúc.

### Bài 3 — Đổi SEQUENCE thành IDENTITY

Tạo nhánh riêng, đổi `GenerationType.SEQUENCE` thành `IDENTITY` và chạy test quan sát INSERT timing. Trường hợp `assertEquals(0, rowCount(...))` có thể đỏ vì INSERT chạy sớm. Giải thích tại sao test phải phù hợp generator strategy.

### Bài 4 — Lỗi UPDATE, không chỉ INSERT

Chạy `dirtyCheckingUpdateFailsDuringFlush`. Thử bỏ dòng `second.changeBookingCode("CODE-FIRST")`; flush còn lỗi unique không? Thử `entityManager.clear()` trước setter rồi phân tích managed/detached difference.

### Bài 5 — Flush không commit

Trong một test nâng cao dùng H2 READ_COMMITTED, thử query từ transaction thứ hai trước và sau commit của transaction thứ nhất. Assert visibility phù hợp isolation, cleanup. Không dùng cùng EntityManager cho cả hai và gọi đó là kiểm tra inter-transaction.

### Bài 6 — Constraint PostgreSQL deferred

Trong PostgreSQL container, tạo `DEFERRABLE INITIALLY DEFERRED` unique constraint. Insert hai rows trùng code, explicit flush, rồi commit. Xác định lỗi phát ở phase nào. Không kỳ vọng H2 tái hiện.

### Bài 7 — Truy vấn tự flush

Dùng Hibernate AUTO và một JPQL query cùng bảng sau `persist`. So sánh với một JdbcTemplate query trước explicit flush trong test SEQUENCE. Giải thích tại sao không dựa vào JPA query để đo SQL timing một cách tuyệt đối.

### Bài 8 — Bean Validation vs SQL

Thêm `@NotBlank` cho `customerName` và starter validation. Test input blank/null; đọc root cause để phân biệt validation violation trước SQL với database unique violation.

### Bài 9 — Batch operations

Chèn nhiều entities qua `saveAll` rồi `flush`, bật Hibernate batch size trong môi trường thử nghiệm. Quan sát SQL logs/batch behavior. Đừng giả định thứ tự từng INSERT giống thứ tự Java gọi.

### Bài 10 — Full integration với Spring Boot

Tạo service tạo booking trong `@Transactional` rồi controller POST endpoint. Dùng `@SpringBootTest(MOCK)`/MockMvc cho logic HTTP và JPA, sau đó một `RANDOM_PORT` live test để xác minh commit và data visibility sau response. Cleanup riêng cho live test server-side writes.

## 26. Checklist để review một test SQL constraint

- [ ] Tôi hiểu test đang dùng `@DataJpaTest` rollback mặc định hay có commit thật.
- [ ] Tôi biết entity mới/cũ và persistence context managed/detached state.
- [ ] Tôi phân biệt `save`/`persist`, flush và commit.
- [ ] Test SQL constraint có explicit flush ở checkpoint hữu ích.
- [ ] Không dùng `assertNotNull(save(...))` làm bằng chứng SQL đã được kiểm tra.
- [ ] ID generation strategy được xem xét: `SEQUENCE` khác `IDENTITY` về timing.
- [ ] Khi cần đọc từ DB, có flush/clear/reload hoặc JDBC direct query phù hợp.
- [ ] Tôi không kết luận flush đã commit hoặc transaction khác đã thấy dữ liệu.
- [ ] Tôi biết AUTO query có thể kích hoạt flush sớm.
- [ ] Negative test bắt exception đủ cụ thể, không bắt mọi `Exception`.
- [ ] Tôi không query thêm trong transaction sau SQL failure.
- [ ] Test database có constraint/schema thật phù hợp production contract.
- [ ] Nếu DB dùng deferred constraints, có test commit thật.
- [ ] Test không vô tình truy cập production database hoặc chạy `create-drop` ngoài sandbox.
- [ ] Nếu test dùng H2, tôi không suy luận PostgreSQL-specific behavior.
- [ ] Không thêm flush khắp production code chỉ để test “nhìn thấy SQL”.
- [ ] Với bulk update/delete, flush/clear và persistence context được xử lý có chủ đích.
- [ ] Với live HTTP server, không dựa vào JUnit test transaction để rollback server writes.
- [ ] Bài test có cả positive fixture và negative fixture hợp lý.
- [ ] Kết quả expected dựa vào database invariant, không lệ thuộc SQL log text.

## 27. Sơ đồ quyết định

```text
Cần kiểm tra gì?
     |
     +-- Business logic Java?
     |     -> JUnit thuần / Mockito, không cần database.
     |
     +-- Repository mapping, SQL constraint?
     |     -> @DataJpaTest + test DB.
     |        save/persist -> explicit flush -> assert.
     |
     +-- SQL timing cụ thể?
     |     -> Xét SEQUENCE vs IDENTITY, AUTO flush, batching.
     |        Dùng JDBC direct observation khi phù hợp.
     |
     +-- Deferred constraint / dữ liệu đã commit?
     |     -> Vendor DB + commit thật + cleanup.
     |
     +-- HTTP request + service transaction + persistence?
           -> @SpringBootTest phù hợp và test DB cô lập;
              RANDOM_PORT khi cần network thật.
```

**Thông điệp cốt lõi:** Trong một JPA test có rollback, **`save()` chưa bảo đảm SQL đã chạy**. Gọi **`flush()` hoặc `saveAndFlush()` tại checkpoint** giúp buộc Hibernate đồng bộ pending changes xuống database để nhiều lỗi constraint/SQL xuất hiện ngay trong body của test. Nhưng **flush không phải commit**, không thay thế test deferred constraints, transaction visibility, hoặc production database behavior. Cách test đúng là nêu rõ điều cần quan sát, chủ động flush khi cần và sử dụng đúng engine/transaction boundary.

## 28. Tài liệu chính thức

- Spring Boot 3.3 — `@DataJpaTest`, transaction rollback mặc định: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Framework — TestContext transaction management, `TestTransaction`, rollback: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Spring Data JPA — `JpaRepository.flush`, `saveAndFlush` Javadoc: https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html
- Hibernate ORM 6 — Flushing, AUTO/COMMIT/MANUAL, IDENTITY timing: https://docs.jboss.org/hibernate/orm/6.5/userguide/html_single/Hibernate_User_Guide.html
- Jakarta Persistence 3.1 — EntityManager `flush`/`FlushModeType`: https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/entitymanager
- Spring Data JPA — Transactions: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- Spring Data JPA — Modifying queries and clearAutomatically/flushAutomatically: https://docs.spring.io/spring-data/jpa/reference/jpa/modifying-queries.html
- PostgreSQL — SET CONSTRAINTS and deferred checking: https://www.postgresql.org/docs/current/sql-set-constraints.html
- PostgreSQL — CREATE TABLE unique/foreign key deferrable: https://www.postgresql.org/docs/current/sql-createtable.html
- JUnit Jupiter — Assertions and lifecycle: https://docs.junit.org/current/user-guide/
