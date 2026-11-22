# Tùy chỉnh endpoint bằng @EndpointWebExtension hoặc @EndpointJmxExtension

## 1. Endpoint chung và cách biểu diễn theo từng kênh

Một endpoint Actuator có thể phục vụ hai nhóm công cụ: công cụ gọi HTTP và công cụ quản trị JVM qua JMX. Dữ liệu quản trị có thể giống nhau, nhưng cách biểu diễn và thông tin đi kèm khác nhau. HTTP có mã trạng thái và phần thân JSON; JMX làm việc với MBean và các thao tác quản trị.

Ví dụ, một hàng đợi đang tạm ngừng nhận việc vẫn cần trả về số công việc tồn đọng. Công cụ giám sát HTTP muốn nhận JSON kèm mã `503`; người vận hành trong JConsole muốn đọc một chuỗi ngắn. Nếu đặt quyết định về mã HTTP vào endpoint chung, phần dùng qua JMX sẽ bị gắn với khái niệm của HTTP.

Trong Actuator, **extension là lớp cung cấp các thao tác bổ sung hoặc thay thế cho một endpoint đã có, theo một công nghệ truy cập cụ thể**:

- `@EndpointWebExtension` áp dụng cho HTTP.
- `@EndpointJmxExtension` áp dụng cho JMX.
- `endpoint = TenLopEndpoint.class` chỉ ra lớp endpoint được mở rộng.

Các annotation này liên kết với một endpoint, không tự tạo một ID quản trị mới. Ý nghĩa của thuộc tính `endpoint` được mô tả trong [API EndpointWebExtension của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/EndpointWebExtension.html).

Trong bài này, ta dùng Spring Boot **3.3.13** và mã nguồn Java **17+**. Chương trình và kiểm thử bên dưới đã được chạy trên Java 21.

## 2. Chọn đúng điểm mở rộng

| Nhu cầu | Thành phần phù hợp |
| --- | --- |
| Tạo endpoint quản trị có mô hình chung cho nhiều kênh | `@Endpoint` |
| Tạo endpoint mới chỉ phục vụ HTTP | `@WebEndpoint` |
| Tạo endpoint mới chỉ phục vụ JMX | `@JmxEndpoint` |
| Điều chỉnh cách một endpoint hiện có phục vụ HTTP | `@EndpointWebExtension` |
| Điều chỉnh cách một endpoint hiện có phục vụ JMX | `@EndpointJmxExtension` |

Ví dụ, nếu `workqueue` đã có dữ liệu hàng đợi chung và chỉ cần bổ sung mã HTTP, chọn web extension. Nếu muốn tạo một chức năng quản trị độc lập với ID khác, hãy thiết kế endpoint mới. Tài liệu [Implementing Custom Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom) trình bày các loại endpoint và extension theo công nghệ.

Trước khi viết extension, cũng nên kiểm tra endpoint đang dùng có sẵn thuộc tính cấu hình hoặc thành phần mở rộng chuyên biệt hay chưa. Chẳng hạn, bổ sung một phép kiểm tra sức khỏe thường phù hợp với `HealthIndicator` hơn là tự viết thêm web extension cho `health`.

## 3. Cơ chế phát hiện và thay thế thao tác

### 3.1. Lớp phải thực sự là Spring bean

Annotation extension mô tả vai trò của lớp. Lớp vẫn phải được đăng ký thành bean bằng `@Bean` hoặc bằng một stereotype phù hợp như `@Component` và được quét đúng phạm vi.

Luồng xử lý có thể hình dung như sau:

1. Spring có bean endpoint gốc và bean extension.
2. Actuator phát hiện các phương thức có `@ReadOperation`, `@WriteOperation` hoặc `@DeleteOperation`.
3. Bộ phát hiện dành cho HTTP chọn web extension; bộ dành cho JMX chọn JMX extension.
4. Actuator kết hợp các thao tác gốc với thao tác của extension, thay thế những thao tác có cùng khóa nhận diện.
5. Các thao tác được xuất ra kênh quản trị theo cấu hình exposure.

