# Kiểm thử giao dịch, rollback và implicit commit của DDL

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Kiểm thử  
> **Mục tiêu:** Hiểu ranh giới transaction trong Oracle; kiểm thử COMMIT, ROLLBACK, SAVEPOINT và các lỗi giữa transaction; nắm implicit commit trước/sau DDL; phân biệt DML có thể rollback với DDL như TRUNCATE/ALTER/DROP; kiểm thử transaction qua Spring Boot/JPA/JDBC; nhận biết tác động của sequence, autonomous transaction và external side effect; xây dựng test cô lập, lặp lại được và không làm bẩn database dùng chung.

## 1. Vì sao phải kiểm thử transaction riêng?

Một chức năng có thể trả HTTP 200 hoặc repository method không ném exception nhưng dữ liệu vẫn sai vì transaction boundary không như người viết code nghĩ.

Các tình huống thường gặp:

- Một service cập nhật hai bảng, bước thứ hai lỗi nhưng bước thứ nhất đã commit.
- Spring method có @Transactional nhưng lời gọi nội bộ không đi qua proxy nên transaction không được mở như dự kiến.
- JPA đã thay đổi entity trong memory nhưng SQL chưa được gửi xuống database vì chưa flush.
- Native SQL hoặc stored procedure cập nhật bảng, trong khi entity đã load vẫn giữ dữ liệu cũ trong persistence context.
- DDL được chạy giữa một transaction DML và Oracle tự commit transaction đang mở.
- Test Spring có @Transactional tưởng rằng mọi thứ sẽ rollback khi test kết thúc, nhưng một câu CREATE TABLE đã commit dữ liệu fixture trước đó.
- Sequence đã tăng dù transaction insert bị rollback.
- Procedure ghi audit bằng autonomous transaction nên audit record vẫn tồn tại dù transaction nghiệp vụ rollback.
- Gọi HTTP hoặc ghi file không thể được hoàn tác bằng ROLLBACK của Oracle.

Kiểm thử transaction phải chứng minh trạng thái dữ liệu sau từng ranh giới commit/rollback, không chỉ kiểm tra return value.

## 2. Transaction trong Oracle

Transaction là một đơn vị công việc logic gồm một hoặc nhiều thay đổi dữ liệu. Oracle bảo đảm các thay đổi DML trong transaction được commit cùng nhau hoặc rollback theo transaction semantics.

Ví dụ:

~~~sql
UPDATE accounts
   SET balance = balance - 100
 WHERE account_id = 10;

UPDATE accounts
   SET balance = balance + 100
 WHERE account_id = 20;

COMMIT;
~~~

Hai UPDATE thuộc cùng transaction. Nếu bước thứ hai thất bại và ứng dụng rollback toàn transaction, thay đổi ở bước thứ nhất cũng bị hoàn tác.

### 2.1. COMMIT

COMMIT kết thúc transaction hiện tại và làm các thay đổi trở nên bền vững theo cơ chế commit của Oracle.

~~~sql
UPDATE orders
   SET status = 'PAID'
 WHERE order_id = 1001;

COMMIT;
~~~

Sau COMMIT, ROLLBACK tiếp theo không thể hoàn tác UPDATE vừa commit.

### 2.2. ROLLBACK

ROLLBACK hủy các thay đổi chưa commit trong transaction hiện tại:

~~~sql
UPDATE orders
   SET status = 'CANCELLED'
 WHERE order_id = 1001;

ROLLBACK;
~~~

Database trở lại trạng thái trước transaction đối với các thay đổi transactional đó.

ROLLBACK không đảo ngược mọi thứ mà ứng dụng đã làm. Nó không hoàn tác email đã gửi, HTTP request đã xử lý, file đã ghi, sequence đã cấp NEXTVAL hoặc autonomous transaction đã commit.

### 2.3. SAVEPOINT

SAVEPOINT đặt mốc trong transaction để có thể rollback một phần:

~~~sql
UPDATE inventory
   SET reserved_qty = reserved_qty + 1
 WHERE product_id = 501;

SAVEPOINT after_reserve;

UPDATE orders
   SET status = 'READY'
 WHERE order_id = 1001;

ROLLBACK TO after_reserve;

COMMIT;
~~~

Trong ví dụ, UPDATE inventory được giữ lại; UPDATE orders bị rollback về savepoint; COMMIT kết thúc transaction với phần thay đổi còn lại.

SAVEPOINT không tạo transaction độc lập. Nó chỉ là mốc bên trong transaction hiện tại.

### 2.4. SAVEPOINT bị mất khi transaction commit

COMMIT kết thúc transaction và loại bỏ savepoint. DDL có implicit commit nên cũng phá ranh giới savepoint hiện tại.

Không thiết kế một workflow dựa vào SAVEPOINT rồi thực hiện DDL với kỳ vọng có thể quay lại savepoint sau đó.

## 3. DML và DDL có transaction semantics khác nhau

DML thay đổi dữ liệu trong bảng:

- INSERT
- UPDATE
- DELETE
- MERGE
- Một số thao tác DML khác theo SQL semantics

DDL thay đổi cấu trúc hoặc metadata database:

- CREATE TABLE
- ALTER TABLE
- DROP TABLE
- CREATE INDEX
- TRUNCATE TABLE
- CREATE/ALTER/DROP VIEW
- CREATE/ALTER/DROP PROCEDURE hoặc PACKAGE
- GRANT và REVOKE
- Nhiều câu lệnh quản trị object khác

Trong Oracle, DDL có quy tắc implicit commit. Đây là điểm đặc biệt quan trọng khi viết migration, stored procedure và integration test.

### 3.1. Quy tắc implicit commit của Oracle

Với một DDL statement hợp lệ về cú pháp, Oracle thực hiện implicit COMMIT trước khi thực thi DDL. Khi DDL thành công, Oracle thực hiện commit sau statement đó.

Hệ quả:

1. DML chưa commit trước DDL được commit trước khi DDL chạy.
2. DDL thành công được hoàn tất như một thao tác riêng.
3. ROLLBACK sau DDL không thể hoàn tác DML đã commit trước DDL hoặc DDL đã thành công.
4. Savepoint của transaction trước đó không còn dùng được sau commit.
5. Nếu DDL thất bại, không được giả định DML trước nó vẫn có thể rollback; commit trước DDL đã xảy ra.

Quy tắc này khác với một số database khác. Không mang giả định transaction của PostgreSQL, SQL Server hoặc H2 sang Oracle mà không kiểm tra.

### 3.2. Ví dụ DDL commit DML trước đó

Giả sử bảng TX_PROBE đã được tạo từ trước:

~~~sql
DELETE FROM tx_probe;
COMMIT;

