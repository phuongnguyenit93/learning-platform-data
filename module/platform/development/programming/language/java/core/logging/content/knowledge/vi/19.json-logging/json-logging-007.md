# Field exception trong JSON logging: ghi lỗi Java thành dữ liệu có cấu trúc

## 1. Field exception là gì?

Trong **JSON logging**, mỗi sự kiện log được biểu diễn thành một **đối tượng JSON** gồm các trường có tên và kiểu dữ liệu rõ ràng. **Field exception** là một hoặc nhiều trường dùng để mô tả ngoại lệ (*exception/Throwable*) xuất hiện khi xử lý một sự kiện: loại lỗi, thông điệp lỗi, stack trace và đôi khi cả nguyên nhân gốc.

Thay vì chỉ ghi một chuỗi dài:

```text
ERROR Checkout failed: java.lang.IllegalStateException: Payment unavailable
```

một JSON log có thể tách dữ liệu ra thành các trường:

```json
{
  "@timestamp": "2026-11-09T10:20:00.000Z",
  "log.level": "ERROR",
  "service.name": "orders-service",
  "message": "Checkout failed",
  "error.type": "java.lang.IllegalStateException",
  "error.message": "Payment unavailable",
  "error.stack_trace": "java.lang.IllegalStateException: Payment unavailable\n\tat demo.OrderService.checkout(OrderService.java:42)"
}
```

Đây là **ví dụ minh họa một schema kiểu Elastic Common Schema (ECS)**; timestamp, tên class và số dòng là dữ liệu ví dụ, không phải output chính xác của chương trình ở phần sau.

Trường `error.stack_trace` là **một JSON string duy nhất**. Trong file JSON Lines, ký tự xuống dòng bên trong stack trace được mã hóa thành `\n`, tab thành `\t` và dấu nháy kép thành `\"` khi cần. Một event vẫn có thể nằm trên **một dòng vật lý**, giúp các công cụ đọc JSON từng dòng mà không nhầm một stack frame thành một bản ghi mới.

**Đừng nhầm field exception với class `java.lang.Exception`.** Field là **một phần của định dạng bản ghi log**; còn `Exception`, `RuntimeException`, `Error` và các subclass đều thuộc họ `Throwable` trong Java. Backend nhận `Throwable` rồi quyết định cách chuyển nó thành các trường JSON.

### Sau bài này, bạn có thể

- Phân biệt `message` của log event với `message` của exception.
- Hiểu `error.type`, `error.message`, `error.stack_trace`; đối chiếu các tên field khác như `exception.type`.
- Truyền nguyên `Throwable` vào logging API thay vì chỉ nối `getMessage()` vào chuỗi.
- Ghi JSON Lines có các trường exception bằng **Log4j2 JsonTemplateLayout** trên Java 17.
- Truy vấn, kiểm tra và xử lý trường lỗi khi không có exception, khi có cause chain hoặc suppressed exceptions.
- Thiết kế schema ổn định, có correlation ID, tránh dữ liệu nhạy cảm và stack trace quá dài.

## 2. Cấu trúc một sự kiện JSON log

Một sự kiện có thể gồm những nhóm field sau:

| Nhóm | Ví dụ field | Ý nghĩa |
| --- | --- | --- |
| Thời gian | `@timestamp` | Lúc sự kiện được tạo |
| Mức độ | `log.level` | INFO, WARN, ERROR... |
| Nguồn | `service.name`, `log.logger` | Service và logger phát sự kiện |
| Ngữ cảnh | `trace.id`, `request.id`, `labels` | Tìm các log thuộc cùng giao dịch |
| Sự kiện | `message` | Mô tả điều ứng dụng đang làm hoặc điều thất bại |
| Ngoại lệ | `error.type` | Tên loại exception |
| Ngoại lệ | `error.message` | Thông điệp của đối tượng Throwable |
| Ngoại lệ | `error.stack_trace` | Stack trace, thường bao gồm các frame và cause |
| Phân loại nghiệp vụ | `error.code` | Mã lỗi ổn định do ứng dụng định nghĩa, nếu có |

**Không phải mọi schema đều dùng các tên này.** Ví dụ, một pipeline theo OpenTelemetry semantic conventions có thể dùng `exception.type`, `exception.message` và `exception.stacktrace`, trong khi một template theo ECS dùng `error.type`, `error.message` và `error.stack_trace`. Dấu chấm trong tên cũng có thể mang ý nghĩa khác nhau khi lưu ở những công cụ tìm kiếm khác nhau.

Vì vậy, cần **chọn một schema thống nhất** cho ứng dụng và hệ thống thu thập. Đừng dựa vào việc tên field nhìn giống nhau rồi kết luận mọi hệ thống sẽ truy vấn, index và lưu nó giống nhau.

### Một điểm rất dễ nhầm: tên có dấu chấm

Hai đối tượng JSON sau đều hợp lệ nhưng **không có cùng cấu trúc**:

```json
{
  "error.type": "java.lang.IllegalStateException"
}
```

```json
{
  "error": {
    "type": "java.lang.IllegalStateException"
  }
}
```

Đối tượng đầu có **một key literal** là `"error.type"`; đối tượng sau có object `error` chứa key `type`. Một số hệ thống indexing có thể ánh xạ các dạng này theo quy tắc riêng, nhưng tại mức JSON thuần chúng là hai cấu trúc khác nhau. Khi phân tích bằng code hoặc `jq`, phải chọn cú pháp truy xuất đúng.

## 3. Field exception khác field message như thế nào?

Một log event có **hai tầng ý nghĩa**:

1. **Message của event** trả lời: *Hoạt động nào thất bại, tại bước nào, với ngữ cảnh nghiệp vụ gì?*
2. **Message của exception** trả lời: *Đối tượng Throwable chứa thông báo nguyên nhân gì?*

Ví dụ:

```java
IllegalStateException failure =
        new IllegalStateException("Payment gateway unavailable");

LOG.error("Checkout for order ORD-42 failed", failure);
```

