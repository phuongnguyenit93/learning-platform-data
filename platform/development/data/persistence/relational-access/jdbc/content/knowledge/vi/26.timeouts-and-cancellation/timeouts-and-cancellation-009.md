# Truyền giới hạn thời gian từ yêu cầu tới từng thao tác dữ liệu trong JDBC

Trong một ứng dụng Java sử dụng **JDBC**, một yêu cầu HTTP có thể phải đọc khách hàng, kiểm tra tồn kho rồi cập nhật đơn hàng. Nếu mỗi thao tác dữ liệu tự đặt timeout là **5 giây**, yêu cầu gồm bốn thao tác có thể kéo dài hơn 20 giây, chưa kể thời gian mượn kết nối từ pool, xử lý Java và truyền phản hồi. Điều này xảy ra dù tất cả câu SQL đều “tuân thủ timeout riêng”.

Giải pháp là truyền **một giới hạn thời gian chung của yêu cầu** (*request deadline*) qua các lớp service và repository. Trước mỗi thao tác, ứng dụng tính **thời gian còn lại**, từ đó chọn mức chờ phù hợp, từ chối công việc mới khi đã hết ngân sách và kết thúc transaction đúng cách khi có lỗi. Đây là trọng tâm của chương **Timeout và hủy** trong module **JDBC**: sử dụng các API chuẩn như `DataSource`, `Connection`, `PreparedStatement`, `ResultSet`, `Statement.setQueryTimeout()` và `Statement.cancel()` nhưng không nhầm lời gọi timeout với cam kết dừng chính xác ở thời điểm mong muốn.

**Nguyên tắc chính:** *Truyền cùng một deadline, không cấp lại toàn bộ thời lượng ở từng tầng.* Timeout của một câu SQL, thời gian chờ kết nối và thời gian của request là **ba phạm vi khác nhau**; chỉ phối hợp chúng mới tạo ra hành vi có giới hạn hợp lý.

## 1. Vì sao timeout riêng lẻ không tạo ra deadline chung?

Giả sử endpoint `POST /orders` có ngân sách xử lý 3 giây:

```text
Request bắt đầu:                          t = 0 ms
    │
    ├─ Chờ DataSource.getConnection():    450 ms
    │
    ├─ SELECT thông tin khách hàng:        700 ms
    │
    ├─ SELECT kiểm tra tồn kho:            900 ms
    │
    ├─ UPDATE ghi đơn hàng:                600 ms
    │
    └─ Tạo phản hồi:                       250 ms
                                          ───────
                               Tổng:      2900 ms
```

Nếu mọi câu SQL cùng nhận `setQueryTimeout(3)`, mỗi câu đều có thể chiếm gần **3 giây** mà không tự biết những bước trước đã dùng bao nhiêu. Request có thể vượt deadline. Ngược lại, khi bước đầu tiên mất 2,5 giây, bước SQL tiếp theo chỉ nên nhận **phần ngân sách còn lại**, không phải 3 giây mới.

Đúng hơn:

```text
Request deadline = thời điểm bắt đầu + ngân sách được cấp

Trước getConnection(): còn 3000 ms
Sau getConnection():  còn 2550 ms
Trước SELECT #2:       còn 1850 ms
Trước UPDATE:          còn 950 ms
Trước tạo response:    còn 350 ms
```

Các số trên là minh họa. Khi đến một bước mà **thời gian còn lại bằng 0**, không khởi tạo thêm thao tác tốn thời gian chỉ để hy vọng thành công trước hạn.

### Timeout và deadline không giống nhau

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Timeout** | Khoảng thời gian tối đa cho *một thao tác*, thường tính từ khi thao tác bắt đầu | “Một SQL query tối đa 2 giây” |
| **Deadline** | Thời điểm kết thúc ngân sách của *toàn bộ công việc* | “Toàn bộ request phải hoàn tất trước mốc D” |
| **Thời gian còn lại** | `deadline - thời điểm hiện tại`, giảm sau từng bước | “Trước bước thứ ba còn 650 ms” |
| **Cancellation** | Tín hiệu yêu cầu công việc đang chạy dừng | `Statement.cancel()` hoặc tín hiệu hủy của framework |
| **Rollback** | Hoàn tác transaction chưa commit theo hợp đồng database | `Connection.rollback()` |

**Hết hạn không đồng nghĩa đã hủy xong và rollback xong.** Deadline là chính sách của ứng dụng; JDBC driver, mạng và database vẫn phải phối hợp để kết thúc lệnh đang chạy. Một thao tác ghi có thể đã hoàn thành ở server dù phía Java nhận lỗi timeout.

## 2. Những “đồng hồ” thực sự hoạt động trong JDBC

| Tầng | API hoặc cấu hình tiêu biểu | Điều nó giới hạn | Điều nó không tự bảo đảm |
| --- | --- | --- | --- |
| Toàn bộ request | Deadline do ứng dụng/framework truyền | Ngân sách đầu-cuối qua service, DAO và các tác vụ khác | Không tự ngắt SQL đang chạy |
| Mượn kết nối từ pool | Cấu hình *acquisition/borrow timeout* riêng của pool | Thời gian chờ `DataSource.getConnection()` trả kết nối | Không đồng nghĩa thời gian driver tạo kết nối vật lý |
| Thiết lập kết nối | `DataSource.setLoginTimeout(seconds)`, thuộc tính connect timeout của driver | Một phần hoặc toàn bộ quá trình tạo/đăng nhập kết nối theo implementation | Không phải API chuẩn để đặt deadline mượn cho từng request |
| Câu SQL | `Statement.setQueryTimeout(seconds)` | Yêu cầu driver áp giới hạn cho thao tác statement theo hỗ trợ của nó | Không bảo đảm toàn bộ request, mọi lần fetch hoặc commit dừng đúng mốc |
| Mạng của kết nối | `Connection.setNetworkTimeout(executor, millis)` | Giới hạn thời gian chờ phản hồi cho một số yêu cầu mạng của JDBC | Không thay thế query timeout hay chính sách rollback; có thể khiến connection mất khả dụng |
| Hủy lệnh | `Statement.cancel()` | Yêu cầu driver hủy statement hiện đang chạy | Không xác nhận chắc chắn server đã dừng hay rollback |
| Transaction | Transaction manager, giới hạn server/driver riêng | Giới hạn phạm vi giao dịch nếu được hỗ trợ và cấu hình | Không được cung cấp như một “transaction timeout” chung bằng một setter JDBC duy nhất |
| Socket/read | Thuộc tính network/socket của driver | Giới hạn một số thao tác socket | Không phải giới hạn nghiệp vụ và có thể khác đơn vị, phạm vi giữa các driver |

