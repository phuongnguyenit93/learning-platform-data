# Kiểm thử persist, find, merge, remove và vòng đời entity trong JPA

Java Persistence API (JPA) không chỉ cung cấp các lệnh lưu, tìm, cập nhật và xóa dữ liệu. Nó duy trì một **persistence context**, theo dõi Java entity instances, quyết định khi nào phát SQL và phối hợp với database transaction. Vì thế, một bài kiểm thử chỉ gọi `persist()` rồi kiểm `id != null` có thể trông như đã chứng minh dữ liệu được lưu, trong khi transaction vẫn chưa commit và hoàn toàn có thể rollback. Tương tự, `find()` trong cùng persistence context có thể trả ngay instance đang được quản lý mà không đọc lại row từ database.

Bài học thuộc chương **Kiểm thử JPA**, hướng dẫn cách kiểm chứng đúng bốn thao tác cốt lõi:

- `EntityManager.persist(entity)`: tiếp nhận một entity mới vào persistence context.
- `EntityManager.find(EntityClass, id)`: tra cứu entity theo primary key.
- `EntityManager.merge(entity)`: sao chép state từ new/detached entity vào một **managed instance được trả về**.
- `EntityManager.remove(entity)`: đánh dấu managed entity để xóa khi đồng bộ transaction.

Chúng ta cũng kiểm thử các trạng thái **new, managed, detached, removed**, flush/commit/rollback, dirty checking, lifecycle callbacks, `@Version`, cascade, `orphanRemoval`, lazy loading, database constraints và Spring Data JPA. Mục tiêu là phân biệt điều được **JPA contract** bảo đảm với hành vi triển khai riêng của Hibernate, EclipseLink hoặc database.

---

## 1. Ba câu hỏi quyết định chất lượng một bài test JPA

Trước khi viết assertion, hãy trả lời:

1. Entity đang ở trạng thái **new, managed, detached hay removed**?
2. Đang ở **cùng EntityManager/transaction** hay một persistence context và transaction mới?
3. Assertion nhằm chứng minh **Java state**, **SQL đã được flush**, hay **database state đã commit**?

Ví dụ:

~~~java
Document document = new Document("D-001", "Draft");
em.persist(document);
assertNotNull(document.getId());
~~~

Điều này không chứng minh transaction đã commit. ID có thể được provider hoặc database cấp trước commit. Một constraint failure hoặc lỗi ở một statement khác có thể làm toàn bộ transaction rollback sau đó.

Bảng phân biệt:

| Cách kiểm tra | Điều chứng minh | Điều chưa chứng minh |
|---|---|---|
| `assertEquals` trên getter | Giá trị của Java object hiện tại | Database đã nhận UPDATE |
| `em.contains(entity)` | Entity thuộc persistence context hiện tại | Row đã commit |
| `em.flush()` trả bình thường | Provider đã đồng bộ những thao tác cần thiết trong transaction | Transaction đã commit |
| `tx.commit()` trả bình thường | Transaction được manager/database xác nhận hoàn tất | External event cũng thành công |
| `find()` trong cùng EM | Identity map hoặc database đã cho một managed entity | Fresh transaction nhìn thấy dữ liệu |
| Fresh EM + transaction mới đọc lại | Kiểm chứng DB state sau transaction trước | Mọi replicas đã đồng bộ |

Một bài kiểm thử tốt đặt assertion ở **đúng ranh giới**.

---

## 2. Bốn trạng thái của entity

~~~text
           new / transient
                |
             persist()
                v
             MANAGED
             /     \
         detach()  remove()
           |         |
           v         v
        DETACHED   REMOVED
           |         |
         merge()    flush/commit
           |         |
           v         v
      managed COPY  DELETE

close()/clear() cũng làm managed entity trở thành detached.
find() thường đưa entity được load vào managed state.
~~~

### 2.1. New/transient

Đối tượng mới được tạo bằng Java constructor, chưa được JPA provider quản lý.

~~~java
Document doc = new Document("DOC-1", "Draft");
assertFalse(em.contains(doc));
~~~

### 2.2. Managed

Sau khi `persist` thành công, đối tượng mới thường được quản lý trong persistence context. Mọi thay đổi persistent fields của managed entity sẽ được theo dõi cho dirty checking.

### 2.3. Detached

Khi `detach`, `clear` hoặc `close`, object rời persistence context. Các setters vẫn thay đổi Java state, nhưng không tự ghi database.

### 2.4. Removed

`remove` trên managed entity đưa nó vào trạng thái được đánh dấu xóa. SQL DELETE có thể được phát ở flush/commit; đến khi commit thành công mới xác nhận row bị xóa bền vững.

### 2.5. Lưu ý về cascade

State transitions có thể cascade tới related entities nếu mapping sử dụng `CascadeType.PERSIST`, `MERGE`, `REMOVE`, `DETACH` hoặc `ALL`. Một test entity đơn không đủ kiểm chứng graph.

---

## 3. Test gì bằng mock, test gì bằng database thật?

| Cấp độ | Dùng để kiểm | Không đủ để kiểm |
|---|---|---|
| Unit test với mock repository | Validation, error mapping, service orchestration | Actual entity mapping/SQL |
| JPA integration test | persist/find/merge/remove, L1 context, callbacks, constraints | External API end-to-end |
| Spring repository slice test | Repository methods, JPQL, Hibernate integration | Commit thật nếu mặc định test rollback |
| Full integration test | HTTP, security, service transaction, database | Race timing nếu không điều khiển concurrency |
| Concurrency/fault test | Optimistic locks, retry, DB transaction behavior | Mọi topology chưa thử |

Mock:

~~~java
when(repository.findById(42L))
    .thenReturn(Optional.empty());
~~~

giúp test cách service phản ứng với empty result. Nó không thể chứng minh `@Version` hoặc foreign key hoạt động. Để kiểm những semantics này, cần chạy JPA provider và database.

Nếu production sử dụng PostgreSQL, MySQL, Oracle hoặc SQL Server, test trên H2 chỉ có giá trị giới hạn: syntax, collation, isolation, constraints và generated IDs có thể khác.

---

## 4. Entity mẫu cho bài kiểm thử

~~~java
package com.example.jpa.domain;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(
    name = "test_document",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_test_document_code",
        columnNames = "code"
    )
)
public class Document {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(nullable = false, unique = true)
    private String code;

    @Column(nullable = false)
    private String title;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at")
    private Instant updatedAt;

    @Version
    private long version;

    @Transient
    private int postLoadCalls;

    @Transient
    private int preUpdateCalls;

    @Transient
    private int preRemoveCalls;

    protected Document() {}

    public Document(String code, String title) {
        this.code = code;
        this.title = title;
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getTitle() { return title; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public long getVersion() { return version; }
    public int getPostLoadCalls() { return postLoadCalls; }
    public int getPreUpdateCalls() { return preUpdateCalls; }
    public int getPreRemoveCalls() { return preRemoveCalls; }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Title required");
        }
        title = newTitle.strip();
    }

    @PrePersist
    void beforePersist() {
        title = title.strip();
        if (createdAt == null) {
            createdAt = Instant.now();
        }
    }

    @PreUpdate
    void beforeUpdate() {
        updatedAt = Instant.now();
        preUpdateCalls++;
    }

    @PostLoad
    void afterLoad() {
        postLoadCalls++;
    }

    @PreRemove
    void beforeRemove() {
        preRemoveCalls++;
    }
}
~~~

### 4.1. Vì sao có các field này?

- `id`: kiểm generated key và identity map.
- `code`: business key UNIQUE, kiểm DB constraint.
- `title`: persistent field để kiểm dirty checking/merge.
- `createdAt/updatedAt`: callback-controlled local state.
- `version`: optimistic locking.
- Ba counters `@Transient`: quan sát callbacks nhưng không ghi chúng vào database.

### 4.2. Database/provider

`GenerationType.SEQUENCE` phù hợp database có sequence support. Nếu DB không hỗ trợ, điều chỉnh strategy theo persistence unit test. Đừng lấy khác biệt key generator làm bằng chứng một lifecycle operation thất bại.

### 4.3. @Transient counter không persistent

Sau khi load từ transaction mới, counter bắt đầu từ giá trị Java mặc định và có thể được callback cập nhật. Không viết assertion rằng counter từ transaction trước phải được bảo toàn trong DB.

---

## 5. RESOURCE_LOCAL test fixture

Một JUnit 5 integration test có thể tạo `EntityManagerFactory` trong `@BeforeAll` rồi đóng ở `@AfterAll`. Mỗi test sử dụng EntityManager mới.

