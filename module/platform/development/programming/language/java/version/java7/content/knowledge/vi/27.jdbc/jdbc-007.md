# JDBC Connection.abort(Executor) — hủy kết nối khi cần thu hồi tài nguyên

**Chủ đề:** Java 7 — JDBC  
**Bài học:** Hủy kết nối bằng `abort` khi cần thu hồi  
**Phạm vi:** Java 17+ và JDBC 4.1 trở lên. `java.sql.Connection.abort(Executor)` xuất hiện từ Java 7 và **vẫn được hỗ trợ trong Java hiện đại**. Nội dung tập trung vào recovery của kết nối JDBC hỏng, không sử dụng phương thức đã lỗi thời. Mã kiểm thử chạy bằng JDK 17+ và mô phỏng hành vi JDBC bằng `java.lang.reflect.Proxy`; chương trình tương tác với database thật cần JDBC driver, cấu hình kết nối và integration test riêng.

## 1. Tình huống: connection không còn đáng tin cậy hoặc việc giải phóng thông thường bị kẹt

Khi giao tiếp với database, ứng dụng thường thực hiện:

```text
Acquire Connection → Prepare/Execute SQL → Commit/Rollback → Close/Return to Pool
```

Trong luồng xử lý bình thường, `Connection.close()` hoặc `try-with-resources` là cách **giải phóng connection**; với connection pool, `close()` của proxy thường là **trả connection về pool** chứ không nhất thiết đóng socket vật lý.

Nhưng có các tình huống bất thường:

- Network partition khiến một lời gọi JDBC bị kẹt lâu trong thao tác đọc/ghi socket.
- Driver phát hiện mất kết nối, trạng thái connection trở nên **không đáng tin cậy**.
- Một tác vụ database đang chạy không thể hoàn tất, cần một coordinator điều phối **thu hồi session**.
- Hệ thống đang shutdown, pool muốn loại bỏ các physical connections không còn khả năng phục hồi.
- `Statement.cancel()` không khả dụng/không giải phóng được connection bị lỗi ở mức mạng.
- Một connection không thể đưa lại vào pool vì có nguy cơ các trạng thái session/transaction không thể làm sạch.

Java JDBC cung cấp `Connection.abort(Executor)` cho tình huống này. Đây là một **cơ chế kết thúc kết nối**, không phải một cách tối ưu mặc định cho mọi request và **không** phải một phép “abort transaction” có rollback/commit semantics độc lập.

### 1.1. Ý tưởng chính

```text
                          Bình thường
                            |
    Work done → commit/rollback theo hợp đồng → close()
                            |
                       Pool/release

                          Bất thường
                            |
         Connection mất tin cậy / stuck I/O / retire
                            |
         Connection.abort(managedAbortExecutor)
                            |
        Connection được đánh dấu đóng theo hợp đồng
                            |
  Tasks giải phóng tài nguyên có thể còn chạy trên Executor
                            |
         Không sử dụng/không trả lại connection đó
                            |
  Tạo/borrow connection khác sau khi recovery policy cho phép
```

Điểm dễ nhầm nhất: **`abort` không giống `close`**, không giống `Statement.cancel` và không đồng nghĩa “transaction đã rollback thành công”. Ta phải hiểu cả API contract lẫn cách driver/pool thực thi.

### 1.2. Khi nào nên học phương thức này?

Khi phát triển ứng dụng dùng JDBC trực tiếp hoặc khi điều tra pool exhaustion, query stuck, connection leak, database failover hoặc service shutdown. Đây là khả năng hữu ích cho recovery, nhưng **không thay thế cấu hình query timeout, socket/network timeout, pool timeout, transaction boundaries hoặc monitoring**.

## 2. Hợp đồng chính thức của Connection.abort(Executor)

Chữ ký trong `java.sql.Connection`:

```java
void abort(Executor executor) throws SQLException;
```

Đây là chữ ký API, không phải một file Java hoàn chỉnh.

Theo JavaDoc, khi hủy một **connection đang mở** bằng `abort`:

1. Connection được **đánh dấu là closed**.
2. Physical connection tới database được đóng trong quá trình hủy.
3. Resources gắn với connection được giải phóng.
4. Threads đang truy cập connection sẽ hoặc **tiến tới hoàn tất**, hoặc nhận `SQLException`.

**Quan trọng:** việc giải phóng tài nguyên có thể tốn nhiều thời gian. Khi `abort` **trả về**, connection đã được **đánh dấu closed**, nhưng executor có thể **vẫn đang thực hiện các tasks cleanup**. Vì vậy:

- Không kết luận socket đã biến mất hoàn toàn chỉ vì method vừa trả về.
- Không sử dụng lại `Connection` sau `abort`.
- Không shutdown hoặc hủy executor theo cách ngăn các cleanup tasks vừa được submit có thể chạy.
- Không kết luận những SQL statements đang chạy đã được xử lý nghiệp vụ thành công.
- Không dùng `abort` làm giao thức xác nhận rollback/commit.

### 2.1. Executor tham gia vào đâu?

Argument `executor` là một `java.util.concurrent.Executor`. Driver có thể dùng nó để chạy phần việc hủy/đóng resources. Một số driver có những bước cleanup đồng bộ, một số có thể submit tasks; **không phải mọi driver đều làm giống nhau**.

```java
connection.abort(abortExecutor);
```

Đây là snippet, trong đó `abortExecutor` phải do một component sở hữu lifecycle hợp lệ cung cấp. Không nhất thiết nó phải là `ExecutorService`; chữ ký nhận interface `Executor`.

**Không truyền `null`:** trên một connection đang mở, hợp đồng API báo `SQLException` khi `executor` bằng null. Đừng thử `connection.abort(null)` để driver “tự chọn executor”.

### 2.2. Abort khi connection đã đóng

JavaDoc nói **gọi `abort` trên connection đã đóng là no-op**. Vì vậy đây không phải một cách “mở lại” connection hay một lệnh ép cleanup lặp vô hạn. Tuy nhiên, đừng dựa vào idempotence của no-op để thiết kế nhiều controllers cùng tự do hủy một connection pooled; **quyền sở hữu** và race với query/return-to-pool vẫn cần được kiểm soát.

### 2.3. Ngoại lệ

`abort` khai báo `SQLException`, có thể xuất hiện vì lỗi truy cập DB hoặc executor không hợp lệ, và các driver có thể có lỗi implementation riêng theo hợp đồng. Executor bị từ chối tasks có thể phát sinh một runtime exception như `RejectedExecutionException` trong thực tế; chi tiết exception phụ thuộc driver và executor.

**Không viết:**

```java
try {
    connection.abort(null);
} catch (Exception ignored) {
    // Coi như đã đóng xong.
}
```

Đây là **anti-pattern**, không phải mã sử dụng khuyến nghị. Việc bắt rồi bỏ mọi lỗi làm mất dấu tình trạng resource, cản trở điều tra pool exhaustion và có thể che lỗi nghiệp vụ ban đầu.

## 3. Phân biệt close, abort, cancel, timeout và validation

| Công cụ | Đối tượng | Mục tiêu | Tình huống thích hợp |
| --- | --- | --- | --- |
| `Connection.close()` | Toàn connection handle | Giải phóng trong lifecycle bình thường | Sau khi hoàn tất/rollback một request |
| `Connection.abort(Executor)` | Toàn connection | Kết thúc connection khi cần hủy/retire | Connection hỏng, recovery khẩn cấp, administrative shutdown |
| `Statement.cancel()` | Một statement | Yêu cầu hủy SQL statement đang thực thi nếu driver/DBMS hỗ trợ | Query quá lâu nhưng có thể giữ connection |
| `Statement.setQueryTimeout(seconds)` | Statement | Giới hạn thời gian thực hiện statement | Phòng ngừa query treo thông thường |
| `Connection.setNetworkTimeout(executor,millis)` | Connection | Giới hạn thời gian đợi phản hồi của một request DB; có thể làm connection bị đóng khi timeout | Network partition/stuck socket read |
| `Connection.isValid(timeoutSeconds)` | Connection | Kiểm tra connection còn hợp lệ không | Health check/validation theo policy |
| `DataSource.getConnection()` | Pool / DataSource | Cấp một connection để sử dụng | Bắt đầu unit of work |
| Pool-specific eviction API | Connection vật lý trong pool | Loại bỏ một connection không an toàn để tái sử dụng | Dùng pool như HikariCP, theo contract của pool |
| JDBC driver connect/socket timeout | Connection setup/network | Bảo vệ giai đoạn connect/read ở mức driver | Tùy driver; cần cấu hình vendor |

### 3.1. close là đường bình thường, abort là cơ chế recovery

Ví dụ:

```java
try (Connection connection = dataSource.getConnection()) {
    // Thực hiện nghiệp vụ bình thường.
    // transaction commit/rollback theo hợp đồng ứng dụng.
}
```

Đây là snippet, cần `DataSource dataSource` và code nghiệp vụ. Nếu dùng pool, `close()` của logical connection thường trả handle lại pool. Không nên thay mọi lời gọi `close` thành `abort`, vì có thể phá lợi ích tái sử dụng physical connections và tạo connection churn.

### 3.2. cancel chỉ nhắm vào statement

