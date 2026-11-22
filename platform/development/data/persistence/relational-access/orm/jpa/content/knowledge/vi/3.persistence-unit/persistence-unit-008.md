# Lựa chọn kiểu giao dịch RESOURCE_LOCAL hoặc JTA trong JPA Persistence Unit

## 1. Vai trò của transaction type trong Persistence Unit

Trong **Jakarta Persistence (JPA)**, một *persistence unit* mô tả tập entity, cấu hình provider ORM, nguồn kết nối cơ sở dữ liệu và những thuộc tính dùng để tạo hoặc cung cấp `EntityManager`. Khi khai báo persistence unit trong `META-INF/persistence.xml`, thuộc tính **transaction-type** chỉ định cách các `EntityManager` của unit đó phối hợp với giao dịch:

- **RESOURCE_LOCAL**: giao dịch do ứng dụng hoặc một framework quản lý bằng cơ chế giao dịch cục bộ trên tài nguyên cơ sở dữ liệu của persistence unit. Với JPA thuần, ứng dụng dùng `EntityTransaction` để `begin()`, `commit()`, `rollback()`.
- **JTA**: `EntityManager` tham gia vào giao dịch do **Jakarta Transactions (JTA)** điều phối. Ranh giới giao dịch được tạo bởi container, interceptor, transaction manager hoặc API JTA bên ngoài `EntityManager`.

Lựa chọn này là lựa chọn **cơ chế quản lý giao dịch**; không phải lựa chọn engine cơ sở dữ liệu, không phải cấu hình mức cô lập, cũng không tự quyết định một thao tác có dùng `INSERT`, `UPDATE` hay `DELETE` hay không.

Ví dụ, hai ứng dụng cùng dùng PostgreSQL, Hibernate và cùng entity `Book` có thể cấu hình khác nhau:

| Ứng dụng | Transaction type phù hợp | Ai điều khiển giao dịch? |
|---|---|---|
| Chương trình Java SE chạy một tác vụ nhập sách | RESOURCE_LOCAL | Mã ứng dụng qua `EntityTransaction` |
| Ứng dụng web Jakarta EE dùng transaction của application server | JTA | Container/JTA transaction manager |
| Ứng dụng Spring dùng một database và `JpaTransactionManager` | Thường RESOURCE_LOCAL | Spring qua transaction manager, không phải mã tự gọi `EntityTransaction` |
| Dịch vụ phối hợp hai nguồn dữ liệu XA trong cùng một giao dịch nguyên tử | JTA, nếu hạ tầng hỗ trợ | JTA manager phối hợp các tài nguyên tham gia |

> **Điểm phân biệt cốt lõi:** transaction type của JPA nói cách `EntityManager` tham gia giao dịch. Cách nghiệp vụ khai báo `@Transactional`, cách connection được cấp, khả năng phối hợp nhiều tài nguyên và mức độ cô lập của DB là những yếu tố liên quan nhưng cần cấu hình, xem xét riêng.

## 2. Đặt transaction type ở đâu?

Một persistence unit thường được khai báo trong file:

~~~text
src/main/resources/
└── META-INF/
    └── persistence.xml
~~~

Trong ứng dụng đóng gói WAR/JAR theo Jakarta EE, vị trí đóng gói có thể khác theo cấu trúc module, nhưng file phải được provider/container phát hiện đúng theo quy tắc triển khai. Thuộc tính `transaction-type` nằm trên phần tử `persistence-unit`:

~~~xml
<persistence-unit name="libraryPu" transaction-type="RESOURCE_LOCAL">
    ...
</persistence-unit>
~~~

hoặc:

~~~xml
<persistence-unit name="libraryPu" transaction-type="JTA">
    ...
</persistence-unit>
~~~

Giá trị hợp lệ là **`RESOURCE_LOCAL`** và **`JTA`**. Đây là một phần trong cấu hình *persistence unit*, vì vậy toàn bộ `EntityManager` tạo hoặc được cung cấp từ unit này sử dụng loại giao dịch được cấu hình cho unit đó.

Theo mô hình triển khai của JPA, khi không khai báo `transaction-type`, kiểu mặc định phụ thuộc môi trường: trong môi trường Jakarta EE container, mặc định là JTA; trong môi trường Java SE, mặc định là RESOURCE_LOCAL. **Khai báo tường minh** giúp code dễ đọc và giảm hiểu nhầm khi chuyển giữa môi trường.

## 3. RESOURCE_LOCAL hoạt động như thế nào?

### 3.1. Cơ chế

Với RESOURCE_LOCAL, một `EntityManager` thực hiện công việc JPA trong phạm vi transaction cục bộ gắn với tài nguyên dữ liệu của nó. Ở JPA thuần, `EntityManager.getTransaction()` trả về một `EntityTransaction` dùng để:

1. Bắt đầu giao dịch bằng `begin()`.
2. Đọc, thêm, sửa hoặc xóa các entity trong persistence context.
3. Đồng bộ thay đổi xuống cơ sở dữ liệu khi `flush()` hoặc trong quá trình commit.
4. Gọi `commit()` nếu thành công; gọi `rollback()` nếu thất bại.

