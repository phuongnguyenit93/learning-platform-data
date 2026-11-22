# Auto-commit JDBC và lý do phải xác định ranh giới giao dịch rõ ràng

Một **giao dịch cơ sở dữ liệu (database transaction)** là một đơn vị công việc phải được **xác nhận cùng nhau** bằng `COMMIT` hoặc **hủy cùng nhau** bằng `ROLLBACK`. Trong Java, khi dùng JDBC thuần, chế độ **auto-commit** trên `java.sql.Connection` quyết định ứng dụng có tự điều khiển điểm commit hay mỗi câu SQL được tự commit sau khi hoàn thành.

Đây là đoạn code có thể nguy hiểm:

~~~java
updateAccountBalance(sourceId, minusAmount);
updateAccountBalance(targetId, plusAmount);
~~~

Hai lời gọi Java nằm cạnh nhau không có nghĩa chúng thuộc cùng transaction. Nếu mỗi method mở JDBC Connection với `autoCommit = true`, thao tác trừ tiền có thể đã commit trước khi thao tác cộng tiền chạy. Nếu thao tác thứ hai thất bại, số dư bị thay đổi một phần.

**JPA/Hibernate không xóa bỏ vấn đề này.** EntityManager, Session, dirty checking và flush đều làm việc với JDBC và database transaction ở bên dưới. Dù ứng dụng không viết SQL thủ công, vẫn phải xác định rõ **giao dịch bắt đầu ở đâu, bao gồm bước nào, ai commit và khi nào rollback**.

Bài học thuộc chương **Giao dịch** trong module *Data Persistence Relational Access ORM Hibernate*, minh họa JDBC chuẩn, Jakarta Persistence (`jakarta.persistence.*`), Hibernate ORM và Spring Data JPA khi phù hợp. SQL sử dụng PostgreSQL để minh họa; các hệ quản trị khác có thể có quy tắc transaction/DDL/isolation khác nhau.

## 1. Transaction là một đơn vị nghiệp vụ, không chỉ một câu SQL

Một thao tác nghiệp vụ có thể gồm nhiều hành động trên database:

~~~text
Đặt hàng:
  1. INSERT orders
  2. INSERT order_items
  3. UPDATE inventory
  4. INSERT order_history

Thành công tất cả → COMMIT
Một bước bắt buộc thất bại → ROLLBACK toàn bộ
~~~

Nếu transaction bao trùm đủ bốn bước, database có thể hủy các thay đổi chưa commit khi bước thứ ba thất bại. Nếu mỗi câu SQL tự commit, hai bước đầu có thể đã nằm vĩnh viễn trong database khi bước trừ kho báo lỗi.

Các thuộc tính **ACID** giúp hiểu lý do:

| Thuộc tính | Ý nghĩa | Liên hệ |
| --- | --- | --- |
| **Atomicity** | Một nhóm thao tác được commit hoặc rollback như một đơn vị | Không có đơn hàng nửa chừng |
| **Consistency** | Dữ liệu tuân thủ các ràng buộc và quy tắc được thực thi | FK, unique, check, quy tắc nghiệp vụ |
| **Isolation** | Transaction đồng thời ảnh hưởng và nhìn thấy nhau theo mức cô lập | Tránh các bất thường khi nhiều người sửa tồn kho |
| **Durability** | Thay đổi đã commit có tính bền vững theo cơ chế database | Đơn hàng đã xác nhận không tự biến mất trong phạm vi bảo đảm DB |

Tắt auto-commit giúp **kiểm soát atomicity qua nhiều statement**, nhưng không tự đảm bảo isolation hợp lý, logic nghiệp vụ đúng hoặc tránh mọi xung đột đồng thời.

## 2. Auto-commit nằm trên JDBC Connection

JDBC định nghĩa những phương thức quan trọng:

~~~java
boolean current = connection.getAutoCommit();

connection.setAutoCommit(false);

connection.commit();

connection.rollback();

connection.setAutoCommit(true);
~~~

Về nguyên tắc:

- Khi **`autoCommit = true`**, mỗi statement SQL hoàn thành được commit theo quy tắc của JDBC. Nhiều statement riêng lẻ **không được gom thành một transaction nghiệp vụ** chỉ vì chúng cùng nằm trong một method.
- Khi **`autoCommit = false`**, các statement được thực hiện trong transaction cần application code gọi `commit()` hoặc `rollback()` để kết thúc.
- `commit()` xác nhận những thay đổi thuộc transaction hiện tại.
- `rollback()` hủy những thay đổi chưa commit của transaction hiện tại.

Theo JDBC, kết nối mới thường mặc định auto-commit bật. Nhưng ứng dụng server có thể dùng `DataSource`, connection pool và transaction manager, nên **trạng thái thực tế lúc code nhận connection không nhất thiết là mặc định của driver**.

Khi tự quản JDBC thuần, dùng `connection.getAutoCommit()` để biết connection đó đang ở mode nào. Khi dùng Spring/JPA, đừng tự thay đổi mode của connection do framework quản lý.

### Statement completion là gì?

Với một lệnh `executeUpdate()` bình thường, auto-commit thường xảy ra khi statement hoàn thành. Với `SELECT` trả `ResultSet` hoặc lệnh có nhiều kết quả, JDBC có khái niệm hoàn thành statement sau khi các result set/kết quả liên quan được xử lý và đóng đúng cách.

Vì vậy không nên diễn đạt một cách tuyệt đối rằng “`executeQuery()` trả về là transaction đã commit ngay” cho mọi kiểu query hoặc cursor. Điểm mấu chốt là **statement được xem như đơn vị commit riêng**, thay vì toàn bộ nghiệp vụ nhiều statement.

## 3. Hậu quả khi chuyển tiền với auto-commit bật

Giả sử bảng tài khoản:

~~~sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    owner_name VARCHAR(120) NOT NULL,
    balance NUMERIC(15, 2) NOT NULL CHECK (balance >= 0)
);

INSERT INTO accounts(id, owner_name, balance)
VALUES (1, 'An', 1000.00),
       (2, 'Bình', 200.00);
~~~

Ứng dụng muốn chuyển 100 từ tài khoản 1 sang tài khoản 2.

