# Vòng đời kết nối và quyền sở hữu giao dịch trong ứng dụng

Trong một ứng dụng dùng cơ sở dữ liệu, transaction không chỉ là vài câu SQL có `BEGIN` và `COMMIT`. Nó còn gắn với một kết nối, một luồng thực thi hoặc một ngữ cảnh reactive, một phạm vi xử lý nghiệp vụ và một cơ chế quản lý tài nguyên. Nếu ứng dụng không xác định rõ ai mở transaction, ai được phép commit/rollback và khi nào kết nối được trả về pool, lỗi có thể xuất hiện dưới dạng dữ liệu commit dở dang, transaction bị giữ quá lâu, connection leak, deadlock hoặc trạng thái session bị rò rỉ sang request khác.

Nguyên tắc quan trọng là **một thành phần ở tầng nghiệp vụ nên sở hữu ranh giới transaction; các repository thực hiện thao tác dữ liệu bên trong ranh giới đó và tuân theo quyền sở hữu đã được thiết lập**. Với JDBC thuần, code mở connection và transaction phải chịu trách nhiệm commit/rollback rồi đóng connection. Với Spring hoặc framework tương tự, transaction manager thường sở hữu connection và điều phối vòng đời; service khai báo ranh giới transaction, còn repository không tự ý commit hay đóng connection do framework quản lý.

## 1. Kết nối và transaction là hai vòng đời liên quan nhưng khác nhau

**Connection** đại diện cho một phiên làm việc giữa ứng dụng và database. Nó mang trạng thái session như transaction đang mở, chế độ autocommit, isolation level, schema hiện tại, session variables, timeout và các tài nguyên đang được sử dụng.

**Transaction** là một đơn vị công việc cần được database xử lý theo các thuộc tính giao dịch. Transaction bắt đầu, thực hiện các câu lệnh, rồi kết thúc bằng commit hoặc rollback. Một transaction thường chạy trên một connection trong mô hình JDBC truyền thống.

Hai vòng đời này có quan hệ như sau:

```text
Ứng dụng mượn connection từ DataSource/pool
        |
        v
Thiết lập hoặc nhận trạng thái transaction
        |
        v
Thực hiện nhiều câu SQL trong transaction
        |
        +---- COMMIT: xác nhận thay đổi
        |             hoặc
        +---- ROLLBACK: hủy thay đổi chưa commit
        |
        v
Trả connection về pool / đóng connection vật lý
```

Kết thúc transaction không nhất thiết đồng nghĩa connection vật lý bị đóng. Nếu dùng connection pool, thao tác `close()` trên connection mượn thường trả nó về pool để tái sử dụng. Connection vật lý chỉ bị pool đóng khi pool loại bỏ nó, ứng dụng shutdown hoặc có chính sách bảo trì.

Ngược lại, một connection có thể tồn tại lâu hơn một transaction. Sau khi transaction kết thúc, connection có thể được mượn cho một transaction khác hoặc thực hiện câu lệnh autocommit tiếp theo. Vì vậy, không nên nhầm “connection còn mở” với “transaction còn mở”.

## 2. Connection pool quản lý kết nối vật lý

Tạo kết nối database mới cho mỗi request có thể tốn thời gian và tài nguyên. Connection pool duy trì một tập connection vật lý đã được tạo sẵn, rồi cho ứng dụng mượn và trả lại khi cần.

Các thành phần thường gặp:

- `DataSource`: điểm truy cập chuẩn để ứng dụng lấy connection.
- Connection pool: quản lý connection vật lý, giới hạn số lượng, cấp phát connection rảnh và thu hồi connection được trả lại.
- Pooled connection: connection vật lý hoặc wrapper do pool quản lý.
- Borrowed connection: handle ứng dụng đang sử dụng; `close()` thường trả handle về pool.

Vòng đời điển hình:

1. Ứng dụng gọi `dataSource.getConnection()`.
2. Pool cấp một connection rảnh; nếu chưa có, request có thể phải chờ đến khi có connection hoặc hết acquisition timeout.
3. Ứng dụng thực hiện SQL và transaction.
4. Ứng dụng hoặc transaction manager kết thúc transaction.
5. Ứng dụng gọi `close()` trên handle đã mượn.
6. Pool reset các trạng thái session cần thiết rồi đánh dấu connection có thể được mượn lại.

Ví dụ JDBC:

