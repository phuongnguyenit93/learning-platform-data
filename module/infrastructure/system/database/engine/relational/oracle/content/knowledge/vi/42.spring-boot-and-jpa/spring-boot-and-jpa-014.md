# Stored procedure, native query và giới hạn trừu tượng ORM

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Spring Boot và JPA  
> **Mục tiêu:** Biết khi nào nên dùng JPQL, native SQL hoặc stored procedure trong ứng dụng Spring Boot/JPA; gọi procedure và package Oracle bằng Spring Data JPA, EntityManager và JDBC; ánh xạ tham số IN/OUT, REF CURSOR và kết quả nhiều tập; hiểu giới hạn của ORM đối với SQL đặc thù Oracle, bulk DML, locking và dữ liệu ngoài entity; quản lý flush, persistence context, transaction, mapping, bảo mật và tính portable.

## 1. ORM trừu tượng hóa điều gì?

JPA là specification Java Persistence API, cung cấp mô hình quản lý entity và persistence context. Hibernate thường là JPA provider được dùng trong Spring Boot. Spring Data JPA bổ sung repository abstraction để giảm mã truy cập dữ liệu.

ORM giúp ứng dụng làm việc với object thay vì tự quản lý mọi câu SQL:

- Entity ánh xạ tới bảng hoặc view.
- Field ánh xạ tới column.
- Quan hệ được biểu diễn bằng association.
- Persistence context theo dõi entity được load và thay đổi.
- Dirty checking tạo DML khi flush.
- JPQL truy vấn theo entity và thuộc tính.
- Transaction phối hợp thay đổi dữ liệu.

ORM không xóa bỏ SQL hoặc đặc tính của database. Khi cần window function, hint, CTE, JSON operator, package, stored procedure, bulk update hoặc plan control, abstraction có thể không còn phù hợp.

**Chọn abstraction theo yêu cầu của truy vấn và cách dữ liệu được dùng.** JPQL phù hợp khi thao tác ở mức entity; native SQL phù hợp khi cần kiểm soát câu SQL; stored procedure phù hợp khi logic hoặc thao tác được đóng gói và quản lý tại database.

## 2. Ba cách truy cập dữ liệu cần phân biệt

| Cách | Đơn vị làm việc | Phù hợp khi | Đánh đổi |
|---|---|---|---|
| JPQL / Criteria API | Entity, association, thuộc tính | CRUD và query nghiệp vụ thông thường | Không biểu đạt mọi tính năng Oracle |
| Native SQL | Table, view, SQL expression | Query đặc thù, analytic, hint, CTE, tối ưu theo Oracle | Phụ thuộc schema/dialect, mapping thủ công hơn |
| Stored procedure/package | Procedure/function và contract tham số | Logic cần tái sử dụng ở DB, bulk operation, integration với hệ thống khác | Debug/versioning/deployment và portability phức tạp hơn |

Đây không phải thứ bậc từ tốt tới xấu. Một hệ thống có thể dùng cả ba, với ranh giới rõ ràng.

### 2.1. JPQL

JPQL tham chiếu entity và field Java, không tham chiếu trực tiếp table/column name:

~~~java
@Query("""
    select o
    from OrderEntity o
    where o.customerId = :customerId
      and o.status = :status
    order by o.createdAt desc
    """)
List<OrderEntity> findOrders(
    @Param("customerId") Long customerId,
    @Param("status") OrderStatus status
);
~~~

Provider chuyển JPQL thành SQL theo dialect. Khi đổi database hoặc schema mapping, query có thể ít phải sửa hơn native SQL, nhưng vẫn chịu giới hạn của JPA provider và database.

### 2.2. Native query

Native query là SQL được gửi tới database, thường dùng tên bảng và cột thật:

~~~java
@Query(value = """
    select order_id, customer_id, status, created_at
    from orders
    where customer_id = :customerId
    order by created_at desc
    fetch first :rowLimit rows only
    """, nativeQuery = true)
List<Object[]> findRecentOrders(
    @Param("customerId") Long customerId,
    @Param("rowLimit") int rowLimit
);
~~~

Ví dụ cú pháp FETCH FIRST là đặc thù Oracle release hỗ trợ. Việc bind biến trong row-limiting clause và cách xử lý native pagination cần kiểm tra trên Hibernate/Oracle JDBC version thực tế.

Native SQL cho quyền kiểm soát lớn hơn nhưng ứng dụng phải chịu trách nhiệm về column mapping, datatype, null, paging, locking và persistence-context synchronization.

### 2.3. Stored procedure

Stored procedure thực thi logic trong database. Với Oracle, procedure/function thường được tổ chức trong PL/SQL package:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE close_order(
        p_order_id IN NUMBER,
        p_result   OUT VARCHAR2
    );
END order_api;
/
~~~

Ứng dụng gọi package qua JPA StoredProcedureQuery, Spring Data @Procedure hoặc JDBC CallableStatement.

Procedure hữu ích khi logic được dùng bởi nhiều client, cần bulk operation hoặc cần tận dụng PL/SQL. Tuy nhiên, chuyển logic sang database tạo thêm dependency vào schema, package version, quyền EXECUTE và quy trình deploy.

## 3. Quyết định dùng JPQL, native SQL hay stored procedure

Hãy đặt các câu hỏi sau:

1. Query chỉ lọc/sắp xếp entity và quan hệ thông thường? Ưu tiên JPQL hoặc Criteria.
2. Cần analytic/window function, optimizer hint, SQL feature hoặc access path đặc thù Oracle? Native SQL có thể phù hợp.
3. Logic cần được nhiều ứng dụng gọi chung, hoặc cần thao tác bulk trong database? Cân nhắc package/procedure.
4. Cần trả về entity đang được persistence context quản lý? JPQL thường rõ ràng hơn; native mapping phải cẩn thận.
5. Query có thay đổi dữ liệu ngoài các entity đã load? Cần xử lý flush/clear/cache.
6. Có yêu cầu chạy trên nhiều database? Tránh SQL/PLSQL đặc thù hoặc cô lập chúng trong adapter.
7. Có yêu cầu kiểm soát quyền? Package API có thể giới hạn quyền DML trực tiếp nhưng cần thiết kế definer/invoker rights an toàn.
8. Có cần transaction atomic với các thao tác JPA khác? Kiểm tra cùng DataSource, transaction manager và connection.

### 3.1. Một ví dụ chọn công cụ

