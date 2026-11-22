# User context trong Logging — Gắn ngữ cảnh người dùng an toàn vào log Java

## 1. User context là gì?

Trong **Java Core Logging**, **user context** là tập thông tin tối thiểu về **chủ thể thực hiện hành động** được gắn kèm các sự kiện log để trả lời các câu hỏi như:

- Ai hoặc **loại chủ thể nào** đã khởi xướng một yêu cầu hay tác vụ?
- Sự kiện này thuộc **request**, phiên xử lý hoặc job nào?
- Chủ thể được xác thực hay là **anonymous**? Nếu là hệ thống nội bộ thì đó là **service account** nào?
- Một thao tác được thực hiện **thay mặt ai** trong tình huống delegated access hoặc impersonation có kiểm soát?
- Có thể liên hệ bản ghi của nhiều tầng ứng dụng với nhau mà **không ghi bí mật hoặc dữ liệu cá nhân không cần thiết** như thế nào?

Ví dụ **log minh họa**:

~~~text
INFO  requestId=req-42 actorRef=usr-7 event=profile.read outcome=success
WARN  requestId=req-42 actorRef=usr-7 event=rate_limit.approaching remaining=2
ERROR requestId=req-42 actorRef=usr-7 event=profile.write.failed errorCode=UPSTREAM_TIMEOUT
~~~

Ở đây, **actorRef=usr-7** là **định danh tham chiếu minh họa**, không phải tên hoặc email. **requestId** chỉ một luồng yêu cầu; **actorRef** đại diện chủ thể đã thực hiện thao tác; **event** và **errorCode** có ý nghĩa ổn định cho tìm kiếm.

**User context trong log không phải cơ chế authentication/authorization.** Log dùng để quan sát và điều tra; các quyết định cho phép truy cập vẫn phải dựa trên security context, token/session đã được xác minh, chính sách phân quyền và trạng thái hệ thống đáng tin cậy.

**User context cũng không phải toàn bộ hồ sơ người dùng.** Trong đa số tình huống, vài trường tham chiếu được kiểm soát là đủ. Ghi nguyên tên, email, số điện thoại, địa chỉ, token hay toàn bộ claims từ JWT vào log làm tăng rủi ro bảo mật mà không nhất thiết giúp chẩn đoán.

### Mục tiêu của bài

Sau bài này, bạn có thể:

1. Chọn những field user context phù hợp cho log.
2. Phân biệt **userId/actorRef**, **requestId**, **traceId**, **tenantRef** và **principal**.
3. Gắn và dọn context đúng vòng đời bằng **SLF4J MDC**.
4. Hiểu tại sao **MDC không tự truyền qua thread pool** và cách copy/restore đúng.
5. Cấu hình Logback để xuất context bằng pattern hoặc structured encoder.
6. Xử lý anonymous user, service principal, delegated action và multi-tenancy.
7. Tránh rò rỉ thông tin và kiểm tra log thực tế bằng một ví dụ Java 17 chạy được.

## 2. Vì sao user context có giá trị?

Một dòng log thiếu context:

~~~text
ERROR event=profile.write.failed errorCode=UPSTREAM_TIMEOUT
~~~

cho biết loại lỗi nhưng không giúp xác định **request** nào trong hàng nghìn request cùng lúc. Có thêm thông tin:

~~~text
ERROR requestId=req-42 actorRef=usr-7 event=profile.write.failed errorCode=UPSTREAM_TIMEOUT
~~~

người vận hành có thể:

- Tìm những event có cùng requestId và xem diễn tiến trước lỗi.
- Phân biệt lỗi của một thao tác cụ thể với lỗi rộng trên toàn service.
- Liên kết với trace/metric và dữ liệu hỗ trợ mà hệ thống **đã cho phép** truy cập.
- Xác định hành vi được phát bởi user thông thường, admin hoặc service account mà không cần lộ thông tin định danh trực tiếp.
- Kiểm tra một bản ghi có đang gắn sai context do thread reuse hay không.

Tuy vậy, log **không chứng minh hành động được ủy quyền hợp lệ** chỉ vì trường actorRef xuất hiện. Dữ liệu MDC có thể bị gắn nhầm, bị sao chép sai hoặc bị lấy từ nguồn không đáng tin. Để điều tra bảo mật/audit, phải kết hợp với **sự kiện xác thực, kiểm tra quyền và audit trail** có kiểm soát.

## 3. Phân biệt các loại context

| Trường | Ví dụ | Mô tả | Sai lầm cần tránh |
| --- | --- | --- | --- |
| **actorRef** | usr-7 | Tham chiếu chủ thể thực hiện hành động | Ghi tên/email/raw token thay thế |
| **actorType** | user / service / anonymous | Loại chủ thể | Mặc định mọi request đều đã đăng nhập |
| **requestId** | req-42 | ID của một yêu cầu | Dùng làm userId hoặc coi là quyền truy cập |
| **traceId** | ID trace theo chuẩn tracing | Liên kết request qua nhiều service | Tự điền bằng dữ liệu người dùng chưa kiểm soát |
| **spanId** | ID một span | Liên kết event tới một bước xử lý | Trộn spanId với requestId |
| **tenantRef** | tenant-3 | Tham chiếu tenant khi ứng dụng multi-tenant | Lộ tenant qua log không kiểm soát |
| **subjectRef** | usr-9 | Đối tượng chịu tác động, có thể khác actor | Đồng nhất actor và subject |
| **jobId** | job-78 | Tác vụ nền không thuộc HTTP request hiện tại | Cố gán requestId giả cho mọi job |
| **authenticationState** | authenticated / anonymous | Tình trạng xác thực đã được xác minh | Log trực tiếp header/token làm bằng chứng |
| **event** | profile.read | Loại sự kiện ổn định | Nhét ID động vào tên event |
| **errorCode** | ACCESS_DENIED | Mã lỗi kỹ thuật/nghiệp vụ ổn định | Dùng exception.message làm mã lỗi |

Các field trên là **gợi ý cho schema**, không phải danh sách bắt buộc. Một dịch vụ nhỏ có thể chỉ cần requestId, actorType, actorRef và event; một hệ thống đa tenant có thể cần thêm tenantRef.

