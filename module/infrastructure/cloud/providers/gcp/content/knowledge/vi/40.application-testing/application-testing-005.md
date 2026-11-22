# Kiểm thử Cloud Run functions bằng Functions Framework

Cloud Run functions cho phép triển khai các hàm nhỏ xử lý HTTP request hoặc CloudEvents từ các hệ thống như Pub/Sub và Cloud Storage. Một hàm có thể ngắn chỉ vài chục dòng, nhưng vẫn có thể lỗi do validate dữ liệu đầu vào, định dạng event, quyền IAM, dịch vụ bên ngoài hoặc tình huống gửi lại sự kiện. **Functions Framework** giúp chạy hàm bằng cùng giao diện lập trình trên máy phát triển để kiểm tra hành vi trước khi đưa lên Google Cloud.

Bài học thuộc chương **Kiểm thử ứng dụng GCP** trong module **CLOUD_PROVIDERS_GCP**. Trong lộ trình khám phá Google Cloud từ project, IAM, VPC đến Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu và quy trình phát hành, kiểm thử function là bước xác nhận thay đổi an toàn, giảm rủi ro triển khai, theo dõi độ tin cậy và kiểm soát chi phí thử nghiệm.

Sau bài học, bạn có thể:

- Phân biệt unit test, local integration test, staging smoke test và end-to-end test cho Cloud Run functions.
- Viết Java HTTP function bằng giao diện HttpFunction; mock HttpRequest/HttpResponse với JUnit và Mockito.
- Chạy HTTP function qua Functions Framework trên localhost rồi gửi request bằng curl.
- Viết CloudEventsFunction và kiểm thử payload/event metadata theo CloudEvents 1.0.
- Giả lập Cloud Storage hoặc Pub/Sub event theo đúng header, content type và data envelope.
- Đặt kiểm thử vào CI/CD, kiểm tra IAM, retries, idempotency, log, timeout và giới hạn của môi trường local.

## 1. Functions Framework nằm ở đâu trong vòng đời một function?

Functions Framework là thư viện nguồn mở cung cấp contract thực thi function. Với Java, bạn triển khai một class implement một trong hai interface:

| Signature | Java interface | Điểm vào | Dùng khi |
|---|---|---|---|
| HTTP | com.google.cloud.functions.HttpFunction | service(HttpRequest, HttpResponse) | API endpoint, webhook, HTTP request |
| CloudEvent | com.google.cloud.functions.CloudEventsFunction | accept(CloudEvent) | Eventarc, Cloud Storage, Pub/Sub hoặc các nguồn CloudEvents |

Trên Java, **entry point là tên class đầy đủ gồm package**, ví dụ com.example.functions.GreetingFunction. Functions Framework phát hiện signature dựa trên interface mà class implement; không cần dùng các flag signature-type của Node.js/Python cho Java.

~~~mermaid
flowchart TD
    SOURCE["Java source<br/>HttpFunction / CloudEventsFunction"]
    SOURCE --> UNIT["Unit test<br/>JUnit + Mockito"]
    SOURCE --> FF["Functions Framework<br/>local HTTP server"]
    FF --> LOCAL["Local integration test<br/>curl / HttpClient / CloudEvents"]
    LOCAL --> PIPE["CI validation<br/>build + tests"]
    PIPE --> STAGE["Cloud Run staging<br/>deploy + trigger"]
    STAGE --> E2E["E2E với Eventarc / IAM / services"]
    E2E --> PROD["Production release"]
~~~

Khi chạy local, Functions Framework khởi động một HTTP server, thường trên cổng 8080. Server nhận HTTP request rồi gọi method tương ứng trong function. Với CloudEvents, framework chuyển request có thông tin CloudEvents thành đối tượng CloudEvent.

**Giới hạn cần hiểu:** chạy local không tự tái hiện toàn bộ Cloud Run, Eventarc, IAM, Cloud SQL, Secret Manager, VPC, autoscaling hoặc quota. Nó mô phỏng **function invocation contract**; muốn kiểm tra tích hợp nền tảng thì phải dùng environment thử nghiệm trên Google Cloud.

## 2. Chiến lược kiểm thử theo các tầng

Không nên cố biến mọi test thành một lần deploy thật. Mỗi tầng bảo đảm một thuộc tính khác nhau:

| Tầng | Kiểm tra điều gì? | Chạy ở đâu? | Phụ thuộc hạ tầng thật? |
|---|---|---|---|
| Unit | Điều kiện, mapping, validate, response và business logic | JVM trong Maven test | Không |
| Component | Function gọi adapter của dịch vụ phụ trợ thế nào | JVM với fake/mock | Thường không |
| Local integration | Functions Framework khởi động đúng entry point, nhận HTTP/CloudEvent, trả status hợp lệ | Localhost | Không, nếu dependency đã giả lập |
| Staging integration | Auth, service account, secrets, network và database thật trong project thử nghiệm | Cloud Run staging | Có |
| End-to-end | Chuỗi producer → Pub/Sub/Eventarc → function → output | Google Cloud test project | Có |
| Regression/contract | Schema, field bắt buộc, lỗi đầu vào và tương thích event version | JVM, local hoặc staging | Tùy mức test |

Một pipeline hợp lý chạy unit test ở mỗi pull request, local integration test khi build, rồi staging smoke test và E2E ở những nhánh phát hành quan trọng. E2E chậm và tốn chi phí hơn nên tập trung vào hành vi nền tảng có giá trị cao: quyền gọi function, Eventarc trigger, dữ liệu thật và thao tác retry.

## 3. Dự án Maven dành cho Java function