| Nghiệp vụ | Lựa chọn thường phù hợp |
|---|---|
| Tìm đơn hàng theo customer và status | JPQL |
| Lấy Top-N theo nhóm với analytic function Oracle | Native SQL |
| Cập nhật trạng thái hàng nghìn đơn theo quy tắc DB dùng chung | Package procedure |
| Gọi hàm tính thuế dùng trong nhiều hệ thống | Function/package hoặc service theo kiến trúc |
| Báo cáo join nhiều bảng, aggregate và hint đã đo hiệu năng | Native SQL |
| Tạo entity mới và quản lý lifecycle | JPA persist |
| Bulk delete theo predicate lớn | JPQL bulk DML hoặc native SQL, có clear context |
| Điều phối workflow có side effect ngoài database | Application service; tránh nhồi toàn bộ vào procedure nếu không cần |

Không chọn stored procedure chỉ vì một query có vẻ dài. Cũng không ép mọi thao tác qua repository nếu query cần semantics mà ORM không thể biểu đạt rõ ràng.

## 4. Khai báo procedure trong Oracle

Ví dụ package có procedure cập nhật trạng thái và trả kết quả:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE close_order(
        p_order_id IN NUMBER,
        p_result   OUT VARCHAR2
    );
END order_api;
/

CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE close_order(
        p_order_id IN NUMBER,
        p_result   OUT VARCHAR2
    )
    IS
    BEGIN
        UPDATE orders
           SET status = 'CLOSED'
         WHERE order_id = p_order_id
           AND status = 'OPEN';

        IF SQL%ROWCOUNT = 1 THEN
            p_result := 'CLOSED';
        ELSE
            p_result := 'NOT_UPDATED';
        END IF;
    END close_order;
END order_api;
/
~~~

Package specification là public contract. Body là implementation. Ứng dụng phụ thuộc tên package, procedure, thứ tự/kiểu tham số và semantics kết quả.

### 4.1. Transaction trong procedure

Procedure trên không gọi COMMIT hoặc ROLLBACK. Transaction owner là ứng dụng gọi procedure, nên thao tác có thể nằm trong cùng transaction với các câu JPA khác.

Đây thường là thiết kế linh hoạt hơn: service layer quyết định commit/rollback.

Nếu procedure tự COMMIT, nó có thể phá vỡ atomicity mà ứng dụng mong đợi. Một service gọi hai repository method và một procedure có thể nghĩ tất cả cùng rollback, nhưng COMMIT bên trong procedure đã làm thay đổi đó không thể rollback theo transaction bên ngoài.

Có những workflow vận hành cần transaction control bên trong database, nhưng phải ghi rõ contract và không trộn lẫn với transaction do Spring quản lý nếu chưa thiết kế.

### 4.2. Quyền EXECUTE

Schema ứng dụng cần quyền EXECUTE trên package:

~~~sql
GRANT EXECUTE ON data_owner.order_api TO app_user;
~~~

Nếu package chạy theo AUTHID DEFINER, owner cần quyền trực tiếp cần thiết trên object mà code sử dụng. Không dựa vào role của caller để cấp quyền cho SQL trong definer-rights stored code.

Ứng dụng không nhất thiết cần UPDATE trực tiếp trên ORDERS nếu mọi thao tác ghi được cung cấp qua package API. Đây là một cách tạo privilege boundary, nhưng package cần validation và authorization đầy đủ.

## 5. Gọi procedure bằng Spring Data JPA @Procedure

Spring Data JPA hỗ trợ khai báo repository method bằng @Procedure. Cách này gọn khi procedure có tham số đơn giản và kết quả scalar.

~~~java
public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {

    @Procedure(
        procedureName = "ORDER_API.CLOSE_ORDER"
    )
    String closeOrder(
        @Param("P_ORDER_ID") Long orderId
    );
}
~~~

Cách map tên procedure/parameter phụ thuộc database, JPA provider và Spring Data JPA version. Với Oracle package, cần kiểm tra tên procedure mà provider truyền vào JDBC và cách driver xử lý call syntax.

Nếu procedure có OUT parameter và method trả về một giá trị, Spring Data có thể map theo khai báo procedure phù hợp. Với nhiều OUT parameters, REF CURSOR hoặc kết quả phức tạp, EntityManager StoredProcedureQuery hoặc JDBC thường rõ ràng hơn.

### 5.1. Dùng @NamedStoredProcedureQuery

Có thể khai báo procedure mapping ở entity:

~~~java
@Entity
@Table(name = "ORDERS")
@NamedStoredProcedureQuery(
    name = "OrderEntity.closeOrder",
    procedureName = "ORDER_API.CLOSE_ORDER",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "P_ORDER_ID",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "P_RESULT",
            type = String.class
        )
    }
)
public class OrderEntity {
    @Id
    @Column(name = "ORDER_ID")
    private Long id;

    // Other mapped fields
}
~~~

Repository:

~~~java
public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {

    @Procedure(name = "OrderEntity.closeOrder")
    String closeOrder(@Param("P_ORDER_ID") Long orderId);
}
~~~

Với procedure có nhiều OUT parameters, kết quả có thể cần được lấy qua StoredProcedureQuery thay vì một giá trị đơn. Cấu hình name và return mapping phải khớp procedure contract.

Một số provider có khác biệt về tên parameter, tên procedure, schema/package qualification và cách map cursor. Test bằng đúng Oracle dialect và driver đang triển khai.

## 6. Gọi procedure bằng EntityManager StoredProcedureQuery

EntityManager API cho phép đăng ký từng tham số và đọc kết quả.

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;

public String closeOrder(long orderId) {
    StoredProcedureQuery query =
        entityManager.createStoredProcedureQuery(
            "ORDER_API.CLOSE_ORDER"
        );

    query.registerStoredProcedureParameter(
        "P_ORDER_ID",
        Long.class,
        ParameterMode.IN
    );

    query.registerStoredProcedureParameter(
        "P_RESULT",
        String.class,
        ParameterMode.OUT
    );

    query.setParameter("P_ORDER_ID", orderId);
    query.execute();

    return (String) query.getOutputParameterValue("P_RESULT");
}
~~~

Import dùng jakarta.persistence cho stack Spring Boot/Jakarta hiện đại. Dự án Spring Boot 2/JPA 2 thường dùng javax.persistence. Không trộn javax và jakarta trong cùng ứng dụng; chọn theo Spring Boot, Hibernate và dependency version.

### 6.1. Đăng ký tham số theo position

JPA hỗ trợ đăng ký theo vị trí:

~~~java
query.registerStoredProcedureParameter(
    1,
    Long.class,
    ParameterMode.IN
);
~~~

Parameter name hoặc position phải phù hợp provider và driver. Với Oracle package, named binding thường dễ đọc nhưng cần kiểm chứng cách provider sinh call statement.

### 6.2. IN, OUT và INOUT

