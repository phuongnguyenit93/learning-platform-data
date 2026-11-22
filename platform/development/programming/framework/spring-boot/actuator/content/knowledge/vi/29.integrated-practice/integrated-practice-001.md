# Tạo ứng dụng có health và info với tập endpoint công bố tối thiểu

## 1. Mục tiêu thực hành và mô hình cần hiểu

Một dịch vụ cần cho công cụ vận hành biết ít nhất hai điều: hiện tại các phép kiểm tra sức khỏe đang cho kết quả gì và đây là bản ứng dụng nào. Spring Boot Actuator cung cấp hai endpoint phù hợp:

- **health** trả về trạng thái sức khỏe tổng hợp từ các thành phần kiểm tra đang được cấu hình.
- **info** trả về thông tin mô tả ứng dụng do các nguồn đóng góp thông tin cung cấp.

Trong bài này, ta xây dựng một ứng dụng web chỉ công bố hai endpoint Actuator đó qua HTTP. Health chỉ trả trạng thái tổng hợp; info chỉ trả ba trường mô tả đã chọn. Các endpoint như env, beans, metrics, loggers hoặc heapdump không nằm trong hợp đồng công bố.

“Tối thiểu” cần được thể hiện ở cả cấu hình lẫn kiểm chứng: gọi được health/info mới là nửa đầu; nửa còn lại là xác nhận những endpoint ngoài danh sách không được công bố.

Cần phân biệt bốn quyết định:

| Quyết định | Câu hỏi nó trả lời | Ví dụ trong bài |
| --- | --- | --- |
| Bật endpoint | Endpoint nào được phép hoạt động? | Chỉ bật health và info |
| Phơi bày qua kênh | Endpoint nào có đường truy cập HTTP/JMX? | HTTP chọn health, info; không xuất endpoint qua JMX |
| Kiểm soát truy cập | Ai có thể gọi đường truy cập đó? | Thí nghiệm chỉ lắng nghe trên loopback |
| Giới hạn dữ liệu | Phản hồi được chứa thông tin gì? | Health chỉ có status, info chỉ có app |

Việc bật endpoint và việc phơi bày nó là các bước khác nhau. Cơ chế này được mô tả tại [Endpoints của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling).

Ứng dụng trong bài dùng Spring MVC, Java 21 và Gradle 8.5. Mã là một dự án độc lập có dependency Spring Boot, không phải chương trình chỉ cần một tệp để chạy bằng `javac`.

## 2. Hợp đồng đầu ra trước khi viết mã

Với ứng dụng chạy trên máy phát triển và giữ nguyên cấu hình trong bài:

| Yêu cầu HTTP | Kết quả mong đợi |
| --- | --- |
| `GET /actuator/health` | HTTP 200 và `{"status":"UP"}` khi các phép kiểm tra hiện có đều khỏe |
| `GET /actuator/info` | HTTP 200 và đối tượng app với name, version, description |
| `GET /actuator/env` | HTTP 404 |
| `GET /actuator/beans` | HTTP 404 |
| `GET /actuator/configprops` | HTTP 404 |
| `GET /actuator/metrics` | HTTP 404 |
| `GET /actuator/loggers` | HTTP 404 |
| `GET /actuator/heapdump` | HTTP 404 |
| `GET /actuator/threaddump` | HTTP 404 |
| `GET /actuator/shutdown` | HTTP 404 |
| `GET /actuator` | HTTP 404 vì trang khám phá endpoint đã tắt |

Bảng áp dụng cho đúng ứng dụng mẫu, không có Spring Security, proxy hoặc controller bổ sung. Nếu tích hợp vào một hệ thống khác, một lớp bảo mật có thể trả 401/403 trước khi yêu cầu tới bộ định tuyến. Khi ấy cần xác minh thêm tập endpoint được đăng ký, không suy luận chỉ từ mã HTTP.

Trạng thái UP phụ thuộc những bộ kiểm tra đang có. Mẫu chưa gắn cơ sở dữ liệu hay dịch vụ ngoài; tuy nhiên tài nguyên máy, chẳng hạn dung lượng đĩa, vẫn có thể ảnh hưởng kết quả health. Không sửa endpoint thành luôn trả UP chỉ để làm bảng kiểm tra thành công.

## 3. Tạo cấu trúc dự án

Chuẩn bị JDK 21 và một bản Gradle 8.5 để tạo wrapper lần đầu. Kiểm tra phiên bản Java và Gradle trong terminal sẽ dùng để chạy bài.

