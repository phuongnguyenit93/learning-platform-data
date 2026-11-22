# Thực hiện flush tường minh để xác định lỗi sớm trong JPA

Trong Jakarta Persistence (JPA), ứng dụng thường sửa các entity đang được quản lý trong **persistence context**, sau đó để provider tự đồng bộ dữ liệu xuống database khi cần. Cách làm này thuận tiện vì không phải viết SQL `INSERT`, `UPDATE` hay `DELETE` sau mỗi thay đổi, nhưng có một hệ quả quan trọng: **lỗi ghi dữ liệu có thể xuất hiện muộn hơn dòng Java gây ra thay đổi**.

Ví dụ, ta gọi `entityManager.persist(product)` để tạo sản phẩm có mã SKU bị trùng. Lời gọi `persist` có thể chưa gửi `INSERT`. Chỉ khi JPA thực thi SQL — thường tại một lần `flush` hoặc trong lúc `commit` — database mới phát hiện vi phạm `UNIQUE`. Nếu lỗi xuất hiện tận cuối transaction, người lập trình khó biết bước nghiệp vụ nào tạo dữ liệu không hợp lệ, và các thao tác khác đã diễn ra sau đó có thể phải hủy theo.

**`EntityManager.flush()`** cho phép ứng dụng yêu cầu JPA **đồng bộ tường minh các thay đổi đang chờ** trong persistence context với database. Khi cần một điểm kiểm tra rõ ràng giữa transaction, `flush` giúp nhiều lỗi về dữ liệu, quan hệ hoặc cạnh tranh cập nhật xuất hiện **trước khi thực hiện các bước tiếp theo**.

Tuy nhiên:

> **`flush()` không phải `commit()`; không có gì bảo đảm rằng mọi lỗi sẽ xuất hiện tại flush hoặc rằng dữ liệu đã được xác nhận bền vững sau flush.**

Bài học thuộc chương **Đồng bộ và flush**, tập trung vào cách dùng flush tường minh để xác định lỗi sớm, phân biệt thời điểm phát hiện với thời điểm xác nhận transaction, xử lý ngoại lệ đúng cách và nhận biết khi nào flush thủ công thực sự có ích.

## 1. Tại sao lỗi có thể đến muộn?

JPA dùng cơ chế **write-behind**: nhiều thay đổi ở entity managed được ghi nhận trong persistence context trước khi được chuyển thành SQL. Ví dụ:

```java
Product product = new Product(
    "KEYBOARD-001",
    "Mechanical keyboard"
);

entityManager.persist(product);

// Ở thời điểm này, Product có thể đã managed,
// nhưng INSERT chưa chắc đã chạy.
```

Nếu database đã có sản phẩm `sku = 'KEYBOARD-001'`, việc tạo bản ghi mới sẽ vi phạm ràng buộc duy nhất. Tuy nhiên, nếu provider chưa gửi câu `INSERT`, database cũng chưa có cơ hội từ chối.

Diễn biến có thể như sau:

```text
Transaction bắt đầu
       |
       v
new Product(...)
       |
       | persist(product)
       v
Product trở thành managed
Pending INSERT trong persistence context
       |
       | Thực hiện thêm nghiệp vụ khác
       v
EntityManager.flush()
       |
       | SQL INSERT được thực thi
       v
Database kiểm tra UNIQUE
       |
       +-----> Lỗi do SKU trùng được báo tại flush
       |
       +-----> Nếu thành công, transaction vẫn chưa commit
```

Không phải mọi chiến lược định danh và provider đều trì hoãn INSERT giống nhau. Chẳng hạn `GenerationType.IDENTITY` có thể cần gửi INSERT sớm để lấy ID. Do vậy hãy hiểu sơ đồ như **một diễn biến có thể xảy ra**, không phải cam kết “mọi `persist` đều chưa chạy SQL cho tới flush”.

### 1.1. Persistence context làm gì trước khi flush?

Persistence context quản lý các entity instance và state liên quan:

- Entity mới qua `persist` có thể đang chờ INSERT.
- Entity managed bị thay đổi field có thể đang chờ UPDATE.
- Entity managed được `remove` có thể đang chờ DELETE.
- Một thay đổi relationship có thể cần UPDATE khóa ngoại hoặc INSERT/DELETE ở bảng nối.
- Provider có thể theo dõi thay đổi bằng snapshot, dirty tracking, collection tracking hoặc các cơ chế riêng.

Ở mốc `flush`, provider xử lý trạng thái cần đồng bộ với database theo thứ tự phù hợp ràng buộc và mapping. Đây **không phải** lời hứa mỗi setter sẽ thành một SQL statement, cũng không phải bảo đảm thứ tự SQL trùng với thứ tự dòng Java.

### 1.2. Tại sao việc phát hiện sớm hữu ích?

Khi workflow có nhiều bước:

```text
1. Tạo hồ sơ đăng ký
2. Gắn quan hệ tới khóa học
3. Lưu các mục đăng ký
4. Chuẩn bị dữ liệu phản hồi
5. Commit
```

Nếu dữ liệu ở bước 1–3 vi phạm ràng buộc, một lần `flush` sau khi hoàn thành các thao tác tạo dữ liệu có thể giúp phát hiện sớm trước khi thực hiện bước 4 hoặc các tác vụ tính toán tốn kém khác.

Nhưng phát hiện sớm chỉ giúp **đặt mốc đồng bộ**, không thay thế việc validate input, thiết kế database constraint hoặc quản lý transaction đúng.

## 2. Flush, commit, rollback: ba thao tác khác nhau

| Thao tác | Ý nghĩa chính | Kết quả nên kỳ vọng |
|---|---|---|
| `persist(entity)` | Đưa entity mới vào managed lifecycle | JPA quản lý entity; SQL có thể chưa chạy |
| Sửa field của managed entity | Thay đổi persistent state | Provider có thể dirty-check khi flush |
| `flush()` | Đồng bộ pending changes với database trong transaction | SQL có thể chạy, lỗi có thể lộ sớm |
| `commit()` | Xác nhận transaction | Dữ liệu được database commit nếu thành công |
| `rollback()` | Hủy transaction | Các thay đổi thuộc transaction không được xác nhận |

Timeline minh họa:

```text
Thời điểm       Ứng dụng                  Database/transaction
------------------------------------------------------------------
T0              begin                      Transaction mở
T1              persist(product)           Có thể chưa có INSERT
T2              product.changePrice(...)   Có pending change
T3              flush()                    Thực thi các SQL cần thiết
T4              query/kiểm tra khác        Transaction vẫn mở
T5              commit()                   Xác nhận transaction
```

Nếu ở T3 `flush` thành công, **T5 vẫn có thể thất bại**. Ví dụ transaction khác gây conflict, deferred constraint được kiểm tra tại commit, sự cố connection hoặc database không thể xác nhận transaction.

Ngược lại, nếu không gọi flush tường minh, provider vẫn có thể flush tự động khi commit hoặc trước một số query. Flush tường minh chỉ tạo **điểm kiểm soát rõ ràng** trong code.

### 2.1. Flush thành công có đồng nghĩa những transaction khác thấy dữ liệu?

Không nhất thiết. Sau flush, các SQL có thể đã chạy nhưng vẫn nằm trong **transaction chưa commit**. Transaction khác có nhìn thấy hay không phụ thuộc isolation và hệ quản trị; mặc định cần xem dữ liệu chưa commit là **chưa được công bố bền vững**.

Không sử dụng flush để tuyên bố “dữ liệu đã sẵn sàng cho tất cả consumer”.

### 2.2. Flush không tự mở transaction

`EntityManager.flush()` dành cho ngữ cảnh có transaction phù hợp hoặc đã tham gia transaction. Nếu không có transaction hợp lệ/không joined như yêu cầu, provider có thể ném `TransactionRequiredException`.

Trong JPA resource-local, nên bắt đầu bằng `EntityTransaction.begin()`. Trong JTA hoặc Spring, transaction do container/framework quản lý và `EntityManager` cần tham gia đúng transaction đó.

