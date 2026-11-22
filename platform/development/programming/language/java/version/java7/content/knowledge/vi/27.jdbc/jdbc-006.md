# Java 7 — JDBC: Network timeout và quyền sở hữu executor

## 1. Vấn đề: một kết nối JDBC có thể chờ phản hồi quá lâu

Trong ứng dụng Java kết nối database qua JDBC, một câu truy vấn có thể chậm vì SQL hoặc lock; nhưng còn một tình huống khác nguy hiểm: **driver đã gửi yêu cầu tới database mà không nhận được phản hồi** do sự cố mạng, thiết bị trung gian hoặc máy chủ không thể liên lạc. Thread gọi JDBC có thể chờ rất lâu ở một network operation.

Từ JDBC 4.1 (API có từ Java 7), `java.sql.Connection` có hai phương thức:

```java
void setNetworkTimeout(Executor executor, int milliseconds)
        throws SQLException;

int getNetworkTimeout() throws SQLException;
```

Đây là **chữ ký API**, không phải một chương trình độc lập. `setNetworkTimeout` yêu cầu một `Executor` và một **ngưỡng tính bằng mili-giây**. Khi driver xác định ngưỡng bị vượt, JDBC quy định connection bị đánh dấu **closed**, tài nguyên liên quan được giải phóng và lần chờ phát sinh `SQLException`. Cơ chế này nghiêm trọng hơn timeout của một SQL statement thông thường.

Đề bài “Network timeout và quyền sở hữu executor” có **hai phần không thể tách rời**:

1. Đặt network timeout với đúng mục đích, đơn vị, mức ưu tiên so với query/transaction timeout và hành vi khi hết hạn.
2. Xác định **ai tạo, ai cho mượn, ai được phép shutdown Executor**, vì một executor bị shutdown quá sớm có thể không đáp ứng được công việc bất đồng bộ do driver cần.

Bài học hướng tới Java 17+, dùng các API vẫn được hỗ trợ. Không dùng cách quản lý tài nguyên đã lỗi thời và không giả định mọi JDBC driver đều thực hiện timeout giống hệt nhau.

### 1.1. Một ví dụ dễ hiểu

Giả sử một request nghiệp vụ chạy câu SELECT. Thông thường:

```text
Application thread                      Database
      |                                    |
      |--- send SQL request -------------->|
      |                                    | xử lý SQL
      |<------------- result --------------|
      | trả kết quả cho caller              |
```

Nhưng nếu mạng không truyền phản hồi:

```text
Application thread                  Mạng / Database
      |                                    |
      |--- send request ------------------>|
      |                                    X mất đường phản hồi
      | [chờ phản hồi từ network I/O]      |
      |        ...
      |    network timeout được driver xác định
      |             |
      v             v
  SQLException, connection bị đánh dấu closed
  -> không tiếp tục dùng connection đó cho truy vấn khác
```

`setNetworkTimeout` được tài liệu JDBC thiết kế cho những tình huống **mất phản hồi hiếm nhưng nghiêm trọng**, đặc biệt khi các socket reads có thể bị treo trong thời gian dài. Nó **không phải** cách thay mọi loại timeout của ứng dụng.

## 2. Tại sao có đối số Executor?

Chữ ký:

```java
connection.setNetworkTimeout(executor, 15_000);
```

gồm:

- `connection`: JDBC `Connection` đã tồn tại và còn mở.
- `executor`: đối tượng thực thi các `Runnable` theo cơ chế do Java/driver sử dụng.
- `15_000`: ngưỡng **15.000 ms = 15 giây** cho phản hồi database request theo hợp đồng API.

`Executor` là một **giao diện** thuộc `java.util.concurrent`. Không có yêu cầu đối số phải là một đối tượng `Thread` hoặc phải tạo một executor mới mỗi lần gọi. Có thể đưa vào một `ExecutorService` sống đủ lâu, do tầng infrastructure/connection-pool manager quản lý.

JDBC driver có thể cần dùng executor để thực hiện những nhiệm vụ hỗ trợ timeout hoặc hủy/giải phóng kết nối. **Lịch chạy, số lần driver gọi executor và cơ chế nội bộ phụ thuộc implementation**. Ứng dụng chỉ nên dựa vào **hợp đồng JDBC công khai**, không đoán driver tạo chính xác một task vào thời điểm nào.

### 2.1. Executor không có nghĩa query được chạy bất đồng bộ

`setNetworkTimeout(executor, ...)` **không** tự chuyển `statement.executeQuery()` sang thread của executor. Query vẫn được gọi bởi thread ứng dụng theo cách JDBC synchronous thông thường. Đối số executor được cung cấp để driver dùng khi cần thực thi công việc liên quan theo thiết kế của nó.

Đừng hiểu `Executor` là “nơi mọi SQL được gửi tới”. Nếu cần gửi truy vấn bất đồng bộ, đó là mô hình concurrency ở tầng ứng dụng và phải quản lý timeout, cancellation, transaction context khác.

### 2.2. Không dùng trực tiếp `Runnable::run` như một cách né quản lý thread

Một `Executor` đồng bộ như:

```java
Executor inline = Runnable::run;
```

là một implementation hợp lệ về mặt Java interface, nhưng nó chạy `Runnable` **ngay trong thread gọi execute**. Trong tình huống cần xử lý việc giải phóng/timeout mà thread gọi có thể đang bị block, inline executor có thể phá vỡ ý định điều phối độc lập. Nên dùng executor phù hợp driver và có khả năng thực hiện công việc **độc lập với thread JDBC đang chờ**; kiểm tra yêu cầu cụ thể của nhà cung cấp driver.

### 2.3. Không truyền null

`connection.setNetworkTimeout(null, 15_000)` không hợp lệ theo JDBC contract, có thể ném `SQLException`. Không “truyền null để driver tự chọn thread pool” nếu nhà cung cấp không có API riêng cho hành vi đó.

### 2.4. Không dùng chung một executor rồi để một module tự đóng

Nếu service A, service B và connection pool cùng sử dụng một executor, một request bất kỳ không được `shutdown()` executor đó sau khi hoàn thành SQL của nó. Quyền dừng phải thuộc **owner của executor** — thường là application lifecycle component hoặc pool/infrastructure manager.

## 3. Chính xác network timeout giới hạn điều gì?

Theo Javadoc Java SE 17, `setNetworkTimeout` đặt **khoảng thời gian tối đa mà Connection hoặc objects được tạo từ Connection chờ database trả lời cho một request**.

Các điểm cần phân biệt:

- Nó giới hạn **thời gian chờ phản hồi database request** theo cách driver áp dụng hợp đồng.
- Nó **không** có nghĩa một API HTTP request với nhiều câu SQL phải hoàn tất trong một ngân sách tổng cộng đúng `milliseconds`.
- Một lời gọi JDBC có thể tạo ra **nhiều trao đổi driver↔database** nội bộ. Java cho phép driver quyết định ngưỡng áp cho toàn lời gọi hoặc từng request con.
- Việc gọi `setNetworkTimeout` **không thay đổi các request đã gửi và đang chờ trước đó**.
- Nếu driver không có độ phân giải millisecond, theo tài liệu có thể **làm tròn lên đến giây gần nhất**.
- Không phải mọi driver hỗ trợ method; `SQLFeatureNotSupportedException` là một khả năng chính thức.
- Network timeout **0** nghĩa **không đặt giới hạn network timeout này**, không phải “timeout ngay lập tức”.
- Giá trị âm là tham số không hợp lệ và JDBC API báo `SQLException`.
- Timeout là cơ chế bảo vệ nghiêm trọng, nên đặt sao cho **các timeout thông thường thường có cơ hội tác động trước**.

### 3.1. Giá trị hợp lệ

```java
connection.setNetworkTimeout(networkExecutor, 15_000);
```

Đây là snippet trong một phương thức có `Connection connection` đã mở và `Executor networkExecutor` thuộc quyền quản lý của caller/infrastructure.

### 3.2. Đọc lại cấu hình

```java
int networkMillis = connection.getNetworkTimeout();
```

Giá trị trả về là **mili-giây**, không phải giây. `getNetworkTimeout()` có thể ném `SQLException` hoặc `SQLFeatureNotSupportedException` tùy driver/trạng thái connection. Không suy rằng getter chắc chắn trả lại con số bạn đặt trên mọi driver/implementation, vì có thể có chính sách làm tròn hoặc wrapper/pool can thiệp.

### 3.3. Tắt riêng JDBC network timeout

```java
connection.setNetworkTimeout(networkExecutor, 0);
```

Đây là việc **bỏ ngưỡng JDBC network timeout** ở connection tương ứng. Nó không tắt toàn bộ timeouts của OS, socket, driver, load balancer hoặc database. Trong production, **không tự ý đặt 0** chỉ vì muốn trả connection về pool; pool có thể có chính sách baseline khác.

### 3.4. Nâng ngưỡng quá cao hoặc quá thấp

- Quá thấp: một biến động mạng hợp lệ có thể bị xem là lỗi nghiêm trọng, khiến connection đóng liên tục.
- Quá cao: khi mạng thực sự mất phản hồi, thread gọi JDBC có thể chờ lâu, ảnh hưởng thread pool và SLA.
- Ngưỡng phù hợp phải dựa trên driver, network topology, latency thực tế, SLO, query timeout và transaction timeout.

Không có một số 5.000, 15.000 hoặc 30.000 ms nào tự động đúng cho mọi hệ thống. Các giá trị trong ví dụ chỉ là **cấu hình minh họa**, không phải chuẩn bắt buộc.

