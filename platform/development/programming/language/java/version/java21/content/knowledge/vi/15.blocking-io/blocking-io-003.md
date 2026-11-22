# Thiết kế xử lý request theo phong cách tuần tự với blocking API

Java 21 cho phép viết một request handler theo luồng tuần tự quen thuộc: đọc dữ liệu, truy vấn database, gọi dịch vụ HTTP, xử lý kết quả rồi trả response. Mỗi request có thể chạy trên một virtual thread riêng, vì vậy lời gọi blocking vẫn giữ được cách viết tuần tự mà không cần dành một platform thread cho toàn bộ thời gian chờ.

Mô hình này thường được gọi là *thread-per-request*. Nó giúp code dễ đọc, dễ gỡ lỗi và sử dụng trực tiếp các API đồng bộ như JDBC hoặc HTTP Client. Virtual thread làm cho việc có nhiều request cùng chờ I/O trở nên khả thi hơn; nó không làm cho database, API bên ngoài, CPU hoặc bộ nhớ trở nên vô hạn.

## 1. Luồng tuần tự bên trong một request

Một request thường có các bước phụ thuộc nhau:

1. Kiểm tra dữ liệu đầu vào và xác thực.
2. Đọc hoặc ghi dữ liệu trong database.
3. Gọi dịch vụ bên ngoài dựa trên kết quả database.
4. Kết hợp dữ liệu và tạo response.

Với blocking API, mỗi bước có thể gọi trực tiếp bước tiếp theo. Khi một lời gọi chờ I/O, virtual thread có thể unmount khỏi carrier nếu thao tác đó được runtime hỗ trợ. Carrier được giải phóng để chạy virtual thread khác.

~~~text
Request A                         Request B
    |                                 |
    v                                 v
Validate                          Validate
    |                                 |
    v                                 v
Query database                    Query database
    |                                 |
    |---- blocking / waiting          |---- running
    |                                 |
    |                                 v
    |                            Call HTTP service
    |                                 |
    |                                 |---- blocking / waiting
    |                                 |
    v                                 v
Call HTTP service                Build response
    |
    |---- blocking / waiting
    |
    v
Build response
    |
    v
Complete

        Virtual threads được lập lịch trên
             một nhóm carrier threads
~~~

Hai request có thể tiến triển độc lập. Khi Request A chờ database hoặc HTTP, carrier có thể thực thi Request B. Nhưng các bước bên trong cùng Request A vẫn chạy tuần tự nếu code gọi chúng tuần tự.

Virtual thread không tự biến một chuỗi lời gọi đồng bộ thành các phép tính song song. Nếu hai lời gọi HTTP độc lập và muốn chạy đồng thời, ứng dụng phải chủ động thiết kế fan-out/concurrency cho hai lời gọi đó.

## 2. Gắn một virtual thread với mỗi request

Java 21 hỗ trợ virtual thread như một tính năng chính thức. Có thể tạo một executor tạo virtual thread cho mỗi task:

~~~java
ExecutorService requestExecutor =
    Executors.newVirtualThreadPerTaskExecutor();
~~~

Nếu web server hoặc framework cho phép cấu hình executor, có thể dùng executor này làm nơi chạy request handler. Ví dụ với JDK HttpServer:

~~~java
HttpServer server = HttpServer.create(
    new InetSocketAddress(8080),
    0
);

ExecutorService requestExecutor =
    Executors.newVirtualThreadPerTaskExecutor();

server.setExecutor(requestExecutor);
server.createContext("/users", exchange -> {
    // Handler chạy trên virtual thread do executor tạo.
    handleUserRequest(exchange);
});

server.start();
~~~

Executor tạo một virtual thread mới cho mỗi task được giao. Nó không phải pool gồm một số virtual thread cố định để tái sử dụng. Khi ứng dụng dừng server, cần dừng nhận request và đóng executor theo vòng đời của ứng dụng.

Trong ứng dụng dùng framework web, hãy dùng cơ chế cấu hình request executor hoặc virtual-thread support mà framework và phiên bản đang dùng cung cấp. Không cần tự tạo một thread thủ công ở mọi tầng service; request đã chạy trên virtual thread thì các lời gọi đồng bộ bên dưới tiếp tục chạy trên cùng virtual thread cho tới khi nó kết thúc hoặc bị tạm dừng.

Có thể kiểm tra thread hiện tại trong lúc chẩn đoán:

~~~java
if (Thread.currentThread().isVirtual()) {
    logger.debug("Request đang chạy trên virtual thread");
}
~~~

