# Mượn, sử dụng và hoàn trả kết nối đúng phạm vi

Kết nối cơ sở dữ liệu là một tài nguyên hữu hạn. Một request Java có thể cần đọc đơn hàng, cập nhật tồn kho hoặc ghi giao dịch, nhưng không nên giữ kết nối trong suốt thời gian người dùng mở trang, chờ HTTP API ngoài hoặc xử lý tệp lớn. Cũng không nên trả kết nối quá sớm khi transaction còn cần thực hiện nhiều câu SQL nguyên tử.

Trong chương **Kết nối và tài nguyên** của module **DATA_PERSISTENCE_FUNDAMENTALS**, bài học này tập trung vào vòng đời kết nối trong ranh giới persistence của Java: **mượn đúng lúc, sử dụng trong phạm vi công việc, hoàn tất hoặc rollback transaction, đóng các tài nguyên phụ thuộc và trả handle cho pool**. Khi quản lý đúng, ứng dụng tránh rò rỉ kết nối, cạn pool, giữ khóa quá lâu và xử lý sai sau lỗi mạng hoặc transaction.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt kết nối vật lý với handle kết nối được mượn từ pool.
- Xác định đúng chủ sở hữu vòng đời Connection, PreparedStatement và ResultSet.
- Viết JDBC với try-with-resources, xử lý đường thành công và lỗi mà không để rò rỉ tài nguyên.
- Đặt ranh giới transaction sao cho các câu SQL liên quan dùng cùng kết nối và được commit/rollback đúng.
- Hiểu khi nào Spring transaction manager chịu trách nhiệm mượn và hoàn trả kết nối.
- Tránh đưa ResultSet, Stream hoặc Connection đang mở ra ngoài phạm vi sở hữu.
- Phân biệt chờ lấy kết nối, chờ thực thi SQL, chờ khóa và chờ mạng; quan sát hiện tượng cạn pool.
- Đưa ra quyết định về timeout, số lượng kết nối và thử nghiệm lỗi phù hợp với tải thật.

## 2. Vòng đời kết nối: từ mượn đến trả

Khi dùng JDBC qua một DataSource có connection pool, thường có hai đối tượng cần phân biệt:

1. **Kết nối vật lý:** phiên làm việc giữa ứng dụng và DB server, có socket, authentication và trạng thái phiên. Tạo mới tương đối tốn kém.
2. **Handle logic:** đối tượng Connection mà ứng dụng nhận từ DataSource.getConnection(). Nó đại diện cho quyền sử dụng một kết nối trong một khoảng thời gian.

Với pool được cấu hình đúng, gọi Connection.close() trên handle logic **thường hoàn trả kết nối về pool** để request khác sử dụng; nó không nhất thiết đóng socket vật lý. Với DriverManager hoặc một DataSource không dùng pool, close() có thể thực sự đóng kết nối vật lý.

~~~mermaid
flowchart LR
    A["HTTP request / service"] -->|getConnection| B["Connection pool"]
    B -->|cho mượn handle| C["JDBC code"]
    C -->|SQL + ResultSet| D["Database"]
    C -->|close handle| B
    B -->|tái sử dụng hoặc loại bỏ| E["Kết nối vật lý"]
~~~

Sơ đồ minh họa đường đi tổng quát; chính pool hoặc framework quyết định lúc nào tạo, giữ, kiểm tra, hủy kết nối vật lý.

### 2.1. Phạm vi đúng là gì?

**Phạm vi sở hữu** là khoảng code cần sử dụng handle và chịu trách nhiệm dọn nó. Một operation đọc đơn giản có thể mượn kết nối ngay trước truy vấn và trả ngay sau khi ánh xạ ResultSet sang dữ liệu ứng dụng. Một transaction cần nhiều câu ghi phải giữ cùng kết nối từ BEGIN tới khi COMMIT hoặc ROLLBACK được xử lý.

| Nhu cầu | Phạm vi mượn hợp lý | Điểm cần tránh |
|---|---|---|
| SELECT một đơn | Mượn, query, map kết quả, trả | Trả ResultSet chưa đọc hết để tầng khác duyệt |
| INSERT một bản ghi autocommit | Mượn, thực thi SQL, trả | Giữ connection sau khi đã xong |
| Chuyển tiền qua hai UPDATE | Cùng một connection trong toàn transaction | Mỗi repository tự mượn connection độc lập rồi tưởng cùng transaction |
| Báo cáo nhiều SELECT cùng snapshot | Một transaction đọc có phạm vi rõ ràng | Giữ transaction quá lâu khi render PDF hoặc gọi mạng |
| Import theo lô | Chia thành batch và transaction hữu hạn | Giữ một transaction rất lớn, đầy bộ nhớ, chiếm connection kéo dài |
| HTTP call sang dịch vụ khác | Thông thường ngoài phạm vi giữ DB connection | Giữ kết nối và khóa DB trong khi chờ timeout HTTP |

**Không có quy tắc “một request HTTP luôn tương ứng một connection”.** Một request không truy cập DB có thể không cần kết nối; một request có nhiều bước có thể trải qua nhiều transaction; một transaction liên quan một DB cần được điều phối để các truy vấn thuộc đúng cùng ngữ cảnh.

## 3. Mẫu JDBC chuẩn: try-with-resources

Ví dụ truy vấn đơn hàng theo tenant để bảo vệ ranh giới dữ liệu nhiều tenant:

