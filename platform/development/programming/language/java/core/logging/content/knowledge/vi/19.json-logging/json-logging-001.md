# JSON log là gì? Structured logging trong Java

## 1. Khái niệm JSON log

**JSON log** là bản ghi nhật ký (log event) được biểu diễn dưới dạng **JSON (JavaScript Object Notation)**. Thay vì chỉ có một dòng văn bản tự do, mỗi sự kiện được thể hiện bằng một đối tượng gồm các **trường có tên**, có thể là chuỗi, số, boolean, null, object hoặc array.

Ví dụ log text truyền thống:

```text
2026-11-09T08:15:03Z INFO OrderService - Accepted order ORD-7 from channel WEB
```

Cùng sự kiện biểu diễn bằng JSON:

```json
{
  "@timestamp": "2026-11-09T08:15:03Z",
  "level": "INFO",
  "logger": "com.example.orders.OrderService",
  "message": "Order accepted",
  "event": "order_accepted",
  "orderId": "ORD-7",
  "channel": "WEB"
}
```

Ở cách thứ hai, `orderId` và `channel` không phải các từ phải “đoán” từ message; chúng là trường riêng mà hệ thống thu thập có thể truy vấn như `orderId == "ORD-7"`.

**JSON chỉ là định dạng dữ liệu**, không phải một logging framework, mức log hay cam kết lưu trữ. Để có log JSON hữu ích, còn cần thiết kế schema, cách đưa dữ liệu sự kiện vào record, encoder/formatter, nơi ghi và hệ thống thu thập.

Những thuật ngữ dễ gặp:

- **Log event:** một sự kiện được ứng dụng phát ra, ví dụ một lần tạo đơn hàng hoặc một lỗi.
- **Structured logging:** tổ chức dữ liệu sự kiện thành các trường có tên và kiểu rõ ràng.
- **JSON logging:** xuất dữ liệu log dưới dạng JSON; thường là một cách triển khai structured logging.
- **JSON Lines / NDJSON:** nhiều đối tượng JSON độc lập, mỗi đối tượng trên **một dòng vật lý** trong file hoặc luồng stdout.
- **Encoder / Formatter / Layout:** thành phần chuyển event trong bộ nhớ thành biểu diễn đầu ra.
- **Collector / shipper:** công cụ thu nhận, vận chuyển, phân tích, lưu và lập chỉ mục log.

Không phải mọi câu chứa ngoặc nhọn là structured logging. Giá trị thật đến từ việc giữ các field nhất quán từ lúc ứng dụng phát sự kiện đến khi truy vấn.

## 2. Vì sao JSON log hữu ích?

### 2.1. Truy vấn theo trường thay vì chỉ tìm chuỗi

Với log text:

```text
INFO order accepted ORD-7 channel=WEB
INFO order accepted ORD-8 channel=MOBILE
```

Muốn tìm riêng đơn `ORD-7`, công cụ có thể phải dùng regex/substring và chịu rủi ro pattern thay đổi. Với JSON:

```json
{"level":"INFO","event":"order_accepted","orderId":"ORD-7","channel":"WEB"}
{"level":"INFO","event":"order_accepted","orderId":"ORD-8","channel":"MOBILE"}
```

Collector có thể lọc theo trường `event`, `orderId` hoặc `channel`, nếu pipeline đã parse và lập chỉ mục chúng.

### 2.2. Giữ kiểu dữ liệu

Một JSON event có thể chứa:

```json
{
  "event": "payment_attempt",
  "attempt": 2,
  "durationMs": 145,
  "success": false,
  "retryable": true,
  "amount": 125000.50,
  "tags": ["checkout", "retry"],
  "context": {
    "region": "ap-southeast",
    "source": "web"
  }
}
```

`attempt` và `durationMs` là **number**, `success` là **boolean**, `tags` là **array**, `context` là **object**. Nếu mọi thứ đều được ghép thành một message string, các kiểu này có thể bị mất hoặc phải tái tạo bằng parser.

Không phải vì JSON cho phép số mà mọi mã định danh đều nên là number. `orderId`, `traceId`, mã bưu điện và những chuỗi có số 0 đầu cần giữ dưới dạng **string**.

### 2.3. Giúp nhiều service chia sẻ một schema

Nếu mọi service đều đưa `level`, `service`, `traceId`, `event`, `message` theo cùng quy ước, việc tìm kiếm sự cố xuyên dịch vụ dễ hơn. Nhưng **không có một bộ key duy nhất bắt buộc cho mọi hệ thống JSON logging**. Một số nền tảng dùng `timestamp`, nơi khác dùng `@timestamp`; OpenTelemetry có thể dùng các tên như `Timestamp`, `SeverityText` ở data model riêng.

Khi triển khai, hãy tuân theo **schema của tổ chức hoặc collector**, không tự giả định mọi backend xuất những field giống nhau.

## 3. JSON Lines: mỗi log event nên thành một dòng

Khi ghi một dòng JSON độc lập cho mỗi event, đầu ra thường được gọi là **JSON Lines** hoặc **NDJSON**:

```json
{"timestamp":"2026-11-09T08:15:03Z","level":"INFO","event":"order_accepted","orderId":"ORD-7"}
{"timestamp":"2026-11-09T08:15:04Z","level":"WARN","event":"stock_low","sku":"SKU-2"}
{"timestamp":"2026-11-09T08:15:05Z","level":"ERROR","event":"save_failed","orderId":"ORD-8"}
```

Ba dòng trên **không tạo thành một JSON document duy nhất** nếu ghép nguyên xi; mỗi dòng là **một JSON object độc lập**. Đó là điều nhiều agent/log collector trông đợi.

Ngược lại, một bản ghi được in đẹp trên nhiều dòng:

```json
{
  "timestamp": "2026-11-09T08:15:03Z",
  "level": "INFO",
  "event": "order_accepted"
}
```

