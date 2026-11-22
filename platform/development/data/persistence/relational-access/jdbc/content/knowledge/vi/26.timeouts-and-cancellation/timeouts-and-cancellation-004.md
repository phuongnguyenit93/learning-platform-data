# Thiết lập network timeout trên Connection

Khi một ứng dụng Java truy cập cơ sở dữ liệu bằng **JDBC**, câu lệnh SQL có thể chạy chậm vì nhiều nguyên nhân: truy vấn phức tạp, chờ khóa, thiếu kết nối trong pool hoặc đường truyền giữa ứng dụng và database bị gián đoạn. Các tình huống này nhìn bề ngoài đều giống nhau — thread đang chờ và người dùng chưa nhận được kết quả — nhưng **không thể xử lý bằng một loại timeout duy nhất**.

`Connection.setNetworkTimeout(Executor, int)` là API chuẩn JDBC dùng để đặt **thời gian chờ phản hồi của database cho một yêu cầu giao tiếp mạng** trên connection. Nó đặc biệt hữu ích khi kết nối bị kẹt do sự cố mạng, vì không nên để một thread ứng dụng chờ vô thời hạn. Tuy nhiên, network timeout **không phải deadline cho toàn bộ request** và cũng không thay thế `Statement.setQueryTimeout(...)`.

Bài học thuộc chương **Timeout và hủy** của module **JDBC**, sử dụng `DataSource`, `Connection`, `PreparedStatement`, `ResultSet`, transaction và cách xử lý `SQLException` để xây dựng thao tác database có giới hạn chờ và cơ chế phục hồi rõ ràng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích phạm vi của `setNetworkTimeout(Executor executor, int milliseconds)` và `getNetworkTimeout()`.
- Phân biệt network timeout với query timeout, login timeout, pool acquisition timeout và timeout ở tầng HTTP.
- Chọn một `Executor` phù hợp và quản lý vòng đời của nó khi JDBC cần hủy connection bị kẹt.
- Thiết lập network timeout trước khi thực thi `PreparedStatement` trên một connection mượn từ `DataSource`.
- Hiểu ý nghĩa của `milliseconds = 0`, giá trị âm, trường hợp driver không hỗ trợ và các thao tác có thể bị ảnh hưởng.
- Xử lý lỗi mà không tiếp tục dùng connection không còn đáng tin cậy.
- Nhận diện tình trạng **không chắc chắn đã commit hay chưa** khi mất phản hồi từ database.
- Kiểm thử network timeout trên driver/DBMS thực tế, tách biệt với việc chỉ chạy một câu SQL chậm.

## 2. Timeout xảy ra ở những tầng nào?

Một yêu cầu truy cập database có nhiều chặng:

~~~mermaid
flowchart LR
    A["HTTP / Job deadline"] --> B["Mượn Connection từ pool"]
    B --> C["Kết nối / đăng nhập DB"]
    C --> D["PreparedStatement.execute..."]
    D --> E["Truyền nhận qua mạng"]
    E --> F["Xử lý ResultSet"]
    F --> G["Trả kết quả cho ứng dụng"]
~~~

Các chặng có thể bị chặn vì những nguyên nhân khác nhau:

| Loại giới hạn | API hoặc cấu hình thường gặp | Giới hạn điều gì? | Đơn vị |
| --- | --- | --- | --- |
| **Pool acquisition timeout** | Cấu hình của connection pool (không thuộc API JDBC chung) | Thời gian chờ mượn được connection từ pool | Thường là ms |
| **Login timeout** | `DataSource.setLoginTimeout(seconds)` hoặc `DriverManager.setLoginTimeout(seconds)` | Thời gian cho bước thiết lập kết nối/đăng nhập theo driver | Giây |
| **Query timeout** | `Statement.setQueryTimeout(seconds)` | Thời gian driver cho phép statement thực thi trước khi cố hủy | Giây |
| **Network timeout** | `Connection.setNetworkTimeout(executor, milliseconds)` | Thời gian chờ database phản hồi **mỗi yêu cầu mạng** trên connection | Mili giây |
| **Hủy statement** | `Statement.cancel()` | Yêu cầu driver/DBMS hủy statement đang chạy | Không phải timeout |
| **Hủy connection** | `Connection.abort(executor)` | Yêu cầu đóng/hủy connection theo cơ chế JDBC | Không phải timeout |
| **Socket/connect/read timeout** | Thuộc tính riêng của JDBC driver/hệ thống mạng | Các bước kết nối/đọc/ghi socket theo driver | Tùy cấu hình |
| **Deadline nghiệp vụ** | HTTP server, task executor, job scheduler hoặc application logic | Tổng thời gian của một yêu cầu, có thể gồm nhiều thao tác | Tùy ứng dụng |

**Không được dùng các giá trị của bảng như thể chúng cộng hoặc thay thế nhau một cách tự động.** Ví dụ, `setNetworkTimeout` chỉ có thể gọi được **sau khi đã có `Connection`**; nếu `dataSource.getConnection()` đang chờ pool, lệnh đó chưa được thực thi. Tương tự, một request dùng ba câu SQL liên tiếp có thể kéo dài lâu hơn network timeout dù mỗi yêu cầu mạng riêng lẻ đều nhận phản hồi trước hạn.

### Minh họa

Một service đặt:

~~~text
Pool acquisition timeout: 3 giây
Query timeout:            5 giây
Network timeout:          15 giây
HTTP deadline:            20 giây
~~~

Các giá trị này chỉ là một **bộ cấu hình minh họa**, không phải đề xuất chung cho mọi sản phẩm. Mục đích là dành thời gian để driver xử lý việc hủy truy vấn trước khi network timeout buộc đóng connection. Phải cân đối số lượng câu SQL, độ trễ mạng, thời gian thao tác và đặc tính của driver, đồng thời bảo đảm tổng thời gian phù hợp với deadline từ tầng gọi.

## 3. Hợp đồng API `Connection.setNetworkTimeout`

Chữ ký phương thức trong JDBC:

~~~java
void setNetworkTimeout(
        java.util.concurrent.Executor executor,
        int milliseconds) throws java.sql.SQLException;

