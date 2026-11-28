# Dựng Config Server cùng hai client dùng cấu hình chung và riêng

Trong bài thực hành này, bạn sẽ dựng một hệ thống nhỏ gồm một Spring Cloud Config Server và hai Spring Boot Config Client: `order-service` và `inventory-service`. Hai service cùng nhận cấu hình nền từ `application.yml`, sau đó nhận cấu hình riêng theo tên ứng dụng và profile. Tất cả dữ liệu được lưu trong một Git repository để có thể review, commit và chọn phiên bản bằng label.

Kết quả cuối cùng là hai service chạy ở hai cổng khác nhau, cùng hiển thị banner và môi trường từ cấu hình chung nhưng có owner, giới hạn đơn hàng và ngưỡng tồn kho riêng. Bạn cũng sẽ thay đổi Git, yêu cầu từng client refresh và quan sát giá trị mới mà không phải dừng ứng dụng.

## 1. Mục tiêu và kiến trúc

Sau khi hoàn thành, bạn có thể:

- Tạo Config Server bằng `@EnableConfigServer` và cấu hình Git backend.
- Tạo hai Config Client dùng `spring.config.import`.
- Tổ chức cấu hình dùng chung, cấu hình riêng theo application và profile.
- Hiểu precedence giữa `order-service-dev.yml`, `application-dev.yml`, `order-service.yml` và `application.yml`.
- Xác minh cấu hình bằng HTTP Environment API và endpoint của từng client.
- Thay đổi Git, commit và refresh từng client bằng Actuator.
- Chọn profile và Git label khác nhau để tái lập một phiên bản cấu hình.

Kiến trúc lab:

```text
                         Git config-repo
                    application.yml
                    application-dev.yml
                    order-service*.yml
                    inventory-service*.yml
                              |
                              | Git backend
                              v
                    +--------------------+
                    | Config Server      |
                    | localhost:8888     |
                    +---------+----------+
                              |
                   Config Data over HTTP
                     /                \
                    v                  v
          +----------------+  +--------------------+
          | order-service  |  | inventory-service  |
          | localhost:8081|  | localhost:8082     |
          +----------------+  +--------------------+
```

Config Server đọc Git và trả một `Environment` theo application/profile/label. Mỗi client dùng `spring.application.name` để yêu cầu đúng cấu hình của mình. Client không cần biết cấu trúc Git repository; nó chỉ cần địa chỉ Config Server và selector cần dùng.

## 2. Phiên bản và công cụ

Ví dụ sử dụng các bản GA hiện hành tại thời điểm biên soạn:

| Thành phần | Phiên bản |
|---|---:|
| Java | 21 |
| Spring Boot | 4.2.0 |
| Spring Cloud release train | 2026.0.0 (Paddington) |
| Spring Cloud Config | 5.1.0, do BOM quản lý |
| Maven | 3.9 trở lên |
| Git | Phiên bản hỗ trợ `git init -b main` |

Spring Cloud 2026.0.0 tương thích với Spring Boot 4.2.0. Giữ Spring Cloud BOM để các module dùng cùng release train; không tự gán version riêng cho `spring-cloud-config-server` hoặc `spring-cloud-starter-config`.

Máy thực hành cần có JDK 21, Maven, Git, `jq` (cho các API assertion trong Bash) và một terminal. Các lệnh có ví dụ PowerShell cho Windows và Bash cho Linux/macOS ở bước cấu hình Git URI.

## 3. Tạo cấu trúc Maven multi-module

Tạo thư mục dự án `spring-cloud-config-lab` với cấu trúc:

```text
spring-cloud-config-lab/
├── pom.xml
├── config-repo/                 # Git repository chứa cấu hình
│   ├── application.yml
│   ├── application-dev.yml
│   ├── application-prod.yml
│   ├── order-service.yml
│   ├── order-service-dev.yml
│   ├── order-service-prod.yml
│   ├── inventory-service.yml
│   ├── inventory-service-dev.yml
│   └── inventory-service-prod.yml
├── config-server/
│   ├── pom.xml
│   └── src/main/
│       ├── java/com/example/configserver/ConfigServerApplication.java
│       └── resources/application.yml
├── order-service/
│   ├── pom.xml
│   └── src/main/java/com/example/orders/...
└── inventory-service/
    ├── pom.xml
    └── src/main/java/com/example/inventory/...
```

`config-repo` là một Git repository độc lập với repository chứa source code ứng dụng. Trong production, config repo thường được host trên Git server nội bộ. Với lab, dùng local Git repository để không cần tài khoản Git từ xa.

### POM ở thư mục gốc

Tạo `spring-cloud-config-lab/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.2.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-cloud-config-lab</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>config-server</module>
        <module>order-service</module>
        <module>inventory-service</module>
    </modules>

    <properties>
        <java.version>21</java.version>
        <spring-cloud.version>2026.0.0</spring-cloud.version>
    </properties>

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
</project>
```