Ví dụ bài thực hành dùng **Java 17**, Maven và một HTTP function có thể kiểm thử riêng biệt.

Cấu trúc dự án:

~~~text
functions-testing-demo/
  pom.xml
  src/
    main/
      java/
        com/example/functions/
          GreetingFunction.java
          StorageFinalizedFunction.java
    test/
      java/
        com/example/functions/
          GreetingFunctionTest.java
          GreetingHttpIT.java
          StorageFinalizedFunctionTest.java
~~~

Ví dụ pom.xml đầy đủ cho các đoạn mã chính:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>functions-testing-demo</artifactId>
  <version>1.0.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>com.google.cloud.functions</groupId>
      <artifactId>functions-framework-api</artifactId>
      <version>1.1.2</version>
      <scope>provided</scope>
    </dependency>

    <dependency>
      <groupId>junit</groupId>
      <artifactId>junit</artifactId>
      <version>4.13.2</version>
      <scope>test</scope>
    </dependency>

    <dependency>
      <groupId>org.mockito</groupId>
      <artifactId>mockito-core</artifactId>
      <version>5.10.0</version>
      <scope>test</scope>
    </dependency>

    <dependency>
      <groupId>io.cloudevents</groupId>
      <artifactId>cloudevents-core</artifactId>
      <version>2.5.0</version>
      <scope>test</scope>
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
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
      </plugin>

      <plugin>
        <groupId>com.google.cloud.functions</groupId>
        <artifactId>function-maven-plugin</artifactId>
        <version>0.11.0</version>
        <configuration>
          <functionTarget>com.example.functions.GreetingFunction</functionTarget>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

- functions-framework-api cung cấp Java interfaces. Scope provided phù hợp môi trường Cloud Run functions; local invoker cung cấp runtime cần thiết.
- function-maven-plugin cung cấp goal function:run để chạy local.
- JUnit và Mockito dành cho unit test; cloudevents-core test scope dùng để xây fixture CloudEvent.
- Các version trên là một bộ phiên bản minh họa có thể đối chiếu tài liệu upstream. Trước khi nâng cấp hoặc dùng cho production, xác nhận tương thích với JDK, runtime được chọn và dependency tree của dự án.

Dùng Maven test để chạy các test mặc định:

~~~bash
mvn -B test
~~~

Goal function:run dùng để **chạy function local**, còn Maven test dùng để chạy các Java test; chúng phục vụ hai mục đích khác nhau.

## 4. Viết một HTTP function có thể kiểm thử

Hàm sau chỉ hỗ trợ GET. Nếu thiếu tham số name, hàm trả lời theo mặc định. Nếu tham số quá dài, hàm từ chối. Nếu phương thức HTTP không đúng, hàm trả 405.

File src/main/java/com/example/functions/GreetingFunction.java:

~~~java
package com.example.functions;

import com.google.cloud.functions.HttpFunction;
import com.google.cloud.functions.HttpRequest;
import com.google.cloud.functions.HttpResponse;
import java.io.IOException;

public final class GreetingFunction implements HttpFunction {
    @Override
    public void service(HttpRequest request, HttpResponse response)
            throws IOException {
        response.appendHeader("Content-Type", "text/plain; charset=UTF-8");

        if (!"GET".equals(request.getMethod())) {
            response.setStatusCode(405);
            response.appendHeader("Allow", "GET");
            response.getWriter().write("Method not allowed");
            return;
        }

        String name = request.getFirstQueryParameter("name")
                .orElse("World").trim();

        if (name.isEmpty()) {
            name = "World";
        }

        if (name.length() > 60) {
            response.setStatusCode(400);
            response.getWriter().write("Invalid name");
            return;
        }

        response.getWriter().write("Hello, " + name + "!");
    }
}
~~~

Ở đây, HttpRequest và HttpResponse là interface, nên có thể dùng Mockito thay thế trong unit test. Business logic cũng đủ nhỏ để người học thấy rõ test case, expected status và response body.

Với một function thật, nên tách thành hai lớp:

1. **Handler/adapter** nhận HttpRequest, validate, gọi service và tạo response.
2. **Service nghiệp vụ** xử lý quy tắc độc lập với Functions Framework.

Cách này giúp unit test phần nghiệp vụ mà không cần tạo HTTP server. Function không cần khởi tạo SDK client hoặc database connection cho mỗi request; các client dùng chung có thể được khởi tạo khi instance start nếu phù hợp với concurrency và lifecycle.

## 5. Unit test HTTP function bằng JUnit và Mockito

Unit test gọi trực tiếp method service(). Test không khởi động Functions Framework và không gọi network.

File src/test/java/com/example/functions/GreetingFunctionTest.java:

~~~java
package com.example.functions;

import com.google.cloud.functions.HttpRequest;
import com.google.cloud.functions.HttpResponse;
import java.io.BufferedWriter;
import java.io.StringWriter;
import java.util.Optional;
import org.junit.Before;
import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.mockito.Mockito.*;

public class GreetingFunctionTest {
    private HttpRequest request;
    private HttpResponse response;
    private StringWriter output;
    private BufferedWriter writer;

    @Before
    public void setUp() throws Exception {
        request = mock(HttpRequest.class);
        response = mock(HttpResponse.class);
        output = new StringWriter();
        writer = new BufferedWriter(output);

        when(response.getWriter()).thenReturn(writer);
    }

    @Test
    public void returnsGreetingForQueryParameter() throws Exception {
        when(request.getMethod()).thenReturn("GET");
        when(request.getFirstQueryParameter("name"))
                .thenReturn(Optional.of("Lan"));

        new GreetingFunction().service(request, response);
        writer.flush();

        assertEquals("Hello, Lan!", output.toString());
        verify(response, never()).setStatusCode(400);
        verify(response, never()).setStatusCode(405);
    }

