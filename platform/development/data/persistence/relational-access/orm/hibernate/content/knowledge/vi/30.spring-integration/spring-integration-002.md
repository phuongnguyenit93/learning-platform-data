# EntityManager được liên kết với giao dịch và cách truy cập Session bằng unwrap

## 1. Mục tiêu và bối cảnh

Khi làm việc với Hibernate ORM trong một ứng dụng Spring, code thường có dạng:

~~~java
@Service
public class ProductService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void changePrice(Long id, BigDecimal price) {
        Product product = entityManager.find(Product.class, id);
        product.changePrice(price);
    }
}
~~~

Không thấy lời gọi `entityManager.getTransaction().begin()`, `commit()` hoặc `close()`. Nhưng Hibernate vẫn có thể ghi dữ liệu khi transaction kết thúc.

Điều đó không phải vì Spring “bỏ qua” giao dịch. Ngược lại, Spring **liên kết một EntityManager/persistence context với phạm vi giao dịch** và phối hợp Hibernate qua `PlatformTransactionManager`. Đối tượng được inject bằng `@PersistenceContext` trong mô hình điển hình là một **proxy** đại diện cho EntityManager phù hợp với ngữ cảnh hiện tại, thay vì một EntityManager duy nhất dùng chung cho mọi request.

Khi một ứng dụng cần API đặc thù Hibernate (chẳng hạn `SelectionQuery`, `MutationQuery`, `Session.setJdbcBatchSize()`, filter hoặc JDBC work), có thể lấy Hibernate `Session` đang đứng sau EntityManager:

~~~java
Session session = entityManager.unwrap(Session.class);
~~~

Điểm quan trọng nhất: **`unwrap(Session.class)` không phải lệnh mở transaction mới, không phải lệnh mở một Session độc lập và không làm Session an toàn để giữ qua nhiều request/thread.** Nó cung cấp quyền truy cập API native của Hibernate từ EntityManager đang được quản lý trong ngữ cảnh thích hợp.

Bài học giúp bạn:

1. Hiểu `EntityManager`, `Session`, persistence context, transaction và JDBC Connection khác nhau thế nào.
2. Biết Spring quản lý EntityManager qua `@PersistenceContext` và `@Transactional`.
3. Hiểu một proxy EntityManager được dùng qua nhiều lời gọi nhưng target thay đổi theo transaction/thread.
4. Sử dụng `entityManager.unwrap(Session.class)` đúng thời điểm và đúng phạm vi.
5. Dùng các Hibernate APIs đặc thù mà không tự đóng/commit tài nguyên của Spring.
6. Xử lý propagation, read-only, flush, lazy loading, OSIV và các trường hợp không có transaction.
7. Tránh lỗi session dùng sai thread, self-invocation và transaction chưa được kích hoạt.
8. Viết integration tests chứng minh entity/Session thực sự tham gia transaction.

**Ngữ cảnh phiên bản:** ví dụ dùng Spring Framework/Spring Data JPA hiện đại, Hibernate ORM 6.x và Jakarta Persistence (`jakarta.persistence.*`). Với các ứng dụng Spring Boot 2/Hibernate 5 cũ, có thể gặp namespace `javax.persistence.*` và các API Hibernate khác; dùng Javadoc và migration guide đúng phiên bản project.

## 2. Năm khái niệm dễ bị nhầm lẫn

### 2.1. EntityManager: API JPA chuẩn

`jakarta.persistence.EntityManager` cung cấp các thao tác như:

- `persist(entity)`: đưa entity mới vào persistence context.
- `find(Entity.class, id)`: tìm entity theo identity.
- `merge(detachedEntity)`: sao chép trạng thái detached entity vào một managed instance.
- `remove(managedEntity)`: đánh dấu xóa một managed entity.
- `createQuery(...)`, `createNativeQuery(...)`: thực thi truy vấn.
- `flush()`, `clear()`, `refresh()`, `detach()`: quản lý state.
- `unwrap(Class<T>)`: truy cập interface đặc thù provider nếu được hỗ trợ.

EntityManager thuộc đặc tả Jakarta Persistence nên code dựa trên nó có thể portable hơn giữa các JPA provider.

### 2.2. Hibernate Session: API native

`org.hibernate.Session` là API của Hibernate. Trong Hibernate ORM, một EntityManager thực tế thường được Hibernate Session triển khai hoặc được một wrapper/proxy đại diện.

Session có nhiều chức năng tương đương JPA:

~~~java
Product product = session.find(Product.class, id);
session.persist(product);
session.remove(product);
~~~

và một số khả năng Hibernate-specific:

~~~java
SelectionQuery<Product> query =
    session.createSelectionQuery(
        "select p from Product p where p.active = true",
        Product.class
    );

List<Product> products = query.getResultList();
~~~

Vì `Session` thuộc Hibernate, code phụ thuộc trực tiếp vào nó không còn độc lập với JPA provider.

### 2.3. Persistence context: vùng quản lý entity

Persistence context giữ identity map, managed entities và trạng thái dùng cho dirty checking. Trong một context, các lần `find` cùng identity thường trả cùng object:

~~~java
Product a = entityManager.find(Product.class, 42L);
Product b = entityManager.find(Product.class, 42L);

assert a == b;
~~~

Nếu entity có thay đổi trong context và transaction phù hợp, Hibernate có thể phát sinh UPDATE khi flush. Context có thể có dữ liệu chưa được flush xuống database; nó không phải transaction log và cũng không phải second-level cache dùng chung giữa Session.

### 2.4. Transaction: ranh giới nhất quán của nghiệp vụ

Spring `@Transactional` xác định giao dịch logic của một method/use case. Tùy cấu hình, `JpaTransactionManager` hoặc `JtaTransactionManager` phối hợp begin/commit/rollback và tài nguyên liên quan.

Một transaction có thể thực hiện nhiều SQL statements; một `flush()` chưa đồng nghĩa commit. Transaction boundary là nơi ứng dụng quyết định atomicity và cách xử lý lỗi.

### 2.5. JDBC Connection: kết nối với database

Hibernate Session tương tác với database qua JDBC connections. **Không nên đồng nhất một EntityManager với một physical connection cố định trong mọi thời điểm**: cách acquire/release connection phụ thuộc connection handling mode, transaction, Hibernate version và pool.

Trong một transaction phù hợp, Spring/Hibernate thường phối hợp JDBC operations trên resource tương ứng; tuy vậy, nếu sử dụng nhiều DataSources hoặc transaction managers, phải xác nhận chúng thực sự chia sẻ cùng transaction.

### 2.6. Bảng tóm lược

| Thành phần | Vai trò | Ai quản lý trong mô hình Spring JPA thường gặp? |
|---|---|---|
| `EntityManagerFactory` | Tạo EntityManagers, provider bootstrap | Spring bean do auto-configuration/config quản lý |
| `EntityManager` | API JPA và persistence context | Spring transaction + shared proxy, target theo scope |
| `Session` | Hibernate-native API tới persistence context | Hibernate; vòng đời gắn với EntityManager/transaction |
| Persistence context (L1) | Managed entities, identity, dirty checking | EntityManager/Session |
| `PlatformTransactionManager` | Begin/commit/rollback, bind/unbind resources | Spring |
| `DataSource` / JDBC Connection | Kết nối và truy vấn DB | Pool/transaction manager/Hibernate |
| Second-level cache | Optional shared entity/collection cache | SessionFactory/cache provider, không phải L1 |

## 3. Spring liên kết EntityManager với giao dịch như thế nào?

### 3.1. Luồng xử lý điển hình

~~~text
HTTP Request / Scheduler / Message Consumer
                        |
                        v
         Gọi ProductService.changePrice(...)
                        |
                        v
            Spring transaction proxy
                        |
             @Transactional boundary
                        |
                        v
             JpaTransactionManager
          begin/join transaction phù hợp
                        |
                        v
        Bind EntityManager-related resource
        vào ngữ cảnh transaction/thread
                        |
                        v
           Shared EntityManager proxy
           (@PersistenceContext field)
                        |
                        v
          EntityManager đích hiện hành
                        |
                        v
            Hibernate Session
                        |
                        v
           Persistence context (L1)
                        |
                        v
                 JDBC / Database
                        |
                        v
      flush (khi phù hợp) + commit/rollback
                        |
                        v
         Cleanup/unbind transaction resources
~~~

Đây là luồng khái niệm cho **Spring imperative transactions**. Không dùng sơ đồ này để suy ra thread-bound EntityManager hoạt động y nguyên trong stack Reactive/R2DBC hoặc khi code tự mở `new Thread(...)`.

### 3.2. Vì sao @PersistenceContext thường là một proxy?

Với Spring, trường:

~~~java
@PersistenceContext
private EntityManager entityManager;
~~~

thường được Spring xử lý bởi `PersistenceAnnotationBeanPostProcessor`; đối tượng inject trong **transaction-scoped persistence context** điển hình là một *shared EntityManager proxy*.

Proxy này:
- Định tuyến lời gọi sang EntityManager đang liên kết với transaction hiện tại nếu có.
- Nếu không có transactional EntityManager phù hợp, một số hoạt động có thể dùng EntityManager tạm cho một lời gọi, tùy semantics Spring/operation.
- Ngăn một số thao tác lifecycle/transaction control không hợp lệ trên proxy.
- Cho phép singleton service bean dùng field EntityManager mà không phải chia sẻ một EntityManager target duy nhất giữa mọi request.

**Phân biệt field proxy và EntityManager thực:** bean service singleton có thể giữ proxy lâu dài; actual EntityManager/Session target thường không được giữ lâu dài và không thread-safe.

### 3.3. Cùng một proxy, target theo giao dịch

~~~text
ProductService singleton
    entityManager field = SharedEntityManager proxy
                          |
     Transaction A -------+----> EntityManager A --> Session A
                          |
     Transaction B -------+----> EntityManager B --> Session B
                          |
     Transaction C -------+----> EntityManager C --> Session C
~~~

Do đó:

~~~java
private final EntityManager entityManager;
~~~

trong một service được Spring quản lý không tự có nghĩa ba transactions dùng chung một persistence context. Tuy nhiên, **nếu bạn tự tạo EntityManager bằng `entityManagerFactory.createEntityManager()` rồi lưu vào singleton field**, bạn đã thay đổi mô hình; nó không tự trở thành shared transaction-scoped proxy.

### 3.4. Vai trò của JpaTransactionManager

Trong ứng dụng dùng JPA resource-local transactions, `org.springframework.orm.jpa.JpaTransactionManager` thường là transaction manager phù hợp. Nó tích hợp Spring transaction management với EntityManagerFactory và có khả năng expose JDBC Connection cho DataSource tương ứng theo cấu hình.

Trong môi trường Jakarta EE/JTA, có thể dùng `JtaTransactionManager` để phối hợp distributed/container transactions. **Không mặc định cả hai transaction managers hoặc hai DataSources có cùng atomicity.**

### 3.5. @Transactional thực hiện điều gì?

~~~java
@Service
public class ProductService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void rename(Long productId, String nextName) {
        Product product = em.find(Product.class, productId);
        product.rename(nextName);
    }
}
~~~

Khi `rename(...)` được gọi qua Spring proxy và transaction manager phù hợp:

1. Transaction được bắt đầu hoặc method tham gia transaction hiện tại theo propagation.
2. EntityManager target được liên kết với giao dịch.
3. `find` trả managed Product hoặc null nếu không có row.
4. Method thay đổi object qua domain method.
5. Tại flush/commit, Hibernate có thể phát UPDATE qua dirty checking.
6. Transaction commit hoặc rollback theo policy.
7. Spring cleanup và unbind resources khi kết thúc phạm vi.

Code không cần gọi `em.getTransaction().begin()` hay `em.close()`.

### 3.6. Không có @Transactional có thể đọc được nhưng không có cùng bảo đảm

Một read-only `find` chạy ngoài `@Transactional` có thể vẫn được Spring proxy thực thi qua EntityManager tạm thời. Nhưng:
- Không có transaction boundary nghiệp vụ rõ ràng.
- Context có thể đóng sau một lời gọi; lazy associations có thể không còn truy cập được.
- Nhiều repository calls có thể không chia sẻ cùng một persistence context/snapshot.
- `persist`/`flush`/`remove` cần transaction phù hợp và có thể ném `TransactionRequiredException`.
- Nếu OSIV hoặc transaction khác đã mở context, behavior có thể khác.

Vì vậy, **đừng suy luận “find chạy được ngoài @Transactional thì update cũng chắc chắn chạy đúng”.** Đặt transaction boundary theo use case.

## 4. Cấu hình Spring Boot + Spring Data JPA + Hibernate

### 4.1. Dependencies cơ bản

Một ứng dụng Spring Boot hỗ trợ JPA có thể dùng starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Đây là ví dụ Gradle build snippet; version của dependencies thường được Spring Boot dependency management/BOM điều phối. Không nên tự ghép một Hibernate version không tương thích với Spring Boot/Jakarta Persistence version của dự án.

### 4.2. application.properties minh họa

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=catalog_app
spring.datasource.password=\${CATALOG_DB_PASSWORD}

spring.jpa.hibernate.ddl-auto=validate
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.open-in-view=false
~~~

Đây là cấu hình mẫu, không phải thông tin kết nối thật. Việc bật `ddl-auto=validate` yêu cầu schema đã được migration tạo đúng. Trong production, thường sử dụng Flyway/Liquibase hoặc migration process riêng thay vì để Hibernate thay đổi DDL tùy ý.

Spring Boot auto-configuration sẽ tạo các infrastructure beans khi dependencies, DataSource và conditions phù hợp; trong dự án có nhiều EntityManagerFactories, cần cấu hình beans và qualifiers chính xác.

### 4.3. Định nghĩa Entity đơn giản

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    @Version
    private long version;

    protected Product() {}

    public Long getId() { return id; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public boolean isActive() { return active; }
    public long getVersion() { return version; }

    public void rename(String nextName) {
        if (nextName == null || nextName.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        this.name = nextName;
    }

    public void changePrice(BigDecimal nextPrice) {
        if (nextPrice == null || nextPrice.signum() < 0) {
            throw new IllegalArgumentException("Price must be >= 0");
        }
        this.price = nextPrice;
    }

    public void deactivate() {
        this.active = false;
    }
}
~~~

Ví dụ dùng PostgreSQL/sequence-compatible database; với MySQL và IDENTITY generator có thể cần mapping khác. Phần entity cố ý đơn giản để tập trung transaction/Session.

### 4.4. Service dùng JPA thuần

~~~java
package com.example.catalog;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;

@Service
public class ProductService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void changePrice(Long productId, BigDecimal nextPrice) {
        Product product = entityManager.find(
            Product.class, productId
        );

        if (product == null) {
            throw new IllegalArgumentException("Product not found");
        }

        product.changePrice(nextPrice);
        // Không cần gọi update/merge khi product đang managed.
    }
}
~~~

**Điểm then chốt:** object đã managed được Hibernate theo dõi. Spring transaction boundary khiến flush/commit diễn ra theo policy. Một setter/domain method **không** tức thì đồng nghĩa SQL UPDATE đã chạy.

### 4.5. Transaction boundary ở service thay vì controller

Một cách tổ chức điển hình:

~~~text
Controller / API Handler
         |
         v
 ProductApplicationService  @Transactional
         |
         v
Repository / EntityManager
         |
         v
 Hibernate Session / JDBC
~~~

Service diễn đạt một use case: nhiều repository calls có thể tham gia cùng transaction. Controller nên nhận/trả DTO và không phụ thuộc entity vẫn còn managed để JSON serialization kích hoạt lazy loading.
+## 5. Lấy Hibernate Session qua EntityManager.unwrap(Session.class)

### 5.1. Cú pháp chuẩn

~~~java
import jakarta.persistence.EntityManager;
import org.hibernate.Session;

Session session = entityManager.unwrap(Session.class);
~~~

`unwrap(Class<T>)` là method chuẩn JPA để lấy interface implementation-specific từ EntityManager. `Session.class` là kiểu của Hibernate. Khi JPA provider là Hibernate và implementation hỗ trợ unwrap, method cho phép truy cập native API.

Nếu JPA provider khác Hibernate, `unwrap(Session.class)` không có contract portable; provider có thể ném `PersistenceException` (hoặc exception theo đường proxy/provider). Vì vậy chỉ dùng ở tầng code chủ ý phụ thuộc Hibernate.

### 5.2. Tại sao không ép kiểu trực tiếp?

Không nên làm:

~~~java
Session session = (Session) entityManager;
~~~

Trong ứng dụng Spring, `entityManager` được inject thường là **shared EntityManager proxy**, không phải object trực tiếp implement Hibernate Session. Cast có thể ném `ClassCastException` dù provider bên dưới là Hibernate.

Đúng:

~~~java
Session session = entityManager.unwrap(Session.class);
~~~

`unwrap` đi qua giao diện JPA và cho phép proxy/provider xử lý cách lấy implementation tương ứng.

### 5.3. Unwrap không tạo một transaction mới

~~~java
@Transactional
public void process() {
    Session session = entityManager.unwrap(Session.class);

    // Cùng ngữ cảnh transaction/persistence context
    // mà EntityManager hiện hành đang đại diện.
    Product product = session.find(Product.class, 42L);
    product.deactivate();
}
~~~

Khi method được Spring transaction proxy gọi đúng cách, Session được unwrap là Hibernate Session gắn với EntityManager target của giao dịch/ngữ cảnh hiện tại.

Một số đặc điểm:
- Không cần gọi `session.beginTransaction()`.
- Không cần gọi `session.getTransaction().commit()`.
- Không được gọi `session.close()` chỉ để đóng tài nguyên vừa unwrap.
- Không lưu Session vào field singleton hoặc chuyển sang thread khác.
- Mọi thay đổi entity cần tuân thủ transaction boundary do Spring quản lý.

Nếu một service truyền Session reference ra ngoài và sử dụng sau khi transaction kết thúc, Session có thể đã đóng hoặc không còn ở persistence context như method ban đầu kỳ vọng.

### 5.4. Ví dụ repository chỉ dùng Session khi cần

~~~java
package com.example.catalog;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.hibernate.Session;
import org.hibernate.query.SelectionQuery;
import org.springframework.stereotype.Repository;
import java.util.List;

@Repository
public class HibernateProductReader {

    @PersistenceContext
    private EntityManager entityManager;

    public List<Product> findActiveProducts() {
        Session session = entityManager.unwrap(Session.class);

        SelectionQuery<Product> query =
            session.createSelectionQuery(
                """
                select p
                from Product p
                where p.active = true
                order by p.id
                """,
                Product.class
            );

        return query.getResultList();
    }
}
~~~

Repository trên **không tự tạo transaction**. Nó nên được gọi từ application service có `@Transactional(readOnly = true)`, ví dụ:

~~~java
@Service
public class CatalogQueryService {

    private final HibernateProductReader reader;

    public CatalogQueryService(HibernateProductReader reader) {
        this.reader = reader;
    }

    @Transactional(readOnly = true)
    public List<Product> loadActiveProducts() {
        return reader.findActiveProducts();
    }
}
~~~

Trong API thật, thường nên chuyển entity sang DTO trong transaction, tránh trả entity graph chưa được khởi tạo tới tầng web.

### 5.5. Unwrap bên trong transaction, không phải trong constructor

Không nên làm:

~~~java
@Service
public class BadProductService {

    private final Session session;

    public BadProductService(EntityManager entityManager) {
        this.session = entityManager.unwrap(Session.class);
    }

    // Session được giữ suốt vòng đời singleton bean: sai hướng.
}
~~~

Constructor bean thường chạy khi Spring bootstrap context, **không** nằm trong transaction xử lý request. Nếu proxy có thể tạo EntityManager tạm để phục vụ unwrap, Session lấy được cũng không an toàn để giữ làm field lâu dài.

Nên giữ:

~~~java
@Service
public class GoodProductService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void process(Long id) {
        Session session = entityManager.unwrap(Session.class);
        Product product = session.find(Product.class, id);
        // ...
    }
}
~~~

**Quy tắc:** inject proxy `EntityManager` vào bean; unwrap `Session` **tại nơi cần dùng**, trong phạm vi transaction/use case.

## 6. EntityManager và Session được unwrap có cùng managed state không?

### 6.1. Một persistence context chung

Trong transaction đang dùng một EntityManager target, các API JPA và Hibernate native của cùng target truy cập một persistence context:

~~~java
@Transactional
public void inspectIdentity(Long id) {
    Product viaJpa = entityManager.find(Product.class, id);

    Session session = entityManager.unwrap(Session.class);
    Product viaHibernate = session.find(Product.class, id);

    if (viaJpa != viaHibernate) {
        throw new IllegalStateException("Unexpected context boundary");
    }
}
~~~

Với cùng entity type/identifier và context, hai biến sẽ tham chiếu cùng managed Java instance. Đây là biểu hiện của identity map, không phải vì `Session` và `EntityManager` là hai “bản sao” được đồng bộ bằng một service riêng.

### 6.2. Mutation ở Session được Hibernate dirty-check như JPA

~~~java
@Transactional
public void update(Long id) {
    Product product = entityManager.find(Product.class, id);

    Session session = entityManager.unwrap(Session.class);

    Product same = session.find(Product.class, id);
    same.changePrice(new BigDecimal("49.90"));

    // JPA find và Hibernate find cùng nhìn state managed hiện tại.
    // Hibernate flush trước/ở commit theo flush mode và transaction.
}
~~~

Không cần `entityManager.merge(same)` nếu `same` đã managed trong cùng persistence context.

### 6.3. Flush qua Session và EntityManager

~~~java
@Transactional
public void apply(Long id) {
    Product p = entityManager.find(Product.class, id);
    p.deactivate();

    Session session = entityManager.unwrap(Session.class);
    session.flush();
}
~~~

`session.flush()` và `entityManager.flush()` đều điều khiển flush của context tương ứng; nó đưa pending SQL xuống transaction, **không commit transaction**.

Không gọi flush sau mỗi setter khi không có lý do; điều đó có thể phá cơ hội JDBC batching và tạo nhiều database round trips. Dùng explicit flush khi nghiệp vụ cần phát hiện constraint sớm hoặc một native SQL sau đó phải đọc pending state.

### 6.4. Clear/refresh cũng có phạm vi context chung

~~~java
@Transactional
public void reload(Long id) {
    Product product = entityManager.find(Product.class, id);
    Session session = entityManager.unwrap(Session.class);

    session.refresh(product);

    // Refresh object managed trong cùng context.
}
~~~