## 4. Network timeout khác query timeout, login timeout và request deadline

Đây là bảng rất quan trọng vì chúng kiểm soát **những giai đoạn khác nhau**.

| Cơ chế | API ví dụ | Đơn vị | Kiểm soát chính |
| --- | --- | --- | --- |
| Kết nối/login timeout | `DataSource.setLoginTimeout(seconds)` | Giây | Thời gian chờ thiết lập kết nối theo DataSource/driver |
| Query timeout | `Statement.setQueryTimeout(seconds)` | Giây | Thời gian thực thi statement theo JDBC contract |
| JDBC network timeout | `Connection.setNetworkTimeout(executor, milliseconds)` | **Mili-giây** | Thời gian chờ DB phản hồi mỗi yêu cầu theo driver |
| Kiểm tra connection sống | `Connection.isValid(timeoutSeconds)` | Giây | Giới hạn chờ kiểm tra tính hợp lệ |
| Transaction timeout | Framework/container/DB setting | Tùy nền tảng | Ngân sách/giới hạn cho toàn transaction |
| Socket/connect/read timeout | Cấu hình JDBC driver cụ thể | Tùy driver | Thời gian kết nối/socket I/O |
| HTTP/request deadline | Web framework/service | Thường duration | Ngân sách end-to-end request |
| Pool connection acquisition timeout | Connection pool cụ thể | Tùy pool | Thời gian chờ có connection rảnh từ pool |

**Quan trọng:** không phải timeout nào cũng là phương thức chuẩn trên `Connection`. Pool-acquisition timeout và driver socket timeout thường là **cấu hình theo vendor/connection pool**, không được chuẩn hóa dưới một tên property chung của JDBC.

### 4.1. Statement.setQueryTimeout()

```java
try (PreparedStatement statement =
             connection.prepareStatement("SELECT id FROM demo_items")) {
    statement.setQueryTimeout(5);
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong(1);
            // Xử lý id.
        }
    }
}
```

Đây là **snippet tích hợp thực tế**, không phải một chương trình độc lập: cần import `java.sql.*`, connection từ DB/driver và bảng `demo_items` do ứng dụng quản lý.

Theo Java SE 17, `setQueryTimeout(5)` thiết lập **5 giây**, mặc định `0` là không giới hạn; driver phải áp dụng tới `execute`, `executeQuery`, `executeUpdate`. Driver có thể chọn áp dụng cả trên `ResultSet`, và batch semantics có thể khác theo vendor.

Nếu driver nhận thấy query timeout, nó cố gắng cancel statement và ném `SQLTimeoutException` theo hợp đồng. Điều đó **không tự động đồng nghĩa Connection bị đóng** nếu network vẫn khỏe; vẫn phải kiểm tra lỗi thực tế, transaction state và khả năng reuse.

### 4.2. Connection.setNetworkTimeout()

```java
connection.setNetworkTimeout(networkExecutor, 15_000);
```

Nó không đặt “query timeout 15 giây”, mà là một **ngưỡng mạng nghiêm trọng 15 giây**. Nếu bị kích hoạt, **connection bị đánh dấu closed**, cả connection và các statement liên quan không thể tiếp tục dùng như bình thường.

### 4.3. Timeout ưu tiên theo mục đích

Ví dụ chính sách minh họa:

```text
Login timeout:          3 giây (giai đoạn mở kết nối)
Query timeout:          5 giây (thực thi một statement)
JDBC network timeout:  15 giây (chờ phản hồi mạng bất thường)
HTTP request budget:   phụ thuộc nhiều bước và SLA toàn request
```

Ở đây 5 giây **ngắn hơn** 15 giây nhằm cho query timeout cơ hội hủy câu SQL bình thường trước khi ngưỡng mạng nghiêm trọng đóng connection. Còn login timeout điều khiển **một giai đoạn khác**, không phải “3 giây kể từ khi bắt đầu SELECT”.

**Không có quy tắc chuẩn buộc networkMillis > querySeconds×1000 trong mọi ứng dụng**. Đó là lựa chọn policy hợp lý mà Java docs khuyến nghị theo thứ tự các timeouts, nhưng cần xét transaction timeout, driver socket settings, đặc tính server và workload.

### 4.4. Một network timeout không phải end-to-end timeout

Giả sử code có ba câu SQL, mỗi câu mất 10 giây. Network timeout 15 giây **không** bảo đảm cả ba hoàn tất trong 15 giây. Nó bảo vệ mỗi lần chờ phản hồi theo cách driver xác định. Nếu cần request deadline 20 giây, ứng dụng phải áp thêm **deadline propagation/cancellation** ở tầng request và các components liên quan.

### 4.5. Đừng nhầm đơn vị

```java
statement.setQueryTimeout(5);            // 5 GIÂY
connection.setNetworkTimeout(executor, 5); // 5 MILI-GIÂY
```

Hai số nguyên `5` có **đơn vị khác nhau đến 1.000 lần**. Đây là lỗi cấu hình rất dễ xảy ra. Đặt tên biến rõ như `querySeconds`, `networkMillis`; nếu dùng `Duration` trong code ứng dụng, chuyển đổi an toàn và validate giới hạn int trước khi gọi JDBC.

## 5. Nếu network timeout thật sự hết hạn, connection bị gì?

Tài liệu Java SE 17 mô tả:

1. Driver xác định database request không được trả lời trong ngưỡng.
2. JDBC method đang chờ trả về bằng `SQLException`.
3. Connection bị đánh dấu **closed**.
4. Driver giải phóng các tài nguyên liên quan; objects được tạo từ connection cũng không còn sử dụng được theo hợp đồng.
5. Các thao tác tiếp theo, trừ những phương thức ngoại lệ được tài liệu nêu như `close`, `isClosed` hoặc `Connection.isValid`, có thể dẫn tới `SQLException`.

### 5.1. Không cố gọi lại query trên connection đã timed out

Sai:

```java
try {
    statement.executeQuery();
} catch (SQLException error) {
    statement.executeQuery(); // Nguy hiểm: connection có thể đã đóng.
}
```

Đây là **anti-pattern**, với `statement` đã định nghĩa. Nếu network timeout làm connection đóng, retry trên cùng connection không phải lựa chọn hợp lệ. Cần **đóng/loại bỏ connection**, lấy một connection mới qua DataSource/pool và cân nhắc có được phép retry nghiệp vụ hay không.

### 5.2. Query timeout không phải network timeout

Nếu query timeout xảy ra khi network vẫn hoạt động, theo JDBC, statement có thể được cancel và connection **có thể vẫn sử dụng được**. Tuy nhiên vẫn phải xét tình trạng transaction, driver và loại lỗi; không hứa mọi SQLTimeoutException luôn cho connection reusable.

Nếu network timeout xảy ra trước query timeout, hoặc query cancellation thất bại do mạng, JDBC quy định connection không thể dùng tiếp.

### 5.3. Không thể luôn biết một transaction đã commit hay chưa

Ví dụ client gửi COMMIT nhưng mạng đứt trước khi nhận phản hồi: client có thể không biết server đã commit thành công hay chưa. Điều này gọi là **ambiguous outcome**. Đừng tự động retry INSERT/UPDATE/COMMIT mà không có idempotency key, unique constraint, transaction/reconciliation protocol thích hợp.

Network timeout **không phải** transaction rollback guarantee. Việc connection bị đóng không chứng minh thao tác trước đó chắc chắn chưa ảnh hưởng database.

### 5.4. Tại sao chỉ đóng connection là chưa đủ?

Nếu các tasks driver dùng executor còn đang hoạt động, ứng dụng cũng phải quản lý executor lifecycle của chính mình. Cần phân biệt hai tài nguyên:

- **Connection**: dùng try-with-resources hoặc do connection pool quản lý logical lease.
- **Executor**: do owner tạo, cấp cho driver, dùng chung nếu phù hợp, rồi owner shutdown khi không còn cần.

Đóng connection **không đồng nghĩa** phải tắt executor; ngược lại, tắt executor không phải cách đóng database connection.

## 6. Phân biệt quyền sở hữu: owner, borrower và driver

**Owner** là thành phần quyết định tạo tài nguyên, quản lý lifetime và chịu trách nhiệm đóng. **Borrower** chỉ dùng tài nguyên trong phạm vi được cấp và **không tự đóng** nếu hợp đồng không cho phép.

Một kiến trúc phổ biến:

```text
Application / Infrastructure Lifecycle (OWNER)
    |
    +-- ExecutorService networkControlExecutor
    |       |--- passed to JDBC Connection A
    |       |--- passed to JDBC Connection B
    |       +--- possible driver control tasks
    |
    +-- DataSource / Connection Pool
            |--- Connection A lease
            |--- Connection B lease
            +--- Connection C lease

Request handler 1: mượn connection lease và Executor
Request handler 2: mượn connection lease và Executor
Request handler 3: mượn connection lease và Executor

Khi app shutdown:
  1) Stop admission/new requests.
  2) Drain/cancel in-flight JDBC work theo policy.
  3) Close pool/leases and let necessary driver cleanup run.
  4) OWNER shutdown + awaitTermination executor.
```

Đây là **mẫu ownership tham khảo**, không phải một life-cycle duy nhất cho mọi thư viện. Nếu connection pool hoặc framework tự quản lý executor, app phải tuân thủ **hợp đồng của pool** thay vì tạo thêm hoặc đóng tài nguyên của pool.

### 6.1. Borrower không được tự shutdown

Sai:

```java
void executeOneQuery(Connection connection, ExecutorService borrowed)
        throws SQLException {
    try {
        connection.setNetworkTimeout(borrowed, 15_000);
        // SQL query...
    } finally {
        borrowed.shutdown(); // Sai: executor do tầng khác sở hữu!
    }
}
```

Đây là **anti-pattern snippet**: borrower đóng một tài nguyên nó không tạo. Request khác có thể đang dùng executor đó, driver có thể cần thêm callback, và các lời gọi mới sẽ bị từ chối.

Tốt hơn: nếu method chỉ cần `execute(Runnable)`, nhận kiểu `Executor` thay vì `ExecutorService`, để tránh expose trực tiếp API `shutdown()` trong method.

### 6.2. Owner tạo một executor sống đủ lâu

```java
ExecutorService networkExecutor =
        Executors.newFixedThreadPool(2);
```

Đây là snippet trong lifecycle component có import `java.util.concurrent.*`. Đây **không** phải khuyến nghị luôn dùng hai threads; kích thước cần dựa trên hành vi driver, workload và nhu cầu điều phối. Với pool connection có nhiều connections, một shared executor sống dài thường phù hợp hơn tạo mỗi request một executor.

### 6.3. Một ExecutorService riêng cho từng truy vấn là lựa chọn dễ rò rỉ

Ví dụ sai:

```java
void run(Connection connection) throws SQLException {
    ExecutorService executor = Executors.newSingleThreadExecutor();
    connection.setNetworkTimeout(executor, 15_000);
    // Không shutdown, thread sống không cần thiết.
}
```

Đây là **anti-pattern** vì method tạo executor nhưng không quản lý đúng vòng đời. Nếu thêm `executor.shutdown()` ngay sau setter, lại có nguy cơ driver cần executor trong các operations sau đó. Chủ sở hữu nên tạo executor ở phạm vi **application/service/pool**, hoặc nếu thật sự per-connection thì đảm bảo lifetime ít nhất bao trùm việc sử dụng connection và cleanup thích hợp.

### 6.4. Shutdown quá sớm có thể khiến task bị từ chối

Sau `ExecutorService.shutdown()`, lời gọi submit/execute mới có thể gặp `RejectedExecutionException`. Nếu driver cần enqueue một nhiệm vụ liên quan đến timeout hoặc abort sau đó, nó có thể không thực hiện được theo ý định. JDBC API không quy định chi tiết mọi failure mode khi executor từ chối tác vụ; hãy **tránh tạo rủi ro** bằng cách giữ executor hoạt động đúng lifetime.

### 6.5. Shutdown không tương đương xong mọi callback

`shutdown()` chỉ ngừng nhận tasks mới và cho tasks đã submit tiếp tục. `awaitTermination(timeout,unit)` cho owner đợi đến khi tasks thực sự kết thúc. `shutdownNow()` cố interrupt tasks còn chạy, **không bảo đảm** mọi callback lập tức dừng.

Trong Java 17, `ExecutorService` **không extends `AutoCloseable`**, nên dùng `try/finally`, `shutdown()` và `awaitTermination()`. Không viết `try (ExecutorService e=...)` rồi bảo đảm `javac --release 17` sẽ biên dịch.

## 7. Executor dành cho JDBC cần có đặc tính gì?

Một executor phù hợp nên:

- **Có chủ sở hữu rõ ràng** và lifetime dài hơn các operations có thể cần nó.
- Có khả năng chạy công việc **độc lập** với thread đang gọi JDBC và có thể bị chặn bởi network.
- Không phụ thuộc vào cùng một worker pool đã bị **starvation** bởi các JDBC calls đang chờ.
- Không bị shutdown chỉ vì một request hoàn tất.
- Có chính sách quản lý queue/capacity/rejection hợp lý.
- Có monitoring cho active threads, queue saturation, rejected tasks và shutdown.
- Không phải nơi chứa những tác vụ business rất chậm khiến callbacks của driver bị đẩy lùi.
- Phù hợp tài liệu driver và pool đang sử dụng.

### 7.1. Không dùng chung executor đã bận bởi toàn bộ blocking SQL nếu có nguy cơ starvation

Ví dụ có một pool với chỉ hai workers; cả hai workers đang chờ network I/O. Nếu driver phải lên lịch tác vụ timeout/abort lên chính pool đang bị kẹt, không còn worker rảnh. **Đây là rủi ro thiết kế**, không phải lời hứa driver nào cũng hoạt động vậy. Tách executor điều khiển phù hợp hoặc dùng executor do driver/pool khuyến nghị.

### 7.2. Không mặc định ForkJoinPool.commonPool phù hợp

Common pool được nhiều thành phần sử dụng, chủ yếu tối ưu cho công việc tính toán có thể chia nhỏ. Nếu callbacks của driver có thể block hoặc có yêu cầu isolation, việc dùng commonPool có thể khó quản lý tải và lifecycle. Ngoài ra, module không sở hữu commonPool và không nên shutdown nó. Chọn executor theo hợp đồng nhà cung cấp và thiết kế infrastructure.

### 7.3. ThreadFactory có thể đặt tên để quan sát

Có thể cấu hình thread names như `jdbc-control-1`, `jdbc-control-2` trong executor service được owner tạo. Điều này giúp thread dumps và monitoring. Nhưng không dùng tên thread làm bằng chứng driver bắt buộc sử dụng executor trong từng lần `setNetworkTimeout`: hành vi lịch chạy phụ thuộc driver.

### 7.4. Không coi Executor là một scheduler timeout của ứng dụng

`Executor` chỉ có method `execute(Runnable)`. Nó **không** có `schedule(Runnable,delay)` như `ScheduledExecutorService`. Việc đếm timeout là phần driver/JDBC semantics, không phải vì code người dùng viết một `Thread.sleep(milliseconds)` trong executor.

Không viết:

```java
executor.execute(() -> {
    Thread.sleep(15_000); // Không phải triển khai JDBC network timeout.
});
```

Đây là pseudo **anti-pattern** (chưa xử lý InterruptedException); nó không làm connection đóng một cách đúng chuẩn. Cơ chế timeout là trách nhiệm driver.

## 8. Chương trình Java 17+ hoàn chỉnh: kiểm thử JDBC API bằng Connection giả lập

Vì bài học cần **có thể biên dịch và chạy mà không có DB server hoặc JDBC driver bên ngoài**, ví dụ đầu tiên sử dụng Java **dynamic proxy** tạo một đối tượng implement `java.sql.Connection` giả lập.

**Giới hạn phải hiểu trước khi chạy:** Đây là **test double (mock/fake)**. Nó **không gửi SQL qua mạng, không mô phỏng chính xác JDBC driver thật** và **không chứng minh socket timeout xảy ra**. Nó chỉ giúp kiểm tra:

1. Chữ ký và cách gọi `setNetworkTimeout(Executor,int)` / `getNetworkTimeout()`.
2. Dùng chung một executor cho hai logical connections.
3. Method không tự shutdown executor do caller sở hữu.
4. Giá trị 0, timeout âm, driver không hỗ trợ.
5. `abort(executor)` có thể dispatch một callback cleanup trong mô hình giả lập và connection trở thành closed.
6. **Chỉ owner** shutdown executor sau khi các connections/cleanup hoàn tất.

