# Nhận correlation ID trong Java Logging

**Nhận correlation ID** là bước đọc một mã định danh tương quan từ **ranh giới đầu vào** của ứng dụng (HTTP request, RPC metadata hoặc message headers), xác định mã đó có được chấp nhận hay không và thiết lập **correlation ID hiệu lực** cho toàn bộ quá trình xử lý. Trong hệ thống Java, mã này thường xuất hiện dưới header HTTP như `X-Correlation-ID` hoặc `X-Request-ID`.

Mục đích của correlation ID là giúp tìm các dòng log thuộc **cùng một yêu cầu hoặc cùng một luồng công việc**, kể cả khi lời gọi đi qua nhiều lớp/service. Nó là **thông tin chẩn đoán**, không phải mật khẩu, session token, user ID, chứng nhận danh tính hay mã xác thực.

Ví dụ một client gửi:

~~~http
GET /orders HTTP/1.1
Host: example.internal
X-Correlation-ID: req-20261109-01
~~~

Nếu ứng dụng chấp nhận ID đó, các log có thể mang:

~~~text
INFO correlationId=req-20261109-01 event=request_received route=/orders
INFO correlationId=req-20261109-01 event=order_loaded orderId=ord-7
INFO correlationId=req-20261109-01 event=response_sent status=200
~~~

Điểm quan trọng là **không để mỗi tầng tự tạo một ID khác**, nếu tất cả đang xử lý cùng một luồng công việc. Tuy nhiên việc tin tưởng một giá trị từ mạng bên ngoài phải có kiểm tra rõ ràng.

## 1. Correlation ID đến từ đâu?

Một correlation ID có thể được cung cấp bởi:

- **Client HTTP:** thêm `X-Correlation-ID` vào request.
- **API gateway/reverse proxy:** tạo ID ở điểm vào hoặc chuyển tiếp ID đã được chấp nhận.
- **Service phía trước:** truyền lại ID khi gọi downstream service.
- **Hệ thống message:** đặt ID trong message properties/headers của queue hoặc event.
- **RPC framework:** dùng metadata của lời gọi để mang giá trị.
- **Job scheduler:** gắn ID khi khởi tạo một batch/job độc lập, rồi truyền vào các bước xử lý.

Một hệ thống có thể có nhiều loại ID:

| ID | Ý nghĩa thường gặp | Có thể giống correlation ID không? |
| --- | --- | --- |
| `correlationId` | Nhóm log của một luồng xử lý/nghiệp vụ | Là trường cần quản lý trong bài |
| `requestId` | Nhận diện riêng một HTTP request | Có thể khác ID xuyên nhiều service |
| `traceId` | Nhận diện trace trong distributed tracing | Có thể dùng để liên kết log, nhưng ngữ nghĩa khác |
| `spanId` | Nhận diện một span trong trace | Không phải correlation ID của toàn luồng |
| `orderId`, `userId` | Định danh thực thể nghiệp vụ | Không nên thay ID chẩn đoán; có chính sách bảo mật riêng |
| `messageId` | Nhận diện message riêng lẻ | Có thể khác ID của workflow chứa nhiều message |

**Đừng mặc định `X-Request-ID`, `X-Correlation-ID` và W3C `traceparent` là cùng một giao thức.** Một hệ thống có thể chọn sử dụng trace ID làm khóa tìm log, nhưng phải giữ đúng format, ý nghĩa và chính sách tracing. Không tự viết đè `traceparent` bằng UUID tùy ý.

## 2. Luồng nhận correlation ID qua HTTP

Sơ đồ xử lý tại ingress:

~~~text
HTTP request
  |
  v
Gateway / load balancer (nếu có)
  |
  v
Java HTTP server / Servlet filter / framework middleware
  |
  v
Đọc header được quy ước
  |
  +-- Không có? --------------------------+
  |                                      |
  +-- Có một giá trị? -> Validate -------+
  |                        |             |
  |                    Không hợp lệ       |
  |                        |             |
  +-- Gửi trùng/không rõ ràng? -----------+
  |                                      |
  |                              Tạo ID mới an toàn
  |                                      |
  +-- Có một giá trị hợp lệ -------------+
  |                 |
  v                 v
Chọn ID hiệu lực (effective correlation ID)
  |
  +--> Đưa vào request context / MDC
  +--> Dùng khi gọi service phụ thuộc
  +--> Gắn lên response header theo chính sách
  |
  v
Xử lý nghiệp vụ và phát log
  |
  v
Dọn context trong finally / try-with-resources
~~~

Các bước này nên nằm ở **tầng entrypoint**, trước khi controller/service nghiệp vụ xử lý. Nếu mỗi controller nhận header theo cách riêng, dễ xảy ra log thiếu ID, cách kiểm tra khác nhau hoặc MDC không được dọn đúng.

### Phân biệt “nhận” và “truyền tiếp”

- **Nhận:** đọc ID từ bên ngoài; kiểm tra, chọn/khởi tạo ID hiệu lực.
- **Gắn context:** giữ ID trong scope xử lý để log có thể lấy.
- **Truyền tiếp:** gửi ID hiệu lực sang downstream service hoặc message.
- **Hoàn tất:** xóa context khỏi thread và (nếu phù hợp) trả ID trong response.

Bài này tập trung vào bước **nhận và kiểm soát ID ở đầu vào**, nhưng các bước sau quyết định ID có còn hữu ích hay không.

## 3. Quy ước header nhận từ HTTP

Một quy ước đơn giản:

~~~text
Tên request header:  X-Correlation-ID
Tên response header: X-Correlation-ID
Tên field trong log: correlationId
~~~

`X-Correlation-ID` và `X-Request-ID` là các tên **quy ước thực tế**, không phải sự bảo đảm rằng mọi gateway/framework đều tự hỗ trợ chúng. Tổ chức phải thống nhất **một tên chính thức** hoặc mô tả rõ thứ tự ưu tiên nếu nhiều nguồn.

HTTP header names **không phân biệt chữ hoa–chữ thường**. Vì vậy `X-Correlation-ID` và `x-correlation-id` đại diện cùng tên header theo HTTP. Đừng viết logic bảo mật dựa vào sự khác biệt chữ hoa chữ thường của tên header.

### Không nhận đồng thời nhiều tên mà thiếu quy tắc

Giả sử request có cả:

~~~http
X-Request-ID: req-a
X-Correlation-ID: req-b
~~~

