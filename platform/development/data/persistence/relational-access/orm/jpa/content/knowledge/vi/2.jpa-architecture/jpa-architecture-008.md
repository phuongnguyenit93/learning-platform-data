# Phạm vi chuẩn JPA và tính năng mở rộng của provider

Trong một ứng dụng Java dùng ORM, lập trình viên thường thấy các annotation như `@Entity`, `@OneToMany` và API `EntityManager`. Những thành phần này không tự lưu dữ liệu: chúng xác định **hợp đồng chuẩn** để một phần mềm ORM thực thi việc ánh xạ đối tượng Java sang cơ sở dữ liệu quan hệ.

Điểm cần nắm vững trong kiến trúc JPA là phân biệt:

- **Chuẩn JPA / Jakarta Persistence**: mô tả API, annotation, ngữ nghĩa quản lý entity, cơ chế truy vấn và các hành vi mà implementation phải tuân theo.
- **JPA provider**: phần mềm hiện thực chuẩn ấy, chẳng hạn Hibernate ORM hoặc EclipseLink. Provider quyết định cách tạo SQL, quản lý persistence context, lazy loading, cache và nhiều chi tiết tối ưu.
- **Tính năng mở rộng của provider**: API, annotation, cấu hình và cách tối ưu nằm ngoài hợp đồng chuẩn JPA, thường chỉ hoạt động với một provider cụ thể.

Một dự án có thể **sử dụng JPA** và đồng thời **phụ thuộc vào tính năng riêng của Hibernate**. Đây không phải điều sai, nhưng đó là một quyết định kiến trúc phải được nhận biết để tránh kỳ vọng nhầm về khả năng di chuyển giữa các provider.

## 1. JPA đứng ở đâu trong kiến trúc ứng dụng?

JPA là tên thường dùng cho *Java Persistence API*. Trong hệ sinh thái Jakarta EE hiện nay, tên chính thức là **Jakarta Persistence** và các package mới dùng tiền tố `jakarta.persistence`. Những dự án cũ có thể dùng `javax.persistence`, nên phải xác định phiên bản API phù hợp khi đọc ví dụ hoặc thêm dependency.

Sơ đồ các tầng:

```text
┌─────────────────────────────────────────────────────┐
│  Ứng dụng Java                                      │
│  OrderService, CheckoutService, domain entities     │
└───────────────────────┬─────────────────────────────┘
                        │ gọi API chuẩn
                        ▼
┌─────────────────────────────────────────────────────┐
│  Jakarta Persistence API / hợp đồng JPA             │
│  @Entity, @Id, EntityManager, JPQL, Criteria API     │
└───────────────────────┬─────────────────────────────┘
                        │ được hiện thực bởi
                        ▼
┌─────────────────────────────────────────────────────┐
│  JPA Provider                                       │
│  Hibernate ORM / EclipseLink / provider tương thích │
│  SQL generation, identity map, dirty checking, ...  │
└───────────────────────┬─────────────────────────────┘
                        │ JDBC, dialect, driver
                        ▼
┌─────────────────────────────────────────────────────┐
│  Hệ quản trị CSDL quan hệ                           │
│  PostgreSQL, MySQL, Oracle, SQL Server, ...          │
└─────────────────────────────────────────────────────┘
```

**API chuẩn không đồng nghĩa với provider.** Thêm dependency `jakarta.persistence-api` cung cấp các interface và annotation để biên dịch, nhưng bản thân nó không phải một ORM engine có khả năng thực hiện `persist()`. Ứng dụng cần một implementation JPA thực tế cùng cấu hình kết nối phù hợp.

**Provider cũng không đồng nghĩa với database.** Hibernate có thể kết nối nhiều loại RDBMS qua JDBC và dialect; PostgreSQL hay MySQL không phải JPA provider. Sự tương thích giữa provider và database còn phụ thuộc phiên bản driver, cú pháp SQL, kiểu cột và các khả năng của từng hệ quản trị.

### Ví dụ đường đi của một thao tác

Ứng dụng gọi:

```java
entityManager.persist(order);
```

JPA quy định ý nghĩa của việc chuyển một entity mới vào trạng thái được quản lý. Provider sẽ theo dõi entity ấy và thực hiện thao tác SQL cần thiết để đồng bộ dữ liệu. SQL có thể được gửi ở thời điểm `flush()`, trước truy vấn trong một số điều kiện, hoặc lúc commit. Cách gom câu lệnh, thứ tự thực hiện, cách lấy khóa sinh tự động và các tối ưu khác phụ thuộc implementation cùng cấu hình.

Vì vậy, câu lệnh `persist()` là API chuẩn, nhưng đoạn SQL cụ thể được phát ra không phải một phần giao diện ứng dụng JPA hứa sẽ giống nhau giữa các provider.

## 2. Những gì JPA tiêu chuẩn hóa

Chuẩn mô tả **cách ứng dụng tương tác với persistence layer** và các ngữ nghĩa chung. Dưới đây là các nhóm chức năng quan trọng.

