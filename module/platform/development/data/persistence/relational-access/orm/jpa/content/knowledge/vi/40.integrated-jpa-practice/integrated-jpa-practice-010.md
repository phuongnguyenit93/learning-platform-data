# Tái hiện xung đột và xử lý bằng khóa lạc quan trong JPA

**Thực hành tổng hợp — Data Persistence Relational Access ORM JPA**

Khi hai người cùng cập nhật một bản ghi, mỗi người có thể đọc cùng trạng thái ban đầu rồi cố ghi một trạng thái mới. Nếu không kiểm soát xung đột, cập nhật của người ghi sau có thể âm thầm ghi đè cập nhật của người ghi trước. Trong hệ thống bán hàng, đặt chỗ, quản lý tài liệu hay điều chỉnh tồn kho, lỗi này có thể làm mất thay đổi hợp lệ và tạo dữ liệu sai.

**Optimistic locking (khóa lạc quan)** trong Jakarta Persistence cho phép phát hiện loại xung đột này bằng một thuộc tính phiên bản, thường được đánh dấu `@Version`. Provider kiểm tra phiên bản đã đọc khi cập nhật, thay vì giữ khóa ghi trên row từ lúc đọc cho đến khi người dùng quyết định.

Bài thực hành xây dựng một entity `Product` có phiên bản, chủ động tạo hai persistence contexts cùng đọc một bản ghi, để giao dịch A commit trước rồi quan sát giao dịch B thất bại vì phiên bản cũ. Sau đó, chúng ta thiết kế xử lý xung đột ở tầng application/API, phân biệt báo lỗi và retry an toàn, và kiểm thử rằng **không xảy ra lost update**.

> Mục tiêu không phải làm cho mọi lần ghi đều thành công. Mục tiêu là không để một thay đổi dựa trên dữ liệu cũ âm thầm ghi đè thay đổi đã được commit.

---

## 1. Mục tiêu cần đạt

Sau khi thực hành, bạn sẽ làm được:

1. Mô tả bằng timeline lỗi **lost update** khi hai phiên làm việc cùng sửa một bản ghi.
2. Tạo entity JPA sử dụng `@Version` và giải thích vai trò của thuộc tính version.
3. Dùng hai `EntityManager` độc lập để tái hiện hai bản chụp dữ liệu cũ.
4. Quan sát SQL cập nhật có điều kiện phiên bản, số hàng cập nhật và ngoại lệ optimistic locking.
5. Hiểu thời điểm phát sinh xung đột có thể nằm ở `flush()` hoặc `commit()`.
6. Rollback, đóng hoặc bỏ persistence context thất bại thay vì cố tiếp tục.
7. Kiểm tra dữ liệu committed bằng EntityManager mới.
8. Xử lý xung đột kiểu “thông báo và cho người dùng xem lại” hoặc “retry trong transaction mới”.
9. Phân biệt giao dịch đồng thời với biểu mẫu HTTP cũ được gửi sau một khoảng thời gian dài.
10. Nêu giới hạn của `@Version` đối với bulk JPQL, native SQL, unique constraints và các invariants xuyên nhiều rows.

## 2. Bối cảnh nghiệp vụ

Giả sử hệ thống có sản phẩm:

| Thuộc tính | Giá trị ban đầu |
| --- | --- |
| ID | 100 |
| SKU | `BOOK-JPA` |
| Tồn kho `stock` | 10 |
| Giá `price` | 150.000 |
| Version | 0 |

Hai nhân viên cùng mở màn hình:

- **A** thấy tồn kho 10 và quyết định giảm còn 8.
- **B** cũng thấy tồn kho 10 và quyết định giảm còn 9.

Nếu cả hai cùng ghi theo câu SQL chỉ dựa trên `id`, B có thể ghi đè kết quả của A, khiến hệ thống từ 8 quay thành 9 mà không biết bản cập nhật A đã bị thay thế.

## 3. Lost update khi không có kiểm soát phiên bản

Timeline:

~~~text
Thời điểm        Giao dịch A            Giao dịch B
-------------------------------------------------------------
t0               đọc stock=10           đọc stock=10
t1               tính stock=8           tính stock=9
t2               UPDATE stock=8
t3               COMMIT
t4                                      UPDATE stock=9
t5                                      COMMIT
-------------------------------------------------------------
Giá trị cuối: 9, thay đổi A bị ghi đè
~~~

SQL nguy hiểm khi update không có điều kiện version:

~~~sql
UPDATE products
SET stock = 8
WHERE id = 100;

UPDATE products
SET stock = 9
WHERE id = 100;
~~~

Trong nhiều hệ thống, row locks có thể làm các UPDATE chờ nhau, nhưng **chờ nhau không tự chứng minh rằng giá trị thứ hai được tính từ trạng thái mới nhất**. Mức cô lập database và chiến lược truy vấn có ảnh hưởng, song không nên mặc định một transaction thông thường sẽ tự phát hiện mọi lost update.

## 4. Ý tưởng optimistic locking

Thêm cột `version`:

~~~text
ID=100, stock=10, version=0

A đọc version=0
B đọc version=0

A UPDATE ... WHERE id=100 AND version=0
  -> 1 row updated
  -> DB: stock=8, version=1

B UPDATE ... WHERE id=100 AND version=0
  -> 0 rows updated
  -> Provider phát hiện stale version
  -> Optimistic lock conflict
~~~

Minh họa SQL:

~~~sql
UPDATE products
SET stock = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Provider truyền version mới trong `SET` và version đã đọc trong `WHERE`. Nếu không còn row nào khớp phiên bản cũ, provider có thể nhận diện xung đột.

**SQL cụ thể, thứ tự cột và cách tăng version phụ thuộc JPA provider và database dialect.** Đây là SQL minh họa, không phải câu lệnh cần tự viết khi sử dụng `@Version` đúng cách.

## 5. Khóa lạc quan không giống khóa bi quan

| Tiêu chí | Optimistic locking | Pessimistic locking |
| --- | --- | --- |
| Ý tưởng | Phát hiện xung đột khi đồng bộ/ghi | Giành khóa tài nguyên trước khi thay đổi |
| JPA | `@Version`, `LockModeType.OPTIMISTIC` | `LockModeType.PESSIMISTIC_WRITE`... |
| Tại thời điểm đọc | Không cần giữ exclusive row lock cho cả lượt suy nghĩ của user | Có thể khóa/chờ lock tùy mode/DB |
| Khi xung đột | Transaction lỗi, phải xử lý lại | Có thể chờ lock, timeout hoặc deadlock |
| Phù hợp | Nhiều đọc, xung đột ghi không quá thường xuyên | Tài nguyên nóng, cần kiểm soát thứ tự truy cập |
| Chi phí | Version check, xử lý thất bại/retry | Lock contention và khả năng chờ |

Ngay cả khi dùng optimistic locking, SQL UPDATE vẫn dùng khóa ở mức database cần thiết để thực thi update. “Optimistic” không có nghĩa **không có bất kỳ khóa database nào**; nó nghĩa chiến lược ứng dụng không cần giữ pessimistic lock xuyên suốt giai đoạn đọc–suy nghĩ–ghi.

## 6. Mô hình thực hành

Chúng ta sẽ dùng:

~~~text
EntityManagerFactory
      |
      +----- EntityManager A ----- Persistence context A
      |                             |
      |                             +--> Product version=0
      |
      +----- EntityManager B ----- Persistence context B
                                    |
                                    +--> Product version=0

                           Database
                              |
                       products table
~~~

Hai `EntityManager` phải **độc lập**. Nếu lấy cùng Product hai lần trong **cùng** persistence context, JPA có thể trả đúng một managed instance, không tạo ra hai trạng thái cũ độc lập cần cho bài thử.

## 7. Công nghệ cần thiết

Bài học dùng các API:

- Java 17 hoặc phiên bản tương thích với stack đang chạy.
- Jakarta Persistence API có `jakarta.persistence.*`.
- Một JPA provider, ví dụ Hibernate ORM.
- Hệ quản trị quan hệ, ví dụ H2 cho bài lab nhanh hoặc PostgreSQL để kiểm tra gần production.
- JUnit 5 nếu viết integration tests.

Một dependency declaration với Maven **khi dự án đã quản lý phiên bản thông qua BOM/dependencyManagement**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.hibernate.orm</groupId>
        <artifactId>hibernate-core</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu không dùng BOM/dependencyManagement, phải khai báo **các phiên bản tương thích được dự án phê duyệt**. Đoạn trên chỉ minh họa nhóm dependencies, không phải một `pom.xml` độc lập hoàn chỉnh.

JPA provider dependency thường kéo Jakarta Persistence API phù hợp; có thể khai báo API trực tiếp nếu project architecture yêu cầu. Tránh trộn `javax.persistence` cũ với `jakarta.persistence` của thế hệ Jakarta.

## 8. Cấu trúc thư mục mẫu

~~~text
src/
  main/
    java/com/example/lab/Product.java
    resources/META-INF/persistence.xml
  test/
    java/com/example/lab/OptimisticLockingLabTest.java
~~~

Tên package, persistence unit và database URL có thể thay theo dự án. Mục đích là tạo một đơn vị thực hành độc lập, không đòi sửa business service đang chạy thật.

## 9. Entity Product dùng @Version

~~~java
package com.example.lab;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private int stock;

    @Column(nullable = false, precision = 15, scale = 2)
    private BigDecimal price;

    @Version
    private Long version;

    protected Product() {
    }

    public Product(
            String sku,
            int stock,
            BigDecimal price) {
        if (sku == null || sku.isBlank()
                || stock < 0 || price == null
                || price.signum() < 0) {
            throw new IllegalArgumentException(
                "Dữ liệu Product không hợp lệ");
        }
        this.sku = sku;
        this.stock = stock;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getStock() {
        return stock;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public Long getVersion() {
        return version;
    }

    public void changeStock(int newStock) {
        if (newStock < 0) {
            throw new IllegalArgumentException(
                "Tồn kho không được âm");
        }
        this.stock = newStock;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null
                || newPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Giá không hợp lệ");
        }
        this.price = newPrice;
    }

    public void reserve(int units) {
        if (units <= 0 || units > stock) {
            throw new IllegalArgumentException(
                "Không đủ số lượng tồn");
        }
        stock -= units;
    }
}
~~~

### Điểm quan trọng

- `@Version` để provider quản lý phiên bản; **không tạo setter public** cho version.
- `Long` phù hợp làm version counter thông dụng. JPA cũng hỗ trợ một số kiểu version hợp lệ khác theo đặc tả/provider.
- Không dùng `stock` làm version: đó là dữ liệu nghiệp vụ, không phải mã thay đổi đồng bộ.
- `reserve()` kiểm tra business invariant. Optimistic locking bảo vệ cập nhật đồng thời, nhưng không thay kiểm tra stock không âm.
- Với `GenerationType.IDENTITY`, insert có thể xảy ra sớm để lấy ID; điều này không thay cơ chế optimistic locking của UPDATE.

## 10. persistence.xml dành cho bài lab