Nếu service A chọn `X-Request-ID` còn service B chọn `X-Correlation-ID`, log có thể bị tách thành hai nhóm. Cần chọn rõ:

1. Một tên được chấp nhận chính thức, các tên khác chỉ phục vụ migration theo thứ tự ưu tiên đã định.
2. Nếu cả hai có mặt và xung đột, có thể từ chối hoặc chỉ dùng ID do gateway đáng tin tạo.
3. Không ghép hai ID thành một chuỗi không có schema.
4. Không âm thầm đổi tên field trong mỗi service.

Với các hệ đã tích hợp distributed tracing, hãy dùng thư viện tracing phù hợp để nhận/lan truyền `traceparent` theo W3C Trace Context, thay vì dùng cùng trình kiểm tra của `X-Correlation-ID` cho mọi header.

## 4. Ranh giới tin cậy: header do client gửi là dữ liệu không tin cậy

Một bên ngoài có thể tự đặt:

~~~http
X-Correlation-ID: admin
~~~

Giá trị đó không chứng minh request được tạo bởi admin. Nếu log có `correlationId=admin`, người điều tra chỉ biết **client đã gửi một chuỗi được chấp nhận**, không biết danh tính của client.

Một số rủi ro:

- **Log forging/spoofing:** attacker chọn ID giống ID của một luồng khác để làm khó điều tra.
- **Log injection:** chuỗi chứa newline hoặc ký tự điều khiển tạo nội dung log giả nếu không escape.
- **Dữ liệu quá dài:** header hàng megabyte làm tốn bộ nhớ hoặc gây quá tải khi serialize/index.
- **Cardinality cao:** mỗi request dùng giá trị khác nhau; hữu ích để truy vết nhưng không phù hợp làm metric label.
- **Rò rỉ dữ liệu:** client nhét email, token, địa chỉ hoặc payload nhạy cảm vào header rồi hệ thống ghi lại.
- **Nhầm ranh giới gateway:** service backend tin header do client trực tiếp gửi, dù chính sách chỉ muốn chấp nhận ID từ gateway.

**Kiểm tra format giúp ID an toàn hơn để ghi và truyền tiếp, nhưng không tự biến nó thành dữ liệu đáng tin về danh tính.**

### Hai chính sách tin cậy thường gặp

**Chính sách A — Cho phép client đề xuất ID:** chấp nhận một ID có cú pháp/độ dài đúng, nếu không thì tạo mới. Phù hợp với API cho phép client tự tương quan request, nhưng cần hiểu rằng client có thể cố tình trùng ID.

**Chính sách B — Gateway là nguồn tin cậy:** edge proxy loại bỏ header do client tự gửi hoặc tạo ID riêng, rồi gắn một header nội bộ chỉ có gateway quyền quản lý. Service phía sau tin vào giá trị **qua kênh đã xác thực và được giới hạn network**, đồng thời vẫn kiểm tra tính hợp lệ để phòng cấu hình sai.

Nếu yêu cầu chống giả mạo mạnh, **chỉ dùng UUID hay regex không đủ**. Cần cơ chế xác thực nguồn, chính sách gateway và khả năng audit độc lập.

## 5. Quy tắc kiểm tra ID đầu vào

Một policy minh họa dễ thực hiện:

- Chỉ nhận **đúng một giá trị header**.
- Giới hạn **tối đa 64 ký tự**.
- Bắt đầu bằng chữ hoặc số ASCII.
- Các ký tự tiếp theo chỉ gồm `A-Z`, `a-z`, `0-9`, dấu chấm `.`, gạch dưới `_`, gạch nối `-`.
- Không cho khoảng trắng, dấu phẩy, slash, dấu nháy, tab hoặc newline.
- Không đưa raw ID không hợp lệ vào MDC, response hoặc message log.
- Nếu thiếu/sai/trùng, dùng UUID ngẫu nhiên mới theo policy ví dụ.

Biểu thức chính quy của ví dụ:

~~~regex
[A-Za-z0-9][A-Za-z0-9._-]{0,63}
~~~

Dấu neo được thực hiện thông qua Java `Matcher.matches()`, yêu cầu **toàn bộ chuỗi** khớp. Regex này chấp nhận ID dài từ **1 đến 64 ký tự**, có ký tự đầu ASCII alphanumeric.

| ID đầu vào | Được chấp nhận theo policy ví dụ? | Lý do |
| --- | --- | --- |
| `req-20261109-01` | Có | Các ký tự trong allowlist |
| `a` | Có | Một ký tự đầu hợp lệ |
| `4a93d0b3-2f5c-4bc0-9a61-b47c3f2bc788` | Có | UUID dạng text hợp lệ theo tập ký tự |
| `bad id!` | Không | Khoảng trắng và dấu chấm than |
| `two,values` | Không | Dấu phẩy |
| `a/b` | Không | Dấu slash |
| Chuỗi 200 ký tự | Không | Vượt giới hạn |
| Chuỗi rỗng | Không | Không có ký tự đầu |
| Dòng có CR/LF | Không | Không thuộc tập ký tự cho phép; HTTP stack có thể từ chối sớm |

**Đây là policy lựa chọn của ứng dụng**, không phải một tiêu chuẩn phổ quát về correlation ID. Một hệ thống chỉ chấp nhận UUID chuẩn có thể dùng một policy khác. Nếu dùng OpenTelemetry trace IDs, cần tuân theo định dạng/semantic của Trace Context, không áp đặt regex chung ở trên.

### Không chỉ dùng trim rồi tin luôn

Một số HTTP stack loại bỏ khoảng trắng ở rìa header khi parse. Cơ chế đó không đồng nghĩa input ban đầu hợp lệ, và `trim()` tùy tiện có thể đổi ID từ `" abc "` thành `"abc"` gây nhập nhằng.

Có thể chọn chuẩn hóa có kiểm soát, nhưng nên quy định rõ trong contract. Ví dụ ở đây **không tự trim**: chuỗi đưa tới tầng ứng dụng phải khớp toàn bộ allowlist.

### Trường hợp header trùng

Một client có thể gửi hai header cùng tên:

~~~http
X-Correlation-ID: one
X-Correlation-ID: two
~~~

API HTTP Java có thể trả chúng dưới dạng **danh sách nhiều giá trị**; một proxy khác có thể gộp thành `one,two`. Hai trường hợp đều phải được xử lý theo chính sách. Ví dụ Java dưới đây **chỉ chấp nhận danh sách đúng một phần tử có format hợp lệ**; chuỗi ghép bằng dấu phẩy cũng sẽ bị regex loại.

