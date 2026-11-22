# Kiểm tra SQL sinh ra và tránh phụ thuộc ngoài chủ đích vào tính năng riêng

Trong một ứng dụng dùng Hibernate, lập trình viên thường viết **HQL/JPQL**, Criteria API hoặc repository method, nhưng database thực sự thực thi **SQL do Hibernate sinh ra**. Hai tầng này liên quan chặt chẽ nhưng không đồng nhất.

Một HQL trông ngắn gọn có thể dẫn đến nhiều SQL statements, join ngoài dự kiến, subquery phức tạp, hàng kết quả bị nhân lên, truy vấn phụ khi khởi tạo lazy association, hoặc câu lệnh có đặc điểm khác nhau giữa PostgreSQL, MySQL, Oracle và SQL Server. Ngược lại, một câu HQL sử dụng cú pháp Hibernate hỗ trợ có thể không phải **JPQL chuẩn**, hoặc một function được Hibernate chuyển xuống SQL có thể chỉ tồn tại trên một hệ quản trị nhất định.

Vì vậy, với **HQL nâng cao**, phải kiểm tra cả hai câu hỏi:

1. **Hibernate thực sự gửi SQL gì đến database?** Số statement, JOIN, WHERE, ORDER BY, parameters, pagination, locking, DML và execution plan có đúng với mong muốn không?
2. **Truy vấn đang phụ thuộc vào những tính năng nào?** Đó là JPQL chuẩn, extension của Hibernate HQL, hành vi theo dialect hay tính năng riêng của database? Sự phụ thuộc có được quyết định và kiểm thử có chủ đích không?

Mục tiêu không phải tránh mọi tính năng chuyên biệt. Một hàm PostgreSQL, recursive CTE hay window function có thể là lựa chọn tốt nhất cho một use case. Vấn đề cần tránh là **phụ thuộc không được nhận biết**, khiến việc nâng Hibernate, đổi database, chạy test trên DB khác hoặc mở rộng deployment tạo lỗi bất ngờ.

---

## 1. Bốn tầng cần phân biệt

Một truy vấn có thể trải qua nhiều tầng:

~~~mermaid
flowchart TD
    A["Ứng dụng: HQL / JPQL / Criteria / Repository"] --> B["Hibernate: parser, semantic model, query plan"]
    B --> C["Hibernate Dialect: sinh SQL theo DB"]
    C --> D["JDBC: prepare, bind parameters, execute"]
    D --> E["Database: parse, optimize, execute"]
    E --> F["Rows / update counts"]
    F --> G["Hibernate: assemble entity / DTO"]
~~~

Mỗi tầng trả lời một nhóm câu hỏi riêng:

| Tầng | Ví dụ | Cần quan sát |
| --- | --- | --- |
| HQL/JPQL | `select o from PurchaseOrder o` | Entity/property path, semantics query |
| Hibernate ORM | Fetch plan, dirty checking, flushing, CTE/window support | SQL nào được tạo, bao nhiêu lần, lúc nào |
| Hibernate Dialect | PostgreSQLDialect, MySQLDialect, SQLServerDialect | Cách biểu diễn pagination, function, lock, cast, CTE |
| Database | PostgreSQL, MySQL, Oracle, SQL Server | Execution plan, index, row counts, lock/IO/latency |

Đọc HQL source là cần thiết, nhưng **không đủ** để khẳng định database đang làm gì.

### 1.1. HQL không phải SQL

HQL sử dụng **tên entity, property và association** theo mô hình Java:

~~~hql
select o.id, o.customer.name
from PurchaseOrder o
where o.status = :status
order by o.createdAt desc
~~~

SQL được tạo ra có thể sử dụng bảng, cột, alias và JOIN theo mapping:

~~~sql
select o1_0.id, c1_0.name
from purchase_orders o1_0
join customers c1_0 on c1_0.id = o1_0.customer_id
where o1_0.status = ?
order by o1_0.created_at desc
~~~

SQL trên chỉ là **minh họa**. Tên alias, thứ tự cột, JOIN, bind type và cú pháp cụ thể có thể thay đổi theo Hibernate version, dialect và mapping.

### 1.2. HQL không đồng nghĩa JPQL portable

Hibernate hỗ trợ một ngôn ngữ HQL phong phú, bao gồm nhiều phần mở rộng ngoài phạm vi JPQL thông dụng, chẳng hạn:

- CTE và recursive CTE trong các Hibernate 6.x hỗ trợ.
- Window functions và ordered-set aggregates.
- Set operations như `union`, `intersect` và `except`.
- Một số biểu thức row value/tuple nâng cao.
- Lateral joins và derived roots trong các phiên bản phù hợp.
- Cú pháp pagination hoặc function mở rộng.

**Một query được `EntityManager.createQuery()` chấp nhận không có nghĩa query đó sẽ chạy trên mọi JPA provider.** Nếu Hibernate là provider, API JPA có thể nhận các extension của HQL.

### 1.3. HQL portable cũng không bảo đảm SQL nhanh

Một biểu thức HQL có thể hợp chuẩn JPQL nhưng Hibernate vẫn tạo SQL mà database thực thi không tối ưu. Tính tương thích cú pháp và hiệu năng là hai trục độc lập.

Ví dụ `join fetch` là kỹ thuật hợp lệ nhưng join nhiều collection to-many có thể tạo Cartesian row multiplication; còn truy cập lazy association trong vòng lặp có thể tạo N+1 queries.

## 2. Bối cảnh ví dụ: đơn hàng, khách hàng và dòng hàng

Giả sử ứng dụng có mapping:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    @Version
    private long version;

    protected PurchaseOrder() {}
}
~~~

~~~java
@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false)
    private int quantity;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal unitPrice;
}
~~~

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {}
}
~~~

HQL danh sách đơn hàng:

~~~java
List<PurchaseOrder> orders = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """, PurchaseOrder.class)
    .setParameter("status", OrderStatus.COMPLETED)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
~~~

Ứng dụng mong muốn một trang gồm tối đa 20 đơn hàng. Nhưng cần xem SQL để biết:

- SQL có `LIMIT/OFFSET` hay cú pháp tương đương theo database không?
- Có `ORDER BY` đủ ổn định không?
- Có thêm JOIN do fetch plan không?
- Có SQL riêng khi code đọc `order.getCustomer()` hoặc `order.getLines()` không?
- Truy vấn nào là kết quả của HQL, truy vấn nào là kết quả của lazy loading?

Những câu trả lời đó không thể có chỉ bằng việc nhìn một lệnh `createQuery()`.

## 3. Bật log SQL của Hibernate 6

Trong ứng dụng Spring Boot dùng Hibernate 6, có thể cấu hình log phát triển:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE

spring:
  jpa:
    properties:
      hibernate:
        format_sql: true
~~~

Ý nghĩa:

| Thiết lập | Dùng để làm gì |
| --- | --- |
| `org.hibernate.SQL=DEBUG` | Xem SQL được Hibernate phát |
| `org.hibernate.orm.jdbc.bind=TRACE` | Xem giá trị/type được bind vào JDBC parameter |
| `hibernate.format_sql=true` | Làm SQL dễ đọc hơn bằng xuống dòng/thụt lề |

Ví dụ log có thể trông như:

~~~text
DEBUG org.hibernate.SQL:
    select
        o1_0.id,
        o1_0.customer_id,
        o1_0.status,
        o1_0.created_at,
        o1_0.total_amount
    from purchase_orders o1_0
    where o1_0.status=?
    order by o1_0.created_at desc, o1_0.id desc
    offset ? rows fetch first ? rows only
~~~

Đoạn SQL chỉ minh họa một kiểu pagination; không được suy ra tất cả database sẽ dùng cú pháp `OFFSET ... FETCH`.

### 3.1. Vì sao SQL có dấu ? thay vì giá trị thật?

Hibernate thường sử dụng JDBC prepared statements:

~~~sql
where status = ?
~~~

Sau đó JDBC bind giá trị thực từ `setParameter("status", ...)`. SQL log và parameter log có thể nằm ở các logger khác nhau. Việc chỉ thấy `?` **không có nghĩa tham số không được truyền**.

Các công cụ phân tích SQL cần phân biệt câu SQL template với bind values và JDBC types.

### 3.2. Hibernate 5 và Hibernate 6 có logger bind khác nhau

Trong Hibernate 5, logging parameter thường được cấu hình thông qua logger như:

~~~properties
logging.level.org.hibernate.type.descriptor.sql.BasicBinder=TRACE
~~~

Trong Hibernate 6, dùng nhóm:

~~~properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Không copy cấu hình debug trên Internet mà không biết phiên bản Hibernate đang chạy. Nếu SQL hiện ra nhưng bind values không xuất hiện, có thể bạn đang dùng tên logger thuộc phiên bản khác.

### 3.3. Đừng dùng show_sql và logger như hai bản sao

Một cấu hình khác:

~~~properties
hibernate.show_sql=true
~~~

có thể in SQL trực tiếp ra console. Trong ứng dụng có logging framework, thường ưu tiên `org.hibernate.SQL` để kiểm soát level, filter và đích log. Bật cả hai có thể khiến SQL hiển thị trùng lặp, khó thống kê số statements.

### 3.4. Cảnh báo dữ liệu nhạy cảm

Bind log có thể chứa:

- Email, số điện thoại, địa chỉ.
- Mã định danh của khách hàng.
- Nội dung đơn hàng, token hoặc dữ liệu nghiệp vụ nhạy cảm.
- Thông tin từ câu truy vấn tìm kiếm.

**Không bật TRACE bind parameters tràn lan trên production**. Nếu cần quan sát production, nên dùng telemetry có kiểm soát, sampling, che dữ liệu, giới hạn quyền truy cập và retention policy phù hợp.

## 4. SQL log không phải bức tranh đầy đủ về truy vấn

Một dòng SQL log giúp thấy câu lệnh Hibernate tạo, nhưng chưa thể kết luận:

- Database đã chọn index nào.
- Số hàng đọc/ghi thực tế.
- Query đang chờ lock hay bị nghẽn I/O.
- Số lần được thực thi qua toàn request.
- Câu SQL có được trả từ query cache hay entity đã nằm trong persistence context không.
- Transaction cuối cùng commit hay rollback.

Cần kết hợp các phương pháp quan sát khác nhau.

### 4.1. SQL được log không chứng minh commit

Ví dụ:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, id);
order.markCompleted();

em.flush(); // UPDATE có thể đã chạy.

// Sau đó transaction có thể rollback.
~~~

Đã thấy SQL `UPDATE` trong log không chứng minh thay đổi đã được commit. Flush và commit là hai thao tác khác nhau.

### 4.2. SELECT không nhất thiết xuất hiện mỗi lần find

Nếu entity đã có trong first-level cache/persistence context:

~~~java
PurchaseOrder first = em.find(PurchaseOrder.class, id);
PurchaseOrder second = em.find(PurchaseOrder.class, id);
~~~

Lệnh `find()` thứ hai có thể không sinh SELECT. Nếu muốn đo SQL load từ database, cần hiểu state của EntityManager; các test độc lập đôi khi phải `flush()`/`clear()` hoặc mở context mới.

### 4.3. SQL ngoài query ban đầu

Một method có thể gọi một HQL nhưng tạo thêm SQL khi:

- Khởi tạo lazy association.
- Flush pending changes trước một query.
- Đọc giá trị generated/identity.
- Tải collection theo batch/subselect.
- Thực hiện cascade/lifecycle actions.

Vì vậy phải đo **toàn bộ use case**, không chỉ SQL trực tiếp xuất phát từ một dòng HQL.

## 5. Hibernate Statistics: đo số statement và hành vi ORM

Hibernate cung cấp statistics API để theo dõi một số chỉ số vận hành.

Bật thống kê trong môi trường phát triển hoặc test:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true
~~~

Ví dụ Java:

~~~java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
    em.getEntityManagerFactory().unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();

statistics.clear();

// Chạy use case cần quan sát.
List<PurchaseOrder> orders = loadOrders();

long statementCount = statistics.getPrepareStatementCount();
long entityLoads = statistics.getEntityLoadCount();
long collectionFetches = statistics.getCollectionFetchCount();

System.out.println("Prepared statements: " + statementCount);
System.out.println("Entity loads: " + entityLoads);
System.out.println("Collection fetches: " + collectionFetches);
~~~

Các counter có ý nghĩa khác nhau:

- `getPrepareStatementCount()` đếm các thao tác prepare JDBC statement theo phạm vi thống kê.
- `getEntityLoadCount()` phản ánh lượng entity load.
- `getCollectionFetchCount()` phản ánh việc fetch collection theo thống kê Hibernate.
- Query cache và second-level cache có thống kê riêng nếu được bật.

### 5.1. Không coi Statistics là bộ đếm riêng từng request

`SessionFactory.getStatistics()` thường là số liệu **toàn SessionFactory**. Nếu test chạy song song hoặc ứng dụng có nhiều request, `clear()` và các counter có thể bị ảnh hưởng bởi công việc khác.

Để assert số statement trong integration test, hãy cô lập test hoặc dùng công cụ capture theo scope phù hợp. Không dùng số liệu toàn cục đang bị chia sẻ để kết luận chính xác một request production sinh bao nhiêu SQL.

### 5.2. Statement count không nói câu SQL có tốt không

Một query tạo 100.000 hàng và JOIN nhiều bảng có thể có statement count bằng 1, trong khi ba query tổng cộng 300 hàng có count bằng 3.

Vì thế hãy xét **cả số lần SQL, lượng dữ liệu trả về, thời gian chạy và execution plan**.

## 6. StatementInspector: quan sát SQL trước khi JDBC prepare

Hibernate có SPI:

~~~java
org.hibernate.resource.jdbc.spi.StatementInspector
~~~

Nó có thể được dùng để kiểm tra SQL trước khi statement được JDBC chuẩn bị.

Ví dụ:

~~~java
import org.hibernate.resource.jdbc.spi.StatementInspector;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class SqlInspectionLogger
        implements StatementInspector {

    private static final Logger log =
        LoggerFactory.getLogger(SqlInspectionLogger.class);

    @Override
    public String inspect(String sql) {
        log.debug("Hibernate SQL template: {}", sql);
        return sql;
    }
}
~~~

Method `inspect` nhận **SQL template**, thường vẫn chứa các dấu `?`. Nó không phải một bản SQL đã nội suy tất cả parameter values.

### 6.1. Đăng ký trong Hibernate

Một cách là cấu hình property:

~~~properties
hibernate.session_factory.statement_inspector=com.example.SqlInspectionLogger
~~~

Trong một ứng dụng Spring Boot, cũng có thể dùng `HibernatePropertiesCustomizer` và đăng ký một instance được quản lý bởi Spring:

~~~java
import org.springframework.boot.autoconfigure.orm.jpa.HibernatePropertiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class HibernateInspectionConfig {

    @Bean
    HibernatePropertiesCustomizer sqlInspectorCustomizer(
            SqlInspectionLogger inspector) {
        return properties -> properties.put(
            "hibernate.session_factory.statement_inspector",
            inspector
        );
    }
}
~~~

Ví dụ trên giả định `SqlInspectionLogger` là bean Spring (ví dụ thêm `@Component` hoặc định nghĩa `@Bean` riêng). Chi tiết tích hợp có thể thay đổi theo Spring Boot/Hibernate version; cần bảo đảm không đăng ký trùng nhiều inspector mà tưởng chúng đều chạy.

### 6.2. Inspector dùng để kiểm tra, không nên lạm dụng sửa SQL

`inspect(String sql)` có thể trả về SQL đã chỉnh sửa, nhưng việc thay chuỗi SQL tùy ý rất dễ gây lỗi:

- Làm sai thứ tự JDBC placeholders.
- Phá quoting hoặc escaping của dialect.
- Mất tương thích khi Hibernate đổi alias/cấu trúc.
- Làm câu SQL không còn khớp với ORM mapping.
- Tạo lỗ hổng injection nếu nối dữ liệu không tin cậy.

Trong đa số tình huống, hãy **trả lại nguyên SQL** và dùng inspector để quan sát hoặc gắn metadata được thiết kế cẩn thận. Nếu cần thay ngữ nghĩa câu query, ưu tiên sửa HQL, mapping hoặc sử dụng một extension chính thức phù hợp.

### 6.3. Tính thread-safe và phạm vi dùng chung

Một inspector đăng ký ở SessionFactory có thể được nhiều Session/request sử dụng. Nếu inspector lưu câu SQL vào một collection phục vụ test, hãy dùng cấu trúc thread-safe và cơ chế cô lập theo test, không lưu state mutable không đồng bộ trong singleton.

Đừng đưa raw SQL/bind values vào một kho log không kiểm soát.

## 7. Bổ sung SQL comments để truy nguyên use case

Hibernate hỗ trợ SQL comments khi bật cấu hình phù hợp:

~~~properties
hibernate.use_sql_comments=true
~~~

Hibernate API có thể cho phép gắn comment cho query, ví dụ:

~~~java
import org.hibernate.query.Query;

Query<PurchaseOrder> query = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.status = :status
    """, PurchaseOrder.class)
    .unwrap(Query.class);

