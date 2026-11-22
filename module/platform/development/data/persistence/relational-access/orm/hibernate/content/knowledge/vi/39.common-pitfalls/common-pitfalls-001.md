# Đồng nhất Hibernate với Jakarta Persistence hoặc Spring Data JPA

Trong một dự án Spring Boot, bạn có thể thấy `@Entity`, `@OneToMany`, `EntityManager`, `Session`, `JpaRepository`, `@Query` và `@Transactional` xuất hiện trong cùng một feature. Vì các thành phần này thường được dùng cạnh nhau, nhiều người gọi tất cả là “Hibernate”, hoặc cho rằng Spring Data JPA chính là Hibernate. Cách gọi đó dễ gây nhầm trách nhiệm, đặc biệt khi chọn dependency, đọc tài liệu, xử lý lỗi, viết query hoặc nâng cấp phiên bản.

Cần phân biệt ba lớp:

1. **Jakarta Persistence** là specification và API chuẩn Java cho object-relational persistence: entity lifecycle, `EntityManager`, mapping annotations, JPQL, Criteria và transaction integration contracts.
2. **Hibernate ORM** là một persistence provider/implementation phổ biến của Jakarta Persistence, đồng thời cung cấp nhiều API và extension riêng như `Session`, HQL extensions, `@Filter`, `@SQLRestriction`, `@SoftDelete` và các cơ chế provider-specific.
3. **Spring Data JPA** là một repository abstraction trong hệ sinh thái Spring. Nó xây dựng repository interfaces, query derivation, projections, specifications và tích hợp transaction/exception translation trên nền Jakarta Persistence provider. Nó thường dùng Hibernate làm provider trong Spring Boot, nhưng không phải chính Hibernate.

~~~text
Application / Service / Domain
          |
          v
Spring Data JPA (optional repository abstraction)
          |
          v
Jakarta Persistence API
  EntityManager / JPQL / Criteria / mappings
          |
          v
Persistence Provider
  Hibernate ORM (or another provider)
          |
          v
JDBC Driver
          |
          v
Relational Database
~~~

**Nguyên tắc cốt lõi:** Specification định nghĩa contract; provider thực thi contract và có thể mở rộng; repository framework cung cấp cách tổ chức truy cập dữ liệu ở cấp ứng dụng. Một API có tên giống nhau hoặc được dùng cùng nhau không có nghĩa chúng thuộc cùng một layer.

> **Phạm vi:** Java 17+, Jakarta Persistence 3.x, Hibernate ORM 6.x, Spring Framework 6.x và Spring Data JPA trong hệ Spring Boot 3.x là bối cảnh minh họa. Các phiên bản cũ có thể dùng `javax.persistence` và các integration APIs khác. Hãy đối chiếu dependency compatibility của đúng Spring Boot/Hibernate/Spring Data release thay vì ghép version tùy ý.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt specification, API, implementation/provider và repository abstraction.
2. Xác định annotation/API nào thuộc Jakarta Persistence, Hibernate hay Spring Data JPA.
3. Hiểu vì sao `EntityManager` không đồng nghĩa với Hibernate `Session`.
4. Phân biệt JPQL chuẩn, HQL của Hibernate và native SQL.
5. Biết `JpaRepository` dựa trên JPA provider chứ không phải một ORM độc lập.
6. Hiểu transaction boundaries khi kết hợp Spring `@Transactional`, repository methods và Hibernate flush/commit.
7. Tránh trộn `javax.persistence` với `jakarta.persistence`.
8. Đọc đúng tài liệu, dependency và version compatibility.
9. Biết lúc nào dùng API chuẩn, lúc nào dùng Hibernate extension hoặc Spring Data feature.
10. Chẩn đoán lỗi ở đúng layer và viết tests phản ánh đúng contract.

## 2. Ba khái niệm không cùng cấp

| Thành phần | Bản chất | Ví dụ tiêu biểu |
|---|---|---|
| Jakarta Persistence | Specification + API chuẩn | `EntityManager`, `@Entity`, JPQL, Criteria |
| Hibernate ORM | Persistence provider + ORM framework | `Session`, HQL, Hibernate annotations, dirty checking implementation |
| Spring Data JPA | Spring repository abstraction | `JpaRepository`, derived queries, `@Query`, projections, Specifications |

Một dự án thường dùng cả ba:

- Source code có thể import `jakarta.persistence.EntityManager`.
- Spring Data JPA tạo repository proxy và gọi persistence infrastructure.
- Hibernate triển khai `EntityManager` và phát SQL qua JDBC.
- Database thực hiện SQL và trả kết quả.

Không có xung đột trong việc sử dụng cả ba; vấn đề là **gán nhầm một behavior cho sai layer**.

## 3. Jakarta Persistence là specification

Jakarta Persistence (trước đây là Java Persistence API/JPA) quy định contract cho persistence trong Java enterprise applications.

Nó định nghĩa các khái niệm như:

- Entity và entity identity.
- Mapping annotations.
- Persistence context.
- `EntityManager` và lifecycle operations.
- JPQL và Criteria API.
- Relationships, cascading và fetch types.
- Locking/versioning.
- Persistence unit/provider integration.
- Một số transaction và cache contracts.

Specification không tự kết nối database hoặc tự thực thi SQL. Ứng dụng cần một **provider** triển khai API đó.

Tài liệu specification mô tả behavior chuẩn mà provider tương thích phải đáp ứng. Nếu một behavior chỉ xuất hiện trong Hibernate Javadocs, không nên gọi nó là “JPA standard” nếu chưa có trong Jakarta Persistence spec.

## 4. Hibernate ORM là persistence provider

Hibernate ORM triển khai Jakarta Persistence interfaces và cung cấp ORM engine.

Nó đảm nhiệm:

- Mapping Java object với relational tables.
- Persistence Context/Session implementation.
- Entity hydration và dirty checking.
- SQL generation theo dialect.
- Flush/action queue.
- JDBC integration.
- Caching integration.
- HQL query engine và các extensions.
- Provider-specific annotations, APIs và events.

Khi dùng Hibernate làm provider, gọi:

~~~java
EntityManager entityManager = ...;
~~~

thường vẫn đang sử dụng Hibernate ở bên dưới nếu persistence unit được cấu hình với Hibernate. Nhưng `EntityManager` là API Jakarta Persistence; nó không trở thành một API Hibernate chỉ vì provider là Hibernate.

## 5. Spring Data JPA là repository abstraction

