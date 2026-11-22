# Giao dịch resource-local và tích hợp JTA

## 1. Vì sao cách quản lý transaction ảnh hưởng trực tiếp đến Hibernate?

Hibernate ORM ánh xạ object Java thành dữ liệu quan hệ, nhưng việc một thay đổi có trở thành dữ liệu bền vững không chỉ phụ thuộc vào `persist()`, `merge()`, `remove()` hoặc dirty checking. Các thao tác đó còn cần nằm trong **ranh giới giao dịch** (*transaction boundary*) phù hợp.

Ví dụ một hệ thống ví điện tử chuyển 500.000 đồng từ tài khoản A sang B:

```text
             Yêu cầu chuyển tiền
                      │
                      ▼
                BEGIN TRANSACTION
                      │
                 ┌────┴────┐
                 ▼         ▼
          Account A     Account B
          -500.000      +500.000
                 │         │
                 └────┬────┘
                      ▼
                  FLUSH SQL
                      │
              ┌───────┴────────┐
              │                │
           Thành công        Có lỗi
              │                │
            COMMIT          ROLLBACK
              │                │
              ▼                ▼
        Cả hai thay đổi    Không thay đổi
        được xác nhận      nào được commit
```

Nếu hai lần ghi diễn ra trong hai transaction độc lập, hệ thống có thể trừ tiền ở A nhưng thất bại khi cộng vào B. ORM không tự sửa được một ranh giới giao dịch thiết kế sai.

Trong thế giới Hibernate/Jakarta Persistence có hai cách phối hợp transaction thường gặp:

- **Resource-local transaction:** ứng dụng trực tiếp điều khiển transaction gắn với tài nguyên persistence/JDBC của một persistence unit hoặc session.
- **JTA transaction (Jakarta Transactions):** transaction manager bên ngoài điều phối ranh giới giao dịch, và Hibernate tham gia vào transaction đó. JTA có thể phối hợp nhiều tài nguyên khi cấu hình thích hợp.

Hai cách đều có thể bảo đảm atomicity cho các thay đổi trong **một database**. JTA không mặc nhiên “tốt hơn” resource-local; lựa chọn phụ thuộc tài nguyên, runtime, khả năng điều phối và trách nhiệm ownership.

## 2. Nắm rõ các tầng: Hibernate, JPA, JDBC và transaction manager

Một đường ghi phổ biến:

```text
Application service
       │
       ├── Transaction boundary
       │     ├── Resource-local: EntityTransaction / JDBC
       │     └── JTA: transaction manager / interceptor
       │
       ▼
EntityManager (JPA) hoặc Session (Hibernate)
       │
       ├── Persistence context / dirty checking
       ├── SQL generation
       └── Flush
             │
             ▼
       JDBC Connection(s)
             │
             ▼
       Relational database
```

**Persistence context** theo dõi entity, còn **transaction** quyết định đơn vị commit/rollback. Một entity có thể đang managed nhưng SQL chưa flush. Một câu SQL có thể đã flush vào transaction nhưng chưa commit. Khi transaction rollback, database hoàn tác các thay đổi chưa commit, trong khi những field của Java object có thể vẫn giữ giá trị đã sửa trong memory.

Định nghĩa những từ dễ bị nhầm:

| Thuật ngữ | Vai trò |
|---|---|
| `Session` | API gốc Hibernate, quản lý persistence context và kết nối/transaction theo cấu hình |
| `EntityManager` | API Jakarta Persistence (JPA), Hibernate có thể là provider |
| `EntityTransaction` | API điều khiển resource-local transaction của `EntityManager` |
| `UserTransaction` | API JTA cho code được phép điều khiển transaction thủ công |
| `TransactionManager` | Dịch vụ JTA nội bộ/runtime phối hợp transaction và tài nguyên |
| `DataSource` | Nguồn tạo JDBC connections; khả năng enlistment/XA tùy cấu hình |
| `XAResource` | Giao diện cho tài nguyên tham gia giao thức giao dịch phân tán XA |
| `flush()` | Đồng bộ các thay đổi pending của persistence context thành SQL trong transaction |
| `commit()` | Xác nhận transaction thành công |
| `rollback()` | Hủy các thay đổi chưa commit thuộc transaction |
| `@Transactional` | Chỉ dẫn/interceptor transaction tùy framework; cần xác định đúng package và runtime |

Một số thuật ngữ có cùng chữ “transaction” nhưng thuộc **tầng khác nhau**. Chẳng hạn Hibernate `org.hibernate.Transaction` là facade transaction của Hibernate; nó không đồng nghĩa Jakarta `jakarta.transaction.Transaction`.

## 3. So sánh resource-local và JTA

| Tiêu chí | Resource-local | JTA |
|---|---|---|
| Bên quản lý transaction | Code ứng dụng/transaction manager local | JTA transaction manager của container/runtime/framework |
| JPA `persistence.xml` | `transaction-type="RESOURCE_LOCAL"` | `transaction-type="JTA"` |
| API JPA trực tiếp | `em.getTransaction().begin()/commit()/rollback()` | Không dùng `em.getTransaction()` để điều khiển |
| API điều khiển | `EntityTransaction`, hoặc Hibernate native transaction | JTA interceptor, `UserTransaction`, framework JTA transaction manager |
| Phạm vi phổ biến | Một persistence unit/JDBC transaction | Một hoặc nhiều tài nguyên được enlist |
| Phối hợp nhiều JDBC resources | Không có transaction coordinator phân tán mặc định | Có thể hỗ trợ nếu transaction manager/resources cấu hình đúng |
| XA / two-phase commit | Không phải đặc tính mặc định | Có thể dùng khi nhiều tài nguyên XA; không tự động xuất hiện |
| Runtime thường gặp | Java SE, Spring ứng dụng một datasource | Jakarta EE server, Narayana/Atomikos hoặc runtime tích hợp JTA |
| Connection management | Hibernate/JPA quản lý JDBC connection của unit; transaction local | Transaction manager và pool quản lý enlistment/connection theo JTA |
| Sai lầm dễ gặp | Mở nhiều local transactions rồi tưởng một commit | Dùng non-XA datasource và tưởng có atomicity đa DB |

**Quy tắc chọn nhanh:** ứng dụng chỉ cần Hibernate làm việc với một database và không có yêu cầu phối hợp nhiều transactional resource thường đủ với resource-local hoặc local transaction manager của framework. JTA có ích khi hạ tầng đã có JTA hoặc một transaction phải điều phối nhiều tài nguyên hỗ trợ enlistment theo thiết kế.

## 4. Resource-local transaction là gì?

Resource-local transaction được điều khiển ở tầng local persistence resource, thông thường gắn với một JDBC connection cho đơn vị công việc. Với Jakarta Persistence:

```java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();
try {
    // find, persist, thay đổi managed entities...
    tx.commit();
} catch (RuntimeException | Error failure) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw failure;
}
```

Ở đây ứng dụng chịu trách nhiệm rõ ràng về:

1. Mở một `EntityManager` hoặc `Session` với lifecycle phù hợp.
2. Bắt đầu transaction.
3. Thực thi business operation.
4. Commit khi thành công; rollback khi lỗi.
5. Đóng resource do chính nó tạo.

`EntityTransaction` chỉ hợp lệ cho persistence unit kiểu resource-local. Nếu `EntityManager` thuộc một JTA persistence unit, gọi `getTransaction()` để begin/commit có thể ném `IllegalStateException` theo hợp đồng JPA.

### 4.1. Một transaction có thể bao gồm nhiều entity trong cùng database

“Resource-local” không có nghĩa chỉ cập nhật được một bảng hay một entity. Một transaction JDBC của một database có thể UPDATE nhiều bảng, INSERT nhiều hàng và giữ chúng nguyên tử.

Ví dụ:

```text
EntityManager (RESOURCE_LOCAL)
       │
       ├── UPDATE accounts SET balance = ...
       ├── UPDATE accounts SET balance = ...
       └── INSERT transfer_records(...)
       │
       ▼
  Cùng JDBC transaction của database
       ├── COMMIT tất cả
       └── ROLLBACK tất cả
```

Điều **không có sẵn** là một transaction coordinator thống nhất để rollback cùng lúc những kết nối *độc lập* tới hai database hoặc hai local persistence units. Việc chúng cùng ở một Java method không làm hai commit trở thành nguyên tử với nhau.

## 5. Cấu hình một persistence unit resource-local

