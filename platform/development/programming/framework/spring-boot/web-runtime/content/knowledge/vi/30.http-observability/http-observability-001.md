# Access log của máy chủ và log xử lý yêu cầu của ứng dụng trong Spring Boot

## 1. Mục tiêu và phạm vi

Khi người dùng báo “API trả 500”, “request mất 4 giây” hay “không thấy lời gọi trong service”, kỹ sư cần phân biệt ít nhất **hai nguồn thông tin**:

1. **Server access log** (nhật ký truy cập của máy chủ HTTP): ghi nhận các request mà web server/container quan sát được, thường có thời điểm, HTTP method, đường dẫn, status, số byte và thời gian xử lý.
2. **Application request log** (nhật ký xử lý request của ứng dụng): ghi lại những bước do code ứng dụng biết, ví dụ request bắt đầu/kết thúc một filter, controller thực thi, gọi downstream, kết quả nghiệp vụ, exception và **correlation/request ID**.

Hai nguồn này **bổ sung nhau, không thay thế nhau**. Access log trả lời “máy chủ đã phục vụ request nào và response nhìn ở tầng đó ra sao”; application log trả lời “logic ứng dụng đã xử lý gì và quyết định nào dẫn đến kết quả ấy”. Khi ứng dụng nằm sau reverse proxy, còn có **edge/proxy access log**, có thể ghi được request mà Tomcat chưa từng nhận.

Bài học dành cho **Spring Boot web runtime**, sử dụng Spring MVC/Servlet với **Tomcat embedded**, Java 17+ và một ví dụ Maven chạy được. Ngoài Tomcat, bài cũng giải thích sự khác biệt khi dùng Jetty, Undertow, WebFlux/Netty; HTTP async/streaming, MDC, Spring Security, reverse proxy, tracing, dữ liệu nhạy cảm và kiểm thử.

Sau khi hoàn thành, bạn có thể:

- Bật và cấu hình Tomcat access log đúng vị trí; phân biệt pattern `%m`, `%U`, `%s`, `%b`, `%D` và `%{X-Request-Id}o`.
- Viết filter dùng `OncePerRequestFilter` để gắn ID, đưa ID vào response header/MDC và ghi application log **không lộ password, cookie hoặc query**.
- Hiểu chính xác giới hạn của filter với async dispatch, exception và final response status.
- Đối chiếu access log và application log bằng ID thay vì dựa vào thread name/IP.
- Kiểm thử response status và request ID qua **HTTP server thật**, cũng như kiểm tra file access log theo cách không phụ thuộc một chuỗi log thời gian cố định.
- Chẩn đoán sự khác nhau giữa 4xx/5xx do proxy, container, filter, Spring Security hay business service.
- Lựa chọn log fields, mức log, retention, sampling và chính sách bảo vệ dữ liệu cho production.

**Nguyên tắc:** một log tốt cần **đúng tầng**, **đúng thời điểm**, có **định danh liên hệ giữa các tầng**, không làm lộ bí mật và không tự biến thành nguyên nhân làm ứng dụng quá tải.

## 2. Ba tầng log trên đường đi của một HTTP request

Giả sử:

```text
Browser / mobile / API client
     |
     | GET https://api.example.com/api/items/42
     v
Reverse proxy / Load balancer / Ingress
     |  -> proxy access log: edge status, public host, upstream time
     |
     | GET http://app-service:8080/api/items/42
     v
Embedded Tomcat
     |  -> Tomcat access log: request/response được container quan sát
     |
     +--> Servlet Filters / Spring Security
     |         |
     |         +--> application filter log: request ID, timing tại filter
     |         |
     v         v
Spring MVC DispatcherServlet -> Controller -> Service -> Database/HTTP client
                                |
                                +--> business/application logs
     |
     v
Response quay lại client qua Tomcat, proxy và network
```

Có thể xuất hiện những khác biệt hợp lệ:

- Proxy trả **403** vì WAF, nên **không có** Tomcat access log hoặc application log cho request ấy.
- Tomcat từ chối một HTTP request malformed **trước khi dispatch**; app filter/controller không chạy.
- Spring Security trả **401/403** trong filter chain; Tomcat access log thường vẫn thấy nếu request đến container, nhưng một application filter đăng ký **sau** security chain có thể không chạy.
- Controller trả **200**, nhưng proxy không gửi xong body vì client ngắt; metrics cuối tại proxy, Tomcat và log của controller có thể không đồng nhất về duration/bytes.
- Controller ghi “bắt đầu xử lý” nhưng async operation/stream chưa hoàn thành; access log được ghi ở giai đoạn khác.
- Một request thành công đến **nhiều replicas** và log application nằm ở pod A trong khi edge log ở gateway. Cần correlation ID/tracing context để nối các bản ghi.

**Không được suy ra “request chưa từng xảy ra” chỉ vì không thấy log trong controller.** Trước tiên xác định request đã đi tới tầng nào.

## 3. So sánh server access log với application request log

| Tiêu chí | Server access log | Application request/business log |
| --- | --- | --- |
| Được tạo bởi | Tomcat AccessLogValve, Jetty/Undertow access log, gateway | SLF4J + Logback/Log4j2, filter/interceptor/controller/service |
| Phạm vi | Request đã tới tầng HTTP tương ứng | Đoạn code/thành phần đã thực thi |
| Trường thường có | Time, remote address, method, URI path, HTTP status, bytes, duration | requestId/traceId, route template, service event, outcome, dependency, exception |
| Đơn vị duration | Do container/proxy định nghĩa, ví dụ Tomcat `%D` là **microseconds** | Do code đo, ví dụ `System.nanoTime()` đổi thành **milliseconds** |
| Kết quả HTTP | Có thể nhìn status cuối ở tầng server | Filter sớm có thể chỉ thấy status lúc thoát filter, chưa chắc final |
| Có thấy request bị từ chối sớm? | Ở tầng container: có thể; tại proxy: tùy hop | Tùy filter order và request có vào app hay không |
| Có biết dữ liệu nghiệp vụ? | Thường không | Có nếu code chủ động log thông tin đã được phép |
| Có sẵn correlation ID? | Không chắc; phải cấu hình pattern/header hoặc tracing | Không chắc; phải thiết kế MDC/tracing |
| Nguy cơ dữ liệu nhạy cảm | Raw URL/query, IP, Referer, cookie, session ID, header | Body, token, secret, PII, exception, user-controlled strings |
| Ghi ra đâu? | File/server pipeline hoặc collector do container/hạ tầng cấu hình | Console/file/structured JSON/OTLP qua hệ thống logging |
| Phù hợp việc gì? | Audit truy cập HTTP, status, throughput, timing tổng quát | Điều tra nghiệp vụ, phân biệt bước lỗi, liên kết trace/span, root cause |

**Cùng một tên “access log” có thể chỉ log Nginx, Tomcat hoặc một middleware do đội phát triển viết.** Khi họp điều tra lỗi, hãy luôn nói rõ **log của tầng nào, theo đồng hồ nào, field nào**.

### 3.1. Access log không phải audit log nghiệp vụ

Một HTTP `POST /payments` trả 200 **không** chứng minh thanh toán được ghi sổ hoặc tiền đã chuyển thành công. Một request có thể trả 202 nhưng công việc trong queue sau đó thất bại. Nếu nghiệp vụ cần audit:

- Ghi event như `PaymentRequested`, `PaymentAuthorized`, `PaymentSettled` trong cơ chế audit bền vững phù hợp.
- Sử dụng transaction/outbox/idempotency khi cần, chứ không tin console log là cơ sở dữ liệu giao dịch.
- Định nghĩa principal, tenant, object ID, hành động, kết quả và timestamp theo chính sách privacy.
- Quy định tính toàn vẹn/retention/quyền truy cập audit trail riêng với debug log.

**Access log là chứng cứ về HTTP**, không tự thay thế lịch sử thay đổi dữ liệu hoặc bằng chứng hoàn tất nghiệp vụ.

## 4. Tomcat access log trong Spring Boot

### 4.1. Bật access log bằng application.properties

Với **Spring Boot 3.5.x + embedded Tomcat**, dùng:

```properties
# Chỉ ví dụ môi trường local/demo; chọn nơi lưu được phê duyệt cho production.
server.tomcat.basedir=./tomcat-demo

server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.directory=logs
server.tomcat.accesslog.prefix=access
server.tomcat.accesslog.suffix=.log

# Tạo file theo ngày; ở production cần retention/rotation tập trung.
server.tomcat.accesslog.rotate=true
server.tomcat.accesslog.max-days=7

# Chỉ dùng buffered=false để quan sát log nhanh trong demo;
# buffered=true (mặc định) thường hiệu quả hơn khi lưu lượng cao.
server.tomcat.accesslog.buffered=false

# Method, URL path (không có query), status, byte và thời gian (microseconds).
# Cuối dòng đọc X-Request-Id do response filter của demo tạo.
server.tomcat.accesslog.pattern=%t %a %m %U %s %b %D %{X-Request-Id}o
```

Điểm quan trọng:

- `server.tomcat.accesslog.enabled` mặc định là `false` trong cấu hình Spring Boot 3.5.
- Nếu không đặt `server.tomcat.basedir`, Tomcat embedded có thể dùng thư mục tạm; file access log không nhất thiết nằm ngay cạnh source code hoặc JAR.
- `directory=logs` là đường dẫn tương đối với Tomcat base dir; với cấu hình trên, log dự kiến dưới `./tomcat-demo/logs/` tính theo working directory khi chạy app.
- `buffered=false` giúp file cập nhật dễ quan sát sau mỗi request nhưng có thể tăng I/O. Production thường dùng buffering phù hợp và collector/rotation; **không coi log file được flush mỗi request là bắt buộc**.
- `max-days=7` chỉ minh họa vòng đời file theo cấu hình Tomcat; doanh nghiệp thường có log aggregation, retention và legal hold ở hạ tầng.
- Các property trên dành riêng cho **Tomcat**. Nếu đổi sang Jetty/Undertow, chúng không tự cấu hình access log của server mới.
- Tùy deployment, container file system có thể ephemeral/read-only. Đặt đường dẫn writable, volume mount hoặc tích hợp logging pipeline do nền tảng hỗ trợ.
- Một ứng dụng có thể được deploy như WAR trong Tomcat bên ngoài; khi đó host Tomcat có cấu hình/access log riêng, không nên giả định mọi Boot property embedded server đều có hiệu lực.

### 4.2. Hiểu đúng Tomcat pattern tokens

Tomcat `AccessLogValve` hỗ trợ pattern; những ký hiệu hữu ích:

| Token | Ý nghĩa |
| --- | --- |
| `%t` | Thời điểm theo Common Log Format |
| `%a` | Remote IP address theo góc nhìn Tomcat (có thể là proxy IP) |
| `%m` | HTTP method, ví dụ GET |
| `%U` | Request URL path, **không gồm query string** |
| `%r` | Dòng request ban đầu; có thể chứa query/đầu vào nhạy cảm |
| `%q` | Query string; **không nên bật bừa bãi** |
| `%s` | HTTP response status |
| `%b` | Số byte body được gửi, trừ headers; có thể là `-` nếu không gửi |
| `%D` | Thời gian xử lý request tính bằng **microseconds** |
| `%T` | Thời gian xử lý tính bằng **seconds** |
| `%F` | Thời gian tới thời điểm commit response (milliseconds) |
| `%I` | Thread name ở tầng request; không phải user/session ID |
| `%X` | Trạng thái connection khi response hoàn tất |
| `%{X-Request-Id}o` | Giá trị response header `X-Request-Id` |
| `%{Some-Header}i` | Giá trị request header được chỉ định; cẩn thận dữ liệu không tin cậy |
| `%{attribute}r` | Giá trị request attribute, nếu có |
| `%S` | Session ID — **tránh ghi** vì rất nhạy cảm |

**Lưu ý riêng về thời gian:** `%D` của Tomcat là **microseconds**; một giá trị `2500` tương đương khoảng **2,5 ms**, không phải 2500 ms. Nếu đưa vào dashboard cùng app log tính milliseconds, phải chuẩn hóa đơn vị. Đối với Undertow, tài liệu Boot nêu yêu cầu bật recording request start time khi muốn timing `%D`; các server không có cùng semantics ở mọi token.

Với pattern minh họa, một dòng có thể **trông giống**:

```text
[08/Nov/2026:09:10:11 +0700] 127.0.0.1 GET /api/items/42 200 25 4200 79a0b899-1a46-44bf-9dbe-60fe630d3083
```

Đây là **dòng minh họa định dạng**, không phải output thực tế của demo và không dùng làm assertion exact. Timestamp, byte count, duration, response field ordering và ID đều phụ thuộc request thật.

### 4.3. Vì sao không bật common/combined pattern tùy tiện ở production?

Pattern `common` thường chứa `"%r"`; `combined` còn có `Referer` và `User-Agent`. Những trường này có thể mang:

- Query chứa `token=...`, `password=...`, email hoặc thông tin tìm kiếm cá nhân.
- Referer URL chứa mã reset password hoặc thông tin client.
- User-Agent/headers do client điều khiển, có thể gây log injection nếu collector/parser xử lý không chuẩn.
- URL path chứa số điện thoại, mã định danh hoặc tên tài liệu.
- IP address có thể là personal data theo chính sách pháp lý của tổ chức.
- Cookie/session ID, Authorization hoặc API key nếu ai đó tùy chỉnh pattern sai.

Do đó, **không mặc định log request body, Authorization, Cookie, Set-Cookie, `%S`, raw query hoặc toàn bộ headers**. Pattern minh họa cố tình chọn `%m` + `%U` và không có `%q`/`%r` để giảm rủi ro query leak; **`%U` vẫn chứa path** và vẫn cần kiểm tra PII trong route/path design.

Nếu cần log một route chứa ID, application log có thể dùng **route template** như `/api/items/{id}` thay vì path chứa ID thật `/api/items/42`. Ở tầng Tomcat AccessLogValve thông thường, `%U` không biết Spring MVC route template; muốn làm việc tương tự ở access log phải dùng hạ tầng xử lý/normalization có kiểm soát hoặc hạn chế lưu raw path.

## 5. Application logs: SLF4J, Logback và MDC

Spring Boot thường dùng **SLF4J facade** với Logback mặc định qua các starter. Trong service/controller:

```java
private static final Logger log = LoggerFactory.getLogger(ItemService.class);

log.info("item.lookup result={} type={}", "found", "demo");
log.warn("inventory.lookup upstreamStatus={}", 503);
log.error("item.lookup failed", exception);
```

Đây là **snippet**, cần import `org.slf4j.Logger`, `LoggerFactory`, lớp `ItemService` và biến `exception` hợp lệ. Dạng có `{}` là **parameterized logging**, giúp không phải tự nối string và có thể tránh xây chuỗi khi log level không bật (với các API/phần việc phù hợp). Nó **không tự làm sạch dữ liệu cá nhân, escape log injection hoặc redaction**. Chỉ truyền giá trị đã chọn lọc cho log.

Các mức log thường dùng:

- **ERROR:** lỗi nghiêm trọng ảnh hưởng request/job, không chỉ vì mọi HTTP 4xx.
- **WARN:** hành vi bất thường/giảm chất lượng, retry, trạng thái cần chú ý; tránh log trùng một lỗi ở mọi tầng.
- **INFO:** vòng đời ứng dụng, sự kiện nghiệp vụ quan trọng, request-summary khi có policy; lưu lượng cao nên có sampling/quota.
- **DEBUG:** chi tiết chẩn đoán theo package, chỉ bật có thời hạn khi được phép.
- **TRACE:** chi tiết sâu; dễ rất lớn và lộ dữ liệu, chỉ bật có kiểm soát.

### 5.1. Mapped Diagnostic Context (MDC)

`MDC` của SLF4J giúp gắn các key-value vào **context của thread đang log**:

```java
MDC.put("requestId", "some-id");

try {
    log.info("processing stage=verify");
} finally {
    MDC.remove("requestId");
}
```

Cần import `org.slf4j.MDC` và một `log` đã khởi tạo. Logback pattern có thể in MDC:

```properties
logging.pattern.console=%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [%thread] req=%X{requestId:-none} %logger{36} - %msg%n
```

Khi đang xử lý request có MDC `requestId`, log có thể chứa:

```text
2026-11-08T09:10:11.123+07:00 INFO  [http-nio-8080-exec-2] req=79a0b899-1a46-44bf-9dbe-60fe630d3083 c.example.demo.ItemController - item.lookup outcome=found
```

Đây chỉ là **ví dụ trình bày**, không phải output cố định; UUID, thread name, timing và class logging thay đổi.

**MDC không phải session storage.** Nó không lưu state của HTTP session, không xác thực user và không tự truyền qua các thread. Nếu thread trong pool phục vụ request A rồi B, quên `MDC.remove` có thể làm **request B mang nhầm ID của A**. Với xử lý async/reactive/virtual threads, propagation cần cơ chế riêng; không giả định ThreadLocal tự chuyển đúng ngữ cảnh.

### 5.2. Request ID, correlation ID và trace ID không đồng nghĩa

| Trường | Ý nghĩa | Ví dụ sử dụng |
| --- | --- | --- |
| `requestId` | ID cho **một HTTP request cụ thể** ở app/gateway | Nối Tomcat access line với app log cùng request |
| `correlationId` | ID nối một nhóm tác vụ/request liên quan theo quy ước | Một business workflow qua nhiều services |
| `traceId` | ID cho một distributed trace theo tracing stack | Nối spans trong OpenTelemetry/Micrometer |
| `spanId` | ID của một đoạn công việc/span thuộc trace | Điều tra dependency/latency trong từng service |
| `sessionId` | Credential/identifier của phiên HTTP | **Không dùng làm public correlation ID** |

Trong Spring Boot với **Micrometer Tracing**, trace/span IDs có thể được tự đưa vào log correlation theo framework. Nếu hệ thống đã có W3C `traceparent` và OpenTelemetry, nên tận dụng tracing đã chuẩn hóa; không tự tạo một cơ chế song song làm rối correlation. Đừng thay request ID bằng session ID, token hay email người dùng.

**Đầu vào không tin cậy:** `X-Request-Id` từ Internet là dữ liệu client có thể giả mạo. Với môi trường doanh nghiệp có trusted gateway, có thể chọn một chính sách: edge kiểm tra length/charset rồi phát ID mới hoặc propagate một ID đã được xác nhận. Không nhận một giá trị dài vô hạn, có CR/LF hoặc chứa PII rồi ghi nguyên vào MDC/log; có nguy cơ log injection và index/cardinality explosion.