## 3. Ví dụ thực hành: lưu sản phẩm có SKU duy nhất

Giả sử bảng `product` bắt buộc mỗi SKU duy nhất:

```sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT uq_product_sku UNIQUE (sku)
);
```

Đây là DDL khái niệm; cách sinh khóa ID và kiểu dữ liệu cụ thể phụ thuộc database. Chính **constraint thực tế trong database** mới bảo đảm uniqueness giữa nhiều transaction, không chỉ annotation JPA.

### 3.1. Entity Product

```java
package com.example.catalog.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "product")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(
        name = "sku",
        nullable = false,
        unique = true,
        length = 64
    )
    private String sku;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Version
    private long version;

    protected Product() {
    }

    public Product(String sku, String name, BigDecimal price) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên sản phẩm không hợp lệ");
        }
        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException("Giá không hợp lệ");
        }

        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void changePrice(BigDecimal newPrice) {
        Objects.requireNonNull(newPrice, "newPrice");
        if (newPrice.signum() < 0) {
            throw new IllegalArgumentException("Giá không được âm");
        }
        this.price = newPrice;
    }
}
```

`GenerationType.SEQUENCE` ở đây giúp minh họa trường hợp provider có thể cấp ID mà chưa cần INSERT product ngay. Nếu database không hỗ trợ sequence hoặc không có mapping sequence phù hợp, cần đổi sang chiến lược sinh ID được hệ thống hỗ trợ.

### 3.2. Mã lưu có flush tường minh

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

import java.math.BigDecimal;

public final class ProductRegistrationService {

    private final EntityManagerFactory emf;

    public ProductRegistrationService(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public Long create(String sku, String name, BigDecimal price) {
        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                Product product = new Product(sku, name, price);
                em.persist(product);

                // Mốc đồng bộ chủ động:
                // những INSERT/UPDATE/DELETE pending thích hợp
                // được chuyển xuống database.
                em.flush();

                Long id = product.getId();

                // Chỉ sau đây mới xác nhận transaction.
                tx.commit();
                return id;
            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    tx.rollback();
                }
                throw ex;
            }
        } finally {
            em.close();
        }
    }
}
```

Nếu SKU trùng, một exception có thể xuất hiện ở `em.flush()` thay vì chỉ khi `tx.commit()`. Điều này giúp đặt lỗi gần mốc nghiệp vụ vừa tạo Product.

**Lưu ý:** Một exception tại flush thường làm transaction thất bại hoặc bị đánh dấu rollback-only theo quy tắc JPA/provider. Đừng catch rồi tiếp tục dùng transaction đó để ghi dữ liệu khác như thể không có gì xảy ra.

### 3.3. Có bắt buộc phải flush mỗi lần tạo Product?

Không. Nếu service chỉ có một thao tác `persist` rồi commit ngay, việc gọi flush trước commit thường không mang nhiều lợi ích. Provider sẽ đồng bộ pending changes lúc commit.

Flush tường minh đáng cân nhắc hơn khi **sau thao tác ghi vẫn còn những bước phụ thuộc vào kết quả ghi hoặc cần xác định lỗi trước khi tiến hành**.

## 4. Lỗi UNIQUE: phát hiện trùng dữ liệu sớm

### 4.1. Trường hợp không flush tường minh

```java
tx.begin();

Product product = new Product(
    "MOUSE-001",
    "Wireless Mouse",
    new BigDecimal("250000")
);

em.persist(product);

// Công việc khác, có thể rất tốn kém.
prepareLargeReport();

tx.commit(); // Vi phạm UNIQUE có thể chỉ lộ ở đây.
```

Nếu SKU đã tồn tại, lỗi có thể xuất hiện sau khi báo cáo đã được tính xong. Tác vụ `prepareLargeReport()` có thể không có tác dụng vì toàn bộ transaction bị rollback.

### 4.2. Đặt flush trước công việc kế tiếp

```java
tx.begin();

Product product = new Product(
    "MOUSE-001",
    "Wireless Mouse",
    new BigDecimal("250000")
);

em.persist(product);
em.flush(); // Cơ hội phát hiện UNIQUE conflict tại đây.

prepareLargeReport();

tx.commit();
```

Khi database kiểm tra ràng buộc UNIQUE ngay lúc xử lý INSERT, `flush` giúp phát hiện lỗi trước `prepareLargeReport()`. Điều này hữu ích nếu báo cáo tốn CPU hoặc có tác vụ tính toán chỉ có ý nghĩa khi Product mới được chấp nhận.

Tuy nhiên, không được xem flush là một **lock/giấy phép đặt chỗ vĩnh viễn** cho SKU. Transaction vẫn chưa commit và có thể thất bại ở bước khác.

### 4.3. Pre-check tồn tại vẫn có race condition

```java
boolean exists = !em.createQuery(
    "select p.id from Product p where p.sku = :sku",
    Long.class
)
.setParameter("sku", sku)
.setMaxResults(1)
.getResultList()
.isEmpty();

if (exists) {
    throw new IllegalArgumentException("SKU đã tồn tại");
}

em.persist(new Product(sku, name, price));
em.flush();
```

Query kiểm tra trước giúp trả thông báo dễ hiểu khi dữ liệu đã tồn tại. Nhưng hai transaction đồng thời có thể cùng thấy SKU chưa tồn tại. Chỉ **UNIQUE constraint trong database** mới bảo vệ tính duy nhất khi commit theo mức isolation và cơ chế xử lý cạnh tranh phù hợp.

Sơ đồ:

```text
Transaction A                   Transaction B
----------------------------    ----------------------------
SELECT SKU -> chưa có          SELECT SKU -> chưa có
persist(Product A)              persist(Product B)
flush -> INSERT                 flush -> INSERT hoặc chờ
commit                         conflict tại flush/commit
```

Thời điểm phát sinh conflict phụ thuộc cơ chế khóa, index, isolation và ràng buộc. Một transaction có thể bị chặn chờ transaction kia trước khi biết có conflict.

**Đừng dựa vào việc flush thành công như bằng chứng tuyệt đối rằng commit sẽ không vi phạm uniqueness.**

## 5. Lỗi NOT NULL: flush giúp kiểm tra cột bắt buộc

Giả sử column `product.name` là `NOT NULL`. Trong entity:

```java
@Column(nullable = false)
private String name;
```

Nếu service tạo Product thiếu tên bằng một constructor hoặc setter không có validation:

```java
Product product = ...; // name bị null.
em.persist(product);
em.flush();
```

Có thể có một trong các kết quả:

- Bean Validation hoặc kiểm tra của provider phát hiện lỗi trước khi SQL chạy.
- Provider phát SQL và database từ chối INSERT do `NOT NULL`.
- Exception xuất hiện tại flush/commit tùy quá trình đồng bộ và cấu hình.

Đừng khẳng định **tất cả `NOT NULL` violations chỉ xuất hiện tại flush**. Trong ví dụ `Product` đã có validation tại constructor, nên input thiếu tên sẽ bị chặn **trước cả persist**.

Một thiết kế có nhiều lớp kiểm tra:

1. Validate request trước khi tạo entity.
2. Constructor/domain method bảo vệ invariant.
3. Bean Validation nếu dự án tích hợp.
4. Mapping JPA mô tả constraints.
5. Database `NOT NULL` bảo vệ dữ liệu cuối cùng.
6. Flush có chủ đích nếu cần phát hiện lỗi ghi trước bước nghiệp vụ tiếp theo.

## 6. Lỗi FOREIGN KEY: entity liên kết không hợp lệ

Xét một đơn hàng tham chiếu khách hàng:

```java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer) {
        this.customer = java.util.Objects.requireNonNull(customer);
    }
}
```

Database có cột `purchase_order.customer_id` với FK tới `customer.id`.

### 6.1. Tham chiếu sai ID bằng getReference

```java
Customer customerRef =
    em.getReference(Customer.class, customerId);