Một ví dụ `META-INF/persistence.xml` dùng Jakarta Persistence 3.1 với Hibernate là provider:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="library-local"
                      transaction-type="RESOURCE_LOCAL">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>com.example.library.Book</class>
        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.postgresql.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:postgresql://localhost:5432/library"/>
            <property name="hibernate.hbm2ddl.auto"
                      value="validate"/>
            <property name="hibernate.show_sql"
                      value="false"/>
        </properties>
    </persistence-unit>
</persistence>
```

Các thông tin tài khoản/mật khẩu và datasource production nên được cung cấp qua hệ thống cấu hình/secret manager, không hard-code trong source. Ví dụ này minh họa thuộc tính và kiểu transaction, không phải cấu hình triển khai hoàn chỉnh. Driver, URL, connection pool, Hibernate/JPA version và schema phải tương thích với môi trường cụ thể.

Đối với resource-local, có thể cấu hình non-JTA `DataSource` thay vì trực tiếp đưa JDBC URL/driver vào persistence unit. Nếu container cung cấp datasource không tham gia JTA:

```xml
<persistence-unit name="library-local"
                  transaction-type="RESOURCE_LOCAL">
    <non-jta-data-source>java:comp/env/jdbc/LibraryLocalDS</non-jta-data-source>
</persistence-unit>
```

Tên JNDI và cách khai báo datasource phụ thuộc runtime. Không trộn một datasource đang được quản lý/enlist vào JTA với resource-local persistence unit mà không hiểu semantics và yêu cầu của provider.

## 6. Resource-local hoàn chỉnh qua EntityManager

Giả sử entity `Book` có phương thức `rename()` và mapping `@Version`:

```java
package com.example.library;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @Version
    private Long version;

    protected Book() {}

    public Book(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Tiêu đề không hợp lệ");
        }
        this.title = title;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public Long getVersion() { return version; }

    public void rename(String newTitle) {
        if (newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Tiêu đề không hợp lệ");
        }
        this.title = newTitle;
    }
}
```

Một service tự quản lý EntityManager:

```java
package com.example.library;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import java.util.Objects;

public final class BookService {
    private final EntityManagerFactory emf;

    public BookService(EntityManagerFactory emf) {
        this.emf = Objects.requireNonNull(emf);
    }

    public void renameBook(Long bookId, String newTitle) {
        EntityManager em = emf.createEntityManager();
        try {
            EntityTransaction tx = em.getTransaction();
            tx.begin();
            try {
                Book book = em.find(Book.class, bookId);
                if (book == null) {
                    throw new IllegalArgumentException(
                            "Không tìm thấy sách: " + bookId);
                }
                book.rename(newTitle);
                tx.commit();
            } catch (RuntimeException | Error failure) {
                if (tx.isActive()) {
                    try {
                        tx.rollback();
                    } catch (RuntimeException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }
                throw failure;
            }
        } finally {
            em.close();
        }
    }
}
```

Trong Java SE:

```java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

public final class Main {
    public static void main(String[] args) {
        try (EntityManagerFactory emf =
                     Persistence.createEntityManagerFactory(
                             "library-local")) {
            BookService service = new BookService(emf);
            service.renameBook(42L, "Hibernate nâng cao");
        }
    }
}
```

Ví dụ dùng Jakarta Persistence API tương thích môi trường hỗ trợ `EntityManagerFactory` trong try-with-resources; cũng có thể gọi `emf.close()` trong `finally` để tương thích cách quản lý đời sống cũ hơn. Không tạo/đóng factory cho mỗi request: `EntityManagerFactory` có chi phí khởi tạo lớn và thường sống theo ứng dụng. Ngược lại, `EntityManager` **không phải** đối tượng để chia sẻ tùy ý giữa các thread.

Điểm quan trọng là **commit và rollback do BookService tự điều khiển**. Sau khi `em.close()`, `Book` đã load không còn được EntityManager đó quản lý. Những thay đổi thực hiện trên detached Book sau đó không tự động được flush.

## 7. Resource-local với Hibernate Session gốc

Nếu dùng Hibernate native, `org.hibernate.Session` và `org.hibernate.Transaction` cung cấp transaction API:

```java
import org.hibernate.Session;
import org.hibernate.SessionFactory;
import org.hibernate.Transaction;

public void createBook(SessionFactory factory, String title) {
    try (Session session = factory.openSession()) {
        Transaction tx = session.beginTransaction();
        try {
            Book book = new Book(title);
            session.persist(book);

            tx.commit();
        } catch (RuntimeException | Error failure) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
            }
            throw failure;
        }
    }
}
```

Với JDBC/resource-local transaction coordinator, `session.beginTransaction()` điều khiển transaction của connection tương ứng. Hibernate cũng có khả năng phối hợp với JTA khi transaction coordinator được cấu hình JTA; **không suy ra** từ cú pháp `session.beginTransaction()` rằng mọi Session luôn resource-local.

### 7.1. Không chia sẻ Session qua các request hoặc thread

Một `SessionFactory` thường được chia sẻ dài hạn, nhưng `Session` không được thiết kế để chia sẻ concurrent giữa nhiều thread. Với resource-local, mô hình phổ biến là một Session và một transaction cho một đơn vị công việc:

```text
SessionFactory (application scope)
       │
       ├── Request A → Session A + Transaction A
       ├── Request B → Session B + Transaction B
       └── Background job → Session C + Transaction C
```

Không mở một transaction rồi giữ nó suốt thời gian người dùng thao tác trên màn hình; lock, connection và snapshot có thể bị giữ quá lâu.

## 8. Flush không phải commit: điều đúng với cả hai mô hình

Hibernate theo dõi những thay đổi trên managed entity, thường lập lịch SQL tại flush:

```java
Book book = em.find(Book.class, 42L);
book.rename("Tên mới");

em.flush();
// SQL UPDATE có thể đã thực thi.
// Transaction vẫn chưa commit.
```

Phân biệt:

| Hành động | Tác động |
|---|---|
| `persist(entity)` | Đưa entity mới vào vòng đời managed và lên lịch tạo row; IDENTITY có thể cần INSERT sớm để lấy khóa |
| Sửa managed entity | Thay state trong memory; dirty checking xác định cập nhật khi flush |
| `flush()` | Đẩy SQL pending xuống database trong transaction |
| `commit()` | Xác nhận transaction; provider có thể flush trước commit |
| `rollback()` | Hoàn tác SQL chưa commit trong phạm vi transaction |
| `clear()` | Bỏ managed entities khỏi persistence context; không rollback SQL đã flush |

Ví dụ:

```text
BEGIN
  Book.title = "B"
  FLUSH → UPDATE books SET title='B' ...
  ROLLBACK → database trở lại title='A'
```

Sau rollback, Java object có thể vẫn mang title `B` trong memory. Không sử dụng lại persistence context đã gặp lỗi giao dịch với kỳ vọng Hibernate tự “đảo ngược” mọi field Java. Trong workflow thông thường, rollback, đóng/bỏ session bị lỗi và dùng transaction/session mới để đọc lại dữ liệu.

Một query JPQL/HQL hoặc hành động khác có thể kích hoạt auto-flush sớm tùy flush mode. Do đó không nên tin “chưa gọi flush tường minh thì chắc chắn chưa có SQL”.

## 9. Exception, rollback và vòng đời resource

Các lỗi có thể xuất hiện khi:

- Validate command hoặc gọi domain method.
- Flush SQL: not-null, unique, foreign key hoặc check constraint.
- Acquire connection, timeout, deadlock, network lỗi.
- Optimistic locking khi version của entity không còn khớp.
- Commit transaction, kể cả khi flush trước đó không báo lỗi.

Với resource-local, application chịu trách nhiệm rollback trong phạm vi transaction đang mở. Không chỉ catch quanh `persist()`; phải bao cả `commit()` vì Hibernate có thể flush tại đó.

Một mẫu xử lý:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();
try {
    performBusinessOperation(em);
    tx.commit();
} catch (RuntimeException | Error error) {
    if (tx.isActive()) {
        try {
            tx.rollback();
        } catch (RuntimeException rollbackError) {
            error.addSuppressed(rollbackError);
        }
    }
    throw error;
}
```

Nếu `commit()` thất bại ở tầng network sau khi database đã xử lý, client đôi khi không biết chắc giao dịch đã commit hay chưa (*uncertain outcome*). Không tự động retry một command không idempotent chỉ vì thấy exception; có thể tạo giao dịch trùng. Cần dùng khóa nghiệp vụ/idempotency, đọc lại trạng thái và cơ chế đối soát theo domain.

Trong JTA, phần rollback thường do transaction manager/interceptor quyết định, nhưng ứng dụng vẫn phải báo lỗi đúng và xác định chính sách đánh dấu rollback-only. Điều này sẽ được trình bày ở phần JTA.

