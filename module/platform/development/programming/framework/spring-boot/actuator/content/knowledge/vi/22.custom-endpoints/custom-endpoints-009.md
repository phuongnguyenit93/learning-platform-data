# Thiết kế kiểu trả về, nội dung JSON và phản hồi tài nguyên

## 1. Hiểu phản hồi của endpoint trước khi chọn kiểu Java

Một endpoint Actuator tùy chỉnh thường phục vụ người vận hành, công cụ chẩn đoán hoặc chương trình tự động. Phía sử dụng cần biết kết quả có ý nghĩa gì, có thể đọc theo cấu trúc nào và khi nào nên xem lần gọi là thất bại. Vì vậy, thiết kế phản hồi là thiết kế một **hợp đồng sử dụng**, không chỉ chọn một kiểu để câu lệnh `return` biên dịch được.

Có ba quyết định liên quan nhưng khác nhau:

- **Kiểu Java trả về:** chẳng hạn một record chứa số liệu, một `Map` nhỏ hoặc một `Resource` chứa nội dung báo cáo.
- **Biểu diễn trên HTTP:** JSON, văn bản thuần hoặc dữ liệu nhị phân; thể hiện qua `Content-Type` và phần thân phản hồi.
- **Ý nghĩa HTTP:** mã 200, 204, 404, 503… cho biết kết quả xử lý yêu cầu theo hợp đồng đã chọn.

Ví dụ, `state="UNAVAILABLE"` là một giá trị trong dữ liệu. Nó không tự biến phản hồi thành HTTP 503. Tương tự, một chuỗi trông giống đường dẫn tệp không làm máy chủ tự đọc và gửi tệp đó.

Trong chương Endpoint tùy chỉnh, thao tác đọc trả lời câu hỏi “ứng dụng đang quan sát được điều gì?”. Một DTO gọn giúp chương trình giám sát đọc các trường ổn định; một phản hồi tài nguyên giúp người vận hành lấy đúng nội dung báo cáo. Hai nhu cầu có thể dùng hai endpoint khác nhau, thay vì bắt một URL lúc trả JSON, lúc trả một kiểu dữ liệu không liên quan.

Bài sử dụng mô hình Spring Boot 3.3.x với Spring MVC. Ví dụ đầy đủ ở phần 6 dùng Java 21 và Spring Boot 3.3.0 để cố định môi trường thực hành; các record trong ví dụ dùng cú pháp có từ Java 17.

## 2. Chọn kiểu trả về theo dữ liệu cần công bố

| Nhu cầu | Kiểu có thể dùng | Điều cần quyết định trước |
| --- | --- | --- |
| Báo cáo có cấu trúc, dùng lâu dài | DTO hoặc `record` | Tên trường, kiểu dữ liệu, đơn vị, ý nghĩa giá trị |
| Một tập trường nhỏ, thay đổi ít | `Map<String, Object>` | Giữ tên khóa và kiểu giá trị nhất quán |
| Một danh sách kết quả | `List<ItemView>` hoặc DTO bao ngoài | Giới hạn số phần tử, thứ tự, trường hợp danh sách rỗng |
| Một giá trị đơn | Số, boolean hoặc chuỗi | Người đọc có đủ ngữ cảnh để hiểu giá trị không? |
| Nội dung báo cáo hoặc tệp | `Resource` | Định dạng, kích thước, khả năng mở lại luồng đọc |
| Cần điều khiển trạng thái HTTP | `WebEndpointResponse<T>` trong phần xử lý dành cho web | Phân biệt dữ liệu `T` với thông tin HTTP |
| Thao tác thực sự không cần phần thân | `void` hoặc kết quả `null` phù hợp | Hành vi HTTP mặc định có đúng ý nghĩa mong muốn không? |

DTO là đối tượng dành riêng cho dữ liệu trao đổi. Không cần gửi toàn bộ đối tượng nghiệp vụ chỉ vì đối tượng đó đang có sẵn trong bộ nhớ. Một thực thể lưu trữ có thể mang theo liên kết vòng, trường nội bộ hoặc chi tiết triển khai mà công cụ vận hành không cần biết.

Ví dụ, yêu cầu “cho biết số công việc đang chạy và thời gian lần chạy gần nhất” có thể dùng:

```java
public record JobSnapshot(
        long activeJobs,
        long lastRunDurationMillis,
        java.util.List<String> warnings) {
}
```