PurchaseOrder order = new PurchaseOrder(customerRef);

em.persist(order);
em.flush();
```

`getReference` có thể trả reference mà không SELECT để kiểm tra ngay row Customer. Nếu ID không tồn tại và provider sử dụng FK đó trong INSERT, database sẽ từ chối do foreign key constraint. Một số provider có thể phát hiện khi truy cập reference trước đó.

**Mốc flush cho biết lỗi có thể xuất hiện sớm hơn commit**, nhưng không thay thế kiểm tra tồn tại hoặc authorization nếu nghiệp vụ yêu cầu.

### 6.2. Quan hệ tới transient entity chưa được persist

```java
Customer transientCustomer = new Customer(...);

PurchaseOrder order = new PurchaseOrder(transientCustomer);

em.persist(order);
// Chưa persist Customer và không có cascade phù hợp.
em.flush();
```

Provider có thể phát hiện tham chiếu tới transient entity hoặc database có thể từ chối FK. Lỗi cũng có thể xuất hiện trước flush nếu provider kiểm tra graph sớm.

Để tạo cả Customer và Order, hoặc:

- Persist Customer rồi persist Order trong transaction.
- Hoặc dùng cascade PERSIST đúng với vòng đời nghiệp vụ và mapping.
- Đồng bộ owning side của association; trong ví dụ `PurchaseOrder.customer` giữ FK.

**Không chỉ thêm cascade bừa bãi** tới entity danh mục hoặc entity độc lập để tránh lỗi. Ví dụ Product/Role đang dùng chung bởi nhiều entity thường không nên được tạo mới tự động khi persist một Order.

## 7. Optimistic locking: phát hiện xung đột khi flush

Flush không chỉ kiểm tra INSERT. Nó cũng có thể đồng bộ **UPDATE** và phát hiện lỗi cạnh tranh cập nhật với `@Version`.

Entity:

```java
@Entity
public class Account {

    @Id
    private Long id;

    @Version
    private long version;

    @Column(nullable = false)
    private String displayName;

    protected Account() {
    }

    public void rename(String name) {
        this.displayName = name;
    }
}
```

Giả sử hai transaction cùng đọc:

```text
Account id=10, version=4

Transaction A                       Transaction B
-------------------------------     -------------------------------
Tải Account#10, version=4           Tải Account#10, version=4
rename("A")                         rename("B")
flush/commit -> version=5           flush -> UPDATE với version=4
                                    có thể nhận OptimisticLockException
```

SQL khái niệm:

```sql
UPDATE account
SET display_name = ?,
    version = 5
WHERE id = 10
  AND version = 4;
```

Nếu không còn row có version 4, provider có thể phát hiện xung đột qua số dòng được cập nhật hoặc cơ chế tương ứng.

### 7.1. Có phải `OptimisticLockException` luôn xuất hiện tại flush?

Không. Việc kiểm tra có thể diễn ra ở flush, khi gọi lock hoặc tại commit, tùy provider và tình huống. Ngoài ra, bulk JPQL/SQL update không có cùng semantics entity-level optimistic locking tự động.

Flush có ích khi muốn **yêu cầu provider thử đồng bộ phiên bản đang quản lý sớm**, nhưng không phải bảo đảm mọi conflict sẽ được phát hiện trước commit.

### 7.2. Không sửa entity rồi refresh để “tự hết conflict”

```java
account.rename("Tên mới");
em.refresh(account);
```

`refresh` có thể ghi đè thay đổi cục bộ chưa flush. Nó không phải phương thức giải quyết conflict một cách an toàn cho mọi nghiệp vụ.

Khi có optimistic locking failure, thông thường cần rollback transaction và bắt đầu lại từ context mới, hoặc báo user dữ liệu đã được người khác thay đổi.

## 8. Lỗi độ dài cột, kiểu dữ liệu và constraint khác

Ngoài `UNIQUE`, `NOT NULL` và FK, SQL khi flush có thể phát sinh lỗi:

- Vượt chiều dài `VARCHAR` nếu DB từ chối thay vì cắt chuỗi.
- Vượt precision/scale của `DECIMAL`.
- Vi phạm `CHECK` constraint, ví dụ `price >= 0`.
- Vi phạm khóa chính `PRIMARY KEY`.
- Vi phạm ràng buộc liên quan bảng nối many-to-many.
- Trigger database từ chối thao tác.
- Deadlock, lock timeout hoặc các vấn đề về concurrency/driver.
- Lỗi conversion, mapping hoặc Bean Validation trong quá trình chuẩn bị đồng bộ.

Ví dụ:

```sql
ALTER TABLE product
ADD CONSTRAINT ck_product_price
CHECK (price >= 0);
```

Nếu code cho phép giá âm bất chấp validation, database có thể phát hiện khi `UPDATE/INSERT` được thực thi. Tuy vậy SQL dialect, trigger, constraint timing và thứ tự statement có thể ảnh hưởng thời điểm xuất hiện exception.

**Flush không phải một “trình kiểm tra toàn bộ database”**. Nó chủ yếu yêu cầu provider đồng bộ các thay đổi đang chờ trong persistence context hiện tại.

## 9. Những lỗi không thể bảo đảm phát hiện tại flush

Đây là giới hạn quan trọng nhất khi đặt flush làm “điểm xác thực”.

### 9.1. Deferred constraints

Một số database cho phép **ràng buộc có thể trì hoãn** (*deferrable constraints*) và kiểm tra ở **cuối transaction**. Khi đó SQL INSERT tại flush có thể thành công, nhưng commit mới báo lỗi.

Ví dụ khái niệm ở database có hỗ trợ:

```sql
CONSTRAINT uq_some_value
UNIQUE (some_value)
DEFERRABLE INITIALLY DEFERRED
```

Với ràng buộc deferred, **flush thành công không chứng minh rằng UNIQUE/FK cuối cùng sẽ hợp lệ khi commit**.

### 9.2. Transaction conflict đến muộn

Một transaction khác có thể thay đổi hoặc commit dữ liệu liên quan sau khi một flush đã hoàn tất, tùy isolation và loại ràng buộc. Deadlock, serialization failure hoặc optimistic conflict trong một thao tác khác vẫn có thể phát sinh ở lần flush kế tiếp hoặc tại commit.

### 9.3. Lỗi kết nối hoặc commit

Ngay cả khi mọi SQL hiện tại thành công, database hoặc mạng có thể gặp sự cố khi commit. Flush không thể bảo đảm đường đi tới một commit thành công trong tương lai.

### 9.4. Những thay đổi xảy ra sau flush

```java
em.persist(productA);
em.flush(); // OK.

// Sau flush vẫn còn thay đổi mới:
em.persist(productB);

// Product B có thể lỗi ở lần flush sau hoặc commit.
tx.commit();
```

Một flush chỉ đồng bộ **những state cần đồng bộ tại mốc đó**. Nó không xác thực tất cả những thay đổi chưa được tạo ra.

### 9.5. Business invariant không được DB kiểm tra

Một rule như “mỗi khách hàng chỉ được tạo tối đa ba đơn đang mở” có thể không được diễn đạt bằng constraint đơn giản. Flush không tự kiểm tra logic đó nếu ứng dụng chưa implement validation và transaction/concurrency control.

**Tóm lại:** flush tạo cơ hội kiểm tra sớm một phần lớn lỗi đồng bộ, nhưng không thay thế commit, business validation hay hệ thống constraint đúng.

## 10. Flush đồng bộ toàn bộ pending changes, không chỉ entity vừa sửa

Một hiểu nhầm phổ biến:

```java
em.persist(productA);
em.persist(productB);
em.flush();
```

`flush` không có tham số entity; nó yêu cầu đồng bộ **persistence context** với database, không chỉ Product B. Do đó, lỗi xảy ra tại `flush` có thể thuộc:

- Product A hoặc Product B.
- Một managed entity khác đã bị thay đổi trước đó.
- Một entity được cascade persist từ quan hệ.
- Một DELETE/UPDATE ở bảng khác.
- Một collection/join table pending operation.

Sơ đồ:

```text
Persistence context
   |
   +-- new Product A        -> pending INSERT
   +-- new Product B        -> pending INSERT
   +-- managed Account C    -> pending UPDATE
   +-- removed Order D      -> pending DELETE
   +-- association change   -> pending join table update
   |
   +------------------------------+
                                  |
                                  | em.flush()
                                  v
                    Provider thực thi SQL cần thiết
                                  |
                                  v
                    Lỗi có thể đến từ bất kỳ
                    pending operation liên quan
