# Đóng stream, socket, connection và tài nguyên khi task thất bại

Khi một task thực hiện blocking I/O, tài nguyên như stream, socket, channel hoặc database connection phải được đóng ngay cả khi task ném exception, bị timeout hoặc bị hủy. Trong Java 21, cách mặc định nên dùng là *try-with-resources* với `AutoCloseable`/`Closeable`, kết hợp quy tắc sở hữu tài nguyên rõ ràng. Khi task kết thúc do lỗi, cơ chế try-with-resources gọi `close()` cho các tài nguyên đã mở thành công; nếu việc đóng cũng thất bại, exception đóng được giữ lại dưới dạng suppressed exception.

Virtual thread không thay thế quy tắc quản lý tài nguyên. Nó giúp phục vụ nhiều task đang chờ I/O, nhưng mỗi task vẫn phải giải phóng socket, stream, connection và các tài nguyên bên ngoài. Một ứng dụng tạo được nhiều virtual thread nhưng không đóng tài nguyên đúng cách vẫn có thể cạn connection pool, file descriptor hoặc socket.

## 1. Xác định ai sở hữu tài nguyên

Trước khi viết `close()`, cần xác định thành phần nào có trách nhiệm kết thúc vòng đời tài nguyên. Quy tắc đơn giản là: nơi tạo hoặc nhận quyền sở hữu tài nguyên sẽ chịu trách nhiệm đóng nó; nơi chỉ mượn tài nguyên không tự ý đóng nếu hợp đồng API không chuyển quyền sở hữu.

| Tình huống | Trách nhiệm đóng |
|---|---|
| Method mở file stream và dùng nội bộ | Method đóng stream trước khi kết thúc |
| Task tự tạo socket để gọi dịch vụ | Task đóng socket trong mọi đường thoát |
| Method nhận stream do caller truyền vào và chỉ đọc một phần | Caller thường vẫn sở hữu stream; method không đóng trừ khi hợp đồng nói rõ |
| Method trả về một stream mới cho caller | Quyền sở hữu được chuyển cho caller; caller phải đóng |
| Framework quản lý transaction/connection | Để framework đóng theo vòng đời transaction; không đóng resource mượn từ framework |
| Lấy JDBC connection từ `DataSource` | Code gọi `getConnection()` đóng connection bằng try-with-resources; với pool, `close()` thường trả connection về pool |

Quyền sở hữu cần được thể hiện trong API và tài liệu method. Tránh để hai thành phần cùng nghĩ rằng mình là chủ sở hữu, vì đóng sớm có thể làm task khác mất kết nối. Cũng tránh để không có thành phần nào chịu trách nhiệm đóng, vì tài nguyên sẽ bị rò rỉ khi task thất bại.

## 2. Dùng try-with-resources thay cho close thủ công

Một resource có thể dùng trong try-with-resources nếu triển khai `AutoCloseable`. `Closeable` mở rộng `AutoCloseable` và được dùng cho nhiều tài nguyên I/O.

```java
static String readFirstLine(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path, UTF_8)) {
        return reader.readLine();
    }
}
```

Khi method trả về bình thường, `reader.close()` được gọi. Nếu `readLine()` ném `IOException`, `close()` vẫn được gọi trước khi exception được truyền ra ngoài. Nếu `close()` cũng ném exception, exception đọc vẫn là exception chính và exception đóng được gắn vào danh sách suppressed.

Khi mở nhiều resource, khai báo chúng trong cùng try-with-resources:

```java
static void copy(Path source, Path target) throws IOException {
    try (InputStream input = Files.newInputStream(source);
         OutputStream output = Files.newOutputStream(target)) {
        input.transferTo(output);
    }
}
```

Các resource được đóng theo thứ tự ngược với thứ tự khai báo: `output` đóng trước, sau đó `input`. Nếu khởi tạo resource thứ hai thất bại, resource thứ nhất đã mở vẫn được đóng. Đây là lý do nên khai báo resource trong header thay vì mở từng resource rồi tự ghép nhiều khối `finally`.

Với một biến resource đã được khởi tạo trước đó và không thay đổi, Java cũng cho phép dùng biến đó trong try-with-resources:

```java
InputStream input = Files.newInputStream(path);

try (input) {
    return input.readAllBytes();
}
```