| Mode | Ý nghĩa | Ví dụ |
|---|---|---|
| IN | Ứng dụng truyền giá trị vào | Order ID |
| OUT | Procedure trả giá trị ra | Result code |
| INOUT | Ứng dụng truyền vào và nhận giá trị mới | Counter hoặc trạng thái |
| REF_CURSOR | Procedure trả cursor/result set | Danh sách hàng |

Ví dụ INOUT:

~~~sql
PROCEDURE adjust_counter(
    p_counter IN OUT NUMBER
);
~~~

JPA đăng ký ParameterMode.INOUT và truyền giá trị ban đầu. Sau execute, đọc output parameter theo API/provider hỗ trợ.

### 6.3. Output parameter và execute order

Đối với procedure có OUT parameter, thực thi procedure trước rồi mới đọc output. Một số procedure trả cả update count và result set; thứ tự đọc có thể phụ thuộc JDBC driver và provider.

Đọc API JPA và test trường hợp nhiều kết quả. Không giả định mọi stored procedure chỉ có một kết quả.

## 7. Oracle REF CURSOR

Oracle PL/SQL có thể trả dữ liệu qua SYS_REFCURSOR:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE find_orders(
        p_customer_id IN NUMBER,
        p_result      OUT SYS_REFCURSOR
    );
END order_api;
/

CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE find_orders(
        p_customer_id IN NUMBER,
        p_result      OUT SYS_REFCURSOR
    )
    IS
    BEGIN
        OPEN p_result FOR
            SELECT order_id,
                   customer_id,
                   status,
                   created_at
              FROM orders
             WHERE customer_id = p_customer_id
             ORDER BY created_at DESC;
    END find_orders;
END order_api;
/
~~~

REF CURSOR là cursor do database trả về, được JDBC/provider tiêu thụ như result set theo cách hỗ trợ của driver.

### 7.1. REF_CURSOR với JPA

JPA có ParameterMode.REF_CURSOR trong các phiên bản hỗ trợ. Ví dụ:

~~~java
StoredProcedureQuery query =
    entityManager.createStoredProcedureQuery(
        "ORDER_API.FIND_ORDERS",
        "OrderSummaryMapping"
    );

query.registerStoredProcedureParameter(
    "P_CUSTOMER_ID",
    Long.class,
    ParameterMode.IN
);

query.registerStoredProcedureParameter(
    "P_RESULT",
    void.class,
    ParameterMode.REF_CURSOR
);

query.setParameter("P_CUSTOMER_ID", customerId);
query.execute();

@SuppressWarnings("unchecked")
List<OrderSummary> rows = query.getResultList();
~~~

REF CURSOR mapping phụ thuộc JPA provider, Hibernate version, Oracle dialect và Oracle JDBC driver. Có thể cần register cursor theo position hoặc dùng Oracle-specific JDBC type. Kiểm tra tài liệu phiên bản đang chạy.

Nếu provider không hỗ trợ đúng contract hoặc cần xử lý nhiều cursor, JDBC CallableStatement có thể minh bạch hơn.

### 7.2. REF CURSOR không phải entity tự động

Result set trả về từ procedure có thể không ánh xạ trực tiếp thành entity managed. Nếu dữ liệu là projection/reporting, dùng DTO mapping. Nếu map thành entity, phải đảm bảo có đủ primary key và column mapping chính xác; entity có thể được đưa vào persistence context theo provider.

Không trả entity thiếu khóa hoặc cột cần thiết rồi mong Hibernate quản lý lifecycle đúng.

## 8. Gọi Oracle package bằng JDBC CallableStatement

Khi cần kiểm soát JDBC-specific behavior, dùng CallableStatement qua connection thuộc transaction manager.

Ví dụ OUT scalar:

~~~java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

public String closeOrder(long orderId) throws SQLException {
    try (Connection connection = dataSource.getConnection();
         CallableStatement call =
             connection.prepareCall(
                 "{ call ORDER_API.CLOSE_ORDER(?, ?) }"
             )) {

        call.setLong(1, orderId);
        call.registerOutParameter(2, Types.VARCHAR);
        call.execute();

        return call.getString(2);
    }
}
~~~

Đoạn code minh họa connection tự lấy từ DataSource. Trong ứng dụng Spring transaction-managed, lấy connection theo cơ chế đồng bộ với transaction hiện tại, chẳng hạn thông qua JdbcTemplate hoặc transaction-aware DataSource integration. Không tự lấy một connection độc lập nếu procedure phải cùng transaction với JPA repository.

### 8.1. Dùng JdbcTemplate

Spring JdbcTemplate quản lý resource JDBC như PreparedStatement/CallableStatement và tích hợp với transaction manager nếu cùng DataSource.

~~~java
public String closeOrder(long orderId) {
    return jdbcTemplate.execute(
        "{ call ORDER_API.CLOSE_ORDER(?, ?) }",
        (CallableStatementCallback<String>) call -> {
            call.setLong(1, orderId);
            call.registerOutParameter(2, Types.VARCHAR);
            call.execute();
            return call.getString(2);
        }
    );
}
~~~

JdbcTemplate phù hợp khi cần JDBC control nhưng vẫn muốn Spring quản lý resource và transaction integration.

### 8.2. CallableStatement trả REF CURSOR

Oracle JDBC có hỗ trợ REF CURSOR thông qua Oracle JDBC APIs. Ví dụ với Oracle driver:

~~~java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Types;
import oracle.jdbc.OracleTypes;

try (CallableStatement call =
         connection.prepareCall(
             "{ call ORDER_API.FIND_ORDERS(?, ?) }")) {

    call.setLong(1, customerId);
    call.registerOutParameter(2, OracleTypes.CURSOR);
    call.execute();

    try (ResultSet resultSet = (ResultSet) call.getObject(2)) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("ORDER_ID");
            String status = resultSet.getString("STATUS");
            // Map to DTO
        }
    }
}
~~~

OracleTypes.CURSOR là Oracle-specific extension. JDBC driver version có thể cung cấp các constant/API khác; kiểm tra Oracle JDBC documentation. ResultSet phải được đọc và đóng trước khi CallableStatement/Connection đóng.

## 9. Native query trong Spring Data JPA

Native query thường được khai báo bằng @Query(nativeQuery = true):

~~~java
public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {

    @Query(
        value = """
            select order_id,
                   customer_id,
                   status,
                   created_at
              from orders
             where customer_id = :customerId
               and status = :status
             order by created_at desc
            """,
        nativeQuery = true
    )
    List<Object[]> findOrderRows(
        @Param("customerId") Long customerId,
        @Param("status") String status
    );
}
~~~

Kết quả Object[] không có type safety tốt. Mỗi index phụ thuộc thứ tự cột trong SELECT; đổi projection có thể làm code map sai mà compile không phát hiện.