```

### 10.1. Đặt flush ở ranh giới hợp lý

Nếu cần phân biệt nhiều giai đoạn nghiệp vụ, có thể:

```java
// Giai đoạn 1: tạo hồ sơ.
em.persist(registration);
em.flush(); // Mốc kiểm tra giai đoạn tạo hồ sơ.

// Giai đoạn 2: thêm các dòng chi tiết.
for (RegistrationLine line : lines) {
    em.persist(line);
}
em.flush(); // Mốc kiểm tra giai đoạn thêm chi tiết.

// Giai đoạn 3: tính toán nội bộ khác.
calculateSummary();
```

Nhưng **mỗi lần flush có thể làm tăng số round trip và giảm khả năng tối ưu batching**. Không nên flush sau mọi dòng trong vòng lặp nếu một mốc sau batch đã đủ.

### 10.2. Thứ tự SQL có thể khác thứ tự Java

Provider có thể sắp xếp INSERT/UPDATE/DELETE để đáp ứng FK hoặc batch tối ưu. Ví dụ Java gọi `persist(orderLine)` trước `persist(order)` nhưng provider có thể INSERT order trước để có FK hợp lệ.

Khi điều tra lỗi, cần nhìn SQL thực tế, entity mapping và stack trace; đừng suy ra chính xác statement nào lỗi chỉ dựa vào dòng gọi persist gần nhất trước flush.

## 11. Cách xử lý exception đúng sau flush thất bại

Một cách xử lý nguy hiểm:

```java
try {
    em.flush();
} catch (PersistenceException ex) {
    // Sai: bỏ qua lỗi rồi tiếp tục transaction.
}

em.persist(otherEntity);
tx.commit();
```

Sau lỗi đồng bộ, transaction có thể đã bị đánh dấu rollback-only hoặc persistence context không còn state có thể tin cậy. Việc catch exception không làm database hoặc provider “quên” lỗi vừa xảy ra.

### 11.1. Cách xử lý resource-local

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product = new Product(sku, name, price);
    em.persist(product);
    em.flush();

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        try {
            tx.rollback();
        } catch (RuntimeException rollbackFailure) {
            ex.addSuppressed(rollbackFailure);
        }
    }
    throw ex;
} finally {
    em.close();
}
```

Ở đây:

1. Bắt lỗi từ mọi giai đoạn của transaction, gồm flush và commit.
2. Rollback nếu transaction vẫn active.
3. Không cố tiếp tục ghi trong context bị lỗi.
4. Đóng EntityManager để kết thúc unit of work.
5. Chuyển exception lên tầng có đủ thông tin để xử lý theo nghiệp vụ.

Với lỗi constraint đã xác định, tầng ứng dụng có thể quy đổi thành mã lỗi như `409 Conflict` cho duplicate SKU. Tuy nhiên, phân loại nên dựa trên exception cause, database error code hoặc cơ chế dịch lỗi của framework; **không bắt mọi PersistenceException rồi gọi chúng là lỗi trùng SKU**.

### 11.2. Vì sao rollback có thể không chạy như dự đoán?

Nếu commit đã hoàn tất hoặc transaction không còn active, `tx.isActive()` có thể trả false; nếu connection gặp lỗi nghiêm trọng, rollback cũng có thể thất bại. Vì vậy ví dụ xử lý rollback theo điều kiện và không ghi đè exception gốc.

Các hệ thống production có thể cần transaction manager và quy tắc exception handling của framework thay vì tự viết đoạn quản lý resource-local ở mọi service.

### 11.3. Retry phải dùng đơn vị công việc mới

Nếu lỗi là deadlock hoặc serialization conflict và nghiệp vụ cho phép retry, thực hiện trong **transaction và persistence context mới** sau khi lỗi cũ đã được xử lý. Không lặp lại `flush` trên cùng context hỏng mà kỳ vọng transaction tự sửa.

Retry cũng cần giới hạn số lần, idempotency và bảo đảm không lặp side effect bên ngoài.

## 12. Dùng flush trong Spring @Transactional

Trong Spring sử dụng Jakarta Persistence, ví dụ:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long createProduct(
            String sku,
            String name,
            BigDecimal price
    ) {
        Product product = new Product(sku, name, price);
        em.persist(product);

        // Muốn kiểm tra SQL/DB constraints trước
        // một bước nghiệp vụ tiếp theo:
        em.flush();

        return product.getId();
    }
}
```

Với Spring transaction interceptor, commit diễn ra khi kết thúc transaction do framework quản lý. Từ trong body của method, `em.flush()` có thể giúp nhìn thấy một lỗi SQL trước lệnh `return`, nhưng phương thức vẫn **chưa tự bảo đảm commit hoàn tất chỉ vì flush trả về**.

### 12.1. JPA EntityManager.flush và Spring Data saveAndFlush

Trong Spring Data JPA thường có:

```java
Product saved = productRepository.save(product);
productRepository.flush();
```

hoặc:

```java
Product saved = productRepository.saveAndFlush(product);
```

`saveAndFlush` là **API Spring Data JPA**, không phải phương thức chuẩn của `EntityManager`. Nó thường kết hợp thao tác save và yêu cầu flush trong cùng transaction phù hợp.

Những điều cần phân biệt:

- `save` có thể dùng persist hoặc merge tùy cách Spring Data nhận diện entity mới.
- `flush`/`saveAndFlush` **không tự commit transaction đang mở**.
- Một lần flush có thể đồng bộ các thay đổi pending khác trong cùng persistence context.
- Flush được chủ động gọi nhằm xác định lỗi sớm, không phải để biến save thành lệnh SQL atomic riêng.

### 12.2. Không catch rồi nuốt lỗi trong @Transactional

Ví dụ không nên làm:

```java
@Transactional
public void createAndIgnoreDuplicate(...) {
    try {
        em.persist(product);
        em.flush();
    } catch (RuntimeException ex) {
        // Bỏ qua, sau đó return bình thường.
    }
}
```

Với lỗi persistence làm transaction rollback-only, method có thể return bình thường nhưng transaction manager vẫn rollback và báo lỗi khi kết thúc. Cách đúng là để exception lan tới tầng xử lý phù hợp hoặc đánh dấu rollback rõ ràng rồi kết thúc transaction.

Nếu nghiệp vụ yêu cầu thử một operation và sau lỗi vẫn thực hiện operation khác, **không dùng một transaction hỏng rồi hy vọng tiếp tục**. Có thể chia ranh giới transaction theo yêu cầu, dùng các transaction độc lập khi phù hợp, hoặc thiết kế kiểm tra/idempotent logic — nhưng không dùng savepoint/native SQL như một kỹ thuật JPA portable mặc định.

### 12.3. Read-only transaction và flush

Một số framework/provider có thể điều chỉnh flush mode hoặc dirty checking cho transaction được đánh dấu read-only. Không nên gọi `persist` + `flush` trong một phương thức chỉ dành cho đọc rồi dự đoán nó sẽ ghi dữ liệu bình thường.

Hãy đặt write operation trong transaction cho phép ghi và có rollback policy rõ ràng.

## 13. Jakarta EE/JTA: flush nhưng không tự gọi commit

Trong Jakarta EE:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.transaction.Transactional;

public class ProductService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void createProduct(
            String sku,
            String name,
            BigDecimal price
    ) {
        Product product = new Product(sku, name, price);

        em.persist(product);
        em.flush();
    }
}
```

