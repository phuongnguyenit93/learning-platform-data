# Chuyển log text sang structured logging trong Java

## 1. Vì sao cần chuyển từ text sang structured?

Trong một ứng dụng Java, log dạng text thường bắt đầu bằng những câu dễ đọc:

```text
2026-01-01 10:15:30 INFO OrderService - Created order O-17 amount=120000 VND
2026-01-01 10:15:31 ERROR PaymentService - Payment failed for O-17: gateway timeout
```

Đây là **ví dụ dữ liệu giả**, không phải log đang chạy trong một hệ thống cụ thể. Người đọc hiểu được nội dung, nhưng máy muốn trả lời các câu hỏi sau sẽ phải xử lý chuỗi:

- Trong 15 phút, bao nhiêu giao dịch thất bại vì `GATEWAY_TIMEOUT`?
- Tìm tất cả sự kiện liên quan `trace_id=tr-42` trên nhiều service.
- Nhóm số lần `payment.failed` theo môi trường, phiên bản hoặc dependency.
- Phân biệt `amount=120000` là **số** chứ không phải một đoạn văn bản.
- Truy vấn những bản ghi có `retryable=true` mà không bị nhầm với chữ `retryable=true` xuất hiện trong câu mô tả.

**Structured logging** là cách biểu diễn mỗi sự kiện log thành một tập **trường có tên và giá trị**, thường được chuyển thành JSON hoặc một định dạng dữ liệu có cấu trúc khác. Ví dụ:

```json
{
  "timestamp": "2026-01-01T10:15:31Z",
  "level": "ERROR",
  "service": "checkout",
  "environment": "production",
  "event_code": "payment.failed",
  "order_id": "O-17",
  "error_code": "GATEWAY_TIMEOUT",
  "retryable": false,
  "trace_id": "tr-42",
  "message": "Không thể hoàn tất thanh toán"
}
```

Ở ví dụ này, `retryable` là boolean, `event_code` là một giá trị thuộc danh mục sự kiện và `order_id` là trường có tên nhất quán. Bộ thu thập có thể lập chỉ mục, lọc, tổng hợp và hiển thị theo trường mà không phải đoán cấu trúc câu văn.

**Chuyển đổi không chỉ là đổi mẫu console thành một chuỗi trông giống JSON.** Một lần migration đúng cần thiết kế schema, thay cách cung cấp dữ liệu tại mã Java, cấu hình backend, kiểm thử encoder/collector, duy trì tương thích với những truy vấn cũ và bảo vệ dữ liệu.

## 2. Phân biệt message, parameter substitution và structured fields

Ba lớp này thường bị nhầm:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| Message | Câu mô tả dễ đọc cho con người | `"Không thể hoàn tất thanh toán"` |
| Parameter substitution | Điền đối số vào template, thường dùng `{}` với SLF4J | `log.info("order={}", orderId)` |
| Structured fields | Thuộc tính có tên, kiểu và ý nghĩa ổn định | `"order_id": "O-17"`, `"amount_minor": 120000` |
| Encoder/layout | Chuyển một logging event thành byte ở đầu ra | JSON encoder của Logback |
| Collector/parser | Thu thập và parse dữ liệu đã được xuất | Agent đọc stdout của container |

Một lời gọi:

```java
log.info("order={} amount={}", orderId, amount);
```

thường tạo **message đã được format** như `order=O-17 amount=120000`. Nó **không đảm bảo** collector có hai field tên `order` và `amount`. Chúng có thể vẫn chỉ nằm trong trường `message` dưới dạng chuỗi.

Ngược lại, một lời gọi SLF4J 2.x theo kiểu fluent:

```java
log.atInfo()
        .addKeyValue("event_code", "order.created")
        .addKeyValue("order_id", orderId)
        .addKeyValue("amount_minor", amountMinor)
        .log("Đã tạo đơn hàng");
```

có thể chuyển **key-value pair** vào logging event. Để biến chúng thành các field JSON thực sự, **backend/encoder phải hỗ trợ và được cấu hình để xuất**. Chỉ gọi `addKeyValue` không tự bảo đảm output cuối có dạng JSON.

Trong bài, các đoạn code nhắc tới `log`, `orderId`, `amountMinor` mà chưa khai báo là **đoạn minh họa trong ứng dụng**, không phải chương trình Java độc lập. Ví dụ có thể chạy đầy đủ xuất hiện ở các phần sau.

## 3. Text logging đang gặp những hạn chế nào?

Hãy nhìn ba kiểu message cùng mang ý nghĩa giao dịch thất bại:

```text
Payment failed for order O-17 due to timeout
payment.error order=O-17 code=TIMEOUT
Order O-17 payment rejected by upstream: timeout=3000ms
```

Nếu bộ truy vấn chỉ tìm chuỗi `"Payment failed"`, nó bỏ sót hai dạng còn lại. Nếu dùng biểu thức chính quy lấy order ID, parser có thể vỡ khi developer đổi thông điệp, ngôn ngữ, dấu phân cách hoặc thêm dữ liệu mới.

Một số rủi ro khác:

1. **Không thống nhất tên field:** `orderId`, `order_id`, `order` xuất hiện lẫn lộn.
2. **Không thống nhất kiểu:** số 1000 hôm nay là integer, ngày mai thành `"1,000"`.
3. **Thiếu ý nghĩa nghiệp vụ:** chỉ có câu `"Something failed"` mà không có event code hoặc error code.
4. **Dữ liệu nằm trong stack trace:** các trường quan trọng bị chôn trong một khối text nhiều dòng.
5. **Khó lọc không có field:** để tìm đúng một request phải search cả message, dễ nhầm với giá trị tương tự.
6. **Sai lệch khi đổi câu chữ:** dashboard/alert phụ thuộc regex hoặc câu cố định có thể hỏng sau một refactor.
7. **Rủi ro thông tin nhạy cảm:** nối cả request/exception vào text có thể vô tình ghi token hoặc dữ liệu cá nhân.
8. **Khó phân biệt loại sự kiện:** cùng chữ `failed` có thể là một lần retry đã phục hồi hoặc thất bại cuối cùng.

Structured logging giúp giải quyết nhiều vấn đề trên, nhưng **không tự biến log thành dữ liệu hoàn toàn đáng tin**. Mất log do buffer, filter, collector hoặc rotation vẫn có thể xảy ra; dữ liệu nhạy cảm vẫn có thể bị ghi nếu ứng dụng truyền vào.

## 4. Thiết kế schema trước khi viết lại mã

**Schema** là hợp đồng về các trường, tên, kiểu dữ liệu, ý nghĩa và tính ổn định qua phiên bản. Không nên bắt đầu migration bằng cách tìm mọi `log.info` rồi đưa từng câu vào một JSON tự ghép.

Một schema minh họa cho service `checkout`:

| Field | Kiểu khuyến nghị | Ý nghĩa |
| --- | --- | --- |
| `timestamp` | Chuỗi thời gian chuẩn có timezone, hoặc kiểu timestamp của đích | Thời điểm sự kiện xảy ra |
| `level` | String có tập giá trị rõ | `INFO`, `WARN`, `ERROR` |
| `service` | String | Tên service logic |
| `environment` | String | `dev`, `staging`, `production` |
| `logger` | String | Tên logger/class/package nguồn |
| `event_code` | String ổn định | Loại sự kiện, ví dụ `order.created` |
| `message` | String | Mô tả ngắn dễ đọc |
| `trace_id` | String tùy chọn | Liên kết hoạt động phân tán |
| `request_id` | String tùy chọn | Liên kết một request |
| `order_id` | String tùy chọn | Định danh đơn hàng; giữ nguyên số 0 đầu nếu có |
| `amount_minor` | Integer/long | Tiền ở đơn vị nhỏ nhất theo quy ước |
| `currency` | String theo mã tiền tệ | `VND`, `USD` |
| `error_code` | String thuộc danh mục | `GATEWAY_TIMEOUT`, `DB_UNAVAILABLE` |
| `retryable` | Boolean | Có thể thử lại theo đánh giá ở thời điểm sự kiện |
| `exception_type` | String khi có lỗi | Tên lớp exception |
| `stack_trace` | String hoặc cấu trúc theo encoder | Vị trí và chuỗi nguyên nhân |

**Không phải mọi event đều phải có tất cả field.** Một sự kiện `order.created` thường không cần `error_code` hay stack trace; một sự kiện `payment.failed` cần có ngữ cảnh lỗi. Schema nên tách **trường chung** và **trường theo loại sự kiện**.

### Những quy tắc tên và kiểu cần thống nhất

- Chọn một quy ước, ví dụ `snake_case` cho key JSON: `order_id`, `error_code`, `duration_ms`.
- Giữ **cùng tên field có cùng kiểu** giữa service và phiên bản. Tránh `duration_ms` lúc là số, lúc là chuỗi `"120 ms"`.
- Đơn vị phải nằm trong tên hoặc tài liệu schema: `duration_ms`, `bytes_sent`, `amount_minor`.
- Không ép các ID vào kiểu số: `"00017"` phải giữ được số 0 đầu.
- Với tiền, chọn nguyên tắc rõ: số nguyên đơn vị nhỏ nhất kèm `currency` hoặc một hợp đồng decimal thích hợp; tránh số thực nhị phân cho phép tính tiền.
- Không nhét cả domain object vào một field `payload` khổng lồ nếu chỉ cần vài thuộc tính.
- Khi thiếu dữ liệu, định nghĩa rõ **field vắng mặt** khác gì `null`, `""` hoặc giá trị mặc định.
- Không tự đổi tên một field đã được dashboard dùng khi chưa có migration plan.
- Không dùng thông điệp con người làm khóa tổng hợp; dùng `event_code`.

Ví dụ tránh xung đột kiểu dữ liệu:

```json
{"event_code":"checkout.completed","duration_ms":153,"success":true}
```

Không nên ở nơi khác xuất:

```json
{"event_code":"checkout.completed","duration_ms":"153ms","success":"yes"}
```

Nếu hai event vào cùng một index/collection có mapping cố định, một số kho lưu trữ có thể từ chối hoặc xử lý sai những bản ghi không cùng kiểu.

## 5. Mã sự kiện: nền tảng để chuyển log từ câu văn sang dữ liệu có thể nhóm

**`event_code`** trả lời: “loại sự kiện nào xảy ra?”. **`error_code`** trả lời: “loại nguyên nhân/trạng thái lỗi nào?”. Hai trường không thay thế nhau.

Ví dụ một chuỗi xử lý thanh toán:

```text
payment.started         INFO
payment.attempt_failed  WARN  attempt=1, error_code=GATEWAY_TIMEOUT
payment.retry_succeeded INFO  attempt=2
```

Nếu retry thành công, **không nên phát `payment.failed` với nghĩa thao tác cuối đã thất bại**.

Khi hết mọi đường phục hồi:

```text
payment.started         INFO
payment.attempt_failed  WARN  attempt=1, error_code=GATEWAY_TIMEOUT
payment.attempt_failed  WARN  attempt=2, error_code=GATEWAY_TIMEOUT
payment.failed          ERROR attempts=2, error_code=GATEWAY_TIMEOUT
```

Một tên mã sự kiện tốt nên:

1. Mô tả ý nghĩa ổn định thay vì câu message hay tên method.
2. Có danh mục và owner: `payment.failed`, `order.created`, `inventory.reserved`.
3. Không chứa ID động: **không dùng** `payment.failed.O-17` làm event code.
4. Phân biệt sự kiện theo lượt thử và trạng thái cuối khi có retry.
5. Giữ ổn định khi nội dung `message` được sửa hoặc dịch sang ngôn ngữ khác.
6. Có chính sách đổi tên/deprecate nếu ý nghĩa thay đổi.

**`trace_id` khác `event_code`.** `trace_id` nối nhiều sự kiện của một hành trình; `event_code` giúp nhóm các sự kiện cùng loại. Một trace có thể chứa hàng chục event code.

## 6. Lộ trình chuyển đổi: không sửa tất cả cùng lúc

Với một hệ thống đang vận hành, nên migration theo từng bước có thể kiểm chứng và rollback.

### Bước 1 — Kiểm kê nguồn và người dùng log

Xác định:

- Service/package nào đang ghi console, file, JUL, Logback hay Log4j 2.
- Pattern text hiện tại và các level/filter/appenders.
- Dashboard, alert, truy vấn hoặc script nào phụ thuộc câu message/regex cũ.
- Service nào có volume log lớn hoặc chứa dữ liệu nhạy cảm.
- Kho nào nhận log và mapping/schema có yêu cầu gì.
- Có event code, trace ID, request ID nào đã tồn tại không.

Đừng chỉ kiểm kê vài dòng dễ thấy. Các lỗi khó thường ở exception, job chạy nền, thư viện bên ngoài hoặc những message có giá trị thay đổi khó parse.

### Bước 2 — Chọn schema và quy tắc đặt tên

Thống nhất các trường tối thiểu cho mọi service, cùng bộ trường nghiệp vụ cho từng sự kiện. Ví dụ cho `checkout`: `timestamp`, `level`, `service`, `environment`, `event_code`, `message`, `trace_id`; bổ sung `order_id` và `error_code` khi có.

Ghi rõ: field nào bắt buộc, kiểu nào, đơn vị nào, có chứa dữ liệu nhạy cảm không, retention và ai có thể đọc.

### Bước 3 — Chọn một backend và encoder phù hợp

Với SLF4J 2.x, ứng dụng có thể tiếp tục gọi SLF4J; backend như Logback sẽ xuất JSON bằng encoder hỗ trợ structured fields. Với Log4j 2, có layout JSON/template phù hợp. Không cài đồng thời các provider cạnh tranh hoặc bridge hai chiều gây vòng.

Cần xác nhận **provider/runtime classpath**, không chỉ tệp `pom.xml`.

### Bước 4 — Chuyển các sự kiện quan trọng trước

Ưu tiên những sự kiện có giá trị vận hành: thất bại thanh toán cuối, lỗi dependency, kết quả xử lý request, job hoàn tất, retry đã cạn. Không đổi tất cả câu DEBUG ít dùng trước khi xây dựng schema cho các sự kiện chính.

### Bước 5 — Kiểm chứng trước và sau

Với cùng một kịch bản, so sánh:

- Kết quả nghiệp vụ và số sự kiện logic.
- Level, event code, error code, trace ID.
- Thuộc tính có kiểu, ví dụ integer, boolean.
- Throwable/cause/stack trace khi có.
- Số bản ghi ở collector và tính truy vấn.
- Không có secret hoặc output JSON không hợp lệ.

### Bước 6 — Chuyển dần dashboard và alert

Một giai đoạn chuyển tiếp có thể giữ parser cũ để tra lịch sử, đồng thời xây truy vấn dựa trên field mới. Không tắt parser/query cũ trước khi xác nhận mọi consumer quan trọng đã dùng field mới.