    @Test
    public void usesDefaultNameWhenParameterMissing() throws Exception {
        when(request.getMethod()).thenReturn("GET");
        when(request.getFirstQueryParameter("name"))
                .thenReturn(Optional.empty());

        new GreetingFunction().service(request, response);
        writer.flush();

        assertEquals("Hello, World!", output.toString());
    }

    @Test
    public void rejectsUnsupportedMethod() throws Exception {
        when(request.getMethod()).thenReturn("POST");

        new GreetingFunction().service(request, response);
        writer.flush();

        verify(response).setStatusCode(405);
        verify(response).appendHeader("Allow", "GET");
        assertEquals("Method not allowed", output.toString());
    }

    @Test
    public void rejectsTooLongName() throws Exception {
        when(request.getMethod()).thenReturn("GET");
        when(request.getFirstQueryParameter("name"))
                .thenReturn(Optional.of("x".repeat(61)));

        new GreetingFunction().service(request, response);
        writer.flush();

        verify(response).setStatusCode(400);
        assertEquals("Invalid name", output.toString());
    }
}
~~~

**Vì sao phải flush() trong test?** HttpResponse.getWriter() được mock bằng BufferedWriter do test sở hữu. Lệnh write có thể còn trong buffer, nên test gọi flush để đọc được StringWriter. Khi chạy qua Functions Framework, framework quản lý vòng đời response thực.

### Những test case nên thêm

| Nhóm | Input | Kết quả kỳ vọng |
|---|---|---|
| Happy path | GET ?name=Lan | 200, nội dung Hello, Lan! |
| Default | GET không có name | 200, Hello, World! |
| Validation | name vượt giới hạn | 400 |
| HTTP contract | POST | 405, header Allow |
| Ký tự quốc tế | GET với UTF-8 URL-encoded | Response đúng charset |
| Input nguy hiểm | HTML markup trong name | Không bị diễn giải thành HTML khi trả text/plain |
| Fault injection | Service phụ trợ ném exception | Trả lỗi được kiểm soát, không lộ secret |
| Timeout | Dependency chậm hơn ngân sách | Dừng hoặc trả lỗi trong giới hạn |

Không nên viết test chỉ khẳng định một mock đã được gọi rồi xem đó là bằng chứng toàn bộ function hoạt động. Chọn các assertion phản ánh API contract hoặc business outcome.

## 6. Chạy HTTP function bằng Functions Framework

### 6.1. Khởi động local invoker

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn function:run \
  -Drun.functionTarget=com.example.functions.GreetingFunction \
  -Drun.port=8080
~~~

Khi lệnh đã khởi động server, mở một terminal thứ hai trên cùng máy và gửi request:

~~~bash
curl -i "http://localhost:8080/?name=Lan"
~~~

Kết quả kỳ vọng: HTTP 200 với body Hello, Lan!.

Kiểm tra nhánh lỗi:

~~~bash
curl -i -X POST "http://localhost:8080/"
curl -i "http://localhost:8080/?name=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
~~~

Lệnh đầu phải trả 405. Lệnh thứ hai dùng 61 ký tự x và phải trả 400.

Trên Windows PowerShell, có thể dùng curl.exe để tránh alias Invoke-WebRequest trong các phiên bản PowerShell cũ:

~~~powershell
curl.exe -i "http://localhost:8080/?name=Lan"
~~~

Java Functions Framework chấp nhận run.functionTarget và run.port qua Maven properties; nó tự nhận biết HTTP hay CloudEvent từ interface của entry point. Nếu nhiều function cùng chạy, dùng các port khác nhau (ví dụ 8080 và 8081).

### 6.2. Mức độ kiểm thử đạt được

Chạy local thật giúp phát hiện lỗi:

- Java entry point sai tên package hoặc class.
- Class không implement interface phù hợp.
- Thiếu dependency runtime hoặc cấu hình Maven plugin.
- HTTP method, header, encoding, response status, body không khớp kỳ vọng.
- Server không bind được port hoặc có exception ở startup.

Tuy vậy, local không chứng minh quyền run.invoker, IAM của service account, Eventarc trigger, Secret Manager và Cloud Run autoscaling đã đúng.

## 7. Integration test HTTP qua cổng localhost

Có thể tự động gửi HTTP request bằng Java HttpClient. Test này yêu cầu **Functions Framework đã chạy trên localhost** trước khi bắt đầu. Nên đặt tên *IT để phân biệt với unit test.

File src/test/java/com/example/functions/GreetingHttpIT.java:

~~~java
package com.example.functions;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class GreetingHttpIT {
    @Test
    public void frameworkDispatchesHttpRequest() throws Exception {
        String baseUrl = System.getenv()
                .getOrDefault("FUNCTION_TEST_URL", "http://localhost:8080");

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/?name=Lan"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpClient client = HttpClient.newHttpClient();
        HttpResponse<String> result = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, result.statusCode());
        assertEquals("Hello, Lan!", result.body());
    }
}
~~~

Thứ tự chạy:

1. Terminal A: khởi động mvn function:run với GreetingFunction.
2. Terminal B: chạy lệnh test được chọn.
3. Sau test, dừng local invoker (Ctrl+C).

~~~bash
mvn -B -Dtest=GreetingHttpIT test
~~~