`statement.cancel()` có thể được gọi từ một thread khác để yêu cầu hủy statement khi driver và DBMS hỗ trợ. Nếu cancel hoạt động và trạng thái connection vẫn an toàn, ta có thể **tiếp tục sử dụng connection** theo policy (sau khi làm sạch transaction/session nếu cần).

`Connection.abort` **mạnh hơn**: mục tiêu là kết thúc toàn bộ connection, có thể ảnh hưởng mọi statements đang gắn với connection. Không sử dụng `abort` chỉ vì muốn “bỏ qua một query slow” nếu `setQueryTimeout`/`cancel` đủ và connection vẫn hợp lệ.

### 3.3. setQueryTimeout và setNetworkTimeout không giống nhau

`Statement.setQueryTimeout(int seconds)` điều khiển thời hạn thực thi SQL statement; khi vượt thời hạn, driver theo contract sẽ nỗ lực hủy statement và báo timeout. `Connection.setNetworkTimeout(Executor,int milliseconds)` bảo vệ tình huống lời gọi JDBC chờ phản hồi từ database trong điều kiện network fault, và kết nối có thể bị đánh dấu đóng khi network timeout xảy ra.

**Không nhầm đơn vị:** query timeout là **giây**; network timeout là **mili-giây**. `0` thường biểu thị không đặt timeout theo contract liên quan, nên không dùng zero mà tưởng “timeout ngay”.

Hỗ trợ và độ chính xác timeout phụ thuộc driver/DBMS. `setNetworkTimeout` có thể ném `SQLFeatureNotSupportedException` nếu driver không hỗ trợ. Đọc driver docs và integration test trường hợp mạng lỗi.

### 3.4. DriverManager login timeout không phải query timeout

`DriverManager.setLoginTimeout` hoặc một cấu hình `loginTimeout` của driver/pool chỉ liên quan **giai đoạn thiết lập kết nối**, không bảo vệ một câu SQL đã chạy từ lâu. Đừng dùng login timeout để mong tự hủy connection stuck trong `executeQuery()`.

## 4. Quy trình quyết định có abort hay không

Một cách đánh giá có thể bảo trì:

```text
Query hoặc transaction có vấn đề
       |
       v
Có phải lỗi statement còn có thể recover?
       |
       +---- Có ---> cancel/query timeout/rollback hoặc close theo policy
       |
       +---- Không / connection không còn tin cậy
                         |
                         v
             Pool quản lý physical connection?
                         |
              +----------+----------+
              |                     |
              v                     v
          Có pool              JDBC trực tiếp
              |                     |
              v                     v
      Pool-supported eviction   Connection.abort(executor)
      /mark broken               khi cần thu hồi
              |                     |
              +----------+----------+
                         |
                         v
              Ngừng mọi hoạt động trên handle
                         |
                         v
              Kiểm tra transaction outcome
              và kế hoạch retry/idempotency
```

**Không có một dấu hiệu đơn lẻ đủ cho mọi driver.** Một `SQLException` không đồng nghĩa connection đã hỏng. Ví dụ SQL syntax error, constraint violation hoặc deadlock SQL có thể cần rollback/retry tùy loại mà **không yêu cầu abort physical connection**. Ngược lại lỗi network, driver “connection is broken”, server shutdown, I/O stuck có thể cần retire session.

### 4.1. SQLState và classification

Nhóm SQLState `08xxx` thường liên quan **connection exception** và là một tín hiệu để xem xét retire connection, nhưng:

- Không phải mọi driver điền SQLState chính xác giống nhau.
- SQL exceptions có `getNextException()` và cause chain nên cần xem bối cảnh.
- Pool có thể có classifier riêng để đánh giá broken connection.
- Một timeout xảy ra khi query đang xử lý có thể để **transaction outcome chưa rõ**.
- Không chỉ kiểm tra `message.contains("timeout")` rồi hủy connection một cách mù quáng.

**Dùng mapping lỗi đã được driver và pool tài liệu hóa**, metrics theo SQLState/cause, và quy định rõ trường hợp normal close/rollback so với fatal abort.

### 4.2. Thời điểm escalation

Cân nhắc `abort` khi:

1. Cơ chế query timeout/cancel không thể bảo đảm tiến độ hợp lý.
2. Connection không còn đủ tin cậy để tiếp tục SQL hoặc tái sử dụng trong pool.
3. Coordinator có quyền quản lý lifecycle của chính connection đó.
4. Có executor khả dụng để hỗ trợ cleanup.
5. Service có chính sách retry / unknown transaction outcome / logging và monitoring rõ.
6. Hệ thống đã kiểm chứng hỗ trợ driver/pool trong tình huống fault tương ứng.

Nếu connection vẫn tốt, **dùng close/rollback thông thường**. Abort connection có thể làm chi phí tạo lại socket, authentication và session state.

## 5. Code application: connection abort với executor được quản lý

Đối với JDBC trực tiếp, controller có thể nắm một `Executor` dùng cho hủy/cleanup. Ví dụ **snippet trong một service đã có DataSource hoặc Connection factory**:

```java
ExecutorService abortExecutor = Executors.newFixedThreadPool(2);
// abortExecutor thuộc lifecycle của application/pool, không tạo-hủy per query.

void retireBrokenConnection(Connection connection, SQLException rootFailure)
        throws SQLException {
    try {
        connection.abort(abortExecutor);
    } catch (SQLException cleanupFailure) {
        rootFailure.addSuppressed(cleanupFailure);
    }
    throw rootFailure;
}
```

Đây là **snippet thiết kế**, không phải file tự biên dịch. Nó minh họa một executor có lifetime đủ dài và việc giữ nguyên nguyên nhân lỗi ban đầu. Không dùng snippet này như nguyên tắc bắt buộc khi connection được quản lý qua pool proxy; với pool cần contract eviction riêng.

### 5.1. Không tự tạo và shutdown executor trong cùng một lời gọi

Anti-pattern:

```java
ExecutorService executor = Executors.newSingleThreadExecutor();
connection.abort(executor);
executor.shutdownNow(); // Có thể làm gián đoạn resource cleanup đã submit.
```

Đây là snippet minh họa lỗi vận hành. Theo JavaDoc, cleanup tasks có thể còn chạy **sau khi `abort` trả về**. `shutdownNow` cố interrupt cả tasks đang chạy và ngừng tasks chưa chạy, không thích hợp nếu cần cho driver giải phóng resources.

**Tốt hơn:** executor được service/pool sở hữu và còn sống trong suốt quá trình recovery. Khi service shutdown, không chấm dứt cleanup executor quá sớm; phối hợp thứ tự stop admissions, retire resources, `shutdown()` và `awaitTermination` với deadline.

### 5.2. Không đưa một direct Executor vào mọi tình huống

`Executor direct = Runnable::run` chạy task ngay trên **caller thread**. Nó là cách hữu ích trong **mô phỏng/test** để kiểm tra rằng code thực sự gọi `executor.execute`, nhưng trong production nếu mục tiêu là cô lập việc cleanup có thể bị chặn, direct executor có thể khiến thread coordinator bị chiếm.

Dùng executor có thread độc lập và capacity hợp lý khi driver có thể làm việc tốn thời gian. Thời gian chính xác của `Connection.abort`/cleanup không được “cắt deadline” tự động chỉ vì bạn truyền một executor.

### 5.3. Giới hạn capacity và rejection

Nếu quá nhiều connections hỏng đồng thời, một executor unbounded queue có thể tích lũy cleanup tasks, còn executor quá nhỏ có thể bị backlog. Nếu đã `shutdown()`, `execute` có thể ném `RejectedExecutionException`. Cần chiến lược:

- Dedicated, được quản lý executor cho các thao tác hủy resource.
- Capacity/bounded queue phù hợp với số physical connections.
- Phương án handle rejected tasks, log/metrics và driver-specific fallback.
- Không giữ lock ứng dụng khi gọi abort nếu cleanup cần lock đó.
- Không cho người dùng bên ngoài gửi tùy ý lệnh hủy connection.
- Thử nghiệm thảm họa nhiều connections timeout cùng lúc.

**Không mặc định driver luôn sử dụng chính xác một task hoặc luôn submit bất đồng bộ.** `Executor` là một argument có contract; chi tiết triển khai driver cần được đo/kiểm chứng.

## 6. Chương trình 1: mô phỏng hợp đồng abort và no-op khi đã đóng

**Lưu ý kiểm thử:** vì Java SE không cung cấp một database/JDBC driver chạy sẵn trong JDK 17, các demo độc lập dưới đây dùng dynamic proxy giả lập `Connection`/`Statement`. Chúng kiểm tra **cách code ứng dụng gọi JDBC API, quản lý executor, xử lý lỗi và lifecycle**; **không chứng minh** rằng bất kỳ driver thật nào sẽ giải phóng network socket đúng kiểu mô phỏng.

Tạo `AbortContractDemo.java`:

```java
import java.lang.reflect.Proxy;
import java.sql.*;
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.*;
public class AbortContractDemo {
  public static void main(String[] args) throws Exception {
    AtomicBoolean closed = new AtomicBoolean();
    AtomicInteger cleanupCalls = new AtomicInteger();
    Connection connection = (Connection) Proxy.newProxyInstance(
        Connection.class.getClassLoader(), new Class<?>[]{Connection.class},
        (proxy, method, values) -> {
          switch (method.getName()) {
            case "abort":
              Executor executor = (Executor) values[0];
              if (executor == null) throw new SQLException("missing executor");
              if (closed.compareAndSet(false, true))
                executor.execute(cleanupCalls::incrementAndGet);
              return null;
            case "close": closed.set(true); return null;
            case "isClosed": return closed.get();
            case "isValid": return !closed.get();
            default: throw new SQLFeatureNotSupportedException(method.getName());
          }
        });
    connection.abort(Runnable::run);
    connection.abort(Runnable::run);
    System.out.println("closed=" + connection.isClosed());
    System.out.println("cleanup-calls=" + cleanupCalls.get());
    System.out.println("second-abort-noop=" + (cleanupCalls.get() == 1));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AbortContractDemo.java
java AbortContractDemo
```

**stdout đã kiểm thử:**

```text
closed=true
cleanup-calls=1
second-abort-noop=true
```

### 6.1. Giải thích

- Proxy chỉ hỗ trợ những phương thức cần cho test; `Connection` thật có nhiều phương thức khác do JDBC driver quản lý.
- `AtomicBoolean closed` mô phỏng trạng thái connection.
- `abort(Runnable::run)` gọi task cleanup trực tiếp, nên ví dụ có thể in số lần cleanup là 1.
- Lời gọi `abort` thứ hai khi closed mô phỏng no-op.
- `isClosed` báo true sau khi abort.

**Không suy rằng một driver thật chắc chắn gọi cleanup đúng một lần** hoặc thực thi nó trên caller thread. Đó là lựa chọn của mô phỏng, không phải yêu cầu chính xác về số tasks từ JDBC.

## 7. Chương trình 2: abort trả về trong khi cleanup còn chạy

Hợp đồng JavaDoc cho phép resource cleanup **tiếp tục trên executor** sau khi `abort` trả về. Ta tạo một latch để giữ task cleanup lại, chứng minh **hai dấu mốc không đồng nhất**.

Tạo `AbortAsyncCleanupDemo.java`:

```java
import java.lang.reflect.Proxy;
import java.sql.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
public class AbortAsyncCleanupDemo {
  public static void main(String[] args) throws Exception {
    AtomicBoolean closed = new AtomicBoolean();
    AtomicBoolean cleanupComplete = new AtomicBoolean();
    CountDownLatch started = new CountDownLatch(1);
    CountDownLatch permitCleanup = new CountDownLatch(1);
    ExecutorService executor = Executors.newSingleThreadExecutor();
    Connection connection = (Connection) Proxy.newProxyInstance(
        Connection.class.getClassLoader(), new Class<?>[]{Connection.class},
        (proxy, method, values) -> {
          switch (method.getName()) {
            case "abort":
              closed.set(true);
              ((Executor) values[0]).execute(() -> {
                started.countDown();
                try {
                  permitCleanup.await();
                  cleanupComplete.set(true);
                } catch (InterruptedException ex) {
                  Thread.currentThread().interrupt();
                }
              });
              return null;
            case "isClosed": return closed.get();
            case "close": closed.set(true); return null;
            default: throw new SQLFeatureNotSupportedException(method.getName());
          }
        });
    try {
      connection.abort(executor);
      if (!started.await(5, TimeUnit.SECONDS)) throw new AssertionError("cleanup not started");
      System.out.println("closed-after-return=" + connection.isClosed());
      System.out.println("cleanup-pending=" + !cleanupComplete.get());
      permitCleanup.countDown();
      executor.shutdown();
      if (!executor.awaitTermination(5, TimeUnit.SECONDS)) throw new AssertionError("cleanup hung");
      System.out.println("cleanup-finished=" + cleanupComplete.get());
    } finally {
      permitCleanup.countDown();
      executor.shutdownNow();
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AbortAsyncCleanupDemo.java
java AbortAsyncCleanupDemo
```

**stdout đã kiểm thử:**

```text
closed-after-return=true
cleanup-pending=true
cleanup-finished=true
```

**Ý nghĩa:**

1. `abort` đánh dấu closed và submit task tới executor.
2. Task báo started rồi đứng đợi latch do test nắm.
3. `abort` đã return nhưng `cleanupComplete` vẫn false.
4. Main cho phép cleanup tiếp tục, gọi `shutdown()` (không phải `shutdownNow`), rồi `awaitTermination`.
5. Cleanup hoàn thành và executor kết thúc.

**Đây là mô phỏng**, không phải kết quả đo độ trễ thực tế của driver. Một driver có thể xử lý đồng bộ một phần, dùng nhiều tasks, hoặc có lỗi network khiến cleanup lâu; application phải tránh nhầm return of abort với resource cleanup fully settled.

## 8. Chương trình 3: executor null và gọi abort lặp trên closed connection

Tạo `AbortArgumentDemo.java`:

```java
import java.lang.reflect.Proxy;
import java.sql.*;
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.*;
public class AbortArgumentDemo {
  public static void main(String[] args) throws Exception {
    AtomicBoolean closed = new AtomicBoolean();
    AtomicInteger operations = new AtomicInteger();
    Connection connection = (Connection) Proxy.newProxyInstance(
        Connection.class.getClassLoader(), new Class<?>[]{Connection.class},
        (proxy, method, values) -> {
          switch (method.getName()) {
            case "abort":
              if (values[0] == null) throw new SQLException("executor is null");
              if (closed.compareAndSet(false, true)) {
                operations.incrementAndGet();
                ((Executor) values[0]).execute(() -> {});
              }
              return null;
            case "isClosed": return closed.get();
            case "close": closed.set(true); return null;
            default: throw new SQLFeatureNotSupportedException(method.getName());
          }
        });
    boolean rejected = false;
    try { connection.abort(null); } catch (SQLException ex) { rejected = true; }
    boolean openAfterInvalid = !connection.isClosed();
    connection.abort(Runnable::run);
    connection.abort(Runnable::run);
    System.out.println("null-rejected=" + rejected);
    System.out.println("open-after-reject=" + openAfterInvalid);
    System.out.println("abort-once=" + (operations.get() == 1));
    System.out.println("closed=" + connection.isClosed());
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AbortArgumentDemo.java
java AbortArgumentDemo
```

**stdout đã kiểm thử:**

```text
null-rejected=true
open-after-reject=true
abort-once=true
closed=true
```

### 8.1. Lưu ý về edge case

Demo kiểm tra `null` **khi connection còn mở** và gọi lại `abort` bằng executor hợp lệ sau khi closed. Không dùng nó để suy ra thứ tự kiểm tra null/closed của tất cả JDBC drivers trong trường hợp connection đã closed mà lại truyền null; policy an toàn là **luôn truyền một Executor hợp lệ**.

Đừng tạo logic retry gọi abort nhiều lần liên tục để “bảo đảm socket đóng hẳn” — API contract không biến lần gọi thứ hai thành completion barrier cho cleanup lần đầu.

## 9. Chương trình 4: coordinator ngắt truy vấn bị kẹt (mô phỏng)

Một tình huống khó là một thread đang thực thi `Statement.execute(...)`, thread khác đóng vai controller phải thu hồi connection. Theo tài liệu, `abort` là một phương án administrator thread có thể dùng khi connection còn được truy cập từ bên ngoài và lời gọi I/O khác bị kẹt.

**Quan trọng:** không thử test này với một database thật mà không có timeout/watchdog và môi trường cô lập; một số network faults có thể làm thực thi treo lâu.

Tạo `AbortWatchdogDemo.java`:

```java
import java.lang.reflect.Proxy;
import java.sql.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
public class AbortWatchdogDemo {
  public static void main(String[] args) throws Exception {
    AtomicBoolean closed = new AtomicBoolean();
    CountDownLatch enteredQuery = new CountDownLatch(1);
    CountDownLatch released = new CountDownLatch(1);
    Statement statement = (Statement) Proxy.newProxyInstance(
        Statement.class.getClassLoader(), new Class<?>[]{Statement.class},
        (proxy, method, values) -> {
          switch (method.getName()) {
            case "execute":
              enteredQuery.countDown();
              if (!released.await(5, TimeUnit.SECONDS))
                throw new SQLException("simulated stalled query");
              if (closed.get()) throw new SQLNonTransientConnectionException("aborted", "08006");
              return true;
            case "close": return null;
            default: throw new SQLFeatureNotSupportedException(method.getName());
          }
        });
    Connection connection = (Connection) Proxy.newProxyInstance(
        Connection.class.getClassLoader(), new Class<?>[]{Connection.class},
        (proxy, method, values) -> {
          switch (method.getName()) {
            case "createStatement": return statement;
            case "abort":
              closed.set(true);
              ((Executor) values[0]).execute(released::countDown);
              return null;
            case "isClosed": return closed.get();
            case "close": closed.set(true); return null;
            default: throw new SQLFeatureNotSupportedException(method.getName());
          }
        });
    ExecutorService queryWorker = Executors.newSingleThreadExecutor();
    ExecutorService cleanupExecutor = Executors.newSingleThreadExecutor();
    try {
      Future<Boolean> result = queryWorker.submit(() -> {
        try (Statement stmt = connection.createStatement()) {
          return stmt.execute("SELECT 1");
        }
      });
      boolean started = enteredQuery.await(5, TimeUnit.SECONDS);
      if (!started) throw new AssertionError("query not started");
      connection.abort(cleanupExecutor);
      boolean gotSqlError = false;
      try { result.get(5, TimeUnit.SECONDS); }
      catch (ExecutionException ex) { gotSqlError = ex.getCause() instanceof SQLException; }
      System.out.println("query-started=" + started);
      System.out.println("worker-sql-error=" + gotSqlError);
      System.out.println("connection-closed=" + connection.isClosed());
    } finally {
      released.countDown();
      cleanupExecutor.shutdownNow();
      queryWorker.shutdownNow();
      cleanupExecutor.awaitTermination(5, TimeUnit.SECONDS);
      queryWorker.awaitTermination(5, TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AbortWatchdogDemo.java
java AbortWatchdogDemo
```