Đây là khai báo kiểu minh họa, chưa phải một ứng dụng độc lập. Ba trường đã cho người đọc biết số lượng, đơn vị thời gian và danh sách cảnh báo. So với trả `Object`, chữ ký `JobSnapshot` giúp người sửa mã thấy ngay hình dạng kết quả dự kiến.

`record` chỉ bất biến ở mức tham chiếu thành phần; một `List` có thể thay đổi vẫn có thể bị sửa từ nơi khác. Nếu tạo kết quả từ danh sách dùng chung, hãy chụp dữ liệu cần thiết và dùng bản sao phù hợp, chẳng hạn `List.copyOf(warnings)` khi các phần tử không null. Khi số liệu được cập nhật đồng thời, việc tạo record không tự bảo đảm rằng mọi trường được đọc ở cùng một thời điểm; tính nhất quán của bản chụp phải được xử lý ở nơi thu thập số liệu.

Với `Map`, vấn đề thường nằm ở hợp đồng yếu hơn:

```java
// Hai kết quả có cùng tên khóa nhưng khác kiểu dữ liệu.
java.util.Map<String, Object> first = java.util.Map.of("activeJobs", 3L);
java.util.Map<String, Object> second = java.util.Map.of("activeJobs", "3 jobs");
```

Đoạn trên minh họa một thay đổi làm chương trình đọc số bị hỏng. Dùng `Map` không sai, nhưng phải quản lý tên khóa và kiểu giá trị cẩn thận như khi dùng DTO. `Map.of` cũng không chấp nhận khóa hoặc giá trị null.

## 3. Thiết kế JSON để chương trình khác đọc ổn định

### 3.1. Đặt tên và đơn vị ngay trong hợp đồng

Giả sử endpoint trả:

```json
{
  "schemaVersion": 1,
  "state": "READY",
  "activeJobs": 3,
  "lastRunDurationMillis": 42,
  "warnings": []
}
```

Đây là cấu trúc JSON do ví dụ của bài định nghĩa. `schemaVersion` là trường do ứng dụng tự thiết kế, không phải trường Actuator tự thêm.

| Trường | Ý nghĩa đã chọn trong ví dụ |
| --- | --- |
| `schemaVersion` | Phiên bản cấu trúc dữ liệu mà phía sử dụng hiểu |
| `state` | Trạng thái do phép chẩn đoán này định nghĩa |
| `activeJobs` | Số công việc, dùng JSON number |
| `lastRunDurationMillis` | Thời lượng lần chạy gần nhất, đơn vị mili giây |
| `warnings` | Danh sách thông báo; không có cảnh báo là `[]` |

Không dùng một trường `duration` rồi lúc trả giây, lúc trả mili giây. Không ghép đơn vị vào một chuỗi nếu phía sử dụng cần so sánh số. Nếu có thời điểm quan sát, có thể thiết kế trường như `observedAt` với chuỗi ISO 8601 có độ lệch múi giờ, nhưng phải thống nhất định dạng và kiểm tra bộ chuyển đổi JSON thực tế.

Tên trường, kiểu, đơn vị và ý nghĩa đều là một phần của hợp đồng. Đổi `activeJobs` thành `running` hoặc đổi số thành chuỗi có thể làm hỏng chương trình sử dụng dù URL vẫn giữ nguyên. Thêm một trường cũng cần kiểm tra phía nhận có chấp nhận trường lạ hay không; không mặc định rằng mọi thay đổi bổ sung đều tương thích.

Không yêu cầu chương trình đọc JSON phụ thuộc vào thứ tự các thuộc tính. Với danh sách, ngược lại, thứ tự phần tử có thể mang ý nghĩa; nếu danh sách được sắp theo mức độ ưu tiên thì hãy ghi rõ quy tắc đó.

### 3.2. Phân biệt không có phần tử, chưa biết và không tìm thấy

- `warnings: []`: đã xác định danh sách và hiện không có phần tử.
- `lastRunDurationMillis: null`: có thể biểu diễn “chưa có lần chạy”, nếu hợp đồng quy định như vậy.
- Không có trường `lastRunDurationMillis`: phía nhận cần biết đây là trường tùy chọn, bị lược bỏ hay cấu trúc không đúng phiên bản.
- Cả kết quả thao tác là `null`: không còn là một trường JSON null bên trong DTO; nó có thể ảnh hưởng đến trạng thái HTTP.