Maven Surefire mặc định thường nhận các tên *Test, nhưng không tự chạy mọi tên *IT. Lệnh -Dtest=GreetingHttpIT ép chạy integration test cụ thể. Trong pipeline chuẩn hơn, dùng Maven Failsafe ở các pha integration-test/verify và quản lý vòng đời local server trong cùng job.

### Những kiểm tra nên có ở HTTP integration test

- HTTP GET và POST đúng response code.
- Header Content-Type, encoding và parameter parsing.
- JSON body nếu function dùng POST payload.
- Response khi body thiếu/không hợp lệ.
- Timeout khi endpoint bị chậm.
- Hai request liên tiếp không làm rò trạng thái giữa các lần gọi.

Unit test giúp xác nhận logic; integration test này giúp xác nhận framework thực sự dispatch đúng class và serialization/request handling.

## 8. CloudEvent function: nhận sự kiện từ Cloud Storage

Các function event-driven có signature CloudEvent. Eventarc chuyển các sự kiện theo chuẩn CloudEvents 1.0; đối tượng CloudEvent gồm thuộc tính chung và payload.

Thuộc tính cơ bản:

| Thuộc tính | Ý nghĩa |
|---|---|
| id | ID của sự kiện từ producer |
| source | Nguồn phát sự kiện |
| type | Loại sự kiện, ví dụ object finalized |
| specversion | Phiên bản CloudEvents |
| time | Thời điểm event, nếu producer cung cấp |
| data | Payload theo schema của nguồn sự kiện |

Ví dụ một function dành cho sự kiện tạo mới object trên Cloud Storage. Để tập trung vào kiểm thử, handler chuyển metadata và payload tới EventSink được tiêm vào. Constructor mặc định chỉ ghi event ID vào log; trong hệ thống thật, thay bằng dịch vụ lưu trữ/xử lý được kiểm soát.

File src/main/java/com/example/functions/StorageFinalizedFunction.java:

~~~java
package com.example.functions;

import com.google.cloud.functions.CloudEventsFunction;
import io.cloudevents.CloudEvent;
import java.nio.charset.StandardCharsets;
import java.util.logging.Logger;

public final class StorageFinalizedFunction implements CloudEventsFunction {
    private static final Logger LOGGER =
            Logger.getLogger(StorageFinalizedFunction.class.getName());
    private static final String EVENT_TYPE =
            "google.cloud.storage.object.v1.finalized";

    @FunctionalInterface
    interface EventSink {
        void record(String eventKey, String payload) throws Exception;
    }

    private final EventSink sink;

    // Constructor này được Functions Framework gọi qua reflection.
    public StorageFinalizedFunction() {
        this((key, payload) -> LOGGER.info("Processed event: " + key));
    }

    // Constructor dành cho unit test hoặc dependency injection.
    StorageFinalizedFunction(EventSink sink) {
        this.sink = sink;
    }

    @Override
    public void accept(CloudEvent event) throws Exception {
        if (!EVENT_TYPE.equals(event.getType())) {
            return;
        }

        if (event.getData() == null) {
            throw new IllegalArgumentException("Missing CloudEvent data");
        }

        String eventKey = event.getSource() + "#" + event.getId();
        String json = new String(
                event.getData().toBytes(), StandardCharsets.UTF_8);

        sink.record(eventKey, json);
    }
}
~~~

Trong code production, cần parse JSON theo schema của Cloud Storage, kiểm tra bucket/name/generation và dùng sink có xử lý idempotency bền vững. Đoạn mẫu chỉ chứng minh routing và khả năng kiểm thử, không thực hiện lưu file hay cập nhật database.

**Phân biệt:** Pub/Sub hoặc Cloud Storage event có thể dùng các thuộc tính payload khác nhau. Không dùng một JSON payload giả tưởng chung cho mọi nguồn; test fixture cần mô phỏng đúng event type và schema mà trigger sẽ gửi.

## 9. Unit test CloudEvent bằng CloudEventBuilder

CloudEvents Java SDK hỗ trợ dựng event fixture theo spec 1.0. Không cần khởi động Functions Framework để gọi accept() trực tiếp.

File src/test/java/com/example/functions/StorageFinalizedFunctionTest.java:

~~~java
package com.example.functions;

import io.cloudevents.CloudEvent;
import io.cloudevents.core.builder.CloudEventBuilder;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import org.junit.Test;

import static org.junit.Assert.assertThrows;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class StorageFinalizedFunctionTest {
    @Test
    public void forwardsFinalizedEventToSink() throws Exception {
        StorageFinalizedFunction.EventSink sink =
                mock(StorageFinalizedFunction.EventSink.class);

        String payload = "{\"bucket\":\"test-bucket\",\"name\":\"a.txt\"}";
        CloudEvent event = CloudEventBuilder.v1()
                .withId("evt-123")
                .withSource(URI.create(
                        "//storage.googleapis.com/projects/_/buckets/test-bucket"))
                .withType("google.cloud.storage.object.v1.finalized")
                .withData("application/json",
                        payload.getBytes(StandardCharsets.UTF_8))
                .build();

        new StorageFinalizedFunction(sink).accept(event);

        verify(sink).record(
                contains("evt-123"),
                eq(payload));
    }

    @Test
    public void ignoresUnexpectedEventType() throws Exception {
        StorageFinalizedFunction.EventSink sink =
                mock(StorageFinalizedFunction.EventSink.class);

        CloudEvent event = CloudEventBuilder.v1()
                .withId("evt-999")
                .withSource(URI.create("https://example.com"))
                .withType("com.example.other")
                .build();

        new StorageFinalizedFunction(sink).accept(event);
        verifyNoInteractions(sink);
    }

    @Test
    public void rejectsMissingPayload() {
        StorageFinalizedFunction.EventSink sink =
                mock(StorageFinalizedFunction.EventSink.class);

        CloudEvent event = CloudEventBuilder.v1()
                .withId("evt-empty")
                .withSource(URI.create("https://example.com"))
                .withType("google.cloud.storage.object.v1.finalized")
                .build();

        assertThrows(IllegalArgumentException.class,
                () -> new StorageFinalizedFunction(sink).accept(event));
        verifyNoInteractions(sink);
    }
}
~~~

