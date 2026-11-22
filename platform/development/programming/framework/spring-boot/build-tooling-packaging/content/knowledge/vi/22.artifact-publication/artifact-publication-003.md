# Xuất bản artifact bằng Maven install, deploy và distributionManagement

## 1. Mục tiêu

Build thành công file JAR chỉ là một phần của quá trình phát hành. Những module khác, developer khác và CI cần tải đúng artifact theo tọa độ Maven. Maven có hai bước quan trọng:

- **`install`**: cài artifact vào **local repository** của máy hiện tại, mặc định `~/.m2/repository`, để các project khác trên cùng máy sử dụng.
- **`deploy`**: xuất bản artifact lên **remote Maven repository** như Nexus Repository hoặc Artifactory để những máy/pipeline khác tải xuống.

`<distributionManagement>` trong POM xác định đích publish. Credentials được lưu riêng trong `settings.xml`, tại `<server>` có `<id>` khớp repository ID trong POM.

Sau bài này, bạn cần phân biệt lifecycle `package`/`verify`/`install`/`deploy`, hiểu GAV/classifier, cấu hình release và snapshot repositories, đặt credentials an toàn, build/install/deploy và xác minh consumer tải được artifact. Bài cũng giải thích Maven multi-module, attached artifacts, Spring Boot `repackage` và lỗi publish thường gặp.

**Phiên bản ví dụ:** Apache Maven 3.9.x, Spring Boot 3.5.16 và Java 17. URL `repo.example.com` chỉ là tên miền minh họa; thay bằng repository manager do tổ chức cấp. Không dùng credential thật trong POM hoặc ví dụ công khai.

## 2. Maven lifecycle: install và deploy nằm ở đâu?

Default lifecycle quản lý compile, test, package, install và deploy. Mỗi phase được gọi sẽ chạy cả những phase đứng trước nó.

```text
validate
   |
compile
   |
test
   |
package       -> tạo JAR/WAR
   |
integration-test (nếu cấu hình)
   |
verify        -> kiểm tra package/kết quả test
   |
install       -> cài vào local repository
   |
deploy        -> upload lên remote repository
```

| Phase | Kết quả |
|---|---|
| `package` | Đóng gói code theo `<packaging>` |
| `verify` | Chạy các kiểm tra đã gắn vào lifecycle, có thể gồm integration-test checks |
| `install` | Ghi artifact và POM vào local Maven repository |
| `deploy` | Publish artifact, POM và attached artifacts tới remote repository |

Vì lifecycle chạy tuần tự, **`mvn deploy` đã bao gồm install và các phase trước đó**. Thông thường không cần chạy riêng `mvn install` rồi mới `mvn deploy` cho cùng một build.

```bash
./mvnw clean verify
./mvnw clean install
./mvnw clean deploy
```

- `clean verify`: build sạch và kiểm tra chất lượng, chưa publish.
- `clean install`: build sạch và cài local.
- `clean deploy`: build sạch và upload remote.

`install` và `deploy` là lifecycle phases; các goal mặc định `install:install` và `deploy:deploy` thực hiện công việc tương ứng. Thường gọi phase thay vì tự gọi plugin goal.

## 3. Artifact coordinates: Maven nhận diện file nào?

Tọa độ artifact:

```text
groupId : artifactId : version : classifier : extension
```

Ví dụ:

```text
com.example.platform : order-service : 1.4.0 : (none) : jar
```

- `groupId`: nhóm/tổ chức, thường dùng tên miền đảo ngược.
- `artifactId`: tên module/artifact.
- `version`: version phát hành; có thể là release hoặc `SNAPSHOT`.
- `classifier`: nhãn bổ sung như `sources`, `javadoc` hoặc `exec`.
- `extension`: định dạng như `jar`, `war` hoặc `pom`.

Dependency thông thường:

```xml
<dependency>
    <groupId>com.example.platform</groupId>
    <artifactId>order-service</artifactId>
    <version>1.4.0</version>
</dependency>
```