Dùng DTO/projection khi có thể.

### 9.1. Interface projection

Ví dụ interface projection:

~~~java
public interface OrderRowView {
    Long getOrderId();
    Long getCustomerId();
    String getStatus();
}
~~~

Query cần alias khớp property getter theo cách Spring Data/provider hỗ trợ:

~~~java
@Query(
    value = """
        select order_id as orderId,
               customer_id as customerId,
               status as status
          from orders
         where customer_id = :customerId
        """,
    nativeQuery = true
)
List<OrderRowView> findOrderView(
    @Param("customerId") Long customerId
);
~~~

Alias casing có thể bị Oracle chuẩn hóa về uppercase. Spring Data/Hibernate thường xử lý alias theo projection strategy nhưng cần integration test. Không giả định mọi tên alias camelCase được driver giữ nguyên.

### 9.2. DTO projection

Có thể dùng constructor mapping hoặc @SqlResultSetMapping tùy provider/version. DTO phù hợp khi query trả dữ liệu tổng hợp không đại diện một entity.

Không cố map báo cáo aggregate thành entity chỉ để dùng repository generic.

## 10. EntityResult và ConstructorResult

JPA hỗ trợ @SqlResultSetMapping để mô tả cách map native query result.

Ví dụ DTO:

~~~java
public class OrderSummary {
    private final Long orderId;
    private final String status;
    private final java.math.BigDecimal amount;

    public OrderSummary(
            Long orderId,
            String status,
            java.math.BigDecimal amount) {
        this.orderId = orderId;
        this.status = status;
        this.amount = amount;
    }

    public Long getOrderId() { return orderId; }
    public String getStatus() { return status; }
    public java.math.BigDecimal getAmount() { return amount; }
}
~~~

Khai báo mapping:

~~~java
@SqlResultSetMapping(
    name = "OrderSummaryMapping",
    classes = @ConstructorResult(
        targetClass = OrderSummary.class,
        columns = {
            @ColumnResult(name = "ORDER_ID", type = Long.class),
            @ColumnResult(name = "STATUS", type = String.class),
            @ColumnResult(name = "TOTAL_AMOUNT", type = java.math.BigDecimal.class)
        }
    )
)
@Entity
@Table(name = "ORDERS")
public class OrderEntity {
    @Id
    @Column(name = "ORDER_ID")
    private Long id;
}
~~~

Sử dụng:

~~~java
Query query = entityManager.createNativeQuery(
    """
    select order_id,
           status,
           total_amount
      from orders
     where customer_id = :customerId
    """,
    "OrderSummaryMapping"
);

query.setParameter("customerId", customerId);

@SuppressWarnings("unchecked")
List<OrderSummary> rows = query.getResultList();
~~~

ColumnResult name phải khớp alias/column label trong ResultSet. Với Oracle NUMBER, scale/precision và JDBC type có thể ảnh hưởng Java mapping; dùng BigDecimal cho decimal amount thường an toàn hơn double.

### 10.1. EntityResult

Nếu native query trả toàn bộ cột entity và mapping phù hợp:

~~~java
@SqlResultSetMapping(
    name = "OrderEntityMapping",
    entities = @EntityResult(
        entityClass = OrderEntity.class,
        fields = {
            @FieldResult(name = "id", column = "ORDER_ID"),
            @FieldResult(name = "status", column = "STATUS")
        }
    )
)
~~~

Trong thực tế, EntityResult thường cần đủ các cột được mapping, bao gồm identifier và các field cần thiết theo entity/provider. Association, discriminator, version và embedded fields có thể làm mapping phức tạp hơn.

Nếu chỉ cần một vài field, DTO projection thường rõ ràng hơn và tránh đưa entity không đầy đủ vào persistence context.

## 11. Native query với Oracle SQL đặc thù

Native SQL hữu ích khi query cần tính năng Oracle mà JPQL không diễn tả trực tiếp.

### 11.1. Analytic function

Ví dụ xếp hạng đơn theo khách hàng:

~~~sql
SELECT order_id,
       customer_id,
       total_amount,
       ROW_NUMBER() OVER (
           PARTITION BY customer_id
           ORDER BY created_at DESC, order_id DESC
       ) AS rn
FROM orders;
~~~

Có thể dùng trong native repository query và map thành DTO. JPQL hỗ trợ một tập chức năng nhất định nhưng analytic function và cú pháp Oracle cụ thể thường cần native SQL hoặc provider extension.

### 11.2. Common Table Expression

~~~sql
WITH recent_orders AS (
    SELECT order_id,
           customer_id,
           created_at,
           total_amount
    FROM orders
    WHERE created_at >= :fromTime
)
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM recent_orders
GROUP BY customer_id;
~~~

CTE hữu ích cho query nhiều bước, recursive query hoặc phân tách logic. Hỗ trợ cú pháp và tối ưu phụ thuộc Oracle release.

### 11.3. Optimizer hint

~~~sql
SELECT /*+ INDEX(o IDX_ORDERS_CUSTOMER_CREATED) */
       o.order_id,
       o.created_at
FROM orders o
WHERE o.customer_id = :customerId;
~~~

Hint là chỉ dẫn cho optimizer, không phải bảo đảm plan sẽ theo đúng mong muốn. Dùng hint sau khi xem execution plan và đo workload; hint cũ có thể trở nên không phù hợp khi data distribution hoặc schema đổi.

### 11.4. JSON và các hàm Oracle

Native SQL có thể dùng JSON_VALUE, JSON_TABLE, JSON_EXISTS hoặc hàm Oracle khác tùy release. Cần kiểm tra datatype, JSON validation, index strategy và return type.

Đặt các query này trong repository/DAO riêng để phần service không phụ thuộc cú pháp SQL cụ thể.

## 12. Native DML và persistence context

Đây là một trong các ranh giới quan trọng nhất của ORM.

Hibernate theo dõi entity được load vào persistence context. Khi dùng entity setter, dirty checking biết entity đã thay đổi. Nhưng native SQL hoặc JPQL bulk DML chạy trực tiếp trong database và có thể không cập nhật các object entity đang nằm trong memory.

Ví dụ:

~~~java
OrderEntity order = entityManager.find(OrderEntity.class, orderId);

// Native SQL cập nhật status trong database.
entityManager.createNativeQuery(
    "update orders set status = 'CLOSED' where order_id = :id"
).setParameter("id", orderId)
 .executeUpdate();

// Object order có thể vẫn giữ status cũ trong persistence context.
~~~

Sau bulk/native DML, entity đã được load có thể stale. Khi đọc lại cùng entity trong cùng persistence context, JPA có thể trả object đang quản lý thay vì query lại database.

