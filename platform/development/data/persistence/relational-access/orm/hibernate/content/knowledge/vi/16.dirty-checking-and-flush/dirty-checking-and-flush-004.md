# Flush khác với commit và không tự kết thúc giao dịch

Trong Hibernate/JPA, `flush()` và `commit()` thường diễn ra gần nhau nhưng không phải hai tên gọi cho cùng một hành động. Khi `flush()` chạy, Hibernate đồng bộ những thay đổi persistent đang chờ thành SQL trong **transaction hiện tại**. Khi `commit()` thành công, database mới xác nhận những thay đổi thuộc transaction đó. Nếu transaction rollback, các thay đổi transactional đã được gửi xuống database bằng flush vẫn có thể bị hủy.

Một sai lầm phổ biến: thấy `INSERT`, `UPDATE` hay `DELETE` trong log ngay sau `entityManager.flush()` rồi kết luận dữ liệu đã được commit, mọi request khác đều nhìn thấy, và transaction đã kết thúc. Không nhận định nào trong số đó tự động đúng.

**Quy tắc cốt lõi: flush không phải commit, không tự kết thúc transaction và không tạo transaction con.** Một giao dịch có thể có nhiều lần flush, rồi commit thành công hoặc rollback toàn bộ các thay đổi transactional của giao dịch.

Bài học này giải thích cơ chế dirty checking, thời điểm flush, transaction isolation, rollback, `@Transactional`, `saveAndFlush()`, flush modes và các tình huống thực tế trong Hibernate.

## 1. Ba lớp trách nhiệm: object, SQL và transaction

Xét entity `InventoryItem`:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 100)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @Version
    private long version;

    protected InventoryItem() {}

    public InventoryItem(String sku, int quantity) {
        if (sku == null || sku.isBlank() || quantity < 0) {
            throw new IllegalArgumentException("Dữ liệu không hợp lệ");
        }
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public long getVersion() {
        return version;
    }

    public void decreaseQuantity(int amount) {
        if (amount <= 0 || amount > quantity) {
            throw new IllegalArgumentException("Không đủ tồn kho");
        }
        quantity -= amount;
    }

    public void increaseQuantity(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số lượng không hợp lệ");
        }
        quantity += amount;
    }
}
~~~

Trong transaction:

~~~java
InventoryItem item = em.find(InventoryItem.class, itemId);
item.decreaseQuantity(3);
em.flush();
~~~

Có ba tầng cần phân biệt:

| Tầng | Công việc | Mốc quan trọng |
| --- | --- | --- |
| **Persistence context** | Giữ entity managed, theo dõi identity, snapshot và pending actions | Khi gọi setter, state Java có thể thay đổi trước SQL |
| **Hibernate/JDBC** | Chuyển pending changes thành SQL và thực thi trên connection | Khi flush hoặc một điểm đồng bộ khác |
| **Database transaction** | Quyết định atomicity, isolation và tính bền vững | Khi commit hoặc rollback |

`item.decreaseQuantity(3)` thay field Java của managed entity. Hibernate có thể phát hiện dirty state. `em.flush()` gửi UPDATE liên quan tới database. Nhưng transaction manager chưa được yêu cầu commit chỉ vì dòng thứ ba chạy.

~~~mermaid
flowchart TD
    A["Entity managed trong persistence context"] --> B["Ứng dụng sửa persistent state"]
    B --> C["Dirty checking / pending actions"]
    C --> D["flush: JDBC INSERT/UPDATE/DELETE"]
    D --> E["Database thực thi SQL trong transaction"]
    E --> F{"Kết thúc transaction?"}
    F -->|"commit thành công"| G["Thay đổi được xác nhận"]
    F -->|"rollback"| H["Thay đổi transactional bị hủy"]
~~~

### 1.1. Dirty checking không phải commit

Hibernate theo dõi entity managed và so sánh trạng thái persistent hoặc sử dụng cơ chế enhancement phù hợp để phát hiện thay đổi. Nếu một entity đang managed:

~~~java
InventoryItem item = em.find(InventoryItem.class, id);
item.decreaseQuantity(1);
~~~

ứng dụng thường không cần gọi `persist()` hoặc `merge()` chỉ để lưu thay đổi. Dirty checking và flush sẽ xử lý khi cần.

Ngược lại, nếu entity đã detached thì sửa object detached không tự tạo pending change của context hiện tại. `flush()` không đi tìm mọi đối tượng Java có ID trong ứng dụng để ghi chúng xuống DB.

### 1.2. Flush xử lý cả INSERT và DELETE

Flush không chỉ tạo UPDATE từ dirty checking. Nó còn đồng bộ những thao tác đã được lên lịch:

~~~java
em.persist(new InventoryItem("SKU-A", 10));
em.remove(existingItem);
em.flush();
~~~