| Phạm vi | Khả năng chuẩn | Ví dụ |
| --- | --- | --- |
| Định nghĩa entity | Mapping class, thuộc tính, khóa chính | `@Entity`, `@Table`, `@Id`, `@Column` |
| Ánh xạ quan hệ | Một-một, nhiều-một, một-nhiều, nhiều-nhiều | `@OneToOne`, `@ManyToOne`, `@OneToMany`, `@ManyToMany` |
| Mô hình dữ liệu | Embedded value, enum, converter, kế thừa | `@Embeddable`, `@Embedded`, `@Enumerated`, `@Converter`, `@Inheritance` |
| Vòng đời entity | Tạo, tìm, cập nhật, xóa, detach, merge | `EntityManager.persist()`, `find()`, `remove()`, `merge()` |
| Persistence context | Theo dõi entity được quản lý và đồng bộ trạng thái | `EntityManager`, `flush()`, `clear()`, `detach()` |
| Truy vấn | JPQL, Criteria API, native query qua giao diện JPA | `createQuery()`, `CriteriaBuilder`, `createNativeQuery()` |
| Kế hoạch tải | Fetch type, fetch join, entity graph | `FetchType.LAZY`, `JOIN FETCH`, `EntityGraph` |
| Giao dịch và xung đột | Tích hợp transaction, lock mode, version | `EntityTransaction`, `LockModeType`, `@Version` |
| Sự kiện entity | Callback vòng đời và entity listener | `@PrePersist`, `@PostLoad`, `@EntityListeners` |
| Cache cấp hai (giao diện) | API điều khiển và quy định khả năng cache | `EntityManagerFactory.getCache()`, `@Cacheable`, `SharedCacheMode` |

Một số khả năng như cache cấp hai và các cách tối ưu có thể là **tùy chọn, phụ thuộc provider hoặc môi trường triển khai**. Có API chuẩn không có nghĩa mọi provider đều có cùng thuật toán, cùng hiệu năng hoặc hỗ trợ tất cả tính năng tùy chọn giống nhau.

### 2.1. Mapping entity và quan hệ

Ví dụ model với Java/Jakarta Persistence:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Version
    private long version;

    protected PurchaseOrder() {
        // Constructor không tham số cho JPA.
    }

    public Customer getCustomer() {
        return customer;
    }
}
```

`@Entity`, `@Table`, `@ManyToOne`, `@JoinColumn` và `@Version` thuộc chuẩn JPA. Ý nghĩa của chúng không bị ràng buộc với tên một provider. Provider phải hiểu mapping này theo các quy tắc của phiên bản đặc tả mà nó hiện thực.

Điều đó **không bảo đảm** mọi database có cùng cách đặt tên định danh, tự tăng ID, khóa ngoài hoặc kiểu dữ liệu. Nếu schema không khớp mapping, ứng dụng vẫn có thể lỗi dù dùng toàn annotation chuẩn.

### 2.2. API quản lý vòng đời entity

```java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, 100L);
entityManager.persist(newOrder);
entityManager.remove(order);
entityManager.flush();
```

Ứng dụng dùng `EntityManager` thay cho class nội bộ của Hibernate hoặc EclipseLink. Chuẩn quy định các trạng thái entity (new, managed, detached, removed), ngữ nghĩa persistence context và các thao tác chính.

Một managed entity thường được provider theo dõi để đồng bộ thay đổi vào database; cơ chế theo dõi chính xác có thể dùng snapshot, bytecode enhancement hoặc kỹ thuật khác. **Dirty checking là hành vi được mong đợi trong ngữ nghĩa quản lý entity, không phải một API riêng bắt buộc ứng dụng phải gọi.**

Một lưu ý quan trọng: `merge(detachedEntity)` trả về một managed instance. Không nên mặc định rằng chính object detached được truyền vào trở thành object managed.

### 2.3. Ngôn ngữ truy vấn độc lập tương đối với database

JPQL mô tả truy vấn theo **entity và thuộc tính**, khác với SQL viết theo tên bảng/cột:

```java
List<PurchaseOrder> orders = entityManager.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "JOIN FETCH o.customer " +
    "WHERE o.id >= :minId",
    PurchaseOrder.class
).setParameter("minId", 100L)
 .getResultList();
```

`PurchaseOrder` và `customer` ở đây là tên class/thuộc tính entity, không phải tên bảng `purchase_orders` hay cột `customer_id`. `JOIN FETCH` là cú pháp **JPQL chuẩn**; cách provider chuyển câu lệnh sang SQL có thể khác nhau.

JPA cũng chuẩn hóa Criteria API, cho phép xây dựng truy vấn có cấu trúc bằng Java thay vì nối chuỗi:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq = cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> root = cq.from(PurchaseOrder.class);

cq.select(root).where(cb.greaterThan(root.get("id"), 100L));

List<PurchaseOrder> result = entityManager.createQuery(cq).getResultList();
```

Criteria API là chuẩn; nhưng tên property, kiểu dữ liệu, chức năng SQL được hỗ trợ và cách tối ưu truy vấn vẫn ảnh hưởng tới tính di động thực tế. Để có kiểm tra kiểu mạnh hơn có thể sử dụng static metamodel.

### 2.4. Entity graph và fetch plan theo chuẩn

Không phải mọi cách tối ưu tải quan hệ đều là phần mở rộng Hibernate. JPA có sẵn entity graph để mô tả quan hệ muốn nạp cho một use case.

```java
EntityGraph<PurchaseOrder> graph =
    entityManager.createEntityGraph(PurchaseOrder.class);
graph.addAttributeNodes("customer");

Map<String, Object> hints = Map.of(
    "jakarta.persistence.fetchgraph", graph
);

PurchaseOrder order =
    entityManager.find(PurchaseOrder.class, 100L, hints);
```

`EntityGraph` và hint `jakarta.persistence.fetchgraph` là phần của Jakarta Persistence. Provider vẫn quyết định SQL cụ thể và phải diễn giải graph theo ngữ nghĩa chuẩn.

Phân biệt ba ý:

1. **Tính đúng chức năng:** entity cần truy cập có được nạp theo yêu cầu hay không.
2. **Tính đúng ngữ nghĩa chuẩn:** provider có xử lý graph/hint phù hợp với đặc tả hay không.
3. **Hiệu năng thực tế:** số query, kiểu `JOIN`, số hàng và bộ nhớ dùng để nạp đồ thị.