### 12.1. Flush trước native query khi cần

Nếu có thay đổi entity chưa flush, native query có thể cần nhìn thấy những thay đổi đó. Dùng:

~~~java
entityManager.flush();
~~~

Flush đẩy pending changes trong persistence context xuống database trong transaction hiện tại. Flush không đồng nghĩa commit.

Hibernate có query flush mode và synchronization behavior riêng cho native query. Để code rõ ràng, gọi flush có chủ đích khi native query phụ thuộc vào các thay đổi entity vừa thực hiện, và test với provider/version thực tế.

### 12.2. Clear sau native DML

Sau bulk update/delete có thể cần:

~~~java
entityManager.clear();
~~~

clear() detach tất cả managed entities khỏi persistence context. Các entity được query lại sẽ lấy trạng thái mới từ database.

Không gọi clear một cách tùy tiện nếu service còn cần thay đổi entity đang managed; các thay đổi chưa flush có thể bị mất khỏi context. Thứ tự thường là flush trước rồi clear sau bulk DML khi cần.

### 12.3. Refresh một entity

Nếu chỉ một entity bị thay đổi ngoài persistence context:

~~~java
entityManager.refresh(order);
~~~

refresh() reload state của entity từ database. Nó ghi đè trạng thái đang managed bằng dữ liệu hiện tại trong database; thay đổi chưa flush trên entity có thể bị mất.

Chỉ refresh khi muốn bỏ trạng thái local và lấy lại state database.

### 12.4. @Modifying và clearAutomatically

Spring Data JPA dùng @Modifying cho repository query update/delete:

~~~java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query(
    value = """
        update orders
           set status = :newStatus
         where customer_id = :customerId
           and status = :oldStatus
        """,
    nativeQuery = true
)
int bulkUpdateStatus(
    @Param("customerId") Long customerId,
    @Param("oldStatus") String oldStatus,
    @Param("newStatus") String newStatus
);
~~~

Cần gọi trong transaction phù hợp, ví dụ service có @Transactional. flushAutomatically đẩy thay đổi pending trước query; clearAutomatically detach context sau query. Hai cờ này có tác động rộng tới persistence context, nên chỉ bật khi caller hiểu entity managed sẽ bị ảnh hưởng.

Không dùng @Modifying cho SELECT query.

## 13. Transaction giữa JPA và JDBC

Một ứng dụng có thể dùng JPA repository và JdbcTemplate trong cùng service transaction nếu chúng dùng cùng DataSource và transaction manager phù hợp.

Ví dụ:

~~~java
@Service
public class OrderService {
    private final OrderRepository repository;
    private final JdbcTemplate jdbcTemplate;

    @Transactional
    public void closeOrder(long orderId) {
        OrderEntity order = repository.findById(orderId)
            .orElseThrow();

        // JPA managed change.
        order.setStatus("CLOSING");

        // Native procedure call through the same transaction-managed DataSource.
        jdbcTemplate.execute(
            "{ call ORDER_API.CLOSE_ORDER(?, ?) }",
            (CallableStatementCallback<String>) call -> {
                call.setLong(1, orderId);
                call.registerOutParameter(2, Types.VARCHAR);
                call.execute();
                return call.getString(2);
            }
        );

        // Transaction commits when the Spring method completes successfully.
    }
}
~~~

Ví dụ minh họa transaction boundary; không nên vừa cập nhật entity status vừa gọi procedure cũng cập nhật cùng row mà không xác định rõ thứ tự và kết quả mong muốn. Nếu procedure sửa row đã được load, entity có thể stale và cần refresh/clear.

### 13.1. Hai connection khác nhau có thể phá atomicity

Nếu JPA dùng DataSource A và JDBC tự mở connection từ DataSource B, hai thao tác có thể nằm trong hai transaction khác nhau.

Khi service rollback, transaction của connection thứ hai có thể đã commit hoặc không được rollback cùng transaction JPA.

Để cùng transaction:

- Cùng DataSource.
- Cùng transaction manager hoặc phối hợp transaction đúng cách.
- Không tự lấy connection ngoài Spring transaction.
- Không tự commit trong stored procedure.
- Không để JDBC code đóng connection do transaction manager sở hữu.

Nếu phải phối hợp nhiều resource manager/database, cần thiết kế distributed transaction hoặc pattern tích hợp phù hợp; @Transactional đơn giản không tự tạo atomicity xuyên mọi connection.

## 14. Bulk operation: ORM có giới hạn tự nhiên

JPA entity lifecycle theo dõi từng entity. Bulk operation có thể xử lý nhiều hàng nhanh hơn nhưng bypass lifecycle callbacks và dirty checking từng entity.

Ví dụ JPQL bulk update:

~~~java
@Modifying
@Query("""
    update OrderEntity o
       set o.status = :newStatus
     where o.createdAt < :cutoff
       and o.status = :oldStatus
    """)
int archiveOldOrders(
    @Param("cutoff") LocalDateTime cutoff,
    @Param("oldStatus") OrderStatus oldStatus,
    @Param("newStatus") OrderStatus newStatus
);
~~~

Bulk update:

- Không gọi setter trên từng entity.
- Không chạy entity lifecycle callback như cập nhật entity từng object.
- Không tự đồng bộ managed entity đang có.
- Có thể không áp dụng optimistic locking/version semantics như từng entity.
- Cần clear/refresh context khi phù hợp.

### 14.1. Native bulk DML

Native SQL có thể dùng Oracle feature, partition operation hoặc SQL tối ưu riêng. Tuy nhiên, persistence context và cache vẫn cần xử lý.

Nếu bulk DML cập nhật nhiều hàng, kiểm tra:

- Row count.
- Trigger side effect.
- Audit.
- Constraint.
- Version column.
- Lock contention.
- Redo/undo.
- Index maintenance.
- Cache invalidation.

### 14.2. Stored procedure bulk DML

Procedure có thể gom logic cập nhật trong database và giảm round trips. Nhưng nếu procedure cập nhật entity đã được load trong cùng persistence context, object Java vẫn có thể stale.

Sau procedure, flush trước khi gọi nếu procedure cần thấy pending entity changes; clear hoặc refresh sau nếu procedure thay đổi dữ liệu mà persistence context đang giữ.

## 15. Transaction isolation và locking

JPQL/native query có thể dùng pessimistic lock hoặc SQL locking. Cần hiểu database transaction semantics, không chỉ annotation.

Ví dụ JPA:

~~~java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select o from OrderEntity o where o.id = :id")
Optional<OrderEntity> findForUpdate(@Param("id") Long id);
~~~

