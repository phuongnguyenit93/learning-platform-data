# Kiểm tra JSON hợp lệ trong Java Logging

**Kiểm tra JSON hợp lệ** là việc xác minh một bản ghi log được biểu diễn đúng theo định dạng JSON, có ranh giới sự kiện rõ ràng, giữ đúng kiểu dữ liệu và đáp ứng hợp đồng thông tin mà hệ thống quan sát cần sử dụng. Trong chủ đề **JSON logging**, tính hợp lệ không dừng ở chỗ dấu ngoặc và dấu nháy đúng.

Ví dụ một sự kiện log:

~~~json
{"timestamp":"2026-11-09T10:15:30Z","level":"WARN","event":"payment_retry","durationMs":42,"message":"Gateway timeout"}
~~~

Dòng này có thể kiểm tra ở bốn cấp độ: **cú pháp JSON**, **mỗi sự kiện trên một dòng JSONL**, **schema và ý nghĩa của từng trường**, cuối cùng là **khả năng được collector nhận và truy vấn đúng**. Một bản ghi qua được cấp độ đầu nhưng vẫn có thể hỏng ở các cấp độ sau.

## 1. Bốn mức độ hợp lệ cần phân biệt

| Mức kiểm tra | Câu hỏi | Trường hợp không đạt |
| --- | --- | --- |
| JSON syntax | Dữ liệu có parse được bằng parser tuân thủ JSON chuẩn không? | Thiếu ngoặc, dùng nháy đơn, dấu phẩy thừa |
| JSON Lines / NDJSON | Mỗi dòng vật lý có đúng một JSON event không? | Pretty print một object ra nhiều dòng |
| Schema / semantic | Root, field bắt buộc, kiểu, timestamp và giá trị có đúng không? | durationMs là string thay vì number |
| End-to-end logging | Backend, collector và storage có giữ đúng event/field không? | JSON đúng nhưng collector không parse hoặc làm sai mapping |

**JSON hợp lệ về cú pháp không đồng nghĩa với một log event hợp lệ.** JSON cho phép root là object, array, string, number, boolean hoặc null. Tuy nhiên hợp đồng JSON logging thường yêu cầu **root object**, gồm các field cụ thể và có thể loại các giá trị mà JSON parser đơn thuần vẫn nhận.

Ví dụ:

~~~json
[{"event":"ready"}]
~~~

Đây là JSON đúng cú pháp nhưng **không phù hợp** nếu ứng dụng quy định mỗi dòng phải là một object đơn lẻ, không phải một mảng.

Tương tự:

~~~json
{"durationMs":"42"}
~~~

là JSON đúng cú pháp, nhưng schema yêu cầu durationMs là **integer** thì bản ghi bị coi là **sai schema**.

## 2. Các quy tắc cú pháp JSON cần nắm

JSON có các kiểu: **object**, **array**, **string**, **number**, **boolean**, **null**. Object là tập hợp các cặp tên–giá trị; array là một dãy giá trị.

~~~json
{
  "event": "order_completed",
  "durationMs": 37,
  "success": true,
  "tags": ["checkout", "payment"],
  "error": null,
  "details": {"attempt": 2}
}
~~~

Một vài quy tắc quan trọng:

1. **Tên field** trong object là string có **nháy kép**.
2. Dấu hai chấm phân tách tên field và giá trị, dấu phẩy phân tách các phần tử.
3. JSON chuẩn không có comment dạng // hay /* ... */.
4. Không cho dấu phẩy ở sau phần tử cuối của object hoặc array.
5. Boolean là chữ thường true và false; giá trị rỗng là null.
6. Không dùng undefined làm literal.
7. Số dùng dấu chấm cho phần thập phân; không dùng NaN hoặc Infinity như JSON number chuẩn.
8. String phải escape dấu nháy kép, backslash và các control characters theo đúng cú pháp.

Các lỗi minh họa:

| Input sai | Nguyên nhân |
| --- | --- |
| {event:"ready"} | Thiếu nháy kép quanh tên key |
| {'event':'ready'} | Dùng nháy đơn theo phong cách JavaScript, không phải JSON |
| {"event":"ready",} | Dấu phẩy thừa |
| {"event":"ready" "level":"INFO"} | Thiếu dấu phẩy |
| {"attempt":undefined} | undefined không phải JSON value |
| {"durationMs":NaN} | NaN không phải JSON number |
| {"success":TRUE} | TRUE phải là true |
| {"event":"ready"} other | Dư dữ liệu có nghĩa sau JSON document |

Một số parser hỗ trợ **non-standard extensions**, chẳng hạn comment hoặc dấu phẩy cuối. Nếu kiểm thử bằng parser đã bật những tùy chọn đó, có thể chấp nhận dữ liệu mà collector production từ chối. Với log giao tiếp giữa nhiều hệ thống, nên dùng cú pháp JSON chuẩn và cấu hình parser chặt.

## 3. JSON Lines (JSONL/NDJSON) là gì?

JSON Lines, thường có phần mở rộng .jsonl, là cách lưu **một JSON value trên mỗi dòng vật lý**. Với JSON logging, hợp đồng thực tế thường yêu cầu **mỗi dòng là một JSON object duy nhất**.

