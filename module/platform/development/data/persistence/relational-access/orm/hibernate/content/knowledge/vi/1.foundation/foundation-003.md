# Hibernate dưới vai trò bộ triển khai đặc tả và các khả năng mở rộng riêng

## 1. Hibernate đứng ở đâu trong tầng truy cập dữ liệu?

Khi xây dựng ứng dụng Java lưu dữ liệu trong cơ sở dữ liệu quan hệ, lập trình viên thường gặp ba tên gọi: **Jakarta Persistence (JPA)**, **Hibernate ORM** và **JDBC**. Chúng liên quan chặt chẽ nhưng đảm nhiệm những vai trò khác nhau:

- **JDBC** là API cấp thấp để gửi SQL, truyền tham số, xử lý `ResultSet` và làm việc với kết nối cơ sở dữ liệu.
- **Jakarta Persistence** là **đặc tả** (specification): định nghĩa API, chú thích ánh xạ và các quy tắc quản lý vòng đời đối tượng khi lưu vào cơ sở dữ liệu quan hệ. Tên gọi **JPA** vẫn được dùng phổ biến; các phiên bản hiện đại sử dụng gói `jakarta.persistence.*`.
- **Hibernate ORM** là một **bộ triển khai** (persistence provider) của Jakarta Persistence. Hibernate hiện thực những hợp đồng mà đặc tả quy định và cung cấp thêm API, annotation, ngôn ngữ truy vấn, cơ chế tối ưu và các tích hợp riêng.

Luồng thực thi điển hình:

```text
Ứng dụng Java / tầng dịch vụ
           |
           | EntityManager, JPQL, @Entity, @OneToMany, ...
           v
   Jakarta Persistence API  <--- hợp đồng chuẩn
           |
           v
       Hibernate ORM        <--- một provider cụ thể
           |  ánh xạ đối tượng, SQL, dirty checking,
           |  quản lý persistence context, caching, ...
           v
          JDBC
           |
           v
    Cơ sở dữ liệu quan hệ
```

**Điểm mấu chốt:** `EntityManager` là giao diện do đặc tả định nghĩa; đối tượng đứng sau giao diện đó có thể do Hibernate tạo ra. Code gọi `entityManager.persist(product)` đang sử dụng API chuẩn, trong khi Hibernate chịu trách nhiệm tính toán và thực hiện câu lệnh `INSERT` phù hợp.

Không nên hiểu Hibernate là “JPA với một tên khác”. JPA quy định **ứng dụng có thể trông đợi điều gì** từ provider; Hibernate quyết định **thực thi điều đó bằng cách nào** và bổ sung những khả năng ngoài phạm vi đặc tả.

### Mục tiêu sau bài học

Sau khi học xong, bạn có thể:

1. Phân biệt phần nào được Jakarta Persistence bảo đảm và phần nào thuộc riêng Hibernate.
2. Viết tầng truy cập dữ liệu dựa trên `EntityManager` nhưng vẫn dùng được Hibernate làm provider.
3. Chủ động chuyển sang `Session`, HQL hoặc annotation riêng khi có nhu cầu thực tế.
4. Đánh giá lợi ích, ràng buộc phiên bản, khả năng chuyển provider và rủi ro vận hành của một phần mở rộng.

## 2. Đặc tả yêu cầu gì, Hibernate thực hiện gì?

Một đặc tả có giá trị vì nhiều thư viện có thể triển khai cùng một hợp đồng. Jakarta Persistence định nghĩa các khái niệm và hành vi quan trọng sau:

| Khái niệm chuẩn | Ý nghĩa | Vai trò của Hibernate khi làm provider |
|---|---|---|
| `@Entity`, `@Table`, `@Id`, `@Column` | Mô tả lớp và thuộc tính cần lưu | Đọc metadata và tạo ánh xạ giữa lớp Java với bảng, cột |
| `@OneToMany`, `@ManyToOne`, `@JoinColumn` | Khai báo quan hệ giữa các entity | Tạo SQL join, truy vấn và quản lý liên kết theo mapping |
| `EntityManagerFactory` | Tạo đối tượng quản lý persistence context | Hibernate cung cấp hiện thực và tài nguyên dùng chung |
| `EntityManager` | `persist`, `find`, `merge`, `remove`, truy vấn | Theo dõi entity, đồng bộ thay đổi và tương tác với DB |
| Persistence context | Quản lý danh tính và trạng thái entity | Dùng bộ nhớ cấp phiên, theo dõi thay đổi, điều phối flush |
| JPQL và Criteria API | Truy vấn theo mô hình đối tượng | Phân tích truy vấn, chuyển thành SQL thích hợp |
| `@Version` và lock mode | Kiểm soát cạnh tranh, optimistic locking | Thêm điều kiện kiểm tra phiên bản khi cập nhật/xóa |
| `EntityGraph`, fetch join | Điều chỉnh dữ liệu liên quan cần tải | Lựa chọn chiến lược truy xuất và phát sinh SQL |

Ví dụ: nếu hai lần gọi `find(Product.class, 7L)` diễn ra trong **cùng một persistence context** và entity vẫn đang được quản lý, JPA yêu cầu chúng biểu diễn cùng một thực thể đang quản lý. Hibernate sử dụng first-level cache của `Session` để hỗ trợ quy tắc danh tính này. Điều đó **không** đồng nghĩa mọi truy vấn đều tránh được SQL hay cache được chia sẻ giữa các request.

