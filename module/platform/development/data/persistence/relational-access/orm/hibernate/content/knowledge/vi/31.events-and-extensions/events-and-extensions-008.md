# Giới hạn của callback khi truy vấn hàng loạt hoặc SQL ngoài ORM

## 1. Bài toán: vì sao câu UPDATE chạy thành công nhưng callback không chạy?

Trong ứng dụng dùng Hibernate ORM, developer thường tận dụng **entity lifecycle callbacks** để tự điền thời điểm cập nhật, kiểm tra một số thuộc tính hoặc thực hiện xử lý phụ khi entity thay đổi:

~~~java
@PreUpdate
public void beforeUpdate() {
    updatedAt = Instant.now();
}
~~~

Nếu service nạp entity thành **managed object**, thay đổi field rồi flush, Hibernate có thể gọi callback này trước khi thực thi UPDATE tương ứng:

~~~java
@Transactional
public void rename(Long id, String newName) {
    Product product = entityManager.find(Product.class, id);
    product.rename(newName);
    // Khi flush một UPDATE thực sự, @PreUpdate có thể được gọi.
}
~~~

Nhưng khi chuyển sang tối ưu hiệu năng bằng một câu lệnh hàng loạt:

~~~java
@Transactional
public int archiveAllOlderThan(Instant cutoff) {
    return entityManager.createQuery(
        """
        update Product p
           set p.archived = true
         where p.createdAt < :cutoff
        """
    )
    .setParameter("cutoff", cutoff)
    .executeUpdate();
}
~~~

câu SQL có thể thay đổi hàng nghìn bản ghi mà **không gọi `@PreUpdate`/`@PostUpdate` cho từng entity**. Một câu native UPDATE, JDBC UPDATE hoặc SQL chạy từ ứng dụng khác cũng không tự kích hoạt entity callbacks của Hibernate.

Hậu quả thực tế có thể gồm:

- `updatedAt` không được thiết lập bởi callback.
- Audit log dựa trên `@PreUpdate`/`@PostUpdate` bị thiếu.
- Domain validation đang đặt trong listener không chạy.
- `@Version` có thể không tăng theo quy tắc entity-level update.
- Những managed objects đã nạp có thể tiếp tục giữ giá trị cũ.
- Cache/query results hoặc sự kiện gửi ra bên ngoài có thể lệch với database.
- Một lệnh bulk DELETE có thể bỏ qua `@PreRemove` và quy tắc cascade của entity graph.

**Kết luận nền tảng:** lifecycle callbacks thuộc **vòng đời entity do persistence provider quản lý**, không phải trigger của database. Chúng không giám sát mọi thay đổi trên các bảng bên dưới.

Bài học này thuộc chương **Sự kiện và mở rộng** của module *Data Persistence Relational Access ORM Hibernate*. Mục tiêu là xác định **chính xác ranh giới callback**, nhận biết các loại bulk operations khác nhau và chọn cách bảo đảm tính đúng đắn khi dùng HQL/JPQL bulk DML, native SQL, JDBC, stored procedure hay hệ thống khác.

### 1.1. Sau bài này bạn sẽ làm được gì?

1. Mô tả khi nào JPA lifecycle callback và entity listener được gọi.
2. Phân biệt bulk SELECT/streaming với **bulk UPDATE/DELETE/INSERT**.
3. Hiểu vì sao HQL `MutationQuery`, JPQL bulk DML và native SQL không chạy per-entity callbacks.
4. Nắm khác biệt giữa JPA lifecycle callbacks, Hibernate event listeners, interceptors và database triggers.
5. Nhận biết ảnh hưởng đến `@Version`, validation, audit, cascade, orphan removal, persistence context và cache.
6. Sử dụng Spring Data JPA `@Modifying`, `deleteAllInBatch` và derived delete một cách có chủ đích.
7. Chọn giữa entity-by-entity updates, set-based SQL, database triggers, transactional outbox, CDC hoặc audit cấp database.
8. Thiết kế integration tests chứng minh callback được gọi hoặc không được gọi trong các đường ghi dữ liệu thực tế.

## 2. Bốn cơ chế “sự kiện” khác nhau

Không phải thứ gì có chữ *event*, *callback* hoặc *listener* cũng có cùng nơi phát sinh và mức bao phủ.

| Cơ chế | Được kích hoạt bởi | Thường dùng cho | Có giám sát external SQL? |
|---|---|---|---|
| JPA entity lifecycle callbacks | Vòng đời của managed entity trong JPA provider | Điền field, kiểm tra nhẹ, xử lý quanh persist/update/remove/load | **Không** |
| Hibernate entity event listeners | Event/action tương ứng trong Hibernate Session event system | Mở rộng Hibernate entity processing, audit integration | **Không** với SQL từ ứng dụng khác |
| Hibernate SQL/statement interception | SQL mà Hibernate chuẩn bị/thực thi theo extension cụ thể | Logging, instrumentation, SQL inspection | Không với JDBC độc lập/SQL bên ngoài Hibernate |
| Database trigger | INSERT/UPDATE/DELETE thật trên bảng theo database rules | Enforce invariant, ghi audit tại DB | **Có**, nếu write đi qua bảng/trigger đó |

Một cơ chế bổ sung là **Spring application/domain events**. Chúng được publish bởi application code, không tự được gọi khi bên khác chạy SQL. Một event handler có thể nghe after-commit event, nhưng đó là transaction event integration ở tầng Spring, **không phải** entity callback hay database trigger.

### 2.1. Nhớ ba ranh giới

~~~text
         Java managed entity lifecycle
  persist / dirty check / remove / load
                   |
                   v
        JPA callbacks / Hibernate
          per-entity event listeners
                   |
                   v
        Hibernate-generated JDBC SQL
                   |
                   v
                 Database
                   ^
                   |
       JDBC / native SQL / ETL / job
                   |
                   v
      Database trigger (nếu đã cài)
~~~

Khi SQL đi thẳng đến database qua một đường không thực thi entity-level operations, nó có thể vẫn kích hoạt **database triggers** nhưng không tự chạy Java `@PreUpdate`, `@PreRemove` hoặc Hibernate entity event listeners cho từng row.

## 3. Một mô hình entity để quan sát callback

Giả sử ứng dụng quản lý sản phẩm, một Product có:
- `name` và `price`;
- `archived` đánh dấu ngừng kinh doanh;
- `createdAt`/`updatedAt`;
- `version` cho optimistic locking.

SQL schema ví dụ trên một database hỗ trợ các kiểu/cú pháp tương ứng:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    price DECIMAL(18,2) NOT NULL,
    archived BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT ck_price_nonnegative CHECK (price >= 0)
);
~~~

### 3.1. Entity dùng @EntityListeners

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "products")
@EntityListeners(ProductLifecycleListener.class)
public class Product {

    @Id
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean archived;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    private long version;

    protected Product() {}

