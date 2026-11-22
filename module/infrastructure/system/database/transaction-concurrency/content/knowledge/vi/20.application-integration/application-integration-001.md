# Đặt ranh giới giao dịch theo một đơn vị công việc nghiệp vụ

Ranh giới giao dịch (transaction boundary) xác định thời điểm một đơn vị thay đổi dữ liệu bắt đầu, những thao tác nào thuộc cùng giao dịch, và thời điểm toàn bộ thay đổi được commit hoặc rollback. Trong ứng dụng, ranh giới này nên phản ánh **một đơn vị công việc nghiệp vụ cần được lưu thành công cùng nhau**.

Ví dụ, khi đặt một đơn hàng, hệ thống có thể phải tạo đơn hàng, tạo các dòng hàng, giữ số lượng tồn kho và ghi một yêu cầu thanh toán vào outbox. Nếu một bước bắt buộc thất bại, dữ liệu database không được để lại trạng thái nửa chừng. Các thao tác database này thường thuộc cùng một transaction.

Đặt ranh giới quá nhỏ có thể khiến một phần nghiệp vụ commit trong khi phần khác thất bại. Đặt ranh giới quá rộng lại khiến transaction giữ khóa lâu, tăng tranh chấp và làm connection bị chiếm dụng. Vì vậy, cần xác định đúng đơn vị công việc, các bất biến phải giữ và những thao tác nào thực sự cần tính nguyên tử.

## 1. Transaction boundary là gì?

Một transaction boundary là khoảng thời gian mà DBMS xem các thao tác database bên trong như một đơn vị nguyên tử. Khi commit, các thay đổi được xác nhận theo cơ chế của DBMS. Khi rollback, các thay đổi thuộc transaction chưa commit được hoàn tác.

Một transaction thường có dạng:

~~~sql
BEGIN;

-- Đọc dữ liệu cần thiết.
-- Kiểm tra điều kiện nghiệp vụ.
-- INSERT / UPDATE / DELETE các bảng liên quan.

COMMIT;
~~~

Nếu một bước thất bại:

~~~sql
ROLLBACK;
~~~

Ranh giới không chỉ là vị trí đặt hai câu lệnh BEGIN và COMMIT. Nó là quyết định kiến trúc về những thay đổi nào phải cùng thành công hoặc cùng thất bại.

### Đơn vị công việc nghiệp vụ (business unit of work)

Một đơn vị công việc nghiệp vụ là một hành động có ý nghĩa đối với người dùng hoặc hệ thống, chẳng hạn:

- Đặt một đơn hàng.
- Chuyển tiền giữa hai tài khoản.
- Xác nhận một lượt đặt chỗ.
- Phát hành một chứng từ.
- Chuyển trạng thái một yêu cầu và ghi lịch sử tương ứng.
- Cập nhật hạn mức cùng với bản ghi sử dụng hạn mức.

Một đơn vị công việc có thể gồm nhiều câu SQL, nhiều repository và nhiều đối tượng domain. Nếu tất cả thay đổi database phải cùng commit để giữ bất biến, chúng cần nằm trong cùng transaction.

Ngược lại, một request HTTP không nhất thiết luôn tương đương một transaction. Một request có thể chỉ đọc dữ liệu; một job nền có thể thực hiện cùng một đơn vị công việc mà không có HTTP request; một API điều phối dài có thể gồm nhiều giai đoạn với các transaction ngắn riêng biệt.

## 2. Vì sao ranh giới nên đặt theo use case?

Trong kiến trúc ứng dụng, service/application layer thường điều phối một use case. Đây là nơi hiểu đầy đủ hành động nghiệp vụ và biết những thay đổi nào cần cùng commit.

Ví dụ đặt hàng có thể cần:

1. Xác thực yêu cầu và kiểm tra dữ liệu đầu vào.
2. Tạo bản ghi order.
3. Tạo các order line.
4. Giữ tồn kho.
5. Ghi sự kiện yêu cầu thanh toán vào outbox.
6. Commit.

Nếu mỗi repository tự mở và commit transaction riêng, hệ thống có thể gặp tình huống:

- Order đã commit.
- Một số order line đã commit.
- Giữ tồn kho thất bại.
- Người dùng nhận lỗi nhưng database còn đơn hàng chưa hoàn chỉnh.

Đặt transaction ở ranh giới use case cho phép các thao tác database bắt buộc cùng thành công hoặc cùng rollback.

### Sơ đồ một đơn vị công việc

