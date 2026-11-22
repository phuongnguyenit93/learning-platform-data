# Logger của Logback — Cách hoạt động và sử dụng trong Java

## 1. Khái niệm

**Logger của Logback** là đối tượng đại diện cho một nguồn phát bản ghi log trong hệ thống **Logback Classic**. Mã ứng dụng thường gọi các phương thức như trace, debug, info, warn hoặc error để mô tả sự kiện; Logback xét mức ghi, tạo sự kiện log và chuyển đến các đích xuất đã cấu hình.

Cần phân biệt hai kiểu Logger có tên gần giống nhưng khác vai trò:

- **org.slf4j.Logger**: giao diện thuộc SLF4J API. Mã nghiệp vụ nên dùng kiểu này để không gắn chặt với một backend.
- **ch.qos.logback.classic.Logger**: lớp triển khai cụ thể của Logback Classic. Ngoài các phương thức thuộc SLF4J, nó có các API phục vụ cấu hình và chẩn đoán như getLevel, getEffectiveLevel, setLevel, setAdditive và addAppender.

Ví dụ thông dụng trong một lớp dịch vụ:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    public void finishOrder(String orderId) {
        LOG.info("event=order.completed orderId={}", orderId);
    }
}
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập có main. Để sử dụng, dự án cần SLF4J API và provider/backend tương ứng, ví dụ Logback Classic. Khi chạy với Logback, đối tượng phía sau giao diện SLF4J thực hiện hoạt động ghi log.

**Mục tiêu của bài:** hiểu logger được quản lý ở đâu, level hiệu lực được suy ra thế nào, additivity và appender tác động tới đầu ra ra sao, và cách dùng chúng trong một ứng dụng Java 17 có cấu hình rõ ràng.

## 2. Sơ đồ tổng thể

~~~text
Mã Java gọi org.slf4j.Logger
                 |
                 v
      SLF4J LoggerFactory
                 |
            Provider
           (Logback)
                 |
                 v
 ch.qos.logback.classic.Logger
                 |
      Level / TurboFilter
                 |
          ILoggingEvent
                 |
     Logger và ancestor
        (additivity)
                 |
                 v
        Appender / Filter
                 |
                 v
       Encoder hoặc Layout
                 |
                 v
   Console / File / Collector
~~~

| Thành phần | Vai trò |
| --- | --- |
| LoggerFactory | Trả logger theo tên hoặc lớp, đi qua cơ chế provider của SLF4J |
| LoggerContext | Bối cảnh quản lý cây logger và cấu hình Logback Classic |
| Logger | Nơi phát sự kiện, có tên, level được gán và effective level |
| Root logger | Logger gốc của phân cấp tên; thường giữ appender và level chung |
| ILoggingEvent | Đối tượng sự kiện bao gồm level, message, arguments và thông tin ngữ cảnh |
| Appender | Nhận sự kiện và ghi tới một đích như console/file |
| Filter và TurboFilter | Cho phép hoặc từ chối sự kiện theo điều kiện bổ sung |
| Encoder / Layout | Chuyển sự kiện thành văn bản/byte theo định dạng |
| MDC | Ngữ cảnh dạng key-value, thường chứa requestId/traceId nếu được truyền đúng |

**Logger không phải file log.** Việc gọi LOG.info chỉ có nghĩa ứng dụng gửi một sự kiện tới API logging. Bản ghi có được xuất hay không còn phụ thuộc level, filter, appender, encoder và trạng thái nơi nhận. Logback không được tích hợp sẵn trong JDK; cần dependency thích hợp.

## 3. Cách lấy Logger

Quy ước phổ biến:

~~~java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(MyService.class);
~~~

Đoạn trên nằm **bên trong lớp MyService**. Logger có tên trùng với tên đầy đủ của lớp, ví dụ com.example.order.MyService. Một cách khác là lấy theo tên tường minh:

~~~java
org.slf4j.Logger log =
        org.slf4j.LoggerFactory.getLogger("com.example.order");
~~~

Trong cùng LoggerContext, logger theo một tên được quản lý và tái sử dụng; không cần tự tạo LoggerContext hoặc đối tượng backend mới ở mỗi request. Quy ước **private static final** giúp tránh lấy logger theo từng instance, giữ tên ổn định và dễ cấu hình theo package.