~~~java
try (Connection connection = dataSource.getConnection()) {
    // Giả sử getAutoCommit() trả true.

    try (PreparedStatement debit = connection.prepareStatement(
             "UPDATE accounts SET balance = balance - ? WHERE id = ?"
         )) {
        debit.setBigDecimal(1, new BigDecimal("100.00"));
        debit.setLong(2, 1L);
        debit.executeUpdate();
    }

    // Nếu xảy ra exception ở đây, debit có thể đã commit.

    try (PreparedStatement credit = connection.prepareStatement(
             "UPDATE accounts SET balance = balance + ? WHERE id = ?"
         )) {
        credit.setBigDecimal(1, new BigDecimal("100.00"));
        credit.setLong(2, 2L);
        credit.executeUpdate();
    }
}
~~~

Nếu đang ở auto-commit true, chuỗi có thể là:

~~~text
Ban đầu:  Account 1 = 1000, Account 2 = 200

SQL debit thành công:
  Account 1 = 900, Account 2 = 200
  COMMIT

Lỗi trước SQL credit:
  Account 1 = 900, Account 2 = 200

Không có transaction còn mở để rollback debit.
~~~

Đó là **lỗi xác định ranh giới transaction**, không phải JDBC tự làm sai. Thao tác debit trên còn thiếu điều kiện kiểm tra đủ tiền và kiểm soát đồng thời; transaction là một phần thiết yếu nhưng không đủ cho nghiệp vụ tài chính production.

### Vì sao rollback sau cùng không cứu được?

Nếu SQL debit đã commit, lệnh `rollback()` của transaction về sau **không thể hủy commit trước đó**. Muốn hủy trọn vẹn hai thay đổi, phải đặt chúng trong cùng transaction **từ trước bước đầu tiên**.

## 4. Tắt auto-commit khi chính ứng dụng quản lý Connection

Trong JDBC thuần, nếu code trực tiếp sở hữu connection và không có transaction manager khác, ta có thể đặt:

~~~java
connection.setAutoCommit(false);
~~~

rồi commit hoặc rollback theo kết quả nghiệp vụ:

~~~java
connection.setAutoCommit(false);

try {
    debitAccount(connection);
    creditAccount(connection);
    writeTransferHistory(connection);

    connection.commit();
} catch (SQLException | RuntimeException ex) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        ex.addSuppressed(rollbackFailure);
    }
    throw ex;
}
~~~

Ở đây các hàm `debitAccount`, `creditAccount` và `writeTransferHistory` được giả định dùng **cùng chính connection nhận từ bên ngoài**. Nếu một hàm bí mật mở connection khác, ta không còn được bảo đảm tất cả SQL thuộc cùng transaction.

~~~mermaid
flowchart TD
    A["connection.setAutoCommit(false)"] --> B["SQL debit"]
    B --> C["SQL credit"]
    C --> D["SQL transfer history"]
    D --> E{"Tất cả thành công?"}
    E -- "Có" --> F["connection.commit()"]
    E -- "Không" --> G["connection.rollback()"]
~~~

Đừng nhầm “dùng cùng transaction” với “gọi những hàm có cùng tên transaction”: chúng thực sự phải chạy qua connection hoặc transaction context được điều phối chung.

## 5. Ví dụ JDBC đầy đủ hơn: chuyển tiền có kiểm tra dữ liệu

Đoạn sau minh họa cách dùng **một Connection, một transaction, prepared statements** và kiểm tra số hàng được cập nhật.

~~~java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(
        long fromId,
        long toId,
        BigDecimal amount
    ) throws SQLException {
        if (fromId == toId) {
            throw new IllegalArgumentException("Hai tài khoản phải khác nhau");
        }
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();
            boolean finished = false;

            try {
                connection.setAutoCommit(false);

                try (PreparedStatement debit = connection.prepareStatement(
                         "UPDATE accounts " +
                         "SET balance = balance - ? " +
                         "WHERE id = ? AND balance >= ?"
                     )) {
                    debit.setBigDecimal(1, amount);
                    debit.setLong(2, fromId);
                    debit.setBigDecimal(3, amount);

                    if (debit.executeUpdate() != 1) {
                        throw new IllegalStateException(
                            "Nguồn không tồn tại hoặc không đủ số dư"
                        );
                    }
                }

                try (PreparedStatement credit = connection.prepareStatement(
                         "UPDATE accounts " +
                         "SET balance = balance + ? WHERE id = ?"
                     )) {
                    credit.setBigDecimal(1, amount);
                    credit.setLong(2, toId);

                    if (credit.executeUpdate() != 1) {
                        throw new IllegalStateException(
                            "Tài khoản đích không tồn tại"
                        );
                    }
                }

                connection.commit();
                finished = true;
            } catch (SQLException | RuntimeException ex) {
                if (!finished) {
                    try {
                        connection.rollback();
                    } catch (SQLException rollbackError) {
                        ex.addSuppressed(rollbackError);
                    }
                }
                throw ex;
            } finally {
                // Chỉ khôi phục connection state khi transaction
                // đã được kết thúc hoặc đã cố gắng rollback.
                if (connection.getAutoCommit() != originalAutoCommit) {
                    connection.setAutoCommit(originalAutoCommit);
                }
            }
        }
    }
}
~~~

Ví dụ có chủ đích dùng `DataSource` do application sở hữu theo JDBC thuần. **Không áp dụng nguyên mẫu vào một Spring/JPA transaction đã được framework quản lý.** Đó là nơi transaction manager chịu trách nhiệm lifecycle và trạng thái JDBC Connection.

Đây cũng không phải thiết kế chuyển tiền production hoàn chỉnh. Ví dụ cần bổ sung định nghĩa currency/precision, kiểm soát retry, idempotency, deadlock, audit ledger, phân quyền và chiến lược khóa phù hợp. Nếu `rollback()` thất bại, trạng thái transaction có thể không còn chắc chắn; việc khôi phục auto-commit có thể lại phát lỗi và không nên được xem là cơ chế cứu transaction.

**Đặc điểm quan trọng:** Khi cập nhật tài khoản đích không thành công, exception đi tới `catch` và thực hiện rollback, nên thao tác trừ tiền chưa commit có thể bị hủy cùng lúc.

## 6. `PreparedStatement` không tự mở transaction chung

`PreparedStatement` giúp bind dữ liệu theo kiểu và tránh ghép chuỗi đầu vào trực tiếp vào SQL:

~~~java
PreparedStatement ps = connection.prepareStatement(
    "UPDATE accounts SET balance = balance + ? WHERE id = ?"
);

