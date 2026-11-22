# Đọc nguyên nhân gốc từ provider và driver mà vẫn giữ ranh giới JPA

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** Lỗi và phục hồi

Một ứng dụng JPA có thể chỉ thực hiện một lời gọi đơn giản:

~~~java
entityManager.persist(product);
~~~

nhưng khi lưu dữ liệu, lỗi thực tế lại phát sinh ở nhiều tầng: **JPA**, **JPA provider** (ví dụ Hibernate), **JDBC driver**, **database** hoặc **transaction manager**. Lỗi đến application service đôi khi chỉ là **PersistenceException**, **RollbackException** hoặc exception do Spring dịch lại; thông tin như tên ràng buộc UNIQUE, mã **SQLState** hoặc mã lỗi vendor lại nằm sâu hơn trong chuỗi nguyên nhân.

Giả sử hai request cùng tạo Product với SKU **KB-001**. Database có ràng buộc UNIQUE và từ chối lần INSERT thứ hai:

~~~sql
CONSTRAINT uk_products_sku UNIQUE (sku)
~~~

Ứng dụng có thể nhìn thấy cấu trúc minh họa:

~~~text
Spring DataIntegrityViolationException          (nếu dùng Spring)
    └─ Hibernate ConstraintViolationException    (provider-specific)
          └─ PostgreSQL PSQLException             (JDBC driver)
                SQLState = 23505
                constraint = uk_products_sku
~~~

Trên một tổ hợp công nghệ khác, chuỗi exception, thứ tự wrapper và thông tin được expose **có thể khác**. Không được lập trình business service dựa trên việc luôn có đúng ba lớp với những tên class đó.

**Mục tiêu của bài** là học cách:
1. Tìm **nguyên nhân có ích** trong cause chain và JDBC exception chain;
2. Phân biệt **lỗi JPA chuẩn**, **lỗi của provider**, **lỗi driver/database** và lỗi validation;
3. Diễn giải **SQLState**, vendor error code, constraint name mà không nhầm chúng là hợp đồng portable của JPA;
4. Tổ chức phần đọc thông tin thấp tầng **bên trong infrastructure adapter**, không để domain/application phụ thuộc trực tiếp Hibernate hoặc PostgreSQL;
5. Phân loại lỗi đúng để **rollback**, **không retry sai**, xử lý concurrency và trả API response phù hợp;
6. Viết integration tests xác minh hành vi thật tại flush/commit thay vì đoán theo tên exception.

**Nguyên tắc cốt lõi:** *Đọc sâu để chẩn đoán; trả kết quả phân loại ổn định ở ranh giới ứng dụng.* Không cần che giấu hoàn toàn thông tin provider/driver, nhưng cũng không được để chi tiết vendor lan khắp business code.

## 1. Bức tranh từ một lệnh persist đến lỗi SQL

### 1.1. Các tầng thực hiện

~~~text
HTTP Controller / Message Consumer
            |
            v
Application Service
            |
            v
Repository / JPA EntityManager
            |
            v
Jakarta Persistence API
            |
            v
JPA Provider (Hibernate / EclipseLink / ...)
            |
            v
JDBC API + Database Driver
            |
            v
Database Engine
  (constraints, locks, transactions, SQL execution)
            |
            +-- Trả lỗi SQLState/vendor code/diagnostics
            |
            v
JDBC SQLException / driver-specific exception
            |
            v
Provider exception + cause chain
            |
            v
JPA PersistenceException / transaction rollback wrapper
            |
            v
Spring DataAccessException (nếu framework có translation)
            |
            v
Application error policy
            |
            v
API response / retry / monitoring
~~~

Một số lớp có thể vắng mặt hoặc có thứ tự khác. Jakarta Persistence không bắt buộc sử dụng Hibernate; Spring không bắt buộc hiện diện trong ứng dụng JPA thuần; JDBC lỗi không phải lúc nào cũng xảy ra vì Bean Validation hoặc JPA mapping có thể từ chối thao tác trước khi gửi SQL.

### 1.2. API chuẩn hóa hợp đồng gì?

**Jakarta Persistence** chuẩn hóa entity mapping, EntityManager, query APIs và nhiều loại exception/semantics ở mức JPA. Ví dụ:
- **jakarta.persistence.PersistenceException**;
- **jakarta.persistence.EntityExistsException**;
- **jakarta.persistence.OptimisticLockException**;
- **jakarta.persistence.PessimisticLockException**;
- **jakarta.persistence.LockTimeoutException**;
- **jakarta.persistence.QueryTimeoutException**;
- **jakarta.persistence.TransactionRequiredException**;
- **jakarta.persistence.RollbackException**;
- **jakarta.persistence.NoResultException**;
- **jakarta.persistence.NonUniqueResultException**.

JPA **không chuẩn hóa toàn bộ**:
- Tên class exception nội bộ Hibernate/EclipseLink;
- SQLState và vendor error code của mọi DB;
- Cách provider dịch SQLException;
- Nội dung tiếng Anh trong exception message;
- Tên constraint được đặt trong cause;
- Một chuỗi exception wrapper cố định;
- Việc một lỗi database sẽ xuất hiện chính xác ở dòng persist hay ở commit.

Do đó, hợp đồng JPA cần là lớp tham chiếu chính ở code dùng JPA; chi tiết sâu hơn là dữ liệu phục vụ **diagnostics và adapter-level classification**.

### 1.3. Tình huống UNIQUE cụ thể

Entity:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(
    name = "products",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_products_sku",
            columnNames = {"sku"}
        )
    }
)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 64)
    private String sku;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Product() {}

    public Product(String sku, BigDecimal price) {
        this.sku = sku;
        this.price = price;
    }
}
~~~

DDL PostgreSQL minh họa:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,

    CONSTRAINT uk_products_sku UNIQUE (sku)
);
~~~

Nếu database đã có SKU **KB-001**, transaction mới cố INSERT cùng SKU:

~~~sql
INSERT INTO products(sku, price)
VALUES ('KB-001', 100000.00);
~~~

thì PostgreSQL thường báo **SQLState 23505** (unique violation). JPA provider có thể chuyển lỗi thành một provider-specific constraint exception, rồi JPA/framework/transaction manager bọc hoặc dịch tiếp.

**Lưu ý:** Annotation @UniqueConstraint chỉ là metadata DDL. Tình huống trên đòi **schema thực tế** có UNIQUE constraint, không chỉ entity Java khai báo.

### 1.4. Không bắt đầu bằng “lỗi gì ở dòng em.persist?”

Với một ID generation strategy, em.persist có thể làm INSERT sớm; với strategy khác hoặc batching, SQL có thể bị trì hoãn đến **flush** hoặc **commit**. Điều tra phải theo dõi **thời điểm DML thực thi** và **transaction boundary**, không chỉ Java line có persist.

## 2. Ba câu hỏi khi đọc một exception

Khi nhận được Throwable từ thao tác lưu JPA, hỏi theo thứ tự:

1. **Lỗi được phân loại ở cấp JPA/framework thế nào?** Đây có phải optimistic conflict, lock acquisition failure, transaction required, missing result hay persistence failure?
2. **Nguyên nhân kỹ thuật sâu hơn là gì?** Có SQLException, SQLState, vendor code, constraint name, connection/timeout/deadlock diagnostics không?
3. **Ứng dụng nên làm gì?** Rollback? Bảo người dùng sửa input? Báo resource conflict? Retry có giới hạn trong transaction mới? Cảnh báo vận hành?

Không đi thẳng từ một raw SQL message sang HTTP status. Ví dụ cùng nhóm integrity error có thể là:
- Vi phạm UNIQUE do hai yêu cầu tạo SKU giống nhau → thường phù hợp với một business conflict;
- Vi phạm FOREIGN KEY do bug code ghi sai Category ID → có thể là lỗi nội bộ;
- Vi phạm NOT NULL do migration chưa đồng bộ DTO/entity/schema → có thể cần sửa deployment;
- Vi phạm CHECK vì người dùng gửi giá âm → thường là validation failure nếu dữ liệu đến từ client.

Cùng một **SQLState class** không tự xác định ai chịu trách nhiệm.

### 2.1. Exception là dữ liệu, không phải văn bản cho user

Không trả trực tiếp:

~~~text
ERROR: duplicate key value violates unique constraint
"uk_products_sku"
Detail: Key (sku)=(KB-001) already exists.
~~~

vì message có thể chứa dữ liệu nhạy cảm, tên bảng/cột nội bộ hoặc khác ngôn ngữ/driver.

Thay vào đó, map thành một response ổn định:

~~~json
{
  "code": "PRODUCT_SKU_ALREADY_EXISTS",
  "field": "sku",
  "message": "Mã sản phẩm đã được sử dụng."
}
~~~

Phần log vận hành có thể ghi **SQLState, vendorCode, constraintName, correlationId** được kiểm soát, không nhất thiết ghi mọi raw parameter.

### 2.2. Phân loại khác với che giấu

Giữ ranh giới JPA không có nghĩa bỏ qua nguyên nhân gốc. Một infrastructure adapter có thể biết Hibernate và PostgreSQL để chẩn đoán chính xác. Nhưng application service chỉ cần nhận lỗi đã phân loại như **DuplicateProductSku** hoặc **RetryableTransactionFailure**, thay vì trực tiếp import **org.postgresql.util.PSQLException**.

## 3. Exception chuẩn JPA cần nhận diện trước

Bảng sau nói về ý nghĩa thường gặp trong JPA; loại wrapper và timing cụ thể có thể khác provider hoặc transaction manager.

| Exception chuẩn JPA | Tình huống thường gặp | Hướng xử lý |
|---|---|---|
| PersistenceException | Lỗi persistence chung, có thể chứa cause sâu | Kiểm tra cause, rollback phù hợp |
| EntityExistsException | Entity cùng identity đã tồn tại hoặc phát hiện trùng | Không tự kết luận UNIQUE của một field |
| OptimisticLockException | Version/check optimistic không còn khớp | Rollback, reload/resolve, không retry snapshot cũ |
| PessimisticLockException | Không lấy được pessimistic lock, thất bại cấp transaction | Rollback, cân nhắc retry |
| LockTimeoutException | Lấy pessimistic lock thất bại nhưng provider xác định statement-level rollback | Xem DB state, thường rollback unit of work |
| QueryTimeoutException | Query vượt giới hạn, không nhất thiết do row lock | Điều tra timeout layers/SQL, rollback phù hợp |
| TransactionRequiredException | Gọi thao tác cần transaction khi không có transaction | Sửa transaction boundary |
| RollbackException | Commit thất bại hoặc transaction rollback, có thể bọc nguyên nhân | Đọc cause chain; không coi là một category nghiệp vụ |
| NoResultException | getSingleResult không tìm thấy kết quả | Thông thường không đánh dấu transaction rollback chỉ vì lỗi này |
| NonUniqueResultException | getSingleResult trả nhiều kết quả | Xem query/data contract; không tự coi là DB UNIQUE violation |

### 3.1. OptimisticLockException không phải SQL UNIQUE

~~~java
@Version
private Long version;
~~~

Khi A giữ version=4 nhưng database đã được B commit lên version=5, A có thể gặp **OptimisticLockException** ở merge/flush/commit. Đây là vấn đề **stale version**, không phải database UNIQUE constraint, kể cả khi bên dưới có một SQL UPDATE với affected row count=0.

Không map nó sang Product SKU trùng chỉ vì thông điệp có từ “constraint” ở một context khác.

### 3.2. LockTimeoutException khác PessimisticLockException

Theo JPA semantics, **LockTimeoutException** dùng khi provider xác định lỗi lock acquisition chỉ buộc rollback **statement**, còn **PessimisticLockException** là failure khiến transaction rollback/rollback-only.

Nhưng **JPA exception category không bảo đảm transaction của mọi database sau đó vẫn usable**. Ví dụ PostgreSQL thường đánh dấu transaction đang lỗi sau một statement error, trừ khi có savepoint/cơ chế phục hồi tương ứng. Trong service đơn giản, rollback toàn unit of work sau lock failure thường an toàn hơn cố ghi tiếp.

### 3.3. QueryTimeoutException không luôn chỉ ra khóa

Một câu SELECT mất thời gian vì sort, I/O, network hoặc chờ lock có thể dẫn đến timeout được báo qua provider. Chỉ tên QueryTimeoutException không cho biết nút thắt ở đâu. Cần metrics, SQLState/cause, DB wait diagnostics và timeout configurations.

### 3.4. NoResultException không nên bị đưa qua bộ phân loại SQL

~~~java
Product result = em.createQuery(
    "select p from Product p where p.sku = :sku",
    Product.class
)
.setParameter("sku", "MISSING")
.getSingleResult();
~~~

Khi không có row, đây là **kết quả của query API** với exception hợp lệ, không phải database connection failure. Xử lý ở repository/query boundary bằng Optional hoặc domain missing-resource policy. Không dò SQLState cho mọi NoResultException rồi ghi log ERROR.

### 3.5. RollbackException thường là wrapper, không phải root cause

~~~java
tx.commit();
~~~

có thể ném **RollbackException** khi commit thất bại; cause bên trong có thể là validation error, constraint error, optimistic conflict hoặc lỗi khác. Nếu chỉ log:

~~~text
RollbackException: Error while committing the transaction
~~~

thì mất thông tin cần để sửa lỗi. Hãy **đọc cause chain có kiểm soát**, nhưng tiếp tục giữ phân loại ổn định ở tầng ứng dụng.

## 4. Thời điểm phát sinh: persist, flush, commit

### 4.1. Trình tự cần hiểu

~~~text
em.persist(entity)
       |
       +-- Entity vào persistence context
       |   có thể INSERT sớm tùy ID strategy
       |
       v
em.flush()
       |
       +-- Dirty checking / SQL DML
       +-- Bean Validation callbacks nếu tích hợp
       +-- Database constraints/locks/concurrency
       |
       v
tx.commit()
       |
       +-- Có thể flush thêm
       +-- Database commit/deferred checks
       +-- Transaction manager quyết định thành công
~~~

Không nên khẳng định persist luôn không gửi SQL hoặc luôn gửi SQL; JPA provider/ID generation/batching có thể thay đổi timing.

### 4.2. Explicit flush giúp đặt điểm quan sát sớm

~~~java
@Transactional
public void createProduct(CreateProductRequest request) {
    Product product = new Product(
        request.sku(), request.price()
    );

    entityManager.persist(product);
    entityManager.flush();
}
~~~

Flush có thể khiến NOT NULL/UNIQUE/CHECK violations được phát hiện bên trong method thay vì sau khi method body return. Nhưng **flush không phải commit**. Có những lỗi chỉ phát hiện ở commit hoặc trong transaction manager; vì thế **không trả “đã lưu chắc chắn” chỉ vì flush thành công**.

### 4.3. Spring proxy commit sau thân method

Trong flow @Transactional thông thường:
1. Proxy mở transaction;
2. Gọi thân method service;
3. Thân method return;
4. Proxy flush/commit;
5. Nếu commit lỗi, exception có thể xuất hiện **ngoài try/catch trong method body**.

Điều này làm một số patterns bắt SQLException/PersistenceException quanh repository.save không bắt được lỗi cuối cùng. Đặt translation ở **transaction boundary thích hợp** hoặc tách trách nhiệm translation của repository/persistence và error handler ngoài cùng, sau khi hiểu khi nào wrapper được tạo.

### 4.4. Exception tại commit không phải một lỗi mới độc lập

