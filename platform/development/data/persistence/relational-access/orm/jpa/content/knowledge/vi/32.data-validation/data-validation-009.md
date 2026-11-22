# Kiểm thử validation cùng thời điểm flush thực tế

Trong JPA, một entity có thể chứa dữ liệu không hợp lệ trong bộ nhớ **trước khi** ứng dụng nhận được lỗi validation. Ví dụ, Java object có thể đã được gán `price = -100`, nhưng nếu không gọi Bean Validation tường minh, không có gì bắt buộc một setter thông thường phải ném `ConstraintViolationException` ngay tại dòng đó.

Lỗi có thể xuất hiện khi provider xử lý lifecycle persistence, khi `EntityManager.flush()` đồng bộ các thay đổi pending xuống database, hoặc khi transaction manager thực hiện flush/commit. Một truy vấn JPQL với flush mode phù hợp cũng có thể làm lỗi xuất hiện **tại chỗ chạy query**, dù query chỉ SELECT.

Ví dụ:

```java
CatalogItem item = em.find(CatalogItem.class, itemId);

item.setPrice(new BigDecimal("-100")); // Chỉ thay đổi Java state.

em.flush(); // Có thể kích hoạt Bean Validation ở pre-update
            // và ném jakarta.validation.ConstraintViolationException.
```

Để hiểu đúng validation trong ứng dụng Java/JPA, không đủ chỉ viết unit test:

```java
validator.validate(item);
```

Ta còn cần **integration test có persistence context, transaction, JPA provider, Bean Validation provider và database thật**, để xác minh lỗi xuất hiện trong lifecycle persistence khi flush diễn ra.

Bài **“Kiểm thử validation cùng thời điểm flush thực tế”**, thuộc chương **Kiểm tra dữ liệu** của chủ đề **Data Persistence Relational Access ORM JPA**, hướng dẫn thiết kế các kiểm thử đó: từ thiết lập fixture, xác minh cấu hình `ValidationMode`, kiểm thử create/update/merge/cascade, query-triggered flush, commit-only failures, phân biệt Bean Validation với database constraints, xử lý rollback, kiểm thử Spring Data JPA và quan sát SQL.

**Mục tiêu trung tâm:** xác định đúng *validation nào được kích hoạt, trên object nào, ở mốc nào của transaction và bằng chứng gì chứng minh database cuối cùng không nhận dữ liệu không hợp lệ*.

Ví dụ dùng Java 17+, Jakarta Persistence (`jakarta.persistence`), Jakarta Bean Validation (`jakarta.validation`) và JUnit 5. Các ví dụ Spring hoặc Hibernate là phần mở rộng có ghi rõ. DDL và cấu hình kết nối cần điều chỉnh theo database/provider thực tế. Những giả định về thời điểm thực thi SQL cụ thể phải được kiểm tra trên đúng stack triển khai, không suy từ tên phương thức đơn lẻ.

---

## 1. Ba loại phép thử thường bị gộp làm một

Giả sử `CatalogItem` có:

```java
@NotBlank
private String name;

@NotNull
@DecimalMin("0.00")
private BigDecimal price;
```

Có ít nhất ba câu hỏi độc lập:

1. **Bean Validation thuần:** Nếu gọi `validator.validate(item)`, các constraints có báo vi phạm không?
2. **JPA lifecycle integration:** Khi một managed entity được persist hoặc update và provider flush, validation có được kích hoạt và báo lỗi không?
3. **Database integrity:** Nếu bỏ qua Bean Validation (ví dụ chạy JDBC/native SQL), database có chặn giá trị vi phạm `NOT NULL`/`CHECK` thật không?

Ba phép thử khác nhau:

| Phép thử | Có EntityManager? | Có transaction/database? | Điều chứng minh |
| --- | --- | --- | --- |
| `validator.validate(item)` | Không cần | Không cần | Constraint metadata và Validator hoạt động |
| `em.persist/modify; em.flush()` | Có | Có | JPA lifecycle phối hợp validation khi đồng bộ |
| JDBC INSERT/UPDATE trực tiếp | Không cần JPA | Có | Ràng buộc database thật sự tồn tại |
| `em.getTransaction().commit()` | Có | Có | Flush còn lại và transaction completion |
| Spring service `@Transactional` | Có qua framework | Có | Toàn boundary, gồm flush/commit do transaction manager thực hiện |

**Một unit test gọi Validator thành công không chứng minh `flush()` sẽ gọi Validator.** Và một integration test flush thành công không chứng minh mọi database constraint đã được kiểm tra nếu database hỗ trợ deferred constraints.

## 2. Bốn thời điểm phải phân biệt

Trong workflow cập nhật:

```text
T0: Java setter / domain method
        │
        │  Chỉ sửa state của object.
        ▼
T1: Validator.validate(entity) — nếu ứng dụng gọi
        │
        │  Kiểm tra Java object ngay tại lời gọi.
        ▼
T2: EntityManager.flush()
        │
        ├─ Dirty checking / lifecycle event
        ├─ Bean Validation integration nếu enabled
        ├─ SQL INSERT/UPDATE/DELETE
        └─ Database constraints có thể báo lỗi
        ▼
T3: Transaction commit
        │
        ├─ Flush pending changes nếu còn
        ├─ Deferred DB constraint / concurrency check
        └─ Commit thành công hoặc rollback/failure
```

Các mốc này **không phải lúc nào cũng tồn tại như bốn bước riêng**. Có thể không gọi Validator tường minh; INSERT đôi khi xảy ra sớm để sinh ID; flush có thể do query; và commit có thể là lần đầu provider đồng bộ các changes.

Hệ quả cho việc viết test:

- Muốn kiểm tra object constraint độc lập, gọi `Validator` trực tiếp.
- Muốn kiểm tra tích hợp JPA, ép provider đi qua lifecycle với `flush()`.
- Muốn kiểm tra transaction hoàn tất, để `commit()` xảy ra trong phạm vi `assertThrows`/error handling.
- Muốn kiểm tra DB constraints, có thể cần đường ghi bỏ qua entity validation.
- Muốn kết luận rollback, đọc lại DB bằng context mới sau transaction lỗi.

## 3. Từ setter tới SQL không phải đường đi đồng bộ tức thì

JPA quản lý entity bằng persistence context và **dirty checking**. Ví dụ:

```java
em.getTransaction().begin();

CatalogItem item = em.find(CatalogItem.class, id);

item.setPrice(new BigDecimal("-10"));

System.out.println(item.getPrice()); // -10 trong Java object.

em.getTransaction().commit();
```

Lời gọi `setPrice` thường chỉ thay state của managed entity. Nếu không có validation trong setter/domain method, exception có thể đến muộn ở lần flush/commit.

**Không đặt test kiểu “gán giá âm phải lập tức ném `ConstraintViolationException`” nếu điều cần chứng minh là JPA lifecycle Bean Validation.** Test đó chỉ đúng khi setter hoặc domain method tự validate.

Một dạng test thích hợp hơn:

```java
item.setPrice(new BigDecimal("-10"));

assertThrows(
    jakarta.validation.ConstraintViolationException.class,
    em::flush
);
```

Nhưng test này chỉ có ý nghĩa khi entity **đã managed, dirty, trong active transaction, có Bean Validation provider và integration được bật**.

---

## 4. Entity mẫu để kiểm thử

Ta sử dụng một entity có các thuộc tính kiểm tra dễ hiểu:

```java
package com.example.validation;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

@Entity
@Table(name = "catalog_items")
public class CatalogItem {

    @Id
    private Long id;

    @Version
    private Long version;

    @NotBlank
    @Size(max = 120)
    @Column(nullable = false, length = 120)
    private String name;

    @NotNull
    @DecimalMin("0.00")
    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    protected CatalogItem() {
    }

    public CatalogItem(Long id, String name, BigDecimal price) {
        this.id = id;
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setName(String name) {
        this.name = name;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }
}
```

**Chú thích thiết kế:** hai setters trong entity mẫu *cố ý không tự validate* để bài test cô lập cơ chế Bean Validation ở flush. Trong domain model production, các invariants thường nên được kiểm tra sớm qua constructor/domain methods; không nên sao chép hai setters “chấp nhận mọi giá trị” cho một aggregate nhạy cảm.

`@Id` là assigned ID, không `@GeneratedValue`, để các bài test có thể kiểm soát mốc INSERT mà không bị chiến lược `IDENTITY` ép SQL sớm để lấy khóa. Cách này chỉ phục vụ fixture và không khẳng định mọi ứng dụng nên dùng assigned IDs.

`@Version` dành cho các bài test phân biệt validation failure với optimistic concurrency failure. Nó không tự kiểm tra `price >= 0`.

## 5. Schema cần phù hợp với bài test

DDL tham khảo:

```sql
CREATE TABLE catalog_items (
    id BIGINT PRIMARY KEY,
    version BIGINT,
    name VARCHAR(120) NOT NULL,
    price DECIMAL(14,2) NOT NULL,
    CONSTRAINT ck_catalog_item_price
        CHECK (price >= 0)
);
```

Schema trên đưa thêm database CHECK để kiểm thử lớp bảo vệ cuối. `version` và kiểu sinh giá trị ban đầu cần phù hợp mapping/provider; production schema nên được quản lý bằng migrations.

Đối với **test Bean Validation trước SQL**, có CHECK vẫn không sao, nhưng ta phải nhận diện exception thật: nếu nhận `jakarta.validation.ConstraintViolationException` thì Bean Validation đã báo lỗi; nếu chỉ nhận database CHECK violation, đó **chưa chứng minh JPA Bean Validation được kích hoạt**.

Một chiến lược test tốt tách hai nhóm:

- **Validation integration tests**: kỳ vọng Bean Validation violation từ entity lifecycle.
- **Database constraint tests**: dùng SQL bỏ qua entity callbacks/Bean Validation và kỳ vọng DB reject.

Nếu không tách, test có thể xanh “vì DB CHECK chặn” trong khi Bean Validation integration đã bị tắt.

## 6. Các thành phần runtime bắt buộc cho integration test

Để kiểm thử JPA lifecycle validation, cần một stack thật:

```text
JUnit 5
   │
   ├─ Jakarta Persistence API
   ├─ JPA provider (ví dụ Hibernate ORM)
   ├─ Jakarta Validation API
   ├─ Bean Validation implementation (ví dụ Hibernate Validator)
   ├─ JDBC driver / DataSource
   └─ Database có schema phù hợp
```

**Có annotation `@NotBlank` trong source không tự bảo đảm Bean Validation runtime integration.** Nếu thiếu implementation, dùng validation mode/config sai hoặc disable callbacks, JPA có thể không chạy các constraints như dự kiến.

Ví dụ trong Maven/Gradle dependencies cần có:

- JUnit Jupiter.
- Jakarta Persistence API tương thích.
- ORM provider.
- Jakarta Validation API.
- Validation provider.
- Database JDBC driver.
- Test database hoặc Testcontainers.
- Tích hợp logging/SQL capture nếu cần quan sát.

Phiên bản artifact và cách khai báo dependencies phụ thuộc dự án. Bài tập trung hành vi JPA, không yêu cầu một version cố định để hiểu timing.

## 7. Cấu hình persistence unit để bật validation

Ví dụ `META-INF/persistence.xml` theo Jakarta Persistence 3.1:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit
        name="validationDemoPU"
        transaction-type="RESOURCE_LOCAL">

        <class>com.example.validation.CatalogItem</class>

        <validation-mode>CALLBACK</validation-mode>

        <properties>
            <!-- JDBC/DataSource và provider settings
                 được bổ sung theo môi trường test. -->
        </properties>
    </persistence-unit>
