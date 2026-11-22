# Khi nào dùng Logback trong ứng dụng Java?

## 1. Trả lời nhanh: chọn Logback khi nào?

**Logback** là một logging backend cho Java, thường được dùng phía sau API **SLF4J**. Khi mã ứng dụng gọi `org.slf4j.Logger`, Logback có thể thực hiện việc lọc theo level, định dạng sự kiện, chuyển tới console/file và quản lý nhiều đích ghi. Bạn nên cân nhắc Logback khi phát triển **ứng dụng Java vận hành lâu dài** và cần cấu hình logging rõ ràng, linh hoạt, nhất quán với thư viện/framework đang sử dụng.

**Logback là lựa chọn phù hợp nếu** ứng dụng:

- Đã tiêu chuẩn hóa lệnh ghi log bằng **SLF4J** và cần một backend đầy đủ thay vì chỉ in log đơn giản.
- Cần điều chỉnh mức log theo package/lớp, ví dụ bật DEBUG tạm thời cho module thanh toán trong khi toàn ứng dụng ở INFO.
- Cần **Appender, Filter, Encoder/Layout**, đích xuất console hoặc file, và chính sách rolling/retention khi ghi file.
- Cần **MDC** để đưa `requestId`, `traceId`, `jobId` vào nhiều dòng log của một luồng xử lý.
- Đang sử dụng **Spring Boot với cấu hình logging mặc định dựa trên Logback**, và chưa có lý do xác đáng để đổi backend.
- Muốn phân tách mã nghiệp vụ khỏi vị trí và định dạng đầu ra: code gọi SLF4J, cấu hình Logback quyết định phần vận hành.

**Không phải lúc nào cũng cần Logback.** Một công cụ Java nhỏ chạy một lần có thể chỉ cần `java.util.logging` (JUL) của JDK hoặc `slf4j-simple`; thư viện Java tái sử dụng thường chỉ nên phụ thuộc **SLF4J API**, không chọn backend cho ứng dụng dùng thư viện. Với hệ thống đã sử dụng Log4j 2 có cấu hình và vận hành ổn định, không có lợi ích mặc định nào bắt buộc chuyển sang Logback.

Điểm cần nhớ: **Logback không đồng nghĩa với SLF4J**. SLF4J là API/facade; Logback là một implementation/backend. Một chương trình có thể dùng SLF4J API nhưng thực tế ghi log bằng Logback, Log4j 2, JUL hoặc một provider khác.

## 2. Vị trí của Logback trong kiến trúc logging

Một cấu hình phổ biến:

```text
Mã nghiệp vụ
  |  LoggerFactory.getLogger(...), logger.info(...), logger.error(...)
  v
SLF4J API
  |
  |  Một SLF4J provider tương thích
  v
Logback Classic
  |
  +-- Logger hierarchy / effective level
  +-- Filters / TurboFilters
  +-- MDC, logging event
  |
  +--> ConsoleAppender --> Encoder --> stdout/stderr
  |
  +--> RollingFileAppender --> Encoder --> file luân phiên
  |
  +--> AsyncAppender --> Appender đích
```

Các thành phần chính:

| Thành phần | Trách nhiệm |
| --- | --- |
| `slf4j-api` | API để mã ứng dụng phát log mà không gắn chặt vào backend |
| `logback-classic` | Tầng Logback kết nối với SLF4J và quản lý Logger/level/event |
| `logback-core` | Cơ sở cho Appender, Encoder và nhiều cấu phần triển khai của Logback |
| Logger | Nhận sự kiện, quyết định mức nào được chấp nhận theo cấu hình hiệu lực |
| Appender | Đưa event ra đích: console, file hoặc một appender khác |
| Encoder/Layout | Biến event thành text hoặc định dạng được collector hỗ trợ |
| Filter/TurboFilter | Lọc sự kiện theo điều kiện |
| MDC | Ngữ cảnh gắn với luồng xử lý, có thể đưa vào pattern/output |

Trong mô hình Logback thông dụng, **Logger có tên theo package/lớp**, thường kế thừa level từ ancestor khi không đặt riêng; **additivity** xác định event có được chuyển tiếp tới appender của logger cha hay không. Đừng nhầm kế thừa level với việc nhân đôi appender: appender có thể được gắn ở root để nhiều logger dùng chung.

