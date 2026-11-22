# Giới hạn với bulk DML hoặc cập nhật trực tiếp ngoài cơ chế sự kiện

Hibernate Envers cung cấp chức năng lưu lịch sử (auditing) cho các entity được đánh dấu `@Audited`. Khi ứng dụng tạo, chỉnh sửa hoặc xóa entity bằng vòng đời persistence bình thường của Hibernate, Envers có thể ghi thêm các dòng lịch sử vào bảng audit và gắn chúng với một revision.

Tuy nhiên, có một giới hạn quan trọng: **Envers chủ yếu dựa trên các sự kiện entity của Hibernate, không phải trên mọi thay đổi dữ liệu xảy ra ở database**.

Vì vậy, những thao tác sau thường không tạo các revision Envers tương ứng với từng entity bị thay đổi:

- Bulk `UPDATE` và `DELETE` bằng HQL/JPQL.
- `CriteriaUpdate` và `CriteriaDelete` của Jakarta Persistence Criteria API.
- Spring Data JPA `@Modifying` thực thi bulk JPQL/native DML.
- Native SQL qua `EntityManager.createNativeQuery(...).executeUpdate()` hoặc Hibernate native query.
- JDBC trực tiếp, stored procedures, ETL, migration scripts và ứng dụng bên ngoài.
- Các cơ chế ghi không đi qua cùng hệ thống entity lifecycle events của Hibernate.

Khi một Product đổi giá từ 100 thành 130 bằng bulk SQL, bảng dữ liệu gốc có thể được cập nhật và transaction commit thành công, nhưng Envers **không biết để lưu trạng thái 130**. Nếu sau đó Product được chỉnh thành 140 bằng ORM thông thường, lịch sử có thể chỉ hiển thị 100 → 140. Việc thiếu revision này không thể được sửa bằng một câu truy vấn `AuditReader` thông minh hơn: dữ liệu về sự kiện ở giữa chưa từng được lưu.

Bài học thuộc chương **Lịch sử với Envers** của module *Data Persistence Relational Access ORM Hibernate*. Nội dung tập trung vào Hibernate ORM 6.x, Jakarta Persistence và Spring Data JPA, làm rõ giới hạn kỹ thuật, rủi ro về tính nhất quán, các phương án thay thế và cách kiểm thử hệ thống có yêu cầu audit đầy đủ.

## 1. Mô hình vận hành: Envers ghi lịch sử ở tầng nào?

Với entity được audit, Envers tích hợp vào hệ thống Hibernate event listeners. Khi Hibernate xử lý những thay đổi theo entity lifecycle, Envers nhận thông tin cần thiết để ghi revision và những cột được audit.

~~~mermaid
flowchart TD
    A["Service / repository"] --> B{"Đường ghi dữ liệu"}
    B --> C["persist / managed dirty checking / remove"]
    B --> D["HQL, JPQL, Criteria bulk DML"]
    B --> E["Native SQL, JDBC hoặc external SQL"]
    C --> F["Hibernate entity events"]
    F --> G["Envers listeners"]
    F --> H["ORM-generated SQL"]
    G --> I["REVINFO + bảng _AUD"]
    D --> J["Bulk SQL statements"]
    E --> K["Direct SQL statements"]
    H --> DB[("Bảng dữ liệu gốc")]
    J --> DB
    K --> DB
    I --> AUD[("Bảng lịch sử")]
~~~

Sơ đồ khái quát trên phân biệt rõ **đường thay đổi entity** với **đường thực thi SQL trực tiếp**. Cả hai có thể được thực thi qua Hibernate và cùng dùng Spring transaction, nhưng chúng không phát cùng loại sự kiện.

### 1.1. Envers không phải trigger trong database

Một database trigger có thể chạy khi bảng bị `INSERT`/`UPDATE`/`DELETE` bởi bất kỳ writer nào. Trong khi đó Envers nhận các sự kiện từ Hibernate ORM trong JVM. Bảng audit thường có tên `products_AUD` không tự theo dõi bảng `products` chỉ vì cả hai nằm trong cùng database.

~~~text
Managed entity update
    -> Hibernate update event
    -> Envers audit action + SQL update

Bulk UPDATE products
    -> SQL trực tiếp
    -> Không có per-entity Hibernate update event
    -> Không tự có Envers revision
~~~

### 1.2. Không nhầm SQL execution với entity event

Hibernate có thể tự chuyển HQL bulk query thành SQL, flush pending state trước query hoặc đồng bộ cache regions sau mutation. **Những việc đó không biến bulk query thành một vòng lặp cập nhật từng managed entity.**

Envers cần event phù hợp, entity identity và audited state. Một câu bulk UPDATE có thể ảnh hưởng hàng triệu rows mà Hibernate không tải từng row lên Java để tạo thông tin audit.

## 2. Cấu hình một entity được Envers audit

Ví dụ Product:

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import org.hibernate.envers.Audited;
import java.math.BigDecimal;

@Entity
@Audited
@Table(name = "products")
public class Product {

    @Id
    private Long id;

    @Column(name = "name", nullable = false)
    private String name;

    @Column(name = "price", nullable = false,
            precision = 12, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private ProductStatus status;

    @Version
    private long version;

    protected Product() {}

    public Long getId() {
        return id;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid price");
        }
        this.price = newPrice;
    }
}
~~~

~~~java
package com.example.catalog;

public enum ProductStatus {
    DRAFT, ACTIVE, ARCHIVED
}
~~~

Mỗi `public` type được đặt trong file Java riêng. Ví dụ giả định mã tạo entity và schema tương ứng đã có trong project.

### 2.1. Dependency Hibernate Envers

Với Hibernate ORM 6.x, Envers thường được tích hợp qua module `hibernate-envers` cùng phiên bản với `hibernate-core`:

~~~xml
<dependency>
    <groupId>org.hibernate.orm</groupId>
    <artifactId>hibernate-core</artifactId>
    <version>6.6.0.Final</version>
</dependency>

<dependency>
    <groupId>org.hibernate.orm</groupId>
    <artifactId>hibernate-envers</artifactId>
    <version>6.6.0.Final</version>
</dependency>
~~~

Version chỉ mang tính minh họa. Trong Spring Boot nên tuân theo dependency management/BOM phù hợp và không tự trộn các bản Hibernate khác nhau.

Envers cần được bootstrap/tích hợp đúng và entity có mapping audit phù hợp. Tuy nhiên, **thêm dependency cùng `@Audited` không làm bulk DML được audit tự động**.

### 2.2. Những bảng audit thường có

Theo convention mặc định, một mô hình có thể gồm:

~~~text
products
  id | name | price | status | version

REVINFO
  REV | REVTSTMP

products_AUD
  id | REV | REVTYPE | name | price | status | ...
~~~

Tên bảng/cột phụ thuộc Envers configuration, naming strategy và audit strategy. Một số thuộc tính có thể không được audit; đặc biệt optimistic-locking field `@Version` thường có chính sách không đưa vào audit theo cấu hình Envers mặc định. Không suy luận rằng `_AUD` là bản sao y nguyên tất cả cột của bảng gốc.

### 2.3. Các loại revision

Envers dùng những loại thay đổi như:

| Loại | Ý nghĩa |
| --- | --- |
| `RevisionType.ADD` | Entity được tạo |
| `RevisionType.MOD` | Entity được chỉnh sửa |
| `RevisionType.DEL` | Entity bị xóa |