```java
try (Connection connection = dataSource.getConnection()) {
    // Sử dụng connection trong phạm vi này.
}
// close() trả connection về pool nếu DataSource dùng pool.
```

Không nên giữ connection trong field singleton, cache toàn cục hoặc biến static để dùng qua nhiều request. Connection là tài nguyên có trạng thái và thường không an toàn khi nhiều thread cùng sử dụng đồng thời.

### Pool size và thời gian giữ connection

Số connection tối đa trong pool là một giới hạn tài nguyên. Nếu một request mượn connection rồi gọi HTTP trong vài giây trước khi trả lại, connection vẫn bị chiếm dù database không thực hiện SQL trong thời gian đó. Khi nhiều request làm tương tự, pool có thể cạn và các request mới phải chờ.

Thời gian giữ connection phụ thuộc nhiều vào thời gian transaction và cách ứng dụng quản lý connection. Một transaction dài giữ connection lâu hơn, làm giảm số request có thể phục vụ đồng thời. Do đó, cần chuẩn bị dữ liệu không cần database trước khi mở transaction, thực hiện phần ghi/đọc cần tính nguyên tử, commit sớm rồi mới thực hiện các công việc bên ngoài.

## 3. Quyền sở hữu transaction

Quyền sở hữu transaction (*transaction ownership*) trả lời ba câu hỏi:

1. Ai quyết định transaction bắt đầu ở đâu?
2. Ai chịu trách nhiệm commit hoặc rollback?
3. Ai giải phóng connection và các tài nguyên liên quan?

Một quy tắc thiết kế dễ hiểu là **tầng bắt đầu transaction cũng chịu trách nhiệm kết thúc transaction**. Nếu service mở transaction, service hoặc transaction manager được service ủy quyền phải bảo đảm mọi nhánh đều commit hoặc rollback. Repository thường không tự commit vì nó không biết toàn bộ quy trình nghiệp vụ đã hoàn thành hay chưa.

Ví dụ một thao tác chuyển tiền cần nhiều bước:

```text
TransferService (sở hữu transaction)
  ├─ AccountRepository: đọc và cập nhật tài khoản A
  ├─ AccountRepository: cập nhật tài khoản B
  └─ LedgerRepository: ghi sổ giao dịch

Nếu mọi bước thành công: COMMIT
Nếu một bước thất bại: ROLLBACK toàn bộ
```

Nếu từng repository tự mở connection và commit riêng, có thể xảy ra tình huống tài khoản A đã bị trừ, tài khoản B chưa được cộng hoặc ledger chưa được ghi. Các bước nghiệp vụ vốn cần nguyên tử đã bị chia thành nhiều transaction độc lập.

Repository nên tập trung vào truy vấn và ánh xạ dữ liệu. Service hoặc application use case điều phối các repository trong một transaction chung. Với hệ thống có transaction manager, repository tham gia transaction hiện có thông qua cơ chế framework cung cấp.

## 4. Vòng đời transaction với JDBC thuần

JDBC cho phép ứng dụng quản lý transaction trực tiếp qua `Connection`.

Ở chế độ mặc định, connection thường có `autoCommit = true`: mỗi statement được thực thi như một transaction riêng và tự commit khi hoàn thành theo driver/database. Muốn nhóm nhiều statement thành một transaction, ứng dụng đặt `autoCommit` thành `false`, thực hiện các câu lệnh rồi gọi `commit()` hoặc `rollback()`.

Ví dụ:

```java
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
            insertLedger(connection, fromId, toId, amount);

            connection.commit();
        } catch (Exception ex) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                ex.addSuppressed(rollbackError);
            }
            throw new TransferException("Transfer failed", ex);
        }
    }
}
```

Điểm quan trọng:

- Cùng một `Connection` được truyền cho các thao tác để tất cả statement tham gia cùng transaction.
- Chỉ gọi `commit()` sau khi mọi bước bắt buộc thành công.
- Khi có lỗi, rollback transaction trước khi trả connection.
- `try-with-resources` bảo đảm `close()` được gọi cả khi có exception.
- Nếu rollback cũng thất bại, giữ lỗi rollback làm suppressed exception để không làm mất nguyên nhân ban đầu.

Trong code thực tế, nên bắt và phân loại exception phù hợp với chữ ký phương thức và chính sách retry. Không nên bắt `Throwable` rồi tiếp tục sử dụng connection có thể đã ở trạng thái không xác định.

