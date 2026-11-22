# Kiểm tra thay đổi bộ phân tích JPQL, native query và count query khi nâng cấp

Khi nâng cấp Spring Data JPA hoặc Hibernate, query cũ có thể gặp lỗi dù mã repository không thay đổi. Nguyên nhân có thể đến từ parser dùng để phân tích và viết lại query, từ bộ phân tích ngữ nghĩa của JPA provider, từ cách Spring Data tạo count query cho phân trang, hoặc từ SQL mà database thực thi.

Cần phân biệt ba lớp:

1. **Spring Data query enhancer/parser** đọc query khai báo để nhận diện projection, alias, sort và tạo count query.
2. **JPA provider parser** kiểm tra query JPQL/HQL và chuyển thành mô hình truy vấn nội bộ. Với Hibernate 6, mô hình này là Semantic Query Model (SQM).
3. **Database SQL parser/optimizer** phân tích SQL cuối cùng do provider sinh ra hoặc SQL native do ứng dụng viết.

Native SQL còn có một đường riêng: Spring Data có thể dùng regex-based enhancer hoặc JSqlParser để hỗ trợ rewrite/sort/count, nhưng database mới là nơi xác thực cú pháp SQL và schema. JSqlParser không thay thế parser của database.

Bài này tập trung vào cách nhận diện thay đổi giữa các phiên bản Spring Data JPA/Hibernate, kiểm tra native query và bảo đảm count query đúng. Ví dụ dùng Jakarta Persistence trong Spring Boot 3+; khi áp dụng, hãy dùng đúng version được Spring Boot/Spring Data BOM quản lý.

## 1. Bốn loại query cần kiểm tra khi nâng cấp

Spring Data JPA có nhiều cách tạo query, và mỗi cách chịu ảnh hưởng khác nhau:

| Loại query | Cách tạo | Thành phần cần kiểm tra |
|---|---|---|
| Derived query | Phân tích tên method như findByStatusAndCreatedAtAfter | Spring Data method-name parser, property traversal, query semantics |
| JPQL trong @Query | Chuỗi JPQL/HQL khai báo trực tiếp | Spring Data query enhancer và parser của JPA provider |
| Native SQL | @Query(nativeQuery = true) hoặc @NativeQuery ở phiên bản hỗ trợ | Native query enhancer, JSqlParser/regex, JDBC driver và database |
| Count query | Sinh tự động hoặc khai báo countQuery | Query enhancer, phép đếm theo đúng semantics, kiểu kết quả và pagination |

Một lỗi ở tầng parser không nhất thiết là lỗi SQL. Ví dụ, Spring Data có thể không rewrite được một native query phức tạp để thêm ORDER BY hoặc tạo count query, dù câu SQL gốc chạy bình thường trong database client. Ngược lại, parser có thể đọc được query nhưng Hibernate hoặc database vẫn từ chối khi thực thi vì sai property, kiểu dữ liệu hoặc cú pháp dialect.

## 2. Phân biệt parser của Spring Data với parser của Hibernate

### 2.1. Spring Data query enhancer

Spring Data cần hiểu cấu trúc query khai báo để thực hiện các công việc như:

- Xác định phần SELECT/projection và alias.
- Viết lại projection cho interface/DTO projection trong một số trường hợp.
- Thêm Sort động vào query.
- Tạo count query cho Page.
- Nhận diện query phức tạp để chọn chiến lược xử lý.

Từ Spring Data JPA 3.1, Spring Data giới thiệu parser dựa trên ANTLR cho HQL và JPQL. Bài viết công bố của Spring mô tả rằng query JPA có thể dùng HQL parser khi Hibernate có trên classpath; nếu không có Hibernate thì dùng parser JPQL theo đặc tả. Tài liệu các dòng mới hơn mô tả các parser chuyên biệt cho HQL (Hibernate) và EQL (EclipseLink).

Cách chọn enhancer phụ thuộc phiên bản Spring Data JPA, provider và cấu hình repository. Không nên suy luận chỉ từ phiên bản Hibernate. Hãy kiểm tra tài liệu đúng release train của dự án.

### 2.2. Hibernate runtime parser và SQM

Hibernate 6 chuyển HQL/Criteria sang mô hình Semantic Query Model (SQM). Quy trình khái quát:

```text
HQL / JPQL / Criteria
        |
        v
Tokenizer và parser
        |
        v
Semantic Query Model (SQM)
        |
        v
SQL AST
        |
        v
Dialect SQL translator
        |
        v
SQL gửi tới database
```

