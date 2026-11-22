# Mở, sử dụng và đóng Session khi giao dịch thành công hoặc thất bại

Trong Hibernate, `Session` là đối tượng trung tâm để truy cập và thay đổi dữ liệu theo mô hình ORM. Ứng dụng dùng `Session` để tải entity, lưu entity mới, cập nhật trạng thái, xóa, thực thi truy vấn và đồng bộ các thay đổi xuống database. Nhưng `Session` đồng thời **giữ trạng thái và sở hữu tài nguyên trong một phạm vi làm việc nhất định**. Vì thế, một tác vụ Hibernate đúng không chỉ cần câu query hoặc lệnh `persist()` đúng; nó phải mở session đúng lúc, quản lý transaction rõ ràng và luôn kết thúc session, kể cả khi giao dịch thất bại.

Đường đi phổ biến khi ứng dụng tự quản lý Hibernate là:

~~~mermaid
flowchart TD
    A["SessionFactory sống trong suốt vòng đời ứng dụng"] --> B["openSession(): tạo Session cho một đơn vị công việc"]
    B --> C["beginTransaction()"]
    C --> D["Đọc / persist / sửa managed entity / remove / query"]
    D --> E{"Có ngoại lệ?"}
    E -- "Không" --> F["commit(): flush phần chờ và xác nhận transaction"]
    E -- "Có" --> G["rollback() nếu transaction còn có thể rollback"]
    F --> H["close(): giải phóng tài nguyên Session"]
    G --> H
    H --> I["Kết thúc đơn vị công việc"]
~~~

Sơ đồ mô tả luồng mong muốn, nhưng **`commit()` cũng có thể ném ngoại lệ**: khi đó ứng dụng phải chuyển sang xử lý lỗi và kết thúc session. Trong Java, `try-with-resources` là cơ chế đặc biệt phù hợp để bảo đảm `close()` được gọi ở mọi đường đi.

> Bài học sử dụng Hibernate ORM 6.x và `org.hibernate.Session`/`SessionFactory`. Với Hibernate 5, nguyên tắc vòng đời tương tự nhưng chi tiết API, logging và hành vi transaction có thể khác. Phần dùng trực tiếp `Session` phù hợp kiểu ứng dụng **application-managed**; trong Spring hoặc Jakarta EE, framework/container thường sở hữu transaction và session, do đó mẫu sử dụng phải điều chỉnh theo chủ sở hữu tài nguyên.

## 1. Phân biệt SessionFactory, Session, JDBC Connection và Transaction

Để tránh mở/đóng nhầm tài nguyên, trước hết cần phân biệt bốn đối tượng:

| Thành phần | Vai trò | Vòng đời mong muốn |
|---|---|---|
| `SessionFactory` | Giữ metadata mapping, dịch vụ Hibernate, cấu hình và cơ chế tạo `Session`. | Tạo ít lần, thường một lần khi ứng dụng khởi động; dùng chung giữa các luồng; đóng khi ứng dụng dừng. |
| `Session` | Một persistence context, first-level cache, entity state và API thực hiện các thao tác ORM. | Ngắn, tương ứng với một đơn vị công việc; **không thread-safe**; đóng sau khi xong. |
| `Transaction` | Điều phối ranh giới commit/rollback của giao dịch. | Bắt đầu trước đơn vị công việc DB và kết thúc bằng commit hoặc rollback. |
| JDBC `Connection` | Kênh làm việc thực tế với database thông qua driver, thường cấp bởi connection pool. | Hibernate có thể lấy khi cần và trả lại theo chế độ quản lý connection; không đồng nghĩa một connection được giữ suốt thời gian `Session` mở. |

Điểm khác biệt quan trọng:

- `SessionFactory` **không phải** thứ cần đóng sau mỗi request. Tạo lại factory cho mỗi query vừa tốn tài nguyên vừa mất lợi ích của metadata và pool/service đã khởi tạo.
- `Session` không nên giữ làm field singleton dùng chung cho nhiều request hoặc nhiều thread. Identity map, dirty state và transaction lifecycle của session không được thiết kế cho truy cập đồng thời tùy ý.
- `Session` **không đồng nghĩa một kết nối JDBC cố định**. Tùy Hibernate version, connection handling mode và môi trường transaction, connection có thể chỉ được lấy khi thực sự cần SQL và được trả về ở những thời điểm khác nhau.
- `Transaction` và `Session` có quan hệ chặt nhưng không phải cùng một đối tượng. Một session có thể tồn tại trước/sau transaction; điều đó không có nghĩa nên kéo dài session cho nhiều nghiệp vụ độc lập nếu không có chủ đích.

### Bên trong một Session có gì?

Một `Session` thường quản lý:

1. **Persistence context**: ánh xạ entity identity đến đối tượng managed trong bộ nhớ.
2. **State/snapshot và dirty checking**: phát hiện thay đổi ở entity hoặc collection để đồng bộ.
3. **Các hành động ghi chờ flush**: insert, update, delete và thay đổi association.
4. **Proxy và persistent collection**: hỗ trợ lazy loading khi session còn hoạt động và kết nối phù hợp.
5. **Liên hệ với transaction/JDBC coordinator**: thực thi SQL, nhận exception và điều phối tài nguyên.

Nếu session vẫn mở quá lâu, những đối tượng managed/snapshot và các tài nguyên liên quan có thể tích lũy. Nếu session bị đóng quá sớm, lazy loading hoặc thay đổi managed state ở bước tiếp theo có thể không thực hiện được. Vì vậy, **ranh giới một đơn vị công việc** quan trọng hơn việc cố giữ session mở ở mọi nơi.

## 2. Mẫu cơ bản: open → begin → work → commit hoặc rollback → close

Trong ứng dụng Java tự quản lý session và transaction, mẫu nên bắt đầu từ `try-with-resources`:

~~~java
import org.hibernate.Session;
import org.hibernate.SessionFactory;
import org.hibernate.Transaction;

public class CustomerService {
    private final SessionFactory sessionFactory;

    public CustomerService(SessionFactory sessionFactory) {
        this.sessionFactory = sessionFactory;
    }

    public Long createCustomer(String email) {
        try (Session session = sessionFactory.openSession()) {
            Transaction tx = session.beginTransaction();
            try {
                Customer customer = new Customer(email);
                session.persist(customer);

                tx.commit();
                return customer.getId();
            } catch (RuntimeException failure) {
                rollbackIfPossible(tx, failure);
                throw failure;
            }
        }
    }

