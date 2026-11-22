# Preserve root cause: giữ nguyên nguyên nhân gốc khi logging exception trong Java

## 1. “Preserve root cause” nghĩa là gì?

Khi một thao tác trong ứng dụng Java thất bại, exception có thể được **bọc qua nhiều tầng**: driver database, repository, service, controller, message consumer hoặc tác vụ bất đồng bộ. Mỗi tầng có thể bổ sung ngữ cảnh có ích, nhưng nếu ném ra một exception mới mà **không truyền exception ban đầu làm cause**, hệ thống có thể mất manh mối quan trọng nhất để tìm nguyên nhân.

**Preserve root cause** là nguyên tắc **giữ lại exception gây ra lỗi** trong chuỗi `Throwable.getCause()`, đồng thời ghi log với **đối tượng `Throwable` thật** để người điều tra có stack trace và quan hệ `Caused by`, không chỉ một câu mô tả lỗi.

Ví dụ tình huống:

```text
HTTP POST /orders
        |
        v
OrderController
        |
        v
OrderService.createOrder
        |
        v
OrderRepository.save
        |
        v
Database driver: connection refused
        |
        +-- SQLException / IOException
                |
                +-- RepositoryException(cause = original)
                        |
                        +-- OrderProcessingException(cause = repository exception)
                                |
                                +-- Controller / exception handler logs Throwable
```

Nếu controller chỉ nhìn thấy `OrderProcessingException: Cannot create order` mà không có `Caused by`, người vận hành khó biết lỗi do kết nối database, kiểm tra dữ liệu, timeout, ràng buộc dữ liệu hay lỗi code.

Mục tiêu không phải tìm một chuỗi `getMessage()` ở tận đáy rồi bỏ mọi wrapper. Một exception ở lớp ngoài có thể giải thích **thao tác nghiệp vụ thất bại**, trong khi exception sâu nhất cung cấp **nguyên nhân kỹ thuật**. **Giữ cả chuỗi cause** giúp người đọc hiểu được hai góc nhìn.

## 2. Hiểu `Throwable`: message, stack trace, cause và suppressed

Java dùng `Throwable` làm gốc cho `Exception` và `Error`. Các phần quan trọng:

| Thành phần | API | Ý nghĩa |
| --- | --- | --- |
| Exception type | `getClass()` | Lỗi được phân loại bởi lớp nào |
| Message | `getMessage()` | Chi tiết văn bản; có thể `null` hoặc chứa dữ liệu nhạy cảm |
| Stack trace | `getStackTrace()` / `printStackTrace()` | Các frame gắn với nơi throwable được tạo hoặc cập nhật stack |
| Cause | `getCause()` | Throwable làm phát sinh exception hiện tại, nếu có |
| Suppressed exceptions | `getSuppressed()` | Những lỗi bổ sung được giữ lại, thường trong `try-with-resources` |
| Original throwable | Chính đối tượng `Throwable` | Đầu vào đầy đủ cho logger và công cụ chẩn đoán |

Ví dụ:

```java
// Mã minh họa tích hợp.
try {
    callStorage();
} catch (java.io.IOException original) {
    throw new IllegalStateException("Cannot complete checkout", original);
}
```

`IllegalStateException` tạo ra **stack trace mới ở nơi bọc lỗi** nhưng có `getCause() == original`, nhờ vậy stack trace cũ vẫn được lưu trong chuỗi nguyên nhân. Đây là **contextual wrapping**: bổ sung thông tin nhưng không xóa bằng chứng gốc.

Một throwable có thể **không có cause**. Không ép mọi lỗi đều phải có nguyên nhân sâu hơn. Ngoài ra, *deepest cause* không nhất thiết là thứ duy nhất cần quan sát: ở hệ thống phân tán, lỗi gốc kỹ thuật có thể là `SocketTimeoutException`, nhưng wrapper `PaymentGatewayException` mới chỉ ra gateway nào và operation nào đang xảy ra.

### 2.1. “Root cause” không đồng nghĩa “message của cause cuối cùng”

Hai chuỗi sau không có giá trị chẩn đoán như nhau:

```text
Cannot create order
Caused by: Connection timed out
```

và:

```text
OrderProcessingException: Cannot create order
    at OrderService.createOrder(...)
Caused by: RepositoryException: Unable to persist order
    at OrderRepository.save(...)
Caused by: SocketTimeoutException: Connection timed out
    at ... driver/network ...
```

Ví dụ thứ nhất chỉ nói **kết quả của việc rút gọn text**; ví dụ thứ hai là cấu trúc gợi nhớ stack trace gồm các tầng. Các dấu `...` chỉ nhằm diễn giải, **không phải stdout của một chương trình**.

Để bảo toàn bằng chứng trong logging, truyền **`Throwable`**, không tự tạo một bản tóm tắt string rồi bỏ exception.

## 3. Sai và đúng khi bọc exception

### 3.1. Sai: tạo exception mới chỉ với message

```java
// Sai: mất tham chiếu cause, stack trace gốc không có trong chain.
try {
    repository.save(order);
} catch (java.sql.SQLException original) {
    throw new RuntimeException("Save failed: " + original.getMessage());
}
```

`new RuntimeException(String)` không nhận nguyên nhân. `RuntimeException.getCause()` của wrapper mới trả `null` trừ khi được gán theo cơ chế khác. Thông tin stack trace gốc bị tách khỏi throwable được truyền lên trên.

Message cũng có thể chứa query parameter, địa chỉ nội bộ hoặc thông tin nhạy cảm mà ứng dụng không muốn nhân bản vào message của lỗi bên ngoài.

### 3.2. Đúng: truyền nguyên nhân gốc vào constructor

```java
// Mã tích hợp, giả định repository và order là biến trong ứng dụng.
try {
    repository.save(order);
} catch (java.sql.SQLException original) {
    throw new RuntimeException("Order persistence failed", original);
}
```

Wrapper giữ bối cảnh nghiệp vụ và giữ `original` như cause. Từ tầng trên có thể đọc:

```java
Throwable immediateCause = failure.getCause();
```