### Không tự commit trong repository

Một repository JDBC có thể nhận connection từ service:

```java
public final class AccountRepository {
    public void debit(Connection connection,
                      long accountId,
                      BigDecimal amount) throws SQLException {
        String sql = """
            UPDATE accounts
            SET balance = balance - ?
            WHERE id = ? AND balance >= ?
            """;

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setBigDecimal(1, amount);
            statement.setLong(2, accountId);
            statement.setBigDecimal(3, amount);

            if (statement.executeUpdate() != 1) {
                throw new InsufficientFundsException();
            }
        }
    }
}
```

Repository không gọi `connection.commit()` hoặc `connection.close()`. Nó chỉ đóng statement do chính nó tạo. Service sở hữu connection và transaction nên quyết định commit/rollback và đóng connection sau cùng.

Truyền connection tường minh có thể hữu ích trong JDBC thuần để thể hiện quyền sở hữu. Ứng dụng cũng có thể đóng gói transaction trong một helper hoặc Unit of Work để tránh truyền connection qua quá nhiều tầng, miễn là ranh giới và trách nhiệm vẫn rõ ràng.

### Cẩn thận khi thay đổi autoCommit

Đặt `autoCommit` thành `false` trước khi bắt đầu nhóm statement cần transaction. Đừng tùy tiện đổi `autoCommit` giữa transaction: JDBC có thể commit transaction hiện tại khi chuyển từ `false` sang `true`, tùy driver và semantics được quy định. Khi dùng pool, phải khôi phục trạng thái connection trước khi trả về hoặc để pool quản lý việc reset.

Nếu một connection đã tham gia transaction do framework quản lý, code repository không được tự thay đổi `autoCommit`. Việc đó có thể phá vỡ transaction boundary của framework.

## 5. Trả connection về pool đúng cách

Connection mượn phải được trả lại dù transaction thành công hay thất bại. Trong JDBC thuần, `try-with-resources` là cách thông dụng:

```java
try (Connection connection = dataSource.getConnection()) {
    // Công việc database
}
```

Với connection pool, `close()` thường đóng logical handle và trả connection về pool. Không gọi API riêng của pool để đóng connection vật lý sau mỗi request.

Nếu transaction đang mở, phải kết thúc transaction trước khi trả connection. Nhiều pool cố gắng rollback transaction chưa commit khi connection được trả lại và reset trạng thái, nhưng không nên dựa vào hành vi tự cứu này như quy trình bình thường. Ứng dụng cần commit/rollback rõ ràng.

### Trạng thái session có thể tồn tại qua lần mượn

Một connection được tái sử dụng có thể mang trạng thái session nếu pool hoặc driver không reset đầy đủ. Các trạng thái có thể bao gồm:

- `autoCommit`.
- Isolation level.
- Read-only mode.
- Schema/catalog hiện tại.
- Session variables hoặc temporary settings.
- Transaction còn mở hoặc savepoint còn tồn tại.
- Network/socket timeout hoặc các thuộc tính riêng của driver.

Pool thường reset một số thuộc tính JDBC tiêu chuẩn khi trả connection, nhưng khả năng reset session-specific state phụ thuộc pool, driver và database. Nếu ứng dụng chạy `SET search_path`, `SET ROLE`, thay đổi timezone hoặc session variable, cần khôi phục trạng thái trong cùng phạm vi sử dụng hoặc cấu hình pool reset phù hợp.

Không dựa vào việc request tiếp theo sẽ nhận một connection sạch theo mọi nghĩa nếu ứng dụng đã thay đổi trạng thái session ngoài những thuộc tính pool biết cách reset.

## 6. Connection không an toàn để chia sẻ giữa nhiều thread

Một JDBC `Connection` thường có trạng thái transaction và session dùng chung. Nhiều thread cùng gọi SQL trên một connection có thể làm các thao tác xen kẽ trong cùng transaction, gây lỗi dữ liệu và hành vi khó dự đoán. JDBC không cung cấp bảo đảm chung rằng một connection có thể được dùng đồng thời an toàn bởi nhiều thread.

Ví dụ thiết kế nguy hiểm:

```java
@Component
public class SharedDatabaseClient {
    private Connection connection; // Không chia sẻ kiểu này giữa requests.
}
```