    private static void rollbackIfPossible(
            Transaction tx, RuntimeException originalFailure) {
        if (tx == null || !tx.isActive()) {
            return;
        }
        try {
            tx.rollback();
        } catch (RuntimeException rollbackFailure) {
            originalFailure.addSuppressed(rollbackFailure);
        }
    }
}
~~~

Ở đây, `Customer` là một `@Entity` hợp lệ với constructor và identifier được cấu hình. Ví dụ tập trung vào quản lý tài nguyên, không phụ thuộc chi tiết của entity.

**Cách đọc mã:**

1. `sessionFactory.openSession()` trả về một session mới và bắt đầu một persistence context mới cho nghiệp vụ.
2. `session.beginTransaction()` mở ranh giới transaction theo cấu hình môi trường.
3. `session.persist(customer)` làm đối tượng trở thành managed; SQL `INSERT` có thể chạy khi flush/commit, hoặc sớm hơn nếu cách sinh ID yêu cầu.
4. `tx.commit()` yêu cầu transaction hoàn tất. Bình thường Hibernate flush các thay đổi cần thiết trước commit.
5. Nếu thao tác nghiệp vụ hay commit ném `RuntimeException`, khối `catch` thử rollback nếu transaction còn active, sau đó **ném lại lỗi ban đầu**.
6. `try-with-resources` gọi `session.close()` sau khi rời khối, bất kể commit thành công, rollback thành công hay có ngoại lệ.

Hàm `rollbackIfPossible` giữ lại lỗi gốc khi rollback cũng thất bại bằng cách thêm lỗi rollback dưới dạng `suppressed exception`. Kiểm tra `tx.isActive()` là guard phổ biến, nhưng trạng thái transaction sau một lỗi commit có thể đã kết thúc hoặc không còn rollback được; trong các trường hợp đó vẫn phải đóng session và để tầng trên xử lý thất bại. Không giả định rollback luôn thành công hoặc tự “sửa” mọi trạng thái DB không chắc chắn.

Ví dụ này xử lý các lỗi ORM/DB thông thường thuộc `RuntimeException`. Với lỗi nghiêm trọng ở mức JVM như `OutOfMemoryError`, `try-with-resources` vẫn là lớp bảo vệ tài nguyên tại ranh giới Java khi stack có thể unwind; ứng dụng không nên kỳ vọng tiếp tục xử lý nghiệp vụ bình thường sau những lỗi kiểu đó.

### Vì sao không chỉ viết `session.close()` ở dòng cuối?

Mã sau có lỗ hổng:

~~~java
Session session = sessionFactory.openSession();
Transaction tx = session.beginTransaction();
session.persist(customer);
tx.commit();
session.close(); // không chạy nếu persist() hoặc commit() ném exception
~~~

Nếu lỗi xảy ra trước dòng cuối, code nhảy ra khỏi phương thức và bỏ qua `close()`. Nếu transaction đang active mà không rollback đúng cách, tài nguyên và trạng thái transaction có thể bị giữ lâu hơn dự kiến. Đặt `close()` trong `finally` cũng xử lý được, nhưng với `Session` (đóng được theo `AutoCloseable`), `try-with-resources` viết gọn và xử lý suppressed exceptions tự nhiên hơn.

## 3. Ba vòng đời phải được kết thúc đúng cách

Một request có thể kết thúc theo ba cách khác nhau:

| Tình huống | Transaction | Session | Kết quả |
|---|---|---|---|
| Nghiệp vụ và commit thành công | `commit()` hoàn tất | Đóng sau commit | Thay đổi đã được xác nhận theo bảo đảm của DB. |
| Lỗi trước commit | Rollback nếu có thể | Đóng sau rollback/đường xử lý lỗi | Các thay đổi trong transaction bị hủy khi rollback thành công. |
| Lỗi trong commit | Thử rollback nếu còn hợp lệ; phải xét trạng thái chưa rõ | Luôn đóng | Không được mặc định giao dịch thành công hoặc mặc định chắc chắn rollback; có thể cần xác minh kết quả. |

**Session close không thay thế transaction rollback.** Đừng dựa vào việc đóng session để định nghĩa kết quả khi transaction đang mở. Đóng tài nguyên và kết thúc giao dịch là hai trách nhiệm khác nhau.

**Flush không thay thế transaction commit.** `session.flush()` gửi SQL pending xuống database nhưng các thay đổi vẫn nằm trong transaction, có thể rollback.

**Commit không thay thế session close.** Dù DB đã xác nhận transaction, persistence context và các tài nguyên mà session quản lý vẫn cần được kết thúc khi đơn vị công việc xong.

### Nhìn qua một trục thời gian

~~~mermaid
sequenceDiagram
    participant A as Application
    participant SF as SessionFactory
    participant S as Session
    participant DB as Database

    A->>SF: openSession()
    SF-->>A: Session
    A->>S: beginTransaction()
    A->>S: persist / query / modify
    Note over S: Managed entities, dirty state
    A->>S: commit()
    S->>DB: flush SQL nếu còn thao tác chờ
    DB-->>S: Thực thi SQL
    S->>DB: commit transaction
    DB-->>S: commit completed
    S-->>A: Thành công
    A->>S: close() qua try-with-resources
~~~

Ở nhánh thất bại, ứng dụng xử lý exception, rollback nếu transaction còn có thể rollback, sau đó đóng session; nếu rollback không thành công, ứng dụng phải bảo toàn thông tin lỗi để tầng gọi quyết định xử lý.

## 4. Điều gì xảy ra khi giao dịch thành công?

Xem ví dụ cập nhật tài khoản:

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        Account account = session.find(Account.class, accountId);
        if (account == null) {
            throw new IllegalArgumentException("Account not found");
        }

        account.setDisplayName("New name"); // managed entity bị thay đổi

        tx.commit(); // Hibernate có thể flush UPDATE trước commit
    } catch (RuntimeException failure) {
        rollbackIfPossible(tx, failure);
        throw failure;
    }
}
~~~

Các thời điểm chính:

- **Lúc `find()`:** Hibernate tìm trong persistence context, sau đó có thể chạy `SELECT` để nạp entity.
- **Lúc gọi setter:** Java object thay đổi; entity đang managed nên Hibernate theo dõi thay đổi. Không cần gọi một `update()` độc lập.
- **Lúc flush (thường trước commit):** Hibernate dirty checking và thực thi SQL `UPDATE` qua JDBC nếu cần.
- **Lúc commit thành công:** database xác nhận transaction.
- **Lúc close:** session và first-level cache của nó kết thúc; object Java mà code còn giữ trở thành detached đối với session này.

Nếu sau `close()` ứng dụng sửa `account.setDisplayName(...)` lần nữa, thay đổi đó **không tự động được lưu** vì đối tượng không còn thuộc persistence context đang hoạt động. Muốn thực hiện nghiệp vụ mới, cần một session/transaction phù hợp và thao tác attach/merge hoặc tải lại entity theo cách thiết kế.

### Có nhất thiết phải gọi `flush()` trước `commit()`?

Với transaction bình thường và flush mode mặc định, không cần gọi `flush()` chỉ để được insert/update/delete trước khi commit; Hibernate sẽ đồng bộ khi cần. Có thể gọi tường minh để:

- nhận lỗi constraint sớm hơn trong luồng nghiệp vụ;
- bảo đảm một nhóm SQL được gửi trước nhóm thao tác kế tiếp;
- kiểm soát kích thước persistence context khi xử lý batch kết hợp `flush()` và `clear()`.

Tuy nhiên, một lần `flush()` có thể gây nhiều SQL và chưa xác nhận transaction. Dùng quá nhiều flush tường minh làm giảm khả năng gom JDBC batch và có thể tăng round trip. Với các chế độ flush đặc biệt như `MANUAL`, ứng dụng phải hiểu rõ cam kết đồng bộ riêng của chế độ đó.

## 5. Điều gì xảy ra khi giao dịch thất bại?

Lỗi có thể xuất hiện ở những điểm khác nhau:

1. Lỗi kiểm tra nghiệp vụ, chẳng hạn dữ liệu đầu vào không hợp lệ.
2. Lỗi lúc load/query, chẳng hạn SQL syntax, timeout hoặc kết nối có vấn đề.
3. Lỗi khi `persist()`/`remove()` hoặc cascade xử lý state.
4. Lỗi khi flush, ví dụ foreign key, unique, not-null constraint, optimistic locking hoặc JDBC exception.
5. Lỗi khi commit, ví dụ database trả về lỗi constraint trì hoãn đến commit, deadlock, network error hoặc transaction manager không commit được.
6. Lỗi khi rollback/close; đây là lỗi dọn dẹp, có thể xảy ra sau lỗi chính.

Với transaction đang hoạt động, cách xử lý chủ đạo là **rollback rồi kết thúc session**. Đừng coi việc đã bắt được exception là có thể tiếp tục dùng chính session đó. Một lỗi JDBC/ORM có thể khiến trạng thái action queue, persistence context, transaction hoặc connection không còn phù hợp để tiếp tục làm việc.

~~~mermaid
flowchart TD
    A["Bắt đầu đơn vị công việc"] --> B["Mở Session và Transaction"]
    B --> C["Thực hiện thao tác Hibernate"]
    C --> D{"Lỗi trước commit?"}
    D -- "Có" --> R["Thử rollback nếu còn hợp lệ"]
    D -- "Không" --> E["Thử commit"]
    E --> F{"Commit thành công?"}
    F -- "Không" --> R
    F -- "Có" --> S["Kết quả thành công"]
    R --> L["Ghi nhận/ném tiếp lỗi gốc"]
    S --> Z["Đóng Session"]
    L --> Z
    Z --> X["Kết thúc"]
~~~

### 5.1. Lỗi nghiệp vụ trước khi Hibernate gửi SQL

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        Account account = session.find(Account.class, accountId);

        if (account.getBalance().signum() < 0) {
            throw new IllegalStateException("Balance is invalid");
        }

        account.setDisplayName("Validated");
        tx.commit();
    } catch (RuntimeException failure) {
        rollbackIfPossible(tx, failure);
        throw failure;
    }
}
~~~

Ngay cả khi code chưa thấy `UPDATE` trong log, rollback vẫn có ý nghĩa: nó đóng ranh giới transaction theo cách có chủ đích và ngăn những thay đổi trong transaction được vô tình xác nhận ở bước sau. Trong hệ thống thực tế, nên kiểm tra `account == null` trước khi truy cập thuộc tính.

### 5.2. Lỗi ràng buộc khi flush

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        session.persist(new Customer("taken@example.com"));
        session.flush(); // có thể ném lỗi unique constraint

        tx.commit();
    } catch (RuntimeException failure) {
        rollbackIfPossible(tx, failure);
        throw failure;
    }
}
~~~

Giả sử `email` có unique constraint và giá trị đã tồn tại, database có thể từ chối `INSERT` ở flush. Hibernate thường ném một exception dạng `ConstraintViolationException` (Hibernate) được bọc vào hoặc biểu hiện dưới một exception ORM/JPA tùy ngữ cảnh. Đây là lỗi của transaction hiện tại: rollback, đóng session và trả thông báo nghiệp vụ phù hợp ở tầng xử lý ngoài là đường đi an toàn.

Không nên làm thế này:

~~~java
try {
    session.flush();
} catch (RuntimeException e) {
    // Sai hướng: bỏ qua lỗi DB rồi sử dụng tiếp cùng transaction/session.
    session.persist(anotherCustomer);
    tx.commit();
}
~~~

Sau lỗi flush, điều kiện transaction và trạng thái session có thể không còn nhất quán. Nếu muốn thử lại, hãy kết thúc transaction lỗi và bắt đầu một transaction mới trong session mới, kèm xử lý nguyên nhân lỗi.

### 5.3. Lỗi xảy ra ở `commit()`

Một số database hỗ trợ constraint kiểm tra tại thời điểm commit; ngoài ra lỗi kết nối hoặc transaction manager có thể xảy ra ngay khi yêu cầu commit. Khi `tx.commit()` ném exception, kết quả transaction **không phải lúc nào cũng có thể xác định chỉ từ phía client**: database có thể đã commit nhưng client không nhận được phản hồi.

Vì vậy:

- Thử rollback chỉ khi transaction manager còn cho phép; rollback thất bại cần được ghi nhận.
- Luôn đóng session đã tham gia transaction lỗi.
- Không retry mù quáng toàn bộ nghiệp vụ có thể tạo dữ liệu lặp (thanh toán, đặt hàng, gửi thông báo, tạo bản ghi mang tính duy nhất).
- Với nghiệp vụ cần retry, thiết kế **idempotency key**, ràng buộc unique phù hợp hoặc bước kiểm tra kết quả trong transaction/connection mới.