~~~java
import jakarta.persistence.*;
import org.junit.jupiter.api.*;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class DocumentJpaTest {

    static EntityManagerFactory emf;

    @BeforeAll
    static void init() {
        emf = Persistence.createEntityManagerFactory(
            "jpa-lifecycle-test"
        );
    }

    @AfterAll
    static void stop() {
        if (emf != null) {
            emf.close();
        }
    }

    static String uniqueCode() {
        return "DOC-" + UUID.randomUUID();
    }
}
~~~

File `META-INF/persistence.xml` của test phải định nghĩa đúng persistence unit, datasource, provider và schema setup. Khi dùng Spring/JTA, không áp mẫu `EntityTransaction` dưới đây cho EntityManager do container quản lý.

### 5.1. Không chia sẻ EntityManager giữa test cases

EntityManager không thread-safe và có first-level cache. Share cùng một EM có thể che những lỗi mà test cần phát hiện và gây tương tác ngầm giữa tests.

### 5.2. Dữ liệu fixture

Dùng code ngẫu nhiên/cố định theo test đã cô lập, reset schema hoặc transaction cleanup phù hợp. Không để hai tests dùng trùng một UNIQUE key ngoài dự kiến.

---

## 6. Helper tạo transaction độc lập

~~~java
import jakarta.persistence.*;
import java.util.function.Function;

public final class JpaTx {

    private JpaTx() {}

    public static <T> T execute(
            EntityManagerFactory emf,
            Function<EntityManager, T> work) {

        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            T result = work.apply(em);

            tx.commit();
            return result;
        } catch (RuntimeException | Error failure) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
            }
            throw failure;
        } finally {
            em.close();
        }
    }
}
~~~

Mỗi lần gọi `JpaTx.execute` thông thường có một persistence context và một RESOURCE_LOCAL transaction riêng. Helper đóng EM sau khi commit.

### 6.1. Vì sao return sau commit?

Callback `work` có thể trả ID nhưng commit thất bại. Helper chỉ trả kết quả bình thường sau khi `tx.commit()` đã hoàn tất mà không ném exception.

### 6.2. Không dùng helper như một bằng chứng rollback sau mất kết nối

Nếu DB đã commit nhưng ACK tới JDBC client bị mất, exception từ commit không đủ để kết luận rollback. Đây là tình huống cần operation identity/idempotency/reconciliation, khác bài test CRUD thông thường.

### 6.3. Hàm fixture

~~~java
static Long persistFixture() {
    return JpaTx.execute(emf, em -> {
        Document doc = new Document(
            uniqueCode(), "Initial title"
        );
        em.persist(doc);
        em.flush();
        return doc.getId();
    });
}
~~~

Hàm này đặt trong test class, dùng helper đã khai báo và đảm bảo transaction commit trước khi trả ID. Nó không được gọi để tự ý tạo nhiều fixtures có cùng code.

---

## 7. Kiểm thử persist: new → managed

~~~java
@Test
void persist_newEntity_becomesManaged() {
    JpaTx.execute(emf, em -> {
        Document doc = new Document(
            uniqueCode(), "  New title  "
        );

        assertFalse(em.contains(doc));
        assertNull(doc.getId());

        em.persist(doc);

        assertTrue(em.contains(doc));

        em.flush();

        assertNotNull(doc.getId());
        assertEquals("New title", doc.getTitle());
        assertNotNull(doc.getCreatedAt());

        return null;
    });
}
~~~

### 7.1. Assertions đang chứng minh điều gì?

`contains` chứng minh managed state. Các fields `title/createdAt` thể hiện `@PrePersist` xử lý local state. `id` sau flush thể hiện entity đã được cấp key trong test setup.

### 7.2. Không khẳng định commit chỉ nhờ contains

Khi gọi `contains` bên trong transaction, provider quản lý object nhưng transaction vẫn có thể rollback. Test này dùng helper commit, nhưng assertion trong lambda vẫn chỉ phản ánh thời điểm trước commit.

### 7.3. Không assert ID được cấp ngay ở mọi strategy

Với `IDENTITY`, ID có thể cần database INSERT; với `SEQUENCE` hoặc assigned UUID, provider có thể biết trước. Viết test sau flush/commit để tránh phụ thuộc timing không cần thiết.

---

## 8. Kiểm thử persist–commit–find trên context mới

~~~java
@Test
void persist_afterCommit_isVisibleInFreshContext() {
    String code = uniqueCode();

    Long id = JpaTx.execute(emf, em -> {
        Document doc = new Document(
            code, "  Contract  "
        );
        em.persist(doc);
        em.flush();
        return doc.getId();
    });

    Document loaded = JpaTx.execute(
        emf,
        em -> em.find(Document.class, id)
    );

    assertNotNull(loaded);
    assertEquals(id, loaded.getId());
    assertEquals(code, loaded.getCode());
    assertEquals("Contract", loaded.getTitle());
    assertNotNull(loaded.getCreatedAt());
}
~~~

Hai calls tạo hai contexts; entity của transaction đầu không thể được tìm lại chỉ vì còn nằm trong identity map của EM đầu.

### 8.1. Vì sao cần context mới?

Nếu gọi `find` ngay sau `persist` trong cùng EM, JPA có thể trả chính instance vừa persist. Test như vậy không chứng minh row đã được database commit.

### 8.2. Sau helper return

`loaded` đã detached vì EM thứ hai đóng. Các basic fields đã nạp vẫn có thể được đọc; lazy associations chưa initialized có thể gặp lỗi khi sử dụng sau close.

### 8.3. “Đọc trên EM mới” chưa chắc là “đọc từ physical SQL”

Provider có thể sử dụng L2 cache. Nếu cần assert SQL SELECT count, bật instrumentation hoặc disable L2/query cache trong test. Đối với kiểm DB state quan trọng, cấu hình nguồn đọc authoritative và transaction boundary rõ.

---

## 9. Kiểm thử find: Có và không có row

~~~java
@Test
void find_existingId_returnsEntity() {
    Long id = persistFixture();

    JpaTx.execute(emf, em -> {
        Document doc = em.find(Document.class, id);

        assertNotNull(doc);
        assertEquals(id, doc.getId());
        assertTrue(em.contains(doc));

        return null;
    });
}

@Test
void find_missingId_returnsNull() {
    JpaTx.execute(emf, em -> {
        Document doc = em.find(
            Document.class, Long.MAX_VALUE
        );

        assertNull(doc);
        return null;
    });
}
~~~

`EntityManager.find` có hợp đồng entity-or-null cho PK lookup. Nó không tự ném `NoResultException` vì không có record. `NoResultException` là tình huống điển hình của `Query.getSingleResult()`.

### 9.1. Cẩn thận với ID không tồn tại

Trong database test dùng chung, một giá trị ID đoán trước có thể tình cờ tồn tại. Prefer disposable schema/database hoặc fixture strategy chứng minh ID không tồn tại.

### 9.2. Không catch mọi exception rồi coi là not found

Một lỗi connection/query/transaction không phải bằng chứng row thiếu. Assertion `assertNull` nên được thực hiện trên kết quả `find` thành công.

---

## 10. Persistence context identity map: Hai lần find, một instance

~~~java
@Test
void find_sameIdentityInOneContext_returnsSameInstance() {
    Long id = persistFixture();

    JpaTx.execute(emf, em -> {
        Document first = em.find(
            Document.class, id
        );

        Document second = em.find(
            Document.class, id
        );

        assertNotNull(first);
        assertSame(first, second);

        return null;
    });
}
~~~

### 10.1. assertSame khác assertEquals

`assertSame` kiểm hai biến cùng Java reference. `assertEquals` có thể chỉ dựa trên `equals` của entity, ví dụ so theo ID.

### 10.2. Tại sao một SELECT có thể không được phát lần hai?

First-level cache duy trì managed instance theo persistent identity. Khi `find` cùng ID trong cùng EM, provider có thể trả từ context, không phải query database lần nữa.

### 10.3. Không dùng test này để kiểm committed visibility

Nó chứng minh identity map, không chứng minh một transaction khác nhìn thấy data.

---

## 11. Dirty checking: Managed entity tự được đồng bộ

~~~java
@Test
void managedMutation_isPersistedWithoutMerge() {
    Long id = persistFixture();

    JpaTx.execute(emf, em -> {
        Document doc = em.find(
            Document.class, id
        );

        doc.rename("Updated while managed");

        assertTrue(em.contains(doc));

        // Không gọi persist, merge hoặc repository.save.
        return null;
    });

    String title = JpaTx.execute(emf, em ->
        em.find(Document.class, id).getTitle()
    );

    assertEquals("Updated while managed", title);
}
~~~