Đoạn trên giả định `LOG` là logger tương thích và nằm trong một method. Dữ liệu định hướng:

```json
{
  "message": "Checkout for order ORD-42 failed",
  "error.type": "java.lang.IllegalStateException",
  "error.message": "Payment gateway unavailable"
}
```

Cả hai message đều có ích nhưng không thay thế nhau. Nếu chỉ lưu exception message, log có thể thiếu order ID, bước xử lý, endpoint hoặc thông tin service. Nếu chỉ lưu event message, log có thể thiếu exception class và stack trace để xác định vị trí lỗi.

**Không nên ghi exception dưới dạng text bằng cách nối chuỗi:**

```java
LOG.error("Checkout failed: " + failure);
LOG.error("Checkout failed: " + failure.getMessage());
```

Hai lời gọi này chỉ cung cấp một **chuỗi message** cho backend, thường không gắn nguyên đối tượng `Throwable` vào sự kiện. Kết quả là bộ mã hóa JSON không có một exception riêng để trích xuất `type`, `stack_trace` hoặc cause.

**Nên truyền Throwable qua overload tương ứng:**

```java
LOG.error("Checkout failed", failure);
```

Trong Log4j2 và SLF4J thông dụng, overload `error(String, Throwable)` làm rõ ý định. Khi dùng parameterized logging, cũng cần biết quy tắc xử lý đối số Throwable cuối của chính API đang dùng. Ví dụ này dùng overload rõ ràng để tránh nhập nhằng.

## 4. Những trường exception cốt lõi

### 4.1. Type/class name

Field `error.type` hoặc `exception.type` thường ghi tên đầy đủ của class:

```text
java.lang.IllegalArgumentException
java.lang.IllegalStateException
java.io.IOException
java.net.SocketTimeoutException
```

Tên class cho phép gộp các sự kiện theo loại ngoại lệ. Tuy nhiên **exception type không phải error code nghiệp vụ**: một `IllegalArgumentException` có thể có nhiều nguyên nhân và nhiều cách xử lý khác nhau.

Một số hệ thống dùng tên đơn giản `IllegalStateException`, một số ghi đầy đủ package. Nên thống nhất để truy vấn ổn định, tránh một service ghi tên ngắn và service khác ghi tên đầy đủ mà không có quy tắc.

### 4.2. Exception message

`Throwable.getMessage()` trả về thông điệp gắn với Throwable; giá trị này **có thể là `null`**.

Ví dụ:

```java
Throwable a = new IllegalArgumentException("Invalid amount");
Throwable b = new IllegalStateException();

System.out.println(a.getMessage());
System.out.println(b.getMessage());
```

**Stdout chính xác** khi chạy đoạn này trong method Java thích hợp:

```text
Invalid amount
null
```

Dòng `null` là kết quả `println(Object)`/nối chuỗi khi tham số null, không có nghĩa mọi JSON encoder sẽ xuất literal string `"null"`. Tùy schema và serializer, một field exception message có thể bị **bỏ qua**, trở thành JSON `null`, hoặc xử lý theo quy tắc khác. Không ép kiểu nó thành một chuỗi bịa ra nếu hệ thống cần giữ ngữ nghĩa thiếu dữ liệu.

### 4.3. Stack trace

Stack trace mô tả các frame của luồng thực thi, thường gồm class, method, file và số dòng khi có. Khi có ngoại lệ bao bọc (*wrapped exception*), stack trace dạng text thường có các đoạn **`Caused by:`** và có thể có **`Suppressed:`**.

Trong JSON có hai cách thể hiện thông dụng:

**Dạng chuỗi:**

```json
{
  "error.stack_trace": "java.lang.IllegalStateException: Payment unavailable\n\tat demo.PaymentService.pay(PaymentService.java:30)\nCaused by: java.lang.IllegalArgumentException: Rejected"
}
```

**Dạng mảng frame có cấu trúc:**

```json
{
  "exception": {
    "type": "java.lang.IllegalStateException",
    "frames": [
      {
        "class": "demo.PaymentService",
        "method": "pay",
        "file": "PaymentService.java",
        "line": 30
      }
    ]
  }
}
```

Hai đoạn đều là **schema minh họa**, không phải JSON mà mọi Log4j2/Logback encoder buộc phải sinh. Dạng string dễ đọc/hiển thị trong UI; dạng object/array thuận tiện lọc theo frame, nhưng chi phí lưu trữ, số trường và yêu cầu parser khác nhau.

Không gửi toàn bộ đối tượng `Throwable` cho JSON serializer chung mà không có quy tắc rõ ràng: nội bộ class Throwable, cause chain, suppressed exception, cyclic reference hoặc các thuộc tính riêng có thể làm output không ổn định. **Logging layout/encoder chuyên dụng** hiểu Throwable thường đáng tin cậy hơn việc tùy tiện gọi `ObjectMapper.writeValueAsString(exception)`.

### 4.4. Root cause và cause chain

Java có thể bao bọc nguyên nhân:

```java
Throwable cause =
        new IllegalArgumentException("Gateway rejected");
Throwable outer =
        new IllegalStateException("Payment unavailable", cause);
```

Khi ghi `outer`:

- **Outer type:** `java.lang.IllegalStateException`.
- **Outer message:** `Payment unavailable`.
- **Root-cause type:** `java.lang.IllegalArgumentException`.
- **Root-cause message:** `Gateway rejected`.

Nếu dùng một trường `error.type`, phải xác định nó đại diện cho exception **ngoài cùng** hay **nguyên nhân sâu nhất**. Các hệ thống khác nhau có thể chọn khác nhau. Nên bổ sung field riêng như `root_cause.type` nếu cần phân tích root cause, thay vì thay ý nghĩa của `error.type` giữa các service.