Khía cạnh thứ ba cần đo đạc với provider và database đang chạy.

## 3. Những gì JPA không bảo đảm giống nhau

Chuẩn JPA không quy định từng chi tiết vận hành của ORM và RDBMS. Hai ứng dụng viết cùng entity và JPQL có thể tạo SQL hoặc dùng tài nguyên rất khác nhau.

| Chủ đề | Hợp đồng chung của JPA | Phần còn phụ thuộc provider / database |
| --- | --- | --- |
| Sinh SQL | Kết quả và ngữ nghĩa truy vấn theo chuẩn | Cách sắp `JOIN`, alias, phân trang SQL, subquery, tối ưu |
| Lazy loading | Mô tả ngữ nghĩa fetch qua mapping và truy vấn | Proxy hay enhancement, batching, hành vi phụ với bytecode |
| Dirty checking | Entity managed được đồng bộ theo quy tắc | Cơ chế snapshot/enhancement, tối ưu câu `UPDATE` |
| JDBC batching | Không đưa ra API di động thống nhất để điều khiển chi tiết batch | Kích thước batch, cách gom `INSERT`/`UPDATE`, thứ tự statement |
| Cache | Có `Cache` và metadata/cấu hình liên quan | Cache provider, eviction policy, concurrency strategy, key format |
| Schema | Có metadata mapping và cơ chế schema generation chuẩn | DDL cụ thể, migration, index đặc thù, kiểu dữ liệu, chiến lược cấp ID |
| Logging/metrics | Không quy định hệ thống SQL logging chung cho mọi provider | Log category, statistics, event hooks, tracing |
| Khả năng SQL riêng | Có native query qua API chuẩn | Cú pháp JSON, window function, locking, loại index, stored procedure theo DB |
| Timeout, hint | Có một số hint và cách truyền hint | Khả năng áp dụng hoặc bỏ qua, cơ chế hủy query tùy DB/driver |
| Multi-tenancy | Không có một cấu hình tenant discriminator thống nhất cho mọi trường hợp/provider | Tenant resolver, filter, schema/database switching, cache scoping |

Một biểu thức JPQL hợp lệ về cú pháp vẫn có thể gặp giới hạn do provider hoặc dialect khi ánh xạ sang SQL của một hệ cơ sở dữ liệu cụ thể. Tính portable cần kiểm tra trên **cả phiên bản provider, database, driver và cấu hình**.

### Truy vấn native là điểm giao nhau quan trọng

Ví dụ:

```java
List<?> rows = entityManager.createNativeQuery(
    "SELECT * FROM purchase_orders WHERE id = ?"
).setParameter(1, 100L)
 .getResultList();
```

`createNativeQuery()` thuộc JPA chuẩn. Tuy nhiên, **câu SQL bên trong không trở thành SQL portable chỉ vì được gửi qua EntityManager**. Nếu dùng `jsonb`, `ILIKE`, cú pháp `UPSERT` hoặc toán tử đặc thù PostgreSQL, việc đổi sang Oracle/MySQL có thể buộc viết lại query.

Tương tự, một project có thể hoàn toàn dùng API JPA chuẩn nhưng phụ thuộc mạnh vào database qua native SQL, DDL, stored procedure và index chuyên biệt.

## 4. Tính năng mở rộng của provider là gì?

Một JPA provider thường cung cấp ba nhóm mở rộng:

- **Annotation hoặc API riêng** được đưa trực tiếp vào code ứng dụng.
- **Cấu hình riêng** nhằm điều khiển tối ưu, SQL dialect, cache, logging, schema hoặc transaction integration.
- **Ngôn ngữ truy vấn / hook bổ sung**, chẳng hạn các cú pháp truy vấn, event, filter hoặc custom type không được đặc tả JPA định nghĩa.

Những chức năng này có thể rất hữu ích khi JPA chuẩn không diễn đạt đủ nhu cầu. Đánh đổi là mã nguồn hoặc hành vi trở nên gắn với provider và thậm chí gắn với **phiên bản** provider.

### 4.1. Ví dụ Hibernate: batch fetching

JPA không có annotation chuẩn tương đương trực tiếp với `@BatchSize` của Hibernate. Khi cần hạn chế nhiều query tải collection lazy, có thể dùng extension:

```java
import jakarta.persistence.*;
import org.hibernate.annotations.BatchSize;

@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    @BatchSize(size = 32) // Hibernate-specific
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}
}
```

Ý tưởng: khi ứng dụng lần lượt truy cập nhiều collection chưa được khởi tạo, Hibernate có thể tải theo nhóm thay vì thực hiện một truy vấn cho từng collection. `size = 32` là gợi ý cấu hình batching; số câu SQL thực tế còn phụ thuộc cách tải, cache và số collection đang chờ.

Đổi provider sang EclipseLink có hai vấn đề:

1. Annotation `org.hibernate.annotations.BatchSize` không thuộc Jakarta Persistence. Source code đang phụ thuộc artifact Hibernate để biên dịch.
2. EclipseLink không có nghĩa vụ hiểu annotation này hoặc áp dụng cùng thuật toán batch fetching.

Ví dụ này thể hiện **extension cấp source code**, khác với việc chỉ cấu hình một thuộc tính trong file deployment.

### 4.2. Ví dụ EclipseLink: batch fetching theo API riêng

EclipseLink có chức năng batch fetching với annotation riêng, chẳng hạn:

```java
import org.eclipse.persistence.annotations.BatchFetch;
import org.eclipse.persistence.annotations.BatchFetchType;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchFetch(BatchFetchType.IN) // EclipseLink-specific
private List<OrderLine> lines = new ArrayList<>();
```

Hai provider cùng giải quyết bài toán tải quan hệ theo nhóm nhưng **không dùng một annotation chung thuộc JPA**, và các chiến lược triển khai không hoàn toàn trùng nhau.

Không nên coi hai annotation này là các bản dịch một-một bảo đảm cùng hiệu năng. Khi thay provider phải quyết định lại fetch strategy và đo SQL thực tế.

### 4.3. Ví dụ Hibernate: truy cập Session API

Trong trường hợp cần khả năng không có ở `EntityManager`, Hibernate cho phép lấy native session:

```java
import org.hibernate.Session;

Session session = entityManager.unwrap(Session.class);
// Từ đây code sử dụng API Hibernate, nằm ngoài JPA chuẩn.
```

`EntityManager.unwrap(Class<T>)` là **phương thức JPA chuẩn**. Tuy nhiên, type `Session` mà code yêu cầu là **API riêng của Hibernate**. Trên provider khác, việc unwrap sang Hibernate `Session` có thể không được hỗ trợ.

Ngược lại, nếu code chỉ nhận `EntityManager` và không ép kiểu về native session, ranh giới phụ thuộc provider sẽ mỏng hơn. Khi bắt buộc dùng extension, nên giữ phần đó trong lớp infrastructure riêng.

### 4.4. Hint chuẩn và hint riêng

JPA có cơ chế `setHint()` cho truy vấn. **Tên hint mới là yếu tố quyết định** hint đó thuộc chuẩn hay thuộc provider.

```java
TypedQuery<PurchaseOrder> query = entityManager.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
);

// Hint có tên trong namespace Jakarta Persistence.
query.setHint("jakarta.persistence.query.timeout", 2000);

// Ví dụ hint riêng của Hibernate:
query.setHint("org.hibernate.readOnly", true);
```

Hint timeout tính bằng mili giây theo hợp đồng của Jakarta Persistence; việc áp dụng timeout thực tế có thể bị giới hạn bởi database, JDBC driver và provider. Hint `org.hibernate.readOnly` mang ngữ nghĩa riêng Hibernate, không phải chuẩn chung cho mọi implementation.

Theo cách thiết kế API JPA, hint không được nhận biết có thể bị bỏ qua. Vì vậy, đừng chỉ dựa vào ứng dụng khởi động thành công để kết luận rằng hint đã có hiệu lực. Cần kiểm tra cấu hình và hành vi thực tế.

## 5. Phân biệt mở rộng JPA với công nghệ nằm ở tầng khác

Trong hệ sinh thái Java persistence, tên gọi gần nhau dễ dẫn đến hiểu nhầm.

| Thành phần | Vai trò | Có phải phần chuẩn JPA? |
| --- | --- | --- |
| **Jakarta Persistence** | Đặc tả và API ORM/persistence | **Có** |
| **Hibernate ORM** | Một implementation JPA và có API mở rộng | Provider, không phải chính đặc tả |
| **EclipseLink** | Một implementation JPA và có các extension riêng | Provider, không phải chính đặc tả |
| **Spring Data JPA** | Lớp abstraction repository và query trên JPA | **Không**; là thư viện Spring |
| **Spring `@Transactional`** | Điều phối giao dịch qua Spring | **Không**; thuộc Spring transaction management |
| **Jakarta Transactions (JTA)** | API transaction phối hợp, tích hợp với JPA | Chuẩn riêng, không đồng nhất với JPA |
| **Bean Validation** | Ràng buộc bean như `@NotNull`, `@Size` | Chuẩn riêng, có thể tích hợp JPA |
| **Flyway / Liquibase** | Quản lý migration database | **Không** |
| **JDBC** | Giao tiếp SQL tới database | Chuẩn Java riêng, được provider sử dụng |

Ví dụ, interface repository sau thuộc **Spring Data JPA**, không thuộc JPA spec:

```java
public interface OrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
    List<PurchaseOrder> findByCustomerId(Long customerId);
}
```

Các method như `save()`, `findByCustomerId()`, tạo query từ tên method và annotation `@Query` của Spring Data là tiện ích từ thư viện đó. `EntityManager.persist()` mới là một phần API JPA chuẩn trực tiếp.

Một ứng dụng Spring Boot thường dùng cùng lúc Spring Data JPA, Jakarta Persistence và Hibernate ORM. Muốn tìm nguyên nhân lỗi hoặc đánh giá portability, phải xác định chức năng đang thuộc **tầng nào**.

## 6. Cấu hình theo chuẩn và cấu hình theo provider

### 6.1. Persistence unit chuẩn

Trong môi trường Java SE, một persistence unit có thể được khai báo trong `META-INF/persistence.xml` và khởi tạo qua API chuẩn:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.0">
    <persistence-unit name="shopPU"
                      transaction-type="RESOURCE_LOCAL">
        <class>com.example.domain.PurchaseOrder</class>
        <class>com.example.domain.Customer</class>
        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.postgresql.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:postgresql://localhost:5432/shop"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="shop_app"/>
        </properties>
    </persistence-unit>
</persistence>
```

Ví dụ không có mật khẩu vì việc cấp thông tin bảo mật thuộc cấu hình triển khai. DTD/schema, XML namespace, thuộc tính và tên property phải phù hợp với phiên bản Jakarta Persistence mà dự án sử dụng. Nếu cần quản lý transaction bởi container/JTA thì kiểu transaction và cấu hình datasource sẽ khác.

Phía Java:

```java
EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("shopPU");

