# StatementInspector để quan sát hoặc xử lý SQL có chủ đích trong Hibernate ORM

Trong Hibernate ORM, ứng dụng thường viết JPQL/HQL, Criteria API hoặc thao tác trên entity; Hibernate sinh SQL tương ứng rồi chuyển đến JDBC. Khi cần quan sát SQL thực sự được chuẩn bị để gửi cho database, hoặc áp một thay đổi SQL rất cụ thể, Hibernate cung cấp extension point **`StatementInspector`**.

Ví dụ, một nhóm phát triển muốn biết truy vấn nào do Hibernate chuẩn bị khi màn hình chi tiết đơn hàng chạy, muốn đánh dấu một số SQL bằng comment cố định để tra cứu trong database logs, hoặc cần áp một optimizer hint cho một truy vấn có dạng đã được kiểm thử trên một dialect cụ thể. Những yêu cầu ấy liên quan **câu SQL đã được Hibernate dựng**, không đơn thuần là nội dung JPQL ban đầu.

`StatementInspector` cho phép nhận chuỗi SQL ngay trước khi Hibernate chuẩn bị JDBC statement:

```java
package org.hibernate.resource.jdbc.spi;

public interface StatementInspector extends java.io.Serializable {

    String inspect(String sql);
}
```

Đây là chữ ký giản lược thể hiện hợp đồng cốt lõi của API trong Hibernate ORM; cách khai báo chi tiết có thể khác nhẹ theo phiên bản.

- Hibernate đưa vào `inspect(String sql)` chuỗi SQL chuẩn bị gửi đến JDBC.
- **Trả `null`** để Hibernate sử dụng SQL gốc, không thay đổi.
- **Trả một `String`** để Hibernate sử dụng chuỗi được trả về làm SQL thay thế.
- Inspector có thể dùng để **quan sát** hoặc **chỉnh sửa SQL có chủ đích**, nhưng không phải nơi phù hợp để viết lại toàn bộ logic truy vấn, xây cơ chế bảo mật từ thao tác chuỗi hoặc thực hiện nghiệp vụ.

Điểm đặc biệt là cùng một extension point rất dễ tạo ra hai kết quả trái ngược: nếu chỉ quan sát cẩn thận, nó giúp chẩn đoán Hibernate; nếu sửa SQL bằng quy tắc mơ hồ, nó có thể làm thay đổi semantics, phá parameter binding hoặc làm ứng dụng lỗi trên dialect khác.

Bài học giải thích vị trí của StatementInspector trong pipeline, cách đăng ký trong Hibernate và Spring, thread-safety, quan sát SQL, tagging, optimizer hints có kiểm soát, ranh giới với logging/interceptor/events, transaction, SQL cache, tenant security, các kỹ thuật kiểm thử và những sai lầm thường gặp.

---

## 1. StatementInspector nằm ở đâu trong đường đi của một truy vấn?

Xét service:

```java
@Transactional(readOnly = true)
public OrderDetail getOrder(Long orderId) {
    PurchaseOrder order = entityManager.find(
        PurchaseOrder.class,
        orderId
    );

    return mapper.toDetail(order);
}
```

Hibernate có thể cần chuẩn bị SQL:

```sql
select o.id, o.status, o.created_at
from purchase_orders o
where o.id = ?
```

Trước khi tạo `PreparedStatement` phù hợp, Hibernate chuyển chuỗi SQL qua `StatementInspector` nếu được cấu hình.

```text
Application service
        |
        v
EntityManager / Hibernate Session
        |
        +-- find, persist, flush, HQL, Criteria, native Query
        |
        v
Mapping + query translation / SQL generation
        |
        v
SQL string sau khi Hibernate sinh
        |
        v
StatementInspector.inspect(sql)
        |
        +-- return null    -> giữ SQL gốc
        |
        +-- return String  -> dùng SQL thay thế
        |
        v
JDBC statement preparation
        |
        v
Bind parameters / execute
        |
        v
Database
```

### 1.1. Điều StatementInspector nhận được

Đầu vào là **chuỗi SQL**, không phải:

- Entity Java đang managed.
- HQL/JPQL AST gốc.
- `CriteriaQuery`/`CriteriaUpdate` object.
- Danh sách Java parameter values đã được bind.
- Kết quả JDBC `ResultSet`.
- Thông tin statement đã thực thi thành công hay thất bại.
- Execution plan thực tế của database.

Ví dụ SQL có placeholder:

```sql
select c.id, c.email
from customers c
where c.organization_id = ?
  and c.active = ?
```

Inspector thấy chuỗi trên, nhưng **không tự nhận giá trị** của `organization_id` và `active` tương ứng với các dấu `?`. Giá trị bind diễn ra qua cơ chế JDBC riêng.

### 1.2. Vì sao thời điểm trước khi prepare quan trọng?

Một câu SQL chỉ có thể thực thi sau khi driver/database nhận đúng cú pháp với các placeholders. Nếu inspector thay đổi chuỗi:

```java
return "select * from ...";
```

thì Hibernate vẫn cố bind parameters dựa trên metadata trước đó. Nếu câu mới có số lượng/thứ tự tham số khác, hệ thống có thể gặp lỗi binding hoặc tệ hơn là sai semantics.

Vì vậy, **không viết lại số lượng, thứ tự hoặc ý nghĩa placeholders** bằng StatementInspector trừ khi bạn kiểm soát toàn bộ đường sinh SQL/metadata và có cơ chế chuyên dụng. Trong phần lớn ứng dụng, chỉ nên quan sát hoặc thêm comment/hint an toàn đã kiểm thử.

## 2. Hợp đồng inspect(String sql)

Một implementation tối giản:

```java
import org.hibernate.resource.jdbc.spi.StatementInspector;

public final class NoOpStatementInspector
        implements StatementInspector {

    @Override
    public String inspect(String sql) {
        return null;
    }
}
```

Trả `null` nghĩa là “không thay đổi câu SQL”.

Một implementation trả lại đúng chuỗi đã nhận:

```java
@Override
public String inspect(String sql) {
    return sql;
}
```

cũng giữ nguyên nội dung SQL, nhưng thường dùng `null` để biểu đạt rõ “không chỉnh sửa”.

### 2.1. Trả SQL thay thế

```java
@Override
public String inspect(String sql) {
    return "/* app:catalog-read */ " + sql;
}
```

Đoạn trên thêm một SQL comment cố định cho **mọi** statement đi qua inspector. Đây chỉ là minh họa cách thay đổi chuỗi, chưa phải thiết kế production: mọi INSERT/UPDATE/DELETE/SELECT đều có comment, có thể tăng noise trong logs hoặc tương tác với SQL/dialect đặc biệt.

### 2.2. Không có hợp đồng sửa SQL sau execute

`StatementInspector` không có callback kiểu:

```java
afterExecute(sql, rows, elapsedTime, exception)
```

Do đó không thể chỉ dựa vào inspector để thu thập chính xác:

- Số row thực sự trả về.
- Thời gian JDBC execute.
- Thời gian chờ network/locks.
- Thông báo SQLSTATE khi thất bại.
- Số batch executions thực tế.
- Rows affected sau execute.

Muốn những thông tin này, hãy dùng JDBC instrumentation, database monitoring, Micrometer/tracing, Hibernate statistics hoặc các công cụ thích hợp ở tầng khác.

### 2.3. Inspector không phải event listener của entity

`@PrePersist`, `@PreUpdate`, `@PostLoad`, Hibernate event listeners hay interceptor có thông tin entity/lifecycle. `StatementInspector` chỉ thấy chuỗi SQL đã sinh.

Nếu yêu cầu là “khi Customer đổi trạng thái thì tạo domain event”, StatementInspector không phải hook đúng; nên xử lý ở domain/application service, outbox hoặc event integration thích hợp.

## 3. Ví dụ chỉ quan sát SQL

Một inspector đơn giản cho môi trường phát triển:

```java
import org.hibernate.resource.jdbc.spi.StatementInspector;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class ObservingSqlInspector
        implements StatementInspector {

    private static final Logger log =
        LoggerFactory.getLogger(ObservingSqlInspector.class);

    @Override
    public String inspect(String sql) {
        if (log.isDebugEnabled()) {
            log.debug("SQL about to be prepared: {}", sql);
        }

        return null;
    }
}
```

Mục đích:

- Tập trung theo dõi SQL Hibernate chuẩn bị.
- Không sửa SQL.
- Tắt chi phí logging phần lớn khi DEBUG không bật.
- Dùng logger với cấu hình rõ ràng thay vì in console trực tiếp.

### 3.1. Những gì cần thận trọng khi log toàn bộ SQL

Dù Hibernate thường dùng `?` cho giá trị bind, SQL vẫn có thể chứa:

- Literal do ứng dụng đưa vào native SQL.
- Hints, comments hoặc tên bảng/cột chứa thông tin hạ tầng.
- Tên schema/tenant được đưa vào SQL khi dùng mô hình multi-tenancy đặc thù.
- SQL rất dài từ điều kiện `IN` hoặc generated expressions.
- Những chi tiết nghiệp vụ không nên xuất hiện ở hệ thống log công khai.

Vì vậy không nên mặc định bật full SQL DEBUG trên production với retention dài hoặc log pipeline không kiểm soát access.

### 3.2. Nên cân nhắc quan sát metadata thay vì SQL nguyên văn

Nếu mục tiêu chỉ là biết có bao nhiêu statements được chuẩn bị, inspector có thể ghi counter mà không lưu toàn bộ nội dung SQL.

```java
import java.util.concurrent.atomic.LongAdder;
import org.hibernate.resource.jdbc.spi.StatementInspector;

public final class CountingSqlInspector
        implements StatementInspector {

    private final LongAdder preparedCandidates =
        new LongAdder();

    @Override
    public String inspect(String sql) {
        preparedCandidates.increment();
        return null;
    }

    public long inspectedCount() {
        return preparedCandidates.sum();
    }
}
```

Tên `preparedCandidates` cố ý diễn đạt “số lần inspect được gọi”, **không phải số câu SQL thực sự đã execute thành công**. Một câu SQL có thể bị chuẩn bị nhiều lần hoặc statement reuse/batching làm số lượt execution khác số lượt inspect.

### 3.3. Counter toàn SessionFactory không phải metric theo request

Nếu inspector được dùng chung toàn `SessionFactory`, counter ghi nhận nhiều requests/threads. Số `inspectedCount()` không biểu diễn số SQL của một API request cụ thể.