Bài thực hành sẽ **luôn sinh UUID ở server** và ghi response header `X-Request-Id`. Khi đi qua gateway thực tế, cần thống nhất nơi nào là owner của ID để tránh proxy và app sinh hai ID không liên hệ được.

## 6. Ví dụ chạy được: Spring Boot + Tomcat access log + application filter

**Bối cảnh:** chúng ta tạo một app có `GET /api/items/{id}`. Tomcat ghi access log, một filter tạo request ID và log summary, controller ghi một business event nhỏ. Không log body, raw query, cookie, token hay tên khách hàng.

Ví dụ cố định **Spring Boot 3.5.16 + Java 17** để API/import tái lập được, với embedded Tomcat mặc định. **Spring Boot 3.5.16 là bản cuối của dòng 3.5.x được OSS hỗ trợ**; đối với production mới nên dùng dòng Spring Boot còn được OSS hỗ trợ cùng bản vá hiện hành (ví dụ 4.0/4.1 theo lịch phát hành), đồng thời đối chiếu lại starter/test APIs. Ví dụ dùng 3.5.16 cho mục đích thực hành, không khuyến khích triển khai sản phẩm trên bản đã hết hỗ trợ.

### 6.1. Cấu trúc dự án

```text
http-logs-demo/
├─ pom.xml
└─ src/
   ├─ main/
   │  ├─ java/com/example/demo/
   │  │  ├─ HttpLogsApplication.java
   │  │  ├─ RequestIdLoggingFilter.java
   │  │  └─ ItemController.java
   │  └─ resources/
   │     └─ application.properties
   └─ test/
      └─ java/com/example/demo/
         └─ HttpLogsApplicationTest.java
```

### 6.2. File Maven

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>http-logs-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-web` cung cấp Spring MVC/Tomcat và logging mặc định phù hợp; `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ và test infrastructure. Không phải thêm một dependency logging khác chỉ để có SLF4J/Logback.

### 6.3. Properties đầy đủ

**`src/main/resources/application.properties`**

```properties
spring.application.name=http-logs-demo
server.port=8080

# Embedded Tomcat access log (demo local).
server.tomcat.basedir=./tomcat-demo
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.directory=logs
server.tomcat.accesslog.prefix=access
server.tomcat.accesslog.suffix=.log
server.tomcat.accesslog.rotate=true
server.tomcat.accesslog.max-days=7
server.tomcat.accesslog.buffered=false
server.tomcat.accesslog.pattern=%t %a %m %U %s %b %D %{X-Request-Id}o

# Console application logs: hiển thị MDC requestId, không in raw request.
logging.pattern.console=%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [%thread] req=%X{requestId:-none} %logger{36} - %msg%n

logging.level.root=INFO
logging.level.com.example.demo=INFO
```

Các lưu ý:

- Để kiểm chứng ví dụ, **tạo project trong thư mục writable**. Tomcat tạo thư mục `tomcat-demo/logs` theo runtime; không tự tin path này hợp lệ khi chạy container chỉ cho phép filesystem read-only.
- Khi access log chưa thấy ngay, đảm bảo app thật sự dùng **embedded Tomcat**, property đang active và ứng dụng đã nhận request. Với `buffered=false`, độ trễ flush thường nhỏ hơn, nhưng việc hiển thị file qua IDE/antivirus/collector vẫn có độ trễ riêng.
- Log application ra **console**; log access ra **file**. Đó là hai kênh khác nhau trong demo. Trên Kubernetes, phải quyết định thu thập file qua volume/sidecar hay đưa access log vào logging pipeline của nền tảng; đừng mặc nhiên collector stdout sẽ đọc file access.
- Nếu thay `logging.pattern.console` bằng structured JSON ở phần sau, chỉ giữ một định dạng output cho pipeline đích, tránh đồng thời cấu hình hai encoder mâu thuẫn.
- `server.tomcat.accesslog.max-days` điều khiển retention ở Tomcat theo semantics phiên bản; SIEM/log store có thể có retention riêng.
- IP từ `%a` là remote address dưới góc nhìn Tomcat; khi sau proxy không nhất thiết là IP browser thật, và là dữ liệu có thể nhạy cảm.

### 6.4. Main class

**`src/main/java/com/example/demo/HttpLogsApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpLogsApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpLogsApplication.class, args);
    }
}
```

### 6.5. Filter tạo requestId, gắn response header và MDC

**`src/main/java/com/example/demo/RequestIdLoggingFilter.java`**

```java
package com.example.demo;

import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
public class RequestIdLoggingFilter extends OncePerRequestFilter {

    private static final Logger log =
        LoggerFactory.getLogger(RequestIdLoggingFilter.class);

    private static final String REQUEST_ID_KEY = "demo.requestId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // Không tin trực tiếp X-Request-Id do client cung cấp.
        String requestId = UUID.randomUUID().toString();
        long startNanos = System.nanoTime();

        request.setAttribute(REQUEST_ID_KEY, requestId);
        response.setHeader("X-Request-Id", requestId);

        // Đây là MDC cho thread đang thực thi filter.
        String previous = MDC.get("requestId");
        MDC.put("requestId", requestId);

        boolean threw = false;
        try {
            chain.doFilter(request, response);
        } catch (IOException | ServletException | RuntimeException | Error ex) {
            threw = true;
            throw ex;
        } finally {
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startNanos
            );

            Object pattern = request.getAttribute(
                HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE
            );
            String route = pattern instanceof String
                ? (String) pattern
                : "unmatched";

            // Đây là lúc chain trả về filter, không cam kết là
            // final status/tổng thời gian của async hoặc error dispatch.
            log.info(
                "http.filter.exit method={} route={} " +
                "statusAtExit={} durationMs={} asyncStarted={} threw={}",
                request.getMethod(),
                route,
                response.getStatus(),
                elapsedMs,
                request.isAsyncStarted(),
                threw
            );

            if (previous == null) {
                MDC.remove("requestId");
            } else {
                MDC.put("requestId", previous);
            }
        }
    }
}
```

**Tại sao thiết kế như trên?**

1. `UUID.randomUUID()` tạo một ID mới cho mỗi request đi qua filter. Request ID **không phải security credential** và không thay thế `traceId`/`spanId`, authentication hay session ID.
2. `request.setAttribute(...)` cho phép các thành phần cùng request đọc ID nếu cần. Response header `X-Request-Id` giúp client cung cấp ID khi báo lỗi, và Tomcat pattern `%{X-Request-Id}o` có thể ghi cùng giá trị.
3. **Không nhận raw inbound `X-Request-Id` từ Internet**: nếu muốn propagate, phải có trusted gateway policy, kiểm tra charset/length và phân biệt định danh từ edge với ID local.
4. `MDC.put` giúp các lệnh `log.info(...)` chạy trên **cùng thread** mang request ID. `finally` khôi phục MDC trước đó hoặc xóa ID để tránh leak sang request kế tiếp trong worker thread pool.
5. `System.nanoTime()` phù hợp đo thời lượng trôi qua, không dùng `System.currentTimeMillis()` để trừ duration vì wall clock có thể thay đổi.
6. `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` cho biết route template sau Spring MVC mapping, ví dụ `/api/items/{id}` thay vì raw path `/api/items/42`. Với request bị chặn trước DispatcherServlet hoặc route không match, attribute có thể không tồn tại → log `unmatched`.
7. `statusAtExit` được đặt tên có chủ đích: nó là **status lúc filter kết thúc**, không chắc là response status cuối cùng nếu xảy ra async/error dispatch hoặc container tự xử lý exception sau đó.
8. `threw=true` cho biết filter chain thoát vì một exception được ném ra ngoài; không có nghĩa status cuối là 500. Có thể một `ResponseStatusException` được Spring MVC resolve và không thoát ra filter, khi đó `threw=false` dù response 4xx.
9. Không log raw URL query, request/response body, headers, principal name, cookie hay token. Thông tin định danh cá nhân cần policy/giảm thiểu khác.
10. Filter này được `@Component` đăng ký tự động trong Spring Boot Servlet app. Khi có Spring Security, thứ tự filter registration mới quyết định filter có nhìn thấy request bị security từ chối hay không; đừng mặc định mọi request tới container đều đi qua filter này.

**Giới hạn có chủ đích:** ví dụ này dành cho xử lý **đồng bộ**. Một request async có thể khiến `chain.doFilter` trả về trước khi body được gửi xong; do đó `durationMs` ở đây là **thời gian tới lúc filter chain thoát**, không phải toàn bộ response duration. Với `Callable`, `DeferredResult`, `StreamingResponseBody` và SSE, phải thiết kế một completion logger dùng Servlet `AsyncListener` / observability instrumentation đúng lifecycle. Khi exception chưa được Spring resolve và xảy ra error dispatch, `response.getStatus()` tại `finally` có thể chưa phản ánh final 500. **Tomcat access log** phù hợp hơn cho total container time, dù cũng cần xem semantics async và disconnect.

### 6.6. Controller có business event an toàn

**`src/main/java/com/example/demo/ItemController.java`**