Parent POM quản lý Spring Boot, Java và Spring Cloud BOM. Ba module kế thừa các version này và không khai báo version lặp lại cho dependency Spring Cloud.

## 4. Tạo Config Server

### Dependency

Tạo `config-server/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>spring-cloud-config-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>config-server</artifactId>

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

### Main class

Tạo `config-server/src/main/java/com/example/configserver/ConfigServerApplication.java`:

```java
package com.example.configserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
```

`@EnableConfigServer` bật HTTP API và các Environment Repository backend của Spring Cloud Config Server.

### Cấu hình Git backend

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
          refresh-rate: 0

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Ý nghĩa:

- `server.port=8888`: cổng mặc định quen thuộc của Config Server.
- `spring.cloud.config.server.git.uri`: Git repository mà server sẽ đọc; giá trị được truyền từ biến môi trường để URI không phụ thuộc máy.
- `default-label=main`: dùng branch `main` khi client không gửi label.
- `refresh-rate=0`: với remote Git, server fetch mỗi lần có request; giá trị dương giới hạn tần suất fetch theo giây và giá trị âm tắt refresh repository. Lab này dùng `file:` URI nên Config Server đọc working tree local trực tiếp, không clone/fetch; do đó `refresh-rate` và `clone-on-start` không được thực hành ở đây.
- `health,info`: chỉ expose các endpoint Actuator cơ bản của Config Server trong lab.

## 5. Tạo Git config repository

Từ thư mục gốc dự án, tạo repository và branch `main`:

```bash
mkdir config-repo
cd config-repo
git init -b main
```

Nếu Git quá cũ chưa hỗ trợ `git init -b`, chạy `git init` rồi tạo branch bằng `git switch -c main`.

### Cấu hình chung cho mọi application

Tạo `config-repo/application.yml`:

```yaml
platform:
  banner: "Cấu hình dùng chung cho toàn hệ thống"
  support-email: "support@example.test"
  environment: "default"
  audit-enabled: true
```

Tên `application` là context chung. Cả `order-service` và `inventory-service` đều có thể nhận các thuộc tính `platform.*` từ file này.

### Cấu hình chung theo profile

Tạo `config-repo/application-dev.yml`:

```yaml
platform:
  environment: "development"
  audit-enabled: false
  precedence-probe: "from-shared-dev"
```

Tạo `config-repo/application-prod.yml`:

```yaml
platform:
  environment: "production"
  audit-enabled: true
```

Hai file này ghi đè một phần cấu hình chung khi client dùng profile tương ứng. Chúng không cần lặp lại `banner` hoặc `support-email` vì các khóa đó vẫn được lấy từ `application.yml`.

### Cấu hình riêng cho order-service

Tạo `config-repo/order-service.yml`:

```yaml
service:
  owner: "order-team"

platform:
  precedence-probe: "from-order-default"

orders:
  max-items: 25
  currency: "VND"
  reservation-window: 15m
```

Tạo `config-repo/order-service-dev.yml`:

```yaml
orders:
  max-items: 50
  reservation-window: 30m
```

Tạo `config-repo/order-service-prod.yml`:

```yaml
orders:
  max-items: 100
  reservation-window: 5m
```

### Cấu hình riêng cho inventory-service

Tạo `config-repo/inventory-service.yml`:

```yaml
service:
  owner: "inventory-team"

inventory:
  low-stock-threshold: 5
  reservation-ttl: 15m
```

Tạo `config-repo/inventory-service-dev.yml`:

```yaml
inventory:
  low-stock-threshold: 12
  reservation-ttl: 30m
```

Tạo `config-repo/inventory-service-prod.yml`:

```yaml
inventory:
  low-stock-threshold: 25
  reservation-ttl: 10m
```

### Sơ đồ precedence của các file

Khi `order-service` yêu cầu profile `dev`, Config Server tìm các nguồn theo mức độ cụ thể:

```text
Ưu tiên cao
  order-service-dev.yml   (application + profile)
  application-dev.yml     (shared + profile)
  order-service.yml       (application)
  application.yml         (shared)
