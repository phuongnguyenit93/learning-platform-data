# Log một lần hay nhiều lần khi xử lý exception trong Java?

## 1. Vì sao một exception có thể tạo ra nhiều dòng log?

Một lời gọi trong hệ thống Java thường đi qua nhiều tầng: controller → service → repository → thư viện hoặc dịch vụ bên ngoài. Khi một thao tác thất bại, exception có thể được ném từ tầng dưới, bắt để bổ sung ngữ cảnh ở tầng giữa, rồi tiếp tục được chuyển lên tầng xử lý ở ngoài.

Ví dụ, cơ sở dữ liệu không phản hồi, repository ném `SQLException`, service chuyển nó thành `OrderSaveException`, còn API trả lỗi HTTP 500. Nếu cả ba tầng đều ghi `ERROR` cùng một stack trace, người vận hành có thể thấy ba “lỗi” mặc dù thực tế chỉ có **một lần xử lý yêu cầu thất bại**.

```text
Repository: ERROR database unavailable      ← cùng sự cố
Service:    ERROR cannot save order ORD-7    ← cùng sự cố
Controller: ERROR request req-42 failed      ← cùng sự cố
```

Các dòng này là **tình huống minh họa**. Tác hại của việc log trùng không chỉ là tốn dung lượng: nó làm tăng nhiễu, gây cảnh báo lặp, khó đếm đúng số yêu cầu lỗi và khiến người đọc tưởng nhiều sự cố độc lập đã xảy ra.

**Quy tắc mặc định hữu ích: với mỗi lần thất bại logic, hãy chọn một nơi chịu trách nhiệm ghi bản ghi lỗi có đầy đủ ngữ cảnh và exception.** Các tầng trung gian nên truyền, chuyển đổi hoặc xử lý exception theo trách nhiệm của mình. Quy tắc này không cấm nhiều bản ghi khi có **nhiều sự kiện khác nhau** (mỗi lần retry, bước bù trừ, phục hồi, trạng thái nghiệp vụ); điều quan trọng là phân biệt *bản ghi trùng của cùng một lỗi* với *dấu mốc khác nhau trong quá trình xử lý*.

## 2. Phân biệt exception, sự kiện và lần thất bại logic

Ba khái niệm liên quan nhưng không đồng nhất:

- **Exception:** đối tượng báo điều kiện bất thường tại một điểm trong luồng thực thi. Một exception có thể đi qua nhiều tầng mà không trở thành nhiều sự cố.
- **Sự kiện log:** điều ứng dụng chủ động ghi nhận, ví dụ `payment_attempt_failed`, `retry_scheduled`, `order_request_failed` hoặc `recovery_succeeded`.
- **Lần thất bại logic:** đơn vị công việc mà ta muốn theo dõi, chẳng hạn một HTTP request, một job hoặc một lần xử lý message từ queue. Đơn vị này có thể có nhiều lần thử, nhiều exception nội bộ và kết quả cuối cùng.

Ví dụ:

```text
Request req-42
  ├─ attempt 1 → timeout → sẽ retry
  ├─ attempt 2 → timeout → sẽ retry
  └─ attempt 3 → thành công
Kết quả request: SUCCESS
```

Hai lần timeout là hai **sự kiện thử thất bại**, nhưng request **không thất bại cuối cùng**. Nếu mỗi lần retry đều được ghi `ERROR` với stack trace giống nhau, hệ thống có thể bị hiểu nhầm là gặp sự cố nghiêm trọng dù đã phục hồi bình thường.

Ngược lại:

```text
Request req-43
  ├─ attempt 1 → timeout → retry
  ├─ attempt 2 → timeout → retry
  └─ attempt 3 → timeout → hết retry
Kết quả request: FAILED
```

Ở tình huống thứ hai, có thể ghi các dấu mốc retry ở mức chi tiết phù hợp rồi ghi **một sự kiện thất bại cuối cùng** cùng exception gốc/cause chain. Trường hợp retry của các hệ thống quan trọng có thể cần một log riêng ở từng lần thử, nhưng mỗi log phải có lý do và ngữ cảnh rõ ràng.

## 3. Cách chọn nơi ghi lỗi: ai sở hữu quyết định cuối cùng?

Thường nên log exception **tại ranh giới nơi lỗi được xử lý hoặc xác định kết quả của công việc**. Ví dụ:

