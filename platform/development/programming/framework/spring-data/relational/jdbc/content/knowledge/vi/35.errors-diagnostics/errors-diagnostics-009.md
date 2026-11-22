# Giao dịch không rollback, kết nối cạn và truy vấn bị treo trong Spring Data JDBC

## 1. Ba nhóm sự cố thường bị nhầm lẫn

Khi một request ghi dữ liệu gặp lỗi hoặc chạy quá lâu, biểu hiện ở tầng ứng dụng có thể giống nhau: request không hoàn tất, dữ liệu ở trạng thái không như mong đợi, hoặc các request khác bắt đầu chờ.

Tuy nhiên, ba nhóm sự cố sau có nguyên nhân khác nhau:

1. **Transaction không rollback:** câu SQL đã chạy nhưng thay đổi vẫn được commit dù use case thất bại.
2. **Connection pool cạn:** ứng dụng không lấy được JDBC connection từ pool để bắt đầu thao tác database.
3. **Truy vấn bị treo hoặc chậm:** ứng dụng đã có connection, nhưng statement chờ lock, chạy lâu, truyền quá nhiều dữ liệu hoặc gặp vấn đề ở driver/network.

Trước khi thay đổi timeout hoặc tăng kích thước pool, cần xác định request đang chờ ở giai đoạn nào.

| Triệu chứng | Nơi cần kiểm tra đầu tiên |
|---|---|
| Dữ liệu vẫn còn sau khi service ném lỗi | Rollback rule, proxy, transaction manager |
| Hikari báo timeout khi lấy connection | Active/idle/pending connections, connection leak, transaction dài |
| SQL log cho thấy statement bắt đầu nhưng không kết thúc | Database lock, query plan, driver và network |
| Nhiều request cùng chờ dù database ít query | Pool acquisition, connection giữ quá lâu hoặc thread bị block |
| Service báo thành công nhưng một phần dữ liệu không được ghi | Transaction boundary, nhiều DataSource hoặc side effect ngoài database |

## 2. Transaction không rollback: kiểm tra rollback rule trước

Theo mặc định của Spring transaction, một transaction được đánh dấu rollback khi method thoát ra với RuntimeException hoặc Error. Checked exception thường không làm rollback nếu không khai báo rollback rule.

Ví dụ:

~~~java
@Transactional
public void placeOrder(Order order) throws IOException {
    orders.save(order);

    throw new IOException("Không thể ghi dữ liệu phụ trợ");
}
~~~

Trong ví dụ này, IOException là checked exception. Nếu không có rollback rule khác, transaction có thể commit thay đổi của orders dù method ném exception ra caller.

Nếu nghiệp vụ yêu cầu checked exception cũng rollback:

~~~java
@Transactional(rollbackFor = IOException.class)
public void placeOrder(Order order) throws IOException {
    orders.save(order);

    throw new IOException("Không thể hoàn tất use case");
}
~~~

Có thể khai báo nhiều loại exception:

~~~java
@Transactional(rollbackFor = {
        IOException.class,
        ImportValidationException.class
})
public void importOrders(...) throws IOException, ImportValidationException {
    // ...
}
~~~

Cũng cần kiểm tra cấu hình noRollbackFor. Nếu exception được khai báo trong noRollbackFor, Spring có thể commit transaction ngay cả khi exception thoát ra ngoài.

### 2.1. Exception bị bắt rồi không ném lại

Một lỗi thường gặp là bắt exception để ghi log rồi kết thúc method bình thường:

~~~java
@Transactional
public void placeOrder(Order order) {
    orders.save(order);

    try {
        inventory.reserve(order.getProductId(), order.getQuantity());
    } catch (InventoryException ex) {
        log.error("Không thể giữ tồn kho", ex);
        // Method vẫn tiếp tục và kết thúc bình thường.
    }
}
~~~

Nếu exception không làm transaction bị đánh dấu rollback-only, method kết thúc bình thường và transaction có thể commit đơn hàng. Kết quả là order tồn tại dù thao tác giữ tồn kho thất bại.

Nếu hai thao tác phải cùng thành công, hãy ném lại exception phù hợp:

~~~java
@Transactional
public void placeOrder(Order order) {
    orders.save(order);

    try {
        inventory.reserve(order.getProductId(), order.getQuantity());
    } catch (InventoryException ex) {
        throw new OrderPlacementException(
                "Không thể tạo đơn hàng",
                ex
        );
    }
}
~~~