Nếu Hibernate JDBC exception được bọc bởi RollbackException tại commit, **đừng log hai lần như hai sự cố độc lập**. Log theo correlation ID và lưu những thông tin liên quan đủ để nối nguyên nhân.

## 5. Cause chain: tìm tín hiệu có ích thay vì chỉ đọc getMessage

### 5.1. Throwable.getCause()

Java Throwable có thể chứa cause:

~~~java
Throwable cause = exception.getCause();
~~~

Cause cho biết exception cấp dưới đã dẫn đến exception hiện tại, nhưng **không có quy ước chung** rằng sau ba lần getCause sẽ tới SQLException hay luôn gặp provider-specific exception.

Ví dụ:

~~~text
RollbackException
    |
    +-- PersistenceException
            |
            +-- org.hibernate.exception.ConstraintViolationException
                    |
                    +-- java.sql.SQLException
~~~

Một lần khác có thể chỉ:

~~~text
jakarta.persistence.OptimisticLockException
    |
    +-- provider-specific stale-state exception
~~~

**Không có SQLException** vẫn có thể là lỗi persistence thật: Bean Validation, mapping, transaction required và optimistic lock failure có thể không đi qua JDBC SQLException như một cause hiển thị.

### 5.2. Root cause không luôn là tầng quyết định nghiệp vụ

Giả sử ngoại lệ sâu nhất là:

~~~text
java.net.SocketException: Connection reset
~~~

Trong khi wrapper phía trên là SQLException với **SQLState class 08**. Cả hai hữu ích; chỉ lấy “cause sâu nhất” có thể làm mất:
- SQLState ở SQLException giữa chuỗi;
- Constraint name trong Hibernate exception;
- Transaction outcome ở JPA RollbackException;
- Tên operation/repository trong wrapper phía trên.

Vì vậy nên thu thập **các tín hiệu từ nhiều tầng**, không chỉ trả một Throwable cuối cùng.

### 5.3. Không hard-code số lớp wrapper

Sai:

~~~java
SQLException sql =
    (SQLException) failure.getCause()
        .getCause().getCause();
~~~

Code này có thể ném **NullPointerException** hoặc **ClassCastException**, làm che mất lỗi gốc và phụ thuộc provider version.

Tốt hơn: duyệt một cách an toàn, có giới hạn và không giả định exception layout cố định.

### 5.4. Ngoài cause còn có SQLException.nextException

JDBC SQLException có:

~~~java
SQLException next = sqlException.getNextException();
~~~

JDBC driver có thể nối nhiều SQLExceptions qua **nextException**, ví dụ khi batch statements thất bại. **nextException không nhất thiết nằm trong Throwable.getCause() chain.**

Vì vậy chỉ viết:

~~~java
while (cause.getCause() != null) {
    cause = cause.getCause();
}
~~~

có thể bỏ sót SQLState quan trọng nằm trong JDBC **nextException**.

### 5.5. BatchUpdateException

Trong JDBC batching, có thể gặp:

~~~java
java.sql.BatchUpdateException
~~~

với:
- Update counts của các statements đã xử lý theo JDBC behavior;
- SQLExceptions bổ sung ở nextException chain;
- Vendor diagnostics cho một statement cụ thể.

**Không suy ra** mọi statement trước lỗi đã được commit. Chúng có thể đã thực thi trong transaction nhưng sẽ bị rollback sau đó; auto-commit, driver và DB behavior phải được xem xét. Nếu batch fail, rollback unit of work khi phù hợp rồi mới đánh giá kết quả.

### 5.6. Suppressed exceptions

Java cũng có **Throwable.getSuppressed()**, thường xuất hiện từ try-with-resources cleanup. Một suppressed exception có thể hữu ích để biết connection close/cleanup cũng thất bại; tuy nhiên không nên coi mọi suppressed exception là nguyên nhân chính của DML error.

Một diagnostics utility có thể duyệt cả cause/next/suppressed theo giới hạn bảo vệ, nhưng phải:
- Không lặp vô hạn;
- Không ghi log raw tất cả messages;
- Không để exception không đáng tin tạo danh sách vô hạn;
- Giữ thứ tự/quan hệ giữa các tín hiệu.

## 6. Utility portable để đọc SQLState và vendor code

Ta có thể xây một utility chỉ phụ thuộc **Java SE/JDBC**, không import Hibernate hay PostgreSQL. Đây là bước đầu giữ ranh giới tốt: phần generic scanner không cần biết provider.

### 6.1. DTO kết quả chẩn đoán

~~~java
package com.example.persistence.diagnostics;

public record SqlSignal(
    String sqlState,
    int vendorCode,
    String exceptionClass
) {}
~~~

Signal cố ý không chứa **raw SQL**, **parameter values** hoặc **exception message**. Những dữ liệu ấy có thể hữu ích trong môi trường debug được kiểm soát, nhưng không nên xuất thẳng trong application API/telemetry mặc định.

### 6.2. Duyệt cause + JDBC nextException

~~~java
package com.example.persistence.diagnostics;

import java.sql.SQLException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public final class SqlSignalScanner {

    private static final int MAX_VISITED = 64;

    private SqlSignalScanner() {}

    public static List<SqlSignal> scan(Throwable root) {
        if (root == null) {
            return List.of();
        }

        Deque<Throwable> pending = new ArrayDeque<>();
        Set<Throwable> seen = Collections.newSetFromMap(
            new IdentityHashMap<Throwable, Boolean>()
        );
        List<SqlSignal> signals = new ArrayList<>();

        pending.addLast(root);

        int visited = 0;
        while (!pending.isEmpty() && visited < MAX_VISITED) {
            Throwable current = pending.removeFirst();

            if (!seen.add(current)) {
                continue;
            }
            visited++;

            if (current instanceof SQLException sql) {
                signals.add(new SqlSignal(
                    sql.getSQLState(),
                    sql.getErrorCode(),
                    sql.getClass().getName()
                ));

                SQLException next = sql.getNextException();
                if (next != null) {
                    pending.addLast(next);
                }
            }

            Throwable cause = current.getCause();
            if (cause != null) {
                pending.addLast(cause);
            }
        }

        return List.copyOf(signals);
    }
}
~~~

Các điểm đáng chú ý:
- **IdentityHashMap-backed Set** phân biệt Throwable theo reference, tránh phụ thuộc equals/hashCode bất thường;
- **MAX_VISITED** giới hạn duyệt;
- **SQLException.getNextException()** được xét riêng;
- Cause có thể null;
- SQLState có thể null, vendorCode có thể 0;
- Không biến SQL messages thành response.

Utility này **không tự phân loại một lỗi thành retryable hay validation error**. Nó chỉ thu thập tín hiệu JDBC để adapter/cơ chế policy dùng tiếp.

### 6.3. Nếu muốn duyệt suppressed exceptions

Có thể bổ sung sau khi xử lý cause:

~~~java
for (Throwable suppressed : current.getSuppressed()) {
    if (suppressed != null) {
        pending.addLast(suppressed);
    }
}
~~~

Nhưng cần giữ giới hạn traversal, thứ tự nguồn và logging policy. Có thể để suppressed trong một kênh diagnostic riêng thay vì dùng nó để đưa ra quyết định business, vì suppressed thường là lỗi cleanup thứ cấp.

### 6.4. Không chọn “SQLState đầu tiên” một cách mù quáng

Một chuỗi có thể có SQLException bọc bên ngoài mang SQLState null, rồi nextException chứa SQLState cụ thể. Nếu chỉ lấy phần tử đầu tiên và kết luận generic database error, ta bỏ qua tín hiệu tốt hơn.

Cách dùng an toàn:
1. Thu thập tất cả signals trong giới hạn;
2. Ưu tiên SQLState có ý nghĩa phù hợp cùng evidence khác;
3. Phân loại theo **database dialect đang được cấu hình**;
4. Tránh kết luận business intent chỉ từ một mã lỗi không có context.

### 6.5. Không xem class name là mã lỗi nghiệp vụ

~~~java
signal.exceptionClass()
~~~

có ích để nhận diện driver trong diagnostics, nhưng không nên cho code nghiệp vụ so với string **org.postgresql.util.PSQLException** để quyết định “SKU trùng”. Điều đó gắn domain vào một vendor và bỏ qua các trường hợp exception translation khác.

## 7. SQLState, vendor error code và constraint name

### 7.1. SQLException.getSQLState()

JDBC cung cấp:

~~~java
String state = sqlException.getSQLState();
~~~

SQLState thường là chuỗi **năm ký tự** theo quy ước SQL/DBMS, ví dụ **23505** trên PostgreSQL cho unique violation. Hai ký tự đầu thường chỉ nhóm/class:

~~~text
23xxx → integrity constraint violation
40xxx → transaction rollback-related conditions
08xxx → connection exception
~~~

Nhưng **giải thích chi tiết từng code phụ thuộc database**, và không phải mọi driver luôn trả SQLState; có thể null.

### 7.2. SQLException.getErrorCode()

~~~java
int vendorCode = sqlException.getErrorCode();
~~~

Vendor code do driver/database cung cấp; ví dụ một mã số ở SQL Server/MySQL/Oracle không có nghĩa tương đương mã đó ở database khác.

Không dùng một bảng ánh xạ vendor code chung cho mọi DBMS.

### 7.3. Constraint name

Một lỗi UNIQUE/CHECK/FK đôi khi chứa tên constraint như **uk_products_sku**. Đây là tín hiệu tốt để quyết định error code cụ thể, vì SQLState **23505** có thể là trùng SKU, trùng email, trùng external reference hoặc constraint khác.

Nhưng constraint name:
- Không được JDBC chuẩn cung cấp qua một method SQLException portable chung;
- Có thể nằm trong provider exception, vendor-specific server error object hoặc message;
- Có thể null, đổi khi migration hoặc khác chữ hoa/chữ thường;
- Cần allowlist/trusted mapping trước khi đưa vào response;
- Không đảm bảo mọi driver expose nó.

### 7.4. Bảng mã PostgreSQL thường gặp

| SQLState | Ý nghĩa PostgreSQL thường gặp | Phản ứng ban đầu cần cân nhắc |
|---|---|---|
| 23505 | unique_violation | Phân biệt constraint nào, cân nhắc conflict |
| 23503 | foreign_key_violation | Kiểm tra reference/operation và API contract |
| 23502 | not_null_violation | Kiểm tra input, mapping, schema drift |
| 23514 | check_violation | Kiểm tra DB business invariant |
| 40001 | serialization_failure | Rollback, retry transaction mới nếu operation an toàn |
| 40P01 | deadlock_detected | Rollback, retry có giới hạn nếu phù hợp |
| 55P03 | lock_not_available | Lock contention/NOWAIT, xem retry policy |
| 57014 | query_canceled | Timeout hoặc cancel, điều tra nguồn |
| 08006 | connection_failure | Connection/DB availability, không đồng nhất với input error |

**Đây là ví dụ theo PostgreSQL**, không phải bảng “các mã chuẩn JPA”. Chúng giúp diagnostic và policy cho một dialect cụ thể, nhưng không quyết định HTTP status một cách máy móc.

### 7.5. Một số ví dụ vendor code khác

| Database | Ví dụ | Ý nghĩa thường gặp |
|---|---|---|
| MySQL | Error 1062 | Duplicate entry / unique constraint |
| SQL Server | Error 2627 hoặc 2601 | Vi phạm unique/duplicate key |
| Oracle | ORA-00001 (vendor code 1) | Unique constraint violated |
| PostgreSQL | SQLState 23505 | Unique violation |

Không giả định SQLState của MySQL/SQL Server/Oracle luôn có cùng mã chi tiết với PostgreSQL. Với các DB trên, cần tra driver/provider version thực tế và viết integration tests theo dialect.

### 7.6. SQLState class 23 chưa nói field nào sai

Nếu nhận:

~~~text
SQLState = 23505
~~~

ta có thể nghi unique constraint vi phạm trong PostgreSQL, nhưng để trả **PRODUCT_SKU_ALREADY_EXISTS**, cần xác nhận:
- Operation đang tạo/sửa Product;
- Constraint là **uk_products_sku** hoặc bằng chứng đáng tin tương đương;
- Database/schema đúng;
- Business mapping đang áp dụng.

Nếu không phân biệt được constraint, trả error category tổng quát hoặc log chẩn đoán để bổ sung mapping, **không đoán field sku**.

### 7.7. Đừng parse localized message làm giao thức chính

Sai:

~~~java
if (error.getMessage().contains("duplicate key")) {
    return "PRODUCT_SKU_ALREADY_EXISTS";
}
~~~

Message có thể đổi theo DBMS/version, locale, driver exception wrapping, provider translation, tên constraint/cột sau migration và batching.

Ưu tiên **structured codes và constraint metadata**, kèm test. Parse message chỉ có thể là fallback được giới hạn tại adapter cho vendor/version xác định và được giám sát, không phải hợp đồng core domain.

## 8. Provider-specific diagnostics: đọc Hibernate nhưng không để domain phụ thuộc

Hibernate là JPA provider phổ biến. Khi lỗi SQL, Hibernate có các lớp ngoại lệ riêng như:

~~~text
org.hibernate.JDBCException
org.hibernate.exception.ConstraintViolationException
org.hibernate.exception.LockAcquisitionException
org.hibernate.exception.JDBCConnectionException
org.hibernate.exception.SQLGrammarException
~~~

Những loại này giúp chẩn đoán, nhưng **không phải Jakarta Persistence API**. Một codebase đổi sang EclipseLink hoặc nâng cấp Hibernate có thể không còn cùng class/method/wrapper.

### 8.1. Hibernate ConstraintViolationException khác Bean Validation

Có **hai lớp có tên gần như giống nhau**:

~~~java
jakarta.validation.ConstraintViolationException
~~~

và:

~~~java
org.hibernate.exception.ConstraintViolationException
~~~

Bảng phân biệt:

| Exception | Thuộc tầng nào? | Nguồn lỗi |
|---|---|---|
| jakarta.validation.ConstraintViolationException | Jakarta Bean Validation | Object vi phạm @NotNull, @Size, @PositiveOrZero... khi validation chạy |
| org.hibernate.exception.ConstraintViolationException | Hibernate ORM | JDBC/database integrity constraint violation, ví dụ UNIQUE, FK, CHECK |
| java.sql.SQLException | JDBC driver/DB | SQLState, vendorCode, nextException |
| org.springframework.dao.DataIntegrityViolationException | Spring data access abstraction | Framework dịch lỗi integrity từ underlying persistence technology |

Đừng import nhầm Hibernate ORM ConstraintViolationException để xử lý một DTO @Valid invalid, hoặc nghĩ Jakarta Bean Validation exception luôn có SQLException cause.

### 8.2. Hibernate JDBCException cung cấp tín hiệu JDBC

Trong những phiên bản Hibernate có API phù hợp, Hibernate **JDBCException** cho phép truy cập:
- **getSQLException()**;
- **getSQLState()**;
- **getErrorCode()**;
- Có thể có thông tin SQL statement;
- Một số subclasses thêm constraint metadata.

Ví dụ code **chỉ dành cho Hibernate infrastructure adapter**:

~~~java
import org.hibernate.JDBCException;

public final class HibernateJdbcProbe {

    public static void inspect(JDBCException ex) {
        String sqlState = ex.getSQLState();
        int vendorCode = ex.getErrorCode();

        java.sql.SQLException jdbc = ex.getSQLException();

        // Chỉ đưa structured diagnostics vào logs.
        // Không gửi raw SQL/parameters cho client.
    }
}
~~~