Sau khối này, `input` đã đóng và không nên tiếp tục sử dụng. Trong code mới, khai báo resource ngay trong header thường làm rõ phạm vi sở hữu hơn.

## 3. Exception chính và suppressed exception

Try-with-resources phân biệt exception từ thân `try` với exception phát sinh trong lúc đóng tài nguyên:

- Nếu thân `try` thất bại, exception đó được ném ra; lỗi từ `close()` được thêm vào `getSuppressed()`.
- Nếu thân `try` thành công nhưng `close()` thất bại, exception đóng được ném ra.
- Nếu có nhiều resource cùng lỗi khi đóng, các exception đóng được lưu theo thứ tự đóng.

Ví dụ quan sát suppressed exception:

```java
try (InputStream input = openInput()) {
    process(input); // Có thể ném IOException
} catch (IOException failure) {
    System.err.println("Lỗi chính: " + failure);

    for (Throwable suppressed : failure.getSuppressed()) {
        System.err.println("Lỗi khi đóng resource: " + suppressed);
    }

    throw failure;
}
```

Không nên bỏ qua exception từ `close()` một cách tùy tiện. Ví dụ, nếu ghi file thất bại rồi việc flush/close cũng thất bại, lỗi đóng có thể cung cấp thông tin quan trọng về dữ liệu chưa được ghi hoàn chỉnh. Khi log exception, hãy log cả stack trace của exception chính; logger thông thường sẽ hiển thị suppressed exception cùng stack trace đó.

Không cần tự gọi `close()` trong `finally` khi đã dùng try-with-resources. Việc đóng thủ công trong cả thân `try` lẫn `finally` có thể tạo đóng lặp, che mất exception gốc hoặc khiến code khó xác định resource nào còn hợp lệ.

## 4. Đóng stream và wrapper đúng cách

Các wrapper như `BufferedInputStream`, `BufferedReader`, `InputStreamReader` và `DataInputStream` thường sở hữu stream được truyền vào constructor. Đóng wrapper sẽ gọi đóng stream nền.

```java
static String readText(Path path) throws IOException {
    try (InputStream input = Files.newInputStream(path);
         Reader decoder = new InputStreamReader(input, UTF_8);
         BufferedReader reader = new BufferedReader(decoder)) {
        return reader.lines().collect(Collectors.joining("\n"));
    }
}
```

Trong ví dụ, các resource được đóng theo thứ tự `reader`, `decoder`, `input`. Việc đóng wrapper sẽ đóng resource nền; những lần đóng tiếp theo là đóng lặp trên cùng chuỗi tài nguyên. Mẫu này thể hiện rõ vòng đời từng wrapper, nhưng trong code thực tế có thể khai báo wrapper ngoài cùng làm resource chính nếu nó là chủ sở hữu của toàn bộ chuỗi.

```java
static String readText(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path, UTF_8)) {
        return reader.lines().collect(Collectors.joining("\n"));
    }
}
```

Tránh đóng một stream mà task khác vẫn đang sử dụng. Nếu nhiều task cùng đọc một resource, cần thiết kế quyền sở hữu và đồng bộ hóa rõ ràng; không dùng một `close()` ở task này để giải phóng tài nguyên mà task khác vẫn coi là hợp lệ.

## 5. Đóng socket khi giao tiếp thất bại

Socket thường cần được đóng khi kết nối thất bại, đọc/ghi lỗi, timeout hoặc task bị hủy. Đóng `Socket` sẽ đóng kết nối và các stream liên quan; các thao tác I/O đang chờ trên socket có thể được đánh thức bằng exception.

```java
static String request(String host, int port, String message) throws IOException {
    try (Socket socket = new Socket()) {
        socket.connect(new InetSocketAddress(host, port), 3_000);
        socket.setSoTimeout(5_000);

        BufferedReader reader = new BufferedReader(
                new InputStreamReader(socket.getInputStream(), UTF_8));
        BufferedWriter writer = new BufferedWriter(
                new OutputStreamWriter(socket.getOutputStream(), UTF_8));

        writer.write(message);
        writer.newLine();
        writer.flush();

        return reader.readLine();
    }
}
```