Hibernate có thể cần INSERT, UPDATE, DELETE, xử lý association, version và thứ tự SQL phù hợp với mapping. Một field có `@Transient` hoặc không nằm trong persistent mapping thì không tự được ghi chỉ vì có flush.

## 2. Timeline: flush rồi rollback

Giả sử hàng đang có quantity bằng 20:

~~~text
T0: BEGIN TRANSACTION
T1: SELECT item, quantity = 20
T2: Java giảm quantity xuống 17
T3: flush() → gửi SQL UPDATE, transaction hiện tại thấy 17
T4: Xử lý bước nghiệp vụ tiếp theo
T5: ROLLBACK
T6: Transaction mới đọc lại: quantity = 20
~~~

SQL minh họa về mặt semantics:

~~~sql
BEGIN;

UPDATE inventory_items
SET quantity = 17, version = 2
WHERE id = 10 AND version = 1;

ROLLBACK;
~~~

Các câu lệnh trên mô tả ý nghĩa giao dịch, không phải SQL Hibernate luôn sinh đúng như vậy. Cách BEGIN/COMMIT/ROLLBACK cụ thể được quản lý qua JPA resource-local, JTA hoặc Spring transaction manager.

Điểm quyết định là `ROLLBACK`. Việc UPDATE đã thực thi trong transaction không biến nó thành bản ghi bền vững. Trong database hỗ trợ transaction theo cách thông thường, rollback hoàn tác các thay đổi transactional chưa commit.

### 2.1. Nếu thay rollback bằng commit

~~~text
T0: BEGIN TRANSACTION
T1: Tải item quantity = 20
T2: Sửa quantity = 17
T3: flush() → UPDATE trong transaction
T4: Thực hiện thêm công việc
T5: COMMIT
T6: Transaction khác có thể thấy quantity = 17
~~~

Cùng một flush nhưng kết cục khác nhau chỉ vì transaction cuối cùng commit hay rollback.

### 2.2. Hai lần flush không phải hai lần commit

~~~text
BEGIN TRANSACTION
  Sửa A
  flush()  → SQL cho A
  Sửa B
  flush()  → SQL cho B
COMMIT     → xác nhận cả A và B
~~~

Nếu thay COMMIT bằng ROLLBACK, về nguyên tắc cả các thay đổi transactional của A và B đều bị hoàn tác. Không có ranh giới transaction mới tại một lần flush.

## 3. EntityManager.flush() với transaction resource-local

JPA cung cấp:

~~~java
entityManager.flush();
~~~

Với resource-local transaction, code có thể quản lý:

~~~java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    InventoryItem item = em.find(InventoryItem.class, itemId);
    item.decreaseQuantity(3);

    em.flush(); // Gửi UPDATE, transaction chưa kết thúc.

    InventoryItem another = em.find(
        InventoryItem.class, otherItemId);
    another.decreaseQuantity(2);

    tx.commit(); // Ghi phần còn lại khi cần, rồi commit.
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
~~~

`flush()` không gọi `tx.commit()`. Sau flush, entity thông thường vẫn managed, transaction còn mở và Hibernate có thể tiếp tục theo dõi thêm sửa đổi.

Đoạn code trên dùng JPA **resource-local**. Với Spring-managed transaction hoặc JTA, không tự gọi `em.getTransaction().begin()`/`commit()` trên shared EntityManager do container quản lý; transaction boundary được tầng tương ứng điều phối.

### 3.1. Flush một persistence context, không phải “save một field”

~~~java
InventoryItem a = em.find(InventoryItem.class, aId);
InventoryItem b = em.find(InventoryItem.class, bId);

a.decreaseQuantity(2);
b.decreaseQuantity(1);

em.flush();
~~~

Flush sẽ đồng bộ những pending actions phù hợp trong **persistence context**, không giới hạn vào entity được sửa cuối cùng.

### 3.2. Không nhất thiết có UPDATE mỗi khi flush

~~~java
InventoryItem item = em.find(InventoryItem.class, id);
em.flush();
~~~

Nếu không có persistent state thay đổi hoặc thao tác chờ nào, Hibernate có thể không phát sinh DML. Gọi flush không đồng nghĩa bắt buộc database phải có một UPDATE.

## 4. Commit thường đồng bộ thay đổi còn chờ

Trong phần lớn workflow JPA/Hibernate mặc định:

~~~java
tx.begin();

InventoryItem item = em.find(InventoryItem.class, id);
item.decreaseQuantity(2);

tx.commit();
~~~

ứng dụng không cần tự gọi flush để Hibernate ghi thay đổi. Khi transaction sắp commit, Hibernate/JPA có thể flush những thay đổi còn chờ, sau đó transaction được commit.

Đây là quan hệ một chiều:

- **Commit** thường liên quan tới flush cần thiết rồi xác nhận transaction.
- **Flush** chỉ đồng bộ SQL; nó không tự tạo commit.