### Bước 7 — Dừng tương thích không cần thiết

Sau khi đo đủ độ phủ và có kế hoạch rollback, có thể bỏ các phần text parser/dual output không cần thiết. Nếu phát **cả bản ghi text lẫn JSON** cho cùng một event, phải đánh dấu pipeline riêng hoặc không đưa cả hai vào cùng phép đếm để tránh nhân đôi chỉ số.

## 7. Trước–sau: chuyển lời gọi log trong Java

Giả sử code ban đầu:

```java
log.error("Payment failed for order " + orderId
        + ", error=" + errorCode + ", retryable=" + retryable,
        exception);
```

Đây là **đoạn minh họa** với các biến đã khai báo. Hạn chế: nối chuỗi trước lời gọi logger; muốn truy vấn `retryable` phải parse message; tên và kiểu field không chắc ổn định.

Một bước cải thiện trung gian:

```java
log.error("event=payment.failed order_id={} error_code={} retryable={}",
        orderId, errorCode, retryable, exception);
```

Cách này dùng placeholder để tránh một số chi phí định dạng khi mức bị tắt và tạo thông điệp có nhãn rõ. Nhưng các giá trị **vẫn nằm trong text** nếu encoder không tách chúng thành các trường.

Với **SLF4J 2.x fluent API**:

```java
log.atError()
        .addKeyValue("event_code", "payment.failed")
        .addKeyValue("order_id", orderId)
        .addKeyValue("error_code", errorCode)
        .addKeyValue("retryable", retryable)
        .setCause(exception)
        .log("Không thể hoàn tất thanh toán");
```

Đây là cách rõ ràng hơn để gửi field riêng cùng Throwable. Các trường sẽ xuất ra JSON khi backend/encoder hỗ trợ đúng. **`setCause(exception)` khác việc truyền `exception.getMessage()`**: nó giữ đối tượng Throwable để backend có thể ghi loại lỗi và stack trace theo cấu hình.

Với những framework đang dùng SLF4J 1.7, API fluent `atError()` chưa có. Có thể dùng cơ chế structured arguments phù hợp với encoder/backend hoặc nâng lên SLF4J 2.x theo lộ trình phiên bản. Không sao chép lời gọi fluent vào dự án cũ rồi cho rằng vẫn biên dịch.

## 8. Ví dụ Java 17 chạy độc lập: từ log text thành hai sự kiện JSON

Ví dụ này **không dùng thư viện logging bên ngoài**. Nó minh họa điểm cốt lõi của structured data: tạo dữ liệu với **tên field, thứ tự và kiểu rõ ràng**, sau đó serialize thành JSON có escaping cho chuỗi.

Đây là **bộ JSON writer tối giản chỉ phục vụ bài thực hành**. Nó hỗ trợ String, Boolean, Integer, Long và null trong một object phẳng; **không phải** thư viện JSON tổng quát và **không thay thế** encoder logging production. Đối với hệ thống thật, nên dùng encoder/bộ serialize đã được kiểm thử và hỗ trợ các kiểu, dữ liệu lồng nhau, giới hạn kích thước và bảo mật.

### 8.1. Lưu tệp `StructuredMigrationDemo.java`

```java
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

public final class StructuredMigrationDemo {
    private static final PrintStream OUT =
            new PrintStream(System.out, true, StandardCharsets.UTF_8);

    private StructuredMigrationDemo() {
    }

    private static String quote(String source) {
        StringBuilder result = new StringBuilder("\"");

        for (int i = 0; i < source.length(); i++) {
            char ch = source.charAt(i);

            switch (ch) {
                case '"' -> result.append("\\\"");
                case '\\' -> result.append("\\\\");
                case '\n' -> result.append("\\n");
                case '\r' -> result.append("\\r");
                case '\t' -> result.append("\\t");
                default -> {
                    if (ch < 0x20) {
                        result.append(
                                String.format(Locale.ROOT,
                                        "\\u%04x", (int) ch));
                    } else {
                        result.append(ch);
                    }
                }
            }
        }

        return result.append('"').toString();
    }

    private static String jsonValue(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String text) {
            return quote(text);
        }
        if (value instanceof Boolean
                || value instanceof Integer
                || value instanceof Long) {
            return value.toString();
        }
        throw new IllegalArgumentException(
                "Unsupported JSON value type: "
                + value.getClass().getName());
    }

    private static void writeEvent(Map<String, Object> fields) {
        StringBuilder result = new StringBuilder("{");
        boolean first = true;

        for (Map.Entry<String, Object> field : fields.entrySet()) {
            if (!first) {
                result.append(",");
            }
            first = false;

            result.append(quote(field.getKey()))
                    .append(":")
                    .append(jsonValue(field.getValue()));
        }

        OUT.println(result.append("}"));
    }

    public static void main(String[] args) {
        Map<String, Object> order = new LinkedHashMap<>();
        order.put("timestamp", "2026-01-01T00:00:00Z");
        order.put("level", "INFO");
        order.put("event_code", "order.created");
        order.put("order_id", "O-17");
        order.put("amount_minor", 120000);
        order.put("currency", "VND");
        order.put("message", "Đã tạo đơn");
        writeEvent(order);

        Map<String, Object> failure = new LinkedHashMap<>();
        failure.put("timestamp", "2026-01-01T00:00:01Z");
        failure.put("level", "ERROR");
        failure.put("event_code", "payment.failed");
        failure.put("order_id", "O-17");
        failure.put("error_code", "GATEWAY_TIMEOUT");
        failure.put("retryable", true);
        failure.put("trace_id", "tr-42");
        failure.put("message", "Gateway timeout: \"read\"");
        writeEvent(failure);
    }
}
```

**Lưu ý về timestamp:** hai giá trị thời gian được **cố định cho bài test**, không đại diện cho thời điểm chạy thật. Trong ứng dụng production, timestamp của logging event nên do backend ghi theo đồng hồ và quy ước timezone đã thống nhất.

### 8.2. Biên dịch và chạy

Yêu cầu JDK 17 trở lên:

```bash
javac -encoding UTF-8 StructuredMigrationDemo.java
java StructuredMigrationDemo
```

**Hai dòng stdout chính xác do chương trình in:**

```json
{"timestamp":"2026-01-01T00:00:00Z","level":"INFO","event_code":"order.created","order_id":"O-17","amount_minor":120000,"currency":"VND","message":"Đã tạo đơn"}
{"timestamp":"2026-01-01T00:00:01Z","level":"ERROR","event_code":"payment.failed","order_id":"O-17","error_code":"GATEWAY_TIMEOUT","retryable":true,"trace_id":"tr-42","message":"Gateway timeout: \"read\""}
```

### 8.3. Đọc kết quả như dữ liệu có cấu trúc

Trong dòng thứ nhất:

- `"order_id":"O-17"` là string, giữ dấu gạch ngang và mọi định dạng ID.
- `"amount_minor":120000` là **số JSON**, không có dấu nháy.
- `"currency":"VND"` là string chỉ đơn vị tiền.
- `"event_code":"order.created"` giữ ý nghĩa sự kiện, không phụ thuộc câu `message`.

Trong dòng thứ hai:

- `"retryable":true` là boolean JSON.
- `"trace_id":"tr-42"` giúp liên kết log.
- `"message":"Gateway timeout: \"read\""` đã escape dấu nháy của giá trị chuỗi đúng cách.
- Dòng này chưa lưu stack trace; ví dụ cố tình mô tả trường. Khi cần exception thật, backend logging phải nhận Throwable và serialize theo schema.

