# Debug production công khai trong ứng dụng Java

**Debug production công khai** là anti-pattern khi ứng dụng đang phục vụ người dùng thật lại để lộ công cụ hoặc dữ liệu chẩn đoán nội bộ qua một giao diện mà người ngoài có thể truy cập. Ví dụ gồm trang lỗi có stack trace, debug console, endpoint quản trị không xác thực, cổng remote debugger, JMX mở ra Internet, heap dump tải công khai hoặc log chứa token và dữ liệu cá nhân.

Những thông tin này giúp đội vận hành tìm nguyên nhân lỗi, nhưng khi công khai chúng có thể tiết lộ cấu trúc hệ thống, thư viện, phiên bản, đường dẫn, hostname, truy vấn database, session, secret và dữ liệu khách hàng. Một số giao diện còn cho phép đọc trạng thái hoặc thay đổi JVM đang chạy.

Trong production, người dùng cần thông báo lỗi đủ rõ để biết yêu cầu thất bại và cách tiếp tục. Đội vận hành cần thông tin chi tiết để điều tra qua một kênh có kiểm soát. Hai mục đích này phải được phục vụ bằng quyền truy cập và mức thông tin phù hợp.

## 1. Vì sao debug công khai là anti-pattern?

Môi trường development thường bật stack trace, auto-reload, debug toolbar, verbose logging và công cụ quản trị để rút ngắn vòng lặp lập trình. Production có dữ liệu thật, credential thật, traffic thật và kết nối tới các hệ thống quan trọng. Giữ nguyên cấu hình debug từ development tạo ra bề mặt tấn công không cần thiết.

Khi người ngoài truy cập được thông tin chẩn đoán, họ có thể:

- Nhận diện framework, application server, thư viện và version đang sử dụng.
- Tìm đường dẫn file, cấu trúc package, tên class, tên bảng và câu SQL.
- Khám phá hostname nội bộ, địa chỉ service, bucket, database hoặc queue.
- Nhìn thấy token, cookie, session ID, API key, password hoặc connection string.
- Đọc dữ liệu cá nhân, nội dung request, dữ liệu giao dịch hoặc thông tin khách hàng.
- Tải heap dump, thread dump, log file hoặc cấu hình có dữ liệu nhạy cảm.
- Gọi thao tác quản trị, thay đổi log level, dừng ứng dụng hoặc can thiệp trạng thái runtime nếu endpoint cho phép.
- Làm ứng dụng chậm hoặc cạn tài nguyên bằng cách yêu cầu dump, trace hoặc profiling nặng.

Một lỗi có vẻ vô hại như hiển thị tên class hoặc đường dẫn tuyệt đối cũng có thể giúp kẻ tấn công lập bản đồ hệ thống và chọn hướng khai thác tiếp theo.

## 2. Nhận diện các dạng debug công khai

| Dạng phơi bày | Ví dụ | Rủi ro |
|---|---|---|
| Error page chi tiết | Stack trace, exception message, SQL | Lộ cấu trúc code, query, path và dữ liệu |
| Debug mode | Trang debug toolbar, interactive console | Lộ biến runtime hoặc cho phép thực thi thao tác |
| Debug endpoint tự tạo | /debug, /dump, /config, /test-db | Bỏ qua authorization hoặc trả dữ liệu nội bộ |
| Remote debugger | JDWP port mở ra mạng công cộng | Người ngoài có thể attach debugger và điều khiển phiên debug |
| Remote JMX | JMX RMI port không được bảo vệ | Theo dõi hoặc quản lý JVM từ xa |
| Actuator/management | env, heapdump, logfile, threaddump | Lộ environment, memory, log và trạng thái hệ thống |
| Public log viewer | Trang tải log hoặc tìm kiếm log không xác thực | Lộ request, token, PII và thông tin vận hành |
| Configuration dump | Hiển thị biến môi trường hoặc application properties | Lộ password, secret, endpoint và feature flag |
| Source map/debug symbol | Source map công khai của frontend | Lộ source code, tên module và logic nội bộ |
| Metrics/trace quá chi tiết | Label chứa email, user ID hoặc request data | Lộ dữ liệu và tạo cardinality cao |

Không phải mọi endpoint quan sát đều nguy hiểm. Health check tối giản có thể phục vụ load balancer hoặc orchestrator. Rủi ro tăng khi endpoint trả chi tiết nội bộ, cho phép thay đổi trạng thái hoặc không có kiểm soát truy cập phù hợp.

## 3. Không trả stack trace cho người dùng