Một transaction có nhiều audited changes thường chia sẻ revision metadata tương ứng cho nhóm thay đổi đã được ghi nhận trong transaction. Revision number là mã định danh của lịch sử được ghi, không phải đồng hồ liên tục theo từng entity; ID có thể bị gián đoạn do entities khác, rollback hoặc cách cấp định danh.

## 3. Đường cập nhật managed entity bình thường

Ví dụ service:

~~~java
@Service
public class ProductService {

    private final EntityManager em;

    public ProductService(EntityManager em) {
        this.em = em;
    }

    @Transactional
    public void changePrice(Long productId, BigDecimal newPrice) {
        Product product = em.find(Product.class, productId);

        if (product == null) {
            throw new EntityNotFoundException("Product not found");
        }

        product.changePrice(newPrice);
    }
}
~~~

Khi transaction flush:

1. Hibernate biết Product ID và trạng thái đang managed.
2. Dirty checking xác định thay đổi có cần SQL UPDATE không.
3. Hệ thống entity lifecycle events xử lý update action.
4. Envers listener nhận audited entity change.
5. Audit row được ghi theo revision metadata.
6. Database SQL UPDATE và audit DML nằm trong transaction theo tích hợp thông thường.

~~~mermaid
sequenceDiagram
    participant S as Service
    participant H as Hibernate
    participant E as Envers
    participant DB as Database
    S->>H: find(Product, 42)
    H->>DB: SELECT products
    DB-->>H: Product managed
    S->>H: changePrice(120)
    S->>H: flush / commit
    H->>E: Update event
    E->>DB: Ghi audit revision
    H->>DB: UPDATE products
    Note over H,DB: Thứ tự statements thực tế tùy Hibernate action queue
    H->>DB: COMMIT
~~~

Không nên suy ra `product.changePrice(...)` tạo revision ngay tức thì. Nếu giá không đổi, transaction rollback, hoặc ORM không phát update action, revision tương ứng có thể không được tạo.

### 3.1. Transaction rollback

Trong cấu hình thông thường, Envers audit DML nằm trong cùng database transaction với những thay đổi ORM tương ứng. Khi transaction rollback, data DML và audit DML trong transaction cũng rollback. Sequence revision IDs có thể vẫn có khoảng trống theo cơ chế cấp số; không dùng khoảng trống ID như bằng chứng thiếu entity audit.

## 4. Bulk HQL/JPQL UPDATE: thay đổi DB nhưng không có Envers MOD

Ví dụ tăng giá mọi Product ACTIVE:

~~~java
@Transactional
public int increaseActivePrices(BigDecimal factor) {
    return em.createQuery(
            """
            update Product p
            set p.price = p.price * :factor
            where p.status = :status
            """
        )
        .setParameter("factor", factor)
        .setParameter("status", ProductStatus.ACTIVE)
        .executeUpdate();
}
~~~

Đây là bulk mutation. Hibernate có thể biến HQL thành một hoặc nhiều SQL statements tùy inheritance mapping và Dialect, nhưng nó **không tải từng Product vào Persistence Context để gọi dirty checking, `@PreUpdate` và Envers listeners**.

Nếu câu query cập nhật 5.000 Products, kết quả `executeUpdate()` có thể báo số affected entities/rows theo semantics của provider, nhưng Envers **không tự tạo 5.000 audit rows**.

### 4.1. Hai đường thực thi khác nhau

~~~text
Đường managed:
    SELECT Product
      -> Persistence Context
      -> thay đổi field
      -> ORM update action
      -> Envers MOD
      -> SQL UPDATE

Đường bulk:
    HQL UPDATE
      -> SQL mutation plan
      -> SQL UPDATE nhiều rows
      -> không có từng Product update action
      -> không có Envers MOD theo từng row
~~~

Hình dạng SQL cuối cùng không xác định rằng Envers đã chạy hay chưa. Một câu UPDATE phát ra từ Hibernate có thể thuộc đường managed hoặc bulk.

### 4.2. Không thể sửa bằng một query hint

Một `@Audited` annotation, query hint hoặc cấu hình SQL logging không tự thêm việc materialize mỗi affected Product và ghi audited state. Nếu nghiệp vụ bắt buộc lịch sử theo từng entity, cần thay đổi **chiến lược ghi dữ liệu**.

## 5. CriteriaUpdate và CriteriaDelete không phải managed entity updates

Criteria API mang lại khả năng dựng query có kiểu nhưng **không thay đổi semantics của bulk DML**.

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<Product> update =
        cb.createCriteriaUpdate(Product.class);

Root<Product> product = update.from(Product.class);

update.set("price", new BigDecimal("199.00"));
update.where(
        cb.equal(
                product.get("status"),
                ProductStatus.ACTIVE
        )
);

int changed = em.createQuery(update).executeUpdate();
~~~

Mặc dù gọi `createCriteriaUpdate(Product.class)`, lệnh này không tạo managed Product cho từng row. Nó không kích hoạt Envers `MOD` cho từng Product bị cập nhật.

Tương tự:

~~~java
CriteriaDelete<Product> delete =
        cb.createCriteriaDelete(Product.class);

Root<Product> root = delete.from(Product.class);

delete.where(
        cb.equal(
                root.get("status"),
                ProductStatus.ARCHIVED
        )
);

int deleted = em.createQuery(delete).executeUpdate();
~~~

Đây là bulk DELETE, không phải vòng lặp `em.remove(product)`.

### 5.1. So sánh API

| Thao tác | Đi qua entity lifecycle events? | Envers per-entity revisions? |
| --- | --- | --- |
| `em.persist(entity)` | Có theo lifecycle | Có thể có khi `@Audited` |
| Managed entity thay đổi rồi flush | Có khi thực sự UPDATE | Có thể có |
| `em.remove(entity)` | Có theo lifecycle | Có thể có |
| HQL/JPQL bulk UPDATE | Không cho từng row | **Không** |
| HQL/JPQL bulk DELETE | Không cho từng row | **Không** |
| `CriteriaUpdate`/`CriteriaDelete` | Không cho từng row | **Không** |
| SQL native/JDBC | Không tạo event entity tương ứng | **Không** |

“Có thể” ở các thao tác managed còn phụ thuộc mapping, change detection, event registration, flush và transaction commit.

## 6. Bulk DELETE còn làm thiếu dấu vết xóa

Ví dụ:

~~~java
@Transactional
public int purgeArchived() {
    return em.createQuery(
            "delete from Product p where p.status = :status"
        )
        .setParameter("status", ProductStatus.ARCHIVED)
        .executeUpdate();
}
~~~

Sau commit, database có thể không còn các rows đó. Nhưng Envers không tự ghi `RevisionType.DEL` cho từng Product đã bị bulk delete.

Hậu quả:

- `AuditReader` có thể không có một deletion event thích hợp.
- Timeline lịch sử không giải thích vì sao entity biến mất.
- Một phép truy vấn trạng thái lịch sử theo revision sau thời điểm direct delete có thể tiếp tục dựa trên audit row cũ, gây ấn tượng entity còn tồn tại.
- Không thể biết actor thực hiện deletion từ Envers nếu không có nguồn audit khác.

### 6.1. ORM cascade và callbacks cũng bị bỏ qua

Bulk DELETE không tương đương gọi `em.remove` cho từng entity:

- `CascadeType.REMOVE` và `orphanRemoval` không chạy theo từng entity như managed removal.
- `@PreRemove`/`@PostRemove` không chạy cho từng affected entity.
- Bean Validation pre-remove groups, nếu cấu hình, không được chạy theo từng entity.
- Envers không tạo những audit delete events tương ứng.

Nếu DB có `ON DELETE CASCADE`, database có thể xóa các child rows, nhưng điều đó **không tạo Envers DEL revisions cho các child entities**.