Socket được khai báo làm resource sở hữu. Khi `connect`, ghi hoặc đọc ném exception, khối try vẫn đóng socket. Việc đóng socket cũng đóng các stream và giải phóng socket descriptor. `setSoTimeout` giới hạn thời gian chờ đọc; nó không phải timeout cho mọi thao tác như DNS lookup hoặc thời gian thiết lập kết nối, nên `connect` nhận timeout riêng.

Nếu dùng `SocketChannel`, `ServerSocketChannel` hoặc `DatagramChannel`, các channel này triển khai `Channel`/`AutoCloseable` và nên được đóng bằng try-with-resources. Đối với `InterruptibleChannel`, interrupt thread đang chờ thao tác I/O có thể đóng channel và làm thao tác kết thúc bằng `ClosedByInterruptException`.

Không nên bắt `IOException` rồi tiếp tục dùng socket như thể kết nối vẫn còn tốt. Sau lỗi I/O, trạng thái giao thức và trạng thái kết nối có thể không còn đồng bộ; đóng socket và tạo kết nối mới thường an toàn hơn nếu nghiệp vụ cho phép retry.

## 6. JDBC Connection, Statement và ResultSet

Với JDBC, `Connection`, `Statement` và `ResultSet` đều có thể được dùng trong try-with-resources. Nên đóng `ResultSet` và `Statement` trong phạm vi nhỏ nhất có thể; đóng connection sau cùng.

```java
static List<String> findNames(DataSource dataSource) throws SQLException {
    String sql = "select name from customer where active = ?";
    List<String> names = new ArrayList<>();

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setBoolean(1, true);

        try (ResultSet resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                names.add(resultSet.getString("name"));
            }
        }
    }

    return names;
}
```

Khi `ResultSet` hoặc câu lệnh thất bại, các resource đã mở vẫn được đóng. Khi lấy connection từ pool, `connection.close()` thường trả connection về pool thay vì đóng socket vật lý ngay lập tức. Đây vẫn là thao tác bắt buộc để pool tái sử dụng connection và giải phóng lease cho task khác.

Nếu connection do framework quản lý transaction cung cấp, không tự đóng nó ở một method con. Hãy tuân theo hợp đồng của framework; đóng một connection đang được transaction manager quản lý có thể phá vỡ transaction hoặc làm task khác mất resource.

### Rollback khi transaction thất bại

Try-with-resources đảm bảo connection được đóng, nhưng đóng connection không thay thế quyết định rollback nghiệp vụ. Với transaction tường minh, rollback khi công việc hoặc commit thất bại:

```java
static void transfer(DataSource dataSource,
                     long fromId, long toId, BigDecimal amount)
        throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            debit(connection, fromId, amount);
            credit(connection, toId, amount);
            connection.commit();
        } catch (SQLException | RuntimeException | Error failure) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }

            throw failure;
        }
    }
}
```

Nếu rollback thất bại, lỗi rollback được thêm vào exception gốc để không che mất nguyên nhân ban đầu. Sau đó try-with-resources đóng connection. Nếu `close()` tiếp tục thất bại, Java tự thêm exception đóng vào danh sách suppressed của exception đang được ném ra.

Ví dụ trên minh họa transaction do method sở hữu. Trong ứng dụng dùng transaction manager hoặc framework như Spring, nên để framework quản lý commit/rollback và vòng đời connection thay vì tự trộn hai cơ chế.

## 7. Task bị lỗi, timeout hoặc bị hủy

Một task có thể kết thúc vì:

- Thân task ném exception.
- Một thao tác I/O timeout.
- Caller gọi `Future.cancel(true)` để yêu cầu interrupt task đang chạy.
- Executor bị dừng hoặc ứng dụng shutdown.

Nếu resource được mở trong task bằng try-with-resources, khi luồng điều khiển thoát khỏi khối `try` do exception hoặc interruption, resource sẽ được đóng. Tuy nhiên, việc gửi interrupt không đảm bảo mọi API I/O hoặc thư viện bên ngoài đều lập tức kết thúc. Task và API đang dùng phải có hợp đồng hủy phù hợp.

Ví dụ với virtual thread thực hiện socket I/O:

```java
static String readFromServer(String host, int port)
        throws IOException {
    try (Socket socket = new Socket()) {
        socket.connect(new InetSocketAddress(host, port), 3_000);
        socket.setSoTimeout(10_000);

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(socket.getInputStream(), UTF_8))) {
            return reader.readLine();
        }
    }
}

static String loadWithTimeout(String host, int port)
        throws InterruptedException, ExecutionException, TimeoutException {

    try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
        Future<String> result = executor.submit(() -> readFromServer(host, port));

        try {
            return result.get(5, TimeUnit.SECONDS);
        } catch (TimeoutException timeout) {
            result.cancel(true);
            throw timeout;
        }
    }
}
```

Trong Java 21, virtual thread bị interrupt khi đang block trong socket I/O của `java.net` sẽ được đánh thức và socket liên quan bị đóng; task thoát khỏi thao tác đọc và try-with-resources hoàn tất việc dọn dẹp. Đây là hành vi hỗ trợ của socket API với virtual thread, không phải lời hứa rằng mọi `InputStream` hoặc thư viện I/O tùy ý đều có thể bị hủy bằng interrupt.

Với `SocketChannel` và các `InterruptibleChannel`, interrupt cũng có thể đóng channel đang chờ và làm thao tác kết thúc. Với API không interruptible, cần dùng timeout của chính API hoặc thiết kế đường hủy có quyền đóng resource từ bên ngoài. Việc đóng socket/channel từ task khác chỉ an toàn khi task đó có quyền sở hữu hoặc có handle hủy được thiết kế rõ ràng.

`Future.cancel(true)` chỉ gửi yêu cầu hủy bằng interrupt; nó không chứng minh task đã kết thúc và resource đã đóng tại thời điểm lời gọi trả về. Nếu cần bảo đảm cleanup hoàn tất trước khi tiếp tục, hãy có tín hiệu hoàn tất riêng hoặc chờ task thực sự kết thúc. Không giữ một resource dùng chung rồi đóng nó từ caller nếu task khác vẫn đang sở hữu.

`ExecutorService.close()` thực hiện shutdown có trật tự và chờ các task hoàn tất; nó không tự đóng socket hoặc stream mà task đang sở hữu và cũng không thay thế yêu cầu cancellation. Nếu task bị kẹt trong một API không phản ứng với interrupt, việc đóng executor có thể phải chờ lâu. Vì vậy, timeout và đường giải phóng resource phải được thiết kế ở cấp task/I/O, không chỉ ở cấp executor.

## 8. Không nuốt InterruptedException

Nhiều thao tác blocking ném `InterruptedException` để báo task nên dừng. Khi bắt exception này, thường cần truyền nó lên caller hoặc khôi phục interrupt status nếu không thể truyền tiếp:

```java
static void waitForWork() {
    try {
        Thread.sleep(1_000);
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        return;
    }
}
```

Không nên bắt rồi bỏ qua `InterruptedException` và tiếp tục chạy như chưa có gì. Nếu interrupt bị nuốt, cơ chế hủy task có thể mất hiệu lực và resource tiếp tục bị giữ lâu hơn dự kiến. Try-with-resources vẫn đóng tài nguyên khi method thoát; nhưng nếu code bắt interrupt rồi không thoát, resource sẽ tiếp tục mở.

## 9. Đặt timeout ở đúng tầng

Một timeout tổng thể cho request không tự động giới hạn mọi thao tác con. Cần đặt timeout phù hợp tại từng API và có deadline tổng:

| Tài nguyên/thao tác | Cách giới hạn thường dùng |
|---|---|
| Thiết lập TCP connection | `Socket.connect(address, timeout)` |
| Đọc từ `Socket` | `Socket.setSoTimeout(timeout)` |
| HTTP request | `HttpRequest.Builder.timeout(Duration)` |
| Chờ kết quả task | `Future.get(timeout, unit)` |
| JDBC query | `Statement.setQueryTimeout(seconds)`; hiệu lực cụ thể phụ thuộc driver |
| Chờ lấy connection từ pool | Cấu hình acquisition timeout của connection pool |
| Chờ lock hoặc semaphore | Các API `tryLock(timeout, unit)` / `tryAcquire(timeout, unit)` |

Timeout ở caller không nhất thiết dừng thao tác bên dưới. Ví dụ, `Future.get(timeout)` ném `TimeoutException` khi hết thời gian chờ, nhưng task vẫn chạy nếu caller không yêu cầu hủy. Nếu hủy bằng interrupt, task vẫn cần sử dụng API có thể phản ứng với interrupt hoặc có đường đóng resource phù hợp.