Trong các hệ thống có message broker hoặc gọi dịch vụ bên ngoài, database rollback không tự động thu hồi email, HTTP request hay message đã gửi. Những side effect đó cần xử lý bằng cơ chế nghiệp vụ như outbox hoặc idempotent consumer.

### 5.4. Nếu rollback cũng thất bại

Mẫu `rollbackIfPossible(tx, failure)` thêm rollback exception vào `failure.getSuppressed()`. Điều này bảo vệ nguyên nhân gốc, đồng thời vẫn lưu lỗi dọn dẹp để log/monitoring điều tra.

Không nên để exception rollback che khuất exception đầu tiên, ví dụ:

~~~java
catch (RuntimeException original) {
    tx.rollback();  // nếu rollback lại ném exception, original bị mất
    throw original;
}
~~~

Với `try-with-resources`, nếu khối try đã ném lỗi mà `session.close()` cũng ném lỗi, Java tự đưa lỗi close vào danh sách suppressed của lỗi ban đầu. Đây là một ưu điểm rõ rệt so với tự đóng tài nguyên trong `finally` mà không xử lý exception đúng cách.

## 6. Phân biệt `close()`, `clear()`, `flush()` và `disconnect()`

Những API liên quan trạng thái/tài nguyên có tên dễ gây nhầm:

| API | Tác động chính | Không có nghĩa là |
|---|---|---|
| `session.flush()` | Đồng bộ các thay đổi pending thành thao tác SQL trong transaction. | Không phải commit hay đóng session. |
| `session.clear()` | Xóa các entity/collection đang được quản lý khỏi persistence context; object trở thành detached. | Không commit, không tự đóng session; nếu làm trước flush có thể bỏ những thay đổi pending. |
| `session.detach(entity)` | Tách một entity cụ thể khỏi context. | Không kết thúc transaction/session. |
| `session.close()` | Kết thúc session và giải phóng tài nguyên thuộc session. | Không phải cơ chế thay thế rollback hoặc cam kết lưu dữ liệu. |
| `session.disconnect()` / `reconnect()` (API/khả năng tùy phiên bản) | Điều khiển liên kết JDBC trong các trường hợp đặc biệt. | Không phải mẫu thay thế thông thường cho close/reopen session. |

Ví dụ:

~~~java
session.persist(order);
session.flush(); // SQL có thể đã chạy nhưng transaction còn active
session.clear(); // các đối tượng managed được tách khỏi context
tx.commit();     // xác nhận những SQL đã thực thi
// try-with-resources tiếp tục đóng session
~~~

Nếu gọi `clear()` **trước khi flush** khi có thay đổi chưa đồng bộ, có thể làm mất cơ hội Hibernate ghi những thay đổi đó. Dùng `flush()`/`clear()` theo batch cần được thiết kế cùng transaction và quan hệ entity, tránh tách object mà các bước sau vẫn cần lazy-load hoặc dirty-check.

## 7. Session đóng rồi thì object và lazy loading ra sao?

Một entity được truy xuất trong session vẫn là object Java sau khi session đóng, nhưng không còn được quản lý bởi persistence context đó. Với thuộc tính đã tải đầy đủ, có thể đọc dữ liệu đang có trong object; với proxy/collection lazy chưa khởi tạo, truy cập sau khi session đóng thường dẫn đến lỗi `LazyInitializationException`.

~~~java
Order order;
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        order = session.find(Order.class, orderId);
        tx.commit();
    } catch (RuntimeException failure) {
        rollbackIfPossible(tx, failure);
        throw failure;
    }
}

// Session đã đóng:
String code = order.getCode(); // được nếu thuộc tính đã tải
int count = order.getLines().size(); // có thể LazyInitializationException
~~~

Các giải pháp có chủ đích:

1. **Truy cập dữ liệu cần thiết khi session/transaction còn mở**, rồi chuyển thành DTO trước khi return.
2. **Fetch join** hoặc `EntityGraph` ở query cần thiết để tải association dự định sử dụng; kiểm soát tránh Cartesian product hoặc tải quá nhiều quan hệ.
3. Viết **query projection** lấy trực tiếp những trường cần trả cho API.
4. Nếu nghiệp vụ cần thêm dữ liệu ở bước khác, mở transaction/session mới và query lại theo ID.

Ví dụ DTO trả ra ngoài ranh giới session:

~~~java
public OrderView getOrderView(long orderId) {
    try (Session session = sessionFactory.openSession()) {
        Transaction tx = session.beginTransaction();
        try {
            Order order = session.createSelectionQuery(
                "select distinct o from Order o " +
                "left join fetch o.lines where o.id = :id", Order.class
            ).setParameter("id", orderId)
             .getSingleResult();

            OrderView view = new OrderView(
                order.getId(),
                order.getCode(),
                order.getLines().stream()
                    .map(line -> new OrderLineView(line.getSku(), line.getQuantity()))
                    .toList()
            );
            tx.commit();
            return view;
        } catch (RuntimeException failure) {
            rollbackIfPossible(tx, failure);
            throw failure;
        }
    }
}

public record OrderLineView(String sku, int quantity) {}
public record OrderView(Long id, String code, List<OrderLineView> lines) {}
~~~

Đây là ví dụ mô tả; giả định các entity `Order`, `OrderLine` và getter tương ứng đã được định nghĩa, chương trình dùng Java 17+. Việc materialize DTO khi context còn mở làm rõ dữ liệu API cần và tránh dựa vào session tồn tại xuyên qua tầng web.

### Vì sao không giữ Session mở đến lúc JSON serialize xong?

Trong web app, cách để session mở xuyên suốt view/render có thể giúp lazy loading “tình cờ hoạt động” nhưng dễ dẫn đến N+1 query, truy vấn phát sinh ngoài service transaction, và việc sử dụng connection không được dự đoán rõ. Kỹ thuật **Open Session in View (OSIV)** có thể được framework hỗ trợ; nên hiểu trade-off và quyết định theo kiến trúc. Ranh giới service transaction cùng DTO/projection thường giúp kiểm soát SQL dễ hơn.

## 8. Kết thúc transaction cho tác vụ chỉ đọc

