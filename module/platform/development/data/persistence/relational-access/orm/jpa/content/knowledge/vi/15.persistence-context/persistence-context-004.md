# Tìm entity bằng find và hành vi khi entity đã được quản lý

Trong JPA, `EntityManager.find()` là cách trực tiếp nhất để truy xuất một entity bằng **giá trị khóa chính**. Khi tìm được bản ghi, kết quả không chỉ là một object Java chứa dữ liệu: nó còn liên quan đến **persistence context**, nơi JPA quản lý identity, trạng thái và các thay đổi của entity.

Một đặc điểm rất quan trọng là: **nếu entity với khóa đó đã được quản lý trong persistence context hiện tại, `find()` trả về chính instance đang managed**, chứ không tạo thêm một object Java độc lập cho cùng entity. Điều này giải thích tại sao hai lần `find()` thường cho kết quả `a == b` là `true`, vì sao lần tìm thứ hai có thể không phát sinh `SELECT`, và vì sao dữ liệu từ `find()` không nhất thiết là bản cập nhật mới nhất của database.

Bài học trình bày cú pháp `find()`, identity map/first-level cache, vòng đời managed entity, dirty checking, ảnh hưởng của transaction và cache, sự khác biệt giữa `find()` và `getReference()`, cùng những lỗi dễ gặp khi dùng nhiều EntityManager hoặc Spring Data JPA.

## 1. Bài toán: tải cùng một sản phẩm hai lần

Giả sử bảng `products` chứa:

| id | sku | name | price |
|---:|---|---|---:|
| 42 | JAVA-042 | Java Fundamentals | 250000 |
| 43 | DB-043 | Database Design | 190000 |

Entity JPA:

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 40)
    private String sku;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false, precision = 15, scale = 2)
    private BigDecimal price;

    @Version
    private Long version;

    protected Product() {}

    public Product(String sku, String name, BigDecimal price) {
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

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public Long getVersion() {
        return version;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không được rỗng");
        }
        this.name = newName;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Giá không hợp lệ");
        }
        this.price = newPrice;
    }
}
~~~

Ví dụ sử dụng:

~~~java
EntityManager em = entityManagerFactory.createEntityManager();
try {
    Product first = em.find(Product.class, 42L);
    Product second = em.find(Product.class, 42L);

    if (first != null) {
        System.out.println(first == second); // true
    }
} finally {
    em.close();
}
~~~

Hai lời gọi sử dụng **cùng EntityManager**, tức cùng persistence context trong ví dụ này. Nếu Product ID 42 tồn tại và được quản lý, cả hai biến tham chiếu **cùng một object Java**.

Điều đáng nhớ: JPA duy trì **một instance managed cho một entity identity trong một persistence context**. Đây không phải quy tắc áp dụng cho mọi object Java trên toàn JVM hay mọi phiên truy cập database.

## 2. Cú pháp và ý nghĩa của EntityManager.find()

Chữ ký cơ bản:

~~~java
<T> T find(Class<T> entityClass, Object primaryKey);
~~~

Trong đó:

- `entityClass`: lớp entity JPA cần tìm, ví dụ `Product.class`.
- `primaryKey`: giá trị khóa chính của entity, ví dụ `42L` nếu `@Id` có kiểu `Long`.
- Kiểu trả về là entity tương ứng nếu tìm thấy, hoặc `null` nếu không có entity với khóa đó.
- Phương thức tìm **theo khóa chính**, không tìm theo tên, SKU, email hay các trường nghiệp vụ khác.

Ví dụ:

~~~java
Product product = em.find(Product.class, 42L);

if (product == null) {
    throw new IllegalArgumentException("Sản phẩm không tồn tại");
}

System.out.println(product.getName());
~~~

Nếu muốn tìm theo SKU, dùng JPQL, Criteria API hoặc repository query, không dùng `find(Product.class, "JAVA-042")` trừ khi SKU thực sự là trường `@Id`.

### 2.1. Các overload khác của find()

JPA còn cung cấp các overload để chọn lock mode hoặc truyền properties/hints:

~~~java
Product p1 = em.find(Product.class, 42L);

Product p2 = em.find(
    Product.class,
    42L,
    LockModeType.OPTIMISTIC
);