Nếu bean singleton chứa một connection và nhiều request gọi đồng thời, transaction của request A có thể bị trộn với câu lệnh của request B. Một request cũng có thể commit hoặc rollback transaction mà request khác đang dùng.

Thiết kế phù hợp hơn là giữ `DataSource` dùng chung (pool thread-safe), nhưng mỗi transaction mượn connection riêng:

```text
Request A -> mượn connection A -> transaction A -> trả connection A
Request B -> mượn connection B -> transaction B -> trả connection B
```

Không truyền connection của request A sang thread nền rồi tiếp tục dùng song song. Nếu công việc cần chạy bất đồng bộ, hãy thiết kế transaction mới trong thread/worker thực hiện công việc đó hoặc dùng cơ chế context propagation được framework hỗ trợ.

## 7. Ranh giới transaction trong Spring

Spring có thể quản lý transaction thông qua `PlatformTransactionManager` và annotation `@Transactional`. Trong ứng dụng imperative với JDBC/JPA, transaction manager điều phối transaction và thường gắn tài nguyên database với execution context hiện tại, phổ biến là thread hiện tại.

Một service có thể khai báo:

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderService(OrderRepository orders,
                        InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void confirmOrder(long orderId) {
        Order order = orders.findForUpdate(orderId);
        inventory.reserve(order.items());
        orders.markConfirmed(orderId);
    }
}
```

Khi method được gọi qua Spring proxy, transaction interceptor bắt đầu hoặc tham gia transaction theo propagation đã cấu hình. Các repository dùng cùng `DataSource` và tích hợp với Spring transaction manager có thể tham gia connection đã được bind cho transaction hiện tại.

Trong mô hình này:

- Service xác định ranh giới nghiệp vụ cần nguyên tử.
- Transaction manager bắt đầu, commit hoặc rollback transaction.
- Repository thực hiện truy vấn và tham gia transaction hiện tại.
- Ứng dụng không tự lấy một connection độc lập ngoài transaction manager cho các thao tác cần cùng transaction.

Nếu một repository tự gọi `dataSource.getConnection()` rồi thực hiện SQL ngoài cơ chế quản lý của Spring, nó có thể nhận một connection khác và thao tác đó không tham gia transaction mà service đang quản lý. Với JDBC trong Spring, dùng `JdbcTemplate` hoặc `DataSourceUtils`/cơ chế tích hợp tương ứng; với JPA, dùng `EntityManager` được quản lý bởi framework.

### @Transactional hoạt động qua proxy

Trong chế độ proxy phổ biến, lời gọi từ bên ngoài bean đi qua proxy để Spring áp dụng transaction advice. Gọi một method `@Transactional` khác bằng `this.someMethod()` trong cùng object thường là self-invocation và không đi qua proxy; annotation trên method được gọi có thể không tạo transaction boundary mới như kỳ vọng.

Ví dụ:

```java
public void process() {
    this.writeInTransaction(); // Có thể bỏ qua transaction proxy.
}