## 10. Ai sở hữu JDBC Connection trong resource-local?

JPA/Hibernate thường lấy connection từ một pool hoặc `DataSource` và quản lý việc sử dụng thông qua Session/EntityManager. Resource-local transaction thường commit/rollback trên JDBC resource liên quan.

Một lỗi kiến trúc:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

Book book = em.find(Book.class, 42L);
book.rename("A");

try (Connection other = dataSource.getConnection()) {
    // Nếu đây là một connection độc lập và không cùng transaction,
    // INSERT này có thể commit/rollback theo một ranh giới khác.
    insertAuditRow(other);
}

tx.commit();
```

Không suy ra mọi `Connection` lấy từ cùng pool tự động tham gia transaction resource-local đang điều khiển qua JPA. Với connection độc lập, `autoCommit` và ranh giới commit riêng có thể phá atomicity.

Nếu cần JDBC trực tiếp trong cùng đơn vị công việc, có thể:

- Dùng Hibernate `Session.doWork()/doReturningWork()` để làm việc với connection gắn với Session tương ứng, trong ranh giới transaction đang hoạt động.
- Dùng một framework transaction manager hỗ trợ cùng connection/resource trong local transaction.
- Tránh trộn nhiều persistence frameworks/connection APIs trong cùng method nếu không có cơ chế đồng bộ transaction rõ ràng.

Ví dụ Hibernate:

```java
try (Session session = factory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        Book book = session.get(Book.class, 42L);
        book.rename("A");

        session.doWork(connection -> {
            try (PreparedStatement ps = connection.prepareStatement(
                    "INSERT INTO audit_events(event_type) VALUES (?)")) {
                ps.setString(1, "BOOK_RENAMED");
                ps.executeUpdate();
            }
        });

        tx.commit();
    } catch (RuntimeException | Error error) {
        if (tx.isActive()) tx.rollback();
        throw error;
    }
}
```

Đoạn ví dụ giả định bảng `audit_events` tồn tại, có import `PreparedStatement` thích hợp và Hibernate đang dùng connection cùng transaction local. Không gọi `connection.commit()` hoặc `connection.close()` từ callback `doWork()`; Hibernate quản lý vòng đời connection.

## 11. JTA là gì trong kiến trúc Hibernate?

**JTA (Jakarta Transactions)** cung cấp API và mô hình điều phối giao dịch ở runtime. Một JTA transaction có thể được bắt đầu và kết thúc bởi container, interceptor, framework hoặc code được cấp quyền dùng `UserTransaction`.

Hibernate với JTA coordinator sẽ **tham gia** transaction được điều khiển bởi JTA transaction manager, thay vì ứng dụng điều khiển riêng từng connection bằng `EntityTransaction`.

```text
                  Application / CDI / EJB / Spring
                                │
                      Transaction interceptor
                                │
                                ▼
                        JTA Transaction Manager
                          /       │       \
                         /        │        \
                Hibernate/JPA   JDBC DS     JMS/XA
                    │             │          │
                    ▼             ▼          ▼
                SQL của ORM   SQL trực tiếp   Message
                         \      │         /
                          \     │        /
                       cùng transaction JTA
                         khi được enlist đúng
                                │
                          COMMIT/ROLLBACK
```

JTA là **giao thức phối hợp và API**, không phải một database mới hay một cache của Hibernate. Các chi tiết như transaction timeout, synchronization, enlistment, XA và recovery được quyết định bởi transaction manager và tài nguyên thực tế.

### 11.1. JTA không có nghĩa phải dùng nhiều database

JTA vẫn có thể quản lý một database duy nhất. Khi chỉ một resource được enlist, manager thường có thể commit bằng cách đơn giản hơn two-phase commit. JTA hữu ích ngay cả khi chỉ muốn thống nhất cách transaction được quản lý trong container.

### 11.2. JTA không tự tạo atomicity cho mọi thao tác

Nếu method JTA gọi:

```text
UPDATE database
HTTP POST tới cổng thanh toán
COMMIT JTA
```

thì HTTP POST thông thường **không phải** XA resource được transaction manager điều phối. Nếu HTTP đã thành công nhưng DB rollback, JTA không có khả năng tự “thu hồi” HTTP request. Cần pattern như transactional outbox, idempotency, saga hoặc compensation theo yêu cầu nghiệp vụ.

## 12. Cấu hình JTA persistence unit

Với Jakarta Persistence, khai báo JTA và datasource do runtime quản lý:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="library-jta"
                      transaction-type="JTA">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <jta-data-source>java:comp/env/jdbc/LibraryJtaDS</jta-data-source>
        <class>com.example.library.Book</class>
        <properties>
            <property name="hibernate.hbm2ddl.auto"
                      value="validate"/>
        </properties>
    </persistence-unit>
</persistence>
```

Ở đây `java:comp/env/jdbc/LibraryJtaDS` chỉ là ví dụ JNDI. Container thực tế phải cung cấp datasource đúng tên và tích hợp với transaction manager. Nếu ứng dụng chạy ngoài Jakarta EE container, cần cấu hình JTA provider và Hibernate JTA platform thích hợp.

Đặc biệt cần phân biệt:

- **JTA-aware DataSource:** pool/container có khả năng tham gia transaction JTA theo cơ chế được hỗ trợ.
- **XA DataSource:** JDBC resource hỗ trợ XA protocol để tham gia distributed two-phase commit khi cấu hình đúng.

Hai khái niệm có liên hệ nhưng không đồng nghĩa. Một JTA transaction với một non-XA datasource có thể được một số runtime hỗ trợ qua mô hình one-phase/local enlistment, nhưng không được suy ra rằng hai non-XA datasources sẽ có atomic commit phân tán.

### 12.1. Hibernate JTA coordinator và JtaPlatform

Trong Hibernate native bootstrap, coordinator phù hợp với JTA thường được cấu hình bằng thiết lập như:

```properties
hibernate.transaction.coordinator_class=jta
```

Hibernate cần biết cách truy cập transaction manager/user transaction/synchronization của runtime. Việc này được tích hợp qua một `JtaPlatform` tương ứng, có thể được container/provider tự nhận diện hoặc cần cấu hình tường minh, ví dụ bằng setting:

```properties
hibernate.transaction.jta.platform=...JtaPlatformImplementation...
```

Dòng giá trị có dấu `...` là **placeholder**, không phải class hợp lệ để copy chạy. Tên class hoặc integration cụ thể tùy Hibernate version, application server và transaction manager đang dùng (chẳng hạn Narayana hay Atomikos). Không chỉ thêm `coordinator_class=jta` rồi giả định runtime tự có một transaction manager hoạt động.

Khi tạo `EntityManagerFactory` qua container Jakarta EE, các chi tiết platform/enlistment thường do integration xử lý. Khi tự bootstrap trong Java SE, người triển khai phải bảo đảm JTA manager được khởi tạo, datasource tương thích, Hibernate tìm đúng platform và transaction boundary được tạo đúng.

## 13. Container-managed JTA: mô hình khuyên dùng trong Jakarta EE

Trong môi trường có CDI/Jakarta Transactions interceptor, ứng dụng có thể khai báo transaction tại service boundary:

```java
package com.example.library.service;

import com.example.library.Book;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.transaction.Transactional;

@ApplicationScoped
public class BookCommandService {
    @PersistenceContext(unitName = "library-jta")
    private EntityManager em;

    @Transactional(Transactional.TxType.REQUIRED)
    public void renameBook(Long bookId, String newTitle) {
        Book book = em.find(Book.class, bookId);
        if (book == null) {
            throw new IllegalArgumentException(
                    "Không tìm thấy sách");
        }
        book.rename(newTitle);
        // Không gọi em.getTransaction().commit().
        // Container/interceptor quyết định commit hoặc rollback.
    }
}
```

Đây là `jakarta.transaction.Transactional`, không phải annotation cùng tên của Spring. Cần runtime CDI/JTA phù hợp để interceptor thực sự tạo/join transaction. Nếu chỉ chạy một class Java SE với annotation mà không có interceptor, annotation không tự làm gì.

Với `TxType.REQUIRED`:

- Nếu caller đã có JTA transaction, method tham gia vào transaction đó.
- Nếu chưa có transaction, interceptor tạo transaction cho method.
- Khi method hoàn tất thành công và nó là boundary đã tạo transaction, manager commit.
- Nếu exception phù hợp với rollback rules xuất hiện, transaction có thể bị đánh dấu rollback-only và rollback.