Tạo thư mục `actuator-minimal` với cấu trúc:

```text
actuator-minimal/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/actuatorminimal/
    │   │   └── ActuatorMinimalApplication.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/actuatorminimal/
            └── ActuatorExposureTest.java
```

Các tệp dưới đây đủ cho dự án mẫu. Wrapper sẽ được tạo bằng Gradle; không tự viết nội dung JAR của wrapper.

### 3.1. settings.gradle

```groovy
rootProject.name = 'actuator-minimal'
```

### 3.2. build.gradle

Ví dụ cố định Spring Boot 3.3.0 để tái lập bài trong dòng 3.3.x. Các dependency Spring Boot dùng chung BOM tương ứng với phiên bản plugin.

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'com.example'
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
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Vai trò của các thành phần:

- Plugin `java` cung cấp tác vụ biên dịch và kiểm thử.
- Plugin Spring Boot cung cấp `bootRun` và `bootJar`.
- Toolchain chọn JDK 21 để biên dịch.
- BOM cung cấp tập phiên bản tương thích cho dependency.
- `spring-boot-starter-web` cung cấp Spring MVC và web server nhúng.
- `spring-boot-starter-actuator` cung cấp hạ tầng endpoint quản trị.
- `spring-boot-starter-test` và JUnit Platform phục vụ kiểm thử hợp đồng.