Không dùng số `0` để đồng thời biểu diễn “thời lượng bằng không” và “chưa đo”. Khi một trường có thể chưa biết, chọn kiểu tham chiếu phù hợp như `Long` hoặc thiết kế trạng thái đo riêng. Đừng dựa vào việc đổi từ `long` sang `Long` để tự có ý nghĩa nghiệp vụ; ý nghĩa đó phải được mô tả.

Một danh sách rỗng vẫn là một kết quả có giá trị. Chẳng hạn, yêu cầu “liệt kê công việc đang chạy” có thể trả HTTP 200 với `[]`. Nó khác yêu cầu “đọc công việc theo ID” khi ID không tồn tại.

### 3.3. Để bộ chuyển đổi JSON xử lý đối tượng

Khi muốn gửi JSON có cấu trúc, trả DTO hoặc `Map` rồi để cơ chế chuyển đổi HTTP xử lý. Đừng nối chuỗi từ dữ liệu bên ngoài để tạo JSON; dấu nháy, xuống dòng và ký tự đặc biệt dễ làm kết quả sai.

Không nên viết `return "{\"activeJobs\":3}";` chỉ để thay một DTO. `String` là kiểu dữ liệu khác; lựa chọn bộ chuyển đổi và cách thể hiện chuỗi còn phụ thuộc cấu hình. Việc một phản hồi cụ thể trông giống JSON không biến chữ ký đó thành hợp đồng đối tượng có kiểu.