Có thể đặt tên logger theo chức năng thay vì tên lớp, nhưng nên nhất quán trong toàn dự án. Tránh dùng tên động gồm orderId/requestId cho từng yêu cầu: logger hierarchy dùng để quản lý nguồn phát và cấu hình, còn requestId thường là **ngữ cảnh sự kiện**, không phải tên logger.

## 4. Phân cấp logger theo tên

Logback tổ chức các logger theo tên có dấu chấm:

~~~text
ROOT
  |
  +-- com
       |
       +-- com.example
            |
            +-- com.example.order
            |      |
            |      +-- com.example.order.OrderService
            |
            +-- com.example.payment
~~~

Nhờ phân cấp này, một cấu hình ở **com.example.order** có thể ảnh hưởng tới các logger con của nhóm order. **com.example.ordering** không phải con theo đúng ranh giới tên của **com.example.order**, dù chuỗi bắt đầu gần giống.

Hai cơ chế riêng biệt dùng hierarchy:

1. **Kế thừa level:** logger chưa có level riêng dùng level của ancestor gần nhất có level được cấu hình.
2. **Chuyển sự kiện đến appender:** event từ logger con có thể đi qua appender ở logger cha và root nếu additivity cho phép.

Hiểu rõ khác biệt giữa hai cơ chế là điều quan trọng nhất khi cấu hình Logger của Logback.

## 5. Level được gán và effective level

Các mức phổ biến trong Logback Classic:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

**Level được gán (assigned level)** là mức đặt trực tiếp trên logger. Nếu không đặt, giá trị này có thể là **null**. **Effective level** là mức thực sự áp dụng, suy ra từ logger hiện tại hoặc ancestor gần nhất đã có level.

Ví dụ:

~~~text
ROOT                         INFO
com.example                  (không đặt)
com.example.order            DEBUG
com.example.order.OrderService (không đặt)
com.example.payment          (không đặt)
~~~

| Logger | Level trực tiếp | Effective level |
| --- | --- | --- |
| ROOT | INFO | INFO |
| com.example | null | INFO |
| com.example.order | DEBUG | DEBUG |
| com.example.order.OrderService | null | DEBUG |
| com.example.payment | null | INFO |

Trong tình huống này:

- Lệnh **debug** ở OrderService được phép vượt qua điều kiện ngưỡng cơ bản vì effective level là DEBUG.
- Lệnh **debug** ở PaymentService thuộc com.example.payment thường bị loại vì effective level là INFO.
- Lệnh **info, warn, error** ở cả hai thành phần vẫn đủ ngưỡng.
- Logger.getLevel() trả null không có nghĩa logger bị tắt; phải xét effective level.

Thông thường level của một sự kiện phải **ít nhất nghiêm trọng bằng** effective level của logger phát. TurboFilter có thể ảnh hưởng thêm đến việc chấp nhận sự kiện, còn Filter tại appender có thể chặn sự kiện đã qua logger.

### Root INFO có chặn DEBUG của logger con không?

Theo cách xử lý mức thông thường của Logback, **không**. Nếu logger con có effective level DEBUG và đã tạo event DEBUG, sự kiện có thể đi đến appender gắn trên root nhờ additivity, ngay cả khi root đặt INFO. **Level của root không được áp lại để loại event đã được logger con chấp nhận** khi nó đi qua tuyến appender. Tuy nhiên, nếu appender có ThresholdFilter ở INFO, filter đó vẫn có thể chặn DEBUG.

## 6. Additivity là gì?

**Additivity** là quy tắc chuyển sự kiện từ logger hiện tại đến appender của các ancestor. Cấu hình mặc định thường là **true**.

Ví dụ cây:

~~~text
ROOT -> Appender CONSOLE
  com.example.order -> Appender ORDER_FILE
    com.example.order.OrderService
~~~

Nếu additivity=true, event của OrderService có thể được ghi vào **ORDER_FILE** và **CONSOLE**. Nếu cùng một appender được gắn ở nhiều cấp, nó có thể nhận cùng event nhiều lần.

Ví dụ cấu hình dễ gây log trùng:

~~~xml
<logger name="com.example.order" level="DEBUG">
    <appender-ref ref="STDOUT"/>
</logger>
<root level="INFO">
    <appender-ref ref="STDOUT"/>
</root>
~~~

Mảnh XML này giả định appender STDOUT đã được khai báo trước đó. Vì logger con có additivity mặc định, nó và root có thể cùng gọi appender STDOUT, làm event xuất hai lần. **Hai dòng giống nhau không nhất thiết là hai lần nghiệp vụ được thực thi.**

