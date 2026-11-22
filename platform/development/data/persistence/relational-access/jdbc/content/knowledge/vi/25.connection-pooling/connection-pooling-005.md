# Phân biệt thời gian chờ mượn và thời gian tạo kết nối trong JDBC

Trong ứng dụng Java sử dụng **JDBC**, lời gọi `DataSource.getConnection()` đôi khi mất hàng trăm mili giây hoặc thất bại vì timeout. Một kết luận dễ mắc là “database tạo kết nối chậm”. Thực tế, ứng dụng có thể đang **chờ một kết nối có sẵn trong pool được trả lại**, trong khi việc tạo kết nối vật lý tới database hoàn toàn bình thường. Ngược lại, khi pool khởi động hoặc phải mở thêm kết nối, lỗi DNS, TCP, TLS hay xác thực có thể làm việc **tạo kết nối mới** chậm, ngay cả khi pool còn chỗ.

Bài học thuộc chương **Pool kết nối** của module **JDBC**. Mục tiêu là phân biệt hai loại thời gian và timeout, nắm vòng đời kết nối, đo đạc bằng API Java/JDBC, tìm nguyên nhân gây nghẽn và cấu hình giới hạn thời gian phù hợp. Nội dung gắn với `DataSource`, `Connection`, `PreparedStatement`, `ResultSet`, CRUD, transaction, batching và xử lý lỗi bằng các API chuẩn.

**Nguyên tắc trung tâm:** **thời gian chờ mượn** là thời gian để một yêu cầu *nhận quyền sử dụng kết nối từ pool*; **thời gian tạo kết nối** là thời gian để *thiết lập một kết nối vật lý mới tới database*. Lời gọi `getConnection()` có thể bao gồm một hoặc cả hai việc tùy thiết kế pool, trạng thái hiện tại và chính sách tạo kết nối.

## 1. Mượn kết nối khác với mở một kết nối vật lý

Nếu ứng dụng kết nối trực tiếp qua `DriverManager.getConnection(...)` mà không dùng pool, mỗi lời gọi thường khởi tạo một kết nối vật lý mới, với các bước như mở socket và xác thực.

Trong ứng dụng có pool, `DataSource.getConnection()` thường trả một **kết nối logic** đại diện cho một kết nối vật lý được quản lý bởi pool. Khi đóng kết nối logic, pool thường thu hồi quyền sử dụng để yêu cầu khác mượn lại.

```text
                     Ứng dụng Java
                           │
                           ▼
                 DataSource.getConnection()
                           │
                    ┌──────┴───────┐
                    │ Pool có kết  │
                    │ nối rảnh?    │
                    └──────┬───────┘
                Có ────────┼──────── Không
                 │         │          │
                 ▼         │          ▼
          Lấy kết nối      │   Được phép tạo thêm?
          logic/rảnh       │       /        \
                 │         │     Có          Không
                 │         │      │             │
                 │         │      ▼             ▼
                 │         │  Tạo kết nối     Chờ kết nối
                 │         │  vật lý mới      đang bận trả về
                 │         │      │             │
                 └─────────┴──────┴─────────────┘
                           │
                 (Kiểm tra hợp lệ nếu cần)
                           │
                           ▼
                 Trả Connection cho code
                           │
                   Thực thi SQL/transaction
                           │
                           ▼
                    Connection.close()
                           │
                   Trả quyền sử dụng cho pool
```

Đây là sơ đồ **khái niệm**. Pool thực tế có thể tạo kết nối ở luồng nền, kiểm tra trước khi cấp phát, mở kết nối song song, ưu tiên các yêu cầu đang chờ hoặc loại bỏ kết nối hết hạn. Không được suy rằng từng ô trong sơ đồ luôn chạy tuần tự bên trong `getConnection()`.

Những khái niệm cần phân biệt:

- **Kết nối vật lý:** phiên kết nối thật tới DBMS; có socket, xác thực và trạng thái phiên server.
- **Kết nối logic:** đối tượng `Connection` mà ứng dụng nhận từ pool; `close()` thường trả nó về pool.
- **Kết nối đang sử dụng (*active/in-use*):** đã được một request hoặc transaction mượn, chưa trả.
- **Kết nối rảnh (*idle*):** có sẵn trong pool và có thể được cấp phát sau khi đáp ứng điều kiện kiểm tra.
- **Yêu cầu đang chờ (*pending/waiting*):** đã gọi `getConnection()` nhưng chưa được cấp phát kết nối.
- **Đang tạo kết nối (*creating*):** pool/driver đang thiết lập kết nối vật lý mới, chưa sẵn sàng để dùng.

Nếu pool có 20 kết nối vật lý và tất cả 20 kết nối đang bận, yêu cầu thứ 21 có thể **chờ mượn** dù không có một thao tác tạo kết nối mới nào. Ngược lại, khi pool chỉ có 2 kết nối và chính sách cho phép tăng đến 20, một yêu cầu có thể phải đợi **tạo kết nối** hoặc đợi luồng tạo kết nối nền hoàn tất.

## 2. Hai khoảng thời gian đo hai vấn đề khác nhau

### 2.1. Thời gian chờ mượn (*connection acquisition/borrow time*)

Từ góc nhìn code Java:

```java
long begin = System.nanoTime();
Connection connection = dataSource.getConnection();
long acquireNanos = System.nanoTime() - begin;
```

`acquireNanos` đo **thời gian lời gọi `getConnection()` mất để trả kết nối**. Trong một pooled `DataSource`, giá trị này có thể chứa:

- Thời gian chờ kết nối rảnh.
- Chi phí cấp phát proxy/đối tượng logic.
- Kiểm tra kết nối còn hợp lệ.
- Chờ pool tạo kết nối vật lý mới hoặc hoạt động tạo kết nối diễn ra trong chính lời gọi.
- Chi phí đồng bộ, lập lịch luồng và các hoạt động nội bộ khác của pool.