Ưu tiên thấp
```

Với `inventory-service`, thứ tự tương ứng là `inventory-service-dev.yml`, `application-dev.yml`, `inventory-service.yml`, rồi `application.yml`. Nếu nhiều nguồn khai báo cùng một key, nguồn đứng trước thắng. Bài lab cố ý khai báo `platform.precedence-probe` trong cả `application-dev.yml` (`from-shared-dev`) và `order-service.yml` (`from-order-default`). Khi `order-service` chạy profile `dev`, giá trị `from-shared-dev` phải thắng vì shared profile-specific source có độ ưu tiên cao hơn application-specific default source.

### Commit cấu hình ban đầu

Trong thư mục `config-repo`, commit các file:

```bash
git config --local user.name "Config Lab"
git config --local user.email "config-lab@example.test"
git add .
git commit -m "Add shared and service configuration"
git tag v1.0.0
```

Đặt `user.name` và `user.email` ở cấp repository để Git có thông tin tác giả khi commit; thay bằng tên/email phù hợp với môi trường thực hành. Tag `v1.0.0` được tạo ngay sau commit ban đầu nên giữ snapshot cấu hình trước các thay đổi tiếp theo.

Kiểm tra branch, commit và tag:

```bash
git branch --show-current
git log -1 --oneline
git rev-parse HEAD
git rev-parse v1.0.0
```

Kết quả branch cần là `main`; ngay sau commit đầu, hai lệnh `rev-parse` phải trả cùng một commit ID.

## 6. Trỏ Config Server tới local Git repository

Config Server cần một Git URI tuyệt đối có thể đọc từ tiến trình đang chạy. Mở terminal mới tại thư mục gốc `spring-cloud-config-lab`.

### Windows PowerShell

```powershell
$repoPath = (Resolve-Path .\config-repo).Path.Replace('\', '/')
$env:CONFIG_REPO_URI = ([System.Uri]::new($repoPath)).AbsoluteUri
mvn -pl config-server spring-boot:run
```

`System.Uri.AbsoluteUri` tạo URI file hợp lệ và percent-encode khoảng trắng cùng ký tự dành riêng trong path, ví dụ `#` thành `%23` và `?` thành `%3F`.

### Linux/macOS Bash

```bash
repo_path="$(cd ./config-repo && pwd -P)"
case "$repo_path" in
  *[[:space:]#?]*) echo "Use a path without spaces, # or ? for this lab URI example." >&2; exit 1 ;;
esac
export CONFIG_REPO_URI="file://${repo_path}"
mvn -pl config-server spring-boot:run
```

Ví dụ Bash yêu cầu đường dẫn không có khoảng trắng, `#` hoặc `?`; nếu cần dùng các ký tự này, hãy percent-encode chúng trong URI (ví dụ `%20`, `%23`, `%3F`). Giữ terminal này mở. Nếu biến `CONFIG_REPO_URI` không tồn tại hoặc URI sai, Config Server không thể đọc Git repository.

Với URI `file:`, Config Server đọc trực tiếp Git repository tại đường dẫn local và không clone repository sang working copy riêng. Commit mới trên local repo được thấy ở request tiếp theo. Vì vậy lab này không kiểm chứng clone ban đầu, `clone-on-start` hay chu kỳ fetch `refresh-rate`; muốn thực hành các hành vi đó, hãy chuyển `uri` sang remote Git qua HTTPS/SSH. Local `file:` repository chỉ phù hợp cho lab; production nên dùng remote Git với credential được quản lý.

## 7. Kiểm tra Config Server trước khi chạy client

Gọi trực tiếp Environment API:

```bash
curl http://localhost:8888/order-service/dev/main
curl http://localhost:8888/inventory-service/dev/main
```

Nếu dùng PowerShell:

```powershell
Invoke-RestMethod http://localhost:8888/order-service/dev/main |
    ConvertTo-Json -Depth 10
```

Response là JSON có `name`, `profiles`, `label`, `version` và `propertySources`. Kiểm tra:

- Request order trả `name=order-service` và profile `dev`.
- Request inventory trả `name=inventory-service` và profile `dev`.
- Cả hai có property source dùng chung từ `application.yml` và `application-dev.yml`.
- Mỗi response có property source riêng của service tương ứng.
- `orders.max-items` và `inventory.low-stock-threshold` có giá trị riêng theo service/profile.

Có thể kiểm tra chính xác các giá trị trong `propertySources[].source` bằng `jq`. Ví dụ dưới đây lấy giá trị đầu tiên của một key theo thứ tự property source, đồng thời xác nhận cả hai nguồn xung đột đều có mặt:

```bash
curl --fail --silent --show-error http://localhost:8888/order-service/dev/main \
  | jq -e '
      def effective($key): [.propertySources[] | .source[$key]? | select(. != null)][0];
      .name == "order-service"
      and .profiles == ["dev"]
      and .label == "main"
      and effective("platform.banner") == "Cấu hình dùng chung cho toàn hệ thống"
      and effective("orders.max-items") == 50
      and any(.propertySources[]; (.name | contains("application-dev.yml")) and .source["platform.precedence-probe"] == "from-shared-dev")
      and any(.propertySources[]; (.name | contains("order-service.yml")) and .source["platform.precedence-probe"] == "from-order-default")
      and effective("platform.precedence-probe") == "from-shared-dev"
    '
```

Với inventory-service, có thể xác nhận cấu hình riêng và giá trị dùng chung:

```bash
curl --fail --silent --show-error http://localhost:8888/inventory-service/dev/main \
  | jq -e '
      def effective($key): [.propertySources[] | .source[$key]? | select(. != null)][0];
      .name == "inventory-service"
      and .profiles == ["dev"]
      and effective("platform.precedence-probe") == "from-shared-dev"
      and effective("inventory.low-stock-threshold") == 12
    '
```

Git backend đặt commit được đọc vào trường `Environment.version`. So sánh nó với `HEAD` của local config repository để xác nhận Config Server đang trả đúng commit:

```bash
expected_version="$(git -C config-repo rev-parse HEAD)"
actual_version="$(curl --fail --silent --show-error http://localhost:8888/order-service/dev/main | jq -r '.version')"
test "$actual_version" = "$expected_version" && echo "Config Server version matches Git HEAD"
```

Nếu endpoint trả HTTP 200 nhưng `propertySources` rỗng, kiểm tra `name`, profile, label và repository. Mặc định `spring.cloud.config.server.accept-empty=true`, nên application không tồn tại thường trả Environment rỗng với HTTP 200. Chỉ khi đặt `spring.cloud.config.server.accept-empty=false`, application không tồn tại mới được trả HTTP 404. Label không tồn tại và lỗi backend là các trường hợp riêng; xem response và log để xác định nguyên nhân, không quy mọi HTTP 404 cho cùng một lỗi.

Nếu Config Server chưa khởi động, xem log đọc repository thay vì tiếp tục chạy client.

## 8. Tạo order-service

### POM

Tạo `order-service/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>spring-cloud-config-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>order-service</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-config</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

### Main class

Tạo `order-service/src/main/java/com/example/orders/OrderServiceApplication.java`:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderServiceApplication.class, args);
    }
}
```

### Class nhận cấu hình dùng chung

Tạo `order-service/src/main/java/com/example/orders/config/PlatformProperties.java`:

```java
package com.example.orders.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "platform")
public class PlatformProperties {

    private String banner;
    private String supportEmail;
    private String environment;
    private boolean auditEnabled;

    public String getBanner() { return banner; }
    public void setBanner(String banner) { this.banner = banner; }
    public String getSupportEmail() { return supportEmail; }
    public void setSupportEmail(String supportEmail) { this.supportEmail = supportEmail; }
    public String getEnvironment() { return environment; }
    public void setEnvironment(String environment) { this.environment = environment; }
    public boolean isAuditEnabled() { return auditEnabled; }
    public void setAuditEnabled(boolean auditEnabled) { this.auditEnabled = auditEnabled; }
}
```

### Class nhận cấu hình riêng của service

Tạo `order-service/src/main/java/com/example/orders/config/ServiceProperties.java`:

```java
package com.example.orders.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "service")
public class ServiceProperties {

    private String owner;

    public String getOwner() { return owner; }
    public void setOwner(String owner) { this.owner = owner; }
}
```

Tạo `order-service/src/main/java/com/example/orders/config/OrderProperties.java`:

```java
package com.example.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "orders")
public class OrderProperties {

    private int maxItems;
    private String currency;
    private Duration reservationWindow;

    public int getMaxItems() { return maxItems; }
    public void setMaxItems(int maxItems) { this.maxItems = maxItems; }
    public String getCurrency() { return currency; }
    public void setCurrency(String currency) { this.currency = currency; }
    public Duration getReservationWindow() { return reservationWindow; }
    public void setReservationWindow(Duration reservationWindow) {
        this.reservationWindow = reservationWindow;
    }
}
```

Các class trên dùng JavaBean getter/setter để Spring Boot bind và Spring Cloud có thể rebind cấu hình khi refresh.

### Controller hiển thị cấu hình đã bind

Tạo `order-service/src/main/java/com/example/orders/OrderConfigController.java`:

```java
package com.example.orders;

import java.util.Map;
import com.example.orders.config.OrderProperties;
import com.example.orders.config.PlatformProperties;
import com.example.orders.config.ServiceProperties;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo")
public class OrderConfigController {

    private final PlatformProperties platform;
    private final ServiceProperties service;
    private final OrderProperties orders;

    public OrderConfigController(PlatformProperties platform,
                                 ServiceProperties service,
                                 OrderProperties orders) {
        this.platform = platform;
        this.service = service;
        this.orders = orders;
    }

    @GetMapping("/config")
    public Map<String, Object> config() {
        return Map.of(
                "banner", platform.getBanner(),
                "supportEmail", platform.getSupportEmail(),
                "environment", platform.getEnvironment(),
                "auditEnabled", platform.isAuditEnabled(),
                "owner", service.getOwner(),
                "maxItems", orders.getMaxItems(),
                "currency", orders.getCurrency(),
                "reservationWindow", orders.getReservationWindow().toString()
        );
    }
}
```

Controller đọc trực tiếp các bean cấu hình. Endpoint chỉ trả các giá trị không nhạy cảm để bạn quan sát kết quả của Config Client.

### Cấu hình local của order-service

Tạo `order-service/src/main/resources/application.yml`:

```yaml
server:
  port: 8081

spring:
  application:
    name: order-service
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
        include: health,refresh
```

`spring.config.import` không có tiền tố `optional:` nên Config Server là dependency bắt buộc trong lab: nếu không lấy được cấu hình, ứng dụng sẽ fail khi khởi động. `spring.application.name` xác định file riêng mà Config Server tìm. `spring.profiles.active=dev` kích hoạt file profile-specific. `spring.cloud.config.label=main` chọn branch `main` trong Git.

## 9. Tạo inventory-service

### POM

Tạo `inventory-service/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.example</groupId>
        <artifactId>spring-cloud-config-lab</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>inventory-service</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-config</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

### Main class

Tạo `inventory-service/src/main/java/com/example/inventory/InventoryServiceApplication.java`:

```java
package com.example.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class InventoryServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(InventoryServiceApplication.class, args);
    }
}
```

### Các class cấu hình

Tạo `inventory-service/src/main/java/com/example/inventory/config/PlatformProperties.java`:

```java
package com.example.inventory.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "platform")
public class PlatformProperties {