Hai cách thiết kế hợp lý:

**Cách A: appender chung ở root, logger con chỉ đặt level.**

~~~xml
<logger name="com.example.order" level="DEBUG"/>
<root level="INFO">
    <appender-ref ref="STDOUT"/>
</root>
~~~

**Cách B: logger con dùng appender riêng và dừng chuyển tiếp.**

~~~xml
<logger name="com.example.order"
        level="DEBUG"
        additivity="false">
    <appender-ref ref="ORDER_FILE"/>
</logger>
~~~

Ở cách B, ORDER_FILE phải tồn tại. Khi **additivity=false**, event không chuyển tiếp tới appender của các ancestor qua đường đó. **Nếu không gắn appender ở nhánh con, event có thể không đi đến đích mong đợi.**

Additivity **không phải ngưỡng level**. Một logger có thể kế thừa level từ cha mà vẫn tắt additivity, hoặc tự đặt level DEBUG trong khi vẫn phát log qua appender ở root.

## 7. Ví dụ đầy đủ với Java 17 và Maven

Mục tiêu: một ứng dụng có **root INFO** nhưng riêng nhóm **demo.order DEBUG**, chỉ dùng **một ConsoleAppender tại root**, để nhìn thấy chính xác cơ chế kế thừa level và additivity.

### 7.1. Cấu trúc dự án

~~~text
logback-logger-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LogbackLoggerDemo.java
        └── resources/
            └── logback.xml
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>logback-logger-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
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
                    <mainClass>demo.LogbackLoggerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các phiên bản trong ví dụ nhằm xác định dependency cho bài thực hành, **không phải khẳng định là phiên bản mới nhất**. Dependency logback-classic thường kéo logback-core và SLF4J API tương thích qua Maven; dự án thật cần quản lý phiên bản tập trung, kiểm tra xung đột dependency và cập nhật bản vá phù hợp.

### 7.3. src/main/resources/logback.xml

~~~xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %logger | %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo.order" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

Cấu hình này có những đặc điểm:

- **ConsoleAppender** của Logback mặc định ghi **stdout**, không nhầm với ConsoleHandler của JUL thường ghi **stderr**.
- **demo.order** có level DEBUG, còn root có INFO.
- Logger con **demo.order.OrderService** kế thừa DEBUG.
- Logger con không gắn appender riêng nên không bị xuất trùng với root theo mô hình cấu hình này.
- **%level**, **%logger**, **%msg** và **%n** quyết định định dạng; không có timestamp để kết quả dễ so sánh.
- Trong production, thường bổ sung timestamp, thread, tên service, request/trace ID và chiến lược xuất Throwable phù hợp.

### 7.4. src/main/java/demo/LogbackLoggerDemo.java

~~~java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class LogbackLoggerDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger("demo.order.OrderService");

    public static void main(String[] args) {
        LOG.debug(
                "event=order.pricing orderId={} base={} discount={}",
                "ORD-7", 100, 10);

        LOG.info(
                "event=order.completed orderId={} total={}",
                "ORD-7", 90);

        LOG.warn(
                "event=order.fallback reason={}",
                "cache_miss");
    }
}
~~~

Logger được đặt tên tường minh là **demo.order.OrderService**, khác tên lớp chính **demo.LogbackLoggerDemo**. Điều đó cho phép ví dụ thể hiện đúng tác động của cấu hình demo.order.

### 7.5. Chạy thử

Yêu cầu **JDK 17+** và Maven đã cài; lần đầu Maven cần tải dependency. Mở terminal ở thư mục logback-logger-demo:

~~~bash
mvn -q compile exec:java
~~~

**Stdout của chương trình Java** (không tính thông tin riêng của Maven/terminal):

~~~text
DEBUG | demo.order.OrderService | event=order.pricing orderId=ORD-7 base=100 discount=10
INFO | demo.order.OrderService | event=order.completed orderId=ORD-7 total=90
WARN | demo.order.OrderService | event=order.fallback reason=cache_miss
~~~

Vì sao có dòng DEBUG?

