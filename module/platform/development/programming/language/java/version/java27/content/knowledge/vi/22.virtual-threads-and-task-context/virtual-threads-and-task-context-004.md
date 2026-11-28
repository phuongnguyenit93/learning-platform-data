# Giới hạn tài nguyên ngoài bằng semaphore và connection pool

**Virtual threads** giúp ứng dụng Java xử lý nhiều tác vụ đồng thời đang chờ I/O mà không cần cấp riêng một platform thread cho mỗi tác vụ trong suốt vòng đời. Tuy nhiên, chi phí tạo virtual thread thấp **không làm tăng** số kết nối cơ sở dữ liệu, khả năng phục vụ của HTTP API hay giới hạn giao dịch của dịch vụ bên ngoài.

Giả sử hệ thống có 20.000 yêu cầu đang xử lý, nhưng database chỉ được cấp 16 connections và API thanh toán chỉ chịu được 8 lời gọi đồng thời. Nếu cứ cho mọi yêu cầu truy cập ngay, virtual threads có thể khiến ứng dụng **tạo áp lực lên tài nguyên ngoài nhanh hơn**, chứ không làm tài nguyên ngoài mạnh hơn.

Hai cơ chế thực tế cần phân biệt:

- **`Semaphore`** giới hạn số thao tác **đồng thời được vào một đoạn code cụ thể**, ví dụ tối đa 8 lời gọi tới API thanh toán.
- **Connection pool** tái sử dụng một số lượng **kết nối thực** hữu hạn, ví dụ tối đa 16 database connections; khi pool hết connections, tác vụ mượn thêm phải chờ hoặc thất bại theo chính sách pool.

Bài học thuộc chương **Virtual threads và ngữ cảnh tác vụ**, module **JAVA_VERSION_JAVA27 – Java 27 và các kiến thức liên quan**. Nội dung sử dụng các API hiện hành trong Java SE 27: `Thread.ofVirtual`, `Executors.newVirtualThreadPerTaskExecutor`, `Semaphore`, `DataSource`, JDBC và `try-with-resources`. Không dùng việc pool virtual threads hoặc một fixed thread pool làm giải pháp mặc định để giới hạn tài nguyên ngoài.

## 1. Ba giới hạn khác nhau thường bị nhầm lẫn

| Đại lượng | Trả lời câu hỏi | Cơ chế kiểm soát |
| --- | --- | --- |
| **Tác vụ đang tồn tại** | Có bao nhiêu requests, virtual threads đang chạy/chờ? | Admission control, deadline, hàng đợi hữu hạn |
| **Thao tác đang dùng tài nguyên** | Có bao nhiêu lời gọi đang cùng truy cập dịch vụ ngoài? | `Semaphore` hoặc concurrency limit tương đương |
| **Kết nối được cấp** | Có tối đa bao nhiêu database sessions hoặc connections? | Connection pool và giới hạn từ server |

**Giới hạn concurrency khác giới hạn số tác vụ chờ.** Nếu semaphore có 8 permits và 100.000 virtual threads gọi `acquire()`, tối đa 8 được vào vùng bảo vệ cùng lúc, nhưng phần còn lại **vẫn có thể chờ**, tiêu tốn bộ nhớ và thời gian sống của request.

Sơ đồ:

```text
             Request ingress
                   |
          [Admission/deadline]
                   |
             Virtual threads
                   |
          +--------+--------+
          |                 |
          v                 v
   [Semaphore: 8]     [DB pool: 16]
          |                 |
          v                 v
   API thanh toán        Database

    Giới hạn số         Giới hạn số
    lời gọi active      connections đang mượn
```

Đây là **hai tài nguyên khác nhau**. Không nên đặt mọi thao tác của một request dưới cùng một semaphore nếu các downstream có khả năng chịu tải riêng.

## 2. Vì sao không pool virtual threads?

Với platform threads, `Executors.newFixedThreadPool(8)` thường được dùng để tạo hiệu ứng “cùng lúc chỉ có 8 tác vụ”. Nhưng mục đích chính của thread pool là **tái sử dụng những threads tương đối đắt đỏ**, không phải mô tả sức chứa của database hay một API.

Virtual threads được thiết kế cho mô hình **một virtual thread trên một tác vụ**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

try (ExecutorService executor =
        Executors.newVirtualThreadPerTaskExecutor()) {
    executor.submit(() -> handleRequest());
}
```

`handleRequest()` là method giả định của ứng dụng. `newVirtualThreadPerTaskExecutor()` tạo **virtual thread mới cho mỗi tác vụ**, không tạo một pool threads tái sử dụng. Nó cũng **không tự giới hạn** tổng số tasks được submit.

Muốn giới hạn chỉ lời gọi đến API A, hãy dùng semaphore tại **ranh giới gọi API A**, thay vì giữ một fixed thread pool cho toàn bộ request. Một request không cần API A không phải chờ permit của API A.

Virtual threads cũng **không giúp phép tính CPU-bound chạy nhanh hơn**; lợi thế chính là khả năng mở rộng những tác vụ thường chờ I/O.

## 3. Cơ chế `Semaphore`: acquire và release

`java.util.concurrent.Semaphore` là **counting semaphore**, quản lý một số permits trừu tượng.

```java
import java.util.concurrent.Semaphore;