Không nên dùng kiểm tra này để rẽ nhánh logic nghiệp vụ. Code xử lý request nên có cùng ngữ nghĩa dù được gọi từ virtual thread hay platform thread, trừ khi có yêu cầu vận hành cụ thể.

## 3. Viết service bằng blocking API theo thứ tự nghiệp vụ

Ví dụ dưới đây đọc thông tin người dùng bằng JDBC, đóng tài nguyên database rồi mới gọi một dịch vụ HTTP. Các lời gọi đều là blocking API, nhưng code vẫn tuần tự và dễ theo dõi.

~~~java
static String handleRequest(
        long userId,
        DataSource dataSource,
        HttpClient httpClient,
        URI profileServiceUri)
        throws SQLException, IOException, InterruptedException {

    String userName;

    // Bước 1: truy vấn database.
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(
             "select name from users where id = ?")) {

        statement.setLong(1, userId);
        statement.setQueryTimeout(3);

        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                throw new NoSuchElementException(
                    "Không tìm thấy người dùng: " + userId
                );
            }

            userName = result.getString("name");
        }
    }

    // Connection và statement đã được đóng trước khi gọi HTTP.

    // Bước 2: gọi dịch vụ profile.
    HttpRequest request = HttpRequest.newBuilder(profileServiceUri)
        .timeout(Duration.ofSeconds(2))
        .GET()
        .build();

    HttpResponse<String> response = httpClient.send(
        request,
        HttpResponse.BodyHandlers.ofString()
    );

    if (response.statusCode() != 200) {
        throw new IOException(
            "Profile service trả HTTP " + response.statusCode()
        );
    }

    // Bước 3: kết hợp dữ liệu và tạo kết quả.
    return userName + " | " + response.body();
}
~~~

Một số chi tiết đáng chú ý:

- JDBC vẫn được gọi đồng bộ qua DataSource, Connection, PreparedStatement và ResultSet.
- HTTP Client dùng phương thức send, phương thức này chờ response trước khi trả về.
- try-with-resources bảo đảm tài nguyên JDBC được đóng khi thành công hoặc khi exception xảy ra.
- Connection database được đóng trước lời gọi HTTP. Nhờ vậy request không giữ connection trong suốt thời gian chờ dịch vụ ngoài.
- Thứ tự xử lý thể hiện trực tiếp quan hệ phụ thuộc: cần có user trước khi tạo kết quả cuối.

Tạo HttpClient dùng chung cho ứng dụng thay vì tạo client mới cho từng request:

~~~java
static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(1))
    .build();
~~~

HttpClient có thể được dùng lại cho nhiều request. Còn connection JDBC nên được lấy từ DataSource/connection pool và trả về pool sau khi hoàn tất giao dịch ngắn.

## 4. Blocking không đồng nghĩa với chiếm carrier trong toàn bộ thời gian chờ

Khi một platform thread gọi API blocking, OS thread thường vẫn bị giữ trong lúc chờ. Với virtual thread, nhiều thao tác blocking của JDK được triển khai để virtual thread unmount khỏi carrier trong khi chờ.

Ví dụ thường gặp là socket I/O, một số thao tác đồng bộ trong các API networking, chờ trên các synchronizer của Java và các cấu trúc như BlockingQueue. Khi thao tác hoàn tất, virtual thread được scheduler đưa trở lại để tiếp tục trên một carrier.

Điều này không có nghĩa mọi lời gọi blocking trong mọi thư viện đều chắc chắn unmount. Cần xét cách thư viện và driver thực hiện I/O:

- HTTP Client của JDK tích hợp với runtime và phù hợp để sử dụng từ virtual thread.
- JDBC là một API đồng bộ; mức độ thân thiện với virtual thread còn phụ thuộc driver, cách driver thực hiện socket/native I/O và connection pool.
- Thư viện gọi native method hoặc foreign function có thể giữ virtual thread trên carrier trong lúc thực thi.
- Một lời gọi blocking có thể chờ trên tài nguyên bên ngoài dù carrier đã được giải phóng; virtual thread và dữ liệu request vẫn còn sống.

Với thư viện quan trọng trong hệ thống, hãy thử nghiệm trên đúng phiên bản driver và JDK, đo số virtual thread bị pin và kiểm tra khả năng phục hồi khi tải cao.

## 5. Đặt timeout cho từng ranh giới I/O

Virtual thread giúp quản lý nhiều request đang chờ, nhưng nó không tự đặt deadline cho các lời gọi blocking. Mỗi ranh giới I/O cần timeout phù hợp để request không chờ vô hạn.

