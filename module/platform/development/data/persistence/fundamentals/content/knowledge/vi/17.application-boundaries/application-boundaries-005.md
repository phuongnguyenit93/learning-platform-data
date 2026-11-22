# Đơn vị công việc (unit of work) và theo dõi thay đổi

Một yêu cầu đặt hàng có thể cần trừ tồn kho, chuyển trạng thái đơn và ghi lịch sử thao tác. Nếu từng repository ghi ngay và xác nhận dữ liệu riêng lẻ, lỗi ở bước cuối sẽ để lại trạng thái nghiệp vụ dở dang. Mặt khác, khi dùng JPA/Hibernate, lập trình viên có thể chỉ sửa thuộc tính của một đối tượng Java mà không gọi UPDATE trực tiếp, nhưng cơ sở dữ liệu vẫn nhận câu SQL khi giao dịch được đồng bộ.

Để lý giải hai vấn đề này, cần hiểu **đơn vị công việc (unit of work – UoW)** và **theo dõi thay đổi (change tracking/dirty checking)**. Đây là những khái niệm quan trọng trong chương **Ranh giới ứng dụng** thuộc module **DATA_PERSISTENCE_FUNDAMENTALS**: thiết kế tầng persistence cho Java, kết nối mô hình dữ liệu, lược đồ và truy vấn với giao dịch, tính cô lập, xử lý lỗi và hiệu năng. Bài tập trung vào nguyên lý chung và cách triển khai bằng **JPA/Hibernate, Spring** và **JDBC**; một vài chi tiết như thời điểm phát SQL và thứ tự thực thi thay đổi tùy nhà cung cấp ORM, flush mode và cấu hình.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích UoW xác định **tập thay đổi cần xử lý cùng nhau** và vai trò của nó trong một thao tác nghiệp vụ.
- Phân biệt **UoW, persistence context, transaction và repository**; biết chúng liên quan nhưng không hoàn toàn đồng nghĩa.
- Mô tả vòng đời entity **new/transient, managed, detached, removed** trong JPA.
- Hiểu **dirty checking**, identity map, cách ORM phát hiện thay đổi và phát SQL tại **flush**.
- Phân biệt **flush** với **commit**; dự đoán kết quả khi rollback hoặc khi flush phát hiện lỗi.
- Đặt transaction boundary ở tầng ứng dụng phù hợp, giải quyết tranh chấp bằng optimistic locking hoặc cập nhật có điều kiện.
- Nhận diện những lối đi vượt qua tracking như **bulk update**, native SQL, thao tác qua DataSource khác, hoặc serialize đối tượng detached.

## 2. Unit of work là một đơn vị thay đổi có chủ đích

**Unit of work** là mẫu tổ chức trong đó các thay đổi liên quan tới một công việc được **ghi nhận và phối hợp xử lý** trước khi đưa xuống nơi lưu trữ. Trong ORM, một UoW thường theo dõi đối tượng đã được nạp, đối tượng mới, đối tượng sửa và đối tượng sẽ bị xóa, rồi phát các câu SQL phù hợp khi đồng bộ.

Hãy xét use case **xác nhận đơn hàng**:

~~~text
Người dùng xác nhận đơn
          |
          v
Application service: ConfirmOrder
          |
          +-- Nạp order
          +-- Kiểm tra trạng thái và quyền tenant
          +-- Nạp inventory
          +-- Kiểm tra còn hàng, trừ số lượng
          +-- Đánh dấu order = CONFIRMED
          +-- Ghi audit/outbox nếu nghiệp vụ yêu cầu
          |
          v
Đồng bộ các thay đổi xuống database
          |
          v
COMMIT toàn bộ hoặc ROLLBACK toàn bộ
~~~

Đơn vị công việc ở đây là **một ý định nghiệp vụ**, không đơn giản là “một câu UPDATE” hay “một lời gọi repository”. Nếu xác nhận đơn thành công thì những thay đổi bắt buộc phải nhất quán; nếu một bước thất bại, transaction phải hoàn tác phần chưa commit.

UoW có hai mặt:

1. **Mặt tổ chức trong ứng dụng:** quyết định thay đổi nào thuộc cùng use case, ai sở hữu các thực thể và khi nào có thể lưu.
2. **Mặt đồng bộ với DB:** theo dõi và chuyển thay đổi thành INSERT/UPDATE/DELETE, phối hợp commit/rollback với cơ chế giao dịch.

Không phải mọi UoW đều có change tracker tự động. **JDBC thuần** vẫn có thể thực hiện một unit of work bằng cách điều phối một Connection và transaction, nhưng ứng dụng tự quyết định câu SQL cần chạy. Ngược lại, **JPA** có persistence context để theo dõi entity, song ứng dụng vẫn phải thiết kế ranh giới nghiệp vụ đúng.

## 3. Phân biệt các khái niệm dễ bị gộp chung

| Khái niệm | Trách nhiệm chính | Không tự bảo đảm |
| --- | --- | --- |
| **Application service/use case** | Xác định một công việc nghiệp vụ và thứ tự các bước | Không tự tạo transaction nếu chưa cấu hình |
| **Unit of work** | Gom, theo dõi, phối hợp các thay đổi của công việc | Không tự tạo bảo đảm ACID trên nhiều hệ thống độc lập |
| **Persistence context (JPA)** | Quản lý các entity, danh tính và thay đổi cần đồng bộ | Không đồng nghĩa một transaction đang mở ở mọi mô hình scope |
| **EntityManager** | API tương tác persistence context, nạp, persist, remove, flush | Không tự biết mọi quy tắc nghiệp vụ |
| **Repository/DAO** | Đọc/ghi dữ liệu theo abstraction được chọn | Không nên tự ý quyết định commit của toàn use case |
| **Database transaction** | Cung cấp ranh giới ACID theo hệ quản trị và mức cô lập | Không quản lý tác dụng phụ như email/API ngoài DB |
| **Connection/DataSource** | Kênh truy cập và quản lý tài nguyên kết nối | Không tự gộp nhiều connection thành một transaction |

