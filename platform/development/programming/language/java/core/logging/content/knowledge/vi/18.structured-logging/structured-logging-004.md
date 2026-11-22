# Field name ổn định trong Structured Logging

**Field name ổn định** là nguyên tắc đặt và duy trì **tên khóa dữ liệu có cấu trúc trong log một cách nhất quán** theo thời gian, giữa các service, môi trường, phiên bản ứng dụng và pipeline xử lý. Khi một event ghi `requestId` hôm nay thì ngày mai không nên tùy tiện đổi thành `request_id`, `requestID` hoặc `rid` trong khi các dashboard, cảnh báo và truy vấn còn dựa vào tên cũ.

Trong **structured logging**, log không chỉ là một chuỗi dành cho người đọc. Mỗi event có thể gồm những cặp **key–value** như `eventName`, `level`, `service`, `requestId`, `orderId`, `durationMs` và `errorCode`. Tên field chính là một phần của **hợp đồng dữ liệu (log schema)** giữa ứng dụng phát log và những bên tiêu thụ: collector, indexer, dashboard, hệ thống alert, công cụ điều tra sự cố, phân tích vận hành.

**Mục tiêu:** không phải khiến tất cả event đều có mọi field, mà là **mỗi tên field được định nghĩa rõ, giữ đúng ý nghĩa, kiểu dữ liệu và đơn vị**, đồng thời những thay đổi schema được quản lý như thay đổi API.

## 1. Vì sao tên field ổn định quan trọng?

Xét hai bản ghi nói về cùng loại yêu cầu:

```json
{"eventName":"checkout.completed","requestId":"req-17","durationMs":23,"outcome":"success"}
{"eventName":"checkout.completed","request_id":"req-18","duration_ms":"19ms","result":"ok"}
```

Con người có thể hiểu hai dòng có cùng ý nghĩa. Nhưng hệ thống tìm kiếm theo `requestId` sẽ bỏ sót bản ghi thứ hai; biểu đồ tính `avg(durationMs)` không thể tự động coi `"19ms"` là số `19`; quy tắc đếm `outcome="success"` không khớp với `result="ok"`.

Những bất nhất này tạo ra nhiều loại lỗi:

1. **Truy vấn thiếu dữ liệu:** log vẫn được ghi nhưng query lọc theo tên field cũ không còn thấy một phần sự kiện.
2. **Alert đánh giá sai:** số lỗi/tỷ lệ thất bại bị tính thấp hoặc bằng không vì một nhóm service chuyển tên field.
3. **Dashboard mất tính liên tục:** dữ liệu trước và sau đợt deploy nằm ở hai field khác nhau, không thể xem chung một cách đáng tin cậy.
4. **Correlation đứt đoạn:** truy vết từ API gateway sang service khác thất bại nếu nơi dùng `traceId`, nơi dùng `trace_id` mà pipeline không có chuẩn hóa.
5. **Chi phí ingest/index tăng:** nhiều alias cho cùng khái niệm làm phình schema, mapping và quy tắc xử lý.
6. **Khó điều tra sự cố:** người trực vận hành phải nhớ nhiều cách đặt tên, viết nhiều câu query dự phòng.
7. **Rủi ro tương thích ngược:** các công cụ tự động tiêu thụ log thường phụ thuộc field, dù log không có kiểu API công khai.

**Tính ổn định gồm nhiều yếu tố**: giữ tên, định nghĩa, loại dữ liệu, đơn vị, cách xử lý field thiếu và bộ giá trị được phép. Một tên `durationMs` vẫn “không ổn định về ý nghĩa” nếu phiên bản sau bí mật đổi giá trị sang microsecond.

## 2. Phân biệt tên field, giá trị và event name