**Chú ý đơn vị:** `setQueryTimeout(int)` và `setLoginTimeout(int)` nhận **giây**; `setNetworkTimeout(..., int)` nhận **mili giây**. Các thuộc tính pool có thể dùng mili giây, giây hoặc cấu trúc `Duration` tùy thư viện. Đừng copy một giá trị “2000” giữa các loại timeout mà không kiểm tra đơn vị.

Một request có deadline 1 giây nhưng pool cấu hình chờ mượn 30 giây sẽ không được ràng buộc đúng chỉ vì mỗi câu SQL sau đó có timeout. Request có thể **kẹt ngay tại `getConnection()`** trước khi tạo được `PreparedStatement`.

## 3. Chọn đồng hồ đo deadline: `System.nanoTime()`, không dùng giờ hệ thống để trừ thời lượng

Trong một tiến trình Java, `System.nanoTime()` phù hợp để đo **khoảng thời gian đã trôi qua**. Nó dùng một mốc tùy ý và không bị ảnh hưởng trực tiếp bởi việc chỉnh giờ lịch hệ thống như cách tính bằng `System.currentTimeMillis()`.

Ta có thể lưu:

```text
startNanos    = System.nanoTime()
budgetNanos   = thời lượng yêu cầu được cấp
elapsedNanos  = System.nanoTime() - startNanos
remaining     = max(0, budgetNanos - elapsedNanos)
```

Với các request có thời lượng hợp lý, cách tính này tránh phải so sánh mốc giờ lịch và tránh cộng một deadline quá lớn. **Giá trị `nanoTime()` chỉ có ý nghĩa trong cùng môi trường đo thời gian**; không gửi nó qua HTTP sang máy khác rồi so sánh trực tiếp. Nếu upstream chuyển một timestamp deadline hoặc thời lượng còn lại, tại ranh giới nhận request hãy quy đổi thành **ngân sách tương đối** mới theo đồng hồ đơn điệu của tiến trình.

### Lớp `RequestDeadline` dùng lại qua service và DAO

Ví dụ Java 8 trở lên:

```java
import java.sql.SQLTimeoutException;
import java.util.concurrent.TimeUnit;

public final class RequestDeadline {
    private static final long MAX_BUDGET_MILLIS =
            TimeUnit.DAYS.toMillis(1);

    private final long startedNanos;
    private final long budgetNanos;

    private RequestDeadline(long budgetMillis) {
        this.startedNanos = System.nanoTime();
        this.budgetNanos =
                TimeUnit.MILLISECONDS.toNanos(budgetMillis);
    }

    public static RequestDeadline start(long budgetMillis) {
        if (budgetMillis <= 0
                || budgetMillis > MAX_BUDGET_MILLIS) {
            throw new IllegalArgumentException(
                    "Budget must be between 1 ms and 1 day");
        }
        return new RequestDeadline(budgetMillis);
    }

    public long remainingNanos() {
        long elapsed = System.nanoTime() - startedNanos;
        return Math.max(0L, budgetNanos - elapsed);
    }

    public void requireTime(String stage)
            throws SQLTimeoutException {
        if (remainingNanos() == 0L) {
            throw new SQLTimeoutException(
                    "Request deadline exceeded before " + stage);
        }
    }

    // JDBC query timeout dùng giây nguyên.
    public int queryTimeoutSeconds() throws SQLTimeoutException {
        long remaining = remainingNanos();
        if (remaining == 0L) {
            throw new SQLTimeoutException(
                    "No request budget remains for SQL");
        }

        long nanosPerSecond = TimeUnit.SECONDS.toNanos(1);
        long roundedUpSeconds =
                1L + (remaining - 1L) / nanosPerSecond;
        return (int) Math.min(
                (long) Integer.MAX_VALUE, roundedUpSeconds);
    }
}
```

**Giải thích các lựa chọn:**

- Tạo đúng **một instance** ở đầu request rồi truyền cùng đối tượng đến các service và repository. Không gọi `RequestDeadline.start(3000)` lại trong từng DAO.
- `remainingNanos()` phản ánh phần ngân sách còn lại, bao gồm cả thời gian xử lý Java, thời gian chờ pool và mọi câu SQL đã chạy.
- Nếu hết ngân sách, `requireTime(...)` ném `SQLTimeoutException` do **ứng dụng tự phát hiện**. Không nên xem lớp exception này là bằng chứng database đã tự hủy thao tác.
- `queryTimeoutSeconds()` làm tròn **lên giây nguyên** vì JDBC không có tham số mili giây cho `setQueryTimeout()`. Nếu còn 10 ms, hàm trả `1`, tức có thể cho phép SQL chạy **quá mốc deadline 990 ms**. Vì vậy nó là *best effort*, không phải deadline chính xác đến nano giây.
- Tránh `0` làm timeout cho câu SQL khi ngân sách đã hết: theo JDBC, `setQueryTimeout(0)` có nghĩa **không giới hạn query timeout**.
- Ví dụ giới hạn ngân sách ở một ngày để phép tính độ dài và cast dễ kiểm soát. Trong hệ thống sản phẩm, giới hạn này nên nhỏ hơn nhiều và phù hợp với deadline của hạ tầng.

Khi request được gọi lồng nhau, không tự “gia hạn” deadline. Nếu service có giới hạn cục bộ ngắn hơn, mức thời gian thực tế cho thao tác phải là **giá trị nhỏ hơn giữa ngân sách còn lại của request và giới hạn cục bộ**.

## 4. Truyền deadline qua các lớp thay vì giữ ở biến toàn cục

Một cách tổ chức dễ kiểm thử:

```text
HTTP Controller
  │ tạo một RequestDeadline từ request budget
  ▼
OrderService.placeOrder(command, deadline)
  │
  ├─ CustomerRepository.find(id, deadline)
  │
  ├─ InventoryRepository.reserve(product, qty, deadline)
  │
  └─ OrderRepository.insert(command, deadline)
       │
       ▼
    JDBC DataSource / Connection / PreparedStatement
```

Chữ ký minh họa:

```java
public interface CustomerRepository {
    Customer findById(long id, RequestDeadline deadline)
            throws SQLException;
}

public interface InventoryRepository {
    boolean reserve(long productId, int quantity,
                    RequestDeadline deadline)
            throws SQLException;
}

public interface OrderRepository {
    void insert(Order order, RequestDeadline deadline)
            throws SQLException;
}
```

Các kiểu `Customer` và `Order` ở đây là lớp miền do ứng dụng định nghĩa. Điểm cốt lõi là **mọi repository nhận cùng đối tượng `RequestDeadline`**, không nhận một con số timeout cố định rồi khởi tạo đồng hồ mới. Có thể thay việc truyền tham số trực tiếp bằng context có cấu trúc của framework, nhưng phải bảo đảm nó đi qua các lời gọi bất đồng bộ và không bị mất khi chuyển thread.

**Deadline và cancellation token là hai tín hiệu khác nhau:** deadline trả lời “còn bao nhiêu thời gian?”, token trả lời “request đã bị người gọi hoặc tầng trên yêu cầu hủy chưa?”. Khi client ngắt kết nối sớm, việc hủy có thể đến **trước khi deadline hết**; ứng dụng cần chính sách kết hợp cả hai thay vì chỉ trông vào đồng hồ.

## 5. Ví dụ JDBC đầy đủ: hai câu SELECT dùng cùng ngân sách còn lại

Ví dụ sau đọc tên khách hàng rồi đếm số đơn hàng của khách hàng đó bằng **hai câu SQL liên tiếp**. Nó chứng minh cách truyền deadline đến **từng `PreparedStatement`**, thay vì cấp lại 3 giây cho mỗi câu.

Giả sử có bảng `customers(id, full_name)` và `orders(id, customer_id)`:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;

public final class CustomerOverviewRepository {
    private final DataSource dataSource;

    public CustomerOverviewRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public Optional<CustomerOverview> load(
            long customerId, RequestDeadline deadline)
            throws SQLException {

        Objects.requireNonNull(deadline);
        deadline.requireTime("borrowing connection");

        // DataSource.getConnection() không có overload chuẩn
        // nhận deadline/timeout riêng cho lần mượn này.
        try (Connection connection = dataSource.getConnection()) {
            deadline.requireTime("first query");

            String customerSql =
                    "SELECT full_name FROM customers WHERE id = ?";
            String customerName;

            try (PreparedStatement statement =
                         connection.prepareStatement(customerSql)) {
                statement.setLong(1, customerId);
                statement.setQueryTimeout(
                        deadline.queryTimeoutSeconds());

                try (ResultSet rs = statement.executeQuery()) {
                    if (!rs.next()) {
                        deadline.requireTime("returning missing customer");
                        return Optional.empty();
                    }
                    customerName = rs.getString("full_name");
                }
            }

            deadline.requireTime("order count query");

            String countSql =
                    "SELECT COUNT(*) FROM orders WHERE customer_id = ?";
            long orderCount;

            try (PreparedStatement statement =
                         connection.prepareStatement(countSql)) {
                statement.setLong(1, customerId);
                statement.setQueryTimeout(
                        deadline.queryTimeoutSeconds());

                try (ResultSet rs = statement.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException(
                                "COUNT(*) query returned no row");
                    }
                    orderCount = rs.getLong(1);
                }
            }

            deadline.requireTime("returning customer overview");
            return Optional.of(
                    new CustomerOverview(
                            customerId, customerName, orderCount));
        }
    }

    public static final class CustomerOverview {
        public final long id;
        public final String fullName;
        public final long orderCount;

        public CustomerOverview(
                long id, String fullName, long orderCount) {
            this.id = id;
            this.fullName = fullName;
            this.orderCount = orderCount;
        }
    }
}
```

Ví dụ gọi ở đầu một request:

```java
RequestDeadline deadline = RequestDeadline.start(3_000);

CustomerOverviewRepository repository =
        new CustomerOverviewRepository(dataSource);

Optional<CustomerOverviewRepository.CustomerOverview> result =
        repository.load(101L, deadline);