Đọc dữ liệu cũng có thể dùng transaction để nhận ngữ nghĩa isolation nhất quán theo database. Đừng suy ra rằng vì không có `INSERT`/`UPDATE` thì không cần quan tâm tài nguyên session hoặc transaction.

~~~java
public CustomerView loadCustomer(Long id) {
    try (Session session = sessionFactory.openSession()) {
        Transaction tx = session.beginTransaction();
        try {
            Customer customer = session.find(Customer.class, id);
            if (customer == null) {
                tx.commit();
                return null;
            }

            CustomerView view =
                new CustomerView(customer.getId(), customer.getEmail());
            tx.commit();
            return view;
        } catch (RuntimeException failure) {
            rollbackIfPossible(tx, failure);
            throw failure;
        }
    }
}

public record CustomerView(Long id, String email) {}
~~~

Một số môi trường có read-only transaction, transaction manager riêng, connection auto-commit hoặc chính sách release khác nhau. Dù transaction chỉ đọc, session vẫn nên được đóng đúng lúc. Nếu framework cung cấp `@Transactional(readOnly = true)`, đó là một *gợi ý/chính sách do framework xử lý* và các tối ưu tùy provider; không nên coi nó là cơ chế bảo vệ chắc chắn chống mọi SQL ghi trên mọi DB.

## 9. Ai sở hữu Session? Application-managed và framework-managed

Mẫu `openSession()` / `close()` đúng khi **code của bạn sở hữu vòng đời**. Nhưng nhiều hệ thống đã có transaction manager để cung cấp session và ràng buộc với transaction hiện tại.

### 9.1. Hibernate thuần: ứng dụng sở hữu

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        // Làm việc với session
        tx.commit();
    } catch (RuntimeException failure) {
        rollbackIfPossible(tx, failure);
        throw failure;
    }
}
~~~

Tầng code này quyết định khi nào mở, commit/rollback và đóng. Mỗi đơn vị công việc độc lập thường lấy session mới. Không nên lưu `Session` vào static field hoặc chia sẻ session giữa request.

### 9.2. `getCurrentSession()`: session theo context

`sessionFactory.getCurrentSession()` trả về session gắn với *current session context* nếu ứng dụng đã cấu hình cơ chế đó (ví dụ tích hợp JTA hoặc context framework). Cách session được bind/unbind, mở/đóng và gắn transaction **phụ thuộc context implementation**. Không được mặc định `getCurrentSession()` giống hệt `openSession()` hoặc luôn được tạo sẵn.

~~~java
// Chỉ là minh họa khi current-session context đã được cấu hình.
Session session = sessionFactory.getCurrentSession();
Customer customer = session.find(Customer.class, id);
// Bên quản lý context/transaction chịu trách nhiệm kết thúc session.
~~~

Nếu Hibernate được tích hợp với transaction manager, tự đóng session thuộc context có thể phá hỏng phần còn lại của nghiệp vụ. Phải xác định rõ **bên nào tạo và sở hữu session** rồi mới quyết định có gọi `close()` hay không.

### 9.3. Spring: framework thường sở hữu Session và transaction

Trong ứng dụng Spring có `@Transactional` và `EntityManager` do Spring cung cấp, cách dùng điển hình:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SpringCustomerService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public Long createCustomer(String email) {
        Customer customer = new Customer(email);
        entityManager.persist(customer);
        return customer.getId();
    }
}
~~~

Spring transaction interceptor thường mở/bind transaction và persistence context thích hợp, commit khi method được thực thi thành công hoặc rollback theo chính sách khi exception xảy ra. Application code **không gọi** `entityManager.close()` trên shared transaction-scoped persistence context, cũng không tự `beginTransaction()`/`commit()` bên trong method đã được framework quản lý.

Các lưu ý quan trọng:

- Với Spring mặc định, unchecked exception (`RuntimeException` và `Error`) thường kích hoạt rollback; checked exception cần cấu hình phù hợp, ví dụ `@Transactional(rollbackFor = Exception.class)` nếu mong muốn.
- Proxy-based `@Transactional` có giới hạn về self-invocation: gọi một method annotated từ method khác trên cùng bean có thể không đi qua transaction proxy.
- Bắt exception và không ném lại có thể khiến transaction interceptor tưởng method thành công, trừ khi transaction đã được đánh dấu rollback-only.
- Thời điểm khởi tạo/đóng persistence context còn phụ thuộc Spring configuration (bao gồm OSIV). Không áp dụng máy móc cách mở/đóng thủ công của Hibernate thuần vào Spring-managed transaction.

### 9.4. Jakarta EE/JTA: container sở hữu transaction

Trong môi trường transaction container-managed, `EntityManager` được inject có thể được gắn với JTA transaction; application thường điều khiển nghiệp vụ qua boundary/container annotation thay vì tự gọi `getTransaction()` trên transaction-scoped `EntityManager`. Khi muốn dùng Hibernate-specific API, có thể `unwrap(Session.class)` trong phạm vi phù hợp, nhưng ownership vẫn thuộc container.

| Bối cảnh | Lấy Session/EntityManager | Ai kết thúc transaction? | Ai đóng resource? |
|---|---|---|---|
| Hibernate thuần, application-managed | `openSession()` | Ứng dụng với `Transaction` | Ứng dụng với `try-with-resources`. |
| `getCurrentSession()` có context | `getCurrentSession()` | Tùy transaction manager/context | Chủ sở hữu current-session context. |
| Spring `@Transactional` | Inject `EntityManager` hoặc repository | Spring transaction manager | Spring / persistence context lifecycle. |
| Jakarta EE container-managed | Inject `EntityManager` | JTA/container | Container. |

## 10. Một request, nhiều thao tác: quyết định phạm vi Session và transaction

Giả sử nghiệp vụ “tạo đơn hàng và trừ tồn kho” gồm đọc sản phẩm, tạo order, tạo order lines, trừ số lượng tồn. Nếu tất cả cần **cùng thành công hoặc cùng thất bại**, hãy thực hiện trong một transaction nghiệp vụ:

~~~java
public Long placeOrder(long productId, int quantity) {
    try (Session session = sessionFactory.openSession()) {
        Transaction tx = session.beginTransaction();
        try {
            Product product = session.find(Product.class, productId);
            if (product == null) {
                throw new IllegalArgumentException("Product not found");
            }
            if (quantity <= 0 || product.getStock() < quantity) {
                throw new IllegalStateException("Insufficient stock");
            }

            product.setStock(product.getStock() - quantity);
            PurchaseOrder order = new PurchaseOrder(product, quantity);
            session.persist(order);

            tx.commit();
            return order.getId();
        } catch (RuntimeException failure) {
            rollbackIfPossible(tx, failure);
            throw failure;
        }
    }
}
~~~

