# Xem dữ liệu trong đối tượng là dữ liệu đã được lưu

Một service Java tạo đối tượng Order, gán trạng thái CONFIRMED, gọi repository.save(order) rồi trả về trạng thái thành công. Màn hình hiển thị CONFIRMED vì đối tượng trong RAM đã đổi. Nhưng nếu transaction sau đó rollback, câu INSERT chưa được flush, hoặc một optimistic-lock conflict xảy ra lúc commit, **database có thể chưa từng lưu trạng thái CONFIRMED**.

Đây là lỗi thiết kế phổ biến: **đồng nhất trạng thái của đối tượng trong bộ nhớ với trạng thái bền vững của hệ thống lưu trữ**. Lỗi này xuất hiện với plain Java object, DTO, JDBC, JPA/Hibernate, Spring Data, ORM khác, cache và hệ thống xử lý bất đồng bộ. Nó đặc biệt nguy hiểm khi một quyết định tiếp theo dựa vào giả định “đã lưu” để gửi email, thu tiền, công bố event, trả HTTP 200 hoặc cho phép người dùng tiếp tục.

Bài thuộc chương **Lỗi thiết kế** trong module **DATA_PERSISTENCE_FUNDAMENTALS**. Nội dung kết hợp tư duy về mô hình dữ liệu, giao dịch, chỉ mục, đồng thời, lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng để chỉ ra cách phân biệt **giá trị mong muốn**, **lệnh đã gửi**, **transaction đã commit** và **dữ liệu được quan sát từ một đường đọc cụ thể**.

> **Nguyên tắc:** một field đã thay đổi trong Java không phải bằng chứng rằng SQL đã chạy; SQL chạy xong chưa phải bằng chứng COMMIT đã thành công; COMMIT thành công ở nguồn chuẩn chưa bảo đảm mọi replica/cache đã kịp cập nhật.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt trạng thái object, trạng thái persistence context, các lệnh SQL đã thực thi, transaction chưa commit và dữ liệu đã commit.
- Giải thích vai trò của persist(), save(), flush(), dirty checking, detach(), merge() và @Transactional trong JPA/Spring.
- Xác định điểm nào trong quy trình ghi có thể coi là đã hoàn tất theo hợp đồng ứng dụng.
- Phân biệt lời gọi Java thành công, thao tác JDBC thành công và kết quả COMMIT được xác nhận.
- Nhận diện các trường hợp object có ID/version/giá trị mới nhưng database chưa lưu hoặc lưu giá trị khác.
- Xử lý rollback, lỗi constraint, optimistic locking, lost update, transaction propagation và ambiguous commit.
- Phân biệt nguồn dữ liệu chuẩn với entity/DTO/cache/read replica; nêu lý do lần đọc sau ghi có thể trả bản cũ.
- Thiết kế API, outbox/idempotency, kiểm thử transaction và kiểm chứng dữ liệu đã lưu mà không tin vào object đang giữ.
- Xây dựng checklist review code nhằm ngăn tạo side effect dựa trên trạng thái chỉ tồn tại trong bộ nhớ.

## 2. Ví dụ đầu tiên: đối tượng đổi giá trị không có nghĩa DB đổi giá trị

Giả sử Order có trạng thái PENDING trong PostgreSQL. Một method Java có thể thực hiện:

~~~java
Order order = repository.findById(orderId).orElseThrow();
order.setStatus(OrderStatus.CONFIRMED);

return order.getStatus(); // CONFIRMED trong object.
~~~

Câu cuối chứng minh **getter** trả CONFIRMED. Nó không tự chứng minh:

- Object có đang được JPA quản lý không hay đã detached?
- Method có nằm trong transaction ghi được phép commit không?
- Dirty checking có phát hiện thay đổi không?
- ORM đã gửi UPDATE chưa?
- UPDATE có khớp đúng hàng, đúng version và tenant không?
- Constraint hoặc trigger có cho phép cập nhật không?
- COMMIT có hoàn tất không?
- Một request GET khác đang đọc primary hay replica/cache?
- Sau khi ghi, database có áp dụng default, trigger hoặc conversion làm khác dữ liệu trong object không?

**Đối tượng là một biểu diễn dữ liệu tại một thời điểm của một tiến trình. Database là hệ thống lưu trữ có transaction, constraint và lifecycle riêng.**

### 2.1. Những điều kiện cần kiểm tra theo từng ranh giới

| Bước | Điều có thể khẳng định | Điều chưa đủ căn cứ |
|---|---|---|
| Constructor/setter hoàn thành | Field trong object đã được gán | Bất kỳ INSERT/UPDATE nào |
| Gọi repository.save() | Đã yêu cầu tầng persistence xử lý | Mọi SQL đã chạy hoặc COMMIT bền vững |
| JPA flush() hoàn tất | Những SQL đang chờ flush đã được gửi/thực thi theo context | Transaction đã commit hoặc replica đã thấy dữ liệu |
| JDBC executeUpdate() trả số hàng | Statement được DB xử lý trong phạm vi transaction | Outer transaction đã commit |
| Transaction COMMIT được xác nhận | Dữ liệu đã commit trên nguồn được ghi theo chính sách durability của hệ thống | Tất cả cache/replica đã đồng bộ |
| GET từ replica trả giá trị mới | Replica/query đó đã quan sát thay đổi | Mọi nguồn đọc khác đều đã bắt kịp |
| GET từ cache trả giá trị mới | Entry này chứa giá trị mới theo cách cache vận hành | Cache là nguồn quyết định nghiệp vụ |

Đây là **chuỗi bằng chứng**, không phải các từ đồng nghĩa của “saved”.

## 3. Hai dòng thời gian: object trong RAM và trạng thái transaction

Xét một thao tác cập nhật Order:

~~~mermaid
sequenceDiagram
    participant U as Application Service
    participant O as Java Object
    participant E as ORM / JDBC
    participant D as PostgreSQL primary
    U->>O: setStatus(CONFIRMED)
    Note over O: Getter trả CONFIRMED
    U->>E: save() hoặc dirty checking
    E->>D: UPDATE khi flush/execute
    D-->>E: Statement OK (chưa COMMIT)
    U->>E: Commit transaction
    E->>D: COMMIT
    D-->>E: COMMIT OK
    Note over D: Trạng thái committed
~~~

Từ khi setter chạy đến khi COMMIT hoàn tất, object có thể chứa giá trị mới trong khi database vẫn chưa commit giá trị ấy.

### 3.1. Bị rollback sau khi object đã thay đổi

~~~text
T0: PostgreSQL orders.status = PENDING (committed)
T1: Java order.status = CONFIRMED
T2: Flush UPDATE -> DB xử lý trong transaction chưa commit
T3: Bước tiếp theo ném exception -> ROLLBACK
T4: PostgreSQL orders.status = PENDING
T5: Java object còn giữ CONFIRMED nếu caller vẫn còn tham chiếu
~~~

Một đối tượng đang giữ trong RAM **không tự biến ngược về trạng thái cũ** mỗi khi transaction rollback. Không nên tái sử dụng state này để kết luận về database; với JPA, transaction lỗi có thể khiến persistence context không còn phù hợp để tiếp tục ghi, cần đóng/clear và nạp lại theo lifecycle.

### 3.2. Object trong RAM có thể mới hơn hoặc cũ hơn DB

- **Mới hơn nhưng chưa bền vững:** ứng dụng gán trạng thái mới, chưa commit.
- **Cũ hơn DB:** một transaction khác cập nhật row sau khi object của ta được đọc.
- **Khác DB:** trigger, default, generated column hoặc conversion trong DB làm giá trị lưu khác object ban đầu.
- **Không có đối tượng DB tương ứng:** chỉ mới tạo object hoặc row chưa commit/bị rollback.
- **Không được phép đọc/ghi:** object chứa ID từ tenant khác nhưng SQL đúng phải chặn truy cập.

Không gọi mọi trường hợp là “cache stale”; nguồn gốc có thể là lifecycle JPA, transaction, concurrency hoặc biến đổi dữ liệu.

## 4. Plain Java object và DTO không có phép màu persistence

Trong JDBC thuần, một POJO không tự tạo SQL:

~~~java
public final class Product {
    private UUID id;
    private BigDecimal price;

    public Product(UUID id, BigDecimal price) {
        this.id = id;
        this.price = price;
    }

    public UUID getId() { return id; }
    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }
}
~~~

Ví dụ:

~~~java
Product product = new Product(
    UUID.randomUUID(), new BigDecimal("10.00")
);
product.setPrice(new BigDecimal("15.00"));

// Chỉ là thay đổi trong bộ nhớ; JDBC không chạy UPDATE.
assertEquals(new BigDecimal("15.00"), product.getPrice());
~~~

Nếu sau đó trả Product qua HTTP, JSON có thể cho thấy price=15.00 trong khi database chưa có product hoặc vẫn lưu 10.00. Cần một lệnh ghi hợp lệ với connection/transaction và kiểm tra kết quả được commit.

### 4.1. Repository fake/map in-memory không chứng minh database

~~~java
Map<UUID, Product> inMemory = new HashMap<>();
inMemory.put(product.getId(), product);

product.setPrice(new BigDecimal("99.00"));
assertEquals(
    new BigDecimal("99.00"),
    inMemory.get(product.getId()).getPrice()
);
~~~

Map giữ **cùng tham chiếu object**, nên không cần bất kỳ phương thức update nào mà giá trị đọc từ map đã đổi. Đây là lỗi phổ biến trong unit test repository giả: test xanh vì aliasing trong RAM, không phải vì persistence adapter đã lưu đúng.

Khi cần test SQL, mapping, constraint và transaction, phải dùng integration test với DB tương ứng; fake chỉ nên kiểm tra logic ở phạm vi mà nó thực sự mô phỏng được.

### 4.2. Object chứa UUID không chứng minh row tồn tại

Ứng dụng có thể cấp UUID trước INSERT:

~~~java
UUID id = UUID.randomUUID();
Product product = new Product(id, new BigDecimal("10.00"));
~~~

ID này là định danh được dự kiến, **không phải giấy xác nhận row đã commit**. Tương tự, việc một ORM đã gán generated ID có thể yêu cầu nó thực thi INSERT sớm tùy chiến lược ID, nhưng không bảo đảm transaction đã commit. Đừng đánh đồng “ID != null” với “entity tồn tại bền vững”.

## 5. JDBC: executeUpdate() và COMMIT là hai mốc riêng