**stdout đã kiểm thử:**

```text
query-started=true
worker-sql-error=true
connection-closed=true
```

### 9.1. Cần đọc đúng điều gì từ demo?

- Thread query mô phỏng lời gọi SQL đang đợi trên `CountDownLatch`.
- Main là **coordinator** đợi tín hiệu query đã vào phương thức `execute` rồi gọi `Connection.abort` từ thread khác.
- Executor thực hiện task giải phóng latch, làm thread query tiếp tục.
- Thread query thấy closed và báo `SQLNonTransientConnectionException`; main nhận qua `Future.get`.
- Thread resources có deadline và cleanup trong `finally`.

**Điều này chỉ chứng minh khả năng xây test harness** bằng interfaces JDBC mà không có DB. Nó không chứng minh driver thật có thể hủy một socket I/O đang kẹt trong mọi loại network failure. Muốn kết luận thực tế, cần driver-specific integration test với fault injection (xem phần kiểm thử hệ thống).

### 9.2. Không chia sẻ một Connection cho nhiều nghiệp vụ đang chạy

Một connection JDBC không nên bị nhiều request độc lập sử dụng đồng thời mà không có lifecycle/ownership rõ. Trong demo, thread coordinator có quyền hủy connection được worker sử dụng vì đó là **cùng một test job**, không phải một request tùy ý abort connection của người khác.

Khi connection thuộc pool, lời gọi trên proxy và physical session có thể có semantics khác; dùng API do pool cung cấp để retire physical connection nếu có.

## 10. Giữ nguyên nguyên nhân lỗi ban đầu khi abort cũng thất bại

Trong một failure path, có thể có:

1. **Lỗi chính:** truy vấn/commit lỗi do connection lost.
2. **Lỗi cleanup:** `connection.abort(executor)` cũng ném `SQLException`.

Nếu code thay lỗi chính bằng lỗi cleanup, debugging trở nên khó hơn. `Throwable.addSuppressed` cho phép giữ cả hai:

```java
SQLException primary = originalFailure;
try {
    connection.abort(abortExecutor);
} catch (SQLException cleanupFailure) {
    primary.addSuppressed(cleanupFailure);
}
throw primary;
```

Đây là **snippet**, `originalFailure`/`connection`/`abortExecutor` phải được cung cấp ở scope phù hợp. Nó không có nghĩa bỏ qua cleanup failure; ta **gắn nó vào lỗi chính**.

### 10.1. Chương trình runnable: preserved root cause

Tạo `AbortErrorPreservationDemo.java`:

```java
import java.lang.reflect.Proxy;
import java.sql.*;
import java.util.concurrent.Executor;
public class AbortErrorPreservationDemo {
  static SQLException preserveRoot(SQLException primary, Connection connection, Executor executor) {
    try {
      connection.abort(executor);
    } catch (SQLException cleanupError) {
      primary.addSuppressed(cleanupError);
    }
    return primary;
  }
  public static void main(String[] args) throws Exception {
    Connection connection = (Connection) Proxy.newProxyInstance(
        Connection.class.getClassLoader(), new Class<?>[]{Connection.class},
        (proxy, method, values) -> {
          if (method.getName().equals("abort"))
            throw new SQLException("cleanup problem", "HY000");
          if (method.getName().equals("isClosed")) return false;
          throw new SQLFeatureNotSupportedException(method.getName());
        });
    SQLException original = new SQLNonTransientConnectionException("connection lost", "08006");
    SQLException recorded = preserveRoot(original, connection, Runnable::run);
    System.out.println("root-message=" + recorded.getMessage());
    System.out.println("root-sqlstate=" + recorded.getSQLState());
    System.out.println("suppressed-errors=" + recorded.getSuppressed().length);
    System.out.println("abort-error-kept=" + recorded.getSuppressed()[0].getMessage().equals("cleanup problem"));
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AbortErrorPreservationDemo.java
java AbortErrorPreservationDemo
```

**stdout đã kiểm thử:**

```text
root-message=connection lost
root-sqlstate=08006
suppressed-errors=1
abort-error-kept=true
```

### 10.2. Những lỗi khác ngoài SQLException

Executor có thể từ chối tasks, hoặc application có thể gặp interruption/cancellation. Không bắt `Throwable` rộng rồi coi mọi lỗi như SQL transient failure. Nếu recovery policy cần bắt `RejectedExecutionException` để xử lý nguồn executor bị đóng, hãy xử lý riêng và giữ root cause thích hợp.

Nếu driver/pool đưa thêm `SQLException.getNextException()`, log/correlation cần giữ chain mà không đưa credentials, SQL parameters nhạy cảm hoặc user data ra log.

## 11. Đừng biến mọi SQL exception thành abort

Một lỗi constraint như unique key violation có thể khiến statement không hoàn thành, nhưng physical connection **không nhất thiết hỏng**. Một lỗi network-level của driver khiến connection bị đóng có thể đòi retire thay vì trả pool.

Ứng dụng phải có **bộ phân loại lỗi** dựa trên driver/pool documentation và business boundary. Ví dụ policy dưới đây nhận sẵn boolean `unrecoverable`; **nó không tự đoán** mọi `SQLException` đều fatal.

### 11.1. Chương trình runnable: close bình thường, abort khi mất tin cậy

Tạo `AbortReleasePolicyDemo.java`:

```java
import java.lang.reflect.Proxy;
import java.sql.*;
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.AtomicInteger;
public class AbortReleasePolicyDemo {
  static Connection fake(AtomicInteger closes, AtomicInteger aborts) {
    return (Connection) Proxy.newProxyInstance(Connection.class.getClassLoader(),
        new Class<?>[]{Connection.class}, (proxy, method, values) -> {
          switch (method.getName()) {
            case "close": closes.incrementAndGet(); return null;
            case "abort": aborts.incrementAndGet(); ((Executor) values[0]).execute(() -> {}); return null;
            case "isClosed": return closes.get() + aborts.get() > 0;
            default: throw new SQLFeatureNotSupportedException(method.getName());
          }
        });
  }
  static void release(Connection connection, boolean unrecoverable, Executor executor)
      throws SQLException {
    if (unrecoverable) connection.abort(executor);
    else connection.close();
  }
  public static void main(String[] args) throws Exception {
    AtomicInteger normalCloses = new AtomicInteger(), normalAborts = new AtomicInteger();
    AtomicInteger brokenCloses = new AtomicInteger(), brokenAborts = new AtomicInteger();
    release(fake(normalCloses, normalAborts), false, Runnable::run);
    release(fake(brokenCloses, brokenAborts), true, Runnable::run);
    System.out.println("normal-close=" + normalCloses.get());
    System.out.println("normal-abort=" + normalAborts.get());
    System.out.println("broken-abort=" + brokenAborts.get());
    System.out.println("broken-close=" + brokenCloses.get());
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AbortReleasePolicyDemo.java
java AbortReleasePolicyDemo
```

**stdout đã kiểm thử:**

```text
normal-close=1
normal-abort=0
broken-abort=1
broken-close=0
```

Mục tiêu chỉ là phân biệt **policy branch**. Mô phỏng không có DB và không thể chứng minh việc close trả proxy về pool hoặc abort đóng socket của driver nào.

### 11.2. Hạn chế của boolean unrecoverable

Production cần nơi chịu trách nhiệm phân loại trạng thái connection. Ví dụ:

- SQLState class 08 hoặc thông tin “broken connection” từ pool.
- Driver documentation về lỗi kết nối, transaction và reconnect.
- Test fault injection với socket close/network partition.
- Pool có chính sách connection validation/eviction riêng.
- Trạng thái hệ thống đang shutdown hoặc failover.

Đừng cho business client bên ngoài quyền gửi `unrecoverable=true` để hủy tùy tiện physical connections. Nó nên là quyết định ở tầng infrastructure có ownership.

## 12. Phối hợp query timeout, network timeout, cancel và abort

Phòng ngừa vấn đề sớm thường tốt hơn phải abort khi đã kẹt. Các layers timeout có thể kết hợp:

```text
Request deadline at application layer
  |
  +-- connection acquisition timeout in pool
  |
  +-- Statement.setQueryTimeout(seconds)
  |
  +-- Connection.setNetworkTimeout(executor, milliseconds)
  |
  +-- driver connect/socket timeout (vendor-specific)
  |
  +-- watchdog / escalation to Connection.abort or pool eviction
```

### 12.1. Query timeout

`Statement.setQueryTimeout(3)` đặt thời hạn **3 giây** cho execute theo contract; nó không nhất thiết là giới hạn toàn bộ business request gồm queueing, connection acquisition, fetch rows và downstream processing.