Các quy tắc rollback của `jakarta.transaction.Transactional` có thể tùy chỉnh bằng `rollbackOn`/`dontRollbackOn`. Theo mặc định, runtime exception thường dẫn tới rollback, trong khi checked exceptions cần xem quy tắc cụ thể; đừng tự giả định mọi exception Java đều rollback giống nhau ở tất cả frameworks.

### 13.1. Không dùng EntityTransaction ở đây

Mẫu không đúng cho JTA persistence unit:

```java
@PersistenceContext(unitName = "library-jta")
EntityManager em;

@Transactional
public void wrong() {
    em.getTransaction().begin(); // Không đúng với JTA EntityManager.
    // ...
    em.getTransaction().commit();
}
```

Transaction manager của container mới là owner. Gọi `EntityManager.getTransaction()` trên JTA EntityManager không phải đường điều khiển hợp lệ theo JPA.

### 13.2. Container-managed EntityManager cũng có owner

`@PersistenceContext` thường cung cấp một proxy/EntityManager do container sở hữu. Không gọi `em.close()` sau mỗi method. Runtime quản lý thời điểm PC và resource được tạo/đóng; ứng dụng vẫn phải tránh giữ reference tới managed entity qua ranh giới không phù hợp.

## 14. JTA với UserTransaction: khi nào được điều khiển thủ công?

Một số runtime hỗ trợ **bean-managed transaction** hoặc code được phép truy cập `jakarta.transaction.UserTransaction`:

```java
import jakarta.annotation.Resource;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.PersistenceUnit;
import jakarta.transaction.UserTransaction;

@ApplicationScoped
public class ProgrammaticJtaBookService {
    @Resource
    private UserTransaction userTransaction;

    @PersistenceUnit(unitName = "library-jta")
    private EntityManagerFactory emf;

    public void createBook(String title) {
        EntityManager em = emf.createEntityManager();
        boolean began = false;
        try {
            userTransaction.begin();
            began = true;

            em.joinTransaction();
            em.persist(new Book(title));

            userTransaction.commit();
            began = false;
        } catch (Exception failure) {
            if (began) {
                try {
                    userTransaction.rollback();
                } catch (Exception rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
            }
            throw new IllegalStateException(
                    "Không hoàn tất JTA transaction", failure);
        } finally {
            em.close();
        }
    }
}
```

Ví dụ minh họa pattern programmatic và phải chạy trong **ngữ cảnh runtime cho phép dùng `UserTransaction`**. Cụ thể, không bắt đầu/commit thủ công trong method vốn đang được container quản lý transaction bằng CMT/interceptor `@Transactional` hoặc trong ngữ cảnh mà specification cấm thao tác này.

Một số lưu ý:

- `UserTransaction.begin()/commit()/rollback()` là thao tác của **JTA manager**, không phải `EntityTransaction`.
- `em.joinTransaction()` yêu cầu EntityManager được cấu hình theo JTA và có transaction phù hợp đang active; với những synchronized container-managed EntityManager, việc join thường tự động.
- Ví dụ tự tạo EntityManager nên tự đóng EntityManager, nhưng không đóng container-managed `EntityManagerFactory` được inject.
- Sau lỗi commit, trạng thái transaction có thể không còn active; rollback có thể thất bại và ngoại lệ phụ được ghi lại thay vì che nguyên nhân ban đầu.
- Một container có thể cung cấp inject bằng annotation/cơ chế khác; cần dùng API và permission đúng môi trường.

Trong service JTA bình thường, **declarative transaction** ở ranh giới ứng dụng thường dễ bảo trì hơn code programmatic này. Chỉ dùng UserTransaction khi có lý do rõ như bean-managed workflow đặc biệt.

## 15. EntityManager.joinTransaction() và enlistment

Hai việc liên quan nhưng khác nhau:

1. **Persistence context join transaction:** JPA EntityManager tham gia vào JTA transaction đang hoạt động, giúp Hibernate đồng bộ state đúng thời điểm.
2. **JDBC resource enlistment:** connection/resource của datasource được transaction manager nhận diện và gắn với transaction; với XA thì có XAResource tham gia protocol.

Không phải cứ gọi `joinTransaction()` là ứng dụng đã có XA 2PC; datasource/pool/transaction manager vẫn phải được cấu hình đúng.

Sơ đồ:

```text
JTA manager đã BEGIN
        │
        ├── EntityManager.joinTransaction() (khi cần)
        │            │
        │            ▼
        │       Hibernate Session
        │            │
        │       DataSource → Connection
        │            │
        └──────── ENLIST ─────────► JTA transaction
                                     │
                                flush SQL
                                     │
                               COMMIT/ROLLBACK
```

Với một `EntityManager` kiểu resource-local, gọi `joinTransaction()` không biến nó thành JTA EntityManager. Transaction type và coordinator phải được chọn từ khi bootstrap; không chuyển đổi một persistence unit chỉ bằng một API call.

### 15.1. Một query có thể chạy ngoài JTA transaction?

Tùy provider, loại query và environment, thao tác đọc có thể được cho phép ngoài transaction, nhưng thao tác ghi/flush cần transaction phù hợp. Một số connection/JTA datasource có chính sách bắt buộc active transaction cho mọi access; các cách nạp ngoài transaction cũng ảnh hưởng PC lifecycle và consistency.

Không nên xây business operation nhiều bước dựa trên việc các SELECT và UPDATE rời rạc “tự động nằm cùng transaction”. Hãy đặt boundary có chủ đích ở service layer.

## 16. Một JTA transaction với một tài nguyên khác gì nhiều tài nguyên?

Có ba tình huống thường bị gộp chung:

### 16.1. Một database, một connection được quản lý

```text
JTA Transaction T
    └── Database A
         ├── UPDATE table_1
         └── INSERT table_2
    → commit hoặc rollback theo một resource
```

JTA manager có thể sử dụng one-phase commit khi phù hợp, không cần distributed two-phase commit cho một XA resource duy nhất.

### 16.2. Hai XA resources

```text
JTA Transaction T
    ├── XA Database A
    └── XA Database B
          │
          ▼
    Two-phase commit (khi cần và được hỗ trợ)
       Phase 1: PREPARE
       Phase 2: COMMIT hoặc ROLLBACK
```

Transaction manager điều phối tài nguyên đã enlist, cần log/recovery và cơ chế xử lý transaction in-doubt khi crash. Khả năng atomic commit xuyên resources phụ thuộc XA driver, datasource, transaction manager và cách ứng dụng xử lý lỗi.

### 16.3. Hai local/non-XA resources đặt trong cùng method

```text
Service method
    ├── Database A qua local Connection A
    └── Database B qua local Connection B
        │
        ▼
    Không tự có distributed atomicity
```

Một số transaction manager hỗ trợ cơ chế *last resource commit optimization* hoặc best-effort one-phase cho một non-XA resource, nhưng đây có đánh đổi và rủi ro recovery. Không coi nó tương đương XA 2PC cho mọi trường hợp.

**Kết luận:** JTA là công cụ điều phối; **distributed atomicity cần tài nguyên và giao thức tương thích**, không chỉ cần một annotation transaction.

## 17. XA và two-phase commit cần hiểu đến mức nào?

XA (eXtended Architecture) cho phép nhiều tài nguyên trình bày interface giao dịch phân tán cho transaction manager. Khái niệm two-phase commit (2PC) gồm:

**Phase 1 — Prepare**

Manager yêu cầu các XA resources đã enlist chuẩn bị commit, ghi nhận rằng chúng có thể commit hoặc không.

**Phase 2 — Decision**

Nếu mọi resource báo sẵn sàng, manager quyết định commit; nếu có resource không thể chuẩn bị, manager quyết định rollback, ngoại trừ các tình huống lỗi đặc biệt có thể dẫn tới heuristic/in-doubt outcome.

```text
             Transaction Manager
              /             \
             ▼               ▼
        XA Database A    XA Database B
             │               │
         PREPARE           PREPARE
             │               │
           YES              YES
              \              /
               ▼            ▼
                 COMMIT
              /            \
             ▼              ▼
        A commits        B commits
```

XA giúp giải quyết atomic commit trong những điều kiện phù hợp, nhưng đi kèm:

- Driver/pool/resources phải hỗ trợ và được cấu hình XA đúng.
- Transaction manager cần lưu log giao dịch bền vững để recovery.
- Có thêm network round trips, lock duration và chi phí prepare/commit.
- Crash ở pha giữa cần cơ chế recovery; app có thể nhận lỗi phức tạp hoặc trạng thái không chắc chắn.
- Không phải mọi service bên ngoài (REST, email, object storage, payment gateway) đều là XA resource.

