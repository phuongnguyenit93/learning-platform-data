# Đưa DevTools vào môi trường phát triển bằng phạm vi phụ thuộc phù hợp

Khi phát triển Spring Boot, ta thường muốn thấy thay đổi mã nhanh, không phải tắt ứng dụng, khởi động lại toàn bộ và kiểm tra thủ công sau mỗi lần biên dịch. **Spring Boot DevTools** (`org.springframework.boot:spring-boot-devtools`) hỗ trợ vòng lặp phát triển đó bằng cơ chế automatic restart, LiveReload và một số giá trị cấu hình thuận tiện cho máy lập trình viên. Tuy nhiên, những cơ chế này thuộc **development**, không nên đi kèm bản phân phối production.

Câu hỏi trung tâm của bài: **Làm thế nào đưa DevTools vào classpath khi phát triển, nhưng tránh mang nó sang ứng dụng/library tiêu thụ hay executable artifact triển khai?** Câu trả lời phụ thuộc vào hai cơ chế khác nhau của Maven và Gradle:

- **Maven:** khai báo DevTools là **optional dependency**; có thể thêm `<scope>runtime</scope>` để nói rõ mã nguồn ứng dụng không cần DevTools API khi compile. Spring Boot Maven Plugin loại DevTools khỏi executable archive trong cấu hình mặc định.
- **Gradle:** đặt DevTools vào cấu hình **`developmentOnly`** do Spring Boot Gradle Plugin cung cấp. Nó sẵn có cho workflow phát triển và mặc định không nằm trong `bootJar`/`bootWar`.
- **Luôn kiểm tra artifact đã đóng gói**, vì thay đổi plugin, scope, publication hoặc custom task có thể làm khác hành vi mặc định.

Ví dụ dùng **Java 17 + Spring Boot 3.3.13** và hai lựa chọn build riêng biệt: Maven 3.9.x hoặc Gradle phù hợp với Spring Boot 3.3. Phiên bản cố định nhằm giúp người học tái hiện ví dụ; dự án thực tế phải chọn phiên bản còn phù hợp với vòng đời hỗ trợ và chính sách cập nhật của mình.

## 1. DevTools dùng để làm gì?

`spring-boot-devtools` là module bổ trợ khi phát triển, không phải Spring Boot starter nghiệp vụ. Một số tính năng chính:

| Tính năng | Ý nghĩa | Giới hạn cần hiểu |
| --- | --- | --- |
| Automatic restart | Khi nội dung classpath (thường là tệp `.class`) thay đổi, ứng dụng khởi tạo lại application context nhanh hơn | **Không phải** hot swap mọi bytecode ngay khi người dùng gõ source; cần cập nhật classpath bằng compile/build |
| Hai classloader | Giữ thư viện tương đối ổn định ở *base classloader* và tạo lại *restart classloader* cho mã đang phát triển | Có thể gây vấn đề classloading với module/thư viện đặc biệt |
| Property defaults cho development | Điều chỉnh một số cache/template/resource settings giúp sửa giao diện thuận tiện | Không coi các giá trị này là mặc định phù hợp production |
| LiveReload | Thông báo để trình duyệt/client có hỗ trợ LiveReload tự refresh | Không thay thế cơ chế build frontend, và có thể cần extension/client hỗ trợ |
| Báo cáo thay đổi condition evaluation | Cho biết auto-configuration thay đổi sau một lần restart | Phục vụ chẩn đoán, không phải kiểm thử đầy đủ |

Với ứng dụng đã đóng gói hoàn chỉnh và chạy bằng `java -jar`, Spring Boot mặc định coi đó là môi trường production và tự vô hiệu hóa DevTools theo cơ chế phát hiện launcher; bên cạnh đó, **các plugin đóng gói chuẩn còn loại DevTools ra khỏi executable archive theo mặc định**. Hai lớp bảo vệ này có mục đích khác nhau:

1. **Classpath/artifact:** DevTools có được đưa vào bản phát hành hay không?
2. **Runtime activation:** Nếu JAR của DevTools có mặt, những tính năng phát triển có được bật khi ứng dụng chạy hay không?

Không dùng lớp thứ hai làm lý do để bỏ qua kiểm tra lớp thứ nhất. Artifact production tốt nhất **không chứa DevTools**.

## 2. “Phạm vi phụ thuộc” khác với “bật tính năng”

Khi khai báo dependency, build tool phải biết nó cần thiết ở bước nào:

```text
                      JAVA PROJECT
                           |
            +--------------+--------------+
            |                             |
       Build/Run IDE                 Artifact phát hành
            |                             |
   DevTools trên classpath?         JAR/WAR có DevTools?
            |                             |
       CÓ, khi phát triển                KHÔNG
            |                             |
   Restart/LiveReload                Môi trường production
```

**Maven `optional` và Gradle `developmentOnly` không phải hai từ đồng nghĩa về implementation.**

