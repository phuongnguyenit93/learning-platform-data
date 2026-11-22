# Ánh xạ tham số từ đường dẫn bằng @Selector

## 1. Vì sao endpoint cần selector?

Giả sử ứng dụng đang theo dõi các tác vụ theo nhóm. Cùng mã tác vụ `7` có thể xuất hiện trong cả nhóm `exports` lẫn `imports`. Người vận hành muốn xem trạng thái của một tác vụ cụ thể:

```http
GET /actuator/jobstate/exports/7
```

Hai giá trị `exports` và `7` là những phần chọn dữ liệu của endpoint `jobstate`. Với Actuator, ta mô tả chúng bằng `@Selector` trên tham số phương thức thao tác:

```java
@ReadOperation
public JobState read(@Selector String group, @Selector int jobId) {
    return jobs.get(new JobKey(group, jobId));
}
```

Đây là trích đoạn phương thức để đọc ý tưởng; các kiểu `JobState`, `JobKey` và Map `jobs` có đầy đủ trong dự án ở mục 4.

`@Selector` đánh dấu tham số chọn một phần dữ liệu của endpoint. Khi công bố qua HTTP, tham số selector trở thành biến trong đường dẫn. [Spring Boot: Selector API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/endpoint/annotation/Selector.html)

Mục tiêu của bài là hiểu cách URL được ghép, giá trị được đưa vào đúng tham số và lỗi được phân loại. Việc thêm selector không tự tạo bean, mở exposure hay cấp quyền truy cập.

## 2. Đọc đường dẫn theo từng phần

Với cấu hình mặc định của ví dụ:

```text
/actuator /jobstate /exports /7
    |         |        |     |
base path  endpoint   group  jobId
              ID
```

Template mà thao tác cần là:

```text
/actuator/jobstate/{group}/{jobId}
```

Dấu ngoặc nhọn mô tả biến đường dẫn, không phải ký tự người gọi phải nhập vào URL thực tế.

| Thành phần | Nguồn quyết định | Ví dụ |
| --- | --- | --- |
| `/actuator` | Base path công bố endpoint qua web | Mặc định của dự án |
| `jobstate` | `@Endpoint(id = "jobstate")` | ID endpoint |
| `{group}` | Tham số selector thứ nhất | `exports` |
| `{jobId}` | Tham số selector thứ hai | `7` |

Thứ tự selector trong phương thức quyết định thứ tự các đoạn selector của thao tác. Với chữ ký ở trên, `/exports/7` đúng thứ tự; `/7/exports` đưa `exports` vào tham số số nguyên và không đáp ứng hợp đồng đó.

Tên phương thức `read()` không được thêm vào URL. Không gọi `/actuator/jobstate/read/exports/7` trừ khi có một hợp đồng đường dẫn khác được định nghĩa rõ.

Base path còn có thể thay đổi theo cấu hình của ứng dụng. Các URL trong bài giả định không cấu hình context path hay cổng quản trị riêng.

## 3. @Selector khác tham số query và @PathVariable thế nào?

### 3.1. Selector là một phần cấu trúc đường dẫn

Trong ví dụ:

```text
Đúng dạng thao tác:
/actuator/jobstate/exports/7

Không thay thế được hai đoạn selector:
/actuator/jobstate?group=exports&jobId=7
```

Tham số query không tự bổ sung những đoạn đường dẫn còn thiếu. Nếu không có thao tác đọc nào ở đường dẫn gốc `/actuator/jobstate`, request thứ hai không chọn được thao tác ở `/{group}/{jobId}`.

Trong thao tác Actuator, tham số không đánh dấu selector có thể nhận dữ liệu từ query hoặc nội dung request theo loại thao tác. Tham số mang `@Selector` được dùng để mở rộng đường dẫn khi công bố qua web. [Spring Boot 3.3: đầu vào và đường dẫn của endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom-endpoints)

### 3.2. Không thay bằng annotation của controller

| Ngữ cảnh | Cơ chế phù hợp |
| --- | --- |
| Phương thức thao tác trên Actuator endpoint | `@Selector` |
| Phương thức controller Spring MVC có `@RequestMapping` | `@PathVariable` theo hợp đồng controller |
| Tham số lọc không nằm trong đường dẫn | Tham số query thích hợp với loại thao tác |