Vì thế, **độ trễ `getConnection()` không phải số đo thuần túy của thời gian xếp hàng**. Muốn có số đo queue wait riêng hoặc thời gian khởi tạo vật lý, cần metric/tracing của pool hoặc driver nếu có.

### 2.2. Thời gian tạo kết nối (*physical connection establishment time*)

Thời gian tạo mới bắt đầu khi driver/pool thực sự khởi tạo một phiên kết nối vật lý; nó có thể gồm:

1. Phân giải DNS hoặc xác định endpoint.
2. Thiết lập TCP/socket và đi qua proxy, firewall hoặc mạng riêng.
3. Thương lượng TLS nếu có cấu hình bảo mật tương ứng.
4. Xác thực tài khoản và đàm phán giao thức với server.
5. Khởi tạo phiên, các thiết lập mặc định và thao tác kiểm tra/khởi tạo riêng của driver hoặc pool.

Các giai đoạn trên là ví dụ thường gặp; giao thức và ranh giới đo của từng driver có thể khác. Thời gian tạo kết nối có thể tăng do mạng, DB quá tải, số phiên đạt giới hạn, TLS hoặc xác thực, **không nhất thiết do thiếu kết nối rảnh trong pool**.

### 2.3. Quan hệ giữa hai khoảng thời gian

Có thể hình dung:

```text
T_acquire_observed = thời gian từ lúc gọi getConnection()
                     đến khi nhận Connection hoặc nhận lỗi

T_create = thời gian xây dựng một physical connection mới

T_queue = thời gian đợi pool tìm được khả năng cấp phát
```

Trong thiết kế đồng bộ đơn giản, `T_acquire_observed` có thể gần bằng `T_queue + T_create + T_validate + overhead`. Nhưng đây **không phải công thức tổng quát**: pool có thể tạo kết nối ở luồng nền, làm các bước chồng lấn hoặc có nhiều lần thử/kiểm tra. Một yêu cầu có thể chỉ chờ tạo kết nối đang diễn ra, không phải tự tạo kết nối đó.

**Không tính `T_create = T_acquire_observed` bằng phép đồng nhất.** Để xác định tác nhân chậm, cần xem thêm các số đo *active/idle/pending*, số lượng kết nối đang tạo, lỗi tạo kết nối và thời gian driver kết nối với server.

## 3. Phân biệt các loại timeout trong hệ thống JDBC

Trong thực tế thường có nhiều “đồng hồ” hoạt động ở những tầng khác nhau:

| Giới hạn / timeout | Bắt đầu khi nào | Ý nghĩa | Thường cấu hình ở đâu |
| --- | --- | --- | --- |
| **Borrow/acquisition timeout** | Ứng dụng yêu cầu lấy `Connection` từ pool | Thời gian tối đa được phép chờ pool cấp phát, theo cách pool định nghĩa | **Thư viện pool**, chẳng hạn thuộc tính kiểu `connectionTimeout` hoặc `maxWait` |
| **Connect timeout** | Driver thử thiết lập kết nối mạng mới | Giới hạn một phần hoặc toàn bộ quá trình kết nối tới endpoint, theo driver | JDBC driver/network, có thể là thuộc tính `connectTimeout` |
| **Login timeout** | Bắt đầu quá trình thiết lập kết nối/đăng nhập | Giới hạn thời gian cố gắng kết nối/đăng nhập theo hợp đồng API và driver | `DataSource.setLoginTimeout(seconds)` hoặc `DriverManager.setLoginTimeout(seconds)` |
| **Validation timeout** | Pool kiểm tra một kết nối có còn dùng được | Giới hạn kiểm tra health, chẳng hạn `Connection.isValid(seconds)` | Pool và/hoặc driver |
| **Socket/read timeout** | Chờ dữ liệu qua socket trong một hoạt động mạng | Giới hạn thời gian đọc mạng, có thể áp dụng lúc thực thi SQL hoặc nhận dữ liệu | Driver/socket, thường là thuộc tính riêng |
| **Query timeout** | Thực thi một statement theo hợp đồng driver | Yêu cầu giới hạn thời gian chạy câu SQL | `Statement.setQueryTimeout(seconds)` |
| **Transaction timeout** | Bắt đầu transaction hoặc phạm vi nghiệp vụ | Giới hạn vòng đời transaction theo framework/server | Transaction manager/server, không phải một cấu hình JDBC chuẩn chung |

**Không đặt dấu bằng giữa borrow timeout và connect/login timeout.** Một pool có thể vẫn xếp hàng chờ vì đã dùng hết kết nối, dù mở kết nối mới rất nhanh. Ngược lại, driver có thể mất thời gian thử tới server ngay khi pool chưa đầy.

Cần phân biệt đơn vị:

- Các API JDBC như `DataSource.setLoginTimeout(int seconds)` và `Statement.setQueryTimeout(int seconds)` dùng **giây**.
- Thuộc tính cấu hình pool/driver có thể dùng **mili giây, giây hoặc giá trị dạng chuỗi**, tùy sản phẩm; phải đọc tài liệu phiên bản đang triển khai.
- `Connection.isValid(int timeout)` nhận tham số **giây**; `0` có ý nghĩa đặc biệt theo JDBC. Pool có thể có thêm timeout validation riêng.
- `System.nanoTime()` trả đơn vị nano giây theo một mốc đơn điệu, phù hợp đo **khoảng thời gian**; không phải timestamp để hiển thị giờ.

Một lỗi cấu hình điển hình là đặt “`2000`” với ý định **2 giây**, nhưng thuộc tính thực tế hiểu **2000 giây**, hoặc ngược lại. Trong tài liệu vận hành nên ghi rõ **thuộc tính, đơn vị, tầng áp dụng và giá trị**.

## 4. `DataSource.setLoginTimeout()` không phải API chuẩn để cấu hình hàng đợi pool

