# Xây dựng InfoContributor cho thông tin ứng dụng đặc thù

## 1. Hiểu vai trò của InfoContributor

Khi vận hành một ứng dụng, ta thường cần biết: đây là dịch vụ nào, đang chạy ở khu vực nào, thuộc luồng phát hành nào và hỗ trợ những khả năng nào. Thông tin này giúp đối chiếu bản triển khai hoặc giải thích sự khác biệt giữa hai môi trường.

`/actuator/info` là nơi tập hợp thông tin mô tả ứng dụng. Một **bộ đóng góp thông tin (`InfoContributor`)** bổ sung một phần dữ liệu vào kết quả đó. Ta viết contributor khi cần lựa chọn, tổ chức hoặc tính toán thông tin đặc thù mà dữ liệu build/Git có sẵn chưa diễn đạt được.

Ví dụ, dịch vụ quản lý danh mục khóa học cần công bố:

```json
{
  "application": {
    "schemaVersion": 1,
    "service": "training-catalog",
    "region": "ap-southeast-1",
    "releaseTrack": "stable",
    "capabilities": ["catalog-search", "course-preview"]
  }
}
```

Các trường này là **hợp đồng dữ liệu do ứng dụng lựa chọn**. `releaseTrack` là nhãn triển khai được cấu hình, không chứng minh rằng các pod đều chạy cùng commit. `capabilities` mô tả khả năng dự kiến hỗ trợ, không xác nhận các hệ thống phụ thuộc đang hoạt động.

Trình tự học trong bài: hiểu quan hệ contributor–endpoint → tạo bean và dữ liệu → mở HTTP endpoint → kiểm tra kết quả → xử lý thứ tự, lỗi và dữ liệu động.

### Chọn đúng công cụ cho câu hỏi

| Câu hỏi | Công cụ thích hợp |
| --- | --- |
| Ứng dụng này có thông tin nhận diện và khả năng gì? | `InfoContributor` |
| Cơ sở dữ liệu có đang sẵn sàng không? | `HealthIndicator` hoặc cơ chế health tương ứng |
| Tổng số yêu cầu, độ trễ hay tỷ lệ lỗi là bao nhiêu? | Micrometer và metrics |
| Người dùng muốn tìm khóa học theo điều kiện? | API nghiệp vụ |
| Cần một thao tác quản trị có đầu vào riêng? | Cân nhắc custom Actuator endpoint |

Không đưa số liệu kinh doanh cần truy vấn nặng, dữ liệu theo từng người dùng hoặc kết quả kiểm tra kết nối vào `info` chỉ vì có thể biểu diễn chúng bằng JSON.

## 2. Cơ chế: contributor bổ sung dữ liệu, endpoint tổng hợp

Giao diện có một phương thức:

```java
void contribute(Info.Builder builder);
```

Phương thức nhận một đối tượng xây dựng kết quả và bổ sung các trường bằng `withDetail(key, value)` hoặc `withDetails(map)`. Nó không tự trả HTTP response và không cần gắn `@RestController` hay `@ReadOperation`. Đây cũng là functional interface, nên một bean có thể được khai báo bằng lambda. [Javadoc InfoContributor 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/InfoContributor.html).

Luồng xử lý khi thao tác đọc thực sự được thực thi:

```text
HTTP GET /actuator/info
  -> ánh xạ Actuator và các lớp kiểm soát truy cập
  -> InfoEndpoint.info()
  -> tạo Info.Builder mới cho lần tổng hợp này
  -> gọi contribute(builder) của từng contributor
  -> builder.build().getDetails()
  -> chuyển kết quả thành JSON
```

`InfoEndpoint` giữ danh sách contributor và duyệt lần lượt; đối tượng builder được tạo bên trong phương thức `info()`. Contributor không nên giữ builder trong một field để tái sử dụng giữa các yêu cầu. [Mã nguồn InfoEndpoint](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/InfoEndpoint.java).

Cần phân biệt ba lớp:

- **Bean:** contributor phải được Spring quản lý và nằm trong phạm vi quét hoặc được khai báo bằng `@Bean`.
- **Endpoint và exposure:** `info` phải được bật và được công bố qua HTTP nếu muốn gọi bằng URL.
- **Dữ liệu:** contributor phải thực sự thêm một trường có thể tuần tự hóa thành JSON.