Lớp `@Endpoint` không phải một controller chỉ vì nó cuối cùng được truy cập qua HTTP. Thêm `@PathVariable` không thay thế vai trò xây dựng đường dẫn của `@Selector`.

Import cần dùng là:

```java
import org.springframework.boot.actuate.endpoint.annotation.Selector;
```

`@Selector` không có thuộc tính để viết cả template URL như `"/jobs/{id}"`. Trong trường hợp thường dùng, chỉ cần đặt annotation trước tham số. Ở trường hợp lấy nhiều đoạn còn lại, dùng thuộc tính `match` như mục 7.

## 4. Dự án chạy đầy đủ: chọn tác vụ theo nhóm và mã

Dự án dùng Spring Boot 3.3.13, Java 21 và Spring MVC. Hai endpoint đều chỉ đọc:

- `jobstate`: hai selector đơn, trong đó `jobId` được đổi sang `int`.
- `pathview`: một selector đầu và một selector lấy các đoạn còn lại.

Dữ liệu tác vụ trong ví dụ là dữ liệu mẫu bất biến, không kết nối hệ thống hàng đợi thật.

### 4.1. Cấu trúc

```text
actuator-selector-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/selector/
    │   │   ├── SelectorDemoApplication.java
    │   │   ├── JobStateEndpoint.java
    │   │   └── PathViewEndpoint.java
    │   └── resources/application.properties
    └── test/
        └── java/example/selector/SelectorEndpointTest.java
```

### 4.2. pom.xml

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
    <groupId>example</groupId>
    <artifactId>actuator-selector-demo</artifactId>
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

`spring-boot-starter-web` cung cấp hạ tầng web; Actuator cung cấp cơ chế endpoint; starter test hỗ trợ kiểm chứng ánh xạ. Các phiên bản thư viện được parent Boot quản lý.

### 4.3. Lớp khởi động

Nội dung `SelectorDemoApplication.java`:

```java
package example.selector;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SelectorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SelectorDemoApplication.class, args);
    }
}
```

Các lớp endpoint nằm cùng package với lớp khởi động. Chúng mang `@Component` để được Spring tạo bean qua quét thành phần. Trong một ứng dụng có tổ chức package khác, phải bảo đảm endpoint nằm trong phạm vi được nạp.

### 4.4. JobStateEndpoint.java

```java
package example.selector;

import java.util.Map;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.Selector;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "jobstate")
public class JobStateEndpoint {
    private final Map<JobKey, JobState> jobs = Map.of(
            new JobKey("exports", 7),
            new JobState("exports", 7, "DONE"),
            new JobKey("exports", 8),
            new JobState("exports", 8, "RUNNING"),
            new JobKey("imports", 7),
            new JobState("imports", 7, "WAITING"));

    @ReadOperation
    public JobState read(@Selector String group, @Selector int jobId) {
        return jobs.get(new JobKey(group, jobId));
    }

    private record JobKey(String group, int jobId) {
    }

    public record JobState(String group, int jobId, String state) {
    }
}
```

Cùng mã `7` được gắn với hai nhóm khác nhau. `JobKey` chứa cả nhóm và mã, nên có thể quan sát được rằng **cả hai selector đều tham gia chọn dữ liệu**.

`@ReadOperation` xác định thao tác đọc. `@Selector String group` nhận đoạn đầu; `@Selector int jobId` nhận đoạn tiếp theo sau khi chuyển đổi kiểu.

Phương thức không nhận `HttpServletRequest` và không tự tách chuỗi URL. Bộ thích ứng web của Actuator thực hiện phần ánh xạ rồi mới gọi logic đọc.

### 4.5. Cấu hình HTTP

Nội dung `application.properties`:

```properties
spring.application.name=actuator-selector-demo
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,jobstate,pathview
```

Ví dụ chỉ lắng nghe trên loopback để thử cục bộ. Hai endpoint được đưa vào danh sách HTTP exposure. `@Selector` không thay thế điều kiện endpoint phải được đăng ký, được bật và được công bố.

Cấu hình exposure dùng ID `jobstate`, không dùng chuỗi `jobstate/exports/7`. Selector là phần đường dẫn của thao tác, không tạo endpoint ID mới.

## 5. Điều gì xảy ra khi nhận request?

Với `GET /actuator/jobstate/exports/7`, có thể đọc quá trình theo các bước:

```text
1. Chọn thao tác GET có dạng /jobstate/{group}/{jobId}
2. Lấy group = "exports", jobId = "7" từ đường dẫn
3. Đổi "7" sang int
4. Gọi read("exports", 7)
5. Tra dữ liệu theo khóa (group, jobId)
6. Chuyển JobState thành JSON phản hồi
```

Kết quả:

```json
{"group":"exports","jobId":7,"state":"DONE"}
```

Nếu đổi nhóm:

```http
GET /actuator/jobstate/imports/7
```

thì kết quả là:

```json
{"group":"imports","jobId":7,"state":"WAITING"}
```

Các trường và giá trị JSON là hợp đồng cần kiểm tra; thứ tự thành viên hoặc khoảng trắng không phải điều kiện về ý nghĩa dữ liệu.

### 5.1. Chuyển đổi kiểu không phải kiểm tra nghiệp vụ

Trong đường dẫn, `7` bắt đầu là dữ liệu dạng chuỗi. Actuator dùng cơ chế chuyển đổi đầu vào để cung cấp giá trị `int` cho phương thức. Một giá trị không đổi được sang kiểu yêu cầu làm request thất bại trước khi logic thao tác được gọi. [Spring Boot 3.3: Input Type Conversion](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom-endpoints.input-type-conversion)

Có kiểu `int` không có nghĩa mã tác vụ chắc chắn tồn tại hoặc luôn dương. Nếu quy tắc hệ thống yêu cầu mã dương, phải kiểm tra quy tắc đó ở logic phù hợp. Ví dụ này tra trong tập dữ liệu có sẵn; một mã số không tồn tại nhận kết quả không tìm thấy.

### 5.2. Phân biệt ba loại thất bại

| Request trong dự án mẫu | Kết quả | Nguyên nhân |
| --- | --- | --- |
| `/actuator/jobstate/exports/not-a-number` | 400 | Đúng hình dạng đường dẫn nhưng không đổi được `jobId` sang `int` |
| `/actuator/jobstate/exports` | 404 | Thiếu một đoạn, không khớp đường dẫn của thao tác |
| `/actuator/jobstate/exports/999` | 404 | Đã chọn được thao tác, nhưng phương thức trả `null` vì không có dữ liệu |
| `/actuator/jobstate/exports/7/extra` | 404 | Thừa đoạn so với hai selector đơn |
| `/actuator/jobstate?group=exports&jobId=7` | 404 | Query không thay được các đoạn selector và ví dụ không có thao tác gốc |

Hai request cùng trả 404 có thể thất bại ở hai bước khác nhau: chọn thao tác hoặc tìm dữ liệu. Không kết luận “selector bị lỗi” chỉ từ mã 404.

Với thao tác đọc, trả về một giá trị dẫn tới phản hồi 200; không có giá trị dẫn tới 404 theo quy tắc phản hồi của Actuator. [Spring Boot 3.3: Web Endpoint Response Status](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom-endpoints.web.response-status)

## 6. Tên tham số và tùy chọn biên dịch -parameters

Actuator cần thông tin tên tham số để ánh xạ đầu vào vào phương thức thao tác. Khi biên dịch Java, giữ tên tham số bằng tùy chọn `-parameters`. Spring Boot Maven parent trong dự án này cấu hình phần hỗ trợ cần thiết; plugin Gradle Boot cũng hỗ trợ cấu hình biên dịch theo hợp đồng đó. [Spring Boot 3.3: nhận đầu vào cho thao tác](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom-endpoints.receiving-input)

Nếu dùng một cấu hình build tự viết, đừng chỉ thấy mã Java biên dịch được rồi mặc định metadata tham số đã đúng. Một lỗi thiếu tên tham số có thể xuất hiện khi framework khám phá hoặc chuẩn bị gọi thao tác.

Những điều không nên nhầm:

- `group` và `jobId` là tên tham số Java, không phải hai chuỗi cố định phải xuất hiện trong URL cụ thể.
- URL cụ thể là `/exports/7`; không cần viết `/group/exports/jobId/7`.
- Đổi thứ tự selector làm thay đổi thứ tự đoạn đường dẫn.
- Chỉ đổi tên phương thức `read` không thêm tên mới vào đường dẫn.

## 7. Lấy nhiều đoạn còn lại bằng ALL_REMAINING