Nếu exception đã bị bắt nhưng một thao tác tham gia transaction đã đánh dấu transaction rollback-only, transaction ngoài có thể gặp UnexpectedRollbackException khi cố commit. Hãy tìm exception gốc trong log thay vì chỉ xử lý exception xuất hiện ở cuối.

## 3. @Transactional có thực sự được áp dụng không?

Trong cấu hình proxy mặc định, Spring áp dụng transaction interceptor khi một lời gọi từ bên ngoài đi qua proxy của bean. Chỉ thêm annotation vào method không bảo đảm method đó đang chạy trong transaction.

### 3.1. Self-invocation bỏ qua proxy

Ví dụ:

~~~java
@Service
public class ImportService {

    public void importAll(List<ImportRow> rows) {
        this.importChunk(rows);
    }

    @Transactional
    public void importChunk(List<ImportRow> rows) {
        // Ghi dữ liệu.
    }
}
~~~

Lời gọi this.importChunk() diễn ra bên trong cùng object, không đi qua Spring proxy. Trong proxy mode, annotation ở importChunk có thể không được áp dụng.

Có thể đặt transaction ở method entry được caller gọi qua proxy:

~~~java
@Service
public class ImportService {

    @Transactional
    public void importAll(List<ImportRow> rows) {
        // Các thao tác repository cùng nằm trong transaction này.
    }
}
~~~

Hoặc tách xử lý chunk sang một bean khác nếu mỗi chunk cần transaction riêng:

~~~java
@Service
public class ImportCoordinator {

    private final ImportChunkService chunks;

    public ImportCoordinator(ImportChunkService chunks) {
        this.chunks = chunks;
    }

    public void importAll(List<ImportRow> rows) {
        for (List<ImportRow> chunk : split(rows, 500)) {
            chunks.importChunk(chunk);
        }
    }
}

@Service
public class ImportChunkService {

    @Transactional
    public void importChunk(List<ImportRow> chunk) {
        // Lời gọi qua bean proxy mở hoặc tham gia transaction.
    }
}
~~~

### 3.2. Bean có do Spring quản lý không?

Các trường hợp sau có thể khiến transaction interceptor không chạy như dự kiến:

- Service được tạo bằng new thay vì được inject từ Spring context.
- Method được gọi trong quá trình khởi tạo bean trước khi proxy sẵn sàng.
- Transaction management chưa được bật trong cấu hình Spring thuần.
- Annotation được đặt trên một method không được proxy/interceptor áp dụng theo kiểu cấu hình đang dùng.
- Caller giữ reference tới target object thay vì proxy.

Hãy kiểm tra bean thực tế được inject và call path từ controller/service khác. Với ứng dụng Spring Boot thông thường, transaction auto-configuration thường đã được bật; với cấu hình Spring thuần, cần cấu hình transaction management và PlatformTransactionManager.

## 4. Nhiều repository có thật sự dùng chung transaction không?

Một transaction JDBC chỉ bao phủ các thao tác tham gia cùng transaction manager và resource phù hợp, thường là cùng DataSource.

Ví dụ service:

~~~java
@Service
public class CheckoutService {

    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public CheckoutService(
            OrderRepository orders,
            InventoryRepository inventory
    ) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void checkout(Order order) {
        orders.save(order);
        inventory.reserve(order.getProductId(), order.getQuantity());
    }
}
~~~

Nếu hai repository dùng cùng DataSource và transaction manager, các thao tác thường tham gia transaction do checkout mở.

Nếu chúng dùng hai DataSource hoặc hai transaction manager khác nhau, một @Transactional thông thường không tự tạo transaction phân tán cho cả hai database.

Khi có nhiều transaction manager, chỉ rõ manager phù hợp:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public void checkout(Order order) {
    // Các repository phải dùng đúng resource do manager này quản lý.
}
~~~

Nếu cần atomicity xuyên nhiều database, phải dùng cơ chế phân tán phù hợp hoặc thiết kế workflow có outbox/saga và thao tác bù trừ. Không giả định hai repository cùng được inject vào một service thì tự động rollback cùng nhau.

### 4.1. Propagation có thể làm dữ liệu tồn tại độc lập