1. Logger được lấy theo tên **demo.order.OrderService**.
2. Logger **demo.order** đã được đặt DEBUG, nên logger con có effective level DEBUG nếu không tự đặt mức khác.
3. Lệnh debug đủ ngưỡng tại logger phát.
4. Event được chuyển đến appender STDOUT gắn tại root vì additivity vẫn bật.
5. Root INFO không lọc lại event DEBUG đã được logger con chấp nhận; cấu hình appender ở trên không có filter cản DEBUG.
6. Encoder định dạng các placeholder **{}** rồi in level, logger name và message.

Để thử ngưỡng, đổi trong logback.xml:

~~~xml
<logger name="demo.order" level="INFO"/>
~~~

Chạy lại cùng chương trình. **Stdout ứng dụng** lúc này còn hai dòng:

~~~text
INFO | demo.order.OrderService | event=order.completed orderId=ORD-7 total=90
WARN | demo.order.OrderService | event=order.fallback reason=cache_miss
~~~

Mã Java không cần sửa. Đây là giá trị của việc tách sự kiện phát ra bởi Logger khỏi cấu hình backend.

## 8. Sự khác nhau giữa Logger và Appender

Logger xác định **tên nguồn phát** và **ngưỡng phát sự kiện**, còn Appender quyết định **đích xuất**. Một logger có thể chuyển sự kiện tới nhiều appender theo cấu hình hierarchy. Ví dụ, console có thể nhận INFO trở lên trong khi file dành cho chẩn đoán có thể nhận DEBUG trở lên.

Một Appender có thể có **filter** riêng. Mảnh cấu hình sau đặt ngưỡng INFO cho ConsoleAppender:

~~~xml
<appender name="STDOUT"
          class="ch.qos.logback.core.ConsoleAppender">
    <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
        <level>INFO</level>
    </filter>
    <encoder>
        <pattern>%level | %logger | %msg%n</pattern>
    </encoder>
</appender>
~~~

Dù logger demo.order chấp nhận DEBUG, filter appender này loại DEBUG trước khi xuất. Đây chỉ là mảnh cấu hình minh họa, **không phải toàn bộ logback.xml chạy độc lập**. Muốn thấy DEBUG, phải xét cả effective level, filter và tuyến appender.

Không gắn cùng một appender vào nhiều cấp một cách ngẫu nhiên. Nếu thấy log trùng, kiểm tra appender-ref tại logger con, ancestor và root cùng với thuộc tính additivity trước khi kết luận nghiệp vụ bị gọi hai lần.

## 9. LoggerContext của Logback

**LoggerContext** là bối cảnh mà Logback Classic dùng để quản lý logger và cấu hình. Khi mã ứng dụng chỉ muốn ghi log, không cần truy cập nó; dùng SLF4J LoggerFactory là đủ.

Khi xây dựng công cụ quản trị hoặc chẩn đoán Logback, có thể truy cập implementation sau khi kiểm tra backend:

~~~java
// Mã minh họa trong method, cần dependency Logback và SLF4J.
org.slf4j.ILoggerFactory factory =
        org.slf4j.LoggerFactory.getILoggerFactory();

if (factory instanceof ch.qos.logback.classic.LoggerContext context) {
    ch.qos.logback.classic.Logger logger =
            context.getLogger("demo.order.OrderService");

    ch.qos.logback.classic.Level assigned = logger.getLevel();
    ch.qos.logback.classic.Level effective =
            logger.getEffectiveLevel();

    System.out.println("assigned=" + assigned);
    System.out.println("effective=" + effective);
}
~~~

Trong cấu hình ví dụ mục 7, logger **demo.order.OrderService** không đặt level trực tiếp: assigned có thể là **null**, effective là **DEBUG**. Hai giá trị này không phải tương đương.

**Tại sao cần instanceof?** Nếu một ứng dụng dùng backend SLF4J khác, ILoggerFactory có thể không phải LoggerContext của Logback. Ép kiểu không kiểm tra có thể gây ClassCastException. Mã thư viện dùng SLF4J nên tránh phụ thuộc trực tiếp backend khi không cần thiết.

Logback cho phép đổi level lúc chạy, ví dụ:

~~~java
// Mảnh mã minh họa trong nơi quản trị; context đã được xác nhận.
ch.qos.logback.classic.Logger target =
        context.getLogger("demo.order");
target.setLevel(ch.qos.logback.classic.Level.DEBUG);
~~~

