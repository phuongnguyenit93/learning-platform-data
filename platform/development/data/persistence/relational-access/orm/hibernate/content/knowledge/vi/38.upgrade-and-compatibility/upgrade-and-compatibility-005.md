# Đọc thay đổi về truy vấn, hệ kiểu và cách sinh SQL trước khi nâng cấp

Nâng cấp Hibernate không chỉ là đổi dependency rồi chạy lại ứng dụng. Một thay đổi trong HQL parser, semantic query model, hệ kiểu Java/JDBC hoặc SQL generation có thể khiến query cũ không còn được chấp nhận, trả về kiểu dữ liệu khác, sinh JOIN khác hoặc thực thi với query plan khác. Source code có thể gần như giữ nguyên nhưng behavior trong production đã đổi.

Ví dụ, một query báo cáo lâu năm dựa vào implicit type conversion của Hibernate cũ. Sau nâng cấp, Hibernate kiểm tra kiểu biểu thức chặt hơn và từ chối phép so sánh không tương thích. Một native query vẫn chạy nhưng enum được bind với JDBC type khác. Một query fetch collection cùng pagination vẫn trả kết quả nhưng đọc nhiều rows hơn và chậm đáng kể.

Trước khi nâng cấp, cần đọc migration guide/release notes theo đúng phiên bản đích, rồi kiểm chứng ba lớp:

1. **Query language và semantics:** HQL/JPQL/Criteria có được parse, type-check và diễn giải đúng không?
2. **Type system và parameter/result mapping:** Java types, Hibernate types và JDBC types có còn tương thích với mapping, functions và driver không?
3. **SQL generation:** SQL mới có đúng với database, schema, indexes, constraints, locking và performance expectations không?

Bài học thuộc chương **Nâng cấp và tương thích** của module *Data Persistence Relational Access ORM Hibernate*. Các ví dụ tập trung vào chuyển Hibernate ORM 5.x lên 6.x vì đây là bước chuyển lớn, nhưng quy trình đọc thay đổi áp dụng cho mọi lần nâng cấp. Chi tiết API phải được đối chiếu với minor version thực tế; không suy rộng ghi chú của 6.0 cho mọi bản 6.x hoặc các phiên bản sau.

## 1. Vì sao phải đọc thay đổi trước khi đổi dependency?

Một truy vấn đi qua nhiều lớp:

~~~mermaid
flowchart TD
    A["Application query code"] --> B["HQL / JPQL / Criteria parser"]
    B --> C["Semantic query model and type checking"]
    C --> D["SQL AST and SQL generation"]
    D --> E["Dialect and JDBC type mapping"]
    E --> F["Database execution"]
    F --> G["Result extraction and Java values"]
~~~

Một query thành công cần tương thích với cả pipeline. Dấu hiệu lỗi theo từng lớp:

| Lớp | Dấu hiệu sau nâng cấp | Ví dụ rủi ro |
| --- | --- | --- |
| Query grammar | Parse error | Cú pháp extension cũ không còn được chấp nhận |
| Semantic/type checking | Query validation error | Hai expressions không tương thích kiểu |
| Result typing | Cast/DTO construction error | Result type khác kỳ vọng |
| Parameter binding | JDBC binding error hoặc kết quả sai | Enum, UUID, temporal, null parameter |
| SQL generation | SQL syntax/column error | Dialect hoặc identifier quoting đổi |
| Query plan | Chạy chậm dù kết quả đúng | Join, cast hoặc parameter type ảnh hưởng index |
| Result extraction | Sai precision/temporal value | JDBC type và Java mapping khác |

Một bản nâng cấp có thể làm query cũ fail sớm hơn. Điều đó đôi khi là tốt vì query trước đó vốn mơ hồ hoặc dựa vào conversion không portable. Cần nhận diện trước để sửa có chủ đích.

### 1.1. Đừng chỉ đọc danh sách API bị xóa

Behavior change có thể nằm ở:

- HQL parser và grammar.
- Type inference và semantic validation.
- Implicit joins và path navigation.
- Function registration/return types.
- Parameter type inference.
- Java-to-JDBC type mapping.
- Dialect defaults và SQL rendering.
- Multi-table UPDATE/DELETE strategy.
- Fetching, pagination và query cache behavior.
- SQL logging và diagnostics.

Đọc release notes để tìm behavior changes, không chỉ compile errors.

## 2. Đọc tài liệu nâng cấp theo đúng phiên bản

Trước khi sửa code, ghi lại chính xác stack:

~~~text
Hibernate hiện tại: 5.x.y.Final
Hibernate mục tiêu: 6.x.y.Final
Jakarta Persistence API: phiên bản target hỗ trợ
Database: DBMS và major version
JDBC driver: artifact và version
JDK: compile/runtime version
Framework: Spring Boot/Spring Framework version
~~~

Không lấy ví dụ từ một minor release rồi giả định mọi version đều có cùng behavior.

### 2.1. Thứ tự tài liệu nên đọc

1. Migration guide từ major version hiện tại đến major version đích.
2. Release notes của từng minor version có liên quan.
3. User Guide của đúng target version, đặc biệt Query Language, Basic Types, Custom Types, Dialects và fetching.
4. Jakarta Persistence specification mà target implement.
5. Javadocs của API đang dùng và API thay thế.
6. Release notes của Spring Boot/framework BOM, JDBC driver và DBMS.
7. Issue/release note cụ thể nếu ứng dụng dùng extension hoặc API nội bộ.

