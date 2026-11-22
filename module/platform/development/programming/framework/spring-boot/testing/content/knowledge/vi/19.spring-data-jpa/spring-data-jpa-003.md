# TestEntityManager với persist, flush, clear và find

## 1. Mục tiêu bài học

Khi kiểm thử Spring Data JPA, một bài test có thể PASS dù dữ liệu **chưa được đồng bộ xuống database**. Nguyên nhân là JPA quản lý các entity trong một **persistence context (first-level cache)**. Một lệnh `find` có thể trả ngay chính object đang được quản lý, thay vì đọc lại trạng thái thực sự đã được database nhận.

`TestEntityManager` là công cụ của Spring Boot Test giúp dựng dữ liệu JPA và thực hiện các thao tác `persist`, `flush`, `clear`, `find` ngắn gọn. Đặc biệt, kết hợp:

```java
BookEntity saved = testEntityManager.persist(
        new BookEntity("ISBN-001", "Spring Data JPA"));
testEntityManager.flush();
testEntityManager.clear();
BookEntity reloaded = testEntityManager.find(
        BookEntity.class, saved.getId());
```

giúp bạn kiểm tra rằng entity có thể được lấy lại **sau khi persistence context cấp một đã bị xóa**. Chuỗi này **không phải commit**: trong `@DataJpaTest`, test vẫn thường nằm trong transaction được rollback sau khi method hoàn tất.

Bài học thuộc nhóm **Spring Data JPA**, với đề mục trực tiếp **“TestEntityManager với persist, flush, clear và find”**. Chúng ta sẽ tìm hiểu:

- Entity lifecycle: transient/new → managed → detached; khác biệt với removed.
- `persist` làm gì, khi nào ID có giá trị, vì sao ID generation strategy quan trọng.
- `flush` đồng bộ các thay đổi với database trong transaction hiện tại, nhưng **không commit**.
- `clear` detaches toàn bộ entities khỏi first-level cache; unflushed changes có thể mất.
- `find` tra cứu theo khóa chính và có thể lấy từ first-level cache nếu chưa clear.
- Helper methods `persistAndFlush`, `persistAndGetId`, `persistFlushFind`: công dụng và những giới hạn cần hiểu đúng.
- Viết test với `@DataJpaTest`, H2 và JUnit Jupiter; xác nhận thông qua repository, JPA và JDBC khi thích hợp.
- Những bẫy về auto flush, dirty checking, unique constraints, transaction rollback, Hibernate-specific behavior và cơ sở dữ liệu thật.

**Phiên bản minh họa:** Java 17+, Spring Boot **3.3.5**, Spring Data JPA/Hibernate 6 và H2. API `TestEntityManager` dùng trong ví dụ thuộc package `org.springframework.boot.test.autoconfigure.orm.jpa` của Boot 3.3; không copy package được đổi ở Boot 4 vào project Boot 3.3.

## 2. Vì sao có TestEntityManager?

Spring Boot `@DataJpaTest` tạo một application context **tập trung vào persistence**: JPA entities, Spring Data repositories, `EntityManager`, DataSource và thành phần liên quan. Khi embedded database như H2 có trên test runtime classpath, test thường được cấu hình chạy trên database đó.

`TestEntityManager` cung cấp một API nhỏ, phù hợp dựng fixture nhanh:

```java
@Autowired
TestEntityManager testEntityManager;
```

Nó không phải một JPA implementation khác. Phần lớn methods chỉ delegate tới một `jakarta.persistence.EntityManager` thực tế do framework quản lý. `getEntityManager()` cho phép truy cập toàn bộ JPA API khi cần.

Dưới `@DataJpaTest`, transaction được mở cho test method theo mặc định, rồi **rollback khi test kết thúc**. Nhờ đó việc tạo dữ liệu test thường không để lại hàng mới trong database giữa các test. Nhưng database-specific side effects như **sequence values** không nhất thiết rollback; đừng assert entity ID đầu tiên luôn là `1`.

### TestEntityManager khác Spring Data Repository

| Công cụ | Trách nhiệm | Khi dùng |
| --- | --- | --- |
| `TestEntityManager` | Chuẩn bị/dò trạng thái JPA, ép flush, clear, find theo ID | Repository tests, mapping tests, constraint tests |
| `EntityManager` | JPA persistence context và API chuẩn đầy đủ | Query, lock, entity lifecycle, criteria, refresh |
| `JpaRepository<T,ID>` | Abstraction truy vấn và persistence của ứng dụng | Kiểm thử logic repository, derived queries |
| `JdbcTemplate` | Thực thi SQL trực tiếp, không đọc qua JPA first-level cache | Kiểm tra hàng DB sau flush trong cùng transaction |
| `@DataJpaTest` | Tạo context test JPA và transaction mặc định | Test repository, entity mapping, JPA behavior |
| `@SpringBootTest` | Context ứng dụng rộng hơn | Test service/transaction boundaries với nhiều bean |

Một test repository hiệu quả thường **chuẩn bị fixture bằng TestEntityManager, flush + clear, sau đó truy vấn bằng chính repository đang được kiểm thử**. Nếu dùng repository để vừa chuẩn bị vừa khẳng định cùng một operation, đôi khi test có thể bỏ sót lỗi mapping/flush.

## 3. Entity lifecycle: bốn trạng thái cần phân biệt

Theo Jakarta Persistence, một entity instance có thể ở các trạng thái chính:

```text
new / transient
  |
  | entityManager.persist(entity)
  v
managed (gắn với persistence context)
  | \
  |  \ entityManager.remove(entity)
  |   \-> removed (đang chờ xóa theo transaction)
  |
  | entityManager.detach(entity)
  | hoặc entityManager.clear()
  v
detached (có identity nhưng không được context quản lý)
  |
  | entityManager.merge(entity)
  v
managed copy (có thể là instance khác)
```

**Transient/new:** object vừa được tạo bằng `new`, chưa gắn vào context. `id` có thể null hoặc do app tự gán.

**Managed:** object được context quản lý. Thay đổi các persistent fields của nó được **dirty checking** theo dõi, và được đồng bộ khi flush/commit tùy flush mode.

**Detached:** object có identity nhưng không còn được context quản lý. Thay đổi trực tiếp object detached **không tự cập nhật DB**. Muốn đưa state trở lại context, dùng `merge`, và phải sử dụng entity managed do `merge` trả về.

**Removed:** entity đang được quản lý và được đánh dấu xóa. Database sẽ nhận DELETE khi flush/commit tùy provider/transaction.

Đừng nhầm `clear` với `remove`: `clear` **không xóa hàng trong database**; nó chỉ làm các entity trong persistence context trở thành detached.

### Cache cấp một và identity

Trong một persistence context, gọi `find(BookEntity.class, id)` lần thứ hai cho cùng entity thường trả **chính instance đang managed**. Vì thế:

```java
BookEntity b = testEntityManager.persistAndFlush(
        new BookEntity("ISBN-002", "Caching"));
BookEntity same = testEntityManager.find(
        BookEntity.class, b.getId());
assertSame(b, same);
```