Đồng thời, nếu FK chặn xóa, bulk DELETE có thể thất bại; database constraints vẫn được enforce.

## 7. Native SQL qua EntityManager vẫn nằm ngoài Envers entity events

Một câu SQL trực tiếp:

~~~java
@Transactional
public int updatePriceNative(
        Long productId,
        BigDecimal newPrice
) {
    return em.createNativeQuery(
            """
            update products
            set price = :price
            where id = :id
            """
        )
        .setParameter("price", newPrice)
        .setParameter("id", productId)
        .executeUpdate();
}
~~~

Dù SQL được chạy qua `EntityManager` và trong `@Transactional`, nó không phải một managed entity UPDATE. Không có lý do để Envers tự tạo MOD revision cho Product tương ứng.

Tương tự với Hibernate Session mutation API:

~~~java
Session session = em.unwrap(Session.class);

int changed = session.createMutationQuery(
        "update Product p set p.price = :newPrice where p.id = :id"
    )
    .setParameter("newPrice", newPrice)
    .setParameter("id", productId)
    .executeUpdate();
~~~

và với Spring JDBC:

~~~java
jdbcTemplate.update(
        "update products set price = ? where id = ?",
        newPrice,
        productId
);
~~~

**Điểm quyết định không phải tên API `EntityManager` hay `Session`, mà là có đi qua event-driven entity lifecycle của Hibernate hay không.**

### 7.1. Transactional SQL không đồng nghĩa transactional audit

Native SQL vẫn có thể commit hoặc rollback cùng database transaction. Nhưng nếu Envers không được gọi, không có audit row nào để rollback hay commit.

- **Atomicity:** một tập SQL operations cùng commit/rollback.
- **Audit completeness:** mọi thay đổi cần theo dõi đều có bản ghi lịch sử.

Hai thuộc tính khác nhau. Có atomicity không có nghĩa tự động có audit completeness.

## 8. Spring Data JPA @Modifying: flush/clear không tạo revision

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query("""
        update Product p
        set p.price = p.price * :factor
        where p.status = :status
        """)
    int increasePrices(
            @Param("status") ProductStatus status,
            @Param("factor") BigDecimal factor
    );
}
~~~

Với câu lệnh này:

- `@Modifying` cho biết đây là một modifying query.
- `flushAutomatically=true` giúp flush những thay đổi pending trước khi chạy bulk SQL theo cơ chế Spring Data.
- `clearAutomatically=true` clear managed state sau query để tránh một số giá trị cũ trong L1.
- **Không có flag nào chuyển bulk UPDATE thành audited entity events.**

Một repository xóa bằng:

~~~java
@Modifying
@Query("delete from Product p where p.status = :status")
int deleteByStatus(
        @Param("status") ProductStatus status
);
~~~

cũng là bulk delete. Cần phân biệt nó với code load entities rồi gọi `delete(entity)`/`remove(entity)` trong cùng transaction. Một số repository method được Spring Data diễn giải thành entity-by-entity operations trong những tình huống nhất định, trong khi JPQL @Modifying delete như trên rõ ràng là bulk. **Đừng suy đoán audit semantics chỉ từ tên repository method; phải biết execution path.**

## 9. Các tác nhân ngoài Hibernate không có Envers listener

Ví dụ DBA chạy:

~~~sql
update products
set price = 170.00
where id = 42;
~~~

Hoặc một ETL process chạy:

~~~sql
delete from products
where status = 'ARCHIVED';
~~~

Envers trong JVM ứng dụng không nhận được những per-entity change events này. Các nguồn thay đổi cần chú ý:

- Database administration scripts.
- Stored procedures.
- Triggers thay đổi các bảng khác.
- Import jobs dùng JDBC hoặc driver native.
- Flyway/Liquibase data migrations.
- Legacy application cùng kết nối DB.
- Microservices dùng database chung.
- Custom batch loaders.

Envers không tự biết actor, reason hoặc old/new values của những lệnh này. Nếu hệ thống cần audit từ tất cả writers, nên xem xét cơ chế quan sát ở database như trigger/CDC, hoặc buộc mọi writer đi qua một API/audit boundary chung.

## 10. Ví dụ thời gian: khoảng trống giữa hai revisions

Giả sử Product ID 42 trải qua ba bước:

| Thời điểm | Operation | Giá thật sau commit | Envers record |
| --- | --- | ---: | --- |
| T1 | `em.persist(product)` | 100 | REV 10, ADD, price 100 |
| T2 | Bulk HQL UPDATE | 130 | **Không có MOD revision** |
| T3 | Managed entity UPDATE | 140 | REV 12, MOD, price 140 |

REV 10 và REV 12 là các mã giả định để minh họa, không bắt buộc liên tiếp.

### 10.1. Lịch sử Envers nhìn thấy

~~~text
REV 10: Product 42, price=100
REV 12: Product 42, price=140
~~~

Giá 130 từng tồn tại ở database sau T2 nhưng **không có trong audit timeline**. Nếu một tính năng UI hiển thị “giá thay đổi từ 100 sang 140”, kết luận đó bỏ qua bước thay đổi giá thành 130.

### 10.2. Trường hợp bulk DELETE

~~~text
T1: Managed INSERT Product 42 -> Envers ADD
T2: Bulk DELETE Product 42 -> database không còn row
T3: Không có Envers DEL event cho bulk DELETE
~~~

Một AuditReader lookup tại revision phù hợp về sau có thể vẫn dựa vào audited state trước khi xóa, vì không có DEL revision để chấm dứt lịch sử entity theo mô hình Envers. Đây là tình huống đặc biệt nguy hiểm khi ứng dụng cần chứng minh “ai xóa record”.

### 10.3. Sửa sau đó không khôi phục lịch sử bị mất

Nếu direct SQL thay giá 100 → 130 → 110, sau đó managed update thành 140, Envers không thể tự suy ra các giá trị 130 và 110 từng tồn tại. Revision mới chỉ phản ánh sự kiện được quan sát tại thời điểm mới.

**Một transition không được ghi lúc xảy ra thường không thể tái tạo trung thực từ state cuối cùng.**

## 11. Đọc audit bằng AuditReader

Envers cung cấp `AuditReader`:

~~~java
import org.hibernate.envers.AuditReader;
import org.hibernate.envers.AuditReaderFactory;

AuditReader reader =
        AuditReaderFactory.get(entityManager);

List<Number> revisions =
        reader.getRevisions(Product.class, 42L);

for (Number revision : revisions) {
    Product snapshot =
            reader.find(Product.class, 42L, revision);

    System.out.println(
            "REV=" + revision +
            ", price=" + snapshot.getPrice()
    );
}
~~~

Nếu Product đi qua kịch bản phần trước, revision list chỉ có những audited changes mà Envers đã nhận. Nó không tự xuất hiện revision cho bulk UPDATE.

### 11.1. AuditReader as-of không phải truy vấn database live state

~~~java
Product current =
        entityManager.find(Product.class, 42L);

Product historical =
        reader.find(Product.class, 42L, revisionNumber);
~~~

`current` là entity state theo persistence context/database hiện tại; `historical` được dựng từ audit rows theo revision semantics. Nếu có direct SQL không được audit, hai kết quả có thể khác nhau một cách hợp lệ về cơ chế nhưng **không đáp ứng lời hứa lịch sử đầy đủ** của ứng dụng.

`reader.find(...)` với revision không có thay đổi của Product thường dựa vào audit record phù hợp gần nhất ở hoặc trước revision ấy (và các deletion markers nếu có). Nó không tự hỏi database hiện tại rằng “liệu có một SQL update nào chưa được audit giữa hai revisions?”.