Stack trace hữu ích cho developer vì nó cho biết exception xuất hiện ở đâu và đi qua những method nào. Nhưng response công khai không nên chứa:

- Tên class và package nội bộ.
- Đường dẫn source hoặc thư mục deploy.
- Tên database, bảng, cột và câu SQL.
- Hostname, IP private và tên service nội bộ.
- Nội dung exception có thể chứa input hoặc dữ liệu nhạy cảm.
- Framework version, server version hoặc dependency version.
- Token, cookie, session ID hoặc connection string.

Một response an toàn nên có HTTP status đúng, error code ổn định, thông báo tổng quát và request/correlation ID để người dùng cung cấp khi liên hệ hỗ trợ.

Ví dụ:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
Cache-Control: no-store
X-Request-ID: 7d1c2f9a-...

{
  "code": "INTERNAL_ERROR",
  "message": "Đã xảy ra lỗi. Vui lòng thử lại sau.",
  "requestId": "7d1c2f9a-..."
}
```

Response này cho biết yêu cầu thất bại và cung cấp mã tra cứu. Stack trace cùng nguyên nhân kỹ thuật được ghi vào log nội bộ có kiểm soát bằng cùng request ID.

Không trả HTTP 200 cho mọi lỗi chỉ để tránh hiển thị lỗi. Giữ status code phù hợp như 400, 401, 403, 404, 409, 429 hoặc 500 để client và monitoring xử lý đúng.

## 4. Phân biệt thông tin dành cho client và thông tin dành cho vận hành

| Thông tin | Client công khai | Log/trace nội bộ |
|---|---|---|
| Error code ổn định | Có | Có |
| Thông báo dễ hiểu | Có | Có thể có |
| Request ID | Có | Có |
| Stack trace | Không | Có, nếu cần |
| Exception class/cause | Không | Có |
| SQL, query parameters | Không | Chỉ khi đã loại dữ liệu nhạy cảm và thật sự cần |
| Absolute path/hostname nội bộ | Không | Hạn chế theo nhu cầu điều tra |
| Access token/password | Không | Không ghi trực tiếp |
| PII/sensitive data | Không | Chỉ thu thập khi có căn cứ, tối thiểu và được bảo vệ |
| Runtime/configuration dump | Không | Chỉ qua công cụ quản trị được phân quyền |

Log nội bộ không đồng nghĩa với nơi có thể ghi mọi thứ. Log có thể được sao chép sang nhiều hệ thống, lưu lâu, tải xuống hoặc truy cập bởi nhiều nhóm. Hãy áp dụng phân quyền, retention, masking và audit cho cả hệ thống log.

## 5. Log exception an toàn

Khi exception xảy ra ở boundary của request, log đủ thông tin để truy vết:

- Request ID hoặc trace ID.
- Thời gian, service, environment và version deploy.
- Operation hoặc route đã xử lý.
- Exception class và stack trace.
- Kết quả xử lý và latency nếu cần.
- Các thuộc tính nghiệp vụ đã được phân loại là an toàn.

Tránh log trực tiếp:

- Password, access token, refresh token, API key và private key.
- Session ID hoặc cookie nguyên vẹn.
- Authorization header.
- Database connection string.
- Dữ liệu thẻ thanh toán, thông tin sức khỏe hoặc định danh cá nhân nhạy cảm.
- Toàn bộ request/response body theo mặc định.
- Secret hoặc environment variable chưa được lọc.

Nếu cần liên kết nhiều event của cùng session, dùng identifier giả danh hoặc giá trị hash theo chính sách dữ liệu. Không dùng token xác thực thật làm correlation ID.

Dữ liệu do người dùng gửi có thể chứa newline hoặc ký tự điều khiển. Khi đưa vào log, cần encode/escape để tránh log injection, nơi một input giả mạo tạo ra dòng log trông như event khác.

## 6. Dùng correlation ID để điều tra lỗi

Correlation ID liên kết response của client với log, trace và event nội bộ. Client có thể gửi request ID, nhưng server cần kiểm tra độ dài/ký tự và không tin một giá trị tùy ý làm identity hoặc quyền truy cập.

Một cách đơn giản là server tự tạo ID:

```java
import java.util.UUID;

String requestId = UUID.randomUUID().toString();