Khi class này có vị trí trong một module **infrastructure-hibernate**, core domain và application services không cần biết Hibernate JDBCException là gì.

### 8.3. Đọc tên constraint từ Hibernate

Một adapter riêng có thể đọc:

~~~java
package com.example.infrastructure.hibernate;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Optional;
import java.util.Set;

public final class HibernateConstraintProbe {

    private HibernateConstraintProbe() {}

    public static Optional<String> findConstraintName(
            Throwable root) {

        Set<Throwable> visited =
            Collections.newSetFromMap(
                new IdentityHashMap<Throwable, Boolean>()
            );

        Throwable current = root;
        int steps = 0;

        while (current != null
                && steps++ < 64
                && visited.add(current)) {

            if (current instanceof
                    org.hibernate.exception.ConstraintViolationException ex) {
                return Optional.ofNullable(
                    ex.getConstraintName()
                );
            }

            current = current.getCause();
        }

        return Optional.empty();
    }
}
~~~

Hàm này dùng Hibernate-specific API. Nó có thể trả **Optional.empty()**, vì constraint name không luôn được provider/driver xác định. Đừng giả định một lần Hibernate ném integrity exception là chắc chắn có constraint name.

Đối với exception chains phức tạp có nextException hoặc nhiều branches, production adapter có thể cần bổ sung traversal tương tự SqlSignalScanner. Đoạn trên có mục tiêu tách ranh giới, không phải cam kết hỗ trợ mọi wrapper/cấu trúc exception của mọi phiên bản.

### 8.4. Không dùng EntityManager.unwrap để xử lý mọi lỗi

JPA cho phép:

~~~java
Session session = em.unwrap(Session.class);
~~~

khi dùng Hibernate Session API tương ứng. Nhưng unwrap:
- Là lối vào **provider-specific API**;
- Không phải yêu cầu để đọc Throwable.getCause();
- Không nên được gọi trên mọi repository chỉ để chuẩn bị diagnostics;
- Có thể làm code không còn portable sang JPA provider khác.

Giữ các khả năng này trong adapter khi thực sự cần một tính năng Hibernate-specific.

### 8.5. Lỗi SQLGrammarException không luôn là “ngữ pháp SQL sai”

Provider-specific **SQLGrammarException** có thể xuất hiện vì bảng/cột không tồn tại, sai schema, quyền, dialect hoặc SQL syntax tùy DB. Không dịch thẳng tên class thành thông điệp client “câu SQL không đúng cú pháp” nếu root cause là migration thiếu bảng.

Cần nhìn SQLState/vendor diagnostics cùng schema metadata và generated SQL.

### 8.6. Có thể phân loại theo API chuẩn trước

Một bộ phân loại ưu tiên semantics JPA:

~~~java
if (failure instanceof OptimisticLockException) {
    // Optimistic conflict.
}
~~~

rồi mới dùng Hibernate/SQLException khi cần chi tiết. Nhưng nếu OptimisticLockException bị bọc dưới RollbackException, cần duyệt cause chain để phát hiện, chứ không chỉ instanceof ở exception ngoài cùng.

### 8.7. Khi đổi Hibernate version

Một upgrade có thể thay:
- Exception conversion strategy;
- Cách unwrap exception;
- Tên hoặc package API provider-specific;
- Có/không có constraint name;
- Batch exception layout;
- Flush/commit timing.

Dùng integration tests để xác minh **public error categories**, không chỉ unit test mock một Hibernate exception constructor.

## 9. Spring Data JPA: exception translation thêm một lớp

Nếu ứng dụng dùng Spring Data JPA, framework có cơ chế **persistence exception translation** nhằm chuyển lỗi công nghệ dữ liệu thành **org.springframework.dao.DataAccessException** và subclasses.

### 9.1. Ví dụ hierarchy thường gặp

~~~text
DataAccessException
    |
    +-- DataIntegrityViolationException
    |      |
    |      +-- DuplicateKeyException (nếu được nhận diện)
    |
    +-- OptimisticLockingFailureException
    |      |
    |      +-- ObjectOptimisticLockingFailureException
    |
    +-- PessimisticLockingFailureException
    |
    +-- CannotAcquireLockException
    |
    +-- QueryTimeoutException
    |
    +-- DataAccessResourceFailureException
~~~

Đây là **minh họa phân loại Spring**, không phải tuyên bố mọi provider/driver mapping sẽ luôn ra đúng subclass. Tên **QueryTimeoutException** trong Spring và JPA có thể trùng simple class name nhưng thuộc package khác nhau.

### 9.2. @Repository và translation boundary

Spring có khả năng dịch exceptions ở beans được quản lý như repositories, tùy cơ chế enablement và exception translation post-processor/configuration.

~~~java
@Repository
public class JpaProductRepository {
    @PersistenceContext
    private EntityManager em;

    // ...
}
~~~

Nhưng một lỗi transaction xuất hiện khi proxy @Transactional **commit sau method body** có thể có wrapper/cách xử lý khác so với exception ném ngay trong repository method. Không dựa vào việc có @Repository để khẳng định mọi exception ở mọi vị trí đã được dịch thành cùng một DataAccessException.

### 9.3. Spring DataIntegrityViolationException

~~~java
import org.springframework.dao.DataIntegrityViolationException;
~~~

Nó có thể bao phủ:
- NOT NULL;
- CHECK;
- UNIQUE;
- FOREIGN KEY;
- Data integrity conditions khác được framework nhận diện.

Vì vậy code:

~~~java
catch (DataIntegrityViolationException ex) {
    throw new DuplicateSkuException();
}
~~~

là **quá rộng** nếu cùng thao tác có thể vi phạm CHECK, FK hoặc UNIQUE khác. Để trả DuplicateSku cần mapping đáng tin theo constraint/business context.

### 9.4. Spring ObjectOptimisticLockingFailureException

Một trường hợp Spring dịch lỗi stale @Version thành **ObjectOptimisticLockingFailureException**. Ở application boundary, điều quan trọng là **optimistic conflict** cần reload/resolve, không được retry vô điều kiện cùng detached source.

Không truy ngược SQLState để cố phân loại một optimistic failure nếu JPA/Spring đã cung cấp thông tin chính xác hơn.

### 9.5. Spring persistence exception không phải domain exception

**DataAccessException** là một abstraction Spring, không phải một domain contract bắt buộc.

Một application layer không muốn phụ thuộc Spring có thể nhận các exception ổn định của chính mình:

~~~java
public class DuplicateProductSku
        extends RuntimeException {

    public DuplicateProductSku(Throwable cause) {
        super("PRODUCT_SKU_ALREADY_EXISTS", cause);
    }
}
~~~

Giữ **cause** để infrastructure logging/diagnostics có thể truy vết, nhưng API response không tự serialize cause hoặc stack trace.

### 9.6. Tránh catch mọi RuntimeException rồi “dịch” thành DB lỗi

Sai:

~~~java
try {
    repository.save(product);
} catch (RuntimeException ex) {
    throw new DatabaseUnavailableException(ex);
}
~~~

Code sẽ map cả IllegalArgumentException do bug, NullPointerException và domain validation failure thành “database unavailable”. Nếu cần translation, nó phải dựa trên exception semantics/tín hiệu xác thực, phần còn lại **propagate như unexpected failure**.

## 10. Jakarta Bean Validation là một nhánh khác của cây lỗi

### 10.1. @NotNull trước DB

~~~java
@NotNull
@PositiveOrZero
private BigDecimal price;
~~~

Nếu Bean Validation được kích hoạt trong request DTO hoặc JPA lifecycle, giá âm có thể bị từ chối mà **chưa có SQL INSERT/UPDATE nào được gửi xuống database**.

Khi đó không nhất thiết có:
- SQLException;
- SQLState;
- Vendor error code;
- Database constraint name.

Đừng viết ErrorTranslator yêu cầu mọi failure phải có JDBC signal; nó cần xử lý **non-SQL failures**.

### 10.2. Chạy Validator.validate trả violations

~~~java
Set<ConstraintViolation<Product>> violations =
    validator.validate(product);
~~~

Lời gọi validate thông thường trả một tập violations. Application có thể ném **jakarta.validation.ConstraintViolationException** nếu quyết định coi violations là lỗi.

Đừng nhầm tập vi phạm của Jakarta Bean Validation với Hibernate ORM SQL constraint diagnostics.

### 10.3. Dữ liệu hợp lệ ở Java vẫn có thể vi phạm DB constraint

Hai request đều qua @NotBlank SKU, nhưng cùng SKU. Chúng có thể:
1. Đều validate thành công;
2. Đều kiểm tra SKU chưa tồn tại;
3. Cùng cố INSERT;
4. Một transaction được commit;
5. Transaction còn lại bị UNIQUE constraint từ chối.

Đây là **concurrency race** mà application validation/pre-check không giải quyết được. SQL UNIQUE và transaction conflict handling vẫn cần thiết.

### 10.4. Schema drift cũng tạo integrity errors

Entity có @Column(nullable=false) nhưng database schema chưa migration đúng có thể gây mismatch. Ngược lại DB có CHECK mới mà Java validator còn cho phép giá trị cũ sẽ làm SQL fail ở commit.

Trước khi map DB CHECK violation thành “user nhập sai”, phải xác định **Java/DB rule có đồng bộ không**.

### 10.5. Xử lý Bean Validation khác xử lý DB lỗi

| Nguồn | Tín hiệu chính | Policy thường phù hợp |
|---|---|---|
| Request DTO @Valid | Field violations có cấu trúc | 400/422 theo contract |
| Domain method | Domain-specific exception | Business error theo tình huống |
| JPA lifecycle Bean Validation | Jakarta ConstraintViolationException | Rollback và trả validation error nếu input-controlled |
| DB NOT NULL/CHECK | SQLState + constraint metadata | Phân loại input vs bug/schema drift |
| DB UNIQUE | SQLState + constraint | Business conflict nếu đúng business key |
| DB FK | SQLState + constraint | Missing reference/concurrency/bug tùy operation |

### 10.6. Không log toàn bộ giá trị field nhạy cảm

Bean Validation violation có thể chứa invalidValue, và SQL error detail có thể chứa key values. Dùng field names/errors đã lọc cho response, tránh log invalidValue thô của mật khẩu, token, số tài khoản hoặc thông tin cá nhân.

## 11. Thiết kế ranh giới: application hiểu loại lỗi, adapter hiểu driver

Một thiết kế theo hướng Ports & Adapters:

~~~text
              Domain / Application
                |
                | ProductRepository port
                v
         Persistence abstraction
                ^
                |
          Infrastructure adapter
          (JPA EntityManager)
                |
                +-- Jakarta Persistence exceptions
                +-- Hibernate diagnostics
                +-- JDBC SQLException
                +-- PostgreSQL SQLState/vendor diagnostics
                |
                v
           Failure translator
                |
                v
       Stable application failure categories
                |
                v
           API/error policy
~~~

Mục tiêu: **domain không import Hibernate hoặc PostgreSQL**, còn infrastructure vẫn được quyền đọc kỹ thuật sâu để quyết định loại lỗi có ý nghĩa.

### 11.1. Định nghĩa danh mục lỗi ổn định

Ví dụ:

~~~java
package com.example.application.errors;

public enum PersistenceProblem {
    DUPLICATE_PRODUCT_SKU,
    INTEGRITY_CONSTRAINT,
    OPTIMISTIC_CONFLICT,
    LOCK_CONTENTION,
    TRANSIENT_TRANSACTION,
    DATABASE_UNAVAILABLE,
    UNKNOWN_PERSISTENCE_FAILURE
}
~~~

Các enum này là contract **của ứng dụng**, không đồng nghĩa Jakarta Persistence exceptions và không bị buộc phải thay tên khi đổi Hibernate driver.

### 11.2. Không nhất thiết đưa SQLState lên application API

Một error result:

~~~java
package com.example.application.errors;

public record ClassifiedPersistenceFailure(
    PersistenceProblem problem,
    String diagnosticId
) {}
~~~

cho phép application quyết định hướng xử lý dựa trên **problem**; correlation/diagnosticId giúp tìm root cause trong logs.

Nếu application cần metadata để cân nhắc retry, có thể thêm **retryCategory** với ý nghĩa ổn định; đừng để service tự nhìn SQLState="40001" rồi retry một thao tác thanh toán không idempotent.

### 11.3. Dùng lỗi có cause khi cần stack trace

~~~java
public final class DuplicateProductSkuException
        extends RuntimeException {

    public DuplicateProductSkuException(Throwable cause) {
        super("PRODUCT_SKU_ALREADY_EXISTS", cause);
    }
}
~~~

Giữ cause hữu ích trong logging. Nhưng đừng tự động serialize **Throwable** trong HTTP response hoặc message bus.

### 11.4. Dịch lỗi tại một vị trí có kiểm soát

Có thể chọn:
- Một **repository JPA adapter** bọc những failures phát sinh bên trong persistence operation;
- Một **transaction boundary decorator** để thấy cả lỗi commit;
- Một **outer exception handler** phân loại và trả API response sau rollback;
- Kết hợp nhiều lớp với trách nhiệm rõ: adapter thu thập diagnostics, outer layer quyết định response.

Không nên tạo nhiều translators khác nhau ở controller, service, repository cùng dựa vào SQLState và trả những mã khác nhau.

### 11.5. Commit boundary khiến transaction-level translation quan trọng

Trong Spring, nếu @Transactional bao quanh service method, commit xảy ra ở proxy ngoài method. Một try/catch trong repository adapter chưa chắc nhìn thấy exception lúc commit.

Thiết kế có thể:
1. Dùng transaction orchestration phù hợp để ensure failure được phân loại ở nơi nó xuất hiện;
2. Cho framework exception translation xử lý khi phù hợp;
3. Dùng outer web/message boundary nhận propagated failure sau transaction;
4. Đặt diagnostics utility có thể đọc JPA/Spring/provider/SQLException cause chain mà không cần một wrapper cố định.

### 11.6. “Ranh giới JPA” không có nghĩa bỏ abstraction phía trên

Nếu business là “đăng ký SKU duy nhất”, service có thể chỉ gọi:

~~~java
productRepository.create(product);
~~~

Repository port có thể ném **DuplicateProductSkuException** khi bị constraint tương ứng. Code nghiệp vụ không cần biết **SQLState 23505**, **getConstraintName()** hay **SQLException.getNextException()**.

Nếu doanh nghiệp cần xử lý khác nhau giữa “SKU trùng” và “database mất kết nối”, adapter trả stable classification khác nhau. Giữ ranh giới là **dịch nghĩa có kiểm chứng**, không chỉ đổi tên exception một cách mù quáng.

## 12. Mẫu classifier trong infrastructure: minh họa theo PostgreSQL

Phần này ghép các nguyên tắc thành một ví dụ có thể triển khai. Mục tiêu **không phải** tạo một thư viện dịch mọi exception của mọi database, mà là minh họa cách chọn **signals thấp tầng** trong adapter và trả **category ổn định**.

### 12.1. Port cho việc đọc constraint name

Một interface nhỏ:

~~~java
package com.example.infrastructure.persistence;

import java.util.Optional;

public interface ConstraintNameProbe {
    Optional<String> find(Throwable failure);
}
~~~