## 12. Bulk DML làm managed entities trong L1 bị stale

Một lỗi khác có thể xuất hiện ngay trong cùng transaction:

~~~java
@Transactional
public void mixedOperation(Long id) {
    Product product = em.find(Product.class, id);

    BigDecimal before = product.getPrice();

    em.createQuery(
            "update Product p set p.price = :price where p.id = :id"
        )
        .setParameter("price", new BigDecimal("150.00"))
        .setParameter("id", id)
        .executeUpdate();

    BigDecimal after = product.getPrice();

    // after có thể vẫn bằng before:
    // bulk SQL không cập nhật tự động object managed.
}
~~~

Persistence Context L1 giữ instance Product và loaded snapshot trước bulk query. SQL cập nhật database nhưng không tự cập nhật Java object managed.

Nếu sau đó code tiếp tục sửa Product trong cùng context, Hibernate có thể phát UPDATE từ state cũ, dẫn đến lost update hoặc optimistic locking conflict tùy mapping/versioning.

### 12.1. Flush trước, clear sau khi thật sự cần bulk

~~~java
@Transactional
public int runBulkAndClear(BigDecimal newPrice) {
    em.flush();

    int changed = em.createQuery(
            "update Product p set p.price = :price " +
            "where p.status = :status"
        )
        .setParameter("price", newPrice)
        .setParameter("status", ProductStatus.ACTIVE)
        .executeUpdate();

    em.clear();

    return changed;
}
~~~

- `flush()` đồng bộ pending managed changes trước bulk statement.
- Bulk mutation cập nhật database.
- `clear()` detach managed entities để các lần load kế tiếp không dùng L1 state cũ.

Nhưng **không có bước nào tự tạo Envers audit rows cho bulk mutation**. Flush có thể audit các managed updates xảy ra trước đó, không biến SQL bulk thành per-entity events.

### 12.2. Refresh không khôi phục revision

~~~java
em.refresh(product);
~~~

`refresh` đọc lại state của managed object theo persistence semantics. Nó không ghi lại những transitions đã xảy ra ngoài Envers. Đồng thời refresh có thể ghi đè những thay đổi local chưa flush, nên không dùng mù quáng.

## 13. @Version và bulk update là vấn đề riêng

Entity:

~~~java
@Version
private long version;
~~~

Managed entity updates thường dùng optimistic locking để kiểm tra version cũ trước khi ghi. Bulk JPQL/HQL UPDATE thông thường **không thực thi optimistic version check như từng managed entity update**.

~~~java
em.createQuery(
        "update Product p set p.price = :price " +
        "where p.status = :status"
    )
    .setParameter("price", newPrice)
    .setParameter("status", ProductStatus.ACTIVE)
    .executeUpdate();
~~~

Lệnh này không tự mang cùng version predicate/check cho từng Product. Có thể làm L1 state cũ và version column không nhất quán với kỳ vọng application.

### 13.1. Hibernate HQL update versioned

Hibernate có extension HQL:

~~~java
em.createQuery(
        """
        update versioned Product p
        set p.price = :price
        where p.status = :status
        """
    )
    .setParameter("price", newPrice)
    .setParameter("status", ProductStatus.ACTIVE)
    .executeUpdate();
~~~

Cơ chế này yêu cầu tăng version khi bulk UPDATE theo khả năng Hibernate/version mapping; nó không phải JPQL chuẩn. Dù có version increment, nó **không phát Envers MOD entity events** cho từng affected row.

### 13.2. Native SQL với expected version

~~~sql
update products
set price = :newPrice,
    version = version + 1
where id = :id
  and version = :expectedVersion;
~~~

Kiểm tra affected row count = 1 để xác nhận version chưa đổi. Đây là một optimistic concurrency technique cho direct SQL, **không phải audit history mechanism**.

Tóm lại:

- **Optimistic versioning** kiểm soát một số xung đột ghi đồng thời.
- **Envers auditing** ghi lịch sử thay đổi entity.
- Một bulk mutation có thể thực hiện versioning mà vẫn không có Envers revision.

## 14. Những tính năng ORM khác cũng bị bulk DML bỏ qua

| Cơ chế | Đường managed entity | Bulk/native DML |
| --- | --- | --- |
| Dirty checking | Có | Không theo từng row |
| `@PreUpdate`/`@PostUpdate` | Theo lifecycle | Không cho từng row |
| `@PreRemove`/`@PostRemove` | Theo lifecycle | Không cho từng row |
| Envers listeners | Có với audited events | Không cho từng row |
| Jakarta Bean Validation lifecycle | Theo events được cấu hình | Không validate từng entity |
| `CascadeType.REMOVE`/`orphanRemoval` | Theo mapped removal | Không tự chạy như managed removal |
| `@Version` optimistic checks | Theo ORM managed updates | Cần tự xử lý/extension |
| L1 managed state | Theo dõi changes | Có thể stale |
| Database FK/UNIQUE/CHECK | Vẫn có | **Vẫn có** |
| DB transaction rollback | Vẫn có | **Vẫn có** nếu cùng transaction |
| Query/L2 cache invalidation | Theo ORM machinery | Có thể có tùy mutation/synchronization |
| Envers revision cho mỗi row | Khi event tương ứng được audit | **Không tự có** |

Không nhầm việc database constraints và transaction vẫn hoạt động với việc callback/Envers cũng được gọi. Những tính năng này nằm ở các tầng khác nhau.

### 14.1. Database constraint không tự tạo revision

Một `CHECK(price >= 0)` có thể chặn bulk update ghi giá âm. Nhưng nếu bulk update thay 100 thành 130 hợp lệ, database không có lý do tự ghi Envers revision chỉ vì đã kiểm tra constraint thành công.

## 15. Cache invalidation cũng không biến bulk SQL thành audited events

Hibernate có thể tự động đồng bộ hoặc invalidate một số vùng L2/query cache quanh HQL bulk mutations. Native SQL có thể cần mô tả query spaces/synchronization trong một số API.

Dù cache state được cập nhật đúng, Envers vẫn có thể thiếu revision.

- Cache invalidation trả lời: “dữ liệu được cache có còn hợp lệ không?”
- Audit event trả lời: “đã có thay đổi nào với entity nào, ở revision nào?”
- SQL execution trả lời: “database đã chạy statement nào?”

Không dùng cache-hit/miss metrics hoặc SQL logs như bằng chứng trực tiếp về audit completeness.

## 16. StatelessSession và các đường ghi tối ưu throughput

Trong Hibernate 6.x, `StatelessSession` cung cấp cách thao tác dữ liệu không dùng persistence context/dirty checking như stateful `Session` thông thường. Nó không có cùng entity event model cho mọi operation.

Nếu ứng dụng dùng `StatelessSession` để import hoặc bulk update hiệu năng cao, **không mặc định Envers sẽ ghi revisions giống managed entity update**. Cần kiểm chứng version/framework integration cụ thể hoặc thiết kế audit độc lập.

Nguyên tắc rộng hơn: bất kỳ API nào bỏ qua entity lifecycle để đạt throughput cao đều phải được đánh giá lại nếu nghiệp vụ phụ thuộc Envers listeners.

## 17. Cách 1 — thay đổi từng managed entity để giữ Envers history

Nếu nghiệp vụ yêu cầu lịch sử Product theo Envers `AuditReader`, cách rõ ràng nhất là cập nhật qua managed entities.