Các bài kiểm thử trên xác nhận loại sự kiện, nội dung, ID và nhánh lỗi. Vì sink được mock, chúng chưa chứng minh event đã thực sự ghi thành công vào Cloud Storage, Firestore hay database; phần đó cần component hoặc integration test riêng.

**Không nên trả lỗi cho mọi dữ liệu không hợp lệ trong production mà không có chiến lược.** Với Eventarc, việc ném exception có thể khiến sự kiện bị gửi lại tùy chính sách retry. Cần phân biệt lỗi tạm thời có thể retry và payload sai vĩnh viễn cần được ghi nhận/đưa vào luồng xử lý riêng.

## 10. Chạy CloudEventsFunction local và gửi fixture

Chạy chức năng Cloud Storage trên cổng riêng:

~~~bash
mvn function:run \
  -Drun.functionTarget=com.example.functions.StorageFinalizedFunction \
  -Drun.port=8081
~~~

CloudEvents hỗ trợ HTTP binary content mode. Ở chế độ này, các thuộc tính CloudEvents nằm trong header ce-*, còn request body chứa JSON của event data.

Gửi sự kiện Cloud Storage finalized từ terminal khác:

~~~bash
curl -i "http://localhost:8081/" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "ce-specversion: 1.0" \
  -H "ce-id: evt-123" \
  -H "ce-type: google.cloud.storage.object.v1.finalized" \
  -H "ce-source: //storage.googleapis.com/projects/_/buckets/test-bucket" \
  -H "ce-subject: objects/a.txt" \
  --data-binary '{"bucket":"test-bucket","name":"a.txt","generation":"1"}'
~~~

Kết quả mong đợi: HTTP 2xx và log có key chứa evt-123. Với CloudEventsFunction có return type void, response thành công thường không có body; hãy kiểm tra HTTP status và tác động/lời ghi log thay vì chờ một chuỗi trả lời.

Để kiểm tra nhánh thiếu header, thử bỏ ce-id hoặc ce-type. Framework phải phát hiện CloudEvent không hợp lệ ở lớp parse; đây là **framework contract test**, khác với test nghiệp vụ trong accept().

### Pub/Sub CloudEvent có data base64

Với trigger Pub/Sub qua Eventarc, CloudEvent type thường là google.cloud.pubsub.topic.v1.messagePublished. Phần data là JSON envelope chứa message, và message.data là chuỗi Base64. Ví dụ:

~~~json
{
  "message": {
    "messageId": "10001",
    "data": "SGVsbG8gZnVuY3Rpb24=",
    "attributes": {
      "source": "orders"
    }
  },
  "subscription": "projects/demo-project/subscriptions/orders-sub"
}
~~~

Một function xử lý Pub/Sub phải đọc event.getData(), parse JSON, lấy message.data rồi Base64-decode; không chuyển trực tiếp chuỗi Base64 thành nội dung message.

Ví dụ HTTP fixture cho handler Pub/Sub **nếu dự án có một CloudEventsFunction riêng cho loại này**:

~~~bash
curl -i "http://localhost:8081/" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "ce-specversion: 1.0" \
  -H "ce-id: pubsub-123" \
  -H "ce-type: google.cloud.pubsub.topic.v1.messagePublished" \
  -H "ce-source: //pubsub.googleapis.com/projects/demo-project/topics/orders" \
  --data-binary '{"message":{"messageId":"10001","data":"SGVsbG8="}}'
~~~

Fixture trên không phải đầu vào nghiệp vụ của StorageFinalizedFunction vì class mẫu lọc loại Cloud Storage. Khi kiểm thử Pub/Sub, chuyển target sang một function implement handler cho event type Pub/Sub.

## 11. Thiết kế test doubles cho dịch vụ bên ngoài

Function có thể gọi Secret Manager, Cloud Storage, Pub/Sub, Firestore, Cloud SQL hoặc HTTP API của đối tác. Một unit test tốt nên kiểm tra logic mà không truy cập production.

### 11.1. Adapter và dependency injection

Tạo interface biểu diễn thao tác nghiệp vụ, ví dụ OrderPublisher hoặc FileMetadataStore. Function nhận interface ở constructor test; constructor mặc định có thể tạo adapter chính thức dùng ADC.

~~~mermaid
flowchart LR
    H["Function handler"] --> S["Business service"]
    S --> I["Storage / PubSub interface"]
    I --> F["Fake hoặc Mockito<br/>unit/component test"]
    I --> REAL["Google Cloud SDK client<br/>staging/production"]
~~~

Đây là cách tạo một seam để thay dependency trong test. Không cần mock sâu các lớp nội bộ của Google Cloud SDK nếu có thể fake ngay ở interface nghiệp vụ. Unit test có thể xác nhận operation name, payload, key idempotency và retry classification.

### 11.2. Emulator và test resource