ps.setBigDecimal(1, amount);
ps.setLong(2, accountId);
ps.executeUpdate();
~~~

Nhưng `PreparedStatement` **không quyết định auto-commit mode**. Cùng một câu lệnh, nếu connection đang auto-commit true, statement thường được commit riêng; nếu false, nó tham gia transaction đang mở theo connection.

Tương tự, việc dùng một object `Statement` để gọi nhiều `executeUpdate()` liên tiếp không tự khiến chúng có atomicity chung. Ranh giới nằm ở **transaction của connection**, không nằm ở số object Java được tạo.

## 7. Điều gì xảy ra sau `commit()` hoặc `rollback()` khi auto-commit tắt?

Xem đoạn:

~~~java
connection.setAutoCommit(false);

statement1.executeUpdate();
statement2.executeUpdate();

connection.commit();

statement3.executeUpdate();
connection.rollback();
~~~

Trong mode manual commit, có thể hiểu:

~~~text
Transaction A:
  statement1
  statement2
  COMMIT

Transaction B:
  statement3
  ROLLBACK
~~~

Sau khi commit/rollback, những thao tác tiếp theo trên connection vẫn đang có `autoCommit=false` và thuộc một transaction mới theo hành vi JDBC/driver. `setAutoCommit(false)` không có nghĩa “chỉ có đúng một transaction cho toàn bộ tuổi thọ của connection”.

Hãy luôn kết thúc transaction trước khi trả connection cho pool hoặc chuyển connection sang phần mã khác.

## 8. `setAutoCommit(true)` có thể commit transaction hiện tại

Một lỗi tinh vi:

~~~java
connection.setAutoCommit(false);

doPartA(connection);
doPartB(connection);

// Muốn dọn trạng thái?
connection.setAutoCommit(true);
~~~

Theo hợp đồng JDBC, việc **đổi chế độ auto-commit** trong khi một transaction còn hoạt động có thể **commit transaction đó**. Vì vậy, `setAutoCommit(true)` không phải phép rollback hoặc thao tác cleanup vô hại.

Quy tắc an toàn khi tự điều khiển JDBC:

1. Chọn mode trước khi chạy thao tác nghiệp vụ.
2. Commit khi toàn bộ công việc thành công.
3. Rollback khi nghiệp vụ không thể hoàn tất.
4. Chỉ khôi phục mode sau khi transaction đã kết thúc theo chủ đích.
5. Không để helper bên trong transaction tự đổi mode của connection.

Nếu lệnh `setAutoCommit(...)` đặt lại đúng mode đang có, driver không nhất thiết coi đó là một lần thay đổi chế độ; nhưng đừng dùng nó để suy luận rằng các transaction khác nhau có thể được quản lý tùy tiện qua một setter.

## 9. Connection pool và transaction manager là hai tầng khác nhau

Ứng dụng server thường dùng pool như HikariCP:

~~~text
Request A → mượn Connection #7 → truy vấn → trả về pool
Request B → mượn lại Connection #7
~~~

Pool giúp **tái sử dụng connection**, quản lý số lượng kết nối và tài nguyên. Transaction manager giúp **bắt đầu, commit, rollback, đặt phạm vi transaction và phối hợp kết nối**.

Khi một connection bị đặt `autoCommit=false` rồi trả về pool với transaction chưa kết thúc, các hệ thống có thể xử lý khác nhau: pool có cơ chế reset, nhưng không nên kỳ vọng pool sẽ thay ứng dụng quyết định đúng logic rollback. Một connection hỏng hoặc chưa được cleanup đầy đủ cũng có thể gây lỗi khó truy vết.

Một số pool cho phép cấu hình mặc định:

~~~properties
spring.datasource.hikari.auto-commit=true
~~~

Đây là **ví dụ về thuộc tính cấu hình**, không phải khuyến nghị phải bật true. Trong transaction do Spring quản lý, transaction manager có thể tạm điều chỉnh auto-commit khi bắt đầu và kết thúc transaction.

**Không trực tiếp lấy Hibernate JDBC Connection rồi đổi auto-commit trong repository nếu Spring/Hibernate đang quản lý transaction đó.**

## 10. Hibernate vẫn sử dụng JDBC transaction ở phía dưới

Mô hình đơn giản:

~~~text
Business service
       ↓
JPA EntityManager / Hibernate Session
       ↓
Persistence context
  - managed entities
  - snapshots
  - dirty checking
       ↓
Flush → INSERT / UPDATE / DELETE
       ↓
JDBC Connection và transaction coordinator
       ↓
Relational database
~~~

Hibernate tự quản lý chuyện entity nào cần `INSERT`, `UPDATE` hoặc `DELETE`, nhưng SQL phải thực thi trong một **database transaction** phù hợp.

Ví dụ:

~~~java
Product product = em.find(Product.class, 10L);
product.changePrice(new BigDecimal("500000.00"));
em.flush();
~~~

`flush()` có thể phát SQL `UPDATE`, nhưng **chưa phải commit**. Nếu transaction sau đó rollback, database sẽ hủy thay đổi vừa flush.

| Hoạt động | Vai trò |
| --- | --- |
| `persist` | Đưa entity mới vào trạng thái managed để insert theo vòng đời |
| Dirty checking | Phát hiện thuộc tính persistent của managed entity thay đổi |
| `flush` | Đồng bộ những thao tác SQL pending với database |
| `commit` | Xác nhận transaction |
| `rollback` | Hủy thay đổi chưa commit của transaction |

Đừng nhầm `save()` của repository, `flush()` và `commit()` là ba cách gọi đồng nghĩa.

## 11. JPA resource-local: quản lý `EntityTransaction`

Với một persistence unit `RESOURCE_LOCAL`, ứng dụng có thể viết:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Customer customer = em.find(Customer.class, customerId);

    if (customer == null) {
        throw new IllegalArgumentException("Khách hàng không tồn tại");
    }

    PurchaseOrder order = new PurchaseOrder(orderCode, customer);
    em.persist(order);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Giả định `Customer` và `PurchaseOrder` đã ánh xạ thành entity hợp lệ và `emf` được bootstrap đúng. Với resource-local transaction, `tx.begin()/commit()/rollback()` là **ranh giới ứng dụng cần điều khiển**.

Không cần gọi:

~~~java
connection.setAutoCommit(false);
~~~

bên trong khối JPA này. Transaction coordinator/provider chịu trách nhiệm làm việc với JDBC Connection theo cấu hình.

