# Dùng flush và clear để tránh chỉ kiểm tra dữ liệu trong bộ nhớ

Trong **Jakarta Persistence (JPA)**, một bài kiểm thử có thể chạy xanh dù mapping thực tế chưa được kiểm chứng đúng. Nguyên nhân rất thường gặp là **persistence context** (bộ nhớ quản lý entity của `EntityManager`): khi test vừa lưu một entity rồi tìm lại entity đó trong **cùng** `EntityManager`, JPA có thể trả chính object đang được quản lý mà không cần đọc lại dữ liệu bằng SQL.

Hãy xem đoạn test:

```java
Product product = new Product("KB-101", "Keyboard");

em.persist(product);

Product loaded = em.find(
    Product.class,
    product.getId()
);

assertEquals("Keyboard", loaded.getName());
```

Test này có thể thành công vì `loaded` chính là `product` đang nằm trong **first-level cache (L1)**, ngay cả khi câu lệnh INSERT chưa được thực thi. Với một số cơ chế sinh khóa như `IDENTITY`, INSERT có thể chạy sớm, nhưng việc `find()` trả entity đang managed **vẫn không chứng minh** mapping đọc lại từ database hoạt động.

Kỹ thuật kiểm thử phổ biến để làm lộ các vấn đề như vậy là:

```java
em.persist(product);
em.flush();        // Buộc đồng bộ thay đổi đang chờ xuống DB.
Long id = product.getId();

em.clear();        // Xóa managed entities khỏi persistence context.

Product reloaded = em.find(Product.class, id);
assertEquals("Keyboard", reloaded.getName());
```

> **Ý quan trọng nhất:** `flush()` giúp buộc JPA gửi những thay đổi đang chờ xuống database theo transaction hiện tại; `clear()` loại bỏ các managed entities khỏi persistence context để lần truy vấn sau không chỉ lấy lại chính instance cũ từ L1. Tuy nhiên, **flush không phải commit**, và **clear không tự buộc đọc vật lý từ database nếu shared cache/L2 còn hoạt động**.

Bài này nằm trong chương **Kiểm thử JPA** của module **Data Persistence Relational Access ORM JPA**. Ta sẽ phân biệt `persist`, `flush`, `clear`, `commit` và `refresh`, dựng integration tests với JUnit và Spring Data JPA, kiểm tra quan hệ, database constraints, SQL sinh bởi provider, data consistency và cách tránh các “test xanh giả” do cache hoặc transaction.

---

## 1. Mục tiêu của bài kiểm thử JPA

Một unit test của class Java bình thường có thể xác nhận:

```java
Product product = new Product("KB-101", "Keyboard");

assertEquals("KB-101", product.getSku());
assertEquals("Keyboard", product.getName());
```

Nhưng nó **không xác nhận**:

- `@Entity` đã được provider nhận diện.
- `@Table` ánh xạ đúng tên bảng.
- `@Column` ánh xạ đúng tên, kiểu và độ dài.
- `@Id`/`@GeneratedValue` hoạt động với database đang dùng.
- Dữ liệu đã được INSERT hay UPDATE.
- Database có các constraints cần thiết.
- Quan hệ `@ManyToOne` lưu đúng cột foreign key.
- Quan hệ `@OneToMany` đọc lại được từ DB.
- `@Version` phát hiện cập nhật cũ.
- Converter/enum/embedded values round-trip chính xác.
- JPQL/native queries chạy được trên dialect thực tế.

Để kiểm tra những điều đó, cần **integration test có JPA provider và database**, với các ranh giới persistence context và transaction rõ ràng.

### 1.1. Ba cấp độ kiểm thử nên tách biệt

| Cấp độ | Có DB thật? | Xác nhận được gì? |
| --- | --- | --- |
| Unit test domain/POJO | Không | Constructor, getters, business methods, pure validation |
| JPA mapping/integration test | Có | Persist/flush/read mapping, query, FK, constraints, converters |
| Transaction/concurrency test | Có, các transactions độc lập | Commit, rollback, optimistic locking, races, isolation |

`flush()/clear()` đặc biệt hữu ích ở **cấp độ thứ hai**. Đối với kết quả đã commit và concurrency, thường còn cần những transactions hoặc `EntityManager` độc lập.

### 1.2. Sơ đồ một test dễ đánh lừa

```text
Create Product Java object
        |
        v
EntityManager.persist(product)
        |
        v
Persistence context
  id=101 -> Product instance
        |
        v
EntityManager.find(Product.class, 101)
        |
        +---- L1 cache hit ----> same Product instance
        |
        v
Assertion passes
```

Không có gì trong sơ đồ yêu cầu phải SELECT database ở bước `find`.

### 1.3. Sơ đồ test sau flush và clear

```text
Create Product
        |
        v
persist(product)
        |
        v
flush()
        |
        +-- Pending INSERT/UPDATE/DELETE sent to DB
        |   within the current transaction
        |
        v
clear()
        |
        +-- Managed entities detached; L1 emptied
        |
        v
find(Product.class, id)
        |
        +-- No matching managed entity in this L1
        |
        +-- May use L2/shared cache if enabled
        |
        +-- Otherwise SELECT from database
        |
        v
Assert reloaded state
```

Cách test này kiểm chứng đường đọc tốt hơn, nhưng cần **kiểm soát L2 cache** nếu mục tiêu là buộc SQL SELECT thực sự.

## 2. Persistence context là gì?

**Persistence context** là tập hợp các entity instances mà một `EntityManager` quản lý trong một ngữ cảnh nhất định.

Nếu một row có primary key `101` được nạp:

```java
Product first = em.find(Product.class, 101L);
Product second = em.find(Product.class, 101L);

assertSame(first, second);
```

Trong cùng persistence context, JPA duy trì một managed instance ứng với cùng persistent identity. Vì vậy `find` lần sau thường trả object đã managed mà không truy vấn lại DB.

### 2.1. Identity map và L1 cache

```text
PersistenceContext (EntityManager A)
  Product#101  -> Object@ABC
  Product#102  -> Object@DEF
  Category#10  -> Object@GHI
```

JPA dùng trạng thái này để:

- Duy trì identity và quan hệ đối tượng.
- Theo dõi thay đổi (*dirty checking*) khi provider hỗ trợ cơ chế phù hợp.
- Hợp nhất các kết quả query thành một object graph.
- Tránh materialize cùng một entity nhiều lần trong cùng context.
- Quản lý cascade và entity lifecycle.

Đây là chức năng bình thường và hữu ích của JPA, không phải lỗi. Nhưng trong kiểm thử persistence, nó có thể **che đi vấn đề ánh xạ hoặc thiếu SQL**.

### 2.2. Managed entity

Entity đã được `persist` hoặc `find` thành công trong context thường là **managed**.

```java
Product p = em.find(Product.class, 101L);

p.rename("New name");

// Provider có thể đồng bộ UPDATE khi flush/commit.
```

Không cần `em.update(p)`: JPA quản lý state của entity.

### 2.3. Detached entity

Sau `clear()`, entity trước đó không còn được context quản lý.

```java
Product p = em.find(Product.class, 101L);

em.clear();

p.rename("Detached change");
```

Thay đổi trên `p` lúc này **không tự được ghi xuống DB** chỉ vì transaction commit. Cần một thao tác rõ ràng như `merge()` (với semantics của merge) hoặc làm việc trên entity được nạp lại.

### 2.4. Một EntityManager khác có L1 khác

```text
EntityManager A
  Product#101 -> Object@ABC

EntityManager B
  Product#101 -> Object@XYZ
```

Hai persistence contexts không chia sẻ managed instance. Tuy vậy, chúng có thể cùng được phục vụ bởi **shared cache/L2** ở cấp EntityManagerFactory/provider.

## 3. Năm thao tác dễ bị nhầm

| Thao tác | Tác dụng chính | Có nhất thiết commit? | Có xóa L1 không? |
| --- | --- | --- | --- |
| `persist(entity)` | Đưa new entity vào managed state, lập lịch lưu | Không | Không |
| `flush()` | Đồng bộ pending changes với DB trong transaction | **Không** | Không |
| `clear()` | Detach mọi managed entities khỏi context | Không | **Có** |
| `refresh(entity)` | Nạp lại state của một managed entity từ database theo contract | Không | Không |
| `commit()` | Hoàn tất transaction và làm thay đổi durable nếu thành công | **Có** | Không đồng nghĩa gọi `clear()` |

Một số hành vi phụ thuộc transaction, ID strategy, flush mode, cache, locking và provider. Bảng nêu **mục tiêu của API**, không phải số SQL cố định.

### 3.1. persist không tương đương INSERT ngay

```java
em.persist(product);
```

JPA có thể trì hoãn INSERT đến flush/commit, hoặc chạy sớm hơn để lấy generated ID. Ví dụ với `GenerationType.IDENTITY`, provider thường cần thực hiện INSERT sớm để nhận khóa sinh bởi DB.

Không thiết kế test dựa trên giả định “persist luôn chưa có SQL”.

### 3.2. flush không tương đương commit

```java
tx.begin();

em.persist(product);
em.flush();

tx.rollback();
```

Provider đã có thể gửi INSERT xuống database, nhưng transaction bị rollback thì dữ liệu **không trở thành committed record**.

### 3.3. clear không tự gọi flush

```java
product.rename("Changed");

em.clear();
```

Nếu thay đổi chỉ nằm trong managed entity, chưa được flush, `clear()` có thể làm mất pending update đó khỏi ngữ cảnh quản lý.

**Bởi vậy test round-trip nên dùng thứ tự `flush()` rồi `clear()`.**

### 3.4. clear khác close

`clear()` bỏ managed state nhưng `EntityManager` vẫn còn mở. `close()` kết thúc EntityManager và những resources liên quan theo contract; không nên tiếp tục sử dụng một `EntityManager` đã đóng.

### 3.5. refresh không giống clear

`refresh(p)` có ý nghĩa nạp lại state cho **p đang managed**, còn `clear()` detach **tất cả**. `refresh()` không dùng được trên một entity đã detached theo cách thông thường.

## 4. Một entity đơn giản để kiểm thử

Giả sử entity `Product` dùng:

```java
package com.example.catalog;

import jakarta.persistence.*;

@Entity
@Table(
    name = "products",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_product_sku",
        columnNames = "sku"
    )
)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(
        name = "sku",
        nullable = false,
        length = 50
    )
    private String sku;

    @Column(
        name = "name",
        nullable = false,
        length = 160
    )
    private String name;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected Product() {
        // JPA constructor.
    }

    public Product(String sku, String name) {
        this.sku = sku;
        this.name = name;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public Long getVersion() { return version; }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException(
                "Product name must not be blank"
            );
        }
        this.name = newName;
    }
}
```

### 4.1. Giả định về schema

Database được chuẩn bị bằng migration tương thích, ví dụ (DDL minh họa gần PostgreSQL):

```sql
CREATE SEQUENCE product_seq START WITH 1;

CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(50) NOT NULL,
    name VARCHAR(160) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT uq_product_sku UNIQUE (sku)
);
```

Tên sequence mà provider mong đợi với `GenerationType.SEQUENCE` **không được cố định chỉ bởi annotation trên**. Dự án thực tế nên khai báo `@SequenceGenerator` có `sequenceName` rõ ràng và đồng bộ migrations; hoặc để test schema generation tạo sequence tương ứng.

Để tránh nhầm trong ví dụ, nếu dùng database migration `product_seq`, ta có thể khai báo cụ thể:

```java
@Id
@SequenceGenerator(
    name = "product_id_gen",
    sequenceName = "product_seq",
    allocationSize = 1
)
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "product_id_gen"
)
private Long id;
```

Thay trường `id` trong entity theo đoạn trên khi chạy với DDL minh họa. Ở phần còn lại, mục tiêu là **round-trip state**, không phụ thuộc vào cú pháp generation cụ thể.

### 4.2. Vì sao dùng SEQUENCE trong ví dụ?

`SEQUENCE` giúp dễ thấy sự khác nhau giữa “đã được cấp ID” và “đã INSERT row”. Provider có thể lấy sequence value khi `persist` mà chưa INSERT Product row cho tới flush.

Nhưng **không suy rằng mọi provider/DB sẽ trì hoãn INSERT giống nhau**. Test bền vững cần gọi `flush()` rõ ràng.

### 4.3. Schema thực là một phần của test

Nếu migrations tạo bảng tên `catalog_products` nhưng `@Table(name="products")`, bài kiểm thử mapping phải phát hiện được sự không khớp. Test chỉ instantiate Java Product không thể phát hiện lỗi đó.

## 5. Test yếu: chỉ kiểm tra object trong bộ nhớ

```java
@Test
void weakPersistTest() {
    Product product = new Product("KB-101", "Keyboard");

    em.persist(product);

    Product loaded = em.find(
        Product.class,
        product.getId()
    );

    assertNotNull(loaded);
    assertEquals("Keyboard", loaded.getName());
}
```

### 5.1. Vì sao test này có thể xanh giả?

Sau `persist()`, `product` thường đã managed. `em.find()` có thể trả chính instance đó.

Ta chưa xác nhận:

- INSERT đã xảy ra.
- Các constraints đã được kiểm tra.
- Giá trị đã round-trip qua database/JDBC.
- Cột `name` được ánh xạ đúng.
- Query đọc thực sự chạy.
- Một EntityManager mới có thể thấy dữ liệu.

### 5.2. assertSame còn làm lộ bản chất

```java
assertSame(product, loaded);
```

Trong cùng persistence context, điều này là hành vi thường có chủ đích theo identity map. Nó xác nhận JPA identity semantics, **không xác nhận database persistence**.

### 5.3. Test vẫn có giá trị không?

Có, nếu mục tiêu cụ thể là kiểm tra identity map hoặc lifecycle của managed entities. Vấn đề là **đặt tên sai mục tiêu**, ví dụ gọi đó là “verify database insert succeeded” khi chưa kiểm chứng storage.

## 6. Mẫu tốt: persist → flush → clear → find

```java
@Test
void shouldReloadPersistedProduct() {
    Product product =
        new Product("KB-101", "Keyboard");

    em.persist(product);
    em.flush();

    Long id = product.getId();

    em.clear();

    Product reloaded = em.find(Product.class, id);

    assertNotNull(reloaded);
    assertNotSame(product, reloaded);
    assertEquals("KB-101", reloaded.getSku());
    assertEquals("Keyboard", reloaded.getName());
}
```

Đoạn ví dụ giả định test đã có `EntityManager` và transaction phù hợp.

### 6.1. Ý nghĩa từng bước

**Bước 1 — `persist`:** đặt Product mới trong persistence context, yêu cầu lưu khi đồng bộ.

**Bước 2 — `flush`:** đồng bộ pending INSERT với database theo transaction. Nếu constraint không thỏa ở thời điểm DB kiểm tra, có thể ném exception.

**Bước 3 — lưu ID:** giữ khóa để có thể `find` sau khi detach entity.

**Bước 4 — `clear`:** loại toàn bộ managed objects khỏi L1.

**Bước 5 — `find`:** provider phải giải quyết Product#id như một entity chưa có trong L1, thông qua cache chia sẻ hoặc database.

**Bước 6 — assertions:** so sánh những giá trị được đọc sau khi loại managed state cũ.

### 6.2. Vì sao assertNotSame hữu ích?

`assertNotSame(product, reloaded)` cho thấy ta không chỉ nhận lại cùng Java reference cũ trong persistence context.

Nhưng lưu ý: nó **không đủ để chứng minh JDBC SELECT xảy ra**, vì L2 cache có thể cung cấp state cho một instance mới.

### 6.3. Giá trị ID không chứng minh insert

`product.getId() != null` sau persist có thể chỉ chứng minh ID generator đã cấp ID. Không dùng nó làm assertion duy nhất cho câu “đã lưu DB thành công”.

## 7. Một integration test JUnit 5 có transaction rõ ràng

Ví dụ dưới đây dùng JPA Java SE với `RESOURCE_LOCAL` và `EntityManagerFactory`. Runtime cần có:

- JPA provider.
- `persistence.xml`/mapping.
- JDBC connection/datasource.
- Database test và schema tương thích.
- JUnit Jupiter.

```java
package com.example.catalog;

import jakarta.persistence.*;
import org.junit.jupiter.api.*;

import static org.junit.jupiter.api.Assertions.*;

class ProductJpaTest {

    private static EntityManagerFactory emf;

    @BeforeAll
    static void openFactory() {
        emf = Persistence.createEntityManagerFactory(
            "catalogTestPU"
        );
    }

    @AfterAll
    static void closeFactory() {
        if (emf != null) {
            emf.close();
        }
    }

    @Test
    void persistFlushClearThenReload() {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            Product product = new Product(
                "KB-441-01",
                "Mechanical Keyboard"
            );

            em.persist(product);
            em.flush();

            Long id = product.getId();
            assertNotNull(id);

            em.clear();

            Product reloaded =
                em.find(Product.class, id);

            assertNotNull(reloaded);
            assertNotSame(product, reloaded);
            assertEquals(
                "KB-441-01",
                reloaded.getSku()
            );
            assertEquals(
                "Mechanical Keyboard",
                reloaded.getName()
            );

            // Test data is rolled back.
            tx.rollback();
        } finally {
            if (tx.isActive()) {
                tx.rollback();
            }
            em.close();
        }
    }
}
```

### 7.1. Điều test trên chứng minh

Trong transaction test, JPA đã đồng bộ state, giải quyết một entity chưa có trong L1 và trả các giá trị phù hợp mapping.

### 7.2. Điều test chưa chứng minh

Vì transaction **rollback**, nó không chứng minh dữ liệu đã commit bền vững để transaction khác nhìn thấy.

Ngoài ra nếu L2 cache bật, `find()` sau clear vẫn có thể đọc từ shared cache. Cần test riêng nếu mục tiêu là database round-trip thực sự và commit visibility.

### 7.3. Cần cô lập dữ liệu test

Một test suite dùng SKU cố định `KB-441-01` có thể bị trùng khi chạy song song hoặc khi dữ liệu fixture còn tồn tại. Có thể dùng transaction rollback, database riêng cho test, hoặc tạo key duy nhất có kiểm soát.

Không nên cho những test cần kiểm chứng DB schema chạy trên production database.

## 8. Flush không phải commit: hai mức kết luận khác nhau

Đây là phân biệt quan trọng nhất của toàn bài.

### 8.1. Test trong cùng transaction

```text
Transaction T1
  persist Product
  flush
  clear
  find Product
  assert state
  rollback
```

T1 có thể đọc những thay đổi chưa commit do chính nó thực hiện. Khi rollback, row không tồn tại bền vững.

### 8.2. Test sau commit bằng một EntityManager mới

```text
Transaction T1
  persist Product
  flush
  commit
       |
       v
Transaction T2
  new EntityManager
  find Product
  assert state
```

Cách thứ hai kiểm chứng mạnh hơn về **commit và khả năng đọc sau commit**.

### 8.3. Java SE test qua hai EntityManagers

```java
Long id;

// Transaction 1: write and commit.
EntityManager writer = emf.createEntityManager();
EntityTransaction writeTx = writer.getTransaction();

try {
    writeTx.begin();

    Product product = new Product(
        "KB-441-02",
        "Wireless Keyboard"
    );

    writer.persist(product);
    writer.flush();

    id = product.getId();

    writeTx.commit();
} catch (RuntimeException e) {
    if (writeTx.isActive()) {
        writeTx.rollback();
    }
    throw e;
} finally {
    writer.close();
}

// Transaction 2: new persistence context.
EntityManager reader = emf.createEntityManager();

try {
    Product reloaded = reader.find(
        Product.class,
        id
    );

    assertNotNull(reloaded);
    assertEquals(
        "Wireless Keyboard",
        reloaded.getName()
    );
} finally {
    reader.close();
}

// Cleanup should run in a separate controlled transaction.
```

### 8.4. Vì sao cần transaction riêng khi kiểm tra visibility?

Một transaction khác không nhất thiết thấy dữ liệu T1 chưa commit; isolation semantics quyết định điều này. Chỉ sau commit thành công mới có cơ sở kiểm tra visibility giữa transactions theo database contract tương ứng.

### 8.5. Không bỏ quên cleanup

Test dùng commit thực sẽ để lại dữ liệu nếu không cleanup. Cần:

- Database tạm do test sở hữu.
- Xóa test fixtures trong transaction sau test.
- Reset schema giữa test suites.
- Hoặc dùng container/database instance riêng cho mỗi suite.

Không chọn `@Rollback(false)` hàng loạt chỉ để test “nhìn thấy dữ liệu” rồi làm nhiễm dữ liệu các tests khác.