EntityManager em = emf.createEntityManager();
try {
    em.getTransaction().begin();
    PurchaseOrder order = em.find(PurchaseOrder.class, 100L);
    em.getTransaction().commit();
} finally {
    em.close();
    emf.close();
}
```

`Persistence`, `EntityManagerFactory`, `EntityManager` và `EntityTransaction` là API chuẩn. Ở đây `getTransaction()` dùng cho **resource-local transaction**; trong môi trường JTA/container-managed, ứng dụng thường không trực tiếp bắt đầu giao dịch bằng method này.

Ứng dụng vẫn phải có JPA provider trên runtime classpath. Nếu nhiều provider cùng xuất hiện, cần cấu hình/chọn provider rõ ràng; nếu chỉ đổi một dòng cấu hình mà code đang nhập `org.hibernate.Session` hoặc `@BatchSize`, việc chuyển provider chưa hoàn tất.

### 6.2. Property riêng có thể ảnh hưởng mạnh đến hiệu năng

Một ví dụ cấu hình riêng của Hibernate:

```properties
hibernate.jdbc.batch_size=30
hibernate.order_inserts=true
hibernate.show_sql=false
```

Các property này không do Jakarta Persistence chuẩn hóa. Tác dụng thực tế phụ thuộc phiên bản Hibernate, JDBC driver, cách sinh ID và loại thao tác. Provider khác có thể dùng tên property khác hoặc không có chức năng tương đương hoàn toàn.

Một số property mang namespace `jakarta.persistence.*` là chuẩn, ví dụ cấu hình JDBC và schema generation. Một số property được đưa qua cùng cơ chế cấu hình nhưng có namespace `hibernate.*` hoặc `eclipselink.*` lại là extension. **Nơi đặt property không tự biến nó thành chuẩn**.

### 6.3. Provider lựa chọn cách phát SQL

Cùng một `@ManyToOne` hoặc `@GeneratedValue`, Hibernate và EclipseLink có thể:

- Sinh alias và cấu trúc `JOIN` khác nhau.
- Chọn cách nạp relation bằng SQL khác nhau trong các tình huống hợp lệ.
- Có cơ chế batching, caching, enhancement và proxy khác nhau.
- Tạo DDL khác nhau khi dùng tính năng schema generation.
- Hỗ trợ các kiểu SQL, function hoặc hint đặc thù tùy dialect.

Không nên viết logic nghiệp vụ dựa vào thứ tự không được cam kết của SQL phát ra hoặc số lần query nội bộ của provider. Nếu cần bảo đảm về hiệu năng, hãy biến nó thành yêu cầu có thể đo và kiểm soát bằng test tích hợp.

## 7. “Có trong chuẩn” khác với “đảm bảo portable tuyệt đối”

Một tính năng có thể sử dụng API chuẩn mà vẫn có ràng buộc môi trường.

### 7.1. `@GeneratedValue` và ID strategy

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

`@GeneratedValue` và `GenerationType` thuộc JPA. Nhưng `IDENTITY` dựa vào khả năng sinh ID của database và có thể ảnh hưởng cách provider gom `INSERT` vào JDBC batch. `SEQUENCE` cần database và schema hỗ trợ sequence phù hợp. Thay đổi database có thể kéo theo đổi chiến lược cấp ID và migration schema.

### 7.2. `@Version` và optimistic locking

```java
@Version
private long version;
```

`@Version` là chuẩn. Nó cung cấp cơ chế optimistic locking cho entity được quản lý. Tuy vậy, kiểu cột, số lượng query, thời điểm phát hiện xung đột, và tác động của câu SQL cập nhật ngoài JPA có thể cần cấu hình hay kiểm soát riêng. Một script SQL cập nhật bản ghi mà không duy trì cột `version` có thể làm hỏng giả định của cơ chế locking.

### 7.3. Lazy/eager và hiệu năng

`FetchType.LAZY`, `FetchType.EAGER` là thành phần JPA. Nhưng:

- `LAZY` có ngữ nghĩa là chiến lược hoãn tải và không nhất thiết là cam kết provider sẽ luôn trì hoãn được theo cùng cách.
- `EAGER` yêu cầu dữ liệu cần thiết được tải, **không có nghĩa phải bằng một SQL JOIN duy nhất**.
- Kiểu proxy, bytecode enhancement, query batching và cơ chế cache có thể khác giữa provider.
- Khi đã đóng persistence context, việc truy cập dữ liệu lazy chưa nạp có thể gây lỗi tùy provider và hoàn cảnh.

Vì vậy, **chiến lược fetch ở annotation** và **kế hoạch lấy dữ liệu cho từng use case** là hai tầng quyết định liên quan nhưng khác nhau.

### 7.4. DDL và migration

JPA có metadata mapping và cơ chế schema generation, hữu ích cho môi trường học tập hoặc prototype. Tuy nhiên, JPA không thay thế toàn bộ công việc quản lý migration database khi phát hành ứng dụng:

- Thêm hoặc đổi cột có thể yêu cầu chuyển đổi dữ liệu cũ.
- Index, constraint, partitioning và trigger có thể cần DDL riêng.
- Kiểu dữ liệu như JSON, full-text search, vector hay spatial thường phụ thuộc database.
- Hệ thống production cần quy trình migration có thứ tự, có kiểm soát và có khả năng rollback phù hợp.

Flyway hoặc Liquibase thường được dùng cho migration vì đây là vấn đề vòng đời schema lớn hơn chức năng ORM chuẩn.

## 8. Thiết kế code để kiểm soát phụ thuộc provider

Mục tiêu thực tế không nhất thiết phải “không dùng extension”, mà là **biết rõ điểm phụ thuộc và giới hạn tác động**.

### 8.1. Giữ nghiệp vụ phụ thuộc giao diện ổn định

Ví dụ service chỉ cần một thao tác tìm đơn hàng theo tiêu chí:

```java
public interface OrderLookup {
    List<PurchaseOrder> findForCustomer(long customerId);
}

