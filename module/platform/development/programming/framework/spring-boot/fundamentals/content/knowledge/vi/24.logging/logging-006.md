# Tham số hóa thông điệp và ghi exception kèm stack trace

Trong ứng dụng Spring Boot, logging không chỉ là ghi vài dòng chữ ra console. Log giúp biết thao tác nào đã xảy ra, dữ liệu ngữ cảnh nào liên quan, lỗi bắt đầu từ đâu và stack trace dẫn qua những phương thức nào. Nhưng nếu ghi log không đúng cách, ứng dụng có thể vừa chậm, vừa thiếu thông tin để chẩn đoán sự cố.

Hai kỹ thuật quan trọng nhất trong bài này là:

1. **Tham số hóa thông điệp:** dùng placeholder `{}` của SLF4J thay vì nối chuỗi hoặc gọi `String.format(...)` trước mỗi lần ghi log.
2. **Ghi exception đúng cách:** truyền đối tượng `Throwable` vào đúng vị trí để logging framework in stack trace, thay vì chỉ ghi `exception.getMessage()`.

Bài học thuộc chương **Logging** của **Spring Boot Fundamentals**. Chúng ta sẽ dùng API `org.slf4j.Logger` và `LoggerFactory`, quan sát cách Spring Boot tích hợp backend logging, phân biệt các overload có `Throwable`, tìm hiểu hiệu năng, log levels, logging có cấu trúc, và viết code Spring Boot đủ rõ để áp dụng khi chẩn đoán lỗi.

## 1. Logging trong Spring Boot gồm những lớp nào?

Khi bạn viết:

```java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);
```

bạn đang sử dụng **SLF4J API**. SLF4J là facade: nó cung cấp giao diện gọi log thống nhất, còn việc định dạng và xuất log do logging provider/backend thực hiện.

Trong một ứng dụng Spring Boot điển hình:

```text
Service / Controller / Component
              │
              ▼
       SLF4J Logger API
              │
              ▼
      Logging provider/backend
       (thường là Logback)
              │
              ▼
   Console / file / hệ thu thập log
```

Spring Boot starters thông thường mang theo `spring-boot-starter-logging`, vốn cấu hình Logback làm backend mặc định. Spring Boot cũng có khả năng tích hợp các backend khác như Log4j2 khi dependency được cấu hình phù hợp.

**Đừng nhầm API với backend:**

- `Logger`, `LoggerFactory`, placeholder `{}`: cách lập trình với SLF4J.
- Pattern layout, appenders, rolling file, JSON encoder: cách backend thực sự xuất log.
- `logging.level.*` trong Spring Boot: cấu hình mức log cho package/class, được Boot chuyển đến logging system.

### 1.1. Ví dụ logger trong service

```java
package com.example.demo.order;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void process(String orderId) {
        log.info("Starting order processing: orderId={}", orderId);
    }
}
```

Kết quả phần message có thể là:

```text
Starting order processing: orderId=ORD-123
```

Timestamp, mức INFO, thread và tên logger có thể được backend thêm vào. Những phần đó không phải nội dung bạn tự nối vào `log.info(...)`.

### 1.2. Nên đặt logger ở đâu?

Thường dùng một logger cho mỗi class:

```java
private static final Logger log =
        LoggerFactory.getLogger(MyService.class);
```

Cách này:

- Cho biết log đến từ class nào.
- Phù hợp với cấu hình `logging.level.com.example...`.
- Tránh phải tạo logger mới trong mỗi method.
- Dễ chuyển giữa các backend thông qua SLF4J.

Bạn có thể dùng annotation `@Slf4j` của Lombok để sinh field logger, nhưng đó là tiện ích compile-time. Bài này dùng Java thông thường để thấy rõ API và không phụ thuộc Lombok.

## 2. Vì sao phải tham số hóa thông điệp?

Giả sử một service xử lý đơn hàng:

```java
String orderId = "ORD-123";
int attempt = 2;
```

Có ít nhất ba cách ghi thông tin này.

**Cách 1 — Nối chuỗi:**

```java
log.debug(
        "Retrying order " + orderId + " at attempt " + attempt
);
```

**Cách 2 — Định dạng trước:**

```java
log.debug(String.format(
        "Retrying order %s at attempt %d",
        orderId,
        attempt
));
```

**Cách 3 — Dùng placeholder SLF4J:**

```java
log.debug(
        "Retrying order {} at attempt {}",
        orderId,
        attempt
);
```

Cả ba có thể tạo cùng message, nhưng cách 3 là lựa chọn thông dụng và phù hợp nhất với SLF4J.

Lý do chính: **SLF4J có thể hoãn công việc định dạng message** cho đến khi biết log level tương ứng có được bật hay không.

### 2.1. Khi DEBUG bị tắt

Giả sử:

```properties
logging.level.com.example.demo=INFO
```

Khi đó `log.debug(...)` không được xuất.

Với nối chuỗi:

```java
log.debug("Order " + orderId + " attempt " + attempt);
```

Java vẫn phải đánh giá phép nối chuỗi trước khi gọi method `debug(...)`. Log statement có thể không ghi dòng nào, nhưng một phần công việc tạo chuỗi đã được thực hiện.

Với placeholder:

```java
log.debug(
        "Order {} attempt {}",
        orderId,
        attempt
);
```

SLF4J có thể bỏ qua việc format chuỗi khi DEBUG bị tắt.

**Giới hạn quan trọng:** Java vẫn đánh giá biểu thức đối số trước khi gọi method. Nếu bạn viết `expensiveOperation()` ở vị trí argument, phương thức đó vẫn có thể chạy dù log bị tắt. Chúng ta sẽ xử lý riêng ở phần hiệu năng.

### 2.2. Vì sao không dùng printf-style?

SLF4J dùng `{}`, không phải `%s` hay `%d`.

Sai nếu kỳ vọng SLF4J tự thay giá trị:

```java
log.info("Order %s has %d items", orderId, itemCount);
```

Các ký hiệu `%s` và `%d` thuộc `String.format`, không phải cú pháp parameterized message của SLF4J.

Đúng:

```java
log.info("Order {} has {} items", orderId, itemCount);
```

Tương tự, `{0}` thường thuộc `MessageFormat`, không phải placeholder của SLF4J.

## 3. Cú pháp placeholder {} cơ bản

SLF4J dùng cặp dấu ngoặc nhọn rỗng:

```text
{}
```

Ví dụ một tham số:

```java
log.info("Order created: {}", orderId);
```

Hai tham số:

```java
log.info(
        "Order {} has status {}",
        orderId,
        status
);
```

Ba tham số:

```java
log.info(
        "Order {} for customer {} has {} items",
        orderId,
        customerId,
        itemCount
);
```

Trong các ví dụ này, mỗi placeholder tương ứng một argument theo thứ tự từ trái sang phải.

### 3.1. Dùng tên trường ngay trong message

Một thông điệp giàu ngữ cảnh thường dễ tìm kiếm hơn khi sử dụng `key=value`:

```java
log.info(
        "Order created: orderId={} customerId={} amount={}",
        orderId,
        customerId,
        amount
);
```

Ví dụ:

```text
Order created: orderId=ORD-123 customerId=C-42 amount=250000
```

Cách này giúp người đọc nhận biết từng giá trị mà không phải đoán vị trí.

Tuy nhiên, `key=value` trong message vẫn là **văn bản**, không đồng nghĩa backend đã phát hành một structured field thực sự. Với JSON logging hoặc structured logging, cần dùng đúng API/encoder hỗ trợ field có cấu trúc.

### 3.2. Đối số không phải String

SLF4J chấp nhận nhiều kiểu:

```java
log.info("Retry count={}", retryCount);
log.info("Payment successful={}", successful);
log.info("Created at={}", createdAt);
log.info("Currency={}", currency);
```

Backend/message formatter sẽ chuyển chúng thành chuỗi khi định dạng.

Hãy để ý rằng `toString()` của object có thể lộ thông tin nhạy cảm hoặc tốn công xử lý. Không phải object nào cũng nên đưa trực tiếp vào log.

### 3.3. Khi số placeholder và argument không khớp

Ví dụ:

```java
log.info("Order {} status {}", orderId);
```

Có hai placeholder nhưng chỉ một argument thông thường. Kết quả có thể để lại placeholder chưa được thay:

```text
Order ORD-123 status {}
```

Ngược lại:

```java
log.info("Order {}", orderId, status);
```