- `optional` trong Maven điều khiển **tính bắc cầu** của dependency khi module của bạn được project khác sử dụng. Một dependency optional trực tiếp vẫn có thể nằm trong classpath của **chính project khai báo**.
- `developmentOnly` trong Gradle là một **configuration** được Spring Boot Gradle Plugin hỗ trợ cho dependency chỉ cần lúc phát triển. Nó không được chọn làm phần của executable archive trong cấu hình đóng gói mặc định.
- Scope `runtime` của Maven và configuration `runtimeOnly` của Gradle mô tả dependency khi chạy, nhưng **tự thân chúng không đảm bảo dependency vắng mặt khỏi artifact production**.
- Scope `test` của Maven hay `testImplementation` của Gradle giới hạn dependency về test; nếu chỉ khai báo DevTools ở đó thì ứng dụng chạy qua `spring-boot:run`/`bootRun` trong main development workflow không nhất thiết có DevTools.
- `provided`/`compileOnly` không thích hợp làm công cụ mặc định cho DevTools: chúng gợi ý dependency phục vụ compile hoặc do môi trường cung cấp, trái với mục tiêu DevTools cần có khi chạy ứng dụng **trong development**.

### Bảng chọn nhanh

| Mục tiêu | Maven | Gradle |
| --- | --- | --- |
| Dùng DevTools khi chạy ứng dụng từ IDE/build tool | Dependency trực tiếp `spring-boot-devtools` với `optional=true` (có thể dùng `scope=runtime`) | `developmentOnly 'org.springframework.boot:spring-boot-devtools'` |
| Tránh tự truyền DevTools cho module downstream | `<optional>true</optional>` | Dùng `developmentOnly` thay vì `api`/`implementation` |
| Tránh đóng DevTools trong executable archive | Spring Boot Maven Plugin: mặc định `excludeDevtools=true` | Spring Boot `bootJar`/`bootWar`: mặc định loại `developmentOnly` |
| Chỉ dùng thư viện cho test | `<scope>test</scope>`, không phải lựa chọn chính của bài này | `testImplementation`, không phải lựa chọn chính của bài này |
| Kiểm tra kết quả thực tế | `mvn dependency:tree` + `jar tf target/...jar` | `./gradlew dependencies` + `jar tf build/libs/...jar` |

## 3. Maven: khai báo DevTools theo cách dự án tự dùng nhưng module khác không kế thừa

### 3.1. Đoạn cấu hình cốt lõi

Trong `pom.xml` của ứng dụng Spring Boot có quản lý dependency version (ví dụ kế thừa `spring-boot-starter-parent`), thêm **dependency** này vào `<dependencies>`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <scope>runtime</scope>
    <optional>true</optional>