public class CheckoutService {
    private final OrderLookup orders;

    public CheckoutService(OrderLookup orders) {
        this.orders = orders;
    }

    public void checkout(long customerId) {
        List<PurchaseOrder> customerOrders =
            orders.findForCustomer(customerId);
        // Xử lý nghiệp vụ bằng Java.
    }
}
```

Tầng infrastructure triển khai bằng `EntityManager` chuẩn:

```java
public class JpaOrderLookup implements OrderLookup {
    private final EntityManager em;

    public JpaOrderLookup(EntityManager em) {
        this.em = em;
    }

    @Override
    public List<PurchaseOrder> findForCustomer(long customerId) {
        return em.createQuery(
            "SELECT o FROM PurchaseOrder o " +
            "WHERE o.customer.id = :customerId",
            PurchaseOrder.class
        ).setParameter("customerId", customerId)
         .getResultList();
    }
}
```

Nếu cần tối ưu riêng của provider, đưa phần tùy biến vào implementation hạ tầng. Khi đó, code xử lý nghiệp vụ không phải nhập trực tiếp Hibernate `Session` hoặc biết tên query hint riêng.

### 8.2. Không lạm dụng `unwrap()`

Với provider cụ thể, `unwrap()` rất hữu ích để truy cập API chuyên sâu, nhưng càng nhiều class nghiệp vụ gọi `unwrap(Session.class)` thì chi phí đổi provider và nâng cấp phiên bản càng lớn.

Hướng thiết kế:

```text
Application / Domain
        │
        ▼
   Repository interface
        │
        ▼
JPA adapter (EntityManager, JPQL)
        │
        ├── Ưu tiên tính năng chuẩn
        └── Provider-specific adapter nếu thực sự cần
                    │
                    ▼
                 Hibernate
```

Đây là cách giảm lan truyền phụ thuộc, không phải bảo đảm có thể đổi ORM provider mà không cần sửa bất cứ code/config nào.

### 8.3. Ghi nhận vì sao dùng extension

Mỗi extension đáng kể nên trả lời được:

1. **Bài toán nào** không được giải quyết đủ tốt bằng JPA chuẩn?
2. **Provider và phiên bản nào** cung cấp tính năng?
3. **Tác động nào** khi thay provider hoặc nâng cấp phiên bản?
4. **Cách đo** tính năng có thực sự cải thiện hiệu năng hoặc đáp ứng nhu cầu?
5. **Cách thay thế** là gì nếu extension bị đổi hoặc loại bỏ?

Ví dụ: dùng Hibernate `@BatchSize(size = 32)` để giảm N+1 khi trang quản trị hiển thị 50 đơn hàng cùng các dòng hàng. Tài liệu kỹ thuật nên ghi số query, tổng thời gian truy vấn và tập dữ liệu kiểm thử trước/sau, thay vì giả định việc thêm annotation luôn tốt hơn.

## 9. So sánh hai hướng xử lý cùng một vấn đề

Bài toán: giao diện quản trị cần hiển thị **danh sách đơn hàng và tên khách hàng**.

### Cách A: dùng JPQL chuẩn

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "JOIN FETCH o.customer " +
    "WHERE o.status = :status",
    PurchaseOrder.class
).setParameter("status", OrderStatus.CREATED)
 .getResultList();
```

**Ưu điểm:** sử dụng cú pháp `JOIN FETCH` chuẩn JPA; truy vấn diễn đạt rõ quan hệ cần nạp. Có thể hoạt động trên các provider tương thích.

**Giới hạn:** cần quan tâm số hàng kết quả, dữ liệu được tải, kích thước trang và kế hoạch thực thi của database. Dùng `JOIN FETCH` với collection và pagination đòi hỏi chú ý đặc biệt vì có thể tạo nhiều hàng cho cùng root entity.

### Cách B: dùng batch fetching riêng provider

Giữ quan hệ ở trạng thái lazy, dùng Hibernate `@BatchSize` hoặc tính năng tương đương của provider cho nhu cầu tải theo nhóm.

**Ưu điểm:** có thể giảm số query khi luồng nghiệp vụ đọc nhiều relation lazy mà không muốn fetch join ngay từ truy vấn root.

**Giới hạn:** phụ thuộc provider; cách provider phân nhóm và tạo SQL có thể khác; không bảo đảm một query; code và hành vi cần kiểm thử khi đổi provider.

### Cách C: DTO projection qua JPQL chuẩn

Nếu màn hình chỉ cần ID và tên khách, có thể tránh tải cả entity graph:

```java
public record OrderRow(Long id, String customerName) {}

List<OrderRow> rows = em.createQuery(
    "SELECT NEW com.example.OrderRow(o.id, o.customer.fullName) " +
    "FROM PurchaseOrder o " +
    "WHERE o.status = :status",
    OrderRow.class
).setParameter("status", OrderStatus.CREATED)
 .getResultList();
```

Constructor expression `SELECT NEW` là tính năng JPQL chuẩn. `OrderRow` phải có constructor nhận đúng kiểu và số lượng trường; ví dụ dùng Java record với constructor mặc định tương ứng.

**Ưu điểm:** thể hiện đúng dữ liệu cần trả về; thường giảm lượng trạng thái entity provider phải quản lý.