Có thể có argument không được dùng trong việc tạo message, tùy overload và logic xử lý `Throwable`. Hãy giữ số placeholder khớp với **số argument dùng làm dữ liệu của message**.

Không nhất thiết mọi argument đều là giá trị thay thế: một `Throwable` cuối cùng có thể được tách làm cause, không dùng để điền placeholder.

## 4. Dùng tham số hóa thay vì nối chuỗi

So sánh:

```java
log.info("Received order " + orderId);
```

với:

```java
log.info("Received order {}", orderId);
```

Cách thứ hai rõ ràng hơn và cho phép bỏ qua formatting khi level không được bật.

Ví dụ với nhiều biến:

```java
log.debug(
        "Calculated shipping: orderId={} distanceKm={} fee={}",
        orderId,
        distanceKm,
        shippingFee
);
```

thay cho:

```java
log.debug(
        "Calculated shipping: orderId="
                + orderId
                + " distanceKm="
                + distanceKm
                + " fee="
                + shippingFee
);
```

Sự khác biệt càng đáng chú ý ở những đoạn code chạy nhiều lần trong một request.

### 4.1. Cẩn thận với String.format

Sai cho logging hiệu quả:

```java
log.debug(String.format(
        "Batch %s processed %d records",
        batchId,
        processedCount
));
```

`String.format` được gọi **trước** `log.debug`, bất kể DEBUG đang bật hay tắt.

Tốt hơn:

```java
log.debug(
        "Batch {} processed {} records",
        batchId,
        processedCount
);
```

Tương tự, tránh `MessageFormat.format(...)` hoặc `String#formatted(...)` khi chỉ muốn tạo message cho SLF4J.

### 4.2. Đừng format dữ liệu từ trước chỉ để đưa vào log

Ví dụ:

```java
String formattedAmount = formatCurrency(amount);
log.debug("Order amount={}", formattedAmount);
```

Dù dùng `{}`, phương thức `formatCurrency` đã chạy trước log statement.

Nếu formatting tốn chi phí đáng kể và chỉ phục vụ DEBUG, bạn có thể dùng guard:

```java
if (log.isDebugEnabled()) {
    log.debug(
            "Order amount={}",
            formatCurrency(amount)
    );
}
```

Hoặc sử dụng SLF4J 2.x Fluent API với supplier ở phần sau.

## 5. Exception gồm những thông tin gì?

Trong Java, các exception như `IllegalArgumentException`, `IOException`, `DataAccessException` đều kế thừa `Throwable` theo hệ thống kiểu.

Một exception thường có:

- **Type:** tên class, ví dụ `java.io.IOException`.
- **Message:** mô tả ngắn, có thể `null`.
- **Stack trace:** các stack frames cho biết đường gọi tại thời điểm throwable được tạo/fill stack trace.
- **Cause:** exception gốc hoặc exception được wrap.
- **Suppressed exceptions:** thông tin phụ, thường gặp khi đóng resource.

Ví dụ:

```java
try {
    throw new IllegalStateException("Inventory unavailable");
} catch (IllegalStateException ex) {
    System.out.println(ex.getClass().getName());
    System.out.println(ex.getMessage());
}
```

Chỉ hai dòng trên không cho biết file/method/line nào đã gây ra exception.

### 5.1. Stack trace cho biết điều gì?

Một stack trace đơn giản:

```text
java.lang.IllegalStateException: Inventory unavailable
    at com.example.demo.InventoryClient.fetch(InventoryClient.java:42)
    at com.example.demo.OrderService.reserve(OrderService.java:85)
    at com.example.demo.OrderController.place(OrderController.java:31)
```

Nó giúp lần ngược từ nơi throwable xuất hiện đến call site.

Khi exception có cause:

```text
com.example.demo.OrderProcessingException: Cannot reserve inventory
    at com.example.demo.OrderService.reserve(OrderService.java:91)
Caused by: java.net.SocketTimeoutException: Read timed out
    at ...
```

Nếu chỉ log exception message, bạn có thể mất cả stack trace và cause chain. Đây là lý do truyền object `Throwable` trực tiếp cho logger thường là cách cần thiết khi ghi lỗi chẩn đoán.

## 6. Cách đúng để ghi exception kèm stack trace

SLF4J có overload nhận `Throwable`:

```java
logger.error(String message, Throwable throwable);
```

Ví dụ:

```java
try {
    inventoryClient.reserve(orderId);
} catch (RuntimeException ex) {
    log.error("Inventory reservation failed", ex);
    throw ex;
}
```

Khi ERROR được bật, backend thông thường sẽ ghi message và stack trace của `ex`.

Phần log minh họa:

```text
ERROR ... Inventory reservation failed
java.lang.IllegalStateException: Inventory unavailable
    at com.example.demo.InventoryClient.reserve(InventoryClient.java:42)
    at com.example.demo.OrderService.process(OrderService.java:85)
    ...
```

Đó là điều `log.error("...", ex)` làm khác với `log.error("{}", ex.getMessage())`.

### 6.1. Truyền Throwable, không chỉ message

Chưa đủ khi cần stack trace:

```java
log.error("Inventory failed: {}", ex.getMessage());
```

Dòng này ghi một chuỗi, không truyền `Throwable` vào logger. Bạn thường chỉ thấy:

```text
Inventory failed: Inventory unavailable
```

Thông tin loại exception, các frames, cause chain và suppressed exceptions có thể không xuất hiện.

Đúng khi cần stack trace:

```java
log.error("Inventory reservation failed", ex);
```

### 6.2. Không cần gọi ex.printStackTrace()

Không nên:

```java
catch (Exception ex) {
    ex.printStackTrace();
}
```

`printStackTrace()` thường ghi ra `System.err` mà không đi qua logging backend được ứng dụng cấu hình. Nó khó đồng bộ về level, appender, structured logging, correlation ID hoặc chính sách thu thập.

Tốt hơn:

```java
catch (Exception ex) {
    log.error("Unexpected failure during import", ex);
}
```

Đoạn code vẫn phải có chính sách xử lý lỗi hợp lý: log không thay thế việc propagate, retry, rollback hoặc trả về response.

### 6.3. Không dùng getStackTrace() làm đối số log

Sai:

```java
log.error("Unexpected failure: {}", ex.getStackTrace());
```

`getStackTrace()` trả về mảng `StackTraceElement[]`, không phải `Throwable`. Việc format mảng không tương đương với stack trace đầy đủ của exception, đặc biệt khi có cause/suppressed.

Đúng:

```java
log.error("Unexpected failure", ex);
```

## 7. Kết hợp placeholder và Throwable đúng cách

Trong ứng dụng thực tế, chúng ta vừa muốn biết ngữ cảnh nghiệp vụ, vừa muốn có stack trace.

Ví dụ:

```java
try {
    paymentGateway.charge(orderId, amount);
} catch (PaymentGatewayException ex) {
    log.error(
            "Payment failed: orderId={} amount={}",
            orderId,
            amount,
            ex
    );
    throw ex;
}
```

Phần message có thể là:

```text
Payment failed: orderId=ORD-123 amount=250000
```

và theo sau là stack trace của `ex`.

### 7.1. Vì sao có hai placeholder nhưng ba đối số?

Hai argument đầu là giá trị cho `{}`:

- `orderId`.
- `amount`.

Argument cuối là `Throwable`. SLF4J nhận diện throwable ở vị trí cuối của danh sách argument và có thể tách nó thành **cause** để backend ghi stack trace.

Vì vậy:

```java
log.error(
        "Failed orderId={}",
        orderId,
        ex
);
```

là pattern phổ biến để log cả business context và stack trace.

### 7.2. Throwable nên đứng cuối

Nên viết:

```java
log.error(
        "Failed to publish event: eventId={} topic={}",
        eventId,
        topic,
        ex
);
```

Tránh viết:

```java
log.error(
        "Failed to publish event: eventId={} topic={}",
        ex,
        eventId,
        topic
);
```

Trong trường hợp thứ hai, `ex` nằm giữa các argument. Nó không còn ở vị trí truyền cause theo quy tắc thông dụng; message có thể được format không như mong muốn và stack trace có thể bị thiếu.

**Quy tắc dễ nhớ:** khi cần vừa tham số hóa message vừa ghi stack trace, để `Throwable` ở **đối số cuối cùng**.

### 7.3. Đếm placeholder không gồm Throwable cuối

Đúng:

```java
log.error(
        "Cannot load customerId={} region={}",
        customerId,
        region,
        ex
);
```

Không phù hợp:

```java
log.error(
        "Cannot load customerId={} region={} exception={}",
        customerId,
        region,
        ex
);
```

