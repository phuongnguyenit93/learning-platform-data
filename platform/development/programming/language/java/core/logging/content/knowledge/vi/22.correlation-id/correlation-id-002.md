# Tạo correlation ID trong Java — Sinh, xác thực và truyền xuyên request

## Mục tiêu học tập

Trong hệ thống Java gồm nhiều lớp, thread và microservice, một HTTP request có thể tạo ra hàng chục dòng log. Khi nhiều request chạy cùng lúc, timestamp và tên thread không đủ để biết những dòng nào thuộc cùng một luồng xử lý. **Correlation ID** là một định danh được gắn với yêu cầu hoặc chuỗi thao tác để có thể **liên kết các logging event từ đầu đến cuối**.

Bài học thuộc nhóm **Correlation ID** của **Java Core Logging**, với đề mục trực tiếp **“Tạo correlation ID”**. Sau khi học, bạn có thể:

- Quyết định **khi nào sinh ID mới, khi nào giữ ID được truyền tới**, dựa trên chính sách trust boundary.
- Sinh ID bằng **UUID.randomUUID()** trong Java 17; hiểu ưu và nhược điểm của UUID v4, ID do gateway cấp và định danh dạng chuỗi tùy chỉnh.
- Kiểm tra header **X-Correlation-ID**: số lượng giá trị, kiểu ký tự, độ dài, tính hợp lệ, nguồn tin cậy; không dùng raw input để đưa thẳng vào log.
- Gắn ID vào **SLF4J MDC** và trả/lan truyền qua HTTP response, downstream request hoặc message headers.
- Hiểu vì sao MDC không tự truyền qua thread pool và vì sao cần remove hoặc restore ở cuối scope.
- Phân biệt **correlation ID**, **request ID**, **trace ID**, **span ID** và **idempotency key**.
- Chạy một ví dụ **Java 17 + HttpServer + HttpClient + Logback** đã kiểm thử: giữ ID hợp lệ, sinh UUID v4 cho ID thiếu/sai định dạng, truyền tới downstream và kiểm tra log.
- Thiết kế QA, privacy/security và observability phù hợp với ứng dụng nhiều service.

**Trọng tâm của bài:** correlation ID có ý nghĩa khi nó được **tạo tại đúng ranh giới**, **được truyền nhất quán**, **được log đúng phạm vi**, và **không rò sang request khác**. Chỉ gọi UUID.randomUUID() mà không có quy trình trên chưa tạo nên một giải pháp correlation hoàn chỉnh.

## 1. Correlation ID là gì?

Correlation ID là một **giá trị nhận diện dùng để liên kết các sự kiện thuộc cùng một luồng xử lý**, ví dụ một request từ gateway qua service A, service B và hệ thống dữ liệu. ID thường là chuỗi ngắn, ổn định trong phạm vi nghiệp vụ được chọn.

Ví dụ trước khi có ID:

~~~text
INFO event=api.received
INFO event=downstream.received
WARN event=inventory.retry
INFO event=api.completed
~~~

Với nhiều request đồng thời, các dòng này dễ xen kẽ. Sau khi gắn ID:

~~~text
correlationId=client-17 | event=api.received
correlationId=client-17 | event=downstream.received
correlationId=client-17 | event=api.completed
correlationId=client-18 | event=api.received
~~~

Nhờ cùng **correlationId=client-17**, ta biết ba dòng đầu cùng thuộc một luồng xử lý được liên kết. **Không được kết luận request thành công chỉ dựa trên việc có ID**: phải xem status, exception, sự kiện kết thúc và dữ liệu nghiệp vụ tương ứng.

Trong nhiều hệ thống, **request ID** được dùng gần giống correlation ID. Tuy nhiên, có kiến trúc cấp một request ID riêng cho mỗi HTTP hop, trong khi correlation ID giữ nguyên suốt workflow. Vì vậy cần **định nghĩa phạm vi và tên header/field rõ ràng** trong thiết kế của tổ chức.

## 2. Vì sao phải tạo correlation ID?

Một ID hữu ích giải quyết nhiều tình huống:

1. **Tìm log theo một request:** tra tất cả log ứng với một ID thay vì lọc theo timestamp gần đúng.
2. **Đi qua nhiều service:** ID được truyền trong HTTP headers hoặc message metadata để mỗi service ghi cùng một giá trị.
3. **Trao đổi với bộ phận hỗ trợ:** có thể cho khách hàng biết một mã tra cứu sự cố không chứa thông tin nhạy cảm.
4. **Điều tra retry:** nhiều lần gọi downstream có thể được gắn với cùng request/workflow khi đó là chính sách tương quan.
5. **Phân tích lỗi bất đồng bộ:** nếu truyền context đúng cách, worker task có thể ghi log cùng ID.
6. **Tách log đồng thời:** hai request chạy trên cùng thread pool không bị gộp nhầm khi ID được dọn đúng lúc.

Nhưng correlation ID **không tự bảo đảm tính duy nhất toàn vũ trụ, không phải token xác thực, không phải transaction ID có tính pháp lý và không phải một distributed trace**. Nếu người dùng được quyền gửi ID, họ có thể cố tình gửi cùng một ID cho nhiều request. Để phân biệt thực sự, cần chính sách nguồn tạo ID, trust boundary và thời điểm tái sinh.

## 3. Các cách sinh correlation ID

### Cách 1: UUID v4 bằng Java 17

API có sẵn trong JDK:

~~~java
import java.util.UUID;

String correlationId = UUID.randomUUID().toString();
System.out.println(correlationId);
~~~

Ví dụ một giá trị có dạng:

~~~text
6b1d2b4a-17be-49f5-b915-b9e54b32c3ea
~~~

Đây là **chuỗi minh họa**, không phải stdout cố định; mỗi lần gọi sẽ tạo giá trị khác theo cơ chế UUID ngẫu nhiên. **UUID v4** có 122 bit ngẫu nhiên trong định dạng UUID 128 bit do một số bit dành cho version/variant. Xác suất collision khi sinh đúng cách rất nhỏ ở quy mô ứng dụng thông thường, nhưng **không phải bảo đảm toán học tuyệt đối không trùng**.

Ưu điểm:
- Không cần database hay service trung tâm để cấp ID.
- Có API chuẩn trong JDK 17.
- Dễ truyền dưới dạng String trong HTTP header, message metadata, MDC và JSON field.
- Có định dạng quen thuộc với thư viện phân tích log.

Giới hạn:
- Chuỗi UUID có độ dài tương đối lớn.
- Không tự mang nghĩa thời gian/nhóm nghiệp vụ.
- Không thể dùng như bằng chứng danh tính của client.
- Không tự thực hiện validation, propagation hoặc cleanup.

### Cách 2: ID do trusted gateway cấp

Một **API gateway** hoặc ingress controller có thể là điểm quyết định ID của mọi yêu cầu. Khi đó service nội bộ nhận header do gateway đã kiểm tra/đặt lại, giữ nguyên ID theo hợp đồng và truyền tiếp xuống downstream.