**actorRef có thể vẫn là dữ liệu liên quan đến một cá nhân.** Đặt ID thay email không tự làm dữ liệu trở thành vô danh. Phải áp dụng chính sách thu thập, quyền truy cập, retention và xóa dữ liệu phù hợp. Nếu dùng pseudonymization, cần thiết kế bởi đội có thẩm quyền; hash không có khóa của một ID dễ đoán thường **không bảo vệ đầy đủ** chống dò ngược.

## 4. User context khác security context

Một luồng yêu cầu có thể có:

~~~text
HTTP request
    |
    v
Authentication: xác minh token/session
    |
    v
Security context: principal và quyền đã được xác thực
    |
    +--> Authorization: được phép thao tác không?
    |
    v
Tạo logging context (allowlist field tối thiểu)
    |
    v
Business code -> Logger -> Appender -> Collector
~~~

**Security context** phục vụ việc xác thực/phân quyền. **Logging context** là dữ liệu để mô tả sự kiện và tương quan log, có thể được tạo từ **một phần thông tin đã xác minh** của security context.

Cần nhớ:

- **Không dùng MDC.get("actorRef") để quyết định quyền truy cập.** MDC là dữ liệu phụ trợ cho logging, không phải kho xác thực an toàn.
- Không tin một header như **X-User-Id** hay request parameter do client gửi để kết luận ai đang đăng nhập.
- Nếu client có gửi request ID, phải áp dụng quy tắc validate/giới hạn độ dài hoặc tạo ID nội bộ đáng tin.
- Chỉ lấy actorRef từ **principal đã xác minh** hoặc service identity do hệ thống tin cậy cung cấp.
- Security context có thể chưa tồn tại khi request chưa đăng nhập hoặc xác thực thất bại; lúc đó **actorType=anonymous** là một lựa chọn minh bạch hơn việc đoán người dùng.

Một lỗi bảo mật thường gặp là đưa toàn bộ **JWT claims** vào log. JWT có thể chứa email, roles, group, tenant và nhiều thông tin nhạy cảm; token nguyên văn là credential không được ghi. Chỉ trích xuất các trường an toàn thực sự cần, theo allowlist.

## 5. Thiết kế schema user context tối thiểu

Một record JSON minh họa:

~~~json
{
  "schemaVersion": 1,
  "timestamp": "2026-11-09T10:15:00.125Z",
  "level": "INFO",
  "service": "profile-api",
  "event": "profile.read",
  "requestId": "req-42",
  "actorType": "user",
  "actorRef": "usr-7",
  "outcome": "success",
  "message": "Profile read completed"
}
~~~

Có thể áp dụng các quy tắc:

1. **actorType** thuộc tập giá trị đã quy định: ví dụ user, service, anonymous. Không để một nhóm dùng "human", nhóm khác dùng "end-user" nếu cùng ý nghĩa.
2. **actorRef** là string theo format do hệ thống kiểm soát, có thể không có đối với anonymous.
3. **requestId** là string cho từng request, tránh dùng giá trị có quyền truy cập hoặc thông tin bí mật.
4. **event** ổn định như profile.read, không dùng thông điệp tự nhiên làm khóa truy vấn.
5. **timestamp** có múi giờ rõ ràng, ưu tiên UTC theo quy ước vận hành.
6. **outcome** là string enum với ý nghĩa thống nhất, không trộn success/ok/done tùy module.
7. **message** giải thích cho con người và không chứa raw data nhạy cảm.
8. Các trường bổ sung như tenantRef, subjectRef, errorCode chỉ xuất khi có ý nghĩa.

### Null, thiếu field và anonymous

Ba cách sau có ý nghĩa khác nhau:

~~~json
{"actorType":"anonymous","event":"catalog.view"}
{"actorType":"user","actorRef":null,"event":"profile.read"}
{"actorType":"user","actorRef":"","event":"profile.read"}
~~~

Ví dụ đầu biểu diễn request anonymous hợp lệ; hai ví dụ sau có thể là **dữ liệu thiếu hoặc sai hợp đồng** nếu actorRef bắt buộc khi actorType=user. Không biến null hoặc chuỗi rỗng thành actorRef="unknown" một cách vô điều kiện, vì nhiều sự kiện không liên quan có thể bị gom thành một chủ thể giả.

**Đừng dùng userRef="anonymous" rồi coi mọi khách chưa đăng nhập là cùng một người dùng.** Nếu cần phân tích hành vi anonymous, hãy dùng cơ chế nhận dạng/consent phù hợp và giảm dữ liệu, không tự tạo tracking ID bền vững trong logging.

## 6. Nên ghi gì và không nên ghi gì?

| Dữ liệu | Có nên ghi? | Điều kiện |
| --- | --- | --- |
| Request ID không phải bí mật | Thường có | Được tạo/validate, giới hạn độ dài |
| Event code và errorCode | Nên | Có schema ổn định |
| actorType (user/service/anonymous) | Thường hữu ích | Không suy đoán xác thực |
| actorRef nội bộ tối thiểu | Cân nhắc | Nhu cầu rõ, được phép xử lý, retention/ACL |
| tenantRef | Cân nhắc | Có giá trị điều tra và phân quyền truy cập log |
| User role ở dạng thô | Hạn chế | Dễ bộc lộ quyền nội bộ; chỉ trường tổng hợp cần thiết |
| Email, họ tên, điện thoại | Tránh theo mặc định | Chỉ khi thật sự cần và có cơ sở/quy trình phù hợp |
| JWT/access token, refresh token | **Không** | Đây là credential |
| Password, API key, session cookie | **Không** | Không có lý do logging chẩn đoán thông thường |
| Toàn bộ HTTP headers/body | **Không theo mặc định** | Dễ chứa bí mật và dữ liệu nhạy cảm |
| Hash trực tiếp của email | Không coi là ẩn danh | Có thể bị dò bằng từ điển |
| IP/user-agent | Cân nhắc rất kỹ | Có thể là dữ liệu nhận dạng; giới hạn mục đích và retention |
| Exception message/stack trace | Có chọn lọc | Cần kiểm tra rò rỉ thông tin và kích thước |

### “Mã tham chiếu” không tự là dữ liệu vô danh