Việc này ảnh hưởng tới logger trong context đang chạy. Nó không phải thao tác nên gọi tự do từ một request hoặc thư viện nghiệp vụ; cần có cơ chế phân quyền, giới hạn thời gian bật DEBUG và đồng bộ với cấu hình đang sử dụng. Khi reload cấu hình, mức được đổi bằng code có thể bị cấu hình mới ghi đè.

## 10. Parameterized logging và chi phí

SLF4J hỗ trợ placeholder **{}**:

~~~java
LOG.info("event=order.created orderId={} total={}", orderId, total);
~~~

Đây là đoạn minh họa trong lớp có Logger và các biến. Cách này giúp giữ message template dễ đọc và tránh một số thao tác nối chuỗi không cần thiết khi mức log bị tắt.

**Tuy nhiên, Java vẫn đánh giá đối số trước khi gọi phương thức.** Ví dụ:

~~~java
LOG.debug("orderDetail={}", serializeExpensively(order));
~~~

Hàm serializeExpensively(order) vẫn chạy trước lời gọi debug, dù DEBUG bị tắt. Với dữ liệu tạo quá tốn kém:

~~~java
if (LOG.isDebugEnabled()) {
    LOG.debug("orderDetail={}", serializeExpensively(order));
}
~~~

Các đoạn trên cần biến và phương thức trong mã thực; **không phải chương trình độc lập**. isDebugEnabled() giúp tránh chi phí tạo message khi level bị loại nhưng không cam kết appender cuối cùng sẽ ghi log (filter hoặc lỗi đích xuất có thể ngăn).

Đừng gắn hành động nghiệp vụ bắt buộc vào quá trình tạo thông điệp DEBUG; nếu nhánh bị tắt, hành động có thể không chạy.

## 11. Ghi exception với Logger

SLF4J Logger cho phép truyền Throwable cùng thông điệp:

~~~java
try {
    performPayment();
} catch (java.io.IOException ex) {
    LOG.error("event=payment.failed requestId={}", requestId, ex);
}
~~~

Đây là **mã minh họa**, cần LOG, requestId và performPayment() ở chương trình thật. Khi sử dụng overload phù hợp, Logback có thể giữ Throwable trong event để encoder/layout xuất stack trace và chuỗi cause.

Chỉ ghi **LOG.error(ex.getMessage())** có thể làm mất stack trace và bỏ ngữ cảnh nghiệp vụ. Khi lỗi được ném qua nhiều tầng, nên chọn **ranh giới chịu trách nhiệm ghi log** thay vì mỗi tầng đều ghi cùng Throwable rồi ném tiếp.

Đừng cho rằng mọi pattern đều giữ đủ thông tin lỗi. Cần kiểm tra encoder, throwable converter, cách parse và retention trong môi trường thực. Với dữ liệu nội bộ nhạy cảm, exception message/stack trace cũng cần được bảo vệ.

## 12. MDC — gắn requestId với log event

**MDC** (Mapped Diagnostic Context) là ngữ cảnh key-value để hỗ trợ tìm các log liên quan cùng yêu cầu. Với SLF4J/Logback:

~~~java
// Mã minh họa đặt trong method có biến LOG.
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("requestId", "req-42")) {
    LOG.info("event=order.created outcome=success");
}
~~~

Trong logback.xml, pattern có thể lấy MDC:

~~~xml
<pattern>%level requestId=%X{requestId} %logger - %msg%n</pattern>
~~~

Đây là mảnh cấu hình bên trong encoder thích hợp. Khi MDC có requestId=req-42, Logback có thể đưa giá trị đó vào log mà không cần nối vào mọi message.

**MDC không tự tạo correlation ID và không tự truyền ngữ cảnh qua mọi asynchronous task.** Với thread pool hoặc CompletableFuture, cần truyền context theo cách phù hợp và dọn MDC sau khi xử lý để thread tái sử dụng không giữ ID của request cũ.

Không dùng MDC để chứa password, token, cookie, dữ liệu cá nhân nhạy cảm hoặc toàn bộ request body.

## 13. Logback Logger và Structured Logging

Logback có thể xuất log dạng văn bản hoặc kết hợp encoder phù hợp để tạo bản ghi có cấu trúc. Ví dụ dạng key=value:

~~~text
INFO event=order.completed orderId=ORD-7 total=90
~~~

và JSON minh họa:

~~~json
{"level":"INFO","logger":"demo.order.OrderService","event":"order.completed","orderId":"ORD-7","total":90}
~~~