~~~java
public Optional<OrderSummary> findOrder(
        DataSource dataSource, long tenantId, long orderId
) throws SQLException {
    String sql = """
        SELECT id, status, total_amount
        FROM orders
        WHERE tenant_id = ? AND id = ?
        """;

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, tenantId);
        statement.setLong(2, orderId);

        try (ResultSet rs = statement.executeQuery()) {
            if (!rs.next()) {
                return Optional.empty();
            }

            OrderSummary order = new OrderSummary(
                rs.getLong("id"),
                rs.getString("status"),
                rs.getBigDecimal("total_amount")
            );

            return Optional.of(order);
        }
    }
}
~~~

Đặc điểm của mẫu:

- DataSource.getConnection() mượn connection khi method thực sự cần DB.
- PreparedStatement giữ tài nguyên phục vụ SQL và truyền tham số an toàn; không nối chuỗi từ dữ liệu đầu vào.
- ResultSet được đọc và ánh xạ khi Connection và PreparedStatement còn sống.
- try-with-resources tự đóng tài nguyên theo **thứ tự ngược với lúc mở**: ResultSet, PreparedStatement, Connection. Điều này áp dụng cả khi có return sớm hoặc exception.
- Method trả về một giá trị ứng dụng độc lập (OrderSummary), không trả JDBC resource đang mở.

### 3.1. Ai đóng cái gì?

| Tài nguyên | Ai tạo/mượn trong ví dụ? | Ai đóng/trả? |
|---|---|---|
| Connection | Method gọi DataSource.getConnection() | try-with-resources của method |
| PreparedStatement | Method gọi connection.prepareStatement() | try-with-resources |
| ResultSet | Method gọi statement.executeQuery() | try-with-resources lồng bên trong |
| OrderSummary | Method ánh xạ từ ResultSet | Đối tượng Java thông thường, không giữ JDBC resource |

Cần thiết lập **một chủ sở hữu rõ ràng** cho việc đóng kết nối. Nếu một method nhận Connection do caller truyền, method đó nên coi Connection là tài nguyên **được mượn từ caller**, không tự đóng nếu hợp đồng không chỉ định nó chuyển quyền sở hữu.

### 3.2. Method nhận Connection từ transaction bên ngoài

~~~java
public void addAuditRecord(
        Connection connection, UUID orderId, String action
) throws SQLException {
    String sql = """
        INSERT INTO order_audit(order_id, action)
        VALUES (?, ?)
        """;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setObject(1, orderId);
        statement.setString(2, action);
        statement.executeUpdate();
    }
    // KHÔNG close connection: caller sở hữu transaction.
}
~~~

Nhờ vậy, caller có thể phối hợp INSERT order và INSERT audit trong **cùng transaction**. Repository phụ trách tài nguyên nó tạo ra (statement) nhưng giữ nguyên quyền sở hữu connection của transaction coordinator.

### 3.3. Đường lỗi phải dọn tài nguyên như đường thành công

Nếu executeQuery(), rs.next() hoặc code ánh xạ dữ liệu ném exception, try-with-resources vẫn cố đóng các tài nguyên. Khi cả thao tác chính và close() cùng gây lỗi, Java giữ lỗi chính và gắn lỗi khi close vào danh sách **suppressed exceptions**. Điều đó hữu ích khi điều tra incident.

Không viết code chỉ close trong nhánh thành công. Một lỗi parse dữ liệu hiếm gặp có thể làm rò rỉ tài nguyên ở đúng lúc tải đang cao.

## 4. Những kiểu rò rỉ hoặc dùng sai Connection

### 4.1. Không close khi truy vấn lỗi

~~~java
// Mẫu sai: nếu executeQuery ném lỗi thì close không chạy.
Connection connection = dataSource.getConnection();
PreparedStatement ps = connection.prepareStatement(sql);
ResultSet rs = ps.executeQuery();
process(rs);
connection.close();
~~~

Sửa bằng try-with-resources, tách rõ ownership và không cần lặp nhiều lệnh close ở từng nhánh return.

### 4.2. Trả ResultSet đang sống ra khỏi repository

~~~java
// Mẫu sai về vòng đời.
public ResultSet search(DataSource dataSource) throws SQLException {
    try (Connection c = dataSource.getConnection();
         PreparedStatement p = c.prepareStatement("SELECT id FROM orders")) {
        return p.executeQuery();
    }
}
~~~

Khi method return, PreparedStatement và Connection đã đóng. ResultSet phụ thuộc vào chúng có thể không đọc được nữa. Nếu giữ connection sống để ResultSet tiếp tục đọc, lại làm mờ ownership và tăng nguy cơ leak.

**Giải pháp:** map kết quả vào DTO trong scope, hoặc thiết kế callback/stream có ownership rõ ràng và lifecycle được tầng gọi quản lý chặt chẽ.

### 4.3. Lưu Connection trong singleton hoặc field của service

~~~java
// Mẫu sai: một instance service có thể phục vụ nhiều thread.
@Service
public class BrokenOrderService {
    private Connection sharedConnection;

    public void init(DataSource dataSource) throws SQLException {
        sharedConnection = dataSource.getConnection();
    }
}
~~~

Connection JDBC có trạng thái phiên và transaction, không nên được chia sẻ tùy tiện giữa nhiều request/thread. Một service singleton giữ connection lâu làm mất lợi ích pool, có thể bị ngắt do idle timeout, gây lẫn trạng thái và phá cô lập transaction.

**Giữ DataSource hoặc JdbcTemplate ở field của service; lấy connection theo operation/transaction.**

### 4.4. Gọi close quá sớm

~~~java
// Mẫu sai nếu nghiệp vụ cần một transaction nguyên tử.
public void createOrder(...) {
    insertOrderUsingOwnConnection(...);
    insertAuditUsingAnotherConnection(...);
}
~~~