Một structured event thường bao gồm:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "checkout-service",
  "eventName": "checkout.completed",
  "requestId": "req-17",
  "orderId": "ord-42",
  "durationMs": 23,
  "outcome": "success",
  "errorCode": null
}
```

Trong đó:

- **Field name** là tên khóa như `requestId` hoặc `durationMs`, phải có ý nghĩa rõ và duy trì nhất quán.
- **Field value** như `req-17` hoặc `23` thay đổi theo từng sự kiện.
- **Event name** như `checkout.completed` là **giá trị có phân loại**, cũng nên ổn định vì metric/alert có thể truy vấn theo nó.
- **Schema** mô tả những trường nào được phép hoặc bắt buộc, kiểu dữ liệu, đơn vị, tập giá trị và điều kiện xuất hiện.
- **Format** là cách chuyển event thành JSON, text hoặc cấu trúc khác. Đổi layout không tự sửa tên field đã phát sai ở ứng dụng.

**Sai lầm phổ biến:** tạo tên khóa động, ví dụ `"user_" + userId`, thay vì giữ khóa `userId` và đặt ID vào value. Với nhiều user, khóa động có thể gây **field explosion** trong index; đó là vấn đề khác với giá trị có cardinality cao, nhưng cả hai cần được quản lý.

```json
{"user_101":"logged_in","user_102":"logged_in"}
```

**Không nên** dùng cấu trúc trên để biểu diễn một event đăng nhập của một người dùng. Dùng tên khóa ổn định:

```json
{"eventName":"auth.login","userId":"101","outcome":"success"}
```

Ví dụ chỉ minh họa hình thức. `userId` có thể là dữ liệu nhạy cảm theo chính sách của tổ chức; cần xét việc có được log hay không, cách giả danh/pseudonymization và thời gian giữ.

## 3. Xây dựng một log schema có hợp đồng rõ ràng

Một schema tối thiểu nên quy định **name, type, semantic, unit, required/optional, nguồn phát sinh và yêu cầu bảo mật**. Ví dụ cho miền checkout:

| Tên field | Kiểu dữ liệu JSON | Ý nghĩa/đơn vị | Chính sách xuất hiện |
| --- | --- | --- | --- |
| `schemaVersion` | number (integer) | Phiên bản hợp đồng log event. | Bắt buộc khi áp dụng versioning ở mức event. |
| `timestamp` | string | Thời điểm event, ISO 8601/RFC 3339 kèm timezone. | Bắt buộc, nếu backend/collector không bổ sung thay. |
| `level` | string | Severity theo quy ước, như `INFO`, `WARN`, `ERROR`. | Bắt buộc. |
| `service` | string | Tên service ổn định theo hệ thống deploy. | Bắt buộc trong log tập trung. |
| `logger` | string | Namespace/class phát log. | Nên có để lọc theo thành phần. |
| `eventName` | string | Tên sự kiện ổn định như `checkout.completed`. | Bắt buộc với event nghiệp vụ định danh. |
| `requestId` | string | ID của một request hoặc đơn vị công việc tương đương. | Tùy ngữ cảnh, có thể thiếu ở job nền. |
| `traceId` | string | ID trace khi tracing được bật. | Tùy ngữ cảnh; không tự sinh nếu không có trace. |
| `orderId` | string | Định danh đơn hàng được phép lưu. | Chỉ với event liên quan đến đơn hàng. |
| `durationMs` | number (integer/decimal theo schema) | Thời lượng tính bằng **mili-giây**. | Có trên event đã đo thời lượng. |
| `outcome` | string (enum) | Trạng thái như `success`, `failure`, `rejected`. | Có với event kết thúc công việc. |
| `errorCode` | string hoặc null | Mã lỗi ổn định; không phải message tự do. | Có khi phát sinh lỗi hoặc trả `null` theo contract. |

Đây là **schema minh họa**, không phải tên trường bắt buộc cho mọi Java framework. Nếu hệ thống đã dùng **OpenTelemetry Semantic Conventions, Elastic Common Schema (ECS)** hoặc chuẩn nội bộ, hãy **chọn một quy ước chính và lập bảng mapping rõ ràng**, không tự đổi tất cả tên sang ví dụ này.

Một schema có chất lượng trả lời được câu hỏi: *“`durationMs` đo từ lúc nào đến lúc nào? Có tính thời gian retry? Nếu chưa đo, field vắng mặt, `null` hay `0`?”* Nếu không định nghĩa, dù tên giữ nguyên thì dữ liệu vẫn khó so sánh.

## 4. Quy tắc đặt tên field ổn định

### 4.1. Chọn một naming convention và áp dụng nhất quán

Một số phong cách:

| Convention | Ví dụ | Ghi chú |
| --- | --- | --- |
| `camelCase` | `requestId`, `durationMs`, `errorCode` | Dễ tương đồng với tên thuộc tính Java, nhưng không bắt buộc. |
| `snake_case` | `request_id`, `duration_ms`, `error_code` | Phổ biến ở một số hệ thống dữ liệu, công cụ observability. |
| Dạng tên có namespace hoặc nested | `http.response.status_code` hoặc object `http.response.status_code` | Cần hiểu sự khác nhau giữa chuỗi khóa chứa dấu chấm và object lồng nhau. |

**Không có một phong cách đúng cho mọi tổ chức.** Điều quan trọng là **schema và pipeline cùng hiểu một kiểu**, không để mỗi team tùy ý đặt tên cho cùng một khái niệm.

Nếu triển khai theo chuẩn OpenTelemetry hoặc ECS, phải tuân thủ **tên trường và cấu trúc do chuẩn đang áp dụng quy định**. Không tự áp một quy tắc camelCase lên những trường chuẩn vốn được định nghĩa khác.

### 4.2. Tên phải thể hiện ý nghĩa, tránh từ chung chung

So sánh:

| Tên khó dùng | Vấn đề | Ví dụ tên rõ hơn |
| --- | --- | --- |
| `id` | Không biết ID của đối tượng nào. | `requestId`, `orderId`, `jobId` |
| `status` | HTTP status, trạng thái job hay kết quả nghiệp vụ? | `httpStatusCode`, `jobStatus`, `outcome` |
| `time` | Thời điểm hay thời lượng? | `timestamp`, `durationMs` |
| `error` | Boolean, message, code hay object? | `errorCode`, `errorMessage`, `exceptionType` |
| `name` | Tên logger, user hay service? | `logger`, `service`, `customerType` |
| `data` | Nội dung tùy ý, khó lập mapping. | Trường có semantic cụ thể và kiểm soát được |

Không đặt tên quá dài bằng cách lặp nhiều cấp namespace không cần thiết. Một tên tốt phải **ngắn vừa đủ nhưng không mơ hồ**.

### 4.3. Đơn vị phải là một phần của hợp đồng

Một vấn đề rất dễ gây dashboard sai là dùng cùng một tên field nhưng thay đổi đơn vị:

```json
{"eventName":"api.completed","duration":250}
{"eventName":"api.completed","duration":0.25}
```

Ở đây `duration` không cho biết mili-giây hay giây. Sửa bằng cách quy định một kiểu rõ:

```json
{"eventName":"api.completed","durationMs":250}
{"eventName":"api.completed","durationMs":125}
```

Nếu ứng dụng dùng `durationMs`, **mọi producer phải phát số theo mili-giây**, không phát chuỗi `"250ms"`, không thay thành nanosecond mà vẫn giữ tên. Nếu sau này cần độ chính xác khác, phải quản lý thay đổi schema, ví dụ thêm `durationNs` và lộ trình chuyển đổi.

### 4.4. Không dùng giá trị động làm tên key

**Sai:**

```json
{"request_472":"success","request_473":"failure"}
```

**Đúng hướng:**

```json
{"requestId":"472","outcome":"success"}
{"requestId":"473","outcome":"failure"}
```

Dữ liệu biến động phải nằm ở value. Ngoài field explosion, key động làm mất khả năng đặt type, dùng mapping và phân quyền theo tên trường.

### 4.5. Không nhét tất cả dữ liệu vào message

**Chỉ có text message:**

```json
{"message":"order ord-42 completed in 23ms"}
```

Con người đọc được nhưng hệ thống phải parse chuỗi, dễ gãy khi đổi câu chữ hoặc ngôn ngữ. **Có field rõ ràng:**

```json
{"eventName":"checkout.completed","orderId":"ord-42","durationMs":23,"outcome":"success","message":"Checkout completed"}
```

Giữ `message` để hỗ trợ người đọc; những dữ liệu dùng cho truy vấn/alert nên có các field riêng. Không cố tách field có cấu trúc từ message bằng regex nếu API/backend đã hỗ trợ structured logging.

## 5. Giữ ổn định cả kiểu dữ liệu và tập giá trị

Tên giống nhau chưa đủ nếu các event xuất giá trị với type khác nhau:

```json
{"durationMs":23}
{"durationMs":"23"}
{"durationMs":"23ms"}
```

Trong một JSON schema rõ ràng, `durationMs` là **number**, không phải string. Một index/search backend có thể chọn mapping theo giá trị đầu tiên hoặc báo conflict khi bản ghi sau khác type. Hành vi phụ thuộc hệ thống ingest; không cần dựa vào một biểu hiện cụ thể để biết đây là schema không nhất quán.

### Quy tắc cho kiểu dữ liệu

- **ID:** thường chọn string ngay cả khi trông như số, vì ID không dùng phép cộng/trừ và có thể chứa số 0 ở đầu.
- **Thời lượng và kích thước:** thường dùng number với đơn vị rõ ràng; có thể dùng số nguyên nếu độ chính xác đáp ứng nhu cầu.
- **HTTP status:** nếu schema định nghĩa number, đừng có lúc viết `200`, lúc `"200"`.
- **Boolean:** chỉ dùng `true`/`false` cho tính chất nhị phân, không trộn với `"yes"`/`"no"`.
- **Timestamp:** chọn định dạng và timezone được công bố rõ; không thay giữa epoch milliseconds và chuỗi ngày giờ trong cùng field.
- **Error code:** nên là mã ổn định như `UPSTREAM_TIMEOUT` hoặc `INVALID_ORDER`, không biến chuỗi `errorMessage` thành nguồn phân loại alert.
- **Enum:** thống nhất `success`/`failure`/`rejected`, không đổi ngẫu nhiên thành `ok`/`failed`/`denied`.

**Giá trị enum cũng là hợp đồng.** Dashboard lọc theo `outcome="failure"` có thể bị gãy nếu release sau dùng `outcome="failed"` dù tên field không đổi.

### Null, absent, empty string và zero không tương đương

| Biểu diễn | Ý nghĩa có thể chọn | Cần định nghĩa |
| --- | --- | --- |
| Không có `errorCode` | Event này không có thuộc tính lỗi, hoặc producer chưa biết giá trị. | Phân biệt “không áp dụng” và “thiếu dữ liệu” nếu nghiệp vụ cần. |
| `"errorCode": null` | Contract có trường nhưng hiện không có lỗi cụ thể. | Collector có giữ null hay bỏ field không? |
| `"errorCode": ""` | Chuỗi rỗng, thường khó phân biệt với dữ liệu bị thiếu. | Tránh dùng làm “không lỗi” nếu có lựa chọn rõ ràng hơn. |
| `"durationMs": 0` | Thời lượng thực sự bằng không theo độ chính xác ghi nhận. | Không dùng để thay cho “chưa đo”. |

Cách chọn **không bắt buộc đồng nhất mọi field**. Quan trọng là producer, schema và consumer thống nhất, có test để bảo vệ lựa chọn.

## 6. Cấp độ ổn định: trong một service, nhiều service và nhiều phiên bản

### Một service, nhiều code path

Các controller, service, batch job cần dùng **cùng tên cho cùng semantic**. Không để REST controller ghi `requestId` nhưng background job lại dùng `reqId` cho cùng khái niệm nếu mục tiêu là truy vết thống nhất.

### Nhiều service

Nếu các service đều dùng `traceId` và `spanId` theo một tracing pipeline, hãy xác định cùng định dạng ID, vị trí gắn context và cách propagation. Không coi `requestId` và `traceId` là một thứ:

- **requestId** có thể nhận diện một request ở ranh giới API, không nhất thiết có cùng vòng đời với trace phân tán.
- **traceId** theo dõi trace xuyên nhiều service khi tracing được bật.
- **spanId** nhận diện một span trong trace.
- **correlationId** có thể là định danh quy trình nghiệp vụ dài hơn một request/trace nếu tổ chức định nghĩa như vậy.

Có thể gắn nhiều ID, nhưng không tự hoán đổi giá trị giữa các trường vì nghĩ chúng “đều là ID”.

### Nhiều phiên bản ứng dụng

Khi deploy rolling/blue-green, **hai phiên bản có thể cùng ghi log trong một khoảng thời gian**. Schema mới phải được xử lý khi các service và dashboard chưa nâng cấp đồng loạt. Đây là lý do thay đổi field name cần lộ trình tương thích ngược chứ không chỉ sửa code rồi deploy.

## 7. Java 17: ví dụ độc lập xuất JSON với field name cố định

Ví dụ sử dụng **Java Util Logging (JUL)** có sẵn trong JDK 17 để minh họa ý tưởng schema ổn định. Nó tạo hai event với:

- **Tên field không đổi:** `schemaVersion`, `timestamp`, `level`, `service`, `logger`, `eventName`, `requestId`, `orderId`, `durationMs`, `outcome`, `errorCode`.
- **Kiểu dữ liệu không đổi:** `durationMs` và `schemaVersion` là number; các ID và enum là string; `errorCode` là string hoặc null.
- **Thứ tự field cố định** để có output dễ kiểm tra, dù **thứ tự key trong object JSON thường không nên là điều kiện để query**.
- Thời điểm cố định trong demo để stdout tái lập. Ứng dụng thật cần thời gian event do clock thực hoặc framework cung cấp.

**Không nhầm ví dụ với API structured logging tích hợp của JUL:** bài dùng một `Formatter` tự viết để giải thích schema. Trong production nên chọn JSON encoder/structured logging library đã được kiểm chứng thay vì tự duy trì serializer thủ công.

### 7.1. Mã nguồn StableFieldNamesDemo.java

```java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class StableFieldNamesDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.checkout");

    // Record này mô tả giá trị nghiệp vụ, không tạo tên field động.
    private record EventFields(
            String requestId,
            String orderId,
            long durationMs,
            String outcome,
            String errorCode
    ) {}

    private static final class JsonFormatter extends Formatter {
        @Override
        public String format(LogRecord record) {
            EventFields event = (EventFields) record.getParameters()[0];
            StringBuilder out = new StringBuilder("{");

            numberField(out, "schemaVersion", 1);
            stringField(out, "timestamp", record.getInstant().toString());
            stringField(out, "level", record.getLevel().getName());
            stringField(out, "service", "checkout-service");
            stringField(out, "logger", record.getLoggerName());
            stringField(out, "eventName", record.getMessage());
            stringField(out, "requestId", event.requestId());
            stringField(out, "orderId", event.orderId());
            numberField(out, "durationMs", event.durationMs());
            stringField(out, "outcome", event.outcome());
            stringField(out, "errorCode", event.errorCode());

            return out.append("}\n").toString();
        }
    }

    private static void prefix(StringBuilder out, String name) {
        if (out.length() > 1) {
            out.append(',');
        }
        out.append('"').append(name).append("\":");
    }

    private static void stringField(
            StringBuilder out, String name, String value) {
        prefix(out, name);
        if (value == null) {
            out.append("null");
        } else {
            out.append('"').append(escapeJson(value)).append('"');
        }
    }

    private static void numberField(
            StringBuilder out, String name, long value) {
        prefix(out, name);
        out.append(value);
    }

    // Serializer đơn giản chỉ dành cho demo, không dùng cho production.
    private static String escapeJson(String value) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        return out.toString();
    }

    private static void emit(
            Level level,
            String eventName,
            Instant timestamp,
            EventFields fields
    ) {
        LogRecord record = new LogRecord(level, eventName);
        record.setInstant(timestamp);
        record.setLoggerName(LOG.getName());
        record.setParameters(new Object[]{fields});
        LOG.log(record);
    }

    public static void main(String[] args) throws Exception {
        LOG.setLevel(Level.INFO);
        LOG.setUseParentHandlers(false);

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        Handler handler = new StreamHandler(bytes, new JsonFormatter());
        handler.setLevel(Level.ALL);
        handler.setEncoding(StandardCharsets.UTF_8.name());
        LOG.addHandler(handler);

        try {
            Instant fixedTime = Instant.parse("2026-11-09T12:00:00Z");

            emit(Level.INFO, "checkout.completed", fixedTime,
                    new EventFields("req-17", "ord-42",
                            23, "success", null));

            emit(Level.WARNING, "checkout.rejected", fixedTime,
                    new EventFields("req-18", "ord-43",
                            7, "rejected", "INVALID_ORDER"));
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }

        System.out.print(bytes.toString(StandardCharsets.UTF_8));
    }
}
```

### 7.2. Biên dịch và chạy

Dùng JDK 17 trở lên:

```bash
javac StableFieldNamesDemo.java
java StableFieldNamesDemo
```

**Standard output chính xác** của chương trình, mỗi event là một JSON object trên một dòng:

```json
{"schemaVersion":1,"timestamp":"2026-11-09T12:00:00Z","level":"INFO","service":"checkout-service","logger":"demo.checkout","eventName":"checkout.completed","requestId":"req-17","orderId":"ord-42","durationMs":23,"outcome":"success","errorCode":null}
{"schemaVersion":1,"timestamp":"2026-11-09T12:00:00Z","level":"WARNING","service":"checkout-service","logger":"demo.checkout","eventName":"checkout.rejected","requestId":"req-18","orderId":"ord-43","durationMs":7,"outcome":"rejected","errorCode":"INVALID_ORDER"}
```

**Vì sao có thể tin kết quả này?**

1. `Logger` và `Handler` đều cho phép `INFO` và `WARNING`, còn `setUseParentHandlers(false)` tránh event bị đưa tới handler của logger cha.
2. `emit` dùng `LogRecord` với message là **event name**, timestamp cố định và `EventFields` chứa giá trị theo kiểu Java rõ ràng.
3. `JsonFormatter` quyết định **tên khóa tĩnh** bằng các lời gọi `stringField`/`numberField`; nó không xây tên khóa từ request ID hoặc nội dung động.
4. `EventFields.durationMs` là `long` nên JSON được viết dạng number, không bị trộn với chuỗi `"23ms"`.
5. `errorCode` có thể là `null` ở event thành công và string ở event bị từ chối; đây là lựa chọn schema được công bố rõ ràng.
6. `handler.close()` flush và đóng `StreamHandler` trước khi đọc nội dung trong `ByteArrayOutputStream`. Đầu ra cuối chỉ do `System.out.print` tạo nên không có timestamp máy hay tên thread bất định.
7. `escapeJson` bảo vệ một số ký tự JSON trong chuỗi. Đây là serializer **giản lược để giảng dạy**, chưa xử lý đầy đủ mọi nhu cầu Unicode/structured exception/schema validation, vì vậy không nên chép vào production làm thư viện JSON tổng quát.

**Bài học của ví dụ:** khi giá trị thay đổi từ `req-17` sang `req-18`, từ `success` sang `rejected`, **field name và type không đổi**. Điều này giúp mọi record đều có thể được truy vấn bằng cùng một câu query qua nhiều lần chạy.

## 8. Giữ field name ổn định với SLF4J, Logback và Log4j2

### 8.1. Chỉ dùng placeholder trong message chưa phải structured fields

```java
// Đoạn minh họa trong class có logger SLF4J.
LOG.info("orderId={} durationMs={}", orderId, durationMs);
```

Lời gọi này **không tự đảm bảo** JSON output có key `orderId` và `durationMs` riêng. Với nhiều backend, nó chỉ tạo một chuỗi message đã format, chẳng hạn `"orderId=ord-42 durationMs=23"`.

Muốn lưu các khóa thực, cần structured logging API hoặc context/key-value facility và một encoder/layout được cấu hình để xuất chúng. Có thể vẫn ghi message thân thiện, nhưng các field dùng cho máy phải hiện ra như thuộc tính riêng biệt.

### 8.2. SLF4J 2.x fluent key–value API

Trong SLF4J 2.x, có thể dùng fluent API để đính kèm key–value vào logging event:

```java
// Mã minh họa, cần SLF4J 2.x và backend tương thích.
LOG.atInfo()
   .addKeyValue("eventName", "checkout.completed")
   .addKeyValue("orderId", orderId)
   .addKeyValue("durationMs", durationMs)
   .log("Checkout completed");
