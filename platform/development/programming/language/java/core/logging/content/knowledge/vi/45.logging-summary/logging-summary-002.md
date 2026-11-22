# Luồng từ logger đến đích ghi — Tổng kết Java Logging

## 1. Bức tranh toàn cảnh

Khi một ứng dụng Java gọi logger.info(...) hoặc logger.error(..., exception), dòng log **không tự động xuất hiện ngay trong file hay dashboard**. Lời gọi đi qua các thành phần có trách nhiệm khác nhau: logging API, backend/provider, quyết định level và filters, event/context, appender hoặc handler, encoder/formatter, tài nguyên đầu ra, rồi có thể qua shipper/collector và hệ thống lưu trữ tập trung.

Một sơ đồ tổng quát:

~~~text
Ứng dụng Java
    |
    | logger.info("Order {} created", orderId)
    v
Logging API / facade (SLF4J, Log4j API hoặc JUL)
    |
    | Provider/binding/implementation thực tế
    v
Logger / configuration / effective level / filters
    |
    +-- disabled / DENY ----------> không có log ở đích
    |
    v
Logging event: time, level, logger name, message,
               arguments, Throwable, MDC/ThreadContext ...
    |
    +-- sync ----------------------+
    |                             |
    +-- async queue / ring buffer-+--> [bounded; có thể block/drop]
                                  |
                                  v
                      Appender hoặc JUL Handler
                                  |
                       filters, routing, failover
                                  |
                                  v
                        Formatter / Layout / Encoder
                                  |
                           text, JSON, bytes
                                  |
                                  v
                   Console / File / Socket / Syslog / ...
                                  |
                 +----------------+----------------+
                 |                                 |
             local sink                    shipper/collector
                                                   |
                                           parse/enrich/redact
                                                   |
                                                   v
                                            index / archive
                                                   |
                                                   v
                                             query / alert
~~~

**Điểm chính:** “đã gọi logger” không đồng nghĩa “log đã được nhận”, “đã enqueue” không đồng nghĩa “đã ghi bền vững”, và “đã ghi stdout” không đồng nghĩa “đã index để tìm trên dashboard”. Mỗi ranh giới có thể có filter, buffer, lỗi kết nối hoặc retry.

Bài tổng kết này mô tả **luồng từ logger đến đích ghi** trong Java Core Logging, sau đó nối tới các backend thông dụng như Logback, Log4j 2 và hệ thống observability.

## 2. Các tên gọi dễ nhầm

| Thành phần | Là gì? | Điều thường không phải |
| --- | --- | --- |
| **Logger** | Điểm vào để code phát sự kiện, theo tên hoặc class | Không nhất thiết tự ghi file |
| **Logging API** | Interface người lập trình gọi | Không nhất thiết là implementation |
| **SLF4J** | Facade/API có provider chọn backend | Không phải một file appender riêng |
| **Backend/provider** | Hệ thống thực thi logging như Logback | Không phải dashboard log |
| **Level** | Mức của yêu cầu: INFO, WARN, ERROR... | Không phải bảo đảm sẽ được lưu |
| **Filter** | Điều kiện ACCEPT/DENY/NEUTRAL tùy backend | Không nhất thiết chỉ chạy ở một chỗ |
| **LogEvent / LogRecord** | Dữ liệu của một sự kiện logging | Không đồng nghĩa một dòng text |
| **MDC/ThreadContext** | Ngữ cảnh gắn với thread/request | Không tự truyền qua mọi async boundary |
| **Appender (Logback/Log4j 2)** | Thành phần nhận sự kiện và xuất tới đích | Không giống formatter |
| **Handler (JUL)** | Thành phần xuất LogRecord của java.util.logging | Không phải Logback Appender |
| **Layout/Formatter** | Chuyển event thành biểu diễn text | Không nhất thiết tự làm I/O |
| **Encoder** | Đưa thông tin thành byte/format để ghi | Không phải công cụ parsing phía collector |
| **Sink** | Console, file, network endpoint, stream... | Không mặc nhiên là durable storage |
| **Collector** | Thu nhận và xử lý log từ các nguồn | Không nhất thiết đã index sự kiện |
| **Index/storage** | Đích lưu phục vụ truy vấn hoặc archive | Không tự đảm bảo đúng retention |

Một backend có thể tích hợp các bước khác nhau trong cùng class. Sơ đồ phía trên là **mô hình tư duy**, không phải một call stack cố định dùng chung cho tất cả các phiên bản và framework.

## 3. Bước 1: Ứng dụng gọi logger

Ví dụ ứng dụng dùng SLF4J:

~~~java
// Fragment: cần org.slf4j.Logger và LoggerFactory trong dependency.
private static final org.slf4j.Logger log =
    org.slf4j.LoggerFactory.getLogger(OrderService.class);

public void createOrder(String orderId) {
    log.info("eventCode=ORDER_CREATE_REQUESTED orderId={}", orderId);
}
~~~

Một lời gọi log chứa:

- **Level được yêu cầu:** INFO trong trường hợp này.
- **Logger name:** thường là tên class OrderService hoặc tên chủ động đặt.
- **Message template:** text có placeholder, có thể được format muộn.
- **Arguments:** giá trị orderId.
- **Throwable (tùy chọn):** để backend giữ stack trace và cause chain.
- **Context:** requestId/traceId từ MDC hoặc instrumentation, nếu có.

Việc tách message template và arguments giúp tránh ghép chuỗi không cần thiết và cho backend xử lý thông điệp có điều kiện. Tuy nhiên, **mọi đối số biểu thức vẫn được Java đánh giá trước khi gọi method**:

~~~java
// Fragment minh họa: expensiveLookup() vẫn chạy trước log.debug(...).
log.debug("Details: {}", expensiveLookup());

// Nếu tính toán đắt, guard trước:
if (log.isDebugEnabled()) {
    log.debug("Details: {}", expensiveLookup());
}
~~~

Một số API còn hỗ trợ Supplier hoặc fluent logging cho phép chuẩn bị dữ liệu trễ, nhưng phải dùng đúng version/binding. Không tuyên bố mọi cách parameterized logging đều tự động tránh được chi phí gọi method tạo argument.

**Về exceptions:** khi muốn gắn throwable, nên dùng overload có nghĩa rõ:

~~~java
log.error("Order creation failed", exception);
~~~

Không thay bằng printStackTrace() cộng một lần logger.error nữa. printStackTrace() ghi trực tiếp một luồng khác, bỏ qua cấu hình level, MDC và appender của backend.

## 4. Bước 2: Logging API chọn implementation thật

### 4.1. SLF4J facade và provider

SLF4J định nghĩa API mà application/library sử dụng. Với **SLF4J 2.x**, cơ chế **ServiceLoader** tìm **provider** trong classpath/module path; provider định tuyến tới backend như Logback Classic, Log4j 2 thông qua adapter phù hợp, hoặc JUL thông qua slf4j-jdk14.

~~~text
Ứng dụng gọi org.slf4j.Logger
            |
            v
        slf4j-api 2.x
            |
        ServiceLoader
            |
            +--> Logback Classic provider --> Logback Core Appenders
            |
            +--> Log4j 2 SLF4J provider --> Log4j Core Appenders
            |
            +--> slf4j-jdk14 provider --> JUL Logger/Handler