Spring Data JPA giúp định nghĩa repository interfaces:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    List<Order> findByStatus(OrderStatus status);

    Optional<Order> findByOrderNumber(String orderNumber);
}
~~~

Bạn khai báo method; Spring Data tạo implementation/proxy và sử dụng Jakarta Persistence để thực hiện query.

Spring Data JPA không tự định nghĩa một entity lifecycle thay thế JPA. Nó dựa vào `EntityManager`, persistence provider, transaction manager và database configuration của ứng dụng.

Nếu Hibernate là provider, đường gọi thường có dạng:

~~~text
Controller
  -> Application Service
      -> OrderRepository proxy
          -> Spring Data JPA repository implementation
              -> EntityManager (Jakarta Persistence API)
                  -> Hibernate provider
                      -> JDBC
                          -> Database
~~~

## 6. Tên “JPA” trong Spring Data JPA không có nghĩa provider là Hibernate

Spring Data JPA được thiết kế quanh Jakarta Persistence. Provider có thể là Hibernate hoặc một implementation tương thích khác, tùy cấu hình và dependency.

Do đó:

- `JpaRepository` không phải `HibernateRepository`.
- `@Query` của Spring Data JPA không phải annotation Hibernate.
- `EntityManager` không phải `Session`.
- Một query JPQL hợp lệ theo specification nên có portability tốt hơn HQL-specific query.
- Một Hibernate extension có thể được dùng trong ứng dụng Spring Data JPA, nhưng đó là lựa chọn provider-specific.

Nếu đổi provider, các phần dựa vào Hibernate-specific behavior có thể cần thay đổi; repository abstraction không xóa khác biệt giữa providers.

## 7. Ví dụ dependency trong Spring Boot

Trong Spring Boot 3.x, dependency thường được khai báo qua starter:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

Starter Data JPA kéo các thành phần cần thiết của Spring Data JPA và một provider mặc định theo dependency management của Spring Boot, thường là Hibernate ORM.

Không nên tự thêm một Hibernate version ngẫu nhiên chỉ vì muốn “dùng Hibernate mới”. Spring Boot BOM quản lý bộ version tương thích. Nếu override provider version, cần xác minh Spring Data, Jakarta Persistence API, bytecode enhancement, dialect và driver tương thích.

Với Maven, nguyên tắc tương tự: dùng parent/BOM của Spring Boot và chỉ override version khi có lý do cùng ma trận kiểm chứng.

## 8. Tại sao không nên ghép version tùy tiện?

Một runtime có nhiều dependency liên quan:

~~~text
Spring Boot
  |
  +-- Spring Framework
  +-- Spring Data JPA
  +-- Jakarta Persistence API
  +-- Hibernate ORM
  +-- Hibernate bytecode/enhancement components
  +-- JDBC driver
  +-- Transaction manager
~~~

Một version mismatch có thể gây:

- `NoSuchMethodError`.
- `ClassNotFoundException`.
- `NoClassDefFoundError`.
- Linkage errors.
- Annotation/API không tồn tại.
- Behavior khác giữa compile time và runtime.
- Boot auto-configuration không tương thích.

Khi gặp lỗi, xem dependency tree và BOM trước khi thêm một JAR thủ công. Đừng sửa lỗi bằng cách kéo thêm một phiên bản `jakarta.persistence-api` tùy ý vào runtime nếu provider đã quản lý dependency đó.

## 9. javax.persistence và jakarta.persistence

Trước Jakarta EE 9, JPA API dùng package:

~~~java
import javax.persistence.Entity;
import javax.persistence.EntityManager;
~~~

Từ Jakarta Persistence, package chuyển thành:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.EntityManager;
~~~

Đây là thay đổi namespace lớn trong hệ sinh thái Java EE/Jakarta EE. Nó không chỉ là đổi tên một dependency; bytecode references và libraries phải tương thích với namespace tương ứng.

Bối cảnh thường gặp:

| Stack | Namespace thường dùng |
|---|---|
| Spring Boot 2.x + Hibernate 5.x | `javax.persistence` |
| Spring Boot 3.x + Hibernate 6.x | `jakarta.persistence` |
| Spring Boot 4.x / stack mới hơn | Theo Jakarta namespace và compatibility matrix tương ứng |

Bảng là định hướng lịch sử/phổ biến, không thay release notes của từng version. Hibernate 5.6 có các artifacts/biến thể Jakarta trong giai đoạn chuyển tiếp; không gom mọi Hibernate 5.x thành một quy tắc tuyệt đối.

## 10. Không trộn hai namespace trong cùng persistence model

Sai lầm:

~~~java
import javax.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Customer {
    @Id
    private Long id;
}
~~~

Các annotations có thể là hai class khác nhau dù tên đơn giản giống nhau. Provider có thể không nhận diện mapping như mong đợi hoặc runtime có lỗi tương thích.

Khi migrate:

1. Chọn một stack version tương thích.
2. Đổi imports nhất quán.
3. Nâng các thư viện tích hợp cùng namespace.
4. Kiểm tra validation/provider/transaction APIs.
5. Chạy compile và integration tests trên database thực tế.
6. Không giữ song song hai persistence APIs chỉ để “cho compile qua” nếu runtime không hỗ trợ.

## 11. Annotation nào thuộc Jakarta Persistence?

Ví dụ các annotations chuẩn:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import jakarta.persistence.Id;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Column;
import jakarta.persistence.OneToMany;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.FetchType;
import jakarta.persistence.CascadeType;
import jakarta.persistence.Version;
import jakarta.persistence.Enumerated;
import jakarta.persistence.EnumType;
~~~

Các annotations này mô tả mapping và lifecycle theo specification.

Ví dụ:

~~~java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String orderNumber;

    @Version
    private long version;
}
~~~

Hibernate là provider thực thi mapping đó, nhưng annotation contract thuộc Jakarta Persistence.

## 12. Annotation nào thuộc Hibernate?

Một số ví dụ provider-specific:

~~~java
import org.hibernate.annotations.Filter;
import org.hibernate.annotations.FilterDef;
import org.hibernate.annotations.SQLRestriction;
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.SoftDelete;
import org.hibernate.annotations.BatchSize;
import org.hibernate.annotations.Formula;
~~~

Các annotation này mở rộng khả năng mapping/query của Hibernate và không tự động portable sang provider khác.

Ví dụ:

~~~java
@Entity
@SQLRestriction("deleted = false")
public class Document {
    @Id
    private Long id;
}
~~~

`@SQLRestriction` là Hibernate-specific; một JPA provider khác không bắt buộc hiểu annotation này.