`session.clear()` hoặc `entityManager.clear()` sẽ detach managed entities trong persistence context tương ứng, **không chỉ những object được load bằng API Session**.

Vì vậy một repository Hibernate-native gọi `session.clear()` có thể ảnh hưởng các managed entities đã được nạp trước đó qua Spring Data JPA repository trong cùng transaction.

## 7. Ví dụ Hibernate SelectionQuery: truy vấn có kiểu

### 7.1. JPQL qua EntityManager

Với câu truy vấn thuộc chuẩn JPQL:

~~~java
List<Product> products = entityManager.createQuery(
    """
    select p
    from Product p
    where p.active = true
    order by p.name, p.id
    """,
    Product.class
).getResultList();
~~~

Cách này không cần unwrap. Nếu chỉ cần JPQL standard, nên ưu tiên `EntityManager` hoặc Spring Data repository.

### 7.2. HQL qua Session.createSelectionQuery

Khi muốn dùng API rõ mục đích của Hibernate:

~~~java
Session session = entityManager.unwrap(Session.class);

SelectionQuery<Product> query =
    session.createSelectionQuery(
        "from Product p where p.active = :active order by p.id",
        Product.class
    );

List<Product> products = query
    .setParameter("active", true)
    .getResultList();
~~~

`SelectionQuery<T>` là Hibernate-specific, phổ biến trong Hibernate 6. Nó biểu đạt query đọc, không phải bulk mutation. Kết quả `Product` là managed entities nếu được load trong persistence context.

### 7.3. Trả DTO thay vì entity graph

~~~java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductCard(
    Long id,
    String name,
    BigDecimal price
) {}
~~~

~~~java
@Transactional(readOnly = true)
public List<ProductCard> cards() {
    Session session = entityManager.unwrap(Session.class);

    return session.createSelectionQuery(
        """
        select new com.example.catalog.ProductCard(
            p.id, p.name, p.price
        )
        from Product p
        where p.active = true
        order by p.name, p.id
        """,
        ProductCard.class
    ).getResultList();
}
~~~

DTO constructor projection trả object không phải entity managed. Khi application chỉ cần dữ liệu cho API response, đây có thể là lựa chọn ít memory/dirty-checking hơn so với load entities và truy cập lazy graph.

### 7.4. Bind parameter, không nối input người dùng vào HQL

~~~java
SelectionQuery<Product> query = session.createSelectionQuery(
    "from Product p where p.price >= :minPrice",
    Product.class
);

List<Product> products = query
    .setParameter("minPrice", new BigDecimal("20.00"))
    .getResultList();
~~~

Không ghép trực tiếp giá trị người dùng vào query string. Tên field/ORDER BY động nên được xây từ allowlist do ứng dụng kiểm soát.

### 7.5. Pagination

~~~java
List<Product> page = session.createSelectionQuery(
    "from Product p where p.active = true order by p.id",
    Product.class
)
.setFirstResult(offset)
.setMaxResults(pageSize)
.getResultList();
~~~

Với tập dữ liệu lớn, OFFSET cao có thể chậm; cân nhắc keyset pagination với predicate phù hợp. Không dùng pagination tùy tiện kết hợp collection fetch join vì Hibernate/DB có thể phải xử lý nhiều rows và giới hạn ở memory.

### 7.6. Read-only query và flush mode

~~~java
SelectionQuery<Product> query = session.createSelectionQuery(
    "from Product p where p.active = true",
    Product.class
);

query.setReadOnly(true);

List<Product> products = query.getResultList();
~~~

`setReadOnly(true)` là Hibernate hint cho entity results theo contract version. Nó có thể giảm dirty checking cho entities được load qua query nhưng không biến kết quả thành DTO, không đổi transaction thành DB read-only tuyệt đối và không đảm bảo những entities đã managed trước đó sẽ tự chuyển trạng thái.

## 8. Ví dụ Hibernate MutationQuery: cập nhật hàng loạt

### 8.1. JPQL bulk UPDATE

Với EntityManager chuẩn:

~~~java
@Transactional
public int deactivateExpensive(BigDecimal threshold) {
    return entityManager.createQuery(
        """
        update Product p
        set p.active = false
        where p.price > :threshold
        """
    )
    .setParameter("threshold", threshold)
    .executeUpdate();
}
~~~

Không cần `unwrap` nếu chỉ cần một câu bulk JPQL bình thường.

### 8.2. Hibernate MutationQuery

~~~java
import org.hibernate.query.MutationQuery;

@Transactional
public int deactivateExpensiveHibernate(BigDecimal threshold) {
    Session session = entityManager.unwrap(Session.class);

    MutationQuery query = session.createMutationQuery(
        """
        update Product p
        set p.active = false
        where p.price > :threshold
        """
    );

    return query
        .setParameter("threshold", threshold)
        .executeUpdate();
}
~~~

`MutationQuery` biểu đạt bulk mutation; `executeUpdate()` trả số entity/row bị ảnh hưởng theo provider semantics.

### 8.3. Bulk DML không đồng bộ tất cả managed objects

~~~java
@Transactional
public void demonstrateStaleState(Long id) {
    Product product = entityManager.find(Product.class, id);

    Session session = entityManager.unwrap(Session.class);
    session.createMutationQuery(
        "update Product p set p.active = false where p.id = :id"
    )
    .setParameter("id", id)
    .executeUpdate();

    // Product đang managed có thể vẫn giữ active=true.
    entityManager.refresh(product);
}
~~~

Điều này đúng về mặt nguy cơ cho cả `EntityManager.createQuery(...).executeUpdate()` và `Session.createMutationQuery(...)`. Bulk DML không có cùng semantics với load entity → gọi domain method → flush.

Khi nhiều managed entities bị ảnh hưởng và không cần giữ object graph hiện tại, có thể flush những local pending changes cần giữ, thực thi bulk DML rồi `clear()`. Nhưng `clear()` detach **toàn bộ** context, không chỉ những Product vừa UPDATE.

### 8.4. Đừng gọi mutation ngoài transaction

Bulk HQL/JPQL UPDATE/DELETE cần transaction phù hợp. Không có transaction, có thể gặp `TransactionRequiredException` hoặc lỗi tương đương.

`unwrap(Session.class)` không khắc phục thiếu `@Transactional`:

~~~java
public void badUpdate() {
    Session session = entityManager.unwrap(Session.class);

    session.createMutationQuery(
        "update Product p set p.active = false"
    ).executeUpdate();  // Không có transaction boundary bảo đảm.
}
~~~

Sửa bằng cách tạo transaction boundary hợp lệ ở service được Spring proxy gọi; không tự `session.beginTransaction()` trên Session do Spring quản lý.

## 9. Ví dụ dùng Hibernate Session-specific APIs

`unwrap` hữu ích khi chức năng không có counterpart chuẩn JPA hoặc muốn dùng API Hibernate có contract rõ hơn.

### 9.1. Tinh chỉnh JDBC batch size ở cấp Session

~~~java
@Transactional
public void importProducts(List<ProductInput> rows) {
    Session session = entityManager.unwrap(Session.class);

    Integer previous = session.getJdbcBatchSize();
    try {
        session.setJdbcBatchSize(25);

        for (ProductInput input : rows) {
            entityManager.persist(Product.from(input));
        }

        entityManager.flush();
    } finally {
        session.setJdbcBatchSize(previous);
    }
}
~~~

Đây là ví dụ định hướng, giả định `Product.from(input)` đã được triển khai với identifier generator cho phép batching. Cần xét memory/flush-clear interval, transaction size và mapping. `setJdbcBatchSize` chỉ điều chỉnh kích thước batch của Session; nó không biến Hibernate IDENTITY inserts thành batch hiệu quả nếu generator không hỗ trợ.

Trong Hibernate versions có `getJdbcBatchSize()/setJdbcBatchSize(Integer)`, `null` thường mang ý nghĩa dùng cấu hình SessionFactory; cần xác nhận exact signature/semantics theo version.

### 9.2. Hibernate Filter theo Session

~~~java
@Transactional(readOnly = true)
public List<Product> loadTenantProducts(Long tenantId) {
    Session session = entityManager.unwrap(Session.class);

    session.enableFilter("tenantFilter")
        .setParameter("tenantId", tenantId);

    try {
        return session.createSelectionQuery(
            "from Product p order by p.id",
            Product.class
        ).getResultList();
    } finally {
        session.disableFilter("tenantFilter");
    }
}
~~~

Ví dụ giả định entity đã khai báo filter definition/mapping phù hợp, ví dụ `@FilterDef` và `@Filter`. `enableFilter` tác động tới Session hiện hành, không phải một cài đặt toàn ứng dụng.

Tuy nhiên, Hibernate filters không phải security isolation hoàn hảo cho mọi cách truy cập: direct ID fetch, native SQL, bulk DML và special associations có behavior/giới hạn riêng theo Hibernate version. Với multi-tenancy có yêu cầu bảo mật nghiêm ngặt, kết hợp tenant predicate, schema/DB isolation và kiểm thử đường truy cập; không chỉ dựa vào một filter.

### 9.3. Hibernate NativeQuery và query spaces

~~~java
@Transactional(readOnly = true)
public long countProductsNative() {
    Session session = entityManager.unwrap(Session.class);

    Object value = session.createNativeQuery(
        "select count(*) from products"
    )
    .addSynchronizedEntityClass(Product.class)
    .getSingleResult();

    return ((Number) value).longValue();
}
~~~

`addSynchronizedEntityClass(Product.class)` khai báo entity/query spaces liên quan, giúp Hibernate quyết định auto-flush/cache synchronization theo version/API. Nó **không** tự refresh các Product objects đã managed sau native DML.

### 9.4. Session.doWork cho JDBC trực tiếp

~~~java
@Transactional
public void callDatabaseStatement(Long id) {
    Session session = entityManager.unwrap(Session.class);

    entityManager.flush(); // Nếu JDBC SQL cần thấy pending changes.

    session.doWork(connection -> {
        try (PreparedStatement ps = connection.prepareStatement(
            """
            update products
            set active = false, version = version + 1
            where id = ?
            """
        )) {
            ps.setLong(1, id);
            ps.executeUpdate();
        }
    });

    // Nếu Product tương ứng đã managed, state có thể stale;
    // refresh/clear tùy phạm vi và điều kiện nghiệp vụ.
}
~~~

Hibernate cung cấp connection theo transaction/session handling. **Không đóng, commit hoặc rollback connection này trong callback**; chỉ đóng `PreparedStatement`/`ResultSet` do code tạo. Để Spring transaction manager xử lý transaction.

### 9.5. Không lạm dụng Hibernate-specific APIs

Nếu use case chỉ cần:

~~~java
Product product = entityManager.find(Product.class, id);
~~~

thì `Session session = entityManager.unwrap(Session.class)` không tạo lợi ích rõ rệt. Một codebase có thể giữ phần lớn repositories theo JPA/Spring Data và cô lập những câu truy vấn/filter/batching đặc biệt trong adapter Hibernate-specific.

~~~text
Application Service
        |
        +--> Spring Data JpaRepository / EntityManager (portable JPA)
        |
        +--> Hibernate-specific adapter (unwrap Session)
                        |
                        v
                  Hibernate Session
~~~

Cách này giảm phụ thuộc vendor và làm nơi cần kiểm tra khi upgrade Hibernate dễ xác định hơn.
+## 10. Propagation quyết định transaction nào đang được sử dụng