query.setComment("OrderList: completed orders");

List<PurchaseOrder> result = query
    .setParameter("status", OrderStatus.COMPLETED)
    .getResultList();
~~~

Đây là tính năng Hibernate-specific. Nếu câu SQL được sinh có comment, log có thể cho biết statement thuộc chức năng nào mà không cần suy đoán từ alias.

**Không đặt dữ liệu người dùng hoặc bí mật vào SQL comments.** Tránh nối request payload, token hoặc raw search text vào comment.

## 8. Cách đọc một câu SQL Hibernate sinh ra

Khi kiểm tra SQL, đọc có hệ thống thay vì chỉ nhìn tên bảng:

1. **SELECT list:** Có lấy quá nhiều cột, LOB, giá trị không cần dùng không?
2. **FROM/JOIN:** Những bảng nào tham gia, JOIN nào là INNER/LEFT?
3. **JOIN predicates:** Điều kiện kết nối có dùng FK/PK đúng như mapping không?
4. **WHERE:** Các filter nghiệp vụ, tenant, soft-delete, trạng thái có xuất hiện không?
5. **Bind parameters:** Type và giá trị có đúng không?
6. **GROUP BY/HAVING:** Aggregate có nhân hàng do join không?
7. **ORDER BY:** Có tie-breaker ổn định cho pagination không?
8. **LIMIT/OFFSET/FETCH:** Database có áp dụng pagination thật sự không?
9. **Locking:** Có FOR UPDATE, lock hint hoặc câu phụ không?
10. **DML:** UPDATE/DELETE có predicate version hoặc tenant cần thiết không?

### 8.1. Implicit join có thể sinh JOIN ngoài dự kiến

HQL:

~~~hql
select o.id, o.customer.name
from PurchaseOrder o
where o.status = :status
~~~

Truy cập `o.customer.name` đòi dữ liệu từ Customer, nên Hibernate có thể sinh JOIN tới bảng khách hàng. Một property path tưởng như chỉ là toán tử dấu chấm có thể thay đổi số bảng tham gia.

Nếu association optional, implicit join hoặc cách biểu diễn path có thể ảnh hưởng những row nào được giữ lại. Khi ý định là giữ cả Order không có Customer, hãy viết JOIN type rõ ràng và kiểm tra SQL thực tế.

### 8.2. Fetch join và tích Descartes

HQL:

~~~hql
select o
from PurchaseOrder o
left join fetch o.lines
where o.id = :id
~~~

Một Order có 10 OrderLine thường tạo nhiều hàng SQL cho cùng root. Khi join fetch thêm collection thứ hai, số hàng có thể tăng theo tích kích thước hai collection.

`DISTINCT` ở cấp entity không nhất thiết giảm lượng dữ liệu thực tế mà database phải join và truyền. Trong Hibernate 6, duplicate root entity do fetch join được xử lý khác các phiên bản trước; điều này không xóa chi phí Cartesian.

### 8.3. N+1 trong code, không chỉ trong HQL

Ví dụ:

~~~java
List<PurchaseOrder> orders = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.status = :status
    """, PurchaseOrder.class)
    .setParameter("status", OrderStatus.OPEN)
    .getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
~~~

Nếu Customer được lazy load và không có batch/second-level cache giúp đỡ, vòng lặp có thể tạo thêm nhiều SELECT. HQL đầu tiên không chứa các SELECT đó; chúng phát sinh khi truy cập association.

Giải pháp tùy use case: `join fetch` to-one, entity graph, DTO projection hoặc batch fetching. Không đổi mọi association thành EAGER để xử lý triệu chứng.

## 9. Pagination: kiểm tra SQL chứ không chỉ setMaxResults

API JPA:

~~~java
query.setFirstResult(offset);
query.setMaxResults(pageSize);
~~~

để Hibernate sinh pagination phù hợp dialect.

SQL có thể dùng:

- `LIMIT ... OFFSET`.
- `OFFSET ... FETCH`.
- Cấu trúc subquery/window function thích hợp.
- Cách diễn đạt khác theo database/version.

### 9.1. Không phụ thuộc vào một cú pháp LIMIT riêng

Nếu ứng dụng cần JPQL portable, `setMaxResults()` và `setFirstResult()` là một cách biểu đạt pagination ở tầng JPA, thay vì chèn cú pháp `LIMIT 20` vào query như một extension HQL hay native SQL.

HQL nâng cao có thể hỗ trợ cú pháp giới hạn trực tiếp; dùng nó là một quyết định phụ thuộc Hibernate, không phải JPQL mặc định.

### 9.2. Luôn có ORDER BY ổn định

Ví dụ:

~~~hql
order by o.createdAt desc, o.id desc
~~~

Nếu chỉ order theo `createdAt`, nhiều Order có cùng timestamp có thể đổi thứ tự giữa các lần phân trang. Thêm ID làm tie-breaker ổn định, phù hợp khi ID duy nhất.

### 9.3. Pagination với collection fetch join

Một HQL có `join fetch o.lines` và đồng thời `setMaxResults(20)` có thể dẫn tới pagination trong bộ nhớ thay vì trên database để tránh cắt collection. Khi đó một request tưởng tải 20 Order lại có thể kéo về rất nhiều hàng SQL.

Có thể bật:

~~~properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

để biến một số trường hợp pagination không an toàn trên collection fetch thành lỗi, tùy Hibernate version.

Giải pháp phổ biến:

1. Query phân trang **ID root** trước.
2. Query thứ hai fetch collection cho các ID đó.
3. Nếu cần nhiều collection to-many, chia thêm truy vấn.
4. Giữ thứ tự page root theo danh sách ID/ORDER BY ban đầu.

## 10. EXPLAIN và execution plan: database thực sự làm gì?

SQL do Hibernate sinh chỉ là câu lệnh được gửi. Database optimizer quyết định cách thực hiện: index scan, table scan, join order, hash join, nested loop, sorting, materialization hoặc các chiến lược khác.

Với PostgreSQL, ví dụ:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.id, o.created_at
FROM purchase_orders o
WHERE o.status = 'COMPLETED'
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20;
~~~

`EXPLAIN` cho kế hoạch ước lượng; `EXPLAIN ANALYZE` trên PostgreSQL **thực thi câu lệnh** để thu thập số liệu runtime.

**Cảnh báo:** Với DML như UPDATE/DELETE, EXPLAIN ANALYZE có thể thực sự thay đổi dữ liệu. Không chạy trên production chỉ để “xem cho biết”. Hãy dùng môi trường thử nghiệm có dữ liệu đại diện, cân nhắc transaction/rollback có kiểm soát và những tác dụng phụ ngoài transaction.

### 10.1. Đọc gì trong execution plan?

Các điểm cần quan sát:

- Estimated rows so với actual rows.
- Sequential scan hay index scan.
- Join algorithm và join order.
- Rows removed by filter.
- Sort/hash cost, memory và disk spill.
- Execution time và planning time.
- Buffer hits/reads, I/O wait nếu DB cung cấp.
- Thời gian chờ lock hoặc contention qua công cụ phù hợp.

Một SQL ngắn có thể chậm vì thiếu index hoặc phân phối dữ liệu; một SQL dài có thể nhanh nếu optimizer chọn plan tốt. Không suy ra performance từ độ dài SQL.

### 10.2. Sử dụng bind values đại diện

Một query parameterized có thể có plan khác nhau theo tính chọn lọc của tham số. Nếu thường chỉ dùng status=COMPLETED nhưng bảng 99% hàng đều COMPLETED, index trên status có thể không mang lợi ích như với một status rất hiếm.

Khi benchmark, dùng data distribution, row counts và parameter values gần workload thật. Không chỉ test với bảng 20 hàng.

### 10.3. Statistics của Hibernate và EXPLAIN bổ sung cho nhau

- Hibernate Statistics trả lời **bao nhiêu statement/entity load/cache hit**.
- SQL log/inspector trả lời **statement nào được tạo**.
- Database EXPLAIN/profiling trả lời **statement thực thi ra sao**.
- Tracing/metrics trả lời **latency toàn request** gồm cả Java, mạng và DB.

Không có một công cụ duy nhất trả lời hết bốn nhóm câu hỏi.

## 11. Cách phân loại mức độ phụ thuộc vào tính năng riêng

Một hệ thống dùng Hibernate có ít nhất bốn loại phụ thuộc cần quản lý:

| Loại | Ví dụ | Hệ quả |
| --- | --- | --- |
| JPQL/JPA chuẩn | Entity path, parameter binding, setMaxResults | Di động giữa JPA provider hơn, nhưng SQL vẫn khác theo dialect |
| Hibernate HQL extension | CTE, window functions, set operators nâng cao, lateral join | Phụ thuộc Hibernate version, có thể không được strict JPQL compliance chấp nhận |
| Hibernate ORM behavior/API | `@Fetch`, `@BatchSize`, SQL comments, `StatementInspector` | Phụ thuộc implementation và semantics của Hibernate |
| Database-specific | PostgreSQL JSON operators, vendor functions, lock hints | Phụ thuộc DB product/version và dialect/function support |

Một truy vấn có thể thuộc **nhiều loại cùng lúc**. Ví dụ HQL sử dụng `function('...')` là cú pháp có thể đi qua ORM nhưng tên hàm bên trong có thể chỉ chạy trên PostgreSQL.

### 11.1. Không nhầm “Hibernate hỗ trợ” với “mọi database hỗ trợ”

Hibernate có thể parse một cấu trúc HQL nhưng database/dialect hiện tại không thể thực thi SQL tương đương. Ví dụ recursive CTE cần database hỗ trợ đệ quy; Hibernate không thể tự biến một DB không có recursive CTE thành DB có recursive CTE chỉ bằng chuyển đổi query.

Một số cấu trúc khác có thể được Hibernate mô phỏng khi dialect thiếu cú pháp gốc, nhưng mô phỏng có thể có giới hạn hoặc chi phí khác.

### 11.2. Không nhầm “hàm chạy được trong HQL” với “hàm chuẩn”

Ví dụ:

~~~hql
select function('date_trunc', 'day', o.createdAt)
from PurchaseOrder o
~~~

`function(...)` giúp gọi function database theo tên. Nhưng `date_trunc` không phải hàm có cùng semantics và availability trên mọi RDBMS.

Có thể Hibernate/dialect hỗ trợ một hàm trừu tượng tương đương, hoặc dự án tự đăng ký function cho mỗi dialect. Nếu không, đây là dependency cụ thể vào database.

### 11.3. Chọn phụ thuộc có chủ đích

Một số tính năng riêng rất đáng dùng, ví dụ index đặc thù, JSONB hoặc full-text search. Khi dùng hãy:

1. Nêu rõ vì sao chức năng đó cần thiết.
2. Ghi nhận DB/version tối thiểu.
3. Định nghĩa nơi đặt truy vấn chuyên biệt.
4. Viết integration test trên DB thật.
5. Ghi nhận fallback hoặc chính sách không hỗ trợ DB khác.
6. Theo dõi rủi ro nâng version ORM/dialect.

Mục tiêu là **quản lý portability**, không phải hy sinh mọi khả năng database để giữ một mức trừu tượng giả tạo.

## 12. Strict JPQL compliance: tìm extension vô tình

Hibernate có setting:

~~~properties
hibernate.jpa.compliance.query=true
~~~

Khi bật query compliance, Hibernate cố gắng bắt buộc truy vấn theo phạm vi JPQL chuẩn thay vì chấp nhận nhiều mở rộng HQL.

Điều này hữu ích khi dự án có yêu cầu chuyển JPA provider hoặc muốn duy trì một subset JPQL portable.

### 12.1. Ví dụ một HQL extension

Hibernate HQL nâng cao có thể dùng window function:

~~~hql
select o.customer.id,
       o.id,
       row_number() over (
           partition by o.customer.id
           order by o.createdAt desc, o.id desc
       )
from PurchaseOrder o
~~~

Một query như vậy có thể chạy trên Hibernate 6.x với dialect phù hợp, nhưng không nên coi đây là JPQL chuẩn portable giữa mọi provider.

Khi strict JPQL compliance được bật, extension tương ứng có thể bị từ chối. Đó là tín hiệu để quyết định:

- Viết lại bằng JPQL portable.
- Chuyển query sang một adapter Hibernate-specific có test phù hợp.
- Hoặc chấp nhận extension, tắt strict mode theo chính sách dự án và ghi nhận phụ thuộc.

### 12.2. Không dùng strict mode như bằng chứng duy nhất của portability

Một query đi qua parser strict JPQL vẫn có thể phụ thuộc vào:

- Mapping vendor-specific trên entity.
- SQL function được đăng ký khác nhau.
- Database collation.
- Cách xử lý NULL, timezone và kiểu dữ liệu.
- Khả năng dialect sinh SQL đúng.

Vì vậy **strict JPQL compliance là một lớp kiểm soát ngôn ngữ**, không phải chứng chỉ chạy giống nhau trên mọi RDBMS.

### 12.3. Áp dụng có chiến lược

Nếu toàn dự án phụ thuộc Hibernate-specific features hợp pháp, bật strict compliance toàn cục có thể khiến nhiều query ngừng chạy. Có thể phân loại truy vấn:

- Vùng JPQL portable cần strict contract.
- Vùng Hibernate HQL nâng cao chấp nhận phụ thuộc provider.
- Vùng native SQL riêng theo DB.

Đừng cố ép một query Hibernate-specific thành “portable” chỉ bằng việc tắt cảnh báo.

## 13. HQL nâng cao: những nơi dễ gặp phụ thuộc không chủ đích

### 13.1. CTE và recursive CTE

Hibernate 6.2+ hỗ trợ các dạng HQL `WITH` và recursive CTE trong môi trường phù hợp. Truy vấn đệ quy yêu cầu database có năng lực recursion.

Ví dụ khái niệm:

~~~hql
with Tree as (
    select n.id as id, 0 as depth
    from Category n
    where n.id = :rootId

    union all

    select c.id as id, parent.depth + 1 as depth
    from Tree parent
    join Category c on c.parent.id = parent.id
)
select t.id, t.depth
from Tree t
~~~

Đây là HQL extension; không mặc định portable qua mọi JPA provider, cũng không chạy khi dialect/database không hỗ trợ recursive CTE.

Cần kiểm tra SQL do Hibernate sinh, mức hỗ trợ `SEARCH`/`CYCLE`, khả năng chặn vòng lặp và execution plan.

### 13.2. Window functions

Ví dụ:

~~~hql
select o.id,
       row_number() over (
           partition by o.customer.id
           order by o.createdAt desc
       )
from PurchaseOrder o
~~~

Một số database hỗ trợ window functions nhưng có khác biệt về cú pháp, frame semantics hoặc function cụ thể. Hibernate có thể cung cấp cú pháp HQL tương đương ở một số trường hợp, nhưng không đảm bảo mọi function/window frame đều dịch được giống nhau.

### 13.3. Set operations

HQL có thể hỗ trợ `union`, `intersect` và `except` trong các phiên bản phù hợp. Database có thể khác nhau về những toán tử được hỗ trợ trực tiếp, kiểu cột, thứ tự và khả năng pagination trên kết quả hợp nhất.

Không trộn các kiểu dữ liệu không tương thích hoặc dựa vào thứ tự kết quả khi không có `ORDER BY` cuối.

### 13.4. Lateral joins

HQL nâng cao có thể diễn đạt lateral subquery join trong môi trường Hibernate hỗ trợ. Một số dialect có cú pháp tương ứng, số khác cần mô phỏng hoặc không thể biểu diễn đầy đủ.

Lateral join có thể là giải pháp tốt cho top-N per group, nhưng cần xem SQL thực tế và execution plan. Nếu Hibernate mô phỏng, cost có thể khác dự đoán.

### 13.5. JSON, array và vendor functions

JSON/array functions có thể rất mạnh trong PostgreSQL và các DB hiện đại, nhưng tên hàm, toán tử, kiểu dữ liệu và indexing khác nhau.

Ví dụ một cách gọi function qua HQL:

~~~hql
select function('vendor_json_function', e.payload)
from EventRecord e
~~~

Tên ở đây là **placeholder minh họa**, không phải hàm SQL thật. Trong code production, phải xác định đúng DB function, mapping return type và dialect registration. Nếu muốn hỗ trợ nhiều DB, thiết kế adapter hoặc abstract function contract rõ ràng.

### 13.6. Locking và isolation

Một JPA lock mode như:

~~~java
em.find(
    PurchaseOrder.class,
    orderId,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

có thể dẫn tới SQL `FOR UPDATE` hoặc lock hints khác nhau theo dialect. Không nên giả định DB nào cũng có cùng cú pháp, phạm vi lock, NOWAIT/SKIP LOCKED behavior hoặc isolation semantics.

Kiểm tra cả SQL và concurrency tests trên database thật.

## 14. Native SQL: khi nào chọn thay HQL?

`createNativeQuery()` gửi SQL native theo database schema:

~~~java
List<?> rows = em.createNativeQuery("""
    select o.id, o.created_at
    from purchase_orders o
    where o.status = :status
    order by o.created_at desc
    """)
    .setParameter("status", "COMPLETED")
    .getResultList();
~~~

Native SQL phù hợp khi cần tính năng database-specific không thể biểu đạt hoặc không hiệu quả qua HQL.

Tuy nhiên, nó tạo thêm các trách nhiệm:

- Dùng table/column names thật, không phải entity/property names.
- Quản lý result mapping hoặc DTO conversion.
- Tự kiểm soát portability theo DB.
- Cân nhắc synchronization với persistence context và flush.
- Không mặc nhiên có entity lifecycle callbacks/dirty checking cho bulk native DML.
- Cân nhắc query cache, second-level cache và invalidation nếu thay đổi dữ liệu.

### 14.1. Không nhầm native SQL với JPQL

~~~hql
from PurchaseOrder o
where o.customer.name = :name
~~~

không phải SQL native hợp lệ nếu database không có bảng tên PurchaseOrder/property path customer.name. Ngược lại:

~~~sql
select *
from purchase_orders
where customer_id = ?
~~~

không phải JPQL chuẩn vì dùng table/column names.

### 14.2. Native SQL không tự là “nhanh hơn”

Một câu native query có thể rất nhanh nếu tận dụng tính năng DB, nhưng cũng có thể tạo plan tệ hoặc bỏ qua một số tối ưu ORM. Đo và so sánh trước khi đổi. Tránh rewrite toàn bộ query sang native chỉ vì thấy SQL Hibernate dài.

## 15. Khác biệt giữa database về NULL, Boolean, thời gian và collation

Một truy vấn trông như portable ở tầng HQL có thể có khác biệt kết quả vì **semantics dữ liệu** giữa DB.

### 15.1. NULL ordering

Không có `NULLS FIRST/LAST` rõ ràng, cách sắp thứ tự các giá trị NULL có thể khác giữa database. Hibernate có thể dịch cú pháp sắp NULL theo dialect nếu hỗ trợ.

Với pagination, khác biệt thứ tự NULL có thể khiến hàng nằm ở trang khác nhau. Khi nghiệp vụ cần thứ tự cố định, biểu đạt rõ semantics và test theo từng DB.

### 15.2. String collation và phân biệt hoa thường

`where c.name = :name` có thể khác nhau theo collation của cột/database: phân biệt hoa thường, dấu tiếng Việt, Unicode normalization và accent sensitivity.

Một query HQL giống hệt nhau có thể trả kết quả khác trên hai DB có collation khác. Đừng chỉ test với ASCII tên đơn giản.

### 15.3. Date/time và timezone

Java `Instant`, `LocalDateTime`, `OffsetDateTime` và SQL timestamp types có semantics khác nhau. Các phép `extract`, `date_trunc`, cast hoặc filter theo ngày có thể phụ thuộc timezone session và dialect.

Nếu query “đơn trong hôm nay” cần chính xác, hãy xác định timezone nghiệp vụ và kiểu cột, ưu tiên bind một khoảng thời gian rõ ràng thay vì dựa mơ hồ vào giờ local của DB.

### 15.4. Numeric precision và phép chia

Một biểu thức aggregate, division hoặc cast có thể trả kiểu/precision khác theo DB. Khi tính tiền, dùng `BigDecimal` và cột numeric có precision/scale rõ, tránh phụ thuộc vào phép chia số nguyên hoặc cast ngầm.

### 15.5. Identifier quoting

Tên table/column trùng reserved keywords hoặc phụ thuộc chữ hoa/chữ thường có thể cần quoting. Dialect có thể sinh dấu nháy phù hợp, nhưng đặt tên schema nhất quán sẽ giảm rủi ro.

## 16. Khi nào nên viết function abstraction riêng?

Nếu ứng dụng cần một thao tác như “truncate timestamp về ngày” trên nhiều DB, có một số hướng:

1. Dùng function chuẩn/HQL abstraction nếu provider hỗ trợ đúng semantics.
2. Đăng ký custom SQL function ở tầng Hibernate/dialect cho các DB mục tiêu.
3. Viết repository/adapter riêng theo dialect.
4. Tính boundary ở Java và bind tham số, ví dụ lọc theo `createdAt >= start` và `createdAt < end` thay cho một hàm trên cột.

Ví dụ cách thứ tư:

~~~hql
select o
from PurchaseOrder o
where o.createdAt >= :startInclusive
  and o.createdAt < :endExclusive
~~~

Có thể giữ query portable hơn, tránh gọi hàm lên indexed timestamp column và giúp optimizer sử dụng range index dễ hơn trong nhiều trường hợp.

Nhưng không phải mọi tính năng có thể rewrite về dạng này. Chọn cách phù hợp với domain và dữ liệu.

### 16.1. Một tên function chưa đủ đảm bảo semantics

Hai DB có thể có cùng tên function nhưng xử lý timezone, format, rounding hoặc NULL khác nhau. Nếu đăng ký một function abstraction để chạy nhiều DB, phải **test kết quả**, không chỉ test query parse thành công.

### 16.2. Không cần tránh mọi DB extension

Một doanh nghiệp đã chuẩn hóa PostgreSQL và không có kế hoạch hỗ trợ DB khác có thể hợp lý khi dùng JSONB, partial indexes hoặc full-text search. Điều cần làm là ghi rõ phạm vi hỗ trợ và có integration tests, không giả vờ đây là truy vấn JPQL portable.

## 17. Kiểm tra correctness, không chỉ SQL syntax

Một query đã parse thành công và database chạy xong vẫn có thể sai nghiệp vụ. Với HQL nâng cao cần kiểm tra:

- Join có làm mất row optional do INNER JOIN không?
- Điều kiện tenant/authorization có áp dụng cho mọi nhánh của query không?
- Aggregate có bị nhân đôi vì join to-many không?
- WHERE trên LEFT JOIN có làm biến semantics thành inner-like filter không?
- DISTINCT có che duplication logic thay vì sửa nguyên nhân không?
- Pagination có bị thiếu/nhân hàng không?
- Recursive CTE có loop hoặc đi qua node ngoài scope không?
- Bulk DML có bỏ qua version/tenant/soft-delete rules không?
- Query có trả cả soft-deleted entities ngoài ý định không?

### 17.1. Ví dụ JOIN biến ý nghĩa kết quả

~~~hql
select o
from PurchaseOrder o
left join o.lines l
where l.quantity > 5
~~~

Dù dùng LEFT JOIN, điều kiện `l.quantity > 5` trong WHERE có thể loại Order không có line. Nếu muốn giữ Order dù không có line, cần thiết kế điều kiện JOIN/filter phù hợp với semantics thật và kiểm tra SQL.

### 17.2. COUNT và to-many join

~~~hql
select count(o)
from PurchaseOrder o
join o.lines l
where o.status = :status
~~~

Đoạn query đếm hàng sau join, nên một Order có nhiều line có thể được đếm nhiều lần. Nếu mục tiêu là số lượng Order phân biệt, có thể cần:

~~~hql
select count(distinct o.id)
from PurchaseOrder o
join o.lines l
where o.status = :status
~~~

Đừng chỉ sửa khi thấy count quá lớn; hiểu tại sao SQL nhân hàng để chọn phương pháp đúng.

### 17.3. Bulk UPDATE/DELETE và version

Một bulk HQL:

~~~hql
update PurchaseOrder o
set o.status = :newStatus
where o.status = :oldStatus
~~~

không đi qua vòng đời dirty checking từng managed entity giống `em.find()` rồi setter. Vì vậy không nên mặc định `@Version` được kiểm tra/tăng như entity UPDATE, hoặc callbacks sẽ chạy cho mọi hàng.

Nếu nghiệp vụ cần optimistic concurrency hoặc audit, phải thiết kế bulk DML phù hợp; kiểm tra SQL/row count và xử lý persistence context stale.

## 18. Test portability theo ma trận môi trường

Một dự án có thể chạy HQL trên H2 khi test và PostgreSQL khi production. Việc test xanh trên H2 **không chứng minh** PostgreSQL có cùng cú pháp, type mapping, collation, lock semantics hoặc query plan.

Một ma trận kiểm thử thực tế:

| Môi trường | Mục đích | Lưu ý |
| --- | --- | --- |
| Unit tests | Xác minh service/domain logic | Không thay thế SQL execution |
| H2/in-memory integration tests | Test nhanh mapping và một số JPQL | Không đại diện đầy đủ cho DB production |
| Testcontainers dùng DB production | Test SQL/dialect/function/constraints thực | Nên có cho query quan trọng |
| DB phụ thứ hai (nếu sản phẩm hỗ trợ) | Kiểm tra portability thật | Chạy test contract chung |
| Staging với dữ liệu gần production | Đánh giá plan/latency/row counts | Cần số liệu và phân phối dữ liệu đại diện |

### 18.1. Một test contract cho nhiều DB

Một query repository có thể có cùng bộ test đầu vào/đầu ra:

- Order có hoặc không có Customer.
- Nhiều OrderLine làm tăng JOIN rows.
- Trạng thái hợp lệ và giá trị NULL.
- Timestamps ở ranh giới ngày/tháng.
- Trùng `createdAt` để kiểm tra pagination ổn định.
- Tên có tiếng Việt và khác hoa/thường.
- Decimal với precision quan trọng.
- Dữ liệu nhiều tenant.

Nếu hỗ trợ hai database, chạy cùng test contract trên cả hai. Chỉ có việc SQL parse thành công chưa đủ: kết quả và invariant phải tương đương.

### 18.2. Có cần so sánh SQL nguyên văn không?

Với portable query, **không nên** snapshot toàn bộ SQL exact string qua mọi Hibernate version/dialect như một hợp đồng bất biến. Hibernate có thể đổi alias, layout, thứ tự join hoặc bind markers mà semantics vẫn tương đương.

Hãy assert các thuộc tính bền vững hơn:

- Số SQL statements trong một use case được cô lập.
- Không có full table scan với dataset lớn khi yêu cầu có index thích hợp.
- Không có pagination trong memory ngoài ý muốn.
- Có tenant/version predicate khi cần.
- Result rows/DTO đúng.
- Có hoặc không có những JOIN quan trọng theo thiết kế.
- Query được thực thi trên DB mục tiêu.

SQL snapshot có thể hữu ích trong test chuyên biệt, nhưng chấp nhận rằng upgrade Hibernate/dialect có thể đòi cập nhật snapshot sau khi đánh giá semantics.

## 19. Kiểm tra query trên chính database sản xuất mục tiêu

Quy trình cho một HQL nâng cao:

1. Viết HQL dùng entity/property rõ ràng.
2. Chạy integration test trên DB product/version mục tiêu.
3. Bật Hibernate SQL log hoặc StatementInspector trong test.
4. Ghi nhận số statements của toàn use case.
5. Chọn SQL và bind values đại diện.
6. Chạy `EXPLAIN`/profiler trong môi trường an toàn.
7. Kiểm tra actual rows, JOIN strategy, index và sorting.
8. Kiểm tra dữ liệu đầu ra cho edge cases.
9. Thử tải lớn và tình huống concurrency nếu nghiệp vụ nhạy cảm.
10. Ghi nhận liệu query dùng JPQL standard, Hibernate extension hay vendor feature.

### 19.1. Một bài test để tránh N+1

Test có thể tạo 10 Order với Customer riêng, load danh sách, rồi đọc `customer.name`. Dùng StatementInspector hoặc thống kê trong context được cô lập để xác định số SQL thực tế.

Nếu mục tiêu là một statement cho danh sách và Customer to-one, có thể viết:

~~~hql
select o
from PurchaseOrder o
join fetch o.customer
where o.status = :status
order by o.id
~~~

Sau đó xác nhận không có SELECT phụ khi code đọc Customer. Nhưng nếu mapping hoặc nhu cầu thay đổi, phép assert nên đánh giá đúng use case chứ không biến “một SQL” thành yêu cầu bất di bất dịch cho mọi workload.

### 19.2. Một bài test để tránh collection pagination trong memory

Bật `hibernate.query.fail_on_pagination_over_collection_fetch=true` trong test. Chạy use case phân trang có collection; nếu query vi phạm, test sẽ phát hiện thay vì chỉ âm thầm lấy toàn bộ rows.

Sau đó áp dụng two-step pagination hoặc fetch strategy thích hợp.

### 19.3. Một bài test kiểm tra vendor function

Nếu repository có:

~~~hql
select function('date_trunc', 'day', o.createdAt)
from PurchaseOrder o
~~~

test trên database thực tế, kiểm tra type/kết quả theo timezone và dữ liệu mẫu. Nếu sản phẩm tuyên bố hỗ trợ nhiều DB, test function equivalent trên từng dialect hoặc thay thế bằng khoảng thời gian portable.

## 20. Query plan cache và dữ liệu bind

Hibernate có query interpretation/plan caching tùy phiên bản và configuration. Database cũng có thể cache prepared statements/execution plans.

Vì vậy khi benchmark:

- Chạy warmup trước khi đo latency ổn định.
- Phân biệt compile/parse cost với execution cost.
- Đo cold vs warm caches khi phù hợp.
- Đo nhiều lần với parameter values khác nhau.
- Kiểm tra dữ liệu đã nằm trong persistence context/second-level cache hay chưa.
- Tránh kết luận một query nhanh chỉ vì lần thứ hai `find()` không gửi SQL.

Không nên dùng đúng một phép đo thời gian trên laptop làm chuẩn production.

### 20.1. Dễ nhầm cache hit với SQL không được sinh

Nếu entity đã nằm trong first-level cache, `find()` có thể không phát SQL. Nếu bật second-level cache hoặc query cache, việc tải cũng có thể khác. Khi kiểm tra logic sinh SQL, cần xác định rõ cache nào đang hoạt động.

### 20.2. IN-list và SQL shape

HQL:

~~~hql
select o
from PurchaseOrder o
where o.id in :ids
~~~

có thể sinh SQL với nhiều placeholders, phụ thuộc số phần tử và cấu hình parameter padding. Database cũng có giới hạn số bind parameters. Với tập ID lớn, cần chia batch hoặc dùng chiến lược khác; đừng mặc định một query `IN :ids` luôn ổn với danh sách hàng chục nghìn ID.

## 21. Truy vết tính năng riêng trong codebase

Để tránh phụ thuộc ngoài chủ đích, nên có tiêu chuẩn review đối với mỗi HQL/query mới.

### 21.1. Những dấu hiệu cần xem kỹ

- `with ... as (...)` và recursive CTE.
- `over (partition by ...)`, window frame, ordered-set aggregate.
- `lateral`, derived roots hoặc set operators.
- `function('vendor_name', ...)`.
- HQL `limit`/`offset` trực tiếp.
- Native SQL có JSON/array operators, vendor-specific cast hoặc hints.
- `@Formula`, `@Subselect`, `@SQLRestriction`, `@Fetch` và các annotation Hibernate-specific.
- Pessimistic locking với NOWAIT/SKIP LOCKED hoặc timeout đặc biệt.
- DML bulk đi đường riêng so với managed entity.
- SQL comments/StatementInspector/custom function registration.

Danh sách này là dấu hiệu **cần nhận diện**, không phải danh sách phải cấm.

### 21.2. Ghi chú ngắn về phụ thuộc

Một mô tả nhỏ trong repository/test có thể chứa:

~~~text
Query: findLatestOrderPerCustomer
Purpose: lấy đơn mới nhất của mỗi khách hàng
Language: Hibernate HQL (không tuyên bố JPQL portable)
Feature: ROW_NUMBER window function
Minimum ORM: Hibernate version theo dependency quản lý
Database contract: PostgreSQL và SQL Server được hỗ trợ
Tests: query contract chạy trên cả hai DB
Fallback: query hai bước nếu thêm dialect không hỗ trợ
Performance: index customer_id + created_at được đánh giá
~~~

Không cần viết tài liệu dài cho từng query đơn giản. Nhưng một feature có thể phá portability cần có **owner và quyết định kỹ thuật rõ ràng**.

### 21.3. Tập trung query chuyên biệt

Nếu một báo cáo dùng tính năng riêng PostgreSQL, có thể tách nó vào repository adapter/implementation có tên rõ ràng thay vì trộn vào hàng chục service.

Ví dụ:

~~~java
public interface RevenueReportPort {
    List<RevenueRow> summarize(Instant from, Instant to);
}
~~~

Một implementation dùng SQL riêng PostgreSQL có thể chịu trách nhiệm về dialect/function, test và tối ưu plan. Nếu sau này thêm DB khác, phạm vi thay đổi dễ nhận diện hơn.

## 22. So sánh ba cách triển khai một yêu cầu

Yêu cầu: lấy 20 đơn hàng mới nhất có trạng thái COMPLETED.

### 22.1. JPQL/JPA portable

~~~java
List<PurchaseOrder> result = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """, PurchaseOrder.class)
    .setParameter("status", OrderStatus.COMPLETED)
    .setMaxResults(20)
    .getResultList();