Trong cách tổ chức phổ biến với Spring và JPA, một lời gọi application service có **@Transactional** tạo ranh giới transaction; các repository sử dụng EntityManager tham gia cùng transaction. Persistence context thường gắn với transaction đó. Tuy nhiên, JPA còn cho phép các mô hình context khác như **extended persistence context**; vì vậy không thể định nghĩa “persistence context = transaction” trong mọi trường hợp.

## 4. Vòng đời entity và phạm vi được theo dõi

Entity trong JPA có những trạng thái chính:

| Trạng thái | Đặc điểm | Thay đổi thuộc tính có tự đồng bộ? |
| --- | --- | --- |
| **New/transient** | Object Java mới, chưa được persistence context quản lý | Chưa; cần persist hoặc cascade phù hợp |
| **Managed** | Được persistence context hiện tại quản lý | Thường có: dirty checking sẽ phát hiện và đưa thay đổi xuống DB lúc flush |
| **Detached** | Từng được quản lý nhưng hiện ở ngoài context đang xét | Không tự đồng bộ; cần nạp lại hoặc merge theo chủ đích |
| **Removed** | Entity được đánh dấu xóa trong context | ORM sẽ phát DELETE theo quy tắc flush, có thể chưa chạy ngay |

Ví dụ dưới đây minh họa một entity được nạp rồi sửa:

~~~java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, orderId);
order.confirm();                  // Sửa object managed.
// Không nhất thiết phải gọi entityManager.persist(order).
// Khi flush, ORM có thể phát UPDATE cho trạng thái mới.
~~~

Nếu object đã **detached**:

~~~java
PurchaseOrder detachedOrder = loadInOldPersistenceContext();
// Context cũ đã kết thúc, object này hiện không được quản lý.
detachedOrder.confirm();
// Thay đổi ở đây chưa chắc được lưu vào DB.
~~~

Tên method **loadInOldPersistenceContext** chỉ đại diện cách ứng dụng nạp dữ liệu trước đó. Ví dụ nhằm phân biệt trạng thái object; một đoạn mã hoàn chỉnh phải định nghĩa method và quản lý vòng đời EntityManager rõ ràng.

Hãy nhớ: **đã có ID của hàng không đồng nghĩa object đang managed**. Hai object Java có cùng primary key nhưng thuộc các context khác nhau không phải cùng một instance được quản lý.

## 5. Identity map: một bản thể managed cho một danh tính

Trong một persistence context, JPA duy trì nguyên tắc **một entity instance được quản lý cho một cặp loại entity và primary key**. Đây thường được gọi là **identity map** hoặc cache cấp một:

~~~java
PurchaseOrder first = entityManager.find(PurchaseOrder.class, 100L);
PurchaseOrder again = entityManager.find(PurchaseOrder.class, 100L);

boolean sameReference = first == again; // Thường là true trong cùng context.
~~~

Điều này giúp UoW có một đối tượng đại diện nhất quán cho hàng đang theo dõi. Nếu hai phần của use case cùng sửa một entity managed, chúng đang tác động lên cùng instance.

Tuy nhiên:

- Identity map **không phải cache toàn ứng dụng**; nó có phạm vi persistence context.
- Identity map không tự cập nhật dữ liệu do một transaction khác vừa commit.
- Truy vấn JPQL vẫn có thể gửi SQL dù một số entity đã được quản lý; identity map không có nghĩa mọi truy vấn đều được phục vụ từ RAM.
- Một entity managed có thể chứa dữ liệu cũ theo snapshot/cách nạp trước đó. Khi cần, phải xem **refresh**, lock hoặc chiến lược đồng thời phù hợp, chứ không giả định một lần find luôn mới nhất.

## 6. Dirty checking hoạt động thế nào?

**Dirty checking** là cơ chế ORM phát hiện entity managed đã thay đổi so với trạng thái nó theo dõi. Trong Hibernate, quá trình này thường dựa trên snapshot trạng thái của entity, hoặc cơ chế tăng cường bytecode/chiến lược tracking khác tùy cấu hình.

~~~text
Nạp entity managed
    |
    +-- DB: status = NEW, total = 500
    +-- Context ghi nhận trạng thái ban đầu
    |
Code Java gọi order.confirm()
    |
    +-- Entity hiện tại: status = CONFIRMED, total = 500
    |
Flush
    |
    +-- Kiểm tra thuộc tính cần đồng bộ
    +-- Xếp lệnh UPDATE thích hợp
    +-- Gửi SQL tới DB
~~~

Ví dụ:

~~~java
@Transactional
public void confirmOrder(long id) {
    PurchaseOrder order = entityManager.find(PurchaseOrder.class, id);
    if (order == null) {
        throw new IllegalArgumentException("Đơn không tồn tại");
    }
    order.confirm();
    // Không có lệnh update() thủ công ở đây.
}
~~~

Khi transaction manager hoàn tất method và tiến tới commit, persistence context thường được flush; thay đổi hợp lệ được đồng bộ xuống DB. Việc **không thấy câu UPDATE ngay tại dòng order.confirm() là bình thường**.