~~~java
@Transactional
public int increasePricesWithEnvers(BigDecimal factor) {
    List<Product> products = em.createQuery(
            "select p from Product p where p.status = :status",
            Product.class
        )
        .setParameter("status", ProductStatus.ACTIVE)
        .getResultList();

    int changed = 0;

    for (Product product : products) {
        BigDecimal adjusted = product.getPrice()
                .multiply(factor)
                .setScale(2, RoundingMode.HALF_UP);

        product.changePrice(adjusted);
        changed++;
    }

    return changed;
}
~~~

Đoạn này dùng `java.math.RoundingMode`. Quy tắc làm tròn tiền tệ phải phù hợp domain thực tế, không tự chọn HALF_UP cho mọi bài toán.

Với đường managed update:

- Hibernate biết entity identity/state.
- Dirty checking, @Version và callbacks có cơ hội hoạt động.
- Envers có thể tạo MOD history cho mỗi entity thật sự được cập nhật.
- Entity DML và audit DML được phối hợp trong transaction.

### 17.1. Chi phí phải chấp nhận

So với một câu bulk UPDATE, cách này có thể:

- Load nhiều entity rows vào Java.
- Tốn RAM và persistence context tracking.
- Phát nhiều UPDATE statements.
- Phát thêm audit INSERT statements.
- Tăng transaction duration và lock contention.
- Chạm vấn đề N+1 nếu truy cập associations.

Đây là đánh đổi thực tế giữa tốc độ bulk SQL và yêu cầu lịch sử per-entity.

### 17.2. JDBC batching hỗ trợ một phần

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_updates=true
hibernate.order_inserts=true
~~~

Batching có thể giảm JDBC round trips cho những statements tương thích, nhưng không biến managed entity updates thành một HQL bulk statement. Envers vẫn thực hiện auditing theo events.

Hiệu quả tùy identifier generation, driver, Dialect, ordering và cache/flush strategy. Cần đo thực tế thay vì hứa rằng batching loại bỏ hết chi phí auditing.

### 17.3. Phân lô để tránh Session quá lớn

Với nhiều Product, có thể:

1. Chọn IDs theo keyset/cursor.
2. Load một tập entity giới hạn.
3. Thay đổi managed state.
4. Flush/clear sau batch phù hợp.
5. Tiếp tục batch tiếp theo.

Một transaction rất lớn có thể giữ quá nhiều objects và locks; nhiều transactions nhỏ làm operation tổng thể không còn all-or-nothing. Phải chọn chunk boundaries theo nghiệp vụ. Không tự commit từng batch nếu hợp đồng yêu cầu toàn bộ thay đổi atomic.

### 17.4. Flush không phải commit

Sau:

~~~java
em.flush();
em.clear();
~~~

audit INSERTs đã flush vẫn có thể rollback khi transaction thất bại. Không coi sự xuất hiện của SQL audit trong log là bằng chứng revision đã được commit.

## 18. Cách 2 — giữ bulk DML nhưng tạo lịch sử tường minh

Với hàng triệu rows, update từng entity có thể quá tốn kém. Một giải pháp khác là sử dụng bulk SQL và thiết kế **bảng audit nghiệp vụ riêng** được ghi atomically trong cùng database transaction.

Ví dụ:

~~~sql
create table product_price_change_log (
    id bigint generated by default as identity primary key,
    operation_id varchar(100) not null,
    product_id bigint not null,
    old_price numeric(12,2) not null,
    new_price numeric(12,2) not null,
    changed_by varchar(120) not null,
    changed_at timestamp not null
);
~~~

Bảng này **không phải Envers products_AUD**. Nó có contract riêng về actor, before/after values và operation ID.

### 18.1. Một transaction làm dữ liệu và audit cùng commit

~~~text
BEGIN TRANSACTION
  1. Xác định chính xác tập rows cần sửa.
  2. Khóa/kiểm soát concurrency theo DBMS.
  3. Lưu old values và IDs của tập đó.
  4. UPDATE đúng những IDs đã xác định.
  5. Ghi audit rows chứa old/new, actor, operation ID.
  6. Kiểm tra row counts và dữ liệu audit phù hợp.
COMMIT

Nếu lỗi:
  ROLLBACK cả database DML và audit DML.
~~~

Đối với transaction có điều kiện phức tạp, dùng stable affected-set (bảng staging/temporary table hoặc cơ chế tương đương) để tránh việc câu SELECT lưu snapshot và câu UPDATE tính toán lại predicate trên một tập rows khác.

### 18.2. Ví dụ một row với optimistic version

SQL minh họa ở DBMS hỗ trợ `FOR UPDATE`:

~~~sql
begin;

select price, version
from products
where id = :id
for update;

-- Ứng dụng lấy old_price và expected_version từ row đã khóa.

update products
set price = :new_price,
    version = version + 1
where id = :id
  and version = :expected_version;

-- Chỉ tiếp tục nếu affected row count đúng 1.

insert into product_price_change_log (
    operation_id, product_id, old_price,
    new_price, changed_by, changed_at
) values (
    :operation_id, :id, :old_price,
    :new_price, :actor, current_timestamp
);

commit;
~~~

Các giá trị old_price/version phải lấy từ snapshot đáng tin cậy trong **cùng transaction**, không lấy tùy ý từ HTTP request. Đây là ví dụ audit table riêng, không phải cơ chế sinh Envers revisions.

### 18.3. Vì sao copy cùng WHERE chưa chắc đủ?

Giả sử:

~~~sql
insert into product_price_change_log (...)
select ...
from products
where status = 'ACTIVE';

update products
set price = price * :factor
where status = 'ACTIVE';
~~~

Ở `READ COMMITTED` với concurrent writers, tập Product ACTIVE có thể thay đổi giữa hai câu SQL. Một Product vừa được insert hoặc đổi status có thể được UPDATE nhưng không có trong audit snapshot, hoặc ngược lại.

Một giải pháp đúng phải xác định ổn định affected IDs, có locking/isolation phù hợp và thực hiện UPDATE **đúng tập** đã ghi snapshot. Có thể dùng SQL DBMS-specific như CTE, temp tables hoặc câu mutation trả affected rows/values, nhưng cần xác minh cú pháp, concurrency semantics và rollback trên DBMS production.

### 18.4. Hai hệ lịch sử không tự hợp nhất

Nếu managed updates được ghi vào `products_AUD` còn bulk updates vào `product_price_change_log`, ứng dụng có hai nguồn history. Một UI cần timeline thống nhất phải có chiến lược hợp nhất, sắp xếp, correlation IDs và semantics tương thích. Không gọi mọi event trong custom log là “Envers revision”.

## 19. Vì sao không nên INSERT thẳng vào products_AUD?

Một giải pháp tưởng đơn giản:

~~~sql
-- KHÔNG dùng như một giải pháp audit production không qua kiểm chứng.
insert into products_AUD (id, REV, REVTYPE, price, ...)
values (...);
~~~

Rủi ro vì Envers quản lý nhiều thứ hơn một row history:

- Revision metadata và sequence/identifier allocation.
- Revision type ADD/MOD/DEL.
- Audit fields và relationship mappings.
- Custom revision entity/listeners chứa actor.
- Modified flags nếu bật.
- Audit primary keys và foreign keys.
- Default/Validity audit strategy.
- Hiệu lực của các audit rows theo revision.
- Nhiều audited entities thay đổi trong một transaction.

### 19.1. DefaultAuditStrategy

Envers thường truy vấn trạng thái tại revision bằng audit row gần nhất phù hợp. Nếu INSERT một row sai revision hoặc thiếu field, kết quả “as-of revision” có thể trả state sai hoặc không còn phù hợp với entity mapping.