Với những flush mode đặc biệt (như Hibernate `MANUAL`), hành vi tự đồng bộ có thể khác. Không nên giả định mọi cấu hình đều auto-flush giống mặc định.

### 4.1. Flush thành công không đảm bảo commit thành công

Một transaction có thể flush xong nhưng gặp lỗi ở commit, ví dụ deferred constraint, khóa, lỗi transaction hoặc hạ tầng. Không thể kết luận “mọi thứ đã lưu bền vững” chỉ vì `flush()` không ném exception.

### 4.2. SQL xuất hiện trên log không chứng minh commit

Nếu log chứa:

~~~text
Hibernate: update inventory_items set quantity=?, version=? where id=? and version=?
~~~

điều đó cho biết Hibernate đã thực hiện/chuẩn bị thực hiện SQL. Để biết transaction commit thành công hay rollback, phải theo dõi transaction boundary và kết quả commit, không chỉ SQL DML.

## 5. Transaction khác có nhìn thấy dữ liệu vừa flush không?

Không nhất thiết. Dữ liệu **đã gửi đến database** và dữ liệu **đã được commit và hiển thị cho transaction khác** là hai chuyện khác nhau.

Ví dụ:

~~~text
Transaction A                           Transaction B
-----------------------------------     --------------------------------
BEGIN                                   BEGIN
UPDATE quantity = 17
flush, chưa commit
                                        SELECT quantity
                                        → thường thấy 20 tại READ COMMITTED
COMMIT
                                        SELECT lần nữa
                                        → có thể thấy 17 tùy isolation
~~~

Dưới `READ COMMITTED` ở nhiều database, một transaction không thấy thay đổi chưa commit của transaction khác. Với `REPEATABLE READ` hoặc snapshot isolation, B có thể còn thấy snapshot cũ sau khi A đã commit, cho tới khi B kết thúc transaction.

Các chi tiết phụ thuộc database, isolation và loại truy vấn. Không nên khẳng định mọi database cùng thực thi MVCC/locking giống nhau.

### 5.1. Transaction thường đọc được những thay đổi do chính nó vừa flush

~~~java
item.decreaseQuantity(3);
em.flush();

Number value = (Number) em.createNativeQuery("""
    SELECT quantity
    FROM inventory_items
    WHERE id = :id
    """)
    .setParameter("id", itemId)
    .getSingleResult();

System.out.println(value.intValue());
~~~

Với database transactional thông thường, câu SELECT trong cùng transaction có thể thấy những thay đổi trước đó của chính transaction. Điều này **không** nghĩa một connection khác đã thấy dữ liệu chưa commit.

### 5.2. Flush sớm có thể giữ lock lâu hơn

SQL UPDATE tại flush có thể lấy row lock và giữ tới commit/rollback. Nếu ứng dụng flush rồi còn chờ nhiều bước tính toán hoặc gọi HTTP, các transaction khác có thể bị chặn. Không phải flush càng sớm luôn càng tốt; nên cân nhắc thời gian giữ transaction và lock.

## 6. Rollback sau flush và trạng thái Java trong RAM

Giả sử:

~~~java
tx.begin();

InventoryItem item = em.find(InventoryItem.class, id);
item.decreaseQuantity(1);

em.flush();
tx.rollback();
~~~

Database transactional thường rollback UPDATE chưa commit. Tuy nhiên, object Java `item` vẫn có thể giữ giá trị `quantity` đã giảm trong RAM. **Rollback DB không đồng nghĩa tự chạy ngược tất cả setter Java.**

Sau rollback, persistence context có thể không còn phù hợp để dùng tiếp; thông thường nên kết thúc scope, mở transaction/context mới và đọc lại dữ liệu khi cần.

### 6.1. Tác dụng phụ ngoài database không tự rollback

Các hành động sau không mặc nhiên nằm trong transaction DB:

- Email hoặc SMS đã gửi.
- HTTP request tới service ngoài.
- Message publish không có transaction phối hợp.
- Ghi file ngoài DB.
- Log/telemetry.
- ID từ sequence hoặc auto-increment đã cấp, tùy database.

Ví dụ:

~~~java
em.persist(order);
em.flush();

emailService.sendConfirmation(order.getId());

throw new IllegalStateException("Lỗi sau đó");
~~~

Hàng order có thể rollback nhưng email đã gửi không tự được thu hồi. **Đã flush không phải bằng chứng giao dịch sẽ commit** và không phải thời điểm an toàn mặc định để phát side effect không thể đảo ngược.

Nếu cần phát event sau commit, có thể cân nhắc transaction synchronization, transactional event listener hoặc transactional outbox theo yêu cầu độ tin cậy.

## 7. Khi nào Hibernate tự flush?

Hibernate thường không flush ngay sau mỗi setter. Thời điểm đồng bộ phụ thuộc **flush mode**, loại query, trạng thái entity và transaction.