Ba giới hạn cần nhớ:

1. Dirty checking áp dụng cho **entity managed** và thuộc tính/quan hệ mà provider có thể theo dõi; nó không tự theo dõi mọi object Java tùy ý.
2. Đổi dữ liệu trong một collection, quan hệ hoặc embeddable phải phù hợp quy tắc mapping/cascade/ownership. Đừng suy từ việc danh sách Java đã đổi rằng foreign key hay bảng liên kết chắc chắn đổi theo.
3. ORM có quyền tối ưu việc phát SQL. Một giá trị được gán lại bằng chính giá trị cũ có thể không tạo UPDATE; số và thứ tự SQL cụ thể phụ thuộc provider, mapping và flush mode.

## 7. Persist, remove, flush và commit không có cùng ý nghĩa

| Thao tác | Ý nghĩa trong JPA | Có đồng nghĩa commit? |
| --- | --- | --- |
| **persist(entity)** | Đưa entity mới vào trạng thái managed, lên lịch chèn khi cần | Không |
| **find(...)** | Nạp entity theo ID, thường trả về managed entity nếu tồn tại | Không |
| **remove(entity)** | Đánh dấu entity managed để xóa khi đồng bộ | Không |
| **flush()** | Đồng bộ các thay đổi đang chờ của context xuống DB trong transaction | **Không** |
| **clear()** | Tách toàn bộ entity khỏi context hiện tại | Không; cũng không phải rollback |
| **detach(entity)** | Tách một entity khỏi context | Không |
| **merge(detached)** | Sao chép trạng thái vào managed instance và trả instance đó | Không |
| **transaction commit** | Xác nhận transaction DB theo cơ chế quản lý đang dùng | Có: ranh giới xác nhận DB |
| **transaction rollback** | Hủy tác động SQL chưa commit của transaction | Không tự phục hồi mọi object Java trong RAM về trạng thái cũ |

### 7.1. Flush là đồng bộ câu SQL, không phải xác nhận bền vững

~~~text
BEGIN
    order.confirm()       (đổi object managed)
    entityManager.flush() (DB có thể nhận UPDATE)
    ... lỗi nghiệp vụ ...
ROLLBACK                 (UPDATE chưa commit bị hủy)
~~~

**Flush thành công không có nghĩa dữ liệu đã commit.** Các transaction khác còn tuân theo mức cô lập và có thể chưa nhìn thấy thay đổi. Sau rollback, DB hủy kết quả chưa commit, nhưng object Java đang giữ có thể vẫn chứa trạng thái vừa sửa; không tiếp tục dùng object đó như bằng chứng DB đã xác nhận.

### 7.2. Khi nào ORM tự flush?

Ở flush mode **AUTO** thông dụng, ORM có thể flush trước khi commit và trong những tình huống cần bảo đảm truy vấn thấy kết quả phù hợp của các thay đổi đang chờ. Chi tiết phụ thuộc loại truy vấn, provider và cách mapping; đừng mặc định **mỗi SELECT đều flush** hoặc **không SELECT nào flush**.

Với JPA **FlushModeType.COMMIT**, việc đồng bộ thường được trì hoãn nhiều hơn, nhưng tác động chính xác đến kết quả query trước commit được quy định có giới hạn. Hibernate còn có những flush mode riêng. Nếu bài toán cần một ranh giới SQL rõ ràng, dùng **flush()** có chủ đích rồi kiểm tra lỗi, không dựa vào suy đoán.

Một số chiến lược tạo ID, ví dụ dùng cột **IDENTITY**, có thể làm ORM cần INSERT sớm để lấy khóa, ngay trước lúc bạn nghĩ tới flush. Vì vậy, **persist không cam kết luôn trì hoãn SQL cho tới cuối method**.

## 8. Ví dụ thực tế: xác nhận đơn hàng bằng một UoW

Giả sử một tenant có đơn hàng ở trạng thái NEW và một dòng tồn kho cho sản phẩm. Xác nhận đơn cần kiểm tra quyền tenant, giảm tồn kho, đổi trạng thái đơn, và lưu một sự kiện nghiệp vụ để phát sau khi commit.

### 8.1. Các entity tối giản

Ví dụ dùng Jakarta Persistence và Java hiện đại. Các class rút gọn để minh họa UoW, chưa thể hiện đầy đủ constructor, getter và mapping cho mọi domain:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

enum OrderStatus { NEW, CONFIRMED, CANCELED }

@Entity
@Table(name = "purchase_orders")
class PurchaseOrder {
    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private long tenantId;

    @Column(name = "product_id", nullable = false)
    private long productId;

    @Column(nullable = false)
    private long quantity;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Version
    private long version;

    protected PurchaseOrder() {}

    public long tenantId() { return tenantId; }
    public long productId() { return productId; }
    public long quantity() { return quantity; }

    public void confirm() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException("Chỉ xác nhận đơn NEW");
        }
        status = OrderStatus.CONFIRMED;
    }
}
~~~

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory_stock")
class InventoryStock {
    @Id
    private Long productId; // Ví dụ: productId là định danh toàn cục.

    @Column(name = "tenant_id", nullable = false)
    private long tenantId;

    @Column(nullable = false)
    private long available;

    @Version
    private long version;

    protected InventoryStock() {}

    public long tenantId() { return tenantId; }

    public void decrease(long quantity) {
        if (quantity <= 0 || available < quantity) {
            throw new IllegalStateException("Không đủ tồn kho");
        }
        available -= quantity;
    }
}
~~~

