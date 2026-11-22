# Tránh tính thông điệp đắt tiền khi log bị tắt trong Java

## 1. Bài toán: log không xuất ra nhưng ứng dụng vẫn tốn CPU

Logging theo nhu cầu (*lazy logging*) là cách chỉ tạo thông điệp hoặc tính dữ liệu phục vụ log **khi mức log tương ứng thực sự được bật**. Vấn đề thường xuất hiện ở những lời gọi debug/trace có tham số cần tính toán: serialize object lớn, dựng JSON, tạo stack trace, duyệt collection, đọc trạng thái phức tạp, tính checksum hoặc gọi một hàm tốn CPU.

Ví dụ:

```java
logger.debug("Request snapshot: " + renderLargeRequest(request));
```

Dù DEBUG đang tắt, Java vẫn phải đánh giá biểu thức đối số **trước khi gọi** `debug`. Vì vậy `renderLargeRequest(request)` vẫn chạy và chuỗi vẫn được tạo. Logging framework chỉ quyết định bỏ bản ghi sau khi đã nhận lời gọi.

Chi phí này có thể đáng kể trong một hot path:

- Tạo nhiều object tạm và tăng áp lực garbage collection.
- Duyệt collection hoặc chuyển object sang JSON dù không ai đọc kết quả.
- Tạo chuỗi dài, gọi `String.format` hoặc nối chuỗi qua nhiều tầng.
- Tính thông tin chẩn đoán như trạng thái cache, query plan, payload summary.
- Tạo exception chỉ để ghi stack trace, dù log level đang tắt.
- Gọi code phụ có I/O hoặc side effect chỉ vì muốn đưa kết quả vào log.

**Mục tiêu:** giữ log hữu ích khi được bật, đồng thời không làm công việc đắt tiền khi log bị vô hiệu hóa.

## 2. Java đánh giá tham số trước khi gọi method

Đây là quy tắc ngôn ngữ Java, không phải riêng của logging:

```java
logger.debug("value = {}", calculateExpensiveValue());
```

Thứ tự khái niệm:

1. Java đánh giá receiver `logger`.
2. Java đánh giá các đối số từ trái sang phải, bao gồm lời gọi `calculateExpensiveValue()`.
3. Sau khi có đủ đối số, Java mới gọi `debug(...)`.
4. Logging API/framework kiểm tra level, filter và quyết định có tạo/ghi bản ghi hay không.

Vì thế, parameterized logging **không tự làm lazy việc tính đối số**. Nó thường trì hoãn việc format message, nhưng giá trị truyền vào vẫn đã được tính.

Đây là điểm phân biệt quan trọng nhất của chủ đề:

| Công việc | Parameterized logging khi level tắt |
| --- | --- |
| Tạo chuỗi format cuối cùng | Thường được trì hoãn |
| Gọi hàm tạo đối số | **Vẫn chạy ngay** |
| Tạo object truyền làm đối số | **Vẫn chạy ngay** |
| Nối chuỗi trước lời gọi | **Vẫn chạy ngay** |
| Supplier đúng API lazy | Có thể được bỏ qua |
| Code nằm trong `if (isDebugEnabled())` | Không chạy khi điều kiện false |

Không nên chỉ nhìn cú pháp `{}` rồi kết luận mọi thứ đã lazy. Hãy hỏi rõ **đối số được tính lúc nào** và **message được format lúc nào**.

## 3. Nối chuỗi và format trước lời gọi: cách dễ gây lãng phí

### 3.1. Nối chuỗi luôn tạo kết quả trước khi gọi logger

```java
logger.debug("User=" + user.getId()
    + ", profile=" + expensiveProfileSummary(user));
```

Chuỗi cuối cùng được tạo trước khi `debug` được gọi. Nếu DEBUG tắt, logger bỏ message nhưng CPU và allocation đã xảy ra.

Tương tự:

```java
logger.debug(String.format(
    "User=%s, profile=%s",
    user.getId(),
    expensiveProfileSummary(user)));
```

`String.format` phải chạy trước lời gọi logger. Việc logger bỏ bản ghi sau đó không hoàn lại chi phí format.

### 3.2. Không tạo exception chỉ để lấy stack trace cho log tắt

```java
logger.trace("Current call site: " + new Exception("trace"));
```

Biểu thức `new Exception(...)` được thực thi trước lời gọi logger; việc tạo exception có thể thu thập stack trace và tốn chi phí. Nếu cần stack trace chẩn đoán ở TRACE, chỉ tạo khi TRACE thực sự bật hoặc dùng API phù hợp nhận exception đã tồn tại.

### 3.3. Một helper đắt tiền vẫn chạy nếu gọi ở đối số

```java
logger.debug("Cache state: {}", cache.dumpAllEntries());
```

Dù framework có trì hoãn format `{}`, `dumpAllEntries()` vẫn được gọi. Nếu helper duyệt toàn cache hoặc dựng bản sao dữ liệu, đó chính là chi phí cần tránh.

**Quy tắc:** không đặt lời gọi đắt tiền, side effect hoặc tạo object lớn trực tiếp trong đối số logging nếu API không có overload Supplier được tài liệu hóa.

## 4. Parameterized logging: tốt cho format, chưa đủ cho tính toán

Các thư viện phổ biến hỗ trợ message template:

```java
logger.debug("Order {} changed to {}", orderId, newStatus);
```