Extension thường nhận endpoint gốc qua constructor để sử dụng lại dữ liệu và logic. Actuator không tự gọi endpoint gốc trước hoặc sau extension. Nếu cần giữ xử lý gốc, extension phải chủ động gọi nó.

### 3.2. HTTP và JMX có khóa nhận diện khác nhau

**Với HTTP**, khóa được tạo từ điều kiện khớp yêu cầu (`request predicate`), gồm đường dẫn, phương thức HTTP và điều kiện kiểu nội dung. Tên phương thức Java không quyết định URL.

Ví dụ trong bài có hai phương thức:

- Endpoint gốc: `@ReadOperation Snapshot snapshot()`.
- Web extension: `@ReadOperation WebEndpointResponse<Map<String, Object>> overview()`.

Cả hai cùng ánh xạ thao tác đọc ở gốc `workqueue`, với các điều kiện nội dung mặc định tương ứng giống nhau. Vì vậy, web extension thay thế thao tác HTTP dù tên `overview` khác `snapshot`. Cách tạo khóa có thể xem trong [WebEndpointDiscoverer 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/annotation/WebEndpointDiscoverer.java).

Nếu thêm `@Selector` làm đường dẫn khác hoặc đổi điều kiện `produces`, phải xét lại toàn bộ predicate. Hai phương thức cùng gắn `@ReadOperation` chưa đủ để kết luận rằng một phương thức sẽ thay thế phương thức kia. Thêm tham số truy vấn cũng không phải cách tách hai thao tác HTTP có cùng predicate.

**Với JMX trong Spring Boot 3.3.13**, khóa thao tác là tên thao tác JMX. Trong ví dụ, extension giữ tên `snapshot` để thay thế thao tác đó. Đổi tên thành `summary` sẽ bổ sung tên thao tác mới; `snapshot` gốc vẫn còn. Không áp dụng cách suy luận overload Java theo danh sách kiểu tham số để thiết kế các thao tác JMX trùng tên.

Các quy tắc kết hợp và khóa JMX có thể đối chiếu trong [EndpointDiscoverer](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/annotation/EndpointDiscoverer.java) và [JmxEndpointDiscoverer](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/jmx/annotation/JmxEndpointDiscoverer.java) của phiên bản này.

### 3.3. Phạm vi thay thế

Web extension chỉ thay đổi các thao tác xuất qua HTTP; JMX extension chỉ thay đổi các thao tác xuất qua JMX. Thao tác gốc có khóa khác vẫn được giữ lại.

Lệnh gọi Java trực tiếp như `endpoint.snapshot()` vẫn gọi phương thức trên đối tượng endpoint gốc. Extension không phải cơ chế `extends`, không cần `@Override`, và không biến endpoint gốc thành một đối tượng khác.

Trong Spring Boot 3.3.13, mỗi endpoint chỉ có tối đa một extension được chọn bởi mỗi bộ phát hiện công nghệ. Có thể đồng thời có một web extension và một JMX extension. Nhiều bean web extension cho cùng endpoint không được ghép như một chuỗi xử lý có thứ tự; hãy gộp trách nhiệm hoặc dùng điều kiện cấu hình để chỉ còn một bean phù hợp.

## 4. Ví dụ hoàn chỉnh: một hàng đợi, hai cách quan sát

Ta xây dựng endpoint `workqueue` với dữ liệu sau:

- `accepting`: hàng đợi có đang nhận công việc mới hay không, ban đầu là `false`.
- `pending`: số công việc tồn đọng, cố định bằng `7` để tập trung vào cơ chế extension.
- `setAccepting`: thao tác quản trị đổi cờ nhận việc.

Đây là mô hình tối giản cho thí nghiệm; chưa triển khai hàng đợi hoặc bộ xử lý công việc thật. Cờ dùng `AtomicBoolean` để các lời gọi HTTP/JMX có thể quan sát thay đổi trạng thái chung.