**Lưu ý mô hình:** ví dụ dùng **productId toàn cục** để làm primary key của InventoryStock. Nếu mỗi tenant có thể có cùng productId, hãy dùng khóa ghép (**tenant_id**, **product_id**) hoặc ID riêng và unique constraint phù hợp. Thuộc tính tenantId không thể thay thế xác thực và kiểm soát quyền truy cập.

### 8.2. Application service định nghĩa ranh giới

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ConfirmOrderService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void confirm(long tenantId, long orderId) {
        PurchaseOrder order =
                entityManager.find(PurchaseOrder.class, orderId);
        if (order == null || order.tenantId() != tenantId) {
            throw new IllegalArgumentException("Không tìm thấy đơn hợp lệ");
        }

        InventoryStock stock =
                entityManager.find(InventoryStock.class, order.productId());
        if (stock == null || stock.tenantId() != tenantId) {
            throw new IllegalStateException("Không tìm thấy tồn kho");
        }

        stock.decrease(order.quantity());
        order.confirm();

        // Cả stock và order đang là managed entities.
        // Dirty checking sẽ đồng bộ thay đổi của cả hai.
        // Ghi audit/outbox qua cùng EntityManager khi nghiệp vụ yêu cầu.
    }
}
~~~

Luồng ở trên có một điểm điều phối **@Transactional** rõ ràng: cùng EntityManager/persistence context, cùng transaction, cùng đơn vị nghiệp vụ. Lập trình viên sửa object, còn JPA/Hibernate theo dõi và phát UPDATE cho **stock.available** và **order.status** lúc flush.

Những điểm cần lưu ý để đưa ví dụ thành ứng dụng thực tế:

- Cần kiểm tra **tenantId** dựa trên danh tính đã xác thực, không tin ID do client tự chọn.
- **@Version** trên cả hai entity giúp phát hiện một số cập nhật tranh chấp. Hai transaction cùng đọc tồn kho rồi cùng trừ có thể khiến một transaction bị lỗi optimistic locking; ứng dụng cần rollback và xử lý hoặc retry toàn bộ use case theo chính sách.
- Ví dụ chưa lưu idempotency key, kết quả đơn hàng và outbox; đó là những yêu cầu bổ sung nếu endpoint được tự động retry hoặc phát sự kiện.
- Nếu phải chống việc đơn được xác nhận hai lần, kiểm tra **status == NEW** kết hợp version/ràng buộc giao dịch là cần thiết. Không mặc định request lặp là thao tác mới hợp lệ.
- Dù business method không gọi commit(), transaction manager vẫn có thể thất bại lúc flush/commit **sau khi method body kết thúc**; người gọi cần xử lý exception tại ranh giới transaction.

### 8.3. Đường đi các thay đổi trong UoW

~~~text
@Transactional bắt đầu
      |
EntityManager.find(order)    -> managed order
EntityManager.find(stock)    -> managed stock
      |
stock.decrease(qty)          -> stock dirty
order.confirm()              -> order dirty
      |
flush (tự động hoặc chủ động)
      |
UPDATE inventory_stock ... WHERE id = ? AND version = ?
UPDATE purchase_orders ... WHERE id = ? AND version = ?
      |
Nếu không xung đột/lỗi -> COMMIT
Nếu lỗi/rollback-only  -> ROLLBACK
~~~

SQL là sơ đồ ý tưởng, không cam kết thứ tự hai UPDATE, danh sách cột hay cú pháp đúng của từng dialect Hibernate. Nếu cần đảm bảo **thứ tự khóa** để giảm deadlock, hãy thiết kế cụ thể ở tầng truy cập dữ liệu thay vì mặc định ORM phát SQL theo thứ tự gọi setter.

## 9. Change tracking và optimistic locking giải quyết hai vấn đề khác nhau

**Dirty checking** trả lời: “entity managed nào đã thay đổi để cần đồng bộ?”. **Optimistic locking** trả lời: “trạng thái mà transaction dựa vào đã bị transaction khác thay đổi theo cơ chế version chưa?”.

Với **@Version**, Hibernate/JPA thường phát UPDATE tương đương:

~~~sql
UPDATE inventory_stock
SET available = :newAvailable,
    version = :newVersion
WHERE product_id = :productId
  AND version = :oldVersion;
~~~

Nếu câu UPDATE có **0 hàng** vì version đã thay đổi, provider phát hiện xung đột optimistic locking và transaction cần rollback. Lỗi có thể xuất hiện lúc **flush hoặc commit**, không nhất thiết ngay khi gọi **stock.decrease()**.

Ví dụ hai transaction:

~~~text
Ban đầu: stock.available = 1, version = 3

T1 đọc available=1, version=3
T2 đọc available=1, version=3

T1 giảm xuống 0, UPDATE ... WHERE version=3 --> thành công
T1 COMMIT, version thành 4

T2 giảm xuống 0 trong object của mình
T2 UPDATE ... WHERE version=3 --> 0 hàng, optimistic conflict
T2 ROLLBACK
~~~

Nếu không có kiểm soát phiên bản hoặc cách khóa tương đương, hai lần read–modify–write trên cùng hàng có thể ghi đè kết quả của nhau ở một số mức cô lập/đường truy cập. Với thao tác giảm tồn kho đơn giản, lựa chọn khác là câu **UPDATE có điều kiện** ở DB:

~~~sql
UPDATE inventory_stock
SET available = available - :quantity
WHERE product_id = :productId
  AND tenant_id = :tenantId
  AND available >= :quantity;
~~~