```

Đây là **đoạn minh họa, không phải chương trình standalone**: biến `LOG`, `orderId`, `durationMs` và dependency phải có sẵn. API `addKeyValue(...)` làm field có tên rõ ràng ở mức event của SLF4J; **không đảm bảo backend mặc định tự in các field dưới dạng JSON**. Cần kiểm tra provider, pattern/encoder và ingestion pipeline thực tế.

Một điểm tốt của API này là tên field xuất hiện rõ tại nơi viết log, nhưng nếu các nhóm code dùng `"durationMs"`, `"latency"` và `"duration"` lẫn lộn thì API vẫn không tự giúp schema ổn định. Nên gom tên field vào hằng số/schema kiểm soát, hoặc helper API nội bộ có kiểu dữ liệu rõ.

### 8.3. MDC: khóa ổn định, giá trị theo context

SLF4J MDC hoặc Log4j2 ThreadContext thường dùng cho dữ liệu gắn với luồng thực thi như `requestId` và `traceId`:

```java
// Mã minh họa trong một method có biến LOG và requestId.
org.slf4j.MDC.put("requestId", requestId);
try {
    LOG.info("event=checkout.started");
} finally {
    org.slf4j.MDC.remove("requestId");
}
```

MDC giúp không phải truyền request ID thủ công vào mọi method, nhưng không tự đặt tên chuẩn. Nếu middleware viết `correlation_id` và controller truy vấn `requestId`, pipeline vẫn có hai field.

**Chú ý type:** MDC thường lưu **chuỗi**, nên nếu dùng MDC để chứa `durationMs`, giá trị có thể xuất ra JSON dạng string trừ khi encoder/schema chuyển đổi rõ ràng. Những số dùng cho aggregation nên được phát với kiểu dữ liệu thích hợp hoặc có bước mapping được kiểm chứng.

**Chú ý concurrency:** MDC/ThreadContext thường liên quan ngữ cảnh thread. Các tác vụ `CompletableFuture`, `ExecutorService`, reactive pipelines hoặc virtual threads không mặc nhiên nhận cùng context. Cần cơ chế propagation phù hợp và dọn field đúng scope để không lẫn ID của các request.

### 8.4. Logback và Log4j2 ở phía backend

- **Logback:** lựa chọn encoder/layout tương thích để xuất event, MDC và key–value thành field riêng. `PatternLayoutEncoder` tạo text pattern; không phải mọi cấu hình text đều là JSON có cấu trúc.
- **Log4j2:** có `ThreadContext` và nhiều layout. `JsonTemplateLayout` có thể được dùng khi module và template tương ứng đã được cài đúng phiên bản.
- **JUL:** `LogRecord`/`Formatter` có thể dùng để định dạng theo chuẩn nội bộ, nhưng ví dụ tự format JSON không nên thay encoder chuẩn khi vào production.
- **Collector:** có thể chuẩn hóa field name khi ingest. Nếu đã chọn tiêu chuẩn ở collector, ứng dụng và pipeline phải thỏa thuận rõ field nguồn/đích, tránh hai nơi cùng đổi tên hoặc mapping không nhất quán.

**Nguyên tắc chung:** chuẩn hóa schema ở **đầu phát** là lý tưởng cho tính nhất quán; mapping ở collector có thể hữu ích khi tích hợp thư viện/legacy service, nhưng phải có tài liệu, kiểm thử và giám sát để không che lỗi dữ liệu.

## 9. Đổi tên field và quản lý schema evolution

Thay đổi tên field là một **breaking change đối với consumer** đang sử dụng nó. Không nên làm chỉ bằng một refactor biến Java.

Giả sử hệ thống đang dùng:

```json
{"durationMs":120}
```

Dự án muốn chuyển sang schema mới dùng `processingTimeMs` để diễn đạt chính xác thời gian nghiệp vụ. Nếu chỉ đổi tên một lần:

```json
{"processingTimeMs":120}
```

dashboard cũ tìm `durationMs` có thể ngừng hiển thị. Cách quản lý thay đổi:

1. **Đánh giá tác động:** tìm các query, dashboard, alert, ETL jobs, downstream consumers, tài liệu và contract test đang dùng tên cũ.
2. **Định nghĩa tên mới:** xác nhận semantic, type, đơn vị và có thực sự cần đổi hay chỉ thay câu diễn giải.
3. **Công bố phiên bản:** ghi nhận thay đổi trong schema registry/tài liệu; có thể tăng `schemaVersion` theo chính sách.
4. **Giai đoạn tương thích:** khi thật sự cần, có thể phát **song song hai tên field** trong thời gian ngắn, hoặc mapping tên cũ sang mới ở collector. Gắn nhãn deprecated cho tên cũ.
5. **Cập nhật consumer:** dashboard, alert, ETL, test và service khác phải hiểu tên mới trước khi bỏ tên cũ.
6. **Quan sát thực tế:** đo tỷ lệ record còn dùng tên cũ, phát hiện producer chưa chuyển.
7. **Chỉ loại tên cũ sau khi hoàn tất chuyển đổi:** thống nhất thời hạn, cập nhật tài liệu/schema và xác nhận không còn consumer phụ thuộc.
8. **Xem xét dữ liệu lịch sử:** dữ liệu cũ vẫn mang tên cũ; dashboard muốn truy vấn xuyên giai đoạn cần alias/mapping hoặc query hỗ trợ cả hai.

### Ví dụ chiến lược dual-write có thời hạn

```json
{"schemaVersion":2,"durationMs":120,"processingTimeMs":120}
```

Đây là **mẫu chuyển tiếp**, không nên duy trì hai alias mãi mãi. Nó làm record lớn hơn và có nguy cơ hai field khác nhau nếu producer tính không nhất quán. Nếu chọn dual-write, phải xác định **một nguồn giá trị duy nhất** để sinh cả hai field và có test xác nhận bằng nhau.

Tùy yêu cầu hạ tầng, có thể **không** dual-write mà chuyển đổi tại collector hoặc để consumer dùng version-aware query. Cách nào cũng cần kế hoạch tương thích; không tự ý xóa field cũ khi còn dùng.

### Đổi ý nghĩa mà không đổi tên còn nguy hiểm hơn

Nếu `durationMs` trước đây đo toàn bộ request nhưng nay chỉ đo database time, dashboard có thể tiếp tục hiển thị bình thường nhưng **số liệu trở nên sai về bản chất**. Khi định nghĩa thay đổi, hãy chọn field mới có semantic rõ (ví dụ `dbDurationMs`) hoặc version schema và cập nhật consumer có kiểm soát.

## 10. Thiết kế field dictionary và ownership

Đối với nhiều team, tạo một **field dictionary** ngắn, được review như code. Một mục nên chứa:

| Thuộc tính | Ví dụ cho `durationMs` |
| --- | --- |
| Canonical name | `durationMs` |
| JSON type | Number, giá trị không âm theo contract |
| Unit | Milliseconds |
| Semantic | Khoảng thời gian từ khi bắt đầu xử lý checkout đến khi có kết quả cuối |
| Required/optional | Có với `checkout.completed` hoặc `checkout.failed` nếu đã đo được |
| Missing behavior | Vắng mặt khi không có phép đo; không dùng `0` để thay missing |
| Source | Application timer, không lấy từ một chuỗi người dùng nhập |
| Privacy classification | Không chứa dữ liệu cá nhân trực tiếp |
| Consumers | Latency dashboard, alert, điều tra sự cố |
| Owner | Nhóm sở hữu schema sự kiện |
| Introduced/deprecated | Ghi release/schema version thay đổi |

Với `errorCode`, nên có danh mục code ổn định. Với `requestId`, nên xác định định dạng, độ dài, retention và quyền truy cập. Với `timestamp`, xác định timezone, nguồn clock và chính sách khi dữ liệu đến trễ.

**Quyền sở hữu schema** quan trọng không kém convention: nếu không có ai review thay đổi, mỗi module sẽ tạo cách đặt tên riêng. Có thể cung cấp constant/helper hoặc typed event builder để giảm lỗi đánh máy, nhưng không nên làm abstraction quá phức tạp.

## 11. Đặt tên thống nhất và tránh xung đột khi tích hợp nhiều nguồn

### 11.1. Tránh đè lên reserved fields

Backend/collector có thể tự cung cấp field như thời điểm, severity, resource/service, logger, exception. Nếu ứng dụng cũng tạo field `timestamp` với ý nghĩa khác hoặc dùng `level` để chỉ cấp độ thành viên, ingestion có thể ghi đè hoặc nhập nhằng.

Nếu field cấp ứng dụng thật sự là `customerLevel`, đừng đặt là `level` khi `level` đã dành cho severity log. Dùng namespace hoặc tên đầy đủ theo schema đã chọn.

### 11.2. Dấu chấm trong field name không luôn là object lồng nhau

Hai cấu trúc sau **không phải một biểu diễn JSON giống hệt nhau**:

```json
{"http.response.status_code":200}
{"http":{"response":{"status_code":200}}}
```

Một số indexer/query engine có thể coi dấu chấm như đường dẫn nested hoặc xử lý khác nhau. Không giả định collector tự chuyển giữa hai dạng. Nếu tổ chức đã dùng chuẩn tên có dấu chấm, hãy quyết định rõ dạng JSON nguồn, mapping và cú pháp truy vấn downstream.

### 11.3. Không trộn field nguồn với field chuẩn hóa vô điều kiện

Một service có thể phát `requestId`, còn pipeline chuẩn mong `request.id`. Có thể chuyển đổi ở collector, nhưng cần:

- Một bản đồ mapping được quản lý phiên bản.
- Quy tắc khi cả field nguồn lẫn field đích đều tồn tại.
- Kiểm tra kiểu dữ liệu và hành vi với null/missing.
- Khả năng đối chiếu event đầu vào với event sau ingest khi điều tra lỗi.
- Contract test để phát hiện khi service đổi field nguồn mà pipeline chưa cập nhật.

Đây là cách hỗ trợ legacy migration; không nên coi mapping là lý do cho phép mỗi service tiếp tục tạo tên tùy ý.

## 12. Kiểm thử tính ổn định của schema

Đừng chỉ kiểm thử rằng ứng dụng đã gọi `logger.info(...)`. Với structured logging, **output sau encoder/formatter** mới là dữ liệu consumer thực sự nhận.

### Các nhóm kiểm thử nên có

1. **Schema key test:** event thuộc loại `checkout.completed` có các key bắt buộc đã công bố.
2. **Type test:** `durationMs` là number; `errorCode` đúng string/null; `schemaVersion` là integer.
3. **Value test:** `outcome` nằm trong tập giá trị được phép; `eventName` là tên ổn định.
4. **Null/missing test:** event thành công có xử lý `errorCode` đúng policy; job nền thiếu `requestId` không bị gán ID giả.
5. **Timestamp test:** timestamp có timezone, có thể parse theo định dạng đã cam kết.
6. **Escaping test:** dấu ngoặc kép, Unicode, xuống dòng và ký tự điều khiển không làm JSON sai cấu trúc hoặc tạo log injection.
7. **Throwable test:** khi lỗi, exception type/stack trace/cause được xuất theo contract mà không lộ bí mật.
8. **Cross-service test:** hai service cùng dùng `traceId` với format/semantic nhất quán.
9. **Compatibility test:** dashboard/query cũ còn hoạt động trong giai đoạn schema migration.
10. **Deployment test:** thực sự chạy trên backend/encoder production, vì cấu hình local/test có thể khác.

### Ví dụ quy tắc kiểm tra kiểu đơn giản

Nếu đã parse một JSON event thành map, có thể kiểm tra:

```text
assert keys contain {"timestamp", "level", "service", "eventName"}
assert type(durationMs) == number
assert type(requestId) == string when requestId exists
assert outcome in {"success", "failure", "rejected"}
assert schemaVersion == expectedVersion
```

Đây là **pseudocode cho contract test**, không phải Java executable. Với Java, dùng JSON parser như Jackson/Jakarta JSON hoặc thư viện phù hợp để đọc object và assert type/key, không kiểm tra bằng cách so chuỗi JSON tuyệt đối nếu thứ tự khóa không được bảo đảm bởi contract.

### Golden event mẫu

Lưu các bản ghi ví dụ đã được rà soát cho từng `eventName`, gồm success, rejected, failure và missing-optional-field. Mỗi lần đổi encoder/schema, so sánh các key, type, enum và semantic; chỉ thay snapshot khi đã review tác động xuống consumer.

## 13. Hiệu năng và bảo mật của field ổn định

### 13.1. Cardinality và chi phí index

Tên field ổn định giúp giảm **số lượng tên field mới** không kiểm soát, nhưng không tự giải quyết **giá trị cardinality cao**. Ví dụ `requestId` có thể có hàng triệu giá trị: đặt vào value là đúng cấu trúc, nhưng index mọi ID vẫn tiêu tốn tài nguyên. Phải cân nhắc chính sách indexing và retention theo nền tảng.

Tránh phát trực tiếp một object/map tự do từ request thành hàng nghìn tên field động. Khi cần ghi metadata linh hoạt, xem xét giới hạn allowlist, kích thước, số phần tử và cách lưu phù hợp (nested object có schema, field chứa payload an toàn, hoặc bỏ phần không cần thiết).

### 13.2. Dữ liệu nhạy cảm

Các field như `userId`, `email`, `clientIp`, `sessionId` và `authorization` có thể là dữ liệu cá nhân hoặc bí mật. Tên field ổn định giúp áp dụng chính sách masking dễ hơn, nhưng **không biến giá trị nhạy cảm thành an toàn**.

Không ghi mật khẩu, access token, session cookie, private key hoặc toàn bộ request body không cần thiết. Đánh giá nhu cầu lưu, mã hóa ở nơi lưu, quyền truy cập, thời gian retention và khả năng truy cập của bên thứ ba. Nếu phải log định danh cá nhân, cân nhắc pseudonymization/hash có quản lý theo chính sách phù hợp; không tự coi hashing đơn giản là ẩn danh tuyệt đối.

### 13.3. Giới hạn kích thước và dữ liệu không tin cậy

String fields như `errorMessage` hoặc user-agent có thể chứa ký tự xuống dòng, ký tự điều khiển hoặc payload lớn. Sử dụng structured encoder có JSON escaping đúng, giới hạn độ dài field, và không dùng dữ liệu đầu vào làm tên key. Một quy ước tên ổn định không thay thế validation nội dung.

### 13.4. Dữ liệu và log không luôn là nguồn sự thật nghiệp vụ

Log có thể bị sampling, filtering, mất khi queue async đầy, lỗi I/O hoặc retention. Không dùng log ứng dụng thông thường làm cơ sở duy nhất để xác nhận một giao dịch tài chính đã được lưu bền. Với nhu cầu audit có tính bắt buộc, phải có cơ chế lưu trữ và xác nhận riêng.

## 14. Các lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `requestId` / `request_id` / `rid` trộn lẫn | Query mất liên kết request giữa các nguồn. | Chọn canonical name hoặc chuẩn hóa có contract. |
| `durationMs` có lúc là number, lúc là string | Aggregation và mapping có thể lỗi. | Định nghĩa một JSON type; kiểm tra tại encoder và bằng schema test. |
| `durationMs` đổi từ ms sang µs nhưng giữ tên | Dashboard cho số liệu sai nghiêm trọng. | Đổi tên/semantic có versioning, cập nhật consumer. |
| `outcome="ok"` và `outcome="success"` cùng nghĩa | Alert và metric phân tán nhóm sai. | Định nghĩa enum ổn định; mapping khi migration. |
| Dùng `user_42` làm tên khóa | Field explosion, schema/index mất kiểm soát. | Dùng `userId` làm key, `"42"` làm value, xét privacy. |
| Đặt field `id` chung cho mọi đối tượng | Không rõ định danh thuộc entity nào. | `orderId`/`jobId`/`requestId` theo semantic. |
| Parse tất cả dữ liệu từ `message` | Regex dễ gãy khi đổi text. | Phát structured key–value fields thực sự. |
| Đổi tên field trong code, không nâng dashboard | Consumer âm thầm bỏ dữ liệu. | Migration và contract test, dual-write/mapping tạm thời. |
| Đổi tên field nhưng không cập nhật collector | Event bị map sai hoặc field thiếu. | Quản lý version và test end-to-end. |
| Coi `null` bằng `0` | Số liệu độ trễ và lỗi bị sai. | Xác định null/missing/zero rõ ràng. |
| MDC lưu số thành string nhưng index mong number | Type mismatch hoặc ép kiểu không mong đợi. | Phát typed field hoặc mapping nhất quán. |
| Ghi `traceId` nhưng context không truyền qua async task | Khó truy vết, liên kết sai. | Propagate context và dọn đúng scope. |
| Đặt tên theo cấu trúc object Java nội bộ | Refactor class làm đổi schema log. | Tách hợp đồng log schema khỏi tên field model/DTO. |
| Giữ field nhạy cảm vô hạn | Rủi ro dữ liệu và compliance. | Minimize, access control, retention, redaction. |
| Ghi nhiều field alias mãi mãi | Log phình và query phức tạp. | Có giai đoạn deprecate, thời hạn gỡ và owner rõ. |

## 15. Checklist review trước khi thêm field mới

- [ ] Tên này đã có trong field dictionary hoặc chuẩn dữ liệu đang dùng chưa?
- [ ] Tên có mô tả đúng semantic, không mơ hồ và không xung đột field hệ thống?
- [ ] Naming convention có nhất quán với các service còn lại không?
- [ ] Type JSON đã rõ, ví dụ number thay vì số lưu dưới dạng string?
- [ ] Nếu có đơn vị, tên/contract có nêu millisecond, byte, tỷ lệ hay epoch?
- [ ] Có thể thiếu field không; absent, null, empty string và zero được xử lý thế nào?
- [ ] Nếu là enum, danh sách giá trị ổn định và quy tắc thêm giá trị mới đã được định nghĩa?
- [ ] Dữ liệu có thể là bí mật hoặc dữ liệu cá nhân không; có thực sự cần log?
- [ ] Field có cardinality cao hoặc key động gây áp lực index không?
- [ ] Field này được phát ở code hay chỉ in vào message; encoder có xuất thành trường riêng không?
- [ ] Nếu rename, migration plan, schemaVersion, dashboard và query cũ đã được đánh giá?
- [ ] Có contract test và kiểm chứng trên backend/collector runtime thật không?
- [ ] Team nào sở hữu định nghĩa và chấp nhận thay đổi field này?

## 16. Tự kiểm tra kiến thức

1. Hai service ghi `requestId` và `request_id` có thể gây hỏng những loại query nào? Đổi layout có tự sửa không?
2. Vì sao `durationMs:23` và `durationMs:"23ms"` không tương thích?
3. Khi một field không áp dụng cho event, chọn absent hay null như thế nào để consumer hiểu đúng?
4. `requestId`, `traceId` và `spanId` khác nhau ở phạm vi ngữ nghĩa nào?
5. Vì sao không nên đặt key `"order_" + orderId` trong một structured log event?
6. Dùng SLF4J `LOG.info("durationMs={}", value)` có đảm bảo JSON field `durationMs` không?
7. Khi đổi `durationMs` thành `processingTimeMs`, cần đánh giá những consumer nào trước khi deploy?
8. Dual-write hai field trong thời kỳ chuyển đổi có ưu điểm và rủi ro gì?
9. Field name ổn định có giải quyết được việc log chứa token, dữ liệu riêng tư hay chi phí index không?
10. Trong Java 17 demo, vì sao formatter xuất `durationMs` là number và giữ `errorCode` theo cùng contract dù giá trị có thể null?

**Kết luận:** Trong structured logging, **field name là một giao diện dữ liệu có người tiêu thụ**, không chỉ là chuỗi tiện viết trong code. Hãy chọn tên chuẩn, định nghĩa type/đơn vị/semantic, giữ nhất quán giữa các service và phiên bản, quản lý rename như thay đổi API, kiểm tra output thực tế và bảo vệ dữ liệu nhạy cảm. Điều đó giúp log có thể được truy vấn, liên kết, tổng hợp và cảnh báo đáng tin cậy theo thời gian.