Selector mặc định dùng `Selector.Match.SINGLE`: mỗi selector đơn tương ứng một đoạn. Với dữ liệu có đường dẫn logic nhiều cấp, có thể chọn `ALL_REMAINING`.

Nội dung đầy đủ `PathViewEndpoint.java`:

```java
package example.selector;

import java.util.List;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.Selector;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "pathview")
public class PathViewEndpoint {
    @ReadOperation
    public PathView read(
            @Selector String area,
            @Selector(match = Selector.Match.ALL_REMAINING) String[] segments) {
        return new PathView(area, List.of(segments));
    }

    public record PathView(String area, List<String> segments) {
    }
}
```

Ví dụ:

```http
GET /actuator/pathview/config/services/mail/smtp
```

Ánh xạ trong ví dụ:

```text
area     = "config"
segments = ["services", "mail", "smtp"]
```

Phản hồi:

```json
{"area":"config","segments":["services","mail","smtp"]}
```

Các điểm cần giữ:

1. Selector `area` lấy một đoạn đầu.
2. Selector `segments` lấy phần còn lại và giữ thứ tự.
3. Dùng `String[]` cho dữ liệu đầu vào nhiều đoạn.
4. Đặt selector lấy phần còn lại ở cuối chữ ký như ví dụ, không thêm một selector cố định sau nó.
5. Viết đúng thuộc tính Java là `match` chữ thường: `@Selector(match = Selector.Match.ALL_REMAINING)`.

Hợp đồng Actuator yêu cầu kiểu của tham số lấy phần còn lại tương thích chuyển đổi từ `String[]`. [Spring Boot 3.3: selector trong đường dẫn](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom-endpoints.web.request-predicates.path)

Không coi `String segments` là một sự thay thế mặc nhiên cho mảng nhiều đoạn. Nếu muốn xử lý theo danh sách hay kiểu tùy chỉnh, cần xác định rõ quy tắc chuyển đổi thay vì đoán cách nối các phần.

Ví dụ này chỉ phản ánh **đường dẫn logic** đã nhận; nó không đọc tệp hay truy cập thư mục trên máy chủ. Nếu dùng các phần đường dẫn để truy cập tài nguyên thật, việc kiểm tra tên, phạm vi được phép và quyền truy cập vẫn là trách nhiệm của ứng dụng.

Đối với đường dẫn không còn phần đuôi, hãy định nghĩa rõ hợp đồng mong muốn và kiểm thử trường hợp đó trước khi dựa vào nó. Không dùng việc thêm `@Nullable` như cách tự biến một template đường dẫn thiếu đoạn thành thao tác khác.

## 8. Biên dịch, chạy và gọi thử

Dự án cần JDK 21, Maven và mạng tải phụ thuộc lần đầu. Chạy các lệnh tại thư mục chứa `pom.xml`.

### 8.1. Kiểm thử và đóng gói

Sau khi thêm lớp test ở mục 9:

```shell
mvn verify
```

Maven biên dịch mã, chạy test và đóng gói JAR. Đây là ứng dụng dùng nhiều thư viện Spring, nên không thể thay bằng một lệnh `javac` trên riêng tệp endpoint mà không chuẩn bị classpath và tài nguyên.

### 8.2. Khởi động ứng dụng

```shell
java -jar target/actuator-selector-demo-1.0.0.jar
```

Nếu cần đổi cổng:

```shell
java -jar target/actuator-selector-demo-1.0.0.jar --server.port=18080
```

Dùng đúng cổng đã chọn trong các lệnh tiếp theo. Log khởi động chứa thời gian và thông tin tiến trình thay đổi theo lần chạy; nội dung JSON mới là kết quả minh họa ổn định.

### 8.3. Gọi selector đơn và selector nhiều đoạn

```shell
curl --silent --show-error --fail -H "Accept: application/json" http://127.0.0.1:8080/actuator/jobstate/exports/7
```

Nội dung phản hồi:

```json
{"group":"exports","jobId":7,"state":"DONE"}
```

Gọi phần đường dẫn còn lại:

```shell
curl --silent --show-error --fail -H "Accept: application/json" http://127.0.0.1:8080/actuator/pathview/config/services/mail/smtp
```

Nội dung phản hồi:

```json
{"area":"config","segments":["services","mail","smtp"]}
```

Trong Windows PowerShell, dùng `curl.exe` nếu `curl` đang là một bí danh khác. Dừng ứng dụng bằng Ctrl+C khi thử xong.