Một actorRef có thể là khóa nối sang bảng người dùng. Người có quyền đối chiếu bảng đó vẫn nhận diện được cá nhân. Khi cần giảm khả năng liên kết, có thể dùng **pseudonymization có khóa**, tách quyền truy cập khóa và quản lý vòng đời; nhưng cách này phải được thiết kế theo nhu cầu pháp lý/bảo mật, không nên tùy tiện tính SHA-256(email) rồi gọi là anonymous.

### Giảm dấu vết khi không cần user context

Không phải mỗi dòng DEBUG của cache, mỗi health check hoặc metric đều cần actorRef. Chỉ gắn user context vào những event thực sự cần liên kết với hành động người dùng. Dữ liệu người dùng càng được sao chép rộng qua nhiều log store càng khó kiểm soát.

## 7. SLF4J MDC là gì?

**Mapped Diagnostic Context (MDC)** là API của SLF4J để lưu **các cặp key-value theo ngữ cảnh thực thi**, giúp nhiều lời gọi Logger có thể dùng cùng requestId/actorRef mà không cần truyền các giá trị này làm tham số vào từng lời gọi.

Ví dụ code trong một lớp đã có LOG:

~~~java
try (org.slf4j.MDC.MDCCloseable request =
         org.slf4j.MDC.putCloseable("requestId", "req-42");
     org.slf4j.MDC.MDCCloseable actor =
         org.slf4j.MDC.putCloseable("actorRef", "usr-7")) {

    LOG.info("event=profile.read outcome=success");
    LOG.warn("event=rate_limit.approaching remaining={}", 2);
}
~~~

Đây là **mảnh mã minh họa**, không phải chương trình hoàn chỉnh. **MDC.putCloseable** tạo một scope tiện lợi: khi thoát **try-with-resources**, resource được close và key tương ứng được **remove**. Điều này tránh để context của request trước tồn tại trên thread tái sử dụng.

**Quan trọng:** putCloseable **không phải một cơ chế tổng quát tự khôi phục mọi giá trị cũ** của cùng key khi lồng nhiều scope. Nếu đã có giá trị trước, cần tự snapshot/restore đúng hoặc dùng context wrapper được kiểm thử. Ví dụ độc lập ở mục sau tạo scope mới từ context rỗng.

### MDC nằm ở đâu trong pipeline?

~~~text
Request handler
  |
  +--> MDC.put("requestId", "req-42")
  +--> MDC.put("actorRef", "usr-7")
  |
  v
Business code -> LOG.info("event=profile.read")
  |
  v
SLF4J API -> Logback event
  |
  v
Encoder: %X{requestId}, %X{actorRef}
  |
  v
stdout/file/collector
  |
  v
Clear/restore MDC ở cuối scope
~~~

Một lỗi thường gặp: **MDC đã được set nhưng log không hiện actorRef**. Lý do là backend/encoder **chưa được cấu hình xuất trường đó**. MDC chỉ giữ dữ liệu ngữ cảnh; cách hiển thị do encoder/formatter quyết định.

### MDC là ThreadLocal hay global?

Với Logback Classic thông thường, MDC được quản lý theo context của **thread hiện tại**, không phải một biến global dùng chung toàn JVM. **Mỗi thread phải có context thích hợp**. Thread pool có thể tái sử dụng thread giữa nhiều request, nên phải dọn/khôi phục sau mỗi task.

MDC **không tự động truyền qua mọi ExecutorService, CompletableFuture, reactive pipeline hoặc luồng xử lý phân tán**. Một worker thread mới có thể không có actorRef; một worker được tái sử dụng có thể mang context cũ nếu code không dọn.

**Không dùng MDC làm nơi lưu data nghiệp vụ quan trọng.** Nếu logic chính cần actorRef/tenantRef, truyền chúng qua một request context hoặc security context **được xác minh**, không phụ thuộc vào cách backend logging giữ ThreadLocal.

## 8. Ví dụ chạy được — Java 17 + SLF4J + Logback + ExecutorService

Ví dụ này chứng minh bốn điều:

1. Lệnh log trong request nhìn thấy user context qua MDC.
2. Task chạy ở **thread pool không tự nhận MDC**; cần truyền snapshot nếu muốn log có cùng context.
3. Code worker phải **restore context có trước task** ở khối finally.
4. Sau khi đóng scope, các log tiếp theo **không bị gắn nhầm user**.

### 8.1. Cấu trúc dự án

~~~text
user-context-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── UserContextDemo.java
        └── resources/
            └── logback.xml
~~~

### 8.2. Tạo pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>user-context-demo</artifactId>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.UserContextDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các phiên bản là **bộ phiên bản cụ thể phục vụ bài học**, không phải tuyên bố mới nhất. Khi triển khai thực tế, kiểm tra phiên bản tương thích, security advisory và dependency management, tránh nhiều SLF4J provider cùng lúc.

### 8.3. Tạo src/main/resources/logback.xml

~~~xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | requestId=%X{requestId} actorRef=%X{actorRef} | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

Trong Logback, **%X{requestId}** lấy giá trị requestId từ MDC của logging event, **%X{actorRef}** lấy actorRef. Khi key chưa được đặt, converter này xuất **chuỗi rỗng** theo cấu hình ở ví dụ.

Để output ổn định, pattern cố ý **không in timestamp hoặc thread name**. Trong production, nên có timestamp có timezone, service, level, tên logger, event và correlation ID theo schema; không bỏ thời gian chỉ vì test snapshot dễ hơn.

### 8.4. Tạo src/main/java/demo/UserContextDemo.java

