# Đặt ranh giới giao dịch tại thao tác nghiệp vụ

Một yêu cầu từ ứng dụng Java có thể phải thực hiện nhiều câu SQL: kiểm tra tồn kho, giữ hàng, tạo đơn và ghi nhận sự kiện cần gửi. Nếu chỉ một bước thành công rồi bước sau thất bại, cơ sở dữ liệu có thể rơi vào trạng thái không khớp với điều mà người dùng đã yêu cầu. **Ranh giới giao dịch** (*transaction boundary*) quyết định những thay đổi nào phải **cùng commit hoặc cùng rollback**, đồng thời xác định thời gian giữ kết nối, khóa và ảnh chụp dữ liệu.

Một thiết kế thường phù hợp là đặt transaction bao quanh **một thao tác nghiệp vụ cần tính nguyên tử** (*business use case / unit of work*). Ranh giới này thường được điều phối ở **application service**, thay vì để mỗi repository tự commit, hoặc giữ một transaction trong toàn bộ vòng đời HTTP request bao gồm cả gọi mạng và xử lý chậm.

Bài thuộc chương **Ranh giới ứng dụng** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Chủ đề kết nối thiết kế persistence cho Java với dữ liệu bền vững, giao dịch, cô lập, kiểm soát đồng thời, xử lý lỗi, cập nhật schema và vận hành hệ thống. Mục tiêu là biết **đặt transaction ở đâu, bao gồm những gì và loại trừ những gì**, trên cơ sở bất biến nghiệp vụ và khả năng thực thi của DBMS.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định một thao tác nghiệp vụ cần atomicity và những thay đổi phải nằm trong cùng transaction.
2. Phân biệt transaction với HTTP request, method Java, repository call và kết nối JDBC.
3. Đặt ranh giới ở tầng application service và tổ chức repository cùng tham gia transaction.
4. Dùng JDBC hoặc Spring `@Transactional` để quản lý commit, rollback và ngoại lệ đúng cách.
5. Phân biệt tác vụ thuần cơ sở dữ liệu với tác dụng phụ như gửi email, gọi API thanh toán, phát message.
6. Nhận diện giới hạn của transaction cục bộ khi thao tác trải qua nhiều database hoặc service.
7. Chọn giải pháp cho đồng thời, retry, idempotency và tình huống không chắc kết quả commit.
8. Kiểm thử cả đường thành công, rollback, tranh chấp và lỗi tại ranh giới transaction.

## 2. Bắt đầu từ bất biến nghiệp vụ

**Bất biến nghiệp vụ** (*business invariant*) là điều kiện phải luôn đúng tại những thời điểm hệ thống đã cam kết một thay đổi hoàn tất. Ví dụ:

- Số lượng hàng còn trong kho không được âm.
- Một lệnh mua có định danh nghiệp vụ duy nhất không được tạo hai đơn đã xác nhận.
- Việc chuyển tiền nội bộ phải ghi cả phần trừ lẫn phần cộng hoặc không ghi phần nào.
- Khi một đơn đã được tạo thành công, sự kiện cần công bố phải có bản ghi bền vững để xử lý sau, nếu hệ thống cam kết cơ chế phát sự kiện tin cậy.

Giả sử nghiệp vụ **đặt hàng** cần:

~~~text
1. Xác nhận request hợp lệ.
2. Giảm số lượng tồn kho.
3. Ghi đơn hàng.
4. Ghi sự kiện vào bảng outbox.
5. Phát sự kiện cho hệ thống giao hàng.
6. Trả phản hồi cho người dùng.
~~~

Các bước 2–4 thay đổi **cùng một cơ sở dữ liệu** và cần đồng bộ với nhau: đã giảm tồn kho thì phải có đơn tương ứng và có dấu vết sự kiện cần phát. Đây là một ứng viên cho **transaction cục bộ**.

Bước 5 gửi đến hệ thống khác: việc phát qua mạng không tự được rollback khi transaction DB rollback. Bước này phải được xử lý theo cơ chế riêng, chẳng hạn **transactional outbox** sau commit.

### 2.1. Atomicity trả lời câu hỏi nào?

Transaction của một DBMS có tính **atomicity**: các thay đổi thuộc transaction cùng được commit hoặc cùng được rollback, trong phạm vi những tài nguyên thực sự tham gia transaction đó.

Nó **không tự bảo đảm**:

- Điều kiện cạnh tranh sẽ luôn đúng nếu dùng mức cô lập không phù hợp.
- Một HTTP request chỉ được xử lý đúng một lần.
- Lệnh gửi email sẽ được thu hồi nếu giao dịch DB thất bại.
- Hai database độc lập sẽ tự commit/rollback cùng nhau.
- Ứng dụng luôn biết chắc transaction đã commit khi đường mạng bị đứt.

Vì vậy xác định phạm vi transaction phải đi cùng câu hỏi về **isolation**, idempotency, hệ thống ngoài và lỗi kết nối.

### 2.2. Sơ đồ ranh giới theo use case

~~~mermaid
flowchart TD
    A["HTTP request: đặt đơn"] --> B["Kiểm tra đầu vào và xác thực"]
    B --> C["Application service: begin transaction"]
    C --> D["Reserve inventory"]
    D --> E["Insert order"]
    E --> F["Insert outbox event"]
    F --> G{"Mọi bước hợp lệ?"}
    G -->|"Có"| H["COMMIT"]
    G -->|"Không / lỗi"| I["ROLLBACK"]
    H --> J["Trả kết quả đã commit"]
    H --> K["Outbox relay gửi thông điệp sau commit"]
~~~

Ranh giới transaction nằm giữa `BEGIN` và `COMMIT/ROLLBACK`; relay gửi thông điệp sau commit là **một công việc khác**. Không nên hiểu sơ đồ là tất cả các bước luôn thực thi tuần tự trong một thread; cách triển khai tùy kiến trúc.