`@PersistenceContext` cung cấp container-managed EntityManager. `@Transactional` theo môi trường JTA mở/điều phối transaction.

Không sử dụng `em.getTransaction().begin()` hoặc `em.getTransaction().commit()` với container-managed JTA EntityManager như ở resource-local. Cũng không tự `em.close()` trên EntityManager do container quản lý.

Một **unsynchronized persistence context** còn có quy tắc join transaction riêng. Nếu context chưa tham gia transaction phù hợp, cần xử lý `joinTransaction()` theo đặc tả trước khi flush; đừng xem flush là lệnh tự join transaction.

## 14. AUTO và COMMIT: flush tường minh khác auto-flush

JPA có hai flush mode quan trọng:

```java
em.setFlushMode(FlushModeType.AUTO);
em.setFlushMode(FlushModeType.COMMIT);
```

| Chế độ | Ý nghĩa tổng quan |
|---|---|
| `AUTO` | Provider phải bảo đảm những thay đổi cần ảnh hưởng tới query được phản ánh theo hợp đồng; có thể flush trước query hoặc theo cách hợp lệ khác |
| `COMMIT` | Nhấn mạnh đồng bộ ở commit; tác động của thay đổi chưa flush đến query trước commit không được quy định hoàn toàn portable |

### 14.1. Flush tường minh vẫn có tác dụng khi mode là COMMIT

```java
em.setFlushMode(FlushModeType.COMMIT);
em.persist(product);
em.flush();
```

Dù flush mode là COMMIT, việc gọi `em.flush()` tường minh vẫn yêu cầu đồng bộ pending changes tại thời điểm đó.

Flush mode điều chỉnh **thời điểm đồng bộ tự động**, không biến `flush()` thành no-op theo mặc định.

### 14.2. Một query có thể làm lỗi xuất hiện trước flush tường minh

```java
em.persist(product);

long count = em.createQuery(
    "select count(p) from Product p",
    Long.class
).getSingleResult();

em.flush();
```

Với `AUTO`, provider có thể flush trước query để bảo đảm kết quả phù hợp. Như vậy, lỗi UNIQUE có thể xuất hiện ở `getSingleResult()` **trước khi code tới `em.flush()`**.

Điều này không mâu thuẫn với flush tường minh; nó cho thấy provider có thể đồng bộ tự động để đáp ứng ngữ nghĩa query.

### 14.3. Đừng dùng FlushMode.COMMIT để “né lỗi”

Chuyển từ AUTO sang COMMIT không làm dữ liệu sai trở nên hợp lệ. Lỗi chỉ có thể xuất hiện ở thời điểm khác, thường gần commit. Nếu cần xác định lỗi ở một mốc, dùng explicit flush với transaction phù hợp; không thay đổi flush mode để che vấn đề.

## 15. Vì sao không nên flush trong mọi vòng lặp?

Một anti-pattern:

```java
for (ProductInput input : inputs) {
    Product product = toProduct(input);
    em.persist(product);
    em.flush(); // Flush sau từng row.
}
```

Mỗi flush có thể:

- Kích hoạt dirty checking/collection synchronization.
- Buộc provider gửi SQL sớm, hạn chế việc gom batch.
- Tăng số round trip đến database.
- Giữ lock lâu hơn trong một transaction dài.
- Tăng khả năng chương trình dừng giữa quy trình vì constraint vốn có thể xử lý theo batch.

### 15.1. Flush theo batch

```java
int batchSize = 100;

for (int i = 1; i <= inputs.size(); i++) {
    Product product = toProduct(inputs.get(i - 1));
    em.persist(product);

    if (i % batchSize == 0) {
        em.flush(); // Điểm kiểm tra cho batch.
        em.clear(); // Detach các entity để kiểm soát memory.
    }
}

em.flush();
em.clear();
```

Cách này có thể giảm kích thước persistence context, nhưng cần lưu ý:

- `clear()` detach tất cả managed entities, không chỉ những Product mới.
- Nếu còn entity chưa flush, clear có thể làm mất pending changes.
- Một transaction vẫn có thể bao trùm nhiều batch; flush không commit từng batch.
- Nếu cần biết chính xác row nào sai, có thể phải log ID/SKU của batch hoặc thử quy trình kiểm tra riêng sau khi rollback.
- Với IDENTITY, provider có thể gửi INSERT từng dòng sớm nên hiệu quả batch khác với SEQUENCE.
- Chia transaction theo batch là quyết định khác, có thể dẫn đến commit từng phần.

Không lựa chọn batch size một cách máy móc; đo thời gian flush, số SQL, memory và các ràng buộc ứng dụng.

## 16. Flush có thể phát hiện lỗi ở DELETE và relationship

Không chỉ `persist` mới cần kiểm tra sớm. Giả sử một danh mục `Category` vẫn được nhiều Product tham chiếu qua FK. Service gọi:

```java
Category category = em.find(Category.class, categoryId);
em.remove(category);
em.flush();
```

Nếu database có foreign key không cho xóa Category đang được tham chiếu, `DELETE` có thể thất bại ở flush. Thay vì chỉ biết lỗi ở commit, service có cơ hội phân loại “không thể xóa danh mục đang được sử dụng”.

Tương tự:

- Thêm quan hệ many-to-many có thể INSERT join row trùng unique key.
- Đổi FK sang entity không tồn tại có thể vi phạm foreign key.
- Xóa entity cha trước khi xử lý entity con có thể gặp constraint.
- Xóa/đổi collection với orphan removal hoặc cascade có thể sinh thêm SQL ngoài dự đoán.

**Flush không tự sửa ownership của association.** Nếu quan hệ hai chiều chỉ đổi inverse collection nhưng không đổi owning side, có thể không có SQL FK như mong muốn. Flush không làm một object graph sai trở nên đúng. Helper method phải đồng bộ hai phía và mapping phải chính xác.

## 17. Flush trước khi dùng dữ liệu mới trong cùng transaction

Đôi khi bước sau dùng SQL/native query, stored procedure hoặc thao tác JDBC cần nhìn thấy những row vừa tạo trong **cùng transaction**.

Ví dụ:

```java
em.persist(product);

em.flush();

// Sau mốc này, với cùng transaction và connection phù hợp,
// SQL liên quan có thể thấy thay đổi đã được đồng bộ.
runNativeProcedureDependingOnProduct();
```

Nhưng cần phân biệt:

- JPQL với `FlushModeType.AUTO` có quy tắc bảo đảm kết quả liên quan; không phải mọi query đều cần explicit flush.
- Native SQL, JDBC trực tiếp hoặc stored procedure có thể cần xem chính xác transaction/connection integration.
- Nếu stored procedure chạy **một transaction khác**, flush chưa commit không bảo đảm transaction kia thấy row.
- Flush không bảo đảm side effect ngoài DB sẽ rollback.

Do đó chỉ đặt explicit flush trước procedure khi đã hiểu **cùng transaction hay khác transaction**, và provider có tự flush phù hợp hay không.

## 18. Flush để phát hiện lỗi sớm trước bước không thể rollback: vẫn chưa đủ

Một tình huống dễ gây sai lầm:

```java
em.persist(product);
em.flush(); // Không ném lỗi.

paymentGateway.chargeCustomer(...);

tx.commit(); // Có thể thất bại.
```

Dù flush thành công, **commit vẫn có thể rollback**. Nhưng tiền đã bị trừ qua payment gateway thường không thể tự rollback bằng DB transaction.

Vì vậy **không dùng flush như sự bảo đảm để thực hiện side effect không thể thu hồi**.

Các giải pháp phù hợp hơn:

- Transactional outbox cho event cần phát ra bên ngoài.
- Transaction synchronization/event sau commit.
- Cơ chế idempotency và retry có kiểm soát.
- Saga/compensation nếu quy trình phân tán nhiều bước.
- Thiết kế rõ trạng thái thanh toán để xử lý khi giao dịch mạng thất bại hoặc kết quả không chắc chắn.