```

**Cần đọc chính xác hành vi:**

1. Thời gian chờ `getConnection()` **tiêu hao deadline**, vì instance đã được tạo trước bước mượn. Nếu pool mất quá lâu và sau đó mới cấp được connection, `requireTime(...)` sau lần mượn sẽ phát hiện hết ngân sách, rồi `try-with-resources` trả connection ngay.
2. Nhưng `requireTime(...)` **không ngắt được `getConnection()` trong lúc nó đang chặn**. Thời gian mượn phải được điều khiển bằng chính sách pool phù hợp và quan sát bằng metric acquire/timeout.
3. `setQueryTimeout(...)` được gọi **trước mỗi câu SQL** với số giây dựa trên phần ngân sách mới nhất. Câu thứ hai không nhận lại ngân sách ban đầu.
4. Đây là chương trình đọc dữ liệu. Nếu cần ảnh chụp nhất quán giữa hai truy vấn, phải xem transaction và isolation của database; deadline không bảo đảm hai câu `SELECT` thấy một trạng thái dữ liệu duy nhất.
5. `requireTime(...)` sau mỗi giai đoạn giúp tránh trả kết quả như thành công khi thời lượng đã vượt giới hạn, nhưng **không quay ngược thời gian** và không thể ngăn mọi lệnh SQL chạy quá hạn do độ phân giải giây/driver.

Trong ứng dụng thật, những hàm xử lý kết quả lớn có thể duyệt hàng nghìn lần `rs.next()`. Nếu đã bị chậm ở **khâu xử lý Java sau khi JDBC trả dữ liệu**, nên kiểm tra deadline ở một số điểm thích hợp trong vòng lặp, không chỉ trước `executeQuery()`.

## 6. Vấn đề của việc chờ lấy kết nối từ pool

API chuẩn `DataSource` chỉ có `getConnection()` và `getConnection(username, password)`. Nó **không cung cấp phương thức `getConnection(deadline)`** để đặt acquisition timeout khác nhau cho mỗi request.

Với connection pool, thường có cấu hình riêng:

- **Borrow/acquisition timeout:** giới hạn thời gian một yêu cầu chờ được cấp kết nối từ pool.
- **Connection creation/login/connect timeout:** giới hạn thời gian mở kết nối vật lý tới database; có thể bị điều khiển bởi driver hoặc chính sách pool.
- **Validation timeout:** thời gian kiểm tra kết nối idle còn hợp lệ.
- **Connection hold duration:** thời gian ứng dụng giữ connection từ mượn đến trả; không phải một timeout nhưng rất quan trọng với nguy cơ cạn pool.

Ví dụ **đặc thù HikariCP** để minh họa phạm vi, không phải API `javax.sql.DataSource`:

```java
// Khi dự án dùng thư viện HikariCP và đã có cấu hình JDBC.
HikariConfig config = new HikariConfig();
config.setJdbcUrl(jdbcUrl);
config.setUsername(user);
config.setPassword(password);
config.setMaximumPoolSize(12);
config.setConnectionTimeout(1_000); // ms: thời gian chờ mượn
HikariDataSource pool = new HikariDataSource(config);
```

Cần import các lớp `com.zaxxer.hikari` và thêm dependency của HikariCP nếu chạy ví dụ. Giá trị `1_000` chỉ mang tính minh họa; cấu hình tối thiểu và tính hợp lệ tùy phiên bản. Khi dùng Commons DBCP, Tomcat JDBC Pool hoặc pool của application server, tên thuộc tính và phạm vi có thể khác. **Không dùng `DataSource.setLoginTimeout(...)` như cách mặc định để giới hạn hàng đợi pool của từng request**.

Nếu yêu cầu có deadline 500 ms nhưng pool cấu hình borrow timeout 10 giây, code ứng dụng không thể bảo đảm dừng đúng 500 ms chỉ bằng việc gọi `requireTime()` sau `getConnection()`. Cần phối hợp chính sách pool với request deadline, hoặc dùng cơ chế cấp phát bất đồng bộ/timeout được pool hỗ trợ và bảo đảm các kết nối được cấp phát muộn vẫn được trả đúng cách.

**Không lấy `Future.cancel(true)` trên một thread đang chặn `getConnection()` làm cách bảo đảm kết nối được trả lại:** ngắt thread có thể không hủy được thao tác JDBC, và kết nối có thể được cấp phát sau khi bên gọi đã bỏ chờ. Nếu bắt buộc thiết kế async, phải có cơ chế sở hữu và đóng connection ngay cả trong tình huống trả kết quả trễ hoặc chạy đua giữa timeout và cấp phát.

## 7. `Statement.setQueryTimeout()` làm được gì và có giới hạn nào?

`Statement.setQueryTimeout(int seconds)` áp dụng cho statement, kể cả `PreparedStatement` vì kế thừa `Statement`.

```java
try (PreparedStatement statement = connection.prepareStatement(
        "SELECT id FROM products WHERE id = ?")) {

    statement.setLong(1, productId);

    int seconds = deadline.queryTimeoutSeconds();
    statement.setQueryTimeout(seconds);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            deadline.requireTime("processing result rows");
            // Đọc/mapping dữ liệu theo yêu cầu nghiệp vụ.
        }
    }
}
```

**Giới hạn kỹ thuật:**

- Đơn vị là **giây nguyên**. Nếu còn 300 ms, đặt `1` giây có thể cho phép câu SQL vượt deadline request. JDBC không có tham số milli/nanosecond chuẩn cho `setQueryTimeout()`.
- `0` có nghĩa **không có giới hạn query timeout**; tránh vô tình làm tròn phần còn lại xuống `0`.
- JDBC yêu cầu driver nỗ lực áp dụng timeout khi thực thi; cách driver/server triển khai có thể khác nhau, và không phải mọi driver hỗ trợ đầy đủ.
- Nếu giới hạn statement bị vượt, driver thường ném `SQLTimeoutException` khi quyết định đã cố hủy thao tác; nhưng thực tế có thể xuất hiện `SQLException` khác tùy sản phẩm và giai đoạn thất bại.
- Không nên mặc định timeout tính bao trùm việc **mượn kết nối, toàn bộ quá trình fetch, đọc dữ liệu Java, transaction commit, rollback hay đóng connection**.
- `setQueryTimeout()` không phải API đặt giới hạn toàn bộ transaction. Trong một transaction có nhiều câu SQL, mỗi statement cần nhận **phần ngân sách còn lại**.
- Statement có thể có timeout cục bộ của hệ quản trị (ví dụ giới hạn chạy SQL ở cấp server) mạnh hơn hoặc yếu hơn giới hạn do JDBC yêu cầu. Cần xác minh thứ tự ưu tiên trong môi trường thực.

Nếu driver không hỗ trợ `setQueryTimeout()` và báo `SQLFeatureNotSupportedException`, ứng dụng phải có chiến lược phù hợp với database/driver, không âm thầm bỏ kiểm soát deadline mà vẫn tuyên bố request bị giới hạn chặt chẽ.

### Giới hạn cục bộ ngắn hơn deadline

Giả sử báo cáo chỉ được chiếm tối đa 2 giây dù request còn 7 giây. Có thể kết hợp:

```java
int requestRemainingSeconds =
        deadline.queryTimeoutSeconds();
int statementLimitSeconds = 2;

statement.setQueryTimeout(
        Math.min(requestRemainingSeconds, statementLimitSeconds));
```

Điều này giúp giới hạn statement trong hai phạm vi, nhưng vẫn có **độ hạt giây** và không phải lời hứa trả kết quả trước deadline. Nếu cần giới hạn dưới 1 giây, phải nghiên cứu timeout mức database/driver hoặc thiết kế khác; đừng dựa vào một phép làm tròn lên để tạo độ chính xác không có thật.

## 8. `Connection.setNetworkTimeout()` khác query timeout

JDBC hỗ trợ:

```java
import java.sql.Connection;
import java.sql.SQLException;
import java.util.concurrent.Executor;