vẫn là JSON hợp lệ, nhưng nếu collector mặc định coi **mỗi newline là một sự kiện**, nó sẽ đọc nhầm thành ba dòng log khác nhau. Vì vậy:

1. Ghi **một JSON object hoàn chỉnh trên một dòng** cho mỗi event khi dùng pipeline dòng.
2. Phân tách các event bằng ký tự newline sau JSON object.
3. Escape newline **bên trong message** dưới dạng `\n` trong chuỗi JSON, không để message tạo dòng vật lý ngoài object.
4. Không in banner, text diagnostics hay exception stack trace tự do xen kẽ vào cùng stream JSON nếu downstream yêu cầu mọi dòng đều parse được.
5. Xác định charset thống nhất, thường là UTF-8.

**JSON Lines không mặc nhiên bảo đảm thứ tự toàn cục giữa nhiều thread/process hoặc delivery đúng một lần.** Nó chỉ quy định cách biểu diễn từng event trong luồng.

## 4. Một schema JSON log cơ bản nên có gì?

Không phải mọi ứng dụng cần tất cả các trường, nhưng nên định nghĩa rõ một tập field cốt lõi.

| Trường gợi ý | Kiểu | Ví dụ | Ý nghĩa |
|---|---|---|---|
| `timestamp` hoặc `@timestamp` | string ISO 8601 | `2026-11-09T08:15:03.125Z` | Thời điểm sự kiện |
| `level` hoặc `severityText` | string | `INFO`, `WARN`, `ERROR` | Mức độ ưu tiên |
| `logger` | string | `com.example.OrderService` | Nguồn logic phát log |
| `service` hoặc `service.name` | string | `orders-api` | Dịch vụ tạo event |
| `environment` | string | `prod` | Môi trường triển khai |
| `event` hoặc `event.name` | string | `order_accepted` | Tên sự kiện ổn định |
| `message` | string | `Order accepted` | Mô tả ngắn cho con người |
| `traceId` / `spanId` | string | `trace-42` | Tương quan với distributed trace |
| `requestId` | string | `req-42` | Liên kết các log của một request |
| `orderId` / `jobId` | string | `ORD-7` | Định danh nghiệp vụ khi được phép ghi |
| `durationMs` | number | `145` | Thời lượng, đơn vị được nêu rõ |
| `error.type` / `exception.type` | string | `java.io.IOException` | Phân loại lỗi |
| `stackTrace` | string | `...` | Dấu vết lỗi, cần giới hạn dữ liệu |
| `schemaVersion` | string/integer | `"1"` | Phiên bản schema khi cần ổn định tương thích |

**Lưu ý về timestamp:** JSON không có kiểu datetime riêng. Một timestamp dạng ISO 8601 thực chất là chuỗi, trừ khi schema chọn một number epoch milliseconds/nanoseconds. Không tự trộn `seconds`, `milliseconds` và `nanoseconds` trong một trường mà không có quy định rõ.

**Lưu ý về số đo:** field `durationMs=145` dễ hiểu hơn `duration=145` vì đã rõ đơn vị. Khi dùng tiêu chuẩn observability chính thức, hãy tuân theo tên và đơn vị do tiêu chuẩn đó quy định.

### 4.1. Dùng tên event ổn định

Nên dùng:

```json
{"event":"order_accepted","orderId":"ORD-7","message":"Order accepted"}
```

Thay vì thay đổi message liên tục và phải suy ra sự kiện bằng cách parse:

```text
Accepted #ORD-7!
Order accepted: ORD-7
Completed receiving order ORD-7
```

`event` nên có bộ giá trị tương đối ổn định. `message` có thể được chỉnh cách diễn đạt cho con người mà không phá dashboard đếm sự kiện theo `event`.

### 4.2. Tránh field name trùng ý nghĩa

Nếu service A dùng `request_id`, B dùng `requestId` và C dùng `correlationId` cho cùng một khái niệm, dashboard phải hỗ trợ nhiều alias. Hãy chuẩn hóa trước. Có thể dùng camelCase, snake_case hoặc dotted keys, nhưng phải chọn một cách và theo hợp đồng schema.

Khi thay schema, cần chiến lược backward compatibility: thêm field mới dễ hơn thay nghĩa một field đang được alert/index/query sử dụng.

## 5. Phân biệt “message là JSON” với “event là JSON có cấu trúc”

Hai log sau **không tương đương**:

```json
{
  "level": "INFO",
  "message": "{\"orderId\":\"ORD-7\",\"event\":\"order_accepted\"}"
}
```

và:

```json
{
  "level": "INFO",
  "message": "Order accepted",
  "event": "order_accepted",
  "orderId": "ORD-7"
}
```

Ở trường hợp đầu, `orderId` chỉ tồn tại trong **chuỗi message**, tức JSON lồng dưới dạng text. Nếu collector chỉ parse object ngoài, `orderId` **không phải field độc lập**. Muốn truy vấn riêng có thể phải parse JSON lần thứ hai hoặc thiết kế encoder phù hợp.

Ở trường hợp thứ hai, `event` và `orderId` đã là field riêng. Đây là cách thuận tiện hơn khi cần chỉ mục/tìm kiếm, miễn là hệ thống nhận đúng kiểu dữ liệu và schema.

Tương tự, code SLF4J:

```java
LOG.info("orderId={} event={}", orderId, "order_accepted");
```

là **message parameterization**, không tự có nghĩa backend sẽ xuất `orderId` và `event` thành hai trường JSON. Backend có thể chỉ tạo field `message` với nội dung `"orderId=ORD-7 event=order_accepted"`. Muốn có structured fields, phải dùng API encoder/structured arguments/MDC hoặc event model phù hợp.

## 6. Vì sao không nên tự ghép JSON bằng chuỗi?

Một cách viết nguy hiểm:

```java
// Sai: đoạn minh họa, có thể tạo JSON không hợp lệ.
String line = "{\"message\":\"" + userInput + "\"}";
```

Nếu `userInput` chứa `"`, `\`, ký tự xuống dòng hoặc control characters, kết quả có thể không còn là JSON hợp lệ hoặc gây log injection. Ví dụ input có thể chứa dòng giả dạng:

```text
Hello
ERROR user=admin action=approved
```

Khi tự nối vào một chuỗi JSON, newline không được escape đúng có thể phá bố cục và tạo sự kiện giả nếu collector chia theo dòng.

**Nên sử dụng JSON serializer/encoder được bảo trì và kiểm thử**, chẳng hạn Jackson trong Java hoặc JSON encoder của logging backend. Serializer xử lý escaping đúng quy tắc JSON; ứng dụng vẫn cần kiểm soát dữ liệu nhạy cảm, giới hạn kích thước, kiểu dữ liệu và schema.

Đặc biệt, không dùng cách `message.replace("\"", "\\\"")` rồi coi là đã đủ: vẫn còn newline, control characters, surrogate pairs và nhiều trường hợp khác cần được xử lý.

JSON escaping **không đồng nghĩa** với masking dữ liệu nhạy cảm. Serializer có thể bảo đảm chuỗi đúng cú pháp JSON nhưng vẫn ghi nguyên access token hoặc mật khẩu nếu ứng dụng đưa chúng vào record.

## 7. JSON log trong Java được tạo ở lớp nào?

Với ứng dụng dùng SLF4J + backend:

```text
Java business code
   |
   | LOG.info("event=...", ...)
   v
SLF4J facade / logging API
   |
   v
Provider/backend: Logback hoặc Log4j 2
   |
   +-- Logger level/filter
   +-- MDC / event attributes
   +-- JSON encoder/layout
   |
   v
Console/File/Async appender
   |
   v
Collector → Parse → Index → Search/Dashboard
```

Sơ đồ rút gọn: tùy backend, việc snapshot dữ liệu, layout, encoder và async scheduling có thể diễn ra ở các thứ tự cụ thể khác nhau.

**JSON logging không yêu cầu đổi API của mã nghiệp vụ trong mọi trường hợp.** Nếu backend đã nhận SLF4J events, nhiều ứng dụng có thể chuyển pattern text thành JSON encoder/formatter bằng cấu hình. Nhưng muốn bổ sung `orderId`/`traceId` thành field riêng, ứng dụng vẫn cần phát dữ liệu theo cơ chế encoder/backend hiểu.

### 7.1. JUL

`java.util.logging` của JDK có `LogRecord`, `Handler`, `Formatter`. JUL chuẩn không có một JSON formatter tổng quát tích hợp sẵn để tự biến mọi custom field thành JSON. Có thể:

- Viết `Formatter` và dùng JSON serializer đáng tin cậy.
- Dùng thư viện formatter/handler hỗ trợ JSON.
- Chuyển log JUL qua bridge về backend có JSON encoder, nếu phù hợp topology.

`LogRecord` có level, timestamp, logger name, message, parameters, thrown và metadata khác; nó **không có sẵn MDC map tiêu chuẩn giống các API contextual logging chuyên dụng**.

### 7.2. SLF4J + Logback

SLF4J là facade, Logback là backend. Cú pháp `{}` chỉ giúp format tham số message; để có JSON thực sự, Logback cần **encoder/layout JSON tương thích** (tích hợp tùy version hoặc thư viện bổ sung) và cách nhận structured event fields.

Logback có thể dùng MDC với pattern hoặc encoder thích hợp, nhưng **MDC không tự tạo request ID/trace ID**. Ứng dụng hoặc tracing instrumentation phải cung cấp context.

### 7.3. SLF4J + Log4j 2

Khi dùng Log4j 2 làm backend, hệ thống có các layout/encoder và cơ chế context/structured data riêng theo version. JSON layout cần được cấu hình đúng; không chỉ thay tên file thành `.json` hoặc thay message template thành chuỗi có dấu ngoặc nhọn.

Nếu mã ứng dụng gọi SLF4J 2.x, provider tích hợp với Log4j 2 phải tương thích. Tránh đồng thời nhiều SLF4J providers và tránh bridge hai chiều Log4j 2 ↔ SLF4J tạo vòng chuyển tiếp.

### 7.4. Framework và collector

Spring Boot có thể đã quản lý backend/logging system mặc định. Khi chọn output JSON, nên kiểm tra version của Boot/backend, dependency tree và cấu hình thực tế. Cấu hình `logback-spring.xml` thuộc tích hợp Spring Boot với Logback, không dùng nguyên cho JUL hoặc Log4j 2.

Collector cần được cấu hình để **parse JSON từ đúng stream/path**, không phải cứ có chuỗi JSON là tự động lập chỉ mục mọi trường.

## 8. Ví dụ Java 17 + Maven chạy được: tạo JSON log qua JUL Formatter và Jackson

Ví dụ sau sử dụng:

- **Java 17** và **Maven**.
- `java.util.logging.Logger`, `LogRecord`, `ConsoleHandler`, `Formatter` của JDK.
- Thư viện **Jackson** để chuyển event thành JSON hợp lệ thay vì tự nối chuỗi.
- Một kiểu `JsonEvent` minh họa chứa **attributes có cấu trúc**, để phân biệt field thật với chuỗi message.

Đầu ra là **hai dòng JSON độc lập trên stderr**. Timestamps được đặt cố định trong demo để người học đối chiếu chính xác; trong ứng dụng thật, thời điểm event thường được framework/LogRecord lấy từ đồng hồ hệ thống.

**Đây là ví dụ giáo dục**, không đề xuất mỗi ứng dụng production tự viết lại toàn bộ logging backend. Trong production, ưu tiên JSON encoder/layout được hỗ trợ chính thức bởi backend, chính sách schema và quy trình kiểm thử phù hợp.

### 8.1. Cấu trúc thư mục

```text
json-log-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── logging/
                        └── JsonLogDemo.java