Implementation Hibernate có thể gọi **HibernateConstraintProbe.findConstraintName(failure)** từ phần 8, còn provider khác có implementation khác hoặc trả empty.

**Interface này nằm ở persistence infrastructure**, không phải business domain. Domain không cần biết khái niệm constraint name vật lý.

### 12.2. Duyệt JPA exception types dù có wrapper

~~~java
package com.example.infrastructure.persistence;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public final class CauseTypes {

    private CauseTypes() {}

    public static boolean contains(
            Throwable root,
            Class<? extends Throwable> type) {

        Set<Throwable> seen = Collections.newSetFromMap(
            new IdentityHashMap<Throwable, Boolean>()
        );

        Throwable current = root;
        int steps = 0;

        while (current != null
                && steps++ < 64
                && seen.add(current)) {

            if (type.isInstance(current)) {
                return true;
            }

            current = current.getCause();
        }

        return false;
    }
}
~~~

Hàm này kiểm tra **getCause chain**, không xét SQLException.nextException như SqlSignalScanner. Với mục đích tìm một loại JPA exception trong wrapper thông thường, điều đó thường hợp lý; muốn bao phủ mọi graph phức tạp có thể dùng một utility traversal tổng quát có giới hạn.

### 12.3. Bộ phân loại lỗi PostgreSQL mẫu

~~~java
package com.example.infrastructure.persistence;

import com.example.application.errors.PersistenceProblem;
import com.example.persistence.diagnostics.SqlSignal;
import com.example.persistence.diagnostics.SqlSignalScanner;

import jakarta.persistence.LockTimeoutException;
import jakarta.persistence.OptimisticLockException;
import jakarta.persistence.PessimisticLockException;
import jakarta.persistence.QueryTimeoutException;

import java.util.List;
import java.util.Optional;

public final class PostgresPersistenceClassifier {

    private final ConstraintNameProbe constraintProbe;

    public PostgresPersistenceClassifier(
            ConstraintNameProbe constraintProbe) {
        this.constraintProbe = constraintProbe;
    }

    public PersistenceProblem classify(Throwable failure) {
        // JPA semantics có ý nghĩa hơn việc đoán từ SQLState.
        if (CauseTypes.contains(
                failure, OptimisticLockException.class)) {
            return PersistenceProblem.OPTIMISTIC_CONFLICT;
        }

        if (CauseTypes.contains(
                failure, PessimisticLockException.class)
                || CauseTypes.contains(
                    failure, LockTimeoutException.class)) {
            return PersistenceProblem.LOCK_CONTENTION;
        }

        List<SqlSignal> signals =
            SqlSignalScanner.scan(failure);

        Optional<String> constraint =
            constraintProbe.find(failure);

        boolean uniqueViolation = hasSqlState(
            signals, "23505"
        );

        if (uniqueViolation
                && constraint
                    .filter("uk_products_sku"::equals)
                    .isPresent()) {
            return PersistenceProblem.DUPLICATE_PRODUCT_SKU;
        }

        if (hasSqlState(signals, "23503")
                || hasSqlState(signals, "23502")
                || hasSqlState(signals, "23514")
                || uniqueViolation) {
            return PersistenceProblem.INTEGRITY_CONSTRAINT;
        }

        if (hasSqlState(signals, "40001")
                || hasSqlState(signals, "40P01")) {
            return PersistenceProblem.TRANSIENT_TRANSACTION;
        }

        if (hasSqlState(signals, "55P03")) {
            return PersistenceProblem.LOCK_CONTENTION;
        }

        if (signals.stream().anyMatch(s ->
                s.sqlState() != null
                && s.sqlState().startsWith("08"))) {
            return PersistenceProblem.DATABASE_UNAVAILABLE;
        }

        // Query timeout có thể không xuất hiện ở SQL signal.
        if (CauseTypes.contains(
                failure, QueryTimeoutException.class)) {
            return PersistenceProblem.TRANSIENT_TRANSACTION;
        }

        return PersistenceProblem.UNKNOWN_PERSISTENCE_FAILURE;
    }

    private static boolean hasSqlState(
            List<SqlSignal> signals,
            String expected) {

        return signals.stream()
            .anyMatch(s ->
                expected.equals(s.sqlState()));
    }
}
~~~

Đây là một **mẫu classifier với cơ sở dữ liệu PostgreSQL**, không phải phân loại nghiệp vụ tự động hoàn hảo. Một số điểm cần nhớ:

- **DUPLICATE_PRODUCT_SKU** chỉ được chọn khi vừa có SQLState 23505 vừa có tên constraint **uk_products_sku** được xác định đáng tin.
- Nếu thiếu constraint name, loại lỗi thành **INTEGRITY_CONSTRAINT**, không đoán SKU.
- **TRANSIENT_TRANSACTION** chỉ là **loại lỗi có thể cân nhắc retry**, không phải chỉ thị retry tự động.
- Query timeout được xếp vào nhóm cần đánh giá lại policy; ngoài đời có thể cần category riêng nếu contract API phân biệt timeout với serialization/deadlock.
- Database connection failure không bảo đảm transaction chưa commit.
- Nếu dùng MySQL/SQL Server/Oracle, phải có adapter khác thay vì tái sử dụng các mã PostgreSQL vô điều kiện.
- **Spring-translated exceptions** nếu không chứa JPA exception/SQLException sâu hơn có thể cần được kiểm tra trực tiếp ở adapter Spring.

### 12.4. SQLState 40 không có nghĩa mọi operation retry an toàn

Một lỗi **serialization_failure** hoặc **deadlock_detected** có thể khiến transaction cần chạy lại toàn bộ. Nhưng nếu transaction đã gọi external payment API hoặc gửi email trước commit, chạy lại toàn bộ operation có thể tạo side effects trùng.

Do đó code classifier **không được** viết:

~~~java
if (problem == TRANSIENT_TRANSACTION) {
    while (true) {
        service.executeAgain();
    }
}
~~~

Cần idempotency, retry budget, backoff và transaction boundary rõ ràng.

### 12.5. Spring adapter có thể bổ sung semantics Spring

Trong dự án Spring Data JPA, trước hoặc sau bước đọc JPA/SQL signals, adapter có thể nhận diện:

~~~java
org.springframework.orm.ObjectOptimisticLockingFailureException
~~~

hoặc các subclasses trong Spring DAO package tùy phiên bản. Chúng giúp phân loại khi underlying cause không còn được giữ theo cách kỳ vọng.

Nhưng **không chuyển mọi DataAccessException thành DATABASE_UNAVAILABLE**: unique constraint violation, optimistic conflict, deadlock và pool starvation có policy khác nhau.

### 12.6. Không dùng classifier chung làm thay transaction manager

Classifier cho biết **lỗi thuộc nhóm nào**. Nó không:
- Rollback transaction;
- Đánh dấu transaction rollback-only;
- Clear/close EntityManager;
- Reconcile external side effects;
- Bảo đảm idempotency;
- Xác định commit đã thành công hay chưa sau connection loss.

Những việc đó thuộc transaction/application workflow. Không gộp toàn bộ vào một catch block lớn và tự nhận là “đã recover”.

## 13. Transaction recovery: quan trọng hơn tên exception

Ngay cả khi chẩn đoán đúng root cause, hệ thống vẫn có thể hỏng nếu phục hồi sai transaction.

### 13.1. Sau PersistenceException có nên tiếp tục dùng EntityManager?

Một persistence failure tại flush/commit có thể khiến:
- Transaction bị đánh dấu rollback-only;
- DB transaction ở trạng thái aborted;
- Persistence context chứa managed state không còn đồng bộ với DB;
- SQL batching state chưa hoàn chỉnh;
- JDBC connection bị invalid.

Thực hành phổ biến và an toàn: **rollback unit of work bị lỗi**; sau đó tạo **transaction mới** và context phù hợp cho lần xử lý tiếp. Không gọi em.clear rồi cố cứu transaction lỗi mà chưa biết DB/session state.

### 13.2. Jakarta Persistence EntityTransaction mẫu

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product p = new Product(
        "KB-001",
        new BigDecimal("100000.00")
    );

    em.persist(p);
    em.flush();

    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) {
        try {
            tx.rollback();
        } catch (RuntimeException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
    }

    // Ở đây log theo policy hoặc rethrow
    // để outer boundary phân loại nguyên nhân.
    throw failure;
} finally {
    em.close();
}
~~~

Đoạn này dành cho **resource-local transactions**. Với JTA/Spring transaction management, không tự trộn em.getTransaction() với transaction do container/framework điều khiển. Hãy để transaction manager tương ứng chịu trách nhiệm rollback/cleanup.

### 13.3. Tại sao addSuppressed khi rollback cũng lỗi?

Nếu INSERT gây integrity violation, rồi rollback bị lỗi vì connection đã hỏng, việc chỉ ném rollbackFailure sẽ làm mất nguyên nhân ban đầu.

~~~java
failure.addSuppressed(rollbackFailure);
~~~

giữ nguyên exception chính và ghi nhận rollback failure thứ cấp. Diagnostics tool có thể xem suppressed exceptions khi cần.

### 13.4. Spring @Transactional và propagation

~~~java
@Transactional
public void createProduct(CreateProductRequest input) {
    // JPA writes ...
}
~~~

Trong Spring, runtime exception vượt qua transactional boundary thường khiến transaction rollback theo default rules. Nếu code **bắt rồi nuốt exception**:

~~~java
@Transactional
public void createProduct(CreateProductRequest input) {
    try {
        repository.save(...);
    } catch (DataIntegrityViolationException ex) {
        log.warn("Duplicate?", ex);
        // Không rethrow, vẫn tiếp tục xử lý?
    }
}
~~~

transaction có thể đã rollback-only hoặc DB connection không usable, và method vẫn cố return success. Không làm vậy. Nếu cần trả lỗi có kiểm soát, throw một domain/application exception phù hợp hoặc đánh dấu rollback-only theo transaction policy.

### 13.5. LockTimeoutException có ngoại lệ về rollback scope

JPA có semantics statement-level cho LockTimeoutException, nhưng một DB có thể abort transaction sau statement error. Dịch được loại exception không thay đổi trạng thái DB. Để service đáng tin, thường rollback toàn business transaction khi không lấy được khóa và quyết định retry trong **new transaction** nếu phù hợp.

### 13.6. Optimistic conflict không phải nơi để “tiếp tục flush”

Nếu A giữ Product version=4 và B đã commit version=5, A flush gặp OptimisticLockException. Không làm:

~~~java
catch (OptimisticLockException ex) {
    em.refresh(staleProduct);
    em.flush(); // Thử tiếp trong transaction lỗi.
}
~~~

Cần rollback, đọc current state trong transaction mới, kiểm tra intent và resolvability, rồi mới retry. Có những thay đổi không thể tự merge mà cần người dùng quyết định.

### 13.7. Commit thất bại do mất kết nối: outcome có thể chưa biết

Một tình huống đặc biệt nguy hiểm:
1. Ứng dụng gửi COMMIT;
2. Database đã commit thành công;
3. Kết nối đứt trước khi client nhận acknowledgment;
4. JPA/driver trả connection/transaction exception.

Caller không thể mặc định “đã có exception tức là DB chắc chắn chưa commit”. **Commit outcome có thể không xác định tại phía caller**.

Với giao dịch quan trọng:
- Sử dụng **idempotency key/request ID**;
- Có UNIQUE constraint bảo vệ request ID;
- Có khả năng **reconcile** trạng thái theo ID;
- Không tự gửi lại payment/transfer mà không kiểm tra;
- Cân nhắc transactional outbox cho side effects.

### 13.8. Rollback exception không phải bằng chứng commit không có hiệu lực

Ở những kịch bản mất kết nối trong quá trình commit, ngay cả cố rollback cũng có thể thất bại vì connection không còn. Ứng dụng cần **reconciliation protocol** thay vì tin rằng rollback call trả lỗi là DB chắc chắn đã rollback.

### 13.9. Retry phải nằm ngoài transaction lỗi

~~~text
Attempt #1
  open tx A
  execute business command
  → serialization failure
  rollback tx A

Backoff, retry budget
  |
  v
Attempt #2
  open NEW tx B
  reload current state
  reapply idempotent intent
  commit / rollback
~~~

**Không retry cùng EntityManager/transaction stale** bằng cách lặp lại repository.save trong catch block.

## 14. Phân loại retry theo loại sự cố

### 14.1. Không phải lỗi nào cũng retry được

| Loại lỗi | Retry tự động? | Vì sao |
|---|---|---|
| Duplicate Product SKU | Thường không, nếu client gửi lại cùng SKU | Dữ liệu/business conflict bền vững |
| NOT NULL/CHECK invalid input | Không | Input/rule phải sửa |
| FOREIGN KEY missing reference | Không mặc định | Có thể sai request hoặc race; cần kiểm tra |
| OptimisticLockException | Không retry nguyên snapshot cũ | Cần reload/resolve |
| Deadlock victim | Có thể, có giới hạn | Transaction bị chọn rollback do cạnh tranh |
| Serialization failure | Có thể, có giới hạn | Cần chạy lại toàn transaction |
| Lock wait timeout | Có thể, có giới hạn | Row đang bị giữ khóa; tránh retry storm |
| Query timeout do truy vấn tốn tài nguyên | Không mặc định | Retry có thể tăng tải |
| Connection failure trước khi bắt đầu transaction | Có thể tùy availability | Cần phân biệt với commit outcome unknown |
| Connection failure trong commit | Không blind retry | Có thể DB đã commit |
| Mapping/schema mismatch | Không | Cần sửa deploy/migration |
| Authorization/domain violation | Không | Không phải lỗi transient của DB |

### 14.2. Retry count và backoff

Một chính sách thực tế có thể là:
- Tối đa 2–3 attempts cho một thao tác nhỏ và idempotent;
- Backoff có jitter;
- Không giữ transaction mở trong lúc backoff;
- Đọc lại dữ liệu hiện tại trong attempt mới;
- Dừng nếu deadline request/transaction không còn đủ;
- Metrics số retries và nguyên nhân;
- Không retry lỗi thuộc nhóm permanent integrity/validation.

Con số là ví dụ thiết kế, không phải quy định chung của Jakarta Persistence.

### 14.3. Deadlock khác lock timeout

Deadlock:

~~~text
Tx A giữ Row#1, chờ Row#2
Tx B giữ Row#2, chờ Row#1
           → wait-for cycle
~~~

Database có thể chủ động chọn victim. Lock timeout chỉ nói không lấy được khóa trong thời gian chờ; cả hai có thể dẫn đến retryable transaction failure, nhưng root cause và cách tối ưu khác. Thứ tự lấy khóa nhất quán và transaction ngắn có thể giúp giảm deadlocks.

### 14.4. Serialization failure cần chạy lại toàn bộ decision

Nếu một transaction:
1. Đọc stock;
2. Kiểm tra stock đủ;
3. Ghi reservation;
4. Trừ stock;

sau serialization failure, không chỉ chạy lại câu UPDATE cuối. Phải **đọc lại current data và quyết định lại business rule** trong transaction mới.

### 14.5. Idempotency trong request có side effects

Nếu caller gửi order request hai lần vì response timeout, service phải có contract để phát hiện cùng một request đã xử lý. Một request_id UNIQUE hoặc business key phù hợp giúp trả kết quả đã tồn tại thay vì tạo giao dịch trùng.

**Đọc đúng SQLState chưa đủ bảo đảm exactly-once behavior.**

## 15. Các tình huống lỗi thực tế và cách lần theo nguyên nhân