### Có thể dựa vào auto-commit để `persist` ngoài transaction không?

Không nên. Jakarta Persistence/Hibernate có hợp đồng transaction và flush riêng; thao tác ghi/flush ngoài transaction thường không được phép hoặc không có hành vi đảm bảo như ứng dụng mong muốn, có thể gây `TransactionRequiredException`.

**JDBC auto-commit true không thay thế `EntityTransaction.begin()`** của ORM.

### JTA khác resource-local

Nếu `EntityManager` do application server, JTA hoặc framework container quản lý, thông thường ứng dụng không gọi `em.getTransaction().begin()`. Khi đó ranh giới transaction được mở/đóng qua JTA hoặc framework phù hợp.

## 12. Hibernate Session cũng có transaction boundary riêng

Trong Hibernate native API:

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    try {
        Product product =
            session.find(Product.class, productId);

        product.changePrice(new BigDecimal("500000.00"));

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
~~~

`Session` quản lý persistence context, còn `Transaction` biểu diễn ranh giới commit/rollback. **Mở Session không tự tạo một transaction nghiệp vụ hoàn chỉnh.**

Hibernate có thể trì hoãn việc lấy JDBC Connection cho đến khi cần SQL. Không nên suy luận từ `session.beginTransaction()` rằng provider bắt buộc phải mở connection vật lý mới hoặc phát một câu SQL `BEGIN` hiển thị trong log ngay thời điểm đó.

Quan trọng là các thay đổi được ghi trong một transaction và có người sở hữu việc commit/rollback rõ ràng.

## 13. Spring `@Transactional`: đặt boundary ở tầng service

Trong Spring Data JPA, transaction thường được khai báo ở **entry point của nghiệp vụ**:

~~~java
@Service
public class CheckoutService {
    private final OrderRepository orders;
    private final OrderItemRepository items;
    private final InventoryRepository inventory;

    public CheckoutService(
        OrderRepository orders,
        OrderItemRepository items,
        InventoryRepository inventory
    ) {
        this.orders = orders;
        this.items = items;
        this.inventory = inventory;
    }

    @Transactional
    public Long placeOrder(PlaceOrderCommand command) {
        Order order =
            orders.save(Order.newOrder(command.customerId()));

        for (OrderLineCommand line : command.lines()) {
            items.save(OrderItem.forOrder(order, line));

            int affected = inventory.reserve(
                line.productId(),
                line.quantity()
            );

            if (affected != 1) {
                throw new IllegalStateException(
                    "Không còn đủ tồn kho"
                );
            }
        }

        return order.getId();
    }
}
~~~

Các lớp `Order`, `OrderItem`, `PlaceOrderCommand` và repository trong ví dụ là thành phần giả định của một ứng dụng Spring; cần bổ sung import, entity mapping, logic validation và SQL reserve phù hợp nếu áp dụng trong dự án thực.

Với transaction manager được cấu hình đúng:

~~~text
CheckoutService.placeOrder()
  ├── orders.save(...)
  ├── items.save(...)
  ├── inventory.reserve(...)
  └── kết thúc method
        ├── thành công → commit
        └── lỗi cần rollback → rollback
~~~

**Một transaction service bao trùm nhiều repository.** Nếu không có boundary này, mỗi lời gọi repository có thể tự chạy transaction riêng theo cấu hình, dẫn đến đơn hàng được commit dù thao tác kho sau đó thất bại.

### Rollback mặc định trong Spring

Với transaction interceptor thông dụng, Spring mặc định rollback khi `RuntimeException` hoặc `Error` thoát khỏi method, còn checked exception không luôn gây rollback theo mặc định.

Nếu nghiệp vụ cần rollback cả checked exception:

~~~java
@Transactional(rollbackFor = Exception.class)
public void performWork() throws Exception {
    // ...
}
~~~

Đây là một lựa chọn có chủ đích, không nhất thiết cần trong mọi service. Cần thống nhất exception nào biểu thị lỗi nghiệp vụ phải hủy transaction.

### Nuốt exception có thể khiến transaction commit

~~~java
@Transactional
public void placeOrder() {
    orders.save(...);

    try {
        inventory.reserve(...);
    } catch (RuntimeException ex) {
        log.warn("Dự trữ kho thất bại", ex);
        // Method vẫn kết thúc bình thường.
    }
}
~~~

Nếu không có trạng thái rollback-only hoặc lỗi khác, transaction **có thể commit** thao tác `orders.save`. Ngược lại, một số lỗi persistence đã đánh dấu transaction rollback-only thì lúc commit có thể xuất hiện `UnexpectedRollbackException`.

Vì vậy đừng catch exception rồi bỏ qua khi nghiệp vụ yêu cầu mọi bước phải thành công. Ném lại exception, xử lý rollback-only hoặc thay đổi luồng nghiệp vụ theo quy tắc rõ ràng.

## 14. Self-invocation có thể làm `@Transactional` không hoạt động

Spring transaction management dạng proxy thường chặn những lời gọi đi **qua proxy**. Ví dụ:

~~~java
@Service
public class PaymentService {
    public void processPayment() {
        writePayment(); // this.writePayment(), không qua proxy.
    }

    @Transactional
    public void writePayment() {
        // Ghi DB.
    }
}
~~~

Trong cấu hình proxy-based thông dụng, lời gọi nội bộ từ `processPayment` tới `writePayment` có thể **không kích hoạt transaction interceptor** cho method bên trong.

Giải pháp thường là:

- Đặt `@Transactional` trên public service entry point được gọi qua proxy.
- Hoặc tách method transactional sang bean khác để gọi qua Spring proxy.
- Kiểm tra transaction management đã bật và transaction manager phù hợp được cấu hình.

Cơ chế AspectJ weaving hoặc kiểu interception khác có quy tắc riêng. Không mặc định annotation luôn tạo transaction chỉ vì nhìn thấy nó trên method Java.

## 15. Transaction propagation có thể chia nghiệp vụ thành nhiều commit

Spring có các propagation mode như `REQUIRED`, `REQUIRES_NEW` và `NESTED`.

| Propagation | Ý nghĩa thường gặp |
| --- | --- |
| `REQUIRED` | Tham gia transaction hiện tại; tạo transaction mới nếu chưa có |
| `REQUIRES_NEW` | Mở transaction độc lập, tạm treo transaction cũ theo khả năng manager |
| `NESTED` | Dùng nested boundary/savepoint khi được transaction manager và database hỗ trợ |

Giả sử:

~~~java
@Transactional
public void placeOrder() {
    orderRepository.save(...);
    auditService.recordAuditInNewTransaction();
    inventoryService.reserve(...);
}
~~~

Nếu `recordAuditInNewTransaction` dùng `REQUIRES_NEW` và thực sự được gọi qua proxy, audit có thể **commit độc lập**. Sau đó nếu reserve lỗi khiến transaction ngoài rollback, audit record vẫn có thể tồn tại.

Đôi khi đó là yêu cầu nghiệp vụ đúng — ví dụ ghi lại một nỗ lực thất bại. Nhưng nếu toàn bộ workflow phải atomic, việc tách `REQUIRES_NEW` có thể phá kỳ vọng.

`NESTED` không đồng nghĩa một transaction độc lập; nó có thể dựa trên JDBC savepoint thuộc transaction ngoài. Khả năng hỗ trợ phụ thuộc transaction manager và database.

## 16. `flush` không phải `commit`

Một ví dụ:

~~~java
@Transactional
public void updatePrice(long productId, BigDecimal price) {
    Product p = em.find(Product.class, productId);

    p.changePrice(price);
    em.flush(); // Có thể phát UPDATE trong transaction.
}
~~~

Luồng thực thi:

~~~text
Transaction bắt đầu
   ↓
find → SELECT
   ↓
changePrice → object dirty
   ↓
flush → UPDATE
   ↓
method return
   ↓
transaction manager COMMIT
~~~

Nếu có lỗi sau `flush` nhưng trước `commit` và transaction bị rollback, UPDATE cũng bị rollback. **Đã thấy SQL UPDATE trên log không có nghĩa dữ liệu đã commit.**

Ngược lại, nếu không gọi `flush()` thủ công, Hibernate thường flush những thay đổi managed cần đồng bộ trước khi commit. Flush mode `AUTO` cũng có thể khiến provider flush trước một số query khi cần đảm bảo kết quả nhất quán với pending changes.

Không thêm `flush` sau mọi setter chỉ để “chắc chắn lưu”. Thao tác này có thể làm tăng round trip và giảm khả năng batching mà không giải quyết vấn đề thiếu transaction boundary.

## 17. Với một SQL đơn lẻ, auto-commit có thể phù hợp

Không phải mọi trường hợp JDBC đều cần tắt auto-commit thủ công. Ví dụ thao tác độc lập:

~~~sql
UPDATE products
SET stock_quantity = stock_quantity - 1
WHERE id = 10 AND stock_quantity > 0;
~~~

Nếu toàn bộ yêu cầu nghiệp vụ thực sự chỉ là **một statement độc lập**, tự commit statement có thể phù hợp. Database vẫn phải bảo đảm ràng buộc và concurrency đúng.

Nhưng nếu thao tác trừ kho đi kèm tạo order, ghi lịch sử và thanh toán trong cùng đơn vị nghiệp vụ, một statement auto-commit không cung cấp atomicity cho những bước còn lại.

| Nhu cầu | Đánh giá auto-commit per statement |
| --- | --- |
| Một SELECT độc lập | Thường đủ nếu không cần snapshot qua nhiều query |
| Một UPDATE độc lập, có constraint đầy đủ | Có thể phù hợp trong JDBC thuần |
| Trừ tiền và cộng tiền bằng hai UPDATE | Không phù hợp |
| Đặt hàng, thêm dòng và trừ tồn kho | Không phù hợp |
| Nhiều SELECT cần cùng một snapshot | Có thể cần read-only transaction với isolation phù hợp |
| Ghi DB và gửi email/message | Một DB transaction chưa đủ để rollback external side effect |

**Đơn vị transaction cần được chọn theo tính nguyên tử của nghiệp vụ**, không phải cứ một method Java là một transaction hoặc mọi lệnh SQL là một transaction.

## 18. Atomicity không giải quyết hết concurrent updates

Hai transaction có thể cùng thấy tồn kho bằng 1 và cùng chấp nhận đặt hàng nếu logic đọc-kiểm tra-ghi không có bảo vệ đồng thời.

~~~text
Transaction A           Transaction B
SELECT stock = 1        SELECT stock = 1
Chấp nhận đơn           Chấp nhận đơn
UPDATE stock = 0        UPDATE stock = 0
~~~

Để tránh thao tác “đọc rồi gán” dựa trên trạng thái cũ, có thể dùng một conditional SQL:

~~~sql
UPDATE products
SET stock_quantity = stock_quantity - :quantity
WHERE id = :productId
  AND stock_quantity >= :quantity;
~~~

Kiểm tra affected row count phải bằng 1 rồi mới coi reserve thành công. Nếu thao tác này thuộc một đơn hàng nhiều bước, nó vẫn cần nằm trong transaction chung.

Các công cụ phối hợp:

- **Unique, CHECK và FOREIGN KEY** constraint tại DB.
- **Optimistic locking** với `@Version` trong JPA/Hibernate.
- **Pessimistic locking** khi cần giữ khóa hàng.
- **Transaction isolation** như READ COMMITTED hoặc SERIALIZABLE theo DB.
- **Conditional UPDATE**, kiểm tra row count và retry có kiểm soát.

Tắt auto-commit là điều kiện về **atomicity**, không phải giải pháp cho mọi race condition.

## 19. `SELECT FOR UPDATE` phải nằm trong transaction đủ dài

Một lệnh SQL:

~~~sql
SELECT balance
FROM accounts
WHERE id = 1
FOR UPDATE;
~~~

được dùng để khóa hàng theo quy tắc database. Nếu connection auto-commit true, statement hoàn thành sẽ kết thúc transaction riêng của nó; lock có thể được giải phóng trước khi ứng dụng tính toán rồi chạy UPDATE ở statement tiếp theo.

~~~text
Sai ý định:
  SELECT ... FOR UPDATE → auto-commit, khóa được giải phóng
  tính toán
  UPDATE ...            → transaction khác
~~~

Đúng hơn khi nghiệp vụ cần giữ lock xuyên qua nhiều SQL:

~~~text
BEGIN TRANSACTION
  SELECT ... FOR UPDATE
  tính toán
  UPDATE ...
COMMIT
~~~

Trong JPA:

~~~java
Account account = em.find(
    Account.class,
    accountId,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Phải có transaction phù hợp và database hỗ trợ locking tương ứng. Reference/getter hoặc Session tự thân không phải công cụ giữ lock nếu thiếu transaction.

## 20. Transaction quá dài cũng nguy hiểm

Không nên mở transaction trong lúc chờ người dùng xác nhận hoặc chờ các tác vụ mạng dài mà không cần thiết:

~~~text
BEGIN TRANSACTION
  đọc vài hàng
  gọi API ngoài mất 15 giây
  chờ user nhập dữ liệu
  giữ lock
  cập nhật DB
COMMIT
~~~

Transaction dài có thể giữ JDBC Connection, lock hoặc snapshot lâu, làm tăng contention, deadlock và giảm throughput.

Thiết kế thường phù hợp:

1. Validate đầu vào thuần Java trước nếu không cần DB.
2. Mở transaction khi chuẩn bị thao tác dữ liệu cần nhất quán.
3. Thực hiện các bước DB liên quan và locking cần thiết.
4. Commit hoặc rollback dứt điểm.
5. Kết thúc context/connection theo framework.

**Transaction ngắn không đồng nghĩa mỗi SQL tự commit.** Nó là một transaction không chứa các khoảng chờ không cần thiết, nhưng vẫn đủ để bao trùm đơn vị nghiệp vụ atomic.

## 21. Side effect ngoài database không tự rollback

Ví dụ:

~~~java
@Transactional
public void placeOrder(...) {
    orderRepository.save(...);
    emailSender.sendConfirmation(...);
    inventoryRepository.reserve(...); // Lỗi.
}
~~~

Khi transaction DB rollback, email đã gửi **không được thu hồi**. Một HTTP request hoặc message broker ngoài cũng không mặc định tham gia cùng JDBC transaction.

Giải pháp phổ biến cho bài toán phát sự kiện sau khi ghi DB là **transactional outbox**:

~~~text
Trong một DB transaction:
  INSERT orders
  INSERT order_items
  INSERT outbox_events
COMMIT

Sau commit:
  Worker đọc outbox_events
  → gửi message
  → retry khi thất bại
~~~

Như vậy thông tin cần phát message được lưu atomic cùng nghiệp vụ DB. Để tránh xử lý trùng khi retry, hệ thống cần consumer idempotent và quy tắc delivery phù hợp. Outbox không tự bảo đảm “exactly once” ở toàn bộ hệ thống.

Một transaction database cục bộ cũng không tự bao trùm hai database khác nhau; các phương án distributed transaction/XA hoặc orchestration/compensation cần được đánh giá riêng.

## 22. Lỗi commit/rollback và trạng thái sau exception

Với JDBC thuần:

~~~java
connection.setAutoCommit(false);

try {
    performFirstStep(connection);
    performSecondStep(connection);
    connection.commit();
} catch (SQLException | RuntimeException ex) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
    }
    throw ex;
}
~~~