SQM giúp Hibernate kiểm tra ngữ nghĩa và kiểu của biểu thức rõ hơn trước khi sinh SQL. Vì vậy, query từng được Hibernate 5 chấp nhận do cách diễn giải lỏng hơn có thể bị từ chối sau khi nâng lên Hibernate 6.

### 2.3. Database parser

Database chỉ nhận SQL cuối cùng. Nếu dùng JPQL, Hibernate/EclipseLink chuyển JPQL thành SQL trước khi database parse. Nếu dùng native query, database parse SQL do ứng dụng cung cấp.

Spring Data parser và Hibernate parser không kiểm tra được mọi khác biệt về function, operator, kiểu dữ liệu, JSON syntax, CTE hay hint của từng database. Integration test trên đúng database engine vẫn là bước bắt buộc.

## 3. Kiểm tra thay đổi Spring Data JPA theo version

Khi nâng Spring Boot, không chỉ nhìn version Spring Data JPA. Hãy ghi nhận cả dependency graph:

- Spring Boot version.
- Spring Data JPA version.
- Spring Data Commons version.
- Hibernate ORM hoặc EclipseLink version.
- JSqlParser version nếu được dùng.
- JDBC driver và database version.

Spring Boot BOM thường quản lý các version tương thích. Không nâng riêng Hibernate hoặc JSqlParser vượt khỏi dependency management nếu chưa xác nhận compatibility.

### 3.1. Mốc Spring Data JPA 3.1 và parser JPQL/HQL

Spring Data JPA 3.1 giới thiệu parser JPQL/HQL dựa trên ANTLR để xử lý các query phức tạp hơn khi rewrite Sort/projection/count. Điều này cải thiện việc nhận diện alias và vị trí đặt ORDER BY/count projection so với các thao tác dựa trên xử lý chuỗi đơn giản.

Điều đó không có nghĩa mọi query JPQL/HQL đều được chấp nhận. Query vẫn phải hợp lệ theo parser được chọn và theo JPA provider khi thực thi. HQL có thể có tính năng riêng của Hibernate mà JPQL portable không có; nếu dự án phụ thuộc HQL extension, hãy xác nhận parser đang dùng là HQL parser.

### 3.2. Dòng Spring Data JPA mới hơn

Tài liệu hiện hành mô tả các query parser chuyên biệt cho HQL và EQL. Với native SQL, Spring Data dùng một enhancer riêng vì SQL khác nhau đáng kể giữa các database. Built-in SQL enhancer chỉ hỗ trợ các query đơn giản cho việc introspection và count derivation.

Các API/configuration mới có thể khác giữa các release train. Trước khi dùng `@NativeQuery`, `QueryEnhancerSelector`, hoặc cấu hình parser native, hãy xác nhận chúng tồn tại trong đúng version đang dùng. Nếu phiên bản chưa có `@NativeQuery`, dùng `@Query(nativeQuery = true)`.

## 4. Những thay đổi HQL/JPQL đáng chú ý khi nâng Hibernate 5 lên 6

Hibernate 6 thay đổi parser và kiểm tra ngữ nghĩa query. Một số pattern cũ cần được rà soát.

### 4.1. Dùng property Java thay vì tên cột SQL trong HQL

HQL/JPQL truy vấn entity và persistent attribute, không truy vấn trực tiếp tên cột vật lý.

Không nên viết:

```java
// Sai trong HQL/JPQL nếu order_status chỉ là tên cột SQL.
@Query("select o from PurchaseOrder o where o.order_status = :status")
List<PurchaseOrder> findByStatus(String status);
```

Dùng property Java:

```java
@Query("""
    select o
    from PurchaseOrder o
    where o.status = :status
    """)
List<PurchaseOrder> findByStatus(
    @Param("status") OrderStatus status
);
```

Mapping `@Column(name = "order_status")` sẽ chuyển property `status` thành cột SQL tương ứng. Native SQL mới dùng tên cột vật lý.

### 4.2. So sánh association với scalar foreign key

Hibernate cũ từng chấp nhận một số biểu thức so sánh association với ID scalar. Hibernate 6 yêu cầu kiểu hai vế tương thích rõ ràng hơn.

Không nên dựa vào:

```java
// Pattern cũ có thể bị từ chối.
where o.customer = :customerId
```

Nếu muốn so sánh foreign key:

```java
@Query("""
    select o
    from PurchaseOrder o
    where o.customer.id = :customerId
    """)
List<PurchaseOrder> findByCustomerId(
    @Param("customerId") Long customerId
);
```

Nếu muốn so sánh association với entity, bind một entity reference:

```java
Customer customerRef =
    entityManager.getReference(Customer.class, customerId);

// Query có thể so sánh o.customer = :customerRef.
```

Dùng `association.id` khi mục tiêu là so sánh khóa ngoại. Dùng entity reference khi semantics thực sự là so sánh entity.

### 4.3. UPDATE không còn chấp nhận FROM tùy chọn

Hibernate 5 cho phép cú pháp như:

```sql
update from PurchaseOrder o
set o.status = :status
```

Để tương thích JPQL và Hibernate 6, bỏ FROM:

```java
@Modifying
@Query("""
    update PurchaseOrder o
    set o.status = :status
    where o.id = :id
    """)
int updateStatus(
    @Param("id") Long id,
    @Param("status") OrderStatus status
);
```

### 4.4. Không còn tự truyền identifier lạ xuống SQL

Hibernate 5 từng cho phép một số identifier không được hiểu là property đi xuyên qua HQL function rồi xuất hiện trong SQL. Cách này đã bị loại bỏ vì có thể tạo query khó dự đoán.

Nếu cần truyền literal SQL fragment được hỗ trợ, Hibernate 6 có function `sql(...)` cho các tình huống cụ thể, ví dụ:

```hql
select substring(e.description, 21, 11, sql('octets'))
from AnEntity e
```

Đây là cú pháp riêng Hibernate, không phải JPQL portable. Chỉ dùng literal do ứng dụng kiểm soát, không đưa input người dùng vào SQL fragment.

### 4.5. So sánh path và kiểu dữ liệu

Hibernate 6 kiểm tra kiểu biểu thức chặt chẽ hơn. Ví dụ entity path không nên so sánh trực tiếp với ID scalar:

```java
// Không đúng kiểu:
where o.customer = 42

// So sánh ID:
where o.customer.id = 42
```

Kiểm tra cả Criteria API: hai vế của predicate, subquery selection và expression phải tương thích kiểu. Một Criteria query có thể biên dịch Java thành công nhưng vẫn bị Hibernate từ chối lúc tạo query vì kiểu expression không hợp lệ.

### 4.6. DISTINCT và join fetch

Hibernate 6 thay đổi cách loại trùng root entity khi join fetch collection. Không nên giữ hoặc xóa `DISTINCT` chỉ dựa trên giả định cũ. Xem SQL sinh ra, kết quả trả về và chi phí database thực tế. `DISTINCT` trong JPQL có thể được truyền xuống SQL; điều này có thể ảnh hưởng execution plan.

### 4.7. Kiểu kết quả của native COUNT

Hibernate 6 thay đổi mapping SQL BIGINT sang Java `Long` theo mặc định trong các trường hợp tương ứng. Native query trả `count(*)` trước đây có thể được ứng dụng nhận là `BigInteger`, nhưng sau nâng cấp có thể là `Long`.

Ví dụ cần rà soát:

```java
// Kiểm tra kiểu kết quả thực tế sau khi nâng Hibernate.
Number total = (Number) entityManager
    .createNativeQuery("select count(*) from purchase_order")
    .getSingleResult();

long count = total.longValue();
```

Nếu repository/custom code ép trực tiếp sang `BigInteger`, hãy kiểm tra và sửa kiểu trả về theo provider/version. Không giả định mọi database/driver luôn trả cùng Java type cho native aggregate.

## 5. Phân biệt JPQL với native SQL trong @Query

JPQL:

```java
@Query("""
    select o
    from PurchaseOrder o
    where o.status = :status
    """)
List<PurchaseOrder> findByStatus(
    @Param("status") OrderStatus status
);
```

Native SQL:

```java
@Query(
    value = """
        select *
        from purchase_order
        where order_status = :status
        """,
    nativeQuery = true
)
List<PurchaseOrder> findByStatusNative(
    @Param("status") String status
);
```

Khác biệt:

| Nội dung | JPQL | Native SQL |
|---|---|---|
| Entity/table | Entity name | Table name |
| Field/column | Java persistent property | Physical column |
| Association | Path expression / join | SQL JOIN và foreign key |
| Function | JPQL/HQL function | Database SQL function |
| Parser thực thi | JPA provider | Database |
| Spring Data rewrite | HQL/EQL/JPQL enhancer theo version | Regex hoặc JSqlParser theo version/config |
| Portability | Cao hơn nếu dùng JPQL chuẩn | Gắn với database/dialect |