| Ranh giới | Hành động điển hình | Khi nào ghi exception? |
|---|---|---|
| Repository/adapter | Gọi DB, filesystem, HTTP, message broker | Thường ném tiếp hoặc chuyển sang exception có ngữ cảnh; tránh ghi lại cùng lỗi nếu phía trên sẽ log |
| Service | Áp dụng nghiệp vụ, retry, fallback | Ghi sự kiện retry/fallback nếu hữu ích; nếu không thể xử lý, truyền exception để bên ngoài ghi lỗi cuối |
| HTTP controller / exception handler | Quyết định HTTP response | Có thể ghi một lần lỗi request bất ngờ kèm requestId và exception, rồi tạo phản hồi an toàn |
| Scheduled job / background worker | Quyết định trạng thái job | Ghi một lần thất bại cuối cùng hoặc kết quả xử lý, kèm jobId |
| Message consumer | Xử lý message, chọn ack/nack/requeue | Ghi ở nơi quyết định trạng thái cuối của lần xử lý, với messageId/attempt |
| Handler xử lý và phục hồi tại chỗ | Bắt exception và thực sự tiếp tục với fallback | Có thể ghi một sự kiện phục hồi thích hợp, tùy mức quan trọng |

**Nơi ném exception chưa chắc là nơi tốt nhất để log nó.** Tầng thấp thường không biết đầy đủ requestId, tác động nghiệp vụ và liệu caller có fallback hay không. Tầng ngoài lại có thể không biết chi tiết lỗi nếu tầng giữa làm mất `cause`. Cách phối hợp thường tốt là: **tầng dưới giữ nguyên nguyên nhân; tầng ngoài ghi một bản lỗi giàu ngữ cảnh**.

Không áp dụng máy móc “luôn log ở controller”: chương trình CLI, batch, consumer, ứng dụng desktop và service chạy nền có ranh giới xử lý khác nhau. Hãy xác định **chủ thể chịu trách nhiệm về kết quả của đơn vị công việc**.

## 4. Anti-pattern: bắt, log rồi ném tiếp ở mọi tầng

Giả sử ứng dụng sử dụng SLF4J:

```java
// Repository: cùng một exception được ghi rồi ném tiếp
try {
    writeToDatabase(order);
} catch (SQLException error) {
    log.error("Database write failed", error);
    throw error;
}

// Service: lại ghi cùng sự cố rồi ném tiếp
try {
    repository.save(order);
} catch (SQLException error) {
    log.error("Cannot save order {}", order.id(), error);
    throw new OrderSaveException("Order save failed", error);
}

// API handler: lại ghi exception khi request thất bại
log.error("Request {} failed", requestId, error);
```

Đây là **ba đoạn minh họa thuộc những tầng khác nhau**, không phải một chương trình Java độc lập. Nếu tất cả chạy trên cùng đường lỗi, log sẽ lặp lại cùng nguyên nhân.

Vấn đề không nằm ở chỗ thông điệp trùng từng ký tự; thông điệp có thể khác nhau nhưng vẫn mô tả **cùng một thất bại logic**. Stack trace được ghi tại repository, service và API có thể giống nhau ở phần nguyên nhân gốc.

Cách sửa thường hợp lý hơn:

```java
// Repository: để exception tiếp tục đi lên; không log cùng lỗi.
writeToDatabase(order);

// Service: chuyển đổi kiểu lỗi để thể hiện nghiệp vụ, giữ cause.
try {
    repository.save(order);
} catch (SQLException error) {
    throw new OrderSaveException(
            "Cannot save order " + order.id(), error);
}

// API boundary: ghi đúng một lần khi đã biết request thất bại.
log.error("requestId={} event=order_save_failed orderId={}",
        requestId, order.id(), error);
```

**Lưu ý cú pháp:** đoạn trên giả định API SLF4J, các lớp `repository`, `OrderSaveException`, `order` và biến `error` tồn tại trong từng phạm vi đúng; đây là sơ đồ cách tổ chức code. Ví dụ chạy được bằng JUL nằm ở mục 7.

Sau khi chuyển `SQLException` thành `OrderSaveException`, cần dùng constructor lưu `cause`. Đừng ném `new OrderSaveException("Cannot save order")` rồi bỏ mất exception gốc. Khi log ở ranh giới, stack trace/cause chain còn đầy đủ để chẩn đoán.

### 4.1. Ba lựa chọn ở mỗi khối `catch`

Với một exception được bắt, hãy quyết định rõ một trong các hướng chính:

1. **Xử lý xong và tiếp tục:** ghi một sự kiện về fallback/phục hồi nếu thực sự cần. Không ném tiếp cùng lỗi.
2. **Không thể xử lý:** truyền exception lên hoặc chuyển thành loại exception phù hợp, **giữ cause**. Để tầng sở hữu kết quả ghi bản lỗi cuối cùng.
3. **Chuyển thành kết quả có chủ đích:** ví dụ trả một phản hồi lỗi nghiệp vụ đã dự kiến, hoặc đánh dấu job thất bại. Quyết định mức và nơi ghi log dựa trên tác động thực tế; không mặc định lỗi người dùng là `SEVERE`.

Chỉ “ghi log” **không đồng nghĩa với xử lý lỗi**. Nếu ứng dụng phải rollback, trả trạng thái thất bại, retry hoặc hủy tác vụ, những việc này vẫn cần được thực hiện.

## 5. Khi nào nên ghi nhiều bản log?

Có những trường hợp **nhiều log là đúng** vì chúng ghi nhận các *sự kiện thực sự khác nhau*:

### 5.1. Các lần thử lại (retry)

Các lần thử có `attempt` riêng. Một bản ghi `attempt_failed` hay `retry_scheduled` giúp biết hệ thống đang phục hồi. Quy tắc gợi ý:

- Retry dự kiến và diễn ra thường xuyên: có thể ghi ở mức `DEBUG`/`FINE` hoặc tổng hợp bằng metrics.
- Retry hiếm, ảnh hưởng tới độ trễ hoặc cho thấy phụ thuộc suy giảm: `WARN`/`WARNING` có thể phù hợp.
- Hết retry và yêu cầu/job cuối cùng thất bại: ghi một sự kiện lỗi cuối cùng kèm Throwable/cause chain ở ranh giới phù hợp.

Không có bảng ánh xạ level bắt buộc cho mọi ứng dụng. Nếu ghi một warning cho từng lần thử thì nên có `attempt`, `maxAttempts`, `dependency`, `requestId` để chứng minh đây là các lần thử riêng, thay vì nhiều bản ghi lỗi trùng lặp.

### 5.2. Fallback và phục hồi

Ví dụ gọi API thanh toán thất bại, hệ thống chuyển sang dự phòng:

```text
WARN  requestId=req-42 event=primary_provider_unavailable provider=A
INFO  requestId=req-42 event=fallback_succeeded provider=B
```

Đây là hai trạng thái khác nhau: phụ thuộc chính gặp sự cố, cơ chế dự phòng đã thành công. Nếu giao dịch cuối cùng vẫn thành công, không nên mặc nhiên ghi thêm `ERROR request failed`.

### 5.3. Bước bù trừ và rollback

Một thao tác có thể thất bại rồi kích hoạt hoàn tiền, hủy giữ kho hoặc bù trừ dữ liệu. Lỗi chính và **kết quả bù trừ** là hai sự kiện độc lập có ý nghĩa vận hành. Có thể cần log riêng cả hai; nếu bù trừ cũng thất bại, đó là **sự cố mới** với nguyên nhân và mức độ riêng.

### 5.4. Ranh giới dịch vụ và công việc khác nhau

Trong hệ thống phân tán, service A gọi service B và nhận lỗi. B có thể ghi rằng **yêu cầu tại B** thất bại; A có thể ghi rằng **nghiệp vụ tại A** thất bại. Hai service sở hữu hai đơn vị công việc khác nhau nên đôi khi cả hai log đều cần thiết. Hãy dùng `traceId`/`requestId`, lỗi có cấu trúc và chính sách tránh nhân bản stack trace vô ích.

“Log một lần” là quy tắc **thiết kế cho một đơn vị thất bại logic**, không phải một cam kết rằng toàn hệ thống phân tán sẽ chỉ có một bản ghi. Collector cũng có thể nhận trùng vì cơ chế chuyển tiếp hay gửi lại.

### 5.5. Audit và an ninh

Một sự kiện bảo mật hoặc nghiệp vụ bắt buộc phải ghi audit có thể cần bản ghi chuyên biệt bên cạnh diagnostic error log. Audit trail có yêu cầu riêng về tính toàn vẹn, quyền truy cập, thời hạn lưu và trách nhiệm pháp lý. Đừng dùng “chỉ log một lần” làm lý do bỏ bằng chứng audit đã được yêu cầu.

## 6. Khi nào KHÔNG nên ghi thêm?

### 6.1. Catch chỉ để thêm một câu rồi rethrow

```java
catch (IOException error) {
    log.error("Read config failed", error);
    throw error;
}
```