</persistence>
```

Ý nghĩa:

- `RESOURCE_LOCAL`: ví dụ test tự begin/commit/rollback qua `EntityTransaction`.
- `validation-mode=CALLBACK`: yêu cầu tích hợp Bean Validation lifecycle callbacks; cần Bean Validation implementation phù hợp.
- `CatalogItem`: entity được provider quản lý.
- JDBC settings/schema phải được cấu hình thật, không thể chỉ copy XML này rồi mong có database.

`AUTO` thường là default theo JPA trong môi trường thích hợp, nhưng **test validation timing nên chọn mode có chủ ý và xác nhận provider đã tích hợp thật**, tránh test “xanh ngẫu nhiên” nhờ CHECK ở DB.

## 8. `ValidationMode.AUTO`, `CALLBACK` và `NONE`

| Mode | Tác dụng | Hệ quả khi kiểm thử |
| --- | --- | --- |
| `AUTO` | Kích hoạt integration theo việc Bean Validation provider có mặt | Có thể thay đổi khi runtime/classpath khác nhau; nên xác minh |
| `CALLBACK` | Yêu cầu lifecycle validation callback integration | Hữu ích để test rõ cơ chế, nhưng thiếu provider phù hợp có thể lỗi bootstrap |
| `NONE` | Không chạy automatic Bean Validation lifecycle qua JPA | Phù hợp đối chứng để chắc DB constraint và explicit validation được phân biệt |

Ví dụ:

```xml
<validation-mode>NONE</validation-mode>
```

không vô hiệu `validator.validate(item)` **nếu** ứng dụng gọi Validator tường minh. Nó chỉ tắt phần automatic JPA lifecycle integration theo mode.

`NONE` cũng **không tắt NOT NULL/CHECK/UNIQUE/FK ở database**.

Vì vậy một test fail tại DB trong mode NONE có thể là database constraint failure, không phải Bean Validation ở flush.

## 9. Nhận diện đúng exception trước khi viết assertion

Có hai exception phổ biến cùng tên ngắn:

```java
jakarta.validation.ConstraintViolationException
```

và:

```java
org.hibernate.exception.ConstraintViolationException
```

Chúng không giống nhau.

| Exception | Nguồn gốc thường gặp | Thông tin quan trọng |
| --- | --- | --- |
| `jakarta.validation.ConstraintViolationException` | Bean Validation | `getConstraintViolations()` chứa property path, message, invalid value |
| `org.hibernate.exception.ConstraintViolationException` | Hibernate ORM bọc lỗi DB constraint | SQLState, constraint name, JDBC cause theo API provider |
| `jakarta.persistence.PersistenceException` | JPA provider | Có thể bọc exception từ validation hoặc DB |
| `jakarta.persistence.RollbackException` | Commit/transaction failure | Cause chain có thể chứa validation/constraint/concurrency error |
| Spring `DataIntegrityViolationException` | Spring DAO exception translation | Thường phản ánh DB integrity issue, cần xem nguyên nhân |
| Spring `TransactionSystemException` | Transaction manager | Có thể bao ngoại lệ sâu hơn tùy stack |

Trong test nhắm đến Bean Validation, đừng chỉ viết:

```java
assertThrows(RuntimeException.class, em::flush);
```

vì một lỗi SQL khác hay `NullPointerException` cũng có thể làm test xanh.

Thay vào đó, xác nhận **đúng exception type hoặc cause chain** và property path/constraint mà bài test nhắm tới.

## 10. Một helper phát hiện Bean Validation trong exception chain

Khi gọi explicit `flush()` trên Hibernate/Jakarta phù hợp, có thể nhận `jakarta.validation.ConstraintViolationException` trực tiếp. Nhưng commit/transaction manager đôi khi bọc exception. Trong test tích hợp portable hơn, có thể dùng helper:

```java
static jakarta.validation.ConstraintViolationException
findBeanValidationViolation(Throwable failure) {

    Throwable current = failure;

    while (current != null) {
        if (current instanceof
                jakarta.validation.ConstraintViolationException violation) {
            return violation;
        }

        current = current.getCause();
    }

    throw new AssertionError(
        "Expected Jakarta Bean Validation violation",
        failure
    );
}
```

Helper không parse `exception.getMessage()` và không nhầm với Hibernate ORM SQL exception.

Ví dụ:

```java
RuntimeException failure = assertThrows(
    RuntimeException.class,
    () -> {
        em.flush();
    }
);

var violation = findBeanValidationViolation(failure);

assertFalse(violation.getConstraintViolations().isEmpty());
```

Nếu provider bọc lỗi theo một cơ chế khác, test cần tuân contract stack đó; không nên biến helper quá rộng để một exception bất kỳ đều được coi là validation.

## 11. Một helper kiểm tra property path

Để đảm bảo lỗi đúng ở field `price`:

```java
static Set<String> violatedPaths(
        jakarta.validation.ConstraintViolationException ex) {

    return ex.getConstraintViolations().stream()
        .map(v -> v.getPropertyPath().toString())
        .collect(Collectors.toSet());
}
```

Trong test:

```java
assertTrue(
    violatedPaths(violation).contains("price")
);
```

Ưu điểm:

- Xác định đúng constraint target.
- Tránh phụ thuộc ngôn ngữ của message template.
- Không hardcode toàn bộ message tiếng Anh.
- Dễ phân biệt lỗi `name` với lỗi `price`.

Nếu có nested `@Valid`, property path có thể là `shippingAddress.city` hoặc chứa indexed collection nodes; không nên assume mọi path chỉ là một từ đơn giản.

---

## 12. Chuẩn bị JUnit fixture quản lý EntityManagerFactory

Một test class resource-local:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;
import jakarta.validation.ConstraintViolationException;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.*;

class CatalogValidationIT {

    private static EntityManagerFactory emf;

    private static final AtomicLong IDS =
        new AtomicLong(10_000L);

    @BeforeAll
    static void startPersistenceUnit() {
        emf = Persistence.createEntityManagerFactory(
            "validationDemoPU"
        );
    }

    @AfterAll
    static void closePersistenceUnit() {
        if (emf != null) {
            emf.close();
        }
    }

    private static Long nextId() {
        return IDS.incrementAndGet();
    }

    // Các @Test và helper bên dưới minh họa
    // các tình huống riêng biệt.
}
```

Ví dụ này giả định schema đã có trước khi test bắt đầu. Nếu dùng Testcontainers, khởi động database container và cung cấp JDBC config trước khi bootstrap EntityManagerFactory.

### Vì sao EntityManagerFactory sống lâu hơn test?

Tạo EntityManagerFactory thường tốn chi phí; mỗi test tạo **EntityManager riêng**, còn factory có thể dùng chung theo lifecycle JUnit class.

Không dùng chung một EntityManager cho các test chạy song song, vì EntityManager không thread-safe, và L1 managed state có thể làm nhiễu kết quả.

## 13. Helper transaction để tránh che exception

Một helper:

```java
static <T> T inTransaction(
        EntityManagerFactory emf,
        Function<EntityManager, T> work) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        T result = work.apply(em);

        em.getTransaction().commit();

        return result;
    } catch (RuntimeException failure) {
        if (em.getTransaction().isActive()) {
            try {
                em.getTransaction().rollback();
            } catch (RuntimeException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
        }
        throw failure;
    } finally {
        em.close();
    }
}
```

Cần import `java.util.function.Function`.

Helper này làm rõ **đơn vị công việc gồm cả commit**. Khi test failure tại commit, exception có thể được ném sau khi `work.apply(...)` trả về.

Để kiểm tra **đúng điểm flush**, ta vẫn gọi `em.flush()` bên trong lambda hoặc một method riêng, không chỉ rely on helper commit.

**Không dùng helper resource-local trên Spring/JTA container-managed EntityManager**; với các stack đó, transaction manager phải quản lý commit/rollback.

## 14. Seed dữ liệu hợp lệ và commit trước mỗi scenario

Ví dụ:

```java
static Long seedValidItem(EntityManagerFactory emf) {
    Long id = IDS.incrementAndGet();

    inTransaction(emf, em -> {
        CatalogItem item = new CatalogItem(
            id,
            "Keyboard",
            new BigDecimal("150000.00")
        );

        em.persist(item);
        return null;
    });

    return id;
}
```

Sau khi helper trả về, transaction đã commit và EntityManager đã close, nên lần test tiếp theo tải CatalogItem vào **persistence context mới**.

Điều này quan trọng cho update validation test:

- Nếu test vẫn giữ object từ seed ở cùng context, dirty-state/lifecycle có thể không như dự định.
- Nếu seed chưa commit, một query khác có thể không nhìn thấy row.
- Nếu dùng một transaction lớn cho toàn bộ test, rollback mặc định có thể làm bạn nhầm rằng data đã persist bền vững.

Fixture cần dùng IDs riêng để tránh đụng các test chạy song song hoặc database dùng chung.

---

## 15. Test 1: Bean Validation thuần, chưa có JPA

Trước khi nói tới flush, xác minh constraint trên Java object thực sự hoạt động:

```java
@Test
void validatorRejectsNegativePrice() {
    CatalogItem item = new CatalogItem(
        1L,
        "Keyboard",
        new BigDecimal("-1.00")
    );

    Set<ConstraintViolation<CatalogItem>> failures =
        validator.validate(item);

    assertTrue(
        failures.stream()
            .anyMatch(v ->
                v.getPropertyPath().toString().equals("price"))
    );
}
```

`validator` là `jakarta.validation.Validator` được tạo từ `ValidatorFactory` tại test fixture.

Test này có thể chạy hoàn toàn không có database. Kết luận:

> “@DecimalMin có hiệu lực khi Validator.validate được gọi.”

Nó **không chứng minh**:

- JPA provider tích hợp Bean Validation.
- `@PreUpdate` lifecycle validation được bật.
- `EntityManager.flush()` thực sự phát hiện giá âm.
- Database có CHECK.
- Transaction rollback sau violation.

Đó là lý do phải thêm integration tests.

## 16. Test 2: update managed entity, ép flush thật

Đây là test trung tâm của bài.

```java
@Test
void invalidManagedUpdateFailsOnExplicitFlush() {
    Long id = seedValidItem(emf);

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        CatalogItem item = em.find(
            CatalogItem.class,
            id
        );

        assertNotNull(item);

        item.setPrice(new BigDecimal("-100.00"));

        RuntimeException failure = assertThrows(
            RuntimeException.class,
            em::flush
        );

        var validation =
            findBeanValidationViolation(failure);

        assertTrue(
            violatedPaths(validation).contains("price")
        );
    } finally {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }

        em.close();
    }
}
```

Điều test chứng minh khi chạy trên stack có validation integration:

1. Entity được load thành **managed**.
2. Price được thay đổi nên entity dirty.
3. `flush()` buộc provider xử lý pending update.
4. Lifecycle Bean Validation phát hiện `price < 0`.
5. Exception thực sự đến từ Jakarta Validation, không phải chỉ CHECK violation.
6. Transaction được rollback/EntityManager được close.

Đây là **test thực thi flush**, khác unit test `Validator.validate`.

### Vì sao seed bằng một transaction riêng?

Để update đúng một row đã commit, tránh trường hợp provider gộp insert/update hoặc chưa có row cần thay đổi.