### 2.2. Lập inventory truy vấn

Tập hợp query từ:

- HQL/JPQL trong repositories và services.
- Criteria API và Specifications.
- Named queries trên entities/XML.
- Native SQL và stored procedure calls.
- Dynamic query builders.
- Report/analytics queries.
- Bulk UPDATE/DELETE.
- Query do framework hoặc third-party library tạo.
- Custom functions, custom types và custom Dialect.
- Queries chỉ chạy trong scheduled jobs hoặc production features.

Với mỗi query, lưu source, mục đích, expected result type, DBMS, tần suất, kích thước dữ liệu và mức độ quan trọng.

### 2.3. Ưu tiên vùng rủi ro

| Mức ưu tiên | Query shape | Vì sao cần chú ý |
| --- | --- | --- |
| Cao | Native SQL, stored procedures, custom Dialect | Phụ thuộc DBMS và JDBC mapping |
| Cao | HQL có implicit joins, functions, subqueries phức tạp | Parser/type inference/SQL AST có thể đổi |
| Cao | Bulk mutation và versioned entities | Mutation strategy và lifecycle khác |
| Cao | Fetch joins + pagination | Có thể tạo nhiều rows hoặc pagination behavior khác |
| Cao | Enum, UUID, JSON, custom UserType | Java/JDBC type mapping |
| Trung bình | DTO constructor projections | Constructor/type compatibility |
| Trung bình | Aggregates, CASE, COALESCE | Return type inference |
| Trung bình | Named/positional parameters | Type inference và binding |
| Trung bình | Simple entity lookup | Ít query-language complexity hơn |

Mức thấp hơn không có nghĩa bỏ qua; nó giúp sắp xếp thứ tự review.

## 3. HQL và semantic query model

HQL là query language của Hibernate, gần JPQL nhưng có extensions riêng. Qua Hibernate 6, query engine được tổ chức lại đáng kể: query được parse và xây semantic representation trước khi chuyển thành SQL AST và SQL theo Dialect.

Vì vậy một query từng được chấp nhận nhờ cách diễn giải linh hoạt có thể bị kiểm tra chặt hơn.

### 3.1. Cú pháp hợp lệ chưa chắc semantics hợp lệ

~~~java
List<Order> rows = session.createQuery(
        "from Order o where o.totalAmount = :value",
        Order.class
    )
    .setParameter("value", value)
    .getResultList();
~~~

Nếu totalAmount là BigDecimal, bind BigDecimal phù hợp. Đừng truyền String rồi dựa vào implicit conversion của database hoặc Hibernate cũ.

Query có thể parse nhưng fail ở semantic validation do:

- So sánh expressions không tương thích.
- Function không được đăng ký hoặc return type không phù hợp.
- Path không tồn tại hoặc không hợp lệ.
- Constructor projection không khớp argument types.
- Kết hợp enum, numeric, temporal hoặc entity expressions không rõ semantics.

### 3.2. Path navigation và implicit joins

~~~java
select o
from PurchaseOrder o
where o.customer.address.city = :city
~~~

Path navigation qua associations có thể làm Hibernate sinh implicit joins. Sau nâng cấp, SQL aliases, join order/type hoặc cách query được tối ưu có thể khác dù HQL giữ nguyên.

Khi giúp làm rõ semantics, viết JOIN tường minh:

~~~java
select o
from PurchaseOrder o
join o.customer c
join c.address a
where a.city = :city
~~~

Không thêm JOIN chỉ để ép SQL giống hệt bản cũ; mục tiêu là đúng semantics và plan phù hợp.

### 3.3. Optional associations

Nếu association là optional, path navigation có thể làm thay đổi tập root rows tùy expression/join semantics. Xác định có cần giữ root entity khi association null không. Nếu cần, viết LEFT JOIN và đặt predicate đúng vị trí:

~~~java
select o
from PurchaseOrder o
left join o.customer c
where c is null or c.status = :status
~~~

Test cả trường hợp association không tồn tại; đừng chỉ dùng fixtures luôn có đầy đủ related rows.

### 3.4. JPQL compliance và Hibernate extensions

HQL có nhiều khả năng vượt JPQL. Nếu ứng dụng bật JPQL compliance hoặc dùng extensions Hibernate, kiểm tra target behavior theo cấu hình thật.

CTE, window functions, derived roots, lateral joins hoặc cú pháp function đặc thù phụ thuộc version và Dialect. Không dùng tài liệu mới nhất để suy ra một version cũ đã hỗ trợ cùng cú pháp.

## 4. Kiểm tra kiểu kết quả truy vấn

Result type là hợp đồng giữa query, Java code và API trả về. Query có thể chạy nhưng trả kiểu khác, gây cast, DTO construction hoặc serialization error.

### 4.1. Single selection và typed query

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
        "select o from PurchaseOrder o",
        PurchaseOrder.class
    )
    .getResultList();
~~~

Scalar selection:

~~~java
List<BigDecimal> totals = entityManager.createQuery(
        "select o.totalAmount from PurchaseOrder o",
        BigDecimal.class
    )
    .getResultList();
~~~

Khai báo result class phù hợp giúp compiler/provider kiểm tra rõ hơn. Tránh khai báo kiểu quá rộng rồi cast ở nhiều nơi.

### 4.2. Multiple selections