~~~text
{"level":"INFO","event":"order_started","orderId":"ord-7"}
{"level":"WARN","event":"payment_retry","orderId":"ord-7","attempt":2}
{"level":"INFO","event":"order_completed","orderId":"ord-7"}
~~~

Lợi ích là có thể append từng event và đọc dần bằng streaming mà không cần giữ nguyên một document khổng lồ trong bộ nhớ.

Phân biệt hai cách biểu diễn:

**Một JSON document hợp lệ được pretty print:**

~~~json
{
  "event": "order_started",
  "level": "INFO"
}
~~~

**Một bản ghi JSONL hợp lệ:**

~~~text
{"event":"order_started","level":"INFO"}
~~~

Cả hai đều là JSON đúng khi xét **nguyên khối**, nhưng nếu collector cắt **mỗi dòng** thành một record thì pretty-printed object sẽ bị chia sai. Vì vậy:

- Một event JSONL cần nằm trên **một dòng vật lý**.
- Newline thực có trong giá trị message phải được **escape trong JSON string**.
- Không in riêng stack trace nhiều dòng sau dấu ngoặc đóng JSON object.
- Dòng rỗng không phải một JSON value hợp lệ, dù một số collector có thể chủ động bỏ qua.
- Luồng nên được mã hóa bằng UTF-8, không có BOM.
- Dòng cuối có thể có newline kết thúc để thuận tiện append; không cần thêm một object rỗng.

**Lưu ý về công cụ:** một parser chấp nhận nhiều JSON documents liên tiếp không nhất thiết xác nhận mỗi object chiếm đúng một dòng. Ngược lại, parser cho một document duy nhất có thể từ chối file JSONL gồm nhiều object. Cần dùng **đúng phương pháp kiểm tra framing**, không chỉ hỏi parser có chấp nhận toàn bộ stream không.

## 4. Escape ký tự điều khiển và bảo vệ ranh giới sự kiện

Giả sử thông điệp thực chứa:

~~~text
gateway said: "retry"
please wait
~~~

Nếu ứng dụng nối chuỗi JSON bằng tay:

~~~java
// Ví dụ SAI nếu message chứa nháy kép hoặc newline.
String json = "{\"message\":\"" + message + "\"}";
~~~

Kết quả có thể tạo JSON không hợp lệ và tách thành nhiều dòng vật lý. Đó là một dạng **log injection** khi giá trị không tin cậy phá ranh giới bản ghi hoặc giả mạo một dòng log khác.

Một JSON serializer chuẩn sẽ chuyển thông điệp đó thành phần value có escape:

~~~json
{"message":"gateway said: \"retry\"\nplease wait"}
~~~

Dòng JSON trên vẫn có **một newline vật lý ở cuối bản ghi**, không có newline vật lý bên trong value. Các chuỗi backslash–n và backslash–quote là escape sequences trong file, được parser khôi phục thành ký tự gốc khi đọc.

Những escape thường gặp:

| Ký tự gốc | Biểu diễn trong JSON string |
| --- | --- |
| Dấu nháy kép | \" |
| Backslash | \\ |
| Xuống dòng LF | \n |
| Carriage return | \r |
| Tab | \t |
| Một số control characters khác | \u00XX |

Không nên tự viết toàn bộ logic escape bằng vài lần replace, vì string có thể chứa nhiều dạng Unicode/control characters khác nhau. **Dùng ObjectMapper hoặc JSON encoder chuyên dụng**, để serializer chịu trách nhiệm mã hóa cú pháp.

Đặc biệt với đường dẫn Windows, một chuỗi chứa backslash không được escape có thể bị hiểu thành tab, newline hay escape không hợp lệ. JSON parse được chưa chắc giá trị path sau parse giống path ban đầu nếu chuỗi do con người ghép sai.

**Escaping không phải redaction.** Một JSON object có password hoặc token vẫn có thể hoàn toàn hợp lệ về cú pháp. Không đưa thông tin nhạy cảm vào log chỉ vì nó được JSON-escape đúng.

## 5. Schema: field nào bắt buộc và kiểu gì?

Một hợp đồng JSON logging minh họa cho Java service:

| Field | Kiểu mong đợi | Bắt buộc trong ví dụ | Quy tắc |
| --- | --- | --- | --- |
| timestamp | String | Có | ISO-8601 có timezone/offset |
| level | String | Có | TRACE, DEBUG, INFO, WARN, ERROR |
| event | String | Có | Tên event ổn định, không rỗng |
| message | String | Có | Thông điệp không rỗng |
| durationMs | Integer | Có | Không âm, vừa phạm vi long |
| service | String | Tùy chọn | Tên service do tổ chức quản lý |
| requestId | String | Tùy chọn | ID tương quan khi phù hợp |
| traceId | String | Tùy chọn | Theo quy ước tracing |
| errorType | String | Tùy chọn | Tên loại exception khi có lỗi |

Đây là **schema dùng để học**, không phải bắt buộc cho mọi backend. Một ứng dụng dùng JUL có thể phát WARNING/SEVERE, trong khi SLF4J dùng WARN/ERROR. Muốn chuẩn hóa, thiết lập level mapping trong logging pipeline.

### Kiểm tra type trước khi chuyển đổi

Nếu input:

~~~json
{"durationMs":"42","success":"false"}
~~~