### Vì sao assert bên trong try/finally?

Để transaction và EntityManager luôn được dọn ngay cả khi assertion thất bại. Không để test rò connection hoặc giữ transaction treo.

## 17. Test 3: chứng minh setter không tự kích hoạt JPA validation

Trong entity mẫu, setter chỉ gán field.

```java
@Test
void settingInvalidValueAloneDoesNotFlush() {
    Long id = seedValidItem(emf);

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        CatalogItem item = em.find(
            CatalogItem.class,
            id
        );

        assertDoesNotThrow(
            () -> item.setPrice(new BigDecimal("-1"))
        );

        assertEquals(
            new BigDecimal("-1"),
            item.getPrice()
        );

        // Không flush hoặc commit thay đổi.
    } finally {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }

        em.close();
    }
}
```

Test này **chỉ đúng cho setter cố ý không validate** ở entity mẫu. Nếu domain method đã kiểm tra giá không âm, setter có thể ném `IllegalArgumentException` ngay và đó là một thiết kế production hoàn toàn hợp lý.

Mục tiêu học tập là phân biệt:

- Exception từ domain setter.
- Exception từ `Validator.validate` tường minh.
- Exception từ JPA lifecycle validation khi flush.
- Exception từ DB constraints khi SQL chạy.

Không phải mọi lỗi tại setter là Bean Validation callback.

## 18. Test 4: sau rollback, database giữ giá trị đã commit

Lỗi validation là một phần; còn phải chứng minh transaction không commit dữ liệu xấu.

```java
@Test
void rollbackKeepsCommittedPriceAfterValidationFailure() {
    Long id = seedValidItem(emf);

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        CatalogItem item = em.find(
            CatalogItem.class, id
        );

        item.setPrice(new BigDecimal("-50.00"));

        assertThrows(
            RuntimeException.class,
            () -> {
                try {
                    em.flush();
                } catch (RuntimeException ex) {
                    findBeanValidationViolation(ex);
                    throw ex;
                }
            }
        );
    } finally {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }

        em.close();
    }

    BigDecimal committed = inTransaction(
        emf,
        fresh -> fresh.find(CatalogItem.class, id)
            .getPrice()
    );

    assertEquals(
        0,
        committed.compareTo(new BigDecimal("150000.00"))
    );
}
```

Khi kiểm tra giá, dùng `BigDecimal.compareTo` nếu chỉ cần **numeric equality**; `equals` còn so sánh scale, có thể khác sau DB DECIMAL hydration.

**Đọc bằng EntityManager mới** là quan trọng. Entity từ context rollback vẫn có thể mang `price = -50` trong Java heap, không phản ánh database đã commit.

## 19. Test 5: persist một entity mới không hợp lệ

Đối với INSERT, validation có thể gắn với thao tác persist/insert lifecycle. Thời điểm provider thực thi SQL có thể khác theo ID generation và implementation.

Một test tránh buộc lỗi phải xuất hiện ở `flush` đúng một dòng nếu provider có quyền validate sớm:

```java
@Test
void invalidNewEntityIsRejectedByJpaLifecycle() {
    Long id = IDS.incrementAndGet();

    RuntimeException failure = assertThrows(
        RuntimeException.class,
        () -> inTransaction(emf, em -> {
            CatalogItem invalid = new CatalogItem(
                id,
                " ",
                new BigDecimal("10.00")
            );

            em.persist(invalid);
            em.flush();
            return null;
        })
    );

    var validation =
        findBeanValidationViolation(failure);

    assertTrue(
        violatedPaths(validation).contains("name")
    );
}
```

Test bao cả `persist`, `flush` và `commit` của helper. Nếu validation xảy ra sớm ở persist, test vẫn xác minh đúng JPA lifecycle integration.

### Muốn test đúng timing INSERT tại flush?

Chỉ assert đúng dòng `flush` khi bạn đã kiểm soát ID generation, provider và behavior tương ứng. Ví dụ với assigned IDs hoặc SEQUENCE, nhiều providers trì hoãn INSERT tới flush, nhưng đó không phải một quy tắc portable tuyệt đối cho mọi provider.

**Đừng gắn correctness của validation với một dòng Java cố định khi spec cho phép timing khác.**

## 20. Test 6: cùng entity, validation sau khi đổi nhiều fields

Giả sử:

```java
item.setName(" ");
item.setPrice(new BigDecimal("-10"));
```

Test:

```java
@Test
void flushReportsMultipleObjectViolations() {
    Long id = seedValidItem(emf);

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        CatalogItem item = em.find(
            CatalogItem.class, id
        );

        item.setName(" ");
        item.setPrice(new BigDecimal("-10"));

        RuntimeException failure =
            assertThrows(RuntimeException.class, em::flush);

        var validation =
            findBeanValidationViolation(failure);

        Set<String> paths = violatedPaths(validation);

        assertTrue(paths.contains("name"));
        assertTrue(paths.contains("price"));
    } finally {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        em.close();
    }
}
```

Bean Validation thông thường trả tập violations; **không nên assert thứ tự** của `ConstraintViolation` vì thứ tự không được thiết kế như một hợp đồng hiển thị cố định.

Nếu cấu hình group sequence fail-fast hoặc provider-specific fast-fail behavior, số violations có thể khác. Khi cần assert cả hai fields, đảm bảo test config không bật fail-fast và validation groups chứa cả hai constraints.

## 21. Test 7: entity không dirty thì chưa chắc có pre-update validation

Một tình huống thường gặp:

```java
em.getTransaction().begin();

CatalogItem item = em.find(CatalogItem.class, id);

em.flush(); // Không thay đổi persistent state.

em.getTransaction().commit();
```

Không nên kết luận `@PreUpdate`/validation sẽ tự chạy cho mọi managed entity chỉ vì gọi `flush`.

JPA thường xác định những entity cần UPDATE dựa trên dirty checking. Nếu entity không dirty, không cần phát SQL UPDATE và không có lý do mặc định chạy pre-update validation cho nó.

### Test đặc biệt về dữ liệu vốn đã sai trong DB

Giả sử database legacy chứa một row `price=-5`, nhưng không có CHECK. Khi load entity mà không thay đổi:

```java
CatalogItem item = em.find(CatalogItem.class, id);
em.flush();
```

Không nên xem flush là một lệnh “quét validation lại toàn bộ những entity đã đọc”. Để kiểm tra dữ liệu legacy khi đọc, gọi `validator.validate(item)` tường minh hoặc chạy data-quality query/migration.

**Lifecycle validation gắn với persistence operations, không phải một scanner tự động cho mọi object trong context.**

## 22. `@PreUpdate` có thể không chạy khi chỉ sửa `@Transient`

Ví dụ:

```java
@Transient
private boolean selectedInUi;
```

Ứng dụng thay:

```java
item.setSelectedInUi(true);
em.flush();
```

Nếu không có persistent field dirty, provider thường không tạo SQL UPDATE. Vì vậy không nên kỳ vọng pre-update validation chạy chỉ vì transient UI state đổi.

Nếu một rule validation quan trọng phụ thuộc cả transient fields, hãy cân nhắc **validate request DTO** hoặc gọi Validator rõ ràng tại use-case boundary.

Sửa transient field có thể hợp lệ trong Java nhưng không phải persistence operation.

## 23. `@Version` không phải constraint giá trị

Một entity có:

```java
@Version
private Long version;
```

và:

```java
@DecimalMin("0.00")
private BigDecimal price;
```

Khi transaction sửa price âm:

- Bean Validation có thể báo `price` không hợp lệ trước SQL UPDATE.
- Nếu Bean Validation tắt/bypass, DB CHECK có thể báo lỗi.
- Nếu cùng lúc có transaction khác sửa entity, version check có thể gây `OptimisticLockException`.
- Lỗi nào xuất hiện trước phụ thuộc nơi thực thi, provider, flush ordering và transaction schedule.

Không nên viết test chỉ assert bất kỳ RuntimeException rồi kết luận đó là “validation giá âm”. Xác minh **đúng loại exception và property path**.

---

## 24. Validation groups khi flush

Jakarta Bean Validation cho phép nhóm constraints:

```java
public interface OnCreate {}
public interface OnUpdate {}
```

Entity:

```java
@NotBlank(groups = OnCreate.class)
private String externalCode;

@NotNull(groups = {OnCreate.class, OnUpdate.class})
@DecimalMin(
    value = "0.00",
    groups = {OnCreate.class, OnUpdate.class}
)
private BigDecimal price;
```

Khi gọi:

```java
validator.validate(item, OnCreate.class);
validator.validate(item, OnUpdate.class);
```

ta chủ động chọn groups. Nhưng **JPA lifecycle validation group** còn được cấu hình riêng ở persistence unit.

Ví dụ thuộc tính chuẩn:

```properties
jakarta.persistence.validation.group.pre-persist
jakarta.persistence.validation.group.pre-update
jakarta.persistence.validation.group.pre-remove
```

Chúng quy định groups áp dụng cho lifecycle validation events tương ứng.

### Lưu ý về group Default

Constraint không khai báo `groups` thuộc `Default`. Nếu JPA chỉ validate Default ở pre-update, một constraint chỉ thuộc `OnUpdate` **không tự được chạy** trừ khi pre-update validation groups được cấu hình bao gồm OnUpdate (hoặc group sequence/inheritance phù hợp).

Test cần bám **groups thực sự được kích hoạt**, không chỉ nhìn annotation.

## 25. Kiểm thử pre-persist và pre-update groups khác nhau

Giả sử:

- SKU chỉ bắt buộc trong create.
- Price được kiểm tra ở create và update.

Test:

```text
Tình huống A: tạo Product thiếu SKU
    → pre-persist group chứa OnCreate
    → kỳ vọng validation failure

Tình huống B: update Product chỉ thay price
    → pre-update group chứa OnUpdate
    → kỳ vọng price check

Tình huống C: pre-update không chứa OnCreate
    → không kỳ vọng constraint chỉ thuộc OnCreate
       tự phát tại pre-update
```

Điểm kiểm soát:

1. Lấy đúng config runtime, không đoán provider default.
2. Seed entity phù hợp với schema.
3. Dùng transaction riêng cho mỗi event.
4. Explicit flush nếu muốn kích hoạt pre-update ngay trong test.
5. Assert constraint paths/groups, không chỉ method return value.
6. Nếu pre-persist constraint mạnh hơn pre-update, nhớ DB schema vẫn có thể cấm giá trị không hợp lệ bất kể group.

Không tạo test group mà database CHECK/NOT NULL chặn trước khi bạn có cơ hội quan sát rule mình đang muốn chứng minh.

## 26. Pre-remove validation không giống pre-update

JPA hỗ trợ validation group configuration cho lifecycle pre-remove, nhưng **không nên tự giả định tất cả entity constraints dùng để tạo/cập nhật đều phải chạy khi DELETE**.

Ví dụ Product đang thiếu name do legacy data nhưng người dùng muốn xóa. Nếu hệ thống validate đầy đủ mọi field ngay trước remove, thao tác xóa dữ liệu xấu có thể bị chặn không cần thiết.

Một chính sách có thể chọn pre-remove groups riêng khi nghiệp vụ muốn bảo vệ operation remove. Ví dụ:

- Không cho xóa một entity nếu còn trạng thái cần giải quyết.
- Hoặc không validate gì ở pre-remove, để service kiểm tra rule xóa.