~~~

Trên cùng một runtime, cần cấu hình provider tương thích với SLF4J API, tránh nhiều provider cạnh tranh. **Không có provider**, SLF4J 2.x có thể cảnh báo và dùng NOP implementation, vì vậy code có gọi log mà console/file vẫn hoàn toàn không có sự kiện. **Có nhiều provider**, SLF4J cảnh báo và không nên phụ thuộc việc provider nào được chọn tình cờ.

Với **SLF4J 1.7 trở xuống**, thuật ngữ là **binding** với cơ chế StaticLoggerBinder. Không lắp một binding 1.7 rồi cho rằng SLF4J 2.x sẽ sử dụng như provider 2.x. Khi nâng version, kiểm tra dependency tree và cảnh báo bootstrap.

Ví dụ phụ thuộc cần đối chiếu theo version:

~~~text
slf4j-api (API)
logback-classic (provider + Logback Classic)
logback-core (thành phần backend)
~~~

Đây là tên artifact minh họa, **không phải BOM hay số version cụ thể**. Với Log4j 2, provider/adaptor artifact và dependency phải tương thích phiên bản. Tham khảo tài liệu chính thức trước khi chọn.

### 4.2. JUL và Log4j API khác gì?

- **JUL / java.util.logging:** có sẵn trong JDK, Logger → LogRecord → Handler → Formatter → output. Không bắt buộc SLF4J.
- **Log4j API + Log4j Core:** Logger từ API đi qua LoggerContext/Configuration/LoggerConfig, Filters, AppenderRef/Appender và Layout.
- **SLF4J + Logback:** code gọi facade, provider Logback tạo event và dispatch tới appenders theo logger hierarchy và config.

**Không nên dùng “SLF4J logger” làm tên cho toàn bộ backend**, vì quyết định level, routing, encoding và output thường thuộc implementation/configuration.

### 4.3. Bridge giữa logging frameworks

Thư viện có thể dùng JUL hoặc Commons Logging trong khi ứng dụng chuẩn hóa về SLF4J/Logback. Bridge giúp đưa các yêu cầu logging vào backend mục tiêu, nhưng một **vòng lặp bridge** có thể dẫn tới recursion hoặc mất kiểm soát:

~~~text
JUL -> SLF4J bridge -> SLF4J provider quay lại JUL -> ...
~~~

Cần xác định **một hướng routing**, loại bridge/provider đối nghịch, kiểm tra dependency tree và chạy integration test. Không copy toàn bộ jar bridge để "cho chắc" vì chúng không phải càng nhiều càng tốt.

## 5. Bước 3: Logger name và effective level

Trong Logback/Log4j 2, logger name thường dùng hierarchy dấu chấm:

~~~text
ROOT
  |
  +-- com.example
           |
           +-- com.example.orders
                      |
                      +-- com.example.orders.OrderService
~~~

Một logger không có level riêng có thể nhận **effective level** từ cấu hình gần nhất trên hierarchy. Ví dụ:

~~~text
ROOT: INFO
com.example.orders: DEBUG
com.example.orders.OrderService: (không đặt riêng)
~~~

Ở Logback, OrderService kế thừa DEBUG từ com.example.orders. Vì vậy debug có thể được kích hoạt cho vùng orders dù ROOT cấu hình INFO.

Quy tắc level thông thường của Logback:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

Một logging request được bật nếu severity của request **không thấp hơn effective level** (chưa tính filters). Nếu effective level là INFO thì DEBUG bị loại tại bước kiểm tra level, còn INFO, WARN, ERROR có thể đi tiếp.

**Đừng suy luận level từ text message:** INFO có thể chứa chữ "error", JUL dùng SEVERE thay ERROR. Các backend có level bổ sung (ví dụ Log4j 2 có FATAL); cần mapping theo công cụ đang chạy.

**Một chi tiết quan trọng của Logback:** một event đã được bật ở logger con có thể được forward đến appender của tổ tiên theo **additivity**; level của logger cha không nhất thiết được xét lại như một cổng mới cho event đó. Vì vậy **ROOT=INFO** không bảo đảm appender ROOT sẽ không thấy DEBUG được tạo bởi logger con có effective level DEBUG. Nếu muốn filter ở chính appender, cấu hình filter/threshold thích hợp.

## 6. Bước 4: Filters và thứ tự kiểm tra

Không chỉ level quyết định event có đi tiếp hay không. Filters cho phép chọn theo logger, marker, context, message, appender và điều kiện đặc thù.

Ví dụ:

- Loại health-check success log theo rule.
- Giữ WARN/ERROR nhưng giảm các DEBUG có volume cao.
- Chặn log chứa field không được phép xuất.
- Route audit security tới sink khác có chính sách riêng.
- Từ chối các events không phù hợp schema hoặc nội dung quá lớn.

**Thứ tự filters không giống nhau ở mọi framework:**

- **JUL:** Logger kiểm tra level, rồi Logger Filter nếu có; khi qua, gửi LogRecord tới Handlers. Mỗi Handler có level/filter riêng.
- **Logback:** có **TurboFilter** sớm, sau đó basic level selection và logging event, rồi **Appender filters** cùng routing.
- **Log4j 2:** Filter có thể hiện diện tại Logger stage, LoggerConfig, AppenderRef/AppenderControl và Appender; API có trạng thái ACCEPT/DENY/NEUTRAL.

Vì vậy sơ đồ “level → filter → event” là **sơ đồ đơn giản**, không được coi là thứ tự máy móc cho mọi implementation. Muốn chẩn đoán chính xác phải xem tài liệu tương ứng và active configuration.

**Tại nơi event bị lọc**, code gọi logger không ném exception chỉ vì một bản ghi DEBUG không được xuất. Nếu người dùng nói "Tôi đã gọi logger mà không thấy log", hãy xem từng filter, level và đích trước khi khẳng định logger bị lỗi.

## 7. Bước 5: Tạo logging event/LogRecord và context

Một sự kiện logging chứa nhiều thông tin hơn text hiển thị:

| Field | Mô tả | Nguồn thường gặp |
| --- | --- | --- |
| Timestamp | Thời điểm tạo log/event | Clock/framework |
| Level | INFO/WARN/ERROR hoặc JUL Level | Method log + backend |
| Logger name | Component/class tạo event | Logger instance |
| Thread name | Thread phát event | Runtime/logging backend |
| Template và arguments | Message trước/sau format | Logger call |
| Throwable | Exception và cause chain | logger.error(msg, ex) |
| MDC/ThreadContext | requestId/traceId/correlation IDs | Request/tracing context |
| Marker/structured fields | eventCode, operation, outcome | SLF4J/fluent/backend API |
| Caller location | Class/method/file/line | Stack walking nếu được bật |

**Một event có thể được in thành nhiều dòng** do throwable stack trace, và cũng có thể tạo hai outputs ở hai sink; không đồng nhất số dòng/số output với số events.