## 9. Spring Data JPA: @DataJpaTest và flush/clear

Trong Spring Boot, `@DataJpaTest` thường cung cấp một JPA test slice với transaction test rollback mặc định. Ví dụ:

```java
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.junit.jupiter.api.Assertions.*;

@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    EntityManager em;

    @Test
    void shouldPersistAndReload() {
        Product product = new Product(
            "KB-441-03",
            "Compact Keyboard"
        );

        em.persist(product);
        em.flush();

        Long id = product.getId();

        em.clear();

        Product loaded = em.find(
            Product.class,
            id
        );

        assertNotNull(loaded);
        assertNotSame(product, loaded);
        assertEquals(
            "Compact Keyboard",
            loaded.getName()
        );
    }
}
```

Import của `@DataJpaTest`/test infrastructure phụ thuộc Spring Boot version đang dùng; ví dụ minh họa workflow test slice phổ biến. Khi chọn stack khác, dùng cấu hình test JPA tương ứng.

### 9.1. Vì sao @DataJpaTest dễ tạo test xanh giả?

Test thường chạy trong một transaction và EntityManager được inject. Nếu chỉ `save()` rồi `findById()` trong cùng context, L1 có thể trả object cũ.

### 9.2. Rollback mặc định có ý nghĩa gì?

Transaction của test có thể rollback sau khi assertions xong, giúp giảm dữ liệu bẩn cho lần chạy sau. Nhưng do không commit, test chưa chứng minh commit visibility hoặc mọi deferred constraints được kiểm tra ở commit.

### 9.3. saveAndFlush có thay clear không?

Không.

```java
Product saved =
    repository.saveAndFlush(product);

Product reloaded =
    repository.findById(saved.getId()).orElseThrow();
```

`saveAndFlush` có thể làm đồng bộ DML, nhưng `saved` vẫn có thể managed, và `findById` có thể nhận lại cùng instance từ L1.

### 9.4. Mẫu với repository và EntityManager

```java
Product saved = repository.save(product);

repository.flush();

Long id = saved.getId();

em.clear();

Product loaded =
    repository.findById(id).orElseThrow();

assertNotSame(saved, loaded);
assertEquals(saved.getSku(), loaded.getSku());
```

Mục tiêu của `flush()` và `clear()` không bị thay đổi vì dùng repository abstraction.

### 9.5. Có cần @Transactional trên mọi test?

Không phải mọi test có cùng nhu cầu. `@DataJpaTest` thường transactional theo thiết lập mặc định, nhưng các tests commit visibility và transaction propagation cần thiết kế khác, có thể sử dụng `TransactionTemplate` hoặc các transactions riêng ngoài outer test transaction.

Đừng tùy tiện mở nested transaction và tưởng nó đã commit độc lập nếu framework propagation `REQUIRED` đang tham gia transaction test hiện hữu.

## 10. Test cập nhật: dirty checking cũng có thể gây xanh giả

Một test yếu:

```java
Product product = em.find(
    Product.class, productId
);

product.rename("Updated name");

Product loaded = em.find(
    Product.class, productId
);

assertEquals("Updated name", loaded.getName());
```

Nếu `loaded == product` thì assertion chỉ chứng minh field Java đã đổi.

### 10.1. Mẫu đúng trong transaction

```java
Product product = em.find(
    Product.class, productId
);

product.rename("Updated name");

em.flush();
em.clear();

Product loaded = em.find(
    Product.class, productId
);

assertEquals("Updated name", loaded.getName());
```

### 10.2. Điều gì có thể bị phát hiện?

- Tên column UPDATE sai.
- SQL UPDATE không chạy vì state không được map/persist đúng.
- DB constraint từ chối giá trị mới.
- Converter xử lý sai.
- Version column được cập nhật không như kỳ vọng.
- Query đọc mới trả dữ liệu không khớp.

### 10.3. Đừng dùng chính entity detached cũ làm oracle

Sau `clear()`, thay vì chỉ assert:

```java
assertEquals("Updated name", product.getName());
```

phải assert trên **instance được nạp lại**:

```java
assertEquals("Updated name", loaded.getName());
```

### 10.4. Test update sau commit còn mạnh hơn

Nếu muốn xác nhận một client/transaction khác thấy thay đổi, commit và mở persistence context khác. `flush()/clear()` trong cùng transaction chưa kiểm tra được visibility sau commit.

## 11. Test remove và orphanRemoval

Một test yếu:

```java
em.remove(product);
assertFalse(em.contains(product));
```

Nó chỉ xác nhận entity không còn managed theo mục tiêu test tại thời điểm đó, chưa chắc chứng minh DELETE database thành công.

### 11.1. Test xóa với flush/clear

```java
Product product = em.find(
    Product.class, productId
);

em.remove(product);
em.flush();
em.clear();

Product loaded = em.find(
    Product.class, productId
);

assertNull(loaded);
```

### 11.2. FK có thể chặn xóa

Nếu Product đang được tham chiếu bởi OrderLine và FK ngăn xóa, exception có thể xảy ra lúc flush hoặc commit. Điều này là một kết quả kiểm thử integrity quan trọng.

### 11.3. orphanRemoval cần kiểm tra child row

Giả sử:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

Sau khi remove một line khỏi collection qua domain method, test phải:

1. `flush()`.
2. `clear()`.
3. Tìm child theo ID hoặc query bảng liên quan.
4. Xác nhận child đã bị xóa theo mapping/transaction dự kiến.

Chỉ kiểm tra `order.getLines().size()` trước flush có thể phản ánh danh sách Java mà không kiểm chứng DB DELETE.

### 11.4. Chú ý owning side

Với `@OneToMany(mappedBy="order")`, `OrderLine.order` là owning side. Nếu helper chỉ thêm child vào collection mà không set `child.order`, DB FK có thể vẫn null/sai.

Kiểm thử round-trip bằng `flush()/clear()` giúp lộ mapping relationship và helper chưa đồng bộ hai phía.

## 12. Kiểm thử quan hệ hai chiều bằng round-trip

Mô hình:

```java
@Entity
class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public void addLine(OrderLine line) {
        lines.add(line);
        line.assignOrder(this);
    }

    public List<OrderLine> getLines() { return lines; }
}
```

Phía con:

```java
@Entity
class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    protected OrderLine() {}

    public void assignOrder(PurchaseOrder order) {
        this.order = order;
    }

    public PurchaseOrder getOrder() { return order; }
}
```

Các phần accessor/constructors còn lại phục vụ fixture có thể thêm theo nhu cầu.

### 12.1. Test không đủ

```java
order.getLines().add(line);

assertEquals(1, order.getLines().size());
```

Nó chỉ kiểm tra collection Java.

### 12.2. Test đúng ý đồ

```java
order.addLine(line);
em.persist(order);

em.flush();

Long orderId = order.getId();
Long lineId = line.getId();

em.clear();

OrderLine loadedLine =
    em.find(OrderLine.class, lineId);

assertNotNull(loadedLine);
assertEquals(
    orderId,
    loadedLine.getOrder().getId()
);
```

Nếu owner side không được set, `NOT NULL`/FK có thể khiến flush thất bại; đó là một tín hiệu hữu ích thay vì để test xanh dựa trên collection.

### 12.3. Không có cascade thì sao?

Nếu mapping không có `CascadeType.PERSIST`, `em.persist(order)` không mặc nhiên persist line mới. Test phải quản lý lifecycle rõ ràng; thêm `flush()/clear()` giúp phát hiện thiếu cascade hoặc việc gán reference chưa phù hợp.

### 12.4. Không tự dùng CascadeType.ALL để sửa test

Cascade mô tả lifecycle ownership, không phải công tắc “lưu cho khỏi lỗi”. Với shared entities như Product, cascade REMOVE có thể nguy hiểm.

## 13. Kiểm tra database constraints đúng thời điểm

Giả sử `Product.sku` unique trong database.

Test:

```java
Product first = new Product(
    "DUP-01", "First"
);

Product second = new Product(
    "DUP-01", "Second"
);

em.persist(first);
em.persist(second);

// Không đủ nếu test không thực thi DML.
```

Một negative integration test thường phải kích hoạt thao tác DB:

```java
assertThrows(
    PersistenceException.class,
    () -> em.flush()
);
```

### 13.1. Vì sao không thể chỉ assert flush luôn ném?

Một số constraints có thể **được trì hoãn đến commit**, tùy DBMS và cách định nghĩa. Flush có thể chạy SQL mà chưa thất bại.

Bởi vậy test cần dựa trên contract của constraint:

- **Immediate constraint**: thường phát hiện tại SQL/flush.
- **Deferred constraint**: có thể phát hiện tại commit.
- **Application/Bean Validation**: có thể ném trước SQL.
- **Provider-specific behavior**: exception type/wrapping có thể khác.

### 13.2. Không chỉ dựa vào annotations

`@Column(unique=true)` là metadata, không đảm bảo production schema thực sự có UNIQUE constraint nếu database được tạo bằng migrations.

Integration test nên chạy **migrations thật** và xác nhận constraint.

### 13.3. Transaction đã lỗi cần rollback

Sau `PersistenceException` ở flush, không nên tiếp tục sử dụng transaction để tạo thêm records rồi mong commit bình thường. Thường phải rollback và đóng/khởi tạo lại context theo framework.

### 13.4. Exception type không hoàn toàn portable

Một provider có thể wrap lỗi constraint thành `PersistenceException` hoặc exception cụ thể; Spring có thể translate thành `DataIntegrityViolationException`. Test nên chọn mức abstraction tương ứng, đồng thời xác nhận bản chất lỗi khi cần.

### 13.5. Một test âm nên độc lập

Không dùng cùng transaction cho nhiều tình huống constraint failure rồi tiếp tục assertions sau lỗi. Mỗi tình huống nên chạy trong transaction riêng để tránh trạng thái rollback-only ảnh hưởng kết quả.

## 14. NOT NULL, độ dài và precision/scale

Một entity có:

```java
@Column(nullable = false, length = 50)
private String sku;
```

Nhưng những điều cần phân biệt:

- JPA metadata có thể được dùng khi tạo schema.
- Bean Validation có các annotations như `@NotNull`, `@Size`.
- Database đã triển khai `NOT NULL` và kiểu `VARCHAR(50)` hay chưa?
- DBMS xử lý chuỗi vượt độ dài như thế nào?

### 14.1. Test mapping storage

