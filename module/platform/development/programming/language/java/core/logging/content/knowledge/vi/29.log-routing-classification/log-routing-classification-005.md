# Tách log nghiệp vụ trong Java: routing và phân loại log

## 1. Tách log nghiệp vụ là gì, để làm gì?

Trong một ứng dụng Java, nhiều thông điệp khác nhau có thể cùng xuất hiện trong log:

~~~text
INFO  HTTP POST /orders returned 201 in 43 ms
INFO  ORDER_PLACED order_id=O-42 amount_minor=125000 currency=VND
WARN  Database connection pool utilization is high
INFO  ORDER_PAID order_id=O-42 payment_method=card
ERROR Payment provider timed out on retry attempt 2
~~~

Dòng thứ nhất, thứ ba và thứ năm nói về **vận hành kỹ thuật**: HTTP, database, timeout, retry. Dòng thứ hai và thứ tư nói về **sự kiện nghiệp vụ**: một đơn hàng đã được ghi nhận, một khoản thanh toán đã được xác nhận. Nếu mọi dòng đều đi vào cùng một kênh mà không phân loại, người đọc và hệ thống giám sát dễ lẫn trạng thái nghiệp vụ với triệu chứng hạ tầng.

**Tách log nghiệp vụ** là gắn loại sự kiện có chủ đích, rồi điều khiển cách ghi, định dạng, gửi, tìm kiếm và lưu trữ dựa trên loại đó. Mục đích không nhất thiết là tạo nhiều file trên máy. Một hệ thống có thể vẫn xuất mọi log ra stdout dưới dạng JSON, nhưng tách kênh một cách logic bằng trường category để collector/backend áp chính sách riêng.

Sau bài này, người học cần phân biệt được business log, technical log và audit/security log; chọn cơ chế tách phù hợp; cấu hình routing không ghi trùng; và hiểu giới hạn về độ tin cậy của log đối với nghiệp vụ.

## 2. Phân loại trước khi chọn appender

| Nhóm | Câu hỏi trả lời | Ví dụ | Đặc trưng |
| --- | --- | --- | --- |
| BUSINESS | Điều gì có ý nghĩa trong quy trình nghiệp vụ vừa xảy ra? | ORDER_PLACED, PAYMENT_CONFIRMED, SHIPMENT_DISPATCHED | Tên sự kiện ổn định, có định danh và kết quả, phục vụ truy vấn hành trình nghiệp vụ |
| TECHNICAL / APPLICATION | Ứng dụng đang vận hành thế nào? | HTTP 500, retry, SQL timeout, cache miss, kết nối bị đóng | Hỗ trợ vận hành, debug, đo hiệu năng và phân tích sự cố |
| SECURITY | Hoạt động bảo mật nào đáng chú ý? | LOGIN_FAILED, quyền truy cập bị từ chối, phát hiện truy cập bất thường | Có thể cần kiểm soát phân quyền, giám sát và retention riêng |
| AUDIT | Ai thực hiện thay đổi gì, khi nào, trên đối tượng nào? | POLICY_CHANGED, ROLE_ASSIGNED, MANUAL_APPROVAL | Có thể có yêu cầu riêng về tính toàn vẹn, nguồn gốc và lịch sử |
| ACCESS | Request nào được phục vụ, kết quả HTTP ra sao? | GET /orders/42 200 35ms | Thường do web server/gateway phát sinh, giúp phân tích traffic |

Một sự kiện có thể đồng thời hữu ích cho nhiều mục đích. Ví dụ quyền của một tài khoản được thay đổi vừa là nghiệp vụ vừa có giá trị audit. Hãy xác định **nguồn sự thật và chính sách lưu trữ** cho từng mục đích; không mặc định một dòng INFO là bằng chứng audit đầy đủ.

### Mức log không phải loại log

DEBUG, INFO, WARN và ERROR thể hiện mức nghiêm trọng/chi tiết, **không quyết định sự kiện thuộc nghiệp vụ hay kỹ thuật**.

- ORDER_PLACED thành công thường ở INFO và thuộc BUSINESS.
- ORDER_REJECTED do điều kiện nghiệp vụ có thể ở INFO hoặc WARN tùy chính sách, vẫn thuộc BUSINESS.
- Một SQL timeout ở ERROR là TECHNICAL, dù có ảnh hưởng đến quy trình đặt hàng.
- Một thay đổi phân quyền ở INFO có thể thuộc AUDIT/SECURITY dù không có lỗi.

Đừng định tuyến toàn bộ INFO vào business.log và toàn bộ ERROR vào technical.log: cả hai loại đều có nhiều mức log.

## 3. Xây dựng tiêu chí business event

Một business event tốt diễn tả **sự kiện đã được xác lập** trong domain, không chỉ mô tả hành động đang được thử. Cần phân biệt:

~~~text
ORDER_PAYMENT_STARTED        # bắt đầu thao tác, chưa có kết quả cuối
ORDER_PAYMENT_CONFIRMED      # hệ thống đã xác nhận thanh toán
ORDER_PAYMENT_REJECTED       # nghiệp vụ từ chối thanh toán theo quy tắc
PAYMENT_PROVIDER_TIMEOUT     # lỗi kỹ thuật ở tích hợp thanh toán
~~~