| Dependency | Cách kiểm tra |
|---|---|
| Pub/Sub | Pub/Sub emulator để thử publish/subscribe/ack; E2E với topic/subscription staging để kiểm tra IAM/Eventarc |
| Firestore | Firestore emulator cho một phần hành vi đọc/ghi/query; kiểm tra khác biệt với service thật ở staging |
| Cloud SQL | Database container hoặc Cloud SQL test instance; kiểm tra transaction/migration thực tế |
| Secret Manager | Fake adapter trong unit; Secret Manager thật của staging cho IAM/secret version |
| Cloud Storage | Fake SDK adapter cho unit; bucket staging cho signed URL, IAM, notification và lifecycle |
| HTTP service đối tác | Stub server kiểm tra status/headers/timeouts và lỗi giả lập |

Emulator thường không tái hiện đầy đủ IAM, audit log, regional routing và quota. Vì thế kết quả unit/component test phải được bổ sung bằng các integration test có phạm vi rõ ràng.

Trong CI, tạo tên resource có suffix ngẫu nhiên cho test và dọn dẹp ở bước finally/cleanup, kể cả khi test thất bại. Không dùng bucket/topic production cho test.

## 12. Kiểm thử retry, duplicate event và idempotency

Các hệ thống event-driven có thể giao event nhiều lần. Trigger từ Eventarc/Pub/Sub thường có mô hình **at-least-once delivery**. Một message có thể được gửi lại khi function trả lỗi, timeout, hoặc xác nhận không đến nơi. Không giả định mỗi event được xử lý đúng một lần.

Một số case quan trọng:

1. Cùng event source + id được gửi hai lần: tác động nghiệp vụ chỉ được thực hiện một lần.
2. Hai event có id khác nhau nhưng cùng resource: quy tắc phiên bản/generation không ghi đè dữ liệu mới bằng dữ liệu cũ.
3. Dependency trả 503 tạm thời: retry có backoff phù hợp.
4. Payload sai định dạng vĩnh viễn: ghi lại bằng chứng, tránh retry vô hạn.
5. Function hoàn thành nhưng response/ack bị mất: lần giao lại không tạo side effect trùng.
6. Hai request chạy đồng thời: xử lý idempotency không có race condition.

**Ví dụ khóa chống xử lý trùng:** kết hợp CloudEvent source và id; với Cloud Storage có thể cần thêm generation hoặc metageneration tùy nghiệp vụ.

Một thiết kế bền vững thường lưu key bằng thao tác insert/create-if-absent có tính atomic trong Firestore/SQL. Việc kiểm tra “key chưa tồn tại” rồi ghi ở hai bước không atomic có thể bị race khi hai instance xử lý cùng lúc.

Trong unit test, fake store có thể giả lập key đã tồn tại; trong integration test, chạy hai invocation đồng thời và xác nhận chỉ một side effect được commit.

## 13. Kiểm thử timeout, concurrency và bộ nhớ

Cloud Run functions chạy trên hạ tầng Cloud Run và chịu ràng buộc về timeout, CPU, bộ nhớ, concurrency và autoscaling theo cấu hình service. Local Functions Framework không tự mô phỏng chính xác những giới hạn này.

Thiết kế các kịch bản:

| Kịch bản | Cần xác minh |
|---|---|
| Dependency chậm | Timeout không vượt ngân sách request, có log hữu ích |
| Dependency trả lỗi | Exception được phân loại, không lộ secret |
| Hai invocation song song | Không dùng biến static mutable không đồng bộ |
| Khởi động lạnh | Thời gian khởi tạo client và kết nối nằm trong giới hạn |
| Memory pressure | Không đọc toàn bộ file lớn vào heap khi có thể stream |
| Hàm HTTP tạo background thread | Công việc phải hoàn thành hoặc được giao sang dịch vụ bền vững trước khi response |
| Retry do event handler lỗi | Side effect idempotent và có giới hạn số lần/thời gian retry |

Không coi việc gửi HTTP 200 rồi tiếp tục xử lý async trong một thread phụ là hoàn thành công việc đáng tin cậy. Cloud Run có thể giới hạn CPU hoặc kết thúc instance khi không còn request; với tác vụ dài, nên dùng Cloud Tasks, Pub/Sub hoặc Cloud Run Jobs/worker phù hợp.

## 14. Tích hợp kiểm thử vào CI/CD

Một pipeline gọn có thể chia ba cổng:

| Cổng | Nội dung | Khi nào |
|---|---|---|
| Pull request | Maven compile, JUnit/Mockito, static analysis | Mỗi thay đổi |
| Build artifact | Functions Framework local smoke, dependency scan, kiểm tra entry point | Sau merge hoặc trước release |
| Staging | Deploy Cloud Run function, gọi authenticated endpoint hoặc phát Eventarc event thử, kiểm tra output | Trước production |

Ví dụ Cloud Build chạy Maven unit test:

~~~yaml
steps:
  - name: 'maven:3.9-eclipse-temurin-17'
    entrypoint: 'mvn'
    args: ['-B', '-ntp', 'test']
timeout: '600s'
~~~

Đây là một **ví dụ CI tối thiểu**. Muốn chạy local integration trong Cloud Build, cần khởi động function server và chạy HTTP assertions trong cùng một step/job có quản lý lifecycle. Không giả định process nền khởi động ở step này sẽ tồn tại trong step tiếp theo.

Trong workflow thực tế:

1. Chạy unit/component tests độc lập với Google Cloud.
2. Khởi động Functions Framework trong job CI, chờ readiness trên cổng local.
3. Gửi HTTP/CloudEvents fixtures và kiểm tra kết quả.
4. Luôn dừng local process và thu thập log khi test kết thúc.
5. Build artifact, kiểm tra dependency/scanning và provenance nếu cần.
6. Deploy đến staging, chạy smoke/E2E; chỉ promote bản build đã được kiểm tra.
7. Chỉ dùng production credentials/traffic khi có quy trình phát hành được phê duyệt.