```java
Product p = new Product("SKU-ABC", "Keyboard");

em.persist(p);
em.flush();
Long id = p.getId();
em.clear();

Product loaded = em.find(Product.class, id);

assertEquals("SKU-ABC", loaded.getSku());
```

### 14.2. Test constraint

Thử lưu SKU null hoặc vượt giới hạn trên database có migration tương ứng và buộc SQL/commit. Không chỉ assert Java constructor hoặc Bean Validation nếu mục tiêu là **database constraint**.

### 14.3. BigDecimal và scale

Ví dụ:

```java
@Column(
    name = "unit_price",
    precision = 14,
    scale = 2
)
private BigDecimal unitPrice;
```

Khi round-trip, nên kiểm tra giá trị được lưu/đọc lại theo chính sách rounding/database type; không chỉ so sánh object vừa gán trong memory.

### 14.4. @Enumerated và converters

Một trường enum:

```java
@Enumerated(EnumType.STRING)
private ProductStatus status;
```

cần được kiểm tra bằng một lần load mới sau flush/clear hoặc transaction mới để xác nhận dữ liệu được chuyển đúng. Tương tự `AttributeConverter` có thể có sai sót serialize/deserialize mà test chỉ đọc object managed cũ không phát hiện.

## 15. Query có thể tự flush: đừng dựa vào tình cờ

JPA có `FlushModeType.AUTO` và `FlushModeType.COMMIT`.

```java
em.setFlushMode(FlushModeType.AUTO);
```

### 15.1. AUTO

Trong transaction, provider có nghĩa vụ bảo đảm những thay đổi có khả năng ảnh hưởng kết quả query được xử lý theo semantics của flush mode AUTO. Nó có thể thực hiện flush trước query hoặc dùng cơ chế khác để đảm bảo kết quả nhất quán.

Vì vậy đôi khi test:

```java
em.persist(product);

List<Product> found = em.createQuery(
    "SELECT p FROM Product p",
    Product.class
).getResultList();
```

có thể kích hoạt INSERT dù test không gọi `flush` rõ ràng.

### 15.2. COMMIT

Với `FlushModeType.COMMIT`, ảnh hưởng của những thay đổi chưa flush tới kết quả query trước commit không được xác định đầy đủ theo cùng cách như AUTO. Không dùng nó để dựng test dựa trên một thứ tự SQL ngầm định.

### 15.3. Vì sao gọi flush rõ ràng trong test?

Vì nó:

- Thể hiện rõ điểm muốn thực hiện SQL.
- Giảm phụ thuộc vào việc query nào tự flush.
- Khiến lỗi DB constraints xuất hiện gần thao tác đang kiểm tra hơn.
- Giúp phân biệt test mapping với test flush mode.

### 15.4. Flush trước query không có nghĩa đã commit

Ngay cả khi query AUTO đã làm INSERT, transaction vẫn có thể rollback toàn bộ.

## 16. IDENTITY, SEQUENCE và lúc INSERT xảy ra

Thời điểm sinh ID dễ làm những test “persist chưa ghi DB” trở nên không ổn định.

### 16.1. IDENTITY

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Một số providers cần INSERT sớm để lấy ID từ database. Khi đó SQL có thể chạy trong lúc `persist`, không đợi explicit `flush`.

### 16.2. SEQUENCE

```java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE)
private Long id;
```

Provider có thể cấp ID từ sequence trước INSERT. `getId() != null` không chứng minh INSERT đã xảy ra.

### 16.3. UUID/gán ID thủ công

Nếu entity được gán ID trước khi persist, khóa có thể đã tồn tại trong Java từ lâu. Càng không thể dùng ID non-null làm storage assertion.

### 16.4. Lời khuyên kiểm thử

Đừng assert số SQL xảy ra **trước flush** trừ khi mục tiêu test chính là kiểm chứng một behavior có tài liệu của provider/ID strategy. Với test mapping thông thường, gọi explicit `flush` rồi xác nhận round-trip.

## 17. clear có thể làm mất thay đổi chưa flush

Một test minh họa nguy cơ:

```java
Product product = em.find(
    Product.class, productId
);

product.rename("Pending name");

em.clear();

Product loaded = em.find(
    Product.class, productId
);
```

Không có explicit flush. Nếu update chưa được provider đồng bộ ở thời điểm `clear()`, thay đổi `Pending name` không được DB lưu.

### 17.1. Đừng dùng clear như một cách “tự lưu”

`clear()` không gọi `persist`, `merge` hay `flush` cho detached state.

### 17.2. Khi nào điều này gây bug thật?

Một service làm:

```java
product.rename("New");
em.clear();
tx.commit();
```

có thể làm mất thay đổi vì entity đã detached trước khi dirty checking flush.

### 17.3. Cần ghi rõ chủ đích

- Nếu muốn **test persistence**: `flush(); clear(); reload()`.
- Nếu muốn **test discard pending changes**: đổi field, `clear()` trước flush, rồi kiểm tra DB còn giá trị cũ (với assumptions về flush mode/provider).
- Nếu muốn **làm sạch context sau bulk**: flush pending changes có chủ đích trước, rồi clear.
- Nếu muốn **chỉ detach một entity**: `detach(entity)` thay vì clear toàn bộ.

### 17.4. Không dùng clear ở transaction đang có nhiều tác vụ

`clear()` detach mọi entity, không chỉ object của test. Trong application code, gọi clear tùy tiện có thể làm các aggregate khác không còn được theo dõi.

## 18. clear, detach, refresh, evict và close

| Cơ chế | Phạm vi | Mục tiêu |
| --- | --- | --- |
| `em.clear()` | Tất cả managed entities trong context | Detach toàn bộ L1 |
| `em.detach(entity)` | Một managed entity và cascade detach theo mapping | Detach chọn lọc |
| `em.refresh(entity)` | Một managed entity và cascade refresh theo mapping | Đồng bộ lại state entity |
| `em.close()` | EntityManager | Kết thúc context/lifecycle |
| `emf.getCache().evict(...)` | Shared cache/L2 | Loại state khỏi shared cache khi supported |
| New `EntityManager` | Context mới | Kiểm tra qua L1 độc lập |

### 18.1. Khi test muốn nạp lại đúng một entity

`em.refresh(product)` có thể hữu ích khi database đã thay đổi và `product` vẫn managed. Nhưng nó không chứng minh hành vi **new entity materialization** giống `clear()+find`.

### 18.2. Khi chỉ muốn detach một entity

```java
em.detach(product);
Product loaded = em.find(Product.class, productId);
```

Có thể đủ nếu không cần loại các managed relations khác. Nhưng nếu related entities vẫn nằm trong L1, một phần object graph vẫn có thể được tái sử dụng.

### 18.3. close và test transaction

Trong container-managed environment, không được tùy tiện đóng injected `EntityManager` như trong Java SE resource-local test. Hãy dùng lifecycle test/framework phù hợp.

## 19. L2 cache: clear chưa chắc buộc SQL SELECT

Sau:

```java
em.flush();
em.clear();

Product loaded =
    em.find(Product.class, productId);
```

lần `find` không còn đọc từ L1 cũ, nhưng provider có thể lấy state từ **shared cache (L2)** và tạo một managed instance mới, mà không cần SQL SELECT.

### 19.1. Khi nào cần quan tâm?

- Test converter/column mapping thực sự đọc từ DB.
- Test dữ liệu bị đổi bởi SQL ngoài JPA.
- Test cache invalidation.
- Test SQL query count.
- Test migration schema tương thích runtime.

### 19.2. Cách đơn giản: tắt shared cache trong persistence unit test

Trong `persistence.xml`:

```xml
<persistence-unit name="catalogTestPU">
    <shared-cache-mode>NONE</shared-cache-mode>
</persistence-unit>
```

Đây là fragment minh họa; production/test persistence unit vẫn cần datasource và mapping đầy đủ.

### 19.3. Bypass cache khi find

JPA có cache retrieval modes chuẩn. Một ví dụ:

```java
Product loaded = em.find(
    Product.class,
    productId,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
```

Với `Map` và `CacheRetrieveMode` imports phù hợp, ý định là không đọc shared cache cho thao tác `find`. `CacheRetrieveMode.BYPASS` không tự bảo đảm xóa mọi provider-specific query cache, DB buffer cache hay SQL plan cache.

### 19.4. Evict shared cache

```java
emf.getCache().evict(
    Product.class,
    productId
);
```

hoặc trong **test cô lập**:

```java
emf.getCache().evictAll();
```

Nhưng evict cache toàn nhà máy session có thể ảnh hưởng các tests chạy song song hoặc production traffic. Không dùng `evictAll()` trong request nghiệp vụ chỉ để chứng minh SELECT xảy ra.

### 19.5. Muốn xác nhận có SQL SELECT?

Dùng JDBC/DataSource instrumentation, SQL logging hoặc DB query observation phù hợp. `assertNotSame` không thể thay một bộ đếm/trace JDBC khi yêu cầu là đo round-trip vật lý.

## 20. Test mapping với native SQL và JPA bulk DML

Một vấn đề khác xuất hiện khi database được sửa **bên ngoài dirty checking của managed entities**.

### 20.1. Native UPDATE

Giả sử:

```java
Product product = em.find(
    Product.class, productId
);

em.createNativeQuery(
    """
    UPDATE products
    SET name = :newName
    WHERE id = :id
    """
)
.setParameter("newName", "Changed by SQL")
.setParameter("id", productId)
.executeUpdate();

assertEquals(
    "Changed by SQL",
    product.getName()
);
```

Assertion cuối có thể **thất bại** vì `product` vẫn giữ state đã nạp trước đó trong L1.

### 20.2. Refresh để kiểm tra SQL update

```java
em.refresh(product);

assertEquals(
    "Changed by SQL",
    product.getName()
);
```

`refresh` có thể đồng bộ lại state của một managed entity sau thay đổi DB phù hợp.

### 20.3. Clear rồi find

```java
em.flush();  // Nếu có pending changes cần giữ.
em.clear();

Product loaded =
    em.find(Product.class, productId);

assertEquals(
    "Changed by SQL",
    loaded.getName()
);
```

Cần kiểm soát shared cache và transaction nếu muốn chắc chắn đọc trạng thái DB mới.

### 20.4. Bulk JPQL update

```java
int changed = em.createQuery(
    """
    UPDATE Product p
    SET p.name = :newName
    WHERE p.id = :id
    """
)
.setParameter("newName", "Bulk changed")
.setParameter("id", productId)
.executeUpdate();
```