    private String banner;
    private String supportEmail;
    private String environment;
    private boolean auditEnabled;

    public String getBanner() { return banner; }
    public void setBanner(String banner) { this.banner = banner; }
    public String getSupportEmail() { return supportEmail; }
    public void setSupportEmail(String supportEmail) { this.supportEmail = supportEmail; }
    public String getEnvironment() { return environment; }
    public void setEnvironment(String environment) { this.environment = environment; }
    public boolean isAuditEnabled() { return auditEnabled; }
    public void setAuditEnabled(boolean auditEnabled) { this.auditEnabled = auditEnabled; }
}
```

Tạo `inventory-service/src/main/java/com/example/inventory/config/ServiceProperties.java`:

```java
package com.example.inventory.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "service")
public class ServiceProperties {

    private String owner;

    public String getOwner() { return owner; }
    public void setOwner(String owner) { this.owner = owner; }
}
```

Tạo `inventory-service/src/main/java/com/example/inventory/config/InventoryProperties.java`:

```java
package com.example.inventory.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "inventory")
public class InventoryProperties {

    private int lowStockThreshold;
    private Duration reservationTtl;

    public int getLowStockThreshold() { return lowStockThreshold; }
    public void setLowStockThreshold(int lowStockThreshold) {
        this.lowStockThreshold = lowStockThreshold;
    }
    public Duration getReservationTtl() { return reservationTtl; }
    public void setReservationTtl(Duration reservationTtl) {
        this.reservationTtl = reservationTtl;
    }
}
```

### Controller hiển thị cấu hình đã bind

Tạo `inventory-service/src/main/java/com/example/inventory/InventoryConfigController.java`:

```java
package com.example.inventory;