Khi query timeout xảy ra, driver nỗ lực cancel và báo `SQLTimeoutException` theo hành vi được tài liệu hóa. Nếu network failure khiến cancel không thể thực thi, connection có thể cần biện pháp mạnh hơn. Consult driver docs.

### 12.2. Network timeout

`Connection.setNetworkTimeout(executor,10_000)` đặt **10.000 ms**, tức 10 giây, để chờ đáp ứng của một request. Theo JavaDoc, nếu network timeout hết khi chờ response, driver **đánh dấu connection closed** và các resources liên quan trở nên không dùng được.

**Đừng coi đây là timer “hủy mọi JDBC method sau đúng 10 giây” trên mọi driver**, và nhớ có thể không hỗ trợ. Nên test với phiên bản driver và cơ sở dữ liệu thật.

### 12.3. Cancel

`Statement.cancel()` là yêu cầu hủy statement. Nó có thể được gọi từ thread khác, nhưng nếu driver/DBMS không hỗ trợ, có thể ném `SQLFeatureNotSupportedException`. Không coi một lời gọi cancel đã trả về là chứng nhận chắc chắn DB transaction đã rollback; cần kiểm tra trạng thái kết quả và transaction.

### 12.4. Chương trình runnable: phân biệt bốn operations

Tạo `AbortTimeoutToolsDemo.java`:

```java
import java.lang.reflect.Proxy;
import java.sql.*;
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.AtomicInteger;
public class AbortTimeoutToolsDemo {
  public static void main(String[] args) throws Exception {
    AtomicInteger querySeconds = new AtomicInteger();
    AtomicInteger networkMillis = new AtomicInteger();
    AtomicInteger canceled = new AtomicInteger();
    AtomicInteger aborted = new AtomicInteger();
    Statement statement = (Statement) Proxy.newProxyInstance(
        Statement.class.getClassLoader(), new Class<?>[]{Statement.class},
        (proxy, method, values) -> {
          switch (method.getName()) {
            case "setQueryTimeout": querySeconds.set((Integer) values[0]); return null;
            case "cancel": canceled.incrementAndGet(); return null;
            case "close": return null;
            default: throw new SQLFeatureNotSupportedException(method.getName());
          }
        });
    Connection connection = (Connection) Proxy.newProxyInstance(
        Connection.class.getClassLoader(), new Class<?>[]{Connection.class},
        (proxy, method, values) -> {
          switch (method.getName()) {
            case "setNetworkTimeout": networkMillis.set((Integer) values[1]); return null;
            case "createStatement": return statement;
            case "abort": aborted.incrementAndGet(); ((Executor) values[0]).execute(() -> {}); return null;
            case "close": return null;
            default: throw new SQLFeatureNotSupportedException(method.getName());
          }
        });
    connection.setNetworkTimeout(Runnable::run, 10_000);
    try (Statement stmt = connection.createStatement()) {
      stmt.setQueryTimeout(3);
      stmt.cancel();
    }
    connection.abort(Runnable::run);
    System.out.println("query-timeout-seconds=" + querySeconds.get());
    System.out.println("network-timeout-ms=" + networkMillis.get());
    System.out.println("statement-cancel=" + canceled.get());
    System.out.println("connection-abort=" + aborted.get());
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AbortTimeoutToolsDemo.java
java AbortTimeoutToolsDemo
```

**stdout đã kiểm thử:**

```text
query-timeout-seconds=3
network-timeout-ms=10000
statement-cancel=1
connection-abort=1
```

**Cách đọc đúng:** proxy ghi lại arguments/method calls; nó **không thực thi SQL**, không tạo network timeout thật, không chứng minh statement đã cancel trên một DBMS. Nó giúp kiểm tra service truyền đúng **đơn vị seconds/milliseconds** và gọi method phù hợp.

### 12.5. Thứ tự áp dụng thời hạn

Một thiết kế thường có **request deadline tổng** lớn hơn hoặc bằng những thành phần nhỏ bên trong, nhưng không phải lúc nào cũng chọn timeout cao dần máy móc. Tham khảo mục tiêu SLA, retry, transaction timeout, driver socket timeout và network behavior để đặt giới hạn phù hợp.

Nếu `setNetworkTimeout` nhỏ hơn query timeout, connection có thể bị đóng trước khi query timeout được thực thi — một kết quả quan trọng khi điều tra “tại sao statement timeout nhưng cả connection mất”.

## 13. Connection pool và physical connection: điều gì bị hủy?

Với pool phổ biến như HikariCP:

- `DataSource.getConnection()` thường trả **proxy** đại diện một borrowed connection.
- `close()` trên proxy thường trả connection về pool sau cleanup.
- Một connection **không còn lành mạnh** cần được **retire/evict**, không để pool đưa nó cho request tiếp theo.
- Pool có thể cung cấp API riêng hoặc tự nhận diện broken connection theo SQLException/SQLState.
- Không tự unwrap physical connection rồi gọi `abort` nếu việc đó bỏ qua lifecycle của pool.
- Không giả định `Connection.abort` trên proxy luôn có semantics giống gọi trên physical connection; cần xem pool/driver version.

Một API cụ thể hiện hành ở HikariCP là `HikariDataSource.evictConnection(Connection)` để yêu cầu loại một connection của pool. **Đây là API thư viện HikariCP, không thuộc `java.sql.Connection` hay Java SE**. Việc dùng thực tế đòi HikariCP dependency và tuân thủ lifecycle/ownership của pool.

### 13.1. Ví dụ kiến trúc: dùng port riêng để không hard-code pool API

```java
interface PoolEvictor {
    void evict(Connection connection) throws SQLException;
}

// Khi dùng pool thực, adapter gọi API eviction do vendor hỗ trợ.
// Khi JDBC trực tiếp, infrastructure có thể lựa chọn connection.abort(executor)
// theo policy và không dùng pooling proxy.
```

Đây là **snippet kiến trúc**, thiếu imports và implementation nên **không phải chương trình standalone**. Nó giúp ứng dụng tách logic “connection không an toàn” khỏi cách từng pool thực sự remove physical connection.

### 13.2. Chương trình runnable: mô phỏng lựa chọn eviction hoặc close

Tạo `AbortPoolEvictionDemo.java`:

```java
import java.lang.reflect.Proxy;
import java.sql.*;
import java.util.concurrent.atomic.AtomicInteger;
public class AbortPoolEvictionDemo {
  interface PoolEvictor { void evict(Connection connection) throws SQLException; }
  static Connection fake(AtomicInteger closed) {
    return (Connection) Proxy.newProxyInstance(
        Connection.class.getClassLoader(), new Class<?>[]{Connection.class},
        (proxy, method, values) -> {
          if (method.getName().equals("close")) { closed.incrementAndGet(); return null; }
          if (method.getName().equals("isClosed")) return closed.get() > 0;
          throw new SQLFeatureNotSupportedException(method.getName());
        });
  }
  public static void main(String[] args) throws Exception {
    AtomicInteger poolEvictions = new AtomicInteger();
    AtomicInteger normalCloses = new AtomicInteger();
    PoolEvictor poolPolicy = connection -> poolEvictions.incrementAndGet();
    Connection broken = fake(normalCloses);
    poolPolicy.evict(broken);
    Connection healthy = fake(normalCloses);
    healthy.close();
    System.out.println("pool-evictions=" + poolEvictions.get());
    System.out.println("normal-closes=" + normalCloses.get());
    System.out.println("eviction-contract-is-external=true");
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AbortPoolEvictionDemo.java
java AbortPoolEvictionDemo
```

**stdout đã kiểm thử:**

```text
pool-evictions=1
normal-closes=1
eviction-contract-is-external=true
```

**Lưu ý:** demo chỉ xác minh adapter callback được gọi trong decision branch; nó **không mô phỏng hoàn chỉnh việc loại physical session**. Với production, đọc tài liệu của pool đang dùng và kiểm tra metrics connection count/retired count để xác nhận không còn tái sử dụng session hỏng.

### 13.3. Không lặp lại abort trên một proxy đã trả pool

Một tình huống nguy hiểm là giữ reference của logical connection, trả nó về pool, rồi một delayed watchdog gọi `abort` trên reference cũ. Vì connection ownership đã hết, bạn không được quyền xem nó còn đại diện physical session riêng của job ban đầu.

**Giải pháp:** watchdog/cancellation gắn với một **lease/ownership token** của request/connection; khi close/return pool, vô hiệu hóa token. Chỉ retire khi còn quyền sở hữu, hoặc chuyển việc retire sang chính pool để nó thực hiện atomic lifecycle phù hợp.

## 14. Tránh nhiều controllers cùng hủy một connection

Khi cùng một request có:

- Query timeout.
- Network watchdog.
- Global service shutdown.
- Admin cancel.
- Circuit breaker.
- Connection-pool health event.

...nhiều observers có thể đồng thời quyết định “cần abort”. Dù `abort` trên closed connection là no-op, hệ thống vẫn cần **điểm sở hữu duy nhất** để đảm bảo không race với việc returning connection vào pool hoặc vô tình gắn hai retry workflows cho cùng một job.

Một cơ chế đơn giản cho **một logical request** là CAS:

```java
if (retired.compareAndSet(false, true)) {
    connection.abort(abortExecutor);
}
```