</dependency>
```

**Ý nghĩa từng trường:**

- `groupId`/`artifactId`: chọn đúng Spring Boot DevTools module.
- Bỏ `<version>`: starter parent hoặc BOM `spring-boot-dependencies` cung cấp managed version tương ứng với Spring Boot release. Nếu project chưa có dependency management, phải chọn version thích hợp rõ ràng.
- `<scope>runtime</scope>`: compiler không cần import DevTools API khi biên dịch source chính; dependency vẫn dùng được trong runtime classpath của application khi chạy phát triển. **Spring Boot 3.3 documentation cũng minh họa DevTools chỉ với `optional=true` và scope Maven mặc định là `compile`; cả hai cách đều có thể hoạt động.** Dùng `runtime` để diễn đạt rõ mục tiêu của bài.
- `<optional>true</optional>`: dự án downstream phụ thuộc vào project hiện tại sẽ **không tự động** nhận DevTools theo đường phụ thuộc bắc cầu. Nó không xóa dependency khỏi classpath của chính project này.
- Spring Boot Maven Plugin với goal `repackage` mặc định loại `spring-boot-devtools` khỏi executable JAR/WAR qua `excludeDevtools=true`. Đây là hành vi **plugin đóng gói**, không phải đặc tính chung của thẻ `optional`.

### 3.2. Ví dụ Maven `pom.xml` độc lập

Một POM tối thiểu cho ứng dụng web Java 17:

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

    <groupId>dev.example</groupId>
    <artifactId>devtools-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-devtools</artifactId>
            <scope>runtime</scope>
            <optional>true</optional>
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

`spring-boot-starter-parent` vừa cung cấp dependency management vừa có cấu hình Maven Plugin, nên khi plugin `spring-boot-maven-plugin` được khai báo như trên, goal `repackage` hoạt động trong vòng đời `package`. Nếu dùng parent công ty và **chỉ import BOM** thay vì kế thừa starter parent, cần khai báo version và execution của Spring Boot Maven Plugin theo build thực tế; BOM import đơn thuần **không** kích hoạt goal `repackage`.

Đầu ra `target/devtools-demo-1.0.0.jar` sẽ là executable JAR nếu build và `repackage` thành công. DevTools vẫn có thể xuất hiện trong dependency graph **phục vụ ứng dụng phát triển**, nhưng không được đóng vào executable JAR theo cấu hình chuẩn của Boot 3.3.

### 3.3. Code Java và kiểm thử dùng chung

Dùng một project source tree cho Maven **hoặc** Gradle, với cấu trúc:

```text
devtools-demo/
├── pom.xml                 # Chọn Maven
├── src/
│   ├── main/java/dev/example/devtools/
│   │   └── DevtoolsDemoApplication.java
│   └── test/java/dev/example/devtools/
│       └── DevtoolsDemoApplicationTests.java
└── (hoặc settings.gradle + build.gradle nếu chọn Gradle)
```

Tệp `src/main/java/dev/example/devtools/DevtoolsDemoApplication.java`:

```java
package dev.example.devtools;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DevtoolsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DevtoolsDemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello v1";
    }
}
```

Tệp `src/test/java/dev/example/devtools/DevtoolsDemoApplicationTests.java`:

```java
package dev.example.devtools;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DevtoolsDemoApplicationTests {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void helloResponds() throws Exception {
        mockMvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello v1"));
    }
}
```

Ví dụ này chỉ dùng Spring MVC và JUnit, **không import class DevTools trong source**. Điều đó hợp với Maven `runtime` hoặc Gradle `developmentOnly`: DevTools thuộc công cụ phát triển; mã nghiệp vụ không có lý do phụ thuộc API của nó.

### 3.4. Thực thi trên Maven

Cần JDK 17 và Maven phù hợp. Nếu dự án có Maven Wrapper, thay `mvn` bằng `./mvnw` (Windows dùng `mvnw.cmd`).

```bash
mvn -version
mvn clean verify
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-devtools
mvn spring-boot:run
```

- `mvn clean verify` kiểm tra compiler/test và tạo JAR ở `package`; Maven không tự bật ứng dụng lâu dài chỉ vì build thành công.
- `mvn dependency:tree` liệt kê DevTools đã được resolved trong dependency graph của chính project. Với cấu hình trên, entry trực tiếp có scope `runtime` và optional flag.
- `mvn spring-boot:run` khởi động ứng dụng phục vụ phát triển từ classpath; DevTools có thể hoạt động khi dependency đã được resolve. Không thay `spring-boot:run` bằng `java -jar` khi bạn đang muốn thử restart.
- Nếu IDE cho phép chạy `main` trực tiếp với module runtime classpath, DevTools cũng có thể được kích hoạt theo cơ chế development của Spring Boot.

Trong terminal thứ hai khi ứng dụng đã sẵn sàng:

```bash
curl -s http://localhost:8080/hello
```

Body HTTP chính xác:

```text
Hello v1
```

## 4. Gradle: đặt DevTools đúng `developmentOnly`

### 4.1. Đoạn cấu hình khuyến nghị

Với **Spring Boot Gradle Plugin**, thông thường chỉ cần:

```groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
```

`developmentOnly` là configuration được plugin Boot cung cấp. Khi ứng dụng chạy từ source qua `bootRun`, DevTools có thể tham gia development runtime classpath. Khi `bootJar`/`bootWar` tạo executable archive theo mặc định, các dependency trong `developmentOnly` **được loại khỏi artifact**.

Không khai báo DevTools bằng `implementation` rồi giả định nó sẽ tự biến mất chỉ vì có chữ “devtools” trong artifact name. Điều khiển classpath với `developmentOnly` khiến ý định của dự án thể hiện trong cấu hình và phù hợp quy tắc packaging của Spring Boot plugin.

### 4.2. `build.gradle` đầy đủ (Groovy DSL)

Tệp `settings.gradle`:

```groovy
rootProject.name = 'devtools-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Trong cấu hình trên, Spring Boot Gradle Plugin làm việc cùng `io.spring.dependency-management` để nhập BOM Spring Boot tương ứng, nên `spring-boot-devtools` không cần version riêng. Nếu dự án thay bằng Gradle native `platform(...)`, cần để **configuration chứa DevTools** nhận version constraints thích hợp; chỉ thêm `platform` vào `implementation` mà không kiểm tra cấu hình khác có thể dẫn đến dependency version chưa được quản lý.

Dùng cùng hai source file Java của mục 3.3. Build bằng Gradle Wrapper nếu dự án đã cung cấp:

```bash
./gradlew clean build
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-devtools --configuration runtimeClasspath
./gradlew bootRun
```

Windows dùng `gradlew.bat`. Task `bootRun` dùng main runtime classpath để chạy ứng dụng từ build output. `runtimeClasspath` trong dự án Spring Boot plugin chứa dependency development phù hợp để phát triển, trong khi `bootJar` dùng cấu hình đóng gói được điều chỉnh để loại dependency `developmentOnly`.

`dependencyInsight` giúp tìm nguyên nhân một dependency được chọn và version resolved thực tế. Với project đã tùy biến source sets/configurations, phải kiểm tra dependency graph của đúng task/configuration, không chỉ nhìn một tên cấu hình và suy ra toàn bộ.

### 4.3. Vì sao không dùng `runtimeOnly` trong Gradle?

`runtimeOnly` có nghĩa **cần dependency khi chạy ứng dụng**, nhưng không nói “chỉ lúc phát triển” với các task đóng gói. Spring Boot plugin cung cấp `developmentOnly` chính để diễn đạt khác biệt đó. Với `runtimeOnly 'org.springframework.boot:spring-boot-devtools'`, tùy cấu hình task và phiên bản plugin, thư viện có thể nằm trong runtime classpath mà `bootJar` sử dụng; bạn không nên coi đó là phạm vi phát triển an toàn mặc định.