**Giới hạn:** DTO không phải managed entity, nên không dùng như entity để dirty checking hay `persist()`. Cần viết projection cụ thể cho từng kiểu dữ liệu đầu ra.

Không có một giải pháp đúng cho mọi use case. Chuẩn JPA cung cấp các công cụ chung; provider bổ sung cách tối ưu phù hợp với workload cụ thể.

## 10. Khi nào nên sử dụng tính năng mở rộng?

| Nhu cầu | Ưu tiên xem xét trong JPA chuẩn | Khi extension có thể hợp lý |
| --- | --- | --- |
| Lấy quan hệ cần cho một màn hình | `JOIN FETCH`, `EntityGraph`, DTO projection | Batch fetching, subselect fetching, tuning fetch riêng |
| Lưu nhiều bản ghi | Transaction đúng ranh giới, `persist()`, `flush()` có chủ đích | JDBC batching, ordered inserts, thống kê batch |
| Kiểm soát xung đột | `@Version`, `LockModeType` | Khóa và chiến lược concurrency đặc thù khi có yêu cầu |
| Giá trị miền nghiệp vụ | `@Embeddable`, `AttributeConverter` | Custom JDBC/SQL type, hỗ trợ JSON/spatial đặc thù |
| Truy vấn phức tạp | JPQL, Criteria API, projection, native query | HQL mở rộng, SQL function integration, query hints riêng |
| Cache | `@Cacheable`, `Cache` API, cache mode chuẩn | Cấu hình cache region, concurrency strategy, cache provider |
| Kiểm tra hiệu năng | Thống kê ở tầng ứng dụng, SQL log từ database | Provider statistics, event listener, metrics extension |
| Nhiều tenant | Thiết kế rõ schema và ranh giới tenant trong ứng dụng/DB | Multi-tenancy API riêng nếu đáp ứng đúng mô hình |

Nên bắt đầu từ **ngữ nghĩa cần có**, xác định vấn đề đo được, rồi mới chọn extension. Nếu yêu cầu chỉ là lấy hai cột để hiển thị, DTO projection có thể giải quyết đơn giản hơn việc cấu hình nhiều lớp cache và fetch strategy.

Nếu yêu cầu bắt buộc chức năng chuyên biệt của database, việc dùng extension hoặc native SQL có thể chính đáng. Phạm vi bảo trì khi đó cần bao gồm provider, database và lộ trình nâng cấp.

## 11. Chi phí kỹ thuật khi đổi provider

Giả sử ứng dụng đang chạy Hibernate và muốn chuyển sang EclipseLink. Những điều cần xem xét gồm:

1. **Dependency và bootstrap:** provider hiện thực JPA tương ứng, cách chọn provider, cấu hình `persistence.xml` hoặc Spring.
2. **Mapping chuẩn:** class entity, khóa chính, converter, inheritance, embedded value, entity graph và lifecycle callback.
3. **Annotation riêng:** `@BatchSize`, `@Filter`, custom type hoặc các annotation trực tiếp nhập từ `org.hibernate.*`.
4. **Native API và query:** `Session`, HQL extension, query hint `org.hibernate.*`, native SQL phụ thuộc database.
5. **Cấu hình:** dialect, JDBC batching, cache, multi-tenancy, enhancement, logging, schema.
6. **Hành vi runtime:** lazy loading, transaction, flush timing, lock, cache, N+1, số truy vấn và exception thực tế.
7. **Kiểm thử:** test tích hợp đối với các thao tác đọc/ghi, transaction, concurrency, constraint và query quan trọng trên database mục tiêu.

Đổi provider không chỉ là đổi tên dependency. Mã biên dịch thành công với toàn annotation JPA cũng chưa chứng minh hệ thống sẽ giữ nguyên hiệu năng và hành vi ở mọi góc cạnh.

### Portability nên được hiểu theo nhiều mức

- **Portability ở source code:** code chỉ import `jakarta.persistence.*` và các API Java chung.
- **Portability ở mapping/query:** entity mapping, JPQL và Criteria chỉ dùng các cấu trúc có hợp đồng tiêu chuẩn.
- **Portability ở runtime:** cách provider triển khai các tính năng đáp ứng đúng yêu cầu nghiệp vụ.
- **Portability ở database:** schema, kiểu dữ liệu, DDL, native SQL và transaction phù hợp với DB mới.
- **Portability ở vận hành:** batching, cache, logging, metrics và cách triển khai được cấu hình lại phù hợp.

Một dự án có thể đạt mức đầu tiên nhưng thiếu các mức sau. Vì vậy, đánh giá khả năng di chuyển phải dựa vào môi trường chạy thật, không chỉ đếm số import của Hibernate.

## 12. Phiên bản và khả năng tương thích

Một yếu tố kiến trúc quan trọng là **ba dòng phiên bản có quan hệ nhưng không trùng nhau**:

```text
Phiên bản Jakarta Persistence API
                  │  provider phải tương thích
                  ▼
Phiên bản Hibernate ORM / EclipseLink
                  │  hỗ trợ driver và dialect
                  ▼
Phiên bản Database / JDBC driver
```

Không nên tùy ý trộn:

- Code nhập `javax.persistence.*` của hệ JPA cũ với implementation chỉ hỗ trợ namespace `jakarta.persistence.*`, hoặc ngược lại.
- API Jakarta Persistence ở phiên bản mới hơn năng lực được provider hiện thực.
- Hibernate extension lấy từ hướng dẫn phiên bản này với artifact Hibernate phiên bản khác.
- Dialect/driver thiếu hỗ trợ cho phiên bản database hoặc kiểu cột đang dùng.