Semaphore apiLimit = new Semaphore(8);
```

Với 8 permits:

1. `acquire()` lấy một permit. Nếu hết permits, thread chờ đến khi có permit hoặc bị interrupt.
2. `release()` trả một permit, có thể đánh thức tác vụ đang chờ.
3. Khi mỗi lần acquire thành công có đúng một lần release, **không quá 8** tác vụ cùng giữ permit.
4. Semaphore không sở hữu HTTP request hay connection nào: nó chỉ kiểm soát quyền đi vào đoạn code.

```text
Semaphore(3)
    |
    +-- Task A: acquire --> đang gọi dịch vụ
    +-- Task B: acquire --> đang gọi dịch vụ
    +-- Task C: acquire --> đang gọi dịch vụ
    |
    +-- Task D: đang chờ
    +-- Task E: đang chờ
                |
           A release()
                |
                v
           Một tác vụ được tiếp tục
```

| API | Ý nghĩa |
| --- | --- |
| `new Semaphore(n)` | `n` permits ban đầu; mặc định **non-fair** |
| `new Semaphore(n, true)` | Bật chính sách **fair** khi chờ |
| `acquire()` | Chờ interruptibly đến khi có một permit |
| `tryAcquire()` | Thử ngay; trả `false` nếu chưa có |
| `tryAcquire(timeout, unit)` | Chờ tối đa khoảng thời gian chỉ định; có thể bị interrupt |
| `release()` | Trả một permit |
| `availablePermits()` | Ảnh chụp số permits còn lại, không phải số đo bất biến |
| `getQueueLength()` | Ước lượng số threads đang chờ |

Có các overload `acquire(int)`/`release(int)` cho nhiều permits, nhưng lời gọi dịch vụ ngoài thông thường nên sử dụng **một permit cho một lần gọi**. Chỉ dùng nhiều permits nếu một operation thực sự tiêu thụ số lượng resource units tương ứng.

## 4. Mẫu an toàn: acquire trước, release trong `finally`

Giả sử API thanh toán chỉ chịu tối đa 8 lời gọi đồng thời:

```java
import java.util.concurrent.Semaphore;

final class PaymentGateway {
    private final Semaphore permits = new Semaphore(8);

    String charge(String paymentId) throws InterruptedException {
        permits.acquire(); // Chỉ đi tiếp sau khi có permit.
        try {
            return callExternalPaymentApi(paymentId);
        } finally {
            permits.release();
        }
    }

    private String callExternalPaymentApi(String paymentId) {
        // Placeholder cho HTTP client thật.
        return "charged:" + paymentId;
    }
}
```

Đây chỉ là mô hình **giới hạn concurrency**, không phải payment integration production: giao dịch thật còn cần xác thực, idempotency key, timeout mạng và chính sách kiểm tra kết quả với nhà cung cấp.

Vì sao đặt `acquire()` **trước** `try/finally`?

```java
gate.acquire();
try {
    callService();
} finally {
    gate.release();
}
```

Nếu thread bị interrupt **khi đang đợi** `acquire()`, lệnh này ném `InterruptedException` mà **chưa lấy được permit**. Vì chưa vào `try`, không có `release()` sai.

Không viết:

```java
// Sai: release có thể chạy dù acquire chưa thành công.
try {
    gate.acquire();
    callService();
} finally {
    gate.release();
}
```

`Semaphore` không theo dõi owner của permit và **không tự ngăn release thừa**. Mã release thừa có thể làm số permits vượt giới hạn ban đầu. Không dùng `availablePermits()` để đoán lần gọi hiện tại đã được cấp permit chưa; hãy thiết kế luồng điều khiển rõ ràng.

### 4.1. Khoanh đúng đoạn cần bảo vệ

```java
String payload = validateAndSerialize(input); // Chưa dùng API.

apiLimit.acquire();
String response;
try {
    response = sendToPartner(payload); // Chỉ giới hạn lời gọi này.
} finally {
    apiLimit.release();
}

return parseResponse(response); // Đã trả permit.
```

Các method là giả định của ứng dụng. Không giữ permit trong lúc serialization, formatting hay tính toán không sử dụng resource ngoài. Nếu cần cả database, tránh giữ permit API khi query DB trừ khi có hợp đồng giới hạn bao trùm rõ ràng.

## 5. Timeout chờ permit và admission control

`acquire()` có thể chờ lâu nếu downstream chậm hoặc treo. Một virtual thread bị block có chi phí thấp, **không phải bằng không**, và deadline của request vẫn phải được tôn trọng.

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

static String callLimitedApi(Semaphore limit, String requestId)
        throws InterruptedException {

    boolean admitted =
            limit.tryAcquire(200, TimeUnit.MILLISECONDS);
    if (!admitted) {
        throw new IllegalStateException(
                "Service is busy; try again later");
    }

    try {
        return invokePartner(requestId);
    } finally {
        limit.release();
    }
}
```

`invokePartner` là method ứng dụng giả định. Nếu quá hạn chờ, **không gọi downstream** và **không release**; nếu lấy được permit, luôn release; nếu bị interrupt khi chờ, không có permit cần trả.

**Timeout chờ permit không phải timeout I/O.** Tác vụ có thể chờ 200 ms để lấy permit rồi kẹt 30 giây trong HTTP call nếu client không có deadline riêng.

