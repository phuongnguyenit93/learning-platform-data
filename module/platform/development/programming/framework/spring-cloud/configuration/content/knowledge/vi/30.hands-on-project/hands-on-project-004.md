# Thay đổi cấu hình và so sánh refresh, RefreshScope với khởi động lại

## 1. Mục tiêu project

Trong project này, bạn dựng một Spring Cloud Config Server đọc cấu hình từ Git và một Spring Boot Config Client tên `orders-service`. Sau khi ứng dụng khởi động với giá trị `v1`, bạn sửa file cấu hình, commit thành `v2`, rồi thử ba cách áp dụng thay đổi:

1. **Refresh Environment**: nạp lại cấu hình từ Config Server và phát hiện các property đã đổi.
2. **`@RefreshScope`**: hủy target bean cũ và tạo target mới ở lần gọi kế tiếp.
3. **Restart ứng dụng**: tạo lại ApplicationContext và toàn bộ bean từ đầu.

Bạn sẽ quan sát đồng thời `Environment`, bean `@ConfigurationProperties`, bean thường dùng `@Value` và bean có `@RefreshScope`. Nhờ đó có thể thấy cùng một thay đổi cấu hình tác động khác nhau lên từng loại bean.

Kết quả mong đợi sau khi thay `demo.message` từ `v1` sang `v2`:

| Cách áp dụng | `Environment` | `@ConfigurationProperties` | Bean thường dùng `@Value` | Bean `@RefreshScope` |
|---|---|---|---|---|
| Chỉ commit Git | Vẫn `v1` | Vẫn `v1` | Vẫn `v1` | Vẫn `v1` |
| Gọi `POST /actuator/refresh` | `v2` | Được rebind thành `v2` | Vẫn giữ `v1` | Target được tạo lại thành `v2` khi gọi tiếp |
| Restart process | `v2` | `v2` | `v2` | `v2` |

Project dùng giá trị demo không nhạy cảm. Trong production, endpoint refresh phải được bảo vệ bằng xác thực, phân quyền và network policy.

## 2. Kiến trúc và cấu trúc thư mục

Project có ba phần:

```text
config-refresh-lab/
├── config-repo/                  # Git repository chứa application.yml
│   └── application.yml
├── config-server/                # Spring Cloud Config Server
│   ├── pom.xml
│   └── src/main/
│       ├── java/.../ConfigServerApplication.java
│       └── resources/application.yml
└── orders-service/               # Spring Boot Config Client
    ├── pom.xml
    └── src/main/
        ├── java/.../
        │   ├── OrdersApplication.java
        │   ├── DemoProperties.java
        │   ├── StartupMessage.java
        │   ├── RefreshableMessage.java
        │   └── ConfigStateController.java
        └── resources/application.yml
```

Luồng dữ liệu:

```mermaid
flowchart LR
    G[(Git config-repo)] -->|application.yml, commit v1/v2| CS[Config Server :8888]
    CS -->|Environment response| CC[orders-service :8080]
    CC --> ENV[Spring Environment]
    ENV --> CP[@ConfigurationProperties]
    ENV --> P[Plain @Value bean]
    ENV --> RS[@RefreshScope proxy]
    CP --> API[/demo/state]
    P --> API
    RS --> API
    ENV --> API
    REF[POST /actuator/refresh] --> CC
    RESTART[Restart process] --> CC
```

## 3. Chuẩn bị phiên bản và dependency

Chọn một Spring Boot release và Spring Cloud release train tương thích theo bảng compatibility chính thức. Mỗi project Maven dùng `spring-boot-starter-parent` làm parent, đặt `java.version` phù hợp với release đã chọn và import Spring Cloud BOM để các dependency Spring Cloud dùng cùng một bộ phiên bản; không tự chọn các version rời rạc cho Config Server, Config Client và Spring Cloud Context.

Ví dụ phần parent và properties trong mỗi `pom.xml`:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>SPRING_BOOT_VERSION_TUONG_THICH</version>
    <relativePath />
</parent>

<properties>
    <java.version>17</java.version>
    <spring-cloud.version>SPRING_CLOUD_RELEASE_TUONG_THICH</spring-cloud.version>