int getNetworkTimeout() throws java.sql.SQLException;
~~~

Ý nghĩa:

- `executor`: bộ thực thi mà JDBC driver có thể sử dụng khi cần **hủy/đóng connection** vì hết thời gian chờ phản hồi mạng. Driver có thể cần một tác vụ khác để giải phóng tài nguyên thay vì đợi thread đang bị kẹt.
- `milliseconds`: số mili giây chờ database phản hồi **một yêu cầu**; `0` mang ý nghĩa không áp dụng network timeout do API này đặt.
- `getNetworkTimeout()`: trả giá trị timeout đang được báo cáo bởi connection, tính bằng mili giây. Giá trị `0` thể hiện không có network timeout được đặt qua cơ chế này.
- `SQLException`: có thể phát sinh khi connection đóng, giá trị không hợp lệ hoặc driver không thể áp dụng yêu cầu.
- `SQLFeatureNotSupportedException`: một dạng `SQLException` khi driver không hỗ trợ tính năng.

Đọc ví dụ:

~~~java
import java.sql.Connection;
import java.util.concurrent.Executor;

Executor abortExecutor = /* Executor được ứng dụng quản lý */ null;

// Minh họa API; cần một Executor thực thay vì null.
connection.setNetworkTimeout(abortExecutor, 15_000);
int configuredMs = connection.getNetworkTimeout();
~~~

**Đây chỉ là minh họa chữ ký, không phải mã để chạy** vì biến `abortExecutor` đang là `null`. Ví dụ hoàn chỉnh ở mục 5 dùng `ExecutorService` thật.

### Vì sao cần `Executor`?

Nếu thread đang gọi JDBC bị chặn chờ network I/O, việc chỉ dựa vào chính thread đó để đóng kết nối có thể không hiệu quả. Driver được cung cấp một `Executor` để chạy công việc xử lý connection trong tình huống timeout. Tác vụ thực tế và số lần driver sử dụng executor phụ thuộc triển khai.

`Executor` **không phải** nơi ứng dụng gửi câu SQL để chạy bất đồng bộ, cũng không phải `ScheduledExecutorService` tự động đếm thời gian cho từng câu SQL. Driver nhận executor để có cơ chế thực thi hành động của nó khi cần.

Một executor phù hợp nên:

- Còn hoạt động trong suốt thời gian những connection đang sử dụng nó có thể cần hủy.
- Có đủ năng lực chạy công việc abort khi nhiều connection gặp sự cố cùng lúc.
- Không bị chiếm hết thread bởi những tác vụ JDBC dài hoặc các job ứng dụng không liên quan.
- Có chính sách giới hạn tài nguyên, giám sát và tắt đúng lúc ứng dụng shutdown.

Không dùng một executor triển khai đồng bộ kiểu `Runnable::run` chỉ vì nó thỏa interface: nếu driver cần thực hiện abort trên một thread khác, cách đó có thể vô hiệu hóa mục tiêu không bị chặn. Cũng không tạo một `new Thread(...)` riêng cho từng statement một cách không giới hạn.

## 4. Network timeout hoạt động ra sao?

Theo hợp đồng JDBC, network timeout nhắm tới trường hợp **database không phản hồi một yêu cầu giao tiếp** trong khoảng chờ đã đặt. Khi timeout của cơ chế này bị vượt quá, driver phải xử lý connection theo đặc tính của API, thường bao gồm **đánh dấu connection đã đóng và giải phóng tài nguyên**.

~~~mermaid
sequenceDiagram
    participant App as Thread ứng dụng
    participant JDBC as JDBC driver
    participant DB as Database
    participant EX as Executor xử lý abort
    App->>JDBC: setNetworkTimeout(executor, 15000)
    App->>JDBC: PreparedStatement.executeQuery()
    JDBC->>DB: Gửi yêu cầu SQL
    Note over JDBC,DB: Không nhận phản hồi trong giới hạn mạng
    JDBC->>EX: Yêu cầu công việc hủy/đóng connection
    JDBC-->>App: SQLException
    Note over App,JDBC: Không tiếp tục dùng connection này
~~~

Sơ đồ thể hiện **mục đích của API**, không khẳng định luồng nội bộ hoặc thời điểm callback giống nhau với mọi driver. Timeout có thể bị ảnh hưởng bởi socket timeout riêng, hệ điều hành, tình trạng mạng và khả năng thực thi tác vụ abort của executor.

### Những điều network timeout **không** bảo đảm

1. **Không phải tổng thời gian request.** Một kết nối có thể thực hiện nhiều yêu cầu mạng; mỗi lần nhận phản hồi trong hạn nhưng toàn bộ công việc vẫn kéo dài.
2. **Không nhất thiết ngắt SQL đúng tại mốc mili giây tuyệt đối.** Việc hủy/đóng thực tế phụ thuộc driver và mạng.
3. **Không thay thế `setQueryTimeout`.** Truy vấn chậm nhưng DB vẫn liên tục phản hồi có thể cần chính sách query timeout riêng.
4. **Không thay thế timeout mượn connection.** Chưa có connection thì chưa thể gọi `setNetworkTimeout`.
5. **Không bảo đảm transaction được rollback ngay lập tức.** Kết nối có thể đã đóng ở client trong khi database còn đang xử lý, hoặc phản hồi commit có thể đã bị mất.
6. **Không thể xem `0` là mọi timeout của driver đã bị vô hiệu.** Driver/OS vẫn có thể có socket timeout, TCP keepalive hoặc deadline khác.
7. **Không tự mang lại retry an toàn.** Retry phải dựa trên loại thao tác và khả năng xác định kết quả trước đó.

## 5. Ví dụ hoàn chỉnh: đọc hóa đơn với network timeout

Giả sử bảng `invoices` có cột `invoice_id BIGINT` và `total DECIMAL(19,2)`. Chúng ta xây dựng một repository chỉ đọc, dùng `DataSource` và truyền vào một executor thuộc quyền quản lý của ứng dụng.

### 5.1. Repository

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.Executor;
import javax.sql.DataSource;