Một method dùng Propagation.REQUIRES_NEW tạo transaction riêng. Transaction này có thể commit ngay cả khi transaction ngoài rollback.

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeIndependentAudit(AuditRecord record) {
    auditRepository.save(record);
}
~~~

Nếu thấy audit record còn tồn tại sau khi use case chính rollback, kiểm tra propagation của method ghi audit. Đây có thể là hành vi đã được cấu hình, không phải transaction manager bỏ sót rollback.

## 5. Connection pool cạn: ứng dụng không lấy được connection

Connection pool giữ một số JDBC connection để tái sử dụng. Khi một request cần truy cập database, nó mượn connection từ pool. Sau khi thao tác kết thúc và connection được trả lại, request khác có thể dùng connection đó.

Với HikariCP, nếu số connection đang được sử dụng đạt maximumPoolSize và không còn connection rảnh, lời gọi lấy connection sẽ chờ. Khi hết connectionTimeout, pool ném SQLException.

Một số nguyên nhân thường gặp:

- Transaction giữ connection quá lâu.
- Query bị block bởi lock hoặc chạy chậm.
- Code mở connection thủ công nhưng không đóng.
- ResultSet, Statement hoặc stream chưa được đóng.
- Gọi HTTP/email hoặc chờ công việc bên ngoài trong khi transaction vẫn mở.
- Nhiều request đồng thời vượt khả năng xử lý của database/pool.
- Một tác vụ giữ connection khi chờ thread hoặc tài nguyên khác.

### 5.1. Phân biệt timeout lấy connection với timeout chạy SQL

Hai loại timeout này có ý nghĩa khác nhau:

| Timeout | Đo khoảng chờ nào? | Cấu hình thường gặp |
|---|---|---|
| Connection acquisition timeout | Chờ pool cấp một connection | Hikari connectionTimeout |
| Query timeout | Thời gian JDBC statement được phép chạy | JdbcTemplate.setQueryTimeout hoặc Statement.setQueryTimeout |
| Transaction timeout | Giới hạn thời gian transaction | @Transactional(timeout = ...) |
| Lock timeout | Thời gian chờ database lock | Cấu hình riêng của database |
| Network/socket timeout | Thời gian chờ giao tiếp mạng/driver | Driver hoặc network configuration |

Nếu log báo không lấy được connection từ pool, tăng query timeout không giải quyết được nguyên nhân. Nếu statement đang chờ database lock, tăng connectionTimeout chỉ khiến request chờ lâu hơn trước khi báo lỗi.

## 6. Theo dõi HikariCP và connection pool

Spring Boot Actuator có thể cung cấp các metric cho DataSource. Các gauge JDBC cho biết số connection active, idle, maximum và minimum. HikariCP còn cung cấp metric riêng với prefix hikaricp.

Khi điều tra pool cạn, theo dõi:

- Active connections: số connection đang được mượn.
- Idle connections: số connection sẵn sàng được mượn.
- Maximum connections: giới hạn pool.
- Pending borrowers: số request đang chờ connection.
- Connection acquisition time: thời gian chờ mượn connection.
- Connection usage time: thời gian connection được giữ.

Một mẫu đáng chú ý:

~~~text
active connections = maximum pool size
idle connections   = 0
pending borrowers  > 0
~~~

Nếu trạng thái này kéo dài, request mới phải chờ connection. Tiếp theo cần xác định những request đang giữ connection làm gì: chạy query chậm, chờ lock, mở transaction quá lâu hay không đóng resource.

### 6.1. Cấu hình HikariCP để chẩn đoán

Ví dụ cấu hình:

~~~properties
spring.datasource.hikari.connection-timeout=30000
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.leak-detection-threshold=20000
~~~

Các giá trị trên chỉ minh họa cách cấu hình; không phải khuyến nghị dùng chung cho mọi ứng dụng.

- connection-timeout là thời gian tối đa chờ lấy connection từ pool.
- maximum-pool-size là số connection tối đa pool được phép giữ.
- leak-detection-threshold yêu cầu Hikari ghi log khi connection ở ngoài pool lâu hơn ngưỡng.

Leak detection chỉ cảnh báo một connection có vẻ bị giữ quá lâu. Nó không tự thu hồi connection đang được ứng dụng sử dụng. Một query hợp lệ nhưng chạy lâu cũng có thể tạo cảnh báo nếu ngưỡng quá thấp.