Tuy nhiên, **business rule xóa** (authorization, FK relationships, trạng thái order) thường thuộc service/DB constraints, không nên nhét hết vào Bean Validation pre-remove group.

### Test đúng event

Một test cần seed entity rồi gọi:

```java
CatalogItem item = em.find(CatalogItem.class, id);

em.remove(item);
em.flush();
```

và xác minh đúng pre-remove group đã cấu hình, thay vì lấy validation pre-update và kết luận nó cũng áp dụng cho DELETE.

## 27. Tích hợp lifecycle callbacks với validation

Entity có thể có:

```java
@PrePersist
void normalizeBeforeInsert() {
    if (name != null) {
        name = name.trim();
    }
}
```

và:

```java
@NotBlank
private String name;
```

Ví dụ input:

```text
name = "   "
```

Sau trim:

```text
name = ""
```

và Bean Validation có thể báo `@NotBlank` tại lifecycle validation.

Điều cần hiểu:

- `@PrePersist` là JPA lifecycle callback.
- `@NotBlank` là Bean Validation constraint.
- Việc kích hoạt và ordering theo lifecycle specification/integration.
- Application vẫn nên validate input sớm nếu cần phản hồi nhanh.
- Callback không phải nơi portable để query DB hoặc gọi external service.

### Không dùng callback làm test thay Validator

Nếu một `@PrePersist` tự ném:

```java
throw new IllegalStateException("invalid");
```

thì test flush có thể thất bại, nhưng đó **không chứng minh Jakarta Bean Validation đã chạy**. Cần xác định đúng exception/violation metadata.

## 28. Cascaded `@Valid` có thể kích hoạt nhiều violations

Một DTO:

```java
public record ShippingAddress(
    @NotBlank String city,
    @NotBlank String street
) {}

public record OrderRequest(
    @NotNull Long customerId,
    @Valid @NotNull ShippingAddress address
) {}
```

Gọi:

```java
validator.validate(orderRequest);
```

có thể báo `address.city`.

Với entity associations/embeddables, `@Valid` cũng có thể yêu cầu cascaded Bean Validation theo spec. Tuy nhiên, **Bean Validation cascade khác JPA cascade**:

- `@Valid`: validate nested object.
- `CascadeType.PERSIST`: persist related entity.
- `CascadeType.MERGE`: merge related entity.
- `orphanRemoval`: xử lý remove của orphan.
- `@EntityListeners`: lifecycle hooks.

Khi test một nested field fail ở flush, cần xác định nested object **thực sự thuộc graph được validate**, constraints được kích hoạt và JPA có persistence operation phù hợp.

Đừng mặc định mọi entity trong relationship graph tự được validate chỉ vì quan hệ có `cascade = PERSIST`.

## 29. Persist graph và thứ tự errors

Giả sử Order cascade persist sang hai OrderLines. Một line có quantity âm.

```java
em.persist(order);
em.flush();
```

Validation có thể xảy ra trên child entity hoặc cascaded `@Valid` graph tùy mapping/config. Provider cũng phải xử lý FK/INSERT ordering.

Vì vậy:

- Không assert chính xác **thứ tự** các violations trong tập.
- Không dựa vào số lượng SQL INSERT cố định nếu batching/ID strategy khác.
- Không coi exception trên parent `persist` là bằng chứng lỗi chỉ nằm ở parent.
- Không dùng callback count hoặc SQL log duy nhất để suy object graph correctness.
- Kiểm tra parent/child paths và final committed rows phù hợp.

Một test tốt xác minh **đơn vị công việc không thể commit graph bất hợp lệ**, rồi kiểm tra cụ thể bean property error nếu tiêu chí là Bean Validation.

## 30. Merge detached entity: validation trên managed target

Một entity detached:

```java
CatalogItem detached = loadThenCloseContext(id);

detached.setPrice(new BigDecimal("-100.00"));
```

Khi:

```java
em.getTransaction().begin();

CatalogItem managedCopy = em.merge(detached);

em.flush();
```

`merge` không biến `detached` thành managed; nó trả về một managed representation có state được copy theo merge semantics.

Lỗi Bean Validation có thể xuất hiện khi provider cần insert/update managed entity tại flush/commit, hoặc sớm hơn theo provider/merge implementation.

### Test mẫu

```java
@Test
void invalidDetachedMergeIsRejected() {
    Long id = seedValidItem(emf);

    CatalogItem detached = inTransaction(
        emf,
        em -> em.find(CatalogItem.class, id)
    ); // EntityManager đóng → detached.

    detached.setPrice(new BigDecimal("-10.00"));

    RuntimeException failure = assertThrows(
        RuntimeException.class,
        () -> inTransaction(emf, em -> {
            em.merge(detached);
            em.flush();
            return null;
        })
    );

    var validation =
        findBeanValidationViolation(failure);

    assertTrue(
        violatedPaths(validation).contains("price")
    );
}
```

Chú ý: nếu version detached đã stale do transaction khác commit, bạn có thể nhận `OptimisticLockException` trước Bean Validation. Test cần cô lập concurrency, không thay đổi row giữa load và merge nếu mục tiêu chỉ là validation.

## 31. `persist()` và ID generation có thể ảnh hưởng timing

Các chiến lược ID:

```java
@GeneratedValue(strategy = GenerationType.IDENTITY)
@GeneratedValue(strategy = GenerationType.SEQUENCE)
@GeneratedValue(strategy = GenerationType.TABLE)
```

Có thể yêu cầu SQL khác nhau trước flush:

- `IDENTITY` thường cần INSERT để database sinh khóa, nên SQL/lifecycle validation có thể diễn ra sớm.
- `SEQUENCE` có thể lấy next sequence value trước INSERT nhưng trì hoãn INSERT tới flush.
- `TABLE` có thể cần thao tác bảng để cấp khóa.
- UUID/assigned ID không đòi hỏi cùng loại SQL cấp khóa.
- Providers/dialects có thể tối ưu khác.

Vì vậy test:

```java
em.persist(invalidEntity);
assertThrows(ConstraintViolationException.class, em::flush);
```

có thể **không phù hợp nếu provider đã ném ở `persist()`**.

Để kiểm thử portable về việc *entity không hợp lệ bị từ chối*, bao cả `persist/flush/commit` trong `assertThrows`. Để kiểm thử timing **đúng tại flush** trên một stack cụ thể, dùng mapping/ID strategy đã kiểm soát và assert mốc cụ thể.

## 32. Query có thể kích hoạt auto-flush trước SELECT

Một lỗi validation khiến developer khó hiểu:

```java
em.getTransaction().begin();

CatalogItem item = em.find(CatalogItem.class, id);

item.setPrice(new BigDecimal("-1"));

List<CatalogItem> results = em.createQuery(
    "SELECT i FROM CatalogItem i WHERE i.price > :min",
    CatalogItem.class
).setParameter("min", BigDecimal.ZERO)
 .getResultList();
```

Với `FlushModeType.AUTO`, provider cần xử lý những pending changes ảnh hưởng kết quả query. Một chiến lược phổ biến là **flush trước SELECT**.

Khi đó stack trace có thể chỉ đến:

```java
getResultList();
```

nhưng violation thực chất là:

```java
item.setPrice(new BigDecimal("-1"));
```

đã làm managed entity không hợp lệ, và query chỉ là nơi kích hoạt synchronization.

### Timeline

```text
find CatalogItem → managed price=100
setPrice(-1)     → dirty Java state, chưa thấy lỗi
JPQL SELECT      → provider auto-flush pending update
                → pre-update Bean Validation
                → ConstraintViolationException
SELECT SQL       → có thể chưa được gửi xuống DB
```

**Không phải mọi SELECT đều bắt buộc auto-flush tất cả dirty entities**, và flush decisions phụ thuộc query semantics/provider. Nếu muốn test riêng query-triggered validation, cần kiểm soát flush mode và query liên quan data đang dirty.

## 33. Test query-triggered AUTO flush

Một test theo provider cụ thể:

```java
@Test
void autoFlushMayExposeViolationAtQuery() {
    Long id = seedValidItem(emf);

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();
        em.setFlushMode(FlushModeType.AUTO);

        CatalogItem item = em.find(CatalogItem.class, id);
        item.setPrice(new BigDecimal("-1"));

        RuntimeException failure = assertThrows(
            RuntimeException.class,
            () -> em.createQuery(
                    "SELECT i FROM CatalogItem i " +
                    "WHERE i.price > :min",
                    CatalogItem.class
                )
                .setParameter("min", BigDecimal.ZERO)
                .getResultList()
        );

        var validation =
            findBeanValidationViolation(failure);

        assertTrue(
            violatedPaths(validation).contains("price")
        );
    } finally {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        em.close();
    }
}
```

Đây là **timing test theo provider/dialect/config**, không phải assertion bắt buộc cho mọi implementation. Nếu provider không auto-flush ở query cụ thể, nó có thể phát hiện khi explicit flush hoặc commit. Mục tiêu portable là bảo đảm invalid update không được commit, không phải ép SELECT luôn là nơi ném lỗi.

## 34. `FlushModeType.AUTO` và `COMMIT`

JPA có:

```java
em.setFlushMode(FlushModeType.AUTO);
em.setFlushMode(FlushModeType.COMMIT);
```

So sánh:

| Tình huống | AUTO | COMMIT |
| --- | --- | --- |
| Query phải bảo đảm tác động pending updates theo semantics JPA | Có yêu cầu nhất quán tương ứng; có thể auto-flush | Không có cùng bảo đảm query thấy pending changes trước commit |
| Query có thể là nơi validation xuất hiện | Có | Có thể tùy provider/explicit operations, không nên tuyệt đối hóa |
| `em.flush()` tường minh | Vẫn đồng bộ | Vẫn đồng bộ |
| Commit | Có thể flush/check | Có thể flush/check |
| Setter tự ném Bean Validation lifecycle | Không mặc định | Không mặc định |

`COMMIT` **không** có nghĩa provider bị cấm mọi SQL trước commit. Đặc biệt, explicit `em.flush()` vẫn yêu cầu synchronization, và ID generation/certain operations có thể tạo SQL sớm.

Một test có thể so sánh AUTO/COMMIT để quan sát stack cụ thể, nhưng không suy từ đó rằng mode COMMIT “tắt validation”.

## 35. `getSingleResult()` và `getResultStream()` cũng cần cẩn thận

Nếu một query khiến auto-flush, exception có thể xuất hiện tại:

- `getResultList()`.
- `getSingleResult()`.
- `getResultStream()`.
- Khi tiêu thụ stream/terminal operation, tùy provider/lazy execution.
- `executeUpdate()` của query nếu một lần flush được kích hoạt trước đó.

Ví dụ:

```java
try (Stream<CatalogItem> stream = em.createQuery(
        "SELECT i FROM CatalogItem i",
        CatalogItem.class
    ).getResultStream()) {

    stream.forEach(this::processItem);
}
```

Không khẳng định mọi provider luôn gửi SQL lúc gọi `getResultStream()` thay vì lúc terminal operation. Java Stream API và JDBC streaming behavior còn phụ thuộc implementation.

Nếu mục tiêu là xác định **lỗi validation ở một điểm rõ ràng**, dùng `em.flush()` trước khi bắt đầu streaming; vẫn xử lý lỗi transaction/commit ở boundary.

## 36. Flush có thể đồng bộ nhiều entities cùng lúc

Giả sử:

```java
CatalogItem itemA = em.find(CatalogItem.class, idA);
CatalogItem itemB = em.find(CatalogItem.class, idB);
CatalogItem itemC = em.find(CatalogItem.class, idC);

itemA.setName("Keyboard A");
itemB.setPrice(new BigDecimal("-1"));
itemC.setName("Keyboard C");

em.flush();
```

`flush()` có thể chạy validation cho nhiều dirty entities, sau đó sắp xếp/batch SQL. Nếu B vi phạm constraint, exception xuất hiện ở `flush()` nhưng **không nhất thiết chỉ ra setter gần nhất trong source code**.

Test có thể:

- Chuẩn bị IDs rõ ràng.
- Xác định violation root bean / property path.
- Kiểm tra dữ liệu committed sau rollback.
- Tránh assert thứ tự validations giữa các entities nếu không được contract bảo đảm.
- Không suy một SQL UPDATE đã thấy trong log đồng nghĩa row đã được commit.

Nếu provider gọi SQL cho A trước khi phát hiện lỗi B, rollback transaction vẫn phải xử lý những thay đổi chưa commit đó.

---

## 37. Database constraints: lỗi ở SQL không giống Bean Validation

Giả sử entity không có Bean Validation constraint trên một field nhưng DB có:

```sql
CONSTRAINT ck_catalog_item_price CHECK (price >= 0)
```

Nếu code ghi giá âm, provider có thể gửi UPDATE và database từ chối. Exception có thể là:

```text
jakarta.persistence.PersistenceException
  └─ org.hibernate.exception.ConstraintViolationException
      └─ java.sql.SQLException
```

Đây là **database constraint failure**, không phải `jakarta.validation.ConstraintViolationException` chứa `getConstraintViolations()`.

Hai loại lỗi có ý nghĩa khác nhau trong test:

- Bean Validation test xác minh annotation được xét trong Java lifecycle.
- DB constraint test xác minh database ràng buộc committed data.
- Application service test xác minh public error mapping.

Một số database hỗ trợ deferrable constraints, nên SQL statement/flush có thể chưa phát lỗi cho đến commit. Không viết mọi test integrity với giả định mọi constraint phải fail tại `flush()`.

## 38. Cách kiểm thử database CHECK mà không dùng entity validation

Nếu muốn chứng minh DB thật có CHECK:

```java
@Test
void databaseRejectsNegativePriceFromJdbc() {
    assertThrows(SQLException.class, () -> {
        try (Connection connection =
                 dataSource.getConnection();
             PreparedStatement statement =
                 connection.prepareStatement(
                     "INSERT INTO catalog_items " +
                     "(id, version, name, price) " +
                     "VALUES (?, ?, ?, ?)"
                 )) {

            statement.setLong(1, nextTestId());
            statement.setLong(2, 0L);
            statement.setString(3, "Invalid");
            statement.setBigDecimal(
                4,
                new BigDecimal("-1")
            );

            statement.executeUpdate();
        }
    });
}
```

`dataSource` và `nextTestId` là fixture helpers, phải kết nối đúng database đã chạy migrations. Transaction/autocommit/isolation cần được thiết lập để fixture không làm bẩn DB sau test.

Test này cố tình **bypass JPA provider và Bean Validation**, để kiểm tra CHECK constraint. Nếu DB không enforce CHECK ở dialect/version tương ứng hoặc schema thiếu constraint, test sẽ phát hiện gap mà một test `Validator.validate` không thấy.

Đối với FK/UNIQUE, có thể dùng đường JDBC tương tự. Trong môi trường có deferrable constraints, cần assert đến commit.

## 39. Kiểm thử validation mode NONE làm đối chứng

Một test trong persistence unit khác cấu hình:

```xml
<validation-mode>NONE</validation-mode>
```

có thể dùng entity vẫn có:

```java
@DecimalMin("0.00")
private BigDecimal price;
```

Khi gọi:

```java
em.persist(invalidItem);
em.flush();
```

automatic JPA Bean Validation không được yêu cầu trong mode NONE. **Nhưng database CHECK vẫn có thể báo lỗi.**

Để test rằng `NONE` thực sự tắt Bean Validation integration, phải:

- Nhận diện exception type/cause là DB vs Jakarta Validation.
- Hoặc dùng một constraint chỉ có ở Java, không có constraint DB tương đương, trong một fixture được kiểm soát.
- Dùng EntityManagerFactory khác khởi tạo với mode NONE.
- Không thay config trong cùng EntityManagerFactory rồi kỳ vọng lifecycle listener registration tự đổi.

Mode NONE không có nghĩa dữ liệu bất hợp lệ được phép commit nếu DB constraints bảo vệ nó.

## 40. Pre-update validator không sửa dữ liệu thay ứng dụng

Ví dụ:

```java
@NotBlank
private String name;
```

Bean Validation mặc định **chỉ kiểm tra**, không tự trim name:

```java
item.setName("   ");
em.flush();
```

Kết quả là violation nếu constraint hoạt động, không phải tự chuyển thành một tên hợp lệ.

Nếu cần normalization:

- Domain/value-object constructor.
- Request mapper.
- Custom converter phù hợp.
- JPA lifecycle callback đơn giản trong giới hạn portable.
- Database canonical column/rule nếu có nhiều writers.

Đừng viết test khẳng định `@NotBlank` sẽ tự sửa “  Keyboard  ” thành “Keyboard”. Validation không phải transformation pipeline.

## 41. Lỗi bắt sai chỗ trong Spring Data JPA

Một service:

```java
@Service
public class CatalogService {

    private final CatalogRepository repository;

    public CatalogService(CatalogRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void changePrice(Long id, BigDecimal price) {
        CatalogItem item = repository.findById(id)
            .orElseThrow();

        item.setPrice(price);
    }
}
```

Không có `save` và `flush` tường minh, nhưng managed entity vẫn có thể được dirty checked và updated khi Spring transaction interceptor commit.

Khi gọi:

```java
catalogService.changePrice(id, new BigDecimal("-1"));
```

exception có thể phát sinh **sau method body**, ở transaction completion do Spring proxy thực hiện.

Vì vậy catch đặt bên trong service body:

```java
@Transactional
public void changePrice(...) {
    try {
        item.setPrice(price);
    } catch (ConstraintViolationException ex) {
        // Không nhất thiết bắt được lỗi ở commit.
    }
}
```

có thể bỏ sót lỗi. Nếu cần log/translation cho commit failures, đặt boundary ở caller/controller advice hoặc transaction wrapper.

## 42. `save()` và `saveAndFlush()` khác nhau

Spring Data JPA có:

```java
repository.save(entity);
repository.saveAndFlush(entity);
repository.flush();
```

Ý nghĩa:

- `save` xử lý persist/merge theo repository semantics; không cam kết SQL/validation đã hoàn tất.
- `saveAndFlush` yêu cầu flush trong lời gọi repository, nên có thể phát hiện lifecycle validation/DB errors sớm hơn.
- `flush` trên repository/JPA context yêu cầu đồng bộ pending state.
- Không method nào trong số này tự tương đương **transaction committed** nếu transaction còn do caller quản lý.

Ví dụ:

```java
@Transactional
public void create(CatalogItem item) {
    repository.saveAndFlush(item);

    // Validation/SQL failure có thể đã được phát hiện.
    // Nhưng transaction vẫn có thể rollback sau đây.
}
```

Không gửi email “đã lưu thành công” chỉ vì `saveAndFlush` trả về bình thường. Commit vẫn có thể fail.

## 43. Test với Spring `@DataJpaTest`

Spring Boot có `@DataJpaTest` để thiết lập JPA test slice. Một ví dụ:

```java
@DataJpaTest
class CatalogRepositoryValidationTest {

    @Autowired
    private TestEntityManager testEntityManager;

    @Test
    void invalidUpdateFailsOnFlush() {
        CatalogItem item = new CatalogItem(
            9001L,
            "Keyboard",
            new BigDecimal("100.00")
        );

        testEntityManager.persistAndFlush(item);

        item.setPrice(new BigDecimal("-1"));

        RuntimeException failure = assertThrows(
            RuntimeException.class,
            testEntityManager::flush
        );

        assertNotNull(
            findBeanValidationViolation(failure)
        );
    }
}
```

Ví dụ cần imports/annotations của Spring Boot Test và một assigned ID không trùng fixture. Khi dùng `TestEntityManager`, tên method và API phụ thuộc phiên bản Spring Boot; nếu chỉ có `EntityManager` thì gọi `em.persist` và `em.flush` tương ứng.

### Bẫy của `@DataJpaTest`

Nhiều `@DataJpaTest` chạy **trong test transaction và rollback sau mỗi test**. Điều này hữu ích cho isolation nhưng gây hiểu nhầm:

- Test không tự chứng minh commit thành công.
- Constraint deferred chỉ fail ở commit có thể không được phát hiện nếu chỉ rollback.
- Entity đã persist trong test transaction có thể chưa được nhìn thấy bởi connection khác.
- Mocks/services gọi qua transaction propagation khác có thể cho behavior không giống production.

Muốn test commit, cần chủ động chạy transaction hoàn tất thật theo test framework hoặc dùng integration test không tự bọc toàn method trong transaction rollback.

## 44. Spring test: dùng `TestTransaction` khi cần commit thật

Trong Spring Test, có `TestTransaction` cho test transaction được framework quản lý, khi phù hợp:

```java
@Test
@Transactional
void transactionCompletionCanBeObserved() {
    CatalogItem item = new CatalogItem(
        nextId(),
        "Keyboard",
        new BigDecimal("100")
    );

    repository.save(item);

    TestTransaction.flagForCommit();
    TestTransaction.end();

    // Tại đây test transaction đã hoàn tất.
    // Dùng context/transaction mới để kiểm tra committed DB state.
}
```

Ví dụ trên minh họa case thành công. Với dữ liệu không hợp lệ, `TestTransaction.end()` có thể ném exception khi commit; test cần bắt và xác định cause phù hợp.

**Chỉ dùng TestTransaction khi test thật sự đang ở Spring test-managed transaction**. Nếu transaction do transaction manager khác hoặc service tạo REQUIRES_NEW, phải hiểu propagation/ownership trước khi kiểm tra.

Không dùng `@Commit` một cách tùy tiện trên toàn suite vì có thể làm dữ liệu fixture rò qua các tests.

## 45. Spring test: dùng `TransactionTemplate` để bao cả commit

Một cách kiểm tra transaction boundary tương đối rõ trong Spring:

```java
@Autowired
private PlatformTransactionManager transactionManager;

@Test
void validationIsRejectedWithinTransactionCompletion() {
    TransactionTemplate template =
        new TransactionTemplate(transactionManager);

    RuntimeException failure = assertThrows(
        RuntimeException.class,
        () -> template.execute(status -> {
            CatalogItem item = em.find(
                CatalogItem.class,
                existingId
            );

            item.setPrice(new BigDecimal("-1"));

            // Không explicit flush.
            // Commit có thể là nơi phát lỗi.
            return null;
        })
    );

    assertNotNull(
        findBeanValidationViolation(failure)
    );
}
```

Vì `TransactionTemplate.execute` bao cả callback và commit do template quản lý, test không chỉ dựa vào method body.

Lưu ý:

- Test **không được đang nằm trong một outer rollback transaction** nếu bạn muốn template tạo transaction độc lập và commit thật theo propagation mặc định.
- `existingId` phải là fixture đã commit.
- `em` phải là EntityManager gắn đúng transaction.
- Framework exception translation có thể bọc/làm thay đổi exception type; kiểm tra cause chain.
- Không bắt mọi RuntimeException rồi coi validation thành công; phải xác minh Bean Validation violation.