Dòng JSON ở trên **không phải output của chương trình mục 7**; nó chỉ minh họa mục tiêu của structured logging. Để xuất JSON thực, dự án cần encoder tương ứng, cấu hình dependency và kiểm chứng parser/escaping. Dùng placeholder {} **không tự biến message thành các trường JSON có kiểu**.

Tên sự kiện ổn định, requestId/traceId và mã lỗi giúp tìm kiếm, nhưng đừng ghi cả đối tượng lớn hoặc raw payload. Log injection có thể xảy ra khi dữ liệu không tin cậy chứa newline/dấu nháy mà formatter không escape đúng.

## 14. Chọn mức log đúng

| Level của SLF4J/Logback | Mục đích thông thường |
| --- | --- |
| TRACE | Truy vết rất sâu khi cần chẩn đoán |
| DEBUG | Nhánh xử lý, trạng thái trung gian và quyết định quan trọng |
| INFO | Cột mốc vận hành có ý nghĩa |
| WARN | Bất thường cần chú ý nhưng vẫn có thể tiếp tục |
| ERROR | Thất bại quan trọng cần xử lý và điều tra |

Logger.error(...) không tự ném exception, rollback hay dừng ứng dụng. Chính logic của ứng dụng chịu trách nhiệm xử lý lỗi. Không mặc định mọi validation error phải được ghi ERROR; mức log cần phản ánh tác động đối với dịch vụ và mục đích vận hành.

Không bật TRACE/DEBUG cho toàn bộ production vô thời hạn. Nên bật theo package/logger cần điều tra, quan sát chi phí và có kế hoạch đưa về mức vận hành.

## 15. Logback khác JUL và Log4j 2 ra sao?

| Hệ thống | Logger API và cấu hình |
| --- | --- |
| JUL (java.util.logging) | Logger và Level nằm trong JDK; cấu hình thường qua logging.properties; Handler/Formatter |
| SLF4J | Facade API org.slf4j.Logger; cần provider phù hợp để ghi |
| Logback Classic | Triển khai SLF4J; ch.qos.logback.classic.Logger, LoggerContext, logback.xml, Appender |
| Log4j 2 | Có API và implementation riêng; sử dụng Appender, cấu hình riêng |
| Spring Boot | Có hệ cơ chế cấu hình logging theo framework/backend thực tế |

Không viết **java.util.logging.Level.FINE** rồi kỳ vọng nó là **ch.qos.logback.classic.Level.DEBUG**. Đây là hai API khác nhau. Nếu có cầu nối JUL → SLF4J, hành vi phụ thuộc cấu hình bridge; tránh lắp nhiều provider/bridge xung đột hoặc vòng chuyển tiếp.

Trong thư viện dùng chung, phụ thuộc vào SLF4J API thường linh hoạt hơn so với dùng lớp Logback implementation trực tiếp.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Nhầm SLF4J Logger với Logback Logger | Không tìm thấy API getEffectiveLevel trên SLF4J | Chỉ dùng backend class trong mã quản trị Logback |
| Coi getLevel()==null là logging bị tắt | Hiểu sai hiệu lực level | Dùng getEffectiveLevel để xét kế thừa |
| Root INFO và nghĩ con DEBUG luôn bị chặn | Gỡ lỗi sai hướng | Đánh giá level của logger phát và appender filter |
| Trùng appender-ref ở con và root | Log xuất hai lần | Gắn appender ở root hoặc cấu hình additivity phù hợp |
| additivity=false nhưng không gắn appender | Không có output mong đợi | Gắn appender cho nhánh hoặc cho phép truyền lên cha |
| Đổi level của sai package/name | Không thấy khác biệt | Xác minh tên logger thực tế |
| Logger DEBUG nhưng appender filter INFO | DEBUG không xuất | Kiểm tra cả filter tại đích |
| Cast thẳng ILoggerFactory sang LoggerContext | Có thể ClassCastException | Kiểm tra backend bằng instanceof |
| Có nhiều SLF4J provider | Backend được chọn không đúng hoặc cảnh báo | Kiểm tra dependency tree, giữ kiến trúc nhất quán |
| Ghép chuỗi đắt tiền trong debug | Tốn CPU dù debug tắt | Dùng placeholder/guard cho phép tính tốn kém |
| Không dọn MDC sau request | Lẫn correlation ID giữa các công việc | Dọn theo scope và truyền context đúng |
| Ghi raw payload/secret vào log | Nguy cơ lộ dữ liệu | Chỉ ghi trường cần, che dữ liệu nhạy cảm |
| Log Throwable ở mọi tầng | Nhiều stack trace trùng | Đặt trách nhiệm log ở boundary |
| Sửa sai tệp logback.xml | Cấu hình không đổi | Kiểm tra classpath, framework, profile, reload |