public final class InvoiceReader {
    private static final int NETWORK_TIMEOUT_MS = 15_000;
    private static final int QUERY_TIMEOUT_SECONDS = 5;

    private final DataSource dataSource;
    private final Executor networkAbortExecutor;

    public InvoiceReader(
            DataSource dataSource, Executor networkAbortExecutor) {
        this.dataSource = Objects.requireNonNull(dataSource);
        this.networkAbortExecutor =
                Objects.requireNonNull(networkAbortExecutor);
    }

    public Optional<BigDecimal> findTotal(long invoiceId)
            throws SQLException {

        String sql = "SELECT total FROM invoices "
                   + "WHERE invoice_id = ?";

        try (Connection connection = dataSource.getConnection()) {
            // Chỉ có thể đặt timeout SAU khi đã mượn connection.
            connection.setNetworkTimeout(
                    networkAbortExecutor, NETWORK_TIMEOUT_MS);

            // Giá trị driver báo cáo; có thể dùng để chẩn đoán
            // trong môi trường test, không cần log mỗi request.
            int actualMs = connection.getNetworkTimeout();

            try (PreparedStatement ps =
                         connection.prepareStatement(sql)) {
                ps.setLong(1, invoiceId);
                ps.setQueryTimeout(QUERY_TIMEOUT_SECONDS);

                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        return Optional.empty();
                    }

                    BigDecimal total = rs.getBigDecimal("total");
                    if (total == null) {
                        throw new SQLException(
                                "Hợp đồng invoice.total không cho phép NULL");
                    }
                    return Optional.of(total);
                }
            }
        }
    }
}
~~~

Ví dụ được viết cho Java 8 trở lên. `Optional.empty()` mang ý nghĩa không tìm thấy hóa đơn; lỗi `SQLException` không được chuyển thành “không có dữ liệu”. `BigDecimal` tránh mất độ chính xác với giá tiền.

Biến `actualMs` trong ví dụ cho thấy có thể đọc lại cấu hình. Ở code production, nên dùng giá trị này cho kiểm thử/chẩn đoán có chọn lọc; nếu trình biên dịch hoặc quy tắc lint cảnh báo biến chưa sử dụng, có thể bỏ dòng khai báo hoặc kiểm tra bằng assertion ở test. **Không cần gọi `getNetworkTimeout` sau mỗi truy vấn** để cơ chế timeout có hiệu lực.

### 5.2. Quản lý `ExecutorService` ở vòng đời ứng dụng

~~~java
import java.math.BigDecimal;
import java.util.Optional;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

ExecutorService abortExecutor = Executors.newFixedThreadPool(2);

try {
    InvoiceReader reader =
            new InvoiceReader(dataSource, abortExecutor);

    Optional<BigDecimal> total = reader.findTotal(1001L);
    total.ifPresent(System.out::println);
} finally {
    // Chỉ tắt executor khi không còn connection nào được
    // ứng dụng dùng với executor này.
    abortExecutor.shutdown();
}
~~~

Đoạn trên giả định `dataSource` đã được cấu hình và đang hoạt động. Với một dịch vụ web, **không tạo rồi shutdown executor cho mỗi HTTP request**. Hãy quản lý một executor phù hợp ở tầng ứng dụng, truyền cho các repository cần nó, rồi shutdown **sau khi đã ngừng nhận việc mới, đóng các connection và kết thúc việc xử lý abort**.

Trong một ứng dụng nhiều kết nối gặp sự cố mạng cùng lúc, pool 2 thread chỉ là ví dụ học tập, không phải giá trị tối ưu. Cần đo mức độ đồng thời và tránh để executor bị nghẽn bởi những công việc khác.

### 5.3. Vì sao đặt 15 giây cho network, 5 giây cho query?

Trong kịch bản minh họa:

- `ps.setQueryTimeout(5)` yêu cầu driver giới hạn thời gian thực thi truy vấn ở mức statement.
- `connection.setNetworkTimeout(executor, 15_000)` có ngưỡng lớn hơn để driver có thêm cơ hội thực hiện hủy truy vấn và nhận phản hồi trước khi connection bị hủy bởi network timeout.

Đây là **một hướng thiết kế thường được khuyến nghị**: query timeout thường nhỏ hơn network timeout để tránh network timeout cắt ngang việc xử lý hủy statement. Nhưng không có công thức cứng “network = 3 lần query” cho mọi driver. Nếu truy vấn có nhiều đợt fetch hoặc nhiều thao tác mạng, yêu cầu về thời gian tổng và transaction cần thiết kế riêng.

### 5.4. Truy vấn chỉ đọc không có nghĩa kết nối luôn an toàn

Nếu xảy ra network timeout, repository không nên bắt ngoại lệ rồi dùng lại `connection` để gọi một statement khác. Dù truy vấn không ghi dữ liệu, **connection đang bị nghi ngờ hoặc đã đóng** và phải được hủy/đưa ra khỏi lưu thông theo cơ chế của driver/pool.

`try-with-resources` sẽ yêu cầu đóng connection khi ra khỏi phạm vi. Với connection pool, đây thường là thao tác trả logical connection về pool; **pool phải được cấu hình và kiểm thử để loại bỏ connection vật lý bị lỗi**, không phát lại session không còn hợp lệ cho request tiếp theo.

## 6. Khi driver không hỗ trợ network timeout

Không phải JDBC driver nào cũng hỗ trợ `setNetworkTimeout` như nhau. Các phản ứng cần phân biệt:

~~~java
import java.sql.Connection;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLException;

try (Connection connection = dataSource.getConnection()) {
    try {
        connection.setNetworkTimeout(abortExecutor, 15_000);
    } catch (SQLFeatureNotSupportedException unsupported) {
        // Chọn chính sách: fail-fast hoặc dùng fallback
        // đã được kiểm thử riêng cho driver đang triển khai.
        throw new SQLException(
                "Driver chưa hỗ trợ JDBC network timeout",
                unsupported.getSQLState(),
                unsupported.getErrorCode());
    }

    // Chỉ dùng connection nếu chính sách timeout đã đạt.
}
~~~