~~~java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class UserContextDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(UserContextDemo.class);

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {

        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            LOG.info("event=system.ready");

            try (MDC.MDCCloseable request =
                         MDC.putCloseable("requestId", "req-42");
                 MDC.MDCCloseable actor =
                         MDC.putCloseable("actorRef", "usr-7")) {

                LOG.info("event=profile.read outcome=success");

                // Chụp bản sao MDC trên thread gọi submit.
                Map<String, String> context =
                        MDC.getCopyOfContextMap();

                executor.submit(() -> {
                    // Lưu context trước đó của worker thread.
                    Map<String, String> previous =
                            MDC.getCopyOfContextMap();
                    try {
                        // Context không tự truyền qua thread pool.
                        if (context == null) {
                            MDC.clear();
                        } else {
                            MDC.setContextMap(context);
                        }

                        LOG.info("event=audit.enqueued outcome=success");
                    } finally {
                        // Quan trọng khi thread này được tái sử dụng.
                        if (previous == null) {
                            MDC.clear();
                        } else {
                            MDC.setContextMap(previous);
                        }
                    }
                }).get();
            }

            // Cùng worker thread, sau khi task trước đã restore.
            executor.submit(() ->
                    LOG.info("event=worker.idle")).get();

            // Main thread đã đóng request/actor MDC scope.
            LOG.info("event=request.closed");
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Chương trình dùng **Java 17** và chỉ các API thông dụng. **Future.get()** đợi task thứ nhất hoàn tất trước khi tiếp tục, nên thứ tự các dòng log trong ví dụ là xác định. ExecutorService được shutdown trong finally.

### 8.5. Biên dịch và chạy

Trong thư mục **user-context-demo**, yêu cầu JDK 17+, Maven và dependency tải được hoặc đã có trong Maven cache:

~~~bash
mvn -q compile exec:java
~~~

**Stdout do chương trình Java phát ra với đúng logback.xml nêu trên** (không tính output riêng của Maven hoặc môi trường):

~~~text
INFO | requestId= actorRef= | event=system.ready
INFO | requestId=req-42 actorRef=usr-7 | event=profile.read outcome=success
INFO | requestId=req-42 actorRef=usr-7 | event=audit.enqueued outcome=success
INFO | requestId= actorRef= | event=worker.idle
INFO | requestId= actorRef= | event=request.closed
~~~

Không có log DEBUG, ERROR hay stack trace vì chương trình không phát các sự kiện đó. Các dòng trống ở requestId/actorRef thể hiện **MDC key chưa được đặt**; production nên có quy tắc rõ ràng cho missing field, ví dụ vắng mặt thay vì key rỗng khi xuất JSON.

### 8.6. Giải thích output

1. **system.ready** chạy trước khi vào MDC scope, nên cả hai field trống.
2. **profile.read** chạy trên main thread sau khi set MDC, nên có req-42 và usr-7.
3. **audit.enqueued** chạy trong worker thread: code đã **copy context** trên main, **setContextMap(context)** trong worker, rồi log.
4. **finally** trong worker **restore previous**. Với executor mới của demo, previous thường null nên MDC được clear.
5. **worker.idle** chạy sau task trước trên executor một thread; không còn actorRef/requestId, xác minh không rò context.
6. **request.closed** chạy sau khi hai MDCCloseable đóng trên main thread; context đã bị remove.
7. **shutdown()** yêu cầu executor ngừng nhận task mới; Future.get đã đợi các task submit hoàn tất.

Bài demo giữ actorRef và requestId là giá trị **giả lập không nhạy cảm**. Production không được copy toàn bộ MDC có thông tin nhạy cảm chỉ vì thuận tiện.

### 8.7. Những giới hạn của ví dụ

- Đây là **executor một thread** để kiểm tra rò context dễ hơn; đa luồng thực tế có nhiều task và error paths phức tạp hơn.
- Demo không có HTTP server, xác thực hay phân quyền. Nó chỉ chứng minh **gắn/propagate/clear logging context**.
- **MDC.putCloseable** remove key khi close, không tự restore giá trị cũ cùng key trong nested scope. Với framework có scope lồng nhau, cần chiến lược snapshot/restore.
- Mã worker restore toàn bộ **previous** để không ảnh hưởng task khác chạy trước trên cùng thread. Nếu chỉ gọi MDC.clear() mà bỏ qua previous thì có thể phá context hợp lệ trong các executor wrapping/lồng nhau.
- MDC không tự đi qua network tới service khác. Cần truyền correlation/trace context qua kênh đáng tin và thiết kế policy không mang thông tin cá nhân tùy tiện qua headers.
- **Logback pattern text** không tự thành JSON structured fields. Nếu hệ thống cần query actorRef/requestId theo field, dùng encoder JSON phù hợp và cấu hình collector.
- Đoạn code không dùng MDC làm security context, không quyết định cho phép đọc profile hay không.
- ConsoleAppender chỉ ghi stream; không bảo đảm sự kiện audit đã lưu bền vững. Dùng hệ audit riêng nếu có yêu cầu.

## 9. Tạo và dọn user context tại ranh giới HTTP

Một ứng dụng web thường cần gắn context **một lần ở điểm xử lý request**, thay vì đặt actorRef lại ở mọi service. Một flow đề xuất:

~~~text
HTTP request
    |
    v
Authentication filter / middleware
    |
    v
Xác nhận principal đáng tin
    |
    v
Tạo requestId và chọn context fields theo allowlist
    |
    v
MDC scope
    |
    v
Controller -> Service -> Repository -> Logger
    |
    v
finally: clear/restore MDC
~~~

Ví dụ **pseudocode** (không phải mã Java độc lập):

~~~java
// Pseudocode: principal được xác thực và requestId được tạo/kiểm tra
// theo cơ chế của framework. Không lấy actorRef từ header tùy ý.
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("requestId", trustedRequestId);
    MDC.put("actorType", authenticated ? "user" : "anonymous");

    if (authenticated) {
        MDC.put("actorRef", approvedActorRef);
    } else {
        MDC.remove("actorRef");
    }

    // frameworkFilterChain.doFilter(request, response);
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
~~~

Đây là pseudocode để thấy **cơ chế và vòng đời**; cần các biến/function do framework thực cung cấp. Trong code thật, có thể dùng servlet filter, interceptor, request scope hoặc cơ chế observation của framework. Việc lấy principal phải đặt **sau xác thực đáng tin** và chính sách exception dispatch/async phải được xử lý phù hợp.

**Tạo context nên là hành động có kiểm soát:**
- Lấy requestId từ lớp gateway/trace đã tin cậy, validate định dạng và độ dài.
- Lấy actorRef từ principal hoặc security service đã xác minh.
- Không đưa thẳng displayName, email hoặc roles/raw JWT vào MDC.
- Ghi actorType=anonymous nếu chưa xác thực, thay vì gán bừa một ID người dùng.
- Dọn context khi request kết thúc hoặc exception xảy ra.

### Cần gắn user context vào event nào?

Không nhất thiết mọi bản ghi trong JVM đều có actorRef. Nên xác định danh mục:

- Request nghiệp vụ: **requestId + actorType + actorRef khi có và được phép**.
- Event hệ thống: **service + event**; thường không có user.
- Job nền: **jobId + actorType=service** hoặc một tham chiếu đã được phê duyệt, không gán user của request đã kích hoạt job nếu không còn phù hợp.
- Audit có yêu cầu: actor/subject/tenantRef theo **hợp đồng audit riêng**, không dùng INFO console thay thế.

### Đừng lấy ngữ cảnh từ HTTP input không đáng tin

Một header kiểu **X-Actor-Id: admin** không phải chứng cứ người gửi là admin. Nếu đưa header đó vào MDC rồi sử dụng như danh tính, log có thể bị giả mạo. Nếu phải ghi một phần input chưa xác thực để điều tra tấn công, cần **gắn rõ là untrusted**, giới hạn kích thước/escaping và tránh nhầm với authenticated actor.

## 10. Anonymous, service principal, admin và delegated action

User context không chỉ là người đã đăng nhập trực tiếp.

| Tình huống | Context hợp lý | Điều cần giữ rõ |
| --- | --- | --- |
| Người dùng đã đăng nhập | actorType=user, actorRef=... | Actor lấy từ principal được xác thực |
| Truy cập ẩn danh | actorType=anonymous, không có actorRef | Không bịa ID người dùng |
| Scheduler/cron | actorType=service, actorRef=job-runner | Không gán người dùng cuối tùy ý |
| Service-to-service | actorType=service, actorRef=svc-payment | Service identity đáng tin, không dùng raw credential |
| Nhân viên hỗ trợ truy cập thay người dùng | actorRef=staffRef, subjectRef=customerRef | Ai làm và ai bị tác động là hai chủ thể khác nhau |
| Admin thao tác tenant khác | actorRef, tenantRef, subjectRef khi cần | Không trộn quyền và tenant của actor/subject |
| Job bắt đầu từ một request | jobId, correlationId, actorRef nếu chính sách cho phép | Mốc thời gian và ý nghĩa tác nhân phải rõ |

### Actor và subject

**Actor** là chủ thể thực hiện thao tác; **subject** là người/tài nguyên chịu tác động. Ví dụ nhân viên hỗ trợ cập nhật tài khoản hộ một khách hàng:

~~~json
{
  "event": "account.support_update",
  "actorType": "user",
  "actorRef": "staff-12",
  "subjectRef": "customer-8",
  "requestId": "req-900",
  "outcome": "success"
}
~~~

Đây là **dữ liệu minh họa**. Nếu chỉ ghi userId=customer-8 mà không phân biệt ai thao tác, log sẽ gợi ý sai rằng khách hàng tự thực hiện hành động.

**Impersonation/delegation** là tình huống nhạy cảm. Nếu có yêu cầu audit, cần sự kiện audit được xác minh và lưu bền vững theo chính sách, không dựa vào một chuỗi MDC có thể bị thay sai.

### Tenant context và multi-tenancy

Với hệ thống multi-tenant:

- tenantRef có thể giúp xác định request thuộc tenant nào.
- Không dùng tenantRef trong MDC để quyết định quyền truy cập DB; security/authorization phải xác minh riêng.
- Chỉ dùng tenant được xác thực hoặc được suy ra đáng tin, không nhận trực tiếp từ một header tùy ý.
- Log của tenant này không nên bị lộ cho tenant khác vì dashboard, search hoặc ACL cấu hình sai.
- Không gắn thông tin tenant nhạy cảm vào mọi event nếu không cần.

## 11. Async task, thread pool và CompletableFuture

MDC thường gắn với thread hiện tại, còn thread pool tái sử dụng worker. Nếu một request submit task rồi kết thúc, việc chạy task có thể diễn ra **sau** khi request scope đã đóng. Do đó:

1. **Snapshot context tại thời điểm submit**, chỉ giữ allowlist giá trị cần thiết.
2. Trên worker, **lưu previous context**.
3. **Set hoặc clear** context đúng cho task.
4. Chạy công việc trong try.
5. **Restore previous trong finally**, kể cả khi công việc ném exception.
6. Không giữ reference tới request object, principal, HTTP headers hoặc token chỉ để log một task.
7. Không giả định snapshot context là bằng chứng quyền còn hợp lệ tại lúc task chạy.

Mảnh wrapper tổng quát:

~~~java
// Mảnh mã minh họa: snapshot chứa các field đã qua allowlist.
Runnable wrapWithMdc(Runnable task, Map<String, String> snapshot) {
    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (snapshot == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(snapshot);
            }
            task.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    };
}
~~~