Không chỉ bắt `SQLException` nếu application logic cũng có thể ném runtime exception và nghiệp vụ cần rollback.

Với JPA resource-local:

~~~java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();
    performJpaWork(em);
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
~~~

Một transaction thất bại cần được kết thúc rõ ràng; sau lỗi persistence nghiêm trọng nên đóng/loại bỏ persistence context đang lỗi thay vì tiếp tục dùng như chưa có chuyện gì.

**Rollback không tự hoàn tác biến Java:** nếu object `Product` được đổi giá rồi transaction rollback, object vẫn có thể giữ giá mới. Muốn làm việc tiếp với trạng thái xác thực từ database, nạp lại trong context mới.

### Commit thất bại có chắc database đã rollback không?

Nếu kết nối mạng hỏng đúng lúc client chờ kết quả commit, có thể phát sinh trạng thái **không biết chắc transaction đã commit ở server chưa**. Không retry mù một thao tác tạo đơn/ghi tiền vì có nguy cơ tạo bản ghi trùng. Nên có idempotency key hoặc mã yêu cầu duy nhất để đối soát.

## 23. Savepoint không tạo transaction độc lập

JDBC có cơ chế savepoint:

~~~java
connection.setAutoCommit(false);

Savepoint point = connection.setSavepoint("optional_step");