Đây là snippet; `retired` là `AtomicBoolean` thuộc request state, `connection` và executor đã được cấp. CAS không giải quyết mọi pool ownership race, nhưng nó chặn nhiều controllers của **cùng request** cố hủy cùng một handle.

### 14.1. Chương trình runnable: chỉ một coordinator thắng quyền abort

Tạo `AbortSingleOwnerDemo.java`:

```java
import java.lang.reflect.Proxy;
import java.sql.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
public class AbortSingleOwnerDemo {
  public static void main(String[] args) throws Exception {
    AtomicBoolean retired = new AtomicBoolean();
    AtomicInteger abortCalls = new AtomicInteger();
    Connection connection = (Connection) Proxy.newProxyInstance(
        Connection.class.getClassLoader(), new Class<?>[]{Connection.class},
        (proxy, method, values) -> {
          if (method.getName().equals("abort")) {
            abortCalls.incrementAndGet();
            ((Executor) values[0]).execute(() -> {});
            return null;
          }
          if (method.getName().equals("isClosed")) return abortCalls.get() > 0;
          throw new SQLFeatureNotSupportedException(method.getName());
        });
    ExecutorService coordinators = Executors.newFixedThreadPool(4);
    try {
      List<Callable<Boolean>> attempts = new ArrayList<>();
      for (int i = 0; i < 4; i++) {
        attempts.add(() -> {
          if (!retired.compareAndSet(false, true)) return false;
          connection.abort(Runnable::run);
          return true;
        });
      }
      List<Future<Boolean>> results = coordinators.invokeAll(attempts, 5, TimeUnit.SECONDS);
      int selected = 0;
      for (Future<Boolean> result : results) if (result.get()) selected++;
      System.out.println("selected-owners=" + selected);
      System.out.println("abort-invocations=" + abortCalls.get());
      System.out.println("is-closed=" + connection.isClosed());
    } finally {
      coordinators.shutdownNow();
      coordinators.awaitTermination(5, TimeUnit.SECONDS);
    }
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AbortSingleOwnerDemo.java
java AbortSingleOwnerDemo
```

**stdout đã kiểm thử:**

```text
selected-owners=1
abort-invocations=1
is-closed=true
```

**Đúng phạm vi:** bốn controllers cùng tranh `compareAndSet`; chỉ một được gọi `abort`. **Không suy** rằng mọi tình huống SQL exception được giải quyết chỉ bằng `AtomicBoolean` — vẫn cần business state machine (RUNNING, CANCELLING, FAILED, COMPLETED), ownership của connection lease, transaction outcome và metrics.

### 14.2. Race với commit

Ngay khi watchdog quyết định abort, một transaction có thể vừa gửi `COMMIT` và server đã áp dụng hoặc chưa áp dụng. CAS chỉ kiểm soát **bao nhiêu controllers gọi abort**, không chứng minh commit thành công hay thất bại. Đây là vấn đề độc lập, cần policy khôi phục như phần 16.

## 15. Executor bị shutdown và RejectedExecutionException

Một lỗi trong recovery path: service đã đóng executor, nhưng code vẫn gọi `connection.abort(closedExecutor)`. Driver có thể cố `executor.execute(task)` và bị từ chối.

### 15.1. Chương trình runnable: mô phỏng rejection

Tạo `AbortExecutorRejectionDemo.java`:

```java
import java.lang.reflect.Proxy;
import java.sql.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
public class AbortExecutorRejectionDemo {
  public static void main(String[] args) throws Exception {
    ExecutorService executor = Executors.newSingleThreadExecutor();
    executor.shutdown();
    AtomicInteger cleanup = new AtomicInteger();
    Connection connection = (Connection) Proxy.newProxyInstance(
        Connection.class.getClassLoader(), new Class<?>[]{Connection.class},
        (proxy, method, values) -> {
          if (method.getName().equals("abort")) {
            ((Executor) values[0]).execute(cleanup::incrementAndGet);
            return null;
          }
          throw new SQLFeatureNotSupportedException(method.getName());
        });
    boolean rejected = false;
    try { connection.abort(executor); }
    catch (RejectedExecutionException ex) { rejected = true; }
    System.out.println("executor-rejected=" + rejected);
    System.out.println("cleanup-not-scheduled=" + (cleanup.get() == 0));
    System.out.println("precondition-violation=true");
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AbortExecutorRejectionDemo.java
java AbortExecutorRejectionDemo
```

**stdout đã kiểm thử:**

```text
executor-rejected=true
cleanup-not-scheduled=true
precondition-violation=true
```

Đây **không phải** bảo đảm rằng mọi JDBC driver đều ném chính xác `RejectedExecutionException` khi executor tắt. Demo cho thấy việc truyền một executor không thể chạy tasks là **rủi ro thiết kế**. Một driver có thể có behavior khác, báo lỗi khác hoặc làm cleanup một phần; kiểm chứng với driver thực.

### 15.2. Thiết kế lifecycle tốt hơn

- **Start:** khởi tạo dedicated recovery executor trước khi accept requests.
- **Normal service:** executor luôn sẵn sàng khi một connection cần retire.
- **Quiesce:** dừng nhận requests/borrow mới, cho phép current jobs hoàn tất hoặc fail.
- **Retire:** hủy các broken connections, chờ cleanup theo deadline và metrics.
- **End:** `shutdown()` và `awaitTermination` executor; chỉ sau đó đóng resource owner.
- **Forced shutdown:** ghi nhận incomplete cleanup và leak risk, không khẳng định đã xử lý mọi physical connection.

Không để caller tùy tiện đóng executor chung trong khi các operations khác vẫn cần nó.

## 16. Transaction outcome sau abort: có thể không xác định

**Điểm an toàn nghiệp vụ quan trọng nhất:** `Connection.abort` **không phải** lời gọi `rollback()` thành công và không phải một tín hiệu xác nhận rằng SQL effects đã/không được commit.

Xét hai dòng thời gian:

```text
Tình huống A:
Client ── INSERT ── COMMIT ──X network lost
Server ── INSERT ── commit success ── response mất
Client không nhận được ACK; abort connection
=> Dữ liệu CÓ THỂ đã commit dù client nhận lỗi.

Tình huống B:
Client ── INSERT ──X network lost before COMMIT arrives
Server không nhận hoặc chưa hoàn tất COMMIT
Client abort connection
=> Transaction CÓ THỂ không commit.

Cả hai cùng có biểu hiện ở client: "không nhận được xác nhận thành công".
```

Nếu client gọi abort rồi **retry một giao dịch không idempotent**, có nguy cơ chạy đôi các side effects. Với payment/order/create-resource, cần:

1. **Idempotency key** duy nhất cho logical operation.
2. Database unique constraint hoặc deduplication ở tầng xử lý.
3. Một cách truy vấn trạng thái server để xác minh operation outcome.
4. Transaction boundary rõ ràng.
5. Retry policy phân loại lỗi, không retry mọi SQLException.
6. Kiểm soát side effects ở các hệ thống ngoài DB.
7. Không ghi “rolled back successfully” khi chỉ có Connection.abort().

### 16.1. Chương trình runnable: unknown commit acknowledgment

Tạo `AbortUnknownOutcomeDemo.java`:

```java
import java.util.*;
public class AbortUnknownOutcomeDemo {
  enum Outcome { ACKNOWLEDGED, UNKNOWN }
  static Outcome classify(boolean receivedCommitAck) {
    return receivedCommitAck ? Outcome.ACKNOWLEDGED : Outcome.UNKNOWN;
  }
  public static void main(String[] args) {
    String operationId = "operation-42";
    Set<String> accepted = new HashSet<>();
    accepted.add(operationId);
    boolean deduplicated = !accepted.add(operationId);
    System.out.println("lost-ack-status=" + classify(false));
    System.out.println("known-ack-status=" + classify(true));
    System.out.println("duplicate-id-detected=" + deduplicated);
    System.out.println("need-server-verification=true");
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all AbortUnknownOutcomeDemo.java
java AbortUnknownOutcomeDemo
```

**stdout đã kiểm thử:**

```text
lost-ack-status=UNKNOWN
known-ack-status=ACKNOWLEDGED
duplicate-id-detected=true
need-server-verification=true
```

**Giới hạn:** `HashSet` là mô phỏng một idempotency store trong **một JVM**, không phải bảo đảm durable transaction hoặc distributed exactly-once. Production cần dữ liệu bền vững, constraints, atomic insert/commit và recovery query tương ứng.

### 16.2. Không gọi rollback trên connection đã abort

Sau khi `abort` đánh dấu connection closed, không giả định có thể gọi `rollback()` thành công trên cùng handle. Nếu transaction đang dang dở, DBMS/driver có chính sách rollback khi session mất, nhưng **thời điểm và trạng thái cuối cùng** phải được xác nhận qua database/driver documentation; lệnh rollback từ client sau abort không thể làm bằng chứng bảo đảm.

### 16.3. Điều gì cần log?

Một incident nên có:

- Operation ID/idempotency key (không có secret).
- Connection acquisition/lease ID an toàn để correlates logs.
- SQLState, vendor error code, class exception (tránh raw PII).
- Deadline đã đặt, timeout xảy ra ở tầng nào.
- Driver/pool/database version.
- Trạng thái transaction last acknowledged.
- Có gọi `Statement.cancel`/`Connection.abort`/pool eviction không.
- Kết quả wait cleanup/connection replacement.
- Tình trạng retry và outcome server verification.