## 46. Đừng thử commit sau `assertThrows(flush)` trong cùng transaction lỗi

Anti-pattern:

```java
try {
    assertThrows(
        ConstraintViolationException.class,
        em::flush
    );

    item.setPrice(BigDecimal.TEN);
    em.getTransaction().commit(); // Cố cứu transaction.
} finally {
    em.close();
}
```

Sau một validation/persistence failure, transaction có thể bị đánh dấu rollback-only; database/provider state cũng có thể không còn hợp lệ để tiếp tục.

Đúng hơn:

```java
try {
    em.getTransaction().begin();
    // Arrange invalid state.
    assertThrows(RuntimeException.class, em::flush);
} finally {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    em.close();
}
```

Khi cần kiểm tra một giá trị hợp lệ sau đó, mở EntityManager/transaction **mới**.

## 47. Kiểm tra transaction status sau lỗi

Có những trường hợp:

```java
boolean active =
    em.getTransaction().isActive();
```

nhưng `isActive() == true` **không đồng nghĩa transaction vẫn có thể commit**. Transaction có thể được đánh dấu rollback-only.

Trong resource-local JPA:

```java
boolean rollbackOnly =
    em.getTransaction().getRollbackOnly();
```

có thể giúp xác định trạng thái theo API/context khi transaction active. Nhưng không nên dựa vào việc mọi exception cùng đánh dấu rollback-only giống nhau ở mọi provider hoặc dùng `getRollbackOnly()` ngoài active transaction không hợp lệ.

Khi test intentionally gây validation failure, cách sạch là rollback trong finally, không đặt kỳ vọng “vẫn commit được” làm default.

## 48. Khi exception xảy ra tại query, log thế nào?

Giả sử stack trace:

```text
CatalogService.listItems(...)
  → TypedQuery.getResultList()
  → provider auto-flush
  → Bean Validation pre-update
  → ConstraintViolationException: price
```

Nếu chỉ log “listItems SELECT lỗi”, bạn có thể điều tra sai hướng.

Cần log có chọn lọc:

- Transaction correlation ID.
- Entity type và ID (nếu không nhạy cảm).
- Operation đang xử lý.
- Field paths vi phạm.
- Flush mode và query boundary khi debug.
- SQL statements đã phát trước exception.
- Cause chain chính xác.
- Tenant/request context nếu được phép log.

Đừng log toàn bộ invalid bean hoặc raw request body nếu có dữ liệu nhạy cảm. Các giá trị `ConstraintViolation.getInvalidValue()` cũng có thể chứa PII.

Quan sát SQL giúp biết validation có chặn trước UPDATE hay không, nhưng **không thể dùng số SQL duy nhất làm bằng chứng validator chạy**. Cần exception/cause paths.

## 49. Test callback vs validation integration

Một entity có:

```java
@PreUpdate
void normalizeName() {
    if (name != null) {
        name = name.trim();
    }
}
```

và:

```java
@NotBlank
private String name;
```

Nếu gọi:

```java
item.setName("   ");
em.flush();
```

thì callback có thể biến tên thành empty string, sau đó validation có thể thấy `@NotBlank` fail theo integration ordering.

Khi viết test:

- Kiểm tra cả callback effects và validation violations nếu hai cơ chế phối hợp.
- Không cho rằng callback là Validator.
- Không cố gọi `EntityManager`/query từ callback để kiểm tra database uniqueness.
- Không dựa vào thứ tự giữa các entity callbacks khác nhau trong một graph nếu specification không bảo đảm.
- Không đoán mọi callback chạy đúng vào `flush` nếu operation bị thực thi sớm do ID strategy.

Nếu pre-callback tự ném `IllegalStateException`, test có thể fail trước Bean Validation; xác minh expected exception source để không nhầm.

## 50. Lifecycle validation không bảo vệ bulk JPQL UPDATE

Ví dụ:

```java
int affected = em.createQuery(
    "UPDATE CatalogItem i " +
    "SET i.price = :price " +
    "WHERE i.id = :id"
).setParameter("price", new BigDecimal("-1"))
 .setParameter("id", id)
 .executeUpdate();
```

Bulk JPQL DML không đưa từng entity qua dirty checking/pre-update Bean Validation theo cách managed update.

Hệ quả:

- `@DecimalMin` trên entity không tự chạy cho mỗi row.
- `@PreUpdate` callback không được gọi trên từng entity.
- L1 managed instances có thể stale.
- DB CHECK mới là hàng rào trực tiếp nếu query cố lưu giá âm.
- `@Version` không tự áp dụng đầy đủ cơ chế per-entity update cho bulk DML.

Vì vậy một **integration test cho managed `flush`** và một **test cho bulk DML** đều cần thiết nếu ứng dụng có cả hai đường ghi.

## 51. Native SQL và JDBC cũng bypass Bean Validation

Ví dụ:

```java
em.createNativeQuery(
    "UPDATE catalog_items SET price = ? WHERE id = ?"
).setParameter(1, new BigDecimal("-1"))
 .setParameter(2, id)
 .executeUpdate();
```

Đây là SQL trực tiếp. JPA entity-level validation không tự được áp dụng cho từng row.

Nếu database có:

```sql
CHECK (price >= 0)
```

SQL phải bị từ chối theo DB constraint semantics. Nhưng không nên kỳ vọng exception có `getConstraintViolations()` từ Jakarta Bean Validation.

Cần làm rõ **đường ghi nào được kiểm thử**:

| Đường ghi | Entity lifecycle Bean Validation? | DB constraint? |
| --- | --- | --- |
| Managed entity update + flush | Có khi integration enabled và event phù hợp | Có nếu SQL phát |
| Persist entity + flush | Có khi integration enabled | Có nếu SQL phát |
| Merge detached entity + flush | Có trên managed target khi event phù hợp | Có |
| JPQL bulk UPDATE | Không per-entity lifecycle | Có |
| CriteriaUpdate | Không per-entity lifecycle | Có |
| Native SQL UPDATE | Không | Có |
| JDBC direct UPDATE | Không | Có |
| DB trigger update | Không qua JPA callback | DB constraints/trigger logic theo engine |

Một test suite chỉ dùng `EntityManager.persist` không chứng minh các job JDBC khác không thể làm hỏng dữ liệu.

## 52. Test validation cùng database NOT NULL

Entity:

```java
@NotNull
@Column(nullable = false)
private BigDecimal price;
```

Database:

```sql
price DECIMAL(14,2) NOT NULL
```

Hai lớp cùng cấm null nhưng khác thời điểm/nơi thực hiện.

Test Bean Validation:

```java
item.setPrice(null);
assertThrows(RuntimeException.class, em::flush);
```

rồi xác minh cause là `jakarta.validation.ConstraintViolationException`.

Test database:

```sql
UPDATE catalog_items
SET price = NULL
WHERE id = ?;
```

qua JDBC/native, kỳ vọng DB NOT NULL violation.

Nếu chỉ test lần đầu, bạn **không chứng minh NOT NULL trong schema**. Nếu chỉ test lần thứ hai, bạn **không chứng minh JPA Bean Validation integration đang bật**.

## 53. Test UNIQUE khác test `@NotBlank`

Giả sử:

```java
@NotBlank
private String sku;
```

và DB:

```sql
UNIQUE (shop_id, sku)
```

Một test Bean Validation có thể xác minh `sku = " "` fail. Nhưng duplicate SKU là **cross-row uniqueness**, không được giải quyết bởi `@NotBlank`.

Ngay cả custom validator gọi repository `existsBySku` vẫn có race giữa SELECT và INSERT. Integration test uniqueness phải dùng DB constraint thật và, khi cần, hai transactions cạnh tranh.

Một cách phân loại:

- Blank SKU → field validation.
- SKU trùng trong database → UNIQUE conflict.
- User không được tạo Product trong shop đó → authorization/business rule.
- Product version lỗi thời → optimistic concurrency conflict.

Không dùng một catch-all ValidationException để che mọi nguyên nhân.

## 54. Test `@Valid` ở API boundary và JPA flush không trùng nhau

Một Spring MVC controller:

```java
@PostMapping("/items")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateItemRequest request) {

    service.create(request);
    return ResponseEntity.status(201).build();
}
```

Request DTO có thể bị từ chối trước khi service/transaction bắt đầu.

Một scheduled job hoặc event handler có thể tạo CatalogItem trực tiếp:

```java
em.persist(new CatalogItem(id, " ", price));
```

Nếu không đi qua controller, `@Valid` ở HTTP method không được chạy; JPA lifecycle validation (nếu bật) và DB constraints mới là các lớp sau.

Test riêng:

1. Web test cho HTTP field errors.
2. JPA integration test cho pre-persist/pre-update validation.
3. DB integration test cho constraints khi bypass ORM.
4. Service test cho rules liên quan nhiều objects/permissions.

**Không coi một request test trả HTTP 400 là đủ chứng minh validation tại flush.**

## 55. Integration test không tự đồng nghĩa production correctness

Một test chạy trên database in-memory có thể khác production:

- Khác hỗ trợ CHECK/deferrable constraints.
- Khác type mapping, collation, Unicode length.
- Khác transaction isolation.
- Khác ID generation.
- Khác SQL dialect.
- Khác JDBC batching.
- Khác flush scheduling hoặc Hibernate settings.
- Khác cách kiểm tra unique constraints khi có concurrency.

Với timing và database integrity nhạy cảm, dùng **Testcontainers hoặc một database tương đương engine/version production** để có kết quả đáng tin cậy hơn.

Testcontainers không thay cho JPA integration; nó cung cấp database thật trong test. JPA provider, Bean Validation provider và transaction manager vẫn phải được cấu hình.

## 56. Kiểm thử với Testcontainers: bố cục khái niệm

Ví dụ hướng tiếp cận với PostgreSQL:

```java
@Testcontainers
class CatalogValidationIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    // Bootstrap EntityManagerFactory dùng:
    // postgres.getJdbcUrl()
    // postgres.getUsername()
    // postgres.getPassword()

    // Chạy migrations và sau đó thực thi các tests.
}
```

Các imports/classes của Testcontainers và cấu hình JDBC tùy phiên bản thư viện. Không tự suy rằng test này tự khởi tạo `persistence.xml` được nếu chưa truyền properties hay cấu hình datasource.

Mục tiêu không phải chạy container ở mỗi test method; có thể tái sử dụng trong class/suite theo isolation plan. Quan trọng là **migrations thật** và **runtime validation integration thật** được dùng trong tests.

## 57. Test fixture phải tránh `@Transactional` tự che commit

Nhiều Spring integration tests đánh dấu class:

```java
@Transactional
class CatalogServiceTest {
    // ...
}
```

và framework tự rollback cuối mỗi test.

Ưu điểm là cô lập dữ liệu. Nhưng nhược điểm khi kiểm tra validation **tại commit**:

- Test transaction có thể không commit.
- Database deferred constraint không được kích hoạt như production.
- Code path transaction proxy có thể kết thúc trong outer test transaction khác.
- Một service method `@Transactional(REQUIRED)` thường join test transaction, không commit khi method return.

Muốn test timing của real commit, cần cấu hình test transaction boundary rõ ràng và chủ động hoàn tất transaction; không để automatic rollback trở thành nguồn kết luận sai.