File `src/main/resources/META-INF/persistence.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">

    <persistence-unit name="optimistic-lock-lab"
                      transaction-type="RESOURCE_LOCAL">

        <provider>
            org.hibernate.jpa.HibernatePersistenceProvider
        </provider>

        <class>com.example.lab.Product</class>

        <properties>
            <property
                name="jakarta.persistence.jdbc.driver"
                value="org.h2.Driver"/>
            <property
                name="jakarta.persistence.jdbc.url"
                value="jdbc:h2:mem:locking_lab;DB_CLOSE_DELAY=-1"/>
            <property
                name="jakarta.persistence.jdbc.user"
                value="sa"/>
            <property
                name="jakarta.persistence.jdbc.password"
                value=""/>
            <property
                name="jakarta.persistence.schema-generation.database.action"
                value="drop-and-create"/>
            <property
                name="hibernate.show_sql"
                value="true"/>
            <property
                name="hibernate.format_sql"
                value="true"/>
        </properties>
    </persistence-unit>
</persistence>
~~~

### Cảnh báo về schema generation

`drop-and-create` **xóa và tạo lại schema** mỗi lần persistence unit được khởi tạo. Chỉ dùng cho database bài lab cô lập; **không sao chép cấu hình này lên production** hoặc vào database có dữ liệu cần giữ.

Mỗi test suite nên quản lý schema/fixtures rõ ràng. Khi dùng PostgreSQL, thay JDBC driver/URL và chọn migration/test schema phù hợp.

## 11. Khởi tạo EntityManagerFactory

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

EntityManagerFactory emf =
    Persistence.createEntityManagerFactory(
        "optimistic-lock-lab");

try {
    EntityManager em = emf.createEntityManager();
    try {
        // Thực hành truy vấn và cập nhật tại đây.
    } finally {
        em.close();
    }
} finally {
    emf.close();
}
~~~

**EntityManagerFactory** tương đối tốn chi phí khởi tạo, có thể dùng chung theo application lifecycle. **EntityManager** quản lý một persistence context và không được chia sẻ tùy tiện giữa các threads. Bài lab sẽ tạo hai EntityManagers riêng để mô phỏng hai phiên làm việc.

## 12. Tạo dữ liệu ban đầu

~~~java
static Long seedProduct(EntityManagerFactory emf) {
    EntityManager em = emf.createEntityManager();
    try {
        em.getTransaction().begin();

        Product product = new Product(
            "BOOK-JPA",
            10,
            new BigDecimal("150000.00")
        );

        em.persist(product);
        em.getTransaction().commit();

        return product.getId();
    } catch (RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
~~~

Sau khi commit:

~~~text
Product
  id      = generated by database
  sku     = BOOK-JPA
  stock   = 10
  price   = 150000.00
  version = initial provider-managed value
~~~

Trong Hibernate với numeric version, giá trị khởi tạo thường là 0, nhưng test không nên phụ thuộc tuyệt đối vào con số nếu mục tiêu là portable JPA. Hãy đọc và lưu **version ban đầu thực tế**.

## 13. Vì sao phải dùng hai EntityManagers?

Trong một context:

~~~java
Product p1 = em.find(Product.class, id);
Product p2 = em.find(Product.class, id);

assert p1 == p2;
~~~

Đó thường là **một** managed instance. Thay đổi từ `p1` sẽ phản ánh trên `p2` trong Java memory.

Trong hai contexts:

~~~java
EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();

Product a = emA.find(Product.class, id);
Product b = emB.find(Product.class, id);

// a và b là hai Java instances độc lập.
~~~

Mỗi EntityManager có bản chụp state/version ở thời điểm nó load. Đây là mô hình gần với hai HTTP requests hoặc hai service instances trong hệ thống thật.

## 14. Kịch bản tái hiện cơ bản

Các bước:

~~~text
1. Seed Product(stock=10, version=v0), commit.
2. EM-A đọc Product -> A thấy v0.
3. EM-B đọc Product -> B thấy v0.
4. TX-A bắt đầu, A.changeStock(8).
5. TX-A flush/commit -> DB có stock=8, version=v1.
6. TX-B bắt đầu, B.changeStock(9).
7. TX-B flush/commit -> version v0 không còn khớp.
8. B bị optimistic conflict; rollback và không reuse context lỗi.
9. EM-C mới đọc DB -> stock=8, version=v1.
~~~

Ở đây hai contexts đọc cùng một phiên bản trước khi A commit; các transaction ghi được bắt đầu lần lượt để test tập trung vào **stale version check**. Đây vẫn là một tình huống optimistic conflict hợp lệ, không cần cho hai threads chạy đồng thời.

## 15. Bài thử đầu tiên: cả A và B đọc cùng version

~~~java
EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();

try {
    Product a = emA.find(Product.class, productId);
    Product b = emB.find(Product.class, productId);

    System.out.println(a.getStock()); // 10
    System.out.println(b.getStock()); // 10

    System.out.println(a.getVersion());
    System.out.println(b.getVersion());
} finally {
    emA.close();
    emB.close();
}
~~~

Kỳ vọng: hai objects đều đọc tồn kho 10 và có phiên bản bằng nhau trước khi có transaction cập nhật nào commit.

**Chưa có conflict** ở bước này. Xung đột chỉ có ý nghĩa khi cả hai cố ghi những state dựa trên version cũ.

## 16. Thực hiện transaction A

Giả sử `a` và `b` đã được load từ hai EntityManagers như phần trên, nhưng **các EntityManager vẫn đang mở**.

~~~java
EntityTransaction txA = emA.getTransaction();

txA.begin();
a.changeStock(8);

emA.flush();
txA.commit();
~~~

Trong provider hỗ trợ và sau commit thành công:

~~~text
DB: stock=8, version=v1
A:  stock=8, version=v1
B:  stock=10, version=v0 (stale)
~~~

### Vì sao B vẫn còn stock=10?

Persistence context B đã materialize Product trước khi A cập nhật. JPA **không tự động sửa mọi object đang managed trong EntityManagers khác** khi một transaction ở nơi khác commit.

Không có cơ chế “live synchronization” giữa mọi contexts chỉ vì chúng đến từ cùng `EntityManagerFactory`.

## 17. Thực hiện transaction B với phiên bản cũ

~~~java
EntityTransaction txB = emB.getTransaction();

try {
    txB.begin();
    b.changeStock(9);
    emB.flush();
    txB.commit();

    // Với dữ liệu stale và @Version hoạt động đúng,
    // không nên tới được nhánh thành công này.
} catch (RuntimeException ex) {
    if (txB.isActive()) {
        txB.rollback();
    }
    throw ex;
}
~~~

Trong bài lab, B vẫn giữ version `v0`, trong khi DB đã có `v1`. Khi provider đồng bộ UPDATE có version predicate, B không thể cập nhật row cũ như thể A chưa từng ghi.

### Ngoại lệ có thể ở đâu?

JPA có thể phát hiện lỗi tại:

- `emB.flush()`;
- `txB.commit()` khi flush bị hoãn;
- hoặc ở tầng transaction manager và được bọc bởi một exception khác.

Vì vậy test nên bao cả **flush và commit**, kiểm tra cause chain khi cần.

## 18. SQL minh họa sau mỗi lần ghi

Giả sử ID thực tế là 100 và numeric version ban đầu 0.

**A:**

~~~sql
UPDATE products
SET stock = 8, version = 1
WHERE id = 100 AND version = 0;
-- 1 row affected
~~~

**B:**

~~~sql
UPDATE products
SET stock = 9, version = 1
WHERE id = 100 AND version = 0;
-- 0 rows affected
~~~

JPA provider nhận diện row count không như kỳ vọng và báo optimistic lock conflict theo implementation.

Một số providers mặc định cập nhật thêm các mapped columns ngay cả khi chỉ `stock` đổi; một số có chiến lược dynamic update. Đừng assert SQL raw string chính xác tuyệt đối theo tên cột/thứ tự/alias nếu mục tiêu chỉ là concurrency semantics.

## 19. Ngoại lệ thường gặp

Trong Jakarta Persistence:

~~~java
jakarta.persistence.OptimisticLockException
~~~

Với transaction resource-local, lỗi có thể trực tiếp là `OptimisticLockException` ở `flush()` hoặc được bọc khi `commit()`.

Trong Spring, exception translation/transaction management có thể chuyển/bọc thành những loại như `ObjectOptimisticLockingFailureException`, `JpaOptimisticLockingFailureException` hoặc loại khác theo integration/version.

### Không chỉ kiểm tra message

Thông điệp exception không phải API contract ổn định; có thể thay đổi theo:

- Provider/dialect.
- Entity name.
- Phiên bản Hibernate.
- JDBC driver.
- Localization.

Test nên kiểm tra **type/cause semantics** và trạng thái database sau thất bại, không phụ thuộc nguyên văn một message.

## 20. Test harness JUnit 5

Thiết kế test sử dụng cùng persistence unit nhưng mỗi test có fixture sạch.

~~~java
package com.example.lab;

import jakarta.persistence.*;
import org.junit.jupiter.api.*;
import java.math.BigDecimal;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class OptimisticLockingLabTest {

    static EntityManagerFactory emf;
    Long productId;

    @BeforeAll
    static void openFactory() {
        emf = Persistence.createEntityManagerFactory(
            "optimistic-lock-lab");
    }

    @BeforeEach
    void prepare() {
        EntityManager em = emf.createEntityManager();
        try {
            em.getTransaction().begin();
            em.createQuery(
                "DELETE FROM Product p")
              .executeUpdate();
            em.getTransaction().commit();
        } catch (RuntimeException ex) {
            if (em.getTransaction().isActive()) {
                em.getTransaction().rollback();
            }
            throw ex;
        } finally {
            em.close();
        }

        productId = seedProduct(emf);
    }

    @AfterAll
    static void closeFactory() {
        if (emf != null) {
            emf.close();
        }
    }

    // seedProduct và các test bên dưới.
}
~~~

### Lưu ý

- Khi dùng setup xóa toàn bảng, **không chạy những tests này song song trên cùng H2 database**.
- Bộ mã này dùng static factory và fixture chung để đơn giản hóa; dự án thực có thể dùng per-test database/schema isolation.
- Chỉ xóa bảng trong **test database**. Không chạy fixture cleanup như thế này trên database có dữ liệu thật.
- IDENTITY có thể không reset sequence sau DELETE; test nên dùng `productId` trả về, không hardcode ID=100.

## 21. Helper seedProduct cho JUnit

Đặt trong class test:

~~~java
static Long seedProduct(EntityManagerFactory emf) {
    EntityManager em = emf.createEntityManager();
    try {
        em.getTransaction().begin();

        Product p = new Product(
            "BOOK-JPA-" + UUID.randomUUID(),
            10,
            new BigDecimal("150000.00")
        );
        em.persist(p);

        em.getTransaction().commit();
        return p.getId();
    } catch (RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
~~~

Ở đây sử dụng SKU ngẫu nhiên cho từng fixture để không xung đột unique key ngoài ý muốn. Bài lab không giả định IDENTITY luôn sinh ID theo một dãy cố định.

## 22. Helper nhận diện OptimisticLockException trong cause chain

~~~java
static boolean hasOptimisticLockCause(Throwable error) {
    Throwable current = error;

    while (current != null) {
        if (current instanceof OptimisticLockException) {
            return true;
        }
        current = current.getCause();
    }
    return false;
}
~~~

Hàm này hữu ích với JPA raw resource-local transaction khi lỗi có thể được bọc.

Trong một dự án Spring, có thể kiểm tra cả các exception types mà Spring dịch ra để xác nhận concurrency conflict theo stack đang sử dụng. Không bắt tất cả `RuntimeException` thành optimistic conflict chỉ vì chúng xuất hiện ở `commit()`.

## 23. Integration test tái hiện xung đột

Ví dụ test chính:

~~~java
@Test
void secondWriterMustNotOverwriteFirstWriter() {
    EntityManager emA = emf.createEntityManager();
    EntityManager emB = emf.createEntityManager();

    try {
        // Hai contexts đọc trước khi có write.
        Product a = emA.find(
            Product.class, productId);
        Product b = emB.find(
            Product.class, productId);

        assertEquals(10, a.getStock());
        assertEquals(10, b.getStock());

        Long initialVersion = a.getVersion();
        assertEquals(initialVersion, b.getVersion());

        // Writer A được commit.
        emA.getTransaction().begin();
        a.changeStock(8);
        emA.flush();
        emA.getTransaction().commit();

        // Writer B vẫn giữ version cũ.
        emB.getTransaction().begin();
        b.changeStock(9);

        RuntimeException failure = assertThrows(
            RuntimeException.class,
            () -> {
                emB.flush();
                emB.getTransaction().commit();
            }
        );

        assertTrue(
            hasOptimisticLockCause(failure),
            "Kỳ vọng optimistic version conflict"
        );

        if (emB.getTransaction().isActive()) {
            emB.getTransaction().rollback();
        }

        // Dùng context mới để kiểm tra dữ liệu thật.
        EntityManager verifier =
            emf.createEntityManager();
        try {
            Product current = verifier.find(
                Product.class, productId);
            assertEquals(8, current.getStock());
            assertNotEquals(
                initialVersion,
                current.getVersion()
            );
        } finally {
            verifier.close();
        }
    } finally {
        if (emA.getTransaction().isActive()) {
            emA.getTransaction().rollback();
        }
        if (emB.getTransaction().isActive()) {
            emB.getTransaction().rollback();
        }
        emA.close();
        emB.close();
    }
}
~~~

### Test khẳng định điều gì?

1. Hai persistence contexts ban đầu đọc cùng một version.
2. A ghi và commit thành công.
3. B cố ghi dựa vào version cũ và thất bại.
4. B được rollback nếu còn active.
5. Dữ liệu DB sau cùng là của A, không bị B ghi đè.

### Vì sao assert ở cả flush và commit?

Vì provider có thể hoãn SQL cho đến commit. Một test chỉ gọi `emB.flush()` và không kiểm tra commit có thể bỏ sót lỗi ở thời điểm commit trong một cấu hình khác.

### Cẩn trọng với isolation level

Ví dụ này cố tình để transaction B bắt đầu **sau khi A commit**, còn entity B đã được load trước đó. Nhờ vậy test tập trung vào stale version check mà ít phụ thuộc vào hiện tượng snapshot/serialization của các giao dịch đồng thời ở mức isolation cao hơn.

## 24. Nếu test vẫn không báo conflict

Các khả năng cần kiểm tra:

- Entity chưa có `@Version` hoặc provider không map đúng.
- Query không update một persistent field thực sự.
- Hai objects đến từ cùng context, không phải hai bản độc lập.
- B vô tình `refresh()` hoặc load lại sau A commit.
- Có ai đó gán version mới cho B một cách thủ công.
- Test dùng bulk DML/native SQL, không qua managed update.
- Transaction B không được bắt đầu/commit đúng.
- Fixture/table schema không có cột version hoặc metadata sai.
- L2 cache/test setup làm path khác điều mong muốn.

**Không thêm `Thread.sleep()` chỉ để “mong có race”.** Bài thử ở trên tạo xung đột có xác định bằng việc kiểm soát thời điểm load và commit.

## 25. Xác minh SQL bằng logging

Hibernate có thể log SQL thông qua các logger và property provider-specific:

~~~properties
hibernate.show_sql=true
hibernate.format_sql=true
~~~

Trong log kỳ vọng thấy một UPDATE có version predicate tương đương:

~~~sql
UPDATE products
SET stock=?, price=?, sku=?, version=?
WHERE id=? AND version=?;
~~~

Đây chỉ là SQL minh họa; Hibernate có thể chọn danh sách columns/format khác. Với mã JPA chuẩn, không cần viết thủ công câu UPDATE này.

### Bind parameters

Nếu bật log bind parameter ở môi trường test, có thể quan sát version cũ và version mới. Trong production không nên log raw SQL parameters chứa dữ liệu cá nhân hoặc bí mật khi không có data governance phù hợp.

## 26. Vai trò của row count

Hình dung:

~~~text
First UPDATE:
  WHERE id=100 AND version=0
  affected rows = 1

Second UPDATE:
  WHERE id=100 AND version=0
  affected rows = 0
~~~

Provider có thể dựa trên affected-row expectation để ném optimistic conflict. Nhưng application **không nên tự đọc JDBC update count cho mọi managed entity update** — JPA provider đã xử lý version semantics theo mapping.

Nếu tự viết SQL bulk/native update, developer phải thiết kế/kiểm tra affected rows và version predicate một cách tường minh nếu muốn giữ concurrency contract.

## 27. Flush không phải commit

Một hiểu nhầm:

> “A gọi `flush()` thành công nghĩa A đã ghi chắc chắn và B phải thất bại.”

Không hẳn. `flush()` đồng bộ pending operations vào database **trong transaction**, nhưng A vẫn có thể rollback.

Ví dụ:

~~~text
TX A:
  UPDATE with version check
  flush success
  rollback

TX B:
  behavior phụ thuộc transaction isolation/locks
  và trạng thái commit cuối cùng của A
~~~

Với bài test, phải **commit A** trước khi cho B thực hiện stale update để có kết quả có thể xác minh.

## 28. Sau optimistic conflict phải rollback và bỏ context lỗi

Khi có lỗi version:

~~~java
try {
    tx.begin();
    // Load + modify + flush/commit
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Không tiếp tục:

~~~java
catch (OptimisticLockException ex) {
    em.refresh(product);
    em.flush();
    tx.commit();
}
~~~

trên một transaction đã có lỗi. Theo JPA transaction semantics, xung đột optimistic locking có thể khiến transaction bị đánh dấu rollback-only; provider có thể không bảo đảm persistence context còn ở trạng thái thích hợp để tiếp tục.

**Muốn retry, mở transaction/persistence context mới, load lại dữ liệu, kiểm tra lại business rules.**

## 29. Tại sao không reuse object stale?

Product B vẫn có:

~~~text
stock=9
version=v0
~~~

Sau khi DB chuyển thành:

~~~text
stock=8
version=v1
~~~

Object B không phải một bản state phù hợp để tiếp tục cập nhật như chưa có gì xảy ra. Một lần `merge(b)` vô điều kiện vào context mới có thể sao chép thông tin người dùng cũ lên managed instance mới hoặc tiếp tục gây conflict, tùy provider/semantics.

### Hướng xử lý

- Đọc lại current state từ database.
- Xác định người dùng muốn **giữ nội dung nào**.
- Re-evaluate invariant và authorization.
- Áp dụng một command có ý nghĩa nghiệp vụ lên current state.
- Ghi trong transaction mới với @Version.

Không tự động “thắng cuộc” bằng cách bỏ version predicate.

## 30. Kết quả của bài thử

| Mốc | Stock | Version | Ghi chú |
| --- | ---: | --- | --- |
| Sau seed | 10 | v0 | Dữ liệu gốc |
| A và B cùng đọc | 10 | v0 | Hai context độc lập |
| A commit | 8 | v1 | A thắng |
| B cố commit | 9 (chỉ trong object stale) | v0 | B bị xung đột |
| DB kiểm tra sau B fail | 8 | v1 | Không bị B ghi đè |

Đây là giá trị cốt lõi của optimistic locking: **phát hiện xung đột, bảo vệ cập nhật đã commit và để application quyết định phản ứng phù hợp**.

## 31. Hai hướng xử lý xung đột

Khi B gặp stale version, application có hai lựa chọn phổ biến:

**Hướng A — báo conflict cho người dùng**:

~~~text
Người dùng B muốn sửa stock=9
  -> Conflict
  -> Hiển thị dữ liệu hiện tại stock=8
  -> Người dùng xem lại và quyết định
  -> Gửi command mới với version mới
~~~

**Hướng B — tự retry một command có thể chạy lại an toàn**:

~~~text
Command: reserve 1 unit
  -> Load stock=10, version=v0
  -> Concurrent writer commit stock=8, v1
  -> Conflict
  -> Rollback, open new transaction
  -> Reload stock=8, version=v1
  -> Reapply "reserve 1 unit"
  -> stock=7, commit nếu vẫn đủ
~~~

Hai hướng không thể thay thế cho nhau tùy tiện. Đặc biệt, **“set stock = 9”** và **“reserve 1 unit”** có ý nghĩa nghiệp vụ khác nhau.

## 32. Khi nào phải trả conflict thay vì retry tự động?

Hãy ưu tiên cho người dùng giải quyết khi:

- Họ đang chỉnh sửa một biểu mẫu chứa nhiều trường.
- Giá trị mới được lựa chọn sau khi nhìn trạng thái cũ.
- Hai người thay nội dung tài liệu/hợp đồng.
- Người dùng cần so sánh và merge các thay đổi.
- Retry sẽ làm mất ý nghĩa “tôi muốn ghi đúng điều tôi đã xem”.
- Hành động có external side effects không thể lặp lại an toàn.

Ví dụ:

~~~text
Người A: sửa price = 140000
Người B: sửa description theo form mở từ trước
~~~

Nếu server retry bằng cách ghi nguyên entity/form của B lên bản mới, giá mà A vừa sửa có thể bị ghi đè mà không được B chủ ý thay đổi.

**Đừng giải quyết conflict bằng chính cách tạo lại lost update.**

## 33. Khi nào retry có thể hợp lý?

Retry thường có thể cân nhắc cho command có ý nghĩa rõ ràng và có thể tính lại trên state mới:

- “Giảm tồn kho đi 1 đơn vị” nếu vẫn còn hàng.
- “Tăng số lượt sử dụng lên 1” nếu không phải operation có side effect độc lập.
- “Gắn một tag vào set” khi kiểm tra duplicate/idempotency.
- “Xác nhận hành động” mà domain rule và idempotency key cho phép.

Không retry mù quáng khi:

- Command chỉ định **giá trị tuyệt đối** dựa trên bản cũ.
- Phiên bản mới làm business invariant thay đổi.
- Có external payment/email/message đã thực hiện.
- Transaction outcome chưa rõ.
- Conflict quá thường xuyên, retry có thể gây tranh chấp dữ dội hơn.

**Mỗi lần retry phải load lại state và đánh giá lại luật nghiệp vụ**, không chỉ chạy lại `flush()`.

## 34. Ví dụ command có ý nghĩa: ReserveStock

Thay vì:

~~~java
product.changeStock(9);
~~~

dịch yêu cầu nghiệp vụ thành:

~~~java
product.reserve(1);
~~~

Method `reserve()` của entity đã định nghĩa:

~~~java
public void reserve(int units) {
    if (units <= 0 || units > stock) {
        throw new IllegalArgumentException(
            "Không đủ số lượng tồn");
    }
    stock -= units;
}
~~~

Khi retry, command `reserve(1)` được áp vào **stock mới nhất đã load**, nên không âm thầm đưa stock về một giá trị từ màn hình cũ.

### Optimistic locking và business invariant bổ sung nhau

Optimistic locking phát hiện snapshot stale. `reserve()` kiểm tra số lượng còn lại. Nếu sau khi A giữ 8 units mà chỉ còn 2, một command B đặt 5 units phải **thất bại do không đủ hàng**, không được cố commit bằng cách đưa stock âm.

## 35. Tầng application chịu trách nhiệm rollback/retry

Một service không nên bắt conflict trong cùng transaction rồi tiếp tục:

~~~java
@Transactional
public void reserve(Long productId, int units) {
    try {
        Product product =
            em.find(Product.class, productId);
        product.reserve(units);
        em.flush();
    } catch (OptimisticLockException ex) {
        // Sai nếu tiếp tục dùng chính transaction này
        // và giả định có thể sửa rồi commit.
    }
}
~~~

Sau lỗi, transaction có thể bị đánh dấu rollback-only. Với Spring, exception có thể xuất hiện ở commit do interceptor thực hiện **sau khi method đã trả về**, nên catch bên trong method có thể không bắt được lỗi.

### Ranh giới phù hợp

~~~text
Outer retry coordinator (không giữ transaction cũ)
    |
    +--> Attempt 1: new transaction
    |       load -> reserve -> flush -> commit
    |       conflict -> rollback
    |
    +--> Attempt 2: new transaction
            reload -> reserve -> flush -> commit
~~~

Retry nằm **bên ngoài transaction boundary của từng attempt**.

## 36. Spring TransactionTemplate: retry có transaction mới

Ví dụ service dùng Spring transaction infrastructure và EntityManager container-managed:

~~~java
@Service
public class StockReservationService {

    private final TransactionTemplate transactionTemplate;

    @PersistenceContext
    private EntityManager em;

    public StockReservationService(
            PlatformTransactionManager manager) {
        this.transactionTemplate =
            new TransactionTemplate(manager);
        this.transactionTemplate.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );
    }

    public int reserveWithRetry(
            Long productId, int units) {
        if (units <= 0) {
            throw new IllegalArgumentException(
                "units phải dương");
        }

        RuntimeException lastConflict = null;
        final int maxAttempts = 3;

        for (int attempt = 1;
                attempt <= maxAttempts;
                attempt++) {
            try {
                Integer remaining =
                    transactionTemplate.execute(status -> {
                        Product product = em.find(
                            Product.class, productId);

                        if (product == null) {
                            throw new ProductNotFound(productId);
                        }

                        product.reserve(units);
                        em.flush();

                        return product.getStock();
                    });

                return Objects.requireNonNull(
                    remaining,
                    "Không có kết quả transaction");

            } catch (RuntimeException ex) {
                if (!isOptimisticConflict(ex)) {
                    throw ex;
                }

                lastConflict = ex;
                // Vòng tiếp theo sẽ có transaction mới.
            }
        }

        throw new StockConflict(
            "Không thể giữ hàng sau nhiều lần xung đột",
            lastConflict
        );
    }

    private static boolean isOptimisticConflict(
            Throwable error) {
        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if (current instanceof OptimisticLockException
                    || current instanceof
                    ObjectOptimisticLockingFailureException) {
                return true;
            }
        }
        return false;
    }
}
~~~

Các lớp `ProductNotFound` và `StockConflict` là application-defined exceptions. Imports cần có Spring `@Service`, `PlatformTransactionManager`, `TransactionTemplate`, `TransactionDefinition`, `ObjectOptimisticLockingFailureException`, Jakarta `@PersistenceContext`/`EntityManager`/`OptimisticLockException` và `java.util.Objects`.

### Điều quan trọng của ví dụ

- Mỗi attempt chạy trong một transaction mới với `REQUIRES_NEW`.
- Khi attempt ném exception, TransactionTemplate để transaction manager xử lý rollback.
- Retry coordinator bắt exception **bên ngoài** attempt, bao gồm lỗi từ commit.
- Mỗi lần tìm lại Product rồi gọi `reserve(units)` trên **state hiện tại**.
- `em.flush()` giúp lộ conflict trong scope attempt, nhưng commit vẫn do template quản lý.
- Chỉ optimistic conflicts được retry; hết hàng/không tìm thấy không tự retry.
- Giới hạn attempts tránh vòng lặp vô tận.

### Giới hạn môi trường

Đoạn code giả định transaction manager được cấu hình đúng cho JPA datasource. Nếu outer caller đã mở transaction, `REQUIRES_NEW` sẽ suspend outer transaction khi được hỗ trợ; phải hiểu transaction propagation và resource boundaries thực tế. Không dùng pattern này để “vượt qua” một transaction nghiệp vụ lớn cần atomicity toàn bộ.

## 37. Retry không có nghĩa bảo đảm thành công

Giả sử stock ban đầu 10:

~~~text
A reserve 8 -> stock 2, commit
B reserve 5 -> conflict
B reload stock 2
B reserve 5 -> business failure
~~~

Đây là kết quả **đúng**. Optimistic locking bảo vệ DB update, còn business method từ chối vượt tồn kho. Không được biến business exception “không đủ hàng” thành retry bất tận.

Khi nhiều workers thường xuyên cập nhật cùng một row, số conflicts có thể tăng và làm thông lượng giảm. Lúc này cần đánh giá mô hình phân bổ hàng, atomic conditional SQL, queueing hoặc pessimistic locking.

## 38. Backoff và chống retry storm

Trong ví dụ trên, ba attempts diễn ra liền nhau cho đơn giản. Trong production, có thể cân nhắc:

- Exponential backoff có giới hạn.
- Jitter để các workers không retry đồng loạt.
- Deadline toàn use case.
- Metrics số lần conflicts và retries.
- Rate/concurrency limits.
- Idempotency key khi operation có thể bị gọi lại do HTTP/network.

Không dùng `Thread.sleep()` như một “cơ chế khóa lạc quan” hoặc để làm test concurrency đáng tin. Backoff là chính sách giảm tải, không thay kiểm tra version.

## 39. REST API: conflict không chỉ xảy ra trong một transaction

Một vấn đề thường gặp trong ứng dụng web:

~~~text
09:00 User A GET Product(id=100, version=5)
09:01 User B sửa Product -> version=6, commit
09:20 User A POST form cũ (price, stock...)
      Server load Product mới version=6
      Server ghi giá trị form của A
      Commit -> version=7, không có conflict tự động
~~~

Tại sao `@Version` **có thể không bắt được** trường hợp này?

Vì transaction POST của A mới được bắt đầu lúc 09:20 và **đọc version mới nhất 6**. Nếu service bỏ qua version=5 mà A nhìn thấy khi mở form, JPA chỉ biết “transaction POST đọc version 6 rồi ghi version 6” — không có stale managed state trong transaction đó.

### Kết luận

Muốn phát hiện **stale HTTP form giữa các requests**, API phải nhận và kiểm tra **expectedVersion từ lúc người dùng đọc dữ liệu** hoặc dùng conditional HTTP semantics như ETag/If-Match.

## 40. DTO gửi version về client

Một response khi GET:

~~~java
public record ProductView(
    Long id,
    String sku,
    int stock,
    BigDecimal price,
    Long version
) {}
~~~

Ví dụ JSON:

~~~json
{
  "id": 100,
  "sku": "BOOK-JPA",
  "stock": 10,
  "price": 150000.00,
  "version": 5
}
~~~

Khi gửi command cập nhật, client gửi giá trị đã xem:

~~~json
{
  "newPrice": 145000.00,
  "expectedVersion": 5
}
~~~

Version là một **concurrency token**, không phải token xác thực/quyền truy cập. Client biết version không có nghĩa được phép sửa Product. Server vẫn phải kiểm tra authorization/tenant scope.

## 41. Service kiểm tra expectedVersion

~~~java
@Transactional
public ProductView changePrice(
        Long productId,
        BigDecimal newPrice,
        Long expectedVersion) {

    if (expectedVersion == null) {
        throw new MissingVersionPrecondition();
    }

    Product product = em.find(
        Product.class, productId);

    if (product == null) {
        throw new ProductNotFound(productId);
    }

    authorization.requireCanEdit(product);

    if (!Objects.equals(
            product.getVersion(), expectedVersion)) {
        throw new StaleProductEdit(
            "Product đã thay đổi từ lúc mở form");
    }

    product.changePrice(newPrice);
    em.flush();

    return new ProductView(
        product.getId(),
        product.getSku(),
        product.getStock(),
        product.getPrice(),
        product.getVersion()
    );
}
~~~

Các exception và `authorization` ở đây là application components. Method chạy qua Spring transactional proxy và dùng EntityManager theo transaction; không tự open/close EM.

### Vì sao vẫn cần @Version sau khi so sánh?

Vì hai transactions có thể cùng đọc version mới trước khi ghi:

~~~text
TX A reads version=6, expected=6 -> precheck passes
TX B reads version=6, expected=6 -> precheck passes
TX A commits -> version=7
TX B flushes -> optimistic conflict
~~~

Expected-version precheck bảo vệ **khoảng thời gian giữa HTTP GET và PUT/PATCH**; `@Version` bảo vệ **race trong thời gian các transactions đang cập nhật**.

## 42. ETag và If-Match

HTTP có thể biểu diễn phiên bản tài nguyên bằng một **strong ETag**:

~~~http
GET /products/100

HTTP/1.1 200 OK
ETag: "product-100-v5"
Content-Type: application/json

{"id":100,"stock":10,"version":5}
~~~

Client cập nhật:

~~~http
PATCH /products/100
If-Match: "product-100-v5"
Content-Type: application/json

{"price":145000.00}
~~~

Server xác minh token khớp representation version hiện tại theo protocol đã định nghĩa. Nếu không khớp:

~~~http
HTTP/1.1 412 Precondition Failed
~~~

### Không tự ghép ETag bừa bãi

Một ETag mạnh phải phù hợp với semantics HTTP representation, đặc biệt nếu nhiều representations (field sets, content negotiation, compression, localization) có thể có nội dung khác nhau. Version đơn thuần có thể là nền tảng nhưng thiết kế token phải nhất quán.

### 409, 412 và 428

- **412 Precondition Failed:** điều kiện HTTP `If-Match` không thỏa.
- **428 Precondition Required:** API yêu cầu conditional request nhưng client không gửi precondition, nếu server áp policy này.
- **409 Conflict:** ứng dụng báo conflict theo business/API contract, ví dụ optimistic conflict khi xử lý command không dùng If-Match.

Không có yêu cầu mọi `OptimisticLockException` nhất thiết luôn map cùng một HTTP code trong mọi API.

## 43. Người dùng nên nhìn thấy gì khi conflict?

Một UI phù hợp có thể hiển thị:

~~~text
Bạn đang chỉnh sửa bản version 5.
Đã có thay đổi mới ở version 6.

Giá hiện tại:   140.000
Giá bạn nhập:  145.000

Các lựa chọn:
  - Xem và áp lại thay đổi lên dữ liệu mới
  - Hủy chỉnh sửa
  - Tải lại
~~~

Không nên âm thầm gửi lại toàn bộ form cũ và ghi đè mọi field.

### Có thể tự merge không?

Một số trường hợp fields độc lập có thể merge theo policy đã định nghĩa, nhưng cần:

- Biết chính xác fields người dùng đã sửa.
- Biết current state và previous state.
- Đánh giá business invariants.
- Không bỏ quyền truy cập và version checks.
- Xử lý conflicts trên cùng field hoặc quan hệ phức tạp.

“Last write wins” có thể là một business policy hợp lệ trong vài dữ liệu không quan trọng, nhưng phải được chọn có ý thức, không phát sinh tình cờ do bỏ optimistic locking.

## 44. PATCH khác PUT và full-entity merge

Ví dụ User A chỉ muốn đổi giá. Nếu controller nhận toàn bộ Product entity từ request:

~~~java
@PutMapping("/products/{id}")
public void update(
        @RequestBody Product product) {
    em.merge(product);
}
~~~

thì ngoài rủi ro over-posting/authorization, một detached graph từ client có thể mang nhiều fields cũ.

### Hướng phù hợp

Dùng command DTO biểu diễn rõ ý định:

~~~java
public record ChangePriceCommand(
    BigDecimal newPrice,
    Long expectedVersion
) {}
~~~

Service chỉ sửa:

~~~java
product.changePrice(command.newPrice());
~~~

và giữ authorization, version check, domain validation.

### PATCH không tự tránh conflict

Nếu hai PATCH cùng sửa `price`, @Version vẫn cần. Nếu hai PATCH sửa hai fields khác nhau, JPA entity-level version có thể cố tình coi đó là conflict để bảo vệ aggregate consistency.

## 45. Xung đột ở cấp entity, không phải mặc định cấp field

Giả sử Product version=4:

~~~text
TX A: changePrice(140000)
TX B: changeStock(8)
~~~

Hai transactions sửa **hai fields khác nhau**, nhưng nếu cùng đọc version=4 rồi ghi, transaction ghi sau vẫn có thể xung đột khi dùng @Version trên cùng Product.

### Tại sao?

Version thuộc **entity identity**, không phải một version riêng cho từng field. Đây là chủ ý giúp bảo vệ invariants có thể phụ thuộc nhiều fields.

### Có nên bỏ version để cho hai updates cùng thành công?

Không tự động. Cần cân nhắc:

- Price và stock có thực sự độc lập trong business aggregate không?
- Có thể tách read/write models hoặc entities theo boundaries hợp lý không?
- Có chấp nhận merge ở application layer sau khi đánh giá state mới không?
- Có cần atomic field-specific UPDATE với version logic riêng không?

Đừng chỉ thêm Hibernate dynamic update và nghĩ nó tự biến @Version thành field-level optimistic locking. Provider-specific behavior phải được đánh giá với concurrency contract.

## 46. @Version được tăng vào thời điểm nào?

Thông thường, với update managed entity có persistent state thay đổi và provider cần ghi SQL, version có thể được tăng trong quá trình flush.

~~~java
Product product = em.find(Product.class, id);
Long before = product.getVersion();

product.changePrice(new BigDecimal("199000.00"));

em.flush();
Long after = product.getVersion();
~~~

Với numeric @Version và update xảy ra, `after` thường khác `before`.

### Những điều không nên giả định

- Mỗi lần gọi setter luôn tăng version.
- Mỗi lần đọc tăng version.
- Mọi provider dùng version khởi tạo 0.
- Mọi association/collection modification luôn tăng version theo cùng quy tắc.
- Giá trị version luôn cập nhật tại chính dòng Java gọi setter.

Đọc docs provider nếu mapping phức tạp, và kiểm chứng bằng integration tests khi version change là một requirement.

## 47. @Version khác LockModeType.OPTIMISTIC

Khai báo:

~~~java
@Version
private Long version;
~~~

định nghĩa thuộc tính version cho entity.

Khi cần yêu cầu optimistic lock semantics khi đọc một managed entity trong transaction, JPA còn cung cấp:

~~~java
Product product = em.find(
    Product.class,
    id,
    LockModeType.OPTIMISTIC
);
~~~

hoặc:

~~~java
em.lock(product, LockModeType.OPTIMISTIC);
~~~

### Khi nào hữu ích?

Một transaction đọc Product để quyết định cập nhật **entity khác**, muốn xác minh Product chưa thay đổi theo optimistic policy trước commit.

### Điều cần hiểu

`OPTIMISTIC` không nhất thiết tăng version; nó yêu cầu kiểm tra optimistic lock theo semantics JPA. Khi và bằng SQL nào provider thực hiện kiểm tra có thể khác nhau.

Không dùng `em.lock()` trên detached entity hoặc ngoài transaction khi lock mode yêu cầu transaction. Với phiên bản không hợp lệ, provider có thể ném exception thích hợp.

## 48. OPTIMISTIC_FORCE_INCREMENT

Trong một số use cases, application cần xem một operation là thay đổi ảnh hưởng tới aggregate/concurrency token ngay cả khi không sửa scalar field của entity được đọc.

~~~java
Product product = em.find(
    Product.class,
    productId,
    LockModeType.OPTIMISTIC_FORCE_INCREMENT
);
~~~

hoặc:

~~~java
em.lock(
    product,
    LockModeType.OPTIMISTIC_FORCE_INCREMENT
);
~~~

### Ý định

Provider phải xử lý việc tăng version theo lock mode semantics khi phù hợp, ngay cả nếu business code không thay đổi scalar Product property.

### Trường hợp cần cân nhắc

Một aggregate root cần đại diện version cho việc thay đổi child state trong một workflow, nhưng root không thay scalar field. Có thể dùng forced increment khi phù hợp với business concurrency contract.

### Cẩn trọng

- Cần transaction phù hợp.
- Tăng version có thể gây nhiều conflicts hơn.
- Có thể tăng tại flush/commit theo provider.
- Không dùng chỉ để “cho chắc” trên mọi read endpoint.

## 49. Không nhầm OPTIMISTIC và PESSIMISTIC_WRITE

~~~java
Product product = em.find(
    Product.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Với database hỗ trợ, provider có thể dùng row-level lock tương đương `SELECT ... FOR UPDATE` hoặc cơ chế thích hợp.

### Điểm khác

Pessimistic write lock có thể làm transaction khác **chờ** trước khi cập nhật. Optimistic lock chủ yếu **phát hiện** khi version không còn khớp.

### Trade-off

- Pessimistic: lock contention, lock timeout/deadlock, giữ connection/transaction.
- Optimistic: nhiều conflict/retry nếu row cực kỳ “nóng”.

Một hệ thống có thể dùng chiến lược khác nhau theo operation. Không có một chiến lược tốt nhất cho mọi workload.

## 50. @Version không thay UNIQUE constraint

Hai transactions cùng tạo một Product mới với SKU giống nhau:

~~~text
TX A: INSERT sku=BOOK-123
TX B: INSERT sku=BOOK-123
~~~

Không có một row Product đã tồn tại với version mà cả hai cùng đọc, nên @Version trên mỗi entity mới **không tự bảo vệ uniqueness của SKU**.

Database constraint:

~~~sql
UNIQUE (sku)
~~~

mới là ranh giới quan trọng để ngăn duplicate business key ở mức dữ liệu.

### Trong test

Tạo hai inserts concurrent với cùng SKU và xác nhận một transaction bị từ chối theo unique constraint khi DB enforcement hoạt động.

Không bắt mọi uniqueness failure thành `OptimisticLockException`. Đây là hai loại concurrency/constraint violations khác nhau.

## 51. @Version không tự bảo vệ invariant trên nhiều rows

Ví dụ:

> “Phải luôn còn ít nhất một bác sĩ trực trong ca.”

Hai transactions:

~~~text
TX A đọc: B đang trực
TX B đọc: A đang trực
TX A tắt trạng thái trực của A, commit
TX B tắt trạng thái trực của B, commit
=> không còn ai trực
~~~

Mỗi transaction cập nhật **một row khác nhau**, nên @Version trên từng row có thể không xảy ra conflict. Đây là một dạng **write skew** tùy isolation/protocol.

### Giải pháp cần xét

- Model chung một versioned aggregate/root có thể được cập nhật khi thay đổi bất kỳ thành viên nào.
- Atomic database constraint phù hợp.
- Pessimistic lock trên row điều phối chung.
- Serializable isolation với xử lý serialization failure.
- Application protocol khác bảo vệ invariant.

Optimistic locking là một công cụ, không phải bằng chứng mọi multi-row invariant đều an toàn.

## 52. Bulk JPQL UPDATE có thể bỏ qua @Version

Ví dụ:

~~~java
int affected = em.createQuery(
        "UPDATE Product p " +
        "SET p.stock = p.stock - :units " +
        "WHERE p.id = :id")
    .setParameter("units", 1)
    .setParameter("id", productId)
    .executeUpdate();
~~~

Bulk JPQL DML **không tự thực hiện cùng optimistic version checking và entity lifecycle callbacks** như cập nhật một managed entity.

### Rủi ro

Nếu một context khác đang giữ Product version=5, bulk SQL thay stock nhưng không tăng version, context ấy có thể vẫn cố ghi với version=5. Một số hành vi có thể dẫn đến overwrite mà @Version đáng lẽ phải ngăn.

### Khi nào dùng bulk?

Với các workloads lớn, bulk DML có thể hợp lý khi application chủ động thiết kế:

- Điều kiện version.
- Điều kiện stock không âm.
- Tenant/authorization scope.
- Cách xử lý affected rows.
- Cache/persistence context invalidation.
- Event/audit strategy.

Đừng coi bulk JPQL là một cách “tăng tốc không thay đổi semantics”.

## 53. Bulk UPDATE có version predicate tường minh

Với numeric version, một ví dụ JPQL có điều kiện:

~~~java
int updated = em.createQuery(
        "UPDATE Product p " +
        "SET p.stock = p.stock - :units, " +
        "    p.version = p.version + 1 " +
        "WHERE p.id = :id " +
        "AND p.version = :expectedVersion " +
        "AND p.stock >= :units")
    .setParameter("units", units)
    .setParameter("id", id)
    .setParameter("expectedVersion", expectedVersion)
    .executeUpdate();

if (updated != 1) {
    throw new StockConflict(
        "Đã đổi phiên bản hoặc không đủ stock");
}
~~~

### Phải hiểu đây là đường ghi khác

Ở đây application tự thiết kế optimistic check và version increment. Nó không tự gọi Product.reserve(), không tự chạy @PreUpdate callbacks theo per-entity semantics, và các managed Product instances đang có trong context có thể trở nên stale.

### Khi affected = 0

Có nhiều nguyên nhân:

- ID không tồn tại.
- Version đã đổi.
- Tồn kho không đủ.
- Tenant predicate không khớp (nếu thêm).

Không nên trả ngay “không đủ hàng” nếu chưa phân loại theo domain/API policy. Một bước đọc lại trong transaction mới có thể làm rõ current state, nhưng phải lưu ý dữ liệu vẫn có thể tiếp tục thay đổi.

### Concurrency

Điều kiện `stock >= :units` nằm trong **cùng atomic UPDATE** giúp tránh check-then-act race cho phép trừ hàng khi không đủ, theo isolation/constraint semantics của DB.

## 54. Native SQL cũng cần tự bảo vệ concurrency

Ví dụ về ý tưởng:

~~~sql
UPDATE products
SET stock = stock - :units,
    version = version + 1
WHERE id = :id
  AND tenant_id = :tenant_id
  AND stock >= :units
  AND version = :expected_version;
~~~

Đây là **SQL minh họa cho schema có tenant_id**, không phải schema Product tối giản ở đầu bài (schema ấy chưa có tenant_id). Nếu dùng trong lab tối giản, hãy bỏ predicate tenant hoặc thêm mapping/column tương ứng; production multi-tenant phải giữ tenant/authorization scope đã được thiết kế.

### Nếu SQL trả về 0 rows

Operation không được áp. Application cần phân biệt permission/not found, stale version và stock invariant theo policy.

### Cache sau native SQL

Native SQL nằm ngoài per-entity dirty checking; cần refresh/clear hoặc tổ chức transaction/context để không đọc nhầm managed state cũ. L2 cache invalidation cũng phụ thuộc integration/provider.

## 55. Không trộn bulk update với managed entity cũ tùy tiện

Ví dụ:

~~~java
Product product =
    em.find(Product.class, productId);

em.createQuery(
        "UPDATE Product p SET p.stock = 0 " +
        "WHERE p.id = :id")
    .setParameter("id", productId)
    .executeUpdate();

System.out.println(product.getStock());
~~~

Biến `product` có thể vẫn chứa stock cũ trong persistence context. Bulk DML không tự đồng bộ mọi managed objects đã load.

### Cách xử lý

Tùy use case:

- Không load managed entity trước bulk update.
- Dùng EntityManager/context khác cho đường bulk.
- `em.clear()` sau khi bảo đảm pending changes đã flush đúng.
- `em.refresh(product)` khi transaction/context còn hợp lệ và muốn lấy state mới.

**Không gọi `clear()` bí mật nếu context còn managed changes khác chưa flush**; các thay đổi đó có thể bị bỏ.

## 56. Version có nên là timestamp không?

Một số JPA mappings cho phép version temporal type phù hợp. Tuy nhiên numeric version counter thường dễ giải thích và kiểm thử hơn:

~~~java
@Version
private Long version;
~~~

Với timestamp version, cần đánh giá độ phân giải thời gian, nguồn sinh thời gian và đặc tính provider/database. Đừng tự làm optimistic locking bằng cách so sánh một `updatedAt` tùy ý mà không kiểm chứng độ chính xác và atomic version update.

### Có được tự sửa version?

Không. Application thường **không nên trực tiếp thay đổi @Version field** để ép một ghi thành công. Việc quản lý phiên bản là trách nhiệm provider hoặc một optimistic protocol được thiết kế rõ khi dùng SQL thủ công.

## 57. Khi nào @Version kiểm tra cả một phiên đọc?

Với một số use cases:

~~~text
Read Product version=5
Read related data
Create separate Reservation row
~~~

Product không có scalar mutation, nên update Reservation row **không nhất thiết làm tăng Product.version**.

Nếu business cần bảo đảm Product không thay đổi trong transaction khi tạo Reservation, có thể cân nhắc:

~~~java
em.lock(product, LockModeType.OPTIMISTIC);
~~~

hoặc `OPTIMISTIC_FORCE_INCREMENT` khi cần biểu diễn “đụng aggregate root”, tùy domain/concurrency policy.

### Không phải mọi check đều cần force increment

Force increment làm tăng xung đột và có write overhead. Chọn theo invariant đang bảo vệ, không tự tăng version trên tất cả read operations.

## 58. Isolation level và optimistic locking

Một DBMS có thể cung cấp các isolation levels:

- READ COMMITTED.
- REPEATABLE READ.
- SERIALIZABLE.

Transaction isolation ảnh hưởng anomalies, snapshot visibility, row locks và serialization errors. @Version cung cấp **application-level stale-write detection** cho entity được versioned khi ORM thực thi managed update.

### Trong concurrency test thực

Nếu hai transactions chồng lấn ở isolation cao, transaction B có thể nhận một database serialization error thay vì JPA `OptimisticLockException` thuần. Test nên xác định mục tiêu:

- **Test @Version:** cho B giữ stale entity nhưng bắt đầu transaction cập nhật sau khi A commit, như phần 23.
- **Test đồng thời thật:** dùng hai threads/transactions và chấp nhận phân loại conflict theo provider/DB isolation.

Không đánh đồng database serialization failure với optimistic version mismatch dù cả hai đều có thể yêu cầu retry.

## 59. Lock timeout khác optimistic conflict

Những exceptions cần phân biệt:

| Loại | Ý nghĩa điển hình |
| --- | --- |
| `OptimisticLockException` | Version/state stale theo optimistic check |
| `LockTimeoutException` | Không lấy được lock trong thời gian chờ phù hợp |
| `PessimisticLockException` | Lỗi lấy pessimistic lock với transaction effects tương ứng |
| `RollbackException` | Transaction commit thất bại, có thể chứa nguyên nhân sâu hơn |
| Constraint violation | DB unique/FK/check từ chối |
| Serialization/deadlock error | Isolation/lock protocol của DB từ chối transaction |

Đừng catch mọi `PersistenceException` và retry vô hạn. Cần **phân loại lỗi và kiểm tra idempotency** theo use case.

## 60. Công thức tư duy cho optimistic locking

~~~text
Read:    (id, state, version=v)
Compute: newState = businessCommand(state)
Write:   UPDATE where id = id and version = v
Check:   affected rows == 1
Result:  success OR conflict
~~~

Với JPA managed entity, provider thường thực hiện logic version predicate; application tập trung vào transaction, business command và conflict policy.

Với bulk/native SQL, developer phải xây dựng protocol tương đương theo nhu cầu.

### Không suy rằng ít conflict nghĩa không có lỗi

Nếu không có version checks, hệ thống có thể báo ít conflicts đơn giản vì nó **âm thầm ghi đè**. Hãy đối chiếu concurrency semantics và dữ liệu committed, không chỉ đếm số exception.

## 61. Thực hành nâng cao: hai threads, hai transactions

Bài thử tuần tự ở phần 23 là cách **ổn định và dễ kiểm tra nhất** để tái hiện stale version. Để mô phỏng giao dịch chồng lấn thực sự, có thể dùng hai worker threads và các synchronization primitives.

### Tại sao không dùng Thread.sleep()?

Mã như:

~~~java
Thread.sleep(200);
~~~

không chứng minh cả hai writers đã đọc cùng version. Trên máy CI chậm, 200 ms có thể không đủ; trên máy khác lại quá lâu. Thay vào đó dùng `CountDownLatch` để đồng bộ **các mốc có ý nghĩa**.

### Sơ đồ thứ tự dự kiến

~~~text
Thread A / Transaction A       Thread B / Transaction B
------------------------       ------------------------
BEGIN                          BEGIN
find Product v0                find Product v0
signal loaded                  signal loaded
wait until both loaded         wait until both loaded
change stock to 8             wait until A committed
flush + COMMIT
signal A committed             change stock to 9
                               flush / COMMIT => conflict
------------------------       ------------------------
DB cuối cùng: stock=8, không bị B ghi đè
~~~

### Khung kiểm thử JUnit

~~~java
@Test
void overlappingTransactionsRejectStaleWriter()
        throws Exception {

    ExecutorService pool =
        Executors.newFixedThreadPool(2);

    CountDownLatch bothLoaded =
        new CountDownLatch(2);

    CountDownLatch firstFinished =
        new CountDownLatch(1);

    Callable<String> writerA = () -> {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();
            Product product = em.find(
                Product.class, productId);

            bothLoaded.countDown();
            if (!bothLoaded.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Timeout waiting for both readers");
            }

            product.changeStock(8);
            em.flush();
            tx.commit();

            return "A_COMMITTED";
        } finally {
            if (tx.isActive()) {
                tx.rollback();
            }
            em.close();
            firstFinished.countDown();
        }
    };

    Callable<String> writerB = () -> {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();
            Product product = em.find(
                Product.class, productId);

            bothLoaded.countDown();
            if (!bothLoaded.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Timeout waiting for both readers");
            }

            if (!firstFinished.await(
                    5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Timeout waiting for first writer");
            }

            product.changeStock(9);
            try {
                em.flush();
                tx.commit();
                return "B_UNEXPECTED_SUCCESS";
            } catch (RuntimeException ex) {
                if (hasOptimisticLockCause(ex)) {
                    return "B_CONFLICT";
                }
                throw ex;
            }
        } finally {
            if (tx.isActive()) {
                tx.rollback();
            }
            em.close();
        }
    };

    try {
        Future<String> a = pool.submit(writerA);
        Future<String> b = pool.submit(writerB);

        assertEquals(
            "A_COMMITTED",
            a.get(10, TimeUnit.SECONDS)
        );
        assertEquals(
            "B_CONFLICT",
            b.get(10, TimeUnit.SECONDS)
        );
    } finally {
        pool.shutdownNow();
    }

    EntityManager verifier =
        emf.createEntityManager();
    try {
        assertEquals(
            8,
            verifier.find(
                Product.class, productId).getStock()
        );
    } finally {
        verifier.close();
    }
}
~~~

Imports cho ví dụ gồm `java.util.concurrent.*`, Jakarta Persistence và JUnit Assertions. Helper `hasOptimisticLockCause()` từ phần 22; fixture seed từ phần 21.

### Giới hạn quan trọng của test hai luồng

- Test giả định H2/default isolation cho phép hai transactions đọc trước khi A cập nhật.
- Với DBMS/isolation khác, transaction B có thể ném serialization failure thay vì OptimisticLockException thuần.
- Latch tránh phụ thuộc may rủi lịch scheduler, nhưng không kiểm soát hoàn toàn hành vi database locking.
- Có timeout cho latch và future để test không treo vô hạn.
- Mỗi thread tạo EntityManager riêng; **không chia sẻ một EntityManager**.
- Không chạy test này song song với suite đang xóa hoặc sửa cùng fixture.

### Vì sao dùng cả test tuần tự và test hai luồng?

Test tuần tự xác minh cơ chế stale `@Version` một cách dễ tái hiện. Test hai luồng kiểm tra end-to-end behavior dưới concurrent transaction scheduling. Hai loại bổ sung nhau, không thay thế nhau.

## 62. Test trường hợp không có xung đột

Một integration test cũng nên chứng minh đường cập nhật bình thường vẫn hoạt động:

~~~text
Seed stock=10, version=v0
TX A load, changeStock(8), commit -> version=v1
TX B mới load current version=v1
TX B changeStock(7), commit -> version=v2

Expect:
  stock=7
  version advanced again
  không có OptimisticLockException
~~~

Mục đích: không tạo một implementation “phát hiện xung đột” bằng cách **từ chối tất cả writes**.

## 63. Test stale HTTP form

Mô phỏng:

1. GET trả `ProductView(version=v0)`.
2. Một transaction khác cập nhật Product và commit, version thành `v1`.
3. Client gửi `ChangePriceCommand(newPrice, expectedVersion=v0)`.
4. Service mở transaction mới, load Product có version `v1`.
5. Precheck từ chối với `StaleProductEdit` hoặc response tương ứng.
6. Không có UPDATE từ request stale.

### Điều cần khẳng định

~~~text
expectedVersion != currentVersion
  -> reject before mutating
  -> committed Product giữ thay đổi mới
~~~

**Test này khác test hai EntityManagers**: các transactions không cần chồng lấn. Nó kiểm tra khoảng thời gian dài giữa HTTP GET và POST, nơi chỉ @Version trong transaction POST không đủ nếu bỏ expectedVersion.

## 64. Test race sau khi precheck đã pass

Hai requests:

~~~text
Request A: expectedVersion=v5, current=v5, precheck OK
Request B: expectedVersion=v5, current=v5, precheck OK

A updates and commits -> v6
B tries update -> OptimisticLockException
~~~

Precheck không loại bỏ race giữa thời điểm kiểm tra và thời điểm cập nhật. Vì vậy vẫn phải giữ @Version, không chỉ so sánh version từ DTO.

### Kết quả API

Có thể trả conflict có cấu trúc và khuyến nghị refresh/reapply. Không dùng vòng catch để tự overwrite phiên bản mới bằng dữ liệu từ form cũ.

## 65. Test version tăng sau cập nhật thật

~~~java
@Test
void versionAdvancesAfterManagedUpdate() {
    EntityManager em = emf.createEntityManager();
    try {
        Product p = em.find(
            Product.class, productId);

        Long original = p.getVersion();

        em.getTransaction().begin();
        p.changePrice(
            new BigDecimal("139000.00")
        );
        em.flush();
        em.getTransaction().commit();

        assertNotEquals(
            original,
            p.getVersion()
        );
    } finally {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        em.close();
    }
}
~~~

Đây là test cho numeric version trong provider đang chạy. Một property-based test có thể tạo nhiều giá trị giá/tồn kho hợp lệ nhưng không cần giả định version bắt đầu bằng 0.

### Nếu gán đúng cùng một giá?

Provider có thể xác định entity không thực sự dirty; không nhất thiết phát UPDATE hoặc tăng version. Test tăng version nên **thực hiện thay đổi persistent state rõ ràng**.

## 66. Test các trường khác nhau vẫn conflict

~~~text
TX A đọc Product(version=v0), sửa price
TX B đọc Product(version=v0), sửa stock
TX A commit -> version=v1
TX B update -> version mismatch
~~~

Đây là **entity-level conflict**, không phải lỗi. Test giúp team hiểu granularity của aggregate/version và tránh vô tình bỏ @Version chỉ vì hai users sửa hai trường khác nhau.

Nếu product domain được tách thành nhiều aggregates với version độc lập, cần test các invariants liên kết giữa các aggregates.

## 67. Test rollback sau conflict

Một test mạnh không chỉ:

~~~java
assertThrows(OptimisticLockException.class, ...);
~~~

mà còn:

- Rollback transaction B khi cần.
- Đóng EntityManager B.
- Đọc Product bằng EntityManager C mới.
- Xác nhận A đã commit; B không ghi đè.
- Kiểm tra những writes khác thuộc transaction B cũng không commit.

### Ví dụ transaction B có hai writes

~~~text
TX B:
  Insert AuditAttempt row
  Update stale Product
  optimistic conflict
  rollback

Expect:
  AuditAttempt INSERT cùng TX B cũng rollback
~~~

Nếu audit failure cần được lưu **ngoài** transaction bị rollback, application phải có logging/outbox/error channel riêng với semantics rõ, không giả định row trong transaction lỗi vẫn commit.

## 68. Test các biến thể @Version trên associations

Một Product có relationship:

~~~java
@OneToMany(mappedBy = "product")
private List<PriceHistory> history;
~~~

Khi thêm PriceHistory, version của Product **có thể hoặc không** tăng tùy owning side, mapping, operation, provider và use of forced increment.

### Nếu business yêu cầu “mọi thay đổi lịch sử giá làm Product version tăng”

Đừng chỉ suy từ @Version có trên Product. Cần:

- Xác định aggregate/root ownership.
- Thiết kế mutation path đúng.
- Dùng forced increment nếu hợp lý.
- Hoặc lưu version trên aggregate state được bảo vệ theo cách khác.
- Viết integration test xác nhận version behavior cụ thể.

Không coi mọi collection mutation đều tương đương update scalar Product.

## 69. Test unique conflict khác optimistic conflict

Hai threads cùng `persist(new Product("BOOK-X", ...))` trong các transactions khác nhau:

- Một insert có thể thành công.
- Insert kia bị database unique constraint từ chối.

Không có hai versions của **cùng một row đã tồn tại** ở đây. Application nên phân loại duplicate SKU riêng, không trả thông báo “dữ liệu đã bị người khác sửa” một cách sai ngữ nghĩa.

### Với upsert

Nếu business cho phép create-or-update, cần một concurrency protocol rõ (unique constraint, atomic upsert SQL, row version checks). Không làm “query tồn tại? nếu không thì insert” mà quên race giữa hai transactions.

## 70. Test SQL và provider behavior

Một test lab có thể bật:

~~~properties
hibernate.show_sql=true
hibernate.format_sql=true
hibernate.generate_statistics=true
~~~

Quan sát:

- UPDATE có version predicate.
- Có một UPDATE thành công.
- B bị optimistic conflict.
- Không có UPDATE ghi đè thành công từ B.
- Sau rollback, DB giữ đúng state.

### Không chỉ dùng SQL count

Một câu SQL UPDATE có thể affected=0 nhưng vẫn là statement được thực thi. Đếm statement count không chứng minh xung đột đã được xử lý đúng. Cần assert **exception semantics và dữ liệu committed**.

### Global statistics

Hibernate Statistics có thể thuộc SessionFactory-wide scope; khi chạy tests song song, counters có thể bị nhiễu. Trong bài lab, test cô lập và log SQL có ích hơn việc gán cứng một query-count budget mà không biết provider SQL shape.

## 71. Spring Data JPA save() không tự giải quyết mọi xung đột

Trong Spring Data JPA:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

một service có thể:

~~~java
@Transactional
public void changePrice(Long id, BigDecimal price) {
    Product product = repository.findById(id)
        .orElseThrow();

    product.changePrice(price);
    // Managed entity được dirty-check khi flush/commit.
}
~~~

Không nhất thiết phải gọi `repository.save(product)` khi Product đã managed trong transaction, dù code có thể dùng save theo team convention.

### Với detached entity?

Spring Data `save()` có thể sử dụng `persist` hoặc `merge` theo chiến lược xác định new/existing entity. `merge()` có semantics copy state và optimistic version handling, không phải một cách “gắn object cũ trở lại” vô điều kiện.

### saveAndFlush() có commit không?

Không. `saveAndFlush()` có thể khiến SQL đồng bộ sớm trong **transaction hiện tại**, nhưng commit vẫn thuộc transaction manager. Một optimistic conflict có thể được phát hiện tại flush hoặc commit tùy provider/timing.

### Ranh giới

Không cho controller nhận raw `Product` entity từ client rồi gọi `repository.save(product)` với hy vọng cơ chế version tự kiểm tra mọi quy tắc authorization, stale form và field visibility.

## 72. Không để client tự sửa version

Trong DTO có version:

~~~json
{
  "newPrice": 145000,
  "expectedVersion": 5
}
~~~

`expectedVersion` là thông tin để **kiểm tra điều kiện ghi**, không phải giá trị được chép vào entity field:

~~~java
product.setVersion(
    request.expectedVersion()); // Không nên làm
~~~

Provider sở hữu việc tăng và kiểm tra @Version cho managed updates.

### Tránh mass assignment

Không map mọi fields tùy ý từ JSON lên Product:

~~~text
id, tenantId, ownerId, version,
internalCost, hiddenFlags, ...
~~~

thành persistent state. Dùng command DTO chỉ chứa fields được phép và so sánh version với current loaded state trước khi gọi domain method.

## 73. Triển khai @Version lên bảng đang có dữ liệu

Đối với hệ thống đã chạy, thêm:

~~~java
@Version
private Long version;
~~~

không phải chỉ sửa một dòng Java. Database schema cần cột version với dữ liệu hợp lệ.

### Lộ trình migration

1. Đánh giá mọi writers hiện tại: JPA, native SQL, jobs, ETL, thủ tục.
2. Tạo cột version theo migration strategy phù hợp DB.
3. Backfill rows cũ bằng một giá trị version khởi tạo hợp lệ.
4. Đảm bảo các rows mới được khởi tạo version đúng theo provider.
5. Chuyển mọi application writers sang update có version semantics.
6. Điều chỉnh bulk/native writers để tăng/check version nếu phải giữ concurrency contract.
7. Bật monitoring/conflict handling và rollout theo kế hoạch.

### Ví dụ SQL định hướng

~~~sql
ALTER TABLE products ADD COLUMN version BIGINT;
UPDATE products SET version = 0 WHERE version IS NULL;
ALTER TABLE products ALTER COLUMN version SET NOT NULL;
~~~

DDL syntax/cách migration **không portable trên mọi DBMS**; ví dụ chỉ minh họa ý định. Với bảng lớn, UPDATE/backfill có thể cần chunks, backfill strategy, migration locks và kế hoạch deploy tương thích nhiều phiên bản ứng dụng.

### Tránh mixed old/new writers

Một writer cũ vẫn dùng:

~~~sql
UPDATE products SET stock = ? WHERE id = ?;
~~~

có thể bỏ qua version check hoặc không tăng version, phá cơ chế bảo vệ. Đây là rủi ro lớn khi rolling deployment.

## 74. Multi-instance application vẫn có thể dùng @Version

Giả sử hai app instances:

~~~text
App Instance A                App Instance B
  JPA EntityManager A          JPA EntityManager B
          |                            |
          +------------+---------------+
                       |
                    Database
                products.version
~~~

@Version được bảo vệ nhờ điều kiện UPDATE và trạng thái ở database, nên không cần hai instances chia sẻ cùng Java lock để phát hiện stale writes.

### Nhưng vẫn cần nhất quán cấu hình

- Mọi writers dùng compatible version semantics.
- DB constraints được enforce.
- L2 cache invalidation đúng cách nếu bật cache.
- Các batch/native writers không âm thầm bỏ version.
- Application handles conflicts thay vì trả lỗi 500 chung không rõ nguyên nhân.

Một local `synchronized` block trong một app instance không bảo vệ những writes ở instance khác.

## 75. Delete cũng cần cân nhắc optimistic consistency

Ví dụ:

~~~text
TX A đọc Product version=5.
TX B sửa Product và commit version=6.
TX A muốn xóa Product.
~~~

Với versioned managed entity, provider có thể dùng optimistic checking khi DELETE, tránh xóa một row đã thay đổi từ lúc A đọc.

### Nhưng:

Bulk JPQL DELETE có thể bỏ qua per-entity version semantics.

Nếu business operation là xóa một aggregate, phải xác định:

- Có bắt buộc xác nhận version user đã xem không?
- Có cascade/orphan/FK constraints không?
- Có data retention/soft delete policy không?
- Có events/audit cần ghi không?

Không coi DELETE là hành động không có concurrency implications.

## 76. Xung đột và idempotency là hai vấn đề khác nhau

Optimistic locking bảo vệ khỏi **stale state overwrite**.

Idempotency bảo vệ khi cùng một **business request** được gửi lại:

~~~text
POST /orders
Idempotency-Key: abc123
~~~

Nếu client mất kết nối sau khi order được commit nhưng trước khi nhận response, retry HTTP có thể tạo thêm order nếu không có idempotency protocol.

### Không dùng @Version thay idempotency key

Một Order mới mỗi lần retry có identity/version khác nhau; @Version không giúp phát hiện hai create requests có cùng business intention.

### Với reserve stock

Nếu retry cùng command vì **optimistic conflict trước commit**, có thể re-run transaction mới. Nếu retry do **không rõ command trước đã commit hay chưa**, cần idempotency request tracking và outcome verification để tránh trừ stock hai lần.

## 77. External side effects và retry

Anti-pattern:

~~~java
@Transactional
public void reserveAndNotify(
        Long productId, int units) {
    product.reserve(units);
    emailGateway.send(...);
    em.flush();
}
~~~

Nếu email gửi xong nhưng UPDATE conflict và rollback, người dùng nhận thông báo đặt hàng thành công trong khi DB không commit.

### Hướng tốt hơn

~~~text
BEGIN TX
  Load Product
  reserve(units)
  INSERT OutboxEvent(StockReserved)
COMMIT

Background publisher:
  Read Outbox
  Notify/email
  Mark delivered or retry
~~~

Outbox giúp ghi **intention to publish** atomic cùng DB state khi cùng transaction resource. Publisher có thể gửi trùng sau crash, nên consumer/handler cần idempotency.

### Tại sao liên quan optimistic retry?

Một attempt thất bại không nên có external side effects không thể rollback. Thiết kế outbox giúp mỗi attempt có kết quả transactional rõ, giảm nguy cơ thông báo trùng/sai khi retry.

## 78. Khi tỷ lệ conflict quá cao

Optimistic locking phù hợp khi conflict tương đối hiếm so với tổng số operations. Nếu hàng trăm workers cùng cập nhật một row Product stock:

~~~text
Read version=100
20 workers compute changes
1 commit succeeds
19 conflicts/retries
~~~

Chi phí retry có thể lớn.

### Các lựa chọn khác

- Atomic conditional SQL update trên cột stock.
- Partition/shard “hot counter” khi business cho phép.
- Queue/serialize commands theo product ID.
- Pessimistic locking trong transaction ngắn.
- Thiết kế riêng inventory reservation ledger.
- Giảm transaction duration hoặc số writes trên cùng aggregate.

Không chỉ tăng `maxAttempts` vô hạn. Hãy đo tỷ lệ conflicts, retries, p95 latency, database lock waits, throughput và business failure rate.

## 79. Chọn chiến lược theo mức tranh chấp

| Workload | Lựa chọn cần cân nhắc | Chú ý |
| --- | --- | --- |
| Sửa hồ sơ ít xung đột | @Version + user conflict UI | Không retry form cũ mù quáng |
| Cập nhật Product giá | @Version + expectedVersion | Authorization, field-level command |
| Reserve stock tần suất vừa | @Version + bounded retry | Recheck stock trên mỗi attempt |
| Reserve stock cực nóng | Atomic conditional SQL/queue/lock | Version/callback/cache policy |
| Ghi nghiệp vụ nhiều rows | Aggregate version/constraints/locks | Write skew và atomicity |
| Tạo resource unique | UNIQUE constraint + idempotency | @Version không thay uniqueness |
| Export/read-only | Không cần force increment mặc định | Không tăng version vô ích |

Điểm quyết định không chỉ là số request/giây; còn là phân bố truy cập, số users cùng đụng một row, transaction duration, data correctness requirements và chi phí xung đột.

## 80. Observability cho optimistic locking

Các metrics hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| Optimistic conflicts per operation | Tỷ lệ xung đột thực |
| Retry attempts per successful command | Retry overhead |
| Max retry exceeded | Commands không thể hoàn tất |
| 409/412 responses | User-facing stale/conflict cases |
| Transaction duration | Thời gian dễ xảy ra stale |
| Rollback count | Chi phí attempts thất bại |
| SQL update rows affected | Phân biệt update thành công/0 rows khi dùng SQL thủ công |
| DB lock waits | Contention ở database |
| Business rejects after retry | Ví dụ không đủ stock sau reload |
| p95/p99 latency | Chất lượng phục vụ |
| Idempotency hits | Duplicate client requests |

### Log an toàn

Có thể ghi:

~~~text
operation=product.reserve
productId=internal-id
attempt=2
reason=optimistic_conflict
durationMs=...
requestId=...
~~~

Không log raw credit card/payment tokens, thông tin cá nhân không cần thiết hoặc toàn bộ entity state chỉ để debug conflict.

## 81. Bảng chẩn đoán sự cố

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Không bao giờ có conflict dù hai writers sửa cùng row | Thiếu @Version, bulk SQL bypass, cùng EM | Kiểm tra mapping/write path, dùng hai EM |
| Test conflict không ổn định | Dựa vào sleep/scheduler | Dùng hai contexts load trước, commit A trước |
| Test chỉ thấy một Java instance | Hai lần `find()` trong cùng persistence context | Dùng hai EntityManagers |
| Test không conflict vì B load sau A commit | B đã lấy version mới | Load B trước khi A commit |
| UPDATE phát nhưng version không đổi | Mapping/provider/custom SQL không versioned | Xem @Version/schema và flush path |
| Conflict ném tại commit thay vì flush | Deferred flush | Bao cả flush/commit trong test |
| Có RollbackException thay vì OptimisticLockException trực tiếp | Exception wrapping | Kiểm tra cause chain |
| Test hai threads ra serialization error | Isolation/DB snapshot semantics | Phân biệt @Version test và concurrency test |
| Retry cùng transaction vẫn thất bại | Transaction đã rollback-only/context invalid | Rollback, mở context/transaction mới |
| Retry stock tạo số âm | Không recheck business invariant | Reload rồi gọi reserve() |
| UI form cũ ghi đè dù có @Version | POST load current version, không xét expectedVersion từ GET | Kiểm tra expectedVersion/If-Match |
| Hai fields khác nhau vẫn conflict | Entity-level version | Đánh giá aggregate boundary/merge policy |
| Bulk update không tăng version | Bulk JPQL bypass managed entity lifecycle | Thêm version protocol hoặc đổi write path |
| Sau bulk query thấy dữ liệu cũ | First-level cache stale | Refresh/clear/new context có kiểm soát |
| Duplicate SKU dù versioned | @Version không bảo vệ insert uniqueness | UNIQUE constraint |
| Không giữ được invariant nhiều row | Write skew/check-then-act | Constraint/lock/aggregate protocol |
| Bật retries nhưng p99 tăng cao | Hot row, retry storm | Backoff/queue/atomic update/lock |
| Email đã gửi nhưng transaction rollback | Side effect trước commit | Outbox/after-commit policy |
| Người dùng gặp 500 cho mọi conflict | API chưa map exception | 409/412 theo contract |
| Lỗi xuất hiện sau service return | Commit do interceptor thực hiện | Retry ở outer boundary |
| SQL log thiếu version WHERE | Query không đi qua versioned managed update | Inspect SQL path/provider mapping |
| Không biết DB state sau lỗi | Chỉ assert exception | Read-back bằng EntityManager mới |

### Thứ tự điều tra

~~~text
Conflict không xuất hiện?
    |
    v
Entity có @Version và schema version?
    |
    v
Hai writers có thực sự giữ state cũ độc lập?
    |
    v
Managed update hay bulk/native DML?
    |
    v
SQL UPDATE có version predicate?
    |
    v
SQL affected rows và exception semantics?
    |
    v
Transaction rollback/commit state?
    |
    v
New EM read-back đúng dữ liệu?
~~~

Nếu mọi tầng kỹ thuật đúng nhưng xung đột vẫn rất thường xuyên, chuyển sang đánh giá **thiết kế contention/workload** thay vì coi đây là lỗi logging.

## 82. Bộ kiểm thử tích hợp nên có

Đây là những **trường hợp cần xây dựng**, không phải một lời khẳng định rằng mọi test đã chạy trong tài liệu:

| Kịch bản | Kết quả cần xác nhận |
| --- | --- |
| Seed versioned Product | ID và version được provider quản lý |
| Update một context | State committed đổi, version tăng |
| Hai EM load cùng version | Hai Java objects độc lập |
| A commit, B stale update | B bị conflict |
| B rollback | Không ghi đè update A |
| New EM read-back | Thấy state đã commit của A |
| B load sau A commit | Update mới hợp lệ có thể thành công |
| A và B sửa hai fields khác nhau | Vẫn có entity-level version conflict |
| HTTP expectedVersion cũ | Precheck từ chối, không overwrite |
| Hai POST cùng expectedVersion | Version check bảo vệ race |
| Retry reserve còn hàng | Reload rồi commit hợp lệ |
| Retry reserve hết hàng | Business invariant từ chối |
| Unique SKU collision | DB unique constraint hoạt động |
| Bulk UPDATE không quản lý version | Không mặc định giữ @Version semantics |
| Bulk UPDATE có version predicate | 1 row = success, 0 row = no update |
| Concurrent insert/chọn cùng ghế | DB protocol ngăn invalid state |
| Conflict trong transaction nhiều writes | Rollback toàn bộ cùng TX |
| Client lặp cùng create command | Idempotency policy ngăn duplicate |
| Outbox và Product trong cùng TX | Cùng commit hoặc cùng rollback |
| Hai threads thật | Conflict/failure đúng theo isolation |

### Mức ưu tiên

Trong project nhỏ, nên hoàn thành trước nhóm:

1. Versioned entity cập nhật bình thường.
2. Hai EntityManagers với stale write.
3. Rollback + DB read-back.
4. Service expectedVersion.
5. Retry có recheck business rule.

Các tests nâng cao về outbox, hot-row contention và bulk/native writer nên đi cùng những tính năng thật có trong dự án.

## 83. Quy trình thực hành từng bước

**Bước A — Chuẩn bị.** Tạo entity `Product` và persistence unit RESOURCE_LOCAL cho database test. Khởi tạo schema có cột version hợp lệ.

**Bước B — Seed.** Insert một Product với stock=10. Commit, đóng EntityManager, lưu ID và version thực tế.

**Bước C — Tạo hai contexts.** Mở `emA`, `emB` riêng, load Product trước bất kỳ update nào.

**Bước D — Ghi A.** Begin A transaction, đổi stock=8, flush và commit.

**Bước E — Ghi B.** Begin B transaction trên stale managed Product, đổi stock=9 và thử flush/commit.

**Bước F — Quan sát.** B phải báo optimistic conflict; rollback/đóng B.

**Bước G — Xác minh.** Mở EM mới, kiểm tra DB còn stock=8.

**Bước H — Mở rộng.** Viết service kiểm tra expectedVersion; chạy hai threads với latch; thử retry reserve trong transaction mới.

**Bước I — Thử đường bypass.** Dùng bulk JPQL UPDATE trên fixture khác và quan sát sự khác biệt, rồi thiết kế version predicate khi cần.

**Bước J — Đánh giá nghiệp vụ.** Chọn conflict UI hay retry theo operation; thêm idempotency/outbox khi có external side effects.

### Điều kiện hoàn thành bài lab

Bạn có thể giải thích vì sao:

~~~text
Version check protects stale writes,
but business rules and transaction policy
still decide whether a retry is safe.
~~~

và có test đọc DB bằng context mới chứng minh cập nhật A không bị B ghi đè.

## 84. Bài tập thực hành

### Bài 1 — Nhận diện lost update

Hai transactions cùng đọc stock=10. A ghi 8, B ghi 9. Nếu B ghi đè mà không thông báo, hiện tượng gì xảy ra?

**Gợi ý:** Lost update; dữ liệu A vừa commit bị thay thế.

### Bài 2 — Vai trò của @Version

Tại sao `@Version` khác việc thêm một column `updatedAt` nhưng không có UPDATE predicate?

**Gợi ý:** Cần kiểm tra stale version tại thời điểm ghi, không chỉ hiển thị mốc thời gian.

### Bài 3 — EntityManager identity

Nếu `em.find(Product.class, id)` hai lần trong cùng EntityManager, có tạo hai snapshots độc lập để tái hiện conflict không?

**Gợi ý:** Không; L1 identity map có thể trả cùng managed instance.

### Bài 4 — Dữ liệu ban đầu

Vì sao test nên đọc version khởi tạo thực tế thay vì hardcode version=0 trong mọi provider?

**Gợi ý:** Initialization strategy thuộc provider/version mapping.

### Bài 5 — SQL update

Viết điều kiện WHERE cần có của một optimistic update cho Product id=100, expectedVersion=5.

**Gợi ý:** `WHERE id = 100 AND version = 5`.

### Bài 6 — A commit

A cập nhật thành công stock=8 từ version=5. B vẫn giữ Product version=5. Khi B ghi stock=9, affected-row expectation là gì?

**Gợi ý:** 0 row nếu DB version đã chuyển lên 6.

### Bài 7 — Flush

`em.flush()` trả về không lỗi có đồng nghĩa transaction đã commit không?

**Gợi ý:** Không. Commit/rollback vẫn do transaction owner quyết định.

### Bài 8 — Exception timing

Vì sao test cần kiểm tra cả `flush()` và `commit()`?

**Gợi ý:** Provider có thể hoãn version check/SQL cho tới commit.

### Bài 9 — Rollback

Sau `OptimisticLockException`, có nên tiếp tục thay Product cũ rồi gọi `tx.commit()` không?

**Gợi ý:** Không; rollback/bỏ context lỗi và mở transaction mới nếu retry.

### Bài 10 — Readback

Tại sao sau test conflict phải dùng EntityManager mới để đọc DB?

**Gợi ý:** Tránh L1 cache trả state cũ hoặc in-memory mutated instance.

### Bài 11 — Không có @Version

Nếu bỏ `@Version`, thử lại kịch bản A=8, B=9. Kết quả nào có nguy cơ xảy ra?

**Gợi ý:** B ghi đè A nếu isolation/write protocol không phát hiện xung đột.

### Bài 12 — Hai threads

Vì sao `CountDownLatch` đáng tin hơn `Thread.sleep()` trong test đồng thời?

**Gợi ý:** Đồng bộ các mốc đọc và commit có ý nghĩa, không phụ thuộc tốc độ scheduler.

### Bài 13 — RESOURCE_LOCAL

Mỗi worker thread nên có EntityManager riêng hay dùng chung một instance?

**Gợi ý:** Riêng; EntityManager không thread-safe cho arbitrary concurrent access.

### Bài 14 — Isolation

Nếu test hai transactions chồng lấn trả database serialization failure thay vì OptimisticLockException, có chứng minh JPA @Version bị hỏng không?

**Gợi ý:** Không; DB isolation có thể phát hiện conflict bằng protocol khác.

### Bài 15 — Lỗi do thứ tự load

Trong một test, B chỉ `find()` sau khi A đã commit. Vì sao không xuất hiện stale-version conflict?

**Gợi ý:** B đã load current version mới.

### Bài 16 — Semantic retry

Phân biệt retry command `changeStock(9)` và `reserve(1)`.

**Gợi ý:** Giá trị tuyệt đối có thể overwrite ý định khác; command tương đối được tính lại trên stock mới.

### Bài 17 — Business invariant

Stock mới sau A commit là 2, B muốn reserve(5). Sau retry B nên làm gì?

**Gợi ý:** Từ chối không đủ stock; không bypass invariant.

### Bài 18 — Retry boundary

Vì sao cần đặt retry loop **ngoài** transaction của từng attempt?

**Gợi ý:** Transaction failed có thể rollback-only; commit error có thể xuất hiện sau service method.

### Bài 19 — Max attempts

Nếu xung đột xảy ra liên tục trên một hot Product, có nên retry vô hạn?

**Gợi ý:** Không; bounded retries/backoff và xem lại contention architecture.

### Bài 20 — Spring saveAndFlush

`repository.saveAndFlush(product)` có tự commit transaction không?

**Gợi ý:** Không; flush và commit là hai ranh giới khác nhau.

### Bài 21 — Stale HTTP form

User GET Product(version=5), người khác cập nhật thành version=6, rồi user PUT. Nếu PUT service load current version=6 và bỏ qua expectedVersion=5, `@Version` có chắc bắt được stale form không?

**Gợi ý:** Không; POST transaction có thể cập nhật thành công trên version 6 nếu không kiểm tra version từ lúc GET.

### Bài 22 — expectedVersion

Vì sao phải kiểm tra expectedVersion trước mutation và vẫn giữ `@Version`?

**Gợi ý:** Bảo vệ hai khoảng thời gian khác nhau: GET→POST và precheck→commit.

### Bài 23 — HTTP status

Với request `If-Match` không khớp, status HTTP nào phù hợp?

**Gợi ý:** 412 Precondition Failed; nếu API đòi precondition mà thiếu, có thể dùng 428.

### Bài 24 — Authorization

Client biết productId và version có đủ quyền sửa Product không?

**Gợi ý:** Không; server vẫn phải kiểm tra principal, tenant và permission.

### Bài 25 — PATCH

Vì sao DTO `ChangePriceCommand` thường an toàn hơn nhận nguyên Product entity từ JSON?

**Gợi ý:** Chỉ nhận field được phép; tránh over-posting, stale full-object merge.

### Bài 26 — Entity-level locking

A sửa giá, B sửa stock trên cùng Product từ cùng version. B có thể conflict dù không sửa chung field nào không?

**Gợi ý:** Có; version bảo vệ cấp entity.

### Bài 27 — OPTIMISTIC

`em.lock(product, LockModeType.OPTIMISTIC)` có bắt buộc tăng version của Product không?

**Gợi ý:** Không; nó yêu cầu optimistic validation.

### Bài 28 — OPTIMISTIC_FORCE_INCREMENT

Khi nào cân nhắc `OPTIMISTIC_FORCE_INCREMENT`?

**Gợi ý:** Muốn nâng version aggregate/root trong một operation được xem là ảnh hưởng concurrency, ngay cả khi không sửa scalar state.

### Bài 29 — Pessimistic

Điểm khác lớn nhất giữa optimistic locking và `PESSIMISTIC_WRITE` là gì?

**Gợi ý:** Phát hiện xung đột khi ghi so với giành/giữ lock trước, có nguy cơ chờ/timeout.

### Bài 30 — Unique insert

Hai users tạo Product mới với SKU giống nhau. @Version có thay UNIQUE constraint không?

**Gợi ý:** Không; chưa có shared row version để kiểm tra uniqueness.

### Bài 31 — Write skew

Hai transactions sửa hai rows riêng, mỗi row có @Version. Một invariant trên cả hai rows có tự được bảo vệ không?

**Gợi ý:** Không mặc định; cần constraint, shared aggregate lock/version hoặc isolation phù hợp.

### Bài 32 — Bulk DML

Vì sao JPQL `UPDATE Product p SET p.stock = 0 WHERE ...` không có cùng automatic version semantics như dirty checking managed Product?

**Gợi ý:** Bulk JPQL bypass per-entity managed update lifecycle.

### Bài 33 — Atomic conditional SQL

Thiết kế điều kiện UPDATE trừ 3 đơn vị với expectedVersion=7 để không trừ stock âm.

**Gợi ý:** Predicate `stock >= 3 AND version = 7`, cập nhật `stock = stock - 3` và `version = version + 1` trong một statement.

### Bài 34 — Bulk affected rows

Một conditional UPDATE trả 0 rows. Có thể khẳng định Product thiếu stock không?

**Gợi ý:** Chưa; có thể sai ID, tenant hoặc expectedVersion.

### Bài 35 — First-level cache

Sau native/bulk UPDATE, một Product đang managed vẫn có stock cũ. Vì sao?

**Gợi ý:** Bulk DML không tự đồng bộ managed state; cần refresh/clear/new context có kiểm soát.

### Bài 36 — Migration

Thêm cột version cho bảng có hàng triệu rows cần cân nhắc những gì?

**Gợi ý:** Backfill, NOT NULL, old writers, rollout, migration locking, schema compatibility và provider mapping.

### Bài 37 — Multi-instance

Hai application instances có cần share một Java synchronized lock để @Version hoạt động không?

**Gợi ý:** Không; DB version predicate bảo vệ cross-instance stale writes khi mọi writers tuân thủ.

### Bài 38 — Idempotency

Client retry POST tạo Order do mất response sau commit. @Version có bảo đảm không tạo hai Orders không?

**Gợi ý:** Không; cần idempotency key/protocol cho repeated create command.

### Bài 39 — Outbox

Vì sao không nên gửi email trong transaction trước khi chắc chắn update Product đã commit?

**Gợi ý:** Email không rollback được. Ghi outbox cùng DB transaction và gửi sau commit qua publisher.

### Bài 40 — Thiết kế tổng hợp

Thiết kế API giữ hàng cho nhiều tenants với Product(version, stock), có transaction, retry, HTTP expectedVersion, idempotency và outbox. Hãy trình bày:

1. Entity và cột `@Version`.
2. Điều kiện nghiệp vụ stock không âm.
3. Repository query luôn lọc tenant/authorization.
4. Ranh giới transaction cho mỗi attempt.
5. Cách phát hiện/rollback optimistic conflict.
6. Khi nào retry và khi nào báo 409/412.
7. Cách không trừ stock hai lần khi client retry.
8. Outbox event sau commit.
9. Test hai EntityManagers.
10. Test concurrency cao và metrics.

**Gợi ý:** Ưu tiên một command có ý nghĩa nghiệp vụ, reload trên transaction mới, giới hạn số retry và kiểm chứng DB state bằng context độc lập.

## 85. Bảng ghi nhớ nhanh

| Khái niệm | Điểm cần nhớ |
| --- | --- |
| Lost update | Ghi sau ghi đè state của người ghi trước |
| Optimistic locking | Phát hiện stale data khi cập nhật |
| `@Version` | Provider quản lý concurrency token |
| Numeric version | Dễ quan sát và so sánh khi lab |
| Two EntityManagers | Tạo hai persistence contexts độc lập |
| Same EntityManager `find()` | Thường trả cùng managed instance |
| SQL version predicate | `WHERE id=? AND version=?` |
| Affected rows = 0 | Có thể biểu thị stale version trong managed update |
| `flush()` | Đồng bộ SQL, không phải commit |
| Commit | Xác nhận DB transaction |
| `OptimisticLockException` | Báo stale optimistic state |
| `RollbackException` | Có thể bọc lỗi phát sinh ở commit |
| Failed persistence context | Không dùng để tiếp tục retry |
| Retry | Transaction mới, reload/re-evaluate |
| Absolute set command | Có thể cần user resolve conflict |
| Relative business command | Có thể retry khi recheck invariants |
| Stock không âm | Domain invariant + DB protocol |
| expectedVersion | Chặn stale HTTP form |
| ETag / If-Match | HTTP conditional update |
| HTTP 412 | If-Match không thỏa |
| HTTP 409 | Business/concurrency conflict theo API |
| HTTP 428 | Server yêu cầu precondition |
| `OPTIMISTIC` | Xác minh optimistic state theo lock semantics |
| `OPTIMISTIC_FORCE_INCREMENT` | Yêu cầu tăng version |
| `PESSIMISTIC_WRITE` | Khóa bi quan, có chờ/timeout |
| Entity-level version | Hai fields khác nhau vẫn có thể conflict |
| UNIQUE constraint | Bảo vệ business key khi insert |
| Write skew | @Version mỗi row không đủ cho mọi invariant nhiều rows |
| Bulk JPQL DML | Có thể bypass @Version/callbacks |
| Native SQL | Tự thiết kế check/update version |
| Atomic conditional UPDATE | Đồng bộ kiểm tra điều kiện và ghi |
| L1 cache | Có thể stale sau bulk update |
| Database isolation | Có thể phát sinh serialization errors |
| Two-thread test | Dùng latches, timeout và EM riêng |
| Spring TransactionTemplate | Tạo transaction riêng cho mỗi retry attempt |
| Idempotency | Ngăn duplicate logical request |
| Outbox | Giữ event intent atomic cùng DB state |
| Hot row | Cần đo conflict rate và cân nhắc chiến lược khác |
| Read-back mới | Xác minh kết quả committed sau conflict |

## 86. Kết luận

Trong bài thực hành này, chúng ta đã tạo entity `Product` có `@Version`, chủ động cho hai `EntityManager` đọc cùng một bản ghi ở cùng phiên bản, để transaction A ghi và commit trước rồi quan sát transaction B bị từ chối khi cố cập nhật bằng version cũ. Bằng cách đọc lại dữ liệu qua một persistence context mới, ta xác minh **thay đổi của A không bị B ghi đè âm thầm**.

**Optimistic locking là cơ chế phát hiện xung đột, không phải cơ chế tự giải quyết mọi khác biệt nghiệp vụ.** Sau conflict, transaction thất bại cần rollback và kết thúc. Application có thể báo người dùng xem lại dữ liệu, hoặc retry có giới hạn trong transaction mới nếu command đủ rõ và có thể tính lại an toàn. Retry phải tải lại state và kiểm tra lại rules như tồn kho không âm; không được cố ghi một giá trị tuyệt đối cũ lên dữ liệu mới.

Trong hệ thống web, còn cần bảo vệ khoảng thời gian dài giữa lúc người dùng GET dữ liệu và lúc họ gửi POST/PATCH. `@Version` ở transaction POST không tự phát hiện “form đã cũ” nếu service đọc version mới rồi bỏ qua version mà client từng thấy. Dùng **expectedVersion hoặc ETag/If-Match** để xác định điều kiện cập nhật, và vẫn giữ @Version để chống race giữa precheck và commit.

Khi mở rộng ứng dụng, cần nhớ `@Version` thường bảo vệ ở cấp entity; nó không thay **UNIQUE constraints, invariants nhiều rows, idempotency hay transaction/outbox policy**. Bulk JPQL và native SQL có thể bypass per-entity version check, vì vậy mọi đường ghi phải tuân thủ một concurrency contract thống nhất. Nếu một row quá nóng và conflict/retry liên tục, hãy đánh giá atomic conditional SQL, queueing, pessimistic locking hoặc điều chỉnh aggregate design.

Nguyên tắc cuối cùng của bài lab: **đọc cùng phiên bản để tái hiện xung đột; kiểm tra version khi ghi; rollback attempt stale; đọc lại trạng thái committed; và chỉ retry khi business command có thể áp dụng lại một cách an toàn trên dữ liệu mới nhất.**