Nếu mỗi hàm tự mượn connection với autocommit=true, INSERT đầu có thể đã commit còn INSERT sau thất bại. Dù tất cả connection được đóng đúng, **transaction boundary vẫn sai**.

Cần coordinator tạo transaction và truyền cùng connection cho hai bước, hoặc dùng Spring transaction manager để các thao tác qua cơ chế hỗ trợ tham gia cùng transaction.

### 4.5. Giữ Connection quá lâu

~~~text
Mượn connection
  -> SELECT kiểm tra tồn kho
  -> gọi HTTP API thanh toán trong 30 giây
  -> cập nhật database
  -> commit
  -> trả connection
~~~

Connection bị chiếm trong cả thời gian chờ mạng, có thể giữ snapshot/lock từ các câu SQL trước. Khi nhiều request cùng thực hiện, pool nhanh chóng cạn dù DB thực tế chưa hết khả năng xử lý SQL.

Nên thiết kế trạng thái nghiệp vụ, transaction ngắn và idempotency/outbox nếu có nhiều tài nguyên bên ngoài. Không thể giải quyết vấn đề bằng cách chỉ tăng maximumPoolSize.

## 5. Transaction và quyền sở hữu kết nối

Một transaction JDBC cần ranh giới rõ: BEGIN hoặc tắt autocommit, thực thi các câu SQL, COMMIT hoặc ROLLBACK và giải phóng handle.

~~~java
public void transfer(
        DataSource dataSource, long fromId, long toId, BigDecimal amount
) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            try (PreparedStatement debit = connection.prepareStatement(
                    """
                    UPDATE accounts
                    SET balance = balance - ?
                    WHERE id = ? AND balance >= ?
                    """)) {
                debit.setBigDecimal(1, amount);
                debit.setLong(2, fromId);
                debit.setBigDecimal(3, amount);

                if (debit.executeUpdate() != 1) {
                    throw new IllegalStateException("Insufficient balance");
                }
            }

            try (PreparedStatement credit = connection.prepareStatement(
                    """
                    UPDATE accounts
                    SET balance = balance + ?
                    WHERE id = ?
                    """)) {
                credit.setBigDecimal(1, amount);
                credit.setLong(2, toId);

                if (credit.executeUpdate() != 1) {
                    throw new IllegalStateException("Receiver not found");
                }
            }

            connection.commit();
        } catch (SQLException | RuntimeException ex) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                ex.addSuppressed(rollbackFailure);
            }
            throw ex;
        }
    }
}
~~~

Ví dụ giả định số tiền dương, fromId khác toId, DataSource cung cấp kết nối thích hợp và bảng có các ràng buộc nghiệp vụ cần thiết. Trong hệ thống thực tế, phải xác thực amount, kiểm soát đồng thời, ghi audit/idempotency, bảo vệ trước chuyển tiền lặp và xử lý riêng **kết quả COMMIT chưa rõ** nếu mất kết nối.

Ở ví dụ này, việc đóng Connection khi rời try-with-resources được thực hiện bất kể thành công hay lỗi. Với pool chuẩn, handle được trả hoặc connection hỏng bị loại bỏ theo chính sách pool. **Không đồng nhất close với commit**. Khi giao dịch có thể đã commit nhưng ACK mất, gọi rollback trong catch không chứng minh tiền chưa chuyển; phải xác minh qua business key hoặc transaction ID phù hợp.

### 5.1. Các nhánh kết thúc cần phân biệt

| Kết thúc | Hành động | Hệ quả |
|---|---|---|
| Các bước ghi hoàn tất | COMMIT | Giao dịch được DB xác nhận theo cấu hình durability |
| Lỗi nghiệp vụ trước commit | ROLLBACK | Bỏ thay đổi chưa commit, trả connection |
| Lỗi SQL trước commit | ROLLBACK nếu kết nối còn dùng được | Có thể cần xử lý connection hỏng |
| Mất kết nối trong COMMIT | Kết quả có thể chưa rõ | Không retry nghiệp vụ không idempotent với ID mới |
| Client hủy request | Cần đảm bảo transaction kết thúc và handle được trả | Hủy request không đồng nghĩa DB tự rollback ngay |
| Pool quyết định loại bỏ connection | Đóng kết nối vật lý hoặc làm sạch theo chính sách | Tránh trao một connection lỗi cho borrower tiếp theo |

### 5.2. Trạng thái autocommit và kết nối tái sử dụng

JDBC thường dùng autocommit cho kết nối mới nếu chưa cấu hình khác. Khi ứng dụng tắt autocommit, nó thay đổi trạng thái phiên; các borrower sau không được vô tình nhận lại connection với transaction đang dang dở hoặc autocommit sai.

Một pool trưởng thành thường phát hiện và khôi phục **các trạng thái JDBC mà nó theo dõi** khi trả handle, và cố gắng xử lý transaction chưa hoàn tất. Không vì vậy mà tin rằng mọi thay đổi trạng thái phiên đều được tự động reset: lệnh SQL tùy ý như SET ROLE, SET search_path, đặt biến phiên, tạo temporary table hoặc advisory lock có thể cần quy tắc cleanup riêng tùy DB và pool.

Với JDBC tự quản lý không có pool, người gọi chịu trách nhiệm với trạng thái kết nối mình sở hữu. Nếu cần reset autocommit thủ công, phải đảm bảo transaction đã commit/rollback trước đó; chuyển autocommit về true khi transaction đang mở có thể làm transaction **commit ngầm** theo hợp đồng JDBC. Khi rollback/connection gặp lỗi không rõ, an toàn hơn là loại bỏ connection không đáng tin cậy, không tiếp tục chia sẻ cho request khác.