```

### 8.2. File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>json-log-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.2</version>
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
                <configuration>
                    <mainClass>com.example.logging.JsonLogDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Phiên bản dependency ở đây là **giá trị cố định cho ví dụ**, không phải tuyên bố phiên bản mới nhất hay phù hợp cho mọi chính sách bảo mật. Khi áp dụng thật, xem dependency management/BOM, supported JDK, security advisories và chính sách update của dự án.

Jackson `ObjectMapper` chuyển map có thứ tự thành chuỗi JSON; mã Java sẽ thêm newline để tạo JSON Lines. Không dùng Gson/Jackson như “logging backend”: chúng chỉ là **thư viện serialization**.

### 8.3. File `src/main/java/com/example/logging/JsonLogDemo.java`

```java
package com.example.logging;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class JsonLogDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.OrderService");

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new JsonLineFormatter());
        LOG.addHandler(console);

        try {
            emit(Level.INFO,
                    Instant.parse("2026-11-09T08:15:03Z"),
                    "Order accepted",
                    "order_accepted", "orderId", "ORD-7");

            emit(Level.WARNING,
                    Instant.parse("2026-11-09T08:15:04Z"),
                    "Stock is low",
                    "stock_low", "sku", "SKU-2");
        } finally {
            LOG.removeHandler(console);
            console.flush();
            console.close();
        }
    }

    private static void emit(
            Level level,
            Instant at,
            String message,
            String eventName,
            String idKey,
            String idValue) {

        JsonEvent event = new JsonEvent(
                level, message, eventName, idKey, idValue);
        event.setLoggerName(LOG.getName());
        event.setInstant(at);
        LOG.log(event);
    }

    private static final class JsonEvent extends LogRecord {
        private static final long serialVersionUID = 1L;
        private final Map<String, Object> attributes;

        private JsonEvent(
                Level level,
                String message,
                String eventName,
                String idKey,
                String idValue) {
            super(level, message);

            Map<String, Object> values = new LinkedHashMap<>();
            values.put("event", eventName);
            values.put(idKey, idValue);
            attributes = Collections.unmodifiableMap(values);
        }

        private Map<String, Object> attributes() {
            return attributes;
        }
    }

    private static final class JsonLineFormatter extends Formatter {
        private final ObjectMapper json = new ObjectMapper();

        @Override
        public String format(LogRecord record) {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("@timestamp", record.getInstant().toString());
            payload.put("level", normalizeLevel(record.getLevel()));
            payload.put("logger", record.getLoggerName());
            payload.put("message", formatMessage(record));

            if (record instanceof JsonEvent event) {
                payload.put("attributes", event.attributes());
            }

            try {
                return json.writeValueAsString(payload) + "\n";
            } catch (JsonProcessingException error) {
                throw new IllegalStateException(
                        "Could not encode JSON log", error);
            }
        }

        private static String normalizeLevel(Level level) {
            if (level == Level.SEVERE) return "ERROR";
            if (level == Level.WARNING) return "WARN";
            return level.getName();
        }
    }
}
```

### 8.4. Biên dịch và chạy

Đặt tệp đúng package/path, mở terminal trong thư mục `json-log-demo` có `pom.xml`, sau đó chạy (yêu cầu JDK 17+, Maven và quyền tải dependency):

```bash
mvn -q compile exec:java
```

Hai dòng **do `ConsoleHandler` phát trên stderr** sẽ là:

```json
{"@timestamp":"2026-11-09T08:15:03Z","level":"INFO","logger":"demo.OrderService","message":"Order accepted","attributes":{"event":"order_accepted","orderId":"ORD-7"}}
{"@timestamp":"2026-11-09T08:15:04Z","level":"WARN","logger":"demo.OrderService","message":"Stock is low","attributes":{"event":"stock_low","sku":"SKU-2"}}
```

Chương trình không tự ghi stdout. Maven có thể có thông báo riêng về build/plugin nếu môi trường khác; hai dòng trên là **output của logging handler trong demo**, không phải toàn bộ mọi thông báo của công cụ chạy.

### 8.5. Giải thích kỹ từng phần

1. `JsonEvent` là một lớp ví dụ mở rộng `LogRecord` và giữ `attributes` tách biệt với `message`. `LinkedHashMap` giữ thứ tự field trong ví dụ; `Collections.unmodifiableMap` tránh việc sửa trực tiếp dữ liệu đó sau khi tạo event.
2. `LOG.setUseParentHandlers(false)` tránh JUL chuyển cùng record lên handler cha gây trùng output.
3. `LOG.setLevel(Level.ALL)` và `console.setLevel(Level.ALL)` cho phép cả INFO/WARNING trong demo.
4. `record.setInstant(...)` tạo timestamp cố định để stdout/stderr kiểm chứng được; ứng dụng thật không nên hardcode thời gian sự kiện.
5. `Formatter.format(...)` dựng một JSON object gồm `@timestamp`, `level`, `logger`, `message` và object `attributes` khi record là `JsonEvent`.
6. `normalizeLevel` ánh xạ `Level.WARNING` của JUL thành nhãn JSON `WARN`. Đây là **quy ước hiển thị/schema**, không sửa level gốc của record.
7. `ObjectMapper.writeValueAsString(...)` tạo JSON hợp lệ và escape ký tự trong chuỗi; `+ "\n"` phân cách event thành JSON Lines.
8. `ConsoleHandler` mặc định dùng **stderr**. Trong production, xác định collector đang đọc stdout, stderr hay cả hai.
9. Vì mã nguồn không gọi `System.out.println` nên stdout của ứng dụng trống. `console.close()` giải phóng tài nguyên handler trong demo kết thúc bình thường.

Để minh họa dễ, class `JsonEvent` dùng `idKey` và `idValue` ở các thuộc tính nghiệp vụ. **Đó không phải cơ chế structured logging chuẩn được JUL cung cấp**. Đây là adapter tự viết trong ví dụ, giúp hiểu rằng muốn có field thật phải đưa dữ liệu vào event/encoder có khả năng nhận field. Trong ứng dụng lớn, dùng API/backend/encoder được duy trì tốt hơn là phát triển một hệ custom LogRecord phức tạp.

### 8.6. Điều gì xảy ra nếu message chứa ký tự đặc biệt?

Giả sử message hoặc field chứa dấu ngoặc kép, dấu gạch chéo ngược hoặc xuống dòng. Jackson sẽ escape chúng trong chuỗi JSON theo đúng quy tắc. Một newline có thể được biểu diễn bằng hai ký tự nhìn thấy `\n` trong JSON output, nhưng khi parse lại sẽ thành ký tự xuống dòng trong giá trị `message`.

**Không bao giờ chỉ thay dấu ngoặc kép mà bỏ qua các ký tự điều khiển khác.** Việc sử dụng serializer là lựa chọn cơ bản để tránh JSON không hợp lệ. Tuy nhiên, nếu dữ liệu nhạy cảm đã nằm trong message, serializer sẽ vẫn xuất chúng; redaction/field allowlist là trách nhiệm khác.

### 8.7. Chuyện gì khi thêm exception?

Trong JUL, event có thể có `Throwable` tại `record.getThrown()`. Khi thiết kế JSON formatter thực tế, nên bổ sung các trường tương ứng, ví dụ:

```json
{
  "level": "ERROR",
  "event": "order_save_failed",
  "error": {
    "type": "java.io.IOException",
    "message": "Storage unavailable",
    "stackTrace": "java.io.IOException: Storage unavailable\n\tat ..."
  }
}
```

Đây là **JSON minh họa**, không phải output của demo 8.3. Nếu dùng Java để lấy stack trace, phải xử lý chuỗi Throwable/cause/suppressed exceptions và giao serializer escape. Không log duy nhất `exception.getMessage()` nếu cần điều tra stack/cause. Cũng không đưa password, JDBC connection credentials hoặc payload nhạy cảm vào exception JSON.

Với JSON Lines, stack trace có thể là một **string chứa `\n` đã escape**, giữ mỗi event trên một dòng vật lý. Khi dùng plain text multiline, collector cần cấu hình gộp stack trace nếu muốn cùng một event.

## 9. Có cần dùng Jackson để có JSON logging không?

**Không bắt buộc.** Jackson là lựa chọn minh họa cách serialize. Một backend logging chuyên dụng có thể cung cấp JSON encoder/layout hoặc tích hợp thư viện serializer riêng. Tùy Logback, Log4j 2, Spring Boot và version, cơ chế cấu hình khác nhau.

Điều quan trọng không phải tên thư viện JSON, mà là đáp ứng các yêu cầu:

- Mỗi log event được chuyển thành JSON hợp lệ đúng schema.
- Encoder đọc những metadata/attributes ứng dụng thật sự cung cấp.
- Các giá trị được giữ đúng kiểu, escape đúng, không in banner làm hỏng stream.
- Timestamp, severity, logger name và exception được xuất ổn định.
- Dữ liệu nhạy cảm được bảo vệ.
- Collector parse được và không đọc trùng/mất event ngoài chính sách.

### Logback JSON encoder ở production

Với Logback, **PatternLayout text**:

```xml
<encoder>
    <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