Cách này thường tốt hơn nối chuỗi vì framework có thể bỏ qua bước format khi level bị tắt, tránh tạo chuỗi cuối cùng. Nó cũng giúp logging API phân tách template với dữ liệu và xử lý placeholder nhất quán.

Nhưng nếu viết:

```java
logger.debug("Order {} snapshot {}", orderId,
    buildExpensiveSnapshot(order));
```

thì `buildExpensiveSnapshot(order)` vẫn chạy trước lời gọi. Parameterized logging giúp **lazy formatting**, không nhất thiết giúp **lazy argument computation**.

### 4.1. Khi đối số rẻ, parameterized logging là lựa chọn tốt

```java
logger.debug("Loaded {} records for tenant {}", count, tenantId);
```

Nếu `count` và `tenantId` đã có sẵn, primitive/String/reference này thường rẻ để truyền. Không cần bọc mọi log bằng `isDebugEnabled()`; guard thừa làm code dài hơn và tăng nhánh kiểm tra mà không mang lợi ích rõ ràng.

### 4.2. Khi đối số đắt, cần guard hoặc Supplier

```java
if (logger.isDebugEnabled()) {
    logger.debug("Request snapshot: {}",
        buildExpensiveSnapshot(request));
}
```

Guard bảo đảm helper chỉ được gọi khi logger báo DEBUG đang bật tại thời điểm kiểm tra. Nếu helper đắt tiền, đây là mẫu đơn giản và dễ hiểu, đặc biệt với API logging không có Supplier overload.

**Lưu ý:** trạng thái logger có thể thay đổi giữa lúc kiểm tra và lúc ghi. Guard không phải một khóa cấu hình; nó là quyết định tại thời điểm kiểm tra. Trong thực tế điều này thường chấp nhận được. Nếu log level vừa bị tắt sau khi guard trả true, phép tính có thể vẫn xảy ra.

## 5. Guard bằng isDebugEnabled / isTraceEnabled

Nhiều logging facade có phương thức kiểm tra level:

- SLF4J: `isTraceEnabled()`, `isDebugEnabled()`, `isInfoEnabled()` và các level tương ứng.
- Log4j 2: các method `isTraceEnabled()`, `isDebugEnabled()`...
- Java Util Logging (JUL): `logger.isLoggable(Level.FINE)` hoặc `Level.FINER`/`FINEST`.

Mẫu:

```java
if (logger.isDebugEnabled()) {
    String diagnostic = buildDiagnosticSnapshot(state);
    logger.debug("State: {}", diagnostic);
}
```

Nếu DEBUG tắt, cả `buildDiagnosticSnapshot` lẫn việc tạo chuỗi đều không chạy.

### 5.1. Chỉ guard phần thực sự đắt

Không cần bọc toàn bộ logging:

```java
logger.debug("Request id={}, status={}", requestId, status);

if (logger.isDebugEnabled()) {
    logger.debug("Full request={}", serializeEntireRequest(request));
}
```

Hai đối số đầu đã có sẵn và rẻ; chỉ phần serialize toàn bộ request cần guard. Cách này giữ code dễ đọc, tránh kiểm tra level lặp lại không cần thiết.

### 5.2. Guard không thay thế parameterized logging

Trong guard, vẫn nên dùng placeholder:

```java
if (logger.isDebugEnabled()) {
    logger.debug("Payload: {}", expensivePayloadSummary(payload));
}
```

Không cần nối chuỗi sau khi đã guard. Parameterized logging vẫn đem lại format nhất quán, xử lý Throwable theo quy tắc của framework và tránh format sớm nếu logger/handler bỏ record vì filter khác.

### 5.3. JUL dùng isLoggable(Level)

JUL không đặt tên DEBUG/TRACE giống SLF4J. Các level thường dùng:

| JUL level | Mức độ khái quát |
| --- | --- |
| `SEVERE` | Lỗi nghiêm trọng |
| `WARNING` | Cảnh báo |
| `INFO` | Thông tin |
| `CONFIG` | Cấu hình |
| `FINE` | Debug |
| `FINER` | Chi tiết hơn |
| `FINEST` | Trace/chi tiết sâu |

Ví dụ:

```java
if (logger.isLoggable(Level.FINE)) {
    logger.fine("Snapshot: " + buildSnapshot(state));
}
```

Các mức JUL có thứ tự độ nghiêm trọng; level logger/handler quyết định bản ghi có được xử lý hay không. Không giả định `FINE` luôn tương ứng tuyệt đối với DEBUG của mọi framework; mapping cần được cấu hình trong ứng dụng.

## 6. Supplier API của Java Util Logging từ Java 8

Java 8 bổ sung overload nhận `Supplier<String>` trong `java.util.logging.Logger`, ví dụ:

- `logger.log(Level level, Supplier<String> msgSupplier)`
- `logger.fine(Supplier<String> msgSupplier)`
- `logger.finer(Supplier<String> msgSupplier)`
- `logger.finest(Supplier<String> msgSupplier)`

Supplier chỉ được gọi khi logger xác định level tương ứng có thể ghi. Nhờ đó, biểu thức tạo message có thể được trì hoãn mà không cần tự viết guard.

```java
logger.log(Level.FINE, () ->
    "Request snapshot: " + buildExpensiveSnapshot(request));
```

Khi FINE bị tắt, logger không cần gọi Supplier nên `buildExpensiveSnapshot` không chạy. Khi FINE bật và record được logger chấp nhận, Supplier được dùng để lấy nội dung message.