Cách dùng BOM bằng `platform` được hỗ trợ trực tiếp trong [Spring Boot Gradle Plugin](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html#managing-dependencies.gradle-bom-support). Dự án này không cần đồng thời thêm plugin quản lý dependency khác để thực hiện cùng một việc.

### 3.3. Lớp khởi động

Tệp `src/main/java/com/example/actuatorminimal/ActuatorMinimalApplication.java`:

```java
package com.example.actuatorminimal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ActuatorMinimalApplication {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorMinimalApplication.class, args);
    }
}
```

Không cần tự viết controller cho health hoặc info. Các endpoint này thuộc Actuator và được cấu hình tự động khi đủ điều kiện.

Đặt lớp khởi động trong package cha của mã ứng dụng. Lớp kiểm thử cũng đặt trong cùng package để cơ chế kiểm thử tìm được cấu hình Spring Boot.

## 4. Cấu hình theo danh sách được phép

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: actuator-minimal
  jmx:
    enabled: false

server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    enabled-by-default: false
    web:
      base-path: /actuator
      exposure:
        include:
          - health
          - info
      discovery:
        enabled: false
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      enabled: true
      show-details: never
      show-components: never
      probes:
        enabled: false
    info:
      enabled: true
  info:
    defaults:
      enabled: false
    env:
      enabled: true

info:
  app:
    name: actuator-minimal
    version: "1.0.0"
    description: "Ứng dụng thực hành Actuator tối thiểu"
```

Không có cấu hình cổng quản trị riêng trong bài; các endpoint HTTP dùng cổng 8080 của web server. Địa chỉ `127.0.0.1` giới hạn listener trong máy chạy ứng dụng. Khi chạy trong container, loopback là loopback của container; bài này mặc định chạy trực tiếp trên máy phát triển.

### 4.1. Hai lớp lựa chọn endpoint

`management.endpoints.enabled-by-default: false` chuyển sang cách bật theo từng endpoint. Hai khóa `management.endpoint.health.enabled` và `management.endpoint.info.enabled` bật lại đúng những endpoint cần dùng.

Danh sách `management.endpoints.web.exposure.include` chọn health và info cho HTTP. Cấu hình bật endpoint và cấu hình exposure có chủ đích giống nhau trong bài này; chúng bảo vệ hai quyết định khác nhau.

Các tên khóa cần đọc chính xác:

- `endpoints` ở số nhiều dùng cho chính sách chung.
- `endpoint` ở số ít dùng cho cấu hình một endpoint cụ thể.
- `info` nằm dưới `management.endpoint` điều khiển endpoint info.
- `management.info` điều khiển các nguồn đóng góp dữ liệu cho endpoint đó.

Không cần dùng `include: "*"` rồi cố gắng liệt kê mọi thứ phải loại trừ. Khi yêu cầu chỉ có hai endpoint, ghi rõ hai ID giúp người đọc và bộ kiểm thử thấy ngay ý định.

### 4.2. HTTP và JMX là hai kênh riêng

`spring.jmx.enabled: false` giữ cơ chế xuất MBean của Spring ở trạng thái không bật. Cấu hình `management.endpoints.jmx.exposure.exclude: "*"` cũng chủ động loại endpoint Actuator khỏi kênh JMX.

Không suy ra rằng danh sách HTTP tự áp dụng cho JMX. Những thiết lập này cũng không có nghĩa mọi thư viện bên thứ ba trong JVM đều bị cấm tự đăng ký MBean. Phạm vi của Spring JMX được nêu tại [Monitoring and Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

### 4.3. Tắt trang khám phá endpoint

`management.endpoints.web.discovery.enabled: false` tắt tài liệu liên kết tại đường gốc `/actuator`. Vì vậy 404 tại `/actuator` là kết quả chủ động của bài, trong khi hai đường con vẫn phải hoạt động.

Ẩn trang khám phá không thay thế exposure hoặc xác thực. Nếu một endpoint khác đã được công bố, việc không có liên kết tới nó không làm đường truy cập biến mất. Vì vậy bài vẫn kiểm tra tập ID endpoint và các đường ngoài danh sách.

### 4.4. Giảm dữ liệu health trả về

`show-details: never` không trả chi tiết của các phép kiểm tra. `show-components: never` không trả danh sách thành phần. Các phép kiểm tra vẫn có thể ảnh hưởng trạng thái tổng hợp.

Bài tắt tự động bật nhóm probe bằng `probes.enabled: false` để phạm vi thực hành không thay đổi theo việc ứng dụng được nhận diện đang chạy trên Kubernetes. Bài tập này chưa thiết kế hợp đồng liveness/readiness riêng.

Các thuộc tính health và discovery có thể đối chiếu trong [danh mục cấu hình Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

## 5. Đưa dữ liệu có chủ đích vào info

Endpoint info hoạt động và có dữ liệu là hai điều khác nhau. Khi endpoint đã được bật/phơi bày nhưng không có nguồn đóng góp thông tin phù hợp, nó vẫn có thể trả HTTP 200 với `{}`.

Cấu hình trong bài chọn một nguồn cụ thể:

```text
Các thuộc tính info.*
        ↓
EnvironmentInfoContributor
        ↓
Endpoint info
        ↓
GET /actuator/info
```

`management.info.env.enabled: true` bật nguồn đóng góp thông tin đọc các thuộc tính có tiền tố `info.`. Nó không bật endpoint `/actuator/env`. Phạm vi dữ liệu được mô tả trong [EnvironmentInfoContributor](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/info/EnvironmentInfoContributor.html).

`management.info.defaults.enabled: false` tắt các nguồn đóng góp mặc định thường được tự bật. Sau đó nguồn env được chọn lại rõ ràng. Điều này giúp mẫu không tự thêm thông tin build hoặc Git chỉ vì một tệp metadata xuất hiện sau này. Cơ chế tạo các nguồn được thể hiện tại [InfoContributorAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/info/InfoContributorAutoConfiguration.html).

Ba trường của bài:

| Trường | Mục đích |
| --- | --- |
| `info.app.name` | Nhận biết ứng dụng đang được hỏi |
| `info.app.version` | Nhận biết phiên bản theo quy ước của bài |
| `info.app.description` | Mô tả ngắn để người vận hành hiểu ứng dụng |

Có hai giới hạn cần giữ rõ:

1. Nguồn env đọc các thuộc tính `info.*`; nó không tự giới hạn ở đúng ba trường app vừa khai báo. Nếu thêm `info.secret`, không được giả định bí mật đó sẽ tự được che.
2. Việc tắt các nguồn đóng góp mặc định không tự xóa một `InfoContributor` tự viết đã được đăng ký bằng mã ứng dụng.

Vì vậy danh sách dữ liệu công bố cần được giữ trong cấu hình và kiểm thử. Không đưa mật khẩu, token, thông tin kết nối nội bộ hoặc toàn bộ môi trường tiến trình vào nhánh `info`.

Phiên bản `1.0.0` trong YAML là dữ liệu tĩnh của bài. Nó không tự đồng bộ với `version` trong Gradle nếu chỉ thay một bên. Khi tăng phiên bản mẫu, cập nhật giá trị tương ứng và kỳ vọng kiểm thử trong cùng thay đổi.

## 6. Chạy ứng dụng và kiểm tra trực tiếp

Mở PowerShell tại thư mục `actuator-minimal`. Dùng Gradle 8.5 đã chuẩn bị để tạo wrapper:

```powershell
gradle wrapper --gradle-version 8.5
```

Sau đó dùng wrapper cho các lần chạy tiếp theo:

```powershell
.\gradlew.bat bootRun
```

Lần đầu cần kết nối tới kho plugin/dependency nếu chúng chưa có trong cache. Chờ log xác nhận ứng dụng đã khởi động; cổng 8080 phải còn trống.

Mở terminal thứ hai. Trên Windows dùng `curl.exe` để tránh nhầm với alias của PowerShell.

### 6.1. Kiểm tra health

```powershell
curl.exe -i http://127.0.0.1:8080/actuator/health
```

Khi các thành phần kiểm tra đều khỏe, phản hồi có HTTP 200. Phần JSON của phản hồi:

```json
{
  "status": "UP"
}
```

Không yêu cầu có `components`, đường dẫn đĩa hoặc chi tiết phụ thuộc. Việc không thấy chi tiết là kết quả cấu hình, không phải endpoint bị hỏng.

UP trong mẫu chứng minh tập kiểm tra hiện tại cho kết quả tốt. Nó không chứng minh mọi thao tác nghiệp vụ của một ứng dụng tương lai đều thành công.

### 6.2. Kiểm tra info

```powershell
curl.exe -i http://127.0.0.1:8080/actuator/info
```

Phản hồi có HTTP 200 và nội dung tương đương:

```json
{
  "app": {
    "name": "actuator-minimal",
    "version": "1.0.0",
    "description": "Ứng dụng thực hành Actuator tối thiểu"
  }
}
```

Các ví dụ JSON được trình bày có thụt lề để dễ đọc. Khoảng trắng, thứ tự khóa và các header như thời gian có thể khác; kiểm tra cấu trúc và giá trị JSON thay vì so khớp nguyên văn toàn bộ phản hồi HTTP.

Info mô tả ứng dụng; health phản ánh trạng thái kiểm tra. Một phản hồi info đúng không thay thế kiểm tra health, và info thường không tự đổi mã HTTP chỉ vì một phụ thuộc đang không khỏe.

### 6.3. Kiểm tra những endpoint không được công bố

Chạy trong PowerShell:

```powershell
$endpointIds = @(
    'env', 'beans', 'configprops', 'metrics',
    'loggers', 'heapdump', 'threaddump', 'shutdown'
)

foreach ($endpointId in $endpointIds) {
    $url = "http://127.0.0.1:8080/actuator/$endpointId"
    $statusCode = curl.exe -sS -o NUL -w '%{http_code}' $url
    "$endpointId=$statusCode"
}
```

Đầu ra mong đợi của vòng lặp:

```text
env=404
beans=404
configprops=404
metrics=404
loggers=404
heapdump=404
threaddump=404
shutdown=404
```

Kiểm tra thêm trang khám phá:

```powershell
curl.exe -i http://127.0.0.1:8080/actuator
```

Kỳ vọng HTTP 404. Đừng dùng phản hồi 404 này để kết luận toàn bộ Actuator đã tắt; health và info ở trên phải vẫn trả lời.

Trên Linux/macOS, dùng `curl`, `./gradlew` và `/dev/null` thay cho `curl.exe`, `.\gradlew.bat` và `NUL` khi thực hiện các lệnh tương ứng.

## 7. Kiểm thử hợp đồng để giữ tập endpoint nhỏ

Chỉ gọi thử hai URL thành công sẽ bỏ sót tình huống một người khác vô tình mở thêm endpoint. Bộ kiểm thử dưới đây kiểm tra cả dữ liệu cho phép và dữ liệu/đường truy cập không được phép xuất hiện.

Tệp `src/test/java/com/example/actuatorminimal/ActuatorExposureTest.java`:

```java
package com.example.actuatorminimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.actuate.endpoint.web.WebEndpointsSupplier;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ActuatorExposureTest {
    @Autowired
    private MockMvc http;

    @Autowired
    private WebEndpointsSupplier webEndpoints;

    @Test
    void healthReturnsOnlyStatus() throws Exception {
        http.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"status\":\"UP\"}", true));
    }

    @Test
    void infoReturnsOnlyApprovedMetadata() throws Exception {
        http.perform(get("/actuator/info"))
                .andExpect(status().isOk())
                .andExpect(content().json("""
                        {
                          "app": {
                            "name": "actuator-minimal",
                            "version": "1.0.0",
                            "description": "Ứng dụng thực hành Actuator tối thiểu"
                          }
                        }
                        """, true));
    }

    @Test
    void unapprovedRoutesAreAbsent() throws Exception {
        String[] paths = {
                "/actuator",
                "/actuator/env",
                "/actuator/beans",
                "/actuator/configprops",
                "/actuator/metrics",
                "/actuator/loggers",
                "/actuator/heapdump",
                "/actuator/threaddump",
                "/actuator/shutdown"
        };

        for (String path : paths) {
            http.perform(get(path)).andExpect(status().isNotFound());
        }
    }

    @Test
    void onlyHealthAndInfoAreDiscoveredAsWebEndpoints() {
        assertThat(webEndpoints.getEndpoints())
                .extracting(endpoint -> endpoint.getEndpointId().toString())
                .containsExactlyInAnyOrder("health", "info");
    }
}
```

Chạy:

```powershell
.\gradlew.bat test
```

Bốn điều bộ kiểm thử chứng minh:

1. Health trả JSON chỉ có `status` với giá trị UP trong điều kiện của mẫu.
2. Info trả đúng tập dữ liệu đã duyệt, không có trường dư trong JSON.
3. Các đường HTTP ngoài danh sách và trang khám phá đều không tồn tại trong ứng dụng mẫu.
4. Tập endpoint Actuator web được khám phá đúng bằng `health` và `info`.

Tham số `true` trong `content().json(..., true)` yêu cầu so khớp JSON nghiêm ngặt, giúp phát hiện dữ liệu bị thêm. Đây là so sánh cấu trúc JSON, không phụ thuộc thứ tự các khóa đối tượng.

`@SpringBootTest` nạp cấu hình ứng dụng; `@AutoConfigureMockMvc` cho phép thực hiện yêu cầu qua tầng Spring MVC giả lập. Bộ kiểm thử không cần chiếm cổng 8080 và không kiểm tra đường mạng ngoài tiến trình. Phân biệt kiểm thử giả lập với kiểm thử mở web server thật tại [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).

Kiểm tra `WebEndpointsSupplier` bổ sung cho các yêu cầu trả 404: nó phát hiện cả một ID endpoint mới chưa được liệt kê trong vòng lặp kiểm tra. Phạm vi của nó là endpoint Actuator web, không phải mọi controller, static resource hoặc tuyến do proxy bên ngoài tạo ra.

Không ghi lại toàn bộ log Gradle như một stdout cố định của bài. Mã thoát thành công và kết quả kiểm thử là bằng chứng chính; thời gian chạy, đường dẫn báo cáo và số dòng log có thể thay đổi.

### Đóng gói và thử bản JAR

Sau khi kiểm thử thành công, tạo JAR chạy được:

```powershell
.\gradlew.bat bootJar
java -jar build/libs/actuator-minimal-1.0.0.jar
```

Dừng phiên `bootRun` cũ bằng Ctrl+C trước khi chạy JAR để tránh tranh chấp cổng. Gọi lại health, info và một số endpoint bị loại trên bản JAR. Việc này xác minh cả tài nguyên cấu hình đã được đóng gói, không chỉ hành vi của lớp kiểm thử.

## 8. Các lỗi thường gặp và cách xác định nguyên nhân

| Hiện tượng | Kiểm tra theo thứ tự | Cách xử lý đúng phạm vi |
| --- | --- | --- |
| Health 404 | Dependency Actuator, enablement, exposure, URL | Xác minh đúng ứng dụng và đủ hai lớp cấu hình |
| Info 404 nhưng health hoạt động | info.enabled và danh sách include | Bật/phơi bày đúng info, không mở tất cả endpoint |
| Info trả `{}` | env contributor và các thuộc tính info.* | Bật nguồn dữ liệu phù hợp; giữ exposure chỉ hai ID |
| Health trả 503 | Trạng thái health và tài nguyên/phụ thuộc đang được kiểm tra | Xử lý nguyên nhân không khỏe, không đổi thành 200 giả |
| Health lộ chi tiết | show-details, show-components và nguồn ghi đè | Khôi phục chính sách dữ liệu tối thiểu |
| Endpoint ngoài danh sách trả 200 | Cấu hình hiệu lực, profile, biến môi trường, controller tùy chỉnh | Tìm nguồn mở rộng hoặc tuyến riêng và sửa tại nguồn |
| Nhận 401/403 | Có Spring Security hoặc proxy khác mẫu không? | Xác định lớp từ chối và quyền cần thiết |
| Kết nối bị từ chối | Ứng dụng đã chạy, đúng cổng, đúng địa chỉ mạng chưa? | Kiểm tra listener và tiến trình trước khi sửa exposure |

Một giá trị trong `application.yml` có thể bị nguồn cấu hình ngoài ghi đè. Nếu thử nghiệm không đúng kỳ vọng, kiểm tra profile, tham số khởi động và các biến như `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE`, thay vì chỉ đọc lại tệp nguồn.

Việc thêm `include: "*"` không phải bước sửa mặc định cho mọi lỗi 404. Nó làm thay đổi yêu cầu của bài mà chưa giải thích nguyên nhân.

Nếu tích hợp Spring Security về sau, “được phơi bày” vẫn không đồng nghĩa “được mọi người truy cập”. Giữ các kiểm thử về tập endpoint và bổ sung kiểm thử danh tính/quyền theo hợp đồng mới.

## 9. Bài tập thay đổi một yếu tố rồi quan sát

Thực hiện mỗi thay đổi trên một bản thực hành cục bộ, quan sát kết quả rồi khôi phục cấu hình trước khi thử tình huống tiếp theo.

### Tình huống A: Tắt nguồn thông tin, giữ endpoint info

Đổi `management.info.env.enabled` thành false, giữ các contributor khác không bật. Khởi động lại.

**Dự đoán:** `/actuator/info` vẫn tồn tại nhưng trả `{}`. Kiểm thử dữ liệu info thất bại, trong khi kiểm thử tập ID endpoint vẫn có thể thành công.

**Ý nghĩa:** đường truy cập và nội dung được tạo bởi hai cơ chế khác nhau.

### Tình huống B: Loại info khỏi HTTP

Giữ `management.endpoint.info.enabled: true` nhưng bỏ info khỏi danh sách HTTP include.

**Dự đoán:** gọi HTTP info trả 404 trong mẫu. Tập endpoint web được khám phá không còn gồm đủ hai ID như hợp đồng ban đầu.

**Ý nghĩa:** được bật chưa đủ để có đường truy cập qua HTTP.

### Tình huống C: Thêm một trường info ngoài hợp đồng

Thêm trường không nhạy cảm `info.app.team: learning`, rồi chạy kiểm thử.

**Dự đoán:** phản hồi info có thêm trường team và kiểm thử JSON nghiêm ngặt thất bại.

**Ý nghĩa:** bộ kiểm thử phát hiện sự mở rộng dữ liệu, kể cả khi tên endpoint không thay đổi. Khôi phục trường dữ liệu sau khi quan sát.

### Tình huống D: Chỉ tắt trang khám phá

Giữ `discovery.enabled: false`, gọi `/actuator` rồi gọi `/actuator/health`.

**Dự đoán:** đường gốc trả 404, health vẫn hoạt động.

**Ý nghĩa:** không có trang liên kết không chứng minh không có endpoint.

### Tình huống E: Thử mở metrics bằng một thay đổi chưa đủ

Chỉ thêm metrics vào HTTP include, không thay `enabled-by-default: false` và không bật metrics riêng.

**Dự đoán:** metrics vẫn không được công bố bởi cấu hình mẫu. Muốn nó khả dụng phải thay cả chính sách bật lẫn exposure; đó sẽ là một hợp đồng khác, cần được duyệt và kiểm thử lại.

**Ý nghĩa:** hai lớp lựa chọn ngăn việc nhầm danh sách đường truy cập với quyết định bật endpoint.

## 10. Tiêu chí hoàn thành bài thực hành

Ứng dụng phải khởi động được từ cấu trúc dự án đã nêu. Với cấu hình gốc và điều kiện máy khỏe, health trả trạng thái tối thiểu, info trả đúng ba trường mô tả, các endpoint ngoài danh sách không được công bố qua HTTP, và tập ID Actuator web đúng bằng health/info.

Giữ lại cả kiểm tra trực tiếp trên bản chạy lẫn kiểm thử hợp đồng. Một bên xác minh tiến trình và cấu hình được đóng gói; bên còn lại phát hiện những lần thay đổi sau làm mở rộng tập endpoint hoặc dữ liệu trả về.

Khi đưa cách làm này vào một ứng dụng có nghiệp vụ thật, hãy định nghĩa lại bộ kiểm tra sức khỏe và quyền truy cập theo nhu cầu vận hành. Hợp đồng nhỏ của bài là điểm xuất phát để đưa ra quyết định có chủ đích, không phải bằng chứng rằng chỉ hai endpoint luôn đáp ứng mọi hệ thống.