```java
package com.example.demo;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ItemController {

    private static final Logger log =
        LoggerFactory.getLogger(ItemController.class);

    @GetMapping("/api/items/{id}")
    public Map<String, Object> item(@PathVariable long id) {
        if (id != 42) {
            log.info("item.lookup outcome=not_found");
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Item not found"
            );
        }

        log.info("item.lookup outcome=found");
        return Map.of("id", id, "status", "available");
    }

    @GetMapping("/api/conflict")
    public void conflict() {
        log.warn("demo.conflict outcome=rejected");
        throw new ResponseStatusException(
            HttpStatus.CONFLICT, "Conflict for demo"
        );
    }

    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }
}
```

Đây là dữ liệu demo, không phải database hoặc hệ thống tồn kho thật. Controller không log `id`; nếu business quyết định log object IDs, phải xác định liệu chúng có phải PII/secret, có thể pseudonymize được không và ai được quyền xem.

**Kết quả kỳ vọng theo từng URL:**

| URL | HTTP status | Nội dung chính | App log của controller |
| --- | --- | --- | --- |
| `GET /api/items/42` | 200 | JSON chứa `"id":42`, `"status":"available"` | `item.lookup outcome=found` |
| `GET /api/items/99` | 404 | Body lỗi theo cấu hình Spring MVC/Boot | `item.lookup outcome=not_found` |
| `GET /api/conflict` | 409 | Response lỗi theo Spring MVC | `demo.conflict outcome=rejected` |
| `GET /api/ping` | 200 | `pong` | Không có business event riêng, chỉ filter log |
| `GET /api/unknown` | 404 | Route chưa match | Không có log của controller; filter route `unmatched` |

Không hardcode exact JSON error body: Spring Boot mặc định có thể chọn cấu trúc lỗi theo `Accept`, error settings và version. Các status trên là contract quan trọng để kiểm thử.

## 7. Chạy và đối chiếu hai loại log

### 7.1. Khởi động

Trong thư mục có `pom.xml`, JDK 17+ và Maven:

```bash
java -version
mvn spring-boot:run
```

Nếu dự án có Maven Wrapper:

```bash
./mvnw spring-boot:run
```

Windows PowerShell/cmd có thể dùng `mvnw.cmd spring-boot:run`. Đảm bảo port 8080 còn trống và working directory có quyền ghi `./tomcat-demo/logs`.

### 7.2. Tạo một request và đọc response header

```bash
curl -i http://localhost:8080/api/items/42
```

Kỳ vọng response có **status 200** và một header dạng:

```http
X-Request-Id: 79a0b899-1a46-44bf-9dbe-60fe630d3083
```

ID trên **chỉ minh họa định dạng UUID**, mỗi request thật sẽ có giá trị khác. Browser có thể đọc header này trong same-origin response; cross-origin frontend cần CORS `Access-Control-Expose-Headers` nếu muốn JavaScript đọc custom response header ở đúng origin, theo chính sách CORS cụ thể.

Ở console application log, bạn thường thấy hai dòng cùng `req=...`:

```text
... INFO  req=79a0b899-... ItemController - item.lookup outcome=found
... INFO  req=79a0b899-... RequestIdLoggingFilter - http.filter.exit method=GET route=/api/items/{id} statusAtExit=200 durationMs=... asyncStarted=false threw=false
```

Đây là **minh họa hình dạng**, không phải stdout chính xác. Trong code, request ID đầy đủ được in bởi `logging.pattern.console` và lần gọi cụ thể có latency khác.

Tomcat access log dưới `./tomcat-demo/logs/` có thể có một dòng:

```text
[...timestamp...] 127.0.0.1 GET /api/items/42 200 25 4300 79a0b899-1a46-44bf-9dbe-60fe630d3083
```

Không so sánh `25` hay `4300` như hằng số. Byte count và microseconds phụ thuộc response thực tế; Tomcat access log và application log đều có **cùng response X-Request-Id** do filter tạo cho request được nó xử lý.

**Phân tích chênh lệch thời gian:** nếu Tomcat ghi `%D = 4300` microseconds thì tương đương **4,3 ms**; filter có thể ghi `durationMs=3` do điểm bắt đầu/kết thúc khác nhau và làm tròn milliseconds. Không xem chênh lệch nhỏ là lỗi.

### 7.3. Tạo các nhánh 404, 409 và 200

```bash
curl -i http://localhost:8080/api/items/99
curl -i http://localhost:8080/api/conflict
curl -i http://localhost:8080/api/ping
curl -i http://localhost:8080/api/unknown
```

Kỳ vọng:

- Tomcat access log có **4 bản ghi** cho bốn request tới container (nếu các request thực sự đến được Tomcat; có thể còn dòng cho favicon/health nếu browser gọi thêm).
- App filter có bản ghi `http.filter.exit` cho những request đi qua nó; route `unmatched` nếu không map.
- Controller chỉ ghi business event khi method tương ứng được gọi.
- 404 từ controller và 404 do thiếu route có thể cùng status, nhưng **route template, logger event và điều tra stack** khác.
- 409 được Spring MVC xử lý theo `ResponseStatusException`, không nhất thiết in stack trace ERROR trong console. Một ứng dụng có thể chủ ý trả 409 như lỗi nghiệp vụ.

### 7.4. Đọc file access log

Trên Linux/macOS:

```bash
ls -l ./tomcat-demo/logs
tail -n 20 ./tomcat-demo/logs/access*.log
```

Trên Windows PowerShell:

```powershell
Get-ChildItem -Path ".\tomcat-demo\logs" -Filter "access*.log"
Get-Content -Path ".\tomcat-demo\logs\access*.log" -Tail 20
```

Nếu không có file:

1. Kiểm tra đã cấu hình đúng Tomcat embedded hay ứng dụng đã thay bằng Jetty/Undertow.
2. Kiểm tra active Spring profile/config có ghi đè `server.tomcat.accesslog.enabled` không.
3. Kiểm tra working directory thực khi khởi động qua IDE/container/systemd.
4. Kiểm tra `basedir`, `directory`, quyền ghi disk, quota và rotation date suffix.
5. Gửi một HTTP request rồi xem lại; file log có thể chỉ xuất hiện sau request.
6. Không sửa bằng cách cấp quyền ghi toàn bộ filesystem hoặc chạy JVM root.

### 7.5. Vì sao không nên kiểm tra bằng một dòng log “cố định”?

Access log có timestamp, request IP, số byte, thời gian và ID biến thiên. Unit tests không nên assert cả chuỗi log như một golden string cứng. Thay vào đó:

- Kiểm tra **HTTP behavior** bằng request integration test.
- Kiểm tra response `X-Request-Id` hợp lệ và thay đổi giữa các requests.
- Trong một môi trường test cô lập, xác nhận file access log có method/path/status/id tương ứng (có thể cần đồng bộ flush/timeout); tránh phụ thuộc thứ tự liên quan các request song song.
- Nếu bắt buộc kiểm thử app log fields, dùng test appender hoặc log collector giả lập, không parse stdout đầy đủ gồm timestamp/thread name.
- Kiểm tra hệ thống log aggregation qua đúng pipeline production-like, vì config file local không chứng minh collector đọc được logs.

## 8. Kiểm thử HTTP thật bằng JDK HttpClient + SpringBootTest

Dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)` để mở **Tomcat thật**, không chỉ `MockMvc`. Test không cần tài khoản hay dịch vụ mạng ngoài, vì request gọi local random port.

**`src/test/java/com/example/demo/HttpLogsApplicationTest.java`**

```java
package com.example.demo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpLogsApplicationTest {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

    private final ObjectMapper json = new ObjectMapper();

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    private HttpResponse<String> get(String path) throws Exception {
        return client.send(
            HttpRequest.newBuilder(uri(path)).GET().build(),
            HttpResponse.BodyHandlers.ofString()
        );
    }

    private String requestId(HttpResponse<?> response) {
        String value = response.headers()
            .firstValue("X-Request-Id").orElseThrow();
        UUID.fromString(value);  // Fail nếu format không phải UUID.
        return value;
    }

    @Test
    void successHasServerGeneratedIdAndExpectedBody()
            throws Exception {
        HttpResponse<String> response = get("/api/items/42");

        assertEquals(200, response.statusCode());
        requestId(response);
        JsonNode body = json.readTree(response.body());
        assertEquals(42, body.get("id").asInt());
        assertEquals("available", body.get("status").asText());
    }

    @Test
    void missingItemHas404AndRequestId() throws Exception {
        HttpResponse<String> response = get("/api/items/99");

        assertEquals(404, response.statusCode());
        requestId(response);
    }

    @Test
    void conflictHas409AndRequestId() throws Exception {
        HttpResponse<String> response = get("/api/conflict");

        assertEquals(409, response.statusCode());
        requestId(response);
    }

    @Test
    void aNewRequestGetsANewId() throws Exception {
        String first = requestId(get("/api/ping"));
        String second = requestId(get("/api/ping"));

        assertNotEquals(first, second);
    }

    @Test
    void untrustedInboundRequestIdIsNotReflected()
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri("/api/ping"))
            .header("X-Request-Id", "client-tried-to-control-the-id")
            .GET()
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString()
        );

        assertEquals(200, response.statusCode());
        String serverId = requestId(response);
        assertNotEquals("client-tried-to-control-the-id", serverId);
    }

    @Test
    void unmatchedRouteStillGetsARequestId()
            throws Exception {
        HttpResponse<String> response = get("/api/unknown");

        assertEquals(404, response.statusCode());
        requestId(response);
    }
}
```

Chạy:

```bash
mvn test
```

Hoặc `./mvnw test` nếu có Maven Wrapper. Với project và cấu hình trong bài, **sáu test được kỳ vọng pass**. Đây là thiết kế test để người học thực thi, **không phải tuyên bố đã biên dịch/chạy test tại một repository cụ thể**.

**Test chứng minh gì?**

- Embedded Tomcat thực sự xử lý các HTTP requests.
- Response của các status 200/404/409 có `X-Request-Id` do filter tạo.
- Client gửi một `X-Request-Id` giả vẫn nhận ID mới từ server.
- Mỗi HTTP request mới có ID khác.
- Controller trả JSON với schema được chỉ định.

**Test chưa chứng minh gì?**

- Nó **chưa assert file Tomcat access log** hoặc JSON output của console, vì những điều ấy thuộc môi trường/filesystem/logger appender và có biến thiên timing/rotation. Hãy kiểm tra bằng lệnh ở phần 7 hoặc viết integration fixture với working-directory/tomcat-basedir riêng và test appender.
- Nó không chứng minh proxy đã forward/log correlation ID đúng, vì test chỉ gọi Tomcat trực tiếp.
- Nó không bao phủ Spring Security, Servlet async/error dispatch, streaming, WebFlux hoặc multi-replica aggregation.
- Nó không chứng minh log collector nhận được bản ghi khi host/container restart.

Nếu cần test file access log tự động, dùng **một temp directory riêng cho test context**, bật `server.tomcat.accesslog.buffered=false` trong test, gửi HTTP request, đợi một khoảng thời gian có giới hạn cho file xuất hiện/flush, sau đó tìm **ID cụ thể** thay vì giả định vị trí dòng hoặc timestamp. Đừng chạy test cùng một `basedir` cố định giữa các process Maven song song; Tomcat access log có thể bị conflict/rotate.

## 9. Ghi log cuối request khi ứng dụng xử lý bất đồng bộ hoặc streaming

Filter trong ví dụ chỉ đo tới lúc `chain.doFilter` trả lại. Với async, điều đó có thể **rất khác** thời gian client nhận xong response.

### 9.1. Ba kiểu xử lý có vòng đời khác nhau

| Kiểu | Ví dụ | Filter `finally` có phải completion? |
| --- | --- | --- |
| Đồng bộ MVC | Controller trả DTO/String, không async | Thường gần end của request dispatch; một số error flow vẫn khác |
| Servlet async | `Callable<T>`, `DeferredResult<T>` | **Không** nhất thiết; request có thể còn đang chạy |
| Streaming MVC | `StreamingResponseBody`, `SseEmitter` | **Không** nhất thiết; stream có thể sống lâu |
| WebFlux/Reactor | `Mono`/`Flux` trên Netty | Không dùng Servlet filter này; lifecycle theo reactive publisher |

Trong Spring MVC, `OncePerRequestFilter` có hai hook quan trọng:

```java
// Snippet minh họa, đặt trong subclass filter khi phù hợp.
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return false;
}

@Override
protected boolean shouldNotFilterErrorDispatch() {
    return false;
}
```

Mặc định các hook trên trả `true` trong Spring Framework, tức filter **không tự lặp lại ở các async/error dispatches** theo cách ứng dụng chưa cấu hình. Tuy nhiên, đổi thành `false` **không tự tạo một “log exactly once khi response hoàn tất”**. Nó chỉ làm filter có thể chạy ở các dispatches tương ứng; nếu dùng chung code ở trên, bạn có thể sinh nhiều request IDs và nhiều log summaries cho một request.

### 9.2. Thiết kế completion logger cho async

Nếu muốn một event **request.completed** sau khi Servlet async thực sự kết thúc, hướng thiết kế:

1. Ở **dispatch đầu tiên**, tạo một state object gắn vào request attribute gồm `requestId`, `startNanos` và cờ `AtomicBoolean logged`.
2. Nếu `request.isAsyncStarted()` ở filter return, đăng ký `AsyncListener` trên `request.getAsyncContext()`. Dùng `onComplete` để ghi summary **một lần** bằng `logged.compareAndSet(false,true)`.
3. Dùng `onError` và `onTimeout` để ghi nhận failure/timeout, nhưng chú ý status chưa chắc final ở thời điểm callback; có thể cần state riêng và log completion khi đóng request.
4. Nếu có `onStartAsync` tạo cycle mới, listener phải được đăng ký lại theo servlet API lifecycle của ứng dụng.
5. Với sync request, log khi filter chain thực sự kết thúc; với async, không log completion sớm.
6. Trong callback ở thread khác, **tái thiết lập requestId/trace context cho đoạn logging** rồi cleanup bằng `finally`; không giả định MDC đi theo.
7. Xử lý error dispatch và client disconnect, tránh double-log khi nhiều đường hoàn tất xảy ra cùng lúc.
8. Ghi method/route template/status/bytes theo những gì có thể xác định đúng, tránh gọi response là “200 completed” khi stream đã đứt sau khi commit.
9. Test `Callable`, `DeferredResult`, SSE, client disconnect và timeout với embedded container thật, không chỉ một MockMvc GET sync.
10. Với hệ thống production phức tạp, cân nhắc **Micrometer Observation/Tracing** hoặc instrumentation do gateway/server cung cấp thay vì tự viết một filter lớn khó kiểm chứng.

**Không copy `AsyncListener` rời rạc** mà bỏ qua lifecycle dispatch/error: một implementation thiếu `onStartAsync` hoặc log trong cả `onError` và `onComplete` có thể tạo logs trùng/không đúng timing.

### 9.3. MDC và xử lý đa luồng

Một request có thể có:

```text
HTTP thread A -> filter MDC=requestId=R
    |
    +-> @Async executor thread B -> mặc định không có MDC R
    |
    +-> callback DeferredResult thread C
    |
    +-> Servlet async dispatch thread D
```

`MDC` theo thread nên log trong B/C/D có thể thiếu request ID, hoặc bị giữ sai nếu context tự copy nhưng không cleanup. Nếu muốn propagation:

- Dùng context-propagation/tracing infrastructure được Spring/Micrometer hỗ trợ theo stack; kiểm tra cấu hình `TaskDecorator` hoặc framework context propagation.
- Không truyền một mutable `MDC.getCopyOfContextMap()` cho nhiều task không đồng bộ rồi quên restore/clear.
- Tránh dùng `InheritableThreadLocal` như giải pháp vạn năng cho thread pools.
- Với Reactor/WebFlux, ưu tiên Reactor Context + Micrometer context propagation. Không dùng `HttpServletRequest`/`OncePerRequestFilter` cho Netty WebFlux.
- Với virtual threads (Java 21+), ThreadLocal có semantics khác hiệu năng nhưng **thread không phải session, không tự là distributed trace**.

**Kết luận cho async:** đơn vị thời gian mà một filter đo **không nhất thiết trùng** toàn bộ thời gian mà access log/container hay người dùng quan sát.

## 10. Structured JSON logging trong Spring Boot

Console text dễ đọc khi phát triển; production logging pipeline thường thích **một JSON object cho một event**. Spring Boot 3.5 hỗ trợ structured logging sẵn cho **ECS, GELF, Logstash** (tùy cấu hình/version). Ví dụ một cấu hình **thay thế** cho `logging.pattern.console`:

```properties
# DÙNG NHƯ PHƯƠNG ÁN THAY THẾ, KHÔNG GIỮ ĐỒNG THỜI
# logging.pattern.console ở phần 6.
logging.structured.format.console=ecs
```

Trong ECS output, log event có trường timestamp, level, logger, message, service và các MDC keys theo cơ chế Spring Boot. Với MDC `requestId`, trường này có thể được đưa vào structured log:

```json
{
  "@timestamp": "2026-11-08T09:10:11.123+07:00",
  "log": { "level": "INFO", "logger": "com.example.demo.RequestIdLoggingFilter" },
  "service": { "name": "http-logs-demo" },
  "message": "http.filter.exit method=GET route=/api/items/{id} statusAtExit=200 durationMs=3 asyncStarted=false threw=false",
  "requestId": "79a0b899-1a46-44bf-9dbe-60fe630d3083"
}
```

Đây là **JSON minh họa** các trường hữu ích, không phải schema/line output được bảo đảm hoàn toàn. ECS serializer thực có thể đặt trường level/logger ở cấu trúc riêng, thêm `process`/`ecs.version` và các metadata khác. **Không kiểm thử bằng cách so sánh nguyên mẫu JSON này với output từng byte**.

Ưu điểm JSON:

- Collector parse field rõ, không phụ thuộc regex cố nhận biết vị trí thread/timestamp.
- Query `requestId`, `traceId`, `route`, `status` và error type nhanh.
- Có thể gắn service name, env, deployment version, pod/host mà không phải viết thêm vào mỗi message.
- Có thể định nghĩa schema và dashboards chung; so sánh p95 latency theo route template.

Nhược điểm và trách nhiệm:

- JSON **không tự redaction** token/PII.
- MDC không được đưa vào mọi formatter/collector nếu cấu hình sai; phải thử end-to-end.
- Nếu ghi toàn bộ request headers/body làm JSON, kích thước và nguy cơ rò dữ liệu vẫn rất lớn.
- Log field do client kiểm soát có thể tạo **high cardinality**, injection hoặc index overload.
- Chuyển format từ text sang JSON có thể phá parser hiện tại; rollout với consumer agreement và versioning.

### 10.1. SLF4J fluent key-value logging

Trong SLF4J 2, bạn có thể chọn structured fields tách khỏi text message:

```java
log.atInfo()
   .addKeyValue("route", "/api/items/{id}")
   .addKeyValue("status", 200)
   .addKeyValue("result", "found")
   .log("http.request");