~~~text
HTTP request / message / scheduled job
                 |
                 v
       Application service
       begin transaction
                 |
       +---------+----------+
       |         |          |
       v         v          v
    Order     Inventory   Outbox
  repository  repository repository
       |         |          |
       +---------+----------+
                 |
          commit / rollback
                 |
                 v
          Kết quả use case
~~~

Các repository thực hiện thao tác dữ liệu trong cùng transaction đang hoạt động. Chúng không cần tự quyết định thời điểm commit toàn bộ nghiệp vụ.

## 3. Xác định những thay đổi nào phải commit cùng nhau

Bắt đầu bằng việc viết bất biến của use case. Ví dụ với đặt hàng:

- Một order đã được tạo phải có đầy đủ order line.
- Không được giữ tồn kho vượt số lượng hiện có.
- Mỗi lần giữ tồn kho phải gắn với đúng order.
- Yêu cầu thanh toán phải được ghi nhận bền vững nếu order chuyển sang trạng thái chờ thanh toán.
- Không được phát ra event xác nhận order khi transaction tạo order đã rollback.

Sau đó phân loại các thao tác:

| Thao tác | Có thuộc transaction tạo order? | Lý do |
|---|---|---|
| INSERT order | Có | Tạo trạng thái nghiệp vụ chính |
| INSERT order lines | Có | Order không hợp lệ nếu thiếu các dòng hàng bắt buộc |
| Giảm available inventory | Có | Phải cùng commit với việc giữ hàng |
| INSERT outbox event | Có | Đảm bảo yêu cầu gửi đi tồn tại nếu order commit |
| Gọi cổng thanh toán qua HTTP | Không nên giữ trong transaction DB | Network có thể chậm, timeout hoặc có kết quả không xác định |
| Gửi email xác nhận trực tiếp | Không | Email không rollback cùng database |
| Ghi log debug | Thường không | Không phải thay đổi nghiệp vụ cần nguyên tử |
| Cập nhật dashboard thống kê | Tùy yêu cầu | Có thể là tác vụ bất đồng bộ sau commit |

Ranh giới phải bao phủ các thay đổi database cần nguyên tử. Những thao tác bên ngoài database cần một giao thức phối hợp riêng, chẳng hạn transactional outbox hoặc saga.

## 4. Ví dụ: đặt hàng trong một transaction

Giả sử ứng dụng có các bảng orders, order_lines, inventory và outbox_events. Một thao tác đặt hàng phải tạo đơn, giữ tồn kho và ghi sự kiện yêu cầu thanh toán.

Ví dụ dưới đây minh họa với PostgreSQL và Spring:

~~~java
@Service
public class PlaceOrderService {

    private final OrderRepository orders;
    private final InventoryRepository inventory;
    private final OutboxRepository outbox;

    public PlaceOrderService(
            OrderRepository orders,
            InventoryRepository inventory,
            OutboxRepository outbox) {
        this.orders = orders;
        this.inventory = inventory;
        this.outbox = outbox;
    }

    @Transactional
    public OrderId placeOrder(PlaceOrderCommand command) {
        Order order = orders.createPending(
            command.customerId(),
            command.items()
        );

        for (OrderItem item : command.items()) {
            int changed = inventory.reserve(
                item.productId(),
                item.quantity()
            );

            if (changed != 1) {
                throw new OutOfStockException(item.productId());
            }
        }

        outbox.add(PaymentRequested.from(order));

        return order.id();
    }
}
~~~

Trong ví dụ, các repository dùng cùng transaction manager và cùng database transaction. Khi phương thức hoàn tất bình thường, Spring commit. Nếu OutOfStockException là unchecked exception, mặc định Spring rollback transaction. Có thể cấu hình rollbackFor nếu dùng checked exception hoặc quy tắc rollback khác.

Nếu một sản phẩm không đủ tồn kho, exception làm transaction rollback: order, order lines, các lần giữ tồn kho trước đó và outbox event đều không được commit.

### Cập nhật tồn kho phải có điều kiện

Repository có thể dùng câu SQL nguyên tử:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE product_id = :product_id
  AND available_quantity >= :quantity;
~~~

Số hàng bị ảnh hưởng bằng 1 nghĩa là đã giữ được số lượng yêu cầu. Bằng 0 nghĩa là sản phẩm không tồn tại hoặc không còn đủ hàng. Cần phân biệt hai trường hợp nếu nghiệp vụ cần thông báo riêng.