Kiểm tra **số hàng cập nhật** rồi thực hiện phần còn lại trong cùng transaction. Lựa chọn giữa ORM dirty checking + version và SQL atomic update tùy nhu cầu: mô hình domain, mức tranh chấp, số hàng, việc cần kiểm tra điều kiện và cách ứng dụng quản lý version. **Nếu pha trộn bulk SQL với entity managed, phải xử lý đồng bộ trạng thái context** như phần sau.

## 10. Detached entity và rủi ro của merge

Một object entity được đưa từ repository qua nhiều lớp, lưu trong session web hoặc serialize thành JSON có thể trở thành **detached** sau khi persistence context kết thúc. Thay đổi detached object không được UoW hiện tại tự theo dõi.

JPA có **merge**:

~~~java
PurchaseOrder managedCopy = entityManager.merge(detachedOrder);
// Giá trị từ detachedOrder được sao chép vào managedCopy theo quy tắc JPA.
// detachedOrder vẫn detached; merge không biến nó thành cùng instance managed.
~~~

Lạm dụng merge có rủi ro:

- Một object detached chứa **dữ liệu cũ** có thể ghi đè giá trị mới hơn nếu không có version/ràng buộc đồng thời phù hợp.
- Payload HTTP thường chỉ mang một số trường. Chuyển thẳng nó thành entity rồi merge có thể khiến giá trị **null/mặc định** vô tình đè lên dữ liệu đang có.
- Merge có thể kéo theo cascade đến các quan hệ được mapping, dẫn tới SQL ngoài dự định.

Cách tiếp cận rõ ràng hơn cho use case sửa hồ sơ:

~~~java
@Transactional
public void rename(long id, String newName) {
    Customer customer = entityManager.find(Customer.class, id);
    if (customer == null) {
        throw new IllegalArgumentException("Không tìm thấy khách hàng");
    }
    customer.rename(newName); // Chỉ đổi trường được nghiệp vụ cho phép.
}
~~~

**Customer** ở đây là một entity giả định của ứng dụng. Tư tưởng là **nạp managed entity rồi gọi hành vi domain có kiểm tra**, không trộn DTO thiếu trường với toàn bộ trạng thái persistence.

## 11. Bulk update/native SQL có thể đi ngoài change tracker

Khi chạy JPQL bulk UPDATE/DELETE hoặc native SQL trực tiếp, các thay đổi có thể xảy ra trong DB **mà không cập nhật ngay các entity đã managed trong persistence context**:

~~~java
PurchaseOrder order = entityManager.find(PurchaseOrder.class, orderId);

entityManager.createQuery(
    "UPDATE PurchaseOrder o SET o.status = :status WHERE o.id = :id"
)
.setParameter("status", OrderStatus.CANCELED)
.setParameter("id", orderId)
.executeUpdate();

// order trong context có thể vẫn giữ status cũ.
~~~

Đó là điểm khác biệt quan trọng:

| Đường ghi | Theo dõi dirty checking? | Lưu ý |
| --- | --- | --- |
| Đổi thuộc tính entity managed | Có theo cơ chế ORM | SQL có thể chờ đến flush |
| **entityManager.persist/remove** | Quản lý entity mới/xóa | Cascade và thứ tự flush cần kiểm tra |
| JPQL bulk UPDATE/DELETE | Bỏ qua cơ chế cập nhật từng entity managed thông thường | Context có thể stale; xử lý flush/clear/refresh |
| Native SQL/JdbcTemplate cùng DB | DB được cập nhật trực tiếp | Context JPA có thể không biết thay đổi |
| Ghi từ ứng dụng hoặc service khác | Ngoài context hiện tại | Dùng version, reload, cache invalidation hoặc isolation phù hợp |

Trước bulk SQL, cần quyết định có phải **flush** những thay đổi đang chờ không; sau bulk SQL, có thể cần **clear() hoặc refresh()** để tránh dùng dữ liệu stale. Nhưng **clear() tách mọi entity khỏi context**, có nguy cơ làm mất những thay đổi managed **chưa flush**. Không gọi clear một cách vô điều kiện mà không hiểu hệ quả.

Một số đường bulk update còn không tự tăng trường **@Version** theo cách cập nhật managed entity thường làm. Nếu phải duy trì optimistic locking với các đường ghi khác, cần thiết kế cập nhật version, truy vấn và cơ chế đồng bộ một cách nhất quán.

## 12. Transaction boundary nên nằm ở đâu trong kiến trúc Java?

Một mô hình dễ bảo trì:

~~~text
HTTP Controller
      |
      v
Application Service / Use Case  <-- quyết định transaction boundary
      |
      +-- Repository A
      +-- Repository B
      +-- EntityManager / JdbcTemplate
      |
      v
Database transaction
~~~

**Controller** nhận và xác thực request ở mức giao thức; **application service** kiểm tra điều kiện và điều phối công việc; **repository** tập trung truy cập dữ liệu. Với use case nhiều thay đổi bắt buộc commit cùng nhau, transaction thường đặt ở **service**.

Không nên để từng repository method tự mở và commit giao dịch riêng nếu các kết quả phải nguyên tử với nhau:

~~~text
Sai về ranh giới:
  orderRepository.save(order)   --> COMMIT #1
  stockRepository.save(stock)   --> COMMIT #2
  auditRepository.save(audit)   --> lỗi

Đúng về ý tưởng:
  BEGIN UoW/transaction
    cập nhật order, stock, audit
  COMMIT nếu mọi bước đạt, ngược lại ROLLBACK
~~~