Nếu tầng trên chắc chắn sẽ ghi lỗi cuối cùng với đầy đủ context, dòng `log.error` thường là trùng. Thay vào đó, có thể để nguyên exception hoặc ném ngoại lệ chuyên biệt với `cause`. Nếu tầng này là điểm duy nhất sở hữu thông tin quan trọng (ví dụ đường dẫn tài nguyên), thêm thông tin vào loại ngoại lệ hoặc message an toàn để tầng ngoài nhìn thấy.

### 6.2. Ghi exception và gọi `printStackTrace()`

```java
catch (Exception error) {
    log.error("Operation failed", error);
    error.printStackTrace();
}
```

Với nhiều backend, cả logger và `printStackTrace()` đều xuất stack trace, có thể dẫn đến bản ghi trùng và mất tính cấu trúc. Hãy chọn một cơ chế ghi được cấu hình phù hợp với hệ thống logging; không tự in stack trace thêm theo thói quen.

### 6.3. Chỉ có một lỗi nhưng nhiều handler/appender cùng ghi

Không phải mọi dòng trùng đều do nhiều khối `catch`. Trong JUL, một record có thể đi tới handler gắn tại logger và các handler cha nếu `useParentHandlers` đang bật. Với Logback/Log4j 2, additivity hoặc nhiều appender tham chiếu cùng đích cũng có thể gây trùng.

Ví dụ: một lời gọi `LOG.log(Level.SEVERE, ..., error)` nhưng xuất hai lần trên console. Khi đó phải **kiểm tra cấu hình propagation, handlers, appenders và collector**, không vội xóa các thông điệp nghiệp vụ có giá trị.

### 6.4. Lỗi đã xử lý đúng như thiết kế

Ví dụ người dùng nhập sai email hoặc tìm tài nguyên không tồn tại như một kết quả bình thường của API. Có thể cần trả HTTP 400/404 và metrics, nhưng **không tự động coi mọi tình huống đó là một exception nghiêm trọng cần stack trace ở mức ERROR**. Mức log phải phản ánh mức độ bất thường và tác động vận hành.

## 7. Ví dụ Java 17+ chạy độc lập: log một lỗi cuối cùng, nhiều sự kiện khi retry

Ví dụ này dùng **`java.util.logging`** của JDK, không cần dependency bên ngoài. Có hai kịch bản:

1. Lưu đơn hàng thất bại trong tầng repository; tầng service **bọc exception và giữ nguyên cause**; chỉ lớp điều phối ghi lỗi cuối cùng.
2. Job gặp lỗi ở lần thử đầu, lập lịch thử lại và thành công ở lần hai; log **hai sự kiện có ý nghĩa khác nhau**, không tạo một `SEVERE` giả cho job đã phục hồi.

### 7.1. Mã nguồn

Tạo tệp `LogOnceOrManyDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogOnceOrManyDemo {
    private static final Logger LOG =
            Logger.getLogger(LogOnceOrManyDemo.class.getName());

    public static void main(String[] args) {
        configureLogger();
        processRequest();
        executeRetriedJob();
    }

    private static void configureLogger() {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String text = record.getLevel().getName()
                        + " " + formatMessage(record);

                Throwable error = record.getThrown();
                if (error != null) {
                    text += " | exception="
                            + error.getClass().getSimpleName()
                            + ":" + error.getMessage();

                    if (error.getCause() != null) {
                        Throwable cause = error.getCause();
                        text += " | cause="
                                + cause.getClass().getSimpleName()
                                + ":" + cause.getMessage();
                    }
                }
                return text + System.lineSeparator();
            }
        });
        LOG.addHandler(console);
    }

    private static void processRequest() {
        try {
            saveOrder("ORD-7");
        } catch (OrderSaveException error) {
            // Một lần log cuối cùng tại ranh giới xử lý request.
            LOG.log(Level.SEVERE,
                    "requestId=req-42 orderId=ORD-7 event=order_save_failed",
                    error);
        }
    }

    private static void saveOrder(String orderId) {
        try {
            simulateDatabaseWrite();
        } catch (IllegalStateException cause) {
            // Giữ cause và bổ sung ngữ cảnh; không log trùng.
            throw new OrderSaveException(
                    "cannot save " + orderId, cause);
        }
    }

    private static void simulateDatabaseWrite() {
        throw new IllegalStateException("database unavailable");
    }

    private static void executeRetriedJob() {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                performAttempt(attempt);
                LOG.info("jobId=job-9 event=job_completed attempt="
                        + attempt);
                return;
            } catch (IllegalStateException error) {
                if (attempt < 2) {
                    LOG.warning(
                            "jobId=job-9 event=retry_scheduled attempt="
                            + attempt + " reason=temporary_timeout");
                } else {
                    // Chỉ ghi SEVERE nếu tất cả lần thử đều thất bại.
                    LOG.log(Level.SEVERE,
                            "jobId=job-9 event=job_failed attempts="
                            + attempt, error);
                }
            }
        }
    }

    private static void performAttempt(int attempt) {
        if (attempt == 1) {
            throw new IllegalStateException("temporary timeout");
        }
    }

    private static final class OrderSaveException
            extends RuntimeException {
        private OrderSaveException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên** trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 LogOnceOrManyDemo.java
java LogOnceOrManyDemo
```

