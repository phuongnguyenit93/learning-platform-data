# Tích hợp JDBC và xác minh khả năng tương thích của driver

JDBC là API truy cập cơ sở dữ liệu phổ biến trong Java. Các thao tác như mở kết nối, gửi câu lệnh SQL và chờ kết quả thường có tính blocking: thread gọi phương thức sẽ chờ cho đến khi driver nhận được phản hồi hoặc phát sinh lỗi. Java 21 bổ sung virtual thread như một cách tổ chức nhiều tác vụ blocking dễ mở rộng hơn, nhưng việc dùng virtual thread không tự động làm cho driver, connection pool hay cơ sở dữ liệu có khả năng xử lý vô hạn yêu cầu đồng thời.

Khi đưa JDBC vào ứng dụng Java 21, cần kiểm tra đồng thời ba lớp: driver có hỗ trợ phiên bản Java và hệ quản trị cơ sở dữ liệu đang dùng hay không; ứng dụng quản lý `Connection`, `Statement` và `ResultSet` đúng vòng đời hay không; và tải đồng thời có phù hợp với giới hạn connection pool cũng như năng lực database hay không.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Tổ chức thao tác JDBC blocking trong platform thread hoặc virtual thread.
- Dùng `DataSource` và try-with-resources để quản lý tài nguyên JDBC.
- Xác minh driver đang được nạp và nhận diện phiên bản driver, JDBC API và database runtime.
- Đánh giá khả năng tương thích của driver với Java 21 dựa trên tài liệu nhà cung cấp và kiểm thử thực tế.
- Hiểu mối quan hệ giữa virtual thread, connection pool và giới hạn kết nối của database.
- Phát hiện và chẩn đoán hiện tượng pinning khi virtual thread thực hiện blocking I/O.
- Thiết kế kiểm thử tích hợp bao phủ truy vấn, transaction, timeout, TLS và tải đồng thời.

## 1. JDBC là blocking I/O

JDBC cung cấp API đồng bộ. Khi gọi `executeQuery()`, `executeUpdate()` hoặc `DataSource.getConnection()`, mã gọi thường chờ kết quả trước khi tiếp tục. Thời gian chờ có thể đến từ:

- Thiết lập kết nối TCP và thương lượng TLS.
- Xác thực với database.
- Chờ database lập kế hoạch và thực thi SQL.
- Truyền dữ liệu kết quả qua mạng.
- Chờ connection pool cấp một connection đang rảnh.

Ví dụ truy vấn đồng bộ:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "select id, display_name from customer where id = ?")) {

    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            return resultSet.getString("display_name");
        }
        return null;
    }
}
```

Thread gọi đoạn mã trên chờ khi driver thực hiện I/O. Đây là hành vi bình thường của JDBC; virtual thread không biến JDBC thành reactive hoặc non-blocking API. Lợi ích là runtime có thể tạm dừng virtual thread trong những thao tác blocking được hỗ trợ và dùng carrier thread để chạy công việc khác.

## 2. Chọn DataSource và quản lý tài nguyên JDBC

Trong ứng dụng thực tế, nên nhận `DataSource` từ cấu hình hoặc dependency injection thay vì tự tạo kết nối rải rác trong từng phương thức. `DataSource` tách cấu hình kết nối khỏi logic truy vấn và có thể được cung cấp bởi connection pool.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

static String findCustomerName(DataSource dataSource, long customerId)
        throws SQLException {
    String sql = "select display_name from customer where id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, customerId);

        try (ResultSet resultSet = statement.executeQuery()) {
            return resultSet.next()
                ? resultSet.getString("display_name")
                : null;
        }
    }
}
```

Try-with-resources đóng `ResultSet`, `PreparedStatement` và `Connection` khi khối lệnh kết thúc, kể cả khi có exception. Với connection pool, `Connection.close()` thường trả connection về pool để tái sử dụng; nó không nhất thiết đóng socket vật lý ngay lập tức.

Các nguyên tắc cần giữ:

- Đóng `ResultSet`, `Statement` và `Connection` đúng vòng đời.
- Dùng `PreparedStatement` và bind parameter thay vì nối dữ liệu người dùng vào chuỗi SQL.
- Không giữ connection trong lúc thực hiện công việc không liên quan đến database.
- Không chia sẻ cùng một `Connection`, `Statement` hoặc `ResultSet` cho nhiều tác vụ đồng thời trừ khi driver và hợp đồng API cụ thể cho phép; thiết kế thông thường là mỗi tác vụ mượn connection riêng.
- Đặt transaction boundary rõ ràng và luôn rollback khi transaction thất bại trước khi trả connection về pool.

## 3. Dùng JDBC với virtual thread trong Java 21

Virtual thread phù hợp với nhiều tác vụ có thời gian chờ I/O. Có thể chạy mỗi yêu cầu database trên một virtual thread:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
    var future = executor.submit(() ->
        findCustomerName(dataSource, 1001L));

    String customerName = future.get();
    System.out.println(customerName);
}
```

`newVirtualThreadPerTaskExecutor()` tạo một virtual thread cho mỗi tác vụ được gửi. Nếu JDBC driver thực hiện socket I/O theo cách runtime có thể unmount virtual thread, carrier thread được giải phóng trong lúc tác vụ chờ I/O. Điều này giúp xử lý nhiều tác vụ chờ đồng thời mà không cần giữ một platform thread riêng cho mỗi tác vụ.

Ví dụ gửi nhiều truy vấn độc lập:

```java
try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
    List<Future<String>> results = new ArrayList<>();

    for (long id : customerIds) {
        results.add(executor.submit(
            () -> findCustomerName(dataSource, id)));
    }

    for (Future<String> result : results) {
        System.out.println(result.get());
    }
}
```

Mỗi tác vụ có connection riêng thông qua `DataSource`. Không chia sẻ một connection duy nhất giữa các virtual thread. Đồng thời, ví dụ này không có nghĩa nên gửi số lượng truy vấn không giới hạn; giới hạn concurrency phải được thiết kế theo năng lực connection pool và database.

### 3.1. Virtual thread không tăng số connection database

Virtual thread giúp giảm chi phí thread khi nhiều tác vụ chờ I/O, nhưng mỗi truy vấn vẫn cần tài nguyên ở phía database. Connection pool có giới hạn số connection đồng thời; database cũng có giới hạn session, worker, CPU, bộ nhớ và I/O.

Ví dụ, nếu executor tạo hàng nghìn virtual thread nhưng pool chỉ có 30 connection, phần lớn tác vụ có thể chờ lấy connection. Điều này không nhất thiết là lỗi, nhưng cần quan sát thời gian chờ pool, thời gian truy vấn và hàng đợi công việc.

Không nên tạo một pool nhỏ các virtual thread chỉ để tái sử dụng chúng. Thay vào đó, dùng virtual thread per task và giới hạn tài nguyên thực sự khan hiếm, chẳng hạn connection hoặc số truy vấn đồng thời.

Một `Semaphore` có thể giới hạn số tác vụ đi vào vùng truy cập database nếu cần backpressure rõ ràng:

```java
Semaphore databasePermits = new Semaphore(20);