Đối với Actuator 3.3, có thuộc tính `management.endpoints.jackson.isolated-object-mapper`, mặc định `true`. Vì vậy, khi điều chỉnh cách đặt tên hoặc định dạng JSON ở ứng dụng, cần xác minh phản hồi Actuator thực tế thay vì giả định cấu hình đó luôn được dùng chung. Ví dụ trong bài dùng tên trường trực tiếp, kiểu số và danh sách đơn giản để giảm phụ thuộc vào cấu hình bổ sung. [Thuộc tính Jackson của Actuator 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### 3.4. Công bố đúng dữ liệu người vận hành cần

Hãy lập danh sách trường được phép trả về, thay vì đưa một đối tượng lớn lên HTTP rồi tìm cách che bớt về sau. Ví dụ chẩn đoán hàng đợi thường cần số lượng và trạng thái; không cần mật khẩu, token, nội dung yêu cầu của người dùng hay toàn bộ chuỗi kết nối.

Đừng coi quy tắc che giá trị của các endpoint có sẵn như `env` là bảo đảm cho mọi trường trong DTO tùy chỉnh. Mỗi trường mới cần được xem xét tại nơi tạo phản hồi. Với danh sách hoặc báo cáo lớn, đặt giới hạn dữ liệu và chi phí tạo kết quả; một endpoint chẩn đoán không nên làm ứng dụng quá tải chỉ vì bị gọi liên tục.

## 4. Quan hệ giữa giá trị trả về và trạng thái HTTP

### 4.1. Hành vi mặc định cần hiểu

Khi chưa dùng lớp bọc điều khiển HTTP, Actuator ánh xạ kết quả thao tác theo các trường hợp sau:

| Loại thao tác | Kết quả | Mã HTTP mặc định |
| --- | --- | --- |
| `@ReadOperation` | Có giá trị, kể cả danh sách rỗng | 200 |
| `@ReadOperation` | Không có giá trị | 404 |
| `@WriteOperation` hoặc `@DeleteOperation` | Có giá trị | 200 |
| `@WriteOperation` hoặc `@DeleteOperation` | Không có giá trị | 204 |

Vì vậy, trả `void` từ thao tác đọc thường không phù hợp nếu mong muốn một phản hồi thành công có nội dung. Cũng cần phân biệt `null` ở cấp kết quả với DTO có một thành phần null. [Quy tắc trạng thái phản hồi của endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.response-status).

### 4.2. Điều khiển trạng thái bằng WebEndpointResponse

`WebEndpointResponse<T>` chứa phần thân `T`, trạng thái và khả năng chỉ định kiểu nội dung. Ví dụ một phương thức thuộc phần mở rộng dành cho web có thể trả:

```java
return new WebEndpointResponse<>(
        body,
        WebEndpointResponse.STATUS_SERVICE_UNAVAILABLE);
```

Đây là đoạn thân phương thức minh họa; `body` là DTO đã tạo ở phương thức đó. Với lớp bọc này, JSON được gửi là DTO ở `body`, không phải một đối tượng JSON bắt buộc có các khóa `body` và `status`. `WebEndpointResponse` không phải cơ chế thêm tùy ý mọi header HTTP. [API WebEndpointResponse 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/WebEndpointResponse.html).

Dùng `@EndpointWebExtension` khi endpoint gốc cung cấp dữ liệu và phần mở rộng cần thêm quyết định dành riêng cho HTTP. Trong ví dụ đầy đủ, endpoint gốc trả `Snapshot`; web extension dùng chính bản chụp đó để quyết định 200 hay 503. `@EndpointWebExtension(endpoint = DiagnosticsEndpoint.class)` xác định endpoint mà phần mở rộng bổ sung hành vi. [API EndpointWebExtension](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/EndpointWebExtension.html).

Ở đây, 503 là **quyết định thiết kế của phép chẩn đoán mẫu**: người gọi coi `READY` là thành công, các trạng thái khác là chưa sẵn sàng. Một endpoint chỉ báo cáo thông tin vẫn có thể dùng 200 và mô tả một cảnh báo trong JSON. Cần chọn ý nghĩa trước rồi mã hóa nó, tránh để người giám sát suy đoán.

Đừng cho rằng `ResponseEntity` trong một operation Actuator được xử lý y hệt giá trị trả về của phương thức `@RestController`. Operation đi qua cơ chế xử lý endpoint của Actuator. Với mẫu trong bài, dùng đúng `WebEndpointResponse` để điều khiển trạng thái; khi cần header hoặc cơ chế tải tệp đặc thù của Spring MVC, lựa chọn lớp xử lý HTTP phù hợp và kiểm tra bằng yêu cầu thực tế.

## 5. JSON, kiểu nội dung và tài nguyên là những việc khác nhau

`Content-Type` mô tả biểu diễn mà máy chủ gửi. `Accept` thể hiện các kiểu nội dung phía gọi chấp nhận. Thuộc tính `produces` của operation tham gia xác định biểu diễn được hỗ trợ; nó không tự chuyển một record thành PDF hay tự biến chuỗi đường dẫn thành nội dung tệp.

Với kiểu trả về `Resource`, mặc định operation dùng `application/octet-stream`; có thể chỉ định rõ kiểu khác. Ví dụ dùng `text/plain;charset=UTF-8` cho báo cáo văn bản và `application/json` cho DTO. Quy tắc mặc định còn phân biệt `void`/`Void` với các kết quả có nội dung. [Quy tắc produces của Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.request-predicates.produces).

Nếu một URL chỉ hỗ trợ JSON mà người gọi chỉ chấp nhận `text/html`, phản hồi có thể là 406. Đổi `Accept` không phải yêu cầu máy chủ tự tạo một biểu diễn mà endpoint chưa hỗ trợ.

Trong mẫu có endpoint gốc và web extension cùng thay thế một thao tác đọc, cả hai dùng cùng `produces = "application/json"`. Giữ nhất quán hợp đồng ánh xạ ở hai phía, thay vì vô tình tạo hai operation khác nhau cạnh tranh trên cùng URL. Đây cũng là điều cần kiểm tra khi gặp lỗi ánh xạ mơ hồ sau khi thêm extension.

## 6. Ví dụ đầy đủ: JSON có kiểu và báo cáo văn bản

Ứng dụng có hai URL:

- `GET /actuator/diagnostics` trả bản chụp JSON. Web extension đặt trạng thái 200 hoặc 503.
- `GET /actuator/diagnosticreport` trả nội dung một tài nguyên văn bản.

`@WebEndpoint` được dùng cho báo cáo chỉ dành cho HTTP. Nó khác `@Endpoint` ở phạm vi công nghệ được công bố. [API WebEndpoint 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/WebEndpoint.html).

### 6.1. Cấu trúc dự án độc lập

```text
actuator-response-demo/
├── pom.xml
└── src/main/
    ├── java/example/actuator/DemoApplication.java
    └── resources/application.properties
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>actuator-response-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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

Nội dung `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=18080
management.endpoints.web.exposure.include=health,diagnostics,diagnosticreport
```

Đây là cấu hình cho thí nghiệm trên máy cá nhân. Hai starter ở trên không thêm Spring Security. Nếu đưa endpoint vào ứng dụng đã có bảo mật, kết quả truy cập còn phụ thuộc quy tắc xác thực và phân quyền của ứng dụng đó.

### 6.2. Mã Java

Nội dung `src/main/java/example/actuator/DemoApplication.java`:

```java
package example.actuator;

import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.web.WebEndpointResponse;
import org.springframework.boot.actuate.endpoint.web.annotation.EndpointWebExtension;
import org.springframework.boot.actuate.endpoint.web.annotation.WebEndpoint;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;

@SpringBootApplication(proxyBeanMethods = false)
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    DiagnosticsEndpoint diagnosticsEndpoint(
            @Value("${demo.state:READY}") String state) {
        return new DiagnosticsEndpoint(state);
    }

    @Bean
    DiagnosticsWebExtension diagnosticsWebExtension(DiagnosticsEndpoint endpoint) {
        return new DiagnosticsWebExtension(endpoint);
    }

    @Bean
    DiagnosticReportEndpoint diagnosticReportEndpoint() {
        return new DiagnosticReportEndpoint();
    }

    public record Snapshot(
            int schemaVersion,
            String state,
            long activeJobs,
            long lastRunDurationMillis,
            List<String> warnings) {
    }

    @Endpoint(id = "diagnostics")
    public static class DiagnosticsEndpoint {
        private final String state;

        public DiagnosticsEndpoint(String state) {
            this.state = state;
        }

        @ReadOperation(produces = "application/json")
        public Snapshot snapshot() {
            return new Snapshot(1, state, 3L, 42L, List.of());
        }
    }

    @EndpointWebExtension(endpoint = DiagnosticsEndpoint.class)
    public static class DiagnosticsWebExtension {
        private final DiagnosticsEndpoint endpoint;

        public DiagnosticsWebExtension(DiagnosticsEndpoint endpoint) {
            this.endpoint = endpoint;
        }

        @ReadOperation(produces = "application/json")
        public WebEndpointResponse<Snapshot> snapshot() {
            Snapshot body = endpoint.snapshot();
            int status = "READY".equals(body.state())
                    ? WebEndpointResponse.STATUS_OK
                    : WebEndpointResponse.STATUS_SERVICE_UNAVAILABLE;
            return new WebEndpointResponse<>(body, status);
        }
    }

    @WebEndpoint(id = "diagnosticreport")
    public static class DiagnosticReportEndpoint {

        @ReadOperation(produces = "text/plain;charset=UTF-8")
        public Resource report() {
            byte[] content = "status=READY\nactiveJobs=3\n"
                    .getBytes(StandardCharsets.UTF_8);
            return new ByteArrayResource(content);
        }
    }
}
```

Ba phương thức `@Bean` đăng ký endpoint và extension. Các lớp lồng được dùng để ví dụ nằm trọn trong một tệp; có thể tách thành các tệp cùng package mà vẫn giữ nguyên trách nhiệm.

`DiagnosticsEndpoint` trả dữ liệu; `DiagnosticsWebExtension` thêm quyết định HTTP. `DiagnosticReportEndpoint` tạo một báo cáo cố định, độc lập với thuộc tính `demo.state`, để dễ quan sát riêng đường đi của `Resource`. Các số 3 và 42 là dữ liệu mẫu, không phải số liệu mà Actuator tự đo.

### 6.3. Biên dịch và chạy

Từ thư mục có `pom.xml`, dùng Maven với JDK 21:

```shell
mvn clean package
java -jar target/actuator-response-demo-1.0.0.jar
```

Maven tải các phụ thuộc khi máy chưa có chúng. Trong thí nghiệm này, `javac DemoApplication.java` đơn lẻ không đủ vì mã cần các thư viện Spring trên classpath. Lệnh Maven xử lý phần biên dịch và đóng gói đó.

Mở terminal khác. Các lệnh dưới đây dùng `curl.exe` trên Windows để tránh nhầm với alias PowerShell; trên hệ điều hành khác dùng `curl`.

```powershell
curl.exe -sS -i -H "Accept: application/json" http://127.0.0.1:18080/actuator/diagnostics
```

Phần phản hồi liên quan:

```http
HTTP/1.1 200
Content-Type: application/json