Với overload/formatter nhận diện `ex` là cause cuối, `ex` không dùng để thay placeholder `exception={}`. Kết quả có thể còn placeholder chưa được thay.

Nếu muốn biết loại exception trong message **và** có stack trace, truyền type như một argument dữ liệu riêng:

```java
log.error(
        "Cannot load customerId={} errorType={}",
        customerId,
        ex.getClass().getSimpleName(),
        ex
);
```

Ở đây hai placeholder được điền bằng `customerId` và tên loại exception, còn `ex` cuối cùng cung cấp stack trace.

## 8. Lưu ý quan trọng về overload Java: log.error("...", ex)

Một số developer viết:

```java
log.error("Unexpected error: {}", ex);
```

và nghĩ rằng `{}` sẽ được thay bằng chuỗi exception.

Nhưng SLF4J có overload riêng:

```java
void error(String message, Throwable t);
```

Do `Throwable` là kiểu cụ thể hơn `Object`, lời gọi với `ex` kiểu exception có thể được Java chọn vào overload `error(String, Throwable)`. Khi đó message `"Unexpected error: {}"` được giữ nguyên như literal, còn `ex` được dùng làm cause.

Kết quả có thể là:

```text
Unexpected error: {}
java.lang.IllegalStateException: ...
    at ...
```

Để không gây nhập nhằng, hãy viết rõ mục đích.

**Chỉ cần message cố định và stack trace:**

```java
log.error("Unexpected error occurred", ex);
```

**Cần một giá trị ngữ cảnh và stack trace:**

```java
log.error(
        "Unexpected error: orderId={}",
        orderId,
        ex
);
```

**Chỉ muốn text của exception, không cần stack trace:**

```java
log.warn(
        "Recoverable error message={}",
        ex.getMessage()
);
```

Cách thứ ba có thể phù hợp với lỗi đã được xử lý và có chủ đích không cần full trace. Nhưng không sử dụng nó thay thế cho logging exception khi đang cần điều tra nguyên nhân.

### 8.1. Một vài trường hợp dễ nhầm

| Code | Ý nghĩa thường gặp |
|---|---|
| `log.error("Database unavailable", ex)` | Ghi message và Throwable cause |
| `log.error("Database failed: id={}", id, ex)` | Điền `id` và ghi stack trace từ `ex` |
| `log.error("Database failed: {}", ex)` | Có thể chọn overload `Throwable`; `{}` không được điền |
| `log.error("Database failed: {}", ex.getMessage())` | Chỉ điền message string, không có Throwable cause |
| `log.error("Database failed: id={} cause={}", id, ex)` | Placeholder cuối có thể không được điền vì `ex` là cause |
| `log.error("Database failed: id={} causeType={}", id, ex.getClass().getSimpleName(), ex)` | Hai placeholder dữ liệu và một Throwable cause |

Dù SLF4J hỗ trợ phát hiện Throwable cuối trong các parameterized overloads, code vẫn nên **truyền cause một cách rõ ràng**, tránh đối số gây nhầm.

### 8.2. Logger.error(String, Object, Object) và varargs

SLF4J có các overload tối ưu cho một hoặc hai argument và overload varargs cho nhiều argument. Đây là chi tiết API/performance.

Ví dụ:

```java
log.error("Order {} failed", orderId, ex);
```

là một lời gọi hợp lệ có placeholder dữ liệu và throwable cuối, dù Java có thể chọn overload nhận hai `Object`. Message formatter nhận diện argument cuối là Throwable để backend xử lý.

Khi danh sách argument dài hơn:

```java
log.error(
        "Failed: orderId={} itemId={} warehouse={}",
        orderId,
        itemId,
        warehouseId,
        ex
);
```

quy tắc đặt Throwable cuối vẫn phù hợp.

## 9. Chọn đúng mức log khi có exception

`Logger` có các mức thông dụng:

- `TRACE`: thông tin rất chi tiết, thường dùng khi điều tra luồng xử lý thấp.
- `DEBUG`: dữ liệu chẩn đoán dành cho developer.
- `INFO`: các mốc hoạt động đáng quan tâm.
- `WARN`: tình huống bất thường nhưng ứng dụng có thể tiếp tục hoặc phục hồi.
- `ERROR`: lỗi khiến một thao tác thất bại hoặc cần hành động điều tra.

Một exception được ném **không tự động có nghĩa phải log ở ERROR**. Hãy xét tác động và chính sách xử lý.

Ví dụ lỗi nhập liệu dự kiến:

```java
if (quantity <= 0) {
    log.warn(
            "Rejected invalid order quantity: orderId={} quantity={}",
            orderId,
            quantity
    );

    throw new IllegalArgumentException(
            "Quantity must be positive"
    );
}
```

Có thể log WARN, hoặc không log tại service mà để boundary xử lý theo chính sách chung. Việc in full stack trace cho mọi lỗi validation dự kiến có thể gây nhiễu.

Ví dụ lỗi database không dự kiến:

```java
catch (DataAccessException ex) {
    log.error(
            "Database operation failed: orderId={}",
            orderId,
            ex
    );
    throw ex;
}
```

Trường hợp này log ERROR kèm trace có thể hữu ích, nhưng hãy lưu ý tránh duplicate logging khi lỗi được ghi lại ở tầng trên.

### 9.1. Bảng gợi ý

| Tình huống | Mức log thường cân nhắc | Cần stack trace? |
|---|---|---|
| Khởi động thành công một tác vụ | INFO | Không |
| Thông số nội bộ để debug | DEBUG | Không |
| Retry một lỗi tạm thời có thể phục hồi | WARN hoặc DEBUG | Tùy nhu cầu |
| Lỗi input hợp lệ theo business rules | WARN/INFO hoặc không log | Thường không cần full trace |
| Truy vấn database thất bại không dự kiến | ERROR | Thường có |
| Tính năng phụ tùy chọn bị vô hiệu hóa có chủ đích | INFO | Không |
| Lỗi hệ thống khiến request thất bại | ERROR ở boundary xử lý | Thường có |

Không có bảng mức log nào thay thế chính sách vận hành của đội ngũ. Quan trọng là nhất quán, có ngữ cảnh và đủ dữ liệu để hành động.

## 10. Ghi ở đâu để tránh lặp stack trace?

Một exception có thể đi qua nhiều tầng:

```text
Repository throws DataAccessException
             │
             ▼
Service wraps OrderProcessingException
             │
             ▼
Controller / exception handler
             │
             ▼
HTTP 500 response
```

Nếu mọi tầng đều log `ERROR` kèm stack trace, cùng một lỗi có thể xuất hiện ba lần.

Ví dụ dễ gây duplicate:

```java
// Repository
catch (DataAccessException ex) {
    log.error("Repository failed", ex);
    throw ex;
}

// Service
catch (DataAccessException ex) {
    log.error("Service failed", ex);
    throw new OrderProcessingException("Cannot process", ex);
}

// Controller
catch (OrderProcessingException ex) {
    log.error("Request failed", ex);
    throw ex;
}
```

Hệ quả:

- Log volume tăng nhanh.
- Một incident có thể trông giống nhiều sự cố độc lập.
- Tốn chi phí lưu trữ và tìm kiếm.
- Khó xác định nơi cần xử lý chính.

### 10.1. Nguyên tắc log hoặc propagate có chủ đích

Một nguyên tắc thực hành hữu ích:

**Tại một error boundary, ghi log đủ ngữ cảnh một lần; ở các tầng thấp hơn, ưu tiên thêm context vào exception hoặc propagate đúng cause nếu chưa có lý do vận hành để log.**

Ví dụ tầng service chỉ wrap:

```java
public Receipt placeOrder(String orderId) {
    try {
        return repository.createReceipt(orderId);
    } catch (DataAccessException ex) {
        throw new OrderProcessingException(
                "Cannot create receipt for order " + orderId,
                ex
        );
    }
}
```

Boundary xử lý log:

```java
log.error(
        "Order request failed: orderId={}",
        orderId,
        ex
);
```

Từ trace, bạn vẫn có thể thấy `Caused by: DataAccessException` nếu exception được wrap với original cause.

### 10.2. Khi nào tầng thấp cũng nên log?

Có thể log khi:

- Exception được **xử lý và không propagate**; nếu không log thì mất tín hiệu về sự cố.
- Có một sự kiện vận hành độc lập cần quan sát, ví dụ retry thứ ba đã bị bỏ qua.
- Một tầng biết thông tin quan trọng mà tầng trên không thể tái tạo, và thông tin đó không nên đưa vào exception.