Đặt UoW quá rộng cũng có hại. Không giữ transaction mở trong lúc chờ người dùng nhập thông tin, thực thi CPU lâu hoặc gọi API ngoài chậm. Giữ transaction **ngắn, có chủ đích, đủ rộng để giữ đúng bất biến nghiệp vụ**.

## 13. Spring @Transactional và propagation

Spring thường dùng transaction interceptor để xác lập phạm vi giao dịch. Một số quy tắc quan trọng:

- Propagation mặc định **REQUIRED**: tham gia transaction hiện có, hoặc bắt đầu transaction mới nếu chưa có.
- **REQUIRES_NEW** tạo transaction độc lập. Nếu audit dùng REQUIRES_NEW và commit trước khi transaction đặt hàng rollback, audit có thể tồn tại dù đơn không thành công. Đó có thể là hành vi mong muốn cho nhật ký kỹ thuật, nhưng không bảo đảm atomicity với đơn.
- **NESTED** có thể dựa trên savepoint khi transaction manager/driver hỗ trợ; nó không giống một transaction độc lập.
- Trong chế độ proxy phổ biến, một method gọi **this.someTransactionalMethod()** trong cùng bean thường bỏ qua transaction interceptor của lời gọi nội bộ.
- Theo mặc định phổ biến, Spring rollback với **RuntimeException**/**Error**; checked exception có thể cần **rollbackFor** hoặc cấu hình rollback rule khác.
- **@Transactional(readOnly = true)** là một gợi ý/hành vi tối ưu tùy provider và transaction manager; không phải cơ chế ủy quyền hoặc lời cam kết mọi lệnh ghi đều bất khả thi.

Ví dụ:

~~~java
@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderApplicationService(
            OrderRepository orders, InventoryRepository inventory
    ) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void confirm(long orderId) {
        var order = orders.findRequired(orderId);
        inventory.reserve(order.productId(), order.quantity());
        order.confirm();
    }
}
~~~

Ví dụ giả định **orders.findRequired** trả managed entity và **inventory.reserve** tham gia cùng transaction; cũng cần kiểm tra tenant, phiên bản và điều kiện nghiệp vụ ở triển khai thực tế. Khi dùng repository Spring Data JPA, method **save** có thể cần cho entity mới hoặc detached, nhưng **không phải cứ sửa managed entity là bắt buộc gọi save**.

### Khi dùng nhiều database hoặc tài nguyên

Một transaction manager cho database A không tự tạo giao dịch nguyên tử trên database B, broker, object storage hoặc HTTP API. Nếu thao tác cần cùng lúc ghi DB và phát sự kiện, có thể dùng **transactional outbox** để ghi ý định phát trong cùng transaction DB, sau đó phát bất đồng bộ. Consumer cần idempotency vì sự kiện có thể lặp.

Với nhiều DataSource, cần xác nhận repository thực sự tham gia đúng manager. “Cùng có @Transactional” không có nghĩa mọi connection tới các database độc lập cùng được commit atomically.

## 14. Ví dụ JDBC: unit of work nhưng không có dirty checking tự động

JDBC không tự biết một entity Java vừa đổi thuộc tính. Ứng dụng phải phát câu SQL và dùng **một Connection** để phối hợp nhiều bước trong một transaction:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class JdbcOrderUnitOfWork {
    private final DataSource dataSource;

    public JdbcOrderUnitOfWork(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void reserve(long tenantId, long productId,
                        long orderId, long quantity) throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                String updateStock = """
                    UPDATE inventory_stock
                    SET available = available - ?
                    WHERE tenant_id = ? AND product_id = ?
                      AND available >= ?
                    """;
                try (PreparedStatement st =
                             connection.prepareStatement(updateStock)) {
                    st.setLong(1, quantity);
                    st.setLong(2, tenantId);
                    st.setLong(3, productId);
                    st.setLong(4, quantity);
                    if (st.executeUpdate() != 1) {
                        throw new IllegalStateException("Không đủ tồn kho");
                    }
                }

                String updateOrder = """
                    UPDATE purchase_orders
                    SET status = 'CONFIRMED'
                    WHERE id = ? AND tenant_id = ? AND status = 'NEW'
                    """;
                try (PreparedStatement st =
                             connection.prepareStatement(updateOrder)) {
                    st.setLong(1, orderId);
                    st.setLong(2, tenantId);
                    if (st.executeUpdate() != 1) {
                        throw new IllegalStateException(
                                "Đơn không tồn tại hoặc đã xử lý");
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

Ưu điểm của cách viết này là **rõ câu SQL, điều kiện và số hàng tác động**. Ví dụ chỉ tập trung vào transaction của hai UPDATE; hệ thống thật còn cần bảo đảm **đơn hàng đúng sản phẩm/số lượng cần trừ**, tránh ghi nhận sai khi caller gửi ID không phù hợp, có idempotency key và trạng thái nghiệp vụ đáng tin cậy. Khi một quy tắc trải qua nhiều hàng, cần kiểm soát đồng thời hoặc ràng buộc bổ sung phù hợp.

Trong đoạn code, **rollback** được gọi khi SQL hoặc kiểm tra nghiệp vụ thất bại. Nếu kết nối mất đúng lúc **commit()**, client có thể không biết commit thành công hay chưa; không tự động chạy lại thao tác không lũy đẳng nếu thiếu cơ chế request ID và đối soát.

Với JDBC, mỗi repository có thể nhận cùng Connection thông qua một tham số hoặc một unit-of-work/context do service quản lý. Không tạo connection mới cho từng bước rồi mặc định các bước nằm trong cùng giao dịch.

## 15. Theo dõi thay đổi và kiểm soát đồng thời

Change tracking không tự ngăn **lost update**, **write skew** hoặc những xung đột nghiệp vụ khác. Nếu hai transaction cùng đọc trạng thái ban đầu, việc mỗi transaction có persistence context riêng không buộc chúng đồng ý về kết quả cuối.

### 15.1. Cập nhật cùng một hàng

**@Version**/optimistic locking thường phù hợp cho hành vi “đọc entity, chỉnh thuộc tính, lưu lại”. Nếu version không khớp, transaction bị từ chối; phải quyết định trả lỗi xung đột hay retry toàn use case theo điều kiện nghiệp vụ.