{"schemaVersion":1,"state":"READY","activeJobs":3,"lastRunDurationMillis":42,"warnings":[]}
```

Các header khác có thể xuất hiện. JSON trên mô tả chính xác giá trị của mẫu; phía nhận phải đọc theo tên trường, không dựa vào thứ tự thuộc tính hoặc khoảng trắng.

Để quan sát trạng thái không sẵn sàng, dừng tiến trình Java bằng `Ctrl+C` rồi chạy lại:

```shell
java -jar target/actuator-response-demo-1.0.0.jar --demo.state=UNAVAILABLE
```

Gọi lại URL chẩn đoán:

```http
HTTP/1.1 503
Content-Type: application/json

{"schemaVersion":1,"state":"UNAVAILABLE","activeJobs":3,"lastRunDurationMillis":42,"warnings":[]}
```

`state` được đưa vào DTO từ cấu hình. Chính logic trong web extension chọn 503; không phải Jackson hoặc tên trường `state` tự suy ra trạng thái HTTP.

### 6.4. Nhận nội dung tài nguyên

```powershell
curl.exe -sS -i http://127.0.0.1:18080/actuator/diagnosticreport
```

Phần phản hồi liên quan:

```http
HTTP/1.1 200
Content-Type: text/plain;charset=UTF-8