### 6.1. Ví dụ Supplier so với String tạo sẵn

```java
// Eager: hàm chạy ngay trước khi gọi log.
logger.fine("snapshot=" + buildSnapshot(state));

// Lazy theo Supplier API của JUL.
logger.fine(() -> "snapshot=" + buildSnapshot(state));
```

Khác biệt nằm ở overload được gọi: dòng thứ hai truyền một lambda tương thích `Supplier<String>`, thay vì truyền một String đã được tạo.

### 6.2. Supplier chỉ trì hoãn phần nằm bên trong nó

```java
String header = buildExpensiveHeader(request); // vẫn chạy ngay

logger.log(Level.FINE, () ->
    header + buildExpensiveBody(request));
```

Nếu FINE tắt, `buildExpensiveHeader` vẫn đã chạy. Đưa **toàn bộ công việc đắt tiền** vào Supplier nếu muốn trì hoãn tất cả:

```java
logger.log(Level.FINE, () ->
    buildExpensiveHeader(request) + buildExpensiveBody(request));
```

### 6.3. Supplier không biến log thành tác vụ bất đồng bộ

`Logger.log(Level, Supplier<String>)` là cách trì hoãn việc tạo message đến lúc logger cần nó; bản thân nó không có nghĩa message được tính trên thread nền. Supplier thường được gọi đồng bộ trong quá trình ghi log. Không đưa I/O mạng, truy vấn DB hoặc công việc nghiệp vụ dài vào Supplier.

### 6.4. JUL kiểm tra logger level/filter trước Supplier, handler có thể có filter riêng

JUL quyết định `isLoggable(level)` ở logger trước khi gọi Supplier. Sau đó record mới được chuyển tới handler. Nếu logger cho phép FINE nhưng mọi handler đều đặt mức INFO, Supplier vẫn có thể đã chạy rồi handler mới loại record. Muốn tiết kiệm đúng như mong đợi, cần cấu hình logger level/filter nhất quán với handler và hiểu đường truyền record.

Đây là chi tiết vận hành quan trọng: “không có dòng nào trong file log” không nhất thiết đồng nghĩa “logger đã bỏ qua Supplier”.

## 7. SLF4J: parameterized logging và Supplier trong fluent API

### 7.1. Parameterized logging truyền thống

Với SLF4J:

```java
logger.debug("User {} changed status to {}", userId, status);
```

Đây là cách tốt để tránh tạo chuỗi format khi DEBUG tắt. Tuy nhiên:

```java
logger.debug("Snapshot for user {}: {}", userId,
    buildExpensiveSnapshot(userId));
```

`buildExpensiveSnapshot` vẫn được gọi ngay. Đây là quy tắc đánh giá tham số của Java, không phụ thuộc phiên bản SLF4J.

Với SLF4J 1.x, cách portable để tránh phép tính đắt tiền là guard:

```java
if (logger.isDebugEnabled()) {
    logger.debug("Snapshot for user {}: {}",
        userId, buildExpensiveSnapshot(userId));
}
```

Không cần nâng cấp thư viện chỉ để dùng guard; đây là mẫu rõ ràng và được hỗ trợ lâu dài.

### 7.2. SLF4J 2.x fluent API nhận Supplier

SLF4J 2.x bổ sung fluent logging API, có thể truyền Supplier cho message/argument:

```java
logger.atDebug()
    .addArgument(() -> buildExpensiveSnapshot(userId))
    .log("Snapshot for user {}: {}");
```

Với level DEBUG tắt, builder không hoạt động theo cách ghi log thông thường và Supplier argument không cần được đánh giá. Khi bật, backend lấy giá trị Supplier để hoàn thiện event.

Có thể trì hoãn cả message:

```java
logger.atDebug()
    .setMessage(() -> buildExpensiveMessage(request))
    .log();
```

Đây là API của **SLF4J 2.x**; không copy vào project đang dùng SLF4J 1.7.x. Kiểm tra phiên bản `slf4j-api` và backend tương thích. Nếu project cần chạy với nhiều facade/backend hoặc phiên bản chưa thống nhất, guard `isDebugEnabled()` vẫn là lựa chọn dễ chuyển đổi.

### 7.3. Supplier không tự biến mọi argument thành lazy

```java
logger.atDebug()
    .addArgument(expensiveValue()) // Eager: tính trước khi addArgument
    .log("Value {}");
```

Dòng này vẫn tính `expensiveValue()` ngay. Cần truyền **lambda/Supplier**:

```java
logger.atDebug()
    .addArgument(() -> expensiveValue())
    .log("Value {}");
```

Không nhầm overload nhận Object với overload nhận Supplier. Đây là cùng một khác biệt giữa giá trị đã tính và hàm sẽ tính giá trị khi được yêu cầu.

## 8. Log4j 2: Supplier cho message đắt tiền

Log4j 2 cung cấp các overload nhận Supplier/MessageSupplier ở logging API hiện hành. Ví dụ ý tưởng:

```java
logger.debug(() -> "Request snapshot: "
    + buildExpensiveSnapshot(request));
```

Supplier message cho phép framework kiểm tra level trước khi lấy message. Với những overload parameterized, việc truyền giá trị tính sẵn vẫn là eager:

```java
logger.debug("Snapshot {}", buildExpensiveSnapshot(request));
```