</properties>
```

Thay hai giá trị placeholder version bằng version thực tương thích trước khi chạy Maven.

Ví dụ phần `dependencyManagement` dùng chung cho hai Maven project:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đặt `spring-cloud.version` theo release train tương thích với Spring Boot parent đang dùng.

**Dependency cho Config Server**:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-config-server</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
```

**Dependency cho Config Client**:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
```

Actuator cung cấp các endpoint quản trị và Spring Cloud Context bổ sung khả năng refresh. Không cần thêm một thư viện refresh riêng.

## 4. Tạo Git repository cấu hình

Tạo thư mục `config-repo` và file `application.yml`:

```yaml
demo:
  message: "Xin chào từ cấu hình Git v1"
  timeout: 2s
```

Khởi tạo repository và commit phiên bản đầu. Lệnh `git init -b main` cần Git 2.28 trở lên. Kiểm tra bằng `git --version`. Sau khi khởi tạo repository, nếu máy chưa cấu hình danh tính commit, đặt tên và email riêng cho repository lab:

```bash
cd config-repo
git --version
git init -b main
git config user.name "Config Lab User"
git config user.email "config-lab@example.test"
git add application.yml
git commit -m "Add initial orders configuration"
```

Nếu Git cũ hơn 2.28, dùng `git init` rồi `git branch -M main` thay cho `git init -b main`. Hai lệnh `git config` ở trên là cấu hình local của repository; thay bằng tên/email phù hợp nếu cần.

Config Server sẽ đọc repository này theo label `main`. Với bài lab local, có thể dùng `file:` URI. Ví dụ:

```text
Linux/macOS: file:///home/dev/config-refresh-lab/config-repo
Windows:     file:///C:/work/config-refresh-lab/config-repo
```

Đường dẫn phải là URI hợp lệ, dùng dấu `/` và trỏ đến thư mục Git repository. Thay `dev` hoặc `C:/work` bằng đường dẫn thực trên máy lab.

Khi dùng `file:` URI, Config Server làm việc trực tiếp trên repository local thay vì clone thành working copy như remote Git. Với Git provider từ xa, Config Server dùng `spring.cloud.config.server.git.refresh-rate`; mặc định `0` nghĩa là fetch cập nhật mỗi khi có request cấu hình. Nếu đặt số dương, thay đổi có thể chưa xuất hiện cho đến khi hết khoảng refresh đó.

## 5. Dựng Config Server

Tạo main class:

```java
package com.example.configserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

@EnableConfigServer
@SpringBootApplication
public class ConfigServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
```

`@EnableConfigServer` bật HTTP Config Server.

Tạo `config-server/src/main/resources/application.yml`:

```yaml
server:
  port: 8888

spring:
  application:
    name: config-server
  cloud:
    config:
      server:
        git:
          uri: ${CONFIG_REPO_URI}
          default-label: main

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Đặt biến môi trường `CONFIG_REPO_URI` trước khi chạy server. Ở bước Git trước, terminal đang ở `config-repo`; quay về project root rồi chuyển vào thư mục Maven `config-server` trước khi chạy lệnh. Nếu mở terminal mới tại `config-refresh-lab`, chỉ cần chạy `cd config-server`.

```text
# Nếu tiếp tục terminal đang ở config-repo:
cd ..
cd config-server
```

Giữ terminal tại `config-server`. Ví dụ PowerShell:

```powershell
$env:CONFIG_REPO_URI = "file:///C:/work/config-refresh-lab/config-repo"
mvn spring-boot:run
```

Ví dụ Linux/macOS:

```bash
export CONFIG_REPO_URI="file:///home/dev/config-refresh-lab/config-repo"
mvn spring-boot:run
```

Nếu project được tạo kèm Maven Wrapper, có thể thay `mvn` bằng `./mvnw` trên Linux/macOS hoặc `mvnw.cmd` trên Windows.

### Xác nhận Config Server đọc đúng Git

Gọi Environment endpoint:

```bash
curl --fail-with-body \
  http://localhost:8888/orders-service/dev/main
```