@Transactional
public void writeInTransaction() {
    // ...
}
```

Nếu cần một ranh giới transaction riêng, đặt logic vào bean khác và gọi qua proxy, hoặc dùng `TransactionTemplate`/API transaction tường minh. Cũng cần lưu ý method visibility, proxy type và cấu hình framework; không giả định annotation luôn được áp dụng cho mọi cách gọi.

## 8. Propagation và quyền sở hữu khi có transaction lồng nhau

Spring định nghĩa propagation để quyết định method được gọi xử lý thế nào khi đã có transaction hiện tại. Các chế độ thường gặp:

| Propagation | Hành vi khái quát |
|---|---|
| `REQUIRED` | Tham gia transaction hiện tại; nếu chưa có thì tạo transaction mới. Đây là mặc định phổ biến. |
| `REQUIRES_NEW` | Tạm đình chỉ transaction hiện tại và tạo transaction độc lập mới. |
| `SUPPORTS` | Tham gia nếu có transaction; nếu không thì chạy không transaction theo semantics của manager. |
| `MANDATORY` | Yêu cầu phải có transaction hiện tại; nếu không có thì báo lỗi. |
| `NOT_SUPPORTED` | Tạm đình chỉ transaction hiện tại và chạy không transaction. |
| `NEVER` | Yêu cầu không có transaction; nếu đang có thì báo lỗi. |
| `NESTED` | Nếu được hỗ trợ, dùng nested transaction thường dựa trên savepoint trong transaction hiện tại. |

### REQUIRED: cùng một đơn vị nguyên tử

```java
@Transactional
public void placeOrder() {
    paymentService.recordPayment(); // REQUIRED mặc định
    inventoryService.reserveStock(); // REQUIRED mặc định
}
```

Nếu cả hai method tham gia transaction hiện tại, thay đổi của chúng cùng commit hoặc rollback theo transaction ngoài. Method được gọi không tự sở hữu quyền commit độc lập.

### REQUIRES_NEW: transaction độc lập

`REQUIRES_NEW` đình chỉ transaction ngoài và dùng transaction mới. Nó hữu ích khi một thao tác phụ cần commit độc lập theo chủ đích, chẳng hạn lưu một bản ghi audit có thể tồn tại dù quy trình chính thất bại. Tuy nhiên, cần hiểu rõ hậu quả: transaction ngoài rollback không thể hoàn tác thay đổi đã commit trong transaction mới.

```java
@Transactional
public void processOrder() {
    orderRepository.markProcessing();
    auditService.recordAttemptInNewTransaction();
    throw new IllegalStateException("Fail main work");
}
```

Nếu audit method dùng `REQUIRES_NEW` và commit thành công, bản ghi audit có thể còn tồn tại dù transaction xử lý đơn bị rollback. Đó có thể là điều mong muốn nếu audit ghi nhận lần thử; nhưng không phù hợp nếu bản ghi được hiểu là “đơn đã xử lý thành công”.

`REQUIRES_NEW` cũng có thể cần thêm connection trong khi transaction ngoài vẫn giữ connection của nó. Nếu nhiều thread cùng giữ transaction ngoài rồi chờ transaction trong, pool nhỏ có thể cạn connection và tạo tình trạng chờ dây chuyền. Hãy tính pool capacity, số thread đồng thời và số tầng `REQUIRES_NEW`.

### NESTED và savepoint

`NESTED` thường dùng savepoint trong cùng transaction vật lý nếu transaction manager và driver hỗ trợ. Nó cho phép rollback một phần công việc về savepoint trong khi transaction ngoài có thể tiếp tục. Nó không tương đương với `REQUIRES_NEW`: nested transaction không commit độc lập ra database.

Không phải transaction manager nào cũng hỗ trợ nested semantics cho mọi loại resource. Hãy kiểm tra hỗ trợ thực tế trước khi dựa vào nó.

## 9. Rollback rules và exception trong Spring

Spring mặc định thường rollback khi method `@Transactional` kết thúc bằng `RuntimeException` hoặc `Error`. Checked exception không tự động làm rollback theo mặc định thông dụng; có thể khai báo `rollbackFor` nếu nghiệp vụ yêu cầu.

Ví dụ:

```java
@Transactional(rollbackFor = IOException.class)
public void importOrder() throws IOException {
    // Nếu IOException thoát khỏi method, transaction được rollback.
}
```

Nếu code bắt exception rồi không ném lại, transaction interceptor có thể thấy method kết thúc bình thường và commit. Vì vậy, cần quyết định rõ exception nào làm transaction thất bại:

```java
@Transactional
public void updateOrder() {
    try {
        repository.update();
    } catch (DataAccessException ex) {
        // Nếu chỉ log rồi nuốt lỗi, transaction có thể vẫn commit
        // hoặc đã bị đánh dấu rollback-only tùy loại lỗi/provider.
        throw ex;
    }
}
```

Một số lỗi persistence hoặc transaction manager có thể đánh dấu transaction `rollback-only`. Khi đó, dù code bắt exception và tiếp tục, lúc commit ngoài cùng có thể nhận `UnexpectedRollbackException`. Không nên coi việc bắt exception là cách khôi phục transaction đã hỏng.

Nếu cần xử lý lỗi và tiếp tục, hãy xác định liệu có thể rollback về savepoint hoặc chuyển phần công việc sang transaction riêng. Không tiếp tục dùng persistence context sau lỗi mà provider yêu cầu transaction kết thúc.

## 10. Transaction và thread/async boundary

Trong ứng dụng imperative của Spring, transaction resources thường được gắn với thread hiện tại. Khi code chuyển sang thread khác bằng `@Async`, `Executor`, `CompletableFuture` hoặc thread tự tạo, transaction hiện tại thường không tự động đi theo.

Ví dụ:

```java
@Transactional
public void createOrder() {
    orderRepository.insertOrder();

    CompletableFuture.runAsync(() ->
        orderRepository.insertAudit()
    );
}
```

`insertAudit()` có thể chạy trên thread khác, không tham gia transaction của `createOrder()`. Nếu transaction ngoài rollback, insert audit có thể vẫn commit riêng (tùy cách repository lấy connection và cấu hình). Điều này có thể tạo dữ liệu không nhất quán.

Nếu công việc bất đồng bộ cần chạy sau khi transaction commit, hãy phát một sự kiện sau commit hoặc ghi outbox trong transaction rồi để worker xử lý. Nếu công việc cần transaction riêng, hãy mở transaction mới trong worker/service được gọi trên thread đó.

Không truyền JDBC `Connection`, `EntityManager` hoặc transaction handle imperative qua thread để dùng song song. Hãy truyền dữ liệu/command cần xử lý, rồi để worker sở hữu connection và transaction của riêng nó.

### Reactive transaction khác imperative transaction

Trong reactive stack như Spring WebFlux với R2DBC, transaction context không dựa trên thread-local theo cùng cách imperative. Resource thường được gắn với Reactor Context và phải được duy trì qua reactive pipeline. Không nên áp dụng quy tắc thread-local một cách máy móc cho reactive transaction; dùng `TransactionalOperator` hoặc cơ chế reactive transaction manager, và giữ các thao tác trong cùng reactive chain/context.

Ví dụ dạng khái niệm:

```java
return transactionalOperator.transactional(
    orderRepository.insert(order)
        .then(inventoryRepository.reserve(order.items()))
);
```

Việc gọi `.subscribe()` lồng bên trong một transaction chain hoặc tách pipeline có thể làm công việc chạy ngoài transaction context dự kiến. Hãy để caller quản lý subscription và composition của pipeline.

## 11. Giới hạn thời gian và vòng đời connection

Các timeout liên quan đến database thường có mục đích khác nhau:

| Timeout | Giới hạn điều gì? |
|---|---|
| Connection acquisition timeout | Thời gian chờ mượn connection từ pool. |
| Connect timeout | Thời gian thiết lập kết nối vật lý tới database. |
| Socket/network timeout | Thời gian chờ hoạt động mạng hoặc phản hồi từ server theo driver. |
| Query/statement timeout | Thời gian tối đa cho một câu lệnh SQL. |
| Lock timeout | Thời gian chờ khóa không tương thích. |
| Transaction timeout | Ngân sách thời gian cho transaction theo framework/manager hỗ trợ. |
| Overall request deadline | Thời gian tổng mà caller chấp nhận cho cả request, gồm pool wait, SQL, retry và xử lý ứng dụng. |

Một query timeout không nhất thiết kết thúc transaction theo cùng một cách trên mọi driver. Một transaction timeout ở framework cũng có thể không hủy ngay câu JDBC đang bị treo nếu driver không hỗ trợ cancellation đúng cách. Cần phối hợp timeout ở pool, driver, database, transaction manager và tầng HTTP.

Đừng đặt mọi timeout bằng cùng một con số mà không xét thứ tự. Ví dụ, request deadline nên lớn hơn tổng thời gian có thể dùng cho database cộng phần xử lý response; connection acquisition timeout nên nhỏ hơn phần deadline còn lại; statement timeout phải đủ để query hợp lệ chạy nhưng không chiếm toàn bộ ngân sách request.

## 12. Connection leak và transaction leak

**Connection leak** xảy ra khi ứng dụng mượn connection nhưng không trả lại pool. **Transaction leak** xảy ra khi transaction không được kết thúc đúng lúc, giữ khóa hoặc snapshot lâu hơn dự kiến. Hai vấn đề thường đi cùng nhau nhưng không hoàn toàn giống nhau.

Nguyên nhân phổ biến:

- Không dùng `try-with-resources` hoặc `finally` trong JDBC thuần.
- Exception thoát ra trước khi `close()` được gọi.
- Bắt đầu transaction rồi chờ người dùng hoặc gọi HTTP trước khi commit.
- Tạo transaction trong async task nhưng không kết thúc khi task bị hủy.
- Repository mở connection riêng nhưng quên đóng.
- Tự quản lý connection trong khi framework cũng đang quản lý transaction.
- Giữ cursor/stream từ database mở quá lâu.

Triệu chứng có thể gồm:

- Pool active connections chạm mức tối đa.
- Số connection đang chờ tăng.
- Acquisition timeout xuất hiện.
- Database có session idle-in-transaction kéo dài.
- Khóa bị giữ lâu, transaction khác chờ hoặc deadlock tăng.
- Bộ nhớ tăng do result set/cursor hoặc entity context giữ dữ liệu.

Theo dõi pool metrics như active, idle, pending/waiting threads, acquisition time và usage duration. Bật leak detection threshold ở môi trường phù hợp để tìm stack trace nơi connection được mượn quá lâu. Leak detector thường chỉ cảnh báo connection vượt ngưỡng; nó không tự sửa vòng đời sai.

## 13. Không giữ transaction trong lúc gọi dịch vụ bên ngoài

Một anti-pattern thường gặp:

```java
@Transactional
public void placeOrder(Order order) {
    orderRepository.insert(order);
    paymentClient.charge(order); // Có thể mất vài giây hoặc timeout.
    inventoryRepository.reserve(order.items());
}
```

Trong lúc chờ payment service, transaction database vẫn có thể giữ connection, snapshot và khóa. Nếu dịch vụ ngoài chậm, nhiều transaction cùng chờ sẽ làm pool cạn và giảm throughput.

Một số cách thiết kế:

- Thực hiện bước chuẩn bị không cần transaction trước khi mở transaction.
- Dùng transaction ngắn để tạo order ở trạng thái chờ và ghi một command/outbox.
- Worker thực hiện gọi dịch vụ ngoài sau commit.
- Khi nhận kết quả, mở transaction mới và chuyển trạng thái bằng câu lệnh có điều kiện.
- Dùng idempotency key và saga/compensation nếu quy trình nhiều dịch vụ cần phục hồi.

Không phải quy trình nào cũng có thể rút gọn thành một transaction database. Khi có dịch vụ ngoài, cần mô hình hóa trạng thái trung gian và hành động bù trừ thay vì giữ một connection mở trong toàn bộ thời gian chờ mạng.

## 14. Một mẫu kiến trúc rõ quyền sở hữu

Mô hình sau giúp phân định trách nhiệm:

```text
HTTP Controller
    |
    v