Cấu trúc dự án độc lập:

```text
endpoint-extension-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/demo/DemoApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/demo/ExtensionTest.java
```

### 4.1. Khai báo thư viện

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>endpoint-extension-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build><plugins><plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
    </plugin></plugins></build>
</project>
```

`spring-boot-starter-web` cung cấp Spring MVC và máy chủ nhúng; `spring-boot-starter-actuator` cung cấp endpoint và extension; `spring-boot-starter-test` dùng cho phần kiểm thử. Dự án kế thừa cấu hình biên dịch của Spring Boot, bao gồm lưu tên tham số để Actuator ánh xạ đầu vào `accepting`.

### 4.2. Endpoint gốc và hai extension

Tạo `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.boot.actuate.endpoint.jmx.annotation.EndpointJmxExtension;
import org.springframework.boot.actuate.endpoint.web.WebEndpointResponse;
import org.springframework.boot.actuate.endpoint.web.annotation.EndpointWebExtension;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    WorkQueueEndpoint workQueueEndpoint() {
        return new WorkQueueEndpoint();
    }

    @Bean
    WorkQueueWebExtension workQueueWebExtension(WorkQueueEndpoint endpoint) {
        return new WorkQueueWebExtension(endpoint);
    }

    @Bean
    WorkQueueJmxExtension workQueueJmxExtension(WorkQueueEndpoint endpoint) {
        return new WorkQueueJmxExtension(endpoint);
    }

    public record Snapshot(boolean accepting, int pending) { }

    @Endpoint(id = "workqueue")
    public static class WorkQueueEndpoint {
        private final AtomicBoolean accepting = new AtomicBoolean(false);

        @ReadOperation
        public Snapshot snapshot() {
            return new Snapshot(accepting.get(), 7);
        }

        @WriteOperation
        public void setAccepting(boolean accepting) {
            this.accepting.set(accepting);
        }
    }

    @EndpointWebExtension(endpoint = WorkQueueEndpoint.class)
    public static class WorkQueueWebExtension {
        private final WorkQueueEndpoint endpoint;

        public WorkQueueWebExtension(WorkQueueEndpoint endpoint) {
            this.endpoint = endpoint;
        }

        @ReadOperation
        public WebEndpointResponse<Map<String, Object>> overview() {
            Snapshot snapshot = endpoint.snapshot();
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("accepting", snapshot.accepting());
            body.put("pending", snapshot.pending());
            int status = snapshot.accepting()
                    ? WebEndpointResponse.STATUS_OK
                    : WebEndpointResponse.STATUS_SERVICE_UNAVAILABLE;
            return new WebEndpointResponse<>(body, status);
        }
    }

    @EndpointJmxExtension(endpoint = WorkQueueEndpoint.class)
    public static class WorkQueueJmxExtension {
        private final WorkQueueEndpoint endpoint;

        public WorkQueueJmxExtension(WorkQueueEndpoint endpoint) {
            this.endpoint = endpoint;
        }

        @ReadOperation
        public String snapshot() {
            Snapshot snapshot = endpoint.snapshot();
            return "accepting=" + snapshot.accepting()
                    + ",pending=" + snapshot.pending();
        }
    }
}
```

Ba phương thức `@Bean` đăng ký tường minh endpoint và hai extension. Các lớp được đặt lồng trong một tệp để dễ chạy thử; trong ứng dụng lớn có thể tách thành các tệp riêng mà vẫn giữ cách liên kết bằng constructor.

**Endpoint gốc** chỉ biết `Snapshot` và thao tác thay đổi trạng thái. Nó không trả mã HTTP hoặc chuỗi trình bày dành cho JMX.

**Web extension** gọi `endpoint.snapshot()`, dựng phần thân JSON và chọn mã phản hồi. `WebEndpointResponse` cho phép cung cấp phần thân cùng mã trạng thái HTTP; đây là mục đích được mô tả trong [API WebEndpointResponse](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/WebEndpointResponse.html). Cần chọn đúng constructor `(body, status)`; constructor chỉ nhận `body` dùng mã mặc định `200`.

**JMX extension** lấy cùng một `Snapshot` rồi chuyển thành `String`, nên người vận hành đọc được cả hai trường trong một thao tác. Không đưa `WebEndpointResponse` vào JMX vì nó mang ý nghĩa phản hồi HTTP.

Cả hai extension chỉ khai báo thao tác đọc. Thao tác ghi `setAccepting` của endpoint gốc vẫn có mặt ở cả HTTP và JMX. Việc gọi lại endpoint gốc giúp hai kênh dùng cùng một trạng thái.

### 4.3. Cấu hình HTTP và JMX

Tạo `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
spring.jmx.enabled=true
management.endpoints.web.exposure.include=health,workqueue
management.endpoints.jmx.exposure.include=workqueue
```

Trong thí nghiệm:

- HTTP phục vụ tại địa chỉ loopback của máy chạy chương trình.
- `workqueue` được đưa vào danh sách xuất qua HTTP.
- `spring.jmx.enabled=true` bật tích hợp JMX của Spring.
- Danh sách xuất JMX có `workqueue`.

Khi endpoint được cấu hình enablement/exposure, các danh sách sử dụng ID `workqueue` của endpoint gốc. Không sử dụng tên bean hoặc tên lớp extension.

JMX của Spring Boot mặc định chưa bật; quy tắc đặt tên MBean và cấu hình được trình bày trong [Monitoring and Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html). Bật `spring.jmx.enabled` không đồng nghĩa với mở một cổng JMX từ xa. Bài này chỉ dùng MBeanServer trong JVM và kết nối JConsole cục bộ.

Dự án mẫu không thêm Spring Security. Khi đưa thao tác quản trị thay đổi trạng thái vào ứng dụng thật, cần kiểm soát quyền truy cập tương ứng cho từng kênh. Bảo vệ HTTP bằng `SecurityFilterChain` không tự bảo vệ một kết nối JMX từ xa.

## 5. Chạy và quan sát

### 5.1. Biên dịch và khởi động

Tại thư mục có `pom.xml`, chạy:

```shell
mvn package
java -jar target/endpoint-extension-demo-1.0.0.jar
```

Maven biên dịch mã Java cùng các thư viện cần thiết; sau đó `java -jar` chạy ứng dụng. Lần đầu cần tải dependency. Cổng HTTP mặc định là `8080`; nếu máy đang dùng cổng này, đổi `server.port` và thay URL tương ứng trong các lệnh.

### 5.2. HTTP ban đầu: mã 503 nhưng vẫn có dữ liệu

Ở cửa sổ terminal khác:

```shell
curl -i -H 'Accept: application/json' http://127.0.0.1:8080/actuator/workqueue
```

Hai thông tin cần quan sát trong phản hồi là mã trạng thái **503** và phần thân JSON:

```json
{"accepting":false,"pending":7}
```

Các header HTTP còn lại có thể khác theo môi trường. JSON trên là phần thân, không phải toàn bộ đầu ra của `curl -i`.

Nếu chỉ dùng thao tác đọc gốc trả `Snapshot`, việc có đối tượng kết quả không tự suy ra mã `503` từ trường `accepting=false`. Quyết định đó nằm trong web extension.

Mã `503` ở đây chỉ là quy ước của endpoint `workqueue`. Nó không tự thay đổi kết quả `health`, trạng thái readiness, hoặc cấu hình kiểm tra của bộ cân bằng tải.

### 5.3. Gọi thao tác ghi được giữ lại từ endpoint gốc

Trong shell hỗ trợ dấu nháy đơn như Bash:

```shell
curl -i -X POST -H 'Content-Type: application/json' -d '{"accepting":true}' http://127.0.0.1:8080/actuator/workqueue
```

Trong PowerShell, có thể dùng lệnh tương đương sau để tránh khác biệt khi truyền dấu nháy cho chương trình native:

```powershell
Invoke-WebRequest -Method Post -Uri 'http://127.0.0.1:8080/actuator/workqueue' -ContentType 'application/json' -Body '{"accepting":true}'
```

Kết quả của POST là **204 No Content**. Phương thức ghi trả `void`, nên không có phần thân kết quả. Extension không khai báo thao tác ghi, nhưng Actuator vẫn giữ `setAccepting` của endpoint gốc.

Gọi lại GET:

```shell
curl -i -H 'Accept: application/json' http://127.0.0.1:8080/actuator/workqueue
```

Lúc này mã trạng thái là **200** và phần thân:

```json
{"accepting":true,"pending":7}
```

Đường dẫn HTTP không chứa tên `overview` hoặc `setAccepting`. Với cấu hình này, GET và POST cùng dùng `/actuator/workqueue`; loại operation quyết định phương thức HTTP.

### 5.4. Quan sát cùng trạng thái bằng JConsole

Với ứng dụng vẫn đang chạy:

1. Chạy `jconsole` từ một JDK có công cụ này, dưới tài khoản có quyền kết nối JVM đang chạy.
2. Chọn tiến trình `DemoApplication` trong danh sách tiến trình cục bộ.
3. Mở tab **MBeans**, tìm domain `org.springframework.boot`.
4. Tìm MBean có ObjectName `org.springframework.boot:type=Endpoint,name=Workqueue`.
5. Mở **Operations** và gọi `snapshot`.

Nếu đã thực hiện POST ở trên, giá trị trả về là:

```text
accepting=true,pending=7
```

Tên `Workqueue` trong ObjectName được tạo từ ID `workqueue` theo cấu hình mặc định của thí nghiệm; nó không phải `WorkQueueWebExtension`. Nếu đổi domain hoặc bật tên duy nhất trong ứng dụng có nhiều context, cần chọn ObjectName thực tế.

Gọi `setAccepting` với giá trị boolean `false` trên cùng MBean. Gọi lại `snapshot`:

```text
accepting=false,pending=7
```

Sau đó GET qua HTTP lại trả **503**. Điều này cho thấy hai cách biểu diễn dùng chung endpoint và trạng thái, thay vì tạo hai bản dữ liệu quản trị riêng.

Nếu muốn xem trạng thái ban đầu, khởi động lại ứng dụng. Cờ được giữ trong bộ nhớ và khởi tạo lại thành `false`.

## 6. Kiểm thử cả hai đường xuất dữ liệu

Chỉ gọi trực tiếp `new WorkQueueWebExtension(...).overview()` chưa kiểm tra được Actuator có phát hiện bean, thay thế đúng thao tác hoặc giữ thao tác gốc hay không. Ta cần kiểm tra cả ánh xạ HTTP của Actuator và MBean đã được đăng ký.

Tạo `src/test/java/com/example/demo/ExtensionTest.java`:

```java
package com.example.demo;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "spring.jmx.enabled=true")
@AutoConfigureMockMvc
class ExtensionTest {
    @Autowired MockMvc http;
    @Autowired MBeanServer mbeans;
    @Autowired DemoApplication.WorkQueueEndpoint endpoint;