Cách trên minh họa **fail-fast**. Trong production, không bắt buộc phải giữ cause nếu logger tự động xuất thông tin nhạy cảm; tầng xử lý lỗi cần tuân thủ chính sách ghi log. Cũng không nên mặc định mọi `SQLException` từ `setNetworkTimeout` đều là không hỗ trợ: có thể connection đã đóng, driver có lỗi I/O hoặc cấu hình không hợp lệ.

Các hướng xử lý khi không hỗ trợ:

1. **Đánh giá và nâng cấp driver** nếu tính năng cần thiết đã được phiên bản mới hỗ trợ.
2. **Dùng thuộc tính socket/read timeout riêng của driver**, có kiểm thử và tài liệu vận hành rõ ràng; không cho rằng cú pháp/đơn vị giống giữa DBMS.
3. **Đặt statement query timeout** và timeout ở tầng ứng dụng, hiểu rằng chúng không thay thế hoàn toàn network timeout.
4. **Không giảm yêu cầu độ tin cậy một cách âm thầm.** Nếu hệ thống cần chặn thời gian chờ mạng nhưng driver không có cơ chế tương đương, quyết định triển khai phải nêu rủi ro cụ thể.

`getNetworkTimeout()` báo một giá trị cũng không chứng minh rằng driver **thực sự cưỡng chế timeout** trong mọi tình huống lỗi. Cần phép thử mạng có kiểm soát.

### Giá trị `0` và giá trị âm

~~~java
connection.setNetworkTimeout(abortExecutor, 0);
~~~

`0` thể hiện không đặt network timeout qua API này. Không nên dùng câu lệnh đó để “sửa nhanh” những lỗi timeout mà chưa hiểu nguyên nhân, vì có thể khiến thread chờ vô hạn khi mạng không phản hồi.

Giá trị **âm** không hợp lệ và JDBC có thể ném `SQLException`. Hãy validate cấu hình timeout ở startup, tránh truyền các giá trị nhập tự do từ request vào kết nối.

## 7. Phân biệt với `Statement.setQueryTimeout`

`setQueryTimeout` và `setNetworkTimeout` đều liên quan tới thời gian, nhưng hoạt động ở hai mức khác nhau:

~~~java
connection.setNetworkTimeout(abortExecutor, 15_000);

try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id FROM reports WHERE report_date >= ?")) {
    ps.setQueryTimeout(5);
    ps.setDate(1, java.sql.Date.valueOf("2026-11-01"));
    ps.executeQuery();
}
~~~

| Câu hỏi | Query timeout | Network timeout |
| --- | --- | --- |
| Đặt ở đâu? | `Statement` / `PreparedStatement` | `Connection` |
| Đơn vị API | Giây | Mili giây |
| Tác động trực tiếp | Thực thi statement | Chờ phản hồi yêu cầu mạng của connection |
| Khi vượt hạn | Driver cố hủy statement và báo lỗi theo khả năng | Driver xử lý connection bị kẹt, có thể đánh dấu đóng |
| Giữ connection để dùng tiếp? | Phụ thuộc loại lỗi và trạng thái transaction/driver | Không nên tiếp tục dùng connection đã bị network timeout |
| Thích hợp khi | SQL chạy quá lâu, chờ khóa | Đường truyền hoặc giao tiếp DB không phản hồi |
| Bảo đảm tổng thời gian request? | Không | Không |

**`setQueryTimeout(0)`** có nghĩa không áp dụng query timeout qua cơ chế đó. Đừng nhầm với `setNetworkTimeout(..., 0)`.

Một số driver có thể áp dụng timeout truy vấn bằng cách gửi lệnh cancel, đóng statement hoặc dùng cơ chế server. Nếu việc cancel cần giao tiếp mạng mà mạng đã kẹt, statement timeout **có thể không đủ** để giải phóng thread. Network timeout bổ sung một cơ chế ở cấp connection, nhưng hiệu quả cuối cùng vẫn phải được kiểm chứng theo driver.

### Trường hợp fetch nhiều lần

Với một truy vấn có kết quả rất lớn, ứng dụng có thể gọi `ResultSet.next()` hàng nghìn lần. Driver có thể lấy các lô dữ liệu từ server theo `fetchSize`. Network timeout liên quan tới **thời gian chờ phản hồi từng yêu cầu mạng**, không phải số giây tối đa để duyệt hết ResultSet. Một consumer xử lý mỗi dòng rất chậm vẫn có thể giữ connection lâu dù không có lần fetch nào vượt ngưỡng.

Do đó, khi xuất dữ liệu lớn cần thêm deadline job, cơ chế cancel và chính sách không giữ transaction/cursor quá lâu.

## 8. Phân biệt với login timeout và timeout của connection pool

Đây là khác biệt thường gây nhầm lẫn trong code review.

### 8.1. Chờ lấy connection từ pool

~~~java
Connection connection = dataSource.getConnection();
~~~

Nếu pool hết connection và phương thức trên đang chờ, **chưa có `Connection` để gọi `setNetworkTimeout`**. Cần cấu hình thời gian chờ mượn connection tại pool, ví dụ thuộc tính pool-specific (tên và đơn vị thay đổi theo HikariCP, Apache DBCP hoặc pool khác).

Không chuyển `DataSource.setLoginTimeout` thành một giả định rằng mọi pool sẽ dùng chính giá trị đó để giới hạn thời gian chờ mượn connection. Trên nhiều pool, timeout mượn connection là thuộc tính riêng.

### 8.2. Thiết lập/đăng nhập kết nối vật lý

Khi driver phải mở kết nối mạng mới với DBMS, cần kiểm soát thời gian kết nối và đăng nhập. JDBC có:

~~~java
dataSource.setLoginTimeout(10); // Giây, nếu DataSource hỗ trợ.
~~~

`DriverManager.setLoginTimeout(10)` có ý nghĩa khi tạo connection qua `DriverManager`. Ngoài ra driver có thể có thuộc tính TCP connect timeout hoặc socket timeout riêng.