~~~

Ưu điểm:

- Truy vấn ở phạm vi JPQL cơ bản.
- Hibernate dịch pagination theo dialect.
- Dễ chạy trên các JPA provider khác hơn.

Vẫn cần kiểm tra execution plan và index.

### 22.2. Hibernate HQL extension

~~~hql
select o
from PurchaseOrder o
where o.status = :status
order by o.createdAt desc, o.id desc
limit 20
~~~

Nếu Hibernate version hỗ trợ cú pháp trực tiếp, query có thể gọn. Nhưng cách viết gắn với HQL extension thay vì chỉ dựa vào `setMaxResults()` của API JPA.

Ưu điểm nhỏ về tiện dụng không nhất thiết bù rủi ro portability khi ứng dụng có yêu cầu hỗ trợ JPA provider khác.

### 22.3. Native SQL

~~~sql
SELECT o.*
FROM purchase_orders o
WHERE o.status = ?
ORDER BY o.created_at DESC, o.id DESC
LIMIT 20;
~~~

Đây là dạng SQL phù hợp với PostgreSQL/MySQL phổ biến, nhưng không phải cú pháp pagination của mọi database. Native SQL còn cần mapping kết quả và kiểm tra dialect cụ thể.

Ba cách có thể trả cùng dữ liệu, nhưng **hợp đồng portability và mức kiểm soát SQL khác nhau**.