Kết quả chính xác theo formatter được cấu hình:

```text
SEVERE requestId=req-42 orderId=ORD-7 event=order_save_failed | exception=OrderSaveException:cannot save ORD-7 | cause=IllegalStateException:database unavailable
WARNING jobId=job-9 event=retry_scheduled attempt=1 reason=temporary_timeout
INFO jobId=job-9 event=job_completed attempt=2
```

**Lưu ý luồng:** `ConsoleHandler` của JUL ghi vào **stderr** theo mặc định, nên ví dụ không tạo stdout. Kết quả trên là ba dòng hiển thị trên console (stderr); nếu chuyển hướng hai luồng riêng, đọc stderr.

### 7.2. Vì sao kết quả đúng?

- `simulateDatabaseWrite()` ném `IllegalStateException`, nhưng phương thức này **không log**.
- `saveOrder(...)` bắt lỗi và ném `OrderSaveException` với `cause`, vẫn **không log**.
- `processRequest()` biết request đã thất bại nên ghi **một** sự kiện `order_save_failed` ở mức `SEVERE` với request ID và order ID.
- Formatter demo lấy `record.getThrown()` và hiển thị exception + cause trong một dòng. Vì đầu ra không có thời gian động hay stack trace nên có thể đối chiếu ổn định.
- `executeRetriedJob()` gặp một lần thử thất bại, ghi `WARNING retry_scheduled` rồi hoàn tất ở lần thứ hai, ghi `INFO job_completed`. Đây là **hai sự kiện khác nhau**. Không ghi `SEVERE job_failed` vì job đã thành công.
- Nếu thay đổi mô phỏng để cả hai lần thử đều thất bại, nhánh `else` sẽ ghi **một `SEVERE` cuối cùng**, không đánh dấu công việc thành công.

**Giới hạn của formatter demo:** nó chỉ trình bày loại exception, message và cause trực tiếp để stdout/stderr ổn định. Khi vận hành thật, cần formatter/backend có thể ghi **stack trace đầy đủ, nguyên nhân lồng nhau và các suppressed exceptions** khi phù hợp. Code demo minh họa *quyết định log ở tầng nào*, không phải cấu hình production đầy đủ.

## 8. Cách ghi exception đúng trong JUL, SLF4J và các backend

### 8.1. Java Util Logging (JUL)

Với JUL, để giữ exception cùng thông điệp, dùng overload nhận `Throwable`:

```java
LOG.log(Level.SEVERE, "event=order_save_failed", error);
```

Nếu dùng `LOG.severe(error.getMessage())`, ứng dụng chỉ truyền message, không truyền đối tượng `Throwable` cho logger. Formatter có thể không có stack trace/cause để xuất.

Nếu cần **cả tham số `{0}` và Throwable**, có thể tạo `LogRecord` có `parameters` và `thrown`:

```java
LogRecord record = new LogRecord(
        Level.SEVERE, "requestId={0} event=order_failed");
record.setParameters(new Object[]{"req-42"});
record.setThrown(error);
LOG.log(record);
```

Các đoạn trong mục này là **minh họa API**, giả định `LOG` và `error` đã được khai báo đúng phạm vi, không phải chương trình độc lập. Formatter cần dùng `formatMessage(record)` nếu muốn thay `{0}` và hỗ trợ `record.getThrown()` nếu cần exception.

### 8.2. SLF4J/Logback

Trong ứng dụng có SLF4J, cách thường gặp:

```java
log.error("requestId={} orderId={} event=order_save_failed",
        requestId, orderId, error);
```