    @Test
    void webAndJmxUseDifferentExtensionsAndRetainTheWriteOperation() throws Exception {
        ObjectName name = new ObjectName("org.springframework.boot:type=Endpoint,name=Workqueue");
        endpoint.setAccepting(false);
        assertThat(endpoint.snapshot()).isEqualTo(new DemoApplication.Snapshot(false, 7));
        http.perform(get("/actuator/workqueue"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(content().json("{\"accepting\":false,\"pending\":7}", true));
        assertThat(mbeans.invoke(name, "snapshot", new Object[0], new String[0]))
                .isEqualTo("accepting=false,pending=7");

        http.perform(post("/actuator/workqueue")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"accepting\":true}"))
                .andExpect(status().isNoContent());
        http.perform(get("/actuator/workqueue"))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"accepting\":true,\"pending\":7}", true));
        assertThat(mbeans.invoke(name, "snapshot", new Object[0], new String[0]))
                .isEqualTo("accepting=true,pending=7");

        mbeans.invoke(name, "setAccepting", new Object[]{false}, new String[]{"boolean"});
        http.perform(get("/actuator/workqueue"))
                .andExpect(status().isServiceUnavailable());
    }
}
```

Chạy:

```shell
mvn test
```

Phần tổng kết kiểm thử thành công có:

```text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Các dòng log khởi động, thời gian chạy và cảnh báo JVM có thể khác.