~~~mermaid
sequenceDiagram
    participant App as Mã ứng dụng
    participant EM as EntityManager
    participant DB as Cơ sở dữ liệu
    App->>EM: getTransaction().begin()
    App->>EM: persist(entity)
    App->>EM: sửa managed entity
    App->>EM: getTransaction().commit()
    EM->>DB: INSERT/UPDATE khi đồng bộ
    EM->>DB: COMMIT
    DB-->>App: Transaction hoàn tất
~~~

Provider có thể thực thi SQL sớm hơn `commit()` trong một số trường hợp, nhưng dữ liệu chỉ được xác nhận khi giao dịch commit thành công. RESOURCE_LOCAL vẫn dựa vào khả năng **ACID của database transaction**; tên “local” không có nghĩa là thay đổi được ghi thiếu an toàn hay giao dịch chỉ tồn tại trong bộ nhớ Java.

### 3.2. Ví dụ persistence.xml cho Java SE

Ví dụ dưới đây sử dụng namespace của Jakarta Persistence 3.1 và JDBC driver PostgreSQL. `Book` là entity minh họa; ứng dụng cần thêm JPA provider và JDBC driver tương thích vào dependencies.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence
        https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
    version="3.1">

    <persistence-unit name="libraryLocalPu"
                      transaction-type="RESOURCE_LOCAL">
        <class>com.example.library.Book</class>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.postgresql.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:postgresql://localhost:5432/library"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="library_app"/>
            <property name="jakarta.persistence.jdbc.password"
                      value="example_only"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

Các thuộc tính `jakarta.persistence.jdbc.*` cho provider biết cách kết nối. Mật khẩu ở đây chỉ là giá trị minh họa: ứng dụng thực tế nên lấy thông tin nhạy cảm từ cơ chế cấu hình bí mật, pool hoặc DataSource được quản lý, thay vì ghi mật khẩu thật trong file nguồn.

Nếu môi trường đã cung cấp **DataSource không được quản lý bởi JTA**, có thể dùng `<non-jta-data-source>` thay cho các thuộc tính JDBC trực tiếp:

~~~xml
<persistence-unit name="libraryLocalPu"
                  transaction-type="RESOURCE_LOCAL">
    <non-jta-data-source>java:comp/env/jdbc/LocalLibraryDS</non-jta-data-source>
    <class>com.example.library.Book</class>
</persistence-unit>
~~~

Tên JNDI phải phù hợp với hạ tầng triển khai; đây là ví dụ một nguồn dữ liệu do môi trường cấu hình.

### 3.3. Entity dùng trong các ví dụ

~~~java
package com.example.library;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String title;

    protected Book() {
        // Constructor cho JPA
    }

    public Book(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void rename(String newTitle) {
        this.title = newTitle;
    }
}
~~~

Entity này có thể dùng ở cả hai kiểu giao dịch. **Không cần đổi annotation của entity chỉ vì đổi transaction type**; điều cần điều chỉnh chủ yếu là cách cấu hình kết nối và điều khiển transaction.

### 3.4. Quản lý RESOURCE_LOCAL bằng EntityTransaction

~~~java
import com.example.library.Book;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

public final class CreateBookApp {
    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("libraryLocalPu");
        try {
            createBook(emf, "Effective Java");
        } finally {
            emf.close();
        }
    }

    static void createBook(EntityManagerFactory emf, String title) {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            Book book = new Book(title);
            em.persist(book);

            tx.commit();
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
~~~

Ở đây:

- `EntityManagerFactory` được tạo cho persistence unit tên `libraryLocalPu`. Factory thường được dùng lại trong nhiều lượt xử lý, còn `EntityManager` có vòng đời ngắn theo từng công việc.
- `tx.begin()` mở transaction cục bộ; các entity do `em` quản lý được theo dõi trong persistence context.
- `em.persist(book)` đưa entity mới vào context. SQL `INSERT` có thể được gửi khi flush hoặc sớm hơn tùy cơ chế sinh khóa, provider.
- `tx.commit()` kết thúc transaction nếu thành công. Khi có lỗi, nhánh catch rollback giao dịch còn active; finally đóng `EntityManager`.

**Giới hạn quan trọng:** `EntityTransaction` điều khiển transaction cục bộ của entity manager này. Tạo hai `EntityManager` với hai kết nối độc lập rồi gọi `commit()` lần lượt **không tạo ra một giao dịch nguyên tử trên hai tài nguyên**. Nếu commit của kết nối thứ hai thất bại sau khi kết nối thứ nhất đã commit, JPA không tự đảo ngược commit thứ nhất.

### 3.5. RESOURCE_LOCAL trong ứng dụng có framework

Không phải ứng dụng RESOURCE_LOCAL nào cũng phải tự viết `tx.begin()` và `tx.commit()`. Ví dụ, Spring có thể quản lý transaction của một persistence unit resource-local bằng `JpaTransactionManager`, cho phép tầng nghiệp vụ dùng annotation giao dịch của Spring:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void renameBook(long id, String newTitle) {
        Book book = em.find(Book.class, id);
        if (book == null) {
            throw new IllegalArgumentException("Book not found");
        }
        book.rename(newTitle);
    }
}
~~~