Đối tượng `Throwable` ở vị trí cuối được API SLF4J xử lý như exception trong các overload parameterized logging thông dụng. Cần có provider/backend hoạt động và layout ghi Throwable; đừng giả định placeholder `{}` của SLF4J đồng nghĩa với `{0}` của JUL.

Ví dụ dưới đây chỉ ghi thông điệp lỗi, có thể mất stack trace:

```java
log.error("Save failed: {}", error.getMessage());
```

Nếu logger ở mức ERROR nhưng layout/encoder không xuất throwable, stack trace vẫn có thể thiếu dù lời gọi đã truyền đối tượng exception. Kiểm tra đồng thời **call site**, cấu hình backend và formatter.

### 8.3. Log4j 2

Log4j 2 cũng cung cấp overload ghi exception và pattern/layout riêng. Cách gắn `Throwable` có thể tùy loại `Message` và overload. Dùng API chính xác của phiên bản đang chạy, truyền exception đúng kiểu và kiểm tra output. Không sao chép máy móc cấu hình additivity hoặc throwable converter giữa JUL, Logback và Log4j 2.

### 8.4. Log một lần không có nghĩa là bỏ thông tin

Một bản ghi cuối cùng nên chứa **đủ ngữ cảnh**:

- Tên event ổn định: `event=order_save_failed`.
- Định danh công việc: `requestId`, `jobId`, `messageId` hoặc `traceId`.
- Mã nghiệp vụ không nhạy cảm: `orderId`, mã lỗi, thành phần liên quan.
- Loại exception, message phù hợp và stack trace/cause chain khi cần.
- Tác động: request thất bại, retry thành công, dữ liệu bị rollback hay tác vụ đang chờ xử lý.

**Không cần ghi từng dữ liệu ở mọi tầng.** Có thể truyền ngữ cảnh bằng exception chuyên biệt, cấu trúc kết quả, tracing hoặc MDC có kiểm soát. Logger tại ranh giới có trách nhiệm tập hợp thông tin rồi tạo bản ghi cần thiết.

## 9. Trường hợp exception được xử lý và phục hồi

Giả sử repository ném lỗi tạm thời nhưng service có thể dùng cache:

```java
try {
    return remoteCatalog.load(productId);
} catch (RemoteServiceException error) {
    log.warn("productId={} event=using_cached_catalog",
            productId);
    return catalogCache.get(productId);
}
```

Đoạn này là **minh họa**, không chạy độc lập; giả định cache hợp lệ và fallback được nghiệp vụ cho phép. Nó ghi dấu mốc rằng ứng dụng phải dùng cache; không tự ghi `ERROR` hay trả kết quả thất bại khi fallback thành công.

Nếu fallback lại ném exception, đó là **một thất bại mới hoặc bước mới trong cùng request** cần được xử lý. Tùy nghiệp vụ, có thể giữ cả nguyên nhân gốc và lỗi fallback trong cause/suppressed exceptions để không mất diễn biến. Không nên ghi cả hai lỗi ở mọi tầng chỉ để “chắc chắn có log”.

Cũng cần phân biệt **lỗi đã dự kiến trong luồng nghiệp vụ** với **exception kỹ thuật bất ngờ**. Ví dụ `ItemNotFoundException` có thể dẫn tới HTTP 404 bình thường, không cần stack trace SEVERE; ngược lại việc database mất kết nối thường cần được điều tra ở mức vận hành.

## 10. Khi có concurrency và xử lý bất đồng bộ

Trong ứng dụng đa luồng, “nơi xử lý cuối” không nhất thiết nằm trên cùng call stack với nơi phát sinh lỗi:

- Với `ExecutorService`/`Future`, lỗi trong task có thể được lưu trong `Future` và bộc lộ khi gọi `get()`. Cần chọn nơi quản lý task ghi lỗi và cập nhật trạng thái; tránh task log rồi caller lại log khi thấy `ExecutionException`.
- Với `CompletableFuture`, nếu có cả `exceptionally`, `whenComplete` và code gọi `join()` cùng log một failure, số bản ghi có thể tăng. Chỉ định rõ callback hoặc boundary chịu trách nhiệm về lỗi cuối cùng.
- Với scheduled job, thread uncaught exception handler hoặc framework có thể tự ghi lỗi. Khi ứng dụng thêm log riêng, hãy kiểm tra log mặc định để tránh ghi trùng.
- Với message consumer, retry/redelivery có thể khiến **cùng message** được xử lý lại. Ghi attempt ID và message ID, kết hợp idempotency và metrics, đừng suy từ số dòng log ra số message duy nhất.