Tùy thiết kế, sự kiện đầu tiên có thể là một bước nghiệp vụ hợp lệ; điều quan trọng là tên sự kiện không tạo ấn tượng sai về trạng thái đã được commit. Ví dụ, nếu database transaction rollback, không thể coi một dòng "ORDER_PAID" ghi ngay trước lệnh commit là bằng chứng thanh toán chắc chắn thành công.

**Cấu trúc dữ liệu đề xuất cho business log:**

~~~json
{
  "timestamp": "2026-11-10T02:30:00Z",
  "category": "BUSINESS",
  "event_type": "ORDER_CONFIRMED",
  "schema_version": 1,
  "event_id": "evt-7d6e",
  "order_id": "O-42",
  "outcome": "SUCCESS",
  "service": "order-service",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "message": "Order confirmed"
}
~~~

Đây là **mẫu schema**, không phải output mặc định của Java/Logback. Ý nghĩa từng trường:

| Trường | Tác dụng | Lưu ý |
| --- | --- | --- |
| timestamp / occurred_at | Thời điểm sự kiện được xác định | Dùng thời gian UTC rõ múi giờ; phân biệt lúc xảy ra và lúc thu thập log |
| category | Nhóm để routing, ví dụ BUSINESS | Dùng tập giá trị hữu hạn và có quản trị |
| event_type | Tên sự kiện ổn định, dùng cho thống kê/truy vấn | Ưu tiên hằng số, không tạo tên mới theo từng order/user |
| schema_version | Phiên bản cấu trúc event | Tăng khi thay đổi hợp đồng trường có ảnh hưởng consumer |
| event_id | Định danh riêng của event | Hữu ích để phát hiện bản ghi lặp trong pipeline, nếu được phát sinh đúng |
| entity_id / order_id | Thực thể nghiệp vụ liên quan | Chỉ ghi định danh cho phép công bố theo chính sách dữ liệu |
| outcome | SUCCESS, REJECTED, FAILED... | Phân biệt từ chối do nghiệp vụ và lỗi kỹ thuật |
| service | Dịch vụ phát ra | Cần ổn định giữa các replica |
| trace_id / request_id | Liên kết tới log kỹ thuật của cùng lần xử lý | Trace ID chỉ có ý nghĩa distributed trace khi context được truyền hợp lệ |
| message | Nội dung con người dễ đọc | Không nên là trường duy nhất dùng để phân loại |

Không phải hệ thống nào cũng cần toàn bộ trường. Chọn schema phù hợp yêu cầu, nhưng giữ tên và kiểu dữ liệu nhất quán; khi log ở dạng JSON, nên để amount là số ở đơn vị nhỏ rõ ràng và currency là mã ISO thay vì chỉ nhét tất cả vào một chuỗi tiếng Việt.

## 4. Các cách tách log nghiệp vụ

Có bốn cách thường gặp; chúng có thể kết hợp với nhau.

### 4.1. Theo tên logger/category

Tạo logger chuyên ghi sự kiện nghiệp vụ:

~~~java
// Snippet khi đã có SLF4J và backend hỗ trợ.
private static final org.slf4j.Logger BUSINESS_LOG =
    org.slf4j.LoggerFactory.getLogger("com.example.business");

private static final org.slf4j.Logger APP_LOG =
    org.slf4j.LoggerFactory.getLogger(OrderService.class);
~~~

Gọi BUSINESS_LOG khi nghiệp vụ đã sinh một sự kiện được quy định. Gọi APP_LOG khi cần diễn giải flow kỹ thuật, xử lý exception, latency hoặc debug. Sau đó cấu hình backend để logger com.example.business đi tới appender riêng.

Ưu điểm: dễ hiểu, cấu hình tương đối đơn giản, phù hợp phạm vi một ứng dụng. Giới hạn: chỉ những event được gửi vào logger đó mới đi đúng kênh. Một dòng lỗi kỹ thuật vô tình gọi BUSINESS_LOG vẫn bị phân loại sai. Cần quy ước và code review.

### 4.2. Theo marker

SLF4J có Marker cho phép đánh dấu event mà không cần tạo logger riêng:

~~~java
// Snippet SLF4J; chưa phải chương trình độc lập.
org.slf4j.Marker marker =
    org.slf4j.MarkerFactory.getMarker("BUSINESS");

logger.info(marker, "event_type={} order_id={}",
    "ORDER_CONFIRMED", "O-42");
~~~

Marker gắn metadata ngữ nghĩa vào log event. Logging backend phải được cấu hình filter/routing đọc marker thì việc tách mới thực sự xảy ra; chỉ khai báo Marker không tự tạo file business.log. Một backend có thể hỗ trợ MarkerFilter, backend khác có API/filter khác nhau.

### 4.3. Theo structured field/category

Tất cả event phát ra JSON line và chứa category=BUSINESS/TECHNICAL/AUDIT. Collector hoặc backend chia stream, index hay retention theo trường này.