| Ranh giới | Cơ chế cần cấu hình |
|---|---|
| Kết nối HTTP | Connect timeout của HttpClient |
| Một HTTP request | Timeout của HttpRequest |
| Lấy connection từ pool | Connection acquisition timeout do pool cung cấp |
| Truy vấn JDBC | Query timeout của Statement và timeout mạng phù hợp với driver |
| Toàn bộ request | Deadline/request timeout ở tầng server hoặc ứng dụng |

Ví dụ với HTTP Client:

~~~java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(1))
    .build();

HttpRequest request = HttpRequest.newBuilder(uri)
    .timeout(Duration.ofSeconds(3))
    .GET()
    .build();

HttpResponse<String> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofString()
);
~~~

Connect timeout giới hạn thời gian thiết lập kết nối; request timeout giới hạn thời gian chờ cho request. Đây là hai phạm vi khác nhau.

Với JDBC, có thể dùng query timeout:

~~~java
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setQueryTimeout(3);
    // bind parameters và thực thi query
}
~~~

Query timeout có hành vi chi tiết phụ thuộc JDBC driver và database. Hãy kiểm tra tài liệu driver, đặc biệt nếu cần timeout cho việc lấy connection, socket read hoặc hủy câu lệnh. Không nên giả định Thread.interrupt() sẽ hủy mọi truy vấn JDBC một cách tức thời.

Timeout từng bước nên nằm trong ngân sách deadline tổng thể của request. Nếu request chỉ còn 500 ms, không nên bắt đầu một lời gọi downstream với timeout 5 giây.

## 6. Giới hạn tài nguyên mà request sử dụng

Virtual thread cho phép có nhiều request chờ cùng lúc, nhưng không tăng số connection database hoặc khả năng xử lý của API bên ngoài.

Ví dụ, nếu connection pool chỉ có 30 connection, request thứ 31 có thể phải chờ connection. Nếu mỗi request giữ một connection trong khi gọi tiếp dịch vụ HTTP, pool sẽ bị chiếm lâu hơn cần thiết và các request khác phải chờ.

Thiết kế tốt nên:

- Chỉ lấy connection khi cần truy cập database.
- Giữ transaction ngắn và đóng/trả connection sớm.
- Không giữ connection database trong lúc gọi dịch vụ HTTP độc lập.
- Đặt giới hạn connection và timeout chờ connection ở pool.
- Đặt rate limit hoặc semaphore cho dịch vụ downstream nếu cần bảo vệ giới hạn của dịch vụ đó.

Có thể dùng Semaphore để giới hạn số lời gọi đồng thời đến một dịch vụ bên ngoài:

~~~java
private static final Semaphore API_LIMIT = new Semaphore(25);

static Result callService(Request request)
        throws InterruptedException {
    API_LIMIT.acquire();
    try {
        return blockingApiCall(request);
    } finally {
        API_LIMIT.release();
    }
}
~~~

Nếu thao tác chờ semaphore unmount virtual thread, carrier được giải phóng trong lúc chờ. Tuy nhiên, mỗi request đang đợi permit vẫn là một virtual thread còn sống và có thể giữ request body, context hoặc dữ liệu khác.

Semaphore bên trong handler giới hạn số lời gọi đang chạy, nhưng không giới hạn tổng số request đã được nhận và chuyển thành virtual thread. Nếu lượng request đến vượt quá khả năng hệ thống trong thời gian dài, cần thêm admission control/backpressure ở tầng tiếp nhận: hàng đợi có giới hạn, giới hạn số request đang xử lý, từ chối sớm hoặc phản hồi quá tải.

Không tạo một virtual thread pool để giới hạn số request. Hãy tách hai việc: virtual thread biểu diễn mỗi tác vụ; cơ chế admission control và giới hạn tài nguyên quyết định hệ thống nhận bao nhiêu tác vụ cùng lúc.

## 7. Xử lý exception và interruption

Code tuần tự giúp exception đi theo call stack tự nhiên. Một lỗi JDBC có thể là SQLException; lỗi HTTP có thể là IOException; lời gọi blocking có thể bị ngắt và ném InterruptedException.

Không nên bắt mọi exception rồi trả về một response thành công giả. Hãy phân loại lỗi theo ranh giới:

- Lỗi đầu vào hoặc không tìm thấy dữ liệu: trả response nghiệp vụ tương ứng.
- Timeout hoặc lỗi dịch vụ downstream: ánh xạ sang lỗi tạm thời hoặc gateway timeout theo hợp đồng API.
- Lỗi không mong đợi: ghi log kèm request/correlation ID và chuyển tới error handler chung.
- Interruption: giữ đúng tín hiệu hủy tác vụ.

Nếu phải bắt InterruptedException mà không thể truyền tiếp, hãy khôi phục interrupt status:

~~~java
try {
    return client.send(request, HttpResponse.BodyHandlers.ofString());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new CancellationException("Request bị hủy");
}
~~~

Nếu method có thể khai báo throws InterruptedException, thường nên truyền exception lên tầng gọi để tầng đó quyết định việc hủy và phản hồi. Tránh nuốt exception hoặc tiếp tục xử lý như thể request vẫn còn hợp lệ.

Future.cancel(true) yêu cầu task bị interrupt, nhưng việc lời gọi blocking thực sự dừng nhanh hay không còn phụ thuộc API, driver và thư viện. Vì thế timeout ở API, database và tầng request vẫn cần được cấu hình riêng.

## 8. Không giữ monitor trong lúc chờ I/O trên Java 21

Trên Java 21 đến Java 23, virtual thread có thể bị pin vào carrier nếu nó thực hiện blocking operation trong khi đang giữ intrinsic monitor, ví dụ bên trong một vùng synchronized. Khi đó carrier không được giải phóng trong thời gian chờ và khả năng mở rộng có thể giảm.

Ví dụ cần tránh:

~~~java
synchronized (lock) {
    // Gọi mạng hoặc database trong khi vẫn giữ monitor.
    callBlockingService();
}
~~~

Hãy thu hẹp vùng đồng bộ để chỉ bảo vệ trạng thái dùng chung:

~~~java
RequestData snapshot;

synchronized (lock) {
    snapshot = copyRequiredState();
}

// I/O thực hiện ngoài monitor.
callBlockingService(snapshot);
~~~

Nếu cần đồng bộ hóa trong khi một tác vụ có thể chờ, có thể xem xét ReentrantLock và thiết kế vùng khóa ngắn, nhưng chỉ thay khóa khi ngữ nghĩa đồng bộ và yêu cầu bảo vệ dữ liệu cho phép. Không cần thay tất cả synchronized trong ứng dụng.

Từ Java 24, JEP 491 thay đổi cách virtual thread tương tác với monitor để blocking bên trong synchronized không còn gây monitor-related pinning như Java 21–23. Native method và foreign function vẫn có thể pin virtual thread. Khi ứng dụng triển khai trên JDK khác Java 21, hãy kiểm tra hành vi theo đúng phiên bản runtime.

## 9. Khi nào nên dùng phong cách tuần tự?

Phong cách tuần tự với blocking API phù hợp khi:

- Các bước trong một request phụ thuộc kết quả của bước trước.
- Thư viện đang dùng cung cấp API đồng bộ ổn định, ví dụ JDBC.
- Muốn dùng try-with-resources, exception handling và call stack thông thường.
- Nhiều request có thể chờ I/O độc lập với nhau.
- Đội ngũ cần code dễ đọc và dễ gỡ lỗi theo luồng nghiệp vụ.

Nó không tự tạo lợi thế khi tác vụ chủ yếu là CPU-bound. Nếu một request cần chạy nhiều phép tính nặng, số carrier/CPU vẫn là giới hạn. Nếu nhiều lời gọi độc lập trong cùng request có thể chạy song song để giảm latency, hãy thiết kế concurrency có chủ đích thay vì giả định virtual thread tự song song hóa các lệnh tuần tự.

## 10. Checklist cho request handler dùng blocking API

- [ ] Mỗi request chạy trên một virtual thread nếu workload và server/framework hỗ trợ mô hình này.
- [ ] Dùng API blocking trực tiếp theo thứ tự nghiệp vụ.
- [ ] Tạo và tái sử dụng HttpClient; dùng DataSource/connection pool cho JDBC.
- [ ] Đóng connection và statement sớm, không giữ database connection qua lời gọi HTTP không liên quan.
- [ ] Đặt connect timeout, request timeout, query timeout và deadline tổng thể.
- [ ] Giới hạn tài nguyên downstream bằng connection pool, semaphore hoặc rate limiter.
- [ ] Có admission control/backpressure để giới hạn tổng request đang sống.
- [ ] Xử lý exception theo đúng loại lỗi và không nuốt interruption.
- [ ] Trên Java 21–23, tránh blocking I/O khi đang giữ intrinsic monitor.
- [ ] Đo heap, số virtual thread đang sống, thời gian chờ, connection pool và sự kiện pinning dưới tải thực tế.

## Tài liệu tham khảo chính thức

- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
- [Java SE 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java SE 21 API — HttpClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 21 API — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Java SE 21 API — Statement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html)
- [Java SE 21 API — DataSource](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/javax/sql/DataSource.html)
- [Java SE 21 API — Semaphore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)