JPQL bulk DML **không tự đồng bộ mọi managed entity instances đã có**. `flush()/clear()` sau đó và đọc mới giúp test xác nhận SQL kết quả.

### 20.5. Vì sao phải cân nhắc flush trước bulk?

Nếu context đang có pending changes và một bulk DML chạy, thứ tự update có thể tạo kết quả bất ngờ. Một pattern có chủ đích:

```java
em.flush();

int count = bulkQuery.executeUpdate();

em.clear();
```

Nhưng `clear()` làm detach toàn bộ entities; chỉ dùng khi code/test đã tính đến lifecycle đó.

### 20.6. @Version và bulk update

Bulk JPQL UPDATE không tự bảo đảm optimistic version behavior giống từng managed entity update theo JPA. Nếu test đang xác nhận optimistic locking, cần phân biệt rõ hai đường cập nhật.

## 21. Read-your-writes trong cùng transaction không phải durability

Sau `flush`, transaction đang thực hiện DML thường có thể đọc dữ liệu do chính nó ghi.

```text
T1:
  INSERT Product#101
  FLUSH
  SELECT Product#101 -> thấy row
  ROLLBACK
```

Kết quả SELECT thành công không chứng minh row vẫn tồn tại sau rollback.

### 21.1. Phân biệt hai mục tiêu kiểm thử

**Mục tiêu A — mapping integration test**

- Có thể rollback sau assertions.
- `flush()/clear()` thường đủ để kiểm tra round-trip trong cùng transaction.
- Nên tắt/bypass L2 nếu yêu cầu SQL read.

**Mục tiêu B — committed data test**

- Phải commit T1.
- Đọc từ T2/EntityManager mới.
- Xác nhận row tồn tại trong committed DB state.
- Cleanup/reset DB test sau đó.

### 21.2. Isolation level và concurrent readers

Một transaction khác không nhất thiết nhìn thấy dữ liệu chưa commit. `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE` hoặc DB-specific semantics có thể ảnh hưởng khi và cái gì được nhìn thấy.

Không suy “flush rồi EntityManager khác không thấy => persist sai” khi T1 chưa commit.

### 21.3. Read replica/async replication

Nếu production đọc qua replica, commit trên primary không bảo đảm replica thấy dữ liệu ngay lập tức. Test replication consistency là bài toán khác với JPA `flush()/clear()`.

### 21.4. Test transaction boundaries

Trong Spring, `@Transactional` test method có thể bọc service call; gọi transaction template với `REQUIRED` thường chỉ tham gia transaction hiện có. Nếu muốn kiểm tra commit giữa hai transactions, cần không đặt test trong outer rollback transaction hoặc cấu hình propagation phù hợp.

## 22. Deferred constraints và kiểm tra tại commit

Trong một số DBMS, foreign key/unique constraints có thể được định nghĩa là **deferred**.

```text
T1 begins
  INSERT row potentially violating deferred FK
  flush -> SQL executed; no error yet
  commit -> constraint checked -> transaction fails
```

### 22.1. Kết luận đúng

`flush()` cho biết provider đã đồng bộ pending operations, **không bảo đảm mọi constraint của database đều đã được kiểm tra xong**.

### 22.2. Khi test cần xác nhận constraint

- Biết constraint đang immediate hay deferred.
- Xác minh lỗi ở flush hoặc commit đúng với DB.
- Dùng integration test trên DBMS thực.
- Không giới hạn assertion chỉ tại một điểm nếu semantics cho phép kiểm tra muộn.

### 22.3. Cẩn trọng với trigger side effects

Database triggers có thể chạy khi DML được execute, nhưng transaction rollback vẫn có thể làm mất dữ liệu transactional do trigger ghi. Một số external effects từ trigger/extensions có semantics khác. Không dùng `flush` như một mốc “mọi side effect bền vững”.

## 23. Test optimistic locking cần hai persistence contexts

`@Version` là cơ chế JPA để phát hiện stale managed updates.

```java
@Version
private Long version;
```

### 23.1. Một EntityManager không tạo conflict đúng nghĩa

Nếu hai biến cùng tham chiếu một entity managed trong cùng persistence context:

```java
Product first = em.find(Product.class, id);
Product second = em.find(Product.class, id);

assertSame(first, second);
```

đó không phải hai actors cạnh tranh.

### 23.2. Cần hai EntityManagers

Mô hình kiểm thử:

```text
EM A / Transaction A
  load Product#101 version=4

EM B / Transaction B
  load Product#101 version=4
  change name
  flush + commit -> version=5

EM A
  change name from stale version 4
  flush/commit -> optimistic conflict
```

### 23.3. Khi nào lỗi xuất hiện?

Provider có thể phát hiện optimistic conflict tại `flush` hoặc `commit` tùy hành vi. Test không nên hard-code một điểm phát sinh exception nếu contract cho phép cả hai.

### 23.4. Tại sao clear không đủ?

`clear()` trong một context làm detach instances nhưng **không mô phỏng hai transactions đồng thời**. Test concurrency cần hai contexts/transactions, ranh giới commit và thời điểm đọc/ghi chủ đích.

### 23.5. DB isolation có thể ảnh hưởng test

Một transaction giữ snapshot cũ có thể có behavior khác tùy DBMS isolation, locks và transaction order. Dùng DB test phù hợp production để không có kết luận sai.

## 24. Flush, clear và kiểm thử vòng đời entity

Những trạng thái quan trọng:

```text
NEW (transient)
   |
   | persist()
   v
MANAGED
   |
   | flush()
   v
MANAGED (SQL synchronized, still in L1)
   |
   | clear() / detach() / close()
   v
DETACHED
   |
   | merge()
   v
MANAGED COPY
```

Với remove:

```text
MANAGED
   |
   | remove()
   v
REMOVED
   |
   | flush()
   v
DELETE synchronized with database
   |
   | rollback?
   v
Transaction decides durability
```

### 24.1. merge không làm object detached cũ thành managed

```java
Product detached = ...;

Product managed = em.merge(detached);

assertNotSame(detached, managed);
```

`merge` trả về managed instance mang state đã hợp nhất; object detached truyền vào vẫn detached.

### 24.2. Test merge bằng flush/clear

```java
Product managed = em.merge(detached);

em.flush();

Long id = managed.getId();

em.clear();

Product reloaded =
    em.find(Product.class, id);

assertEquals(
    detached.getName(),
    reloaded.getName()
);
```

Nhưng với detached graph và partial updates, cần test rõ những field nào được phép merge; không dùng arbitrary DTO → entity → merge nếu có nguy cơ mất dữ liệu.

### 24.3. Cascade và merge

Nếu entity graph có children, `CascadeType.MERGE` ảnh hưởng những associations được merge theo lifecycle. `flush()/clear()` giúp phát hiện child state không được lưu như giả định.

## 25. Test Bean Validation so với database validation

Giả sử:

```java
@NotBlank
@Column(name = "name", nullable = false)
private String name;
```

### 25.1. Bean Validation

`@NotBlank` có thể từ chối chuỗi chỉ chứa whitespace khi được validate; JPA có thể tích hợp automatic validation trên lifecycle trong điều kiện phù hợp.

### 25.2. Database constraint

`NOT NULL` từ migration không tự từ chối chuỗi `"   "`. Nếu database cần từ chối những giá trị này, phải có additional constraint/check phù hợp.

### 25.3. Một test cần biết đang kiểm tra lớp nào

**Test Bean Validation:** gọi validator hoặc JPA lifecycle validation trong điều kiện xác định.

**Test database NOT NULL:** bỏ qua/integrate JPA validation theo setup thích hợp hoặc thực hiện JDBC SQL trực tiếp trong một test DB riêng để xác nhận constraint thực.

### 25.4. Flush có thể ném trước JDBC

Nếu Bean Validation tích hợp JPA phát hiện invalid entity trước khi SQL thực thi, `flush` có thể ném exception dù database chưa hề xử lý INSERT/UPDATE.

Vì vậy **`flush ném lỗi` không tự chứng minh database constraint tồn tại**.

### 25.5. Test cả hai lớp nếu cần

Một dự án trưởng thành nên có:

- Unit test domain validation.
- Bean Validation tests.
- Integration test entity mapping.
- Database constraint tests trên schema migrations.
- Concurrency tests cho uniqueness/versioning.

## 26. L1 cache còn che lỗi khi query aggregate không?

Các JPQL scalar/aggregate queries thường cần provider truy vấn database hoặc thực hiện tính toán phù hợp. Ví dụ:

```jpql
SELECT COUNT(p) FROM Product p
```

có thể kích hoạt AUTO flush trước khi trả count.

Nhưng nếu test chỉ dùng count query, nó chưa xác nhận mọi fields được round-trip.

### 26.1. Test COUNT không thay entity reload

```java
em.persist(product);
em.flush();

Long count = em.createQuery(
    "SELECT COUNT(p) FROM Product p",
    Long.class
).getSingleResult();
```

Kết quả count có thể xác nhận row được database nhìn thấy trong transaction, nhưng không chứng minh column `name` map đúng hoặc converter hoạt động như mong đợi.

### 26.2. Test entity reload không thay constraint test

Ngược lại, `flush/clear/find` có thể trả data đúng trên schema thiếu unique constraint. Cần những tests riêng để xác nhận integrity.

### 26.3. Test SQL query explicitly

Nếu mục tiêu là xác nhận DB có row:

```java
Object count = em.createNativeQuery(
    "SELECT COUNT(*) FROM products WHERE id = :id"
)
.setParameter("id", productId)
.getSingleResult();
```

Một scalar native query có thể giúp nhìn database trực tiếp trong cùng transaction, nhưng cần xử lý `Number` type phù hợp DB/provider và không coi nó là bằng chứng commit nếu transaction còn mở.

## 27. Kiểm soát schema để test có ý nghĩa

Một test `flush()/clear()` không thể bảo đảm production schema khớp migration nếu test database được tạo bằng cách khác.

### 27.1. Hai cách tạo test schema

**Hướng A — JPA schema generation trên DB tạm:**

```properties
jakarta.persistence.schema-generation.database.action=drop-and-create
```

Hữu ích để thử mapping có thể tạo bảng.

**Hướng B — chạy migrations giống production:**

```text
Empty test DB
   |
   v
Flyway/Liquibase migrations
   |
   v
JPA database.action=none
   |
   v
Integration tests flush/clear/reload
```