Trên PowerShell có thể dùng `curl.exe` để gọi đúng chương trình curl:

```powershell
curl.exe --fail-with-body http://localhost:8888/orders-service/dev/main
```

Response cần có `name` là `orders-service`, profile `dev`, label `main` và property source chứa `demo.message` với giá trị `Xin chào từ cấu hình Git v1`. Nếu endpoint không trả đúng, kiểm tra Git URI, label, tên file và log Config Server trước khi tiếp tục.

## 6. Dựng Config Client

Tạo `orders-service/src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  application:
    name: orders-service
  profiles:
    active: dev
  config:
    import: "configserver:http://localhost:8888"
  cloud:
    config:
      label: main

management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
```

Import không có `optional:` để Config Server là nguồn bắt buộc khi khởi động. Điều này giúp lab báo lỗi sớm nếu server không sẵn sàng. `refresh` chỉ được expose để thực hành local; không expose endpoint này công khai trong production.

Main class bật scan cho `@ConfigurationProperties`:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

## 7. Tạo ba kiểu bean để quan sát

### Bean `@ConfigurationProperties` có thể rebind

Tạo `DemoProperties.java`:

```java
package com.example.orders;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public class DemoProperties {

    private String message = "local-default";
    private Duration timeout = Duration.ofSeconds(1);

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

Đây là class mutable có no-argument constructor ngầm định và setter để Spring Cloud rebind khi `EnvironmentChangeEvent` được phát. Trong lab, tránh dùng Java record hoặc constructor-bound `@ConfigurationProperties`: các bean dùng constructor binding, bao gồm Java record, không được Spring Cloud refresh rebinding hỗ trợ.

### Bean thường dùng `@Value`

Tạo `StartupMessage.java`:

```java
package com.example.orders;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class StartupMessage {

    private final String message;

    public StartupMessage(
            @Value("${demo.message:local-default}") String message) {
        this.message = message;
    }

    public String getMessage() {
        return message;
    }
}
```

`message` được đọc khi bean được tạo. Đây là singleton thông thường; Spring không tự gọi lại constructor chỉ vì Environment thay đổi. Sau refresh, field `message` của instance hiện tại vẫn giữ giá trị cũ.

### Bean dùng `@RefreshScope`

Tạo `RefreshableMessage.java`:

```java
package com.example.orders;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class RefreshableMessage {

    private final String message;

    public RefreshableMessage(
            @Value("${demo.message:local-default}") String message) {
        this.message = message;
    }

    public String getMessage() {
        return message;
    }
}
```

Bean này được truy cập thông qua proxy của refresh scope. Khi refresh scope bị invalidate, target cũ bị hủy; lần gọi `getMessage()` tiếp theo tạo target mới và inject giá trị hiện hành từ Environment.

Lớp không được khai báo `final` để proxy dựa trên class có thể hoạt động. Với bean dùng interface/JDK proxy, cần bảo đảm cách inject và kiểu proxy phù hợp.

## 8. Tạo endpoint quan sát trạng thái

Tạo `ConfigStateController.java`:

```java
package com.example.orders;