Muốn correlation per-request, cần thiết kế context/tracing an toàn, phù hợp thread model và không dựa vào mutable field dùng chung.

## 4. Cấu hình StatementInspector cho SessionFactory

Trong Hibernate ORM, có setting thông dụng:

```properties
hibernate.session_factory.statement_inspector=com.example.persistence.ObservingSqlInspector
```

Giá trị có thể được cấu hình bằng class name hoặc một instance qua bootstrap/programmatic configuration, tùy cách ứng dụng khởi tạo Hibernate và phiên bản.

Ví dụ cấu hình một class:

```java
public final class ObservingSqlInspector
        implements StatementInspector {

    public ObservingSqlInspector() {
    }

    @Override
    public String inspect(String sql) {
        return null;
    }
}
```

Khi provider tự khởi tạo từ class name, constructor/configuration requirements phụ thuộc cơ chế bootstrap. Nếu inspector cần Spring DI, đừng giả định Hibernate tạo class sẽ tự inject mọi Spring bean; nên truyền một **instance** qua integration phù hợp.

### 4.1. Phạm vi SessionFactory

Một inspector cấu hình ở `SessionFactory` có thể được dùng bởi các Session do factory tạo. Do đó, nó phải được thiết kế **thread-safe** khi được chia sẻ giữa nhiều transactions.

Sai:

```java
public final class UnsafeInspector
        implements StatementInspector {

    private String lastSql;
    private String currentUserId;

    @Override
    public String inspect(String sql) {
        lastSql = sql;
        return "/* user:" + currentUserId + " */ " + sql;
    }
}
```

Nếu inspector singleton được nhiều threads dùng:

- `lastSql` bị ghi đè bởi request khác.
- `currentUserId` có thể không thuộc caller hiện tại.
- Thông tin user có thể bị lộ vào SQL comment.
- Đường xử lý phụ thuộc race giữa requests.

### 4.2. Tốt hơn: immutable configuration

```java
public final class StableCommentInspector
        implements StatementInspector {

    private final String marker;

    public StableCommentInspector(String marker) {
        this.marker = marker;
    }

    @Override
    public String inspect(String sql) {
        return "/* " + marker + " */ " + sql;
    }
}
```

Chỉ dùng `marker` khi nó là **giá trị cố định, do ứng dụng kiểm soát**, không chứa SQL comment terminator hoặc untrusted input. Ví dụ này thêm comment vào mọi SQL; trong thực tế có thể giới hạn áp dụng theo điều kiện.

### 4.3. Không giữ EntityManager trong inspector

Inspector thường được gọi **trong lúc Hibernate đang chuẩn bị SQL**. Đừng inject EntityManager rồi chạy một HQL query khác bên trong `inspect` để kiểm tra user/tenant. Điều đó có nguy cơ:

- Re-entrant SQL preparation/recursive invocation.
- Thay đổi transaction/persistence context không mong muốn.
- N+1 queries và deadlocks.
- Vòng lặp inspector gọi query, query lại gọi inspector.

Inspector nên làm việc nhẹ, không gọi database hoặc remote service.

## 5. Đăng ký trong Spring Boot

Trong các cấu hình Spring Boot dùng JPA/Hibernate, property của Hibernate có thể được truyền qua Spring Boot:

```properties
spring.jpa.properties.hibernate.session_factory.statement_inspector=com.example.persistence.ObservingSqlInspector
```

Với cách này Hibernate thường có trách nhiệm khởi tạo class. Nó phù hợp một inspector không cần dependency injection phức tạp.

### 5.1. Dùng HibernatePropertiesCustomizer để truyền bean instance

Trong các phiên bản Spring Boot hỗ trợ `HibernatePropertiesCustomizer`, có thể tạo inspector như Spring bean:

```java
import org.hibernate.resource.jdbc.spi.StatementInspector;

import org.springframework.boot.autoconfigure.orm.jpa.HibernatePropertiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SqlInspectionConfiguration {

    @Bean
    public StatementInspector statementInspector() {
        return new ObservingSqlInspector();
    }

    @Bean
    public HibernatePropertiesCustomizer inspectorCustomizer(
            StatementInspector statementInspector) {

        return properties -> properties.put(
            "hibernate.session_factory.statement_inspector",
            statementInspector
        );
    }
}
```

Điểm quan trọng:

- `StatementInspector` là instance được Spring tạo và quản lý.
- Hibernate nhận instance khi SessionFactory khởi tạo.
- Không cần mỗi Session tự tạo inspector.
- Nếu dùng chung singleton, implementation phải thread-safe.
- Package/API của `HibernatePropertiesCustomizer` và cách bootstrap có thể thay đổi theo Spring Boot major version; cần đối chiếu dependencies thực tế.

### 5.2. Không cấu hình trùng hai nguồn thiếu kiểm soát

Nếu vừa đặt property class name vừa truyền instance qua customizer, giá trị cuối cùng có thể phụ thuộc thứ tự cấu hình. Chỉ nên có **một nguồn cấu hình hiệu lực** cho inspector, hoặc một composite inspector chủ đích kết hợp các chức năng.

### 5.3. Chỉ bật ở môi trường thích hợp

Có thể dùng Spring profiles hoặc conditional configuration:

```java
@Configuration
@Profile("sql-observation")
public class SqlObservationConfiguration {
    // Beans dành cho môi trường muốn quan sát SQL.
}
```

Tuy nhiên, nếu đang điều tra lỗi production, bạn có thể cần cơ chế bật/tắt có kiểm soát và logging policy tương ứng. Đừng dùng profile như một quyền truy cập bảo mật; phải kiểm soát ai có thể thay đổi cấu hình.

## 6. Đăng ký per-Session khi cần phạm vi hẹp

Hibernate native APIs có thể cho phép chọn inspector riêng khi tạo một Session:

```java
import org.hibernate.Session;
import org.hibernate.SessionFactory;

Session session = sessionFactory
    .withOptions()
    .statementInspector(new ObservingSqlInspector())
    .openSession();

try (session) {
    // Sử dụng Session phù hợp với transaction.
}
```

Ví dụ minh họa việc gắn inspector cho Session; transaction phải được quản lý theo mô hình ứng dụng.

### 6.1. Ưu điểm của per-Session inspector

- Có thể cô lập SQL inspection cho một unit of work.
- Có thể tạo inspector chỉ dành cho integration test.
- Có thể thu thập statements của một Session cụ thể mà không ảnh hưởng mọi Session.
- Tránh giữ mutable request-specific fields trong inspector singleton.

### 6.2. Giới hạn trong Spring-managed JPA

Với Spring Data JPA thông thường, EntityManager được tạo/quản lý bởi transaction infrastructure. Bạn không thể mặc định gọi `sessionFactory.withOptions()` rồi mong Session mới tự tham gia đúng transaction/cùng persistence context của `@Transactional` hiện tại.

Nếu cần per-request/per-transaction inspection trong Spring:

- Đánh giá giải pháp logging/tracing/JDBC instrumentation phù hợp.
- Hoặc có một abstraction được thiết kế rõ để tạo Session scoped.
- Không trộn hai Session khác nhau trong cùng use case chỉ vì muốn gắn inspector.
- Kiểm tra transaction manager, connection và entity identity boundaries.

## 7. Quan sát SQL nào có thể xuất hiện?

Hibernate có thể chuẩn bị nhiều loại SQL từ các đường khác nhau:

```java
em.find(Customer.class, id);                // SELECT
em.persist(new Customer(...));              // INSERT khi flush
managedCustomer.changeName("New");          // UPDATE khi flush
em.remove(managedCustomer);                 // DELETE khi flush
em.createQuery(hql).getResultList();        // SELECT
em.createQuery(bulkHql).executeUpdate();    // bulk DML
em.createNativeQuery(sql).getResultList();  // Native SQL qua Hibernate
```

`StatementInspector` hoạt động ở tầng SQL chuẩn bị qua Hibernate, nên thường có thể quan sát những statement Hibernate đưa qua pipeline đó.

### 7.1. Không phải mọi câu JDBC trên connection đều đi qua inspector

Không tự động bao phủ:

- `JdbcTemplate` chạy trực tiếp qua DataSource.
- Code gọi `connection.prepareStatement(...)` ngoài Hibernate.
- Migration Flyway/Liquibase chạy bằng connection riêng.
- Database triggers phát sinh statement nội bộ.
- SQL chạy bởi service/process khác.
- Stored procedure nội bộ sinh thêm nhiều SQL trong database.

Nếu yêu cầu là **quan sát mọi JDBC statement của ứng dụng**, một DataSource/JDBC proxy hoặc APM instrumentation thường là công cụ phù hợp hơn.

### 7.2. SQL cho fetch lazy

Một method service tưởng chỉ có một `find` có thể phát thêm SQL khi truy cập lazy association:

```java
Customer c = em.find(Customer.class, id);
int count = c.getOrders().size();
```

Inspector có thể cho thấy SELECT nạp Customer và một SELECT khác cho orders nếu association chưa được initialize và provider cần tải dữ liệu.

Dựa vào điều này, có thể phát hiện các kiểu N+1 query. Tuy nhiên, **inspector không tự kết luận N+1**; cần tương quan số statement theo use case cùng dữ liệu test/trace.

### 7.3. SQL batch

Hibernate có thể chuẩn bị một SQL INSERT rồi dùng JDBC batch để gửi nhiều parameter sets. Inspector không nhất thiết được gọi một lần cho mỗi row được insert.

Đừng so số lần `inspect` với số bản ghi đã ghi để đo throughput hay độ hiệu quả JDBC batching.

## 8. Phân biệt StatementInspector với Hibernate SQL logging

Để quan sát SQL mà không cần viết extension, Hibernate đã có logging settings.

Ví dụ:

```properties
hibernate.show_sql=true
hibernate.format_sql=true
hibernate.use_sql_comments=true
```

Các cấu hình này có vai trò khác nhau:

- `show_sql` có thể in SQL Hibernate phát sinh, thường ra console/standard output theo cơ chế Hibernate.
- `format_sql` định dạng SQL dễ đọc hơn.
- `use_sql_comments` cho phép Hibernate thêm comments chứa thông tin/truy vấn phù hợp vào SQL trong một số đường thực thi.

### 8.1. Logger Hibernate SQL