Khi query chọn nhiều expressions, định nghĩa result shape rõ:

~~~java
List<Object[]> rows = entityManager.createQuery(
        "select o.id, o.status from PurchaseOrder o",
        Object[].class
    )
    .getResultList();
~~~

Hoặc dùng DTO constructor expression:

~~~java
public record OrderSummary(
        Long id,
        OrderStatus status,
        BigDecimal totalAmount
) {}
~~~

~~~java
List<OrderSummary> summaries = entityManager.createQuery(
        """
        select new com.example.reporting.OrderSummary(
            o.id, o.status, o.totalAmount
        )
        from PurchaseOrder o
        """,
        OrderSummary.class
    )
    .getResultList();
~~~

Constructor cần đúng thứ tự và kiểu tham số tương thích. Kiểm tra wrapper/primitive, numeric widening, enum và nullability.

### 4.3. Tuple projection

Nếu muốn truy cập theo alias thay vì index:

~~~java
List<Tuple> rows = entityManager.createQuery(
        """
        select o.id as orderId,
               o.status as orderStatus
        from PurchaseOrder o
        """,
        Tuple.class
    )
    .getResultList();

for (Tuple row : rows) {
    Long id = row.get("orderId", Long.class);
    OrderStatus status =
            row.get("orderStatus", OrderStatus.class);
}
~~~

Alias là một phần của result contract. Test alias nếu code đọc theo tên.

### 4.4. Aggregate return types

Aggregate có quy tắc kiểu riêng. COUNT thường trả Long; SUM phụ thuộc kiểu numeric expression theo query-language rules. Không mặc định kết quả luôn có kiểu của field đầu vào.

~~~java
Long count = entityManager.createQuery(
        "select count(o) from PurchaseOrder o",
        Long.class
    )
    .getSingleResult();
~~~

~~~java
BigDecimal total = entityManager.createQuery(
        "select sum(o.totalAmount) from PurchaseOrder o",
        BigDecimal.class
    )
    .getSingleResult();
~~~

Kiểm tra empty results: SUM/AVG có thể trả NULL trong khi COUNT trả 0. DTO và primitive mapping phải xử lý đúng.

### 4.5. CASE, COALESCE và NULL

~~~java
select coalesce(o.discountAmount, 0)
from PurchaseOrder o
~~~

Literal số nguyên có kiểu riêng. Nếu expression kết hợp BigDecimal, integer, long hoặc function DB-specific, type inference cần được kiểm tra. Dùng literal/parameter đúng kiểu domain khi cần.

Không chuyển NULL thành zero nếu nghiệp vụ phân biệt “không có dữ liệu” với “giá trị bằng 0”.

## 5. Parameter binding và type inference

Parameters là nơi Hibernate type system gặp JDBC binding.

### 5.1. Named parameters

~~~java
List<PurchaseOrder> orders = entityManager.createQuery(
        """
        select o from PurchaseOrder o
        where o.createdAt >= :from
          and o.createdAt < :to
        """,
        PurchaseOrder.class
    )
    .setParameter("from", fromInstant)
    .setParameter("to", toInstant)
    .getResultList();
~~~

Parameter Java type phải phù hợp với mapped attribute. Với temporal values, xác định rõ Instant, LocalDate, LocalDateTime, timezone semantics và database column type.

### 5.2. Null parameter có thể mơ hồ

~~~java
query.setParameter("status", null);
~~~

Null không mang runtime Java type rõ ràng. Provider có thể suy ra kiểu từ query expression; trong native SQL hoặc query phức tạp, việc suy luận có thể không đủ thông tin.

Nếu query cần null parameter, khai báo type qua API phù hợp với Hibernate/JPA version hoặc viết predicate rõ:

~~~java
where (:status is null or o.status = :status)
~~~

Cách này vẫn cần kiểm tra type inference và query plan; không áp dụng máy móc nếu DB planner không tối ưu tốt.

### 5.3. Positional parameters

JPQL dùng ordinal parameters dạng `?1`, `?2` theo specification. Native SQL và các API Hibernate có quy tắc binding riêng tùy loại query/API. Không thay thế hàng loạt dấu hỏi bằng ordinal syntax mà không xác định query là JPQL, HQL hay native SQL.

Named parameters thường dễ review và ít nhầm thứ tự hơn trong query dài.

### 5.4. Enum parameters

~~~java
@Enumerated(EnumType.STRING)
private OrderStatus status;
~~~

Bind enum Java value:

~~~java
query.setParameter("status", OrderStatus.PAID);
~~~

Không bind String rồi dựa vào DB cast nếu expression được định nghĩa là enum. Đổi STRING sang ORDINAL là thay đổi schema/data contract, không phải một tối ưu query đơn giản.

## 6. Function registry và return type

HQL có thể gọi database functions và functions do Hibernate đăng ký. Một function cần xác định:

- Tên và cú pháp.
- Số lượng/kiểu arguments.
- Return type.
- SQL rendering theo Dialect.
- Null semantics nếu ảnh hưởng expression.

Ví dụ:

~~~java
select lower(c.email)
from Customer c
where lower(c.email) = :email
~~~

Nếu ứng dụng có custom function, kiểm tra API đăng ký trong phiên bản đích. Extension APIs của function registry thay đổi qua major releases; không mang code custom cũ sang mà không đọc migration guide.

### 6.1. Kiểm tra return type