### 19.2. ValidityAuditStrategy

Với `ValidityAuditStrategy`, Envers có thể quản lý thông tin điểm bắt đầu và kết thúc hiệu lực revision, ví dụ một cột `REVEND` tùy cấu hình. Khi tạo revision mới, dữ liệu hiệu lực của revision cũ có thể phải được cập nhật.

Nếu chỉ INSERT một audit row mới mà không cập nhật end revision của row trước, các khoảng hiệu lực có thể bị chồng lấp hoặc hỏng. Các queries của Envers sẽ không còn diễn giải timeline chính xác.

### 19.3. Custom revision metadata

Ví dụ:

~~~java
@RevisionEntity(MyRevisionListener.class)
public class MyRevisionEntity {
    // Revision fields và metadata.
}
~~~

Custom listener có thể lưu actor từ security context của application. Một SQL script ngoài JVM không có listener context ấy và không thể tự biết actor nghiệp vụ.

**Nếu buộc phải tích hợp direct SQL với Envers schema, đó phải là một integration được thiết kế và kiểm thử theo implementation/version cụ thể**, không phải một INSERT vá lỗi. Thông thường audit table riêng, trigger hoặc CDC có hợp đồng rõ ràng dễ vận hành hơn.

## 20. Cách 3 — database triggers để quan sát mọi DML

Khi có nhiều writers cùng sửa một bảng, database trigger có thể ghi audit bất kể lệnh đến từ Hibernate hay JDBC:

~~~mermaid
flowchart TD
    W1["Hibernate managed/bulk"] --> DB[("products")]
    W2["JDBC hoặc legacy app"] --> DB
    W3["DBA scripts"] --> DB
    DB --> TR["Database trigger"]
    TR --> H[("History table do DB quản lý")]
~~~

Nếu trigger ghi trong cùng database transaction, khi transaction rollback, history write cũng rollback theo DB semantics.

**Ưu điểm:** bao phủ nhiều write paths hơn Envers; có thể ghi OLD/NEW row values tại DB layer.

**Giới hạn:**

- Cú pháp và behavior phụ thuộc DBMS.
- Mọi row update có thể tăng write latency.
- Actor ứng dụng không tự có trong DB session.
- Connection pool có thể làm session context rò rỉ nếu không reset.
- Triggers phải được version hóa và kiểm thử.
- Có thể gây recursion, locking hoặc maintenance complexity.
- Không tự tạo Envers-compatible revision history.

Nếu Envers và trigger cùng ghi hai hệ lịch sử, một managed update có thể xuất hiện ở cả hai. Cần quy tắc deduplication và source-of-truth nếu nghiệp vụ muốn kết quả thống nhất.

### 20.1. Actor và correlation ID

Để biết ai sửa, database user dùng chung cho cả ứng dụng thường không đủ. Có thể truyền một trusted actor/operation ID vào DB transaction context theo cơ chế DBMS, nhưng phải:

- Lấy actor từ authenticated server context.
- Không nhận raw actor tùy ý từ client.
- Reset session variables khi trả JDBC connection về pool.
- Đặt policy riêng cho background jobs và DBA actions.

## 21. Cách 4 — Change Data Capture (CDC)

CDC quan sát database transaction log (ví dụ PostgreSQL WAL hoặc MySQL binlog) để sinh change events.

~~~mermaid
flowchart LR
    A["ORM/JDBC/SQL writers"] --> DB[("Database")]
    DB --> LOG["WAL / binlog / change log"]
    LOG --> CDC["CDC connector"]
    CDC --> STREAM["Change event stream"]
    STREAM --> AUDIT["Audit processing"]
~~~

CDC có thể quan sát những committed row changes dù writer không dùng Hibernate Envers.

**Tuy nhiên CDC không đồng nghĩa Envers:**

- Thường bất đồng bộ và có độ trễ.
- Một raw change event không mặc định chứa business reason/actor.
- Có thể cần snapshot/backfill cho dữ liệu trước khi bật CDC.
- Event delivery cần xử lý duplicate/retry.
- Schema evolution và connector downtime cần quản lý.
- Không tự ghi `REVINFO`/`_AUD` theo Envers semantics.
- Nếu log retention không đủ trong outage, có nguy cơ thiếu events.

CDC phù hợp khi yêu cầu là **capture mọi database changes**, không chỉ những entity events trong một JVM.

## 22. Cách 5 — transactional outbox và domain audit events

Đối với audit ở cấp nghiệp vụ, có thể ghi event cùng transaction dữ liệu:

~~~text
Transaction:
    UPDATE products theo use case
    INSERT outbox(event_id, actor, reason, affected_ids, payload)
    COMMIT

Sau commit:
    Publisher/CDC đọc outbox
    Consumer idempotent lưu audit event
~~~

Lợi ích là event có thể diễn đạt lý do: “áp dụng campaign giảm giá”, “phê duyệt điều chỉnh tồn kho”, “backfill dữ liệu”.

Nhưng một event chỉ ghi:

~~~json
{
  "operation": "PRICE_INCREASE",
  "factor": 1.1,
  "affectedCount": 5000
}
~~~

không đủ để tái tạo **before/after price của từng Product** nếu đó là yêu cầu. Nếu cần per-row history, outbox/audit payload hoặc một bảng staging phải lưu những thông tin đó.

Outbox cũng không tự capture SQL được DBA chạy bên ngoài ứng dụng. Nó chỉ bao phủ những write paths được lập trình để ghi outbox events.

## 23. Chọn giải pháp theo yêu cầu

| Yêu cầu | Chiến lược phù hợp | Rủi ro phải kiểm soát |
| --- | --- | --- |
| Envers `AuditReader` phải cho lịch sử entity đầy đủ | Managed entity operations | Performance, large sessions, transaction size |
| Vài trăm/thousands entities cần Envers per-row revision | Managed updates + batching/chunking | Memory và commit boundaries |
| Hàng triệu rows, cần before/after từng row | Bulk SQL + transactional audit log | Concurrency, stable IDs, atomicity |
| Bất kỳ writer nào vào DB cũng phải được audit | DB trigger hoặc CDC | Actor, schema, latency, cluster operations |
| Cần reason/actor/correlation ID | Domain audit events hoặc outbox | Event completeness và idempotency |
| Chỉ cần biết một batch đã chạy | Batch operation log | Không có per-entity history |
| Muốn một timeline duy nhất từ nhiều cơ chế | Audit aggregation layer có hợp đồng rõ | Dedupe, ordering, source-of-truth |
| Cần ràng buộc DB luôn đúng | PK/FK/UNIQUE/CHECK + transactions | Không tự tạo Envers history |

Điểm lựa chọn đầu tiên không phải “công nghệ nào nhanh nhất?” mà là: **phải chứng minh những gì về dữ liệu đã thay đổi?**

## 24. Phát hiện khoảng trống giữa lịch sử Envers và database

Một bước reconciliation có thể so sánh current state với latest audited state của entity.

~~~java
AuditReader reader =
        AuditReaderFactory.get(em);

List<Number> revisions =
        reader.getRevisions(Product.class, productId);

if (!revisions.isEmpty()) {
    Number latest =
            revisions.get(revisions.size() - 1);

    Product history =
            reader.find(Product.class, productId, latest);

    Product current =
            em.find(Product.class, productId);

    // Đối chiếu audited fields phù hợp.
    // Cần hiểu chính sách xóa và concurrent writes.
}
~~~

### 24.1. Giới hạn của reconciliation