Điều này giúp tập trung chính sách và tra cứu từ lớp ngoài cùng. Nhưng gateway chỉ có thể được tin cậy nếu **không có đường bypass tùy ý từ Internet đến service nội bộ** hoặc service vẫn thực thi kiểm tra nguồn phù hợp. **Header có vẻ hợp lệ không đồng nghĩa header đến từ gateway đáng tin**.

### Cách 3: Định danh dạng chuỗi hữu hạn theo quy ước riêng

Ví dụ **client-17**, **req_XY92f** hoặc ID sinh bởi hệ thống đã kiểm soát. Cần xác định:
- Tập ký tự và giới hạn độ dài.
- Chính sách tính duy nhất và thời gian sống.
- Ai được phát hành và ai có thể sửa.
- Cách xử lý duplicate hoặc missing.
- Khả năng truy vấn và rủi ro lộ thông tin.

Với ứng dụng mới, **UUID v4 là một lựa chọn mặc định thực dụng**. Nếu tổ chức đã có định dạng ID chuẩn, nên tuân thủ chuẩn đó thay vì tạo thêm một format mới không tương thích.

## 4. Quy tắc nhận header: giữ, thay mới hay từ chối?

Một HTTP request có thể chứa:

~~~http
GET /orders/42 HTTP/1.1
Host: example.test
X-Correlation-ID: client-17
~~~

Định dạng **X-Correlation-ID** là quy ước phổ biến nhưng **không phải chuẩn toàn cục bắt buộc**. Một số tổ chức dùng **X-Request-ID** hoặc tên khác. Hãy chọn một tên theo hợp đồng gateway/service và giữ nhất quán.

**Ba chiến lược thường gặp:**

| Trường hợp | Chính sách có thể chọn | Lưu ý |
| --- | --- | --- |
| Không có header | Sinh ID mới | Phải đưa ID vào logs và response/downstream nếu áp dụng |
| Header đúng cú pháp từ nguồn được phép | Có thể giữ nguyên | Nguồn tin cậy và định dạng phải được định nghĩa rõ |
| Header thiếu/không hợp lệ/quá dài | Sinh ID mới hoặc reject request theo hợp đồng | Không dùng raw input trực tiếp làm ID |
| Nhiều header cùng tên | Reject hoặc sinh ID mới | Tránh nhập nhằng nhiều giá trị |
| Header hợp lệ về cú pháp nhưng từ client chưa tin cậy | Có thể **luôn thay bằng server-generated ID** ở public ingress | Regex hợp lệ không chứng minh đáng tin |
| Header được proxy/gateway xác thực và cấp | Giữ nguyên theo chính sách nội bộ | Bảo đảm các đường đi không bypass trust boundary |

**Điểm bảo mật quan trọng:** hai câu hỏi độc lập là **cú pháp có hợp lệ không?** và **nguồn phát hành có đáng tin không?**. Regex chỉ giúp trả lời câu thứ nhất. Một client có thể gửi chuỗi rất đẹp nhưng cố tình tái sử dụng ID từ request khác, khiến việc phân tích log bị trộn.

Một chiến lược sản xuất hay dùng là **gateway luôn tạo ID ở ranh giới public**, ghi đè header client tự cung cấp, sau đó các service nội bộ tin vào ID do gateway phân phối qua kênh được kiểm soát. Một chiến lược khác có thể giữ ID an toàn của client để hỗ trợ end-to-end tracing của khách hàng, nhưng phải chấp nhận và xử lý nguy cơ collision/chồng chéo ID.

## 5. Kiểm tra format ID trước khi đưa vào logs

Để bài học có hành vi dễ lặp lại, ta dùng regex cho phép:
- Ký tự đầu là ASCII letter hoặc chữ số.
- Các ký tự sau là ASCII letter, chữ số, dấu gạch dưới hoặc gạch ngang.
- Tổng chiều dài từ 1 đến 64 ký tự.

~~~java
// Đoạn minh họa trong một lớp Java, không phải chương trình độc lập.
private static final java.util.regex.Pattern SAFE_ID =
        java.util.regex.Pattern.compile("[A-Za-z0-9][A-Za-z0-9_-]{0,63}");
~~~

Ví dụ:

| Giá trị | Kết quả validation |
| --- | --- |
| client-17 | Hợp lệ theo regex |
| a | Hợp lệ |
| 6b1d2b4a-17be-49f5-b915-b9e54b32c3ea | Hợp lệ |
| chuỗi rỗng | Không hợp lệ |
| bad id with spaces | Không hợp lệ |
| id có dấu xuống dòng | Không hợp lệ |
| ../secrets | Không hợp lệ |
| Chuỗi quá 64 ký tự | Không hợp lệ |
| Hai header X-Correlation-ID | Cần chính sách riêng; không chọn một giá trị ngẫu nhiên |

Đây là **quy tắc của ví dụ**, không phải định nghĩa chuẩn của mọi correlation ID. Nếu hệ thống chỉ chấp nhận UUID v4 canonical, validation có thể chặt hơn. Nếu framework cấp một ID khác, cần bảo đảm regex tương thích với định dạng mà framework thực sự tạo ra.

### Hàm chọn ID

~~~java
// Đoạn minh họa, dùng trong cùng lớp có SAFE_ID và import UUID.
private static String chooseId(java.util.List<String> values) {
    if (values != null && values.size() == 1
            && SAFE_ID.matcher(values.get(0)).matches()) {
        return values.get(0);
    }
    return java.util.UUID.randomUUID().toString();
}
~~~

Nếu có **đúng một giá trị hợp lệ**, demo giữ nguyên. Nếu thiếu/khác điều kiện, nó **sinh UUID v4**. Trong hệ thống public ingress không tin cậy, hãy thay nhánh nhận ID bằng việc **luôn sinh server ID** hoặc chỉ giữ khi thực sự được policy cho phép. Hàm này **không thực hiện xác thực danh tính/nguồn header**.

Kiểm tra cả **số lượng giá trị** rất quan trọng. Những proxy/framework có thể gộp nhiều header cùng tên thành một chuỗi chứa dấu phẩy; regex của ví dụ cũng không chấp nhận dấu phẩy. Tuy nhiên, hệ thống sản xuất phải hiểu cơ chế chuẩn hóa header của từng proxy/server trước khi thiết kế quyết định cuối cùng.

## 6. Luồng tạo và truyền ID qua các service

Một request đi qua API rồi downstream service:

~~~mermaid
flowchart LR
    A["Client gửi X-Correlation-ID?"] --> B["Ingress kiểm tra trust và format"]
    B --> C{"Có ID được chấp nhận?"}
    C -->|Có| D["Giữ ID"]
    C -->|Không| E["Sinh UUID v4"]
    D --> F["Đặt MDC correlationId"]
    E --> F
    F --> G["Ghi log API"]
    G --> H["HTTP call downstream + header"]
    H --> I["Downstream đặt MDC và ghi log"]
    I --> J["Trả response cùng ID theo policy"]
    J --> K["Dọn MDC ở cả hai scope"]
~~~

**Yêu cầu quan trọng:**