```text
Deadline tổng của request
     |
     +-- Chờ admission/permit: timeout
     +-- Gọi HTTP/DB: connect/read/query timeout
     +-- Xử lý kết quả: vẫn nằm trong deadline tổng
```

### 5.1. `tryAcquire()` để fail-fast

```java
if (!limit.tryAcquire()) {
    return "busy"; // Chỉ là quy ước minh họa.
}
try {
    return invokePartner(requestId);
} finally {
    limit.release();
}
```

Fail-fast hữu ích khi request không được phép chờ. Nhưng có thể từ chối ngay cả khi permit trở lại sau vài mili giây; chọn theo SLO chứ không mặc định cách nào đúng cho mọi dịch vụ.

### 5.2. Giới hạn tác vụ chờ là lớp khác

Semaphore chỉ giới hạn **active calls**, không giới hạn số virtual threads đang chờ. Với lượng đầu vào cực lớn, cần thêm:

1. **Admission control** ở ingress: nhận hoặc từ chối có kiểm soát.
2. **Bounded queue** hay giới hạn số requests đang sống, với chính sách khi đầy.
3. **Timeout/deadline** cho permit và I/O; không giữ công việc đã quá hạn.
4. **Cancellation** cho những tác vụ không còn người chờ; downstream client cũng phải hợp tác với việc hủy.

Không coi virtual threads rẻ là lý do cho **hàng đợi vô hạn**.

## 6. Interruption và cancellation

`Semaphore.acquire()` và `tryAcquire(timeout, unit)` là các thao tác **interruptible**; khi bị interrupt, chúng ném `InterruptedException`. Nếu method khai báo `throws InterruptedException`, có thể truyền thẳng lỗi lên caller:

```java
static void doWork(Semaphore semaphore)
        throws InterruptedException {
    semaphore.acquire();
    try {
        runExternalOperation();
    } finally {
        semaphore.release();
    }
}
```

Nếu bắt `InterruptedException` để chuyển thành exception khác, nên khôi phục interrupted status:

```java
try {
    semaphore.acquire();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Task was interrupted", ex);
}
```

Đây chỉ là phần xử lý interrupt; sau khi acquire thành công, vẫn phải có `try/finally` bảo đảm release. Không catch rồi bỏ qua và tiếp tục gọi downstream.

Với `ExecutorService`, `Future.cancel(true)` yêu cầu interrupt thread đang chạy tác vụ. Nếu virtual thread đang chờ permit, tác vụ có thể dừng chờ sớm. **Interrupt không phải cưỡng chế giết task**: JDBC driver hoặc HTTP client cụ thể có thể cần timeout/cơ chế hủy riêng. Tránh `acquireUninterruptibly()` trong request cần deadline/cancellation trừ khi đã chấp nhận lý do kỹ thuật đặc biệt.

## 7. Fairness của `Semaphore`

`new Semaphore(permits, true)` bật chính sách **fair**. Khi cạnh tranh, các lời gọi `acquire()` được chọn theo thứ tự chúng đến **điểm xếp hàng nội bộ**, không nhất thiết theo thứ tự xuất hiện trong log.

```java
Semaphore fairGate = new Semaphore(8, true);
Semaphore nonFairGate = new Semaphore(8); // Mặc định.
```

| Chế độ | Ưu điểm | Điều cần nhớ |
| --- | --- | --- |
| Fair | Giảm nguy cơ tác vụ đến sau vượt người đang chờ | Có thể giảm throughput; FIFO tại điểm đồng bộ nội bộ |
| Non-fair | Có thể tăng throughput trong một số workload | Cho phép barging, không hứa thứ tự FIFO |

**Ngoại lệ:** `tryAcquire()` **không timeout** có thể lấy permit ngay cả khi `fair=true` và đã có thread chờ. Nếu cần thử không chờ nhưng vẫn tôn trọng fairness, Javadoc gợi ý `tryAcquire(0, TimeUnit.SECONDS)` (cũng kiểm tra interruption).

Fairness không thay thế một chính sách ưu tiên theo deadline, khách hàng hay workload class; nếu các lớp requests cần SLO khác nhau, cần admission/queue policy phù hợp.

## 8. Concurrency limit khác rate limit

Một semaphore 8 permits có thể cho phép nhiều hơn 100 calls/giây nếu mỗi lời gọi hoàn thành rất nhanh. Nó chỉ đảm bảo **tối đa 8 active calls**, không đảm bảo quota “100 calls/phút”.

| Loại giới hạn | Ví dụ | Cơ chế đúng |
| --- | --- | --- |
| Concurrent in-flight | Tối đa 8 HTTP calls đang chạy | `Semaphore(8)` |
| Quota theo thời gian | Tối đa 100 requests/phút | Rate limiter/token bucket |
| Kết nối vật lý | Tối đa 16 database sessions | Connection pool |
| Tổng tải nhận vào | Tối đa 500 requests trong hệ thống | Admission control, bounded queue, deadline |

Trong sản phẩm thật có thể cần **đồng thời concurrency limit và rate limit**; hai cơ chế không thay thế nhau.

Ví dụ lý tưởng: mỗi lời gọi giữ permit 100 ms và cho phép 8 thao tác cùng lúc, thì thông lượng lý thuyết bão hòa có thể xấp xỉ 80 thao tác/giây, **không phải cam kết**. Latency biến động, timeout, retry, overhead và năng lực phía server làm con số thực tế khác đi.