Product p3 = em.find(
    Product.class,
    42L,
    java.util.Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
~~~

Các overload không thay đổi mục tiêu cơ bản: tìm entity theo primary key trong ngữ cảnh quản lý của EntityManager. Nhưng lock/hints có ý nghĩa khác và cần hiểu rõ transaction/provider. Đặc biệt, hint cache không tự động biến một managed entity thành dữ liệu mới từ database; phần này sẽ được phân tích ở mục về freshness.

### 2.2. Nếu không tìm thấy thì sao?

~~~java
Product missing = em.find(Product.class, 999999L);

System.out.println(missing == null); // true nếu không có entity đó
~~~

`find()` **không mặc định ném `EntityNotFoundException` chỉ vì ID không tồn tại**. Nó thường trả `null`. Tuy nhiên, các lỗi khác vẫn có thể xảy ra, ví dụ:

- Truyền class không phải entity hoặc kiểu khóa chính không hợp lệ: có thể có `IllegalArgumentException`.
- Không thể truy cập database: có thể phát sinh `PersistenceException` hoặc exception của provider.
- Lock không lấy được hoặc phiên bản xung đột: có thể phát sinh exception liên quan locking/optimistic locking.
- Transaction bị lỗi hoặc không đáp ứng điều kiện lock mode: có thể phát sinh exception transaction.

Không viết code giả định rằng mọi lời gọi `find()` chỉ có hai kết quả thành công hoặc `null`. Cần thiết kế handling phù hợp với tầng service và lỗi thực tế.

### 2.3. Vì sao dùng Long thay vì int hoặc String tùy ý?

Nếu entity khai báo:

~~~java
@Id
private Long id;
~~~

thì khóa được truyền theo kiểu tương thích, ví dụ `42L`. Đừng giả định giá trị chuỗi `"42"` sẽ được provider tự chuyển an toàn thành `Long`. API JPA có quyền từ chối khóa sai kiểu.

Nếu ID được gán bằng chuỗi:

~~~java
@Id
private String sku;
~~~

thì có thể gọi `em.find(Product.class, "JAVA-042")` **chỉ khi** class đó thực sự ánh xạ `sku` làm `@Id`. Không nhầm khóa nghiệp vụ có `@Column(unique=true)` với primary key.

## 3. Persistence context là gì?

**Persistence context** là phạm vi JPA dùng để theo dõi các entity đang managed. Mỗi EntityManager application-managed thường gắn với một persistence context; trong môi trường container/Spring, EntityManager được inject có thể là proxy dẫn đến context thực tế theo transaction.

Với một entity identity, persistence context duy trì một instance managed đại diện cho identity đó:

~~~text
                 EntityManager / Persistence Context

                       Identity map
            +----------------------------------+
            | (Product.class, 42L)             |
            |            |                     |
            |            v                     |
            |     Product instance A           |
            |     id=42, name="Java..."        |
            |                                  |
            | (Product.class, 43L)             |
            |            |                     |
            |            v                     |
            |     Product instance B           |
            +----------------------------------+
                       |
                       v
                 Database products
                id=42 / id=43 / ...
~~~

Identity được hiểu theo entity type và primary-key value. Hai entity khác lớp nhưng tình cờ cùng ID số 42 không phải một entity.

**Persistence context không phải database, không phải singleton toàn ứng dụng, và không phải cache chung cho mọi transaction.** Nó là môi trường quản lý trạng thái, identity và thao tác đồng bộ của một đơn vị làm việc JPA.

### 3.1. Tính đồng nhất tham chiếu trong cùng context

~~~java
Product a = em.find(Product.class, 42L);
Product b = em.find(Product.class, 42L);

System.out.println(a == b); // true nếu a tồn tại
~~~

Nếu Product 42 đã được managed, JPA không tạo object Product khác cho cùng identity trong context đó. Đây là đặc điểm thường gọi là **identity map** hoặc *first-level cache*.

Hai biến Java có thể trỏ cùng object, nên thay đổi qua một biến sẽ được biến kia nhìn thấy:

~~~java
Product a = em.find(Product.class, 42L);
Product b = em.find(Product.class, 42L);

if (a != null) {
    a.rename("Java Fundamentals - 2nd Edition");
    System.out.println(b.getName());
    // "Java Fundamentals - 2nd Edition"
}
~~~

Sự thay đổi trên là thay đổi **trạng thái cùng object Java**; việc nó được ghi xuống database lúc nào còn phụ thuộc transaction và flush.

### 3.2. Cùng primary key nhưng khác persistence context

~~~java
EntityManager em1 = entityManagerFactory.createEntityManager();
EntityManager em2 = entityManagerFactory.createEntityManager();

try {
    Product fromEm1 = em1.find(Product.class, 42L);
    Product fromEm2 = em2.find(Product.class, 42L);

    if (fromEm1 != null && fromEm2 != null) {
        System.out.println(fromEm1 == fromEm2);
        // false với hai EntityManager/context độc lập

        System.out.println(
            fromEm1.getId().equals(fromEm2.getId())
        ); // true
    }
} finally {
    em1.close();
    em2.close();
}
~~~

Trong hai context độc lập, mỗi context có thể có instance riêng cho cùng bản ghi; đây là kết quả đúng. **JPA entity identity không đồng nhất với Java reference identity ở mọi thời điểm**.

Đặc biệt khi làm việc với controller/service qua nhiều HTTP request, không dùng toán tử `==` để kiểm tra hai entity tải ở hai transaction khác nhau có cùng bản ghi hay không.

### 3.3. Entity đã managed có phải được giữ vĩnh viễn không?

Không. Một entity chỉ managed khi còn thuộc một persistence context đang quản lý nó. Các thao tác như `detach()`, `clear()`, `close()` hoặc kết thúc phạm vi context do container quản lý có thể làm object trở thành detached.

EntityManager cũng không tự động an toàn để chia sẻ giữa nhiều thread. Trong Java SE, mỗi đơn vị công việc thường tạo và đóng EntityManager riêng. `EntityManagerFactory` được thiết kế để chia sẻ và tạo các EntityManager; không chia sẻ một `EntityManager` tùy tiện giữa nhiều request/thread.

## 4. find() có luôn thực hiện SQL SELECT không?

**Không.** Một lời gọi `find()` có thể phải truy cập database, nhưng nếu entity đã managed trong persistence context, provider có thể trả ngay instance hiện có mà không gửi `SELECT` mới.

Tình huống thường gặp:

~~~text
Bước 1: em.find(Product.class, 42L)
        -> Context chưa có Product 42
        -> Có thể gửi SELECT hoặc lấy dữ liệu từ cache được phép
        -> Tạo/nhận managed instance

Bước 2: em.find(Product.class, 42L)
        -> Context đã có Product 42
        -> Trả cùng instance
        -> Thường không gửi SELECT mới

Bước 3: em.find(Product.class, 43L)
        -> Chưa có Product 43
        -> Có thể phải tải dữ liệu tương ứng
~~~

Việc **chưa thấy SQL** khi gọi `find()` không có nghĩa code không thực thi hoặc database không cần thiết. Nó có thể đang sử dụng entity đã có trong context.

### 4.1. First-level cache khác second-level cache

| Cơ chế | Phạm vi | Vai trò | Mức độ mặc định |
|---|---|---|---|
| Persistence context / first-level cache | Từng context JPA | Giữ instance managed, identity map và dirty checking | Là phần thiết yếu của hành vi persistence context |
| Second-level cache / shared cache | Có thể chia sẻ giữa các context theo provider/config | Lưu dữ liệu có thể tái sử dụng qua các context | Tùy provider, entity và cấu hình |
| Query cache | Cache kết quả truy vấn theo provider | Có thể giảm chi phí một số truy vấn | Thường là tính năng riêng của provider |
| Database cache | Bên trong DBMS | Tăng tốc truy cập trang/index/query | Do DBMS quản lý |

Điểm khác biệt quan trọng: first-level cache **giữ object managed của context hiện tại**. Second-level cache không có nghĩa hai EntityManager khác nhau nhất thiết trả **cùng Java object**. Chúng vẫn cần quản lý các instance trong context riêng.

### 4.2. Cùng context, tìm lại không đồng nghĩa refresh

Giả sử:

1. Transaction A tải Product 42 với name = "Java Book".
2. Transaction B cập nhật name của Product 42 thành "Java Book Revised" rồi commit.
3. Trong context A, code gọi `find(Product.class, 42L)` lần nữa.

Nếu Product 42 vẫn đang managed, `find()` có thể trả **instance cũ** với name trước khi B cập nhật. Nó không mặc định tải lại dữ liệu mới nhất.

Đây là hệ quả có chủ đích của identity map và unit-of-work, không phải bug của `find()`. Nếu cần refresh, phải chọn một cơ chế phù hợp với transaction, isolation và yêu cầu đồng thời của ứng dụng.

## 5. Hành vi khi entity đã managed trước lúc gọi find()

Một entity có thể trở thành managed trước lời gọi `find()` do nhiều đường khác nhau:

- Được tải bởi `find()` trước đó.
- Được tải bằng JPQL/Criteria query.
- Được tải qua quan hệ tới entity khác hoặc thao tác navigation.
- Là giá trị trả về của `merge()`.
- Được đưa vào context bởi `persist()`, trong trường hợp entity mới.
- Được lấy qua reference và sau đó được provider quản lý/khởi tạo.

Đối với entity đã managed với cùng identity, `find()` trả instance đang được quản lý thay vì tạo thêm instance mới.

### 5.1. Query trước, find sau

~~~java
Product viaQuery = em.createQuery(
        "SELECT p FROM Product p WHERE p.id = :id",
        Product.class
    )
    .setParameter("id", 42L)
    .getSingleResult();

Product viaFind = em.find(Product.class, 42L);

System.out.println(viaQuery == viaFind); // true
~~~

Ví dụ giả định entity tồn tại và query trả đúng một kết quả. Dù hai con đường truy xuất khác nhau, trong cùng context JPA vẫn giữ **một instance managed cho identity Product 42**.

Cần nhớ: câu JPQL có thể thực hiện SQL ngay cả khi context đang quản lý entity; JPA có thể tái sử dụng instance managed trong kết quả thay vì tạo object thứ hai. **Identity reuse không đồng nghĩa mọi truy vấn JPQL đều được bỏ qua SQL.**

### 5.2. persist() trước, find() sau

~~~java
EntityTransaction tx = em.getTransaction();

tx.begin();

Product created = new Product(
    "JAVA-NEW",
    "New Java Book",
    new BigDecimal("120000.00")
);

em.persist(created);
// ID có thể được gán ở các thời điểm khác nhau tùy strategy.

em.flush(); // Đồng bộ INSERT, chưa commit.

Long id = created.getId();
Product found = em.find(Product.class, id);

System.out.println(created == found); // true

tx.commit();
~~~

Ví dụ sử dụng ID tự sinh và chủ động gọi `flush()` trước khi lấy khóa, để minh họa việc entity đã được context quản lý và có ID khi truy xuất. Thời điểm provider cấp ID trước flush khác nhau với `IDENTITY`, `SEQUENCE`, UUID hoặc chiến lược cụ thể; không dựa vào giả định ID luôn có ngay sau `new`.

Với entity vừa được persist và đang managed, gọi `find()` bằng ID hiện có không có lý do tạo instance thứ hai cho cùng entity identity.

### 5.3. find() sau khi chỉnh sửa một managed entity

~~~java
tx.begin();

Product p = em.find(Product.class, 42L);
if (p != null) {
    p.rename("Java Book Updated");

    Product foundAgain = em.find(Product.class, 42L);

    System.out.println(p == foundAgain); // true
    System.out.println(foundAgain.getName());
    // "Java Book Updated"
}

tx.commit();
~~~

Lần `find()` thứ hai nhìn thấy thay đổi **chưa cần commit** vì đó là cùng object managed. Nhưng điều này **không có nghĩa người dùng khác đã nhìn thấy giá trị ấy trong database**.

## 6. Managed entity, dirty checking và transaction

JPA/Hibernate dùng *dirty checking* để đồng bộ thay đổi của entity managed. Khi một entity được tải trong transaction và thay đổi qua các method nghiệp vụ, provider có thể phát hiện thay đổi và tạo `UPDATE` tại flush/commit.

Ví dụ Java SE với `RESOURCE_LOCAL`:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product = em.find(Product.class, 42L);

    if (product == null) {
        throw new IllegalArgumentException("Product 42 không tồn tại");
    }

    product.rename("Effective Java Persistence");

    tx.commit(); // Flush và commit theo cơ chế JPA.
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Không cần gọi `em.persist(product)` cho một entity đã managed. Cũng không cần gọi `em.merge(product)` chỉ để lưu tên mới: dirty checking trong transaction đã đảm nhiệm việc đồng bộ.

### 6.1. Flush khác commit

- **Flush**: đồng bộ các thay đổi pending trong persistence context xuống database bằng SQL INSERT/UPDATE/DELETE; không mặc nhiên kết thúc transaction.
- **Commit**: xác nhận transaction hoàn tất để dữ liệu được commit theo quy tắc database.
- **Rollback**: hủy các thay đổi transaction chưa commit ở database, nhưng các object Java đang được tham chiếu không tự trở lại giá trị cũ như một phép “undo” trong bộ nhớ.

Ví dụ:

~~~java
tx.begin();
Product p = em.find(Product.class, 42L);

p.rename("Draft name");

em.flush(); // SQL UPDATE có thể được thực thi tại đây.
// Nếu sau đó rollback, database không giữ UPDATE này.

tx.rollback();
~~~

Sau rollback, tùy container/provider, persistence context và các entity trong bộ nhớ có thể không còn phù hợp để tiếp tục công việc. Với Java SE, thường đóng EntityManager rồi bắt đầu đơn vị công việc mới, thay vì tiếp tục dựa vào object graph đã bị rollback.

### 6.2. Có thể find() mà không mở transaction không?

Trong nhiều trường hợp, các thao tác đọc như `find()` có thể thực hiện mà không chủ động begin transaction trên application-managed EntityManager. Nhưng:

- Một số chế độ lock đòi hỏi transaction đang hoạt động.
- Việc thay đổi entity rồi kỳ vọng ghi xuống database khi không có transaction là sai về mô hình transaction.
- Với môi trường container, transaction-scoped persistence context và thời gian managed của object phụ thuộc phạm vi transaction/request thực tế.
- Việc đọc nhất quán cần được thiết kế theo isolation và transaction của use case, không chỉ theo khả năng API đọc một hàng.

Đối với service nghiệp vụ có thao tác cập nhật, nên bao tất cả các bước đọc, kiểm tra, đổi trạng thái và commit vào transaction phù hợp.

## 7. Vòng đời entity và kết quả của find()

Entity JPA thường được xét qua bốn trạng thái:

| Trạng thái | Ý nghĩa | Vai trò của `find()` |
|---|---|---|
| **New/transient** | Java object mới, chưa được context quản lý | Không thể dùng object reference làm PK; chỉ tìm theo ID có ý nghĩa |
| **Managed** | Đang được persistence context theo dõi | Với cùng entity identity, `find()` trả instance managed đó |
| **Detached** | Từng managed nhưng hiện không còn thuộc context | Context khác có thể `find()` để tải một managed instance mới, không “gắn lại” object detached cũ |
| **Removed** | Entity được đánh dấu cần xóa trong context | Không sử dụng `find()` như cách kiểm chứng xóa đã commit; phải xét transaction và trạng thái tương ứng |

Sơ đồ:

~~~text
    new Product(...)
          |
          | em.persist(...)
          v
       MANAGED  <------------- em.find(id)
          |                     |
          | em.detach(),        | entity được tải vào context
          | em.clear(),         |
          | em.close()          |
          v                     |
       DETACHED -- em.merge --> MANAGED COPY
          ^
          |
    Context đóng hoặc entity bị detach

       MANAGED -- em.remove --> REMOVED
~~~

Sơ đồ mô tả các đường thường gặp, không có ý nghĩa mọi object phải đi qua mọi trạng thái theo đúng thứ tự.

### 7.1. detach(): cùng ID, object cũ không được quản lý

~~~java
Product detached = em.find(Product.class, 42L);

em.detach(detached);

Product managedAgain = em.find(Product.class, 42L);

if (managedAgain != null) {
    System.out.println(detached == managedAgain);
    // false trong tình huống đã detach rồi tải lại.
}
~~~

Khi bị detach, object Java cũ vẫn có thể giữ ID và dữ liệu. Nhưng nó không còn được em theo dõi. Một `find()` tiếp theo có thể tạo một instance managed khác cho cùng identity.

Đừng dựa vào `detached == managedAgain` để xác định chúng có cùng bản ghi. Chúng là hai instance Java, nhưng cùng biểu diễn Product ID 42.

### 7.2. clear(): bỏ quản lý mọi entity trong context

~~~java
Product before = em.find(Product.class, 42L);

em.clear(); // Detach toàn bộ managed entities.

Product after = em.find(Product.class, 42L);

if (before != null && after != null) {
    System.out.println(before == after); // false trong ví dụ.
}
~~~

`clear()` **không xóa bảng database** và không làm Java object cũ biến mất. Nó chỉ xóa các thực thể đang được persistence context quản lý khỏi phạm vi theo dõi.

Một điểm quan trọng: nếu có thay đổi pending chưa flush, `clear()` có thể khiến chúng **không được đồng bộ**. Không nên gọi `clear()` tùy tiện sau khi sửa entity mà không hiểu trạng thái flush/transaction.

### 7.3. close(): hết phạm vi EntityManager

~~~java
EntityManager em = emf.createEntityManager();
Product loaded;
try {
    loaded = em.find(Product.class, 42L);
} finally {
    em.close();
}

// loaded vẫn là Java object nếu còn reference,
// nhưng không còn managed bởi EntityManager đã đóng.
~~~

Với application-managed EntityManager, đóng context kết thúc việc theo dõi những entity đó. Trong lần gọi khác với EntityManager mới, `find()` có thể tạo instance Java khác cho cùng PK.

### 7.4. merge() trả về managed instance

~~~java
EntityManager nextEm = emf.createEntityManager();
EntityTransaction tx = nextEm.getTransaction();

try {
    tx.begin();

    Product managed = nextEm.merge(detached);

    // detached vẫn không tự trở thành managed.
    // Đối tượng trả về mới là đối tượng managed ở nextEm.
    managed.rename("Name after merge");

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) tx.rollback();
    throw ex;
} finally {
    nextEm.close();
}
~~~