Chuẩn JPA có:

~~~java
import jakarta.persistence.FlushModeType;

em.setFlushMode(FlushModeType.AUTO);
em.setFlushMode(FlushModeType.COMMIT);
~~~

| Chế độ | Ý nghĩa thường gặp | Lưu ý |
| --- | --- | --- |
| JPA `AUTO` | Provider đồng bộ khi cần để đảm bảo kết quả query theo hợp đồng và khi commit | Có thể phát SQL trước commit |
| JPA `COMMIT` | Ưu tiên đồng bộ tại commit | Ảnh hưởng của thay đổi chưa flush lên query trước commit không được đảm bảo giống AUTO |
| Hibernate `ALWAYS` | Flush trước các query theo ngữ nghĩa Hibernate | Extension Hibernate, không phải enum JPA |
| Hibernate `MANUAL` | Hạn chế tự flush, yêu cầu flush tường minh trong các ngữ cảnh thích hợp | Có thể bỏ sót ghi dữ liệu nếu dùng sai |
| Hibernate `AUTO` | Chế độ phổ biến do Hibernate quản lý | Phụ thuộc query và synchronization |

`ALWAYS`/`MANUAL` thuộc các API Hibernate riêng, không phải giá trị của `jakarta.persistence.FlushModeType`.

### 7.1. Query có thể khiến Hibernate flush trước commit

~~~java
InventoryItem item = em.find(InventoryItem.class, id);
item.decreaseQuantity(1);

Long count = em.createQuery("""
    SELECT COUNT(i)
    FROM InventoryItem i
    WHERE i.quantity > 0
    """, Long.class)
    .getSingleResult();
~~~

Ở AUTO, Hibernate có thể flush trước query vì truy vấn cần xem dữ liệu đã được thay đổi trong cùng persistence context. Nhưng **không phải mọi SELECT luôn flush**, vì provider có thể xác định query không liên quan tới bảng đã sửa hoặc chọn thời điểm đồng bộ khác.

Với native SQL, hành vi đồng bộ có thể khác giữa đường API `EntityManager` và Hibernate `Session`, giữa các phiên bản và những query spaces đã khai báo. Nếu nghiệp vụ bắt buộc DML được gửi trước một SQL riêng, flush tường minh có thể dễ hiểu hơn trông chờ query tự kích hoạt flush.

### 7.2. JPA COMMIT flush mode không phải JDBC autoCommit

`FlushModeType.COMMIT` điều chỉnh lịch đồng bộ của provider. Nó **không** bật JDBC auto-commit cho từng câu SQL. Không nên nhầm với `Connection.setAutoCommit(true)` hoặc giả định `flush()` sẽ commit khi flush mode là COMMIT.

## 8. Khi nào gọi flush thủ công là hữu ích?

### 8.1. Phát hiện một số lỗi constraint sớm

Nếu database có unique constraint trên `sku`:

~~~java
em.persist(new InventoryItem("SKU-EXISTING", 10));
em.flush();
~~~

Khi Hibernate thực thi INSERT, database có thể báo duplicate key ngay tại flush. Điều này giúp tránh thực hiện thêm những bước nghiệp vụ đắt tiền trước khi biết dữ liệu không hợp lệ.

Tuy nhiên, lỗi có thể chỉ xuất hiện tại commit nếu database dùng deferred constraints hoặc có kiểm tra transaction-level. Flush thành công không thay thế kết quả commit.

**Nếu flush lỗi, thường cần rollback và kết thúc persistence context hiện tại**, không nên bắt lỗi rồi tùy tiện tiếp tục ghi trong cùng transaction.

### 8.2. Đọc lại giá trị do trigger tạo ra

Giả sử database trigger tính thuế sau UPDATE invoice:

~~~java
invoice.updateAmount(newAmount);

em.flush();          // Gửi UPDATE, trigger có thể chạy.
em.refresh(invoice); // Đọc lại generated tax_amount.
~~~

Flush đưa thay đổi xuống DB; refresh đọc persistent state từ DB về chính entity managed. Nếu Hibernate hỗ trợ mapping generated value phù hợp, có thể không cần refresh thủ công.

### 8.3. SQL riêng cần dữ liệu vừa thay đổi

Nếu một native query cần một hàng mới đã được INSERT trong cùng transaction:

~~~java
em.persist(order);
em.flush();

em.createNativeQuery("""
    UPDATE order_statistics
    SET order_count = order_count + 1
    WHERE account_id = :accountId
    """)
    .setParameter("accountId", accountId)
    .executeUpdate();
~~~

Flush buộc SQL đang chờ được gửi trước native command. Đây chỉ là ví dụ sắp thứ tự, không có nghĩa nghiệp vụ thống kê thực tế nên dùng mẫu cập nhật này mà không cân nhắc concurrency, trigger hoặc kiến trúc aggregation.