Cũng không dùng `testImplementation` nếu muốn DevTools trong quá trình chạy ứng dụng bằng `bootRun`: configuration test phục vụ biên dịch/chạy test, không có nghĩa tự đưa dependency sang main development runtime.

**Hãy dùng `developmentOnly` khi chọn Gradle** và xác minh bằng kiểm tra artifact.

## 5. Thực hành DevTools restart và quan sát đúng tín hiệu

DevTools không theo dõi trực tiếp từng ký tự trong `.java` như một trình biên dịch thông minh bên trong JVM. Nó quan sát sự thay đổi **classpath directory entries** và kích hoạt restart khi output biên dịch thay đổi.

Quy trình:

1. Chạy `mvn spring-boot:run` hoặc `./gradlew bootRun`, hoặc chạy application `main` từ IDE với DevTools trên runtime classpath.
2. Từ terminal khác gọi `curl -s http://localhost:8080/hello` và nhận `Hello v1`.
3. Sửa **duy nhất** chuỗi trả về trong `DevtoolsDemoApplication.hello()` thành `"Hello v2"`.
4. Để IDE compile project hoặc chạy `mvn compile` với Maven / task compile tương ứng của Gradle để cập nhật `.class`.
5. Quan sát ứng dụng restart khi classpath thay đổi và gọi lại endpoint; khi application đã restart thành công, body là `Hello v2`.
6. Nếu muốn chạy lại `mvn clean verify`/`./gradlew clean build` sau khi đổi mã, hãy **đồng thời cập nhật expected string trong test thành `Hello v2`** hoặc hoàn nguyên source về `Hello v1`. Nếu không, test đúng ra sẽ thất bại.

Luồng quan sát:

```text
Mã nguồn /hello -> "Hello v1"
        |
        v
Build/IDE compile -> classpath chứa .class v1
        |
        v
DevTools chạy trong development JVM
        |
        +--- sửa source thành "Hello v2"
        |
        +--- compiler cập nhật .class v2
        |
        v
DevTools phát hiện classpath change -> restart context
        |
        v
HTTP /hello -> "Hello v2"
```

**Restart khác reload tĩnh:** sửa HTML/CSS/js static assets có thể chỉ làm browser reload mà không cần restart Java application context. DevTools có danh sách đường dẫn tài nguyên loại trừ khỏi full restart theo mặc định; LiveReload là tiện ích riêng và phụ thuộc client/browser tương ứng.

**Không phải thay đổi source nào cũng restart ngay:** nếu IDE không tự compile khi lưu file, classpath vẫn giữ `.class` cũ. Vấn đề thường là quá trình compile chưa diễn ra hoặc output không được DevTools theo dõi, không phải DevTools “không đọc `.java` đúng cách”.

### Trường hợp phải tạm tắt restart để chẩn đoán

Nếu thấy lỗi classloader trong module nội bộ hoặc thư viện đặc biệt, thử thuộc tính:

```properties
spring.devtools.restart.enabled=false
```

Đây là cấu hình **khi phát triển** để tắt chức năng restart. Khi chỉ tắt restart bằng property file, một số thành phần DevTools vẫn có thể được khởi tạo; muốn loại hoàn toàn khỏi project/runtime classpath thì loại dependency ở build. Với một project production, cách đúng là tạo artifact không chứa DevTools thay vì dùng một property che giấu dependency.

Không bật DevTools restart cưỡng bức bên trong môi trường production. DevTools cung cấp khả năng giám sát và sửa đổi liên quan đến developer workflow; ép kích hoạt trong môi trường public có thể tạo rủi ro vận hành và bảo mật.

## 6. Tách ba khái niệm: dev dependency, Spring profile và build profile

Một lỗi khái niệm phổ biến là nghĩ đặt Spring profile `dev` sẽ **tự tải** module `spring-boot-devtools`, hoặc `-Pdev` trong Maven sẽ tự chọn scope DevTools.

Trên thực tế, có ba điều khiển độc lập:

| Bộ điều khiển | Ai quyết định? | Ví dụ | Công dụng |
| --- | --- | --- | --- |
| Dependency/configuration | Maven hoặc Gradle | `<optional>true</optional>`; `developmentOnly` | Có JAR DevTools trên classpath phát triển và/hoặc trong artifact |
| Spring runtime profile | Spring Boot | `--spring.profiles.active=dev`, `application-dev.yml` | Chọn properties/beans khi ứng dụng khởi động |
| Maven build profile | Maven | `mvn -Pci clean verify` | Chọn phần cấu hình POM/goal khi build |

Nếu `spring-boot-devtools` **không có** trong classpath, chỉ đặt `--spring.profiles.active=dev` sẽ **không** tự bổ sung module đó. Nếu dependency đã được khai báo đúng, bạn không cần tạo thêm Spring profile có tên `dev` để DevTools hoạt động trong môi trường phát triển.

Trong Spring Boot, `spring.profiles.active` có ý nghĩa riêng đối với cấu hình ứng dụng; không dùng nó để thay thế `developmentOnly` hay Maven `optional`. Ngược lại, `<scope>runtime</scope>` không tự chỉ định `spring.profiles.active`. Chúng thuộc những tầng khác nhau.