Đây là một ví dụ quan trọng: khi entity đã managed trong transaction, JPA thường phát hiện persistent state đã thay đổi khi flush/commit.

### 11.1. Setter không phát SQL ngay lập tức

`doc.rename` thay Java state. SQL UPDATE được phát tại thời điểm provider đồng bộ persistence context, có thể trong flush hoặc commit.

### 11.2. Đừng gọi merge với managed entity chỉ vì muốn save

Merge managed entity thường không cần thiết cho cập nhật basic state; dùng domain methods để thay state rồi để dirty checking thực hiện.

---

## 12. Flush và commit không đồng nghĩa

~~~java
@Test
void flush_thenRollback_doesNotCommitRow() {
    String code = uniqueCode();

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Document doc = new Document(
            code, "Uncommitted"
        );
        em.persist(doc);
        em.flush();

        assertNotNull(doc.getId());

        tx.rollback();
    } finally {
        if (tx.isActive()) {
            tx.rollback();
        }
        em.close();
    }

    Long count = JpaTx.execute(emf, check ->
        check.createQuery(
            """
            SELECT COUNT(d) FROM Document d
            WHERE d.code = :code
            """,
            Long.class
        )
        .setParameter("code", code)
        .getSingleResult()
    );

    assertEquals(0L, count);
}
~~~

### 12.1. Điều gì được chứng minh?

Row không tồn tại sau rollback dù `flush()` và generated ID đã thành công.

### 12.2. Gaps của sequence là bình thường

ID đã cấp có thể bị bỏ qua sau rollback. Không assert IDs tăng liên tục hoặc gapless.

### 12.3. Callback có thể chạy trước rollback

`@PostPersist` không phải after-commit. Một callback đã chạy vẫn có thể tương ứng với DB transaction rollback.

---

## 13. Rollback do lỗi trong transaction

~~~java
@Test
void exceptionBeforeCommit_discardsPersistedEntity() {
    String code = uniqueCode();

    assertThrows(
        IllegalStateException.class,
        () -> JpaTx.execute(emf, em -> {
            em.persist(
                new Document(code, "Rollback me")
            );
            em.flush();

            throw new IllegalStateException(
                "Simulated application failure"
            );
        })
    );

    Long count = JpaTx.execute(emf, em ->
        em.createQuery(
            """
            SELECT COUNT(d) FROM Document d
            WHERE d.code = :code
            """,
            Long.class
        )
        .setParameter("code", code)
        .getSingleResult()
    );

    assertEquals(0L, count);
}
~~~

Đây là một transaction test, không chỉ exception test. Assertion quan trọng nằm ở **fresh transaction** sau rollback.

### 13.1. Phân biệt application exception và database error

Một runtime exception ném trước commit được helper rollback; database constraint failure cũng thường làm transaction fail, nhưng có thể phát sinh ở flush hoặc commit.

### 13.2. Không giữ EM hỏng để kiểm kết quả

Sau persistence exception nghiêm trọng, transaction có thể đã bị đánh dấu rollback-only. Rollback/close rồi xác minh bằng EM mới.

---

## 14. Kiểm thử detach: Entity không còn managed

~~~java
@Test
void detach_mutationsAreNotAutomaticallyStored() {
    Long id = persistFixture();

    Document detached = JpaTx.execute(
        emf,
        em -> em.find(Document.class, id)
    );

    detached.rename("Changed only in Java");

    String stored = JpaTx.execute(emf, em ->
        em.find(Document.class, id).getTitle()
    );

    assertEquals("Initial title", stored);
}
~~~

Helper đóng EM sau transaction đầu, nên `detached` không còn managed.

### 14.1. Explicit detach

~~~java
Document doc = em.find(Document.class, id);
assertTrue(em.contains(doc));

em.detach(doc);
assertFalse(em.contains(doc));
~~~

### 14.2. close và clear

`em.close()` detach mọi managed entities trong context đó. `em.clear()` cũng tách mọi managed instances; riêng `detach(entity)` xử lý một entity, với cascade DETACH nếu được mapping.

### 14.3. Detached setter vẫn đổi Java state

Không mong getter tự revert khi entity detached. Database chỉ giữ old value cho tới khi một managed instance được cập nhật và commit.

---

## 15. Kiểm thử clear và identity

~~~java
@Test
void clear_nextFindReturnsDifferentManagedInstance() {
    Long id = persistFixture();

    JpaTx.execute(emf, em -> {
        Document first = em.find(
            Document.class, id
        );

        em.clear();

        assertFalse(em.contains(first));

        Document second = em.find(
            Document.class, id
        );

        assertNotNull(second);
        assertNotSame(first, second);
        assertTrue(em.contains(second));
        return null;
    });
}
~~~

### 15.1. Clear trước flush có thể làm mất pending state

Nếu sửa một managed Document, rồi `clear()` trước flush, những thay đổi chưa được đồng bộ có thể bị bỏ qua. Test muốn giữ thay đổi cần chủ động flush trước clear hoặc commit trước khi mở context mới.

### 15.2. Không dùng clear để thay rollback

Clear chỉ tác động persistence context, không tự hủy transaction hoặc hoàn tác SQL đã được flush.

---

## 16. Kiểm thử merge: Detached → managed copy

~~~java
@Test
void merge_detachedStateIsCopiedToManagedInstance() {
    Long id = persistFixture();

    Document detached = JpaTx.execute(
        emf,
        em -> em.find(Document.class, id)
    );

    detached.rename("Edited offline");

    JpaTx.execute(emf, em -> {
        assertFalse(em.contains(detached));

        Document managed = em.merge(detached);

        assertTrue(em.contains(managed));
        assertFalse(em.contains(detached));
        assertNotSame(detached, managed);
        assertEquals(id, managed.getId());
        assertEquals(
            "Edited offline", managed.getTitle()
        );

        return null;
    });

    String stored = JpaTx.execute(emf, em ->
        em.find(Document.class, id).getTitle()
    );

    assertEquals("Edited offline", stored);
}
~~~

### 16.1. Điểm quan trọng nhất của merge

`merge(detached)` **không attach detached argument**. Provider tạo/tìm managed instance và sao chép state sang đó, rồi trả managed instance cho caller.

### 16.2. Đừng sửa detached sau merge

~~~java
Document managed = em.merge(detached);
detached.rename("Changed after merge"); // Không tự đồng bộ.
managed.rename("The managed change");   // Được theo dõi.
~~~

### 16.3. Kết quả còn tùy dirty state và version

Nếu detached snapshot không thực sự thay đổi persistent state, không được mặc định sẽ có SQL UPDATE. Với version conflict, exception có thể xuất hiện tại merge, flush hoặc commit.

---

## 17. Merge khi context đã chứa managed entity

~~~java
@Test
void merge_usesAlreadyManagedInstanceForSameIdentity() {
    Long id = persistFixture();

    Document detached = JpaTx.execute(
        emf,
        em -> em.find(Document.class, id)
    );

    detached.rename("Detached value");

    JpaTx.execute(emf, em -> {
        Document alreadyManaged =
            em.find(Document.class, id);

        Document result = em.merge(detached);

        assertSame(alreadyManaged, result);
        assertEquals(
            "Detached value", result.getTitle()
        );

        return null;
    });
}
~~~

### 17.1. Hai Java objects, một persistent identity

Detached và managed objects có thể cùng ID, nhưng chỉ một trong hai là managed của context hiện tại.

### 17.2. Stale detached snapshot có thể gây mất dữ liệu

Nếu một managed instance đã có changes khác rồi bị merge state cũ từ detached object, application có nguy cơ ghi đè. `@Version` và command-specific patch logic giúp kiểm soát, không nên biến merge thành generic “save bất cứ DTO nào”.

---

## 18. Merge của new entity

~~~java
@Test
void merge_newEntity_returnsManagedCopy() {
    String code = uniqueCode();

    Long id = JpaTx.execute(emf, em -> {
        Document input = new Document(
            code, "Created through merge"
        );

        Document managed = em.merge(input);

        assertNotSame(input, managed);
        assertFalse(em.contains(input));
        assertTrue(em.contains(managed));

        em.flush();
        return managed.getId();
    });

    assertNotNull(id);

    Document loaded = JpaTx.execute(
        emf,
        em -> em.find(Document.class, id)
    );

    assertEquals(
        "Created through merge", loaded.getTitle()
    );
}
~~~