Provider tạo SQL locking phù hợp dialect, thường tương đương SELECT FOR UPDATE trong Oracle.

Native SQL có thể ghi rõ:

~~~sql
SELECT order_id, status
FROM orders
WHERE order_id = :orderId
FOR UPDATE;
~~~

Khóa row giữ tới commit/rollback. Không giữ lock trong lúc gọi external API hoặc stream file lớn. Với SKIP LOCKED hoặc NOWAIT, cú pháp và behavior phụ thuộc Oracle và use case.

### 15.1. Optimistic locking

Entity có @Version:

~~~java
@Version
@Column(name = "VERSION_NO")
private Long version;
~~~

Hibernate dùng version để phát hiện lost update trong thao tác entity được quản lý.

Native SQL/procedure tự cập nhật bảng phải duy trì version column theo contract nếu ứng dụng dựa vào optimistic locking. Nếu procedure không tăng version, một transaction JPA khác có thể không phát hiện thay đổi ngoài dự kiến.

### 15.2. Lock timeout

Lock timeout có thể được đặt qua query hint/provider hoặc Oracle SQL tùy API. Đặt timeout hợp lý và xử lý exception. Không để session chờ lock vô hạn nếu nghiệp vụ cần phản hồi nhanh.

## 16. Mapping datatype Oracle sang Java

Native query và procedure thường làm lộ chi tiết datatype nhiều hơn JPQL.

| Oracle datatype | Java mapping thường gặp | Lưu ý |
|---|---|---|
| NUMBER | BigDecimal, Long, Integer | Chọn theo precision/scale và miền giá trị |
| VARCHAR2 | String | Độ dài và character semantics |
| DATE | LocalDateTime hoặc kiểu phù hợp mapping | Oracle DATE chứa cả giờ/phút/giây |
| TIMESTAMP | LocalDateTime | Không chứa timezone |
| TIMESTAMP WITH TIME ZONE | OffsetDateTime hoặc mapping provider phù hợp | Kiểm tra driver/provider |
| CLOB | Clob, String hoặc Reader | String không phù hợp cho LOB lớn |
| BLOB | Blob hoặc byte[] | byte[] có thể tốn heap |
| RAW | byte[] | Kích thước giới hạn theo datatype |
| REF CURSOR | ResultSet/DTO mapping | Provider/driver-specific |

Đừng map Oracle DATE sang LocalDate nếu cần giữ phần time-of-day. Đừng map NUMBER có scale tiền tệ sang double nếu cần độ chính xác thập phân; dùng BigDecimal.

### 16.1. Null và numeric conversion

JDBC getLong() trả 0 nếu SQL NULL; phải gọi wasNull() nếu cần phân biệt:

~~~java
long value = resultSet.getLong("COUNT_VALUE");
if (resultSet.wasNull()) {
    // Database value was NULL.
}
~~~

Với nullable numeric projection, có thể dùng getObject hoặc mapping DTO phù hợp.

### 16.2. Oracle DATE và timezone

Oracle DATE lưu ngày và thời gian tới giây nhưng không lưu timezone. TIMESTAMP cũng không có timezone. TIMESTAMP WITH TIME ZONE có thông tin timezone/offset.

Khi native query trả timestamp, xác định semantics timezone trước khi map sang Instant/OffsetDateTime/LocalDateTime. Tránh chuyển đổi ngầm theo timezone mặc định của JVM hoặc session.

## 17. Pagination và count query cho native SQL

Spring Data JPA hỗ trợ Pageable cho một số native query:

~~~java
@Query(
    value = """
        select order_id, customer_id, status, created_at
          from orders
         where status = :status
         order by created_at desc, order_id desc
        """,
    countQuery = """
        select count(*)
          from orders
         where status = :status
        """,
    nativeQuery = true
)
Page<Object[]> findByStatus(
    @Param("status") String status,
    Pageable pageable
);
~~~

Với native SQL phức tạp, cung cấp countQuery riêng vì provider không luôn suy ra count query đúng từ CTE, GROUP BY, DISTINCT hoặc analytic query.

### 17.1. Deterministic ordering

Pagination cần ORDER BY ổn định và unique tie-breaker. Nếu chỉ order theo CREATED_AT mà nhiều hàng cùng timestamp, các page có thể lặp hoặc bỏ sót hàng khi dữ liệu thay đổi.

Ví dụ:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

### 17.2. Deep offset