Một event có thể qua Logger nhưng **không xuất hiện ở đích** nếu appender có filter, bị ảnh hưởng bởi chính sách async/buffer, hoặc nơi lưu trữ lỗi. Việc gọi `logger.info(...)` không bảo đảm log đã được ghi bền vững vào ổ đĩa/hệ thống tập trung.

## 3. Bảng quyết định: Logback hay giải pháp khác?

| Tình huống | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Chương trình Java nhỏ, chỉ cần vài dòng chẩn đoán, không muốn dependency ngoài | `java.util.logging` của JDK | Có sẵn, đủ level/handler/formatter cơ bản |
| CLI nhỏ đã dùng SLF4J, chỉ cần output đơn giản | `slf4j-simple` | Ít cấu hình; phù hợp nhu cầu đơn giản |
| Web service Java có nhiều package, môi trường và đích log | **Logback** | Dễ đặt logger hierarchy, appenders, filter và encoder |
| Ứng dụng Spring Boot đang dùng logging starter mặc định | **Giữ Logback mặc định** nếu đáp ứng yêu cầu | Hạn chế đổi backend không cần thiết, tận dụng tích hợp sẵn |
| Dự án đã có Log4j 2 được vận hành tốt | Thường **giữ Log4j 2** | Tránh migration chỉ vì sở thích; so sánh yêu cầu thực tế |
| Thư viện Java dùng chung bởi nhiều ứng dụng | Chỉ khai báo **`slf4j-api`** | Backend nên do ứng dụng tiêu thụ quyết định |
| Hệ thống cần chức năng đặc biệt của một backend/encoder/appender | Đánh giá Logback và Log4j 2 theo yêu cầu | Độ tương thích và kết quả thử tải quan trọng hơn khẩu hiệu |
| Ghi audit yêu cầu giao dịch, bền vững, chống sửa đổi | Thiết kế **audit trail** chuyên biệt | Appender thông thường không phải bảo đảm giao dịch/audit |

Không nên kết luận Logback **luôn nhanh hơn** Log4j 2, **luôn nhẹ hơn** JUL hoặc là lựa chọn duy nhất cho production. Hiệu năng phụ thuộc workload, formatter, appender, tốc độ I/O, đồng bộ/bất đồng bộ, cấu hình filter và cách benchmark.

### 3.1. Dấu hiệu chưa cần một backend đầy đủ

Nếu ứng dụng chỉ là một công cụ thực hiện một tác vụ ngắn, có vài dòng log và không cần thay cấu hình ở runtime, JUL có thể đáp ứng. Việc thêm Logback kéo theo dependency, file cấu hình và trách nhiệm quản lý. Bản thân “dùng framework nhiều tính năng hơn” không phải một mục tiêu kỹ thuật.

Ngược lại, khi ứng dụng lớn lên và cần phân loại sự kiện theo module, ghép context, phối hợp nhiều đích hoặc chuyển logging backend mà không sửa mã nghiệp vụ, **SLF4J + Logback** là một thiết kế rõ ràng.

### 3.2. Khi đã chọn backend khác

Nếu hệ thống đang dùng Log4j 2 hoặc logging service của nền tảng, hãy rà soát những khả năng chưa đáp ứng: format, throughput, appender/plugin, lifecycle, tracing và hỗ trợ của framework. Quyết định đổi sang Logback cần dựa trên thiếu sót cụ thể, kế hoạch migration, kiểm thử và chi phí vận hành — không phải chỉ vì thấy Logback phổ biến.

## 4. Khi cần cấu hình log theo module

Trong một backend đơn giản, thay level thường ảnh hưởng cả chương trình. Với Logback, bạn có thể giữ root ở `INFO` và mở `DEBUG` riêng cho một nhánh:

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{40} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.payment" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Đây là **ví dụ file `logback.xml` hoàn chỉnh** cho một appender console; ứng dụng demo ở mục 8 dùng file cấu hình khác để stdout ổn định. Ý nghĩa:

- Loggers không có cấu hình riêng dùng level hiệu lực từ ancestor/root.
- Các logger thuộc `com.example.payment` có thể phát `DEBUG` trong khi phần còn lại dùng `INFO`.
- Appender gắn ở root nhận các event được chuyển tới root theo cơ chế additivity.
- `%logger{40}`, `%thread`, `%d`, `%msg`, `%n` là các pattern converter của Logback, không phải placeholder tham số của SLF4J.

**Cẩn thận:** ghi `<logger name="com.example.payment" level="DEBUG"/>` không tự tạo một file riêng. Nó chỉ thay chính sách của Logger nhánh đó; chính Appender và cấu hình đường đi quyết định nơi xuất.