Khi ấy, chọn level và chi tiết vừa đủ. Không bắt buộc tầng thấp luôn log stack trace ở ERROR.

## 11. Giữ cause khi wrap exception

Khi cần chuyển exception hạ tầng thành exception nghiệp vụ, hãy bảo toàn cause.

Chưa tốt:

```java
catch (IOException ex) {
    throw new ImportFailedException(
            "Cannot read import file"
    );
}
```

Exception mới không liên kết với `IOException` ban đầu, khiến trace mất thông tin nguyên nhân.

Tốt:

```java
catch (IOException ex) {
    throw new ImportFailedException(
            "Cannot read import file",
            ex
    );
}
```

Custom exception:

```java
package com.example.demo.importer;

public class ImportFailedException extends RuntimeException {

    public ImportFailedException(
            String message,
            Throwable cause
    ) {
        super(message, cause);
    }
}
```

Khi được log:

```java
log.error("Import workflow failed: batchId={}", batchId, ex);
```

stack trace có thể chứa `Caused by: java.io.IOException`, giúp bạn thấy lỗi gốc.

### 11.1. Không tạo một exception mới chỉ để log

Không phù hợp:

```java
catch (IOException ex) {
    log.error(
            "Import failed",
            new RuntimeException("Import failed")
    );
}
```

Bạn đã tạo một Throwable mới không mang cause của `ex` và stack trace có thể bắt đầu ở vị trí tạo exception mới, không phải lỗi I/O gốc.

Đúng:

```java
catch (IOException ex) {
    log.error("Import failed", ex);
}
```

Hoặc wrap có cause rồi propagate theo API của service.

## 12. Exception message không phải stack trace

Hai lời gọi sau không tương đương:

```java
log.error(
        "Failed to load order: {}",
        ex.getMessage()
);
```

```java
log.error(
        "Failed to load order",
        ex
);
```

Lời gọi đầu chỉ điền một chuỗi; lời gọi sau truyền Throwable cho logging backend.

Thông thường:

- `ex.getMessage()` chỉ cung cấp một mô tả ngắn và có thể `null`.
- `ex.toString()` thường chứa loại exception cùng message.
- `ex.getStackTrace()` trả về mảng các frame, không bao gồm trình bày đầy đủ cause/suppressed tự động.
- Truyền `ex` như cause cho logger cho phép backend render exception theo cấu hình.

### 12.1. Vì sao không dùng ex.toString() cho mọi lỗi?

Ví dụ:

```java
log.error(
        "Failed: {}",
        ex.toString()
);
```

Bạn có thể thấy:

```text
Failed: java.io.IOException: Connection reset
```

Nhưng vẫn không có đường gọi đầy đủ.

Khi cần chẩn đoán lỗi hệ thống, dùng:

```java
log.error("Failed to communicate with remote service", ex);
```

### 12.2. Khi nào log message-only là hợp lý?

Khi lỗi đã được dự kiến và xử lý, ví dụ người dùng gửi mã khuyến mại hết hạn:

```java
log.info(
        "Coupon rejected: couponId={} reason={}",
        couponId,
        "expired"
);
```

Không nhất thiết phải ném rồi log stack trace cho một điều kiện nghiệp vụ bình thường.

**Tham số hóa message** và **ghi stack trace** là hai kỹ thuật riêng. Bạn cần chủ động quyết định lúc nào dùng cả hai.

## 13. Log hiệu quả khi level bị tắt

Một ưu điểm của `{}` là hoãn formatting, nhưng đừng hiểu nhầm rằng mọi đối số đều được đánh giá lười (lazy) theo mặc định.

Ví dụ:

```java
log.debug(
        "Order snapshot={}",
        buildExpensiveOrderSnapshot(order)
);
```

Java đánh giá `buildExpensiveOrderSnapshot(order)` trước khi gọi `debug(...)`. Nếu DEBUG tắt, công việc này vẫn đã xảy ra.

### 13.1. Dùng isDebugEnabled khi tính toán đắt

```java
if (log.isDebugEnabled()) {
    log.debug(
            "Order snapshot={}",
            buildExpensiveOrderSnapshot(order)
    );
}
```

Cách này tránh tính snapshot khi DEBUG tắt.

Không cần bao mọi lời gọi `log.debug("id={}", id)` bằng `isDebugEnabled()`. Với các biến đơn giản có sẵn, placeholder đã đáp ứng tốt mục tiêu hiệu năng; guard thêm có thể làm code dài không cần thiết.

### 13.2. toString cũng có thể đắt hoặc lộ dữ liệu

```java
log.debug("Order object={}", order);
```

Nếu DEBUG bật, SLF4J cần tạo text từ `order`, thường qua `toString()`. `toString()` có thể:

- Duyệt một object graph rất lớn.
- Trigger lazy-loaded relation nếu implementation sử dụng dữ liệu liên quan.
- Chứa dữ liệu khách hàng hoặc thông tin thanh toán.
- Gây log dài, khó tìm kiếm.

Vì vậy, ngay cả khi dùng placeholder, nên ưu tiên những field được phép ghi và có ý nghĩa chẩn đoán:

```java
log.debug(
        "Order state: orderId={} status={} itemCount={}",
        order.id(),
        order.status(),
        order.itemCount()
);
```

## 14. Fluent Logging API trong SLF4J 2.x

SLF4J 2.x cung cấp **Fluent API** qua các phương thức như `atDebug()` và `atError()`.

Ví dụ:

```java
log.atInfo()
        .addArgument(orderId)
        .addArgument(status)
        .log("Order {} moved to status {}");
```

Nó tương tự:

```java
log.info(
        "Order {} moved to status {}",
        orderId,
        status
);
```

Fluent API hữu ích khi cần supplier, key-value pairs hoặc cause được thiết lập tường minh.

**Lưu ý phiên bản:** các API Fluent `atInfo()`, `addArgument(...)`, `addKeyValue(...)` và `setCause(...)` thuộc SLF4J 2.x. Các project Spring Boot hiện đại thường dùng dòng SLF4J này; ứng dụng Boot cũ với SLF4J 1.7 không có các API đó. Kiểm tra dependency version thực tế trước khi áp dụng.

### 14.1. Supplier giúp trì hoãn tính toán

```java
log.atDebug()
        .addArgument(() -> buildExpensiveOrderSnapshot(order))
        .log("Order snapshot={}");
```

Ở đây argument được cung cấp qua `Supplier`. Khi DEBUG bị tắt, SLF4J có thể bỏ qua việc gọi supplier.

So sánh:

```java
// Biểu thức được Java đánh giá ngay.
log.debug(
        "Snapshot={}",
        buildExpensiveOrderSnapshot(order)
);

// Dùng supplier để hoãn tính toán.
log.atDebug()
        .addArgument(() -> buildExpensiveOrderSnapshot(order))
        .log("Snapshot={}");
```

**Hạn chế:** supplier chỉ nên có nhiệm vụ tạo dữ liệu để log, không gây side effect nghiệp vụ. Nếu DEBUG tắt thì supplier có thể không chạy; không được đặt cập nhật database hoặc thay đổi trạng thái vào supplier.

### 14.2. setCause giúp chỉ rõ exception

Fluent API cho phép:

```java
log.atError()
        .setCause(ex)
        .log("Cannot complete payment");
```

Hoặc cùng các argument dữ liệu:

```java
log.atError()
        .addArgument(orderId)
        .addArgument(amount)
        .setCause(ex)
        .log("Payment failed: orderId={} amount={}");
```

Cách này thể hiện tường minh rằng `ex` là cause, không phải giá trị cần điền vào `{}`.

### 14.3. Key-value pairs

```java
log.atError()
        .addKeyValue("orderId", orderId)
        .addKeyValue("attempt", attempt)
        .setCause(ex)
        .log("Payment gateway call failed");
```

Những cặp key-value được đưa vào logging event theo khả năng của SLF4J 2.x. **Chúng chỉ hiện thành field JSON hoặc thành văn bản theo cách backend/layout/encoder được cấu hình**. Đừng giả định mọi console pattern sẽ xuất đầy đủ các key-value pairs nếu chưa kiểm tra cấu hình backend.

### 14.4. Đừng quên log(...) ở cuối chain

Đúng:

```java
log.atInfo()
        .addKeyValue("orderId", orderId)
        .log("Order created");
```

Thiếu `.log(...)` thì event chưa được phát hành. Fluent builder được dùng để chuẩn bị event; thao tác terminal `log(...)` mới thực sự yêu cầu ghi log.