**Network timeout ở cấp `Connection` không thay thế login timeout**, vì chỉ được đặt sau khi connection được tạo. Cũng không nên dùng một con số timeout cho mọi chặng: nếu pool có quá ít connection, tăng network timeout không làm request mượn connection nhanh hơn.

## 9. Hủy statement và hủy connection

Ngoài timeout cấu hình trước, JDBC có hai API để **chủ động yêu cầu hủy**:

### `Statement.cancel()`

~~~java
statement.cancel();
~~~

Đây là lời yêu cầu hủy việc thực thi hiện tại của statement. Nó không phải lệnh `rollback()` và **không bảo đảm câu SQL lập tức dừng**. Thao tác cancel có thể cần giao tiếp với database, và khả năng đáp ứng phụ thuộc driver/DBMS.

Nếu một thread riêng muốn gọi `cancel()` vào statement đang chạy ở thread khác, cần kiểm tra tính thread-safe và hướng dẫn driver. Không nên dùng cùng một `Connection` để thực thi đồng thời các câu SQL không liên quan, vì nhiều driver không bảo đảm an toàn thread trong trường hợp đó.

### `Connection.abort(Executor)`

~~~java
connection.abort(abortExecutor);
~~~

Đây là API yêu cầu driver hủy connection theo cơ chế JDBC, có thể sử dụng executor để không bị chặn bởi cleanup. Nó **khác** với `close()` thông thường và không thể coi như việc rollback đã được xác nhận.

`abort` phù hợp với tình huống nghiêm trọng khi connection không còn lành mạnh hoặc không thể đóng bình thường. Khi đã abort, không tiếp tục đưa connection đó vào giao dịch mới. Nếu dùng pool, cần kiểm tra cơ chế loại bỏ kết nối vật lý bị lỗi.

### Hủy `Future`/thread không đồng nghĩa hủy SQL

~~~java
future.cancel(true);
~~~

`Future.cancel(true)` có thể phát tín hiệu interrupt đến Java thread, nhưng JDBC driver **không bắt buộc** phải dừng một socket read hoặc một query chỉ vì thread bị interrupt. Trong môi trường có deadline, phải kết hợp timeout/cancel của JDBC và DBMS với điều phối thread, chứ không dựa riêng vào `Future.cancel`.

## 10. Transaction: khi mất phản hồi, commit có thể không xác định

Đây là điểm rủi ro nhất khi dùng network timeout trong các thao tác **ghi dữ liệu**.

Giả sử ứng dụng gửi lệnh `COMMIT`. Database có thể đã commit thành công, nhưng phản hồi trên mạng bị mất. Client sau đó nhận `SQLException` hoặc bị network timeout.

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng Java
    participant D as Database
    A->>D: UPDATE invoice ...
    D-->>A: OK
    A->>D: COMMIT
    Note over D: Database có thể đã commit
    Note over A,D: Phản hồi COMMIT bị mất do sự cố mạng
    A-->>A: SQLException / network timeout
    Note over A: Không thể kết luận chắc chắn "đã rollback"
~~~

Lỗi mạng ở thời điểm commit có thể tạo trạng thái **kết quả không xác định** (*uncertain commit outcome*). Hệ quả:

- Không được mặc định `SQLException` ở `commit()` có nghĩa database chắc chắn chưa commit.
- Gọi `rollback()` sau khi connection đã mất **không chứng minh** dữ liệu được hoàn tác.
- Không tự động retry một lệnh chuyển tiền/ghi hóa đơn nếu lần trước có thể đã commit, vì có nguy cơ tạo giao dịch trùng.
- Khi cần retry an toàn, phải có **idempotency key**, ràng buộc duy nhất, trạng thái nghiệp vụ có thể truy vấn lại hoặc quy trình đối soát.
- Nếu connection đã đóng/abort, không nên tiếp tục `commit` hoặc `rollback` trên cùng connection để “thử cho chắc”.

### Mẫu transaction với xử lý lỗi best effort

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.concurrent.Executor;
import javax.sql.DataSource;

public final class PaymentWriter {
    private final DataSource dataSource;
    private final Executor abortExecutor;

    public PaymentWriter(DataSource dataSource, Executor abortExecutor) {
        this.dataSource = dataSource;
        this.abortExecutor = abortExecutor;
    }

    public void applyPayment(long paymentId, long invoiceId)
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            connection.setNetworkTimeout(abortExecutor, 15_000);
            connection.setAutoCommit(false);

            boolean commitAttempted = false;

            try {
                // payment_id được bảo vệ bằng UNIQUE/PRIMARY KEY
                // ở schema để hỗ trợ idempotency nghiệp vụ.
                String sql = "INSERT INTO payments "
                           + "(payment_id, invoice_id) VALUES (?, ?)";

                try (PreparedStatement ps =
                             connection.prepareStatement(sql)) {
                    ps.setQueryTimeout(5);
                    ps.setLong(1, paymentId);
                    ps.setLong(2, invoiceId);
                    ps.executeUpdate();
                }

                commitAttempted = true;
                connection.commit();

            } catch (SQLException | RuntimeException failure) {
                // Chỉ cố rollback nếu connection chưa báo đóng.
                // Ngay cả khi rollback báo OK, phải đánh giá
                // tình trạng của lần commit đã thử.
                try {
                    if (!connection.isClosed()) {
                        connection.rollback();
                    }
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }

                if (commitAttempted) {
                    // Ghi sự kiện "commit outcome uncertain" tại
                    // tầng điều phối theo chính sách; KHÔNG retry mù.
                }

                throw failure;
            }
        }
    }
}
~~~

Ví dụ giả định có bảng `payments` với hai cột tương ứng và `payment_id` là khóa duy nhất. Đây là **mẫu cấu trúc transaction**, không phải toàn bộ nghiệp vụ thanh toán. Một hệ thống thực cần kiểm tra số dòng, định danh thao tác, quyền truy cập, số tiền và khả năng xác minh lại trạng thái đã ghi.