Ở Hibernate 6, cấu hình logger thường dùng:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Logger bind có thể khác giữa Hibernate major versions; ở nhánh cũ thường gặp logger `org.hibernate.type.descriptor.sql.BasicBinder`.

**Bind parameter logging có thể chứa PII và secrets**, nên chỉ bật khi thật sự cần, trong môi trường có kiểm soát hoặc với redaction/retention thích hợp.

### 8.2. Khi nào nên dùng logging thay vì inspector?

Nếu mục tiêu duy nhất là “xem câu SQL Hibernate gửi đi”:

1. Bật logger SQL phù hợp.
2. Dùng tracing/correlation context ở log pipeline.
3. Kiểm tra query count bằng Hibernate statistics/tests nếu cần.

Không nhất thiết phải viết `StatementInspector` chỉ để thay thế logger đã có.

### 8.3. Khi nào inspector có lợi hơn?

Inspector hữu ích khi bạn cần **chủ động xử lý chuỗi SQL trước khi chuẩn bị**, ví dụ:

- Đính kèm marker SQL comment ổn định.
- Thu thập dấu hiệu query shape phục vụ một integration test.
- Áp optimizer hint trên một câu SQL đã được nhận diện chắc chắn.
- Kiểm tra có chủ đích những SQL shapes do một mapping tạo ra.

Dù vậy, không phải mục tiêu quan sát nào cũng cần sửa SQL.

## 9. Phân biệt SQL inspection với parameter binding

HQL:

```java
List<Customer> rows = em.createQuery("""
    select c
    from Customer c
    where c.email = :email
      and c.organizationId = :orgId
    """, Customer.class)
    .setParameter("email", email)
    .setParameter("orgId", orgId)
    .getResultList();
```

Inspector thường thấy SQL dạng:

```sql
select c.id, c.email, c.organization_id
from customers c
where c.email = ?
  and c.organization_id = ?
```

Nó không nhận object:

```text
parameters = {
    1: "alice@example.com",
    2: "org-123"
}
```

### 9.1. Không tự nối bind values vào SQL string

Một cách làm nguy hiểm:

```java
String rewrittenSql = sql.replace(
    "?",
    "'" + userInput + "'"
);
```

Cách này vừa sai khi có nhiều parameters, vừa làm mất prepared-statement safety, vừa có nguy cơ SQL injection, escaping lỗi và sai kiểu dữ liệu.

Không dùng StatementInspector để “hiển thị full SQL với values” bằng cách tự thay `?`.

### 9.2. Công cụ phù hợp để quan sát binds

- Logger Hibernate bind ở level có kiểm soát.
- JDBC proxy có khả năng logging parameters.
- Tracing/APM phù hợp.
- Hibernate statistics cho số lượng/hiệu năng tổng quan.
- Database logs/slow-query analyzer theo khả năng DB.

Mỗi công cụ có mức rủi ro bảo mật riêng. Không bật logging secrets trong production chỉ vì debug.

## 10. Thêm comment cố định để nhận diện truy vấn

Một nhu cầu hợp lệ là gắn marker vào câu SQL phục vụ tìm kiếm trong database diagnostics.

```java
public final class SqlMarkerInspector
        implements StatementInspector {

    @Override
    public String inspect(String sql) {
        return "/* app:crm-hibernate */ " + sql;
    }
}
```

Marker ổn định được quản lý bởi code; trong nhiều dialect, SQL comment đứng trước statement là hợp lệ.

### 10.1. Vì sao phải là marker ổn định?

Một comment biến đổi theo request:

```text
/* request=51e... */ SELECT ...
/* request=8d7... */ SELECT ...
/* request=409... */ SELECT ...
```

làm SQL text khác nhau ở mỗi request. Điều này có thể:

- Tăng cardinality trong SQL metrics.
- Làm giảm hiệu quả statement/plan cache ở driver/database.
- Làm noisy database logs.
- Rò correlation IDs vào log lưu lâu.
- Tạo SQL comment injection nếu marker lấy từ nguồn không tin cậy.

Đối với truy vấn lặp lại nhiều, ưu tiên marker **theo loại operation/version**, không phải user ID/request ID động, trừ khi DB/monitoring setup đã được kiểm chứng.

### 10.2. Chỉ thêm comment khi dialect hỗ trợ vị trí đó

`/* ... */` là SQL comment phổ biến, nhưng không nên khẳng định mọi driver, statement type, procedure, dialect và vị trí comment đều cư xử như nhau.

Nếu thêm comment vào statements nhạy với vị trí cú pháp hoặc nhiều statement batches, cần integration tests trên database mục tiêu.

### 10.3. Comment không thay thế tracing

Comment giúp nhóm SQL trong logs. Để theo dõi đầy đủ request, hãy dùng distributed tracing/MDC/JDBC instrumentation có correlation IDs ở đúng tầng, thay vì biến mọi SQL text thành một truy vấn mới.

## 11. Chỉ xử lý những câu SQL được chọn rõ ràng

Không nên dùng một inspector để rewrite mọi `SELECT` theo pattern chung.

Ví dụ một ứng dụng muốn đánh dấu riêng query danh sách đơn hàng. Ý tưởng:

```java
@Override
public String inspect(String sql) {
    if (sql.toLowerCase(Locale.ROOT)
           .contains("from purchase_orders")) {

        return "/* app:order-query */ " + sql;
    }

    return null;
}
```

Đoạn này **chỉ nên xem là bản minh họa sơ bộ** vì substring matching còn nhiều lỗ hổng:

- SQL alias và quoting có thể thay đổi.
- Query có JOIN đến `purchase_orders` nhưng root thực chất là entity khác.
- Tên bảng có thể xuất hiện trong subquery/comment/string literal.
- Case/formatting có thể khác.
- Query DELETE/UPDATE cũng có thể chứa chuỗi tương tự.
- Mapping đổi table name làm inspector ngừng hoạt động.

### 11.1. Ưu tiên marker từ query do ứng dụng kiểm soát

Hibernate Query API có thể hỗ trợ `setComment(...)`:

```java
var query = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.customer.id = :customerId
    order by o.createdAt desc
    """, PurchaseOrder.class);

query.unwrap(org.hibernate.query.Query.class)
     .setComment("orders-by-customer-v1");

List<PurchaseOrder> orders = query
    .setParameter("customerId", customerId)
    .getResultList();
```

Khi cấu hình SQL comments tương ứng được bật, Hibernate có thể đưa comment do Query định nghĩa vào generated SQL. Inspector có thể nhận diện một marker **nội bộ, ổn định** thay vì đoán theo tên bảng:

```java
@Override
public String inspect(String sql) {
    if (sql.contains("orders-by-customer-v1")) {
        // Ví dụ: chỉ quan sát query đã gắn marker.
        return null;
    }
    return null;
}
```

Việc marker xuất hiện ở dạng nào phụ thuộc Hibernate version/settings và cách SQL comments được render, nên cần test trên SQL thực tế. Marker này không phải cơ chế bảo mật; caller/application phải kiểm soát nguồn comment.

### 11.2. Không gắn comment tùy ý từ đầu vào người dùng

Nếu một API cho phép client truyền query comment raw, attacker có thể tạo log injection, comment termination hoặc làm thay đổi SQL nếu inspector nối chuỗi bất cẩn.

Chỉ chấp nhận marker nằm trong whitelist nội bộ (chữ/số/dấu nối hữu hạn), không chứa `*/`, newline, quote hoặc SQL fragments.

## 12. Áp optimizer hint: trường hợp xử lý SQL có chủ đích

Một số database hỗ trợ optimizer hints trong SQL comment hoặc cú pháp đặc biệt. Ví dụ **Oracle-specific**:

```sql
select /*+ INDEX(o IDX_ORDERS_CUSTOMER) */
       o.id, o.status
from purchase_orders o
where o.customer_id = ?
```

Đây là minh họa SQL cho một dialect và schema có index tương ứng, **không phải cú pháp JPQL portable hay lời khuyên luôn ép index**.

StatementInspector có thể được dùng để chèn hint trong những hoàn cảnh được kiểm soát:

1. Xác định đúng query shape.
2. Xác định đúng database dialect/version.
3. Đặt hint đúng vị trí mà optimizer nhận.
4. Không đổi placeholders hoặc projection.
5. Kiểm tra execution plan và kết quả sau khi rewrite.
6. Có rollback/feature flag nếu plan xấu đi.

### 12.1. Vì sao không viết một regex để thêm hint vào mọi SELECT?

Các câu SQL Hibernate có thể bắt đầu bằng:

```sql
select ...
with recursive ...
/* comment */ select ...
select distinct ...
insert into ... select ...
update ...
```

Một regex kiểu:

```java
sql.replaceFirst("select", "select /*+ HINT */")
```

có thể gặp `select` trong comment, subquery, CTE hoặc identifier/string literal. Nó không bảo đảm sửa đúng SELECT statement cần tác động.

Một SQL parser phù hợp hoặc extension/hint API chuyên biệt của Hibernate/dialect thường đáng tin cậy hơn khi yêu cầu rewrite phức tạp.

### 12.2. Ví dụ cấu hình chặt, giới hạn scope

Một inspector có cấu hình immutable và chỉ chèn comment/hint nếu nhận đúng marker/query shape:

```java
public final class TargetedHintInspector
        implements StatementInspector {

    private static final String TARGET_MARKER =
        "orders-by-customer-v1";

    @Override
    public String inspect(String sql) {
        if (!sql.contains(TARGET_MARKER)) {
            return null;
        }

        // Chỉ thực hiện nếu đã có trình biến đổi SQL
        // đúng dialect được integration-test.
        return applyVerifiedDialectSpecificHint(sql);
    }

    private String applyVerifiedDialectSpecificHint(
            String sql) {
        // Không cài đặt phép rewrite tổng quát bằng regex.
        // Chỉ cho phép SQL shapes đã nhận diện và test.
        return sql;
    }
}
```

Đây là **skeleton minh họa kiến trúc**, không tuyên bố đã chèn một optimizer hint thực tế. Nếu không có biến đổi đã được kiểm chứng, giữ nguyên SQL.

### 12.3. Khi không nên dùng StatementInspector cho hint

Nếu Hibernate/dialect/query API đã cung cấp cách khai báo hint đáng tin cậy, ưu tiên cơ chế đó để giảm sự phụ thuộc vào SQL string formatting.