### 10.1. Propagation.REQUIRED: mặc định

~~~java
@Transactional
public void processOrder(Long productId) {
    productRepository.doSomething(productId);
    productAuditRepository.record(...);
}
~~~

Nếu các repository/service bên trong không yêu cầu propagation khác, chúng thường tham gia transaction hiện tại do `Propagation.REQUIRED`.

Điều này có nghĩa trong một request, chúng có thể cùng dùng transaction-bound EntityManager/persistence context và cùng nhìn những managed entities đã nạp. Unwrap từ các thành phần đang gọi trong cùng transaction sẽ truy cập Hibernate Session của context liên quan, không tự mở Session riêng cho từng method.

### 10.2. Propagation.REQUIRES_NEW: transaction độc lập

~~~java
@Service
public class AuditService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAudit(AuditEvent event) {
        em.persist(event);
    }
}
~~~

Khi gọi qua **một Spring proxy khác** từ method đã có transaction:
- Spring thường suspend transaction/resource của caller.
- Tạo một physical transaction mới với EntityManager/session resource phù hợp.
- Commit/rollback audit transaction độc lập.
- Resume transaction của caller.

Session được unwrap trong `AuditService.recordAudit` **không nhất thiết là cùng Hibernate Session** với caller, dù cả hai class đều inject EntityManager từ cùng EntityManagerFactory.

~~~text
Transaction A (Product Service)
  EntityManager A --> Session A
        |
        | gọi AuditService qua Spring proxy
        v
   SUSPEND Transaction A
        |
        v
Transaction B (REQUIRES_NEW)
  EntityManager B --> Session B
        |
      COMMIT B
        |
        v
   RESUME Transaction A
~~~

### 10.3. Cảnh báo về connection pool khi dùng REQUIRES_NEW

Transaction B có thể cần connection mới trong khi transaction A còn giữ connection. Nếu nhiều threads đồng thời chờ REQUIRES_NEW và pool chỉ vừa đủ số threads, có nguy cơ thiếu connection hoặc deadlock do tranh tài nguyên.

Không chọn REQUIRES_NEW cho mọi helper method chỉ để “cho chắc có transaction”. Dùng khi nghiệp vụ thực sự yêu cầu commit/rollback độc lập, và cấu hình pool/phạm vi gọi phù hợp.

### 10.4. Propagation.SUPPORTS

Với `SUPPORTS`, method tham gia transaction đang có; nếu không có transaction, nó có thể chạy **không có transaction nghiệp vụ**. Khi ấy không được mặc định Hibernate Session unwrap có vòng đời và lazy loading giống lúc được gọi từ REQUIRED transaction.

### 10.5. Propagation.MANDATORY

`MANDATORY` yêu cầu caller đã có transaction. Nếu không, Spring có thể từ chối lời gọi ngay trước khi vào method. Đây là lựa chọn có thể dùng cho các repository adapter mà contract yêu cầu được gọi trong use case transaction:

~~~java
@Transactional(propagation = Propagation.MANDATORY)
public List<Product> loadWithSession() {
    Session session = entityManager.unwrap(Session.class);
    return session.createSelectionQuery(
        "from Product",
        Product.class
    ).getResultList();
}
~~~

Mô hình này giúp phát hiện gọi sai boundary nhưng ràng buộc adapter với Spring transaction model.

### 10.6. Propagation.NESTED không đồng nghĩa Session mới

`NESTED` dùng nested transaction/savepoint khi transaction manager và database hỗ trợ. Với JPA, khả năng nested semantics có giới hạn; `JpaTransactionManager` không mặc định hỗ trợ nested transactions cho persistence context và nested rollback không tự rewind Java managed entity state.

Đừng coi NESTED là một cách an toàn để có Session độc lập trong cùng outer transaction. Nếu cần rollback từng phase, phải hiểu transaction manager/JDBC savepoints và cách resynchronize persistence context.

### 10.7. NOT_SUPPORTED / NEVER

`NOT_SUPPORTED` yêu cầu chạy ngoài transaction; nó có thể suspend transaction hiện tại. `NEVER` từ chối nếu caller đang có transaction. Trong những phạm vi này, unwrap và entity operations có thể không có transaction-bound target như bạn kỳ vọng.

**Kết luận:** phương thức Java có cùng annotation `@PersistenceContext` không chắc luôn nhận cùng persistence context; propagation và transaction boundary mới quyết định tài nguyên được tham chiếu.

## 11. @Transactional không tự hoạt động trong mọi lời gọi

### 11.1. Self-invocation: gọi method nội bộ trong cùng bean

Ví dụ:

~~~java
@Service
public class ProductService {

    public void run() {
        updatePrice(42L); // this.updatePrice(...): lời gọi nội bộ.
    }

    @Transactional
    public void updatePrice(Long id) {
        // ...
    }
}
~~~

Với Spring proxy-based transaction management thông thường, `run()` gọi `updatePrice()` bằng `this` không đi qua transaction proxy. Vì vậy `@Transactional` trên `updatePrice()` **có thể không được kích hoạt** khi chỉ được gọi bằng đường nội bộ này.

Hậu quả:
- Không có transaction như code tưởng.
- `EntityManager.flush()` hoặc bulk DML có thể ném `TransactionRequiredException`.
- `unwrap(Session.class)` không làm transaction xuất hiện.
- EntityManager có thể hoạt động với target tạm có vòng đời không phù hợp.

**Giải pháp cấu trúc**: đặt method transactional trong service khác được inject, hoặc đặt transaction boundary ở public entrypoint được Spring proxy gọi. AspectJ transaction weaving có semantics khác proxy-based mode, nhưng không mặc định được bật.

### 11.2. Tự khởi tạo service bằng new

Không đúng:

~~~java
ProductService service = new ProductService();
service.updatePrice(42L);
~~~

Object này không được Spring quản lý; `@PersistenceContext` và `@Transactional` không được xử lý như bean Spring. Nếu service cần dependency injection và AOP, lấy bean thông qua DI/IoC thay vì tự `new`.

### 11.3. @Transactional trên private method

Một private method không thể được external caller gọi qua Spring proxy theo cách thông thường. Đặt `@Transactional` chỉ trên private helper rồi mong tự tạo transaction là không phù hợp với proxy-based transaction management.

Trong Spring các version mới có nuances với package-private/protected methods và class-based proxies, nhưng quy tắc đáng tin cậy là **đặt transaction boundary trên method service được proxy intercept**, không dựa vào self-invocation hoặc private method.

### 11.4. Checked exception và rollback policy

Theo default của Spring transaction management, unchecked `RuntimeException` và `Error` thường làm transaction rollback; checked exceptions không tự rollback trừ khi cấu hình phù hợp.

~~~java
@Transactional(rollbackFor = IOException.class)
public void importCsv(...) throws IOException {
    // ...
}
~~~

Nếu code catch exception và không rethrow, transaction interceptor có thể xem method kết thúc bình thường và commit. Khi cần rollback có thể rethrow hoặc đánh dấu rollback theo cơ chế Spring phù hợp.

### 11.5. Rollback-only khi inner operation thất bại

Một transaction có thể bị đánh dấu rollback-only do lỗi từ repository/service bên trong. Dù outer method catch exception rồi trả bình thường, lúc commit Spring có thể ném `UnexpectedRollbackException` vì transaction đã bị đánh dấu không thể commit.

Không thử “cứu” một Hibernate Session đã rơi vào trạng thái lỗi SQL bằng cách tiếp tục query/flush không kiểm soát. Cần rollback use case hoặc tạo retry trong transaction/session mới khi thích hợp.

### 11.6. Transaction được xác định bởi đường gọi thực

Một test đơn giản có thể quan sát:

~~~java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
~~~

Method này thuộc `org.springframework.transaction.support.TransactionSynchronizationManager` và phản ánh trạng thái Spring transaction tại thread hiện tại. Nó giúp chẩn đoán, nhưng `true` không tự chứng minh EntityManager và một DataSource cụ thể đang cùng một transaction, nhất là ứng dụng có nhiều transaction managers.

## 12. Không truyền EntityManager/Session qua thread hoặc async boundary

### 12.1. Session không thread-safe

Hibernate `Session` và JPA `EntityManager` **không an toàn để chia sẻ đồng thời giữa nhiều threads**. Nó quản lý mutable persistence context, entity snapshots, flush state và JDBC interaction.

Không làm:

~~~java
@Transactional
public void wrongParallelAccess(List<Long> ids) {
    Session session = entityManager.unwrap(Session.class);

    ids.parallelStream().forEach(id -> {
        Product p = session.find(Product.class, id);
        // Sai: nhiều worker threads cùng truy cập Session.
    });
}
~~~

Cũng không đưa Session vào field static, cache, HTTP session, CompletableFuture hoặc một singleton worker để dùng sau.

### 12.2. @Async thay đổi thread

~~~java
@Service
public class BackgroundWorker {

    @Async
    public CompletableFuture<Void> process(Long productId) {
        // Ở thread khác, transaction/context của caller
        // không mặc định được kế thừa.
        return CompletableFuture.completedFuture(null);
    }
}
~~~

Spring imperative transaction context thường gắn với thread thực thi. `@Async` chạy trên thread khác, nên không mặc định kế thừa transaction-bound EntityManager từ caller.

Nếu async job cần DB transaction, đặt `@Transactional` trên method chạy qua Spring proxy **trong thread async đó** hoặc dùng TransactionTemplate/transaction manager đúng nơi. Không truyền `Session` hoặc managed entity rồi mong lazy loading/dirty checking vẫn hoạt động.

### 12.3. Truyền IDs/DTO, không truyền Session

Một cách phù hợp:

~~~text
Request Transaction A
    |
    +--> Validate input
    +--> Publish job with productId
    +--> Commit
                    |
                    v
             Async Worker
                    |
             @Transactional
                    |
             Load Product by ID
                    |
             Apply updates
                    |
             Commit
~~~

Worker tự tạo/nhận transaction và persistence context phù hợp trong thread của nó. Các yêu cầu xử lý sau commit, idempotency, message retry và eventual consistency phải được quyết định theo hệ thống, không chỉ bằng một annotation.

### 12.4. Reactive stack là mô hình khác

Spring WebFlux/R2DBC và Reactive Transactions có cơ chế context propagation khác với imperative thread-bound transaction model. `EntityManager` và Hibernate ORM Session thông thường là blocking APIs. Không giả định chúng tham gia reactive transaction bằng cách gọi `unwrap` bên trong một Reactor `Mono/Flux`.

Nếu phải dùng JPA trong ứng dụng web reactive, cần quản lý blocking execution và transaction ở boundary riêng phù hợp. Hibernate Reactive dùng `Mutiny.Session`/reactive APIs khác, không phải `org.hibernate.Session` thông thường được unwrap từ JPA EntityManager.

## 13. Lazy loading, transaction boundary và Open EntityManager in View

### 13.1. LazyInitializationException sau khi context đóng

Entity có lazy association:

~~~java
@Entity
public class Category {
    @Id
    private Long id;

    @OneToMany(mappedBy = "category", fetch = FetchType.LAZY)
    private List<Product> products;
}
~~~

Service:

~~~java
@Transactional(readOnly = true)
public Category loadCategory(Long id) {
    return entityManager.find(Category.class, id);
}
~~~