Một số cơ chế Hibernate được lập trình viên nhìn thấy qua API chuẩn:

- **Dirty checking:** thay đổi thuộc tính của entity đang được quản lý; provider phát hiện và đồng bộ khi flush theo các quy tắc áp dụng.
- **Write-behind:** `persist()` hoặc thay đổi thuộc tính không nhất thiết lập tức gửi `INSERT`/`UPDATE`; SQL có thể được trì hoãn đến lúc flush.
- **Lazy loading:** dữ liệu liên quan có thể chỉ được tải khi truy cập. Việc truy cập dữ liệu chưa tải sau khi persistence context đóng có thể gây lỗi đặc trưng của Hibernate.
- **Dialect:** Hibernate chọn cách sinh SQL theo hệ quản trị cơ sở dữ liệu, nhưng tính di động vẫn phụ thuộc kiểu dữ liệu, hàm và tính năng SQL mà ứng dụng sử dụng.

> **Phân biệt kết quả với cơ chế:** đặc tả quy định hành vi quan sát được, không bắt mọi provider phải sử dụng cùng một cấu trúc cache, cùng thuật toán dirty checking hoặc cùng chiến lược sinh SQL nội bộ.

## 3. Ví dụ nền tảng: dùng API chuẩn với Hibernate làm provider

Giả sử ứng dụng quản lý sản phẩm. Entity sau chỉ sử dụng annotation Jakarta Persistence:

```java
package demo;

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

    @Column(nullable = false, unique = true, length = 50)
    private String sku;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Version
    private long version;

    protected Product() { // Constructor cho JPA
    }

    public Product(String sku, BigDecimal price) {
        this.sku = sku;
        this.price = price;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }
}
```

Một ví dụ Java SE có thể đặt cấu hình tại `src/main/resources/META-INF/persistence.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="demo-pu" transaction-type="RESOURCE_LOCAL">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>demo.Product</class>
        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:demo;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.schema-generation.database.action"
                      value="create"/>
        </properties>
    </persistence-unit>
</persistence>
```

Ở đây:

- `provider` chỉ định Hibernate triển khai persistence unit này; nếu môi trường đã tự nhận diện provider phù hợp thì không nhất thiết phải khai báo tường minh.
- Cần có dependency Hibernate ORM, JDBC driver H2 và phiên bản Jakarta Persistence API tương thích. Với Hibernate hiện đại, artifact chính thường là `org.hibernate.orm:hibernate-core`; nên quản lý phiên bản nhất quán qua BOM hoặc dependency management của dự án.
- Tùy chọn `schema-generation.database.action=create` thuận tiện cho bài thử nghiệm. Môi trường production nên quản lý migration có kiểm soát (chẳng hạn Flyway hoặc Liquibase), không để ứng dụng tùy tiện tạo lại schema.
- File XML minh họa namespace Jakarta Persistence 3.1; cần chọn schema và dependency tương ứng với phiên bản đang sử dụng. Dự án cũ dùng `javax.persistence.*` không thể chỉ thay mỗi tên gói rồi mặc nhiên coi là tương thích.

Tầng dịch vụ có thể thao tác hoàn toàn qua API chuẩn:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;
import java.math.BigDecimal;
import java.util.List;

EntityManagerFactory emf = Persistence.createEntityManagerFactory("demo-pu");
try {
    EntityManager em = emf.createEntityManager();
    try {
        em.getTransaction().begin();

        Product product = new Product("JAVA-101", new BigDecimal("199.00"));
        em.persist(product);

        em.getTransaction().commit();
    } catch (RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        throw ex;
    } finally {
        em.close();
    }

    EntityManager reader = emf.createEntityManager();
    try {
        List<Product> products = reader.createQuery(
                "select p from Product p where p.price >= :min", Product.class)
            .setParameter("min", new BigDecimal("100.00"))
            .getResultList();
        products.forEach(p -> System.out.println(p.getSku()));
    } finally {
        reader.close();
    }
} finally {
    emf.close();
}
```

Lưu ý rằng ví dụ dùng **resource-local transaction**, thích hợp cho Java SE. Trong Spring hoặc Jakarta EE, transaction thường do container/framework quản lý qua `@Transactional`; khi đó không tự ý `begin()`/`commit()` trên `EntityManager` do container cung cấp. Các truy vấn đọc cũng có thể cần transaction nhất quán tùy nghiệp vụ và môi trường.

**Điều đáng chú ý:** entity, thao tác CRUD và JPQL ở ví dụ trên đều sử dụng hợp đồng chuẩn. Hibernate hiện diện trong dependency và cấu hình provider, nhưng phần lớn mã nghiệp vụ không phụ thuộc tên lớp `org.hibernate.*`.

## 4. Hai bề mặt API: `EntityManager` và `Session`

Hibernate có API gốc (native API) xoay quanh `SessionFactory`, `Session` và `StatelessSession`:

| Jakarta Persistence | Hibernate | Quan hệ và cách sử dụng |
|---|---|---|
| `EntityManagerFactory` | `SessionFactory` | Hibernate `SessionFactory` triển khai/mở rộng hợp đồng factory chuẩn |
| `EntityManager` | `Session` | Trong Hibernate hiện đại, `Session` mở rộng `EntityManager` và bổ sung thao tác riêng |
| `TypedQuery<T>` | Các giao diện query của Hibernate như `SelectionQuery<T>` | Truy vấn có kiểu với các tiện ích riêng |
| Không có đối ứng trực tiếp trong JPA phổ biến | `StatelessSession` | Phiên không có persistence context cấp một theo mô hình stateful |

Vì vậy, có thể bắt đầu từ `EntityManager` và chỉ mở rộng khi cần:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.Session;
import org.hibernate.SessionFactory;

Session session = entityManager.unwrap(Session.class);
SessionFactory sessionFactory = entityManagerFactory.unwrap(SessionFactory.class);
```