## 58. Tránh tác động của L1 cache khi xác minh DB state

Sau flush failure:

```java
CatalogItem item = em.find(CatalogItem.class, id);
```

trong cùng context có thể trả managed object còn mang giá âm.

Điều đó không chứng minh database đã lưu giá âm.

Cách xác minh:

```java
em.getTransaction().rollback();
em.close();

EntityManager fresh = emf.createEntityManager();

try {
    CatalogItem committed = fresh.find(
        CatalogItem.class, id
    );
    // Assert giá đã commit trước đó.
} finally {
    fresh.close();
}
```

Nếu L2 cache bật, cần hiểu cache consistency và có thể dùng query/JDBC độc lập khi test đòi kiểm chứng database trực tiếp. Đừng dùng rollbacked entity state như bằng chứng persisted state.

## 59. Validation + optimistic locking: phân loại khi cùng xảy ra

Giả sử entity có:

```java
@Version
private Long version;
```

Hai transactions cùng sửa CatalogItem. Một transaction sửa giá âm; transaction khác đã update version.

Có thể xảy ra:

- Bean Validation chặn giá âm trước SQL UPDATE.
- Version mismatch làm ORM ném `OptimisticLockException` ở flush/commit.
- DB CHECK chặn nếu Bean Validation không chạy.
- Database deadlock/serialization failure theo isolation.

Nếu test nhắm tới Bean Validation, **không tạo tình huống stale version**. Nếu test nhắm optimistic locking, dùng entity hợp lệ để loại validation khỏi biến nhiễu.

Một test chỉ assert “có exception” có thể xanh vì lý do sai.

## 60. Flush với JDBC batching: thứ tự phát lỗi có thể khác

Với nhiều pending entities và JDBC batching:

```text
item A changed
item B invalid
item C changed
       │
       ▼
em.flush()
       │
       ├─ Bean Validation lifecycle checks
       ├─ SQL batching/ordering (provider-specific)
       └─ Exception
```

Nếu Bean Validation báo lỗi sớm, một số SQL có thể chưa gửi. Nếu database constraint báo lỗi trong batch, exception có thể xuất hiện tại batch execution và bọc nhiều lớp.

Đừng assert:

```java
assertEquals(1, sqlUpdateCount);
```

cho mọi provider trừ khi mục tiêu test đúng là SQL behavior của provider cụ thể.

Tập trung assert:

- Lỗi đúng loại/field.
- Transaction rollback.
- DB committed state bất biến.
- Không external success side effects.
- Không rò connection/persistence context.

## 61. Error handling đúng cho service production

Một method resource-local có thể:

```java
public void changePrice(
        EntityManagerFactory emf,
        Long id,
        BigDecimal newPrice) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        CatalogItem item = em.find(CatalogItem.class, id);

        if (item == null) {
            throw new IllegalArgumentException("Item not found");
        }

        item.setPrice(newPrice);

        em.getTransaction().commit();
    } catch (RuntimeException failure) {
        if (em.getTransaction().isActive()) {
            try {
                em.getTransaction().rollback();
            } catch (RuntimeException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
        }
        throw failure;
    } finally {
        em.close();
    }
}
```

Đây là mẫu quản lý transaction, **không phải mẫu domain design khuyến nghị bỏ kiểm tra giá trong setter**. Ứng dụng nên validate request/domain ngay từ đầu khi có thể; Bean Validation/DB constraints là các lớp bảo vệ bổ sung.

Exception được phân loại ở boundary:

- Bean Validation violations → thông báo field phù hợp.
- Domain rule violations → mã lỗi nghiệp vụ.
- DB integrity failure → map constraint đã biết.
- Optimistic conflict → báo dữ liệu đã thay đổi.
- Infrastructure failure → xử lý availability/retry theo vận hành.

Không bắt `RuntimeException` rồi luôn trả “giá âm” vì lỗi có thể là connection failure hay concurrency.

## 62. Đừng gửi side effects khi chỉ mới flush thành công

Ví dụ nguy hiểm:

```java
em.flush();

emailSender.send("Đã cập nhật thành công");

em.getTransaction().commit();
```

`flush()` thành công không bảo đảm commit thành công. Commit có thể thất bại do deferred constraint, optimistic conflict hoặc transaction errors.

Tương tự, lifecycle `@PostUpdate` xảy ra sau SQL UPDATE nhưng **không phải after-commit event**.

Nếu cần phát message sau commit một cách đáng tin cậy, cân nhắc:

- Transactional outbox lưu event row trong cùng transaction.
- Worker publish sau khi outbox row đã commit.
- Idempotent consumer và retry.
- Hoặc transaction synchronization after-commit cho nhu cầu nhẹ, hiểu rõ limitations về delivery khi process crash.

Kiểm thử validation/flush nên kiểm tra rằng **không có irreversible external success notification** trước khi transaction thực sự thành công.

## 63. Test boundary: khi nào nên gọi `flush()` tường minh?

Có những trường hợp chủ động flush trong business code hoặc test:

1. Muốn phát hiện Bean Validation lifecycle failure trước một bước tiếp theo.
2. Muốn biết DB CHECK/FK/UNIQUE failure trước một operation khác trong cùng transaction.
3. Muốn kiểm tra SQL được phát tại một mốc rõ ràng.
4. Muốn integration test chứng minh provider nhận diện dirty entity.
5. Muốn xử lý một constraint có thể thất bại theo semantics đã biết.
6. Muốn tránh lỗi xuất hiện bất ngờ tại JPQL query trigger auto-flush.

Nhưng cần nhớ:

- Flush có chi phí I/O.
- Flush không commit.
- Deferred DB constraints có thể vẫn fail lúc commit.
- Một flush có thể đồng bộ **toàn bộ persistence context**, không chỉ entity bạn vừa sửa.
- Không nên flush sau mỗi setter theo phản xạ.
- Không được swallow validation exception rồi tiếp tục transaction lỗi.

Trong test, explicit flush hữu ích vì tạo **ranh giới quan sát**; trong production phải cân nhắc hiệu năng và transaction design.

## 64. Những hiểu nhầm thường gặp

### Hiểu nhầm 1: Có `@NotNull` thì setter tự ném lỗi

Không. Setter chỉ ném nếu chính domain code kiểm tra hoặc một cơ chế khác kích hoạt validation tại đó.

### Hiểu nhầm 2: Gọi `validator.validate` đã test JPA flush

Không. Đó là Bean Validation thuần, không dùng persistence context.

### Hiểu nhầm 3: `persist` trả về nghĩa INSERT hợp lệ

Không. INSERT/validation/DB checks có thể xảy ra ở flush hoặc commit.

### Hiểu nhầm 4: `flush()` thành công nghĩa transaction đã commit

Không. Rollback hoặc deferred constraints vẫn có thể làm transaction thất bại.

### Hiểu nhầm 5: `@Column(nullable=false)` tương đương `@NotNull`

Không. Mapping/DDL metadata khác Jakarta Bean Validation constraint.

### Hiểu nhầm 6: Test fail vì CHECK chứng minh Bean Validation integration đang bật

Không. DB constraint và Java Bean Validation là hai cơ chế độc lập.

### Hiểu nhầm 7: Hibernate ORM `ConstraintViolationException` là Jakarta Validation exception

Không. Khác package và thường khác nguồn lỗi.

### Hiểu nhầm 8: Mọi `em.flush()` đều validate lại mọi entity trong context

Không. Pre-update validation gắn với lifecycle update, không phải lệnh quét tất cả objects.

### Hiểu nhầm 9: `FlushModeType.COMMIT` tắt validation

Không. Nó ảnh hưởng thời điểm synchronization/query semantics, không vô hiệu Bean Validation.

### Hiểu nhầm 10: SELECT luôn vô can với validation

Không. Query có thể kích hoạt auto-flush của dirty entities.

### Hiểu nhầm 11: Mọi JPQL SELECT đều buộc ném lỗi ở query

Không. Auto-flush phụ thuộc query, provider và flush mode.

### Hiểu nhầm 12: Entity mới luôn được validate đúng tại `flush()`

Không portable. ID generation/provider có thể khiến INSERT/validation xảy ra sớm hơn.

### Hiểu nhầm 13: `saveAndFlush` tương đương commit

Không. Nó flush trong active transaction.

### Hiểu nhầm 14: `@DataJpaTest` tự kiểm thử commit thật

Không luôn; nhiều test được rollback tự động.

### Hiểu nhầm 15: Chỉ cần assert RuntimeException

Không đủ. Cần kiểm tra Bean Validation type/cause/property path.

### Hiểu nhầm 16: Có validation mode NONE thì DB cho phép dữ liệu sai

Không. DB constraints vẫn còn.

### Hiểu nhầm 17: Bean Validation áp dụng tự động cho native/bulk UPDATE

Không theo per-entity lifecycle.

### Hiểu nhầm 18: Sau validation failure có thể sửa field rồi flush lại cùng transaction

Không nên. Transaction có thể rollback-only; rollback và dùng context mới.

### Hiểu nhầm 19: Managed entity sau rollback phản ánh database

Không. Java object có thể giữ state bị từ chối.

### Hiểu nhầm 20: Tăng `@Version` thay cho kiểm tra giá

Không. Optimistic locking bảo vệ concurrency, không thay validation.

### Hiểu nhầm 21: Test dữ liệu invalid phải assert SQL UPDATE đã chạy

Không. Bean Validation có thể chặn **trước khi SQL** được gửi.

### Hiểu nhầm 22: Unit test setter pass chứng minh JPA provider hoạt động

Không. Không có provider/transaction trong unit test.

### Hiểu nhầm 23: Native JDBC test check constraint có thể bỏ migrations

Không. Test phải chạy trên schema thật tương đương production.

### Hiểu nhầm 24: Test exception tại query là bug của SELECT

Không nhất thiết; lỗi có thể do auto-flush pending update trước SELECT.

### Hiểu nhầm 25: Catch bên trong `@Transactional` service luôn bắt lỗi ở commit

Không. Spring interceptor có thể commit sau khi method body trả về.

## 65. Bài tập thực hành

### Bài 1: Bean Validation thuần

Tạo CatalogItem với `price = -10`, gọi `validator.validate`.

**Câu hỏi:** Đã kiểm tra flush chưa?

**Đáp án:** Chưa. Chỉ kiểm tra constraints trên Java object.

### Bài 2: Managed update

Seed CatalogItem giá hợp lệ và commit, mở EntityManager mới, set price âm, gọi `flush`.

**Câu hỏi:** Test chứng minh điều gì nếu nhận Jakarta `ConstraintViolationException` có path `price`?

**Đáp án:** JPA lifecycle validation đã được kích hoạt trong quá trình flush update entity.

### Bài 3: SQL CHECK

Dùng JDBC UPDATE trực tiếp price âm.

**Câu hỏi:** Exception nào cần nhận diện?

**Đáp án:** DB/JDBC constraint failure, không phải Jakarta Bean Validation. Phải có CHECK trong schema thật.

### Bài 4: Setter không ném lỗi

Một setter chỉ gán field.

**Câu hỏi:** Giá âm có thể tồn tại trong Java object trước flush không?

**Đáp án:** Có. Java state có thể tạm invalid; validation sẽ báo khi được kích hoạt, trừ khi domain method tự chặn sớm.

### Bài 5: `persist` và `IDENTITY`

JPA provider phải INSERT sớm để lấy ID.