**Vì sao dùng `LinkedHashMap`?** Nó duy trì thứ tự chèn field, giúp stdout bài thực hành có thứ tự dự đoán được. **Thứ tự property trong JSON object không phải ý nghĩa nghiệp vụ**. Các consumer không nên phụ thuộc vào việc `event_code` nhất thiết đứng trước `message`.

**Vì sao cần `quote`?** Nếu nối trực tiếp `"message":"` + input + `"`, một giá trị có dấu nháy, newline hoặc ký tự điều khiển có thể phá cú pháp JSON hoặc tạo log injection. Bộ helper của ví dụ escape chuỗi ở phạm vi giá trị được hỗ trợ. Với dữ liệu production, dùng JSON encoder chuẩn để xử lý kiểu dữ liệu đa dạng, nested object, surrogate Unicode và các giới hạn an toàn.

**Vì sao không gọi `System.out.println(map.toString())`?** `Map.toString()` của Java tạo dạng giống `{key=value}`, **không phải JSON**. Nó không giữ một schema JSON có kiểu và escaping hợp lệ. Dùng một serializer/encoder đáng tin trong hệ thống thật.

## 9. Chuyển Logback từ PatternLayoutEncoder text sang JSON

Trong nhiều ứng dụng, mã sử dụng **SLF4J** và backend là **Logback Classic**. Khi muốn chuyển từ text sang structured, có thể giữ facade và thay encoder ở appender, đồng thời chuyển những thông tin nghiệp vụ thành field.

### 9.1. Cấu hình text trước khi chuyển

Ví dụ `src/main/resources/logback.xml`:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Đầu ra text phụ thuộc ngày giờ, thread và logger. Các giá trị nghiệp vụ có thể chỉ nằm trong `%msg`.

### 9.2. Thêm dependency cho JSON encoder

Một lựa chọn là **`logstash-logback-encoder`**, hoạt động cùng Logback. Ví dụ một `pom.xml` **độc lập** cho JDK 17, dùng SLF4J API được kéo theo bởi Logback Classic:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>structured-logback-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
        </dependency>
        <dependency>
            <groupId>net.logstash.logback</groupId>
            <artifactId>logstash-logback-encoder</artifactId>
            <version>8.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Các phiên bản ở đây là **một bộ phiên bản minh họa cố định**, không phải khẳng định về phiên bản mới nhất hay hướng dẫn bỏ qua dependency management của framework. Khi áp dụng thực tế, chọn bản Logback/SLF4J/encoder được hỗ trợ và kiểm tra thông báo bảo mật, yêu cầu JDK cùng dependency bắc cầu của dự án.

### 9.3. Đổi `logback.xml` sang encoder JSON

```xml
<configuration>
    <appender name="JSON_STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder class="net.logstash.logback.encoder.LogstashEncoder">
            <customFields>{"service":"checkout","environment":"demo"}</customFields>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="JSON_STDOUT" />
    </root>
</configuration>
```

Giải thích:

- `ConsoleAppender` vẫn ghi vào stdout: phù hợp kiến trúc logging theo container.
- `LogstashEncoder` chuyển event Logback thành JSON theo các provider/quy tắc của encoder.
- `customFields` bổ sung trường chung cho service/môi trường trong ví dụ. Với deployment thật, môi trường thường lấy từ cấu hình bên ngoài đã kiểm soát; không cố định `demo` trong image production.
- `Root level="INFO"` tiếp tục quyết định log nào được ghi.
- Chỉ gắn một appender JSON vào root trong ví dụ; không giữ thêm ConsoleAppender text cùng output khi chưa có kế hoạch tránh nhân đôi.

**Đừng đặt `LogstashEncoder` vào `logback.xml` khi dependency không có trên runtime classpath.** Backend có thể báo lỗi khởi tạo appender/encoder. Kiểm tra toàn bộ dependency graph và cấu hình nạp thật.

### 9.4. Java SLF4J 2.x: gắn field và Throwable rõ ràng

Tạo `src/main/java/demo/StructuredLogbackDemo.java`:

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class StructuredLogbackDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(StructuredLogbackDemo.class);

    private StructuredLogbackDemo() {
    }

    public static void main(String[] args) {
        MDC.put("trace_id", "tr-42");
        try {
            LOG.atInfo()
                    .addKeyValue("event_code", "order.created")
                    .addKeyValue("order_id", "O-17")
                    .addKeyValue("amount_minor", 120000)
                    .addKeyValue("currency", "VND")
                    .log("Đã tạo đơn hàng");

            try {
                throw new IllegalStateException("gateway unavailable");
            } catch (IllegalStateException failure) {
                LOG.atError()
                        .addKeyValue("event_code", "payment.failed")
                        .addKeyValue("order_id", "O-17")
                        .addKeyValue("error_code", "GATEWAY_TIMEOUT")
                        .addKeyValue("retryable", true)
                        .setCause(failure)
                        .log("Không thể hoàn tất thanh toán");
            }
        } finally {
            MDC.remove("trace_id");
        }
    }
}
```

Chạy từ thư mục dự án:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.StructuredLogbackDemo
```

Đoạn này cần JDK 17, Maven và các dependency XML ở trên. Khi backend thực sự dùng `LogstashEncoder` và cấu hình đã nạp, stdout là các JSON object chứa những thuộc tính như `message`, `level`, `logger_name`, `trace_id`, `event_code`, `order_id` và khi có lỗi là dữ liệu exception/stack trace theo thiết kế encoder.

**Không có một stdout byte-for-byte cố định cho ví dụ Logback này.** Timestamp, thread, logger name và biểu diễn exception có thể phụ thuộc phiên bản/cấu hình; hơn nữa cấu trúc field mặc định của encoder có thể bao gồm các thuộc tính khác. Muốn kiểm thử phải **parse JSON và assert từng field**, không so sánh toàn bộ dòng với một chuỗi cố định. Ví dụ Java thuần ở phần 8 đã cung cấp stdout chính xác để học cơ chế dữ liệu có cấu trúc.

### 9.5. MDC nên dùng cho dữ liệu gì?

`MDC` thích hợp cho ngữ cảnh dùng chung trong phạm vi xử lý: `trace_id`, `request_id` hoặc `tenant_id` nếu có chính sách bảo mật phù hợp. Các giá trị này có thể được encoder thêm vào mọi sự kiện trong phạm vi.

Dùng:

```java
MDC.put("request_id", requestId);
try {
    processRequest();
} finally {
    MDC.remove("request_id");
}
```

Đây là **đoạn minh họa**, giả định đã có `requestId` và `processRequest()`. Với thread pool, `CompletableFuture` hoặc framework reactive, MDC không tự được chuyển qua mọi luồng: cần cơ chế truyền ngữ cảnh thích hợp và kiểm thử.

**Không đặt mọi dữ liệu nghiệp vụ vào MDC.** `order_id` của một event cụ thể có thể được thêm ngay vào sự kiện bằng key-value. Nếu đưa dữ liệu biến đổi liên tục vào MDC toàn thread, dễ làm rò giá trị giữa các tác vụ và gây nhầm lẫn với các event không cùng đơn hàng.

## 10. Log4j 2: chuyển từ PatternLayout sang JSON có cấu trúc