thì hai value là **string**, không phải number và boolean. Một số API Java có thể ép string sang number và làm mất dấu vết dữ liệu sai kiểu. Để chẩn đoán schema, nên kiểm tra trực tiếp kiểu JSON của node trước, như isIntegralNumber() hoặc isBoolean(), thay vì chỉ gọi asLong() hay asBoolean() rồi coi mọi thứ hợp lệ.

### Phân biệt missing, null và empty

Các object dưới đây mang trạng thái khác nhau:

~~~json
{"requestId":null}
~~~

~~~json
{}
~~~

~~~json
{"requestId":""}
~~~

Thiếu field, field bằng null và field là chuỗi rỗng không có cùng nghĩa trong mọi hợp đồng. Validator phải đặt quy tắc rõ: một field tùy chọn có thể không xuất hiện, nhưng nếu xuất hiện nó phải thuộc kiểu nào? Với field bắt buộc, null hoặc empty có được phép không?

### Giá trị sai dù type đúng

~~~json
{"durationMs":-10}
~~~

Giá trị này có thể là number hợp lệ, nhưng sai nếu duration phải không âm. Tương tự, event name dùng UUID động có thể đúng string nhưng gây khó thống kê; level "INFORMATION" có thể sai enum dù không sai JSON syntax.

**Schema validation nên kiểm tra cả tên, kiểu, miền giá trị và đơn vị.** Các điều kiện phức tạp có thể dùng JSON Schema hoặc contract validator, nhưng vẫn cần test ở điểm ingestion.

## 6. Timestamp hợp lệ và timezone

JSON không có kiểu datetime riêng; timestamp thường được lưu dưới dạng string theo hợp đồng của hệ logging.

~~~json
{"timestamp":"2026-11-09T10:15:30Z"}
~~~

~~~json
{"timestamp":"2026-11-09T17:15:30+07:00"}
~~~

Hai giá trị trên có offset rõ ràng. Trong Java có thể parse bằng java.time.OffsetDateTime rồi chuyển về Instant. Trái lại, các string như "yesterday" hoặc "2026-11-09 10:15:30" vẫn hợp lệ là **JSON string**, nhưng thiếu định dạng thời gian/offset được schema ví dụ chấp nhận.

~~~java
// Đoạn minh họa trong một method có biến timestamp kiểu String.
java.time.OffsetDateTime parsed =
        java.time.OffsetDateTime.parse(timestamp);
java.time.Instant utcInstant = parsed.toInstant();
~~~

Điểm cần hiểu:

1. **Parse được** không chứng minh đồng hồ máy chủ đúng.
2. **Event timestamp** khác **ingestion timestamp**; queue/network có thể tạo độ trễ.
3. Nếu dùng UTC, hãy ghi Z hoặc offset phù hợp thật, không thêm chữ Z vào giờ local tùy ý.
4. Thống nhất độ chính xác và timezone giữa các service.
5. Timestamp sai khiến event nằm ngoài time range dashboard, dù JSON syntax hoàn toàn hợp lệ.

## 7. Duplicate keys và trailing tokens

Một vấn đề dễ bị bỏ qua:

~~~json
{"event":"ready","level":"INFO","level":"ERROR"}
~~~

Một số JSON parser có thể chấp nhận key trùng và lấy giá trị cuối; một số parser khác sẽ lấy giá trị đầu hoặc báo lỗi. Theo RFC 8259, tên member **nên duy nhất**; về mặt vận hành, để tránh collector và ứng dụng hiểu cùng event theo hai cách khác nhau, nên **từ chối duplicate keys**.

Jackson có tùy chọn **StreamReadFeature.STRICT_DUPLICATE_DETECTION** để phát hiện trường hợp này.

Một trường hợp khác:

~~~text
{"event":"ready"} true
~~~

Dòng đó không phải một JSON value duy nhất. Nếu code chỉ đọc phần object đầu tiên và bỏ qua token sau, validator có thể báo pass sai. Jackson hỗ trợ **DeserializationFeature.FAIL_ON_TRAILING_TOKENS** để từ chối phần dữ liệu có nghĩa còn dư sau một giá trị.

Đừng nhầm điều này với việc **có nhiều dòng JSONL**: mỗi dòng vẫn được phép là một object hợp lệ riêng, nhưng trong **một dòng** không được ghép nhiều document.

### Tại sao phải bật kiểm tra rõ ràng?

Các thư viện có cấu hình mặc định khác nhau và thay đổi theo phiên bản. Nếu yêu cầu strict parsing, hãy khai báo rõ các tính năng quan trọng, viết test duplicate/trailing và chạy lại test sau khi nâng phiên bản.

Chi phí phát hiện duplicate keys có thể làm parser tốn thêm tài nguyên; nếu validator chạy trên tuyến ingest lưu lượng lớn, cần đo với workload thực tế thay vì đoán.

## 8. Ví dụ hoàn chỉnh Java 17+: kiểm tra file JSONL bằng Jackson

Ví dụ này dùng Maven, **Jackson 2.18.4** và JDK 17+. Chương trình tạo event hợp lệ bằng serializer, ghi cùng các trường hợp lỗi vào **file tạm**, đọc từng dòng rồi trả về một trong ba nhãn:

- **VALID:** JSON parse được, root object và các trường đúng schema mẫu.
- **INVALID_JSON:** cú pháp lỗi, duplicate keys, trailing tokens hoặc dòng rỗng.
- **INVALID_SCHEMA:** cú pháp JSON đúng nhưng root/type/required field/value sai.

Không có dependency Logback hoặc Log4j 2 ở đây vì mục đích là **kiểm tra bản ghi JSON đã xuất ra**. Trong production, có thể kết hợp validator với việc đọc file/stream thực tế do backend ghi.

### 8.1. Cấu trúc dự án

~~~text
json-log-validation/
├── pom.xml
└── src/main/java/demo/JsonLogValidationDemo.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://www.w3.org/2001/XMLSchema-instance">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>json-log-validation</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
      <version>2.18.4</version>
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
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 8.3. JsonLogValidationDemo.java

~~~java
package demo;

import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class JsonLogValidationDemo {
    private static final ObjectMapper MAPPER =
            new ObjectMapper(JsonFactory.builder()
                    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
                    .build())
                    .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
    private static final Set<String> LEVELS =
            Set.of("TRACE", "DEBUG", "INFO", "WARN", "ERROR");

    public static void main(String[] args) throws Exception {
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("timestamp", "2026-11-09T10:15:30Z");
        event.put("level", "WARN");
        event.put("event", "payment_retry");
        event.put("durationMs", 42);
        event.put("message", "gateway said: \"retry\"\nnext");
        String valid = MAPPER.writeValueAsString(event);

        List<String> input = List.of(
                valid,
                "{\"event\":\"unfinished\",",
                "{\"timestamp\":\"2026-11-09T10:15:30Z\","
                    + "\"level\":\"INFO\",\"event\":\"ok\","
                    + "\"durationMs\":\"42\",\"message\":\"done\"}",
                "{\"timestamp\":\"2026-11-09T10:15:30Z\","
                    + "\"level\":\"WARN\",\"event\":\"a\","
                    + "\"event\":\"b\",\"durationMs\":1,\"message\":\"x\"}",
                "{\"timestamp\":\"2026-11-09T10:15:30Z\","
                    + "\"level\":\"INFO\",\"event\":\"ok\","
                    + "\"durationMs\":1,\"message\":\"done\"} true",
                "{\"level\":\"INFO\",\"event\":\"ok\","
                    + "\"durationMs\":1,\"message\":\"done\"}",
                "[]");

        Path file = Files.createTempFile("json-log-validation-", ".jsonl");
        try {
            Files.write(file, input, StandardCharsets.UTF_8);
            try (BufferedReader reader =
                    Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String line;
                int number = 0;
                while ((line = reader.readLine()) != null) {
                    System.out.println("line" + (++number) + "=" + validate(line));
                }
            }
            System.out.println("validJsonIsOneLine="
                    + !valid.contains("\n"));
        } finally {
            Files.deleteIfExists(file);
        }
    }

    private static String validate(String line) {
        if (line.isBlank()) {
            return "INVALID_JSON";
        }

        final JsonNode record;
        try {
            record = MAPPER.readTree(line);
        } catch (JsonProcessingException e) {
            return "INVALID_JSON";
        }

        if (record == null || !record.isObject()
                || !textPresent(record, "timestamp")
                || !textPresent(record, "event")
                || !textPresent(record, "message")
                || !textPresent(record, "level")
                || !LEVELS.contains(record.get("level").asText())
                || !record.path("durationMs").isIntegralNumber()
                || !record.path("durationMs").canConvertToLong()
                || record.path("durationMs").longValue() < 0) {
            return "INVALID_SCHEMA";
        }

        try {
            OffsetDateTime.parse(record.get("timestamp").asText());
        } catch (DateTimeParseException e) {
            return "INVALID_SCHEMA";
        }
        return "VALID";
    }

    private static boolean textPresent(JsonNode record, String field) {
        JsonNode value = record.path(field);
        return value.isTextual() && !value.asText().isBlank();
    }
}
~~~

### 8.4. Lệnh chạy

Trong thư mục có pom.xml, dùng Maven và JDK 17+:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.JsonLogValidationDemo
~~~

**Stdout đã được kiểm chứng bằng chương trình Java thực:**

~~~text
line1=VALID
line2=INVALID_JSON
line3=INVALID_SCHEMA
line4=INVALID_JSON
line5=INVALID_JSON
line6=INVALID_SCHEMA
line7=INVALID_SCHEMA
validJsonIsOneLine=true
~~~

Đọc từng kết quả:

| Dòng | Mẫu dữ liệu | Tại sao? |
| --- | --- | --- |
| 1 | Jackson serialize object có dấu nháy và newline trong message | Có escape, field đúng và trên một dòng |
| 2 | Object chưa đóng và thiếu value | INVALID_JSON do cú pháp |
| 3 | durationMs được truyền dưới dạng string | INVALID_SCHEMA vì type sai |
| 4 | Field event xuất hiện hai lần | INVALID_JSON do strict duplicate detection |
| 5 | Một object cộng thêm token true | INVALID_JSON do trailing token |
| 6 | Thiếu timestamp | INVALID_SCHEMA |
| 7 | Root là array rỗng | JSON parse được nhưng INVALID_SCHEMA |