Đoạn trên là **method minh họa** cần import java.util.Map và org.slf4j.MDC, được đặt trong một lớp. Với hệ thống thật, nên dùng thư viện/framework hỗ trợ context propagation, tránh tự bọc không thống nhất ở nhiều module.

**CompletableFuture.supplyAsync(...)** có thể chạy ở common pool hoặc executor đã chỉ định. Nó **không tự mang MDC của caller** trong mọi runtime. Reactor, servlet async và message consumer có cơ chế context riêng; cần dùng giải pháp phù hợp framework.

### Bảo mật khi truyền user context

Sao chép **toàn bộ MDC** có thể mang theo field do một thư viện khác đặt vào, kể cả dữ liệu không nên gửi tới worker. Trong production, ưu tiên **chỉ truyền các key được phê duyệt**, chẳng hạn requestId, traceId và actorRef khi có cơ sở rõ ràng; cân nhắc không truyền actorRef qua những task không liên quan trực tiếp đến người dùng.

**Không dùng bản snapshot MDC để thực hiện authorization.** Tại lúc xử lý task, quyền của người dùng có thể thay đổi hoặc phiên đăng nhập đã hết hạn. Quyết định bảo mật cần được xác minh bằng cơ chế đáng tin tương ứng.

## 12. SLF4J MDC, Log4j ThreadContext và JUL có giống nhau không?

| Hệ logging | Context API điển hình | Ghi chú |
| --- | --- | --- |
| **SLF4J + Logback** | org.slf4j.MDC | Dùng qua provider; Logback thường lưu context theo thread |
| **Log4j 2** | org.apache.logging.log4j.ThreadContext | Có khái niệm context map/stack và cấu hình riêng |
| **JUL (java.util.logging)** | Không có MDC chuẩn tương đương trực tiếp | Có thể dùng LogRecord parameters/custom Formatter hoặc abstraction riêng |