**Tệp: `NetworkTimeoutContractDemo.java`**

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class NetworkTimeoutContractDemo {
    private static final class FakeDriver implements InvocationHandler {
        private final boolean supportsTimeout;
        private int timeoutMillis;
        private boolean closed;
        private CountDownLatch abortedTaskFinished;

        FakeDriver(boolean supportsTimeout) {
            this.supportsTimeout = supportsTimeout;
        }

        Connection connection() {
            return (Connection) Proxy.newProxyInstance(
                    Connection.class.getClassLoader(),
                    new Class<?>[]{Connection.class}, this);
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Exception {
            switch (method.getName()) {
                case "setNetworkTimeout" -> {
                    if (closed) throw new SQLException("connection closed");
                    if (!supportsTimeout) {
                        throw new SQLFeatureNotSupportedException("not supported");
                    }
                    Executor executor = (Executor) args[0];
                    int value = (Integer) args[1];
                    if (executor == null || value < 0) {
                        throw new SQLException("bad arguments");
                    }
                    timeoutMillis = value;
                    return null;
                }
                case "getNetworkTimeout" -> {
                    if (!supportsTimeout) {
                        throw new SQLFeatureNotSupportedException("not supported");
                    }
                    if (closed) throw new SQLException("connection closed");
                    return timeoutMillis;
                }
                case "abort" -> {
                    Executor executor = (Executor) args[0];
                    if (executor == null) throw new SQLException("null executor");
                    closed = true;
                    abortedTaskFinished = new CountDownLatch(1);
                    executor.execute(abortedTaskFinished::countDown);
                    return null;
                }
                case "close" -> {
                    closed = true;
                    return null;
                }
                case "isClosed" -> {
                    return closed;
                }
                case "isValid" -> {
                    return !closed;
                }
                case "toString" -> {
                    return "FakeJdbcConnection";
                }
                default -> throw new SQLFeatureNotSupportedException(
                        "Mock only supports timeout/lifecycle methods");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService ownedExecutor = Executors.newSingleThreadExecutor();
        try {
            FakeDriver driverA = new FakeDriver(true);
            FakeDriver driverB = new FakeDriver(true);
            try (Connection a = driverA.connection();
                 Connection b = driverB.connection()) {
                a.setNetworkTimeout(ownedExecutor, 12_000);
                b.setNetworkTimeout(ownedExecutor, 15_000);
                System.out.println("A timeout ms = " + a.getNetworkTimeout());
                System.out.println("B timeout ms = " + b.getNetworkTimeout());
                System.out.println("executor still open = " +
                        !ownedExecutor.isShutdown());

                a.setNetworkTimeout(ownedExecutor, 0);
                System.out.println("A disabled = " +
                        (a.getNetworkTimeout() == 0));

                boolean invalidRejected = false;
                try {
                    a.setNetworkTimeout(ownedExecutor, -1);
                } catch (SQLException expected) {
                    invalidRejected = true;
                }
                System.out.println("negative timeout rejected = " +
                        invalidRejected);

                boolean unsupported = false;
                try (Connection c = new FakeDriver(false).connection()) {
                    c.setNetworkTimeout(ownedExecutor, 5_000);
                } catch (SQLFeatureNotSupportedException expected) {
                    unsupported = true;
                }
                System.out.println("unsupported detected = " + unsupported);

                b.abort(ownedExecutor);
                System.out.println("B closed after abort = " + b.isClosed());
                System.out.println("abort callback done = " +
                        driverB.abortedTaskFinished.await(5, TimeUnit.SECONDS));
            }
        } finally {
            ownedExecutor.shutdown();
            if (!ownedExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
                ownedExecutor.shutdownNow();
            }
        }
        System.out.println("owned executor terminated = " +
                ownedExecutor.isTerminated());
    }
}
```

Biên dịch và chạy (không cần JDBC driver/DB):

```bash
javac --release 17 NetworkTimeoutContractDemo.java
java NetworkTimeoutContractDemo
```

**Stdout được kiểm thử trên Windows/JDK 24, Java 17-compatible:**

```text
A timeout ms = 12000
B timeout ms = 15000
executor still open = true
A disabled = true
negative timeout rejected = true
unsupported detected = true
B closed after abort = true
abort callback done = true
owned executor terminated = true
```

### 8.1. Vai trò của dynamic proxy

`Proxy.newProxyInstance` tạo object implement interface `Connection`. `FakeDriver.invoke()` phản hồi một số phương thức dùng trong bài. Các phương thức khác cố ý ném `SQLFeatureNotSupportedException`; đây không phải một JDBC driver đủ chức năng.

### 8.2. Hai connections dùng một executor là hợp lệ

Cả `a.setNetworkTimeout(ownedExecutor, ...)` và `b.setNetworkTimeout(ownedExecutor, ...)` đều nhận **cùng executor**. Executor có thể được share bởi nhiều connections nếu owner thiết kế và sizing phù hợp. Bản thân gọi setter không khiến executor tự shutdown.

### 8.3. Cấu hình timeout thuộc connection, không thuộc executor

Hai connections nhận 12.000 ms và 15.000 ms khác nhau trong mock, dù executor giống nhau. Điều này minh họa **ngưỡng network timeout được cấu hình trên Connection**; executor là tài nguyên thực thi hỗ trợ, không phải object giữ một “timeout chung” cho mọi connections.

### 8.4. Vì sao có CountDownLatch?

Mock `abort` gửi một callback vào executor rồi trả về. `CountDownLatch.await` được dùng để đợi callback mô phỏng kết thúc trước khi owner shutdown. Javadoc `Connection.abort` nói việc giải phóng tài nguyên **có thể còn tiếp diễn sau khi abort trả về**.

Nhưng demo **không** chứng minh một JDBC driver thật nhất định submit đúng một callback hoặc gọi `countDown` tương tự. Cách thực thi và tình trạng các tasks sau abort là đặc thù implementation.

### 8.5. Tại sao “executor still open = true” quan trọng?

Nó chứng minh code cấu hình hai connections **không chiếm quyền shutdown** executor. Trong thực tế, nếu nhiều request đang dùng một executor, tắt nó từ method ngắn hạn có thể khiến request khác và driver cleanup gặp sự cố.

### 8.6. Tại sao chỉ fake được kiểm thử, không giả lập network timeout thực?

Một network timeout thật cần JDBC driver và cơ sở dữ liệu/network fault injection. Fake trên không chờ 12 hoặc 15 giây và không đóng connection vì một socket read bị treo. Đừng lấy output “A timeout ms = 12000” làm bằng chứng driver production hỗ trợ mạng hoặc deadline chính xác.

## 9. Chương trình Java 17+: biểu diễn policy timeout và kiểm tra thứ tự

Một service có thể gom các số cấu hình với **đơn vị rõ ràng** và bắt các cấu hình vô lý ngay khi startup.

**Tệp: `TimeoutPolicyDemo.java`**

Chương trình sau đưa ra một **policy ví dụ của ứng dụng**: login timeout phải dương, query timeout phải dương, network timeout dương và cao hơn query timeout. Đây **không phải validation bắt buộc của JDBC**: JDBC cho phép network timeout 0 để tắt, cho phép các mức timeout khác nhau tùy use case. Record này cố ý chặt hơn API để mô tả một cấu hình “network timeout là hàng rào cuối”.

```java
import java.util.concurrent.TimeUnit;

public class TimeoutPolicyDemo {
    private record Policy(int loginSeconds, int querySeconds,
                          int networkMillis) {
        Policy {
            if (loginSeconds <= 0 || querySeconds <= 0 ||
                    networkMillis <= 0) {
                throw new IllegalArgumentException("timeouts must be positive");
            }
            long queryMillis = TimeUnit.SECONDS.toMillis(querySeconds);
            if (networkMillis <= queryMillis) {
                throw new IllegalArgumentException(
                        "network guard must be greater than query timeout");
            }
        }
    }

    public static void main(String[] args) {
        Policy p = new Policy(3, 5, 15_000);
        System.out.println("login timeout seconds = " + p.loginSeconds());
        System.out.println("query timeout seconds = " + p.querySeconds());
        System.out.println("network timeout millis = " + p.networkMillis());
        System.out.println("query before network = " +
                (TimeUnit.SECONDS.toMillis(p.querySeconds()) <
                 p.networkMillis()));

        boolean wrongOrderRejected = false;
        try {
            new Policy(3, 12, 5_000);
        } catch (IllegalArgumentException expected) {
            wrongOrderRejected = true;
        }
        System.out.println("wrong order rejected = " + wrongOrderRejected);
    }
}
```

Chạy:

```bash
javac --release 17 TimeoutPolicyDemo.java
java TimeoutPolicyDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
login timeout seconds = 3
query timeout seconds = 5
network timeout millis = 15000
query before network = true
wrong order rejected = true
```

### 9.1. Tại sao dùng TimeUnit?

`TimeUnit.SECONDS.toMillis(querySeconds)` làm chuyển đổi đơn vị rõ ràng và an toàn hơn viết `querySeconds * 1000` với kiểu int, vốn có thể overflow khi số quá lớn. Ở đây so sánh bằng long; `networkMillis` vẫn là int theo chữ ký JDBC.

### 9.2. Nên nhận cấu hình theo Duration không?

Có thể: `java.time.Duration` là abstraction tốt trong application code, rồi chuyển sang int milliseconds/seconds khi gọi JDBC. Nhưng phải kiểm tra:

- Giá trị không âm hoặc dương theo policy.
- Chuyển đổi có thể vượt `Integer.MAX_VALUE` milliseconds.
- Các Duration có phần lẻ dưới mili-giây có thể bị làm tròn/truncate khi đổi đơn vị.
- Không lẫn `Duration.ofSeconds(15)` với số `15` ms của setter.

Nếu business cần một duration dài hơn giới hạn int ms, không ép kiểu lặng lẽ; phải chọn giới hạn hoặc cấu hình driver cụ thể có range khác theo tài liệu.

### 9.3. Mối quan hệ với transaction timeout

Tài liệu JDBC khuyến nghị network timeout đủ cao để không kích hoạt trước các timeout thông thường như transaction timeout. Ví dụ record chỉ so với **query timeout**, chưa mô hình hóa transaction framework timeout. Trong production, xét toàn bộ timeout stack, request deadline và recovery policy.

## 10. Chương trình Java 17+: bên mượn executor không được đóng nó

Để làm rõ **ownership** tách biệt hoàn toàn với driver implementation, ví dụ này chỉ dùng java.util.concurrent, mô phỏng một thành phần nhận `Executor` để dispatch callback. Không có Connection hay DB, vì mục tiêu là chứng minh **borrower dùng, owner đóng**.

**Tệp: `BorrowedExecutorDemo.java`**

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class BorrowedExecutorDemo {
    private static void useBorrowed(Executor executor,
                                    CountDownLatch completed) {
        executor.execute(completed::countDown);
        // Never close/shutdown an executor owned by our caller.
    }

    public static void main(String[] args) throws Exception {
        ExecutorService owner = Executors.newFixedThreadPool(2);
        boolean allCallbacks;
        boolean remainedOpen;
        try {
            CountDownLatch completed = new CountDownLatch(3);
            useBorrowed(owner, completed);
            useBorrowed(owner, completed);
            useBorrowed(owner, completed);
            allCallbacks = completed.await(5, TimeUnit.SECONDS);
            remainedOpen = !owner.isShutdown();
        } finally {
            owner.shutdown();
            if (!owner.awaitTermination(5, TimeUnit.SECONDS)) {
                owner.shutdownNow();
            }
        }
        System.out.println("callbacks completed = " + allCallbacks);
        System.out.println("borrowed executor remained open = " + remainedOpen);
        System.out.println("owner terminated executor = " +
                owner.isTerminated());
    }
}
```

Chạy:

```bash
javac --release 17 BorrowedExecutorDemo.java
java BorrowedExecutorDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
callbacks completed = true
borrowed executor remained open = true
owner terminated executor = true
```

### 10.1. Vì sao method chỉ nhận Executor?

`useBorrowed(Executor executor,...)` chỉ cần phương thức `execute()`, không cần quyền `shutdown()`. Nhận interface nhỏ nhất thể hiện ý định: method **không sở hữu lifecycle**.

### 10.2. Vì sao owner gọi shutdown sau khi callbacks xong?

`CountDownLatch.await` đợi ba callbacks hoàn tất. Sau đó owner mới đóng pool ở `finally`. Trong JDBC thực tế, tình huống có thể phức tạp hơn: callbacks của driver có thể không có handle bạn quản lý, vì thế owner cần thiết kế shutdown sau khi dừng các operations và giải phóng connection pool.

### 10.3. Nếu awaitTermination hết thời gian?

Demo gọi `shutdownNow()` nếu các tasks không kết thúc kịp. Trong production có thể cần log cảnh báo, thêm deadline và theo dõi tasks còn chạy. `shutdownNow()` là nỗ lực ngắt tasks, **không bảo đảm** tất cả dừng ngay.

### 10.4. Đây có phải ví dụ query JDBC?

Không. Nó chứng minh nguyên tắc về executor ownership trong Java concurrency. Để áp dụng với JDBC, service/pool có thể **mượn cùng Executor** qua `Connection.setNetworkTimeout` và chỉ owner được dừng executor.

## 11. Mẫu tích hợp với DataSource và PreparedStatement thực tế

Trong ứng dụng thật, nên sử dụng `javax.sql.DataSource` để tạo/thuê Connection; đây là API JDBC được Java khuyến nghị thay cho phụ thuộc trực tiếp vào một global DriverManager setup.

Dưới đây là một **mẫu lớp Java 17+ có thể biên dịch**, nhưng chỉ chạy được khi application đã cung cấp:
- `DataSource` được cấu hình với JDBC driver và database thực.
- Bảng `orders` có cột `id`, `status`.
- Executor do tầng infrastructure sở hữu và đang hoạt động.

**Tệp mẫu tích hợp: `JdbcTimeoutUseCase.java`** — class không có `main()` vì phụ thuộc vào application wiring; **không có stdout cố định** để tránh bịa response của database.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.Executor;
import javax.sql.DataSource;

public final class JdbcTimeoutUseCase {
    private final DataSource dataSource;
    private final Executor networkExecutor;

    public JdbcTimeoutUseCase(DataSource dataSource,
                              Executor networkExecutor) {
        this.dataSource = Objects.requireNonNull(dataSource);
        this.networkExecutor = Objects.requireNonNull(networkExecutor);
    }

    public List<Long> findReadyOrderIds() throws SQLException {
        List<Long> ids = new ArrayList<>();
        try (Connection connection = dataSource.getConnection()) {
            connection.setNetworkTimeout(networkExecutor, 15_000);
            try (PreparedStatement statement = connection.prepareStatement(
                    "SELECT id FROM orders WHERE status = ?")) {
                statement.setString(1, "READY");
                statement.setQueryTimeout(5);
                try (ResultSet result = statement.executeQuery()) {
                    while (result.next()) {
                        ids.add(result.getLong(1));
                    }
                }
            }
        }
        return ids;
    }
}
```

### 11.1. Chỗ nào sở hữu executor?

Constructor chỉ nhận `Executor` và giữ reference để **dùng**, không gọi `shutdown()`. Thành phần cấu hình app sẽ tạo một `ExecutorService` phù hợp, đưa nó vào `JdbcTimeoutUseCase`, rồi **đóng chính ExecutorService đó trong application shutdown** sau khi các operations/pool không còn cần.

### 11.2. Chỗ nào sở hữu connection?

`findReadyOrderIds()` mượn `Connection` từ DataSource trong phạm vi try-with-resources rồi đóng logical connection handle ở cuối. Nếu DataSource là connection pool, `close()` trên logical handle thường **trả connection về pool** thay vì đóng socket vật lý ngay. Chi tiết reset network timeout và connection state là trách nhiệm/cấu hình của pool; không đoán và không override bừa.

### 11.3. PreparedStatement và ResultSet phải được đóng

Try-with-resources đóng `ResultSet`, `PreparedStatement` và `Connection` khi rời scope, kể cả khi ném exception. Đóng các JDBC resources **không shutdown executor**. Lấy timeout/transaction behavior từ driver/pool contract thực tế.

### 11.4. Khi driver không hỗ trợ setNetworkTimeout?

Method có thể ném `SQLFeatureNotSupportedException`, là subclass của `SQLException`. Trong mẫu trên, exception được propagate về caller, thay vì ngầm bỏ qua một policy safety quan trọng. Ứng dụng có thể quyết định startup fail hoặc dùng **driver-specific socket/read timeout** đã được xác minh và cấu hình ở pool; nhưng không tuyên bố rằng `setQueryTimeout` đơn thuần thay thế đầy đủ chức năng network timeout.

### 11.5. Có nên reset network timeout ở finally?

Nếu đây là connection **do pool cấp**, xem pool có reset trạng thái connection khi trả về hay không. Nhiều pool quản lý các thuộc tính connection theo chính sách riêng. Đừng dùng `setNetworkTimeout(executor,0)` vô điều kiện ngay trước `close()` vì có thể làm sai baseline timeout của pooled physical connection.

Với một connection do ứng dụng sở hữu hoàn toàn và được chia sẻ qua nhiều scopes có điều phối, có thể đọc `getNetworkTimeout()` trước, tạm thay đổi, rồi phục hồi **nếu connection vẫn mở**. Tuy nhiên phải xử lý exception trong finally cẩn thận để không che nguyên nhân lỗi chính. Trong production, dùng policy nhất quán tại lúc tạo/checkout connection thường đơn giản hơn.

## 12. Bảo đảm hỗ trợ driver: SQLFeatureNotSupportedException

JDBC interface có method `setNetworkTimeout` nhưng **không có nghĩa mọi vendor driver bắt buộc thực hiện được**. Nếu driver không hỗ trợ, Javadoc nêu `SQLFeatureNotSupportedException`.

### 12.1. Không catch rồi cho rằng timeout vẫn đang hoạt động

Sai:

```java
try {
    connection.setNetworkTimeout(executor, 15_000);
} catch (SQLFeatureNotSupportedException ignored) {
    // Nguy hiểm: ứng dụng tiếp tục như thể mạng đã được bảo vệ.
}
```

Đây là anti-pattern nếu timeout là một yêu cầu vận hành bắt buộc. Nếu bỏ qua, JDBC calls có thể vẫn chờ rất lâu trong điều kiện mạng xấu.

Tốt hơn:

```java
try {
    connection.setNetworkTimeout(executor, 15_000);
} catch (SQLFeatureNotSupportedException unsupported) {
    throw new SQLException(
            "JDBC driver cannot enforce the required network timeout",
            unsupported);
}
```

Đây là **snippet trong method**; logger/alerting và chiến lược fallback phụ thuộc app. Trong production, nhiều nơi kiểm tra capability ngay startup hoặc integration test thay vì đợi lỗi đầu tiên trong production traffic.

### 12.2. Có thể có cơ chế thay thế ở driver

Một số driver cung cấp các thuộc tính **connectTimeout**, **socketTimeout**, **readTimeout**, **queryTimeout** hoặc tên tương đương. Chúng **không đồng nhất giữa vendors**, có thể đặt ở JDBC URL, DataSource property hoặc API riêng. Tham khảo đúng phiên bản driver đang dùng và test network fault thực tế trước khi tuyên bố tương đương `setNetworkTimeout`.

### 12.3. Getter cũng có thể không được hỗ trợ

`connection.getNetworkTimeout()` cũng có thể ném `SQLFeatureNotSupportedException`. Không dùng getter làm “capability probe miễn phí” rồi giả định mọi driver đều có cùng semantics. Dùng connection integration test, vendor documentation và cấu hình pool.

## 13. Connection.abort(Executor): liên quan nhưng không giống setNetworkTimeout

JDBC có:

```java
connection.abort(executor);
```

`abort` được thiết kế để **kết thúc một connection đang mở**, có thể dùng từ một thread quản trị khi cần giải phóng một connection bị mắc kẹt. Tài liệu Java 17 mô tả:

- Connection bị đánh dấu closed.
- Kết nối vật lý tới database được đóng.
- Tài nguyên liên quan được giải phóng.
- Thread đang truy cập connection sẽ tiến tới hoàn thành hoặc ném SQLException.
- Khi `abort` trả về, connection đã được đánh dấu closed, nhưng executor **có thể vẫn đang chạy tasks** để giải phóng tài nguyên.
- Gọi `abort` trên connection đã closed là no-op.

### 13.1. Khi nào dùng abort?

Dùng khi có **chính sách hủy/khẩn cấp** được kiểm soát, ví dụ quản trị muốn giải phóng connection bị network hang, theo yêu cầu driver/pool. Không dùng `abort` mỗi khi một query bình thường kết thúc: dùng `close()` hoặc trả logical connection về pool theo try-with-resources.

### 13.2. Network timeout tự động khác abort chủ động

- `setNetworkTimeout` đặt trước một ngưỡng để driver phát hiện và đóng connection nếu chờ phản hồi quá lâu.
- `abort` là lời gọi chủ động để kết thúc connection.

Cả hai liên quan đến executor và có thể kết thúc connection, nhưng **không phải cùng API**, và không thể tự động xem một lời gọi abort là query timeout.

### 13.3. Vì sao shutdown executor ngay sau abort có thể sai?

Javadoc nêu rõ executor **có thể còn xử lý việc giải phóng tài nguyên sau khi abort trả về**. Nếu owner gọi `shutdownNow()` ngay tức khắc, có thể làm gián đoạn cleanup. Nếu một borrower shutdown shared executor, còn nguy hiểm hơn vì ảnh hưởng những connections khác.

Owner nên điều phối:
- Stop new work.
- Gọi abort khi chính sách cho phép.
- Theo dõi connection/pool shutdown và driver cleanup theo khả năng quan sát.
- Cho các tasks đã được gửi cơ hội chạy xong.
- Sau cùng shutdown executor và awaitTermination theo deadline hợp lý.

### 13.4. Executor không phải bảo đảm mọi cleanup sẽ luôn hoàn thành

Ngay cả executor hoạt động, network/driver có thể có lỗi. `abort` không biến một kết nối hỏng thành có thể tái sử dụng; không “undo” các thao tác DB có kết quả chưa rõ. Cần recovery policy và đo diagnostics.

## 14. Phân biệt connection pool lifecycle và executor lifecycle

Trong nhiều ứng dụng production, cả hai được một framework quản lý:

```text
App runtime
  |--> DataSource / JDBC connection pool
  |      |--> logical Connection lease (request 1)
  |      |--> logical Connection lease (request 2)
  |      |--> physical database connections
  |
  |--> ExecutorService (nếu app sở hữu)
         |--> driver support tasks / abort callbacks

Request 1 kết thúc:
  close(logical Connection) -> pool quản lý trả/loại connection
  KHÔNG shutdown(ExecutorService).

Toàn app kết thúc:
  stop admission -> drain in-flight -> pool close
  -> owner shutdown(ExecutorService) -> awaitTermination.
```

### 14.1. Pool có thể làm thay đổi trạng thái physical connection

Một `Connection` được pool trả về có thể là **wrapper** cho physical connection. Phương thức `setNetworkTimeout` có thể được forward tới driver hoặc được pool quản lý theo cách riêng. Tài liệu của pool/driver quyết định cách reset. Việc gọi `close()` trên logical handle **không nhất thiết** đóng socket.

Không giả định `getNetworkTimeout()` sau checkout luôn là 0, vì pool có thể áp một baseline nonzero.

### 14.2. Không giữ logical Connection sau khi đóng

Nếu try-with-resources đóng connection, không giữ `PreparedStatement`/`ResultSet` từ connection đó rồi đọc ở thread khác. Khi network timeout đóng connection, các objects cũng bị ảnh hưởng. Hợp đồng lifecycle của JDBC phải được giữ.

### 14.3. Không dùng đồng thời một Connection từ nhiều threads nếu driver không bảo đảm

Một số JDBC driver/pool không hỗ trợ mọi operation concurrent trên cùng Connection. Network timeout không biến Connection thành immutable/thread-safe object. Nên một logical JDBC transaction thường thuộc một luồng/đơn vị công việc, hoặc thực hiện theo khả năng hỗ trợ được tài liệu driver xác nhận. Shared Executor **không đồng nghĩa** Connection nên được chia sẻ giữa requests.

### 14.4. Dừng pool trước khi dừng executor?

Nếu executor có thể được driver dùng để phục vụ timeout/abort trong lúc pool đang đóng connections, phải giữ nó hoạt động đủ lâu. Thứ tự thực tế còn phụ thuộc integration và pool có sở hữu executor hay không; ghi rõ dependency để shutdown không tạo vòng chờ.

## 15. Những tình huống sự cố nên kiểm tra trong môi trường test

Network timeout là một tính năng liên quan fault tolerance; **kiểm thử happy path chưa đủ**.

### 15.1. Database không phản hồi một request

Khi giả lập mạng mất gói/partition sau khi một query đã được gửi, đo:

- Thread đang chờ phản hồi có thoát theo policy không?
- Driver có ném SQLException không?
- Connection bị marked closed và pool loại khỏi sử dụng không?
- Statement/ResultSet liên quan có còn dùng được không?
- Có threads/tài nguyên bị giữ lâu không?
- Ứng dụng có thử lại nghiệp vụ an toàn không?

Đừng yêu cầu luôn đúng chính xác 15.000 ms trên đồng hồ: driver được phép làm tròn, network faults khó tái tạo tuyệt đối và có những giai đoạn nhiều request nội bộ.

### 15.2. Query chậm nhưng mạng vẫn tốt

Một SQL cố tình chậm về CPU/lock có thể bị `setQueryTimeout` trước, trong khi `setNetworkTimeout` đặt cao hơn. Kỳ vọng là statement timeout được xử lý mà connection có thể vẫn dùng được nếu phù hợp. Nhưng điều kiện DB/driver có thể khiến transaction phải rollback hoặc pool loại connection; không hardcode một giả định “mọi query timeout connection vẫn sống”.

### 15.3. Network timeout trước query timeout

Cấu hình sai thứ tự hoặc mạng rất xấu có thể làm network guard kích hoạt trước. Khi đó connection bị đóng. Test code không cố reuse connection, và pool tạo/thuê connection mới theo policy.

### 15.4. Executor shutdown sớm

Có thể thiết kế integration test có kiểm soát để xác nhận hệ thống **không shutdown shared executor** trong phạm vi request. Không nên cố làm hỏng production bằng cách ngắt executor đang dùng chung; dùng test doubles/fault injection và kiểm tra lifecycle logs.

### 15.5. Driver không hỗ trợ network timeout

Tạo test với một mock như demo hoặc một driver trong môi trường test không hỗ trợ method, xác nhận application **fail fast** nếu network timeout là bắt buộc. Nếu fallback, test lại chính loại timeout vendor-specific được chọn.

### 15.6. Connection pool reused after borrow

Test một logical connection lease được cấu hình timeout rồi trả về pool. Lần checkout kế tiếp có nhận baseline đúng theo pool policy không? Không dựa vào hành vi của một driver khác. Đảm bảo timeout không bị rò rỉ giữa các clients có policy khác nhau.

### 15.7. Shutdown có transaction đang chờ

Test thứ tự: ngừng nhận request mới → chờ hoặc cancel transactions đang chạy → đóng pool → executor owner shutdown. Quan sát threads, connection metrics và lỗi shutdown. Tránh deadlock do pool shutdown chờ executor trong khi executor đã bị dừng.

## 16. Timeout không tương đương cancellation an toàn mọi trường hợp

Một ứng dụng có thể đặt `Future.get(timeout)` quanh task JDBC:

```java
Future<?> queryFuture = executor.submit(() -> runQuery());
queryFuture.get(5, TimeUnit.SECONDS);
```

Đây là **snippet minh họa**: `executor` và `runQuery` do ứng dụng định nghĩa. Nó giới hạn **thời gian caller chờ Future**, không tự bảo đảm JDBC network I/O đã bị hủy hoặc connection đã đóng khi Future timeout. Nếu worker bị block trong driver, `Future.cancel(true)` có thể không cắt được socket read tùy driver.

Vì vậy nên phân tầng:

- Caller deadline: giới hạn thời gian người dùng/API được phép chờ.
- Query timeout: driver yêu cầu statement ngừng theo API.
- Network timeout: hàng rào bảo vệ network-hang có thể đóng connection.
- Driver socket/connect timeout: nếu cần, cấu hình vendor-specific.
- Transaction recovery: xử lý trạng thái DB có thể chưa rõ.

### 16.1. Không tạo task mới mà quên hủy task cũ

Nếu caller timeout nhưng task JDBC cũ vẫn chạy, retry ngay một task mới có thể làm DB chịu **nhiều truy vấn trùng lặp** và connection pool cạn. Phải theo dõi in-flight operations, cancellation, retry budget và idempotency.

### 16.2. Không lẫn query timeout với pool-acquisition timeout

Nếu không có connection rảnh, thread có thể chờ ở `dataSource.getConnection()` **trước khi có Connection để gọi setNetworkTimeout**. Trường hợp này thuộc pool acquisition/login configuration. Đặt network timeout trên connection không sửa được tình trạng pool bị cạn ngay từ đầu.

## 17. Giá trị millis, overflow và cấu hình an toàn

Chữ ký JDBC dùng `int milliseconds`. Nghĩa là không thể truyền một `long` milliseconds quá lớn mà bỏ qua kiểm tra.

### 17.1. Cấu hình theo Duration

Một helper ở tầng ứng dụng:

```java
static int positiveMillis(Duration timeout) {
    Objects.requireNonNull(timeout, "timeout");
    long millis = timeout.toMillis();
    if (millis <= 0 || millis > Integer.MAX_VALUE) {
        throw new IllegalArgumentException("timeout out of JDBC range");
    }
    return (int) millis;
}
```

Đây là **snippet** với imports `java.time.Duration` và `java.util.Objects`. Khi Duration không phải số ms nguyên, `toMillis()` có thể truncate phần dưới ms; nếu điều đó ảnh hưởng SLA, cần policy rounding/validation riêng. `Duration.toMillis()` cũng có thể throw `ArithmeticException` nếu conversion overflow long.

### 17.2. Kiểm tra cận trước khi cast

Sai:

```java
int networkMillis = (int) duration.toMillis();
```

Nếu Duration quá lớn, cast long→int **cắt bớt bits** và có thể thành âm hoặc một số khác. Hãy validate trước, như helper trên.

### 17.3. 0 có ý nghĩa đặc biệt, không cùng với “không cấu hình”

Nếu application config không có giá trị, nên dùng một kiểu trạng thái tường minh như `Optional<Duration>`/configuration object để phân biệt:
- Để pool/vendor default.
- Chủ động đặt network timeout nonzero.
- Chủ động disable bằng 0.

Đừng tự chuyển mọi cấu hình missing thành 0 và vô tình tắt baseline timeout của pool.

### 17.4. Các driver có thể làm tròn

JDBC nói nếu driver không hỗ trợ độ phân giải ms thì có thể làm tròn lên giây gần nhất. Do đó 1.500 ms có thể thực tế trở thành 2 giây theo cách driver áp dụng. Nếu ứng dụng cần deadline cực chặt ở mức ms, phải test driver/network thật và cân nhắc kiến trúc khác, không chỉ tin setter.

## 18. Kiểm thử logic không phụ thuộc network thật

Hai dạng test nên **tách biệt**:

### 18.1. Unit tests với fake Connection

Unit tests có thể dùng dynamic proxy như `NetworkTimeoutContractDemo` để xác nhận:
- Application gọi `setNetworkTimeout` với đúng `Executor` và millis.
- Các failure states được propagate.
- Caller không shutdown borrowed executor.
- Connection.close được gọi khi rời scope.
- Driver unsupported được xử lý đúng policy.

Unit test **không chứng minh** khả năng ngắt một socket read thật của database driver.

### 18.2. Integration tests với driver/database thật

Dùng một database/driver cùng version đang triển khai, gây lỗi network bằng môi trường test được kiểm soát, rồi quan sát behavior thực tế. Nên có tests:
- Trả lời bình thường.
- Server xử lý query chậm.
- Mạng đứt sau khi request đã đi.
- Timeout khi đọc kết quả nhiều batch.
- Timeout trong transaction có write.
- Pool recovery và reconnection.
- Shutdown khi đang có request block.
- Driver chỉ hỗ trợ một số timeout riêng.

Không thực hiện fault injection nguy hiểm trên database production.

### 18.3. Assertion cần tránh

- “Task luôn timeout đúng 15.000 ms, sai 1 ms là bug.”
- “Query timeout xảy ra thì Connection chắc chắn closed.”
- “Network timeout xảy ra thì Connection vẫn có thể reuse.”
- “Calling setter chắc chắn submit đúng 1 Runnable lên Executor.”
- “Nếu Future.get() timeout thì JDBC driver đã ngừng thực thi.”
- “Connection.close() bắt buộc shutdown mọi Executor.”
- “Mọi JDBC driver hỗ trợ setNetworkTimeout.”
- “Không thể có uncertain commit outcome sau network failure.”

### 18.4. Assertion nên có

- Timeout policy đúng đơn vị và range.
- Connection đã bị đóng nếu driver nhận diện network timeout theo hợp đồng.
- Không phát truy vấn mới trên connection bị marked closed.
- Lỗi driver unsupported được xử lý.
- Shared executor vẫn active suốt quãng dùng connections.
- Owner shutdown pool/executor theo thứ tự và deadline.
- Query timeout và network timeout được cấu hình độc lập.
- Transaction retry có idempotency/reconciliation policy.

## 19. Monitoring khi vận hành

Các metrics hữu ích:

- Số network timeout events/SQLException phân loại theo SQLState/vendor code.
- Query timeout events/SQLTimeoutException.
- Connection pool active/idle/pending acquisition counts.
- Thời gian checkout, execution, result streaming, commit và close.
- Tỷ lệ connections bị marked broken/evicted/recreated.
- Số callbacks được executor nhận, active threads, queue size và rejection count (nếu đo được).
- Thread dumps cho blocked JDBC calls.
- TCP/network fault metrics và database server logs.
- Transaction ambiguous outcomes và retry/duplicate counts.
- Shutdown/drain duration khi deploy.
- Tỷ lệ DataSource/driver hỗ trợ network timeout thật sự.

### 19.1. Không log mật khẩu/connection string chứa secret

Khi ghi log SQLException, có thể lưu SQLState, vendor code, operation name, timeout policy, connection ID đã ẩn danh và correlation ID. Không ghi JDBC URL có password hoặc SQL literal chứa dữ liệu nhạy cảm vào log.

### 19.2. Đừng chỉ nhìn một exception class

Một sự cố network có thể xuất hiện với nhiều subclass của `SQLException`, phụ thuộc driver và nguyên nhân. `SQLTimeoutException` không phải dấu hiệu duy nhất của network timeout và cũng không luôn báo connection closed. Dùng SQLState, vendor code, connection health, pool diagnostics và driver docs để phân loại.

### 19.3. Tại sao cần theo dõi executor rejection?

Nếu executor đã shutdown hoặc queue quá tải, tasks được gửi tới có thể bị reject. Đây có thể là triệu chứng lifecycle/sizing sai. Không tự suy JDBC driver chắc chắn log lỗi theo một format cố định; thiết kế monitoring quanh executor owned và tích hợp vendor.

## 20. Những lỗi phổ biến

**1. “setNetworkTimeout(…,15) nghĩa 15 giây.”** Sai; 15 mili-giây.

**2. “setQueryTimeout(15) nghĩa 15 mili-giây.”** Sai; 15 giây.

**3. “Network timeout bảo đảm toàn bộ HTTP request không vượt thời hạn.”** Sai; nó điều khiển chờ database reply theo driver.

**4. “Network timeout hoàn toàn giống query timeout.”** Sai; network timeout có thể đóng connection.

**5. “Nếu query timeout hết hạn, connection luôn bị đóng.”** Không phải mặc định JDBC contract; còn phụ thuộc trạng thái mạng/driver/transaction.

**6. “Nếu network timeout hết hạn, cứ retry trên cùng connection.”** Sai; connection bị marked closed theo contract.

**7. “setNetworkTimeout tự làm query chạy async.”** Sai; executor là công cụ driver có thể dùng cho hỗ trợ timeout/cleanup.

**8. “Executor là SQL query worker pool của Connection.”** Sai; không có bảo đảm mọi SQL chạy ở đó.

**9. “Một request được shutdown shared executor sau khi SQL xong.”** Sai; borrower không có quyền đóng.

**10. “Mỗi query phải tạo newSingleThreadExecutor.”** Không; thường tạo overhead/rò rỉ và khó quản lý lifetime.

**11. “ExecutorService Java 17 dùng try-with-resources được.”** Sai; Java 17 không implements AutoCloseable.

**12. “Connection.close sẽ tự shutdown executor đã truyền vào setter.”** Không có hợp đồng như vậy.

**13. “Connection.abort trả về thì chắc không còn task cleanup nào.”** Sai; Javadoc cho phép executor còn chạy.

**14. “Runnable::run chắc chắn tạo worker độc lập.”** Sai; nó thực thi inline trên thread gọi.

**15. “Có thể pass null cho executor để driver tự chọn.”** Không theo API chuẩn; null không hợp lệ.

**16. “Một executor dùng chung nghĩa mọi Connection có cùng network timeout.”** Sai; timeout là cấu hình trên connection.

**17. “Một setter có thể thay đổi timeout của request JDBC đã đang chờ.”** Không; API nói không ảnh hưởng outstanding requests.

**18. “Timeout 0 nghĩa fail ngay.”** Sai; 0 là không đặt ngưỡng network timeout.

**19. “Mọi JDBC driver có setNetworkTimeout vì interface có method.”** Sai; driver có thể không hỗ trợ.

**20. “Bắt SQLFeatureNotSupportedException rồi bỏ qua vẫn là bảo vệ network.”** Không; thiếu cấu hình bảo vệ cần có fallback/fail-fast rõ.

**21. “Thời gian network timeout luôn chính xác ở ms.”** Sai; driver có thể làm tròn lên theo giây.

**22. “JDBC method luôn chỉ gửi đúng một network request.”** Sai; driver có thể chia thành nhiều transmissions.

**23. “getNetworkTimeout luôn trả đúng value của setter dù có pool/driver wrapper.”** Không thể hứa không xét implementation; đọc/kiểm tra runtime.

**24. “Pool close ngay thì executor có thể dừng trước mọi cleanup.”** Không luôn đúng; xét dependencies.

**25. “Dừng executor là tương đương đóng Connection.”** Sai; hai tài nguyên khác nhau.

**26. “Đặt network timeout trên Connection giải quyết chờ pool acquisition.”** Sai; lúc đó chưa có Connection.

**27. “Future.get(timeout) hủy socket read trong JDBC.”** Không; nó chỉ giới hạn thời gian caller đợi Future.

**28. “Future.cancel(true) bảo đảm driver không còn thực hiện SQL.”** Không; interrupt hỗ trợ tùy driver.

**29. “Network timeout tự rollback mọi transaction.”** Sai; outcome của write/commit có thể chưa rõ.

**30. “Timeout thì retry INSERT ngay chắc chắn không trùng.”** Sai; cần idempotency/reconciliation.

**31. “Không cần close ResultSet/PreparedStatement nếu có network timeout.”** Sai; try-with-resources vẫn quan trọng.

**32. “Mượn executor nên nhận ExecutorService và gọi shutdown cho sạch.”** Sai; nhận Executor khi chỉ cần execute.

**33. “Để executor chung bị tắc bởi blocking SQL không ảnh hưởng callbacks.”** Có thể gây starvation; cần sizing/isolation phù hợp.

**34. “Một mock Connection chứng minh lỗi mạng thật được xử lý.”** Sai; unit test chỉ kiểm tra wiring/lifecycle.

**35. “Mọi connection pool reset setNetworkTimeout giống nhau.”** Không; đọc tài liệu pool và thử đúng version.

**36. “Đặt timeout quá thấp luôn cải thiện reliability.”** Sai; có thể gây liên tục đóng kết nối hợp lệ.

**37. “Chuyển Duration.toMillis thành int không cần kiểm tra overflow.”** Sai; cast có thể thay đổi giá trị.

**38. “Query timeout bằng giây nhưng network timeout cũng giây.”** Sai; hai đơn vị khác nhau.

**39. “setNetworkTimeout làm DB server dừng tính SQL ngay.”** Không; JDBC client network timeout không là chứng nhận server đã hủy/rollback.

**40. “Mọi SQLTimeoutException báo đúng cùng loại nguyên nhân.”** Không; phải quan sát thêm context/driver SQLState.

## 21. Checklist triển khai thực tế

- [ ] Đã xác định cần protection khỏi network partitions/socket reads treo?
- [ ] JDBC driver thực tế có hỗ trợ `Connection.setNetworkTimeout` không?
- [ ] Đã xác minh trên đúng driver version và connection pool version?
- [ ] Timeout dùng đơn vị **milliseconds**, không nhầm với queryTimeout seconds?
- [ ] Network timeout đủ cao so với các timeout thông thường theo policy?
- [ ] Nếu có transaction timeout, đã so thứ tự ưu tiên và ngân sách tổng?
- [ ] Nếu có HTTP deadline, đã phân biệt deadline end-to-end với per-request network timeout?
- [ ] Có xử lý timeout 0 như “disable” chứ không phải 0ms?
- [ ] Giá trị âm bị từ chối?
- [ ] Nếu cấu hình dùng Duration, có kiểm tra range int millis/overflow?
- [ ] Không giả định thời gian timeout chính xác từng millisecond?
- [ ] Không giả định timeout setter ảnh hưởng outstanding requests?
- [ ] Không mặc định network timeout có thể áp cả những trường hợp chưa có connection?
- [ ] Executor không null và phù hợp driver?
- [ ] Executor có khả năng thực hiện công việc độc lập với blocked JDBC thread?
- [ ] Executor không bị request/borrower shutdown?
- [ ] Đã xác định rõ owner của ExecutorService là app/service/pool?
- [ ] Không new executor mỗi query nếu không có lý do/lifecycle rõ?
- [ ] Không shutdown executor ngay sau setNetworkTimeout?
- [ ] Không dựa vào commonPool rồi cố shutdown pool dùng chung?
- [ ] Executor không bị starvation bởi các blocking operations khác?
- [ ] Owner có lifecycle stop admission, drain/cancel, close resources và shutdown/await?
- [ ] Trong Java 17 dùng shutdown/finally thay vì try-with-resources cho ExecutorService?
- [ ] Connection và ResultSet/PreparedStatement có try-with-resources?
- [ ] Nếu dùng pool, đã biết policy reset network timeout khi return lease?
- [ ] Không share cùng một Connection qua threads trái driver contract?
- [ ] Nếu query timeout, kiểm tra transaction/connection state thay vì reuse mù?
- [ ] Nếu network timeout, loại connection closed và lấy connection mới?
- [ ] Không retry write/commit khi chưa rõ outcome và chưa có idempotency?
- [ ] Có xử lý `SQLFeatureNotSupportedException` rõ ràng?
- [ ] Nếu fallback sang driver socket timeout, đã kiểm tra vendor docs?
- [ ] Có test actual network faults và không chỉ mock?
- [ ] Có test query chậm nhưng network vẫn hoạt động?
- [ ] Có test pool recovery/connection eviction?
- [ ] Có monitoring timeout rates, executor rejection, thread counts và pool health?
- [ ] Có phân biệt log SQLState/vendor code và bảo vệ credentials?
- [ ] API Java 17+ còn hiện hành, không dùng giả định legacy?

## 22. Câu hỏi tự kiểm tra

**1.** `Connection.setNetworkTimeout` nhận các tham số nào? — `Executor` và `int milliseconds`.

**2.** Đơn vị network timeout? — Mili-giây.

**3.** Đơn vị Statement.setQueryTimeout? — Giây.

**4.** Giá trị network timeout 0 có nghĩa gì? — Không đặt giới hạn network timeout JDBC đó.

**5.** Nếu milliseconds âm thì sao? — SQLException theo JDBC contract.

**6.** Nếu executor null? — SQLException theo JDBC contract.

**7.** Driver không hỗ trợ network timeout có thể ném gì? — SQLFeatureNotSupportedException.

**8.** Cần set query timeout và network timeout ở đâu? — Query timeout ở Statement, network timeout ở Connection.

**9.** Khi network timeout thật sự hết hạn, Connection ra sao? — Bị đánh dấu closed và không nên reuse.

**10.** Query timeout có buộc close Connection không? — Không mặc định nếu network vẫn hoạt động và driver xử lý cancel; kiểm tra tình trạng thực tế.

**11.** setNetworkTimeout có thay đổi JDBC requests đã outstanding không? — Không.

**12.** Driver có thể làm tròn thời gian timeout không? — Có, nếu không hỗ trợ millisecond resolution.

**13.** setNetworkTimeout có đồng nghĩa timeout cả HTTP request? — Không.

**14.** Executor có chạy mọi SQL statements không? — Không có hợp đồng như vậy.

**15.** Có nên dùng `Runnable::run` làm executor mặc định cho network timeout không? — Không nên nếu cần tính độc lập của callbacks; xem driver requirements.

**16.** Một ExecutorService có thể cấp cho hai Connections không? — Có nếu owner thiết kế/sizing đúng.

**17.** Ai được shutdown executor? — Thành phần **sở hữu** nó, không phải mọi borrower.

**18.** Tại sao không tạo executor mỗi query? — Overhead, rò tài nguyên, khó bảo đảm lifetime.

**19.** Java 17 ExecutorService có AutoCloseable không? — Không.

**20.** Dừng executor ngay sau setter có rủi ro gì? — Driver có thể còn cần executor cho công việc sau.

**21.** abort(Executor) có thể trả về trước khi cleanup hoàn tất không? — Có.

**22.** Connection.close() có shutdown executor không? — Không theo hợp đồng JDBC.

**23.** DataSource.setLoginTimeout dùng đơn vị nào? — Giây.

**24.** Pool acquisition timeout thuộc API nào? — Theo connection pool, không phải Connection.setNetworkTimeout.

**25.** Future.get(timeout) có chắc hủy JDBC I/O không? — Không, chỉ giới hạn thời gian đợi Future.

**26.** Network timeout xảy ra sau COMMIT request thì có chắc DB chưa commit không? — Không, có thể chưa rõ outcome.

**27.** Có nên retry write tự động khi outcome chưa rõ? — Chỉ theo chính sách idempotency/reconciliation.

**28.** Bắt SQLFeatureNotSupportedException và bỏ qua có rủi ro gì? — Policy safety có thể không được thực thi.

**29.** Mock dynamic proxy chứng minh điều gì? — API wiring, ownership và response giả lập; không chứng minh network fault thực.

**30.** Tại sao cần integration test với driver/database thật? — Timeout/cancel/pool recovery phụ thuộc implementation và mạng.

**31.** Vì sao cần metrics executor queue/rejection? — Detect shutdown sớm, saturation và lifecycle lỗi.

**32.** Giá trị 15 trong setNetworkTimeout là bao nhiêu giây? — 0,015 giây.

**33.** Giá trị 15_000 trong setNetworkTimeout là bao nhiêu giây? — 15 giây.

**34.** Query timeout 5 giây và network timeout 15 giây thể hiện ý đồ gì? — Query cancellation thường có cơ hội xảy ra trước network guard nghiêm trọng.

**35.** Vì sao không reset timeout về 0 vô điều kiện khi trả pooled Connection? — Pool có thể có baseline policy khác.

## 23. Tài liệu chính thức — Java SE 17

- [Connection — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): `setNetworkTimeout`/`getNetworkTimeout`, ngữ nghĩa closed connection, `abort(Executor)`, outstanding requests, driver support và timeout ordering.
- [Statement — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html): `setQueryTimeout(int seconds)`, `SQLTimeoutException` và `cancel()`.
- [PreparedStatement — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): sử dụng câu SQL có tham số và close resources.
- [DataSource — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/javax/sql/DataSource.html): quản lý kết nối, `setLoginTimeout` và pooling.
- [Executor — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): hợp đồng `execute(Runnable)`.
- [ExecutorService — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown()`, `shutdownNow()`, `awaitTermination()` và quản lý owner.
- [SQLException — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html): lỗi JDBC và SQLState/vendor code.
- [SQLFeatureNotSupportedException — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): API không được driver hỗ trợ.
- [SQLTimeoutException — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLTimeoutException.html): timeout theo JDBC.
- [Duration — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): biểu diễn duration và chuyển đổi đơn vị.

**Ghi nhớ:** `Connection.setNetworkTimeout(executor, milliseconds)` là ngưỡng **mili-giây** bảo vệ JDBC khi database không phản hồi; timeout này có thể **đóng Connection**, khác `Statement.setQueryTimeout(seconds)`. Executor được truyền vào là **tài nguyên có owner**, không được một request/borrower tự shutdown; nên có lifecycle sống đủ lâu để driver hoàn thành công việc. Connection/ResultSet/Statement vẫn phải được đóng theo ownership riêng; với pool phải xét policy reset state và recovery. `abort(Executor)` có thể trả về trước khi công việc cleanup hoàn tất. Kiểm tra driver có hỗ trợ API, phân biệt timeout types, không reuse connection đã closed và không retry database writes khi outcome chưa rõ. Unit test với mock chỉ kiểm tra wiring; hãy kiểm thử actual network faults với driver/database thật trước khi khẳng định khả năng bảo vệ production.