## 7. Kiểm tra DevTools thực sự vắng khỏi executable JAR

**Đừng coi `mvn clean verify` hoặc `./gradlew clean build` thành công là đã kiểm tra đủ phạm vi dependency.** Build có thể thành công ngay cả khi người viết thay đổi phân loại dependency khiến một JAR chỉ dành cho development bị đóng vào artifact phát hành. Hãy quan sát **chính tệp JAR/WAR dự kiến deploy**.

### Maven: kiểm tra JAR được `repackage`

Sau khi chạy:

```bash
mvn clean verify
```

Xem nội dung:

```bash
jar tf target/devtools-demo-1.0.0.jar
```

Executable JAR Spring Boot thường có:

```text
BOOT-INF/classes/dev/example/devtools/DevtoolsDemoApplication.class
BOOT-INF/lib/spring-boot-3.3.13.jar
BOOT-INF/lib/spring-boot-autoconfigure-3.3.13.jar
...
```

Các entry khác, version phụ thuộc và thứ tự liệt kê không cần giống ví dụ. **Không được có** entry bắt đầu bằng `BOOT-INF/lib/spring-boot-devtools-` trong bản phát hành mặc định. Nếu cấu hình `repackage` bị vô hiệu hóa, hoặc bạn xem nhầm JAR gốc/thư viện thuần, layout sẽ khác; cần xác định đúng artifact mà môi trường triển khai thực sự dùng.

Kiểm tra tự động trên Linux/macOS:

```bash
if jar tf target/devtools-demo-1.0.0.jar | grep -q 'BOOT-INF/lib/spring-boot-devtools-'; then
  echo "FAIL: DevTools found in executable JAR"
  exit 1
else
  echo "PASS: DevTools absent from executable JAR"
fi
```

Với POM chuẩn ở mục 3, output của phép kiểm tra **nếu thành công**:

```text
PASS: DevTools absent from executable JAR
```

PowerShell:

```powershell
$archive = "target/devtools-demo-1.0.0.jar"
$hits = jar tf $archive | Select-String 'BOOT-INF/lib/spring-boot-devtools-'
if ($hits) {
    throw "FAIL: DevTools found in executable JAR"
}
Write-Output "PASS: DevTools absent from executable JAR"
```

### Gradle: kiểm tra `bootJar`

```bash
./gradlew clean build
jar tf build/libs/devtools-demo-1.0.0.jar
```

Trong executable JAR, cũng không được có `BOOT-INF/lib/spring-boot-devtools-*.jar`. Với Gradle nếu project còn tạo `-plain.jar`, **đừng nhầm `-plain.jar` với executable Boot JAR**. Chọn đúng `bootJar` output theo tên/version thực tế của `build.gradle`.

Có thể dùng câu lệnh shell tương tự, đổi đường dẫn:

```bash
if jar tf build/libs/devtools-demo-1.0.0.jar | grep -q 'BOOT-INF/lib/spring-boot-devtools-'; then
  echo "FAIL: DevTools found in executable JAR"
  exit 1
else
  echo "PASS: DevTools absent from executable JAR"
fi
```

**Kết luận phải dựa trên hai phép quan sát:** DevTools có mặt khi chạy local (dependency được resolved và vòng lặp restart hoạt động), và **không có** trong executable artifact (lệnh `jar tf` đã đối chiếu đúng file). Kiểm tra một bên chưa chứng minh được bên còn lại.

## 8. Vì sao Maven `optional` không đồng nghĩa “chỉ ở development”?

Cơ chế Maven optional áp dụng chủ yếu khi **project khác sử dụng artifact của bạn**. Ví dụ:

```text
Module app-a:
  depends on spring-boot-devtools (optional = true)
                     |
                     v
Module app-b:
  depends on app-a
  -> KHÔNG tự nhận spring-boot-devtools theo đường app-a
```

Đối với **chính app-a**, dependency optional trực tiếp vẫn được Maven phân giải và có thể có trên runtime classpath. Do đó phát biểu “đặt `optional=true` thì Maven không tải DevTools khi chạy project này” là sai. Thẻ optional quản lý transitivity; Spring Boot Maven Plugin mới là thành phần áp dụng loại trừ DevTools khi `repackage` executable archive.

Cần tách các lựa chọn Maven sau:

| Cấu hình Maven | Compile classpath | Runtime classpath của project trực tiếp | Truyền bắc cầu sang consumer |
| --- | --- | --- | --- |
| `<scope>compile</scope>` (default), không optional | Có | Có | Có theo mediation |
| `<scope>runtime</scope>`, không optional | Không cần khi compile nguồn chính | Có | Có, theo rules runtime |
| `<scope>runtime</scope><optional>true</optional>` | Không cần khi compile nguồn chính | Có | **Không tự truyền** |
| `<scope>test</scope>` | Không nằm trong compile classpath chính | Dành cho test | Không |
| `<scope>provided</scope>` | Có | Không được coi là runtime dependency mặc định của ứng dụng tự chạy | Không theo cách dependency compile thông thường |