status=READY
activeJobs=3
```

Phần thân là `status=READY\nactiveJobs=3\n`: có xuống dòng sau cả hai dòng, tổng cộng **26 byte** vì toàn bộ ký tự đều thuộc ASCII. Đây là nội dung tài nguyên, không phải JSON mô tả một đối tượng `Resource`.

Muốn lưu về máy:

```powershell
curl.exe -sS -o diagnostic-report.txt http://127.0.0.1:18080/actuator/diagnosticreport
```

Tên `diagnostic-report.txt` ở đây do phía gọi chọn qua `-o`. Nó không chứng minh máy chủ đã gửi header `Content-Disposition`, cũng không phải tên tệp mà `ByteArrayResource` bắt buộc phải có.

### 6.5. Yêu cầu một phần tài nguyên

```powershell
curl.exe -sS -i -H "Range: bytes=0-5" http://127.0.0.1:18080/actuator/diagnosticreport
```

Với mẫu Spring MVC và `ByteArrayResource` này:

```http
HTTP/1.1 206
Content-Type: text/plain;charset=UTF-8
Content-Range: bytes 0-5/26

status
```

Vị trí bắt đầu từ 0 và vị trí cuối 5 được tính vào khoảng, nên có sáu byte: `status`. Phần thân thực tế của yêu cầu này không có ký tự xuống dòng ở cuối. Nếu dùng `Range: bytes=100-110`, mẫu trả 416 vì khoảng yêu cầu nằm ngoài tài nguyên dài 26 byte.

Hỗ trợ Range của endpoint trả `Resource` được tài liệu Actuator nêu cho Spring MVC và WebFlux; Jersey không hỗ trợ theo cùng cơ chế. Không suy rộng kết quả của tài nguyên mở lại được sang mọi loại luồng đọc. [Range request trong Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.range-requests).

Cuối cùng, thử một kiểu nội dung không được endpoint JSON hỗ trợ:

```powershell
curl.exe -sS -i -H "Accept: text/html" http://127.0.0.1:18080/actuator/diagnostics
```

Mẫu trả 406. Đây là vấn đề thương lượng kiểu nội dung, khác với 503 do web extension chủ động trả sau khi đọc dữ liệu.

## 7. Thiết kế phản hồi tài nguyên trong ứng dụng thực tế

### 7.1. Resource mô tả cách đọc nội dung

`Resource` là trừu tượng truy cập nội dung của Spring. Với một phản hồi tài nguyên, lớp xử lý HTTP cần có cách mở nội dung để ghi ra phản hồi. Chọn triển khai dựa trên nơi dữ liệu đang tồn tại:

| Triển khai | Phù hợp khi | Điểm cần xét |
| --- | --- | --- |
| `ByteArrayResource` | Nội dung nhỏ đã có dưới dạng `byte[]` | Toàn bộ dữ liệu nằm trong bộ nhớ |
| `FileSystemResource` | Báo cáo đã tồn tại trên hệ thống tệp | Quyền đọc, vòng đời và tính ổn định của tệp |
| `ClassPathResource` | Tài nguyên được đóng gói cùng ứng dụng | Không mặc định tài nguyên bên trong JAR là một `File` thông thường |
| `InputStreamResource` | Trường hợp cần bọc một luồng dùng một lần | Không coi là nguồn có thể đọc lại tùy ý |

Với `ByteArrayResource`, mỗi lần cần đọc có thể mở một luồng trên mảng byte. Kích thước bộ nhớ tăng theo kích thước nội dung, nên mẫu này hợp với báo cáo nhỏ. Với báo cáo lớn, việc gọi `Files.readAllBytes` rồi bọc lại vẫn nạp toàn bộ tệp vào bộ nhớ; thay tên kiểu trả về không làm mất chi phí đó. [Trừu tượng và các triển khai Resource](https://docs.spring.io/spring-framework/reference/core/resources.html).

Ví dụ một phương thức trả báo cáo đã được tạo sẵn có thể dùng:

```java
// Đoạn minh họa trong một lớp đã có trường approvedReportPath kiểu Path.
@ReadOperation
public Resource report() {
    return new org.springframework.core.io.FileSystemResource(approvedReportPath);
}
```

`approvedReportPath` trong đoạn minh họa là đường dẫn mà ứng dụng đã xác định và kiểm soát. Việc tạo `FileSystemResource` không bảo đảm tệp sẽ còn tồn tại hoặc còn quyền đọc khi HTTP bắt đầu ghi nội dung. Luồng được mở khi đọc, và các thao tác như lấy độ dài hoặc đọc tệp có thể thất bại. [API FileSystemResource](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/io/FileSystemResource.html).

Nếu cần chọn báo cáo từ đầu vào, ưu tiên ID báo cáo được ánh xạ tới danh sách tài nguyên cho phép. Không chuyển trực tiếp chuỗi đường dẫn hoặc URL bất kỳ của người gọi thành tài nguyên để đọc. Giới hạn kích thước và dữ liệu được công bố vẫn phải áp dụng cho nội dung tệp như với JSON.

### 7.2. Luồng đọc phải còn dùng được khi ghi phản hồi

Không mở luồng bằng `try-with-resources`, bọc nó trong `InputStreamResource` rồi trả về sau khi khối `try` kết thúc. Khi đó luồng đã đóng trước lúc lớp xử lý HTTP đọc nó.

`InputStreamResource` mang đặc điểm dùng một lần; không giữ lại một instance để dùng chung cho nhiều yêu cầu và không giả định nó hỗ trợ việc đọc lặp lại. Khi cần biết kích thước, tua tới vị trí hoặc phục vụ Range, khả năng của nguồn dữ liệu phải được xét cụ thể. [API InputStreamResource 6.1](https://docs.spring.io/spring-framework/docs/6.1.7/javadoc-api/org/springframework/core/io/InputStreamResource.html).

Một tài nguyên đã mở lại được cũng cần nội dung ổn định. Nếu tệp bị ghi đè giữa hai lần yêu cầu Range, phía tải có thể ghép các phần từ hai phiên bản khác nhau. Với báo cáo lớn, có thể thiết kế mỗi báo cáo hoàn tất thành một bản bất biến rồi mới công bố ID tải về.

### 7.3. Phân biệt nội dung, tên tệp và thông tin HTTP

Ba điều sau không đồng nghĩa:

1. `Resource` cung cấp nội dung để đọc.
2. `Content-Type` cho biết định dạng phần thân.
3. `Content-Disposition` có thể gợi ý cách tải và tên tệp cho trình khách.

Không mặc định `getFilename()` hoặc phần mô tả của resource sẽ tạo đúng header tải xuống mong muốn trong mọi cơ chế xử lý HTTP. Nếu yêu cầu bắt buộc có tên tệp, header bộ đệm hoặc cơ chế tải đặc thù, cần chọn phần xử lý web hỗ trợ yêu cầu đó và kiểm tra header thực tế.

Cũng không trộn một kết quả thành công dạng tệp với lỗi dạng JSON mà vẫn giữ một kiểu nội dung cố định không phù hợp. Ví dụ, `application/octet-stream` cùng phần thân JSON lỗi khiến phía tải có thể lưu lỗi thành tệp báo cáo. Hợp đồng phải mô tả rõ trạng thái lỗi, phần thân và kiểu nội dung mà người gọi cần xử lý.

## 8. Lỗi thiết kế thường gặp và cách sửa

| Hiện tượng | Nguyên nhân có thể có | Hướng xử lý |
| --- | --- | --- |
| JSON vẫn về 200 dù có trường `error` | Trường dữ liệu không điều khiển HTTP | Quyết định ý nghĩa thành công/thất bại và dùng phản hồi web phù hợp |
| Thao tác đọc trả 404 ngoài dự kiến | Kết quả thao tác là null hoặc không có giá trị | Phân biệt không tìm thấy với danh sách rỗng và kiểm tra chữ ký |
| Thêm web extension rồi ánh xạ bị mơ hồ | Operation gốc và extension không cùng hợp đồng ánh xạ | Đối chiếu selector, thao tác và `produces` |
| Phía nhận chỉ thấy một đường dẫn | Đang trả `String` chứa đường dẫn | Nếu cần nội dung tệp, cung cấp `Resource` đúng nguồn |
| JSON thay đổi theo cấu trúc đối tượng nội bộ | Trả trực tiếp đối tượng không dành cho giao tiếp | Tạo DTO có các trường được chọn rõ ràng |
| Chương trình đọc số bị lỗi | Cùng một trường lúc là số, lúc là chuỗi | Cố định kiểu và đặt đơn vị rõ |
| Báo cáo tải về rỗng hoặc đọc lỗi | Luồng đã đóng, bị đọc trước hoặc dùng lại | Kiểm soát vòng đời và chọn Resource phù hợp |
| Một yêu cầu báo cáo tiêu tốn quá nhiều bộ nhớ | Tạo mảng byte cho tệp lớn | Tránh nạp toàn bộ nội dung khi không cần; giới hạn kích thước |
| Đổi cấu hình JSON nhưng Actuator không như dự kiến | Cấu hình bộ chuyển đổi không phải cấu hình đang được dùng | Kiểm tra cấu hình Jackson của Actuator và phản hồi thật |
| Gọi URL JSON bằng `Accept: text/html` nhận 406 | Endpoint không có biểu diễn được chấp nhận | Dùng kiểu nội dung endpoint hỗ trợ |

Khi chẩn đoán, kiểm tra theo thứ tự: URL và operation được ánh xạ → kiểu nội dung được chấp nhận → giá trị mà phương thức thực sự trả → cơ chế xử lý HTTP → JSON hoặc byte đã nhận. Đừng chỉ kiểm tra một lệnh gọi phương thức Java rồi kết luận rằng toàn bộ hợp đồng HTTP đúng.

## 9. Thực hành kiểm tra hợp đồng

Thực hiện trên ứng dụng mẫu:

1. Gọi endpoint JSON với `Accept: application/json`. Xác minh `activeJobs` là số và `warnings` là mảng rỗng.
2. Khởi động lại với `--demo.state=UNAVAILABLE`. Xác minh vừa có HTTP 503, vừa có `state="UNAVAILABLE"` trong JSON.
3. Tải báo cáo và kiểm tra đủ hai dòng cùng ký tự xuống dòng cuối. Không diễn giải báo cáo này thành JSON.
4. Gửi `Range: bytes=0-5`. Xác minh trạng thái 206, tổng độ dài 26 và đúng sáu byte `status`.
5. Gửi khoảng vượt kích thước và kiểu `Accept` không hỗ trợ. Phân biệt lỗi 416 với 406.
6. Thiết kế thêm trường “thời điểm lần chạy gần nhất”. Trước khi viết mã, xác định biểu diễn thời gian, múi giờ và ý nghĩa khi chưa có lần chạy.

Tự kiểm tra các quyết định:

- **Không có cảnh báo có cần trả null không?** Không. Với hợp đồng mẫu, `[]` thể hiện danh sách đã biết và đang rỗng.
- **Record có trường null có bắt buộc trả 404 không?** Không. DTO vẫn là kết quả có giá trị; null của toàn kết quả là trường hợp khác.
- **Đặt `produces="application/pdf"` có tạo được PDF từ một DTO không?** Không. Cần thực sự cung cấp nội dung PDF và cơ chế ghi tương ứng.
- **Đổi báo cáo sang FileSystemResource có bảo đảm không dùng bộ nhớ hay không lỗi I/O không?** Không. Nó thay cách truy cập nguồn; chi phí đọc, ghi và lỗi của hệ thống tệp vẫn tồn tại.
- **Một kiểm thử gọi `snapshot()` có đủ chứng minh HTTP 503 không?** Không. Cần đi qua lớp xử lý web để kiểm tra trạng thái, kiểu nội dung và phần thân cùng nhau.