Hãy kiểm tra chữ ký chính xác trong phiên bản `log4j-api` của project, nhất là khi dùng `MessageSupplier`, `Supplier<?>` hoặc overload varargs. Không dựa vào một ví dụ dành cho phiên bản khác mà bỏ qua compile test.

### 8.1. Supplier nên chỉ tạo nội dung chẩn đoán

```java
logger.debug(() -> renderState(state));
```

Supplier nên làm công việc đọc/format an toàn. Tránh:

```java
logger.debug(() -> {
    database.updateSomething(); // Sai: side effect trong log
    return "updated";
});
```

Nếu DEBUG bị tắt, side effect có thể không chạy; khi DEBUG bật, nó lại chạy. Như vậy **bật/tắt log làm thay đổi hành vi nghiệp vụ**. Supplier phải không có side effect và không được chứa quyết định nghiệp vụ.

## 9. Chọn cách nào? Bảng quyết định

| Tình huống | Cách phù hợp | Vì sao |
| --- | --- | --- |
| Đối số đã có sẵn, rẻ | Parameterized logging | Trì hoãn format, code gọn |
| Đối số cần gọi helper tốn CPU | `isDebugEnabled()` guard | Chỉ gọi helper khi level bật |
| JUL Java 8+ và tạo message đắt | `Logger.log(Level, Supplier<String>)` | Supplier được trì hoãn |
| SLF4J 2.x | Fluent API `addArgument(Supplier)` / `setMessage(Supplier)` | Supplier rõ ràng |
| Log4j 2 có Supplier overload | Supplier message phù hợp API version | Trì hoãn tạo message |
| Project có nhiều backend/version | Guard + parameterized logging | Dễ tương thích |
| Chỉ nối chuỗi ngắn, rẻ | Có thể dùng parameterized logging | Tránh tạo format sớm |
| Tạo JSON/stack trace/object graph lớn | Guard hoặc Supplier | Tránh CPU/allocation |
| Có side effect trong helper | Không gọi helper từ log | Logging không được điều khiển nghiệp vụ |
| Log có dữ liệu nhạy cảm | Redact trước khi log | Lazy không thay thế bảo mật |

Không có lý do để bọc mọi log bằng guard. Tập trung vào phần tính toán thực sự đắt và đường code được gọi rất thường xuyên.

## 10. Guard và Supplier: trade-off

### 10.1. Guard phù hợp khi helper phức tạp hoặc có nhiều đối số đắt

```java
if (logger.isDebugEnabled()) {
    String json = objectMapper.writeValueAsString(request);
    String metrics = buildDetailedMetrics(request);
    logger.debug("request={}, metrics={}", json, metrics);
}
```

Guard gom tất cả công việc cần thiết vào một block, dễ đọc và không cần Supplier API. Đây là lựa chọn tốt khi có nhiều bước hoặc nhiều giá trị dùng chung cho cùng một log statement.

### 10.2. Supplier phù hợp cho một biểu thức message độc lập

```java
logger.log(Level.FINE, () -> describeState(state));
```

Cú pháp ngắn, thể hiện trực tiếp “tạo message khi cần”. Với JUL, đây là API chuẩn Java 8; không phải tự viết `if`.

### 10.3. Guard và Supplier đều có chi phí nhỏ

Một lần kiểm tra level hoặc tạo lambda có chi phí. JVM thường tối ưu lambda không capture; lambda capture có thể tạo object tùy runtime/JIT và ngữ cảnh. Đừng giả định Supplier luôn miễn phí tuyệt đối. Nhưng trong đa số trường hợp, chi phí này nhỏ hơn nhiều so với serialize object lớn hoặc tạo stack trace. Nếu hot path cực nhạy, benchmark bằng JMH trên workload thật.

### 10.4. Đừng gọi isDebugEnabled nhiều lần không cần thiết

```java
if (logger.isDebugEnabled()) {
    logger.debug("A={}", expensiveA());
    logger.debug("B={}", expensiveB());
    logger.debug("C={}", expensiveC());
}
```

Một guard có thể bao nhiều biểu thức thuộc cùng một level. Không cần kiểm tra lại ba lần nếu không có lý do. Nhưng cũng không nên kéo một block quá rộng, làm code nghiệp vụ bị lẫn với logging.

## 11. Những công việc “đắt tiền” thường ẩn trong log

### 11.1. Serialize object thành JSON/XML

```java
logger.debug("payload={}", objectMapper.writeValueAsString(payload));
```

Serialization có thể duyệt sâu object graph, xử lý annotation/custom serializer, allocate buffer và format chuỗi. Hãy guard hoặc dùng Supplier API nếu cần.

### 11.2. Dựng snapshot của collection

```java
logger.trace("cache={}", new HashMap<>(cache));
```

Copy một map lớn không miễn phí; nếu cache đang concurrent, copy còn có thể cần chi phí đồng bộ hoặc có semantics snapshot riêng. Chỉ làm khi TRACE được bật.

### 11.3. Tạo chuỗi từ stream/collector

```java
logger.debug("IDs={}", ids.stream()
    .map(String::valueOf)
    .collect(Collectors.joining(",")));
```

Toàn bộ pipeline và joining chạy trước khi logger nhận kết quả. Dùng guard hoặc Supplier.

### 11.4. Tính checksum, hash, diff

```java
logger.debug("Payload hash={}", calculateSha256(payload));
```