Trong JDBC, lệnh ghi explicit được thực thi khi gọi executeUpdate() hoặc API tương ứng; nhưng transaction boundary vẫn quyết định tính bền vững.

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement stmt = connection.prepareStatement(
            """
            UPDATE products
            SET price = ?, version = version + 1
            WHERE tenant_id = ? AND id = ?
              AND version = ?
            """)) {
        stmt.setBigDecimal(1, new BigDecimal("15.00"));
        stmt.setLong(2, tenantId);
        stmt.setObject(3, productId);
        stmt.setLong(4, expectedVersion);

        int changed = stmt.executeUpdate();
        if (changed != 1) {
            connection.rollback();
            throw new IllegalStateException(
                "Not found or optimistic-lock conflict"
            );
        }
    }

    // Đến đây UPDATE đã thực thi trong transaction.
    // Nếu lỗi xảy ra trước COMMIT, chưa được coi là lưu hoàn tất.
    connection.commit();
}
~~~

Đoạn mã tập trung vào sự khác biệt statement/COMMIT; bản triển khai thực tế cần rollback trong mọi nhánh lỗi, bảo vệ exception suppression và lifecycle connection theo pool.

### 5.1. Khi autoCommit=true

Trong JDBC auto-commit thông thường, statement thành công được DB commit theo semantics kết nối/driver, nhưng:

- Không suy một chuỗi nhiều statement trở thành giao dịch nguyên tử chỉ vì mỗi statement tự commit.
- Không gọi một batch nhiều business step là thành công nếu bước thứ hai thất bại mà bước đầu đã auto-commit.
- Cần xem sự khác biệt giữa lệnh SQL thực thi thành công và response HTTP đã tới client.
- Nếu lỗi mạng xảy ra trong quá trình xác nhận kết quả, outcome của thao tác có thể không rõ.

### 5.2. Số hàng bị tác động là bằng chứng có giới hạn

Giá trị 1 từ executeUpdate() có thể chứng minh một hàng khớp điều kiện và statement đã tác động trong transaction. Nó không chứng minh tất cả bước khác đã commit. Giá trị 0 có thể do không tồn tại, version cũ, tenant sai hoặc trạng thái đã xóa. Hợp đồng repository phải nói rõ có phân biệt các nguyên nhân ấy không.

## 6. JPA: entity có nhiều trạng thái, không phải mọi object đều được theo dõi

JPA/Hibernate giúp Java làm việc với row dưới dạng entity và có cơ chế dirty checking. Nhưng ORM chỉ có thể tự đồng bộ theo những điều kiện nhất định.

### 6.1. Các trạng thái entity cần phân biệt

| Trạng thái JPA | Ý nghĩa | Việc setter làm thay đổi DB? |
|---|---|---|
| New/transient | Object mới, chưa được quản lý bởi persistence context | Không; phải yêu cầu persist hoặc luồng save phù hợp |
| Managed/persistent | Object đang thuộc một persistence context còn hiệu lực | Thay đổi có thể được dirty checking và flush |
| Detached | Object đã rời context, ví dụ transaction/session kết thúc | Setter không được context cũ tự flush |
| Removed | Entity được đánh dấu xóa trong context | DELETE thường được phát khi flush; vẫn cần commit |

Vòng đời phổ biến:

~~~mermaid
stateDiagram-v2
    [*] --> Transient: new Entity()
    Transient --> Managed: persist()
    Managed --> Detached: detach / clear / close
    Detached --> Managed: merge() trả managed copy
    Managed --> Removed: remove()
    Removed --> [*]: DELETE khi flush và COMMIT
~~~

Sơ đồ rút gọn nhằm mô tả lifecycle; persist/merge/remove có những tiền điều kiện và ngoại lệ riêng, cascade/transaction có thể ảnh hưởng trạng thái của graph entity.

### 6.2. Managed entity và dirty checking

Ví dụ service JPA:

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private UUID id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @Version
    private long version;

    public OrderStatus getStatus() { return status; }
    public void setStatus(OrderStatus status) { this.status = status; }
}
~~~

~~~java
@Service
public class OrderService {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void confirm(UUID id) {
        OrderEntity order = em.find(OrderEntity.class, id);
        if (order == null) {
            throw new NoSuchElementException();
        }

        order.setStatus(OrderStatus.CONFIRMED);
        // Managed entity: dirty checking có thể lên lịch UPDATE.
        // Không cần gọi save() chỉ để ORM nhận thay đổi managed.
    }
}
~~~

Trong điều kiện transaction đang hoạt động, provider được cấu hình để flush thay đổi, gọi method qua Spring proxy và không bị rollback, JPA có thể tự phát UPDATE khi flush/commit. Tuy vậy, **dòng setter không trực tiếp tương đương UPDATE**. Trước khi interceptor transaction commit thành công, method body có thể đã chạy hết nhưng hệ thống chưa hoàn tất nghiệp vụ.

Không suy mọi setter trên mọi object đều được dirty checking. Object phải thực sự được quản lý trong đúng context đang hoạt động và mapping thay đổi phải được provider nhận biết.

### 6.3. Detached entity không tự ghi xuống database

~~~java
OrderEntity order = loadOrderInPreviousTransaction(orderId);
// Đến đây transaction/context cũ đã kết thúc; order có thể detached.
order.setStatus(OrderStatus.CONFIRMED);

// Không có persistence context nào tự động flush thay đổi này.
return order;
~~~

Một lớp DTO được map từ entity còn ít ràng buộc hơn: thay DTO chỉ là thay data object.

Giải pháp đúng không phải lúc nào cũng gọi save() trên bất kỳ object nào: thường nên mở transaction, load authoritative entity bên trong transaction, kiểm tra điều kiện nghiệp vụ rồi sửa managed entity, hoặc dùng câu UPDATE có điều kiện.

### 6.4. merge() không làm object đầu vào trở thành managed

Theo JPA, merge() sao chép state của detached entity sang một managed instance và trả managed instance đó; object đầu vào vẫn là detached:

~~~java
OrderEntity detached = loadOrderEarlier(orderId);
detached.setStatus(OrderStatus.CONFIRMED);

OrderEntity managed = entityManager.merge(detached);
// managed là instance trả về có ý nghĩa với persistence context.
// detached không tự trở thành managed.
~~~

Dùng merge() bừa bãi có thể ghi đè nhiều field bằng state stale đã được nạp từ trước, tùy mapping và provider. Với ứng dụng có cập nhật từng phần, load current row/expectedVersion và áp dụng command có điều kiện thường minh bạch hơn việc gửi cả detached entity cũ để merge.

**Hãy kiểm tra version:** @Version và optimistic-lock conflict có thể phát hiện một entity đã cũ, nhưng lỗi có thể xuất hiện khi flush/commit, không nhất thiết ngay ở lời gọi merge().

## 7. persist(), save(), flush(), commit(): bốn sự kiện khác nhau

### 7.1. persist() yêu cầu ORM quản lý object mới

~~~java
OrderEntity order = new OrderEntity(...);
entityManager.persist(order);
~~~

Nó đánh dấu entity để được quản lý và lên lịch/làm INSERT theo chiến lược provider, ID generation và flush mode. Trong một số trường hợp, INSERT có thể được thực hiện sớm để lấy ID (ví dụ IDENTITY); trong trường hợp khác, chưa có SQL cho tới flush.

Không viết test giả định **mọi** persist() đều chưa hề phát INSERT; cũng không khẳng định persist() luôn đã INSERT và COMMIT.

### 7.2. Spring Data save() có thể gọi persist hoặc merge

Với Spring Data JPA, save(entity) có thể xác định entity mới/cũ để gọi persist hoặc merge theo cơ chế nhận diện newness và repository implementation. Một lời gọi save không phải giao dịch lưu trữ độc lập với transaction hiện hành:

~~~java
@Transactional
public void change(UUID id) {
    OrderEntity order = orders.findById(id).orElseThrow();
    order.setStatus(OrderStatus.CONFIRMED);
    orders.save(order); // Thường không cần để dirty checking của managed entity.
    // Method body có thể kết thúc trước khi outer transaction COMMIT.
}
~~~

Ngay cả nếu save() không ném exception, transaction ngoài vẫn có thể rollback vì bước sau. Nếu save() được gọi ngoài transaction, repository method có thể tự được bao trong transaction tùy cấu hình Spring Data; đó là **một contract khác** cần xác minh, không suy từ tên save.

### 7.3. flush() đồng bộ lệnh SQL đang chờ, không commit

~~~java
@Transactional
public void create() {
    entityManager.persist(newOrder);
    entityManager.flush(); // Có thể phát hiện constraint hoặc lock conflict.
    // Nếu throw ở đây hoặc transaction rollback sau đó, chưa commit.
}
~~~

JPA FlushMode, provider và một số truy vấn có thể kích hoạt auto-flush trước khi commit. Vì vậy:

- Đừng khẳng định SQL chỉ chạy đúng thời điểm COMMIT.
- Đừng khẳng định SQL **đã** chạy chỉ vì entity có giá trị mới.
- Flush có thể trả lỗi constraint/optimistic locking/DB connectivity.
- Flush thành công chỉ chứng minh pending SQL được xử lý tới mốc đó trong transaction, không chứng minh durability.
- Nếu muốn chứng minh transaction đã commit, hãy kiểm tra **ngoài** transaction đã kết thúc.

### 7.4. flush rồi rollback vẫn không lưu

~~~text
BEGIN
  INSERT orders(id=O1, status=PENDING)
  FLUSH -> INSERT chạy thành công
  UPDATE inventory ... -> violation
ROLLBACK
SELECT O1 từ connection mới -> không có hàng
~~~

Bất kỳ method nào trả kết quả trước khi outer transaction hoàn tất không nên tuyên bố “đã lưu bền vững” chỉ dựa vào flush.

### 7.5. saveAndFlush() cũng chưa phải bảo đảm commit

Tên saveAndFlush trong Spring Data JPA nói về flush sớm trong transaction. Nếu đang có transaction ngoài, nó **không phải lệnh COMMIT độc lập**. Nó có thể hữu ích để phát hiện lỗi constraint sớm nhưng không được dùng như cơ chế thông báo chắc chắn đã lưu.

### 7.6. ID, version và trường generated có thể gây hiểu lầm