## 9. Connection pool và `DataSource`

`javax.sql.DataSource` là giao diện JDBC chuẩn để lấy `java.sql.Connection`. Một triển khai `DataSource` có thể là:

- **Basic data source:** tạo connection thông thường, **không bảo đảm có pooling**.
- **Pooled data source:** làm việc với connection pool manager để mượn/trả logical connection handles từ tập physical connections.
- Data source tích hợp transaction management theo cấu hình riêng.

**JDK không tự cung cấp một connection pool quản lý chung chỉ vì code có kiểu `DataSource`.** Cần một implementation/pool manager được cấu hình thực sự, từ framework, application server hoặc thư viện/driver. Java SE 27 cung cấp các hợp đồng `DataSource`, `ConnectionPoolDataSource`, `PooledConnection` và `Connection`.

```text
Task A ----- getConnection() ---+
Task B ----- getConnection() ---+--> Pool [max=3] --> DB
Task C ----- getConnection() ---+
Task D ----- getConnection() ------> Chờ/timeout theo pool

Task B ----- connection.close() ---> Trả logical handle để tái sử dụng
```

Mã ứng dụng thông thường gọi `DataSource.getConnection()` để nhận **Connection handle**. Với pooled implementation, `Connection.close()` trả handle cho pool; physical connection thường tiếp tục tồn tại để tái sử dụng. Với basic data source không pool, `close()` có thể đóng physical connection.

`PooledConnection` là giao diện của **tầng quản lý pool/driver**, không phải đối tượng mà business code nên mượn và quản lý trực tiếp.

### 9.1. Pool đã đóng vai trò semaphore cho connections

Nếu pool tối đa 16 connections và mỗi task cần mượn một connection, **tối đa 16 tasks** có thể cùng giữ connections từ pool ấy. Task thứ 17 thường chờ hoặc timeout theo cấu hình.

Vì vậy, tài liệu Java 27 nhấn mạnh **connection pool tự nó đã có tác dụng như một semaphore**. Không mặc định thêm `Semaphore(16)` trước `dataSource.getConnection()`: điều đó thường tạo hai lớp xếp hàng/timeout mà không tăng khả năng bảo vệ database.

## 10. Luôn trả connection bằng `try-with-resources`

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

record Customer(long id, String name) {}