`javax.sql.DataSource` có phương thức:

```java
dataSource.setLoginTimeout(10); // giây
int seconds = dataSource.getLoginTimeout();
```

Theo ý nghĩa JDBC, login timeout liên quan thời gian datasource chờ khi cố gắng **thiết lập kết nối đến database**. Nhưng `DataSource` chỉ là interface; mỗi implementation, đặc biệt pool bên thứ ba, có thể xử lý/ủy quyền cấu hình này khác nhau. **Không được suy rằng `setLoginTimeout(10)` luôn đặt giới hạn mượn pool là 10 giây**.

`DriverManager.setLoginTimeout(...)` cũng áp dụng ở một cơ chế khác: quản lý việc thiết lập kết nối qua `DriverManager`; không phải cấu hình chung cho mọi connection pool:

```java
import java.sql.DriverManager;

DriverManager.setLoginTimeout(10); // giây, phạm vi DriverManager
```

Trong ứng dụng sử dụng pool, thời gian chờ cấp phát thường có **thuộc tính riêng do pool định nghĩa**. Một số thư viện đặt tên là `connectionTimeout`, `maxWaitMillis`, `maxWait` hoặc cách gọi khác. Chúng không phải các phương thức thống nhất trong `javax.sql.DataSource`.

**Ví dụ riêng HikariCP** (thư viện bên ngoài JDBC, chỉ để thấy rõ các giới hạn):

```java
// Đoạn cấu hình minh họa khi dự án đã có thư viện HikariCP.
// Không phải API chuẩn của javax.sql.DataSource.
HikariConfig config = new HikariConfig();

config.setJdbcUrl(jdbcUrl);
config.setUsername(dbUser);
config.setPassword(dbPassword);

config.setMaximumPoolSize(16);
config.setConnectionTimeout(2_000);  // ms: thời gian chờ lấy connection
config.setValidationTimeout(1_000);  // ms: thời gian giới hạn validation

HikariDataSource dataSource = new HikariDataSource(config);
```

Ví dụ giả định các biến `jdbcUrl`, `dbUser`, `dbPassword` đã được cung cấp an toàn; cần import `com.zaxxer.hikari.HikariConfig` và `HikariDataSource`, thêm dependency và cấu hình đầy đủ theo dự án. **`setConnectionTimeout(2_000)` là thuộc tính borrow của HikariCP**, không phải `DriverManager.setLoginTimeout(2_000)` và không thay thế hoàn toàn cấu hình timeout mạng/driver. Các giới hạn của HikariCP cũng có điều kiện và giá trị tối thiểu theo phiên bản.

Khi dùng Tomcat JDBC Pool, Apache Commons DBCP, application server hay framework khác, phải xác định **đúng tên và phạm vi timeout của implementation đó**, thay vì copy cấu hình của HikariCP.

## 5. Đo chính xác phần nào từ code ứng dụng?

Dùng `System.nanoTime()` để đo thời gian ứng dụng đợi `getConnection()`. Ví dụ repository sau tách hai mốc: **lấy kết nối** và **thực thi/trả dữ liệu của một truy vấn**.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import java.util.concurrent.TimeUnit;

public final class CustomerLookup {
    private final DataSource dataSource;