Không đổi `nativeQuery=true` chỉ để làm parser chấp nhận cú pháp. Hãy xác định query đang dùng entity semantics hay SQL vật lý.

## 6. Native query enhancer: regex và JSqlParser

Spring Data cần phân tích native SQL khi phải thêm sort, pagination hoặc tạo count query. SQL có nhiều dialect và cấu trúc; không thể xử lý mọi query chỉ bằng một regex đơn giản.

Hai hướng thường gặp:

- **Built-in regex-based enhancer:** nhẹ, không cần parser SQL bên ngoài, phù hợp query đơn giản.
- **JSqlParser:** thư viện phân tích SQL thành cấu trúc để Spring Data introspect/rewrite query phức tạp hơn.

Tài liệu Spring Data JPA 3.5 mô tả property lựa chọn parser native trong các phiên bản hỗ trợ:

```properties
spring.data.jpa.query.native.parser=auto
```

Các giá trị được tài liệu phiên bản đó mô tả:

| Giá trị | Ý nghĩa |
|---|---|
| `auto` | Tự chọn theo dependency/configuration; đây là mặc định |
| `regex` | Dùng built-in regex-based Query Enhancer |
| `jsqlparser` | Buộc dùng JSqlParser |

Tài liệu 3.5 hướng dẫn đặt property trong file `spring.properties` hoặc system property. Đừng mặc định property này được đọc giống mọi khóa trong `application.properties`; kiểm tra đúng tài liệu và cấu hình của release train đang dùng. Một số version mới có cơ chế chọn enhancer qua `QueryEnhancerSelector`.

Nếu JSqlParser có trên classpath, các version Spring Data được tài liệu hóa có thể tự dùng nó cho native query. Vì vậy, thêm hoặc nâng JSqlParser có thể làm thay đổi cách query được parse/rewrite dù source repository không đổi.

### 6.1. Khi nào regex đủ dùng?

Regex enhancer có thể đủ cho query dạng đơn giản:

```sql
select id, name
from product
where active = true
```

Nhưng các query có thể gây khó khăn:

- CTE bắt đầu bằng WITH.
- UNION/UNION ALL.
- Subquery lồng nhau.
- Window function.
- GROUP BY/HAVING.
- SELECT DISTINCT với projection phức tạp.
- Comment, hint hoặc syntax đặc thù database.
- ORDER BY nằm trong subquery và ORDER BY ở query ngoài.

Không có một danh sách giới hạn cố định áp dụng cho mọi release. Khi query có cấu trúc phức tạp, kiểm tra khả năng enhancer của đúng version hoặc khai báo countQuery tường minh.

### 6.2. JSqlParser không phải database validator

JSqlParser có thể hiểu cấu trúc SQL và giúp Spring Data rewrite query. Nó không xác nhận:

- Table/column có tồn tại trong schema.
- Function có tồn tại trong database.
- Kiểu dữ liệu có tương thích với operator.
- SQL có được database version cụ thể hỗ trợ.
- Query có execution plan tốt hay không.

Một query parse được bởi JSqlParser vẫn có thể bị database từ chối. Ngược lại, một SQL hợp lệ với database vendor-specific có thể không được JSqlParser version hiện tại parse hoặc rewrite chính xác.

Nếu JSqlParser được thêm vào classpath, kiểm tra version tương thích với Spring Data JPA đang dùng và chạy integration test. Tránh override dependency chỉ để có parser mới mà không xem dependency management.

## 7. Kiểm tra count query khi dùng Page

Khi repository method trả `Page<T>`, Spring Data cần biết tổng số phần tử để tính `totalElements` và `totalPages`. Framework có thể tạo count query từ query chính hoặc dùng query do lập trình viên khai báo.

Ví dụ JPQL đơn giản:

```java
@Query("""
    select o
    from PurchaseOrder o
    where o.status = :status
    """)
Page<PurchaseOrder> findByStatus(
    @Param("status") OrderStatus status,
    Pageable pageable
);
```

Spring Data có thể derive count query tương ứng. Tuy nhiên, với query phức tạp, không nên giả định phép biến đổi luôn giữ đúng semantics.

Có thể khai báo countQuery:

```java
@Query(
    value = """
        select o
        from PurchaseOrder o
        join o.customer c
        where c.status = :customerStatus
        """,
    countQuery = """
        select count(o)
        from PurchaseOrder o
        join o.customer c
        where c.status = :customerStatus
        """
)
Page<PurchaseOrder> findPageByCustomerStatus(
    @Param("customerStatus") CustomerStatus customerStatus,
    Pageable pageable
);
```

Query dữ liệu và count query cần cùng predicate nghiệp vụ. Count query không cần ORDER BY và thường không cần fetch join.

## 8. Khi nào cần countQuery tường minh?

Ưu tiên countQuery tường minh khi:

- Native query phức tạp hoặc dùng syntax riêng database.
- Có CTE, UNION, window function hoặc nested subquery.
- Có GROUP BY/HAVING và tổng cần đếm số group.
- Query dùng DISTINCT hoặc projection khiến count derivation khó đoán.
- Có JOIN collection làm nhân bản root row.
- Query dùng nhiều alias hoặc SELECT expression phức tạp.
- Sau upgrade parser, count query sinh ra khác với mong đợi.
- Query chính chạy được nhưng pagination báo lỗi ở count query.

Ví dụ query join collection:

```java
@Query(
    value = """
        select distinct o
        from PurchaseOrder o
        join o.lines line
        where line.productCode = :code
        """,
    countQuery = """
        select count(distinct o.id)
        from PurchaseOrder o
        join o.lines line
        where line.productCode = :code
        """
)
Page<PurchaseOrder> findByLineProductCode(
    @Param("code") String code,
    Pageable pageable
);
```

Nếu đếm `count(o)` trong query join collection, một Order có nhiều Line khớp có thể bị đếm nhiều lần. Dùng `count(distinct o.id)` nếu mục tiêu là đếm entity Order duy nhất.

### 8.1. Count theo nhóm

Nếu query trả một hàng cho mỗi nhóm, count cần đếm số nhóm, không phải số entity nguồn.

Ví dụ SQL native:

```sql
select category_id, count(*)
from product
group by category_id
having count(*) > 5
```

Count đúng cho Page phải đếm số category group thỏa HAVING. Một cách SQL thường dùng là bọc truy vấn nhóm:

```sql
select count(*)
from (
    select category_id
    from product
    group by category_id
    having count(*) > 5
) grouped_categories
```

Cú pháp derived table và alias có thể cần điều chỉnh theo database. JPQL portable không hỗ trợ mọi kiểu subquery trong FROM như SQL; với báo cáo nhóm phức tạp, có thể dùng native SQL, custom repository hoặc một query riêng.

## 9. Native query với countQuery

Với native query, nên khai báo countQuery rõ khi query có cấu trúc phức tạp:

```java
@Query(
    value = """
        select p.*
        from product p
        where p.tenant_id = :tenantId
          and p.active = true
        order by p.created_at desc, p.id desc
        """,
    countQuery = """
        select count(*)
        from product p
        where p.tenant_id = :tenantId
          and p.active = true
        """,
    nativeQuery = true
)
Page<Product> findActiveProducts(
    @Param("tenantId") Long tenantId,
    Pageable pageable
);
```

Trong các version hỗ trợ `@NativeQuery`, có thể dùng annotation này thay cho `@Query(nativeQuery = true)`. Ví dụ tương đương:

```java
@NativeQuery(
    value = """
        select p.*
        from product p
        where p.tenant_id = :tenantId
          and p.active = true
        """,
    countQuery = """
        select count(*)
        from product p
        where p.tenant_id = :tenantId
          and p.active = true
        """
)
Page<Product> findActiveProducts(
    @Param("tenantId") Long tenantId,
    Pageable pageable
);
```

Kiểm tra annotation có trong version đang dùng. `@NativeQuery` là composed annotation cho native query và có thể cung cấp thêm thuộc tính như `sqlResultSetMapping` trong các release hỗ trợ.

Count query cần:

- Giữ tất cả điều kiện filter ảnh hưởng tập kết quả.
- Giữ JOIN cần thiết để áp dụng filter.
- Đếm đúng đơn vị kết quả: row, entity distinct hay group.
- Dùng parameter name/position tương ứng query chính.
- Trả một giá trị count phù hợp với kiểu mà provider/repository mong đợi.
- Không giữ ORDER BY nếu không cần.

## 10. Count projection không thay thế mọi countQuery