### 15.2. Quy tắc xuyên nhiều hàng

Ví dụ hai bác sĩ trong cùng ca đều đọc “còn 2 người trực” rồi mỗi người đánh dấu mình nghỉ. Hai UoW riêng, mỗi UoW theo dõi một entity khác nhau, **có thể đều commit** dưới một số mức cô lập dù sau cùng không còn ai trực. Đó là **write skew**, không thể giải quyết chỉ bằng dirty checking.

Cách bảo vệ gồm **transaction SERIALIZABLE** và retry, **khóa tài nguyên chung**, hoặc mô hình dữ liệu/ràng buộc có thể thực thi chính bất biến. Phải kiểm tra cách thực thi của DBMS đang dùng.

### 15.3. Truy vấn và version

Khi có nhiều luồng ghi, lỗi optimistic locking có thể xuất hiện **muộn khi flush/commit**. Không chỉ bắt exception ở method setter. Sau khi transaction bị đánh dấu rollback-only, phải kết thúc và tạo transaction mới nếu nghiệp vụ cho phép thử lại.

## 16. Quan hệ giữa UoW với kiểm thử và khả năng quan sát

Một kiểm thử đúng không chỉ kiểm tra entity Java có giá trị mới trước commit. Cần quan sát trạng thái DB **sau khi transaction thực sự hoàn tất**.

Những kịch bản hữu ích:

1. **Thành công:** xác nhận đơn và giảm tồn kho cùng commit; trạng thái DB và các ràng buộc hợp lệ.
2. **Lỗi giữa chừng:** gây lỗi ở bước thứ hai và xác minh transaction rollback cả bước thứ nhất.
3. **Đồng thời:** hai transaction riêng cùng cố giữ đơn vị hàng cuối; chỉ số yêu cầu thành công phù hợp với tồn kho cuối.
4. **Version conflict:** hai transaction đọc cùng version rồi cùng cập nhật; xác minh exception và rollback theo provider.
5. **Bulk SQL:** thay đổi DB qua bulk update rồi kiểm tra context có dữ liệu stale; dùng refresh/clear có chủ đích.
6. **Detached input:** gửi DTO thiếu trường và bảo đảm chỉ cập nhật trường được cho phép, không mất dữ liệu khác.
7. **Commit không chắc chắn:** mô phỏng phản hồi commit bị mất và xác minh idempotency key ngăn tác động lặp.

Về vận hành, có thể theo dõi:

- **Transaction duration** và tỷ lệ commit/rollback.
- Số **INSERT/UPDATE/DELETE** phát ra cho mỗi use case, nhận biết write amplification.
- Số entity loaded, số truy vấn và tình trạng **N+1** khi ORM nạp quan hệ.
- Tỷ lệ **optimistic lock failure**, deadlock, lock wait, timeout.
- Số connection active/pending trong pool và thời gian giữ connection.
- Thời gian flush/commit và độ trễ query ở DB.

Nếu thấy service chỉ sửa một entity nhưng phát rất nhiều UPDATE/SELECT, cần xem mapping, cascade, flush mode, lazy loading và logic domain thay vì vội tăng connection pool.

## 17. Các lỗi phổ biến khi đặt ranh giới UoW

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Mỗi repository tự commit | Các bước trong một nghiệp vụ có thể thành công một phần | Đặt transaction ở application service |
| Coi mọi object có ID là managed | Sửa detached object nhưng DB không đổi | Hiểu entity lifecycle, nạp managed entity hoặc merge có chủ đích |
| Coi **flush = commit** | Tưởng dữ liệu đã bền vững dù transaction còn có thể rollback | Phân biệt đồng bộ SQL và xác nhận giao dịch |
| Chỉ dựa vào dirty checking để xử lý tranh chấp | Có thể gặp lost update hoặc write skew | Version, conditional UPDATE, khóa hoặc isolation phù hợp |
| Merge DTO trực tiếp vào entity | Ghi đè trường không được gửi hoặc dữ liệu cũ | Map các command hợp lệ lên entity managed |
| Bulk SQL nhưng tiếp tục dùng entity stale | Quyết định nghiệp vụ dựa trên dữ liệu không nhất quán trong context | Flush/refresh/clear đúng thời điểm |
| Gọi **clear()** trước khi flush | Làm mất các thay đổi managed chưa đồng bộ | Flush có chủ đích hoặc tổ chức lại UoW |
| Giữ transaction trong cả vòng xử lý HTTP | Chiếm connection/khóa lâu, ảnh hưởng tải và MVCC | Transaction ngắn theo use case |
| Gọi API ngoài trước khi commit và nghĩ rollback sẽ hoàn tác nó | Email, message hoặc thanh toán ngoài DB vẫn xảy ra | Outbox, idempotency hoặc cơ chế phối hợp |
| **@Transactional** bị bỏ qua do self-invocation | Không có transaction như kỳ vọng | Gọi qua proxy/ranh giới được framework quản lý |
| Dùng **REQUIRES_NEW** cho bước phải commit cùng use case | Có thể lưu một phần dù transaction cha rollback | Chỉ tách transaction khi đó là chủ đích nghiệp vụ |
| Cho rằng nhiều DataSource cùng @Transactional là nguyên tử | Các nguồn dữ liệu có thể commit độc lập | Thiết kế giao dịch phân tán hoặc eventual consistency thích hợp |