Dòng validJsonIsOneLine=true chứng minh serializer không để **newline vật lý** bên trong JSON text do message chứa newline. Newline được encode thành escape sequence.

Chương trình dùng LinkedHashMap để tạo event dễ dự đoán khi debug; **schema và truy vấn không nên phụ thuộc thứ tự field JSON**. Nó không in nguyên JSON chứa dữ liệu thật ra diagnostic stream.

### 8.5. Vì sao dùng BufferedReader?

Đọc từng dòng với Files.newBufferedReader và StandardCharsets.UTF_8 giúp kiểm tra file JSONL mà không nạp tất cả file vào bộ nhớ cùng lúc. Tuy nhiên readLine() vẫn tạo **một String cho cả dòng**. Với input không tin cậy có dòng hàng trăm megabyte, cần thêm **giới hạn byte/line hoặc parser stream constraints**, tránh rủi ro cạn bộ nhớ.

File tạm trong bài được xóa trong finally. Khi kiểm tra log production, **không xóa hoặc ghi đè file log thật**; đọc snapshot/stream được phép truy cập và giữ đúng chính sách bảo mật.

### 8.6. Vì sao cấu hình Jackson trước khi dùng?

ObjectMapper được tạo với StreamReadFeature.STRICT_DUPLICATE_DETECTION trong JsonFactory và bật DeserializationFeature.FAIL_ON_TRAILING_TOKENS. Hai tùy chọn này là những yêu cầu kiểm tra chủ động; **không nên dựa vào mặc định parser**.

Một ObjectMapper đã cấu hình xong có thể được tái sử dụng, tránh tạo mapper mới cho từng log event. Không nên liên tục thay đổi cấu hình của cùng một mapper khi nhiều thread đang dùng chung.

### 8.7. Giới hạn của validator mẫu

Validator trên chỉ thực thi **schema cơ bản**. Nó chưa kiểm tra:

- Các field bổ sung có bị cấm hay không.
- Giới hạn độ dài event/message hoặc độ sâu nested object.
- Định dạng riêng của traceId, service hoặc errorType.
- Tính hợp lệ liên sự kiện, chẳng hạn order_complete chỉ xuất sau order_started.
- Hợp lệ của JSON Schema phức tạp hoặc version schema.
- Byte stream gốc có bị giải mã sai không.
- Các vấn đề bảo mật trong nội dung message/exception.
- Dữ liệu đã đến collector và được index đúng chưa.

Nếu muốn kiểm tra nhiều loại event hoặc hợp đồng có điều kiện, hãy dùng JSON Schema hoặc validator chuyên dụng và đặt test cho thay đổi schema. Parse thành JsonNode **không thay thế kiểm tra nghiệp vụ**.

## 9. Jackson và những lựa chọn strict validation

Ba điểm cần để ý:

**Thứ nhất: chỉ dùng ObjectMapper.readTree không đủ cho schema.** readTree xác nhận có thể parse dữ liệu thành cây JSON; nó không biết field nào là bắt buộc trong hệ logging.

**Thứ hai: duplicate keys có thể được xử lý khác nhau giữa các hệ thống.** Nếu ứng dụng và collector hiểu cùng tên field theo hai cách, log có thể tạo ra kết quả sai hoặc gây nhầm lẫn trong điều tra. Cấu hình strict duplicate detection giúp tránh một lớp lỗi này.

**Thứ ba: trailing tokens phải được phát hiện khi hợp đồng yêu cầu mỗi dòng một event.** Bật FAIL_ON_TRAILING_TOKENS để không đọc một object đầu rồi âm thầm bỏ qua phần dữ liệu còn lại.

Đối với dữ liệu quá lớn hoặc nested quá sâu, có thể áp dụng parser constraints của phiên bản Jackson đang sử dụng. Cần cân bằng tính chặt chẽ, chi phí CPU và mục tiêu bảo vệ pipeline trước input không tin cậy.

## 10. JSON number, NaN, Infinity và dữ liệu phép tính

Java có các giá trị Double.NaN, Double.POSITIVE_INFINITY và Double.NEGATIVE_INFINITY. Chúng **không có literal JSON number hợp lệ** theo chuẩn.

Nếu structured log chứa kết quả phép chia hoặc thống kê có thể tạo ra non-finite value, phải xác định schema:

- Từ chối event hoặc field.
- Bỏ field và ghi reason code.
- Dùng JSON null nếu contract cho phép.
- Dùng string được quy định rõ, nếu hệ phân tích thật sự hỗ trợ.

Không bật non-standard JSON number chỉ vì serializer có tùy chọn, nếu downstream collector chỉ hỗ trợ JSON chuẩn.

Một dạng lỗi khác là quá số lớn hoặc mất độ chính xác: JSON parser có thể đọc số rất lớn bằng BigInteger/BigDecimal, còn schema ứng dụng có thể yêu cầu signed 64-bit integer. Vì vậy validator ví dụ kiểm tra cả isIntegralNumber và canConvertToLong trước khi nhận durationMs.

## 11. UTF-8 và Unicode

JSON Lines được quy ước sử dụng **UTF-8**. Chuỗi chứa tiếng Việt, emoji và các ký tự Unicode phải được mã hóa đúng trong byte stream.

Những vấn đề cần lưu ý:

- Producer và consumer phải thống nhất charset.
- Byte stream bị cắt giữa một ký tự UTF-8 có thể khiến decoder/parser báo lỗi.
- Một số decoder thay byte không hợp lệ bằng ký tự thay thế, làm dữ liệu hiển thị có vẻ “hợp lệ” nhưng đã bị đổi.
- BOM ở đầu stream có thể khiến một số parser đọc lỗi; với JSON Lines nên không phát BOM.
- Unicode escape có thể hợp lệ nhưng cách hiển thị hoặc chuẩn hóa ký tự khác nhau giữa hệ thống.
- Dùng UTF-8 khi ghi và đọc file, không dựa vào default charset của máy.

Khi cần kiểm chứng ở mức byte, hãy dùng decoder báo lỗi malformed/unmappable input hoặc kiểm tra bằng pipeline mục tiêu. **Việc console hiển thị dấu tiếng Việt chưa chứng minh byte stream lưu trữ hoàn toàn đúng**.

## 12. Gắn validator với backend logging thật

Ở Java, việc tạo JSON cuối cùng thường do **backend encoder/layout**, không phải SLF4J API đơn lẻ:

| Logging stack | Nơi tạo JSON event | Điều cần kiểm tra |
| --- | --- | --- |
| JUL | Formatter hoặc adapter tùy chỉnh | Một event/object, escaping, UTF-8 |
| SLF4J + Logback | JSON encoder/layout tương thích | Provider đúng, pattern không chèn text ngoài JSON |
| SLF4J + Log4j 2 | JSON layout/encoder và Appender | Schema/field được giữ, không trùng output |
| Console JSON trong container | Encoder → stdout/stderr → collector | Một physical line/event, ingest đúng |
| File JSONL | Encoder → FileAppender/FileHandler → file | Rotation, newline, collector tailing |

Một file có nội dung gần như JSON nhưng mỗi dòng bị thêm prefix text:

~~~text
2026-11-09 10:15:30 INFO {"event":"order_started"}
~~~

sẽ **không còn là một JSON object nguyên dòng**. Cấu hình pattern, console wrapper hoặc một log agent có thể vô tình thêm prefix/suffix. Hãy kiểm tra **raw bytes/line tại đích mà collector thực sự đọc**, không chỉ xem object được tạo trong Java.

### Exception và stack trace

Nếu backend in stack trace nhiều dòng **ngoài JSON string**, collector đọc từng dòng sẽ coi các dòng stack trace là sự kiện riêng. Để xuất JSONL, stack trace phải là field đã được encode JSON đúng hoặc cấu trúc mà encoder và collector cùng hiểu.

Ví dụ:

~~~json
{"level":"ERROR","event":"payment_failed","errorType":"IllegalStateException","stackTrace":"demo.Service.handle(Service.java:42)\n..."}
~~~

Đây là mẫu minh họa, không phải output mặc định của mọi backend. Dữ liệu exception có thể chứa URL, thông tin người dùng, SQL hoặc nội dung nhạy cảm; kiểm soát cả **nội dung** lẫn **định dạng**.

## 13. Kiểm tra end-to-end đến collector và dashboard

Một unit test ObjectMapper pass **không chứng minh** JSON logging đã hoạt động trong production. Cần thử cả tuyến:

~~~text
Java code
   |
   v
SLF4J/JUL/Log4j 2 Logger
   |
   v
Backend, filter, encoder
   |
   v
stdout/stderr/file
   |
   v
Collector/agent parse JSONL
   |
   v
Index/storage mapping
   |
   v
Query/dashboard/alert
~~~

Quy trình:

1. Phát một event có ID thử nghiệm không nhạy cảm.
2. Xác nhận raw output là **một JSON object trên một dòng**.
3. Parse bằng validator JSON chặt và kiểm tra schema.
4. Xác nhận collector đọc đúng nguồn stdout/file.
5. Truy vấn field event/level/durationMs theo **kiểu dữ liệu thực**.
6. Xác nhận timestamp và timezone được mapping đúng.
7. Kiểm tra retention, quyền xem log và chính sách làm sạch dữ liệu.
8. Quan sát queue drop, backpressure hoặc kích thước event vượt giới hạn.

Nếu không tìm thấy event trong dashboard, nguyên nhân có thể là logger level đã lọc, backend chưa gắn appender, collector không đọc đường dẫn, mapping sai, timestamp nằm ngoài khung thời gian hoặc event bị drop. **JSON syntax pass không loại bỏ các lỗi này.**

## 14. Khi một dòng log không hợp lệ, xử lý thế nào?

Đối với pipeline thu thập log, không nên âm thầm biến mọi input lỗi thành dữ liệu “có vẻ đúng”.

| Chính sách | Lợi ích | Cần cảnh giác |
| --- | --- | --- |
| Reject và tăng bộ đếm lỗi | Giữ contract ingestion sạch | Mất nội dung cần chẩn đoán |
| Gửi vào vùng quarantine/dead-letter được bảo vệ | Có thể điều tra lại lỗi | Tốn storage và chứa dữ liệu nhạy cảm |
| Bỏ qua có cảnh báo | Giữ pipeline tiếp tục xử lý | Có thể mất event lúc sự cố |
| Tạm dừng ingest | Tránh lan rộng dữ liệu sai | Backpressure tới nguồn và nguy cơ backlog |
| Sửa tự động một số lỗi xác định | Giảm thất bại do lỗi known format | Dễ che lỗi gốc hoặc đổi ý nghĩa sự kiện |