`unwrap()` là API chuẩn cho phép yêu cầu provider trả về một giao diện triển khai tương ứng. Đoạn code trên **chỉ chạy nếu provider hỗ trợ `Session`/`SessionFactory` của Hibernate**. Nếu đổi sang provider khác, lời gọi có thể thất bại.

Khi trực tiếp bootstrap Hibernate, ta có thể lấy session bằng `sessionFactory.openSession()`; session ngắn hạn và gắn với một đơn vị công việc. `SessionFactory` thường được khởi tạo một lần và dùng chung; **`Session` không thread-safe**, không chia sẻ qua các request/thread. Không giữ một `Session` mở vô thời hạn để né lỗi lazy loading.

Một ví dụ native API trong transaction:

```java
Session session = sessionFactory.openSession();
org.hibernate.Transaction tx = null;
try {
    tx = session.beginTransaction();

    Product product = session.find(Product.class, 1L);
    if (product != null) {
        product.setPrice(new BigDecimal("219.00"));
    }

    tx.commit(); // Hibernate flush những thay đổi cần đồng bộ
} catch (RuntimeException ex) {
    if (tx != null && tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    session.close();
}
```

Không cần `session.update(product)` để lưu thay đổi thuộc tính của một entity **đang được quản lý**. Sự thay đổi trạng thái được phát hiện và đồng bộ qua persistence context. Entity đã **detached** là trường hợp khác; hãy hiểu ngữ nghĩa `merge()` trước khi dùng và tránh giả định rằng mọi đối tượng Java đều tự được theo dõi.

### `StatelessSession` khác gì?

`StatelessSession` là lựa chọn riêng của Hibernate, thao tác theo kiểu không duy trì first-level persistence context như `Session` thông thường:

```java
try (org.hibernate.StatelessSession stateless =
         sessionFactory.openStatelessSession()) {
    Product product = stateless.get(Product.class, 1L);
    // Các thao tác ghi dùng API tường minh của StatelessSession.
}
```

Điểm khác biệt chính là không có dirty checking tự động theo mô hình `Session` stateful: sửa thuộc tính của đối tượng vừa đọc không có nghĩa sẽ tự phát sinh `UPDATE`. Ứng dụng cần sử dụng thao tác ghi thích hợp, như `stateless.update(product)`, trong transaction. Tập tính năng, tương tác với cache và cách tải quan hệ đã thay đổi qua các phiên bản Hibernate; hãy đọc đúng tài liệu phiên bản sử dụng. Đây là một mô hình xử lý có lựa chọn rõ ràng, hữu ích khi muốn kiểm soát các thao tác dữ liệu hoặc xử lý lượng lớn bản ghi.

## 5. Truy vấn chuẩn JPQL và phần mở rộng HQL

**JPQL** là ngôn ngữ truy vấn do Jakarta Persistence định nghĩa, dùng tên entity và thuộc tính Java thay vì tên bảng/cột SQL. Ví dụ:

```java
List<Product> products = entityManager.createQuery(
        "select p from Product p where p.price >= :min order by p.price desc",
        Product.class)
    .setParameter("min", new BigDecimal("100.00"))
    .getResultList();
```

**HQL (Hibernate Query Language)** là ngôn ngữ của Hibernate. Hibernate hỗ trợ JPQL và đồng thời cung cấp thêm cú pháp, biểu thức, hàm và dạng truy vấn tùy phiên bản. Chẳng hạn, HQL có thể lược bỏ phần `select` trong câu truy vấn đơn giản:

```java
Session session = entityManager.unwrap(Session.class);

List<Product> products = session.createSelectionQuery(
        "from Product p where p.price >= :min order by p.price desc",
        Product.class)
    .setParameter("min", new BigDecimal("100.00"))
    .getResultList();
```

Các khả năng HQL phong phú hơn JPQL, như một số phép toán trên tập hợp, CTE, biểu thức cửa sổ hoặc tính năng truy vấn chuyên sâu, phụ thuộc vào phiên bản Hibernate và hỗ trợ của cơ sở dữ liệu. **HQL không đồng nghĩa SQL**: `from Product` ở ví dụ trên nhắc đến entity `Product`, không phải tên bảng `products`.

Khi quyết định viết một truy vấn, có thể đi theo thứ tự:

1. Dùng JPQL hoặc Criteria API nếu đã diễn tả được yêu cầu một cách rõ ràng.
2. Dùng HQL mở rộng nếu biểu thức đó giúp truy vấn dễ hiểu hoặc hiệu quả hơn, sau khi kiểm tra hành vi trên dialect thực tế.
3. Dùng native SQL khi cần cú pháp/hint/tính năng chuyên biệt của DB mà lớp truy vấn đối tượng không thể diễn tả phù hợp.

Tham số `:min` phải được bind bằng `setParameter()`. Không ghép dữ liệu người dùng trực tiếp vào chuỗi JPQL, HQL hoặc SQL. Hãy đo SQL thực tế và execution plan trước khi kết luận một cú pháp Hibernate nhanh hơn cú pháp JPA tương đương.

## 6. Mapping: khi annotation chuẩn chưa mô tả đủ

Phần mở rộng rõ nhất của Hibernate là nhóm annotation trong `org.hibernate.annotations`. Chúng có thể gắn lên cùng entity đang dùng annotation `jakarta.persistence.*`, nhưng chúng **không tự động trở thành một phần của đặc tả**.

### 6.1. Thời điểm tạo và sửa: `@CreationTimestamp`, `@UpdateTimestamp`

```java
import java.time.Instant;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

@CreationTimestamp
@Column(name = "created_at", nullable = false, updatable = false)
private Instant createdAt;

@UpdateTimestamp
@Column(name = "updated_at", nullable = false)
private Instant updatedAt;
```

Hibernate có thể tự gán thời điểm tạo và cập nhật theo cơ chế timestamp của nó. Đây là sự tiện lợi cho dữ liệu audit đơn giản, nhưng cần lưu ý:

- Thời gian sinh ở JVM hay ở DB phụ thuộc cấu hình và khả năng tương ứng của phiên bản Hibernate; hãy thống nhất nguồn đồng hồ khi nhiều dịch vụ ghi cùng database.
- Dữ liệu ghi trực tiếp bằng SQL bên ngoài Hibernate sẽ không tự đi qua cơ chế ứng dụng này.
- JPA có lifecycle callbacks (`@PrePersist`, `@PreUpdate`) và có thể dùng default/trigger tại DB; lựa chọn phụ thuộc yêu cầu nhất quán.

### 6.2. Trường tính toán: `@Formula`

```java
import org.hibernate.annotations.Formula;

// Các cột unit_price và quantity tồn tại trong bảng order_lines.
@Formula("unit_price * quantity")
private BigDecimal lineTotal;
```

`@Formula` cho phép ánh xạ một thuộc tính chỉ đọc từ **biểu thức SQL** do Hibernate đưa vào câu truy vấn. Nó phù hợp với trường suy ra từ dữ liệu sẵn có, nhưng biểu thức phụ thuộc tên cột, SQL và khả năng DB. Thuộc tính tính bằng `@Formula` thường được tính lúc đọc; không phải một giá trị sẽ tự cập nhật trên mọi object đang nằm trong bộ nhớ ngay sau khi sửa các thuộc tính khác.

Nếu phép tính thuộc quy tắc nghiệp vụ và cần chạy nhất quán ở nhiều môi trường, cân nhắc thực hiện trong domain service hoặc thiết kế cột/view phù hợp, thay vì đẩy mọi logic vào `@Formula`.

### 6.3. Ánh xạ JSON: `@JdbcTypeCode(SqlTypes.JSON)`

```java
import java.util.Map;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@JdbcTypeCode(SqlTypes.JSON)
@Column(name = "attributes")
private Map<String, Object> attributes;
```

Hibernate có thể ánh xạ thuộc tính Java với cột JSON nhờ hệ thống type của nó. Cần phân biệt **hỗ trợ mapping** với **tính di động của schema và truy vấn JSON**:

- Database/dialect quyết định kiểu cột và khả năng SQL JSON có sẵn.
- Cần thư viện và cấu hình serialize/deserialize JSON tương thích.
- Việc truy vấn sâu vào cấu trúc JSON, tạo index và migration vẫn có thể khác biệt giữa PostgreSQL, MySQL, Oracle, v.v.
- Không nên dùng JSON để thay thế mọi quan hệ cần khóa ngoại và ràng buộc toàn vẹn.

Đặc tả Jakarta Persistence có `AttributeConverter` cho trường hợp chuyển đổi giá trị tổng quát, nhưng không phải mọi yêu cầu về kiểu cột JSON đều giải quyết được chỉ bằng converter chuẩn.

### 6.4. Khóa nghiệp vụ: `@NaturalId`

Trong ví dụ `Product`, `id` là khóa kỹ thuật còn `sku` có thể là khóa nghiệp vụ (natural key). Hibernate hỗ trợ khai báo:

```java
import org.hibernate.annotations.NaturalId;

@NaturalId
@Column(nullable = false, unique = true, length = 50)
private String sku;
```

Sau đó có thể tra cứu qua API riêng:

```java
Product product = session.bySimpleNaturalId(Product.class)
                         .load("JAVA-101");
```

Annotation `@NaturalId` bổ sung metadata và cơ chế truy xuất của Hibernate; nó **không thay thế** ràng buộc `UNIQUE` thực sự trong database. Khóa nghiệp vụ thường nên ổn định. Nếu giá trị có thể thay đổi, phải xem xét rõ tùy chọn mutable và những hệ quả đối với cache, lookup, cập nhật.