Ví dụ giả định entity và mapping đã tồn tại. Để tránh overselling khi nhiều request đồng thời, nghiệp vụ thật còn cần thiết kế **concurrency control**, chẳng hạn `@Version` optimistic locking hoặc lock/atomic update thích hợp; chỉ có một transaction không tự bảo đảm điều kiện kiểm tra số lượng trước đó là an toàn trước cạnh tranh.

Nếu thay vì một transaction bạn mở hai session và commit trừ kho trước khi lưu order, sau đó phần lưu order lỗi, database có thể rơi vào trạng thái trừ kho nhưng không có order. Mỗi transaction riêng không tự liên kết rollback. Do đó xác định **đơn vị công việc nguyên tử** trước rồi mới đặt ranh giới session/transaction.

### Session-per-operation, session-per-request và session-per-conversation

| Kiểu phạm vi | Khi phù hợp | Rủi ro cần quản lý |
|---|---|---|
| Session-per-operation nhỏ | Job/script độc lập với thao tác ngắn, không cần atomicity qua nhiều thao tác. | Không có atomicity nếu nghiệp vụ thực tế trải qua nhiều operation được commit riêng. |
| Session-per-service-transaction | Nhiều thao tác DB của một nghiệp vụ được gom trong transaction rõ ràng. | Phải chuẩn bị dữ liệu trả ra trước khi context đóng, xử lý lazy đúng cách. |
| Session-per-request | Có thể thuận tiện nếu mỗi HTTP request trùng một transaction/đơn vị công việc. | Request có thể gồm gọi dịch vụ ngoài, chờ I/O, render view; giữ transaction/session quá dài. |
| Long conversation / extended context | Một số quy trình stateful phức tạp có thiết kế riêng. | First-level cache phình to, stale state, concurrency, session không thread-safe; cần quản lý reconnect/merge/version chặt chẽ. |

Quy tắc thực dụng: một session nên phục vụ **một đơn vị công việc có ranh giới rõ** và sống ngắn; thời gian mở transaction nên ngắn nhất có thể mà vẫn bảo đảm tính nguyên tử.

## 11. Lưu ý connection pool và release tài nguyên

Nhiều ứng dụng Hibernate dùng DataSource/connection pool như HikariCP. Trong tình huống ấy:

~~~text
Application
    -> SessionFactory
         -> Session (persistence context)
              -> khi cần SQL: mượn JDBC Connection từ pool
              -> PreparedStatement / ResultSet / SQL
              -> cuối giai đoạn thích hợp: trả connection cho pool
    -> close Session
~~~

“Trả connection cho pool” không có nghĩa đóng TCP connection vật lý mỗi lần. Pool quản lý connection và quyết định giữ hay tái tạo connection. Đóng session đúng lúc góp phần trả những tài nguyên session còn nắm giữ, nhưng thời điểm thực tế trả JDBC connection còn tùy connection handling mode, JTA và transaction boundary.

Không nên tự gọi `connection.close()` lên connection do Hibernate/session đang quản lý, trừ khi API/contract được dùng cho phép và code hiểu chính xác quyền sở hữu. Nếu cần chạy JDBC trực tiếp trong transaction Hibernate, cân nhắc:

~~~java
session.doWork(connection -> {
    try (PreparedStatement ps = connection.prepareStatement(
            "update audit_counter set total = total + 1 where id = ?")) {
        ps.setLong(1, 1L);
        ps.executeUpdate();
    }
});
~~~

Trong callback `doWork`, ứng dụng sở hữu `PreparedStatement` do mình tạo và phải đóng nó; JDBC `Connection` được Hibernate cung cấp vẫn do Hibernate/transaction infrastructure quản lý. Mã SQL thẳng này được gửi ngay khi chạy callback; nó không phải là một entity action trong persistence context và có thể yêu cầu cân nhắc flush để tránh thứ tự/thông tin stale khi kết hợp ORM DML và JDBC DML.

### Rò rỉ tài nguyên biểu hiện thế nào?

Một session/transaction không được kết thúc có thể khiến:

- connection pool hết connection cho request mới, gây timeout khi chờ borrow;
- transaction giữ lock hoặc snapshot lâu hơn dự kiến, ảnh hưởng concurrency và VACUUM/undo tùy DB;
- persistence context giữ nhiều entity, snapshot và collection, tăng bộ nhớ;
- application tiếp tục thực thi với entity state cũ, gây sai lệch khi các transaction khác đã thay đổi dữ liệu.

Không phải mọi tình trạng “connection leak” đều bắt nguồn từ session chưa đóng. Cần dùng pool metrics, log transaction, thread dump và query DB để xác định đúng nguyên nhân trước khi sửa.

## 12. Những lỗi triển khai thường gặp

### 12.1. Dùng một Session làm singleton

~~~java
// Sai: nhiều request/thread cùng dùng một Session.
class SharedRepository {
    private final Session session;
    SharedRepository(SessionFactory factory) {
        this.session = factory.openSession();
    }
}
~~~

Vì session không thread-safe và giữ một persistence context, concurrent calls có thể trộn trạng thái và transaction. Giữ singleton `SessionFactory` hoặc pool/repository component, nhưng lấy session theo transaction/đơn vị công việc.

### 12.2. Quên rollback khi thao tác lỗi

~~~java
try (Session session = factory.openSession()) {
    Transaction tx = session.beginTransaction();
    session.persist(customer);
    tx.commit(); // nếu ném exception, try-with-resources đóng Session...
}
// ...nhưng không có nhánh rollback tường minh.
~~~

Mẫu trên có lợi ở chỗ session vẫn được đóng, nhưng không đủ chủ động xử lý transaction đang active hoặc thông tin failure. Nên có `catch` rollback-if-possible, log/throw lỗi gốc và kết thúc session.

### 12.3. Nuốt exception rồi commit

~~~java
Transaction tx = session.beginTransaction();
try {
    doBusinessWork(session);
} catch (RuntimeException e) {
    logger.warn("Problem", e); // lỗi được nuốt
}
tx.commit(); // có thể commit trạng thái dang dở
~~~