là ví dụ một hành vi hợp lý khi chưa `clear`. Nếu test chỉ kiểm tra `find` trả dữ liệu đúng ngay sau `persist`, nó có thể chỉ kiểm tra object trong memory — chưa đủ chứng minh khả năng lưu và đọc lại qua SQL/database.

## 4. persist(): đưa entity mới vào persistence context

`persist` tạo association giữa entity mới và persistence context. Ví dụ:

```java
BookEntity entity = new BookEntity(
        "ISBN-003", "Transactions");
BookEntity managed = testEntityManager.persist(entity);
```

Trong `TestEntityManager` của Spring Boot 3.3, `persist(E)` delegate tới `EntityManager.persist(Object)` rồi trả lại entity được truyền vào. Với ví dụ entity thông thường, `managed == entity` là `true`.

**Đừng suy rằng persist luôn chạy INSERT ngay.** SQL có thể được trì hoãn đến flush/commit; thời điểm phụ thuộc ID generation strategy và provider:

- Với `GenerationType.SEQUENCE`, Hibernate thường lấy giá trị sequence trước rồi queue INSERT đến flush. Có ID **không chứng minh** hàng đã được INSERT.
- Với `GenerationType.IDENTITY`, provider thường phải thực hiện INSERT sớm để lấy ID từ database; vì vậy không dùng nó để chứng minh “persist chưa chạy SQL”.
- Với ID tự gán, entity có ID ngay cả trước persist; ID càng không phải bằng chứng lưu thành công.

Trong project ví dụ, ta chọn `SEQUENCE` và H2 để câu chuyện về flush có thể dự đoán và minh bạch hơn.

### persist không phải merge

`persist` dùng cho entity mới; truyền một entity detached hoặc entity đã có identity theo trạng thái không hợp lệ có thể tạo `EntityExistsException`, `PersistenceException` hoặc lỗi provider khác khi flush. Với entity detached cần cập nhật, dùng `merge` hoặc tải entity managed rồi sửa các field; đừng dùng `persist` như một thao tác upsert phổ quát.

## 5. flush(): đồng bộ JPA state với database, không commit

`TestEntityManager.flush()` delegate tới `EntityManager.flush()`. Nó yêu cầu persistence provider đồng bộ những thay đổi đang pending của persistence context với underlying database **trong transaction hiện tại**:

```java
testEntityManager.persist(book);
testEntityManager.flush();
```

Trong Hibernate, flush có thể phát SQL `INSERT`, `UPDATE`, `DELETE` đang đợi thực thi và có thể lộ ra lỗi do database constraints.

Nhưng điều quan trọng:

**Flush ≠ Commit.**

| Thao tác | Ý nghĩa | Transaction đã commit? |
| --- | --- | --- |
| `persist(entity)` | Đưa entity mới thành managed | Không |
| `flush()` | Đồng bộ pending changes tới DB trong transaction | Không |
| `clear()` | Detach entities khỏi persistence context | Không |
| `find(Entity.class,id)` | Tra cứu theo primary key trong context/DB | Không |
| Transaction commit | Hoàn tất transaction và xác nhận thay đổi theo DB | Có, nếu thành công |
| Transaction rollback | Hủy thay đổi transactional chưa commit | Không có thay đổi commit |

Trong `@DataJpaTest`, bạn có thể `persist → flush → clear → find` thành công, nhưng khi test kết thúc, transaction được **rollback** và hàng đó không trở thành dữ liệu bền vững giữa tests.

### Auto flush có thể xảy ra trước query

Với `FlushModeType.AUTO` (thường là default), JPA có thể flush trước truy vấn nếu cần đảm bảo query nhìn thấy những thay đổi thích hợp. Vì vậy một test:

```java
testEntityManager.persist(book);
assertEquals(1L, repository.count());
```

không chứng minh `persist` đã tự ghi SQL trước câu `count()`: repository query **có thể khiến provider tự flush**. Khi test muốn xác định chính xác điểm SQL/database nhận thay đổi, hãy gọi `flush` tường minh và quan sát qua một boundary phù hợp.

### Flush có thể fail muộn

`persist` không ném lỗi ngay không có nghĩa dữ liệu hợp lệ. Unique key, NOT NULL, foreign key, optimistic locking hoặc database-specific constraints có thể chỉ bị kiểm tra khi SQL được phát tại flush.

Khi test một constraint failure, chạy trong **test riêng** và không tiếp tục query trong transaction đã bị lỗi; provider/transaction có thể bị đánh dấu rollback-only. Đừng catch exception rồi cố chạy tiếp mọi JPA operation như transaction vẫn khỏe.

## 6. clear(): giải phóng first-level cache và detach managed entities

`TestEntityManager.clear()` delegate tới `EntityManager.clear()`: **tất cả** entity đang managed trong persistence context trở thành detached. Nó không xóa dữ liệu đã được flush xuống database.

```java
BookEntity managed = testEntityManager.persistAndFlush(
        new BookEntity("ISBN-004", "Persistence"));
Long id = managed.getId();

testEntityManager.clear();

BookEntity reloaded =
        testEntityManager.find(BookEntity.class, id);
```

Sau `clear`, `managed` không còn được EntityManager quản lý, còn `reloaded` là một managed entity mới trong context hiện tại. Trong project mẫu không có second-level cache bật, `find` sau clear có thể thực hiện database lookup. Nói chính xác hơn, **clear loại dữ liệu khỏi first-level cache**; nó không đảm bảo provider bỏ qua second-level cache nếu ứng dụng có cấu hình L2 cache.

### Vì sao phải flush trước clear?

Nếu sửa entity managed nhưng **chưa flush** rồi gọi `clear`, những sửa đổi đó không còn được theo dõi và có thể bị bỏ. Ví dụ:

```java
BookEntity entity = testEntityManager.persistAndFlush(
        new BookEntity("ISBN-005", "Original"));
entity.changeTitle("Unsaved");
testEntityManager.clear();
```

Một lần tìm lại entity thường nhận title `Original`, vì `Unsaved` chỉ là sửa đổi trong object managed và bị discard trước flush.

**Trình tự thường đúng để kiểm tra database state:**

```text
persist → flush → clear → find
                        ↑
              mới đọc lại entity
              ngoài L1 context cũ
```

**Trình tự nguy hiểm khi đang có unflushed modifications:**

```text
persist / mutate → clear → find
                    ↑
             pending changes có thể mất
```

Điều đó không có nghĩa mọi provider không bao giờ ghi SQL trước clear: một số operations/ID strategies có thể thực hiện SQL sớm. Test cần chủ động lựa chọn ID strategy và flush mode phù hợp nếu muốn kiểm tra chi tiết timing.

## 7. find(): tra cứu theo primary key và ranh giới của bộ nhớ đệm

`TestEntityManager.find(BookEntity.class, id)` delegate tới `EntityManager.find(Class<T>, Object primaryKey)`.

- Nếu entity theo khóa chính đó đã managed, JPA thường trả về instance ấy từ first-level cache.
- Nếu không có trong context, provider tìm entity từ persistence store/cache phù hợp và trả một managed instance.
- Nếu không có bản ghi, trả **`null`**, không phải `Optional.empty()`.
- Nếu truyền primaryKey sai kiểu hoặc null, có thể có `IllegalArgumentException` theo JPA API; không dùng `find` với null ID như thể đây là query hợp lệ.