## 18. Bài tập tự kiểm tra

### Bài 1. Managed và detached

Trong một method **@Transactional**, bạn gọi **entityManager.find()** rồi sửa **order.status**. Có cần gọi **entityManager.persist(order)** để lưu thay đổi không? Nếu sửa object sau khi context đóng thì sao?

**Gợi ý:** Entity đang managed thường được dirty checking theo dõi và đồng bộ ở flush, không cần persist lại. Sau khi detached, sửa thuộc tính không tự lưu; cần nạp lại managed entity rồi cập nhật, hoặc merge một cách có kiểm soát.

### Bài 2. Flush rồi lỗi

Trong transaction, application service thay đổi order, gọi **flush()** thành công, sau đó kiểm tra nghiệp vụ thất bại và rollback. DB có giữ order.status mới không?

**Gợi ý:** Không. Flush có thể đã gửi UPDATE nhưng chưa commit; rollback hủy tác động thuộc transaction. Object Java đang giữ có thể vẫn mang trạng thái vừa sửa, nên không dùng nó làm bằng chứng DB đã lưu.

### Bài 3. Hai repository, hai connection

Service gọi **orderRepository.update()** và **stockRepository.update()**. Mỗi repository tự mở Connection, bật auto-commit, chạy một UPDATE rồi đóng. Nếu bước stock lỗi, vì sao không có UoW nguyên tử?

**Gợi ý:** Hai UPDATE là hai giao dịch riêng; order có thể đã commit. Cần một transaction/connection hoặc transaction manager điều phối đúng các bước.

### Bài 4. Lost update

Hai transaction cùng nạp stock.available = 1 rồi cùng giảm còn 0 bằng dirty checking. Có chắc chỉ một transaction được chấp nhận không?

**Gợi ý:** Không thể chắc nếu thiếu cơ chế đồng thời. @Version có thể phát hiện xung đột; UPDATE có điều kiện **available >= 1** cũng là lựa chọn phù hợp khi chỉ giảm một hàng. Phải xử lý xung đột và kết quả commit theo đúng isolation/DBMS.

### Bài 5. Bulk update

Bạn đã nạp một entity managed có status NEW, rồi chạy JPQL bulk UPDATE để đổi status sang CANCELED. Ngay sau đó, code tiếp tục kiểm tra entity đang có trong context. Có thể thấy giá trị nào?

**Gợi ý:** Entity managed có thể vẫn là NEW vì bulk operation bỏ qua việc đồng bộ từng entity trong context. Cần chọn chiến lược refresh/clear và flush hợp lý.

### Bài 6. REQUIRES_NEW

Một use case xác nhận đơn có bước ghi audit dùng **REQUIRES_NEW** và commit thành công. Sau đó transaction chính rollback. Audit còn không?

**Gợi ý:** Có thể vẫn còn vì audit nằm trong transaction độc lập. Chỉ dùng khi mong muốn giữ nhật ký cả yêu cầu thất bại; nếu audit phải gắn nguyên tử với đơn thì không tách kiểu này.

### Bài 7. Phản hồi commit bị mất

Transaction gồm trừ kho và tạo order đã commit trên DB, nhưng mạng đứt trước khi API nhận được kết quả. Client retry với cùng payload. Chỉ có UoW và transaction có đủ chống tạo trùng không?

**Gợi ý:** Chưa đủ. Mỗi lần retry có thể mở một transaction hợp lệ mới. Cần request ID ổn định, ràng buộc duy nhất, lưu kết quả và đối chiếu khi lặp.

### Bài 8. Đặt phạm vi

Một service mở transaction, sửa một entity rồi gọi API vận chuyển ngoài DB mất 20 giây, sau đó mới commit. Những rủi ro chính là gì?

**Gợi ý:** Connection và khóa có thể bị giữ lâu; các phiên bản MVCC có thể tồn tại lâu hơn, timeout tăng; API ngoài đã có tác động dù DB có thể rollback. Nên thu ngắn UoW và dùng outbox/cơ chế phối hợp thích hợp.

## 19. Ghi nhớ khi thiết kế persistence

**Unit of work** giúp ứng dụng xác định những thay đổi thuộc cùng một ý định nghiệp vụ. **Persistence context và dirty checking** giúp JPA/Hibernate ghi nhận thay đổi của các entity managed mà không cần phát UPDATE trực tiếp ở từng setter. **Flush** đưa thay đổi xuống DB theo quy tắc ORM, còn **commit** mới xác nhận transaction; rollback vẫn có thể hủy SQL đã flush.

Đặt ranh giới transaction ở application service đủ bao trùm các bước bắt buộc, giữ transaction ngắn, quản lý vòng đời entity và hiểu những đường ghi vượt khỏi change tracker. Khi có đồng thời, kết hợp **version, atomic UPDATE, ràng buộc hoặc isolation** phù hợp; khi có retry hoặc tác dụng ngoài DB, bổ sung **idempotency và outbox**. Những quyết định đó giúp tầng persistence Java vừa phản ánh đúng nghiệp vụ, vừa có cơ sở kiểm soát lỗi, tài nguyên và hiệu năng khi hệ thống vận hành thật.
