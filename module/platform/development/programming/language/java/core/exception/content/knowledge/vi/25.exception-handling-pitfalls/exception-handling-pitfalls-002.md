# Bắt Exception hoặc Throwable quá rộng ở mọi tầng: sai lầm phổ biến trong Java

## 1. Bản chất của vấn đề

Java dùng exception để báo một lời gọi **không thể hoàn tất theo hợp đồng**. Khi gặp exception, JVM tìm `catch` thích hợp trên call stack của **luồng đang thực thi**, chạy các khối dọn dẹp cần thiết rồi chuyển điều khiển đến handler. Vì thế, không cần và cũng không nên đặt một `catch` chung trong mọi phương thức trung gian.

Anti-pattern thường gặp:

```java
try {
    performBusinessOperation();
} catch (Exception ex) {
    System.err.println(ex.getMessage());
    return null;
}
```

Đây là **mảnh code cố tình minh họa sai lầm**, giả sử `performBusinessOperation()` đã được định nghĩa và method bao quanh cho phép `return null`. Nó trông có vẻ an toàn vì không có exception vượt ra ngoài, nhưng có thể:

- Giấu lỗi I/O hoặc bug lập trình và biến một thất bại thành kết quả hợp lệ giả.
- Làm mất khả năng phân biệt lỗi input, lỗi trạng thái, lỗi phụ thuộc và lỗi cancellation.
- Ngăn caller thực hiện retry, rollback, hiển thị mã lỗi hoặc báo động phù hợp.
- Log dữ liệu nhạy cảm qua `getMessage()` nhưng vẫn không giữ đầy đủ stack trace.
- Làm hệ thống tiếp tục ở trạng thái không đúng hợp đồng.

Một biến thể nghiêm trọng hơn:

```java
try {
    performBusinessOperation();
} catch (Throwable error) {
    return null;
}
```

`Throwable` còn bao gồm `Error`; bắt rồi nuốt nó không đảm bảo JVM hoặc thành phần bên dưới còn vận hành an toàn.

**Nguyên tắc:** một tầng chỉ nên bắt loại lỗi mà nó **thật sự có trách nhiệm và khả năng xử lý**: phục hồi hợp lệ, dịch lỗi sang contract của tầng, cleanup/rollback ở phạm vi sở hữu, ghi nhận kết quả thất bại hoặc trả thông báo ở boundary. Các lỗi khác nên tiếp tục lan truyền.

“Không bắt ở đây” không đồng nghĩa “bỏ qua lỗi”. Nó có thể là cách để tầng phù hợp hơn quyết định chính sách.

## 2. Phân cấp exception quan trọng

```text
java.lang.Throwable
├── Error
│   ├── OutOfMemoryError
│   ├── StackOverflowError
│   ├── LinkageError
│   └── AssertionError
└── Exception
    ├── IOException
    │   └── FileNotFoundException
    ├── SQLException
    ├── InterruptedException
    ├── ExecutionException
    └── RuntimeException
        ├── IllegalArgumentException
        ├── IllegalStateException
        ├── NullPointerException
        └── IndexOutOfBoundsException
```

Đây là cây **rút gọn**, không liệt kê mọi class.

| Catch | Phạm vi bắt được | Lưu ý |
| --- | --- | --- |
| `catch (IOException ex)` | `IOException` và subclass như `FileNotFoundException` | Thích hợp nếu tầng xử lý lỗi I/O |
| `catch (RuntimeException ex)` | Runtime exceptions | Có thể vô tình nuốt bug `NullPointerException` |
| `catch (Exception ex)` | Checked và unchecked thuộc `Exception` | **Không** bắt `Error`, nhưng **có** bắt `InterruptedException` |
| `catch (Throwable ex)` | Cả `Exception` và `Error` | Không chứng minh có thể phục hồi mọi lỗi |
| `catch (InterruptedException ex)` | Tín hiệu ngắt chờ | Cần quyết định truyền tiếp hoặc khôi phục interrupt flag |

Checked exception yêu cầu caller xử lý hoặc khai báo tại compile time; các subclass của `RuntimeException` và `Error` không chịu yêu cầu ấy. Nhưng **checked/unchecked không tự quyết định nơi catch**. Đó là vấn đề contract và chính sách.

Đặc biệt, `catch (Throwable)` không có nghĩa “bắt được mọi trạng thái phá hủy JVM”: process có thể bị kill, máy mất điện hoặc runtime không còn tài nguyên để thực thi handler.

## 3. Vì sao bắt rộng ở mọi tầng làm kiến trúc yếu đi?

Giả sử hệ thống có:

```text
Controller -> OrderService -> OrderRepository -> Database
```