### 8.4. Batch processing và quản lý bộ nhớ

~~~java
for (int i = 0; i < records.size(); i++) {
    em.persist(records.get(i));

    if ((i + 1) % 50 == 0) {
        em.flush();
        em.clear();
    }
}

em.flush();
em.clear();
~~~

`flush()` gửi SQL pending; `clear()` detach managed entities để context không phình to quá mức. Nhưng **không có commit tại mỗi mốc 50** nếu vòng lặp vẫn nằm trong một transaction.

Nếu cần commit từng batch 50, phải thiết kế transaction boundary độc lập cho mỗi batch, xử lý partial success và khả năng chạy lại idempotent.

## 9. Spring Data JPA: saveAndFlush không phải commit

Spring Data JPA cung cấp các thao tác như:

~~~java
repository.save(entity);
repository.flush();
repository.saveAndFlush(entity);
~~~

| API | Mục đích | Tự commit độc lập khi có outer transaction? |
| --- | --- | --- |
| `save(entity)` | Persist hoặc merge theo cách xác định entity mới | Không |
| `flush()` | Đồng bộ context với database | Không |
| `saveAndFlush(entity)` | Save rồi flush | Không |
| `EntityManager.flush()` | Flush context | Không |
| Transaction manager commit | Kết thúc thành công transaction hiện tại | Có nếu nó sở hữu transaction đó |
| Transaction manager rollback | Hủy các thay đổi transactional chưa commit | Không commit |

Nếu gọi repository method **ngoài một transaction service bao ngoài**, Spring Data có thể tự mở transaction cho method ghi và commit khi method đó kết thúc. Nhưng trong một `@Transactional` service, `saveAndFlush()` tham gia **transaction đang mở**, không tạo commit con.

### 9.1. Ví dụ service rollback sau saveAndFlush

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void createThenFail() {
        repository.saveAndFlush(
            new InventoryItem("SKU-NEW", 10)
        );

        throw new IllegalStateException("Buộc rollback");
    }
}
~~~

Với rollback policy mặc định của Spring cho unchecked exception và transaction thực sự được quản lý, hàng `SKU-NEW` không được commit. Việc `saveAndFlush()` đã gửi SQL không thay đổi tính nguyên tử của transaction.

Nếu service tự bắt và bỏ qua exception, transaction có thể tiếp tục tới commit tùy trạng thái rollback-only và cấu hình; không nên giả định “hễ có lỗi là chắc chắn rollback” khi code cố tình nuốt lỗi.

### 9.2. saveAndFlush không làm object trở thành managed mãi mãi

Nếu `save()` chọn nhánh `merge()` cho detached entity, giá trị trả về có thể là một managed counterpart khác object truyền vào. Khi transaction/context kết thúc, object đó cũng có thể detached.

Đây là vấn đề khác với flush/commit: **object identity và transaction boundary là hai trục độc lập**.

### 9.3. @Transactional(readOnly = true) có thể thay cách flush

Trong một số tích hợp Spring + Hibernate, `readOnly = true` tối ưu bằng cách đặt flush mode hoặc dirty-checking behavior khác. Nếu nghiệp vụ thật sự cần ghi, dùng transaction ghi phù hợp; đừng cố gọi flush để vượt ý định read-only.

Mức độ cơ sở dữ liệu thực thi read-only còn tùy driver và transaction manager; không phải một đảm bảo giống nhau trên mọi cấu hình.

## 10. Nhiều flush và một commit trong Spring

Một service có thể:

~~~java
@Transactional
public void moveStock(Long fromId, Long toId, int amount) {
    InventoryItem from = em.find(InventoryItem.class, fromId);
    InventoryItem to = em.find(InventoryItem.class, toId);

    from.decreaseQuantity(amount);
    em.flush(); // UPDATE ở bước debit.

    to.increaseQuantity(amount);
    em.flush(); // UPDATE ở bước credit.

    // Khi phương thức kết thúc thành công:
    // Spring transaction manager tiến hành commit.
}
~~~

Cả hai flush vẫn nằm trong **cùng transaction**. Nếu một bước cuối gây exception khiến transaction rollback, cả hai thay đổi transactional sẽ bị hoàn tác.

Không nên chèn flush để “chốt” từng bước và tưởng rằng bước đầu không thể đảo ngược. Với nghiệp vụ chuyển kho/tiền thật, còn phải xử lý concurrency bằng `@Version`, locking, transaction isolation và validation phù hợp.

### 10.1. Muốn commit độc lập cần transaction độc lập

Nếu yêu cầu thật sự là:

~~~text
Transaction A → COMMIT
Transaction B → COMMIT hoặc ROLLBACK riêng
~~~