Một class Java triển khai interface nhưng không được đăng ký làm bean sẽ không tự xuất hiện trong danh sách tổng hợp. Ngược lại, có bean chưa đồng nghĩa URL đã truy cập được.

## 3. Ví dụ hoàn chỉnh: thông tin triển khai của dịch vụ khóa học

Ví dụ dùng Java 21, Spring Boot 3.3.0 và Gradle 8.5, phù hợp nhánh kiến thức Spring Boot 3.3.x. Mã dùng record và các API có từ Java 17 trở lên. Đây là **dự án thực hành độc lập**; các tệp Gradle dưới đây không dùng để thay thế cấu hình của một repository đa module.

### 3.1. Cấu trúc dự án

```text
info-contributor-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/example/info/
│   ├── InfoDemoApplication.java
│   ├── ApplicationMetadata.java
│   └── ApplicationInfoContributor.java
├── src/main/resources/application.yml
└── src/test/java/example/info/
    ├── ApplicationInfoContributorTest.java
    ├── InfoEndpointIntegrationTest.java
    └── InfoEndpointDisabledIntegrationTest.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'info-contributor-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`starter-web` cung cấp máy chủ HTTP cho bài thực hành; `starter-actuator` cung cấp cơ chế endpoint. Bộ kiểm thử dùng JUnit Jupiter và MockMvc từ `starter-test`. Không cần thư viện riêng để triển khai `InfoContributor`.

### 3.2. Khai báo ứng dụng và đăng ký cấu hình

Tệp `src/main/java/example/info/InfoDemoApplication.java`:

```java
package example.info;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ApplicationMetadata.class)
public class InfoDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(InfoDemoApplication.class, args);
    }
}
```

Tệp `src/main/java/example/info/ApplicationMetadata.java`:

```java
package example.info;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.metadata")
public record ApplicationMetadata(
        String service,
        String region,
        String releaseTrack) {

    public ApplicationMetadata {
        service = requireText(service, "app.metadata.service");
        region = requireText(region, "app.metadata.region");
        releaseTrack = requireText(releaseTrack, "app.metadata.release-track");
    }

    private static String requireText(String value, String property) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(property + " must not be blank");
        }
        return value;
    }
}
```

`@ConfigurationProperties` gom các thuộc tính liên quan vào một kiểu dữ liệu. Khóa YAML `release-track` được liên kết với thành phần record `releaseTrack`. Record có một constructor chuẩn nên ví dụ không cần thêm `@ConstructorBinding`.

Constructor kiểm tra ba giá trị bắt buộc ngay lúc tạo cấu hình. Thiếu dữ liệu nhận diện là lỗi cấu hình và làm khởi động thất bại, thay vì để lần gọi `/actuator/info` đầu tiên mới vỡ vì `Map.of` không chấp nhận `null`.

Đây là chính sách của ví dụ. Với dữ liệu tùy chọn, hãy chủ động bỏ trường hoặc dùng giá trị mô tả đã thống nhất; không giả một giá trị trông như dữ liệu thật. Cũng cần nhớ rằng record bất biến không tự làm cho toàn bộ object graph bất biến nếu thành phần của nó là collection có thể sửa.

### 3.3. Viết contributor

Tệp `src/main/java/example/info/ApplicationInfoContributor.java`:

```java
package example.info;

import java.util.List;
import java.util.Map;

import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        prefix = "app.metadata",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class ApplicationInfoContributor implements InfoContributor {

    private final Map<String, Object> details;

    public ApplicationInfoContributor(ApplicationMetadata metadata) {
        this.details = Map.of(
                "schemaVersion", 1,
                "service", metadata.service(),
                "region", metadata.region(),
                "releaseTrack", metadata.releaseTrack(),
                "capabilities", List.of("catalog-search", "course-preview"));
    }

    @Override
    public void contribute(Info.Builder builder) {
        builder.withDetail("application", this.details);
    }
}
```

Giải thích các quyết định:

1. `@Component` đăng ký bean trong package con của ứng dụng.
2. Constructor nhận cấu hình qua dependency injection và tạo sẵn dữ liệu ít thay đổi.
3. `application` là khóa cấp cao nhất do contributor này sở hữu; tên bean không quyết định khóa JSON.
4. `Map.of` và `List.of` cùng các giá trị chuỗi/số giúp ví dụ không có collection dùng chung bị sửa trong lúc đọc.
5. `contribute` chỉ gắn dữ liệu vào builder, không truy vấn mạng, ghi cơ sở dữ liệu hay thay đổi trạng thái nghiệp vụ.
6. `schemaVersion` giúp công cụ đọc thông tin nhận diện phiên bản hợp đồng nếu sau này cấu trúc thay đổi.
7. `app.metadata.enabled` là công tắc riêng mà chính ứng dụng gắn với điều kiện tạo bean.

Nếu chọn đăng ký bằng `@Bean` thay cho `@Component`, hãy bỏ `@Component` và chuyển điều kiện bật/tắt sang phương thức `@Bean` nếu vẫn cần nó. Không đăng ký cả hai cách cho cùng contributor vì có thể khiến nó được gọi hai lần.

### 3.4. Cấu hình dữ liệu và mở endpoint

Tệp `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: info-contributor-demo