import java.util.Map;
import com.example.inventory.config.InventoryProperties;
import com.example.inventory.config.PlatformProperties;
import com.example.inventory.config.ServiceProperties;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo")
public class InventoryConfigController {

    private final PlatformProperties platform;
    private final ServiceProperties service;
    private final InventoryProperties inventory;

    public InventoryConfigController(PlatformProperties platform,
                                     ServiceProperties service,
                                     InventoryProperties inventory) {
        this.platform = platform;
        this.service = service;
        this.inventory = inventory;
    }

    @GetMapping("/config")
    public Map<String, Object> config() {
        return Map.of(
                "banner", platform.getBanner(),
                "supportEmail", platform.getSupportEmail(),
                "environment", platform.getEnvironment(),
                "auditEnabled", platform.isAuditEnabled(),
                "owner", service.getOwner(),
                "lowStockThreshold", inventory.getLowStockThreshold(),
                "reservationTtl", inventory.getReservationTtl().toString()
        );
    }
}
```

### Cấu hình local của inventory-service

Tạo `inventory-service/src/main/resources/application.yml`:

```yaml
server:
  port: 8082

spring:
  application:
    name: inventory-service
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
        include: health,refresh
```

Hai client dùng cùng Config Server, profile và label. Tên ứng dụng khác nhau khiến chúng nhận các property source riêng khác nhau.

## 10. Khởi động toàn bộ hệ thống

Bạn cần ba terminal. Đảm bảo Config Server đã chạy ở terminal thứ nhất.

### Terminal 2: order-service

Tại thư mục gốc Maven project:

```bash
mvn -pl order-service spring-boot:run
```

Service lắng nghe tại `http://localhost:8081`.