System.out.println("requestId=" + requestId);
```

Stdout:

```text
requestId=<UUID-generated-at-runtime>
```

Trong ứng dụng web, tạo ID ở request filter/interceptor, gắn vào logging context (ví dụ MDC của logging framework), trả về header response và đưa vào trace. Khi nhận ticket hỗ trợ, đội vận hành tìm đúng ID trong hệ thống log.

Correlation ID không phải secret, session token hoặc cơ chế xác thực. Không cấp quyền truy cập log chỉ vì người dùng biết request ID. Không cho phép ID do client gửi chứa newline hoặc nội dung dài bất thường.

## 7. Ví dụ Java 17+: trả lỗi đã làm sạch và log nguyên nhân nội bộ

Ví dụ dưới đây dùng HTTP server có sẵn trong JDK để minh họa cách tách response công khai khỏi log kỹ thuật. Endpoint demo luôn phát sinh lỗi để dễ quan sát; không dùng logic giả lập này cho endpoint nghiệp vụ thật.

Tạo file `SafeErrorServer.java`:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

public final class SafeErrorServer {
    private static final System.Logger LOG =
            System.getLogger(SafeErrorServer.class.getName());

    private SafeErrorServer() {
    }

    public static void main(String[] args) throws IOException {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 8080), 0);

        server.createContext("/demo", SafeErrorServer::handle);
        server.start();

        System.out.println("listening=http://127.0.0.1:8080");
    }

    private static void handle(HttpExchange exchange)
            throws IOException {
        String requestId = UUID.randomUUID().toString();

        try {
            // Demo: thay bằng thao tác nghiệp vụ có thể phát sinh lỗi.
            throw new IllegalStateException(
                    "Database connection unavailable");
        } catch (RuntimeException failure) {
            LOG.log(
                    System.Logger.Level.ERROR,
                    "request_id=" + requestId + " operation=demo",
                    failure);

            String json = "{"
                    + "\"code\":\"INTERNAL_ERROR\","
                    + "\"message\":\"Đã xảy ra lỗi. Vui lòng thử lại sau.\","
                    + "\"requestId\":\"" + requestId + "\""
                    + "}";

            byte[] body = json.getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type", "application/json; charset=utf-8");
            exchange.getResponseHeaders().set("Cache-Control", "no-store");
            exchange.getResponseHeaders().set("X-Request-ID", requestId);

            exchange.sendResponseHeaders(500, body.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(body);
            }
        } finally {
            exchange.close();
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```sh
javac --add-modules jdk.httpserver SafeErrorServer.java
java --add-modules jdk.httpserver SafeErrorServer
```

Stdout khi server khởi động:

```text
listening=http://127.0.0.1:8080
```

Gửi request ở terminal khác:

```sh
curl -i http://127.0.0.1:8080/demo
```

Response body có dạng:

```json
{
  "code": "INTERNAL_ERROR",
  "message": "Đã xảy ra lỗi. Vui lòng thử lại sau.",
  "requestId": "<UUID>"
}
```

Request ID thay đổi theo mỗi request. Exception và stack trace được gửi tới logger; trong production, cấu hình logger chuyển chúng tới log collector nội bộ có phân quyền. Không cấu hình stderr của process thành một endpoint hoặc log stream công khai.

Server demo bind vào loopback 127.0.0.1 để thử tại máy local. Khi triển khai thật, địa chỉ bind phải phù hợp với kiến trúc mạng/service mesh; việc bind vào private interface không tự thay thế authentication, authorization và firewall.

## 8. Xử lý exception tập trung trong web framework

Trong ứng dụng Spring MVC, có thể dùng `@RestControllerAdvice` để chuẩn hóa lỗi tại một nơi:

```java
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    private static final Logger log =
            LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> handleUnexpected(Exception error) {
        String requestId = UUID.randomUUID().toString();

        log.error("request_id={} operation=api-request",
                requestId, error);

        ApiError body = new ApiError(
                "INTERNAL_ERROR",
                "Đã xảy ra lỗi. Vui lòng thử lại sau.",
                requestId);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .header("X-Request-ID", requestId)
                .body(body);
    }

    public record ApiError(
            String code,
            String message,
            String requestId) {
    }
}
```

Đây là ví dụ phụ thuộc Spring Web và SLF4J; không phải class chỉ dùng JDK. Trong ứng dụng thực tế, nên có handler riêng cho lỗi nghiệp vụ dự kiến (validation, not found, conflict, rate limit) và handler tổng quát cho lỗi bất ngờ.

Không bắt Throwable rồi tiếp tục chạy như không có gì. Những lỗi nghiêm trọng của JVM như OutOfMemoryError không nên bị xử lý như lỗi request thông thường. Cần để cơ chế runtime/orchestrator xử lý theo chính sách phục hồi phù hợp.

## 9. Tắt debug mode và error detail trong production

Cấu hình production cần được tách khỏi development. Đừng dựa vào việc developer nhớ tắt một checkbox trước khi release.

Các kiểm soát thường cần có:

- Không đóng gói dev console hoặc interactive debug page vào production runtime.
- Tắt verbose error page và stack trace trong HTTP response.
- Không bật profile development ở production.
- Không để debug toolbar, test controller hoặc endpoint giả lập tồn tại trong artifact release.
- Không bật remote restart/devtools trên môi trường public.
- Dùng cấu hình production mặc định an toàn và kiểm tra lại ở bước deploy.
- Fail deployment nếu cấu hình debug không phù hợp với môi trường production.

Với Spring Boot, các thuộc tính sau giúp tránh đưa exception detail vào error response:

```yaml
server:
  error:
    include-message: never
    include-binding-errors: never
    include-stacktrace: never
    include-exception: false

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      show-components: never
```

Đây là ví dụ cấu hình Spring Boot. Kiểm tra tài liệu của đúng version framework đang dùng trước khi áp dụng; cấu hình error response không thay thế security rules cho endpoint quản trị.

## 10. Actuator không phải public debug console

Spring Boot Actuator cung cấp endpoint giám sát và quản trị. Một số endpoint có thể trả dữ liệu nhạy cảm hoặc thực hiện thao tác ảnh hưởng đến ứng dụng.

Các endpoint cần được đánh giá kỹ:

| Endpoint | Nội dung/chức năng | Rủi ro khi công khai |
|---|---|---|
| /actuator/health | Trạng thái health | Có thể tiết lộ component nếu bật details |
| /actuator/env | Environment và property source | Có thể lộ config/secret nếu unsanitize |
| /actuator/configprops | Configuration properties | Có thể lộ cấu hình nhạy cảm |
| /actuator/beans | Bean trong application context | Tiết lộ cấu trúc ứng dụng |
| /actuator/mappings | Request mapping | Tiết lộ route và handler |
| /actuator/loggers | Đọc/thay đổi log level | Có thể làm lộ dữ liệu qua verbose logging |
| /actuator/threaddump | Thread dump | Tiết lộ stack, tên thread và hoạt động nội bộ |
| /actuator/heapdump | Heap dump | Có thể chứa password, token và dữ liệu trong memory |
| /actuator/logfile | Nội dung log file | Có thể lộ request, PII và secret |
| /actuator/shutdown | Yêu cầu tắt ứng dụng | Có thể gây gián đoạn dịch vụ nếu được bật |

Tài liệu Spring Boot hiện hành cho biết chỉ health endpoint được expose qua HTTP theo mặc định. Endpoint health mặc định không hiển thị details. Khi mở thêm endpoint, phải đánh giá dữ liệu trả về và bảo vệ bằng security policy phù hợp.

Nếu cần management endpoint cho monitoring, chỉ expose endpoint thật sự cần thiết. Đặt management interface trong mạng riêng, dùng authentication/authorization và firewall hoặc service mesh policy. Tách management port có thể hữu ích về kiến trúc, nhưng riêng port khác không phải ranh giới bảo mật.

Nếu ứng dụng có custom Spring Security SecurityFilterChain, quy tắc auto-configuration của Actuator có thể không còn áp dụng theo cách bạn mong đợi. Hãy viết và kiểm thử rule rõ ràng cho từng nhóm endpoint.

## 11. Health check công khai cần trả mức thông tin tối thiểu

Load balancer và orchestrator thường cần biết ứng dụng còn sống hay đã sẵn sàng nhận traffic. Họ không cần toàn bộ cấu hình database, hostname, credential hoặc trạng thái của từng dependency.

Có thể phân biệt:

- **Liveness:** process còn hoạt động và không cần bị restart ngay.
- **Readiness:** instance có thể nhận request mới hay chưa.
- **Deep diagnostics:** thông tin chi tiết về dependency, pool, queue, thread và resource; chỉ dành cho monitoring/operations có quyền.

Health response công khai nên tránh trả:

- JDBC URL hoặc hostname database.
- Tên bucket, queue, internal service.
- Exception message từ dependency.
- Secret hoặc connection status có chi tiết xác thực.
- Stack trace và cấu hình runtime.

Nếu cần health detail, chỉ hiển thị cho role monitoring được xác thực hoặc trên management network. Cẩn thận với health check phụ thuộc quá nhiều service bên ngoài: một dependency tạm thời lỗi có thể khiến mọi instance bị đánh dấu unhealthy và tạo thêm outage.

## 12. Không mở JDWP remote debugger ra Internet

Java Debug Wire Protocol (JDWP) cho phép debugger giao tiếp với JVM đang được debug. Socket transport dùng TCP; khi target VM lắng nghe, debugger có thể attach và gửi command tới JVM.

Ví dụ tùy chọn khởi động:

```sh
-agentlib:jdwp=transport=dt_socket,server=y,address=*:5005,suspend=n
```

Địa chỉ * yêu cầu socket lắng nghe trên mọi network interface. Nếu port 5005 có thể truy cập công khai, người ngoài có thể tìm cách kết nối tới debug agent. Hãy coi khả năng kết nối JDWP như quyền truy cập đặc quyền vào process.

Không bật JDWP trong production thông thường. Nếu incident thực sự cần debugger:

1. Ưu tiên tái hiện lỗi trên staging với dữ liệu đã được làm sạch.
2. Nếu buộc phải debug production, có phê duyệt incident và người chịu trách nhiệm.
3. Bind vào loopback hoặc private interface được kiểm soát.
4. Dùng VPN, bastion hoặc SSH tunnel có xác thực để kết nối.
5. Giới hạn source IP và thời gian mở port.
6. Không mở port debug trực tiếp trên public load balancer/security group.
7. Ghi nhận ai đã attach, thời điểm và thao tác đã thực hiện.
8. Tắt JDWP, đóng tunnel/firewall rule và xác minh port không còn lắng nghe sau khi điều tra.

Ví dụ bind loopback:

```sh
-agentlib:jdwp=transport=dt_socket,server=y,address=127.0.0.1:5005,suspend=n
```

Có thể tạo tunnel từ máy quản trị đã xác thực:

```sh
ssh -L 5005:127.0.0.1:5005 operator@private-host
```

Lệnh tunnel chỉ có ý nghĩa khi SSH host là máy có thể truy cập an toàn và port debug target chỉ bind vào loopback của host đó. Không coi JDWP là giao thức có authentication/encryption tương đương một API production được bảo vệ.

## 13. Bảo vệ JMX remote

JMX hỗ trợ theo dõi và quản lý JVM, MBean và một số thao tác runtime. Remote JMX có thể hữu ích cho công cụ vận hành nhưng không nên mở tự do trên Internet.

Oracle cảnh báo remote JMX cần security để ngăn người không được phép theo dõi hoặc điều khiển ứng dụng. Tài liệu production khuyến nghị dùng cả client certificate SSL/TLS và password authentication để xác thực host/client và user.

Các nguyên tắc:

- Chỉ bật remote JMX khi có nhu cầu vận hành cụ thể.
- Giới hạn network path tới management network.
- Bật TLS và client authentication theo policy.
- Dùng password/access file hoặc cơ chế identity phù hợp, bảo vệ file credential bằng permission nghiêm ngặt.
- Phân quyền read-only và control riêng nếu hệ thống hỗ trợ.
- Không đặt com.sun.management.jmxremote.authenticate=false cùng com.sun.management.jmxremote.ssl=false trong production.
- Không công bố RMI registry và connector port ra public network.
- Theo dõi access log và thay credential/certificate theo vòng đời.

JMX read-only vẫn có thể tiết lộ thông tin runtime. Quyền quản lý có thể thay đổi cấu hình hoặc hành vi ứng dụng; hãy phân quyền theo nhiệm vụ.

## 14. Heap dump, thread dump và Java Flight Recorder

Các công cụ chẩn đoán JVM rất hữu ích khi xử lý memory leak, deadlock hoặc latency. Chúng cũng có thể chứa thông tin nhạy cảm.

**Heap dump** có thể chứa object đang sống trong heap: nội dung request, session, token, password tạm thời, dữ liệu cá nhân và cache. Một file heap dump có thể lớn và tốn CPU/I/O khi tạo.

**Thread dump** chứa stack trace, tên thread, tên class, lock và hoạt động của ứng dụng. Nó có thể tiết lộ internal route, dependency và operation đang chạy.

**Java Flight Recorder (JFR)** ghi lại sự kiện runtime phục vụ phân tích hiệu năng. Tùy event và cấu hình, recording có thể chứa metadata hoặc dữ liệu nhạy cảm.

Hãy lưu các file này trong storage nội bộ có ACL, encryption at rest, retention ngắn và audit download. Không đặt heap dump hoặc recording trong thư mục static/public web. Xác định người được phép tải, mục đích sử dụng và thời hạn lưu; xóa bản sao theo retention policy sau incident nếu không cần lưu làm evidence.

Không tạo heap dump liên tục trên production chỉ để “xem thử”. Đánh giá dung lượng, tác động performance và cách thu thập trước khi thực hiện.

## 15. Không công khai log viewer và configuration dump

Một trang log viewer tiện lợi cho developer có thể trở thành nguồn rò rỉ dữ liệu khi được publish cùng ứng dụng.

Không tạo endpoint public để:

- Tải file log theo path do request cung cấp.
- Tìm kiếm log theo user hoặc session mà không có authorization.
- Xem toàn bộ environment variables.
- Xem toàn bộ Spring properties hoặc secrets.
- Đọc file cấu hình tùy ý.
- Trả nội dung heap/thread dump.
- Chạy câu SQL hoặc command để kiểm tra hệ thống.

Đường dẫn do người dùng truyền vào log viewer còn có thể gây path traversal nếu xử lý sai. Hệ thống log nên được truy cập qua nền tảng observability riêng, với SSO/MFA, role, audit và bộ lọc dữ liệu.

Configuration dump đặc biệt nguy hiểm vì nhiều secret được inject từ environment, secret manager hoặc mounted file. Không trả nguyên object config để tiện debug; chỉ cung cấp trạng thái đã lọc và không chứa giá trị secret.

## 16. Metrics và traces cũng có thể làm lộ dữ liệu

Metrics thường được coi là an toàn vì chỉ chứa số liệu. Nhưng label có thể chứa thông tin nhạy cảm nếu đưa email, username, account ID, order ID hoặc URL đầy đủ vào metric dimension.

Tránh:

- Label theo từng user hoặc từng request.
- Ghi nguyên query string có token.
- Đưa email, số điện thoại hoặc định danh cá nhân vào tag.
- Ghi SQL bind parameter vào span không được lọc.
- Dùng exception message làm metric label.
- Expose metrics endpoint ra public mà không có network policy.

Metrics cần label có cardinality thấp và không chứa dữ liệu cá nhân. Traces cần sampling, masking attribute và phân quyền truy cập. Với URL, chỉ giữ route template như /orders/{id} thay vì URL đầy đủ chứa identifier hoặc query parameter.

## 17. Source map và debug symbol trong artifact frontend

Một ứng dụng Java có thể phục vụ frontend bundle. Source map công khai có thể cho phép khôi phục source code dễ đọc, tên module, cấu trúc thư mục và một phần comment/logic nội bộ.

Trước release:

- Xác định source map có cần public hay chỉ phục vụ error monitoring.
- Nếu dùng dịch vụ error monitoring, upload source map qua kênh xác thực và không public file đó.
- Kiểm tra web server/CDN không phục vụ file .map ngoài chủ đích.
- Không nhúng secret vào frontend bundle; mọi giá trị gửi tới browser đều có thể bị người dùng xem.
- Xác minh artifact production không chứa debug asset hoặc config development.

Obfuscation không thay thế bảo mật. Bất kỳ logic hoặc credential nào chạy trong browser phải được xem là có thể quan sát từ phía client.

## 18. Không dùng debug endpoint để sửa dữ liệu production

Một số endpoint được tạo tạm để hỗ trợ incident có thể thực hiện thao tác nguy hiểm:

- Đổi trạng thái đơn hàng hoặc tài khoản.
- Xóa cache hoặc queue.
- Chạy SQL tùy ý.
- Reset password hoặc tạo user quản trị.
- Gửi lại event hoặc thanh toán.
- Gọi method nội bộ bằng tên class/method.
- Chỉnh log level hoặc feature flag không có audit.

Nếu cần thao tác quản trị, xây dựng control plane riêng có authentication, authorization, validation, audit, approval và idempotency. Không tạo endpoint bí mật dựa trên URL khó đoán hoặc một query parameter như ?admin=true.

Một endpoint không được liên kết trong menu vẫn có thể bị tìm thấy qua route discovery, log, source code hoặc traffic. “Không ai biết URL” không phải cơ chế kiểm soát truy cập.

## 19. Quy trình debug production an toàn

Khi incident xảy ra, ưu tiên sử dụng dữ liệu quan sát đã được thiết kế trước:

1. Xác định thời gian, service, version deploy và phạm vi ảnh hưởng.
2. Dùng metrics để xác định xu hướng lỗi, latency, saturation và dependency.
3. Dùng trace để tìm span chậm hoặc service gây lỗi.
4. Dùng log nội bộ theo request ID để xem exception và operation.
5. Kiểm tra deployment/config change gần thời điểm bắt đầu lỗi.
6. Tái hiện trên staging bằng dữ liệu đã ẩn danh nếu có thể.
7. Nếu cần diagnostics đặc quyền trên production, mở quyền theo incident, thời hạn và người chịu trách nhiệm.
8. Thu thập dump/recording vào storage được bảo vệ và ghi nhận tác động.
9. Khôi phục cấu hình, đóng port/tunnel và thu hồi quyền tạm sau điều tra.
10. Nếu dữ liệu nhạy cảm đã bị lộ, đánh giá phạm vi, bảo toàn evidence và rotate/revoke credential theo incident response plan.

Không bật debug công khai chỉ để tăng tốc điều tra. Nếu thiếu telemetry, bổ sung instrumentation có kiểm soát sau khi đã đánh giá dữ liệu được thu thập.

## 20. Kiểm tra cấu hình production trước khi phát hành

Tạo release checklist cho từng service:

- Profile production đã được chọn.
- Debug mode, dev console, debug toolbar và test route đã tắt/gỡ.
- Error response không chứa stack trace hoặc exception detail.
- Actuator chỉ expose endpoint được phê duyệt.
- Health details không tiết lộ dependency hoặc internal hostname.
- JDWP không bật; không có debug port public.
- JMX remote bị tắt nếu không cần, hoặc được bảo vệ đúng policy.
- Log viewer/config dump không public.
- Heap dump, thread dump và recording lưu ở storage riêng.
- Metrics/traces không chứa PII, token hoặc high-cardinality identifiers.
- Source map/debug symbol không bị public ngoài chủ đích.
- Security rules đã được kiểm thử sau khi thêm custom filter chain.
- Secret không xuất hiện trong response, log, artifact hoặc container image.
- Public route scan không tìm thấy endpoint debug/admin ngoài dự kiến.

Kiểm tra cấu hình thực tế của artifact đã build và môi trường deploy. Một file application-prod.yml đúng không đảm bảo deploy thật sự dùng profile đó.

## 21. Kiểm thử không rò rỉ thông tin

Trong test/staging hoặc security test có thẩm quyền, tạo một số lỗi có kiểm soát và xác minh response công khai.

Kiểm tra:

- Lỗi 500 không trả stack trace, exception message hoặc internal path.
- Lỗi validation không echo secret hoặc toàn bộ input nhạy cảm.
- Response có request ID và status code đúng.
- Health endpoint chỉ trả thông tin tối thiểu.
- Endpoint management không được phép trả 401/403 hoặc không tồn tại theo policy.
- JDWP/JMX port không reachable từ mạng công cộng.
- Log có request ID nhưng không có password/token/cookie.
- Heap dump/log file không được phục vụ từ static web directory.
- Production artifact không chứa dev-only endpoint hoặc source map public.
- Người dùng không có quyền quản trị không thể gọi control endpoint.

Có thể kiểm tra response bằng test tự động:

```sh
curl -i https://app.example.com/api/demo-error
```

Sau đó xác nhận body không chứa các chuỗi như java.lang., at com., /opt/app/, jdbc:, password=, Authorization: hoặc token thật. Các chuỗi trên chỉ là dấu hiệu tìm kiếm; kiểm tra bảo mật phải xét ngữ cảnh để tránh false positive.

Không chạy fuzzing hoặc tạo tải lớn trên production khi chưa có kế hoạch và phê duyệt phù hợp.

## 22. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Người dùng thấy stack trace HTTP 500 | Framework đang include exception/stack trace | Tắt error detail và dùng handler tập trung |
| Response có SQL hoặc database hostname | Exception message được trả trực tiếp | Trả error code tổng quát, log nội bộ đã lọc |
| Actuator trả environment/config | Expose endpoint quá rộng hoặc sanitizer không phù hợp | Chỉ expose endpoint cần thiết, xác thực và kiểm tra sanitize |
| Heap dump tải được từ URL public | Dump nằm trong static directory hoặc endpoint không bảo vệ | Chuyển sang private storage và giới hạn quyền |
| JDWP port xuất hiện trong public scan | Debug agent bind wildcard/public interface | Tắt JDWP hoặc bind loopback/private network và đóng firewall |
| JMX không yêu cầu authentication | Remote JMX security bị tắt | Bật TLS/client auth/password và giới hạn network |
| Log có token hoặc cookie | Log toàn bộ header/request | Mask/drop trường nhạy cảm trước khi ghi |
| Metrics chứa email/user ID | Dùng dữ liệu người dùng làm label | Dùng dimension tổng hợp, cardinality thấp |
| Frontend source map truy cập được | Build/deploy public .map ngoài chủ đích | Giữ source map trong error-monitoring service riêng |
| Debug endpoint không có trong menu vẫn truy cập được | URL khó đoán được coi là bảo mật | Áp dụng authorization server-side và remove route |
| Chỉ staging an toàn, production vẫn debug | Profile hoặc environment variable deploy sai | Kiểm tra effective config và fail deployment khi debug bật |
| Sau incident quên đóng cổng debug | Không có expiry và cleanup owner | Dùng change có thời hạn, ticket và bước xác minh đóng port |
| Security rule Actuator không còn tác dụng | Custom SecurityFilterChain làm thay đổi auto-configuration | Viết rule endpoint riêng và test integration |

## 23. Runbook khi phát hiện debug công khai

Nếu phát hiện production đang phơi bày thông tin debug:

1. Xác định endpoint/port và dữ liệu có thể truy cập.
2. Thu thập evidence tối thiểu: URL, thời gian, response mẫu đã redact, source IP và log liên quan.
3. Xác định liệu dữ liệu nhạy cảm, token, credential hoặc PII có bị lộ không.
4. Chặn truy cập public bằng network/security rule hoặc tắt endpoint theo quy trình incident.
5. Không xóa log/evidence cần thiết cho điều tra.
6. Rotate/revoke credential nếu có khả năng đã lộ.
7. Xác định thời điểm bắt đầu phơi bày và phạm vi người có thể truy cập.
8. Kiểm tra access log để xác định request đã truy cập endpoint.
9. Khôi phục cấu hình an toàn và triển khai bản sửa.
10. Kiểm tra lại từ góc nhìn mạng bên ngoài.
11. Ghi nhận nguyên nhân gốc, ảnh hưởng, hành động khắc phục và biện pháp ngăn tái diễn.

Nếu endpoint cho phép thay đổi trạng thái hoặc thực thi thao tác đặc quyền, xử lý như một security incident theo quy trình của tổ chức.

## 24. Checklist

- [ ] Production không bật debug mode, interactive console hoặc debug toolbar.
- [ ] Error response không trả stack trace, exception message hoặc internal path.
- [ ] Error code và request ID được dùng để tra cứu nội bộ.
- [ ] Log exception được lưu trong hệ thống có phân quyền.
- [ ] Log không chứa password, token, cookie, connection string hoặc private key.
- [ ] PII và request body được thu thập tối thiểu, masking theo policy.
- [ ] Log input được sanitize để ngăn log injection.
- [ ] Actuator chỉ expose endpoint đã được phê duyệt.
- [ ] Health response không trả dependency detail hoặc secret.
- [ ] Management endpoint có authentication, authorization và network control.
- [ ] JDWP không mở ra public network.
- [ ] JMX remote được tắt hoặc bảo vệ bằng TLS/client certificate và authentication.
- [ ] Heap dump, thread dump và JFR lưu ở storage riêng có retention.
- [ ] Log viewer và configuration dump không public.
- [ ] Metrics/traces không chứa PII, token hoặc high-cardinality identifiers.
- [ ] Source map/debug symbol không public ngoài chủ đích.
- [ ] Admin/debug operation có RBAC, audit và approval.
- [ ] Production profile và effective configuration được kiểm tra trong release.
- [ ] Error/endpoint exposure được kiểm thử tự động.
- [ ] Diagnostic access tạm thời có owner, expiry và bước cleanup.
- [ ] Credential được rotate nếu có bằng chứng hoặc khả năng đã bị lộ.

## 25. Tài liệu tham khảo

- OWASP Error Handling Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html
- OWASP Web Security Testing Guide — Improper Error Handling: https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/08-Error_Handling/01-Improper_Error_Handling/
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- Spring Boot Reference — Actuator Endpoints and Security: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Oracle Java Platform Debugger Architecture — Connection and Invocation Details: https://docs.oracle.com/en/java/javase/17/docs/specs/jpda/conninv.html
- Oracle Java Management — Monitoring and Management Using JMX: https://docs.oracle.com/en/java/javase/17/management/monitoring-and-management-using-jmx-technology.html
- Oracle Java Management — JMX Security: https://docs.oracle.com/en/java/javase/17/jmx/security.html

Debug production công khai làm tăng nguy cơ lộ cấu trúc hệ thống, dữ liệu khách hàng và quyền điều khiển runtime. Hãy trả lỗi tổng quát kèm request ID, lưu diagnostics trong log/observability có phân quyền, giới hạn Actuator/JMX/JDWP vào management plane được bảo vệ và chỉ mở quyền debug tạm thời theo quy trình incident có audit và thời hạn rõ ràng.