Trong **JUL**, Java API dùng **LogRecord** giữa Logger và Handler. Khi một LogRecord bị chuyển sang thread khác, các thông tin caller có thể được suy ra trễ và không luôn đúng nếu backend/handler chưa nắm context tại thread tạo; tài liệu Oracle lưu ý việc buộc source class/method inference trước khi handoff khi cần.

Trong Logback/Log4j 2, async appenders/loggers cũng có lưu ý **caller data**: tính stack location đắt và có thể cần chủ động bật/capture tại thời điểm phù hợp. Không bật includeCallerData/includeLocation tràn lan nếu không có nhu cầu; chi phí và behavior phải đo đúng backend.

## 8. MDC/ThreadContext trên đường đi

**Mapped Diagnostic Context (MDC)** cho phép gắn field chung như requestId lên những event phát trong cùng context:

~~~java
// Fragment có SLF4J; requestId đến từ middleware đáng tin.
org.slf4j.MDC.put("requestId", requestId);
try {
    service.process();
} finally {
    org.slf4j.MDC.remove("requestId");
}
~~~

Trong Logback PatternLayout, %X{requestId} có thể xuất giá trị MDC nếu event giữ được context:

~~~text
2026-11-10T03:30:05Z INFO requestId=req-42 com.example.OrderService - Order created
~~~

**Bẫy thread pools:** MDC thường gắn với thread context. Khi submit task sang ExecutorService, @Async, CompletableFuture hoặc reactive pipeline, dữ liệu không mặc nhiên truyền đúng qua mọi thread. Nếu quên cleanup, requestId của request cũ có thể xuất trong log của request tiếp theo vì worker thread được tái sử dụng.

- Tạo/validate requestId ở entry boundary.
- Đặt MDC khi bắt đầu xử lý.
- Cleanup bằng try/finally hoặc scope API tương ứng.
- Chuyển context qua async task có kiểm soát; không copy ThreadLocal bừa.
- Dùng trace instrumentation phù hợp cho Spring WebFlux/Reactor.
- Cấu hình encoder/appender thực sự xuất MDC.
- Không tin header do client cung cấp mà không validate và xác định trust boundary.

**MDC chứa context kỹ thuật, không phải nơi nhét raw request body, token hoặc PII.** Với nhiều async hops, kiểm tra kết quả tại index, không chỉ thread đang chạy controller.

## 9. Bước 6: Appender/Handler chọn đích

Trong **Logback**, Appender là interface/đối tượng nhận logging event và thực hiện xuất. Một số appender phổ biến:

- ConsoleAppender: viết ra stream console.
- FileAppender: ghi file thông thường.
- RollingFileAppender: ghi file active và rollover/archive theo chính sách.
- AsyncAppender: đưa events vào queue để xử lý trên thread khác rồi chuyển tới appender đích.
- Một số appender/network/custom: gửi tới dịch vụ hoặc protocol tương ứng.

Trong **Log4j 2**, Appender thường dùng Layout/Manager để serialize và ghi vào Console, File, RollingFile, Socket hoặc đích khác. LoggerConfig giữ các AppenderRef, level/filters và liên kết hierarchy.

Trong **JUL**, khái niệm tương ứng ở đầu ra là **Handler**: ConsoleHandler, FileHandler, SocketHandler hoặc Handler tùy chỉnh. Handler có Formatter và Filter/Level; ConsoleHandler mặc định dùng **System.err**, không nên luôn nói mọi console log của JUL đi System.out.

Một **Logger** có thể gửi cùng một event tới nhiều appenders, ví dụ Console và File. Điều đó là **fan-out có chủ đích** nếu được cấu hình đúng. Nếu cùng một ConsoleAppender được tham chiếu ở logger con và ROOT theo additivity, event có thể xuất trùng tại cùng đích.

Để hiểu mất log hoặc trùng log, cần hỏi:

1. Logger nào đã nhận request?
2. Level/filter nào cho phép?
3. Appender/Handler nào thực sự được tham chiếu?
4. Có parent forwarding/additivity không?
5. Appender đã start và đủ quyền tài nguyên chưa?
6. Encoder/Layout được gắn đúng không?
7. Có queue async, network retry hoặc collector đọc lại không?

## 10. Additivity: một event có thể tới nhiều appenders

Ví dụ Logback có logger hierarchy:

~~~text
Logger com.example.orders
    |
    +--> CONSOLE appender tại logger con
    |
    +--> (additivity=true) ROOT
                           |
                           +--> CONSOLE appender tại ROOT
~~~

Nếu **cùng CONSOLE appender** được tham chiếu ở hai cấp, một lời gọi log có thể xuất **hai bản ở cùng đích**. Trong Logback, additivity mặc định thường là true. Nếu chỉ muốn một console copy, có thể gắn appender một lần ở ROOT hoặc cấu hình additivity=false khi logger con có route riêng.

**Không đặt additivity=false một cách mù quáng:** logger con không có appender riêng có thể bị mất output. Cần test những logger namespace bị ảnh hưởng, đặc biệt security/audit.

Ví dụ Logback tránh tham chiếu CONSOLE lặp:

~~~xml
<configuration>
  <appender name="CONSOLE"
      class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n%ex{full}</pattern>
    </encoder>
  </appender>
  <logger name="com.example.orders" level="DEBUG"/>
  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

Đây là **logback.xml minh họa**. Các events từ com.example.orders được bật theo effective level DEBUG và có đường tới CONSOLE ở ROOT, dù ROOT level là INFO. Trường hợp cụ thể còn phụ thuộc filters/appenders khác nếu ứng dụng có thêm cấu hình.

Nếu muốn audit đi tới kho riêng, có thể thêm logger dedicated và additivity=false, nhưng phải đảm bảo đã gắn audit appender, policy failover và retention riêng. Không dùng chung file audit và debug nếu nghĩa vụ lưu trữ khác nhau.

## 11. Bước 7: Layout/Formatter/Encoder làm gì?

Sau khi sự kiện được chấp nhận và đến appender, backend thường cần chuyển event thành output:

~~~text
LoggingEvent / LogRecord
   |
   +--> PatternLayout / Formatter --> text
   |
   +--> JSON encoder/template ------> structured JSON
   |
   +--> binary/network serializer --> protocol bytes
   |
   v
byte stream / connection / storage
~~~

**Layout/Formatter** định nghĩa hình thức hiển thị: timestamp, level, logger, MDC, message và exception. **Encoder** thường kết hợp layout/serialization với việc sinh bytes, charset, framing để appender có thể ghi. Tên class/ranh giới chính xác tùy framework, nên không buộc mọi backend phải có cả hai object độc lập.

Ví dụ Logback text pattern:

~~~text
%d{ISO8601} %-5level [%thread] %logger requestId=%X{requestId:-} - %msg%n%ex{full}
~~~

Điều này có thể xuất ra:

~~~text
2026-11-10 10:30:05,123 INFO  [http-4] com.example.OrderService requestId=req-42 - Order created
~~~

Định dạng timestamp thực phụ thuộc pattern/version/timezone. Tương tự, stack trace khi có throwable có thể thêm nhiều dòng.

**Encoding và parsing là hai hướng khác nhau:**

- **Encoder ở Java**: LogEvent → text/JSON/bytes.
- **Parser ở collector**: bytes/text/JSON → field đã chuẩn hóa cho tìm kiếm.