Đây là **mảnh mã tích hợp**; `failure` phải là một `Throwable` được khai báo. Có thể đi tiếp nhiều lần `getCause()` nếu cần phân tích sâu.

### 3.3. Đúng: khai báo custom exception có constructor nhận cause

```java
public final class OrderProcessingException extends RuntimeException {
    public OrderProcessingException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là **class độc lập có thể biên dịch** nếu lưu trong file `OrderProcessingException.java`. Trong ứng dụng, ném:

```java
// Mảnh mã tích hợp; original là Throwable gây lỗi.
throw new OrderProcessingException("Cannot create order", original);
```

Nếu một custom exception chỉ có constructor `(String)`, người viết code thường vô tình đánh mất cause khi wrap. Với lớp exception nghiệp vụ, nên cung cấp các constructor phù hợp với cách xử lý thực tế, tránh thêm constructor không có mục đích.

### 3.4. `throw original` hay `throw new Wrapper(..., original)`?

- **Rethrow** (`throw original;`) giữ chính đối tượng throwable, stack trace và cause của nó. Phù hợp khi tầng hiện tại không cần đổi loại exception và chữ ký phương thức cho phép.
- **Wrap with cause** bổ sung loại và context cho boundary giữa tầng persistence, service, transport; stack trace của wrapper bắt đầu tại nơi wrap, nhưng stack trace gốc được giữ trong cause.
- **Wrap without cause** thường là lỗi chẩn đoán.
- **Replace intentionally** chỉ hợp lý khi có yêu cầu chính sách rõ ràng (ví dụ không để exception nội bộ vượt trust boundary). Ngay cả khi trả về response lỗi đã sanitize, hệ thống có thể giữ cause trong log nội bộ được bảo vệ.

Đừng đổi sang `throw new RuntimeException(original.getMessage())` chỉ để tránh checked exception; cách đó làm mất chuỗi nguyên nhân và có thể nhân bản dữ liệu nhạy cảm.

## 4. Java 17: ví dụ độc lập chứng minh cause được giữ nguyên qua logging

Chương trình dưới mô phỏng:

1. Lớp lưu trữ ném `IOException`.
2. Lớp nghiệp vụ bọc thành `OrderProcessingException` **với cause**.
3. Boundary bắt wrapper, xác định loại throwable sâu nhất để phân loại.
4. JUL `Logger.log(Level, String, Throwable)` nhận **chính wrapper**, không chỉ chuỗi lỗi.
5. Handler demo in metadata ổn định để có stdout xác định. Trong ứng dụng thật, formatter có thể in stack trace đầy đủ.

Lưu file **`RootCauseLoggingDemo.java`**:

```java
import java.io.IOException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RootCauseLoggingDemo {
    private static final class OrderProcessingException
            extends RuntimeException {
        OrderProcessingException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    private static void saveOrder() throws IOException {
        throw new IOException("storage unavailable");
    }

    private static void createOrder() {
        try {
            saveOrder();
        } catch (IOException original) {
            throw new OrderProcessingException(
                    "cannot create order", original);
        }
    }

    private static Throwable deepestCause(Throwable failure) {
        Set<Throwable> seen = Collections.newSetFromMap(
                new IdentityHashMap<Throwable, Boolean>());
        Throwable current = failure;
        seen.add(current);

        while (current.getCause() != null
                && seen.add(current.getCause())) {
            current = current.getCause();
        }
        return current;
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.root-cause");
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);

        Handler output = new Handler() {
            {
                setLevel(Level.ALL);
            }

            @Override
            public void publish(LogRecord record) {
                if (record != null && isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
                    Throwable thrown = record.getThrown();
                    if (thrown != null) {
                        System.out.println("thrownType="
                                + thrown.getClass().getSimpleName());
                        Throwable cause = thrown.getCause();
                        System.out.println("causeType="
                                + (cause == null
                                    ? "none"
                                    : cause.getClass().getSimpleName()));
                    }
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush(); // Không đóng System.out của JVM.
            }
        };

        logger.addHandler(output);
        try {
            try {
                createOrder();
            } catch (OrderProcessingException failure) {
                Throwable root = deepestCause(failure);
                logger.log(
                        Level.SEVERE,
                        "event=order_failed rootType="
                                + root.getClass().getSimpleName(),
                        failure); // Quan trọng: truyền Throwable gốc.
            }
        } finally {
            logger.removeHandler(output);
            output.close();
        }
    }
}
```

Biên dịch/chạy với **JDK 17 trở lên**:

```bash
javac RootCauseLoggingDemo.java
java RootCauseLoggingDemo
```

Kết quả chính xác trên **`stdout`**:

```text
SEVERE event=order_failed rootType=IOException
thrownType=OrderProcessingException
causeType=IOException
```

Vì handler demo tự in trường đã chọn nên **không có stack trace dài hoặc line number** trong output trên. Điều này không có nghĩa exception mất stack trace: `record.getThrown()` vẫn là `OrderProcessingException`, và `getCause()` vẫn là `IOException`. Formatter thực tế của JUL như `SimpleFormatter` có thể dùng trường `LogRecord.thrown` để in stack trace và dòng `Caused by`.

### 4.1. Các điểm cần giải thích

- `saveOrder()` mô phỏng failure gần nguồn nhất. `IOException` vẫn tồn tại dù tầng `createOrder()` ném một exception khác.
- Constructor `super(message, cause)` giữ nguyên instance `IOException`; không cần gọi `printStackTrace()` trong tầng service.
- `deepestCause` sử dụng tập dựa trên **object identity** để tránh lặp vô hạn khi có cause cycle không thông thường. Với chain bình thường, kết quả là throwable cuối cùng trước `null`.
- `IdentityHashMap` trong ví dụ giúp hàm khám phá an toàn hơn; **không tự xác định root cause nghiệp vụ thực sự**.
- `logger.log(Level.SEVERE, message, failure)` truyền một `Throwable` vào JUL để backend/formatter có thể giữ toàn bộ cause chain.
- `logger.setUseParentHandlers(false)` tránh in thêm ở root handler; handler demo chỉ ghi `stdout`, không phụ thuộc timestamp.
- `finally` gỡ handler để tránh side effect khi demo nằm trong JVM khác.
- Ví dụ cố ý chỉ in **kiểu** của cause thay vì `IOException.getMessage()` để giảm khả năng đưa thông tin môi trường nội bộ vào log tổng hợp.

### 4.2. Vì sao không phải lúc nào cũng cần tự tìm deepest cause?

`logger.log(..., failure)` đã giữ wrapper và chain. Trong một ứng dụng production, có thể chỉ cần:

```java
// Mảnh tích hợp; logger là java.util.logging.Logger.
logger.log(Level.SEVERE, "Order processing failed", failure);
```

Hàm đi đến đáy cause chỉ có ích khi cần **phân loại lỗi**, ví dụ ghi `rootCauseType`, thống kê theo exception class hoặc lựa chọn retry. Nếu chỉ muốn stack trace đầy đủ, **truyền chính throwable** thường tốt hơn việc thay throwable bằng deepest cause: logger cũng cần context ở các tầng bao ngoài.

## 5. Các cách ghi log làm mất thông tin nguyên nhân

| Cách viết | Hậu quả | Gợi ý |
| --- | --- | --- |
| `log.error("Failed: " + e.getMessage())` | Chỉ ghi chuỗi message, thường không có stack trace và cause chain | `log.error("Failed", e)` |
| `log.error("Failed: {}", e.getMessage())` | Placeholder không tự khôi phục throwable | Truyền `e` như Throwable |
| `log.error(e.toString())` | Chỉ tên kiểu + message, không giữ chain dưới dạng exception | Ghi `e` bằng overload hỗ trợ |
| `e.printStackTrace()` | In ra stderr trực tiếp, không theo cấu hình/định dạng/routing chuẩn của logger | Dùng logger với Throwable |
| `throw new RuntimeException(e.getMessage())` | Cause của wrapper mới là null | `throw new RuntimeException("...", e)` |
| `throw new RuntimeException("Unexpected")` | Thay thế lỗi có thể làm mất chứng cứ | Gắn cause trừ khi policy yêu cầu khác |
| Chỉ `log.error("{}", e.getCause())` | Có thể chỉ in `toString()` của immediate cause và mất context | Ghi exception gốc đầy đủ |
| `log.error("Failed", e)` ở mọi tầng | Không làm mất cause nhưng tạo log trùng và tăng nhiễu | Log tại boundary có trách nhiệm |

Đối với **SLF4J**, cách đơn giản, rõ ràng:

```java
// Đoạn tích hợp: log là org.slf4j.Logger.
log.error("Unable to process order", exception);
```

Đây là overload nhận `Throwable`, khác với `log.error("Unable to process order: " + exception.getMessage())`.

Với tham số nghiệp vụ:

```java
// Đoạn tích hợp: orderId là mã đã kiểm duyệt, exception là Throwable.
log.error("Unable to process orderId={}", orderId, exception);
```

Ở những phiên bản SLF4J thông dụng, **Throwable ở vị trí đối số cuối** được nhận diện như cause của sự kiện, tách khỏi placeholder message. Nếu phụ thuộc provider/phiên bản hoặc overload gây mơ hồ, có thể dùng dạng rõ ràng `log.error("Unable to process orderId=" + safeOrderId, exception)` tại boundary, nhưng vẫn cần bảo đảm `safeOrderId` được kiểm duyệt và không tạo dữ liệu nhạy cảm.

Với JUL:

```java
// Đoạn tích hợp: logger là java.util.logging.Logger.
logger.log(Level.SEVERE, "Order processing failed", exception);
```

JUL không dùng `log.error(...)` mà dùng `Level.SEVERE`; không trộn `java.util.logging.Level` với enum level của Log4j 2 hoặc các API framework khác.

## 6. Đừng đánh đồng cause với suppressed exception

Một lỗi quan trọng khác là **suppressed exception**, thường xảy ra khi một thao tác đã thất bại, sau đó việc đóng tài nguyên trong `try-with-resources` cũng thất bại.

Ví dụ:

```text
Primary failure: xử lý dữ liệu bị lỗi
       |
       +-- Suppressed: đóng file/socket/connection cũng bị lỗi
```

Suppressed **không nhất thiết là cause của primary error**. Java giữ chúng qua `Throwable.getSuppressed()`; `printStackTrace()` theo chuẩn thường thể hiện một phần `Suppressed:` bên cạnh `Caused by:`.

Nếu người lập trình chỉ lấy `getCause()` hoặc chỉ in một deepest cause, có thể bỏ qua thông tin về lỗi cleanup. Đối với cơ chế retry và điều tra mất dữ liệu, lỗi đóng resource đôi khi có ý nghĩa rất lớn.

### 6.1. Ví dụ Java 17 độc lập về suppressed exception

Lưu file **`SuppressedCauseDemo.java`**:

```java
public class SuppressedCauseDemo {
    static final class FragileResource implements AutoCloseable {
        @Override
        public void close() throws Exception {
            throw new Exception("close failed");
        }
    }

    public static void main(String[] args) {
        try (FragileResource ignored = new FragileResource()) {
            throw new IllegalStateException("work failed");
        } catch (Exception failure) {
            System.out.println("primaryType="
                    + failure.getClass().getSimpleName());
            System.out.println("causePresent="
                    + (failure.getCause() != null));
            System.out.println("suppressedCount="
                    + failure.getSuppressed().length);
            System.out.println("suppressedType="
                    + failure.getSuppressed()[0]
                            .getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac SuppressedCauseDemo.java
java SuppressedCauseDemo
```

Kết quả **`stdout`**:

```text
primaryType=IllegalStateException
causePresent=false
suppressedCount=1
suppressedType=Exception
```

Giải thích:

- Phần body ném `IllegalStateException`: đó là **primary exception**.
- Khi đi ra khỏi `try-with-resources`, `close()` ném `Exception`. Java thêm lỗi đóng vào mảng **suppressed** của primary throwable.
- Primary có `getCause() == null` nhưng vẫn có một suppressed exception. Vì vậy “không có cause” **không đồng nghĩa không có lỗi liên quan**.
- Mã cố ý in type/count thay vì stack trace để có output xác định; logger thật nên giữ primary throwable nguyên vẹn cho formatter có thể hiển thị suppressed.

**Không nên thay suppressed bằng cause** một cách máy móc: chúng thể hiện quan hệ khác nhau. Nếu viết code quản lý tài nguyên thủ công và một lỗi cleanup mới che mất lỗi xử lý chính, cần cân nhắc `addSuppressed(cleanupFailure)` đúng ngữ nghĩa, nhưng `try-with-resources` thường đã giúp thực hiện việc này an toàn hơn.

## 7. Chuỗi nguyên nhân qua nhiều tầng của ứng dụng

Hãy xem ba boundary:

```text
Repository: data access
    -> Service: business operation
        -> Controller/Message handler: entry boundary
```

**Repository** có thể chuyển lỗi thư viện thành exception thuộc abstraction tầng lưu trữ:

```java
// Mã tích hợp: gọi repository thực tế bên trong phương thức.
try {
    jdbcOperation();
} catch (java.sql.SQLException cause) {
    throw new DataAccessFailure(
            "Unable to execute order persistence operation", cause);
}
```

**Service** bổ sung ngữ cảnh nghiệp vụ:

```java
try {
    persistOrder(order);
} catch (DataAccessFailure cause) {
    throw new OrderProcessingException(
            "Unable to create order", cause);
}
```

Hai đoạn trên chỉ là **mảnh tích hợp**; `DataAccessFailure`, `OrderProcessingException`, `jdbcOperation`, `persistOrder` và `order` cần được định nghĩa trong ứng dụng. Điểm quan trọng là cùng một chain đi lên thay vì bị thay thế bởi message.

**Boundary** (web exception handler, scheduled job wrapper, message consumer) quyết định ghi log:

```java
// Mảnh tích hợp: logger và operationId đã khai báo.
try {
    applicationService.execute();
} catch (OrderProcessingException failure) {
    logger.log(Level.SEVERE,
            "operation failed, operationId=" + safeOperationId,
            failure);
    throw failure;
}
```

Đoạn này **vừa log vừa rethrow** có thể tạo **duplicate log** nếu tầng ngoài cũng log. Trong thực tế thường chọn **một boundary chịu trách nhiệm log exception chưa được xử lý**, và chỉ giữ nguyên chain khi chuyển tầng. Nếu phải ghi trước khi rethrow vì một lý do nghiệp vụ, cần xác định rằng tầng tiếp theo có ghi lại hay không.

### 7.1. Khi nào chỉ cần `throw;` hoặc `throw e;`?

Java không có `throw;` giống một số ngôn ngữ khác. Khi đang trong `catch (SomeException e)`, dùng `throw e;` để ném lại **chính throwable** nếu chữ ký phương thức cho phép.

```java
try {
    performOperation();
} catch (java.io.IOException e) {
    // Có thể làm cleanup/metric an toàn, không thay throwable.
    throw e;
}
```

Mảnh mã cần khai báo `performOperation()` và phương thức chứa phải cho phép ném `IOException`. `throw e;` giữ object và stack trace hiện có. Không cần bọc exception nếu tầng hiện tại không thực sự có thông tin bổ sung hoặc abstraction cần thiết.

### 7.2. Custom exception không được làm mất cause

Nếu tạo exception riêng, nên xem xét cung cấp constructor phù hợp:

```java
public class ServiceFailure extends RuntimeException {
    public ServiceFailure(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là class độc lập có thể lưu dưới tên `ServiceFailure.java`. Đừng bọc mọi exception thành cùng một `ServiceFailure("Error")` không có cause; người xử lý sẽ không phân biệt lỗi database, validation và downstream.

## 8. Logging once: giữ cause không có nghĩa log ở mọi tầng

Một anti-pattern:

```text
Repository catches SQLException -> ERROR + stack
Service catches RepositoryException -> ERROR + stack
Controller catches ServiceException -> ERROR + stack
Gateway catches request failure -> ERROR + stack
```

Một lỗi thực có thể sinh 4 stack trace. Khi lỗi lặp liên tục, ứng dụng gặp **log storm**, async logging queue đầy, disk/collector quá tải và thông tin quan trọng bị chìm trong nhiễu.

Quy tắc thực tế:

1. Tầng thấp **wrap với cause và truyền lên**, tránh log lỗi mà nó không xử lý.
2. Tầng có thể **phục hồi thật** (retry thành công, fallback thành công) ghi sự kiện có ngữ nghĩa phù hợp; không báo ERROR sau khi đã xử lý hoàn toàn nếu hệ thống không cần cảnh báo.
3. Tầng **đầu vào/điểm xử lý cuối** quyết định một lần log đầy đủ với Throwable khi lỗi không thể xử lý.
4. Nếu policy yêu cầu audit riêng một hành động bị từ chối/thất bại, ghi audit event theo schema/retention riêng, không coi đó là phép lặp bản stack trace.
5. Nếu cần context cho mỗi tầng, bọc nguyên nhân với thông điệp ngắn, ổn định; không dump payload.

**“Log once” không phải luật tuyệt đối.** Retry attempt, circuit breaker transition hoặc một side effect riêng có thể là các sự kiện độc lập đáng ghi. Tuy nhiên, những bản ghi đó nên có event code khác nhau, attempt/count và mức độ phù hợp, không sao chép cùng một stack trace ở mọi nơi.

## 9. Async exceptions: `CompletionException` và `ExecutionException`

Trong Java concurrency, exception có thể bị một API bất đồng bộ **bọc tự động**:

- `CompletableFuture.join()` thường ném `CompletionException` khi tác vụ hoàn tất lỗi.
- `Future.get()` hoặc `CompletableFuture.get()` có thể ném `ExecutionException` bao quanh nguyên nhân.
- Ngoài ra còn có `CancellationException` hoặc `InterruptedException` với ngữ nghĩa riêng.

Ví dụ mảnh mã tích hợp:

```java
try {
    resultFuture.join();
} catch (java.util.concurrent.CompletionException wrapper) {
    Throwable cause = wrapper.getCause();
    // Ghi wrapper cùng Throwable sẽ giữ cause chain nếu được thiết lập.
    log.error("Background task failed", wrapper);
    // Không tự động biến mọi cause thành lỗi retryable.
}
```

Đây là đoạn tích hợp, giả định `resultFuture` và `log` có sẵn. Nếu ứng dụng chuẩn hóa lỗi tại boundary, có thể chọn `wrapper.getCause()` làm nguồn phân loại, nhưng **không nên loại bỏ wrapper nếu nó giúp xác định boundary async**.

Một anti-pattern:

```java
// Sai: tạo exception mới với chuỗi message, làm mất cause.
catch (java.util.concurrent.ExecutionException e) {
    throw new RuntimeException(e.getMessage());
}
```

Tốt hơn:

```java
// Mảnh mã trong phương thức có thể ném runtime exception.
catch (java.util.concurrent.ExecutionException e) {
    throw new RuntimeException("Async operation failed", e);
}
```

Có thể xử lý theo nguyên nhân thật thay vì wrap lại tùy contract của API, nhưng cần giữ chain hoặc có lý do rõ cho việc chuẩn hóa.

### 9.1. Không unwrap vô hạn

Một helper “root cause” có thể đi nhiều lần qua `getCause()`. Tuy nhiên:

- Có thể gặp `null` và phải dừng.
- Các exception do thư viện tạo có thể có quan hệ cause không thông thường; cần tránh loop.
- `InterruptedException`, `CancellationException`, `TimeoutException` có ngữ nghĩa xử lý khác nhau, **không chỉ là wrapper**.
- `SQLException` còn có thể mang `getNextException()` ngoài cause chain.
- Exception suppressed là nhánh khác, không nằm trong đường `getCause()` thông thường.

Do đó không nên dồn tất cả thành một string `rootCause.message` rồi bỏ original `Throwable`. Chỉ chuẩn hóa các **loại wrapper đã hiểu rõ** phục vụ policy cụ thể.

## 10. `InterruptedException`: vừa giữ cause vừa giữ cờ interrupt

Java dùng interrupt để báo yêu cầu hủy/dừng công việc. Nếu bắt `InterruptedException`, một số blocking API có thể **xóa trạng thái interrupt** khi ném. Nếu phương thức không thể ném lại checked exception, cần phục hồi cờ interrupt trước khi wrap:

```java
// Mảnh mã tích hợp; taskQueue là BlockingQueue<?>.
try {
    taskQueue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Consumer interrupted", e);
}
```

Đây là ví dụ khi chữ ký phương thức **không cho phép `throws InterruptedException`** và policy là kết thúc xử lý theo cách phù hợp. Ngược lại, nếu có thể, **ném lại trực tiếp** và cho tầng gọi xử lý:

```java
public void awaitWork() throws InterruptedException {
    taskQueue.take(); // taskQueue là field BlockingQueue<?> có sẵn.
}
```

Đoạn trên là mảnh tích hợp cần `taskQueue`. Không phải lỗi interrupt nào cũng nên log ở `ERROR`: khi hệ thống shutdown có trật tự, interrupt có thể là tín hiệu bình thường. Nhưng **nuốt interrupt và chỉ log message** có thể khiến worker tiếp tục chạy sai lifecycle.

Giữ `cause=e` giúp sau này biết thao tác bị interrupt; `Thread.currentThread().interrupt()` giúp luồng xử lý tiếp tục nhận tín hiệu hủy. Hai hành động giải quyết **hai vấn đề khác nhau**, không thay thế nhau.

## 11. Root cause đối với HTTP, service và message consumer

### 11.1. Web controller / exception handler

Ví dụ một HTTP request thất bại vì storage. Client có thể nhận response đã sanitize như:

```json
{
  "errorCode": "ORDER_PROCESSING_FAILED",
  "message": "Không thể xử lý yêu cầu lúc này",
  "requestId": "req-2041"
}
```

Đây là response **minh họa**, không phải output của chương trình Java ở trên. Nó không tiết lộ stack trace, hostname, query SQL hoặc credential. Bên trong, handler nên có một log tương quan với `requestId`, `errorCode`, `exceptionType` và **Throwable** để người vận hành tìm nguyên nhân.

Đừng trả thẳng `rootCause.getMessage()` hoặc `Throwable.printStackTrace()` trong HTTP response. Message sâu nhất có thể chứa cấu hình mạng, đường dẫn file, tên bảng, SQL hoặc dữ liệu đầu vào nhạy cảm.

Đối với lỗi input dự kiến (ví dụ validation 400), thường không cần stack trace `ERROR` mỗi lần; phân loại error code và mức log hợp lý để tránh gây nhiễu.

### 11.2. Message consumer

Một consumer xử lý event có thể thất bại ở database:

```text
Message received
  -> business handler
  -> RepositoryException(cause=SQLException)
  -> Consumer boundary
      -> classified failure/retry or DLQ
```

Log được cân nhắc:

- `messageId`/broker coordinates (đã kiểm duyệt), `consumerGroup`, `attempt`, `errorCode`.
- `exceptionType` và `rootCauseType` để phân loại, **không lộ nguyên message**.
- `Throwable` đầy đủ tại thời điểm cần điều tra, với tần suất và quyền truy cập phù hợp.
- Outcome `retry_scheduled`/ `dead_lettered`/ `processing_failed` phải phản ánh **trạng thái thật**, không suy ra từ exception class.

Một cause gốc là `SQLTimeoutException` có thể là tín hiệu cho retry, nhưng **retry policy phải xét idempotency, giới hạn số lần, backoff và side effect đã commit**. Không tự retry vô hạn chỉ vì root cause chứa chữ “timeout”.

### 11.3. Scheduled jobs

Trong scheduled job, lỗi có thể được scheduler bọc hoặc bắt để tiếp tục các lần chạy sau. Hãy ghi `jobName`, `runId`, `scheduleTime` phù hợp và giữ `Throwable`. Đừng chỉ in `"Job failed"` rồi nuốt exception khi scheduler cần trạng thái thất bại để retry/cảnh báo.

## 12. Tìm “root cause” an toàn trong cause chain

Một helper dạng thông thường:

```java
// Mảnh tích hợp; caller bảo đảm failure != null.
Throwable current = failure;
while (current.getCause() != null) {
    current = current.getCause();
}
```

Là cách giải thích ý tưởng, nhưng nếu cause chain không chuẩn hoặc có **cycle**, có thể không dừng. Bản code Java 17 chạy độc lập ở phần 4 sử dụng một tập identity để tránh vòng lặp.

Khi nhận dữ liệu lỗi từ thư viện phức tạp, nên:

1. Giữ original Throwable làm nguồn gốc.
2. Dùng một helper an toàn nếu cần **deepest cause type**.
3. Xem xét wrappers đặc biệt có ý nghĩa, như `CompletionException` hoặc `ExecutionException`, trước khi phân loại.
4. Kiểm tra `getSuppressed()` khi resource cleanup, transaction rollback hoặc shutdown liên quan.
5. Đối với SQL, xem `SQLException.getNextException()` nếu driver có chuỗi lỗi liên quan.
6. Không ép “deepest cause luôn là nguyên nhân thực” khi vấn đề có nhiều yếu tố hoặc lỗi downstream đồng thời.

Một `NullPointerException` nằm sâu có thể cho biết điểm crash, nhưng không tự xác định **vì sao giá trị null**. Root cause analysis thực sự còn cần log context, metrics, trace, cấu hình, sự kiện deploy và dữ liệu nghiệp vụ.

### 12.1. Không sử dụng `Throwable.getMessage()` làm error code

`getMessage()` có thể thay đổi theo Java version, driver, locale hoặc dữ liệu. Một số message còn chứa query/định danh nhạy cảm. Khi muốn dashboard lỗi:

```json
{
  "event": "order.processing_failed",
  "errorCode": "STORAGE_UNAVAILABLE",
  "exceptionType": "OrderProcessingException",
  "rootCauseType": "IOException",
  "requestId": "req-2041"
}
```

Đây là event cấu trúc minh họa. `errorCode` nên do ứng dụng xác định theo policy, không lấy bừa đoạn text đầu exception rồi dùng làm metric label có cardinality cao.

## 13. Root cause và log có cấu trúc

Một exception event tốt thường gồm:

| Field | Vai trò |
| --- | --- |
| `timestamp` | Thời điểm theo UTC/định dạng nhất quán |
| `event` | Ví dụ `order.processing_failed` |
| `level` | Mức độ quan trọng theo policy |
| `service`, `environment`, `instance` | Hệ thống/instance gặp lỗi |
| `requestId`/`traceId`/`messageId` | Tương quan request hoặc event |
| `errorCode` | Mã lỗi ổn định cho dashboard |
| `exceptionType` | Loại exception bao ngoài |
| `rootCauseType` | Loại nguyên nhân sâu nhất nếu phù hợp |
| `operation` | Tác vụ thất bại đã kiểm duyệt |
| `durationMs` | Thời gian xử lý nếu có ý nghĩa |
| `throwable` | Object Throwable cho backend tạo stack trace và cause chain |
| `retryable` / `attempt` | Ngữ cảnh retry đã được phân loại |

Không cần mọi field trên ở mọi event; chọn tập hữu ích theo mức rủi ro và công cụ quan sát. **Đừng tự xuất full exception object thành JSON tùy ý** nếu serializer sẽ duyệt toàn bộ object graph, lộ fields hoặc gây vòng lặp. Dùng logging API với Throwable và encoder được thiết kế để xử lý exception.

Với **SLF4J + Logback**, lời gọi:

```java
// Mảnh mã tích hợp; log, requestId và cause đã khai báo.
log.error("event=order_failed requestId={}", requestId, cause);
```

truyền throwable dưới dạng tham số cuối. Trong hệ sinh thái có structured logging API, có thể thêm các key-value fields riêng; vẫn phải bảo đảm throwable được giữ. Các thư viện/backends khác nhau về cách cấu hình stack trace encoder, JSON layout, message template và MDC.

**MDC** chỉ là context kèm theo event: nó không tự bảo toàn cause. Cần dọn context trong `finally` với thread pool và propagate đúng qua async. `traceId` hỗ trợ điều tra xuyên service nhưng không chứng minh lỗi đã có cause tại JVM khác; thường chỉ có **trace liên kết sự kiện giữa các tiến trình**, không phải một chuỗi `Throwable.getCause()` tự động xuyên HTTP/Kafka.

## 14. Khi log format hoặc framework làm mất stack trace

Ngay cả khi code truyền `Throwable`, log cuối có thể không hiển thị nguyên nhân do cấu hình:

- Pattern/layout chỉ in `%msg` mà không xuất exception phù hợp.
- JSON encoder bỏ trường stack trace hoặc đặt giới hạn stack depth.
- Appender/filter loại ERROR event.
- Async queue đầy, log bị drop hoặc JVM crash trước khi flush.
- Collector/parser cắt message quá dài hay gom multiline không đúng.
- Redaction rule quá rộng xóa toàn bộ thông tin chẩn đoán.
- Log routing đưa stack trace sang sink mà người điều tra không có quyền đọc.

Ví dụ Logback pattern thường thấy:

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n%ex</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Đây là cấu hình minh họa cho dự án có Logback Classic phù hợp; `%ex` yêu cầu hiển thị exception trong pattern. Với JSON logging, cần xem encoder có xuất `stack_trace`/cause chain hay không. Các tên field khác nhau tùy thư viện/version; không mặc định pattern Logback chạy được trong Log4j 2.

**Đừng chỉ xem một dòng text rồi kết luận root cause bị mất.** Một số collector lưu exception ở trường riêng hoặc tách stack trace thành nhiều trường. Kiểm tra **dữ liệu cuối tại sink** và quyền truy vấn. Khi logger bị tắt do level hoặc formatter không xuất Throwable, sự hiện diện của cause trong Java object chưa bảo đảm người vận hành thấy nó.

## 15. Mức log và phân loại lỗi

Giữ cause không có nghĩa mọi exception phải ở `ERROR`.

| Tình huống | Level cân nhắc | Lý do |
| --- | --- | --- |
| Validation người dùng sai dự kiến | INFO/WARN hoặc event chuyên biệt | Không phải lỗi hạ tầng |
| Resource không tồn tại hợp lệ | DEBUG/INFO tùy policy | Tránh báo động giả |
| Retryable timeout còn trong ngân sách | WARN hoặc event retry có hạn mức | Cần theo dõi nhưng hệ thống có thể tự phục hồi |
| Thao tác cuối cùng thất bại | ERROR với throwable phù hợp | Cần điều tra/alert |
| Shutdown bình thường gây interrupt | DEBUG/INFO tùy policy | Tránh báo ERROR ồ ạt |
| `OutOfMemoryError` hoặc `StackOverflowError` | Sự cố nghiêm trọng cần xử lý chuyên biệt | Không tùy tiện catch rồi coi là phục hồi được |

Chỉ số `errorCode` và `outcome` nên mô tả **nghĩa nghiệp vụ/kỹ thuật**, còn `level` diễn đạt mức ưu tiên quan sát. Không dựa chỉ vào deepest exception type để chọn log level.

Cẩn thận với `catch (Throwable t)`: nó bắt cả `Error` có thể biểu thị lỗi JVM nghiêm trọng, và có thể làm ứng dụng tiếp tục ở trạng thái không an toàn. Thông thường bắt những loại exception bạn thực sự biết cách xử lý; tại boundary đặc biệt có thể cần cơ chế giám sát thất bại tối hậu nhưng phải giữ chính sách vận hành phù hợp.

## 16. Bảo mật và quyền riêng tư khi ghi root cause

Một cause sâu trong stack có thể chứa:

- JDBC URL, hostname, tên database hoặc schema.
- SQL query với giá trị literal, unique constraint có chứa dữ liệu cá nhân.
- HTTP URL chứa query token hoặc path nhạy cảm.
- File path nội bộ, tên tài khoản hệ điều hành hoặc thông tin môi trường.
- Header authorization hoặc nội dung message trong exception message.
- Chi tiết thư viện và phiên bản có thể giúp kẻ tấn công suy đoán hạ tầng.

Các nguyên tắc:

1. **Không gửi stack trace/cause chain thô cho client công khai.** Client nhận error code/request ID đã sanitize; nội bộ giữ log theo quyền.
2. **Không đặt raw exception message làm nhãn metric** hoặc một trường cardinality vô hạn.
3. **Không serialise payload để “bổ sung context”** nếu payload chứa PII/secret.
4. Dùng `errorCode`, `safeId`, `operation`, `traceId` đã kiểm tra định dạng để điều tra.
5. Hạn chế quyền truy cập log có stack trace, retention và đường chuyển dữ liệu.
6. Nếu cần redaction, triển khai và kiểm thử ở tầng phù hợp sao cho **không xóa luôn thông tin cause chain** cần vận hành.
7. Phân biệt ứng dụng logging với audit trail bắt buộc lưu; audit có thể yêu cầu nguồn dữ liệu tối thiểu, tính toàn vẹn và quyền tách biệt.
8. Cảnh giác **log injection** khi context hoặc `Throwable.getMessage()` chứa newline/control characters; dùng encoder/structured logging có escaping phù hợp.

**Preserve root cause không có nghĩa công khai mọi thông tin nội bộ.** Giữ bằng chứng ở vùng tin cậy và trình bày thông tin đủ an toàn ở boundary ra ngoài.

## 17. Kiểm thử việc giữ nguyên cause qua tầng ứng dụng

Đừng chỉ kiểm thử một message text. Nên xác minh **quan hệ Throwable** và kết quả log:

| Trường hợp | Điều cần chứng minh |
| --- | --- |
| Wrap với `super(message, cause)` | `wrapper.getCause() == original` |
| Wrap qua 2–3 tầng | Chain đầy đủ: service → repository → I/O/SQL |
| Wrap sai chỉ lấy message | Test phát hiện cause bị mất |
| Rethrow `throw e;` | Không tạo một throwable mới không cần thiết |
| JUL logging với `Throwable` | `LogRecord.getThrown()` chứa original wrapper |
| SLF4J logging với exception | Test appender/event giữ throwable và stack trace |
| `try-with-resources` có lỗi xử lý + close | Lỗi close nằm trong `getSuppressed()` |
| `CompletableFuture.join()` lỗi | Cause của `CompletionException` được bảo toàn |
| `Future.get()` lỗi | `ExecutionException` chứa lỗi từ task |
| Interrupt khi blocking | Interrupt flag được xử lý đúng theo contract |
| Handler/formatter tùy chỉnh | Stack trace/cause được xuất như kỳ vọng |
| JSON log collector | Throwable vẫn tìm được tại sink, không bị cắt hết |
| Exception message chứa token hoặc newline | Không làm lộ secret hay giả tạo dòng log |
| Một lỗi qua nhiều tầng | Không tạo stack trace trùng vô ích |
| Async logging queue đầy | Có metric/backpressure/failure policy, không giả định log luôn tồn tại |

Một unit test đơn giản có thể dùng:

```java
// Mảnh tích hợp; original và wrapper là Throwable đã tạo.
if (wrapper.getCause() != original) {
    throw new AssertionError("Root cause lost");
}
```

Để test logging qua JUL, tạo một handler test thu `LogRecord` và kiểm tra `record.getThrown()` đúng object; với SLF4J/Logback, dùng test appender phù hợp. Trong end-to-end test, còn phải kiểm tra formatter, collector và dữ liệu đã lưu, vì exception có thể được giữ ở JVM mà bị bỏ sau đó.

**Không suy diễn từ số dòng `Caused by:`** để xác định success: một số encoder gom/cắt stack trace và các SDK chuyển exception thành fields riêng. Test phải bám vào mục tiêu quan sát thực tế.

## 18. Chẩn đoán root cause trong production

Khi điều tra một event `order.processing_failed`:

1. Lấy `requestId` hoặc `traceId`, `service`, `environment`, thời điểm xảy ra.
2. Mở log ở boundary có **Throwable**; kiểm tra exception type bao ngoài.
3. Duyệt **`Caused by` chain** để hiểu lỗi của các tầng dưới.
4. Xem **Suppressed** nếu lỗi liên quan đóng resource hoặc cleanup.
5. Đối chiếu thời điểm với metrics như connection pool saturation, latency, network errors, disk và deployment/config changes.
6. Nếu sự cố qua nhiều service, dùng distributed trace và error code để nối các nguyên nhân ở các tiến trình; đừng chờ `Throwable.getCause()` tự vượt ranh giới network.
7. Kiểm tra retry, circuit breaker, rollback và side effect đã commit để xác định hệ quả.
8. Chỉ sau khi có đủ bằng chứng mới kết luận nguyên nhân hệ thống, không chỉ đọc dòng exception cuối cùng.

Ví dụ: deepest cause là `SocketTimeoutException`. Nguyên nhân vận hành có thể là downstream quá tải, DNS/network, connection pool kẹt, GC pause hoặc timeout quá thấp. Cause chain cho **điểm lỗi quan sát được**, còn root-cause analysis cần **bằng chứng liên quan** để tìm nguyên nhân sâu hơn ở cấp hệ thống.

## 19. Các sai lầm phổ biến

### 19.1. Chỉ ghi `e.getMessage()`

Bị mất type, stack và causes ở logging event. Dùng overload logger nhận `Throwable`.

### 19.2. Bọc lỗi bằng `new RuntimeException(e.toString())`

Vẫn chỉ tạo text. Hãy truyền `e` như cause.

### 19.3. Nghĩ `throw new Exception("...", cause)` giữ nguyên hoàn toàn stack wrapper

Wrapper có stack mới ở nơi wrap. Điều quan trọng là **cause cũ vẫn được giữ**, không phải stack của wrapper trùng stack ban đầu.

### 19.4. Log stack trace ở mọi tầng

Không làm mất cause nhưng tạo nhiều bản ghi trùng, tăng chi phí và che mất tín hiệu. Chọn boundary phù hợp.

### 19.5. Chỉ log deepest cause

Có thể bỏ bối cảnh nghiệp vụ của wrapper và suppressed exceptions. Truyền throwable ở boundary, dùng deepest type như một trường bổ sung khi cần.

### 19.6. Nuốt `InterruptedException`

Có thể phá lifecycle thread và mất lý do hủy. Ném lại hoặc phục hồi cờ interrupt, giữ cause nếu phải wrap.

### 19.7. Không quan sát suppressed

Lỗi cleanup có thể bị bỏ quên nếu chỉ gọi `getCause()`. Dùng formatter hỗ trợ suppressed hoặc kiểm tra `getSuppressed()` trong trường hợp cần.

### 19.8. Coi một exception class là root-cause diagnosis cuối

`IOException`, `SQLException` hoặc timeout là **triệu chứng kỹ thuật quan sát được**; vẫn cần xem hạ tầng, trạng thái và phụ thuộc khác.

### 19.9. In stack trace trực tiếp ra client

Có nguy cơ lộ nội bộ. Boundary bên ngoài nên trả code/message an toàn và request ID, trong khi log nội bộ bảo vệ throwable.

### 19.10. Bỏ qua cấu hình encoder/collector

Code có `log.error("...", e)` nhưng JSON layout chỉ lưu message hoặc hệ thống drop/cắt stack trace. Kiểm chứng đến đích lưu thực tế.

## 20. Checklist triển khai

- [ ] Khi wrap exception, luôn cân nhắc constructor `(message, cause)`.
- [ ] Không thay cause chain bằng `getMessage()`/`toString()` khi tạo lỗi tầng trên.
- [ ] Rethrow cùng throwable nếu không cần đổi abstraction.
- [ ] Truyền **`Throwable` thật** cho JUL, SLF4J, Log4j 2 hoặc logging API tương ứng.
- [ ] Giữ cả wrapper bối cảnh nghiệp vụ và cause sâu hơn; không chỉ in deepest message.
- [ ] Hiểu khác nhau giữa `getCause()` và `getSuppressed()`.
- [ ] Với async wrappers, không unwrap mù `CompletionException`/`ExecutionException`.
- [ ] Khi bắt `InterruptedException`, xử lý interrupt đúng contract; không nuốt tín hiệu hủy.
- [ ] Chọn một error boundary chịu trách nhiệm log throwable đầy đủ, tránh duplicate stack.
- [ ] Không log full stack cho lỗi validation dự kiến ở tần suất cao nếu không có nhu cầu.
- [ ] Dùng error code và correlation ID ổn định, không lấy exception message thô làm metric label.
- [ ] Không lộ stack trace/PII/secret cho client hoặc sink không được phép.
- [ ] Kiểm tra logging encoder, async queue, collector và nơi lưu có giữ/có quyền truy vấn throwable.
- [ ] Test quan hệ `wrapper.getCause() == original`, suppressed, rethrow, async và redaction.
- [ ] Điều tra root cause bằng log + trace + metrics + trạng thái thực, không kết luận chỉ từ exception cuối.

**Kết luận:** **Preserve root cause** nghĩa là **bổ sung context mà không phá chuỗi nguyên nhân**: wrap bằng `new ...Exception("context", original)`, truyền **Throwable** vào logger, giữ cả `Caused by` và `Suppressed`, đồng thời chọn boundary ghi log có trách nhiệm. Nhờ đó một dòng lỗi ở tầng nghiệp vụ vẫn dẫn người vận hành đến lỗi kỹ thuật phát sinh ban đầu, nhưng không đánh đổi quyền riêng tư và độ tin cậy của hệ thống logging.