Để nhìn rõ mã phản hồi của trường hợp lỗi, có thể dùng `curl -i` trên URL cần kiểm tra. Khi dùng `--fail`, curl coi mã HTTP lỗi là thất bại; đừng nhầm mã thoát của curl với mã HTTP.

## 9. Kiểm thử ánh xạ bằng MockMvc

Nội dung `SelectorEndpointTest.java`:

```java
package example.selector;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SelectorEndpointTest {
    @Autowired
    private MockMvc http;

    @Test
    void bindsSelectorsInDeclaredOrderAndConvertsTheNumber() throws Exception {
        http.perform(get("/actuator/jobstate/exports/7")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.group").value("exports"))
                .andExpect(jsonPath("$.jobId").value(7))
                .andExpect(jsonPath("$.state").value("DONE"));
    }

    @Test
    void theGroupIsPartOfTheLookupKey() throws Exception {
        http.perform(get("/actuator/jobstate/imports/7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.group").value("imports"))
                .andExpect(jsonPath("$.state").value("WAITING"));
    }

    @Test
    void rejectsASelectorThatCannotBeConvertedToInt() throws Exception {
        http.perform(get("/actuator/jobstate/exports/not-a-number"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void aMissingPathSegmentDoesNotMatchTheOperation() throws Exception {
        http.perform(get("/actuator/jobstate/exports"))
                .andExpect(status().isNotFound());
    }

    @Test
    void queryParametersDoNotReplaceSelectorSegments() throws Exception {
        http.perform(get("/actuator/jobstate")
                        .param("group", "exports")
                        .param("jobId", "7"))
                .andExpect(status().isNotFound());
    }

    @Test
    void anUnknownJobReturnsNotFound() throws Exception {
        http.perform(get("/actuator/jobstate/exports/999"))
                .andExpect(status().isNotFound());
    }

    @Test
    void singleSelectorsDoNotConsumeExtraSegments() throws Exception {
        http.perform(get("/actuator/jobstate/exports/7/extra"))
                .andExpect(status().isNotFound());
    }

    @Test
    void allRemainingCollectsTheRemainingSegmentsInOrder() throws Exception {
        http.perform(get("/actuator/pathview/config/services/mail/smtp"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.area").value("config"))
                .andExpect(jsonPath("$.segments.length()").value(3))
                .andExpect(jsonPath("$.segments[0]").value("services"))
                .andExpect(jsonPath("$.segments[1]").value("mail"))
                .andExpect(jsonPath("$.segments[2]").value("smtp"));
    }
}
```

Các test nạp Spring context và đi qua hạ tầng request của Spring MVC bằng MockMvc. Chúng kiểm tra đường dẫn, chuyển đổi tham số và dữ liệu phản hồi; không mở cổng máy chủ TCP. [Spring Framework: MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)

Tám test tập trung vào hành vi có ý nghĩa:

- Giá trị vào đúng selector và `jobId` được chuyển thành số.
- Nhóm tham gia chọn dữ liệu, tránh chỉ kiểm tra một mã số.
- Giá trị không chuyển đổi được bị từ chối.
- Thiếu đoạn và thừa đoạn không khớp thao tác.
- Query không thay cho các đoạn selector.
- Dữ liệu không tồn tại có phản hồi phù hợp.
- Các đoạn `ALL_REMAINING` giữ đúng thứ tự.

Những test này không chỉ gọi trực tiếp phương thức `read(...)`: một lời gọi Java trực tiếp không kiểm tra được việc Actuator tạo đường dẫn hay chuyển đổi dữ liệu HTTP.

Kiểm thử TCP, reverse proxy, mã hóa đường dẫn đặc biệt và quy tắc xác thực là các lớp kiểm chứng bổ sung khi triển khai thật; không suy chúng từ kết quả MockMvc.

## 10. Lưu ý khi thiết kế hợp đồng selector

### 10.1. Không dùng kiểu Java để phân biệt hai URL cùng hình dạng

Hai thao tác chỉ khác `int id` và `String name` không tự trở thành hai tuyến rõ ràng cho cùng một vị trí selector. Trong HTTP, giá trị đường dẫn bắt đầu là chuỗi; framework chọn thao tác theo điều kiện request rồi mới chuyển đổi đầu vào.