~~~text
Java services
   └─ stdout JSON lines
         └─ container runtime
               └─ collector parses category
                      ├─ BUSINESS → index / stream business
                      ├─ TECHNICAL → index / stream application
                      └─ AUDIT → pipeline và quyền riêng
~~~

Đây thường là phương án dễ vận hành trong container: giảm nhu cầu chia sẻ file và phù hợp tìm kiếm tập trung. Nhưng nếu collector cấu hình sai, parse thất bại hoặc nhận sự kiện không có category, cần có đường fallback/quarantine cùng metrics để tránh mất log không rõ nguyên nhân.

### 4.4. Theo appender/handler đích

Một ứng dụng có thể gửi BUSINESS tới file, broker, syslog hoặc appender riêng; TECHNICAL tới console/file khác. Với Java Util Logging dùng Logger + Handler; với Logback/Log4j 2 dùng logger configuration, additivity và appender reference. Cách này phù hợp khi yêu cầu tách vật lý, nhưng phải kiểm soát rotation, quyền truy cập, shutdown và lỗi sink.

**Đừng tự động tạo một file riêng cho mỗi order_id/user_id**: số lượng đích tăng theo cardinality, gây quá nhiều file/appender, open file handles và chi phí vận hành. Dùng định danh trong event để lọc ở backend sẽ linh hoạt hơn.

## 5. Ví dụ Java 17 độc lập: BUSINESS và TECHNICAL là hai kênh khác nhau

Ví dụ dưới đây chỉ dùng **java.util.logging** có sẵn trong JDK. Hai logger tên khác nhau và hai Handler nhận các sự kiện riêng biệt. ByteArrayOutputStream đại diện cho hai sink để test định tuyến, nhờ vậy output là xác định và không cần quyền ghi file.

**Tệp: BusinessLogRoutingDemo.java**