Không lấy bừa **phần tử đầu tiên** nếu một request có nhiều giá trị chưa được xác định. Khi các tầng gateway và ứng dụng có cách chọn khác nhau, việc điều tra có thể không nhất quán.

## 6. Khi thiếu hoặc sai: tạo ID, từ chối hay dùng ID gateway?

Không có chính sách duy nhất phù hợp với mọi ứng dụng.

| Tình huống | Lựa chọn phổ biến | Điều cần ghi nhớ |
| --- | --- | --- |
| Không có header | Tạo ID mới | Không có nghĩa request lỗi |
| Header rỗng/sai format | Tạo ID mới hoặc trả 400 theo contract | Không echo raw giá trị sai |
| Header bị gửi trùng | Tạo ID mới hoặc từ chối | Tránh cách hiểu khác nhau giữa proxy/service |
| Header hợp lệ từ client ngoài | Chấp nhận nếu API cho phép | Không coi đó là danh tính đáng tin |
| ID đã do gateway đáng tin cấp | Sử dụng lại sau kiểm tra | Cần bảo vệ tuyến giữa gateway và service |
| Request mở một workflow hoàn toàn mới | Có thể tạo workflow ID mới | Định nghĩa mối quan hệ với request/trace ID |
| Downstream nhận ID từ upstream | Nên giữ ID hiệu lực nếu policy cho phép | Không tự tạo mới mỗi hop |

Đối với ví dụ học tập, chọn policy **graceful fallback**: ID đầu vào không hợp lệ thì tạo **UUID mới** rồi tiếp tục xử lý request. Lý do là correlation ID phục vụ chẩn đoán và không nhất thiết là điều kiện nghiệp vụ bắt buộc.

Với hệ thống có contract yêu cầu ID chính thức từ client hoặc gateway, có thể trả lỗi 400 thay vì tạo mới. Nếu chọn cách đó, phải kiểm tra các lỗi và đảm bảo không log raw header độc hại.

### Vì sao dùng UUID.randomUUID()?

Java 17 có:

~~~java
String correlationId = java.util.UUID.randomUUID().toString();
~~~

Phương thức này tạo UUID version 4 phù hợp làm ID ngẫu nhiên cho mục đích tương quan thông thường. Kết quả có dạng 36 ký tự, ví dụ:

~~~text
4a93d0b3-2f5c-4bc0-9a61-b47c3f2bc788
~~~

Đây là **ví dụ về hình dạng**, không phải output cố định của một lần gọi. Xác suất trùng khi dùng đúng rất nhỏ, nhưng UUID không phải chứng nhận quyền truy cập. Không dùng correlation ID làm authentication token, không dựa vào “khó đoán” để cho phép xem dữ liệu.

### Có nên ghi nhận lý do phải tạo ID mới?

Có thể ghi một metric/counter hoặc một log event an toàn, chẳng hạn:

~~~text
event=correlation_id_regenerated reason=INVALID_FORMAT
~~~

**Không cần ghi raw ID bị từ chối**. Nếu vẫn cần điều tra nguồn vi phạm, ghi các thông tin đã được cho phép như route template, gateway name, loại lỗi và request ID mới; không phản chiếu bí mật hoặc ký tự điều khiển từ client vào log.

## 7. Lưu ID trong request context và MDC

Sau khi nhận/khởi tạo ID, ứng dụng cần cho phép các dòng log cùng request mang chung ID. Với Java, **SLF4J MDC** (*Mapped Diagnostic Context*) là một cơ chế phổ biến.

~~~java
// Đoạn minh họa trong một method có effectiveId và logger.
try (org.slf4j.MDC.MDCCloseable ignored =
        org.slf4j.MDC.putCloseable("correlationId", effectiveId)) {
    logger.info("event=request_received");
    // Thực thi nghiệp vụ của request.
}
~~~

MDC thường mang **key–value string** trong context của thread hiện tại. Backend như Logback có thể đưa value ra pattern:

~~~xml
<pattern>%level | correlationId=%X{correlationId} | %msg%n</pattern>
~~~

Nếu gọi log ở bên ngoài scope MDC, `%X{correlationId}` thường không có giá trị; nếu không dọn MDC ở thread pool, request sau có thể **kế thừa nhầm ID của request trước**.

**Đưa ID vào MDC là việc bổ sung context, không phải tự động truyền header tới downstream HTTP call.** Muốn truyền ID, mã outbound client hoặc framework instrumentation phải gửi nó trong request header/message metadata.

### Vì sao cần finally hoặc try-with-resources?

Thread của HTTP server thường được tái sử dụng. Nếu có exception trong controller mà MDC không được xóa, request kế tiếp trên cùng thread có thể nhận sai `correlationId`, dẫn đến log bị liên kết nhầm.

`MDC.putCloseable` trả về đối tượng có thể dùng trong try-with-resources để xóa key khi scope kết thúc. Với các framework có nhiều thành phần cùng quản lý MDC, cần xác định chính sách restore/clear hợp lý, tránh xóa context không thuộc quyền sở hữu của mình.

### MDC và bất đồng bộ

Không được giả định MDC tự lan truyền qua:

- `CompletableFuture.supplyAsync`.
- `ExecutorService` với các worker thread.
- Reactive pipelines.
- Threads tự tạo.
- RPC/message consumer gọi xử lý ở thread khác.

Nếu service chuyển việc sang executor, hãy **truyền correlation ID như dữ liệu** hoặc dùng cơ chế context propagation của framework, rồi thiết lập MDC trong worker **có scope và cleanup riêng**.

Đừng chỉ thiết lập MDC ở HTTP thread rồi hy vọng log ở background task có đúng ID. Nên viết test cho thread hop và kiểm tra context đã được dọn sau khi hoàn tất.

## 8. Ví dụ Java 17+: nhận correlation ID qua HTTP header

Ví dụ hoàn chỉnh này dùng:

- **JDK 17+** với `com.sun.net.httpserver.HttpServer` để tạo một endpoint HTTP local.
- **JDK HttpClient** để gửi request kiểm thử.
- **SLF4J API 2.0.17** cho Logger và MDC.
- **Logback 1.5.18** làm SLF4J provider/backend để in MDC ra stderr.