static Optional<Customer> findCustomer(
        DataSource dataSource, long customerId) throws SQLException {

    String sql = "SELECT name FROM customers WHERE id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
                 connection.prepareStatement(sql)) {

        statement.setLong(1, customerId);
        try (ResultSet results = statement.executeQuery()) {
            if (results.next()) {
                return Optional.of(
                        new Customer(customerId, results.getString(1)));
            }
            return Optional.empty();
        }
    }
}
```

Ví dụ giả định có bảng `customers(id, name)` và `DataSource` đã cấu hình, nên **không phải chương trình standalone** nếu thiếu database/driver.

Quy trình: mượn connection khi thực sự cần, dùng `PreparedStatement` với tham số thay vì ghép SQL từ input, đọc `ResultSet` trong scope ngắn và dùng `try-with-resources` để đóng đúng thứ tự kể cả khi `return` hoặc ném exception. Với pooled implementation, `Connection.close()` **trả handle** để request khác có thể mượn.

### 10.1. Giữ connection scope càng ngắn càng tốt — nhưng đúng transaction

Anti-pattern khi không cần giữ cùng DB transaction:

```java
try (Connection connection = dataSource.getConnection()) {
    Customer customer = readCustomer(connection, customerId);
    String quote = callPartnerApi(customer); // Chờ mạng lâu!
    persistQuote(connection, quote);
}
```

Nếu việc gọi đối tác không cần nằm trong một transaction DB đang mở, nên tách:

```java
Customer customer = readCustomerInShortConnection(dataSource, customerId);
String quote = callPartnerApi(customer);
writeQuoteInShortConnection(dataSource, quote);
```

Đây là minh họa, các methods cần được xây dựng trong hệ thống thực tế. **Không chia transaction một cách máy móc:** nếu nghiệp vụ yêu cầu tính nhất quán, phải thiết kế transaction boundary/isolation/commit/rollback phù hợp; đừng giả định `Connection.close()` mặc nhiên thay thế rollback trong transaction chưa hoàn tất.

### 10.2. Không chia sẻ một `Connection` cho nhiều virtual threads

Không lưu một `Connection` trong biến static để mọi request gọi đồng thời. Connection chứa session/transaction state, nhiều drivers không bảo đảm thao tác concurrent trên cùng handle. Hãy để mỗi task mượn connection qua pool và trả khi xong. Không tự tạo `ThreadLocal<Connection>` cho mỗi virtual thread — virtual threads không được pool/tái sử dụng giữa các requests, nên cách đó còn dễ làm tăng số tài nguyên giữ lâu.

## 11. Khi nào semaphore bổ sung cho connection pool?

**Thông thường không cần** nếu mục tiêu duy nhất là “không quá 16 tasks cùng giữ database connection” và pool đã giới hạn 16. Chỉ thêm semaphore khi nó bảo vệ một **ràng buộc khác**:

| Tình huống | Chọn cách nào? |
| --- | --- |
| Pool giới hạn 16 connections, chỉ cần giới hạn connections được mượn | **Dùng pool**, không thêm semaphore cùng mức |
| API thanh toán giới hạn 8 requests đồng thời, không có pool tương ứng | Dùng **semaphore riêng** quanh HTTP call |
| Truy vấn báo cáo đặc biệt chỉ cho 3 tác vụ nặng dù pool có 16 connections | Có thể dùng **semaphore 3** cho loại query nặng |
| Có nhiều replicas cùng truy cập database | Tính **tổng pool sizes**; semaphore local không tự là global |
| Cần quota 100 requests/phút | Dùng **rate limiter**, không chỉ semaphore |

Ví dụ một nhóm báo cáo nặng:

```java
static void generateHeavyReport(
        Semaphore heavyReportLimit, DataSource dataSource)
        throws InterruptedException, SQLException {

    heavyReportLimit.acquire();
    try {
        try (Connection connection = dataSource.getConnection()) {
            runHeavyQuery(connection);
        }
    } finally {
        heavyReportLimit.release();
    }
}
```

`runHeavyQuery` là method giả định. Trong ví dụ, semaphore bảo vệ **ngân sách query nặng**, còn pool bảo vệ **ngân sách connection**. Tuy nhiên, nếu pool hết connections, ba permits báo cáo có thể bị giữ bởi những tasks **chỉ đang đợi pool**. Hãy đo chờ ở cả hai tầng, dùng timeout nếu cần và xem xét sắp xếp lại admission nếu gây nghẽn.

Nếu một đường xử lý giữ tài nguyên `A` rồi chờ `B`, còn đường khác giữ `B` rồi chờ `A`, hệ thống có nguy cơ **deadlock**. Ưu tiên không giữ nhiều tài nguyên cùng lúc; khi bắt buộc, xác định thứ tự cấp phát nhất quán và deadline phù hợp.

### 11.1. Local semaphore không tự giới hạn toàn cụm

Một semaphore `new Semaphore(8)` trong mỗi instance chỉ giới hạn **8 concurrent calls từ instance đó**. Nếu chạy 4 instances, hệ thống có thể có tối đa **32 concurrent calls** đến cùng downstream (chưa tính các ứng dụng khác).

Nếu đối tác đặt giới hạn **toàn bộ tài khoản** là 8 calls, một semaphore local trên mỗi replica **không đủ**. Cần điều phối global/distributed phù hợp, hoặc phân bổ budgets tĩnh/động giữa các replicas và áp dụng kiểm soát phía upstream. Không nhầm giới hạn JVM-local với quota toàn hệ thống.

## 12. Sizing connection pool: theo database, không theo số virtual threads

Không có công thức “mỗi virtual thread cần một connection” hoặc “pool size nên bằng số cores”. Kích thước pool phụ thuộc:

- Giới hạn database sessions/connections, kể cả các services khác dùng chung.
- Số application instances/replicas và số pools mỗi instance.
- Thời gian thực sự **giữ connection**, gồm query, transaction, chờ lock; không nên bao gồm HTTP chờ bên ngoài nếu không cần.
- Thời gian truy vấn, IO/CPU DB, tình trạng index, locking và transaction scopes.
- Mức tải peak, SLO về chờ mượn connection và ngưỡng bảo vệ DB.

Ví dụ giả định:

```text
4 application instances
  mỗi instance có pool tối đa 8 connections
             |
             v
 4 x 8 = tối đa 32 connections
         từ các pool đó