Nếu một hint phải đổi theo số parameter hoặc cardinality runtime, cần đo hiệu quả và cân nhắc strategy ở tầng database/query planner thay vì tạo vô số SQL variants.

## 13. Không dùng StatementInspector làm bộ máy bảo mật tenant

Một ý tưởng sai:

```java
@Override
public String inspect(String sql) {
    if (sql.trim().startsWith("select")) {
        return sql + " where organization_id = ?";
    }
    return sql;
}
```

Đoạn này lỗi trên nhiều phương diện:

- SQL có thể đã có WHERE, GROUP BY, ORDER BY hoặc LIMIT.
- Không biết alias của table.
- JOIN và subquery có thể cần tenant predicate ở nhiều nơi.
- Dấu `?` mới không có binding tương ứng.
- UPDATE/DELETE vẫn không được bảo vệ.
- Query có thể chứa nhiều tables với tenant columns khác nhau.
- Hibernate L1/L2 cache có thể trả entity không đi qua SQL SELECT mới.
- Native JDBC ngoài Hibernate không đi qua inspector.

**Không xây tenant isolation bằng cách nối một WHERE vào SQL do Hibernate đã sinh.**

### 13.1. Những cơ chế phù hợp hơn

- Hibernate multi-tenancy/`@TenantId` ở mapping/version hỗ trợ.
- Query restrictions và scoped repositories.
- Security policy kiểm tra organization membership và resource authorization.
- Composite tenant-aware foreign keys/constraints.
- Database row-level security (RLS) với session context đúng.
- Integration tests bảo đảm isolation ở SELECT, INSERT, UPDATE, DELETE, association và cache.

StatementInspector có thể **quan sát** SQL để hỗ trợ kiểm tra tenant predicates, nhưng không nên là chốt bảo vệ duy nhất hoặc nơi tạo tenant predicate bằng string rewrite.

### 13.2. Không dùng regex để chặn SQL nguy hiểm

Một inspector kiểm tra:

```java
if (sql.contains("delete")) {
    throw new SecurityException(...);
}
```

không phải authorization đáng tin cậy. Keyword có thể ở comment, identifier, subquery; quyền xóa cần biết user, resource, action và transaction context. Nếu hệ thống cần cấm DML, dùng database permissions, read-only role hoặc kiến trúc repository phù hợp.

Có thể dùng assert kiểm thử SQL shape ở môi trường test, nhưng không trình bày regex keyword như một policy engine production.

## 14. Phân biệt SQL comments và domain audit

Một comment:

```sql
/* app:approve-invoice */
update invoices set status = ? where id = ?
```

giúp một DBA thấy query liên quan operation nào, nhưng nó không chứng minh:

- Ai đã phê duyệt?
- Quyền đã được kiểm tra?
- Update có thành công?
- Hàng nào thực sự thay đổi?
- Transaction đã commit?
- Event audit đã được ghi?

Audit nghiệp vụ nên là bản ghi **có cấu trúc và bền vững** được tạo ở application/domain layer hoặc database audit mechanism.

### 14.1. Vì sao không ghi audit từ inspect?

Nếu inspector ghi một audit record khi thấy SQL:

```text
inspect("update invoices ...")
    -> "Invoice approved"
```

thông tin ấy có thể sai vì statement sau đó:

- Không được execute.
- Execute nhưng affected rows = 0.
- Execute rồi transaction rollback.
- Fail do FK/constraint/deadlock.
- Là UPDATE của một use case khác.

`inspect` không biết kết quả DB/commit. Dùng transactional outbox/audit table hoặc lifecycle/domain events đúng semantics.

## 15. StatementInspector và Hibernate Interceptor

Hibernate có các extension points khác nhau:

- `StatementInspector`: xử lý SQL string trước JDBC preparation.
- `Interceptor`: một số hook ở mức session/entity/SQL lifecycle tùy version.
- Event listeners (ví dụ persist/update/delete events): can thiệp/quan sát lifecycle entities.
- Jakarta Persistence lifecycle callbacks: `@PrePersist`, `@PostLoad`, `@PreUpdate`, `@PreRemove`...
- Hibernate integrators/services: extension ở mức bootstrap/hạ tầng.

### 15.1. Chọn hook theo dữ liệu cần quan sát

| Yêu cầu | Extension/cơ chế thường phù hợp |
|---|---|
| Xem SQL Hibernate chuẩn bị | SQL logger hoặc `StatementInspector` |
| Thêm comment/hint vào SQL được kiểm soát | `StatementInspector` hoặc query/dialect-specific API |
| Biết entity nào được cập nhật | Entity listeners / domain layer / Hibernate events |
| Kiểm tra điều kiện trước persist | Bean Validation, domain policy, constraints |
| Ghi event nghiệp vụ sau thay đổi | Application service + outbox |
| Đo execute duration và row count | JDBC instrumentation/APM/DB metrics |
| Kiểm tra lazy loading/N+1 | Hibernate statistics, SQL tracing và tests |
| Phân tách tenants và quyền | Hibernate multi-tenancy, repository/authorization/DB policy |
| Sửa HQL/Criteria query semantics | Query construction layer, không phải SQL rewrite muộn |
| Đổi mapping hoặc SQL AST/dialect rendering | Hibernate extension chuyên sâu phù hợp, không phải regex trên SQL |

### 15.2. Không nhầm onPrepareStatement legacy

Một số phiên bản Hibernate cũ từng có những API interceptor liên quan SQL preparation. Khi dùng code mẫu trên internet, hãy kiểm tra **major version**. Với Hibernate ORM hiện đại, `StatementInspector` là extension point rõ ràng cho việc quan sát/biến đổi SQL text trước khi prepare.

Không copy signature từ Hibernate 4/5 vào Hibernate 6/7 mà không xem API tương ứng.

## 16. StatementInspector và HQL/Criteria query construction

HQL:

```java
List<PurchaseOrder> result = em.createQuery("""
    select o from PurchaseOrder o
    where o.customer.id = :customerId
    """, PurchaseOrder.class)
    .setParameter("customerId", customerId)
    .getResultList();
```

Criteria:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> o =
    cq.from(PurchaseOrder.class);

cq.select(o).where(
    cb.equal(o.get("customer").get("id"), customerId)
);

List<PurchaseOrder> result =
    em.createQuery(cq).getResultList();
```

Cả hai cuối cùng có thể sinh SQL được inspector quan sát.

### 16.1. Inspector không biết source API

Một SQL string có thể được sinh từ:

- `find()`.
- HQL.
- Criteria.
- Named query.
- Lazy loading.
- Batch fetching.
- Bulk DML.
- Native SQL qua Hibernate.

Inspector chỉ nhìn SQL string, nên không tự biết query bắt nguồn từ method Java nào. Nếu cần correlation, cần marker/call context/trace instrumentation có kiểm soát.

### 16.2. SQL shape có thể đổi khi mapping đổi

Thay fetch plan, inheritance, pagination, dialect, Hibernate minor version hoặc batch fetch settings có thể tạo SQL khác dù HQL source giữ nguyên. Vì vậy logic phụ thuộc exact SQL string phải được bảo vệ bằng integration tests và giới hạn phạm vi.

## 17. Query plan cache, prepared statements và tác động của SQL rewriting

Rất nhiều database/driver/connection pool dùng SQL text hoặc một dạng normalized text làm phần của statement/plan caching. Cách xử lý comment khác nhau theo sản phẩm và version.

Nếu inspector thêm marker động:

```text
/* request: a1 */ select ...
/* request: a2 */ select ...
/* request: a3 */ select ...
```

thì từ góc nhìn string equality, đây là ba câu SQL khác nhau.

### 17.1. Tác hại có thể gặp

- Prepared statement cache hit rate giảm.
- Query plan cache có thêm entries.
- Tăng compile/parse overhead.
- APM/database monitoring phân tán cùng query shape thành nhiều tên.
- Logs trở nên khó nhóm và tốn storage.
- Có thể làm hỏng nhận diện “slow query” nếu tooling fingerprint dựa trên SQL text.

### 17.2. Không có quy tắc chung cho mọi database

Một số database normalize hoặc bỏ qua comments khi tạo plan cache key; một số driver/công cụ phân biệt text. Vì vậy cần kiểm tra môi trường thực tế.

**Quy tắc an toàn:** marker càng ổn định, scope càng rõ và số biến thể SQL càng ít thì rủi ro càng thấp.

### 17.3. Return null khi không cần rewrite

Đừng luôn tạo một chuỗi mới bằng `sql.replace(...)` chỉ để trả lại SQL không đổi. Nếu không biến đổi, `return null` truyền tải ý định và tránh overhead không cần thiết.

## 18. Thread-safety: SessionFactory inspector được chia sẻ

Một inspector dùng chung có thể bị gọi đồng thời từ nhiều threads:

```text
Request A thread -> Session A -> inspect(SQL A)
Request B thread -> Session B -> inspect(SQL B)
Scheduled job    -> Session C -> inspect(SQL C)
```

Nếu inspector chứa mutable state, phải thiết kế concurrency.

### 18.1. Counter thread-safe

```java
public final class MetricsInspector
        implements StatementInspector {

    private final LongAdder total = new LongAdder();

    @Override
    public String inspect(String sql) {
        total.increment();
        return null;
    }

    public long totalInspected() {
        return total.sum();
    }
}
```

`LongAdder` phù hợp counter có nhiều threads; kết quả `sum()` có thể là snapshot không nguyên tử khi concurrent updates diễn ra, thường chấp nhận cho metrics.

### 18.2. Không dùng ArrayList chung không đồng bộ

Sai:

```java
private final List<String> statements =
    new ArrayList<>();