INSERT INTO tx_probe(id, note)
VALUES (1, 'DML before DDL');

CREATE TABLE ddl_probe (
    id NUMBER PRIMARY KEY
);

ROLLBACK;

SELECT id, note
FROM tx_probe
WHERE id = 1;
~~~

Kết quả vẫn có hàng ID = 1. INSERT đã được commit trước khi CREATE TABLE chạy. ROLLBACK sau đó không thể lấy lại transaction boundary cũ.

CREATE TABLE thành công cũng được commit. Vì vậy, DDL_PROBE vẫn tồn tại sau ROLLBACK.

### 3.3. DDL thất bại cũng có thể làm commit DML trước đó

Giả sử có DML chưa commit rồi thực hiện một DDL statement hợp lệ về cú pháp nhưng thất bại khi thực thi, ví dụ do object name đã tồn tại hoặc thiếu privilege.

Oracle đã thực hiện implicit commit trước khi thực thi DDL. Do đó DML trước DDL có thể đã được commit dù DDL không thành công.

Đây là lý do không dùng DDL như một thao tác thử trong transaction nghiệp vụ. Nếu cần kiểm tra schema/object, hãy dùng query metadata hoặc chạy DDL trong schema test riêng.

### 3.4. DDL trong PL/SQL vẫn có tác động

DDL không thể viết trực tiếp như một câu SQL tĩnh trong PL/SQL block thông thường; thường dùng dynamic SQL:

~~~sql
BEGIN
    EXECUTE IMMEDIATE
        'CREATE TABLE runtime_probe (id NUMBER)';
END;
/
~~~

Việc đưa DDL vào EXECUTE IMMEDIATE không biến nó thành DML transactional. Quy tắc implicit commit của DDL vẫn áp dụng.

Một procedure chứa DDL có thể commit transaction của caller ngoài dự kiến. Không gọi procedure loại này giữa một business transaction cần atomicity nếu chưa thiết kế rõ ranh giới.

## 4. DELETE, TRUNCATE và DROP không giống nhau

Ba lệnh có thể làm bảng mất dữ liệu nhưng semantics khác nhau:

| Lệnh | Loại | Có thể rollback dữ liệu đã xóa? | Ý nghĩa |
|---|---|---:|---|
| DELETE | DML | Có, trước COMMIT | Xóa hàng theo predicate hoặc toàn bảng |
| TRUNCATE TABLE | DDL | Không | Xóa toàn bộ hàng bằng thao tác DDL |
| DROP TABLE | DDL | Không bằng ROLLBACK thông thường | Xóa object/table khỏi schema |

### 4.1. DELETE có thể rollback

~~~sql
DELETE FROM staging_orders
WHERE batch_id = 9001;

ROLLBACK;
~~~

Các hàng được xóa bởi DELETE được khôi phục khi rollback transaction trước commit.

### 4.2. TRUNCATE không thể rollback

~~~sql
TRUNCATE TABLE staging_orders;
~~~

TRUNCATE là DDL trong Oracle. Nó gây implicit commit và không thể khôi phục dữ liệu bằng ROLLBACK thông thường.

Nếu cần xóa dữ liệu có khả năng rollback, dùng DELETE hoặc thiết kế partition maintenance/recovery phù hợp. TRUNCATE thường nhanh và ít redo/undo hơn DELETE cho trường hợp xóa toàn bộ, nhưng phải hiểu tác động transaction.

### 4.3. DROP TABLE không phải DELETE

DROP TABLE xóa object. Không thể dùng ROLLBACK để phục hồi table vừa drop. Oracle có thể hỗ trợ Flashback Drop qua recycle bin trong điều kiện phù hợp, nhưng đó là cơ chế recovery riêng, không phải transaction rollback.

Không dùng DROP/CREATE để reset dữ liệu trong test đang chạy trong một transaction và mong Spring tự rollback toàn bộ.

## 5. Kiểm thử transaction bằng SQL thuần

Trước khi kiểm thử qua framework, hiểu hành vi database bằng một bảng probe trong schema lab.

~~~sql
CREATE TABLE tx_probe (
    id      NUMBER PRIMARY KEY,
    note    VARCHAR2(100)
);
~~~

Tạo bảng một lần trước các test. Không tạo lại bảng trong transaction mà test đang muốn rollback.

### 5.1. Test commit

~~~sql
INSERT INTO tx_probe(id, note)
VALUES (10, 'commit case');

COMMIT;

SELECT *
FROM tx_probe
WHERE id = 10;
~~~

Hàng phải còn sau khi session kết thúc.

### 5.2. Test rollback

~~~sql
INSERT INTO tx_probe(id, note)
VALUES (11, 'rollback case');

ROLLBACK;

SELECT *
FROM tx_probe
WHERE id = 11;
~~~

Không có hàng ID = 11.

### 5.3. Test savepoint

~~~sql
INSERT INTO tx_probe(id, note)
VALUES (12, 'before savepoint');

SAVEPOINT s1;

INSERT INTO tx_probe(id, note)
VALUES (13, 'after savepoint');

ROLLBACK TO s1;

COMMIT;

SELECT id
FROM tx_probe
WHERE id IN (12, 13)
ORDER BY id;
~~~

Chỉ hàng ID = 12 tồn tại.

### 5.4. Test implicit commit

~~~sql
INSERT INTO tx_probe(id, note)
VALUES (14, 'before DDL');

CREATE TABLE tx_ddl_probe (
    id NUMBER
);

ROLLBACK;

SELECT *
FROM tx_probe
WHERE id = 14;
~~~

Hàng ID = 14 vẫn tồn tại vì INSERT được commit trước DDL. Table TX_DDL_PROBE cũng tồn tại sau ROLLBACK.

Chạy ví dụ trong schema lab. DROP table probe là DDL và sẽ commit transaction hiện tại; dọn dẹp trong bước riêng, sau khi xác nhận không còn test khác sử dụng object.

## 6. Transaction boundary trong Spring Boot

Spring quản lý transaction thông qua PlatformTransactionManager, thường là JpaTransactionManager cho JPA hoặc DataSourceTransactionManager/JdbcTransactionManager cho JDBC.

Ví dụ:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final PaymentRepository paymentRepository;

    public OrderService(
            OrderRepository orderRepository,
            PaymentRepository paymentRepository) {
        this.orderRepository = orderRepository;
        this.paymentRepository = paymentRepository;
    }

    @Transactional
    public void payOrder(long orderId) {
        OrderEntity order = orderRepository.findById(orderId)
            .orElseThrow();

        order.markPaid();

        paymentRepository.save(
            PaymentEntity.forOrder(orderId)
        );
    }
}
~~~