Đặt leak threshold cao hơn thời gian giữ connection bình thường và chỉ bật trong thời gian cần chẩn đoán nếu log quá nhiều.

### 6.2. Không tăng pool size một cách mù quáng

Tăng maximumPoolSize có thể giúp khi pool quá nhỏ so với tải, nhưng cũng có thể làm database chịu nhiều truy vấn đồng thời hơn và tăng lock contention.

Trước khi tăng pool:

1. Đo active/idle/pending.
2. Xác định thời gian giữ connection.
3. Tìm query hoặc transaction dài.
4. Kiểm tra giới hạn connection của database.
5. Đánh giá tải đồng thời mà database thực sự xử lý được.
6. Chỉ thay đổi pool size sau khi có số liệu.

Pool size là một phần của giới hạn concurrency toàn hệ thống, không phải nút tăng hiệu năng vô hạn.

## 7. Tìm connection leak trong code

Nếu dùng JdbcTemplate hoặc NamedParameterJdbcTemplate, Spring quản lý việc lấy và trả connection trong các thao tác JDBC thông thường.

Khi tự dùng JDBC API, phải đóng resource đúng cách:

~~~java
public List<Customer> loadCustomers(DataSource dataSource)
        throws SQLException {

    String sql = "SELECT id, name FROM customers";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql);
         ResultSet resultSet = statement.executeQuery()) {

        List<Customer> result = new ArrayList<>();

        while (resultSet.next()) {
            result.add(new Customer(
                    resultSet.getLong("id"),
                    resultSet.getString("name")
            ));
        }

        return result;
    }
}
~~~

Try-with-resources bảo đảm ResultSet, Statement và Connection được đóng khi thoát khỏi block, kể cả khi có exception.

Trong code tham gia Spring transaction, không tự mở connection độc lập nếu muốn thao tác dùng cùng transaction. Ưu tiên JdbcTemplate hoặc cơ chế lấy/giải phóng connection được Spring quản lý, chẳng hạn DataSourceUtils, theo đúng contract của transaction manager.

### 7.1. Stream và result set lớn

Một số API trả Stream để đọc dữ liệu theo luồng. Stream có thể giữ tài nguyên JDBC cho tới khi được đóng.

Ví dụ:

~~~java
try (Stream<Order> orders = aggregateTemplate.streamAll(Order.class)) {
    orders.forEach(this::process);
}
~~~

Nếu bỏ qua close, connection có thể tiếp tục bị giữ sau khi caller đã xử lý xong dữ liệu. Hãy dùng try-with-resources cho stream dựa trên JDBC.

### 7.2. Không giữ connection trong lúc gọi hệ thống bên ngoài

Ví dụ dễ gây cạn pool:

~~~java
@Transactional
public void register(Customer customer) {
    customers.save(customer);

    emailClient.sendWelcomeEmail(customer);
    paymentClient.verifyAccount(customer);
}
~~~

Trong lúc HTTP call chờ phản hồi, transaction có thể vẫn giữ connection và lock. Nếu dịch vụ ngoài chậm, nhiều request sẽ đồng thời giữ connection lâu hơn bình thường.

Giữ transaction tập trung vào các thao tác database cần atomic. Ghi outbox trong transaction rồi gửi thông báo ở worker sau commit nếu use case cần side effect đáng tin cậy.

## 8. Truy vấn bị treo: connection đã được cấp nhưng statement chưa hoàn tất

Nếu connection đã được cấp, cần tìm xem thời gian đang bị tiêu tốn ở đâu:

1. Database đang chờ lock.
2. Query đang chạy nhưng execution plan kém.
3. Query quét hoặc trả quá nhiều hàng.
4. JDBC driver đang chờ network/database response.
5. Ứng dụng đang đọc ResultSet quá chậm.
6. Transaction giữ lock và chờ một thao tác khác.

Một query nhìn như bị treo không nhất thiết là database không phản hồi. Nó có thể đang chờ một transaction khác giải phóng lock.

### 8.1. Lock wait

Ví dụ transaction A:

~~~sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 100;
-- Transaction A chưa commit.
~~~

Transaction B:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 100;
~~~

Transaction B có thể phải chờ transaction A nhả lock trên hàng inventory. Nếu A giữ transaction quá lâu, B và các request khác có thể bị block.

Các nguyên nhân phổ biến:

- Transaction mở lâu.
- Cập nhật nhiều hàng theo thứ tự khác nhau giữa các request.
- Có thao tác bên ngoài database trong transaction.
- Query cần lock nhiều hàng.
- Deadlock giữa các transaction cạnh tranh.

### 8.2. Xem query đang chờ trên PostgreSQL

PostgreSQL cung cấp pg_stat_activity và pg_blocking_pids để điều tra session đang hoạt động và session chặn nó.

Ví dụ:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS duration,
    query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start;
~~~

Để tìm session bị block và session đang block nó:

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.query AS blocked_query,
    blocker.pid AS blocker_pid,
    blocker.query AS blocker_query
FROM pg_stat_activity blocked
JOIN pg_stat_activity blocker
    ON blocker.pid = ANY(pg_blocking_pids(blocked.pid));
~~~

Các truy vấn này dành riêng cho PostgreSQL. Database khác có view và công cụ chẩn đoán lock riêng. Không chạy câu SQL PostgreSQL trên MySQL hoặc SQL Server mà không chuyển đổi.

## 9. Đặt timeout cho query và transaction

Không nên để một request chờ vô hạn khi statement có thể bị block hoặc chạy quá lâu.

### 9.1. Query timeout với JdbcTemplate

JdbcTemplate hỗ trợ setQueryTimeout, đơn vị là giây:

~~~java
@Bean
JdbcTemplate jdbcTemplate(DataSource dataSource) {
    JdbcTemplate jdbc = new JdbcTemplate(dataSource);
    jdbc.setQueryTimeout(5);
    return jdbc;
}
~~~

Giá trị mặc định là -1, nghĩa là không truyền query timeout cụ thể xuống JDBC driver. Driver có trách nhiệm thực thi timeout theo JDBC contract; hành vi thực tế cần được kiểm tra với driver/database đang dùng.

Nếu transaction đã có timeout, thời gian còn lại của transaction có thể ghi đè timeout được cấu hình trực tiếp trên JdbcTemplate.

### 9.2. Transaction timeout

Có thể đặt timeout cho use case:

~~~java
@Transactional(timeout = 10)
public void updateOrder(Long orderId) {
    // Các thao tác database của use case.
}
~~~

Transaction timeout giới hạn thời gian transaction theo khả năng của transaction manager. Với JDBC, timeout còn lại có thể được áp dụng lên statement do Spring quản lý.

Transaction timeout không đồng nghĩa với timeout lấy connection từ HikariCP, cũng không thay thế socket timeout hoặc lock timeout của database.

### 9.3. Lock timeout riêng của database

Một số database hỗ trợ cấu hình thời gian tối đa chờ lock. Ví dụ PostgreSQL có tham số lock_timeout và statement_timeout.

Các timeout này có phạm vi khác nhau:

- lock_timeout giới hạn thời gian chờ lock.
- statement_timeout giới hạn thời gian statement chạy.
- JDBC query timeout truyền yêu cầu timeout qua driver.
- transaction timeout áp dụng cho toàn bộ transaction.

Không đặt tất cả timeout cùng một con số mà không xem xét quan hệ giữa chúng. Hãy thiết kế để thao tác bị chặn có thể thất bại trong thời gian hữu hạn và ứng dụng có thể xử lý exception phù hợp.

## 10. Đọc thread dump và log để xác định điểm chờ

Khi request bị treo, thread dump có thể giúp xác định thread đang chờ ở tầng nào.

Một số dấu hiệu thường gặp:

| Stack trace / dấu hiệu | Khả năng |
|---|---|
| Thread đang ở HikariPool.getConnection | Đang chờ pool cấp connection |
| Thread ở PreparedStatement.execute hoặc driver socket read | Đã có connection, đang chờ statement/driver |
| Thread chờ monitor/lock trong code ứng dụng | Có thể bị khóa bởi synchronized/lock nội bộ |
| Thread đang đọc ResultSet hoặc map nhiều entity | Đang xử lý kết quả lớn |
| Thread đang chờ HTTP client trong khi transaction mở | Connection có thể bị giữ trong lúc gọi dịch vụ ngoài |

Thread dump chỉ là một ảnh chụp tại một thời điểm. Hãy lấy nhiều dump cách nhau một khoảng ngắn và đối chiếu với SQL log, database session và pool metrics.