Nếu chỉ cần một database, cấu hình XA cho tất cả transaction có thể không mang lại lợi ích tương xứng. Nếu có nhiều database cần nguyên tử thật, cần đánh giá hạ tầng và chi phí vận hành, không chỉ thay mã nguồn từ `EntityTransaction` sang `@Transactional`.

## 18. Trường hợp dùng JTA với database và message broker

Một nghiệp vụ có thể vừa:

1. Persist `Order` trong DB.
2. Gửi một message `OrderCreated` qua message broker/JMS.

Với JTA và một JMS resource được cấu hình XA đúng, cả hai có thể tham gia cùng transaction:

```text
JTA T
    ├── Hibernate/JPA → INSERT orders
    └── JMS XA session → send OrderCreated
            │
            ▼
      JTA coordinator
      COMMIT hoặc ROLLBACK cả hai
```

Nhưng nếu message client không XA hoặc gửi HTTP tới Kafka/REST bằng thư viện ngoài cơ chế enlistment, gửi message có thể thành công ngay cả khi DB rollback.

Trong hệ thống microservices, nhiều team lựa chọn **transactional outbox**:

```text
Local DB transaction:
    ├── INSERT orders
    └── INSERT outbox_events
          │
          ▼
        COMMIT
          │
          ▼
 Outbox relay đọc event đã commit
          │
          ▼
      Publish đến broker
          │
          ▼
     Mark event delivered
```

Outbox không bảo đảm publish đúng một lần tuyệt đối ở mọi tầng; relay có thể retry sau lỗi, nên consumer cần idempotency/deduplication. Tuy nhiên nó tránh yêu cầu XA giữa DB và broker trong nhiều kiến trúc. JTA/2PC và outbox giải quyết cùng một vùng bài toán bằng các đánh đổi khác nhau; không có lựa chọn đúng cho mọi hệ thống.

## 19. Spring Framework và transaction local

Trong Spring, `@Transactional` thường cho phép định nghĩa transaction declaratively mà không gọi `EntityTransaction` thủ công:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {
    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void rename(Long id, String title) {
        Book book = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Không tìm thấy"));
        book.rename(title);
        // Spring transaction manager commit/rollback.
    }
}
```

Ví dụ giả định `BookRepository` là Spring Data JPA repository của `Book`. Annotation đang dùng là `org.springframework.transaction.annotation.Transactional`, **không phải** Jakarta Transactional.

Nếu ứng dụng Spring Boot dùng một database và Hibernate/JPA, thường có một local transaction manager phù hợp với JPA, chẳng hạn `JpaTransactionManager`. Nó điều khiển transaction của EntityManager/JDBC resource trong bối cảnh Spring. Code nghiệp vụ không nên vừa được Spring quản lý transaction vừa tự gọi `em.getTransaction().begin()`.

### 19.1. JpaTransactionManager và DataSourceTransactionManager không giống nhau

`JpaTransactionManager` chuyên tích hợp JPA EntityManager transaction, có thể phối hợp JDBC access tới cùng DataSource trong điều kiện cấu hình đúng. `DataSourceTransactionManager` quản lý JDBC local transaction trên một DataSource. Dùng transaction manager không phù hợp hoặc hai manager độc lập cho hai đường ghi không tự làm chúng nằm trong cùng physical transaction.

Trong ứng dụng kết hợp JPA với JDBC, hãy xác nhận:

- JPA và JDBC dùng cùng transaction-managed DataSource/connection được framework bind đúng.
- Không tự gọi `Connection.commit()/setAutoCommit(true)` từ business code.
- Chỉ có một transaction boundary chính xác cho unit of work đó.
- Những thư viện truy cập DB trực tiếp nhận connection theo cơ chế framework, không mở connection độc lập ngoài transaction.

## 20. Spring tích hợp JTA: trách nhiệm chuyển sang JTA manager

Spring có `JtaTransactionManager` để kết nối annotation `@Transactional` với JTA transaction manager của runtime. Khi một ứng dụng đã sử dụng JTA, service có thể tiếp tục viết theo mô hình:

```java
@Service
public class TransferService {
    @PersistenceContext(unitName = "payment-jta")
    private EntityManager em;

    @Transactional
    public void transfer(...) {
        // Thao tác JPA qua EntityManager đã tham gia JTA transaction.
    }
}
```

Nhưng trong trường hợp này `@Transactional` của Spring phải được cấu hình để dùng **JTA-capable PlatformTransactionManager**, và EntityManagerFactory/datasource phải được cấu hình JTA đồng bộ với manager đó.

Không đủ nếu chỉ:

```java
@Transactional
public void transfer(...) { ... }
```

rồi suy ra “đã có XA transaction đa DB”. Cần kiểm tra type của persistence unit, JTA manager, DataSource, XA driver và việc tài nguyên được enlist.

### 20.1. Tránh có hai transaction managers cùng tưởng mình sở hữu một thao tác

Một ứng dụng có `JpaTransactionManager` local cho database A và `JtaTransactionManager` cho hệ thống khác có thể định nghĩa nhiều transaction managers. Nếu một method không chỉ rõ manager phù hợp, framework có thể chọn manager mặc định không như người lập trình kỳ vọng.

Nếu một use case cần atomicity qua tài nguyên JTA, toàn bộ đường ghi liên quan phải tham gia **cùng JTA transaction**. Không giải quyết được bằng cách gắn hai annotation transaction lên cùng method và mong hai manager tự phối hợp.

### 20.2. Spring @Transactional và Jakarta @Transactional

| Annotation | Namespace | Chủ yếu được xử lý bởi |
|---|---|---|
| Spring `@Transactional` | `org.springframework.transaction.annotation.Transactional` | Spring transaction AOP/interceptor |
| Jakarta `@Transactional` | `jakarta.transaction.Transactional` | Jakarta Transactions/CDI interceptor; Spring có thể nhận diện một số cấu hình |

Hai annotation có các thuộc tính và semantics không hoàn toàn giống nhau, đặc biệt `propagation`, isolation, rollback rules và runtime activation. Khi đọc code, cần kiểm tra **import**, không chỉ thấy tên `@Transactional`.

## 21. Propagation: REQUIRED, REQUIRES_NEW và ranh giới thực tế

Một operation có thể gọi operation khác:

```text
CheckoutService.placeOrder()
    ├── OrderService.persistOrder()
    └── AuditService.recordEvent()
```

Propagation quyết định method con dùng chung transaction với caller hay có ranh giới khác.

| Ý nghĩa | Jakarta TxType | Spring propagation gần tương ứng |
|---|---|---|
| Tham gia transaction hiện có, nếu chưa có thì tạo | `REQUIRED` | `REQUIRED` |
| Luôn chạy trong transaction mới, suspend transaction cũ khi có | `REQUIRES_NEW` | `REQUIRES_NEW` |
| Chỉ chạy khi đã có transaction | `MANDATORY` | `MANDATORY` |
| Không tạo transaction; tham gia nếu có | `SUPPORTS` | `SUPPORTS` |
| Chạy ngoài transaction, suspend nếu có | `NOT_SUPPORTED` | `NOT_SUPPORTED` |
| Không cho chạy nếu đang có transaction | `NEVER` | `NEVER` |

Jakarta `TxType` còn có những quy tắc interceptor/exception riêng; Spring bổ sung những lựa chọn khác như `NESTED` với điều kiện hỗ trợ.

### 21.1. REQUIRES_NEW có thể phá “tất cả hoặc không có gì”

Nếu `recordEvent()` chạy `REQUIRES_NEW` rồi commit thành công, nhưng `placeOrder()` sau đó rollback, audit event vẫn có thể tồn tại dù Order chưa được commit:

```text
Outer T1: placeOrder()
     │
     ├── suspend T1
     ├── T2: recordEvent() → COMMIT
     └── resume T1 → ROLLBACK