## 6. Spring quản lý Connection qua transaction manager

Trong Spring, JdbcTemplate dùng cơ chế quản lý tài nguyên tích hợp, và DataSourceTransactionManager hoặc JdbcTransactionManager có thể liên kết một connection với transaction trong thread thực thi.

~~~java
@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        int debited = jdbc.update(
            """
            UPDATE accounts
            SET balance = balance - ?
            WHERE id = ? AND balance >= ?
            """,
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("Debit failed");
        }

        int credited = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalStateException("Credit failed");
        }
    }
}
~~~

Với cùng DataSource và transaction manager phù hợp, các thao tác JdbcTemplate tham gia cùng transaction. Framework chịu trách nhiệm commit/rollback và hoàn trả connection khi transaction hoàn tất. Cấu hình JDBC và DataSource phải nhất quán; annotation trên service không tự kết hợp hai DataSource khác nhau thành một transaction.

**Trong method dùng @Transactional và JdbcTemplate, không cần tự gọi DataSource.getConnection() rồi close handle bằng tay.** Dùng JdbcTemplate hoặc DataSourceUtils theo đúng cơ chế Spring để tham gia transaction đang được quản lý. Nếu tự mở một connection raw từ DataSource bên ngoài cơ chế transaction-aware, rất dễ thực thi SQL ngoài transaction dự kiến.

### 6.1. Những điểm về Spring transaction boundary

- Một method có @Transactional được gọi qua proxy và tạo transaction mới có thể mượn connection ở bước framework bắt đầu transaction hoặc khi lần đầu thực sự cần SQL, tùy transaction manager và cấu hình. Đừng suy thời điểm mượn chỉ từ vị trí annotation.
- Method tự gọi bằng this.someMethod() trong cùng bean có thể bỏ qua proxy, khiến transaction khai báo không được kích hoạt như dự định.
- Một method với propagation REQUIRED tham gia transaction sẵn có sẽ sử dụng ranh giới của transaction bên ngoài; nó không tự commit và trả connection khi return.
- REQUIRES_NEW có thể yêu cầu connection khác trong lúc transaction ngoài vẫn giữ connection. Khi nhiều thread cùng làm việc, cấu hình pool quá nhỏ có thể làm các transaction chờ lẫn nhau.
- Với JPA, EntityManager và transaction manager cũng kiểm soát tài nguyên; entity được lazy load sau khi scope đóng có thể gặp lỗi hoặc khiến phạm vi sử dụng connection kéo dài nếu cấu hình giữ session mở.
- Một transaction qua thread/async boundary không tự động chia sẻ connection; đừng chuyền một Connection đang mượn sang Executor hoặc @Async.

### 6.2. Phân biệt scope transaction với scope HTTP request

Ví dụ:

~~~text
POST /orders
  -> parse và xác thực input
  -> gọi service @Transactional
       -> mượn connection / transaction
       -> INSERT order + outbox
       -> COMMIT / ROLLBACK
       -> hoàn trả connection
  -> build response JSON
  -> HTTP response
~~~

Ranh giới DB nên đủ hẹp để không giữ connection khi xây dựng response, render trang hay gọi API bên ngoài. Nhưng cũng cần đủ rộng để những thay đổi bắt buộc cùng thành công được commit nguyên tử.

Không đặt @Transactional trên một controller lớn chứa cả upload file, HTTP request và lệnh SQL nếu không có lý do nghiệp vụ cụ thể.

## 7. ResultSet, Stream và xử lý lazy: tài nguyên sống lâu hơn bạn tưởng

Một lỗi phổ biến không nằm ở việc quên close rõ ràng, mà ở việc dữ liệu được xử lý **sau** khi scope chứa connection đã kết thúc.

### 7.1. Không trả Stream phụ thuộc JDBC ra ngoài

~~~java
// Ý tưởng sai: giữ ResultSet sống để caller duyệt sau.
public Stream<Order> streamOrders() {
    // Trả Stream mà việc đọc phụ thuộc ResultSet/Connection mở.
    // Caller quên close Stream -> Connection có thể không được trả.
    // Scope repository đã đóng -> Stream có thể thất bại khi duyệt.
}
~~~

Một Stream lazy có thể chỉ thực sự truy vấn/đọc dữ liệu khi caller gọi forEach(), collect() hoặc iterator(). Nếu method mở connection trước rồi trả stream, ai sẽ đóng nó khi caller không tiêu thụ hết, gặp exception hay bỏ ngang?

Cách an toàn nhất cho tập kết quả vừa phải là materialize danh sách DTO trong phạm vi query:

~~~java
public List<OrderSummary> findRecentOrders(
        DataSource dataSource, long tenantId, int limit
) throws SQLException {
    String sql = """
        SELECT id, status, total_amount
        FROM orders
        WHERE tenant_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """;

    try (Connection c = dataSource.getConnection();
         PreparedStatement ps = c.prepareStatement(sql)) {
        ps.setLong(1, tenantId);
        ps.setInt(2, limit);

        try (ResultSet rs = ps.executeQuery()) {
            List<OrderSummary> result = new ArrayList<>();
            while (rs.next()) {
                result.add(new OrderSummary(
                    rs.getLong("id"),
                    rs.getString("status"),
                    rs.getBigDecimal("total_amount")
                ));
            }
            return result;
        }
    }
}
~~~