Kiểm thử này sử dụng **MockMvc**, đi qua cơ chế ánh xạ và xử lý HTTP của ứng dụng trong bộ nhớ; nó không mở cổng TCP. Phần JMX gọi MBeanServer thật trong cùng JVM, không tạo kết nối JMX từ xa.

`@SpringBootTest(properties = "spring.jmx.enabled=true")` bật JMX tường minh cho lần kiểm thử. Spring Boot mặc định vô hiệu hóa JMX trong ngữ cảnh kiểm thử `@SpringBootTest`, nên không nên chỉ dựa vào cấu hình của lần chạy ứng dụng thông thường.

Các điều kiện được kiểm tra:

| Đường gọi | Kết quả được xác nhận |
| --- | --- |
| Gọi Java trực tiếp `endpoint.snapshot()` | Vẫn nhận `Snapshot(false, 7)` từ endpoint gốc |
| GET khi chưa nhận việc | Web extension trả 503 và đúng hai trường JSON |
| JMX `snapshot` | JMX extension trả chuỗi của cùng trạng thái |
| POST `accepting=true` | Thao tác ghi gốc còn tồn tại, trả 204 |
| GET sau POST | Trả 200 và `accepting=true` |
| JMX sau POST | Nhìn thấy trạng thái `true` |
| JMX `setAccepting(false)` rồi GET | Thao tác ghi gốc đổi cùng trạng thái; HTTP trở lại 503 |