### 15.1. SKU trùng do UNIQUE

**Bối cảnh:** Client tạo Product với sku="KB-001", DB đã có cùng SKU.

~~~sql
INSERT INTO products (sku, price)
VALUES ('KB-001', 100000.00);
~~~

PostgreSQL thường báo **23505**. Adapter cần xác nhận **uk_products_sku**, sau đó có thể dịch thành **DUPLICATE_PRODUCT_SKU**. Không retry cùng dữ liệu như một lỗi tạm thời.

Điều cần kiểm tra:
- Constraint UNIQUE có thật trong schema không;
- Có trùng theo tenant, case folding/collation, normalization hay không;
- Các transactions có chạy song song khiến pre-check sai không;
- Client đã gửi idempotency key hay chưa;
- Constraint name có đúng sau migrations không.

### 15.2. FOREIGN KEY vi phạm khi xóa parent

**Bối cảnh:** Một Customer còn PurchaseOrders; service cố DELETE customer. DB FK với ON DELETE RESTRICT/NO ACTION từ chối.

PostgreSQL thường có SQLState **23503**, nhưng policy không tự động là “không tìm thấy customer”:
- Parent có thể tồn tại;
- Child references đang ngăn xóa;
- Nghiệp vụ cần cấm xóa khách hàng còn đơn;
- Hoặc cần soft delete/archival.

Adapter nên xem FK constraint name; application có thể trả conflict theo business rule. Không retry vô hạn.

### 15.3. CHECK(price >= 0) bị vi phạm

**Bối cảnh:** ETL hoặc đường code sai ghi price=-100.

~~~sql
UPDATE products
SET price = -100
WHERE id = 42;
~~~

PostgreSQL có thể trả **23514**. Cần phân biệt:
- Input từ user không hợp lệ;
- Domain validation bị bỏ qua;
- Mapping/DDL rule không đồng nhất;
- External data import sai;
- Rule vừa được sửa nhưng Java cũ vẫn gửi giá cũ.

Nếu source là người dùng, trả validation error phù hợp; nếu source là ETL nội bộ, đưa dữ liệu vào quarantine/repair thay vì đổ trách nhiệm cho client.

### 15.4. NOT NULL do schema drift

**Bối cảnh:** DB bổ sung NOT NULL cho order_status; ứng dụng cũ vẫn gửi NULL.

PostgreSQL có thể trả **23502**. Đây có thể là lỗi rollout schema/app, không phải validation mà client có thể tự sửa. Cần xem:
- Migration đã được áp chưa;
- DTO có bắt buộc field chưa;
- JPA @Column(nullable) có khớp schema không;
- Default/insertable behavior;
- Old application versions vẫn hoạt động không.

Không map mọi 23502 thành HTTP 400 nếu nguyên nhân là application mapping sai.

### 15.5. OptimisticLockException khi cập nhật từ form cũ

A load Product version=8; B commit version=9; A save bản version=8.

Có thể thấy **OptimisticLockException** hoặc Spring translation tương ứng, đôi khi bị bọc ở commit. Phản hồi phù hợp cần cho client biết bản sửa đổi đã lỗi thời, giữ draft và cung cấp workflow reload/diff/resolve. **Không tự retry detached snapshot version=8** vì có thể ghi đè thay đổi của B.

### 15.6. Pessimistic lock timeout

A giữ PESSIMISTIC_WRITE trên Product#42; B yêu cầu lock với timeout ngắn rồi thất bại. Có thể gặp **LockTimeoutException**, **PessimisticLockException**, hoặc DB/vendor-specific cause.

Điều cần đo:
- B thật sự chờ row lock hay chờ connection pool?
- Timeout là lock, query hay transaction timeout?
- DB/vendor exception có SQLState gì?
- Transaction B cần rollback không?
- Retry budget và business SLA có cho phép thử lại không?

### 15.7. Serialization failure

Một database chạy isolation mạnh có thể từ chối một giao dịch do xung đột serializability. PostgreSQL dùng SQLState **40001**. Service phải rollback rồi, khi phù hợp, **chạy lại toàn transaction** trong một unit of work mới.

Không chỉ chạy lại SQL UPDATE cuối cùng trong cùng transaction. Cần recompute business decision dựa trên state mới.

### 15.8. Deadlock victim

Hai transactions khóa hai rows ngược thứ tự:

~~~text
Tx A: lock Account#1 → chờ Account#2
Tx B: lock Account#2 → chờ Account#1
~~~

PostgreSQL thường trả **40P01** cho deadlock_detected. Giải pháp không chỉ retry:
- Lock rows theo thứ tự nhất quán;
- Thu ngắn transaction;
- Giảm lock scope;
- Monitor deadlock rate;
- Retry ngắn có jitter và idempotency.

### 15.9. SQL grammar hoặc schema mismatch

Provider báo lỗi SQLGrammarException; underlying DB nói relation "sales.purchase_orders" does not exist.

Nguyên nhân có thể:
- @Table(schema/name) sai;
- Migration chưa tạo table;
- Default schema/search_path sai;
- Role không có quyền;
- Quoted identifier case mismatch;
- Dialect hoặc native SQL dùng cú pháp sai.

Không retry như transient lock conflict. Cần sửa mapping/DDL/privileges/deploy.

### 15.10. Query bị cancel

PostgreSQL SQLState **57014** thường liên quan **query_canceled**, có thể do statement timeout, admin cancel hoặc nguyên nhân cancel khác. Cần xem DB diagnostics, query timeout settings và request cancellation flow, không cứ trả “database unavailable”.

Nếu query thường xuyên timeout do thiếu index, retry tự động có thể tăng tải.

### 15.11. JDBC connection failure

SQLException có SQLState class **08** hoặc vendor network errors; JDBC pool/DB bị ngắt.

Cần xác định thất bại xảy ra:
- Trước khi bắt đầu transaction;
- Giữa một query;
- Trong flush;
- Trong commit.

Đặc biệt, **connection lost around commit** có thể để lại trạng thái commit chưa biết ở phía caller; dùng idempotency/reconciliation, không mặc định rollback hoặc retry an toàn.

### 15.12. Lỗi ở connection pool, chưa có SQLState

HikariCP hoặc pool khác không cấp được connection trong deadline. Không phải mọi lỗi pool đều chứa SQLException với mã SQLState có ích; request có thể chưa gửi một câu SQL nào.

Metrics cần xem:
- Pool active/idle/pending;
- Connection acquisition time;
- Transactions giữ connections quá lâu;
- Connection leaks;
- DB max connections;
- Timeout của pool so với query/lock.

Không cố chỉnh @QueryHint lock.timeout để sửa một lỗi chờ connection.

### 15.13. JDBC batch INSERT bị lỗi

Một batch 100 Products có 1 SKU trùng:
- Provider có thể ném BatchUpdateException;
- SQLState chính xác có thể nằm trong nextException;
- Một số statements có update counts;
- Transaction có thể rollback toàn bộ hoặc ứng dụng đang ở cấu hình khác.

**Không báo “99 sản phẩm đã được lưu thành công” nếu transaction bị rollback** chỉ vì batch update counts cho biết các statements khác từng được thực thi.

### 15.14. Bean Validation fail trước SQL

Một Product có price=-1 và @PositiveOrZero được validate:
- Có thể có Jakarta ConstraintViolationException;
- Có thể không có SQLException;
- SQLState scanner có thể trả list rỗng;
- Application nên trả validation error theo field.

Không log “unknown JDBC error” chỉ vì không có SQLState.

### 15.15. Có lỗi khi đóng tài nguyên

try-with-resources đang xử lý SQLException chính, nhưng connection.close cũng lỗi và xuất hiện trong **suppressed exceptions**. Cần giữ nguyên cause chính, xem suppressed trong diagnostics. Đừng ghi đè sự cố gốc bằng lỗi cleanup hoặc để logging che mất exception ban đầu.

## 16. Ánh xạ lỗi tới API và message consumers

### 16.1. Error category không đồng nghĩa HTTP status

Một category như **INTEGRITY_CONSTRAINT** cần **business context** trước khi chọn response.

| Category/context | Response có thể phù hợp | Ghi chú |
|---|---|---|
| DTO field invalid | 400 hoặc 422 | Theo API contract |
| Product SKU thực sự trùng | 409 | Conflict trên business key |
| Optimistic version conflict | 409 | Cần resolve/reload |
| If-Match precondition không thỏa | 412 | HTTP precondition semantics |
| Foreign key chặn thao tác xóa | 409 | Nếu là business conflict rõ |
| Resource không tồn tại | 404 | Không tự suy từ generic FK violation |
| Lock contention tạm thời | 409/423/503 theo contract | Không có mapping JPA→HTTP bắt buộc |
| DB unavailable | 503 trong một số thiết kế | Retry-After chỉ khi có cơ sở |
| Unexpected schema/mapping failure | 500 | Server defect; log diagnostics |
| Authorization failure | 403/404 theo security policy | Không suy từ SQL error |
| Unknown commit outcome | Response có thể phải tra cứu trạng thái | Không nói chắc request thất bại |

**Đây là lựa chọn thiết kế API**, không phải quy tắc bắt buộc từ Jakarta Persistence. Việc trả 423 Locked thuộc semantics HTTP và contract cụ thể, không phải mọi LockTimeoutException mặc định thành 423.

### 16.2. Message consumer: retry, DLQ, quarantine

Một consumer nhập dữ liệu từ queue gặp CHECK constraint:
- Nếu payload vĩnh viễn sai, retry vô hạn chỉ làm tắc queue;
- Nếu schema deploy chưa đồng bộ, có thể cần dừng pipeline và báo incident;
- Nếu deadlock, có thể retry message trong transaction mới;
- Nếu commit outcome unknown, cần idempotency/reconciliation trước khi gửi lại.

Bộ phân loại nên hỗ trợ **permanent / transient / unknown outcome** nhưng quyết định ack/nack/dead-letter do message-processing policy điều khiển.

### 16.3. Trả về mã lỗi ổn định

Một response API:

~~~json
{
  "code": "PRODUCT_SKU_ALREADY_EXISTS",
  "message": "Mã sản phẩm đã được sử dụng.",
  "requestId": "req-7f4c"
}
~~~

Có thể thêm field path với data validation error khi phù hợp. Tránh trường **sqlState**, **vendorCode**, **rawSql**, **stackTrace** trong public response.

### 16.4. Dữ liệu nhạy cảm trong unique constraints

Một unique constraint cho email, phone number hoặc account number có thể xuất hiện nguyên giá trị trong DB error detail. Không log trực tiếp exception.toString nếu hệ thống không có bảo vệ, vì driver có thể đưa key values vào message.

Ngay cả constraint name cũng có thể tiết lộ schema. Giữ nó trong internal structured logs với quyền truy cập tương ứng; gửi client **error code đã duyệt**.

### 16.5. Tránh lộ sự tồn tại tài nguyên

Khi người dùng không có quyền trên một Product, không trả chi tiết “SKU này đã tồn tại trong tenant khác” chỉ vì database UNIQUE error. Security policy có thể yêu cầu response chung hoặc kiểm tra authorization trước khi tiết lộ business existence.

### 16.6. Không swallow exception để trả success

Sai:

~~~java
try {
    productRepository.create(product);
} catch (RuntimeException ex) {
    log.warn("Save failed: {}", ex.toString());
}
return success();
~~~

Nếu persistence fail, transaction có thể rollback nhưng API lại trả success. Cần propagate/translate theo contract và chỉ xác nhận kết quả sau transaction commit thực sự thành công.

## 17. Structured logging, tracing và observability

### 17.1. Log một event hữu ích thay vì toàn bộ SQL payload

Một log nội bộ có thể chứa:

~~~text
event=persistence_write_failure
operation=product.create
category=INTEGRITY_CONSTRAINT
sql_state=23505
vendor_code=0
constraint=uk_products_sku
provider=Hibernate
database=PostgreSQL
request_id=req-7f4c
transaction_outcome=rolled_back
~~~

Chỉ ghi những trường đã được xác minh. Ví dụ trên là **một event minh họa**, không phải mặc định vendorCode=0 trong mọi PostgreSQL driver.

### 17.2. Ghi những gì có thể kiểm chứng

- Operation name;
- Stable error category;
- Correlation/request ID;
- Persistence unit/datasource identifier không nhạy cảm;
- Provider/driver/DB version khi phù hợp;
- SQLState/vendorCode;
- Constraint name nếu trusted/available;
- Retry attempt;
- Transaction outcome (COMMITTED, ROLLED_BACK, UNKNOWN khi xác định được);
- Latency, timeout budget;
- Span trace ID.

Không ghi **transaction_outcome=rolled_back** nếu rollback call thất bại hoặc connection lost làm outcome chưa biết.

### 17.3. Ghi log một lần ở boundary có ownership

Nếu repository log ERROR, service log ERROR, controller advice log ERROR, cùng một request có thể sinh ba alerts. Thông thường:
- Infrastructure thu thập diagnostics;
- Outer boundary chịu trách nhiệm ghi sự cố với correlation;
- Internal helper chỉ log debug khi cần hoặc không log thêm.

Dùng một nơi có ownership để giảm duplicate alerts, nhưng vẫn giữ exception cause.

### 17.4. Phân loại metrics

| Metric | Ý nghĩa |
|---|---|
| persistence_error_total{category} | Tỷ lệ lỗi phân loại |
| sql_state_total{state_class} | Nhóm lỗi SQLState, tránh quá nhiều labels |
| optimistic_conflict_total | Tần suất stale writes |
| constraint_violation_total{constraint_code} | Nhóm constraints đã allowlist |
| transaction_retry_total | Số lần chạy lại |
| transaction_rollback_total | Lỗi business/DB cần rollback |
| connection_acquisition_timeout_total | Pool starvation |
| query_timeout_total | Query quá chậm/canceled |
| deadlock_total | DB lock scheduling issue |
| commit_outcome_unknown_total | Trường hợp cần reconciliation |

Cần giới hạn **cardinality** của labels: đừng gắn raw SQL, productId, email hay exception message vào metrics labels.

### 17.5. Correlation từ HTTP tới DB

Trace một Product create:
1. HTTP request có requestId;
2. Service span có operation product.create;
3. Repository/JPA span;
4. Database statement/span;
5. Failure classification event;
6. Transaction rollback/commit outcome;
7. API response code.

Nếu dùng OpenTelemetry, tránh ghi statement parameters nhạy cảm trong attributes. Việc truy vết cần tuân thủ privacy/security policy của hệ thống.

### 17.6. SQL logs chỉ bật theo nhu cầu

Hibernate có SQL loggers và JDBC proxy/driver diagnostics, tên logger có thể đổi theo phiên bản. Trong môi trường test có thể bật để hiểu generated SQL; production nên kiểm soát:
- Level;
- Sampling;
- Parameter redaction;
- Retention/access;
- Logging overhead;
- Error message chứa values.

### 17.7. Một lỗi hiếm cần lưu context đủ để tái hiện

Với intermittent deadlock hoặc unique race, log chỉ “PersistenceException” không đủ. Nên ghi:
- Operation type;
- Transaction attempt;
- Constraint category;
- Lock order hoặc contention metrics nếu có;
- SQLState/vendor code;
- Correlation ID;
- Code release/database migration version.

Nhưng **không cần lưu toàn bộ Java entity hoặc raw request** nếu chứa dữ liệu nhạy cảm.