Hướng B chứng minh rõ hơn việc JPA runtime khớp schema thực mà production triển khai.

### 27.2. Không chạy drop-and-create trên DB dùng chung

`drop-and-create` có thể xóa dữ liệu. Chỉ dùng trên database thực sự thuộc test suite, không có dữ liệu cần giữ.

### 27.3. Test trên DBMS gần production

H2 và PostgreSQL có thể khác:

- Identity/sequence.
- Deferred constraints.
- Timestamp/decimal precision.
- SQL dialect.
- Locking.
- FK/unique behavior.
- JSON/array types.
- Case sensitivity.

Với mapping quan trọng, dùng DBMS thật hoặc Testcontainers tương ứng.

### 27.4. SQL logging không thay assertions

Log SQL giúp chẩn đoán nhưng test vẫn phải assert trạng thái và dữ liệu. Một SQL được in ra chưa chứng minh commit thành công.

## 28. Sử dụng Testcontainers cho integration test

Khi cần PostgreSQL gần production, có thể dùng Testcontainers để chạy database tạm cho integration tests.

Mô hình:

```text
JUnit test suite
      |
      v
Start PostgreSQL container
      |
      v
Apply migrations
      |
      v
Create EntityManagerFactory / Spring context
      |
      v
Run flush-clear-reload tests
      |
      v
Rollback/cleanup
      |
      v
Stop container
```

### 28.1. Ví dụ khung JUnit với Testcontainers

```java
@Testcontainers
class ProductDatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    // DataSource/JPA configuration is wired to
    // postgres.getJdbcUrl(), username and password.
    // Apply migrations before running tests.

    @Test
    void persistsThroughDatabase() {
        // Transactional persist/flush/clear/reload test.
    }
}
```

Đây là **khung minh họa**, không phải complete Spring configuration. Cần dependencies và cách inject database URL phù hợp Spring Boot/test infrastructure version; DB image cũng phải phù hợp policy dự án.

### 28.2. Khi nào cần container?

- Entity dùng DB-specific types/functions.
- Foreign key/unique constraints quan trọng.
- Optimistic/pessimistic locking.
- SQL migration contract.
- Provider dialect behavior.
- Native SQL.
- Deferred constraints hoặc DB triggers.

### 28.3. Tốc độ test

Không nhất thiết chạy container cho mọi unit test. Tách fast pure unit tests và JPA integration suites có DB để vừa nhanh vừa đủ tin cậy.

## 29. Test isolation: rollback, cleanup và parallelism

### 29.1. Mỗi test cần dữ liệu độc lập

Hai tests tạo cùng SKU có thể gây unique conflict nếu chạy cùng DB và commits của test trước còn tồn tại.

### 29.2. Rollback là công cụ tốt nhưng có giới hạn

Rollback đảm bảo changes của transaction test không durable, nhưng không mô phỏng toàn bộ transaction commit path.

### 29.3. Những gì rollback không luôn phục hồi?

- Sequence values có thể vẫn được tiêu thụ (tùy DBMS).
- External side effects không transactional.
- Dữ liệu được ghi bởi transaction `REQUIRES_NEW` độc lập có thể đã commit.
- Test jobs bên ngoài transaction có thể không rollback theo test.
- Cache state và một số in-memory effects có thể cần reset riêng.

### 29.4. Chạy song song

Nếu dùng shared EntityManagerFactory/Hibernate Statistics toàn cục, test parallelism có thể trộn SQL counters hoặc chiếm data fixtures.

Chọn database/schema riêng hoặc định danh dữ liệu độc lập khi cần chạy parallel.

### 29.5. Không phụ thuộc ID tăng liên tục

Sequence/IDENTITY có thể tạo gaps khi rollback hoặc concurrent inserts. Test nên assert entity identity và relational correctness, không assert “ID mới chắc chắn bằng ID cũ + 1” trừ khi đó là yêu cầu cụ thể của một generator dưới môi trường kiểm soát.

## 30. Đo SQL để xác nhận test thực sự đọc database

`flush()/clear()` chỉ bảo đảm L1 không trả lại instance managed trước đó. Nếu mục tiêu cụ thể là thấy JDBC SELECT, hãy đo.

### 30.1. Hibernate SQL logging

Với Hibernate 6, cấu hình môi trường test có thể như:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Chỉ bật bind values khi test data không nhạy cảm; tránh log credentials, PII và production bind parameters.

### 30.2. Hibernate Statistics

```java
SessionFactory sessionFactory =
    emf.unwrap(SessionFactory.class);

Statistics stats =
    sessionFactory.getStatistics();
```

Đây là API Hibernate-specific, không phải JPA standard. `getPrepareStatementCount()` hữu ích cho quan sát nhưng không phải luôn bằng số SQL execute calls khi batching/reuse.

### 30.3. JDBC DataSource instrumentation

Để đếm các `executeQuery/executeUpdate/executeBatch` thực sự, có thể dùng datasource proxy hoặc JDBC tracing phù hợp.

### 30.4. Kiểm chứng SQL round-trip

Một test mạnh có thể:

1. Tắt/bypass L2 cache.
2. Persist và flush.
3. Clear L1.
4. Bắt đầu SQL execution counter.
5. Gọi find/query.
6. Assert entity data.
7. Assert một SQL SELECT hoặc pattern phù hợp **nếu số SQL là contract của test**.

Không đưa query count cứng nhắc vào mọi test mapping; SQL shape có thể thay đổi theo provider/version/fetch plan.

## 31. Kiểm tra dữ liệu từ một JDBC Connection khác

Một chiến lược khác để tránh chỉ nhìn ORM cache là đọc bằng JDBC trong transaction phù hợp.

### 31.1. Đọc trong cùng connection/transaction

Nếu lấy được JDBC connection tham gia transaction JPA, scalar SELECT có thể xác nhận row mà JPA vừa flush. Nhưng kết quả vẫn có thể là **uncommitted state của chính transaction**, chưa phải durability.

### 31.2. Đọc bằng connection độc lập

Nếu muốn kiểm tra committed visibility:

1. JPA transaction commit.
2. Lấy connection độc lập sau commit.
3. Query database.
4. Assert dữ liệu.
5. Cleanup test.

### 31.3. Không trộn transaction managers tùy tiện

Một JDBC Connection được mở riêng chưa chắc tham gia cùng transaction với JPA; nếu đọc trước commit có thể không thấy dữ liệu, hoặc tạo lock waits.

### 31.4. Khi nào JDBC assertion phù hợp?

- Xác nhận database-generated columns.
- Kiểm tra triggers/defaults.
- Xác nhận tên cột/format thật.
- Kiểm tra rows tạo bởi association table.
- Kiểm tra DB constraints độc lập với JPA entity lifecycle.

Một test mapping thường vẫn nên dùng `em.clear(); em.find()` để kiểm tra JPA read path; JDBC là phép đo bổ sung theo mục tiêu cụ thể.

## 32. Khi database tự thay đổi giá trị: defaults và triggers

Giả sử database có:

```sql
updated_at TIMESTAMP
    DEFAULT CURRENT_TIMESTAMP
```

hoặc trigger cập nhật `updated_at` khi UPDATE.

### 32.1. Vì sao object Java có thể stale?

Provider có thể không tự cập nhật mọi server-generated column trong managed instance ngay sau DML nếu không được mapping/cấu hình tương ứng.

### 32.2. Test reload

```java
em.persist(entity);
em.flush();
em.clear();

Entity loaded = em.find(
    Entity.class,
    entityId
);
```

Với mapping hợp lệ và cache được kiểm soát, có thể quan sát giá trị sinh bởi database.

### 32.3. refresh cũng hữu ích

Nếu cần giữ một managed instance:

```java
em.flush();
em.refresh(entity);
```

để cập nhật state theo DB; tuy nhiên semantics cụ thể phụ thuộc mapping và provider.

### 32.4. Commit vẫn là mốc riêng

Trigger được thực thi ở thời điểm SQL không đồng nghĩa dữ liệu đã commit bền vững. Đối với tác vụ cần sau commit, test phải có transaction boundary thích hợp.

## 33. Kiểm thử tối ưu và N+1 không chỉ dùng flush/clear

Bài học tập trung vào correctness, nhưng flush/clear cũng giúp tạo điều kiện đo hiệu năng khách quan.

### 33.1. L1 che N+1

Nếu test đã nạp Customer trước, vòng duyệt Orders có thể không phát thêm SELECT; N+1 bị che bởi L1.

### 33.2. Fresh persistence context

Trước khi đo N+1:

```java
em.flush();
em.clear();
```

Sau đó thực thi query và truy cập relationships trong scope đo.

### 33.3. L2 vẫn có thể che query count

Với shared cache, cần test cold/warm separately hoặc bypass/evict cache theo chiến lược đã định nghĩa.

### 33.4. Không gọi clear giữa mọi item để tạo N+1 giả

Nếu test cố `clear()` giữa mỗi Order, pattern được đo không đại diện một request bình thường. Benchmark phải phản ánh workload thực tế.

### 33.5. Các chỉ số bổ sung

- SQL execution count.
- Entity/collection loads.
- Query/JDBC duration.
- Rows returned.
- Heap allocation.
- Cache hit/miss.

`flush()/clear()` là công cụ kiểm soát context, không phải framework đo performance đầy đủ.

## 34. Những sai lầm phổ biến

### Sai lầm 1 — Persist rồi find cùng EntityManager và gọi là DB round-trip

L1 có thể trả object managed.

### Sai lầm 2 — Tưởng flush cũng commit

Flush gửi DML theo transaction; rollback vẫn có thể đảo thay đổi.

### Sai lầm 3 — Tưởng clear tự flush pending changes

Clear detach managed entities, có thể làm pending changes chưa flush bị bỏ.

### Sai lầm 4 — Chỉ assert ID khác null

ID có thể được cấp trước INSERT.

### Sai lầm 5 — Chỉ assert Java getter sau persist

Không chứng minh provider map columns đúng.

### Sai lầm 6 — saveAndFlush rồi findById nhưng không clear

Entity vẫn có thể ở L1.

### Sai lầm 7 — Dùng assertNotSame làm bằng chứng có JDBC SELECT

L2 cache có thể trả state cho instance mới.

### Sai lầm 8 — Đọc bằng EntityManager khác trước khi writer commit

Transaction isolation có thể ngăn thấy uncommitted writes.

