# Vừa ghi log vừa ném lại ở nhiều tầng: tránh nhân bản lỗi trong Java

> **Chủ đề:** Java Core → Exception → Sai lầm thường gặp. Bài này phân tích anti-pattern **log-and-rethrow**: một exception đi qua repository, service, controller hoặc worker nhưng mỗi tầng lại ghi lỗi rồi ném tiếp. Mục tiêu là thiết kế một **ranh giới ghi nhận lỗi có trách nhiệm**, giữ nguyên nguyên nhân và ngữ cảnh, tránh stack trace trùng lặp, nhưng vẫn không làm mất các sự kiện vận hành thực sự có giá trị.

## 1. Vấn đề: một thất bại có thể trở thành nhiều dòng ERROR

Giả sử việc lưu đơn hàng thất bại do database không sẵn sàng. Lỗi đi qua ba tầng:

~~~text
database call
   |
   v
Repository ── catch, ERROR, throw ──>
   |
   v
Service    ── catch, ERROR, throw ──>
   |
   v
Controller ── catch, ERROR, response
~~~

Nếu mỗi tầng đều ghi cùng stack trace, một thất bại thực tế có thể tạo ba sự kiện `ERROR`, nhiều bản stack trace và các thông báo chỉ khác nhau rất ít. Hậu quả không chỉ là tốn dung lượng log:

- **Đếm lỗi bị phóng đại:** dashboard nhóm theo log ERROR có thể trông như ba lỗi độc lập trong khi chỉ một request thất bại.
- **Khó xác định nơi xử lý cuối:** có log ở repository rồi service rồi controller, nhưng không rõ tầng nào đã quyết định retry, fallback hoặc trả lỗi ra bên ngoài.
- **Chi phí vận hành:** formatting stack trace, ghi log, gửi và lưu log tăng đáng kể nếu volume lớn.
- **Đánh mất mối quan hệ:** ba dòng không có correlation ID có thể bị hiểu nhầm là ba request.
- **Che dấu tín hiệu thật:** log lặp lại cạnh tranh với những lỗi độc lập, khiến cảnh báo ồn và khó phân loại.
- **Nguy cơ lộ dữ liệu:** cùng một message chứa thông tin nhạy cảm bị sao chép qua nhiều log sink.

Quy tắc thực hành: **khi chỉ chuyển exception lên tầng trên để nơi đó quyết định xử lý, thường không cần ghi ERROR và toàn bộ stack trace tại mỗi tầng trung gian**. Hãy bổ sung `cause`/ngữ cảnh và ghi log ở một ranh giới phù hợp với quyền sở hữu kết quả.

Quy tắc này không có nghĩa mỗi lỗi trên toàn bộ hệ thống chỉ được tạo đúng một dòng log. Một attempt retry hoặc một compensation có thể là **sự kiện riêng biệt** cần ghi; vấn đề là không nhân bản *cùng một failure event* mà không thêm thông tin mới.

## 2. Định nghĩa log-and-rethrow và ranh giới xử lý

**Log-and-rethrow** là mẫu:

~~~java
// Mã minh họa, log được cung cấp bởi thư viện logging của ứng dụng.
try {
    repository.save(order);
} catch (RuntimeException ex) {
    log.error("save failed", ex);
    throw ex;
}
~~~

Đoạn này giữ nguyên exception nên không làm mất `cause`, nhưng nếu tầng trên cũng bắt, ghi ERROR và ném tiếp, cùng một lỗi được ghi nhiều lần. Khi nhiều lớp cùng áp dụng mẫu này mặc định, lượng log tăng theo số tầng mà exception đi qua.

Phân biệt ba vai trò:

1. **Nơi phát hiện:** nơi API không thể hoàn tất và exception được tạo hoặc ném; có thể không biết request/business context đầy đủ.
2. **Nơi dịch ngữ nghĩa:** nơi đổi lỗi kỹ thuật thành exception miền nghiệp vụ/abstraction mới; có thể thêm operation, business ID và `cause` mà không cần log tại chỗ.
3. **Nơi quyết định kết quả:** tầng biên HTTP, consumer, scheduled job, CLI hoặc event loop, nơi quyết định retry, fallback, fail request hay stop job; thường là nơi hợp lý để ghi **failure cuối cùng**.

Nếu một tầng **thực sự xử lý** lỗi (ví dụ phục hồi bằng fallback và không ném tiếp), tầng ấy có thể ghi sự kiện kết quả riêng. Nếu tầng chỉ chuyển tiếp lỗi, đừng tự động ghi một bản ERROR đầy đủ.

## 3. Phản ví dụ: mỗi tầng log rồi lại throw