## 18. Kiểm thử utility đọc nguyên nhân gốc

Unit tests cho utility đọc exceptions có thể chạy **không cần database**. Chúng bảo đảm code đọc cause/nextException không phụ thuộc một số lượng wrappers cố định.

### 18.1. Test SQLException nằm dưới nhiều wrappers

~~~java
import jakarta.persistence.PersistenceException;
import org.junit.jupiter.api.Test;

import java.sql.SQLException;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class SqlSignalScannerTest {

    @Test
    void findsSQLExceptionThroughCauseChain() {
        SQLException sql = new SQLException(
            "duplicate",
            "23505",
            0
        );

        RuntimeException provider =
            new RuntimeException("provider", sql);

        PersistenceException jpa =
            new PersistenceException("JPA failure", provider);

        List<SqlSignal> signals =
            SqlSignalScanner.scan(jpa);

        assertTrue(signals.stream().anyMatch(s ->
            "23505".equals(s.sqlState())
        ));
    }
}
~~~

Test không yêu cầu exception từ đúng ba tầng; số wrapper thay đổi mà utility vẫn tìm được SQLState.

### 18.2. Test SQLException.nextException

~~~java
@Test
void findsSqlStateInNextException() {
    SQLException outer = new SQLException(
        "batch failed",
        null,
        0
    );

    SQLException unique = new SQLException(
        "unique violation",
        "23505",
        0
    );

    outer.setNextException(unique);

    PersistenceException wrapped =
        new PersistenceException(
            "JPA batch failure", outer
        );

    List<SqlSignal> signals =
        SqlSignalScanner.scan(wrapped);

    assertTrue(signals.stream().anyMatch(s ->
        "23505".equals(s.sqlState())
    ));
}
~~~

Nếu utility chỉ dùng getCause, test này có thể bỏ sót **23505**.

### 18.3. Test không có SQLException

~~~java
@Test
void nonSqlFailureReturnsEmptySignals() {
    IllegalArgumentException validationFailure =
        new IllegalArgumentException("invalid input");

    assertTrue(
        SqlSignalScanner.scan(validationFailure).isEmpty()
    );
}
~~~

**Empty signals không có nghĩa không có lỗi**, chỉ nghĩa utility không tìm thấy SQLException trong các links được quét.

### 18.4. Test có cause chain lặp

Một số Throwable wrappers/custom exceptions có thể tạo liên kết không bình thường (ví dụ nextException chain có cycle nếu bị cấu hình sai). Utility sử dụng identity-based visited set và giới hạn 64 để không treo.

Có thể tạo một SQLException A và B, đặt A.next=B, B.next=A để test termination:

~~~java
@Test
void doesNotLoopOnNextExceptionCycle() {
    SQLException a = new SQLException("a", "23505");
    SQLException b = new SQLException("b", "23503");

    a.setNextException(b);
    b.setNextException(a);

    List<SqlSignal> signals =
        SqlSignalScanner.scan(a);

    assertEquals(2, signals.size());
}
~~~

Trong môi trường thực, không nên cố tình tạo vòng lỗi; test chỉ kiểm tra thuật toán đọc exceptions phòng thủ.

### 18.5. Test SQLState null và vendorCode

~~~java
@Test
void preservesNullSqlStateWithoutCrashing() {
    SQLException sql = new SQLException(
        "unknown vendor failure",
        null,
        1062
    );

    List<SqlSignal> signals =
        SqlSignalScanner.scan(sql);

    assertEquals(1, signals.size());
    assertNull(signals.get(0).sqlState());
    assertEquals(1062, signals.get(0).vendorCode());
}
~~~

Điểm quan trọng: **SQLState null** là dữ liệu diagnostic thiếu, không phải lý do để utility ném NullPointerException.

### 18.6. Test classifier không đoán trùng SKU

Với SQLState 23505 nhưng constraintProbe trả **Optional.empty()**:

~~~text
Expected:
INTEGRITY_CONSTRAINT
Không tự suy ra:
DUPLICATE_PRODUCT_SKU
~~~

Với cùng SQLState và constraintName=uk_products_sku:

~~~text
Expected:
DUPLICATE_PRODUCT_SKU
~~~

Đây là test cho **bộ phân loại có business context**, không chỉ cho scanner JDBC.

### 18.7. Test JPA semantic ưu tiên SQL code

Nếu có OptimisticLockException với cause SQLException chung, classifier nên ưu tiên semantic **OPTIMISTIC_CONFLICT**, thay vì gán UNKNOWN hoặc DATABASE_UNAVAILABLE do thiếu/nhầm SQLState.

Điều này chứng minh mục tiêu **đọc sâu mà không mất ranh giới JPA**: thông tin provider/driver bổ sung, không thay JPA exception contract một cách tùy tiện.

## 19. Integration tests trên PostgreSQL và JPA provider thực

Unit tests ở phần 18 không chứng minh Hibernate + PostgreSQL thực sự báo SQLState/constraintName như ta mong đợi. Để bảo đảm application error policy, cần **database integration tests**.

### 19.1. Cấu hình môi trường test

- PostgreSQL thật hoặc Testcontainers với version gần production;
- JPA provider/driver versions được ghi rõ;
- Schema migrations thật (không chỉ Hibernate auto-create DDL);
- Table products có **uk_products_sku**;
- Transaction manager/context giống production ở những điểm có ý nghĩa;
- Pool cho phép nhiều connections nếu test concurrency;
- Mỗi test có fixture riêng, cleanup/rollback;
- Không log credentials hoặc raw sensitive parameters.

### 19.2. Helper resource-local transaction để tạo Product

Ví dụ sử dụng entity Product từ phần 1 và EntityManagerFactory **emf** đã được khởi tạo:

~~~java
private void insertAndCommit(
        EntityManagerFactory emf,
        String sku) {

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        em.persist(new Product(
            sku,
            new BigDecimal("100000.00")
        ));

        em.flush();
        tx.commit();
    } catch (RuntimeException failure) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw failure;
    } finally {
        em.close();
    }
}
~~~

Code dành cho **JPA resource-local**, không dùng trực tiếp trong một JTA/Spring-managed transaction. Phần imports cần bao gồm EntityManager/EntityTransaction/EntityManagerFactory, BigDecimal và JUnit.

### 19.3. Test duplicate SKU và SQLState 23505

~~~java
@Test
void duplicateSkuHasPostgresUniqueSignal() {
    String sku = "KB-" + UUID.randomUUID();

    insertAndCommit(emf, sku);

    RuntimeException failure = assertThrows(
        RuntimeException.class,
        () -> insertAndCommit(emf, sku)
    );

    List<SqlSignal> signals =
        SqlSignalScanner.scan(failure);

    assertTrue(signals.stream().anyMatch(s ->
        "23505".equals(s.sqlState())
    ));
}
~~~

Test này được viết **cụ thể cho PostgreSQL/stack test**. Nếu dùng MySQL/SQL Server/Oracle, phải đổi expected signals. Nếu không tìm thấy SQLState vì provider đã che đi một lớp hoặc driver không giữ chain, test giúp phát hiện limitation cần điều chỉnh adapter, **không được sửa bằng cách đoán exception từ message thô**.

### 19.4. Test constraint name nếu Hibernate hỗ trợ

~~~java
Optional<String> constraintName =
    HibernateConstraintProbe.findConstraintName(failure);

assertEquals(
    Optional.of("uk_products_sku"),
    constraintName
);
~~~

Test chỉ phù hợp khi **Hibernate + PostgreSQL dialect/driver** thực sự expose constraint name. Nếu provider không có tên, cần quyết định classifier fallback category tổng quát, không ép luôn trả DUPLICATE_PRODUCT_SKU.

### 19.5. Test DB row sau rollback

Sau khi INSERT trùng bị từ chối:
1. Mở EntityManager C mới;
2. Query count by SKU;
3. Assert chỉ có một row;
4. Không dùng EntityManager của transaction lỗi để kiểm tra DB.

~~~java
EntityManager check = emf.createEntityManager();

try {
    Long count = check.createQuery(
        """
        select count(p)
        from Product p
        where p.sku = :sku
        """,
        Long.class
    )
    .setParameter("sku", sku)
    .getSingleResult();

    assertEquals(1L, count);
} finally {
    check.close();
}
~~~

Điều này giúp chứng minh transaction thất bại không làm thêm row thứ hai.

### 19.6. Test CHECK bằng JDBC writer độc lập

Tạo schema có:

~~~sql
CONSTRAINT ck_products_price_nonnegative
    CHECK (price >= 0)
~~~

Dùng JDBC riêng:

~~~java
try (Connection c = dataSource.getConnection()) {
    c.setAutoCommit(false);

    try (PreparedStatement ps = c.prepareStatement(
            """
            INSERT INTO products(sku, price)
            VALUES (?, ?)
            """
    )) {
        ps.setString(1, "BAD-" + UUID.randomUUID());
        ps.setBigDecimal(2, new BigDecimal("-10"));

        SQLException error = assertThrows(
            SQLException.class,
            ps::executeUpdate
        );

        assertEquals("23514", error.getSQLState());
    } finally {
        c.rollback();
    }
}
~~~

Test chứng minh DB CHECK hoạt động **không cần** Jakarta Bean Validation hoặc JPA. Tên chính xác constraint phụ thuộc migration; nên test diagnostic mapping cho nó riêng nếu application contract cần.

### 19.7. Test NOT NULL và FOREIGN KEY riêng

Dùng JDBC:
- INSERT price=NULL để gây NOT NULL (PostgreSQL thường 23502);
- INSERT order với customer_id không tồn tại để gây FK (thường 23503).

Mỗi test phải có schema/fixtures phù hợp. Không suy rằng SQLState 23503 tự có nghĩa “user nhập sai” vì lỗi FK cũng có thể đến từ race giữa check và delete.

### 19.8. Test optimistic conflict hai EntityManagers

Với một entity có:

~~~java
@Version
private Long version;
~~~

tạo scenario:

~~~text
1. A begin + find Document#42 version V.
2. B begin + find Document#42 version V.
3. B thay đổi field và commit → DB version V+1.
4. A thay đổi field dựa trên bản V.
5. A flush/commit → optimistic conflict.
6. Rollback A.
7. Context C mới đọc DB → state của B còn nguyên.
~~~

Test phải dùng **hai EntityManagers/transactions độc lập**, không dùng cùng persistence context. Exception có thể xuất hiện tại flush hoặc commit, nên assert bao quanh transaction boundary và dùng **CauseTypes** hoặc framework translation phù hợp.

### 19.9. Test deadlock và serialization không nên dựa vào sleep mù quáng

Muốn tạo deadlock có kiểm soát, dùng hai physical connections/transactions và **CountDownLatch/Barrier** để đảm bảo A/B đã lấy khóa đầu tiên trước khi thử khóa thứ hai. Cần có timeout guard và cleanup để CI không treo.

Không dùng **Thread.sleep(1000)** rồi kết luận test luôn tạo deadlock; tốc độ scheduler/DB/connection pool có thể thay đổi.

### 19.10. Test commit-time error tại outer boundary

Với Spring @Transactional, có thể dùng **TransactionTemplate** để chắc chắn test quan sát cả commit:

~~~java
RuntimeException failure = assertThrows(
    RuntimeException.class,
    () -> transactionTemplate.executeWithoutResult(
        status -> {
            Product product = new Product(
                duplicateSku,
                new BigDecimal("100000.00")
            );

            entityManager.persist(product);
            // Không bắt buộc flush ở đây;
            // lỗi có thể phát ra khi template commit.
        }
    )
);
~~~

Đây là snippet cho Spring environment có **transactionTemplate**, **entityManager**, **duplicateSku** fixtures. Tên exception cụ thể có thể là Spring DataAccessException hoặc JPA wrapper. Test nên phân loại **đúng category**, không hard-code một message hay wrapper cố định.

### 19.11. Test portability bằng cùng application category

Khi hỗ trợ PostgreSQL và MySQL:
- Adapter PostgreSQL đọc SQLState 23505;
- Adapter MySQL đọc vendorCode 1062 và constraint evidence phù hợp;
- Cả hai trả **DUPLICATE_PRODUCT_SKU** khi chắc chắn vi phạm đúng business key;
- Application service không đổi.

Test nên assert **stable application outcome** và log diagnostics theo dialect, thay vì ép cùng SQLState cụ thể trên hai DBMS.

### 19.12. Test commit outcome unknown khó mô phỏng

Mất kết nối đúng thời điểm COMMIT là một lỗi phân tán khó tái hiện deterministically. Có thể dùng network fault injection/proxy trong staging/chaos tests để kiểm tra idempotency/reconciliation; không nên có một unit test giả lập exception rồi kết luận giao dịch đã rollback.

Application contract phải cho phép xác minh theo request ID khi outcome chưa biết.

## 20. Kỹ thuật debug khi có một incident

Một trình tự thực tế:

### 20.1. Bước 1 — Thu thập top-level exception

Ghi:
- Package/class của exception ngoài cùng;
- Operation đang chạy;
- Transaction boundary;
- Trace/request ID;
- Thời điểm lỗi: persist/flush/commit;
- Có Spring transaction translation hay không.

Không chỉ chụp dòng cuối stack trace.

### 20.2. Bước 2 — Duyệt causes và JDBC chain

Dùng SqlSignalScanner hoặc diagnostics tương đương để đọc:
- SQLState;
- Vendor code;
- Driver exception class;
- SQLException.nextException chain.

Tìm thêm:
- JPA OptimisticLockException;
- Hibernate constraintName;
- Jakarta Bean Validation violations;
- Suppressed rollback/cleanup errors.

### 20.3. Bước 3 — Xác nhận schema/SQL

Nếu lỗi integrity:
- Constraint có thật trong schema/migration không?
- Constraint name là gì?
- Field/column nào chịu trách nhiệm?
- DB có đúng schema/tenant không?
- Native SQL có dùng physical names đúng không?

Nếu lỗi connection/query timeout:
- DB logs/wait events;
- Pool metrics;
- Timeouts;
- Query plan;
- Network.

### 20.4. Bước 4 — Xác định transaction outcome

Một câu hỏi bắt buộc:
- Transaction đã commit chưa?
- Đã rollback chưa?
- Đã bị đánh dấu rollback-only chưa?
- Có connection loss lúc commit khiến outcome chưa biết không?
- Có side effect bên ngoài DB đã chạy trước commit không?

Không ghi **COMMITTED** chỉ vì service method body return, hoặc **ROLLED_BACK** chỉ vì code vào catch.

### 20.5. Bước 5 — Áp error policy rồi xử lý nguyên nhân dài hạn

Sau khi có dữ liệu:
- Client invalid → validation response;
- Duplicate business key → conflict;
- Deadlock → short retry policy và review lock ordering;
- Schema drift → migration fix;
- Connection failures → infrastructure alert/reconciliation;
- Repeated query timeout → index/query/DB capacity analysis.

Không dừng ở việc map exception; root cause có thể cần một thay đổi thiết kế.

## 21. Những anti-pattern khi đọc lỗi JPA