cần thiết kế hai transaction thực sự. Spring có propagation `REQUIRES_NEW` trong điều kiện proxy/transaction manager phù hợp, nhưng cần lưu ý self-invocation, connection pool, việc inner transaction không thấy outer transaction chưa commit và khả năng kết quả từng phần.

**Đừng dùng REQUIRES_NEW chỉ để thay cho flush**. Nó thay đổi atomicity của nghiệp vụ, đôi khi gây sai lệch dữ liệu.

## 11. JDBC batching và flush thường xuyên

Hibernate có thể gom statements vào JDBC batch nếu mapping/driver và cấu hình cho phép, ví dụ:

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
~~~

Nếu code:

~~~java
for (InventoryItem item : items) {
    em.persist(item);
    em.flush();
}
~~~

thì mỗi lần flush có thể làm mất cơ hội gom nhiều thao tác thành batch. Flush theo kích thước hợp lý có thể giảm round-trip và giới hạn memory.

Tuy nhiên, `GenerationType.IDENTITY` thường đòi INSERT sớm để lấy ID, có thể hạn chế batching. Khi tối ưu performance, cần quan sát SQL và JDBC thực tế chứ không chỉ đếm số lần gọi `flush()`.

### 11.1. Không suy ra thứ tự SQL từ thứ tự setter

Hibernate có action queue và có thể sắp xếp các thao tác để phù hợp FK/mapping và tối ưu batching. Một loạt `persist()` rồi flush không bắt buộc phát nguyên văn INSERT theo thứ tự từng dòng Java.

Nếu cần một native SQL phụ thuộc row đã insert, hãy xác định điểm đồng bộ có chủ đích và constraint của database.

## 12. IDENTITY có thể INSERT trước flush tường minh

Với:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Hibernate thường cần INSERT để database cấp generated ID. Trong một số ngữ cảnh nó có thể thực thi INSERT sớm, không đợi đúng lần `flush()` do lập trình viên gọi.

Với `SEQUENCE`, Hibernate có thể xin sequence number trước khi INSERT. Dù ID đã có, **không thể kết luận transaction đã commit**.

Sau rollback, ID từng được cấp có thể vẫn còn trong Java object hoặc sequence không quay ngược, dù row chưa commit. Điều đó không phải dấu hiệu database còn giữ hàng mới.

## 13. Lỗi tại flush và tại commit

Những lỗi có thể phát sinh khi SQL thực thi:

- Vi phạm unique, not-null, check, foreign key constraint.
- Dữ liệu không hợp lệ với SQL column type.
- Optimistic locking: version không còn khớp.
- Deadlock, lock timeout hoặc lỗi JDBC.
- Trigger/stored procedure báo lỗi.

Lỗi có thể xuất hiện tại `flush()` vì đó là lúc SQL được gửi. Nhưng deferred constraints hay lỗi transaction-level có thể chỉ xuất hiện tại `commit()`. Vì vậy **flush thành công chưa chứng minh commit chắc chắn thành công**.

### 13.1. Không tiếp tục giao dịch sau lỗi flush một cách tùy tiện

~~~java
try {
    em.flush();
} catch (PersistenceException ex) {
    // KHÔNG nên bỏ qua rồi dùng tiếp EntityManager
    // như thể transaction vẫn hoàn toàn hợp lệ.
}
~~~

Sau lỗi database/persistence, transaction có thể đã rollback-only và context có thể không nhất quán. Hướng thông thường là rollback, kết thúc scope và tạo transaction/persistence context mới khi cần.

### 13.2. Optimistic locking xảy ra khi DML được kiểm tra

Với `@Version`, Hibernate có thể sinh UPDATE tương đương:

~~~sql
UPDATE inventory_items
SET quantity = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Nếu transaction khác đã đổi version, Hibernate có thể phát hiện xung đột khi SQL UPDATE chạy hoặc tại flush/commit tùy cơ chế. Flush sớm có thể đưa lỗi ra sớm hơn, **không tự hòa giải** xung đột.

## 14. Sự khác nhau giữa flush và refresh

Một đôi dễ nhầm:

~~~java
em.flush();         // Từ persistence context xuống DB.
em.refresh(item);   // Từ DB lên managed item.
~~~

Ví dụ database có trigger tính `updated_at`:

~~~java
item.decreaseQuantity(1);
em.flush();          // Gửi UPDATE để trigger chạy.
em.refresh(item);    // Nạp lại updated_at từ DB.
~~~

Flush không tự đồng bộ mọi giá trị do trigger thay đổi trở lại object Java. Refresh có thể giúp trong trường hợp cần đọc state mới ngay, nhưng có thể ghi đè các sửa đổi chưa flush. Generated-value mapping phù hợp đôi khi tốt hơn việc refresh thủ công.

## 15. Flush và cascade

Ví dụ quan hệ:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
~~~