Việc ghi artifact test nên kèm commit SHA, entry point, test result và version Java/runtime để có thể tái lập sự cố.

## 15. Kiểm thử sau triển khai trên Cloud Run staging

### 15.1. Deploy HTTP function đã qua test

Cloud Run có lệnh deploy từ source với flag --function xác định entry point và --base-image chọn Java runtime.

Ví dụ:

~~~bash
gcloud run deploy greeting-function-staging \
  --source . \
  --function com.example.functions.GreetingFunction \
  --base-image java21 \
  --region asia-southeast1 \
  --no-allow-unauthenticated
~~~

JDK dùng để compile phải tương thích runtime deploy. Nếu build sử dụng Java 17 như ví dụ Maven, Java 21 có thể chạy bytecode Java 17; kiểm tra dependencies theo môi trường đã chọn.

Cloud Run source deploy cần những API và quyền triển khai/build phù hợp (Cloud Run, Cloud Build, Artifact Registry). Nên sử dụng service account runtime riêng và giới hạn IAM theo nhu cầu.

### 15.2. Gọi một function yêu cầu xác thực

Lấy URL thực của service:

~~~bash
gcloud run services describe greeting-function-staging \
  --region asia-southeast1 \
  --format="value(status.url)"
~~~

Giả sử URL đó được gán vào biến SERVICE_URL:

~~~bash
SERVICE_URL="https://YOUR-STAGING-SERVICE-URL"
curl -i \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$SERVICE_URL/?name=Lan"
~~~

Principal gọi endpoint phải có quyền Cloud Run Invoker trên service. ID token cũng phải có audience phù hợp. Nếu API yêu cầu auth, 401/403 không tự động chứng minh code function lỗi; hãy kiểm tra token và IAM trước.

Không mở --allow-unauthenticated chỉ để vượt qua một lỗi quyền trong staging hoặc production. Nếu thật sự cần public endpoint, thiết kế cơ chế chống lạm dụng, validation, rate limiting và xác thực cấp ứng dụng tùy chức năng.

### 15.3. Staging cho CloudEventsFunction

Để kiểm tra Eventarc thật, tạo trigger staging với đúng event type, region, nguồn sự kiện và trigger service account. Sau đó phát sự kiện vào bucket/topic staging.

Kiểm tra end-to-end:

- Trigger có nhận đúng event type và filter hay không?
- Trigger service account có quyền gọi Cloud Run service không?
- Function có nhận schema đúng và ghi log hợp lệ không?
- Side effect có xuất hiện đúng một lần về mặt nghiệp vụ dù event có thể được gửi lại?
- Retry, dead-letter/alerting và permission của các dịch vụ đích có hoạt động không?

Không thể xác minh các thuộc tính này chỉ bằng curl đến localhost. Local curl kiểm tra contract CloudEvent; staging kiểm tra cả Eventarc và Google Cloud IAM/network.

## 16. Observability, độ tin cậy và chi phí kiểm thử

Khi chạy local, logs từ Functions Framework và function thường xuất hiện ở terminal. Khi deploy, Cloud Logging ghi nhận request logs và application logs theo cấu hình Cloud Run. Cloud Monitoring cho phép dựng biểu đồ requests, latency, error rate và container resource usage.

Chỉ số nên theo dõi trong staging:

- Tỷ lệ response 2xx/4xx/5xx theo entry point.
- P50/P95/P99 latency và cold start khi phù hợp.
- Thời gian chạy dependency, retry và timeout.
- Số lần Eventarc gửi lại event và tỷ lệ event xử lý thành công.
- Memory, CPU và số instance.
- Quota và chi phí từ Cloud Run, Cloud Build, Pub/Sub, Cloud Storage hoặc các dịch vụ phụ trợ.

Kết nối log với request ID hoặc CloudEvent source/id để tra cứu. Không ghi trực tiếp token, password, secret hoặc payload chứa thông tin nhạy cảm. Khi tạo fixture có dữ liệu cá nhân, thay bằng dữ liệu tổng hợp.

Có thể giảm chi phí bằng cách chạy nhiều unit/local tests trước khi deploy, giữ staging resource đúng quy mô, giới hạn retry và dọn bucket/topic/database test khi hoàn thành. Tránh tạo trigger vĩnh viễn trên production topic chỉ để chạy smoke test.

## 17. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| ClassNotFound hoặc no function found | Sai package/entry point hoặc build output thiếu class | Dùng fully-qualified class name và kiểm tra cấu trúc src/main/java |
| mvn function:run không nhận goal | Maven plugin chưa khai báo hoặc dependency/plugin resolution lỗi | Kiểm tra pom.xml, Maven repository và function-maven-plugin |
| Port 8080 đã bị chiếm | Service khác đang listen | Dùng -Drun.port=8081 và đổi URL test |
| HTTP handler chạy nhưng test response body trống | BufferedWriter mock chưa flush | Flush trong unit test rồi assert StringWriter |
| HTTP POST trả 405 | Handler chỉ chấp nhận GET | Dùng GET theo contract hoặc bổ sung nhánh POST có kiểm thử |
| CloudEvent trả 400 trước khi vào accept | Thiếu ce-id, ce-source, ce-type, ce-specversion hoặc content type sai | Đối chiếu CloudEvents 1.0 binary headers và payload |
| Pub/Sub event không đọc được message | Nhầm event.data JSON với message.data Base64 | Parse envelope rồi decode Base64 |
| Event bị xử lý nhiều lần | Eventarc/PubSub at-least-once và retry | Thêm deduplication atomic theo event key |
| Local test PASS nhưng Cloud Run 403 | Principal thiếu run.invoker hoặc ID token sai audience | Kiểm tra IAM caller và Authorization Bearer token |
| Local test PASS nhưng staging thất bại | Thiếu quyền dịch vụ, secret, VPC route hoặc Eventarc trigger | Chạy staging integration và kiểm tra audit logs |
| Unit test lệ thuộc Internet/production | Code khởi tạo SDK client thật trong constructor | Trừu tượng dependency và dùng fake/mock ở unit test |
| Test bất ổn theo thời gian | Sleep cố định, timezone và external state không kiểm soát | Dùng clock injectable, deterministic fixture và readiness polling có timeout |
| Request timeout | Dependency chậm hoặc function xử lý quá lâu | Đặt timeout cho downstream, chuyển task dài sang queue/job |
| Test tiêu tốn tài nguyên | Không cleanup trigger/topic/bucket hoặc retry vô hạn | Dọn tài nguyên, giới hạn quy mô staging và cảnh báo chi phí |