### Sai lầm 9 — Dùng rollback test để khẳng định dữ liệu durable

Rollback test chưa chứng minh commit success.

### Sai lầm 10 — Chỉ assert lỗi constraint tại flush

Deferred constraints có thể được kiểm tra ở commit.

### Sai lầm 11 — Coi flush exception là bằng chứng DB NOT NULL đã tồn tại

Bean Validation có thể ném trước SQL.

### Sai lầm 12 — Test schema do JPA tự tạo nhưng production dùng migrations khác

Có thể che mapping/schema drift.

### Sai lầm 13 — Test trên H2 rồi kết luận PostgreSQL constraints giống hệt

Dialect, sequences, types, locking và deferred behavior khác nhau.

### Sai lầm 14 — Kiểm tra collection.size() trước flush

Có thể chỉ phản ánh Java list, không phải quan hệ lưu đúng DB.

### Sai lầm 15 — Quên owning side của quan hệ hai chiều

Thêm child vào inverse collection mà không set FK-owning side có thể không tạo relationship đúng.

### Sai lầm 16 — Tự thêm CascadeType.ALL chỉ để test xanh

Có thể tạo lifecycle semantics sai, đặc biệt với shared entities.

### Sai lầm 17 — Test remove bằng em.contains()

Không chứng minh DELETE DB đã thực hiện.

### Sai lầm 18 — Dùng em.clear() trong service khi còn pending changes khác

Có thể detach mọi entity và bỏ qua dirty changes cần lưu.

### Sai lầm 19 — Thay đổi detached entity rồi kỳ vọng commit tự ghi

Detached state không được dirty checking như managed state.

### Sai lầm 20 — Quên merge trả về managed instance khác

Object input của merge vẫn detached.

### Sai lầm 21 — Bulk JPQL UPDATE rồi assert managed entity cũ

Bulk DML có thể làm L1 stale.

### Sai lầm 22 — Dùng một EntityManager để test optimistic conflict

Không tạo hai actors/versions độc lập.

### Sai lầm 23 — Dựa vào query AUTO flush ngầm để test mapping

Có thể khiến test phụ thuộc query shape/flush mode và khó hiểu.

### Sai lầm 24 — Hard-code SQL count trong mọi test entity

Provider/fetch plan/version có thể thay đổi số statements dù semantics vẫn đúng.

### Sai lầm 25 — Bật L2 cache và không ghi rõ trạng thái cache

Test round-trip có thể không thực sự đọc DB.

### Sai lầm 26 — Gọi evictAll() trong production để “test lạnh”

Ảnh hưởng cache của requests khác và độ trễ hệ thống.

### Sai lầm 27 — Test lỗi FK/UNIQUE rồi tiếp tục cùng transaction đã lỗi

Transaction có thể rollback-only; kết quả tiếp theo không tin cậy.

### Sai lầm 28 — Chạy tests commit data mà không cleanup

Dữ liệu thừa gây xung đột và flaky tests.

### Sai lầm 29 — Giả định sequence numbers luôn liên tục

Rollbacks/concurrency và generator allocation có thể tạo gaps.

### Sai lầm 30 — Test không chạy SQL nào nhưng tuyên bố JPA mapping đã được xác minh

Một pure unit test không thay thế persistence integration test.

## 35. Một quy trình mẫu khi viết JPA integration test

Trước khi viết một test, xác định nó kiểm tra điều gì.

### 35.1. Nếu mục tiêu là mapping round-trip

```text
Arrange:
  create test entity and prerequisite references

Act:
  persist/update/remove
  flush
  clear

Assert:
  find/query again
  compare persisted state
  verify relationships/constraints as needed

Cleanup:
  rollback transaction or reset test DB
```

### 35.2. Nếu mục tiêu là commit visibility

```text
Arrange:
  start with isolated DB fixture

Transaction T1:
  persist
  flush
  commit

Transaction T2:
  new EntityManager
  find/query
  assert committed state

Cleanup:
  independent cleanup transaction
```

### 35.3. Nếu mục tiêu là DB constraint

```text
Arrange:
  migrate schema with constraint

Act:
  perform invalid DML from JPA/JDBC

Assert:
  failure at SQL/flush/commit according to DB semantics
  transaction rollback
  no invalid committed data
```

### 35.4. Nếu mục tiêu là concurrency

```text
Arrange:
  create committed fixture

T1 and T2:
  load state independently
  coordinate updates in controlled order

Assert:
  expected conflict/atomicity/isolation
  committed final state correct
```

### 35.5. Nếu mục tiêu là SQL round-trip

```text
Arrange:
  disable/bypass shared cache
  start relevant JDBC SQL observation

Act:
  flush
  clear
  find/query

Assert:
  values
  observed SQL execution if that is test contract
```

## 36. Bài tập thực hành

### Bài 1 — Phát hiện test xanh giả

```java
Product p = new Product("A", "Mouse");
em.persist(p);

assertEquals(
    "Mouse",
    em.find(Product.class, p.getId()).getName()
);
```

**Hỏi:** Test đã xác nhận database có row chưa?

**Đáp án:** Chưa chắc. `find` có thể trả entity từ L1. Thêm `flush(); clear(); find()` và kiểm soát L2 nếu cần buộc DB SELECT.

### Bài 2 — Flush khác commit

```java
tx.begin();
em.persist(product);
em.flush();
tx.rollback();
```

**Hỏi:** Có chắc product tồn tại sau rollback không?

**Đáp án:** Không. Flush đồng bộ SQL trong transaction, không commit.

### Bài 3 — Clear trước flush

```java
Product p = em.find(Product.class, id);
p.rename("Changed");
em.clear();
tx.commit();
```

**Hỏi:** Giá trị Changed có được lưu không?

**Đáp án:** Không được bảo đảm; pending update có thể bị bỏ khi detach trước flush. Test storage cần flush trước clear.

### Bài 4 — SaveAndFlush

```java
Product p = repository.saveAndFlush(new Product(...));
Product reloaded = repository.findById(p.getId()).orElseThrow();
```

**Hỏi:** Có chắc reloaded là object mới không?

**Đáp án:** Không. Cùng persistence context có thể trả instance managed. Cần clear hoặc context mới.

### Bài 5 — L2 cache

Test `flush/clear/find` pass nhưng không thấy SELECT trong SQL log.

**Đáp án:** Shared cache có thể phục vụ state. Tắt/bypass L2 trong test hoặc dùng JDBC observation phù hợp.

### Bài 6 — Foreign key

Một OrderLine tham chiếu Order chưa tồn tại.

**Hỏi:** Điều gì cần để chứng minh FK của DB đang hoạt động?

**Đáp án:** Dùng schema migration có FK thật, thực hiện DML, kiểm tra lỗi tại flush/commit và transaction rollback; không chỉ test Bean Validation.

### Bài 7 — Relationship owning side

`order.getLines().add(line)`, nhưng `line.order` không set.

**Đáp án:** Java collection có thể đúng nhưng FK sai. Test `flush/clear` và query child; sửa domain helper để đồng bộ cả hai phía.

### Bài 8 — Remove

`em.remove(p)` rồi `assertFalse(em.contains(p))`.

**Đáp án:** Chưa xác nhận DB DELETE; flush/clear/find hoặc transaction mới.

### Bài 9 — @Version

Hai object references trong cùng EM cùng tìm Product#1.

**Đáp án:** Đó thường là một managed instance; cần EM/transactions độc lập để test optimistic locking.

### Bài 10 — Deferred constraint

`em.flush()` không ném lỗi nhưng `tx.commit()` thất bại.

**Đáp án:** Có thể do database kiểm tra constraint tại commit; đây không phải mâu thuẫn với khái niệm flush.

### Bài 11 — Bean Validation

`@NotBlank` từ chối dữ liệu trước INSERT.

**Hỏi:** DB CHECK đã được xác nhận chưa?

**Đáp án:** Chưa. Lỗi có thể xuất phát từ validator, cần test DB constraints riêng.

### Bài 12 — AUTO flush

Một JPQL query làm provider phát INSERT trước khi trả kết quả.

**Đáp án:** AUTO flush có thể là nguyên nhân. Dùng explicit flush khi muốn điểm SQL rõ.

### Bài 13 — Bulk DML

Query UPDATE thay Product name, nhưng entity managed cũ vẫn giữ name cũ.

**Đáp án:** Bulk DML không tự đồng bộ L1; dùng refresh hoặc flush/clear/reload có chủ đích.

### Bài 14 — Transaction mới

Writer flush nhưng chưa commit; reader EM khác không tìm thấy Product.

**Đáp án:** Có thể do isolation. Commit writer trước rồi mới xác nhận committed visibility.

### Bài 15 — Converter

AttributeConverter lưu một enum/code tùy biến vào column.

**Đáp án:** Persist, flush, clear, find và so sánh giá trị round-trip; nếu cần xác nhận physical DB representation, dùng JDBC/direct SQL assertion.

### Bài 16 — Test fixture trùng SKU

Hai tests commit Product với SKU cố định và không cleanup.

**Đáp án:** Dễ gây flaky unique failures. Cô lập DB, rollback/cleanup có kế hoạch hoặc dùng unique identifiers.

### Bài 17 — Sequence gaps

Test muốn ID liên tục 101,102,103 sau rollbacks.

**Đáp án:** Không nên xem đó là invariant chung của sequence/identity.

### Bài 18 — H2 vs PostgreSQL

H2 test pass nhưng PostgreSQL migration có deferred foreign key.

**Đáp án:** Cần test DBMS đích, nhất là commit-time constraints.

### Bài 19 — Ngăn SQL SELECT

Sau clear, `assertNotSame(p, loaded)` pass.

**Hỏi:** Có đủ để assert một SELECT đã chạy?

**Đáp án:** Không. L2 có thể dùng; cần cache control và JDBC instrumentation.

### Bài 20 — Chọn đúng test

Một tính năng cần chứng minh dữ liệu được transaction thứ hai đọc sau khi transaction thứ nhất commit.

**Đáp án:** Flush/clear trong cùng transaction chưa đủ; dùng T1 commit, T2/new EntityManager đọc rồi cleanup.

## 37. Câu hỏi tự kiểm tra

**1. Vì sao persist rồi find trong cùng EntityManager dễ tạo test xanh giả?**

Vì first-level cache có thể trả lại chính managed instance chưa cần SELECT.

**2. Persistence context là gì?**

Tập hợp managed entities và thông tin quản lý state mà EntityManager sử dụng.