Nếu application dùng extension, hãy ghi nhận provider requirement trong architecture/dependency docs và test khi nâng Hibernate.

## 13. Annotation nào thuộc Spring Data JPA?

Ví dụ:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.domain.Specification;
~~~

`@Query` ở đây là Spring Data JPA annotation, dù nội dung chuỗi thường là JPQL:

~~~java
@Query("""
    select o
    from Order o
    where o.status = :status
    """)
List<Order> findOrders(@Param("status") OrderStatus status);
~~~

Spring Data đọc annotation, tạo query thông qua persistence infrastructure, và Hibernate thực thi nếu là provider.

Không nhầm `org.springframework.data.jpa.repository.Query` với HQL engine API hoặc Jakarta Persistence `Query` interface.

## 14. EntityManager và Session

Jakarta Persistence:

~~~java
EntityManager entityManager;
~~~

Hibernate:

~~~java
Session session;
~~~

`EntityManager` là interface chuẩn. Hibernate `Session` là API native của Hibernate và cung cấp các chức năng tương ứng cùng nhiều extension.

Khi dùng Hibernate provider, có thể unwrap:

~~~java
Session session = entityManager.unwrap(Session.class);
~~~

Hoặc kiểm tra provider-specific access qua API phù hợp. `unwrap()` là cách explicit để chuyển từ abstraction sang provider API.

Không cast trực tiếp implementation class nội bộ của Hibernate từ `EntityManager`; implementation classes có thể đổi giữa versions.

## 15. Dùng EntityManager khi cần portability

Ví dụ chuẩn:

~~~java
@Transactional
public void renameCustomer(Long id, String name) {
    Customer customer = entityManager.find(Customer.class, id);

    if (customer == null) {
        throw new CustomerNotFoundException(id);
    }

    customer.setName(name);
}
~~~

Các thao tác `find`, `persist`, `remove`, `flush`, `clear`, `detach`, `merge` là API Jakarta Persistence.

Nếu application chỉ cần những contract chuẩn, dùng `EntityManager` giúp giảm phụ thuộc trực tiếp vào Hibernate. Nhưng provider vẫn quyết định SQL, dialect và một số behavior implementation.

Portability không có nghĩa mọi database/query plan đều giống nhau; nó chỉ giới hạn mức độ phụ thuộc vào provider-specific APIs.

## 16. Dùng Session khi cần tính năng Hibernate-specific

Ví dụ HQL/Session API:

~~~java
Session session = entityManager.unwrap(Session.class);

List<Order> orders = session.createSelectionQuery(
    "from Order o where o.status = :status",
    Order.class
)
.setParameter("status", OrderStatus.PENDING)
.getResultList();
~~~

Hibernate `Session` có API riêng cho:

- HQL selection/mutation queries.
- Scrollable results.
- Filters.
- Stateless sessions.
- Hibernate-specific lock/fetch/cache controls.
- Session event and statistics integration.

Không có lý do phải unwrap Session cho mọi query CRUD đơn giản. Chỉ dùng khi tính năng cụ thể cần Hibernate API hoặc khi kiến trúc dự án chủ đích gắn với Hibernate.

## 17. JPQL và HQL có quan hệ gì?

**JPQL** là query language được Jakarta Persistence specification định nghĩa. Nó query entity model, không query table/column SQL trực tiếp.

**HQL** là Hibernate Query Language. Hibernate hỗ trợ HQL và trong các phiên bản hiện đại mở rộng/cập nhật language features; JPQL là tập con/compatibility target quan trọng trong các trường hợp phù hợp.

Ví dụ JPQL phổ biến:

~~~java
select o
from Order o
where o.status = :status
order by o.createdAt desc
~~~

Query này thường chạy trên các JPA providers tương thích.

Hibernate HQL có thể hỗ trợ thêm features không có trong JPQL version mà ứng dụng target. Khi sử dụng extension, query không còn portable như JPQL chuẩn.

## 18. JPQL query entity, không query table

JPQL:

~~~java
select c
from Customer c
where c.email = :email
~~~

Dùng entity name và persistent attributes (`Customer`, `email`).

SQL:

~~~sql
SELECT c.id, c.email
FROM customer c
WHERE c.email = ?;
~~~

Hibernate chuyển JPQL/HQL sang SQL theo mapping/dialect.

Không viết tên table/column SQL trong JPQL trừ khi đó là native query. Một lỗi phổ biến là dùng `customer` thay `Customer` hoặc `email_address` thay property `email`.

## 19. Native SQL là một layer khác

Jakarta Persistence:

~~~java
List<?> rows = entityManager.createNativeQuery(
    "select id, email from customer where active = true"
).getResultList();
~~~

Đây là SQL do ứng dụng viết. Database/dialect chịu trách nhiệm parse và thực thi. ORM có thể map result theo cấu hình, nhưng native SQL không được tự chuyển thành JPQL.

Native SQL hữu ích khi cần:

- Window functions/CTEs hoặc DB-specific syntax.
- Stored procedures.
- Vendor-specific hints.
- Bulk operations đặc thù.
- Reporting/query tuning cần kiểm soát SQL.

Đổi lại, code phụ thuộc schema/dialect rõ hơn và phải tự xử lý predicates, tenant/security, soft delete, result mapping và cache synchronization phù hợp.

## 20. Criteria API thuộc Jakarta Persistence

Criteria API cho phép tạo query bằng object model:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<Order> cq = cb.createQuery(Order.class);

Root<Order> order = cq.from(Order.class);

cq.select(order)
  .where(cb.equal(order.get("status"), OrderStatus.PENDING));

List<Order> result =
    entityManager.createQuery(cq).getResultList();
~~~

Đây là Jakarta Persistence Criteria API. Hibernate triển khai query engine và có extensions riêng tùy version.

Criteria hữu ích khi query structure động, nhưng string-based attribute paths vẫn có thể lỗi runtime. Static metamodel generation có thể tăng type safety.

## 21. Spring Data query derivation không phải JPQL parser do Hibernate cung cấp

Method:

~~~java
List<Order> findByStatusAndCustomerId(
    OrderStatus status,
    Long customerId
);
~~~

Spring Data phân tích method name và xây dựng query theo repository metadata/property paths. Hibernate không tự parse method name đó.

Các bước khái niệm:

~~~text
findByStatusAndCustomerId(...)
        |
Spring Data repository infrastructure
        |
derive query from entity properties
        |
EntityManager / query API
        |
Hibernate provider generates SQL
~~~

Nếu method name dài, ambiguous hoặc query phức tạp, dùng `@Query`, Specification hoặc custom repository implementation.