Mục tiêu của ví dụ là chứng minh **nhận đúng một header, giữ ID hợp lệ, thay ID thiếu/sai/trùng bằng UUID và dọn MDC**. Server chỉ bind loopback, dùng một worker thread cho bài thử; **không phải cấu hình server tối ưu hoặc một API production hoàn chỉnh**.

### 8.1. Cấu trúc dự án

~~~text
correlation-receive/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/CorrelationReceiveDemo.java
        └── resources/logback.xml
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>correlation-receive</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.slf4j</groupId>
      <artifactId>slf4j-api</artifactId>
      <version>2.0.17</version>
    </dependency>
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
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Bộ version trên đã được dùng để **biên dịch/chạy thử**; đó không phải tuyên bố về phiên bản mới nhất. Trong dự án thật, nên quản lý version theo dependency management và khả năng tương thích với framework.

### 8.3. logback.xml

Tạo `src/main/resources/logback.xml`:

~~~xml
<configuration>
  <appender name="STDERR" class="ch.qos.logback.core.ConsoleAppender">
    <target>System.err</target>
    <encoder>
      <pattern>%level | correlationId=%X{correlationId} | %msg%n</pattern>
    </encoder>
  </appender>
  <root level="INFO">
    <appender-ref ref="STDERR"/>
  </root>
</configuration>
~~~

Logback đọc `%X{correlationId}` từ MDC trong scope của request. `%msg` là phần message, không tự chứa correlation ID; vì thế phải cấu hình pattern/JSON encoder phù hợp.

### 8.4. CorrelationReceiveDemo.java

Tạo `src/main/java/demo/CorrelationReceiveDemo.java`:

~~~java
package demo;