Function trả string, numeric, boolean hay temporal? Nếu Hibernate không biết return type, query composition hoặc DTO projection có thể lỗi semantic/JDBC extraction.

Với custom functions, khai báo return type rõ theo API target và integration-test trên từng Dialect.

### 6.2. Function portability

Một function cùng tên ở hai DBMS không đảm bảo semantics giống nhau. Collation, timezone, string length, rounding và NULL behavior có thể khác. Ứng dụng hỗ trợ nhiều DBMS cần test từng Dialect hoặc cung cấp implementation riêng.

## 7. Hệ kiểu Hibernate: Java type, Hibernate type và JDBC type

Một giá trị đi qua nhiều lớp:

~~~mermaid
flowchart LR
    A["Java attribute type"] --> B["Hibernate Java/type mapping"]
    B --> C["JDBC type and binder/extractor"]
    C --> D["Database column type"]
    D --> E["JDBC result extraction"]
    E --> F["Java value"]
~~~

Không coi Java type và database column type là một khái niệm.

Ví dụ UUID trong Java có thể lưu dạng native UUID, binary hoặc character tùy DBMS/configuration. Boolean có thể map thành BOOLEAN, BIT, numeric hoặc representation khác. Instant và LocalDateTime có timezone semantics khác nhau. Một thay đổi trong Hibernate type system hoặc Dialect có thể làm SQL bind/extract khác.

### 7.1. JavaType và JdbcType

Hibernate 6 tổ chức type system thành các phần có trách nhiệm rõ hơn, bao gồm Java-side representation và JDBC-side SQL type/binding. Khi nâng custom type code, đọc migration guide về:

- BasicType và type registries.
- JavaType descriptors.
- JdbcType descriptors.
- Value binders/extractors.
- Mutability plans.
- Type contributors.
- UserType API.
- SQL type codes và Dialect support.

Không chỉ sửa imports để code compile. Phải xác minh dữ liệu bind/extract đúng với schema và driver.

### 7.2. Custom UserType

Nếu ứng dụng có custom UserType hoặc type contributor, kiểm tra API signatures và semantics ở target version. Type APIs cũ có thể đã được thay đổi hoặc tách trách nhiệm. Custom type compile được nhưng binder/extractor sai vẫn có thể lưu dữ liệu sai.

Test custom types với:
- Persist rồi load lại.
- Query parameter binding.
- Criteria predicates.
- Null values.
- Dirty checking/mutability.
- Cache serialization nếu bật.
- Schema type thực tế.
- Round-trip qua JDBC driver production.

### 7.3. @JdbcTypeCode và @JavaType

Hibernate cung cấp mapping APIs/annotations để chỉ định JDBC/Java type trong trường hợp cần thiết. Trước khi dùng, kiểm tra API của phiên bản đích và xem mapping mặc định đã đáp ứng chưa.

Không thêm type override chỉ để query compile nếu chưa hiểu cột database và dữ liệu hiện có.

## 8. Những kiểu dữ liệu cần kiểm tra đặc biệt

### 8.1. UUID

Xác định UUID được lưu native, binary hay text. Kiểm tra DDL, JDBC binding type, native query parameter type, index/equality comparisons, migration/backfill và interoperability với các ứng dụng khác.

Không đổi UUID storage representation trong cùng lần nâng ORM mà thiếu migration/data compatibility plan.

### 8.2. Enum

Với EnumType.STRING, column thường chứa tên enum; với ORDINAL, column chứa số thứ tự. Nếu thứ tự enum thay đổi, dữ liệu ordinal cũ có thể được diễn giải thành giá trị khác. Test query parameters và schema values, không chỉ test Java serialization.

### 8.3. BigDecimal và numeric precision

Kiểm tra precision/scale trong DDL, JDBC extraction, aggregate result types và rounding. Đừng chỉ dùng double trong test monetary values.

### 8.4. Temporal values

Phân biệt LocalDate, LocalDateTime, Instant và OffsetDateTime. Kiểm tra timezone JVM, JDBC driver, database session và column type. Query range có thể đổi kết quả nếu conversion timezone hoặc precision khác.

### 8.5. JSON, arrays và vendor-specific types

JSON/JSONB, arrays, spatial types và custom DB types phụ thuộc Dialect/driver. Kiểm tra DDL, binding, extraction, query operators và index usage. Đừng giả định HQL function/Criteria expression portable.

## 9. SQL generation và Dialect

Hibernate chuyển query semantics thành SQL phù hợp với Dialect, mapping, table/column metadata và database capabilities. SQL có thể đổi ở:

- Alias và alias numbering.
- Join order/type.
- Subquery rendering.
- Parameter marker positions.
- Identifier quoting.
- Pagination syntax.
- Lock clauses.
- Casts và JDBC types.
- Sequence/identity retrieval.
- Multi-table UPDATE/DELETE strategy.
- CTE/temp-table usage.
- Function rendering.

### 9.1. Đừng snapshot toàn bộ SQL làm contract

SQL generated có thể thay alias, whitespace hoặc thứ tự biểu thức mà không đổi semantics. Test chỉ so sánh nguyên văn SQL có thể fail vô ích sau upgrade.

Thay vào đó, test:
- Kết quả và kiểu dữ liệu.
- Rows bị đọc/ghi.
- Tenant/security predicates.
- Số statements/round trips nếu có yêu cầu.
- Locking semantics.
- Execution plan/performance.
- Schema compatibility.