Biến `commitAttempted` chỉ cho biết phía Java đã **bắt đầu thử commit**. Nó không thể tự phân biệt commit thành công, commit thất bại hay phản hồi thất lạc. Sau lỗi, caller phải **kiểm tra trạng thái qua một connection mới** và áp dụng idempotency/đối soát trước khi quyết định thử lại.

### Kể cả auto-commit cũng có thể bất định

Với `autoCommit=true`, một câu `INSERT` riêng lẻ có thể đã được database ghi và commit trước khi phản hồi bị mất. Do đó, thiếu lệnh `commit()` tường minh **không khiến retry tự động trở nên an toàn**. Bất kỳ thao tác ghi nào cần khả năng retry đều nên có một khóa nghiệp vụ hoặc cơ chế idempotency.

## 11. Trạng thái connection và connection pool sau timeout

Một connection đã gặp network timeout có thể bị driver đánh dấu closed. `try-with-resources` sẽ cố đóng logical connection; với pool, cơ chế quản lý phải nhận biết/loại bỏ physical connection hỏng.

Những nguyên tắc vận hành:

1. **Không tái sử dụng connection đã gặp network timeout** cho câu SQL tiếp theo.
2. **Không mặc định `isValid()` hoặc `isClosed()` là cơ chế phục hồi.** Đây chỉ là công cụ kiểm tra trong những điều kiện nhất định; connection hỏng nên bị loại theo chính sách của driver/pool.
3. **Không tái tạo connection vô hạn.** Nếu database hay đường mạng đang sự cố, retry tràn lan làm cạn pool và gây thêm tải.
4. **Theo dõi lỗi theo loại.** Phân biệt login timeout, acquisition timeout, query timeout, network timeout, SQLState và trạng thái commit không rõ.
5. **Kiểm soát thiết lập trên pooled connection.** `setNetworkTimeout` có thể thay đổi trạng thái logical/physical connection; cần biết pool có reset giá trị khi trả lại không. Nếu không, đặt cấu hình chuẩn ở thời điểm mượn connection hoặc thông qua pool/driver được hỗ trợ.
6. **Đừng reset network timeout bằng `setNetworkTimeout(..., 0)` trên connection đã nghi hỏng.** Reset trên connection lành mạnh cần theo contract pool và phạm vi sở hữu; trên connection đã bị đóng thì thao tác có thể ném lỗi.
7. **Giám sát executor dùng cho abort.** Nếu executor bị shutdown hoặc cạn thread trong một đợt lỗi mạng, cơ chế hủy connection có thể không hoạt động đúng lúc.

### Cách thiết kế vòng đời của executor

Ở ứng dụng server:

~~~text
Startup
  ├─ Cấu hình DataSource / pool
  └─ Khởi tạo executor dành cho JDBC abort

Mỗi request
  ├─ getConnection()
  ├─ setNetworkTimeout(executor, ...)
  ├─ prepare/execute/read
  └─ close() / trả connection vào pool

Shutdown
  ├─ Ngừng nhận request mới
  ├─ Đợi/hủy các thao tác DB đang hoạt động theo chính sách
  ├─ Đóng DataSource/pool
  └─ Shutdown executor
~~~

Điều quan trọng là **executor còn sống khi driver vẫn có thể cần chạy hành động abort**. Tránh shutdown executor ngay sau khi gọi `setNetworkTimeout` mà chưa đóng các connection tương ứng.

## 12. Quy tắc chọn các timeout phối hợp

Thay vì chọn các giá trị độc lập một cách tùy ý, hãy xuất phát từ **SLO của nghiệp vụ** và hành vi của driver:

~~~text
Request deadline
    ├── thời gian mượn connection
    ├── thời gian thực thi 1..N statements
    ├── thời gian đọc/ghi kết quả
    └── thời gian chuyển đổi/trả dữ liệu
~~~

Ví dụ một thao tác đọc có yêu cầu hoàn tất tương đối nhanh:

| Thành phần | Giá trị minh họa | Lý do |
| --- | --- | --- |
| Pool acquisition | 2 giây | Không đợi pool quá lâu |
| Login/connect | 5 giây | Không giữ thread nếu mở connection vật lý thất bại |
| Query timeout | 4 giây | Giới hạn truy vấn chậm |
| Network timeout | 12 giây | Dự phòng cho cancel và giao tiếp mạng bị kẹt |
| HTTP deadline | 15 giây | Ranh giới tổng của request phía ứng dụng |

Không cộng các con số này rồi coi tổng là deadline. Thời gian thực tế có thể chồng lấn hoặc không chồng lấn, gồm nhiều câu SQL, nhiều lần fetch và retry. Các giá trị chỉ có ý nghĩa khi được **kiểm thử với driver thật** và thống nhất giữa tầng web, pool, driver và server database.

Một số DBMS cung cấp `statement_timeout` hoặc `lock_timeout` ở cấp server. Các thiết lập này có thể là lớp bảo vệ bổ sung, nhất là khi query timeout ở JDBC không được driver xử lý như kỳ vọng. Nhưng chúng cũng **không thay thế** chính sách connection/network timeout của client.

## 13. Kiểm thử network timeout có kiểm soát

Một câu SQL chạy lâu không đủ để chứng minh `setNetworkTimeout` đã hoạt động: SQL chậm và **mạng không phản hồi** là hai sự cố khác nhau.

### 13.1. Các bài kiểm thử nên có

| Kịch bản | Mục tiêu xác minh |
| --- | --- |
| `setNetworkTimeout` trên connection lành mạnh | Driver nhận cấu hình và `getNetworkTimeout` phản ánh giá trị mong đợi |
| `milliseconds = 0` | Cấu hình tắt network timeout qua API; không có lỗi ngoài dự kiến |
| Giá trị âm | Phát hiện sai cấu hình, báo `SQLException` |
| Driver không hỗ trợ | `SQLFeatureNotSupportedException` hoặc lỗi tương ứng; ứng dụng chọn fallback rõ ràng |
| Truy vấn chậm nhưng mạng hoạt động | Query timeout và logic hủy statement |
| Network path mất phản hồi khi đang chờ DB | Driver có giới hạn chờ; ứng dụng thoát, connection không được tái sử dụng |
| Mất kết nối khi đọc nhiều đợt `ResultSet` | Xử lý lỗi và đóng tài nguyên, không trả dữ liệu hoàn chỉnh giả |
| Mất phản hồi quanh `commit()` | Đánh dấu outcome bất định và xác minh qua connection mới |
| Nhiều connection cùng bị kẹt | Executor abort không bị nghẽn, pool loại bỏ connection hỏng |
| Timeout khi `getConnection()` đang chờ pool | Pool acquisition timeout hoạt động, không nhầm với network timeout |
| Client hủy request | Tài nguyên JDBC được cleanup, không chỉ `Future.cancel(true)` |
| Connection được trả về pool rồi mượn lại | Giá trị timeout và trạng thái connection được khôi phục theo chính sách |