### 4.1. Level và additivity

Ví dụ nếu gắn appender ở Logger con **và** root mà vẫn cho additivity, event có thể đi qua cả hai appender và tạo output trùng. Nếu thật sự muốn module ghi vào một đích riêng, có thể dùng:

```xml
<logger name="com.example.payment" level="DEBUG" additivity="false">
    <appender-ref ref="PAYMENT_FILE"/>
</logger>
```

Đây là **mảnh XML nằm bên trong `<configuration>`** và giả sử `PAYMENT_FILE` đã được khai báo. `additivity="false"` chặn việc chuyển event của nhánh này tiếp tới appenders của ancestor. Dùng nó sai khi Logger nhánh **không có appender riêng** sẽ khiến event không có đích xuất.

`additivity` liên quan tới truyền event đến appender cha, **không đồng nghĩa** với vô hiệu hóa kế thừa level. Đặt level hoặc additivity cần thử cả `DEBUG`, `INFO`, `WARN`, `ERROR`, không chỉ quan sát một dòng log.

## 5. Khi cần MDC và correlation ID cho nhiều request

Một ứng dụng web xử lý request song song thường cần `requestId` hoặc `traceId` để nhận diện event:

```text
INFO  requestId=req-61 event=request.received
INFO  requestId=req-62 event=request.received
WARN  requestId=req-61 event=payment.retry
INFO  requestId=req-62 event=request.completed
```

**MDC (Mapped Diagnostic Context)** cho phép gắn một số trường vào context logging của thread hiện tại, thay vì nối thủ công `requestId` vào từng message. Một pattern Logback có thể dùng `%X{requestId}` để in trường tương ứng.

Ví dụ **mảnh mã** dùng SLF4J và một `logger`/phương thức `processRequest()` đã tồn tại:

```java
String oldRequestId = MDC.get("requestId");
try {
    MDC.put("requestId", requestId);
    logger.info("event=request.received");
    processRequest();
} finally {
    if (oldRequestId == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", oldRequestId);
    }
}
```

Cần import `org.slf4j.MDC` cùng backend hỗ trợ MDC. `finally` khôi phục context cũ, phù hợp cho cả phạm vi lồng nhau và thread pool. **Không giả định MDC tự truyền qua `ExecutorService`, `CompletableFuture` hoặc reactive pipeline**; nếu công việc chạy trên thread khác, phải truyền context tường minh hoặc sử dụng cơ chế context propagation của framework/tracing library.

Một `requestId` từ HTTP header phải được kiểm tra độ dài, ký tự và độ tin cậy trước khi đưa vào log; không mặc nhiên tin giá trị từ client. MDC không thay thế distributed tracing, nhưng có thể dùng traceId/spanId đã được tracing library tạo ra để kết nối log với trace.

**Khi Logback có ích:** muốn mọi log cùng request có ID bằng cấu hình, trong khi code nghiệp vụ chỉ cần thiết lập context ở ranh giới xử lý. Tuy nhiên nếu ứng dụng chỉ có một tác vụ đơn giản, có thể truyền ID tường minh và không cần MDC.

## 6. Khi cần nhiều đích xuất, rolling file và retention

Logback hỗ trợ `ConsoleAppender`, `FileAppender`, `RollingFileAppender` và khả năng kết hợp với các appender khác trong hệ sinh thái. Có thể xuất:

- **Console stdout** để container runtime/agent thu thập tập trung.
- **File** khi hệ thống thực sự cần lưu cục bộ, có quyền ghi và quy trình rotation.
- **Các đích chuyên biệt** qua appender phù hợp, sau khi cân nhắc lỗi mạng, bộ đệm và backpressure.

### 6.1. Ví dụ RollingFileAppender

Khi chạy một ứng dụng quản lý file log cục bộ, có thể dùng **mảnh cấu hình bên trong `<configuration>`**:

```xml
<appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>

    <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
        <fileNamePattern>logs/application.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
        <maxHistory>14</maxHistory>
        <totalSizeCap>500MB</totalSizeCap>
    </rollingPolicy>

    <encoder>
        <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
    </encoder>
</appender>
```

Sau khi khai báo appender, cần tham chiếu nó từ Logger/root bằng `<appender-ref ref="FILE"/>` để các event được chuyển tới đó. Chính sách trên mô tả rollover hằng ngày, giới hạn lịch sử và tổng dung lượng archive; **không có nghĩa mọi điều kiện hệ thống file và shutdown đều đảm bảo dữ liệu không mất**.