@Override
public String inspect(String sql) {
    statements.add(sql);
    return null;
}
```

Trong SessionFactory đa luồng, `ArrayList` không thread-safe; còn có nguy cơ giữ vô hạn SQL strings trong memory.

### 18.3. Thu thập theo giới hạn

Với inspector dùng cho test có thể dùng `CopyOnWriteArrayList` hoặc synchronized collection, nhưng chỉ nên thu thập giới hạn trong thời gian test. Với production, dùng bounded buffer/metrics aggregation/sampling và không giữ raw SQL vô hạn.

## 19. Mối quan hệ với MDC và trace context

Một số ứng dụng đặt correlation IDs trong MDC:

```java
String traceId = MDC.get("traceId");
```

Inspector có thể đọc MDC trong cùng thread rồi log SQL kèm trace ID:

```java
@Override
public String inspect(String sql) {
    log.debug("Preparing Hibernate SQL");
    return null;
}
```

Nếu log framework đang đưa `traceId` từ MDC vào log pattern, không cần chèn nó vào SQL string.

### 19.1. Vì sao nên ưu tiên MDC/tracing cho correlation?

- SQL text giữ ổn định.
- Không tăng plan cache cardinality vì trace ID.
- Không lộ token/user ID trong SQL comment.
- Dễ liên kết logs của controller/service/repository.
- Không cần biến đổi SQL do Hibernate sinh.

### 19.2. Lưu ý thread model

MDC thường gắn với thread. Với `@Async`, thread pools hoặc reactive workloads, context không tự được propagate trong mọi cấu hình. Dùng framework tracing/context propagation phù hợp và cleanup đúng.

Inspector không nên lưu `currentTraceId` thành field singleton rồi đổi trước mỗi request.

## 20. SQL formatting, whitespace và dialect

Một câu SQL Hibernate sinh có thể khác nhau theo:

- Dialect.
- Database naming strategy.
- Version Hibernate.
- Mapped inheritance.
- Fetch plan.
- Pagination/locking.
- CTE/window expressions.
- Quoting của identifiers.
- Bật/tắt SQL comments.
- Driver-specific syntax.

Ví dụ cùng nghiệp vụ phân trang có thể dùng:

```sql
-- Một dialect:
select ... from orders order by id
offset ? rows fetch next ? rows only
```

hoặc:

```sql
-- Dialect khác:
select ... from orders order by id
limit ? offset ?
```

### 20.1. Đừng gắn logic rewrite vào dấu cách cố định

Một condition như:

```java
if (sql.startsWith("select * from orders")) ...
```

rất dễ sai vì Hibernate thường select từng cột, có alias, có comment trước `select` hoặc tên bảng đã quote.

Nếu chỉ cần đánh dấu query nội bộ, dùng comment marker hoặc một API query-level phù hợp. Nếu cần rewrite thật, phải thử nhiều SQL shapes và dialect.

### 20.2. Không tự thay tên bảng theo regex

Ví dụ cố đổi:

```java
sql.replace("orders", "orders_archive")
```

có thể thay cả alias, tên cột, string literal hoặc subquery, làm SQL invalid hoặc cập nhật sai bảng.

Table routing/tenancy cần được thiết kế ở mapping/schema/connection level, không ở SQL string post-processing tùy tiện.

## 21. Phân biệt SELECT, INSERT, UPDATE, DELETE nếu chỉ để quan sát

Một inspector có thể muốn đếm các loại statement. Cách đơn giản:

```java
@Override
public String inspect(String sql) {
    String trimmed = sql.stripLeading();

    if (trimmed.regionMatches(
            true, 0, "select", 0, "select".length())) {
        selectCount.increment();
    }

    return null;
}
```

Đoạn minh họa có thể hoạt động với SQL SELECT bắt đầu bằng keyword, nhưng chưa xử lý:

- CTE bắt đầu `WITH`.
- Comments/hints trước keyword.
- `INSERT ... SELECT`.
- Stored procedure syntax.
- DDL hoặc DB-specific statements.
- Keywords trong string literal.

Vì vậy những counters dựa trên prefix chỉ nên được diễn giải **xấp xỉ theo SQL shape đã biết**, không coi là kiểm toán đầy đủ mọi loại DML.

### 21.1. Nếu metrics cần chính xác

Muốn đếm SQL executions/latency/batches theo JDBC, dùng instrumentation ở JDBC/database level, nơi có thông tin statement lifecycle. StatementInspector chỉ là hook tại SQL preparation.

## 22. Exception từ inspector ảnh hưởng transaction thế nào?

Giả sử:

```java
@Override
public String inspect(String sql) {
    if (sql.length() > 10_000) {
        throw new IllegalStateException(
            "Unexpected SQL length"
        );
    }
    return null;
}
```

Nếu inspector ném exception, quá trình chuẩn bị statement có thể bị chặn. Exception có thể lan lên service, khiến transaction bị rollback theo Spring rules khi thoát một `@Transactional` method.

Tuy nhiên:

- Ngưỡng độ dài không chứng minh query nguy hiểm.
- Không nên dùng throws dựa trên heuristic làm security enforcement chính.
- Một production inspector lỗi có thể chặn rất nhiều DB operations.
- SQL length có thể tăng hợp lệ do batch loading/IN predicates.

### 22.1. Fail-open hay fail-closed?

Nếu inspector phục vụ **observability không nhạy cảm**, lỗi instrumentation thường không nên làm hỏng nghiệp vụ; có thể bắt/giảm mức lỗi trong logging/metrics code.

Nếu inspector mang một chính sách SQL rewrite bắt buộc, cần thiết kế chặt chẽ và test; nhưng với security invariant, nên chuyển enforcement sang repository/DB authorization thay vì đặt sinh tử của hệ thống vào inspector.

### 22.2. Đừng nuốt mọi RuntimeException từ code nghiệp vụ

Một inspector không nên gọi domain service, network hoặc repository. Nếu làm vậy rồi nuốt exception, ứng dụng có thể che lỗi; nếu ném ra, nó có thể phá transaction. Thiết kế tốt nhất là giữ code inspector **nhỏ, thuần và xác định**.

## 23. Những thay đổi SQL nào tương đối an toàn?

Theo mức độ rủi ro tăng dần:

| Mục đích | Ví dụ | Mức độ thận trọng |
|---|---|---|
| Quan sát, không sửa | Log SQL shape hoặc counter | Thấp hơn, vẫn phải tránh secrets/overhead |
| Thêm comment ổn định | `/* app:orders-v1 */` | Cần test dialect và cache effects |
| Chèn optimizer hint có mục tiêu | Hint đúng DB/query/version | Cao, kiểm tra execution plan |
| Thay schema/table name | Rewrite SQL identifiers | Rất cao; nên dùng mapping/connection routing |
| Thêm tenant WHERE/security predicate | Nối chuỗi vào SQL | Không phù hợp làm security boundary |
| Thay placeholders/parameter order | Thêm/bớt `?` | Không phù hợp; phá binding metadata |
| Thay SQL command type | UPDATE thành DELETE | Nguy hiểm; không nên |
| Gọi DB/network trong inspector | Lookup policy/audit | Không phù hợp; reentrancy/latency |
| Rewrite query theo user input | Dynamic raw SQL | Nguy cơ injection và data leak |

### 23.1. Điều kiện của một biến đổi SQL có chủ đích

Một rewrite có thể được cân nhắc khi:

1. Có lý do kỹ thuật cụ thể đo được.
2. Target là một SQL shape đã xác định.
3. Không làm thay đổi số lượng/thứ tự JDBC parameters.
4. Không thay đổi business semantics.
5. Hỗ trợ dialect/version được kiểm soát.
6. Có feature flag hoặc rollback mechanism.
7. Có integration tests trên database thật hoặc gần production.
8. Có metrics để phát hiện regression.

Nếu thiếu một trong các yếu tố trên, ưu tiên sửa query/Hibernate mapping hoặc dùng JDBC/database tuning thay vì inspector.

## 24. Ví dụ inspector quan sát SQL phục vụ integration test

Một test inspector:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public final class CapturingStatementInspector
        implements StatementInspector {

    private final CopyOnWriteArrayList<String> sqls =
        new CopyOnWriteArrayList<>();

    @Override
    public String inspect(String sql) {
        sqls.add(sql);
        return null;
    }

    public List<String> snapshot() {
        return List.copyOf(sqls);
    }

    public void clearCaptured() {
        sqls.clear();
    }
}
```

Nó dùng collection thread-safe; phù hợp test nhỏ, **không** dùng làm production logger với SQL vô hạn.

### 24.1. Kiểm thử số SELECT của một use case

Giả sử tạo Session/EntityManager test được gắn inspector phù hợp. Một test có thể:

1. Tạo data fixture.
2. Flush/clear để fixture setup không lẫn SQL đo.
3. Xóa captured statements.
4. Gọi use case truy xuất orders.
5. Quan sát những SQL statements Hibernate chuẩn bị.
6. Xác nhận query shapes hoặc số SELECT trong phạm vi test.

Ví dụ pseudo-test:

```java
inspector.clearCaptured();

service.loadOrderSummaries(customerId);

long selectCount = inspector.snapshot()
    .stream()
    .filter(sql -> sql.stripLeading()
        .toLowerCase(Locale.ROOT)
        .startsWith("select "))
    .count();

assertThat(selectCount)
    .isLessThanOrEqualTo(3);
```

Đây là **test minh họa**; code giả định đã đăng ký inspector vào SessionFactory/Session mà service sử dụng và không có background SQL chen vào. Với CTE hoặc comments trước SELECT, heuristic prefix cần điều chỉnh.

### 24.2. Đừng test exact SQL string không cần thiết

Exact SQL thường thay đổi theo Hibernate version, quoting, alias, dialect và select-column order. Test so sánh nguyên văn từng ký tự có thể giòn.

Ưu tiên kiểm thử:

- Số lượng statement tương đối.
- Query có JOIN/FK predicate quan trọng.
- Không có N+1 trong use case.
- Kết quả nghiệp vụ đúng.
- Rewritten SQL được database chấp nhận khi có hint/comment.

Nếu cần assert exact SQL cho một rewrite, đó phải là integration test chủ đích gắn với Hibernate/dialect version cụ thể.

## 25. SQL comments theo từng query thay vì sửa toàn bộ bằng inspector

Một lựa chọn nhẹ hơn cho SQL tagging là Hibernate `Query.setComment(...)`.

```java
var query = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.status = :status
    """, PurchaseOrder.class);

query.unwrap(org.hibernate.query.Query.class)
     .setComment("orders-list-by-status-v1");

List<PurchaseOrder> orders = query
    .setParameter("status", "READY")
    .getResultList();
```

Khi `hibernate.use_sql_comments` được bật và API provider render comment, generated SQL có thể mang marker đã định nghĩa.

### 25.1. Khi nào đủ dùng setComment?

Nếu mục tiêu chỉ để:

- Nhận ra query trong SQL log.
- Phân biệt các query quan trọng.
- Hỗ trợ DBA/tracing xem nguồn truy vấn.

thì `setComment` có thể đủ, không cần tự viết inspector.