`merge()` sao chép trạng thái của entity detached vào một managed instance tương ứng, tạo hoặc tìm instance đó trong context đích. Đối tượng được truyền vào **vẫn detached**. Khi đã có instance managed cùng identity, provider hợp nhất trạng thái vào instance đó; điều này liên hệ trực tiếp tới quy tắc một managed instance cho mỗi identity/context.

**Không tự động gọi `merge()` sau mọi `find()`.** Khi entity đã managed, việc làm thêm đó thường không cần thiết và có thể khiến code khó hiểu.

## 8. find() và getReference(): giống và khác

`EntityManager.getReference()` cũng nhận entity class và primary key:

~~~java
Product reference = em.getReference(Product.class, 42L);
~~~

Nhưng mục đích của nó khác `find()`.

| Đặc điểm | `find()` | `getReference()` |
|---|---|---|
| Mục tiêu thường gặp | Tải entity theo PK và dùng dữ liệu của nó | Lấy tham chiếu tới entity theo PK khi chưa cần đọc toàn bộ thuộc tính |
| Khi ID không tồn tại | Thường trả `null` | Có thể ném `EntityNotFoundException` khi truy cập trạng thái, hoặc ngay tại lời gọi tùy provider |
| Có thể trì hoãn SQL | Có nhờ context/shared cache | Có thể cung cấp reference/lazy proxy chưa tải state |
| Đọc field ngoài ID | Thường có state entity để dùng | Có thể buộc provider tải dữ liệu và có thể lỗi nếu entity không tồn tại |
| Dùng với quan hệ khóa ngoại | Được, nhưng có thể phải đọc nhiều dữ liệu hơn cần thiết | Hữu ích để gán association khi biết ID hợp lệ |