Nếu thread liên tục ở cùng vị trí, đó là dấu hiệu mạnh hơn một stack trace đơn lẻ.

## 11. Phân biệt deadlock, lock wait và query chậm

| Loại sự cố | Biểu hiện | Cách điều tra |
|---|---|---|
| Lock wait | Statement chờ một transaction khác nhả lock | Xem blocking session và thời gian transaction |
| Deadlock | Database phát hiện chu trình chờ và hủy một transaction | Đọc SQLState/vendor code và deadlock report |
| Query chậm | Statement đang chạy, tiêu thụ CPU/I/O hoặc scan nhiều hàng | Xem execution plan, index, rows scanned |
| Connection pool starvation | Request không lấy được connection | Xem active/idle/pending và connection usage time |
| Network/driver wait | Statement đã gửi nhưng client chờ phản hồi | Kiểm tra driver logs, network timeout và database health |
| Result processing chậm | Database trả kết quả nhưng ứng dụng mất thời gian đọc/map | Xem rows returned, fetch size, mapping và heap |

Đừng sửa deadlock bằng cách chỉ tăng query timeout. Deadlock là xung đột thứ tự lock cần được xử lý bằng cách thống nhất thứ tự cập nhật, giảm transaction duration hoặc thiết kế retry có giới hạn.

## 12. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Service ném checked exception nhưng dữ liệu vẫn commit | Default rollback rule không rollback checked exception | Dùng rollbackFor khi nghiệp vụ yêu cầu |
| Bắt exception rồi method kết thúc bình thường | Transaction không được đánh dấu rollback-only | Ném lại exception hoặc chủ động đánh dấu rollback |
| @Transactional không có tác dụng khi method gọi nội bộ | Self-invocation bỏ qua proxy | Đặt transaction ở entry method hoặc tách bean |
| Repository khác không rollback cùng nhau | Khác DataSource/transaction manager | Dùng cùng resource hoặc thiết kế distributed workflow |
| Audit record còn sau rollback | Audit method dùng REQUIRES_NEW | Xác định rõ dữ liệu nào cần commit độc lập |
| Hikari báo connection timeout | Pool hết connection rảnh | Kiểm tra active, idle, pending và thời gian giữ connection |
| Leak detection cảnh báo liên tục | Connection bị giữ lâu hoặc resource chưa đóng | Kiểm tra stack trace lúc acquire và close resource |
| Pool hết connection khi stream dữ liệu | Stream/ResultSet chưa đóng | Dùng try-with-resources |
| Request chờ dù database ít hoạt động | Thread chờ pool hoặc chờ dịch vụ ngoài | Kiểm tra thread dump và connection acquisition |
| Query timeout không dừng request | Timeout không áp dụng ở tầng đang chờ hoặc driver không hỗ trợ như kỳ vọng | Phân biệt pool/query/lock/socket timeout và kiểm tra driver |
| Tăng maximumPoolSize nhưng database chậm hơn | Tạo quá nhiều concurrency và contention | Đo tải database, giảm transaction duration |
| Query bị treo do lock | Transaction khác chưa commit/rollback | Tìm blocking session và rút ngắn transaction |
| Deadlock xuất hiện ngẫu nhiên | Các transaction khóa hàng theo thứ tự khác nhau | Chuẩn hóa thứ tự cập nhật và retry có giới hạn |
| SQL chậm dù không bị lock | Execution plan hoặc index không phù hợp | Dùng EXPLAIN và đo rows scanned |
| Transaction giữ connection trong lúc gửi email | External I/O nằm bên trong transaction | Chuyển side effect ra sau commit hoặc dùng outbox |

## 13. Quy trình chẩn đoán theo thứ tự

Khi nhận được báo cáo “request ghi dữ liệu bị treo” hoặc “transaction không rollback”, hãy đi theo các bước:

1. Xác định request thất bại ở bước nào: trước khi lấy connection, khi execute SQL, khi đọc kết quả hay lúc commit.
2. Ghi nhận exception đầy đủ, bao gồm root cause, SQLState và vendor error code.
3. Kiểm tra transaction boundary, rollbackFor/noRollbackFor, self-invocation và transaction manager.
4. Kiểm tra pool metrics: active, idle, maximum, pending và acquisition time.
5. Bật leak detection tạm thời nếu nghi ngờ connection không được trả lại.
6. Lấy thread dump để phân biệt chờ pool, chờ driver hay xử lý ResultSet.
7. Kiểm tra session database, lock wait và blocking transaction.
8. Đo execution plan, số hàng đọc/trả về và thời gian statement.
9. Đặt query/transaction/lock timeout phù hợp với use case và driver.
10. Chạy lại kịch bản cạnh tranh và xác nhận dữ liệu, connection và lock được giải phóng đúng cách.