### Terminal 3: inventory-service

```bash
mvn -pl inventory-service spring-boot:run
```

Service lắng nghe tại `http://localhost:8082`.

Nếu một client dừng ở giai đoạn Config Data, kiểm tra log để biết nó không kết nối được Config Server, sai profile/label hay không tìm thấy cấu hình. Vì import đang bắt buộc, client sẽ không âm thầm chạy với một bộ cấu hình thiếu.

## 11. Kiểm tra kết quả của hai client

Gọi hai endpoint:

```bash
curl http://localhost:8081/demo/config
curl http://localhost:8082/demo/config
```

PowerShell:

```powershell
Invoke-RestMethod http://localhost:8081/demo/config |
    ConvertTo-Json -Depth 5
Invoke-RestMethod http://localhost:8082/demo/config |
    ConvertTo-Json -Depth 5
```

Kết quả mong đợi của order-service tương tự:

```json
{
  "banner": "Cấu hình dùng chung cho toàn hệ thống",
  "supportEmail": "support@example.test",
  "environment": "development",
  "auditEnabled": false,
  "owner": "order-team",
  "maxItems": 50,
  "currency": "VND",
  "reservationWindow": "PT30M"
}
```

Kết quả mong đợi của inventory-service tương tự:

```json
{
  "banner": "Cấu hình dùng chung cho toàn hệ thống",
  "supportEmail": "support@example.test",
  "environment": "development",
  "auditEnabled": false,
  "owner": "inventory-team",
  "lowStockThreshold": 12,
  "reservationTtl": "PT30M"
}
```

`PT30M` là cách `java.time.Duration` biểu diễn 30 phút theo ISO-8601. Cả hai service có cùng banner, email, environment và audit flag vì chúng đến từ cấu hình chung. `owner`, giới hạn đơn hàng và ngưỡng tồn kho khác nhau vì chúng đến từ file riêng của từng application.

## 12. Quan sát thứ tự property source

Gọi Config Server cho từng client:

```bash
curl http://localhost:8888/order-service/dev/main
curl http://localhost:8888/inventory-service/dev/main
```

Trong `propertySources`, bạn sẽ thấy các nguồn cụ thể của service và các nguồn dùng chung. Với order-service, thứ tự thường có dạng:

```text
order-service-dev.yml
application-dev.yml
order-service.yml
application.yml
```

Với inventory-service:

```text
inventory-service-dev.yml
application-dev.yml
inventory-service.yml
application.yml
```

Nguồn đứng trước có độ ưu tiên cao hơn. `orders.max-items` có trong `order-service-dev.yml` và `order-service.yml`, nên giá trị `50` từ application-profile source thắng giá trị `25` từ application-default source. Quan trọng hơn, `platform.precedence-probe` có trong cả `application-dev.yml` và `order-service.yml`; giá trị `from-shared-dev` từ shared-profile source thắng `from-order-default` từ application-default source. Trong khi đó `platform.banner` không có ở các file riêng nên được lấy từ `application.yml`.

Hãy kiểm tra response thực tế để xác nhận thứ tự property source của phiên bản/backend đang chạy.

## 13. Thay đổi cấu hình và refresh client

### Thay đổi cấu hình chung

Mở `config-repo/application.yml` và đổi banner:

```yaml
platform:
  banner: "Cấu hình chung đã được cập nhật"
  support-email: "support@example.test"
  environment: "default"
  audit-enabled: true
```

Commit thay đổi trong `config-repo`:

```bash
git add application.yml
git commit -m "Update shared platform banner"
```

Vì lab dùng `file:` URI, Config Server đọc trực tiếp local repository nên request kế tiếp sẽ thấy commit mới mà không cần fetch. `refresh-rate: 0` chỉ có ý nghĩa với remote Git. Xác minh server trước:

```bash
curl http://localhost:8888/order-service/dev/main
```

Tìm banner mới trong response. Nếu server chưa thấy thay đổi, kiểm tra commit, branch `main`, URI Git và log Config Server.

### Refresh từng client

Actuator đã được thêm vào hai client và endpoint `refresh` đã được expose. Gửi POST rỗng:

```bash
curl -X POST http://localhost:8081/actuator/refresh
curl -X POST http://localhost:8082/actuator/refresh
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8081/actuator/refresh
Invoke-RestMethod -Method Post -Uri http://localhost:8082/actuator/refresh
```

Gọi lại hai endpoint `/demo/config`. Cả hai service cần hiển thị banner mới. Trong lab này, bạn gọi refresh riêng từng client. Khi có nhiều instance, Spring Cloud Bus có thể phát một refresh event đến nhiều client thông qua broker; Bus là bước mở rộng tiếp theo, không cần thiết cho project cơ bản này.

## 14. Thử profile `prod`