Ví dụ khi tạo OrderLine chỉ cần liên kết Product đã có:

~~~java
Product productRef = em.getReference(Product.class, productId);
OrderLine line = new OrderLine(productRef, quantity);

em.persist(line);
~~~

Ví dụ giả định `OrderLine` có mapping `@ManyToOne Product` và constructor phù hợp. Trong tình huống này, `getReference()` có thể tránh truy vấn Product ngay lập tức nếu provider chỉ cần PK để ghi foreign key. **Tuy nhiên, ID không tồn tại vẫn có thể làm transaction thất bại do foreign key**; getReference không thay validation nghiệp vụ.

### 8.1. Proxy và Java class

Hibernate có thể dùng proxy cho lazy reference, nên:

~~~java
reference.getClass() == Product.class
~~~

không phải phép kiểm tra có thể áp dụng mù quáng trong mọi cấu hình. Proxy có thể là subclass hoặc dùng cơ chế enhancement khác.

Tương tự, `find()` có thể gặp entity đã được quản lý dưới dạng proxy/reference. Điều quan trọng là context giữ tính nhất quán identity của entity; không phải mọi chi tiết lớp triển khai của proxy đều theo cách suy đoán.

### 8.2. Cần dữ liệu thật thì dùng find()

Nếu business rule cần kiểm tra `product.getPrice()` hoặc `product.getName()`, `find()` thường thể hiện ý định rõ hơn và cho phép xử lý `null` khi sản phẩm không tồn tại. Khi chỉ gán foreign key biết trước, `getReference()` có thể giảm tải.

Cả hai cách cần được xem xét theo transaction, khóa ngoại, lazy loading và quy tắc kiểm tra dữ liệu thật của domain.