Snapshot SQL hữu ích cho query quan trọng nhưng cần tách phần không ổn định như aliases và formatting.

### 9.2. Custom Dialect

Nếu dự án subclass Dialect hoặc override SQL rendering, đây là vùng rủi ro cao. APIs có thể thay đổi lớn giữa major versions; không mang subclass cũ sang rồi chỉ sửa compile errors.

Kiểm tra:
- Có thật sự cần custom Dialect không?
- Built-in Dialect target đã hỗ trợ DB version chưa?
- Custom functions có thể dùng function contributor?
- Custom SQL types có thể dùng JdbcType/TypeContributor?
- Pagination/locking/sequence overrides còn cần không?
- Dialect mới đã hỗ trợ native feature chưa?

Ưu tiên extension points công khai của target version và test trên DBMS thật.

## 10. Identifier quoting, naming và aliases

Tên bảng/cột có thể trùng reserved words hoặc bị quote khác theo Dialect. Native SQL hardcode quoted names có thể không chạy khi schema/naming strategy thay đổi.

Kiểm tra:

- Implicit naming strategy.
- Physical naming strategy.
- Quoted identifiers và reserved words.
- Case sensitivity.
- Schema/catalog qualification.
- Generated aliases.
- Join table và foreign key names.

Không dùng alias Hibernate sinh ra trong code ngoài ứng dụng; alias thường là implementation detail.

### 10.1. Native SQL cần inventory riêng

Native SQL tham chiếu table/column thật. Nếu naming strategy hoặc DDL đổi, HQL có thể vẫn đúng trong khi native SQL fail. Kiểm tất cả native queries trên schema target sau migration.

## 11. Pagination, sorting và fetch joins

Một query fetch collection:

~~~java
select distinct o
from PurchaseOrder o
left join fetch o.lines
order by o.createdAt desc
~~~

Nếu kết hợp setFirstResult/setMaxResults, SQL rows do join tạo ra có thể nhiều hơn số root entities. Hibernate có thể phải xử lý pagination ở application side trong một số trường hợp, dẫn tới đọc quá nhiều rows.

### 11.1. Kiểm tra warning và SQL

Dùng cấu hình fail-fast phù hợp target version, ví dụ `hibernate.query.fail_on_pagination_over_collection_fetch` nếu được hỗ trợ. Đọc logs để phát hiện pagination over collection fetch.

### 11.2. Tách query IDs và fetch graph

Một pattern có thể phù hợp:

1. Query page of root IDs với điều kiện/order ổn định.
2. Query fetch graph cho đúng IDs của page.
3. Khôi phục thứ tự page nếu cần.

Cần xử lý tenant scope, deleted rows và concurrent changes giữa hai queries. Nếu snapshot consistency quan trọng, chọn isolation/transaction phù hợp.

### 11.3. Keyset pagination

Với dataset lớn, keyset pagination thường tránh OFFSET sâu. Query cần sort keys ổn định và unique tie-breaker. Khi nâng Hibernate, kiểm cú pháp pagination và SQL do Dialect sinh ra.

## 12. Bulk mutation và SQL strategy

HQL bulk UPDATE/DELETE không tương đương entity-by-entity operations. Với inheritance mappings hoặc mutation tác động nhiều tables, Hibernate có thể cần nhiều statements hoặc chiến lược temporary table/CTE tùy Dialect và provider version.

Kiểm tra:
- Rows thực sự bị ảnh hưởng.
- FK/cascade constraints.
- Version increments/optimistic checks.
- Persistence Context stale state.
- L2/query cache cleanup.
- Audit events.
- Transaction rollback.
- SQL plan và locking.

Query compile thành công chưa chứng minh nó còn cập nhật đúng số rows hoặc giữ đúng transaction semantics.

### 12.1. L1 state sau bulk DML

~~~java
entityManager.flush();

int changed = entityManager.createQuery(
        """
        update Product p
        set p.status = :next
        where p.status = :previous
        """
    )
    .setParameter("next", ProductStatus.ARCHIVED)
    .setParameter("previous", ProductStatus.ACTIVE)
    .executeUpdate();

entityManager.clear();
~~~

`clear()` detach toàn bộ Persistence Context; flush pending changes trước nếu cần giữ chúng. Không coi clear là invalidation cho mọi application cache.

## 13. Kiểm tra behavior, không chỉ query compilation

| Nhóm test | Điều cần xác nhận |
| --- | --- |
| Entity selection | Entity, associations và tenant đúng |
| Scalar projection | Java result type và NULL handling |
| DTO constructor | Argument order và type |
| Aggregate | COUNT/SUM/AVG return type và empty result |
| Parameters | Named/positional, null, enum, temporal |
| Functions | SQL rendering và return type |
| Joins | Optional association và cardinality |
| Pagination | Root row count và order ổn định |
| Bulk DML | Affected count, L1, version và audit |
| Native SQL | Schema names, JDBC types và syntax |
| Locking | Lock clauses, timeout và transaction outcome |
| Multi-tenant | Không đọc/ghi chéo tenant |

### 13.1. Dữ liệu biên

Bổ sung fixtures cho:
- Không có rows và chỉ một row.
- Nhiều rows cùng sort key.
- NULL ở optional attributes.
- Association không tồn tại.
- Numeric boundary/precision.
- Unicode/case/collation.
- Temporal boundary/timezone.
- Enum values cũ/mới.
- UUID/binary values.
- Tenant có cùng local identifiers.
- Batch lớn và page cuối.