```

Không thể coi 32 là mức an toàn nếu DB còn cần connections cho operations, migration, worker jobs và services khác. `max pool size` là **trần cấu hình**, không phải cam kết lúc nào cũng có đúng số connections vật lý đó.

### 12.1. Little's Law là chỉ dẫn để đo, không phải công thức cấu hình duy nhất

Ở trạng thái ổn định, số lượng thao tác đồng thời trung bình của một giai đoạn xấp xỉ:

\[
L = \lambda W
\]

Trong đó `L` là số thao tác đồng thời trung bình, `λ` là thông lượng (thao tác/giây), `W` là thời gian trung bình trong giai đoạn (giây).

Ví dụ giả định ứng dụng hoàn thành 100 queries/giây, mỗi query **giữ connection** trung bình 0,05 giây. Mức connections bận trung bình của giai đoạn đó xấp xỉ `100 × 0,05 = 5`. Đây **không** phải lời khuyên cấu hình pool đúng bằng 5: cần tính đến peak, phân phối latency, transaction dài, sai số, nguồn lực DB và safety margin.

Không đưa **thời gian chờ pool** vào `W` của đoạn đang *sở hữu connection* rồi suy ngược số connections cần cấp; hãy đo **borrow wait** và **hold time** riêng.

### 12.2. Các timeout không giống nhau

Connection pool/driver có thể có cấu hình cho:

1. **Borrow/acquisition timeout:** đợi connection khả dụng từ pool.
2. **Connect/login timeout:** thiết lập connection vật lý tới database.
3. **Query timeout:** thời gian query (ví dụ `Statement.setQueryTimeout(...)`, với cơ chế chi tiết phụ thuộc driver/DB).
4. **Transaction timeout/deadline:** nếu được transaction manager hỗ trợ.

`DataSource.setLoginTimeout(...)` **không phải** một chuẩn chung buộc mọi connection pool áp dụng cho thời gian chờ mượn connection. Phải xem tài liệu implementation thực tế.

## 13. Virtual threads có làm database nhanh hơn không?

Virtual threads có thể giúp ứng dụng duy trì nhiều **tác vụ chờ** mà không chiếm riêng platform thread cho toàn thời gian chờ; `Semaphore.acquire()` là một blocking synchronization point phù hợp với mô hình này.

Nhưng:

1. Pool 16 connections vẫn chỉ cấp tối đa 16 connections từ pool đó cùng lúc.
2. Query chậm hoặc DB quá tải không chạy nhanh hơn chỉ vì caller là virtual thread.
3. API chỉ chấp nhận 8 in-flight calls vẫn phải được bảo vệ dù ứng dụng có 100.000 virtual threads.
4. Mức scalability của thao tác JDBC còn phụ thuộc **driver, native code, đường I/O** và cách hiện thực blocking.

**Không cam kết mọi lệnh JDBC đều unmount virtual thread theo cùng một cách.** Hãy benchmark/quan sát stack driver và database thực tế, đo throughput, CPU, chờ pool và dấu hiệu pinning khi nghi ngờ.

Trong Java 27, việc dùng `synchronized` cũng không còn chịu mọi hạn chế pinning của các phiên bản virtual-thread ban đầu: hỗ trợ monitor đã được cải thiện từ Java 24. Vì vậy, không áp dụng máy móc lời khuyên cũ “mọi blocking operation bên trong `synchronized` đều pin carrier”. Native/foreign calls và các tình huống đặc biệt vẫn cần xem xét, nhưng **đó không phải lý do bỏ semaphore hoặc connection pool**.

## 14. Retry, circuit breaker, quota và backpressure là vấn đề riêng

Semaphore bảo vệ số calls **đồng thời**, không tự:

- Giới hạn tổng số **retries** gửi đến downstream.
- Hủy lập tức mọi tác vụ đã vượt deadline.
- Giới hạn tổng số tasks đang xếp hàng.
- Mở circuit breaker khi dịch vụ ngoài lỗi hệ thống.
- Kiểm soát requests/phút.
- Đảm bảo giao dịch không được thực thi trùng.

Một luồng xử lý có kiểm soát có thể gồm:

```text
Request deadline và admission limit
                  |
                  v
      Kiểm tra circuit state
                  |
                  v
        Try acquire có timeout
                  |
                  v
      Gọi downstream có I/O timeout
                  |
                  v
      Release permit trong finally
                  |
                  v
        Xử lý kết quả / lỗi
```

Thứ tự kết hợp các bước tùy kiến trúc, nhưng mỗi attempt retry **đều tiêu thụ** downstream capacity. Tránh giữ permit qua cả thời gian backoff khi không dùng tài nguyên; không retry vô hạn. Với API thanh toán hoặc thao tác có side effects, dùng **idempotency key** hay cơ chế xác minh trạng thái phù hợp — semaphore không giải quyết việc giao dịch bị lặp.

## 15. Đo lường: phân biệt nghẽn pool, permit và downstream

| Chỉ số | Ý nghĩa | Dấu hiệu cần điều tra |
| --- | --- | --- |
| Semaphore permits in use | Số calls trong vùng giới hạn | Chạm trần kéo dài |
| Semaphore wait duration | Chờ permit mất bao lâu | p95/p99 tăng hoặc nhiều timeouts |
| Acquire rejected/timed out | Không vào được trước deadline | Quá tải hoặc limit không phù hợp |
| Pool active connections | Connections đang được mượn | Gần max kéo dài; transaction scopes quá dài |
| Pool idle connections | Connections sẵn để mượn | Gần 0 trong khi chờ tăng |
| Pool acquisition wait | Chờ mượn connection | Nghẽn pool hoặc thời gian giữ connection cao |
| Pool acquisition timeout | Không mượn được connection đúng hạn | Vượt khả năng hoặc connection leak |
| Downstream latency/errors | DB/API phản hồi thế nào | Nguyên nhân thực tế có thể nằm ở downstream |
| Total in-flight/queued tasks | Khối lượng tác vụ đang sống | Backlog tăng vô hạn dù limit không đổi |

`availablePermits()` và `getQueueLength()` chỉ mô tả trạng thái tại thời điểm đọc hoặc **ước lượng** dưới concurrency. Đừng dùng một lần đọc làm quyết định điều phối đòi tính chính xác tuyệt đối; ưu tiên metrics theo thời gian, latency histograms và error counts.

Nếu pool active bằng max, chờ pool tăng và DB query latency cũng tăng, **tăng max pool có thể khiến DB quá tải nặng hơn**. Kiểm tra query chậm, locks, transaction scope, leaks và tổng pool budgets giữa các replicas trước khi thay cấu hình.

Khi logging, không để lộ connection strings chứa credentials, dữ liệu cá nhân trong SQL parameters hay HTTP body của thanh toán. Hãy đo thời gian và trạng thái tổng quát mà không rò rỉ dữ liệu nhạy cảm.

## 16. Ví dụ hoàn chỉnh: 12 virtual threads, tối đa 3 thao tác cùng lúc

Tạo file `Demo.java` sau. Ví dụ chỉ dùng các API chuẩn của Java 27, không cần database hay thư viện ngoài. `Thread.sleep(...)` **mô phỏng độ trễ I/O**, không gửi HTTP request thật.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class Demo {
    private static final int LIMIT = 3;

    private static String simulatedExternalCall(
            int id,
            Semaphore gate,
            AtomicInteger active,
            AtomicInteger peak) throws InterruptedException {

        if (!gate.tryAcquire(5, TimeUnit.SECONDS)) {
            return "busy-" + id;
        }

        try {
            int inFlight = active.incrementAndGet();
            try {
                peak.accumulateAndGet(inFlight, Math::max);
                Thread.sleep(80); // Mô phỏng I/O blocking.
                return "ok-" + id;
            } finally {
                active.decrementAndGet();
            }
        } finally {
            gate.release();
        }
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {

        Semaphore gate = new Semaphore(LIMIT, true);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();

        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<String>> futures = new ArrayList<>();

            for (int i = 1; i <= 12; i++) {
                final int id = i;
                futures.add(executor.submit(() ->
                        simulatedExternalCall(id, gate, active, peak)));
            }

            // Thu kết quả theo thứ tự submit, không giả định thứ tự
            // thực thi/hoàn thành của virtual threads.
            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        }

        System.out.println("peak in-flight = " + peak.get());
        System.out.println("final active = " + active.get());
        System.out.println("permits available = "
                + gate.availablePermits());

        if (peak.get() > LIMIT || active.get() != 0
                || gate.availablePermits() != LIMIT) {
            throw new AssertionError("Permit accounting failed");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac Demo.java
java Demo
```