import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpServer;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class CorrelationReceiveDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(CorrelationReceiveDemo.class);
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");
    private static final String HEADER = "X-Correlation-ID";

    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newSingleThreadExecutor();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.setExecutor(workers);
        server.createContext("/orders", exchange -> {
            String correlationId = receiveCorrelationId(
                    exchange.getRequestHeaders());
            try (MDC.MDCCloseable ignored =
                    MDC.putCloseable("correlationId", correlationId)) {
                LOG.info("event=request_received method={} route=/orders",
                        exchange.getRequestMethod());
                exchange.getResponseHeaders().set(HEADER, correlationId);
                byte[] body = "accepted".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, body.length);
                try (var out = exchange.getResponseBody()) {
                    out.write(body);
                }
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            String url = "http://127.0.0.1:"
                    + server.getAddress().getPort() + "/orders";
            HttpClient client = HttpClient.newHttpClient();

            HttpResponse<String> valid =
                    request(client, url, List.of("req-20261109-01"));
            HttpResponse<String> missing =
                    request(client, url, List.of());
            HttpResponse<String> invalid =
                    request(client, url, List.of("bad id!"));
            HttpResponse<String> duplicate =
                    request(client, url, List.of("one", "two"));

            String validId = value(valid);
            String missingId = value(missing);
            String invalidId = value(invalid);
            String duplicateId = value(duplicate);

            System.out.println("validPreserved="
                    + "req-20261109-01".equals(validId));
            System.out.println("missingGenerated=" + isUuid(missingId));
            System.out.println("invalidReplaced=" + isUuid(invalidId));
            System.out.println("duplicateReplaced=" + isUuid(duplicateId));
            System.out.println("mdcCleared="
                    + workers.submit(() -> MDC.get("correlationId") == null)
                            .get());
            System.out.println("bodyReceived="
                    + (valid.statusCode() == 200
                    && "accepted".equals(valid.body())));
        } finally {
            server.stop(0);
            workers.shutdownNow();
            workers.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    private static String receiveCorrelationId(Headers headers) {
        List<String> values = headers.get(HEADER);
        if (values != null && values.size() == 1) {
            String id = values.get(0);
            if (id != null && SAFE_ID.matcher(id).matches()) {
                return id;
            }
        }
        return UUID.randomUUID().toString();
    }

    private static HttpResponse<String> request(
            HttpClient client, String url, List<String> ids)
            throws Exception {
        HttpRequest.Builder builder =
                HttpRequest.newBuilder(URI.create(url)).GET();
        for (String id : ids) {
            builder.header(HEADER, id);
        }
        return client.send(builder.build(),
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    }

    private static String value(HttpResponse<?> response) {
        return response.headers().firstValue(HEADER).orElse("");
    }

    private static boolean isUuid(String value) {
        try {
            return value.length() == 36
                    && UUID.fromString(value).toString().equals(value);
        } catch (IllegalArgumentException e) {
            return false;
        }
    }
}
~~~

### 8.5. Chạy chương trình

Từ thư mục chứa `pom.xml`, dùng Maven và JDK 17+:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CorrelationReceiveDemo
~~~

**Stdout chính xác đã được kiểm chứng:**

~~~text
validPreserved=true
missingGenerated=true
invalidReplaced=true
duplicateReplaced=true
mdcCleared=true
bodyReceived=true
~~~

Bên cạnh stdout, Logback in **bốn dòng INFO trên stderr** theo pattern:

~~~text
INFO | correlationId=req-20261109-01 | event=request_received method=GET route=/orders
INFO | correlationId=<UUID được tạo> | event=request_received method=GET route=/orders
INFO | correlationId=<UUID được tạo> | event=request_received method=GET route=/orders
INFO | correlationId=<UUID được tạo> | event=request_received method=GET route=/orders
~~~

Ba chuỗi UUID trong sơ đồ stderr là **ký hiệu giải thích**, không phải literal output. Giá trị UUID thật thay đổi mỗi lần chạy nên bài kiểm thử xác nhận nó có dạng UUID thay vì in một mã giả định.

### 8.6. Phân tích từng trường hợp

1. **Header hợp lệ:** `req-20261109-01` khớp allowlist, được giữ nguyên và trả qua `X-Correlation-ID`.
2. **Header thiếu:** hàm nhận không có danh sách giá trị, tạo UUID mới; `missingGenerated=true`.
3. **Header sai:** `bad id!` có khoảng trắng và dấu chấm than, không khớp regex; server trả UUID mới thay vì echo chuỗi không hợp lệ.
4. **Header trùng:** client gửi hai giá trị cùng tên; API server trả danh sách nhiều phần tử hoặc proxy có thể gộp bằng dấu phẩy. Policy chỉ nhận đúng một giá trị hợp lệ, nên trường hợp thử được thay bằng UUID.
5. **Dọn MDC:** handler dùng try-with-resources, sau bốn request cùng chạy qua một worker thread, tác vụ kiểm tra trên chính worker xác nhận `MDC.get("correlationId") == null`.
6. **Trả response:** server trả body `accepted` và status 200; test kiểm tra response thành công.
7. **Phạm vi HTTP:** server bind vào loopback và chọn cổng ngẫu nhiên để không ảnh hưởng dịch vụ công khai. Kết nối test dùng localhost.

Đây là ví dụ ngắn để hiểu **ranh giới nhận header và context**. Trong ứng dụng thực tế, handler cần xử lý I/O lỗi, timeout, cancellation, filter chains, authentication, CORS và lifecycle phù hợp với framework; không sao chép nguyên mẫu server thử nghiệm như bộ khung triển khai production.

### 8.7. Vì sao dùng pattern Logback thay vì gắn ID vào mọi message?

Nếu ứng dụng tự viết:

~~~java
logger.info("correlationId={} event=request_received", correlationId);
~~~

mỗi lời gọi đều phải truyền đúng ID và tên trường. Khi có MDC, encoder/layout có thể tự chèn `correlationId` vào **các log event phát trong scope**, kể cả ở lớp nghiệp vụ không trực tiếp biết HTTP header.

Tuy nhiên MDC không phải cơ chế bảo mật hay storage. Nó chỉ giúp đính ngữ cảnh logging, cần dọn đúng vòng đời và đồng bộ khi đổi thread. Đối với structured logging, cấu hình JSON encoder để xuất `correlationId` thành field riêng thay vì chỉ text pattern.

## 9. Nhận ID trong Servlet filter hoặc Spring framework

Trong một ứng dụng Servlet (Tomcat, Jetty, Spring MVC...), nên nhận ID bằng **filter/interceptor/middleware tập trung** ở ranh giới request. Quy tắc tổng quát:

~~~text
onRequest:
  lấy toàn bộ các giá trị X-Correlation-ID
  chọn ID hiệu lực theo policy
  lưu ID vào request attribute/context
  set MDC correlationId trong scope
  gọi filter chain hoặc controller
  thêm response header theo chính sách
finally:
  khôi phục/dọn MDC của scope này
~~~

Đây là **pseudocode**, không phải class Servlet hoàn chỉnh. Với Servlet, method lấy header nhiều giá trị như `getHeaders(name)` hữu ích hơn chỉ `getHeader(name)` khi cần phát hiện duplicate values. Nếu chỉ dùng `getHeader`, bạn có thể vô tình lấy **một giá trị đầu tiên** và bỏ qua tình huống trùng.

### Những điều cần chú ý khi triển khai framework

- **Thứ tự filter:** nếu logging filter chạy sau các filter có thể từ chối request, một số log lỗi xác thực có thể thiếu ID. Chọn vị trí được phép để ID có mặt cho các log cần quan sát.
- **Error response:** lỗi trong controller vẫn cần cùng correlation ID nếu response còn có thể được gửi.
- **Async dispatch:** nếu Servlet chuyển request sang async, scope MDC ở thread ban đầu không tự bao trùm worker thread hoặc dispatch sau.
- **Request attributes:** có thể lưu ID hiệu lực vào attribute của request để mã xử lý không phụ thuộc trực tiếp MDC.
- **Authentication:** việc nhận ID không làm thay bước xác thực/ủy quyền; không dùng header chẩn đoán để suy ra quyền.
- **Nhiều filter trùng:** tránh mỗi filter tự tạo ID khác nhau hoặc xóa MDC của filter khác.
- **Proxy headers:** chỉ tin những header đã được gateway xử lý qua kênh tin cậy.

Nếu framework đã có instrumentation nhận trace/correlation, nên tích hợp với nó thay vì cài một filter mới cạnh tranh việc đặt requestId/traceId.

## 10. Trả correlation ID trong HTTP response

Trả ID hiệu lực qua response header thường giúp client hoặc đội hỗ trợ đối chiếu báo lỗi:

~~~http
HTTP/1.1 200 OK
X-Correlation-ID: req-20261109-01
Content-Type: application/json
~~~

Trong ví dụ Java, header response **luôn là ID đã được kiểm tra hoặc tạo mới**, không phải raw header bị từ chối.

Lợi ích:

- Người dùng có thể cung cấp một ID trong báo cáo lỗi mà không gửi nội dung nghiệp vụ nhạy cảm.
- Client biết ID nào thực sự được server dùng nếu giá trị đầu vào bị thay thế.
- API gateway/support có thể liên kết sự kiện giữa request và response.

Nhưng cần lưu ý:

- Một correlation ID **không chứng minh client sở hữu request**; hỗ trợ khách hàng vẫn phải xác minh danh tính qua kênh riêng.
- Không cho phép tra cứu log nội bộ chỉ bằng cách biết một ID công khai.
- Với browser gọi API **cross-origin**, client có thể cần `Access-Control-Expose-Headers: X-Correlation-ID` để JavaScript đọc response header.
- Nếu browser gửi custom request header `X-Correlation-ID` qua cross-origin, server có thể cần cấu hình CORS preflight và `Access-Control-Allow-Headers` phù hợp theo chính sách origin.
- Không bật CORS quá rộng chỉ để đọc correlation ID; vẫn bảo vệ các endpoint và dữ liệu nhạy cảm.

Một số hệ thống chọn không phản hồi ID cho client công khai. Đó là quyết định thiết kế API/bảo mật, không phải bắt buộc để internal logging hoạt động.

## 11. Truyền ID hiệu lực sang downstream HTTP service

Nhận ID chỉ có ích nếu những tầng tiếp theo dùng đúng nó. Với `HttpClient` Java 17:

~~~java
// Đoạn minh họa trong method có biến client, uri và effectiveId.
HttpRequest request = HttpRequest.newBuilder(uri)
        .header("X-Correlation-ID", effectiveId)
        .GET()
        .build();
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
~~~

Đây **không phải chương trình độc lập**; `client`, `uri`, `effectiveId` là các biến đã có ở tầng gọi. Điều quan trọng là truyền **effectiveId đã chọn**, không lấy lại raw header từ request gốc.

Nếu service A nhận một ID hợp lệ và gọi B rồi C, hãy duy trì ID xuyên các hop khi các hệ thống thống nhất correlation contract. Mỗi service vẫn có thể tạo `requestId` riêng cho request nội bộ, nhưng phải tách tên field để không ghi đè correlation ID của toàn workflow.

### Đừng dựa vào MDC làm giao thức truyền

MDC chỉ là context logging trong cùng tiến trình/thread và **không tự thêm HTTP headers**. Để outbound service nhận ID cần:

- Truyền ID tường minh vào client request; hoặc
- Dùng client interceptor/instrumentation được cấu hình để lấy context hiệu lực và gắn header.

Một interceptor phải có chính sách tránh gửi ID từ một trust domain này sang một domain bên ngoài nếu không được phép. Không tự động forward toàn bộ request headers vào HTTP call khác; chỉ truyền những header cần thiết đã được kiểm tra.

## 12. Nhận correlation ID ngoài HTTP

Ý tưởng tương tự khi xử lý message và RPC, nhưng **nơi chứa metadata khác nhau**.

### Queue hoặc event bus

Một message có thể mang:

~~~text
topic: payment-events
headers:
  X-Correlation-ID: req-20261109-01
payload:
  event: payment_retry
~~~

Đây là biểu diễn minh họa, không phải cú pháp API bắt buộc của Kafka, RabbitMQ hoặc JMS. Khi consumer nhận message:

1. Đọc correlation ID trong **message headers/properties** theo contract.
2. Kiểm tra type/encoding, chiều dài và policy tin cậy.
3. Tạo ID mới nếu không có/sai theo quy tắc.
4. Đưa ID vào scope xử lý và logger context.
5. Truyền tiếp ID khi phát message mới nếu chúng thuộc cùng workflow.
6. Dọn context sau khi xử lý message, kể cả khi lỗi hoặc retry.

Nếu message được retry, cần quyết định giữ nguyên correlation ID của workflow và dùng thêm attempt/message ID để phân biệt từng lần xử lý. Không tạo correlation ID mới mỗi retry nếu điều đó khiến log mất khả năng liên kết.

### gRPC

gRPC truyền metadata theo quy tắc header của HTTP/2 và gRPC. Hãy dùng **server interceptor** phù hợp thay vì tự xử lý raw HTTP header trong business method. Chú ý kiểu metadata key, ký tự hợp lệ, giới hạn độ dài và cách propagation giữa calls.

### Batch/job

Với công việc không bắt đầu từ HTTP request, có thể tạo correlation ID mới tại **đầu job**, gắn vào toàn bộ bước xử lý hoặc truyền qua task context. Nếu một job kích hoạt nhiều giao dịch độc lập, cân nhắc tách `jobId` và `correlationId` để không gom quá nhiều sự kiện không liên quan.

## 13. Correlation ID và distributed tracing khác nhau ở đâu?

**Correlation ID** là khóa nối log theo quy ước ứng dụng. **Distributed tracing** cung cấp cấu trúc trace/span, quan hệ cha–con, sampling và chuẩn propagator.

Một trace theo W3C Trace Context sử dụng header như `traceparent`, có **trace-id**, **parent-id** và **trace-flags** theo quy tắc riêng. Không nên:

- Lấy nguyên toàn bộ `traceparent` làm `correlationId` mà không có thiết kế rõ.
- Tạo một UUID correlation ID rồi nhét vào vị trí `traceparent` sai format.
- Thay đổi trace-id trên mỗi hop mà tưởng rằng các span vẫn thuộc cùng trace.
- Gộp `spanId` và `correlationId` vào cùng một field khiến truy vấn nhầm.
- Tin header tracing ngoài internet là chứng nhận đã xác thực người dùng.

Hướng tích hợp thực dụng:

| Nhu cầu | Dữ liệu nên dùng |
| --- | --- |
| Liên kết các log cùng workflow theo hợp đồng ứng dụng | `correlationId` |
| Liên kết một HTTP request duy nhất | `requestId` nếu được tách riêng |
| Tra cứu trace end-to-end | `traceId` do tracing instrumentation cung cấp |
| Tra cứu một operation/span | `spanId` |

Nếu ứng dụng đã có tracing chuẩn và mọi service ghi `traceId` vào log, có thể không cần phát minh thêm một correlation ID mới. Tuy nhiên nếu có workflow ngoài trace hiện tại (job dài, retry nhiều message, batch nhiều lần gọi), một ID nghiệp vụ-tương quan độc lập vẫn có ích. Chọn theo **ngữ nghĩa và câu hỏi cần truy vấn**, không theo tên gọi cho có.

## 14. Bảo mật, dữ liệu cá nhân và chống lạm dụng

Mặc dù correlation ID không phải dữ liệu bí mật mặc định, header nhận từ client vẫn là dữ liệu bên ngoài cần kiểm tra.

Các biện pháp thực hành:

1. **Giới hạn chiều dài và ký tự:** tránh newline/control characters và ID quá lớn.
2. **Hạn chế duplicate/ambiguous headers:** chọn chính sách reject/regenerate rõ.
3. **Không log raw ID bất hợp lệ:** log reason code thay vì dữ liệu có thể chứa secret.
4. **Không dùng ID làm authorization:** biết correlation ID không cho phép đọc session hay log nội bộ.
5. **Không đồng nhất ID với user identity:** có thể cần cùng một correlation ID cho nhiều service nhưng vẫn xác thực user riêng.
6. **Bảo vệ trust boundary:** gateway có quyền quản lý ID nội bộ nếu policy yêu cầu.
7. **Không trộn PII vào ID:** đừng chọn email, số điện thoại hoặc token làm correlation ID.
8. **Kiểm soát retention và quyền xem log:** correlation ID giúp tra cứu, nhưng log còn chứa nhiều field nhạy cảm khác.
9. **Không làm metric label bằng correlationId:** giá trị rất nhiều/duy nhất gây cardinality cao trong metrics.
10. **Giám sát chất lượng header:** đếm sự kiện missing/invalid/duplicate bằng metric có label cardinality thấp.

### Correlation ID từ user có thể trùng có chủ ý

Một client có thể cố ý gửi cùng một ID cho nhiều request. Theo policy chấp nhận client-supplied ID, log của chúng có thể bị nhóm cùng nhau. Nếu cần phân biệt từng request, hãy thêm `requestId` nội bộ do server tạo riêng; đó là **một field khác**, không phải chỉ chỉnh regex.

## 15. Hiệu năng và vòng đời request

Việc đọc một header, kiểm tra regex ngắn và tạo UUID khi cần thường không quá nặng trong phần lớn HTTP services. Tuy nhiên cơ chế context/logging có các chi phí cần cân nhắc:

- `UUID.randomUUID()` tạo chuỗi mới; không tạo ID nhiều lần cho cùng một request.
- MDC là context theo thread/implementation; thiết lập/xóa nhiều lần ở từng method là thừa.
- JSON encoder/structured logging có thể ghi correlation ID lặp trong mọi event, làm tăng bytes.
- Một lượng log INFO lớn trong high-throughput endpoint có thể chiếm nhiều dung lượng hơn chi phí nhận ID.
- Async framework cần context propagation đúng; rò rỉ MDC gây lỗi dữ liệu khó phát hiện hơn chi phí runtime.
- Nếu nhiều request dùng correlation ID có cardinality cao, index/storage cần thiết kế dựa trên nhu cầu tìm từng request.

Có thể đo: tỷ lệ request có inbound ID hợp lệ, tỷ lệ regenerate, tỷ lệ log thiếu correlationId, overhead của logger encoder và mức tăng payload. Không cố “tối ưu” bằng cách dùng chung một ID cho nhiều request độc lập chỉ để giảm cardinality.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách khắc phục |
| --- | --- | --- |
| Log có correlationId=null | Chưa set MDC hoặc pattern/encoder đọc sai key | Xác minh key `correlationId` và scope |
| Request sau mang ID của request trước | Quên dọn ThreadLocal/MDC trong thread pool | try-with-resources hoặc finally |
| Một request tạo nhiều ID | Nhiều filter/controller tự generate | Chỉ một entrypoint chọn effective ID |
| Header trùng nhưng lấy giá trị đầu | Dùng getHeader một giá trị và bỏ qua danh sách | Đọc toàn bộ giá trị, chọn policy |
| Giá trị sai có dấu xuống dòng trong log | Ghi raw header mà không validate | Allowlist, không log raw invalid |
| Client gửi ID nhưng response dùng ID khác | Gateway đã ghi đè hoặc validator regenerate | Định nghĩa contract và phản hồi ID hiệu lực |
| Microservice B không thấy ID từ A | MDC không tự truyền HTTP header | Outbound client interceptor/tường minh |
| Async task bị mất correlationId | Context không tự lan qua executor/reactive | Propagate context có scope riêng |
| Mọi request trên service đều có cùng ID | Static/global variable hoặc reuse context sai | Scope theo request, không lưu global |
| Log theo traceId nhưng không theo correlationId | Hai ID khác loại, không map field | Tách field và chiến lược tìm log |
| Correlation ID bị dùng để xem dữ liệu khách hàng | Hiểu nhầm nó là auth token | Luôn xác thực/ủy quyền riêng |
| Metrics tăng mạnh vì nhiều series | Dùng correlationId làm metric label | Chỉ giữ ID trong logs/traces |
| Browser không đọc được response ID | Thiếu CORS expose header | Cấu hình `Access-Control-Expose-Headers` phù hợp |
| Browser không gửi được custom header cross-origin | CORS preflight/allow headers chưa đúng | Cấu hình `Access-Control-Allow-Headers` và origin |
| Log trước controller thiếu ID | Filter được cài quá muộn | Đặt middleware đủ sớm trong pipeline |
| ID không tìm thấy sau khi gửi message | Consumer không đọc/forward message metadata | Định nghĩa hợp đồng correlation trên bus |
| Invalid ID được chấp nhận nhầm | Chỉ kiểm tra non-null hoặc cắt chuỗi tùy tiện | Matcher.matches, max length, reject ambiguous |
| Log chứa email/token ở correlation ID | Chấp nhận chuỗi tùy ý và ghi thẳng | Policy allowlist và kiểm soát dữ liệu từ nguồn |

### Quy trình điều tra nhanh

1. Xác nhận header thực sự đến tới **Java ingress** hay đã bị gateway xóa/đổi.
2. Xem code nào quyết định **effective correlation ID** và tại thời điểm nào.
3. Kiểm tra số lượng header, regex, length và quy tắc fallback.
4. Xem MDC/request context có được set trước log đầu tiên không.
5. Xác nhận Logback/Log4j2 encoder thật sự xuất field `correlationId`.
6. Kiểm tra cleanup sau cả response thành công và exception.
7. Với async thread, xác minh propagation và cleanup riêng.
8. Kiểm tra outbound header và context của service downstream.
9. Query log theo ID hiệu lực nhận từ response, không raw ID bị loại.
10. Xác nhận collector parse/index và retention để phân biệt lỗi nhận ID với lỗi mất log.

## 17. Ma trận kiểm thử đề xuất

| Tình huống | Dữ liệu gửi | Kỳ vọng |
| --- | --- | --- |
| Header hợp lệ | `req-20261109-01` | Giữ nguyên |
| Header thiếu | Không có X-Correlation-ID | Tạo UUID hiệu lực |
| Header rỗng | Empty string | Tạo mới hoặc 400 theo contract |
| Header có khoảng trắng | `bad id!` | Không dùng nguyên bản |
| Header quá dài | Hơn 64 ký tự | Tạo mới hoặc 400 |
| Header có ký tự điều khiển | Giá trị bị HTTP stack từ chối hoặc tới tầng app | Không đưa raw input vào log |
| Hai header cùng tên | `one`, `two` | Regenerate/reject theo policy |
| Hai dạng tên hoa-thường | `x-correlation-id` | Hiểu cùng tên HTTP |
| Response thành công | 200 | Header phản hồi là effective ID |
| Response lỗi | 4xx/5xx sau ingress | Nếu response còn writable, trả đúng effective ID |
| Log nhiều lớp trong một request | Các service method khác nhau | Cùng correlationId |
| Request thứ hai cùng worker | Thread pool reuse | Không mang MDC cũ |
| CompletableFuture | Async hop | ID được propagate nếu đã cấu hình |
| Gọi downstream | HttpClient hoặc interceptor | Header downstream giữ effective ID |
| Message retry | Cùng workflow | ID workflow được giữ theo contract |
| Client cố dùng cùng ID cho hai request | ID hợp lệ, gửi lặp | Policy quyết định; có thể cần requestId riêng |
| Không có backend/provider | Chỉ có SLF4J API | Cần kiểm tra provider nếu không thấy log |
| Collector không index field | JSON chỉ có message text | Kiểm tra encoder/mapping end-to-end |

Không chỉ test code chọn ID: phải thử log trước/sau exception, handler filter, async dispatch và middleware order vì lỗi tương quan thường xuất hiện **sau khi phần nhận header đã đúng**.

## 18. Bài tập và đáp án

### Bài tập 1 — Header thiếu

Client gọi `GET /orders` không gửi `X-Correlation-ID`.

**Câu hỏi:** có nên cho request thất bại ngay không?

**Đáp án:** tùy contract. Trong đa số API chọn fallback, ứng dụng tạo ID mới, đưa vào logs và có thể trả về trong response. Không có header chẩn đoán không nhất thiết là lỗi nghiệp vụ.

### Bài tập 2 — ID có newline

Một giá trị bên ngoài cố chèn newline và dòng `ERROR payment succeeded`.

**Câu hỏi:** vì sao không đưa thẳng vào MDC?

**Đáp án:** có nguy cơ log injection và lỗi định dạng. Header có thể bị HTTP stack từ chối từ sớm; nếu vẫn tới tầng app, validate ký tự/độ dài và regenerate/reject, không ghi raw giá trị độc hại.

### Bài tập 3 — Header trùng

Một proxy chuyển đến hai giá trị: `a-1` và `b-2`.

**Câu hỏi:** dùng `getHeader` lấy một giá trị đầu có đủ không?

**Đáp án:** không nếu contract yêu cầu phát hiện duplicate. Nên lấy toàn bộ danh sách và xử lý nhất quán. Ví dụ chọn regenerate khi không có đúng một giá trị hợp lệ.

### Bài tập 4 — MDC không dọn

Một servlet thread xử lý request A, set correlationId A nhưng quên clear; sau đó xử lý request B không có header.

**Câu hỏi:** hậu quả?

**Đáp án:** log B có thể bị gắn ID A, gây liên kết nhầm. Cần một effective ID riêng cho B và cleanup context trong finally/try-with-resources.

### Bài tập 5 — Trace ID khác correlation ID

Một service có `traceId` do OpenTelemetry cấp, đồng thời nhận `X-Correlation-ID` từ workflow.

**Câu hỏi:** nên ghi đè traceId bằng correlationId không?

**Đáp án:** không. Giữ field riêng và quy tắc propagation riêng; có thể ghi cả hai nếu có giá trị điều tra.

### Bài tập 6 — Browser không thấy response header

API trả `X-Correlation-ID` nhưng JavaScript gọi cross-origin không đọc được.

**Câu hỏi:** header có chắc bị thiếu không?

**Đáp án:** chưa chắc. Kiểm tra CORS `Access-Control-Expose-Headers` phù hợp; nếu client cần gửi custom header, kiểm tra thêm preflight và allow-headers theo policy.

### Bài tập 7 — Mã ID làm metric label

Một ứng dụng thêm correlationId vào label của counter mỗi request.

**Câu hỏi:** vấn đề?

**Đáp án:** cardinality rất cao, có thể làm hệ thống metrics tốn tài nguyên. Chỉ dùng correlation ID cho log/traces và tìm kiếm mục tiêu; dùng labels metrics ổn định như route template/status class.

### Bài tập 8 — Truyền sang hệ queue

Một HTTP request phát message xử lý background. Consumer có log nhưng thiếu correlationId.

**Câu hỏi:** nhận HTTP header đúng rồi vì sao vẫn thiếu?

**Đáp án:** MDC của HTTP thread không tự đi qua message bus. Phải đặt ID trong message metadata và consumer nhận/thiết lập scope riêng.

## 19. Checklist trước khi triển khai

- [ ] Thống nhất header name và field name trong log.
- [ ] Xác định có nhận ID do client gửi hay chỉ tin gateway.
- [ ] Đọc toàn bộ header values, không bỏ qua trường hợp trùng.
- [ ] Có allowlist ký tự, độ dài tối đa, policy missing/invalid rõ.
- [ ] Không log hoặc trả lại raw ID không hợp lệ.
- [ ] Dùng UUID hoặc ID generator được phê duyệt khi cần fallback.
- [ ] Chỉ chọn **một effective ID** tại entrypoint mỗi request.
- [ ] Đưa ID vào request context/MDC đủ sớm và dọn trong finally.
- [ ] Không dùng global/static mutable field để lưu ID request.
- [ ] Test cleanup ở thread pool và propagation khi async.
- [ ] Cấu hình encoder in correlationId ở field/pattern mong muốn.
- [ ] Truyền effective ID cho outbound HTTP/RPC/message nếu thuộc cùng workflow.
- [ ] Trả effective ID trong response nếu contract cho phép; kiểm tra CORS khi cần.
- [ ] Tách correlationId khỏi traceId/spanId và khỏi ID nghiệp vụ.
- [ ] Không dùng correlationId làm auth token hoặc metric label.
- [ ] Kiểm tra gateway policy, header rewrite và trust boundaries.
- [ ] Không cho dữ liệu cá nhân/token xuất hiện trong correlation ID.
- [ ] Đếm tỉ lệ missing/invalid/duplicate mà không lộ raw input.
- [ ] Kiểm tra log end-to-end từ ingress tới collector và truy vấn.
- [ ] Kiểm thử missing, invalid, duplicate, exception, retry, async và nhiều service.

## 20. Tài liệu tham khảo

- [SLF4J manual](https://www.slf4j.org/manual.html): Logger, MDC và cách tích hợp facade với backend.
- [Logback MDC](https://logback.qos.ch/manual/mdc.html): cách dùng mapped diagnostic context và pattern output.
- [JDK 17 HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): HTTP server JDK dùng trong ví dụ.
- [JDK 17 HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): gửi HTTP request và đọc response.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): phân biệt trace context chuẩn với correlation header do ứng dụng quy ước.

**Ghi nhớ:** Nhận correlation ID đúng không phải chỉ lấy một string từ HTTP header. Cần **một contract về nguồn, kiểm tra độ dài/ký tự/số giá trị, chọn ID hiệu lực, đặt context đúng scope, dọn MDC, phản hồi hoặc truyền tiếp có kiểm soát**, và cuối cùng kiểm chứng mọi log của cùng workflow có thể được liên kết chính xác. Đặc biệt, correlation ID giúp điều tra **chứ không chứng minh danh tính hay quyền truy cập**.