Nếu method hoàn tất bình thường, Spring transaction interceptor commit. Nếu method ném exception thuộc loại rollback rule, transaction rollback.

### 6.1. Default rollback rules

Theo mặc định phổ biến của Spring:

- RuntimeException: rollback.
- Error: rollback.
- Checked exception: không tự động rollback, trừ khi cấu hình rollback rule.

Ví dụ nếu business method ném checked exception và muốn rollback:

~~~java
@Transactional(rollbackFor = Exception.class)
public void importOrders() throws Exception {
    // Database changes.
}
~~~

Có thể cấu hình noRollbackFor cho một số exception, nhưng phải cân nhắc kỹ vì caller có thể nhận lỗi trong khi database đã commit.

Không giả định mọi exception đều tự động rollback.

### 6.2. Propagation REQUIRED

REQUIRED là propagation mặc định. Method tham gia transaction hiện có hoặc tạo transaction mới nếu chưa có.

~~~java
@Transactional
public void processOrder() {
    updateOrder();
    createPayment();
}
~~~

Nếu updateOrder và createPayment đều tham gia cùng transaction manager/context, chúng có thể cùng commit hoặc rollback.

### 6.3. REQUIRES_NEW

REQUIRES_NEW tạm ngưng transaction hiện tại và chạy một transaction độc lập mới:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditRecord() {
    auditRepository.save(...);
}
~~~

Transaction REQUIRES_NEW có thể commit độc lập. Nếu transaction bên ngoài rollback, audit record đã commit vẫn còn.

Đây có thể là chủ đích cho audit/telemetry, nhưng không dùng cho dữ liệu nghiệp vụ phải rollback cùng transaction cha.

### 6.4. NESTED và savepoint

Propagation NESTED có thể dùng savepoint nếu transaction manager và resource hỗ trợ. Không mặc định JpaTransactionManager hỗ trợ nested transaction theo đúng cách ứng dụng mong muốn.

Nếu cần savepoint, xác nhận transaction manager, JDBC connection và driver. Test rollback tới savepoint trên Oracle thật.

## 7. Những trường hợp @Transactional không hoạt động như mong đợi

### 7.1. Self-invocation

Spring proxy thường áp dụng @Transactional khi method được gọi qua proxy. Gọi một method transactional khác từ method trong cùng object có thể không đi qua proxy:

~~~java
@Service
public class ImportService {

    public void runImport() {
        saveBatch(); // self-invocation, may bypass proxy
    }

    @Transactional
    public void saveBatch() {
        // Expected transaction may not be created.
    }
}
~~~

Tách method transactional sang bean khác hoặc gọi qua proxy theo kiến trúc rõ ràng. Không dựa vào annotation nếu đường gọi thực tế không đi qua transaction interceptor.

### 7.2. Thread boundary

Transaction context thông thường gắn với thread. Khi dùng @Async, executor hoặc tạo thread mới, transaction không tự truyền sang thread khác.

~~~java
@Transactional
public void process() {
    executor.execute(() -> repository.save(...));
}
~~~

Lệnh save trong thread khác có thể chạy trong transaction riêng hoặc auto-commit theo cấu hình. Thiết kế worker có transaction boundary riêng và truyền ID/data, không truyền EntityManager/Connection đang dùng.

### 7.3. Method visibility và proxy mode

Cách Spring xử lý method annotation phụ thuộc proxy mode, interface/class proxy và phiên bản. Public service method được gọi từ bean khác là pattern dễ dự đoán nhất.

Kiểm tra transaction manager và proxy configuration thực tế. Không dựa vào annotation đặt trên private helper method như thể mọi lời gọi đều được intercept.

### 7.4. Nhiều transaction manager

Ứng dụng có thể có nhiều DataSource hoặc transaction manager. @Transactional cần chỉ rõ manager phù hợp khi có nhiều manager:

~~~java
@Transactional(transactionManager = "oracleTransactionManager")
public void updateOracleData() {
    // Oracle work.
}
~~~

Nếu JPA repository dùng Oracle DataSource nhưng JDBC code tự lấy connection từ một DataSource khác, hai thay đổi không cùng transaction.

## 8. Kiểm thử @Transactional trong Spring Test

Spring Test hỗ trợ test-managed transaction. Test method có @Transactional thường được rollback sau khi test hoàn tất.

~~~java
@SpringBootTest
@Transactional
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void savesOrderInsideTestTransaction() {
        repository.save(new OrderEntity(...));

        assertTrue(repository.findById(...).isPresent());
    }
}
~~~

Sau test, Spring rollback transaction test-managed theo mặc định. Đây là cách tiện để cô lập DML fixture.

Nhưng có một ngoại lệ quan trọng: DDL Oracle có implicit commit. Nếu test chạy CREATE TABLE hoặc TRUNCATE trong transaction, DML fixture trước đó có thể đã commit và không được test rollback.

### 8.1. @Rollback và @Commit

~~~java
@Test
@Transactional
@Rollback
void rollbackByDefault() {
    // Changes rolled back after test.
}
~~~

~~~java
@Test
@Transactional
@Commit
void commitTestChanges() {
    // Changes committed after test.
}
~~~

@Commit tương đương yêu cầu không rollback khi test kết thúc. Chỉ dùng khi test cần dữ liệu tồn tại sau method và có kế hoạch cleanup rõ ràng.

### 8.2. Test không transaction-managed

Một số integration test cần kiểm tra transaction boundary thực sự. Có thể dùng @Transactional(propagation = NOT_SUPPORTED) ở test để không bọc toàn bộ method trong test transaction, sau đó dùng TransactionTemplate hoặc service transaction riêng.

Điều này giúp kiểm tra trạng thái sau khi transaction đã commit/rollback thật, thay vì chỉ kiểm tra trong cùng persistence context.

### 8.3. @BeforeEach và @AfterEach

Lifecycle method của Spring Test thường chạy trong test-managed transaction nếu test method có transaction. Dùng @BeforeTransaction và @AfterTransaction khi cần thao tác trước/sau test transaction.

Đừng chạy DDL tạo fixture trong @BeforeEach rồi tin rằng rollback sau test sẽ dọn sạch. DDL có thể commit transaction.

### 8.4. Preemptive timeout

Một số test framework thực hiện preemptive timeout bằng cách chạy test body trên thread khác. Vì Spring transaction context gắn với thread, test body có thể chạy ngoài transaction mà Spring Test đã mở.

Nếu dùng timeout, hiểu cách framework thực thi và xác nhận thread/transaction. Không để test rollback tạo cảm giác an toàn giả.

## 9. Flush không phải commit

JPA persistence context có thể giữ thay đổi trong memory trước khi gửi SQL xuống database.