Kết quả: T2 đã commit độc lập.
```

Đây có thể là chủ đích với audit ghi lỗi độc lập, nhưng là sai nếu event phải khớp chính xác với trạng thái Order đã commit. Không dùng `REQUIRES_NEW` chỉ để “chắc chắn ghi log” mà bỏ qua consistency của nghiệp vụ.

### 21.2. Nested transaction không mặc nhiên tồn tại trong JTA

JTA thông thường không cung cấp nested transactions theo nghĩa savepoint lồng như JDBC local. Spring `Propagation.NESTED` phụ thuộc transaction manager và khả năng JDBC savepoint; không nên xem nó tương đương `REQUIRES_NEW` hoặc bảo đảm hoạt động với JTA.

Với resource-local JDBC, savepoint có thể hữu ích trong một số quy trình nhưng Hibernate persistence context có thể không tự quay về state trước savepoint nếu JDBC rollback-to-savepoint được gọi ngoài ORM. Nếu cần partial rollback, phải đồng bộ state ORM và xác định semantics rõ.

### 21.3. Self-invocation và proxy

Trong Spring AOP proxy-based transactions, method `@Transactional` được một method khác trong cùng object gọi bằng `this.someMethod()` có thể **không đi qua proxy** để kích hoạt propagation mới. Thiết kế service boundary và injection rõ ràng để annotation thực sự có hiệu lực.

## 22. Rollback-only và ngoại lệ trong JTA

Trong JTA, một transaction có thể được đánh dấu **rollback-only**. Khi đó ứng dụng không thể làm transaction commit thành công chỉ bằng cách bắt exception và tiếp tục xử lý.

Ví dụ:

```text
JTA Transaction T
   ├── Hibernate flush → constraint violation
   ├── Transaction được đánh dấu rollback-only
   ├── Application catch exception, tiếp tục tính toán
   └── Kết thúc method → COMMIT bị từ chối/rollback
```

Nếu code:

```java
try {
    repository.save(invalidEntity);
} catch (RuntimeException ignored) {
    // Tiếp tục như thể transaction vẫn khỏe.
}
```

thì không chắc chắn transaction còn có thể commit. Trong JTA và các framework transaction managers, lỗi persistence nghiêm trọng có thể làm transaction không còn hợp lệ.

### 22.1. Chỉ định rollback khi nghiệp vụ phát hiện lỗi

Trong môi trường container hỗ trợ:

```java
import jakarta.annotation.Resource;
import jakarta.transaction.TransactionSynchronizationRegistry;

@Resource
private TransactionSynchronizationRegistry registry;

public void rejectCurrentTransaction() {
    registry.setRollbackOnly();
}
```

Đây là ví dụ dùng API JTA để đánh dấu rollback-only trong ngữ cảnh thích hợp; không phải một cách xử lý exception chung có thể copy vào Java SE mà không có JTA runtime. Với CDI `@Transactional` cũng có thể cấu hình rollback rules trên annotation, và ở Spring thường sử dụng exception/TransactionStatus theo cơ chế transaction manager.

Nếu cần thông báo lỗi nghiệp vụ mà **không** rollback, phải thiết kế điều kiện đó ngay trong transaction contract, tránh catch lỗi DB rồi cố phục hồi persistence context đang ở trạng thái lỗi.

## 23. Timeout, isolation và locking không được JTA “tự sửa”

Giao dịch tốt cần tính đến đồng thời, nhưng chọn resource-local hay JTA **không tự quyết định isolation level**. Isolation phổ biến của database:

- `READ COMMITTED`
- `REPEATABLE READ`
- `SERIALIZABLE`

Cách triển khai, phantom reads và serialization failure phụ thuộc database. Hibernate có thể sử dụng optimistic locking qua `@Version` hoặc pessimistic locking qua `LockModeType.PESSIMISTIC_WRITE`.

Ví dụ update entity được bảo vệ bằng optimistic version:

```java
@Version
private Long version;
```

SQL logic có thể tương tự:

```sql
UPDATE books
SET title = :new_title,
    version = :new_version
WHERE id = :id
  AND version = :old_version;
```

Nếu transaction khác đã cập nhật row, affected row count có thể bằng 0 và Hibernate báo optimistic lock conflict. Điều này đúng cả khi transaction được quản lý local hay JTA.

### 23.1. JTA UserTransaction timeout

JTA cung cấp API thiết lập timeout cho những transaction mới:

```java
userTransaction.setTransactionTimeout(30); // giây
userTransaction.begin();
```

Hành vi hiệu lực, giới hạn và rollback khi timeout phụ thuộc transaction manager/container. Không gọi `setTransactionTimeout()` trong một method container-managed đã được interceptor mở transaction mà cho rằng nó thay đổi timeout hiện tại.

### 23.2. Transaction timeout khác query timeout

| Loại timeout | Ý nghĩa |
|---|---|
| Transaction timeout | Giới hạn thời gian transaction theo manager/runtime |
| JDBC statement/query timeout | Giới hạn thời gian một SQL statement/query |
| Connection acquisition timeout | Giới hạn chờ lấy connection từ pool |
| Database lock timeout | Giới hạn thời gian chờ lock |
| HTTP client timeout | Giới hạn call tới service ngoài |

Chỉ đặt transaction timeout không bảo đảm mọi loại network/driver request sẽ bị hủy tức thì. Cần cấu hình nhiều lớp phù hợp và định nghĩa cách retry, đặc biệt với transaction outcome không chắc chắn.

### 23.3. Isolation trong JTA do ai quản lý?

Trong local JDBC transaction, connection/database có thể được cấu hình isolation theo datasource/driver và transaction manager. Trong JTA, isolation thường được cấu hình ở datasource/container/transaction integration; `UserTransaction` API không có phương thức chuẩn đặt isolation riêng cho mỗi transaction như một số Spring local transaction managers.

Spring `@Transactional(isolation=...)` không được mọi JTA manager hỗ trợ theo cùng cách. Nếu yêu cầu isolation cụ thể là bắt buộc, hãy xác nhận khả năng provider và database thay vì chỉ ghi annotation.

## 24. Một bài toán chuyển tiền trong một database: resource-local là đủ

Để thấy không cần JTA chỉ vì transaction chạm nhiều row, xét bảng:

```sql
CREATE TABLE wallet_accounts (
    id BIGINT PRIMARY KEY,
    balance NUMERIC(19, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT ck_balance_nonnegative CHECK (balance >= 0)
);

CREATE TABLE wallet_transfers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    transfer_key VARCHAR(80) NOT NULL UNIQUE,
    from_account_id BIGINT NOT NULL REFERENCES wallet_accounts(id),
    to_account_id BIGINT NOT NULL REFERENCES wallet_accounts(id),
    amount NUMERIC(19, 2) NOT NULL CHECK (amount > 0)
);
```

Entity account:

```java
@Entity
@Table(name = "wallet_accounts")
public class WalletAccount {
    @Id
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal balance;

    @Version
    private Long version;

    protected WalletAccount() {}

    public BigDecimal getBalance() { return balance; }

    public void debit(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0
                || balance.compareTo(amount) < 0) {
            throw new IllegalArgumentException(
                    "Số dư không đủ hoặc số tiền không hợp lệ");
        }
        balance = balance.subtract(amount);
    }

    public void credit(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Số tiền không hợp lệ");
        }
        balance = balance.add(amount);
    }
}
```

Ví dụ dùng `BigDecimal` và các annotation Jakarta Persistence cần import trong project. Service resource-local:

```java
public void transfer(EntityManagerFactory emf,
                     Long fromId,
                     Long toId,
                     BigDecimal amount) {
    if (fromId.equals(toId)) {
        throw new IllegalArgumentException(
                "Không thể chuyển đến cùng tài khoản");
    }

    EntityManager em = emf.createEntityManager();
    try {
        EntityTransaction tx = em.getTransaction();
        tx.begin();
        try {
            WalletAccount from = em.find(
                    WalletAccount.class, fromId,
                    LockModeType.PESSIMISTIC_WRITE);
            WalletAccount to = em.find(
                    WalletAccount.class, toId,
                    LockModeType.PESSIMISTIC_WRITE);

            if (from == null || to == null) {
                throw new IllegalArgumentException(
                        "Tài khoản không tồn tại");
            }

            from.debit(amount);
            to.credit(amount);

            tx.commit();
        } catch (RuntimeException | Error failure) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
            }
            throw failure;
        }
    } finally {
        em.close();
    }
}
```

Đây là ví dụ nguyên tử cho **hai account trong cùng database**. Với `PESSIMISTIC_WRITE`, transaction giữ lock cho các row theo semantics database và ngăn một số xung đột. Để giảm nguy cơ deadlock khi nhiều giao dịch chuyển theo hai hướng, thực tế nên khóa account theo thứ tự ID ổn định; còn cần idempotency record, audit, retry policy và xử lý uncertain commit outcome trước khi coi ví dụ là giải pháp ví điện tử production.

Sự cần thiết của transaction được quyết định bởi cùng một phép chuyển tiền; không nhất thiết cần JTA cho nhiều hàng trên một database.

## 25. Khi hai database độc lập cùng tham gia nghiệp vụ

Giả sử một dịch vụ vừa cập nhật database `billing_db` vừa cập nhật `loyalty_db`:

```text
Local transaction A: UPDATE billing_db → COMMIT
Local transaction B: UPDATE loyalty_db → FAIL
```

Nếu hai transaction local độc lập, không có coordinator để tự rollback commit A. Việc gom code trong một method, một thread hoặc một request không tạo atomicity.

Với một JTA manager và hai XA datasources được cấu hình đúng:

```text
JTA transaction
    ├── JPA Persistence Unit billing-jta → XA BillingDS
    └── JPA Persistence Unit loyalty-jta → XA LoyaltyDS
          │
          ▼
    Transaction manager phối hợp prepare/commit