Nếu nghiệp vụ không được phép thành công một phần, cần rollback và ném lỗi hoặc trả kết quả thất bại rõ ràng. Việc bỏ qua exception không làm transaction tự rollback trong mô hình application-managed.

### 12.4. Quên đóng session khi trả về sớm

~~~java
Session session = factory.openSession();
if (session.find(Customer.class, id) == null) {
    return null; // session không đóng
}
session.close();
~~~

Dùng `try-with-resources` cho mọi nhánh return; trong khối có transaction thì commit/rollback theo kết quả trước khi thoát khối.

### 12.5. Dùng session sau khi close

~~~java
Session session = factory.openSession();
session.close();
session.find(Customer.class, 1L); // không hợp lệ
~~~

Session đã đóng không được dùng lại. Mở session mới qua factory; đừng cố “khởi động lại” một session đóng bằng `beginTransaction()`.

### 12.6. Phụ thuộc lazy loading sau khi service trả về

~~~java
// Service return Order entity nhưng Session đã đóng.
return order;
// JSON serializer bên ngoài truy cập order.getLines(), có thể lỗi.
~~~

Chuẩn bị dữ liệu cần thiết trong transaction và trả DTO hoặc query projection. Không dùng việc giữ session mở toàn HTTP request như cách chữa mặc định cho thiết kế fetch chưa rõ.

### 12.7. Gọi `session.clear()` rồi nghĩ rằng đã commit

`clear()` chủ yếu thay đổi persistence context. Dữ liệu đã flush nhưng chưa commit vẫn có thể rollback; dữ liệu pending chưa flush có thể bị loại bỏ khi clear. Phải phân biệt đơn vị quản lý entity trong RAM với đơn vị giao dịch trong DB.

### 12.8. Đóng `SessionFactory` sau mỗi method

~~~java
try (SessionFactory factory = buildFactory()) {
    try (Session session = factory.openSession()) {
        // ...
    }
}
~~~

Đoạn mã có thể phù hợp một chương trình console chạy đúng một lần, nhưng rất tốn kém nếu lặp trong request. Trong backend, factory nên được tạo khi startup và đóng ở shutdown theo cơ chế quản lý dependency injection/lifecycle phù hợp.

## 13. Điều gì cần xảy ra khi có nhiều session trong một nghiệp vụ?

Hai session cùng truy cập một entity với cùng ID vẫn có **hai persistence context độc lập**. Nếu session A sửa object trong bộ nhớ, session B không tự thấy object Java của session A thay đổi. DB isolation, flush/commit, second-level cache và optimistic/pessimistic locking quyết định khả năng nhìn thấy dữ liệu đã ghi.

~~~java
try (Session first = sessionFactory.openSession();
     Session second = sessionFactory.openSession()) {
    Customer a = first.find(Customer.class, customerId);
    Customer b = second.find(Customer.class, customerId);
    // Cùng một database row, nhưng thông thường a != b.
}
~~~

Ví dụ chỉ làm rõ identity trong từng context; code thật nên dùng transaction phù hợp khi thực hiện query. Không được xem việc mở hai session là “hai bước trong cùng transaction” trừ khi transaction manager đã liên kết chúng theo một cấu hình cụ thể. Với business operation cần atomicity, một session/transaction nhất quán thường dễ kiểm soát hơn.

### Session có được truyền qua luồng khác không?

Không dùng chung một `Session` giữa threads. Một session có thể mang state của giao dịch và persistent collection, không an toàn cho concurrent access. Khi xử lý async/job:

- Truyền ID hoặc DTO immutable qua queue/thread boundary.
- Tạo transaction và session thích hợp trong worker thread.
- Load lại entity cần thiết trong session của worker.

Không truyền entity đang managed ở thread A rồi giả định nó vẫn được Hibernate theo dõi đúng trong session của thread B. Entity có thể là Java object hợp lệ nhưng context và lazy loading thuộc phạm vi khác.

## 14. Mẫu tiện ích gói transaction và giới hạn của nó

Khi code nhiều service Hibernate thuần, dễ lặp lại cấu trúc try/commit/rollback/close. Có thể gói thành một helper nhỏ để giảm nguy cơ quên cleanup:

~~~java
import java.util.function.Function;
import org.hibernate.Session;
import org.hibernate.SessionFactory;
import org.hibernate.Transaction;

public final class HibernateUnitOfWork {
    private final SessionFactory sessionFactory;

    public HibernateUnitOfWork(SessionFactory sessionFactory) {
        this.sessionFactory = sessionFactory;
    }

    public <T> T inTransaction(Function<Session, T> work) {
        try (Session session = sessionFactory.openSession()) {
            Transaction tx = session.beginTransaction();
            try {
                T result = work.apply(session);
                tx.commit();
                return result;
            } catch (RuntimeException failure) {
                if (tx.isActive()) {
                    try {
                        tx.rollback();
                    } catch (RuntimeException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }
                throw failure;
            }
        }
    }
}
~~~

Sử dụng:

~~~java
Long id = unitOfWork.inTransaction(session -> {
    Customer customer = new Customer("sample@example.com");
    session.persist(customer);
    return customer.getId();
});
~~~

Helper định nghĩa một ranh giới session/transaction mới cho mỗi lời gọi. Nó phù hợp thao tác **độc lập**, nhưng không tự hỗ trợ transaction propagation, rollback rule cho checked exception, nested transactions, JTA, timeout, transaction synchronization hoặc distributed tracing như transaction manager trưởng thành. Nếu ứng dụng đã dùng Spring/Jakarta EE, ưu tiên cơ chế transaction của framework. Hibernate phiên bản mới còn có API tiện ích transaction tại `SessionFactory` tùy phiên bản; cần đối chiếu API đang dùng trước khi tự tạo abstraction.

### Có nên retry ngay trong helper?

Không nên tự động retry trong cùng `Session` sau lỗi SQL. Nếu cần retry do deadlock hoặc optimistic locking, mỗi lần thử phải có transaction/session mới, và việc retry chỉ phù hợp với operation được thiết kế idempotent hoặc có chính sách khôi phục rõ ràng. Với commit outcome uncertain, cũng không thể giả định chắc chắn lần trước rollback.

## 15. Theo dõi tài nguyên và lỗi trong thực tế

Khi gỡ lỗi vòng đời session, log nên giúp trả lời:

| Câu hỏi | Nơi kiểm tra |
|---|---|
| Request/job đã mở bao nhiêu session? | Metrics Hibernate hoặc instrumentation ở lớp application/repository. |
| Transaction nào đã commit, rollback hoặc timeout? | Transaction manager log, tracing và database monitoring. |
| Session có giữ quá nhiều entity? | Hibernate statistics, heap profiling, scope của persistence context. |
| Connection pool có bị cạn? | Pool active/idle/pending/timeout metrics, stack traces nơi borrow connection. |
| SQL có chạy trước khi exception xuất hiện không? | Log `org.hibernate.SQL`, bind log và trace theo transaction/request. |
| Lỗi xuất hiện lúc flush hay lúc commit? | Stack trace, logging transaction và các constraint của DB. |
| Có lazy loading ngoài ranh giới session? | `LazyInitializationException` stack trace, mapping fetch và tầng serialize. |

Với Hibernate 6, các logger thường gặp:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Đây là ví dụ cú pháp Spring Boot `application.properties`; cấu hình logger cụ thể tùy framework và phiên bản Hibernate. Log bind parameters có thể chứa thông tin nhạy cảm, vì vậy bật có chọn lọc trong môi trường kiểm thử hoặc theo chính sách bảo mật của hệ thống.

Để quan sát việc trả connection, theo dõi số active connections trên pool và timeout khi chờ connection. Không đánh giá “rò rỉ” chỉ bằng việc thấy nhiều session hoặc nhiều câu SQL; cần đối chiếu thời gian transaction và hành vi release của pool.

## 16. Bốn tình huống thực hành để thấy rõ ranh giới

### Tình huống A — Commit thành công, session đóng

~~~java
try (Session session = factory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        session.persist(new Customer("a@example.com"));
        tx.commit();
    } catch (RuntimeException e) {
        rollbackIfPossible(tx, e);
        throw e;
    }
}
~~~