Đây là **mẫu dùng Spring**, không phải ví dụ container-managed `@PersistenceContext` theo Jakarta EE. Cách tạo persistence unit và transaction manager trong Spring phải nhất quán với cấu hình ứng dụng. Annotation `org.springframework.transaction.annotation.Transactional` **không mặc nhiên biến transaction thành JTA**: Spring có thể dùng `JpaTransactionManager` cho giao dịch cục bộ hoặc `JtaTransactionManager` nếu đã cấu hình JTA.

## 4. JTA hoạt động như thế nào?

### 4.1. Cơ chế

**Jakarta Transactions** cung cấp cơ chế điều phối transaction nằm bên ngoài `EntityManager`. Với JTA, JPA provider cần tích hợp với JTA manager để connection và các thao tác SQL tham gia transaction hiện hành. Trong một ứng dụng Jakarta EE, transaction có thể được mở, xác nhận hoặc rollback bởi container; mã nghiệp vụ thường chỉ khai báo ranh giới giao dịch.

~~~mermaid
flowchart TD
    A[Phương thức nghiệp vụ] --> B[JTA transaction manager]
    B --> C[EntityManager JTA]
    C --> D[Persistence context]
    D --> E[DataSource tham gia JTA]
    E --> F[(Database)]
    B --> G[Nguồn dữ liệu / tài nguyên khác nếu được cấu hình]
~~~

Ví dụ một transaction dịch vụ có thể thực hiện các thao tác JPA cùng một transaction JTA hiện có. Khi cần phối hợp **nhiều tài nguyên độc lập**, JTA manager có thể dùng các cơ chế như XA/2-phase commit với tài nguyên tương thích để điều phối việc commit. Tuy nhiên:

- Đặt `transaction-type="JTA"` **không tự tạo** JTA transaction manager.
- JTA **không mặc nhiên bảo đảm** mỗi nguồn dữ liệu hoặc message broker đều hỗ trợ giao dịch phân tán XA.
- Có JTA không đồng nghĩa sẽ luôn thực hiện 2-phase commit; điều đó phụ thuộc số lượng, loại tài nguyên và transaction manager.
- Một ứng dụng dùng **duy nhất một DB** vẫn có thể chọn JTA để phù hợp kiến trúc container; JTA không chỉ dành cho nhiều database.

### 4.2. Ví dụ persistence.xml dùng JTA DataSource

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/persistence
        https://jakarta.ee/xml/ns/persistence/persistence_3_1.xsd"
    version="3.1">

    <persistence-unit name="libraryJtaPu"
                      transaction-type="JTA">
        <jta-data-source>java:app/jdbc/LibraryDS</jta-data-source>
        <class>com.example.library.Book</class>
    </persistence-unit>
</persistence>
~~~

`<jta-data-source>` trỏ tới DataSource mà môi trường quản lý theo quy tắc tích hợp JTA. Việc khai báo, pool kết nối, thông tin xác thực và khả năng XA của DataSource được cấu hình tại application server hoặc nền tảng triển khai. Đường dẫn `java:app/jdbc/LibraryDS` là ví dụ; ứng dụng thực tế phải dùng JNDI name tồn tại trong môi trường của mình.

Không nên chỉ thay giá trị `RESOURCE_LOCAL` thành `JTA` trong XML rồi giữ nguyên toàn bộ mã thao tác với `EntityTransaction`. Hai kiểu này có cơ chế điều khiển khác nhau; khi chuyển phải xem lại transaction manager, DataSource và API giao dịch.

### 4.3. Giao dịch khai báo trong Jakarta EE

Trong ứng dụng có CDI/transaction interceptor hỗ trợ Jakarta Transactions:

~~~java
package com.example.library;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.transaction.Transactional;

@ApplicationScoped
public class LibraryService {

    @PersistenceContext(unitName = "libraryJtaPu")
    private EntityManager em;

    @Transactional(Transactional.TxType.REQUIRED)
    public void createAndRename(String original, String updated) {
        Book book = new Book(original);
        em.persist(book);
        book.rename(updated);
    }
}
~~~

Khi lời gọi đi qua interceptor giao dịch của môi trường Jakarta EE:

1. Nếu chưa có JTA transaction, `REQUIRED` tạo transaction mới; nếu đã có transaction phù hợp, phương thức tham gia transaction đó.
2. Persistence context được dùng trong transaction; `persist()` và việc đổi title được JPA theo dõi.
3. Khi phương thức hoàn tất theo quy tắc interceptor, JTA manager quyết định commit. Khi xuất hiện lỗi làm transaction bị đánh dấu rollback, thay đổi không được xác nhận.

Trong mã trên không gọi `em.getTransaction()`: đối với **JTA EntityManager**, phương thức này không phải API thích hợp để điều khiển transaction và có thể ném `IllegalStateException`.