import java.util.Map;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConfigStateController {

    private final Environment environment;
    private final DemoProperties properties;
    private final StartupMessage startupMessage;
    private final RefreshableMessage refreshableMessage;

    public ConfigStateController(
            Environment environment,
            DemoProperties properties,
            StartupMessage startupMessage,
            RefreshableMessage refreshableMessage) {
        this.environment = environment;
        this.properties = properties;
        this.startupMessage = startupMessage;
        this.refreshableMessage = refreshableMessage;
    }

    @GetMapping("/demo/state")
    public Map<String, String> state() {
        return Map.of(
                "environment", environment.getProperty("demo.message", "missing"),
                "configurationProperties", properties.getMessage(),
                "plainSingleton", startupMessage.getMessage(),
                "refreshScope", refreshableMessage.getMessage(),
                "timeout", properties.getTimeout().toString());
    }
}
```

Endpoint này chỉ trả giá trị demo để quan sát. Không tạo endpoint tương tự để dump toàn bộ Environment hoặc secret trong production.

Chạy client trong terminal khác:

```bash
cd orders-service
mvn spring-boot:run
```

Trên Windows:

```powershell
cd orders-service
mvn spring-boot:run
```

Gọi endpoint:

```bash
curl http://localhost:8080/demo/state
```

Kết quả ban đầu tương tự:

```json
{
  "environment": "Xin chào từ cấu hình Git v1",
  "configurationProperties": "Xin chào từ cấu hình Git v1",
  "plainSingleton": "Xin chào từ cấu hình Git v1",
  "refreshScope": "Xin chào từ cấu hình Git v1",
  "timeout": "PT2S"
}
```

Nếu giá trị không khớp, kiểm tra Config Server response, `spring.application.name`, active profile và label trước khi thử refresh.

## 9. Thay đổi cấu hình trong Git

Mở `config-repo/application.yml`, thay `demo.message` thành `v2`:

```yaml
demo:
  message: "Xin chào từ cấu hình Git v2"
  timeout: 2s