`flush` hữu ích cho **lỗi SQL sớm**, không phải cơ chế giao dịch phân tán.

### 18.1. @PostPersist cũng không phải after commit

Callback `@PostPersist` có thể xảy ra sau một lần INSERT ở persist/flush, nhưng không đồng nghĩa transaction đã commit. Không phát email/notification thành công chỉ từ callback này.

## 19. Bean Validation và lỗi trước flush

Nếu tích hợp Jakarta Bean Validation:

```java
@NotBlank
@Column(nullable = false)
private String name;

@PositiveOrZero
@Column(nullable = false)
private BigDecimal price;
```

Application hoặc provider có thể kiểm tra state trước khi SQL chạy. Do đó:

```java
em.persist(product);
em.flush();
```

có thể ném exception về validation trong pipeline trước JDBC hoặc ngay khi thực hiện persistence operation.

Một mô hình nhiều lớp:

```text
Input validation / business rules
            |
            v
Entity constructor / domain invariant
            |
            v
Jakarta Bean Validation (nếu tích hợp)
            |
            v
JPA mapping + provider state checks
            |
            v
SQL tại flush / auto-flush / commit
            |
            v
Database constraints
            |
            v
Transaction commit
```

**Không dùng flush như validation framework.** Input sai cần được chặn sớm bằng rule rõ ràng; database constraints là lớp bảo vệ cuối cùng cho consistency và concurrency.

## 20. Flush và optimistic/pessimistic locking

### 20.1. Optimistic locking với @Version

Entity có `@Version` cho phép provider phát hiện cập nhật stale, thường bằng điều kiện version trong UPDATE/DELETE.

Explicit flush có thể giúp thực thi UPDATE sớm và nhận `OptimisticLockException` trước những bước tiếp theo. Nhưng conflict cũng có thể được phát hiện ở commit hoặc operation khác. Sau optimistic lock failure, rollback và tải lại trong context mới là hướng xử lý phổ biến.

### 20.2. Pessimistic locking

Khi ứng dụng gọi:

```java
Product product = em.find(
    Product.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);
```

database/provider có thể lấy lock trước khi cập nhật. Flush vẫn cần để đồng bộ thay đổi pending, nhưng **không phải lệnh lấy lock thay thế**. Nếu cần bảo vệ invariant cạnh tranh, chọn lock mode/isolation phù hợp chứ không chỉ flush sớm.

### 20.3. Không coi flush là concurrency control

Một flush thành công không ngăn transaction khác cập nhật mọi thứ trong tương lai. Cơ chế concurrency control thuộc về version, lock, isolation và constraints, không chỉ thời điểm SQL được gửi.

## 21. Bulk JPQL/SQL và managed state

Một bulk update:

```java
int changed = em.createQuery(
    """
    update Product p
    set p.price = :newPrice
    where p.sku like :prefix
    """
)
.setParameter("newPrice", new BigDecimal("100000"))
.setParameter("prefix", "PROMO-%")
.executeUpdate();
```

được thực thi như bulk DML và **không tự cập nhật trạng thái các Product managed đã load** theo cách dirty checking entity bình thường.

Nếu trước đó có pending changes ở persistence context, ứng dụng cần quyết định thứ tự:

```java
em.flush(); // Đồng bộ entity changes hiện có trước bulk DML.

em.createQuery(...).executeUpdate();

em.clear(); // Khi phù hợp để tránh dùng managed state stale.
```

Tuy nhiên `clear` detach toàn bộ entity, và bulk operation có thể có semantics version/cascade khác update từng managed entity. Hãy cân nhắc transaction boundary, lock và khối lượng dữ liệu; không dùng một flush để “làm mới” entities sau bulk DML.

## 22. Nên dùng flush ở đâu để nhận diện nguyên nhân lỗi?

### 22.1. Đặt theo ranh giới nghiệp vụ

Nếu một transaction gồm ba giai đoạn:

1. Tạo phiếu đăng ký.
2. Ghi các dòng chi tiết.
3. Tạo bản ghi phân bổ liên quan.

Có thể đặt flush tại mốc có ý nghĩa, chẳng hạn **sau khi tạo phiếu và chi tiết**, trước khi bắt đầu tính phân bổ tốn kém. Một mốc như vậy dễ liên hệ với nhóm pending changes hơn so với chờ commit cuối cùng.

### 22.2. Flush không tự gắn lỗi với một entity

Một flush có thể bao gồm nhiều INSERT/UPDATE/DELETE. Để debug:

- Ghi mã nghiệp vụ/ID tương ứng với nhóm dữ liệu đang xử lý.
- Dùng SQL logging của provider trong môi trường phù hợp.
- Quan sát SQL/bind parameters nếu được phép; tránh lộ thông tin nhạy cảm.
- Ghi root cause của exception, SQLState/vendor code nếu có.
- Kiểm tra constraint name trong database error.
- Không suy đoán entity lỗi chỉ dựa vào lời gọi persist gần nhất.

### 22.3. Làm sao báo lỗi thân thiện?

Một workflow tạo Product có thể muốn phân biệt:

- SKU trùng: trả conflict (ví dụ HTTP 409).
- Dữ liệu rỗng: trả validation error (ví dụ HTTP 400).
- FK tham chiếu không tồn tại: trả lỗi nghiệp vụ “không tìm thấy danh mục”.
- Database mất kết nối: trả lỗi hệ thống/tạm thời.

Đừng viết một catch `RuntimeException` rồi luôn quy thành “SKU đã tồn tại”. Một exception có thể đến từ optimistic lock, timeout, mapping, transaction hoặc những entity pending khác.

Ở các framework như Spring, có thể có cơ chế dịch exception database sang kiểu liên quan constraint/integrity, nhưng phụ thuộc provider và đường gọi. Ở JPA chuẩn, thường cần xem root cause thay vì dựa trên một subtype chung cho tất cả database.

## 23. Kiểm thử flush với lỗi sớm

### 23.1. Test vi phạm UNIQUE

Giả sử database có unique constraint thật trên `product.sku`. Tạo trước một Product:

```java
// Trong setup transaction đã commit:
persistProduct("SKU-001");
```

Trong test khác:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

try {
    Product duplicate = new Product(
        "SKU-001",
        "Duplicate product",
        new BigDecimal("150000")
    );

    em.persist(duplicate);

    // Nếu ràng buộc UNIQUE được kiểm tra ngay khi
    // INSERT chạy, lỗi có thể xuất hiện ở đây.
    em.flush();

    throw new AssertionError(
        "Kỳ vọng lỗi UNIQUE khi đồng bộ dữ liệu"
    );
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }

    // Trong test thực tế, phân biệt AssertionError với
    // database exception và assert root cause phù hợp.
}
```

Đoạn này minh họa ý tưởng, **chưa phải test assertion hoàn chỉnh**. Một test đáng tin cậy phải phân loại exception thật, dùng dữ liệu setup không trùng ngoài ý muốn, rollback/cleanup đúng và không catch lỗi assertion như thể đó là lỗi database.

### 23.2. Mẫu JUnit nhận lỗi bằng assertThrows

Trong môi trường JUnit 5, nếu đã kiểm soát schema và provider:

```java
tx.begin();

try {
    Product duplicate = new Product(
        "SKU-001",
        "Duplicate product",
        new BigDecimal("150000")
    );

    em.persist(duplicate);

    org.junit.jupiter.api.Assertions.assertThrows(
        jakarta.persistence.PersistenceException.class,
        em::flush
    );
} finally {
    if (tx.isActive()) {
        tx.rollback();
    }
}
```

Mẫu này giả định provider bọc lỗi constraint trong `PersistenceException` tại flush. Trong một số cấu hình exception có thể thuộc subtype/provider riêng, hoặc INSERT xảy ra sớm tại `persist` nếu dùng IDENTITY, hoặc constraint được hoãn tới commit. Vì vậy, **chọn setup với ID strategy và constraint timing phù hợp**; không dùng cùng expectation cho mọi DB/provider mà không điều chỉnh.

### 23.3. Test rollback sau flush thành công

Một test khác kiểm chứng flush không commit:

```java
tx.begin();