## 9. Tính mới của dữ liệu: find(), refresh() và cache

Giả sử entity đã managed, nhưng một transaction khác cập nhật database. Gọi `find()` lần nữa **không có nghĩa** context tự nhận giá trị mới.

### 9.1. refresh() khi cần tải lại managed entity

~~~java
Product product = em.find(Product.class, 42L);

if (product != null) {
    em.refresh(product);
    System.out.println(product.getName());
}
~~~

`refresh()` yêu cầu provider đồng bộ lại trạng thái của **managed entity** từ nguồn persistence theo quy tắc JPA. Nó có thể ghi đè các thay đổi local chưa lưu trên entity; vì vậy không nên gọi tùy tiện giữa một quy trình đang chỉnh sửa.

Lưu ý:

- `refresh()` hoạt động trên managed entity; gọi trên detached entity có thể phát sinh exception.
- Cách quan sát thay đổi do transaction khác commit còn phụ thuộc isolation, lock và khả năng nhìn thấy của transaction hiện tại.
- Refresh không tự biến quy trình nhiều bước thành atomic; nó không thay thế concurrency control.

### 9.2. CacheRetrieveMode.BYPASS không thay thế clear()/refresh()

Trong JPA, các hint shared cache như:

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);

Product product = em.find(Product.class, 42L, hints);
~~~

có thể điều chỉnh hành vi truy xuất **shared/second-level cache**, tùy provider và cấu hình. Nhưng nếu Product 42 đã nằm trong **persistence context hiện tại**, `find()` vẫn có thể trả instance managed. Đừng mong chỉ truyền `CacheRetrieveMode.BYPASS` là bắt buộc database được truy vấn lại và mọi field được cập nhật.

Khi cần xử lý dữ liệu mới hơn, phải xét context, refresh/clear, transaction isolation, lock và quy tắc cache thực tế.

### 9.3. Transaction isolation có thể khiến dữ liệu vẫn “cũ”

Nếu transaction đang dùng mức cô lập theo snapshot, việc đọc lại có thể tiếp tục nhìn thấy snapshot cũ dù transaction khác đã commit. Cách gọi `refresh()` hay tạo context mới không tự thay đổi mọi bảo đảm isolation của database.

Điều này đặc biệt quan trọng ở những use case kiểm tra số dư, tồn kho, giới hạn đăng ký hoặc dữ liệu nhiều người sửa đồng thời. “Đã gọi SELECT lần nữa” và “đã nhìn thấy phiên bản mới nhất” là hai nhận định khác nhau.

## 10. Lock khi find() và cập nhật đồng thời

`find()` có overload nhận `LockModeType`. Ví dụ:

~~~java
Product product = em.find(
    Product.class,
    42L,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Mục đích là đề nghị khóa theo cơ chế pessimistic locking phù hợp khi tải entity. Các loại lock có cách hoạt động và điều kiện khác nhau tùy JPA provider/DBMS. Với các lock đòi transaction, gọi bên ngoài transaction có thể ném `TransactionRequiredException`.

### 10.1. Optimistic locking qua @Version

Entity Product trong ví dụ có:

~~~java
@Version
private Long version;
~~~

Khi hai transaction cùng sửa Product, provider có thể kiểm tra giá trị version ở thời điểm UPDATE để phát hiện xung đột:

~~~text
Transaction A đọc Product 42, version = 5
Transaction B đọc Product 42, version = 5

B cập nhật và commit -> version = 6
A cố cập nhật dựa trên version = 5
-> Có thể nhận OptimisticLockException khi flush/commit
~~~

Điểm cần nhớ: **cùng entity identity không đồng nghĩa có quyền ghi đè cập nhật của transaction khác**. Identity map quản lý object trong một context; optimistic locking giải quyết một khía cạnh xung đột giữa transaction.

### 10.2. OPTIMISTIC và PESSIMISTIC_WRITE

- `LockModeType.OPTIMISTIC` dùng cơ chế optimistic locking cho entity có hỗ trợ version phù hợp.
- `LockModeType.PESSIMISTIC_READ` hoặc `PESSIMISTIC_WRITE` yêu cầu database/provider phối hợp khóa theo kiểu pessimistic, thường cần transaction.
- Với lỗi timeout, deadlock hoặc không lấy được lock, ứng dụng cần có chính sách retry/rollback thích hợp.
- Không đặt pessimistic lock lên mọi lời gọi find chỉ để “an toàn”: nó có thể làm tăng contention và giảm throughput.

Nếu nghiệp vụ chỉ cần đọc một Product để hiển thị, thường không cần khóa ghi. Nếu đang trừ tồn kho theo giao dịch cạnh tranh, cần quy tắc atomic update/version hoặc locking được thiết kế cho use case đó.

### 10.3. Không phải cứ đã managed thì refresh/lock tự xảy ra

Khi `find()` thấy entity đã managed và bạn truyền lock mode, provider có thể cần thực thi hành vi lock theo yêu cầu. Đừng suy luận một cách tuyệt đối rằng **mọi** `find()` lặp lại đều không có SQL, nhất là khi sử dụng lock, hints hoặc đặc tính khác của provider. Quy tắc quan trọng là identity instance nhất quán; hành vi SQL cụ thể tùy đường đi.

## 11. Khóa chính ghép và find()

`find()` không bị giới hạn ở khóa `Long`. Với entity có composite primary key qua `@EmbeddedId` hoặc `@IdClass`, đối số primary key là object khóa phù hợp.

Ví dụ lớp khóa ghép:

~~~java
package com.example.school;

import jakarta.persistence.*;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class EnrollmentId implements Serializable {

    @Column(name = "student_id")
    private Long studentId;

    @Column(name = "course_id")
    private Long courseId;

    protected EnrollmentId() {}

    public EnrollmentId(Long studentId, Long courseId) {
        this.studentId = studentId;
        this.courseId = courseId;
    }

    public Long getStudentId() {
        return studentId;
    }

    public Long getCourseId() {
        return courseId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof EnrollmentId id)) return false;
        return Objects.equals(studentId, id.studentId)
            && Objects.equals(courseId, id.courseId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(studentId, courseId);
    }
}
~~~

Entity:

~~~java
@Entity
@Table(name = "enrollments")
public class Enrollment {

    @EmbeddedId
    private EnrollmentId id;

    @Column(nullable = false)
    private String status;

    protected Enrollment() {}

    public Enrollment(EnrollmentId id, String status) {
        this.id = id;
        this.status = status;
    }

    public EnrollmentId getId() {
        return id;
    }
}
~~~

Tìm:

~~~java
EnrollmentId key = new EnrollmentId(10L, 100L);
Enrollment enrollment = em.find(Enrollment.class, key);
~~~

Ở đây, identity là `(Enrollment, EnrollmentId(10,100))`. Hai object khóa ghép khác reference nhưng bằng nhau về giá trị có thể biểu diễn cùng primary key nếu `equals/hashCode` của key được triển khai đúng.

Không gọi `em.find(Enrollment.class, 10L)` vì một thành phần `studentId` không đủ xác định khóa ghép. Không đổi các thuộc tính của khóa chính sau khi entity đã managed; thay đổi ID trong persistence context là một tình huống không được thiết kế để sử dụng như cập nhật thuộc tính bình thường.

## 12. Spring Boot và Spring Data JPA: ngữ nghĩa có thay đổi không?

Trong Spring Boot, bạn thường gọi:

~~~java
Product product = productRepository.findById(42L)
    .orElseThrow(() ->
        new IllegalArgumentException("Không tìm thấy Product 42")
    );
~~~

Method `findById` của Spring Data JPA trả về `Optional<Product>`, khác về API so với `EntityManager.find()` trả `Product` hoặc `null`. Nhưng thao tác đọc entity bằng primary key vẫn dựa trên cơ chế JPA tương ứng.

### 12.1. @Transactional giữ cùng context trong một unit of work

Ví dụ service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {

    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public void renameTwice(Long id) {
        Product first = products.findById(id).orElseThrow();
        Product second = products.findById(id).orElseThrow();

        System.out.println(first == second); // true trong cùng context

        first.rename("New title");
        System.out.println(second.getName()); // New title

        // Dirty checking khi transaction được flush/commit.
    }
}
~~~

Trong cấu hình Spring Data JPA thông thường, transaction service tạo/ghép một transaction-scoped persistence context cho các thao tác repository cùng datasource/EntityManagerFactory. Vì vậy, hai lần `findById` trong cùng transaction sử dụng cùng managed instance.

Nếu một method gọi qua transaction riêng `REQUIRES_NEW`, một EntityManagerFactory khác, hoặc cấu hình context đặc biệt, không còn được giả định chúng chia sẻ cùng context.

### 12.2. @PersistenceContext có thể inject proxy

~~~java
@PersistenceContext
private EntityManager em;
~~~

Trong Spring, `em` được inject có thể là một shared EntityManager proxy. Nó chuyển lời gọi tới EntityManager thực tế gắn với transaction hiện tại. Vì vậy:

~~~java
EntityManager a = em;
EntityManager b = em;
System.out.println(a == b);
~~~

không chứng minh rằng hai lời gọi trong **hai transaction khác nhau** có cùng persistence context. Bạn chỉ đang so sánh hai biến tham chiếu tới proxy. Muốn xác định identity managed của entity, phải xét **phạm vi transaction/context thực tế**, không xét identity của proxy EntityManager.

### 12.3. Khi nào entity trở thành detached?

Một service `@Transactional` trả entity ra controller. Sau khi transaction/context đóng, entity có thể detached. Nếu controller sửa field:

~~~java
product.rename("Name from controller");
~~~

thì không nên kỳ vọng thay đổi đó tự được lưu vào database. Muốn cập nhật, nên gọi một phương thức service có transaction, tải lại entity managed bằng ID rồi áp dụng thay đổi có kiểm soát.

Ví dụ:

~~~java
@Transactional
public void changeProductName(Long id, String newName) {
    Product managed = products.findById(id).orElseThrow();
    managed.rename(newName);
}
~~~

Thiết kế này giúp ranh giới transaction, validation và dirty checking rõ ràng hơn việc sửa entity detached ở tầng presentation.

### 12.4. Open Session in View không phải giải pháp identity/concurrency

Một số cấu hình Spring Boot/Hibernate sử dụng Open Session in View để giữ session/persistence context tồn tại qua phần xử lý web request, giúp truy cập association lazy ở tầng view/controller. Điều này có thể làm thời điểm entity detached khác đi và khiến SQL phát sinh ngoài đoạn service mong đợi.

Tuy nhiên, OSIV không tự giải quyết N+1, tính nhất quán transaction hay race condition. Với ứng dụng cần kiểm soát rõ truy vấn, nên thiết kế DTO/projection/fetch plan trong service thay vì dựa vào context tồn tại tới lúc serialize JSON.

## 13. find() và quan hệ LAZY/EAGER

`find(Product.class, 42L)` tải entity theo primary key, nhưng “tải Product” không đồng nghĩa tất cả quan hệ từ Product đều được tải ngay.

Ví dụ:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private Set<OrderLine> lines = new HashSet<>();
}
~~~

Khi gọi:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
~~~

provider có thể chưa tải `order.lines`, vì nó là collection lazy. Nếu code đọc collection sau khi context đóng, Hibernate có thể ném `LazyInitializationException`.

### 13.1. Tính identity vẫn áp dụng khi tải qua association

Giả sử cùng context có:

~~~java
Product direct = em.find(Product.class, 42L);
Product viaLine = orderLine.getProduct();
~~~

Nếu `orderLine.getProduct()` trỏ tới Product ID 42, persistence context phải giữ ngữ nghĩa identity nhất quán cho entity này; provider không được quản lý hai instance độc lập cho cùng identity trong cùng context. Cách proxy/lazy reference được hiện thực là chi tiết của provider.

Không nên dùng `getClass() == Product.class` hoặc các giả định về SQL chỉ dựa trên cách lấy entity. Ưu tiên kiểm tra identity nghiệp vụ theo ID với quy tắc equality phù hợp khi làm việc xuyên context.

### 13.2. Fetch graph và entity graph

JPA hỗ trợ entity graph để xác định nhu cầu fetch:

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

Map<String, Object> hints = Map.of(
    "jakarta.persistence.fetchgraph", graph
);

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    hints
);
~~~

Ví dụ yêu cầu fetch Customer theo graph khi tìm order; SQL cụ thể phụ thuộc provider, mapping và trạng thái context. Nếu Order đã managed trong context trước đó, lần find có thể không “tải lại” các trường như người đọc mong muốn chỉ vì truyền fetch graph mới. Khi cần một fetch plan cụ thể, phải xét entity đã được quản lý hay chưa và sử dụng truy vấn/refresh phù hợp.

### 13.3. N+1 liên quan nhưng khác identity map

Nếu tải 100 đơn hàng rồi lần lượt truy cập `order.getCustomer().getName()`, provider có thể thực hiện nhiều truy vấn bổ sung tùy fetch plan và dữ liệu đã có trong context. Identity map có thể giúp tránh tải lặp lại cùng Customer, nhưng **không đảm bảo không có N+1**.