- **Tạo ID một lần cho phạm vi đã chọn**, không gọi UUID.randomUUID() ở mọi Logger.info.
- **Truyền cùng ID cho downstream** bằng header rõ ràng, không chỉ dựa vào MDC cục bộ.
- **Đặt ID vào MDC ở từng service**, vì MDC không tự truyền qua network.
- **Dọn MDC sau khi kết thúc xử lý**, kể cả khi có exception.
- **Trả ID trong response** nếu đó là hợp đồng API; không để dữ liệu không tin cậy hoặc giá trị nội bộ nhạy cảm bị echo.
- **Phân biệt retry:** nếu vẫn là cùng workflow/request đang retry một thao tác, thường giữ correlation ID; mỗi attempt có thể có trường attempt hoặc request-hop ID riêng.

Hệ thống chỉ dùng correlation ID để tìm log sẽ hữu ích nhất khi kết hợp với **service.name, timestamp, level, event name** và **status**, vì cùng ID có thể xuất ở nhiều service.

## 7. Ví dụ Java 17 hoàn chỉnh: HTTP API tự tạo và truyền correlation ID

Ví dụ dùng **Java 17**, **JDK HttpServer**, **HttpClient**, **SLF4J** và **Logback Classic**. Nó thực hiện ba request tự động:

1. **X-Correlation-ID: client-17** hợp lệ → giữ nguyên.
2. **X-Correlation-ID: bad id with spaces** không hợp lệ → sinh UUID v4.
3. Không có header → sinh UUID v4.

Mỗi request qua **/api**, được gọi tiếp qua **/downstream** với ID đã chọn. Các request chạy trong một tiến trình Java để tự kiểm thử dễ dàng; trong hệ thống thật, hai endpoint có thể nằm ở các service/host khác nhau.

**Cấu trúc dự án:**

~~~text
correlation-id-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── logging/
        │               └── CorrelationHttpDemo.java
        └── resources/
            └── logback.xml
~~~

### File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>correlation-id-demo</artifactId>
  <version>1.0</version>

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
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Đây là **bộ phiên bản cố định được thử nghiệm cho bài học**, không phải khẳng định các phiên bản mới nhất. Dependency logback-classic mang theo SLF4J API tương thích. Với dự án production, dùng BOM/dependencyManagement, kiểm tra CVE và chính sách cập nhật của tổ chức.

### File src/main/resources/logback.xml

~~~xml
<configuration>
  <appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>target/correlation-demo.log</file>
    <append>false</append>
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>correlationId=%X{correlationId:-missing} | %msg%n</pattern>
    </encoder>
  </appender>
  <root level="INFO"><appender-ref ref="FILE"/></root>
</configuration>
~~~

**PatternLayoutEncoder** xuất **correlationId** từ MDC bằng **%X{correlationId:-missing}**. Nếu không có context, fallback **missing** giúp phát hiện lỗi. **%msg** in nội dung event, **%n** xuống dòng. FileAppender được dùng để chương trình đọc lại log sau khi dừng context.

**append=false** chỉ phục vụ bài thực hành, bảo đảm mỗi lần chạy có file mới để đếm 9 record. Với production cần rotation/retention và không tự ghi đè file lịch sử; có thể dùng RollingFileAppender hoặc stdout/stderr theo kiến trúc vận hành.

### File src/main/java/com/example/logging/CorrelationHttpDemo.java

~~~java
package com.example.logging;