Khi persist Order, cascade có thể lên lịch INSERT các OrderLine. Khi bỏ một child khỏi collection, orphan removal có thể lên lịch DELETE. Flush gửi SQL của các thao tác đã lên lịch.

Nhưng:

- Persist parent/child, flush rồi rollback → những INSERT transactional chưa commit có thể bị hủy.
- Xóa parent/child, flush rồi rollback → các DELETE transactional chưa commit có thể được hoàn tác.
- Transaction rollback không tự phục hồi mọi object Java và association trong bộ nhớ.

Cascade quyết định thao tác ORM được lan truyền; commit/rollback quyết định kết quả transaction, không phải số lần flush.

## 16. Transaction boundary và tác dụng phụ bên ngoài

Một kiểu code rủi ro:

~~~java
@Transactional
public Long placeOrder() {
    Order order = new Order();
    em.persist(order);
    em.flush();

    remotePaymentService.charge(order.getId());

    return order.getId();
}
~~~

Nếu remote payment thành công nhưng commit Order thất bại, có thể xảy ra việc thanh toán bên ngoài đã thực hiện còn database không xác nhận đơn hàng.

Ngược lại, việc remote call chậm sau flush có thể giữ DB lock/connection lâu. Cần thiết kế tích hợp theo nghiệp vụ bằng idempotency, outbox, saga hoặc cơ chế xử lý sau commit; **không coi flush như một điểm xác nhận giao dịch phân tán**.

## 17. Quan sát flush và transaction trong Hibernate

Trong Hibernate 6 và Spring Boot, có thể bật log phát triển:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

Logger bind có thể làm lộ dữ liệu nhạy cảm, chỉ dùng trong môi trường an toàn.

Để phân tích request, hãy quan sát cả:

1. Transaction bắt đầu khi nào.
2. Entity nào đang managed và thay đổi field nào.
3. SQL phát ở flush tường minh hay auto-flush.
4. Có JDBC batching hoặc generated ID không.
5. Transaction commit, rollback hay marked rollback-only.
6. Những request khác đọc dữ liệu dưới isolation nào.

SQL log tự nó chỉ cho thấy hoạt động DML, không cho thấy transaction chắc chắn được commit.

## 18. Những nhầm lẫn cần tránh

| Nhận định sai | Điều đúng |
| --- | --- |
| “Flush là commit.” | Flush gửi SQL; commit xác nhận và kết thúc transaction. |
| “Flush tự kết thúc transaction.” | Transaction vẫn mở đến commit/rollback. |
| “Hai lần flush là hai transaction.” | Có thể nhiều flush trong một transaction duy nhất. |
| “Rollback chỉ hủy thay đổi sau lần flush cuối.” | Rollback hủy thay đổi transactional chưa commit của toàn transaction. |
| “Đã thấy SQL UPDATE là dữ liệu bền vững.” | DML có thể chưa commit hoặc sẽ rollback. |
| “ID đã có thì insert đã commit.” | ID có thể được cấp trước commit. |
| “saveAndFlush luôn commit.” | Trong outer transaction, nó flush mà không commit độc lập. |
| “Flush chỉ xử lý entity cuối cùng sửa.” | Flush đồng bộ pending actions của persistence context. |
| “AUTO flush sau mọi setter.” | Hibernate thường gom thay đổi; query/commit mới có thể kích hoạt flush. |
| “Mọi query đều flush.” | Phụ thuộc flush mode, query spaces và đường API. |
| “Flush thành công thì commit không thể lỗi.” | Một số lỗi có thể xảy ra tại commit. |
| “Flush xong transaction khác thấy dữ liệu.” | Phụ thuộc commit và isolation. |
| “Rollback tự đổi Java object về giá trị cũ.” | Rollback DB không chạy ngược mọi setter. |
| “Flush sẽ lấy mọi giá trị trigger mới vào entity.” | Có thể cần generated mapping hoặc refresh. |
| “Muốn commit từng 100 bản ghi thì flush mỗi 100.” | Cần transaction boundary riêng nếu muốn commit từng batch. |

## 19. Checklist quyết định gọi flush thủ công

Trước khi chèn `em.flush()`, hãy trả lời:

1. **Transaction hiện tại do ai quản lý?** JPA resource-local, JTA hay Spring?
2. **Có lý do cần SQL chạy sớm không?** Kiểm tra constraint, trigger, native query phụ thuộc?
3. **Có thể để flush tại commit không?** Nếu không cần kết quả trung gian, thường đơn giản hơn.
4. **Những entity khác trong context có pending changes không?** Flush có thể gửi cả chúng.
5. **Nếu flush lỗi, service rollback thế nào?** Không dùng tiếp context sai trạng thái.
6. **Nếu phần sau thất bại, toàn transaction có rollback không?** Hiểu Spring rollback policy.
7. **Có email, SMS hoặc API call ngoài DB không?** Chúng không tự rollback.
8. **Có cần commit thật sự ở mốc này không?** Khi đó tạo transaction boundary, không dùng flush thay thế.
9. **Lock có bị giữ lâu sau flush không?** Cân nhắc throughput và deadlock.
10. **Batching có bị phá bởi flush quá thường xuyên không?** Tối ưu theo workload.
11. **Isolation có cho transaction khác thấy dữ liệu chưa commit không?** Không suy luận từ log SQL.
12. **Có nhầm `saveAndFlush()` với commit không?** Xem outer transaction.