**Câu hỏi:** Có bắt buộc `flush()` là dòng đầu tiên ném validation failure không?

**Đáp án:** Không. Có thể fail tại persist; test portable bao cả unit of work.

### Bài 6: `@PreUpdate`

Entity được load và chỉ gọi getter, rồi flush.

**Câu hỏi:** Có nhất thiết chạy pre-update validation không?

**Đáp án:** Không nếu không có dirty persistent update.

### Bài 7: Query AUTO

Set price âm rồi gọi JPQL SELECT liên quan CatalogItem.

**Câu hỏi:** Vì sao lỗi có thể xuất hiện ở `getResultList()`?

**Đáp án:** Query-triggered auto-flush thực hiện pre-update validation trước SELECT.

### Bài 8: Query COMMIT

Set flush mode COMMIT rồi chạy SELECT.

**Câu hỏi:** Có bảo đảm SELECT sẽ ném Bean Validation exception không?

**Đáp án:** Không. Pending update có thể được đồng bộ muộn hơn tại explicit flush/commit.

### Bài 9: Nested `@Valid`

OrderRequest có AddressRequest.city trống.

**Câu hỏi:** Cần gì để validator đi vào Address?

**Đáp án:** Cascaded `@Valid` trên nested property và các constraints phù hợp trên Address.

### Bài 10: Validation groups

`price` chỉ có group `OnUpdate`; JPA pre-update không cấu hình OnUpdate.

**Câu hỏi:** Constraint có chắc được validate khi flush không?

**Đáp án:** Không. Phải cấu hình groups thực sự áp dụng; `Default` không tự bao gồm mọi custom group.

### Bài 11: Validation mode NONE

Entity vẫn có `@DecimalMin`; DB có CHECK.

**Câu hỏi:** Flush vẫn có thể fail không?

**Đáp án:** Có, do DB CHECK. Không được gọi đó là Bean Validation failure nếu cause không phải Jakarta Validation.

### Bài 12: Merge detached

Detached entity price âm, merge vào EntityManager mới.

**Câu hỏi:** Cần kiểm tra instance nào?

**Đáp án:** Managed representation trả về từ `merge` và transaction boundary. Detached instance không tự trở thành managed.

### Bài 13: Bulk UPDATE

JPQL bulk UPDATE price âm.

**Câu hỏi:** `@DecimalMin` per-entity có được gọi tự động không?

**Đáp án:** Không theo entity update lifecycle. DB CHECK phải bảo vệ.

### Bài 14: Spring `save`

Repository.save trả về bình thường.

**Câu hỏi:** Entity đã chắc vượt qua validation/DB constraints chưa?

**Đáp án:** Chưa; flush/commit có thể fail.

### Bài 15: Spring `saveAndFlush`

saveAndFlush thành công, sau đó một transaction khác/constraint làm commit fail.

**Câu hỏi:** Có thể đã gửi email thành công sau saveAndFlush chưa?

**Đáp án:** Không nên; flush chưa phải durable commit.

### Bài 16: `@DataJpaTest`

Test được rollback sau method.

**Câu hỏi:** Nó có kiểm thử deferred constraint tại commit thật không?

**Đáp án:** Không nhất thiết. Cần chủ động kiểm tra transaction completion.

### Bài 17: Rollback state

Flush fail; entity trong heap còn price âm.

**Câu hỏi:** DB đã lưu price âm chưa?

**Đáp án:** Không thể suy từ object. Rollback và đọc lại bằng context mới.

### Bài 18: Đếm SQL

Validation fail trước SQL UPDATE.

**Câu hỏi:** Test có bị sai khi assert bắt buộc 1 UPDATE statement không?

**Đáp án:** Có. Validation Java có thể chặn trước khi SQL phát.

### Bài 19: Hai exceptions cùng tên

`jakarta.validation.ConstraintViolationException` và `org.hibernate.exception.ConstraintViolationException`.

**Câu hỏi:** Khác nhau thế nào?

**Đáp án:** Một đến từ Bean Validation, một thường từ database constraint qua ORM; phải phân biệt package/cause.

### Bài 20: Optimistic locking

Transaction khác update same row lên version mới; transaction hiện tại vừa stale vừa có price âm.

**Câu hỏi:** Test có thể ngẫu nhiên nhận optimistic exception thay vì validation không?

**Đáp án:** Có thể tùy kiểm tra/provider/schedule. Test Bean Validation nên cô lập concurrency.

### Bài 21: JPA lifecycle callback

`@PreUpdate` tự ném IllegalStateException.

**Câu hỏi:** Có chứng minh Bean Validation hoạt động không?

**Đáp án:** Không. Đó là lifecycle callback tự ném lỗi.

### Bài 22: Constraint ở database

Entity `@NotNull` nhưng schema production cho phép NULL.

**Câu hỏi:** Test validator xanh có đủ không?

**Đáp án:** Không. External JDBC writers có thể lưu NULL; cần DB NOT NULL và schema test.

### Bài 23: Transaction status

Flush ném exception, `getTransaction().isActive()` còn true.

**Câu hỏi:** Có chắc commit được không?

**Đáp án:** Không. Transaction có thể rollback-only; nên rollback, không tiếp tục.

### Bài 24: Query streaming

`getResultStream()` có lazy execution tùy provider.

**Câu hỏi:** Validation có thể xuất hiện khi nào?

**Đáp án:** Khi query execution/auto-flush/terminal traversal hoặc transaction completion, tùy provider; dùng explicit flush để tạo mốc kiểm tra khi cần.

### Bài 25: Thiết kế test suite đầy đủ

**Yêu cầu:** Chứng minh CatalogItem không thể lưu giá âm qua managed JPA, bulk JPQL và JDBC.

**Gợi ý:** Tạo ba tests riêng: managed update nhận Jakarta Bean Validation violation ở flush; bulk JPQL/native UPDATE bị DB CHECK từ chối; JDBC direct UPDATE bị DB CHECK từ chối. Sau mỗi failure, rollback và đọc DB qua context mới; không nhầm error sources.

---

## 66. Checklist trước khi kết luận đã kiểm thử validation ở flush

1. Entity có constraint Jakarta Validation đúng package không?
2. Runtime có Bean Validation implementation tương thích không?
3. JPA validation mode đang là AUTO/CALLBACK/NONE?
4. Đã kiểm tra pre-persist/pre-update groups thực sự áp dụng chưa?
5. Entity thuộc persistence unit và mapping đúng không?
6. Có active transaction và joined persistence context không?
7. Entity đang managed hay detached?
8. Nếu test update, entity đã được seed và commit trước đó chưa?
9. Persistent field thật sự dirty không?
10. Có setter/domain method tự ném trước khi tới flush không?
11. Có lifecycle callback tự ném exception làm nhiễu test không?
12. `@Id` strategy có khiến INSERT phát sớm trước flush không?
13. Test có explicit `em.flush()` tại boundary quan sát rõ không?
14. Nếu không flush, test có bao cả commit không?
15. Query có auto-flush và làm thay đổi mốc lỗi không?
16. Flush mode có phải AUTO hay COMMIT theo scenario không?
17. Test có phân biệt Jakarta Bean Validation exception với ORM SQL exception không?
18. Có assert property path cụ thể thay vì chỉ assert RuntimeException không?
19. Có loại nhiễu từ optimistic locking và concurrent writers không?
20. Có tách riêng kiểm thử DB CHECK/UNIQUE/FK/NOT NULL không?
21. Có schema migrations thật và database phù hợp không?
22. Có test native/bulk paths vốn bỏ qua entity validation không?
23. Có tránh dùng cùng EntityManager giữa tests không?
24. Có rollback và close context sau exception không?
25. Có đọc committed DB state qua fresh context/JDBC không?
26. Có tránh assert BigDecimal.equals sai do scale không?
27. Có tránh assert thứ tự ConstraintViolations không được bảo đảm không?
28. Có kiểm tra group-specific violations với đúng config không?
29. Có test pre-remove nếu ứng dụng có validation groups cho remove không?
30. Có test cascaded `@Valid` khi graph cần validate không?
31. Có xem Spring `@DataJpaTest` rollback mặc định che commit không?
32. Có kiểm tra commit failure ở boundary ngoài method `@Transactional` không?
33. Có phân biệt `saveAndFlush` với commit không?
34. Có quan sát SQL để xác định Bean Validation chặn trước DB hay lỗi tới từ DB không?
35. Có tránh gửi external side effects khi chỉ mới flush thành công không?
36. Có tích hợp provider/cache/ID strategy production-like khi cần xác minh timing không?
37. Có test các scenarios vào riêng transaction/fixture có thể lặp lại không?
38. Có thiết kế tests không phụ thuộc sleep/time-sensitive scheduling không?
39. Có tách errors do validation, domain rules, DB integrity và infrastructure không?
40. Có ghi nhận rõ những assertion timing nào là provider-specific không?

Checklist này không nhằm biến mọi test thành kiểm thử nặng. Mục đích là bảo đảm khi nói **“validation đã được kiểm thử tại flush”**, ta thực sự đã quan sát JPA lifecycle trong một transaction, chứ không chỉ gọi Validator hoặc nhận một exception không liên quan.

## Kết luận

**Kiểm thử validation cùng thời điểm flush thực tế** là kiểm thử sự phối hợp giữa Java entity state, JPA persistence context, Bean Validation integration, transaction và database constraints.

Những điểm quan trọng:

- **`Validator.validate(...)`** chứng minh constraints hoạt động trên Java object khi được gọi tường minh. Nó không chứng minh JPA đã gọi validator trong flush.
- **`EntityManager.flush()`** là điểm kiểm thử hữu ích cho managed update hoặc pending insert vì nó yêu cầu đồng bộ changes và có thể kích hoạt pre-persist/pre-update Bean Validation. Tuy nhiên, INSERT/validation có thể xảy ra sớm hơn theo provider/ID generation.
- **`commit()`** vẫn cần được kiểm thử riêng, vì flush có thể bị trì hoãn tới commit và một số database constraints có thể được kiểm tra ở commit. Flush thành công không bảo đảm transaction thành công.
- **JPQL/Criteria query trong `AUTO`** có thể gây auto-flush, khiến lỗi validation xuất hiện ở `getResultList()` hoặc một phương thức query thay vì dòng setter.
- **Bean Validation failure** và **database constraint failure** là hai nguồn lỗi khác nhau. Hãy xác minh exception package/cause, property path và schema thật, không chỉ assert RuntimeException.
- **Bulk JPQL, CriteriaUpdate và native SQL** không tự kích hoạt per-entity Bean Validation, nên database constraints vẫn cần thiết.
- **Rollback không tự hoàn tác Java object state**; đọc lại bằng context/connection mới để xác minh dữ liệu đã commit.
- Với Spring, **`saveAndFlush` không tương đương commit** và test `@Transactional` có thể rollback mặc định; khi cần kiểm tra transaction completion, phải chủ động điều khiển boundary.

Một test đáng tin phải trả lời năm câu hỏi: **“Entity có managed và dirty không? Constraint/group nào được kích hoạt? Lỗi xuất hiện ở flush, query hay commit? Nó là Bean Validation hay database integrity error? Và sau rollback database đang giữ giá trị gì?”**.

Trả lời đúng cả năm sẽ giúp kiểm thử validation không chỉ ở mức annotation, mà ở **chính thời điểm JPA thực sự đồng bộ dữ liệu**, với kết quả có thể lặp lại và phù hợp hành vi transaction trong ứng dụng thực tế.