Nếu mã dùng **Log4j 2 API** hoặc SLF4J được nối đúng tới Log4j 2 Core, một hướng phổ biến là thay PatternLayout text bằng layout JSON có khả năng biểu diễn các trường của logging event.

Ví dụ cấu hình text ban đầu:

```xml
<Configuration>
    <Appenders>
        <Console name="TEXT" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%d{ISO8601} %-5level %c - %m%n" />
        </Console>
    </Appenders>
    <Loggers>
        <Root level="info">
            <AppenderRef ref="TEXT" />
        </Root>
    </Loggers>
</Configuration>
```

Khi chuyển sang JSON, có thể dùng **`JsonTemplateLayout`** trong module `log4j-layout-template-json` tương thích hoặc layout JSON được phiên bản Log4j 2 hỗ trợ, kèm dependency cần thiết.

Ví dụ **đoạn XML minh họa** vị trí một layout JSON template:

```xml
<Console name="JSON" target="SYSTEM_OUT">
    <JsonTemplateLayout
        eventTemplateUri="classpath:EcsLayout.json"
        stackTraceEnabled="true" />
</Console>
```

**Điều kiện:** ứng dụng phải có dependency/module và template đúng phiên bản. Cấu hình này **không phải ví dụ độc lập**; cần thêm khung `<Configuration>`, `<Appenders>`, `<Loggers>`, appender reference và dependency Log4j 2 tương thích. Tên field, đường dẫn template, cách ánh xạ message/Throwable/ThreadContext phụ thuộc template, vì vậy không nên giả định nó cho JSON giống LogstashEncoder.

Đối với mã Log4j 2 API, các trường nghiệp vụ có thể truyền qua `StringMapMessage` hoặc cơ chế message/key-value được hỗ trợ:

```java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.logging.log4j.message.StringMapMessage;

Logger log = LogManager.getLogger("demo.payment");
StringMapMessage event = new StringMapMessage()
        .with("event_code", "payment.failed")
        .with("order_id", "O-17")
        .with("error_code", "GATEWAY_TIMEOUT");
log.error(event);
```

Đây là **mã minh họa trong phạm vi một phương thức**, không phải Java class độc lập; để các cặp xuất thành field JSON cần một layout/template biết xử lý `MapMessage`. Nếu layout chỉ in `%m`, dữ liệu có thể bị thu gọn thành chuỗi thay vì field JSON. Khi cần kèm Throwable, dùng lời gọi/hợp đồng hỗ trợ `Throwable` của API và xác minh output.

**Không thay Logback bằng Log4j 2 chỉ vì muốn structured logging** nếu backend hiện có đã hỗ trợ JSON đầy đủ. Chuyển backend có thể tạo rủi ro xung đột provider, bridge, config và thay đổi behavior. Đa số trường hợp có thể nâng cấp encoder/schema trên backend hiện tại.

## 11. Khi chưa sửa được mã Java: parse log text thành field ở collector

Trong một hệ thống legacy, việc sửa hàng nghìn câu log có thể không thực hiện ngay. Một bước chuyển tiếp là **parse text ở ingestion**.

Ví dụ text legacy có dạng cố định:

```text
INFO order=O-17 amount=120000 currency=VND
```

Một regex minh họa:

```regex
^(?<level>INFO|WARN|ERROR) order=(?<order_id>\S+) amount=(?<amount_minor>\d+) currency=(?<currency>[A-Z]{3})$
```

Khi parser hỗ trợ named groups, có thể tách `level`, `order_id`, `amount_minor` và `currency`. Nhưng hãy nhớ:

- Regex nhóm `amount_minor` ban đầu là **chuỗi**; pipeline phải chuyển thành số.
- Nếu message thay đổi thứ tự hoặc xuất thêm khoảng trắng, regex có thể không còn khớp.
- Nếu giá trị chứa dấu cách/`=`/newlines, parser đơn giản dễ sai.
- Regex chỉ nhận diện **một dạng log**; exception multiline và thông điệp từ thư viện có cấu trúc khác.
- Parser không thể suy ra chính xác `event_code` nếu log không có quy tắc gán ổn định.
- Truy vấn/dashboards còn phụ thuộc mapping của đích.

**Parse legacy là giải pháp chuyển tiếp**, không phải thay thế hoàn toàn việc phát field có cấu trúc từ nguồn. Nên đo **tỷ lệ bản ghi parse thành công, tỷ lệ field thiếu, tỷ lệ lỗi kiểu dữ liệu** và lưu đủ bản gốc theo quyền/retention nếu cần điều tra.

### Nguy cơ mất lịch sử khi cắt chuyển

Log cũ đã lưu chỉ dưới dạng text sẽ không tự có field mới sau khi deploy phiên bản Java mới. Có thể phải:

1. Giữ query cũ song song cho dữ liệu lịch sử.
2. Backfill/reindex dữ liệu cũ nếu có yêu cầu thật và chi phí cho phép.
3. Xây dashboard có mốc chuyển đổi theo ngày.
4. Thống nhất khi nào có thể xóa parser cũ.

Không được giả định schema mới có hiệu lực hồi tố trên mọi bản ghi lịch sử.

## 12. Giữ tương thích, tránh nhân đôi và kế hoạch rollback

Một chiến lược triển khai có thể gồm:

```text
Phase A: Text hiện tại + thống kê consumer/field cần giữ
Phase B: Schema ổn định + test ở môi trường phát triển
Phase C: JSON canary trên một service/instance
Phase D: Dashboard/alert chuyển sang field mới
Phase E: Mở rộng JSON + theo dõi ingest, lỗi parse, chi phí
Phase F: Bỏ text/parser không cần thiết sau khi xác nhận
```

Ở giai đoạn canary, nên có **cách phân biệt định dạng** ở collector, ví dụ theo deployment version hoặc pipeline/source riêng. Một số rủi ro:

- Cả text và JSON được gửi vào cùng index, khiến mapping conflict và dashboard tăng gấp đôi event.
- Một service tạo hai appender text và JSON cùng ghi stdout, collector đếm cả hai như hai giao dịch.
- Alert regex cũ vẫn chạy nhưng field mới đã có, gây cảnh báo lặp.
- Dữ liệu từ nhiều version dùng tên field khác nhau; cùng truy vấn không trả kết quả nhất quán.
- JSON encoder mới in stack trace rất dài hoặc chứa field nhạy cảm mà text trước đây không in.
- Collector không parse được JSON do line framing/multiline.
- Khi rollback, service quay về text nhưng query mới mất dữ liệu.

Để an toàn, chọn **một sự kiện chuẩn** cho phép đếm KPI, định rõ nguồn được tin cậy, và có cờ/phiên bản schema nếu sự thay đổi không tương thích.

### Có cần giữ cùng tên trường `message` không?

Thông thường nên giữ `message` để người vận hành đọc nhanh. Structured logging **không loại bỏ câu mô tả con người**; nó đưa dữ liệu quan trọng ra các field riêng. Điều có thể thay đổi là việc dashboard không còn parse các ID từ `message`.

Nếu cần tương thích một thời gian, message có thể giữ một số từ khóa cũ, nhưng đừng biến câu văn thành nguồn sự thật lâu dài. Trường `event_code`, `error_code` và các field typed nên là giao diện truy vấn ổn định.

## 13. Kiểu dữ liệu và mapping ở kho log

Khi JSON đã xuất đúng từ ứng dụng, collector và kho đích vẫn có thể thay đổi hoặc làm mất kiểu dữ liệu.

Một bộ test cần xác minh:

```json
{
  "event_code": "payment.failed",
  "attempt": 3,
  "retryable": false,
  "duration_ms": 1250,
  "trace_id": "tr-42",
  "error_code": "GATEWAY_TIMEOUT"
}
```

Sau ingest:

- `attempt` còn là integer hay bị chuyển thành string?
- `duration_ms` là số, đủ độ lớn và thống nhất đơn vị chưa?
- `retryable` còn là boolean hay bị parser chuyển thành `"false"`?
- `trace_id` được giữ nguyên, không bị xem là số hoặc cắt ký tự?
- `event_code` có thể lọc chính xác và nhóm ổn định không?
- Field vắng mặt và null có được xử lý nhất quán không?
- Các giá trị chứa Unicode, dấu nháy, newline có được giữ nguyên không?

Trong những hệ thống như Elasticsearch, OpenSearch hoặc công cụ có mapping/schema, **một field dùng hai kiểu khác nhau** có thể gây lỗi ingest hoặc truy vấn. Với các công cụ khác, kiểu có thể linh hoạt hơn nhưng vẫn cần quy ước để dashboard không sai.

### Cẩn trọng với số đo tiền và thời gian

Không ghi:

```json
{"amount":"1.200.000 VND","duration":"2 seconds"}
```

nếu mục tiêu là tổng hợp số học. Thay vào đó:

```json
{"amount_minor":1200000,"currency":"VND","duration_ms":2000}
```

**Giá trị tiền ở ví dụ là dữ liệu giả.** Quan trọng là cùng một thước đo dùng cùng đơn vị và kiểu. Đối với tiền tệ khác nhau, không cộng `amount_minor` của nhiều currency như cùng một đơn vị.

### Event schema version

Khi cần thay đổi không tương thích, có thể thêm một trường như `schema_version` hoặc phân tách namespace/event mới. Không cần tăng version cho mỗi lần sửa câu message. Tăng khi **ý nghĩa hoặc kiểu của trường** thay đổi làm consumer cũ không đọc đúng.

Một thay đổi thêm field tùy chọn có thể tương thích, nhưng thay `duration_ms` từ số sang chuỗi là thay đổi phá vỡ hợp đồng. Cần kiểm tra cách kho đích và ứng dụng consumer xử lý.

## 14. Correlation ID, MDC và ngữ cảnh phân tán

Structured logging phát huy giá trị khi log của nhiều service có thể được nối bằng ID.

Ví dụ:

```text
gateway:  trace_id=tr-42 event=request.received
checkout: trace_id=tr-42 event=order.created
payment:  trace_id=tr-42 event=payment.failed
gateway:  trace_id=tr-42 event=request.failed
```

Các giá trị `trace_id` có thể được đưa vào MDC/ThreadContext tại ranh giới request và được encoder xuất ở mọi bản ghi. Tuy nhiên:

1. MDC thường gắn với **thread/context**, không tự truyền qua mọi `ExecutorService` hoặc `CompletableFuture`.
2. Một thread trong pool có thể phục vụ nhiều request, nên **bắt buộc cleanup** theo lifecycle.
3. Không tạo trace ID mới ở mỗi phương thức: như vậy log không còn liên kết.
4. Không đặt `trace_id`/`order_id` thành tên logger để tạo hàng triệu logger động.
5. Không cho rằng mọi `trace_id` đều an toàn công khai; quyền truy cập log vẫn cần kiểm soát.

Nếu hệ thống dùng tracing theo chuẩn của nền tảng, nên lấy ID từ tracing context thật; **đừng tự phát minh format rồi xem nó là một distributed trace chuẩn**. Khi đổi backend hoặc cơ chế instrumentation, test propagation và mapping sang field log.

### Request ID, Trace ID, Span ID

- `request_id`: ID của một request theo hệ thống của bạn.
- `trace_id`: ID cho toàn bộ trace phân tán, có thể qua nhiều service.
- `span_id`: một phần công việc trong trace, khi tracing framework có khái niệm span.
- `event_code`: loại sự kiện, không phải ID phiên xử lý.

Một event có thể có nhiều ID, mỗi ID có vai trò riêng. Chỉ ghi ID nào đã được tạo/hợp đồng công nhận; đừng trộn lẫn chúng vì trông giống chuỗi.

## 15. Throwable, stack trace và lỗi nghiệp vụ

Log text thường ghi ngoại lệ theo dạng:

```text
ERROR Payment failed: java.lang.IllegalStateException: gateway unavailable
    at ...
    at ...
```

Với JSON, có thể chọn trường như `exception_type`, `error_code`, `stack_trace` và `message`, nhưng việc nhận được stack trace phụ thuộc **backend/encoder và việc truyền Throwable**.

Lời gọi đúng ý khi cần giữ nguyên nhân:

```java
log.atError()
        .addKeyValue("event_code", "payment.failed")
        .addKeyValue("order_id", orderId)
        .addKeyValue("error_code", errorCode)
        .setCause(exception)
        .log("Không thể hoàn tất thanh toán");
```

Không tương đương với:

```java
log.error("payment failed: {}", exception.getMessage());
```

Trong lời gọi thứ hai, backend chỉ nhận một string message đã định dạng; **không tự giữ đối tượng Throwable gốc**. Nếu có cause chain quan trọng, cần truyền Throwable bằng API thích hợp.

### Đừng tạo hai event thất bại cuối từ một exception

Trong nhiều kiến trúc Java, repository ném exception, service bọc nguyên nhân, controller trả lỗi. Nếu cả ba tầng cùng ghi `payment.failed` và rồi ném lại, một giao dịch có thể bị đếm ba lần. Structured logging **không tự khử trùng lặp sự kiện logic**.

Chọn ranh giới log cuối hoặc đặt mã sự kiện khác nhau nếu mỗi tầng thực sự mang ý nghĩa khác nhau. Khi xây KPI, định nghĩa sự kiện đếm rõ ràng và tốt nhất dùng metric nghiệp vụ/tác vụ hoàn tất có nguồn đáng tin.

### Làm gì với stack trace nhiều dòng?

Text stack trace có thể gây collector hiểu một exception thành nhiều record. JSON encoder đúng thường escape newline trong string hoặc biểu diễn exception theo cấu trúc được hỗ trợ, nhưng **không phải mọi JSON encoder đều tạo cùng schema**. Hãy test log exception thực, parse từng record và so sánh loại lỗi/cause cần thiết.

Đừng cắt stack trace quá sớm chỉ vì muốn một dòng ngắn: cần giữ đủ dữ liệu điều tra trong kênh cho phép, có giới hạn kích thước và chính sách dữ liệu rõ ràng.

## 16. Bảo mật: chuyển sang JSON không có nghĩa là an toàn hơn

Structured logging làm dữ liệu **dễ truy vấn hơn**, vì vậy cũng có thể làm dữ liệu nhạy cảm dễ tìm hơn nếu bị ghi sai.

Các nguồn rò rỉ phổ biến:

- HTTP header `Authorization`, cookie, API key.
- Request/response body chứa thông tin cá nhân.
- `Throwable.getMessage()` chứa URL với token hoặc SQL kèm tham số.
- `toString()` của một domain object chứa dữ liệu riêng tư.
- MDC giữ user ID/tenant ID vượt phạm vi cần thiết.
- JSON encoder mặc định xuất thêm field không được phép.
- Collector ghi bản gốc sau khi ứng dụng đã cố che ở một trường khác.

Nguyên tắc:

1. **Data minimization:** chỉ ghi trường cần cho điều tra, không dump cả object.
2. **Allowlist field:** xác định trường được phép xuất cho từng loại event.
3. **Mask hoặc loại bỏ tại nguồn:** tránh để secret lọt vào event hoặc Throwable nếu có thể.
4. **Kiểm tra mọi đích:** stdout, file, collector, kho tập trung; hai appender có thể áp dụng chính sách khác nhau.
5. **Giới hạn quyền đọc và thời gian lưu:** việc chuyển định dạng không thay retention/compliance.
6. **Kiểm tra injection:** giá trị có quote, newline, tab hoặc ký tự điều khiển phải được JSON encoder escape đúng.
7. **Không dùng secret thật trong test:** dùng chuỗi giả như `SECRET_TEST_TOKEN_123` rồi assert nó **không xuất hiện** trong output.

Parameter substitution `{}` hoặc fluent `addKeyValue` **không che giá trị tự động**. Muốn tránh lộ secret phải quyết định từ nguồn, không chỉ sửa pattern.

## 17. Hiệu năng, dung lượng và cardinality

Structured logging có thể tăng số byte cho mỗi event vì lặp lại tên field, timestamp, service và ngữ cảnh. Điều đó **không nhất thiết là xấu**: đổi lại, truy vấn và vận hành có thể chính xác hơn. Nhưng cần đo trước khi áp dụng diện rộng.

Những nguồn chi phí:

- Encoder serialize JSON, escape chuỗi, format exception.
- Bổ sung trường toàn cục vào mọi event.
- Stack trace lớn hoặc object lồng sâu.
- Collector parse và lưu field nhiều hơn.
- Kho log lập chỉ mục quá nhiều field động.
- Nhiều bản ghi do retry hoặc dual output text+JSON.
- Log tần suất DEBUG/TRACE cao.

### Phân biệt field có giá trị động với metric label

`trace_id` hoặc `order_id` thường có **cardinality cao** vì có vô số giá trị khác nhau. Chúng hữu ích cho **tìm kiếm một request**, nhưng không nên lấy làm nhãn metric tổng hợp không giới hạn.

Những trường có danh mục ổn định như `event_code`, `service`, `environment`, `result` hoặc `error_code` thường phù hợp hơn cho nhóm dashboard/metric. Nhưng nếu `error_code` được tạo ngẫu nhiên hoặc nối ID vào cuối thì bản thân nó cũng có thể trở thành cardinality cao.

### Structured logging không biến log thành hệ thống giao nhận bảo đảm

Một sự kiện JSON hợp lệ vẫn có thể mất khi:

- Appender queue đầy hoặc backend drop.
- Container restart trước khi flush.
- Collector bị lỗi hoặc mất kết nối.
- Rotation xóa dữ liệu cũ trước khi được đọc.
- Bộ thu thập bị filter hoặc mapping reject.
- Hệ thống index chậm/thất bại.

Các sự kiện audit hoặc nghiệp vụ yêu cầu chính xác tuyệt đối cần cơ chế lưu/gửi và đối soát chuyên biệt; không nên chỉ dựa vào `log.info`.

## 18. Kiểm thử migration: từ schema đến collector

Một bộ test tốt có ít nhất bốn tầng.

### 18.1. Kiểm thử ý nghĩa tại nguồn

Trong unit test, xác nhận:

- Sự kiện đúng `event_code` theo tình huống.
- Level đúng (retry tạm thời khác thất bại cuối).
- `order_id`, `error_code`, `attempt` và `retryable` có nghĩa đúng.
- Có Throwable cho exception cần điều tra.
- Không log một thất bại cuối nhiều lần vô tình.
- Không phát event lỗi khi thao tác đã phục hồi.

Các assertion kiểu này có thể dùng ListAppender/handler hoặc abstraction riêng, nhưng **chưa chứng minh JSON được encode đúng**.

### 18.2. Kiểm thử JSON đầu ra

Phát event qua encoder thật, rồi đọc byte từ appender test/console subprocess. **Parse JSON bằng thư viện JSON đáng tin**, đừng chỉ tìm chuỗi:

```text
"retryable":true
```

Vì dấu cách và thứ tự field có thể thay đổi. Kiểm tra kiểu và giá trị sau parse:

| Field | Assertion có ý nghĩa |
| --- | --- |
| `event_code` | Bằng `payment.failed` |
| `retryable` | Boolean `false`/`true` theo tình huống |
| `attempt` | Number nguyên và đúng giá trị |
| `order_id` | String và giữ định dạng ID |
| `trace_id` | Có khi context được thiết lập |
| `error_code` | Thuộc danh mục hợp lệ |
| `stack_trace` | Có khi exception cần chẩn đoán, theo schema |
| `message` | Là string dễ hiểu, không chứa secret |

Nếu muốn bảo đảm JSON Lines, mỗi dòng phải là một object JSON parse được và dữ liệu có xuống dòng bên trong message phải được escape, không tạo “dòng log giả”.

### 18.3. Kiểm thử collector và mapping

Trong staging hoặc môi trường tích hợp, phát một tập event có `trace_id`/`event_code`/schema version xác định. Sau đó xác minh:

1. Collector nhận đúng stdout/file.
2. Dữ liệu parse thành JSON, không bị trộn với text build tool.
3. Field có kiểu đúng tại kho lưu trữ.
4. Timestamp có thể tìm theo cửa sổ thời gian phù hợp.
5. Không có mapping conflict hoặc reject record.
6. Có thể lọc/group theo field mới.
7. Kịch bản lỗi có cause/stack trace theo yêu cầu.
8. Không có dữ liệu giả cần che.
9. Số event ở đích so với số phát ra phù hợp chính sách drop/retry.
10. Truy vấn/dashboard cũ và mới trong giai đoạn canary được đối chiếu.

### 18.4. Kiểm thử rollout và rollback

Chạy canary có kiểm soát để đo:

- Tỷ lệ log JSON hợp lệ.
- Tỷ lệ record thiếu field bắt buộc.
- Số lượng mapping conflict/parse fail.
- Lưu lượng log theo service/level.
- Độ trễ ingest và số bản ghi bị drop.
- Dashboard/alert có tiếp tục đúng không.
- Rollback có đưa hệ thống về text và query tương ứng không.

Đừng chọn tiêu chí duy nhất là “console in ra dấu ngoặc nhọn”. Một chuỗi trông như JSON có thể sai escape, sai kiểu field hoặc không tới kho tìm kiếm.