Bảng trên mô tả mô hình scope ở mức chủ đề, chưa bao gồm mọi nuance của plugin, test classpath, dependency mediation và môi trường container. Với DevTools, **`runtime + optional` hoặc optional mặc định theo tài liệu Boot** đều là cách dùng hợp lý trong Maven; verify bằng `dependency:tree` và artifact thực tế.

### Vì sao `test` không thay `runtime`?

DevTools hỗ trợ developer khi **chạy application**, không phải một thư viện assertion dành riêng cho JUnit. `test` đưa dependency vào pha test (và các classpath test tương ứng), nhưng `spring-boot:run` thường dùng main runtime classpath. Nếu đặt DevTools vào `test` chỉ vì “không chạy trên production”, bạn có thể mất tính năng khi chạy ứng dụng local.

### Vì sao không dùng Maven `provided`?

`provided` chủ yếu cho API/thư viện do JDK hoặc container cung cấp và có mặt khi compile/test. Với executable Spring Boot JAR, việc dùng `provided` làm “mẹo” loại dependency có thể phản tác dụng vì Spring Boot Maven Plugin có quy tắc riêng đối với provided dependencies khi `repackage`. Đừng dùng `provided` để thay thế `optional` và loại trừ DevTools.

## 9. Gradle: hiểu `developmentOnly` trong cấu hình lớn hơn

Gradle tổ chức dependency theo configurations, và classpath cuối cùng còn chịu ảnh hưởng của source sets/tasks và quan hệ `extendsFrom`. Spring Boot Gradle Plugin tạo `developmentOnly` khi áp dụng cùng Java plugin và thiết lập các task chạy/đóng gói theo convention của nó.

Trong build chuẩn:

```text
implementation ------> main application compile/runtime
runtimeOnly  --------> main runtime; có thể dùng khi đóng gói
developmentOnly -----> local run workflow; excluded from bootJar/bootWar
testImplementation --> test compilation/runtime
testRuntimeOnly -----> test runtime
```

Một số lỗi phổ biến:

- Đặt DevTools vào `api` của Java Library plugin: nó xuất hiện trong API/dependency metadata cho consumers, trái với ý định dev-only.
- Đặt DevTools vào `implementation`: application runtime classpath có thư viện và tùy cách đóng gói có thể đưa nó vào archive.
- Đặt DevTools vào `testImplementation`: bạn có thể thấy nó trong test nhưng `bootRun` không nhận theo main runtime classpath.
- Áp dụng cấu hình copy/fat-jar thủ công thay `bootJar`: quy tắc loại trừ `developmentOnly` mặc định của Boot plugin **không tự bảo đảm** cho custom packaging task đó.
- Tùy biến `tasks.named('bootJar') { classpath ... }` mà vô tình cộng cả `developmentOnly`: chính custom configuration đã thay đổi phạm vi phát hành.

**Tránh cấu hình phá chuẩn:** mục tiêu của bài là giữ `developmentOnly` cho local và giữ DevTools ngoài artifact, nên không cần chỉnh `bootJar.classpath` hoặc đặt `excludeDevtools=false`. Nếu một yêu cầu rất đặc biệt thực sự cần remote DevTools, phải được đánh giá riêng; đây không phải cấu hình cho một ứng dụng production thông thường.

## 10. Spring Boot packaging bảo vệ DevTools như thế nào?

Đối với Boot 3.3:

- **Maven Spring Boot Plugin (`repackage`):** `excludeDevtools` mặc định `true`. Với executable JAR/WAR, plugin loại artifact DevTools khi đóng gói. Nếu bạn không dùng `repackage`/plugin chuẩn, không được suy từ dòng cấu hình Maven optional rằng DevTools chắc chắn bị loại khỏi mọi artifact khác.
- **Gradle Spring Boot Plugin (`bootJar`/`bootWar`):** các dependency trong configuration `developmentOnly` được loại mặc định. Nếu tạo custom `jar`, `shadowJar`, `distribution` hoặc Docker build tự copy dependency folder, phải kiểm chứng phạm vi của các công cụ ấy riêng.
- **Runtime:** DevTools có kiểm tra môi trường chạy và thường tự vô hiệu hóa khi ứng dụng đóng gói đầy đủ được chạy như một production application. Đây là cơ chế *runtime*, không có nghĩa DevTools có mặt trong archive là an toàn.

### Multi-module và library khác executable application

Nếu repository có `common` (library) và `web-app` (application), DevTools thường nên là dependency development trực tiếp của **module chạy web-app**. Đừng cài nó vào shared library nơi mọi module sử dụng. Nếu library có DevTools để chạy test/dev riêng, dùng đúng optional/developmentOnly tại library đó và kiểm tra metadata publication.

Trong Maven, `optional=true` quan trọng khi module A được module B tiêu thụ. Trong Gradle, `developmentOnly` quan trọng vì Gradle configurations và publication có ngữ nghĩa khác `api`/`implementation`. Điều này tránh dependency gây side effect cho những module không chủ định dùng DevTools.

Với Spring Boot application module dùng `java -jar`, CI nên phân biệt các artifact: `bootJar` executable, `jar` plain library (nếu được tạo), `bootWar` (nếu có). Kiểm tra loại artifact thật đem đi triển khai, không chỉ kiểm tra một tệp cùng project name.