Maven không nhận diện dependency chỉ bằng tên file; GAV/classifier/extension xác định tọa độ.

### 3.1. Local repository layout

Với `com.example.platform:order-service:1.4.0`, local repository mặc định có cấu trúc:

```text
~/.m2/repository/
└── com/example/platform/order-service/1.4.0/
    ├── order-service-1.4.0.jar
    └── order-service-1.4.0.pom
```

Trên Windows, mặc định thường là `%USERPROFILE%\.m2\repository`. Có thể đổi bằng `<localRepository>` trong user settings hoặc `-Dmaven.repo.local=...`.

Artifact cài local **không tự xuất hiện** trên máy đồng nghiệp. Local repository thuộc môi trường người dùng/build machine hiện tại.

### 3.2. Maven publish cả POM

Khi install/deploy, Maven thường đưa lên JAR/WAR/POM chính, các attached artifacts (sources, javadoc, classifier khác) và metadata/checksum/signature theo cấu hình. POM mô tả dependency/transitive dependencies. Chỉ upload JAR thiếu POM có thể khiến consumer không resolve được dependency graph như mong đợi.

## 4. repositories, distributionManagement và settings.xml

| Thành phần | Mục đích |
|---|---|
| `<repositories>` | Nơi Maven tìm dependency để tải xuống |
| `<pluginRepositories>` | Nơi Maven tìm plugin artifacts |
| `<distributionManagement>` | Nơi artifact của project được upload khi chạy deploy |
| `<servers>` trong settings | Credentials theo repository/server ID |
| `<mirrors>` trong settings | Chuyển hướng repository requests qua mirror/repository manager |

**`distributionManagement` không phải nguồn dependency download.** Một project có thể publish vào release repository riêng nhưng consumer tải từ repository group URL qua `<repositories>` hoặc mirror.

POM được publish và có thể được mọi consumer tải; vì vậy **không đặt username/password/token trong `pom.xml`**.

## 5. Cấu hình distributionManagement cho release và snapshot

Thêm vào POM:

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <name>Company Maven Releases</name>
        <url>https://repo.example.com/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <name>Company Maven Snapshots</name>
        <url>https://repo.example.com/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

- `<repository>`: đích publish cho release version như `1.4.0`.
- `<snapshotRepository>`: đích publish cho version kết thúc `-SNAPSHOT` như `1.5.0-SNAPSHOT`.
- `<id>`: định danh repository để Maven tra server credentials trong settings.
- `<url>`: endpoint upload do repository manager cung cấp.

Maven chọn đích theo version hiện tại. Nếu không khai báo `snapshotRepository`, POM có quy tắc fallback sang `repository`; môi trường có policy tách biệt nên khai báo cả hai. URL ví dụ không phải repository thật.

### 5.1. Release và snapshot

| POM version | Loại | Đích |
|---|---|---|
| `1.0.0-SNAPSHOT` | Snapshot | `snapshotRepository` |
| `1.0.1-SNAPSHOT` | Snapshot | `snapshotRepository` |
| `1.0.0` | Release | `repository` |
| `1.0.0-rc1` | Theo quy ước release của tổ chức; Maven không xem là snapshot | Thường `repository` |

Maven nhận diện snapshot theo hậu tố `-SNAPSHOT`. Snapshot repository có thể cập nhật cùng tọa độ và quản lý timestamp/build number qua metadata. Release repository thường chặn ghi đè cùng version để bảo đảm tính bất biến. Không dùng release version như một tag mutable; nếu cần sửa lỗi, phát hành version mới.

## 6. Credentials trong settings.xml: server ID phải khớp

User settings mặc định tại:

```text
${user.home}/.m2/settings.xml
```

Ví dụ:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Maven settings hỗ trợ nội suy biến môi trường; ví dụ dùng biến `MAVEN_REPO_USER` và `MAVEN_REPO_TOKEN` trong môi trường CI. Nếu release và snapshot dùng credential khác nhau, dùng biến riêng.