</encoder>
```

**không tự tạo JSON object**; output vẫn là text theo pattern. Muốn JSON, dùng encoder/layout JSON tương thích, khai báo dependency cần thiết và cấu hình đúng class/field mapping theo version.

Không đổi `<file>orders.log</file>` thành `orders.json` rồi coi là JSON logging: phần mở rộng của tệp không quyết định byte format.

### Log4j 2 JSON layout

Tương tự, một `PatternLayout` Log4j 2 phát text trừ khi cấu hình pattern để tạo JSON hợp lệ theo cách đáng tin cậy; **nên dùng layout/encoder JSON đúng chức năng** thay vì tự ghép trường JSON bằng PatternLayout đơn giản, nhất là khi message chứa dữ liệu động.

## 10. MDC và correlation ID trong JSON log

Đối với request xử lý qua nhiều lớp/service, các trường như `requestId`, `traceId`, `spanId` rất hữu ích.

Ví dụ:

```json
{"level":"INFO","traceId":"trace-42","requestId":"req-42","service":"orders-api","event":"order_accepted","orderId":"ORD-7"}
{"level":"INFO","traceId":"trace-42","requestId":"req-42","service":"inventory-api","event":"stock_reserved","orderId":"ORD-7"}
```

Trong ứng dụng có SLF4J, **MDC (Mapped Diagnostic Context)** là một cách đưa context vào logging event. Ví dụ fragment:

```java
import org.slf4j.MDC;