## 11. Cần làm gì nếu DevTools vẫn xuất hiện trong artifact?

Kiểm tra theo thứ tự sau:

1. **Xác định chính xác đầu ra:** file `target/...jar` hay `build/libs/...jar` nào sẽ được upload/deploy? Kiểm tra tên, `-plain` classifier và manifest.
2. **Maven:** có `spring-boot-maven-plugin` với `repackage` không? Có override `excludeDevtools` thành `false` không? `mvn help:effective-pom` cho thấy effective plugin configuration.
3. **Gradle:** DevTools có nằm trong `developmentOnly` đúng module không? Có thêm cùng artifact ở `implementation`/`runtimeOnly`/custom configuration không? Có custom bootJar/Shadow/Copy task trộn tất cả JAR không?
4. **Chạy lại build sạch** để loại output cũ, sau đó kiểm tra `jar tf`.
5. **Dependency graph:** dùng `mvn dependency:tree` hoặc `./gradlew dependencyInsight` để tìm đường kéo DevTools vào.
6. **CI:** thêm gate kiểm tra archive, báo lỗi khi thấy `BOOT-INF/lib/spring-boot-devtools-`; với WAR, kiểm tra `WEB-INF/lib/` và `WEB-INF/lib-provided/` theo layout thực tế.
7. **Nếu build plugin thực sự không hỗ trợ exclusion** cho artifact riêng, sửa cấu hình packaging/dependency ở đúng task hoặc chọn quy trình build được hỗ trợ; không chỉ tắt tính năng bằng Spring runtime property rồi bỏ qua artifact.

Trong trường hợp DevTools **không chạy khi phát triển**, hãy kiểm tra ngược lại:

- IDE/`bootRun`/`spring-boot:run` có dùng runtime classpath chứa DevTools hay không.
- Ứng dụng có thực sự chạy từ thư mục classpath (unpackaged) không; `java -jar` khác `bootRun`.
- Compiler/IDE có cập nhật `.class` hay mới chỉ lưu `.java`.
- Có đặt `spring.devtools.restart.enabled=false` hoặc đặt cấu hình restart exclusions quá rộng không.
- Multi-module có classloader đặc biệt hoặc JRebel/AspectJ toolchain không; một số công nghệ có tương tác không giống default restart.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `mvn spring-boot:run` không thấy DevTools | Thiếu dependency, khác module, runtime classpath sai hoặc dùng profile làm loại trừ | Kiểm tra POM, effective model, `dependency:tree` và plugin run configuration |
| `./gradlew bootRun` thiếu DevTools | Đặt vào `testImplementation`/`compileOnly` hoặc plugin/configuration không phù hợp | Đổi sang `developmentOnly` đúng module, kiểm tra runtimeClasspath |
| Lưu Java mà app không restart | IDE chưa biên dịch cập nhật `.class` | Compile/build project; xác nhận output classpath thực sự thay đổi |
| Thấy hai bản class/mất bean sau restart | Hai classloader/devtools restart liên quan multi-module | Tạm tắt restart để chẩn đoán, cân nhắc `META-INF/spring-devtools.properties` theo tài liệu |
| Maven `optional=true` nhưng dependency vẫn hiện ở `dependency:tree` | Optional ngăn truyền bắc cầu, không loại khỏi project trực tiếp | Đây là hành vi đúng; kiểm tra executable archive riêng |
| Maven dùng `test` rồi không có restart khi chạy app | Test scope không thuộc main runtime | Dùng optional dependency, có thể kèm runtime scope |
| Gradle dùng `runtimeOnly` và Boot JAR chứa DevTools | Scope runtime không đồng nghĩa development-only | Dùng `developmentOnly` và kiểm tra `bootJar` |
| `java -jar` không restart như khi `bootRun` | Packaged launch được coi là production và DevTools thường bị loại | Chạy từ source để phát triển; không ép bật DevTools trên production |
| Boot JAR vẫn chứa DevTools | Plugin exclusion bị thay đổi hoặc custom packaging | Xem build task và `jar tf`, loại DevTools từ artifact phát hành |
| Có LiveReload nhưng browser không refresh | Browser/client chưa hỗ trợ LiveReload hoặc chỉ thay Java class mà không refresh UI | Kiểm tra client extension/luồng refresh, phân biệt restart với reload |
| Startup sản phẩm bị lộ cấu hình development | Tự nhúng DevTools hoặc debug flags vào artifact/cấu hình môi trường | Loại dependency và debug options khỏi pipeline phát hành |
| Version DevTools lệch Spring Boot | Pin thủ công phiên bản module không khớp BOM/plugin | Quản lý bằng Boot BOM/release, xác minh resolved versions |

**Đừng “sửa” bằng cách xóa dependency sau mỗi lần build.** Cấu hình đúng scope rồi để build tool tự tạo classpath phát triển và artifact phát hành là giải pháp có thể lặp lại.

## 13. Tình huống phân tích