| Quan sát trong Java | Điều có thể xảy ra | Cách kiểm chứng |
|---|---|---|
| Entity có ID mới | ID cấp ở app/sequence trước commit | Đọc row sau commit từ nguồn authoritative |
| Entity version tăng | Provider tăng khi flush hoặc theo phiên bản cập nhật | Xác nhận committed version và optimistic lock |
| @CreationTimestamp có giá trị | Provider/DB đã tạo thời điểm | Kiểm tra field sau commit và timezone |
| DB DEFAULT có giá trị | Chỉ áp khi SQL không cung cấp cột, phụ thuộc statement | RETURNING/refresh hoặc đọc lại theo contract |
| Trigger chỉnh tổng tiền/trạng thái | DB có thể thay giá trị vừa gửi | Đọc giá trị do DB xác nhận |
| UUID nằm trong response HTTP | Có thể là ID dự kiến, chưa có row bền vững | Ranh giới transaction + readback |

Không lấy việc entity có ID hợp lệ làm oracle của persistence correctness.

## 8. Spring @Transactional: method return không nhất thiết là transaction complete

Một Spring transaction proxy thường mở transaction trước khi vào method, gọi body, rồi commit hoặc rollback sau khi body kết thúc. Điều này dẫn tới một khác biệt quan trọng:

~~~text
Caller
  -> Transaction Proxy bắt đầu transaction
     -> Service method body
        -> entity.setStatus(...)
        -> return result từ body
     -> Proxy flush/COMMIT
  -> Caller nhận result nếu proxy commit thành công
~~~

Nếu method được gọi qua proxy với transaction mới do proxy sở hữu, **caller** nhận kết quả bình thường sau khi proxy đã hoàn tất commit. Nhưng **code bên trong method body**, callback chưa đúng thời điểm hoặc một transaction ngoài vẫn có thể nhìn kết quả trước khi commit.

### 8.1. Transaction tham gia một scope ngoài

~~~java
@Transactional
public void checkout(UUID orderId) {
    confirmOrder(orderId); // Thao tác lồng trong outer transaction.
    callSomethingThatCanFail(); // Có thể khiến toàn bộ transaction rollback.
}
~~~

Ngay cả khi confirmOrder đã return thành công, nó chưa tự tạo durable commit nếu tham gia transaction của checkout. Nếu gửi event từ confirmOrder ngay lúc return, event có thể nói CONFIRMED dù checkout rollback.

### 8.2. Self-invocation có thể bỏ qua proxy

~~~java
@Service
public class OrderService {
    public void process(UUID id) {
        this.confirm(id);
    }

    @Transactional
    public void confirm(UUID id) {
        // Nếu gọi qua this từ cùng bean trong proxy-based AOP,
        // interceptor @Transactional thông thường không chạy.
    }
}
~~~

Không suy có transaction chỉ vì annotation xuất hiện trong source. Kiểm tra mode AOP, proxy boundary, invocation path và transaction manager thật.

### 8.3. readOnly không tự biến object thành immutable

Spring @Transactional(readOnly=true) thường là hint/setting cho ORM/connection theo manager; không phải cơ chế universal đảm bảo mọi setter bị cấm và không phải bằng chứng SQL được commit. Một managed entity bị sửa trong read-only transaction có thể không được flush theo chính sách provider, hoặc có cách hành xử khác theo cấu hình. Nếu business cần ghi, dùng transaction ghi rõ ràng; không dựa vào behavior vô tình của read-only flag.

### 8.4. Ngoại lệ checked/unchecked và rollback rule

Theo cấu hình Spring thường gặp, runtime exception/Error làm transaction rollback mặc định, còn checked exception có thể không kích hoạt rollback mặc định. Nếu yêu cầu “bất kỳ lỗi nghiệp vụ X đều không commit”, cần cấu hình rollback rules hoặc biểu diễn lỗi phù hợp và test đúng loại exception.

Đừng bắt exception rồi return thành công trong khi transaction vẫn có thể commit một phần các bước trước đó. Ngược lại, sau một persistence error làm transaction bị đánh dấu rollback-only, cố ép commit có thể dẫn tới UnexpectedRollbackException ở boundary ngoài.

### 8.5. REQUIRES_NEW tạo transaction khác

Một method ghi audit dùng REQUIRES_NEW có thể commit độc lập trong khi outer transaction về order rollback. Đôi lúc đây là chủ đích cho audit sự cố, nhưng nếu hợp đồng yêu cầu audit/outbox phản ánh chính xác business commit thì dùng transaction khác dễ tạo event không tương ứng.

Cần phân biệt các bảo đảm:

- REQUIRED tham gia transaction hiện có (hoặc tạo mới nếu chưa có).
- REQUIRES_NEW tách một transaction mới theo Spring proxy/manager.
- Các hệ ngoài DB vẫn không tham gia transaction local chỉ nhờ annotation.

## 9. Database có thể từ chối hoặc biến đổi giá trị mà object đang giữ

Đừng coi object ban đầu là bản sao chắc chắn của committed row. Database có ràng buộc và quy tắc biến đổi riêng.

### 9.1. Ràng buộc SQL được kiểm tra khi statement chạy hoặc khi commit

Ví dụ schema:

~~~sql
CREATE TABLE accounts (
    tenant_id bigint NOT NULL,
    id uuid NOT NULL,
    email text NOT NULL,
    balance numeric(18, 2) NOT NULL,
    version bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, id),
    CONSTRAINT accounts_balance_nonnegative CHECK (balance >= 0),
    CONSTRAINT accounts_email_unique UNIQUE (tenant_id, email)
);
~~~

Java có thể giữ:

~~~java
Account account = new Account(id, "a@example.test",
                              new BigDecimal("-100.00"));
entityManager.persist(account);
~~~

Dù object có balance=-100.00 và được gọi persist, database sẽ từ chối row vi phạm CHECK khi INSERT/UPDATE được thực thi. Với constraint deferrable được cấu hình phù hợp, một số ràng buộc có thể chỉ được kiểm tra tại COMMIT. Lưu ý PostgreSQL CHECK không phải loại deferrable thông thường; UNIQUE/FK mới có những khả năng deferrable tùy DDL.

**Test:** phải xác minh row không được commit, không chỉ assert code gọi persist() hay field trong object.

### 9.2. DB default, trigger và generated values

Giả sử cột created_at do database tạo:

~~~sql
CREATE TABLE orders (
    id uuid PRIMARY KEY,
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
~~~

Nếu application không cung cấp created_at trong INSERT, database sẽ điền giá trị mặc định. Object Java có thể còn createdAt=null cho tới khi ORM fetch/generated-value handling hoặc refresh. Với trigger/logic DB, trường được lưu có thể khác trường gửi đi.

Trong PostgreSQL, có thể dùng RETURNING để nhận giá trị DB trả ở chính statement:

~~~sql
INSERT INTO orders (id, status)
VALUES (:id, :status)
RETURNING id, status, created_at, updated_at;
~~~

Nhưng giá trị RETURNING cũng là kết quả của **statement trong transaction**, không chứng minh outer transaction đã commit. Sau COMMIT, một transaction khác có thể sửa row; nếu cần sự thật mới nhất ở thời điểm đọc, phải xác định consistency của truy vấn.

### 9.3. Numeric precision và thời gian

Object có BigDecimal("19.999"), cột DB là numeric(12,2). PostgreSQL có thể làm tròn khi lưu vào cột có scale cố định. Nếu nghiệp vụ yêu cầu “không làm tròn ngầm”, validation phải kiểm tra bằng BigDecimal.setScale với RoundingMode.UNNECESSARY hoặc quy tắc tương ứng trước khi gửi SQL.

Tương tự:

- LocalDateTime không có timezone không tương đương Instant tuyệt đối.
- timestamp precision có thể khác nhau giữa JVM và DB.
- chuỗi text có quy tắc collation/normalization ảnh hưởng UNIQUE và ORDER BY.
- enum mới trong Java chưa chắc đã được DB schema cũ chấp nhận.
- UPDATE có thể bị trigger bổ sung cột audit hoặc cập nhật trạng thái dẫn xuất.

Khi cần so dữ liệu đã lưu, so theo **hợp đồng biểu diễn của database**, không chỉ equals() với object trước mapping.

### 9.4. Tên field hợp lệ trong Java chưa có nghĩa row hợp lệ trong DB

Validator ở application có thể bị bỏ qua bởi batch/job khác hoặc phiên bản cũ. DB constraint là một lớp bảo vệ ở ranh giới lưu trữ. Ngược lại, constraint chỉ kiểm tra biểu thức đã định, không tự kiểm tra mọi quy tắc nghiệp vụ cần nhiều bảng hoặc external state. Cần cả hai, với test có phạm vi rõ.

## 10. Concurrency: object vừa đọc có thể trở nên lỗi thời

Một đối tượng được đọc từ DB chỉ phản ánh snapshot tại thời điểm truy vấn. Trong lúc xử lý, một transaction khác có thể thay đổi row.

~~~text
DB: account balance=100, version=7

T1: load Account(balance=100, version=7) -> object A
T2: load Account(balance=100, version=7) -> object B
T1: set balance=70
T1: COMMIT balance=70, version=8
T2: set balance=50 trên object B còn version=7
T2: nếu UPDATE không kiểm tra version -> có thể ghi đè T1
~~~

Object B vẫn có balance=50 trong RAM dù hệ thống cần phát hiện xung đột.

### 10.1. Lost update khi ghi cả entity stale

Một endpoint nhận entity đầy đủ từ client hoặc merge detached entity cũ có thể ghi đè trường mà người khác vừa sửa. Đặc biệt nguy hiểm với form tải trước hàng phút, session dài hoặc object được cache xuyên request.

Ví dụ nếu SQL được viết thiếu bảo vệ:

~~~sql
UPDATE accounts
SET balance = :balance,
    email = :email
WHERE tenant_id = :tenant_id AND id = :id;
~~~

Một giá trị email cũ gửi kèm DTO có thể ghi đè email mới dù yêu cầu chỉ định sửa balance. Đừng coi toàn bộ state của DTO là dữ liệu authoritative. Thiết kế command chỉ chứa các trường được phép thay đổi và kiểm tra expectedVersion khi cần.

### 10.2. Optimistic locking: kiểm tra version ở nguồn chuẩn

~~~sql
UPDATE accounts
SET balance = :new_balance,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND id = :id
  AND version = :expected_version
RETURNING balance, version;
~~~

Khi UPDATE trả 0 hàng, có thể là wrong tenant, ID không tồn tại hoặc version không khớp. Khi đã có version mới, object cũ không được sử dụng để tự ghi đè.

Với JPA, có thể dùng @Version:

~~~java
@Entity
public class AccountEntity {
    @Id
    private UUID id;

    @Version
    private long version;

    private BigDecimal balance;
}
~~~

ORM có thể đưa version vào điều kiện UPDATE, phát hiện optimistic locking conflict khi flush/commit. Nếu xung đột, transaction có thể bị rollback; **object trong RAM vẫn có balance mong muốn**, không phải balance đã commit. Sau lỗi, cần load lại state và ra quyết định retry hoặc conflict theo hợp đồng.

### 10.3. Kiểm tra và cập nhật phải nằm trong cùng ranh giới

Sai:

~~~java
int available = product.getAvailable();
if (available >= requested) {
    order.setStatus(CONFIRMED); // Chỉ đổi object, không reserve tồn kho.
}
~~~

Đúng hơn cho mô hình tồn kho trong PostgreSQL là kiểm tra và giảm tại nguồn authoritative một cách nguyên tử:

~~~sql
UPDATE inventory
SET available = available - :requested,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND sku = :sku
  AND available >= :requested
RETURNING available, version;
~~~

Nếu không có row trả về thì chưa reserve được hàng. Một object tồn kho được đọc trước đó, dù là JPA managed, cũng không thể tự bảo đảm invariant “không bán vượt tồn” trong mọi lịch concurrency.

### 10.4. Row version chưa đủ cho bất biến nhiều hàng

@Version trên từng account ngăn cập nhật đè cùng một row, nhưng không bảo vệ mọi invariant liên quan hai row (ví dụ tổng hạn mức, số nhân viên trực tối thiểu) nếu transaction chỉ ghi các row khác nhau. Cần thiết kế constraint, khóa guard row, SERIALIZABLE hoặc protocol phù hợp và kiểm thử write skew. Không biến optimistic locking thành lời hứa “mọi race condition đều được giải quyết”.

## 11. Rollback và exception: object không biết cách tự phục hồi

Một lệnh service có thể thay nhiều object managed:

~~~java
@Transactional
public void settle(UUID orderId) {
    OrderEntity order = orders.findById(orderId).orElseThrow();
    order.setStatus(OrderStatus.PAID);

    paymentLedger.recordSettlement(orderId); // Có thể ném exception.
}
~~~

Nếu paymentLedger dùng cùng DB transaction và ném runtime exception dẫn tới rollback, trạng thái PAID trong object không phải dữ liệu bền vững. Nếu paymentLedger là HTTP API ngoài DB, nó có thể đã tạo side effect dù local transaction rollback; cần thiết kế riêng cho cả hai trường hợp.

### 11.1. Không bắt lỗi rồi coi là thành công

~~~java
@Transactional
public void unsafe(UUID orderId) {
    OrderEntity order = orders.findById(orderId).orElseThrow();
    order.setStatus(OrderStatus.PAID);

    try {
        publishOrUpdateSomething();
    } catch (Exception ex) {
        log.warn("Ignored failure", ex);
    }
    // Có thể vẫn COMMIT dù một business step bắt buộc đã thất bại.
}
~~~

Nếu side effect là điều kiện bắt buộc trước khi báo thành công, phải định nghĩa hành vi thất bại rõ, không dùng catch-all để hợp thức hóa state object. Mặt khác, nếu catch persistence exception nhưng transaction đã bị DB đặt vào trạng thái lỗi hoặc rollback-only, cố return bình thường có thể vẫn thất bại tại transaction boundary.

### 11.2. rollback không khôi phục mọi Java field

Sau rollback:

- Một entity/DTO giữ trong bộ nhớ có thể vẫn có giá trị setter đã gán.
- Object được publish vào event/callback ở thời điểm quá sớm có thể mang dữ liệu không bao giờ commit.
- Cache do app chủ động SET trước COMMIT có thể chứa giá trị chưa từng hợp lệ trong DB.
- Java List/Map của application không được DB transaction tự hoàn tác.

Phải phân tách **transaction database** với **mutation trong JVM**. Nếu cần trả kết quả sau rollback, không dùng trực tiếp entity đã lỗi; tạo error response, nạp lại dữ liệu hoặc dùng state machine phân biệt tentative và committed.

### 11.3. Outer transaction kết thúc sau khi inner method return

~~~java
@Transactional
public void placeOrder(Command cmd) {
    OrderEntity order = createOrder(cmd);
    outboxRepository.appendEvent(order.getId());
    // Một exception cuối phương thức có thể rollback cả hai thao tác.
}
~~~

Nếu createOrder trả entity có ID, không được công bố sự kiện externally chỉ vì ID đã tồn tại. Nếu outbox ở cùng local DB transaction, record outbox và order sẽ commit/rollback cùng nhau, còn dispatcher phát event sau commit. Đây là một ví dụ phân định rõ **ý định lưu** và **tác động bên ngoài sau lưu**.

## 12. Lỗi mạng tại COMMIT: kết quả chưa rõ

Một trường hợp khó hơn rollback xác định là **mất acknowledgment**:

~~~text
Service                  PostgreSQL
  |                          |
  |------ COMMIT ----------->|
  |                          | ghi nhận COMMIT
  |<--- phản hồi bị mất ------X
  |
  | SQLException/timeout
  | Không biết chắc transaction đã commit hay chưa
~~~

Không có đủ bằng chứng để kết luận “chưa lưu” chỉ vì caller nhận timeout. Mức durability của commit còn phụ thuộc cấu hình WAL, synchronous_commit, fsync và topology được hỗ trợ; nhưng trong tình huống ACK mất, chính trạng thái đã commit hay chưa có thể chưa rõ với caller.

### 12.1. Không retry mù với ID mới

Sai:

~~~java
try {
    createOrder(UUID.randomUUID(), request);
} catch (SQLException ex) {
    createOrder(UUID.randomUUID(), request); // Có thể tạo đơn trùng.
}
~~~

Nếu lần đầu đã COMMIT nhưng ACK mất, lần thứ hai có thể tạo thêm một đơn cho cùng ý định.

Thiết kế phù hợp hơn:

- Client/command có một idempotency key ổn định trong phạm vi tenant.
- Database có UNIQUE cho (tenant_id, request_key).
- Ghi idempotency record và business effect trong cùng local transaction.
- Retry dùng **cùng key và payload**, đọc lại authoritative state khi outcome không rõ.
- Trả kết quả trước đó hoặc trạng thái cần đối soát, thay vì tự sinh thêm business operation.
- Không dựa vào một lần not found trên replica chậm để kết luận transaction chưa xảy ra.

### 12.2. Tách lệnh ghi và biểu diễn dữ liệu trả về

Một API có thể trả:

~~~json
{
  "orderId": "4d9b5006-3c83-4f59-89a7-24ebfe777311",
  "status": "CONFIRMED",
  "version": 8
}
~~~

Nhưng contract phải nói **khi nào response này được gửi**. Với Spring proxy sở hữu transaction mới và commit thành công, controller gọi service sau proxy có thể nhận trạng thái đã commit. Nếu trả HTTP response trực tiếp từ callback bên trong transaction hoặc streaming trước commit, có nguy cơ gửi success trước khi transaction boundary thực sự hoàn tất.

Nếu kết quả commit là UNKNOWN, đừng tạo response “COMPLETED” chỉ vì DTO có status=CONFIRMED; dùng error/pending-reconciliation contract phù hợp.

## 13. Đọc sau ghi: primary, replica, cache và persistence context

Sau khi primary xác nhận COMMIT, một lời gọi đọc có thể vẫn trả dữ liệu cũ nếu nó đi qua **nguồn khác**.

~~~mermaid
flowchart LR
    W["Java writer"] --> P[("PostgreSQL primary")]
    P -->|WAL replay trễ| R[("Read replica")]
    P -->|Invalidation/refresh trễ| C[("Redis cache")]
    G["GET API"] --> Q{"Read routing"}
    Q --> P
    Q --> R
    Q --> C
~~~

### 13.1. Replica lag không chứng minh COMMIT đã thất bại

~~~text
T1: UPDATE orders SET status=CONFIRMED trên primary; COMMIT OK
T2: GET trên replica còn ở version cũ -> PENDING
T3: Replica replay COMMIT
T4: GET với snapshot mới -> CONFIRMED
~~~

Nếu API hứa read-your-writes, đường GET sau ghi phải đọc primary hoặc dùng cơ chế chờ replica đạt version/LSN tương ứng với commit, cùng snapshot đủ mới. Một object trong controller chứa CONFIRMED không làm replica tiến nhanh hơn.

### 13.2. Cache hit có thể là stale

Redis chứa trạng thái PENDING từ trước. Java object mới sau UPDATE đã CONFIRMED, nhưng cache entry vẫn còn PENDING vì invalidation chưa chạy hoặc mất event. **Không thể chọn thứ tự cache->DB làm cơ sở bảo đảm** nếu use case cần trạng thái mới nhất; phải có cache policy và ranh giới source of truth rõ.

Ngược lại, cập nhật cache thành CONFIRMED **trước khi DB COMMIT** có thể khiến GET thấy trạng thái chưa bao giờ được commit nếu DB rollback. Gọi afterCommit callback giúp tránh một số lỗi nhưng còn cửa sổ process chết sau COMMIT trước callback; outbox bền vững là một lựa chọn cho invalidation cần phục hồi.

### 13.3. JPA first-level cache có thể giữ cùng managed object

Trong một EntityManager/persistence context, entity được quản lý có identity map. Gọi find() lại với cùng ID có thể trả chính instance đang quản lý, không nhất thiết tạo một SELECT độc lập từ DB. Vì vậy:

~~~java
OrderEntity e = entityManager.find(OrderEntity.class, id);
e.setStatus(OrderStatus.CONFIRMED);

OrderEntity again = entityManager.find(OrderEntity.class, id);
assertSame(e, again);
~~~

Test này **không chứng minh database đã nhận UPDATE**; nó có thể chỉ chứng minh JPA trả cùng managed instance. Khi cần kiểm tra trạng thái đã lưu thực tế, phải kết thúc transaction/clear context phù hợp rồi đọc từ connection/context mới sau COMMIT, hoặc kiểm tra độc lập trong phạm vi test.

### 13.4. Refresh không tự thay thế commit

EntityManager.refresh(entity) có thể tải lại state từ DB cho managed entity theo semantics provider, nhưng nếu transaction hiện tại chưa commit hoặc snapshot/isolation không phù hợp, đọc lại **trong cùng transaction** vẫn không phải bằng chứng độc lập về một commit đã bền vững. Test cần quan sát từ transaction/connection mới sau khi writer đã commit.

## 14. Side effect bên ngoài dựa vào object chưa commit

Một lỗi thiết kế nguy hiểm là phát sự kiện hoặc gửi thông báo ngay khi object đổi state:

~~~java
@Transactional
public void confirm(UUID orderId) {
    OrderEntity order = orders.findById(orderId).orElseThrow();
    order.setStatus(OrderStatus.CONFIRMED);

    eventPublisher.publish(
        new OrderConfirmed(order.getId(), order.getStatus())
    );

    // DB flush/commit có thể còn ở phía sau.
}
~~~

Một consumer có thể nhận OrderConfirmed trong lúc transaction vẫn chưa commit. Nếu consumer đọc primary bằng connection khác, nó có thể vẫn thấy PENDING; nếu outer transaction cuối cùng rollback, event CONFIRMED không còn tương ứng với trạng thái authoritative.

### 14.1. Các cách triển khai và giới hạn

| Cách phát thông báo | Điều có thể bảo đảm | Vấn đề còn lại |
|---|---|---|
| Publish ngay sau setter | Dữ liệu object đã đổi | DB chưa commit, event có thể sai |
| Publish sau flush | SQL đã được thực thi trong transaction | Vẫn có thể rollback |
| Callback afterCommit trong JVM | Không chạy trước commit thành công theo callback contract | JVM có thể chết sau commit trước khi phát |
| Transactional outbox trong cùng DB transaction | Lưu event intent cùng business row, cùng commit/rollback | Dispatch bất đồng bộ, duplicate/out-of-order cần xử lý |
| Message broker transaction riêng | Broker commit theo policy broker | Không tự nguyên tử với DB local |

### 14.2. Transactional outbox: intent cùng commit

~~~sql
CREATE TABLE order_outbox (
    event_id uuid PRIMARY KEY,
    tenant_id bigint NOT NULL,
    order_id uuid NOT NULL,
    event_type text NOT NULL,
    order_version bigint NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);
~~~

Application có thể ghi business row và outbox row trong cùng transaction PostgreSQL. Dispatcher đọc các outbox record đã commit rồi publish, với retry và idempotency. Khi DB rollback, outbox event cũng rollback; không công bố một trạng thái chỉ có trong object tạm thời.

**Không suy outbox tạo exactly-once trên mọi hệ thống.** Một message có thể được phát lặp sau timeout hoặc consumer restart. Event ID, version, deduplication và idempotent handler vẫn cần thiết.

### 14.3. Khi không nên coi DTO response là event durable

Một DTO chứa confirmed=true có thể chỉ là một kết quả tính toán dự kiến. Nếu ứng dụng đưa DTO đó vào queue in-memory trước commit, queue có thể xử lý một nghiệp vụ chưa xảy ra. Chỉ dùng payload từ đối tượng sau khi đã ràng buộc được nó với commit hợp lệ theo giao thức rõ.

### 14.4. External call trước COMMIT còn giữ connection lâu

Gọi HTTP/payment trong transaction local rồi chờ có thể giữ connection và row locks quá lâu. Khi external call thành công nhưng DB rollback, lại cần compensation. Thường nên tách workflow thành trạng thái bền vững như PENDING, outbox event và bước xác nhận sau, thay vì coi việc setStatus(CONFIRMED) là đã hoàn thành mọi hệ ngoài.

## 15. Định nghĩa thời điểm thành công trong hợp đồng ứng dụng

Câu hỏi “đã lưu hay chưa” chỉ trả lời được sau khi hợp đồng định nghĩa thành công ở mốc nào.

### 15.1. Ba lớp success

| Lớp | Ví dụ | Có thể thông báo gì? |
|---|---|---|
| Ý định được tiếp nhận | Request được validate và đưa vào queue bền vững | ACCEPTED/PENDING nếu queue là authoritative cho ý định |
| Ghi vào transaction local và commit OK | Order row/outbox được xác nhận ở primary | Hoàn tất bước lưu cục bộ theo durability policy |
| Nghiệp vụ xuyên dịch vụ đã hoàn tất | Payment capture, inventory reserve, notification hoặc shipping đồng bộ | COMPLETED khi workflow được chứng minh đạt điều kiện |

Không gọi một trạng thái tạm trong object là cả ba. Nếu backend chỉ nhận yêu cầu async, HTTP 202 với operation ID thường minh bạch hơn 200 “đã hoàn tất”, nhưng lựa chọn status phụ thuộc giao thức API cụ thể.

### 15.2. Dùng command và result thay vì để entity tự báo commit

Ví dụ hai lớp ý nghĩa tách biệt:

~~~java
public record ConfirmOrderCommand(
    long tenantId, UUID orderId, long expectedVersion
) {}

public record ConfirmOrderResult(
    UUID orderId, long committedVersion, String status
) {}
~~~

Application service nhận command, xác nhận precondition, ghi đúng transaction; controller chỉ nhận ConfirmOrderResult sau khi transaction proxy thuộc quyền sở hữu service hoàn tất thành công. Cần tránh method tham gia outer transaction chưa commit mà vẫn trả result dưới tên committedVersion. Nếu giao dịch còn đang chạy trong scope ngoài, dùng tên tentativeVersion hoặc định nghĩa rõ result chỉ có hiệu lực sau outer commit.

### 15.3. Không trả entity JPA làm hợp đồng durable

Trả trực tiếp managed entity ra controller có rủi ro:

- Lazy fields phát sinh SQL sau khi transaction đóng.
- Entity tiếp tục mutable và dễ bị sửa ngoài ý muốn.
- Serialization tiết lộ field nội bộ/PII không được phép.
- GET response thể hiện giá trị object chưa refresh từ database.
- Vòng tham chiếu quan hệ JPA gây lỗi serialize/N+1.
- Caller tưởng entity đang gắn DB qua mọi tầng ứng dụng.

Nên trả DTO immutable được định nghĩa theo API và nguồn dữ liệu, phân biệt representation tạm với kết quả bước commit. DTO vẫn không phải bằng chứng độc lập của database nếu đã được tạo trước commit.

## 16. Thiết kế transaction và repository contract rõ ràng

Một cách giảm nhầm lẫn là làm contract của repository nói rõ mức bảo đảm.

### 16.1. Tránh tên API khiến caller suy quá mức

Các tên như save(), update(), persist() tiện dụng nhưng không cho biết:

- Có tham gia transaction ngoài không?
- Có flush ngay hay trì hoãn?
- Có phát event bên ngoài không?
- Có dùng primary hay một cache write-behind?
- Có chống ghi đè dữ liệu cạnh tranh không?
- Có trả giá trị sau DB-generated column/trigger không?

Không nhất thiết phải đổi tên mọi method, nhưng **documentation và test** phải chỉ ra ranh giới kết quả. Ví dụ updatePriceIfVersionMatches(...), createInCurrentTransaction(...) hoặc reserveInventoryAtomically(...) diễn tả điều kiện quan trọng rõ hơn save(entity) chung chung.

### 16.2. Chỉ một chủ sở hữu của transaction cho một use case

Ví dụ với Spring:

~~~java
@Service
public class ChangePriceService {
    private final ProductWriteRepository products;
    private final OutboxRepository outbox;

    @Transactional
    public long changePrice(
            long tenantId,
            UUID productId,
            long expectedVersion,
            BigDecimal newPrice) {
        long version = products.updateIfVersionMatches(
            tenantId, productId, expectedVersion, newPrice
        );
        outbox.appendProductPriceChanged(tenantId, productId, version);
        return version;
    }
}
~~~

Ví dụ giả định hai repository dùng cùng DataSource và transaction manager; lời gọi thông qua transaction proxy; updateIfVersionMatches trả version mới hoặc ném conflict nếu UPDATE không ảnh hưởng row. Method body trả version trước commit do proxy thực hiện; caller bên ngoài proxy chỉ được dùng giá trị ấy làm kết quả commit khi proxy đã hoàn tất thành công và không có transaction ngoài chưa kết thúc.

Nếu một repository tự mở transaction mới trong khi service tưởng mọi ghi thuộc cùng transaction, ranh giới atomicity bị phá. Cần test với lỗi ở bước thứ hai.

### 16.3. Đọc lại khi nào và từ đâu?

Sau khi DB commit, đọc lại hữu ích khi:

- Cần giá trị được database tính toán bằng DEFAULT, GENERATED, TRIGGER.
- Cần chắc chắn state theo một snapshot mới.
- Muốn đối soát UPDATE/DELETE và constraint nhiều bảng.
- Cần trả representation authoritative cho client.

Nhưng không phải mọi write cần một SELECT thêm; RETURNING, JPA generated-value mapping hoặc DTO từ giá trị đã được xác nhận có thể đủ theo contract. Nếu chọn đọc lại, phải biết nguồn là primary, transaction/snapshot mới hay replica trễ; một readback sai nguồn có thể gây thêm hiểu lầm.

### 16.4. Repository không phải nơi đưa ra tất cả quyết định kinh doanh

Một repository có thể bảo đảm câu UPDATE có điều kiện; domain/application service quyết định khi nào được phép chuyển PENDING → CONFIRMED, trừ tồn kho, gửi email hoặc thu phí. Object chứa state mong muốn không thể thay thế transaction bảo vệ bất biến hoặc workflow xuyên hệ thống.

## 17. Bảo mật: object nhìn thấy dữ liệu không đồng nghĩa được phép lưu hoặc đọc

Trong hệ thống multi-tenant, một object có thể được deserialize từ request hoặc cache:

~~~java
OrderEntity candidate = request.toOrderEntity();
candidate.setTenantId(request.tenantId());
repository.save(candidate);
~~~

Nếu tenantId đến từ input không được xác thực, request có thể đề nghị ghi vào tenant khác. Kể cả DTO đầy đủ trông hợp lệ, vẫn phải:

- Xác định tenant và actor từ security context đáng tin.
- Truy vấn/giao dịch theo tenant scope.
- Kiểm tra ownership, role và field-level authorization.
- Không chấp nhận client tùy ý gửi version, status đặc biệt hoặc những trường chỉ hệ thống được điều khiển.
- Dùng parameterized SQL, không nối dữ liệu vào câu truy vấn.
- Tránh trả entity có internal state hoặc credential trong response.
- Ghi audit tương ứng với committed action, không chỉ object mutation dự kiến.

### 17.1. Mass assignment qua entity trực tiếp

Nếu controller bind JSON trực tiếp vào entity có field isAdmin, balance, status hoặc tenantId rồi gọi save, client có thể tự sửa trường nghiệp vụ được bảo vệ. Tách command DTO chỉ gồm field được phép thay đổi, chạy validation và load đối tượng hiện tại trong transaction có quyền phù hợp.

### 17.2. Tenant isolation và trường version

Khi optimistic update, SQL cần cả tenant/id/version:

~~~sql
UPDATE orders
SET status = :status,
    version = version + 1
WHERE tenant_id = :authorized_tenant
  AND id = :order_id
  AND version = :expected_version
  AND deleted_at IS NULL
RETURNING version;
~~~

Một entity được load với ID hợp lệ nhưng thuộc tenant khác không phải bằng chứng caller được phép cập nhật. SQL WHERE phải dùng tenant được xác thực; tránh phân loại lỗi 0 hàng làm lộ sự tồn tại của record ở tenant khác.

## 18. Schema evolution: class Java và schema DB có thể lệch pha

Một ứng dụng có field mới trong entity không đồng nghĩa database đã có cột tương ứng:

~~~java
@Column(name = "shipping_address_encrypted")
private byte[] shippingAddressEncrypted;
~~~

Nếu migration thêm cột chưa được áp dụng trên một shard/replica, lệnh SQL có thể thất bại. Nếu cột tồn tại nhưng dữ liệu lịch sử chưa backfill, object đọc lại có thể chứa null hoặc default, khác giả định của code mới.

### 18.1. Expand → migrate → contract

~~~mermaid
flowchart LR
    A["DB schema cũ"] --> B["Thêm cột mới"]
    B --> C["Writer tương thích"]
    C --> D["Backfill"]
    D --> E["Đối soát"]
    E --> F["Chuyển reader"]
    F --> G["Contract cột cũ"]
~~~

Kiểm tra:

- Binary cũ và mới có tương thích schema ở giai đoạn rolling deployment?
- Writer cũ có thể tiếp tục ghi thiếu cột mới không?
- Dữ liệu mới và cũ có mapping nhất quán trong transition?
- Backfill có idempotency, checkpoint và điều kiện không ghi đè writer mới?
- Reader mới có phân biệt dữ liệu chưa backfill với business null không?
- Dữ liệu trên replica/read model đã theo kịp khi cutover?
- Đã kiểm chứng sau commit chứ không dựa vào object mới dựng từ DTO?

### 18.2. Entity annotation không phải schema thực tế

Các annotation @Column(nullable=false), @Version, @Enumerated hay @Index mô tả mapping/ý định ở tầng Java hoặc công cụ schema; **không tự chứng minh** PostgreSQL production đã có constraint/index/migration tương ứng. Cần kiểm tra migration được áp dụng, cấu trúc database và integration test trên schema thực.

Tương tự, code có @Transactional không bảo đảm transaction được chạy đúng qua proxy. Không dựa vào annotation như bằng chứng duy nhất: hãy test behavior và observability.

## 19. Kiểm thử đúng: dùng bằng chứng từ database, không dùng lại object làm oracle

Một test có thể pass dù chưa có bản ghi nào được commit:

~~~java
@Test
void wrongTest() {
    OrderEntity order = new OrderEntity(...);
    order.setStatus(OrderStatus.CONFIRMED);
    orderRepository.save(order);

    assertEquals(OrderStatus.CONFIRMED, order.getStatus());
}
~~~

Assertion chỉ kiểm tra object trong RAM. Kể cả test chạy trong @Transactional và save phát SQL, toàn bộ transaction kiểm thử có thể bị rollback ở cuối, trong khi getter vẫn trả CONFIRMED.

### 19.1. Các cấp bằng chứng khác nhau

| Bằng chứng | Đáng tin cho điều gì? | Không đủ cho điều gì? |
|---|---|---|
| Getter object | Object giữ field mong muốn | DB ghi thành công |
| Mock verify(save) | Method được gọi | SQL và commit |
| JPA find cùng EntityManager | State của persistence context | Truy vấn độc lập từ DB |
| flush() không lỗi | SQL được xử lý ở mốc flush | Commit đã hoàn tất |
| Kiểm tra row trong cùng transaction | Tính nhất quán trong snapshot/transaction đó | Đã bền vững sau commit |
| Query qua connection/transaction mới sau COMMIT | Trạng thái committed có thể được quan sát từ nguồn đó | Mọi replica/cache đã cập nhật |
| Test restart/fault injection | Một số bảo đảm phục hồi trong kịch bản đã thử | Mọi crash và mất dữ liệu bất khả thi |

### 19.2. Repository integration test với PostgreSQL thật

Với JUnit 5, Spring Boot và Testcontainers, test có thể tạo PostgreSQL test instance và chạy các migrations giống production. Không cần dùng production DB hoặc kết nối tới môi trường chung.

Ví dụ khung:

~~~java
@SpringBootTest
@Testcontainers
class OrderPersistenceIT {
    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void postgresProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired OrderApplicationService application;
    @Autowired JdbcTemplate jdbc;
}
~~~

Mẫu phụ thuộc cấu hình migrations, dependency Testcontainers, JUnit/Spring và các bean của ứng dụng. Điều quan trọng là test **không dùng database giả khác semantics** nếu mục tiêu là chứng minh PostgreSQL constraint, transaction, isolation và SQL dialect.

### 19.3. Test transaction commit rồi query bằng snapshot mới

Một test ở tầng tích hợp:

~~~java
@Test
void confirmedOrderIsVisibleAfterSuccessfulCommit() {
    UUID id = fixture.createCommittedPendingOrder();

    // Gọi qua Spring proxy của service để nó sở hữu transaction.
    application.confirmOrder(id);

    // Không để test method bị bao trong một outer transaction.
    // JdbcTemplate thực hiện SELECT từ DB sau khi service trả về.
    String status = jdbc.queryForObject(
        "SELECT status FROM orders WHERE id = ?",
        String.class,
        id
    );

    assertEquals("CONFIRMED", status);
}
~~~

**Giả định phải công bố:** fixture đã commit, application.confirmOrder được gọi qua proxy với transaction của chính nó, PostgreSQL primary là nguồn đọc, test không có outer @Transactional và query sau dùng một statement/snapshot mới.

Nếu test được bọc trong @Transactional từ JUnit/Spring Test, việc đọc lại ở cùng transaction không chứng minh commit. Test cũng không nên chỉ gọi repository.findById() trong một EntityManager đang giữ managed entity từ bước cập nhật rồi kết luận đã persist.

### 19.4. Test rollback sau khi object đã đổi

~~~java
@Test
void objectMutationIsNotProofOfCommit() {
    UUID id = fixture.createCommittedPendingOrder();

    assertThrows(IllegalStateException.class, () ->
        tx.executeWithoutResult(status -> {
            OrderEntity order =
                entityManager.find(OrderEntity.class, id);
            order.setStatus(OrderStatus.CONFIRMED);
            entityManager.flush();

            throw new IllegalStateException("Simulated failure");
        })
    );

    String persisted = jdbc.queryForObject(
        "SELECT status FROM orders WHERE id = ?",
        String.class,
        id
    );
    assertEquals("PENDING", persisted);
}
~~~

Ví dụ giả định tx là TransactionTemplate của cùng JPA transaction manager, fixture đã commit, EntityManager là container-managed và test không có outer transaction. Nếu dùng một EntityManager cũ còn giữ entity modified sau rollback, cần clear/close context trước khi assert. Mục tiêu là kiểm tra dữ liệu đã commit từ nguồn DB, **không gọi lại getter trên order đã rollback**.

### 19.5. Test optimistic-lock conflict

Một kịch bản xác định:

1. T1 đọc row version=7.
2. T2 đọc cùng row version=7 và commit cập nhật version=8.
3. T1 cố commit thay đổi từ version=7.
4. T1 phải conflict/rollback theo contract.
5. Database giữ thay đổi của T2; object T1 có thể giữ trạng thái mong muốn nhưng chưa được lưu.

Với JPA, xung đột có thể xuất hiện ở flush/commit, nên test phải đặt assertion quanh **toàn bộ transaction boundary**, không chỉ setter. Với JDBC dùng WHERE version=7, kiểm tra affected rows=0 và dữ liệu committed không bị ghi đè.

### 19.6. Test dữ liệu do database tự sinh

Nếu DB dùng generated/default/trigger, test nên assert:

- Giá trị SQL lưu phù hợp constraint và mapping.
- Khi lệnh INSERT dùng RETURNING, object/result nhận giá trị DB trả đúng.
- Khi cần đối soát sau commit, query mới thấy giá trị được lưu.
- Các trường không được phép sửa không bị ghi đè.
- BigDecimal/timezone/nullable được xử lý theo contract, không chỉ bằng object.equals() cũ.

### 19.7. Test đọc từ replica/cache theo từng bảo đảm

Nếu use case hứa eventual consistency, test nên xác định giới hạn chờ và cách trả kết quả stale. Nếu hứa read-your-writes, test phải mô phỏng replica lag/cache stale và kiểm tra routing về primary hoặc cơ chế version/LSN phù hợp.

Một test “POST xong GET sau 200 ms luôn đúng” chỉ là thực nghiệm trong một điều kiện, không phải chứng minh consistency khi workload/network thay đổi.

### 19.8. Đừng dùng SQL log làm bằng chứng commit duy nhất

Log có dòng UPDATE chứng minh một câu SQL có thể đã được chuẩn bị/gửi, không chứng minh COMMIT. Hibernate SQL logging có thể ghi câu SQL được phát ngay cả khi transaction sau đó rollback.

Để điều tra, kết hợp transaction outcome, logs theo correlation ID, affected rows, SQLSTATE, audit/outbox transaction và readback authoritative. Không log thông tin nhạy cảm hoặc toàn bộ SQL parameter nếu chúng chứa PII.

## 20. Case study: xác nhận đơn hàng và gửi sự kiện

### 20.1. Thiết kế lỗi

Order Service muốn xác nhận một đơn sau khi kiểm tra tồn kho:

~~~java
@Transactional
public void confirm(UUID orderId) {
    OrderEntity order = orders.findById(orderId).orElseThrow();

    if (inventoryCache.getAvailable(order.getSku()) > 0) {
        order.setStatus(OrderStatus.CONFIRMED);
        orderEventPublisher.publish(
            new OrderConfirmed(orderId)
        );
    }
}
~~~

Các sai lầm chồng nhau:

1. Dùng cached inventory làm căn cứ quyết định cuối cùng thay vì reserve tại nguồn authoritative.
2. Gọi setStatus rồi coi order đã được lưu.
3. Publish event trước khi transaction DB commit.
4. Không xác minh optimistic version hoặc transition hợp lệ.
5. Không phân biệt exception tại COMMIT với nghiệp vụ chưa xảy ra.
6. Không có idempotency cho confirm command.
7. Consumer có thể đọc replica chưa replay bản cập nhật.

### 20.2. Thiết kế an toàn hơn

Giả sử order và inventory nằm trên **cùng PostgreSQL** và có thể được bảo vệ trong một local transaction. Nếu thuộc hai dịch vụ/DB riêng, cần workflow khác thay vì dùng một transaction giả.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant DB as PostgreSQL primary
    participant O as Outbox Worker
    participant B as Message Broker
    API->>DB: BEGIN
    API->>DB: Verify order version/state
    API->>DB: Atomic inventory reservation
    API->>DB: Update order status/version
    API->>DB: Insert outbox event
    API->>DB: COMMIT
    DB-->>API: COMMIT OK
    API-->>API: Return confirmed response
    O->>DB: Read committed outbox
    O->>B: Publish event (retryable)
~~~

Một câu lệnh reserve tồn kho có điều kiện:

~~~sql
UPDATE inventory
SET available = available - :requested,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND sku = :sku
  AND available >= :requested
RETURNING available, version;
~~~

Chỉ khi reserve thành công mới cập nhật order theo expectedVersion và transition hợp lệ trong cùng transaction. Ghi outbox event cùng transaction. Nếu bất kỳ bước nào lỗi, toàn bộ local transaction rollback và không có OrderConfirmed event **đã commit** trong outbox.

Sau khi proxy transaction commit thành công, controller có thể trả representation tương ứng. Consumer phải chịu được event duplicate và có thể phải chờ read replica bắt kịp nếu nó dùng replica để đọc order theo event.

### 20.3. Nếu inventory ở DB của dịch vụ khác

Nếu Order DB và Inventory DB độc lập:

- Không coi @Transactional của Order Service là transaction bao cả hai DB/HTTP.
- Không công bố CONFIRMED chỉ vì object order đã đổi trước khi Inventory Service reserve được hàng.
- Thiết kế state PENDING_RESERVATION, outbox, idempotent reservation command, deadline và trạng thái thất bại/compensation.
- Source of truth của mỗi dữ liệu phải được xác định rõ.
- Trạng thái hoàn tất nghiệp vụ đến khi những điều kiện xuyên dịch vụ được chứng minh theo workflow.

Đây là nơi sự nhầm lẫn giữa **object state** và **durable distributed state** dễ dẫn tới đơn hàng đã “xác nhận” nhưng không có hàng thật.

### 20.4. Ma trận kiểm chứng case study

| Sự cố | Hệ quả nếu tin object | Bảo vệ và test |
|---|---|---|
| Setter chạy, DB rollback | Trả CONFIRMED sai | Test rollback + readback primary |
| INSERT outbox thất bại | Event không có hoặc workflow dở dang | Transaction chung + assert cả hai rollback |
| Redis tồn kho stale | Bán vượt tồn | Atomic reserve trên authoritative DB |
| Hai request confirm version cũ | Cùng quyết định dựa trên snapshot stale | Optimistic version, idempotency |
| COMMIT OK nhưng event worker chết | Event không phát | Outbox bền vững, retry |
| Event đến hai lần | Consumer tạo side effect trùng | Event ID, dedup/idempotency |
| COMMIT ACK bị mất | Client tạo lại đơn | Stable request key + reconciliation |
| Replica chưa replay | Consumer GET thấy PENDING | Primary/read-your-writes/watermark theo contract |
| JPA entity detached | setStatus không ra UPDATE | Transaction-bound load/update hoặc explicit command |
| Trigger thay field | Response khác giá trị DB | RETURNING/readback và mapping contract |

## 21. Các dấu hiệu code review cần cảnh giác

| Mẫu code/nhận định | Rủi ro | Câu hỏi review |
|---|---|---|
| order.setStatus(CONFIRMED); return ok() | Chưa có bằng chứng ghi | Ai sở hữu transaction và COMMIT? |
| repository.save(entity); publish(event) | Event có thể đi trước commit | Có outbox hoặc protocol an toàn? |
| entity.getId() != null ⇒ persisted | ID có thể sinh trước INSERT/COMMIT | Row đã commit ở nguồn nào? |
| saveAndFlush() ⇒ durable | Flush chưa phải COMMIT | Outer transaction có thể rollback không? |
| @Transactional trên private/self-call method | Proxy không chặn lời gọi | Interceptor có thực sự chạy không? |
| Bắt DataAccessException rồi trả Optional.empty() | Biến lỗi hạ tầng thành not found | Có phân biệt failure vs absence? |
| Detach rồi sửa object | Setter không được ORM theo dõi | Ai gọi update/merge và kiểm tra version? |
| Merge detached entity đầy đủ từ request | Ghi đè field đã thay đổi | Có command DTO/expectedVersion? |
| Same EntityManager find() để verify | Có thể trả identity map | Đã kết thúc transaction và clear context chưa? |
| Cache SET trước DB COMMIT | Lộ trạng thái chưa commit | Chính sách invalidation/commit order nào? |
| Replica GET ngay sau primary POST | Có thể stale read | Contract có read-your-writes không? |
| Checked exception bị catch/return | Transaction có thể vẫn commit | Rollback rules và failure policy? |
| REQUIRES_NEW event/audit không chủ đích | Side effect tách khỏi business commit | Có cần cùng transaction? |
| Test chỉ verify(mock.save) | Không biết SQL thực | Có integration test trên DB thật? |
| Đưa entity trực tiếp vào controller | Leak field/lazy load/DTO sai | Có DTO theo quyền và trạng thái commit? |
| Mất kết nối ⇒ retry với UUID mới | Duplicate khi commit outcome unknown | Có idempotency key ổn định? |

**Điểm chung:** không thể suy tính bền vững của một thay đổi chỉ từ tên method, annotation, ID, getter hoặc log SQL. Phải biết ranh giới giao dịch và sự thật authoritative mà hành động đó phụ thuộc.

## 22. Quy trình chẩn đoán khi object đúng nhưng dữ liệu lưu không đúng

Khi gặp lỗi “trong log object đã CONFIRMED nhưng query DB vẫn PENDING”, đừng vội thêm save(), flush() hoặc sleep(). Hãy điều tra theo thứ tự ranh giới:

### 22.1. Bước 1 — Xác định bản ghi và nguồn dữ liệu có thẩm quyền

- Object có đúng tenantId, primary/business key và version không?
- Query kiểm chứng đang đọc primary, read replica, cache, search index hay test DB khác?
- Có soft delete, row-level security, schema/search_path hoặc transaction snapshot gây sai phạm vi không?
- Request ID, command ID và timestamp đã đối chiếu đúng nghiệp vụ chưa?

**Không suy từ một GET stale trên replica rằng primary chưa commit.**

### 22.2. Bước 2 — Kiểm tra trạng thái object và context

- Object được tạo mới, managed, detached hay removed?
- Có cùng EntityManager/persistence context đang hoạt động không?
- Setter có gọi trên đúng instance managed không?
- Lệnh repository.save() có được dùng đúng semantics persist/merge không?
- Có mapper tạo bản copy hoặc immutable DTO mà code chỉ sửa bản copy không?
- Có mở transaction read-only hoặc self-invocation khiến flush/transaction khác dự kiến không?

Ví dụ:

~~~text
Object in memory:       status=CONFIRMED
Persistence context:    DETACHED
SQL UPDATE emitted:     NONE
Authoritative DB:       PENDING
Root cause:             sửa detached entity, không có đường ghi
~~~

### 22.3. Bước 3 — Tìm SQL và số hàng

- SQL INSERT/UPDATE/DELETE có thực sự chạy không?
- Điều kiện WHERE có đủ tenant, ID, version và trạng thái hợp lệ không?
- UPDATE affected row count bằng bao nhiêu?
- Có DB constraint, foreign key, trigger hoặc conversion gây lỗi không?
- Có flush mode, batching hoặc lịch flush trì hoãn không?
- Có SQL bị đưa vào transaction khác qua nhiều DataSource hoặc transaction manager không?

Không log PII hoặc query parameter nhạy cảm để debug. Dùng trace ID, SQL template, timing, affected rows, SQLSTATE và metadata an toàn.

### 22.4. Bước 4 — Theo dõi kết quả transaction

- Ai là owner của transaction?
- Method được gọi qua proxy @Transactional hay self-invocation?
- Transaction có tham gia outer scope không?
- Có exception sau khi set field, hoặc rollback-only bị đánh dấu?
- Có lỗi ở COMMIT, timeout hoặc mất kết nối khiến outcome chưa rõ?
- Với nhiều DB, có bước nào commit ở nguồn khác độc lập không?

Ví dụ:

~~~text
Object status:          CONFIRMED
SQL UPDATE emitted:     YES
Affected rows:          1
Transaction final:      ROLLBACK
Authoritative DB:       PENDING
Root cause:             side effect/step sau gây rollback
~~~

### 22.5. Bước 5 — Đọc lại qua nguồn và snapshot đúng

Sau COMMIT được xác nhận, dùng query rõ ràng trên source authoritative với transaction/snapshot mới. Nếu kết quả khác:

- Kiểm tra trigger/default/database-generated field.
- Kiểm tra writer khác cập nhật row sau commit.
- Đối chiếu version và audit/transaction logs theo chính sách.
- Kiểm tra dùng đúng schema/shard/tenant hay không.

Nếu primary đã đúng nhưng GET vẫn cũ, chuyển sang điều tra replication lag, cache invalidation, HTTP cache và ORM identity map.

### 22.6. Bước 6 — Chọn hướng sửa theo nguyên nhân

| Nguyên nhân | Hướng sửa thích hợp |
|---|---|
| Chỉ sửa POJO/DTO | Thực hiện lệnh ghi trong transaction đúng |
| Entity detached | Load managed entity trong transaction hoặc merge có version/contract |
| Flush trì hoãn | Hiểu ORM flush mode, test tại transaction boundary; flush khi cần phát hiện lỗi sớm |
| Transaction rollback | Sửa lỗi/transaction flow; đừng dựa vào object sau rollback |
| UPDATE count=0 | Xử lý not-found/conflict/sai tenant đúng contract |
| Trigger/DB default thay value | RETURNING/refresh/readback đúng nguồn |
| Concurrent writer | ExpectedVersion, constraint/locking theo invariant |
| COMMIT ACK mất | Idempotency/reconciliation, không retry với ID mới |
| Replica/cache stale | Routing theo freshness hoặc version/invalidation |
| Event phát quá sớm | Outbox/after-commit theo độ tin cậy cần thiết |
| API trả entity không phù hợp | DTO tách command/result, kiểm tra quyền và transaction |

**Không có một lời gọi save() bổ sung nào sửa được đồng thời tất cả lỗi trên.**

## 23. Bài tập tự kiểm tra

### Bài A — Setter trên managed entity

Một method @Transactional load Order entity managed rồi setStatus(CONFIRMED), không gọi save(). Không có exception.

**Hỏi:** Có thể được lưu không? Vì sao không nên nói setter đã trực tiếp commit?

**Gợi ý:** Trong JPA, dirty checking có thể ghi thay đổi khi flush/commit nếu context/transaction/provider cho phép. Setter chỉ đổi field object; commit được xác nhận ở boundary transaction, không ở setter.

### Bài B — Đối tượng đã detached

Một API nhận OrderEntity được serialize từ request, thay đổi status rồi trả entity đó mà không gọi repository nào.

**Hỏi:** Database có tự cập nhật không?

**Gợi ý:** Không. Đây là object detached/không được quản lý trong context hiện tại. Cần command DTO có quyền, load state authoritative rồi cập nhật trong transaction và bảo vệ concurrency.

### Bài C — saveAndFlush nhưng outer transaction rollback

Method A gọi repository.saveAndFlush(order) rồi trả entity. Method B là outer transaction, sau đó ném exception và rollback.

**Hỏi:** Có được coi order đã lưu bền vững không?

**Gợi ý:** Không. Flush đồng bộ SQL chờ nhưng chưa commit outer transaction. Object có thể giữ giá trị mới dù row committed không đổi.

### Bài D — Object ID khác null

Client sinh UUID trước INSERT, gửi response chứa UUID, nhưng INSERT bị DB từ chối bởi CHECK.

**Hỏi:** UUID có chứng minh bản ghi tồn tại không?

**Gợi ý:** Không. ID có thể được sinh trước DB statement và commit. Cần kết quả transaction và xử lý constraint.

### Bài E — Đọc lại bằng cùng EntityManager

Sau setStatus(CONFIRMED), service gọi entityManager.find() với ID cũ và nhận object CONFIRMED.

**Hỏi:** Đã chứng minh DB ghi chưa?

**Gợi ý:** Chưa. First-level cache/identity map có thể trả cùng managed instance. Kiểm chứng committed state bằng transaction/context mới tại nguồn authoritative.

### Bài F — Cập nhật stale object

T1 đọc account version 4 và giữ object. T2 cập nhật account thành version 5. T1 gửi lại toàn bộ entity stale để save.

**Hỏi:** Có thể xảy ra điều gì và bảo vệ như thế nào?

**Gợi ý:** Lost update hoặc optimistic-lock conflict. Dùng @Version hoặc UPDATE WHERE version=4, không merge tùy tiện tất cả stale field, trả conflict/refresh theo contract.

### Bài G — Trigger thay giá trị

Java INSERT giá tiền 19.999 vào cột numeric(12,2), sau đó database lưu 20.00 theo quy tắc ép scale.

**Hỏi:** Object getter có phản ánh giá trị committed chính xác không?

**Gợi ý:** Không chắc. Cần validation để tránh làm tròn không chủ ý và đọc DB-generated/stored representation khi contract yêu cầu.

### Bài H — Sự kiện gửi trước COMMIT

Java set Order CONFIRMED rồi publish event, cuối transaction bị rollback.

**Hỏi:** Consumer có thể nhận thông tin gì sai và thiết kế nào giảm rủi ro?

**Gợi ý:** Consumer đã nhận OrderConfirmed dù DB không commit. Ghi outbox cùng local transaction, dispatcher phát sau commit; consumer idempotent.

### Bài I — Mất acknowledgment COMMIT

DB đã commit nhưng socket lỗi khiến application nhận SQLException. Application retry tạo record mới bằng UUID mới.

**Hỏi:** Hậu quả và cơ chế bảo vệ?

**Gợi ý:** Có thể tạo duplicate nghiệp vụ. Dùng idempotency key ổn định, UNIQUE, đối soát authoritative và retry đúng ý định.

### Bài J — Replica trả dữ liệu cũ

POST thành công trên primary; GET đọc replica chưa replay nên trả PENDING.

**Hỏi:** Đây có phải chứng cứ POST thất bại không?

**Gợi ý:** Không. Có thể là replica lag. Nếu API cần read-your-writes, đọc primary hoặc kiểm tra watermark của replica.

### Bài K — Test unit với in-memory fake

FakeRepository lưu cùng object reference trong HashMap. Test sửa object rồi đọc lại fake thấy field mới, dù không gọi update.

**Hỏi:** Test đã chứng minh persistence adapter đúng chưa?

**Gợi ý:** Không. Kết quả đến từ mutable object aliasing. Cần integration test SQL/schema/transaction thật.

### Bài L — Checked exception không rollback

Method @Transactional cập nhật managed entity rồi ném một checked exception mà rollback rules không bao phủ.

**Hỏi:** Có chắc DB rollback không?

**Gợi ý:** Không. Phải xác minh Spring rollback configuration và test loại exception thực; mặc định thường rollback với runtime exception/Error chứ không phải mọi checked exception.

### Bài M — @Transactional gọi qua this

Service method ngoài gọi this.innerTransactional(), inner method có annotation @Transactional; không có outer transaction.

**Hỏi:** Annotation có chắc được áp dụng không?

**Gợi ý:** Với proxy-based Spring AOP thông thường, self-invocation bỏ qua proxy; cần gọi qua bean/proxy boundary phù hợp hoặc thay thiết kế, rồi kiểm chứng.

### Bài N — Dữ liệu vừa rollback nhưng trả HTTP 200

Controller dùng entity đã setStatus(PAID) để dựng response trước khi transaction hoàn tất. Sau đó DB constraint error.

**Hỏi:** API đang hứa sai điều gì?

**Gợi ý:** Nó đánh đồng representation dự kiến với kết quả committed. Response thành công phải gắn với ranh giới commit/nghiệp vụ theo contract; xử lý lỗi transaction thay vì gửi success sớm.

## 24. Checklist review trước khi coi dữ liệu là đã lưu

### Trạng thái object và cơ chế ORM

- [ ] Biết object là POJO/DTO, managed hay detached; không suy từ setter.
- [ ] Không dùng ID != null làm bằng chứng row đã commit.
- [ ] Hiểu persist, merge, dirty checking, flush và provider-specific ID generation.
- [ ] Không cho rằng save/saveAndFlush luôn commit một transaction độc lập.
- [ ] Không test persistence bằng getter của chính object vừa sửa.
- [ ] Khi cần xác nhận, đọc bằng context/transaction phù hợp, không vô tình lấy first-level cache.

### Giao dịch và lỗi

- [ ] Xác định chính xác transaction owner, propagation và DataSource/manager.
- [ ] Lời gọi @Transactional thực sự đi qua proxy hoặc cơ chế interception phù hợp.
- [ ] Đã kiểm tra rollback rules và exception handling; không nuốt lỗi bắt buộc.
- [ ] Không trả trạng thái committed trước khi transaction theo contract hoàn tất.
- [ ] Không coi flush hoặc affected row count là bằng chứng outer COMMIT.
- [ ] Không tái sử dụng object bị rollback như dữ liệu authoritative.
- [ ] Có xử lý COMMIT outcome UNKNOWN và idempotency khi cần.
- [ ] Các side effect ngoài DB không được nhầm là thuộc local transaction.

### Đồng thời và bất biến dữ liệu

- [ ] Có khóa/version hoặc cơ chế kiểm soát lost update khi nhiều writer.
- [ ] UPDATE/DELETE kiểm tra tenant, ID, trạng thái và expectedVersion phù hợp.
- [ ] Invariant quan trọng được bảo vệ ở DB/transaction, không chỉ trên object.
- [ ] Đã kiểm tra constraint/default/trigger/generated values và mapping kiểu dữ liệu.
- [ ] Nếu dùng JPA @Version, test xung đột tại flush/commit, không chỉ setter.
- [ ] Không merge toàn bộ detached entity stale từ request khi chỉ cần thay một phần.

### Đường đọc, event và bảo mật

- [ ] Phân biệt primary, replica, cache và ORM first-level cache.
- [ ] Read-your-writes được thiết kế rõ nếu API hứa đọc ngay sau ghi.
- [ ] Không cập nhật cache thành committed state trước DB commit nếu không có giao thức phù hợp.
- [ ] Event/notification gửi theo outbox/after-commit policy có giới hạn được hiểu rõ.
- [ ] Controller không bind/trả JPA entity tùy ý khi có field nội bộ hoặc quyền hạn.
- [ ] Tenant/actor đến từ security context đáng tin, không từ client tự tuyên bố.

### Kiểm thử và vận hành

- [ ] Có test PostgreSQL thật nếu contract phụ thuộc SQL, constraint hoặc isolation.
- [ ] Có test rollback sau setter và sau flush.
- [ ] Có test readback bằng transaction/connection mới sau commit.
- [ ] Có test concurrent writer, stale version và mutation không đúng tenant.
- [ ] Có test commit timeout, idempotent retry hoặc reconciliation nếu nghiệp vụ cần.
- [ ] Có test side effect không phát khi business transaction rollback.
- [ ] Traces/metrics thể hiện transaction outcome, version, SQLSTATE, source role và correlation ID.
- [ ] Không log plaintext nhạy cảm/secret chỉ để chứng minh SQL đã chạy.
- [ ] Có quy trình điều tra khi object đúng nhưng dữ liệu DB không khớp.

## 25. Kết luận

Lỗi **“Xem dữ liệu trong đối tượng là dữ liệu đã được lưu”** bắt nguồn từ việc trộn lẫn hai thế giới: bộ nhớ Java có thể thay đổi ngay theo setter, trong khi database chỉ chấp nhận và công bố trạng thái theo SQL, constraint, transaction, commit và replication của chính nó.

Một thiết kế persistence đáng tin cần luôn trả lời bốn câu hỏi:

1. **Đối tượng đang ở trạng thái nào?** POJO, managed hay detached?
2. **Database đã làm gì?** Chỉ nhận yêu cầu, đã thực thi SQL, đã flush hay đã commit?
3. **Dữ liệu nào là authoritative và ai đang đọc?** Primary, replica, cache hay persistence context?
4. **Có bảo đảm nào về lỗi và cạnh tranh?** Rollback, conflict, ambiguous commit, idempotency và side effect bên ngoài?

**Ghi nhớ:** giá trị trong object có thể là ý định, snapshot hoặc kết quả tạm. Nó chỉ trở thành dữ liệu đã được lưu theo nghĩa nghiệp vụ khi ranh giới persistence và transaction đã thực sự đáp ứng hợp đồng. Hãy kiểm chứng điều đó bằng trạng thái committed, bất biến dữ liệu và những test độc lập, thay vì tin vào getter hoặc tên save().