## 14. So sánh SQL trước và sau upgrade

Trong môi trường test/dev có thể bật:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
~~~

Để xem bind values, Hibernate 6 có logging category cho JDBC bind, thường là `org.hibernate.orm.jdbc.bind` ở TRACE. Xác nhận logger theo đúng target version; bind logs có thể chứa dữ liệu nhạy cảm nên chỉ bật có kiểm soát.

Thu thập:
- SQL trước và sau.
- Bind parameter types/values an toàn.
- Execution plan trên cùng DBMS và dữ liệu tương đương.
- Rows đọc/ghi.
- Latency và DB resource metrics.

### 14.1. SQL khác không đồng nghĩa query sai

Alias khác hoặc join order khác có thể vẫn đúng. Ngược lại, SQL gần giống chưa chắc behavior giống nếu JDBC type binding hoặc transaction semantics đổi.

Đánh giá correctness và performance độc lập:

- **Correctness:** query trả/ghi đúng dữ liệu và giữ invariants.
- **Performance:** query plan, rows scanned, locks, round trips và latency chấp nhận được.

## 15. Query plan có thể đổi dù SQL trông tương tự

Database optimizer chọn plan dựa trên SQL, parameter types, statistics, indexes, cardinality và DB configuration. Type binding khác có thể làm DB chọn plan khác hoặc không dùng index như trước.

Kiểm tra:
- EXPLAIN/execution plan theo DBMS.
- Index scan vs sequential/table scan.
- Join algorithms.
- Estimated vs actual row counts.
- Sort/hash memory và temporary spills.
- Lock waits.
- Parameter-sensitive plans.
- Latency ở cardinalities đại diện.

Không tối ưu dựa trên dataset quá nhỏ; dùng dữ liệu và statistics gần production.

## 16. Các vùng đáng chú ý khi chuyển Hibernate 5 sang 6

Đây là bản đồ những vùng thường phải đọc trong migration guide, không phải danh sách đầy đủ mọi thay đổi của mọi bản 6.x.

### 16.1. Jakarta Persistence namespace

Hibernate 6 chuyển sang hệ Jakarta Persistence. Imports `javax.persistence.*` cần chuyển sang `jakarta.persistence.*` cùng dependencies/framework tương thích.

Đây là thay đổi source/binary ecosystem, không chỉ query syntax. Kiểm annotations, converters, entity listeners, Criteria, metamodel, validation integration và third-party libraries.

### 16.2. Query API

Các APIs cũ và overloads có thể thay đổi hoặc bị loại bỏ. Inventory việc dùng:
- Session.createQuery.
- Session.createSQLQuery và native query APIs.
- org.hibernate.Query cũ so với org.hibernate.query.Query.
- createSelectionQuery/createMutationQuery ở phiên bản hỗ trợ.
- Query result typing và typed overloads.
- Query hints và parameter binding APIs.

Sửa theo migration guide thay vì rename hàng loạt rồi giả định semantics giữ nguyên.

### 16.3. HQL engine và semantic checking

Hibernate 6 tổ chức lại query engine với semantic query model và SQL AST. Query cũ dựa vào parse/type inference linh hoạt có thể cần sửa. Ưu tiên query rõ kiểu, explicit joins và parameter types chính xác.

### 16.4. Type system và custom types

Các extension type APIs thay đổi đáng kể. Kiểm UserType, BasicType, JavaType, JdbcType, type contributors, binder/extractor và SQL type codes. Test round-trip và query binding; compile thành công chưa đủ.

### 16.5. Dialect và SQL generation

Dialect APIs thay đổi; built-in Dialects và SQL rendering có thể khác. Nếu có custom Dialect, function registration hoặc custom SQL type, review riêng. Không copy subclass cũ một cách máy móc.

### 16.6. SQL aliases và bind logging

Alias/formatting có thể đổi. Điều chỉnh SQL snapshot tests nếu chúng so sánh chi tiết không ổn định. Kiểm logger categories và bind behavior theo version mới.

## 17. Minor upgrades cũng có thể đổi behavior

Không chỉ major upgrades mới có behavior changes. Một bug fix trong minor release có thể thay đổi:
- Query edge-case handling.
- SQL rendering cho một Dialect.
- Locking hoặc pagination.
- Type inference cho expression/function.
- Cache invalidation.
- Parameter binding.
- Schema tooling.

Khi đọc release notes, tìm theo query pattern, DBMS/Dialect và issue IDs. Đừng bỏ qua các minor releases giữa current và target.

## 18. Quy trình nâng cấp có kiểm soát

~~~mermaid
flowchart TD
    A["Pin current and target versions"] --> B["Read migration guide and release notes"]
    B --> C["Inventory queries, types and extensions"]
    C --> D["Migrate APIs and compile"]
    D --> E["Run query/type integration tests"]
    E --> F["Capture generated SQL and plans"]
    F --> G{"Correctness and performance acceptable?"}
    G -- No --> H["Fix query, mapping or Dialect integration"]
    H --> E
    G -- Yes --> I["Run DBMS and workload regression suite"]
    I --> J["Deploy gradually and monitor"]
~~~

### 18.1. Chuẩn bị