## 22. JpaRepository là interface, không phải implementation ORM

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {
}
~~~

Spring Data tạo proxy và cung cấp implementation cho các repository operations. Một implementation phổ biến trong Spring Data JPA là `SimpleJpaRepository`, nhưng details có thể đổi theo version/configuration.

Nó dùng `EntityManager` để thực hiện persistence operations. Hibernate chỉ tham gia nếu Hibernate được cấu hình làm provider.

Bạn có thể viết custom repository fragment để dùng Criteria, native SQL, Hibernate Session hoặc JDBC khi cần.

## 23. `save()` không phải Hibernate `persist()` đồng nghĩa trong mọi trường hợp

Spring Data JPA `save(entity)` thường quyết định entity mới hay đã tồn tại dựa trên new-state detection, rồi gọi:

- `EntityManager.persist(entity)` nếu được nhận diện là mới.
- `EntityManager.merge(entity)` nếu được nhận diện là đã tồn tại/detached.

Do đó, `save()` là abstraction Spring Data, không phải tên khác của `Session.persist()`.

Với `merge()`:

~~~java
Order managed = entityManager.merge(detachedOrder);
~~~

Object trả về là managed instance. Object truyền vào không nhất thiết trở thành managed.

Khi dùng Spring Data:

~~~java
Order saved = repository.save(detachedOrder);
~~~

nếu tiếp tục thao tác, dùng return value. Đừng giả định `save()` luôn INSERT hoặc luôn UPDATE.

## 24. `saveAndFlush()` cũng không phải commit

~~~java
Order saved = repository.saveAndFlush(order);
~~~

Method này lưu và yêu cầu flush Persistence Context qua `EntityManager`. Nó không nhất thiết commit transaction.

Nếu transaction còn được quản lý bởi outer `@Transactional`, commit diễn ra ở boundary của transaction đó. Sau flush, constraint errors có thể xuất hiện; transaction vẫn có thể rollback sau đó.

Không gọi `saveAndFlush()` sau mọi `save()` như một thói quen; flush quá thường xuyên có thể giảm batching và tăng round trips.

## 25. Transaction `@Transactional` có thể thuộc Spring hoặc Jakarta

Spring:

~~~java
import org.springframework.transaction.annotation.Transactional;
~~~

Jakarta Transactions:

~~~java
import jakarta.transaction.Transactional;
~~~

Cả hai annotations có thể được Spring hỗ trợ trong các cấu hình tương ứng, nhưng chúng thuộc hai API khác nhau và có attributes/semantics khác nhau. Spring `@Transactional` có nhiều options riêng như propagation, isolation, timeout và rollback rules.

Đừng import nhầm annotation chỉ vì tên giống nhau. Trong ứng dụng Spring truyền thống, chọn Spring transaction annotation theo conventions của project.

## 26. Transaction boundary không nằm ở mỗi repository call

Ví dụ:

~~~java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final HistoryRepository histories;

    @Transactional
    public void confirm(Long id) {
        Order order = orders.findById(id).orElseThrow();
        order.confirm();
        histories.save(OrderHistory.confirmed(id));
    }
}
~~~

Hai repository calls thường tham gia cùng transaction đã mở bởi service proxy, nếu transaction manager và propagation phù hợp.

Không cần mỗi repository method commit riêng. `@Transactional` trên service thường biểu đạt unit of work rõ hơn khi nhiều repositories phải cùng atomic.

## 27. Repository methods có thể có transaction defaults

Spring Data JPA repository base methods thường có transaction configuration phù hợp cho read/write operations theo framework defaults. Nhưng query methods tự khai báo không nên được giả định có cùng transaction semantics trong mọi trường hợp.

Best practice:

- Đặt transaction boundary theo use case/service.
- Chỉ dùng read-only transaction cho read workflows phù hợp.
- Hiểu propagation khi repository được gọi từ transaction outer.
- Không để remote HTTP call dài bên trong transaction DB nếu không cần.
- Kiểm tra commit/rollback ở đúng proxy boundary.

`@Transactional(readOnly=true)` là hint/configuration cho transaction integration; không tự đảm bảo DB không thể ghi hoặc entity không thể bị sửa trong Java.

## 28. Dirty checking thuộc persistence provider

Jakarta Persistence quy định managed entity state được đồng bộ với database trong lifecycle của persistence context. Hibernate thực thi dirty checking bằng cơ chế nội bộ của nó.

Ví dụ:

~~~java
@Transactional
public void rename(Long id) {
    Order order = entityManager.find(Order.class, id);
    order.setOrderNumber("ORD-NEW");
    // Không bắt buộc gọi save() nếu entity vẫn managed.
}
~~~

Spring Data `save()` không cần thiết để báo Hibernate rằng managed entity đã thay đổi. Flush/commit của persistence context sẽ đồng bộ theo provider semantics.

Nhưng nếu entity detached, thay đổi field không tự được flush. Cần merge hoặc load managed entity và áp dụng command.

## 29. Cascade là mapping contract, không phải repository feature

Jakarta Persistence định nghĩa:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
private List<OrderLine> lines;
~~~

Hibernate triển khai cascade/lifecycle behavior. Spring Data repository `save(order)` không tự định nghĩa cascade graph mới; nó dựa vào JPA provider và mapping.

Cần phân biệt:

- `CascadeType.PERSIST`.
- `CascadeType.MERGE`.
- `CascadeType.REMOVE`.
- `orphanRemoval`.
- Database FK `ON DELETE CASCADE`.

Chúng không tương đương. Repository save không có nghĩa mọi child luôn được INSERT/UPDATE/DELETE theo ý muốn nếu mapping cascade sai.

## 30. FetchType LAZY/EAGER thuộc Jakarta Persistence mapping

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

`FetchType` là JPA annotation enum. Provider quyết định cách thực hiện fetch theo contract và khả năng của nó.

Hibernate dùng proxies/bytecode enhancement/SQL strategies để triển khai lazy loading. Spring Data có thể thêm fetch plan qua EntityGraph hoặc query definition.

`EAGER` không có nghĩa luôn JOIN trong một SQL. Provider có thể thực hiện secondary selects. `LAZY` cũng không đảm bảo mọi provider/association/field behave giống hệt. Hãy đo SQL và kiểm tra đúng mapping/version.

## 31. EntityGraph là Jakarta Persistence API, Spring Data có thể khai báo

Jakarta Persistence có `@NamedEntityGraph`/`EntityGraph` API. Spring Data JPA cung cấp annotation repository `@EntityGraph` để áp dụng fetch graph cho query methods.