Lưu ý vận hành:

- Thư mục phải có quyền ghi; disk có thể đầy; ứng dụng phải có chiến lược giám sát.
- File log và archive không nên nằm trên ổ dùng chung giữa nhiều instance nếu backend/rolling policy không được thiết kế cho tình huống ghi đồng thời.
- Trong Kubernetes/container/cloud, **ghi stdout/stderr và để nền tảng quản lý thu gom/rotation thường đơn giản hơn** ghi rolling file trong filesystem ephemeral.
- Chọn retention phù hợp với yêu cầu điều tra và quy định dữ liệu; retention quá dài có thể giữ cả dữ liệu nhạy cảm.
- Với hệ thống tập trung, cần kiểm tra khả năng parse format, đồng hồ/timestamp, trace ID và timezone.

**Khi dùng Logback:** cần cấu hình console/file/rolling ngay trong app, hoặc muốn dùng appender/encoder đã được hệ sinh thái hỗ trợ. **Không nên** chỉ vì Logback có RollingFileAppender mà buộc mọi service container ghi file cục bộ.

## 7. Khi cần bất đồng bộ và hiệu năng có kiểm soát

`AsyncAppender` là một lựa chọn của Logback để đưa event vào hàng đợi rồi chuyển tới appender đích ở worker thread. Nó có thể giảm thời gian blocking của thread ứng dụng trong một số workload, đặc biệt khi đích ghi chậm. Nhưng cần hiểu rủi ro:

- Queue có **dung lượng hữu hạn**; khi gần đầy, chính sách discard có thể bỏ các event mức thấp theo cấu hình.
- Khi queue đầy, có thể blocking hoặc bỏ event tùy chính sách `neverBlock` và cấu hình tương ứng.
- Việc lời gọi log trả về không có nghĩa event đã được lưu bền vững.
- Khi ứng dụng tắt đột ngột, các event chưa được xử lý trong queue có thể mất.
- Dữ liệu ở MDC/argument cần được capture đúng thời điểm; custom object mutable có thể thay đổi trước khi encoder xử lý.

Ví dụ **mảnh XML** minh họa bọc một appender đã khai báo tên `FILE`:

```xml
<appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>1024</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <appender-ref ref="FILE"/>
</appender>
```

Đây không phải một `logback.xml` độc lập. Để dùng, tham chiếu `ASYNC` từ Logger/root và tránh đồng thời tham chiếu `FILE` ở cùng đường nếu không muốn in trùng. `discardingThreshold=0` tắt cơ chế loại event do ngưỡng queue còn trống thông thường, nhưng **không bảo đảm không bao giờ mất log** khi shutdown/crash hoặc lỗi ở appender đích; với `neverBlock=false`, thread ứng dụng có thể bị chặn khi queue đầy. Cần thử dưới tải thật, giám sát mức hàng đợi và thời gian shutdown.

Logback cũng không tự động biến log thành một pipeline giao dịch đáng tin cậy. Những sự kiện audit phải được bảo đảm bền vững/không thể sửa đổi có thể cần cơ chế ghi chuyên biệt, transaction, phân quyền và storage riêng.

**Khi không nên bật async ngay:** số lượng event nhỏ, console có đủ tốc độ, ứng dụng cần đơn giản hoặc chưa có benchmark chứng minh bottleneck ở logging. Bất đồng bộ thêm phức tạp và chính sách mất/chặn event.

## 8. Ví dụ Java 17 chạy độc lập bằng Gradle và Logback

Ví dụ thực hành này sử dụng **Java 17, SLF4J API và Logback Classic**. Ta tạo một ứng dụng nhỏ với root level `INFO`, nhưng bật `DEBUG` cho Logger `demo.detail`. Pattern in level, tên logger, `requestId` từ MDC và message để quan sát chính xác.

Ta dùng phiên bản Logback 1.5.18 làm mốc **cố định cho bài thực hành**; đó không phải lời khẳng định phiên bản mới nhất. Khi đưa vào dự án thực tế, hãy chọn phiên bản được hỗ trợ, cập nhật bảo mật và quản lý tập trung. `logback-classic` kéo theo các dependency cần thiết, gồm `logback-core` và phiên bản SLF4J API tương thích; không cần thêm một provider thứ hai.

### 8.1. Cấu trúc thư mục

```text
logback-choice-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LogbackChoiceDemo.java
        └── resources/
            └── logback.xml
```