Nếu mọi tầng đều làm:

```java
try {
    callNextLayer();
} catch (Exception ex) {
    logger.error("failed", ex);
    throw new RuntimeException("failed");
}
```

thì một lỗi `SQLException` có thể trở thành chuỗi nhiều wrapper `RuntimeException` không rõ loại. Vì constructor mới không có `cause`, **lỗi gốc có thể mất hẳn**. Nếu mỗi tầng ghi log, một sự kiện tạo nhiều stack trace trùng, làm ồn dashboard và tăng nguy cơ rò dữ liệu từ cause.

Tệ hơn, nếu repository trả `null` khi DB không sẵn sàng, service có thể tưởng “không tìm thấy đơn hàng”. Tầng HTTP trả 404 thay vì 503, khiến client không retry dù lỗi thật chỉ tạm thời.

Một vài biểu hiện:

1. Mọi method có `try/catch (Exception)` gần như giống nhau, không làm công việc hữu ích.
2. Handler trả `null`, `false`, `0`, object mặc định hoặc trạng thái “success” khi không thể chắc chắn thành công.
3. Lỗi đầu vào, lỗi business và lỗi hạ tầng bị bọc thành cùng một class.
4. Exception chỉ được log message mà không giữ cause/stack, hoặc bị log ở quá nhiều tầng.
5. Tác vụ đang hủy cũng bị đưa vào vòng retry như mọi lỗi khác.
6. `Error` nghiêm trọng bị swallow để tiến trình “cứ chạy”.

Đừng tối ưu cho “không xuất hiện exception trên console” mà bỏ qua **tính đúng của dữ liệu và hành vi caller**.

## 4. Call stack đã tự lan truyền lỗi qua các tầng

Ví dụ khái niệm:

```java
static void repository() throws IOException {
    throw new IOException("dependency unavailable");
}

static void service() throws IOException {
    repository();
}

static void entryPoint() {
    try {
        service();
    } catch (IOException ex) {
        // Một nơi có trách nhiệm chuyển lỗi thành phản hồi phù hợp.
    }
}
```

Đây là **các phương thức minh họa** cần đặt trong class và import `java.io.IOException`. `service()` không cần catch chỉ để ném lại. Nếu nó không có nghiệp vụ phục hồi hoặc translation, để exception lan truyền là hợp lý.

Trong lúc exception đi ngược stack:

- `finally` có cơ hội cleanup theo quy tắc Java.
- `try-with-resources` đóng tài nguyên `AutoCloseable`.
- Monitor của vùng `synchronized` được giải phóng khi unwind.
- Các thay đổi đã làm lên object, file hay DB **không tự được rollback**.
- Một exception trong worker thread **không tự** sang `catch` ở luồng khác; cần `Future` hoặc kênh chuyển kết quả.

Một `catch` thừa không làm stack unwinding an toàn hơn. Nó chỉ bổ sung một chỗ có thể che lỗi, biến đổi trạng thái hoặc ném một exception mới.

## 5. Ba anti-pattern chính

### 5.1. Swallow rồi trả giá trị giả

```java
String loadOrder(String id) {
    try {
        return repository.fetch(id);
    } catch (Exception ignored) {
        return "ORDER_READY";
    }
}
```

**Mảnh code minh họa sai**, với `repository` đã định nghĩa. Nếu repository offline, caller vẫn nhận `ORDER_READY`. Nếu kiểu kết quả là `Optional<T>`, trả `Optional.empty()` cho lỗi kết nối cũng sai nếu empty có nghĩa “không có bản ghi”.

Chỉ dùng fallback khi giá trị đó **được nghiệp vụ cho phép** và caller có thể hiểu trạng thái degraded nếu cần. Ví dụ cache cũ chỉ chấp nhận được nếu hệ thống cho phép đọc stale; không được tùy tiện dùng nó cho thanh toán.

### 5.2. Mất nguyên nhân khi rethrow

```java
catch (Exception ex) {
    throw new RuntimeException("Operation failed");
}
```

Mất `cause`, khiến tầng ngoài không biết nguồn thất bại.

Mẫu tốt hơn ở **ranh giới cần dịch lỗi**:

```java
catch (IOException ex) {
    throw new DependencyUnavailableException("Storage unavailable", ex);
}
```

Đây là mảnh code cần exception domain `DependencyUnavailableException` tự định nghĩa. Constructor nhận `cause` để giữ mối liên hệ lỗi. Tuy vậy, **giữ cause vẫn chưa đủ** nếu mọi loại lỗi được bắt rồi ép thành một class không đúng ý nghĩa.