Thông điệp `requestId`/`traceId` rất hữu ích khi nhiều luồng xen kẽ. MDC/thread context cần được truyền và xóa đúng khi dùng thread pool. Ghi log một lần trong mã nguồn cũng **không bảo đảm exactly-once delivery** trong hệ thống thu thập log.

## 11. Mức log, cảnh báo và hiệu năng

### 11.1. Chọn level theo kết quả

| Tình huống | Mức tham khảo | Vì sao |
|---|---|---|
| Request/job bất ngờ thất bại, không phục hồi | `ERROR` / JUL `SEVERE` | Cần điều tra nguyên nhân và tác động |
| Một attempt thất bại nhưng retry có thể giải quyết | `DEBUG`/`FINE` hoặc `WARN`/`WARNING` | Tùy tần suất và giá trị vận hành, ghi attempt context |
| Fallback hợp lệ đã được sử dụng | `INFO` hoặc `WARN`/`WARNING` | Thể hiện tình trạng suy giảm nhưng chưa chắc là thất bại cuối |
| Dữ liệu người dùng không hợp lệ theo quy tắc | `INFO`/`DEBUG` hoặc không ghi | Không nhất thiết là sự cố hệ thống |
| Sự cố bảo mật cần lưu dấu vết | Theo chính sách security/audit | Có thể cần kênh audit riêng với schema và retention riêng |

Không có level chuẩn áp dụng tự động cho mọi miền nghiệp vụ. Mức `SEVERE` của JUL gần về ý nghĩa với `ERROR` trong nhiều backend nhưng không cùng tên hay luôn tương đương trong mọi cấu hình.

### 11.2. Không dùng số dòng ERROR để suy số lỗi thật

Nếu một failure bị log ba lần, hệ thống giám sát đếm mỗi dòng sẽ báo số lỗi tăng gấp ba. Ngược lại, sampling hoặc lọc log có thể khiến số dòng **thấp hơn** số lỗi thực tế.

Khi đo error rate hay SLO, nên dùng **metrics** theo điểm đo rõ ràng (ví dụ một kết quả HTTP request hoặc một lần hoàn tất job), thay vì chỉ đếm số sự kiện `ERROR`. Logs cung cấp chi tiết để điều tra; traces liên kết các bước trên cùng request.

### 11.3. Không ghi stack trace cho mọi attempt

Stack trace dài tốn CPU, bộ nhớ, băng thông và dung lượng lưu trữ. Trong retry tần suất cao, có thể ghi một bản tổng kết kèm số lần thử, dependency, khoảng thời gian và exception cuối cùng; còn chi tiết mỗi attempt ở mức debug hoặc metrics có nhãn thích hợp.

Không cắt bỏ nguyên nhân kỹ thuật quan trọng chỉ vì muốn giảm log. Hãy giữ **bằng chứng đủ để điều tra sự cố thật**, đồng thời tránh nhân bản cùng stack trace. Khi dùng sampling, bảo đảm các cảnh báo quan trọng và audit bắt buộc không bị mất ngoài chính sách.

## 12. Bảo mật và khả năng điều tra

Truyền exception vào logger có thể vô tình đưa cả **exception message chứa dữ liệu nhạy cảm** lên log. Thông điệp từ HTTP client, JDBC hoặc thư viện khác đôi khi chứa URL query, định danh cá nhân hoặc một phần dữ liệu đầu vào. Không tự động log toàn bộ request body, access token, password, session cookie, SQL parameters hay response chứa thông tin cá nhân.

Các trường nghiệp vụ như `orderId` có thể giúp điều tra, nhưng cần xét chính sách phân quyền và thời hạn lưu. Với dữ liệu đầu vào không tin cậy, hãy xử lý newline/control characters để tránh log injection, và sử dụng JSON encoder bảo đảm escaping khi cần.

Nếu tự viết formatter, phải quyết định cách xuất `Throwable`: loại lỗi, message, stack trace, cause chain và suppressed exceptions. Một formatter chỉ xuất `error.getMessage()` có thể vừa làm lộ dữ liệu mà vẫn thiếu bằng chứng hữu ích.

## 13. Những lỗi phổ biến và cách nhận biết