## 3. Vì sao ranh giới theo repository có thể sai?

Một repository thường đại diện cho việc truy cập một loại dữ liệu: `InventoryRepository`, `OrderRepository`, `OutboxRepository`. Nếu **mỗi method repository tự bắt đầu và commit transaction riêng**, thao tác nghiệp vụ nhiều bước không còn nguyên tử.

Ví dụ thiết kế sai:

~~~text
OrderService.placeOrder()
  -> inventoryRepository.decrease()    [BEGIN, UPDATE, COMMIT]
  -> orderRepository.insert()           [BEGIN, INSERT, ERROR, ROLLBACK]
  -> outboxRepository.append()          [chưa chạy]
~~~

Kết quả: tồn kho đã giảm nhưng đơn hàng không tồn tại. Hai câu SQL đều có transaction riêng, nhưng **bất biến nghiệp vụ liên quan hai câu** đã bị phá vỡ.

Trong một thao tác nghiệp vụ nhiều bước, repository nên **tham gia transaction do application service/transaction manager điều phối**. Repository giữ trách nhiệm xây dựng truy vấn và ánh xạ dữ liệu; tầng điều phối giữ trách nhiệm xác định khi nào toàn thao tác đã thành công.

Điều đó không có nghĩa mọi method repository đều bị cấm transaction: một thao tác độc lập, nguyên tử trong một câu SQL có thể sử dụng transaction tự động của DBMS. Vấn đề nằm ở **đơn vị nguyên tử cần bảo đảm**, chứ không phải tên lớp.

## 4. Vì sao transaction cũng không nên bao trùm toàn HTTP request?

Ở chiều ngược lại, mở transaction ngay khi nhận request và chỉ commit lúc xuất HTTP response có thể giữ connection, khóa và snapshot lâu hơn cần thiết.

~~~text
HTTP request
  BEGIN
    Đọc cấu hình
    Gọi HTTP kiểm tra thông tin người nhận     <-- chờ mạng
    Sinh nội dung PDF                           <-- CPU
    UPDATE database                             <-- bắt đầu giữ khóa ghi
    Gửi email xác nhận                          <-- tác dụng phụ ngoài DB
  COMMIT
HTTP response
~~~

Nếu email đã gửi rồi `COMMIT` thất bại, người nhận có thông báo thành công nhưng DB chưa ghi kết quả tương ứng. Nếu giao dịch đang giữ khóa lúc chờ HTTP, request khác có thể bị chặn và connection pool bị cạn.

Thiết kế tốt thường là:

~~~text
Request
  -> xác thực và chuẩn hóa dữ liệu
  -> chuẩn bị dữ liệu có thể tính trước
  -> BEGIN
       đọc/ghi cần nhất quán
       kiểm tra bất biến trong transaction
       ghi bản ghi outbox nếu cần
     COMMIT hoặc ROLLBACK
  -> trả kết quả / lên lịch công việc sau commit
~~~

**Transaction nên đủ rộng để bao trọn bất biến, và đủ ngắn để tránh giữ tài nguyên không cần thiết.** Đây là nguyên tắc tối ưu ranh giới, không phải quy tắc luôn phải có một transaction cho mỗi request. Một request có thể gồm nhiều use case hoặc một thao tác đọc độc lập; một job nền cũng có thể cần transaction dù không có HTTP request.

## 5. Thiết kế use case đặt hàng trên một database

Ví dụ sau sử dụng PostgreSQL để diễn giải ranh giới nghiệp vụ. Các tên bảng chỉ nhằm thực hành; thiết kế thật còn cần mô hình giá, thanh toán, giao hàng và phân quyền tương ứng.

### 5.1. Schema cho quy tắc nguyên tử

~~~sql
CREATE TABLE inventory (
    sku       TEXT PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);

CREATE TABLE purchase_orders (
    id         UUID PRIMARY KEY,
    command_id UUID NOT NULL UNIQUE,
    sku        TEXT NOT NULL REFERENCES inventory(sku),
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    status     TEXT NOT NULL
);