`@Transactional` trong ví dụ là `jakarta.transaction.Transactional`, khác với annotation cùng tên của Spring. Nó chỉ phát huy hiệu lực khi phương thức được gọi trong môi trường có interceptor quản lý; tự tạo đối tượng bằng `new LibraryService()` trong Java SE thuần sẽ không tự sinh JTA transaction.

### 4.4. Kiểm soát JTA bằng UserTransaction

Trong những môi trường Jakarta EE cho phép **bean-managed transaction**, API `jakarta.transaction.UserTransaction` cung cấp `begin()`, `commit()`, `rollback()` cho JTA. Đây là API của JTA, không phải `jakarta.persistence.EntityTransaction`.

~~~java
import jakarta.annotation.Resource;
import jakarta.transaction.UserTransaction;

public class ExampleBeanManagedTransaction {

    @Resource
    private UserTransaction userTransaction;

    public void doWork() throws Exception {
        userTransaction.begin();
        try {
            // Gọi các thao tác JPA đã tham gia transaction JTA.
            performJpaOperations();
            userTransaction.commit();
        } catch (Exception ex) {
            // Ví dụ minh họa: mã thực tế cần xét trạng thái transaction
            // trước rollback và xử lý lỗi rollback riêng.
            try {
                userTransaction.rollback();
            } catch (Exception rollbackFailure) {
                ex.addSuppressed(rollbackFailure);
            }
            throw ex;
        }
    }

    private void performJpaOperations() {
        // Sử dụng một JTA EntityManager đã được cung cấp hợp lệ.
    }
}
~~~

Việc inject `UserTransaction`, quyền điều khiển giao dịch và tham gia transaction phụ thuộc loại component/container; ví dụ chỉ minh họa ranh giới API. Trong dự án dịch vụ thông thường, khai báo giao dịch bằng interceptor/container thường dễ duy trì hơn so với tự kiểm soát tất cả nhánh commit/rollback.

### 4.5. Khi nào phải dùng joinTransaction()?

Một **JTA EntityManager được đồng bộ bình thường** có thể tự tham gia JTA transaction đang hoạt động theo quy tắc của môi trường/provider. Những tình huống nâng cao như **unsynchronized persistence context** hoặc một số `EntityManager` do ứng dụng tự quản lý có thể cần gọi `em.joinTransaction()` để tham gia transaction hiện tại:

~~~java
// Chỉ dùng khi có JTA transaction đang hoạt động
// và mô hình EntityManager yêu cầu tham gia tường minh.
em.joinTransaction();
~~~

Không gọi `joinTransaction()` như cách thay thế cho việc **tạo transaction**. Phương thức này không bắt đầu giao dịch, và sẽ không biến một RESOURCE_LOCAL `EntityManager` thành JTA. Với container-managed synchronized persistence context thông thường, không nên thêm lệnh join chỉ theo thói quen.

## 5. So sánh RESOURCE_LOCAL và JTA

| Tiêu chí | RESOURCE_LOCAL | JTA |
|---|---|---|
| Đơn vị quản lý | Giao dịch cục bộ gắn với tài nguyên persistence unit | Giao dịch do JTA transaction manager điều phối |
| API JPA trực tiếp | `em.getTransaction()`, `EntityTransaction` | `EntityManager` tham gia JTA, không điều khiển bằng `EntityTransaction` |
| Cách mở và kết thúc transaction | Mã ứng dụng hoặc framework local transaction manager | Container, JTA interceptor, JTA manager hoặc `UserTransaction` |
| Cấu hình DataSource điển hình | JDBC properties hoặc `<non-jta-data-source>` | `<jta-data-source>` |
| Môi trường thường dùng | Java SE, batch, microservice một DB, Spring với local manager | Jakarta EE container, ứng dụng cần JTA coordination |
| Nhiều tài nguyên độc lập cùng commit nguyên tử | Không được bảo đảm bằng nhiều `EntityTransaction` riêng | Có thể đạt được khi JTA manager và các tài nguyên hỗ trợ coordination thích hợp |
| Độ phức tạp vận hành | Thường thấp hơn nếu chỉ một DB | Cần hạ tầng/transaction manager và cấu hình enlistment |
| Cơ chế dirty checking, persistence context | Có | Có |
| Hỗ trợ rollback các thao tác trong transaction DB | Có | Có |
| Có tự giải quyết xung đột đồng thời? | Không | Không |

**Không nên dùng bảng theo kiểu “JTA mạnh hơn nên luôn tốt hơn”.** Cả hai đều sử dụng giao dịch của DB để bảo đảm nguyên tử trong phạm vi mà chúng quản lý. Khác biệt quyết định nằm ở **ai điều phối transaction và có phải gom nhiều tài nguyên vào cùng một đơn vị nguyên tử hay không**.

## 6. Chọn kiểu nào cho từng tình huống?

### Trường hợp A: Java SE/CLI nhập dữ liệu vào một cơ sở dữ liệu

Một chương trình command line đọc CSV, kiểm tra dữ liệu và chèn từng lô vào một DB duy nhất. Ứng dụng tự kiểm soát thời điểm bắt đầu, xác nhận và rollback.