Một số phiên bản Spring Data cho phép khai báo `countProjection` để chỉ định phần projection dùng khi derive count query.

Nó hữu ích khi query vẫn đơn giản và phần cần thay đổi chủ yếu là biểu thức count. Nhưng nó không giải quyết mọi vấn đề semantics của JOIN, GROUP BY, UNION, CTE hoặc native SQL vendor-specific.

Nếu count cần một cấu trúc khác với query chính, hãy khai báo toàn bộ `countQuery`. Điều này rõ ràng và dễ review hơn việc cố điều khiển một phép rewrite không còn phù hợp.

## 11. Page, Slice và chi phí count

Không phải endpoint nào cũng cần tổng số trang.

| Return type | Metadata | Count query |
|---|---|---|
| `Page<T>` | Tổng phần tử, tổng trang, số trang hiện tại | Có thể cần để xác định total |
| `Slice<T>` | Có trang tiếp theo hay không | Không cần tổng số trang |
| `List<T>` + Pageable | Chỉ danh sách đã giới hạn | Không có Page metadata |

Nếu UI chỉ có nút “Xem thêm”, dùng Slice có thể tránh count query. Nếu nghiệp vụ cần totalElements/totalPages, Page vẫn phù hợp và cần kiểm tra count query.

Một số trường hợp Spring Data có thể suy ra tổng số từ content mà không thực thi count query. Vì vậy, test query count nên xác nhận cả trường hợp trang đầy và trang cuối; không giả định mỗi lời gọi Page luôn chạy hai SQL.

## 12. Sort và alias khi parser rewrite query

Spring Data có thể thêm Sort vào query khai báo. Với JPQL, Sort property cần là domain property hoặc alias hợp lệ trong query.

Ví dụ:

```java
@Query("""
    select p.name as productName,
           length(p.name) as nameLength
    from Product p
    where p.active = true
    """)
List<Object[]> findNames(Sort sort);
```

Sort theo alias:

```java
Sort.by("nameLength")
```

Query enhancer cần nhận diện alias để đặt ORDER BY ở đúng cấp query. Với subquery hoặc set operation, Sort nên được áp dụng ở outer query theo ý nghĩa kết quả. Một số lỗi rewrite chỉ xuất hiện khi query có ngoặc, UNION hoặc nhiều SELECT.

Không dùng `Sort.by("LENGTH(p.name)")` như property path thông thường. Spring Data có `JpaSort.unsafe(...)` cho một số biểu thức, nhưng biểu thức unsafe phải do ứng dụng kiểm soát và whitelist; không nối input người dùng vào query.

Native SQL dynamic sort còn phụ thuộc enhancer và dialect. Nếu query có cấu trúc phức tạp hoặc ORDER BY đặc thù, viết SQL/query riêng theo sort được whitelist thường đáng tin hơn.

## 13. QueryRewriter là lớp khác với query parser

Spring Data có `QueryRewriter` để thay đổi query ngay trước khi query được chuyển tới EntityManager. Đây là hook tùy chỉnh, không phải parser JPQL/SQL và không thay thế validation.

QueryRewriter có thể được áp dụng cho query thực tế và count query khi phù hợp. Nếu rewriter thay alias, thêm điều kiện hoặc thay cấu trúc, phải bảo đảm count query cũng còn đúng semantics.

Không dùng regex replace toàn chuỗi để sửa query có nhiều alias hoặc subquery nếu không hiểu cấu trúc. Với rewrite phức tạp, cân nhắc custom repository/Criteria hoặc một query builder có AST rõ ràng.

## 14. Những khác biệt native query cần kiểm tra sau upgrade

Native query phụ thuộc database, JDBC driver, parser enhancer và Hibernate result mapping. Hãy kiểm tra:

- Cột và alias trả về có còn đúng mapping entity/DTO không.
- Kiểu dữ liệu aggregate có đổi không, đặc biệt BIGINT/count.
- Parameter binding có đúng kiểu JDBC không.
- Pagination có thêm LIMIT/OFFSET/FETCH đúng dialect không.
- Dynamic Sort có được đặt ở outer query không.
- CTE, UNION, subquery và window function có bị enhancer parse sai không.
- Native countQuery có đúng số entity/group không.
- ResultSet mapping có còn tương thích với provider.
- SQL function/operator có được database version hỗ trợ không.

Đặc biệt, native SQL không được Hibernate phân tích như JPQL. Spring Data có thể parse để rewrite, nhưng database mới quyết định câu SQL có hợp lệ hay không.