~~~java
// Trích đoạn các tầng của một hệ thống, chưa phải chương trình độc lập.
void saveInRepository(Order order) {
    try {
        jdbcWrite(order);
    } catch (SQLException ex) {
        log.error("Repository save failed", ex);
        throw new StorageException("write failed", ex);
    }
}

void placeOrder(Order order) {
    try {
        saveInRepository(order);
    } catch (StorageException ex) {
        log.error("Service placeOrder failed", ex);
        throw new OrderProcessingException("order failed", ex);
    }
}

void handleHttpRequest(Order order) {
    try {
        placeOrder(order);
    } catch (OrderProcessingException ex) {
        log.error("Request failed", ex);
        sendErrorResponse();
    }
}
~~~

Các kiểu `Order`, `StorageException`, `OrderProcessingException` và các hàm được giả định do ứng dụng định nghĩa; mã này chỉ minh họa anti-pattern. Trong flow trên:

- `Repository` log stack trace rồi chuyển thành exception lưu trữ.
- `Service` log chuỗi stack/cause đã được ghi rồi bọc lần nữa.
- `Controller` log cùng chuỗi lần thứ ba.
- Nếu cả ba dòng được tính là failure độc lập, tỷ lệ sự cố bị nhân lên.
- Thông điệp `"failed"` lặp lại không cung cấp correlation ID, error code hoặc trạng thái request.

Cần sửa hai vấn đề độc lập: **vị trí log** và **chất lượng context/cause**. Chỉ xóa log ở tầng thấp mà ném exception không có cause cũng chưa đủ để điều tra.

## 4. Java 17 chạy độc lập: ba log sai so với một log đúng

Ví dụ dùng `System.out` thay cho thư viện logging để có **stdout xác định**. Chương trình không mô phỏng chi phí stack trace, mà cho thấy rõ số lượng sự kiện ERROR và cách giữ cause qua các tầng.

Lưu thành tệp **`LogAndRethrowDemo.java`**:

~~~java
public class LogAndRethrowDemo {
    static final class StorageFailure extends RuntimeException {
        StorageFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static final class OrderFailure extends RuntimeException {
        private final String orderId;

        OrderFailure(String orderId, Throwable cause) {
            super("place order failed", cause);
            this.orderId = orderId;
        }

        String orderId() {
            return orderId;
        }

        String errorCode() {
            return "ORDER_WRITE_FAILED";
        }
    }

    static void writeToDatabase() {
        throw new IllegalStateException("connection lost");
    }

    static void badRepository() {
        try {
            writeToDatabase();
        } catch (IllegalStateException ex) {
            System.out.println("ERROR repository: " + ex.getMessage());
            throw new StorageFailure("save failed", ex);
        }
    }

    static void badService() {
        try {
            badRepository();
        } catch (StorageFailure ex) {
            System.out.println("ERROR service: " + ex.getMessage());
            throw new OrderFailure("order-42", ex);
        }
    }

    static void badBoundary() {
        try {
            badService();
        } catch (OrderFailure ex) {
            System.out.println("ERROR boundary: " + ex.getMessage());
            Throwable root = rootCause(ex);
            System.out.println("BAD root cause: "
                    + root.getClass().getSimpleName()
                    + ": " + root.getMessage());
        }
    }

    static void goodRepository() {
        try {
            writeToDatabase();
        } catch (IllegalStateException ex) {
            throw new StorageFailure("save failed", ex);
        }
    }

    static void goodService() {
        try {
            goodRepository();
        } catch (StorageFailure ex) {
            throw new OrderFailure("order-42", ex);
        }
    }

    static void goodBoundary() {
        try {
            goodService();
        } catch (OrderFailure ex) {
            System.out.println(
                    "ERROR event=place_order_failed operation=place_order"
                    + " requestId=req-8 orderId=" + ex.orderId()
                    + " code=" + ex.errorCode());

            Throwable root = rootCause(ex);
            System.out.println("GOOD root cause: "
                    + root.getClass().getSimpleName()
                    + ": " + root.getMessage());
        }
    }

    static Throwable rootCause(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }

    public static void main(String[] args) {
        badBoundary();
        goodBoundary();
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac LogAndRethrowDemo.java
java LogAndRethrowDemo
~~~

**Stdout chính xác:**

~~~text
ERROR repository: connection lost
ERROR service: save failed
ERROR boundary: place order failed
BAD root cause: IllegalStateException: connection lost
ERROR event=place_order_failed operation=place_order requestId=req-8 orderId=order-42 code=ORDER_WRITE_FAILED
GOOD root cause: IllegalStateException: connection lost
~~~

### Diễn giải

- **Nhánh bad:** repository, service và boundary mỗi nơi ghi một sự kiện ERROR; ba dòng ERROR đều bắt nguồn từ một thao tác ghi database bị lỗi.
- **Nhánh good:** repository chỉ chuyển lỗi `IllegalStateException` thành `StorageFailure` có cause; service chỉ chuyển thành `OrderFailure` có business ID và cause; boundary ghi **một sự kiện ERROR** đủ operation, request ID, order ID và error code.
- Hàm `rootCause` đi qua chuỗi cause để minh họa rằng thông tin `IllegalStateException("connection lost")` vẫn có thể được truy hồi sau hai lớp bọc. Trong chương trình thật, exception tree có thể còn `suppressed` và wrapper riêng; đừng mặc định “cause sâu nhất là toàn bộ sự thật”.
- Hai lời gọi bad/good trong `main` là **hai lượt minh họa độc lập**, không phải hai lần xử lý cùng một request production.
- Dòng `GOOD root cause` là dòng giải thích cho người học, **không phải ERROR log thứ hai**. Trong production nên log toàn bộ `Throwable` một lần tại boundary để backend giữ stack trace, cause chain và suppressed exceptions.

Việc sử dụng `System.out` trong ví dụ không phải khuyến nghị triển khai logging production. Chọn logger có level, structured fields và cơ chế thu thập tập trung thích hợp.

## 5. Thiết kế mới: ném có ngữ cảnh, ghi ở nơi chịu trách nhiệm

Mẫu thiết kế thường phù hợp với ứng dụng theo tầng:

~~~text
Repository
  -> bắt lỗi kỹ thuật khi cần dịch abstraction
  -> throw StorageException(cause)

Service
  -> bổ sung business operation hoặc error code
  -> throw OrderException(cause)

Boundary
  -> phân loại lỗi / quyết định HTTP status hoặc job outcome
  -> log một failure event có context + Throwable
  -> trả response / đánh dấu tác vụ lỗi / chuyển lỗi đúng hợp đồng
~~~

Lợi ích:

- Mỗi ranh giới có chức năng rõ: chuyển nghĩa, bổ sung ngữ cảnh hay xử lý kết quả.
- Không cần log khi không có hành động vận hành độc lập.
- Log final có thể chứa requestId, traceId, business ID, error code và cause.
- Một failure cuối cùng dễ được đếm trong metrics/alert.
- Unit test có thể kiểm tra loại exception và cause mà không cần assert log text ở mỗi tầng.

**Chọn owner log bằng quyền xử lý lỗi, không chỉ bằng tên lớp.** Ở HTTP server, global exception handler thường là nơi xử lý lỗi không được giải quyết. Ở một CLI nhỏ, `main` có thể là nơi in lỗi. Ở worker, tầng quản lý lifecycle task hoặc consumer xử lý message có thể là boundary. Trong thư viện dùng lại, thường nên ném exception cho ứng dụng chủ quyết định thay vì tự ý ghi ERROR mặc định.

## 6. Đặt log tại boundary nào?

| Vị trí | Thường nên làm gì | Có nên ghi ERROR? |
|---|---|---|
| DAO/repository | Giữ cause khi chuyển lỗi công nghệ thành lỗi lưu trữ | Không mặc định nếu caller còn xử lý |
| Application service | Thêm operation, business ID, error code; truyền tiếp | Không mặc định nếu không sở hữu outcome |
| REST controller/global handler | Map lỗi sang response, ghi failure event cuối | Thường hợp lý khi lỗi đủ nghiêm trọng |
| Message consumer | Quyết định ack/retry/dead-letter; log outcome | Hợp lý nếu nó thực sự sở hữu xử lý message |
| Scheduled job boundary | Quyết định job failed, retry hoặc stop | Hợp lý cho failure cuối cùng |
| Background CompletableFuture | Giữ exceptional completion; chủ nhận kết quả quan sát | Chỉ log độc lập nếu kết quả có thể không có consumer |
| Low-level shared library | Throw có ngữ nghĩa, tài liệu hóa cause | Tránh spam/error log ở mọi caller |
| Retry attempt handler | Có thể ghi attempt event, metrics, backoff | WARN/DEBUG/metrics khi chưa phải failure cuối |

**Không áp đặt một boundary duy nhất cho toàn hệ thống phân tán.** Service A có thể log một request đến A đã lỗi và service B cũng log yêu cầu tương ứng vào B, vì chúng là hai đơn vị triển khai/owner khác nhau. Cần `traceId`, `spanId` và correlation ID để nối quan hệ, nhưng không phải mọi log từ nhiều service đều là nhân bản sai. Vấn đề là cùng một tầng hoặc cùng một luồng điều khiển local ném đi qua nhiều lớp mà mỗi lớp phát bản lỗi không có ý nghĩa mới.

## 7. Bảo toàn cause và loại exception

Loại bỏ log-and-rethrow ở mọi tầng **không có nghĩa bỏ nguyên nhân lỗi**. Repository có thể dịch lỗi kỹ thuật sang exception phù hợp hơn với tầng storage:

~~~java
try {
    jdbcWrite(order);
} catch (java.sql.SQLException original) {
    throw new OrderStorageException("order persistence failed", original);
}
~~~

Đây là mảnh minh họa; `OrderStorageException` cần constructor `(String, Throwable)` và `jdbcWrite` phải được khai báo. Nếu `SQLException` đã đúng hợp đồng, để nó lan truyền hoặc `throw original;` cũng phù hợp. Không tạo nhiều wrapper `RuntimeException("failed", error)` qua các tầng khi chúng không thêm ngữ nghĩa.

Điểm chính của bài **log ownership** là mỗi tầng giữ cause và cung cấp ngữ cảnh cần thiết, nhưng không ghi cùng một stack trace ở repository, service và controller nếu chỉ xử lý một thất bại. Bài về cause giải thích riêng cách tạo, bảo toàn và duyệt chuỗi ngoại lệ.

## 8. Thêm ngữ cảnh đúng nơi, tránh message chung chung

Một bản log final nên giúp trả lời: **thao tác gì**, **request/task nào**, **business entity nào**, **dependency nào**, **lỗi gì**.

~~~json
{
  "level": "ERROR",
  "event": "order_persist_failed",
  "operation": "place_order",
  "requestId": "req-8",
  "orderId": "order-42",
  "errorCode": "ORDER_WRITE_FAILED",
  "dependency": "orders-db",
  "exceptionType": "OrderFailure",
  "causeType": "IllegalStateException"
}
~~~

Đây là **schema minh họa**, không phải log sinh bởi ví dụ Java. Trong production, structured logger có thể ghi các field này riêng và đính kèm `Throwable` để giữ stack trace/cause. Tránh chỉ nối text thành một message không thể truy vấn theo field.

Đối chiếu các ID:

- `requestId`: tìm tất cả sự kiện trong một request cụ thể.
- `traceId`: nối hành trình qua các dịch vụ khi có distributed tracing.
- `orderId`: truy ngược các thao tác trên một đơn hàng; không thay thế request ID.
- `jobRunId`/`messageId`: cần cho worker, queue, batch.
- `attempt`: phân biệt một lần retry với kết quả cuối.
- `errorCode`: nhóm lỗi ổn định, không phải ID ngẫu nhiên.

**Giữ ngữ cảnh xuyên tầng mà không phải ghi nhiều lần.** Có thể truyền một immutable context object hoặc gắn các trường typed vào exception miền nghiệp vụ. MDC của logging framework tiện dụng nhưng cần cleanup và context propagation qua thread pool; nó không tự truyền qua mọi `CompletableFuture` hoặc executor.

## 9. Khi nào log trung gian vẫn đúng?

Không có luật tuyệt đối “chỉ log một lần”. Một log trung gian có thể đúng nếu nó mô tả **sự kiện vận hành riêng**:

### 9.1. Retry attempt có ý nghĩa

~~~text
WARN  event=dependency_attempt_failed operation=save_order attempt=1 willRetry=true
WARN  event=dependency_attempt_failed operation=save_order attempt=2 willRetry=true
ERROR event=order_save_failed operation=save_order attempts=3 final=true
~~~

Nếu application có hai lần lỗi tạm thời rồi lần cuối thất bại, các attempt là sự kiện tách biệt giúp phân tích backoff/circuit breaker. Tuy nhiên không cần ba stack trace giống hệt: có thể log thông tin nhẹ ở mức WARN/DEBUG, metrics theo attempt, và ghi stack/cause đầy đủ cho final failure. Nếu retry cuối thành công, cần ghi **outcome thành công** và không đếm các attempt tạm thời là request failure cuối.

### 9.2. Compensation hoặc rollback thất bại

Ví dụ chuyển tiền gây lỗi và bước bù/rollback cũng lỗi. Đây là **hai thất bại khác nhau**, không phải hai lần ghi lại một exception. Log event riêng cho compensation failure có thể rất quan trọng vì nó thay đổi trạng thái nghiệp vụ.

### 9.3. Lỗi được xử lý cục bộ

Tầng thấp có thể bắt lỗi provider A, dùng fallback provider B và thành công. Nó không ném cùng lỗi lên trên; một sự kiện `fallback_used` hoặc metrics là hợp lý khi vận hành cần biết. Không tự động dùng ERROR nếu fallback là chiến lược dự kiến và người dùng không bị ảnh hưởng.

### 9.4. Ranh giới quyền sở hữu khác nhau

Một microservice gọi service khác có thể log lỗi outbound dependency; service nhận request cũng log failure inbound ở phạm vi riêng. Mỗi sự kiện nên có message/operation rõ ràng, trace context và tránh trùng `eventId` hoặc gọi một lỗi thành ba incident độc lập.

**Tiêu chí:** log trung gian có trả lời câu hỏi mới mà bản final không trả lời được hay không? Nếu chỉ ghi `"failed"` + cùng stack trace, thường không đáng ghi.

## 10. Đừng biến mọi exception thành ERROR

Mức log phải dựa vào **tính kỳ vọng và ảnh hưởng thực**, không chỉ vào `catch` có mặt:

| Tình huống | Mức hợp lý thường cân nhắc | Ghi chú |
|---|---|---|
| Input client không hợp lệ, trả response 400 | INFO/WARN hoặc chỉ metrics | Có thể là flow dự kiến, tránh flood |
| Record đã được xử lý (idempotency) | DEBUG/INFO | Không nhất thiết là lỗi |
| Retry tạm thời, vẫn còn cơ hội phục hồi | WARN/DEBUG hoặc metrics | `attempt` và `willRetry` có giá trị |
| Dependency failure cuối, request không thành công | ERROR | Log final một lần đủ context |
| User hủy thao tác có chủ đích | DEBUG/INFO | `CancellationException` không nhất thiết sự cố |
| Vi phạm invariant hoặc coding bug | ERROR | Bảo toàn stack trace/cause |
| Timeout sau khi task có thể đã commit | WARN/ERROR theo tác động | Không suy đoán đã rollback |

Nếu logging quá rộng khiến error alert đếm mọi invalid input hoặc cancellation, nhóm vận hành có thể mất niềm tin vào dashboard. Ngược lại, không giảm mức nghiêm trọng của lỗi mất dữ liệu chỉ vì nó được bắt rồi retry một lần.

## 11. Lỗi log rồi ném lại trong vòng lặp hoặc batch

Một worker xử lý 100.000 bản ghi có thể gặp dữ liệu sai thường xuyên. Nếu mỗi record lỗi bị log stack trace ở tầng parse, tầng validate và tầng batch, khối lượng log tăng phi tuyến theo chuỗi xử lý lỗi.

Không nên:

~~~java
// Mã minh họa: parse, validate, batch xử lý cùng một lỗi.
try {
    processRecord(record);
} catch (ValidationException ex) {
    log.error("record error", ex);
    throw ex;
}
~~~

Nếu record invalid là kết quả dự kiến, có thể dùng một `ValidationResult` hoặc tập hợp lỗi theo mã để phục vụ người dùng, không cần exception/stack trace cho mọi bản ghi. Nếu một record lỗi khiến toàn batch thất bại, boundary batch có thể log `batchId`, `recordId`, `errorCode` và số lượng phần tử đã xử lý.

**Hiệu năng không phải lý do duy nhất:** triage được cải thiện khi log phản ánh “một batch thất bại” và những record liên quan, thay vì hàng chục nghìn dòng `ERROR` thiếu correlation.

## 12. Log-and-rethrow trong CompletableFuture và ExecutorService

Với công việc bất đồng bộ, một nguồn trùng log phổ biến:

~~~java
// Trích đoạn, serviceAsync trả CompletableFuture và log có sẵn.
CompletableFuture<String> stage =
        serviceAsync().whenComplete((value, error) -> {
            if (error != null) {
                log.error("async failed", error);
            }
        });

// Sau đó boundary vẫn gọi stage.join() và log cùng lỗi lần nữa.
~~~

`whenComplete` chủ yếu phục vụ **quan sát**, không mặc định chuyển lỗi thành kết quả thành công. Nếu upstream hoàn tất bất thường, stage phía sau thường cũng hoàn tất bất thường; boundary gọi `join()` có thể bắt `CompletionException` và log lần hai. Vì vậy:

- Nếu boundary chắc chắn nhận và xử lý kết quả, ưu tiên để pipeline truyền failure rồi log ở boundary.
- Nếu tác vụ hoàn toàn *fire-and-forget*, không có caller tiêu thụ Future, cần một **điểm giám sát lỗi có trách nhiệm** trong worker hoặc handler kết quả. Đừng dùng khái niệm “log ở cuối” khi thực sự không có ai quan sát cuối.
- `ExecutorService.submit` có thể lưu ngoại lệ trong `Future`; nếu không ai gọi `get()` hoặc kiểm tra future, lỗi có thể không được báo cho ứng dụng. Cần thiết kế owner của future/monitoring.
- `Thread.UncaughtExceptionHandler` giúp ghi nhận lỗi chưa bắt của thread trần, nhưng không thay thế cơ chế lỗi của `FutureTask` hoặc pipeline.
- Khi callback `whenComplete` còn làm thêm việc có thể ném exception, stage mới có thể mang lỗi khác; hãy xem API semantics trước khi đặt logging side effect ở đây.

### Bóc wrapper đúng mức

~~~java
// Mã minh họa, một phương thức có CompletableFuture<String> future.
try {
    String value = future.join();
    consume(value);
} catch (java.util.concurrent.CancellationException ex) {
    handleCancellation(ex);
} catch (java.util.concurrent.CompletionException ex) {
    Throwable cause = ex.getCause();
    handleFailure(cause == null ? ex : cause);
}
~~~

`consume`, `handleCancellation` và `handleFailure` là các hàm ứng dụng cần định nghĩa; đoạn này không độc lập. Không log cả `CompletionException` và `cause` thành **hai sự kiện ERROR** chỉ vì có hai object exception liên quan. Truyền đầy đủ `Throwable` có cause cho logger và thêm context tại ranh giới.

Với `Future.get()`, lỗi computation thường đi qua `ExecutionException`; `InterruptedException` báo luồng **đang chờ** bị ngắt, không phải lỗi nghiệp vụ từ task. Đừng bắt rộng rồi log mỗi exception như cùng một nguyên nhân.

## 13. Không để thao tác logging che exception gốc

Trong hầu hết trường hợp, logger được thiết kế để hoạt động ổn định, nhưng các thao tác phụ như serialize object, tính toán argument, gọi `toString()`, enrich context hoặc gửi sang external sink **có thể lỗi hoặc bị chặn**. Ví dụ xấu:

~~~java
// Minh họa; formatter và auditSink là các phụ thuộc của ứng dụng.
catch (RuntimeException original) {
    String payload = formatter.format(hugeMutableRequest);
    auditSink.send(payload); // Nếu ném, original có thể bị che.
    throw original;
}
~~~

Ở đây nếu `formatter` hoặc `auditSink` thất bại, có thể không bao giờ chạy `throw original;`. Nếu việc gửi audit là trách nhiệm nghiệp vụ bắt buộc, cần hợp đồng rõ ràng về **hai lỗi độc lập** và chính sách transaction/outbox; không được giả định logging không thể ảnh hưởng luồng điều khiển.

Cách tiếp cận:

- Tránh đưa computation phức tạp hoặc access dữ liệu mutable lớn vào lập luận log.
- Dùng structured fields tối thiểu, dữ liệu đã được xác thực và có ranh giới nhạy cảm.
- Với logger chuẩn có API tham số, truyền Throwable cho backend để giữ cause/stack trace.
- Không nuốt `InterruptedException` khi chờ gửi log; nếu không thể truyền tiếp, cân nhắc khôi phục interrupt flag và kết thúc theo chính sách.
- Nếu phải bắt một lỗi phát sinh trong cleanup liên quan, bảo toàn exception gốc và thông tin secondary failure (`addSuppressed` khi phù hợp) thay vì âm thầm thay thế.
- Tránh `System.out.println` làm cơ chế quản trị lỗi production duy nhất vì thiếu level, cấu trúc và luồng thu thập đáng tin.

## 14. Logger nhiều cấp với thư viện phổ biến

SLF4J, Log4j hoặc `java.util.logging` là các lựa chọn có hợp đồng API riêng. Ví dụ SLF4J (cần dependency và logging backend, **không phải chương trình JDK độc lập**):

~~~java
// log: org.slf4j.Logger; context và ex đã có trong scope.
log.error(
        "event=order_write_failed operation={} requestId={} orderId={}",
        context.operation(), context.requestId(), context.orderId(), ex);
~~~

Khi dùng SLF4J, cần kiểm tra overload/cách xử lý `Throwable` ở phiên bản cụ thể để đảm bảo argument cuối là exception được log làm stack trace, không chỉ là giá trị format. Nếu backend hỗ trợ structured key-value pairs, ưu tiên xuất field riêng để query thay vì nối một message dài.

### MDC và async context

Các framework logging có thể cung cấp MDC để đưa request/correlation ID vào mỗi sự kiện trong thread hiện tại. Nhưng:

- `ThreadLocal`/MDC không tự truyền sang mọi executor hoặc stage `CompletableFuture`.
- Thread pool tái sử dụng thread; context không được dọn trong `finally` có thể làm request B xuất log mang ID request A.
- MDC là **cách làm giàu log**, không phải nơi duy nhất lưu thông tin nghiệp vụ cần thiết cho exception contract.
- Nếu cần log tại boundary async, truyền context bất biến vào task hoặc dùng context propagation do framework hỗ trợ.

Không sửa yêu cầu “log một lần ở boundary” bằng cách bắt/log ở từng tầng chỉ vì tầng đó là nơi cuối cùng còn thấy requestId. Hãy thiết kế đường truyền context trước.

## 15. Bảo mật và tính ổn định của ngữ cảnh log

Ghi log ít lần hơn không giúp gì nếu mỗi log vẫn chứa secret. Những thứ **không nên đưa nguyên văn** vào exception message hoặc logging fields nếu không có cơ sở và bảo vệ rõ:

- Mật khẩu, API key, access token, refresh token, cookie, authorization header.
- Thông tin thẻ thanh toán đầy đủ hoặc mã bí mật xác minh.
- Toàn bộ request/response body, dữ liệu cá nhân, thông tin sức khỏe nếu không cần thiết.
- Connection URL chứa credential, SQL với literal nhạy cảm, các cấu trúc `toString()` có thể lộ secret.
- IDs do bên ngoài gửi mà chưa được kiểm tra độ dài, ký tự điều khiển hoặc nguy cơ log injection.

Ưu tiên `requestId`, `traceId`, `operation`, `errorCode`, `dependency` và business ID được cho phép ghi. Validation các ID từ client: giới hạn độ dài, character set, trim/control characters, chống giả dòng log và phân biệt namespace. Log có thể bị copy sang hệ thống khác với quyền truy cập rộng hơn, nên áp dụng retention và access control thích hợp.

Một `orderId` có thể liên kết tới người dùng khi kết hợp dữ liệu khác; không đồng nhất “ID” với “không nhạy cảm”.

## 16. Stack trace, cause và suppressed exceptions: ghi thế nào đủ?

Java `Throwable` lưu các thông tin hữu ích:

- **Type:** lớp exception.
- **Message:** mô tả tình huống, không nhất thiết là mã lỗi ổn định.
- **Stack trace:** những frame tại điểm ném/tạo theo semantics của Throwable.
- **Cause:** nguyên nhân được bọc bằng `Throwable.getCause()`.
- **Suppressed exceptions:** thường xuất hiện khi xử lý tài nguyên trong `try-with-resources` hoặc khi ứng dụng dùng `addSuppressed`.

Khi một tầng chỉ log `ex.getMessage()` rồi throw, bản log của tầng đó có thể không chứa đủ cause/stack, trong khi tầng cuối có thể nhận chuỗi lỗi hoàn chỉnh. Mục tiêu là **một sự kiện chẩn đoán đầy đủ**, không phải mỗi tầng một phần thông tin rời rạc cần ghép bằng tay.

Trong `try-with-resources`, lỗi đóng tài nguyên có thể bị đưa vào `getSuppressed()` của exception chính. Nếu bạn chỉ log root cause bằng `rootCause(ex).getMessage()`, thông tin cleanup có thể bị mất. Trong production, truyền chính object `Throwable` tới logger để backend có cơ hội hiển thị cả cấu trúc liên quan.

**Đừng chuyển mọi throwable về exception gốc sâu nhất rồi vứt các lớp wrapper.** Wrapper có thể chứa ID, error code và ý nghĩa abstraction. Root cause là một góc nhìn, không thay thế toàn bộ exception chain.

## 17. Giám sát và thống kê: một log không phải một failure count

Nhiều dashboard đếm số ERROR logs như thể đó là số request lỗi. Khi log-and-rethrow nhiều tầng, cách đếm này thường sai.

Chọn số liệu có ngữ nghĩa:

- `requests_total{status="failed",operation=...}`: đếm **request** đã có outcome thất bại.
- `job_runs_total{outcome="failed"}`: đếm một lần chạy job thất bại.
- `retry_attempts_total{dependency=...,result=...}`: đếm nỗ lực retry, không lẫn với failure cuối.
- `exceptions_observed_total` nếu có: phản ánh sự kiện exception được ghi nhận, không tự gán nghĩa bằng số giao dịch thất bại.

Đây là **tên metric minh họa**, không phải một schema tiêu chuẩn bắt buộc. Với metrics, đừng gắn `requestId` hoặc `orderId` làm label: cardinality rất lớn. ID cụ thể phù hợp hơn trong logs và traces; metric theo operation/errorCode/dependency giúp tổng hợp.

Khi log ERROR bị giảm từ ba còn một, không có nghĩa reliability tự tốt lên ba lần. **Đã giảm trùng log**, không phải giảm số exception thật. Tách riêng đánh giá observability và quality của code xử lý lỗi.

## 18. Kiểm thử log ownership và ngoại lệ

Một bộ test tốt xác nhận cả hành vi chương trình lẫn chiến lược ghi nhận:

| Tình huống | Điều cần assert |
|---|---|
| Repository ném lỗi kỹ thuật | Service nhận cause; không in ERROR trùng ở repository |
| Service bọc lỗi domain | Lớp wrapper có đúng error code/ID; cause không mất |
| Boundary xử lý failure cuối | Một failure event có operation/requestId/businessId và Throwable |
| Retry rồi thành công | Outcome cuối không bị tính failed; attempt metrics riêng |
| Retry hết lần | Failure cuối log một lần; attempt metadata đủ để điều tra |
| Fallback xử lý được lỗi | Không có error cuối nếu hợp đồng coi recovery là thành công |
| CompletableFuture thất bại | Có owner nhận exceptional completion, không mất lỗi/nhân log |
| Cancellation/interrupt | Không vô tình ghi ERROR cho hủy hợp lệ; tín hiệu interrupt được xử lý |
| Lỗi trong cleanup | Exception gốc còn, lỗi phụ được liên kết hoặc thông báo hợp lý |
| Hai request trên một thread pool | MDC/context không bị rò chéo request |
| Exception chứa thông tin nhạy cảm | Log/response không làm lộ dữ liệu ngoài chính sách |
| Logging backend thất bại | Chính sách ứng dụng không âm thầm làm mất thông tin lỗi chính |

Các unit test của ứng dụng có thể dùng test appender hoặc in-memory logger để **đếm đúng log event theo mã/tên**, không chỉ so khớp text. Đồng thời `assertThrows` và kiểm tra `getCause()`/error code cho các lớp chuyển đổi exception. Tách test chiến lược logging khỏi test hành vi xử lý request để tránh phụ thuộc chi tiết format của backend.

**Kiểm tra lỗi trên cả luồng async và caller:** nếu một callback đã log rồi boundary `join()` cũng log, test cần thấy có hai sự kiện trùng và giúp loại bỏ một trong hai. Nếu không có người tiêu thụ future, test phải chứng minh sự kiện failure vẫn tới kênh giám sát.

## 19. Quy trình rà soát code có nhiều catch/log

Khi thấy cùng exception đi qua nhiều `catch`, hãy lần lượt đặt câu hỏi:

1. **Đây là một lỗi hay nhiều lỗi khác nhau?** Xem original exception/cause, requestId, attempt, event type.
2. **Tầng nào sở hữu outcome?** Ai quyết định retry, fallback, trả response, đánh dấu job failed?
3. **Catch này có làm gì ngoài log và throw?** Nếu không, cân nhắc bỏ catch hoặc chỉ giữ mapping abstraction.
4. **Nếu bỏ log tầng này, context nào bị mất?** Chuyển context sang exception/result/MDC/tracing trước khi xóa.
5. **Có giữ `cause` không?** Khi bọc phải dùng constructor nhận cause; không tạo RuntimeException mới làm mất nguồn gốc.
6. **Thông tin trong log có hữu ích không?** Operation, ID, error code, dependency, attempt, trạng thái rollback/commit.
7. **Có nơi nào log final đầy đủ chưa?** Nếu có, kiểm tra log tầng khác có phản ánh sự kiện độc lập thực sự không.
8. **Severity phản ánh tác động không?** Validation/cancellation/retry dự kiến không luôn là ERROR.
9. **Có duplicate stack trace từ framework tự log không?** Ví dụ request error handler và servlet/container logger, hoặc background task logger.
10. **Có dữ liệu nhạy cảm trong message/cause/context không?** Gỡ bỏ/che đúng chỗ.
11. **Có mã async không được quan sát không?** Kiểm tra `Future`/`CompletableFuture` và kênh giám sát nếu fire-and-forget.
12. **Test và metrics có còn đúng sau refactor không?** Giảm log duplicate nhưng không bỏ mất thông tin về failure cuối.

## 20. Kết luận

**Vừa ghi log vừa ném lại ở nhiều tầng** là sai lầm thường gặp vì nhân bản một lỗi thành nhiều sự kiện ERROR, làm khó chẩn đoán, tăng chi phí logging và có thể khiến dashboard đếm sai. Khi tầng hiện tại chỉ **chuyển lỗi**, hãy ném tiếp hoặc bọc có `cause` và thêm context đúng ngữ nghĩa. Khi một tầng **sở hữu kết quả cuối**, hãy ghi một failure event đủ operation, correlation/business IDs, error code và toàn bộ Throwable.

**Không nhầm “log tại boundary” với “cấm mọi log trung gian”.** Retry attempt, fallback, compensation, audit hoặc các ranh giới dịch vụ khác nhau có thể là sự kiện riêng cần ghi — miễn là mỗi event có mục đích, severity và danh tính rõ ràng.

Quy tắc tự kiểm tra: *Nếu xóa dòng log ở tầng này, thông tin điều tra có mất không? Nếu có, có thể chuyển thông tin ấy thành ngữ cảnh và để boundary ghi một lần hay không?* Câu trả lời dẫn đến hệ thống xử lý exception dễ bảo trì và hệ thống log dễ tin cậy hơn.

### Tài liệu tham khảo

- [Java SE 17 — Throwable: cause, stack trace, suppressed exceptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)
- [Java SE 17 — RuntimeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/RuntimeException.html)
- [Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [SLF4J Manual — parameterized logging](https://www.slf4j.org/manual.html)