Kết quả này đồng thời kiểm chứng việc thay thế thao tác đọc theo từng kênh và việc bảo toàn thao tác ghi.

## 7. Các lỗi thường gặp và cách xác định nguyên nhân

### Có annotation nhưng extension không được dùng

Kiểm tra bean có được đăng ký không, lớp chứa `@Bean` có được nạp không, và `endpoint = ...class` có trỏ đúng lớp endpoint gốc không. Chỉ đặt annotation lên một lớp nằm ngoài phạm vi cấu hình chưa tạo được bean.

Nếu endpoint gốc có điều kiện khởi tạo, hãy bảo đảm extension chỉ được tạo khi endpoint tương ứng tồn tại. Extension không thể làm nguồn dữ liệu thay cho một endpoint gốc chưa được đăng ký.

### HTTP vẫn trả kết quả gốc hoặc có ánh xạ xung đột

Đối chiếu predicate của hai thao tác: HTTP method, đường dẫn sinh từ ID/`@Selector`, điều kiện consumes và produces. Cùng tên phương thức Java không bảo đảm cùng ánh xạ HTTP.

Ngược lại, hai thao tác đọc trong cùng lớp có cùng predicate có thể xung đột dù tên Java khác nhau. Hãy thiết kế đường dẫn và loại operation rõ ràng, rồi kiểm thử qua HTTP mapping.

### JMX xuất hiện cả thao tác cũ lẫn thao tác mới

Kiểm tra tên thao tác. Trong phiên bản dùng ở bài, `summary` là khóa khác `snapshot`. Nếu mục tiêu là thay thế `snapshot`, extension phải cung cấp đúng tên đó.

### Endpoint không truy cập được