// connection và executor do tầng hạ tầng quản lý.
public static void configureNetworkTimeout(
        Connection connection,
        Executor executor,
        int timeoutMillis) throws SQLException {

    connection.setNetworkTimeout(executor, timeoutMillis);
}
```

`setNetworkTimeout(executor, millis)` nhằm giới hạn thời gian driver chờ các phản hồi mạng trong hoạt động JDBC, theo hợp đồng và khả năng hỗ trợ của driver. Đây **không phải cách thay thế an toàn cho `setQueryTimeout()`**:

- Query timeout hướng đến **câu lệnh SQL**; network timeout hướng đến **thao tác giao tiếp qua kết nối**.
- Network timeout có thể đóng hoặc khiến `Connection` trở nên không còn sử dụng được khi hết hạn. Cần xử lý connection như đối tượng nghi vấn, để pool loại bỏ theo cơ chế hỗ trợ.
- Tham số `executor` thuộc cơ chế JDBC driver dùng cho hoạt động bất đồng bộ cần thiết, không nên tạo thread pool mới cho mỗi câu SQL rồi quên đóng.
- Nếu đổi network timeout trên kết nối lấy từ pool, ứng dụng phải hiểu chính sách reset trạng thái của pool và không khôi phục một cách mù quáng nếu kết nối đã hỏng.
- Một số driver không hỗ trợ đầy đủ API và có thể ném `SQLFeatureNotSupportedException`; việc hỗ trợ phụ thuộc phiên bản driver.

Vì vậy, network timeout thường được cấu hình **ở tầng hạ tầng kết nối**, kết hợp timeout socket/driver và pool. Không nên để mỗi DAO tự ý thay `setNetworkTimeout()` mà không có quy tắc về quyền sở hữu và cleanup.

## 9. `Statement.cancel()` và hủy bởi request là “yêu cầu”, không phải xác nhận hoàn tác

Giả sử client hủy request khi query vẫn đang chạy. `Statement.cancel()` là API JDBC để **đề nghị hủy câu SQL hiện tại**, thường từ một thread khác:

```java
// Giả sử statement đang chạy trên một thread khác.
try {
    statement.cancel();
} catch (SQLException cancellationFailure) {
    // Ghi nhận lỗi hủy; không suy ra server đã dừng.
}
```

Có những tình huống chạy đua:

```text
Thread A: statement.executeUpdate() ─────────────► hoàn tất
Thread B:                      statement.cancel()
                                │
                                └─ yêu cầu hủy đến muộn
```

Hoặc `cancel()` được gửi nhưng driver/network không thể liên lạc với server; cũng có trường hợp server đã thực hiện một phần công việc, đã commit hoặc đang xử lý rollback theo ngữ nghĩa transaction. Vì thế:

1. **Không coi `cancel()` trả về bình thường là bằng chứng database đã rollback.**
2. **Không coi việc client ngắt kết nối là bằng chứng JDBC/SQL đã dừng.**
3. Nếu đang thực hiện nhiều thao tác trong transaction, bên sở hữu `Connection` phải quyết định rollback và quản lý lỗi rollback.
4. Nếu câu lệnh ghi/commit đã được gửi mà kết quả chưa rõ, **không retry mù quáng**; dùng idempotency key, đối soát hoặc cơ chế ghi an toàn theo nghiệp vụ.
5. Không tự dùng lại connection có trạng thái transaction không rõ sau timeout/hủy; tuân theo chính sách loại bỏ của pool.

Một cơ chế quản lý deadline nâng cao có thể dùng **`ScheduledExecutorService` dùng chung** để lập lịch gọi `cancel()` khi hết hạn, nhưng cần phối hợp an toàn vòng đời `Statement`, nhiệm vụ hủy, transaction và connection. Khi statement hoàn thành, nhiệm vụ hủy còn chờ phải được hủy; các cuộc đua giữa “query vừa xong” và “cancel được gửi” vẫn phải được chấp nhận và xử lý.

Ví dụ khung ý tưởng, **không phải bảo đảm hủy đúng hạn**:

```java
// scheduler là ScheduledExecutorService dùng chung do hạ tầng quản lý.
// statement đã được tạo; deadline dùng chung với request.
long remaining = deadline.remainingNanos();
deadline.requireTime("scheduling SQL");

ScheduledFuture<?> cancellation = scheduler.schedule(() -> {
    try {
        statement.cancel();
    } catch (SQLException ignored) {
        // Ở bản sản phẩm, ghi log nội bộ theo chính sách.
    }
}, remaining, TimeUnit.NANOSECONDS);