    public Product(Long id, String name, BigDecimal price) {
        this.id = id;
        this.name = name;
        this.price = price;
        this.archived = false;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public boolean isArchived() { return archived; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public long getVersion() { return version; }

    public void rename(String nextName) {
        if (nextName == null || nextName.isBlank()) {
            throw new IllegalArgumentException("Name required");
        }
        this.name = nextName;
    }

    public void changePrice(BigDecimal nextPrice) {
        if (nextPrice == null || nextPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid price");
        }
        this.price = nextPrice;
    }

    public void archive() {
        this.archived = true;
    }

    void markCreated(Instant now) {
        createdAt = now;
        updatedAt = now;
    }

    void markUpdated(Instant now) {
        updatedAt = now;
    }
}
~~~

Đây là một ví dụ tối giản để minh họa entity lifecycle. Trong ứng dụng thật có thể cần ID generator, validation/constructor phù hợp và migration tạo schema.

### 3.2. Listener chỉ xử lý các thao tác an toàn cho lifecycle

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import java.time.Instant;

public class ProductLifecycleListener {

    @PrePersist
    public void beforePersist(Product product) {
        product.markCreated(Instant.now());
    }

    @PreUpdate
    public void beforeUpdate(Product product) {
        product.markUpdated(Instant.now());
    }

    @PreRemove
    public void beforeRemove(Product product) {
        // Chỉ minh họa hook; không gửi email/HTTP ở đây.
        // Không dùng nó làm audit bắt buộc cho mọi SQL DELETE.
    }

    @PostLoad
    public void afterLoad(Product product) {
        // Ví dụ: khởi tạo state @Transient nếu thực sự cần.
        // Tránh gọi DB/API trong listener.
    }

    @PostUpdate
    public void afterUpdate(Product product) {
        // Không đồng nghĩa transaction đã commit!
    }
}
~~~

Các callback trong ví dụ **không phải cơ chế kiểm toán tài chính đáng tin cậy**. `Instant.now()` từ JVM còn khác thời gian database server; nếu tính nhất quán thời gian chặt là yêu cầu, cần thiết kế nguồn thời gian và audit rõ ràng.

### 3.3. Callback đặt ngay trên entity

Ngoài listener class, callback có thể là method của entity:

~~~java
@Entity
public class SimpleProduct {

    @Id
    private Long id;

    private Instant updatedAt;

    @PreUpdate
    void updateTimestamp() {
        updatedAt = Instant.now();
    }
}
~~~

Phạm vi kích hoạt của nó **không rộng hơn** chỉ vì callback nằm trực tiếp trong entity. Nó vẫn là JPA entity lifecycle callback; bulk DML/native SQL không đi qua đường gọi entity callback cho từng row.

### 3.4. Các callbacks của JPA cần nhận diện

| Annotation | Khi nào liên quan đến vòng đời entity |
|---|---|
| `@PrePersist` | Trước thao tác persist của entity qua provider |
| `@PostPersist` | Sau insert action của entity theo lifecycle semantics |
| `@PreUpdate` | Trước khi provider thực hiện cập nhật row của entity được managed |
| `@PostUpdate` | Sau entity update action theo lifecycle semantics |
| `@PreRemove` | Trước thao tác remove entity của provider |
| `@PostRemove` | Sau entity removal action của provider |
| `@PostLoad` | Sau khi entity state được load từ DB hoặc được refresh theo rules của provider |

**Timing chi tiết** của post-callback so với flush và transaction commit không giống “after commit”. Những callback sau DML có thể được gọi **trước khi transaction commit**; nếu transaction rollback, chúng không thể được diễn giải như sự kiện commit thành công.

### 3.5. Giới hạn xử lý ngay bên trong callback

Theo tinh thần portable JPA lifecycle callbacks, nên:
- Giữ callback đơn giản và cục bộ, ví dụ cập nhật trường scalar hoặc kiểm tra nhẹ.
- Tránh gọi `EntityManager`, chạy query, thay relationship graph, thao tác entities khác hoặc giao tiếp hệ thống ngoài ngay trong callback.
- Không dựa vào transaction callback để gửi email HTTP/gọi payment API khi transaction vẫn có thể rollback.
- Không sử dụng listener như một “Spring service” tùy tiện nếu injection/khởi tạo listener do provider và framework khác nhau quản lý.
- Tránh recursion khi listener gián tiếp làm phát sinh thêm entity operations.

Các ràng buộc chính xác phụ thuộc Jakarta Persistence specification, listener type và provider; muốn làm cross-entity business workflows nên dùng **application service trong transaction**, không nhét vào lifecycle hook.

## 4. Entity-by-entity UPDATE: đường mà @PreUpdate thường có hiệu lực

### 4.1. Luồng xử lý

~~~java
@Transactional
public void rename(Long productId, String nextName) {
    Product product = entityManager.find(
        Product.class, productId
    );

    if (product == null) {
        throw new IllegalArgumentException("Product missing");
    }

    product.rename(nextName);
    // Hibernate kiểm tra dirty state và flush khi phù hợp.
}
~~~

Ở flush:
1. Hibernate nhận thấy managed Product có sự thay đổi cần UPDATE.
2. Lifecycle update callback được gọi theo semantics provider.
3. Listener đặt `updatedAt`.
4. Hibernate tạo UPDATE cho entity (có thể bao gồm version predicate).
5. SQL được gửi qua JDBC.
6. Transaction tiếp tục và commit/rollback ở boundary.

Sơ đồ khái niệm:

~~~text
EntityManager.find(Product, 42)
               |
               v
  Managed Product#42 (L1)
               |
       product.rename(...)
               |
               v
       Flush / dirty checking
               |
               v
        @PreUpdate(Product)
               |
               v
    UPDATE products ... WHERE id=42
               |
               v
        @PostUpdate(Product)
               |
               v
      COMMIT hoặc ROLLBACK sau đó
~~~

### 4.2. Không phải mọi setter đều dẫn tới @PreUpdate

~~~java
@Transactional
public void noActualChange(Long id) {
    Product product = entityManager.find(Product.class, id);
    product.rename(product.getName());
}
~~~

Nếu Hibernate xác định không có persistent change cần UPDATE, có thể không có SQL UPDATE và không có `@PreUpdate`.

Tương tự, `@PreUpdate` không phải timer/periodic callback; nó không tự chạy khi một entity chỉ được đọc.

Tùy provider và mapping, hành vi với embeddable, collections, dirty checking và update timing có thể khác. Khi correctness phụ thuộc việc timestamp được thay đổi ngay cả khi *không có UPDATE*, hãy thiết kế explicit business operation thay vì giả định @PreUpdate luôn được gọi.

### 4.3. flush() không đồng nghĩa commit

~~~java
@Transactional
public void updateThenFail(Long id) {
    Product product = entityManager.find(Product.class, id);
    product.rename("Changed");

    entityManager.flush();

    throw new IllegalStateException("rollback demonstration");
}
~~~

Callback và SQL UPDATE có thể đã chạy khi gọi `flush()`. Nhưng Spring transaction sau đó rollback: không có commit thành công.

Nếu `@PostUpdate` đã gửi email hoặc publish message tới hệ ngoài, email/message **không tự rollback** theo DB transaction. Đây là lý do audit/event bắt buộc nên sử dụng transactionally coordinated design (như outbox), không gắn sự kiện không thể rollback vào post-entity callback.

## 5. Entity-by-entity DELETE: @PreRemove và cascades

### 5.1. Remove một managed entity

~~~java
@Transactional
public void deleteOne(Long id) {
    Product product = entityManager.find(Product.class, id);

    if (product != null) {
        entityManager.remove(product);
    }
}
~~~

Trong entity removal lifecycle, `@PreRemove`/`@PostRemove` có cơ hội được thực thi theo JPA provider rules. Nếu mapping có cascade REMOVE/`orphanRemoval`, Hibernate có thể thực hiện thêm entity-level operations với semantics liên quan.

### 5.2. Khi remove nhiều entity bằng vòng lặp

~~~java
@Transactional
public int deleteSelected(List<Long> ids) {
    int removed = 0;

    for (Long id : ids) {
        Product product = entityManager.find(Product.class, id);
        if (product != null) {
            entityManager.remove(product);
            removed++;
        }
    }

    return removed;
}
~~~

Đây vẫn là nhiều **entity removal operations**, không phải một bulk DELETE. Nó có thể kích hoạt per-entity callbacks và cascade mappings, đổi lại:
- Nhiều lần load entity.
- Persistence context giữ nhiều objects.
- Số SQL actions có thể lớn.
- Phải flush/clear theo batch nếu tập rất lớn và domain semantics cho phép.
- Transaction và memory cần được thiết kế phù hợp.

Không đồng nhất “xử lý nhiều entities trong một vòng lặp” với “bulk SQL mutation” khi bàn về callback.

## 6. Bulk SELECT có bỏ qua callback không?

Cụm “truy vấn hàng loạt” dễ gây nhầm lẫn. Cần phân biệt **nạp nhiều entity để đọc** và **DML thay đổi nhiều rows trực tiếp tại database**.

### 6.1. SELECT trả managed entities

~~~java
List<Product> products = entityManager.createQuery(
    "select p from Product p where p.archived = false",
    Product.class
).getResultList();
~~~

Nếu Hibernate thực sự load entity state từ DB vào context, các `@PostLoad` callbacks có thể được gọi cho entities được load theo semantics JPA.

Nhưng:
- Nếu entity **đã managed trong L1**, Hibernate có thể trả lại instance cũ, không load lại và không gọi `@PostLoad` lần nữa.
- Nếu result trả DTO/scalar, không có Product entity lifecycle load cho từng row DTO.
- `@PreUpdate` không chạy chỉ vì SELECT được thực hiện.
- Query cache/L2 cache và fetch plan có thể ảnh hưởng các trường hợp load thực tế; đừng dùng `@PostLoad` làm bộ đếm số SQL rows.
- Bulk read lớn có thể dùng streaming/scroll và cần quản lý persistence context, resource lifecycle.

### 6.2. DTO projection không tạo Product entity để callback

~~~java
public record ProductCard(
    Long id,
    String name,
    BigDecimal price
) {}
~~~

~~~java
List<ProductCard> cards = entityManager.createQuery(
    """
    select new com.example.catalog.ProductCard(
        p.id, p.name, p.price
    )
    from Product p
    where p.archived = false
    """,
    ProductCard.class
).getResultList();
~~~

Kết quả là DTO, không phải managed Product. Không mong đợi `@PostLoad(Product)` được gọi cho mỗi ProductCard nếu truy vấn chỉ project các scalar fields.

### 6.3. Stream, scroll và pagination khi đọc entity

~~~java
try (Stream<Product> stream = entityManager.createQuery(
        "select p from Product p order by p.id",
        Product.class
    ).getResultStream()) {

    stream.forEach(product -> {
        // Có thể làm việc với managed entity khi nó được load.
        // Không phải một bulk DML mutation.
    });
}
~~~

Stream cần được sử dụng trong transaction/Session phù hợp và đóng tài nguyên khi query provider yêu cầu. Có thể phát sinh `@PostLoad` cho entities thực sự được load; điều đó không đảm bảo một callback cho mỗi SQL row hay mỗi lần stream đi qua object.

**Kết luận:** bulk SELECT là chuyện đọc; “callback không chạy trong bulk operations” thường nhắm vào **bulk DML** và SQL ngoài entity lifecycle, chứ không phải khẳng định mọi SELECT nhiều hàng đều bỏ qua `@PostLoad`.
+## 7. JPQL bulk UPDATE: thao tác theo tập hợp, không theo từng entity

### 7.1. Hai đoạn code giống mục tiêu nhưng khác semantics

**Đường entity lifecycle:**

~~~java
@Transactional
public int archiveUsingEntities(Instant cutoff) {
    List<Product> products = entityManager.createQuery(
        """
        select p from Product p
        where p.createdAt < :cutoff
          and p.archived = false
        """,
        Product.class
    )
    .setParameter("cutoff", cutoff)
    .getResultList();

    for (Product product : products) {
        product.archive();
    }

    // Có thể gọi @PreUpdate khi flush từng entity có UPDATE.
    return products.size();
}
~~~

**Đường bulk JPQL:**

~~~java
@Transactional
public int archiveUsingBulkJpql(Instant cutoff) {
    return entityManager.createQuery(
        """
        update Product p
           set p.archived = true
         where p.createdAt < :cutoff
           and p.archived = false
        """
    )
    .setParameter("cutoff", cutoff)
    .executeUpdate();
}
~~~

Cả hai có thể dẫn đến cùng giá trị `archived=true` cho những rows phù hợp, nhưng **không tương đương** về vòng đời:

| Khía cạnh | Load entities + mutate | JPQL bulk UPDATE |
|---|---|---|
| Có managed Product object cho mỗi row | Có | Không bắt buộc, thường không |
| `@PreUpdate`/`@PostUpdate` cho từng Product | Có thể chạy nếu entity được update thực sự | **Không** |
| Entity-level dirty checking | Có | Bypass |
| Cascades và domain methods | Theo thao tác entity/mapping | Không tự chạy per entity |
| `@Version` optimistic check trên mỗi managed entity | Có theo mapping | Không tự tương đương |
| Cập nhật `updatedAt` từ listener | Có thể | Không tự có |
| Cập nhật L1 objects đang managed | Có, trên objects được sửa | Không tự đồng bộ |
| Số SQL UPDATE | Có thể nhiều, đôi khi JDBC batch | Set-based mutation do Hibernate dịch |
| Dữ liệu lớn | Tốn memory/entity loads | Thường giảm entity materialization |

**Vì sao?** Bulk JPQL diễn đạt trực tiếp một phép biến đổi tập rows theo predicate, không ra lệnh “đi lấy từng Product rồi gọi một method trên nó”.

### 7.2. Callback không chạy dù câu JPQL được viết bằng tên entity

~~~sql
update Product p set p.archived = true
where p.createdAt < :cutoff
~~~

Có tên `Product` và path `p.archived` nghĩa là provider hiểu entity metadata để dịch query. Điều đó **không** biến câu UPDATE thành chuỗi lệnh `entityManager.find(Product, id)` và `product.archive()`.

Không nên hiểu “SQL gốc không có listener, JPQL thì luôn có listener”. **Bulk JPQL/HQL DML cũng bypass per-entity callbacks**.

### 7.3. Tự cập nhật các cột mà callback thường cập nhật

Nếu nghiệp vụ yêu cầu `updatedAt` có giá trị đúng ngay sau bulk UPDATE, phải đưa quy tắc đó vào chính DML:

~~~java
@Transactional
public int archiveUsingBulkJpql(Instant cutoff, Instant now) {
    return entityManager.createQuery(
        """
        update Product p
           set p.archived = true,
               p.updatedAt = :now
         where p.createdAt < :cutoff
           and p.archived = false
        """
    )
    .setParameter("now", now)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
}
~~~

Trong một hệ thống nhiều nodes, thời gian `now` lấy từ JVM có thể lệch DB clock. Nếu tính nhất quán timestamp cần thiết, cân nhắc provider/database function có kiểm soát hoặc DB default/trigger. Đừng mặc định mọi JPQL function có SQL translation giống nhau.

### 7.4. @Version trong bulk UPDATE không tự tăng như entity-level update

Giả sử Product có `@Version private long version`. Khi Hibernate dirty-check entity và ghi UPDATE, optimistic locking thường kiểm tra version hiện hành và tăng nó.

Ngược lại, bulk JPQL UPDATE **không tự tăng version/timestamp field theo mặc định**. Nếu application dùng bulk update nhưng không cập nhật version, một managed Product ở transaction khác có thể tiếp tục mang version cũ và optimistic check không phát hiện được tất cả external changes.

Có thể thiết kế bulk DML tường minh:

~~~java
int affected = entityManager.createQuery(
    """
    update Product p
       set p.archived = true,
           p.updatedAt = :now,
           p.version = p.version + 1
     where p.archived = false
    """
)
.setParameter("now", Instant.now())
.executeUpdate();
~~~

Đây là ví dụ cho **numeric version**. Không áp dụng máy móc cho timestamp version/UUID/custom version type. Hibernate HQL còn có extension `update versioned` cho một số trường hợp, nhưng không phải JPQL portable và có giới hạn version types; kiểm tra guide đúng phiên bản trước khi dùng.

**Quan trọng:** tự tăng version của mọi row trong bulk DML không đồng nghĩa đã kiểm tra một version mong đợi của từng entity. Khi cần optimistic conflict check từ dữ liệu client đã đọc, thêm version predicate theo contract nghiệp vụ và xử lý affected-row count; với bulk nhiều IDs/versions cần chiến lược riêng.

### 7.5. Update count không phải callback count

`executeUpdate()` trả một con số đại diện số entity/rows bị tác động theo provider semantics. Với inheritance mappings, một bulk mutation logic có thể dẫn đến nhiều SQL statements trên các bảng. Không suy luận số này luôn bằng số SQL statements hoặc số callbacks.

Dù `executeUpdate()` trả 15.000, **không có nghĩa `@PreUpdate` đã được gọi 15.000 lần**.

## 8. JPQL/HQL bulk DELETE: không có @PreRemove cho từng row

### 8.1. Xóa bằng entity manager

~~~java
@Transactional
public void deleteManaged(Long id) {
    Product product = entityManager.find(Product.class, id);
    if (product != null) {
        entityManager.remove(product);
    }
}
~~~

Entity removal lifecycle chạy qua provider. `@PreRemove` có cơ hội được gọi, cùng các quan hệ/cascade theo mapping.

### 8.2. Xóa bằng bulk query

~~~java
@Transactional
public int deleteArchivedBefore(Instant cutoff) {
    return entityManager.createQuery(
        """
        delete from Product p
        where p.archived = true
          and p.updatedAt < :cutoff
        """
    )
    .setParameter("cutoff", cutoff)
    .executeUpdate();
}
~~~

Ở đây Hibernate gửi set-based DELETE theo mapping/dialect, **không load từng Product** và không gọi `@PreRemove`/`@PostRemove` của từng Product.

Hệ quả:

- Cleanup logic chỉ được đặt trong `@PreRemove` sẽ bị bỏ qua.
- `CascadeType.REMOVE` và `orphanRemoval` qua entity graph không tự được thực hiện như `remove(entity)`.
- Database foreign key constraints vẫn có hiệu lực; DELETE có thể thất bại nếu còn child rows.
- DB-level `ON DELETE CASCADE` nếu được cấu hình **có thể** xóa child rows, nhưng sẽ không gọi JPA `@PreRemove` cho từng child.
- Bulk DELETE có thể làm managed Product/associations đã load trong L1 stale.

### 8.3. Domain cleanup và DB cascade là hai cơ chế khác nhau

~~~text
EM.remove(parent)
  -> Hibernate entity lifecycle
  -> @PreRemove(parent)
  -> cascade REMOVE qua mapping (nếu có)
  -> callbacks trên các managed child được remove
  -> SQL DELETE(s)

Bulk DELETE parent
  -> SQL DELETE theo query
  -> DB FK / ON DELETE CASCADE nếu cấu hình
  -> KHÔNG có per-entity Java callbacks cho rows đã bị xóa
~~~

Nếu cleanup liên quan tới files trên object storage, search index, payment holds hoặc event notification, **không** dựa vào `@PreRemove` như cơ chế duy nhất khi có bulk SQL path.

### 8.4. Soft delete phải được thiết kế cho mọi đường xóa

Một entity có thể có soft-delete behavior qua custom SQL, Hibernate annotations hoặc domain method thay vì physical DELETE. Tuy nhiên, một native:

~~~sql
DELETE FROM products WHERE id = ?;
~~~

vẫn có thể physical delete row nếu DB cho phép. Một HQL bulk DELETE cũng có semantics/version-dependent handling riêng, không được mặc định đi qua custom per-entity soft-delete callback.

Nếu “không bao giờ xóa vật lý” là invariant quan trọng, cần:
- Giới hạn database permissions.
- Tập trung write API.
- Có trigger/constraint hoặc chính sách DB phù hợp.
- Review mọi bulk/native SQL routes.
- Test riêng đường deletion của Hibernate version đang dùng.

Không chỉ dựa vào một entity listener để bảo vệ một invariant mà external SQL có thể phá.

## 9. HQL MutationQuery và Hibernate-specific bulk mutation

### 9.1. Cú pháp qua Hibernate Session

Hibernate ORM 6.x có `MutationQuery` cho HQL mutation:

~~~java
import jakarta.persistence.EntityManager;
import org.hibernate.Session;
import org.hibernate.query.MutationQuery;

@Transactional
public int archiveViaHibernate(Instant cutoff) {
    Session session = entityManager.unwrap(Session.class);

    MutationQuery query = session.createMutationQuery(
        """
        update Product p
           set p.archived = true,
               p.updatedAt = :now
         where p.createdAt < :cutoff
        """
    );

    return query
        .setParameter("now", Instant.now())
        .setParameter("cutoff", cutoff)
        .executeUpdate();
}
~~~

`MutationQuery` làm rõ đây là DML; **nó không biến bulk HQL thành entity-by-entity mutation**. Không có `@PreUpdate`/`@PostUpdate` cho từng Product bị ảnh hưởng.

### 9.2. HQL bulk INSERT cũng bypass @PrePersist của từng row

Tùy Hibernate version và query shape, HQL có thể hỗ trợ `insert ... select ...` hoặc các form mutation nâng cao.

Ví dụ minh họa ý tưởng:

~~~sql
insert into ArchivedProduct (id, name, archivedAt)
select p.id, p.name, :now
from Product p
where p.archived = true
~~~

Đây là HQL bulk INSERT theo mapping (giả định có entity ArchivedProduct với field và identifier phù hợp). Những rows được chèn qua set-based INSERT **không tương đương** việc tạo từng ArchivedProduct rồi `entityManager.persist(entity)`; không gọi `@PrePersist` cho từng row.

Nếu ArchivedProduct có các trường bắt buộc thường được gán trong callback, câu INSERT cần cung cấp các giá trị cần thiết hoặc DB defaults/triggers phải bảo đảm chúng.

### 9.3. Multi-table entity inheritance và mutation

Hibernate có thể phải dùng chiến lược thực thi đặc thù cho bulk mutation ở những entity mapping nhiều bảng/inheritance. Một HQL mutation có thể sinh hơn một SQL statement hoặc dùng temporary tables/CTE tùy dialect/provider.

Điều đó **không** làm per-entity callbacks tự xuất hiện. Nó chỉ cho thấy provider phải dịch một mutation logic ra SQL phù hợp schema.

Khi kiểm tra kết quả, tập trung vào:
- Rows/entity instances bị tác động về mặt nghiệp vụ.
- Constraints và versions.
- Stale persistence context/cache.
- Callback có chạy không.
- SQL generation theo Hibernate version/dialect.

### 9.4. Dấu hiệu nhận diện nhanh

Nếu code viết:

~~~java
session.createMutationQuery("delete from Product ...").executeUpdate();
~~~

thì hãy tự hỏi: **có bất kỳ managed Product nào được load và gọi `remove()` riêng lẻ không?** Thông thường câu trả lời là không. Vì thế đừng mong `@PreRemove` chạy cho những rows do query xóa.

## 10. SQL gốc, JDBC và SQL chạy ngoài ứng dụng

### 10.1. Native UPDATE qua EntityManager

~~~java
@Transactional
public int nativeArchive(Instant cutoff, Instant now) {
    return entityManager.createNativeQuery(
        """
        UPDATE products
           SET archived = true,
               updated_at = :now,
               version = version + 1
         WHERE created_at < :cutoff
           AND archived = false
        """
    )
    .setParameter("now", now)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
}
~~~

Đây là **native SQL** (tên bảng/cột thật), không phải HQL/JPQL. Nó chạy qua Hibernate EntityManager nhưng không tạo vòng đời update cho từng Product object, nên không gọi `@PreUpdate` cho từng row.

Điểm tốt của ví dụ là việc cập nhật `updated_at` và `version` được **diễn đạt tường minh trong SQL**, không phụ thuộc vào callback sẽ không chạy.

### 10.2. JDBC thuần/JdbcTemplate

~~~java
int count = jdbcTemplate.update(
    """
    UPDATE products
       SET price = ?,
           updated_at = ?,
           version = version + 1
     WHERE id = ?
    """,
    nextPrice,
    Timestamp.from(now),
    id
);
~~~

Spring `JdbcTemplate` chỉ chạy JDBC SQL; nó không load Product managed và không gọi Hibernate entity lifecycle callbacks. Nếu JDBC/JPA cùng DataSource/transaction manager phù hợp, SQL có thể tham gia cùng transaction, nhưng sự tham gia transaction **không đổi** phạm vi callbacks.

JDBC `PreparedStatement.addBatch()/executeBatch()` cũng không đồng nghĩa “ORM per-entity callbacks chạy theo batch”. Nó chỉ batch những SQL executions tại JDBC layer.

### 10.3. Session.doWork không kích hoạt entity callbacks

~~~java
Session session = entityManager.unwrap(Session.class);

session.doWork(connection -> {
    try (PreparedStatement ps = connection.prepareStatement(
        """
        UPDATE products
           SET archived = true,
               updated_at = CURRENT_TIMESTAMP,
               version = version + 1
         WHERE id = ?
        """
    )) {
        ps.setLong(1, id);
        ps.executeUpdate();
    }
});
~~~

Mặc dù `doWork` nhận connection của Hibernate Session, câu JDBC UPDATE vẫn không thông qua `Product.archive()`, dirty checking hay `@PreUpdate`. Ngoài ra, Hibernate không tự phân tích từng PreparedStatement do ứng dụng tự thực thi để cập nhật tất cả managed Product trong L1.

Không `connection.close()`, `commit()` hoặc `rollback()` trong callback khi connection thuộc transaction manager/Hibernate. Chỉ đóng statement/result set do code mở.

### 10.4. SQL chạy bởi một ứng dụng khác

~~~sql
UPDATE products
SET archived = true,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE created_at < TIMESTAMP '2025-01-01 00:00:00';
~~~

Nếu câu SQL do ETL, administrator, migration tool hoặc service B gửi tới database, JVM chạy Hibernate ở service A có thể **không biết một thao tác nào đã xảy ra**.

Hệ quả:
- Không JPA callbacks.
- Không Hibernate entity event listeners.
- Không Spring application events trừ khi có tích hợp explicit.
- Có thể có database triggers.
- L1/L2/query cache ở service A có thể stale.
- Bất kỳ business rule chỉ tồn tại trong Java listener đều có thể bị bypass.

### 10.5. Stored procedure và trigger side effects

~~~java
StoredProcedureQuery procedure =
    entityManager.createStoredProcedureQuery("archive_old_products");

procedure.registerStoredProcedureParameter(
    1, Instant.class, ParameterMode.IN
);
procedure.setParameter(1, cutoff);
procedure.execute();
~~~

Stored procedure có thể thay đổi nhiều bảng; không thể giả định Hibernate hiểu mọi row/relationship bị ảnh hưởng. Dù procedure được gọi bằng EntityManager, nó không tương đương `remove(entity)`/`persist(entity)` trên những rows procedure chạm tới.

Ngược lại, **database triggers** trên các bảng bị UPDATE/DELETE có thể chạy theo quy tắc của DB vì chúng thuộc database layer. Trigger không phải JPA `@PreUpdate`. Nếu dùng trigger làm audit nguồn sự thật, phải thiết kế schema/transaction/security, không trộn chúng thành “Hibernate listeners”.

## 11. Spring Data JPA: @Modifying, deleteAllInBatch và derived delete

### 11.1. @Modifying + JPQL bulk UPDATE

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query(
        """
        update Product p
           set p.archived = true,
               p.updatedAt = :now
         where p.createdAt < :cutoff
        """
    )
    int archiveOld(
        @Param("cutoff") Instant cutoff,
        @Param("now") Instant now
    );
}
~~~

`@Modifying` nói với Spring Data JPA rằng `@Query` là modifying query; nó **không yêu cầu Hibernate load từng Product** để chạy callbacks.

- `flushAutomatically=true`: Spring Data yêu cầu flush EntityManager trước khi chạy query.
- `clearAutomatically=true`: Spring Data clear EntityManager sau khi query.
- Hai flags này giúp quản lý L1/pending state, **không làm `@PreUpdate` được gọi**.
- `clearAutomatically` detach toàn bộ managed entities trong context; cần cẩn trọng nếu caller còn dùng graph hoặc có unflushed changes.
- Method cần transaction ghi (ví dụ `@Transactional` ở service).

### 11.2. deleteAllInBatch và deleteAllByIdInBatch

Spring Data JPA có các APIs xóa hàng loạt như:

~~~java
@Transactional
public void purge() {
    productRepository.deleteAllInBatch();
}
~~~

Các phương thức batch delete kiểu này dùng bulk deletion ở DB thay vì lần lượt gọi entity remove lifecycle. Spring Data JPA documentation cảnh báo thao tác batch delete có thể:
- Không tuân theo JPA cascade semantics như entity-by-entity remove.
- Không phát sinh lifecycle callbacks tương ứng.
- Để first-level cache và database ở trạng thái không đồng bộ.

Đừng chọn `deleteAllInBatch()` nếu `@PreRemove` là nơi duy nhất triển khai business cleanup mà quy trình bắt buộc phải chạy cho mọi Product.

### 11.3. Derived delete có thể khác @Modifying bulk delete

Spring Data JPA phân biệt derived delete queries và bulk modifying queries. Ví dụ về ý định:

~~~java
long deleteByArchivedTrue();
~~~

Với một số derived delete methods, Spring Data JPA có thể **truy vấn tìm entities rồi xóa từng entity** để lifecycle callbacks như `@PreRemove` có cơ hội chạy. Điều này khác với:

~~~java
@Modifying
@Query("delete from Product p where p.archived = true")
int deleteArchivedInBulk();
~~~

Phương thức thứ hai biểu diễn **một bulk JPQL DELETE**, bỏ qua per-entity callbacks.

Tuy nhiên, không chỉ dựa vào tên method `deleteBy...` hay `deleteAll...` mà đoán implementation; kiểm tra Spring Data JPA version, repository implementation, mapping và SQL thực tế. Derived delete nạp nhiều entities có thể tiêu thụ bộ nhớ đáng kể; khi số lượng rất lớn, cần quyết định giữa callback semantics và hiệu năng.

### 11.4. Spring Data auditing annotations

Spring Data JPA có auditing annotations như `@CreatedDate`, `@LastModifiedDate` cùng auditing infrastructure; các giá trị này thường được cập nhật thông qua listener/callback trên entity lifecycle.

Nếu chạy một JPQL bulk UPDATE hoặc native SQL không tạo per-entity lifecycle callbacks, **không nên mặc định Spring Data auditing tự cập nhật `@LastModifiedDate` cho mọi row**.

Phải đưa timestamp vào DML, dùng DB trigger/generated policy hoặc chọn entity operations theo yêu cầu.

### 11.5. Không nhầm việc phát SQL bulk với flush của managed changes

~~~java
@Transactional
public void mixedOperation(Long id) {
    Product product = entityManager.find(Product.class, id);
    product.changePrice(new BigDecimal("99.00"));

    productRepository.archiveOld(cutoff, Instant.now());
}
~~~

Tùy `flushAutomatically`, flush mode và query spaces, UPDATE của `product.changePrice` có thể flush **trước** bulk query. Lúc đó `@PreUpdate` có thể chạy cho **Product được sửa qua entity lifecycle**. Nhưng điều này **không có nghĩa bulk query chạy callback cho mọi row mà nó tác động**.

Đây là một nguồn nhầm lẫn khi developer thấy một vài listener logs trong một transaction chứa cả managed updates lẫn bulk DML: cần quy về operation nào thực sự kích hoạt callback.
+## 12. Persistence context có thể stale sau bulk DML

### 12.1. Managed entity đang giữ giá trị cũ

~~~java
@Transactional
public void demonstrateStaleState(Long id) {
    Product product = entityManager.find(Product.class, id);
    boolean before = product.isArchived();

    entityManager.createQuery(
        """
        update Product p
           set p.archived = true
         where p.id = :id
        """
    )
    .setParameter("id", id)
    .executeUpdate();

    boolean after = product.isArchived();

    // after có thể vẫn bằng before:
    // bulk SQL không ghi lại field của managed Product.
}
~~~

Ngay cả khi code gọi:

~~~java
Product another = entityManager.find(Product.class, id);
~~~

Hibernate có thể trả chính managed instance `product` trong identity map. Một lần `find` khác trong cùng context **không bảo đảm reload** từ DB.

### 12.2. Flush trước bulk DML nếu pending changes cần giữ

Nếu context có managed changes chưa được SQL ghi ra, còn bulk DML phụ thuộc những changes đó, cần kiểm soát thứ tự:

~~~java
@Transactional
public void updateThenArchive(Long id, Instant cutoff) {
    Product product = entityManager.find(Product.class, id);
    product.rename("Renamed");

    entityManager.flush();  // Managed changes -> DB trong transaction.

    entityManager.createQuery(
        """
        update Product p
        set p.archived = true, p.updatedAt = :now
        where p.createdAt < :cutoff
        """
    )
    .setParameter("now", Instant.now())
    .setParameter("cutoff", cutoff)
    .executeUpdate();

    // Nếu còn cần product fresh, refresh/clear tùy nhu cầu.
}
~~~

JPA/Hibernate có auto-flush rules theo flush mode và query spaces, nhưng explicit flush giúp diễn đạt thứ tự khi correctness phụ thuộc SQL state.

`flush()` có thể khiến `@PreUpdate` chạy cho Product được sửa qua dirty checking trong bước đầu; **nó không gọi callback cho những rows khác mà bulk statement tác động**.

### 12.3. refresh một entity còn tồn tại

~~~java
entityManager.refresh(product);

boolean refreshedArchived = product.isArchived();
~~~

`refresh` đọc lại DB state cho một managed entity hiện còn tồn tại theo transaction visibility. Những local changes chưa flush trên entity có thể bị overwrite. Nếu row đã bị bulk DELETE thì refresh có thể lỗi vì row không còn.

### 12.4. clear cả persistence context

~~~java
entityManager.flush(); // Chỉ nếu có pending changes phải giữ.

int affected = entityManager.createQuery(
    "update Product p set p.archived = true"
).executeUpdate();

entityManager.clear();

Product reloaded =
    entityManager.find(Product.class, productId);
~~~

`clear()` detach tất cả managed entities trong context; những Java references cũ không tự nhận field values mới.

Đặc biệt:
- Nếu `clear` trước flush, pending entity changes có thể bị mất.
- Clear không commit/rollback transaction.
- Clear không tự xóa mọi second-level cache/query cache.
- Nếu caller đang dùng nhiều repositories trong cùng transaction, clear của một repository có thể ảnh hưởng các entities do repository khác quản lý.

### 12.5. Cache dùng chung sau SQL ngoài Hibernate

Một Hibernate native mutation có thể phối hợp invalidation theo query spaces/provider version, nhưng **external JDBC** hoặc một admin SQL script không tự thông báo thay đổi tới second-level cache/query cache của Hibernate process khác.

Ví dụ:
- Service A cache Product#42 với `archived=false`.
- ETL dùng JDBC set `archived=true`, commit.
- Service A mở Session mới, nhưng L2/query cache có thể vẫn chứa thông tin cũ.

Các biện pháp có thể gồm:
- Cache eviction/invalidation theo entity/collection/query region.
- Event-driven/CDC invalidation.
- Không cache entity có nhiều external writers.
- Giới hạn stale window bằng TTL khi nghiệp vụ cho phép.
- Đọc DB authoritative cho quyết định cần nhất quán mạnh.

**Callback là cơ chế trước/sau entity action; cache invalidation là cơ chế nhất quán đọc**. Không gộp hai vấn đề này thành một.

### 12.6. NativeQuery query spaces không biến SQL thành entity update

Hibernate có API để khai báo các query spaces liên quan native SQL:

~~~java
Session session = entityManager.unwrap(Session.class);

NativeQuery<?> query = session.createNativeQuery(
    """
    UPDATE products
       SET archived = true, updated_at = CURRENT_TIMESTAMP
     WHERE id = :id
    """
);

query.addSynchronizedEntityClass(Product.class);
query.setParameter("id", productId);

query.executeUpdate();
~~~

`addSynchronizedEntityClass(Product.class)` giúp Hibernate biết những entity/table spaces liên quan, phục vụ auto-flush/cache coordination theo version. Nhưng **nó không khiến `@PreUpdate` chạy cho Product#ID**, không tự load entity và không refresh instance đang managed.

## 13. Validation đặt ở callback cũng có thể bị bỏ qua

### 13.1. Bean Validation tích hợp với ORM lifecycle

Một entity có thể khai báo:

~~~java
@Entity
public class Subscription {