~~~java
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class BusinessLogRoutingDemo {
    private static final Logger BUSINESS =
            Logger.getLogger("example.business");
    private static final Logger TECHNICAL =
            Logger.getLogger("example.technical");

    private static StreamHandler newHandler(OutputStream target) {
        StreamHandler handler = new StreamHandler(target, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getMessage() + System.lineSeparator();
            }
        });
        handler.setLevel(Level.ALL);
        return handler;
    }

    private static void connect(Logger logger, Handler handler) {
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);
        logger.addHandler(handler);
    }

    public static void main(String[] args) {
        ByteArrayOutputStream businessBytes = new ByteArrayOutputStream();
        ByteArrayOutputStream technicalBytes = new ByteArrayOutputStream();

        StreamHandler businessHandler = newHandler(businessBytes);
        StreamHandler technicalHandler = newHandler(technicalBytes);
        connect(BUSINESS, businessHandler);
        connect(TECHNICAL, technicalHandler);

        try {
            TECHNICAL.info("GET /orders status=200");
            BUSINESS.info(
                    "event=ORDER_ACCEPTED order_id=O-42 result=SUCCESS");
            TECHNICAL.warning("payment latency_ms=45");
            BUSINESS.info(
                    "event=ORDER_PAID order_id=O-42 result=SUCCESS");
        } finally {
            businessHandler.flush();
            technicalHandler.flush();
            BUSINESS.removeHandler(businessHandler);
            TECHNICAL.removeHandler(technicalHandler);
            businessHandler.close();
            technicalHandler.close();
        }

        System.out.println("=== BUSINESS ===");
        System.out.print(
                businessBytes.toString(StandardCharsets.UTF_8));
        System.out.println("=== TECHNICAL ===");
        System.out.print(
                technicalBytes.toString(StandardCharsets.UTF_8));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 BusinessLogRoutingDemo.java
java BusinessLogRoutingDemo
~~~

**Stdout chính xác từ chương trình:**

~~~text
=== BUSINESS ===
event=ORDER_ACCEPTED order_id=O-42 result=SUCCESS
event=ORDER_PAID order_id=O-42 result=SUCCESS
=== TECHNICAL ===
GET /orders status=200
payment latency_ms=45
~~~

### Phân tích ví dụ

- BUSINESS và TECHNICAL là **hai logger khác tên** với Handler riêng. Không có điều kiện dựa trên mức log để đoán loại sự kiện.
- setUseParentHandlers(false) ngăn event tiếp tục tới Handler của logger cha, tránh bản sao ở console mặc định. Trong JUL, setUseParentHandlers chi phối việc truyền LogRecord lên parent.
- StreamHandler có buffer; flush() bảo đảm dữ liệu trong handler được chuyển vào ByteArrayOutputStream trước khi chương trình in hai vùng. Vì vậy không thiếu dòng dù Java Handler không tự động flush sau mỗi record.
- Level.INFO cho phép INFO và WARNING được tạo ra ở từng logger; hai Handler Level.ALL không chặn thêm event.
- Formatter chỉ in message và newline, không có timestamp hay tên thread biến thiên, nên kết quả ví dụ có thể đối chiếu nguyên văn.
- ByteArrayOutputStream đóng vai trò sink để học và test, **không phải nơi lưu log production**. Với service thực tế, dùng Handler/Appender được backend hỗ trợ, quản lý rotation/collector và vòng đời.

Nếu bỏ setUseParentHandlers(false), JUL có thể chuyển event tới các Handler của parent/root và log xuất hiện **thêm một lần ở đích khác**. Đây là lỗi phổ biến khi tách logger mà không kiểm soát propagation. Ví dụ không chứng minh rằng mọi hệ thống phân tán có thể gửi hai kênh đúng một lần; tính đúng một lần phụ thuộc nhiều tầng truyền và lưu.

### Mở rộng: routing dựa trên loại event

Trong bài tập, có thể tạo enum BusinessEventType và wrapper emitBusinessEvent(...), kiểm tra input trước khi log. Nếu cần kiểm tra dữ liệu nghiệp vụ, hãy làm điều đó ở domain/application layer rồi chuyển một record bất biến vào logger; đừng đặt toàn bộ quy tắc nghiệp vụ trong một custom Handler.

## 6. Logback: tách appender theo logger và additivity

Với dự án dùng SLF4J + Logback, tạo logger tên cố định com.example.business. Cấu hình ví dụ trong **src/main/resources/logback.xml**:

~~~xml
<configuration>
    <appender name="BUSINESS_FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/business.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level category=BUSINESS %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="TECH_CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.business"
            level="INFO" additivity="false">
        <appender-ref ref="BUSINESS_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="TECH_CONSOLE"/>
    </root>
</configuration>
~~~

**Cơ chế:**

1. Logger com.example.business và các logger con dùng BUSINESS_FILE theo cấu hình hierarchy.
2. additivity="false" dừng quá trình truyền sự kiện từ nhánh business lên root, tránh event nghiệp vụ cũng vào TECH_CONSOLE.
3. Những logger khác tiếp tục sử dụng root và TECH_CONSOLE.
4. Level.INFO trên logger business không có nghĩa mọi INFO là business; tên logger mới là tiêu chí routing.

Ví dụ lời gọi SLF4J tương ứng:

~~~java
// Snippet cần slf4j-api và backend Logback phù hợp.
private static final org.slf4j.Logger BUSINESS_LOG =
    org.slf4j.LoggerFactory.getLogger("com.example.business");

BUSINESS_LOG.info("event_type={} order_id={} result={}",
    "ORDER_CONFIRMED", "O-42", "SUCCESS");
~~~

Đoạn XML và lời gọi SLF4J là ví dụ **cho ứng dụng có dependency phù hợp**, không phải chương trình Java chỉ dùng JDK như ở mục 5. Nếu code thật đặt logger theo class, ví dụ LoggerFactory.getLogger(OrderService.class), thì tên logger là tên class/package và **không tự trỏ tới nhánh com.example.business**. Cần gọi đúng category logger hoặc thiết kế tên package tương ứng.

### Có nhất thiết phải dùng FileAppender?

Không. FileAppender giúp minh họa **tách vật lý**; trong Docker/Kubernetes, viết logs/business.log bên trong image/container có thể gây khó thu thập hoặc mất log khi Pod bị xóa. Có thể chọn nhiều ConsoleAppender được gắn tag category riêng hoặc dùng một appender JSON console rồi định tuyến ở collector. Nếu thật sự ghi file, phải bảo đảm thư mục writable, rotation, retention và forwarder tương ứng.

### Bẫy additivity và logger trùng tên

Nếu có cả appender riêng trên logger business và appender ở root, additivity mặc định có thể làm một event xuất ở cả hai. Việc đặt additivity="false" giúp cách ly, nhưng cũng có nghĩa event business **không đi qua root appender**. Nếu yêu cầu một bản sao cho kênh vận hành chung và một bản riêng cho business, phải thiết kế hai AppenderRef có chủ đích thay vì vô tình ghi trùng.

Ngoài ra, logger tên business dễ bị dùng sai trong code. Với hệ thống lớn, nên bọc API emitBusinessEvent hoặc quy ước category để hạn chế việc developer vô tình gửi lỗi SQL vào business log.

## 7. Log4j 2: logger riêng, Filter và RoutingAppender

Log4j 2 có LoggerConfig, AppenderRef, Filter và các cơ chế routing. Với nhu cầu chia hai kênh cố định, logger riêng thường đủ đơn giản.

Ví dụ **src/main/resources/log4j2.xml** của Log4j 2 Core:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <File name="BUSINESS_FILE"
              fileName="logs/business.log">
            <PatternLayout pattern="%d{ISO8601} %-5level category=BUSINESS %msg%n"/>
        </File>
        <Console name="TECH_CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{ISO8601} %-5level %logger - %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.business"
                level="info" additivity="false">
            <AppenderRef ref="BUSINESS_FILE"/>
        </Logger>
        <Root level="info">
            <AppenderRef ref="TECH_CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Đây là cấu hình **Log4j 2**, không dùng với Logback. Tư tưởng giống phần Logback: business logger đi vào file riêng, root chuyển những logger còn lại tới console, additivity false tránh truyền lên root.

Nếu cần tách theo **Marker** hoặc thuộc tính context thay vì tên logger, Log4j 2 cung cấp MarkerFilter và RoutingAppender. Filter có thể ACCEPT, DENY hoặc NEUTRAL tùy giai đoạn. RoutingAppender phân phát event tới appender đích dựa trên route key; cần đọc chính xác cấu hình theo phiên bản và kiểm thử cả trường hợp route key không tồn tại.

### Khi nào dùng routing động?

Routing theo category hữu hạn như BUSINESS/TECHNICAL/AUDIT có thể hợp lý. Routing động theo customer ID, order ID hoặc user ID thường nguy hiểm vì tạo nhiều đích hoặc file: cardinality lớn, chiếm tài nguyên và khó xoay vòng. Nếu chỉ cần lọc theo order_id, ghi field đó vào log và lọc ở backend tập trung.

### Marker không tự cách ly dữ liệu

Một event mang Marker BUSINESS vẫn có thể bị root appender ghi nếu filter và additivity không giới hạn đích. Khi lưu dữ liệu nhạy cảm, chỉ gắn marker là **không đủ** để bảo đảm cách ly quyền truy cập. Kiểm tra đường đi cuối cùng tới sink, ACL/index, exporter và retention.

## 8. Trong Spring Boot nên chọn cách nào?

Spring Boot thường dùng SLF4J; backend được quyết định bởi dependency (mặc định thường là Logback khi dùng starter logging). Khi cần cấu hình backend nâng cao, có thể dùng **logback-spring.xml** hoặc **log4j2-spring.xml** đúng theo backend.

Ví dụ giảm log kỹ thuật nhiều nhiễu nhưng vẫn giữ business:

**application.properties**

~~~properties
logging.level.root=WARN
logging.level.com.example.business=INFO
~~~

Đây là cấu hình **level**, không phải cấu hình tách sink. Nó cho phép logger business INFO dù root đang ở WARN, với điều kiện đường đi tới appender và các filter khác cho phép. Nếu muốn business sang đích riêng, cần cấu hình appender/logger category trong XML hoặc routing ở collector.

Nếu application.properties có:

~~~properties
logging.file.name=/var/log/app/application.log
~~~

thì đây là cấu hình tên file đầu ra theo cơ chế hỗ trợ của Boot, **không tự biến log nghiệp vụ thành một file riêng**. Khi tự định nghĩa appender trong XML, phải bảo đảm các property mà appender dùng được liên kết đúng.

### Container thường ưu tiên tách logic

Với nhiều replica, có thể phát log JSON console có category và event_type rồi chuyển bằng collector:

~~~json
{"category":"BUSINESS","event_type":"ORDER_CONFIRMED","order_id":"O-42","service":"orders"}
{"category":"TECHNICAL","event_type":"HTTP_REQUEST_DONE","status":201,"service":"orders"}
~~~

Backend có thể đặt index/stream và retention khác nhau, ví dụ BUSINESS truy vấn lâu hơn TECHNICAL nếu yêu cầu hợp lệ. Lúc này việc tách không phụ thuộc vào việc nhiều container cùng ghi file logs/business.log. Tất nhiên collector/backend phải bảo đảm quyền truy cập và khả năng parse các trường; một JSON line không tự mang lại tính bền vững.

## 9. Đừng nhầm business log với domain event hay audit ledger

Đây là phần quan trọng nhất khi đưa tách log nghiệp vụ vào hệ thống thật.

### 9.1. Log quan sát khác nguồn sự thật giao dịch

Giả sử ứng dụng thực hiện:

~~~java
// Minh họa sai về bảo đảm giao dịch: chưa phải chương trình độc lập.
businessLogger.info("event_type=ORDER_PAID order_id={}", orderId);
repository.markPaid(orderId);
~~~

Nếu markPaid thất bại hoặc transaction rollback, dòng log nói đơn hàng đã thanh toán vẫn tồn tại. Đảo thứ tự cũng không biến log thành ghi nhận bảo đảm:

~~~java
repository.markPaid(orderId);
businessLogger.info("event_type=ORDER_PAID order_id={}", orderId);
~~~

Giữa hai lời gọi vẫn có thể xảy ra crash; ghi database thành công nhưng log chưa kịp đi vào sink. Với xử lý bất đồng bộ/collector, ghi thành công tại logger cũng không bảo đảm event đã được giữ ở backend.

**Nếu sự kiện phải được phát hành/lưu không mất cùng giao dịch**, cần thiết kế bền vững thích hợp, ví dụ transactional outbox: lưu trạng thái và outbox record trong cùng database transaction, sau đó một publisher chuyển outbox record tới broker, consumer xử lý idempotent. Đây là cơ chế nghiệp vụ/bền vững, **không phải điều một FileAppender hay logger INFO tự bảo đảm**.

### 9.2. Audit log có yêu cầu riêng

Audit trail có thể cần danh tính tác nhân, hành động, đối tượng, nguồn yêu cầu, thời gian, kết quả, chống sửa đổi và chính sách retention. Chỉ tách một file audit.log không giải quyết toàn bộ yêu cầu này. Cần xác định hệ thống audit được phép tin cậy và bảo vệ dữ liệu theo quy định tổ chức.

Nếu hệ thống yêu cầu chứng cứ pháp lý, tính toàn vẹn hoặc giao dịch quan trọng, cần kiến trúc audit/event store có cơ chế bền vững, phân quyền và kiểm chứng riêng. Không tái dùng business log best-effort làm nguồn duy nhất để quyết toán hoặc đối soát tài chính.

### 9.3. Nhận diện event trùng lặp

Trong hệ thống có retry, redelivery hoặc nhiều sink, cùng một sự kiện nghiệp vụ có thể được ghi hơn một lần. event_id giúp đối chiếu bản ghi lặp. Tuy nhiên event_id chỉ hữu ích nếu được phát sinh ổn định **cho cùng sự kiện**, không tạo ID mới mỗi lần retry rồi coi đó là event khác. Consumer downstream vẫn nên có quy tắc deduplicate/idempotency khi cần.

Ngoài event_id, có thể dùng correlation_id/causation_id để nối một chuỗi nghiệp vụ, nhưng phải định nghĩa rõ ý nghĩa và vòng đời từng trường, tránh trùng với trace_id.

## 10. Đề xuất schema business log rõ ràng

Trước khi triển khai, thiết kế một hợp đồng event tối thiểu:

~~~text
category       = BUSINESS
event_type     = ORDER_CONFIRMED
event_version  = 1
event_id       = evt-7d6e
entity_type    = ORDER
entity_id      = O-42
outcome        = SUCCESS
service        = order-service
occurred_at    = 2026-11-10T02:30:00Z
trace_id       = ...
attributes     = {currency: "VND", amount_minor: 125000}
~~~

Những ví dụ này chỉ mang tính minh họa dữ liệu. Khi ghi JSON, hãy chọn kiểu số/boolean/null đúng nghĩa; không ép mọi field thành chuỗi nếu backend cần so sánh số.

### Tên sự kiện

Ưu tiên tên ổn định ở thì quá khứ hoặc mô tả trạng thái đã đạt, ví dụ ORDER_CONFIRMED, PAYMENT_FAILED, SHIPMENT_CREATED. Tránh tạo event_type bằng chuỗi chứa ID như ORDER_CONFIRMED_O-42 vì làm tăng cardinality và phá khả năng tổng hợp.

### Sự kiện thành công và thất bại

Sự kiện nghiệp vụ bị từ chối hợp lệ không nhất thiết là exception:

~~~json
{"category":"BUSINESS","event_type":"ORDER_REJECTED","entity_id":"O-42","reason_code":"OUT_OF_STOCK","outcome":"REJECTED"}
~~~

Lỗi kết nối database hoặc timeout từ gateway là kỹ thuật; có thể ghi thêm business outcome sau khi hệ thống xác định quyết định nghiệp vụ, nhưng cần tránh phát cả ORDER_REJECTED khi thực tế kết quả thanh toán đang UNKNOWN. Việc đặt outcome phải tuân theo state machine thực tế, không suy đoán từ một lỗi network.

### Chỉ ghi thuộc tính được cho phép

Không đưa số thẻ đầy đủ, mật khẩu, access token, cookie phiên, giấy tờ cá nhân, thông tin sức khỏe hoặc payload chứa PII vào business log. Kể cả order_id, customer_id và user_id cũng có thể là dữ liệu định danh gián tiếp; hãy kiểm soát mục đích và phân quyền truy cập. Có thể dùng ID nội bộ/giả danh theo chính sách, che/mask dữ liệu trước khi vào logger.

## 11. Phân luồng log trong môi trường phân tán

Một request đặt hàng có thể đi qua API, order-service, payment-service và inventory-service:

~~~text
HTTP request
    |
    v
order-service (BUSINESS: ORDER_PLACED)
    |             \
    |              \-- TECHNICAL: request latency / DB query
    v
payment-service (BUSINESS: PAYMENT_CONFIRMED)
    |             \
    |              \-- TECHNICAL: gateway retry / circuit breaker
    v
inventory-service (BUSINESS: STOCK_RESERVED)
                  \
                   \-- TECHNICAL: cache miss / API error
~~~

Để nối các log giữa service, sử dụng trace_id/span_id từ tracing context hợp lệ và business correlation_id khi cần. **Trace ID không thay thế entity_id**: một đơn hàng có thể đi qua nhiều trace, và một trace có thể chứa nhiều thao tác nghiệp vụ.

### MDC và context propagation

MDC của SLF4J có thể mang request_id, trace_id và các thuộc tính an toàn phục vụ logging. Nhưng MDC thường gắn với thread; khi dùng ExecutorService, CompletableFuture hoặc reactive pipeline, cần truyền context đúng scope và dọn/khôi phục trong finally. Đừng tin rằng MDC tự chuyển qua thread mới hay HTTP call.

Tương tự, nếu dùng Log4j 2 Thread Context, phải kiểm tra cơ chế capture/restore trong async tasks. Với OpenTelemetry, dùng instrumentation/context propagation phù hợp để trace ID trong business và technical log thuộc cùng trace.

### Chia retention và quyền truy cập theo loại

Business log có thể hữu ích cho phân tích hành trình dài hơn technical DEBUG; security/audit log có thể cần quyền xem hạn chế hơn. Chính sách phải xuất phát từ mục đích và yêu cầu pháp lý/thực tế, không có một số ngày lưu chuẩn cho mọi ứng dụng.

Nếu chỉ tách file nhưng tất cả vẫn gửi tới một index không có phân quyền riêng, hệ thống chưa thực sự cách ly dữ liệu. Kiểm tra đường đi từ code đến appender, stdout/container runtime, collector, backend và người dùng cuối.

## 12. Performance, reliability và rủi ro của routing

### 12.1. Chi phí của log

Các business event thường có giá trị quan sát cao, nhưng log đồng bộ và định dạng JSON phức tạp có thể ảnh hưởng latency. Parameterized logging giảm chi phí dựng thông điệp khi level tắt, song không biến đối tượng mutable thành snapshot nhất quán và không tránh việc appender block.

Khi dùng async appender, cần nắm queue capacity, chính sách khi queue đầy (block/drop/chuyển đồng bộ tùy provider), flush và shutdown. Business event quan trọng **không nên chỉ dựa vào một queue log không bền vững** để đáp ứng nghiệp vụ.

### 12.2. Quy tắc routing phải có nhánh dự phòng

Khi category bị thiếu, sai chính tả hoặc event_type mới chưa được khai báo, cần định nghĩa có giữ vào technical/default stream, chuyển sang quarantine hay báo lỗi. Không im lặng loại bỏ record không khớp mà không có metric/alert, đặc biệt nếu team đang dựa vào kênh business để quan sát sự cố.

### 12.3. Tránh logging recursion

Custom Handler/Appender tự gọi logger vào cùng sink có thể tạo vòng lặp và stack overflow/hàng đợi tràn. Chẩn đoán lỗi sink qua cơ chế trạng thái/error handling được framework cung cấp, không gọi lại đúng pipeline đang lỗi mà thiếu kiểm soát.

### 12.4. Một event không đồng nghĩa đúng một bản sao

Trùng do logger additivity là lỗi cấu hình có thể sửa được. Nhưng chuyển tiếp async, retry collector hoặc delivery của broker có thể tạo bản ghi lặp ở backend ngay cả khi application chỉ gọi logger một lần. Đừng tuyên bố exactly-once end-to-end nếu chưa có cơ chế giao dịch/dedup cho toàn đường đi.

## 13. Kiểm thử tách log nghiệp vụ

Một bộ kiểm thử hữu ích nên kiểm tra đồng thời **đúng đích, đúng schema và đúng dữ liệu**:

| Ca thử | Dữ liệu tạo | Kỳ vọng |
| --- | --- | --- |
| Ghi BUSINESS chuẩn | ORDER_CONFIRMED | Chỉ business sink nếu cấu hình chủ ý cách ly; đủ event_type/entity_id |
| Ghi TECHNICAL | HTTP_REQUEST_DONE hoặc exception | Chỉ technical sink; không lọt vào business |
| Sai level | Business INFO, Technical WARN/ERROR | Routing theo category/logger, không theo suy đoán từ level |
| Parent logger | Business logger có appender riêng và root appender | Không có bản sao vô tình do additivity |
| Thiếu category | Event không có loại | Áp dụng default/quarantine có quan sát được |
| Song song | Nhiều request và thread pool | Không lẫn correlation_id/MDC, không ghép hỏng bản ghi |
| Retry nghiệp vụ | Cùng operation được xử lý lại | Quy ước event_id và deduplicate phản ánh đúng logic |
| Sink lỗi hoặc queue đầy | Backend log tạm không khả dụng | Quan sát retry/drop/backpressure và không nhầm với giao dịch |
| Bảo mật | Payload chứa dữ liệu nhạy cảm | Redaction/allowlist loại bỏ dữ liệu không được phép |
| Container restart | Pod/container bị tạo lại | Biết log local có thể mất, collector/backend có retention riêng |

Với ví dụ Java 17 ở mục 5, cách kiểm thử cơ bản là biên dịch, chạy rồi so sánh toàn bộ stdout. Nếu event TECHNICAL lẫn vào phần BUSINESS, hoặc event BUSINESS xuất hai lần, cần xem các Handler, logger hierarchy và propagation.

Khi dùng Logback/Log4j 2, nên thực hiện integration test với **đúng file cấu hình và provider sẽ deploy**. Một test chỉ giả lập Logger API mà không nạp appender thực không thể chứng minh routing hoạt động. Đặc biệt, test environment có thể dùng logback-test.xml hoặc log4j2-test.xml khác với production.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng khắc phục |
| --- | --- | --- |
| business.log có đầy lỗi SQL | Dùng INFO/ERROR làm tiêu chí category, hoặc gọi sai business logger | Tách category ở code/domain, dùng logger name/marker rõ ràng |
| BUSINESS vừa trong file riêng vừa trên console | additivity truyền event lên root | Xem logger hierarchy, đặt additivity=false khi muốn cách ly |
| Không có business log nhưng technical vẫn có | Sai logger name, sai file cấu hình, level/filter chặn, appender lỗi | Kiểm tra backend đang chạy và đường đi của event |
| Chỉ còn log trên local container | Appender ghi file không được thu gom | Console/collector, volume + forwarder khi cần, retention backend |
| Thiếu ORDER_CONFIRMED sau crash | Log chưa flush, event ghi trước/ngoài transaction, queue mất | Phân biệt log quan sát và outbox/event store cho yêu cầu bền vững |
| Nhiều ORDER_CONFIRMED cho cùng order | Retry, dedup chưa rõ, appender/collector phát lặp | Xem event_id, operation_id, cơ chế delivery và additivity |
| Business log thiếu trace_id | Không propagate context, không có span hiện tại | Kiểm tra instrumentation, MDC và async boundary |
| Log lộ dữ liệu khách hàng | Ghi toàn bộ entity/payload/exception | Dùng allowlist field, mask thông tin, kiểm tra redaction |
| JSON log parse sai | Escape newline/quote sai, schema không thống nhất | Dùng encoder JSON chuẩn và kiểm thử parser |
| Kho business bùng nổ dung lượng | Một file per entity, log trùng hoặc quá nhiều event chi tiết | Giảm cardinality route, log event có ý nghĩa, cấu hình retention |

### Quy trình chẩn đoán thực tế

1. Tìm đúng sự kiện trong code và xác định category theo ý nghĩa nghiệp vụ.
2. Xác định logger/backend thực tế của runtime (JUL, Logback, Log4j 2), không suy từ tên dependency.
3. Theo dõi event qua logger → level/filter → additivity → appender → collector → backend.
4. Kiểm tra đích nào nhận event, có trùng hay mất, và liệu backend có đọc đúng schema.
5. Với business event liên quan transaction, xác định chính xác thời điểm trạng thái được commit và yêu cầu bền vững.
6. Kiểm tra quyền truy cập và dữ liệu nhạy cảm ở **mọi** kênh mà event có thể đi qua.

## 15. Bài tập tự luyện

**Bài 1 – Đổi chính sách định tuyến JUL.** Từ BusinessLogRoutingDemo.java, thêm một dòng TECHNICAL.severe("database unavailable"). Dự đoán và xác nhận dòng này chỉ xuất trong TECHNICAL. Sau đó cố ý bỏ setUseParentHandlers(false), quan sát việc truyền event tới parent handler theo cấu hình JUL hiện tại; giải thích vì sao đó là vấn đề propagation.

**Bài 2 – Logback logger naming.** Với cấu hình ở mục 6, dùng LoggerFactory.getLogger("com.example.business") và LoggerFactory.getLogger("com.example.OrderService") để phát hai event khác nhau. Kiểm tra business.log và console. Thử additivity=true rồi giải thích các bản sao không mong muốn.

**Bài 3 – Structured log.** Thiết kế ba event ORDER_PLACED, ORDER_REJECTED và PAYMENT_CONFIRMED dưới dạng JSON line có category, event_type, event_id, entity_id, outcome và timestamp. Viết phép kiểm tra schema để xác nhận mọi event đủ trường bắt buộc và không chứa token hay payload nhạy cảm.

**Bài 4 – Sự kiện và transaction.** Vẽ sơ đồ transaction cập nhật ORDER_PAID, lời gọi logger, DB commit và thời điểm crash có thể xảy ra. Xác định các trường hợp log xuất hiện dù transaction rollback hoặc trạng thái đã commit nhưng thiếu log. Đề xuất outbox khi cần chuyển event đáng tin cậy.

**Bài 5 – Kubernetes.** Cho hai replica Java xuất log JSON console, collector tách category BUSINESS và TECHNICAL. Tạo kịch bản backend BUSINESS tạm không khả dụng; xác định nơi retry/buffer/drop được cấu hình, cách đo lường và cách truy vết event_id khi nhận bản sao lặp.

## 16. Ghi nhớ

Tách log nghiệp vụ bắt đầu bằng **phân loại ý nghĩa sự kiện** rồi mới chọn logger, marker, field, filter và appender. Mức INFO/WARN/ERROR không thay thế category. Một ứng dụng Java có thể tách bằng logger name và additivity trong Logback/Log4j 2, hoặc bằng Logger/Handler trong JUL; trong container, tách theo field JSON ở collector thường dễ quản trị hơn tách nhiều file cục bộ.

Business log hỗ trợ quan sát hành trình nghiệp vụ nhưng **không tự bảo đảm giao dịch, đúng một lần hay lưu trữ bền vững**. Đối với nghiệp vụ quan trọng, thiết kế outbox/audit store đúng yêu cầu, giữ event_id và schema ổn định, ngăn rò rỉ dữ liệu nhạy cảm và kiểm thử đường đi của log từ ứng dụng đến backend.

### Tài liệu tham khảo

- Oracle Java 17 – Logger (logger name, handler inheritance): https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Oracle Java 17 – Handler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html
- Oracle Java 17 – StreamHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/StreamHandler.html
- SLF4J Marker API: https://www.slf4j.org/apidocs/org/slf4j/Marker.html
- Logback – Architecture, logger hierarchy, additivity: https://logback.qos.ch/manual/architecture.html
- Logback – Configuration: https://logback.qos.ch/manual/configuration.html
- Log4j 2 – Filters: https://logging.apache.org/log4j/2.x/manual/filters.html
- Log4j 2 – Delegating Appenders/Routing: https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html
- Spring Boot – Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