    public CustomerLookup(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<String> findEmail(long customerId)
            throws SQLException {

        long acquisitionStarted = System.nanoTime();
        Connection connection;

        try {
            connection = dataSource.getConnection();
        } catch (SQLException failure) {
            long elapsed = System.nanoTime() - acquisitionStarted;
            recordDuration("jdbc.acquire.failure", elapsed);
            throw failure;
        }

        long acquiredAt = System.nanoTime();
        recordDuration(
                "jdbc.acquire.success",
                acquiredAt - acquisitionStarted);

        String sql = "SELECT email FROM customers WHERE id = ?";

        try (Connection borrowed = connection) {
            long sqlStarted = System.nanoTime();

            try (PreparedStatement statement =
                         borrowed.prepareStatement(sql)) {
                statement.setLong(1, customerId);
                statement.setQueryTimeout(5); // giây, tùy driver hỗ trợ

                try (ResultSet result = statement.executeQuery()) {
                    if (!result.next()) {
                        return Optional.empty();
                    }
                    // Giả định cột email là NOT NULL.
                    return Optional.of(result.getString("email"));
                }
            } finally {
                recordDuration(
                        "jdbc.sql.phase",
                        System.nanoTime() - sqlStarted);
            }
        }
    }

    private static void recordDuration(
            String metricName, long elapsedNanos) {
        long millis = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
        System.out.println(metricName + "_ms=" + millis);
    }
}
```

Kết quả mẫu:

```text
jdbc.acquire.success_ms=3
jdbc.sql.phase_ms=42
```

**Ý nghĩa chính xác của hai số:**

- `jdbc.acquire.success_ms` đo tổng thời gian **lấy `Connection`** từ `DataSource`. Không thể từ số này suy ra “đã chờ queue 3 ms” hoặc “tạo physical connection 3 ms”.
- `jdbc.sql.phase_ms` đo thời gian từ lúc chuẩn bị statement đến khi xử lý xong kết quả/đóng statement trong khối `try`; nó bao gồm việc chuẩn bị, thực thi, nhận và đọc `ResultSet`. Đây **không phải chỉ CPU của database** hay thời gian chạy server-side query.
- Trong ví dụ, việc `Connection.close()` ở ngoài `sql.phase` không nằm trong đồng hồ SQL. Nếu cần biết **thời gian giữ kết nối** (*connection hold time*), phải đo từ lúc nhận connection đến khi đã trả/đóng, với metric riêng.
- Cách `System.out.println` chỉ có giá trị dạy học. Trong ứng dụng sản phẩm, dùng hệ metric/log có cấu trúc, percentiles và giới hạn cardinality; không log email, SQL parameters hoặc mật khẩu.

Đo thành công và thất bại riêng: nếu `getConnection()` ném lỗi sau 2 giây, đây vẫn là **một lần thử mượn 2 giây**, không được bỏ qua chỉ vì chưa nhận kết nối. Lỗi này cần được phân loại bằng `SQLException` và metric của pool.

### Giới hạn của việc đo ở tầng ứng dụng

Không thể suy từ `DataSource.getConnection()` rằng:

- Kết nối đang được cấp từ `idle` hay vừa được tạo mới.
- Lời gọi đã trải qua một lần hoặc nhiều lần kiểm tra `isValid()`.
- Tạo physical connection mất bao lâu nếu pool chạy công việc đó ở background.
- DB server nhận yêu cầu lúc nào hoặc hoàn tất TLS/auth lúc nào.

Muốn biết những dữ liệu đó, kết hợp **metric của pool**, driver, database, hệ thống mạng và tracing nếu có.

## 6. Đo tạo kết nối vật lý khác đo checkout

Để quan sát tương đối **thời gian mở phiên kết nối mới**, trong môi trường thử nghiệm có thể đo lời gọi driver trực tiếp (không qua pool):

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.concurrent.TimeUnit;

// Chỉ dùng trong phép thử có kiểm soát; không mở kết nối mới
// cho mỗi request trong hệ thống sử dụng pool.
public static long measureDirectConnect(
        String jdbcUrl, String user, String password)
        throws SQLException {

    long started = System.nanoTime();

    try (Connection connection =
                 DriverManager.getConnection(jdbcUrl, user, password)) {

        long elapsed = System.nanoTime() - started;
        return TimeUnit.NANOSECONDS.toMillis(elapsed);
    }
}
```

Kết quả này là độ trễ **lời gọi trực tiếp tạo `Connection` qua driver**. Nó có thể gồm DNS, TCP, TLS, xác thực và khởi tạo session; còn phụ thuộc driver và môi trường. Nếu dùng một JDBC URL hoặc driver cung cấp cơ chế pooling/proxy riêng, phải xác minh lời gọi thật sự tạo kết nối vật lý mới trước khi gọi đó là số đo `T_create`.

**Không dùng phép thử này thay hoàn toàn metric tạo kết nối của pool**: pool có thể có quy trình khởi tạo riêng, chạy setup SQL, validation, retry, cơ chế proxy và quản lý TLS khác. Để phân tích sự cố sản phẩm, ưu tiên chỉ số tạo connection từ pool/driver và kiểm tra server logs.

Không gọi `DriverManager.setLoginTimeout(...)` như “một phần benchmark” tùy tiện trong tiến trình nhiều thành phần: nó là cấu hình toàn cục của `DriverManager` và có thể ảnh hưởng lời gọi khác.

## 7. Năm tình huống dễ nhầm lẫn

### 7.1. Pool cạn kết nối: thời gian chờ mượn tăng, tạo mới vẫn nhanh

Giả sử pool tối đa 10 kết nối, đang có 10 kết nối `active`, `idle=0`, `pending=25`. Mọi kết nối đã đạt giới hạn tối đa.

```text
Max pool = 10
Active   = 10
Idle     = 0
Pending  = 25

Driver connect: nhanh khi thử riêng
Pool borrow: nhiều request chờ đến timeout
```

**Chẩn đoán:** dấu hiệu chính là pool **bão hòa công suất mượn**. Tăng connect timeout của driver thường **không giải quyết** vì pool không được phép tạo kết nối thứ 11. Cần tìm vì sao các kết nối bị giữ lâu: truy vấn chậm, transaction mở lâu, connection leak, thread chạy tác vụ khác trong khi đang giữ connection, hay lưu lượng đến vượt khả năng phục vụ.

### 7.2. Pool còn khả năng tăng nhưng mở kết nối mới chậm

Giả sử pool tối đa 20, mới có 3 kết nối, đang cần tăng quy mô nhưng quá trình tạo physical connection mất thời gian do DNS, TLS hoặc database từ chối/giới hạn kết nối.

```text
Max pool   = 20
Existing   = 3
Creating   > 0
Connect    = chậm/lỗi
Borrow     = chậm vì chưa có connection mới để phát
```

**Chẩn đoán:** xem thời gian/lỗi **connection creation** của pool, cấu hình mạng/driver, trạng thái database và tốc độ khởi tạo session. Tăng `maximumPoolSize` không làm handshake nhanh hơn. Nhiều kết nối mới mở đồng thời còn có thể tăng tải xác thực và tài nguyên server.

### 7.3. Cold start: lần mượn đầu tiên chậm, sau đó nhanh

Khi pool vừa khởi động, có thể chưa có đủ `idle`. Một số implementation tạo kết nối sẵn lúc init, số khác tạo theo nhu cầu hoặc trong luồng nền. Do đó:

- Thời gian khởi tạo pool có thể chứa chi phí tạo kết nối.
- Lần `getConnection()` đầu tiên có thể phải đợi tạo/kiểm tra kết nối.
- Những lần sau tái sử dụng kết nối nên thường nhanh hơn nếu pool đủ `idle` và DB ổn định.

Không dùng một lần startup chậm để kết luận database chậm trong suốt quá trình chạy. Cần phân biệt **startup readiness**, warm-up, số kết nối được tạo trước và thời gian mở kết nối mới khi mở rộng pool.

### 7.4. Kết nối idle bị mạng hoặc database đóng

Pool có thể giữ một `Connection` mà server/network đã ngắt sau thời gian không sử dụng. Khi mượn, pool phải validation rồi loại bỏ/thay thế kết nối hỏng.

Hậu quả có thể là `getConnection()` chậm dù `pending` không cao, hoặc một yêu cầu đầu tiên gặp lỗi vì kết nối không còn hợp lệ. Cần xem metric **failed validation**, **connection eviction**, thời gian mở connection mới và chính sách keepalive/idle/lifetime.

Đặt `validationTimeout` quá dài có thể làm mỗi lần kiểm tra lỗi kéo dài; đặt quá ngắn có thể tạo false negative khi mạng nhất thời chậm. Không dùng `isValid()` liên tục trên mọi request ngoài nhu cầu nếu pool đã có cơ chế kiểm tra phù hợp.

### 7.5. SQL chậm nhưng mượn kết nối nhanh

Một request có thể nhận connection sau 1 ms, nhưng câu `SELECT` hoặc `UPDATE` chạy 8 giây vì thiếu index, lock wait, dữ liệu lớn hoặc mạng. Đây **không phải một lỗi mượn kết nối của chính request đó**.

Tuy nhiên nếu nhiều request tương tự cùng giữ connection trong 8 giây, pool dần hết `idle` và **những request đến sau bắt đầu gặp borrow timeout**. Vì vậy có thể có chuỗi nhân quả:

```text
SQL chậm / transaction giữ connection lâu
                  ↓
Active connections tăng
                  ↓
Idle giảm về 0
                  ↓
Pending tăng
                  ↓
Borrow timeout xuất hiện
```

Chỉ nâng borrow timeout sẽ khiến các request chờ lâu hơn mà không sửa nguyên nhân ban đầu. Cần đo riêng thời gian SQL, thời gian chờ khóa, thời gian giữ connection và hàng đợi.

## 8. Cấu hình timeout phải phản ánh ngân sách thời gian của yêu cầu

Giả sử API có ngân sách phản hồi 3 giây. Nếu cho phép **mượn kết nối tới 5 giây**, thì yêu cầu có thể hết ngân sách trước khi nhận được kết nối để chạy SQL. Khi đó, tăng timeout không làm API “chịu tải tốt hơn”, mà có thể chỉ làm nhiều thread bị giữ chờ lâu hơn.

Một sơ đồ ngân sách thời gian:

```text
Tổng ngân sách API: 3000 ms
  ├─ Xử lý đầu vào và xác thực
  ├─ Chờ lấy Connection từ pool
  ├─ Thực thi SQL / nhận ResultSet
  ├─ Xử lý nghiệp vụ
  └─ Trả response
```

Không nhất thiết các mốc đều là phần cộng tuần tự tuyệt đối: có thể có thao tác song song, hủy giữa chừng, retries hoặc quy tắc timeout khác nhau. Dù vậy, các giới hạn phải **tương thích với deadline tổng** của request, thay vì cấu hình độc lập không có ngân sách.

Một ví dụ **minh họa, không phải giá trị mặc định khuyến nghị**:

| Thành phần | Ngân sách thử nghiệm | Mục tiêu |
| --- | ---: | --- |
| Borrow/acquire | 300 ms | Không giữ request chờ pool quá lâu khi đang nghẽn |
| Query chính | 1.500 ms | Có đủ thời gian cho SQL trong điều kiện bình thường |
| Xử lý khác và dự phòng | 1.200 ms | Phù hợp tổng request 3.000 ms |

Đây là cách chia ngân sách phục vụ thảo luận; trên sản phẩm thật phải hiệu chỉnh theo p95/p99, hành vi timeout của driver và chi phí retry. `Statement.setQueryTimeout(...)` dùng **giây**, nên không thể áp thẳng giá trị 1.500 ms bằng phương thức đó nếu driver không có cơ chế timeout chi tiết hơn. Ngoài ra, timeout câu SQL **không phải deadline tổng cho transaction**.

Lỗi thiết kế thường gặp là chỉ đặt timeout mượn ngắn, trong khi phần lớn thời gian connection bị giữ trong một transaction dài hoặc trên truy vấn thiếu index. Hãy quản lý cả **thời gian mượn**, **thời gian sử dụng** và **thời gian tạo mới**.

## 9. Dùng số liệu pool để tìm đúng nút thắt

Các metric hữu ích, nếu pool cung cấp:

| Metric | Diễn giải | Dấu hiệu cần xem |
| --- | --- | --- |
| `active` / `in-use` | Kết nối đang được giữ bởi ứng dụng | Duy trì gần `maximumPoolSize` trong thời gian dài |
| `idle` / `available` | Kết nối sẵn sàng cấp phát | Liên tục bằng 0 khi tải cao |
| `pending` / `waiting threads` | Yêu cầu đang chờ mượn | Tăng nhanh hoặc kéo dài theo tải |
| Acquisition duration p50/p95/p99 | Độ trễ lấy kết nối | Đuôi p99 cao khi SQL chậm hoặc pool đầy |
| Borrow timeout count | Số lần chờ vượt giới hạn | Tăng khi backlog, connection creation lỗi hoặc pool cạn |
| Physical creation duration | Thời gian mở kết nối vật lý | Tăng khi DNS/TCP/TLS/auth hoặc server chậm |
| Creation failures | Tạo kết nối mới bị lỗi | Kiểm tra mã SQLState/vendor, mạng và giới hạn DB |
| Validation failures/duration | Connection hỏng hoặc kiểm tra kéo dài | Xem idle timeout mạng, health và lifetime |
| Connection usage/hold duration | Thời gian từ mượn đến trả | Đuôi dài chỉ ra SQL/transaction/connection leak |
| Pool size / max/min | Số kết nối pool duy trì | So sánh với giới hạn server và số instance |

**Đừng chỉ nhìn giá trị trung bình.** Một pool có thời gian mượn trung bình 5 ms vẫn có thể có p99 = 2 giây vì một nhóm request bị chặn trong những thời điểm tải cao. Cần giữ cả histogram/percentiles và đánh dấu thời điểm pool gần đạt max.

Nếu metrics của pool cho thấy borrow timeout tăng nhưng physical creation duration ổn định và pool đang full, hướng điều tra khác hẳn tình huống creation failures tăng khi pool còn nhiều chỗ.

### Một nguyên tắc ước lượng quy mô pool

Trong trạng thái tải **ổn định**, theo Little's Law:

```text
Số kết nối đang được sử dụng trung bình
    ≈ tốc độ các lượt mượn thành công (lượt/giây)
      × thời gian giữ kết nối trung bình (giây)
```

Ví dụ `200 lượt mượn/giây` và mỗi lượt giữ connection trung bình `0,05 giây` thì mức sử dụng trung bình xấp xỉ `10 kết nối`. Đây **không phải khuyến nghị đặt maximumPoolSize = 10**: tải có đỉnh, phân phối thời gian giữ có đuôi dài, số request song song có thể tăng mạnh và giới hạn throughput database cũng phải xét.

Quan trọng hơn, **tăng pool vô hạn không làm database nhanh hơn**. Nếu có 12 instance ứng dụng, mỗi instance tối đa 20 connection, tổng tiềm năng là `12 × 20 = 240` kết nối vật lý. Cần cộng cả ứng dụng khác, job và kết nối quản trị so với `max_connections` hay giới hạn phiên thực của server. Đặt mỗi pool quá lớn có thể làm database cạn tài nguyên hoặc tăng tranh chấp lock.

Thường nên tìm và giảm **thời gian giữ connection** trước khi tăng giới hạn. Một số thao tác giúp giảm thời gian giữ: chỉ mượn kết nối khi sắp làm SQL, tránh chờ HTTP/API bên ngoài trong transaction, dùng batch phù hợp, thêm index cho query chậm và đóng kết nối đúng scope.

## 10. `Connection.close()` và kết nối bị giữ lâu

Với `DataSource` có pool, `Connection.close()` thường là điểm trả **quyền sử dụng**. `close()` không nhất thiết đóng socket vật lý và cũng **không thay thế commit/rollback** của một transaction đang mở.

Ví dụ một phương thức CRUD đúng phạm vi:

```java
public int updateEmail(
        DataSource dataSource, long customerId, String email)
        throws SQLException {

    String sql = "UPDATE customers SET email = ? WHERE id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setString(1, email);
        statement.setLong(2, customerId);

        return statement.executeUpdate();
    }
}
```

`try-with-resources` bảo đảm đóng statement và connection khi rời scope, kể cả khi `executeUpdate()` ném `SQLException`. Nếu tầng service cần dùng **một transaction qua nhiều DAO**, service phải giữ `Connection` và tự quản lý `commit()`/`rollback()`; DAO khi đó nhận connection từ bên gọi và không tự đóng connection đó.

### Connection leak khác connection bận hợp lệ

Không phải mọi kết nối `active` lâu đều bị leak:

- **Giữ hợp lệ:** transaction đang chạy truy vấn nặng hoặc bị chờ khóa; có hoạt động và sẽ trả connection khi hoàn thành.
- **Giữ quá lâu do thiết kế:** đã lấy connection nhưng đang chờ gọi API khác hoặc thao tác người dùng; connection không cần thiết ở thời điểm đó.
- **Leak:** một nhánh thực thi không gọi `close()`/không kết thúc scope, khiến kết nối không được trả dù công việc đã xong.

Pool có thể có chức năng phát hiện “mượn quá lâu”, nhưng **đó là tín hiệu nghi vấn, không tự chứng minh leak**. Cần đối chiếu log thời điểm mượn/trả, thread stack, SQL đang chạy, transaction đang chờ và metric hold duration.

Cũng không nên tự viết `finally { connection.close(); }` chồng chéo với `try-with-resources` rồi đóng nhầm một connection do tầng khác sở hữu.

## 11. Phân loại lỗi: timeout mượn không phải SQL timeout

Một lời gọi `getConnection()` có thể ném `SQLException`. Pool có thể bọc nguyên nhân trong `SQLTransientConnectionException` hoặc một loại khác; driver có thể báo lỗi kết nối với SQLState class `08`. Không nên suy từ **một lớp ngoại lệ** rằng lỗi chắc chắn là “pool đã đầy” hoặc “TCP connect timeout”.

Ví dụ chẩn đoán có giới hạn:

```java
import java.sql.SQLException;

public static void describeConnectionFailure(SQLException failure) {
    SQLException current = failure;
    int seen = 0;

    while (current != null && seen < 10) {
        System.err.println(
                "type=" + current.getClass().getSimpleName()
                + ", SQLState=" + current.getSQLState()
                + ", vendorCode=" + current.getErrorCode());

        current = current.getNextException();
        seen++;
    }
}
```

Hãy kết hợp:

- **Loại và thời điểm lỗi:** xảy ra khi `getConnection()`, `executeQuery()`, `commit()` hay `close()`?
- **Message/SQLState/vendor code:** dùng trong log nội bộ đã kiểm soát, đối chiếu tài liệu pool/driver; không dựa duy nhất vào một chuỗi lỗi.
- **Metric pool:** pending, active, idle, borrow timeout, creation failure.
- **Metric DB/network:** thời gian handshake, kết nối bị từ chối, giới hạn session, CPU/lock, DNS/TLS.
- **Request/transaction trace:** connection bị giữ lâu vì SQL hay vì việc khác?

**Đừng tự retry toàn bộ nghiệp vụ chỉ vì getConnection timeout.** Nếu lỗi xảy ra **trước khi nhận connection và trước khi chạy bất kỳ SQL nào trong nghiệp vụ**, việc thử lại ở tầng request có thể được cân nhắc với giới hạn và backoff. Nhưng nếu cùng nghiệp vụ đã có tác động ở các hệ thống khác, hoặc `getConnection()` xảy ra ở giữa chuỗi thao tác, vẫn phải kiểm tra idempotency và ranh giới transaction. Lỗi kết nối sau `INSERT`/`COMMIT` có thể để lại kết quả không rõ ràng, không được gửi lại lệnh ghi mù quáng.

## 12. Kịch bản kiểm thử để tách hai loại thời gian

Dùng cơ sở dữ liệu **thử nghiệm**, không làm các thao tác phá kết nối hoặc giữ connection cố ý trên môi trường sản phẩm.

### Kịch bản A — cạn pool nhưng DB kết nối tốt

1. Cấu hình pool có `maximumPoolSize = 2`, borrow timeout ngắn và workload thử nghiệm nhỏ.
2. Dùng hai luồng mượn hai connection rồi giữ chúng qua một cơ chế đồng bộ như `CountDownLatch`, **không chạy SQL làm chậm database**.
3. Ở luồng thứ ba, đo thời gian `dataSource.getConnection()`.
4. Kiểm tra: active = 2, idle = 0, pending tăng; luồng thứ ba chờ hoặc nhận lỗi borrow timeout.
5. Cho một luồng trả connection; kiểm tra luồng thứ ba có nhận connection không.

**Kỳ vọng:** tạo kết nối vật lý không phải nút thắt trong kịch bản này; pool đơn giản là không có connection rảnh. Không cần làm hỏng mạng để tái hiện.

### Kịch bản B — tạo kết nối mới chậm

1. Khởi tạo pool thử nghiệm với số kết nối tối thiểu thấp và cho phép tạo thêm.
2. Đo latency tạo connection từ metric pool hoặc phép thử driver trực tiếp.
3. Trong môi trường mô phỏng mạng được phép, áp dụng độ trễ DNS/TCP/TLS hoặc dùng một endpoint thử nghiệm có hành vi chậm đã kiểm soát.
4. Ghi nhận `getConnection()`, metric creation, lỗi và trạng thái active/idle/pending.
5. Phân biệt request đang đợi pool **tạo kết nối** với request đang đợi **kết nối đã mượn được trả lại**.

Không thực hiện thử nghiệm làm gián đoạn DB của người dùng khác. Nếu không có quyền mô phỏng mạng, chỉ so sánh thời gian cold start và warm pool trong môi trường dành riêng cho thử nghiệm, không suy kết luận quá rộng.

### Kịch bản C — SQL chậm làm pool bị nghẽn gián tiếp

1. Lặp một câu SQL chậm có kiểm soát hoặc tạo lock wait trong DB thử nghiệm.
2. Đo `jdbc.acquire.*` và `jdbc.sql.phase` như ví dụ phần 5.
3. Quan sát connection hold duration, active và pending tăng.
4. Khắc phục query hoặc giảm thời gian giữ connection, chạy lại.
5. So sánh với phương án chỉ tăng borrow timeout để thấy vấn đề gốc có thực sự được giải quyết hay không.

### Kịch bản D — validation sau thời gian idle

1. Tạo connection trong pool rồi để idle theo chính sách thử nghiệm.
2. Chỉ khi có môi trường riêng, cấu hình DB/network đóng phiên idle hoặc mô phỏng một kết nối không hợp lệ.
3. Quan sát validation failures và thời gian thay thế kết nối.
4. Đối chiếu với borrow latency trước và sau khi pool thay connection.
5. Điều chỉnh validation/keepalive/lifetime theo tài liệu của pool và DB, không đặt timeout quá nhỏ theo suy đoán.

### Bảng kết quả cần ghi

| Kịch bản | Active | Idle | Pending | Creation duration | Acquire duration | Nhận định |
| --- | ---: | ---: | ---: | --- | --- | --- |
| Pool full | Gần max | 0 | Tăng | Bình thường/không tạo | Cao hoặc timeout | Nghẽn quyền mượn |
| Tạo kết nối chậm | Chưa đạt max | Ít | Có thể tăng | Cao/lỗi | Có thể cao | Nút thắt driver/network/DB |
| SQL giữ connection lâu | Tăng dần | Giảm | Tăng khi full | Có thể bình thường | Cao ở request sau | Nút thắt thời gian sử dụng |
| Validation lỗi | Thay đổi | Có thể giảm | Có thể tăng | Thêm lần tạo thay thế | Dao động | Kết nối idle không còn hợp lệ |

Đây là các mẫu **định tính**, không phải kết quả benchmark. Những metric có sẵn và ranh giới đo phụ thuộc pool; hãy lưu tên pool, phiên bản, cấu hình, đặc tính SQL, quy mô tải và thời gian thử.

## 13. Cách xử lý sự cố theo triệu chứng

| Triệu chứng ở ứng dụng | Điều nên xem đầu tiên | Hướng xử lý ban đầu |
| --- | --- | --- |
| `getConnection()` thường timeout khi tải cao | `active` gần max, `idle=0`, `pending` tăng | Tìm SQL/transaction chậm, leak, thời gian giữ kết nối, sizing |
| Lần gọi đầu chậm, sau đó ổn | Cold start, tạo idle, TLS/auth và pool initialization | Điều chỉnh startup/warm-up phù hợp, đo connection creation |
| Connection creation errors nhiều | DB session limit, DNS/TCP/TLS/auth, driver, firewall | Kiểm tra kết nối mạng và giới hạn DB, sửa nguyên nhân |
| Borrow latency cao dù không full | Validation, kết nối bị thay, lock nội bộ pool, scheduling | Xem validation failures, metrics của pool và JVM |
| Timeout tăng sau một đợt SQL chậm | Query latency, lock wait, connection hold | Tối ưu SQL, chỉ mục, transaction, kiểm tra nghẽn database |
| Vừa tăng max pool thì DB chậm hơn | Tổng connections trên các replica, DB CPU/memory/lock | Kiểm tra giới hạn DB, giảm cạnh tranh, giới hạn tải |
| Chỉ một số request chậm ở p99 | Queue spikes, hold tail latency, GC pause | So sánh traces/metrics cùng thời điểm, không chỉ average |
| Lỗi khi database failover | Kết nối cũ bị ngắt, validation/creation failures | Chính sách eviction/reconnect, retry nghiệp vụ có điều kiện |

Khi database đã đến giới hạn CPU, IO hoặc số phiên, nâng `maximumPoolSize` có thể làm **tăng** tranh chấp và thời gian chờ. Khi SQL giữ connection quá lâu, nâng borrow timeout có thể làm request tồn tại lâu hơn trong hàng đợi. Khi driver không tới được DB, nâng borrow timeout cũng không sửa được cấu hình mạng.

**Thứ tự điều tra hợp lý:** xác định **lỗi nằm ở acquire hay SQL**, xem pool có đầy hay không, xem physical creation/validation có chậm hoặc lỗi không, rồi mới quyết định thay đổi cấu hình timeout hoặc kích thước pool.

## 14. Bài tập thiết kế và câu hỏi tự kiểm tra

### Bài tập 1: phân biệt số đo

Giả sử hệ thống ghi được:

```text
getConnection latency: 1900 ms
physical creation time p95: 40 ms
pool active: 16/16
pool idle: 0
pool pending: 24
```

Giải thích tại sao dữ liệu này nghiêng về **chờ mượn do pool bận** hơn là “driver tạo kết nối mất 1900 ms”. Nêu các metric cần xem tiếp để xác định vì sao 16 connection bị giữ lâu.

### Bài tập 2: cold start và tạo kết nối

Trong một lần khởi động, `getConnection()` mất 700 ms, pool mới có 0 idle và số đo creation gần 600 ms. Sau warm-up, acquire chỉ 2 ms. Xác định phần nào thuộc việc thiết lập physical connection và vì sao không thể dùng latency cold start làm ngưỡng cho mọi request.

### Bài tập 3: ngân sách timeout

Một API có deadline 2 giây, SQL p95 khoảng 900 ms, còn có thêm xử lý nghiệp vụ và gọi API khác. Hãy đề xuất mức borrow timeout ban đầu **có ngân sách**, nêu giả định về phần dự phòng và cách kiểm chứng bằng p95/p99. Giải thích vì sao `setLoginTimeout(2)` không chắc đặt giới hạn chờ mượn pool thành 2 giây.

### Bài tập 4: tổng số kết nối

Hệ thống có 8 replica, mỗi replica `maximumPoolSize = 25`. Database cho phép tối đa 220 phiên đồng thời, trong đó job và công cụ quản trị cũng cần kết nối. Tính **trần kết nối tiềm năng** của ứng dụng: `8 × 25 = 200`, rồi giải thích tại sao giá trị ấy có thể không để đủ headroom cho hệ thống.

### Bài tập 5: kịch bản retry

Một request nhận borrow timeout **trước khi thực thi SQL**, còn request khác gặp lỗi kết nối **ngay sau khi gửi lệnh INSERT**. So sánh độ an toàn của retry ở hai trường hợp; nêu yêu cầu idempotency và đối soát khi kết quả câu lệnh ghi chưa xác định.

### Câu hỏi tự kiểm tra

- Pool đã đạt `maximumPoolSize` và tất cả connection đang active. Connect timeout của driver có giúp request đang chờ mượn được cấp phát nhanh hơn không?
- Một lời gọi `DataSource.getConnection()` chậm có chứng minh physical connection creation chậm không?
- Vì sao `setLoginTimeout()` và thuộc tính borrow timeout của pool không phải cùng API?
- Pool có `pending=0` nhưng thỉnh thoảng acquire latency cao. Những nguyên nhân nào ngoài queue wait cần kiểm tra?
- Khi có nhiều replica ứng dụng, tại sao cần tính **tổng** kích thước các pool trước khi tăng từng pool?
- Vì sao metric thời gian giữ connection đôi khi hữu ích hơn chỉ đo thời gian thực thi SQL?
- Lỗi `SQLException` trong `getConnection()` có đủ để kết luận là pool hết connection không?

## 15. Tổng kết các nguyên tắc

1. **Borrow/acquisition là quá trình xin quyền sử dụng kết nối từ pool.** Đo thời gian từ `DataSource.getConnection()` đến lúc nhận connection hoặc lỗi.
2. **Connection creation là việc tạo phiên kết nối vật lý.** Nó có thể gồm DNS, TCP, TLS, xác thực và setup session; không nhất thiết xảy ra trong mỗi lần mượn.
3. **Hai khoảng thời gian liên quan nhưng không đồng nhất.** Pool có thể chờ trả kết nối, tạo connection nền, validation hoặc retry; độ trễ `getConnection()` là số tổng hợp.
4. **Phân biệt chính xác các timeout.** Borrow timeout do pool định nghĩa; connect/login timeout, validation timeout và query timeout có phạm vi khác nhau và đơn vị khác nhau.
5. **Đọc metrics theo bối cảnh.** Active/idle/pending, connection creation failures, acquisition p99 và hold duration giúp biết pool nghẽn vì tải, mạng hay SQL.
6. **Giảm thời gian giữ kết nối trước khi tăng pool vô hạn.** Tối ưu query, transaction, đảm bảo `close()`, và tính tổng kết nối giữa mọi replica với giới hạn server.
7. **Không retry thao tác ghi khi trạng thái chưa rõ.** Cần transaction, idempotency, đối soát và chính sách retry phù hợp.
8. **Kiểm thử trên pool và driver đang triển khai.** Không suy từ tên thuộc tính hoặc một phép đo trung bình rằng mọi trường hợp hành xử giống nhau.

**Kết luận:** một lỗi “không lấy được connection” trong JDBC có thể bắt nguồn từ **hàng đợi mượn** hoặc **quá trình tạo/kiểm tra kết nối**, cũng có thể là hệ quả gián tiếp của SQL giữ kết nối quá lâu. Muốn xử lý đúng, cần tách các đồng hồ đo, hiểu quyền sở hữu `Connection` và quan sát cả pool, driver lẫn database trước khi đổi timeout hoặc kích thước pool.