**ID phải khớp chính xác:**

```text
POM repository.id       = company-releases
settings server.id      = company-releases
```

Tương tự với `company-snapshots`. Maven tra credential theo **ID**, không tự suy ra từ URL. ID không khớp thường dẫn tới `401 Unauthorized` hoặc lỗi xác thực tương tự.

### 6.1. Quy tắc bảo mật

- Không ghi token thật vào POM, source control, Dockerfile hoặc command line.
- Cấp user settings cho CI qua secret injection; không in nội dung settings ra log.
- Dùng account có quyền tối thiểu, chỉ publish vào repository cần thiết.
- Dùng HTTPS và certificate chain được tin cậy.
- Rotate/revoke token nếu lỡ commit hoặc in ra log.
- Password encryption của Maven settings là lớp bảo vệ phụ thuộc master password; với CI vẫn cần secret manager và kiểm soát runner.

POM mô tả artifact được publish ở đâu; settings mô tả thông tin xác thực của người thực hiện. Developer có thể có quyền đọc nhưng không có quyền deploy, đó là phân quyền bình thường.

## 7. Ví dụ Spring Boot 3.5 + Maven + Java 17

Tạo project `order-service` bằng Spring Initializr hoặc tạo các file sau. Dùng `spring-boot-starter-parent` để quản lý version plugin/dependencies và repackage configuration.

### 7.1. Cấu trúc

```text
order-service/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/
│   ├── maven-wrapper.jar
│   └── maven-wrapper.properties
└── src/
    ├── main/java/com/example/platform/order/
    │   ├── OrderApplication.java
    │   └── OrderController.java
    └── test/java/com/example/platform/order/
        └── OrderControllerTest.java
```

Wrapper scripts/JAR phải được sinh bởi Maven Wrapper/Initializr và commit hợp lệ; sơ đồ chỉ mô tả cấu trúc, không thay thế wrapper binaries.

### 7.2. pom.xml

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example.platform</groupId>
    <artifactId>order-service</artifactId>
    <version>1.4.0-SNAPSHOT</version>
    <name>Order Service</name>
    <description>Example Spring Boot artifact publication</description>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <distributionManagement>
        <repository>
            <id>company-releases</id>
            <url>https://repo.example.com/repository/maven-releases/</url>
        </repository>
        <snapshotRepository>
            <id>company-snapshots</id>
            <url>https://repo.example.com/repository/maven-snapshots/</url>
        </snapshotRepository>
    </distributionManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Spring Boot 3.5 Maven Plugin yêu cầu Maven 3.6.3 trở lên. `groupId`/`artifactId`/`version` xác định GAV; `distributionManagement` chọn remote repository; `spring-boot-maven-plugin` tạo executable JAR. Khi kế thừa starter parent, `repackage` execution đã được cấu hình sẵn, không cần thêm execution trùng.

### 7.3. Main class

`src/main/java/com/example/platform/order/OrderApplication.java`:

```java
package com.example.platform.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

### 7.4. Controller

`src/main/java/com/example/platform/order/OrderController.java`:

```java
package com.example.platform.order;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    @GetMapping("/orders/status")
    public Map<String, String> status() {
        return Map.of("service", "order-service", "status", "ready");
    }
}
```

### 7.5. JUnit test

`src/test/java/com/example/platform/order/OrderControllerTest.java`:

```java
package com.example.platform.order;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void reportsReady() throws Exception {
        mockMvc.perform(get("/orders/status"))
                .andExpect(status().isOk())
                .andExpect(content().json(
                        "{\"service\":\"order-service\",\"status\":\"ready\"}"));
    }
}
```

Test kiểm tra HTTP response trong Spring MVC test context, không cần bind cổng 8080. JSON response:

```json
{
  "service": "order-service",
  "status": "ready"
}
```

`content().json` so sánh cấu trúc JSON, không phụ thuộc thứ tự key. Đây là source Java/Spring cần dependency Maven; không thể compile toàn project bằng `javac` trần mà thiếu Spring/JUnit classpath.

## 8. Cài artifact vào local repository bằng mvn install

Từ thư mục root:

```bash
./mvnw --version
./mvnw clean verify
./mvnw clean install
```

Trên Windows:

```powershell
.\mvnw.cmd --version
.\mvnw.cmd clean verify
.\mvnw.cmd clean install
```

`clean install` chạy các phase trước install: validate, compile, test, package, verify và các goal đã bind, rồi ghi artifact/POM vào local repository.

Với GAV `com.example.platform:order-service:1.4.0-SNAPSHOT`, đường dẫn thường có:

```text
~/.m2/repository/com/example/platform/order-service/1.4.0-SNAPSHOT/
```

Vì Spring Boot Maven Plugin repackages main JAR, artifact được install mặc định là **executable JAR**. Nó chạy bằng `java -jar` nhưng không nên dùng làm dependency thông thường vì application classes nằm dưới `BOOT-INF/classes`. Phần 12 giải thích cách giữ plain JAR.

### 8.1. Kiểm tra local artifact

Unix/macOS:

```bash
ls -la ~/.m2/repository/com/example/platform/order-service/1.4.0-SNAPSHOT/
```

PowerShell:

```powershell
Get-ChildItem "$env:USERPROFILE\.m2\repository\com\example\platform\order-service\1.4.0-SNAPSHOT"
```

Các file thường có:

```text
order-service-1.4.0-SNAPSHOT.jar
order-service-1.4.0-SNAPSHOT.pom
```

Snapshot local không nhất thiết có timestamped filename như remote snapshot. Maven quản lý metadata local phù hợp với resolver của máy đó.

### 8.2. Dùng artifact từ project khác

Consumer khai báo:

```xml
<dependency>
    <groupId>com.example.platform</groupId>
    <artifactId>order-service</artifactId>
    <version>1.4.0-SNAPSHOT</version>
</dependency>
```

Trên cùng máy, Maven có thể resolve sau khi install. Nhưng nếu consumer import class từ `OrderApplication`/`OrderController` của executable Boot JAR, có thể không tìm thấy vì layout executable không phù hợp làm dependency. Với code dùng chung, publish plain library module hoặc attach plain JAR riêng.

## 9. Publish remote bằng mvn deploy

### 9.1. Cấu hình user settings

Đảm bảo `~/.m2/settings.xml` có `server.id` trùng POM:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Cấp biến môi trường từ secret store/CI. Nếu release và snapshot dùng token khác nhau, thay bằng biến riêng.

### 9.2. Chạy deploy

POM hiện có version `1.4.0-SNAPSHOT`, vì vậy Maven chọn `snapshotRepository`:

```bash
./mvnw -B -ntp clean deploy
```

- `-B` bật batch mode cho CI.
- `-ntp` tắt transfer progress để log gọn.
- `clean` xóa build output cũ.
- `deploy` chạy lifecycle tới deploy, bao gồm compile/test/package/verify/install trước upload.

Khi version là `1.4.0` (không có hậu tố `-SNAPSHOT`), Maven chọn `<repository>`. Đổi version theo release process đã phê duyệt; không đổi thành release chỉ để thử deploy.

### 9.3. Xác minh publish

Sau `BUILD SUCCESS`, kiểm tra:

- Repository manager có đúng GAV.
- JAR/POM/attached artifacts có mặt.
- Version nằm đúng release/snapshot repository.
- Consumer project resolve được artifact từ remote.
- Artifact đã publish chính là file vừa test.

Lỗi ở `deploy:deploy` có thể xảy ra sau khi compile/test/package thành công; phân biệt lỗi build với lỗi upload/auth/repository policy.

## 10. Kiểm tra remote từ consumer project

Trong POM consumer, `<repositories>` dùng để tải dependency:

```xml
<repositories>
    <repository>
        <id>company-public</id>
        <url>https://repo.example.com/repository/maven-public/</url>
        <releases>
            <enabled>true</enabled>
        </releases>
        <snapshots>
            <enabled>true</enabled>
        </snapshots>
    </repository>