```

Commit thay đổi:

```bash
cd config-repo
git add application.yml
git commit -m "Change demo message to v2"
```

Không cần restart Config Server cho thay đổi file cấu hình Git thông thường. Với local `file:` repository, Config Server đọc repository local trực tiếp. Nếu dùng remote Git, Config Server phải fetch revision mới theo `refresh-rate`; mặc định `0` fetch mỗi request. Nếu đã đặt `refresh-rate` dương, chờ chu kỳ đó hoặc điều chỉnh cấu hình lab trước khi kiểm tra.

Trước khi refresh client, gọi trực tiếp Config Server:

```bash
curl --fail-with-body http://localhost:8888/orders-service/dev/main
```

Xác nhận response đã chứa `Xin chào từ cấu hình Git v2`. Bước này tách lỗi Git/Config Server khỏi lỗi refresh ở client.

## 10. Quan sát trạng thái trước khi refresh

Gọi lại client:

```bash
curl http://localhost:8080/demo/state
```

Kết quả vẫn là `v1` ở cả bốn trường. Đây là hành vi bình thường: Config Client không tự polling Config Server để phát hiện thay đổi theo mặc định. Việc commit Git chỉ cập nhật nguồn dữ liệu; Environment đang nằm trong process client chưa tự đổi.

Ở thời điểm này bạn đã xác minh:

- Git đã có commit `v2`.
- Config Server trả `v2` cho đúng application/profile/label.
- Client đang chạy vẫn giữ Environment và bean state từ lần nạp trước.

## 11. Thực hiện refresh trên Config Client

Gửi POST đến endpoint refresh:

```bash
curl --fail-with-body -X POST http://localhost:8080/actuator/refresh
```

Trên PowerShell:

```powershell
curl.exe --fail-with-body -X POST http://localhost:8080/actuator/refresh
```

Response thường là danh sách các key đã thay đổi, ví dụ:

```json
["demo.message"]
```

Endpoint refresh của Spring Cloud Context nạp lại cấu hình từ nguồn ngoài, so sánh Environment và phát sự kiện thay đổi. Các `@ConfigurationProperties` bean được rebind; các bean `@RefreshScope` được clear target cache để tạo lại khi được gọi tiếp.

Gọi lại `/demo/state`:

```bash
curl http://localhost:8080/demo/state
```

Kết quả mong đợi:

```json
{
  "environment": "Xin chào từ cấu hình Git v2",
  "configurationProperties": "Xin chào từ cấu hình Git v2",
  "plainSingleton": "Xin chào từ cấu hình Git v1",
  "refreshScope": "Xin chào từ cấu hình Git v2",
  "timeout": "PT2S"
}
```

Đây là điểm quan sát quan trọng nhất của project:

- `Environment` đã nhận giá trị mới.
- `DemoProperties` được rebind theo `EnvironmentChangeEvent`.
- `StartupMessage` là singleton thường, field được inject lúc startup nên vẫn là `v1`.
- `RefreshableMessage` được gọi qua proxy; target cũ đã bị hủy và target mới đọc `v2` ở lần gọi này.

## 12. Hiểu chính xác `@RefreshScope`

`@RefreshScope` không sửa field của object cũ. Nó đặt bean sau một proxy và quản lý target như một cache:

1. Lần đầu có lời gọi qua proxy, scope tạo target và cache target đó.
2. Khi refresh, cache entry của target bị xóa và lifecycle hủy target cũ được thực hiện.
3. Lời gọi tiếp theo qua proxy tạo target mới từ Environment hiện hành.

Vì vậy việc POST `/actuator/refresh` thành công không nhất thiết tạo ngay target mới cho mọi bean refresh-scoped. Target được khởi tạo khi bean được dùng tiếp theo.

`@RefreshScope` phù hợp với bean có trạng thái được khởi tạo từ cấu hình, ví dụ một client kết nối tới endpoint thay đổi hoặc một service wrapper giữ timeout lúc khởi tạo. Tuy nhiên, không phải mọi tài nguyên đều có thể refresh an toàn. Một số loại bean, như `HikariDataSource`, nằm trong danh sách mặc định không refreshable của Spring Cloud; hãy dùng cơ chế cấu hình lại được hỗ trợ hoặc restart có kiểm soát.

Đặt `@RefreshScope` lên một class `@Configuration` cũng không có nghĩa mọi bean được khai báo bên trong class đó đều tự động thuộc refresh scope. Nếu một bean phụ thuộc vào cấu hình được tạo lại, hãy xem xét scope của chính bean phụ thuộc và vòng đời của dependency.

## 13. Hiểu `@ConfigurationProperties` rebinding

Spring Cloud phát `EnvironmentChangeEvent` khi Environment thay đổi. Các bean `@ConfigurationProperties` được rebind để nhận giá trị mới.

Trong project, `DemoProperties` có setter và constructor rỗng, vì thế rebinder có thể cập nhật các field `message` và `timeout` trên bean đang tồn tại.

Có một số giới hạn cần nhớ:

- Java record và các bean dùng constructor binding không được hỗ trợ refresh rebinding.
- Rebinding thay đổi object tại chỗ, không thay toàn bộ object bằng một instance mới.
- Khi một bean có nhiều field được cập nhật, reader đồng thời có thể nhìn thấy trạng thái chuyển tiếp giữa giá trị cũ và mới.
- Collection có thể tạm thời rỗng trong một khoảng ngắn khi Binder cập nhật; nếu cần một snapshot nhất quán, cân nhắc `@RefreshScope`.
- Giá trị bị xóa khỏi Environment không phải lúc nào cũng được xử lý giống một giá trị mới; nếu cần tắt tính năng, nên dùng một cờ có giá trị tường minh thay vì phụ thuộc vào việc xóa key.

Với cấu hình nhiều field phải thay đổi nguyên tử, có thể gom chúng thành một bean refresh-scoped hoặc thiết kế immutable configuration snapshot và thay snapshot sau khi validation thành công.

## 14. Thử nghiệm restart ứng dụng

Giữ nguyên Git ở `v2`. Dừng process `orders-service` bằng Ctrl+C. Terminal đã dùng để chạy client ở bước 8 vẫn đang ở thư mục `orders-service`, vì vậy chạy Maven trực tiếp trong terminal đó:

```bash
mvn spring-boot:run
```

Nếu đã đóng terminal và mở terminal mới tại project root `config-refresh-lab`, chuyển vào thư mục client đúng một lần rồi chạy Maven:

```bash
cd orders-service
mvn spring-boot:run
```

Sau khi startup hoàn tất, gọi:

```bash
curl http://localhost:8080/demo/state
```

Kết quả mong đợi:

```json
{
  "environment": "Xin chào từ cấu hình Git v2",
  "configurationProperties": "Xin chào từ cấu hình Git v2",
  "plainSingleton": "Xin chào từ cấu hình Git v2",
  "refreshScope": "Xin chào từ cấu hình Git v2",
  "timeout": "PT2S"
}
```

Restart tạo lại ApplicationContext, do đó tất cả singleton và refresh-scoped target được tạo mới từ cấu hình hiện hành. Nó cũng chạy lại toàn bộ quá trình startup, bao gồm kết nối dependency, khởi tạo cache, listener và resource pool.

Trong production, restart thường được thực hiện qua rolling deployment/orchestrator để thay instance theo từng đợt và duy trì capacity. Không nên restart tất cả replica cùng lúc nếu ứng dụng không có dư capacity hoặc không có cơ chế bảo đảm availability.

## 15. So sánh ba cơ chế sau project

| Tiêu chí | Refresh Environment | `@RefreshScope` | Restart process |
|---|---|---|---|
| Mục đích | Nạp lại property source và phát sự kiện thay đổi. | Tạo lại target của bean được đánh dấu. | Khởi tạo lại toàn bộ ứng dụng. |
| Phạm vi | Environment của một process. | Bean thuộc refresh scope trong process đó. | Tất cả bean/tài nguyên trong process. |
| `@ConfigurationProperties` | Rebind theo `EnvironmentChangeEvent` nếu bean hỗ trợ. | Có thể dùng refresh scope cho bean cần thay instance/snapshot nhất quán. | Bind lại từ đầu khi startup. |
| Bean thường có `@Value` | Không tự thay field đã inject vào singleton. | Được cập nhật nếu chính bean đó thuộc refresh scope. | Được tạo lại và inject giá trị mới. |
| Thời điểm áp dụng | Sau khi refresh lấy được Environment mới. | Target mới được tạo ở lần gọi kế tiếp sau khi cache bị clear. | Sau khi process mới khởi động thành công. |
| Tác động | Không cần dừng process, nhưng có thể có trạng thái chuyển tiếp. | Chỉ tác động bean được scope, cần xem dependency/lifecycle. | Có startup time và gián đoạn nếu không rolling. |
| Phù hợp | Thay đổi property và rebinding có thể thực hiện an toàn. | Bean giữ state/config ở thời điểm khởi tạo. | Thay đổi không refreshable, cần tái tạo wiring hoặc resource toàn cục. |

Refresh Environment và `@RefreshScope` thường được dùng cùng nhau. `@RefreshScope` không tự tìm cấu hình mới trong Git; nó cần Environment được cập nhật trước. Restart là phương án rộng hơn vì nó tạo lại toàn bộ process state.

## 16. Thử thêm một thay đổi kiểu dữ liệu

Đổi cả message và timeout:

```yaml
demo:
  message: "Xin chào từ cấu hình Git v3"
  timeout: 5s