Ví dụ:

```java
BookEntity existing =
        testEntityManager.find(BookEntity.class, persistedId);

BookEntity missing =
        testEntityManager.find(BookEntity.class, 999999999L);
```

Nếu muốn `Optional<BookEntity>`, phương thức `JpaRepository.findById(id)` có kiểu API khác. Cả hai cùng thể hiện tra cứu theo ID, nhưng không nhất thiết có cùng behavior như filter query hoặc lazy proxy.

### find không phải getReference

`EntityManager.getReference(...)` có thể trả proxy/reference mà chưa nạp ngay state; truy cập field sau đó có thể ném `EntityNotFoundException` nếu DB không có hàng. `find(...)` trả entity hoặc null theo contract tra cứu. Đừng dùng `getReference` để “chứng minh hàng đã tồn tại” mà chưa truy cập state.

## 8. persistAndFlush, persistAndGetId và persistFlushFind

`TestEntityManager` của Spring Boot 3.3 cung cấp các helper:

| Phương thức | Ý nghĩa trong Boot 3.3 | Điều không nên suy ra |
| --- | --- | --- |
| `persist(entity)` | persist rồi trả entity được truyền | SQL INSERT đã chắc chắn chạy |
| `persistAndFlush(entity)` | persist, flush, trả entity gốc | Transaction đã commit |
| `persistAndGetId(entity)` | persist, trả identifier | Bản ghi đã được flush/commit |
| `persistAndGetId(entity, Long.class)` | persist, trả ID theo type | ID bắt buộc bắt đầu từ 1 |
| `persistFlushFind(entity)` | persistAndFlush rồi find theo ID | Tự clear L1 hoặc buộc SELECT mới |
| `getId(entity)` | Lấy identifier qua PersistenceUnitUtil | Entity luôn đang managed |
| `detach(entity)` | Detach một entity | Xóa bản ghi trong DB |
| `clear()` | Detach mọi managed entities | Đã flush/commit trước đó |
| `getEntityManager()` | Truy cập JPA EntityManager thật | Có thể dùng khi không có transaction |

**Điểm đặc biệt theo phiên bản:** trong Javadoc Spring Boot **3.3**, `persistFlushFind` được mô tả là delegate tới `persistAndFlush` rồi `find(Class, Object)`. Nó **không được tài liệu Boot 3.3 đảm bảo tự clear** persistence context trước lần find. Vì vậy, đừng viết:

```java
BookEntity fresh = testEntityManager.persistFlushFind(
        new BookEntity("ISBN-006", "Demo"));
assertNotSame(original, fresh); // Không có cơ sở ở Boot 3.3!
```

Đoạn trên là **phản ví dụ** (còn tham chiếu `original` chưa có định nghĩa), chỉ để nhấn mạnh không được dùng identity assertion sai. Khi muốn chứng minh **first-level cache bị loại bỏ**, hãy dùng **`persist → flush → clear → find`** tường minh và assert entity mới không cùng instance với entity trước clear.

Một ứng dụng nâng lên phiên bản Boot khác nên kiểm tra lại Javadoc/source tương ứng; implementation helper có thể đổi mà không thay bản chất các phương thức JPA chuẩn.

## 9. Chuẩn bị project thực hành Java 17+ / Spring Boot 3.3.5

Ta tạo một project chỉ có một entity `BookEntity`, một Spring Data JPA repository và `@DataJpaTest` dùng H2. Không có web server, service ngoài hoặc database production.

Cấu trúc thư mục:

```text
jpa-test-entity-manager/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/jpatest/
│   ├── JpaTestApplication.java
│   ├── BookEntity.java
│   └── BookRepository.java
└── src/test/java/com/example/jpatest/
    └── BookPersistenceTest.java
```

### 9.1. settings.gradle

```groovy
rootProject.name = 'jpa-test-entity-manager'
```

### 9.2. build.gradle

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
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
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

- `spring-boot-starter-data-jpa` chứa JPA, Hibernate và Spring Data repositories.
- `h2` ở test runtime để có embedded DB phù hợp cho JPA slice mà không cần tài khoản database.
- `spring-boot-starter-test` mang theo JUnit Jupiter, AssertJ và Spring Test.
- `junit-platform-launcher` giúp Gradle chạy test JUnit Platform theo cấu hình.

Khi dự án có Flyway/Liquibase hoặc sử dụng một DataSource thật, quy tắc tạo schema/test database phải được xem riêng. Trong **project mẫu** dưới đây, ta yêu cầu Hibernate `create-drop` để có schema theo entity model trong database H2 của test.

### 9.3. Application root

`src/main/java/com/example/jpatest/JpaTestApplication.java`:

```java
package com.example.jpatest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JpaTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(JpaTestApplication.class, args);
    }
}
```

`@DataJpaTest` sẽ tìm `@SpringBootConfiguration`/`@SpringBootApplication` này từ package của test. Không cần chạy `main()` để test repository.

### 9.4. Entity dùng GenerationType.SEQUENCE

`src/main/java/com/example/jpatest/BookEntity.java`:

```java
package com.example.jpatest;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

@Entity
@Table(name = "catalog_books")
public class BookEntity {

    @Id
    @GeneratedValue(
            strategy = GenerationType.SEQUENCE,
            generator = "catalog_book_id_generator")
    @SequenceGenerator(
            name = "catalog_book_id_generator",
            sequenceName = "catalog_book_id_seq",
            allocationSize = 1)
    private Long id;

    @Column(nullable = false, unique = true, length = 32)
    private String isbn;

    @Column(nullable = false, length = 160)
    private String title;

    protected BookEntity() {
        // Constructor cho JPA provider.
    }

    public BookEntity(String isbn, String title) {
        if (isbn == null || isbn.isBlank()) {
            throw new IllegalArgumentException("isbn is required");
        }
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        this.isbn = isbn;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getIsbn() {
        return isbn;
    }

    public String getTitle() {
        return title;
    }

    public void changeTitle(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        this.title = title;
    }
}
```

**Tại sao không dùng Java record làm JPA entity?** JPA entity thường cần class có no-arg constructor (ít nhất protected), identity và cơ chế managed state/dirty checking. Record là final và immutable, nên không phải lựa chọn mặc định cho JPA entity Hibernate kiểu này. Record vẫn rất phù hợp để làm DTO hoặc projection.

**Tại sao dùng SEQUENCE?** H2 hỗ trợ database sequence; Hibernate có thể cấp ID khi persist nhưng trì hoãn INSERT đến flush. Dùng `IDENTITY` sẽ làm ví dụ về timing khác đi vì provider thường cần INSERT sớm để lấy generated ID. Dù chọn SEQUENCE, không nên assert SQL count/timing trong mọi database/provider mà không có cơ chế đo đúng.

**Tại sao có unique ISBN?** Để thảo luận database constraints và thời điểm flush kiểm tra lỗi. Các test runnable bên dưới tập trung vào successful persistence flow; kiểm tra constraint failure cần test riêng và thận trọng vì transaction sau lỗi có thể không tiếp tục được.