## 23. Những lỗi hiểu sai phổ biến

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “HQL được Hibernate parse là JPQL chuẩn.” | Hibernate HQL có nhiều extension ngoài JPQL. |
| “Một HQL tạo đúng một SQL.” | Lazy loading, auto-flush, cascade và fetch strategy có thể tạo thêm statements. |
| “SQL log có UPDATE nghĩa đã commit.” | SQL có thể thuộc transaction sẽ rollback. |
| “Có dấu ? nghĩa query chưa bind parameter.” | Prepared statement bind values riêng qua JDBC. |
| “Không thấy SQL là Hibernate lỗi.” | Có thể do first-level/second-level cache hoặc query chưa được thực thi. |
| “Một query luôn nhanh hơn ba query.” | Một query Cartesian có thể trả nhiều hàng lặp hơn. |
| “DISTINCT luôn loại Cartesian product.” | DISTINCT entity result không loại mọi tổ hợp child rows. |
| “setMaxResults bảo đảm DB chỉ xử lý 20 hàng.” | Collection fetch join có thể gây pagination trong memory. |
| “Hibernate 6 và 5 dùng cùng bind logger.” | Logger categories đã thay đổi. |
| “StatementInspector thấy tất cả bind values.” | Inspector chủ yếu nhận SQL template, không phải JDBC bind log. |
| “EXPLAIN ANALYZE chỉ xem plan, không thực thi.” | Trên một số DB, ANALYZE thực thi query; DML có thể có side effect. |
| “Strict JPQL compliance bảo đảm mọi DB giống nhau.” | Còn mapping, function, collation, types và dialect differences. |
| “Function('x') là portable vì JPQL hỗ trợ function.” | Tên và semantics của function x có thể vendor-specific. |
| “HQL recursive CTE chạy được nếu Hibernate hiểu cú pháp.” | Database/dialect cũng phải hỗ trợ recursion. |
| “Đổi sang native SQL luôn tối ưu hơn.” | Cần đo plan, IO và latency thực tế. |
| “H2 test xanh nghĩa production SQL chắc đúng.” | H2 không thay thế integration test trên DB production. |
| “Các alias SQL phải giữ nguyên khi nâng Hibernate.” | Alias và SQL layout là chi tiết implementation, có thể thay đổi. |
| “Dùng database extension là thiết kế sai.” | Có thể tốt nếu phụ thuộc được ghi nhận, kiểm thử và vận hành có chủ đích. |