Nếu controller nhận Category rồi gọi `category.getProducts().size()` **sau khi transaction và EntityManager đã đóng**, Hibernate có thể ném `LazyInitializationException`.

`unwrap(Session.class)` trong service không biến lazy association thành eager và không giữ Session tồn tại sau khi service trả về.

### 13.2. Tải đủ dữ liệu trong transaction

Có thể dùng fetch join:

~~~java
@Transactional(readOnly = true)
public CategoryDetails getCategoryDetails(Long id) {
    Session session = entityManager.unwrap(Session.class);

    Category category = session.createSelectionQuery(
        """
        select c
        from Category c
        left join fetch c.products
        where c.id = :id
        """,
        Category.class
    )
    .setParameter("id", id)
    .getSingleResult();

    List<ProductCard> cards = category.getProducts().stream()
        .map(p -> new ProductCard(
            p.getId(), p.getName(), p.getPrice()
        ))
        .toList();

    return new CategoryDetails(category.getId(), cards);
}
~~~

Giả định `CategoryDetails` là DTO được định nghĩa tương ứng; khi database không có Category, `getSingleResult()` có thể ném exception cần xử lý. Collection fetch join có thể tạo nhiều SQL rows và không nên dùng bừa với pagination.

Một cách khác là DTO projection, entity graph hoặc hai queries theo parent page.

### 13.3. Open EntityManager in View (OSIV)

Trong Spring web applications, **Open EntityManager in View** có thể giữ EntityManager mở xuyên suốt vòng đời request, bao gồm giai đoạn controller/view serialization sau khi service transaction đã kết thúc.

Điều này đôi khi làm lazy access ngoài service transaction vẫn chạy, nhưng có các rủi ro:
- SQL được kích hoạt ở view/serialization layer không rõ ràng.
- N+1 queries do truy cập association từng object.
- Database reads nằm ngoài transaction service, có thể có isolation/snapshot khác.
- EntityManager còn mở không có nghĩa còn một transaction nghiệp vụ thống nhất.
- Khó kiểm soát query count và hiệu năng.

Cấu hình mẫu để tắt OSIV trong Spring Boot:

~~~properties
spring.jpa.open-in-view=false
~~~

Không dựa vào “request vẫn chạy được với lazy loading” để khẳng định transaction boundary đúng. Tốt hơn là fetch dữ liệu cần thiết bên trong service transaction rồi trả DTO.

### 13.4. Session còn open ≠ transaction đang active

Ngay cả nếu OSIV giữ EntityManager/Session mở, `@Transactional` của service có thể đã kết thúc. Hibernate Session còn truy cập được không đồng nghĩa bulk write được bảo vệ trong cùng transaction hoặc mọi lazy load đều thấy cùng snapshot.

Đây là phân biệt quan trọng khi debug: **session lifecycle** và **transaction lifecycle** có thể không trùng tuyệt đối trong mọi cấu hình.

## 14. @Transactional(readOnly = true) và Hibernate flush modes

### 14.1. Read-only là ý định, không phải hàng rào tuyệt đối

~~~java
@Transactional(readOnly = true)
public List<ProductCard> listCards() {
    // Read-only query / DTO projection.
}
~~~

Spring có thể dùng read-only flag làm hint cho transaction manager/JDBC connection và với Hibernate có thể điều chỉnh `FlushMode`/default read-only settings. Tùy Spring/Hibernate version, các tối ưu này làm giảm flush/dirty checking.

**Không coi `readOnly=true` là bảo đảm mọi database sẽ cấm ghi**. Để áp dụng bảo vệ mạnh, dùng DB permissions/read-only transactions được DB hỗ trợ và thiết kế API riêng cho read/write.

### 14.2. Không sửa entity trong readOnly transaction rồi mặc định UPDATE sẽ được commit

~~~java
@Transactional(readOnly = true)
public void wrongWrite(Long id) {
    Product p = entityManager.find(Product.class, id);
    p.deactivate();
}
~~~

Nếu Spring/Hibernate đặt flush mode không tự flush trong transaction read-only, thay đổi có thể không được ghi. Nhưng behavior phụ thuộc provider/config; nếu có explicit SQL write thì DB có thể vẫn nhận, trừ khi transaction/read-only DB enforcement từ chối.

**Lựa chọn đúng:** operations ghi phải có transaction ghi rõ ràng; không dùng `readOnly=true` cho use case sửa state.

### 14.3. FlushModeType.AUTO và COMMIT

JPA có `FlushModeType.AUTO` và `FlushModeType.COMMIT`:

~~~java
entityManager.setFlushMode(FlushModeType.AUTO);
~~~

Trong mode AUTO, provider bảo đảm query results phản ánh phù hợp pending updates ảnh hưởng đến query theo contract; trong COMMIT, query visibility với pending changes trước commit có thể khác và cần xem specification.

Hibernate cũng có flush modes riêng như `AUTO`, `COMMIT`, `MANUAL`, `ALWAYS` theo version/API; đừng cho rằng enum JPA và Hibernate luôn có từng giá trị tương đương.

Khi unwrap Session rồi thay đổi flush mode:

~~~java
Session session = entityManager.unwrap(Session.class);
FlushMode previous = session.getHibernateFlushMode();

try {
    session.setHibernateFlushMode(FlushMode.MANUAL);
    // Đọc/ghi có chủ đích...
} finally {
    session.setHibernateFlushMode(previous);
}
~~~

hãy hiểu rằng đây là cấu hình **trên Session đang tham gia transaction hiện tại**, không phải một setting cô lập cho một query. Nếu quên restore, caller/repository khác dùng cùng Session có thể có flush behavior khác mong đợi, dẫn tới mất update hoặc query không thấy pending state.

**Không set MANUAL tùy tiện để tối ưu hiệu năng**; trước hết dùng `@Transactional(readOnly = true)`, DTO projections và query options với contract rõ ràng.

### 14.4. Explicit flush không phải commit

~~~java
@Transactional
public void updateAndInspect(Long id) {
    Product p = entityManager.find(Product.class, id);
    p.deactivate();

    entityManager.flush(); // SQL đã gửi DB nhưng chưa commit.

    // Các SQL tiếp theo trong cùng transaction có thể
    // dựa trên kết quả vừa được flush.
}
~~~

Nếu sau đó transaction rollback, những SQL đã flush cũng rollback theo DB transaction semantics. Không dùng flush để “commit một phần” của transaction.

## 15. Không tự quản lý vòng đời Hibernate Session đã unwrap

### 15.1. Những lời gọi nên tránh trên Session của Spring

~~~java
@Transactional
public void badLifecycle() {
    Session session = entityManager.unwrap(Session.class);

    // Sai hướng cho managed Session:
    session.beginTransaction();
    session.getTransaction().commit();
    session.close();
}
~~~

Lý do:
- Spring đã sở hữu transaction boundary.
- Commit thủ công có thể phá transaction state đang được proxy/manager theo dõi.
- Close thủ công làm caller/repositories sau đó không dùng được context.
- Trong JTA, transaction semantics còn khác resource-local.

Không tự mở/đóng tài nguyên do framework sở hữu. Nếu cần transaction thủ công trong một standalone Java SE program, cách đó thuộc mô hình khác.

### 15.2. Không nhầm unwrap với SessionFactory.openSession

~~~java
Session session = entityManager.unwrap(Session.class);
~~~

khác với:

~~~java
Session session = sessionFactory.openSession();
~~~

`openSession()` tạo một Hibernate Session mới, có persistence context riêng và vòng đời riêng. Nó **không tự** tham gia transaction hiện tại chỉ vì được gọi bên trong một Spring `@Transactional` method.

Nếu code tự mở Session, nó phải quản lý transaction/connection/cleanup đúng theo mô hình tích hợp tương ứng. Với Spring JPA, thông thường nên dùng EntityManager proxy đã được inject và unwrap khi cần, thay vì mở Session mới gây hai contexts và state divergence.

### 15.3. SessionFactory.getCurrentSession cũng không tự tương đương trong mọi cấu hình

Hibernate có `SessionFactory.getCurrentSession()` khi một `CurrentSessionContext` phù hợp được cấu hình. Trong một số cấu hình native Hibernate/Spring, nó có thể trả current Session theo transaction.

Tuy nhiên, khi ứng dụng dùng Spring Data JPA và `JpaTransactionManager`, **không được mặc định** gọi `sessionFactory.getCurrentSession()` sẽ trả đúng Session mà `@PersistenceContext EntityManager` đang sử dụng. Điều đó phụ thuộc integration/config/version.

Trong một JPA application đã có transaction-bound EntityManager, `em.unwrap(Session.class)` thường là đường ít mơ hồ hơn để lấy Session tương ứng.

### 15.4. Không gọi em.getTransaction() trên container-managed proxy

Trong Java SE thuần, application có thể dùng:

~~~java
EntityManager em = emf.createEntityManager();

EntityTransaction tx = em.getTransaction();
tx.begin();
try {
    // Operations...
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) tx.rollback();
    throw ex;
} finally {
    em.close();
}
~~~

Nhưng đoạn trên là **application-managed EntityManager**; nó khác @PersistenceContext trong Spring-managed JPA.

Trong mô hình Spring declarative transaction, dùng `@Transactional` hoặc `TransactionTemplate`. Gọi `em.getTransaction()` trên shared EntityManager proxy có thể bị Spring từ chối vì giao dịch thuộc transaction manager.

### 15.5. Không dùng một EntityManager cho nhiều requests

`EntityManagerFactory` là đối tượng hạ tầng có thể dùng chung, còn `EntityManager` target không thread-safe. Nếu tự `emf.createEntityManager()`, phải quản lý scope, thread confinement và close; đừng lưu object này vào singleton để dùng qua các HTTP requests.
+## 16. Nhiều EntityManagerFactories và nhiều database

### 16.1. Transaction manager phải khớp persistence unit

Một ứng dụng có thể có:
- `catalogEntityManagerFactory` / `catalogTransactionManager`.
- `billingEntityManagerFactory` / `billingTransactionManager`.

Trong trường hợp này, không thể giả định một `@Transactional` không chỉ định manager sẽ quản lý đúng mọi EntityManager.

~~~text
Catalog service
  @PersistenceContext(unitName="catalogPU")
        |
        v
catalog EntityManagerFactory
        |
        v
catalog JpaTransactionManager
        |
        v
Catalog Database


Billing service
  @PersistenceContext(unitName="billingPU")
        |
        v
billing EntityManagerFactory
        |
        v
billing JpaTransactionManager
        |
        v
Billing Database
~~~

Ví dụ giả định những persistence units/beans đã được cấu hình:

~~~java
@Service
public class CatalogService {

    @PersistenceContext(unitName = "catalogPU")
    private EntityManager catalogEntityManager;

    @Transactional("catalogTransactionManager")
    public void deactivate(Long id) {
        Session session =
            catalogEntityManager.unwrap(Session.class);

        Product product = session.find(Product.class, id);
        if (product == null) {
            throw new IllegalArgumentException("Product missing");
        }
        product.deactivate();
    }
}
~~~

`unitName` xác định persistence unit mà EntityManager proxy đại diện. Tên transaction manager xác định resource mà giao dịch Spring quản lý. **Unwrap không thể sửa một EntityManagerFactory/transaction manager đã được chọn sai.**

### 16.2. Một local transaction không bao trùm hai databases độc lập