app:
  metadata:
    enabled: true
    service: training-catalog
    region: ap-southeast-1
    release-track: stable

management:
  endpoint:
    info:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
  info:
    defaults:
      enabled: false
```

Máy chủ được giới hạn ở loopback cho bài thực hành. Ví dụ không thêm Spring Security nên không có bước đăng nhập. Khi tích hợp vào ứng dụng có bảo mật, phải tuân theo chuỗi bộ lọc bảo mật của ứng dụng; thêm `info` vào exposure không cấp quyền truy cập.

Trong nhánh Boot 3.3, `info` cần được đưa vào HTTP exposure nếu muốn gọi qua URL. `management.endpoint.info.enabled` điều khiển endpoint; `management.endpoints.web.exposure.include` điều khiển công bố qua web. Hai việc này khác với tạo bean contributor. [Cấu hình endpoint và exposure](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#enabling).

`management.info.defaults.enabled=false` giúp kết quả thực hành không lẫn các contributor mặc định như build/Git. Nó **không tự tắt bean tự viết** ở trên. Các điều kiện `management.info.<id>.enabled` được áp dụng cho những contributor mà auto-configuration gắn điều kiện tương ứng; tên `application` trong JSON không tự tạo ra công tắc `management.info.application.enabled`. [Auto-configuration contributor trong Boot 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/info/InfoContributorAutoConfiguration.java).

Cấu hình vẫn liên kết và kiểm tra `ApplicationMetadata` khi contributor bị tắt, vì `@EnableConfigurationProperties` đăng ký record độc lập. Công tắc trong ví dụ chỉ quyết định đóng góp thông tin, không vô hiệu hóa việc kiểm tra cấu hình đó.

### 3.5. Chạy và quan sát

Từ thư mục dự án, với JDK 21 và Gradle 8.5 đã cài:

```shell
gradle wrapper --gradle-version 8.5
```

Sau khi có Gradle Wrapper, trên PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

Trên Linux/macOS dùng `./gradlew test` và `./gradlew bootRun`. Không biên dịch riêng từng class bằng `javac` thiếu classpath, vì đây là ứng dụng phụ thuộc Spring và cần cấu hình cùng tài nguyên.

Mở terminal thứ hai:

```shell
curl --silent --show-error http://127.0.0.1:8080/actuator/info
```

Trên Windows dùng `curl.exe` nếu tên `curl` đang trỏ đến một alias PowerShell. Kết quả có cấu trúc:

```json
{
  "application": {
    "schemaVersion": 1,
    "service": "training-catalog",
    "region": "ap-southeast-1",
    "releaseTrack": "stable",
    "capabilities": ["catalog-search", "course-preview"]
  }
}
```

JSON được trình bày lại cho dễ đọc; thứ tự khóa và khoảng trắng không phải hợp đồng. Thứ tự phần tử của danh sách `capabilities` trong ví dụ được giữ theo `List.of`. Không kiểm tra chuỗi JSON bằng phép so sánh phụ thuộc thứ tự khóa của `Map.of`.

Thử đổi `release-track` thành `canary`, khởi động lại rồi đọc lại endpoint. Trường `releaseTrack` đổi theo cấu hình. Tệp cấu hình thay đổi không tự làm bean hiện có được tạo lại; ví dụ không cài cơ chế refresh cấu hình.

Dừng ứng dụng rồi chạy với contributor bị tắt:

```powershell
.\gradlew.bat bootRun --args="--app.metadata.enabled=false"
```

Với đúng cấu hình mẫu và không có contributor khác được thêm vào, kết quả `/actuator/info` là:

```json
{}
```

HTTP endpoint vẫn tồn tại. Điều bị loại bỏ là bean `ApplicationInfoContributor`, không phải toàn bộ `info`.

## 4. Kiểm thử từ hợp đồng Java đến HTTP

Chỉ thấy một lần gọi curl thành công chưa chứng minh contributor giữ đúng dữ liệu, không ghi đè phần khác và thực sự được Spring đăng ký. Ta kiểm tra hai mức khác nhau.

### 4.1. Kiểm thử đơn vị: dữ liệu và ranh giới khóa

Tệp `src/test/java/example/info/ApplicationInfoContributorTest.java`:

```java
package example.info;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.actuate.info.InfoEndpoint;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ApplicationInfoContributorTest {

    private final ApplicationMetadata metadata =
            new ApplicationMetadata(
                    "training-catalog", "ap-southeast-1", "stable");

    @Test
    void contributesOnlyTheExpectedApplicationContract() {
        var builder = new Info.Builder();
        new ApplicationInfoContributor(metadata).contribute(builder);

        Map<String, Object> expected = Map.of(
                "schemaVersion", 1,
                "service", "training-catalog",
                "region", "ap-southeast-1",
                "releaseTrack", "stable",
                "capabilities", List.of("catalog-search", "course-preview"));

        assertEquals(Map.of("application", expected),
                builder.build().getDetails());
    }

    @Test
    void preservesUnrelatedTopLevelInformation() {
        var builder = new Info.Builder();
        builder.withDetail("operations", Map.of("owner", "learning-team"));

        new ApplicationInfoContributor(metadata).contribute(builder);

        assertEquals(Map.of("owner", "learning-team"),
                builder.build().getDetails().get("operations"));
    }

    @Test
    void laterContributorReplacesTheWholeDuplicateTopLevelValue() {
        InfoContributor first = builder -> builder.withDetail(
                "application", Map.of("service", "first"));
        InfoContributor second = builder -> builder.withDetail(
                "application", Map.of("region", "second"));

        var endpoint = new InfoEndpoint(List.of(first, second));

        assertEquals(
                Map.of("application", Map.of("region", "second")),
                endpoint.info());
    }

    @Test
    void rejectsMissingRequiredMetadata() {
        var error = assertThrows(IllegalArgumentException.class,
                () -> new ApplicationMetadata(
                        "training-catalog", " ", "stable"));

        assertEquals("app.metadata.region must not be blank",
                error.getMessage());
    }
}
```

Kiểm thử thứ nhất kiểm tra toàn bộ hợp đồng, kể cả không vô tình thêm khóa lạ. Kiểm thử thứ hai bảo vệ dữ liệu của contributor khác. Kiểm thử thứ ba cố ý tạo trùng khóa để quan sát quy tắc thay thế; nó không phụ thuộc thứ tự quét bean vì truyền một danh sách có thứ tự rõ ràng cho endpoint. Kiểm thử cuối xác minh chính sách dữ liệu bắt buộc.

### 4.2. Kiểm thử tích hợp: bean, cấu hình và URL

Tệp `src/test/java/example/info/InfoEndpointIntegrationTest.java`:

```java
package example.info;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class InfoEndpointIntegrationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void exposesApplicationMetadataThroughActuator() throws Exception {
        mvc.perform(get("/actuator/info"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.application.schemaVersion").value(1))
                .andExpect(jsonPath("$.application.service")
                        .value("training-catalog"))
                .andExpect(jsonPath("$.application.region")
                        .value("ap-southeast-1"))
                .andExpect(jsonPath("$.application.releaseTrack")
                        .value("stable"))
                .andExpect(jsonPath("$.application.capabilities.length()")
                        .value(2))
                .andExpect(jsonPath("$.application.capabilities[0]")
                        .value("catalog-search"))
                .andExpect(jsonPath("$.application.capabilities[1]")
                        .value("course-preview"));
    }
}
```

Tệp `src/test/java/example/info/InfoEndpointDisabledIntegrationTest.java`:

```java
package example.info;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "app.metadata.enabled=false")
@AutoConfigureMockMvc
class InfoEndpointDisabledIntegrationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void keepsTheEndpointAvailableWhenTheContributorIsDisabled()
            throws Exception {
        mvc.perform(get("/actuator/info"))
                .andExpect(status().isOk())
                .andExpect(content().json("{}", true));
    }
}
```

Chạy `.\gradlew.bat test` để thực thi sáu kiểm thử trên. Chúng không in kết quả JSON ra stdout; báo cáo HTML nằm ở `build/reports/tests/test/index.html`. Thông báo build, thời gian và log khởi động thay đổi theo môi trường, nên không dùng chúng làm kết quả cố định.

MockMvc kiểm tra ánh xạ HTTP trong ngữ cảnh Spring nhưng không mở socket TCP thật. Lệnh curl ở phần trước bổ sung kiểm tra qua máy chủ đang chạy. Nếu đưa bài vào ứng dụng có Spring Security, kiểm thử HTTP phải bổ sung cơ chế xác thực/quyền phù hợp thay vì vô hiệu hóa bảo mật để ép kiểm thử chạy qua.

## 5. Nhiều contributor: quyền sở hữu khóa và thứ tự

### 5.1. Mỗi vùng dữ liệu có một bên sở hữu

Các contributor độc lập có thể cùng đóng góp:

```json
{
  "application": {
    "service": "training-catalog"
  },
  "operations": {
    "owner": "learning-team"
  }
}
```

Nhưng nếu hai contributor đều gọi `withDetail("application", ...)`, giá trị được ghi sau thay thế **toàn bộ giá trị tại khóa đó**. Các map lồng nhau không tự hợp nhất theo từng trường. Kiểm thử trùng khóa phía trên là bằng chứng thực thi của hành vi này.

Tương tự, `withDetails(map)` thêm các mục của map vào cấp trên cùng; nó không tự tạo một nhóm theo tên bean. Muốn có nhóm `application`, hãy truyền một map làm giá trị cho `withDetail("application", map)`.

Thiết kế dễ duy trì là mỗi contributor sở hữu một khóa cấp trên cùng. Nếu nhiều nguồn cùng tạo nhóm `application`, nên có một contributor tổng hợp từ các đối tượng cung cấp dữ liệu nhỏ, rồi chỉ ghi nhóm đó một lần. Tránh lấy `build`, `git`, `java` hoặc `os` làm khóa cho dữ liệu khác nghĩa khi còn dùng các contributor tương ứng.

### 5.2. Thứ tự có thể điều khiển nhưng không thay được thiết kế

Auto-configuration lấy các bean thông qua `orderedStream()`. Có thể dùng `@Order` hoặc `Ordered`; số nhỏ được ưu tiên trước. Khi tự khai báo bean bằng phương thức `@Bean`, có thể đặt `@Order` trên phương thức đó. Không suy luận thứ tự từ tên class, tên file hoặc thứ tự phát hiện component. [Mã nguồn InfoEndpointAutoConfiguration](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/info/InfoEndpointAutoConfiguration.java).

Một contributor có thể cố ý ghi sau để ghi đè, nhưng cách này khiến nội dung phụ thuộc vào thứ tự và cấu hình bean. Nếu không có yêu cầu tương thích rõ ràng, phân chia khóa sẽ dễ hiểu hơn. Thứ tự thực thi contributor cũng không phải cam kết thứ tự hiển thị các trường JSON cho bên tiêu thụ.

## 6. Thông tin động, hiệu năng và lỗi

### 6.1. Tách dữ liệu ít thay đổi khỏi dữ liệu cập nhật lúc chạy

Trong ví dụ, metadata được chụp khi tạo bean. Phù hợp với tên dịch vụ, vùng triển khai và nhãn phát hành vốn không đổi trong vòng đời tiến trình.

Nếu cần công bố một bản cấu hình nghiệp vụ được cập nhật lúc chạy, contributor nên đọc **bản chụp dữ liệu đã được chuẩn bị**, chẳng hạn một record bất biến lưu trong `AtomicReference`. Tác vụ nền thay toàn bộ bản chụp khi cập nhật thành công; contributor chỉ đọc một lần rồi tạo JSON. Ví dụ thiết kế, không phải tệp bổ sung của dự án mẫu:

```java
record CatalogSnapshot(String revision, String observedAt) {}
```

Nhóm JSON tương ứng có thể là:

```json
{
  "catalogMetadata": {
    "revision": "catalog-42",
    "observedAt": "2026-01-01T00:00:00Z",
    "sourceState": "cached"
  }
}
```

`observedAt` cần phản ánh lúc quan sát nguồn thành công. Không thay nó bằng thời điểm gọi endpoint rồi khiến dữ liệu cũ trông như vừa cập nhật. Khi tác vụ nền thất bại, có thể giữ bản chụp cũ kèm trạng thái cũ/quá hạn theo hợp đồng đã định, hoặc bỏ nhóm tùy chọn. Không đưa exception, địa chỉ kết nối riêng hay stack trace vào JSON.

### 6.2. Không biến thao tác đọc metadata thành giao dịch nặng

Một cách triển khai gây vấn đề là mỗi lần `contribute` lại gọi nhiều API từ xa hoặc truy vấn thống kê toàn bảng. Khi hệ thống giám sát đọc liên tục, chi phí tăng theo số lần gọi; một nguồn chậm còn làm endpoint chậm theo.

Ưu tiên dữ liệu trong bộ nhớ, giá trị tính sẵn hoặc bản chụp cập nhật có kiểm soát. Contributor cần an toàn khi có nhiều luồng đọc đồng thời. Không sửa một `HashMap` dùng chung trong lúc luồng khác đang tuần tự hóa nó; ưu tiên tạo dữ liệu bất biến và thay tham chiếu nguyên khối.

Với dữ liệu thực sự phải lấy bên ngoài, hãy xác định rõ timeout, giới hạn chi phí, hành vi khi không có dữ liệu và mức độ cũ được chấp nhận. Đừng đặt logic nghiệp vụ có tác dụng phụ trong thao tác đọc `info`.

### 6.3. Phân biệt cache ở endpoint với cache nguồn dữ liệu

Mỗi lần gọi trực tiếp `InfoEndpoint.info()` đều tạo builder và duyệt contributor. Qua hạ tầng Actuator, kết quả của thao tác đọc có thể được cache khi cấu hình TTL phù hợp. Do đó không nên khẳng định contributor luôn chạy đúng một lần cho mỗi HTTP request trong mọi cấu hình.

Ví dụ cấu hình bổ sung, ghép vào cây `management` hiện có:

```yaml
management:
  endpoint:
    info:
      cache:
        time-to-live: 10s