## 24. Quy trình thực hành từ HQL tới SQL

Có thể áp dụng quy trình sau cho một query quan trọng trước khi release:

1. **Viết yêu cầu nghiệp vụ:** cần trả những hàng/cột nào, cardinality, pagination và quyền truy cập.
2. **Viết HQL/JPQL:** chọn entity/property path, parameter binding, fetch plan.
3. **Gắn nhãn portability:** JPQL chuẩn, Hibernate extension hay vendor-specific.
4. **Bật quan sát trong test:** Hibernate SQL DEBUG, bind TRACE khi an toàn hoặc StatementInspector.
5. **Chạy use case đầy đủ:** kể cả mapper/serializer truy cập lazy associations.
6. **Đếm statements:** phân biệt SQL chính, N+1, auto-flush và batch/subselect.
7. **Đọc SQL sinh ra:** kiểm tra JOIN, filter, sort, pagination, DML, lock.
8. **Đọc execution plan:** chọn DB product/version và parameters gần production.
9. **Kiểm tra correctness:** NULL, duplicate, aggregate, multi-tenant, timezone, concurrent updates.
10. **Kiểm thử tính di động:** nếu hỗ trợ nhiều DB, chạy cùng contract tests trên từng DB.
11. **Ghi nhận phụ thuộc có chủ đích:** function, dialect, index, minimum version và fallback.
12. **Giám sát sau release:** latency, slow queries, statement count và regressions sau upgrade.