### 25.2. Khi nào vẫn cần inspector?

Nếu yêu cầu là biến đổi cuối đường SQL generation mà query-level API không hỗ trợ hoặc cần quan sát mọi statement của Hibernate, inspector vẫn phù hợp hơn.

### 25.3. Không sử dụng tên action động như user input

Marker tốt:

```text
orders-list-by-status-v1
```

Marker rủi ro:

```text
user-{email}-request-{uuid}-token-{...}
```

Marker phải tránh PII, secrets và high-cardinality SQL text.

## 26. Cách gắn một stable comment cho nhóm SQL theo whitelist

Một cách khả thi là chỉ gắn comment cho SQL từ một danh sách SQL shapes chính xác do ứng dụng kiểm soát. Tuy nhiên, so khớp full SQL string có thể giòn.

Một thiết kế trung gian:

```java
public final class WhitelistedSqlCommentInspector
        implements StatementInspector {

    private final Set<String> approvedMarkers;

    public WhitelistedSqlCommentInspector(
            Set<String> approvedMarkers) {

        this.approvedMarkers =
            Set.copyOf(approvedMarkers);
    }

    @Override
    public String inspect(String sql) {
        for (String marker : approvedMarkers) {
            if (sql.contains("/* " + marker + " */")) {
                return "/* observed:" + marker + " */ " + sql;
            }
        }
        return null;
    }
}
```

Đây là ví dụ kỹ thuật dựa trên comments đã được Hibernate render, chỉ dùng khi toàn bộ marker là constants nội bộ được validate trước khi tạo inspector.

### 26.1. Điều gì còn phải kiểm thử?

- `hibernate.use_sql_comments` thực sự bật.
- Query comment xuất hiện đúng dạng mong đợi.
- Không chèn comment trùng khi có nhiều nguồn.
- Dialect chấp nhận prefix comment.
- Parameter positions không thay đổi.
- Hibernate minor upgrade có ảnh hưởng comment formatting không.
- SQL text không chứa marker giống một literal tùy ý từ người dùng.

Đối với bài toán quan sát đơn giản, việc viết lại như vậy có thể không đáng so với logging. Chỉ áp nếu giá trị vận hành rõ ràng.

## 27. Đừng dùng StatementInspector để tạo SQL audit trail

Một số hệ thống muốn “ghi lại mọi SQL thay đổi dữ liệu để audit”. Inspector thiếu thông tin thiết yếu:

- Bound parameter values.
- Actor/resource semantics.
- Số hàng thực sự thay đổi.
- Transaction commit/rollback outcome.
- Database trigger/side-effect.
- External writes không qua Hibernate.

### 27.1. Sự khác nhau giữa SQL trace và audit nghiệp vụ

| SQL trace | Audit nghiệp vụ |
|---|---|
| `UPDATE orders SET status=? WHERE id=?` | “User A approved Order 123” |
| Có thể thiếu parameter values | Có actor, action, resource, time |
| Có thể ghi statement trước execute | Chỉ ghi event theo outcome/transaction policy |
| Chứa thông tin kỹ thuật | Chứa sự kiện domain có ý nghĩa |
| Không tự bảo đảm retention/compliance | Có schema, retention, access control |
| Có thể thiếu external SQL | Được thiết kế bao đúng các business paths |

Nếu cần audit bền vững, dùng outbox/audit entity/database logging phù hợp và áp chính sách bảo vệ dữ liệu riêng.

### 27.2. SQL trace vẫn có giá trị

Không có nghĩa SQL trace vô dụng. Nó rất hữu ích để:

- Điều tra query shape.
- Phát hiện N+1.
- Tìm SQL do mapping sinh.
- Xác minh hint/comment.
- Hỗ trợ DBA xem execution plan.

Chỉ cần gọi đúng tên và không thay audit contract bằng SQL inspection.

## 28. Transaction và thời điểm gọi inspect

Trong Spring:

```java
@Transactional
public void approveInvoice(Long invoiceId) {
    Invoice invoice = em.find(
        Invoice.class,
        invoiceId
    );

    invoice.approve();
}
```

Một SELECT có thể được chuẩn bị trong `find`. UPDATE có thể được chuẩn bị **sau khi method body gần hoàn thành**, tại flush do Hibernate hoặc transaction commit.

Do đó, inspector thường thấy SQL khi Hibernate thực sự chuẩn bị statement, **không nhất thiết ngay lúc setter được gọi**.

### 28.1. Điều này ảnh hưởng logging

Nếu inspector muốn biết “dòng code nào đã tạo UPDATE”, stack trace tại thời điểm prepare có thể trỏ đến flush/transaction infrastructure chứ không trỏ đến `invoice.approve()`.

Dùng tracing ở application service/ORM statistics và hiểu dirty checking pipeline; đừng gắn SQL statement vào một setter dựa trên stack trace đơn giản.

### 28.2. Inspector thấy SQL chưa chắc transaction đã commit

Một UPDATE có thể được chuẩn bị/executed rồi transaction rollback. SQL inspection không chứng minh dữ liệu cuối cùng được ghi bền vững.

### 28.3. Batching làm thay đổi quan sát thời điểm

Với JDBC batching, Hibernate có thể chuẩn bị statement rồi gửi các parameter sets trong batch sau đó. Inspector không phải callback cho từng batch execution.

## 29. Những nguồn SQL đặc biệt

### 29.1. Entity INSERT với IDENTITY

Với `GenerationType.IDENTITY`, Hibernate có thể phải insert sớm để nhận generated key, làm thời điểm inspect/prepare khác entity SEQUENCE được batch ở flush.

### 29.2. Sequence queries

Một số identifier strategies/dialects cần gọi sequence hoặc lấy generated values. Những SQL statements liên quan generator có thể đi qua các đường JDBC/ORM riêng; không suy luận mọi thao tác lấy sequence đều xuất hiện cùng cách như SELECT entity.

### 29.3. Multi-table mutation

Bulk DELETE/UPDATE trên entity inheritance `JOINED` có thể sinh nhiều physical SQL statements. Inspector có thể được gọi cho từng statement được chuẩn bị, không chỉ một lần cho HQL mutation.

### 29.4. Schema generation/DDL

Không mặc định mọi DDL trong Hibernate bootstrap hoặc migration đều đi qua cùng pipeline Session JDBC statement preparation. StatementInspector không phải công cụ kiểm toán toàn bộ schema changes.

## 30. SQL rewrite và parameter placeholders

Một câu SQL:

```sql
update products
set price = ?
where id = ? and version = ?
```

Hibernate bind parameters theo metadata tương ứng:

```text
1: new price
2: product ID
3: expected version
```

Nếu inspector đổi:

```sql
update products
set price = ?
where id = ?
```

thì Hibernate có thể vẫn cố bind tham số thứ ba; driver có thể báo “parameter index out of range”.

Nguy hiểm hơn, nếu chỉ **đổi thứ tự** hai placeholders còn cùng count, binding có thể thành công nhưng gán sai giá trị.

### 30.1. Quy tắc bất biến

Một biến đổi an toàn phải giữ:

- Số lượng placeholders.
- Thứ tự placeholders.
- Vai trò dữ liệu của từng placeholder.
- Projection columns/aliases mà Hibernate kỳ vọng mapping.
- SQL command type.
- Kiểu kết quả/returning semantics.
- Locking/pagination semantics.
- Tất cả tenant/soft-delete/security predicates đã được ORM sinh.

Vì những điều kiện ấy khó kiểm chứng với string rewriting, **hạn chế biến đổi vào comments/hints đã được test** và để query semantics ở tầng cao hơn.

### 30.2. JDBC question mark không phải mọi dấu hỏi đều là bind

Một số SQL dialect/operator có thể sử dụng dấu `?` như cú pháp SQL (ví dụ operator đặc thù). Hibernate/driver xử lý parameter binding theo pipeline riêng. Đếm ký tự `?` trong chuỗi SQL bằng regex không phải cách đáng tin để xác minh bind metadata.

## 31. Bảo mật logging và SQL comments

### 31.1. Không log secrets

Nếu inspector ghi toàn SQL vào log, code khác dùng native SQL với literal secret có thể làm lộ dữ liệu. Cần:

- Tránh đưa secrets vào SQL literals ngay từ đầu.
- Dùng bind parameters.
- Bật log levels theo môi trường.
- Redact và giới hạn access/retention.
- Kiểm tra log forwarding đến SaaS APM.

### 31.2. Không gắn user email/token vào comments

```text
/* user=alice@example.com token=abc... */
```

có thể xuất hiện trong database logs, query statistics, support dumps. Thay bằng marker ổn định không nhạy cảm.

### 31.3. Không thiết kế SQL comment injection

Nếu comment nối từ dữ liệu client:

```java
return "/* " + requestHeader + " */ " + sql;
```

input chứa `*/` có thể kết thúc comment và đưa thêm SQL vào chuỗi. Không dùng dữ liệu không tin cậy trong SQL rewrite. Nếu một marker bắt buộc có dynamic fragment, cần whitelist character set và độ dài rất chặt, nhưng thường nên chuyển nó sang tracing context ngoài SQL.

## 32. Multi-tenant Hibernate và SQL inspection

Trong hệ thống có nhiều tổ chức, inspector có thể được cấu hình một lần ở SessionFactory và nhận SQL từ nhiều tenants.

Không giữ mutable field `currentTenant` trong singleton. Đừng dùng inspector để đoán tenant bằng SQL text.

### 32.1. Quan sát tenant predicate không đủ để chứng minh isolation

Ví dụ inspector thấy:

```sql
select ... from documents where tenant_id = ?
```

Điều đó không chứng minh:

- Parameter bind là tenant đúng.
- Caller đã được xác thực.
- Tenant ID có được authorization.
- L2 cache hit có bypass SQL không.
- Native SQL/bulk DML cũng có predicate.
- Associations và direct `find` đều scoped.

StatementInspector giúp nhìn một phần SQL pipeline, không là một chứng nhận bảo mật.

### 32.2. Không rewrite schema theo tenant bằng replace()

Sai:

```java
return sql.replace("public.", currentTenant + ".");
```

Vì tenant context có thể sai, string có thể xuất hiện ở nhiều nơi, driver/dialect quoting phức tạp, và SQL query plan/cache bị biến đổi tùy request.

Dùng multi-tenant connection provider/schema routing hoặc Hibernate mapping có hỗ trợ thực sự.