### 13.2. Tạo sự cố mạng khác với tạo SQL chậm

Có thể dùng một **network proxy dành cho kiểm thử**, công cụ fault injection hoặc môi trường container để chặn/hoãn dữ liệu giữa JDBC client và database. Điều kiện là phải nằm trong hệ thống **được phép kiểm thử**, không can thiệp vào database production. Ghi nhận:

- Thời điểm client gửi yêu cầu và thời điểm bắt đầu chặn phản hồi.
- Giá trị `getNetworkTimeout()` và cấu hình socket timeout của driver.
- Thời điểm JDBC ném `SQLException`, SQLState và trạng thái `Connection`.
- Tài nguyên sau lỗi: còn thread/connection/statement treo hay không.
- Database có giữ transaction/khóa không, pool có loại bỏ session không.
- Hệ thống có thể tiếp tục truy vấn bằng **connection mới** sau khi mạng hồi phục hay không.

Kết quả có thể khác nhau tùy lỗi mạng xảy ra lúc **đang kết nối**, **đang gửi yêu cầu**, **đang chờ phản hồi**, **đang fetch dữ liệu** hoặc **đang commit**. Vì vậy cần cố ý mô tả vị trí fault injection trong báo cáo.

### 13.3. Không dựa vào sleep như bằng chứng

Một test kiểu:

~~~java
ps.setQueryTimeout(2);
ps.execute("SELECT long_running_function()");
~~~

chỉ kiểm tra được một phần cơ chế statement timeout, tùy DBMS và cách triển khai routine. Nó **không chứng minh** JDBC network timeout đã can thiệp, vì database có thể chủ động báo lỗi/cancel trong khi mạng vẫn bình thường.

Đo **thời gian thực tế** và trạng thái tài nguyên ở cả các kịch bản query chậm và network stall. Với test có thể treo, đặt deadline ngoài process hoặc cơ chế hủy ở tầng test harness để không khóa CI vô hạn.

## 14. Logging, metric và xử lý lỗi an toàn

Trong production, chỉ ghi những thông tin cần thiết để điều tra. Ví dụ:

~~~text
event=jdbc_network_timeout
query_id=invoice.findTotal.v1
trace_id=<ID do server tạo>
network_timeout_ms=15000
query_timeout_seconds=5
connection_discarded=true
sqlstate=<mã đã chuẩn hóa nếu có>
~~~

Tránh:

- In nguyên `PreparedStatement.toString()` vì driver có thể đưa tham số vào chuỗi.
- Ghi password/URL connection có chứa thông tin xác thực.
- Log giá trị `ResultSet`, dữ liệu khách hàng hoặc payload nhạy cảm.
- Đưa nguyên văn message/stack trace JDBC chưa kiểm soát ra response HTTP.
- Dùng trace ID hoặc ID giao dịch duy nhất làm nhãn metric, vì gây **high cardinality**.

Các metric hữu ích gồm thời gian mượn connection, thời gian truy vấn, số lỗi timeout theo loại, tỷ lệ kết nối bị loại khỏi pool và số thread executor abort đang bận. Nhóm sự kiện bằng **mã truy vấn cố định**, loại thao tác, loại timeout và driver/DBMS khi phù hợp; không gắn tham số người dùng vào nhãn.

Nếu có `SQLException`, có thể đọc `getSQLState()` và `getErrorCode()` để phục vụ phân loại nội bộ, nhưng không nên tự suy rằng một mã SQLState cụ thể luôn biểu thị network timeout trên mọi driver. Đặt mã lỗi nghiệp vụ ổn định ở tầng ứng dụng rồi đối chiếu tài liệu driver khi cần.

## 15. Sai lầm thường gặp

### 15.1. Cho rằng network timeout giới hạn toàn bộ request

~~~java
connection.setNetworkTimeout(executor, 10_000);
runManyQueries(connection);
~~~

Mỗi truy vấn có thể hoàn tất yêu cầu mạng trong 10 giây nhưng tổng thời gian vẫn lên hàng phút. Cần deadline ở tầng nghiệp vụ và giới hạn các tác vụ con.

### 15.2. Đặt network timeout ngắn hơn query timeout

~~~java
connection.setNetworkTimeout(executor, 2_000);
ps.setQueryTimeout(30);
~~~

Với truy vấn hợp lệ mất nhiều thời gian chờ DB phản hồi, connection có thể bị hủy bởi network timeout trước khi query timeout có cơ hội hoạt động; việc hủy câu SQL cũng có thể không nhận được phản hồi. Cần xác định chính sách phối hợp và đo trên driver thực tế.

### 15.3. Tắt executor khi connection còn hoạt động

~~~java
ExecutorService executor = Executors.newFixedThreadPool(1);
connection.setNetworkTimeout(executor, 15_000);
executor.shutdown(); // Quá sớm: driver có thể còn cần executor.
~~~

Hãy để application/service quản lý executor dài hạn và shutdown sau khi các connection không còn phụ thuộc nó.

### 15.4. Bắt lỗi rồi tiếp tục dùng connection

~~~java
try {
    ps.executeQuery();
} catch (SQLException ignored) {
    // Sai: không xác minh trạng thái connection.
}
runNextStatement(connection);
~~~

Sau network timeout hoặc lỗi I/O nghiêm trọng, không dùng lại connection. Phải giải phóng và mượn connection mới theo chính sách, đồng thời xử lý trạng thái transaction.