### 6.5. Lọc dữ liệu theo ngữ cảnh: `@FilterDef` và `@Filter`

Một ứng dụng nhiều tenant có thể có cột `tenant_id` trong từng bảng. Hibernate hỗ trợ filter bật theo `Session`:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.Filter;
import org.hibernate.annotations.FilterDef;
import org.hibernate.annotations.ParamDef;

@Entity
@Table(name = "purchase_orders")
@FilterDef(
    name = "tenantScope",
    parameters = @ParamDef(name = "tenantId", type = Long.class)
)
@Filter(name = "tenantScope", condition = "tenant_id = :tenantId")
public class PurchaseOrder {
    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    protected PurchaseOrder() {}
}
```

Khi xử lý một yêu cầu hợp lệ cho tenant `42`:

```java
Session session = entityManager.unwrap(Session.class);
session.enableFilter("tenantScope").setParameter("tenantId", 42L);

List<PurchaseOrder> orders = session.createSelectionQuery(
        "from PurchaseOrder", PurchaseOrder.class)
    .getResultList();
```

Filter hữu ích để tránh lặp điều kiện trong nhiều truy vấn nhưng **không nên là ranh giới bảo mật duy nhất**. Cần kiểm chứng cả đường đọc theo id, liên kết, native SQL, bulk operations và cấu hình từng phiên bản; không giả định mọi lối truy cập đều bị lọc giống nhau. Tenant ID phải lấy từ ngữ cảnh đã xác thực, không tin trực tiếp giá trị người dùng gửi. Hệ thống nhạy cảm thường cần thêm kiểm soát tại service, chính sách DB (nếu có), hoặc chiến lược multi-tenancy phù hợp.

### 6.6. Xóa mềm: `@SoftDelete`

Từ Hibernate 6.4, annotation `@SoftDelete` cung cấp hỗ trợ mapping xóa mềm cho các trường hợp được tài liệu phiên bản đó định nghĩa. Ví dụ khái niệm:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import org.hibernate.annotations.SoftDelete;

@Entity
@SoftDelete // Dùng ở phiên bản Hibernate hỗ trợ annotation này
public class Article {
    @Id
    private Long id;

    protected Article() {}
}
```

Thay vì xóa vật lý, Hibernate có thể dùng cột đánh dấu để biểu thị bản ghi đã bị xóa và loại nó khỏi những truy vấn ORM tương ứng. Các tùy chọn về tên cột, chiến lược biểu diễn trạng thái và nơi đặt annotation cần theo tài liệu phiên bản đang sử dụng.

Xóa mềm có những vấn đề nghiệp vụ **không được annotation tự giải quyết**: ràng buộc unique với bản ghi đã xóa, khôi phục, cascades, dọn dữ liệu, truy vấn báo cáo và SQL bên ngoài ORM. Đặc biệt phải kiểm tra hành vi bulk update/delete và những hệ thống khác cùng truy cập database.

### 6.7. Điều chỉnh fetching: `@BatchSize`, `@Fetch`

Hibernate còn cho phép điều chỉnh chiến lược nạp dữ liệu liên quan:

```java
import java.util.List;
import jakarta.persistence.OneToMany;
import org.hibernate.annotations.BatchSize;

@OneToMany(mappedBy = "customer")
@BatchSize(size = 32)
private List<PurchaseOrder> orders;
```

`@BatchSize` cho phép Hibernate gom nhiều lần tải lazy thành các đợt thích hợp, giúp giảm số round trip trong một số tình huống N+1. `@Fetch(FetchMode.SUBSELECT)` là lựa chọn khác cho một số collection mapping. Tuy nhiên:

- Chúng điều chỉnh chiến lược Hibernate, không bảo đảm số lượng câu SQL cố định cho mọi truy vấn.
- Cần so sánh với JPQL `join fetch`, `EntityGraph`, DTO projection và truy vấn theo lô phù hợp.
- Fetch quá nhiều có thể tạo cartesian product, kết quả trùng, tăng bộ nhớ hoặc truyền dữ liệu không cần thiết.

Tối ưu fetching phải dựa trên SQL log, thống kê, kích thước tập dữ liệu và truy vấn thực tế, không chọn annotation chỉ vì “nhanh hơn” theo kinh nghiệm chung.

## 7. Những năng lực mở rộng ngoài annotation entity

Hibernate còn cung cấp nhiều cơ chế vượt ra ngoài hợp đồng cơ bản của Jakarta Persistence:

| Năng lực | Ví dụ Hibernate | Mục đích và giới hạn cần biết |
|---|---|---|
| Điều khiển session | `Session`, `SessionFactory`, `StatelessSession` | Thao tác bổ sung và mô hình xử lý riêng; phụ thuộc provider |
| Truy vấn nâng cao | HQL, Hibernate Criteria extension, các hàm bổ sung | Biểu diễn truy vấn mà JPQL chuẩn chưa hỗ trợ; cần xét dialect |
| Kiểu dữ liệu | `@JdbcTypeCode`, type hệ thống Hibernate | Ánh xạ JSON, kiểu đặc thù; phụ thuộc DB và thư viện type |
| Tối ưu nạp dữ liệu | `@BatchSize`, `@Fetch`, batch fetching | Giảm round trip trong điều kiện thích hợp; phải đo lường |
| Cache cấp hai | Hibernate second-level cache với cache provider | Dùng chung dữ liệu giữa các session nếu cấu hình; cần chiến lược nhất quán |
| Thống kê và giám sát | `SessionFactory.getStatistics()` và tích hợp metrics | Đo truy vấn, entity load, cache hit/miss; có chi phí quan sát |
| Sự kiện và interceptors | Event listeners, interceptors | Hook vào quá trình ORM; dễ tạo phụ thuộc sâu vào vòng đời nội bộ |
| Ghi lịch sử thay đổi | Hibernate Envers và `@Audited` | Lưu lịch sử entity qua module riêng; cần bảng audit và chính sách lưu trữ |
| Multi-tenancy | Tenant identifier, connection/provider integration | Phân vùng truy cập dữ liệu; chọn chiến lược theo kiến trúc |
| Bytecode enhancement | Công cụ enhancement của Hibernate | Bổ sung khả năng tối ưu tracking/lazy ở một số mô hình; cần cấu hình build |

### Cache cấp một và cấp hai không giống nhau

**First-level cache** là persistence context gắn với từng `EntityManager`/`Session` stateful; đây là thành phần nền tảng của mô hình quản lý entity. **Second-level cache** là cơ chế tùy chọn, có thể chia sẻ dữ liệu giữa các session trong phạm vi cấu hình cache. Bật cache cấp hai không đương nhiên làm mọi truy vấn nhanh hơn: cần xác định entity nào phù hợp, cơ chế eviction/invalidation, cache provider, concurrency strategy và khả năng ứng dụng khác ghi trực tiếp vào DB.

**Query cache** (nếu sử dụng) có cơ chế và trade-off riêng; không nên nhầm nó với second-level entity cache. Đặc biệt dữ liệu thay đổi thường xuyên có thể khiến cache trở thành gánh nặng thay vì lợi ích.

### Hibernate Envers không phải `@Version`

`@Version` của JPA phục vụ **optimistic locking**: phát hiện cạnh tranh cập nhật một entity. Envers là một **module audit** riêng, có thể lưu các revision để tra cứu lịch sử thay đổi. Ví dụ annotation `@Audited` thuộc Envers và cần dependency/cấu hình liên quan. Hai công cụ giải quyết hai yêu cầu khác nhau: phát hiện xung đột ghi so với lưu lại lịch sử.

### Dialect hỗ trợ SQL khác biệt, nhưng không xóa bỏ khác biệt DB

Hibernate có thể sinh SQL phù hợp với dialect được cấu hình và che bớt khác biệt về pagination, kiểu cột, khóa, hàm và cấu trúc câu lệnh. Dù vậy, nếu ứng dụng dùng JSON operators, full-text search, expression index, stored procedure hoặc cú pháp SQL riêng, việc chuyển database vẫn có thể đòi hỏi thay đổi truy vấn, schema và migration. **Khả năng đổi provider** và **khả năng đổi database** là hai chiều di động khác nhau.

## 8. Khi nào nên ở lại chuẩn, khi nào nên dùng phần mở rộng?

Quy tắc thực hành hữu ích: **bắt đầu bằng API chuẩn để giữ ranh giới rõ ràng; dùng tính năng riêng khi nó giải quyết được vấn đề đã xác định.** Không phải mọi phụ thuộc vào Hibernate đều xấu. Nếu dự án đã chọn Hibernate lâu dài, một phần mở rộng đúng chỗ có thể đơn giản hơn và dễ vận hành hơn một giải pháp tự chế phức tạp.

| Tình huống | Lựa chọn ban đầu | Lý do |
|---|---|---|
| CRUD, lifecycle entity, transaction, optimistic locking | JPA `EntityManager`, `@Entity`, `@Version` | Đặc tả đã có hợp đồng rõ ràng |
| Tra cứu khóa nghiệp vụ thường xuyên | Xem xét `@NaturalId` | API Hibernate thuận tiện, nhưng vẫn cần unique constraint |
| Một thuộc tính cần lưu thành JSON | Xem xét `@JdbcTypeCode(SqlTypes.JSON)` | Mapping mạnh nhưng phụ thuộc dialect và phiên bản |
| Cần một biểu thức truy vấn không có trong JPQL | HQL extension hoặc native SQL | Đổi lấy sức biểu đạt và phụ thuộc provider/DB |
| Truy vấn gặp N+1 | `join fetch`/`EntityGraph` trước, đo rồi chọn `@BatchSize` khi phù hợp | Chọn theo pattern tải dữ liệu thực tế |
| Cần xóa mềm nhất quán ở ORM | `@SoftDelete` nếu phiên bản và nghiệp vụ phù hợp | Phải xử lý unique constraint, SQL ngoài ORM, khôi phục |
| Cần lịch sử revision entity | Envers hoặc giải pháp audit có chủ đích | Là yêu cầu lịch sử, không chỉ là đồng bộ entity |
| Xử lý lượng bản ghi lớn có thao tác ghi tường minh | Xem xét `StatelessSession` | Tránh giữ persistence context lớn, đổi lấy cơ chế làm việc khác |

### Mức độ phụ thuộc có thể tăng theo từng lớp