```

Đây là snippet trong class có `log`. Formatter của Spring Boot structured logging có thể đưa fields này vào JSON. Nếu dùng console pattern thông thường, cách hiển thị key-values phụ thuộc Logback layout; không giả định lúc nào cũng có property JSON sẵn.

**Không dùng ID người dùng hoặc raw URI làm tên field/key**. Hãy chọn một schema cố định, cardinality hợp lý.

## 11. Micrometer Observation, distributed tracing và correlation ID

Khi hệ thống gồm nhiều service:

```text
Client -> API Gateway -> Service A -> Service B -> Database
            |               |           |
         access log       app logs    app logs
            |               |           |
           trace ID xuyên suốt + span IDs riêng
```

Một request ID được sinh tại Service A **chỉ** giúp nối log trong Service A/Tomcat của nó. Muốn theo dõi cả distributed call chain, dùng OpenTelemetry/Micrometer Tracing và một **trace context chuẩn** như W3C `traceparent`, có propagation qua HTTP clients.

Spring Boot Actuator/observability có instrumentation cho HTTP server/client, nhưng bạn phải cấu hình dependencies/exporter/sampling phù hợp. Đừng khẳng định cứ thêm `spring-boot-starter-actuator` là có trace exporter đầy đủ.

Trong Spring Boot khi **Micrometer Tracing** được cấu hình, log correlation ID mặc định dựa trên MDC `traceId` và `spanId`. Có thể điều chỉnh bằng `logging.pattern.correlation` nếu cần. Một service còn có thể phát `X-Request-Id` theo contract gateway; hãy xác định rõ:

- ID nào theo **một incoming HTTP request**?
- ID nào theo **toàn distributed trace**?
- ID nào do **gateway tin cậy cấp**?
- Có được phép gửi ID cho client/partner hay không?
- Gateway có strip/untrusted normalization đối với trace context và request ID không?
- Khi sampling tắt một trace, application logs vẫn lưu ID nào để hỗ trợ điều tra?
- Khi HTTP client retry hoặc fan-out, mỗi outbound HTTP exchange có span ID riêng hay request ID nào?

**Chỉ dựa vào log text và ThreadLocal MDC sẽ không tạo ra distributed trace hoàn chỉnh.** Dùng span events, metrics và trace exporters theo chính sách dữ liệu, bảo mật token và sampling.

### 11.1. Correlate access log với app log

Ví dụ truy vết:

1. Khách hàng đưa `X-Request-Id` nhận trong response: `79a0...`.
2. Tìm Tomcat access log dòng có ID này, xem `GET /api/items/42`, `status=200` và `%D`.
3. Tìm console/structured logs cùng `requestId` để xem `http.filter.exit` và `item.lookup outcome=found`.
4. Nếu app log có `traceId`, mở trace để xem các HTTP/db spans.
5. Nếu request không thấy trong Tomcat, tìm edge/gateway access logs theo ID hoặc time window/user-safe metadata.
6. Nếu proxy có status khác, đối chiếu upstream status, retry, timeouts, circuit breaker hoặc client disconnect.
7. Nếu vẫn thiếu log, xác định log collector/backpressure/sampling/retention và version/instance đang dùng.

Không sử dụng session ID hoặc raw bearer token để nối logs. Những giá trị đó là bí mật và có thể bị tái sử dụng để tấn công.

## 12. Phân tích thời gian: vì sao hai log có duration khác nhau?

Giả sử request đi qua proxy:

```text
Client TCP/TLS -> Edge queue -> Proxy to upstream
                      |
                      v
                Tomcat request
                      |
                Filter begins
                      |
                Controller -> DB
                      |
                Filter exits (durationMs tại app)
                      |
                Tomcat completes (Tomcat %D)
                      |
                Proxy sends bytes (proxy request_time)
                      |
                Client receives final byte
```

Có thể xảy ra:

- **Filter duration = 15 ms**, **Tomcat %D = 17000 µs (~17 ms)**, **proxy time = 25 ms**: hợp lý vì phạm vi đo khác nhau và có thêm network/queue/serialization.
- **App log = 2 ms**, **Tomcat = 6 s**: có thể stream/async body còn chạy sau filter exit, client chậm, blocking output, compression hoặc container overhead.
- **Proxy = 10 s**, **Tomcat = 20 ms**: có thể upstream connect queue, client download chậm, proxy buffering, retries hoặc proxy timeout; phải nhìn đúng các fields proxy.
- **Tomcat 499?** 499 thường là mã **Nginx-specific** cho client closed request; Tomcat không nhất thiết dùng 499. Không đồng nhất mã proxy với HTTP status do Spring controller trả.
- **HTTP 200 nhưng client báo tải hỏng**: server đã commit 200 rồi stream lỗi giữa chừng; inspect bytes sent, connection status, exception/cancellation và client-side metrics.

Không chỉ dựa vào trung bình duration; đo **p95/p99 theo route**. Tuy nhiên log không thay thế **histogram metrics**: thống kê latency từ full access logs có thể tốn lưu trữ và bias do sampling/retention. Metrics thích hợp với SLO, trace/log thích hợp chẩn đoán nguyên nhân.

### 12.1. HTTP/2, keep-alive và virtual threads

HTTP/1.1 keep-alive và HTTP/2 multiplexing cho phép nhiều request trên một kết nối. **Connection ID không phải request ID**, IP/client port không đủ phân biệt request, và Thread name không ổn định đại diện một user. Trong Java 21 virtual threads, mỗi request có thể có thread ngắn hạn, càng không nên dùng thread name để liên kết nghiệp vụ qua requests.

## 13. Proxy, forwarded headers và IP đúng

Sau reverse proxy, `request.getRemoteAddr()` hoặc Tomcat `%a` có thể là IP của Nginx/gateway. Các header:

```http
Forwarded: for=203.0.113.10;proto=https;host=api.example.com
X-Forwarded-For: 203.0.113.10
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.com
```

chỉ đáng tin nếu **proxy được phép** đã strip/ghi đè giá trị client gửi, network chặn direct access vào backend và Spring/Container được cấu hình đúng.

Với Spring Boot, các lựa chọn:

```properties
# Chỉ bật khi có trusted proxy và policy kiểm tra header.
server.forward-headers-strategy=framework
```

Hoặc `native` tùy Tomcat/Undertow/Jetty, với trust proxy IP/network đúng. **Không** bật `framework` để nhận `X-Forwarded-For` tùy ý từ Internet rồi quyết định rate limit, location-based access hay audit identity. Tomcat access log có cấu hình riêng liên quan request attributes/RemoteIpValve; nếu cần log client IP thật, phải xem cả cách access log ghi attributes sau xử lý forwarded metadata. Không giả định bật một property sẽ làm mọi access log, security principal và edge IP giống nhau.

**Khuyến nghị:** trong logs, phân biệt `peerIp` (IP của hop đang kết nối trực tiếp) và `clientIp` (đã xác thực qua trust chain). Đặt retention/redaction cho IP theo chính sách bảo vệ dữ liệu. Đừng log toàn bộ `X-Forwarded-For` chuỗi dài chưa chuẩn hóa vì có thể bị spoof/injection.

### 13.1. Edge request ID và application request ID

Nếu ingress đã cấp `X-Request-Id`, ví dụ:

```text
Client -> Edge [requestId=EDGE-1]
              -> Spring [requestId=APP-9]