Không ghi mật khẩu database, JDBC URL có credentials, auth tokens hoặc thông số truy vấn nhạy cảm vào logs.

## 17. Thiết kế thật với DataSource và pool

### 17.1. Trường hợp JDBC trực tiếp không qua pool

Một service có thể nhận `Connection` từ `DriverManager` hoặc một `DataSource` không pooling, dùng `try-with-resources` cho đường bình thường và có **dedicated error path** để abort nếu connection bị mất tin cậy.

**Pseudocode đời thực:**

```text
Acquire connection
Prepare/execute statement with query timeout
If success:
   Commit if manual transaction
   Close normally
If SQL error:
   Classify error + transaction outcome
   If recoverable:
       Rollback/close according to transaction policy
   Else if known unrecoverable:
       Stop other operations on connection
       Abort using managed executor
       Preserve error + suppressed cleanup failures
   Verify/deduplicate before retry
```

Đây là **pseudocode**, không thể dán trực tiếp vào file Java. Nếu bạn dùng connection pool, phần retire nên được điều khiển qua pool adapter như đã nêu, không tùy ý bypass pool.

### 17.2. Khi pool đã tự xử lý broken connections

Nhiều pools nhận diện connection fatal khi statement ném exception. Nếu pool đã mark connection broken và tự loại physical session khi logical proxy được đóng, ứng dụng có thể không cần gọi `abort` trực tiếp.

**Tránh gọi hai cơ chế eviction với giả định luôn lành tính.** Thay vào đó:

1. Đọc pool docs.
2. Biết connection proxy có delegated behavior gì.
3. Dựa vào error classifier và pool metrics.
4. Nếu thực sự cần manual eviction, dùng public API được pool hỗ trợ.
5. Test connection replacement sau khi inject fault.

### 17.3. Cách hiểu `HikariDataSource.evictConnection`

Đây là API của **thư viện**, không phải Java SE. Nó cho phép ứng dụng báo pool loại một connection cụ thể. Cách pool xử lý immediate/soft eviction phụ thuộc trạng thái borrowed/returned connection theo tài liệu và implementation của phiên bản đang dùng. **Không import HikariCP vào những ví dụ Java SE standalone**; chúng sẽ không biên dịch nếu không có dependency.

### 17.4. Đừng tạo DataSource mới sau mỗi abort

Nếu một physical connection bị hỏng, thường nên để **pool quản lý replacement** theo cấu hình. Việc hủy toàn bộ DataSource/pool rồi tạo lại sau một lỗi đơn lẻ có thể gây connection storm, mất pooling benefits và tăng tải database, trừ khi incident recovery policy thực sự yêu cầu thay cả pool.

## 18. Testing trên database thật: các kiểm chứng bắt buộc

Mười một chương trình Java SE của bài đã kiểm thử **API invocation và ứng dụng mô phỏng**. Không chương trình nào khởi tạo một connection thật đến PostgreSQL/MySQL/SQL Server/Oracle. Muốn xác nhận các hiệu ứng vật lý của `abort` cần integration testing.

### 18.1. Test matrix đề xuất

| Test | Cách thiết lập | Quan sát phải thu thập |
| --- | --- | --- |
| Normal release | Query thành công rồi `close` | Pool borrowed count giảm/connection reusable |
| Abort một connection mở | Borrow connection, gọi `abort(executor)` theo driver/pool policy | `isClosed`, session bị retire, resources eventually reclaimed |
| Abort khi đã closed | `close` trước rồi `abort` với executor hợp lệ | Driver behavior phù hợp no-op contract |
| Null executor | Trên connection còn mở gọi `abort(null)` | `SQLException`; không che root failure |
| Query đang chạy lâu | Câu truy vấn delay có thời hạn từ môi trường test | Worker và controller không kẹt ngoài deadline |
| Network partition | Fault injection tại network proxy | Khả năng giải phóng blocked reads; network timeout vs abort |
| DB restart/failover | Tắt/khởi động lại DB test | Pool evicts bad sessions và tạo replacement |
| Driver không hỗ trợ feature | Kiểm tra `setNetworkTimeout`/`Statement.cancel` | `SQLFeatureNotSupportedException` hoặc policy fallback |
| Pool proxy lifecycle | Borrow → mark broken/evict → borrow lại | Không dùng lại physical session cũ |
| Abort executor shutdown | Stop executor trước trong sandbox | Error/recovery metrics; không treo test |
| Nhiều abort đồng thời | N coordinators với ownership token | Một logical request chỉ retire once |
| Transaction lost ACK | Cắt kết nối quanh COMMIT test transaction | Status có thể UNKNOWN; dedup/reconcile |
| Shutdown race | Stop admission rồi retire active sessions | Executor cleanup còn sống đủ lâu |
| Resource leak | Lặp có giới hạn trong sandbox | Active sockets/threads/DB connections eventually giảm |

**Không kiểm thử fault injection phá mạng trên database production**. Dùng test container/DB riêng, test credentials hạn chế, max duration và cleanup watchdog. Đừng để bài test chạy vô hạn trong CI.

### 18.2. Bằng chứng nào cần thu thập?

- Driver/DBMS/pool version và JDBC URL **đã loại credentials**.
- Ghi nhận `Connection.isClosed` sau abort.
- Pool borrowed/idle/total metrics.
- Server-side session count và session IDs (nếu DB hỗ trợ).
- Thời gian từ abort request đến worker unblock.
- Thời gian từ abort return đến resource cleanup/physical session removal.
- Lỗi do query worker nhận và trạng thái transaction.
- Số lần retry/idempotency outcomes.
- Timeout values có đơn vị rõ.
- Executor threads active/queued/rejected.

### 18.3. Một kết luận thường bị nói quá

Nếu `connection.isClosed()==true` ngay sau abort, điều đó **không tự chứng minh**:
- physical TCP socket đã được OS dọn xong,
- server đã rollback/commit theo suy đoán,
- tất cả locks phía server đã được giải phóng ngay,
- pool đã tạo connection replacement,
- mọi client worker đã ngừng hoạt động,
- mọi side effect bên ngoài database đã được đảo ngược.

`isClosed` là tín hiệu JDBC handle state, không phải hệ thống đo toàn bộ health/distributed transaction.

## 19. Các lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `abort` sau mọi query bình thường | Hủy physical connections không cần thiết | `close`/try-with-resources |
| Nghĩ `abort` chỉ dừng một statement | Tác động cả connection | `Statement.cancel` hoặc query timeout |
| Truyền null executor | `SQLException` theo contract | Cung cấp executor hợp lệ |
| Tạo executor rồi `shutdownNow` ngay | Cleanup tasks bị interrupt/bỏ qua | Executor có lifecycle của service/pool |
| Dùng direct executor cho cleanup network chậm | Caller bị chặn không mong muốn | Managed executor phù hợp, test driver |
| Truyền executor đã shutdown | Tasks có thể bị reject | Giữ capacity/lifecycle đúng |
| Giả định abort không bao giờ block | Có thể có work đồng bộ trước return | Watchdog, deadline và driver test |
| Giả định abort return = physical cleanup complete | Resource cleanup có thể tiếp tục | Monitor/reconcile completion |
| Coi abort = rollback | Commit outcome có thể không xác định | Verify, idempotency và transaction policy |
| Retry non-idempotent transaction sau mất ACK | Có thể duplicate side effect | Idempotency key/unique constraint |
| Dùng `isClosed` để suy server session/locks đã biến mất | Sai cấp độ đo | Server-side metrics và DB check |
| Bắt `SQLException` rồi bỏ nguyên nhân chính | Debug và error propagation kém | Suppress cleanup failures |
| Bắt mọi `Throwable` và im lặng | Có thể che lỗi nghiêm trọng | Bắt ngoại lệ có chủ đích |
| Gọi `rollback` sau khi abort rồi tin đã thành công | Connection đã unusable | Xử lý transaction state trước/verify server |
| Gọi abort qua pool proxy không hiểu semantics | Pool lifecycle bị bypass/race | Pool-supported eviction API |
| Unwrap raw connection rồi bypass pool | Broken pool inventory | Infrastructure adapter/pool contract |
| Giữ reference sau khi trả connection về pool | Watchdog có thể đụng lease hết hạn | Owner token/cancel handle |
| Dùng SQLState string comparison duy nhất | Có thể classify sai lỗi | Driver/pool-aware classifier |
| Nghĩ setQueryTimeout thay thế network timeout | Network faults có thể chặn cancellation | Phối hợp timeout layers |
| Quên đơn vị timeout seconds vs milliseconds | Timeout sai x1000 | Đặt tên biến có suffix đơn vị |
| `setNetworkTimeout` không được driver hỗ trợ | Unexpected SQLException | Feature detection/fallback |
| Thử nghiệm bằng fake Proxy rồi tuyên bố driver thật tốt | Sai bằng chứng | Integration test với DB thực |
| Không có quota abort tasks | Cleanup queue hoặc threads có thể quá tải | Bounded executor/admission |
| Cho người dùng ra lệnh abort connection bất kỳ | DoS/hủy transaction người khác | Authorization, ownership và audit |
| Ghi JDBC password/SQL parameters trong log | Rò dữ liệu | Scrub/redact telemetry |
| Abort toàn pool vì một connection lỗi | Connection storm | Pool eviction individual theo policy |