**3. flush có tác dụng chính gì?**

Đồng bộ pending changes xuống database trong transaction đang hoạt động.

**4. flush có commit transaction không?**

Không.

**5. clear có tác dụng gì?**

Detach tất cả managed entities khỏi persistence context.

**6. clear có tự flush không?**

Không.

**7. Vì sao thường gọi flush trước clear trong integration test?**

Để gửi pending DML xuống DB trước khi bỏ managed state.

**8. assertSame trong cùng persistence context chứng minh điều gì?**

Identity map behavior; không chứng minh round-trip database.

**9. assertNotSame sau clear có chứng minh SQL SELECT không?**

Không; shared cache/L2 vẫn có thể cung cấp state.

**10. Nếu muốn buộc đọc DB, cần chú ý cache nào?**

Ít nhất L1 và L2/shared cache, và provider-specific query cache nếu liên quan.

**11. EntityManagerFactory.getCache().evictAll() ảnh hưởng cái gì?**

Shared entity cache theo API chuẩn trong phạm vi provider hỗ trợ; không bảo đảm xóa mọi DB/driver cache.

**12. commit cần thiết khi test điều gì?**

Durability và visibility của committed changes giữa transactions.

**13. @DataJpaTest thường rollback sau test không?**

Thông thường có transactional rollback mặc định trong cấu hình test slice phổ biến.

**14. saveAndFlush có tự clear persistence context không?**

Không.

**15. @Version test cần bao nhiêu context?**

Thông thường ít nhất hai contexts/transactions độc lập để mô phỏng stale update.

**16. Bean Validation failure có chứng minh DB constraint tồn tại không?**

Không.

**17. Unique/FK constraints có luôn bị phát hiện ở flush không?**

Không; deferred constraints có thể phát hiện khi commit.

**18. Hibernate/JPA có thể INSERT sớm vì IDENTITY không?**

Có, tùy provider/ID generation.

**19. ID khác null có chứng minh row đã INSERT không?**

Không.

**20. @OneToMany(mappedBy=...) phía nào sở hữu FK?**

Phía có relationship owning attribute, thường `@ManyToOne` với `@JoinColumn` trên child.

**21. Đếm collection.size trước flush chứng minh FK chưa?**

Không.

**22. Bulk JPQL UPDATE có tự sửa managed entities đang có trong L1 không?**

Không nên giả định; cần đồng bộ lại state theo chiến lược phù hợp.

**23. refresh khác clear thế nào?**

Refresh nạp lại một managed entity; clear detach toàn bộ managed entities.

**24. detach khác clear thế nào?**

Detach nhắm một entity; clear nhắm tất cả entities trong context.

**25. close có dùng thay clear được mọi lúc không?**

Không; close kết thúc EntityManager lifecycle và không phù hợp mọi môi trường/container-managed EM.

**26. Một query JPQL có thể tự flush không?**

Có thể, đặc biệt với AUTO flush mode trong transaction theo semantics chuẩn.

**27. Một test chạy trên JPA-generated schema có xác nhận migrations production không?**

Không.

**28. Tại sao cần Testcontainers/DBMS đích cho một số tests?**

Vì SQL dialect, constraints, ID strategies và locks có thể khác database in-memory.

**29. Một transaction rollback có để lại sequence gaps không?**

Có thể, tùy DBMS và generator semantics.

**30. Khi nào dùng JDBC assertion ngoài EntityManager?**

Khi cần xác nhận physical DB values, trigger/default hoặc SQL-visible state độc lập ORM cache.

**31. Vì sao không chạy nhiều negative constraint tests trong cùng transaction sau một lỗi?**

Transaction có thể đã rollback-only hoặc state provider không còn phù hợp.

**32. Khi nào cần kiểm tra SQL logs/counters?**

Khi mục tiêu là chứng minh SQL thực thi hoặc đo query count, không chỉ entity state.

**33. Có nên coi flush là thao tác an toàn ngoài transaction không?**

Không. Flush với transaction-scoped EntityManager thường yêu cầu transaction phù hợp; có thể ném `TransactionRequiredException` nếu không có transaction khi cần.

**34. Nếu test pass sau flush/clear nhưng dữ liệu rollback, kết luận chính xác là gì?**

Mapping round-trip trong transaction đã được kiểm tra ở mức phù hợp, nhưng durability sau commit chưa được chứng minh.

**35. Công thức kiểm thử quan trọng nhất?**

`Persist/modify → flush → clear → reload → assert`, và **commit + context mới** khi yêu cầu kiểm tra dữ liệu đã được lưu bền vững.

## 38. Một tình huống thực tế: phát hiện lỗi trước khi deploy

Một nhóm xây API cập nhật Product. Service:

```java
@Transactional
public void renameProduct(
        long productId,
        String newName) {

    Product product =
        em.find(Product.class, productId);

    product.rename(newName);
}
```

Unit test cũ:

```java
product.rename("New");

assertEquals("New", product.getName());
```

Test xanh nhưng không kiểm tra:

- `@Column(name="name")` khớp DB.
- Dirty checking phát sinh UPDATE.
- `@Version` được cập nhật.
- DB constraint chấp nhận tên mới.
- Một transaction khác nhìn thấy giá trị mới sau commit.

### 38.1. Nâng cấp thành integration test đúng mục tiêu

1. Tạo Product fixture trong database test.
2. Gọi service trong transaction thực.
3. Flush để buộc SQL.
4. Clear persistence context của test.
5. Tìm lại Product qua JPA.
6. Assert tên/version.
7. Khi cần durability, kết thúc transaction commit và đọc bằng EM mới.
8. Cleanup fixture.

### 38.2. Một lỗi được phát hiện

Giả sử entity map sai:

```java
@Column(name="product_display_name")
private String name;
```

nhưng migration chỉ có `name`. Khi provider tạo UPDATE/SELECT, test integration có thể lỗi SQL; unit test trên Java object vẫn xanh.

### 38.3. Một lỗi khác: mapping association

Service thêm OrderLine vào `order.getLines()` nhưng quên set `line.order`. Unit test collection size vẫn xanh, trong khi test `flush` có thể ném lỗi FK/NOT NULL và test reload có thể phát hiện graph sai.

### 38.4. Một lỗi concurrency

Một user cập nhật Product dựa trên version cũ. Test một EM không tạo conflict, còn test hai EM/transactions với `@Version` có thể phát hiện race.

### 38.5. Kết quả cần ghi nhận

Không chỉ “JUnit pass”, mà:

```text
Test purpose: mapping round-trip
Database: PostgreSQL test instance
Schema source: versioned migrations
JPA provider: actual project provider
Transaction: rollback after assertions
L1: cleared before reload
L2: disabled/bypassed for database-read assertions
Assertions: persisted fields + associations + version
Additional commit test: separate EM/transaction when required
```

Những thông tin này làm test dễ hiểu và giảm kết luận sai khi đổi cấu hình.

## 39. Quy tắc thực hành cuối bài

1. **Biết rõ bạn đang kiểm tra Java object hay database state.** Hai việc khác nhau.
2. **Không coi `persist() → find()` trong cùng context là bằng chứng round-trip.**
3. **Gọi `flush()` để buộc đồng bộ pending DML** tại điểm test đã định.
4. **Gọi `clear()` sau flush** để tránh đọc lại managed instance từ L1.
5. **Chú ý L2/shared cache** nếu mục tiêu là xác nhận SQL SELECT thực sự.
6. **Đừng coi flush là commit.** Một transaction vẫn có thể rollback.
7. **Dùng transaction mới sau commit** khi kiểm tra durable/committed visibility.
8. **Không dùng `clear()` tùy tiện khi còn pending changes**, vì detached state có thể không được ghi.
9. **Test cả INSERT, UPDATE, DELETE và relationships**, không chỉ persist đơn giản.
10. **Kiểm tra owning side, cascade và orphanRemoval qua reload** thay vì chỉ xem collections Java.
11. **Biết constraints có thể được kiểm tra ở flush hoặc commit**, không hard-code một giả định trái DB semantics.
12. **Phân biệt lỗi Bean Validation với DB constraints**, vì flush exception có thể phát sinh trước SQL.
13. **Dùng schema migrations thật khi kiểm tra production contract**, không chỉ DDL do JPA provider tự tạo.
14. **Chạy trên DBMS gần production cho tests quan trọng**, nhất là khóa ngoại, sequence, precision và concurrency.
15. **Thiết kế test isolation/cleanup**, không dựa vào IDs liên tục hoặc fixture cũ.
16. **Đo SQL riêng khi cần chứng minh execution**, không dùng assertNotSame làm SQL counter.
17. **Tách JPA mapping tests và transaction/concurrency tests**, để mỗi bài có kết luận rõ.
18. **Dùng `flush()/clear()` như công cụ kiểm soát persistence context**, không phải một quy trình “luôn luôn dùng trong production”.

## 40. Kết luận

**`flush()` và `clear()` là hai thao tác nhỏ nhưng rất quan trọng trong JPA integration testing.** Chúng giúp phân biệt một assertion chỉ đọc managed object trong bộ nhớ với một assertion đi qua cơ chế lưu trữ và nạp lại entity.

Chuỗi:

```java
em.persist(entity);
em.flush();

ID id = entity.getId();

em.clear();

Entity reloaded = em.find(Entity.class, id);

assertExpectedState(reloaded);
```

là **mẫu tư duy** cho những bài test mapping cần round-trip. Tùy chương trình thực tế, `ID`, `Entity` và `assertExpectedState` phải thay bằng types và assertions cụ thể.

Tuy nhiên, phải nhớ ba giới hạn:

- **`flush()` không commit**: rollback vẫn có thể loại toàn bộ thay đổi.
- **`clear()` chỉ làm sạch persistence context/L1**, không nhất thiết bypass shared cache/L2.
- **Một lần đọc lại trong cùng transaction không chứng minh đã commit**: nếu yêu cầu là durability/visibility qua transaction, cần commit rồi kiểm tra bằng một context/transaction độc lập.

Khi kết hợp những nguyên tắc này với schema migrations thực, test ràng buộc DB, entity lifecycle, optimistic locking và concurrency, JPA tests sẽ đáng tin cậy hơn rất nhiều: không chỉ xác nhận đối tượng Java “trông đúng”, mà còn kiểm chứng **metadata thực sự lưu và đọc dữ liệu đúng cách trong database mà ứng dụng sẽ dùng**.