</repositories>
```

`company-public` là endpoint minh họa; nhiều tổ chức cấu hình mirror trong settings để request đi qua repository manager.

Thêm dependency:

```xml
<dependency>
    <groupId>com.example.platform</groupId>
    <artifactId>order-service</artifactId>
    <version>1.4.0-SNAPSHOT</version>
</dependency>
```

Consumer private repository có thể cần credentials đọc trong settings; server ID phải khớp ID repository/mirror mà Maven sử dụng.

### 10.1. Kiểm tra snapshot mới

Nếu local cache có snapshot cũ, `-U` yêu cầu Maven kiểm tra cập nhật:

```bash
./mvnw -U dependency:tree
./mvnw -U test
```

`-U` không thay đổi release artifact bất biến và không giải quyết quyền truy cập. Với release version đã publish sai, phát hành version mới theo policy thay vì ghi đè.

**Không dùng local install để chứng minh remote deploy.** Consumer trên cùng máy có thể lấy artifact từ `~/.m2/repository`. Để kiểm chứng remote thật, dùng local repository sạch/khác hoặc runner khác, và bảo đảm consumer route tới đúng remote endpoint.

Có thể dùng local repository tạm trong consumer:

```bash
./mvnw -Dmaven.repo.local=target/consumer-m2 -U test
```

Chạy lệnh trong consumer project có `<repositories>` phù hợp và settings credentials đọc nếu repository private. Không cần xóa toàn bộ `~/.m2/repository` của developer.

## 11. Snapshot và release trong quy trình phát hành

### 11.1. Snapshot

`1.4.1-SNAPSHOT` là version phát triển có thể publish lại. Repository manager thường tạo timestamp/build number và cập nhật `maven-metadata.xml`; resolver dùng metadata để chọn snapshot phù hợp.

Snapshot hữu ích khi nhiều module đang tích hợp, CI build từ nhánh phát triển hoặc consumer cần thử API trước release. Không nên dùng snapshot lâu dài cho production nếu cần tính bất biến; cùng tọa độ snapshot có thể trỏ nội dung khác ở các thời điểm khác nhau.

### 11.2. Release

`1.4.0` là release version theo quy ước Maven. Repository manager thường chặn overwrite cùng release coordinate. Release nên được build từ source revision đã chốt, qua test/verification và có release record. Nếu phát hiện lỗi sau publish, phát hành version mới như `1.4.1`.

Hậu tố `-SNAPSHOT` là quy ước version Maven, không đồng nghĩa Git branch `develop`. Nên ghi source commit/build metadata riêng nếu cần truy vết.

## 12. Spring Boot executable JAR khi install/deploy

Spring Boot Maven Plugin goal `repackage` biến JAR/WAR bình thường thành executable archive. Với `spring-boot-starter-parent`, repackage execution đã được cấu hình; khai báo plugin là đủ.

Executable JAR đặt application classes dưới `BOOT-INF/classes` và dependencies dưới `BOOT-INF/lib`. Nó dùng cho `java -jar`, nhưng **không phù hợp làm dependency JAR thông thường** vì consumer classloader không tìm class trong layout nested đó.

### 12.1. Giữ plain JAR và attach executable JAR bằng classifier

Nếu cần publish cả library JAR và executable JAR, cấu hình classifier cho repackage:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đặt fragment trong `<build><plugins>`. Khi dùng starter parent, sửa execution id `repackage` đã có; tránh thêm execution trùng.

Kết quả điển hình:

```text
order-service-1.4.0-SNAPSHOT.jar       -> plain JAR
order-service-1.4.0-SNAPSHOT-exec.jar  -> executable Spring Boot JAR
```

Maven install/deploy có thể publish artifact chính và executable artifact được attach với classifier. Consumer dependency mặc định lấy plain JAR; executable artifact có classifier `exec`.

### 12.2. Tách library và application module

Thiết kế multi-module thường rõ ràng hơn:

```text
platform-parent (packaging=pom)
      |
      +-- domain-library (plain JAR)
      |
      +-- order-service (executable Spring Boot JAR)
              |
              +-- dependency -> domain-library