try {
    performOptionalStep(connection);
} catch (SQLException ex) {
    connection.rollback(point);
}

performRequiredStep(connection);
connection.commit();
~~~

`rollback(point)` hủy các thay đổi sau điểm lưu, nhưng phần còn lại vẫn thuộc **transaction ngoài**. Nếu transaction ngoài rollback, toàn bộ thay đổi chưa commit vẫn bị hủy.

Savepoint chỉ nên dùng khi nghiệp vụ cho phép một bước tùy chọn thất bại nhưng vẫn có thể commit những bước còn lại. Khả năng hỗ trợ savepoint và cách xử lý transaction sau lỗi phụ thuộc driver/database.

Nếu code đang dùng Spring/JTA/Hibernate transaction manager, không tự thao tác savepoint trên JDBC Connection mà framework đang quản lý; sử dụng cơ chế nested/transaction API phù hợp.

## 24. Read-only transaction khác auto-commit

JDBC có:

~~~java
connection.setReadOnly(true);
~~~

Spring có:

~~~java
@Transactional(readOnly = true)
public List<ProductDto> report() {
    // ...
}
~~~

Read-only là **gợi ý/chế độ được framework và DB diễn giải theo cấu hình**, không phải thay thế commit/rollback. Một transaction chỉ đọc có thể vẫn cần thiết khi nhiều SELECT phải nhìn một snapshot nhất quán hoặc có yêu cầu locking.

Một ứng dụng không nên đặt `@Transactional(readOnly=true)` trên method ghi rồi kỳ vọng mọi thay đổi entity tự commit bình thường. Trong Spring + Hibernate, read-only có thể ảnh hưởng flush mode và dirty checking tùy phiên bản/cấu hình.

Tương tự, một connection có auto-commit true **không bảo đảm hai SELECT liên tiếp thấy cùng một snapshot dữ liệu**. Nếu report cần nhất quán qua nhiều query, cần xem transaction isolation của database.

## 25. DDL có thể commit khác với DML

Các database không có một hành vi thống nhất cho transactional DDL. Một số hệ quản trị implicit commit khi thực thi `CREATE TABLE` hoặc `ALTER TABLE`; PostgreSQL hỗ trợ transactional DDL cho nhiều thao tác nhưng vẫn có ngoại lệ.