```text
Ít phụ thuộc Hibernate
   |
   +-- Domain entity dùng annotation Jakarta Persistence
   |
   +-- Repository/service gọi EntityManager và JPQL chuẩn
   |
   +-- Một vài entity có Hibernate mapping annotation
   |
   +-- Repository cụ thể unwrap Session và dùng HQL riêng
   |
   +-- Hệ thống dựa rộng rãi vào event, cache, custom type,
       enhancement và hành vi riêng của Hibernate
   |
Nhiều phụ thuộc Hibernate
```

Mức phụ thuộc càng cao, việc đổi provider thường càng tốn công. Nhưng mức phụ thuộc thấp **không bảo đảm** có thể thay provider bằng cách đổi dependency: hành vi lazy loading, DDL generation, kế hoạch truy vấn, thứ tự flush, kiểu dữ liệu và hiệu năng vẫn cần kiểm thử thực tế.

## 9. Giữ ranh giới sử dụng Hibernate trong kiến trúc ứng dụng

Một cách tổ chức dễ bảo trì là để service làm việc qua giao diện nghiệp vụ hoặc `EntityManager`, còn phần tối ưu riêng của Hibernate được đặt ở implementation của repository.

```java
public interface ProductCatalog {
    List<Product> findAffordable(BigDecimal maximumPrice);
}
```

Phiên bản sử dụng chuẩn JPA:

```java
import jakarta.persistence.EntityManager;

public class JpaProductCatalog implements ProductCatalog {
    private final EntityManager em;

    public JpaProductCatalog(EntityManager em) {
        this.em = em;
    }

    @Override
    public List<Product> findAffordable(BigDecimal maximumPrice) {
        return em.createQuery(
                "select p from Product p where p.price <= :max", Product.class)
            .setParameter("max", maximumPrice)
            .getResultList();
    }
}
```

Khi cần truy vấn HQL cụ thể, implementation có thể chủ động phụ thuộc Hibernate:

```java
import org.hibernate.Session;

public class HibernateProductCatalog implements ProductCatalog {
    private final EntityManager em;

    public HibernateProductCatalog(EntityManager em) {
        this.em = em;
    }

    @Override
    public List<Product> findAffordable(BigDecimal maximumPrice) {
        Session session = em.unwrap(Session.class);
        return session.createSelectionQuery(
                "from Product p where p.price <= :max", Product.class)
            .setParameter("max", maximumPrice)
            .getResultList();
    }
}
```

Hai implementation trên cố ý minh họa **ranh giới phụ thuộc**; truy vấn HQL đơn giản này không mang lại lợi ích hiệu năng tự động. Trong dự án thực tế, chỉ cần implementation Hibernate khi có lý do cụ thể, ví dụ dùng cấu trúc HQL mở rộng, filter hay native session operation mà API chuẩn không đáp ứng hợp lý.

Một số nguyên tắc kiến trúc:

- Giữ transaction boundary ở tầng dịch vụ và thống nhất cách quản lý với framework.
- Không truyền `Session` đang mở hoặc Hibernate proxy qua biên API công khai/serialization rồi kỳ vọng đối tượng vẫn tải được quan hệ.
- Không đặt lệnh SQL, lựa chọn dialect hoặc thao tác Hibernate session trong domain model nếu có thể giữ chúng ở tầng hạ tầng.
- Viết integration test với **database và provider thực tế** cho những mapping/query đặc thù. Database mô phỏng trong bộ nhớ hữu ích cho bài học nhưng không thay thế mọi hành vi của DB production.
- Ghi rõ phiên bản Hibernate yêu cầu khi sử dụng annotation mới; tránh import lẫn `javax.persistence.*` và `jakarta.persistence.*` trong code được dự kiến chạy trên cùng một thế hệ thư viện.

## 10. Các hiểu nhầm thường gặp

### “Có Hibernate rồi thì không cần học JPA”

Thực tế, Hibernate hiện thực rất nhiều khái niệm cốt lõi của Jakarta Persistence. Hiểu entity state, persistence context, cascade, fetch, transaction, flush, optimistic locking và JPQL sẽ giúp giải thích hành vi của Hibernate chính xác hơn. Nếu chỉ học một số annotation riêng mà không nắm vòng đời entity, rất dễ tạo lỗi cập nhật hoặc truy vấn.

### “`persist()` lập tức chạy SQL `INSERT`”

Không phải lúc nào cũng vậy. Provider có thể trì hoãn SQL đến lúc flush; chiến lược sinh id và những yêu cầu đồng bộ khác có thể khiến SQL được thực thi sớm hơn. Điều quan trọng là hiểu transaction và thời điểm đồng bộ, thay vì dự đoán số câu SQL từ số lần gọi method.

### “Dùng `FetchType.EAGER` sẽ hết lỗi N+1”

`EAGER` thể hiện yêu cầu tải liên kết, không bảo đảm Hibernate gom mọi truy vấn thành một SQL. Nó có thể khiến ứng dụng tải quá nhiều dữ liệu và vẫn phát sinh nhiều truy vấn. Tối ưu nên bắt đầu từ từng use case và tập dữ liệu thực tế.

### “Filter tenant đã bật thì mọi con đường đọc/ghi đều được cách ly”