- Entity có thể đã bị xóa hợp lệ với DEL revision.
- Field `@NotAudited` không nên dùng để kết luận audit mismatch.
- Current object trong L1 có thể stale.
- Concurrent transactions khiến hai nguồn được đọc ở thời điểm khác nhau.
- Lazy associations/relations có cách audit riêng.
- **Nếu dữ liệu từng đi 100 → 130 → 100 bằng direct SQL, current state vẫn bằng latest audited state, nhưng hai transitions đã mất.**

Vì vậy reconciliation là công cụ phát hiện một số sai lệch, **không thể chứng minh toàn bộ lịch sử đã được ghi hoặc tái tạo quá khứ bị thiếu**.

### 24.2. Có nên tạo “revision bù”?

Nếu thiếu lịch sử từ một thao tác đã xảy ra, ứng dụng có thể tạo một reconciliation note hoặc audit event **ở thời điểm phát hiện** với mức độ chắc chắn thích hợp.

Không nên giả mạo một Envers revision cũ với timestamps/actor/values mà hệ thống không còn biết. Một event mới mô tả sự cố audit không thay thế được chuỗi thực tế đã mất.

## 25. Quan sát và vận hành

### 25.1. Hibernate SQL logging

Trong dev/test:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
~~~

Có thể kiểm tra SQL đối với `products` và audit tables. Managed updates thường phát thêm audit-related DML, còn bulk mutations không tạo per-entity audit inserts.

Tuy nhiên log ở Hibernate **không thấy** SQL do DBA hoặc ứng dụng khác chạy. Với yêu cầu audit toàn hệ thống, cần database-level observability.

### 25.2. Metrics và logging khác

Có thể theo dõi:

- Số rows bị bulk updates/deletes theo operation.
- Số audit rows sinh tương ứng ở cơ chế đã chọn.
- Operation/correlation IDs.
- Database audit logs hoặc trigger metrics.
- CDC connector lag và health.
- Outbox retry/dead-letter queue.
- Sự khác biệt giữa current state và audited state trong reconciliation.

Không dựa vào số lượng audit rows bằng số lượng SQL statements. Một statement có thể đổi hàng nghìn rows, và một revision có thể chứa nhiều audited entity changes.

### 25.3. Bảo vệ dữ liệu lịch sử

Envers lưu lịch sử nhưng không mặc định cung cấp tính **tamper-proof**:

- DBA có quyền cao có thể sửa/xóa bảng history.
- Bảng audit có thể chứa thông tin cá nhân/tài chính.
- Cần retention, encryption, access controls và backup thích hợp.
- Nếu bắt buộc chống chỉnh sửa, cân nhắc lưu log bất biến, ký/đối chiếu dữ liệu hoặc hạ tầng chuyên dụng phù hợp.
- Nếu cần xóa dữ liệu theo chính sách bảo mật/riêng tư, phải xét cả audit tables và downstream copies.

Không tuyên bố hệ thống đáp ứng compliance chỉ vì entity có `@Audited`.

## 26. Kiểm thử đường ghi được audit

Một unit test trên entity class không chứng minh Envers listeners thực sự ghi DB. Cần integration tests với Hibernate Envers, datasource và transaction boundaries thật.

### 26.1. Baseline: managed INSERT và UPDATE

~~~java
// Transaction A:
em.persist(Product.create(
        42L,
        "Sample",
        new BigDecimal("100.00"),
        ProductStatus.ACTIVE
));
// Commit A.

// Transaction B:
Product product = em.find(Product.class, 42L);
product.changePrice(new BigDecimal("120.00"));
// Commit B.

// Transaction C:
AuditReader reader = AuditReaderFactory.get(em);
List<Number> revisions =
        reader.getRevisions(Product.class, 42L);
// Mong đợi có ADD và MOD revisions tương ứng.
~~~

Ví dụ là pseudo-flow; mã factory `Product.create` và transaction setup phải được dự án thực thi. Dùng EntityManager mới theo các bước để quan sát state đã commit.

### 26.2. Bulk UPDATE: DB đổi, revision count không đổi

~~~java
// Transaction D:
int affected = em.createQuery(
        "update Product p set p.price = :price where p.id = :id"
    )
    .setParameter("price", new BigDecimal("150.00"))
    .setParameter("id", 42L)
    .executeUpdate();
// Commit D.

// Transaction E, EntityManager mới:
Product current =
        em.find(Product.class, 42L);

List<Number> laterRevisions =
        AuditReaderFactory.get(em)
            .getRevisions(Product.class, 42L);
~~~

Nếu không có audit mechanism bổ sung:

- `current.getPrice()` là 150.
- Revision list không có revision mới do bulk UPDATE.
- Latest historical value có thể vẫn là 120.

Đây là minh chứng trực tiếp cho giới hạn, tốt hơn chỉ quan sát SQL logs.

### 26.3. Native SQL

Lặp lại với:

~~~java
em.createNativeQuery(
        "update products set price = :price where id = :id"
    )
    .setParameter("price", new BigDecimal("170.00"))
    .setParameter("id", 42L)
    .executeUpdate();
~~~

Kiểm tra database state đổi, còn Envers revisions không tăng vì chính câu SQL này.

### 26.4. Bulk DELETE

~~~java
em.createQuery(
        "delete from Product p where p.id = :id"
    )
    .setParameter("id", 42L)
    .executeUpdate();
~~~

Kiểm tra:

- Row bị xóa từ table gốc.
- Không có Envers DEL revision do bulk DELETE.
- AuditReader trả trạng thái as-of thế nào.
- FK/cascade behavior ở DB.

Không chạy test trên database dùng chung hoặc có dữ liệu thật.

### 26.5. Test concurrency và L1

- Load Product trong EntityManager A.
- Chạy bulk UPDATE ở transaction khác.
- Đọc lại A để quan sát stale state.
- Kiểm tra `@Version`, conflicts và flush/clear behavior.
- Đảm bảo mỗi transaction dùng context phù hợp.
- Dùng barriers/latches để điều phối thay vì `Thread.sleep` tùy thời gian.

### 26.6. Test custom bulk audit/triggers/CDC

Nếu đã thiết kế cơ chế audit thay thế, kiểm tra:

1. Every affected row có audit record theo contract.
2. Before/after values là giá trị thật.
3. Actor và operation ID đáng tin cậy.
4. Rollback không để lại history giả.
5. Retry không tạo duplicate logical events.
6. Concurrent writers không làm audit mất hoặc thừa rows.
7. Bulk DELETE và DB cascades có lịch sử đầy đủ.
8. Schema evolution không làm history reader hỏng.
9. Audit retention/access control phù hợp.
10. CDC lag/outbox retries được theo dõi.

## 27. Những hiểu nhầm phổ biến

| Nhận định | Vì sao sai? |
| --- | --- |
| “Có `@Audited` là mọi SQL đều được audit” | Annotation áp lên ORM lifecycle events, không phải SQL ngoài Envers |
| “HQL UPDATE của Hibernate vẫn gọi Envers” | Bulk HQL bypass per-entity events |
| “CriteriaUpdate type-safe nên có @PreUpdate” | Query-building type safety không thay event semantics |
| “@Modifying(clearAutomatically=true) sửa lịch sử” | Chỉ giúp tránh managed state stale |
| “Flush trước bulk sẽ audit bulk” | Flush audit pending managed changes, không audit SQL mutation kế tiếp |
| “Refresh sau bulk sẽ tạo revision” | Refresh đọc state, không tái tạo sự kiện quá khứ |
| “update versioned nghĩa là Envers được gọi” | Version increment không phải audit revision |
| “DB ON DELETE CASCADE sinh DEL revision cho children” | Database cascade không phát Hibernate entity events |
| “Có cache invalidation nên Envers cũng xử lý” | Cache và audit là hai cơ chế khác |
| “Một revision cuối đủ để suy lại mọi thay đổi” | Không có old/new transition records thì không tái tạo được |
| “Tự INSERT một row vào _AUD là đủ” | Revision strategy, metadata và relations phức tạp |
| “Latest audited state bằng live state nghĩa là không thiếu gì” | Nhiều transitions có thể đã xảy ra rồi quay về giá cũ |
| “CDC luôn có actor nghiệp vụ” | Raw DB changes không tự biết authenticated app user |
| “Audit log nằm trong DB thì bất biến” | Quyền cao có thể sửa/xóa nếu không có bảo vệ riêng |