~~~java
OrderEntity order = entityManager.find(OrderEntity.class, orderId);
order.setStatus("PAID");

entityManager.flush();
~~~

flush() đồng bộ thay đổi pending xuống database trong transaction hiện tại. Nó không commit transaction.

Sau flush:

- SQL đã được gửi tới database.
- Constraint và trigger có thể được thực thi.
- Transaction vẫn có thể rollback.
- Lock có thể vẫn được giữ.
- Thay đổi chưa bền vững với transaction khác cho tới commit theo isolation semantics.

### 9.1. Vì sao test cần flush?

Nếu test chỉ gọi repository.save() rồi assert object trong memory, test có thể không thực sự kiểm tra SQL/database behavior.

Để kiểm tra constraint hoặc SQL mapping:

~~~java
repository.save(entity);
entityManager.flush();
~~~

Sau đó có thể clear persistence context và query lại để xác minh dữ liệu thực sự được lưu:

~~~java
entityManager.clear();
OrderEntity reloaded = repository.findById(id).orElseThrow();
~~~

flush giúp phát hiện lỗi DML sớm. clear làm entity managed bị detach; lần query tiếp theo sẽ lấy state mới từ database.

### 9.2. Lỗi có thể xảy ra ở flush hoặc commit

Constraint thông thường có thể lỗi khi SQL được flush. Constraint DEFERRABLE được đặt deferred có thể chỉ được kiểm tra tại COMMIT.

Do đó, test chỉ gọi flush chưa chắc đã kiểm tra toàn bộ commit behavior.

Trong Oracle, có thể khai báo constraint deferrable và đặt trạng thái deferred trong transaction:

~~~sql
SET CONSTRAINTS ALL DEFERRED;
~~~

Chỉ các constraint được khai báo DEFERRABLE mới có thể trì hoãn kiểm tra theo cơ chế này. Test phải commit để xác nhận lỗi deferred constraint thực sự xuất hiện.

## 10. Kiểm thử rollback thật bằng TransactionTemplate

Để chứng minh dữ liệu không tồn tại sau rollback, hãy kiểm tra trong transaction khác sau khi transaction đầu tiên kết thúc.

Ví dụ:

~~~java
@SpringBootTest
class TransactionRollbackTest {

    @Autowired
    TransactionTemplate transactionTemplate;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void rollsBackInsertedRow() {
        long id = 900001L;

        transactionTemplate.executeWithoutResult(status -> {
            jdbcTemplate.update(
                "insert into tx_probe(id, note) values (?, ?)",
                id,
                "rollback-test"
            );

            status.setRollbackOnly();
        });

        Integer count = jdbcTemplate.queryForObject(
            "select count(*) from tx_probe where id = ?",
            Integer.class,
            id
        );

        assertEquals(0, count);
    }
}
~~~

Test này cần chạy ngoài một transaction test-managed khác để TransactionTemplate tạo và kết thúc transaction độc lập. Có thể dùng @Transactional(propagation = NOT_SUPPORTED) ở test class/method nếu cần.

Bảng TX_PROBE phải được tạo trước test bằng migration hoặc schema setup ngoài transaction đang kiểm tra.

### 10.1. Kiểm tra commit

~~~java
transactionTemplate.executeWithoutResult(status -> {
    jdbcTemplate.update(
        "insert into tx_probe(id, note) values (?, ?)",
        id,
        "commit-test"
    );
});

Integer count = jdbcTemplate.queryForObject(
    "select count(*) from tx_probe where id = ?",
    Integer.class,
    id
);

assertEquals(1, count);
~~~

Không gọi setRollbackOnly. Khi callback hoàn tất bình thường, TransactionTemplate commit theo cấu hình.

### 10.2. Kiểm tra exception rollback

~~~java
assertThrows(IllegalStateException.class, () ->
    transactionTemplate.executeWithoutResult(status -> {
        jdbcTemplate.update(
            "insert into tx_probe(id, note) values (?, ?)",
            id,
            "exception-test"
        );

        throw new IllegalStateException("force rollback");
    })
);
~~~

Sau đó query trong transaction khác để xác nhận hàng không tồn tại.

### 10.3. Kiểm tra checked exception

Spring default không rollback checked exception theo quy tắc thông thường. Kiểm tra annotation:

~~~java
@Transactional(rollbackFor = Exception.class)
public void importBatch() throws Exception {
    repository.save(...);
    throw new Exception("import failed");
}
~~~

Test cần chứng minh checked exception có rollback theo cấu hình mong muốn. Không chỉ kiểm tra exception được ném.

## 11. Kiểm thử implicit commit bằng Oracle thật

Đây là test đặc biệt quan trọng vì H2 hoặc mock có thể không phản ánh đúng Oracle DDL semantics.

Chuẩn bị trước:

~~~sql
CREATE TABLE tx_ddl_probe (
    id NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);
~~~

Test trong một schema lab riêng:

~~~java
@Test
void oracleDdlCommitsPendingDml() {
    long id = 900101L;

    transactionTemplate.executeWithoutResult(status -> {
        jdbcTemplate.update(
            "insert into tx_ddl_probe(id, note) values (?, ?)",
            id,
            "dml-before-ddl"
        );

        jdbcTemplate.execute(
            "create table ddl_commit_marker (id number)"
        );

        status.setRollbackOnly();
    });

    Integer count = jdbcTemplate.queryForObject(
        "select count(*) from tx_ddl_probe where id = ?",
        Integer.class,
        id
    );

    assertEquals(1, count);
}
~~~

Kết quả mong đợi trên Oracle: hàng được INSERT vẫn tồn tại vì CREATE TABLE đã implicit commit transaction trước DDL. setRollbackOnly không thể đảo ngược commit đã xảy ra ở database.

Test này phải chạy trong schema/database cô lập vì nó tạo object thật. Sau test, cleanup hàng bằng DML trong transaction riêng và drop marker table ở bước cleanup riêng. DROP TABLE cũng là DDL và có implicit commit.

### 11.1. Tại sao Spring không ngăn được implicit commit?

Spring transaction manager quản lý transaction qua JDBC/JPA connection. Nhưng Oracle thực thi quy tắc implicit commit bên trong database khi nhận DDL.

Spring không thể biến DDL thành transactional DML. Transaction manager có thể vẫn nghĩ transaction đang mở trong khi database đã commit nó.

Vì vậy, khi DDL chạy trong transaction Spring:

- Pending DML có thể đã commit.
- DDL thành công được commit.
- Các DML tiếp theo có thể nằm trong một transaction mới trên cùng session.
- Khi Spring kết thúc transaction, rollback chỉ áp dụng phần transaction còn lại, không đảo ngược phần đã commit bởi DDL.