### 18.1. Tại sao persist thường rõ hơn?

Với entity mới, `persist` quản lý chính instance đầu vào; `merge` áp copy semantics. Performance/SQL của merge có thể khác vì provider phải xác định entity state.

### 18.2. Merge không phải portable upsert contract

Đừng dựa vào merge để làm `INSERT ... ON CONFLICT DO UPDATE` atomic cho business keys. Nó có semantics entity state/identity, không tự giải quyết duplicate creates hoặc races.

---

## 19. Persist một detached entity là misuse

`persist` dành cho new entity. Gọi nó trên detached entity có thể ném `EntityExistsException` hoặc `PersistenceException` liên quan, ở lời gọi `persist`, `flush` hoặc `commit` tùy provider/tình huống.

~~~java
@Test
void persist_detachedIsNotAnUpdateOperation() {
    Long id = persistFixture();

    Document detached = JpaTx.execute(
        emf,
        em -> em.find(Document.class, id)
    );

    assertThrows(
        RuntimeException.class,
        () -> JpaTx.execute(emf, em -> {
            em.persist(detached);
            em.flush();
            return null;
        })
    );
}
~~~

Bài test cố tình chấp nhận superclass rộng để minh họa exception có thể được wrapper; trong suite thực tế nên assert exception/cause cụ thể theo provider/DB đang dùng.

### 19.1. Đừng dùng persist để “save existing”

Cách đơn giản nhất cho update là load managed entity trong transaction rồi mutate. Với detached graph, dùng merge và kiểm optimistic concurrency/relationship semantics.

---

## 20. Remove managed entity và kiểm row bị xóa

~~~java
@Test
void remove_managedEntity_deletesAfterCommit() {
    Long id = persistFixture();

    JpaTx.execute(emf, em -> {
        Document managed = em.find(
            Document.class, id
        );

        assertNotNull(managed);
        em.remove(managed);
        em.flush();

        assertTrue(
            managed.getPreRemoveCalls() >= 1
        );

        return null;
    });

    Document missing = JpaTx.execute(
        emf,
        em -> em.find(Document.class, id)
    );

    assertNull(missing);
}
~~~

### 20.1. Remove không nhất thiết DELETE ngay khi gọi

Provider có thể trì hoãn statement tới flush/commit. Không coi method return là cam kết row đã mất bền vững.

### 20.2. PreRemove chỉ là callback

Một callback PreRemove có thể chạy trước transaction rollback. Không gửi external notification ở đó như thể xóa đã hoàn tất.

### 20.3. Nếu không tìm thấy

Nếu `em.find` trả null, hãy theo delete contract của service (not-found hoặc idempotent success). Không gọi `em.remove(null)` rồi kết luận đó là xử lý chuẩn.

---

## 21. Remove detached entity không hợp lệ

~~~java
@Test
void remove_detachedEntity_isRejected() {
    Long id = persistFixture();

    Document detached = JpaTx.execute(
        emf,
        em -> em.find(Document.class, id)
    );

    assertThrows(
        IllegalArgumentException.class,
        () -> JpaTx.execute(emf, em -> {
            em.remove(detached);
            return null;
        })
    );
}
~~~

### 21.1. Hướng thực hành

~~~java
Document managed = em.find(
    Document.class, detached.getId()
);

if (managed != null) {
    em.remove(managed);
}
~~~

### 21.2. Tại sao không cứ merge rồi remove?

`em.remove(em.merge(detached))` có thể có tác dụng phụ do copy detached state và cascade MERGE trước khi remove. Nếu nghiệp vụ chỉ cần xóa theo ID, load/lock đúng row, kiểm authorization rồi remove thường rõ ràng hơn.

---

## 22. Remove rồi rollback

~~~java
@Test
void remove_thenRollback_keepsDatabaseRow() {
    Long id = persistFixture();

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Document doc = em.find(
            Document.class, id
        );

        em.remove(doc);
        em.flush();

        tx.rollback();
    } finally {
        if (tx.isActive()) {
            tx.rollback();
        }
        em.close();
    }

    Document stillPresent = JpaTx.execute(
        emf,
        check -> check.find(
            Document.class, id
        )
    );

    assertNotNull(stillPresent);
}
~~~

### 22.1. Test tại fresh transaction

Không kiểm instance removed sau rollback trong EM cũ để suy luận DB đã hoàn tác; object state trong memory có thể không tự trở lại như trước.

### 22.2. PostRemove không phải after-commit

Một provider có thể gọi PostRemove sau DELETE SQL nhưng trước khi transaction rollback vì lỗi khác. Nếu cần event chỉ cho committed deletion, dùng transactional outbox hoặc after-commit mechanism phù hợp.

---

## 23. Lifecycle callbacks: Test theo sự kiện, không theo setter

Các annotation thường gặp:

| Callback | Sự kiện | Lưu ý test |
|---|---|---|
| `@PrePersist` | Trước persist/INSERT lifecycle operation | IDENTITY ID có thể chưa cấp |
| `@PostPersist` | Sau persist/INSERT lifecycle operation | Không có nghĩa commit |
| `@PreUpdate` | Trước UPDATE lifecycle operation | Không chạy ngay ở setter |
| `@PostUpdate` | Sau UPDATE lifecycle operation | Transaction vẫn có thể rollback |
| `@PreRemove` | Trước remove/DELETE lifecycle operation | Có thể xảy ra trước flush |
| `@PostRemove` | Sau remove/DELETE lifecycle operation | Không là after-commit |
| `@PostLoad` | Sau load/refresh theo lifecycle | Không gọi lại cho mọi `find` trên L1 |

### 23.1. @PrePersist

~~~java
Document doc = new Document(
    uniqueCode(), "  Padded title  "
);
em.persist(doc);
em.flush();

assertEquals("Padded title", doc.getTitle());
assertNotNull(doc.getCreatedAt());
~~~

Sau commit, đọc lại để chắc normalized title/createdAt được lưu trong DB.

### 23.2. @PreUpdate

~~~java
Document doc = em.find(Document.class, id);
doc.rename("Changed");
em.flush();

assertTrue(doc.getPreUpdateCalls() >= 1);
assertNotNull(doc.getUpdatedAt());
~~~

Không assert callback chạy chỉ vì gọi `rename()`; callback gắn với actual update lifecycle.

### 23.3. @PostLoad

~~~java
Document doc = em.find(Document.class, id);
assertTrue(doc.getPostLoadCalls() >= 1);

Document same = em.find(Document.class, id);
assertSame(doc, same);
~~~

Một repeated find cùng context thường không thực hiện load mới, nên đừng mong `PostLoad` là “mỗi lần gọi find”.

### 23.4. @PreRemove

~~~java
Document doc = em.find(Document.class, id);
em.remove(doc);
em.flush();

assertTrue(doc.getPreRemoveCalls() >= 1);
~~~

### 23.5. Đừng test callbacks bằng external side effects

Từ callbacks không nên gọi network, broker hoặc `EntityManager` query lồng nhau để chỉ đếm sự kiện. Sử dụng transient counters, listener spy cô lập hoặc test instrumentation phù hợp.

---

## 24. Thời điểm gọi lifecycle callback không phải commit time

~~~text
BEGIN
  persist(Document)
  INSERT tại flush
  @PostPersist
  INSERT entity khác -> violation
ROLLBACK
~~~

Dù `@PostPersist` chạy, Document không được commit. Đối với `@PostUpdate` và `@PostRemove` cũng không được coi là after-commit confirmation.

### 24.1. Test rollback sau callback

Tạo entity, flush để callbacks tương ứng có thể diễn ra, gây lỗi trước commit, rollback, rồi đọc lại từ context mới.

### 24.2. Không dùng callback để tạo audit entity bằng em.persist

Trong portable JPA lifecycle callback, tránh gọi EntityManager/query, truy cập entities khác và thay relationship graph. Cross-entity audit nên ở service hoặc auditing infrastructure có transaction contract rõ.

### 24.3. @PreUpdate không phải field-change observer

Một managed entity không dirty có thể không tạo UPDATE và không gọi PreUpdate. Không dùng callback này như “lastSeenAt được cập nhật mỗi lần GET”.

---

## 25. Cascade PERSIST: Parent và children

Một mô hình khác để test graph:

~~~java
@Entity
public class Project {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @OneToMany(
        mappedBy = "project",
        cascade = CascadeType.PERSIST
    )
    private List<ProjectTask> tasks =
        new ArrayList<>();