**Không tự động cắt dữ liệu sau dấu ngoặc cuối hoặc thêm ngoặc đóng khi một object bị truncate.** Việc đó có thể tạo bản ghi giả hợp lệ với thông tin thiếu hoặc sai.

Lỗi chẩn đoán nên chứa **số dòng, loại lỗi, tên field, phiên bản schema, nguồn** và các thông tin đã được phép ghi. Tránh log lại **toàn bộ dòng JSON lỗi** vì nó có thể chứa token, thông tin cá nhân hoặc payload lớn.

Có thể theo dõi các metric: invalid JSON rate, schema failure rate, parse failures, ingestion drop, event size và field mapping conflicts. Đặt cảnh báo theo tỷ lệ/cửa sổ thời gian phù hợp thay vì báo động vì mọi lỗi nhỏ riêng lẻ.

## 15. JSON có cấu trúc nhưng chứa dữ liệu nhạy cảm

Những ví dụ sau có thể là JSON hợp lệ nhưng **không nên xuất vào log**:

~~~json
{"event":"login_failed","password":"plaintext-password","authorization":"Bearer secret-token"}
~~~

Một kiểm tra syntax/schema thông thường có thể không nhận ra rằng giá trị đã lộ. Cần **data policy** riêng:

- Allowlist field được phép phát log.
- Không log password, token, API key, session cookie, private key hoặc raw authentication header.
- Cân nhắc pseudonym/ID nội bộ đối với dữ liệu cá nhân cần liên hệ.
- Giới hạn độ dài message, request body và stack trace.
- Áp dụng redaction **trước khi serialization** nếu có thể.
- Bảo vệ quyền đọc/retention của file, collector, dashboard và archive.
- Không dán log sản xuất chứa thông tin nhạy cảm vào một JSON validator online.

**JSON escaping giữ đúng cấu trúc, không tự xóa bí mật.** Nếu message chứa secret, serializer vẫn có thể encode và ghi secret đó một cách hoàn toàn hợp lệ.

## 16. Công cụ hỗ trợ và giới hạn

### Python json.tool

~~~bash
python -m json.tool sample.json
~~~

Phù hợp để kiểm tra **một JSON document** và có thể pretty-print, nhưng không mặc nhiên là công cụ kiểm tra file JSONL có **nhiều JSON objects**. Nếu đầu vào là JSONL, cần kiểm tra từng dòng.

### jq

~~~bash
jq -c . sample.json
~~~

Có thể giúp parse và in JSON gọn nếu cài jq. Tuy nhiên jq có thể chấp nhận **nhiều JSON values từ cùng một stream**; vì vậy lệnh chạy thành công **không tự chứng minh mỗi dòng vật lý có đúng một object** hoặc schema đã đúng. Kết hợp với per-line check và schema validation khi yêu cầu JSONL nghiêm ngặt.

### Online JSON validators

Chỉ dùng với dữ liệu giả hoặc đã được làm sạch và được tổ chức cho phép. Không chuyển raw production logs lên dịch vụ bên ngoài khi chưa xác nhận quyền và chính sách dữ liệu.

### JSON Schema

JSON Schema hữu ích với required fields, type, enum, range, nested object và điều kiện giữa các field. Nó không thay thế việc kiểm tra byte stream, JSONL framing, tính đồng bộ thời gian, quyền truy cập log hoặc ingestion end-to-end.

## 17. Bảng lỗi chẩn đoán nhanh

| Triệu chứng | Khả năng cao | Cách xử lý |
| --- | --- | --- |
| Dòng nhìn giống JSON nhưng parser lỗi | Dấu nháy, ngoặc, dấu phẩy hoặc escaping sai | Dùng JSON serializer và parser chuẩn |
| Collector đọc một event thành nhiều dòng | Pretty printing hoặc newline chưa escape | Một object/physical line |
| JSON đúng nhưng query durationMs sai | Kiểu string thay vì number | Kiểm tra schema và storage mapping |
| Hai giá trị level trong một event | Duplicate keys | Bật strict duplicate detection |
| Parser chỉ nhận object đầu | Trailing tokens bị bỏ qua | Bật FAIL_ON_TRAILING_TOKENS |
| Root [] được xem là hợp lệ | JSON đúng nhưng schema yêu cầu object | Kiểm tra root type |
| Không có timestamp | Field bắt buộc thiếu | Schema validation |
| Timestamp nằm ngoài kết quả query | Sai timezone/mapping | Parse offset và chuẩn hóa event time |
| UTF-8 hiển thị ký tự lỗi | Encoding/decoder hoặc stream bị cắt | Kiểm tra bytes và charset |
| NaN/Infinity gây lỗi parser | Non-finite JSON number | Chọn biểu diễn hợp đồng chuẩn |
| JSON hợp lệ nhưng event quá lớn | Ingestion/queue/collector limit | Giới hạn event/message size |
| JSON có nhưng dashboard không thấy field | Collector chưa parse hoặc mapping conflict | Xem raw output và ingest pipeline |
| Stack trace thành các event riêng | Multiline bên ngoài JSON object | Dùng exception JSON encoder |
| Dữ liệu bí mật vẫn có trong log | Không có allowlist/redaction | Loại ở nguồn và kiểm soát retention |
| Java test pass nhưng container fail | Khác config/encoder/charset hoặc nguồn log | Kiểm tra runtime và collector thật |
| JSON Lines có dòng trắng | File/encoder thêm blank lines | Xác định chính sách reject hoặc skip có chủ đích |