```

Library publish JAR thuần để module khác sử dụng; application module repackage thành executable JAR để chạy. Không dùng executable Boot JAR làm shared library chỉ vì cả hai có extension `.jar`.

## 13. Maven multi-module deploy từ aggregator

Root POM:

```xml
<packaging>pom</packaging>
<modules>
    <module>domain-library</module>
    <module>order-service</module>
</modules>
```

Parent có thể chứa `distributionManagement` để các module con kế thừa nếu quan hệ POM được thiết lập phù hợp. Chạy từ root:

```bash
./mvnw -B -ntp clean deploy
```

Maven reactor thu thập modules, sắp thứ tự theo quan hệ build/dependency và chạy lifecycle cho từng project.

Chỉ deploy module ứng dụng cùng các module cần thiết:

```bash
./mvnw -pl :order-service -am deploy
```

- `-pl :order-service` chọn module theo artifactId.
- `-am` thêm những project trong reactor mà module đó cần.
- `deploy` publish các project được chọn.

Lệnh có thể publish cả dependency modules được thêm bởi `-am`; xác định scope trước khi dùng trong CI. Nếu chỉ muốn build/test, chọn `verify` thay vì deploy.

**Reactor deploy không phải transaction nguyên tử.** Module đầu có thể đã upload khi module cuối thất bại. Với release nhiều module, dùng staging/close/promote của repository manager nếu có hoặc quy trình xử lý partial publication; không giả định server tự rollback toàn bộ.

## 14. Artifact không được build bởi Maven project: install-file và deploy-file

Dùng các goal này cho JAR bên ngoài không có Maven build chuẩn, không phải cách publish bình thường cho source project có POM.

### 14.1. Cài JAR bên ngoài vào local repository

```bash
./mvnw install:install-file \
  -Dfile=vendor-sdk.jar \
  -DgroupId=com.vendor \
  -DartifactId=vendor-sdk \
  -Dversion=2.3.0 \
  -Dpackaging=jar \
  -DgeneratePom=true
```

`install:install-file` chỉ cài local. `-DgeneratePom=true` tạo POM tối thiểu, không thể tự suy luận transitive dependencies đầy đủ. Nếu vendor cung cấp POM, dùng `-DpomFile` để giữ metadata chính xác.

### 14.2. Deploy một file lên remote

```bash
./mvnw deploy:deploy-file \
  -Dfile=vendor-sdk.jar \
  -DgroupId=com.vendor \
  -DartifactId=vendor-sdk \
  -Dversion=2.3.0 \
  -Dpackaging=jar \
  -DrepositoryId=company-releases \
  -Durl=https://repo.example.com/repository/maven-releases/