    protected Project() {}

    public void addTask(ProjectTask task) {
        tasks.add(task);
        task.setProject(this);
    }

    public Long getId() { return id; }
    public List<ProjectTask> getTasks() {
        return tasks;
    }
}
~~~

~~~java
@Entity
public class ProjectTask {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @ManyToOne(optional = false)
    @JoinColumn(
        name = "project_id", nullable = false
    )
    private Project project;

    protected ProjectTask() {}

    public void setProject(Project project) {
        this.project = project;
    }

    public Long getId() { return id; }
}
~~~

### 25.1. Test persist graph

~~~java
Project project = new Project();
ProjectTask task = new ProjectTask();

project.addTask(task);

em.persist(project);
em.flush();

assertTrue(em.contains(project));
assertTrue(em.contains(task));
~~~

Sau commit, đọc lại Task/Project và xác minh FK đúng.

### 25.2. Owning side quan trọng

`ProjectTask.project` sở hữu FK. Chỉ thêm Task vào `project.tasks` mà không set `task.project` có thể khiến FK null/sai.

### 25.3. Cascade type là một hợp đồng cụ thể

`cascade = PERSIST` không đồng nghĩa `MERGE` và `REMOVE` cũng cascade. Test các operation được khai báo thực sự.

---

## 26. Cascade MERGE và orphanRemoval

Một mapping:

~~~java
@OneToMany(
    mappedBy = "project",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE
    },
    orphanRemoval = true
)
private List<ProjectTask> tasks;
~~~

### 26.1. Test cascade MERGE

1. Persist Project với một Task, commit.
2. Load Project và initialize Tasks khi còn EM mở.
3. Đóng EM để graph detached.
4. Đổi persistent fields của parent và child.
5. Merge parent trong EM mới.
6. Kiểm returned managed graph.
7. Commit và đọc DB state bằng EM khác.

Khi child được update thông qua cascade MERGE, phải có mapping `MERGE` phù hợp, không tự suy rằng mọi association cascade.

### 26.2. Test orphanRemoval

1. Persist Project có hai persistent Tasks, commit.
2. Load Project và collection trong transaction khác.
3. Gọi domain helper loại một task khỏi collection và xóa reference owning side.
4. Flush/commit.
5. Fresh read: task bị loại không còn row; task còn lại vẫn có.

### 26.3. orphanRemoval khác CascadeType.REMOVE

`orphanRemoval` xử lý một child bị tách khỏi quan hệ với parent. `CascadeType.REMOVE` áp khi remove parent. Không viết một test rồi coi đã bao phủ cả hai.

### 26.4. Trường hợp child còn new

Đừng mặc định orphanRemoval phải phát DELETE cho một child chỉ vừa tạo, chưa persistent. JPA lifecycle và state của child ảnh hưởng semantics.

---

## 27. Lazy loading và detached entity

Giả sử:

~~~java
@OneToMany(
    mappedBy = "project",
    fetch = FetchType.LAZY
)
private List<ProjectTask> tasks;
~~~

Nếu Project detached khi collection chưa initialized, truy cập sau khi EM đóng có thể gây lỗi lazy initialization tùy provider.

### 27.1. Test ở đúng transaction scope

Test dữ liệu graph cần chủ động fetch collection bằng JOIN FETCH, EntityGraph hoặc DTO query trong transaction, rồi mới dùng ngoài transaction.

### 27.2. Không assert Hibernate exception cho mọi provider

`LazyInitializationException` là Hibernate-specific, không phải exception portable do JPA quy định cho mọi tình huống detached lazy access.

### 27.3. Open Session in View không thay fetch design

Việc context mở dài tới view có thể che N+1 và query phát ở serialization. Integration tests cần xem fetch plan và SQL count nếu hiệu năng quan trọng.

---

## 28. refresh, detach và clear

### 28.1. refresh

~~~java
Document managed = em.find(
    Document.class, id
);

managed.rename("Not yet flushed");

em.refresh(managed);
~~~

`refresh` reload persistent state vào managed entity và có thể ghi đè pending in-memory changes. Không dùng refresh làm “đảm bảo commit”.

### 28.2. detach

~~~java
Document managed = em.find(
    Document.class, id
);

em.detach(managed);

assertFalse(em.contains(managed));
~~~

### 28.3. clear

~~~java
em.clear();
~~~

Tách mọi managed entities khỏi context. Một pending change chưa flush có thể bị bỏ qua.

### 28.4. Tests nên tách từng method

Một test muốn chứng minh `refresh` overwrite state không nên trộn thêm `merge`/`remove` nếu không cần. Kiểm từng transition với data readback phù hợp.

---

## 29. Optimistic locking với @Version

Một versioned entity ngăn lost update theo JPA optimistic locking semantics.

~~~text
EntityManager A: load Document id=10, version=0
EntityManager B: load Document id=10, version=0

A: rename, commit -> version tăng
B: rename, commit -> stale update bị từ chối
~~~

### 29.1. Hai EntityManagers độc lập

~~~java
@Test
void version_rejectsStaleConcurrentUpdate() {
    Long id = persistFixture();

    EntityManager a = emf.createEntityManager();
    EntityManager b = emf.createEntityManager();

    try {
        a.getTransaction().begin();
        b.getTransaction().begin();

        Document left = a.find(
            Document.class, id
        );
        Document right = b.find(
            Document.class, id
        );

        left.rename("Winner");
        a.getTransaction().commit();

        right.rename("Stale");

        assertThrows(
            RuntimeException.class,
            () -> b.getTransaction().commit()
        );

        if (b.getTransaction().isActive()) {
            b.getTransaction().rollback();
        }
    } finally {
        if (a.getTransaction().isActive()) {
            a.getTransaction().rollback();
        }
        if (b.getTransaction().isActive()) {
            b.getTransaction().rollback();
        }
        a.close();
        b.close();
    }

    String title = JpaTx.execute(emf, em ->
        em.find(Document.class, id).getTitle()
    );

    assertEquals("Winner", title);
}
~~~

### 29.2. Exception type/timing

Tại commit, provider có thể ném `OptimisticLockException` hoặc wrapper. Suite thực tế nên assert đúng optimistic-lock cause theo stack chứ không chấp nhận bất kỳ lỗi không liên quan.

### 29.3. Transaction isolation ảnh hưởng concurrency test

Một database có snapshot/isolation semantics khác có thể gây lỗi cạnh tranh sớm hơn hoặc connection waits. Test trên DB tương đương production và đặt timeouts.

### 29.4. Không share EM giữa threads

Mỗi concurrent worker phải dùng EntityManager/transaction riêng; JPA EntityManager không thread-safe.

---

## 30. Merge một detached snapshot đã stale

Một request frontend đọc Document version 3. Giao dịch khác update thành version 4. Frontend gửi lại snapshot version 3 để merge.

### 30.1. Test setup

- Commit một entity có `@Version`.
- Load entity A trong EM riêng rồi detach.
- EM B sửa entity và commit.
- Sửa detached A.
- EM C merge A và flush/commit.
- Assert version conflict theo stack.
- Fresh read xác nhận kết quả B không bị ghi đè.

### 30.2. Không dựa vào ID để kiểm concurrency

Cùng primary key vẫn có thể mang snapshot cũ. Version là cơ chế để nhận biết stale state; ID chỉ xác định row.

### 30.3. Merge DTO tùy tiện có thể gây lost update

Với một DTO chứa null/defaults thay cho fields chưa gửi, merge có thể ghi đè state. Dùng command-specific methods trên managed entity và version/ETag checks rõ ràng.

---

## 31. Kiểm thử constraints tại flush/commit

Entity có unique business key `code`. Hai entities dùng cùng code không thể cùng commit nếu database UNIQUE constraint tồn tại.

~~~java
@Test
void duplicateCode_failsAtFlushOrCommit() {
    String code = uniqueCode();

    JpaTx.execute(emf, em -> {
        em.persist(
            new Document(code, "First")
        );
        return null;
    });

    assertThrows(
        RuntimeException.class,
        () -> JpaTx.execute(emf, em -> {
            em.persist(
                new Document(code, "Duplicate")
            );
            em.flush();
            return null;
        })
    );

    Long count = JpaTx.execute(emf, em ->
        em.createQuery(
            """
            SELECT COUNT(d) FROM Document d
            WHERE d.code = :code
            """,
            Long.class
        )
        .setParameter("code", code)
        .getSingleResult()
    );

    assertEquals(1L, count);
}
~~~