**Chọn RESOURCE_LOCAL**. Cấu hình gọn, chỉ cần provider và driver/DataSource; dùng `EntityTransaction` hoặc framework quản lý transaction cục bộ.

### Trường hợp B: Ứng dụng Jakarta EE với container quản lý JPA

Một ứng dụng WAR có CDI/EJB, `@PersistenceContext`, DataSource JNDI và ranh giới transaction do container cung cấp.

**Chọn JTA**. Đây là mô hình tích hợp tự nhiên để persistence context tham gia transaction do container điều phối; mã nghiệp vụ có thể dùng `jakarta.transaction.Transactional` hoặc cơ chế transaction của EJB.

### Trường hợp C: Spring Boot chỉ truy cập một relational DB

Service dùng Spring Data JPA và annotation `org.springframework.transaction.annotation.Transactional`. Nếu dùng `JpaTransactionManager` và không yêu cầu transaction phân tán, **RESOURCE_LOCAL thường phù hợp**. Lúc này Spring vẫn mở/commit/rollback transaction; lập trình viên không cần tự gọi `EntityTransaction`.

Nếu dự án đã tích hợp JTA manager theo yêu cầu hạ tầng, có thể chọn JTA. **Không suy ra transaction type chỉ từ việc thấy annotation `@Transactional`**; phải kiểm tra transaction manager thực tế và persistence unit.

### Trường hợp D: Cần ghi vào hai cơ sở dữ liệu độc lập

Một nghiệp vụ yêu cầu cập nhật DB A và DB B sao cho không có tình huống chỉ một bên commit. Hai lần RESOURCE_LOCAL commit nối tiếp không bảo đảm điều này.

**Cân nhắc JTA với các XA DataSource và transaction manager hỗ trợ coordination thích hợp**. Cũng cần kiểm tra khả năng phục hồi sau sự cố, timeout, log giao dịch và hạn chế của driver/DB. Nếu các tài nguyên không hỗ trợ transaction phân tán, chọn cách thiết kế nghiệp vụ như saga, outbox hoặc cơ chế bù trừ thay vì nghĩ rằng chỉ bật JTA đã đủ.

### Trường hợp E: Vừa ghi DB, vừa gửi message

Ghi order vào DB rồi phát sự kiện lên message broker là bài toán nhất quán giữa hai tài nguyên. Có thể chọn JTA/XA nếu DB, broker, driver, transaction manager và hạ tầng đều hỗ trợ; nhiều hệ thống hiện đại lại chọn **transactional outbox**: ghi order và event vào cùng DB transaction, sau đó một tiến trình khác phát event đáng tin cậy.

**Không tự động chọn JTA chỉ vì có message broker.** Quyết định dựa vào bảo đảm thực tế của tài nguyên, khả năng chịu lỗi và yêu cầu vận hành.

### Sơ đồ quyết định

~~~mermaid
flowchart TD
    A[Ứng dụng cần quản lý giao dịch JPA] --> B{Đang ở container với JTA transaction manager?}
    B -- Có --> C{Muốn EntityManager tham gia transaction của container?}
    C -- Có --> J[JTA]
    C -- Không --> D[Xem lại nhu cầu quản lý cục bộ và cấu hình runtime]
    B -- Không --> E{Một DB / một tài nguyên giao dịch?}
    E -- Có --> L[RESOURCE_LOCAL thường phù hợp]
    E -- Không --> F{Cần atomic commit qua nhiều tài nguyên?}
    F -- Có --> G{JTA manager và tài nguyên XA hỗ trợ?}
    G -- Có --> J
    G -- Không --> H[Thiết kế outbox/saga/bù trừ hoặc thay đổi hạ tầng]
    F -- Không --> I[Thiết kế giao dịch riêng cho từng tài nguyên]
~~~

Sơ đồ mang tính định hướng. Nếu kiến trúc đang dùng một framework transaction manager, hãy xác định những khả năng mà framework và môi trường thực tế hỗ trợ trước khi quyết định.

## 7. Transaction type liên hệ thế nào với Persistence Context?

Cả hai kiểu đều dùng persistence context để quản lý entity, nhưng **vòng đời context và ranh giới transaction không phải lúc nào cũng trùng nhau**:

| Khái niệm | Chức năng | Lưu ý |
|---|---|---|
| Persistence Unit | Bộ cấu hình JPA: mapping, provider, dữ liệu, transaction type | Một ứng dụng có thể chứa nhiều persistence unit |
| EntityManager | API truy cập entity và context của unit | Vòng đời do ứng dụng/framework/container quản lý |
| Persistence Context | Quản lý entity identity, trạng thái managed và dirty checking | Có thể tồn tại ngắn hoặc dài tùy phạm vi |
| Transaction | Ranh giới commit/rollback thay đổi DB | RESOURCE_LOCAL hoặc JTA là cách điều khiển/tham gia |

Ví dụ với RESOURCE_LOCAL:

~~~java
EntityManager em = emf.createEntityManager();
try {
    em.getTransaction().begin();
    Book book = em.find(Book.class, 1L);
    if (book != null) {
        book.rename("Tên mới");
    }
    em.getTransaction().commit();
} finally {
    em.close();
}
~~~

Nếu `book` tồn tại, JPA có thể phát hiện thay đổi của entity managed và tạo `UPDATE` khi đồng bộ. Với JTA, cơ chế dirty checking tương tự, chỉ khác cách thiết lập transaction. Do đó việc đổi transaction type **không khiến một entity detached tự động trở thành managed**, không làm `merge()` đổi bản chất, cũng không khiến `flush()` trở thành `commit()`.

### 7.1. Transaction-scoped và extended context không phải transaction type

Trong container Jakarta EE, persistence context có thể được quản lý theo phạm vi transaction:

~~~java
@PersistenceContext(
    unitName = "libraryJtaPu",
    type = PersistenceContextType.TRANSACTION
)
private EntityManager em;
~~~

Hoặc ở những component hỗ trợ, có thể dùng **extended persistence context** qua nhiều transaction:

~~~java
@PersistenceContext(
    unitName = "libraryJtaPu",
    type = PersistenceContextType.EXTENDED
)
private EntityManager em;
~~~

Đây là cấu hình **phạm vi persistence context**, không phải giá trị `transaction-type` trong XML. Một extended context giữ entity managed qua nhiều transaction, trong khi transaction vẫn được bắt đầu và kết thúc theo cơ chế JTA thích hợp. Extended context cần dùng đúng loại component/vòng đời được container hỗ trợ.

### 7.2. Flush và commit

Đối với cả RESOURCE_LOCAL và JTA:

- **`flush()`** đồng bộ trạng thái đang chờ trong persistence context xuống cơ sở dữ liệu trong transaction phù hợp; có thể phát sinh SQL hoặc lỗi ràng buộc.
- **`commit`** xác nhận transaction nếu thành công. Với RESOURCE_LOCAL thuần, ứng dụng gọi `EntityTransaction.commit()`. Với JTA, transaction manager thực hiện commit.
- **`rollback`** hủy thay đổi thuộc transaction ở DB. Entity Java còn tham chiếu sau rollback có thể chứa trạng thái đã thay đổi trong bộ nhớ, không nên coi nó là bản phản ánh DB đúng cho lượt công việc mới.

Giả sử đã gửi `UPDATE` do `flush()`, sau đó transaction rollback: thay đổi DB vẫn bị rollback. **`flush()` không thay thế commit** trong bất kỳ transaction type nào.

## 8. Hiểu đúng về JTA, XA và giao dịch phân tán

Ba tên này thường xuất hiện cùng nhau nhưng không đồng nghĩa:

**JTA (Jakarta Transactions)** là API và mô hình điều phối giao dịch Java. Một JTA transaction có thể điều phối một hoặc nhiều tài nguyên được enlist đúng cách.

**XA** là giao thức/khả năng của tài nguyên, ví dụ XA DataSource, để tham gia điều phối commit phân tán. Nếu hệ thống muốn atomic commit hai DB độc lập thông qua JTA thì thường phải có tài nguyên XA, transaction manager hỗ trợ và các cấu hình liên quan.

**Two-phase commit (2PC)** là cơ chế phối hợp các bên tham gia transaction: giai đoạn chuẩn bị, sau đó quyết định commit hoặc rollback. 2PC có chi phí, đòi hỏi khả năng phục hồi, logging và có thể gặp hạn chế về tính sẵn sàng khi xảy ra sự cố.

| Nhận định | Đúng hay sai? | Giải thích |
|---|---|---|
| Dùng JTA luôn yêu cầu hai cơ sở dữ liệu | Sai | Một DataSource JTA vẫn là cách triển khai bình thường |
| Dùng JTA đồng nghĩa có XA | Sai | XA còn tùy driver, DataSource, manager và cấu hình |
| Có hai RESOURCE_LOCAL EntityManager thì gọi hai commit là nguyên tử | Sai | Commit thứ nhất có thể thành công còn commit thứ hai thất bại |
| JTA có thể gom nhiều tài nguyên thành một transaction | Có điều kiện | Các tài nguyên và hạ tầng phải hỗ trợ coordination đúng cách |
| Dùng JTA sẽ giải quyết mọi vấn đề concurrent update | Sai | Vẫn cần isolation, khóa/version và ràng buộc nghiệp vụ |

Khi có nhiều hệ thống độc lập (DB, queue, dịch vụ HTTP), quyết định còn phụ thuộc tính tương thích của tài nguyên. Một lời gọi HTTP đến dịch vụ khác thông thường không tự động tham gia transaction JTA của dịch vụ gọi.

## 9. Giao dịch và xử lý lỗi

### 9.1. Lỗi không có transaction

Nhiều thao tác thay đổi dữ liệu yêu cầu transaction đang hoạt động. Nếu cố gọi `flush()`, `remove()` hoặc bulk update trong môi trường yêu cầu transaction nhưng chưa mở transaction phù hợp, provider có thể ném `TransactionRequiredException`.