Một lỗi parse timestamp tại collector có thể do encoder đổi format, không phải do Logger.info bị lỗi.

## 12. Structured JSON vs text: chọn theo contract

Text pattern có thể đọc trực tiếp bằng mắt, nhưng dễ bị ảnh hưởng bởi dấu cách, delimiter, multiline stack traces và thay đổi layout. JSON Lines có cấu trúc thường dễ query hơn:

~~~json
{"timestamp":"2026-11-10T03:30:05Z","level":"INFO","service":"order-service","logger":"com.example.OrderService","requestId":"req-42","eventCode":"ORDER_CREATED","message":"Order created"}
~~~

Nếu dùng JSON Lines:

- **Mỗi event thành một JSON object trên một dòng vật lý**.
- Message chứa dấu quote, backslash hoặc newline được escape bằng JSON serializer.
- Timestamp/timezone được định nghĩa rõ; không tự hiểu tất cả giờ là UTC.
- Field types nhất quán: durationMs là số, không lúc là chuỗi "17ms".
- Exception có thể là field string escape newline hoặc object nested.
- Không thêm dynamic keys không giới hạn; kiểm soát index schema/cardinality.
- Không ghép JSON bằng phép nối string thủ công khi có dữ liệu không tin cậy.
- Có version hoặc contract cho field, cùng golden fixture tests.

**Java standard library không có parser JSON tổng quát bắt buộc phải dùng ở mọi ứng dụng**. Để serialize JSON chuẩn, nên dùng encoder/backend hoặc thư viện JSON được duy trì, không split message thủ công. Nếu Log4j 2 dùng JSON Template Layout hoặc Logback dùng JSON encoder tương thích, cần kiểm tra dependency và version thực tế.

**JSON không tự đảm bảo an toàn.** Nó có thể khiến trường PII dễ tìm hơn; phải làm data minimization/redaction tại nguồn và downstream.

## 13. Bước 8: Đồng bộ và bất đồng bộ

### Synchronous path

~~~text
Application thread
    -> Logger enabled check
    -> event/filter
    -> Appender/Handler
    -> encode
    -> write to sink
    -> return to application
~~~

Ưu điểm: dễ lý luận hơn về thời điểm hàm logging hoàn tất. Nhược điểm: độ trễ caller có thể bị ảnh hưởng bởi lock, disk I/O, network hoặc encoder tốn CPU. **Ngay cả với synchronous appender, return từ log method không tự chứng minh dữ liệu đã fsync xuống ổ đĩa hay được collector index.**

### Asynchronous path

~~~text
Application thread                        Logging worker
    |                                          |
    v                                          |
 Logger enabled check                           |
    |                                          |
    v                                          |
 Capture event + context                        |
    |                                          |
    v                                          |
  bounded queue / ring buffer -----------------+
                                               |
                                               v
                                         Appender/Handler
                                               |
                                         encoder + sink
~~~

Ưu điểm: có thể giảm độ trễ lời gọi log và hấp thụ burst nếu queue đủ. Nhược điểm: queue có giới hạn, khi producer nhanh hơn sink lâu dài sẽ đầy; có thể block caller, discard theo policy hoặc chuyển xử lý khác tùy backend/config. Dữ liệu còn trong memory queue **có thể mất khi process crash**.

**Bất đồng bộ không tự tăng throughput bền vững của disk/network**. Năng lực sink thực vẫn là giới hạn cuối. Nếu đến 20.000 events/s nhưng đích chỉ xử lý 10.000 events/s lâu dài, backlog tăng cho tới khi queue đầy.

### Không nhầm hai khái niệm trong Log4j 2

- **AsyncAppender**: một appender bao ngoài các appender khác với queue.
- **AsyncLogger**: cơ chế asynchronous logging ở cấp logger, thường dùng Disruptor/ring buffer theo cấu hình Log4j 2.

Chúng có API/config, queue-full policy và chi phí khác nhau; không cho rằng bật AsyncAppender đồng nghĩa toàn bộ LoggerContext đã chuyển thành AsyncLogger. **Benchmark với payload và sink thực** trước khi khẳng định một giải pháp nhanh hơn.

## 14. Ví dụ Logback: một luồng tới AsyncAppender rồi Console

Một file **logback.xml minh họa**, chỉ tham chiếu AsyncAppender từ ROOT để tránh ghi trực tiếp CONSOLE thêm lần nữa:

~~~xml
<configuration>
  <appender name="CONSOLE"
      class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <charset>UTF-8</charset>
      <pattern>%d{ISO8601} %-5level requestId=%X{requestId:-} %logger - %msg%n%ex{full}</pattern>
    </encoder>
  </appender>

  <appender name="ASYNC"
      class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>1024</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <maxFlushTime>5000</maxFlushTime>
    <appender-ref ref="CONSOLE"/>
  </appender>

  <logger name="com.example.orders" level="DEBUG"/>

  <root level="INFO">
    <appender-ref ref="ASYNC"/>
  </root>
</configuration>
~~~

Luồng chủ yếu:

~~~text
SLF4J logger com.example.orders.OrderService
        |
   Logback level/filters + event/MDC
        |
        v
     ASYNC queue
        |
       worker
        |
        v
   CONSOLE appender
        |
        v
    Pattern encoder -> stdout/stderr theo appender -> container/collector
~~~

Các ý cần kiểm tra:

- queueSize=1024 là **số events** trong queue mẫu, không phải 1024 bytes.
- discardingThreshold=0 tắt cơ chế loại sự kiện theo threshold mặc định của AsyncAppender; nó **không bảo đảm không mất log khi crash, stop timeout hoặc lỗi backend**.
- neverBlock=false cho phép caller chờ khi queue đầy theo cơ chế backend, tác động latency.
- maxFlushTime là giới hạn chờ drain khi shutdown; nếu chưa drain hết theo timeout, có nguy cơ mất events.
- AsyncAppender thường cho phép chỉ một appender downstream trong cấu hình thông dụng; nếu cần nhiều sink, thiết kế fan-out theo khả năng backend.
- Khai báo CONSOLE nhưng **không** gắn trực tiếp vào ROOT bên cạnh ASYNC, vì như vậy một event có thể được in hai lần.
- Không áp dụng cấu hình này nguyên xi cho audit bắt buộc không được phép mất; phải đánh giá durability/failure semantics riêng.

Không có một cấu hình async phù hợp mọi workload. Với sink rất nhanh hoặc ứng dụng ít log, synchronous có thể đơn giản và đủ tốt.

## 15. Ví dụ Log4j 2: LoggerConfig, AppenderRef, Layout, sink

Log4j 2 tổ chức qua **LoggerContext**, **Configuration**, **Logger/LoggerConfig**, Filters, AppenderRef/AppenderControl, Appender và Layout/Manager. Một cấu hình **log4j2.xml** tối giản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
  <Appenders>
    <Console name="CONSOLE" target="SYSTEM_OUT">
      <PatternLayout
          pattern="%d{ISO8601} %-5p [%t] %c - %m%n%throwable"/>
    </Console>
  </Appenders>

  <Loggers>
    <Logger name="com.example.orders" level="debug"/>
    <Root level="info">
      <AppenderRef ref="CONSOLE"/>
    </Root>
  </Loggers>