Ví dụ:

~~~java
@EntityGraph(attributePaths = {"customer", "lines"})
Optional<Order> findWithDetailsById(Long id);
~~~

Annotation trên repository thuộc Spring Data JPA; entity graph concept/API thuộc Jakarta Persistence; Hibernate thực hiện SQL fetch.

Đây là ví dụ điển hình ba layers cùng tham gia một feature. Không gọi toàn bộ annotation đó là Hibernate annotation.

## 32. Cache: specification contract và provider behavior

Jakarta Persistence có cache-related APIs/hints ở mức chuẩn. Hibernate cung cấp second-level/query cache integration và cache concurrency strategies riêng. Spring Data JPA không tạo một cache engine thay thế Hibernate.

Khi debug cache:

- Xác định L1 Persistence Context.
- Xác định JPA shared cache settings.
- Xác định Hibernate L2/query cache settings.
- Xác định cache provider (nếu dùng).
- Kiểm tra transaction isolation và invalidation.
- Xác định repository/query cache behavior.

Không nhầm Spring Cache (`@Cacheable`) với Hibernate L2 cache. Spring Cache thường cache method result theo key; Hibernate L2 cache cache entity/collection state theo provider mapping. Chúng có lifecycle và consistency concerns khác nhau.

## 33. `@Cacheable` có thể là hai annotation khác nhau

Jakarta Persistence:

~~~java
import jakarta.persistence.Cacheable;
~~~

Spring Cache:

~~~java
import org.springframework.cache.annotation.Cacheable;
~~~

Hai annotation cùng tên nhưng package và mục đích khác:

- JPA `@Cacheable` điều khiển entity participation trong shared cache semantics.
- Spring `@Cacheable` cache kết quả method invocation qua Spring Cache abstraction.

Hibernate còn có:

~~~java
@org.hibernate.annotations.Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE
)
~~~

Đây là Hibernate-specific second-level cache mapping. Luôn kiểm tra import khi code có nhiều annotations cùng tên.

## 34. Filter và soft delete là ví dụ provider extension

Jakarta Persistence không định nghĩa Hibernate `@Filter` hoặc `@SQLRestriction`.

~~~java
@FilterDef(
    name = "activeOnly",
    parameters = @ParamDef(name = "enabled", type = Boolean.class)
)
@Filter(
    name = "activeOnly",
    condition = "active = :enabled"
)
@Entity
class Account {
}
~~~

~~~java
@Entity
@SQLRestriction("deleted = false")
class Document {
}
~~~

Đây là Hibernate annotations. Spring Data JPA repository có thể query các entities này, nhưng behavior đến từ provider mapping và SQL generation.

Nếu cần portability, cân nhắc JPQL predicates, Specifications, DB views hoặc application-level repository contracts. Nếu cần Hibernate feature, ghi rõ provider dependency và test mọi loading paths.

## 35. `@SoftDelete` không phải Jakarta Persistence annotation

Hibernate ORM 6.4+ cung cấp:

~~~java
@SoftDelete(columnName = "deleted")
@Entity
class Document {
    @Id
    private Long id;
}
~~~

Đây là Hibernate-specific soft-delete mapping. Spring Data `delete()` có thể gọi JPA `EntityManager.remove()` và Hibernate provider áp dụng soft-delete semantics theo mapping/version.

Nhưng bulk repository methods như `deleteAllInBatch()` có thể đi theo bulk DML path, không nhất thiết gọi entity removal từng row. Đừng giả định tất cả repository delete methods đều có cùng soft-delete behavior; test từng API.

## 36. `@Modifying` là Spring Data JPA annotation

Ví dụ:

~~~java
@Modifying
@Query("""
    update Order o
    set o.status = :status
    where o.createdAt < :cutoff
    """)
int archiveOldOrders(
    OrderStatus status,
    Instant cutoff
);
~~~

`@Modifying` báo Spring Data rằng query method thực hiện mutation thay vì SELECT. Query body ở đây là JPQL và Hibernate thực thi thành SQL.

Bulk update bypasses per-entity dirty checking/callbacks và có thể làm persistence context stale. Spring Data cung cấp options như `clearAutomatically`/`flushAutomatically` trên `@Modifying` theo version. Hiểu đúng semantics trước khi bật; clear có thể detach các entities khác trong cùng context.

## 37. Specifications thuộc Spring Data JPA

Spring Data JPA có `Specification<T>` để tạo predicate động dựa trên JPA Criteria:

~~~java
public static Specification<Order> hasStatus(OrderStatus status) {
    return (root, query, cb) ->
        status == null
            ? cb.conjunction()
            : cb.equal(root.get("status"), status);
}
~~~

Repository:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long>,
                JpaSpecificationExecutor<Order> {
}
~~~

`Specification` là abstraction Spring Data; `CriteriaBuilder`, `Root`, `Predicate` là Jakarta Persistence API; Hibernate chuyển Criteria query thành SQL.

Không gọi Specification là Hibernate Criteria. Hibernate có các legacy/native query APIs riêng, nhưng Spring Data Specification thường xây trên JPA Criteria.

## 38. Query derivation, @Query và HQL/JPQL

Spring Data method:

~~~java
findByStatusAndCustomerId(...)
~~~

Spring Data derivation.

Spring Data:

~~~java
@Query("select o from Order o where o.status = :status")
~~~

Annotation Spring Data, query string thường là JPQL.

Hibernate:

~~~java
session.createSelectionQuery("from Order o", Order.class)
~~~

Hibernate Session API, query string HQL.

Native SQL:

~~~java
@Query(
    value = "select * from orders where status = :status",
    nativeQuery = true
)
~~~

Spring Data method nhưng SQL string native.

**Cần đọc cả package/import và query language**, không chỉ tên method.

## 39. Criteria API và Hibernate Criteria legacy

Jakarta Persistence Criteria:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<Order> query = cb.createQuery(Order.class);
~~~

Đây là API chuẩn.

Hibernate từng có Criteria API legacy riêng trong các phiên bản cũ; nó không phải Jakarta Criteria. Khi đọc code cũ hoặc migrate Hibernate, xác định import chính xác.

Không dùng từ “Criteria” chung chung mà bỏ qua package; hai API có thể có class/method names khác nhau và compatibility khác nhau.

## 40. Exception đến từ layer nào?

Một lỗi persistence có thể đi qua nhiều lớp:

~~~text
Database constraint / SQL error
        |
JDBC SQLException
        |
Hibernate exception conversion
        |