Đây là sự lệch giữa abstraction transaction ở ứng dụng và semantics DDL của Oracle.

### 11.2. Không dùng H2 làm bằng chứng Oracle DDL behavior

H2 có chế độ tương thích Oracle nhưng không phải Oracle Database. DDL transaction semantics, PL/SQL, data dictionary, sequence, lock và driver behavior có thể khác.

Test implicit commit phải chạy trên Oracle version gần production. H2 vẫn hữu ích cho một số unit test, nhưng không thay thế integration test cho Oracle semantics.

## 12. Kiểm thử TRUNCATE và DELETE

Một test có thể minh họa sự khác nhau:

~~~sql
-- Chuẩn bị dữ liệu trước test.
INSERT INTO tx_probe(id, note) VALUES (20, 'keep');
COMMIT;

-- DELETE có thể rollback.
DELETE FROM tx_probe WHERE id = 20;
ROLLBACK;

SELECT COUNT(*) FROM tx_probe WHERE id = 20;
-- Expected: 1

-- TRUNCATE là DDL, không rollback được.
TRUNCATE TABLE tx_probe;

ROLLBACK;

SELECT COUNT(*) FROM tx_probe WHERE id = 20;
-- Expected: 0
~~~

Không chạy TRUNCATE trên bảng fixture dùng chung. Nó ảnh hưởng tất cả test/session và không thể được hoàn tác bằng transaction rollback.

Nếu cần reset bảng test:

- Dùng schema riêng cho test.
- Dùng bảng tạm hoặc dữ liệu có test key.
- Dùng DELETE theo test identifier khi cần rollback.
- Tạo lại schema/container giữa test suite nếu môi trường hỗ trợ.
- Đặt DDL setup/teardown ngoài transaction nghiệp vụ.

## 13. DDL trong Flyway và Liquibase

Database migration thường chứa DDL như CREATE TABLE, ALTER TABLE, CREATE INDEX và constraint changes.

Với Oracle, DDL implicit commit có nghĩa migration chứa DDL không thể được xem như một transaction có thể rollback toàn bộ bằng ROLLBACK thông thường.

### 13.1. Flyway

Flyway quản lý version và thứ tự migration. Transaction behavior phụ thuộc database và loại statement; Oracle DDL tự commit dù tool cố chạy migration trong transaction.

Vì vậy:

- Không giả định migration DDL thất bại sẽ rollback toàn bộ thay đổi trước đó.
- Thiết kế migration nhỏ, có thể kiểm tra trạng thái trước/sau.
- Dùng idempotent/guarded operation khi phù hợp.
- Nếu migration dừng giữa chừng, có runbook sửa schema rồi repair/version state theo quy trình.
- Không tự chạy lại script có DDL không idempotent khi chưa xác định statement nào đã thành công.

### 13.2. Liquibase

Liquibase có thuộc tính runInTransaction cho changeset. Tuy nhiên, runInTransaction không thể vô hiệu hóa implicit commit của Oracle DDL.

Một changeset chứa nhiều DDL có thể hoàn thành một phần trước khi lỗi. Nếu migration tool đánh dấu trạng thái thất bại, database có thể vẫn có một số object đã được tạo.

Tách changeset theo bước nhỏ và thiết kế recovery/forward fix. Kiểm tra bảng DATABASECHANGELOG cùng dictionary để xác định trạng thái thực tế.

### 13.3. Không dùng rollback migration như rollback dữ liệu

Rollback script của migration tool thường là một tập DDL/DML mới nhằm đưa schema về trạng thái tương đương trước đó. Nó không phải rollback transaction gốc của Oracle.

Một DROP/ALTER rollback cũng có thể commit và có thể làm mất dữ liệu mới đã được ghi sau migration. Cần backup, compatibility strategy và forward fix plan.

## 14. Sequence và các side effect không transactional

### 14.1. Sequence không rollback

Ví dụ:

~~~sql
CREATE SEQUENCE order_seq START WITH 1;

SELECT order_seq.NEXTVAL FROM dual;
-- Returns 1

ROLLBACK;

SELECT order_seq.NEXTVAL FROM dual;
-- Returns a later value, not 1
~~~

Sequence được thiết kế để cấp giá trị đồng thời, không đảm bảo không có khoảng trống. NEXTVAL đã lấy không được trả lại khi transaction rollback.

Cache, instance restart và RAC có thể làm khoảng trống lớn hơn. Không kiểm thử bằng giả định sequence phải liên tục.

Identity column của Oracle cũng dựa trên sequence mechanism và có thể có gap. Không dùng ID liên tục làm bằng chứng transaction commit.

### 14.2. Autonomous transaction

PL/SQL có thể khai báo autonomous transaction:

~~~sql
CREATE OR REPLACE PROCEDURE write_audit(
    p_message IN VARCHAR2
)
IS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO audit_log(message, created_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
END;
/
~~~

Autonomous transaction độc lập với transaction caller. Nếu transaction nghiệp vụ rollback, audit record đã commit vẫn tồn tại.

Điều này hữu ích cho một số loại audit/diagnostic cần giữ lại dù operation thất bại. Nhưng cần ghi rõ audit đang ghi attempt, error hay business event đã commit; không để audit record gây hiểu nhầm rằng nghiệp vụ đã thành công.

Autonomous routine phải kết thúc transaction của chính nó bằng COMMIT hoặc ROLLBACK; nếu không, có thể phát sinh lỗi khi routine kết thúc.

### 14.3. External side effects

ROLLBACK của Oracle không thể hoàn tác:

- HTTP request đã được remote service xử lý.
- Email đã gửi.
- File đã ghi lên filesystem.
- Message đã publish tới broker.
- Payment gateway đã charge.
- Một transaction ở database khác đã commit độc lập.

Đối với workflow có external side effect, dùng outbox, idempotency key, saga/compensation hoặc distributed transaction phù hợp. Không đặt HTTP call vào giữa transaction database rồi giả định rollback sẽ đảo ngược remote effect.

## 15. Kiểm thử transaction với native query và stored procedure

Stored procedure chạy trên cùng database session có thể tham gia transaction của caller, miễn là procedure không tự COMMIT/ROLLBACK và không có autonomous transaction.

Ví dụ procedure:

~~~sql
CREATE OR REPLACE PROCEDURE update_order_status(
    p_order_id IN NUMBER,
    p_status   IN VARCHAR2
)
IS
BEGIN
    UPDATE orders
       SET status = p_status
     WHERE order_id = p_order_id;
END;
/
~~~

Nếu Spring gọi procedure trong cùng transaction, caller có thể rollback UPDATE.

Nhưng nếu procedure chứa:

~~~sql
COMMIT;
~~~

thì transaction caller bị commit. ROLLBACK từ Spring không thể undo phần đó.

### 15.1. Test procedure tham gia transaction

1. Bắt đầu transaction.
2. Gọi procedure cập nhật dữ liệu.
3. Đọc trạng thái trong transaction.
4. Đánh dấu rollback.
5. Kết thúc transaction.
6. Query từ transaction mới.
7. Xác nhận dữ liệu trở về trạng thái ban đầu.

### 15.2. Test procedure có COMMIT

Tạo procedure test riêng có COMMIT. Gọi trong TransactionTemplate rồi đánh dấu rollback. Query ở transaction mới để chứng minh thay đổi đã được procedure commit vẫn còn.

Không dùng procedure tự commit cho business operation cần atomicity với các repository method khác.

### 15.3. Native DML

Native query update/delete cũng tham gia transaction hiện tại nếu dùng cùng connection/context. Nhưng persistence context có thể stale.

~~~java
entityManager.flush();

entityManager.createNativeQuery(
    "update orders set status = 'CLOSED' where order_id = :id"
).setParameter("id", orderId)
 .executeUpdate();

entityManager.clear();
~~~

Sau clear, query tiếp theo load state từ database. Flush trước nếu cần gửi các thay đổi entity pending trước native DML; clear sau nếu không muốn giữ managed object stale.

## 16. Kiểm thử constraint và lỗi ở thời điểm commit

Không phải mọi lỗi đều xuất hiện ngay khi gọi save().

### 16.1. Constraint immediate

Các constraint thông thường có thể được kiểm tra khi statement thực thi/flush:

- PRIMARY KEY.
- UNIQUE.
- NOT NULL.
- FOREIGN KEY.
- CHECK.

Ví dụ duplicate key có thể gây ORA-00001. Vi phạm foreign key có thể gây ORA-02291 hoặc ORA-02292.

Trong JPA test, gọi flush để phát hiện lỗi tại điểm dự kiến:

~~~java
entityManager.persist(entity);
assertThrows(PersistenceException.class, entityManager::flush);
~~~

Loại exception cụ thể có thể được Spring/Hibernate wrap. Assert theo root cause/vendor code khi cần.

### 16.2. Deferred constraint

Oracle cho phép một số constraint DEFERRABLE được kiểm tra ở cuối transaction khi deferred.

~~~sql
ALTER TABLE child_orders
ADD CONSTRAINT child_orders_parent_fk
FOREIGN KEY (parent_id)
REFERENCES parent_orders(parent_id)
DEFERRABLE INITIALLY DEFERRED;
~~~

Trong transaction:

~~~sql
SET CONSTRAINTS ALL DEFERRED;

INSERT INTO child_orders(child_id, parent_id)
VALUES (1, 999);

-- Có thể chưa lỗi ở statement này.
COMMIT;
-- Constraint được kiểm tra tại commit.
~~~

Test chỉ flush có thể không phát hiện lỗi deferred. Phải test commit thực sự.

Không phải mọi constraint đều có thể DEFERRABLE; kiểm tra DDL và dictionary metadata.

## 17. Kiểm thử concurrency và locking

Transaction test không chỉ kiểm tra commit/rollback một session. Cần kiểm tra hai transaction cạnh tranh khi nghiệp vụ phụ thuộc locking.

### 17.1. SELECT FOR UPDATE

Oracle khóa hàng khi dùng SELECT FOR UPDATE cho tới COMMIT hoặc ROLLBACK.

~~~sql
SELECT balance
FROM accounts
WHERE account_id = 10
FOR UPDATE;
~~~

Test concurrency nên dùng hai connection/session riêng:

1. Transaction A SELECT FOR UPDATE.
2. Transaction B thử UPDATE cùng row.
3. B chờ hoặc nhận lỗi theo timeout/locking clause.
4. A commit hoặc rollback.
5. B tiếp tục hoặc thất bại theo kết quả.

Không dùng cùng một JDBC Connection cho cả hai transaction; chúng sẽ không mô phỏng concurrency độc lập.

### 17.2. NOWAIT và WAIT

~~~sql
SELECT *
FROM accounts
WHERE account_id = 10
FOR UPDATE NOWAIT;
~~~

NOWAIT không chờ lock nếu row đã bị khóa; có thể nhận ORA-00054.

Có thể dùng WAIT n để chờ một khoảng thời gian theo cú pháp Oracle. Kiểm thử cả success và lock contention.

### 17.3. Deadlock

Nếu hai transaction khóa tài nguyên theo thứ tự ngược nhau, Oracle có thể phát hiện deadlock và trả ORA-00060.

Test deadlock trong môi trường lab với hai session và barrier đồng bộ, không dùng sleep tùy tiện để phỏng đoán thời điểm. Ứng dụng cần xử lý transaction bị hủy và chỉ retry khi operation an toàn.

### 17.4. Optimistic locking

JPA @Version phát hiện lost update trong entity-managed update. Test hai transaction cùng đọc một version, transaction đầu commit, transaction sau thử update và nhận optimistic locking failure.

Nếu native SQL hoặc procedure sửa dữ liệu, chúng phải duy trì version column nếu ứng dụng dựa vào optimistic locking.

## 18. Isolation level và snapshot

Oracle mặc định READ COMMITTED. Mỗi câu SELECT thường đọc một consistent snapshot tại thời điểm statement bắt đầu, không phải snapshot cố định cho toàn transaction.

### 18.1. READ COMMITTED

Một transaction có thể chạy hai SELECT giống nhau nhưng thấy kết quả khác nếu transaction khác commit giữa hai câu lệnh.

Test cần xác định điều đó có phù hợp nghiệp vụ không.

### 18.2. SERIALIZABLE

Serializable cung cấp transaction-level consistency theo semantics Oracle, nhưng concurrent write conflict có thể dẫn tới ORA-08177: can't serialize access for this transaction.

Ứng dụng cần xử lý retry toàn transaction khi phù hợp. Không chỉ retry riêng câu UPDATE cuối vì transaction snapshot và các quyết định trước đó có thể đã cũ.

### 18.3. Isolation trong Spring

~~~java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void processOrder() {
    // Work in the current transaction.
}
~~~

Isolation setting có thể chỉ được áp dụng khi transaction mới được tạo; nếu method tham gia transaction đã tồn tại, behavior phụ thuộc transaction manager. Kiểm tra propagation và actual database session.

## 19. Test fixture và schema lifecycle

Một test tốt phải bắt đầu từ trạng thái dữ liệu xác định và kết thúc không làm bẩn test khác.

### 19.1. Tách schema test

Khuyến nghị:

- Schema riêng cho integration test.
- Migration setup chạy trước test suite.
- Seed data có ID/key riêng.
- Test DML dùng rollback hoặc cleanup theo ID.
- DDL setup/teardown chạy ngoài transaction test.
- Không chạy TRUNCATE/DROP trên schema dùng chung nhiều worker.
- Mỗi test song song có namespace hoặc schema độc lập.

### 19.2. Dùng Testcontainers hoặc Oracle test database

H2 có thể hữu ích cho logic repository đơn giản nhưng không thay Oracle khi kiểm thử:

- Implicit commit của DDL.
- PL/SQL package.
- Oracle sequence/identity behavior.
- REF CURSOR.
- Oracle datatype.
- Locking và isolation.
- Optimizer hint.
- Data dictionary.
- Oracle JDBC driver.

Dùng Oracle container/image phù hợp với license và môi trường CI, hoặc database test do tổ chức cung cấp. Pin image/database version gần production.

### 19.3. Test song song

Nếu nhiều test cùng dùng một schema:

- DDL test có thể commit transaction của test khác nếu dùng chung session? DDL commit áp dụng session transaction của chính connection, nhưng DDL trên object chung có thể gây lock/ảnh hưởng dữ liệu test khác.
- TRUNCATE/DROP có thể xóa object/dữ liệu mà test khác đang dùng.
- Sequence dùng chung không đảm bảo ID liền nhau.
- Cleanup theo predicate rộng có thể xóa dữ liệu của test khác.

Tốt nhất dùng schema/database isolation hoặc tên object/data namespace riêng.

## 20. Kiểm thử migration DDL

Migration test cần xác minh cả schema trước và sau, không chỉ trạng thái tool.

Ví dụ migration:

~~~sql
ALTER TABLE orders ADD source_system VARCHAR2(30);

CREATE INDEX idx_orders_source
ON orders(source_system);
~~~

Các câu DDL có thể commit độc lập theo Oracle semantics. Nếu câu thứ hai lỗi, cột từ câu đầu có thể vẫn tồn tại.

### 20.1. Test migration failure

1. Tạo schema ở version trước migration.
2. Chạy migration trong database Oracle test.
3. Cố ý tạo điều kiện lỗi ở một bước trong migration test.
4. Kiểm tra object nào đã được tạo/thay đổi.
5. Kiểm tra trạng thái migration tool.
6. Xây dựng forward fix hoặc cleanup script.
7. Chạy lại từ trạng thái thực tế, không giả định database đã rollback sạch.

Không cố tình làm migration lỗi trong production để kiểm tra behavior.

### 20.2. Expand-contract

Đối với thay đổi schema có ứng dụng đang chạy:

1. Expand: thêm column/table/index tương thích.
2. Deploy ứng dụng có thể đọc/ghi cả schema cũ và mới.
3. Backfill dữ liệu theo batch có thể resume.
4. Chuyển traffic/logic sang schema mới.
5. Contract: xóa column/object cũ ở release sau khi không còn consumer.

Cách này giảm yêu cầu rollback DDL tức thời. Với DDL đã commit, forward-compatible migration thường an toàn hơn cố hoàn nguyên cấu trúc và dữ liệu.

## 21. Kiểm thử rollback khi có nhiều side effect

Một transaction nghiệp vụ có thể bao gồm:

- DML trong Oracle.
- Gọi REST API.
- Gửi email.
- Publish message.
- Ghi file.
- Ghi audit qua autonomous transaction.

Rollback Oracle chỉ hoàn tác phần DML transactional cùng transaction đó.

### 21.1. Ví dụ lỗi phối hợp

~~~text
BEGIN DATABASE TRANSACTION
    UPDATE ORDERS
    INSERT PAYMENT
    CALL EXTERNAL PAYMENT API
    API succeeds
    INSERT fails
ROLLBACK DATABASE
~~~

Database có thể rollback ORDER và PAYMENT, nhưng payment gateway đã charge tiền. Hệ thống bị lệch giữa database và external service.

### 21.2. Outbox pattern

Ghi business change và event vào outbox trong cùng transaction:

~~~text
Transaction:
    UPDATE ORDERS
    INSERT OUTBOX_EVENT
    COMMIT

Worker:
    Read pending event
    Call remote service with idempotency key
    Mark event delivered
~~~

Nếu worker crash sau khi remote service xử lý nhưng trước khi đánh dấu delivered, event có thể được gửi lại. Remote service cần idempotency hoặc consumer phải deduplicate.

### 21.3. Saga/compensation

Một số workflow phân tán dùng compensation thay vì rollback xuyên hệ thống. Ví dụ nếu payment đã charge nhưng bước fulfillment thất bại, gọi refund operation theo business contract.

Compensation là một nghiệp vụ mới, không phải rollback transaction gốc. Nó cũng có thể thất bại và cần retry/monitoring.

## 22. Các lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Test @Transactional vẫn để lại dữ liệu | DDL implicit commit, @Commit, REQUIRES_NEW hoặc procedure COMMIT | Xem SQL/transaction boundary và DDL |
| DML trước CREATE TABLE không rollback | Oracle commit trước DDL | Tách DDL khỏi transaction test |
| DELETE rollback được nhưng TRUNCATE không | DELETE là DML, TRUNCATE là DDL | Kiểm tra loại statement |
| Spring không rollback khi checked exception | Default rollback rules | rollbackFor hoặc exception design |
| @Transactional không hoạt động | Self-invocation/proxy/thread boundary | Kiểm tra call path và transaction manager |
| Repository save chưa thấy SQL | JPA chưa flush | Gọi flush trong test |
| Entity vẫn có dữ liệu cũ sau procedure | Persistence context stale | refresh/clear và query lại |
| Procedure commit làm hỏng atomicity | COMMIT trong PL/SQL | Review procedure source |
| Sequence bị gap sau rollback | Sequence không transactional | Không assert ID liên tục |
| Audit còn sau rollback | Autonomous transaction | Kiểm tra PRAGMA AUTONOMOUS_TRANSACTION |
| External payment vẫn tồn tại sau rollback | Side effect ngoài DB | Outbox/idempotency/compensation |
| Deferred constraint chỉ lỗi khi kết thúc | Kiểm tra tại COMMIT | Test commit thật |
| ORA-00060 | Deadlock | Phân tích lock order và transaction |
| ORA-08177 | Serializable conflict | Retry toàn transaction khi an toàn |
| ORA-00054 | NOWAIT/resource busy | Kiểm tra session đang giữ lock |
| Test pass trên H2 nhưng fail Oracle | Khác biệt dialect/transaction semantics | Oracle integration test |

## 23. Runbook điều tra transaction không rollback

### Bước 1 — Xác định trạng thái mong đợi

Ghi:

- Database và schema.
- Request/test ID.
- Transaction boundary dự kiến.
- Các bảng/object đã thay đổi.
- Exception xảy ra ở bước nào.
- Dữ liệu thực tế sau khi method kết thúc.

### Bước 2 — Xác định commit source

Tìm:

- COMMIT trong PL/SQL package/procedure.
- DDL chạy trực tiếp hoặc qua EXECUTE IMMEDIATE.
- TRUNCATE, CREATE, ALTER, DROP, GRANT, REVOKE.
- Spring @Commit hoặc @Rollback(false).
- REQUIRES_NEW.
- Autonomous transaction.
- JDBC connection auto-commit.
- Transaction manager/DataSource khác nhau.
- Async/thread boundary.

### Bước 3 — Kiểm tra persistence context

- Entity có được load trước native DML không?
- Có flush pending changes không?
- Có clear/refresh sau procedure không?
- Test có query trong cùng persistence context hay transaction mới?
- Entity có bị detach sau rollback không?

### Bước 4 — Kiểm tra database

Dùng session mới hoặc connection độc lập để query dữ liệu. Không chỉ đọc lại entity trong cùng persistence context.

Nếu nghi DDL, kiểm tra object metadata và DML row state trong schema test.

### Bước 5 — Khắc phục

- Tách DDL khỏi business transaction.
- Loại COMMIT không cần thiết khỏi procedure.
- Căn chỉnh transaction manager/DataSource.
- Bổ sung rollbackFor khi cần.
- Sửa proxy/self-invocation hoặc thread boundary.
- Dùng outbox cho external side effect.
- Bổ sung test Oracle thật.

## 24. Checklist kiểm thử transaction và DDL

### Transaction cơ bản

- [ ] DML commit tồn tại sau transaction.
- [ ] DML rollback không tồn tại sau transaction.
- [ ] SAVEPOINT rollback đúng phần thay đổi.
- [ ] Exception runtime rollback theo contract.
- [ ] Checked exception có rollback rule rõ.
- [ ] Procedure không commit ngoài ý muốn.
- [ ] REQUIRES_NEW được kiểm tra độc lập.

### Oracle DDL

- [ ] Test DDL commit pending DML trước DDL.
- [ ] Test DDL thành công tồn tại sau rollback.
- [ ] Test failed DDL không giả định DML trước đó còn rollback được.
- [ ] Test TRUNCATE khác DELETE.
- [ ] Test DDL dynamic qua EXECUTE IMMEDIATE.
- [ ] Không chạy DDL trong test-managed transaction nếu mong rollback toàn bộ.
- [ ] Migration failure được kiểm tra trên Oracle.

### Spring/JPA

- [ ] @Transactional đi qua proxy.
- [ ] Không mất transaction khi đổi thread/async.
- [ ] DataSource và transaction manager đúng.
- [ ] flush được dùng khi cần kiểm tra SQL/constraint.
- [ ] clear/refresh xử lý persistence context stale.
- [ ] Bulk DML không bỏ sót audit/version/callback.
- [ ] Test rollback được xác minh từ transaction mới.

### Oracle-specific side effects

- [ ] Sequence gap được chấp nhận.
- [ ] Autonomous transaction được review.
- [ ] Deferred constraint được kiểm tra ở commit.
- [ ] Lock/deadlock/concurrency được test.
- [ ] External side effect có idempotency/outbox/compensation.

## 25. Ghi nhớ cốt lõi

- DML như INSERT/UPDATE/DELETE có thể rollback trước COMMIT; COMMIT kết thúc transaction và làm thay đổi bền vững.
- SAVEPOINT cho phép rollback một phần trong cùng transaction; nó không tạo transaction độc lập.
- Oracle thực hiện implicit COMMIT trước DDL hợp lệ về cú pháp và commit sau DDL thành công.
- DML chưa commit trước CREATE/ALTER/DROP/TRUNCATE có thể bị commit trước khi DDL chạy; ROLLBACK sau đó không undo được.
- DDL thất bại không có nghĩa DML trước DDL vẫn rollback được; implicit commit trước DDL đã có thể xảy ra.
- TRUNCATE là DDL và không rollback như DELETE.
- DDL trong EXECUTE IMMEDIATE vẫn giữ semantics implicit commit.
- Spring @Transactional không thể vô hiệu hóa implicit commit do Oracle thực hiện.
- Spring rollback mặc định cho RuntimeException/Error; checked exception cần rollback rule nếu muốn rollback.
- Self-invocation, async/thread boundary và nhiều transaction manager có thể làm transaction không hoạt động như dự kiến.
- JPA flush gửi SQL xuống database nhưng không commit; constraint có thể lỗi ở flush hoặc commit tùy loại.
- Native DML/stored procedure có thể làm entity managed stale; dùng flush, clear hoặc refresh có chủ đích.
- Procedure tự COMMIT có thể phá atomicity với JPA/JDBC transaction bên ngoài.
- REQUIRES_NEW và autonomous transaction commit độc lập; outer rollback không undo được.
- Sequence NEXTVAL không transactional; rollback không trả lại số đã cấp.
- HTTP, email, file và message broker không rollback cùng Oracle; dùng outbox, idempotency hoặc compensation.
- DDL migration trên Oracle cần forward-fix/recovery plan; không giả định tool rollback được DDL.
- Test implicit commit, PL/SQL, locking, sequence và migration phải chạy trên Oracle thật hoặc môi trường Oracle tương thích, không chỉ H2.
- Xác minh rollback từ transaction/connection mới; object trong persistence context không phải bằng chứng database đã commit hay rollback.

### Tài liệu Oracle, Spring và JPA nên đối chiếu

- [Oracle Database Concepts — Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html) — Transaction, commit, rollback, savepoints and consistency.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/) — DDL, DML, TRUNCATE, transaction control and constraint syntax.
- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/) — Dynamic SQL, autonomous transactions and stored program behavior.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html) — @Transactional, propagation, rollback rules and transaction managers.
- [Spring Framework Reference — Testing](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html) — Test-managed transactions, rollback and commit behavior.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — Persistence context, flush, bulk operations, locking and transaction semantics.
- [Spring Boot Reference](https://docs.spring.io/spring-boot/reference/testing/index.html) — Integration testing and database test setup.
- [Flyway Documentation](https://documentation.red-gate.com/flyway) and [Liquibase Documentation](https://docs.liquibase.com/) — Migration execution and recovery practices.

Oracle DDL semantics are database-specific and differ from transactional DDL behavior in other engines. Confirm the deployed Oracle release, Spring transaction manager, JPA provider and JDBC driver; run DDL/rollback integration tests in an isolated Oracle schema before relying on test rollback or migration rollback in production.