Hash một payload lớn có thể tiêu thụ CPU đáng kể. Nếu hash còn được dùng cho logic thật, tính một lần ở luồng nghiệp vụ rồi tái sử dụng; nếu chỉ phục vụ log, trì hoãn bằng guard/Supplier.

### 11.5. Gọi toString có chi phí hoặc side effect

`logger.debug("object={}", object)` có thể khiến framework gọi `toString()` khi format event. Đây thường là điều mong muốn vì format có thể được trì hoãn; nhưng nếu `toString()` tự truy cập database, duyệt object graph lớn hoặc có side effect, hãy thiết kế lại `toString()` và tạo một summary chẩn đoán riêng.

Không viết `logger.debug("object=" + object)` nếu muốn trì hoãn `toString()`; nối chuỗi sẽ gọi `toString()` trước logger.

### 11.6. Tạo exception để log

Nếu exception đã được ném ra, truyền exception vào logging API thích hợp để framework ghi stack trace. Đừng tạo exception mới chỉ để lấy stack trace ở log level có thể đang tắt:

```java
if (logger.isTraceEnabled()) {
    logger.trace("Call path", new Exception("diagnostic"));
}
```

Stack trace có chi phí; chỉ thu thập khi thật sự cần. Không thay exception nghiệp vụ bằng một exception log-only.

## 12. Supplier và lambda: các quy tắc cần nhớ

### 12.1. Lambda không chạy khi được tạo

```java
Supplier<String> message = () -> buildMessage(state);
```

Dòng này tạo một đối tượng Supplier/lambda (có thể được JVM tối ưu), nhưng **không gọi `buildMessage`**. Phương thức chỉ chạy khi ai đó gọi `message.get()`.

### 12.2. Gọi .get() trước logger làm mất lazy behavior

```java
Supplier<String> supplier = () -> buildMessage(state);
logger.log(Level.FINE, supplier.get()); // Eager: get() chạy trước log
```

Cần truyền Supplier vào overload nhận Supplier:

```java
logger.log(Level.FINE, supplier);
```

Không chuyển Supplier thành String trước khi gọi logger.

### 12.3. Capture biến và giá trị mutable

Lambda Java chỉ capture biến local `final` hoặc effectively final. Nếu capture một reference tới object mutable, Supplier có thể đọc **trạng thái tại lúc được gọi**, không nhất thiết trạng thái tại lúc tạo lambda.

```java
Supplier<String> message = () -> "state=" + state.getStatus();
logger.log(Level.FINE, message);
```

Nếu object thay đổi giữa lúc tạo Supplier và lúc logger đánh giá nó, message có thể phản ánh trạng thái mới. Với logging đồng bộ, khoảng thời gian thường ngắn; với API async hoặc queue appender, thời điểm đánh giá có thể phụ thuộc framework. Nếu cần snapshot tại một thời điểm, hãy capture dữ liệu bất biến/rẻ trước hoặc tạo snapshot trong guard khi level bật.

### 12.4. Không giữ request lớn trong Supplier lâu hơn cần thiết

Một Supplier capture request, response hoặc object graph lớn có thể giữ reference đó sống lâu nếu được đưa vào queue bất đồng bộ. Dùng Supplier không tự giải phóng object; chỉ giải phóng khi event được xử lý/loại bỏ và reference không còn được giữ.

Với async logging, kiểm tra contract của framework về thời điểm Supplier được đánh giá và cách event được copy. Không giả định mọi backend đánh giá Supplier ngay tại call site.

### 12.5. Supplier không nên ném exception nghiệp vụ

```java
logger.debug(() -> loadRemoteConfiguration());
```

Nếu helper ném runtime exception, logging call có thể làm luồng nghiệp vụ ném lỗi dù mục tiêu chỉ là log. Không để Supplier gọi service có thể fail. Tạo summary từ dữ liệu sẵn có, xử lý lỗi chẩn đoán bên trong Supplier một cách có chủ đích, hoặc bỏ phần log phụ nếu không thể tạo an toàn.

## 13. Bảo mật và tính đúng đắn của log

Lazy logging là tối ưu hiệu năng, không phải biện pháp bảo mật. Những quy tắc sau vẫn cần thiết:

- **Redact dữ liệu nhạy cảm:** password, access token, session cookie, private key, dữ liệu cá nhân và payload bí mật.
- Không serialize toàn bộ request/response nếu chỉ cần một vài field an toàn.
- Không đưa raw SQL parameter hoặc Authorization header vào DEBUG theo mặc định.
- Giới hạn độ dài summary để tránh log injection hoặc log flooding.
- Không thực hiện side effect trong Supplier.
- Không để log disabled thay đổi kết quả nghiệp vụ.
- Không ghi toàn bộ stack trace ở mọi request nếu chỉ cần error code/correlation ID.
- Với multi-tenant service, bảo đảm summary không lộ dữ liệu của tenant khác.

Ví dụ helper an toàn hơn:

```java
if (logger.isDebugEnabled()) {
    logger.debug("Request id={}, bodyLength={}",
        requestId, request.getBodyLength());
}
```

Chỉ ghi định danh an toàn và độ dài payload thay vì nội dung payload. Nếu cần chi tiết, tạo một summary đã redacted và giới hạn kích thước.

## 14. Chương trình Java 8 chạy độc lập: đo số lần Supplier/argument được tính

Ví dụ dưới đây dùng **Java Util Logging (JUL)** có sẵn trong JDK, không cần dependency bên ngoài. Một handler nhỏ chỉ đếm record được nhận, tránh timestamp/format phụ thuộc môi trường.