Ví dụ RESOURCE_LOCAL sai:

~~~java
EntityManager em = emf.createEntityManager();
try {
    em.persist(new Book("Java"));
    em.flush(); // Chưa begin transaction: có thể gây TransactionRequiredException.
} finally {
    em.close();
}
~~~

Khắc phục: mở `EntityTransaction` và kết thúc bằng commit/rollback, hoặc sử dụng framework transaction manager đúng với cấu hình persistence unit.

### 9.2. Gọi EntityTransaction trên JTA EntityManager

~~~java
// Sai đối với một JTA EntityManager:
EntityTransaction tx = jtaEntityManager.getTransaction();
tx.begin();
~~~

Khi ứng dụng đã chọn JTA, ranh giới giao dịch phải được mở bằng cơ chế JTA phù hợp, ví dụ `@Transactional` được container xử lý hoặc API `UserTransaction` trong môi trường cho phép.

### 9.3. Không có JTA manager thực sự

Đổi XML sang JTA nhưng chạy Java SE không được cung cấp transaction manager, platform integration và JTA DataSource có thể dẫn đến lỗi khởi tạo provider, không thể join transaction hoặc không có giao dịch đang hoạt động. **JTA là sự tích hợp hạ tầng**, không chỉ một giá trị enum. Trong một ứng dụng Java SE tự quản lý, RESOURCE_LOCAL thường dễ thiết lập hơn.

### 9.4. Rollback khi lỗi trong một Unit of Work

Với RESOURCE_LOCAL, code cần `rollback()` nếu transaction còn hoạt động. Với container/JTA declarative transaction, việc rollback phụ thuộc quy tắc interceptor và kiểu ngoại lệ:

- `jakarta.transaction.Transactional` mặc định có những quy tắc khác nhau cho runtime exception và checked exception; có thể điều chỉnh bằng `rollbackOn`/`dontRollbackOn`.
- Spring `@Transactional` cũng có các quy tắc rollback riêng, chẳng hạn cấu hình `rollbackFor`.
- Một lỗi phát sinh sau khi JPA gửi SQL nhưng trước commit có thể khiến toàn bộ transaction bị rollback.

Vì vậy cần kiểm tra **loại annotation**, transaction manager và chính sách rollback đang dùng. Không nên giả định bất kỳ ngoại lệ Java nào cũng tự động rollback trong mọi framework.

### 9.5. Bối cảnh đa luồng

`EntityManager` không được thiết kế để chia sẻ đồng thời giữa nhiều thread. Với RESOURCE_LOCAL, thông thường mỗi lượt xử lý lấy `EntityManager` riêng. Với container-managed JTA, injection và phạm vi context do container giải quyết. Không nên đưa một `EntityManager` đang dùng vào nhiều task bất đồng bộ rồi kỳ vọng các task dùng chung transaction an toàn.

## 10. Hai Persistence Unit trong cùng ứng dụng

Về mặt cấu hình, một ứng dụng có thể có nhiều persistence unit, mỗi unit mang tên và transaction type khác nhau:

~~~xml
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit name="reportingLocalPu"
                      transaction-type="RESOURCE_LOCAL">
        <non-jta-data-source>java:comp/env/jdbc/ReportDS</non-jta-data-source>
        <class>com.example.reporting.Report</class>
    </persistence-unit>

    <persistence-unit name="ordersJtaPu"
                      transaction-type="JTA">
        <jta-data-source>java:app/jdbc/OrdersDS</jta-data-source>
        <class>com.example.orders.Order</class>
    </persistence-unit>
</persistence>
~~~

Đây là ví dụ cấu trúc: mỗi DataSource/JNDI name phải được cấu hình trong môi trường tương ứng, và hai nhóm entity/transaction manager phải được gắn đúng persistence unit. Không nên hiểu “cùng file persistence.xml” nghĩa là hai unit tự động chia sẻ một transaction.

Trong ứng dụng JTA, nếu một phương thức đang chạy trong transaction JTA mà truy cập persistence unit RESOURCE_LOCAL độc lập, thao tác RESOURCE_LOCAL **không tự động** gia nhập transaction JTA. Muốn yêu cầu nguyên tử trên các tài nguyên độc lập, cần thiết kế cơ chế coordination tương ứng, thay vì đặt hai persistence unit cạnh nhau.

## 11. Những câu hỏi cần trả lời trước khi cấu hình

Trước khi chọn `RESOURCE_LOCAL` hoặc `JTA`, hãy xác định:

1. **Môi trường chạy**: Java SE tự khởi tạo `EntityManagerFactory`, Spring, hay Jakarta EE application server? Có JTA transaction manager thực sự không?
2. **Ranh giới use case**: Một nghiệp vụ phải commit/rollback một DB, hay cần nhiều nguồn dữ liệu/tài nguyên cùng commit nguyên tử?
3. **Nguồn kết nối**: JDBC URL/driver, non-JTA DataSource hay JTA DataSource? Ai quản lý connection pool và enlistment?
4. **API tạo transaction**: Gọi `EntityTransaction`, dùng transaction manager của Spring, CDI/JTA interceptor hay `UserTransaction`?
5. **Khả năng của hạ tầng**: Nếu cần XA, DB driver, message broker, DataSource và transaction manager có hỗ trợ XA đúng cách không?
6. **Chiến lược lỗi**: Nếu một phần nghiệp vụ thất bại, rollback có bao phủ toàn bộ thay đổi mong muốn không? Có cần retry, version check, outbox hoặc bù trừ không?