CREATE TABLE outbox_events (
    id           UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    event_type   TEXT NOT NULL,
    payload      JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

- `inventory.available >= 0` được bảo vệ bằng `CHECK` ở DB, không chỉ bằng kiểm tra trên Java.
- `purchase_orders.command_id UNIQUE` tạo một điểm chống trùng cho một lệnh nghiệp vụ.
- `outbox_events` ghi lại ý định phát sự kiện ngay trong cùng transaction với đơn.
- Các ràng buộc trên không tự giải quyết mọi vấn đề vận hành; chẳng hạn worker phát outbox cần xử lý gửi lặp, thất bại và retry.

### 5.2. Các câu SQL cần nằm trong một transaction

~~~sql
BEGIN;

UPDATE inventory
SET available = available - 2
WHERE sku = 'SKU-001'
  AND available >= 2;

-- Ứng dụng kiểm tra affected rows = 1.
-- Nếu bằng 0: tồn kho thiếu hoặc SKU không tồn tại -> rollback.

INSERT INTO purchase_orders (
    id, command_id, sku, quantity, status
) VALUES (
    '00000000-0000-4000-8000-000000000101',
    '00000000-0000-4000-8000-000000000201',
    'SKU-001', 2, 'CREATED'
);

INSERT INTO outbox_events (
    id, aggregate_id, event_type, payload
) VALUES (
    '00000000-0000-4000-8000-000000000301',
    '00000000-0000-4000-8000-000000000101',
    'OrderCreated',
    '{"orderId":"00000000-0000-4000-8000-000000000101"}'::jsonb
);

COMMIT;
~~~

Ví dụ chạy tuần tự để minh họa; các UUID cố định chỉ dùng trong cơ sở dữ liệu thử nghiệm. Trong service thật, nếu `UPDATE` ảnh hưởng 0 hàng, service phải **dừng và rollback** thay vì tiếp tục chèn đơn. Nếu `INSERT` thứ hai thất bại do ràng buộc, toàn transaction phải rollback, bao gồm thao tác giảm tồn kho.

Phép `UPDATE ... WHERE available >= ?` là một **phép ghi có điều kiện**. Ở các engine giao dịch phù hợp, nó tránh kiểu ứng dụng đọc tồn kho rồi cập nhật mù dựa trên dữ liệu cũ. Tuy nhiên, cần kết hợp với cách xử lý lỗi cạnh tranh và kiểm thử thực tế của DBMS đang sử dụng.

### 5.3. Đặt transaction ở application service với Spring

Một thiết kế minh họa:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {
    private final InventoryRepository inventory;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public PlaceOrderService(
            InventoryRepository inventory,
            OrderRepository orders,
            OutboxRepository outbox) {
        this.inventory = inventory;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public UUID place(PlaceOrderCommand command) {
        validate(command);

        var existing = orders.findByCommandId(command.commandId());
        if (existing.isPresent()) {
            ensureSameRequest(existing.get(), command);
            return existing.get().id();
        }

        int changed = inventory.reserve(
            command.sku(), command.quantity());
        if (changed != 1) {
            throw new InsufficientStockException(command.sku());
        }

        UUID orderId = UUID.randomUUID();
        orders.insert(
            orderId, command.commandId(),
            command.sku(), command.quantity(), "CREATED"
        );
        outbox.insertOrderCreated(UUID.randomUUID(), orderId);

        return orderId; // Spring commit khi interceptor kết thúc bình thường.
    }

    // validate / ensureSameRequest là logic kiểm tra nghiệp vụ.
    // Các kiểu PlaceOrderCommand, repository, exception là thành phần
    // minh họa, cần triển khai đúng trong dự án.
}
~~~

Ví dụ được viết ở mức **khung application service**, vì vậy các interface, domain type và method kiểm tra cần được định nghĩa trong dự án. Điểm cốt lõi nằm ở ranh giới: `inventory`, `orders` và `outbox` phải cùng sử dụng **một transaction manager và cùng database/nguồn dữ liệu có khả năng tham gia transaction**. Với Spring, `@Transactional` chỉ có tác dụng mong muốn khi method được gọi qua cơ chế transaction interception và cấu hình đúng.

Nếu một trong các repository tự mở connection độc lập rồi commit riêng, annotation ở service **không tự sửa được** việc tách transaction. Cần kiểm tra thật cách repository lấy connection và cách transaction manager quản lý tài nguyên.

### 5.4. Xử lý request lặp và cạnh tranh

Đoạn `findByCommandId` ở trên là bước kiểm tra giúp trả kết quả cho lệnh đã xử lý. Nó **chưa đủ để ngăn race**:

~~~text
T1: findByCommandId -> không thấy
T2: findByCommandId -> không thấy
T1: thử INSERT command_id X
T2: thử INSERT command_id X
~~~

Ràng buộc `UNIQUE(command_id)` ở database phải là lớp bảo vệ cuối. Giao dịch thua cuộc có thể nhận lỗi trùng khóa và cần rollback. Sau đó có thể dùng **transaction mới** để đọc kết quả gắn với command ID, xác minh nội dung request tương ứng trước khi trả kết quả cũ. Không coi mọi lỗi unique là tín hiệu “trả thành công”: lỗi có thể xảy ra ở một constraint khác.

Đây là lý do **transaction và idempotency là hai cơ chế bổ trợ**: transaction bảo vệ các thay đổi trong một lần thử; idempotency xử lý nhiều lần yêu cầu cùng một ý định nghiệp vụ.

## 6. JDBC: tự quản lý đúng một transaction cho nhiều repository

Nếu không dùng framework transaction manager, tầng service có thể mượn một connection từ `DataSource`, tắt auto-commit, thực hiện các bước nghiệp vụ qua **cùng connection**, rồi commit/rollback.

### 6.1. Ví dụ chuyển số dư giữa hai tài khoản

~~~sql
CREATE TABLE accounts (
    id      BIGINT PRIMARY KEY,
    balance NUMERIC(16, 2) NOT NULL CHECK (balance >= 0)
);

INSERT INTO accounts (id, balance)
VALUES (101, 500.00), (102, 250.00);
~~~

Mã Java minh họa:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(long fromId, long toId, BigDecimal amount)
            throws SQLException {
        if (fromId == toId || amount == null
                || amount.signum() <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();
            Throwable primaryFailure = null;
            try {
                connection.setAutoCommit(false);

                int debited = debit(connection, fromId, amount);
                if (debited != 1) {
                    throw new IllegalStateException(
                        "Source account absent or insufficient balance");
                }

                int credited = credit(connection, toId, amount);
                if (credited != 1) {
                    throw new IllegalStateException(
                        "Destination account absent");
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                primaryFailure = failure;
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                try {
                    connection.setAutoCommit(originalAutoCommit);
                } catch (SQLException resetFailure) {
                    if (primaryFailure != null) {
                        primaryFailure.addSuppressed(resetFailure);
                    } else {
                        throw resetFailure;
                    }
                }
            }
        }
    }

    private static int debit(
            Connection connection, long id, BigDecimal amount)
            throws SQLException {
        try (PreparedStatement sql = connection.prepareStatement(
                "UPDATE accounts "
              + "SET balance = balance - ? "
              + "WHERE id = ? AND balance >= ?")) {
            sql.setBigDecimal(1, amount);
            sql.setLong(2, id);
            sql.setBigDecimal(3, amount);
            return sql.executeUpdate();
        }
    }

    private static int credit(
            Connection connection, long id, BigDecimal amount)
            throws SQLException {
        try (PreparedStatement sql = connection.prepareStatement(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {
            sql.setBigDecimal(1, amount);
            sql.setLong(2, id);
            return sql.executeUpdate();
        }
    }
}
~~~

Đoạn mã chỉ minh họa transaction cục bộ trong JDBC. Một hệ thống tiền tệ thật còn cần định danh lệnh chuyển duy nhất, ledger/kiểm toán, cơ chế idempotency, phân quyền, quy tắc làm tròn, chống tranh chấp và xác minh kết quả khi mất kết nối.

Các điểm quan trọng:

- Hai phép `UPDATE` dùng **chính đối tượng connection** do service mượn.
- Nếu bước thứ hai lỗi, service rollback cả phép trừ trước đó.
- `try-with-resources` đóng lease JDBC khi kết thúc; với pool, `close()` thường trả connection về pool.
- Ngoại lệ rollback được giữ trong `suppressed` để không che mất lỗi đầu tiên.
- Việc reset `autoCommit` có thể thất bại và khiến caller nhận lỗi sau khi commit đã thành công; cần phân biệt lỗi cleanup và kết quả transaction thực sự, không retry mù.
- `commit()` không tự giải quyết trường hợp mất kết nối sau khi server đã nhận commit nhưng trước khi client nhận kết quả.

**Giới hạn của ví dụ:** không bảo đảm ngăn mọi deadlock, kiểm tra số dư không thay thế tất cả kiểm soát đồng thời và các exception/thông điệp chưa được ánh xạ thành API lỗi theo nghiệp vụ. Trong dự án lớn nên dùng transaction manager ổn định để tránh lặp mã quản lý transaction ở nhiều service.

### 6.2. Tại sao không truyền connection tùy ý khắp nơi?

Có thể truyền `Connection` cho các hàm repository nội bộ trong phạm vi transaction, nhưng tránh để domain model hoặc controller phụ thuộc trực tiếp vào JDBC. Một lớp điều phối transaction/repository abstraction giúp mã nghiệp vụ tách khỏi công nghệ lưu trữ.

Không dùng một connection làm field singleton chia sẻ giữa nhiều request: transaction và trạng thái session có thể bị trộn. Mỗi đơn vị công việc phải có vòng đời mượn/trả tài nguyên rõ ràng.

## 7. Spring `@Transactional`: hành vi cần hiểu

### 7.1. Commit và rollback không chỉ phụ thuộc annotation

Với cấu hình Spring transaction phổ biến:

- Method `@Transactional` được gọi qua interceptor sẽ tham gia hoặc tạo transaction theo propagation.
- Nếu method hoàn tất bình thường, transaction manager thử commit ở cuối ranh giới.
- Nếu ném **unchecked exception** (ví dụ `RuntimeException`, `Error`), Spring mặc định đánh dấu rollback.
- Với **checked exception**, mặc định phổ biến không rollback nếu chưa cấu hình, dù vẫn có thể cấu hình `rollbackFor` hoặc quy tắc khác.
- Rollback chỉ có thể đảo các thao tác thuộc tài nguyên thực sự tham gia transaction; gửi HTTP, ghi file hoặc phát thông điệp bên ngoài không tự được đảo.

Ví dụ:

~~~java
@Transactional(rollbackFor = BusinessValidationException.class)
public void executeBusinessOperation() throws BusinessValidationException {
    // BusinessValidationException là checked exception
    // mà use case muốn rollback khi ném ra.
}
~~~

Đừng dựa vào quy tắc checked/unchecked mà không xem chính sách transaction của phiên bản framework và dự án đang dùng.

### 7.2. Nuốt lỗi bên trong transaction có thể dẫn tới commit sai

~~~java
@Transactional
public void placeOrder(PlaceOrderCommand command) {
    inventory.reserve(command.sku(), command.quantity());

    try {
        orders.insert(command);
    } catch (DataAccessException error) {
        log.warn("Could not insert order", error);
        // Sai nếu method tiếp tục và được coi như thành công.
    }
}
~~~

Nếu lỗi được bắt và không ném tiếp hoặc không đánh dấu rollback phù hợp, transaction manager có thể thử commit phần thay đổi còn lại (hoặc DBMS có thể đã đưa transaction vào trạng thái lỗi). Đúng hay sai còn phụ thuộc trạng thái DB, nhưng **không thể dựa vào annotation để cứu một luồng xử lý đã che lỗi**.

Khi nghiệp vụ không thể hoàn thành, hãy biểu diễn thất bại một cách rõ ràng để transaction manager thực hiện rollback. Nếu một bước chỉ là *best effort*, hãy tách rõ ngữ nghĩa và ranh giới xử lý của nó.

### 7.3. Self-invocation và lời gọi qua proxy

Với chế độ proxy/AOP thông dụng trong Spring, annotation thường được áp dụng khi lời gọi đi qua proxy. Một phương thức trong cùng bean gọi trực tiếp phương thức `@Transactional` khác của chính đối tượng có thể **không được interceptor xử lý như kỳ vọng**:

~~~java
@Service
public class ExampleService {
    public void outer() {
        inner(); // Lời gọi nội bộ thường không đi qua proxy.
    }

    @Transactional
    public void inner() {
        // Không mặc nhiên có transaction mới do annotation này.
    }
}
~~~

Cách tổ chức là để entry point được container quản lý gọi qua boundary phù hợp, tách use case ra service khác hoặc dùng transaction API tường minh nếu cần. Chi tiết phụ thuộc cấu hình proxy, AspectJ và framework; cần kiểm tra thực tế.

### 7.4. Propagation: REQUIRED, REQUIRES_NEW, NESTED

Một use case có thể gọi service khác có annotation transaction. Propagation định nghĩa cách những lời gọi đó liên hệ với transaction đã tồn tại:

| Propagation (Spring) | Ý tưởng chính | Hệ quả cần cân nhắc |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện tại; nếu chưa có thì tạo mới | Các bước thường commit/rollback cùng nhau |
| `REQUIRES_NEW` | Tạm ngưng transaction hiện tại và mở transaction độc lập | Transaction bên trong có thể commit dù bên ngoài rollback |
| `NESTED` | Sử dụng transaction lồng dựa trên savepoint khi transaction manager/tài nguyên hỗ trợ | Có thể rollback về savepoint, nhưng không tương đương transaction độc lập |
| `SUPPORTS` | Tham gia nếu có transaction, nếu không có thì chạy ngoài transaction | Không bảo đảm atomicity nếu caller chưa mở transaction |
| `MANDATORY` | Yêu cầu phải có transaction hiện tại | Giúp phát hiện lời gọi sai ranh giới |

Ví dụ rủi ro:

~~~text
placeOrder()           [REQUIRED, transaction T1]
  reserveInventory()   [tham gia T1]
  auditService.log()   [REQUIRES_NEW, transaction T2: COMMIT]
  insertOrder()        [T1 lỗi -> ROLLBACK]
~~~

Kết quả: audit của T2 có thể tồn tại dù đơn T1 rollback. Có khi đây là chủ ý (ghi log cố gắng độc lập), nhưng với **outbox phải mô tả trạng thái đã commit**, việc tách sang transaction độc lập thường không phù hợp.

`REQUIRES_NEW` cũng có thể cần connection thứ hai trong khi transaction ngoài vẫn giữ một connection; nếu nhiều thread làm tương tự, pool có thể cạn. `NESTED` và savepoint phụ thuộc transaction manager/driver, không phải cam kết hỗ trợ của mọi backend.

Một tình huống khác: transaction tham gia cùng nhau nhưng một bước đã đánh dấu `rollback-only`; caller bắt lỗi rồi cố commit có thể nhận lỗi tương tự `UnexpectedRollbackException`. Cần điều tra vì sao transaction chung bị đánh dấu rollback thay vì lén bỏ qua.

## 8. Tính cô lập và tính nguyên tử là hai vấn đề khác nhau

Đặt đúng ranh giới transaction bảo vệ **atomicity**, nhưng không tự loại hết race condition. Hãy xem thao tác giảm tồn kho:

~~~text
T1: SELECT available -> 1
T2: SELECT available -> 1
T1: UPDATE available = 0; COMMIT
T2: UPDATE available = 0; COMMIT
~~~

Nếu cả hai hệ thống đều ghi nhận một đơn thành công, có thể đã bán hai sản phẩm từ một đơn vị tồn kho dù giá trị cột không âm. Hai transaction vẫn có thể hoàn tất một cách nguyên tử, nhưng **bất biến số đơn được chấp nhận so với số hàng còn lại đã sai**.

Một hướng thường hiệu quả hơn là đưa điều kiện vào chính câu SQL ghi:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE sku = :sku
  AND available >= :quantity;
~~~

Trong đoạn trên, `:quantity` và `:sku` là ký hiệu tham số đặt tên theo cách trình bày của thư viện truy cập dữ liệu; khi dùng JDBC `PreparedStatement` thuần cần chuyển thành dấu `?` và gắn giá trị qua setter theo vị trí. Đây không phải cú pháp tham số dùng trực tiếp trong `psql`.

Chỉ tiếp tục đặt đơn nếu `affected rows = 1`. Đây là cách triển khai một phép ghi có điều kiện; phải kiểm thử với DBMS, isolation và workload thật.

Các lựa chọn khác gồm:

- **Optimistic locking:** thêm cột `version` và chỉ update nếu version còn đúng.
- **Pessimistic locking:** chọn và khóa hàng cần sửa bằng `SELECT ... FOR UPDATE` hoặc cơ chế tương ứng.
- **Ràng buộc database:** unique, foreign key, check để bảo vệ điều kiện có thể biểu diễn tại DB.
- **SERIALIZABLE / phát hiện xung đột:** dùng khi nghiệp vụ có bất biến liên hàng và cần bảo đảm tương đương lịch tuần tự, chấp nhận khả năng transaction phải retry.

Không phải mọi ràng buộc nghiệp vụ liên hàng có thể giải quyết bằng một `CHECK`. Nếu hai transaction đọc “hiện còn một người trực khác” rồi cập nhật hai hàng khác nhau, *write skew* có thể vẫn xảy ra dưới một số hiện thực snapshot isolation. Cần thiết kế đồng thời dựa trên bất biến cụ thể.

## 9. Một use case không luôn tương đương một transaction database

Nếu use case trải qua nhiều hệ thống, transaction cục bộ chỉ quản lý một phạm vi. Ví dụ:

~~~text
Đặt đơn:
  - Database Order: lưu đơn
  - Payment Gateway: trừ tiền
  - Warehouse Service: giữ hàng
  - Message Broker: thông báo xử lý
~~~

Không thể mặc định một `@Transactional` trên OrderService sẽ commit/rollback đồng thời tất cả thành phần trên. Transaction manager chỉ bảo đảm các tài nguyên nó thực sự quản lý với cơ chế tương ứng.

### 9.1. Transactional outbox

Khi cần bảo đảm rằng việc tạo đơn sẽ đi cùng ý định phát sự kiện:

~~~text
Transaction T1 (Order DB):
  INSERT purchase_orders
  INSERT outbox_events
  COMMIT

Outbox relay (sau commit, công việc độc lập):
  Đọc sự kiện chưa gửi
  Gửi đến message broker
  Đánh dấu / ghi nhận kết quả gửi
~~~

Nếu T1 rollback thì không có đơn cũng không có outbox event. Nếu relay lỗi sau commit, bản ghi outbox còn lại để retry. Tuy nhiên, một relay có thể gửi thành công nhưng chưa kịp đánh dấu đã gửi trước khi crash: **thông điệp có thể được gửi lặp**. Consumer cần idempotency/deduplication theo event ID hoặc khóa nghiệp vụ thích hợp.

Đây là cơ chế nhất quán dựa trên bản ghi bền vững và retry, không biến DB và broker thành một transaction nguyên tử duy nhất.

### 9.2. Saga và hành động bù

Với chuỗi nghiệp vụ dài giữa các service, có thể cần mô hình **saga**: mỗi bước có transaction cục bộ và, khi bước sau thất bại, hệ thống thực hiện các hành động bù (*compensating actions*) phù hợp.

~~~text
T1: tạo đơn chờ thanh toán       COMMIT
T2: yêu cầu thanh toán           thành công
T3: giữ hàng ở kho               thất bại
Bù: yêu cầu hoàn/hủy thanh toán, chuyển đơn về trạng thái phù hợp
~~~

Hành động bù **không phải rollback tức thời**: có thể cần thời gian, retry, giám sát và xử lý trường hợp không bù được. Người dùng có thể nhìn thấy trạng thái trung gian. Cần state machine và khả năng đối soát để ngăn thực thi lặp hoặc bỏ sót.

### 9.3. Distributed transaction có phù hợp không?

Một số hệ thống hỗ trợ giao thức commit phân tán như 2PC/XA. Đây là cơ chế có chi phí, giới hạn tương thích và rủi ro khi hạ tầng gặp sự cố. Không nên coi một annotation ở service mặc nhiên bật transaction phân tán.

Lựa chọn giữa transaction cục bộ + outbox, saga hoặc transaction phân tán phải dựa trên yêu cầu nhất quán, hệ thống tham gia, hạ tầng và khả năng vận hành.

## 10. Retry, rollback và kết quả COMMIT không chắc chắn

### 10.1. Retry bao trọn thao tác nghiệp vụ

Một transaction có thể bị hủy do deadlock, serialization failure hoặc xung đột khác. Khi nghiệp vụ cho phép thử lại, cần **rollback và chạy lại toàn bộ thao tác transaction** với dữ liệu mới:

~~~text
for attempt from 1 to MAX_ATTEMPTS:
    BEGIN
    read current state
    validate business rules
    perform all DB writes
    COMMIT
    return result

    if known retryable concurrency failure:
        ROLLBACK if still active
        bounded backoff (+ jitter)
        repeat from BEGIN
~~~

Ví dụ PostgreSQL có SQLSTATE `40P01` cho deadlock và `40001` cho serialization failure. Không retry vô hạn, và không tự nhận mọi lỗi `SQLException` đều có thể retry. Lỗi sai schema, vi phạm dữ liệu hay sai quyền cần xử lý riêng.

Nếu một transaction đã bị đánh dấu không hợp lệ, retry riêng câu SQL cuối trong **cùng transaction** thường không thể sửa được; các điều kiện nghiệp vụ đã đọc trước đó cũng có thể đã lỗi thời.

### 10.2. Không dùng transaction để che rủi ro thực thi lặp

Một lệnh mua có thể được gửi nhiều lần do client retry hoặc mạng chập chờn. Vì vậy:

- Gắn **idempotency key/command ID** ổn định vào đơn vị nghiệp vụ.
- Dùng ràng buộc `UNIQUE` để chống ghi trùng ở DB.
- Nếu nhận lại cùng command, xác minh payload tương đương và trả kết quả đã lưu khi phù hợp.
- Đừng gửi email/thu tiền trực tiếp trong vòng retry của transaction, trừ khi hệ thống ngoài có hợp đồng idempotency đầy đủ.

**Tình huống khó nhất:** ứng dụng gửi `COMMIT` nhưng mất kết nối trước khi nhận phản hồi. DB có thể đã commit. `rollback()` gọi sau đó không chứng minh transaction chưa được commit. Cần **đối soát bằng command ID** ở transaction/kết nối mới trước khi quyết định thử lại.

### 10.3. Lỗi cleanup không được che lỗi chính

Trong JDBC, `rollback()` và `close()` cũng có thể thất bại. Nếu lỗi SQL đầu tiên bị che bằng ngoại lệ rollback, việc điều tra và quyết định retry trở nên khó khăn. Hãy giữ lỗi đầu làm `cause` hoặc exception chính, và gắn lỗi phụ qua `addSuppressed()` khi phù hợp.

Với Spring, cần quan sát nguyên nhân transaction đã rollback, lỗi tại commit và ngoại lệ do transaction interceptor ném ra. **Không** đổi mọi lỗi thành một thông báo “thử lại sau” nếu chưa phân loại.

## 11. Giao dịch đọc và tác vụ dài

### 11.1. Không phải mọi truy vấn SELECT đều cần transaction tường minh dài

Nếu endpoint chỉ đọc một hàng bằng một câu `SELECT`, transaction mặc định của DBMS có thể đã đủ cho yêu cầu nhất quán của câu lệnh. Việc giữ `@Transactional(readOnly = true)` dài qua nhiều bước không mặc nhiên làm API nhanh hơn hay an toàn hơn.

Khi báo cáo gồm nhiều `SELECT` phải nhìn một ảnh chụp nhất quán, có thể cần transaction đọc với isolation phù hợp (chẳng hạn PostgreSQL `REPEATABLE READ` cho các SELECT thường). Ngữ nghĩa khác giữa DBMS và kiểu câu lệnh; `readOnly = true` trong Spring thường là *hint*/cấu hình cho framework, không phải cam kết mọi hệ quản trị đều chặn ghi.

Transaction đọc dài vẫn có chi phí: giữ connection trong pool, giữ snapshot/phiên bản dữ liệu ở các engine MVCC và có thể ảnh hưởng vận hành.

### 11.2. Batch job: không gom vô hạn bản ghi vào một transaction

Nếu job nhập một triệu hàng, một transaction duy nhất có thể tạo thời gian giữ khóa, dung lượng log và rủi ro rollback rất lớn. Có thể chia job thành các lô độc lập nếu nghiệp vụ cho phép:

~~~text
Job import:
  Batch 1 -> transaction riêng -> COMMIT -> checkpoint 1
  Batch 2 -> transaction riêng -> COMMIT -> checkpoint 2
  Batch 3 -> lỗi -> ROLLBACK batch 3
  Retry từ checkpoint phù hợp
~~~

Đổi từ một transaction lớn sang nhiều batch **thay đổi ngữ nghĩa atomicity**: các batch trước có thể đã commit dù batch sau thất bại. Phải thiết kế trạng thái nhập, checkpoint, idempotency và xử lý dữ liệu dở dang.

### 11.3. Luồng bất đồng bộ không tự kế thừa transaction

Trong Java, `@Async`, `CompletableFuture`, worker hoặc callback có thể chạy ở thread khác. Một transaction gắn với thread hiện tại của Spring phổ biến **không tự lan qua mọi thread**; việc dùng cùng `DataSource` không tạo chung transaction.

Nếu cần xử lý nền bền vững, hãy tạo một đơn vị công việc riêng với transaction riêng, cơ chế enqueue/outbox và ranh giới lỗi rõ ràng. Không giữ connection/transaction của request mở để chờ task bất đồng bộ kết thúc.

## 12. Đo chi phí ranh giới giao dịch

Mỗi transaction dùng tài nguyên: connection, bản ghi log, khóa, snapshot và công việc commit. Một transaction quá dài có thể:

- Chặn các giao dịch ghi khác.
- Giữ connection và làm cạn pool khi tải tăng.
- Kéo dài thời gian lưu phiên bản dữ liệu cũ trong hệ MVCC.
- Tăng xác suất deadlock, timeout và lỗi khi retry.
- Mở rộng phạm vi thất bại: rollback một giao dịch lớn có thể làm mất nhiều công việc hơn.

Một transaction quá nhỏ hoặc bị tách sai có thể:

- Commit phần dữ liệu dù use case chưa hoàn tất.
- Đòi hỏi logic bù hoặc khôi phục phức tạp.
- Tạo nhiều lần đi lại mạng/commit cho một thao tác có thể thực hiện gọn hơn.
- Khiến người dùng quan sát trạng thái nửa hoàn tất.

Đo các chỉ số như: thời lượng transaction, thời gian giữ connection, lock wait, deadlock/serialization failures, số rollback, độ trễ p95/p99 và tần suất retry. Khi có thay đổi ranh giới, đánh giá cả **tính đúng đắn nghiệp vụ** và **khả năng chịu tải**.

## 13. Kiểm thử ranh giới giao dịch

Không đủ nếu chỉ kiểm tra “gọi service trả về thành công”. Cần kiểm thử các trường hợp khiến một bước lỗi và các request cạnh tranh.

| Tình huống thử | Bằng chứng mong đợi |
|---|---|
| Tất cả bước DB thành công | Inventory, order và outbox cùng commit |
| `inventory.reserve` ảnh hưởng 0 hàng | Không tạo order/outbox |
| `orders.insert` vi phạm ràng buộc | Inventory đã giảm trong transaction phải rollback |
| `outbox.insert` lỗi | Order và inventory cùng rollback |
| Hai lệnh cùng mua số lượng tồn cuối cùng | Không chấp nhận nhiều đơn hơn tồn kho thực tế |
| Cùng `command_id` được gọi hai lần | Không tạo hai đơn; kết quả xử lý lặp nhất quán |
| Lỗi serialization/deadlock | Retry toàn transaction trong giới hạn |
| Mất kết nối lúc commit | Không khẳng định commit/rollback thiếu bằng chứng; đối soát |
| Outbox relay gửi thành công rồi crash | Consumer không tạo tác dụng phụ lặp ngoài kiểm soát |
| Gọi service qua Spring proxy / self-invocation | Ranh giới transaction thực tế khớp thiết kế |

Với PostgreSQL, có thể mở hai connection độc lập và điều khiển thứ tự chạy để tái hiện race. Đừng chỉ mock repository để khẳng định rollback thật đã xảy ra: kiểm thử integration với DBMS/transaction manager thật giúp phát hiện khác biệt mà mock không thể hiện.

Không cần biến mọi trường hợp thành một test nặng. Ưu tiên test có **nguy cơ làm sai dữ liệu** và những ca phụ thuộc cơ chế giao dịch của DBMS.

## 14. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách thiết kế lại |
|---|---|---|
| Mỗi repository tự commit một lần | Use case nhiều bước có thể bị commit một nửa | Đặt transaction tại application service |
| Đặt transaction bao cả network call dài | Giữ khóa/connection quá lâu | Chuyển network I/O ra ngoài transaction |
| Bắt exception rồi tiếp tục như thành công | DB có thể commit dữ liệu thiếu bước bắt buộc | Ném lỗi/đánh dấu rollback đúng |
| Đặt `@Transactional` ở method nội bộ và tự gọi | Interceptor có thể không chạy | Gọi qua boundary được quản lý hoặc dùng transaction API |
| Dùng `REQUIRES_NEW` cho outbox phải đi cùng đơn | Outbox có thể commit dù đơn rollback | Cho outbox tham gia transaction của đơn |
| Chỉ đọc tồn kho rồi ghi từ giá trị cũ | Overselling/lost update | Ghi có điều kiện, lock hoặc cơ chế đồng thời phù hợp |
| Xem `@Transactional` là transaction toàn hệ thống | Side effect ngoài DB không rollback | Outbox, saga hoặc cơ chế phân tán thích hợp |
| Retry mỗi câu SQL trong transaction lỗi | Bất biến không được kiểm tra lại | Retry toàn use case transaction |
| Retry mù khi COMMIT mất phản hồi | Có thể thực thi lệnh hai lần | Idempotency key và đối soát |
| Giữ một transaction cho job nhập cực lớn | Khóa/log/rollback lớn và khó phục hồi | Batch có checkpoint nếu nghiệp vụ cho phép |

## 15. Bài tập vận dụng

### Bài 1. Ranh giới của use case đặt đơn

Một service lần lượt (1) trừ tồn kho, (2) chèn đơn, (3) gửi email, (4) ghi outbox. Các bước nào nên cùng transaction cục bộ nếu inventory, order và outbox cùng DB?

**Gợi ý:** (1), (2) và (4) cùng transaction. Gửi email không thực hiện bên trong transaction nếu không có hợp đồng idempotency/phối hợp phù hợp; outbox relay xử lý sau commit.

### Bài 2. Repository commit sớm

`InventoryRepository.reserve()` tự `COMMIT`. `OrderRepository.insert()` gặp lỗi unique. Service có `@Transactional`. Tồn kho có chắc được rollback?

**Gợi ý:** Không. Nếu repository đã commit trên transaction riêng, transaction của service không thể rollback thay đổi đã commit. Kiểm tra cách kết nối/transaction manager được sử dụng.

### Bài 3. Checked exception và rollback

Method Spring `@Transactional` cập nhật DB, sau đó ném một checked exception mà cấu hình không yêu cầu rollback. Có chắc DB sẽ rollback?

**Gợi ý:** Không. Mặc định phổ biến rollback cho unchecked exception và `Error`; với checked exception cần cấu hình `rollbackFor` hoặc chính sách tương đương khi muốn rollback.

### Bài 4. Self-invocation

Method `create()` trong một Spring bean gọi trực tiếp `saveInternal()` cùng bean; chỉ `saveInternal()` có `@Transactional`. Có chắc transaction được tạo?

**Gợi ý:** Không với proxy-based AOP phổ biến. Cần gọi qua transaction proxy/boundary phù hợp hoặc dùng transaction API tường minh.

### Bài 5. Hai người cùng mua sản phẩm cuối

Có đúng một sản phẩm trong kho. Hai request cùng đọc `available = 1`, sau đó cả hai tạo đơn. Chỉ mở transaction cho mỗi request có đủ để ngăn lỗi không?

**Gợi ý:** Không. Dùng phép update có điều kiện `available >= quantity`, ràng buộc DB và xử lý row count/xung đột phù hợp với DBMS.

### Bài 6. Timeout khi đang commit

Ứng dụng gửi `COMMIT` nhưng mất mạng trước khi nhận kết quả. Có thể luôn coi transaction đã rollback và retry?

**Gợi ý:** Không. Kết quả có thể đã commit. Dùng command ID cố định, đối soát trạng thái và chỉ retry theo hợp đồng idempotency.

### Bài 7. Transaction trong job nhập dữ liệu

Job cập nhật 100.000 dòng trong một transaction, thường bị timeout và rollback mọi thứ. Nhóm muốn chia thành 100 batch, mỗi batch có một commit. Cần quyết định điều gì trước?

**Gợi ý:** Các batch có thể commit riêng được không? Nếu một batch lỗi, xử lý các batch trước thế nào? Thiết kế checkpoint, idempotency, trạng thái job và khả năng khôi phục.

### Bài 8. `REQUIRES_NEW` gây lệch trạng thái

Use case tạo đơn đang trong T1; method ghi outbox dùng `REQUIRES_NEW` tạo T2 và commit. T1 sau đó rollback. Điều gì xảy ra?

**Gợi ý:** Outbox đã commit dù đơn không có. Nếu outbox phải phản ánh đơn đã commit, hãy dùng cùng transaction với đơn.

## 16. Ghi nhớ

- **Ranh giới transaction được quyết định bởi bất biến của thao tác nghiệp vụ.** Một use case gồm nhiều bước DB có thể cần cùng commit/rollback; tên method repository không quyết định tính nguyên tử.
- **Application service thường là nơi điều phối transaction** giữa các repository; controller/domain giữ những trách nhiệm riêng.
- **Transaction cần vừa đủ và ngắn.** Bao trọn kiểm tra và ghi cần nhất quán, tránh giữ connection/khóa trong khi gọi dịch vụ ngoài hoặc xử lý không liên quan DB.
- **`@Transactional` chỉ có tác dụng khi cấu hình và lời gọi phù hợp.** Hiểu rollback rules, propagation, self-invocation và cách repository tham gia nguồn dữ liệu.
- **Atomicity không thay thế isolation.** Race condition còn cần update có điều kiện, optimistic/pessimistic locking, ràng buộc và mức cô lập phù hợp.
- **Một transaction DB không tự bao phủ hệ thống phân tán.** Outbox, saga, idempotency và đối soát giúp xử lý side effect và kết quả không chắc chắn.
- **Kiểm chứng bằng lỗi và đồng thời**, không chỉ bằng đường thành công; ưu tiên test rollback, race, duplicate command và mất phản hồi commit.

Đặt ranh giới giao dịch tại thao tác nghiệp vụ giúp lớp persistence Java bảo đảm dữ liệu được thay đổi trọn vẹn theo một ý định có nghĩa, đồng thời giữ tài nguyên và thời gian khóa trong tầm kiểm soát. Thiết kế tốt bắt đầu từ **bất biến cần bảo vệ**, rồi mới chọn công cụ JDBC, Spring, mức cô lập và chiến lược phối hợp với các hệ thống bên ngoài.