```

`deploy:deploy-file` upload một artifact đơn lẻ; `repositoryId` phải khớp server ID trong settings. Goal này không chạy quy trình build/test của project nguồn. Cú pháp/parameters phụ thuộc version Maven Deploy Plugin; xem plugin docs và pin version phù hợp trước khi automation.

## 15. CI/CD: publish an toàn và có thể lặp lại

Một job phát hành nên:

1. Checkout source revision và xác định release/snapshot version.
2. Cài JDK/Maven Wrapper đúng version.
3. Cấp user settings/credentials từ secret manager.
4. Chạy verify/tests và quality gates.
5. Build/package artifact.
6. Deploy vào đúng snapshot/release repository.
7. Kiểm tra GAV, POM và attached artifacts trong repository manager.
8. Dùng consumer smoke test hoặc dependency resolution từ remote.
9. Ghi build number, source commit, checksum và release record.
10. Rotate/revoke token khi không còn cần.

Lệnh CI mẫu:

```bash
./mvnw -B -ntp clean deploy
```

**Không dùng `-DskipTests` mặc định cho release.** Nó bỏ chạy test (nhưng có thể vẫn compile test sources tùy plugin); `-Dmaven.test.skip=true` bỏ cả compile tests. Chỉ skip nếu có quality gate khác đã xác minh và artifact publish chính là artifact đã qua gate.

Tách quyền:

- Developer thường có quyền đọc dependency repository.
- CI release job có quyền deploy release.
- CI integration job có quyền deploy snapshot.
- Repository manager áp policy immutable release, snapshot retention và cleanup.

Một release version nên được build một lần, verify và publish đúng artifact đã kiểm tra. Rebuild ở stage khác có thể tạo bytes khác do timestamp/dependency/environment; truyền artifact qua pipeline hoặc so checksum/digest.

## 16. Security, TLS và repository manager

- Dùng HTTPS và certificate chain được tin cậy.
- Không tắt TLS validation để chữa lỗi certificate; cài CA đúng cho Maven/JDK/runner.
- Credentials nằm trong user settings/secret injection, không nằm trong POM.
- Không đưa password vào command line vì shell history/process list/log có thể lưu lại.
- Dùng token giới hạn quyền publish đúng repository/path.
- Tách quyền release và snapshot.
- Không chia sẻ debug log chứa internal URLs, usernames, local paths hoặc credentials.
- Theo dõi checksum/signature/audit log theo policy.
- Với artifact quan trọng, bổ sung SBOM, signature, provenance/attestation; Maven deploy đơn thuần không chứng minh artifact an toàn hoặc được build từ source đã phê duyệt.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `401 Unauthorized` | Sai token hoặc server ID không khớp | So repository ID với settings server ID |
| `403 Forbidden` | Account không có quyền deploy | Cấp đúng quyền trên repository |
| `Repository does not allow updating assets` | Release version đã tồn tại | Tăng version, không ghi đè release |
| Snapshot vào release repo | Sai `snapshotRepository` hoặc version | Kiểm tra hậu tố `-SNAPSHOT` và effective POM |
| Release vào snapshot repo | Version/POM config sai | Kiểm tra `distributionManagement` |
| `mvn install` xong nhưng máy khác không resolve | Artifact chỉ có local | Chạy `mvn deploy` |
| Consumer dùng snapshot cũ | Local metadata/cache cũ | Dùng `-U`, kiểm tra remote metadata |
| Không resolve sau deploy | Sai GAV/classifier hoặc consumer dùng repo khác | Kiểm tra repository browse, POM và mirror |
| JAR deploy được nhưng consumer không thấy class | Đó là executable Boot JAR | Publish plain JAR hoặc library module |
| Thiếu transitive dependencies | Deploy-file không có POM đúng | Dùng `-DpomFile` hoặc Maven lifecycle |
| `Failed to transfer file` | Network/proxy/TLS/DNS/server | Kiểm tra endpoint, CA, proxy, status |
| Checksum mismatch | Upload/storage/proxy lỗi | Kiểm tra artifact và repository metadata |
| Multi-module deploy dừng giữa chừng | Một module lỗi sau khi module khác đã upload | Dùng staging/release orchestration |
| CI không có credential | Secret/settings chưa được cấp hoặc sai user home | Kiểm tra settings path và env injection |
| Deploy sai URL | Parent/profile/override khác dự kiến | Xem `help:effective-pom` |
| Remote bytes khác local | Build lại từ workspace khác hoặc snapshot đổi | So checksum, revision và deployment metadata |

### 17.1. Lệnh chẩn đoán

```bash
./mvnw --version
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw -B -ntp clean deploy
./mvnw -U verify
```

`help:effective-pom` cho biết `distributionManagement` hiệu lực sau inheritance/profile. `dependency:tree` kiểm tra dependency graph, không chứng minh remote deploy. Khi dùng `-s /path/to/settings.xml`, kiểm tra path và file permissions; không chia sẻ debug/settings output nếu có thông tin nhạy cảm.

## 18. Bài thực hành end-to-end

**A — Build/test:** trong project mục 7 chạy `./mvnw clean verify`. Kỳ vọng `BUILD SUCCESS` và `OrderControllerTest` pass.

**B — Install local:** chạy `./mvnw clean install`; kiểm tra thư mục `~/.m2/repository/com/example/platform/order-service/1.4.0-SNAPSHOT/`.

**C — Deploy snapshot:** thay URL ví dụ bằng snapshot repository thật, cấp credentials qua settings/secret manager, giữ version `1.4.0-SNAPSHOT`, rồi chạy `./mvnw -B -ntp clean deploy`. Kiểm tra repository manager nhận artifact và metadata.

**D — Consumer test:** tạo project khác, khai báo `<repositories>` cho read endpoint và dependency GAV; dùng local repository sạch hoặc runner khác để chứng minh artifact tải từ remote.

**E — Release:** khi được phê duyệt, chuyển version sang `1.4.0` theo release process, build/test/verify từ source revision đã chốt và deploy lên release repository. Không redeploy cùng release version nếu có lỗi; phát hành version mới.

**F — Multi-module:** chạy từ aggregator, kiểm tra reactor summary và xác định module nào publish plain JAR, module nào publish executable JAR/classifier.

### Checklist trước khi bật deploy trong CI

- [ ] Maven Wrapper và Java version được pin.
- [ ] POM GAV đúng với release policy.
- [ ] `distributionManagement` có đúng release/snapshot URL và ID.
- [ ] `settings.xml` có `server.id` trùng ID trong POM.
- [ ] Credential lấy từ secret store, không commit/in log.
- [ ] Repository dùng HTTPS và certificate hợp lệ.
- [ ] Release repository immutable; snapshot repository có retention/cleanup.
- [ ] `mvn verify` và quality gates pass trước deploy.
- [ ] Hiểu `mvn install` là local-only.
- [ ] `mvn deploy` chạy trong môi trường có quyền publish.
- [ ] POM/JAR/classifier/attached artifacts đã được kiểm tra.
- [ ] Consumer project resolve đúng GAV từ remote.
- [ ] Executable Spring Boot JAR không bị dùng nhầm làm library dependency.
- [ ] Multi-module deploy order và partial failure được xử lý.
- [ ] Release record lưu checksum/source revision.
- [ ] Không skip tests mặc định khi release.

### Tài liệu chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — POM Reference: Distribution Management](https://maven.apache.org/pom.html#Distribution_Management)
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html)
- [Apache Maven — Deploying over HTTP(S), Credentials and Repository IDs](https://maven.apache.org/guides/mini/guide-deployment-transports.html)
- [Apache Maven — Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/)
- [Apache Maven — Maven Install Plugin](https://maven.apache.org/plugins/maven-install-plugin/)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
- [Spring Boot 3.5 — Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 — Build and Use an Executable JAR](https://docs.spring.io/spring-boot/3.5/how-to/build.html)

**Ghi nhớ:** `install` chỉ đưa artifact vào **local Maven repository**; `deploy` đưa artifact lên **remote repository**. `distributionManagement` xác định đích publish, còn `settings.xml` giữ credentials được tra theo đúng `server.id`. Với Spring Boot, kiểm tra loại JAR được publish: executable archive dành để chạy, plain JAR dành cho dependency; xác minh GAV, POM, classifier và remote resolution trước khi coi bản phát hành đã hoàn tất.