## 20. Bài tập thực hành

### Bài 1 — Flush rồi rollback

Giả sử quantity ban đầu bằng 10:

~~~java
tx.begin();

InventoryItem item = em.find(InventoryItem.class, id);
item.decreaseQuantity(2);

em.flush();
tx.rollback();
~~~

Trong transaction mới, quantity là bao nhiêu nếu không có transaction khác can thiệp? Tại sao nhìn thấy UPDATE trong log không chứng minh việc ghi bền vững?

### Bài 2 — Hai flush và một commit

~~~java
tx.begin();
updateA();
em.flush();
updateB();
em.flush();
tx.commit();
~~~

Có bao nhiêu transaction? Nếu commit thất bại và transaction rollback, điều gì xảy ra với A và B?

### Bài 3 — Spring Data JPA

~~~java
@Transactional
public void createAndFail() {
    repository.saveAndFlush(
        new InventoryItem("SKU-X", 10)
    );
    throw new IllegalStateException("Failure");
}
~~~

Với rollback mặc định cho unchecked exception, hàng SKU-X có được commit không? Điều gì có thể khác nếu gọi repository bên ngoài outer transaction?

### Bài 4 — AUTO flush và query

~~~java
InventoryItem item = em.find(InventoryItem.class, id);
item.decreaseQuantity(1);

Long count = em.createQuery("""
    SELECT COUNT(i)
    FROM InventoryItem i
    WHERE i.quantity > 0
    """, Long.class).getSingleResult();
~~~

Giải thích vì sao Hibernate có thể flush trước query. Query có đồng nghĩa transaction commit hay không?

### Bài 5 — Lỗi khi flush

Một INSERT vi phạm unique constraint. Sau lỗi tại `em.flush()`, có an toàn nếu bắt exception rồi tiếp tục dùng EntityManager và commit không? Vì sao?

### Bài 6 — IDENTITY

Một entity nhận được generated ID sau `persist()` nhưng transaction rollback. ID đã có chứng minh hàng đã commit không? Vì sao INSERT đôi khi chạy trước `flush()` tường minh?

### Bài 7 — Chuyển tiền

Trong một transaction, A bị trừ 100.000 đồng, flush, B được cộng 100.000 đồng, rồi exception khiến rollback. Tại sao cả hai cập nhật transactional bị hủy? Gửi SMS sau flush nhưng trước commit có rủi ro gì?

### Bài 8 — Batch processing

Job ghi 10.000 hàng, flush và clear mỗi 100 nhưng giữ nguyên một transaction bao toàn bộ job. Lỗi ở hàng thứ 9.000 dẫn đến rollback. Bao nhiêu hàng đã được commit? Muốn commit mỗi 100 bản ghi thì phải thay đổi gì?

### Gợi ý

- **Bài 1:** Quantity vẫn là 10 sau rollback, giả định DB transactional và không có giao dịch khác thay đổi.
- **Bài 2:** Một transaction, A và B cùng thuộc kết quả commit/rollback cuối cùng.
- **Bài 3:** Hàng không commit khi rollback đúng cấu hình; repository tự mở transaction ngoài outer scope có thể commit ở cuối method.
- **Bài 4:** AUTO có thể đồng bộ thay đổi cần thiết trước query; query không tự commit.
- **Bài 5:** Thường phải rollback và dùng context/transaction mới sau lỗi persistence.
- **Bài 6:** ID có trước commit không đảm bảo dữ liệu bền vững; IDENTITY có thể cần INSERT để lấy ID.
- **Bài 7:** Rollback hủy cả hai thay đổi của transaction, nhưng SMS bên ngoài không tự thu hồi.
- **Bài 8:** Không hàng nào của transaction đó commit nếu toàn transaction rollback; cần thiết kế transaction theo batch để commit từng phần.

---

**Ghi nhớ:** `flush()` **đồng bộ thay đổi persistent thành SQL trong transaction hiện tại**; `commit()` **xác nhận và kết thúc transaction**; `rollback()` **hủy các thay đổi transactional chưa commit**. Một transaction có thể flush nhiều lần, SQL có thể xuất hiện trước commit, và flush thành công vẫn có thể bị rollback. Muốn đảm bảo tính nguyên tử và độ bền vững, phải hiểu và quản lý **transaction boundary**, không chỉ theo dõi lời gọi flush hoặc SQL log.