</Configuration>
~~~

Đường đi minh họa:

~~~text
Log4j API logger
  -> enabled/filter
  -> LoggerConfig (com.example.orders)
  -> AppenderRef từ Root theo additivity
  -> CONSOLE appender
  -> PatternLayout
  -> SYSTEM_OUT
~~~

Mọi logger khác có thể kế thừa ROOT theo configuration. Nếu gắn CONSOLE ở logger con *và* ROOT, cần xem additivity để tránh sự kiện được đưa tới cùng appender hai lần.

Nếu muốn đặt filter chỉ cho một appender ref, Log4j 2 hỗ trợ cấu hình level/filter ở **AppenderRef**; một event có thể qua logger-level nhưng bị từ chối tại appender stage. **Không suy đoán chỉ cần root level=INFO là mọi appender đều bỏ DEBUG từ logger con**; cần hiểu hierarchy và từng filter gate.

Nếu thay bằng AsyncAppender trong Log4j 2, ví dụ fragment minh họa:

~~~xml
<Async name="ASYNC">
  <AppenderRef ref="CONSOLE"/>
</Async>
~~~

Cần thêm cấu hình Root tham chiếu ASYNC, không tham chiếu CONSOLE trực tiếp trừ khi cố tình fan-out. Fragment không phải file hoàn chỉnh và behavior queue phụ thuộc phiên bản/policy.

**Bật AsyncLogger toàn cục là một cấu hình khác**. Không trộn các cách async chỉ để thấy nhiều thread; nhiều tầng queue có thể gây tăng độ trễ, khó flush và khó giải thích log loss.

## 16. Java 17+ chạy độc lập: kiểm chứng từng chặng bằng JUL

Để hiểu sâu luồng **Logger → level → Filter → LogRecord → Handler → Formatter → sink**, ví dụ dùng **java.util.logging** có sẵn trong JDK. Không cần thư viện bên ngoài hay quyền truy cập filesystem.

Một Handler tùy chỉnh:

- Kiểm tra level/filter bằng isLoggable(record).
- Dùng Formatter chuyển LogRecord thành chuỗi xác định.
- Chuyển sang UTF-8 bytes và ghi vào ByteArrayOutputStream như **sink giả trong bộ nhớ**.
- Đếm số events đến Handler để không nhầm với số dòng.
- Disable parent handlers để output không bị thêm từ cấu hình JUL toàn cục.

Tạo file **LoggerToSinkDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggerToSinkDemo {
    static class MemoryHandler extends Handler {
        final ByteArrayOutputStream sink = new ByteArrayOutputStream();
        int accepted;

        MemoryHandler() {
            setLevel(Level.ALL);
            setFormatter(new Formatter() {
                @Override public String format(LogRecord r) {
                    String cause = r.getThrown() == null
                        ? "none"
                        : r.getThrown().getClass().getSimpleName();

                    return r.getLevel() + "|" + r.getMessage()
                        + "|cause=" + cause + "\n";
                }
            });
        }

        @Override
        public void publish(LogRecord record) {
            if (!isLoggable(record)) return;

            sink.writeBytes(getFormatter().format(record)
                    .getBytes(StandardCharsets.UTF_8));
            accepted++;
        }

        @Override public void flush() {}
        @Override public void close() {}

        String contents() {
            return sink.toString(StandardCharsets.UTF_8);
        }
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.pipeline");

        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        AtomicInteger filterSeen = new AtomicInteger();
        logger.setFilter(record -> {
            filterSeen.incrementAndGet();
            return !record.getMessage().startsWith("DROP ");
        });

        MemoryHandler handler = new MemoryHandler();
        logger.addHandler(handler);

        try {
            logger.fine("requestId=req-42 stage=TRACE");

            logger.info("requestId=req-42 stage=START");

            logger.warning(
                    "DROP requestId=req-42 stage=NOISE");

            logger.log(Level.SEVERE,
                    "requestId=req-42 stage=FAILED",
                    new IllegalStateException(
                            "downstream unavailable"));

            System.out.print("sink:\n" + handler.contents());
            System.out.println(
                    "loggerFilterSeen=" + filterSeen.get());
            System.out.println("sinkEvents=" + handler.accepted);
        } finally {
            logger.removeHandler(handler);
            logger.setFilter(null);
            handler.close();
        }
    }
}
~~~

Chạy bằng Java 17 trở lên:

~~~bash
javac LoggerToSinkDemo.java
java LoggerToSinkDemo
~~~

**Stdout chính xác đã được kiểm chứng:**

~~~text
sink:
INFO|requestId=req-42 stage=START|cause=none
SEVERE|requestId=req-42 stage=FAILED|cause=IllegalStateException
loggerFilterSeen=3
sinkEvents=2
~~~

### Diễn giải từng bước

1. Logger có Level.INFO. Lời gọi logger.fine(...) ở mức FINE thấp hơn INFO nên bị loại **trước khi Logger Filter xử lý**; không có LogRecord đến handler cho dòng này.
2. INFO vượt qua level và Filter, tạo LogRecord; MemoryHandler chấp nhận và Formatter tạo một dòng text với cause=none.
3. WARNING vượt qua level, Filter nhìn thấy text bắt đầu bằng DROP và từ chối; sự kiện này không đến Handler.
4. SEVERE vượt qua level và Filter, LogRecord giữ Throwable; Formatter viết cause=IllegalStateException.
5. **loggerFilterSeen=3** vì Logger Filter kiểm tra INFO, WARNING và SEVERE, không kiểm tra FINE đã bị level chặn.
6. **sinkEvents=2** vì chỉ INFO và SEVERE qua mọi gate đến Handler; dữ liệu sink gồm hai dòng.
7. Handler chuyển formatted string thành UTF-8 bytes bằng getBytes(StandardCharsets.UTF_8) rồi ghi vào ByteArrayOutputStream.

**Giới hạn:** sink là RAM, không phải file/network/durable store. Ví dụ không mô phỏng async queue, concurrency, retry, checksum, fsync hoặc collector indexing. Handler.accepted chỉ là counter đơn luồng, không thread-safe khi dùng trong production. Filter dựa trên message prefix chỉ dùng để minh họa **một gate**; không dùng kiểu lọc này làm biện pháp bảo vệ PII trong hệ thống thật.

### Vì sao ví dụ dùng JUL?

JUL có sẵn trong Java 17, nên bài chạy được chỉ với javac/java. Nó minh họa cùng tư duy **enabled check → event → output component → formatting → sink**, nhưng **Logback và Log4j 2 có pipeline/filters/API khác**. Không copy JUL Handler sang Logback Appender như thể là cùng interface.

## 17. Một sự kiện lỗi đi qua các tầng như thế nào?

Xét use case người dùng tạo đơn hàng, repository gặp timeout:

~~~text
HTTP POST /orders
    |
    v
Request filter gắn requestId=req-42
    |
    v