### 31.1. Exception có thể bọc nhiều lớp

Hibernate `ConstraintViolationException`, JPA `PersistenceException`/`RollbackException` và Spring `DataIntegrityViolationException` khác nhau theo stack. Test nên kiểm cause/constraint semantics đúng môi trường.

### 31.2. Không chỉ assertThrows

Fresh read đảm bảo first committed row còn, second failed transaction không tạo duplicate.

### 31.3. Foreign keys cũng phải được test

Khi Task tham chiếu Project không tồn tại hoặc không set owning side, test cần xác minh database FK/NOT NULL constraints thay vì chỉ Java annotation.

---

## 32. JPQL bulk DML không đi qua per-entity lifecycle như remove

~~~java
int affected = em.createQuery(
    """
    UPDATE Document d
    SET d.title = :title
    WHERE d.id = :id
    """
)
.setParameter("title", "Bulk")
.setParameter("id", id)
.executeUpdate();
~~~

### 32.1. @PreUpdate có thể không chạy cho mỗi row

Bulk JPQL bypass per-entity dirty checking/lifecycle callbacks. Không dùng `@PreUpdate` counter để test bulk update.

### 32.2. Persistence context có thể stale

Nếu đã load Document thành managed, sau bulk update Java object có thể giữ giá trị cũ.

~~~java
Document managed = em.find(
    Document.class, id
);

em.createQuery(
    "UPDATE Document d SET d.title = :t WHERE d.id = :id"
)
.setParameter("t", "Bulk")
.setParameter("id", id)
.executeUpdate();

em.clear();

Document fresh = em.find(
    Document.class, id
);

assertEquals("Bulk", fresh.getTitle());
~~~

### 32.3. Bulk DELETE khác remove

`DELETE FROM Document d ...` không mặc định chạy `@PreRemove`/`@PostRemove` per entity hoặc cascade như `em.remove`.

### 32.4. Bulk @Version

Version field không tự được update theo cùng semantics managed entity UPDATE. Nếu business cần optimistic locking, thiết kế DML predicate/update rõ.

---

## 33. EntityManager.find và getReference

`find` trả entity hoặc null khi row không tồn tại theo PK.

`getReference` có thể tạo một reference/proxy mà chưa truy vấn DB ngay; dữ liệu không tồn tại có thể chỉ được phát hiện khi state được truy cập theo implementation semantics.

### 33.1. Test getReference theo contract

Không bắt buộc provider phát SELECT ngay tại `getReference`. Kiểm object usage ở transaction scope và exception semantics của stack.

### 33.2. Không dùng reference làm bằng chứng tồn tại

Có Java reference không chứng minh row tồn tại hay caller được phép truy cập.

### 33.3. Authorization tách khỏi lifecycle

`em.find(Document.class,id)` không tự kiểm tenant/owner. Các service-level tests phải kiểm scoped query và object authorization riêng.

---

## 34. FlushMode AUTO và COMMIT

~~~java
em.setFlushMode(FlushModeType.AUTO);
~~~

Với `AUTO`, provider phải đảm bảo query consistency theo semantics JPA và có thể flush trước query nếu pending changes ảnh hưởng kết quả.

~~~java
em.setFlushMode(FlushModeType.COMMIT);
~~~

Với `COMMIT`, tác động của những pending updates lên queries trước commit không luôn được bảo đảm như AUTO.

### 34.1. Vì sao test có thể sai?

Một test sửa managed entity rồi dùng JPQL query ngay có thể thấy kết quả khác do flush mode/provider. Nó không nhất thiết là lỗi dirty checking.

### 34.2. Không trộn find và JPQL query

`find` có thể trả managed object từ L1; JPQL query có thể yêu cầu SQL/flush. Khi muốn test DB state, dùng flush/commit/clear/new EM phù hợp.

---

## 35. Spring Data JPA: @DataJpaTest

Với Spring Boot, repository test có thể viết:

~~~java
@DataJpaTest
class DocumentRepositoryTest {

    @Autowired
    TestEntityManager tem;

    @Autowired
    DocumentRepository repository;

    @Test
    void saveAndFind() {
        Document doc = new Document(
            "SPRING-" + UUID.randomUUID(),
            "Hello"
        );

        Document saved = repository.save(doc);

        tem.flush();
        tem.clear();

        Optional<Document> found =
            repository.findById(saved.getId());

        assertTrue(found.isPresent());
        assertEquals(
            "Hello",
            found.orElseThrow().getTitle()
        );
    }
}
~~~

`DocumentRepository` là interface ví dụ extends `JpaRepository<Document, Long>`.

### 35.1. Cảnh báo quan trọng về @DataJpaTest

Theo Spring Boot defaults, `@DataJpaTest` thường chạy trong **test-managed transaction sẽ rollback** khi test kết thúc. `tem.flush()` không tự commit; `tem.clear()` cũng không tạo transaction mới.

### 35.2. Điều gì được test?

Mapping, repository save/find, flush và L1 behavior trong test transaction. Không mặc định đã kiểm data committed sau test.

### 35.3. Test DB thay thế

`@DataJpaTest` có thể dùng embedded DB khi dependency/configuration cho phép. Với yêu cầu production-like, tắt replacement và cấu hình datasource/Testcontainers phù hợp.

---

## 36. Kiểm committed state trong Spring bằng TransactionTemplate

Một cách rõ ràng là tắt test-managed transaction cho test cụ thể và chủ động tạo transactions:

~~~java
@DataJpaTest
@Transactional(
    propagation = Propagation.NOT_SUPPORTED
)
class CommittedDocumentTest {

    @Autowired
    EntityManager em;

    @Autowired
    PlatformTransactionManager manager;

    @Test
    void committedDocumentIsReadableNextTransaction() {
        TransactionTemplate tx =
            new TransactionTemplate(manager);

        String code =
            "TX-" + UUID.randomUUID();

        Long id = tx.execute(status -> {
            Document doc = new Document(
                code, "Committed"
            );
            em.persist(doc);
            em.flush();
            return doc.getId();
        });

        String title = tx.execute(status -> {
            em.clear();
            return em.find(
                Document.class, id
            ).getTitle();
        });

        assertEquals("Committed", title);
    }
}
~~~

### 36.1. Hai tx.execute là hai transaction boundaries

Với test-level transaction bị suspend/disabled như trên, mỗi template call mở/commit một transaction theo Spring transaction manager.

### 36.2. Cleanup

Test đã commit dữ liệu thật; không trông đợi framework rollback sau test. Dùng disposable DB/schema hoặc cleanup transaction.

### 36.3. Không gọi em.getTransaction với Spring-managed EntityManager

Spring transaction manager sở hữu transaction. Nếu cần kiểm ngoại lệ xảy ra tại commit, catch exception ở bên ngoài `TransactionTemplate.execute`.

---

## 37. Spring TestTransaction để commit giữa test

Khi một Spring test đã chạy trong test-managed transaction:

~~~java
@Test
void commitThenFindInNextTestTransaction() {
    Document doc = new Document(
        "TT-" + UUID.randomUUID(), "Saved"
    );

    em.persist(doc);
    em.flush();

    Long id = doc.getId();

    TestTransaction.flagForCommit();
    TestTransaction.end();

    TestTransaction.start();

    em.clear();

    Document found = em.find(
        Document.class, id
    );

    assertNotNull(found);
}
~~~

### 37.1. TestTransaction cần test framework hỗ trợ

Cách này chỉ phù hợp với một test đã được Spring TestContext quản lý transaction, không dùng cho JPA RESOURCE_LOCAL thuần.

### 37.2. Đã commit thì phải dọn data

`flagForCommit` làm row tồn tại sau test transaction đầu. Bảo đảm test isolation bằng unique keys, test schema hoặc cleanup.

### 37.3. Không phải mọi test đều cần commit thật

Đối với tests mapping cơ bản, rollback mặc định có thể nhanh và đủ. Chỉ cần explicit commit khi mục tiêu là transaction durability/visibility.

---

## 38. Testcontainers với database gần production

Một Spring Boot test có thể dùng PostgreSQL Testcontainers:

~~~java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class DocumentPostgresTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void configure(
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
    }
}
~~~

Các imports/dependencies của Spring Boot, JUnit 5 và Testcontainers phải khớp project. Chọn image/tag theo DB target, không mặc định PostgreSQL 16 là phiên bản production của mọi ứng dụng.

### 38.1. Vì sao đáng dùng?