Có thể ghi lại quyết định kiến trúc dưới dạng:

~~~text
Persistence Unit: libraryLocalPu
Transaction type: RESOURCE_LOCAL
Runtime: Java SE
Transaction manager: EntityTransaction
Database resources per unit of work: 1 PostgreSQL connection
Boundary: một lần nhập lô dữ liệu
Rollback: rollback toàn bộ lô nếu có lỗi
~~~

hoặc:

~~~text
Persistence Unit: ordersJtaPu
Transaction type: JTA
Runtime: Jakarta EE application server
Transaction manager: container JTA
Datasource: JTA-managed OrdersDS
Boundary: phương thức nghiệp vụ @Transactional
Rollback: theo chính sách Jakarta Transactions và lỗi nghiệp vụ
~~~

Việc mô tả rõ những yếu tố này giúp nhóm phát triển hiểu ai chịu trách nhiệm transaction và tránh hai tầng cùng cố gắng bắt đầu hoặc commit một giao dịch.

## 12. Bài tập áp dụng

### Bài tập 1: Chọn loại transaction

Cho bốn tình huống:

1. Một tool Java SE di chuyển dữ liệu từ file vào một bảng của một database.
2. Một ứng dụng Jakarta EE đã có DataSource JNDI và transaction interceptor của container.
3. Một service chỉ dùng một PostgreSQL database với Spring `JpaTransactionManager`.
4. Một service bắt buộc commit atomically trên hai database độc lập có XA driver và JTA manager hỗ trợ.

**Gợi ý trả lời:** (1) RESOURCE_LOCAL; (2) JTA; (3) thường RESOURCE_LOCAL; (4) JTA/XA với cấu hình coordination đúng. Tình huống (4) vẫn cần đánh giá vận hành và lựa chọn thay thế nếu phân tán không phù hợp.

### Bài tập 2: Nhận diện API sai

~~~java
// persistence.xml đặt transaction-type="JTA".
EntityManager em = ...;
em.getTransaction().begin();
em.persist(new Book("JPA"));
em.getTransaction().commit();
~~~

**Vấn đề:** `EntityTransaction` không phải API điều khiển JTA EntityManager. Cần tạo transaction qua interceptor/container hoặc `UserTransaction` trong môi trường hỗ trợ.

### Bài tập 3: Phân biệt flush và commit

~~~java
tx.begin();
Book book = em.find(Book.class, 10L);
book.rename("Đổi tiêu đề");
em.flush();
tx.rollback();
~~~

**Kết quả mong đợi:** Dù `UPDATE` có thể đã gửi xuống DB khi flush, rollback của cùng transaction làm thay đổi không được commit. Tên trong đối tượng Java có thể vẫn là tên mới cho đến khi đối tượng bị bỏ/được tải lại; không nên tái sử dụng entity đó như nguồn dữ liệu xác thực sau rollback.

### Bài tập 4: Hai commit không nguyên tử

~~~java
txA.begin();
txB.begin();

// Ghi dữ liệu vào hai database khác nhau.
txA.commit();
txB.commit(); // Thất bại tại đây.
~~~

**Câu hỏi:** Vì sao dùng RESOURCE_LOCAL như trên không bảo đảm nguyên tử? **Trả lời:** `txA` đã commit độc lập trước khi `txB` gặp lỗi. Không có coordinator bảo đảm cả hai cùng commit hoặc cùng rollback. Cần cơ chế phối hợp phù hợp hoặc thiết kế nghiệp vụ khác như outbox/saga.

## 13. Ghi nhớ khi thiết kế Persistence Unit

**Chọn RESOURCE_LOCAL** khi một Unit of Work có thể được xử lý an toàn bằng transaction cục bộ trên một tài nguyên dữ liệu, đặc biệt trong Java SE hoặc ứng dụng dùng framework local transaction manager.

**Chọn JTA** khi ứng dụng đã có hạ tầng JTA và cần các `EntityManager` tham gia transaction do container/manager điều phối, hoặc khi kiến trúc thật sự cần phối hợp nhiều tài nguyên tương thích. Khi cần transaction phân tán, phải xác minh khả năng XA và cơ chế phục hồi của toàn bộ hệ thống.

Sau khi chọn transaction type, cần nhất quán ở **ba chỗ**: cấu hình `persistence.xml`, DataSource/transaction manager của runtime và code thiết lập ranh giới transaction. Chỉ một trong ba sai hoặc lệch nhau có thể làm ứng dụng lỗi, commit từng phần hoặc chạy ngoài transaction mong muốn.