~~~java
@Transactional("catalogTransactionManager")
public void updateCatalogAndBilling() {
    // Catalog write...
    // Billing write bằng manager khác...
}
~~~

`JpaTransactionManager` cho Catalog không tự biến Billing DB thành một phần của transaction atomic. Nếu nghiệp vụ cần atomicity xuyên nhiều resource, phải thiết kế JTA/XA khi thích hợp, hoặc saga/outbox/compensation với eventual consistency.

Đừng tin rằng hai repository dùng Hibernate và đều gọi `unwrap(Session.class)` có nghĩa chúng cùng JDBC transaction.

### 16.3. Chọn đúng tenant và data source

Nếu application dùng multi-tenancy, Session tương ứng với tenant/connection/schema được thiết lập bởi provider lúc tạo context. Không truyền Session của tenant A sang một request của tenant B hoặc đổi tenant context giữa cùng Session mà không có thiết kế riêng.

Một Hibernate `@Filter` cho tenant không phải rào bảo mật tự động cho mọi native SQL/direct lookup/bulk operation. Cần kiểm tra tất cả đường truy cập cùng DB isolation policy.

## 17. Transaction-scoped và extended persistence context

### 17.1. Transaction-scoped là lựa chọn phổ biến

~~~java
@PersistenceContext
private EntityManager em;
~~~

Trong mô hình stateless Spring service thông thường, đây là transaction-scoped EntityManager proxy. Target persistence context được phối hợp với transaction; sau khi scope kết thúc và context đóng, entity references có thể detached.

Field proxy an toàn để inject vào singleton Spring bean; target EntityManager/Session không phải một object dùng chung đồng thời giữa requests.

### 17.2. Extended persistence context

JPA hỗ trợ:

~~~java
@PersistenceContext(type = PersistenceContextType.EXTENDED)
private EntityManager extendedEntityManager;
~~~

Extended context có thể sống qua nhiều transactions, phù hợp một số stateful/conversation-scoped components được thiết kế riêng.

Nhưng:
- EntityManager không thread-safe.
- Không inject extended target vô điều kiện vào singleton được gọi đồng thời.
- Managed entities có thể nằm trong memory lâu và stale.
- Việc tham gia transaction/flush có semantics riêng.
- Cần xem Spring/JPA provider guide về hỗ trợ scoped beans.

Với REST/stateless service, transaction-scoped context thường dễ hiểu và dễ bảo trì hơn.

### 17.3. Unsynchronized persistence context

Jakarta Persistence có `SynchronizationType.UNSYNCHRONIZED` cho persistence context không tự join transaction cho tới khi được yêu cầu theo quy tắc JPA. Đó là tính năng nâng cao, không phải mặc định của service `@PersistenceContext` điển hình.

Nếu dự án dùng unsynchronized context, phải hiểu `joinTransaction()` và flush rules trước khi áp dụng các ví dụ transaction-scoped mặc định.

### 17.4. Kiểm tra trạng thái joined

~~~java
@Transactional
public void inspect() {
    boolean joined = entityManager.isJoinedToTransaction();

    if (!joined) {
        throw new IllegalStateException(
            "EntityManager not joined to transaction"
        );
    }
}
~~~

`isJoinedToTransaction()` hữu ích để điều tra, nhưng không thay thế việc xác minh đúng transaction manager/EntityManagerFactory hoặc transaction visibility trên DB.

## 18. Spring Data JpaRepository và EntityManager trong một transaction

Giả sử repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Service:

~~~java
@Service
public class ProductWorkflow {

    private final ProductRepository repository;

    @PersistenceContext
    private EntityManager em;

    public ProductWorkflow(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void process(Long id) {
        Product fromRepo = repository.findById(id)
            .orElseThrow();

        Product fromEm = em.find(Product.class, id);

        if (fromRepo != fromEm) {
            throw new IllegalStateException(
                "Expected the same managed entity"
            );
        }

        Session session = em.unwrap(Session.class);
        Product fromSession = session.find(Product.class, id);

        fromSession.deactivate();
        // Không cần save/merge một entity còn managed
        // chỉ để Hibernate dirty-check ở flush.
    }
}
~~~

Khi repository và EntityManager sử dụng **cùng EntityManagerFactory và persistence context** trong transaction, những lần load cùng entity identity thường trả cùng object.

Nếu propagation tạo transaction mới, repository dùng EMF khác hoặc một đoạn code gọi `clear()/detach()`, identity scope có thể khác. Không suy luận từ việc hai biến Java không giống nhau rằng “Hibernate tạo hai hàng DB”.

### 18.1. Spring Data save không nhất thiết là flush ngay

`JpaRepository.save` thường dùng `persist` hoặc `merge` tùy entity state/newness. Nó không bắt buộc gửi SQL ngay tại thời điểm gọi:

~~~java
@Transactional
public void createAndReadBySql(Product product) {
    repository.save(product);
    em.flush(); // Nếu SQL sau cần đọc pending changes.

    Session session = em.unwrap(Session.class);
    // Native SQL/query...
}
~~~

Với IDENTITY generator, INSERT có thể được thực thi sớm để lấy identifier; với SEQUENCE và generator khác timing có thể khác. Không đồng nhất `save` với `saveAndFlush`.

### 18.2. Một service gọi cả Spring Data và Hibernate-specific adapter

~~~text
CatalogUseCase @Transactional
            |
            +-- ProductRepository (Spring Data JPA)
            |
            +-- HibernateProductReader
                     @PersistenceContext EntityManager
                     unwrap(Session.class)
            |
            v
     Transaction-bound context (nếu cùng EMF)
~~~

Đây là cách tổ chức hợp lệ: hầu hết code dùng API portable, phần nhỏ cần Hibernate-specific đặt trong infrastructure adapter.
+## 19. TransactionTemplate: tạo transaction rõ ràng trong code

`@Transactional` phù hợp hầu hết service methods. Khi cần điều khiển transaction bằng code (ví dụ job worker hoặc method không thể gọi qua transaction proxy), Spring có `TransactionTemplate`.

### 19.1. Ví dụ programmatic transaction

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ProgrammaticProductReader {

    private final TransactionTemplate txTemplate;

    @PersistenceContext
    private EntityManager em;

    public ProgrammaticProductReader(
        PlatformTransactionManager transactionManager
    ) {
        this.txTemplate = new TransactionTemplate(transactionManager);
    }

    public ProductCard loadCard(Long id) {
        return txTemplate.execute(status -> {
            Product product = em.find(Product.class, id);

            if (product == null) {
                return null;
            }

            // Có thể unwrap tại đây nếu cần Hibernate Session.
            Session session = em.unwrap(Session.class);

            return new ProductCard(
                product.getId(), product.getName(), product.getPrice()
            );
        });
    }
}
~~~

Biến `session` minh họa thời điểm unwrap; nếu method chỉ dùng JPA `find`, không cần unwrap. Code giả định Spring inject đúng `PlatformTransactionManager` của EntityManagerFactory này.

### 19.2. Không return Session ra ngoài transaction callback

Sai hướng:

~~~java
Session leaked = txTemplate.execute(
    status -> em.unwrap(Session.class)
);

// Transaction callback kết thúc, Session có thể đã cleanup.
// Không sử dụng leaked ở đây.
~~~

Nên trả DTO, scalar hoặc một kết quả đã được xử lý/materialize trong callback.

### 19.3. TransactionTemplate không biến nhiều databases thành một transaction

Một `TransactionTemplate` dùng transaction manager cụ thể. Nó không phối hợp hai local resources thành XA transaction chỉ bằng việc cùng xuất hiện trong một lambda. Cần cấu hình/resource management đúng nếu workflow chạm nhiều DBs.

## 20. Use case hoàn chỉnh: cập nhật qua JPA và đọc bằng Hibernate

Giả sử API nhận yêu cầu cập nhật giá rồi trả thông tin sản phẩm.

### 20.1. DTO response

~~~java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductCard(
    Long id,
    String name,
    BigDecimal price
) {}
~~~

### 20.2. Application service

~~~java
package com.example.catalog;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.hibernate.Session;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;

@Service
public class CatalogApplicationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public ProductCard updateAndRead(
            Long id,
            BigDecimal nextPrice) {

        Product product = em.find(Product.class, id);
        if (product == null) {
            throw new IllegalArgumentException("Product not found");
        }

        product.changePrice(nextPrice);

        // Flush có chủ đích để SQL của DTO query đọc DB state mới.
        // Không bắt buộc cho mọi service operation.
        em.flush();

        Session session = em.unwrap(Session.class);

        return session.createSelectionQuery(
            """
            select new com.example.catalog.ProductCard(
                p.id, p.name, p.price
            )
            from Product p
            where p.id = :id
            """,
            ProductCard.class
        )
        .setParameter("id", id)
        .getSingleResult();
    }
}
~~~

Cơ chế:
1. Spring intercept method và bắt đầu/join transaction.
2. `em.find` load Product managed trong context.
3. `product.changePrice` thay đổi Java state.
4. `em.flush()` phát SQL pending trong transaction, **không commit**.
5. `em.unwrap(Session.class)` truy cập Session của cùng context.
6. HQL constructor query trả DTO, không cần trả entity managed cho controller.
7. Spring transaction manager quyết định commit/rollback khi method kết thúc.

Flush trong ví dụ có vai trò minh họa rõ thời điểm query phải nhìn pending DB state; trong use case chỉ cần response từ managed Product, có thể dựng DTO trực tiếp từ getter và để flush xảy ra khi commit. Tránh flush sớm vô ích nếu làm giảm batching.

### 20.3. Optimistic locking không biến mất khi unwrap

Nếu Product có `@Version`, Hibernate-managed entity update qua JPA hoặc Session vẫn tham gia version checking theo entity mapping. Nhưng `Session.createMutationQuery(...)` thực hiện bulk mutation và native SQL có semantics khác; không mặc định chúng kiểm tra version từng entity giống entity-level dirty checking.

### 20.4. Adapter Hibernate-specific thay vì lạm dụng unwrap

Một kiến trúc dễ nâng cấp:

~~~text
Controller
    |
    v
CatalogUseCase / Domain Service
    |
    +-- ProductRepository (JPA portable)
    |
    +-- ProductReadPort (application interface)
              |
              v
      HibernateProductReadAdapter
              |
       EntityManager.unwrap(Session.class)
~~~

Đặt những HQL extension/Session-specific APIs trong adapter giúp giảm phụ thuộc provider ở core domain/application layer.

## 21. Debug transaction và Session: checklist theo triệu chứng

Khi code báo lỗi hoặc dữ liệu không đúng, hãy xác định:
- Method có thực sự được gọi qua Spring transaction proxy không?
- Transaction manager có đúng EntityManagerFactory/DataSource không?
- Transaction hiện tại có active/joined không?
- Đã có Session/EntityManager target phù hợp chưa?
- Entity là managed, detached hay new?
- SQL đã flush hay chỉ thay Java state?
- Context/transaction đã đóng chưa?
- Có async/thread switch hoặc propagation mới không?
- Có OSIV/read-only flush policy ảnh hưởng không?