Jakarta Persistence exception (nếu áp dụng)
        |
Spring exception translation
        |
Repository/service caller
~~~

Ví dụ có thể gặp:

- `SQLException` từ driver.
- Hibernate `ConstraintViolationException`.
- JPA `PersistenceException`.
- Spring `DataIntegrityViolationException`.
- Spring `JpaSystemException`.

Exception translation phụ thuộc exception type, provider, translator và repository proxy. Đừng bắt duy nhất Hibernate exception nếu code định hướng portability; cũng đừng bắt `Exception` rồi nuốt mất nguyên nhân.

Log root cause, SQLState/constraint metadata an toàn và transaction outcome.

## 41. Repository exception translation không làm mất provider details hoàn toàn

Spring `@Repository`/persistence exception translation có thể chuyển provider exceptions sang Spring `DataAccessException` hierarchy.

Lợi ích:

- Service code có thể xử lý nhóm lỗi tương đối portable.
- Không buộc mọi business service import Hibernate exception.
- Tách persistence implementation khỏi business logic.

Tuy vậy, root cause có thể vẫn là Hibernate/JDBC exception và hữu ích khi chẩn đoán. Giữ causal chain và log đủ context; không biến lỗi thành một thông báo chung không thể truy nguyên.

## 42. Locking: API chuẩn và implementation

Jakarta Persistence định nghĩa optimistic/pessimistic lock modes và `@Version`.

~~~java
@Entity
class InventoryItem {
    @Id
    private Long id;

    @Version
    private long version;
}
~~~