```

Điều kiện cần:

1. Cả hai persistence units tham gia cùng active JTA transaction.
2. Mỗi DataSource/resource được enlist đúng.
3. XA drivers và pool được cấu hình cho distributed transaction.
4. Transaction manager có logging và recovery phù hợp.
5. Application không lén mở connection local/autocommit bên ngoài giao dịch.

Nếu không đáp ứng một trong các điều kiện, kết quả có thể không có bảo đảm nguyên tử như kỳ vọng. Cân nhắc chi phí XA với phương án eventual consistency, saga hoặc outbox tùy nghiệp vụ.

## 26. Đọc dữ liệu, read-only hint và transaction boundary

Một query chỉ đọc vẫn nên có transaction khi yêu cầu consistency hoặc runtime yêu cầu connection/session được quản lý rõ:

```java
@Transactional(readOnly = true)
public BookSummary loadSummary(Long id) {
    return em.createQuery(
            "select new com.example.library.BookSummary(" +
            "b.id, b.title) from Book b where b.id = :id",
            BookSummary.class)
            .setParameter("id", id)
            .getSingleResult();
}
```

Ở đây ví dụ là Spring `@Transactional`; `BookSummary` là record DTO có constructor `(Long, String)`. Với Jakarta interceptor thuần, cách cấu hình đọc và annotation khác; `jakarta.transaction.Transactional` không có thuộc tính `readOnly` như Spring.

**Read-only hint không phải authorization hay database security boundary.** Tùy transaction manager, nó có thể ảnh hưởng flush mode hoặc JDBC connection read-only; nhưng một lệnh native SQL/DML tường minh vẫn có thể được phép ở một số môi trường.

Tương tự, khi Hibernate nạp entity theo read-only flag, scalar dirty checking có thể được bỏ qua, nhưng thay đổi collection/cascade vẫn có thể ghi. Nếu thực sự không được ghi, cần tách đường read/write và cấu hình quyền database phù hợp.

### 26.1. Open Session in View không thay transaction đúng chỗ

Một số ứng dụng giữ EntityManager/Session mở đến tầng web view để cho phép lazy loading. Điều này không đồng nghĩa toàn bộ request có một transaction nhất quán. Truy cập lazy ngoài transaction nghiệp vụ có thể phát thêm SQL SELECT không được kiểm soát và che khuất N+1.

Ưu tiên service transaction boundary rõ ràng, query đúng fetch plan/DTO cho API. Không kéo dài transaction qua thời gian chờ client chỉ để giữ entity managed.

## 27. Thread, async và transaction context

Trong những runtime JTA, transaction thường gắn với execution context của thread và cơ chế propagation của container. Một method đang trong JTA transaction không mặc nhiên truyền transaction sang arbitrary thread:

```java
@Transactional
public void process() {
    CompletableFuture.runAsync(() -> {
        // Không mặc nhiên tham gia JTA transaction của thread gọi.
        // EntityManager cũng không an toàn để chia sẻ concurrent.
    });
}
```

Nếu cần async processing, hãy dùng executor/context propagation do container/framework hỗ trợ hoặc thiết kế message/job với transaction riêng. Không chia sẻ `EntityManager` hoặc Hibernate `Session` đồng thời giữa nhiều thread.

Điều này cũng áp dụng cho resource-local: mỗi Session/EntityManager quản lý state gắn với unit of work, không được dùng làm shared mutable singleton.

### 27.1. Scheduler và background jobs

Một background job xử lý 1 triệu record thường nên có transaction theo chunk để giới hạn thời gian giữ lock và persistence context. Nếu dùng JTA, timeout và transaction propagation của scheduler phải được cấu hình; nếu dùng local, code hoặc framework phải mở/commit transaction cho từng chunk.

Tính nguyên tử qua nhiều chunk không tự xuất hiện với bất kỳ loại transaction nào. Cần checkpoint, idempotency và retry policy.

## 28. TransactionSynchronization và hành động sau commit

Trong một số workflow, ứng dụng chỉ muốn thực hiện công việc **sau khi transaction thành công**, ví dụ invalidating cache hoặc gửi notification. JTA cung cấp cơ chế synchronization để runtime callback trước/sau completion.

Khái quát:

```text
JTA Transaction T
   ├── ORM work / flush
   ├── beforeCompletion callbacks
   ├── COMMIT hoặc ROLLBACK
   └── afterCompletion(status)