## 28. Quy trình chọn write path an toàn

1. **Xác định entity/table có lịch sử cần bảo toàn.**
2. **Làm rõ granularity:** mỗi entity revision, mỗi DB row change hay một business operation.
3. **Kiểm tra API mutation:** managed entity hay bulk/native SQL.
4. **Nếu bắt buộc AuditReader history đầy đủ, ưu tiên managed updates.**
5. **Nếu cần bulk hiệu năng cao, thiết kế transactional audit table hoặc cơ chế DB-level capture.**
6. **Đảm bảo before/after state và affected IDs được xác định ổn định dưới concurrency.**
7. **Không tự INSERT vào _AUD nếu chưa có integration được kiểm thử sâu.**
8. **Phân biệt cache invalidation, optimistic versioning và audit.**
9. **Xử lý stale Persistence Context sau bulk DML.**
10. **Bổ sung DB constraints cho invariants không thể chỉ dựa vào ORM listeners.**
11. **Giữ actor/reason/operation ID theo nguồn đáng tin cậy.**
12. **Quy định các đường ghi từ DBA, ETL, migration và external services.**
13. **Tạo integration tests chứng minh cả database changes và history records.**
14. **Quan sát gaps, CDC lag, audit storage và quyền truy cập.**
15. **Đánh giá retention, privacy và khả năng chống chỉnh sửa của history.**

## 29. Bài tập thực hành

### Bài 1 — So sánh hai cách đổi giá

~~~java
Product p = em.find(Product.class, 42L);
p.changePrice(new BigDecimal("150.00"));
~~~

và:

~~~java
em.createQuery(
        "update Product p set p.price = :price where p.id = :id"
    )
    .setParameter("price", new BigDecimal("150.00"))
    .setParameter("id", 42L)
    .executeUpdate();
~~~

Đường nào có thể tạo Envers MOD revision và tại sao?

### Bài 2 — Khoảng trống lịch sử

Product có giá 100 ở REV 10. Bulk UPDATE đặt giá 130. Sau đó một managed UPDATE đặt giá 140 ở REV 12. AuditReader có thể hiển thị những giá nào? Vì sao giá 130 bị thiếu?

### Bài 3 — Bulk DELETE

Một Spring Data repository dùng `@Modifying @Query("delete from Product ...")`. Cần kiểm tra gì nếu nghiệp vụ yêu cầu biết chính xác ai đã xóa từng Product?

### Bài 4 — Stale state

Một EntityManager load Product giá 100, bulk UPDATE đặt DB giá 120, rồi Java đọc lại `product.getPrice()`. Vì sao có thể vẫn nhận 100? `clear()` giải quyết vấn đề gì và có giải quyết audit không?

### Bài 5 — Optimistic locking

Một HQL `update versioned Product ...` có thể thay đổi version. Nó có đồng nghĩa Envers có MOD revision không? Vì sao?

### Bài 6 — Triggers

Ba ứng dụng cùng sửa bảng products, chỉ một ứng dụng dùng Hibernate. Nếu mọi UPDATE cần được log, hãy so sánh Envers với database trigger và nêu vấn đề actor/trust.

### Bài 7 — CDC

CDC nhận transaction log từ DB. Nó có thể phát hiện DBA SQL changes không? Vì sao một raw CDC event chưa chắc ghi được business reason?

### Bài 8 — Bảng audit riêng

Thiết kế bulk price update với bảng `product_price_change_log`. Làm thế nào đảm bảo tập IDs được UPDATE bằng đúng tập đã chụp old values trong một transaction có concurrent writers?

### Bài 9 — Tự ghi products_AUD

Vì sao không nên tự INSERT dòng `products_AUD` chỉ có `REV` và price? Khi bật ValidityAuditStrategy, cần chú ý thêm những hiệu lực nào?

### Bài 10 — Reconciliation

Latest audited price bằng current price. Có đủ chứng minh không thiếu revision không? Hãy cho ví dụ giá thay đổi rồi quay về giá ban đầu qua direct SQL.

### Bài 11 — Audit completeness test

Mô tả một integration test tạo Product bằng ORM, bulk UPDATE bằng HQL và sau đó kiểm tra cả bảng dữ liệu gốc lẫn `AuditReader.getRevisions`. Expected results là gì?

### Bài 12 — Đánh đổi hiệu năng

Một job cần đổi giá hàng triệu Products. Nếu bắt buộc Envers history cho từng entity, có thể tối ưu managed updates bằng những cơ chế nào? Nếu chuyển sang bulk SQL, những yêu cầu audit mới nào phải thực hiện rõ ràng?

**Gợi ý:** (1) managed event path; (2) 100 và 140, không có 130; (3) DEL revision hoặc audit thay thế; (4) L1 stale, clear không retroactive audit; (5) khác nhau; (6) trigger thấy mọi DB writes, actor cần enrichment; (7) được nhưng không tự có lý do nghiệp vụ; (8) stable staging/lock/isolation; (9) revision metadata/validity ranges; (10) 100 → 130 → 100; (11) live state đổi, Envers revision count không đổi; (12) batching/chunking hoặc transactional explicit audit.

## 30. Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide — Envers](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#envers): audited entities, revision metadata, audit strategies và queries.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): bulk DML, persistence context, entity lifecycle, flushing và versioning.
- [Hibernate ORM 6.6 HQL Reference](https://docs.hibernate.org/orm/6.6/querylanguage/html_single/Hibernate_Query_Language.html): UPDATE/DELETE mutation queries và extension `update versioned`.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): JPQL bulk operations, CriteriaUpdate/Delete, lifecycle callbacks và optimistic locking.
- [Spring Data JPA Reference — Modifying Queries](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): `@Modifying`, flushAutomatically và clearAutomatically.
- [Debezium Documentation](https://debezium.io/documentation/): CDC từ transaction logs và event-stream processing.

**Kết luận:** Envers ghi lịch sử qua **audited entity lifecycle events**, không tự thu thập mọi thay đổi trong database. Bulk HQL/JPQL/Criteria DML, native SQL, JDBC và external writers có thể cập nhật hoặc xóa rows mà không có ADD/MOD/DEL revisions; chúng cũng có thể bỏ qua callbacks, validation và optimistic checks, đồng thời làm Persistence Context stale. Nếu cần lịch sử per-entity theo Envers, hãy dùng managed entity updates và tối ưu batching/chunking. Nếu phải bulk DML quy mô lớn, thiết kế transactional audit hoặc DB triggers/CDC/outbox với contract riêng, kiểm tra actor, affected rows và concurrency. Không vá các khoảng trống bằng cách tự ghi thiếu thông tin vào `_AUD`. Những transitions không được ghi lại tại thời điểm xảy ra thường không thể được tái tạo trung thực chỉ từ state cuối cùng.