| Anti-pattern | Vì sao sai | Hướng thay thế |
|---|---|---|
| Chỉ log exception.getMessage() | Mất SQLState/constraint/cause | Structured diagnostics + correlation |
| Lấy getCause().getCause().getCause() | Phụ thuộc wrapper count, dễ NPE | Duyệt chain an toàn |
| Chỉ lấy deepest Throwable | Có thể bỏ SQLException ở giữa | Thu thập tín hiệu nhiều tầng |
| Bỏ qua SQLException.nextException | Mất lỗi chi tiết của JDBC batch | Duyệt nextException |
| Mọi PersistenceException đều retry | Permanent constraints không tự hết | Classifier và retry policy |
| Mọi DataIntegrityViolationException là trùng SKU | Còn FK/CHECK/NOT NULL | Map theo constraint/business |
| Mọi SQLState class 23 trả HTTP 400 | Có thể là bug/schema drift/race | Xem context và ownership |
| SQLState 23505 ở mọi DB | Mã cụ thể phụ thuộc dialect | Dialect-specific adapter |
| So raw English message "duplicate key" | Thay đổi theo locale/version | SQLState/vendor/constraint structured |
| Domain import PSQLException | Khóa business vào PostgreSQL driver | Infrastructure adapter |
| Domain import Hibernate ConstraintViolationException | Khóa core vào provider | Dịch sang stable application error |
| Nhầm Jakarta Validation với Hibernate ORM exception | Hai tầng có cách xử lý khác | Fully qualified names/adapter |
| Cố unwrapping Hibernate Session ở mọi service | Lệ thuộc provider, thiếu cần thiết | Dùng JPA API mặc định |
| Bắt mọi RuntimeException rồi coi là DB unavailable | Che code bug/validation | Narrow classification/propagate |
| Bắt exception trong @Transactional rồi return success | Transaction có thể rollback | Propagate/mark rollback phù hợp |
| Chỉ catch quanh repository.save | Lỗi có thể phát ở commit | Catch/translate ở transaction boundary |
| Flush thành công thì báo đã commit | Flush không phải commit | Xác nhận sau commit |
| Retry cùng EntityManager sau flush fail | Context/transaction có thể invalid | Rollback, context mới |
| Retry stale optimistic snapshot y nguyên | Có thể ghi đè dữ liệu mới | Reload/resolve intent |
| Retry payment sau connection loss ở commit | Commit outcome có thể unknown | Idempotency + reconciliation |
| Log exception chứa key value nhạy cảm | Rò PII/credentials | Redaction, structured tags |
| Gắn raw SQL vào metrics label | High cardinality/secrets | Bounded categories |
| Một lỗi log ERROR ở mọi tầng | Duplicate alerts | Một ownership boundary |
| SQLGrammarException luôn là lỗi cú pháp | Có thể thiếu table/permission | Xem DB SQLState/metadata |
| NoResultException được coi DB outage | Kết quả query hợp lệ | Optional/missing-resource policy |
| BatchUpdateException update counts = committed rows | Transaction có thể rollback | Kiểm tra commit outcome |
| Test H2 rồi áp SQLState PostgreSQL | Drivers/dialects khác | Target-DB integration tests |
| Mock Hibernate wrapper và gọi là integration test | Không chứng minh DB thực trả code | Test DB/driver thật |
| Không test rollback sau constraint failure | Có thể để connection/tx hỏng | Verify clean tx/new context |
| Expose constraintName cho API mọi lúc | Lộ schema/internal fields | Stable public error code |
| Map FK violation thành 404 mặc định | Không biết parent/child operation | Domain context |
| Retry query timeout vì “transient” | Có thể tăng tải và lặp vô hạn | Query diagnostics/limits |
| Quên 08-class connection errors | Mất thông tin availability/outcome | Classifier + idempotency |
| Constraint name hard-code rải khắp service | Khó migration/provider swap | Centralized adapter registry |

### 21.1. Vì sao có những lỗi không nên “xử lý” ngay?

Một lỗi SQL do migration thiếu table không thể được sửa bằng cách catch rồi chuyển thành danh sách rỗng:

~~~java
try {
    return repository.findAll();
} catch (PersistenceException ex) {
    return List.of();
}
~~~

Client sẽ tưởng “không có sản phẩm” dù hệ thống đang hỏng. Cần phân biệt **empty business result** với **infrastructure failure**, giữ alert/log để vận hành biết nguyên nhân.

### 21.2. Log đầy đủ không nhất thiết log thô

Một log hữu ích có thể chứa:
- Category, SQLState, constraint code;
- Operation, transaction attempt, request ID;
- Provider/driver version;
- Sanitized stack trace trong kênh bảo mật.

Không cần ghi raw SQL bind parameter hoặc toàn bộ entity fields. Đặc biệt constraint errors của UNIQUE có thể chứa exact value làm lộ email, tài khoản, token nếu log message thô.

### 21.3. Cách dùng Throwable trực tiếp có thể tạo coupling

Ứng dụng giữ root exception cause để kỹ thuật truy vết là tốt. Nhưng để controllers/service branches gọi:

~~~java
if (cause instanceof
        org.hibernate.exception.ConstraintViolationException) {
    // Business workflow A
}
~~~

khiến mỗi chức năng phải hiểu provider. Hãy gom mã hiểu provider trong persistence adapter/translator và expose **ổn định theo nghiệp vụ**.

## 22. Bài tập thực hành

Các bài tập khuyến khích trả lời theo ba phần: **tín hiệu quan sát được**, **phân loại lỗi**, và **phục hồi/response**. Không chỉ nêu một tên exception.

### Bài 1. Đọc chuỗi bốn tầng

Cho:

~~~text
RollbackException
  → PersistenceException
  → Hibernate ConstraintViolationException
  → PostgreSQL SQLException SQLState=23505
~~~

Hãy xác định tầng nào là JPA, provider và JDBC. Nếu constraint=uk_products_sku, application có thể trả category nào? Vì sao domain không nên import Hibernate exception?

### Bài 2. Không có SQLException

Một Product bị Bean Validation @NotNull từ chối trước INSERT. SqlSignalScanner.scan trả list rỗng. Điều đó chứng minh “không có lỗi” không? Hãy phân loại.

### Bài 3. Root cause không phải SQLState

Một RollbackException có cause SQLException SQLState 08006, SQL exception lại có cause SocketException. Nếu chỉ lấy deepest cause, có thể bỏ sót thông tin gì?

### Bài 4. SQLException.nextException

Một BatchUpdateException có SQLState null, nextException có 23505. Viết đoạn code hoặc sử dụng SqlSignalScanner để lấy đủ tín hiệu. Tại sao vòng while(getCause) không đủ?

### Bài 5. Tránh NPE và vòng lặp

Viết một traversal có tối đa 64 nodes, visited identity set, xử lý cause null và nextException cycles. Giải thích vì sao không hard-code ba lần getCause.

### Bài 6. SQLState null

Một MySQL driver trả SQLException với SQLState null, vendorCode=1062. Bộ phân loại PostgreSQL có được kết luận duplicate SKU ngay không? Cần xác định dialect và constraint evidence gì?

### Bài 7. SQLState class 23

Một PostgreSQL error có SQLState=23503. Đó là loại nào? Tại sao không mặc định trả “SKU đã tồn tại”?

### Bài 8. Constraint name không có

SQLState=23505 nhưng provider không trả constraint name. Hãy thiết kế fallback category và public response sao cho không khẳng định sai field.

### Bài 9. Multiple UNIQUE constraints

Products có uk_products_sku và uk_products_external_ref. Hai lỗi đều 23505. Hãy thiết kế mapping adapter trả hai business categories riêng nếu có constraint name, và INTEGRITY_CONSTRAINT nếu không xác định được.

### Bài 10. SQLException vendor code

So sánh duplicate key:
- PostgreSQL 23505;
- MySQL error 1062;
- SQL Server 2627/2601;
- Oracle ORA-00001.

Vì sao một bộ phân loại chung chỉ so vendorCode==1062 là sai?

### Bài 11. Hibernate và Jakarta ConstraintViolationException

Chọn namespace đúng cho:
- Entity @PositiveOrZero fail khi validation chạy;
- DB UNIQUE constraint fail qua Hibernate ORM.

Vì sao hai exceptions có cùng simple name không được xử lý cùng cách vô điều kiện?

### Bài 12. Spring DataIntegrityViolationException

Code catch DataIntegrityViolationException rồi luôn trả PRODUCT_SKU_ALREADY_EXISTS. Hãy phân tích các trường hợp FK, NOT NULL và CHECK làm code này sai.

### Bài 13. NoResultException

getSingleResult không trả row. Nó có phải database unavailable không? Theo JPA, NoResultException có bắt buộc đánh dấu rollback không? Đề xuất repository method trả Optional phù hợp.

### Bài 14. Optimistic conflict

A sửa Product version=8, B commit version=9 trước A. A flush gặp OptimisticLockException. Có nên dựa vào SQLState 23505 để phân loại không? Làm sao xử lý bản nháp của A?

### Bài 15. Pessimistic lock

A giữ lock trên Product#42, B timeout. Phân biệt LockTimeoutException và PessimisticLockException theo rollback scope JPA. Với PostgreSQL transaction đã aborted, service nên làm gì?

### Bài 16. Query timeout vs lock timeout

Một query chậm do full table scan, không có row lock contention, nhưng ném QueryTimeoutException. Tại sao tăng jakarta.persistence.lock.timeout không giải quyết? Nêu metric/plan cần xem.

### Bài 17. Lỗi xuất hiện muộn

Một @Transactional service gọi repository.save và return. Commit trong Spring proxy mới ném constraint failure. Vì sao try/catch chỉ bao quanh save có thể bỏ lỡ? Đề xuất vị trí error boundary phù hợp.

### Bài 18. Flush không commit

Một service gọi em.flush thành công rồi gửi email “đã lưu”, nhưng commit thất bại. Đề xuất outbox/after-commit policy để không tạo side effects sai.

### Bài 19. Nuốt exception

Một service catch PersistenceException, log warning, rồi return success. Transaction thực tế rollback-only. Mô tả response sai có thể xảy ra và cách sửa.

### Bài 20. Rollback thất bại

INSERT bị UNIQUE violation; sau đó rollback cũng lỗi vì connection đứt. Làm sao giữ nguyên exception chính mà vẫn lưu rollbackFailure để diagnostics?

### Bài 21. PostgreSQL 40001

Hai transactions concurrent gây serialization failure. Hãy thiết kế retry toàn transaction, context mới, backoff và test reread business state.

### Bài 22. PostgreSQL 40P01

A khóa Account#1 rồi #2, B khóa #2 rồi #1. Vẽ wait-for graph và trình bày cách giảm deadlock, không chỉ retry.

### Bài 23. PostgreSQL 55P03

Một operation yêu cầu NOWAIT và nhận lock_not_available. Có nên coi database unavailable không? Nên phân loại lock contention thế nào?

### Bài 24. Commit outcome unknown

Ứng dụng gửi COMMIT, database đã commit nhưng connection reset trước acknowledgment. Caller nhận exception và gửi lại request chuyển tiền. Hãy thiết kế idempotency key, UNIQUE request_id và reconciliation.

### Bài 25. Connection pool cạn

B chờ lấy JDBC connection rồi timeout trước khi SQL thực thi. SQLState scanner có thể tìm được SQLState lock contention không? Cần xem metrics nào?

### Bài 26. Batch 100 rows

Một batch INSERT 100 Products gặp SKU trùng ở statement thứ 72. Driver trả BatchUpdateException với update counts. Có được báo 71 Products đã commit không? Vì sao transaction boundary là yếu tố quyết định?

### Bài 27. Schema drift

Error class là Hibernate SQLGrammarException; cause là table "sales.purchase_orders" không tồn tại. Hãy liệt kê các nguyên nhân ngoài syntax: schema, migration, permissions, quoted identifiers, wrong database.

### Bài 28. CHECK failure từ ETL

Một ETL ghi giá -10, DB CHECK trả PostgreSQL 23514. Nên retry message vô hạn hay quarantine/repair? Phân biệt với lỗi transient deadlock.

### Bài 29. UNIQUE race

Hai concurrent requests đều pass existsBySku("KB-001") rồi INSERT. Tại sao application-level pre-check không thay DB UNIQUE? Error category nên được quyết định ở đâu?

### Bài 30. Spring exception translation

Một application nhận ObjectOptimisticLockingFailureException, code chỉ kiểm tra jakarta.persistence.OptimisticLockException trong top-level Throwable. Có thể bỏ sót gì? Đề xuất adapter hỗ trợ cả Spring semantic và cause chain.

### Bài 31. Logging và privacy

PostgreSQL unique error có detail chứa email address. Thiết kế log fields an toàn và một public response không tiết lộ email hoặc raw SQL.

### Bài 32. SQLState trong metrics

Một team gắn SQL message, productId, email và full SQL vào metric labels. Tại sao có vấn đề cardinality/privacy? Thay bằng error categories, SQLState class và constraint code allowlisted.

### Bài 33. Dịch lỗi theo business operation

Cùng SQLState 23503 xuất hiện khi:
1. Tạo Order với customer_id không tồn tại;
2. Xóa Customer còn Orders.

Có nên trả cùng thông điệp “Customer không tồn tại” không? Nêu business context và constraint metadata cần xét.

### Bài 34. Unit test scanner

Tạo SQLException SQLState null có nextException SQLState 23505. Assert scanner tìm được 23505. Tạo cause cycle hoặc nextException cycle, assert scanner kết thúc theo giới hạn.

### Bài 35. Unit test classifier

Dùng fake ConstraintNameProbe trả:
- uk_products_sku;
- uk_products_external_ref;
- Optional.empty().

Với cùng SQLState 23505, xác nhận category tương ứng và không đoán sai khi thiếu tên.

### Bài 36. Integration test database thật

Dùng PostgreSQL Testcontainers/migrations để:
- Insert Product SKU duy nhất;
- Insert duplicate SKU;
- Bắt propagated exception quanh persist/flush/commit;
- Dò SQLException 23505;
- Kiểm tra constraint name khi provider hỗ trợ;
- Kiểm tra chỉ còn một row bằng EntityManager mới.

### Bài 37. Validation vs SQL exception

Tạo Product price=-1:
- Case A: Jakarta Bean Validation chặn trước SQL;
- Case B: Bypass Java validation bằng JDBC và để DB CHECK chặn.

So sánh exception types, SQLState availability và cách trả API error.

### Bài 38. Retry policy matrix

Cho các trường hợp:
- 23505 duplicate;
- 23514 CHECK;
- 40001 serialization;
- 40P01 deadlock;
- OptimisticLockException;
- 08006 lúc bắt đầu query;
- Mất kết nối ngay tại commit.

Đề xuất quyết định **retry / không retry / reconcile** và lý giải idempotency.

### Bài 39. Nhiều provider

Một dự án chuẩn bị đổi Hibernate sang EclipseLink. Những files nào được phép import Hibernate-specific APIs? Unit tests và integration tests cần chứng minh application error categories giữ nguyên thế nào?

### Bài 40. Thiết kế một hệ thống lỗi hoàn chỉnh

Hãy xây kiến trúc:
1. Domain Product và ProductRepository port;
2. JPA infrastructure adapter;
3. SqlSignalScanner đọc cause + SQLException.nextException;
4. Provider-specific constraint probe;
5. Dialect-specific classifier;
6. Stable application exception/categories;
7. Transaction rollback strategy;
8. HTTP/controller error handler;
9. Structured logs/traces với requestId;
10. JUnit unit tests + PostgreSQL integration tests;
11. Retry/idempotency policy khi transaction lỗi.

Mục tiêu là **đổi DB/provider mà không phải sửa domain service**, nhưng vẫn giữ đủ kỹ thuật để debug nguyên nhân gốc.