Hãy ghi lại thời điểm bắt đầu/kết thúc, request ID, transaction boundary và query fingerprint để liên kết log ứng dụng với session database.

## 14. Bài tập thực hành

### Bài 1 — Checked exception không rollback

Tạo service lưu Order rồi ném IOException. Quan sát dữ liệu sau lời gọi. Thêm rollbackFor và so sánh kết quả.

### Bài 2 — Exception bị nuốt

Tạo service lưu Order, bắt exception từ InventoryRepository rồi không ném lại. Xác nhận transaction có thể commit. Sau đó chuyển exception thành runtime exception và kiểm tra rollback.

### Bài 3 — Self-invocation

Tạo một service có method ngoài gọi method transactional bên trong bằng this. Quan sát transaction behavior, sau đó tách method vào bean khác và so sánh.

### Bài 4 — Connection pool nhỏ

Cấu hình pool nhỏ trong môi trường test, tạo nhiều request đồng thời giữ connection. Theo dõi active, idle, pending và connection acquisition timeout.

### Bài 5 — Connection leak

Viết một đoạn JDBC code mở connection nhưng không đóng. Bật leakDetectionThreshold và quan sát cảnh báo. Sửa bằng try-with-resources rồi chạy lại.

### Bài 6 — Query bị block bởi lock

Mở hai transaction trên cùng một hàng. Giữ transaction thứ nhất chưa commit, chạy UPDATE từ transaction thứ hai và quan sát lock wait trên database.

### Bài 7 — Query timeout

Đặt query timeout cho JdbcTemplate. Chạy một query cố ý chậm trong database test và quan sát exception. So sánh với connectionTimeout của HikariCP.

### Bài 8 — Transaction timeout

Đặt @Transactional(timeout = 5) cho use case có nhiều statement. Quan sát thời gian còn lại được áp dụng cho thao tác JDBC và so sánh với query timeout.

### Bài 9 — PostgreSQL lock diagnostics

Chạy hai transaction cạnh tranh cùng một hàng. Dùng pg_stat_activity và pg_blocking_pids để xác định session bị block và session chặn.

### Bài 10 — Pool metrics và tải đồng thời

Bật Spring Boot Actuator/Micrometer, theo dõi jdbc.connections và Hikari metrics trong một bài tải nhỏ. So sánh connection usage time trước và sau khi đưa HTTP call ra ngoài transaction.

## 15. Ghi nhớ

- Transaction không rollback thường liên quan đến rollback rules, exception bị bắt, proxy/self-invocation hoặc transaction manager/resource không đúng.
- Spring mặc định rollback với RuntimeException và Error; checked exception cần rollbackFor nếu nghiệp vụ yêu cầu.
- Trong proxy mode, self-invocation không đi qua transaction interceptor.
- Nhiều repository chỉ rollback cùng nhau khi chúng tham gia cùng transaction manager và resource phù hợp.
- Connection pool timeout là thời gian chờ mượn connection, không phải thời gian chạy SQL.
- Hikari leak detection chỉ cảnh báo connection bị giữ quá ngưỡng; nó không tự thu hồi connection.
- Theo dõi active, idle, maximum, pending và connection usage time để nhận diện pool starvation.
- Dùng JdbcTemplate hoặc try-with-resources để quản lý JDBC resource; đóng Stream khi API giữ resource.
- Truy vấn đã có connection nhưng bị treo có thể đang chờ lock, chạy query chậm, đọc nhiều dòng hoặc chờ driver/network.
- Phân biệt query timeout, transaction timeout, lock timeout, socket timeout và connection acquisition timeout.
- Không tăng pool size hoặc timeout trước khi xác định điểm chờ và nguyên nhân.
- Dùng thread dump, SQL log, database session/lock view và pool metrics cùng nhau để tìm nguyên nhân.

## Tài liệu tham khảo

- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)
- [Spring Boot — SQL Databases and Connection Pools](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