Product product = new Product(
    "SKU-TEMP",
    "Temporary product",
    new BigDecimal("10000")
);

em.persist(product);
em.flush();
Long id = product.getId();

tx.rollback();

// Mở context mới để kiểm tra row không được commit.
EntityManager verifyEm = emf.createEntityManager();
try {
    Product found = verifyEm.find(Product.class, id);
    // Nếu không có dữ liệu trước đó cùng ID,
    // kỳ vọng found == null.
} finally {
    verifyEm.close();
}
```

Giả định đây là row mới chỉ do transaction vừa rollback tạo ra. Test nên dùng dữ liệu riêng và không dựa vào ID cố định.

### 23.4. Test trong Spring có @Transactional

Nhiều test Spring `@Transactional` mặc định rollback sau test. Vì vậy test chỉ gọi repository save mà không flush có thể **không phát lộ constraint violation** như một transaction production commit.

Nếu mục tiêu là test lỗi SQL sớm:

```java
repository.save(product);
repository.flush();
```

Nhưng nếu ràng buộc được defer tới commit, flush trong test vẫn không phát hiện. Khi cần kiểm tra commit failure, thiết kế test transaction thực sự commit với cleanup thích hợp, thay vì chỉ quan sát rollback mặc định.

### 23.5. Khi nào cần log SQL?

Với Hibernate, có thể bật logging SQL ở mức phù hợp và xem thống kê prepared statements; với EclipseLink, dùng logging/diagnostics theo phiên bản. Không đồng nhất một lần `em.flush()` với một câu SQL.

Khi log bind parameters chứa email, địa chỉ, token hoặc thông tin nhạy cảm, cần che hoặc giới hạn môi trường logging theo chính sách bảo mật.

## 24. Những hiểu nhầm phổ biến

### 24.1. “Gọi flush sẽ commit ngay”

**Sai.** Flush đồng bộ state trong transaction; commit mới xác nhận thay đổi.

### 24.2. “Flush thành công nghĩa là chắc chắn commit thành công”

**Sai.** Deferred constraints, conflict mới, lỗi kết nối hoặc những thay đổi sau flush có thể khiến commit thất bại.

### 24.3. “Persist lúc nào cũng chờ flush mới INSERT”

**Sai.** IDENTITY hoặc provider có thể cần SQL sớm; `persist` có thể phát INSERT trước explicit flush.

### 24.4. “Mọi lỗi database đều xuất hiện ở flush”

**Sai.** Có lỗi xuất hiện trước SQL (validation/provider), có lỗi chờ commit (deferred constraint, transaction conflict), và có lỗi phát sinh sau flush.

### 24.5. “Flush chỉ đồng bộ entity vừa persist”

**Sai.** Flush đồng bộ pending changes liên quan của **toàn persistence context**, kể cả UPDATE, DELETE, cascade và join table.

### 24.6. “Flush một entity bằng em.flush(entity)”

**Sai.** JPA chuẩn có `EntityManager.flush()` không nhận tham số entity; không có API chuẩn `flush(entity)`.

### 24.7. “Thử catch PersistenceException rồi tiếp tục transaction”

**Nguy hiểm.** Transaction có thể bị rollback-only và context không còn đáng tin. Cần rollback/kết thúc unit of work.

### 24.8. “Flush thay thế validate input”

**Sai.** Constructor, Bean Validation và business validation vẫn cần thiết. Database constraint là lớp bảo vệ cuối cùng.

### 24.9. “Flush có thể bảo đảm email thanh toán gửi ra ngoài an toàn”

**Sai.** External side effects không rollback cùng DB; dùng after-commit/outbox/idempotency.

### 24.10. “Đổi FlushMode sang COMMIT khiến explicit flush vô hiệu”

**Sai.** `em.flush()` tường minh vẫn yêu cầu đồng bộ tại mốc đó trong transaction phù hợp.

### 24.11. “Dùng AUTO thì không thể có lỗi trước flush tường minh”

**Sai.** Query hoặc provider có thể tự flush để đáp ứng ngữ nghĩa query trước khi đến dòng explicit flush.

### 24.12. “Flush sau mỗi persist luôn tối ưu”

**Sai.** Flush quá thường xuyên có thể làm giảm batching và tăng round trip/chi phí xử lý.

### 24.13. “Có unique check trước persist thì không cần database constraint”

**Sai.** Hai transaction có thể cùng vượt qua pre-check. DB unique constraint vẫn cần thiết.

### 24.14. “Flush sửa được lỗi quan hệ hai chiều”

**Sai.** Flush không tự sửa một owning side bị bỏ quên. Phải cập nhật graph và FK owner đúng.

### 24.15. “Sau flush đọc lại bằng cùng EntityManager là kiểm chứng commit”

**Sai.** `find` có thể trả managed instance từ context, chưa chắc đọc database và chưa chứng minh commit.

### 24.16. “@PostPersist là dấu hiệu DB transaction đã commit”

**Sai.** Callback có thể được gọi trong quá trình flush trước commit.

### 24.17. “Flush có thể thay @Version hoặc lock”

**Sai.** Flush là đồng bộ; concurrency control cần version/lock/isolation/constraint phù hợp.

### 24.18. “Clear luôn nên gọi ngay sau flush”

**Không luôn đúng.** `clear()` detach toàn bộ managed entities, có thể làm code sau đó sửa detached object mà không lưu. Chỉ clear nếu đã thiết kế lifecycle/batch phù hợp.

### 24.19. “Lỗi tại flush chắc chắn do dòng persist gần nhất”

**Sai.** Có thể do bất kỳ pending change liên quan trong context.

### 24.20. “Nếu flush thất bại thì chỉ cần gọi flush lại”

**Sai.** Transaction/context có thể bị lỗi. Phải xử lý rollback và dùng transaction/context mới khi retry theo chính sách.

## 25. Khi nào nên và không nên flush tường minh?

| Tình huống | Có nên cân nhắc explicit flush? | Lý do |
|---|---|---|
| Lưu một entity rồi commit ngay | Thường không cần | Commit đã là mốc đồng bộ |
| Cần phát hiện UNIQUE/FK sớm trước tính toán lớn | Có | Lỗi SQL có thể xuất hiện trước công việc tốn kém |
| Cần xác định optimistic lock conflict trước bước tiếp | Có, nhưng không bảo đảm phát hiện hết | UPDATE có thể kiểm tra version khi flush |
| Cần chạy native SQL/stored procedure phụ thuộc dữ liệu mới trong cùng transaction | Có thể | Cần đồng bộ pending entity state trước truy vấn đặc thù |
| Import nhiều nghìn bản ghi | Flush theo batch phù hợp | Kiểm soát memory và mốc lỗi |
| Sau mỗi field setter | Không | Tăng overhead, không có lợi ích rõ |
| Sau mỗi persist trong vòng lặp | Thường không | Giảm hiệu quả batching |
| Trước gửi email/thanh toán để “bảo đảm thành công” | Không đủ | Flush không commit |
| Muốn thay thế Bean Validation | Không | Không phải tầng validation nghiệp vụ |
| Muốn tự xóa trạng thái managed | Không | Đó là vấn đề detach/clear |
| Muốn transaction khác đọc được row mới | Không đủ | Phải xem commit/isolation |
| Muốn biến transaction rollback-only thành hợp lệ | Không | Phải rollback và bắt đầu unit of work mới |

Một quy tắc thực dụng:

> **Chỉ thêm `flush()` tại nơi bạn có lý do rõ ràng để cần dữ liệu đã đồng bộ hoặc để lỗi SQL phát sinh trước một bước quan trọng.** Nếu không có lý do như vậy, hãy để provider flush ở những mốc tự nhiên.

## 26. Bài tập thực hành

### Bài 1: Phân biệt flush và commit

```java
tx.begin();
em.persist(new Product("SKU-A", "A", price));
em.flush();
tx.rollback();
```

**Câu hỏi:** Product có được commit không?

**Gợi ý:** Không. Flush chỉ đồng bộ SQL trong transaction; rollback hủy thay đổi.

### Bài 2: UNIQUE phát hiện sớm

Một service tạo Product trùng SKU rồi chạy tác vụ tính báo cáo lớn trước commit.

**Câu hỏi:** Đặt flush ở đâu để tránh tính toán vô ích khi constraint được kiểm tra lúc INSERT?

**Gợi ý:** Sau khi persist Product và trước báo cáo, trong transaction thích hợp; nhưng vẫn phải xử lý commit failure.

### Bài 3: IDENTITY và INSERT

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

**Câu hỏi:** Có thể giả định lỗi UNIQUE chỉ xuất hiện tại `em.flush()` không?

**Gợi ý:** Không. Với IDENTITY provider có thể INSERT sớm khi persist để lấy ID.

### Bài 4: SQL từ nhiều entity

```java
em.persist(productA);
em.persist(productB);
account.rename("New");
em.flush();
```

**Câu hỏi:** Nếu flush báo lỗi, có thể kết luận Product B sai?

**Gợi ý:** Không. Flush đồng bộ các pending changes; lỗi có thể đến từ Product A, B hoặc Account.

### Bài 5: Deferred constraint

Database cấu hình UNIQUE được kiểm tra tại commit. `flush` thành công.

**Câu hỏi:** Có thể thông báo transaction chắc chắn thành công chưa?

**Gợi ý:** Chưa. Commit vẫn có thể báo constraint violation.

### Bài 6: Xử lý lỗi tại flush

```java
try {
    em.flush();
} catch (PersistenceException ex) {
    em.persist(other);
}
```

**Câu hỏi:** Vì sao nguy hiểm?

**Gợi ý:** Transaction có thể đã rollback-only, context không còn đáng tin. Nên rollback/kết thúc unit of work, phân loại lỗi và retry trong transaction mới nếu phù hợp.

### Bài 7: Cạnh tranh unique SKU

Hai transaction cùng query không thấy SKU trước khi persist.

**Câu hỏi:** Explicit flush có thay UNIQUE constraint trong DB không?

**Gợi ý:** Không. Flush không giải quyết race condition chỉ bằng việc đổi thời điểm SQL.

### Bài 8: Optimistic locking

Hai EntityManager đọc cùng Account version 3; A commit tăng version lên 4; B sửa và gọi flush.

**Câu hỏi:** B có thể nhận lỗi gì? Có bảo đảm lỗi chỉ ở flush?

**Gợi ý:** `OptimisticLockException` có thể xuất hiện tại flush/commit tùy provider. Không bảo đảm một mốc duy nhất.

### Bài 9: FlushMode.COMMIT

```java
em.setFlushMode(FlushModeType.COMMIT);
em.persist(product);
em.flush();
```

**Câu hỏi:** Explicit flush có bị bỏ qua không?

**Gợi ý:** Không. Trong transaction phù hợp, flush tường minh vẫn yêu cầu đồng bộ.

### Bài 10: AUTO và JPQL

```java
em.persist(product);
long count = em.createQuery(
    "select count(p) from Product p", Long.class
).getSingleResult();
em.flush();
```

**Câu hỏi:** Lỗi có thể xuất hiện trước dòng flush tường minh không?

**Gợi ý:** Có. Provider có thể auto-flush trước query với mode AUTO.

### Bài 11: Test rollback

Một integration test gọi persist, flush rồi rollback.

**Câu hỏi:** Test `em.contains(product)` hoặc `em.find` cùng context có chứng minh row đã commit không?

**Gợi ý:** Không. Cần đọc lại ở context mới sau commit khi mục tiêu là xác nhận dữ liệu bền vững.

### Bài 12: Batch import

Service import 20.000 Product và flush mỗi row.

**Câu hỏi:** Cải thiện như thế nào?

**Gợi ý:** Cân nhắc flush/clear theo batch, giữ transaction boundary phù hợp, đo SQL/memory. Nếu muốn commit từng batch, cần transaction theo chunk, không chỉ flush.

### Bài 13: Gửi thông báo sau flush

```java
em.persist(product);
em.flush();
notificationService.sendCreated(product);
tx.commit();
```

**Câu hỏi:** Còn rủi ro gì?

**Gợi ý:** Commit vẫn có thể thất bại nhưng thông báo đã gửi. Nên dùng after-commit hoặc outbox.

### Bài 14: FK bị lỗi

Order mới tham chiếu Customer ID không tồn tại bằng `getReference`.

**Câu hỏi:** Lỗi có thể xuất hiện khi nào?

**Gợi ý:** Khi truy cập reference, lúc provider thực thi INSERT (có thể tại flush), hoặc tại commit tùy ràng buộc/provider. Cần kiểm tra existence/authorization theo yêu cầu nghiệp vụ.

### Bài 15: Có nên flush sau mọi setter?

```java
product.changePrice(newPrice);
em.flush();
product.changeName(newName);
em.flush();
```

**Câu hỏi:** Có lợi ích chắc chắn gì so với đổi cả hai thuộc tính rồi flush một lần?

**Gợi ý:** Không có lợi ích mặc định. Hai flush có thể tạo thêm SQL/overhead, nhất là khi mục tiêu chỉ lưu state cuối.

## 27. Tóm tắt kiến thức trọng tâm

- **`EntityManager.flush()` yêu cầu đồng bộ pending changes trong persistence context với database**, không chỉ một entity riêng.
- **Flush không phải commit.** Transaction vẫn có thể rollback sau khi SQL đã được gửi.
- Flush tường minh hữu ích khi muốn **lỗi ràng buộc/SQL xuất hiện trước các bước nghiệp vụ tiếp theo**, nhất là UNIQUE, NOT NULL, FK, CHECK hoặc optimistic locking.
- **Không có bảo đảm mọi lỗi sẽ xuất hiện tại flush**: IDENTITY có thể INSERT sớm; deferred constraints, conflict hoặc lỗi commit có thể xuất hiện muộn.
- **Lỗi flush thường khiến transaction không còn dùng tiếp an toàn**. Cần rollback/kết thúc đơn vị công việc, không catch rồi tiếp tục ghi.
- **`FlushModeType.AUTO` có thể auto-flush trước query**; `FlushModeType.COMMIT` không vô hiệu hóa explicit flush.
- **Không flush sau mọi thao tác nhỏ** nếu không có nhu cầu; việc đó có thể giảm hiệu quả batching và tăng round trip.
- **Dùng constraints thật ở database** để bảo vệ dữ liệu khi đồng thời; pre-check trước persist không thay unique key.
- **Đừng dùng flush làm “commit sớm” trước email, thanh toán hoặc event bên ngoài**. Cần after-commit, outbox hoặc cơ chế phân tán tương ứng.
- **Test cần phân biệt managed state, SQL đã flush và transaction đã commit**; đọc lại bằng context mới sau commit để xác nhận dữ liệu bền vững.

**Kết luận:** Thực hiện **flush tường minh để xác định lỗi sớm** là kỹ thuật đặt một **điểm đồng bộ có chủ đích** giữa các bước nghiệp vụ JPA. Khi sử dụng đúng, `em.flush()` có thể làm constraint violation và optimistic locking conflict xuất hiện trước khi service thực hiện những bước tiếp theo, giúp debug và xử lý transaction rõ ràng hơn. Nhưng **flush không thay transaction, không bảo đảm commit và không thay business validation hay database constraints**. Hãy đặt flush đúng ranh giới cần kiểm tra, xử lý exception bằng rollback và để commit quyết định kết quả cuối cùng của thao tác ghi.