Chương trình so sánh:

1. Nối chuỗi khi FINE tắt.
2. Parameterized logging với đối số đã tính khi FINE tắt.
3. Supplier message khi FINE tắt.
4. Guard `isLoggable` khi FINE tắt.
5. Cùng các cách đó khi FINE bật.

Tạo file **LazyLoggingDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LazyLoggingDemo {
    static final class CountingHandler extends Handler {
        private final List<String> messages = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                messages.add(record.getMessage());
            }
        }

        @Override
        public void flush() {
        }

        @Override
        public void close() {
        }

        int size() {
            return messages.size();
        }
    }

    private static String expensiveMessage(AtomicInteger calls) {
        int number = calls.incrementAndGet();
        return "computed-" + number;
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.lazy.logging");
        logger.setUseParentHandlers(false);
        logger.setFilter(null);

        for (Handler existing : logger.getHandlers()) {
            logger.removeHandler(existing);
        }

        CountingHandler handler = new CountingHandler();
        handler.setLevel(Level.ALL);
        logger.addHandler(handler);

        AtomicInteger calls = new AtomicInteger();
        try {
            logger.setLevel(Level.OFF);

            logger.fine("concat=" + expensiveMessage(calls));
            logger.log(Level.FINE, "parameter={0}",
                expensiveMessage(calls));
            logger.log(Level.FINE,
                () -> "supplier=" + expensiveMessage(calls));

            if (logger.isLoggable(Level.FINE)) {
                logger.fine("guard=" + expensiveMessage(calls));
            }

            System.out.println("Disabled level expensive computations: "
                + calls.get());
            System.out.println("Disabled level emitted records: "
                + handler.size());

            logger.setLevel(Level.FINE);

            logger.fine("concat=" + expensiveMessage(calls));
            logger.log(Level.FINE, "parameter={0}",
                expensiveMessage(calls));
            logger.log(Level.FINE,
                () -> "supplier=" + expensiveMessage(calls));

            if (logger.isLoggable(Level.FINE)) {
                logger.fine("guard=" + expensiveMessage(calls));
            }

            System.out.println("Enabled level expensive computations: "
                + calls.get());
            System.out.println("Enabled level emitted records: "
                + handler.size());
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
```

Biên dịch và chạy với JDK có hỗ trợ `--release`:

```bash
javac --release 8 -encoding UTF-8 LazyLoggingDemo.java
java LazyLoggingDemo
```

Trên JDK 8, bỏ `--release 8` khỏi lệnh `javac`; chương trình dùng Supplier overload có từ Java 8.

**Stdout chính xác:**

```text
Disabled level expensive computations: 2
Disabled level emitted records: 0
Enabled level expensive computations: 6
Enabled level emitted records: 4
```

### 14.1. Vì sao khi FINE tắt vẫn có hai lần tính?

Hai lời gọi đầu:

```java
logger.fine("concat=" + expensiveMessage(calls));
logger.log(Level.FINE, "parameter={0}", expensiveMessage(calls));
```

- Nối chuỗi gọi `expensiveMessage` trước khi logger nhận String.
- Overload parameterized JUL nhận một Object argument; `expensiveMessage` vẫn được đánh giá trước lời gọi. Logger có thể không format record, nhưng đối số đã tồn tại.

Hai cách tiếp theo:

```java
logger.log(Level.FINE,
    () -> "supplier=" + expensiveMessage(calls));

if (logger.isLoggable(Level.FINE)) {
    logger.fine("guard=" + expensiveMessage(calls));
}
```

- Supplier được truyền nguyên vẹn; khi level FINE tắt, logger không gọi Supplier.
- Guard false nên thân block không chạy.

Vì vậy counter bằng 2, còn handler nhận 0 record.

### 14.2. Khi FINE bật, cả bốn cách đều thực hiện công việc

Khi logger level chuyển sang FINE, cả nối chuỗi, parameterized argument, Supplier và guard đều được đánh giá. Counter tăng thêm 4 thành 6, handler nhận 4 record.

Bài test kiểm tra **số lần thực thi helper**, không đo thời gian CPU. Nó chứng minh cơ chế lazy/eager theo API, không phải benchmark hiệu năng.

### 14.3. Handler chỉ đếm message, không in log

`CountingHandler` lưu `LogRecord.getMessage()` để minh họa record đã tới handler. Nó không gọi formatter hoặc ghi ra console; do đó stdout cố định trên Windows, Linux và các JDK tương thích. Nếu handler có level cao hơn logger, logger vẫn có thể đánh giá Supplier trước rồi handler mới loại record — xem mục 6.4.

## 15. Kiểm thử và benchmark trong dự án thật

### 15.1. Unit test nên kiểm tra helper không được gọi

Có thể dùng `AtomicInteger` hoặc mock:

```java
AtomicInteger calls = new AtomicInteger();

logger.setLevel(Level.OFF);
logger.log(Level.FINE, () -> {
    calls.incrementAndGet();
    return "expensive";
});

assertEquals(0, calls.get());
```

Đây là snippet minh họa test; cấu hình logger/handler phải được cô lập để tránh ảnh hưởng test khác. Không thay đổi level của logger global dùng chung mà không khôi phục cấu hình sau test.

### 15.2. Test cả đường bật log

Một test chỉ xác nhận Supplier không chạy khi disabled là chưa đủ. Khi level bật, phải xác nhận Supplier được gọi và nội dung log đúng. Đồng thời kiểm tra filter/handler levels để hiểu đường ghi thực tế.

### 15.3. Benchmark phải so sánh cùng kết quả và cùng cấu hình

Nếu tối ưu một hot path, benchmark các trường hợp:

- Nối chuỗi với level disabled.
- Parameterized logging với argument đã tính.
- Guard quanh computation.
- Supplier API.
- Level enabled và handler thực sự ghi output.
- Object summary nhỏ so với serialize payload lớn.

Dùng JMH với warmup, measurement và forks phù hợp. Tránh chỉ đo một vòng `System.nanoTime()`; JIT, dead-code elimination, GC và filesystem I/O có thể làm số liệu sai lệch.

Không bật log ra console trong benchmark nếu mục tiêu là đo chi phí tạo message. Cũng không benchmark logger disabled bằng một fake method không tương đương API thật rồi kết luận cho backend production.

## 16. Lỗi thường gặp và cách sửa

1. **Nghĩ `{}` làm đối số lazy.** Sai: chỉ format thường được trì hoãn; helper trong argument vẫn chạy. Dùng guard hoặc Supplier.
2. **Nối chuỗi trước logger.** Sai: chuỗi được tạo ngay. Dùng template hoặc Supplier.
3. **Gọi `String.format` trước logger.** Sai: format chạy ngay. Dùng parameterized message.
4. **Tạo JSON trong argument.** Sai: serializer vẫn chạy. Đưa serializer vào guard/Supplier.
5. **Dùng `supplier.get()` trước khi log.** Sai: tự kích hoạt Supplier. Truyền Supplier cho overload nhận Supplier.
6. **Truyền giá trị thay vì lambda vào fluent API.** `addArgument(expensive())` là eager; dùng `addArgument(() -> expensive())`.
7. **Guard mọi câu log.** Thừa khi arguments rẻ và framework đã parameterize. Chỉ guard công việc đắt.
8. **Đặt side effect trong Supplier.** Bật/tắt log làm đổi hành vi. Supplier chỉ nên tạo dữ liệu chẩn đoán.
9. **Dùng Supplier để gọi DB/HTTP.** Có thể kéo dài luồng ghi log và gây lỗi phụ. Tính nghiệp vụ ở nơi phù hợp.
10. **Tạo exception mới khi TRACE tắt.** Stack trace vẫn được thu thập. Guard việc tạo exception.
11. **Giả định JUL handler level được kiểm tra trước Supplier.** Logger có thể đánh giá Supplier rồi handler mới loại record. Cấu hình level nhất quán.
12. **Dùng SLF4J 2 fluent API trên SLF4J 1.x.** Không tương thích. Kiểm tra version API/backend hoặc dùng guard.
13. **Dùng API Supplier không đúng overload.** Compile test với version thư viện thực tế.
14. **Capture object mutable rồi mong snapshot tại thời điểm tạo lambda.** Supplier có thể đọc trạng thái mới khi được gọi. Capture immutable snapshot nếu cần.
15. **Giữ request lớn trong async Supplier.** Reference có thể sống lâu. Chỉ capture dữ liệu cần thiết và kiểm tra semantics backend.
16. **Để Supplier ném exception nghiệp vụ.** Logging phụ có thể làm request fail. Chỉ gọi helper chẩn đoán an toàn.
17. **Log toàn bộ object bằng toString.** Có thể đắt hoặc lộ dữ liệu. Dùng summary có giới hạn và redact.
18. **Tin log disabled là không có chi phí nào.** Vẫn có thể có method dispatch, level check, lambda/capture và argument evaluation bên ngoài. Tối ưu đúng phần đắt.
19. **Không đo trong workload thật.** Dùng JMH và profiling trước khi thêm guard khắp code.
20. **Dùng logging làm control flow.** Log chỉ quan sát; không đặt nghiệp vụ phụ thuộc level.

## 17. Checklist review code logging

- [ ] Có phép nối chuỗi hoặc `String.format` nằm trước lời gọi logger?
- [ ] Có helper tốn CPU/serialize/dump collection trong argument?
- [ ] Parameterized logging có bị hiểu nhầm là lazy argument?
- [ ] Có guard `isDebugEnabled`/`isLoggable` cho phần thực sự đắt?
- [ ] Nếu có Supplier overload, project version có hỗ trợ đúng API?
- [ ] Supplier có thuần, không side effect và không làm I/O dài?
- [ ] Lambda capture có giữ object lớn hoặc đọc trạng thái mutable muộn?
- [ ] Logger level và handler/appender filters có nhất quán?
- [ ] Có tạo exception/stack trace chỉ để ghi log có thể bị tắt?
- [ ] Có redact token, password, PII và giới hạn payload?
- [ ] Có test cả log disabled và enabled?
- [ ] Unit test có khôi phục cấu hình logger sau khi chạy?
- [ ] Có benchmark khi chi phí thực sự quan trọng?
- [ ] Có giữ message format ổn định để log aggregation/search hoạt động?
- [ ] Logging có thể bị tắt mà không đổi kết quả nghiệp vụ?

## 18. Câu hỏi tự luyện và đáp án

**1. Vì sao `logger.debug("x=" + expensive())` vẫn chạy `expensive()` khi DEBUG tắt?**  
Vì Java đánh giá đối số trước khi gọi method logger.

**2. Parameterized logging `{}` có tác dụng gì?**  
Thường trì hoãn format chuỗi cuối cùng và giúp template nhất quán; nó không tự trì hoãn việc tính argument.

**3. Cách đơn giản để bỏ qua một helper đắt tiền khi DEBUG tắt?**  
Dùng `if (logger.isDebugEnabled())` rồi gọi helper bên trong block.

**4. JUL dùng method nào để kiểm tra FINE?**  
`logger.isLoggable(Level.FINE)`.

**5. JUL có Supplier logging từ Java 8 không?**  
Có, ví dụ `logger.log(Level.FINE, () -> buildMessage())` và `logger.fine(() -> buildMessage())`.

**6. Supplier được tạo có đồng nghĩa hàm bên trong chạy ngay không?**  
Không. Nó chạy khi consumer gọi `get()`; JUL chỉ yêu cầu Supplier khi level được chấp nhận ở logger.

**7. `logger.log(Level.FINE, supplier.get())` có lazy không?**  
Không. `get()` chạy trước khi logger được gọi.

**8. `logger.log(Level.FINE, () -> expensive())` khác gì `logger.log(Level.FINE, expensive())`?**  
Vế đầu truyền Supplier; vế sau tính String trước và truyền giá trị đã tạo.

**9. SLF4J 1.x parameterized logging có lazy argument không?**  
Không. Dùng guard cho phép tính đắt tiền.

**10. SLF4J 2.x fluent API trì hoãn argument thế nào?**  
Dùng `addArgument(() -> expensive())`; không dùng `addArgument(expensive())`.

**11. Log4j 2 có thể nhận Supplier message không?**  
Có các Supplier/MessageSupplier overload trong API hiện hành; kiểm tra chữ ký theo phiên bản `log4j-api`.

**12. Supplier có làm logging thành asynchronous không?**  
Không. Supplier trì hoãn tạo nội dung; không tự chuyển công việc sang thread nền.

**13. Nếu JUL logger level cho phép FINE nhưng handler chỉ cho INFO thì Supplier có thể chạy không?**  
Có. Logger có thể đánh giá Supplier trước khi handler loại record.

**14. Có nên guard mọi câu log dù đối số chỉ là hai primitive đã có?**  
Thường không. Parameterized logging là đủ và giữ code đơn giản.

**15. Có nên gọi database từ Supplier chỉ để log kết quả?**  
Không. Logging không nên chứa I/O dài hoặc side effect nghiệp vụ.

**16. Nếu object thay đổi sau khi tạo lambda Supplier, message có thể thấy trạng thái nào?**  
Có thể thấy trạng thái tại lúc Supplier được gọi. Dùng immutable snapshot nếu cần trạng thái tại thời điểm tạo.

**17. Vì sao tạo `new Exception()` chỉ để log TRACE có thể đắt?**  
Vì tạo exception có thể thu thập stack trace trước khi logger quyết định bỏ message.

**18. Supplier có thể ném runtime exception không?**  
Có. Exception đó có thể thoát ra khỏi logging call; chỉ dùng computation chẩn đoán an toàn.

**19. Cách kiểm tra lazy behavior ổn định trong unit test?**  
Dùng counter/mock để xác nhận helper không được gọi khi level disabled và được gọi khi enabled.

**20. Cách benchmark chi phí logging đúng?**  
Dùng JMH, cùng cấu hình backend, phân biệt disabled/enabled, tránh console I/O ngoài mục tiêu và kiểm tra kết quả computation.

## 19. Tài liệu API và phiên bản còn áp dụng

- [Java SE 25 Logger API](https://docs.oracle.com/en/java/javase/25/docs/api/java.logging/java/util/logging/Logger.html): `isLoggable`, `log(Level, Supplier<String>)`, `fine(Supplier<String>)` và cách logger đánh giá message supplier.
- [Java 8 Logger API](https://docs.oracle.com/javase/8/docs/api/java/util/logging/Logger.html): đối chiếu các Supplier overload đã có từ Java 8.
- [SLF4J 2.x Manual — Fluent Logging API](https://www.slf4j.org/manual.html#fluent): `LoggingEventBuilder`, `addArgument(Supplier<?>)`, `setMessage(Supplier<String>)` và no-op builder khi level tắt.
- [SLF4J FAQ — parameterized logging](https://www.slf4j.org/faq.html#logging_performance): lợi ích của parameterized messages và cách tránh format không cần thiết.
- [Log4j 2 API — Logger](https://logging.apache.org/log4j/2.x/javadoc/log4j-api/org/apache/logging/log4j/Logger.html): Supplier/MessageSupplier overload và kiểm tra level.
- [JMH — OpenJDK Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): thiết kế benchmark có warmup, measurement và forks.

Các API Supplier của JUL và ví dụ runnable ở đây tương thích Java 8. SLF4J fluent Supplier là API **2.x**; không áp dụng cho SLF4J 1.x. Với Log4j 2, đối chiếu đúng artifact/version mà ứng dụng triển khai. Không dùng Log4j 1.x hoặc API đã ngừng duy trì làm hướng dẫn mới.

**Nguyên tắc cuối:** parameterized logging tránh format sớm; guard hoặc Supplier mới tránh được việc **tính đối số đắt tiền** khi level bị tắt. Hãy giữ Supplier thuần, kiểm tra đúng logging API/version, và chỉ tối ưu những computation thực sự tốn kém.