## 18. Bài tập tự kiểm tra

**Bài 1.** Xét dữ liệu:

~~~json
{"event":"ready","durationMs":"42"}
~~~

Câu hỏi: nó có đúng JSON syntax không? Có đáp ứng schema yêu cầu durationMs là integer không?

**Đáp án:** cú pháp đúng, nhưng schema sai vì durationMs là string, không phải number.

**Bài 2.** Cho:

~~~json
[{"event":"ready"}]
~~~

Câu hỏi: vì sao validator logging trả INVALID_SCHEMA dù JSON parse được?

**Đáp án:** hợp đồng ví dụ yêu cầu mỗi dòng là một root object của một event; array là kiểu root khác.

**Bài 3.** Cho object có key event lặp lại hai lần.

Câu hỏi: một parser có thể chọn giá trị nào, và tại sao nên bật strict duplicate detection?

**Đáp án:** các triển khai có thể khác nhau, dẫn tới sai khác giữa ứng dụng và collector. Từ chối key trùng tạo quy tắc thống nhất.

**Bài 4.** Một message thật chứa dấu nháy và newline. Cách an toàn để xuất JSONL là gì?

**Đáp án:** dùng serializer; dấu nháy và newline trong string được escape, toàn object còn trên một dòng vật lý.

**Bài 5.** Một JSON object được pretty print ra bốn dòng, collector tách theo từng dòng.

**Đáp án:** object có thể đúng JSON document, nhưng **sai framing JSON Lines** đối với collector đó.

**Bài 6.** JSON syntax pass nhưng timestamp thiếu timezone và durationMs có đơn vị giây thay vì milli giây.

**Đáp án:** schema/semantics có vấn đề; cần timestamp có offset và quy tắc đơn vị nhất quán.

**Bài 7.** Bản ghi JSON được unit test xác nhận hợp lệ nhưng không xuất hiện trên dashboard.

**Đáp án:** kiểm tra backend encoder/output, collector, event timestamp, ingestion drop, mapping và truy vấn, không dừng ở JSON parser.

**Bài 8.** Một JSON event hợp lệ chứa stack trace 10 MB, collector giới hạn 1 MB.

**Đáp án:** có thể bị từ chối hoặc cắt ở ingestion; cần giới hạn độ dài và chính sách exception riêng.

## 19. Checklist kiểm tra JSON logging

- [ ] Xác định rõ hợp đồng **JSON document** hay **JSONL/NDJSON**.
- [ ] Nếu là JSONL, mỗi dòng vật lý chứa một root object/event.
- [ ] Dùng UTF-8 nhất quán và tránh BOM không mong đợi.
- [ ] Serializer/encoder escape đầy đủ dấu nháy, backslash, newline và control characters.
- [ ] Parser không chấp nhận non-standard syntax không được phép.
- [ ] Từ chối duplicate keys khi schema yêu cầu tên field duy nhất.
- [ ] Từ chối trailing tokens sau một event.
- [ ] Root object và các field bắt buộc được xác minh.
- [ ] Số vẫn là number, boolean vẫn là boolean, không ép kiểu âm thầm.
- [ ] Timestamp parse được, có timezone/offset rõ.
- [ ] Field null/missing/empty được xử lý theo contract.
- [ ] Enum, range và đơn vị được kiểm tra.
- [ ] Stack trace/error nằm trong JSON value được encode, không phá framing.
- [ ] Event size và nesting được giới hạn phù hợp.
- [ ] Không xuất secret, token và dữ liệu cá nhân không được phép.
- [ ] Test với malformed JSON, duplicate, trailing, wrong type, missing, array root và input có Unicode/newline.
- [ ] Kiểm tra raw output do **backend thật** ghi, không chỉ object Java.
- [ ] Truy vấn một event thử thành công tại **collector/storage cuối**.
- [ ] Theo dõi số dòng lỗi, parse fail, schema conflict và dropped logs.

## 20. Tài liệu tham khảo

- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): cú pháp JSON, kiểu dữ liệu và Unicode.
- [JSON Lines](https://jsonlines.org/): mỗi JSON value trên một dòng UTF-8.
- [Jackson Databind](https://github.com/FasterXML/jackson-databind): ObjectMapper, JsonNode và data binding.
- [Jackson Core](https://github.com/FasterXML/jackson-core): parser, generator và strict parsing.

**Kết luận:** Trong JSON logging, một event thực sự đáng tin cần **đúng cú pháp JSON, đúng ranh giới một event/dòng, đúng schema/kiểu dữ liệu và đúng pipeline thu thập**. Kiểm tra thêm duplicate keys, trailing tokens, timestamp, Unicode, giới hạn kích thước và bảo mật ngay từ nguồn giúp tránh tình trạng log parse được nhưng không thể truy vấn, hoặc tệ hơn là gây nhầm lẫn khi điều tra sự cố.