| Dấu hiệu | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Một request lỗi có 3–4 stack trace gần giống | Nhiều tầng `catch` cùng log rồi rethrow | Chọn boundary ghi bản lỗi cuối, truyền cause ở tầng giữa |
| Một lời gọi logger xuất hai bản giống hệt | Handler cha/appenders hoặc collector duplicate | Kiểm tra propagation/additivity, destinations, pipeline |
| Không thấy lỗi sau khi service bọc exception | Wrapper không giữ `cause`, outer handler bỏ Throwable | Dùng constructor có cause, truyền Throwable, kiểm tra formatter |
| Log ghi ERROR nhưng API trả thành công | Retry/fallback đã phục hồi | Dùng mức và event thể hiện attempt/recovery |
| Retry xảy ra nhưng không thấy số lần thử | Thiếu `attempt`, `maxAttempts` hoặc metric | Ghi attempt context hoặc aggregate tại boundary |
| Một failure gây nhiều alert và error count sai | Alert đếm log nhân bản | Đếm metrics theo đơn vị công việc và giảm log trùng |
| Log lỗi nhưng task vẫn được coi thành công | Catch rồi chỉ ghi log và bỏ qua | Xử lý trạng thái, trả lỗi, rollback/retry/propagate phù hợp |
| Lỗi xuất hiện hai lần qua async callback | Nhiều nơi quan sát cùng `Future`/`CompletionStage` | Phân công nơi log và nơi chỉ propagate/trả kết quả |
| Không thể ghép log giữa service | Thiếu `requestId`/`traceId` | Truyền correlation ID đúng và dùng structured fields |

### Bài tập tự kiểm tra

Một yêu cầu thanh toán thực hiện ba lần thử: hai lần đầu timeout, lần thứ ba thành công. Ở tầng HTTP handler, lập trình viên còn log `ERROR` khi bắt được hai exception timeout đã được service xử lý.

Hãy xác định:

1. Kết quả cuối cùng của **request** là gì?
2. Có nên coi hai timeout là **hai request thất bại** không?
3. Nếu muốn biết từng attempt đã làm gì, nên thêm những trường nào?
4. Nên log lỗi cuối cùng ở đâu nếu cả ba lần thử đều thất bại?
5. Nếu service và handler đều phát cùng một stack trace, làm thế nào giảm bản ghi trùng mà vẫn giữ cause?

**Gợi ý kiểm tra:** request cuối cùng thành công, vì vậy không có failure cuối của request. Hai timeout là sự kiện thử thất bại, có thể theo dõi bằng `attempt` và `requestId` ở mức phù hợp. Nếu hết retry, nơi sở hữu kết quả request hoặc job ghi một bản lỗi cuối cùng với `Throwable`; tầng bên dưới truyền cause và ngữ cảnh.

## 14. Checklist ra quyết định cho từng exception

Trước khi thêm `logger.error(...)` hoặc `LOG.log(Level.SEVERE, ...)`, hãy kiểm tra:

1. **Lỗi đã được xử lý chưa?** Nếu chưa, tầng hiện tại có nên propagate hay wrap với cause thay vì log?
2. **Đây là lần thử hay thất bại cuối?** Nếu sẽ retry, đặt tên event và level phù hợp với attempt.
3. **Ai sở hữu kết quả của công việc?** HTTP boundary, consumer, job runner hay hàm có fallback?
4. **Đã có logger/framework khác ghi cùng failure chưa?** Kiểm tra catch/rethrow, exception handler, appenders và collector.
5. **Bản ghi này thêm thông tin mới không?** Nếu chỉ lặp lại stack trace, thường nên bỏ; nếu là sự kiện độc lập, ghi đúng ngữ cảnh riêng.
6. **Có giữ exception gốc không?** Truyền `Throwable`, cause chain và stack trace khi phù hợp.
7. **Có đủ định danh để liên kết không?** `requestId`, `jobId`, `attempt`, `traceId` và event name.
8. **Có ảnh hưởng bảo mật hay chi phí không?** Tránh dữ liệu nhạy cảm, flooding và cảnh báo sai.

**Nguyên tắc thực hành:** đối với **một lần thất bại logic**, thường ghi **một bản lỗi cuối cùng** ở nơi có đủ ngữ cảnh và chịu trách nhiệm xử lý kết quả; các tầng khác truyền hoặc xử lý exception. Khi có retry, fallback, rollback, bù trừ, audit hoặc các đơn vị công việc độc lập, **nhiều bản ghi có thể chính xác** vì chúng mô tả nhiều sự kiện khác nhau. Chất lượng log được đánh giá bằng khả năng hiểu diễn biến và điều tra nguyên nhân, không phải bằng số lần in cùng một stack trace.