OFFSET lớn có thể khiến database đọc/bỏ qua nhiều hàng trước khi trả page. Với bảng lớn, cân nhắc keyset pagination:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = :customerId
  AND (
       created_at < :lastCreatedAt
       OR (created_at = :lastCreatedAt AND order_id < :lastOrderId)
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :pageSize ROWS ONLY;
~~~

Native SQL cho phép điều khiển query này rõ ràng. Bind values và null ordering phải được xử lý theo sort contract.

## 18. Security: bind values và dynamic SQL

Native query vẫn phải chống SQL injection. Dùng bind parameter cho dữ liệu:

~~~java
Query query = entityManager.createNativeQuery(
    "select order_id from orders where customer_id = :customerId"
);
query.setParameter("customerId", customerId);
~~~

Không nối chuỗi:

~~~java
String sql = "select * from orders where customer_id = " + userInput;
~~~

Bind variable không dùng để thay tên bảng, cột, sort direction hoặc SQL keyword. Nếu identifier cần dynamic, dùng whitelist phía server:

~~~java
String orderColumn = switch (sortKey) {
    case "created" -> "created_at";
    case "amount"  -> "total_amount";
    default -> throw new IllegalArgumentException("Unsupported sort key");
};
~~~

Sau đó chỉ ghép identifier đã được whitelist. Không dùng tên cột từ request trực tiếp.

### 18.1. Stored procedure không tự miễn SQL injection

Procedure có dynamic SQL cũng có thể bị injection:

~~~sql
l_sql := 'SELECT * FROM orders WHERE status = ''' || p_status || '''';
EXECUTE IMMEDIATE l_sql;
~~~

Dùng bind:

~~~sql
l_sql := 'SELECT * FROM orders WHERE status = :b1';
OPEN p_result FOR l_sql USING p_status;
~~~

Với dynamic identifier, dùng whitelist và DBMS_ASSERT phù hợp. DBMS_ASSERT không thay thế authorization.

### 18.2. Phân quyền theo package

Có thể cấp EXECUTE trên package và không cấp DML trực tiếp trên bảng. Điều này hữu ích nếu package là API nghiệp vụ có validation, audit và quyền owner tối thiểu.

Không cấp EXECUTE cho PUBLIC nếu không có yêu cầu. Review AUTHID DEFINER/CURRENT_USER và direct grants của package owner.

## 19. SQL logging và observability

Native query/procedure cần observability ở cả ứng dụng và database.

Ghi nhận:

- Repository/service operation.
- SQL_ID nếu có.
- Procedure/package name.
- Bind metadata đã lọc.
- Duration.
- Rows affected/returned.
- Oracle error code.
- Transaction outcome.
- Correlation ID.
- Connection pool wait.
- Timeout/retry.

Không log password, token, PII hoặc toàn bộ LOB/payload nhạy cảm.

### 19.1. Hibernate SQL logging

Có thể bật SQL logging trong môi trường phát triển:

~~~properties
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Tên logger bind parameter phụ thuộc Hibernate version. Bind logging có thể lộ dữ liệu nhạy cảm; không bật TRACE trong production nếu chưa có redaction và approval.

### 19.2. SQL_ID và execution plan

Khi query chậm, tìm SQL_ID trong V$SQL, xem child cursor, plan hash, elapsed, CPU, buffer gets và disk reads. Dùng DBMS_XPLAN.DISPLAY_CURSOR với runtime statistics khi đã thu thập.

Đừng chỉ tối ưu theo thời gian đo từ Java. Tách connection acquisition, SQL execution, fetch, mapping và serialization để xác định bottleneck.

## 20. Test stored procedure và native query

Test phải chạy trên Oracle version/driver tương thích với production, vì H2 hoặc mock không mô phỏng đầy đủ PL/SQL, REF CURSOR, Oracle datatype và optimizer behavior.

### 20.1. Integration test

Dùng Testcontainers Oracle nếu image/license/runtime phù hợp với tổ chức hoặc dùng Oracle test database được quản lý. Không giả định H2 có thể xác minh Oracle package.

Test:

- Package tồn tại và compile.
- User có EXECUTE đúng.
- IN/OUT parameter mapping.
- REF CURSOR mapping.
- Numeric/date/LOB datatype.
- Transaction commit/rollback.
- Native query alias và DTO mapping.
- Flush/clear behavior.
- Pessimistic lock và timeout.
- SQL injection defense.
- Pagination/count query.

### 20.2. Transaction rollback test

Ví dụ test Spring:

~~~java
@SpringBootTest
@Transactional
class OrderProcedureIntegrationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void procedureRunsWithinTransaction() {
        orderService.closeOrder(1001L);

        // Assert expected state using a fresh/cleared persistence context.
    }
}
~~~

Test @Transactional mặc định có thể rollback sau khi test kết thúc. Nhưng nếu procedure tự COMMIT, rollback của test không hoàn tác thay đổi đó. Đây là cách phát hiện contract transaction không phù hợp.

### 20.3. Test persistence context stale

1. Load entity bằng EntityManager.
2. Gọi native update hoặc stored procedure thay đổi cùng row.
3. Đọc lại entity trong cùng persistence context.
4. Quan sát trạng thái.
5. Dùng refresh hoặc clear rồi đọc lại.
6. Ghi rõ synchronization strategy trong service code.

Test này giúp tránh lỗi ứng dụng thấy trạng thái cũ sau procedure.

## 21. Version compatibility: Spring Boot, JPA và Oracle JDBC

Một ứng dụng cần tương thích các lớp:

- Spring Boot release.
- Spring Data JPA release.
- Hibernate ORM release.
- Jakarta Persistence hoặc javax.persistence.
- Oracle JDBC driver (ojdbc).
- Oracle Database release/RU.
- Oracle dialect/provider configuration.

Spring Boot 3 dùng Jakarta namespace cho JPA; Spring Boot 2 thường dùng javax namespace. Không copy annotation import từ project version khác mà không kiểm tra.

Oracle JDBC driver version phải tương thích JDK và database deployment. REF CURSOR, LOB, TIMESTAMP WITH TIME ZONE, array/struct, JSON và procedure parameter behavior có thể khác theo driver.

Không tự đặt dialect class cũ nếu Hibernate version đã cung cấp dialect phù hợp. Dùng cấu hình Spring Boot/Hibernate theo version được support và xác nhận SQL sinh ra trong integration test.

## 22. Runbook chẩn đoán lỗi procedure/native query

### Bước 1 — Xác định tầng lỗi

- Spring Data repository parsing.
- JPA provider parameter registration.
- JDBC call syntax.
- Oracle package/schema resolution.
- Database privilege.
- Datatype/parameter conversion.
- SQL execution/constraint.
- ResultSet/REF CURSOR mapping.
- Transaction/persistence context.

### Bước 2 — Xác nhận procedure contract

~~~sql
SELECT owner,
       object_name,
       procedure_name,
       object_type
FROM all_procedures
WHERE object_name = 'ORDER_API'
ORDER BY owner, procedure_name;
~~~

Xem argument metadata:

~~~sql
SELECT owner,
       package_name,
       object_name,
       argument_name,
       position,
       sequence,
       data_type,
       in_out,
       data_level
FROM all_arguments
WHERE package_name = 'ORDER_API'
  AND object_name = 'CLOSE_ORDER'
ORDER BY sequence;
~~~

ALL_ARGUMENTS có thể biểu diễn package procedure/function và overload; kiểm tra overload, position, datatype, IN_OUT và cursor type.

### Bước 3 — Kiểm tra quyền

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege
FROM all_tab_privs
WHERE table_name = 'ORDER_API'
ORDER BY grantee, privilege;
~~~

Đối chiếu schema thực thi, package owner, AUTHID và quyền trên bảng nền.

### Bước 4 — Xem error stack

Ghi SQLState, vendor error code, message và cause chain. Với Oracle, ORA-06550/PLS errors có thể là lỗi compile/call signature; ORA-01031 là thiếu quyền; ORA-01403 là no data found trong PL/SQL context; ORA-00904 có thể là tên column/alias sai.

Không chỉ ghi exception message ngoài cùng từ Spring. Giữ SQLException chain và Oracle error code.

### Bước 5 — Xác minh transaction và context

- Connection có cùng transaction manager không?
- Procedure có COMMIT không?
- Entity changes đã flush chưa?
- Persistence context có entity stale không?
- Native DML có clear/refresh sau đó không?
- Connection có được trả về pool với trạng thái sạch không?

## 23. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng native SQL cho mọi query | Mất lợi ích entity mapping và portability | JPQL cho query entity thông thường |
| Ép JPQL cho analytic/hint Oracle | Query khó đọc hoặc không biểu đạt được | Native SQL cô lập trong repository |
| Gọi procedure nhưng không hiểu OUT mapping | Giá trị trả về null/sai | Đăng ký mode/type/name/position rõ |
| Giả định REF CURSOR tự map thành entity | Mapping lỗi hoặc entity thiếu state | DTO/SqlResultSetMapping hoặc JDBC |
| Procedure tự COMMIT | Phá atomicity của Spring transaction | Để transaction owner quyết định |
| JPA và JDBC dùng hai connection | Rollback không đồng nhất | Cùng DataSource/transaction manager |
| Native DML nhưng không clear context | Entity managed bị stale | Flush/clear/refresh có chủ đích |
| clear trước khi flush | Mất pending entity changes | Flush trước nếu cần |
| Bulk DML kỳ vọng lifecycle callback | Callback/audit không chạy như entity update | Xử lý audit/side effect rõ ràng |
| Mapping NUMBER sang double | Sai số thập phân | BigDecimal |
| Mapping Oracle DATE thành LocalDate | Mất phần thời gian | LocalDateTime hoặc mapping phù hợp |
| Bind dynamic identifier | SQL không hợp lệ hoặc injection | Whitelist identifier |
| Dùng H2 test procedure Oracle | Test pass giả hoặc không chạy được | Oracle integration test |
| Bật bind logging production | Lộ dữ liệu nhạy cảm | Redaction và giới hạn logging |
| Không kiểm tra driver version | REF CURSOR/LOB/type behavior khác | Pin và test driver tương thích |

## 24. Checklist lựa chọn và triển khai

### Lựa chọn abstraction

- [ ] Query có thể biểu đạt rõ bằng JPQL/Criteria không?
- [ ] Có cần Oracle SQL feature, hint hoặc analytic function không?
- [ ] Logic có cần dùng chung qua nhiều client không?
- [ ] Stored procedure có lợi ích về bulk/privilege boundary không?
- [ ] Có yêu cầu portability giữa nhiều database không?
- [ ] Contract procedure và ownership được ghi rõ?

### Procedure

- [ ] Package/procedure signature được version control.
- [ ] IN/OUT/INOUT/REF CURSOR được khai báo đúng.
- [ ] EXECUTE grant tối thiểu.
- [ ] AUTHID và direct grants được review.
- [ ] Procedure không COMMIT ngoài contract.
- [ ] Error code và business result được định nghĩa.
- [ ] Test bằng Oracle database/driver thật.

### Native SQL

- [ ] Tất cả value dùng bind parameters.
- [ ] Identifier động dùng whitelist.
- [ ] Result mapping rõ ràng bằng projection/DTO.
- [ ] Count query và pagination được kiểm thử.
- [ ] SQL có deterministic ORDER BY nếu phân trang.
- [ ] Execution plan và index được đo.
- [ ] Native DML đồng bộ persistence context.

### Transaction và ORM state

- [ ] JPA và JDBC dùng cùng transaction context khi cần atomicity.
- [ ] Pending changes được flush trước query phụ thuộc chúng.
- [ ] clear/refresh được dùng đúng thời điểm.
- [ ] Procedure không commit bất ngờ.
- [ ] Optimistic version và lock semantics được duy trì.
- [ ] Connection trả về pool sau khi transaction/resource hoàn tất.

## 25. Ghi nhớ cốt lõi

- JPQL làm việc ở mức entity; native SQL làm việc trực tiếp với SQL/table; stored procedure gọi logic được đóng gói trong database.
- Dùng JPQL cho truy vấn entity thông thường; native SQL cho tính năng Oracle hoặc query cần kiểm soát SQL; procedure cho API database dùng chung, bulk operation hoặc logic cần nằm trong DB.
- Spring Data JPA @Procedure phù hợp procedure đơn giản; EntityManager StoredProcedureQuery linh hoạt hơn với IN/OUT/INOUT và REF CURSOR; JDBC CallableStatement phù hợp khi cần Oracle-specific control.
- Oracle package procedure cần EXECUTE privilege; package owner và AUTHID quyết định quyền runtime.
- Procedure không nên tự COMMIT nếu service cần atomic transaction với các thao tác JPA khác.
- REF CURSOR là kết quả cursor; mapping phụ thuộc JPA provider, Hibernate và Oracle JDBC driver; DTO thường phù hợp cho projection.
- Native query cần mapping rõ ràng; Object[] phụ thuộc thứ tự cột và dễ lỗi khi projection đổi.
- @SqlResultSetMapping hỗ trợ EntityResult và ConstructorResult cho kết quả native.
- Native DML và stored procedure có thể thay đổi database mà không cập nhật entity đang managed.
- Flush đẩy pending changes xuống database nhưng không commit; clear detach toàn bộ managed entities; refresh reload một entity và có thể bỏ thay đổi local chưa flush.
- Spring Data @Modifying có thể dùng flushAutomatically/clearAutomatically nhưng cần hiểu tác động persistence context.
- JPA và JdbcTemplate có thể cùng transaction nếu dùng cùng DataSource/transaction manager; connection độc lập có thể phá atomicity.
- Bulk DML không chạy entity lifecycle theo cách cập nhật từng entity; cần xem callback, audit, version và cache.
- Oracle NUMBER thường nên map BigDecimal khi cần độ chính xác; Oracle DATE chứa cả time-of-day; timezone datatype cần semantics rõ.
- Native SQL phải dùng bind parameter; identifier động phải whitelist; stored procedure dynamic SQL cũng có thể bị injection.
- Test procedure, REF CURSOR, datatype và SQL đặc thù trên Oracle version/driver thực tế; H2 không thay thế Oracle integration test.
- ORM là abstraction hữu ích nhưng không che giấu transaction, SQL execution, database privilege hoặc persistence-context lifecycle.

### Tài liệu Spring, JPA và Oracle nên đối chiếu

- [Spring Data JPA Reference — Stored Procedures](https://docs.spring.io/spring-data/jpa/reference/jpa/stored-procedures.html) — @Procedure, @NamedStoredProcedureQuery và OUT parameters.
- [Spring Data JPA Reference — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html) — @Query, native query, projections và modifying queries.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — StoredProcedureQuery, native SQL, result mappings, entity lifecycle và persistence context.
- [Hibernate ORM User Guide](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html) — Native SQL, stored procedures, flush modes, bulk operations and JDBC integration.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html) — @Transactional, transaction managers and JDBC/JPA integration.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — CallableStatement, REF CURSOR, Oracle JDBC datatypes and driver behavior.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/) — PL/SQL packages, procedure signatures and REF CURSOR.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/) — Oracle SQL syntax, analytic functions, row limiting and native features.

Spring Boot, Spring Data JPA, Hibernate, Jakarta Persistence and Oracle JDBC versions must be compatible. Verify imports (javax versus jakarta), procedure name/parameter binding, REF CURSOR support, native pagination and transaction behavior with the exact stack deployed; keep database-specific code behind a clear repository or adapter boundary.