Điều kiện nằm trong câu UPDATE để DBMS đánh giá tại thời điểm ghi. Nếu chỉ SELECT số lượng rồi kiểm tra ở application trước khi UPDATE, một transaction khác có thể thay đổi tồn kho giữa hai bước.

Có thể bổ sung CHECK constraint:

~~~sql
ALTER TABLE inventory
ADD CONSTRAINT inventory_available_nonnegative
CHECK (available_quantity >= 0);
~~~

Câu UPDATE thể hiện quy tắc giữ hàng; CHECK constraint bảo vệ dữ liệu trước các đường ghi khác có thể đưa số lượng xuống âm.

## 5. Không đặt commit bên trong từng repository method

Một repository thường chịu trách nhiệm truy vấn và lưu dữ liệu của một aggregate hoặc nhóm bảng. Nó không nhất thiết sở hữu ranh giới transaction của use case gọi nó.

Ví dụ thiết kế dễ gây lỗi:

~~~java
public Order createOrder(...) {
    // INSERT order
    // COMMIT ngay tại đây
}

public void reserveInventory(...) {
    // UPDATE inventory
    // COMMIT ngay tại đây
}
~~~

Nếu reserveInventory thất bại, order đã commit và không thể rollback cùng nó.

Thiết kế phù hợp hơn:

~~~java
@Service
public class PlaceOrderService {

    @Transactional
    public OrderId placeOrder(PlaceOrderCommand command) {
        Order order = orders.create(command);
        inventory.reserveAll(command.items());
        outbox.recordPaymentRequested(order);
        return order.id();
    }
}
~~~

Các repository thực hiện thao tác trên transaction hiện tại. Application service quyết định khi nào use case hoàn tất và transaction được commit.

### Repository có thể có transaction riêng không?

Có thể, nhưng phải là quyết định có chủ đích. Một method được gọi trong transaction hiện tại thường nên tham gia transaction đó thay vì tự commit độc lập.

Trong Spring, propagation mặc định là REQUIRED: nếu đã có transaction thì tham gia transaction hiện tại; nếu chưa có thì tạo transaction mới. Điều này thường phù hợp với repository hoặc service con được gọi từ một use case.

## 6. Transaction quá nhỏ: partial commit

Transaction quá nhỏ khi các bước phải cùng thành công lại được commit riêng.

Ví dụ chuyển tiền:

~~~text
Transaction A:
  trừ 100 từ tài khoản nguồn
  COMMIT

Transaction B:
  cộng 100 vào tài khoản đích
  lỗi trước COMMIT
~~~

Kết quả là tiền đã bị trừ khỏi tài khoản nguồn nhưng chưa được cộng vào tài khoản đích. Bất biến bảo toàn tổng số dư bị phá vỡ.

Hai cập nhật phải nằm trong cùng transaction:

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1
  AND balance >= 100;

-- Kiểm tra một hàng được cập nhật.

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
~~~

Trong ứng dụng, nếu một bước không thành công, phải rollback toàn bộ transaction. Cần khóa hai tài khoản theo thứ tự nhất quán hoặc dùng cơ chế phù hợp để giảm deadlock khi có nhiều chuyển khoản đồng thời.

### Dấu hiệu transaction quá nhỏ

- Một use case gọi nhiều repository nhưng mỗi repository tự commit.
- Trạng thái trung gian có thể được transaction khác đọc như dữ liệu đã hoàn tất.
- Một thao tác thất bại để lại dữ liệu chỉ được tạo một phần.
- Ứng dụng phải viết nhiều câu lệnh bù chỉ để sửa partial commit trong cùng database.
- Việc kiểm tra bất biến phải dựa vào giả định các bước luôn thành công.

Nếu các bước thuộc một đơn vị nguyên tử, hãy đưa chúng vào cùng transaction.

## 7. Transaction quá rộng: giữ khóa và connection quá lâu

Transaction quá rộng khi nó bao gồm thời gian chờ hoặc công việc không cần nằm trong một đơn vị commit database.

Ví dụ không nên làm:

~~~java
@Transactional
public void processOrder(long orderId) {
    Order order = orders.findById(orderId);
    inventory.reserve(order);

    paymentGateway.charge(order); // Gọi mạng trong transaction.
    emailService.sendConfirmation(order); // Gửi email trong transaction.

    orders.markConfirmed(orderId);
}
~~~

Lời gọi HTTP hoặc email có thể mất vài giây, timeout hoặc treo. Trong thời gian đó:

- Transaction vẫn giữ connection database.
- Khóa hàng có thể tiếp tục được giữ.
- Transaction khác phải chờ.
- Connection pool có thể cạn.
- Nếu external call thành công nhưng database commit thất bại, hệ thống có thể ở trạng thái không đồng nhất.
- Nếu transaction retry, external call có thể bị thực hiện lần nữa.

### Ranh giới ngắn hơn

Một thiết kế tốt hơn:

~~~text
Transaction 1:
  tạo order PENDING
  giữ inventory
  ghi PaymentRequested vào outbox
  COMMIT

Worker:
  đọc outbox
  gọi payment provider bằng idempotency key

Transaction 2:
  cập nhật trạng thái payment/order
  ghi event tiếp theo vào outbox
  COMMIT
~~~

Database transaction đầu tiên kết thúc nhanh sau khi lưu trạng thái và yêu cầu công việc. Worker xử lý mạng bên ngoài sau commit. Kết quả thanh toán được ghi nhận bằng một transaction mới.

Không phải mọi thao tác cần nhiều transaction đều là một transaction nguyên tử duy nhất. Với quy trình kéo dài qua nhiều hệ thống, cần mô hình hóa trạng thái và các bước bù rõ ràng.

## 8. Phối hợp với hệ thống bên ngoài: transactional outbox

Database transaction chỉ bảo đảm nguyên tử trong phạm vi resource manager/database được tham gia. Nó không tự rollback một request HTTP đã được server bên ngoài xử lý, một email đã gửi hoặc một message đã publish.

Một lỗi thường gặp:

1. Ghi order vào database.
2. Commit.
3. Gửi message sang broker.
4. Broker lỗi.
5. Order đã tồn tại nhưng không có message để hệ thống khác xử lý.

Nếu gửi message trước commit, tình huống ngược lại có thể xảy ra: broker nhận event nhưng transaction database rollback.

Transactional outbox giải quyết khoảng trống giữa hai thao tác bằng cách ghi event trong cùng database transaction với dữ liệu nghiệp vụ.

~~~sql
BEGIN;

INSERT INTO orders (order_id, status)
VALUES (:order_id, 'PENDING_PAYMENT');

INSERT INTO outbox_events (
    event_id,
    aggregate_id,
    event_type,
    payload,
    created_at
)
VALUES (
    :event_id,
    :order_id,
    'PaymentRequested',
    :payload,
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

Sau commit, worker đọc outbox và publish event. Worker có thể gửi lặp nếu publish thành công nhưng việc đánh dấu sent thất bại. Vì vậy, consumer cần idempotent hoặc có inbox/deduplication key.

Outbox không tạo exactly-once delivery tuyệt đối. Nó giúp không mất ý định phát event giữa commit dữ liệu và publish message; delivery thường là at-least-once và phải xử lý duplicate.

## 9. Transaction boundary và propagation trong Spring

Spring cung cấp transaction management qua annotation hoặc API tường minh. Cần hiểu propagation vì một method được gọi bên trong transaction có thể tham gia transaction hiện tại hoặc tạo transaction riêng.

### REQUIRED

Đây là propagation mặc định:

- Nếu caller đã có transaction, method tham gia transaction đó.
- Nếu chưa có, Spring tạo transaction mới.
- Khi method con thất bại và đánh dấu transaction rollback-only, caller không thể commit thành công transaction đó như bình thường.

Đây là lựa chọn thường phù hợp cho các service/repository con thuộc cùng một đơn vị công việc.

### REQUIRES_NEW

REQUIRES_NEW tạm ngưng transaction hiện tại và tạo transaction độc lập:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAuditAttempt(AuditEntry entry) {
    auditRepository.save(entry);
}
~~~

Transaction audit có thể commit ngay cả khi transaction ngoài rollback. Nhưng điều đó có nghĩa audit entry không thuộc cùng đơn vị nguyên tử với thay đổi nghiệp vụ.

Chỉ dùng khi thật sự muốn commit độc lập. Nếu dùng quá tùy tiện, có thể tạo trạng thái như audit nói một thao tác đã xảy ra trong khi thay đổi nghiệp vụ tương ứng bị rollback.

REQUIRES_NEW cũng có thể cần thêm một connection trong lúc transaction ngoài vẫn giữ connection bị suspend, làm tăng áp lực lên connection pool.

### NESTED

NESTED thường dùng savepoint bên trong transaction hiện tại nếu transaction manager và database hỗ trợ. Nó cho phép rollback một phần thao tác về savepoint, nhưng không phải một transaction độc lập đã commit.

Cần kiểm tra hỗ trợ thực tế của transaction manager và JDBC driver. Không nên giả định mọi DBMS hoặc mọi loại transaction manager đều hỗ trợ giống nhau.

### Self-invocation và ranh giới annotation

Trong Spring proxy-based transaction management, lời gọi một method có @Transactional từ method khác trong cùng instance thường không đi qua proxy. Vì vậy, annotation ở method được gọi nội bộ có thể không kích hoạt transaction như mong đợi.

Nên đặt transaction ở public application service method được gọi qua Spring bean proxy, hoặc dùng TransactionTemplate khi cần ranh giới tường minh. Cần kiểm tra cấu hình proxy và cách gọi thực tế của ứng dụng.

## 10. JDBC: quản lý ranh giới tường minh

Nếu dùng JDBC trực tiếp, application service hoặc một abstraction tương đương có thể sở hữu transaction:

~~~java
public void transfer(
        DataSource dataSource,
        long fromId,
        long toId,
        BigDecimal amount) throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            debit(connection, fromId, amount);
            credit(connection, toId, amount);
            insertTransferRecord(connection, fromId, toId, amount);

            connection.commit();
        } catch (SQLException | RuntimeException error) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                error.addSuppressed(rollbackError);
            }
            throw error;
        }
    }
}
~~~