Filter là cơ chế ORM theo ngữ cảnh session, không thay thế kiểm tra quyền và cách ly dữ liệu. Native SQL, thao tác truy cập theo khóa và các luồng xử lý ngoài ORM phải được đánh giá riêng. Thiết kế nhiều tenant cần kiểm soát xuyên suốt từ xác thực đến database.

### “Có `@SoftDelete` thì có ngay hệ thống thùng rác/khôi phục”

Xóa mềm chỉ là một phần của nghiệp vụ. Khôi phục bản ghi, quan hệ dữ liệu, tính duy nhất của business key, dữ liệu ẩn trong báo cáo và cơ chế dọn dữ liệu vẫn phải được thiết kế rõ ràng.

### “Hibernate hỗ trợ nhiều database nên mọi thứ đều portable”

Một entity dùng `@Column` đơn giản thường dễ di chuyển hơn entity sử dụng `@Formula` chứa hàm SQL riêng, cột JSON với biểu thức đặc thù hoặc native query. Cần đánh giá riêng ba yếu tố: **API/provider**, **schema/dialect**, **ngữ nghĩa nghiệp vụ**.

## 11. Tình huống thực hành: bổ sung phần mở rộng có kiểm soát

Giả sử hệ thống quản lý đơn hàng đang dùng `EntityManager` và cần thêm ba chức năng:

**Yêu cầu A: tìm sản phẩm theo `sku`.** Trước hết, tạo unique constraint cho cột `sku` và truy vấn bằng JPQL. Nếu nhu cầu tra cứu natural key lặp lại nhiều và Hibernate đang là provider cố định, cân nhắc `@NaturalId` cùng API truy xuất tương ứng. Cần đo xem phần mở rộng có giúp ích thật không.

**Yêu cầu B: lọc danh sách đơn hàng theo tenant.** Một giải pháp đơn giản là điều kiện `where o.tenantId = :tenantId` trong từng repository. Nếu hệ thống chọn `@Filter`, phải có nơi bật filter đúng cho mỗi session và integration test xác nhận tất cả lối truy cập nhạy cảm. Không cho phép request tùy ý quyết định tenant của mình.

**Yêu cầu C: lưu thuộc tính sản phẩm linh hoạt dưới dạng JSON.** Xem xét `@JdbcTypeCode(SqlTypes.JSON)` và quy định rõ database hỗ trợ, mapping Java, index, migration, cách kiểm tra dữ liệu và chiến lược tìm kiếm. Nếu thuộc tính cần ràng buộc quan hệ hoặc truy vấn phức tạp, mô hình bảng quan hệ có thể thích hợp hơn.

Ba ví dụ cho thấy một quy trình quyết định chung:

```text
Yêu cầu nghiệp vụ
      |
      v
JPA/JPQL tiêu chuẩn có diễn đạt tốt không?
      |                         |
     Có                       Chưa
      |                         |
  Ưu tiên chuẩn       Xem phần mở rộng Hibernate
                                |
                                v
                     Kiểm tra phiên bản + dialect
                                |
                                v
                     Đo lường và integration test
                                |
                                v
                     Gói phụ thuộc ở tầng phù hợp
```

## 12. Ghi nhớ và tài liệu đọc tiếp

Hibernate đóng **hai vai trò đồng thời**: (1) thực thi hợp đồng Jakarta Persistence và (2) cung cấp bộ công cụ ORM riêng vượt ra ngoài hợp đồng đó. Vì vậy, câu hỏi quan trọng không phải “nên dùng JPA hay Hibernate?” theo kiểu chọn một trong hai. Một ứng dụng hoàn toàn có thể **viết qua JPA và chạy bằng Hibernate**, rồi chỉ dùng extension Hibernate ở những nơi nó có giá trị.

Khi gặp một tính năng mới, hãy xác định nó thuộc `jakarta.persistence.*` hay `org.hibernate.*`, hiểu hành vi trong transaction/persistence context, kiểm tra phiên bản hỗ trợ và mức độ phụ thuộc database. Cách tiếp cận này giúp ứng dụng vừa tận dụng được Hibernate, vừa giữ được cấu trúc dễ hiểu và có thể thay đổi.

Tài liệu chính thức để tra cứu hành vi theo phiên bản:

- [Jakarta Persistence — đặc tả và phiên bản](https://jakarta.ee/specifications/persistence/).
- [Hibernate ORM User Guide 7.1](https://docs.hibernate.org/orm/7.1/userguide/html_single/): mapping, query, fetching, session, caching và các phần mở rộng.
- [Hibernate ORM 7.1 Introduction](https://docs.hibernate.org/orm/7.1/introduction/html_single/): tổng quan JPA, Hibernate, session và transaction.
- [Hibernate ORM Javadocs 7.1](https://docs.hibernate.org/orm/7.1/javadocs/): chữ ký API và ngữ nghĩa của các lớp, annotation cụ thể.

> **Lưu ý về phiên bản:** các ví dụ ưu tiên Jakarta Persistence và Hibernate ORM hiện đại; một số API/annotation (`createSelectionQuery`, `@JdbcTypeCode`, `@SoftDelete`, tính năng `StatelessSession`) không tồn tại hoặc có hành vi khác trên các bản Hibernate cũ. Luôn đối chiếu tài liệu và dependency thực tế của dự án trước khi sao chép vào production.