## 23. Bảng tra cứu nhanh: tầng lỗi và nguồn thông tin

| Cần biết | Nơi đọc | Lưu ý |
|---|---|---|
| Có phải lỗi JPA không? | jakarta.persistence.PersistenceException và subclasses | Có thể có wrapper |
| Optimistic conflict? | OptimisticLockException hoặc Spring translation | Không tự retry stale snapshot |
| Pessimistic lock failure? | LockTimeoutException/PessimisticLockException | Xét rollback scope và DB state |
| Query không có row? | NoResultException | Không phải JDBC failure |
| Commit thất bại? | RollbackException/transaction manager error | Đọc causes, có thể outcome unknown |
| Object vi phạm Bean Validation? | jakarta.validation.ConstraintViolationException | Có thể không có SQL |
| Hibernate báo SQL integrity? | org.hibernate.exception.ConstraintViolationException | Provider-specific |
| Hibernate có SQLException bên trong? | org.hibernate.JDBCException.getSQLException() | Chỉ ở Hibernate adapter |
| SQLState? | SQLException.getSQLState() | Có thể null; dialect-specific details |
| Vendor error code? | SQLException.getErrorCode() | Không portable giữa DB |
| JDBC batch error tiếp theo? | SQLException.getNextException() | Khác Throwable.getCause |
| Root cause chain? | Throwable.getCause() | Không hard-code số lớp |
| Cleanup/rollback cũng lỗi? | Throwable.getSuppressed() | Đừng che exception chính |
| Constraint name? | Provider/driver-specific metadata | Có thể null, cần allowlist |
| Spring integrity abstraction? | DataIntegrityViolationException | Bao gồm UNIQUE, FK, CHECK, NOT NULL |
| Spring optimistic abstraction? | OptimisticLockingFailureException | Có thể có subclass |
| Duplicate PostgreSQL? | SQLState 23505 | Kiểm tra constraint cụ thể |
| FK PostgreSQL? | SQLState 23503 | Cần business operation context |
| NOT NULL PostgreSQL? | SQLState 23502 | Có thể input hoặc schema drift |
| CHECK PostgreSQL? | SQLState 23514 | Kiểm tra DB rule và input source |
| Serialization PostgreSQL? | SQLState 40001 | Retry toàn transaction nếu an toàn |
| Deadlock PostgreSQL? | SQLState 40P01 | Rollback, lock ordering, bounded retry |
| Lock unavailable PostgreSQL? | SQLState 55P03 | NOWAIT/lock contention |
| Query canceled PostgreSQL? | SQLState 57014 | Không mặc định là row lock |
| Connection failure class? | SQLState prefix 08, DB/driver logs | Commit outcome có thể unknown |
| MySQL duplicate? | Vendor code 1062 thường gặp | Kiểm tra dialect/constraint |
| SQL Server duplicate? | Vendor codes 2601/2627 thường gặp | Kiểm tra driver/error mapping |
| Oracle duplicate? | ORA-00001 thường gặp | Kiểm tra driver/vendor code |
| Retryable? | Transaction context + classifier + idempotency policy | Không suy tự động từ mọi SQLState |
| DB đã commit chưa? | Transaction outcome/reconciliation | Exception không luôn chứng minh chưa commit |
| Public API error? | Application error mapping | Không trả raw SQL/stack trace |
| Điều tra incident? | Structured logs + trace/request ID + DB diagnostics | Kiểm soát dữ liệu nhạy cảm |

### 23.1. Ma trận vị trí code phù hợp

| Loại logic | Domain | Application service | Persistence adapter | Web/message boundary |
|---|---:|---:|---:|---:|
| Business invariant | Có | Có khi orchestration | Không làm policy chính | Không |
| Gọi Repository port | Không bắt buộc | Có | Implementation | Không |
| Biết Jakarta Persistence API | Tránh nếu clean architecture | Tùy kiến trúc, ưu tiên tránh | Có | Tránh |
| Biết Hibernate exception class | Không | Không | **Có, nếu dùng Hibernate** | Không |
| Biết PostgreSQL SQLState | Không | Không | **Có, ở dialect adapter** | Không |
| Duyệt SQLException.nextException | Không | Không | **Có** | Không |
| Chọn retry transaction | Không | **Có** | Đưa tín hiệu | Có thể orchestration |
| Quyết định 409/412/503 | Không | Có thể đưa category | Không | **Có** |
| Log SQL diagnostics | Không | Không cần | Thu thập | Ghi nhận có kiểm soát |
| Bảo đảm idempotency | Domain/invariant | **Có** | DB UNIQUE hỗ trợ | Request ID |
| Reconcile unknown commit | Quy tắc nghiệp vụ | **Có** | Đọc authoritative state | Trả pending/status |

Bảng thể hiện một phương án tổ chức phổ biến, không bắt buộc mọi dự án dùng hexagonal architecture. Mục tiêu bất biến là **giữ sự hiểu biết về provider/driver ở nơi có ownership rõ**.

## 24. Checklist đọc root cause và phục hồi an toàn

### 24.1. Nhận diện lỗi

1. **Exception ngoài cùng thuộc package nào?** Jakarta Persistence, Spring DAO, Hibernate, JDBC hay validation?
2. **Có RollbackException wrapper ở commit không?**
3. **Có OptimisticLockException hoặc semantic tương đương sâu trong cause chain không?**
4. **Có LockTimeoutException/PessimisticLockException không?**
5. **Có QueryTimeoutException không và timeout ở lớp nào?**
6. **Có NoResultException/NonUniqueResultException thuộc query contract không?**
7. **Có Jakarta Bean Validation violation trước khi SQL chạy không?**
8. **Có Hibernate ORM JDBC/ConstraintViolationException không?**
9. **Có Throwable cause chain cần duyệt không?**
10. **Có SQLException.nextException hay BatchUpdateException không?**
11. **Có suppressed rollback/cleanup failure cần ghi nhận không?**
12. **Có giới hạn traversal và phát hiện cycles không?**
13. **Có tránh hard-code getCause().getCause() không?**

### 24.2. SQL/provider diagnostics

14. **Có tìm được SQLException không?** Nếu không, có thể lỗi vẫn là JPA/validation.
15. **SQLState có null không?**
16. **SQLState prefix/class có được nhận diện theo database không?**
17. **Vendor error code có được đọc đúng driver không?**
18. **Database product/version/dialect có được xác nhận không?**
19. **Constraint name có được provider/driver expose không?**
20. **Tên constraint có phải từ trusted metadata không?**
21. **Nếu thiếu constraint name, có fallback category an toàn không?**
22. **Có nhiều SQL signals với một cái chi tiết hơn không?**
23. **Có phân biệt FK, CHECK, NOT NULL và UNIQUE không?**
24. **Có kiểm tra generated SQL/native SQL/DDL migration đúng không?**
25. **Có kiểm tra đúng schema/catalog/tenant không?**
26. **Có phân biệt connection pool failure với SQL lock wait không?**
27. **Có xem DB wait events khi deadlock/query timeout không?**

### 24.3. Ranh giới kiến trúc

28. **Domain có đang import Hibernate hoặc PostgreSQL exception không?**
29. **Repository adapter có chịu trách nhiệm đọc provider-specific metadata không?**
30. **Có generic SQLException scanner không phụ thuộc provider không?**
31. **Có dialect-specific classification khi cần không?**
32. **Có stable application error category không?**
33. **Có phân biệt technical diagnostics với business response không?**
34. **Có giữ cause trong internal exception để debug không?**
35. **Có tránh serialize Throwable trong HTTP response không?**
36. **Có tránh nhiều nơi cùng map một lỗi thành codes khác nhau không?**
37. **Có xử lý Spring DataAccessException khi project dùng Spring không?**
38. **Có bao trọn commit boundary thay vì chỉ repository.save không?**

### 24.4. Transaction và phục hồi

39. **Lỗi xảy ra tại persist, flush hay commit?**
40. **Transaction đã rollback hoặc rollback-only chưa?**
41. **EntityManager có còn usable không, hay cần đóng/tạo mới?**
42. **Có tránh tiếp tục SQL trên DB transaction aborted không?**
43. **Nếu rollback cũng lỗi, có giữ primary failure không?**
44. **Có phân biệt SQL transient và permanent không?**
45. **Có tránh retry UNIQUE/CHECK/NOT NULL invalid input không?**
46. **Với optimistic conflict, có reload/resolve thay vì retry snapshot cũ không?**
47. **Với deadlock/serialization, có retry toàn transaction mới không?**
48. **Có retry budget và backoff/jitter không?**
49. **Operation có idempotent hoặc request ID không?**
50. **Connection loss có xảy ra lúc commit không?**
51. **Nếu commit outcome unknown, có reconciliation protocol không?**
52. **Có tránh phát side effects trước commit hoặc dùng outbox không?**

### 24.5. API, bảo mật và quan sát

53. **Public error code có ổn định và được tài liệu hóa không?**
54. **HTTP status có phản ánh business context không, không chỉ SQLState?**
55. **Có tránh tiết lộ constraint/table/column details cho client không?**
56. **Có ẩn raw SQL bind values và PII khỏi logs/metrics không?**
57. **Có correlation/trace ID giữa API, service và DB không?**
58. **Có log SQLState/vendorCode/constraintName nội bộ khi phù hợp không?**
59. **Có tránh duplicate ERROR logs ở nhiều layers không?**
60. **Có metrics lock/optimistic conflicts/deadlock/retry/unknown outcome không?**
61. **Metrics labels có bounded cardinality không?**
62. **Có response phù hợp với authorization/tenant isolation không?**

### 24.6. Kiểm thử và vận hành

63. **Có unit test cause traversal với nhiều wrappers không?**
64. **Có test SQLException.nextException riêng không?**
65. **Có test SQLState null và vendorCode không?**
66. **Có test cause/next cycles và traversal limit không?**
67. **Có unit test classifier theo constraintName hiện diện/vắng mặt không?**
68. **Có test optimistic vs integrity phân loại không?**
69. **Có integration test với database/provider/driver như production không?**
70. **Có migration thực tạo UNIQUE/FK/CHECK/NOT NULL không?**
71. **Có test lỗi phát sinh ở flush và commit boundary không?**
72. **Có xác minh DB state sau rollback bằng EntityManager mới không?**
73. **Có test JDBC external writer bypass Bean Validation không?**
74. **Có test concurrency deadlock/optimistic conflict khi cần không?**
75. **Có test lỗi khi DB connection lost hoặc fault injection theo khả năng không?**
76. **Có test đổi provider/dialect mà public application categories vẫn ổn không?**
77. **Có kiểm tra lỗi sau upgrade driver/Hibernate/Spring không?**
78. **Có kế hoạch incident runbook và escalation khi database unavailable không?**

### 24.7. Cây quyết định khi nhận một persistence failure

~~~text
       Một thao tác JPA thất bại
                 |
                 v
         Exception thuộc tầng nào?
                 |
         +-------+--------+
         |                |
     Validation        JPA/Spring persistence
         |                |
         v                v
   Field violations    Có OptimisticLockException?
         |               /             \
   Input/domain rule   Có              Không
         |              |                |
   Trả lỗi an toàn     Rollback          v
                       Reload/resolve   Lock/Query timeout?
                                          /       \
                                        Có        Không
                                        |           |
                                  DB wait/timeout   v
                                  tx rollback?  Đọc cause chain
                                        |           |
                                        |           v
                                        |     SQLException?
                                        |      /       \
                                        |    Có        Không
                                        |     |          |
                                        | SQLState/     JPA wrapper/
                                        | vendor/       mapping/transaction/
                                        | constraint    unknown failure
                                        |     |          |
                                        +-----+----------+
                                              |
                                              v
                                 Infrastructure classifier
                                              |
                              +---------------+---------------+
                              |               |               |
                           Permanent       Transient        Unknown/
                           integrity       transaction      unknown outcome
                              |               |               |
                           Không retry      Rollback +     Reconcile/
                           cùng input       bounded retry  investigate
                              |               |               |
                              +---------------+---------------+
                                              |
                                              v
                                  Application error category
                                              |
                                              v
                           HTTP/message policy + structured logs
~~~

## 25. Tổng kết

Một lỗi phát sinh trong JPA có thể đi qua nhiều tầng: từ **database**, qua **JDBC driver**, **JPA provider**, **Jakarta Persistence API**, rồi tới **Spring exception translation** hoặc application transaction manager. Đọc được nguyên nhân gốc giúp quyết định sửa input, xử lý conflict, retry hay báo sự cố hạ tầng, nhưng làm trực tiếp trong domain service sẽ khiến code bị phụ thuộc vendor.

Ba nguyên tắc quan trọng nhất:

1. **Đọc exception như một chuỗi tín hiệu, không chỉ một message.** Duyệt Throwable.getCause an toàn, kiểm tra SQLException.getNextException, đọc SQLState/vendorCode và constraint name khi khả dụng. Root cause sâu nhất không nhất thiết chứa đủ thông tin.
2. **Phân loại ở đúng ranh giới.** Dùng JPA exceptions cho semantics chuẩn như optimistic conflict; dùng Hibernate/Spring/JDBC/DB diagnostics trong infrastructure adapter. Chuyển thành stable application categories thay vì để domain so SQLState hoặc import PSQLException.
3. **Phục hồi dựa trên transaction state và business intent.** Lỗi có thể xuất hiện tại persist, flush hoặc commit. Rollback phù hợp, không cố retry trên transaction/context lỗi; chỉ retry transient cases trong transaction mới với giới hạn/idempotency. Nếu connection mất đúng lúc commit, outcome có thể chưa biết và phải reconcile.

Ví dụ ngắn:

~~~java
try {
    entityManager.persist(product);
    entityManager.flush();
} catch (RuntimeException failure) {
    // Infrastructure: thu thập signals có cấu trúc.
    List<SqlSignal> jdbcSignals =
        SqlSignalScanner.scan(failure);

    // Dịch tại boundary phù hợp,
    // không viết SQLState-dependent business logic
    // trong Product domain.
    throw failure;
}
~~~

**Lưu ý:** Đây là phần minh họa việc đọc diagnostics, không phải cách rollback hoàn chỉnh. Trong thực tế transaction manager/outer boundary phải chịu trách nhiệm rollback và chuyển failure thành response; nếu lỗi commit xảy ra sau thân method, catch bên trong có thể không bắt được.

Sơ đồ ghi nhớ:

~~~text
JPA/Spring exception
       |
       +-- Semantic JPA type? → optimistic/lock/transaction
       |
       +-- Provider detail?   → constraintName/SQL conversion
       |
       +-- JDBC SQLException? → SQLState/vendorCode/nextException
       |
       +-- Database metadata? → UNIQUE/FK/CHECK/locks/connection
       |
       v
Infrastructure classification
       |
       v
Stable application error
       |
       +-- Permanent input/business conflict
       +-- Retryable transaction failure
       +-- Infrastructure availability failure
       +-- Unknown commit outcome / reconciliation
       |
       v
Rollback/retry/HTTP/logging policy
~~~

**Bài học thực hành cuối cùng:** *Đọc sâu để biết nguyên nhân, nhưng trả về một hợp đồng lỗi mà application sở hữu.* Khi tách được chẩn đoán provider/driver ra khỏi domain, hệ thống vừa dễ debug các vấn đề JDBC/DBMS thật, vừa duy trì tính di động, an toàn dữ liệu và khả năng phục hồi của ứng dụng JPA.