Các helper debit, credit và insertTransferRecord nhận cùng Connection. Nhờ vậy, chúng tham gia cùng transaction. Nếu mỗi helper tự lấy một connection khác, chúng sẽ không còn nằm trong cùng transaction cục bộ.

Trong code production, cần xử lý thêm:

- Khôi phục trạng thái connection nếu connection được quản lý thủ công hoặc trả về pool.
- Phân biệt lỗi trước commit với lỗi trong lúc commit.
- Không tái sử dụng connection ở trạng thái không rõ sau lỗi.
- Kiểm tra số hàng bị ảnh hưởng.
- Bảo đảm rollback không che mất lỗi ban đầu.
- Dùng transaction manager/framework nếu ứng dụng đã có cơ chế quản lý tập trung.

Với JDBC connection pool, connection được trả về pool khi đóng; pool thường reset trạng thái, nhưng ứng dụng vẫn phải tuân thủ contract của pool và transaction manager.

## 11. Rollback rules và lỗi nghiệp vụ

Một exception không phải lúc nào cũng có nghĩa transaction sẽ tự rollback. Hành vi phụ thuộc framework và cấu hình.

Trong Spring, mặc định transaction thường rollback với RuntimeException và Error, nhưng checked exception không tự động kích hoạt rollback theo mặc định. Có thể khai báo:

~~~java
@Transactional(rollbackFor = BusinessRuleException.class)
public void executeUseCase(...) throws BusinessRuleException {
    // Các thay đổi database thuộc cùng use case.
}
~~~

Hoặc dùng RuntimeException cho lỗi khiến use case không thể hoàn tất, tùy quy ước dự án.

Cần phân biệt:

- **Validation trước transaction**: dữ liệu đầu vào sai, có thể từ chối trước khi mở transaction.
- **Business rule thất bại sau khi đọc dữ liệu**: transaction có thể cần rollback vì đã thực hiện một số thao tác.
- **Lỗi kỹ thuật**: deadlock, serialization failure, connection failure.
- **Kết quả không thành công nhưng là trạng thái nghiệp vụ hợp lệ**: ví dụ không đủ tồn kho. Có thể rollback phần giữ hàng và trả kết quả từ chối.

Nếu bắt exception rồi không ném lại, framework có thể hiểu phương thức hoàn tất bình thường và commit. Nếu cần rollback, phải đánh dấu rollback-only hoặc để exception phù hợp thoát khỏi transaction boundary.

## 12. Ranh giới transaction và isolation level

Transaction boundary xác định những thao tác nào cùng commit. Isolation level xác định cách transaction quan sát và phối hợp với transaction khác.

Hai quyết định này liên quan nhưng không thay thế nhau:

- Transaction đúng phạm vi nhưng isolation không phù hợp vẫn có thể gặp lost update, write skew hoặc phantom.
- Isolation SERIALIZABLE không sửa được một use case chia thành hai transaction riêng trong khi nghiệp vụ đòi hỏi chúng cùng commit.
- Khóa hàng có thể bảo vệ một phần dữ liệu nhưng không tự bao phủ những bảng hoặc predicate bị bỏ sót.