```

Commit, xác nhận Config Server trả `v3`, rồi gọi `/actuator/refresh`.

`DemoProperties.timeout` được Binder chuyển từ chuỗi `5s` thành `Duration`. Trong JSON endpoint, `Duration.toString()` có thể trả `PT5S`. Đây là biểu diễn ISO-8601 của năm giây, không phải lỗi dữ liệu.

Nếu timeout được dùng để tạo một HTTP client hoặc connection pool trong constructor của bean thường, thay đổi Environment không tự cấu hình lại object đó. Hãy đặt bean khởi tạo client trong refresh scope nếu implementation hỗ trợ tái tạo an toàn, hoặc lên kế hoạch restart.

## 17. Thử nghiệm nhiều instance

Chạy hai instance `orders-service` với hai port khác nhau, ví dụ `8080` và `8081`, cùng application/profile/label. Mở hai terminal tại thư mục `orders-service`. Terminal thứ nhất dùng port mặc định `8080`:

```bash
mvn spring-boot:run
```

Terminal thứ hai phải override `server.port` để tránh chiếm cùng port:

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--server.port=8081"
```

Lệnh override trên dùng Spring Boot Maven Plugin; trên PowerShell cũng có thể chạy nguyên lệnh trong dấu nháy như trên.

1. Khởi động cả hai khi Git chứa `v1`.
2. Commit `v2`.
3. Gọi `/actuator/refresh` trên instance `8080`.
4. Gọi `/demo/state` trên cả hai instance.