### 15.5. Retry thanh toán chỉ vì nhận timeout

~~~java
try {
    commitPayment();
} catch (SQLException failure) {
    commitPayment(); // Nguy cơ ghi hai lần.
}
~~~

Phản hồi commit có thể bị mất dù database đã commit. Cần khóa idempotency, kiểm tra trạng thái qua connection mới và đối soát trước khi thực hiện lại.

### 15.6. Coi `getNetworkTimeout` là bằng chứng kiểm thử đầy đủ

`getNetworkTimeout() == 15000` chỉ nói driver báo có cấu hình 15 giây. Muốn chứng minh hiệu lực, phải gây một **network stall** trong môi trường test và kiểm tra thời gian, trạng thái connection sau lỗi và việc cleanup.

## 16. Bài tập thực hành

### Bài 1 — Phân biệt phạm vi

Một ứng dụng dùng connection pool, mất 8 giây để mượn connection rồi mất 1 giây để thực thi câu SQL. `setNetworkTimeout(executor, 3_000)` được gọi sau `getConnection()`. Cơ chế này có tự làm thời gian mượn connection dưới 3 giây không?

**Gợi ý:** Không. Khi còn đang chờ `getConnection()`, chưa có `Connection` để đặt network timeout. Cần cấu hình pool acquisition timeout.

### Bài 2 — Sửa thứ tự timeout

Hệ thống dùng `setQueryTimeout(60)` và `setNetworkTimeout(executor, 5_000)`. Khi database xử lý truy vấn lâu và không gửi phản hồi, hệ quả nào có thể xảy ra? Nên cân nhắc thứ tự các ngưỡng timeout như thế nào?

**Gợi ý:** Network timeout có thể hủy connection sớm trước khi statement query timeout được kích hoạt. Thường chọn network timeout lớn hơn query timeout, nhưng vẫn kiểm thử theo driver và deadline nghiệp vụ.

### Bài 3 — Executor và vòng đời

Một controller tạo `ExecutorService` mới trong mỗi request, gọi `setNetworkTimeout` rồi `shutdownNow()` ngay sau khi tạo statement. Vì sao thiết kế này nguy hiểm? Hãy đề xuất lớp chịu trách nhiệm sở hữu executor.

**Gợi ý:** Driver có thể cần executor khi xử lý network stall ở thời điểm sau; nên sở hữu executor tại application/service lifecycle và chỉ tắt khi các connection đã kết thúc.

### Bài 4 — Network timeout có phải query timeout?

Một truy vấn có kết quả hàng triệu dòng, mỗi lần fetch được phản hồi trong 200 ms, nhưng consumer xử lý chậm trong 15 phút. Network timeout 5 giây có đảm bảo toàn bộ export dưới 5 giây không?

**Gợi ý:** Không; timeout này không phải deadline toàn bộ quá trình. Cần timeout job, backpressure, cursor/page strategy và chính sách đóng tài nguyên.

### Bài 5 — Commit bất định

Ứng dụng gửi `COMMIT`, sau đó nhận lỗi kết nối. Có thể khẳng định database chưa ghi dữ liệu không? Vì sao retry một giao dịch tạo hóa đơn có thể làm trùng dữ liệu?

**Gợi ý:** Không. DB có thể đã commit nhưng response bị mất. Cần idempotency key, ràng buộc duy nhất và đối chiếu qua connection mới trước khi retry.

### Bài 6 — Kịch bản kiểm thử

Hãy thiết kế hai test riêng: một test gây **SQL chậm nhưng mạng hoạt động**, một test **chặn phản hồi mạng** giữa DB và JDBC client. Mỗi test nên xác nhận những gì?

**Gợi ý:** Test SQL chậm kiểm tra `setQueryTimeout`/cancel; test mạng kiểm tra `setNetworkTimeout`, connection closed/discarded, executor đủ hoạt động và không còn thread/connection treo.

---

## 17. Checklist khi đưa vào production

- [ ] Tôi đã phân biệt rõ pool acquisition, login/connect, query, network và request deadline.
- [ ] Tôi biết đơn vị: `setQueryTimeout` dùng **giây**, `setNetworkTimeout` dùng **mili giây**.
- [ ] `setNetworkTimeout` được gọi trên connection đã mượn, **trước** các thao tác SQL cần bảo vệ.
- [ ] Tôi đã kiểm tra driver hỗ trợ `setNetworkTimeout` và có chính sách khi không hỗ trợ.
- [ ] Tôi dùng executor hoạt động độc lập, có vòng đời đủ dài và giới hạn tài nguyên.
- [ ] Query timeout và network timeout được phối hợp theo yêu cầu nghiệp vụ, không chọn ngẫu nhiên.
- [ ] Tôi không xem network timeout là deadline cho toàn bộ request hay toàn bộ ResultSet.
- [ ] Sau network timeout, tôi không tiếp tục dùng connection; pool xử lý loại bỏ kết nối lỗi.
- [ ] Với các thao tác ghi, tôi có idempotency/đối soát cho kết quả commit bất định.
- [ ] Tôi đã thử nghiệm network stall **thật** trên driver/DBMS mục tiêu, không chỉ chạy SQL sleep.
- [ ] Tôi đã kiểm tra hành vi timeout khi connection pool cạn và khi nhiều connection cùng hỏng.
- [ ] Log/metric không chứa tham số SQL, dữ liệu khách hàng hoặc thông tin xác thực.

**Kết luận:** `Connection.setNetworkTimeout(Executor, int)` là công cụ JDBC để giới hạn **thời gian chờ phản hồi giao tiếp mạng trên một connection**, sử dụng executor khi cần hủy connection bị kẹt. Để một ứng dụng ổn định, phải kết hợp nó với query timeout, login/pool timeout, deadline nghiệp vụ, quản lý transaction và chiến lược xử lý lỗi an toàn. Đặc biệt, **mất phản hồi không đồng nghĩa database chưa commit**; hãy xác minh kết quả qua kết nối mới trước khi retry những thao tác ghi quan trọng.