Ví dụ, khi xác nhận đặt chỗ, việc kiểm tra capacity và ghi reservation phải nằm trong một transaction có cơ chế concurrency phù hợp. Có thể dùng atomic conditional UPDATE, guard row, constraint hoặc SERIALIZABLE tùy mô hình.

Không nên chọn SERIALIZABLE cho mọi use case chỉ vì muốn an toàn. Hãy xác định bất biến, truy vấn và xung đột có thể xảy ra, rồi chọn isolation/locking/constraint tương ứng.

## 13. Transaction boundary không nên kéo dài qua thời gian người dùng chờ

Một màn hình chỉnh sửa có thể mở trong nhiều phút. Không nên bắt đầu transaction khi người dùng mở form rồi giữ transaction đến khi họ bấm Save.

Thay vào đó:

1. Đọc dữ liệu và version khi mở form.
2. Người dùng chỉnh sửa ngoài transaction.
3. Khi bấm Save, bắt đầu transaction ngắn.
4. UPDATE có điều kiện theo version đã đọc.
5. Nếu version không còn khớp, trả xung đột để người dùng tải lại hoặc hợp nhất thay đổi.
6. Commit nếu điều kiện thành công.

Ví dụ optimistic locking:

~~~sql
UPDATE documents
SET title = :new_title,
    body = :new_body,
    version = version + 1
WHERE document_id = :id
  AND version = :version_read;
~~~

Nếu không có hàng nào được cập nhật, dữ liệu đã thay đổi hoặc bản ghi không còn tồn tại. Ứng dụng không giữ khóa trong suốt thời gian người dùng suy nghĩ.

## 14. Job nền và xử lý theo lô

Một worker có thể xử lý hàng nghìn bản ghi. Đặt toàn bộ job trong một transaction dài có thể giữ nhiều khóa, chiếm connection và làm rollback rất tốn kém nếu lỗi ở cuối.

Nếu nghiệp vụ cho phép xử lý từng nhóm độc lập, có thể chia thành các transaction theo chunk:

~~~text
Lấy chunk 1
  BEGIN
  xử lý và cập nhật chunk 1
  COMMIT

Lấy chunk 2
  BEGIN
  xử lý và cập nhật chunk 2
  COMMIT

...
~~~

Mỗi chunk là một đơn vị commit riêng. Điều này thay đổi ngữ nghĩa: nếu chunk 3 thất bại, chunk 1 và 2 đã commit. Vì vậy cần:

- Xác định checkpoint.
- Làm thao tác có thể retry an toàn.
- Dùng idempotency key hoặc unique constraint cho bản ghi kết quả.
- Ghi nhận tiến độ bền vững.
- Xác định cách resume sau crash.
- Không chia nhỏ nếu nghiệp vụ yêu cầu toàn bộ batch phải nguyên tử.

Với job claim từ queue database, việc lấy một job, đánh dấu RUNNING và commit có thể là transaction ngắn. Xử lý công việc dài diễn ra ngoài transaction; kết quả được ghi bằng transaction khác, có lease hoặc claim token để xử lý worker chết và job hết hạn.

## 15. Quy trình kéo dài qua nhiều dịch vụ: Saga

Một transaction ACID cục bộ thường không thể bao trùm nhiều database và dịch vụ độc lập nếu không triển khai distributed transaction như XA/2PC. Trong kiến trúc microservices, mỗi service thường sở hữu database riêng.

Ví dụ đặt hàng có thể đi qua:

1. Order service tạo order PENDING.
2. Inventory service giữ hàng.
3. Payment service thu tiền.
4. Order service chuyển sang CONFIRMED.

Mỗi service có transaction cục bộ riêng. Nếu thanh toán thất bại sau khi đã giữ hàng, hệ thống cần một hành động bù để giải phóng hàng. Đây là mô hình Saga.

~~~text
Tạo order PENDING
       |
       v
Giữ inventory
       |
       v
Thanh toán
   /       \
Thành công  Thất bại
   |           |
   v           v
CONFIRMED   Hủy reservation
               |
               v
          Đánh dấu FAILED
~~~

Saga không phải một transaction database lớn. Nó là một quy trình gồm nhiều bước commit độc lập, có trạng thái tiến trình, retry, timeout và compensation.

Mỗi bước cần idempotent hoặc có operation id để message lặp không tạo hiệu ứng trùng. Compensation là một hành động nghiệp vụ mới, không phải rollback vật lý transaction đã commit trước đó.

## 16. Transaction boundary và ORM persistence context