// LOG là org.slf4j.Logger đã khai báo trong một class.
MDC.put("requestId", "req-42");
try {
    LOG.info("event=order_accepted orderId={}", "ORD-7");
} finally {
    MDC.remove("requestId");
}
```

Đoạn trên là **snippet**, không phải chương trình Java độc lập. JSON encoder có thể được cấu hình để xuất MDC field; **chỉ gọi MDC.put không tự bảo đảm field đó đã nằm trong JSON output**. Cần kiểm tra layout/encoder và schema.

**MDC thường gắn với context của luồng hiện tại.** Khi code chuyển sang `ExecutorService`, `CompletableFuture` hoặc callback, phải có cách truyền và dọn context. Với thread pool, quên `MDC.remove`/`MDC.clear` trong lifecycle phù hợp có thể làm request sau bị gắn nhầm request ID của request trước.

JSON logging **không tự tạo distributed tracing**. Trace ID/span ID cần được instrumentation hoặc ứng dụng cung cấp theo hệ thống tracing được chọn.

## 11. Chuẩn hóa level trong nhiều backend

Tên severity có thể khác:

| Ý nghĩa | JUL | SLF4J/Logback/Log4j 2 phổ biến |
|---|---|---|
| Thông tin | `INFO` | `INFO` |
| Cảnh báo | `WARNING` | `WARN` |
| Lỗi | `SEVERE` | `ERROR` |
| Debug | `FINE` | `DEBUG` |
| Chi tiết hơn | `FINER`/`FINEST` | `TRACE` gần tương ứng |

Đây là **so sánh ý nghĩa**, không phải mapping bắt buộc của mọi adapter. Nếu collector yêu cầu `level="WARN"`, cần một mapping ổn định từ `WARNING` của JUL. Nhưng đừng map `SEVERE` thành `INFO` chỉ để làm output đẹp: như vậy biến dạng semantics và khiến alert sai.

Nếu dùng một chuẩn như OpenTelemetry Logs, schema có thể phân biệt `SeverityText` và `SeverityNumber`, không chỉ một string `level`. Áp dụng quy tắc của chuẩn đang dùng, không tự suy severity bằng cách so thứ tự từ điển của chuỗi.

**Không thêm dấu cách căn lề vào trường JSON**:

```json
{"level":"WARN"}
```

khác:

```json
{"level":"WARN "}
```

Khoảng trắng do pattern text có thể khiến query `level == "WARN"` bỏ sót event. Padding/ANSI color chỉ nên nằm trong text layout dành cho người đọc, không phải dữ liệu severity chuẩn hóa.

## 12. JSON logs và exception: điều cần giữ

Một exception hữu ích khi điều tra thường cần:

- `error.type`: loại exception, ví dụ `java.sql.SQLException`.
- `error.message`: thông điệp, sau khi xem xét có chứa secret hay không.
- `stackTrace`: chuỗi stack có cause chain/suppressed exceptions khi phù hợp.
- `event`: mã sự kiện ổn định, ví dụ `order_save_failed`.
- `traceId` hoặc `requestId`: liên kết với lần xử lý.
- `retryable`, `attempt` hoặc `operation` nếu có ý nghĩa nghiệp vụ.

Đừng chỉ viết:

```java
// Sai về khả năng điều tra nếu cần biết stack/cause.
LOG.error("save failed: {}", error.getMessage());
```

Đây là đoạn SLF4J minh họa, giả định `LOG` và `error` đã có. Nếu muốn backend ghi exception, phải truyền `Throwable` vào overload phù hợp (cần xem API/version và số arguments):

```java
// Minh họa cách ghi lỗi với Throwable.
LOG.error("event=order_save_failed", error);
```

JSON encoder cần được cấu hình để serialize exception đúng cách. Một số encoder giữ stack trace trong một string; số khác có cấu trúc khác hoặc giới hạn chiều dài. **Không có một cấu trúc exception JSON chuẩn duy nhất cho mọi backend.**

Khi collector parse JSON Lines, một stack trace chứa newline đã được escape trong chuỗi sẽ không tự tạo thêm event vật lý. Nếu encoder in stack trace ra ngoài JSON object, collector có thể parse sai.

## 13. Query, index và high-cardinality

JSON dễ truy vấn theo field, nhưng không phải cứ thêm mọi thuộc tính là tốt.

Ví dụ:

```json
{"event":"http_request","method":"GET","route":"/orders/{id}","status":200,"durationMs":37}
```

Trường `route` là mẫu tuyến đường ổn định, giúp tổng hợp theo API mà không sinh quá nhiều giá trị khác nhau. Nếu ghi raw URL chứa ID hoặc query parameters, vừa tăng cardinality vừa có thể làm lộ token/PII.

Phân biệt:

- **Field cố định:** `level`, `service`, `event`, `environment`, `http.method`.
- **Field động có giá trị điều tra:** `requestId`, `orderId`, `traceId` khi được phép.
- **Payload tùy ý:** body, headers, object đầy đủ thường không nên log mặc định.

Một số collector có chi phí tăng mạnh khi mỗi record có key mới hoặc quá nhiều giá trị unique. Hạn chế **dynamic field names** (ví dụ tạo key `user_123456`) và kiểm soát index mapping. Có thể giữ ID dưới dạng giá trị field ổn định thay vì tên field.

Để lọc JSON Lines trong file cục bộ, công cụ `jq` có thể hữu ích nếu được cài riêng (không thuộc JDK):

```bash
jq -c 'select(.level == "WARN")' application.jsonl
```

Lệnh giả định mỗi dòng là JSON object hợp lệ có field `level`. Với file chứa banner text, dòng JSON đa dòng hoặc record bị cắt, `jq` có thể báo lỗi parse.

## 14. JSON logging có luôn nhanh hơn text logging không?

**Không.** JSON đem lại lợi ích về cấu trúc và khả năng parse, nhưng serialization, escaping, object allocation và việc ghi nhiều field có chi phí CPU/bộ nhớ/I/O. Text ngắn có thể nhẹ hơn; ngược lại, pipeline JSON được tối ưu tốt có thể giúp giảm công parse downstream.

Hiệu năng phụ thuộc:

1. Số events/s và tỷ lệ events bị lọc.
2. Kích thước message, MDC/context, array/object và exception.
3. Encoder/serializer và chính sách allocation.
4. Appender console/file/network, buffered I/O và downstream collector.
5. Có async appender/queue, batching, compression hay không.
6. Log volume tăng do schema thừa hay payload lớn.

### JSON và async appender là hai khái niệm khác nhau

- **JSON encoder** chọn cách **biểu diễn** event.
- **Async appender** chọn cách **xếp hàng và tách thread** để xử lý event.
- **Rolling policy** chọn cách **chia file theo kích thước/thời gian**.
- **Collector** chọn cách **thu, vận chuyển, parse/index**.

Bật JSON không tự bật async, rotation hoặc retention. Bật async không bảo đảm không mất log; queue có thể đầy, sự kiện có thể drop hoặc còn trong bộ nhớ khi process chết. Phải kiểm thử shutdown/flush và policy quá tải.

Không lấy JSON log làm dữ liệu giao dịch duy nhất khi nghiệp vụ yêu cầu durability, exactly-once hoặc audit chống sửa đổi. Có thể cần transactional outbox, event store hoặc audit trail chuyên dụng.

## 15. Bảo mật và quyền riêng tư

JSON khiến việc tra cứu dữ liệu dễ hơn, nên rủi ro **lộ thông tin qua field có cấu trúc** cũng đáng chú ý hơn.

### 15.1. Không ghi bí mật vào log

Không log password, API key, access token, session cookie, mã thẻ, chuỗi kết nối có credentials hoặc payload chứa thông tin cá nhân không cần thiết. Không giả định level DEBUG là an toàn: dữ liệu thật có thể bị ghi vào file, backup, collector hoặc môi trường thử nghiệm dùng dữ liệu production.

Nên dùng **allowlist trường được phép ghi**, không chỉ blacklist một vài từ nhạy cảm. Với ID nghiệp vụ, cân nhắc masking/hash/pseudonymization phù hợp yêu cầu vận hành và pháp lý.

### 15.2. Escaping không đồng nghĩa redaction

JSON serializer giải quyết **cú pháp**: biến dấu nháy, control character và newline thành chuỗi JSON hợp lệ. Nó **không quyết định** dữ liệu nào cần ẩn.

Một event có giá trị `"password":"my-secret"` vẫn là JSON hợp lệ nhưng là sai về bảo mật.

### 15.3. Tránh log injection và phá schema

Không cho dữ liệu user quyết định key của JSON object hoặc đưa trực tiếp vào template JSON chưa được escape. Dùng serializer và schema field name cố định. Nếu message có newline, collector nên nhận nó dưới dạng một JSON string hợp lệ trong một JSON Line.

### 15.4. Phân quyền và retention

File/stream JSON có thể được ship tới nhiều hệ thống. Cần:
- Quyền truy cập log phù hợp vai trò.
- Mã hóa đường truyền/lưu trữ theo chính sách.
- Rotation, retention, deletion và quota được quản lý.
- Kiểm tra schema không giữ quá nhiều dữ liệu không cần thiết.
- Audit ai có quyền tra cứu/xuất log nhạy cảm.

JSON không tự mã hóa hay xác thực nguồn gốc sự kiện.

## 16. Triển khai trong container và hệ thống phân tán

Nhiều ứng dụng Java chạy trong container thường xuất log ra **stdout/stderr**, để runtime/agent thu thập. JSON Lines là lựa chọn phổ biến vì một record có thể được parse độc lập.

Tuy nhiên, cần thống nhất:

- **Stream nào:** stdout, stderr hay cả hai? Một số công cụ gắn severity từ stream riêng; đừng vô tình khiến collector bỏ một stream.
- **Schema nào:** các service cùng tên field, timezone, level mapping và kiểu dữ liệu.
- **Metadata nào:** pod/container/service labels có thể được collector bổ sung; không cần ghi lặp hoặc để user giả mạo metadata.
- **Giới hạn kích thước:** collector/platform có thể cắt dòng quá dài, khiến JSON mất tính hợp lệ.
- **Exception:** stack trace nên ở một JSON string/field có escaping đúng.
- **Ordering:** nhiều threads/instances không có thứ tự toàn cục; dùng event timestamp và correlation ID.
- **Delivery:** agent restart, network outage và retention có thể gây mất/trùng; JSON format không giải quyết.
- **Latency:** event phát lúc này có thể đến collector muộn do queue/batching/backpressure.

Nếu file hiện tại ghi JSON Lines, cần thống nhất file pattern, cách agent theo dõi rotate/rename và retention. Đừng để app vừa ghi JSON file vừa ghi JSON console rồi collector thu cả hai mà không có chủ đích; điều này có thể nhân đôi dashboard counts.

## 17. Lỗi thường gặp khi dùng JSON logging

| Hiện tượng | Nguyên nhân có thể | Cách xác minh/khắc phục |
|---|---|---|
| Collector báo JSON parse error | Text banner xen kẽ, JSON đa dòng, message chưa được escape | Kiểm tra từng dòng bằng JSON parser, dùng encoder JSON |
| Field `orderId` không tìm được | Nó nằm trong chuỗi `message` | Đưa vào structured field riêng |
| JSON bị cắt giữa chừng | Collector giới hạn độ dài dòng hoặc crash/partial write | Kiểm tra max event size, batching và pipeline |
| Timestamp sai múi giờ | Server timezone không thống nhất | Chuẩn hóa ISO 8601/UTC hoặc zone theo schema |
| `level` là `WARNING` nhưng dashboard tìm `WARN` | JUL và backend khác tên mức | Mapping có chủ đích và thống nhất |
| JSON nhìn hợp lệ nhưng sai kiểu | `durationMs` được ghi thành string | Kiểm tra serializer, schema và index mapping |
| Không có `requestId`/`traceId` | Context chưa được gắn hoặc không được encoder xuất | Kiểm tra MDC/tracing và async boundary |
| Hai sự kiện thành một dòng | Thiếu newline phân tách | Bổ sung newline sau mỗi object |
| Một exception thành nhiều sự kiện | Stack trace raw in ngoài JSON | Serialize exception vào trường và escape |
| Một event bị đếm hai lần | Console + file cùng ship, nhiều appenders/bridge | Kiểm tra topology và nguồn collector |
| JSON có dữ liệu nhạy cảm | Không lọc field/Throwable, chỉ dựa vào serializer | Dùng allowlist, masking, kiểm soát retention |
| Chạy Logback nhưng file vẫn là text | Đang dùng PatternLayout text | Chọn JSON encoder đúng class/version |
| Chỉ thay đuôi file thành `.json` | Định dạng byte chưa đổi | Thay formatter/encoder, kiểm tra parser |
| JSON log mất khi traffic cao | Async queue drop, I/O/collector lỗi | Đo queue, loss, shutdown và log pipeline |
| Không parse được do ANSI color | Pattern tô màu ghi vào JSON stream | Tắt màu trên output máy đọc |
| Alert sai sau khi đổi key | Schema thay đổi mà query cũ không cập nhật | Versioning/backward compatibility |

### Quy trình chẩn đoán nhanh

1. Xác định **backend/encoder thực sự đang chạy**; không chỉ dựa vào import SLF4J.
2. Lấy **một dòng raw** từ stdout/file trước collector, xác nhận nó là JSON object hợp lệ.
3. Kiểm tra timestamp, level, logger, message và các field nghiệp vụ.
4. Kiểm tra các field thật sự có kiểu và tên đúng theo schema.
5. Kiểm tra escaping của dấu nháy, backslash, newline, Unicode.
6. Kiểm tra exception và context của event ở request thực.
7. Đối chiếu record raw với dữ liệu đã parse/index trong collector.
8. Nếu dữ liệu có trong raw nhưng mất trên dashboard, kiểm tra collector/parser/index/retention, không vội sửa logic nghiệp vụ.

## 18. Bài tập thực hành

### Bài tập A — Text sang JSON

Cho một dòng:

```text
2026-11-09T08:15:03Z WARN PaymentClient - Retry attempt 3 for order ORD-7
```

Hãy thiết kế JSON với các trường `timestamp`, `level`, `logger`, `event`, `attempt` và `orderId`. Đừng ghi `attempt` như string nếu schema đã xác định đó là number.

Một kết quả hợp lý:

```json
{"timestamp":"2026-11-09T08:15:03Z","level":"WARN","logger":"PaymentClient","event":"payment_retry","attempt":3,"orderId":"ORD-7"}
```

### Bài tập B — Phân biệt message JSON

Cho:

```json
{"level":"INFO","message":"{\"event\":\"order_accepted\",\"orderId\":\"ORD-7\"}"}
```

`orderId` có phải field top-level không?

**Đáp án:** Không. Nó nằm trong chuỗi message. Muốn truy vấn trực tiếp, encoder phải đưa nó thành field cấu trúc hoặc collector phải chủ động parse message lần nữa.

### Bài tập C — JSON Lines

Một chương trình dùng pretty-print để in mỗi JSON event trên năm dòng. Collector lại coi mỗi newline là một event. Kết quả có thể là gì?

**Đáp án:** Collector có thể báo parse error, bỏ những mảnh không hợp lệ hoặc tách một sự kiện thành nhiều dòng rời rạc. Giải pháp là dùng compact JSON một object/một dòng hoặc cấu hình framing/multiline chính xác theo pipeline.

### Bài tập D — Lỗi bảo mật

Một developer thêm `http.headers` đầy đủ vào JSON để debug lỗi xác thực. Header chứa Authorization bearer token.

**Đáp án:** JSON vẫn hợp lệ nhưng nguy hiểm. Nên chỉ ghi allowlisted headers/metadata an toàn, che hoặc bỏ credential và giới hạn quyền xem/retention. Không coi JSON encoder là một cơ chế bảo mật.

## 19. Checklist trước khi đưa JSON logging vào production

- [ ] Mỗi event xuất thành **một JSON object trên một dòng** nếu dùng JSON Lines.
- [ ] Formatter/encoder dùng serializer đáng tin cậy, không tự ghép chuỗi JSON.
- [ ] Các key lõi và kiểu dữ liệu tuân theo schema chung.
- [ ] Timestamp, timezone và độ chính xác thống nhất.
- [ ] Level có mapping rõ giữa JUL và SLF4J/Logback/Log4j 2 nếu cần.
- [ ] Event name ổn định, message dành cho con người và attributes dành cho máy.
- [ ] `orderId`, `traceId` và `requestId` là field thật khi pipeline cần truy vấn.
- [ ] Context được gán, truyền qua async boundary và dọn đúng.
- [ ] Exception được serialize có kiểm soát, không phá quy tắc một dòng.
- [ ] Không chứa secrets/PII không cần thiết; có field allowlist/redaction.
- [ ] Không tạo dynamic field names gây cardinality/index mapping explosion.
- [ ] Đã test đầu ra raw bằng JSON parser trước khi đưa vào collector.
- [ ] Đã kiểm tra stream stdout/stderr, file rotation, duplicate và queue loss.
- [ ] Đã thử input chứa dấu nháy, newline, backslash, Unicode và payload dài.
- [ ] Có kế hoạch schema versioning, monitoring lỗi parse và rollback.
- [ ] Đã kiểm tra dashboard/query/alert sau khi chuyển từ text sang JSON.

**Kết luận:** JSON log là cách biểu diễn mỗi **sự kiện logging** thành một đối tượng JSON có các trường có tên và kiểu dữ liệu rõ ràng, thường xuất theo **JSON Lines** để hệ thống tập trung parse và truy vấn thuận tiện. Nó khác với việc chỉ nhét một chuỗi JSON vào `message`. Trong Java, ứng dụng cần cung cấp event/context, còn formatter/encoder của JUL, Logback hoặc Log4j 2 chịu trách nhiệm serialization. JSON giúp tăng khả năng quan sát, nhưng **không thay thế** chính sách level, kiểm soát dữ liệu nhạy cảm, async/rotation/retention hay thiết kế collector bền vững.