~~~java
entityManager.lock(
    item,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Hibernate triển khai locking theo dialect/DB capabilities. Spring Data có thể khai báo lock trên repository:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select i from InventoryItem i where i.id = :id")
Optional<InventoryItem> lockById(Long id);
~~~

`@Lock` ở đây thuộc Spring Data JPA, `LockModeType` thuộc Jakarta Persistence, Hibernate phát SQL lock phù hợp DB. Đọc generated SQL và kiểm tra timeout/deadlock behavior trên database thật.

## 43. Pagination: Spring Data abstraction, JPA query, provider SQL

Spring Data:

~~~java
Page<Order> page = repository.findByStatus(
    OrderStatus.PENDING,
    PageRequest.of(0, 50, Sort.by("createdAt").descending())
);
~~~

`Page`, `Pageable`, `Sort` thuộc Spring Data Commons. Repository dùng JPA query APIs; Hibernate/dialect sinh SQL pagination.

`Page` có thể cần count query. `Slice` hoặc keyset `Window` APIs tùy version có thể giảm count overhead. Không gọi pagination API là “Hibernate pagination” nếu đang nói về Spring Data abstraction.

## 44. Projections: Spring Data, JPQL và Hibernate

Spring Data interface projection:

~~~java
interface OrderView {
    Long getId();
    String getOrderNumber();
}
~~~

Spring Data tạo projection view.

JPQL constructor projection:

~~~java
select new com.example.OrderViewDto(o.id, o.orderNumber)
from Order o
~~~

JPQL query được thực thi bởi provider.

Hibernate HQL projection có thể cung cấp thêm features theo version. Cần phân biệt projection result shape với entity hydration; DTO không tự trở thành managed entity.

## 45. Auditing: Spring Data feature và entity listener integration

Spring Data JPA auditing thường dùng:

~~~java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant updatedAt;

@CreatedBy
private String createdBy;
~~~

Các auditing annotations thuộc Spring Data Commons/JPA integration. Cần bật auditing infrastructure và cung cấp `AuditorAware` nếu dùng created/modified by.

JPA entity lifecycle callbacks là một cơ chế khác. Hibernate event listeners lại là provider-specific. Đừng đồng nhất ba cơ chế chỉ vì chúng đều chạy quanh persist/update.

Test auditing với actual transaction/lifecycle và verify timestamp/user values sau reload.

## 46. Validation: Jakarta Bean Validation khác Persistence

~~~java
@NotNull
@Size(max = 100)
private String orderNumber;
~~~

`@NotNull`/`@Size` thường thuộc Jakarta Bean Validation (`jakarta.validation`), không phải Jakarta Persistence. Hibernate Validator là một implementation phổ biến của Bean Validation; tên “Hibernate” ở đây có thể khiến người đọc nhầm với Hibernate ORM.

Có ba sản phẩm/layer khác nhau:

- Hibernate ORM: persistence provider.
- Hibernate Validator: Bean Validation provider.
- Jakarta Validation: validation specification/API.

Spring tích hợp validation vào request/service và JPA lifecycle khi được cấu hình. Database constraints vẫn là enforcement độc lập.

## 47. Hibernate ORM khác Hibernate Validator

Cùng tổ chức/tên Hibernate không có nghĩa cùng library:

| Thành phần | Nhiệm vụ |
|---|---|
| Hibernate ORM | Object-relational mapping/persistence |
| Hibernate Validator | Bean Validation implementation |
| Jakarta Validation | Standard validation API/spec |
| Spring Validation integration | Kết nối validation với Spring application |

Nếu stack trace có `org.hibernate.validator`, đó không phải tự động là lỗi Hibernate ORM/SQL. Xác định package/class trước khi chẩn đoán.

## 48. Spring transaction manager và Hibernate transaction

Spring quản lý transaction boundaries qua `PlatformTransactionManager` hoặc reactive transaction manager. Với JPA, thường dùng `JpaTransactionManager`; Spring Boot auto-configures phù hợp với application setup.

Hibernate Session/JDBC connection được gắn với transaction theo integration. Không mở transaction Hibernate native thủ công bên trong một Spring-managed JPA transaction nếu không hiểu resource coordination.

Nếu unwrap Session, tiếp tục dùng cùng transaction-bound resource:

~~~java
Session session = entityManager.unwrap(Session.class);
~~~

Không gọi `session.beginTransaction()` tùy tiện khi Spring đã quản lý transaction. Dùng Spring `@Transactional` hoặc `TransactionTemplate` theo architecture.

## 49. Open Session in View không phải JPA specification feature

Spring có OSIV integration giữ persistence context/session mở qua web request để hỗ trợ lazy loading trong view/serialization. Đây là integration pattern của framework/provider.

OSIV có thể che việc service trả entity có lazy associations; serializer truy cập sau khi service transaction kết thúc và phát SQL muộn.

DTO response và fetch plan rõ ràng thường giúp API behavior dễ dự đoán hơn. Nếu bật OSIV, hiểu transaction/connection behavior và theo dõi SQL phát trong serialization.

Không gán OSIV cho Hibernate/Jakarta Persistence như một lifecycle requirement chuẩn.

## 50. Test `@DataJpaTest` và provider behavior

Spring Boot `@DataJpaTest` là test slice tập trung vào JPA components, repositories và entity mappings. Nó thường cấu hình test database theo project dependencies.

Nó không chứng minh application behavior trên production DB nếu test tự dùng H2 trong khi production dùng PostgreSQL.

Dùng:

- `@DataJpaTest` cho repository/mapping-focused tests.
- Testcontainers với DB production-like cho dialect/constraint/locking tests.
- `@SpringBootTest` cho transaction/security/service integration rộng hơn.
- Provider-specific tests nếu dùng Hibernate extensions.

Test cũng cần quản lý transaction rollback mặc định của slice để không nhầm flush với commit.

## 51. Test provider portability khi cần

Nếu application muốn hỗ trợ nhiều JPA providers, một số tests nên chạy trên provider khác hoặc module compatibility suite:

- JPQL queries.
- Standard mapping annotations.
- Entity lifecycle.
- Cascade/locking.
- Criteria API.
- Standard converters.
- Entity graphs.
- Transaction semantics theo specification.

Các tests dùng `Session`, `@Filter`, `@SQLRestriction`, HQL extensions hoặc `@SoftDelete` là provider-specific; không kỳ vọng chạy trên provider khác nếu không có compatibility layer tương ứng.

Không cần test nhiều providers nếu architecture chủ đích gắn với Hibernate; điều quan trọng là ghi rõ quyết định đó.

## 52. Kiểm tra dependency tree và classpath

Maven:

~~~bash
mvn dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm:

- Có nhiều phiên bản Hibernate ORM không?
- Có `javax.persistence-api` và `jakarta.persistence-api` cùng lúc?
- Spring Data JPA có tương thích Spring Boot/Framework?
- JDBC driver đúng version?
- Hibernate Validator có bị nhầm với Hibernate ORM?
- Có library cũ chỉ hỗ trợ javax namespace?
- Bytecode enhancement plugin có khớp Hibernate version?

Không loại dependency chỉ vì tên giống nhau; xem dependency path và module thực sự dùng package nào.

## 53. Đọc tài liệu đúng layer

Khi cần trả lời câu hỏi:

| Câu hỏi | Tài liệu nên xem trước |
|---|---|
| `EntityManager.find()` có semantics gì? | Jakarta Persistence spec/API |
| `@SQLRestriction` có disable được không? | Hibernate ORM Javadocs/User Guide |
| `JpaRepository.save()` xử lý new/detached thế nào? | Spring Data JPA reference |
| HQL có function/extension nào? | Hibernate Query Language guide |
| `@EntityGraph` trên repository hoạt động thế nào? | Spring Data JPA + Jakarta Persistence docs |
| Transaction propagation của Spring? | Spring Framework transaction docs |
| SQL type/lock/index behavior? | DBMS docs + JDBC driver docs |
| `@NotNull` validation? | Jakarta Validation + Hibernate Validator docs |

Đọc đúng docs tiết kiệm thời gian và tránh áp dụng nhầm một guarantee của layer khác.

## 54. Quy trình nâng cấp stack

Khi nâng Spring Boot/Hibernate:

1. Xem release notes và supported versions của Spring Boot.
2. Xác định Jakarta Persistence version mà provider implement.
3. Xác định Spring Data JPA version đi cùng Boot BOM.
4. Kiểm tra `javax` → `jakarta` namespace migration nếu đang qua ranh giới.
5. Kiểm tra Hibernate extension/API đã dùng có thay đổi/deprecated không.
6. Kiểm tra HQL parser/query behavior và generated SQL.
7. Chạy migrations và schema validation trên DB thật.
8. Chạy repository/transaction/cache/locking tests.
9. Kiểm tra driver và dialect compatibility.
10. Xem dependency tree sau upgrade.

Không nâng riêng Hibernate ORM vượt ra ngoài compatibility range của Spring Boot chỉ vì một annotation mới xuất hiện trong Javadocs.

## 55. Bảng phân loại API thường gặp

| API/annotation | Layer | Ghi chú |
|---|---|---|
| `@Entity`, `@Id`, `@OneToMany` | Jakarta Persistence | Standard mapping |
| `EntityManager` | Jakarta Persistence | Standard persistence API |
| `Query`, `TypedQuery`, `CriteriaBuilder` | Jakarta Persistence | Standard query APIs |
| JPQL | Jakarta Persistence | Standard query language |
| `Session`, `StatelessSession` | Hibernate ORM | Native provider APIs |
| HQL extensions | Hibernate ORM | Có thể không portable |
| `@Filter`, `@SQLRestriction` | Hibernate ORM | Provider-specific |
| `@SoftDelete` | Hibernate ORM | Version-specific extension |
| `JpaRepository` | Spring Data JPA | Repository abstraction |
| `@Query`, `@Modifying` | Spring Data JPA | Repository query metadata |
| `Specification` | Spring Data JPA | Built on JPA Criteria |
| `Pageable`, `Page`, `Slice` | Spring Data Commons | Repository paging abstraction |
| Spring `@Transactional` | Spring Framework | Declarative transaction management |
| JPA `@Cacheable` | Jakarta Persistence | Shared cache participation |
| Spring `@Cacheable` | Spring Framework | Method-result cache abstraction |
| `@NotNull` | Jakarta Validation | Validation constraint |
| Hibernate Validator | Validation provider | Không phải Hibernate ORM |

## 56. Những cách nói gây nhầm lẫn

| Cách nói mơ hồ | Cách nói chính xác hơn |
|---|---|
| “Hibernate annotation `@Entity`” | Jakarta Persistence `@Entity`, được Hibernate xử lý |
| “JPA là database” | Jakarta Persistence là persistence API/specification |
| “Spring Data JPA là ORM” | Spring Data JPA là repository abstraction dùng JPA provider |
| “Hibernate `EntityManager`” | Jakarta Persistence `EntityManager` do Hibernate implement |
| “`save()` gọi persist” | Spring Data `save()` có thể gọi persist hoặc merge |
| “`saveAndFlush()` commit” | Save + flush; commit do transaction boundary |
| “`@Query` là HQL” | Spring Data `@Query` thường chứa JPQL; có thể cấu hình native SQL |
| “Criteria của Hibernate” | Cần xác định JPA Criteria hay Hibernate legacy/native API |
| “Hibernate cache” | Cần phân biệt L1, L2, query cache và Spring Cache |
| “Hibernate validation” | Có thể là Hibernate Validator, khác Hibernate ORM |
| “JPA transaction” | Cần nói rõ Spring/JTA/Jakarta transaction manager/provider integration |

## 57. Lỗi thường gặp khi trộn các layers

| Lỗi | Vì sao sai | Hướng xử lý |
|---|---|---|
| Import nhầm `javax.persistence` trong Boot 3 | Namespace không tương thích | Dùng `jakarta.persistence` |
| Gọi `JpaRepository` là Hibernate API | Sai abstraction layer | Đọc Spring Data JPA contract |
| Dùng `Session` ở mọi nơi | Tăng coupling provider | Dùng EntityManager khi đủ |
| Dùng JPQL nhưng viết table/column names | JPQL query entity model | Dùng entity/property names hoặc native SQL |
| Cho rằng `save()` luôn INSERT | Spring Data có thể merge | Hiểu new-state detection |
| Cho rằng `saveAndFlush()` commit | Flush không commit | Kiểm tra outer transaction |
| Dùng Hibernate annotation nhưng muốn đổi provider | Extension không portable | Standard mapping hoặc adapter |
| Dùng Spring Cache thay L2 cache | Hai cache abstractions khác nhau | Xác định cache layer |
| Bắt mỗi Hibernate exception trong service | Coupling provider, bỏ qua translation | Spring DataAccessException khi phù hợp |
| Thêm Hibernate version tùy tiện | BOM mismatch | Dùng dependency management |
| Gọi `beginTransaction()` trong Spring tx | Resource coordination sai | Để Spring quản lý |
| Dùng native SQL rồi mong Filter áp dụng | Raw SQL có thể bypass ORM mapping | Explicit predicates/DB policies |

## 58. Bài tập thực hành

1. Tạo một entity với Jakarta Persistence annotations và chạy bằng Hibernate provider; xác định package/API ở từng dòng.
2. Viết cùng một use case bằng `EntityManager` và bằng `JpaRepository`; trace call path.
3. Unwrap Hibernate `Session` từ `EntityManager` và dùng một Hibernate-specific feature có kiểm soát.
4. Viết JPQL query và một HQL-specific query; phân loại portability.
5. Viết Spring Data derived query, `@Query` JPQL và native query; bật SQL logs so sánh.
6. Kiểm tra `repository.save()` cho entity mới và detached entity; xem persist/merge path.
7. Dùng `saveAndFlush()` trong outer transaction rồi throw exception; chứng minh flush không commit.
8. Tạo `@SQLRestriction`/`@Filter` và xác định đó là Hibernate extension.
9. So sánh JPA `@Cacheable` với Spring `@Cacheable` trong hai tests riêng.
10. Tạo `@DataJpaTest` với H2 rồi chạy cùng mapping tests trên PostgreSQL Testcontainers.
11. Kiểm tra dependency tree có `javax.persistence` và `jakarta.persistence` không.
12. Migrate một project cũ từ `javax.persistence` sang `jakarta.persistence` theo version-compatible stack.
13. Tạo validation constraint và database NOT NULL; xác định layer phát exception.
14. Đọc một stack trace và phân loại exception thuộc JDBC, Hibernate ORM, Jakarta Persistence hay Spring translation.

## 59. Sơ đồ quyết định: chọn API ở layer nào?

~~~mermaid
flowchart TD
    A["Cần thao tác persistence"] --> B{"Cần repository abstraction?"}
    B -- "Có" --> C["Spring Data JPA Repository"]
    B -- "Không" --> D["Jakarta Persistence EntityManager"]
    C --> E["JPA API / query metadata"]
    D --> E
    E --> F{"Cần Hibernate-specific feature?"}
    F -- "Không" --> G["Giữ standard JPA contract"]
    F -- "Có" --> H["Unwrap Session / Hibernate extension"]
    G --> I["Persistence provider"]
    H --> I
    I --> J["JDBC + Database"]
    J --> K["Test đúng DB, provider và versions"]
~~~

## 60. Tài liệu tham khảo chính thức

- [Jakarta Persistence](https://jakarta.ee/specifications/persistence/) — specification, API, entity lifecycle, JPQL và Criteria.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/current/userguide/html_single/Hibernate_User_Guide.html) — provider behavior, mappings, Session, HQL, fetching, cache và extensions.
- [Hibernate ORM Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/) — xác định chính xác package và version của Hibernate-specific APIs.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/) — repositories, query derivation, projections, specifications và `@Modifying`.
- [Spring Framework Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html) — Spring transaction boundaries, propagation và proxy semantics.
- [Spring Boot Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html) — BOM/starters và dependency alignment.
- [Jakarta Validation](https://jakarta.ee/specifications/bean-validation/) — validation specification, phân biệt với persistence.
- [Hibernate Validator](https://hibernate.org/validator/) — Bean Validation implementation, khác Hibernate ORM.

Các trang `current` có thể mô tả phiên bản mới hơn project. Luôn xem release notes, BOM và Javadocs của đúng Spring Boot/Hibernate/Spring Data versions đang dùng.

## 61. Tổng kết

**Jakarta Persistence, Hibernate ORM và Spring Data JPA liên quan chặt chẽ nhưng không phải cùng một sản phẩm hoặc cùng một layer.**

- **Jakarta Persistence** định nghĩa specification/API chuẩn: entity mappings, `EntityManager`, JPQL, Criteria và lifecycle contracts.
- **Hibernate ORM** là provider triển khai API đó, tạo SQL và cung cấp extensions/native APIs như `Session`, HQL features, filters và soft delete.
- **Spring Data JPA** cung cấp repository abstraction, query derivation, projections, Specifications và tích hợp với JPA provider.
- **Spring Framework** quản lý transaction declarative qua `@Transactional` và transaction manager; nó phối hợp với persistence resources.
- **JDBC/Database** thực hiện SQL và enforce physical constraints, types, locks và transaction durability.

Khi gặp một behavior, hãy xác định nó thuộc **specification, provider, repository framework, transaction integration hay database** trước khi tìm cách sửa. Dùng API chuẩn khi contract chuẩn đã đủ; dùng Hibernate extension khi cần và chấp nhận provider coupling; dùng Spring Data repository để tổ chức data access mà không nhầm nó với ORM engine.

Phân biệt đúng các layer giúp chọn dependency tương thích, đọc đúng tài liệu, viết query portable khi cần và chẩn đoán lỗi ở đúng nơi thay vì đổ mọi vấn đề cho “Hibernate”.