Một lần chạy thông thường:

```text
ok-1
ok-2
ok-3
ok-4
ok-5
ok-6
ok-7
ok-8
ok-9
ok-10
ok-11
ok-12
peak in-flight = 3
final active = 0
permits available = 3
```

`peak in-flight` có thể **nhỏ hơn 3** tùy scheduler; bất biến cần kiểm tra là **không vượt 3**. Trong môi trường bị chậm bất thường, `tryAcquire(5, SECONDS)` có thể hết hạn và một dòng `busy-...` xuất hiện. Các tasks không nhất thiết **hoàn tất** theo thứ tự ID; output có thứ tự ID vì vòng lặp gọi `Future.get()` theo thứ tự submit.

Điểm kỹ thuật:

1. Có **12 tasks**, executor tạo virtual thread riêng cho từng task; **không có pool virtual threads kích thước 3**.
2. `Semaphore(3, true)` chỉ cho tối đa **3 lời gọi mô phỏng** trong đoạn bảo vệ cùng lúc.
3. `tryAcquire` giới hạn thời gian chờ và hỗ trợ interruption.
4. `active` tăng **sau khi lấy permit**, giảm và release trong các khối `finally`, kể cả khi `Thread.sleep` bị interrupt.
5. `AtomicInteger` giúp quan sát số in-flight an toàn giữa threads; nó không thay thế semaphore.
6. `ExecutorService` dùng `try-with-resources`; `close()` chờ các tasks đã submit hoàn tất theo hợp đồng.
7. `Future.get()` giúp caller quan sát lỗi của task qua `ExecutionException`, thay vì âm thầm bỏ qua thất bại.

Với ứng dụng thật, thay `Thread.sleep` bằng I/O có timeout và chọn LIMIT theo năng lực downstream, không lấy số 3 làm cấu hình mặc định.

## 17. Các lỗi triển khai phổ biến

| Cách làm | Vấn đề | Hướng tiếp cận |
| --- | --- | --- |
| Dùng fixed thread pool kích thước 8 để giới hạn virtual-thread workload | Pool virtual threads không được khuyến nghị; ràng buộc nhầm toàn bộ tasks | Virtual thread per task + `Semaphore(8)` ở ranh giới tài nguyên |
| Có 100.000 virtual threads chờ `acquire()` vì 8 permits | Chỉ giới hạn active, backlog vẫn rất lớn | Admission control, timeout, bounded queue |
| Release trong `finally` dù `acquire` chưa thành công | Release thừa, tăng permits vượt giới hạn | Chỉ vào `try/finally` sau acquire thành công |
| Quên release khi HTTP call ném exception | Permit leak, tác vụ sau chờ mãi | `finally` cho mọi đường thoát |
| `acquireUninterruptibly()` cho request có deadline | Cancellation khó dừng chờ permit | `acquire()`/`tryAcquire(timeout, unit)` |
| Coi `fair=true` là `tryAcquire()` luôn FIFO | Untimed `tryAcquire()` cho phép barging | Dùng timed variant khi cần fairness |
| Dùng semaphore để đạt quota 100 req/phút | Concurrency không phải rate | Rate limiter độc lập |
| Dùng `DataSource` nhưng tưởng JDK tự bật pooling | Basic DataSource không có pool | Cấu hình pooled implementation |
| Thêm semaphore 16 trên pool đã có tối đa 16 connections | Điều tiết trùng lặp và tạo thêm tầng chờ | Để pool tự giới hạn connections |
| Quên `Connection.close()` vì tin pool tự thu hồi | Rò rỉ logical connections | `try-with-resources` mỗi lần mượn |
| Giữ connection trong lúc gọi HTTP hàng giây | Chiếm slot DB không cần thiết | Thu hẹp connection/transaction scope |
| Chia sẻ `Connection` giữa virtual threads | Session state và thread safety khó kiểm soát | Mượn/trả connection mỗi task |
| Tăng pool size theo số lượng virtual threads | Có thể khiến database quá tải | Sizing theo DB và thời gian giữ connection |
| Quên tính nhiều replicas | Vượt tổng database connection budget | Cộng giới hạn trên toàn hệ thống |
| Coi `setLoginTimeout` là mọi pool borrow timeout | Cấu hình khác theo implementation | Dùng tài liệu pool và driver |
| Giữ permit qua đoạn code không dùng tài nguyên ngoài | Giảm throughput | Scope permit đúng đoạn I/O |
| Giữ nhiều resources theo thứ tự khác nhau | Có thể deadlock | Giảm vùng giữ đồng thời, thống nhất thứ tự |
| Retry vô hạn khi downstream lỗi | Khuếch đại tải và side effects | Deadline, retry budget, backoff, idempotency |
| Tin mọi JDBC call trên virtual thread đều non-blocking | Hiệu quả tùy driver và runtime path | Load test và đo stack thực tế |
| Chỉ theo dõi CPU, bỏ qua wait time | Khó thấy nghẽn pool/semaphore | Đo permit wait, pool borrow, timeout và latency |