Vì vậy đừng mặc định:

~~~text
setAutoCommit(false)
CREATE TABLE ...
INSERT ...
rollback()
~~~

sẽ luôn xóa cả bảng vừa tạo trên mọi database. Quản lý schema nên có migration tool/quy trình DBA và hiểu quy tắc commit của DDL trên hệ quản trị đang dùng.

Các ví dụ atomicity trong bài chủ yếu nói về DML nghiệp vụ như `INSERT`, `UPDATE` và `DELETE`.

## 26. Cấu hình auto-commit trong Hibernate cần cực kỳ thận trọng

Hibernate có các thuộc tính connection provider liên quan auto-commit. Một tùy chọn nâng cao:

~~~properties
hibernate.connection.provider_disables_autocommit=true
~~~

Khi cấu hình này được bật, Hibernate **tin rằng connection provider đã cấp connection với auto-commit tắt**, nên có thể bỏ qua một số thao tác điều chỉnh mode lúc bắt đầu transaction.

**Đừng bật nếu pool/provider thực tế vẫn trả connection có autoCommit=true.** Nếu cấu hình khẳng định sai trạng thái, SQL có thể bị commit từng statement dù code ORM tin rằng nó đang nằm trong transaction rộng hơn. Đây là lỗi **tính đúng đắn dữ liệu**, không đơn thuần là hiệu năng.

Những phiên bản Hibernate khác nhau có cách quản lý connection acquisition/auto-commit và tên setting khác nhau. Với Spring Boot/HikariCP, nên để transaction manager và Hibernate được cấu hình nhất quán; chỉ tối ưu setting này khi hiểu rõ cam kết của connection provider.

### Tại sao không chỉnh connection trong `Session.doWork`?

Đoạn như:

~~~java
session.doWork(
    connection -> connection.setAutoCommit(false)
);
~~~

không phải cách chuẩn để định nghĩa transaction khi Hibernate Session đã có transaction coordinator. Can thiệp vào JDBC Connection bên dưới có thể làm trạng thái provider và transaction manager không còn đồng bộ. Hãy dùng `session.beginTransaction()` hoặc transaction framework đang quản lý.

## 27. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Bước đầu đã commit trước khi bước sau lỗi | Auto-commit true hoặc nhiều transaction rời rạc | Đặt boundary bao trùm nghiệp vụ |
| `rollback()` không hoàn tác bước cũ | Bước cũ đã commit | Mở transaction trước bước đầu |
| Gọi `commit()` khi auto-commit true bị lỗi | Trộn manual transaction API với auto-commit | Chọn mode và owner rõ ràng |
| `@Transactional` không tạo transaction | Self-invocation/proxy/configuration | Đặt boundary ở entry point qua proxy |
| Exception bị catch nhưng DB vẫn có dữ liệu | Nuốt lỗi, rollback rule không phù hợp | Ném lại hoặc đánh dấu rollback có chủ đích |
| Hibernate in SQL UPDATE nhưng dữ liệu không còn | Flush đã chạy nhưng transaction rollback | Phân biệt flush với commit |
| `SELECT FOR UPDATE` không giữ khóa đủ lâu | Statement auto-commit riêng | Dùng một transaction bao quanh read/update |
| Connection trả về pool rồi request sau gặp vấn đề | Connection state/transaction chưa được xử lý đúng | Để pool/manager quản lý lifecycle |
| Dùng `REQUIRES_NEW` dẫn đến audit commit độc lập | Propagation tách transaction | Chọn theo yêu cầu nghiệp vụ |
| Bật `provider_disables_autocommit` nhưng SQL commit riêng | Provider không thật sự tắt auto-commit | Sửa cấu hình pool và flag |
| Flush/commit báo constraint violation | Schema ngăn thay đổi không hợp lệ | Rollback và xử lý dữ liệu/logic |
| Gửi email rồi DB rollback | Email nằm ngoài JDBC transaction | Outbox/after-commit processing |
| Query đọc nhiều lần thấy dữ liệu khác | Isolation/snapshot không phù hợp | Xem transaction read-only và isolation |
| Commit exception nhưng không biết trạng thái | Mất kết nối ở ranh giới commit | Idempotency và kiểm tra lại kết quả |

Nhìn thấy SQL trong log **không đủ để khẳng định commit đã hoàn tất**. Cần xác định transaction manager, ranh giới và trạng thái dữ liệu cuối cùng sau commit hoặc rollback.

### Quan sát transaction khi phát triển

Spring có thể log thông tin transaction:

~~~properties
logging.level.org.springframework.transaction=DEBUG
logging.level.org.hibernate.SQL=DEBUG
~~~

Logger cụ thể có thể khác theo phiên bản Spring/Hibernate. Tránh bật logging bind parameter nhạy cảm trên production; log SQL và transaction nên gắn với request/correlation ID để tìm đúng một workflow.

## 28. Kịch bản kiểm tra tính nguyên tử

Một service tạo đơn thực hiện:

~~~text
1. INSERT orders
2. INSERT order_items
3. UPDATE inventory
~~~

Để biết boundary có thật sự đúng, thử cho bước 3 **thất bại có chủ đích trong môi trường test**. Sau khi exception được xử lý và transaction kết thúc, đọc database bằng context/transaction mới để quan sát:

- Có còn `orders` do bước 1 tạo không?
- Có còn `order_items` do bước 2 tạo không?
- Tồn kho có bị trừ một phần không?
- Các FK/unique/check constraint có được giữ đúng không?

Nếu nghiệp vụ đòi cả ba bước thành công, tất cả những thay đổi chưa commit phải bị rollback khi bước 3 thất bại.

Một **unit test với mock repository** chỉ xác minh method được gọi; nó không chứng minh JDBC connection, transaction manager và database rollback đúng. Để kiểm tra atomicity cần integration test với database và transaction infrastructure phù hợp.

Đoạn này mô tả phương pháp kiểm tra, không yêu cầu chạy test trong bước viết Markdown.

## 29. Bài tập tình huống

**1. Hai `executeUpdate` liên tiếp có tự nằm trong một transaction không?**

Không. Chúng có cùng transaction hay không phụ thuộc connection auto-commit và transaction owner. Với autoCommit true, mỗi statement thường được commit riêng.

**2. Trừ tiền đã auto-commit, sau đó cộng tiền lỗi. Gọi rollback có cứu được không?**