Với ORM như JPA/Hibernate, persistence context theo dõi entity đã đọc và thay đổi. Khi flush hoặc commit, ORM đồng bộ các thay đổi xuống database.

Transaction boundary thường cũng là ranh giới hợp lý cho persistence context của một use case:

- Entity được tải trong transaction có thể được quản lý và cập nhật.
- Lazy loading thường cần persistence context còn mở.
- Sau khi transaction/persistence context đóng, entity có thể detached.
- Flush có thể xảy ra trước commit và phát hiện constraint violation hoặc lỗi SQL.
- Commit vẫn có thể thất bại dù method body đã chạy hết.

Không nên giữ persistence context mở tùy tiện qua toàn bộ vòng đời HTTP response nếu điều đó khiến query phát sinh ngoài transaction hoặc che giấu ranh giới truy cập dữ liệu. Hãy tải dữ liệu cần thiết trong transaction và trả DTO phù hợp.

Cũng cần nhớ rằng transaction database không đồng nghĩa mọi thay đổi object trong bộ nhớ tự được khôi phục khi rollback. Nếu ORM đã sửa entity trong persistence context rồi transaction rollback, hãy tránh tiếp tục dùng trạng thái object cũ như thể nó phản ánh database. Thường cần clear, refresh hoặc bỏ persistence context theo cách framework quản lý.

## 17. Các tình huống commit có kết quả không xác định

Có thể xảy ra mất kết nối đúng lúc client gửi COMMIT. Database có thể đã commit nhưng response không đến được ứng dụng. Ứng dụng không thể kết luận chắc chắn rằng transaction đã rollback.

Đây là ambiguous commit outcome.

Không nên tự động chạy lại một thao tác không idempotent như trừ tiền hoặc tạo thanh toán mà không có cơ chế nhận diện request đã xử lý. Dùng operation id/idempotency key được lưu bền vững cùng dữ liệu nghiệp vụ, rồi truy vấn trạng thái để xác định kết quả.

Với thao tác quan trọng:

- Mỗi yêu cầu có một idempotency key ổn định.
- Database có UNIQUE constraint trên phạm vi key.
- Kết quả xử lý được lưu trong cùng transaction.
- Request lặp đọc lại kết quả đã lưu.
- Side effect ngoài database được xử lý qua outbox/provider idempotency.

Ranh giới transaction giúp commit các thay đổi nội bộ cùng nhau; idempotency giúp xử lý trường hợp caller không biết transaction đã commit hay chưa.

## 18. Kiểm thử ranh giới transaction

Một bài test cần chứng minh cả trường hợp thành công và thất bại giữa chừng.

### Test tất cả cùng commit

- Gọi use case hợp lệ.
- Đọc lại các bảng liên quan bằng transaction/connection mới.
- Xác nhận order, order lines, inventory reservation và outbox event đều tồn tại.
- Xác nhận trạng thái nghiệp vụ đúng.

### Test rollback khi bước giữa thất bại

- Tạo dữ liệu ban đầu.
- Khiến bước giữ inventory hoặc ghi outbox thất bại.
- Gọi use case.
- Xác nhận order và order lines không được commit.
- Xác nhận inventory đã cập nhật ở bước trước được rollback.
- Xác nhận không có outbox event nửa chừng.

### Test ranh giới propagation

Nếu dùng REQUIRED, kiểm tra method con tham gia transaction hiện tại. Nếu dùng REQUIRES_NEW, kiểm tra transaction con có commit độc lập như dự kiến khi transaction ngoài rollback. Không dùng REQUIRES_NEW mà không kiểm tra hệ quả nghiệp vụ.

### Test lỗi ở commit

Một số lỗi như deferred constraint hoặc serialization failure có thể chỉ xuất hiện khi flush/commit. Test cần kiểm tra lỗi tại ranh giới thực tế, không chỉ trong method body.

### Test external side effect

- Nếu database rollback, không được có event đã publish hoặc email đã gửi như thể nghiệp vụ thành công.
- Nếu database commit nhưng worker chưa publish, outbox vẫn phải còn để xử lý lại.
- Nếu worker publish lặp, consumer phải xử lý idempotent.

Dùng integration test với đúng DBMS và transaction manager của ứng dụng. Mock repository đơn thuần không chứng minh được khóa, rollback hoặc isolation thực tế.

## 19. Những lỗi thiết kế thường gặp

### Mỗi repository tự commit

Một use case nhiều bước có thể để lại partial commit. Đặt transaction ở application service/use case và để repository tham gia transaction hiện tại.

### Mở transaction từ đầu HTTP request đến cuối response