- Test đúng DDL và unique/FK constraints.
- Kiểm sequence/identity mapping đúng dialect.
- Tái hiện optimistic locking và DB transaction semantics sát hơn H2.
- Phát hiện native query/dialect issues.

### 38.2. Testcontainers không tự mô phỏng failover

Một container database đơn không cho thấy mọi lỗi replica lag, failover, network partition. Chúng cần môi trường/fault-injection tests riêng.

---

## 39. SQL logging và xác minh hành vi JPA

Nếu muốn kiểm SQL count hoặc N+1:

- Hibernate SQL logs/statistics hoặc JDBC proxy.
- Database query logs/tracing.
- Query count assertions trong integration test có setup ổn định.
- Cache được kiểm soát trong test (L1/L2/query cache).
- Đo flush/commit, không chỉ thời gian `persist()`.

### 39.1. Đừng assert mỗi persist luôn phát một INSERT ngay

JPA có write-behind; SQL timing phụ thuộc generator, flush mode, provider và transaction.

### 39.2. Không hiểu SQL logging như API portable

Hibernate statistics là Hibernate-specific. Các providers khác dùng metrics khác. Một test chỉ cần xác nhận DB state không nên quá gắn với exact SQL statement ordering.

### 39.3. Batch writes và generated IDs

`IDENTITY` có thể đòi INSERT sớm để nhận key, còn `SEQUENCE` thường cấp ID trước INSERT. Test generated ID timing không được áp kết luận từ một strategy sang strategy khác.

---

## 40. Concurrency tests phải kiểm data cuối

Khi hai transactions update cùng entity:

1. Cả hai đọc cùng version ban đầu.
2. Transaction A thay đổi và commit.
3. Transaction B cố commit stale state.
4. Assert optimistic locking conflict.
5. Dùng transaction mới xác nhận DB state là kết quả A.

### 40.1. Tránh Thread.sleep để điều khiển race

Dùng `CountDownLatch`, `CyclicBarrier` hoặc sequencing rõ để bảo đảm threads đến đúng điểm.

### 40.2. Transaction per thread

Mỗi thread có EntityManager riêng. Không dùng cùng EM qua nhiều threads.

### 40.3. Timeouts và cleanup

Concurrency test có thể deadlock/wait lock; cần timeout, rollback failed transaction và dọn fixtures.

### 40.4. Concrete exception

Có thể là `OptimisticLockException` hoặc wrapper của Spring/Hibernate. Kiểm root cause/correctness, không coi mọi `RuntimeException` là pass.

---

## 41. Authorization, multi-tenancy và lifecycle

Một service JPA có thể load Document theo PK và sửa nó:

~~~java
Document doc = em.find(
    Document.class, id
);
doc.rename(title);
~~~

Điều này không tự bảo vệ object-level authorization. Nếu entity thuộc tenant/owner khác, thao tác vẫn có thể đúng về mặt JPA và sai về mặt bảo mật.

### 41.1. Các tests bổ sung

- User A không đọc Document của user B ngoài quyền.
- Tenant T1 không mutate/delete entity T2.
- `merge` không cho caller override tenantId/ownerId từ DTO.
- Bulk UPDATE/DELETE giữ tenant/ACL predicates.
- Cascade associations không liên kết entity của tenant khác.

### 41.2. Đừng nhầm @Version với phân quyền

Version giúp concurrency control, không biết caller có quyền sửa row hay không.

---

## 42. Các lỗi test phổ biến

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Persist test pass nhưng row không có sau test | Test transaction rollback hoặc chỉ assert ID | Commit + fresh read khi cần |
| Find trả same object sau setter | L1 identity map | Clear/new EM |
| Merge test chỉ kiểm detached argument | Merge tạo/copy vào managed instance khác | Kiểm returned managed instance |
| Detached setter không ghi DB | Object không managed | Managed mutation hoặc merge |
| Remove detached thất bại | API yêu cầu managed | Find/lock rồi remove |
| Remove trả bình thường nhưng row chưa mất | DELETE deferred | Flush/commit + fresh read |
| @PreUpdate không chạy ngay khi setter | Lifecycle gắn với UPDATE | Flush dirty entity |
| @PostPersist chạy rồi rollback | Callback trước commit | Test durability riêng |
| @PostLoad không chạy lần find thứ hai | L1 đã có instance | Fresh context nếu test load |
| @Transient counter không giữ qua transaction | Không persistent | Kỳ vọng đúng |
| Hibernate lazy exception ngoài EM | Detached association chưa initialized | Fetch plan/DTO |
| Cascade child không được INSERT | Thiếu cascade hoặc owning side | Mapping + domain helper |
| Orphan child vẫn còn | Chưa persistent, mapping/helper sai | Test state/relationship |
| Bulk update bỏ qua @PreUpdate | Bulk DML bypass lifecycle | Test riêng |
| Duplicate code lỗi ở commit | Constraint kiểm muộn | Bao cả commit trong test |
| @Version stale test không fail | Hai requests chưa thật sự dùng stale snapshots | Two EM + distinct versions |
| H2 pass PostgreSQL fail | DB behavior khác | Testcontainers DB target |
| Tests flake khi parallel | Shared fixture/EM/schema | Isolation và unique keys |
| ID gaps làm assertion fail | Sequence caching/rollback | Không assert gapless IDs |
| @DataJpaTest không test commit | Test framework rollback mặc định | TransactionTemplate/TestTransaction |
| SQL count không ổn định | L2 cache/flush/dialect | Controlled instrumentation |

---

## 43. Ma trận kiểm thử đề xuất

| Operation | Input state | Hậu điều kiện | Assertion quan trọng |
|---|---|---|---|
| persist | New | Managed | `contains == true` |
| persist | New + commit | Row tồn tại | Fresh EM find |
| persist | New + rollback | Không có committed row | Fresh count=0 |
| persist | Detached | Misuse/exception | persist–flush–commit boundary |
| find | Existing PK | Managed instance | non-null, contains |
| find | Missing PK | Không tìm thấy | null |
| find | Same PK trong 1 EM | Identity map | assertSame |
| find | Sau clear | Instance managed khác | assertNotSame |
| managed update | Managed | Dirty checking | Fresh title đổi |
| detached update | Detached | Không auto-save | Fresh title cũ |
| merge | Detached | Managed copy | `contains(result)`, not input |
| merge | New | Managed copy/INSERT | Fresh row |
| merge | Stale version | Optimistic conflict | Cause + final DB state |
| remove | Managed | DELETE sau commit | Fresh find=null |
| remove | Detached | Không hợp lệ | IllegalArgumentException |
| remove | Managed + rollback | Row còn | Fresh find non-null |
| callback | Persist | Local normalization | PrePersist + fresh read |
| callback | Dirty UPDATE | updatedAt được điền | PreUpdate sau flush |
| callback | Load | PostLoad local state | Fresh EM |
| callback | Remove | PreRemove được gọi | Transient counter |
| cascade | Parent new | Child persisted | Fresh FK read |
| orphanRemoval | Child persistent | Child DELETE | Fresh find child=null |
| bulk DML | Query update/delete | Không per-entity lifecycle | SQL count/state |
| @Version | Two contexts | Reject stale write | Failure + winner retained |
| unique constraint | Duplicate key | Không commit duplicate | Count=1 |
| @DataJpaTest | Default tx | Rollback test | Đừng suy commit từ flush |

---

## 44. Bài tập thực hành

### Bài 1. New entity

`new Document(...)` có là managed entity không?

**Đáp án:** Chưa. Đó là transient/new entity, trừ khi đã được đưa vào persistence context theo JPA lifecycle.

### Bài 2. Persist

`em.persist(doc)` có tự commit không?

**Đáp án:** Không. Nó thay persistence lifecycle state; transaction commit là việc khác.

### Bài 3. ID

ID khác null sau persist/flush có chứng minh row committed?

**Đáp án:** Không. Rollback vẫn có thể xảy ra.

### Bài 4. Find cùng EM

Hai lần `em.find(Document.class,id)` trong một context trả gì?

**Đáp án:** Cùng managed instance cho persistent identity đó; có thể kiểm `assertSame`.

### Bài 5. Find missing

**Đáp án:** `em.find` trả null; `NoResultException` là behavior của `getSingleResult` trên query không có result.

### Bài 6. Dirty checking

Managed entity đổi title và commit, có cần gọi merge không?

**Đáp án:** Không. Provider theo dõi state và đồng bộ khi flush/commit.

### Bài 7. Detached mutation

**Đáp án:** Java object đổi nhưng database không tự update.