Không, vì thao tác trừ tiền đã được commit. Cần một transaction bao quanh cả hai từ đầu.

**3. `setAutoCommit(false)` rồi đổi về true mà không commit/rollback có an toàn không?**

Không. Việc đổi mode có thể commit transaction đang hoạt động. Phải kết thúc transaction đúng chủ đích trước khi phục hồi cấu hình connection.

**4. Gọi `em.flush()` và không có exception nghĩa dữ liệu đã commit chưa?**

Chưa chắc. Flush có thể gửi SQL nhưng transaction vẫn có thể rollback.

**5. Một method service gọi ba repository nhưng không có `@Transactional`. Có atomicity chung không?**

Không được bảo đảm. Cần boundary ở tầng nghiệp vụ hoặc transaction API phù hợp.

**6. Tại sao `@Transactional` trên method được gọi bởi `this` đôi khi không hiệu lực?**

Trong Spring proxy mode, lời gọi nội bộ không đi qua proxy transaction nên interceptor có thể không mở transaction như kỳ vọng.

**7. Transaction read-only có ích cho hai SELECT không?**

Có thể. Nếu cần một snapshot nhất quán theo isolation của DB, boundary cho một nhóm query read-only vẫn quan trọng.

**8. `SELECT ... FOR UPDATE` rồi UPDATE ở một statement khác khi autoCommit true giữ lock được không?**

Không nên kỳ vọng. Lock của statement đầu có thể được giải phóng khi transaction auto-commit của statement đó kết thúc.

**9. `@Transactional(REQUIRES_NEW)` bên trong outer transaction có luôn rollback khi outer rollback không?**

Không. Transaction trong có thể commit độc lập khi propagation hoạt động như thiết kế.

**10. Vì sao không gọi `setAutoCommit(false)` trực tiếp trong repository Spring JPA?**

Vì JDBC Connection đã do Hibernate/transaction manager quản lý. Boundary phải khai báo qua transaction API của framework.

**11. Tắt auto-commit có ngăn mọi lỗi concurrency không?**

Không. Vẫn cần isolation, locking, unique constraint, versioning hoặc conditional updates theo nghiệp vụ.

**12. Database rollback có thu hồi email đã gửi không?**

Không. Email không thuộc local JDBC transaction; cân nhắc outbox và retry/đối soát.

**13. Chỉ sửa một cột bằng một SQL độc lập có bắt buộc manual transaction không?**

Không nhất thiết trong JDBC thuần; một statement auto-commit có thể phù hợp nếu nghiệp vụ thật sự chỉ gồm statement đó và không có yêu cầu isolation/atomicity rộng hơn.

**14. Bật `hibernate.connection.provider_disables_autocommit=true` nhưng pool trả connection autoCommit true có sao không?**

Có. Hibernate có thể không điều chỉnh mode và các statement tự commit trái kỳ vọng. Đây là rủi ro tính toàn vẹn dữ liệu.

## 30. Quy trình quyết định ranh giới transaction

~~~mermaid
flowchart TD
    A["Một workflow cần truy cập database"] --> B{"Nhiều thao tác phải cùng thành công?"}
    B -- "Có" --> C["Chọn một transaction nghiệp vụ"]
    B -- "Không" --> D{"Có cần snapshot hoặc lock qua nhiều SQL?"}
    D -- "Có" --> C
    D -- "Không" --> E["Statement riêng có thể phù hợp; giữ DB constraints"]
    C --> F{"Ai quản lý transaction?"}
    F -- "JDBC thuần" --> G["setAutoCommit(false), commit, rollback"]
    F -- "JPA resource-local" --> H["EntityTransaction"]
    F -- "Hibernate native" --> I["Session Transaction"]
    F -- "Spring / JTA" --> J["@Transactional / transaction manager"]
    G --> K["Kiểm tra isolation, rollback và connection cleanup"]
    H --> K
    I --> K
    J --> K
    K --> L["Giữ boundary vừa đủ, kiểm tra cả lỗi và thành công"]
~~~

Mỗi nhánh chọn một **chủ thể quản lý transaction**. Không phối hợp bằng cách vừa gọi `@Transactional`, vừa tự `setAutoCommit(false)` trên JDBC connection của Hibernate, vừa tự `commit()` ngoài framework.

## 31. Tổng kết

**JDBC auto-commit quyết định cách những statement SQL được xác nhận trên một Connection.** Khi auto-commit bật, một statement hoàn thành thường được commit như một transaction riêng. Nhiều statement Java nối tiếp nhau **không mặc nhiên có atomicity cho toàn bộ nghiệp vụ**. Khi auto-commit tắt, ứng dụng chịu trách nhiệm commit/rollback rõ ràng.

Trong JPA/Hibernate, **dirty checking** quyết định managed entity nào thay đổi, **flush** gửi SQL cần thiết, và **transaction commit/rollback** quyết định thay đổi có được xác nhận hay hủy. Spring `@Transactional`, JPA `EntityTransaction` hoặc Hibernate `Transaction` phải được dùng nhất quán với cơ chế quản lý connection hiện tại.

Các nguyên tắc cần nhớ:

1. **Chọn transaction boundary theo đơn vị nghiệp vụ**, không chỉ theo một method repository hoặc một câu SQL.
2. **Auto-commit true có thể làm workflow nhiều bước commit một phần**.
3. **Auto-commit false không đủ nếu rollback/exception handling sai**.
4. **Đổi auto-commit mode giữa transaction có thể dẫn tới commit**, nên cần kết thúc transaction trước khi reset connection.
5. **Connection pool không thay thế transaction manager**.
6. **Flush không phải commit**, SQL đã phát vẫn có thể rollback.
7. **Atomicity khác isolation**; concurrency cần giải pháp riêng.
8. **Không giữ transaction quá dài**, nhưng cũng không chia quá nhỏ làm mất tính nguyên tử.
9. **HTTP, email và message không tự rollback** cùng database.
10. **Kiểm chứng bằng tình huống lỗi**, không chỉ bằng log SQL thành công.

Khi xác định rõ **giao dịch bắt đầu ở đâu, bước nào phải cùng commit, ai rollback và ai quản lý JDBC Connection**, ứng dụng JDBC/JPA/Hibernate mới có thể bảo vệ tính nhất quán của một nghiệp vụ hoàn chỉnh thay vì chỉ của từng câu SQL riêng lẻ.