- Pin Hibernate, JPA, Spring Boot, JDK và JDBC driver versions.
- Đọc migration guide và release notes liên quan.
- Inventory queries, native SQL, functions và custom types.
- Lưu baseline results/SQL/plans cho query quan trọng.
- Chuẩn bị DB test giống production.

### 18.2. API migration

- Cập nhật Jakarta namespace nếu target yêu cầu.
- Sửa Query APIs bị thay đổi.
- Chuyển custom types và Dialect extensions.
- Kiểm framework BOM để tránh trộn Hibernate versions.
- Không nâng nhiều dependencies độc lập nếu chưa biết compatibility matrix.

### 18.3. Query correctness

Với mỗi query trọng yếu:
1. Parse/execute trên target Hibernate.
2. Xác nhận result type.
3. Xác nhận parameters và null handling.
4. Kiểm joins, subqueries và functions.
5. Kiểm tenant/security predicates.
6. Kiểm affected rows cho mutations.
7. Kiểm persistence context và cache.
8. Verify trên DBMS thật.

### 18.4. SQL/performance

- Capture SQL và bind types.
- So sánh execution plans.
- Kiểm index usage và row counts.
- Kiểm pagination/fetch behavior.
- Kiểm locking/transaction duration.
- Chạy workload với cardinality gần production.
- Ghi query regression và phương án rollback.

### 18.5. Rollout

Nếu hệ thống lớn, nâng cấp theo môi trường/canary. Theo dõi query latency, DB CPU, connection pool, error rates, deadlocks, timeouts và slow query logs. Có rollback plan phù hợp schema/data migrations; không giả định revert dependency là đủ nếu mapping/schema đã thay đổi.

## 19. Viết test bền vững qua nâng cấp

Một test tốt kiểm contract ứng dụng cần, không khóa chặt implementation detail không ổn định.

### 19.1. Ưu tiên behavior assertions

~~~java
assertEquals(expectedIds, actual.stream()
        .map(PurchaseOrder::getId)
        .toList());
~~~

SQL snapshot test có thể hữu ích cho query critical, nhưng nên normalize alias/whitespace và tách assertion semantics khỏi formatting.

### 19.2. Assert result types rõ

~~~java
BigDecimal total = query.getSingleResult();
assertEquals(new BigDecimal("125.50"), total);
~~~

Tránh chuyển monetary values sang double nếu domain yêu cầu decimal precision. Định nghĩa scale/rounding policy rõ.

### 19.3. Kiểm NULL và empty results

Một query có thể trả empty list, NULL aggregate hoặc NoResultException tùy API/method. Test riêng để không biến behavior khác nhau thành bug ở service layer.

### 19.4. Test mọi DBMS được hỗ trợ

Nếu ứng dụng chạy PostgreSQL và Oracle, không test một Dialect rồi suy ra Dialect kia. Native SQL, function rendering, pagination và type mapping cần integration tests riêng.

## 20. Checklist đọc release notes cho query/type/SQL

| Chủ đề | Câu hỏi |
| --- | --- |
| HQL grammar | Cú pháp đang dùng có đổi hoặc bị loại bỏ không? |
| JPQL compliance | Strictness/setting có ảnh hưởng không? |
| Semantic typing | So sánh, CASE, COALESCE, function expressions có đổi không? |
| Result typing | Typed query, Tuple, DTO, aggregates có đổi không? |
| Parameters | Null, enum, temporal, UUID, positional/named binding có đổi không? |
| Custom functions | Function registry API/return type có đổi không? |
| Custom types | UserType/JavaType/JdbcType/binder/extractor có đổi không? |
| Dialect | Built-in/custom Dialect có API hoặc SQL behavior đổi không? |
| SQL generation | Joins, aliases, casts, quoting, pagination, locks có đổi không? |
| Bulk mutation | Multi-table UPDATE/DELETE strategy có đổi không? |
| Fetching | Fetch join, batch fetching, pagination có đổi không? |
| Caching | L1/L2/query cache cleanup và query spaces có đổi không? |
| Schema | DDL, sequence, identity, column types có đổi không? |
| Diagnostics | Logger categories, exception types, SQL comments có đổi không? |

## 21. Lỗi thường gặp khi nâng cấp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| HQL cũ parse fail | Grammar/semantic checking đổi | Đọc migration guide, viết query rõ hơn |
| DTO projection cast fail | Constructor/selection type mismatch | Typed DTO/Tuple và test |
| Null parameter binding fail | Không suy ra type | Khai báo type hoặc sửa predicate |
| Enum query không match | Mapping/binding không thống nhất | Bind enum đúng Java type, kiểm column |
| UUID native query lỗi | JDBC type/storage khác | Kiểm schema, driver và type mapping |
| Date range lệch | Temporal type/timezone/precision | Xác định Java/DB timezone contract |
| Function không chạy | Function registry/return type đổi | Đăng ký theo API target và test Dialect |
| SQL syntax error | Dialect rendering/custom Dialect cũ | Kiểm SQL sinh ra và Dialect |
| Query chậm hơn | Plan, parameter type, join hoặc index đổi | EXPLAIN trên dữ liệu gần production |
| Pagination sai | Collection fetch join | Tách ID page và fetch graph |
| Bulk DML sai rows | Mutation/tenant/version assumptions | Kiểm affected count và SQL |
| Native mapping sai | JDBC type/result extraction | Kiểm scalar/entity mapping |
| SQL snapshot tests fail | Alias/formatting đổi | Assert behavior, normalize SQL |
| Custom type compile fail | Type SPI đổi | Port theo JavaType/JdbcType/UserType docs |