    @Id
    private Long id;

    @NotNull
    @Min(0)
    private Integer remainingCredits;

    @PreUpdate
    void checkBusinessCondition() {
        if (remainingCredits != null &&
            remainingCredits > 1_000_000) {
            throw new IllegalStateException("Credits out of range");
        }
    }
}
~~~

Khi entity được lưu qua JPA lifecycle, Bean Validation integration (nếu được cấu hình) và callbacks có thể kiểm tra entity theo event groups/rules tương ứng.

Nhưng một SQL:

~~~sql
UPDATE subscriptions
SET remaining_credits = -100
WHERE id = 42;
~~~

không tạo entity validation event ở Java. Nếu database không có CHECK constraint, dữ liệu không hợp lệ có thể được ghi.

### 13.2. Validation ở tầng Java không phải database constraint

| Quy tắc | Có ngăn external JDBC SQL không? |
|---|---|
| Constructor/domain method Java | Không |
| `@PreUpdate` throw exception | Không |
| Bean Validation `@Min(0)` khi entity được ORM xử lý | Không tự ngăn JDBC độc lập |
| SQL CHECK `remaining_credits >= 0` | Có, nếu DB constraint được cài và enforced |
| SQL NOT NULL/UNIQUE/FK | Có, nếu DB constraint tồn tại và đang hiệu lực |
| DB trigger kiểm tra quy tắc | Có trong phạm vi trigger DB được bật và các quyền liên quan |
| Service/API authorization | Chỉ ngăn các đường đi qua service đó |

### 13.3. Database constraints là tuyến phòng thủ cuối

~~~sql
ALTER TABLE subscriptions
ADD CONSTRAINT ck_nonnegative_credits
CHECK (remaining_credits >= 0);
~~~

Đây là DDL minh họa trên DB hỗ trợ CHECK; trong hệ có migration tool, đặt thay đổi vào migration được review thay vì chạy thủ công.

Nếu nhiều applications có quyền ghi, những invariant có thể biểu diễn bằng DB constraints nên được thực thi ở database. Business rules phức tạp vẫn có thể cần service/domain logic, nhưng đừng đặt toàn bộ integrity chỉ trong lifecycle callbacks rồi cho rằng bulk SQL không thể phá.

### 13.4. @PreUpdate không phải một validation hook cho mọi row thay đổi

Nếu dùng `@PreUpdate` để kiểm tra thứ tự nghiệp vụ, bulk UPDATE có thể bỏ qua nó. Hãy chọn:
- Entity operations nếu cần domain validation thực hiện cho từng entity.
- Predicate/CASE/CHECK/trigger phù hợp nếu cần set-based mutation.
- Một command service kiểm soát mọi writers nếu tính thống nhất giữa các hệ thống được bảo đảm.
- Database-level restriction/permission để cấm những đường ghi phá invariant.

## 14. Hibernate event listeners và interceptors có cứu được bulk callbacks không?

JPA callbacks chỉ là một lớp mở rộng. Hibernate còn có Event System, Interceptor, Integrator, StatementInspector. Chúng **không đồng nhất** về thời điểm và phạm vi.

### 14.1. Hibernate entity event listeners

Hibernate có các event types liên quan:
- `PreInsertEvent` / `PreInsertEventListener`;
- `PreUpdateEvent` / `PreUpdateEventListener`;
- `PreDeleteEvent` / `PreDeleteEventListener`;
- `PostInsertEvent` / `PostUpdateEvent` / `PostDeleteEvent`;
- Load/flush/collection events tùy SPI.

Chúng gắn với entity actions diễn ra trong Hibernate Session event processing. Nếu một Product được load và dirty-check để UPDATE, một số entity event listeners có thể chạy.

Nhưng một query:

~~~java
session.createMutationQuery(
    "update Product p set p.archived = true"
).executeUpdate();
~~~

là một **bulk mutation**, không sinh chuỗi `PreUpdateEvent(Product#1)`, `PreUpdateEvent(Product#2)` ... cho từng row.

Kể cả một Hibernate event listener được đăng ký ở mức `EventListenerRegistry` cũng không thể tự nhận external UPDATE từ một JDBC client độc lập.

### 14.2. Một listener ví dụ qua Hibernate SPI

Ví dụ chữ ký:

~~~java
import org.hibernate.event.spi.PreUpdateEvent;
import org.hibernate.event.spi.PreUpdateEventListener;

public class ProductPreUpdateListener
        implements PreUpdateEventListener {

    @Override
    public boolean onPreUpdate(PreUpdateEvent event) {
        if (!(event.getEntity() instanceof Product product)) {
            return false;
        }

        // Có thể đọc property state/metadata của entity update.
        // Tránh giao tiếp hệ thống ngoài từ đây.
        return false; // false: không veto update.
    }
}
~~~

Đăng ký listener này phải dùng SPI/integrator/registry phù hợp Hibernate version; chỉ định class như trên **không tự đăng ký** listener.

Giá trị return trong `PreUpdateEventListener` có semantics veto theo contract Hibernate. Không copy một listener từ Hibernate 5 sang 6/7 mà không kiểm tra Javadoc, vì SPI có thể thay đổi.

**Điều quan trọng nhất:** kể cả đã đăng ký đúng, listener là **per-entity event listener**, không biến một set-based SQL UPDATE thành N entity UPDATE events.

### 14.3. Interceptor.onFlushDirty và StatementInspector

Hibernate `Interceptor` có hooks liên quan entity lifecycle/flush như `onFlushDirty` trong những phiên bản tương ứng. Cơ chế này nhìn thấy xử lý entity dirty state do Hibernate quản lý, không phải một database change feed.

`StatementInspector` cho phép quan sát/chỉnh SQL string mà Hibernate chuẩn bị, ví dụ:

~~~java
import org.hibernate.resource.jdbc.spi.StatementInspector;

public class SqlTagInspector implements StatementInspector {
    @Override
    public String inspect(String sql) {
        return sql; // Ví dụ tối thiểu, không biến đổi SQL.
    }
}
~~~

StatementInspector có thể được gọi với SQL do Hibernate sinh, bao gồm SQL bulk HQL mutation theo đường Hibernate chuẩn, nhưng:
- Không nắm đầy đủ các row values thực sự bị thay đổi.
- Không nhận callbacks per-entity.
- Không thấy JDBC SQL độc lập do process khác gửi.
- Không phải nơi lý tưởng để gửi audit events phụ thuộc commit.
- Không có một contract chung rằng nó bao phủ JDBC trực tiếp trong `doWork`.

**SQL interception khác entity lifecycle interception**. Một callback SQL inspector có thể thấy một câu UPDATE tổng, nhưng không tự biết 10.000 Product IDs tương ứng.

### 14.4. Hibernate Envers

Hibernate Envers là mô-đun audit/versioning sử dụng Hibernate integration với entity operations/events. Nó có thể ghi audit revisions cho những entity mutations do Hibernate quản lý theo đường event phù hợp.

Nhưng **bulk HQL/JPQL DML, native SQL và external JDBC không tự tạo Envers audit revisions cho từng entity**. Nếu hệ thống dựa vào Envers làm audit source of truth, phải:
- Hạn chế direct/bulk writes tới audited tables;
- Hoặc tích hợp một đường audit riêng cho các writes ngoài entity lifecycle;
- Hoặc thiết kế database/CDC audit có phạm vi bao phủ mọi writers.

Không suy luận bảng audit Envers đầy đủ chỉ vì annotation `@Audited` có trên entity trong khi hệ thống cũng chạy script UPDATE trực tiếp.

### 14.5. @UpdateTimestamp và annotation-generated values

Hibernate có annotations như `@CreationTimestamp`/`@UpdateTimestamp` và các cơ chế generated values theo version. Chúng liên quan Hibernate-managed entity persistence/update paths.

Khi native SQL/JDBC/bulk mutation bypass per-entity generation logic, không mặc định các trường do annotations ấy quản lý sẽ được cập nhật. Nếu DB có default/trigger/computed column thì **DB behavior** có thể cung cấp giá trị — đó là cơ chế khác và cần test riêng.

### 14.6. Domain event vs Hibernate event

Một application service có thể publish:

~~~java
applicationEventPublisher.publishEvent(
    new ProductArchived(productId)
);
~~~

Đây là **application event do code gọi**. Nó không tự được publish khi ai đó chạy `UPDATE products SET archived=true` ngoài service ấy.

Nếu dùng `@TransactionalEventListener(phase = AFTER_COMMIT)`, listener chỉ xử lý event mà application đã publish trong transaction context phù hợp. External SQL không biết Spring events. Ngoài ra, in-process after-commit listener có thể bị mất nếu process crash sau DB commit trước khi handler xử lý; muốn độ bền cao cần outbox/CDC.

## 15. Tại sao Post-callback không phải after-commit hook?

### 15.1. @PostUpdate có thể xảy ra trước COMMIT

~~~text
Transaction begin
       |
       v
Entity changed in memory
       |
       v
Hibernate flush
       |
       +-- @PreUpdate
       |
       +-- SQL UPDATE products
       |
       +-- @PostUpdate
       |
       v
Additional work / more SQL
       |
       +-- Exception possible
       |
       v
COMMIT / ROLLBACK
~~~

Nếu `@PostUpdate` gọi external payment gateway và transaction sau đó rollback, external side effect đã xảy ra nhưng DB state quay lại cũ.

`@PostPersist`/`@PostRemove` cũng không nên mặc định được xem là **committed domain event**. Để gửi email, message bus event hoặc invalidate cache sau transaction, dùng cơ chế transaction-aware riêng và hiểu tính bền vững của nó.

### 15.2. Audit “callback chạy rồi” không nghĩa “DB commit rồi”

Một test ghi log từ `@PostUpdate` có thể cho thấy callback đã chạy dù transaction rollback. Nếu hệ thống dùng callback logs như bằng chứng business action đã commit, nó sẽ tạo dữ liệu kiểm toán sai.

### 15.3. Spring afterCommit là ranh giới khác

Trong Spring:

~~~java
@Transactional
public void archiveOne(Long id) {
    Product product = entityManager.find(Product.class, id);
    product.archive();

    applicationEventPublisher.publishEvent(
        new ProductArchived(id)
    );
}
~~~

Event listener có thể đăng ký `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` để chờ commit trước khi gửi notification. Tuy nhiên:
- Event phải được application publish; bulk/native SQL khác không tự publish.
- In-process callback **không atomic** với DB commit.
- Process có thể crash sau commit trước khi event đến broker.
- Handler async cần idempotency/retry chính xác.

Khi domain event phải không được mất, transactional outbox thường đáng cân nhắc hơn callback in-memory đơn thuần.

## 16. Chọn kỹ thuật theo invariant nghiệp vụ

Không có kết luận “bulk UPDATE luôn sai” hoặc “entity listener luôn đúng”. Mỗi kỹ thuật giải một lớp nhu cầu.

| Yêu cầu | Phương án thường hợp lý | Trade-off |
|---|---|---|
| Chỉnh vài chục entities, cần callbacks/validation/cascade | Load entities, gọi domain methods, flush | Nhiều entity loads, memory/SQL |
| Cập nhật hàng triệu rows, chỉ set một cột | JPQL/HQL bulk DML hoặc native SQL | Bypass per-entity callbacks, cần tự giữ invariants |
| Timestamp/version luôn đúng kể cả direct SQL | DB trigger/generated semantics hoặc SQL DML tường minh | Schema/dialect coupling |
| Audit mọi update trên bảng từ mọi writers | Database audit trigger/CDC hoặc được kiểm soát bởi DB | Vận hành, schema/audit overhead |
| Domain event từ một service do ứng dụng sở hữu | Application service + transactional outbox | Phải quản lý outbox/dispatcher |
| Mọi nguồn ghi đều dùng cùng service API | Đặt business rules trong service/domain model | Phải hạn chế DB write permissions bypass |
| Cache nhất quán sau external DML | Event invalidation/CDC/eviction/TTL theo SLA | Stale window và failure handling |
| Cleanup ngoài DB (search/files/object storage) khi delete | Service workflow + event/outbox | Distributed consistency/retry |
| Bảo đảm dữ liệu không âm, FK hợp lệ | SQL CHECK/FK/NOT NULL/UNIQUE | Không thay đầy đủ complex business rules |
| Phát hiện conflict cập nhật giữa các writers | Version predicate/lock/concurrency design | Có thể cần retry và conflict UI |

Hãy hỏi **ai có quyền ghi dữ liệu này** và **điều gì phải đúng sau mọi đường ghi** trước khi quyết định callback hay bulk SQL.
+## 17. Mẫu 1: vẫn dùng entity callbacks nhưng xử lý theo chunks

Nếu requirement **bắt buộc chạy `@PreUpdate`/`@PreRemove` theo từng entity**, không có cấu hình batch size nào biến một bulk HQL UPDATE thành N entity callback invocations.

Một lựa chọn là nạp entities theo chunks, áp dụng domain operations, flush/clear để tránh giữ quá nhiều managed objects.

### 17.1. UPDATE theo entity lifecycle

~~~java
@Transactional
public int archiveSelected(List<Long> productIds) {
    final int flushInterval = 200;
    int changed = 0;

    for (int i = 0; i < productIds.size(); i++) {
        Product product = entityManager.find(
            Product.class, productIds.get(i)
        );

        if (product != null && !product.isArchived()) {
            product.archive();
            changed++;
        }

        if ((i + 1) % flushInterval == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
    return changed;
}
~~~

Với entity `Product` được update thật:
- `@PreUpdate` có thể chạy ở flush.
- `updatedAt` được listener set.
- `@Version` được Hibernate quản lý theo entity-level update.
- Mapped callbacks/cascades liên quan entity actions có cơ hội thực thi.

Nhưng phương án này có trade-offs:
- Có SELECT để nạp mỗi Product (hoặc batch fetching/query từng page).
- Persistence context phải quản lý entities cho tới lúc flush.
- Nhiều row updates thay vì một set-based UPDATE.
- `flush()/clear()` có thể ảnh hưởng các entities khác nếu transaction dùng context chung.
- List IDs có thể rất dài, nên cần paging/streaming và transaction chunks khi phù hợp.
- `@PreUpdate` chỉ chạy cho entity có UPDATE thực sự, không bắt buộc cho mọi ID được lặp qua.

### 17.2. JDBC batching không phải bulk DML

~~~properties
hibernate.jdbc.batch_size=25
hibernate.order_updates=true
~~~

Trong ví dụ entity-by-entity, Hibernate có thể gom **nhiều entity-level UPDATE statements tương thích** bằng JDBC batching khi mapping/driver cho phép. Dù JDBC driver sử dụng `PreparedStatement.addBatch()/executeBatch()`, các entity callbacks đã được xử lý theo Hibernate entity lifecycle.

Do đó:

~~~text
Nhiều managed Product thay đổi
     |
     +--> @PreUpdate(Product#1)
     +--> @PreUpdate(Product#2)
     +--> @PreUpdate(Product#3)
     |
     v
Hibernate SQL actions
     |
     v
JDBC batch addBatch / executeBatch
~~~

khác hẳn:

~~~text
Một HQL bulk UPDATE
     |
     v
Set-based SQL UPDATE nhiều rows
     |
     v
Database
     |
     +--> Không có per-entity JPA @PreUpdate callbacks
~~~

**“Batching JDBC” và “bulk HQL mutation” không đồng nghĩa.** Câu thứ nhất là cách gom nhiều SQL executions; câu thứ hai thay đổi tập rows trực tiếp qua một mutation query.

### 17.3. Transaction chunk không đồng nghĩa flush interval

- JDBC batch size: số executions gom trong một batch.
- Flush/clear interval: số entity actions giữa các lần flush/detach.
- Transaction chunk size: số records/operations được commit cùng nhau.

Một transaction chứa 10.000 updates và flush mỗi 200 entity vẫn là **một transaction 10.000 updates** nếu outer `@Transactional` bao trùm toàn bộ. Muốn commit từng chunk, cần transaction boundaries riêng, ví dụ một Spring bean xử lý chunk trong `@Transactional`, được gọi qua proxy từ job bean không có outer transaction.

Tuy nhiên, nếu nghiệp vụ cần all-or-nothing cho 10.000 rows, chia thành nhiều commits sẽ thay đổi semantics. Không đổi transaction design chỉ để đạt batch performance.

## 18. Mẫu 2: bulk DML kèm business invariants viết tường minh

Khi dữ liệu quá lớn để load per entity, thay vì hy vọng callback chạy, hãy viết những quy tắc quan trọng ngay trong SQL/JPQL và constraint DB.

### 18.1. JPQL bulk UPDATE gồm timestamp và version

~~~java
@Transactional
public int archiveOldProducts(Instant cutoff, Instant now) {
    int affected = entityManager.createQuery(
        """
        update Product p
           set p.archived = true,
               p.updatedAt = :now,
               p.version = p.version + 1
         where p.archived = false
           and p.createdAt < :cutoff
        """
    )
    .setParameter("now", now)
    .setParameter("cutoff", cutoff)
    .executeUpdate();

    entityManager.clear();
    return affected;
}
~~~

Câu lệnh:
1. Tự set `archived=true`.
2. Tự set `updatedAt`.
3. Tự tăng numeric `version`.
4. Dùng predicate để tránh cập nhật những rows đã archived.
5. Không dựa vào `@PreUpdate`.

`clear()` chỉ phù hợp nếu transaction context hiện tại không cần tiếp tục dùng những managed entities khác, và mọi pending changes cần giữ đã được flush. Trong service được caller chia sẻ transaction, clear bất ngờ có thể là lỗi nghiêm trọng.

### 18.2. Native SQL với CHECK và version predicate

Ví dụ cập nhật giá có điều kiện không cho giá âm:

~~~sql
UPDATE products
   SET price = :new_price,
       updated_at = CURRENT_TIMESTAMP,
       version = version + 1
 WHERE id = :product_id
   AND version = :expected_version
   AND :new_price >= 0;
~~~

Ứng dụng phải kiểm tra affected-row count:

~~~java
int affected = entityManager.createNativeQuery(
    """
    UPDATE products
       SET price = :newPrice,
           updated_at = CURRENT_TIMESTAMP,
           version = version + 1
     WHERE id = :id
       AND version = :expectedVersion
       AND :newPrice >= 0
    """
)
.setParameter("newPrice", newPrice)
.setParameter("id", productId)
.setParameter("expectedVersion", expectedVersion)
.executeUpdate();

if (affected != 1) {
    throw new IllegalStateException(
        "Row missing, invalid price or version conflict"
    );
}
~~~

Không vì đã có `@PreUpdate` hoặc Bean Validation trong entity mà bỏ CHECK constraint/database predicate cần thiết. Các quy tắc DB là tuyến cuối để bảo vệ dữ liệu trước direct SQL.

### 18.3. Ràng buộc không thể diễn đạt chỉ bằng một câu SQL

Ví dụ “trước khi archive Product phải hủy hold ở hệ thống thanh toán, gỡ khỏi search, gửi thông báo cho chủ sở hữu” là workflow xuyên services. Một HQL bulk UPDATE đơn thuần không thể bảo đảm tất cả side effects đó.

Các hướng khả thi:
- Dùng application service/domain workflow per entity nếu số lượng và yêu cầu throughput cho phép.
- Dùng bulk database mutation + durable event/outbox + downstream handlers.
- Dùng staged workflow: đánh dấu yêu cầu archive, worker xử lý ngoại vi rồi xác nhận trạng thái.
- Đưa những invariants cốt lõi vào DB constraints/transactional operations khi có thể.

Không đặt một chuỗi HTTP calls vào `@PreUpdate` rồi mong có distributed atomic transaction.

## 19. Mẫu 3: database triggers cho quy tắc áp dụng với mọi SQL writer

Nếu **mọi nguồn ghi vào một bảng** đều phải cập nhật audit/timestamp và không thể ép họ dùng Hibernate, database trigger có thể là cơ chế phù hợp hơn.

### 19.1. Trigger chạy ở tầng database

Ví dụ PostgreSQL minh họa tự cập nhật `updated_at` mỗi khi rows trong `products` được UPDATE:

~~~sql
CREATE OR REPLACE FUNCTION set_product_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_products_updated_at
BEFORE UPDATE ON products
FOR EACH ROW
EXECUTE FUNCTION set_product_updated_at();
~~~

Với trigger này, một Hibernate entity UPDATE, JDBC UPDATE, HQL bulk UPDATE được dịch thành SQL hoặc một SQL từ ứng dụng khác đều **có thể** kích hoạt trigger nếu chúng thực thi UPDATE trên bảng và trigger được enable.

Cần lưu ý:
- Đây là **PostgreSQL-specific DDL**, không dùng y nguyên trên MySQL/SQL Server/Oracle.
- Một câu bulk UPDATE có thể làm trigger chạy cho từng row theo `FOR EACH ROW`.
- Trigger không gọi `@PreUpdate` của Java entity; nó là cơ chế riêng.
- `updated_at` của managed Java Product có thể vẫn stale cho đến refresh nếu DB trigger thay đổi sau khi Hibernate xây entity state.
- Bảng audit/trigger có chi phí ghi, locking và migration.
- DB privileges có thể cho phép disable triggers hoặc bulk-load bypass trong một số quy trình; thiết kế security/vận hành phù hợp.

### 19.2. Audit row bằng database trigger

Bảng audit ví dụ:

~~~sql
CREATE TABLE product_price_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL,
    old_price DECIMAL(18,2),
    new_price DECIMAL(18,2),
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Trigger function:

~~~sql
CREATE OR REPLACE FUNCTION audit_product_price()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.price IS DISTINCT FROM NEW.price THEN
        INSERT INTO product_price_audit (
            product_id, old_price, new_price
        )
        VALUES (
            NEW.id, OLD.price, NEW.price
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_product_price_audit
AFTER UPDATE ON products
FOR EACH ROW
EXECUTE FUNCTION audit_product_price();
~~~

Bằng `FOR EACH ROW`, trigger có thể tạo audit record cho từng row thay đổi thật, kể cả khi SQL là một bulk UPDATE.

Nếu cả Product UPDATE và audit INSERT thuộc **cùng database transaction**, khi transaction rollback, audit insert cũng rollback theo transaction semantics. Đây là khác biệt quan trọng so với gửi email trong `@PostUpdate`.

### 19.3. Trigger không thay thế domain events ở tầng ứng dụng

Database trigger biết OLD/NEW row data nhưng thường không biết đầy đủ:
- Người dùng cuối đã yêu cầu gì, lý do nghiệp vụ nào.
- Correlation ID, tenant context, authorization decision.
- Trạng thái từ hệ thống khác.
- Business event “CheckoutCompleted” khác với thay đổi một field.

Nếu muốn audit kèm user/reason, cần cách truyền context đúng (ví dụ transaction metadata/session variables an toàn hoặc columns explicit), hoặc ghi outbox từ application service.

Không biến trigger thành nơi thực hiện HTTP request; DB trigger cần nhanh, dự đoán được và transactionally safe.

## 20. Mẫu 4: transactional outbox thay cho callback phát external event

### 20.1. Vì sao after-commit application event có lỗ hổng?

Giả sử:

~~~text
Database UPDATE commit thành công
            |
            v
Java @PostUpdate / afterCommit handler định gửi message
            |
            X  Process crash trước khi gửi
            |
            v
External service không biết Product đã đổi
~~~

`@PostUpdate` còn có vấn đề sớm hơn: nó có thể chạy **trước commit** rồi transaction rollback. Một callback after-commit tránh được publish trước commit, nhưng nếu process chết giữa commit và send thì message vẫn có thể mất.

Transactional outbox giải quyết ranh giới bằng cách **ghi state change và event intent vào cùng DB transaction**.

### 20.2. Bảng outbox mẫu

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(64) PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(80),
    event_type VARCHAR(120) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP NULL
);
~~~

### 20.3. Entity cập nhật + outbox insert trong một transaction

~~~java
@Transactional
public void archiveOne(Long productId) {
    Product product = entityManager.find(
        Product.class, productId
    );

    if (product == null) {
        throw new IllegalArgumentException("Product missing");
    }

    product.archive();

    OutboxEvent event = new OutboxEvent(
        UUID.randomUUID().toString(),
        "Product",
        productId.toString(),
        "ProductArchived",
        "{\"productId\":" + productId + "}"
    );

    entityManager.persist(event);
}
~~~

Ví dụ giả định `OutboxEvent` là entity được mapping tới bảng trên và có constructor tương ứng. Trong code thật nên serialize JSON qua thư viện JSON thay vì tự nối chuỗi, đặc biệt với string/user data.

Khi commit:
- UPDATE Product (nếu dirty) và INSERT Outbox cùng transaction.
- Nếu transaction rollback, cả hai cùng rollback.
- Worker/publisher đọc committed outbox events và gửi tới message broker.
- Consumer xử lý idempotently và cập nhật published state/retry.
- Có thể phát lại event nếu publish xong nhưng chưa mark published.

### 20.4. Bulk UPDATE + outbox: chọn đúng granularity

Nếu một câu bulk SQL archive 50.000 Products, có ít nhất hai yêu cầu khác nhau:

**Yêu cầu A: chỉ cần thông báo “đã chạy đợt archive”.**

Một event dạng `ProductsArchivedInBulk` với `batchId`, cutoff, affected count và metadata có thể đủ nếu downstream biết cách tự rebuild/reconcile tập dữ liệu.

**Yêu cầu B: phải phát một event chính xác cho từng Product ID đã thay đổi.**

Không đủ để chỉ chạy bulk UPDATE rồi tạo một event chứa số `affected=50000`. Cần xác định **chính xác IDs đã bị đổi**, không dùng một SELECT trước UPDATE mà không tính concurrency/race.

Các chiến lược:
- Database-specific DML `UPDATE ... RETURNING`/CTE hoặc staging table lưu impacted IDs trong cùng transaction.
- Một database trigger ghi audit/outbox row cho mỗi updated row.
- Chạy entity-by-entity workflow nếu không cần throughput cực lớn.
- Một job hai pha với lock/version/claim semantics và kiểm tra affected IDs đầy đủ.

Phải bảo đảm update và ghi outbox có atomicity trong cùng database transaction; nếu ghi outbox sau commit vào hệ khác thì lại tạo một dual-write failure window.

### 20.5. Event consumer và cache invalidation

Outbox/CDC có thể cung cấp change events cho:
- Search indexing.
- Cache eviction/invalidation.
- Analytics projections.
- Notifications.
- Downstream workflows.

Nhưng event processing thường **eventually consistent**. Cần:
- Idempotent consumers bằng `event_id`.
- Retry/backoff/dead-letter.
- Ordering/version handling.
- Monitoring lag và reconciliation.
- Không cho old event overwrite state mới khi delivery out of order.

Transactional outbox không phải một thay thế trực tiếp cho `@PreUpdate` khi requirement là validation **trước khi ghi DB**. Nó phù hợp với **reliable effects sau committed state change**.

## 21. Mẫu 5: CDC khi nhiều ứng dụng có quyền cập nhật

### 21.1. Khi callback của một service không thể bao phủ mọi writer

Nếu Product table được cập nhật từ:
- Service Java/Hibernate.
- ETL Python/JDBC.
- Admin SQL.
- Một service .NET.
- Stored procedure trong DB.

thì mỗi service có một bộ callbacks/ORM khác nhau (hoặc không có ORM). Không có lý do kỳ vọng listener Java của service A bao phủ mọi write.

**Change Data Capture (CDC)** có thể lấy committed changes từ transaction log/database change feed (tùy DB/connector) và chuyển thành events cho audit/index/cache systems.

~~~text
Hibernate service ------\
JDBC ETL ----------------+--> Database commit / log
Admin SQL --------------/
                             |
                             v
                        CDC connector
                             |
                             v
                        Message stream
                             |
            +----------------+----------------+
            |                |                |
            v                v                v
          Audit         Search index      Cache invalidation
~~~

### 21.2. CDC không tự biết semantic domain event

CDC thường biết row changes, không nhất thiết biết business intent. Chẳng hạn một Product chuyển archived=false → true có thể đến từ:
- Chủ hàng chủ động archive.
- Product hết hạn.
- Bảo trì dữ liệu.
- Admin sửa trực tiếp.

Nếu downstream cần phân biệt các ý định đó, cần encode reason/correlation/batch ID vào database schema/outbox/event payload hoặc áp dụng domain event từ source of truth.

### 21.3. CDC cũng phải có consistency contract

- Có độ trễ giữa commit và event delivery.
- Phải xử lý duplicate/change ordering.
- Schema migrations có thể thay đổi payload.
- Consumer cần idempotent và replay strategy.
- Một số bulk operations có thể phát rất nhiều change records.
- Monitoring/connectors cần vận hành riêng.

CDC thích hợp cho observability/change propagation của nhiều DB writers, không thay thế trực tiếp Bean Validation/domain rules trước khi commit.
+## 22. Integration tests: chứng minh callback chạy hoặc bị bypass

Đây là chủ đề **phải thử với Hibernate provider và database thật** khi ứng dụng phụ thuộc correctness của audit/validation. Unit test chỉ mock repository rồi tự gọi listener method không chứng minh vòng đời JPA provider.

### 22.1. Tạo listener đếm callback trong phạm vi test

Một fixture kiểm thử có thể dùng counter để **quan sát**:

~~~java
import jakarta.persistence.*;
import java.util.concurrent.atomic.AtomicInteger;

public final class CallbackProbe {

    public static final AtomicInteger prePersist =
        new AtomicInteger();

    public static final AtomicInteger preUpdate =
        new AtomicInteger();

    public static final AtomicInteger preRemove =
        new AtomicInteger();

    private CallbackProbe() {}

    public static void reset() {
        prePersist.set(0);
        preUpdate.set(0);
        preRemove.set(0);
    }
}

public class ProbeListener {

    @PrePersist
    public void prePersist(Object entity) {
        CallbackProbe.prePersist.incrementAndGet();
    }

    @PreUpdate
    public void preUpdate(Object entity) {
        CallbackProbe.preUpdate.incrementAndGet();
    }

    @PreRemove
    public void preRemove(Object entity) {
        CallbackProbe.preRemove.incrementAndGet();
    }
}
~~~

Dùng `@EntityListeners(ProbeListener.class)` trên một entity **test fixture** riêng, không chèn static counter vào production code. Counter static chỉ phù hợp test chạy **tuần tự/cô lập**, không bảo đảm đúng nếu suite chạy song song hoặc nhiều tests chia sẻ listener.

### 22.2. Test entity-level update có callback

~~~java
@Test
@Transactional
void managedEntityUpdateInvokesPreUpdate() {
    CallbackProbe.reset();

    ProbeProduct product = entityManager.find(
        ProbeProduct.class, fixtureId
    );

    product.rename("Changed-" + UUID.randomUUID());

    entityManager.flush();

    assertTrue(CallbackProbe.preUpdate.get() > 0);
}
~~~

Giả định `ProbeProduct` mapping listener trên và `fixtureId` đã tồn tại. Để tránh trường hợp Hibernate không thấy dirty change, test dùng một tên khác dữ liệu ban đầu.

Nếu test chỉ gọi `product.rename(...)` rồi assert ngay trước flush, callback có thể chưa chạy — vì update action chưa đến lúc thực thi.

### 22.3. Test bulk JPQL UPDATE không gọi @PreUpdate cho mỗi row

~~~java
@Test
@Transactional
void bulkUpdateBypassesPreUpdate() {
    CallbackProbe.reset();

    int affected = entityManager.createQuery(
        """
        update ProbeProduct p
        set p.archived = true
        where p.archived = false
        """
    ).executeUpdate();

    assertTrue(affected >= 0);
    assertEquals(0, CallbackProbe.preUpdate.get());
}
~~~

Với fixture độc lập, đảm bảo không còn pending managed updates từ setup hoặc một test khác trong cùng context; flush/clear trước khi reset probe nếu cần. Điều quan trọng là **isolate đường bulk DML** để event đến từ managed entity không bị tính nhầm.

Nếu DB trigger làm thay đổi các cột sau UPDATE, điều đó vẫn không tạo JPA `@PreUpdate`. Muốn xác nhận database effects, query SQL state riêng.

### 22.4. Test entity-level remove và bulk delete

Hai ca riêng:

**Remove path:**

~~~java
@Test
@Transactional
void removeManagedEntityInvokesPreRemove() {
    CallbackProbe.reset();

    ProbeProduct product = entityManager.find(
        ProbeProduct.class, fixtureId
    );

    entityManager.remove(product);
    entityManager.flush();

    assertTrue(CallbackProbe.preRemove.get() > 0);
}
~~~

**Bulk delete path:**

~~~java
@Test
@Transactional
void bulkDeleteBypassesPreRemove() {
    CallbackProbe.reset();

    int affected = entityManager.createQuery(
        "delete from ProbeProduct p where p.archived = true"
    ).executeUpdate();

    assertTrue(affected >= 0);
    assertEquals(0, CallbackProbe.preRemove.get());
}
~~~

Dùng fixtures khác nhau và xử lý foreign keys đúng để test không phụ thuộc data của ca trước. Một số callback như `@PreRemove` được provider kích hoạt ở thời điểm `remove` hoặc flush; test chỉ kiểm tra sau `flush` để tránh suy luận timing quá sớm.

### 22.5. Test @PostLoad và DTO projection

Hai query:
1. `select p from ProbeProduct p` và clear context trước đó để buộc load.
2. `select new ...Dto(p.id, p.name) ...` chỉ project scalar/DTO.

Một `@PostLoad` probe có thể đếm entities được hydrate trong ca 1. Ca 2 không nên kỳ vọng entity callback cho mỗi DTO row nếu query không materialize ProbeProduct entity.

**Không** dùng count PostLoad làm thước đo số SQL rows: cache, same-context identity và entity reuse làm số callbacks khác số result rows.

### 22.6. Test native SQL và JDBC độc lập

~~~java
@Test
@Transactional
void nativeUpdateDoesNotCallPreUpdatePerEntity() {
    CallbackProbe.reset();

    entityManager.createNativeQuery(
        """
        UPDATE probe_products
           SET archived = true
         WHERE archived = false
        """
    ).executeUpdate();

    assertEquals(0, CallbackProbe.preUpdate.get());
}
~~~

JDBC test dùng `PreparedStatement`/`JdbcTemplate` tương ứng. Test cần đúng bảng của ProbeProduct và transaction fixture.

Để chứng minh **external application** không phát Hibernate callbacks, dùng hai connections/transactions độc lập hoặc một integration test process khác; gọi JDBC ngay trong same process vẫn không có per-entity callback nhưng không kiểm chứng được multi-process behavior.

### 22.7. Test audit và version

Nếu audit bắt buộc, **đừng chỉ test callback count**. Test cả:
- DB row `updated_at` sau bulk update.
- `version` tăng hay không theo strategy.
- Audit table có record đúng số lượng/IDs không.
- Khi rollback, audit record còn hay mất?
- Khi external JDBC thay đổi dữ liệu, audit có đầy đủ không?
- L2/query cache có bị invalidation theo policy không?
- Nếu outbox publisher crash, event có được retry/replay không?

Một hệ có JPA callback “pass” nhưng audit DB không đầy đủ vẫn chưa đáp ứng mục tiêu nghiệp vụ.

### 22.8. Spring test có thể vô tình che giấu transaction lỗi

Một `@SpringBootTest @Transactional` test tự mở transaction, nên service/repository thiếu `@Transactional` trong production vẫn có thể chạy khi được gọi từ test.

Để kiểm chứng service transaction boundary:
1. Gọi bean service qua Spring proxy.
2. Tránh test-level transaction bao quanh trường hợp cần kiểm tra service tự commit/rollback.
3. Kiểm tra state DB trong một transaction mới sau khi service trả về.
4. Với outbox, xác nhận commit state và publisher behavior độc lập.
5. Với `REQUIRES_NEW`, xác định inner transaction có thể commit riêng dù outer rollback.

## 23. Tình huống thực tế: archive toàn bộ sản phẩm quá hạn

### 23.1. Bài toán nghiệp vụ

Mỗi đêm, 300.000 Products hết hạn cần được archive. Hệ thống yêu cầu:

- `archived=true` và `updated_at` đúng.
- Version thay đổi để clients đang sửa entity phát hiện conflict.
- Product không còn xuất hiện trong search/cache.
- Một audit record cho mỗi Product thực sự chuyển từ active sang archived.
- Job có thể chạy lại sau crash mà không tạo audit/event trùng.
- Không thể load đồng thời 300.000 managed entities trong JVM.

Chỉ thêm:

~~~java
@PreUpdate
void audit() { ... }
~~~

**không thể bảo đảm toàn bộ yêu cầu** nếu job dùng một bulk UPDATE. Phải thiết kế workflow phù hợp.

### 23.2. Phương án entity-by-entity

~~~text
Page IDs cần archive
      |
      v
Load entities trong transaction/chunk
      |
      v
product.archive() cho từng Product
      |
      v
@PreUpdate / Hibernate lifecycle
      |
      v
Flush / JDBC batching / commit
      |
      v
Phát event/outbox từ service
~~~

Ưu điểm:
- Có domain operations, validation/lifecycle theo entity.
- Hibernate optimistic locking hoạt động với managed entities.
- Dễ liên kết Business Event cho từng Product ID tại service layer.

Nhược điểm:
- SQL SELECT/UPDATE nhiều.
- Memory/dirty checking/transaction cost.
- Callback vẫn không phải event commit đáng tin cậy cho external systems.
- Phải dùng transaction chunks, idempotency và batch fetching hợp lý.

### 23.3. Phương án set-based + DB audit/outbox

~~~text
Claim batch / xác định rows cần archive
                 |
                 v
Database transaction:
  UPDATE products
    SET archived=true,
        updated_at=...,
        version=version+1
    WHERE archived=false AND expired...
                 |
                 +--> DB trigger audit rows hoặc
                 |    UPDATE...RETURNING / staging impacted IDs
                 |
                 +--> Outbox event(s) cho impacted rows/batch
                 |
                 v
              COMMIT
                 |
                 v
        Outbox/CDC publisher
          /             \
         v               v
      Search           Cache
      update          invalidation
~~~

Ưu điểm:
- Database xử lý set-based DML, thường phù hợp số lượng lớn.
- Có thể audit mọi row qua DB trigger trong cùng transaction.
- Có thể đảm bảo event intent được lưu cùng DB update.

Nhược điểm:
- Phụ thuộc dialect/schema/trigger/CDC.
- Cần cơ chế lấy đúng impacted IDs, xử lý retry và concurrency.
- Listener Java không tham gia per row; domain rules phải chuyển vào SQL/DB/service.
- Cần policy idempotency và duplicate event handling.

### 23.4. Sai lầm với SELECT IDs trước UPDATE

Ví dụ thiếu an toàn nếu không xử lý concurrency:

~~~java
List<Long> ids = selectIdsEligibleForArchive(cutoff);

// Một transaction khác có thể đã đổi trạng thái/điều kiện
// giữa SELECT và UPDATE.

int count = bulkArchive(cutoff);

// Gửi một event cho mọi id trong ids dù tập UPDATE thực tế
// có thể khác do race: không đáng tin.
~~~

Giải pháp cần đảm bảo **tập IDs phát event** khớp với rows thực sự đã đổi. Cách thực hiện tùy DB:
- UPDATE + RETURNING trong cùng transaction nếu DB hỗ trợ.
- Staging/claim IDs với locks/version predicates và kiểm tra affected set.
- DB trigger ghi outbox per row.
- Serializing/partitioning job hoặc transaction isolation phù hợp.
- Reconciliation khi có concurrent writers.

Không dùng một count aggregate như bằng chứng rằng tất cả IDs preselected đã được update.

### 23.5. Version và client conflict

Nếu job bulk archive Product#42 mà không tăng version, client đã load Product#42 trước đó có thể cố sửa name/price với version cũ và ghi đè hoặc tạo state không mong muốn, tùy SQL/mapping.

Cập nhật numeric `version = version + 1` trong bulk DML là một biện pháp hỗ trợ conflict detection. Tuy nhiên, nếu business logic cần cấm chỉnh sửa archived Product, còn phải bảo đảm điều kiện ở update path, ví dụ recheck archived status/DB predicate, không chỉ dựa vào version.

### 23.6. Audit và callback trong từng lựa chọn

| Yêu cầu | Per-entity path | Set-based path |
|---|---|---|
| JPA `@PreUpdate` | Có thể chạy cho entity UPDATE | Không |
| Tự set timestamp trong callback | Có thể | Phải set bằng SQL/trigger |
| Optimistic locking theo managed entity | Theo mapping | Thiết kế version/predicate riêng |
| Audit record mỗi Product | Service/Envers/DB theo config | DB trigger/RETURNING/outbox |
| External notification sau commit | Outbox/event integration | Outbox/CDC |
| Memory khi xử lý 300k rows | Cần chunk/clear | Thường ít entity materialization |
| DB throughput | Có thể JDBC batch | Set-based SQL |
| Portability | JPA-centric | SQL/trigger/dialect có thể đặc thù |
| External JDBC coverage | Không nhờ callback | DB trigger/CDC có thể bao phủ |

## 24. Các lỗi và hiểu lầm thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `@PreUpdate` không chạy sau `executeUpdate()` | Bulk JPQL/HQL bypass entity lifecycle | Đặt invariants trong DML/DB hoặc xử lý per-entity |
| `@PreRemove` không chạy sau `deleteAllInBatch()` | Bulk DELETE thay vì remove từng entity | Chọn delete path đúng callbacks/cascade requirements |
| @LastModifiedDate không thay đổi với bulk query | Spring Data auditing dựa entity lifecycle | Set timestamp trong DML/trigger |
| `updatedAt` đúng với entity update nhưng sai với JDBC | JDBC bỏ qua Java listener | SQL tự set hoặc DB trigger |
| `@Version` không tăng sau JPQL bulk UPDATE | Bulk update không auto-version theo entity semantics | Tăng numeric version có chủ đích/test |
| `@PostUpdate` chạy nhưng transaction rollback | Post callback không phải after-commit | Outbox/commit-aware design |
| Envers thiếu audit rows sau bulk SQL | Không có entity events cho từng row | Chuyển audit sang DB/outbox/CDC hoặc hạn chế writes |
| NativeQuery có `addSynchronizedEntityClass` nhưng listener vẫn không chạy | Query-space metadata không tạo managed entity actions | Không dùng synchronization API để kích hoạt callbacks |
| Hibernate `PreUpdateEventListener` không nhận external SQL | External JDBC không qua Session event system | DB trigger/CDC |
| StatementInspector thấy một UPDATE nhưng không biết IDs | Inspector nhìn SQL text, không phải rows thay đổi | RETURNING/staging/audit trigger |
| Bulk DELETE thất bại do FK | Không cascade REMOVE qua Java graph | Thiết kế DB FK/cascade hoặc entity deletion |
| DB ON DELETE CASCADE xóa child nhưng Java listener không chạy | Database cascade ngoài ORM lifecycle | DB audit/cleanup workflow riêng |
| `@PostLoad` không chạy khi đọc DTO | DTO không được hydrate thành managed entity | Không dùng entity callback cho DTO |
| `@PostLoad` không chạy lại khi `find` | Entity đã có trong L1 | Refresh/context mới khi cần |
| PreUpdate không chạy sau setter cùng giá trị | Có thể không có dirty UPDATE | Không dùng callback như timer |
| Managed Product vẫn `archived=false` sau bulk SQL | L1 giữ state cũ | Refresh/clear/context mới |
| Clear làm mất thay đổi managed khác | Clear trước flush trong shared context | Flush có chủ đích; scope service phù hợp |
| Một transaction có callback logs của vài entity, tưởng bulk gọi listeners | Flush pending managed changes khác | Phân biệt operation source |
| DB trigger làm field đổi nhưng entity vẫn cũ | Trigger thay DB sau SQL, L1 chưa reload | Refresh/generated value handling |
| Native UPDATE chạy qua Hibernate nhưng cache không như mong muốn | Query-space metadata, cache provider/dialect | Kiểm tra SQL paths và invalidation strategy |
| Callback gửi email dù DB rollback | External side effect không transactional | Outbox hoặc explicit saga/retry |
| After-commit event đôi khi bị mất | Process crash sau commit trước publish | Transactional outbox/CDC |
| Bulk event count đúng nhưng per-ID events sai | Preselect IDs race với bulk mutation | RETURNING/trigger/staging concurrency-safe |
| Listener gây recursion/deadlock | Gọi EM/query/other writes trong callback | Giữ callback cục bộ; chuyển logic sang service |
| @PreRemove không chạy khi xóa bằng SQL script | SQL script không chạy Java ORM | Database audit/permissions |
| Validation @Min bị bypass bởi ETL | DB thiếu CHECK constraint | Thiết lập DB constraints |
| Batch import dùng JDBC addBatch nhưng thiếu @PrePersist | JDBC batching không phải entity persist | Đưa default vào SQL/DB hoặc dùng entity ops |
| Hibernate interceptor không thấy JDBC từ app khác | Interceptor chỉ trong Hibernate integration | CDC/DB triggers |

## 25. Bài tập thực hành

### Bài 1 — Hai đường UPDATE

Cho hai đoạn:

~~~java
// A
Product p = em.find(Product.class, id);
p.changePrice(new BigDecimal("19.90"));
em.flush();

// B
em.createQuery(
    "update Product p set p.price = :price where p.id = :id"
).setParameter("price", new BigDecimal("19.90"))
 .setParameter("id", id)
 .executeUpdate();
~~~

**Hỏi:** `@PreUpdate` có nhất thiết chạy ở cả A và B không?

**Đáp án:** Không. A đi qua entity dirty checking nếu có update thật; B là JPQL bulk UPDATE và không gọi callback per entity.

### Bài 2 — Bulk DELETE và audit

Một entity có `@PreRemove` ghi audit log. Một job gọi `deleteAllInBatch()`.

**Hỏi:** có thể coi audit đầy đủ không?

**Đáp án:** Không. Bulk delete bypass per-entity lifecycle. Cần chọn entity removal hoặc audit được bảo đảm bằng DB/CDC/outbox.

### Bài 3 — @PostLoad với nhiều kết quả

Một query `select p from Product p` trả 500 managed Products.

**Hỏi:** `@PostLoad` chắc chắn được gọi 500 lần trong mọi hoàn cảnh?

**Đáp án:** Không. Chỉ entities được load theo lifecycle semantics mới kích hoạt; các instance đã managed trong L1 có thể được reuse, cache/queries có ảnh hưởng. Không dùng PostLoad như bộ đếm rows.

### Bài 4 — DTO query

~~~sql
select new com.example.catalog.ProductCard(p.id, p.name, p.price)
from Product p
~~~

**Hỏi:** ProductCard có chạy `@PostLoad(Product)` không?

**Đáp án:** Không có Product entity lifecycle load chỉ vì một DTO được dựng từ scalar projection.

### Bài 5 — update timestamp

`@PreUpdate` đặt `updatedAt=now`, bulk SQL set `archived=true`.

**Hỏi:** phải thêm gì?

**Đáp án:** Set `updatedAt` trong câu bulk SQL hoặc DB trigger/generated policy. Không dựa callback.

### Bài 6 — optimistic version

Bulk JPQL UPDATE không nhắc `version`.

**Hỏi:** version có tự tăng theo rules của entity-level update không?

**Đáp án:** Không mặc định. Có thể cần version increment tường minh và concurrency predicate theo nhu cầu.

### Bài 7 — Hibernate event listener

Ứng dụng đăng ký `PreUpdateEventListener`.

**Hỏi:** liệu một script JDBC ngoài JVM có gọi listener đó không?

**Đáp án:** Không. Script chỉ tác động DB, không vào Hibernate Session event system.

### Bài 8 — StatementInspector

Một interceptor nhìn thấy SQL string `UPDATE products SET archived=true`.

**Hỏi:** đã biết chính xác mọi Product IDs bị đổi chưa?

**Đáp án:** Chưa. SQL text không chứa đầy đủ affected row set cho predicate tổng quát; dùng RETURNING/staging/DB audit nếu cần.

### Bài 9 — Database trigger

PostgreSQL có row-level AFTER UPDATE trigger tạo price audit.

**Hỏi:** một JDBC bulk UPDATE có tạo audit rows không?

**Đáp án:** Có thể, nếu trigger được enable và UPDATE thực hiện trên bảng theo DB rules. Đây là DB trigger, không phải JPA callback.

### Bài 10 — @PostUpdate và rollback

`@PostUpdate` gửi email rồi transaction rollback.

**Hỏi:** email có tự rollback không?

**Đáp án:** Không. Chọn event/outbox/transactional coordination phù hợp.

### Bài 11 — afterCommit crash

Sau DB commit, app crash trước khi gửi message.

**Hỏi:** giải pháp nào giúp không bỏ lỡ event intent?

**Đáp án:** Transactional outbox ghi state+event trong cùng transaction, rồi publisher retry/replay; hoặc CDC phù hợp.

### Bài 12 — bulk UPDATE 100.000 rows

Business rule chỉ cần set archived, timestamp, version; không có cross-service action.

**Hỏi:** có cần load toàn bộ entities để callback chạy không?

**Đáp án:** Không nhất thiết. Một set-based DML với explicit field updates, DB constraints và test có thể hợp lý hơn.

### Bài 13 — domain validation

`@PreUpdate` throw nếu price âm; ETL dùng JDBC ghi price=-1.

**Hỏi:** invariant được bảo vệ không?

**Đáp án:** Không nhờ Java callback. Cần CHECK constraint/validation ở đường ETL hoặc giới hạn DB permissions.

### Bài 14 — FK cascade

Một bulk SQL DELETE parent kích hoạt DB `ON DELETE CASCADE` tới child.

**Hỏi:** Hibernate có gọi `@PreRemove` cho mỗi child không?

**Đáp án:** Không. DB cascade không đi qua Java entity removal lifecycle.

### Bài 15 — stale state

Product đang managed có `archived=false`. Bulk JPQL set true, getter vẫn false.

**Hỏi:** hướng xử lý?

**Đáp án:** Refresh Product khi còn tồn tại, hoặc clear/context mới nếu nhiều rows, sau khi xử lý pending changes.

### Bài 16 — Spring Data derived delete

So sánh `deleteByArchivedTrue()` với `@Modifying @Query("delete ...")`.

**Hỏi:** có luôn giống nhau về callbacks không?

**Đáp án:** Không. Derived delete ở một số Spring Data JPA paths có thể load và remove entities; bulk modifying query không chạy per-entity callbacks. Kiểm tra implementation/version.

### Bài 17 — JDBC batching vs bulk HQL

Một vòng lặp `persist(entity)` tạo 1.000 entities rồi Hibernate JDBC-batch INSERT.

**Hỏi:** có thể có `@PrePersist` không?

**Đáp án:** Có. JDBC batching diễn ra sau các entity lifecycle actions; khác với HQL bulk INSERT/INSERT SELECT.

### Bài 18 — audit nhiều nguồn ghi

Product table được sửa bởi Hibernate, Python ETL và admin scripts.

**Hỏi:** audit chỉ dùng Envers có đủ không?

**Đáp án:** Không mặc định. Envers thường theo Hibernate entity events, không bao phủ tất cả external writers. Cần thay đổi write ownership hoặc database/CDC audit.

### Bài 19 — preselect IDs và concurrency

Job SELECT IDs eligible trước, rồi bulk UPDATE. Transaction khác sửa một số rows trong khoảng giữa.

**Hỏi:** có thể gửi event cho tất cả IDs preselected không?

**Đáp án:** Không nếu yêu cầu chính xác per-updated-row events. Phải xác định impacted IDs qua DML/locking/trigger/RETURNING hoặc staged workflow.

### Bài 20 — query space synchronization

`session.createNativeQuery(...).addSynchronizedEntityClass(Product.class)`.

**Hỏi:** metadata đó có gọi `@PreUpdate` per entity không?

**Đáp án:** Không. Nó phục vụ Hibernate query-space/flush/cache coordination, không chuyển raw SQL thành entity lifecycle.

### Bài 21 — callback là transaction boundary?

`@PostPersist` chạy, sau đó service ném exception.

**Hỏi:** có thể nói persist đã commit vì post-callback chạy không?

**Đáp án:** Không. Flush/post lifecycle và commit là hai giai đoạn khác nhau; DB transaction có thể rollback.

### Bài 22 — transactional outbox và transaction

Job bulk UPDATE Product rồi INSERT outbox event trong **cùng database transaction**.

**Hỏi:** nếu transaction rollback thì event intent có tồn tại không?

**Đáp án:** Không, nếu cả UPDATE và INSERT outbox thực sự nằm trong cùng transaction và cùng atomic DB resource. Đây là lợi thế quan trọng của transactional outbox.

### Bài 23 — chọn giữa trigger và application listener

Yêu cầu: `updated_at` phải thay đổi với mọi SQL UPDATE, kể cả admin SQL.

**Hỏi:** Java `@PreUpdate` hay DB trigger phù hợp hơn làm hàng rào cuối?

**Đáp án:** DB trigger/generated policy vì nó nằm ở tầng DB mà mọi đường ghi tới bảng đi qua (trừ các trường hợp DB cho phép disable/bypass và cần governance).

### Bài 24 — multiple service notifications

Product bị archive và cần search reindex, cache invalidation, audit export.

**Hỏi:** có nên gọi ba HTTP APIs trong `@PreUpdate` không?

**Đáp án:** Không nên. Transaction còn có thể rollback và external failures gây coupling. Dùng outbox/CDC + idempotent consumers hoặc workflow thích hợp.

## 26. Tổng kết

### 26.1. Bảng kết luận theo đường thao tác

| Đường xử lý | Có per-entity JPA callbacks? | Có database triggers? | Ghi chú |
|---|---|---|---|
| `EntityManager.persist(entity)` | Có theo lifecycle | Có nếu DB INSERT và trigger phù hợp | `@PrePersist`, `@PostPersist` |
| Managed entity dirty checking + flush | Có thể có nếu UPDATE thực sự | Có nếu DB UPDATE và trigger phù hợp | `@PreUpdate`, `@PostUpdate` |
| `EntityManager.remove(entity)` | Có theo lifecycle | Có nếu DB DELETE và trigger phù hợp | `@PreRemove`, `@PostRemove` |
| SELECT load entity | `@PostLoad` khi entity được load | Không có DML trigger chỉ bởi SELECT | Không dùng PostLoad để đếm rows |
| SELECT DTO/scalar | Không có callback entity cho DTO | Không | DTO không phải managed entity |
| JPQL/HQL bulk UPDATE | **Không** per updated row | Có thể, theo DB UPDATE | Update timestamps/version tường minh |
| JPQL/HQL bulk DELETE | **Không** per deleted row | Có thể, theo DB DELETE | Không cascade REMOVE theo entity graph |
| HQL bulk INSERT | **Không** per inserted row | Có thể, theo DB INSERT | Phải cung cấp defaults/invariants |
| Native SQL qua EntityManager/Session | **Không** per affected row | Có thể, theo SQL/DB | Hibernate query-space metadata ≠ callbacks |
| JDBC/JdbcTemplate/doWork | **Không** per affected row | Có thể, theo SQL/DB | Không đi qua entity lifecycle |
| Stored procedure thay rows | **Không** per affected row | Có thể, theo statement và DB | Side effects cần được tính |
| SQL từ ứng dụng khác | **Không** trong JVM Hibernate hiện tại | Có thể, theo DB | Cần cache/audit/event strategy riêng |
| DB FK ON DELETE CASCADE | **Không** cho child bị xóa bởi DB | Có thể, theo DB trigger rules | Không gọi child JPA PreRemove |

### 26.2. Năm nguyên tắc thiết kế

1. **Callbacks là entity lifecycle hooks, không phải database triggers.** Chúng chỉ có phạm vi các operations do JPA/Hibernate quản lý theo lifecycle tương ứng.
2. **Bulk DML tối ưu số lượng rows nhưng bypass per-entity hooks.** Không phải Java callback sẽ tự chạy vì query có tên entity.
3. **Business invariants phải tồn tại ở tầng bao phủ mọi writer cần thiết.** Dùng DB constraints/triggers khi thích hợp, explicit DML hoặc tập trung service API.
4. **Auditing và external notifications cần transaction-aware, durable design.** `@PostUpdate` không đồng nghĩa after commit; Envers không bao phủ mọi external SQL.
5. **Persistence context và cache có thể stale sau bulk/native writes.** Refresh/clear/invalidate đúng tầng, và tách rõ khỏi vấn đề callback.

### 26.3. Một câu hỏi giúp chọn đúng API

Khi chuẩn bị viết một câu lệnh cập nhật nhiều rows, hãy hỏi:

> “Đây chỉ là phép đổi trạng thái dữ liệu theo tập hợp, hay mỗi entity có một vòng đời nghiệp vụ riêng với validation, cascade, audit và side effects bắt buộc?”

Nếu chỉ là set-based mutation, bulk HQL/JPQL/native SQL có thể phù hợp, nhưng phải thể hiện timestamp/version/constraints/audit rõ ràng. Nếu mỗi entity có lifecycle riêng, cân nhắc entity-by-entity operations kết hợp JDBC batching và transaction chunks. Nếu audit/events phải bao phủ cả external writers, ứng dụng cần một cơ chế ngoài Java lifecycle callbacks, như database trigger, CDC hoặc outbox được thiết kế đúng.

## Tài liệu chính thức

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — entity lifecycle callbacks, entity listeners, persistence context, bulk update/delete semantics.
- [Jakarta Persistence API](https://jakarta.ee/specifications/persistence/) — `EntityManager`, `@PreUpdate`, `@PreRemove`, `@PostLoad`, `@EntityListeners`.
- [Hibernate ORM Documentation](https://docs.hibernate.org/orm/) — chọn version User Guide/Javadocs phù hợp dependency.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — entity lifecycle, event system, HQL/JPQL bulk DML, flush, native SQL.
- [Hibernate ORM 6.6 HQL Guide](https://docs.hibernate.org/orm/6.6/querylanguage/html_single/) — mutation statements và các giới hạn khi thực thi bulk DML.
- [Hibernate ORM 6.6 Event System Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/event/spi/package-summary.html) — entity event types/listener contracts.
- [Hibernate ORM 6.6 StatementInspector Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/resource/jdbc/spi/StatementInspector.html) — SQL inspection extension.
- [Hibernate Envers](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#envers) — entity auditing integration, scope và cấu hình.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/) — deleting queries, modifying queries, repository lifecycle và transactions.
- [Spring Data JPA — Modifying Queries](https://docs.spring.io/spring-data/jpa/reference/jpa/modifying-queries.html) — `@Modifying`, `flushAutomatically`, `clearAutomatically`, derived delete vs bulk.
- [PostgreSQL — Trigger Functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html) — `OLD`/`NEW`, row-level triggers.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) — `@TransactionalEventListener` và transaction phases.

> Các code snippets nhằm minh họa cơ chế trong Hibernate ORM 6.x/Jakarta Persistence/Spring Data JPA. JPA callback timing, Hibernate SPI, Spring Data derived-delete execution, HQL extensions, database trigger syntax và native DML invalidation có thể khác giữa phiên bản/provider/dialect. Cần integration test trên stack thực tế; audit/business invariants không nên chỉ dựa vào một callback nếu tồn tại đường ghi ngoài entity lifecycle.