### 21.1. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `TransactionRequiredException` khi flush | Không có transaction active/joined | Đặt `@Transactional` trên entrypoint được proxy gọi; kiểm tra manager |
| `@Transactional` không hoạt động | Self-invocation, tự new bean, proxy không intercept | Gọi qua Spring bean/proxy, thiết kế lại boundary |
| `ClassCastException` khi cast EntityManager sang Session | Injected EM là shared proxy | Dùng `em.unwrap(Session.class)` |
| `PersistenceException` khi unwrap Session | JPA provider không phải Hibernate hoặc không hỗ trợ | Kiểm tra provider và dependency |
| `Session is closed` sau service method | Giữ Session ra ngoài scope hoặc tự close | Unwrap và dùng ngay trong transaction |
| `LazyInitializationException` khi trả entity | Truy cập lazy association khi context đã đóng | Fetch trong transaction, trả DTO |
| Lazy SQL chạy khi serialize JSON | OSIV còn bật hoặc session còn mở | Tắt/đánh giá OSIV, thiết kế DTO/fetch plan |
| Session mới nhưng entity thay đổi chưa thấy | Transaction chưa flush/commit, isolation/cache | Xác nhận commit và context/cache |
| `readOnly=true` mà không thấy UPDATE | Hibernate/Spring flush/read-only semantics | Dùng transaction ghi đúng contract |
| `getTransaction()` bị từ chối | Shared JPA EntityManager do Spring quản lý | Dùng `@Transactional`/`TransactionTemplate` |
| Repository A và EntityManager B không cùng entity object | Khác EMF/context/propagation hoặc đã clear | Kiểm tra persistence unit và transaction |
| `getCurrentSession()` không tìm thấy Session | CurrentSessionContext không được cấu hình phù hợp | Trong Spring JPA ưu tiên `em.unwrap(Session.class)` |
| REQUIRES_NEW gây thiếu connection | Outer transaction giữ connection, inner cần connection khác | Đánh giá pool và propagation |
| Commit outer lỗi `UnexpectedRollbackException` | Inner operation đánh dấu rollback-only | Xem exception gốc và rollback handling |
| `@Async` đọc Session lỗi | Thread không kế thừa transaction/context | Transaction ở worker, truyền IDs/DTO |
| Hibernate Query đổi L1 state không như mong muốn | Bulk DML không sync managed entities | Refresh/clear/context mới có chủ đích |
| Gọi `session.clear()` làm detached objects | Clear ảnh hưởng toàn context, kể cả JPA entities | Cân nhắc refresh/detach hoặc boundary khác |
| Custom flush mode ảnh hưởng repository khác | Đã thay mode trên cùng Session, không restore | Khôi phục trong finally; tránh lạm dụng |
| JDBC SQL không thấy pending changes | Chưa flush hoặc dùng resource/connection khác | Flush có chủ đích, kiểm tra transaction sharing |
| Database B commit dù A rollback | Nhiều transaction managers/resources độc lập | JTA/XA hoặc thiết kế saga/outbox |
| `NoResultException` trên getSingleResult | Không có entity thỏa predicate | Xử lý absence hoặc dùng optional/list method |
| Hibernate API không compile sau upgrade | API/namespace Hibernate 5/6/7 khác | Xem migration guide và imports |
| L1 giữ trạng thái cũ sau native SQL | Native mutation không tự refresh entities | Refresh/clear/context mới |

### 21.2. Kiểm tra transaction hoạt động trong Spring

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Transactional
public void diagnostic() {
    boolean active =
        TransactionSynchronizationManager.isActualTransactionActive();

    boolean joined = entityManager.isJoinedToTransaction();

    Session session = entityManager.unwrap(Session.class);

    System.out.println("springTxActive=" + active);
    System.out.println("entityManagerJoined=" + joined);
    System.out.println("sessionOpen=" + session.isOpen());
}
~~~

Đây là phép chẩn đoán, không nên log session internals hoặc dữ liệu nhạy cảm không cần thiết trong production. `session.isOpen()` không chứng minh transaction đang active; OSIV hoặc những Session scopes khác có thể giữ Session mở ngoài transaction.

### 21.3. Transaction logger và SQL logger

Khi debug, có thể bật các log categories của Spring transaction và Hibernate SQL phù hợp phiên bản:

~~~properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.orm.jpa=DEBUG
logging.level.org.hibernate.SQL=DEBUG
~~~

SQL log có thể hiển thị lệnh thực thi/flush timing, còn Spring transaction log giúp thấy begin/join/commit/rollback. Tránh bật log bind parameters (nhất là PII, giá trị nhạy cảm) trong production khi chưa có quy trình bảo vệ.

## 22. Integration tests: chứng minh cùng context và đúng transaction

### 22.1. Test cùng entity identity qua JPA và Session

Một test với database thật và Spring context:

~~~java
@SpringBootTest
class EntityManagerSessionIntegrationTest {

    @PersistenceContext
    private EntityManager em;

    @Test
    @Transactional
    void jpaAndHibernateSeeSameManagedInstance() {
        Long id = /* ID của Product đã có trong fixture */ 42L;

        Product viaJpa = em.find(Product.class, id);
        assertNotNull(viaJpa);

        Session session = em.unwrap(Session.class);
        Product viaSession = session.find(Product.class, id);

        assertSame(viaJpa, viaSession);
        assertTrue(em.contains(viaJpa));
    }
}
~~~

Ví dụ dùng JUnit 5 assertions và fixture Product#42; import ``@SpringBootTest`, `@Test`, `@Transactional`, `assertSame`, `assertTrue` theo dependencies tương ứng. Test-managed transaction thông thường có thể rollback sau test, nên tránh suy luận rằng test đã xác nhận commit vào database.

### 22.2. Test service được proxy intercept

Một test `@Transactional` bao trùm test method có thể **che giấu lỗi** thiếu `@Transactional` trong service, vì service tự động tham gia transaction test hiện có.

Để kiểm tra service transaction boundary thực sự hoạt động:
1. Gọi bean service qua Spring context.
2. Tránh test-level `@Transactional` bao quanh lời gọi đang cần chứng minh.
3. Cho service thực hiện write.
4. Đọc từ một transaction/EntityManager mới sau khi service trả về.
5. Xác nhận commit/rollback theo contract.

Nếu test cần cô lập database, dùng cleanup fixtures hoặc `TransactionTemplate`/TestTransaction phù hợp; không giả định test rollback tự động bao gồm transaction REQUIRES_NEW do service đã commit.

### 22.3. Test exception rollback

Một use case:

~~~java
@Transactional
public void createAndFail(Product product) {
    entityManager.persist(product);
    throw new IllegalStateException("Force rollback");
}
~~~

Integration test gọi service qua Spring proxy, bắt exception rồi query trong transaction mới để kiểm tra row không được commit. Nếu SQL đã flush trước exception, transaction rollback vẫn phải hoàn tác theo DB semantics.

### 22.4. Test REQUIRES_NEW

Thiết lập một bean A có REQUIRED transaction, một bean B có `REQUIRES_NEW`. Trong test, kiểm tra:
- Khi B commit, thay đổi của B có thể tồn tại dù A rollback (theo thiết kế).
- EntityManager/persistence context của A không tự có cùng managed identities với B.
- Không cần đo object identity `Session` bằng `==` để chứng minh transaction correctness; quan sát SQL/result/rollback cùng context behavior phù hợp hơn.

### 22.5. Test read-only và flush

Một test có thể xác nhận rằng service readOnly không dựa vào entity dirty checking để thực hiện write. Nhưng đừng mặc định mọi driver/DB chặn DML khi readOnly; test phải dựa vào contract dự án, đúng Spring/Hibernate/DB versions.

### 22.6. Test @Async

Cho async worker nhận Product ID, tự load/update trong worker transaction. Không truyền Session/managed entity từ caller. Xác nhận callback/future hoàn tất, transaction commit và không có `LazyInitializationException` do cross-thread access.

### 22.7. Vì sao mock EntityManager không đủ?

Mock có thể trả một `Session` giả cho `unwrap`, nhưng không kiểm chứng:
- Shared EntityManager proxy có target transaction-bound thật không.
- Dirty checking và flush có xảy ra.
- Hibernate Session và JPA EntityManager có chung identity map không.
- Transaction propagation suspend/resume đúng không.
- Lazy loading/OSIV và SQL driver.
- Commit/rollback trên database.

Các behavior này cần integration test với Spring transaction infrastructure, Hibernate provider và database phù hợp.
+## 23. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài 1 — Phân biệt proxy và target EntityManager

Một singleton Spring service có:

~~~java
@PersistenceContext
private EntityManager em;
~~~

**Câu hỏi:** Có phải mọi request sử dụng cùng một EntityManager target không?

**Đáp án:** Không. Trong mô hình transaction-scoped của Spring, field thường là shared EntityManager proxy, định tuyến tới target gắn với transaction/context hiện tại. Chia sẻ proxy không đồng nghĩa chia sẻ một persistence context giữa các requests.

### Bài 2 — Lấy Session

~~~java
Session session = (Session) em;
~~~

**Câu hỏi:** Có nên cast trực tiếp không?

**Đáp án:** Không. Spring có thể inject proxy không implement Session. Dùng `em.unwrap(Session.class)` khi provider là Hibernate.

### Bài 3 — Transaction được mở bởi ai?

Service method có `@Transactional`, code gọi `em.unwrap(Session.class)`.

**Câu hỏi:** Có cần gọi `session.beginTransaction()` và `session.getTransaction().commit()` không?

**Đáp án:** Không trong mô hình Spring-managed transaction. Spring transaction manager sở hữu begin/commit/rollback.

### Bài 4 — @Transactional self-invocation

~~~java
public void run() {
    update(42L);
}

@Transactional
public void update(Long id) {
    // ...
}
~~~

**Câu hỏi:** Proxy transaction có chắc intercept lời gọi `update` từ `run` không?

**Đáp án:** Không với proxy-based Spring AOP thông thường. Tổ chức entrypoint transactional qua một bean/proxy hoặc thiết kế boundary khác.

### Bài 5 — Cùng context giữa JpaRepository và Session

Repository và EntityManager dùng cùng EMF/transaction; cả hai load Product#42.

**Câu hỏi:** Có thể mong đợi cùng Java instance không?

**Đáp án:** Có, nếu entity type/identifier và persistence context là một, theo identity map. Nếu propagation hoặc EMF khác, không áp dụng.

### Bài 6 — Unwrap ngoài transaction

~~~java
public List<Product> findAll() {
    Session session = em.unwrap(Session.class);
    return session.createSelectionQuery(
        "from Product", Product.class
    ).getResultList();
}
~~~

**Câu hỏi:** Có bảo đảm Session được giữ xuyên nhiều lời gọi repository bên ngoài transaction không?

**Đáp án:** Không. Shared EntityManager proxy có thể dùng target tạm hoặc ngữ cảnh khác; cách an toàn là đặt read transaction ở application service và dùng Session trong scope đó.

### Bài 7 — Đóng Session thủ công

Trong method `@Transactional`, developer gọi `session.close()` sau khi query.

**Câu hỏi:** Rủi ro?

**Đáp án:** Session do Spring quản lý có thể bị đóng khi transaction/caller vẫn cần; cleanup phải thuộc framework.

### Bài 8 — Mất UPDATE trong readOnly transaction

~~~java
@Transactional(readOnly = true)
public void changePrice(Long id, BigDecimal value) {
    em.find(Product.class, id).changePrice(value);
}
~~~

**Câu hỏi:** Có nên dựa vào commit để ghi price không?