## 15. Ma trận lỗi và cách khoanh vùng

| Triệu chứng | Lớp có thể gây lỗi | Cách kiểm tra |
|---|---|---|
| Repository khởi động lỗi khi tạo query | Spring Data query creation hoặc JPA provider validation | Xem root cause, query string và provider version |
| JPQL property không tồn tại | Hibernate/EclipseLink semantic parser | Dùng entity property, kiểm tra mapping |
| JPQL cũ chạy Hibernate 5 nhưng lỗi Hibernate 6 | SQM/semantic validation thay đổi | Soát association comparison, identifier, UPDATE syntax, path types |
| Query chính chạy nhưng Page lỗi | Count query derivation hoặc countQuery | Log riêng count SQL và chạy trực tiếp trên DB |
| Native query chạy DB client nhưng Pageable lỗi | Spring Data native enhancer không rewrite được | Thử JSqlParser nếu version hỗ trợ hoặc khai báo countQuery |
| Thêm JSqlParser khiến query khác behavior | Native enhancer selection/version | Kiểm tra dependency tree và parser selection |
| Sort vào sai cấp subquery | Query enhancer không nhận diện cấu trúc/alias | Đưa Sort vào outer query hoặc viết query riêng |
| Count bị nhân bản | JOIN collection làm trùng root | Dùng count distinct theo ID |
| Count số group sai | Count đếm row nguồn thay vì nhóm | Đếm derived table của grouped query |
| Native count trả sai Java type | Hibernate/JDBC mapping thay đổi | Dùng Number/Long đúng contract và test driver |
| Query parse được nhưng database từ chối | SQL dialect/schema/function | Chạy SQL cuối cùng trên đúng DB version |
| Query chạy nhưng chậm sau upgrade | SQL generation hoặc execution plan đổi | So sánh SQL, EXPLAIN và index |

## 16. Quy trình kiểm tra trước khi nâng cấp

1. Lập danh sách derived query, JPQL @Query, native query và method trả Page.
2. Ghi lại version Spring Boot, Spring Data JPA, Hibernate/EclipseLink, JSqlParser, JDBC driver và database.
3. Xác định query nào phụ thuộc HQL extension hoặc native syntax riêng.
4. Với Hibernate 5 lên 6, rà soát property path, association comparison, UPDATE syntax, kiểu result và native count.
5. Với Spring Data nâng version, kiểm tra thay đổi query enhancer, alias handling, native parser selection và count derivation.
6. Chạy test repository trên database tương thích production.
7. Bật SQL logging trong môi trường test để so sánh query chính và count query.
8. Kiểm tra các query có DISTINCT, JOIN collection, GROUP BY, CTE, UNION, window function và subquery.
9. Viết countQuery tường minh cho query native/phức tạp nếu auto derivation không rõ.
10. Chạy EXPLAIN/EXPLAIN ANALYZE cho query quan trọng.
11. Kiểm tra dependency tree để tránh JSqlParser hoặc Hibernate bị override ngoài BOM.
12. Triển khai theo từng bước và theo dõi lỗi query/runtime sau upgrade.

## 17. Integration test cho query parser và count

Unit test chỉ kiểm tra chuỗi query hoặc mock repository không đủ để xác nhận parser, provider và database cùng hiểu query như nhau.

Dùng `@DataJpaTest` với database test phù hợp; nếu query dùng native syntax đặc thù, ưu tiên Testcontainers với đúng engine/version gần production.

Các test nên có:

- Derived query trả đúng kết quả sau upgrade.
- JPQL @Query chạy với alias, join, subquery và projection thực tế.
- Hibernate 6 không còn query dựa trên cú pháp HQL cũ.
- Native query chạy trực tiếp trên database.
- Native query có Pageable thêm sort/limit đúng.
- Count query trả tổng chính xác khi filter có JOIN.
- JOIN collection dùng count distinct khi đếm entity.
- GROUP BY/HAVING đếm số group đúng.
- CTE/UNION/window function có countQuery tường minh và chạy đúng.
- Native aggregate trả đúng Java type.
- QueryRewriter không làm lệch count query.
- Page content và totalElements khớp fixture đã biết.

Ví dụ test Page:

```java
@DataJpaTest
class PurchaseOrderQueryTest {

    @Autowired
    private PurchaseOrderRepository repository;

    @Test
    void pageCountMatchesFilteredOrders() {
        // Arrange: tạo dữ liệu có nhiều OrderLine
        // và có Order không khớp filter.

        Page<PurchaseOrder> page = repository.findByLineProductCode(
            "SKU-1",
            PageRequest.of(0, 10)
        );

        assertThat(page.getContent()).hasSize(2);
        assertThat(page.getTotalElements()).isEqualTo(2);
    }
}
```

Fixture cần có trường hợp một Order có nhiều Line cùng khớp để test phát hiện count bị nhân bản. Ví dụ chỉ minh họa cấu trúc test; dữ liệu và constructor phải theo entity thực tế.

## 18. Logging và quan sát query

Trong môi trường test/dev, có thể bật log SQL Hibernate:

```properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Bind logging có thể lộ dữ liệu nhạy cảm. Chỉ bật trong môi trường an toàn và tắt sau khi debug.

Khi phân tích lỗi, thu thập:

- Query khai báo trong repository.
- Query sau khi Spring Data rewrite nếu có thể quan sát.
- SQL cuối cùng do Hibernate gửi tới JDBC.
- Bind parameter và kiểu dữ liệu.
- SQL count query.
- Database engine/version và execution plan.
- Root cause exception đầy đủ.

Không chỉ kiểm tra log JPQL hoặc SQL ban đầu. Điều cần xác nhận là câu SQL thực tế và count query thực tế mà database nhận.

## 19. Checklist trước khi merge bản nâng cấp

- [ ] Spring Boot, Spring Data JPA, Hibernate/EclipseLink và driver nằm trong bộ version tương thích?
- [ ] Derived query và property traversal vẫn đúng?
- [ ] JPQL dùng entity property thay vì physical column?
- [ ] HQL extension có phụ thuộc parser/provider cụ thể?
- [ ] Query Hibernate 5 có pattern association = scalar ID cần sửa?
- [ ] UPDATE query có FROM tùy chọn cần loại bỏ?
- [ ] Criteria expression có hai vế cùng kiểu?
- [ ] Native query có phụ thuộc parser enhancer hoặc JSqlParser?
- [ ] Parser native được chọn đúng theo version/config?
- [ ] Query phức tạp có countQuery tường minh?
- [ ] Count query giữ filter và đếm đúng entity/group?
- [ ] DISTINCT/JOIN/GROUP BY/HAVING đã được test?
- [ ] Native count/aggregate có Java type đúng?
- [ ] Sort động được áp dụng ở đúng cấp query?
- [ ] SQL cuối cùng chạy trên database production-compatible?
- [ ] Execution plan và query latency không thoái lui?

## 20. Kết luận

Khi nâng Spring Data JPA và Hibernate, hãy kiểm tra riêng parser của Spring Data, parser ngữ nghĩa của provider và parser SQL của database. Spring Data query enhancer phân tích query để xử lý projection, Sort và count; Hibernate SQM kiểm tra HQL/JPQL và chuyển thành SQL; native SQL được database phân tích sau khi Spring Data thực hiện các rewrite mà enhancer hỗ trợ.

Với JPQL, rà soát các thay đổi ngữ nghĩa của Hibernate 6 như property path, association comparison, UPDATE syntax và kiểu kết quả. Với native query, xác nhận regex/JSqlParser và khả năng rewrite của đúng version; query phức tạp nên có countQuery rõ ràng. Count query phải đếm đúng đơn vị kết quả, đặc biệt khi có JOIN collection, DISTINCT hoặc GROUP BY.

Cuối cùng, chạy integration test trên database mục tiêu, so sánh SQL và count query thực tế, kiểm tra kiểu bind/result và execution plan. Parser giúp framework hiểu cấu trúc query; chỉ kiểm thử trên provider và database thật mới xác nhận query vẫn đúng sau nâng cấp.

## Tài liệu tham khảo chính thức

- Spring Data JPA 3.5 — JPA Query Methods: https://docs.spring.io/spring-data/jpa/reference/3.5/jpa/query-methods.html
- Spring Data JPA current — JPA Query Methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Blog — Spring Data JPA introduces query parser (21 Mar 2023): https://spring.io/blog/2023/03/21/spring-data-jpa-introduces-query-parser/
- Hibernate ORM 6.0 Migration Guide: https://docs.hibernate.org/orm/6.0/migration-guide/migration-guide/
- Hibernate ORM migration guides by series: https://hibernate.org/orm/documentation/migrate/