### 32.3. Cache hits có thể làm SQL biến mất

Nếu Hibernate trả entity từ L1/L2 mà không chuẩn bị JDBC SELECT, inspector sẽ không thấy query ấy. Vì vậy số lần inspector ghi SQL không bằng số lần application đọc entity hay số lần quyền được kiểm tra.

Authorization cần độc lập với cache hit/miss.

## 33. Dùng StatementInspector để hỗ trợ chẩn đoán N+1

Một màn hình tải 20 đơn:

```java
List<PurchaseOrder> orders = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.customer.id = :customerId
    """, PurchaseOrder.class)
    .setParameter("customerId", id)
    .getResultList();

for (PurchaseOrder o : orders) {
    System.out.println(o.getLines().size());
}
```

Nếu `lines` là lazy to-many collection và chưa cached/batched, Hibernate có thể thực hiện:

```text
1 SELECT orders
20 SELECT order_lines (mỗi order một câu)
---------------------
21 SELECT
```

Inspector có thể ghi nhận các SQL shapes lặp lại và giúp phát hiện tình huống này.

### 33.1. Phương án sửa nằm ở fetch plan, không phải inspector

- DTO projection trực tiếp.
- `JOIN FETCH` phù hợp khi không paginate collection.
- `@BatchSize` hoặc batch fetching.
- EntityGraph.
- Query chọn IDs rồi fetch associations theo một lần/chunks.
- Thiết kế endpoint không đọc collection nếu không cần.

Không dùng inspector để tự thay SELECT thành JOIN FETCH trên SQL string. Hibernate còn cần mapping result-set/entity hydration tương ứng.

### 33.2. Cần phân biệt batch fetching

Nếu Hibernate gộp lazy collection loads bằng `IN (?, ?, ...)`, số SELECT có thể giảm đáng kể. Inspector có thể hỗ trợ quan sát SQL sau khi tuning, nhưng đếm statements không cho biết toàn bộ response time.

## 34. Test rewrite trên đúng database dialect

Nếu inspector thật sự chèn SQL comment/hint, test phải có hai nhóm: **tính đúng dữ liệu** và **tác động của SQL rewrite**.

### 34.1. Test SELECT

- Query trả đúng tập rows.
- Các parameters vẫn bind đúng.
- Pagination/locking vẫn hoạt động.
- Query dùng CTE/subquery có bị rewrite nhầm không.
- SQL query cache/prepared statements có bị tác động không.

### 34.2. Test INSERT/UPDATE/DELETE

- Insert entity thành công.
- Optimistic version update hoạt động.
- DELETE với foreign key/cascade không bị thay semantics.
- Batch insert/update không lỗi.
- Bulk HQL DML không bị matcher áp nhầm hint.

### 34.3. Test SQL đặc biệt

- Quoted identifiers.
- Multi-line SQL.
- SQL đã có comments.
- Query starts with WITH.
- Vendor-specific pagination.
- Lock clauses.
- Generated IDs/sequence calls.
- Native queries.
- Multi-table inheritance mutation.

### 34.4. Test khi nâng cấp Hibernate

SQL alias/naming, AST rendering và dialect behavior có thể đổi qua major/minor versions. Khi inspector phụ thuộc query shape, cần chạy integration tests sau upgrade trước khi deploy.

### 34.5. Test query plan

Một hint đúng cú pháp **không đảm bảo query nhanh hơn**. Kiểm tra `EXPLAIN`/`EXPLAIN ANALYZE` hoặc công cụ tương ứng với dữ liệu đủ đại diện, đo latency, IO, CPU và lock waits. Có feature flag để tắt hint khi thống kê/index thay đổi.

## 35. Kiểm thử cấu hình inspector có thật sự được dùng

Một lỗi cấu hình phổ biến là viết class đúng nhưng Hibernate không nhận instance đó, hoặc service dùng một SessionFactory khác.

Một integration test có thể:

1. Khởi động Spring context thật.
2. Đảm bảo inspector bean được đăng ký vào Hibernate SessionFactory.
3. Thực hiện một query qua repository/EntityManager.
4. Xác nhận inspector quan sát SQL.
5. Kiểm tra không ghi SQL sau khi tắt cấu hình/test profile.

### 35.1. Không kiểm tra bằng việc gọi inspect() trực tiếp rồi kết luận integration đúng

`inspector.inspect("select 1")` chỉ là unit test của method Java. Nó không chứng minh SessionFactory đã cấu hình inspector hay Hibernate thực sự dùng nó.

Cần test qua đường JPA/Hibernate thật để xác nhận integration.

### 35.2. Multiple EntityManagerFactory

Ứng dụng có nhiều datasources/JPA persistence units có thể tạo nhiều EntityManagerFactories. Đăng ký inspector cho factory A không có nghĩa query qua factory B cũng đi qua nó.

Hãy xác định factory nào chịu trách nhiệm và gắn configuration tương ứng.

## 36. Ví dụ ứng dụng hoàn chỉnh: quan sát SQL bằng Spring bean

Một implementation đọc-only, không can thiệp SQL, phù hợp làm nền cho observability:

```java
package com.example.persistence;

import org.hibernate.resource.jdbc.spi.StatementInspector;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class ProductionSafeInspector
        implements StatementInspector {

    private static final Logger LOG =
        LoggerFactory.getLogger(ProductionSafeInspector.class);

    @Override
    public String inspect(String sql) {
        // Không ghi nội dung SQL mặc định vào production log.
        if (LOG.isTraceEnabled()) {
            LOG.trace(
                "Hibernate is preparing SQL (length={})",
                sql.length()
            );
        }

        return null;
    }
}
```

Spring registration:

```java
@Configuration
public class PersistenceDiagnosticsConfig {

    @Bean
    public StatementInspector statementInspector() {
        return new ProductionSafeInspector();
    }

    @Bean
    public HibernatePropertiesCustomizer sqlInspectorCustomizer(
            StatementInspector inspector) {
        return props -> props.put(
            "hibernate.session_factory.statement_inspector",
            inspector
        );
    }
}
```

Đây là ví dụ ứng dụng dùng Spring Boot/JPA integration hỗ trợ `HibernatePropertiesCustomizer`. Nếu dùng Spring Framework thuần hoặc Hibernate bootstrap không qua Boot, đăng ký vào bootstrap tương ứng.

### 36.1. Lợi ích

- Inspector được DI quản lý.
- Chỉ phát log metadata khi TRACE bật.
- Không lộ raw SQL/parameters mặc định.
- Không thay SQL.
- Không phụ thuộc request-level mutable state.
- Có thể mở rộng thêm metrics đã được thiết kế/giới hạn.

### 36.2. Giới hạn

- Không cung cấp duration hay affected rows.
- Không xác minh transaction commit.
- Không đo JDBC execution count tuyệt đối.
- Không thay bảo mật tenant/ACL.
- Không thay database slow-query logs.

Hãy mô tả nó như một thành phần quan sát SQL preparation, không phải một APM hoàn chỉnh.

## 37. Kiểm thử inspector thu thập SQL theo một Session

Một kịch bản test với native Hibernate Session:

```java
CapturingStatementInspector inspector =
    new CapturingStatementInspector();

try (Session session = sessionFactory.withOptions()
        .statementInspector(inspector)
        .openSession()) {

    Transaction tx = session.beginTransaction();

    session.createQuery("""
        select c
        from Customer c
        where c.active = true
        """, Customer.class)
        .getResultList();

    tx.commit();
}

List<String> captured = inspector.snapshot();
```

### 37.1. Vì sao per-Session capture phù hợp test?

- Không trộn SQL của sessions khác trong SessionFactory chung.
- Không cần giữ toàn bộ SQL production.
- Có thể gắn inspector vào đúng unit under test.
- Dễ đóng session ngay sau test.

### 37.2. Khi test trong Spring

Không tự tạo Session riêng nếu service under test đang dùng Spring-managed EntityManager khác. Cần bảo đảm inspector được đăng ký vào factory/context thực sự sử dụng trong test; có thể cấu hình test-specific bean hoặc transaction-scoped instrumentation tương ứng.

## 38. Khi nào nên dùng giải pháp khác?

### 38.1. Muốn xem tất cả câu SQL + bind values

Dùng Hibernate SQL/bind logging hoặc JDBC proxy có redaction phù hợp. StatementInspector không nhận bind values.

### 38.2. Muốn đo thời gian truy vấn

Dùng JDBC instrumentation, Micrometer, OpenTelemetry/APM, Hibernate statistics hoặc database metrics. Inspector xảy ra trước execution nên không có duration.

### 38.3. Muốn đổi query để tránh N+1

Dùng fetch plan, DTO query, batch fetching/EntityGraph. Không rewrite SQL SELECT tại inspector.

### 38.4. Muốn kiểm soát tenant/authorization

Dùng multi-tenancy, scoped repository, policy service, database RLS/constraints. Inspector không thay thế security enforcement.

### 38.5. Muốn ghi audit nghiệp vụ

Dùng domain/app service, entity listeners khi phù hợp, transactional outbox hoặc DB audit trail. Inspector không biết commit.

### 38.6. Muốn áp hint ở một query

Ưu tiên Hibernate query/dialect API nếu có, hoặc inspector có whitelist/marker và integration tests nếu thực sự cần.

### 38.7. Muốn sửa tên bảng/schema động

Dùng mapping, naming strategy, multi-tenancy connection provider hoặc schema routing đúng, không dùng `String.replace` trên SQL đã sinh.