Không nhầm các API này:

- **SLF4J Logger** không phải **java.util.logging.Logger**.
- **MDC** là API context phục vụ logging, không phải database session hoặc security principal.
- **ThreadContext** của Log4j 2 có cú pháp/behavior riêng, không thể copy nguyên XML Logback sang cấu hình Log4j 2.
- **JUL LogRecord.setParameters(...)** không phải MDC tự động cho toàn bộ request. Nếu dùng, phải có hợp đồng riêng cho cách Formatter hiểu parameters.

Khi tích hợp framework, cần xác định ai sở hữu context: ứng dụng, web filter, framework observation/tracing, task decorator hoặc một thư viện chung. Không có một cấu hình tự động phù hợp cho mọi môi trường.

## 13. Structured logging: đưa user context thành field truy vấn được

Một pattern text của Logback:

~~~xml
<pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level requestId=%X{requestId} actorRef=%X{actorRef} %logger - %msg%n</pattern>
~~~

có thể hữu ích cho con người, nhưng **text key=value không tự biến thành structured fields ở collector**. Nếu message chứa newline hoặc dấu bằng, parser đơn giản có thể hiểu sai.

Một object JSON phù hợp hơn cho hệ thống truy vấn field:

~~~json
{"timestamp":"2026-11-09T10:15:00.125Z","level":"INFO","service":"profile-api","event":"profile.read","requestId":"req-42","actorType":"user","actorRef":"usr-7","outcome":"success"}
~~~

Trong production:

- Để backend/encoder lấy **level, timestamp, logger và MDC** từ logging event, không nhập tay các trường này ở mọi lời gọi.
- Dùng JSON encoder có escaping đúng; mỗi event trên một dòng vật lý nếu collector nhận JSON Lines.
- Bảo đảm **requestId, actorRef và actorType** được map đúng tên/kiểu, không tạo duplicate key giữa MDC và event payload.
- Kiểm tra **null/missing**: khi anonymous, không bắt buộc ghi actorRef rỗng; schema nên cho phép field vắng mặt.
- Có **schemaVersion** hoặc chiến lược tương thích nếu tên trường, kiểu hoặc ý nghĩa thay đổi.
- Giới hạn log size và cách ghi exception/stack trace.
- Kiểm tra collector thực sự parse và lập chỉ mục những field được phép, không chỉ lưu raw JSON string.

### SLF4J 2 fluent API

Ngoài MDC, một event có thể mang thuộc tính **chỉ áp dụng cho lời gọi đó**:

~~~java
// Mảnh minh họa trong lớp có LOG và biến actorRef.
LOG.atInfo()
        .addKeyValue("event", "profile.read")
        .addKeyValue("actorRef", actorRef)
        .addKeyValue("outcome", "success")
        .log("Profile read completed");
~~~

Đây **không phải chương trình độc lập**. SLF4J 2.x cung cấp key-value API, nhưng **không bảo đảm mọi backend/encoder xuất chúng thành JSON hoặc collector index đúng**. MDC phù hợp với context dùng cho nhiều event của một scope; event key-value phù hợp với thuộc tính cục bộ của một sự kiện. Cần chọn schema sao cho không có key trùng hoặc bất nhất.

## 14. User context và distributed tracing

Một request đi qua API gateway, profile service và audit service có thể cần traceId/spanId để liên kết sự kiện. User context không thay thế tracing:

~~~text
Gateway       -> traceId=trace-a, spanId=span-1
Profile API   -> traceId=trace-a, spanId=span-2
Audit worker  -> traceId=trace-a, spanId=span-3
~~~

Cùng traceId có thể có nhiều span; requestId có thể là ID do gateway tạo, tùy kiến trúc. Những trường này phục vụ tương quan **luồng thực thi**, còn actorRef mô tả **chủ thể** của hoạt động.

Nếu tích hợp OpenTelemetry hoặc hệ tương tự, có thể dùng context propagation được framework hỗ trợ để truyền trace/span context. **Không nên tự đưa email, token, userId thô vào trace baggage**: baggage có thể đi qua boundary mạng và tiếp cận các service không cần biết danh tính.

### Khi nào cần truyền actorRef qua service?

Không phải lúc nào cũng cần. Một service có thể chỉ cần traceId/requestId để điều tra; việc ghi actorRef ở service nhận có thể làm tăng bề mặt dữ liệu cá nhân. Nếu cần chia sẻ actor identity để audit hoặc nghiệp vụ, phải dùng **cơ chế xác thực/ủy quyền tin cậy**, không lấy giá trị trong baggage/logging header làm chứng cứ.

## 15. Bảo mật user context và quyền truy cập log

User context đặc biệt nhạy cảm vì nó làm log có thể liên kết trực tiếp tới một cá nhân hoặc tài khoản. Những quy tắc nên áp dụng:

- Chỉ ghi field có **mục đích đã được xác định** và thực sự hữu ích cho điều tra.
- Áp dụng **allowlist** thay vì dump principal, JWT, session hoặc toàn bộ HTTP headers.
- **Không ghi credential** ở bất kỳ level nào, kể cả DEBUG.
- Kiểm tra **quyền đọc** log theo service, team, tenant, môi trường và loại dữ liệu.
- Áp dụng **retention**, xóa dữ liệu và quy trình xử lý yêu cầu dữ liệu theo chính sách.
- Giới hạn việc truy vấn hàng loạt theo actorRef nếu có nguy cơ lạm dụng dữ liệu.
- **Masking, pseudonymization và tokenization** phải được thiết kế và kiểm chứng, không coi việc đổi tên key là bảo vệ dữ liệu.
- Kiểm soát log injection bằng encoder xử lý newline, quote và control characters.
- Không log raw profile payload, email hoặc toàn bộ roles/permissions vì dễ phơi bày nhiều thông tin.
- Kiểm tra cấu hình export sang collector, SIEM hoặc nền tảng giám sát bên ngoài, vì log có thể rời môi trường ứng dụng.
- Tách **audit security events** khỏi log chẩn đoán best effort nếu có yêu cầu tính toàn vẹn, retention hoặc lưu bền vững cao hơn.