Với tập kết quả lớn, không nên đọc toàn bộ vào bộ nhớ. Thay vào đó, dùng **phân trang/keyset pagination** hoặc API callback thực thi toàn bộ vòng lặp tiêu thụ **bên trong scope tài nguyên**. Nếu framework hỗ trợ streaming, hợp đồng cần yêu cầu caller đóng Stream trong một scope có transaction còn hiệu lực, và không truyền Stream đó sang thread/request khác.

### 7.2. Server-side cursor, fetch size và transaction

Cursor và cơ chế fetch theo lô giúp giảm bộ nhớ client, nhưng có thể **giữ connection, transaction hoặc server-side resource** trong suốt quá trình đọc. Một chương trình xuất hàng triệu bản ghi ra CSV rồi ghi trực tiếp lên network chậm có thể giữ connection hàng phút/hàng giờ.

Với PostgreSQL JDBC, khả năng cursor/fetch theo lô phụ thuộc cấu hình, chẳng hạn fetchSize và autocommit phù hợp. Không khẳng định chỉ cần setFetchSize là driver chắc chắn tạo server-side cursor trong mọi tình huống.

Thay vì để connection treo khi upload CSV, có thể xử lý thành từng lô hữu hạn, lưu checkpoint và tách bước đọc DB khỏi bước tải dữ liệu ra mạng. Cần đánh giá yêu cầu snapshot nhất quán nếu báo cáo phải thấy toàn bộ dữ liệu ở cùng một thời điểm.

### 7.3. Async, CompletableFuture và thread khác

Không chuyền Connection hoặc ResultSet đang mượn sang một CompletableFuture chạy trên thread khác rồi trả ngay ở thread gốc. Khi scope gốc kết thúc, handle có thể đã được trả cho pool trong lúc thread khác vẫn sử dụng, tạo race nguy hiểm.

~~~java
// Sai: callback bất đồng bộ giữ handle ngoài scope mượn.
try (Connection c = dataSource.getConnection()) {
    executor.submit(() -> queryUsing(c));
}
// Scope này đóng c khi task có thể vẫn đang chạy.
~~~

Tác vụ nền nên có **scope mượn riêng** trên thread thực thi hoặc nhận dữ liệu DTO đã được materialize; nếu cần transaction, tạo transaction trong task đó thông qua cơ chế được hỗ trợ. Không giả định Spring transaction thread-bound tự đi theo @Async.

## 8. Timeouts: biết đang chờ điều gì

Cùng một thông báo “timeout” có thể đến từ nhiều chỗ khác nhau. Chẩn đoán sai sẽ dẫn tới tăng pool vô ích hoặc retry khi transaction chưa rõ kết quả.

| Loại timeout | Đang chờ | Hướng xử lý |
|---|---|---|
| Pool acquisition timeout | Chờ một connection rảnh từ pool | Kiểm tra active, idle, pending, hold time, leak, pool size |
| Connect timeout | Mở socket hoặc handshake tới DB | Kiểm tra mạng, DNS, DB endpoint, authentication, giới hạn kết nối |
| Query/statement timeout | Một câu SQL thực thi quá thời hạn | Kiểm tra plan, lock, dữ liệu, chỉ mục và thời gian query |
| Lock timeout | Câu lệnh chờ lock quá lâu | Xem transaction dài, thứ tự khóa và contention |
| Transaction timeout | Toàn transaction vượt deadline | Rút ngắn scope, tách tác vụ lâu, xử lý rollback |
| Socket/read timeout | Chờ phản hồi qua mạng quá lâu | Phân biệt lỗi mạng với DB đã thực hiện yêu cầu |
| Request deadline | HTTP client ngừng chờ | Không suy ra JDBC transaction đã rollback |
| Idle connection timeout | Connection không được sử dụng một thời gian | Kiểm tra cấu hình pool và thiết bị mạng |

**Đối chiếu deadline theo tầng.** Nếu HTTP request hết hạn trong 2 giây nhưng câu SQL được phép chạy 60 giây, DB có thể tiếp tục xử lý sau khi client đã bỏ cuộc. Khi tác vụ có khả năng ghi, kết quả từ phía client có thể không rõ; retry phải bảo đảm idempotency.

### 8.1. Query timeout trong JDBC

~~~java
try (Connection c = dataSource.getConnection();
     PreparedStatement ps = c.prepareStatement(
         "SELECT id FROM orders WHERE tenant_id = ?")) {
    ps.setLong(1, tenantId);
    ps.setQueryTimeout(3); // Đơn vị giây theo API JDBC.

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            consumeId(rs.getLong(1));
        }
    }
}
~~~

setQueryTimeout yêu cầu driver áp dụng giới hạn cho execution của statement theo khả năng hỗ trợ. Nó **không phải timeout để mượn connection từ pool**, không bảo đảm DB đã dừng ngay tại thời điểm client ngừng chờ, và không tự xác định kết quả commit của một transaction khác.

### 8.2. HikariCP: tham số cấu hình minh họa

~~~java
HikariConfig config = new HikariConfig();
config.setJdbcUrl(jdbcUrl);
config.setUsername(dbUser);
config.setPassword(dbPassword);

config.setMaximumPoolSize(20);
config.setConnectionTimeout(2_000); // Chờ mượn tối đa 2 giây.
config.setPoolName("orders-pool");

HikariDataSource dataSource = new HikariDataSource(config);
~~~

Đây là ví dụ cú pháp, **không phải khuyến nghị mọi ứng dụng nên có 20 kết nối và 2 giây timeout**. Cần chọn dựa trên số instance, giới hạn DB, công việc mỗi transaction và mức tải. Trong ứng dụng thực tế, quản lý vòng đời HikariDataSource ở cấp ứng dụng/framework; khi shutdown phải đóng pool theo hợp đồng, không tạo một pool mới cho từng request.