### 9.5. Repository interface

`src/main/java/com/example/jpatest/BookRepository.java`:

```java
package com.example.jpatest;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository
        extends JpaRepository<BookEntity, Long> {

    Optional<BookEntity> findByIsbn(String isbn);

    long countByTitle(String title);
}
```

Spring Data JPA sẽ triển khai derived query methods `findByIsbn` và `countByTitle`. Một test repository phải bảo vệ method thật thay vì chỉ xác nhận TestEntityManager đọc chính entity vừa persist.

## 10. Bộ test đầy đủ dùng TestEntityManager

Tạo `src/test/java/com/example/jpatest/BookPersistenceTest.java`:

```java
package com.example.jpatest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(
        showSql = false,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop")
class BookPersistenceTest {

    @Autowired
    TestEntityManager entities;

    @Autowired
    BookRepository repository;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void persistFlushClearFindReloadsEntity() {
        BookEntity initial = entities.persist(
                new BookEntity("ISBN-101", "JPA basics"));

        Long id = initial.getId();
        assertNotNull(id);

        entities.flush();
        entities.clear();

        assertFalse(
                entities.getEntityManager().contains(initial));

        BookEntity loaded = entities.find(BookEntity.class, id);
        assertNotNull(loaded);
        assertNotSame(initial, loaded);
        assertEquals("ISBN-101", loaded.getIsbn());
        assertEquals("JPA basics", loaded.getTitle());
        assertTrue(entities.getEntityManager().contains(loaded));
    }

    @Test
    void findWithoutClearCanReturnSameManagedInstance() {
        BookEntity initial = entities.persistAndFlush(
                new BookEntity("ISBN-102", "First level cache"));

        BookEntity found = entities.find(
                BookEntity.class, initial.getId());

        assertSame(initial, found);
    }

    @Test
    void clearDiscardsUnflushedManagedChanges() {
        BookEntity initial = entities.persistAndFlush(
                new BookEntity("ISBN-103", "Original"));

        Long id = initial.getId();
        initial.changeTitle("Not flushed");

        entities.clear();

        BookEntity loaded = entities.find(BookEntity.class, id);
        assertNotNull(loaded);
        assertEquals("Original", loaded.getTitle());
    }

    @Test
    void managedChangesPersistAfterFlushAndClear() {
        BookEntity initial = entities.persistAndFlush(
                new BookEntity("ISBN-104", "Before"));
        Long id = initial.getId();

        entities.clear();

        BookEntity managed = entities.find(BookEntity.class, id);
        assertNotNull(managed);
        managed.changeTitle("After");

        entities.flush();
        entities.clear();

        BookEntity loaded = entities.find(BookEntity.class, id);
        assertNotNull(loaded);
        assertEquals("After", loaded.getTitle());
    }

    @Test
    void repositoryFindByIsbnReadsFixtureAfterClear() {
        BookEntity initial = entities.persistAndFlush(
                new BookEntity("ISBN-105", "Repository query"));
        Long id = initial.getId();

        entities.clear();

        BookEntity found = repository
                .findByIsbn("ISBN-105")
                .orElseThrow();

        assertEquals(id, found.getId());
        assertEquals("Repository query", found.getTitle());
    }

    @Test
    void repositorySaveIsVisibleToEntityManager() {
        BookEntity saved = repository.save(
                new BookEntity("ISBN-106", "Saved by repository"));
        Long id = saved.getId();

        assertNotNull(id);
        entities.flush();
        entities.clear();

        BookEntity found = entities.find(BookEntity.class, id);
        assertNotNull(found);
        assertEquals("Saved by repository", found.getTitle());
    }

    @Test
    void findReturnsNullForMissingPrimaryKey() {
        BookEntity missing = entities.find(
                BookEntity.class, 999999999L);

        assertNull(missing);
    }

    @Test
    void persistAndGetIdCanReturnTypedIdentifier() {
        Long id = entities.persistAndGetId(
                new BookEntity("ISBN-107", "Identifier helper"),
                Long.class);

        assertNotNull(id);
        entities.flush();
        entities.clear();

        BookEntity found = entities.find(BookEntity.class, id);
        assertNotNull(found);
        assertEquals("ISBN-107", found.getIsbn());
    }

    @Test
    void persistFlushFindHelperReturnsMatchingEntity() {
        BookEntity found = entities.persistFlushFind(
                new BookEntity("ISBN-108", "Convenience method"));

        assertNotNull(found);
        Long id = found.getId();
        assertNotNull(id);
        assertEquals("Convenience method", found.getTitle());

        // Boot 3.3 helper không bảo đảm clear L1.
        entities.clear();
        BookEntity reloaded = entities.find(BookEntity.class, id);
        assertNotNull(reloaded);
        assertEquals("Convenience method", reloaded.getTitle());
    }

    @Test
    void detachOneEntityPreventsUnflushedUpdate() {
        BookEntity initial = entities.persistAndFlush(
                new BookEntity("ISBN-109", "Stored"));
        Long id = initial.getId();

        initial.changeTitle("Detached change");
        entities.detach(initial);

        assertFalse(
                entities.getEntityManager().contains(initial));

        entities.flush();
        entities.clear();

        BookEntity loaded = entities.find(BookEntity.class, id);
        assertNotNull(loaded);
        assertEquals("Stored", loaded.getTitle());
    }

    @Test
    void mergeCopiesDetachedStateToManagedInstance() {
        BookEntity detached = entities.persistAndFlush(
                new BookEntity("ISBN-110", "Before merge"));
        Long id = detached.getId();

        entities.clear();
        detached.changeTitle("After merge");

        BookEntity managed = entities.merge(detached);
        assertNotSame(detached, managed);

        entities.flush();
        entities.clear();

        BookEntity loaded = entities.find(BookEntity.class, id);
        assertNotNull(loaded);
        assertEquals("After merge", loaded.getTitle());
    }

    @Test
    void refreshRestoresFlushedDatabaseValue() {
        BookEntity managed = entities.persistAndFlush(
                new BookEntity("ISBN-111", "Persisted title"));

        managed.changeTitle("Only in memory");

        entities.refresh(managed);

        assertEquals("Persisted title", managed.getTitle());
    }

    @Test
    void repositoryCountUsesFlushedRows() {
        entities.persistAndFlush(
                new BookEntity("ISBN-112", "Count target"));
        entities.clear();

        assertEquals(1L, repository.countByTitle("Count target"));
    }

    @Test
    void jdbcSeesFlushedInsertInsideSameTransaction() {
        BookEntity entity = entities.persist(
                new BookEntity("ISBN-113", "JDBC check"));

        entities.flush();

        Long count = jdbc.queryForObject(
                "select count(*) from catalog_books where isbn = ?",
                Long.class,
                entity.getIsbn());

        assertEquals(1L, count);
    }
}
```

**Có 14 phương thức `@Test`** trong class này. Chúng được thiết kế cho project demo Boot 3.3.5, Hibernate và H2 trên test runtime classpath. Đây là bộ test mẫu có thể tái hiện; **chưa khẳng định đã thực thi Gradle tại thời điểm biên soạn**.