static String findWithLimit(
        DataSource dataSource,
        Semaphore permits,
        long customerId) throws SQLException, InterruptedException {

    permits.acquire();
    try {
        return findCustomerName(dataSource, customerId);
    } finally {
        permits.release();
    }
}
```

Đặt giới hạn dựa trên capacity đã đo và cấu hình pool. Tránh tạo nhiều tầng semaphore và pool với giới hạn không đồng bộ, vì chúng có thể làm tăng thời gian chờ và gây khó chẩn đoán. Nếu pool đã cung cấp hàng đợi và giới hạn phù hợp, có thể dùng chính cơ chế đó làm điểm điều tiết.

## 4. Transaction và vòng đời connection

Một transaction cần dùng cùng một connection cho các câu lệnh thuộc transaction đó. Không tách các bước transaction sang những virtual thread độc lập nếu chúng phải chia sẻ cùng transaction context.

```java
static void transfer(
        DataSource dataSource,
        long fromId,
        long toId,
        BigDecimal amount) throws SQLException {

    String debitSql = "update account set balance = balance - ? where id = ?";
    String creditSql = "update account set balance = balance + ? where id = ?";

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            try (PreparedStatement debit = connection.prepareStatement(debitSql);
                 PreparedStatement credit = connection.prepareStatement(creditSql)) {

                debit.setBigDecimal(1, amount);
                debit.setLong(2, fromId);
                debit.executeUpdate();

                credit.setBigDecimal(1, amount);
                credit.setLong(2, toId);
                credit.executeUpdate();
            }

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
```

Trong ứng dụng production, cần kiểm tra số dòng bị cập nhật, xử lý lỗi nghiệp vụ và tuân thủ chính sách transaction của database. Ví dụ chỉ minh họa rằng một transaction dùng một connection xuyên suốt; không phải một transaction cho mỗi câu lệnh hay mỗi virtual thread.

Nếu dùng connection pool, hãy xác minh pool reset trạng thái connection khi trả về, bao gồm auto-commit, isolation level, schema, read-only mode và các thuộc tính session mà ứng dụng có thể thay đổi.

## 5. Xác minh driver có tương thích với Java 21

Không có một phép kiểm tra đơn lẻ nào chứng minh driver tương thích hoàn toàn. Hãy kết hợp tài liệu nhà cung cấp, dependency thực tế, thông tin runtime và kiểm thử tích hợp trên môi trường gần với production.

### 5.1. Kiểm tra ma trận hỗ trợ của nhà cung cấp

Trước khi nâng JDK lên Java 21 hoặc thay driver, kiểm tra các thông tin sau trong tài liệu chính thức và release notes của nhà cung cấp:

- Phiên bản driver có hỗ trợ Java 21 hoặc JDK 21 theo ma trận hỗ trợ của nhà cung cấp không.
- Driver hỗ trợ phiên bản database server và giao thức đang vận hành không.
- Driver có tương thích với TLS, cơ chế xác thực, chứng thư và chính sách mã hóa đang dùng không.
- Phiên bản driver có sửa các lỗi liên quan đến socket I/O, timeout, cancellation, transaction hoặc connection leak không.
- Driver có phụ thuộc native library, module hoặc runtime component bổ sung không.
- Phiên bản connection pool và framework truy cập dữ liệu có hỗ trợ JDK cùng driver đó không.

Không suy ra hỗ trợ Java 21 chỉ vì file JAR có thể được nạp hoặc ứng dụng biên dịch thành công. Việc biên dịch chỉ xác minh một phần API tại compile time; các lỗi có thể chỉ xuất hiện khi driver khởi tạo, thương lượng kết nối hoặc xử lý truy vấn thực tế.

Không nên tự chọn phiên bản driver chỉ theo số lớn nhất. Hãy chọn bản phát hành còn được nhà cung cấp hỗ trợ, phù hợp với database server và đã được kiểm thử trong môi trường của ứng dụng.

### 5.2. Khai báo dependency rõ ràng

Khai báo driver trực tiếp trong build file và quản lý phiên bản một cách có kiểm soát. Ví dụ Maven với biến phiên bản minh họa:

```xml
<properties>
    <database.driver.version>REPLACE_WITH_SUPPORTED_VERSION</database.driver.version>
</properties>

<dependencies>
    <dependency>
        <groupId>com.vendor</groupId>
        <artifactId>database-jdbc-driver</artifactId>
        <version>${database.driver.version}</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Thay tọa độ artifact và phiên bản minh họa bằng thông tin chính thức của driver đang chọn. Với Gradle, khai báo driver trong `runtimeOnly` nếu mã nguồn chỉ phụ thuộc JDBC API:

```groovy
dependencies {
    runtimeOnly("com.vendor:database-jdbc-driver:SUPPORTED_VERSION")
}
```

Không để dependency version trôi nổi hoặc tải JAR tùy tiện từ một nguồn không được kiểm soát. Trong CI, kiểm tra dependency tree để phát hiện driver trùng phiên bản, dependency bắc cầu kéo về bản cũ hoặc nhiều driver cho cùng một database.

### 5.3. Kiểm tra driver đang được runtime sử dụng

Khi đã có `Connection`, dùng `DatabaseMetaData` để lấy thông tin driver và database:

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println("Driver: " + metadata.getDriverName());
    System.out.println("Driver version: " + metadata.getDriverVersion());
    System.out.println("JDBC level: "
        + metadata.getJDBCMajorVersion() + "."
        + metadata.getJDBCMinorVersion());
    System.out.println("Database: " + metadata.getDatabaseProductName());
    System.out.println("Database version: " + metadata.getDatabaseProductVersion());
}
```

Thông tin này giúp xác nhận runtime đang kết nối bằng driver và database nào. JDBC level do metadata công bố mô tả mức JDBC mà driver hỗ trợ; nó không tự chứng minh toàn bộ driver tương thích với mọi đặc điểm của JDK 21.

Có thể ghi thêm phiên bản runtime đang chạy:

```java
System.out.println("Java runtime: " + Runtime.version());
System.out.println("Java vendor: " + System.getProperty("java.vendor"));
```

Không ghi URL kết nối chứa mật khẩu, access token, thông tin xác thực hoặc dữ liệu nhạy cảm vào log khi thu thập thông tin chẩn đoán.

### 5.4. JDBC driver discovery

Các JDBC driver hiện đại thường đăng ký thông qua cơ chế service provider và được JDBC driver manager tự phát hiện khi driver JAR có mặt trên runtime classpath hoặc module path phù hợp. Với ứng dụng dùng `DataSource` do framework hoặc pool cung cấp, thường cấu hình implementation `DataSource` theo hướng dẫn của nhà cung cấp.

Không cần thêm lời gọi `Class.forName("...")` vào mọi ứng dụng chỉ để nạp JDBC driver. Chỉ dùng cách nạp tường minh nếu driver hoặc môi trường triển khai cụ thể yêu cầu và tài liệu nhà cung cấp hướng dẫn như vậy.

## 6. Kiểm thử tích hợp driver trên Java 21

Kiểm thử tương thích cần kết nối với đúng loại database server và driver sẽ dùng khi triển khai. Mock JDBC có ích để kiểm tra logic ở một số lớp, nhưng không thể thay thế kiểm thử driver thật đối với giao thức, TLS, timeout và transaction.

Một bộ kiểm thử tích hợp nên bao gồm:

| Nhóm kiểm thử | Điều cần xác minh |
|---|---|
| Kết nối cơ bản | Mở connection, xác thực, đọc metadata và đóng connection |
| Truy vấn | Prepared statement, kiểu dữ liệu, null, Unicode và kết quả lớn |
| Ghi dữ liệu | Insert/update/delete, generated keys và batch nếu ứng dụng sử dụng |
| Transaction | Commit, rollback, isolation level và lỗi giữa transaction |
| Timeout | Connection timeout, query timeout và socket/network timeout theo driver |
| Cancellation | Hủy tác vụ khi query đang chạy và xác minh connection còn sử dụng được |
| TLS và xác thực | Chứng thư, hostname verification, truststore và cơ chế xác thực production |
| Connection pool | Mượn/trả connection, validation, leak detection và phục hồi sau lỗi mạng |
| Concurrency | Nhiều truy vấn đồng thời, giới hạn pool và hành vi khi pool cạn |
| Virtual thread | Blocking I/O, cancellation, thread pinning và tải thực tế |

Hãy chạy các bài test trên JDK 21 chính xác mà production sẽ sử dụng. Nếu production dùng container image hoặc custom runtime image, kiểm thử trên cùng loại môi trường đó để phát hiện khác biệt về module, chứng thư CA, native library và cấu hình hệ thống.

### 6.1. Kiểm tra tải với platform thread và virtual thread

Để đánh giá lợi ích của virtual thread, so sánh workload tương đương trong hai cấu hình:

- Platform thread với số worker được giới hạn.
- Virtual thread per task, nhưng giới hạn số truy vấn đồng thời theo capacity của pool/database.

Đo các chỉ số:

- Throughput và p95/p99 latency.
- Thời gian chờ lấy connection từ pool.
- Số connection đang dùng, số connection chờ và số lần timeout.
- CPU, heap, allocation và số lượng thread.
- Số truy vấn bị timeout, retry hoặc thất bại.
- Sự kiện virtual thread bị pin trong lúc blocking.

Nếu tăng số virtual thread chỉ làm hàng đợi connection dài hơn, latency tăng mà throughput không tăng, nút thắt đang nằm ở pool hoặc database. Không đánh giá hiệu năng chỉ dựa vào số lượng thread có thể tạo.

## 7. Chẩn đoán pinning khi JDBC chạy trên virtual thread

Trong Java 21, virtual thread có thể bị pin vào carrier thread khi thực hiện blocking trong một số tình huống, đáng chú ý là blocking khi đang giữ intrinsic monitor (`synchronized`) hoặc khi thực hiện native/foreign call. Khi bị pin, virtual thread không thể unmount carrier theo cách thông thường trong khoảng thời gian đó.

Driver JDBC có thể dùng socket I/O, synchronization hoặc native component tùy implementation. Vì vậy, không nên giả định mọi driver có cùng hành vi khi chạy trên virtual thread. Cần đo bằng đúng driver và workload thực tế.

### 7.1. Dùng cảnh báo pinning của JDK 21

Có thể chạy ứng dụng Java 21 với tùy chọn chẩn đoán:

```bash
java -Djdk.tracePinnedThreads=full -jar application.jar
```

Khi virtual thread bị pin trong lúc thực hiện blocking, runtime có thể in stack trace để hỗ trợ tìm đoạn code liên quan. Tùy chọn này phục vụ chẩn đoán, không nên mặc định bật trong production lâu dài nếu chưa đánh giá ảnh hưởng log và chi phí quan sát.

Java Flight Recorder cũng có event `jdk.VirtualThreadPinned`. Ghi một JFR profile trong bài kiểm thử tải và kiểm tra event này cùng stack trace để xác định pinning có xảy ra trong driver, pool hoặc code ứng dụng hay không. Chọn cấu hình event và ngưỡng ghi phù hợp với thời gian pin cần điều tra.

### 7.2. Cách xử lý khi phát hiện pinning

1. Xác định stack trace chỉ ra code ứng dụng, connection pool, driver hay native library.
2. Kiểm tra release notes và hướng dẫn của nhà cung cấp để tìm bản driver hoặc pool đã sửa vấn đề.
3. Nếu pinning nằm trong code ứng dụng, giảm thời gian giữ monitor quanh thao tác blocking; không giữ `synchronized` trong khi chờ database hoặc mạng.
4. Nếu pinning xuất phát từ native call, trao đổi với nhà cung cấp về hỗ trợ virtual thread hoặc phương án driver phù hợp.
5. Đo lại trên đúng JDK, driver và cấu hình pool sau khi thay đổi.

Không xóa `synchronized` một cách máy móc để tránh pinning. Đồng bộ hóa có thể đang bảo vệ invariant quan trọng. Trước hết cần hiểu vùng trạng thái được bảo vệ, sau đó thiết kế lại phạm vi khóa hoặc cập nhật thư viện có vấn đề.

## 8. Timeout, cancellation và retry

Virtual thread giúp tổ chức tác vụ blocking, nhưng không loại bỏ nhu cầu đặt timeout cho thao tác database. Cần phân biệt:

- **Connection timeout:** thời gian tối đa chờ lấy hoặc thiết lập connection, tùy cấu hình pool/driver.
- **Query timeout:** giới hạn thời gian thực thi câu lệnh thông qua `Statement.setQueryTimeout()`; mức độ chính xác và cách driver chuyển thành protocol timeout phụ thuộc implementation.
- **Network/socket timeout:** giới hạn thời gian chờ I/O ở tầng mạng theo cấu hình driver.
- **Request deadline:** thời gian tổng thể mà ứng dụng dành cho toàn bộ request, có thể bao gồm chờ pool, query, xử lý và gửi phản hồi.

Đặt timeout sao cho các tầng thống nhất với deadline tổng. Ví dụ, query timeout dài hơn request deadline sẽ không giúp request kết thúc đúng hạn. Kiểm thử cách driver phản ứng khi timeout xảy ra: statement có bị cancel không, connection có được trả về pool an toàn không, transaction có cần rollback không.

Không phải mọi lời gọi `Future.cancel(true)` đều bảo đảm database server dừng query ngay lập tức. Hiệu quả phụ thuộc executor, driver, protocol và server. Hãy kiểm thử cancellation với driver thật và kiểm tra trạng thái connection sau khi hủy.

Retry chỉ phù hợp với lỗi tạm thời và thao tác có ngữ nghĩa retry an toàn. Không tự động retry một transaction ghi dữ liệu nếu chưa xác định server đã commit hay chưa; nếu kết quả commit không rõ ràng, cần thiết kế idempotency key hoặc cơ chế xác minh trạng thái nghiệp vụ.

## 9. Checklist triển khai JDBC trên Java 21

Trước khi đưa phiên bản driver mới hoặc virtual thread vào production, hãy xác nhận:

- Driver version được nhà cung cấp hỗ trợ trên JDK 21 và database server đang dùng.
- Dependency được pin và chỉ có một phiên bản driver dự kiến trên runtime.
- Driver thực tế được nạp đúng; `DatabaseMetaData` trả về thông tin như kỳ vọng.
- `DataSource` và connection pool có cấu hình giới hạn, timeout, validation và leak detection phù hợp.
- Mọi `Connection`, `Statement` và `ResultSet` được đóng đúng vòng đời.
- Transaction dùng đúng connection và rollback khi thất bại.
- Không chia sẻ connection hoặc statement giữa các tác vụ đồng thời.
- Tải đồng thời bị giới hạn theo năng lực pool và database.
- Test bao phủ query, update, transaction, timeout, cancellation, TLS và phục hồi sau lỗi mạng.
- Nếu dùng virtual thread, đã kiểm tra pinning và đo throughput/latency trên đúng driver.
- Log không chứa credential hoặc dữ liệu nhạy cảm.

## 10. Nguyên tắc thiết kế

- Coi JDBC là API blocking; virtual thread giúp quản lý nhiều tác vụ chờ I/O, không thay đổi bản chất API.
- Dùng `DataSource` và connection pool được nhà cung cấp hỗ trợ trên JDK đang triển khai.
- Chọn driver dựa trên ma trận hỗ trợ chính thức, release notes và integration test.
- Dùng `try-with-resources` để đóng JDBC resource và xác định transaction boundary rõ ràng.
- Mỗi tác vụ đồng thời nên có connection riêng; không chia sẻ connection cho nhiều thread cùng thao tác.
- Giới hạn số truy vấn đồng thời theo database capacity, ngay cả khi dùng virtual thread.
- Theo dõi thời gian chờ pool, query latency, timeout và pinning thay vì chỉ theo dõi số thread.
- Xem `DatabaseMetaData` là bằng chứng nhận diện runtime, không phải chứng nhận tương thích đầy đủ.
- Không dựa vào `Class.forName()` như bước bắt buộc trong mọi ứng dụng JDBC hiện đại; theo hướng dẫn của driver cụ thể.

Tích hợp JDBC trên Java 21 cần kết hợp driver được hỗ trợ, quản lý tài nguyên đúng cách và giới hạn concurrency phù hợp. Virtual thread có thể làm mô hình xử lý blocking dễ mở rộng hơn, nhưng chỉ kiểm thử trên driver, pool và database thực tế mới cho biết ứng dụng có đáp ứng yêu cầu vận hành hay không.

## Tài liệu tham khảo

- [Java SE 21 API — JDBC](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/module-summary.html): module `java.sql` và các API JDBC.
- [Java SE 21 API — `DataSource`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/javax/sql/DataSource.html): abstraction cung cấp kết nối database.
- [Java SE 21 API — `DatabaseMetaData`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/DatabaseMetaData.html): thông tin driver, JDBC level và database runtime.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): hành vi blocking, pinning và chẩn đoán virtual thread trong Java 21.
- [Java SE 21 API — `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): thực thi tác vụ và quản lý vòng đời executor.