## 39. Những lỗi phổ biến

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Hiểu inspect là sau execute | Đo sai latency/row count | Dùng JDBC/APM/DB instrumentation |
| Trả null để “hủy SQL” | Hibernate vẫn chạy SQL gốc | Trả null nghĩa là không sửa |
| Thay số `?` placeholders | Bind parameter lỗi hoặc sai dữ liệu | Không đổi JDBC parameter layout |
| Nối raw user input vào SQL comment | Injection/log leak | Chỉ dùng marker ổn định, whitelist |
| Gắn request ID vào mọi SQL | High-cardinality plan/log keys | Dùng tracing/MDC ngoài SQL |
| Ghi toàn bộ raw SQL production | PII/secrets, log overhead | Logging có kiểm soát/redaction |
| Giữ mutable currentUser trong singleton | Race/cross-request leak | Immutable config hoặc context scoping |
| Gọi repository trong inspect | Re-entrant queries, recursion, N+1 | Inspector nhẹ, không gọi DB |
| Đếm inspect = rows updated | Sai metrics | Phân biệt prepare và execute |
| Regex SELECT giả định luôn bắt đầu `select` | Bỏ sót CTE/comments | Cân nhắc parser/marker hoặc không rewrite |
| Thay tên bảng/schema bằng replace | SQL sai/tenant leak | Dùng proper mapping/multi-tenancy |
| Dùng inspector làm ACL/tenant firewall | Bypass bởi cache/SQL khác | Security tại app+DB boundary |
| Nghĩ SQL comment là domain audit | Không biết actor/commit | Transactional audit/outbox |
| Dùng exact SQL test cho mọi version | Test giòn vì alias/dialect thay đổi | Assert mục tiêu quan trọng, test theo version |
| Cấu hình inspector class nhưng không có no-arg constructor | Bootstrap có thể lỗi | Dùng instance injection/cấu hình đúng |
| Đăng ký vào sai EntityManagerFactory | Không thấy SQL muốn quan sát | Xác nhận factory thực tế |
| Thu thập SQL vào ArrayList toàn cục | Race + memory leak | Bounded/thread-safe capture cho test |
| Dùng `show_sql` và custom inspector logging trùng | Log noise/overhead | Chọn một chiến lược rõ |
| Chèn hint theo tên bảng substring | Áp nhầm query khác | Target marker/SQL shape được kiểm chứng |
| Tin hint chắc chắn cải thiện performance | Query plan regression | Đo EXPLAIN và triển khai feature flag |
| Quên SQL do JdbcTemplate không qua inspector | Thiếu observability | DataSource-level instrumentation |
| Đọc SQL nhưng không biết bind values | Chẩn đoán sai | Dùng binder logs có bảo vệ dữ liệu |

## 40. Bài tập 1: dự đoán return null

```java
@Override
public String inspect(String sql) {
    if (sql.startsWith("select")) {
        return null;
    }
    return null;
}
```

**Câu hỏi:** Có SQL nào bị chặn không?

**Đáp án:** Không. `null` yêu cầu Hibernate giữ SQL gốc. Nếu muốn chặn query vì policy, không dùng StatementInspector làm security barrier; xử lý ở query/application/DB boundary phù hợp.

## 41. Bài tập 2: bind parameter

Inspector nhận:

```sql
select * from customers
where organization_id = ?
  and email = ?
```

**Câu hỏi:** Có thể lấy email thật từ chuỗi SQL đó không?

**Đáp án:** Không. SQL string chỉ chứa placeholders. Hibernate bind parameter values qua cơ chế JDBC khác. Nếu cần quan sát binds, dùng logging/instrumentation phù hợp và bảo vệ PII.

## 42. Bài tập 3: nhận diện query theo table name

Inspector:

```java
if (sql.contains("orders")) {
    return "/* orders */ " + sql;
}
```

**Câu hỏi:** Vì sao không đủ đáng tin?

**Đáp án:** Chuỗi có thể xuất hiện trong alias, subquery, comment, literal hoặc tên bảng khác. SQL formatting và dialect thay đổi. Nên dùng marker nội bộ, query-level comment hoặc một cơ chế nhận diện SQL shape đã kiểm chứng, không suy luận root query qua substring.

## 43. Bài tập 4: singleton thread safety

Inspector có:

```java
private String currentTenant;

public void setTenant(String value) {
    this.currentTenant = value;
}
```

Các requests A/B cập nhật field rồi chạy query.

**Câu hỏi:** Nguy cơ nào?

**Đáp án:** Field mutable trong singleton có thể bị race giữa threads; inspector của A có thể đọc tenant B, gây log leak hoặc SQL rewrite sai tenant. Không dùng inspector singleton để giữ mutable request state.

## 44. Bài tập 5: optimizer hint

Ứng dụng muốn chèn một hint Oracle cho query tìm orders theo customer.

**Bài làm:** Trình bày kế hoạch an toàn:

1. Xác định đúng query operation.
2. Gắn marker ổn định hoặc dùng API hỗ trợ hint.
3. Xác minh dialect Oracle thực tế và SQL syntax.
4. Không thay parameters/projection.
5. Test kết quả bằng integration test.
6. Dùng EXPLAIN/plan stats xác nhận lợi ích.
7. Có feature flag rollback khi query chậm hơn.

**Kết luận:** Một hint được DB chấp nhận chưa chứng minh hint tối ưu.

## 45. Bài tập 6: audit và rollback

Inspector ghi “Order updated” khi thấy:

```sql
update orders set status=? where id=?
```

Sau đó DB transaction rollback.

**Câu hỏi:** Audit “Order updated” có đúng không?

**Đáp án:** Không nhất thiết. Inspector thấy câu SQL chuẩn bị, không biết execute/commit. Nếu audit yêu cầu only committed operations, dùng audit table/outbox trong cùng transaction hoặc cơ chế bảo đảm phù hợp.

## 46. Bài tập 7: đo N+1

Test query tải 10 Orders và sau đó truy cập lazy `lines` của từng order.

**Câu hỏi:** Inspector có thể chứng minh gì?

**Đáp án:** Nó có thể giúp quan sát SQL shapes/number of preparations để nhận ra nhiều SELECT lặp, nhưng không tự có per-row execute metrics. Sửa N+1 qua fetch plan, batching hoặc DTO projection rồi kiểm thử lại.

## 47. Checklist trước khi đưa StatementInspector vào production

1. **Mục đích:** chỉ quan sát hay cần rewrite SQL?
2. **Tầng hook:** vấn đề thực sự nằm ở SQL string trước JDBC preparation?
3. **API:** dùng `org.hibernate.resource.jdbc.spi.StatementInspector` đúng major version?
4. **Registration:** đã xác nhận SessionFactory đang dùng đúng inspector?
5. **Phạm vi:** inspector singleton toàn SessionFactory hay per-Session?
6. **Thread safety:** không có mutable request state dùng chung?
7. **Performance:** logic nhỏ, không DB calls/network/I/O blocking?
8. **Logging:** có thể rò SQL literals, tenant names, secrets/PII không?
9. **Parameters:** có giữ đúng placeholders và binder metadata?
10. **SQL semantics:** có đổi command/projection/WHERE/locks/pagination không?
11. **Dialect:** comment/hint có hợp lệ trên DB mục tiêu?
12. **Targeting:** rewrite chỉ áp cho SQL shape/operation đã cho phép?
13. **SQL text cardinality:** có tạo comment động làm cache/plan/log noise?
14. **Cache:** có ảnh hưởng statement cache, query plan, metrics grouping?
15. **Transactions:** không dùng inspect như chứng cứ commit/audit?
16. **Tenancy:** không dùng rewrite để bổ sung tenant predicate bảo mật?
17. **Authorization:** cache hits không được bypass security policy?
18. **Instrumentation:** muốn duration/row count thì dùng JDBC/APM thay thế?
19. **Tests:** đã test SQL SELECT/INSERT/UPDATE/DELETE, bulk, lazy, native?
20. **Versions:** đã test sau Hibernate/Spring/dialect upgrades?
21. **Operations:** có flag để tắt inspector rewrite nếu gặp regression?
22. **Monitoring:** đã có cách quan sát lỗi bootstrap, statement preparation, DB timeouts?
23. **Multiple factories:** cấu hình đã áp đúng persistence unit?
24. **Data retention:** log/metrics/captured SQL có thời hạn và phân quyền?
25. **Fallback:** khi không nhận diện được SQL target, có trả null để giữ nguyên thay vì rewrite bừa?

## 48. Ghi nhớ

- **`StatementInspector`** là hook Hibernate cho SQL string **trước khi JDBC statement được chuẩn bị**.
- Hợp đồng chính: `String inspect(String sql)`; **trả `null` để giữ SQL gốc**, trả String để thay thế SQL.
- Inspector thấy **SQL text**, không tự nhận giá trị binds, HQL AST, entity events, rows affected, duration hay commit status.
- Nó phù hợp **quan sát SQL, tagging bằng comment ổn định hoặc hint đã kiểm chứng**, không phải nơi viết nghiệp vụ hoặc bảo mật.
- Có thể đăng ký ở **SessionFactory** bằng `hibernate.session_factory.statement_inspector`, qua Spring Boot `HibernatePropertiesCustomizer` hoặc **per-Session** với native Hibernate APIs tương ứng.
- Inspector dùng chung phải **thread-safe**; tránh mutable actor/tenant/request state trong singleton.
- **Không gọi repository/EntityManager trong inspect** vì nguy cơ reentrancy, deadlock và performance.
- Không biến `?` thành literals hoặc thay thứ tự placeholders; Hibernate đã quản lý parameter binding riêng.
- Không dùng SQL regex để thêm tenant WHERE, thay bảng/schema, sửa authorization hay xóa dữ liệu theo policy.
- Một SQL **được inspect không đồng nghĩa đã execute hoặc commit**; audit và transaction semantics cần cơ chế khác.
- SQL comments động theo request có thể gây high-cardinality SQL text và làm giảm hiệu quả các cache/monitoring systems.
- Khi chỉ muốn xem SQL, **SQL logging và bind logging** thường đủ; khi muốn đo execution duration/row count dùng JDBC instrumentation/APM/DB metrics.
- Dùng inspector để phát hiện patterns như N+1 nhưng sửa chúng tại **fetch plan/query design**.
- Rewriting có chủ đích phải được **integration-test trên đúng Hibernate/dialect/database**, giữ semantics và có đường rollback.
- Một extension càng gần JDBC càng cần giới hạn trách nhiệm; **quan sát chính xác, chỉnh sửa tối thiểu** thường là nguyên tắc tốt nhất.

**Kết luận:** `StatementInspector` là công cụ mở rộng hữu ích khi cần nhìn hoặc điều chỉnh **chuỗi SQL cuối đường Hibernate generation, trước JDBC preparation**. Sử dụng tốt nhất là giữ inspector đơn giản, ít side effect, thread-safe, không làm thay đổi binding/query semantics và chỉ rewrite trong một phạm vi đã kiểm chứng. Với những yêu cầu như phân quyền, multi-tenancy, audit, query performance hay transaction outcome, inspector có thể hỗ trợ quan sát nhưng không thay thế kiến trúc tương ứng ở tầng application, ORM, JDBC hoặc database.