Hai client hiện đang dùng profile `dev`. Để thấy cấu hình profile khác, dừng order-service hiện tại và chạy lại với profile `prod`.

PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
mvn -pl order-service spring-boot:run
```

Bash:

```bash
SPRING_PROFILES_ACTIVE=prod mvn -pl order-service spring-boot:run
```

Gọi endpoint order-service. Các giá trị mong đợi:

- `environment=production` và `auditEnabled=true` từ `application-prod.yml`.
- `maxItems=100` và `reservationWindow=PT5M` từ `order-service-prod.yml`.
- `owner=order-team` và `currency=VND` vẫn lấy từ `order-service.yml`.
- `banner` và `supportEmail` vẫn lấy từ `application.yml`.

Sau khi thử, dừng service và xóa biến môi trường trong PowerShell:

```powershell
Remove-Item Env:SPRING_PROFILES_ACTIVE
```

Profile chọn tập hợp cấu hình theo môi trường. Nó không phải label và không tạo một Git branch mới.

## 15. Thử Git label để tái lập cấu hình

Label của Git backend có thể là branch, tag hoặc commit ID. Tag `v1.0.0` đã được tạo ngay sau commit cấu hình ban đầu ở bước 5. Không tạo lại tag sau khi thay đổi banner. Sau khi commit bản mới trên branch `main`, xác nhận tag vẫn trỏ tới snapshot cũ:

```bash
git rev-parse v1.0.0
git rev-parse HEAD
curl http://localhost:8888/order-service/dev/main
curl http://localhost:8888/order-service/dev/v1.0.0
```

Sau commit banner mới, `git rev-parse v1.0.0` và `git rev-parse HEAD` phải khác nhau. Response dùng `main` nhận cấu hình mới; response dùng `v1.0.0` vẫn nhận snapshot tại commit ban đầu. Để client dùng tag, đặt `spring.cloud.config.label: v1.0.0` trong cấu hình local hoặc truyền property tương ứng khi khởi chạy.

Profile `dev` xác định biến thể môi trường; label `v1.0.0` xác định revision Git. Có thể kết hợp cả hai để tái lập cấu hình của một ứng dụng ở một môi trường và một phiên bản repository.

## 16. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Config Server không đọc được repository | `CONFIG_REPO_URI` thiếu/sai, thư mục chưa phải Git repo hoặc branch không tồn tại | Kiểm tra biến môi trường, `git status`, branch `main` và URI `file:///...` |
| Config Server trả HTTP 200 nhưng Environment rỗng | Application không tồn tại và `accept-empty` đang mặc định `true`, hoặc không có property source khớp | Kiểm tra `name`, profile, label và repository; đặt `spring.cloud.config.server.accept-empty=false` nếu muốn application không tồn tại trả 404 |
| Config Server trả 404 | Có thể đã đặt `accept-empty=false`, label/backend không hợp lệ hoặc request path sai | Kiểm tra `accept-empty`, URL `/{application}/{profile}/{label}`, log backend và tên file |
| Client không khởi động | Config Server chưa chạy hoặc import bắt buộc không kết nối được | Khởi động Config Server trước, kiểm tra `localhost:8888` và log client |
| Client gọi nhầm `localhost:8888` | Client chạy trong container khác hoặc máy khác | Dùng hostname/service name có thể truy cập từ môi trường client |
| Cấu hình chung có nhưng cấu hình riêng không có | `spring.application.name` sai hoặc file application-specific đặt sai tên | Dùng đúng `order-service`/`inventory-service` và đúng dấu gạch nối |
| Profile không ghi đè giá trị | Profile chưa active hoặc file profile-specific sai tên | Kiểm tra `spring.profiles.active` và tên `*-dev.yml`/`*-prod.yml` |
| Client nhận giá trị cũ sau Git commit | Config Server chưa đọc revision mới hoặc client chưa refresh | Với `file:` URI, kiểm tra local HEAD và server response; sau đó POST `/actuator/refresh` |
| Một client đổi nhưng client kia chưa đổi | Chỉ một client được refresh | Gửi refresh đến client còn lại; Bus chưa được bật trong lab này |
| `Duration` không bind được | Value không đúng cú pháp thời lượng | Dùng dạng `15m`, `30s`, `2h` hoặc ISO-8601 hợp lệ |
| `application.yml` ghi đè file riêng | Tên file hoặc thứ tự property source không đúng dự kiến | Xem `propertySources` trong response Config Server và sửa tên/context |
| Tag label trả 404 | Tag chưa được tạo hoặc server không nhìn thấy tag | Chạy `git tag --list` trong config repo và kiểm tra URI/branch |

## 17. Mở rộng và đưa mô hình vào production

Lab dùng local Git repository và Config Server không xác thực để tập trung vào luồng cấu hình. Trước khi triển khai thật:

- Đưa config repo lên Git server có backup, audit và review thay đổi.
- Dùng HTTPS hoặc SSH; xác minh TLS/SSH host key và cấp credential read-only cho Config Server.
- Không commit password, token, private key hoặc dữ liệu nhạy cảm dạng rõ. Dùng Vault/secret manager hoặc cơ chế mã hóa phù hợp.
- Bảo vệ Config Server API bằng authentication và authorization theo application/profile/label.
- Bảo vệ Actuator `/refresh`; chỉ mở trong management network và yêu cầu xác thực/phân quyền.
- Dùng `clone-on-start=true` với remote Git nếu muốn phát hiện lỗi repository ngay lúc Config Server khởi động.
- Triển khai nhiều Config Server instance khi cần HA; mỗi instance phải dùng cùng Git repository và cấu hình backend tương thích.
- Theo dõi Git revision, request lỗi, thời gian lấy cấu hình và trạng thái refresh của từng client.
- Khi cần refresh nhiều client cùng lúc, bổ sung Spring Cloud Bus và broker; kiểm tra event delivery thay vì giả định một request đã cập nhật mọi instance.

Không dùng local `file:` Git URI làm backend production cho nhiều Config Server replica. Tài liệu Spring Cloud Config khuyến nghị dùng remote Git qua HTTPS/SSH để mỗi server có working copy riêng.

## 18. Checklist hoàn thành lab

| Hạng mục | Kết quả cần đạt |
|---|---|
| Maven parent | Có ba module và Spring Cloud BOM 2026.0.0 |
| Config Server | Khởi động cổng 8888 và đọc Git branch `main` |
| Config repository | Có shared, service-specific và profile-specific YAML |
| Order client | Dùng application `order-service`, profile `dev`, port 8081 |
| Inventory client | Dùng application `inventory-service`, profile `dev`, port 8082 |
| Config Data import | Hai client dùng `configserver:http://localhost:8888` |
| Shared values | Hai client nhận cùng banner, email và môi trường |
| Private values | Mỗi client nhận owner và tham số nghiệp vụ riêng |
| Precedence | Application-profile > shared-profile > application-default > shared-default; đã kiểm tra key trùng |
| Refresh | Git commit mới được server nhìn thấy và cả hai client nhận sau refresh |
| Profile | Có thể chuyển từ `dev` sang `prod` |
| Label | Có thể đọc cùng profile từ branch/tag khác nhau |

## 19. Nguyên tắc cần ghi nhớ

- Config Server cung cấp API cấu hình tập trung; Git là nguồn lưu trữ và version control trong project này.
- `spring.config.import=configserver:...` kích hoạt Config Client trong Config Data mode.
- `spring.application.name` chọn cấu hình riêng của service; active profile chọn biến thể môi trường; label chọn revision Git.
- `application.yml` là cấu hình dùng chung; `<application>.yml` và `<application>-<profile>.yml` chứa cấu hình riêng và override.
- Thứ tự một profile: application-profile, shared-profile, application-default, shared-default; source đứng trước thắng khi trùng key.
- Config Server có thể trả Environment JSON để kiểm tra trước khi khởi động client.
- Với Git backend, `Environment.version` cho biết revision đã đọc và có thể đối chiếu với `git rev-parse HEAD` khi dùng local repository.
- Sau khi Git thay đổi, kiểm tra Config Server trước rồi refresh từng client qua `/actuator/refresh`.
- `@ConfigurationProperties` giúp bind các nhóm thuộc tính vào Java bean có kiểu rõ ràng.
- Actuator refresh là endpoint quản trị; phải bảo vệ nó trong production.
- Git label và Spring profile là hai selector khác nhau, có thể kết hợp để tái lập cấu hình.

Project này hoàn tất luồng tập trung cấu hình cơ bản: một Git repository lưu phần chung và phần riêng, một Config Server phục vụ chúng qua HTTP, và hai client độc lập nạp đúng cấu hình theo tên ứng dụng/profile. Khi bạn có thể thay đổi Git, xác minh Environment response, refresh hai client và tái lập một tag cũ, bạn đã nắm được vòng đời cơ bản của cấu hình tập trung bằng Spring Cloud Config.

## Tài liệu tham khảo

- [Spring Cloud 2026.0.0 — Release notes và Boot compatibility](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Boot 4.2.0 — Release announcement](https://spring.io/blog/2026/11/19/spring-boot-4-2-0-available-now/)
- [Spring Cloud Config 5.1 — Quick Start](https://docs.spring.io/spring-cloud-config/reference/quickstart.html)
- [Spring Cloud Config 5.1 — Config Server](https://docs.spring.io/spring-cloud-config/reference/server.html)
- [Spring Cloud Config 5.1 — Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html)
- [Spring Cloud Config 5.1 — Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Commons — Refresh Scope và `/actuator/refresh`](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