Để giảm N+1, dùng JOIN FETCH, entity graph hoặc projection phù hợp với use case và kiểm tra SQL phát sinh. Đừng mặc định rằng “find có cache” là tối ưu cho mọi khối lượng dữ liệu.

## 14. find(), query và tính nhất quán của persistence context

### 14.1. find theo PK, query theo điều kiện

~~~java
Product byId = em.find(Product.class, 42L);

List<Product> bySku = em.createQuery(
        "SELECT p FROM Product p WHERE p.sku = :sku",
        Product.class
    )
    .setParameter("sku", "JAVA-042")
    .getResultList();
~~~

`find()` dùng PK; JPQL có thể tìm theo trường khác, trả nhiều hàng, dùng JOIN/ORDER BY, projection và phân trang. Dù đường truy xuất khác, entity result trong cùng context có identity nhất quán.

### 14.2. Query có thể flush trước khi chạy

Với `FlushModeType.AUTO` và transaction phù hợp, provider có thể flush thay đổi pending trước khi thực thi truy vấn nhằm đảm bảo kết quả tuân thủ semantics của persistence context. Với `FlushModeType.COMMIT`, thời điểm flush có thể khác và tác động của thay đổi chưa flush tới query result có những giới hạn cụ thể.

Không nên dựa vào việc một query “chắc chắn chỉ đọc, không có UPDATE” nếu trong context đang có nhiều entity bị sửa. Khi cần phân tích hiệu năng và side effects của query, phải xem flush mode và transaction.

### 14.3. getResultList() không thay thế identity map

Một query trả cùng Product ID 42 nhiều lần do join có thể dẫn đến dữ liệu lặp ở danh sách kết quả tùy truy vấn và provider. Nhưng các phần tử entity biểu diễn cùng identity trong một context dùng managed instance tương ứng. Danh sách có thể lặp **reference** mà không có hai managed instances khác nhau cho cùng identity.

Khi truy vấn nhiều-nhiều gây trùng root rows, có thể dùng `SELECT DISTINCT` phù hợp. Vấn đề số phần tử của result list và tính identity của managed entity là hai khái niệm riêng.

## 15. Những lỗi thường gặp khi sử dụng find()

### 15.1. Nghĩ find() lần nào cũng lấy trạng thái mới nhất

~~~java
Product p1 = em.find(Product.class, 42L);
// Transaction khác sửa dữ liệu và commit.
Product p2 = em.find(Product.class, 42L);
~~~

Trong cùng context, `p2` có thể chính là `p1` với state cũ. Cần xét refresh/clear, cache, isolation và locking nếu dữ liệu mới nhất là yêu cầu cốt lõi.

### 15.2. Dùng == để so sánh entity qua nhiều context

~~~java
Product a = em1.find(Product.class, 42L);
Product b = em2.find(Product.class, 42L);
~~~

`a == b` không phải phép kiểm tra cùng bản ghi. Hai context độc lập có thể có hai Java objects. Khi so sánh qua boundary, dùng entity type và ID với chính sách equals/hashCode rõ ràng, xử lý trường hợp ID chưa được cấp.

### 15.3. Dùng find() để tìm theo trường unique không phải @Id

~~~java
Product p = em.find(Product.class, "JAVA-042");
~~~

Nếu `@Id` là `Long id`, lời gọi trên không đúng. `@Column(unique = true)` trên SKU không biến nó thành primary key. Dùng query theo SKU hoặc repository method tương ứng.

### 15.4. Sau find() luôn gọi save()/merge()/persist()

Nếu entity đã managed trong transaction, sửa trạng thái và để dirty checking đồng bộ. Tùy Spring Data JPA, `save()` có logic persist/merge dành cho entity mới/detached, nhưng gọi thêm một cách máy móc có thể che mờ semantics. Không cần tạo chu trình “find → edit → merge” để cập nhật một managed entity thông thường.

### 15.5. Giữ EntityManager dùng chung giữa mọi request

EntityManager không được thiết kế để chia sẻ tùy tiện giữa nhiều thread. Dùng một EntityManager toàn cục có thể làm dữ liệu stale, mất isolation và trộn các unit of work. Tạo EntityManager theo phạm vi thích hợp hoặc dùng transaction manager/container quản lý context.

### 15.6. Truy cập collection lazy ngoài context

Tìm được entity không đồng nghĩa association lazy đã được tải. Nếu cần dữ liệu qua association trong API, lên kế hoạch fetch hoặc projection trong service transaction.

### 15.7. Không kiểm tra null

`find()` có thể trả `null` khi không tìm thấy PK. Phải có chính sách phản hồi phù hợp, ví dụ 404 trong HTTP API hoặc exception nghiệp vụ.

### 15.8. Xóa entity bằng remove rồi nghĩ find sẽ “undo”

`em.remove(managed)` đánh dấu entity cần xóa. Không nên dùng `find()` như một phép thử để tự động khôi phục object hoặc chứng minh bản ghi đã được xóa vĩnh viễn. Phải xét trạng thái context, flush/commit và transaction. Nếu cần kiểm tra dữ liệu sau khi commit, mở unit of work mới và thực hiện query theo yêu cầu.

### 15.9. Gọi clear() để tiết kiệm bộ nhớ mà quên flush

Trong batch processing, `em.clear()` có thể giải phóng các entity khỏi context, nhưng nếu chưa flush, thay đổi pending có thể bị mất. Với transaction lớn, thường cân nhắc phân lô flush/clear có kiểm soát, không thực hiện clear ngẫu nhiên.

### 15.10. Cho rằng refresh() và lock tương đương

`refresh()` nhằm tải lại trạng thái; lock nhằm phối hợp concurrency theo một mode nhất định. Chúng không thay thế cho nhau. Một entity fresh hơn vẫn có thể bị thay đổi ngay sau đó nếu không có cơ chế đồng thời phù hợp.

## 16. Quy trình dùng find() trong service nghiệp vụ

Một quy trình đơn giản để cập nhật Product:

1. Mở hoặc tham gia transaction phù hợp.
2. Dùng `find(Product.class, id)` để tìm entity theo khóa chính.
3. Kiểm tra `null` và quyền truy cập.
4. Áp dụng business rule lên managed entity qua method có chủ đích.
5. Để provider flush/commit các thay đổi hoặc chủ động flush khi thật sự cần ràng buộc lỗi xuất hiện sớm.
6. Xử lý rollback/optimistic conflict, đóng EntityManager nếu do ứng dụng quản lý.
7. Trả DTO/result thay vì để tầng API sửa entity detached.