### 5.3. Log rồi ném lại ở mọi lớp

```java
catch (Exception ex) {
    logger.error("Operation failed", ex);
    throw ex;
}
```

Đây là mảnh code framework logging và cần chữ ký phù hợp với checked exception. Nếu caller cũng log, sẽ có nhiều sự kiện cho cùng một lỗi. Mỗi tầng chỉ nên log khi thực sự có **thông tin vận hành hoặc trách nhiệm quan sát riêng**; thông thường log tại boundary cuối cùng hoặc nơi trạng thái được quyết định.

## 6. Ví dụ Java 17+ độc lập, chạy được

Chương trình này minh họa cách **bắt các loại lỗi I/O có ngữ nghĩa khác nhau**, giữ cause, không che validation error, đồng thời cho thấy hệ quả của catch quá rộng và xử lý interruption.

Lưu file **`BroadCatchDemo.java`**:

```java
import java.io.FileNotFoundException;
import java.io.IOException;
import java.util.concurrent.CountDownLatch;

public class BroadCatchDemo {
    static final class OrderNotFoundException extends RuntimeException {
        OrderNotFoundException(String id, Throwable cause) {
            super("Order not found: " + id, cause);
        }
    }

    static final class DependencyUnavailableException extends RuntimeException {
        DependencyUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class Repository {
        String fetch(String id) throws IOException {
            if ("missing".equals(id)) {
                throw new FileNotFoundException("no row");
            }
            if ("offline".equals(id)) {
                throw new IOException("connection failed");
            }
            return "ORDER:" + id;
        }
    }

    static final class OrderService {
        private final Repository repository = new Repository();

        String load(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id must not be blank");
            }
            try {
                return repository.fetch(id);
            } catch (FileNotFoundException ex) {
                throw new OrderNotFoundException(id, ex);
            } catch (IOException ex) {
                throw new DependencyUnavailableException(
                        "Order repository unavailable", ex);
            }
        }
    }

    static String brokenFallback(OrderService service, String id) {
        try {
            return service.load(id);
        } catch (Exception ignored) {
            return "FAKE_SUCCESS";
        }
    }

    static void waitForWork(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException ex) {
            boolean clearedByAwait = !Thread.currentThread().isInterrupted();
            Thread.currentThread().interrupt();
            System.out.println("INTERRUPT: cleared=" + clearedByAwait
                    + " restored=" + Thread.currentThread().isInterrupted());
        }
    }

    public static void main(String[] args) {
        OrderService service = new OrderService();
        System.out.println("SUCCESS: " + service.load("42"));

        try {
            service.load("missing");
        } catch (OrderNotFoundException ex) {
            System.out.println("NOT_FOUND: cause="
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            service.load("offline");
        } catch (DependencyUnavailableException ex) {
            System.out.println("UNAVAILABLE: cause="
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            service.load("");
        } catch (IllegalArgumentException ex) {
            System.out.println("VALIDATION: "
                    + ex.getClass().getSimpleName());
        }

        System.out.println("BROAD_CATCH_BUG: "
                + brokenFallback(service, "offline"));

        Thread.currentThread().interrupt();
        waitForWork(new CountDownLatch(1));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 BroadCatchDemo.java
java BroadCatchDemo
```

Standard output đã kiểm chứng:

```text
SUCCESS: ORDER:42
NOT_FOUND: cause=FileNotFoundException
UNAVAILABLE: cause=IOException
VALIDATION: IllegalArgumentException
BROAD_CATCH_BUG: FAKE_SUCCESS
INTERRUPT: cleared=true restored=true
```

**Giải thích:**

1. `service.load("42")` thành công, trả kết quả có ý nghĩa.
2. `FileNotFoundException` được bắt **trước** `IOException` vì là subclass; service dịch thành `OrderNotFoundException` và giữ cause.
3. Các `IOException` còn lại được dịch thành `DependencyUnavailableException`. Caller có thể phân biệt lỗi dependency với not found.
4. Validation input rỗng diễn ra trước gọi repository; `IllegalArgumentException` không bị đổi nhầm thành lỗi dependency.
5. `brokenFallback("offline")` là **mã sai được đưa vào để đối chiếu**, trả `FAKE_SUCCESS` trong khi repository thực sự thất bại.
6. `CountDownLatch.await()` thấy luồng đã bị interrupt, ném `InterruptedException` và xóa cờ; handler đặt lại cờ và kết thúc công việc. Dòng cuối xác nhận `cleared=true restored=true`.
7. Các ID như `42`, `missing` là giả. Nếu ID thực liên quan dữ liệu cá nhân hoặc bí mật, không đưa nó vào exception message/log mặc định như demo đơn giản này.