## 17. Checklist khi không thấy log

1. Mã có thật sự đi qua lời gọi LOG.debug/info tương ứng không?
2. Tên logger được lấy từ tên lớp hay từ chuỗi tường minh? Có trùng với tên cấu hình không?
3. Effective level của logger là gì?
4. TurboFilter và filter của appender có loại event không?
5. Có appender nào nhận? Có additivity=false ở một cấp mà thiếu appender không?
6. Log đi tới stdout, stderr, file hay collector?
7. Logback Classic có thực sự là backend đang chạy không? Có xung đột SLF4J provider hoặc bridge không?
8. logback.xml có được đóng gói vào classpath và được nạp không?
9. Có thread context/MDC đúng để lọc log của yêu cầu tương ứng không?
10. Dữ liệu có thể bị trễ, sampling, mất do buffer hoặc hết thời gian lưu ở hệ thống tập trung không?

Nếu không thấy một dòng log, **không thể kết luận chỉ từ đó rằng nhánh code chưa thực thi**.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao mã nghiệp vụ nên khai báo org.slf4j.Logger thay vì ch.qos.logback.classic.Logger?

**Đáp án:** Vì SLF4J là API trung gian; mã có thể dùng các backend khác mà không cần gắn chặt với lớp nội bộ Logback. Backend class cần thiết chủ yếu khi quản lý/cấu hình Logback.

**Câu 2.** Root INFO, logger demo.order DEBUG, appender nằm ở root, không có filter đặc biệt: có thể thấy DEBUG của demo.order.OrderService không?

**Đáp án:** Có. Logger con có effective level DEBUG, event được chấp nhận rồi đi tới appender root qua additivity. Root INFO không tự lọc lại event đã được logger con chấp nhận.

**Câu 3.** Logger.getLevel() trả null nghĩa là gì?

**Đáp án:** Logger chưa được gán level trực tiếp và thường kế thừa effective level từ ancestor; không đồng nghĩa bị tắt.

**Câu 4.** Một dòng log xuất hai lần khi logger con và root đều gắn STDOUT. Nguyên nhân có thể là gì?

**Đáp án:** Additivity cho phép event đến appender ở cả hai cấp. Điều chỉnh appender-ref hoặc cấu hình additivity để tránh ghi trùng.

**Câu 5.** additivity=false và logger con không có appender riêng sẽ thế nào?

**Đáp án:** Event không đi tới appender root qua tuyến chuyển tiếp, có thể không xuất ra đích nào.

**Câu 6.** Vì sao LOG.debug("data={}", expensive(data)) vẫn tốn CPU khi DEBUG tắt?

**Đáp án:** Java tính expensive(data) trước lời gọi; dùng guard isDebugEnabled nếu phép tính thực sự đắt.

**Câu 7.** Có nên giả định MDC tự truyền qua CompletableFuture và thread pool không?

**Đáp án:** Không. Cần chiến lược truyền ngữ cảnh thích hợp và dọn MDC để tránh lẫn dữ liệu giữa request.

**Câu 8.** Nếu backend không phải Logback Classic mà vẫn cast ILoggerFactory thành LoggerContext, điều gì có thể xảy ra?

**Đáp án:** ClassCastException. Kiểm tra instanceof trước khi dùng API nội bộ Logback.

**Câu 9.** Log event chứa Throwable nhưng hệ thống chỉ hiển thị message. Cần kiểm tra gì?

**Đáp án:** Encoder/layout/formatter, appender filter và cách hiển thị exception; không mặc định mọi định dạng đều chứa đủ stack trace.

**Ghi nhớ:** **Logger của Logback** là triển khai phía sau **SLF4J Logger**. Muốn hiểu vì sao một log xuất hiện hoặc biến mất, hãy kiểm tra **tên logger → effective level → filter → additivity → appender → encoder/đích xuất**. Trong mã nghiệp vụ dùng SLF4J; cấu hình và quản lý Logback ở đúng tầng, giữ log hữu ích và bảo vệ dữ liệu nhạy cảm.