Request có thể bao gồm xác thực, gọi dịch vụ ngoài, serialize response hoặc xử lý chậm. Những bước đó không cần giữ khóa database. Mở transaction quanh phần đọc/ghi cần nguyên tử.

### Gọi dịch vụ ngoài khi đang giữ khóa

Network latency không ổn định. Ghi trạng thái và outbox rồi xử lý external call sau commit.

### Dùng REQUIRES_NEW để “chắc chắn lưu được”

Transaction độc lập có thể commit dữ liệu không còn nhất quán với transaction ngoài. Chỉ dùng khi thật sự muốn hiệu ứng tồn tại độc lập.

### Bắt exception rồi trả success

Framework có thể commit nếu exception bị nuốt và transaction chưa được đánh dấu rollback-only. Xác định rõ exception nào cần rollback và kết quả nghiệp vụ nào là thất bại.

### Chia batch mà không có checkpoint/idempotency

Một phần batch có thể commit trước khi phần sau thất bại. Cần biết resume từ đâu và tránh xử lý trùng.

### Nghĩ một transaction bao trùm nhiều database

Transaction cục bộ thường chỉ bao phủ một resource manager. Nhiều database hoặc service cần distributed transaction có cấu hình phù hợp hoặc saga/outbox.

## 20. Quy trình chọn transaction boundary

1. **Xác định use case**: hành động nghiệp vụ nào đang được thực hiện?
2. **Viết bất biến**: điều kiện nào phải đúng sau khi commit?
3. **Liệt kê thay đổi database**: bảng, aggregate, counter, reservation và event nào cần cập nhật?
4. **Nhóm thay đổi nguyên tử**: những thay đổi nào phải cùng commit hoặc rollback?
5. **Tách thao tác bên ngoài**: HTTP, email, broker và thời gian chờ người dùng xử lý sau commit hoặc qua saga/outbox.
6. **Chọn application service làm điểm điều phối**: đặt transaction quanh use case, repository tham gia transaction hiện tại.
7. **Chọn propagation và rollback rules**: xác định REQUIRED, REQUIRES_NEW, savepoint và exception nào gây rollback.
8. **Chọn isolation/locking/constraint**: bảo vệ các bất biến dưới concurrency.
9. **Giữ transaction ngắn**: không sleep, gọi mạng hoặc chờ người dùng khi đang giữ khóa.
10. **Kiểm thử commit/rollback**: xác nhận dữ liệu thực tế trên database sau cả success và failure.
11. **Xử lý retry và kết quả không xác định**: retry toàn bộ transaction phù hợp, dùng idempotency và outbox.
12. **Đo vận hành**: thời gian transaction, lock wait, connection pool, deadlock và retry rate.

## 21. Bảng lựa chọn nhanh

| Tình huống | Ranh giới phù hợp |
|---|---|
| Một use case cập nhật nhiều bảng trong cùng database | Một transaction ở application service bao trùm các thay đổi bắt buộc cùng commit |
| Repository được gọi từ một use case đang có transaction | Tham gia transaction hiện tại, không tự commit riêng |
| Đọc dữ liệu cho màn hình chỉnh sửa | Transaction đọc ngắn; khi Save mở transaction ghi và kiểm tra version |
| Gửi email hoặc gọi payment provider | Sau commit qua outbox/worker; dùng idempotency |
| Batch có thể chia thành phần độc lập | Một transaction cho mỗi chunk, có checkpoint và retry an toàn |
| Quy trình qua nhiều service/database | Transaction cục bộ từng bước, điều phối bằng Saga/outbox |
| Audit cần tồn tại dù nghiệp vụ rollback | Có thể dùng transaction độc lập nếu yêu cầu được xác định rõ và chấp nhận tính độc lập |
| Công việc giữ khóa trong thời gian dài | Tách thành trạng thái/lease/reservation và nhiều transaction ngắn |

Ranh giới transaction tốt phản ánh chính xác một đơn vị công việc nghiệp vụ cần được lưu nhất quán. Application service thường là nơi phù hợp để điều phối các repository trong cùng transaction; các repository thực hiện thao tác dữ liệu và tham gia transaction hiện tại. Giữ transaction đủ rộng để bảo vệ bất biến, nhưng đủ ngắn để không giữ connection và khóa trong lúc chờ mạng hoặc người dùng. Với công việc vượt qua nhiều dịch vụ, hãy dùng outbox, idempotency và saga để quản lý các bước commit riêng biệt một cách có kiểm soát.