**Throwable.getCause()` trả về cause trực tiếp**, có thể null. Cause chain không nhất thiết chỉ có hai tầng; khi tự duyệt chain phải tránh vòng tham chiếu không mong muốn và đặt giới hạn độ sâu.

### 4.5. Suppressed exceptions

Các tác vụ `try-with-resources` có thể gắn exception phát sinh khi `close()` thành một **suppressed exception**:

```java
Throwable error = new IllegalStateException("Primary failure");
error.addSuppressed(new IllegalArgumentException("Cleanup failure"));
```

Một stack trace stringified theo cơ chế hỗ trợ của backend có thể chứa đoạn `Suppressed:`. Nhưng **không mặc định** JSON encoder sẽ tạo riêng một mảng `suppressed`; điều đó phải được schema hoặc resolver hỗ trợ/cấu hình. Đừng tự loại bỏ suppressed information nếu cần hiểu nguyên nhân shutdown hoặc cleanup lỗi.

## 5. JSON Lines: một exception không được phá vỡ một record

Một file JSON Lines (thường có đuôi `.jsonl` hoặc `.ndjson`) chứa **một JSON object trên mỗi dòng**. Khi exception stack trace có nhiều dòng, serializer phải mã hóa các ký tự đặc biệt bên trong JSON string.

Ví dụ hợp lệ, toàn bộ là **một dòng vật lý**:

```json
{"log.level":"ERROR","message":"Order failed","error.stack_trace":"java.lang.IllegalStateException: Failed\n\tat demo.OrderService.place(OrderService.java:17)"}
```

Không làm kiểu này trong một file JSON Lines:

```text
{"message":"Order failed","error.stack_trace":"java.lang.IllegalStateException: Failed
    at demo.OrderService.place(OrderService.java:17)"}
```

Dạng thứ hai có **ký tự newline thực bên trong một JSON string chưa được escape**, làm JSON không hợp lệ và khiến collector tail file có thể hiểu stack frame thành một dòng mới.

JSON serializer chuyên dụng xử lý đúng:

- Dấu nháy kép `"` → escape `\"` khi cần.
- Dấu gạch chéo ngược `\` → escape `\\` khi cần.
- Tab, newline và ký tự điều khiển → các escape JSON tương ứng.
- Unicode → xuất hoặc escape đúng UTF-8/JSON theo cấu hình.

**Không tự lắp JSON bằng phép nối chuỗi Java** nếu message có dữ liệu từ client hoặc exception. Một input chứa dấu nháy, newline hoặc ký tự điều khiển có thể làm sai schema, phá log collector hoặc tạo giả dòng log. Dùng layout/encoder có quy tắc escape được kiểm chứng.

## 6. Ví dụ Maven + Java 17: Log4j2 JSON Template Layout

Ví dụ này dùng **Apache Log4j2** và `JsonTemplateLayout`, tạo hai sự kiện: INFO bình thường và ERROR có `Throwable` chứa cause. File đầu ra được ghi ở dạng JSON Lines theo mẫu ECS. Không cần tự serialize exception trong mã nghiệp vụ.

### 6.1. Cấu trúc dự án

```text
exception-json-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── JsonExceptionDemo.java
        └── resources/
            └── log4j2.xml
```

### 6.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>exception-json-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-api</artifactId>
            <version>2.24.3</version>
        </dependency>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-core</artifactId>
            <version>2.24.3</version>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-layout-template-json</artifactId>
            <version>2.24.3</version>
            <scope>runtime</scope>
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

**Vì sao cần ba dependency?**

- `log4j-api`: mã Java import `LogManager` và `Logger`.
- `log4j-core`: backend cung cấp appender/configuration.
- `log4j-layout-template-json`: module chứa `JsonTemplateLayout` và các event template như `EcsLayout.json`.

Ba version được ghim thống nhất chỉ để bài học có một cấu hình xác định. Chúng **không được khẳng định là bản mới nhất** hoặc lựa chọn production tối ưu tại mọi thời điểm. Khi triển khai thật, cập nhật phiên bản được duy trì, các bản vá bảo mật và tránh trộn Log4j2 artifact khác major/minor tùy tiện.

### 6.3. Tệp src/main/resources/log4j2.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <File name="JsonFile"
              fileName="logs/events.jsonl"
              append="false">
            <JsonTemplateLayout
                    eventTemplateUri="classpath:EcsLayout.json"/>
        </File>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="JsonFile"/>
        </Root>
    </Loggers>
</Configuration>
```

Các ý chính:

1. `File` là appender ghi vào `logs/events.jsonl` tính từ thư mục làm việc.
2. `append="false"` chỉ dành cho **demo độc lập** để file được ghi lại qua mỗi lần chạy, dễ so sánh. **Không dùng cho log vận hành cần giữ lịch sử**, trừ khi đã có chính sách archive khác.
3. `JsonTemplateLayout` sinh JSON; template `EcsLayout.json` được đóng gói trong module JSON Template Layout, không cần tự tạo tệp JSON template.
4. Layout dùng delimiter giữa các event, mặc định là newline theo nền tảng. Một event được mã hóa thành **một JSON record**, stack trace bên trong string được escape.
5. `Root level="info"` cho phép INFO/WARN/ERROR... nhưng không phát DEBUG/TRACE qua root ở cấu hình này.
6. Không gắn Console appender để stdout chính của demo dễ kiểm chứng.
7. Log4j2 Core và template-layout module phải có mặt ở **runtime**; chỉ thêm `log4j-api` sẽ không cung cấp tính năng này.

### 6.4. Tệp src/main/java/demo/JsonExceptionDemo.java

```java
package demo;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.logging.log4j.ThreadContext;

public final class JsonExceptionDemo {
    private static final Logger LOG =
            LogManager.getLogger(JsonExceptionDemo.class);

    public static void main(String[] args) {
        ThreadContext.put("requestId", "REQ-204");

        try {
            LOG.info("JSON exception demo started");

            try {
                throw new IllegalArgumentException("Gateway rejected");
            } catch (IllegalArgumentException cause) {
                throw new IllegalStateException(
                        "Payment unavailable", cause);
            }
        } catch (IllegalStateException exception) {
            LOG.error("Order ORD-42 failed", exception);
        } finally {
            ThreadContext.remove("requestId");
        }

        System.out.println("demo-finished");
    }
}
```

Giải thích đường sự kiện:

- Event `INFO` có `message` nhưng **không có Throwable**.
- Event `ERROR` có event message `Order ORD-42 failed` và nguyên `IllegalStateException`.
- Exception ngoài cùng có message `Payment unavailable`, cause bên trong là `IllegalArgumentException` với message `Gateway rejected`.
- `ThreadContext` thêm `requestId` cho các event trong cùng luồng; template ECS có thể biểu diễn context map dưới `labels` tùy template cụ thể.
- Khối `finally` xóa context sau khi ghi để tránh thông tin request bị rò sang công việc khác trong một thread được tái sử dụng.
- `System.out.println` không đi qua Log4j2; nó tạo stdout riêng.

### 6.5. Chạy chương trình

Từ thư mục `exception-json-demo`, với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.JsonExceptionDemo
```

**Stdout do riêng class `JsonExceptionDemo` tạo ra, chính xác:**

```text
demo-finished
```

Các sự kiện logger đi vào `logs/events.jsonl`, không xuất ra console trong cấu hình demo. Maven/plugin hoặc hệ thống khác có thể hiển thị thông báo riêng; đó không phải output của `System.out.println` trong class.

**Kết quả cần kiểm tra trong file**: hai JSON object tách bởi newline, một INFO và một ERROR. Bản ERROR có các field exception kiểu ECS, điển hình:

```json
{
  "log.level": "ERROR",
  "message": "Order ORD-42 failed",
  "error.type": "java.lang.IllegalStateException",
  "error.message": "Payment unavailable",
  "error.stack_trace": "java.lang.IllegalStateException: Payment unavailable\nCaused by: java.lang.IllegalArgumentException: Gateway rejected"
}
```

Đây là **minh họa những trường đáng quan sát**, không phải output đầy đủ hoặc chuỗi JSON nguyên văn từ template. File thực còn timestamp, logger, thread, context và **nhiều frame stack trace**; `error.stack_trace` chứa chuỗi đầy đủ hơn ví dụ rút gọn trên. Template không được yêu cầu pretty-print thành nhiều dòng: nội dung `events.jsonl` là JSON Lines.

Với event INFO, không có Throwable để lấy `error.type`/`error.message`/`error.stack_trace`. Các field đó có thể **vắng mặt hoặc được biểu diễn theo quy tắc null của template/encoder**, không nên kỳ vọng một chuỗi mặc định `"No exception"`.

### 6.6. Xem JSON Lines

Trên Linux/macOS:

```bash
cat logs/events.jsonl
```

Trên PowerShell:

```powershell
Get-Content logs/events.jsonl
```

Nếu có `jq`, có thể xem riêng những field exception của event ERROR:

```bash
jq -c 'select(."log.level" == "ERROR") |
       {message: .message, type: ."error.type", cause: ."error.message"}' \
       logs/events.jsonl
```

Kết quả mong đợi của **những field được chọn**, nếu template xuất đúng các field như trên:

```json
{"message":"Order ORD-42 failed","type":"java.lang.IllegalStateException","cause":"Payment unavailable"}
```

Lệnh dùng `."error.type"` vì trong JSON thuần đó là **key literal chứa dấu chấm**. Viết `.error.type` sẽ chỉ đúng với schema nested `{"error":{"type":"..."}}`, không phải cùng cấu trúc.

Kiểm tra từng dòng có parse được thành JSON:

```bash
jq -c . logs/events.jsonl
```

Nếu lệnh báo lỗi JSON, kiểm tra file thực có bị trộn log text, bị cắt ở giữa lúc ghi, hoặc ghi nhiều dòng vật lý không được escape đúng hay không.

## 7. Log4j2 exception resolver: kiểm soát field tùy schema

`JsonTemplateLayout` cho phép định nghĩa event template riêng, không nhất thiết dùng mẫu ECS có sẵn. Các resolver dành cho Throwable trong Log4j2 bao gồm:

- `exception`: lấy dữ liệu từ `LogEvent.getThrown()`, tức exception ngoài cùng.
- `exceptionRootCause`: lấy dữ liệu từ exception nguyên nhân sâu nhất.
- `field="className"`: tên class.
- `field="message"`: `Throwable.getMessage()`.
- `field="stackTrace"`: stack trace theo cách biểu diễn được cấu hình.

Ví dụ fragment trong **event template JSON**, không phải một dòng log đầu ra:

```json
{
  "exception": {
    "type": {
      "$resolver": "exception",
      "field": "className"
    },
    "message": {
      "$resolver": "exception",
      "field": "message"
    },
    "stack_trace": {
      "$resolver": "exception",
      "field": "stackTrace",
      "stackTrace": {
        "stringified": true
      }
    },
    "root_cause_type": {
      "$resolver": "exceptionRootCause",
      "field": "className"
    },
    "root_cause_message": {
      "$resolver": "exceptionRootCause",
      "field": "message"
    }
  }
}
```

Các key `exception.type`, `exception.message` trong ví dụ này là **nested object do bạn tự định nghĩa**, không tự biến thành ECS `error.type`. Muốn dùng schema ECS, hãy chọn key tương ứng trong event template hoặc dùng mẫu `EcsLayout.json`.

### 7.1. Một template hoàn chỉnh tối giản

Nếu muốn kiểm soát tên trường rõ ràng, tạo file `src/main/resources/ExceptionLayout.json`:

```json
{
  "timestamp": {
    "$resolver": "timestamp",
    "pattern": {
      "format": "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",
      "timeZone": "UTC"
    }
  },
  "level": {
    "$resolver": "level",
    "field": "name"
  },
  "logger": {
    "$resolver": "logger",
    "field": "name"
  },
  "message": {
    "$resolver": "message",
    "stringified": true
  },
  "error.type": {
    "$resolver": "exception",
    "field": "className"
  },
  "error.message": {
    "$resolver": "exception",
    "field": "message"
  },
  "error.stack_trace": {
    "$resolver": "exception",
    "field": "stackTrace",
    "stackTrace": {
      "stringified": true
    }
  },
  "error.root_cause_type": {
    "$resolver": "exceptionRootCause",
    "field": "className"
  }
}
```

Thay layout trong `log4j2.xml` của demo bằng:

```xml
<JsonTemplateLayout
        eventTemplateUri="classpath:ExceptionLayout.json"/>
```

Đây là **biến thể tùy chọn** sau khi chạy demo mặc định. Các trường tên `error.root_cause_type` là sự lựa chọn của **schema riêng trong bài**, không mặc nhiên là tên chuẩn ECS. Với exception ngoài cùng và root cause khác nhau, phần này hữu ích để so sánh hai lớp lỗi.

Tùy các resolver và cấu hình, trường trả về null có thể bị lược bỏ hoặc được biểu diễn theo quy tắc layout. Luôn kiểm chứng event INFO và ERROR thật, thay vì giả định mọi key đều xuất khi không có Throwable.

### 7.2. Stack trace string hay mảng frame?

Resolver `exception` với `field="stackTrace"` có thể tạo **mảng các stack frame**. Nếu muốn giữ nó thành chuỗi chứa các dòng `at ...` và `Caused by:`, dùng:

```json
{
  "$resolver": "exception",
  "field": "stackTrace",
  "stackTrace": {
    "stringified": true
  }
}
```

Đừng quên phân biệt phần cấu hình resolver với **giá trị JSON đã được resolve**. Trong file template, `"$resolver"` là chỉ thị của Log4j2; trong file sự kiện đầu ra, bạn thấy string hoặc mảng đã được tạo, không phải một đối tượng chứa `"$resolver"`.

Một số phiên bản tài liệu cũ có cú pháp `"stringified": true` ở cấp resolver. Trong tài liệu Log4j2 hiện hành, nên ưu tiên cấu hình `stackTrace.stringified` như trên và kiểm tra phiên bản đang triển khai.

## 8. Các API khác: JUL, SLF4J và Logback

Đích JSON không được quyết định chỉ bằng API gọi logger. Các API có cách gắn Throwable tương ứng.

| API | Ví dụ ghi exception | Ai quyết định JSON field? |
| --- | --- | --- |
| JUL | `logger.log(Level.SEVERE, "Failed", ex)` | Handler/Formatter, hoặc backend/bridge đang nhận |
| SLF4J | `log.error("Failed", ex)` | Provider/backend, thường Logback/Log4j2 |
| Log4j2 API | `LOG.error("Failed", ex)` | Log4j2 Core Layout, ví dụ JsonTemplateLayout |
| `System.err.println` | Chỉ in text | Không tự có schema JSON |

### 8.1. JUL LogRecord có Throwable riêng

Trong Java Util Logging:

```java
try {
    Integer.parseInt("bad");
} catch (NumberFormatException ex) {
    logger.log(java.util.logging.Level.SEVERE,
            "Failed to parse integer", ex);
}
```

Đây là snippet trong một method đã có `java.util.logging.Logger logger`. `LogRecord` giữ ngoại lệ qua `getThrown()`. Một formatter được thiết kế cho JSON có thể đọc trường này để mã hóa thành các key riêng. **JUL SimpleFormatter mặc định tạo text, không tự tạo JSON**; phải dùng formatter/handler thích hợp hoặc bridge tới backend có JSON encoder.

### 8.2. SLF4J không tự quyết định field exception

`org.slf4j.Logger` cung cấp các overload gắn Throwable, ví dụ `log.error("Failed", ex)`. Nhưng `slf4j-api` riêng lẻ không biết output là console text, file JSON hay nơi khác. Một ứng dụng dùng SLF4J + Logback có thể có `logback.xml` và JSON encoder phù hợp; một ứng dụng dùng SLF4J + Log4j2 cần đúng provider tương thích.

Nếu chỉ thêm `slf4j-api` mà thiếu provider, có thể không có log. Nếu có nhiều provider, schema runtime có thể khác dự kiến. Luôn xác định backend thực trước khi tìm lý do field exception không xuất.

### 8.3. Logback: mô hình tương đương nhưng không cùng XML

Trong Logback Classic, lời gọi `log.error("Checkout failed", ex)` cho backend biết có Throwable. Việc xuất `exception.class`, `exception.message`, `stack_trace` hoặc những field khác phụ thuộc encoder JSON được chọn, phiên bản và cấu hình. **Không dùng `JsonTemplateLayout` của Log4j2 trong `logback.xml`**, vì đây là plugin dành cho Log4j2 Core.

Một đoạn Logback với `PatternLayoutEncoder` và `%ex` có thể in stack trace dạng text, nhưng không tự biến record thành JSON hợp lệ:

```xml
<encoder>
    <pattern>%d %-5level %logger - %msg%n%ex</pattern>
</encoder>
```

Đây là **mảnh cấu hình Logback**. Để có JSON, cần encoder/formatter hỗ trợ JSON và cấu hình field mapping cụ thể. Các lựa chọn encoder và schema có thể khác theo phiên bản; không sao chép tên field từ Log4j2 rồi giả định Logback tạo y hệt.

## 9. Root cause và suppressed trong JSON: thiết kế có chủ đích

Một exception Java có thể chứa:

```text
IllegalStateException: Payment unavailable
  caused by IllegalArgumentException: Gateway rejected
  suppressed IOException: Cleanup failed
```

Một JSON schema có thể lựa chọn một trong các dạng:

**Chỉ lưu stack trace string:** đủ để đọc/điều tra nhưng khó query riêng từng cause.

**Lưu thêm root cause fields:**

```json
{
  "error.type": "java.lang.IllegalStateException",
  "error.message": "Payment unavailable",
  "error.root_cause_type": "java.lang.IllegalArgumentException",
  "error.root_cause_message": "Gateway rejected"
}
```

**Dùng mảng cause có cấu trúc nếu hệ thống thật sự cần:**

```json
{
  "exception": {
    "type": "java.lang.IllegalStateException",
    "causes": [
      {
        "type": "java.lang.IllegalArgumentException",
        "message": "Gateway rejected"
      }
    ]
  }
}
```

Đây là **ví dụ schema tùy biến**. Các backend không tự bảo đảm xuất `causes[]` hoặc `suppressed[]` nếu chưa có resolver/encoder hỗ trợ. Khi tự xây schema cần xác định:

1. Dùng outer exception, root cause hay cả hai cho việc nhóm lỗi?
2. Giới hạn số tầng cause/suppressed để tránh event quá lớn?
3. Cách biểu diễn class name, message null và stack frame thiếu line number?
4. Một exception không có cause sẽ thiếu key, để null hay mảng rỗng?
5. Dữ liệu cause message có chứa secret/PII không?
6. Các service khác nhau có áp dụng cùng schema không?

**Không xóa mất cause hoặc suppressed chỉ để JSON ngắn hơn** nếu hệ thống đang điều tra lỗi I/O/shutdown. Nhưng cũng không ghi vô hạn dữ liệu: đặt giới hạn độ dài hợp lý và có chính sách truncation.

## 10. Exception không có message, checked exception và Error

Trong Java, ngoại lệ không nhất thiết có message; một số loại có thể mang message động hoặc được bọc bởi exception khác. Kiểu `Throwable` bao gồm cả `Error` và `Exception`; nhiều logging API nhận `Throwable` chứ không chỉ `Exception`.

Ví dụ:

```java
Throwable failure = new IllegalStateException();
System.out.println(failure.getClass().getName());
System.out.println(failure.getMessage());
```

**Stdout khi chạy trong method Java:**

```text
java.lang.IllegalStateException
null
```

Khi message là null, JSON encoder phải xử lý giá trị thiếu đúng kiểu. **Không đổi null thành string `"null"` chỉ để thuận tiện truy vấn** vì chúng có ngữ nghĩa khác nhau.

Cũng cần tránh log lỗi hai lần: cùng một Throwable có thể được log ERROR tại service và lại được log ERROR ở HTTP handler, khiến pipeline thu thập hai sự kiện độc lập với cùng stack trace. Hãy chọn boundary phù hợp nơi exception được xử lý hoặc chuyển thành response, đặt event message rõ ràng và giữ cause chain.

Khi một lỗi đã được xử lý như tình huống nghiệp vụ bình thường (ví dụ đầu vào không hợp lệ), không phải lúc nào cũng cần stack trace ở mức ERROR. Level phải phù hợp mức độ ảnh hưởng, chính sách vận hành và số lượng lỗi dự kiến.

## 11. Truy vấn field exception trong log aggregation

Lợi ích chính của JSON logging là **truy vấn theo trường**, không phải quét text stack trace toàn cục.

Giả sử hệ thống lưu các trường:

```json
{
  "service.name": "orders-service",
  "log.level": "ERROR",
  "error.type": "java.lang.IllegalStateException",
  "error.message": "Payment unavailable",
  "error.code": "PAYMENT_UNAVAILABLE",
  "request.id": "REQ-204"
}
```

Có thể xây các câu hỏi:

- Service nào có nhiều `error.type=java.net.SocketTimeoutException`?
- Một `request.id` xuất hiện ở những event nào trước lỗi?
- Tỷ lệ ERROR theo phiên bản triển khai có tăng không?
- `error.code=PAYMENT_UNAVAILABLE` tăng theo thời gian hay chỉ ở một instance?
- Exception type nào có tần suất cao nhưng chưa có alert?

**Không nhóm tất cả lỗi chỉ bằng `error.message`**: message có thể chứa order ID, URL, địa chỉ hoặc giá trị động, tạo số lượng nhóm rất lớn (*high cardinality*). Những trường tương đối ổn định như `service.name`, `error.type`, `error.code` hoặc fingerprint được kiểm soát thường phù hợp hơn để tổng hợp.

Trong `jq`, khi field là key literal:

```bash
jq -r 'select(."log.level" == "ERROR") | ."error.type"' logs/events.jsonl
```

Với schema nested `{"error":{"type":"..."}}`, câu truy vấn khác:

```bash
jq -r 'select(.level == "ERROR") | .error.type' logs/events.jsonl
```

Cả hai lệnh đều là **mẫu truy vấn phụ thuộc schema**; đừng dùng ngẫu nhiên rồi kết luận dữ liệu không tồn tại. Trong Elasticsearch/OpenSearch, Loki, Splunk, Datadog hoặc collector khác, cách index và cú pháp query cũng khác nhau.

## 12. Field exception và correlation ID

Một event lỗi có stack trace nhưng thiếu ngữ cảnh có thể vẫn khó điều tra khi nhiều request được xử lý đồng thời. Vì vậy nên kết hợp những trường exception với **correlation ID**:

```json
{
  "service.name": "orders-service",
  "request.id": "REQ-204",
  "trace.id": "8c9e89f60b014eee9bc2c6f4d6b43d16",
  "log.level": "ERROR",
  "message": "Order failed",
  "error.type": "java.lang.IllegalStateException"
}
```

Đây là **dữ liệu minh họa**. Cùng một request ID giúp tìm event trước và sau lỗi; `trace.id` có thể liên kết với distributed tracing khi hệ thống tracing đã được tích hợp.

Trong Log4j2, `ThreadContext.put("requestId", value)` có thể thêm một trường MDC/context. Tuy nhiên:

- Context map không tự truyền sang mọi thread khác hoặc task của `CompletableFuture`.
- Nếu sử dụng thread pool, cần **dọn context** trong `finally` hoặc phạm vi tự đóng thích hợp.
- Template/encoder phải được cấu hình để xuất những key cần thiết.
- Ghi trace ID trong JSON **không tự tạo span hay distributed trace**.
- Không dùng dữ liệu nhạy cảm như token hoặc user session làm correlation ID.

Một exception log lớn có thể bị collector cắt, còn event trước đó chứa ngữ cảnh cần thiết. Vì vậy ngoài stack trace, nên có các mốc nghiệp vụ và ID có kiểm soát giúp lần theo quá trình xử lý.

## 13. Chi phí và dung lượng: không phải lúc nào cũng cần toàn bộ stack trace

Một stack trace có thể chiếm hàng nghìn hoặc hàng chục nghìn ký tự. Khi lỗi xuất hàng trăm lần mỗi giây, lưu nguyên trace cho mọi event làm tăng:

- CPU do tạo/format stack trace.
- Bộ nhớ và allocation khi serialize.
- I/O đến file, stdout hoặc network sink.
- Dung lượng và chi phí index/search.
- Khả năng bị truncation ở collector hoặc giới hạn kích thước event.
- Sự nhiễu của dashboard/alert nếu cùng một lỗi lặp lại liên tục.

Một số cách tối ưu:

1. **Chọn level đúng:** lỗi được xử lý thường xuyên có thể chỉ cần WARN hoặc INFO tùy ngữ nghĩa.
2. **Ghi exception tại boundary hợp lý:** không tạo ba ERROR stack traces ở ba tầng khi chỉ cần một.
3. **Thêm error code ổn định:** hỗ trợ tổng hợp mà không phải đọc toàn bộ stack.
4. **Dùng sampling/rate limit khi phù hợp:** phải rõ trường hợp nào được giữ đầy đủ, đặc biệt với sự cố hiếm gặp hoặc yêu cầu audit.
5. **Giới hạn độ dài có chủ đích:** nếu phải truncate stack trace, nên hiển thị dấu hiệu truncation và giữ đủ phần nguyên nhân hữu ích.
6. **Giám sát mức cắt của collector:** layout có thể tạo JSON hợp lệ nhưng collector giới hạn số byte làm record hỏng hoặc mất field cuối.
7. **Tách sự kiện giao dịch quan trọng khỏi log chẩn đoán:** logging không thay thế lưu trữ giao dịch bền vững.

Với Log4j2 `JsonTemplateLayout`, cấu hình `stackTraceEnabled` có thể điều khiển việc sử dụng stack trace; giá trị mặc định của module thông dụng cho phép stack trace. Một số giới hạn như `maxStringLength` áp dụng cho giá trị string, nhưng **không nhất thiết là giới hạn toàn bộ JSON object**. Hãy kiểm tra tài liệu đúng phiên bản và output thực tế khi thay đổi.

## 14. Bảo mật và quyền riêng tư của field exception

**Exception message và stack trace rất dễ làm lộ dữ liệu.** Một exception từ HTTP client, JDBC, file system hoặc thư viện xác thực có thể mang:

- URL với query string chứa token.
- Đường dẫn filesystem nội bộ, hostname hoặc tên tài khoản.
- SQL statement, tên bảng hoặc dữ liệu đầu vào.
- Header, cookie hoặc payload request.
- Thông tin về cách cấu trúc ứng dụng và phiên bản thư viện.

Ngay cả khi `message` của log được viết an toàn, **`error.message` hoặc `error.stack_trace` vẫn có thể chứa dữ liệu nhạy cảm** từ Throwable do thư viện khác tạo.

Các nguyên tắc bảo vệ:

- Không đưa secret, password, access token, API key, session cookie hay dữ liệu thẻ vào exception message nếu có thể tránh.
- Không lưu nguyên request body và stack trace chỉ để debug một lỗi thông thường.
- Khi phải log thông tin nhận diện, dùng ID được phép và đã kiểm soát, tránh dữ liệu cá nhân không cần thiết.
- Cân nhắc redaction/masking ở nguồn và pipeline, nhưng **kiểm thử cả event message, error message, root cause và stack trace**.
- Đặt quyền truy cập và retention cho file JSON, log collector, kho tìm kiếm và dashboard.
- Bảo đảm encoding/JSON escaping đúng để input không tin cậy không giả mạo field hoặc bản ghi mới.
- Không để dữ liệu exception có thể truy vấn công khai chỉ vì ứng dụng gửi log lên stdout.
- Nếu cần lưu stack trace đầy đủ cho sự cố nghiêm trọng, bảo vệ nó tương xứng với dữ liệu nội bộ nhạy cảm.

**Không mặc định thay `getMessage()` bằng `getClass().getSimpleName()` là đủ bảo mật.** Root cause, stack trace và các context field vẫn có thể lộ dữ liệu. Thiết kế schema và data minimization phải xét toàn bộ event.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| JSON có `message` nhưng không có `error.type` | Chỉ ghi chuỗi, không truyền nguyên Throwable | Dùng overload nhận Throwable; xem encoder |
| Có `error.type` nhưng không có `error.stack_trace` | Layout tắt stack trace hoặc không cấu hình xuất trường | Kiểm tra `stackTraceEnabled`/event template |
| `error.message` bằng null | Throwable không có message | Xử lý null/missing đúng schema, không ép thành string giả |
| Một lỗi xuất hai bản ghi JSON | Cùng exception bị log ở nhiều tầng hoặc additivity/appender trùng | Kiểm tra đường đi và nơi ghi lỗi |
| File JSONL không parse được | Dòng text xen vào hoặc stack trace chứa newline không escape | Dùng JSON encoder thật và kiểm tra từng dòng |
| Truy vấn `.error.type` không có kết quả | JSON chứa literal key `"error.type"`, không phải nested object | Dùng `."error.type"` hoặc truy vấn đúng schema |
| Error message có dữ liệu nhạy cảm | Exception được tạo với URL/query/token hoặc dữ liệu client | Redact/giảm dữ liệu ở nguồn và sink |
| Group theo message có hàng nghìn nhóm | Message chứa ID hoặc URL động | Group theo type/code/fingerprint ổn định |
| Cause không xuất riêng | Template chỉ có resolver `exception`, chưa có `exceptionRootCause` | Bổ sung root cause fields nếu cần |
| Supressed exception không thấy thành field | Encoder chưa hỗ trợ mảng suppressed riêng | Kiểm tra stringified stack trace hoặc schema tùy chỉnh |
| File `events.jsonl` không được tạo | Sai path, quyền ghi, config không được nạp, thiếu Core | Kiểm tra runtime classpath, appender/status log |
| Plugin `JsonTemplateLayout` không được nhận | Thiếu module `log4j-layout-template-json` hoặc version lệch | Thêm dependency phù hợp, kiểm tra lỗi startup |
| Code log qua SLF4J nhưng không có field exception | Provider/backend thực khác dự kiến | Kiểm tra dependency tree và runtime provider |
| JSON bị cắt ngang ở cuối | Process crash, file/collector limit, buffer chưa flush | Kiểm tra lifecycle, kích thước, parser và pipeline |
| Field names không giống tài liệu | Đang dùng template khác hoặc schema backend khác | Xác định chính xác `eventTemplateUri` và file config |

### Checklist chẩn đoán

1. Mã đang gọi **API nào**: JUL, SLF4J, Log4j2 hay in text trực tiếp?
2. Có **truyền nguyên Throwable** vào logger không?
3. Backend/provider thực tế là gì, có hỗ trợ JSON layout/encoder không?
4. Schema đang dùng định nghĩa `error.type`, `exception.type` hay field khác?
5. File cấu hình và template JSON có được nạp đúng từ runtime classpath không?
6. Có event bình thường không Throwable để kiểm tra cách bỏ/null trường?
7. Với exception có cause, outer type và root-cause type có đúng không?
8. Stack trace có còn các frame/cause cần thiết, có bị truncate không?
9. Mỗi dòng trong JSONL có parse hợp lệ không?
10. Các field exception, MDC và file log có làm lộ thông tin không?
11. Event ERROR có được gắn request/trace ID khi yêu cầu điều tra không?
12. Trước khi kết luận QA, kiểm tra output của **đúng phiên bản đã deploy**, không chỉ dựa vào cấu hình dự kiến.

## 16. Tự kiểm tra kiến thức

**Câu 1.** Vì sao field exception hữu ích hơn việc chỉ ghi `exception.toString()` trong message?  
**Đáp án:** Nó tách type/message/stack trace thành các trường có thể tìm kiếm, lọc, nhóm và định dạng độc lập.

**Câu 2.** `message` của event và `error.message` khác nhau ra sao?  
**Đáp án:** Event message mô tả ngữ cảnh thao tác; exception message là thông báo từ `Throwable.getMessage()`. Chúng có thể khác nhau.

**Câu 3.** Gọi `LOG.error("Failure: " + ex.getMessage())` có chắc tạo field `error.type` không?  
**Đáp án:** Không. Nó chỉ cung cấp chuỗi; nên truyền nguyên Throwable bằng overload phù hợp.

**Câu 4.** Một stack trace nhiều dòng có thể được lưu trong JSON Lines không?  
**Đáp án:** Có. Serializer escape newline thành `\n` bên trong JSON string để một event vẫn là một dòng vật lý.

**Câu 5.** `"error.type"` và `{"error":{"type":...}}` có cùng cấu trúc JSON không?  
**Đáp án:** Không. Một dạng dùng key literal chứa dấu chấm, dạng kia là object lồng nhau.

**Câu 6.** Nếu Throwable không có message, có nên ghi `"error.message":"null"` không?  
**Đáp án:** Không nên tùy tiện. Null/missing có ngữ nghĩa riêng; tuân thủ schema/encoder.

**Câu 7.** `exceptionRootCause` của Log4j2 giúp gì?  
**Đáp án:** Lấy dữ liệu từ Throwable sâu nhất trong cause chain, giúp phân biệt lỗi bao bọc bên ngoài với nguyên nhân bên trong.

**Câu 8.** Vì sao `error.stack_trace` có thể nguy hiểm về quyền riêng tư?  
**Đáp án:** Frame và thông điệp exception có thể chứa URL, đường dẫn, dữ liệu đầu vào, tên dịch vụ hoặc các bí mật được đưa vào lỗi.

**Câu 9.** Thêm `slf4j-api` có đủ để sinh JSON exception fields không?  
**Đáp án:** Không. Cần provider/backend và encoder/layout có schema phù hợp.

**Câu 10.** Muốn truy vấn literal key `"error.type"` bằng `jq` thì dùng cú pháp gì?  
**Đáp án:** Dùng `."error.type"` hoặc `.["error.type"]`; `.error.type` chỉ phù hợp với object nested.

**Câu 11.** Nếu event ERROR có cause, có chắc mọi encoder tạo mảng `causes[]` không?  
**Đáp án:** Không. Có encoder chỉ xuất stringified stack trace; muốn mảng có cấu trúc phải có schema và resolver tương ứng.

**Câu 12.** Tại sao nên có error code nghiệp vụ ngoài exception type?  
**Đáp án:** Exception type chỉ nói class của lỗi, còn error code ổn định giúp phân biệt tình huống nghiệp vụ và tổng hợp cảnh báo.

**Ghi nhớ:** **Field exception là cách biến Throwable thành dữ liệu JSON có cấu trúc**. Muốn làm đúng, truyền nguyên Throwable vào logger, chọn schema thống nhất, để encoder chuyên dụng tạo `type`, `message`, `stack_trace` và root cause khi cần. Kiểm tra JSON Lines thật, xử lý trường thiếu/null đúng ngữ nghĩa và luôn bảo vệ dữ liệu nhạy cảm trong exception.