Ví dụ service Java SE:

~~~java
public final class ProductPriceService {
    private final EntityManagerFactory emf;

    public ProductPriceService(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public void updatePrice(Long id, BigDecimal newPrice) {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            Product product = em.find(Product.class, id);
            if (product == null) {
                throw new IllegalArgumentException(
                    "Không tìm thấy sản phẩm: " + id
                );
            }

            product.changePrice(newPrice);
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

Đoạn mã có ba điểm đáng chú ý:

- `find()` trả Product managed để cập nhật.
- Không gọi `persist(product)` hoặc `merge(product)` sau khi sửa.
- `@Version` trong entity giúp provider phát hiện một số xung đột cập nhật qua optimistic locking.

Trong ứng dụng Spring, transaction manager thường thay cho `getTransaction()` thủ công, nhưng bản chất managed entity và dirty checking không thay đổi.

## 17. Câu hỏi phân biệt và bài tập

### Bài tập 1 — Hai lời gọi find trong một context

~~~java
Product a = em.find(Product.class, 42L);
Product b = em.find(Product.class, 42L);
~~~

Nếu Product 42 tồn tại và đang được quản lý, `a == b` trả gì? Có bắt buộc phát sinh hai SELECT không?

**Gợi ý:** cùng managed instance, nên `a == b` true; lần thứ hai thường không cần SQL mới.

### Bài tập 2 — Hai EntityManager

~~~java
Product x = em1.find(Product.class, 42L);
Product y = em2.find(Product.class, 42L);
~~~

Nếu `em1` và `em2` là hai context độc lập, có bắt buộc `x == y` không? Nếu `x.getId().equals(y.getId())` thì có thể kết luận gì?

**Gợi ý:** hai instance Java có thể khác; chúng có thể biểu diễn cùng Product identity theo PK nếu cả hai tồn tại và thuộc cùng nguồn dữ liệu.

### Bài tập 3 — Thấy giá trị mới trong bộ nhớ

~~~java
tx.begin();

Product a = em.find(Product.class, 42L);
a.rename("Changed locally");

Product b = em.find(Product.class, 42L);

System.out.println(b.getName());

tx.rollback();
~~~

Hãy giải thích tại sao `b` có thể thấy tên mới ngay lập tức dù transaction cuối cùng rollback, và vì sao object trong bộ nhớ không phải bản sao của database sau rollback.

### Bài tập 4 — Refresh

Transaction A tải Product 42. Transaction B sửa Product 42 và commit. Transaction A gọi `find(Product.class, 42L)` lần nữa. Có chắc nhìn thấy tên mới không? Nếu muốn tải lại, dùng API nào và cần cân nhắc điều gì?

**Gợi ý:** không chắc; `refresh()` có thể tải lại managed entity, nhưng phải xét transaction isolation và nguy cơ ghi đè thay đổi local.

### Bài tập 5 — Detached và merge

~~~java
Product detached = em1.find(Product.class, 42L);
em1.close();

Product managed = em2.merge(detached);
~~~

Sau khi merge, object nào được em2 quản lý? `detached == managed` có bắt buộc true không? Vì sao code nên dùng giá trị trả về từ merge?

### Bài tập 6 — Tìm bằng composite PK

Giả sử `Enrollment` dùng `EnrollmentId(studentId, courseId)` làm `@EmbeddedId`. Viết câu gọi `find()` để tải đăng ký của Student 10 vào Course 100. Giải thích tại sao không thể chỉ truyền `10L`.

### Bài tập 7 — Lock và version

Hai transaction cùng tải Product 42 version 5, cùng sửa giá. Transaction B commit trước làm version thành 6. Vì sao transaction A có thể gặp `OptimisticLockException` khi commit? Tính đồng nhất managed instance trong context A có ngăn lỗi đó không?

**Gợi ý:** identity map chỉ quản lý instance ở context A; optimistic locking xử lý xung đột khi dữ liệu được ghi bởi transaction khác.

### Bài tập 8 — find vs getReference

Trong một transaction đang tạo OrderLine tham chiếu Product ID 42, bạn chưa cần đọc tên/giá Product. Khi nào `getReference(Product.class, 42L)` có lợi? Vì sao vẫn cần foreign key và kiểm tra nghiệp vụ nếu ID do client nhập?

## 18. Ghi nhớ

- **`EntityManager.find(EntityClass.class, primaryKey)` tìm theo primary key** và trả entity hoặc `null` nếu không tồn tại.
- **Một entity identity trong một persistence context có một instance managed**. Gọi `find()` lần nữa cho cùng entity thường trả chính object đó.
- **`find()` không bắt buộc thực hiện SELECT mỗi lần**; nó có thể sử dụng instance managed và cơ chế cache.
- Cùng bản ghi ở hai persistence context khác nhau **không bắt buộc cùng Java reference**.
- Khi entity đang managed, sửa field trong transaction thường được lưu qua **dirty checking** ở flush/commit; không cần gọi `persist()` hoặc `merge()` thêm.
- **Flush không phải commit**; thay đổi Java trong cùng object được thấy ngay trong bộ nhớ nhưng có thể rollback ở database.
- `detach()`, `clear()` và `close()` thay đổi trạng thái quản lý của entity; `merge()` trả về managed instance khác với object detached đầu vào.
- **`find()` không tự bảo đảm dữ liệu mới nhất** khi entity đã managed; cân nhắc `refresh()`, isolation, cache hints và locking theo nhu cầu.
- `getReference()` có thể giúp làm việc bằng ID khi chưa cần state đầy đủ, nhưng không chứng minh ID tồn tại và không thay thế validation/foreign key.
- `@Version` và lock mode phục vụ concurrency; identity map không thay thế cơ chế chống xung đột giữa transaction.
- Với Spring, cần xét **persistence context gắn với transaction thực tế**, không chỉ nhìn reference của EntityManager proxy.
- Với composite PK, truyền object khóa `@EmbeddedId`/`@IdClass` phù hợp, không chỉ một thành phần của khóa.

**Kết luận:** `find()` là công cụ tìm entity theo khóa chính, nhưng sức mạnh cốt lõi của nó nằm ở persistence context: JPA không chỉ trả dữ liệu từ database mà còn cung cấp một **instance managed có identity nhất quán**, cho phép chương trình theo dõi và đồng bộ thay đổi trong cùng đơn vị công việc. Hiểu rõ phạm vi context và transaction là chìa khóa để dùng `find()` chính xác, tránh truy vấn thừa, tránh dữ liệu stale và tránh nhầm lẫn giữa object Java với entity đã được lưu.