### 10.1. Cách đọc mỗi test và điều nó thực sự chứng minh

| Test method | Chuỗi thao tác chính | Bằng chứng |
| --- | --- | --- |
| `persistFlushClearFindReloadsEntity` | persist → flush → clear → find | Entity sau clear có trạng thái đã được đồng bộ và instance khác |
| `findWithoutClearCanReturnSameManagedInstance` | persistAndFlush → find | L1 context có thể trả cùng object |
| `clearDiscardsUnflushedManagedChanges` | persistAndFlush → mutate → clear → find | Đổi managed field chưa flush có thể bị discard |
| `managedChangesPersistAfterFlushAndClear` | persist/flush → clear → find/mutate → flush/clear/find | Dirty checking đồng bộ update của managed entity |
| `repositoryFindByIsbnReadsFixtureAfterClear` | persistAndFlush → clear → repository query | Derived query tìm đúng fixture qua database/context mới |
| `repositorySaveIsVisibleToEntityManager` | repository.save → flush → clear → find | Repository ghi entity mà JPA có thể đọc lại |
| `findReturnsNullForMissingPrimaryKey` | find nonexistent ID | API `find` trả null khi không có |
| `persistAndGetIdCanReturnTypedIdentifier` | persistAndGetId → flush → clear → find | Helper trả ID có type, entity có thể tìm lại |
| `persistFlushFindHelperReturnsMatchingEntity` | persistFlushFind → clear → find | Helper persist/flush/find đúng; clear thêm để kiểm chứng ngoài L1 |
| `detachOneEntityPreventsUnflushedUpdate` | mutate → detach → flush/clear/find | Detached mutation không được dirty checking đồng bộ |
| `mergeCopiesDetachedStateToManagedInstance` | clear → mutate detached → merge → flush/clear/find | merge trả managed copy có state được cập nhật |
| `refreshRestoresFlushedDatabaseValue` | persistAndFlush → mutate → refresh | Refresh thay thay đổi chưa flush bằng state DB |
| `repositoryCountUsesFlushedRows` | persistAndFlush → clear → derived count | Query repository thấy fixture theo điều kiện |
| `jdbcSeesFlushedInsertInsideSameTransaction` | persist → flush → JDBC COUNT | JDBC nhìn thấy hàng trong cùng transaction |

**Hạn chế quan trọng:** test `jdbcSeesFlushedInsertInsideSameTransaction` dùng `JdbcTemplate` đi qua cùng transaction/DataSource của test. Nó xác nhận SQL row visibility trong transaction đó, **không chứng minh client ở transaction khác thấy hàng đã commit**. Với transaction isolation mặc định, một session bên ngoài thường không thể đọc dữ liệu chưa commit.

### 10.2. Vì sao assertNotSame sau clear là hữu ích?

Trong `persistFlushClearFindReloadsEntity`:

1. `initial` là managed entity sau persist.
2. `flush` đồng bộ pending SQL.
3. `clear` detach `initial`.
4. `find` lấy entity managed trong context sau reset.
5. `assertNotSame(initial, loaded)` cho thấy `find` không trả lại cùng reference `initial` ở first-level cache cũ.
6. `assertEquals(...)` xác nhận dữ liệu quan trọng có thể đọc lại.

Nếu ứng dụng bật second-level cache, query sau clear có thể đọc từ L2 cache; assertNotSame **không tự chứng minh** SELECT tới database. Với project mẫu không chủ động bật L2 cache, chuỗi này vẫn là cách tiêu chuẩn để tránh test chỉ đọc cùng object managed.

### 10.3. Vì sao phải test thay đổi sau clear?

`clearDiscardsUnflushedManagedChanges` có hai phiên bản của title:

- Bản đã flush: `Original`.
- Bản thay đổi trong memory: `Not flushed`.

Sau `clear`, entity cũ detached; dirty checking không còn áp dụng. `find` nhận `Original`. Nếu bài test bỏ `flush` ban đầu, có thể không có bản ghi để tìm lại, làm việc chẩn đoán sai.

Trong `managedChangesPersistAfterFlushAndClear`, test load entity managed, thay title, gọi `flush` rồi `clear`. Lần find sau phải trả `After`. Cặp test này cho thấy **flush trước clear** là ranh giới quyết định đối với dirty checking.

### 10.4. Vai trò của JdbcTemplate

`JdbcTemplate` ở đây được Spring Boot JPA test slice cấu hình để query cùng H2 DataSource. Nó không dùng JPA first-level cache. Một `COUNT(*)` qua SQL sau flush giúp kiểm tra row có mặt trong underlying database **trong transaction hiện hành**.

Không hardcode SQL table name khác mapping `@Table(name="catalog_books")`. Nếu dùng schema khác hoặc naming strategy khác, SQL trực tiếp cần điều chỉnh; nó không tự đổi theo tên entity như JPQL.

### 10.5. Vì sao tất cả test fixture dùng ISBN khác nhau?

Ví dụ dùng các giá trị `ISBN-101` tới `ISBN-113` để mỗi case độc lập ngay khi đọc code. Dù `@DataJpaTest` mặc định rollback, test vẫn không nên phụ thuộc thứ tự chạy và không được tái sử dụng một ID tự tăng được kỳ vọng bằng số cụ thể. Nếu cần test transaction commit/rollback qua nhiều context, chủ động tạo và xóa fixture trong môi trường được cô lập.

## 11. Test EntityManager và Repository cùng nhau thế nào cho hiệu quả?

Một mẫu tốt để kiểm tra derived query:

```java
BookEntity fixture = entities.persistAndFlush(
        new BookEntity("ISBN-200", "Spring Data Guide"));
entities.clear();

BookEntity actual = repository
        .findByIsbn("ISBN-200")
        .orElseThrow();

assertEquals(fixture.getId(), actual.getId());
assertEquals("Spring Data Guide", actual.getTitle());
```

Đây là snippet dựa vào các class đã được tạo trong project, thích hợp để đưa vào test method. Nó tách:

- **Arrange:** `TestEntityManager` lưu fixture.
- **Act:** `BookRepository` thực hiện chính query cần test.
- **Assert:** entity tìm được có ID/title đúng.

Ngược lại, một test dùng repository `save` rồi repository `findById` không phải vô dụng, nhưng có thể chủ yếu kiểm tra happy path của chính abstraction, chưa cho thấy mapping khi persistence context được clear. Với query phức tạp, nên chuẩn bị fixture qua TestEntityManager và kiểm tra các cases lọc/sắp xếp/pagination.

### Test @Query và lazy relation

Nếu entity có `@ManyToOne`, `@OneToMany` hoặc fetch policy LAZY, `clear` giúp kiểm tra behavior thực hơn: sau clear, repository phải load entity/association theo mapping. Nhưng test phải tránh truy cập một lazy association trên **detached entity** sau khi transaction đóng, vì có thể bị `LazyInitializationException`.

Trong `@DataJpaTest` transaction mặc định đang active trong test method; sau `clear` và `find`, entity mới managed, nên có thể load lazy relation khi truy cập nếu provider cho phép. Để kiểm tra N+1/SQL count, cần instrumentation như Hibernate Statistics hoặc datasource-proxy; không suy số SELECT chỉ từ `assertNotSame`.