## 19. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| `log.info("order={}", id)` nhưng collector không có `order_id` | Chỉ format message, chưa gửi field có cấu trúc | Dùng key-value/event data và encoder hỗ trợ. |
| JSON output chỉ có `message` | Layout chưa xuất custom key-value hoặc MDC | Kiểm tra provider/encoder/schema. |
| Log text và JSON đều xuất ra stdout | Hai appender hoặc hai đường route | Đặt kế hoạch dual-write, tránh nhân đôi event. |
| Dashboard cũ mất dữ liệu | Query regex dựa text cũ | Chuyển query theo field và giữ giai đoạn tương thích. |
| Một field có lúc số lúc chuỗi | Schema không cố định | Thống nhất kiểu/đơn vị, kiểm tra mapping. |
| Exception không thấy trong JSON | Không truyền Throwable hoặc encoder không xuất | Dùng `setCause`/overload thích hợp, test Throwable. |
| Trace ID thiếu trong async task | MDC không tự lan truyền | Dùng context propagation đúng framework. |
| Trace ID nhầm giữa request | Quên cleanup MDC/thread reuse | `finally` và kiểm tra lifecycle. |
| JSON bị cắt hoặc nhiều dòng lỗi | Encoder tự ghép text, record lớn, collector partial | Dùng encoder chuẩn, giới hạn event, test framing. |
| Container log tăng quá nhanh | Nhiều field/stack trace hoặc ghi trùng | Đo volume, level, retry, rotation và retention. |
| Không parse được Unicode/newline | Charset hoặc escaping sai | UTF-8 và JSON serializer đáng tin. |
| Có JSON nhưng collector không nhận | Wrong output stream, parser/index/filter | Kiểm tra toàn đường ingest. |
| `LogstashEncoder` không khởi tạo | Thiếu dependency hoặc version không tương thích | Kiểm tra runtime classpath và status log. |
| SLF4J có nhiều provider | Nhiều backend trên classpath | Chọn đúng một provider cuối. |
| JSON có secret | Gửi token/payload/exception vào event | Allowlist, mask tại nguồn, test secret giả. |
| Có nhiều event `payment.failed` cho một request | Retry/tầng xử lý đều log cùng semantic | Đặt ranh giới event và phân biệt attempt với final. |
| Không truy vấn lịch sử bằng field mới | Log cũ chưa backfill/reindex | Giữ query cũ hoặc migration dữ liệu có kế hoạch. |

## 20. Bài tập áp dụng

### Bài 1 — Thiết kế schema

Log cũ:

```text
Order O-17 completed in 153 ms, total=120000 VND
```

Hãy đề xuất field có kiểu.

**Gợi ý đáp án:**

```json
{
  "event_code": "order.completed",
  "order_id": "O-17",
  "duration_ms": 153,
  "amount_minor": 120000,
  "currency": "VND",
  "message": "Hoàn tất đơn hàng"
}
```

Cần xác nhận ý nghĩa `amount_minor` theo hệ thống tiền tệ thực tế; không tự ép một chuỗi tiền sang số khi chưa biết đơn vị.

### Bài 2 — Cú pháp SLF4J 2.x

Trong một method đã có `log`, `orderId`, `durationMs`, hãy ghi sự kiện thành công có ba field `event_code`, `order_id`, `duration_ms`.

**Gợi ý:**

```java
log.atInfo()
        .addKeyValue("event_code", "order.completed")
        .addKeyValue("order_id", orderId)
        .addKeyValue("duration_ms", durationMs)
        .log("Hoàn tất đơn hàng");
```

Sau đó kiểm tra encoder thực sự xuất ba field, trong đó `duration_ms` là số.

### Bài 3 — Phân biệt retry với thất bại cuối

Một payment timeout ở attempt 1 nhưng attempt 2 thành công. Có nên ghi `payment.failed` mức ERROR ở attempt 1 không?

**Gợi ý:** Nếu `payment.failed` được định nghĩa là giao dịch **thất bại cuối cùng**, thì không. Có thể ghi `payment.attempt_failed` với attempt và error_code; event cuối là kết quả thành công. Tránh dashboard đếm timeout tạm thời như payment thất bại.

### Bài 4 — Parse text legacy

Parser regex đọc `amount=120000` thành chuỗi `"120000"`. Sau khi chuyển sang JSON, dashboard muốn tính tổng amount. Cần làm gì?

**Gợi ý:** Chuyển field thành kiểu số, xác nhận đơn vị, giữ cùng mapping giữa mọi service và kiểm tra dữ liệu lỗi/thiếu. Không cộng trực tiếp chuỗi hoặc các loại tiền khác nhau.

### Bài 5 — Xử lý dữ liệu nhạy cảm

Một event có `Authorization: Bearer SECRET_TEST_TOKEN_123` trong exception message. Có đủ an toàn nếu JSON encoder escape quote và newline không?

**Gợi ý:** Không. JSON escaping chỉ bảo đảm cú pháp, **không tự che bí mật**. Cần ngăn/che secret trong message, Throwable và trường kèm theo; kiểm thử mọi kênh output.

### Bài 6 — Dual logging

Một service gửi cùng một event sang ConsoleAppender text và JSON, cả hai đều tới một index. Dashboard đếm số `order.created` tăng gấp đôi. Có thể sửa bằng cách đổi field name không?

**Gợi ý:** Vấn đề là **nhân đôi tuyến sự kiện**, không chỉ tên field. Chọn nguồn chuẩn, tách pipeline/kênh, loại bản không dùng khỏi phép đếm và có lộ trình gỡ dual-write.

### Bài 7 — Trace trong thread pool

Một request có `trace_id=tr-42` ở thread A, nhưng task chạy trên executor không có trace ID. Vì sao và sửa thế nào?

**Gợi ý:** MDC theo ngữ cảnh thực thi không tự lan truyền qua mọi thread. Dùng cơ chế context propagation được framework/tracing cung cấp, và cleanup khi thread được tái sử dụng. Kiểm tra log từ cả hai thread.

### Bài 8 — Kiểm thử migration end-to-end

Hãy viết checklist cho một event `payment.failed` trước khi rollout.

**Gợi ý:** Xác nhận event code và level, order ID, error code, số attempt, trạng thái cuối, Throwable, schema/type, JSON escaping, quyền dữ liệu, collector nhận đúng, query theo trace ID hoạt động, mapping không conflict, không duplicate, alert/dashboard mới đúng và rollback vẫn có cách tra log.

## 21. Checklist thực hiện tại dự án

- [ ] Biết backend và runtime provider thật; không có bridge/provider xung đột.
- [ ] Có danh mục `event_code` và owner chịu trách nhiệm.
- [ ] Có schema chung + schema theo event, tên/kiểu/đơn vị ổn định.
- [ ] Không còn phụ thuộc câu message để đếm và nhóm các sự kiện chính.
- [ ] Dữ liệu nghiệp vụ được gửi qua field, không chỉ qua placeholder `{}`.
- [ ] JSON encoder/layout thực sự xuất key-value và MDC cần thiết.
- [ ] Timestamp có timezone, kiểu đúng; duration và amount có đơn vị.
- [ ] Trace/request ID được truyền và cleanup đúng khi async/thread pool.
- [ ] Exception/stack trace giữ đủ cho chẩn đoán nhưng không lộ secret.
- [ ] Message Unicode, quote, backslash, newline được escape hợp lệ.
- [ ] Không phát một failure cuối nhiều lần ngoài chủ đích.
- [ ] Không ghi toàn bộ request/token/PII vào event.
- [ ] Collector parse được JSON và mapping không conflict.
- [ ] Dashboard/alert mới dựa trên field; lịch sử text có kế hoạch tương thích.
- [ ] Canary đo ingest/drop/volume/cost và có quy trình rollback.
- [ ] Retention, quyền đọc và khả năng mất log được xem xét riêng.
- [ ] Không dùng log như nguồn duy nhất cho dữ liệu audit cần exactly-once.

**Kết luận:** Chuyển log text sang structured là chuyển từ **“câu chữ để đọc”** sang **“sự kiện có schema để máy và người cùng hiểu”**. Bắt đầu bằng field và ý nghĩa ổn định, phát các giá trị có kiểu ngay từ mã Java, dùng encoder JSON thực sự, kiểm tra Throwable/MDC và collector, rồi chuyển dần consumer cũ bằng canary có khả năng rollback. Khi làm đúng, hệ thống tìm lỗi chính xác hơn mà vẫn giữ message dễ đọc cho con người.