### 8.2. File settings.gradle

```groovy
rootProject.name = 'logback-choice-demo'
```

### 8.3. File build.gradle (Groovy DSL)

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'ch.qos.logback:logback-classic:1.5.18'
}

application {
    mainClass = 'demo.LogbackChoiceDemo'
}
```

Plugin `application` cung cấp task `run`. Java toolchain yêu cầu môi trường có hoặc cung cấp được JDK 17. Logback không phải một thành phần của JDK, nên Gradle phải tải dependency từ Maven Central hoặc repository được tổ chức cấu hình.

### 8.4. File src/main/resources/logback.xml

```xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%-5level %logger requestId=%X{requestId} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo.detail" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Chú ý:

- Tên resource là `logback.xml` đặt trên runtime classpath.
- `<target>System.out</target>` làm appender xuất ra stdout.
- `%X{requestId}` đọc ngữ cảnh MDC.
- Root ở `INFO` nên sự kiện `DEBUG` ở Logger thông thường bị bỏ.
- Logger `demo.detail` đặt `DEBUG`; nó không cần appender riêng vì mặc định có additivity về root.
- `%-5level` in level canh trái rộng 5 ký tự, nên `INFO` và `WARN` có một dấu cách đệm.

### 8.5. File src/main/java/demo/LogbackChoiceDemo.java

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class LogbackChoiceDemo {
    private static final Logger APP =
            LoggerFactory.getLogger(LogbackChoiceDemo.class);
    private static final Logger DETAIL =
            LoggerFactory.getLogger("demo.detail");

    public static void main(String[] args) {
        String previous = MDC.get("requestId");
        try {
            MDC.put("requestId", "req-42");

            APP.info("event=order.created orderId={}", "ord-7");
            APP.debug("event=diagnostic.hidden");
            DETAIL.debug("event=cache.miss key={}", "product-8");
            APP.warn("event=payment.retry attempt={}", 2);
        } finally {
            if (previous == null) {
                MDC.remove("requestId");
            } else {
                MDC.put("requestId", previous);
            }
        }
    }
}
```

Đoạn trên dùng placeholder `{}` của SLF4J, **không phải** `{0}` của `java.util.logging`. Logger dùng chung dưới dạng `static final`, còn context theo request nằm trong MDC, không được biến thành tên Logger mới.

### 8.6. Biên dịch và chạy

Tại thư mục `logback-choice-demo`, dùng Gradle bản tương thích với Java 17:

```bash
gradle run --quiet
```

Nếu dự án đã có Gradle Wrapper, thay bằng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows. Ví dụ này không đóng gói Gradle Wrapper; khi không có Gradle được cài sẵn, cần chuẩn bị Gradle/JDK trước.

**stdout của chương trình khi chạy với đúng cấu hình trên:**

```text
INFO  demo.LogbackChoiceDemo requestId=req-42 - event=order.created orderId=ord-7
DEBUG demo.detail requestId=req-42 - event=cache.miss key=product-8
WARN  demo.LogbackChoiceDemo requestId=req-42 - event=payment.retry attempt=2
```

Phân tích:

1. `APP.info` qua root `INFO`; `%X{requestId}` điền `req-42`.
2. `APP.debug` không hiện vì Logger `demo.LogbackChoiceDemo` không đặt level riêng, nên level hiệu lực là `INFO` từ root.
3. `DETAIL.debug` vẫn hiện vì Logger tên `demo.detail` có level `DEBUG`.
4. `APP.warn` in `WARN` và tham số `2` được SLF4J thay vào `{}`.
5. `finally` xóa/khôi phục MDC để tránh rò request ID nếu thread được tái sử dụng.
6. Không có timestamp/thread trong pattern của demo, vì thế đầu ra có thể đối chiếu chính xác. Trong sản xuất nên có timestamp, service/instance và các trường cần cho hệ thống thu thập.

Nếu đổi `<root level="INFO">` thành `<root level="DEBUG">`, lời gọi `APP.debug("event=diagnostic.hidden")` sẽ xuất hiện. Nếu xóa dòng logger `demo.detail`, sự kiện `DETAIL.debug` không còn xuất khi root vẫn là `INFO`. Đó là minh họa cụ thể lợi ích của cấu hình theo từng nhánh mà không sửa logic ứng dụng.

## 9. Logback trong Spring Boot: khi nào giữ mặc định?

Nhiều ứng dụng Spring Boot dùng logging starter mặc định có **Logback** làm backend, do đó đã có cấu hình logging và tích hợp theo hệ sinh thái. Khi hệ thống đã dùng backend này ổn định:

- **Không cần tự thêm `logback-classic` lần nữa** chỉ để sử dụng `LoggerFactory.getLogger` hoặc gọi `logger.info`.
- Ưu tiên quản lý mức log theo cấu hình Spring Boot cho nhu cầu đơn giản; khi cần Appender/Encoder/phân luồng đặc biệt mới dùng cấu hình Logback riêng.
- Với cấu hình Logback qua Spring Boot, định dạng và tên file có thể khác ứng dụng Java thuần. Một số khả năng riêng của Spring Boot được hỗ trợ qua `logback-spring.xml`, không nên mặc định đặt chúng vào `logback.xml` thuần và kỳ vọng mọi extension hoạt động.
- Nếu chọn chuyển sang Log4j 2, cần **loại backend mặc định và thêm đúng logging starter/provider** theo hướng dẫn của phiên bản Spring Boot đang sử dụng, không chỉ bổ sung Log4j 2 bên cạnh Logback.

Trong Java thuần, `logback.xml` trên classpath là lựa chọn điển hình. Trong Spring Boot, cách quản lý cấu hình có thêm lớp môi trường/starter, nên cần kiểm tra backend runtime và quy ước của framework.

### 9.1. Đảm bảo một provider SLF4J đúng phiên bản

Logback Classic hiện đại triển khai provider cho **SLF4J 2.x**. Nếu runtime còn `slf4j-simple`, `slf4j-nop` hay `log4j-slf4j2-impl` cùng làm provider, SLF4J có thể cảnh báo **multiple providers**; nếu provider NOP được chọn, log có thể bị bỏ.

Nếu dùng SLF4J 1.7.x, cơ chế cũ là `StaticLoggerBinder`; SLF4J 2.x dùng `ServiceLoader`. Đừng trộn các thế hệ một cách tùy ý. Trong một ứng dụng vận hành, giữ **một backend/provider** chủ đích và kiểm tra dependency bắc cầu.

Lệnh chẩn đoán Gradle:

```bash
gradle dependencies --configuration runtimeClasspath
gradle dependencyInsight --configuration runtimeClasspath --dependency logback-classic
```

Maven:

```bash
mvn dependency:tree
```

Đây là lệnh kiểm tra **dự án đang có**, không phải lệnh bắt buộc của demo nếu không có lỗi. Trong ứng dụng nhiều module, kiểm tra `runtimeClasspath` của module khởi động và cả `testRuntimeClasspath` nếu cảnh báo chỉ xuất hiện khi chạy test.

## 10. Logging có cấu trúc và hệ thống thu thập

Logback có thể xuất text theo pattern, nhưng **pattern text không phải tự nhiên là structured JSON**. Khi cần truy vấn theo các trường `traceId`, `requestId`, `errorCode` và đo chính xác kết quả, nên dùng encoder hỗ trợ JSON có schema, escape an toàn, đúng kiểu số/boolean và phù hợp với hệ thống thu thập.

Một event có cấu trúc có thể mang:

```json
{
  "timestamp": "2026-01-12T10:15:00Z",
  "level": "ERROR",
  "service": "checkout",
  "event": "payment.failed",
  "requestId": "req-42",
  "errorCode": "GATEWAY_TIMEOUT",
  "durationMs": 450
}
```

Đây là **mẫu JSON minh họa**, không phải đầu ra tự động của cấu hình `logback.xml` trong mục 8. Một số encoder JSON cần dependency bổ sung và cấu hình riêng; hãy chọn giải pháp được backend/framework hiện dùng hỗ trợ, không tự nối JSON bằng chuỗi thủ công đối với dữ liệu không đáng tin cậy.

Ngoài log, nên có **metrics** (tỷ lệ lỗi, độ trễ, throughput) và **traces** (đường đi qua nhiều service). Logback là backend logging, không tự thay thế toàn bộ observability stack.

### 10.1. Bảo mật nội dung log

Dù backend nào, phải thực hiện các nguyên tắc:

- Không ghi password, token, cookie, khóa bí mật, thông tin thẻ hoặc payload chứa dữ liệu nhạy cảm.
- Chọn các trường context theo allowlist; tránh gọi `toString()` trên DTO có thể chứa secret.
- Escape/sanitize giá trị do client cung cấp để ngăn **log injection** bằng xuống dòng hoặc ký tự điều khiển.
- Không ghi stack trace ở mọi tầng nếu cùng một lỗi đã được ghi tại ranh giới xử lý phù hợp.
- Quản lý quyền đọc log, thời gian giữ log và việc chuyển dữ liệu sang collector.
- Không sử dụng appender production để tự động ghi thông tin cá nhân mà không có mục đích và quyền truy cập phù hợp.

Formatter/encoder có thể giúp che dữ liệu, nhưng tốt nhất là **không đưa bí mật vào log event ngay từ đầu**. Một layout tùy chỉnh không thể bảo đảm tìm thấy mọi secret ẩn trong exception hoặc object được serialize.

## 11. Chi phí vận hành và các giới hạn cần biết

### 11.1. Cấu hình sai có thể làm mất hoặc trùng log

- Logger con có appender riêng và vẫn có additivity lên root: **log trùng**.
- Tắt additivity khi Logger con không có appender nào: **log không có đích**.
- Đặt root `INFO` và Logger `DEBUG` nhưng appender có filter chặn: **DEBUG không xuất**.
- Chọn provider NOP hoặc cấu hình nhiều provider SLF4J: **backend thực tế không đúng ý định**.
- Log được đưa vào AsyncAppender nhưng tiến trình crash trước khi ghi: **event có thể mất**.

Cần kiểm tra pipeline từ lời gọi SLF4J → logger level/filter → appender → encoder → stdout/file/collector; không dừng ở việc `logger.isDebugEnabled()` trả `true`.

### 11.2. Hiệu năng không tự đến từ tên backend

Chi phí log gồm kiểm tra level, tạo đối số/message, MDC snapshot, format, stack trace, I/O, queue và collector. SLF4J hỗ trợ placeholder `{}` giúp trì hoãn format chuỗi thông thường, nhưng **biểu thức Java truyền làm đối số vẫn được đánh giá trước khi gọi**.

Ví dụ:

```java
logger.debug("state={}", expensiveSnapshot());
```

Đây là **đoạn minh họa**, giả sử `logger` và `expensiveSnapshot()` đã được định nghĩa. `expensiveSnapshot()` vẫn chạy ngay cả khi DEBUG bị tắt. Nếu phép tính đắt, cân nhắc:

```java
if (logger.isDebugEnabled()) {
    logger.debug("state={}", expensiveSnapshot());
}
```

Logback không khiến toàn bộ phép tính trong biểu thức Java tự động lazy. Cũng không đặt side effect nghiệp vụ bên trong tính toán phục vụ log.

### 11.3. Deployment và lifecycle

Đối với server chạy lâu dài, xem xét flush/stop logging context khi shutdown bình thường, xử lý lỗi I/O, đích lưu, log rotation và retention. Với container, stdout và collector thường giảm quản lý file cục bộ. Nếu thay đổi file cấu hình ở runtime, cần hiểu cơ chế nạp lại và khả năng hỗ trợ của phiên bản; **không mặc định mọi thay đổi đều hot reload tức thì**.

Các yêu cầu audit có tính pháp lý hoặc tính giao dịch cao cần được thiết kế độc lập, không mặc định một dòng `logger.info` là bằng chứng bền vững không thể sửa đổi.

## 12. Những sai lầm khi quyết định dùng Logback

| Sai lầm | Cách nhìn đúng |
| --- | --- |
| “SLF4J là Logback” | SLF4J là API; Logback là một backend |
| “Library nào cũng phải thêm logback-classic” | Library thường chỉ cần SLF4J API; ứng dụng chọn provider |
| “Logback luôn nhanh hơn mọi backend” | Phải benchmark đúng workload, appender và cấu hình |
| “Thêm Logback vào Spring Boot luôn cải thiện logging” | Framework có thể đã dùng Logback sẵn; thêm dư gây xung đột |
| “Có log file là đủ an toàn” | Cần retention, quyền truy cập, bảo vệ dữ liệu và giám sát |
| “AsyncAppender giúp log không bao giờ mất” | Queue/crash và chính sách discard có thể làm mất event |
| “Đặt DEBUG cho một Logger thì mọi đích đều in DEBUG” | Appender filter và đường đi event vẫn quyết định |
| “Tắt additivity luôn chữa được log trùng” | Nếu nhánh không có appender riêng, có thể mất log |
| “MDC tự đi theo CompletableFuture” | Thường phải truyền/khôi phục context tường minh hoặc qua framework |
| “Ghi JSON bằng PatternLayout tức là đủ structured” | Cần encoder/serializer đúng schema và escape |
| “Một backend logging thay được audit/metrics/tracing” | Mỗi loại tín hiệu có trách nhiệm và mức đảm bảo riêng |

## 13. Quy trình lựa chọn cho dự án thật

**Bước 1 — Xác định vai trò artifact.** Nếu bạn đang xây **thư viện** để ứng dụng khác sử dụng, thường chỉ nên phụ thuộc SLF4J API; không ép backend. Nếu là **ứng dụng khởi động**, mới quyết định Logback hay backend khác.

**Bước 2 — Xác định framework đang dùng.** Với Spring Boot sử dụng mặc định Logback, ưu tiên giữ nếu đáp ứng yêu cầu. Với dự án đã chọn Log4j 2 ổn định, xác định lý do rõ trước khi đổi.

**Bước 3 — Liệt kê yêu cầu vận hành.** Cần level theo package? MDC? JSON encoder? File rolling? Async? Thu thập qua stdout? Tracing? Những yêu cầu này mới quyết định backend và cấu hình cụ thể.

**Bước 4 — Chọn một provider SLF4J tương thích.** Rà dependency graph, loại provider dư và tránh bridge hai chiều có thể gây vòng routing.

**Bước 5 — Thiết kế đường xuất.** Container thường ưu tiên stdout/collector; hệ thống ghi file cần rotation, retention, quyền ghi, giám sát dung lượng và shutdown.

**Bước 6 — Kiểm thử hành vi.** Tạo sự kiện ở INFO, DEBUG, WARN, ERROR, có requestId, có ngoại lệ; kiểm tra output, đích ghi, trùng log, mất context ở executor và độ trễ khi log nhiều.

**Bước 7 — Đánh giá bảo mật và chi phí.** Giới hạn dữ liệu nhạy cảm, kiểm soát lượng log, cập nhật phiên bản backend được hỗ trợ và có giám sát chính sách discard/collector.

## 14. Checklist trước khi chọn hoặc triển khai

- [ ] Ứng dụng thật sự cần một backend đầy đủ thay vì JUL/slf4j-simple.
- [ ] Đã phân biệt vai trò **thư viện** và **ứng dụng chạy**.
- [ ] Đã xác định framework/backend đang hoạt động, tránh thay thế không cần thiết.
- [ ] Chỉ có một SLF4J provider tương thích trong runtime classpath.
- [ ] Level theo package/lớp, hierarchy và additivity được thiết kế nhất quán.
- [ ] Có Appender và Encoder phù hợp đích console/file/collector.
- [ ] Nếu ghi file, có rolling, retention, quyền ghi và xử lý thiếu dung lượng.
- [ ] Nếu dùng MDC/trace, có propagation và cleanup khi qua thread/executor khác.
- [ ] Nếu dùng AsyncAppender, hiểu rõ queue, blocking, discard và giới hạn shutdown.
- [ ] Có chính sách dữ liệu nhạy cảm, escaping, phân quyền và lưu trữ log.
- [ ] Có kiểm thử các luồng thành công, thất bại, ngoại lệ, log trùng và log bị lọc.
- [ ] Đã đánh giá performance trên workload thực thay vì dựa vào danh tiếng backend.

### Nguồn tham khảo kỹ thuật

- [Logback documentation](https://logback.qos.ch/documentation.html): kiến trúc, cấu hình, logger, appender và encoder.
- [Logback manual — Configuration](https://logback.qos.ch/manual/configuration.html): cách đặt cấu hình và cơ chế đọc file.
- [Logback manual — Appenders](https://logback.qos.ch/manual/appenders.html): ConsoleAppender, RollingFileAppender và AsyncAppender.
- [SLF4J manual](https://www.slf4j.org/manual.html): API facade, provider và cách dùng logger.
- [Spring Boot logging reference](https://docs.spring.io/spring-boot/reference/features/logging.html): tích hợp logging và tùy chọn cấu hình framework.

**Kết luận:** **Dùng Logback khi bạn cần một backend logging được cấu hình, quan sát và vận hành nghiêm túc cho ứng dụng Java**, nhất là khi mã đã dùng SLF4J hoặc framework vốn tích hợp Logback. Không dùng nó chỉ vì quen tay: hãy bắt đầu từ yêu cầu thực tế, chọn đúng một provider, thiết kế Appender/Encoder và kiểm tra MDC, log retention, hiệu năng cùng khả năng bảo vệ thông tin.