## 15. Structured logging và tham số hóa message

Nhiều hệ thống thu thập log muốn một event có các trường tách biệt:

```json
{
  "level": "ERROR",
  "message": "Payment gateway call failed",
  "orderId": "ORD-123",
  "attempt": 2,
  "exception": "java.net.SocketTimeoutException: Read timed out"
}
```

Đây là ví dụ khái niệm. Các field thực tế, cách serialize stack trace và tên khóa tùy backend/encoder cùng phiên bản Spring Boot.

So sánh hai cách:

**Văn bản có placeholder:**

```java
log.error(
        "Payment failed orderId={} attempt={}",
        orderId,
        attempt,
        ex
);
```

**Fluent key-value:**

```java
log.atError()
        .addKeyValue("orderId", orderId)
        .addKeyValue("attempt", attempt)
        .setCause(ex)
        .log("Payment failed");
```

Với một structured encoder phù hợp, cách thứ hai giúp hệ thống log query theo field `orderId` thay vì chỉ tìm chuỗi.

### 15.1. Không phải cứ message có key=value là JSON

```text
Payment failed orderId=ORD-123 attempt=2
```

vẫn là một chuỗi message. Hệ thống thu thập có thể parse text nếu cấu hình parser, nhưng điều đó khác với việc backend xuất structured attributes ngay từ đầu.

### 15.2. Tham số hóa không tự che dữ liệu nhạy cảm

Dù log bằng `{}` hay structured fields, nếu bạn truyền password/token vào logger, dữ liệu đó vẫn có thể bị ghi.

Ví dụ **không nên viết**:

```java
log.info(
        "User login: username={} password={}",
        username,
        password
);
```

Không nên:

```java
log.debug("Authorization header={}", authorizationHeader);
```

Kỹ thuật formatting không thay thế data classification, redaction và access control.

## 16. Chọn thông tin ngữ cảnh nào khi log exception?

Một stack trace cho biết lỗi phát sinh ở đường gọi nào, nhưng thường **không chứa đầy đủ business context**.

Ví dụ:

```java
log.error("Connection timed out", ex);
```

có stack trace nhưng không nói request đang xử lý order nào.

Tốt hơn:

```java
log.error(
        "Payment request timed out: orderId={} gateway={} attempt={}",
        orderId,
        gatewayName,
        attempt,
        ex
);
```

Các trường hữu ích tùy ngữ cảnh:

- ID nghiệp vụ không nhạy cảm: `orderId`, `batchId`, `jobId`.
- Tên dependency hoặc integration: `paymentGateway`, `inventory-service`.
- Loại thao tác: `reserve`, `publish`, `import`.
- Số lần thử: `attempt`.
- Trạng thái hoặc phase: `validation`, `commit`.
- Mã lỗi ổn định: `errorCode`.
- Trace/correlation ID nếu ứng dụng có cơ chế observability tương ứng.

### 16.1. Message nên diễn tả sự kiện, không lặp exception message

Ít ngữ cảnh:

```java
log.error("Error", ex);
```

Tốt hơn:

```java
log.error(
        "Failed to reserve inventory: orderId={} warehouseId={}",
        orderId,
        warehouseId,
        ex
);
```

Bạn không nhất thiết nối `ex.getMessage()` vào message. Khi Throwable được truyền đúng cách, backend thường hiển thị exception type và message trong phần stack trace.

### 16.2. Tránh log toàn bộ payload

Ví dụ không phù hợp nếu payload có dữ liệu cá nhân:

```java
log.error(
        "Payment failed for request={}",
        paymentRequest,
        ex
);
```

`paymentRequest.toString()` có thể chứa thông tin thẻ, địa chỉ hoặc dữ liệu riêng tư.

Tốt hơn:

```java
log.error(
        "Payment failed: orderId={} methodType={} attempt={}",
        orderId,
        paymentMethodType,
        attempt,
        ex
);
```

Hãy chọn field theo chính sách dữ liệu và quyền truy cập log của hệ thống.

## 17. Logging trong Spring Boot: mức log và cấu hình

Spring Boot cho phép cấu hình mức log theo package hoặc class.

Ví dụ `application.yml`:

```yaml
logging:
  level:
    root: INFO
    com.example.demo: DEBUG
    org.springframework.web: WARN
```

Ở đây:

- Logger root mặc định ghi từ INFO trở lên.
- Các logger dưới `com.example.demo` có thể ghi DEBUG.
- Logger dưới `org.springframework.web` được giảm mức chi tiết xuống WARN và ERROR.

Ví dụ `application.properties`:

```properties
logging.level.root=INFO
logging.level.com.example.demo.order=DEBUG
```

### 17.1. Nếu DEBUG bị tắt thì log đi đâu?

Một câu lệnh:

```java
log.debug("Order id={}", orderId);
```

có thể không tạo event được xuất nếu effective level của logger không cho phép DEBUG.

Điều này không có nghĩa `orderId` sai hoặc backend bị hỏng. Hãy kiểm tra level hiệu lực trước.

### 17.2. Cách chạy có thể ghi đè logging level

Ví dụ:

```bash
java -jar demo.jar --logging.level.com.example.demo.order=DEBUG
```

Command-line arguments có thể ghi đè file config theo quy tắc precedence của Spring Boot.

Với ứng dụng sản xuất, hãy cẩn thận khi bật DEBUG: log volume, thông tin request và dữ liệu nội bộ có thể tăng đáng kể.

### 17.3. Log console, file và JSON

Việc `logger.error(...)` dẫn đến console hay file phụ thuộc backend và cấu hình:

- Console logging.
- File logging.
- Rolling files.
- Structured/JSON logging nếu được cấu hình.
- Log aggregation bên ngoài (container stdout, collector, observability platform).

Không cần tự thêm timestamp, thread name, PID hoặc level vào từng message nếu pattern/encoder đã cung cấp chúng.

## 18. MDC và correlation ID: thêm ngữ cảnh xuyên suốt lời gọi

Khi một request qua controller, service và repository, nhiều log có thể liên quan đến cùng một thao tác.

SLF4J cung cấp `MDC` (Mapped Diagnostic Context) để gắn các key-value context với thread hiện tại theo cơ chế backend tương ứng.

Ví dụ:

```java
import org.slf4j.MDC;

String requestId = "req-123";

try {
    MDC.put("requestId", requestId);

    log.info("Received request");
    orderService.process("ORD-123");
} finally {
    MDC.remove("requestId");
}
```

Nếu logging pattern/encoder hỗ trợ hiển thị MDC key `requestId`, log có thể trở thành:

```text
requestId=req-123 INFO Received request
requestId=req-123 INFO Processing order ORD-123
```

### 18.1. MDC khác placeholder

Placeholder:

```java
log.info("Order id={}", orderId);
```

chỉ cung cấp argument cho message này.

MDC:

```java
MDC.put("requestId", requestId);
```

gắn context để các log event tương ứng có thể sử dụng, tùy thread/context propagation và backend configuration.

Có thể kết hợp cả hai.

### 18.2. Phải dọn MDC

Thread pool tái sử dụng thread. Nếu bạn `put` mà không `remove` hoặc `clear`, context của request trước có thể rò sang tác vụ sau.

Ví dụ an toàn với `finally`:

```java
MDC.put("jobId", jobId);

try {
    executeJob(jobId);
} finally {
    MDC.remove("jobId");
}
```

Chỉ dùng `MDC.clear()` khi thật sự sở hữu toàn bộ context trên thread, vì `clear()` có thể xóa những key do thư viện khác thiết lập.

### 18.3. Async/reactive context cần propagation riêng

MDC thường liên quan đến thread-local context. Khi code chuyển sang `@Async`, executor khác hoặc reactive pipeline, các key không nhất thiết tự đi theo execution context.

Spring Boot Micrometer/Observability có thể cung cấp cơ chế correlation/tracing khi được cấu hình phù hợp, nhưng đừng giả định mọi ứng dụng có MDC propagation sẵn.

Nếu cần request ID xuyên thread, hãy chọn giải pháp context propagation tương thích với kiểu ứng dụng đang chạy.

## 19. Logging trong Spring MVC exception handler

Một ứng dụng web thường có một điểm tập trung xử lý exception.

Ví dụ:

```java
package com.example.demo.web;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log =
            LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(OrderProcessingException.class)
    public ResponseEntity<ErrorResponse> handleOrderError(
            OrderProcessingException ex
    ) {
        log.error(
                "Order processing failed: errorCode={}",
                "ORDER_PROCESSING_FAILED",
                ex
        );

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ErrorResponse(
                        "ORDER_PROCESSING_FAILED",
                        "Unable to process the order"
                ));
    }

    public record ErrorResponse(
            String code,
            String message
    ) {
    }
}
```

Ở đây:

- Log bên server có thể ghi stack trace đầy đủ.
- Client nhận một error code và message an toàn.
- Internal exception message/stack trace không bị đưa trực tiếp vào HTTP response.
- Điểm xử lý này có thể trở thành nơi log lỗi một lần, tránh duplicate ở service.

Ví dụ giả định `OrderProcessingException` được định nghĩa trong ứng dụng và import phù hợp.

### 19.1. Không trả stack trace về client

Không nên:

```java
return ResponseEntity.internalServerError()
        .body(ex.getStackTrace());
```

Stack trace có thể để lộ package names, implementation details, thư viện hoặc dữ liệu không nên công khai. Ghi trace vào kênh server logging được bảo vệ; HTTP response nên dùng contract lỗi phù hợp.

### 19.2. Validation error có thể không cần ERROR trace

Ví dụ:

```java
@ExceptionHandler(IllegalArgumentException.class)
public ResponseEntity<ErrorResponse> handleInvalidInput(
        IllegalArgumentException ex
) {
    log.warn("Request rejected: reasonCode={}", "INVALID_INPUT");

    return ResponseEntity.badRequest()
            .body(new ErrorResponse(
                    "INVALID_INPUT",
                    "Invalid request"
            ));
}
```

Không phải mọi input sai đều là incident hệ thống. Chính sách log cần phân biệt lỗi do client với lỗi không dự kiến ở server.

## 20. Logging khi gọi dịch vụ ngoài và retry

Khi ứng dụng gọi HTTP client, database hoặc message broker, retry có thể tạo nhiều exception cho cùng một thao tác.

Giả sử một lời gọi được thử ba lần:

```text
attempt 1 -> timeout
attempt 2 -> timeout
attempt 3 -> failure
```

Nếu mỗi attempt log ERROR kèm full stack trace và cuối cùng boundary cũng log ERROR, sự cố sẽ tạo bốn stack traces.

Một chính sách hợp lý có thể là:

- Retry thất bại tạm thời: WARN hoặc DEBUG với order ID, attempt, mã lỗi.
- Khi hết retry và thao tác thất bại: một ERROR kèm stack trace của lỗi cuối (hoặc exception tổng hợp có cause).
- Nếu không retry và lỗi gây thất bại ngay: log tại error boundary.

### 20.1. Ví dụ có retry đơn giản

```java
public Receipt submitWithRetry(String orderId) {
    RuntimeException lastFailure = null;

    for (int attempt = 1; attempt <= 3; attempt++) {
        try {
            return gateway.submit(orderId);
        } catch (TransientGatewayException ex) {
            lastFailure = ex;

            log.warn(
                    "Transient gateway failure: orderId={} attempt={}",
                    orderId,
                    attempt
            );
        }
    }

    log.error(
            "Gateway retries exhausted: orderId={} attempts={}",
            orderId,
            3,
            lastFailure
    );

    throw new OrderProcessingException(
            "Cannot submit order " + orderId,
            lastFailure
    );
}
```

Ví dụ cố ý đơn giản để minh họa log policy. Trong hệ thống thực tế, cần phân loại retryable errors, backoff, timeout, idempotency và cancellation. Không nên retry mọi exception hoặc cứ loop liên tục mà không có delay.

### 20.2. Đừng mất exception cuối cùng

Nếu chỉ log một chuỗi:

```java
log.error("Retries exhausted: orderId={}", orderId);
```

bạn có thể thiếu thông tin timeout là `SocketTimeoutException`, `ConnectException` hay lỗi parse response.

Truyền `lastFailure` dưới dạng cause để giữ trace khi đây là một lỗi đáng chẩn đoán.

## 21. Security: dữ liệu không được đưa vào log

Log là dữ liệu có thể được chia sẻ rộng trong môi trường vận hành. Tham số hóa message giúp format hiệu quả, nhưng **không tự bảo vệ dữ liệu**.

Những thứ cần tránh ghi nguyên văn nếu không có chính sách cho phép:

- Password, OTP, recovery code.
- API key, bearer token, session cookie.
- Full payment card data, CVV.
- Secret trong connection string.
- Nội dung payload chứa thông tin cá nhân.
- Authorization headers.
- Khóa riêng hoặc access credentials.
- Exception message có chứa URL kèm token/query secret.

### 21.1. Ví dụ không an toàn

```java
log.error(
        "Payment request failed: payload={}",
        paymentRequest,
        ex
);
```

Nếu `paymentRequest.toString()` trả cả chi tiết thẻ hoặc thông tin cá nhân, log có thể trở thành nguồn rò rỉ.

Tốt hơn:

```java
log.error(
        "Payment request failed: orderId={} paymentMethodType={}",
        orderId,
        paymentMethodType,
        ex
);
```

### 21.2. Exception message có thể chứa bí mật

Ngay cả khi bạn chỉ viết:

```java
log.error("Remote request failed", ex);
```

exception message của một số thư viện có thể chứa URL hoặc query parameters. Đừng giả định full stack trace luôn hoàn toàn an toàn để đưa vào mọi nơi.

Khi triển khai production, cần xét chính sách redaction, backend encoder, log retention, access control và nơi log được gửi đến. Với những error types có dữ liệu nhạy cảm, hãy cân nhắc sanitize hoặc thiết kế exception message từ đầu để không đưa secret vào Throwable.

### 21.3. Log injection

Nếu dữ liệu người dùng chứa ký tự xuống dòng:

```text
ORD-123
ERROR Admin access granted
```

việc đưa trực tiếp vào text log có thể làm log nhiều dòng trông giống nhiều sự kiện, nhất là với layout không escape.

Ví dụ:

```java
log.warn("Rejected orderId={}", untrustedOrderId);
```

Parameterization không tự bảo đảm output an toàn chống log injection. Hãy dùng structured logging/encoder escape ký tự điều khiển, validate/sanitize các field không tin cậy, và không cho phép user input giả làm metadata của event.

## 22. Stack trace và hiệu năng

Ghi một stack trace có thể tốn chi phí:

- Thu thập hoặc xử lý stack frames.
- Chuyển Throwable, cause chain, suppressed exceptions thành văn bản.
- Tăng số byte ghi ra console/file hoặc gửi tới hệ thống log.
- Tăng tải I/O và chi phí lưu trữ.
- Làm khó tìm sự kiện thật sự quan trọng giữa những log lặp.

Vì vậy không nên log stack trace ở ERROR trong mọi vòng lặp hoặc mọi tình huống validation dự kiến.

### 22.1. Log level quyết định event có được xuất

```java
log.debug("Detailed diagnostic", ex);
```

Nếu DEBUG tắt, backend có thể bỏ qua event, bao gồm việc format stack trace cho lần ghi đó. Nhưng exception `ex` đã được tạo trước khi tới dòng log; tắt DEBUG không có nghĩa JVM tránh được toàn bộ chi phí tạo Throwable.

### 22.2. Đừng tạo exception chỉ để lấy stack trace thường xuyên

Ví dụ không phù hợp trong hot path:

```java
log.debug("Trace current call path", new Exception("trace"));
```

Tạo exception để lấy call stack chỉ phục vụ debug có thể tốn kém, đặc biệt nếu thực hiện hàng nghìn lần mỗi giây.

Nếu cần sampling, profiling hay tracing, hãy dùng công cụ tương ứng. Logging không nên biến thành một profiler tự chế bằng cách tạo Throwable liên tục.

### 22.3. Cân đối độ chi tiết

Một thông điệp tốt thường gồm:

- Tên hành động và kết quả.
- Một vài khóa ngữ cảnh ổn định.
- Mức log phù hợp.
- Throwable nếu cần chẩn đoán exception.
- Không chứa dữ liệu nhạy cảm ngoài chính sách.

Đừng ghi nguyên object graph vào mọi DEBUG log chỉ vì placeholder hỗ trợ bất kỳ `Object` nào.

## 23. Ví dụ hoàn chỉnh: log thành công và thất bại trong Spring Boot service

Ta xây dựng service nhập dữ liệu đơn giản.

### 23.1. Service interface

```java
package com.example.demo.importer;

public interface ImportService {
    int importFile(String fileId);
}
```

### 23.2. Repository interface minh họa