OrderController -> OrderService -> Repository
                                     |
                                     X timeout
                                     |
                          throw (giữ root cause)
                                     |
                            boundary handler
                                     |
                    logger.error("Order failed", ex)
                                     |
                                     v
                          Logger + backend/provider
                                     |
                         enabled by ERROR level?
                                     |
                                 Filter policy
                                     |
                           event + requestId + cause
                                     |
                           Appender / Async queue
                                     |
                             encoder JSON/text
                                     |
                         stdout/container or file
                                     |
                                 collector
                                     |
                                  log index
                                     |
                        support query requestId
~~~

**Không nên bắt/log/rethrow ở mọi tầng.** Một lỗi logic có thể xuất ba stack traces giống nhau nếu repository, service và controller đều log ERROR. Thay vào đó, giữ Throwable cause và ghi **một terminal event** ở boundary đã được chọn; metrics/tracing có thể bổ sung attempt/fallback context.

Log trong response và log ở server cần **cùng requestId**, nhưng không trả stack trace hoặc thông tin nội bộ cho client. Với lỗi validation 400 dự kiến, có thể dùng INFO/metric/access log theo chính sách thay vì ERROR full stack trace.

**Một exception stack trace nhiều dòng thường là một logging event.** Nếu shipper đọc từng dòng không multiline, dashboard có thể hiểu thành nhiều records. Sửa framing/JSON encoding chứ không tìm mọi dòng "at ..." trong code.

## 18. Đích ghi local: console, file, rotation

### Console

Trong container, console thường thuận tiện vì runtime có thể thu stdout/stderr. Tuy nhiên:

- ConsoleAppender ghi vào stream được cấu hình, ví dụ SYSTEM_OUT.
- JUL ConsoleHandler mặc định ghi vào System.err.
- Container runtime có thể áp dụng log rotation riêng.
- Khi container/pod bị xóa, bản local không tự được giữ vô hạn; cần shipper/kho tập trung nếu muốn truy vấn sau đó.
- Ghi console không mặc nhiên là collector đã ACK.

**Đừng tuyên bố "log ra console là durable"**. Có thể có buffering, process crash, pod restart, disk evictions hoặc collector outage.

### File

FileAppender/RollingFileAppender ghi vào filesystem theo đường dẫn, quyền, charset và policy. Một pipeline file:

~~~text
LoggingEvent
   -> RollingFileAppender
   -> Encoder
   -> app.log (active)
   -> app.YYYY-MM-DD.log.gz (archive khi rollover)
   -> Filebeat/collector tail
   -> index/archive
~~~

Rotation và retention khác nhau: rollover chia file; cleanup archive cần maxHistory/totalSizeCap hoặc lifecycle riêng. Thời gian lưu trên file không quyết định retention của index/backup. Cần kiểm tra file đang ghi, quyền thư mục, disk full, rotation khi log ít và việc collector theo file identity.

**Không đọc rồi xóa file active để dọn dung lượng** khi không có kế hoạch; có thể gây mất log hoặc ảnh hưởng collector registry.

## 19. Đích ghi mạng và collector

Khi appender/handler gửi qua socket/HTTP/protocol, có thêm chặng:

~~~text
Application -> queue -> encoder -> network
                                    |
                        endpoint unavailable?
                                    |
                          retry/backoff/buffer
                                    |
                                 receiver
                                    |
                        parse/enrich/redact
                                    |
                             storage/index
~~~

Cần phân biệt:

- **Accepted:** hàm logger chấp nhận request.
- **Enqueued:** event nằm trong queue memory/disk.
- **Processed:** logging worker đã lấy và chuyển tới appender.
- **Emitted:** bytes đã được write/gửi khỏi tiến trình theo semantics của sink.
- **Received/ACKed:** bên nhận xác nhận theo protocol.
- **Indexed/archived:** dữ liệu đã lưu theo semantics của backend.
- **Queryable:** có thể truy vấn, đôi khi sau một khoảng refresh/ingest lag.

Không có **một API logging phổ thông** trả về tất cả các trạng thái này. Cần metric/trace ở collector, appender và storage nếu muốn đo end-to-end. Một SocketAppender có thể chỉ xác nhận đã gửi vào OS buffer, không đảm bảo hệ thống cuối đã lưu.

Nếu mạng down, quyết định **drop, block, retry, buffer và failover** là một phần của chính sách quan sát và độ bền. Với audit/security events không được phép mất, có thể cần kiến trúc bền vững khác application debug logging.

## 20. Sau đích ghi còn những gì?

Khi dữ liệu rời JVM, luồng thường gồm:

1. **Container/file shipper** như Filebeat, Fluent Bit hoặc agent có khả năng đọc từ file/stdout.
2. **Framing/multiline:** xác định ranh giới của một event; Java Throwable thường nhiều dòng nếu dùng text.
3. **Decoding/parsing:** từ text/JSON sang timestamp, severity, logger, MDC và exception fields.
4. **Enrichment:** service.name, environment, host, metadata đã được xác thực.
5. **Redaction:** giảm PII/secret và enforce policy; tốt nhất tránh ghi từ nguồn ngay từ đầu.
6. **Buffer/retry/backpressure:** xử lý collector hoặc storage tạm thời quá tải.
7. **Indexing/archive:** lưu theo schema/retention với khả năng truy vấn hoặc phục hồi.
8. **Dashboards/alerts:** query theo requestId/traceId, eventCode, mức lỗi, route hoặc service.

**Một lỗi parsing ở collector không nhất thiết là lỗi Logger.info trong Java.** Có thể encoder thay pattern, JSON pretty-print nhiều dòng, timestamp không có offset hoặc field type thay đổi.

**Một event query được trên dashboard không chứng minh không có duplicates hoặc missing gaps.** Cần đối chiếu eventId/requestId và đếm theo các ranh giới đã định.

## 21. Luồng quan sát bằng metric: nơi nào có thể mất?

Một bảng kiểm tra theo chặng:

| Chặng | Metric hoặc bằng chứng nên có | Dấu hiệu bất thường |
| --- | --- | --- |
| Lời gọi ứng dụng | operation count, eventCode theo policy | Nhiều callsites log một failure |
| Logger/level | effective configuration, enabled test | DEBUG bị chặn không đúng mong đợi |
| Filter | rejected events theo rule nếu backend hỗ trợ | Drop nhầm audit |
| Async queue | depth, capacity, enqueue/drop/block | Queue đầy, latency tăng |
| Appender/Handler | append successes/failures, flush errors | File permission, socket broken |
| Encoder | serialization errors, malformed output | JSON sai escaping/schema |
| File/stdout | bytes produced, rotation, disk free | Không tăng file, disk full |
| Shipper | read offsets, received/retried/drop | Registry sai hoặc backlog |
| Collector | parsed/rejected, queue utilization | Multiline lỗi, parser drift |
| Backend | accepted/indexed, storage, mapping rejects | Ingest ok nhưng index reject |
| Query/alert | sample event readback, ingest lag | Dữ liệu chưa thấy hoặc alert sai |

Các tên metric phụ thuộc implementation; không mặc định Logback/Log4j 2 tự xuất mọi số. Có thể dùng application instrumentation, agent, JMX, exporter và backend APIs theo phiên bản.

**Công thức backlog gần đúng** cho một queue:

~~~text
backlog_growth_events_per_second
  ≈ ingress_events_per_second - sustainable_output_events_per_second