```

Hibernate và transaction manager sử dụng synchronization để phối hợp flush/lifecycle. Application có thể đăng ký callback qua API/runtime phù hợp, nhưng cần lưu ý:

- Callback `afterCompletion` không nên giả định có thể rollback một commit đã hoàn tất.
- Lỗi process sau commit không làm database transaction đã commit tự rollback.
- Gửi HTTP trong callback không tạo exactly-once delivery.
- Nếu phải đảm bảo event không mất sau crash, transactional outbox thường bền vững hơn một callback chỉ nằm trong memory.

Không tự tạo synchronization để thay thế một transaction boundary đúng; nó chỉ cung cấp hook lifecycle ở tầng transaction.

## 29. Testing resource-local và JTA

### 29.1. Kiểm thử resource-local

Một integration test có thể:

1. Tạo EntityManagerFactory với database test.
2. Mở EntityManager, begin transaction.
3. Persist/update entities.
4. Flush/commit hoặc rollback.
5. Đóng EntityManager và nạp lại bằng EntityManager mới để xác nhận dữ liệu bền vững.

Nếu chỉ kiểm tra state của managed entity **trước khi clear**, test có thể trả đúng giá trị trong memory dù SQL không được commit hoặc mapping sai. Khi cần quan sát database state, commit và nạp lại ở persistence context mới theo transaction phù hợp.

### 29.2. Kiểm thử JTA

Đối với JTA, cần integration environment có transaction manager thực sự. Test chỉ chạy Java SE không có JTA provider không thể chứng minh:

- Datasource đã được enlist đúng.
- Two-phase commit/recovery hoạt động.
- Transaction interceptor thật sự tạo boundary.
- Rollback-only và timeout được provider áp dụng như production.

Test có thể mô phỏng exception trong service và xác nhận rollback DB. Với nhiều XA resources, cần test fail giữa chuẩn bị/commit và quy trình recovery nếu đó là yêu cầu production; unit test mock không thay thế bài test này.

### 29.3. @Transactional trong test có thể che thiếu sót

Nếu toàn bộ test method tự mở transaction và rollback ở cuối, service thiếu annotation transaction đôi khi vẫn chạy được vì nó tham gia transaction do test tạo. Nên có test thực thi service ở boundary tương đương runtime thực tế để không bỏ sót transaction configuration.

## 30. Lỗi thường gặp khi tích hợp Hibernate và transaction manager

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `EntityManager.getTransaction()` ném IllegalStateException | Persistence unit là JTA | Dùng JTA transaction manager/interceptor |
| Method `@Transactional` không commit gì | Annotation không được interceptor kích hoạt hoặc transaction manager sai | Kiểm tra runtime, import, proxy, boundary |
| SQL chạy nhưng commit không cùng transaction với JDBC khác | Lấy connection độc lập ngoài managed resource | Dùng datasource/resource enlistment đúng |
| Hai database không rollback cùng lúc | Hai local transactions, không có XA coordinator | Chọn XA/JTA đúng hoặc saga/outbox |
| Rollback-only dù application đã catch lỗi | Persistence failure đã đánh dấu transaction không còn commit được | Rollback và tạo transaction mới |
| `LazyInitializationException` sau service | Session/PC đóng trước khi truy cập lazy data | Query DTO/fetch plan trong service transaction |
| Dữ liệu không cập nhật dù setter chạy | Detached entity hoặc read-only/flush mode | Kiểm tra PC, mapping và transaction boundary |
| `TransactionRequiredException` | Ghi/flush khi không có transaction hợp lệ | Tạo/join transaction trước DML |
| Connection pool cạn | Transaction dài hoặc session/connection leak | Giới hạn transaction, đóng resource, theo dõi pool |
| Transaction timeout | Query chậm, lock wait, call ngoài quá lâu | Index, transaction ngắn, timeout/lock policy |
| Deadlock khi update nhiều account | Lock theo thứ tự không nhất quán | Sắp xếp khóa trước update, retry có kiểm soát |
| DataSource trong JTA nhưng vẫn autocommit độc lập | Pool/driver không enlist đúng | Cấu hình transaction-aware datasource và XA khi cần |
| Exception tại commit gây retry trùng | Outcome không chắc chắn, command không idempotent | Business key, idempotency key, reconcile |
| Hai `@Transactional` lồng mà inner commit riêng | `REQUIRES_NEW` thay vì REQUIRED | Xác định propagation theo invariant |
| Inner annotation không có tác dụng trong Spring | Self-invocation không qua proxy | Tách service/proxy boundary phù hợp |
| JTA transaction không chạy trong async thread | Không propagation qua arbitrary executor | Dùng managed context hoặc transaction riêng |
| Cấu hình JTA provider rồi vẫn dùng local PU | Transaction type/coordinator mismatch | Đồng bộ persistence unit, manager và DS |
| XA recovery lỗi sau crash | Log/recovery ID/resource setup chưa đúng | Cấu hình durable recovery, kiểm thử failure |
| Ràng buộc DB báo lỗi lúc commit, không phải lúc persist | Hibernate flush trì hoãn SQL | Bắt/rollback ở boundary commit |
| `clear()` sau flush nhưng before commit | PC mất state nhưng SQL chưa xác nhận | Hiểu flush/commit/rollback khác nhau |

## 31. Cách chọn mô hình theo nhu cầu

| Bối cảnh | Phương án thường phù hợp | Lưu ý |
|---|---|---|
| CLI Java SE dùng Hibernate với một PostgreSQL | Resource-local `EntityTransaction` hoặc Hibernate `Transaction` | Quản lý begin/commit/rollback/close đúng |
| Spring Boot REST API với một JPA DataSource | Local transaction qua Spring `JpaTransactionManager` và `@Transactional` | Không tự begin JPA transaction trong service |
| Jakarta EE server với `@PersistenceContext` | JTA container-managed | Để container quản lý transaction và EntityManager lifecycle |
| Hai SQL resources cần atomic commit và đều XA-capable | JTA + XA datasources + transaction recovery | Chấp nhận chi phí 2PC, kiểm thử failure |
| DB và HTTP payment gateway | Local/JTA cho DB, saga/outbox/idempotency cho external call | HTTP không tự enlist vào JTA |
| Event publish cần không mất khi DB commit | Transactional outbox | Relay/consumer idempotent |
| Batch nhiều triệu rows | Transaction theo chunk, flush/clear/streaming phù hợp | Xác định partial success/retry |
| Báo cáo chỉ đọc | Read-only transaction/DTO projection | Không nhầm hint với quyền DB |
| Microservices với database mỗi service | Thường local transactions + asynchronous consistency | XA xuyên nhiều service thường khó vận hành |

“Dùng JTA cho mọi thứ để an toàn hơn” không phải tối ưu mặc định. Nếu tài nguyên không XA, hệ thống vẫn phải thiết kế consistency; nếu chỉ một database, local transaction có thể đơn giản, dễ vận hành hơn.

## 32. Checklist cấu hình resource-local

Trước khi triển khai một unit of work resource-local, cần xác định:

1. Persistence unit có `transaction-type="RESOURCE_LOCAL"` hoặc cấu hình tương đương không?
2. JDBC datasource/connection pool có phù hợp với local transaction coordinator không?
3. Mỗi business operation có boundary begin/commit/rollback rõ ràng không?
4. Exception trong business logic, flush và commit có được rollback và không bị nuốt không?
5. EntityManager/Session được đóng theo owner lifecycle, không chia sẻ concurrent giữa các thread không?
6. Có tác vụ JDBC trực tiếp nào đang dùng connection **khác** ngoài transaction không?
7. Có `@Version`, lock hoặc constraint để chống race condition theo domain không?
8. Có công việc HTTP/message nào bị hiểu nhầm là “cùng transaction” với DB không?
9. Có idempotency policy nếu retry sau timeout/network failure không?
10. Có log correlation, metrics về transaction duration, rollback rate và pool usage không?

Đây là các câu hỏi kiến trúc, không phải lý do để luôn mở transaction lớn nhất có thể. Transaction càng dài có thể càng giữ nhiều lock và resource; đơn vị công việc nên vừa đủ để bảo vệ invariant.

## 33. Checklist cấu hình JTA

Với một ứng dụng JTA:

1. Runtime có JTA transaction manager hoạt động và được cấu hình recovery khi cần không?
2. Persistence unit được khai báo `JTA` và Hibernate tìm được JtaPlatform/coordinator thích hợp không?
3. Datasource dùng với Hibernate có transaction-aware enlistment phù hợp không?
4. Nếu cần distributed 2PC, **mọi tài nguyên liên quan** có XA capability và được cấu hình đúng không?
5. Application có dùng một transaction boundary thống nhất thay vì tự begin local EntityTransaction không?
6. `@Transactional` thực sự được interceptor/framework kích hoạt chứ không chỉ là annotation trên class không được quản lý không?
7. Có code gọi `UserTransaction` trong ngữ cảnh CMT không cho phép không?
8. Có `EntityManager.joinTransaction()` khi dùng application-managed JTA EntityManager cần tham gia transaction không?
9. Có những JDBC connections hoặc message sends không được enlist nhưng vẫn bị coi là cùng transaction không?
10. Có kiểm soát propagation `REQUIRED/REQUIRES_NEW`, rollback-only, timeout và isolation đúng không?
11. Có kiểm thử crash recovery/heuristic outcomes đối với XA quan trọng không?
12. Có idempotency, correlation ID, transaction logs và quy trình đối soát khi outcome không chắc chắn không?

## 34. Sơ đồ quyết định kiến trúc

```text
                    Một nghiệp vụ cần ghi dữ liệu
                               │
                    Cần atomicity trên tài nguyên nào?
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
           Một database                Nhiều tài nguyên
                 │                           │
                 ▼                           ▼
      Resource-local hoặc          Tất cả có tham gia
      framework local transaction   cùng JTA/XA được không?
                 │                    ┌──────┴──────┐
                 │                   CÓ            KHÔNG
                 │                    │              │
                 │                    ▼              ▼
                 │               JTA + XA      Local transaction
                 │               và recovery  + outbox / saga /
                 │                    │         compensation
                 │                    │              │
                 └───────────┬────────┴──────────────┘
                             ▼
                    Thiết kế transaction boundary
                    + rollback/timeout/locking
                    + idempotency/retry policy
                             │
                             ▼
                  Hibernate Session/EntityManager
                     tham gia transaction đúng
                             │
                             ▼
                     FLUSH → COMMIT/ROLLBACK
```

## 35. Tóm lược những khác biệt không được nhầm

**Resource-local** là cách application hoặc framework local điều khiển transaction của persistence resource/JDBC. Nó có thể cập nhật nhiều bảng trong một database một cách nguyên tử. Với JPA, dùng `EntityTransaction`; với Hibernate native, dùng `Session`/Hibernate `Transaction` theo coordinator được cấu hình.

**JTA** là cơ chế transaction manager của runtime điều phối transaction mà Hibernate tham gia. Với JTA persistence unit, không tự gọi `EntityManager.getTransaction()` để commit. Sử dụng container/framework interceptor hoặc `UserTransaction` trong những ngữ cảnh được phép.

**XA/2PC** không tự xuất hiện chỉ vì ứng dụng bật JTA hoặc có `@Transactional`. Cần nhiều tài nguyên hỗ trợ giao thức, enlistment đúng, transaction manager và recovery. HTTP calls và đa số APIs bên ngoài không tự trở thành transactional resource.

**Flush** đồng bộ SQL nhưng không commit. **Persistence context** quản lý state entity nhưng không thay thế transaction. **Rollback** hoàn tác thay đổi database chưa commit, không tự đưa mọi object Java về giá trị cũ.

Vì vậy, khi tích hợp Hibernate, hãy bắt đầu từ **ranh giới nghiệp vụ và phạm vi nguyên tử thực sự cần**, rồi chọn resource-local hay JTA cho đúng hạ tầng. Một transaction được thiết kế chặt chẽ, có ownership, rollback và consistency rõ ràng quan trọng hơn việc chọn API nghe có vẻ “mạnh” hơn.