### Test projection và DTO

`TestEntityManager` phù hợp để tạo entity fixture, còn act có thể là repository method trả DTO projection, interface projection hoặc `Page<T>`. Dùng assertion trên fields thực tế của projection thay vì chỉ xem fixture được lưu. Với pagination, thiết lập sort order rõ, không dựa vào thứ tự mặc định của bảng SQL.

## 12. Đặc biệt: flush không đồng nghĩa transaction commit

Spring `@DataJpaTest` mặc định transactional và rollback sau từng method. Vì thế:

```text
Test method begins
  ├─ Transaction BEGIN
  ├─ persist(Book)
  ├─ flush()       -> INSERT bên trong transaction
  ├─ clear()
  ├─ find(Book,id) -> tìm thấy trong cùng transaction
  └─ Test ends     -> ROLLBACK

Test method khác không được dùng fixture từ transaction đó
```

Một bản ghi được tìm thấy trong cùng transaction không phải bằng chứng đã được commit. Điều này đúng với H2 và phần lớn RDBMS có transaction isolation.

### Muốn kiểm tra transaction boundary thật thì sao?

Spring Test cung cấp `TestTransaction` khi test chạy trong framework-managed transaction. Một kịch bản nâng cao có thể:

1. Persist/flush một entity trong test transaction.
2. Gọi `TestTransaction.flagForRollback()`.
3. Kết thúc transaction bằng `TestTransaction.end()`.
4. Bắt đầu transaction mới bằng `TestTransaction.start()`.
5. Query lại để xác nhận row không còn.

Đây là **hướng mở rộng**, không nằm trong 14 test runnable của bài, bởi việc tự kết thúc/bắt đầu transaction cần kiểm soát lifecycle và cleanup cẩn thận. Nếu test commit thực, cần dùng database dành cho test và xóa dữ liệu sau đó, không chạy trên production DB.

Một test chạy với `@Transactional(propagation = Propagation.NOT_SUPPORTED)` hoặc không có transaction có thể không dùng được các thao tác `flush` của TestEntityManager giống mặc định; `EntityManager.flush()` đòi transaction phù hợp và có thể ném `TransactionRequiredException`.

## 13. Phát hiện database constraint bằng flush

Giả sử entity có:

```java
@Column(nullable = false, unique = true, length = 32)
private String isbn;
```

Schema do Hibernate tạo cho H2 có thể có unique constraint cho ISBN. Một test có thể persist hai entities với cùng ISBN rồi flush:

```java
entities.persistAndFlush(
        new BookEntity("ISBN-DUP", "First"));
entities.persist(
        new BookEntity("ISBN-DUP", "Second"));

assertThrows(RuntimeException.class, entities::flush);
```

Đây là **snippet kịch bản**, chưa có imports và cần đặt trong một **test method riêng**. Assertion kiểu `RuntimeException` chỉ giúp minh họa thời điểm lỗi, **chưa đủ để bảo vệ đúng constraint**. Test production nên kiểm tra root cause/SQL state/error type phù hợp với database và exception translation của stack hiện tại, ví dụ Jakarta `PersistenceException` hoặc Spring `DataIntegrityViolationException` khi được translate ở repository boundary.

**Không tiếp tục dùng cùng transaction như thể chưa có lỗi.** Sau constraint violation, JPA provider thường đánh dấu transaction rollback-only hoặc session không còn trạng thái an toàn. Hãy để test rollback và bắt đầu một test mới cho scenario khác.

### Vì sao không assert ném ngay tại persist()?

Vì `GenerationType.SEQUENCE` trong demo thường trì hoãn INSERT; database unique constraint chỉ có thể phát hiện khi SQL được gửi lúc flush. Trong các mapping/provider khác, INSERT có thể phát sớm. Bài test nên giữ mục tiêu là **constraint được database thực thi**, không khóa chặt một thời điểm tùy tiện nếu code hỗ trợ nhiều cơ sở dữ liệu.

### Đừng chỉ tin @Column(unique=true)

`@Column(unique=true)` là metadata cho schema generation, không thay thế migration đã deploy. Trong production dùng Flyway/Liquibase, unique index phải có trong migration/schema thật. Một H2 `create-drop` test PASS không chứng minh database production đã có unique constraint đúng; kiểm tra migration và chạy test với database production-compatible khi cần.

## 14. Những helper khác: detach, merge, refresh và remove

`TestEntityManager` có một số methods ngoài bốn thao tác chính:

### detach(entity)

Detach **một** entity, trong khi `clear` detach tất cả entity. Một entity detached bị thay đổi trong memory không tự flush. Test `detachOneEntityPreventsUnflushedUpdate` thể hiện chính xác hành vi này.

### merge(entity)

Khi entity detached đã có thay đổi cần đưa vào persistence context:

```java
BookEntity managedCopy = entities.merge(detached);
```

`merge` trả **managed instance**, có thể khác object detached gốc. Sau đó nên làm việc với `managedCopy`, không giả định detached gốc đã được attach lại. Khi có associations và cascade MERGE, cần kiểm tra behavior theo mapping.

### refresh(entity)

`refresh` nạp lại state từ database vào một **managed** entity, ghi đè thay đổi unflushed trong memory. Với entity detached, `refresh` có thể ném `IllegalArgumentException` hoặc lỗi provider tương ứng; nó không phải cách “tự reattach” entity.

### remove(entity)

`remove` đánh dấu managed entity để xóa, lệnh DELETE được xử lý theo flush/commit. Sau `remove`, muốn test database thật sự không còn row trong transaction, có thể `flush + clear + find == null`; nhưng phải hiểu soft delete, cascade và foreign keys của entity thực.

### getEntityManager()

`entities.getEntityManager()` cho phép dùng JPA API như `contains`, `createQuery`, `setFlushMode`, `lock` hoặc unwrap provider. Với mục tiêu kiểm thử bốn thao tác cơ bản, nên giữ TestEntityManager ở mức đơn giản thay vì lạm dụng provider-specific APIs.

## 15. Common pitfalls: những khẳng định sai dễ gặp

### 15.1. persist đã có ID, vậy DB đã có hàng

**Sai.** Generated ID có thể được lấy từ sequence trước khi INSERT được flush. ID không phải bằng chứng transaction đã commit hoặc ngay cả INSERT đã chạy.

### 15.2. flush là commit

**Sai.** Flush đồng bộ trong transaction, transaction vẫn có thể rollback. Trong `@DataJpaTest`, rollback là hành vi mặc định.

### 15.3. clear xóa database

**Sai.** Clear detach entities khỏi first-level context; những rows đã flush vẫn tồn tại trong transaction cho tới khi rollback/commit.

### 15.4. find sau persist chắc chắn chạy SELECT

**Sai.** Khi entity đang managed, find thường trả lại instance từ first-level cache. Clear trước find nếu mục tiêu là kiểm tra load bên ngoài context cũ.

### 15.5. clear tự flush những thay đổi pending