~~~

Khi output chậm hơn ingress lâu dài, queue cuối cùng đầy dù ban đầu có vẻ mọi log được ghi nhanh. Đo cả **events/s** và **bytes/s**, vì cùng số events nhưng stack trace lớn sẽ tiêu thụ I/O nhiều hơn.

## 22. Hiệu năng của từng chặng

Chi phí của một lời gọi log không chỉ là disk I/O:

- **Argument computation:** hàm tạo chuỗi/DTO chạy trước khi logger nhận.
- **Enabled check/filter:** thường rẻ nhưng vẫn có chi phí khi gọi lặp rất nhiều.
- **Event allocation:** metadata, message, Throwable và MDC snapshot.
- **Caller data:** stack walking đắt khi cần file/line chính xác.
- **Formatting:** regex/pattern/JSON serialization, timestamp, escaping, stack trace.
- **Contention:** lock trong appenders hoặc shared output.
- **Queue:** enqueue, context switching, producer blocking khi đầy.
- **Disk:** buffer, fsync policy, rotation/compression.
- **Network:** bandwidth, retries, TLS, backpressure.
- **Collector:** multiline, parser, enrichment, redaction, index mapping.

Một benchmark chỉ gọi log.debug với level tắt không đo năng lực appender. Một benchmark viết vào ByteArrayOutputStream không đại diện file/network. Một benchmark đo caller-side latency async không chứng minh event đã đến sink.

Thiết kế benchmark công bằng:

1. Giữ message/event sizes và tỉ lệ exceptions/MDC tương đương production.
2. So với cùng effective levels và routing.
3. Tách caller latency, append throughput và sink-confirmed throughput.
4. Quan sát CPU, allocation, GC, queue depth và disk/network saturation.
5. Đo sau warmup phù hợp; test cả burst và sustained rate.
6. Kiểm tra số events đến đích có bằng số events được mong đợi khi policy không cho drop.
7. Với async, đợi drain/flush và ghi nhận những events bị discard.
8. Test shutdown/crash/sink outage, không chỉ steady state.

Đừng lấy kết quả microbenchmark một máy để tuyên bố log file hay remote collector production sẽ đạt cùng tốc độ.

## 23. Bảo mật của toàn bộ luồng

Mỗi chặng có rủi ro về dữ liệu:

| Chặng | Rủi ro | Bảo vệ |
| --- | --- | --- |
| Application | Log raw password, Cookie, Authorization header | Không ghi dữ liệu nhạy cảm từ nguồn |
| MDC | Gắn user token vào mọi event | Chỉ dùng IDs có mục đích và được validate |
| Encoder | Message có newline tạo log injection | Escape/structured serialization |
| File/console | Quyền OS/container rộng | Least privilege, permissions, rotation |
| Network | Plaintext hoặc endpoint sai | TLS/auth và allowlist theo hệ thống |
| Collector | Raw log được in lại khi parse fail | Redaction/quarantine bảo vệ |
| Storage | Index truy vấn rộng quyền | RBAC, retention, audit access |
| Archive/backup | Dữ liệu còn sau khi xóa index | Lifecycle, legal hold, deletion ledger |

Một exception message từ thư viện có thể chứa URL/query/path nhạy cảm; không truyền nguyên Throwable cho mọi audience. **Client response** thường chỉ cần errorCode/requestId và thông điệp an toàn, không có stack trace.

Nếu muốn loại bỏ PII, chỉ redaction ở collector chưa đủ vì bản raw có thể đã nằm trong stdout, file, agent buffer hoặc archive. **Data minimization ngay tại logger call** là biện pháp đầu tiên.

Khi log security/audit có yêu cầu tính toàn vẹn và lưu giữ, phải thiết kế kênh riêng với quyền, durability/retention phù hợp. Không áp sampling hoặc discard policy cho loại dữ liệu đó khi chưa được đánh giá và chấp thuận.

## 24. Các lỗi thường gặp và cách khoanh vùng

### 24.1. Gọi logger nhưng không có output

Kiểm tra theo thứ tự:

1. Có provider/backend tương thích hay SLF4J rơi vào NOP?
2. Logger name và effective level có cho phép sự kiện?
3. Có TurboFilter/Logger Filter/Appender Filter/ThresholdFilter từ chối?
4. Appender/Handler có được gắn, start và đúng route không?
5. additivity=false có làm logger không còn appender?
6. Output vào stdout hay stderr, file nào, container nào?
7. File/dir permissions, queue full, socket/collector errors?
8. Encoder đang tạo dữ liệu không hợp lệ hay collector reject/index lỗi?
9. Nếu đọc dashboard: ingestion lag, filter query, timezone và retention?

Không sửa root level thành DEBUG toàn production ngay để “thử cho dễ” vì có thể làm tăng volume và lộ data. Dùng namespace cần chẩn đoán với thời hạn bật phù hợp.

### 24.2. Log xuất hai lần

Phân biệt:

- Code log ở nhiều tầng: catch–log–throw rồi handler log lại.
- Logback/Log4j 2 additivity: cùng appender ở logger con và ROOT.
- Một event fan-out tới console và file có chủ đích.
- Shipper/collector đọc cùng dữ liệu qua hai đường hoặc retry at-least-once.
- Stack trace nhiều dòng **không phải** nhiều events.

So eventId/requestId, logger name, timestamp, destination và số callsites để xác định lỗi trùng bắt đầu ở đâu. Không suppress chỉ bằng exception message vì các request độc lập có thể giống nhau.

### 24.3. Có text nhưng thiếu requestId

- Middleware có tạo và validate requestId chưa?
- MDC được đặt và clear đúng vòng đời không?
- Task chuyển thread có propagation đúng không?
- Appender/encoder có %X{requestId} hoặc JSON field phù hợp không?
- Collector parser có drop field hoặc map sai không?
- Response trả ID có trùng field log không?

Không bịa requestId ở collector từ "event gần nhất"; nhiều request đồng thời có thể bị gán sai.

### 24.4. Log bị cắt hoặc mất khi tải tăng

- Async queue đầy/drop hay caller bị block?
- maxFlushTime/shutdown có đủ drain?
- Output sink chậm, disk đầy hoặc network lỗi?
- Collector/shipper retry và backpressure thế nào?
- Rotated file bị xóa trước khi shipper đọc xong?
- Index quota/mapping conflict/retention khiến log không query được?

Cần đối chiếu count theo chặng. Nếu sản phẩm không đảm bảo at-least-once end-to-end, không tuyên bố 100% delivery chỉ bằng việc không thấy error của logger.

## 25. Ma trận kiểm thử end-to-end