Nếu không có lỗi, transaction được commit và session đóng khi ra khỏi khối. Truy vấn lại từ session mới sẽ thấy bản ghi theo isolation/mapping bình thường.

### Tình huống B — Flush đã gửi SQL, rồi rollback

~~~java
try (Session session = factory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        session.persist(new Customer("b@example.com"));
        session.flush(); // INSERT có thể đã chạy
        throw new IllegalStateException("Simulated business failure");
    } catch (RuntimeException e) {
        rollbackIfPossible(tx, e);
        // Ở bài tập có thể ghi log rồi xác nhận tình huống thất bại.
    }
}
~~~

Nếu rollback thành công, insert không được commit dù có SQL trong log. Nếu identifier dùng sequence, số thứ tự sequence đã lấy có thể không được trả lại sau rollback; điều đó không làm mất tính nguyên tử của transaction đối với bản ghi vừa insert.

### Tình huống C — Lỗi unique constraint, thử lại trong session mới

~~~java
try {
    unitOfWork.inTransaction(session -> {
        session.persist(new Customer("existing@example.com"));
        session.flush();
        return null;
    });
} catch (RuntimeException failure) {
    // Session lỗi đã đóng bởi unitOfWork.
    // Quyết định trả thông báo trùng email, hoặc retry theo nghiệp vụ.
    log.warn("Customer creation failed", failure);
}
~~~

Không chuyển sang `persist()` entity khác trong chính session/transaction đã lỗi. Nếu lỗi là trùng email, retry dữ liệu y hệt không giải quyết nguyên nhân.

### Tình huống D — Xử lý lazy loading trước khi close

~~~java
List<String> skus = unitOfWork.inTransaction(session -> {
    Order order = session.createSelectionQuery(
        "select distinct o from Order o " +
        "left join fetch o.lines where o.id = :id", Order.class
    ).setParameter("id", orderId).getSingleResult();

    return order.getLines().stream()
        .map(OrderLine::getSku)
        .toList();
});

// Sử dụng skus sau khi session đã đóng vẫn an toàn
// vì đây là List<String> đã materialize, không phải lazy collection.
~~~

Khi thực hành, hãy quan sát thời điểm SQL được gửi, transaction được commit/rollback, session được đóng, và phản ứng khi truy cập entity/collection sau close. Điều quan trọng là **đặt ranh giới resource theo nghiệp vụ**, không phải làm cho `Session` sống càng lâu càng tốt.

## 17. Nguyên tắc vận hành cần ghi nhớ

Khi tự quản lý Hibernate, một đơn vị công việc cơ bản luôn có **chủ sở hữu session rõ ràng**, một **transaction boundary rõ ràng**, và **đường cleanup cho cả thành công lẫn thất bại**. Mã nên đọc theo thứ tự: tạo session từ factory, bắt đầu transaction, thực hiện ORM, commit hoặc rollback, và đóng session.

Những điểm mang tính quyết định:

1. **Tạo `SessionFactory` một lần ở phạm vi ứng dụng** và dùng chung theo cơ chế thread-safe; **không chia sẻ `Session` giữa các thread**.
2. **Mở session theo một đơn vị công việc ngắn**; dùng `try-with-resources` khi chính ứng dụng sở hữu session.
3. **Begin/commit/rollback transaction có chủ đích**; đặc biệt không dùng `close()` thay rollback và không dùng `flush()` thay commit.
4. **Sau lỗi flush/JDBC/transaction, kết thúc session lỗi**; retry nếu cần trong transaction/session mới và theo chính sách idempotency.
5. **Bảo toàn exception gốc**, nhưng ghi nhận lỗi rollback/close bằng suppressed exceptions và logging thích hợp.
6. **Tải những dữ liệu cần trả trước khi đóng session**, hoặc dùng DTO/projection để tránh phụ thuộc vào lazy loading ở tầng sau.
7. **Tôn trọng ownership của framework**: trong Spring/JTA container-managed, để transaction manager quản lý session/persistence context theo hợp đồng của nó.

Tóm lại, `Session` là nơi Hibernate theo dõi các entity trong một phạm vi công việc; `Transaction` quyết định các thao tác SQL ấy được xác nhận hay bị hủy; `SessionFactory` cung cấp hạ tầng dùng chung; còn `close()` chấm dứt vòng đời tài nguyên của session. Thiết kế đúng cả bốn ranh giới giúp ứng dụng tránh rò rỉ tài nguyên, tránh thao tác trên context hỏng sau exception và giữ tính nhất quán dữ liệu khi nghiệp vụ thành công hoặc thất bại.