import ch.qos.logback.classic.LoggerContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class CorrelationHttpDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(CorrelationHttpDemo.class);
    private static final String HEADER = "X-Correlation-ID";
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9_-]{0,63}");
    private static final HttpClient CLIENT =
            HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

    private static String chooseId(List<String> values) {
        if (values != null && values.size() == 1
                && SAFE_ID.matcher(values.get(0)).matches()) {
            return values.get(0);
        }
        return UUID.randomUUID().toString();
    }

    private static void respond(HttpExchange exchange, int status,
                                String id, String body) throws IOException {
        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(HEADER, id);
        exchange.sendResponseHeaders(status, data.length);
        try (var stream = exchange.getResponseBody()) {
            stream.write(data);
        }
    }

    private static void handleDownstream(HttpExchange exchange)
            throws IOException {
        String id = chooseId(exchange.getRequestHeaders().get(HEADER));
        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("correlationId", id)) {
            LOG.info("event=downstream.received");
            respond(exchange, 200, id, "ok");
        } finally {
            exchange.close();
        }
    }

    private static void handleApi(HttpExchange exchange, int port)
            throws IOException {
        String id = chooseId(exchange.getRequestHeaders().get(HEADER));
        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("correlationId", id)) {
            LOG.info("event=api.received");

            HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:" + port + "/downstream"))
                    .timeout(Duration.ofSeconds(3))
                    .header(HEADER, id)
                    .GET()
                    .build();

            try {
                HttpResponse<String> next =
                        CLIENT.send(request,
                                HttpResponse.BodyHandlers.ofString());
                boolean same = next.statusCode() == 200
                        && id.equals(next.headers()
                                .firstValue(HEADER).orElse(""));
                if (!same) {
                    LOG.error("event=api.downstream_mismatch");
                    respond(exchange, 502, id, "bad gateway");
                    return;
                }
                LOG.info("event=api.completed");
                respond(exchange, 200, id, "ok");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                LOG.error("event=api.interrupted", e);
                respond(exchange, 503, id, "interrupted");
            }
        } finally {
            exchange.close();
        }
    }

    private static HttpResponse<String> invoke(String uri, String id)
            throws Exception {
        HttpRequest.Builder builder =
                HttpRequest.newBuilder(URI.create(uri))
                        .timeout(Duration.ofSeconds(3))
                        .GET();
        if (id != null) {
            builder.header(HEADER, id);
        }
        return CLIENT.send(
                builder.build(), HttpResponse.BodyHandlers.ofString());
    }

    private static String responseId(HttpResponse<String> response) {
        return response.headers().firstValue(HEADER).orElse("");
    }

    private static boolean canonicalUuid4(String id) {
        try {
            UUID uuid = UUID.fromString(id);
            return uuid.version() == 4
                    && uuid.toString().equals(id);
        } catch (IllegalArgumentException e) {
            return false;
        }
    }

    private static long countFor(List<String> lines, String id) {
        return lines.stream()
                .filter(s -> s.startsWith(
                        "correlationId=" + id + " | "))
                .count();
    }

    public static void main(String[] args) throws Exception {
        LoggerContext context =
                (LoggerContext) LoggerFactory.getILoggerFactory();
        ExecutorService workers =
                Executors.newFixedThreadPool(4);
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.setExecutor(workers);
        int port = server.getAddress().getPort();
        server.createContext("/api",
                exchange -> handleApi(exchange, port));
        server.createContext("/downstream",
                CorrelationHttpDemo::handleDownstream);

        HttpResponse<String> valid;
        HttpResponse<String> invalid;
        HttpResponse<String> missing;
        try {
            server.start();
            String api = "http://127.0.0.1:" + port + "/api";
            valid = invoke(api, "client-17");
            invalid = invoke(api, "bad id with spaces");
            missing = invoke(api, null);
        } finally {
            server.stop(0);
            workers.shutdown();
            if (!workers.awaitTermination(5, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
            context.stop();
        }

        String validId = responseId(valid);
        String invalidId = responseId(invalid);
        String missingId = responseId(missing);
        List<String> lines = Files.readAllLines(
                Path.of("target", "correlation-demo.log"),
                StandardCharsets.UTF_8);
        Set<String> ids =
                new HashSet<>(List.of(validId, invalidId, missingId));

        System.out.println("validStatus=" + valid.statusCode());
        System.out.println("validIdPreserved="
                + validId.equals("client-17"));
        System.out.println("invalidStatus=" + invalid.statusCode());
        System.out.println("invalidIdRegenerated="
                + canonicalUuid4(invalidId));
        System.out.println("missingStatus=" + missing.statusCode());
        System.out.println("missingIdGenerated="
                + canonicalUuid4(missingId));
        System.out.println("allIdsDistinct=" + (ids.size() == 3));
        System.out.println("logEvents=" + lines.size());
        System.out.println("validIdLogEvents="
                + countFor(lines, validId));
        System.out.println("invalidIdLogEvents="
                + countFor(lines, invalidId));
        System.out.println("missingIdLogEvents="
                + countFor(lines, missingId));
        System.out.println("noMissingMdc=" + lines.stream()
                .noneMatch(s ->
                        s.startsWith("correlationId=missing")));
    }
}
~~~

**Chạy ứng dụng** tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:exec "-Dexec.executable=java" "-Dexec.args=-classpath %classpath com.example.logging.CorrelationHttpDemo"
~~~

Maven Exec Plugin chạy **một JVM con** với classpath dự án, giúp không lẫn backend logging của Maven. Đây là mô phỏng local: server bind vào **127.0.0.1** tại cổng được hệ điều hành chọn bằng **port=0**; không cần mở cổng Internet hay dựng một server thực bên ngoài.

Nếu dùng JPMS với **module-info.java** thay vì classpath demo, còn phải khai báo các **requires/opens** phù hợp, trong đó module **jdk.httpserver** cho HttpServer. Đây là ví dụ classpath Maven nên không có module-info.java.

### Kết quả chạy đã kiểm thử

**Stdout chính xác** của chương trình thành công, không tính thông tin riêng của Maven:

~~~text
validStatus=200
validIdPreserved=true
invalidStatus=200
invalidIdRegenerated=true
missingStatus=200
missingIdGenerated=true
allIdsDistinct=true
logEvents=9
validIdLogEvents=3
invalidIdLogEvents=3
missingIdLogEvents=3
noMissingMdc=true
~~~

Đã biên dịch và chạy thành công trên JDK/Maven với dependency ở trên. Các giá trị UUID cụ thể thay đổi sau mỗi lần chạy; chương trình kiểm tra **dạng canonical UUID v4 và tính khác nhau** thay vì in một UUID cố định không đáng tin.

**Ví dụ bốn dòng đầu trong file log của một lần chạy:**

~~~text
correlationId=client-17 | event=api.received
correlationId=client-17 | event=downstream.received
correlationId=client-17 | event=api.completed
correlationId=5edc5388-3333-4122-a1de-3f6b83bd9a5b | event=api.received
~~~

UUID **5edc5388-...** chỉ là giá trị của **lần chạy đã kiểm thử**, không phải giá trị mà bạn luôn nhận được. Trong file thật có ba nhóm, **mỗi nhóm ba event**: api.received, downstream.received, api.completed. Vì demo gọi API tuần tự, nhóm tương ứng dễ quan sát; không giả định log production đa thread sẽ luôn được sắp xếp thành các nhóm liên tiếp.

### Giải thích sâu luồng code

1. **chooseId** kiểm tra đúng một header value bằng SAFE_ID; nếu thiếu hoặc sai định dạng, nó sinh UUID v4 bằng UUID.randomUUID().
2. **handleApi** nhận ID đã chọn, đặt MDC correlationId trước khi ghi event đầu.
3. Khi xây dựng HttpRequest tới **/downstream**, code **chủ động đưa ID vào header**. Đây là bước propagation qua HTTP, không phải hành vi tự động của MDC.
4. **handleDownstream** đọc header, đặt MDC riêng trong thread xử lý downstream và ghi event downstream.received.
5. **respond** trả X-Correlation-ID trong response để client và upstream có thể biết mã được chấp nhận/tạo mới.
6. **handleApi** xác nhận downstream trả status 200 và header ID trùng; nếu không, ghi lỗi và trả 502.
7. **MDC.putCloseable** dùng trong try-with-resources, nên key được remove khi scope kết thúc, kể cả với nhánh lỗi chạy qua scope.
8. **server.stop**, executor shutdown và **context.stop** được thực hiện trước khi đọc file; chương trình không tiếp tục phát business log sau khi context đóng.
9. **Files.readAllLines** đọc một JSON? Không: ví dụ này ghi **text log** qua PatternLayoutEncoder. countFor đối chiếu prefix correlationId theo định dạng đã cấu hình, không parse JSON.
10. **allIdsDistinct** kiểm tra ba request trong test này không trùng ID. Đây không phải chứng minh tuyệt đối rằng mọi UUID v4 trên thế giới sẽ không bao giờ collision.
11. **noMissingMdc** xác minh mọi event được đọc đều có ID trong phạm vi test; test thực tế cần đối chiếu thêm expected event ID và nhiều luồng bất đồng bộ.
12. **HttpServer** của JDK dùng executor nhiều thread; không phụ thuộc việc API và downstream có chạy trên cùng thread hay không, vì **header** là đường truyền ID, còn mỗi handler tự đặt MDC.

**Giới hạn của demo:** hàm chooseId cố ý giữ chuỗi client-17 nếu hợp lệ để minh họa ba nhánh. Đây **không phải một chính sách bảo mật hoàn chỉnh cho public ingress**. Trong service production, chỉ nên giữ ID theo chính sách trust boundary rõ ràng; nếu Internet client không đáng tin, gateway có thể luôn sinh ID mới, ghi đè header và chỉ service nội bộ sử dụng ID do gateway cấp.

## 8. Tại sao phải đặt correlation ID vào MDC?

**MDC — Mapped Diagnostic Context** là map key–value của logging context cho phép backend xuất field chung trên nhiều event. Với SLF4J:

~~~java
// Đoạn minh họa, LOG là org.slf4j.Logger đã khai báo.
try (org.slf4j.MDC.MDCCloseable scope =
             org.slf4j.MDC.putCloseable("correlationId", "client-17")) {
    LOG.info("event=request.started");
    LOG.info("event=request.finished status=200");
}
~~~

Khi Logback layout có **%X{correlationId}**, hai event trong scope có cùng ID mà không phải nối string vào từng message.

**Nguyên tắc lifecycle:**
- **Đặt** ID trước khi ghi log request.
- **Ghi log kết thúc** trong scope nếu muốn record kết thúc mang cùng ID.
- **Dọn key** ở cuối scope bằng remove/finally hoặc putCloseable.
- **Không dọn toàn bộ MDC tùy tiện** nếu framework sở hữu key khác như traceId.
- Nếu **ghi đè key đã có**, putCloseable chỉ remove key khi close; nó **không tự restore giá trị cũ**. Khi nested context cần khôi phục, chụp map và restore có chủ đích.

### MDC có tự truyền qua HTTP không?

**Không.** MDC trong Logback gắn với ngữ cảnh thực thi của thread/JVM, không phải network protocol. Dù API gọi downstream trong cùng method, service nhận không thể đọc MDC của service gửi qua HTTP. Cần đưa ID vào header hoặc message metadata rồi đặt MDC mới ở service nhận.

### MDC có tự truyền qua Executor không?

**Không được giả định.** Khi dùng ExecutorService, CompletableFuture, async servlet hoặc reactive pipeline, công việc có thể chạy trên thread khác. Cần cơ chế context propagation của framework hoặc snapshot/restore.

## 9. Truyền MDC sang worker thread đúng cách

Một ví dụ minh họa wrapper task với **SLF4J MDC**:

~~~java
// Đoạn minh họa: executor là ExecutorService,
// task là Runnable và đoạn này chạy trên thread có MDC đúng.
java.util.Map<String, String> captured =
        org.slf4j.MDC.getCopyOfContextMap();

executor.submit(() -> {
    java.util.Map<String, String> previous =
            org.slf4j.MDC.getCopyOfContextMap();
    try {
        if (captured == null) {
            org.slf4j.MDC.clear();
        } else {
            org.slf4j.MDC.setContextMap(captured);
        }
        task.run();
    } finally {
        if (previous == null) {
            org.slf4j.MDC.clear();
        } else {
            org.slf4j.MDC.setContextMap(previous);
        }
    }
});
~~~

Giải thích:
- **captured** được lấy **trên thread gửi task**, nơi correlationId đã có.
- Worker lưu lại map **previous** để không phá ngữ cảnh hợp lệ đang tồn tại.
- Worker gắn snapshot trước khi chạy task rồi **khôi phục previous trong finally**.
- Không dùng một MDC map global chia sẻ giữa các request.
- Không tạo một correlation ID mới cho mỗi thread worker nếu worker vẫn thuộc cùng workflow.
- Nếu framework đã có context propagator, dùng integration chính thức và kiểm thử đầu ra, tránh tự bọc task nhiều lần theo các quy ước xung đột.

Trong một số ứng dụng reactive, ThreadLocal không còn là phạm vi request đáng tin. Khi đó cần context của framework và bridge thích hợp giữa reactive context và logging context. **Không xem một ví dụ thread pool là quy tắc tự động cho mọi runtime.**

## 10. Tạo ID ở ingress layer thay vì khắp nơi trong business code

**Vị trí tốt nhất để quyết định ID thường là entry point của workflow**, chẳng hạn:

- HTTP filter/interceptor/middleware ở gateway hoặc service.
- Message consumer trước khi gọi business handler.
- Scheduler/job runner trước khi chạy một job.
- RPC server interceptor trước khi vào business method.
- Handler của sự kiện được xử lý bất đồng bộ.

Nếu đặt UUID.randomUUID trong từng class service, cùng một request có thể nhận hàng loạt ID không liên quan:

~~~text
OrderController: correlationId=uuid-A
OrderService: correlationId=uuid-B
PaymentClient: correlationId=uuid-C
~~~

Khi đó công cụ tìm kiếm không thể gom chúng lại bằng một ID duy nhất.

Thay vào đó:

~~~text
Entry point: validate/generate correlationId=uuid-A
    ↓
Request handler: MDC=uuid-A
    ↓
Business service: MDC=uuid-A
    ↓
Outbound HTTP: X-Correlation-ID=uuid-A
    ↓
Downstream: MDC=uuid-A
~~~

Trong Spring MVC hoặc Jakarta Servlet, có thể đặt logic này tại **filter** và dọn MDC trong finally. Tuy nhiên, các chế độ async dispatch, exception handlers, deferred responses và callback cần kiểm tra lifecycle thực tế. **Không copy máy móc một filter đồng bộ cho framework khác rồi cho rằng mọi log async đều đã mang ID.**

## 11. Xử lý lỗi, timeout và retry

Tạo/lan truyền ID đúng cần bao phủ cả đường lỗi, không chỉ response 200.

### Khi downstream trả lỗi

Nếu downstream trả 500, 502, 503, timeout hoặc kết nối thất bại, API nên ghi log lỗi/trạng thái trong scope đang có correlationId. Tùy hợp đồng, upstream có thể trả status phù hợp **kèm cùng correlation ID** để việc điều tra không đứt giữa hai service.

Trong ví dụ runnable, nhánh downstream status/header không phù hợp được ghi **event=api.downstream_mismatch** và trả 502; nhánh InterruptedException ghi **event=api.interrupted** và trả 503. Chương trình demo không chứng minh mọi loại IOException trong hệ thống thực đều sẽ được xử lý; production cần mapping exception và response thống nhất theo framework.

### Khi retry cùng thao tác

Ví dụ một request gọi payment service ba lần vì lỗi tạm thời:

~~~text
correlationId=req-17 event=payment.attempt attempt=1
correlationId=req-17 event=payment.attempt attempt=2
correlationId=req-17 event=payment.attempt attempt=3
correlationId=req-17 event=payment.completed status=ok
~~~

Đây là ví dụ minh họa. **Giữ correlation ID** nếu các attempt thuộc cùng workflow; dùng **attempt=1/2/3** hoặc operationId riêng để phân biệt từng lần thử. Không tạo ID hoàn toàn mới ở mỗi attempt nếu làm mất mối liên kết, trừ khi kiến trúc có ID cấp hop và một correlation ID cha ổn định.

### Khi client tự gửi ID

Nếu public client có thể truyền tùy ý một ID, hai request khác nhau có thể mang cùng ID. Do đó:
- Không dùng correlation ID làm chìa khóa phân quyền hoặc để xác thực request.
- Không dùng nó như bằng chứng giao dịch chưa từng chạy.
- Khi cần định danh thao tác bất biến, phải có ID nội bộ riêng do server cấp theo policy.
- Ghi thêm timestamp, service.name, event name, instance ID hoặc request hop ID khi phân tích.

## 12. Correlation ID, request ID, trace ID và idempotency key

Đây là các khái niệm thường bị nhầm:

| Loại ID | Dùng để làm gì? | Thay thế nhau được không? |
| --- | --- | --- |
| **Correlation ID** | Gom các sự kiện thuộc cùng workflow/chuỗi xử lý | Không tự thay trace hoặc idempotency |
| **Request ID** | Nhận diện một request/hop theo hợp đồng service/gateway | Có thể trùng vai trò correlation ID nhưng không bắt buộc |
| **Trace ID** | Nhận diện một distributed trace theo tracing system | Có quy tắc riêng; không đơn giản là chuỗi bất kỳ |
| **Span ID** | Nhận diện một span trong distributed trace | Không dùng làm correlation ID của toàn trace |
| **Idempotency key** | Giúp backend nhận diện và xử lý lặp yêu cầu theo semantics nghiệp vụ | Không phải khóa tìm log hoặc security token |
| **Transaction ID** | Nhận diện một giao dịch theo mô hình nghiệp vụ/dữ liệu | Có vòng đời và tính bất biến riêng |
| **Session ID** | Nhận diện phiên người dùng theo cơ chế session | Không đưa raw secret/session token vào log |

Một **idempotency key** có thể do client gửi để chống thanh toán trùng theo một quy trình có lưu trữ trạng thái, scope, expiration và kiểm tra payload. **Correlation ID không tự cung cấp bất kỳ điều nào trong các bảo đảm đó.** Nếu một request với cùng correlation ID được gửi hai lần, ứng dụng vẫn có thể xử lý hai giao dịch độc lập nếu không có idempotency mechanism đúng.

**Trace ID** có thể được đưa vào MDC để tìm log, nhưng đó vẫn là dữ liệu do tracing instrumentation cung cấp. Không tự gọi UUID.randomUUID rồi nói đó là W3C trace ID hợp lệ mà không tuân thủ format/propagation của hệ tracing.

## 13. Quan hệ với W3C Trace Context và OpenTelemetry

Trong hệ phân tán hiện đại, nhiều framework dùng chuẩn **W3C Trace Context** với header **traceparent** (và tùy chọn **tracestate**) để truyền tracing context. **Traceparent** có định dạng và quy tắc validation riêng, trong khi **X-Correlation-ID** chỉ là quy ước của ứng dụng.

Ví dụ một traceparent minh họa có cấu trúc:

~~~text
00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Không xem đây là header correlation ID có thể thay bằng mọi chuỗi. Với OpenTelemetry:
- Tracing instrumentation quyết định/đọc traceId, spanId và propagation.
- Logging integration có thể đưa traceId/spanId vào log.
- Correlation ID theo nghiệp vụ có thể là một field riêng nếu cần.
- Không phát minh một traceId mới ở từng microservice khi có trace context hợp lệ được truyền xuống.
- Nếu muốn đồng nhất correlation ID với trace ID, phải **thiết kế rõ** cách lấy trace ID từ context, tính trust và hành vi khi không có trace, không gộp hai cơ chế ngẫu nhiên.

Một quy ước JSON logging có thể gồm:

~~~json
{
  "service": "order-api",
  "level": "INFO",
  "correlationId": "client-17",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "message": "event=order.created"
}
~~~

Đây là **ví dụ schema**, không phải output JSON của ứng dụng ở mục 7 (ứng dụng đó ghi text file). Tên field có thể khác tùy chuẩn ECS/OpenTelemetry và encoder/collector. Quan trọng là các field có ý nghĩa tách biệt, không gắn nhãn sai.

## 14. Tạo correlation ID cho message queue và background job

Không phải mọi workflow bắt đầu từ HTTP.

### Message broker

Khi publish message, hệ thống có thể đưa correlation ID vào **message header/metadata** thay vì payload nghiệp vụ:

~~~text
Message headers:
  correlationId: req-17
  messageId: msg-8821

Message payload:
  orderId: OD-42
~~~

Đây là ví dụ khái niệm, không phải format bắt buộc của một broker cụ thể. Consumer đọc correlation ID theo chính sách tin cậy, đặt vào MDC trong phạm vi xử lý, rồi dọn khi hoàn tất. Nếu consumer tạo message tiếp theo cùng workflow, nó có thể truyền correlation ID cùng message con.

Không dùng một correlation ID để thay cho **messageId**: nhiều message trong cùng workflow cần ID riêng để xử lý retry, deduplication, dead-letter queue hoặc ordering.

### Background job

Nếu một scheduler khởi tạo job không có request gốc, nó có thể **sinh correlation ID mới tại đầu job**. Nếu job có nhiều task con, giữ ID chung và dùng **jobId/taskId** riêng để phân biệt.

~~~text
correlationId=job-flow-17 jobId=batch-42 event=job.started
correlationId=job-flow-17 taskId=chunk-1 event=task.completed
correlationId=job-flow-17 taskId=chunk-2 event=task.completed
correlationId=job-flow-17 jobId=batch-42 event=job.finished
~~~

Trong task pool, cần context propagation như mục 9. **MDC là context cục bộ**, không tự đi theo queue hoặc RPC; phải truyền metadata có chủ đích.

## 15. Bảo mật và tính riêng tư khi tạo ID

Correlation ID thường xuất hiện **trên mọi dòng log của request**, có thể được index và lưu lâu. Vì thế không nên coi đây là trường vô hại trong mọi trường hợp.

### Những điều cần tránh

- **Không dùng access token, JWT, session cookie, password hoặc API key làm correlation ID.**
- **Không đưa email, số điện thoại, tên người dùng hoặc dữ liệu nhạy cảm vào ID**; tạo ID không mang PII.
- **Không tin header Internet chỉ vì regex match.** Validation cú pháp không chứng minh nguồn phát hành đáng tin.
- **Không cho ID dài không giới hạn** làm tăng log ingestion/storage cost.
- **Không cho newline/control character vào ID**, vì có thể gây log injection hoặc phá JSON/text parser.
- **Không để client chỉ định ID được dùng như khóa xác thực/ủy quyền**.
- **Không expose thông tin nội bộ có thể suy ra khách hàng/volume** qua một thuật toán ID tự tạo thiếu đánh giá.
- **Không log cả raw header sai định dạng** chỉ để debug nếu header đó có thể chứa payload tấn công; nếu cần thống kê, ghi reason code/safe metadata theo policy.

### Làm gì khi validation thất bại?

Trong ví dụ, ứng dụng **tạo UUID v4 mới**. Với API khác, bạn có thể muốn trả HTTP 400 nếu client vi phạm hợp đồng. Lựa chọn tùy UX, security policy và vai trò của ID. Đừng âm thầm fallback theo cách khiến operator nghĩ đã giữ client ID, hoặc echo raw ID tấn công.

### Cardinality và storage

Correlation ID thường có **cardinality rất cao** vì gần như mỗi workflow có ID khác nhau. Đây là điều bình thường khi field được index để tìm log. Nhưng **không dùng correlationId làm metric label** trên hệ time-series có giới hạn cardinality trừ khi hiểu rõ chi phí. Đối với metrics, nên aggregate theo endpoint, status, service và những nhãn hữu hạn.

### Collision và giá trị trùng

UUID v4 làm xác suất collision rất nhỏ trong điều kiện sinh đúng. Nếu một ID trùng do client cố ý gửi lại, do bug tạo ID hoặc do hiếm gặp collision, **log correlation có thể trộn hai luồng**. Khi cần định danh có bảo đảm mạnh hơn, tổ chức phải có chính sách cấp phát/kiểm tra uniqueness tại nơi phù hợp, không chỉ trông vào regex hay hash set của ví dụ.

## 16. Chuẩn hóa schema cho logging và API response

Một ứng dụng nên nhất quán về **tên header**, **tên MDC key**, **tên JSON field**, **cách trả response** và **cách tìm trong hệ thống log**.

Ví dụ quy ước:

| Tầng | Tên | Giá trị ví dụ |
| --- | --- | --- |
| HTTP inbound | X-Correlation-ID | client-17 |
| HTTP outbound | X-Correlation-ID | client-17 |
| HTTP response | X-Correlation-ID | client-17 |
| SLF4J MDC | correlationId | client-17 |
| Text Logback pattern | %X{correlationId} | client-17 |
| JSON field | correlationId | client-17 |
| Tracing field riêng | traceId | Giá trị do tracing system cấp |
| Business field riêng | orderId | OD-42 |

**Header và MDC key không nhất thiết cùng chính tả** nhưng mapping phải rõ, test được. Không gắn correlationId lên business message theo cách khiến retry/idempotency bị nhầm.

Với JSON encoder hỗ trợ MDC, một log có thể là:

~~~json
{
  "@timestamp": "2026-11-09T13:20:30.123Z",
  "level": "INFO",
  "logger": "com.example.api.OrderController",
  "message": "event=order.created",
  "correlationId": "client-17",
  "service": "order-api"
}
~~~

Đây là JSON minh họa. Một backend như **logstash-logback-encoder** có thể đưa MDC entries vào JSON nếu đã cấu hình đúng; một PatternLayoutEncoder text như demo **không tự tạo JSON**.

**Tránh duplicate keys:** nếu encoder đã đưa MDC.correlationId thành field top-level, đừng thêm một custom field có cùng key mà không kiểm soát. JSON duplicate property có thể bị các parser xử lý khác nhau.

## 17. Tìm log theo correlation ID

Trong một file text theo format của demo:

~~~text
correlationId=client-17 | event=api.received
correlationId=client-17 | event=downstream.received
correlationId=client-17 | event=api.completed
~~~

Một truy vấn trên log backend thường có ý tưởng:

~~~text
correlationId == "client-17"
~~~

Cách viết query cụ thể phụ thuộc Elasticsearch, OpenSearch, Loki, Splunk, CloudWatch hoặc hệ quan sát khác. Không dùng một cú pháp tưởng tượng rồi gọi đó là câu lệnh chạy được trên mọi hệ.

Nếu log dạng JSONL và có **jq**:

~~~bash
jq -c 'select(.correlationId == "client-17")' application.jsonl
~~~

Điều này chỉ chạy khi đã cài jq và file thực sự có mỗi dòng một object JSON hợp lệ. Với schema ECS hoặc field nested, phải dùng đúng đường dẫn field.

**Kết hợp các trường khác khi điều tra**:
- service.name / service để biết service nào phát log.
- level và event name để phân loại lỗi.
- timestamp và deployment version để xác định khoảng thời gian.
- traceId/spanId khi cần xem các bước phân tán.
- status, orderId và operation khi cần phân tích nghiệp vụ.

**Không coi có cùng ID là bằng chứng hai event chắc chắn liên quan nếu nguồn ID không được tin cậy.** Log correlation là công cụ quan sát; dữ liệu bất thường vẫn cần kiểm chứng.

## 18. Kiểm thử việc tạo và truyền correlation ID

Bài QA nên có ít nhất những tình huống sau:

| Kịch bản | Input | Kết quả mong đợi |
| --- | --- | --- |
| Không có ID | Header không có | Server tạo ID mới hợp lệ |
| ID hợp lệ ở nguồn tin cậy | client-17 | Giữ nguyên theo chính sách |
| ID sai cú pháp | bad id with spaces | Tạo mới hoặc reject theo contract |
| ID rỗng | Chuỗi rỗng | Tạo mới hoặc reject |
| ID quá dài | Trên 64 ký tự theo rule ví dụ | Không chấp nhận nguyên chuỗi |
| Ký tự điều khiển/newline | Input xấu | Không được đưa raw vào log |
| Nhiều header | Hai X-Correlation-ID | Không chọn nhầm một giá trị không được phép |
| Public client không tin cậy | Header hợp lệ về regex | Áp chính sách trust boundary; có thể luôn thay ID |
| Downstream HTTP | Header từ API | Cùng correlation ID đến backend nhận |
| Response | Request đã có hoặc được sinh ID | Trả ID theo hợp đồng |
| Hai request độc lập | Hai lần gọi | Không vô tình dùng ID cũ do thread reuse |
| Async task | Đổi thread | Propagate và restore context đúng |
| Retry | Nhiều attempt cùng workflow | Giữ ID chung, phân biệt attempt |
| Exception | Handler lỗi | Log/response lỗi có ID nếu có thể |
| Service restart | Hệ thống khởi động lại | Không tái sử dụng ID do state không được reset đúng |
| Log JSON | Field correlationId | Parser đọc đúng string, không duplicate |
| PII/security | Raw header chứa secret | Không lưu/echo input nguy hiểm |

### Kết quả kiểm thử của chương trình ở mục 7

Chương trình đã xác nhận:
- **validStatus=200** và **validIdPreserved=true**.
- **invalidStatus=200** và **invalidIdRegenerated=true**.
- **missingStatus=200** và **missingIdGenerated=true**.
- **allIdsDistinct=true** trong ba request.
- Có **9 log events**, mỗi correlation ID xuất hiện đúng **3 lần**.
- **noMissingMdc=true**, không có event thiếu correlationId trong phạm vi test.

**Điều chương trình chưa chứng minh:** xử lý đầy đủ mọi lỗi I/O, rate limit, gateway auth, retry thực, concurrent races với hàng nghìn request, propagation đa process, collector ingestion và tính an toàn ở public edge. Những yêu cầu đó cần integration/load/security tests theo kiến trúc thật.

### Cách kiểm tra sâu hơn

Trong ứng dụng thật, có thể bổ sung:
1. **Unit test cho chooseId** với null, list 0/1/nhiều phần tử, độ dài biên và regex.
2. **Property-based test** cho chuỗi không tin cậy và encoding.
3. **Integration test** với gateway và upstream/downstream thật.
4. **Concurrency test** để phát hiện context rò khi thread pool reuse.
5. **Retry test** để xác nhận cùng correlationId qua nhiều attempt.
6. **Error-path test** cho 4xx/5xx, timeout và exception.
7. **Log schema test** bằng JSON parser; kiểm tra exact field name/type.
8. **Test privacy** để bảo đảm không lưu raw token/user data.
9. **Test collector** để tìm cùng ID trong hệ thống log tập trung.
10. **Test tracing** nếu tổ chức đồng thời dùng W3C traceparent/OpenTelemetry.

## 19. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Mỗi log line có ID khác | Sinh UUID tại từng Logger.info | Chỉ sinh ở entry point, giữ qua scope |
| API có ID nhưng downstream không có | Không truyền HTTP/message header | Gắn ID vào outbound request/metadata |
| Downstream tự sinh ID khác | Sai tên header, validation khác hoặc không tin nguồn | Chuẩn hóa contract và trust boundary |
| Event cuối không có ID | Đóng MDC scope trước khi ghi log kết thúc | Ghi event kết thúc trong scope |
| Worker log mang ID request cũ | Không restore/clear MDC trong thread pool | Dùng task decorator, try/finally |
| ID hợp lệ mà đáng ngờ xuất ở nhiều client | Header untrusted được giữ nguyên | Gateway cấp ID mới hoặc chính sách nhận ID tin cậy |
| Một request có hai ID khác nhau | Hai filter/middleware độc lập đều sinh lại | Chỉ một nguồn cấp ID chính và phân biệt ID cấp hop |
| Header có newline | Không validation/escaping | Validate giới hạn ký tự và độ dài trước log/response |
| Log trên console có ID nhưng JSON index không có | JSON encoder/ingest không xuất MDC | Kiểm tra field mapping, parser và pipeline |
| Correlation ID bị dùng làm idempotency key | Trộn mục đích observability với dedup nghiệp vụ | Tách contract và nơi lưu trạng thái idempotency |
| Dashboard trống khi lọc correlationId | Key bị đổi hoặc dữ liệu chỉ có trong message | Chuẩn hóa schema, kiểm tra raw event |
| Hai request cùng ID dù khác nhau | Client reuse, bug hoặc va chạm ID | Kiểm tra nguồn cấp phát, trust policy và dữ liệu |
| Log nhiều mà tìm khó | Thiếu event names/service/timestamp | Bổ sung field có nghĩa, không chỉ một ID |
| Tạo ID bằng timestamp mili giây | Có thể trùng khi request đồng thời | Dùng generator thích hợp như UUID v4 |
| Tạo ID từ user email/order ID | Có thể lộ PII, không đủ duy nhất | Dùng ID ngẫu nhiên không tiết lộ nghiệp vụ |
| Log app bị thiếu khi service lỗi | Scope, backend hoặc I/O exception | Test error path, shutdown/flush và collector |

**Không sửa vấn đề bằng cách tăng độ dài ID một cách mù quáng.** Cần xác định lỗi ở tầng nào: tạo, validation, trust, propagation, logging context, encoder hay search backend.

## 20. Câu hỏi và đáp án tự kiểm tra

**Câu 1.** Correlation ID dùng để làm gì?  
**Đáp án:** Liên kết các logging event thuộc cùng một request/workflow qua nhiều thành phần, hỗ trợ tra cứu và chẩn đoán.

**Câu 2.** Tạo UUID v4 trong Java 17 bằng API nào?  
**Đáp án:** UUID.randomUUID().toString().

**Câu 3.** Tại sao không tạo ID mới ở mỗi service method?  
**Đáp án:** Vì các log của cùng workflow sẽ mang ID khác nhau và không còn liên kết được.

**Câu 4.** Một header hợp lệ theo regex có thể tự động tin cậy chưa?  
**Đáp án:** Chưa. Cần kiểm tra trust boundary, gateway và nguồn phát hành. Client không tin cậy vẫn có thể gửi một chuỗi hợp lệ.

**Câu 5.** Vì sao phải kiểm tra nhiều header cùng tên?  
**Đáp án:** Để không chọn nhầm giá trị không được phép, không bị nhập nhằng khi proxy hợp nhất header và không tạo kênh đưa dữ liệu xấu vào log.

**Câu 6.** Đặt ID vào MDC có tự đưa nó qua HTTP không?  
**Đáp án:** Không. Phải truyền ID qua header/message metadata và đặt context mới ở service nhận.

**Câu 7.** Correlation ID có phải một access token không?  
**Đáp án:** Không. Không dùng nó để xác thực/ủy quyền và không dùng secret làm ID.

**Câu 8.** Vì sao phải remove correlationId khỏi MDC cuối request?  
**Đáp án:** Để tránh ID request trước bị giữ trên thread pool và gán sai cho request sau.

**Câu 9.** Retry cùng workflow nên tạo ID mới không?  
**Đáp án:** Thường giữ correlation ID chung và dùng attempt ID/counter riêng; tùy contract, nhưng cần khả năng nối các lần thử.

**Câu 10.** Correlation ID có thay được idempotency key không?  
**Đáp án:** Không. Idempotency có hợp đồng nghiệp vụ và cơ chế lưu/kiểm tra lặp riêng.

**Câu 11.** Trace ID trong traceparent có phải bất kỳ UUID string nào cũng được không?  
**Đáp án:** Không. W3C Trace Context có format và quy tắc validation/propagation cụ thể.

**Câu 12.** Nếu correlation ID có trong response nhưng không có ở log, có thể kết luận logging đã đúng không?  
**Đáp án:** Không. Cần kiểm tra MDC, encoder, level/filter, lỗi backend và ingest pipeline.

**Câu 13.** Trong demo ba request, vì sao expected log count là 9?  
**Đáp án:** Mỗi request phát ba event: api.received, downstream.received và api.completed.

**Câu 14.** Vì sao không dùng timestamp milliseconds làm ID duy nhất?  
**Đáp án:** Hai request đồng thời có thể cùng mili giây; timestamp không đủ entropy và uniqueness theo kỳ vọng.

**Câu 15.** Khi application dùng OpenTelemetry, có còn cần correlation ID riêng không?  
**Đáp án:** Tùy nhu cầu. Trace ID đã liên kết các span; correlation ID nghiệp vụ có thể bổ sung nếu contract hỗ trợ hoặc cần tra cứu không dựa trên trace lifecycle.

## 21. Tài liệu tham khảo kỹ thuật

- [Oracle Java SE 17 — UUID](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/UUID.html): UUID.randomUUID, version, toString, fromString và dạng canonical.
- [Oracle Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): HttpServer, HttpExchange và executor.
- [Oracle Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): outbound HTTP request/response và timeout.
- [SLF4J API — MDC](https://www.slf4j.org/api/org/slf4j/MDC.html): putCloseable, remove, getCopyOfContextMap và setContextMap.
- [Logback Manual — MDC](https://logback.qos.ch/manual/mdc.html): Mapped Diagnostic Context và quy tắc propagation giữa các thread.
- [Logback Manual — Layouts](https://logback.qos.ch/manual/layouts.html): %X{key} và PatternLayout.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): header traceparent/tracestate, format và tính tương tác.
- [OpenTelemetry — Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/): trace context, propagators và integration xuyên service.

## Tóm tắt

**Tạo correlation ID đúng nghĩa là quyết định một ID tại entry point, kiểm tra nguồn tin cậy và định dạng, giữ nó nhất quán trong phạm vi request/workflow, truyền qua downstream và ghi vào log bằng MDC/encoder đúng cách.** Trong Java 17, **UUID.randomUUID()** là cách tạo một ID ngẫu nhiên thực dụng khi không có ID được chấp nhận. **Regex chỉ xác minh cú pháp, không xác minh trust**. Tránh gắn secret hoặc PII vào ID, không dùng correlation ID thay cho authentication, tracing hay idempotency, và phải dọn logging context đúng lifecycle. Khi kiểm thử, hãy đối chiếu **response ID, downstream header, ID trong log và tình huống lỗi/async**, không chỉ thấy một chuỗi UUID rồi kết luận hoàn tất.