**User context có thể làm dữ liệu trở nên nhạy cảm hơn dù từng field riêng lẻ có vẻ vô hại.** Kết hợp thời điểm, IP, actorRef, tenantRef và event có thể suy ra hành vi. Cần áp dụng nguyên tắc giảm dữ liệu và quyền truy cập nhỏ nhất.

## 16. User context và hiệu năng

MDC đơn giản thường có chi phí vừa phải, nhưng không có nghĩa có thể ghi vô hạn field và log mọi hành động. Các điểm cần cân nhắc:

1. **Số key trong MDC:** càng nhiều field càng tăng chi phí copy/context propagation và độ khó quản trị.
2. **Số event:** ghi LOG.info cho mỗi phần tử trong vòng lặp tải cao có thể tạo log storm.
3. **Kích thước field:** không đặt JSON profile hoặc toàn bộ JWT vào MDC.
4. **AsyncAppender/queue:** việc chuyển event qua queue có thể liên quan snapshot context, chính sách drop và lifecycle.
5. **Field cardinality:** actorRef thường có rất nhiều giá trị khác nhau; lưu/index mọi giá trị có chi phí.
6. **Correlation với metrics:** không dùng actorRef/requestId duy nhất làm metric label không giới hạn.
7. **Tần suất tạo context:** tạo một scope ở ranh giới request thay vì set/remove lặp lại tại mọi method.

Nếu cần số lượng request, tỷ lệ lỗi hoặc latency, **metrics** phù hợp hơn việc phát một loạt log số đếm; **tracing** phù hợp với đường đi qua nhiều dịch vụ. Log có user context hữu ích để điều tra các event cụ thể, nhưng không thay thế toàn bộ hệ quan sát.

## 17. Vấn đề đồng thời và cleanup thường gặp

| Lỗi | Biểu hiện | Khắc phục |
| --- | --- | --- |
| Không remove MDC sau request | Log request B có actorRef của A | try/finally hoặc scope wrapper |
| Set MDC ở main rồi nghĩ executor nhận được | Worker log thiếu user context | Snapshot tại submit và set trong worker |
| Chỉ MDC.clear() khi kết thúc wrapper lồng | Làm mất context hợp lệ của scope ngoài | Snapshot/restore previous |
| putCloseable lồng trên cùng key, nghĩ nó tự restore | Giá trị trước bị mất khi close | Tự quản lý nested scope |
| Ghi email/raw token vào MDC | Dữ liệu nhạy cảm lan qua nhiều log | Allowlists, actorRef tối thiểu |
| Lấy actorRef trực tiếp từ X-User-Id | User có thể giả mạo identity trong log | Dùng principal đã xác minh |
| MDC được set nhưng encoder không in | Không truy vấn được actorRef | Cấu hình pattern/JSON encoder |
| Chuyển toàn bộ MDC sang mọi service | Dữ liệu cá nhân lan không cần thiết | Chỉ propagate field được phép |
| Dùng MDC để quyết định quyền | Rủi ro authorization bypass | Security context độc lập |
| Dùng actorRef cho mọi anonymous request | Nhiều khách bị gộp một định danh giả | actorType=anonymous, actorRef vắng mặt |
| Đồng nhất actorRef với subjectRef | Log sai người thực hiện | Phân biệt actor và subject |
| Đổi key userId thành actorRef không migration | Query/dashboard cũ thiếu kết quả | Schema versioning và kiểm thử |
| Dùng actorRef làm metric label | Cardinality tăng | Không dùng ID riêng lẻ làm metric dimension |
| Để user context trong log quá lâu | Rủi ro privacy/retention | Chính sách thời gian lưu và ACL |
| Không xử lý exception trong scope | MDC leak khi flow lỗi | finally, đóng scope chắc chắn |
| Cùng request xử lý async sau khi kết thúc HTTP | Context sai hoặc hết giá trị | Context propagation có kiểm soát |

## 18. Quy trình điều tra khi user context không đúng

Khi một log có actorRef sai hoặc thiếu:

1. **Xác nhận event phát từ đâu:** HTTP request, scheduler, queue consumer hay background job?
2. **Kiểm tra điểm xác thực:** actorRef đến từ principal đã xác minh hay nguồn bên ngoài không tin cậy?
3. **Tìm scope MDC:** key được put trước khi gọi Logger chưa?
4. **Kiểm tra ranh giới thread:** có ExecutorService, CompletableFuture, virtual thread hoặc reactive pipeline không?
5. **Kiểm tra copy/restore:** worker có mang context cũ từ task trước không?
6. **Xem encoder:** Logback pattern/JSON encoder có thực sự lấy key từ MDC không?
7. **Kiểm tra appender/filter:** event có bị chặn theo level, route sang backend khác hoặc bị nhân đôi không?
8. **Xem requestId/traceId:** các log liên quan có cùng correlation ID không?
9. **Xem trường actor/subject/tenant:** có bị ghi nhầm người thực hiện với đối tượng chịu tác động không?
10. **Kiểm tra privacy:** có giá trị email/token/raw claim bất ngờ xuất trong MDC hoặc message không?
11. **Kiểm tra collector:** field có bị rename, overwrite hoặc parse sai kiểu không?
12. **Xác nhận bằng test:** chạy hai request khác actorRef trên cùng thread pool và kiểm tra không lẫn giá trị.

**Không thấy actorRef không đủ để kết luận request anonymous.** Đó có thể là lỗi tạo context, propagation hoặc encoder. Khi cần phân biệt, đặt actorType=anonymous rõ ràng tại điểm đã xác minh trạng thái.

## 19. Kiểm thử user context

Các tình huống nên đưa vào test tự động:

- **Authenticated request:** actorType=user và actorRef đúng tham chiếu được phép.
- **Anonymous request:** actorType=anonymous, không tạo ID người dùng giả.
- **Service principal:** actorType=service và ID service hợp lệ.
- **User context cleanup:** request A và B chạy liên tiếp trên cùng thread không thấy actorRef lẫn nhau.
- **Exception path:** khi controller/service ném lỗi, finally vẫn dọn/restore MDC.
- **Executor propagation:** task trong worker nhìn thấy đúng snapshot được phép.
- **Executor isolation:** task kế tiếp không mang context của task trước.
- **Nested scope:** restore previous đúng khi scope ngoài còn tồn tại.
- **Impersonation/delegation:** actorRef và subjectRef phân biệt; không dùng userId mơ hồ.
- **Multi-tenant:** tenantRef không bị trộn hoặc rò giữa tenant.
- **JSON output:** requestId/actorRef thành field truy vấn được, không chỉ là text trong message.
- **Security:** test không xuất token, password, email/phone khi bị cấm, kể cả Throwable.
- **Cardinality và kích thước:** key allowlist, độ dài actorRef và retention phù hợp.
- **Unknown/missing:** missing actorRef có ngữ nghĩa theo schema, không tự biến thành "anonymous".
- **Compatibility:** nếu đổi tên field phải kiểm tra query/alert ở collector.