Code dùng Java 17 không có thư viện ngoài, không truy cập DB hoặc mạng thật. Vì thế output có thứ tự xác định và không phụ thuộc thời gian scheduler.

## 7. Bắt lớp đủ cụ thể theo chính sách, không nhất thiết bắt lớp lá

“Bắt hẹp” không có nghĩa mỗi subclass phải có `catch` riêng. Nếu tất cả `IOException` từ một API có cùng cách xử lý, `catch (IOException)` hoàn toàn hợp lý:

```java
try {
    remoteClient.fetch();
} catch (IOException ex) {
    throw new DependencyUnavailableException("Remote dependency failed", ex);
}
```

Đây là mảnh code với `remoteClient` và exception domain đã định nghĩa. Nhưng nếu `FileNotFoundException` có nghĩa nghiệp vụ “tài nguyên không tồn tại” còn `SocketTimeoutException` có nghĩa “phụ thuộc chậm”, service có thể cần phân biệt.

Trong Java, thứ tự catch theo subclass trước superclass rất quan trọng:

```java
try {
    read();
} catch (FileNotFoundException ex) {
    handleMissing(ex);
} catch (IOException ex) {
    handleOtherIo(ex);
}
```

Mảnh code cần import `java.io.FileNotFoundException` và `java.io.IOException` cùng các phương thức ứng dụng. Đặt `catch (IOException)` trước `catch (FileNotFoundException)` sẽ gây lỗi compile vì nhánh subclass không thể tới.

Có thể dùng multi-catch với các kiểu **không có quan hệ subclass** nếu xử lý giống nhau:

```java
catch (SocketTimeoutException | ConnectException ex) {
    markTemporaryFailure(ex);
}
```

Đây là mảnh code cần import `java.net.SocketTimeoutException`, `java.net.ConnectException`, và định nghĩa `markTemporaryFailure`. Không viết `catch (Exception | IOException ex)` vì `IOException` nằm dưới `Exception`.

Một điểm quan trọng khác là **phạm vi try**: nếu bạn chỉ muốn biến lỗi I/O thành lỗi dependency, chỉ đặt phần gọi I/O vào try thay vì ôm cả validation, tính toán business, notification và cleanup.

## 8. Các tầng nên sở hữu loại lỗi nào?

| Tầng | Trách nhiệm chính | Hành động khi lỗi |
| --- | --- | --- |
| Input validation | Xác nhận tham số và schema | Báo lỗi tham số cụ thể; không giả mạo lỗi hệ thống |
| Repository/adapter | Kết nối database, filesystem, HTTP client | Giữ hoặc dịch lỗi dependency có cause |
| Service/use case | Quy tắc nghiệp vụ và trạng thái | Xử lý lỗi domain, quyết định retry/compensation khi được phép |
| Controller/API boundary | Mã HTTP/response an toàn | Mã lỗi công khai, correlation ID, fallback 500 cho bất ngờ |
| Worker/job runner | Quản lý vòng đời tác vụ | Phân biệt FAILED, CANCELLED, retryable; lưu trạng thái |
| Framework/global handler | Xử lý thất bại không dự kiến | Báo lỗi và giữ hệ thống ở trạng thái được phép |

Đây là bảng **định hướng**, không phải bắt buộc một kiến trúc phải có đủ các lớp. Điều cần đạt là mỗi lỗi có **một nơi chịu trách nhiệm xử lý**, các tầng còn lại không che hoặc nhân bản log vô ích.

Một câu hỏi code review rất hiệu quả: **nếu bỏ catch ở tầng này, có mất một hành động cần thiết hay không?** Nếu không mất gì ngoài một dòng “failed”, có thể bỏ catch.

## 9. Khi nào catch(Exception) có thể hợp lý?

Không phải mọi `catch (Exception)` đều là anti-pattern. Nó có thể phù hợp ở **boundary cuối**, với điều kiện các loại lỗi dự kiến đã được xử lý cụ thể, phần unexpected được ghi nhận là thất bại và không bị biến thành success.

### HTTP/controller boundary

```java
try {
    return handler.handle(request);
} catch (InvalidRequestException ex) {
    return badRequest();
} catch (UpstreamUnavailableException ex) {
    return serviceUnavailable();
} catch (Exception ex) {
    return internalServerError();
}
```

Đây là mảnh code khái niệm cần định nghĩa các exception, `handler` và response helper. Handler rộng cuối cùng chỉ giải quyết lỗi **không dự đoán được**: trả response an toàn, không phơi stack trace hay raw message ra client, và ghi nhận sự kiện ở nơi có trách nhiệm.