## 18. Checklist trước khi phát hành

- [ ] Entry point là tên class Java đầy đủ, đúng HTTP hoặc CloudEvents interface.
- [ ] Dependency Functions Framework và Maven plugin được khai báo, version được kiểm soát.
- [ ] Có unit tests cho happy path, input thiếu, input sai và lỗi dependency.
- [ ] Không gọi dịch vụ production trong unit tests.
- [ ] Functions Framework khởi động trên localhost và nhận HTTP request thực.
- [ ] HTTP tests assert status, headers, body và timeout.
- [ ] CloudEvent fixtures có type, id, source, specversion và data hợp lệ.
- [ ] Pub/Sub message.data được decode Base64 khi cần.
- [ ] Event handler có chiến lược idempotency và retry rõ ràng.
- [ ] CI chạy Maven tests và local smoke tests trước bước deploy.
- [ ] Staging kiểm tra Cloud Run Invoker, Eventarc trigger và quyền runtime thật.
- [ ] Có logs/metrics cho error, latency và event processing.
- [ ] Không log secrets hoặc dùng dữ liệu production nhạy cảm làm fixture.
- [ ] Có rollback và quy trình cleanup resource của test.
- [ ] Cấu hình runtime, timeout, concurrency và region đã được xác minh.

## 19. Câu hỏi tự kiểm tra

**1. Functions Framework giúp kiểm thử điều gì trên máy local?**

Nó cung cấp HTTP server và cơ chế dispatch tới Java HttpFunction hoặc CloudEventsFunction để kiểm tra entry point, request/response và CloudEvents contract mà không phải deploy mỗi lần thay đổi.

**2. Vì sao unit test không cần chạy mvn function:run?**

Unit test có thể gọi trực tiếp service() hoặc accept() với mock/fake đối tượng đầu vào và dependency. Local invoker chủ yếu dùng ở integration test để kiểm tra framework thực sự nhận HTTP và dispatch đúng.

**3. Trên Java, function target là tên method hay class?**

Là tên class đầy đủ gồm package, ví dụ com.example.functions.GreetingFunction. Java Functions Framework tự suy ra signature từ interface được implement.

**4. HTTP function và CloudEvent function khác nhau ở đầu vào nào?**

HTTP function nhận HttpRequest và HttpResponse. CloudEvent function nhận CloudEvent chứa id, source, type và data, được framework chuyển từ HTTP CloudEvents envelope.

**5. Vì sao Pub/Sub fixture có Base64?**

Trong CloudEvent Pub/Sub, message.data được Base64-encode trong JSON envelope. Function cần parse envelope và decode dữ liệu này.

**6. Vì sao event-driven function phải xử lý trùng lặp?**

Eventarc/Pub/Sub có thể giao lại cùng một event khi retry hoặc mất ack. Side effect cần idempotent, thường bằng key được ghi atomic theo source/id.

**7. Local test PASS có bảo đảm function được Eventarc kích hoạt ở production không?**

Không. Local test không kiểm chứng trigger, IAM, VPC, secret hay service account thực. Những thuộc tính đó cần staging integration/E2E tests.

## 20. Tài liệu tham khảo

- [Google Cloud: Write Cloud Run functions](https://cloud.google.com/run/docs/write-functions)
- [Google Cloud: Develop functions locally](https://cloud.google.com/run/docs/local-dev-functions)
- [Google Cloud: Java dependencies for Cloud Run functions](https://cloud.google.com/run/docs/runtimes/java-dependencies)
- [Google Cloud: Deploy a Cloud Run function](https://cloud.google.com/run/docs/deploy-functions)
- [Google Cloud: Function triggers](https://cloud.google.com/run/docs/function-triggers)
- [Functions Framework for Java: GitHub](https://github.com/GoogleCloudPlatform/functions-framework-java)
- [Google Cloud Java sample: HTTP method types](https://cloud.google.com/functions/docs/samples/functions-http-method)
- [Google Cloud Java sample: Cloud Storage CloudEvent unit test](https://cloud.google.com/functions/docs/samples/functions-cloudevent-storage-unit-test)
- [Google Cloud Java sample: Pub/Sub CloudEvent unit test](https://cloud.google.com/functions/docs/samples/functions-cloudevent-pubsub-unit-test)
- [Google Cloud: Eventarc triggers for Cloud Run functions](https://cloud.google.com/run/docs/tutorials/pubsub-eventdriven)
- [CloudEvents specification](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md)
- [CloudEvents Java SDK](https://github.com/cloudevents/sdk-java)