### Bài 8. Clear

**Đáp án:** Tách mọi managed instances; pending unflushed state có thể bị mất.

### Bài 9. Merge detached

**Đáp án:** Trả managed copy, không biến input thành managed.

### Bài 10. Sửa input sau merge

**Đáp án:** Không tự ảnh hưởng returned managed instance.

### Bài 11. Merge new entity

**Đáp án:** Có thể tạo managed copy và INSERT; với new entity, persist thường dễ hiểu hơn.

### Bài 12. Persist detached

**Đáp án:** Không phải update API; có thể ném EntityExists/PersistenceException ở persist/flush/commit.

### Bài 13. Remove managed

**Đáp án:** Đánh dấu xóa; cần commit + fresh read để xác nhận row mất.

### Bài 14. Remove detached

**Đáp án:** Không hợp lệ; load managed rồi remove.

### Bài 15. Remove rollback

**Đáp án:** Row còn sau rollback; kiểm bằng transaction mới.

### Bài 16. @PrePersist

**Đáp án:** Có thể normalize basic fields của chính entity; callback không phải commit confirmation.

### Bài 17. @PreUpdate

**Đáp án:** Gắn với update lifecycle, không chạy ngay tại setter.

### Bài 18. @PostLoad

**Đáp án:** Chạy khi entity được load/refresh theo semantics, không mặc định với mỗi repeated find từ L1.

### Bài 19. @PostRemove

**Đáp án:** Không chứng minh database transaction đã commit.

### Bài 20. Cascade PERSIST

**Đáp án:** Có thể persist children khi mapping có PERSIST và owning side được gán đúng.

### Bài 21. OrphanRemoval

**Đáp án:** Với persistent child bị tách khỏi collection có orphanRemoval, provider có thể DELETE child theo lifecycle; không nhầm với cascade REMOVE khi xóa parent.

### Bài 22. Merge stale

**Đáp án:** `@Version` cần phát hiện stale state theo provider/transaction semantics.

### Bài 23. JPQL bulk update

**Đáp án:** Không mặc định gọi `@PreUpdate` cho từng managed row, không tự đồng bộ L1 cache.

### Bài 24. H2

H2 pass nghĩa là PostgreSQL production chắc chắn pass?

**Đáp án:** Không. Test trên database dialect/engine đại diện production cho các semantics quan trọng.

### Bài 25. @DataJpaTest

Flush rồi clear trong test có nghĩa DB đã commit?

**Đáp án:** Không; Spring Data slice test thường rollback test transaction cuối test.

### Bài 26. Commit thật trong Spring

**Đáp án:** Dùng transaction boundaries riêng như TransactionTemplate/TestTransaction hoặc test không nằm trong test-managed rollback transaction.

### Bài 27. Persistence exception

Nên tiếp tục dùng cùng EM sau một SQL constraint failure?

**Đáp án:** Không nên. Rollback/close rồi mở EM và transaction mới để xác minh.

### Bài 28. Lazy loading

Detached Project chưa initialize Tasks có được đảm bảo load ngoài EM?

**Đáp án:** Không. Cần fetch plan/DTO trong scope thích hợp.

### Bài 29. Multi-tenant

Có thể dùng `em.find` theo ID để tự bảo vệ tenant?

**Đáp án:** Không. Cần scoped authorization query/database RLS có contract phù hợp.

### Bài 30. Đồng thời

Dùng cùng EntityManager giữa hai threads để test optimistic conflict có đúng không?

**Đáp án:** Không. Dùng hai EM/transactions độc lập và barrier/sequence rõ.

---

## 45. Checklist khi hoàn thiện bộ kiểm thử

1. Test xác định rõ entity state trước và sau operation?
2. Có phân biệt persist với commit?
3. Có test generated ID nhưng không coi ID là commit proof?
4. Có kiểm `em.contains` khi cần managed semantics?
5. Có kiểm first-level cache identity bằng `assertSame`?
6. Có đọc lại từ EM/transaction mới khi cần durable DB state?
7. Có test find missing trả null?
8. Có test managed dirty checking không cần merge?
9. Có test detached mutation không auto-save?
10. Có assert merge result là managed, input không attached?
11. Có test merge khi managed instance đã tồn tại?
12. Có test merge của new entity nếu code dùng?
13. Có test stale merge/version conflict?
14. Có test persist detached là misuse?
15. Có test remove managed và detached riêng?
16. Có test remove rồi rollback?
17. Có test flush rồi rollback?
18. Có test callbacks không đồng nghĩa after-commit?
19. Có test @PrePersist/@PreUpdate/@PostLoad/@PreRemove?
20. Có test cascade PERSIST/MERGE/REMOVE theo mapping thật?
21. Có test owning side và FK integrity?
22. Có test orphanRemoval với persistent child?
23. Có test lazy access qua detached boundary?
24. Có test bulk DML bypass callbacks/dirty checking?
25. Có test SQL constraints tại flush/commit?
26. Có dùng DB production-like khi quan trọng?
27. Có kiểm Spring @DataJpaTest rollback mặc định?
28. Có commit thật khi bài test yêu cầu?
29. Có cleanup những fixtures đã commit?
30. Có tránh share EntityManager giữa threads/tests?
31. Có timeouts/barriers cho concurrency tests?
32. Có kiểm final DB state sau optimistic conflicts?
33. Có tránh khẳng định exact SQL ordering không được bảo đảm?
34. Có phân biệt test authorization với JPA lifecycle mechanics?
35. Có đặt tên tests thể hiện state–operation–expected result?

---

## 46. Quy trình lựa chọn cách kiểm chứng

~~~text
             Cần kiểm chứng một thao tác JPA
                           |
                           v
                  Chứng minh điều gì?
             +-------------+-------------+
             |             |             |
             v             v             v
          Java state     SQL flush     Committed DB state
             |             |             |
             v             v             v
          contains/     em.flush()     tx.commit()
          same/getter   + exceptions        |
                                          v
                                  Fresh EntityManager
                                          |
                                          v
                                  find/query/constraints
                                          |
                                          v
                             Race, @Version, DB-specific?
                                   /          \
                                  Có          Không
                                  |             |
                                  v             v
                            Two contexts   Test complete
                            + real DB
                            + ordering
~~~

### 46.1. Không ép tất cả vào một test

Một test cho identity map, một test cho committed readback và một test cho rollback dễ chẩn đoán hơn một test dài làm mọi thứ.

### 46.2. Mục tiêu quyết định boundary

`contains` nên assert trong context đang mở; persisted state nên assert sau commit bằng context mới; optimistic concurrency cần ít nhất hai snapshots độc lập.

---

## 47. Kết luận

1. **`persist`** xử lý new entity và làm nó managed; không thay commit.
2. **`find`** tra PK và trả managed entity hoặc null; trong cùng context có identity map.
3. **`merge`** copy state vào **managed result**; detached input vẫn detached.
4. **`remove`** yêu cầu managed entity; DELETE có thể chờ flush/commit.
5. **`flush` khác `commit`**: flush không chứng minh dữ liệu bền vững.
6. **`detach`, `clear`, `close`** làm entities rời context; setters trên detached objects không auto-save.
7. **Dirty checking** ghi persistent changes trên managed entities trong transaction, không cần merge lặp lại.
8. **Lifecycle callbacks** phải được kiểm đúng thời điểm; PostPersist/PostUpdate/PostRemove không đồng nghĩa after-commit.
9. **`@Version`** cần test hai persistence contexts và final DB state.
10. **Cascades và orphanRemoval** phụ thuộc mapping, owning side, state của child và transaction.
11. **Bulk JPQL UPDATE/DELETE** không giống per-entity managed lifecycle.
12. **Constraints** có thể fail ở flush/commit; cần test cả boundary và đọc lại.
13. **`@DataJpaTest` thường rollback cuối test**, nên clear/find trong cùng test không tự chứng minh commit.
14. **Testcontainers/DB target** giúp kiểm actual SQL, constraints và locking khác biệt với in-memory databases.
15. **Không lấy một unit mock làm bằng chứng persistence semantics**.

Một bộ test JPA đáng tin cậy trả lời được cả ba câu hỏi: **entity đã chuyển sang trạng thái nào; transaction đã thật sự hoàn tất chưa; và một persistence context độc lập thấy dữ liệu gì sau commit/rollback?** Khi ba điểm này được tách bạch, các lỗi khó như detached merge, delayed SQL, orphan removal, stale version, false-positive cache và test rollback ngầm sẽ dễ phát hiện hơn nhiều.