try {
    // Đây là lời gọi đồng bộ; driver có thể không phản hồi cancel ngay.
    statement.execute();
} finally {
    cancellation.cancel(false);
}
```

Đoạn này dùng `ScheduledFuture` và `TimeUnit`, cần import từ `java.util.concurrent`, và **không tạo scheduler riêng cho mỗi request**. Nó minh họa việc truyền cùng thời gian còn lại sang tín hiệu hủy, nhưng không xử lý đầy đủ tình huống hủy đến đúng lúc statement đóng, connection bị lỗi hoặc câu SQL tiếp tục chạy trên server. Trong mã sản phẩm phải có quản lý trạng thái, log/callback và cách xử lý connection hỏng riêng; nhiều trường hợp chỉ cần `setQueryTimeout()` và timeout server đã được kiểm chứng.

**Ngắt thread không đồng nghĩa hủy SQL.** `Future.cancel(true)` đặt tín hiệu interrupt cho thread Java, nhưng cách driver JDBC phản ứng phụ thuộc implementation. Không dùng interrupt như cơ chế duy nhất để khẳng định một transaction ghi đã dừng.

## 10. Transaction nhiều bước: deadline phải sống cùng transaction

Giả sử nghiệp vụ đặt hàng gồm:

1. Trừ tồn kho có điều kiện.
2. Ghi đơn hàng.
3. Ghi nhật ký nghiệp vụ.
4. Commit cả ba thay đổi.

Nếu sau bước 2 deadline hết, service phải **rollback** thay vì tiếp tục bước 3 hoặc trả thành công trước khi `commit()` hoàn tất.

Ví dụ khung transaction dưới đây giữ một `Connection` cho nhiều thao tác. Các hàm `reserveInventory(...)`, `insertOrder(...)` và `insertAudit(...)` là helper do ứng dụng định nghĩa, **dùng chính `Connection` được truyền vào** và tự tính query timeout từ cùng `RequestDeadline` trước từng statement:

```java
public void placeOrder(
        long customerId,
        long productId,
        int quantity,
        RequestDeadline deadline) throws SQLException {

    deadline.requireTime("borrowing for order transaction");

    try (Connection connection = dataSource.getConnection()) {
        deadline.requireTime("starting order transaction");

        boolean originalAutoCommit = connection.getAutoCommit();
        if (!originalAutoCommit) {
            throw new SQLException(
                    "Expected a connection without an active transaction");
        }

        connection.setAutoCommit(false);
        boolean transactionEnded = false;
        Throwable primaryFailure = null;

        try {
            deadline.requireTime("reserving inventory");
            reserveInventory(connection, productId, quantity, deadline);

            deadline.requireTime("inserting order");
            insertOrder(connection, customerId, productId,
                    quantity, deadline);

            deadline.requireTime("writing audit");
            insertAudit(connection, customerId, productId, deadline);

            // Kiểm tra trước commit, nhưng không có API JDBC chuẩn
            // để áp đặt deadline mili giây riêng cho commit().
            deadline.requireTime("committing order");
            connection.commit();
            transactionEnded = true;

        } catch (SQLException | RuntimeException | Error failure) {
            primaryFailure = failure;

            if (!transactionEnded) {
                try {
                    connection.rollback();
                    transactionEnded = true;
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
            }
            throw failure;

        } finally {
            // Chỉ chuyển lại autoCommit khi transaction đã được
            // xác nhận kết thúc bằng commit hoặc rollback.
            if (transactionEnded) {
                try {
                    connection.setAutoCommit(originalAutoCommit);
                } catch (SQLException restoreFailure) {
                    if (primaryFailure != null) {
                        primaryFailure.addSuppressed(restoreFailure);
                    } else {
                        throw restoreFailure;
                    }
                }
            }
        }
    }
}
```

Đây là ví dụ **đặt trong một lớp service có field `DataSource dataSource`** và các helper chưa được trình bày, chứ không phải lớp Java đầy đủ để chạy độc lập. Việc xử lý lỗi phần dọn dẹp chỉ nhằm minh họa những điểm quan trọng:

- Deadline được tạo **ngoài phương thức** và không khởi động lại khi transaction bắt đầu.
- Mọi helper chạy bằng **cùng connection** và phải đặt giới hạn cho từng statement theo ngân sách còn lại.
- Nếu một bước lỗi hoặc deadline đã hết, code cố **rollback**. Dù đã hết deadline, vẫn cần dọn dẹp transaction/tài nguyên; không bỏ rollback chỉ vì hết ngân sách.
- Sau `commit()` thành công, transaction đã kết thúc. Sau `rollback()` thành công, có thể phục hồi `autoCommit`. Nếu rollback thất bại, **không bật `autoCommit=true`**, bởi việc thay đổi chế độ có thể vô tình commit transaction chưa hoàn tác.
- Nếu `commit()` báo `SQLException` do mất kết nối, trạng thái ở database có thể **không xác định**; cố rollback là bước dọn dẹp, không chứng minh server chưa commit. Service cần cơ chế đối soát/idempotency trước khi thử lại.
- `close()` trên pooled `Connection` thường trả quyền sử dụng cho pool; một kết nối hỏng hoặc transaction không chắc chắn phải được loại bỏ theo cơ chế cụ thể của pool. Không thể đảm bảo loại bỏ chỉ bằng một setter JDBC chung.

**Deadline không thay thế transaction manager.** Nếu framework sở hữu transaction, repository không được tự `commit()`, `rollback()` hoặc `setAutoCommit(true)`. Hãy tích hợp propagation/cancellation với transaction manager đang dùng và không làm hai tầng cùng sở hữu một transaction.

## 11. Retry phải dùng ngân sách còn lại, không tạo deadline mới

Một lỗi serialization hoặc deadlock có thể retry theo chính sách đã định. Nhưng nếu mỗi lần retry lại tạo một deadline 3 giây, ba lần thử có thể kéo dài 9 giây **chưa tính backoff**, phá vỡ giới hạn ban đầu.

Cách hiểu đúng:

```text
Request deadline: 3000 ms

Attempt 1: 800 ms  → lỗi có thể retry
Backoff:   100 ms
Còn lại:  2100 ms

Attempt 2: 1500 ms → lỗi
Backoff:   200 ms
Còn lại:   400 ms

Attempt 3: kiểm tra ngân sách, chỉ thử nếu còn đủ theo chính sách;
           KHÔNG cấp lại 3000 ms
```

Trong mã Java, giữ cùng `RequestDeadline`:

```java
for (int attempt = 1; attempt <= 3; attempt++) {
    deadline.requireTime("starting database attempt " + attempt);

    try {
        performWholeTransaction(deadline);
        break;
    } catch (SQLException failure) {
        if (!isRetryableTransactionFailure(failure) || attempt == 3) {
            throw failure;
        }

        long remaining = deadline.remainingNanos();
        if (remaining == 0L) {
            throw failure;
        }

        // Backoff phải được giới hạn bởi phần ngân sách còn lại.
        // retryDelayNanos và performWholeTransaction được ứng dụng
        // định nghĩa, không phải API JDBC.
        long delay = Math.min(retryDelayNanos(attempt), remaining);
        TimeUnit.NANOSECONDS.sleep(delay);
    }
}
```

Đây là **pseudocode Java cho vòng retry**: giả định các helper được định nghĩa, và phương thức bao quanh xử lý `InterruptedException` (khôi phục interrupt flag hoặc truyền ra ngoài phù hợp). Trong ứng dụng thật, không xem mọi `SQLException` đều retry được; `SQLState 40001` ở một số hệ quản trị có thể biểu thị serialization failure, nhưng cần đối chiếu driver/database và ngữ nghĩa của transaction.

Nếu phương thức `performWholeTransaction(...)` gửi email hoặc gọi dịch vụ thanh toán, thực thi lại có thể tạo tác động lặp. Cần idempotency, outbox hoặc thiết kế tách tác động ngoài DB khỏi transaction. Đặc biệt, **timeout ngay sau khi gửi `COMMIT` không bảo đảm giao dịch chưa commit**; retry phải dựa trên đối soát hoặc khóa idempotent, không chỉ vào loại exception.

### Đừng ngủ hết toàn bộ ngân sách

Một vòng retry hữu ích cần để lại thời gian cho việc thực thi SQL, rollback và trả response. Nếu còn 2 ms, gọi `sleep(2 ms)` rồi bắt đầu một transaction mới gần như không có ý nghĩa. Có thể dùng **ngưỡng ngân sách tối thiểu** cho một lần thử mới, được cấu hình dựa trên latency thực tế. Backoff cũng phải bị hủy khi request nhận cancellation token.

## 12. Timeout trong batch và thao tác đọc nhiều dòng

### Batching

Một lời gọi `executeBatch()` có thể chạy nhiều lệnh đã tích lũy. `Statement.setQueryTimeout()` trên batch **không cung cấp một hợp đồng deadline toàn request chính xác, thống nhất trên mọi driver**. Cần kiểm thử xem timeout được áp dụng cho toàn batch hay từng phần tử và driver có tiếp tục thực thi sau lỗi không.

Khi `BatchUpdateException` xảy ra:

- Đọc `getUpdateCounts()` để biết phần thông tin driver báo về.
- Xem `getNextException()`, SQLState và mã lỗi.
- Nếu toàn batch thuộc một transaction chưa commit, bên sở hữu quyết định rollback.
- Không gửi lại toàn batch khi chưa xác định phần nào đã chạy, commit và tính idempotent.
- Nếu chia batch thành nhiều phần nhỏ, đặt timeout từng lần `executeBatch()` từ **cùng deadline**, không cấp lại thời lượng ban đầu cho từng batch.

### Đọc nhiều dòng và streaming

Ngay cả khi `executeQuery()` trả về nhanh, đọc `ResultSet` có thể mất nhiều thời gian do fetch thêm dữ liệu từ server hoặc do việc mapping trong Java:

```java
try (ResultSet rs = statement.executeQuery()) {
    int processed = 0;

    while (rs.next()) {
        if ((processed++ & 127) == 0) {
            deadline.requireTime("mapping ResultSet");
        }

        // Đọc cột, map DTO, ghi vào output...
    }
}
```

Thử check mỗi 128 dòng là một **lựa chọn minh họa** để giảm chi phí gọi đồng hồ, không bảo đảm chính xác về deadline nếu một lần `rs.next()` bị chặn lâu hoặc việc map một hàng rất nặng. Driver có thể fetch theo từng đợt; `setFetchSize(...)` chỉ là gợi ý với nhiều implementation. Nếu cần deadline chặt cho việc đọc stream, phải kết hợp khả năng timeout của driver/network và chiến lược hủy được hỗ trợ.

Không để `ResultSet`, `Statement` hay `Connection` sống qua một tương tác người dùng dài chỉ vì request bên ngoài chưa gửi xong toàn bộ nội dung.

## 13. Bắt lỗi timeout đúng phạm vi và ghi log đủ dữ kiện

Khi gặp timeout, trước hết xác định **nó xảy ra ở giai đoạn nào**:

| Giai đoạn | Triệu chứng | Hướng điều tra |
| --- | --- | --- |
| Trước khi lấy connection | Pool borrow timeout | Active/idle/pending, thời gian giữ connection, số lượng connection tối đa |
| Tạo connection vật lý | Login/connect/socket timeout | DNS/TCP/TLS, xác thực, DB connection limit, driver |
| `executeQuery()`/`executeUpdate()` | `SQLTimeoutException` hoặc lỗi driver | Query plan, lock wait, query timeout, server statement limit |
| Đọc `ResultSet` | Fetch/network timeout hoặc ứng dụng hết deadline | Fetch size, dữ liệu lớn, stream, mạng, CPU mapping |
| `commit()` | Timeout/mất kết nối | Trạng thái commit chưa xác định; đối soát, không retry mù quáng |
| `rollback()` | Lỗi dọn dẹp giao dịch | Kết nối nghi vấn; thông tin suppressed, chính sách loại bỏ của pool |
| `close()` | Lỗi đóng/trả connection | Pool/driver, lỗi phụ của try-with-resources, tài nguyên tồn đọng |

Các thông tin log/metric hữu ích:

- Tên thao tác ổn định như `orders.reserve`, `orders.insert`, **không log tham số SQL nhạy cảm**.
- `requestDeadlineBudgetMs`, `elapsedMs` và `remainingMs` tại thời điểm bắt đầu mỗi thao tác.
- `connection.acquire.duration`, `statement.duration`, số hàng đã xử lý và thời gian giữ connection.
- Pool `active/idle/pending`, borrow timeout count, creation failures, connection validation duration.
- `SQLState`, `SQLException.getErrorCode()`, lớp ngoại lệ, lỗi rollback/cancel/close được gắn bằng `addSuppressed()` khi phù hợp.
- Trace ID để nối sự kiện giữa HTTP, service, DAO và database; không đưa raw SQL error message hay connection string ra response công khai.

**Không đồng nhất `SQLTimeoutException` với một kết quả database duy nhất.** Ngoại lệ do `RequestDeadline.requireTime()` ném ra trước khi có câu SQL khác hẳn ngoại lệ do driver báo trong lúc statement đang chạy; log nên ghi rõ `stage` để phân tích đúng.

## 14. Kiểm thử deadline propagation trên JDBC thật

Nên kiểm thử trong môi trường riêng, với **đúng driver, pool và phiên bản hệ quản trị** dự kiến dùng. Mock Java giúp kiểm tra cách tính deadline; nhưng chỉ kiểm thử tích hợp mới xác nhận cách database hủy query, trả kết quả hoặc xử lý transaction.

| Kịch bản | Cách thực hiện | Điều cần kiểm chứng |
| --- | --- | --- |
| Hai query dùng cùng deadline | Làm query thứ nhất chậm có kiểm soát rồi gọi query thứ hai | Query thứ hai nhận **ngân sách còn lại**, không nhận lại timeout ban đầu |
| Deadline hết trước query | Chờ đến khi thời lượng hết rồi gọi DAO | Không gửi câu SQL mới; báo lỗi deadline rõ ràng |
| Pool bão hòa | Giữ toàn bộ connection trong pool thử nghiệm | `getConnection()` chờ/timeout theo cấu hình pool; `requireTime()` sau mượn không thể ngắt nó |
| Query chạy quá giới hạn | Dùng SQL chậm trên database thử nghiệm | Quan sát hành vi `setQueryTimeout()`, loại exception và server có dừng lệnh không |
| Client hủy giữa query | Dùng cơ chế cancellation của ứng dụng hoặc `Statement.cancel()` | Không giả định cancel bảo đảm rollback; tài nguyên được giải phóng |
| Lỗi ngay sau câu `INSERT` | Mô phỏng đứt kết nối chỉ trong môi trường riêng | Không retry mù quáng, có cơ chế đối soát/idempotency |
| Deadline giữa transaction | Bước 1 thành công, sau đó hết thời gian trước bước 2 | Transaction bị rollback, không commit một phần nghiệp vụ |
| Rollback thất bại | Tạo tình huống lỗi có kiểm soát trên connection thử | Không bật lại auto-commit vô điều kiện; pool loại bỏ kết nối nghi vấn |
| Retry có backoff | Tạo lỗi serialization/deadlock có thể retry | Mọi lần thử dùng cùng deadline và giới hạn số lần thử |
| ResultSet nhiều hàng | Đọc dữ liệu lớn/fetch nhiều đợt | Kiểm tra deadline trong mapping và tài nguyên đóng đúng lúc |

### Bài thực hành

1. Viết một lớp `RequestDeadline` dựa trên `System.nanoTime()`. Giải thích vì sao phép làm tròn timeout JDBC xuống `0` là nguy hiểm.
2. Tạo hai phương thức DAO cùng nhận `RequestDeadline`: một phương thức `SELECT`, một phương thức `UPDATE` có tham số. Đo và ghi thời gian còn lại trước mỗi câu SQL.
3. Cấu hình pool chỉ có hai connection. Giữ hai connection trong hai thread và thử gọi `getConnection()` từ thread thứ ba. Kiểm tra borrow timeout khác query timeout như thế nào.
4. Tạo transaction hai bước; cho hết deadline sau bước đầu và xác nhận rollback trong database thử nghiệm.
5. Thử `Statement.cancel()` với query dài có kiểm soát. Ghi lại loại exception, thời gian thực tế để driver trả về và trạng thái connection sau đó.
6. Xây dựng retry tối đa ba lần cho lỗi serialization đã được driver xác nhận. Không khởi tạo deadline mới và không retry khi commit có kết quả chưa rõ.
7. Viết báo cáo ngắn: deadline ứng dụng, timeout mượn pool, query timeout, network timeout của driver, timeout server, kết quả kiểm thử và rủi ro chưa thể bảo đảm.

### Các câu hỏi tự kiểm tra

- Vì sao đặt `setQueryTimeout(3)` cho ba câu SQL không bảo đảm tổng request hoàn thành dưới 3 giây?
- `RequestDeadline` dùng `nanoTime()` có thể gửi trực tiếp sang một máy khác và so sánh với `nanoTime()` ở máy đó không?
- Nếu còn 100 ms, `setQueryTimeout(1)` có bảo đảm câu SQL kết thúc dưới 100 ms không?
- Có thể dùng `DataSource.setLoginTimeout()` để đặt deadline mượn pool khác nhau cho từng request không?
- Nếu `Statement.cancel()` trả về bình thường, có thể kết luận transaction đã rollback không?
- Vì sao lỗi timeout tại `commit()` nguy hiểm hơn lỗi deadline phát hiện **trước khi bắt đầu SQL**?
- Khi retry sau deadlock, thời gian backoff và transaction mới phải tiêu thụ ngân sách nào?
- Sau khi deadline hết, tại sao vẫn phải cố rollback/đóng tài nguyên thay vì bỏ mọi cleanup?

## 15. Tổng kết nguyên tắc

1. **Tạo một deadline ở đầu request** và truyền nó qua mọi service/DAO. Không tạo một timeout đầy đủ mới cho từng câu SQL.
2. **Dùng đồng hồ đơn điệu** để tính thời gian còn lại; không so sánh các giá trị `System.nanoTime()` giữa những máy khác nhau.
3. **Tách các phạm vi giới hạn**: thời gian chờ pool, tạo kết nối, query, network, transaction và toàn request là những đồng hồ khác nhau.
4. **Dùng `Statement.setQueryTimeout()` có hiểu biết**: đơn vị giây, `0` là không giới hạn, làm tròn lên không bảo đảm deadline chính xác.
5. **Đừng mặc định hủy đồng nghĩa rollback**: `Statement.cancel()` và interrupt chỉ là tín hiệu theo khả năng driver.
6. **Transaction phải tự kết thúc rõ ràng**: commit khi thành công, rollback khi lỗi; xử lý kết nối có trạng thái không chắc chắn theo chính sách của pool.
7. **Retry dùng đúng ngân sách còn lại** và chỉ cho lỗi có thể retry an toàn; cần idempotency/đối soát nếu thao tác ghi có kết quả chưa rõ.
8. **Đo và kiểm thử trong môi trường thực**: ghi nhận acquire time, SQL time, fetch, cancel latency, lỗi driver, thời gian giữ connection và deadline đã tiêu hao.

**Kết luận:** trong JDBC, truyền deadline từ request đến từng thao tác dữ liệu là cách kiểm soát **ngân sách thời gian của cả nghiệp vụ**, chứ không chỉ thiết lập một số giây cho `PreparedStatement`. Khi phối hợp deadline đơn điệu, chính sách mượn pool, timeout của driver/server, xử lý cancellation và transaction rõ ràng, ứng dụng có thể phản ứng nhất quán hơn trước tải lớn và lỗi hệ thống — nhưng vẫn phải chấp nhận rằng timeout/hủy không tự chứng minh một thao tác ghi đã bị hoàn tác.