Việc chuyển namespace từ `javax` sang `jakarta` không chỉ là thay tên trong ví dụ; phải đồng bộ dependency, provider và các thư viện framework liên quan. Đọc tài liệu theo **phiên bản đang dùng** đặc biệt quan trọng khi xử lý API mở rộng vốn không bị ràng buộc bởi tiêu chuẩn JPA.

Khi tra cứu tài liệu, nên phân loại:

| Loại tài liệu | Đọc khi cần |
| --- | --- |
| Jakarta Persistence specification và API Javadoc | Xác định hợp đồng chuẩn, annotation, lifecycle, JPQL |
| Hướng dẫn Hibernate ORM/EclipseLink đúng phiên bản | Cấu hình riêng, annotation mở rộng, hành vi runtime |
| Tài liệu JDBC driver và database | SQL, kiểu cột, khóa, performance, transaction |
| Tài liệu Spring/Spring Data nếu đang dùng | Transaction boundary, repository abstraction, integration |

Các nguồn tài liệu này trả lời các câu hỏi khác nhau. Không nên lấy hành vi mô tả ở hướng dẫn Hibernate rồi diễn đạt thành một cam kết của toàn bộ chuẩn JPA.

## 13. Tình huống thực hành: phân định chuẩn và extension

Hãy xem một đề xuất tối ưu cho danh sách đơn hàng:

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order")
    @org.hibernate.annotations.BatchSize(size = 20)
    private List<OrderLine> lines;

    @Version
    private long version;
}
```

Các thành phần được phân loại như sau:

| Thành phần | Phân loại | Hệ quả |
| --- | --- | --- |
| `@Entity`, `@Id` | JPA chuẩn | Provider phù hợp cần hiểu |
| `@ManyToOne`, `@OneToMany` | JPA chuẩn | Có ngữ nghĩa mapping quan hệ chuẩn |
| `FetchType.LAZY` | JPA chuẩn | Cần hiểu cơ chế thực thi lazy của provider |
| `@Version` | JPA chuẩn | Được dùng cho optimistic locking |
| `@BatchSize` | Hibernate extension | Gắn source code với annotation Hibernate |
| `size = 20` | Tham số extension | Hiệu quả batching phụ thuộc môi trường |

Giả sử sau đó thêm:

```java
entityManager.createQuery(
    "SELECT o FROM PurchaseOrder o JOIN FETCH o.customer",
    PurchaseOrder.class
).getResultList();
```

`JOIN FETCH` là JPQL chuẩn, trong khi `@BatchSize` vẫn là cấu hình riêng của Hibernate. Hai kỹ thuật có thể tồn tại trong cùng use case, nhưng giải quyết các đoạn tải dữ liệu khác nhau: khách hàng được yêu cầu tải cùng đơn hàng, còn collection `lines` có thể được tải theo nhóm nếu sau đó được truy cập và còn lazy.

Nếu một thành viên nói “cả ví dụ này là JPA chuẩn” thì phát biểu ấy chưa chính xác. Phần lớn mapping và truy vấn là chuẩn, nhưng chiến lược batch fetching đang phụ thuộc vào Hibernate.

### Câu hỏi vận dụng

1. Vì sao code gọi `EntityManager.unwrap(Session.class)` vẫn có chứa một phương thức JPA chuẩn nhưng toàn đoạn code lại phụ thuộc Hibernate?
2. Vì sao `createNativeQuery()` là phương thức chuẩn nhưng nội dung SQL chạy bên trong có thể không portable?
3. Nếu một use case bị N+1 khi tải khách hàng, liệu phải dùng ngay `@BatchSize` hay có thể giải quyết bằng `JOIN FETCH`/`EntityGraph`?
4. Khi đổi database nhưng giữ nguyên Hibernate, những phần nào vẫn phải kiểm tra ngoài code JPA?
5. Nếu Hibernate và EclipseLink đều hiện thực cùng API, điều đó có bảo đảm số SQL query và tốc độ luôn giống nhau không?

Các câu hỏi này giúp đánh giá được **ranh giới cam kết của chuẩn** và **quyết định triển khai của provider**, thay vì chỉ học thuộc tên annotation.

## Kết luận

**JPA/Jakarta Persistence chuẩn hóa cách ứng dụng Java mô tả entity, quản lý vòng đời persistence và thực hiện truy vấn theo hợp đồng chung.** Hibernate ORM, EclipseLink và các provider khác là những implementation hiện thực hợp đồng ấy, đồng thời cung cấp thêm API, annotation và khả năng cấu hình để đáp ứng nhu cầu thực tế.

Dùng tính năng JPA chuẩn giúp giảm phụ thuộc trực tiếp vào một ORM provider, nhưng không tự bảo đảm mọi câu SQL, hiệu năng hoặc hành vi database đều giống nhau. Tính năng mở rộng thường giúp giải quyết vấn đề chuyên sâu như batching, custom type hay multi-tenancy, đổi lại ứng dụng phải quản lý rõ dependency và rủi ro nâng cấp.

Khi đọc một đoạn code persistence, hãy hỏi ba điều: **“Đây là hợp đồng của Jakarta Persistence, chức năng riêng của provider, hay tính năng của framework/database bên ngoài?”**, **“Nếu đổi provider hoặc nâng cấp phiên bản thì điều gì phải kiểm tra lại?”**, và **“Có một cách dùng API chuẩn đủ đáp ứng yêu cầu trước khi cần extension hay không?”**. Nhìn đúng ba ranh giới ấy là cơ sở để thiết kế tầng persistence dễ hiểu, dễ kiểm chứng và dễ bảo trì.