```

Khi bật cache, một cập nhật dữ liệu có thể chưa xuất hiện ngay trong response. Cache endpoint tái sử dụng kết quả đọc trong một khoảng thời gian; cache nguồn dữ liệu giúp tránh lấy dữ liệu đắt tiền bên trong contributor. Hai lớp giải quyết các chi phí khác nhau. [Cấu hình cache thao tác đọc Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#configuring).

### 6.4. Contributor ném lỗi có thể làm hỏng cả thao tác tổng hợp

Vòng lặp của `InfoEndpoint` không bao từng contributor bằng một khối `try/catch` riêng. Nếu contributor ném exception, thao tác không tự bỏ qua contributor đó và trả một kết quả thành công từng phần; qua HTTP, lỗi có thể trở thành phản hồi 5xx tùy lớp xử lý lỗi.

Vì vậy cần tách hai loại lỗi:

- **Cấu hình bắt buộc sai:** kiểm tra sớm lúc khởi động, như record của ví dụ.
- **Nguồn bổ sung tạm thời không đọc được:** xử lý tại lớp cung cấp dữ liệu với chính sách thiếu/quá hạn cụ thể.

Không dùng `catch (Exception)` rồi im lặng trả dữ liệu giả. Ghi nhận lỗi ở kênh vận hành thích hợp và giữ hợp đồng JSON nhất quán. Trạng thái sẵn sàng của phụ thuộc vẫn cần cơ chế health riêng nếu nó ảnh hưởng đến việc phục vụ yêu cầu.

## 7. Công bố dữ liệu theo danh sách cho phép

Contributor tự viết kiểm soát dữ liệu đầu ra. Hãy coi mọi trường đưa vào `Info.Builder` là dữ liệu có thể được người có quyền truy cập endpoint nhìn thấy.

Không đưa toàn bộ `Environment`, biến môi trường tiến trình, object cấu hình hay đối tượng dịch vụ vào `withDetail`. Việc chọn tường minh `service`, `region`, `releaseTrack` trong ví dụ tạo một danh sách trường được phép công bố và giúp kiểm thử hợp đồng rõ ràng.

Các giá trị cần tránh gồm mật khẩu, token, khóa ký, thông tin nhận diện người dùng, chuỗi kết nối có tài khoản và cấu hình nội bộ không dành cho bên đọc endpoint. Không trông chờ quy tắc che giá trị của `/actuator/env` tự áp dụng cho map do contributor tạo.

Giữ dữ liệu dễ chuyển thành JSON: chuỗi, số, boolean, danh sách và map có khóa rõ ràng. Tránh trả entity JPA, request/session hoặc object chứa tham chiếu vòng vì có thể kéo theo trường ngoài ý muốn, truy vấn lười hoặc lỗi tuần tự hóa.

Nếu sau này bật `management.info.env.enabled=true` để đưa `info.*` vào kết quả, phải kiểm tra lại toàn bộ hợp đồng công bố và nguy cơ trùng khóa. Việc này độc lập với contributor đọc `app.metadata.*` trong bài.

## 8. Chẩn đoán lỗi thường gặp

| Hiện tượng | Điểm cần kiểm tra |
| --- | --- |
| `404` khi gọi URL | Đúng cổng, base path/context path, endpoint được bật và HTTP exposure có `info`; kiểm tra cả exclusion |
| `401` hoặc `403` | Cơ chế xác thực và quyền của Spring Security/proxy; exposure không cấp quyền |
| `200` với `{}` | Có bean contributor không, package có được quét không, công tắc có tắt bean không, có contributor nào thực sự đóng góp không |
| Thiếu một phần nhóm JSON | Có contributor khác ghi cùng khóa cấp trên cùng không |
| Cấu hình có `info.*` nhưng không xuất hiện | Đây là đường của EnvironmentInfoContributor; cần kiểm tra contributor đó riêng |
| Đặt `management.info.application.enabled=false` nhưng nhóm tự viết vẫn còn | Tên khóa JSON không tự nối với điều kiện tạo bean; dùng công tắc đã khai báo |
| Khởi động thất bại vì metadata trống | Kiểm tra ba thuộc tính bắt buộc và profile/property override đang có hiệu lực |
| Endpoint chậm hoặc trả 5xx | Contributor có I/O đồng bộ, lỗi tuần tự hóa hay exception từ nguồn bổ sung không |
| Đổi tệp YAML nhưng giá trị cũ vẫn còn | Bean không tự refresh; kiểm tra việc khởi động lại, bản chụp và cache |
| Dữ liệu thay đổi theo người gọi | Xem lại thiết kế: metadata ứng dụng nên có hợp đồng vận hành ổn định, không trộn dữ liệu cá nhân hóa |

Thứ tự chẩn đoán nên đi từ khả năng truy cập → bean → dữ liệu → tổng hợp → hiệu năng. Một lỗi HTTP không nhất thiết bắt nguồn từ phương thức `contribute`.

## 9. Thực hành có tiêu chí kiểm chứng

1. Thêm trường cấu hình `deployment-group` vào record, YAML và JSON; kiểm thử giá trị liên kết cùng tên khóa JSON đã chọn.
2. Thêm một contributor sở hữu khóa `operations` với giá trị công khai giả lập, rồi xác minh cả hai nhóm cùng tồn tại.
3. Cố ý cho contributor thứ hai dùng khóa `application`; viết kiểm thử với thứ tự rõ ràng để thấy giá trị bị thay thế. Sau đó sửa bằng cách trả lại quyền sở hữu khóa riêng.
4. Tắt `app.metadata.enabled`, giữ endpoint được công bố và xác minh nhóm `application` biến mất mà URL vẫn đọc được.
5. Thử một metadata bắt buộc trống để quan sát lỗi cấu hình lúc khởi động, rồi khôi phục giá trị hợp lệ.
6. Với phương án dữ liệu động, mô tả thời điểm cập nhật, tuổi dữ liệu chấp nhận được và hành vi khi lấy nguồn thất bại trước khi viết contributor.

Hoàn thành bài khi có thể giải thích được **ai tạo dữ liệu, ai sở hữu từng khóa, khi nào contributor chạy và vì sao HTTP endpoint truy cập được**; đồng thời chứng minh được hợp đồng JSON bằng kiểm thử mà không phụ thuộc thứ tự trường.