**Sai.** Unflushed updates có thể mất sau clear. Chủ động flush khi cần giữ thay đổi.

### 15.6. persistFlushFind luôn tạo một Java object mới

**Không được khẳng định ở Boot 3.3.** Javadoc phiên bản này mô tả persistAndFlush rồi find, không đảm bảo clear. Kiểm tra API theo version; dùng flush+clear+find riêng nếu identity/load boundary là mục tiêu.

### 15.7. find sau clear chắc chắn thực hiện một SELECT

**Không luôn đúng.** L1 cache bị reset, nhưng nếu có L2 cache hoặc provider-specific optimization, có thể không phát SELECT. Muốn đếm SQL, dùng instrumentation thích hợp.

### 15.8. @DataJpaTest nạp toàn bộ application beans

**Sai.** JPA slice tập trung vào entities/repositories và infrastructure liên quan; các service/controller thông thường không tự được scan. Với test service transaction có nhiều collaborators, dùng cấu hình rộng hơn hoặc `@Import` đúng phạm vi.

### 15.9. Dùng H2 đủ chứng minh PostgreSQL/MySQL production

**Không đủ.** SQL dialect, locking, transaction isolation, sequence/identity, JSON columns, case sensitivity và constraints có thể khác. Khi behavior phụ thuộc database-specific feature, dùng Testcontainers với database cùng loại hoặc integration environment thích hợp.

### 15.10. Test dựa vào thứ tự chạy và ID liên tục

**Không ổn định.** Test transaction rollback không chắc đưa sequence về giá trị cũ. Không assert ID đầu luôn bằng 1; thay bằng `assertNotNull(id)` và so sánh ID đọc lại.

### 15.11. Trộn javax.persistence và jakarta.persistence

**Sai ở Boot 3.x.** Dùng `jakarta.persistence.*` với Jakarta Persistence/Hibernate 6. Import `javax.persistence.*` từ project Boot 2 có thể khiến entity mapping/test lỗi hoặc không biên dịch.

### 15.12. Không có transaction nhưng vẫn gọi flush

`EntityManager.flush()` yêu cầu transaction theo JPA. Nếu bạn tắt transaction mặc định của `@DataJpaTest`, phải thiết kế transaction rõ thay vì gọi flush trong ngữ cảnh không hỗ trợ.

## 16. Tối ưu tốc độ và tính cô lập của test

`@DataJpaTest` thường nhẹ hơn `@SpringBootTest` vì chỉ nạp phần JPA slice. Dù vậy, tạo EntityManagerFactory/Hibernate metadata và schema H2 vẫn mất thời gian; nên gom các test cùng configuration để tận dụng Spring TestContext cache.

Các điểm cần bảo vệ:

- Test không phụ thuộc fixture từ test method khác.
- Không dùng `@Order` để bắt test A phải chạy trước test B.
- Không dùng static mutable cache cho entities/ID.
- Tránh đặt `@DirtiesContext` lên mọi test trừ khi thật sự thay application context.
- Nếu test cấp quyền commit, xóa dữ liệu sau thử nghiệm.
- Nếu test chạy song song chia sẻ cùng database/schema, cần ID/fixture isolation và kiểm soát schema reset.
- SQL logging có thể giúp debug nhưng không dùng log output như một assertion không ổn định.
- Nếu cần chứng minh số query và N+1, dùng Hibernate Statistics/datasource instrumentation và chuẩn bị context/provider cụ thể, không suy từ số lời gọi repository.

### Tương tác với transaction isolation

Một `JdbcTemplate` dùng cùng Spring-managed transaction thấy dữ liệu đã flush, nhưng một transaction khác có thể không thấy vì isolation. Khi test concurrency, read-committed, repeatable-read hoặc locking, cần nhiều transaction/connection có kiểm soát, không chỉ gọi `clear()` trong cùng transaction.

### H2 trong test runtime

Dùng H2 embedded hợp lý cho repository CRUD/mapping cơ bản. Nhưng Hibernate DDL auto `create-drop` chỉ phù hợp với sandbox test; trong ứng dụng dùng migration, ưu tiên chạy schema thực được Flyway/Liquibase quản lý. Không gán `spring.jpa.hibernate.ddl-auto=create-drop` cho môi trường production.

## 17. So sánh một test yếu với test mạnh

**Test yếu:**

```java
BookEntity saved = entities.persist(
        new BookEntity("ISBN-300", "Book"));
assertNotNull(saved.getId());

BookEntity found = entities.find(
        BookEntity.class, saved.getId());
assertEquals("Book", found.getTitle());
```

Test có thể PASS dù chưa kiểm tra SQL INSERT, vì ID có thể từ sequence và `find` trả object đang managed.

**Test mạnh hơn:**

```java
BookEntity saved = entities.persist(
        new BookEntity("ISBN-300", "Book"));
Long id = saved.getId();

entities.flush();
entities.clear();

BookEntity found = entities.find(BookEntity.class, id);

assertNotNull(found);
assertNotSame(saved, found);
assertEquals("Book", found.getTitle());
```

Sau clear, lookup không thể trả reference cũ từ first-level context. Nếu còn cần chứng minh row được database nhận, có thể dùng JDBC query **trong transaction hiện tại** như test `jdbcSeesFlushedInsertInsideSameTransaction`.

**Đừng gọi một test là “đã commit” chỉ vì nó sử dụng flush+clear+find.** Đó là test database-state synchronization và persistence-context boundary, không phải commit verification.

## 18. Troubleshooting theo dấu hiệu

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `No qualifying bean of type TestEntityManager` | Không ở `@DataJpaTest` hoặc chưa thêm `@AutoConfigureTestEntityManager` | Dùng JPA test slice; nếu ở test context khác, cấu hình hỗ trợ rõ |
| `Unable to find a @SpringBootConfiguration` | Test ngoài package hierarchy application root | Di chuyển package phù hợp hoặc chỉ định test configuration |
| `TransactionRequiredException` khi flush | Không có transaction phù hợp | Dùng `@DataJpaTest` mặc định transactional hoặc khai báo transaction |
| `Table not found` / schema lỗi | H2 DDL/migration/schema chưa thiết lập | Xem JPA DDL settings, datasource, Flyway/Liquibase |
| ID null sau persist | Strategy/assignment/provider không như giả định | Kiểm tra `@GeneratedValue`, `SEQUENCE` và provider |
| Test PASS trước clear nhưng FAIL sau clear | Có thay đổi chưa flush, mapping/SQL sai | Flush tường minh trước clear, đọc root cause |
| `find` trả cùng object trước clear | L1 cache hoạt động đúng | Dùng clear khi cần load ngoài context cũ |
| `find` trả null sau clear | Insert chưa flush, ID sai hoặc row bị xóa/rollback | Kiểm tra thứ tự persist/flush và transaction |
| `find` sau clear vẫn không phát SELECT | L2 cache hoặc provider optimization | Đừng suy từ code; đo bằng SQL instrumentation |
| Thay field detached không lưu | Detached không được dirty checking | Merge hoặc tải managed instance và sửa |
| `LazyInitializationException` | Truy cập lazy relation trên detached/ngoài session | Thiết kế fetch/transaction phù hợp |
| Duplicate ISBN chỉ fail khi flush | Unique constraint kiểm tra lúc SQL thực thi | Test constraint trong transaction riêng |
| Unique constraint trên H2 PASS nhưng production lỗi | Dialect/schema/migration khác | Testcontainers cho DB cùng loại |
| Repository test không thấy service bean | `@DataJpaTest` chỉ nạp slice | Import collaborators hoặc dùng @SpringBootTest khi cần |
| Test có ID thay đổi giữa các lần | Sequence không reset với rollback | Không assert ID cố định |
| N+1/SQL performance không được phát hiện | Test chỉ kiểm tra Java entity state | Dùng SQL count/statistics và dữ liệu đủ lớn |