```

thì hai bản ghi không thể tự động join bằng một key duy nhất. Ba cách triển khai:

1. **Dùng ID của edge nhưng phải verify/normalize ở trust boundary** (edge strip incoming, đặt ID mới, app tin only trusted hop).
2. **Dùng hai field có tên khác nhau**: `edgeRequestId` và `appRequestId`; app có thể phát cả hai qua headers/tracing khi được phép.
3. **Dùng distributed trace**: `traceId` xuyên services, `spanId` theo mỗi hop, request ID địa phương để điều tra bên trong process.

Bài demo chọn cách đơn giản: **app sinh UUID** để join Tomcat và app logs. Điều này chỉ đảm bảo correlation **bên trong app**; production phải thống nhất policy với gateway để join từ edge.

## 14. Dữ liệu nhạy cảm và nguy cơ log injection

### 14.1. Những giá trị không nên ghi nguyên vào log

- `Authorization: Bearer ...`, Basic credentials, API keys.
- `Cookie`, `Set-Cookie`, `JSESSIONID` và session identifiers.
- Raw request/response body chứa password, OTP, thẻ thanh toán, địa chỉ, hồ sơ sức khỏe hoặc PII.
- Reset password URLs, magic links, OAuth `code`/`state`, query token.
- Full request line `%r`, raw query `%q`, Referer và User-Agent khi chưa có policy.
- HTTP client/dependency headers có chứa secrets hoặc nội dung nhiều tenant.
- Stack trace chứa URL/token trong exception message do thư viện bên ngoài tạo.
- Giá trị dynamic user input không được kiểm tra, đặc biệt chuỗi có CR/LF, control characters hoặc Unicode khó phân tích.

Không khẳng định rằng “có JSON logger” đồng nghĩa mọi trường đã được sanitize. Dữ liệu vẫn có thể bị rò qua collector, dashboards, retention, export và backup.

### 14.2. Khi cần thêm user/tenant ID để điều tra

Nếu thật sự cần field danh tính:

- Chỉ ghi **ID nội bộ đã được xác thực** hoặc giá trị đã pseudonymize (nếu policy yêu cầu), không nhận `?user=...` từ client.
- Không ghi password, cookie, token.
- Tránh cho ID vào **metric labels** có cardinality cao; logs và metrics có chiến lược khác.
- Có cơ chế phân quyền người xem logs, mã hóa vận chuyển/lưu trữ, retention và xóa theo chính sách.
- Nếu cần phân tích công khai, aggregate/anonymize; log storage vẫn là hệ thống chứa dữ liệu nhạy cảm.
- Khi security event quan trọng, tạo **audit record có integrity/retention riêng**, không dựa hoàn toàn vào access log dạng text.

### 14.3. Log injection

Client có thể gửi một tham số có newline hoặc control characters. Nếu code làm:

```java
// ANTI-PATTERN — không dùng trong production:
log.info("User said: " + request.getParameter("message"));
```

một số downstream parser có thể bị đánh lừa thành nhiều dòng hay trường giả. Parameterized logging `{}` **không tự ngăn** dữ liệu chứa newline/các ký tự gây log forging. Hãy chọn lọc fields, giới hạn length, encode/escape hoặc loại bỏ các ký tự điều khiển, và dùng structured logger phù hợp. Không tự ghép URL/headers/body vào log theo mặc định.

### 14.4. Logging body gây ảnh hưởng performance và bảo mật

`CommonsRequestLoggingFilter` và `ContentCachingRequestWrapper` của Spring có thể giúp quan sát một phần payload trong môi trường chẩn đoán, nhưng cần hiểu:

- Caching wrapper chỉ giữ **những byte đã được đọc**, không nhất thiết là toàn body ngay khi filter bắt đầu.
- Ghi payload có thể lộ mật khẩu/file upload/PII.
- Thao tác buffering/tee stream sai có thể làm request body không còn đọc được ở controller hoặc tăng memory nhiều lần.
- Response streaming/SSE có thể bị chậm nếu filter buffer body chỉ để log.
- Một request có thể rất lớn hoặc không kết thúc nhanh; log toàn bộ body tạo rủi ro DoS và chi phí lưu trữ.
- Debugging production nên ưu tiên **metadata an toàn**, tracing spans và sampling theo chính sách, không bật dump payload toàn app.

Nếu có quy định phải chụp body phục vụ điều tra, cần allowlist route/field, size limit, redaction, thời hạn bật, quyền duyệt, kiểm thử trên dữ liệu giả và cleanup sau incident.

## 15. Log và exception: tránh đếm đôi lỗi 4xx/5xx

Giả sử `GET /api/items/99` là item không tồn tại theo nghiệp vụ. Nó trả 404, nhưng nếu mọi 404 đều được log ERROR và có stack trace, dashboard có thể báo hệ thống “lỗi nghiêm trọng” mặc dù người dùng nhập ID không có thật.

Thiết kế thường hữu ích:

| Tình huống | HTTP status | App log level thường hợp lý | Metrics/SLO |
| --- | --- | --- | --- |
| GET thành công | 200 | Có thể INFO summary hoặc sample | Counting + latency |
| Validation sai | 400 | INFO/DEBUG, không log raw input nhạy cảm | 4xx rate |
| Anonymous cần auth | 401 | INFO/WARN tùy cảnh báo security | Auth reject rate |
| Không đủ quyền | 403 | WARN/INFO + security audit theo policy | Security denials |
| Không tồn tại | 404 | INFO/DEBUG nếu expected; WARN khi bất thường | 4xx route distribution |
| Conflict nghiệp vụ | 409 | INFO/WARN theo domain | Conflict rate |
| Rate limited | 429 | INFO/WARN, correlation | Rate limit metrics |
| Dependency lỗi | 502/503/504 | WARN/ERROR tùy ảnh hưởng | Dependency SLO |
| Unhandled server error | 500 | ERROR ở **một điểm** có context đáng tin | 5xx error budget |

**Tránh log trùng một exception ở controller, service, filter và global handler** như bốn ERROR stack traces, dù chỉ một request thất bại. Chọn một owner của error log; những tầng khác ghi thông tin bổ sung nếu cần nhưng không lập lại full stack trace.

Ở application filter mẫu, `threw` chỉ cho biết exception thoát filter chain, không phải loại lỗi; không in exception message vào request summary. Cần xử lý exception tại `@ControllerAdvice`/error handling với schema, redaction và exception classification phù hợp.

## 16. Access log của Jetty, Undertow và WebFlux khác gì?

### 16.1. Undertow

Spring Boot hỗ trợ nhóm properties riêng:

```properties
# Chỉ dùng khi runtime thật sự sử dụng Undertow.
server.undertow.accesslog.enabled=true
server.undertow.accesslog.pattern=%t %a %r %s (%D milliseconds)
server.undertow.options.server.record-request-start-time=true
```

Theo tài liệu Spring Boot, khi dùng Undertow `%D` để đo thời gian xử lý phải bật recording request start time. **Đơn vị không mặc định giống Tomcat**: ví dụ này ghi rõ milliseconds cho Undertow. Không copy Tomcat pattern/properties sang Undertow và mặc định kết quả giống hệt.

### 16.2. Jetty

Một cấu hình tham khảo:

```properties
# Chỉ dành cho ứng dụng đã thay Tomcat bằng Jetty.
server.jetty.accesslog.enabled=true
server.jetty.accesslog.filename=/var/log/jetty-access.log
```

Đường dẫn chỉ là ví dụ production-like, cần volume/permissions, không phải file chắc chắn tồn tại trên mọi máy. Jetty có API/pattern/rotation riêng; đối chiếu docs của version đang chạy.

### 16.3. Spring WebFlux / Reactor Netty

Nếu dùng `spring-boot-starter-webflux` trên Reactor Netty và không dùng Servlet engine, `server.tomcat.accesslog.*` **không** có ý nghĩa. Reactor Netty hỗ trợ access logs và các tùy chọn/instrumentation riêng, phụ thuộc version. Không dùng `jakarta.servlet.Filter` hoặc `OncePerRequestFilter` để “log mọi WebFlux request” trên Netty; dùng `WebFilter`, Reactor Context, observations/tracing và transport logging thích hợp.

**Cẩn thận `wiretap`:** Reactor Netty wiretap có thể log dữ liệu thấp tầng, headers/body và gây lộ secrets/ảnh hưởng performance. Nó không phải một access log an toàn mặc định cho production. Bật riêng có thời hạn trong môi trường được cho phép.

## 17. Vận hành logging production: volume, rotation, retention và sampling

### 17.1. Tách log cho người và cho máy

Một thiết kế thường gặp:

- **Access logs**: dùng cho HTTP status/latency/bytes, yêu cầu điều tra request, đôi khi vào một index riêng với retention ngắn.
- **Application/business logs**: structured events và errors theo service/environment/version.
- **Security/audit logs**: authentication/authorization-sensitive actions theo quy định truy cập và tính toàn vẹn riêng.
- **Metrics**: request rate, error rate, p95/p99 latency và dependency stats (dùng histogram/counters).
- **Traces**: spans để xem tuyến đường request qua services, thường sampling.

Đừng dùng INFO request log 100% làm thay thế metric counters/histograms nếu request rate cao. Có thể sampling successful request summaries, nhưng giữ đủ thông tin về error/security events theo yêu cầu compliance và SLO; định nghĩa sampling bias khi phân tích data.

### 17.2. Khi chạy Docker/Kubernetes

Ở container runtime, console stdout/stderr thường được nền tảng thu thập tốt hơn file tùy ý; file `./tomcat-demo/logs` có thể **không nằm trong pipeline ấy**. Các lựa chọn:

1. Mount volume/sidecar collector để ship Tomcat access logs.
2. Dùng web server/gateway access logs được hạ tầng thu thập sẵn, phối hợp app structured logs.
3. Cấu hình access log gửi vào một logging pipeline tập trung bằng cách phù hợp platform (không dùng hack file descriptor không được vận hành chấp thuận).
4. Nếu không cần thêm Tomcat logs vì gateway log đáp ứng observability, chủ động quyết định sampling/coverage thay vì bật trùng cả ba tầng không tính chi phí.

Cần giám sát disk quota, log buffer, write errors, rotation, retention và collector backpressure. Nếu disk full chỉ vì access log, HTTP service có thể suy giảm hoặc chết; logging không được trở thành single point of failure.

### 17.3. Vòng đời và quyền truy cập

- Phân quyền read/write log files, index và dashboard theo nhóm cần biết.
- Mã hóa khi truyền đến collector; TLS/authentication cho log pipeline.
- Redaction/allowlist fields trước khi gửi, không chỉ ẩn trong giao diện.
- Định nghĩa retention và xóa dữ liệu theo quy định; đừng giữ PII vô hạn.
- Kiểm tra timezone/cách parse timestamp giữa access logs và application logs; ưu tiên chuẩn UTC trong pipeline khi cần so sánh.
- Thêm service name, deployment version, pod/instance ID để phân biệt replicas.
- Có quy trình hỗ trợ incident: tìm request theo ID, trace, status, route và time window; không yêu cầu người dùng chia sẻ session cookie.

## 18. Các tình huống lỗi và cách điều tra

| Triệu chứng | Khả năng | Bước kiểm tra |
| --- | --- | --- |
| Không thấy Tomcat access log file | Chưa enable, sai basedir/dir, không writable, không dùng Tomcat | Kiểm tra `server.tomcat.accesslog.*` và runtime connector |
| Có Tomcat log nhưng không có app log | Request chặn trước app filter, security filter order, log level/collector | Xác định filter order, `logging.level`, edge/container status |
| Có app business log nhưng thiếu requestId | MDC không truyền async/thread khác, filter không chạy | Kiểm tra lifecycle và context propagation |
| App log có requestId nhưng Tomcat line là `-` | Response header chưa set, log pattern sai, request đi qua handler khác | Kiểm tra `%{X-Request-Id}o` và response header |
| Tomcat status 404, controller không log | Route không match hoặc request không vào method | Kiểm tra route mapping/context path |
| 403 ở gateway nhưng Tomcat không có request | WAF/ingress chặn trước app | Tìm edge access logs và security rule |
| Access log thấy 200, client gặp lỗi download | Stream commit 200 rồi bị cắt, proxy/client disconnect | Bytes/status/connection state và stream error |
| Duration app nhỏ, proxy lớn | Queue/connect/client download/buffering/async | So sánh điểm đo, network, proxy upstream time |
| Duration Tomcat lớn hơn app | Container overhead, async streaming, slow client | Xem `%D` và async/response lifecycle |
| INFO logs quá nhiều | Request rate cao/success logging không sampling | Thêm log volume budget và metrics |
| Log chứa password trong URL | `%r`/`%q`/Referer hay app log raw input | Thay fields, rotate/redact, xử lý incident |
| Debug mất sau restart | File nằm trong temp/ephemeral filesystem | Đưa vào centralized logging/volume |
| Không tìm thấy cùng ID giữa edge và app | Hai phía sinh ID riêng hoặc strip header | Thiết kế edge/app correlation contract |
| Dữ liệu log trùng 2-3 lần | Nhiều filters, duplicate appenders hoặc error dispatch | Kiểm tra logger config, async/error dispatch |
| Exception nhưng statusAtExit=200 | Exception chưa được xử lý, error dispatch xảy ra sau filter | Dùng final container access log/observation |
| `X-Forwarded-For` bị spoof | Proxy không strip, backend public | Khóa trust boundary, không tin header từ client |
| Metrics p99 khác duration từ logs | Sampling, điểm đo khác, đơn vị khác, async | Chuẩn hóa definitions và test pipeline |
| Số request log lệch browser requests | CORS preflight, favicon, health, proxy retries | Tách method, route, edge requests và tracing |

## 19. Checklist trước khi đưa logging lên production

- [ ] Đã xác định **edge access log**, **container access log** và **application request log** với chủ sở hữu rõ.
- [ ] Với Tomcat, `server.tomcat.accesslog.enabled`, basedir, directory, pattern, retention và collector đã được kiểm chứng.
- [ ] Với Jetty/Undertow/WebFlux, không copy nguyên cấu hình Tomcat.
- [ ] Có request ID do nguồn đáng tin cấp; ID được đưa vào response header và log correlation phù hợp.
- [ ] Có distributed tracing nếu request đi qua nhiều services; phân biệt requestId/traceId/spanId.
- [ ] Không log Authorization/Cookie/session ID/password/token/raw sensitive body hoặc query.
- [ ] Route template thay raw path khi có thể, và kiểm tra PII còn có thể nằm trong URL path.
- [ ] App MDC được cleanup ở `finally`, không làm rò ID sang request trên thread reuse.
- [ ] Async, streaming, client disconnect/error dispatch được logging theo **final lifecycle**, không gọi filter exit là full completion khi chưa kiểm tra.
- [ ] Unit/HTTP integration tests kiểm tra status/response header; log pipeline cũng được QA riêng.
- [ ] Đã đối chiếu đơn vị timing của Tomcat `%D`, app milliseconds và proxy latency metrics.
- [ ] Có log budgets/sampling/retention, disk quota/collector alerts và quyền truy cập phù hợp.
- [ ] Log events có fixed schema, không dynamic keys/cardinality cao.
- [ ] Có security-specific audit events khi nghiệp vụ yêu cầu, không chỉ HTTP status.
- [ ] Reverse proxy có forwarded header trust policy; không suy IP/user từ header tùy ý.
- [ ] Đã kiểm tra backup/rotation/kho lưu logs phù hợp chính sách dữ liệu.
- [ ] Đã cập nhật Spring Boot/runtime/collector lên bản bảo trì và có vá bảo mật.

## 20. Câu hỏi tự kiểm tra

**1. Access log và application log có cùng một mục đích không?**  
Không. Access log mô tả HTTP exchange ở server/proxy; app log mô tả diễn biến trong code/business.

**2. Tại sao có HTTP 403 ở edge mà không thấy bất kỳ Tomcat access log nào?**  
Gateway/WAF có thể chặn trước khi request tới app.

**3. Tomcat `%D=10000` nên hiểu là 10000 ms?**  
Không. Với Tomcat, `%D` là microseconds; 10000 µs = 10 ms.

**4. `%U` và `%r` khác nhau gì?**  
`%U` là URL path; `%r` là dòng request có thể kèm query, nên dễ lộ token/PII hơn.

**5. Vì sao requestId trong MDC bị “dính” giữa hai requests?**  
MDC gắn với thread; filter/service không cleanup đúng khi thread được tái sử dụng.

**6. `OncePerRequestFilter` `finally` có luôn là thời điểm client nhận xong SSE không?**  
Không. Servlet async/streaming có thể tiếp tục sau filter chain đã thoát.

**7. Một response 500 ở Tomcat nhưng filter log statusAtExit=200 có thể hợp lệ không?**  
Có, nếu error handling/dispatch diễn ra sau filter thoát; phải log rõ điểm đo.

**8. `X-Request-Id` do client gửi có được tin mặc định không?**  
Không. Cần trusted edge contract, validation hoặc tự sinh ID server như demo.

**9. Muốn liên hệ requests qua nhiều microservices nên dùng requestId local hay distributed tracing?**  
Nên dùng trace context/traceId chuẩn hoặc định danh đã thống nhất ở gateway; requestId local chưa đủ.

**10. Có nên bật `logging.level.org.springframework=TRACE` lâu dài ở production để dễ debug không?**  
Không. Có thể tốn tài nguyên và lộ dữ liệu; chỉ bật theo phạm vi/thời gian được phép.

**11. Access log `%a` phía sau proxy là IP browser thật?**  
Không được bảo đảm; có thể là IP proxy. Cần trust chain và cấu hình đúng.

**12. Log body giúp tìm mọi bug, nên bật global ContentCachingRequestWrapper?**  
Không. Dễ rò PII/secret, tốn memory và làm hỏng hoặc chậm streaming nếu xử lý sai.

**13. Tomcat access log ghi file nhưng console logs được ship lên collector có đủ chưa?**  
Chưa chắc. Collector stdout không tự đọc file access log; cần tích hợp riêng.

**14. Java `System.nanoTime()` dùng để làm gì trong filter?**  
Đo elapsed duration trên cùng clock monotonic, không phải timestamp để đối chiếu timezones.

**15. HTTP status 200 có đủ chứng minh nghiệp vụ đã hoàn tất?**  
Không. 200 chỉ nói response HTTP thành công theo tầng đó; business/audit events cần contract riêng.

## 21. Tài liệu chính thức

- Spring Boot 3.5 — **Configure Access Logging (Embedded Web Servers)**: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5 — **Common Application Properties, server.tomcat.accesslog.***: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Boot — **Logging and Structured Logging**: https://docs.spring.io/spring-boot/reference/features/logging.html
- Spring Boot 3.5 — **Micrometer Tracing / Logging Correlation IDs**: https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html
- Apache Tomcat 10.1 — **AccessLogValve pattern and timing units**: https://tomcat.apache.org/tomcat-10.1-doc/config/valve.html
- Spring Framework — **OncePerRequestFilter API, async/error dispatch**: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Framework — **Asynchronous Requests in Spring MVC**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — **CommonsRequestLoggingFilter API**: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/CommonsRequestLoggingFilter.html
- Spring Framework — **ContentCachingRequestWrapper API**: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/ContentCachingRequestWrapper.html
- SLF4J — **MDC API**: https://www.slf4j.org/api/org/slf4j/MDC.html
- W3C — **Trace Context**: https://www.w3.org/TR/trace-context/
- Spring Boot 3.5.16 — **Release and end-of-OSS-support notice**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Kết luận:** khi quan sát HTTP trong Spring Boot, dùng **container access log** để biết HTTP method/route path/status/bytes/duration từ góc nhìn web server, dùng **application request/business logs** để hiểu logic và kết quả xử lý, và liên kết cả hai bằng **request ID/trace context** đáng tin. Không lẫn duration của Tomcat `%D` với milliseconds, không tin raw client headers, không log credential/PII, không coi filter `finally` là toàn bộ thời gian của async/streaming, và hãy kiểm thử cả HTTP behavior lẫn log collection pipeline trước production.