### Transaction owner

Một thành phần sở hữu transaction có thể cần bắt lỗi để **thử rollback** và giữ lỗi ban đầu. Nó không được kết luận “đã rollback” chỉ vì handler chạy, nhất là khi rollback cũng ném exception.

### Worker/job boundary

Job runner có thể bắt lỗi bất ngờ để cập nhật trạng thái FAILED, không cho một sự cố biến thành job SUCCESS. Nếu worker hỗ trợ cancellation, xử lý `InterruptedException` hoặc cancellation riêng trước khi dùng fallback chung.

### Adapter legacy

Một API bên ngoài chỉ khai báo `throws Exception` có thể được bọc **một lần** ở adapter với contract mới. Không sao chép catch đó xuyên mọi layer của ứng dụng.

**Tiêu chuẩn:** có chính sách rõ, không nuốt lỗi, không giữ tiến trình chạy “mù” sau lỗi và không làm mất thông tin cần cho caller.

## 10. `catch (Throwable)` nguy hiểm hơn vì bao gồm Error

`Error` có thể chỉ lỗi nghiêm trọng của JVM hoặc linkage. Khi nhận `OutOfMemoryError`, ngay cả logger, cấu trúc dữ liệu dự phòng hoặc logic retry có thể không còn đủ tài nguyên. `StackOverflowError` có thể xảy ra khi đệ quy vượt khả năng stack. `LinkageError` có thể liên quan đến bytecode/classpath không tương thích.

Anti-pattern:

```java
catch (Throwable error) {
    logger.warn("ignored", error);
    return defaultValue;
}
```

Đây là mảnh code **không khuyến nghị**. Nó giả định sau bất kỳ tình trạng lỗi nào, vẫn có thể in log, tạo fallback và tiếp tục phục vụ request đúng đắn.

Có **ranh giới đặc biệt** có lý do quan sát `Throwable`, như harness kiểm thử hoặc plugin-host cần ghi nhận trạng thái thất bại của module. Nhưng hành động thường là **báo thất bại, cách ly, hoặc rethrow theo chính sách**, không hứa phục hồi tất cả. Nếu chỉ muốn cleanup bất kể đường rời, `finally` và `try-with-resources` thường là công cụ thích hợp hơn.

Không biến `catch(Throwable)` thành lớp bảo hiểm mọi nơi. Nó không thể chống mất điện, bị kill process hoặc hết tài nguyên nghiêm trọng, và có thể tạo cảm giác an toàn sai.

## 11. `InterruptedException` bị nuốt bởi catch(Exception)

`InterruptedException` thường là tín hiệu một luồng đang chờ được yêu cầu dừng/hủy. Các API như `Thread.sleep`, `BlockingQueue.take`, `CountDownLatch.await` và `Future.get` có thể ném nó. Khi ném exception này, nhiều API **xóa interrupt flag** của luồng đang chờ.

Anti-pattern:

```java
while (true) {
    try {
        process(queue.take());
    } catch (Exception ex) {
        logger.warn("retrying", ex);
    }
}
```

Đây là mảnh code giả định `queue`, `process` và logger thuộc ứng dụng. Khi thread bị interrupt trong `take()`, exception bị catch chung; vòng lặp tiếp tục và có thể lại block như chưa từng được yêu cầu dừng.

Nếu một phương thức có thể khai báo `throws InterruptedException`, thường nên **truyền tiếp**:

```java
void consume(BlockingQueue<Job> queue) throws InterruptedException {
    process(queue.take());
}
```

Đây là mảnh code cần import `BlockingQueue`, định nghĩa `Job` và `process`.

Nếu nằm trong `Runnable.run()` không thể ném checked `InterruptedException`:

```java
@Override
public void run() {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            process(queue.take());
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    } finally {
        releaseResources();
    }
}
```

Đây là mảnh code trong class có queue và cleanup. **Khôi phục cờ + kết thúc đường thực thi** thích hợp hơn khôi phục rồi quay lại `while(true)`, vì thao tác chờ tiếp theo có thể bị interrupt ngay, gây vòng lặp nóng.

Tuy nhiên không bắt buộc restore cờ ở mọi tầng nếu `InterruptedException` đã được truyền tiếp đúng hợp đồng, hoặc một tầng **sở hữu toàn bộ giao thức hủy** đã xử lý dứt điểm tín hiệu.

## 12. Bắt RuntimeException quá rộng có thể che lỗi lập trình

`RuntimeException` có cả lỗi domain không checked lẫn lỗi lập trình như `NullPointerException`, `IndexOutOfBoundsException`. Đoạn:

```java
try {
    return calculateInvoice();
} catch (RuntimeException ex) {
    return BigDecimal.ZERO;
}
```

là mảnh code sai nếu `calculateInvoice` trả `BigDecimal` và một bug không được phép biến thành hóa đơn `0`; cần import `java.math.BigDecimal`.

Nếu trường hợp thiếu dữ liệu là hợp lệ, API nên biểu diễn nó theo contract, chẳng hạn `Optional.empty()` hoặc một result domain. Nếu xảy ra NPE bất ngờ, nên để lỗi tới boundary cuối để điều tra, không tạo dữ liệu tài chính sai.

Tương tự, một bug lập trình cần sửa tại nguồn, không được coi mọi runtime exception là sự cố mạng tạm thời để retry.

## 13. Cleanup đúng cơ chế thay vì catch vô nghĩa

Một lý do khiến nhiều người bắt rộng là sợ rò tài nguyên. Nhưng nếu tài nguyên triển khai `AutoCloseable`, Java đã có `try-with-resources`:

```java
try (InputStream in = Files.newInputStream(path)) {
    return in.read();
}
```

Đây là mảnh code trong method khai báo `throws IOException` và có biến `Path path`, cần import `java.io.InputStream` và `java.nio.file.Files`. Tài nguyên được đóng khi rời khối theo hợp đồng, kể cả khi đọc lỗi.

Với lock:

```java
lock.lock();
try {
    mutateSharedState();
} finally {
    lock.unlock();
}
```

Đây là mảnh code trong class có `lock` và `mutateSharedState()`. `finally` phù hợp để nhả lock mà không cần catch rộng. Lưu ý nhả lock **không rollback** những thay đổi trước exception.

Khi thân `try-with-resources` và `close()` cùng lỗi, Java thường giữ lỗi từ close trong `getSuppressed()` của exception chính. Nếu tự viết cleanup và cleanup ném, cần bảo toàn lỗi gốc. Không thêm `catch (Throwable)` chỉ để tự triển khai một cơ chế cleanup vốn đã có.

## 14. Transaction, rollback và trạng thái sau lỗi

Exception không tự rollback DB, file hoặc mạng. Ví dụ:

```java
try {
    debitAccount();   // Có thể đã commit.
    sendReceipt();    // Có thể lỗi sau commit.
    return true;
} catch (Exception ex) {
    return false;
}
```

Đây là mảnh anti-pattern trong method trả boolean có các hàm nghiệp vụ đã định nghĩa. Nếu `debitAccount` đã commit và `sendReceipt` ném, method trả `false` nhưng tiền **có thể đã trừ**. Caller retry toàn bộ quy trình có thể trừ thêm lần nữa.

Trong transaction owner, cần rõ:

1. Những thao tác nào thực sự thuộc **cùng transaction**?
2. Lỗi xảy ra trước hay sau commit?
3. Nếu `rollback()` cũng thất bại, trạng thái đã được xác minh chưa?
4. Nếu `commit()` mất phản hồi, có thể biết chắc DB đã/chưa commit không?
5. Tác dụng phụ ở hệ thống khác có được bù trừ hoặc đối chiếu riêng không?
6. Retry có idempotency và giới hạn phù hợp không?

Một catch rộng dùng để **thử rollback rồi rethrow** có thể hợp lý trong phạm vi transaction owner. Nhưng catch không tự bảo đảm “đã hoàn tác mọi hệ thống”. Nếu rollback ném lỗi, giữ lỗi ban đầu và thông tin rollback (ví dụ `addSuppressed`) cùng trạng thái chưa chắc chắn.

## 15. Future, CompletableFuture và lỗi bất đồng bộ

Một `catch(Exception)` quanh câu nộp task:

```java
try {
    CompletableFuture<Integer> future =
            CompletableFuture.supplyAsync(() -> compute());
} catch (Exception ex) {
    // Chỉ bắt lỗi đồng bộ ở luồng đang nộp.
}
```

Đây là mảnh code với `compute` đã định nghĩa. Nếu `compute` ném exception về sau ở worker, nó được ghi vào trạng thái future, **không tự lan vào catch quanh câu tạo future**.

Khi caller quan sát:

```java
try {
    int result = future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} catch (ExecutionException ex) {
    handleTaskFailure(ex.getCause());
}
```

Đây là mảnh trong method `void`, có `future`, `handleTaskFailure`, import `ExecutionException`. Phân biệt `InterruptedException` của **thread caller đang chờ** với `ExecutionException` có cause từ worker. `CancellationException` có nghĩa hủy; `get(timeout, unit)` còn có thể ném `TimeoutException`, không có nghĩa task đã dừng.