**Tình huống A.** Developer thêm:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <scope>test</scope>
</dependency>
```

và hỏi vì sao `mvn spring-boot:run` không có automatic restart. **Đáp án:** DevTools đã được đưa vào test scope, không được bảo đảm có mặt trên main runtime classpath. Đổi thành dependency `optional=true` (có thể `scope=runtime`) theo mục 3.

**Tình huống B.** Ứng dụng Maven được project khác import như dependency, dù đã có DevTools, project mới không nhận DevTools. **Đáp án:** Đây là mục đích của `optional=true`. Nó chỉ ngăn đường bắc cầu, không làm DevTools biến mất khỏi ứng dụng khai báo trực tiếp.

**Tình huống C.** Gradle khai báo:

```groovy
dependencies {
    runtimeOnly 'org.springframework.boot:spring-boot-devtools'
}
```

rồi tin rằng vì có chữ `runtimeOnly` nên sản phẩm không mang DevTools. **Đáp án:** Sai về ngữ nghĩa; `runtimeOnly` không phải dev-only. Chuyển sang `developmentOnly` và kiểm tra archive.

**Tình huống D.** Team chạy `java -jar target/devtools-demo-1.0.0.jar` nhưng không thấy restart khi sửa source. **Đáp án:** Đó là executable artifact đã đóng gói và DevTools bị loại mặc định; ứng dụng chạy như production. Để phát triển, dùng `mvn spring-boot:run`, `./gradlew bootRun` hoặc IDE với classpath development.

**Tình huống E.** Trong `pom.xml` đã có DevTools optional, nhưng một custom script upload toàn bộ `target/dependency/*.jar` lên server. Có thể kết luận môi trường deploy không chứa DevTools không? **Đáp án:** Không. Thẻ optional không kiểm soát custom copy. Phải xem command copy và artifact thực sự; quy tắc `repackage` chỉ áp dụng cho output của plugin đó.

**Tình huống F.** Sau đổi Java source, endpoint vẫn trả `Hello v1` cho đến khi chọn Build Project trong IDE. **Đáp án:** DevTools theo dõi compiled classpath; trước đó file `.class` chưa đổi. Build/compile tạo `.class` mới rồi DevTools mới có tín hiệu restart.

**Tình huống G.** Ứng dụng Spring Boot dùng profile `dev` nhưng không có JAR DevTools trong dependency graph. Thêm `spring.profiles.active=dev` có tự cài module không? **Đáp án:** Không. Spring profile quản lý runtime config/beans, không thêm Maven/Gradle dependency.

**Tình huống H.** Lệnh `mvn clean verify` thành công, artifact có `BOOT-INF/lib/spring-boot-devtools-...jar`. Có nên cho qua gate vì test pass? **Đáp án:** Không. Kiểm tra vì sao exclusion mặc định không hiệu lực; sửa build/package và tái tạo artifact, rồi chạy lại kiểm tra tập phụ thuộc trong JAR.

## 14. Checklist khi đưa vào dự án thật

- **Đúng module:** khai báo DevTools ở module Spring Boot ứng dụng đang chạy khi phát triển, không vô tình ở shared library.
- **Đúng cách khai báo:** Maven `optional=true` (cân nhắc `scope=runtime`); Gradle `developmentOnly`.
- **Đúng version:** dùng Spring Boot BOM hoặc cơ chế dependency management tương ứng, tránh DevTools khác release.
- **Đúng classpath:** chạy app từ IDE/`spring-boot:run`/`bootRun` và xác minh DevTools hoạt động sau khi compile thay đổi.
- **Đúng tách biệt môi trường:** Spring profile `dev` chỉ điều khiển config; nó không thay thế dependency scope.
- **Đúng artifact:** executable JAR/WAR production không có DevTools; kiểm tra bằng `jar tf` hoặc archive inspection trong CI.
- **Đúng plugin:** nếu custom packaging, tự kiểm chứng behavior vì mặc định Boot plugin không bảo đảm cho mọi custom task.
- **Đúng phát hành:** publish và deploy chính artifact đã kiểm tra, không build lại bằng một script riêng vô tình kéo dependency development.
- **Đúng bảo mật:** không bật remote DevTools/restart ép buộc trên production; quản lý secrets và debug endpoints theo môi trường.
- **Đúng khả năng tái tạo:** có Wrapper/build configuration version hóa và build sạch đạt; thay đổi dependency scope có test/inspection evidence.

**Điểm cần nhớ:** `spring-boot-devtools` nên **có mặt khi phát triển và vắng mặt khỏi bản phát hành**. Maven dùng **`optional`** để ngăn phụ thuộc bắc cầu, thường kết hợp runtime scope để biểu đạt đúng mục đích; Spring Boot Maven Plugin bảo đảm exclusion khi repackage. Gradle dùng **`developmentOnly`** để phân biệt development classpath và executable packaging. Hãy xem dependency graph cùng với **nội dung archive thực tế** trước khi kết luận.

### Tài liệu chính thức

- Spring Boot 3.3 — Developer Tools: https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html
- Spring Boot 3.3 — Maven Plugin: Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin: Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Running Your Application with Gradle: https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html
- Apache Maven — Optional Dependencies and Exclusions: https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html
- Apache Maven — Dependency Mechanism and Scopes: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html