Quy trình này giúp biến “ORM tự sinh SQL” từ một hộp đen thành một cơ chế có thể quan sát và kiểm soát.

## 25. Bài tập thực hành

### Bài 1 — HQL và SQL khác nhau thế nào?

Cho HQL:

~~~hql
select o.id, o.customer.name
from PurchaseOrder o
where o.status = :status
~~~

Hãy liệt kê những JOIN/cột mà Hibernate có thể cần khi chuyển sang SQL. Vì sao không được dự đoán tên alias SQL chính xác chỉ từ HQL?

### Bài 2 — Bật SQL và bind logging

Viết cấu hình Spring Boot cho Hibernate 6 để xem SQL và JDBC bind parameters trong môi trường test. Tại sao không nên bật bind TRACE trên production?

### Bài 3 — N+1

Một service tải 100 Order rồi lặp qua `order.getCustomer().getName()`. Hibernate SQL log có 101 SELECT. Hãy xác định nguyên nhân, đề xuất ít nhất hai cách xử lý và giải thích vì sao “một SELECT” không tự là mục tiêu hiệu năng cuối cùng.

### Bài 4 — DISTINCT và Cartesian product

Order có 10 lines và 8 tags. Nếu một query JOIN FETCH cả hai, kết quả SQL có thể có bao nhiêu tổ hợp hàng cho một Order? `DISTINCT` trên root entity có loại bỏ hoàn toàn số hàng đó không?

### Bài 5 — Pagination trong memory

Một query dùng collection fetch join với `setMaxResults(20)`. Vì sao Hibernate có thể phải tải rất nhiều hàng trước khi trả 20 roots? Hãy mô tả chiến lược page root IDs trước, fetch collection sau.

### Bài 6 — Vendor function

Một query dùng:

~~~hql
select function('date_trunc', 'day', o.createdAt)
from PurchaseOrder o
~~~

Hãy phân loại mức phụ thuộc của query. Cần test những gì nếu ứng dụng tuyên bố hỗ trợ cả PostgreSQL và SQL Server?

### Bài 7 — Strict compliance

Nếu bật `hibernate.jpa.compliance.query=true` và một query dùng window function bị từ chối, hãy nêu ba hướng giải quyết và trade-off của mỗi hướng.

### Bài 8 — EXPLAIN ANALYZE

Một developer chạy `EXPLAIN ANALYZE DELETE FROM purchase_orders WHERE ...` trên production để đo hiệu năng. Rủi ro là gì? Nên thực hiện kiểm tra plan thế nào cho an toàn?

### Bài 9 — Cache và thống kê

Hai lần gọi `em.find()` cùng ID trong một EntityManager chỉ có một SELECT. Vì sao? Làm cách nào kiểm tra SQL load trong transaction/context mới?

### Bài 10 — Ma trận DB

Một query HQL dùng recursive CTE và `CYCLE` chạy trên một DB nhưng lỗi ở DB khác. Hãy xác định những tầng cần kiểm tra: Hibernate version, HQL grammar, dialect và database support.

### Bài 11 — Bulk update và optimistic locking

Một bulk HQL UPDATE sửa `status` hàng nghìn Order nhưng không tự tăng version. Nếu các service khác dựa vào `@Version`, điều gì có thể xảy ra? Hãy đề xuất một cách bảo vệ concurrency có chủ đích.

### Bài 12 — Thiết kế một query contract

Một màn hình báo cáo cần tổng doanh số theo tháng, không được vượt tenant hiện tại và phải chạy trên hai DB. Hãy ghi lại kết quả kỳ vọng, semantics timezone, aggregate, filter tenant, phụ thuộc function và các integration tests cần có.

### Gợi ý trả lời

- **Bài 1:** Property path `o.customer.name` có thể làm phát sinh JOIN; SQL alias là chi tiết của Hibernate/dialect.
- **Bài 2:** SQL DEBUG và `org.hibernate.orm.jdbc.bind` TRACE; parameter log có thể lộ dữ liệu nhạy cảm.
- **Bài 3:** Lazy association trong vòng lặp; cân nhắc fetch join to-one, entity graph hoặc DTO/batch fetching; vẫn cần đo rows và latency.
- **Bài 4:** 10 × 8 = 80 tổ hợp; DISTINCT không xóa mọi dữ liệu join chéo.
- **Bài 5:** Pagination theo SQL rows có thể cắt collection nên Hibernate lấy nhiều rows rồi giới hạn roots trong memory; dùng page IDs trước.
- **Bài 6:** Cú pháp function đi qua HQL nhưng function cụ thể phụ thuộc DB; cần test return type, semantics và dialect.
- **Bài 7:** Viết lại JPQL portable, cô lập HQL extension, hoặc dùng native SQL theo DB; mỗi hướng có chi phí khác nhau.
- **Bài 8:** Trên PostgreSQL EXPLAIN ANALYZE thực thi DML; dùng môi trường an toàn và dữ liệu đại diện, tránh side effect production.
- **Bài 9:** Persistence context/first-level cache; dùng context mới hoặc clear khi phù hợp.
- **Bài 10:** Hibernate parse được không có nghĩa DB chạy được; kiểm tra SQL sinh ra và năng lực recursive CTE/SEARCH/CYCLE.
- **Bài 11:** Bulk DML có thể làm version contract bị bỏ qua; cần tăng/kiểm tra version hoặc cơ chế concurrency khác trong command.
- **Bài 12:** Test trên cả hai database, xác định timezone và monthly boundaries, áp dụng tenant predicate, kiểm tra aggregate và index/plan.

---

## Kết luận

**HQL là ý định truy vấn ở tầng ORM; SQL sinh ra là thứ database thực thi.** Muốn tối ưu và đảm bảo correctness, cần quan sát SQL, JDBC parameters, số statements, dữ liệu trả về và execution plan — không chỉ đọc HQL hoặc đếm số dòng code.

**Tính di động là một quyết định thiết kế, không phải mặc định của Hibernate.** HQL có nhiều extension mạnh hơn JPQL; dialect có thể dịch một số khác biệt nhưng không thể bù cho mọi năng lực database. Hãy dùng feature đặc thù khi có lợi ích rõ ràng, đồng thời ghi nhận dependency, test trên database thực tế và giữ một phương án triển khai/khả năng nâng cấp có chủ đích.