## 18. Checklist khi đưa vào production

1. **Tài nguyên bị giới hạn là gì?** Concurrent calls, connections, quota/phút hay số tasks đang chờ?
2. **Giới hạn đã được thực thi ở đâu?** Pool, client, ingress hay cần semaphore mới?
3. **Có đang pool virtual threads thay vì đặt giới hạn tại resource boundary không?**
4. **Mỗi acquire thành công có đúng một release?** Xét exception, interruption và timeout.
5. **Semaphore có bảo vệ đúng đoạn I/O?** Không giữ qua công việc không liên quan.
6. **Có timeout chờ permit?** Mỗi request có deadline rõ ràng không?
7. **Downstream I/O có timeout riêng?** Chờ permit và socket/query là hai giai đoạn.
8. **Hàng đợi tổng có được kiểm soát?** Virtual threads không tạo bộ nhớ vô hạn.
9. **Cancellation có được chuyển tiếp hợp lý?** Không nuốt tín hiệu interrupt.
10. **Fairness có thật sự cần?** Nếu có, đã hiểu semantics của `tryAcquire()`?
11. **Pool đã cấu hình đúng?** Max size, borrow timeout, lifetime, validation, số replicas.
12. **Mã JDBC dùng `try-with-resources`?** Kể cả đường throw và return.
13. **Connection/transaction scope có quá dài?** Tránh giữ trong lúc gọi tài nguyên khác.
14. **Có nhiều resource limits gây deadlock?** Xác định thứ tự hoặc tách phase.
15. **Cần rate limiter/circuit breaker ngoài concurrency limit?** Không đánh đồng.
16. **Metrics đã tách thời gian chờ và thời gian thực thi?** Quan sát p95/p99, error rate, pool waits.
17. **Đã load test với driver, DB và pool thật?** Không suy hiệu năng từ `Thread.sleep`.
18. **Đã kiểm thử overload và recovery?** Khi không lấy được resource, hệ thống từ chối/thoái lui có kiểm soát.

## 19. Tổng kết

Virtual threads khiến **tác vụ đang chờ** rẻ hơn, nhưng database hay API ngoài **không có sức chứa vô hạn**. Trong Java 27, chọn **`Semaphore`** khi cần hạn chế các thao tác đồng thời vào tài nguyên chưa được điều tiết ở mức đó. Đặt `acquire` đúng ranh giới, **chỉ release sau acquire thành công**, bảo vệ bằng `try/finally` và cân nhắc timeout/cancellation.

Với database, **connection pool đã là bộ giới hạn số connections được mượn**. Ứng dụng mượn logical connection qua pooled `DataSource` được cấu hình thực sự, dùng `try-with-resources` để trả nó và giữ transaction/connection scope ngắn nhất mà vẫn đúng nghiệp vụ. **Không tự động chồng thêm semaphore cùng giới hạn** nếu không có một chính sách bảo vệ khác rõ ràng.

Điều quan trọng khi triển khai là phân biệt **concurrency, rate, connection capacity và queue capacity**; tính ngân sách toàn hệ thống, thiết lập deadline và giám sát điểm nghẽn thực tế. Khi đó virtual threads tăng khả năng mở rộng tác vụ I/O mà không đánh đổi an toàn cho tài nguyên ngoài.

## Tài liệu tham khảo

- [Virtual Threads — Java SE 27 Core Libraries](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html) — không pool virtual threads, dùng semaphore giới hạn concurrency và connection pool đã điều tiết connections.
- [Semaphore (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Semaphore.html) — permits, `acquire`/`release`, fairness, `tryAcquire` có timeout.
- [Executors (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html) — `newVirtualThreadPerTaskExecutor()`.
- [ExecutorService (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html) — `submit`, shutdown và `close()`.
- [Future (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html) — `get()`, `cancel(true)` và lỗi tác vụ.
- [DataSource (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/javax/sql/DataSource.html) — basic/pooling, `getConnection()`.
- [PooledConnection (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/javax/sql/PooledConnection.html) — logical handles và physical connections trong pool.
- [Connection (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/Connection.html) — session, transaction, `close()`, `AutoCloseable`.
- [PreparedStatement (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/PreparedStatement.html) — tham số hóa truy vấn JDBC.
- [AtomicInteger (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html) — biến đếm đồng thời trong ví dụ.