Cần hiểu thêm maxLifetime, keepaliveTime và idleTimeout tùy phiên bản/cấu hình; đặt maxLifetime phù hợp với giới hạn từ DB hoặc thiết bị mạng thay vì sao chép một giá trị tùy ý. Bảo mật credentials qua hệ thống quản lý secret, không hard-code trong source.

## 9. Kích thước pool, throughput và thời gian giữ kết nối

Pool size là giới hạn số connection có thể được **mượn đồng thời** từ một pool. Nó không phải số request HTTP được phép vào hệ thống và không phải mục tiêu phải sử dụng hết mọi lúc.

Nếu một request giữ connection lâu vì chờ mạng, việc tăng kích thước pool có thể chỉ khiến nhiều transaction cùng giữ tài nguyên, tăng lock contention và đẩy DB tới giới hạn kết nối.

### 9.1. Những yếu tố quyết định kích thước pool

- Số request có phần công việc DB đồng thời thực sự.
- Thời gian mỗi request giữ connection, gồm thời gian chờ khóa hoặc chạy nhiều query.
- Số application instance/worker, số pool trên mỗi instance, background jobs và connection của công cụ quản trị.
- Giới hạn max_connections của DB, bộ nhớ/CPU và workload giữa các ứng dụng cùng dùng DB.
- Latency và throughput mục tiêu, thời gian chờ mượn được chấp nhận, và chính sách backpressure.

**Tổng kết nối tiềm năng** phải được tính trên toàn bộ instance cùng các pool khác và những client khác. Cấu hình 30 connection trên mỗi instance không có cùng ý nghĩa khi chạy 2 hay 50 instance.

### 9.2. Metrics nên theo dõi đồng thời

| Metric | Câu hỏi |
|---|---|
| Active / in-use connections | Có bao nhiêu handle đang được mượn? |
| Idle connections | Có connection sẵn để phục vụ không? |
| Pending threads / waiters | Có bao nhiêu yêu cầu đang chờ mượn? |
| Acquisition wait time p50/p95/p99 | Thời gian chờ trước khi nhận connection là bao lâu? |
| Usage / hold time | Một handle được giữ trung bình và ở p95 bao lâu? |
| Connection creation / validation failures | Có lỗi mạng, credentials hay endpoint? |
| Timeout count | Pool không đáp ứng được trong deadline bao nhiêu lần? |
| DB active queries / lock waits | Connection được mượn đang chạy SQL hay chỉ giữ khi chờ? |
| DB transaction age | Có transaction bỏ quên hoặc rất dài? |
| Request latency và throughput | Người dùng thực tế bị ảnh hưởng thế nào? |

Cùng mức active=maximumPoolSize nhưng có hai nguyên nhân khác nhau: database đang xử lý nhiều truy vấn cần thiết, hoặc code đang giữ nhiều connection lúc không dùng. Phải đối chiếu với số query DB đang chạy, lock wait và thời gian hold trước khi thay đổi cấu hình.

### 9.3. Dấu hiệu pool đang cạn

~~~text
08:12:01 API latency p95 tăng
08:12:02 Pool active đạt maximum, idle = 0
08:12:02 Pending threads tăng
08:12:04 Nhiều getConnection() timeout
08:12:05 CPU DB vẫn không cao
~~~

Đây là dấu hiệu cần điều tra **connection hold time**, query bị chờ lock, công việc ngoài DB nằm trong transaction, tác vụ streaming chưa đóng hoặc rò rỉ resource. CPU DB thấp không chứng minh database khỏe; các session có thể đang chờ khóa hoặc network.

Một pool ở trạng thái active cao không nhất thiết là leak: giao dịch chậm hoặc tải thực sự vượt năng lực cũng có thể gây biểu hiện giống nhau.

## 10. Trạng thái session và cách trả kết nối an toàn

Connection không phải một vật chứa vô trạng thái. Nó có thể mang:

- autocommit, readOnly và isolation level;
- catalog/schema hiện tại, network timeout, holdability;
- trạng thái transaction còn mở hoặc đã lỗi;
- biến session của DB, vai trò người dùng (role), search path;
- temporary table, prepared statement phía server hoặc advisory lock;
- cursor và các tài nguyên phụ thuộc.

### 10.1. Tránh rò trạng thái giữa hai borrower

Nếu request của tenant A thay đổi search_path hoặc session role để truy cập schema khác, một request tenant B mượn lại cùng physical connection có thể gặp rủi ro dữ liệu và phân quyền nếu trạng thái không được reset.

Giải pháp thiết kế nên dùng điều kiện tenant tường minh và phân quyền DB rõ ràng khi phù hợp. Nếu ứng dụng dùng session variables hoặc role-based row security, cần có chính sách đặt và reset trạng thái theo **mỗi transaction** đáng tin cậy. Không chỉ tin vào việc close() tự động xóa mọi SET tùy ý.

Trong PostgreSQL, những lệnh như SET LOCAL áp dụng trong transaction hiện tại có thể giúp thu hẹp phạm vi một số thiết lập, nhưng phải hiểu rõ thời điểm transaction bắt đầu và ngữ nghĩa của tham số. Thiết lập ngoài transaction hoặc trên connection bất định có thể không có hiệu lực như mong muốn.

### 10.2. Sau lỗi nặng, có nên tái sử dụng connection?

Các lỗi SQL thông thường không luôn làm connection vật lý hỏng. Nhưng socket mất, protocol bị lỗi, DB restart hoặc connection bị đánh dấu broken có thể khiến handle không còn hợp lệ. Driver và pool thường nhận diện loại lỗi cần loại bỏ physical connection.