Phân biệt ba lớp kiểm tra: bean/operation được phát hiện; endpoint được cho phép xuất qua kênh đang dùng; lời gọi được tầng bảo mật cho phép.

Với thí nghiệm này, cần xác minh đúng ID trong `management.endpoints.web.exposure.include` hoặc `management.endpoints.jmx.exposure.include`. Khi có cấu hình `exclude`, nó ưu tiên hơn `include`. Khi tích hợp vào ứng dụng khác, kiểm tra thêm cấu hình enablement, base path và management port.

### HTTP trả 401 hoặc 403

Đây có thể là kết quả của xác thực, phân quyền hoặc CSRF khi ứng dụng có Spring Security. Đừng kết luận extension chưa được phát hiện chỉ từ các mã này. Mẫu độc lập ở bài không có thư viện Security; ứng dụng thực tế có thể có cấu hình khác.

### POST báo lỗi đầu vào

JSON cần có thuộc tính `accepting` khớp tên tham số. Mã nguồn phải được biên dịch có thông tin tên tham số, chẳng hạn bằng cấu hình parent Spring Boot trong `pom.xml` ở trên. Kiểm tra cả kiểu boolean và `Content-Type`.

### Có nhiều extension cùng công nghệ cho một endpoint

Tránh đăng ký đồng thời hai web extension cho `workqueue`. Việc thêm `@Order` không biến chúng thành các bộ lọc nối tiếp. Nếu nhiều cấu hình cùng đóng góp bean, cần làm rõ điều kiện chọn một extension.

Đối với endpoint dựng sẵn như `health`, trước hết xác định extension hoặc thành phần chuyên biệt mà Boot đã cung cấp; đừng giả định có thể thêm một web extension thứ hai để tự động bổ sung hành vi.

### Dữ liệu quản trị bị cũ

Nếu ứng dụng cấu hình `management.endpoint.workqueue.cache.time-to-live` lớn hơn 0, thao tác đọc không có tham số có thể được cache. Khi kiểm tra thay đổi tức thời như bài này, giữ TTL bằng 0 để không nhầm dữ liệu cache với lỗi extension. Dự án mẫu không cấu hình TTL dương.

## 8. Thực hành có kết quả đối chiếu

1. **Bỏ đăng ký web extension, giữ endpoint gốc và JMX extension.** Sau khi khởi động lại với trạng thái `false`, HTTP dùng thao tác đọc gốc và không còn quyết định trả 503 từ `overview`. JMX vẫn trả chuỗi từ extension của nó.
2. **Bỏ đăng ký JMX extension, giữ web extension.** HTTP tiếp tục dùng `overview`; JMX dùng thao tác gốc. Cách hiển thị kiểu dữ liệu gốc cần được quan sát qua công cụ JMX, thay vì giả định nó giống chuỗi của extension.
3. **Đổi tên phương thức web extension từ `overview` thành `inspect`.** Giữ nguyên operation và điều kiện ánh xạ; URL GET vẫn là `/actuator/workqueue`.
4. **Trong JMX extension, đổi `snapshot` thành `summary`.** Quan sát danh sách Operations để thấy thao tác mới được thêm, còn `snapshot` gốc không còn bị thay thế.
5. **Chỉ expose `workqueue` qua HTTP.** Xác minh việc HTTP hoạt động không kéo theo việc MBean `workqueue` phải được xuất qua JMX.

Sau mỗi thay đổi, khởi động lại ứng dụng và xác minh cả hai kênh. Với thay đổi có chủ ý làm khác hợp đồng, cập nhật kỳ vọng kiểm thử tương ứng trước khi đánh giá kết quả.

Khi thiết kế extension cho một endpoint khác, hãy xác định rõ: dữ liệu dùng chung nằm ở đâu, kênh nào cần cách biểu diễn riêng, thao tác nào bị thay thế, thao tác nào cần được giữ lại, và điều kiện nào cho phép xuất dữ liệu quản trị.