### Khi gặp Failed to load ApplicationContext

Đọc **Caused by** cụ thể thay vì chỉ dòng wrapper. Các nguyên nhân khác nhau cần xử lý khác nhau: lỗi DataSource, dialect, entity mapping, schema migration, repository query parsing hoặc bean wiring. Đừng chuyển test sang `@SpringBootTest` chỉ để tránh hiểu tại sao JPA slice không load được.

## 19. Bài tập thực hành

Với project ở mục 9–10:

1. Chạy `persistFlushClearFindReloadsEntity`, bỏ `clear` rồi thay assertion thành `assertSame(initial, loaded)`. Giải thích vì sao không còn kiểm tra load sau reset context.
2. Gọi `persist` rồi kiểm tra ID, nhưng **không flush**. Vì sao ID non-null chưa chứng minh INSERT đã chạy?
3. Trong `clearDiscardsUnflushedManagedChanges`, thêm `flush` sau `changeTitle("Not flushed")` rồi mới clear; đổi expected title thành `Not flushed`.
4. Trong `managedChangesPersistAfterFlushAndClear`, thử bỏ flush lần hai và dự đoán kết quả sau clear.
5. Thay `GenerationType.SEQUENCE` bằng `IDENTITY` trong sandbox, quan sát thời điểm SQL INSERT và giải thích khác biệt.
6. Thử `repository.findByIsbn(...)` ngay sau persist, so với sau flush+clear; giải thích vì sao auto flush có thể che mất giả định của test.
7. Viết test mới cho ISBN không tồn tại; repository trả `Optional.empty()`, còn `TestEntityManager.find` trả `null`.
8. Thêm unique ISBN duplicate case trong **test riêng**, xác định loại exception/root cause trong H2 và không chạy các JPA operations tiếp theo trong transaction bị lỗi.
9. Tách transaction bằng `TestTransaction` để chứng minh flush không phải commit, không chạy trên production DB.
10. Thử `TestEntityManager.persistAndGetId(...)` với `Long.class`; không assert ID bằng 1.
11. Thử `persistFlushFind` trên Boot 3.3 và kiểm tra instance identity trước/sau **explicit clear**; đọc đúng Javadoc của version.
12. Dùng `JdbcTemplate` query `catalog_books` sau flush để xác nhận row được đồng bộ trong transaction hiện hành.
13. Thêm một `@ManyToOne(fetch=LAZY)` và test repository fetch behavior sau clear; khi cần đo query count hãy dùng instrumentation, không suy từ `assertNotSame`.
14. Chạy test tương tự với PostgreSQL Testcontainers để so sánh H2 về schema, sequence và constraints.
15. Kiểm tra test report thực của Gradle có **14 @Test** và số FAIL/SKIPPED hợp lý; không coi số lượng code mẫu là kết quả CI đã chạy.

## 20. Checklist trước khi merge JPA test

- [ ] Test muốn kiểm tra entity mapping, repository query, database constraint hay transaction boundary?
- [ ] `@DataJpaTest` có tải đúng entity/repository và dùng datasource test thích hợp?
- [ ] Entity có no-arg constructor, `@Id`, ID strategy và annotations `jakarta.persistence` đúng Boot 3.x?
- [ ] Fixture được tạo bằng `persist`/`persistAndFlush` và có ISBN/ID độc lập với các tests khác?
- [ ] Nếu cần DB synchronization, đã gọi `flush` đúng chỗ?
- [ ] Nếu cần đọc ngoài L1 context, đã gọi `clear` trước `find`/repository query?
- [ ] Không hiểu `clear` thành xóa dữ liệu database hay `flush` thành commit?
- [ ] Với entity detached, không kỳ vọng mutate tự được ghi; dùng merge/managed instance khi cần?
- [ ] Có test both success and invalid/constraint cases khi domain yêu cầu?
- [ ] Với unique/foreign key violation, test riêng và không tiếp tục dùng transaction lỗi?
- [ ] Có tránh dùng `persistFlushFind` như bằng chứng mặc định rằng L1 cache đã clear trên Boot 3.3?
- [ ] Test không dựa vào ID cố định, order test methods hoặc sequence rollback?
- [ ] SQL constraint/migration trên database production-compatible đã được kiểm chứng khi cần?
- [ ] Có phân biệt một query trong cùng transaction với committed visibility bên ngoài?
- [ ] Có tránh bỏ qua JPA slice failures bằng cách tùy tiện mở full @SpringBootTest?
- [ ] Có xem test report thật, không chỉ khẳng định test chạy từ code mẫu?

## 21. Tài liệu chính thức

- [Spring Boot 3.3 — TestEntityManager API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/TestEntityManager.html): API `persist`, `persistAndFlush`, `persistFlushFind`, `clear`, `find` và helpers.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@DataJpaTest`, embedded database, transaction/rollback, TestEntityManager.
- [Jakarta Persistence 3.1 — EntityManager](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/EntityManager.html): `persist`, `flush`, `clear`, `find`, managed/detached.
- [Jakarta Persistence specification](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1.html): lifecycle states, dirty checking và flush modes.
- [Spring Data JPA reference — Repositories](https://docs.spring.io/spring-data/jpa/reference/repositories.html): derived queries, repository testing và transaction behavior.
- [Spring Framework — Transactional Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transaction, rollback và `TestTransaction`.

## 22. Kết luận

**`TestEntityManager` là công cụ kiểm thử persistence context của Spring Boot, không phải một DB hay một transaction manager mới.** `persist` làm entity trở thành managed; `flush` đồng bộ thay đổi vào DB trong transaction; `clear` detach các managed entities để tránh đọc lại từ cache cấp một; `find` tìm theo khóa chính, có thể trả ngay managed instance nếu chưa clear.

Chuỗi **`persist → flush → clear → find`** là nền tảng của nhiều JPA repository tests đáng tin: nó kiểm tra dữ liệu sau khi được đồng bộ và sau khi context cũ không còn quản lý object ban đầu. Tuy nhiên, **flush không commit**, và **clear không bảo đảm vô hiệu hóa second-level cache**. Trên Spring Boot 3.3, helper `persistFlushFind` không phải thay thế cho explicit `clear` khi mục tiêu là kiểm tra boundary của L1 cache. Kết hợp JUnit Jupiter, `@DataJpaTest`, TestEntityManager, repository queries và một ít JDBC assertions sẽ giúp tách rõ lỗi mapping, caching, transaction và dữ liệu trong database.