Ứng dụng không nên giữ một Connection hỏng trong field rồi retry vô hạn. Hãy kết thúc scope, để pool kiểm tra/hủy handle, mượn connection mới trong transaction mới, và chỉ retry khi công việc nghiệp vụ cho phép. Đặc biệt sau timeout ở bước COMMIT, phải phân biệt **transaction outcome chưa rõ** với lỗi chắc chắn đã rollback.

### 10.3. Đừng nuốt lỗi close, rollback hoặc reset

~~~java
// Mẫu sai khi làm mất toàn bộ nguyên nhân.
try {
    doSql();
} catch (Exception ignored) {
    // Không có log hoặc báo lỗi.
}
~~~

Lỗi cleanup có thể là tín hiệu DB đã mất kết nối hoặc session không còn an toàn. Dùng suppressed exceptions, log có correlation ID và bảo đảm không lộ credential/SQL chứa dữ liệu nhạy cảm. Tránh ghi mật khẩu, connection string có secret hay toàn bộ nội dung của người dùng vào log.

## 11. Chẩn đoán rò rỉ và kiểm thử vòng đời

Một leak nghĩa là tài nguyên đã được mượn nhưng không được trả theo hợp đồng khi công việc kết thúc. Tuy nhiên một connection được giữ quá lâu vì query chậm chưa chắc là leak. Cần phân biệt bằng mốc mượn, mốc trả và mục đích giữ.

### 11.1. Kiểm thử các nhánh thực thi

Dùng một DataSource/pool thật trong môi trường test, thực hiện:

1. Truy vấn thành công và đọc hết ResultSet.
2. Truy vấn không có hàng và return sớm.
3. SQL ném SQLException.
4. Row mapper ném RuntimeException giữa lúc duyệt ResultSet.
5. Transaction thứ hai thất bại sau câu ghi đầu và phải rollback.
6. Một consumer/task bị hủy giữa chừng.
7. DB mất kết nối trong lúc query hoặc commit.
8. Nhiều request đồng thời vượt kích thước pool và phải chờ hoặc timeout.
9. Method repository lồng nhau có Spring transaction; xác nhận phạm vi join transaction và việc hoàn trả khi outer transaction kết thúc.
10. Một đường dùng lazy stream hoặc cursor có cleanup đúng kể cả khi dừng sớm.

Tại những điểm ổn định sau khi tác vụ kết thúc, xác nhận lượng active của pool trở về mức kỳ vọng, không có transaction lơ lửng và trạng thái session không rò giữa các borrower. Tránh assert con số pool luôn là 0 nếu framework hoặc workload vẫn đang chạy; chọn điều kiện phù hợp môi trường test.

### 11.2. Leak detection là công cụ điều tra

Một số pool có cơ chế cảnh báo khi handle bị giữ lâu hơn ngưỡng. Ví dụ HikariCP có leakDetectionThreshold để ghi cảnh báo phục vụ chẩn đoán. Một request chậm hợp lệ cũng có thể tạo cảnh báo; **cảnh báo leak không tự chứng minh đã quên close**.

Nếu thiết lập ngưỡng quá thấp, log tràn ngập thông báo từ các transaction bình thường. Cần phân tích stack trace mượn connection, metrics hold time và timeline request/transaction để tìm nguyên nhân.

### 11.3. Truy vấn database để tìm transaction lâu

Trên PostgreSQL, trong phạm vi quyền đọc phù hợp, có thể quan sát phiên kết nối:

~~~sql
SELECT pid,
       state,
       now() - xact_start AS transaction_age,
       wait_event_type,
       wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Các trường như state, xact_start và wait_event giúp tìm session đang idle in transaction hoặc chờ khóa. Không nên suy số lượng session trên DB bằng đúng active handles của một pool vì còn các pool khác, worker, công cụ quản trị và kết nối hệ thống.

Khi xem query text trong pg_stat_activity hoặc log SQL, bảo đảm kiểm soát quyền và ẩn dữ liệu nhạy cảm.

## 12. Case study: pool cạn dù SQL trung bình chỉ vài mili giây

Một dịch vụ đặt hàng có pool 15 connection. Mỗi request làm:

~~~text
getConnection()
  -> SELECT tồn kho (nhanh)
  -> gọi HTTP service báo giá (có lúc chờ vài giây)
  -> UPDATE đơn (nhanh)
  -> COMMIT
  -> close()
~~~

Khi nhà cung cấp báo giá chậm, nhiều request giữ connection cùng lúc, active đạt 15, pending tăng, rồi getConnection() của request khác timeout. Nhìn riêng metrics “thời gian SELECT trung bình” sẽ không tìm ra nguyên nhân.

**Phân tích:** toàn bộ thời gian gọi HTTP nằm trong scope sở hữu connection; nếu transaction đã bắt đầu, còn có thể giữ lock hoặc snapshot DB. Pool cạn vì **hold time**, không nhất thiết vì SQL chậm.

**Thiết kế lại:** lấy báo giá trước khi mở transaction khi nghiệp vụ cho phép; xác minh phiên bản/giá lúc commit nếu cần để tránh dữ liệu cũ; giữ transaction cho những câu SQL phải nguyên tử. Nếu thao tác ngoài DB cần phối hợp bất đồng bộ, lưu trạng thái PENDING cùng outbox và xử lý tiếp có idempotency, retry/reconciliation.

**Kiểm chứng:** so sánh active/pending, p95 thời gian mượn và giữ handle, số lock waits, throughput, tỷ lệ lỗi sau khi rút ngắn transaction. Không coi việc tăng pool lên 100 là sửa tận gốc.