Với `CompletableFuture.join()`, lỗi thường được báo dưới dạng `CompletionException`. Dùng `exceptionally` hoặc `handle` để phục hồi chỉ khi fallback có ý nghĩa nghiệp vụ; nếu cứ `exceptionally(ex -> null)` ở mọi stage thì pipeline có thể hoàn tất “thành công” với dữ liệu không hợp lệ.

Một job scheduler cũng cần biết tác vụ FAILED hay CANCELLED; catch rộng rồi trả bình thường có thể làm framework đánh dấu job là SUCCESS và tiếp tục lịch sai chính sách.

## 16. Logging exception: ít điểm log, đủ bối cảnh, không lộ dữ liệu

Nếu mỗi tầng log rồi rethrow, dashboard có thể có mười cảnh báo cho một lỗi. Chọn **một điểm quan sát cuối** cho từng request/task khi có thể, cộng metric/ngữ cảnh riêng ở những nơi thực sự cần.

Một policy hữu ích:

- Domain/API error code ổn định cho caller.
- Operation name thuộc allowlist, request/correlation ID an toàn.
- Thông tin retry, timeout, dependency category khi phù hợp.
- Throwable cause giữ nội bộ để chẩn đoán nếu được phép.
- Không đưa password, token, cookies, raw request body hoặc dữ liệu cá nhân vào exception message/log.

Đừng trả `ex.getMessage()` hay `ex.toString()` trực tiếp về HTTP response; dependency có thể đã chèn URL, header hoặc thông tin bí mật vào message. Ngược lại, đừng xóa cause ở mọi tầng một cách mù quáng vì sẽ khó điều tra. Phải **phân biệt dữ liệu giữ trong exception và dữ liệu được phép xuất ra sink**.

Một fallback boundary có thể gửi response 500 an toàn và ghi mã sự kiện; controller không cần log lại toàn bộ exception đã được ghi đầy đủ ở một nơi khác.

## 17. Lỗi checked và khai báo throws Exception quá rộng

Một mẫu song hành với catch quá rộng là:

```java
public void process() throws Exception {
    repositoryCall();
}
```

Đây là mảnh code với `repositoryCall` đã định nghĩa. Nó có thể hợp lệ trong một vài test hay entrypoint ngắn, nhưng API công khai chỉ khai báo `Exception` khiến caller không biết nên chuẩn bị xử lý điều kiện nào, thường dẫn tới `catch(Exception)` tiếp tục lan rộng.

Ví dụ hợp đồng hẹp hơn:

```java
void readConfig(Path path) throws IOException {
    Files.readString(path);
}
```

Đây là mảnh code cần import `java.nio.file.Path`, `java.nio.file.Files` và `java.io.IOException`. Nó biểu thị nhóm lỗi I/O phù hợp. Không cần liệt kê mọi subclass trừ khi caller có chính sách đặc hiệu.

Nếu “không tìm thấy dữ liệu” là trường hợp bình thường, cân nhắc `Optional<T>` hoặc result domain thay vì ném rồi catch ở nhiều tầng. Nhưng không nên đồng nhất lỗi kết nối DB với `Optional.empty()` vì **không biết có dữ liệu** khác hoàn toàn **biết là không có dữ liệu**.

## 18. Retry không thể áp dụng cho mọi Exception

Vòng lặp này đặc biệt nguy hiểm:

```java
while (true) {
    try {
        return chargeCustomer();
    } catch (Exception ignored) {
        // Retry ngay, không giới hạn.
    }
}
```

Đây là **mảnh anti-pattern**, giả định method trả kết quả tương ứng và `chargeCustomer()` có tác dụng phụ. Nó có thể retry bug validation, làm cạn CPU, hoặc tạo giao dịch trùng nếu lệnh trước **đã commit nhưng phản hồi thất lạc**.

Retry có trách nhiệm phải biết:

- Loại lỗi nào thực sự tạm thời.
- Lệnh có idempotency key hay không.
- Kết quả sau timeout là thất bại chắc chắn hay chưa xác định.
- Ngân sách retry, timeout, backoff/jitter.
- Có tín hiệu `InterruptedException`/cancellation từ caller không.
- Có tầng khác đã retry sẵn hay không, tránh nhân số lần gọi.

Một phương thức catch rộng rồi retry ở mọi tầng có thể tạo *retry storm*. Bắt cụ thể theo chính sách giúp tránh điều đó.

## 19. Khi nào nên log và rethrow?

Không cần catch chỉ để:

```java
try {
    call();
} catch (IOException ex) {
    throw ex;
}
```

Đây là mảnh code trong method có `throws IOException`; bỏ catch không đổi hành vi cơ bản.