## 22. Bài tập thực hành

### Bài 1 — Query inventory

Ứng dụng có 150 repository methods, 20 native queries, 5 custom functions và 3 custom UserTypes. Hãy lập thứ tự ưu tiên review trước major upgrade.

### Bài 2 — Typed query

Một query chọn id và status nhưng code cast từ Object. Hãy sửa thành DTO projection hoặc Tuple và nêu assertions.

### Bài 3 — Parameter inference

Native query bind null vào parameter trong predicate. Vì sao type có thể mơ hồ? Nêu hai cách xử lý.

### Bài 4 — Temporal mapping

Query lọc createdAt lệch một giờ sau upgrade. Những Java types, timezone settings, JDBC types và DB column definitions nào cần kiểm tra?

### Bài 5 — Function registration

Ứng dụng có custom HQL function trả BigDecimal. Hãy liệt kê function descriptor cần khai báo và tests trên từng Dialect.

### Bài 6 — Implicit join

Một HQL path đi qua association optional. Vì sao SQL join semantics ảnh hưởng kết quả? Viết lại bằng LEFT JOIN nếu cần giữ root rows.

### Bài 7 — Fetch join pagination

Query fetch collection rồi setMaxResults. Vì sao cần kiểm SQL row count và pagination strategy? Nêu cách tách ID page và fetch query.

### Bài 8 — SQL aliases

Sau upgrade, SQL snapshot fail vì alias khác nhưng result giống. Khi nào nên cập nhật snapshot, khi nào nên test behavior?

### Bài 9 — Custom UserType

Custom type compile nhưng dữ liệu load lại khác giá trị persist. Hãy kiểm binder, extractor, mutability, null handling và JDBC type.

### Bài 10 — Dialect

Ứng dụng subclass Dialect cũ để render pagination và function. Vì sao không nên chỉ sửa compile errors? Nêu tests trên DBMS thật.

### Bài 11 — Bulk mutation

Bulk UPDATE thay đổi entity có @Version và Envers. Vì sao compile/execute thành công không chứng minh versioning/audit semantics còn đúng?

### Bài 12 — Query plan regression

SQL sau upgrade gần giống cũ nhưng chậm hơn 10 lần. Những yếu tố parameter type, statistics, indexes, join plan và bind values nào cần thu thập?

### Bài 13 — Native SQL compatibility

Native query hardcode table/column names. Naming strategy hoặc schema migration thay đổi. Hãy đề xuất cách quản lý query và integration tests.

### Bài 14 — Multi-DBMS

Ứng dụng hỗ trợ PostgreSQL và Oracle, dùng functions, pagination và UUID. Hãy thiết kế test matrix theo Hibernate Dialect và JDBC driver.

### Bài 15 — Rollout

Xây dựng kế hoạch canary upgrade với query metrics, SQL errors, deadlocks, connection pool, rollback và schema compatibility.

**Gợi ý:** (1) ưu tiên native/custom types/functions/bulk/fetch joins; (2) DTO/Tuple typed; (3) explicit type hoặc predicate rõ; (4) Instant/LocalDateTime/timezone/precision; (5) arguments, rendering, return type; (6) optional association semantics; (7) page IDs trước; (8) không khóa alias không ổn định; (9) bind/extract round-trip; (10) Dialect SPI và SQL behavior; (11) bulk bypass per-entity lifecycle; (12) execution plan và parameter types; (13) inventory native SQL; (14) test từng DBMS; (15) rollout theo môi trường và monitor.

## 23. Tài liệu tham khảo

- [Hibernate ORM 6.6 Migration Guide](https://docs.hibernate.org/orm/6.6/migration-guide/): thay đổi khi chuyển sang Hibernate 6.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): Query Language, basic types, custom types, fetching, caching và Dialects.
- [Hibernate Query Language Reference](https://docs.hibernate.org/orm/6.6/querylanguage/html_single/Hibernate_Query_Language.html): grammar, expressions, joins, functions, subqueries và mutations.
- [Hibernate ORM 6.6 Javadocs](https://docs.hibernate.org/orm/6.6/javadocs/): query APIs, type system, Dialect và extension points.
- [Jakarta Persistence Specifications](https://jakarta.ee/specifications/persistence/): JPQL, Criteria, typed queries, parameter binding và result semantics.
- [Spring Boot Reference — Data Access](https://docs.spring.io/spring-boot/reference/data/sql.html): dependency management và persistence integration.
- [PostgreSQL EXPLAIN Documentation](https://www.postgresql.org/docs/current/using-explain.html): đọc query plan trên PostgreSQL.

**Kết luận:** trước khi nâng Hibernate, hãy đọc migration guide và release notes theo đúng version, inventory HQL/JPQL/Criteria/native queries, custom functions, custom types và Dialect extensions. Kiểm tra query grammar, semantic typing, result types, parameter binding và Java/JDBC/database mappings; sau đó so sánh SQL sinh ra và execution plans trên DBMS thật. Một query compile không chứng minh result mapping, tenant scope, locking, bulk semantics hay performance vẫn đúng. Ưu tiên typed queries, explicit joins, parameter types rõ ràng và integration tests cho các query quan trọng. Chỉ tiếp tục rollout khi correctness lẫn performance contract đều được xác nhận.