| Tình huống | Kỳ vọng |
| --- | --- |
| Level INFO, gọi FINE/DEBUG | Event bị chặn theo effective level thích hợp |
| Level cho qua nhưng filter DENY | Không tới appender, có quan sát filter khi cần |
| Throwable log | Một event có exception/cause chain |
| MDC requestId | Field có ở output và khớp response |
| Async task | Context không bị mất hoặc lẫn giữa requests |
| Appender filter | Chỉ những events hợp lệ tới sink |
| Logger con và ROOT | Không duplicate ngoài thiết kế fan-out |
| File/console | Charset, newline, rolling và quyền đúng |
| JSON encoder | Parser nhận field/escape/schema đúng |
| Java stack trace | Text multiline được gom thành một event |
| Async queue đầy | Drop/block/fallback theo policy và đo được |
| Shutdown | Drain/flush theo giới hạn đã thiết kế |
| Collector down | Retry/backpressure/retention đúng yêu cầu |
| Security audit | Không bị sampling/drop hoặc leak dữ liệu không phép |
| Disk full | Lỗi được báo, không làm chết cả app ngoài failure policy |
| Collector parse error | Có metric/quarantine, không tự log vòng lặp |
| Sink retry | Phân biệt duplicate thực tế và intentional fan-out |
| Indexing | Đối chiếu eventId/query/ingest timestamp |
| Retention | Log được giữ và xóa đúng theo policy ở mọi nơi |
| Multiple independent requests | Không suppress lỗi thật vì cùng message |

Một chương trình JUL trong ví dụ kiểm tra **một đoạn** của pipeline. Kiểm thử production cần thêm Logback/Log4j 2 integration test với dependencies thật, collector và index theo môi trường giả lập/được cô lập.

## 26. Thực hành: cách tự vẽ luồng log của dự án

Chọn một logging statement cụ thể, ví dụ:

~~~java
log.error("Order creation failed", exception);
~~~

Điền vào bảng:

| Câu hỏi | Cần ghi lại câu trả lời thực tế |
| --- | --- |
| API | SLF4J 2.x, Log4j API hay JUL? |
| Provider/backend | Phiên bản Logback/Log4j2/JUL nào đang chạy? |
| Logger name | Class nào, namespace nào, effective level bao nhiêu? |
| Filters | Có TurboFilter/ThresholdFilter/marker/level rule nào? |
| Event | Throwable, MDC, eventCode, timestamp, thread captured ra sao? |
| Routing | Appender nào trực tiếp/qua hierarchy, additivity thế nào? |
| Async | Queue/ring buffer nào, full/flush/shutdown policy ra sao? |
| Encoding | PatternLayout/JSON encoder nào, charset và newline ra sao? |
| Local sink | Stdout/stderr, active file, rolling file hay socket? |
| Shipping | Agent nào đọc, file identity và multiline rules? |
| Collector | Parser/schema/redaction/enrichment nào? |
| Storage | Index/archive nào, retention, ACL và query? |
| Evidence | EventId/requestId đọc lại từ đích, metrics ở mỗi chặng? |

Hãy dùng **một synthetic requestId** và một eventCode cố định, sau đó quan sát từng chặng đã được phân quyền truy cập. Nếu không thấy sự kiện ở index nhưng file local có, vấn đề không còn ở logger enabled check; chuyển điều tra sang shipper/collector/index.

Sơ đồ hóa bằng đường đi thực tế:

~~~text
OrderService.info
  -> SLF4J
  -> Logback
  -> com.example.orders effectiveLevel=INFO
  -> AsyncAppender
  -> RollingFileAppender
  -> app.log JSON Lines
  -> Filebeat
  -> Collector
  -> log index
  -> query requestId=req-demo
~~~

Đây là ví dụ tham khảo, không phải cấu hình được xác nhận của một hệ thống cụ thể.

## 27. Checklist trước khi triển khai

- [ ] Logging API/backend/provider tương thích, không có NOP hoặc bridge loop.
- [ ] Biết effective level và đường filter của namespace quan trọng.
- [ ] Logger name, eventCode, requestId và traceId có contract.
- [ ] Throwable/cause chain được truyền đúng, không printStackTrace() lặp.
- [ ] Có chiến lược MDC setup, cleanup và async propagation.
- [ ] Appenders/Handlers đã start, cấu hình đúng sink và quyền.
- [ ] Additivity không tạo duplicate hay làm mất log ngoài ý muốn.
- [ ] Encoder/formatter được kiểm tra bằng output thực tế, đúng charset.
- [ ] JSON Lines/multiline handling phù hợp với log được tạo.
- [ ] Async queue/full/shutdown/drop policy được ghi rõ và đo bằng metric.
- [ ] Có quan sát riêng cho application, shipper, collector và index.
- [ ] Không coi logger return là bằng chứng đã fsync/index/ACK.
- [ ] Có kiểm soát PII/secret tại nguồn, redaction, ACL và retention tại các sinks.
- [ ] Đã test normal, error, burst, shutdown, collector outage và retry.
- [ ] Đã dùng một requestId/eventId mẫu để đối chiếu end-to-end.
- [ ] Đã có runbook khoanh vùng mất/trùng log mà không bật DEBUG bừa bãi.

**Kết luận:** Luồng Java Logging bắt đầu từ **lời gọi Logger**, được **API/provider/backend** quyết định và kiểm soát qua **level/filters**, hình thành **logging event chứa message/Throwable/context**, đi tới **Appender hoặc JUL Handler**, được **Layout/Formatter/Encoder** chuyển thành output rồi tới **console, file hoặc network**. Nếu có hệ thống tập trung, log tiếp tục qua **shipper, collector, parser, index và dashboard**. Hiểu rõ những ranh giới này giúp biết **log bị chặn/mất/trùng ở đâu**, phân biệt **sự kiện được chấp nhận với dữ liệu đã lưu**, và đưa ra quyết định performance, security, reliability có thể kiểm chứng.

## 28. Tài liệu tham khảo

- [Oracle Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): enabled check, Filter, LogRecord, Handler và parent handler propagation.
- [Oracle Java SE 17 — java.util.logging.Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html): publish, isLoggable, Formatter, flush, close.
- [Oracle Java SE 17 — java.util.logging.LogRecord](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogRecord.html): event metadata và caller information khi async handoff.
- [SLF4J Manual](https://www.slf4j.org/manual.html): facade, parameterized logging, provider và fluent API.
- [SLF4J FAQ](https://www.slf4j.org/faq.html): SLF4J 2.x ServiceLoader/provider và tương thích phiên bản.
- [SLF4J Error Codes](https://www.slf4j.org/codes.html): missing/multiple providers, NOP behavior.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html): effective level, hierarchy, additivity và request processing.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): appender, layouts/encoders, AsyncAppender và rolling.
- [Logback Manual — MDC](https://logback.qos.ch/manual/mdc.html): context theo thread, propagation và cleanup.
- [Apache Log4j 2 — Architecture](https://logging.apache.org/log4j/2.x/manual/architecture.html): LoggerContext, LoggerConfig, AppenderRef, Appender, Layout/Manager.
- [Apache Log4j 2 — Filters](https://logging.apache.org/log4j/2.x/manual/filters.html): nhiều giai đoạn lọc trong pipeline.
- [Apache Log4j 2 — Async logging](https://logging.apache.org/log4j/2.x/manual/async.html): asynchronous logger/appender, queue-full policy và trade-offs.
- [Apache Log4j 2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html): cấu hình Loggers, Appenders, filters và AppenderRefs.
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): timestamp, severity, body, resource, attributes và tracing context.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): phạm vi sự kiện, dữ liệu nhạy cảm, an toàn log và quản lý logging.