```java
package com.example.demo.importer;

import java.io.IOException;

public interface ImportRepository {
    int importRecords(String fileId) throws IOException;
}
```

### 23.3. Exception nghiệp vụ

```java
package com.example.demo.importer;

public class ImportFailedException extends RuntimeException {

    public ImportFailedException(
            String message,
            Throwable cause
    ) {
        super(message, cause);
    }
}
```

### 23.4. Service implementation

```java
package com.example.demo.importer;

import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class DefaultImportService implements ImportService {

    private static final Logger log =
            LoggerFactory.getLogger(DefaultImportService.class);

    private final ImportRepository repository;

    public DefaultImportService(ImportRepository repository) {
        this.repository = repository;
    }

    @Override
    public int importFile(String fileId) {
        log.info("Import started: fileId={}", fileId);

        try {
            int count = repository.importRecords(fileId);

            log.info(
                    "Import succeeded: fileId={} records={}",
                    fileId,
                    count
            );

            return count;
        } catch (IOException ex) {
            throw new ImportFailedException(
                    "Cannot import file " + fileId,
                    ex
            );
        }
    }
}
```

Service log sự kiện bắt đầu và thành công, nhưng khi lỗi I/O thì wrap với cause và propagate. Nó không bắt buộc phải log ERROR ngay tại đây nếu boundary sẽ log.

### 23.5. Runner làm error boundary

```java
package com.example.demo.importer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class ImportRunner implements CommandLineRunner {

    private static final Logger log =
            LoggerFactory.getLogger(ImportRunner.class);

    private final ImportService importService;

    public ImportRunner(ImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(String... args) {
        String fileId = args.length > 0
                ? args[0]
                : "demo-file";

        try {
            importService.importFile(fileId);
        } catch (ImportFailedException ex) {
            log.error(
                    "Import command failed: fileId={}",
                    fileId,
                    ex
            );

            throw ex;
        }
    }
}
```

Khi lỗi:

- Service giữ cause gốc.
- Runner log ngữ cảnh `fileId` và full Throwable.
- Runner rethrow để process startup không được báo thành công giả.

**Lưu ý:** vì runner rethrow, Spring Boot còn có thể ghi thêm thông tin failure trong logging khởi động. Trong một CLI thực tế, cần quyết định điểm chịu trách nhiệm log cuối cùng và exit code để tránh double logging với bộ xử lý startup failure của framework. Ví dụ trên minh họa cách truyền cause rõ ràng, không khẳng định startup chỉ tạo một log event.

### 23.6. Main application

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImportApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ImportApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }
}
```

Ứng dụng non-web phù hợp khi runner là một tác vụ CLI/batch. Trong project chạy thật, cần có một bean implement `ImportRepository` để dependency injection thành công.

## 24. Lưu ý riêng cho Java records, arrays và object toString()

Các kiểu argument khác nhau có thể được format khác nhau.

### 24.1. Primitive và wrapper

```java
int count = 3;
boolean active = true;

log.debug("count={} active={}", count, active);
```

Autoboxing có thể xảy ra khi truyền primitive vào overload nhận Object. Với một hai argument thông thường, chi phí này không đáng kể so với tính rõ ràng; nếu log hot path thực sự rất nóng, hãy đo đạc thay vì đoán.

### 24.2. Array

```java
String[] ids = {"A", "B"};

log.debug("Order ids={}", (Object) ids);
```

SLF4J formatter có hỗ trợ trình bày một số loại mảng. Nhưng nếu cần format cố định, dễ tìm kiếm và không nhầm với varargs, bạn có thể chọn rõ:

```java
log.debug("Order ids={}", java.util.Arrays.toString(ids));
```

Cách `Arrays.toString` tính chuỗi ngay trước log statement; cân nhắc `isDebugEnabled` hoặc supplier nếu array lớn và DEBUG thường tắt.

Việc ép sang `Object` trong ví dụ đầu giúp thể hiện ý định truyền **một array làm một argument** thay vì nhầm nó với danh sách varargs trong những trường hợp overload.

### 24.3. Java record

```java
public record OrderKey(String orderId, String region) {
}
```

```java
log.debug("Order key={}", orderKey);
```

Record tạo `toString()` mặc định liệt kê field names và values. Điều này tiện cho debug nhưng có thể vô tình ghi giá trị riêng tư nếu record chứa dữ liệu nhạy cảm. Hãy chọn field theo chính sách log thay vì mặc định ghi cả object.

### 24.4. toString có thể ném exception

Một `toString()` tự viết không an toàn có thể ném RuntimeException hoặc truy cập trạng thái không còn hợp lệ. Logging formatter thường cố gắng xử lý một số lỗi chuyển object thành text, nhưng không nên phụ thuộc vào điều đó.

Nên giữ `toString()` đơn giản, không gây side effect, hoặc log các field cụ thể thay vì object phức tạp.

## 25. Các lỗi và cách sửa thường gặp

| Cách viết / hiện tượng | Vấn đề | Cách sửa |
|---|---|---|
| `log.debug("Order " + orderId)` | Nối chuỗi trước khi biết DEBUG có bật | `log.debug("Order {}", orderId)` |
| `log.debug(String.format(...))` | Format eager, dùng sai cú pháp cho SLF4J | Dùng `{}` và arguments |
| `log.info("id=%s", id)` | SLF4J không dùng `%s` | `log.info("id={}", id)` |
| `log.error("Failure: {}", ex.getMessage())` | Không có Throwable cause, mất trace | `log.error("Failure", ex)` nếu cần trace |
| `log.error("Failure: {}", ex)` | Overload `Throwable` có thể để nguyên `{}` | `log.error("Failure", ex)` |
| `log.error("Failed id={} cause={}", id, ex)` | Throwable cuối được xem là cause, thiếu value cho placeholder | `log.error("Failed id={}", id, ex)` |
| `log.error("Failed", ex.getStackTrace())` | Mảng frames không phải Throwable cause | `log.error("Failed", ex)` |
| `ex.printStackTrace()` | Bỏ qua logging backend và level | Dùng `log.error("...", ex)` |
| `log.error("Failed " + ex, ex)` | Lặp thông tin; eager concatenation | Message ngắn có context và Throwable |
| `log.error("Error", ex)` ở mọi tầng | Duplicate stack traces | Chọn error boundary để ghi |
| `log.debug("value={}", expensive())` | `expensive()` chạy dù DEBUG tắt | `isDebugEnabled` hoặc Fluent supplier |
| `log.info("payload={}", request)` | Có thể lộ dữ liệu nhạy cảm | Log field được phép, có chủ đích |
| `log.error("...", ex)` nhưng không thấy trace | Level, appender/encoder hoặc log collection có thể ẩn/truncate trace | Kiểm tra cấu hình và output backend |
| Kỳ vọng `addKeyValue` tự thành JSON | Layout không hỗ trợ structured fields | Cấu hình structured encoder phù hợp |

### 25.1. Có thấy message nhưng không có stack trace?

Thực hiện theo thứ tự:

1. Kiểm tra có truyền `Throwable` thực sự, không chỉ `getMessage()`.
2. Kiểm tra Throwable nằm cuối parameter list hoặc dùng overload `(String, Throwable)`.
3. Kiểm tra log level: ERROR có được xuất không?
4. Kiểm tra backend pattern/encoder có ghi exception không.
5. Kiểm tra collector/UI có gom nhiều dòng, truncate hoặc ẩn stack trace không.
6. Xem exception có được wrap với cause đúng không.
7. Kiểm tra log có bị chuyển thành structured event mà UI hiển thị exception trong field riêng không.

### 25.2. Có quá nhiều stack traces giống nhau?

Kiểm tra:

1. Có log ở repository, service, controller và handler cho cùng exception không?
2. Có retry log full trace ở từng attempt không?
3. Có nhiều replica cùng gặp một failure không?
4. Spring Boot startup failure handler có thêm log sau khi runner ném lỗi không?
5. Collector có duplicate ingest không?

Một thông điệp tốt không thay thế chiến lược logging hợp lý ở cấp ứng dụng.

## 26. Thực hành so sánh các overload SLF4J

Giả sử:

```java
String orderId = "ORD-123";
RuntimeException ex =
        new IllegalStateException("Connection unavailable");