Nếu cần hai loại dữ liệu, hãy chọn hợp đồng đường dẫn hoặc endpoint ID phân biệt rõ. Không dựa vào overloading Java để làm cơ chế định tuyến.

### 10.2. Selector không phải cơ chế phân quyền

Một giá trị `group=exports` đến từ URL chỉ là đầu vào. Nó không chứng minh người gọi được phép xem tác vụ của nhóm đó. Với dữ liệu quản trị thật, phải kiểm tra quyền phù hợp trước khi công bố kết quả.

Dùng tên hoặc mã ngắn, ổn định cho selector. Không đặt bí mật vào URL vì đường dẫn thường xuất hiện trong log truy cập và công cụ trung gian.

### 10.3. Đừng dùng dấu gạch chéo mã hóa để né hợp đồng

Một selector đơn chọn một đoạn, còn `ALL_REMAINING` được thiết kế để nhận nhiều đoạn. Không coi `%2F` là cách bảo đảm nhét một đường dẫn nhiều cấp vào selector đơn: máy chủ, proxy và bộ lọc có thể xử lý hoặc từ chối khác nhau.

Trong bài thử, các selector dùng ký tự ASCII đơn giản để tập trung vào cơ chế ánh xạ. Khi hợp đồng cần ký tự đặc biệt, kiểm thử toàn bộ đường đi của request trong môi trường triển khai tương ứng.

### 10.4. HTTP và JMX không có cùng cách biểu diễn đầu vào

`@Endpoint` thuộc mô hình Actuator không gắn riêng với Spring MVC. Khi gọi qua HTTP, selector được biểu diễn bằng đoạn đường dẫn. Khi gọi một thao tác qua JMX, đầu vào là tham số thao tác JMX, không phải một URL HTTP cần tự tách.

Vì vậy không thay cơ chế selector bằng `@PathVariable` chỉ để gắn mã vào một công nghệ cụ thể nếu mục tiêu vẫn là thao tác Actuator.

## 11. Lỗi thường gặp

| Biểu hiện | Điều cần kiểm tra |
| --- | --- |
| URL có đoạn cuối nhưng không gọi được thao tác | Tham số đã có `@Selector` chưa, import có đúng không? |
| Giá trị nhóm đi vào tham số số | Thứ tự đoạn URL có khớp thứ tự selector không? |
| HTTP 400 với mã tác vụ | Giá trị có chuyển được sang kiểu Java yêu cầu không? |
| HTTP 404 khi thiếu đoạn | Template của thao tác có yêu cầu đoạn đó không? |
| Truyền query vẫn không được | Có đang bỏ mất đoạn selector bắt buộc không? |
| Lấy nhiều đoạn nhưng chỉ một đoạn hoạt động | Có đang dùng chế độ SINGLE thay vì ALL_REMAINING không? |
| Lỗi metadata tham số khi nạp endpoint | Build có giữ tên tham số bằng `-parameters` không? |
| Cùng một số mã nhưng trả nhầm nhóm | Logic chọn dữ liệu có dùng toàn bộ selector cần thiết không? |
| Mọi URL của endpoint đều không truy cập được | Bean, enabled, exposure, base path, cổng và bảo mật có đúng không? |

Không sửa thiếu selector bằng cách mở tất cả endpoint hoặc bỏ bảo mật. Hãy kiểm tra theo chuỗi: cấu trúc đường dẫn → chuyển đổi tham số → logic dữ liệu → các điều kiện công bố/truy cập liên quan.

## 12. Thực hành

1. Đổi request từ `exports/7` sang `imports/7` và giải thích vì sao trạng thái thay đổi dù mã số giống nhau.
2. Đổi thứ tự hai selector trong chữ ký rồi cập nhật URL và test tương ứng. Phân biệt thay đổi tên tham số với thay đổi vị trí.
3. Thử mã không đổi được sang số và mã số không tồn tại; chỉ ra khác biệt giữa lỗi 400 và 404.
4. Tăng phần đuôi của `pathview` thêm một đoạn; kiểm tra mảng trả về tăng đúng một phần tử và giữ thứ tự.
5. Nếu cần hỗ trợ truy cập ở đường dẫn gốc, thiết kế một thao tác riêng có ý nghĩa và kiểm tra nó không xung đột với thao tác có selector.

Sau bài này, hãy tự lập được template URL từ chữ ký một phương thức thao tác và chỉ ra chính xác giá trị nào đi vào từng tham số.