Application Service  <--- sở hữu use case và transaction boundary
    |
    +---- OrderRepository
    |
    +---- InventoryRepository
    |
    +---- PaymentRecordRepository
    |
    +---- OutboxRepository
    |
    v
Transaction Manager / JDBC Connection
    |
    v
Database
```

Controller xác thực request và gọi use case. Application service xác định nhóm thay đổi cần nguyên tử. Repository không tự commit. Transaction manager hoặc code JDBC thuần quản lý connection, transaction và cleanup. Outbox worker chạy sau commit trong transaction riêng của nó.

Trong JDBC thuần, application service có thể dùng một `TransactionRunner` nhận callback và cung cấp connection trong phạm vi transaction. Trong Spring, service có thể dùng `@Transactional`, còn repository dùng các API tích hợp để tham gia transaction manager. Hai cách tiếp cận khác nhau về triển khai nhưng cùng cần ranh giới sở hữu rõ ràng.

## 15. Kiểm tra quyền sở hữu transaction khi debug

Khi một thay đổi bất ngờ không rollback hoặc connection pool bị cạn, hãy xác định:

1. Transaction bắt đầu ở method/use case nào?
2. Có bao nhiêu connection được mượn trong một request?
3. Các repository có tham gia cùng transaction manager không?
4. Có câu SQL nào tự mở connection độc lập không?
5. Ai gọi `commit`, `rollback` và `close`?
6. Có exception nào bị bắt rồi nuốt khiến transaction commit ngoài ý muốn không?
7. Có method `@Transactional` nào được gọi qua self-invocation không?
8. Có `REQUIRES_NEW` khiến cần thêm connection hoặc commit độc lập không?
9. Có thao tác async/reactive bị tách khỏi transaction context không?
10. Transaction có giữ connection khi chờ HTTP, message broker hoặc người dùng không?
11. Pool có reset isolation, autoCommit, readOnly và session state sau khi trả connection không?
12. Query, lock và transaction timeout có phù hợp với deadline request không?

Log nên có request/trace ID, transaction boundary, thời gian mượn connection, thời gian transaction, kết quả commit/rollback và lỗi cuối. Tránh log dữ liệu nhạy cảm hoặc credential. Khi điều tra production, kết hợp application log với pool metrics và session/transaction views của database.

## 16. Những lỗi thiết kế thường gặp

- **Mỗi repository tự lấy connection và commit:** một use case nhiều bước bị tách thành nhiều transaction, có thể để lại trạng thái một phần.
- **Đóng connection do framework quản lý:** có thể phá vỡ tài nguyên đang được transaction manager sử dụng. Hãy dùng API tích hợp của framework.
- **Không đóng connection JDBC thuần:** pool cạn dần vì connection không được trả lại.
- **Chia sẻ một connection giữa nhiều request/thread:** transaction và session state có thể bị trộn.
- **Giữ transaction trong lúc gọi HTTP:** connection và khóa bị giữ trong thời gian chờ dịch vụ ngoài.
- **Cho rằng `close()` luôn đóng socket:** với pool, nó thường trả handle về pool.
- **Tự đổi `autoCommit` trong transaction do framework quản lý:** có thể commit ngoài ý muốn hoặc làm transaction manager mất kiểm soát.
- **Cho rằng `@Transactional` áp dụng khi self-invocation:** proxy có thể bị bỏ qua.
- **Cho rằng transaction tự đi theo `CompletableFuture` hoặc thread mới:** imperative transaction thường gắn với thread/context hiện tại.
- **Dùng `REQUIRES_NEW` mà không tính pool:** outer transaction vẫn giữ connection trong lúc inner transaction cần connection khác.
- **Nuốt exception:** transaction có thể commit hoặc đã bị đánh dấu rollback-only, gây kết quả khó hiểu.
- **Dùng một timeout duy nhất cho mọi tầng:** request có thể vượt deadline hoặc query bị hủy quá sớm.

## 17. Cách thiết kế vòng đời kết nối và transaction

Khi triển khai một use case có truy cập database, hãy quyết định:

1. Thành phần nào sở hữu transaction boundary của use case?
2. Dữ liệu nào phải commit hoặc rollback cùng nhau?
3. Các repository sẽ tham gia transaction hiện tại bằng API nào?
4. Connection được lấy từ pool ở đâu và được trả lại ở đâu?
5. Mọi đường thoát do exception, timeout hoặc cancellation có rollback và cleanup không?
6. Có giữ connection trong lúc gọi dịch vụ ngoài hay chờ người dùng không?
7. Có chuyển thread hoặc reactive context không; transaction context được quản lý ra sao?
8. Có propagation `REQUIRES_NEW`/`NESTED` không và hậu quả về atomicity/pool capacity là gì?
9. Session state nào được thay đổi và ai khôi phục nó trước khi trả connection?
10. Acquisition, query, lock, transaction và request timeout có nằm trong ngân sách tổng không?
11. Metric nào giúp phát hiện connection leak, transaction dài và pool saturation?

Nếu một use case cần nhiều thao tác database cùng thành công, đặt transaction boundary ở application service hoặc transaction runner bao trùm toàn bộ các thao tác đó. Để một thành phần chịu trách nhiệm kết thúc transaction và giải phóng connection. Các repository chỉ thao tác dữ liệu trong phạm vi được giao; worker bất đồng bộ sở hữu transaction riêng; và các lời gọi bên ngoài không nên kéo dài thời gian giữ connection.

## 18. Kết luận

Connection đại diện cho phiên làm việc với database; transaction là đơn vị thay đổi dữ liệu cần commit hoặc rollback. Connection pool tái sử dụng kết nối vật lý, vì vậy `close()` trên handle đã mượn thường trả connection về pool. Ứng dụng phải hiểu rõ trạng thái session và không chia sẻ một connection có trạng thái giữa nhiều thread.

Quyền sở hữu transaction nên nằm ở ranh giới use case: code JDBC thuần chịu trách nhiệm lấy connection, bắt đầu transaction, commit/rollback và đóng connection; với Spring, transaction manager điều phối connection và transaction qua proxy/context, còn service xác định phạm vi nghiệp vụ và repository tham gia transaction hiện tại. Propagation, exception, async boundary và timeout đều ảnh hưởng đến quyền sở hữu này. Khi giữ transaction ngắn, cleanup mọi nhánh và không gọi dịch vụ ngoài trong lúc giữ connection, ứng dụng giảm được connection leak, pool exhaustion và các lỗi nhất quán do transaction bị chia cắt hoặc kéo dài.