## 20. Checklist code review cho Connection.abort

1. Tình huống có thực sự cần **terminate connection**, hay chỉ close/cancel statement?
2. Có một policy phân biệt normal close và unrecoverable connection không?
3. Có dùng JDBC `Connection.abort(Executor)` từ API đang được hỗ trợ không?
4. Có truyền executor non-null và còn khả năng `execute` tasks không?
5. Executor có lifetime do app/pool quản lý, không shutdown quá sớm không?
6. Có tránh direct executor nếu cleanup có thể block caller critical thread không?
7. Có bounded capacity/rejection policy nếu nhiều connections fail cùng lúc không?
8. Có hiểu `abort` trả về khi marked closed nhưng tasks cleanup có thể còn chạy không?
9. Có không tiếp tục sử dụng `Connection`/`Statement` sau abort không?
10. Có giữ connection ownership token đến khi retire hoàn tất theo policy không?
11. Nếu dùng pool, có tuân theo eviction contract của pool cụ thể không?
12. Có tránh unwrap physical connection tùy tiện không?
13. Có không giữ reference để hủy sau khi logical connection đã trả pool không?
14. Có dùng `Statement.setQueryTimeout` với **seconds** khi thích hợp không?
15. Có dùng `Connection.setNetworkTimeout` với **milliseconds** khi driver hỗ trợ không?
16. Có phân biệt `Statement.cancel` với connection-level abort không?
17. Có test trên driver/DBMS version thật trước khi dựa vào behavior không?
18. Có điều phối query worker và watchdog để tránh hủy connection của request khác không?
19. Có không ném bỏ primary SQL exception khi cleanup cũng lỗi không?
20. Có log SQLState, vendor code và root cause an toàn không?
21. Có hiểu aborted transaction có thể **UNKNOWN outcome**, không giả định rollback không?
22. Có idempotency key hoặc DB constraint khi retry không?
23. Có tránh retry vô hạn với non-idempotent transactions không?
24. Có theo dõi server session count/pool metrics sau abort không?
25. Có tránh kết luận socket cleanup done chỉ từ `isClosed` không?
26. Có integration test network partition, server restart, query stuck và shutdown race không?
27. Có bảo đảm test fault injection dùng môi trường cô lập và deadline không?
28. Có giới hạn quyền kích hoạt administrative abort không?
29. Có không dùng API đã lỗi thời trong implementation mới không?
30. Có quy trình thu hồi resources trước khi service shutdown executor không?

## 21. Bài tập thực hành

**Bài 1 — Hiểu contract.** Chạy `AbortContractDemo`. Giải thích vì sao second abort không tạo thêm cleanup task trong mô phỏng; so sánh với điều mà JavaDoc thực sự bảo đảm.

**Bài 2 — Async cleanup.** Chạy `AbortAsyncCleanupDemo`. Vẽ ba thời điểm: abort returns, task cleanup starts, task cleanup finishes. Vì sao không được shutdownNow ngay?

**Bài 3 — Null executor.** Chạy `AbortArgumentDemo`. Viết một helper validation đảm bảo `executor != null` trước khi gọi `abort`.

**Bài 4 — Watchdog.** Chạy `AbortWatchdogDemo`. Thay delay query bằng một latch và deadline khác; không tạo test có thể treo vô hạn.

**Bài 5 — Exceptions.** Chạy `AbortErrorPreservationDemo`. Bổ sung log SQLState của root và suppressed error nhưng không ghi credentials.

**Bài 6 — Release policy.** Chạy `AbortReleasePolicyDemo`. Đề xuất classifier dùng SQLState/driver/pool metadata, và chỉ abort khi thật sự unrecoverable.

**Bài 7 — Timeout units.** Chạy `AbortTimeoutToolsDemo`. Đổi query timeout thành 5 seconds, network timeout thành 15_000 ms. Vì sao hai đơn vị khác nhau?

**Bài 8 — Pool eviction.** Chạy `AbortPoolEvictionDemo`. Viết adapter tới pool đang sử dụng trong dự án (thêm dependency riêng), test rằng physical connection không quay lại active pool.

**Bài 9 — Ownership race.** Chạy `AbortSingleOwnerDemo` với 20 controllers. Thiết kế CAS gắn với request lease và ngừng watchdog khi connection đã close.

**Bài 10 — Executor rejection.** Chạy `AbortExecutorRejectionDemo`. Thiết kế fallback khi executor không chạy được mà không khẳng định cleanup đã hoàn tất.

**Bài 11 — Unknown outcome.** Chạy `AbortUnknownOutcomeDemo`. Đưa operation ID vào database unique index hoặc idempotency store thực; kiểm tra trường hợp response commit bị mất.

**Bài 12 — Comparison.** Viết một bảng ghi rõ tác động của `close`, `Statement.cancel`, `setQueryTimeout`, `setNetworkTimeout` và `abort` tới connection/statement.

**Bài 13 — Transaction.** Tạo một test DB thật trong sandbox, thực hiện `INSERT` có idempotency key, simulate mất ACK quanh COMMIT và kiểm tra dữ liệu server trước retry.

**Bài 14 — Pool.** Dùng một connection pool đang hỗ trợ và test `close` trả connection; sau đó simulate broken connection và kiểm tra eviction/borrow mới.

**Bài 15 — DB failover.** Trong sandbox, restart database khi query đang chạy; đo thời gian worker thoát và pool replacement. Có watchdog tối đa, không để CI treo.

**Bài 16 — Network partition.** Dùng network proxy fault injection, so `setNetworkTimeout` với controller gọi `abort`. Xác nhận driver support thực tế.

**Bài 17 — Shutdown.** Thiết kế service shutdown theo thứ tự stop admission → abort broken sessions → await cleanup executor → terminate pool. Test không rò threads.

**Bài 18 — Metrics.** Đo count abort_requested, abort_failed, cleanup_pending, pool_evicted, active connections và transaction_outcome_unknown.

**Bài 19 — Security.** Thiết kế chính sách ai được phép administrative abort, audit log nào được ghi và cách redact JDBC URL/SQL parameters nhạy cảm.

**Bài 20 — Production incident.** Với triệu chứng “connection pool exhausted, một số JDBC calls stuck”, viết runbook gồm kiểm tra pool metrics, network/driver timeouts, root-cause classification, safe eviction, transaction reconciliation và bảo đảm không chạy lại giao dịch gây duplicate.

## 22. Tổng kết

- `Connection.abort(Executor)` là API JDBC **vẫn hiện hành** dùng để **terminate** connection khi thu hồi tài nguyên khẩn cấp, không phải thay thế `close()` trong mọi đường đi bình thường.
- Khi `abort` trả về, connection đã được **đánh dấu đóng**, nhưng executor có thể vẫn còn **cleanup tasks** đang hoạt động.
- **Executor** cần hợp lệ, non-null, có lifecycle đủ dài và capacity phù hợp. Nếu shutdown quá sớm hoặc bị reject tasks, recovery có thể không đầy đủ.
- `Statement.cancel` và `setQueryTimeout` nhắm tới statement; `setNetworkTimeout` nhằm tình huống network wait; `abort` là hành động ở **toàn connection**.
- Với pool, phải xem pool-specific semantics/eviction API; không tự unwrap physical connection hoặc hủy handle đã trả pool.
- Một `SQLException` đơn lẻ không luôn là lý do abort. Hãy phân loại theo driver/pool và tình trạng connection.
- **Không giả định abort = rollback**. Nếu mất xác nhận COMMIT, transaction outcome có thể **UNKNOWN**; cần server verification và idempotency trước khi retry.
- Giữ root SQL exception; gắn cleanup failure vào suppressed exceptions hoặc monitoring.
- Các ví dụ `Proxy` của bài **chỉ là unit test mô phỏng API**: runnable trên JDK 17+ nhưng không thay thế integration testing với DBMS/driver thật.
- Kiểm thử network faults, pool eviction, cleanup latency, timeout và transaction reconciliation trong sandbox trước khi sử dụng `abort` như recovery mechanism production.

## Tài liệu chính thức và nguồn tham khảo

- [Connection — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html): `abort(Executor)`, `close()`, `setNetworkTimeout`, `isClosed`, `isValid` và transaction lifecycle.
- [Connection — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): contract tương thích với Java 17.
- [Statement — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html): `cancel()`, `setQueryTimeout(int)` và `SQLTimeoutException`.
- [SQLException — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor error code, nextException chain.
- [SQLNonTransientConnectionException — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/SQLNonTransientConnectionException.html): phân loại lỗi connection.
- [Executor — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executor.html): contract `execute(Runnable)`.
- [ExecutorService — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `shutdownNow`, `awaitTermination`.
- [DataSource — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/javax/sql/DataSource.html): tạo kết nối trong ứng dụng.
- [pgJDBC — Connection parameters](https://jdbc.postgresql.org/documentation/use/): ví dụ tài liệu driver về query/socket/connect timeout; chỉ áp dụng khi dùng PostgreSQL JDBC.
- [HikariCP — HikariDataSource source](https://github.com/brettwooldridge/HikariCP/blob/dev/src/main/java/com/zaxxer/hikari/HikariDataSource.java): API `evictConnection` của pool và lifecycle.