### Cách kiểm tra bằng output demo

Trong ví dụ Java 17 ở mục 8, quan sát:

- Hai dòng **profile.read** và **audit.enqueued** có requestId=req-42 actorRef=usr-7.
- Dòng **worker.idle** không còn context đó, dù cùng executor đã chạy task trước.
- Dòng **request.closed** cũng không còn context trên main thread.

Đó là **bằng chứng tối thiểu cho một luồng chạy cụ thể**, không phải khẳng định toàn hệ thống đã hoàn toàn thread-safe hoặc mọi async framework đã tự truyền context.

## 20. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** User context có phải toàn bộ hồ sơ người dùng được ghi vào log không?

**Đáp án:** Không. Chỉ nên ghi các trường tối thiểu, được phép và có ích cho điều tra, ví dụ actorType, actorRef và requestId.

**Câu 2.** Có thể dùng MDC.get("actorRef") để cấp quyền truy cập database không?

**Đáp án:** Không. MDC là context cho logging, không phải nguồn xác thực/phân quyền đáng tin. Quyền phải được xác minh bằng security context và policy riêng.

**Câu 3.** Một request anonymous nên có actorRef="anonymous" như ID của người dùng không?

**Đáp án:** Không nên coi giá trị đó là một người dùng. Có thể dùng actorType=anonymous và không có actorRef.

**Câu 4.** Khi dùng SLF4J MDC, tại sao task trong ExecutorService không tự có context?

**Đáp án:** MDC của Logback thông thường gắn với thread; worker thread của pool khác caller. Cần snapshot/propagate/restore có kiểm soát.

**Câu 5.** Vì sao code wrapper phải restore previous MDC trong finally thay vì chỉ clear tất cả?

**Đáp án:** Để tránh rò context và đồng thời không xóa context hợp lệ của scope trước đó nếu worker có wrapper/nested task.

**Câu 6.** MDC.putCloseable tự restore giá trị cũ của cùng key khi lồng scope không?

**Đáp án:** Không. Nó đóng scope bằng cách remove key; nested scope cần snapshot/restore hoặc abstraction phù hợp.

**Câu 7.** Request ID và actorRef có giống nhau không?

**Đáp án:** Không. Request ID đại diện một luồng yêu cầu; actorRef đại diện chủ thể. Một actor có thể thực hiện nhiều request.

**Câu 8.** Nếu nhân viên hỗ trợ chỉnh dữ liệu hộ khách hàng, actor và subject là ai?

**Đáp án:** Actor là nhân viên đã thực hiện; subject là khách hàng/tài khoản bị tác động. Nên dùng field khác nhau khi có yêu cầu lưu.

**Câu 9.** Ghi userId nội bộ thay email có tự biến log thành ẩn danh không?

**Đáp án:** Không. ID vẫn có thể liên kết tới cá nhân; cần policy và kiểm soát truy cập/retention.

**Câu 10.** Có thể copy toàn bộ JWT claims vào MDC rồi đẩy qua queue cho tiện không?

**Đáp án:** Không. Claims có thể chứa bí mật hoặc thông tin nhạy cảm; chỉ chọn field an toàn cần thiết, không chuyển raw token.

**Câu 11.** Đặt MDC mà output không có actorRef có thể do đâu?

**Đáp án:** Encoder chưa xuất key đó, scope chưa được set đúng thread, context bị dọn, hoặc collector không parse/truy vấn field.

**Câu 12.** MDC có tự truyền qua network sang microservice khác không?

**Đáp án:** Không. Cần cơ chế truyền trace/correlation context phù hợp và không sử dụng header logging như bằng chứng xác thực.

**Câu 13.** Có nên dùng actorRef làm metric label để thống kê request từng người không?

**Đáp án:** Thường không. Nó tạo cardinality cao, tăng chi phí và rủi ro privacy; metrics nên dùng các chiều có số lượng giá trị hữu hạn.

**Câu 14.** Nếu log sự kiện audit cần bền vững, ConsoleAppender và actorRef có đủ không?

**Đáp án:** Không. Logging chẩn đoán có thể bị lọc, drop hoặc lưu không bền vững; cần audit storage với hợp đồng riêng nếu bắt buộc.

**Câu 15.** Trong Java 17 demo, vì sao worker.idle không in usr-7?

**Đáp án:** Task audit.enqueued đã restore previous MDC trong finally; worker được tái sử dụng nhưng không còn giữ context của request trước.

## 21. Tổng kết

**User context trong logging là cách gắn thông tin tối thiểu về chủ thể của sự kiện để điều tra và tương quan log, không phải cách lưu hồ sơ người dùng hay thay thế hệ thống bảo mật.**

Một thiết kế tốt phải đồng thời đảm bảo:

1. **Đúng chủ thể:** phân biệt actor, subject, service và anonymous.
2. **Đúng thời điểm và scope:** tạo context sau xác thực đáng tin, dọn/restore trong finally.
3. **Đúng luồng thực thi:** snapshot/propagate MDC khi chuyển thread, không giả định ThreadLocal tự lan.
4. **Đúng schema:** requestId, actorType, actorRef, tenantRef/traceId khi cần, output bằng encoder có thể truy vấn.
5. **Đúng chính sách bảo mật:** không ghi credential, không thu thập PII không cần thiết, kiểm soát quyền truy cập và retention.
6. **Đúng ranh giới trách nhiệm:** MDC phục vụ log; security context phục vụ quyền; audit store phục vụ yêu cầu lưu bền vững nếu có.

Khi áp dụng các nguyên tắc đó, log Java cung cấp được bối cảnh đủ để điều tra sự cố mà vẫn hạn chế rò rỉ dữ liệu và tránh lẫn thông tin giữa các request hoặc thread.