Instance `8080` sẽ có Environment mới; instance `8081` vẫn giữ Environment cũ cho đến khi được refresh hoặc restart. Endpoint `/actuator/refresh` chỉ tác động process nhận request.

Trong hệ thống nhiều replica, có thể gửi refresh đến từng instance. Spring Cloud Bus là phần mở rộng tùy chọn, không nằm trong các bước được kiểm thử của project này: project chưa thêm Bus starter, chưa cấu hình RabbitMQ/Kafka và chưa kiểm tra broadcast event. Nếu muốn thực hành Bus, cần bổ sung dependency `spring-cloud-starter-bus-amqp` hoặc `spring-cloud-starter-bus-kafka`, cấu hình broker cho mọi client, expose/bảo vệ endpoint Bus và xác minh event/ack cùng revision ở từng instance. Dù dùng Bus, vẫn cần quan sát instance nào đã xử lý và kiểm soát burst.

## 18. Kiểm tra lỗi và tình huống biên

| Thử nghiệm | Kết quả cần quan sát | Cách xử lý |
|---|---|---|
| Config Server tắt trước khi client startup | Import bắt buộc khiến client startup thất bại. | Khởi động Config Server trước; trong production quyết định rõ required hay optional fallback. |
| Git commit mới nhưng Config Server response vẫn cũ | Server đang dùng label khác hoặc remote fetch chưa cập nhật. | Kiểm tra endpoint trực tiếp, label và `refresh-rate`. |
| POST refresh trả lỗi | Config Server không truy cập được, refresh context lỗi hoặc property source không hợp lệ. | Đọc log client/server, xác nhận Git response trước khi retry. |
| `Environment` đổi nhưng bean `@Value` không đổi | Bean thường giữ field đã inject lúc khởi tạo. | Dùng `@ConfigurationProperties`, `@RefreshScope` hoặc restart theo nhu cầu. |
| `@RefreshScope` bean lỗi ở lần gọi sau refresh | Constructor/khởi tạo target không thành công với giá trị mới. | Kiểm tra validation, dependency và log refresh scope. |
| `@ConfigurationProperties` không đổi | Bean dùng constructor binding/record hoặc không được đăng ký đúng. | Dùng mutable bean phù hợp hoặc refresh scope; xác minh bean registration. |
| Một số replica vẫn dùng `v1` | Chỉ một instance nhận refresh. | Refresh từng instance hoặc phát event qua Bus. |
| Xóa property rồi refresh nhưng giá trị cũ còn | Xử lý property bị loại bỏ có giới hạn và default có thể được giữ. | Dùng cờ/giá trị tường minh, kiểm tra Environment và class-level default. |

## 19. Bảo vệ endpoint refresh

`/actuator/refresh` có thể thay đổi cấu hình đang chạy và làm khởi tạo lại các bean có state. Nếu kẻ không có quyền gọi được endpoint này, họ có thể gây thay đổi hành vi hoặc làm gián đoạn ứng dụng.

Trong production:

- Chỉ expose endpoint thật sự cần thiết.
- Bảo vệ bằng Spring Security, role quản trị và authentication mạnh.
- Giới hạn management endpoint qua mạng nội bộ, mTLS hoặc network policy.
- Ghi audit: ai yêu cầu refresh, lúc nào, application/instance nào và revision nào được áp dụng.
- Kiểm tra config revision và validation trước khi phát lệnh refresh diện rộng.
- Nếu đã bổ sung và kiểm thử đầy đủ broker/dependency, dùng Spring Cloud Bus; nếu không, refresh từng instance hoặc dùng deployment controller có kiểm soát khi cần cập nhật nhiều instance.
- Không expose `/actuator/env`, `/actuator/configprops` hoặc giá trị secret chỉ để phục vụ project refresh.

Endpoint `/actuator/restart` của Spring Cloud Context bị tắt mặc định trong các cấu hình hiện hành. Trong production, nên thực hiện restart qua cơ chế rollout của nền tảng để có readiness, drain traffic và rollback rõ ràng.

## 20. Quy trình áp dụng thay đổi cấu hình trong môi trường thật

Một quy trình có thể dùng cho release cấu hình:

1. Tạo commit hoặc tag cấu hình có thể truy vết.
2. Kiểm tra Config Server trả đúng application/profile/label/revision.
3. Kiểm tra các property bắt buộc và kiểu dữ liệu.
4. Chọn cơ chế: refresh, refresh-scoped bean hay rolling restart.
5. Áp dụng trên một canary instance.
6. Kiểm tra `/actuator/health`, log, metric và hành vi nghiệp vụ.
7. Xác nhận revision mới trên canary trước khi mở rộng.
8. Cập nhật từng nhóm instance; theo dõi lỗi khởi tạo lại bean và connection pool.
9. Nếu có lỗi, rollback Git label/commit hoặc triển khai cấu hình sửa lỗi và refresh/restart theo kế hoạch.
10. Ghi nhận revision cuối cùng mà mỗi instance đang dùng.

Không dùng refresh như một cam kết rằng mọi thay đổi đều có thể áp dụng mà không gián đoạn. Các thay đổi port listener, cấu trúc bean graph, datasource không refreshable hoặc resource đã được thư viện khởi tạo có thể cần restart.

## 21. Checklist hoàn thành project

- [ ] Git repository `config-repo` có branch `main` và commit `v1`.
- [ ] Config Server đọc được `orders-service/dev/main`.
- [ ] Config Client nạp được `demo.message` và `demo.timeout`.
- [ ] Endpoint `/demo/state` hiển thị giá trị từ Environment và ba kiểu bean.
- [ ] Commit `v2` đã được tạo trong Git.
- [ ] Config Server trực tiếp trả `v2` trước khi refresh client.
- [ ] Trước refresh, client vẫn hiển thị `v1`.
- [ ] Sau `/actuator/refresh`, Environment và `@ConfigurationProperties` là `v2`.
- [ ] Bean thường dùng `@Value` vẫn là `v1` sau refresh.
- [ ] Bean `@RefreshScope` là `v2` sau lần gọi tiếp theo.
- [ ] Sau restart, tất cả bean đều là `v2`.
- [ ] Đã thử ít nhất một thay đổi `Duration`.
- [ ] Đã hiểu refresh endpoint chỉ tác động một instance.
- [ ] Đã giới hạn endpoint quản trị và không đưa secret vào response.

## 22. Câu hỏi tự kiểm tra

1. Vì sao commit Git không làm Environment của Config Client tự thay đổi?
2. `/actuator/refresh` thực hiện những công việc nào?
3. Vì sao bean singleton dùng constructor `@Value` vẫn giữ giá trị cũ sau refresh?
4. Spring Cloud rebind `@ConfigurationProperties` theo sự kiện nào?
5. Vì sao class mutable có no-argument constructor phù hợp với bài lab này?
6. Java record dùng constructor binding có được refresh rebinding không?
7. `@RefreshScope` proxy và target bean khác nhau như thế nào?
8. Khi nào target refresh-scoped bean mới được tạo lại?
9. Vì sao Environment đã đổi nhưng bean khởi tạo HTTP client có thể vẫn dùng timeout cũ?
10. Khi nào nên restart thay vì refresh?
11. `/actuator/refresh` có tự cập nhật mọi replica không?
12. Cần làm gì để endpoint refresh an toàn trong production?

Sau project, bạn có thể thay đổi một property trong Git, xác minh revision qua Config Server, refresh Config Client và quan sát tác động riêng lên Environment, `@ConfigurationProperties`, singleton thường và `@RefreshScope`; từ đó lựa chọn giữa refresh và restart dựa trên vòng đời thực tế của bean.

## Tài liệu tham khảo

- [Spring Cloud Config – Quick Start and Client](https://docs.spring.io/spring-cloud-config/reference/): dựng Config Server, Config Client và `spring.config.import`.
- [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): `EnvironmentChangeEvent`, rebinding `@ConfigurationProperties`, `@RefreshScope`, refresh endpoint và giới hạn refresh.
- [Spring Cloud Config – Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html): Git URI, local `file:` repository, default label và `refresh-rate`.
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): expose, secure và quản lý endpoint Actuator.