Catch rồi rethrow có giá trị khi:

1. Dịch lỗi ở ranh giới adapter sang exception domain, **giữ cause**.
2. Cập nhật trạng thái FAILED/CANCELLED mà tầng dưới không sở hữu.
3. Thử rollback ở transaction owner.
4. Thêm bối cảnh **không nhạy cảm** cần thiết, không chỉ viết “failed”.
5. Ghi metric có ý nghĩa tại một nơi duy nhất.
6. Bảo đảm cleanup đặc thù không thể thể hiện rõ hơn qua `finally`/`try-with-resources`.

Nếu handler có thể ném lỗi khác trong khi xử lý, cần quyết định bảo toàn cause/suppressed và trạng thái sau failure. Đừng tuyên bố đã phục hồi khi rollback hoặc cleanup chưa chắc thành công.

## 20. Test phát hiện catch rộng gây sai hành vi

Các test cần tiêm lỗi để xem không chỉ loại exception, mà còn **trạng thái và tác dụng phụ sau lỗi**.

| Tình huống | Kỳ vọng |
| --- | --- |
| Input không hợp lệ | Error validation phù hợp, không gọi repository |
| Dữ liệu không tồn tại | Contract not found rõ ràng, khác unavailable |
| Repository offline | Lỗi dependency được báo, không có success giả |
| Bug `NullPointerException` | Không bị biến thành `0`, `null` hoặc success |
| Blocking worker bị interrupt | Không nuốt tín hiệu, worker kết thúc theo policy |
| Future hoàn tất exceptionally | Caller lấy đúng `getCause()` |
| Transaction thất bại giữa các bước | Rollback đúng phạm vi hoặc báo chưa xác minh |
| Timeout/commit không rõ kết quả | Không retry mù gây tác dụng phụ trùng |
| Cleanup hoặc rollback cũng lỗi | Lỗi chính và thông tin lỗi phụ được bảo toàn |
| Logger gặp Throwable nhạy cảm | Client/log rộng quyền không lộ token hoặc PII |
| `Error` nghiêm trọng | Không có catch chung nuốt rồi cho hệ thống chạy như success |

Với `BroadCatchDemo`, test quan trọng là `service.load("missing")` và `service.load("offline")` khác loại domain nhưng đều giữ cause, validation rỗng vẫn đúng loại, còn `brokenFallback` phải bị đánh dấu **sai có chủ đích** khi trả `FAKE_SUCCESS`.

Mọi test có worker cần timeout và cleanup, không để process treo. Kiểm thử rollback phải xét side effect, không chỉ `assertThrows`.

## 21. Checklist code review thực dụng

1. Mỗi `catch` phải có **lý do xử lý ở tầng đó**.
2. Nếu chỉ rethrow y nguyên và không bổ sung hành động, thường nên bỏ.
3. Bắt nhóm exception đủ hẹp theo chính sách; subclass trước superclass.
4. Không bắt `Throwable` đại trà; không mặc định có thể phục hồi từ `Error`.
5. Không biến validation, dependency, cancellation và bug thành cùng một exception mơ hồ.
6. Khi chuyển loại lỗi, giữ cause và mã lỗi có ý nghĩa.
7. Không trả kết quả giả để che lỗi không được phép fallback.
8. Đừng nuốt `InterruptedException`; truyền tiếp hoặc restore và dừng đúng đường.
9. Dùng `try-with-resources`/`finally` cho cleanup, không catch rộng vô nghĩa.
10. Rollback phải theo transaction boundary; catch không tự hoàn tác thay đổi đã commit.
11. Chỉ retry khi lỗi và thao tác đáp ứng chính sách retry an toàn.
12. Tránh log trùng ở nhiều tầng; không tiết lộ secret/PII qua message và cause.
13. Với future/async, quan sát kết quả bất đồng bộ, không dựa vào catch lúc submit.
14. Boundary cuối có thể có fallback cho unexpected `Exception` nhưng vẫn đánh dấu fail, trả lỗi an toàn.
15. Kiểm thử cả lỗi dự kiến, bug bất ngờ, interrupt và trạng thái sau thất bại.

**Kết luận:** `catch (Exception)` và `catch (Throwable)` không phải lớp bảo hiểm có thể dán vào mọi phương thức. Bắt quá rộng ở mọi tầng làm mất phân loại, che bug, nuốt tín hiệu hủy, gây log trùng và biến failure thành success giả. Hãy bắt ở **tầng sở hữu hành động xử lý**, cho lỗi không xử lý được tiếp tục lan truyền, và dùng đúng cơ chế cleanup, rollback, reporting và retry.