## 13. Câu hỏi ôn tập

### A. try-with-resources và return sớm

Một method mở Connection, PreparedStatement và ResultSet bằng try-with-resources; sau khi đọc hàng đầu tiên thì return DTO.

**Hỏi:** Connection có được trả không? Nếu đọc hàng đầu tiên ném RuntimeException thì sao?

**Gợi ý:** Khi thoát khỏi scope try, Java gọi close các resource theo thứ tự ngược lúc mở, kể cả return hoặc exception. Với pool, close handle trả connection hoặc khiến pool loại bỏ connection không hợp lệ theo chính sách.

### B. Repository tự close connection do caller truyền

Transaction service mượn Connection và truyền cho repository A, B. A gọi connection.close() trước khi B chạy.

**Hỏi:** Vấn đề ownership nằm ở đâu?

**Gợi ý:** Transaction service là chủ sở hữu connection; A chỉ nên đóng Statement/ResultSet mà A tạo. Đóng connection do caller truyền có thể trả handle quá sớm và phá transaction.

### C. Spring @Transactional và hai DataSource

Một service có @Transactional, repository A dùng DataSource X qua JdbcTemplate, repository B tự lấy raw Connection từ DataSource Y.

**Hỏi:** Có bảo đảm cả hai INSERT cùng commit/rollback không?

**Gợi ý:** Không. Annotation không tự tạo transaction chung cho hai DataSource. Phải hiểu transaction manager và cơ chế phối hợp thực tế; nếu cần nhất quán xuyên hai DB, cần chiến lược phân tán phù hợp.

### D. Pool active luôn tối đa

CPU DB thấp, pool active tối đa, pending tăng, SQL query log đa số nhanh.

**Hỏi:** Nên kiểm tra gì trước khi tăng pool?

**Gợi ý:** Thời gian giữ connection, đoạn code gọi mạng trong transaction, stream/cursor chưa đóng, lock waits, transaction idle và request bị treo; dùng metrics và traces thay vì chỉ tăng cấu hình.

### E. ResultSet trả ra ngoài method

Một repository return ResultSet từ try-with-resources, controller duyệt nó để sinh JSON.

**Hỏi:** Tại sao lỗi dù SQL đã chạy thành công?

**Gợi ý:** ResultSet phụ thuộc statement và connection đã đóng. Map DTO bên trong scope hoặc dùng API streaming mà caller sở hữu đúng lifecycle.

### F. Timeout khi COMMIT

App không nhận được phản hồi từ commit() và nhận SQLException. Code gọi lại toàn bộ lệnh chuyển tiền bằng request ID mới.

**Hỏi:** Rủi ro?

**Gợi ý:** Commit có thể đã hoàn tất ở DB nhưng ACK mất. Retry bằng ID mới có thể chuyển tiền hai lần. Cần idempotency key ổn định, ràng buộc DB và đối soát trạng thái trước khi thử lại.

### G. Session state

Request A dùng SQL SET search_path, sau đó close handle. Request B mượn lại physical connection đó.

**Hỏi:** Có thể chắc B nhận search_path mặc định không?

**Gợi ý:** Không. Pool thường reset những thuộc tính JDBC theo dõi, nhưng thay đổi session bằng SQL tùy ý không luôn được reset tự động. Cần chính sách rõ về trạng thái session/tenant.

## 14. Checklist khi viết code truy cập dữ liệu

- [ ] DataSource/pool có vòng đời ở cấp ứng dụng, không tạo mới mỗi request.
- [ ] Connection được mượn gần điểm cần dùng và có chủ sở hữu close rõ ràng.
- [ ] PreparedStatement và ResultSet được đóng trong mọi nhánh thành công, lỗi, return sớm.
- [ ] Repository nhận Connection từ caller không tự đóng connection khi không sở hữu.
- [ ] Không trả ResultSet/Stream phụ thuộc JDBC ra khỏi scope còn sống.
- [ ] Không lưu Connection trong singleton, không chia sẻ tùy tiện giữa thread.
- [ ] Các SQL phải nguyên tử chạy trong cùng transaction/connection hoặc qua transaction manager phù hợp.
- [ ] Transaction commit hoặc rollback được xử lý trước khi trả handle về pool.
- [ ] Kết quả COMMIT chưa rõ được đối soát, không retry nghiệp vụ không idempotent với ID mới.
- [ ] Không giữ connection khi chờ HTTP, email, upload hay xử lý kéo dài không thuộc transaction.
- [ ] Spring @Transactional, propagation và DataSource thực sự khớp với ranh giới nghiệp vụ.
- [ ] Session state và autocommit/isolation/role không rò sang borrower tiếp theo.
- [ ] Phân biệt pool wait, query timeout, lock wait và network timeout.
- [ ] Giám sát active, idle, pending, acquisition time, hold time, DB waits và request p95.
- [ ] Đã kiểm thử đường lỗi, stream bị hủy, transaction rollback và quá tải pool.

**Ghi nhớ:** mượn connection là nhận quyền sử dụng một tài nguyên hữu hạn trong **một phạm vi cụ thể**. Code đúng phải đóng những tài nguyên nó tạo, kết thúc giao dịch trước khi trả handle và không phụ thuộc vào connection sau khi scope đóng. Khi dùng Spring hoặc một pool, hãy hiểu ai đang sở hữu transaction và connection tại từng thời điểm; quản lý vòng đời đúng giúp cả tính đúng đắn dữ liệu lẫn độ ổn định của ứng dụng Java.