**Đáp án:** Không. Spring/Hibernate có thể tối ưu read-only bằng thay đổi flush/dirty checking. Đặt transaction ghi đúng mục đích.

### Bài 9 — Flush khác commit

~~~java
em.flush();
~~~

**Câu hỏi:** Transaction khác có chắc thấy dữ liệu vừa flush chưa?

**Đáp án:** Không. Flush gửi pending SQL trong transaction hiện tại; visibility còn phụ thuộc commit/isolation.

### Bài 10 — Bulk HQL và stale managed entity

Service đã load Product#42; `MutationQuery` update `active=false`.

**Câu hỏi:** `product.isActive()` chắc chắn tự trả false không?

**Đáp án:** Không. Bulk DML không cập nhật từng Java managed object; refresh/clear theo phạm vi cần thiết.

### Bài 11 — @Async

Method outer đang trong transaction gọi `@Async` worker và truyền một Hibernate Session.

**Câu hỏi:** Có phù hợp không?

**Đáp án:** Không. Session không thread-safe; transaction context không tự truyền giữa threads. Truyền ID/DTO, mở transaction/EntityManager ở worker.

### Bài 12 — Lazy loading ngoài service

Service trả Product có `@ManyToOne(fetch = LAZY)`, controller truy cập association sau khi EntityManager đã đóng.

**Câu hỏi:** Lỗi có thể gặp?

**Đáp án:** `LazyInitializationException`. Query đủ dữ liệu và chuyển sang DTO trong transaction hoặc thiết kế fetch plan.

### Bài 13 — OSIV

Ứng dụng bật Open EntityManager in View; controller/serializer vẫn lazy-load được dù service transaction đã kết thúc.

**Câu hỏi:** Như vậy tất cả SQL đều trong một transaction nghiệp vụ không?

**Đáp án:** Không. Session/context lifetime có thể dài hơn transaction lifetime, gây lazy SQL ngoài service boundary.

### Bài 14 — REQUIRES_NEW

Transaction A gọi AuditService `REQUIRES_NEW` qua Spring proxy.

**Câu hỏi:** Session unwrap trong B có chắc là Session của A không?

**Đáp án:** Không. B thường có transaction/resource/context riêng; A được suspend và resume.

### Bài 15 — Nhiều databases

`@Transactional("catalogTransactionManager")` nhưng code unwrap từ `@PersistenceContext(unitName="billingPU")`.

**Câu hỏi:** Điều gì cần kiểm tra?

**Đáp án:** Transaction manager có quản lý billing EntityManager/DB không? Unwrap không tự kết nối transaction khác. Chỉ định đúng unit/manager hoặc thiết kế transaction xuyên resources.

### Bài 16 — flush mode bị thay đổi

Một repository gọi `session.setHibernateFlushMode(FlushMode.MANUAL)` và không restore.

**Câu hỏi:** Rủi ro cho repository khác trong cùng transaction?

**Đáp án:** Cùng Session có thể dùng flush mode bất ngờ, làm pending changes không được flush như caller kỳ vọng. Chỉ thay mode khi hiểu contract và restore có chủ đích.

### Bài 17 — SessionFactory.openSession

Developer dùng `sessionFactory.openSession()` trong service `@Transactional` đã inject EntityManager.

**Câu hỏi:** Session mới có tự chia sẻ context với EntityManager không?

**Đáp án:** Không. Nó tạo Session/persistence context riêng, không tự join transaction hiện tại chỉ vì lời gọi nằm bên trong annotated method.

### Bài 18 — Test bị transaction của test che giấu

Một `@SpringBootTest @Transactional` test gọi service thiếu `@Transactional`; mọi thứ vẫn chạy.

**Câu hỏi:** Điều gì đã bị bỏ qua?

**Đáp án:** Test đã tạo transaction từ trước, nên service có thể tham gia transaction test dù production entrypoint không có. Kiểm tra bằng integration test gọi service **ngoài test-managed transaction** và quan sát commit/rollback.

### Bài 19 — JPA portable hay Hibernate-specific?

Nhu cầu chỉ là `find` và JPQL `select`.

**Câu hỏi:** Có cần unwrap Session không?

**Đáp án:** Không. EntityManager/TypedQuery/Spring Data repository là lựa chọn phù hợp hơn nếu không cần API Hibernate-specific.

### Bài 20 — Resource leak

Một service lưu `Session` đã unwrap vào field và dùng lại ở request tiếp theo.

**Câu hỏi:** Vi phạm nguyên tắc nào?

**Đáp án:** Session target là stateful, không thread-safe, vòng đời gắn với transaction/context; chỉ nên giữ shared EntityManager proxy được Spring inject, không giữ Session target qua requests.

### Bài 21 — @Version sau bulk SQL

Entity Product có `@Version`; một native SQL thay price nhưng không cập nhật version.

**Câu hỏi:** Có bảo đảm Hibernate phát hiện mọi lost update không?

**Đáp án:** Không. Native SQL cần tham gia cùng version/locking strategy; đồng thời xử lý stale persistence context.

### Bài 22 — TransactionTemplate

`TransactionTemplate.execute(...)` trả một Session object để dùng về sau.

**Câu hỏi:** Có nên làm vậy không?

**Đáp án:** Không. Scope transaction đã kết thúc; nên xử lý query ngay trong callback và trả kết quả scalar/DTO.

### Bài 23 — @PersistenceContext EXTENDED

Một singleton service dùng `PersistenceContextType.EXTENDED` và bị nhiều requests truy cập đồng thời.

**Câu hỏi:** Rủi ro?

**Đáp án:** Extended EntityManager target không thread-safe; có thể giữ managed state lâu và gây race/stale data. Dùng scope/stateful component thích hợp hoặc transaction-scoped default.

### Bài 24 — Chọn nơi đặt transaction

Workflow vừa đọc Product, vừa đổi giá, vừa lưu audit và trả DTO.

**Câu hỏi:** Nên đặt `@Transactional` trên getter của repository hay application use case?

**Định hướng:** Application service/use-case boundary thường rõ hơn vì diễn đạt một đơn vị nghiệp vụ có atomicity; repository tham gia transaction đó. Nếu audit cần commit độc lập, xác định riêng propagation và failure semantics.

## 24. Tổng kết

### 24.1. Ba điều phải luôn phân biệt

**(1) Injected EntityManager proxy không phải lúc nào cũng là một EntityManager target duy nhất.** Trong transaction-scoped Spring JPA, proxy đại diện target được liên kết với transaction/context hiện tại.

**(2) Session unwrap là một góc nhìn Hibernate-native vào EntityManager target.** Nó không tạo transaction mới, không tự mở persistence context riêng và không trao ownership lifecycle cho caller.

**(3) Transaction boundary không đồng nghĩa Session lifecycle trong mọi cấu hình.** Các trường hợp OSIV, extended persistence context, propagation, async và multi-EMF có những ranh giới riêng.

### 24.2. Lựa chọn API nhanh

| Nhu cầu | Công cụ nên cân nhắc |
|---|---|
| CRUD, JPQL portable | `EntityManager` hoặc Spring Data JPA |
| Unit of work có nhiều repository operations | `@Transactional` ở application service |
| Programmatic transaction rõ ràng | `TransactionTemplate` |
| HQL SelectionQuery/MutationQuery | `em.unwrap(Session.class)` |
| Hibernate filter, JDBC batch override, native query spaces | Hibernate `Session` qua unwrap |
| JDBC cần connection cùng Session | `Session.doWork(...)` với transaction ownership đúng |
| Mở Session độc lập trong Java SE program | `SessionFactory.openSession()` và quản lý toàn vòng đời |
| Read response tránh lazy loading sau transaction | DTO projection/fetch trong transaction |
| Async/background job | Tạo transaction trong worker, truyền IDs/DTO |
| Multi-EMF / multi-DB | Match persistence unit và transaction manager; thiết kế atomicity riêng |

### 24.3. Mẫu code nên nhớ

~~~java
@Service
public class ExampleService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public List<ProductCard> execute() {
        Session session = entityManager.unwrap(Session.class);

        return session.createSelectionQuery(
            """
            select new com.example.catalog.ProductCard(
                p.id, p.name, p.price
            )
            from Product p
            where p.active = true
            order by p.id
            """,
            ProductCard.class
        ).getResultList();
    }
}
~~~

Với mô hình này:
- EntityManager proxy do Spring cung cấp.
- Transaction do Spring kiểm soát.
- Session được unwrap tại nơi sử dụng.
- Không gọi `beginTransaction()`/`commit()`/`close()` trên Session.
- Trả DTO để tránh dựa vào lazy loading sau khi transaction kết thúc.

### 24.4. Danh mục tránh lỗi

- Không cast trực tiếp shared `EntityManager` thành `Session`.
- Không unwrap Session trong constructor rồi giữ ở singleton field.
- Không tự đóng/commit một Session mà Spring đang quản lý.
- Không dựa vào self-invocation để `@Transactional` được proxy intercept.
- Không dùng cùng Session đồng thời ở `@Async`/parallel streams.
- Không cho rằng `readOnly=true` tương đương một DB write lock.
- Không giả định OSIV giữ cùng transaction tới lúc serializer hoàn thành.
- Không kết luận `flush()` tương đương commit.
- Không nhầm Hibernate bulk mutation với dirty checking managed entities.
- Không dùng `openSession()` khi mục tiêu chỉ là tiếp tục transaction-bound context hiện có.
- Không để ứng dụng nhiều EMFs chọn nhầm transaction manager.
- Không trả Session/EntityManager target ra ngoài phạm vi use case.

## Tài liệu chính thức

- [Spring Framework — ORM / JPA](https://docs.spring.io/spring-framework/reference/data-access/orm/jpa.html) — EntityManagerFactory, `@PersistenceContext`, shared EntityManager và transaction integration.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — `@Transactional` và proxy interception.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html) — REQUIRED, REQUIRES_NEW, NESTED.
- [Spring Framework — TransactionTemplate](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html) — programmatic transaction management.
- [Spring Framework — JpaTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html) — JPA transaction resource coordination.
- [Spring Framework — SharedEntityManagerCreator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/jpa/SharedEntityManagerCreator.html) — shared transaction-aware EntityManager proxy.
- [Spring Boot — Data JPA](https://docs.spring.io/spring-boot/reference/data/sql.html#data.sql.jpa-and-spring-data) — JPA auto-configuration/OSIV và Spring Data integration.
- [Hibernate ORM Documentation](https://docs.hibernate.org/orm/) — chọn User Guide/Javadocs theo đúng version.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — Session/persistence context, flushing, HQL, lazy loading và native APIs.
- [Hibernate ORM 6.6 Session Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/Session.html) — native Session API và lifecycle.
- [Hibernate ORM 6.6 SelectionQuery Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/query/SelectionQuery.html) — Hibernate selection queries.
- [Hibernate ORM 6.6 MutationQuery Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/query/MutationQuery.html) — HQL bulk mutations.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — EntityManager, persistence context, `unwrap`, transaction contracts.

> Cơ chế chính áp dụng cho Spring **imperative** transaction management và Hibernate ORM/Jakarta Persistence trên ứng dụng thông thường. Các chi tiết proxy, read-only optimization, OSIV, transaction propagation, native APIs và namespace khác nhau theo Spring/Hibernate version, transaction manager và cấu hình. Trong dự án thật, xác nhận trên đúng dependency versions, database và Spring transaction setup bằng integration tests.