Với JDBC, `Statement.setQueryTimeout` là yêu cầu tới driver; cần kiểm tra hành vi của driver và database. Không mặc định rằng cancel statement sẽ lập tức rollback transaction hoặc đóng connection. Ứng dụng vẫn phải xử lý rollback và đóng resource theo quyền sở hữu.

## 10. Các lỗi quản lý tài nguyên thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Mở stream/socket rồi return hoặc throw trước khi close | Rò rỉ file descriptor/socket | Khai báo resource trong try-with-resources |
| Chỉ đóng resource ở nhánh thành công | Task thất bại để lại resource mở | Dùng một phạm vi sở hữu bao trùm mọi đường thoát |
| Đóng connection do framework quản lý | Transaction hoặc task khác bị ảnh hưởng | Tuân theo hợp đồng ownership của framework |
| Bắt exception rồi bỏ qua lỗi close | Mất thông tin ghi/flush/cleanup thất bại | Giữ exception chính và log suppressed exception |
| Chỉ gọi `Future.cancel(true)` rồi giả định task đã dừng | Resource có thể vẫn mở nếu task/API không phản ứng với interrupt | Dùng timeout, API interruptible và tín hiệu xác nhận cleanup |
| Dùng timeout ở caller nhưng không hủy task | Task tiếp tục chạy và giữ resource | Thiết kế deadline, cancellation và cleanup ở task |
| Không rollback transaction khi thao tác thất bại | Dữ liệu có thể ở trạng thái không như mong muốn | Rollback tường minh hoặc để transaction manager xử lý |
| Dùng một stream/socket chung cho nhiều task mà không có ownership rõ | Một task có thể đóng resource của task khác | Mỗi task sở hữu resource riêng hoặc dùng cơ chế chia sẻ được thiết kế rõ |

## 11. Quy trình kiểm tra khi task thất bại

Khi điều tra rò rỉ tài nguyên hoặc lỗi đóng sau một task thất bại, thực hiện theo thứ tự:

1. Xác định task nào mở resource và thành phần nào chịu trách nhiệm đóng.
2. Kiểm tra mọi đường thoát: return bình thường, exception, timeout, interrupt và cancellation.
3. Đưa resource vào try-with-resources càng gần điểm tạo càng tốt.
4. Kiểm tra resource wrapper có đóng resource nền hay không để tránh đóng sớm hoặc bỏ sót.
5. Kiểm tra exception chính và `getSuppressed()` để phát hiện lỗi khi đóng.
6. Với socket/channel, xác minh API có phản ứng với interrupt hay cần close/timeout riêng.
7. Với JDBC, xác minh statement/result set/connection được đóng và transaction được commit/rollback đúng hợp đồng.
8. Theo dõi số connection đang mượn, số socket/file descriptor, timeout và thời gian task kết thúc trong môi trường tải thực tế.

## 12. Nguyên tắc áp dụng

- Dùng try-with-resources cho mọi tài nguyên có vòng đời hữu hạn và triển khai `AutoCloseable`.
- Đóng resource ở đúng nơi sở hữu; không đóng resource được mượn nếu hợp đồng không chuyển ownership.
- Đặt resource trong phạm vi nhỏ nhất có thể và đóng theo thứ tự ngược với thứ tự mở.
- Không bỏ qua suppressed exception; chúng có thể chỉ ra lỗi flush hoặc cleanup quan trọng.
- Đối với socket và channel, kết hợp try-with-resources, timeout và cancellation phù hợp với API.
- Với task dùng virtual thread, không mặc định mọi I/O đều interruptible; kiểm tra hành vi cụ thể của API.
- Với JDBC, đóng connection trả về pool và rollback transaction khi thất bại theo đúng chủ sở hữu transaction.
- Không coi `Future.cancel(true)` là bằng chứng cleanup đã hoàn tất.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 21 — The try-with-resources Statement](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html)
- [Java SE 21 API — AutoCloseable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html)
- [Java SE 21 API — Socket](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html)
- [Java SE 21 API — InterruptibleChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/InterruptibleChannel.html)
- [Java SE 21 API — Connection](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html)
- [Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