```

Thử từng lời gọi:

### Trường hợp A — Chỉ message và exception

```java
log.error("Order failed", ex);
```

Mục tiêu: message cố định + full Throwable.

### Trường hợp B — Một trường ngữ cảnh và exception

```java
log.error(
        "Order failed: orderId={}",
        orderId,
        ex
);
```

Mục tiêu: điền một placeholder, giữ stack trace.

### Trường hợp C — Chỉ message của exception

```java
log.error(
        "Order failed: reason={}",
        ex.getMessage()
);
```

Mục tiêu: chỉ ghi chuỗi reason. **Không có cause** được truyền cho logger.

### Trường hợp D — Dễ gây nhầm overload

```java
log.error("Order failed: {}", ex);
```

Mục tiêu người viết có thể tưởng là in `ex` vào placeholder, nhưng Java có thể chọn overload nhận `Throwable`. Kết quả không như mong muốn.

### Trường hợp E — Fluent API với cause

```java
log.atError()
        .addArgument(orderId)
        .setCause(ex)
        .log("Order failed: orderId={}");
```

Mục tiêu: diễn đạt rõ ràng data argument và cause.

### Trường hợp F — Exception type cùng stack trace

```java
log.error(
        "Order failed: orderId={} exceptionType={}",
        orderId,
        ex.getClass().getSimpleName(),
        ex
);
```

Mục tiêu: message có 2 giá trị và exception cuối chỉ để xuất trace.

Khi học logging, hãy giải thích mỗi argument đóng vai trò **giá trị placeholder** hay **Throwable cause**. Chỉ cần phân biệt được hai vai trò này là bạn sẽ tránh được phần lớn lỗi mất stack trace.

## 27. Quy trình thiết kế log message hữu ích

Khi thêm một log statement, đặt các câu hỏi:

### Bước 1 — Sự kiện cần ghi là gì?

Ví dụ:

```text
Payment request failed
```

Tốt hơn một message mơ hồ như `Error happened`.

### Bước 2 — Những field nào giúp chẩn đoán?

Ví dụ:

```text
orderId, gatewayName, attempt
```

Không ghi field không cần thiết hoặc dữ liệu nhạy cảm.

### Bước 3 — Chọn log level

- INFO cho mốc hoạt động.
- DEBUG cho chi tiết kỹ thuật.
- WARN cho bất thường có thể phục hồi.
- ERROR cho sự cố cần điều tra.

### Bước 4 — Dùng placeholder {}

```java
log.warn(
        "Gateway retry: orderId={} attempt={}",
        orderId,
        attempt
);
```

### Bước 5 — Có exception cần giữ stack trace không?

Nếu có:

```java
log.error(
        "Gateway failed: orderId={} attempt={}",
        orderId,
        attempt,
        ex
);
```

Đưa `Throwable` cuối cùng.

### Bước 6 — Đã log cùng lỗi ở tầng khác chưa?

Chọn boundary chịu trách nhiệm log. Nếu tầng dưới đang propagate, có thể không cần log ERROR ở đó.

### Bước 7 — Có chi phí hoặc dữ liệu nhạy cảm không?

Kiểm tra `toString()`, object graph, payload, token và các phép tính đắt tiền chỉ để log.

### Bước 8 — Có thể tìm kiếm log sau này không?

Dùng message ổn định và field names nhất quán. Với hệ thống phân tích log, ưu tiên structured logging theo backend phù hợp.

## 28. Bài thực hành

### Bài 1 — Đổi nối chuỗi thành placeholder

Viết một `CommandLineRunner` ghi `orderId` và `status` bằng nối chuỗi. Đổi sang `{}`, sau đó đặt logger level thành INFO để quan sát DEBUG bị tắt.

### Bài 2 — Phân biệt %s và {}

Thử:

```java
log.info("User %s logged in", username);
```

và:

```java
log.info("User {} logged in", username);
```

So sánh output và giải thích cú pháp của SLF4J.

### Bài 3 — Ghi Throwable đúng cách

Tạo `IllegalStateException`, so sánh:

```java
log.error("Failure: {}", ex.getMessage());
log.error("Failure", ex);
```

Quan sát sự khác biệt giữa message-only và stack trace.

### Bài 4 — Kết hợp hai placeholder và exception

Tạo biến `orderId`, `attempt` và `IOException`. Viết `log.error` sao cho hai trường ngữ cảnh xuất hiện trong message và exception được ghi với stack trace.

### Bài 5 — Kiểm tra overload khó hiểu

Thử:

```java
log.error("Failed: {}", ex);
```

Rồi sửa thành message cố định hoặc thêm một trường dữ liệu trước Throwable. Giải thích vì sao Java overload resolution ảnh hưởng kết quả.

### Bài 6 — Giữ cause khi wrap

Tạo `IOException`, wrap vào `ImportFailedException` bằng constructor nhận `Throwable cause`, rồi log wrapper ở boundary. Kiểm tra `Caused by` xuất hiện trong trace.

### Bài 7 — Tránh duplicate logging

Tạo flow repository → service → controller. Cho mỗi tầng log cùng exception, quan sát số lượng stack traces rồi đổi sang chiến lược log tại error boundary.

### Bài 8 — Đối số tính toán tốn kém

Tạo method `expensive()` tăng bộ đếm mỗi lần được gọi. Đặt DEBUG tắt và thử:

```java
log.debug("Data={}", expensive());
```

Sau đó thử guard `isDebugEnabled()` và Fluent supplier. So sánh số lần method được gọi.

### Bài 9 — Fluent cause

Trong dự án dùng SLF4J 2.x, ghi một lỗi với `log.atError().setCause(ex).log(...)`. Thêm `addKeyValue("orderId", orderId)` và xem output theo backend đang dùng.

### Bài 10 — MDC correlation

Gắn `requestId` vào MDC trong `try` và xóa trong `finally`. Cấu hình log pattern phù hợp rồi quan sát cùng ID xuất hiện trên nhiều log statement.

### Bài 11 — Bảo vệ dữ liệu nhạy cảm

Giả lập một payment request chứa token. Viết hai phiên bản log: một bản không an toàn ghi toàn bộ request và một bản chỉ ghi order ID, method type và error code. Giải thích lý do bản thứ hai an toàn hơn.

### Bài 12 — Spring MVC exception handler

Tạo `@RestControllerAdvice` xử lý exception hệ thống. Ghi trace ở server, trả về mã lỗi và message an toàn cho client. Xác nhận không trả stack trace trực tiếp qua HTTP.

### Bài 13 — Phân loại retry logs

Giả lập ba lần gọi gateway, hai lần đầu lỗi tạm thời và lần cuối thất bại. Thiết kế log WARN cho retries và ERROR kèm stack trace khi hết retry. Giải thích tại sao không nên in full trace ở mọi attempt.

### Bài 14 — Chẩn đoán log thiếu stack trace

Tạo code truyền `ex.getMessage()` rồi quan sát log thiếu trace. Sửa thành `Throwable` cuối và kiểm tra output. Nếu vẫn không thấy trace, xem cấu hình appender/encoder thay vì chỉ sửa Java code.

## 29. Tài liệu tham khảo chính thức

- [SLF4J User Manual](https://www.slf4j.org/manual.html): placeholder `{}`, parameterized logging và Fluent Logging API.
- [SLF4J FAQ — Parameterized Logging](https://www.slf4j.org/faq.html): cú pháp `{}`, hiệu năng và cách xử lý arguments.
- [SLF4J Logger API](https://www.slf4j.org/apidocs/org/slf4j/Logger.html): các overload như `error(String, Throwable)`, `error(String, Object...)` và các log levels.
- [SLF4J LoggingEventBuilder API](https://www.slf4j.org/apidocs/org/slf4j/spi/LoggingEventBuilder.html): `addArgument`, `addKeyValue`, `setCause` và `log`.
- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): cấu hình mức log, logging system và output trong Spring Boot.
- [Spring Boot Reference — Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html#features.logging.structured): các khả năng structured logging theo phiên bản Spring Boot.
- [Logback Manual](https://logback.qos.ch/manual/index.html): backend, appenders, layouts và exception rendering.

**Nguyên tắc thực hành quan trọng nhất:** dùng `logger.info("Order id={}", orderId)` thay vì nối chuỗi để format theo cơ chế SLF4J; và khi cần ghi stack trace, truyền **đối tượng exception** cho logger như `logger.error("Order failed: id={}", orderId, ex)`, với `ex` ở cuối. Đừng nhầm `getMessage()` với toàn bộ stack trace, đừng tạo nhiều bản sao của cùng một lỗi ở mọi tầng, và luôn chọn thông tin ngữ cảnh an toàn để log có giá trị chẩn đoán mà không làm lộ dữ liệu nhạy cảm.
