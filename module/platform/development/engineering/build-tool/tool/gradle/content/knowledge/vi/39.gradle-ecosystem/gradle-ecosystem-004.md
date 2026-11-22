# Quản lý phiên bản dependency trong dự án Spring Boot với Gradle

**Nhóm kiến thức:** Hệ sinh thái Gradle.  
**Phạm vi:** Spring Boot Gradle Plugin, Spring Boot BOM, Gradle native platform, Spring Dependency Management Plugin, version catalogs, dependency constraints, multi-project build, resolution diagnostics, nâng cấp và CI.

## 1. Vì sao một ứng dụng Spring Boot không nên tự ghi version của mọi thư viện?

Một ứng dụng Spring Boot thường có hàng chục dependency **trực tiếp** và hàng trăm dependency **bắc cầu (transitive)**:

```text
Ứng dụng
  |
  +-- spring-boot-starter-web
  |     +-- spring-web
  |     +-- spring-webmvc
  |     +-- embedded servlet container
  |     +-- Jackson và nhiều thành phần khác
  |
  +-- spring-boot-starter-validation
  |     +-- Bean Validation API
  |     +-- Hibernate Validator
  |
  +-- spring-boot-starter-test
        +-- JUnit Jupiter
        +-- AssertJ
        +-- Spring Test
        +-- Mockito và test utilities
```

Tên/thành phần phụ thuộc cụ thể thay đổi theo phiên bản Spring Boot; sơ đồ chỉ là khái niệm. Nếu developer ghi version riêng từng library, các lỗi dễ xuất hiện:

- Spring Framework modules bị lệch phiên bản: `spring-core`, `spring-web` và `spring-context` không còn thuộc một tập được kiểm thử cùng nhau.
- Jackson `jackson-databind`/`jackson-core` khác release train.
- `NoSuchMethodError` hoặc `NoClassDefFoundError` xuất hiện lúc runtime mặc dù compile thành công.
- Logging API và implementation khác nhau; backend logging không load hoặc có nhiều providers.
- JUnit Jupiter, JUnit Platform Launcher và Spring Test không tương thích khi nâng không đồng bộ.
- Một module ghim version A, module khác ghim B, cuối cùng Gradle chọn C theo resolution rules.
- Cố sửa một CVE bằng cách override một artifact nhưng quên family/BOM tương ứng.
- Upgrade Spring Boot plugin mà quên upgrade dependency BOM; packaging plugin và runtime dependencies bị lệch.
- Dùng `latest.release` hoặc version `+`: CI của cùng commit có thể resolve ra kết quả khác theo ngày.
- Version catalog làm code đẹp hơn nhưng không tự áp đặt constraint cho transitive dependency graph.

**Giải pháp mặc định:** để Spring Boot cung cấp **tập phiên bản được quản lý cùng nhau** qua `org.springframework.boot:spring-boot-dependencies` (BOM), rồi dùng một trong hai cơ chế Gradle được Spring Boot hỗ trợ:

1. **Gradle native BOM support**: `platform(...)`.
2. **Spring Dependency Management Plugin**: `io.spring.dependency-management`.

Hai cơ chế phục vụ mục đích tương tự nhưng **không cùng cách xử lý override/constraint**. Không trộn cả hai theo thói quen mà không hiểu hệ quả.

### Mục tiêu bài học

Sau bài học, bạn có thể:

1. Phân biệt **Gradle plugin version**, **Spring Boot BOM version** và **dependency resolved version**.
2. Chọn giữa `platform` và `io.spring.dependency-management` theo nhu cầu.
3. Viết một ứng dụng Java 17 + Spring Boot 3.5.x đầy đủ bằng Gradle Kotlin DSL.
4. Khai báo starters không có version khi chúng nằm trong Boot BOM.
5. Đọc `dependencies` và `dependencyInsight` để biết phiên bản thực sự được chọn.
6. Dùng `libs.versions.toml` để giữ plugin/BOM ở một nguồn sự thật.
7. Quản lý BOM trong multi-module `:app`/`:library` mà không làm ô nhiễm public API.
8. Hiểu `constraints`, `strictly`, `platform` và `enforcedPlatform` trước khi override.
9. Biết cách xử lý dependency bên ngoài Boot BOM, Spring Cloud BOM và CVE patch.
10. Nâng Spring Boot có kiểm soát, chốt lockfiles/verification metadata và kiểm CI.

## 2. Bốn loại “version” dễ bị nhầm

| Loại phiên bản | Khai báo ở đâu? | Nó điều khiển gì? |
| --- | --- | --- |
| **Spring Boot Gradle Plugin** | `plugins { id("org.springframework.boot") version "..." }` | `bootRun`, `bootJar`, packaging, plugin integration |
| **Spring Boot dependencies BOM** | `platform("org.springframework.boot:spring-boot-dependencies:...")` hoặc Spring DM import | Tập dependency version constraints/recommendations |
| **Version trên một declaration** | `implementation("group:name:version")` hoặc catalog | Version được **request** cho artifact cụ thể |
| **Version Gradle thực sự resolve** | `runtimeClasspath`, `compileClasspath`, `testRuntimeClasspath` | Version được **chọn** sau BOM, constraints, conflicts và variants |

**Ví dụ một cấu hình dễ nhầm:**

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

Đoạn trên **chưa đầy đủ** nếu không có `io.spring.dependency-management` hoặc Gradle `platform(...)` ở dependency configuration phù hợp. Áp **Boot Gradle plugin một mình** không nên được hiểu là mọi versionless dependency tự động resolve. Tài liệu Spring Boot hướng dẫn áp plugin quản lý dependency **hoặc** dùng Gradle native BOM support.

Version của Boot plugin và BOM **thường nên đồng bộ** theo cùng Spring Boot release, nhưng Gradle không ngầm bảo đảm điều đó khi bạn tự nhập `platform("...:BOM_VERSION")`.

## 3. BOM là gì và nó hoạt động thế nào?

BOM (*Bill of Materials*) trong hệ sinh thái Maven là một POM có phần `dependencyManagement`, đưa ra một bộ quản lý phiên bản cho nhiều Maven coordinates. Spring Boot phát hành:

```text
org.springframework.boot:spring-boot-dependencies:<boot-version>
```

BOM không chỉ quản lý các artifacts `org.springframework.boot` mà còn chọn một danh sách rất nhiều thư viện bên thứ ba: Spring Framework, Jackson, logging, embedded servlet container, testing libraries, database drivers v.v.

Ví dụ conceptual:

```text
spring-boot-dependencies:3.5.16
   |
   +-- spring-boot-starter-web     -> phiên bản phù hợp Boot 3.5.16
   +-- spring-context             -> Spring Framework release tương ứng
   +-- jackson-databind           -> Jackson release được quản lý
   +-- slf4j-api                  -> Logging release tương ứng
   +-- junit-jupiter              -> JUnit release tương ứng
   +-- ...
```

**Không phải mọi thư viện trong Maven Central đều nằm trong BOM.** Nếu thêm một artifact chưa được Boot BOM quản lý, bạn vẫn phải có version từ catalog, dependency constraint hoặc một platform khác.

Để biết **một coordinate cụ thể** được Boot 3.5.16 quản lý hay không và version dự kiến, xem danh sách [Managed Dependency Coordinates của Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html). Đừng dự đoán version bằng trí nhớ, vì tập managed versions thay đổi theo từng maintenance release.

### 3.1. BOM không phải plugin

- **Plugin** là code mở rộng Gradle lifecycle/tasks.
- **BOM** tham gia **dependency resolution** và cung cấp constraints.
- **Starter** là dependency gộp một tập modules thường dùng, kèm Spring Boot auto-configuration theo các điều kiện runtime.
- **Version catalog** là bảng alias/coordinates để build script gọi gọn và nhất quán.
- **Dependency lockfile** ghi lại resolved dependencies đã khóa để build tái lập; không thay BOM.

Các thành phần có thể cùng tồn tại nhưng không thể dùng một thành phần thay hoàn toàn thành phần kia.

## 4. Chọn một chiến lược quản lý phiên bản

Tài liệu Spring Boot chính thức chấp nhận hai chiến lược:

| Tiêu chí | Gradle `platform(...)` | `io.spring.dependency-management` |
| --- | --- | --- |
| Cơ chế | Native Gradle BOM/platform constraints | Plugin mô phỏng Maven dependency management |
| Áp Boot BOM | Explicit `platform(...)` hoặc BootPlugin.BOM_COORDINATES | Tự nhập BOM tương ứng khi Boot plugin và DM plugin cùng áp |
| Khai báo versionless dependencies | Có, nếu configuration nhận BOM | Có với managed dependencies |
| Kiểm scopes | Qua dependency configurations và inheritance | Qua mô hình plugin dependency management |
| Override bằng BOM properties | Không; dùng Gradle mechanisms | Có; property-based customization |
| Hiệu năng | Thường nhanh hơn theo Spring Boot docs | Thêm plugin và lớp logic |
| Debug resolution | `dependencies`, `dependencyInsight` | Hai lệnh trên; plugin có thể thêm report riêng |
| Multi-module | Khai báo platform ở configurations cần | Apply DM/BOM cho các modules cần |
| Khuyến nghị cho project mới | Lựa chọn tốt nếu ưu tiên Gradle-native | Phù hợp khi cần tương thích cách override của Maven |

**Bài thực hành chính sử dụng Gradle native BOM support**: ít magic, dễ thấy configuration nào nhận constraints và phù hợp với version catalog. Phần 8 trình bày phương án `io.spring.dependency-management` độc lập.

**Không áp hai chiến lược chỉ vì thấy hai snippets trên Internet.** Nếu cả Spring DM và native platform cùng đặt constraints cho một configuration, việc giải thích version selection khó hơn. Nếu đang migrate, hãy đo dependency tree trước/sau, chọn một chiến lược và kiểm tests.

## 5. Phiên bản và môi trường cố định cho ví dụ

Để bài chạy có thể tái lập, ví dụ chọn:

- **Spring Boot Gradle Plugin**: `3.5.16`.
- **Spring Boot BOM**: `3.5.16`.
- **Java source/target**: Java 17 toolchain.
- **Gradle Wrapper**: Gradle `8.14.3`.
- **DSL**: Gradle Kotlin DSL (`*.gradle.kts`).
- **Test**: JUnit Jupiter thông qua `spring-boot-starter-test`.
- **Ứng dụng**: Spring MVC endpoint trả text cố định.

`3.5.16` là bản Spring Boot 3.5.x được Spring documentation công bố; Gradle plugin 3.5 hỗ trợ các Gradle 8.x được công bố từ 8.4 trở lên. Gradle8.14.3 và JDK17 là tổ hợp phù hợp cho demo. **Đây là phiên bản được ghim cho ví dụ, không phải lời khuyên luôn chạy bản cũ nhất hoặc tuyên bố “mới nhất” ở mọi thời điểm.**

Ở các dự án dùng Spring Boot 4.1.x, tài liệu/plugin/module names và Gradle minimum thay đổi. Không copy nguyên dependency/test annotations của ví dụ Boot3.5 sang Boot4 mà không đọc migration notes; xem phần 19.

## 6. Demo một module đầy đủ — Java 17 + Spring Boot 3.5.16 + native BOM

### 6.1. Cây thư mục

```text
boot-bom-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/bootdemo/
    │   ├── BootBomApplication.java
    │   └── GreetingController.java
    └── test/java/com/example/bootdemo/
        └── GreetingControllerTest.java
```

Có hai file Java production, một Java test và hai Gradle scripts. Không cần database, Redis hay Docker.

**Chuẩn bị:** có JDK17, một Gradle Wrapper thực hoặc Gradle cài sẵn để tạo Wrapper, Maven Central/approved mirror cho plugins/dependencies. Đừng tự viết `gradle-wrapper.jar`. Một cách tạo ban đầu trong project mới là:

```bash
gradle wrapper --gradle-version 8.14.3 --distribution-type bin
```

Sau đó dùng `./gradlew` hoặc `gradlew.bat` thay vì Gradle cài toàn hệ thống, commit Wrapper scripts/JAR/properties sau khi kiểm nguồn tin cậy.

### 6.2. `settings.gradle.kts`

```kotlin
rootProject.name = "boot-bom-lab"
```

Khi chạy Gradle, file này xác định project root name; artifact `bootJar` mặc định thường dùng project name/version tương ứng.

### 6.3. Toàn bộ `build.gradle.kts`

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

group = "com.example"
version = "0.1.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    // Spring Boot BOM quản lý versions trên main classpaths.
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )

    // Starters do BOM quản lý, không ghi version cho từng starter.
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")

    // Đặt BOM rõ cho test configurations để không phụ thuộc
    // một giả định ngầm về configuration inheritance.
    testImplementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
```

**Code trên không áp `io.spring.dependency-management`.** Spring Boot plugin làm các tasks `bootRun`/`bootJar` khi Java plugin cũng được apply; Gradle native platform xử lý versions.

**Giải thích chính xác từng phần:**

1. `plugins { java }` cung cấp `compileJava`, `test`, `jar`, `check` và Java source sets.
2. Spring Boot plugin `3.5.16` cung cấp các Boot tasks và packaging integration; nó không tự thay thế `platform(...)`.
3. `group`/`version` là project metadata và liên quan artifact naming, không phải Spring BOM version.
4. `repositories { mavenCentral() }` phục vụ dependency artifacts; plugin resolution thường dùng Gradle Plugin Portal qua `plugins` DSL (nếu settings không override).
5. `java.toolchain=17` giúp chọn Java compiler/JDK toolchain. JVM chạy Gradle Daemon có thể khác nếu Gradle/JVM compatibility cho phép.
6. `implementation(platform(...))` áp constraints trên main compile/runtime dependency graph.
7. `testImplementation(platform(...))` làm scope quản lý tests tường minh: `spring-boot-starter-test`/`junit-platform-launcher` nhận versions từ cùng BOM.
8. `implementation("...:spring-boot-starter-web")` không có version nhưng **hợp lệ vì BOM** có managed version.
9. `spring-boot-starter-validation` được BOM quản lý và cung cấp Bean Validation cho app, dù demo endpoint không bắt buộc dùng.
10. `testRuntimeOnly("org.junit.platform:junit-platform-launcher")` dùng Boot BOM để có managed version của launcher; đúng trường hợp JUnit Platform tests cần engine/launcher.
11. `useJUnitPlatform()` bảo Gradle Test task chạy JUnit5 Jupiter tests.
12. Không ghim version riêng của Spring Framework, Jackson, SLF4J hoặc JUnit khi chưa có lý do đã kiểm thử.
13. `platform(...)` dùng một tọa độ BOM **có version**, khác với các starters không version.

### 6.4. `BootBomApplication.java`

File `src/main/java/com/example/bootdemo/BootBomApplication.java`:

```java
package com.example.bootdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BootBomApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootBomApplication.class, args);
    }
}
```

`@SpringBootApplication` kích hoạt Spring Boot auto-configuration và component scanning từ package gốc `com.example.bootdemo`. Code sử dụng Java17-compatible syntax.

### 6.5. `GreetingController.java`

File `src/main/java/com/example/bootdemo/GreetingController.java`:

```java
package com.example.bootdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello, managed dependencies!";
    }
}
```

Spring MVC tự ánh xạ endpoint `GET /hello`. String trả về là HTTP response body, không có newline được thêm bởi method này.

### 6.6. `GreetingControllerTest.java`

File `src/test/java/com/example/bootdemo/GreetingControllerTest.java`:

```java
package com.example.bootdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
class GreetingControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void helloEndpointReturnsExpectedText() throws Exception {
        mockMvc.perform(get("/hello"))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, managed dependencies!"));
    }
}
```

**Tại sao test có giá trị?**

- `@WebMvcTest` là Boot3.5 test slice cho Spring MVC. Nó load web layer/test components cần thiết, không cần kết nối database.
- `MockMvc` gửi request đến controller trong test context, không mở public network port.
- `spring-boot-starter-test` cung cấp Spring Test/JUnit/MockMvc-related testing stack phù hợp Boot BOM.
- Test failure cho thấy source/runtime/test dependency graph không còn phù hợp, thay vì chỉ “build script parse được”.
- Đây là một **test method**; output Gradle console phụ thuộc logs, nhưng assertion kỳ vọng là HTTP status 200 và response body chính xác.

### 6.7. Chạy build và ứng dụng

Linux/macOS:

```bash
./gradlew --version
./gradlew clean test bootJar --no-daemon --console=plain
./gradlew bootRun --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat clean test bootJar --no-daemon --console=plain
.\gradlew.bat bootRun --console=plain
```

Sau khi `bootRun` khởi động, trong terminal thứ hai gọi:

```bash
curl -fsS http://localhost:8080/hello
```

Hoặc PowerShell:

```powershell
Invoke-RestMethod -Uri http://localhost:8080/hello
```

HTTP response body kỳ vọng **chính xác**:

```text
Hello, managed dependencies!
```

Lưu ý `curl` có thể không tự in newline cuối. Spring Boot startup logs, task outcomes, timestamps và port messages **không** được trình bày ở đây như output cố định. Nếu port 8080 bị chiếm, cấu hình `server.port` trong properties hoặc `--args` cho `bootRun` rồi dùng URL tương ứng.

Artifact `bootJar` mặc định dự kiến là:

```text
build/libs/boot-bom-lab-0.1.0.jar
```

Có thể khởi chạy:

```bash
java -jar build/libs/boot-bom-lab-0.1.0.jar
```

`bootJar` tạo executable archive có application classes và dependencies cần thiết. Gradle `jar` thông thường có thể tạo một `*-plain.jar` riêng tùy Boot plugin configuration; đừng nhầm `jar` với `bootJar` khi muốn chạy `java -jar`.

### 6.8. Cần chú ý điều gì về các version được chọn?

Plugin version `3.5.16` và BOM version `3.5.16` trùng nhau **do ta khai báo rõ**. Nếu ai đó chỉ đổi:

```kotlin
id("org.springframework.boot") version "3.5.16"
```

thành một version khác mà quên cập nhật:

```kotlin
platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
```

thì plugin packaging và runtime dependencies có thể không thuộc cùng Spring Boot release. Vì vậy phần version catalog sẽ giúp giảm số chỗ cần sửa.

## 7. Kiểm dependency tree: version được khai báo khác version được chọn

Gradle không chỉ “download tọa độ” mà phải resolve:

- Requested versions từ direct/transitive dependencies.
- Constraints đến từ BOM và các Gradle platforms.
- Các quy tắc conflict resolution và rich version constraints.
- Attributes/variants của configurations.
- Dependency substitution, excludes, capabilities nếu có.
- Lockfiles/verification policies ở build tương ứng.

Từ demo:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

PowerShell:

```powershell
.\gradlew.bat dependencies --configuration compileClasspath
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencies --configuration testRuntimeClasspath
```

**Đọc kết quả đúng cách:**

- `spring-boot-dependencies:3.5.16` là imported platform.
- Một phần output có `(c)` thể hiện **dependency constraints**, không phải một JAR được đóng gói giống artifact thường.
- Một mũi tên `A -> B` cho biết Gradle chọn resolved version B khác requested version A.
- Một version “selected by rule/constraint” có thể đến từ BOM/plugin/platform khác.
- `(*)` thường ám chỉ một subtree đã được in trước đó.
- Tree ở `compileClasspath` khác `runtimeClasspath` và `testRuntimeClasspath`; không dùng một tree để đại diện tất cả.

**Không tự gán một version Jackson/Netty/JUnit “chắc chắn” chỉ từ Boot version.** Boot BOM có list release-specific, và graph có thể select khác do constraint mạnh hơn. Xem actual dependency report và official managed coordinates.

### 7.1. Lệnh `dependencyInsight` — công cụ tìm một version chính xác

Ví dụ hỏi: “Tại sao `jackson-databind` là version đang thấy?”

```bash
./gradlew dependencyInsight \
  --dependency com.fasterxml.jackson.core:jackson-databind \
  --configuration runtimeClasspath
```

Cho Spring Framework:

```bash
./gradlew dependencyInsight \
  --dependency org.springframework:spring-core \
  --configuration runtimeClasspath
```

Cho test library:

```bash
./gradlew dependencyInsight \
  --dependency org.junit.jupiter:junit-jupiter \
  --configuration testRuntimeClasspath
```

Nếu Gradle chạy trên Windows PowerShell, dùng mỗi lệnh một dòng:

```powershell
.\gradlew.bat dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath
```

`dependencyInsight` chỉ giải thích dependency **trong configuration đã chọn**. Nó không chứng minh rằng artifact đó có mặt trong `bootJar` nếu packaging sử dụng một runtimeClasspath/configuration khác, và không phải một “universal project-wide version”.

### 7.2. Khi nào dùng `buildEnvironment`?

```bash
./gradlew buildEnvironment
```

Lệnh này chủ yếu chẩn đoán **buildscript classpath**, tức plugins/build logic dependencies, không thay thế `dependencies --configuration runtimeClasspath` của ứng dụng. Khi Spring Boot plugin resolve sai, `buildEnvironment` có thể hữu ích; khi Jackson runtime resolve sai, dùng `dependencyInsight` ở runtimeClasspath.

### 7.3. Kết quả được chọn có thể khác BOM đề xuất

Theo Gradle, `platform` thêm BOM constraints nhưng **không đảm bảo version luôn bị ép đúng con số BOM**. Nếu một transitive dependency có requested version mạnh hơn, Gradle có thể chọn version khác. Khi đó cần đánh giá tương thích chứ không kết luận native BOM “không hoạt động”.

`enforcedPlatform` có thể ép version theo platform nhưng cũng mang hệ quả mạnh cho consumer graph, thường không phải giải pháp mặc định cho Spring Boot application.

## 8. Phương án thay thế: Spring Dependency Management Plugin

Spring Boot Gradle Plugin có thể làm việc cùng `io.spring.dependency-management`. Khi **cả hai được apply**, Spring Boot plugin tự động nhập BOM tương ứng với chính version của Boot plugin.

Để thử phương án này, dùng **một file `build.gradle.kts` khác** thay cho file ở phần 6; không cộng thêm vào cùng dependencies block để tránh trộn hai cách.

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

// Boot plugin có dependency tới Spring Dependency Management Plugin;
// tài liệu Boot hướng dẫn apply theo cách này.
apply(plugin = "io.spring.dependency-management")

group = "com.example"
version = "0.1.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    // Không cần import platform thủ công ở phương án này.
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
```

**Các điểm khác với native BOM:**

- `apply(plugin = "io.spring.dependency-management")` sau Boot plugin (đúng cơ chế được Spring Boot docs mô tả) kích hoạt auto-import Boot BOM.
- Version của managed starters/test libraries được đồng bộ theo Spring Boot plugin version.
- Không cần hai `platform(...)` declarations.
- Plugin này có hỗ trợ **property-based override** của managed versions theo Spring Boot BOM properties.
- Cơ chế resolution/plugin overhead có thể khác; Spring Boot docs cho biết Gradle native BOM support có khả năng nhanh hơn.
- `dependencyManagement` là plugin-specific configuration, không phải cú pháp của Gradle native platforms.
- Nếu cố dùng một dependency không có trong Boot BOM, vẫn cần chọn version hoặc import BOM khác.

### 8.1. Override bằng BOM property chỉ áp với phương án plugin

Khi thật sự cần đổi một managed version và đã kiểm compatibility, Spring Dependency Management Plugin hỗ trợ property tương ứng của Boot BOM, ví dụ hình thức:

```kotlin
// Chỉ là cú pháp minh họa — KHÔNG dùng số phiên bản tùy ý
// để thay thư viện production nếu chưa kiểm thử.
extra["slf4j.version"] = "2.0.17"
```

Đây là một giá trị **minh họa syntax**, không phải khuyến nghị hạ/nâng SLF4J lên 2.0.17 với Boot 3.5.16. Phải xem [Boot dependency version properties](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/properties.html) và release/security notes.

**Không áp câu `extra["slf4j.version"] = ...` để điều khiển native Gradle `platform`.** Spring Boot docs nêu rõ BOM properties không còn là cơ chế Gradle-native override trong cách đó. Dùng Gradle constraints/rich versions/resolution rules có lý do rõ ràng, rồi kiểm `dependencyInsight`.

### 8.2. Hai cách quản lý dependency trong project root không tương đương với repository configuration

`repositories { mavenCentral() }` cho Gradle biết **lấy artifacts ở đâu**, không quyết định phiên bản nào được dùng.

`pluginManagement.repositories` trong settings phục vụ **plugin resolution**, còn `dependencyResolutionManagement.repositories` hoặc project repositories phục vụ dependency artifacts. Đây là các tầng riêng; Maven Central có artifact không chứng minh Gradle đã nhận BOM constraints.

## 9. Dùng SpringBootPlugin.BOM_COORDINATES để tránh hardcode version thứ hai

Với native Gradle BOM và Boot plugin đã apply, Spring Boot tài liệu cung cấp:

```kotlin
import org.springframework.boot.gradle.plugin.SpringBootPlugin

plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

dependencies {
    implementation(platform(SpringBootPlugin.BOM_COORDINATES))
    testImplementation(platform(SpringBootPlugin.BOM_COORDINATES))

    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

`SpringBootPlugin.BOM_COORDINATES` tự mang `group:name:version` khớp Spring Boot plugin version. Đây là một cách tránh duplication.

**Cảnh báo về snippet:** để trở thành file build hoàn chỉnh, cần giữ `repositories`, Java toolchain và Test configuration từ phần 6; đoạn này chỉ minh họa **cách tham chiếu BOM**. Dùng Boot plugin class ở một build áp plugin là hợp lý; một `java-library` module không áp Boot plugin có thể không có class này trên script classpath.

**Hai hướng centralization hợp lệ:**

- Dùng `SpringBootPlugin.BOM_COORDINATES` khi Boot plugin hiện diện và muốn implicit plugin/BOM alignment.
- Dùng **version catalog** chung `springBoot` cho cả plugin alias lẫn BOM alias, đặc biệt ở multi-project.

Chọn một, không cần cả hai chỉ vì có thể.

## 10. Version catalog: một nguồn phiên bản Spring Boot cho plugin và BOM

Gradle tự tìm `gradle/libs.versions.toml` và tạo type-safe accessors `libs` cho build. Version catalog giúp tránh literal version lặp lại, nhưng **không phải hệ thống áp version constraints**.

### 10.1. `gradle/libs.versions.toml` đầy đủ

```toml
[versions]
spring-boot = "3.5.16"

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }

[libraries]
spring-boot-bom = { module = "org.springframework.boot:spring-boot-dependencies", version.ref = "spring-boot" }
spring-boot-starter-web = { module = "org.springframework.boot:spring-boot-starter-web" }
spring-boot-starter-validation = { module = "org.springframework.boot:spring-boot-starter-validation" }
spring-boot-starter-test = { module = "org.springframework.boot:spring-boot-starter-test" }
junit-platform-launcher = { module = "org.junit.platform:junit-platform-launcher" }
```

**Tại sao chỉ BOM alias có version?**

- Boot plugin alias lấy `version.ref="spring-boot"`.
- BOM alias lấy **cùng** `version.ref`.
- Các Boot managed starters và JUnit Platform Launcher không cần version trong catalog, vì native `platform(...)` cung cấp managed versions khi dependencies được khai báo ở đúng configurations.
- Nếu một artifact **không** có trong Boot BOM, alias cần version riêng hoặc một platform/constraint thích hợp; không bỏ trống tùy tiện.

### 10.2. `build.gradle.kts` dùng catalog và native BOM

```kotlin
plugins {
    java
    alias(libs.plugins.spring.boot)
}

group = "com.example"
version = "0.1.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(platform(libs.spring.boot.bom))
    implementation(libs.spring.boot.starter.web)
    implementation(libs.spring.boot.starter.validation)

    testImplementation(platform(libs.spring.boot.bom))
    testImplementation(libs.spring.boot.starter.test)
    testRuntimeOnly(libs.junit.platform.launcher)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
```

Gradle hyphenated catalog aliases tạo nested accessors, nên:

- `spring-boot-bom` → `libs.spring.boot.bom`.
- `spring-boot-starter-web` → `libs.spring.boot.starter.web`.
- `spring-boot` plugin alias → `libs.plugins.spring.boot`.

**Tác dụng thật:** Khi nâng `spring-boot = "3.5.16"` lên một version được phê duyệt, plugin và BOM **cùng lấy một version**. Tuy nhiên cần kiểm Boot major upgrade, starter/test APIs, Gradle/JDK compatibility, lockfiles và dependency graph. Không đổi một property rồi tự kết luận đã nâng thành công.

### 10.3. Version catalog không quyết định resolved version

Gradle official docs nhấn mạnh: catalog là **kho tọa độ và requested versions**, không tạo cưỡng chế cho transitive dependencies. Ví dụ một alias yêu cầu `lib:1.0` nhưng một dependency transitive cần `lib:2.0` và không có strict constraints, Gradle có thể chọn 2.0.

**BOM/platform mới tạo constraints trong graph.** Do đó `libs.versions.toml` không thay thế `implementation(platform(libs.spring.boot.bom))`. Nếu bỏ platform trong ví dụ này, các alias versionless có thể báo lỗi resolution dù catalog vẫn hợp lệ.

### 10.4. Không dùng version catalog “pin” lại toàn bộ managed dependencies

Phản ví dụ:

```toml
[versions]
spring-boot = "3.5.16"
spring-core = "6.x.y"
jackson = "2.x.y"
junit = "5.x.y"
logging = "2.x.y"
```

Các chữ `x` ở đây chỉ là **ký hiệu phản ví dụ**, không phải values để copy. Ý là tự ghim hàng loạt artifacts làm BOM mất vai trò chọn một bộ version đồng bộ. Với dependency thuộc Spring Boot BOM, hãy để BOM quản lý; chỉ thêm catalog version khi có **ngoại lệ có kiểm chứng**.

## 11. Quản lý ở nhiều module: ứng dụng và Java library không giống nhau

Giả sử:

```text
boot-multi/
├── settings.gradle.kts
├── gradle/libs.versions.toml
├── app/build.gradle.kts
└── core/build.gradle.kts
```

- `:app` là Spring Boot application, có `bootJar` và runtime dependency graph.
- `:core` là Java library dùng chung, có thể không cần Boot plugin.
- Cả hai cần version management hợp lý nhưng **không nhất thiết phải áp Spring Boot plugin lên mọi module**.

### 11.1. Root `settings.gradle.kts`

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = "boot-multi"
include(":app", ":core")
```

Đây là root settings dùng centralized dependency repositories. Nếu project repositories cũng khai báo ở subprojects, Gradle có thể vẫn cho phép theo repository mode; khi muốn cấm mọi project repositories và giữ một nơi duy nhất, bổ sung `repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)` theo Gradle docs. Không cần bật tùy chọn đó chỉ để học version management.

### 11.2. Root catalog

Dùng `gradle/libs.versions.toml` từ phần 10, trùng một shared `spring-boot` version cho plugin/BOM.

### 11.3. `app/build.gradle.kts`

```kotlin
plugins {
    java
    alias(libs.plugins.spring.boot)
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(platform(libs.spring.boot.bom))
    implementation(project(":core"))
    implementation(libs.spring.boot.starter.web)

    testImplementation(platform(libs.spring.boot.bom))
    testImplementation(libs.spring.boot.starter.test)
    testRuntimeOnly(libs.junit.platform.launcher)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
```

`:app` chọn Spring Boot runtime ecosystem và tạo bootable application. App runtimeClasspath nhận `:core` dependencies qua project dependency.

### 11.4. `core/build.gradle.kts`

```kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    // Chỉ nhập BOM nếu core trực tiếp dùng Boot-managed coordinates.
    implementation(platform(libs.spring.boot.bom))
    implementation("org.springframework:spring-context")

    // Ví dụ tests riêng của core:
    testImplementation(platform(libs.spring.boot.bom))
    testImplementation(libs.spring.boot.starter.test)
    testRuntimeOnly(libs.junit.platform.launcher)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
```

**Giới hạn của snippets multi-module:** đây là minh họa dependency management. Cần thêm các Java source/test classes phù hợp để thực sự chạy `:core:test`/`:app:bootJar`; không coi hai snippets một mình là application hoàn chỉnh. Ví dụ standalone runnable ở phần 6.

### 11.5. Có nên dùng `api(platform(...))` trong library?

Cẩn thận:

- `implementation(platform(...))` làm BOM constraints tham gia **internal implementation** configurations của library.
- `api(platform(...))` có thể **xuất** platform constraints sang consumer's compile API surface khi Gradle Module Metadata được publish.
- Nếu `:core` là internal library chỉ dùng trong Boot ecosystem, việc để consumer nhận constraints có thể có chủ đích.
- Nếu `:core` là **public general-purpose Java library**, ép toàn bộ Boot BOM ra consumer có thể gây khó chịu/xung đột, nhất là khi consumer không dùng Boot.
- Application thường là nơi quyết định **full runtime dependency alignment**; library nên công bố API constraints thật sự cần, không tự impose toàn bộ ứng dụng BOM vô điều kiện.

**Một BOM không tự có hiệu lực cho tất cả modules/configurations** chỉ vì root project chứa nó. Cần áp đúng Gradle configuration scopes tại các projects được resolve.

## 12. Scope và Gradle configuration inheritance

Cùng một dependency có thể cần ở nhiều nơi:

| Configuration | Mục đích | Ví dụ |
| --- | --- | --- |
| `implementation` | Compile/runtime nội bộ application/library | Spring MVC starter |
| `api` | Public API library (`java-library`) | Type xuất hiện trong public method signatures |
| `compileOnly` | Chỉ compile, không đưa vào runtime | Compile-only annotations |
| `runtimeOnly` | Chỉ runtime | JDBC driver khi code không reference trực tiếp |
| `testImplementation` | Compile/test code | Spring Boot Starter Test |
| `testRuntimeOnly` | Runtime tests | JUnit Platform Launcher |
| `annotationProcessor` | Annotation processing classpath | Processor library |
| `testAnnotationProcessor` | Annotation processors cho tests | Khi tests có generated code |

Một imported platform chỉ tác động tới configurations **được khai báo** và những configurations có quan hệ extendsFrom thích hợp. Chính Spring Boot docs lưu ý có thể cần khai báo cùng platform trên nhiều configurations.

Vì thế bài demo cố ý có:

```kotlin
implementation(platform(libs.spring.boot.bom))
testImplementation(platform(libs.spring.boot.bom))
```

Khi thêm plugin tạo `integrationTestRuntimeClasspath` riêng, không suy mặc định nó nhận BOM từ `testImplementation`. Kiểm configuration inheritance và thêm platform đúng chỗ.

### 12.1. Annotation processors không nhất thiết dùng main BOM

Ví dụ nếu dùng Lombok hoặc MapStruct processor, `annotationProcessor` có dependency graph riêng. Spring Boot BOM có thể quản lý hoặc không quản lý một tọa độ cụ thể. Kiểm official managed coordinates và explicit annotationProcessor configuration.

Đừng khai báo một processor là `implementation` chỉ để “truyền BOM tới nó”; điều đó làm sai dependency scope. Dùng constraint/platform ở processor configuration nếu cần.

## 13. Platform, enforcedPlatform, constraints và force

Bốn công cụ có ý nghĩa khác nhau:

### 13.1. `platform` — lựa chọn mặc định

```kotlin
dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

BOM đóng góp dependency constraints và participates in Gradle resolution. Các version được BOM đề xuất/require có thể được nâng lên nếu graph có version mạnh hơn. Đây là lý do phải đọc `dependencyInsight` khi bất ngờ thấy version khác BOM.

### 13.2. `enforcedPlatform` — ràng buộc mạnh, dùng có cân nhắc

```kotlin
dependencies {
    implementation(
        enforcedPlatform(
            "org.springframework.boot:spring-boot-dependencies:3.5.16"
        )
    )
}
```

Đây là **snippet mô tả API**, không phải đề xuất thay native platform ở demo. `enforcedPlatform` áp constraints dạng cưỡng chế; có thể làm downstream consumers bị ép version và gây conflict với constraints khác. Gradle docs cảnh báo về việc export enforced platforms từ library.

**Đừng dùng enforcedPlatform chỉ để làm một báo cáo dependency tree trông “khớp BOM”** khi không có compatibility evidence.

### 13.3. Dependency constraints — ngoại lệ có lý do

Khi một thư viện transitive cần được nâng để vá CVE hoặc sửa bug, dùng Gradle constraints có `because(...)` và version rule rõ:

```kotlin
dependencies {
    constraints {
        implementation("com.fasterxml.jackson.core:jackson-databind") {
            version {
                strictly("2.21.4")
            }
            because("Example: demonstrate an explicitly reviewed constraint")
        }
    }
}
```

**Giới hạn snippet:** `2.21.4` là giá trị ví dụ từ managed coordinates của Boot3.5.16 tại thời điểm biên soạn; dùng cùng version với BOM chủ yếu để minh họa syntax, **không phải một bản vá CVE**. Khi security fix có version khác, phải kiểm Jackson family compatibility, test và release notes, rồi thay version đúng số đã phê duyệt.

`strictly` có thể tạo resolution failure thay vì âm thầm upgrade, đó là điểm mạnh khi bạn cần ràng buộc chặt. Nhưng pin một artifact trong family có thể gây lệch các artifacts liên quan; nên ưu tiên **nâng Spring Boot patch release** nếu release đó đã quản lý bản vá.

### 13.4. `resolutionStrategy.force` hoặc `eachDependency`

Gradle có các resolution strategies:

```kotlin
configurations.configureEach {
    resolutionStrategy.eachDependency {
        if (requested.group == "org.example.specific") {
            // useVersion(...) chỉ khi có version đã được phê duyệt.
        }
    }
}
```

Đoạn này là **ý tưởng API**, không phải một rule hoạt động vì group giả định không nằm trong demo. `force` và `eachDependency` có thể override normal constraints mà khó theo dõi; tránh biến chúng thành “cách vá mọi conflict”. Ưu tiên BOM/platform/constraints với lý do cụ thể, test và inspect `dependencyInsight`.

### 13.5. Loại bỏ dependency transitive?

`exclude` có thể ngăn một module được kéo qua một đường phụ thuộc, nhưng nếu module khác vẫn cần nó hoặc code/runtime yêu cầu nó, ứng dụng có thể lỗi. Hãy chứng minh:

- Artifact nào đang kéo dependency?
- Có đường transitive khác không?
- Exclusion có còn hợp lệ sau Boot upgrade không?
- Có đang thiếu class runtime vì exclusion?
- Có lựa chọn starter/module đúng hơn thay vì exclude không?

Không exclude Jackson/logging/servlet modules tùy tiện chỉ để giảm JAR size.

## 14. Dependency version được chọn vì conflict như thế nào?

Giả sử một versionless Spring Boot starter kéo `library-x:1.0` và một dependency mới cần `library-x:2.0`. Gradle có thể chọn 2.0 theo conflict resolution và version constraints, dù BOM gợi ý 1.0.

```text
app runtimeClasspath
  |
  +-- Boot BOM constraint: lib-x >= 1.0
  +-- starter-A -> lib-x:1.0
  +-- library-B -> lib-x:2.0
                 |
                 v
           resolved lib-x:2.0
```

**Sơ đồ chỉ minh họa generic Gradle resolution**, không mô tả một artifact/version cụ thể của Boot3.5.16.

Cách điều tra:

1. Xác định lỗi runtime/compile và **module bị nghi ngờ**.
2. Chạy `dependencies --configuration runtimeClasspath`.
3. Chạy `dependencyInsight --dependency lib-x --configuration runtimeClasspath`.
4. Đọc **requested vs selected**, conflict/reason/constraint.
5. Kiểm module có thuộc Boot BOM không.
6. Kiểm direct declaration/catalog constraint hay transitive dependency nào yêu cầu version cao hơn.
7. Đọc Boot support matrix và upstream release notes.
8. Thay một biến: nâng Boot patch, thay dependency, hoặc constraint đã phê duyệt.
9. Chạy tests/integration tests/bootJar.
10. Xóa workaround cũ nếu upgrade đã giải quyết.

**Không giả định selected version là đúng chỉ vì Gradle resolve không báo lỗi.** Gradle biết giải thuật version conflict, không có khả năng đảm bảo mọi tổ hợp third-party libraries chạy đúng cùng nhau.

## 15. Spring Boot Starter, dependency và BOM không giống nhau

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `spring-boot-starter-web` | Tập dependencies cho ứng dụng Spring MVC trên Boot3.5 | `implementation("...:spring-boot-starter-web")` |
| `spring-boot-starter-validation` | Validation stack | `implementation("...:spring-boot-starter-validation")` |
| `spring-boot-starter-test` | JUnit/Spring Test stack | `testImplementation("...:spring-boot-starter-test")` |
| `spring-boot-dependencies` | Tập managed version constraints | `implementation(platform("..."))` |
| `org.springframework.boot` Gradle plugin | Build tasks và executable packaging | `plugins { id(...) version ... }` |

**Starter không có nghĩa “một JAR duy nhất”.** Nó thường là POM/module với transitive graph. BOM không tự kéo starter vào app; nó chỉ quản lý versions khi dependency tham gia graph.

Một lỗi phổ biến:

```kotlin
// Chỉ import BOM, không có web implementation:
dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )
}
```

Điều đó **không thêm Spring MVC/Tomcat**. Muốn có web functionality, phải khai báo `spring-boot-starter-web` hoặc các modules thực sự cần.

## 16. Spring Cloud BOM: thêm release train có mục tiêu

Dự án tích hợp Spring Cloud có thể cần **thêm Spring Cloud BOM** vì nhiều Cloud dependencies không thuộc Spring Boot BOM hoặc cần phiên bản được quản lý theo release train.

Mẫu ý tưởng:

```kotlin
dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )

    // Thêm một Spring Cloud BOM CHỈ khi đã chọn release train
    // tương thích với đúng Spring Boot version.
    // implementation(platform("org.springframework.cloud:spring-cloud-dependencies:<approved-version>"))
}
```

Dòng comment chứa cú pháp placeholder để **giải thích vị trí**, không phải lệnh dùng trong demo. Để thêm thật, tra [Spring Cloud compatibility release train](https://spring.io/projects/spring-cloud) và điền release đã được xác minh. Không đoán phiên bản Cloud chỉ từ Boot major.minor, không để literal `latest` hoặc `+` ở production.

### 16.1. Nếu hai BOM cùng quản lý một artifact

- Gradle có thể nhận constraints từ cả hai.
- Version được chọn dựa trên kết hợp constraints/requirements.
- Không thể suy “BOM khai báo sau luôn thắng” theo cú pháp Gradle native platform như quy tắc chung.
- Nếu có strict conflicts, resolution có thể fail.
- Phải xem dependencyInsight ở configuration cần và kiểm Spring Boot/Spring Cloud compatibility.
- Đừng ép tất cả bằng `enforcedPlatform` để che một release train sai.

**Cấu hình Spring Cloud phải là một quyết định compatibility**, không phải chỉ thêm BOM vì project có “cloud” trong tên.

## 17. Trường hợp một library chưa có trong Boot BOM

Nếu Gradle báo:

```text
Could not find org.example:some-library:.
```

hoặc lỗi version missing khi bạn khai báo versionless module, có thể library đó **không được BOM quản lý** hoặc platform chưa áp vào đúng configuration.

Với artifact **không do Boot quản lý**, đưa version vào catalog:

```toml
[versions]
third-party-api = "1.2.3"

[libraries]
third-party-api = { module = "org.example:third-party-api", version.ref = "third-party-api" }
```

**Đây là tọa độ giả định để minh họa TOML**, không phải library có thật hay dependency để thêm vào demo. Với project thật, thay bằng artifact và version đã được kiểm theo repository/vendor docs. Nếu phiên bản được publish trong một BOM riêng, ưu tiên nhập BOM tương ứng.

### 17.1. Một lỗi versionless khác

Ngay cả khi artifact nằm trong Boot BOM, versionless declaration có thể fail nếu bạn chỉ nhập BOM ở `implementation` nhưng dependency lại nằm trong một **detached configuration** hoặc `annotationProcessor` không kế thừa BOM constraint. Phải kiểm configuration graph chứ không vội ghim version.

## 18. Dependency locking, verification và tính tái lập

Spring Boot BOM giúp đồng bộ **tập versions**, nhưng không tự khóa mọi resolved dependency graph theo thời gian. Gradle có cơ chế:

### 18.1. Dependency locking

Có thể bật Gradle dependency locking trên các configurations cần quản lý:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Sau đó generate lock state bằng một invocation resolve configurations phù hợp, ví dụ:

```bash
./gradlew test bootJar --write-locks
```

Lưu `gradle.lockfile` trong VCS. Lưu ý: `--write-locks` chỉ ghi dependencies trong các **configurations được resolve** ở invocation đó; không suy rằng một lệnh đã bao phủ mọi detached/custom/integration-test configuration.

**Khi nâng Boot/BOM:**

1. Sửa version Boot/BOM có chủ đích.
2. Chạy tasks resolve các configurations cần update với `--write-locks`.
3. Review lockfile diff để biết package nào thực sự đổi.
4. Chạy tests và dependency diagnostics.
5. Commit lockfile cùng dependency version changes.

Locking làm selected versions tái lập, nhưng **không xác minh artifact đã được tải là bytes đáng tin**; vấn đề đó là dependency verification.

### 18.2. Dependency verification

Gradle hỗ trợ checksum/signature verification qua:

```text
gradle/verification-metadata.xml
```

Lệnh bootstrap có thể là:

```bash
./gradlew --write-verification-metadata sha256
```

Nhưng bootstrap từ repository trạng thái hiện tại có yếu tố **trust on first use**. Đừng auto-approve mọi checksum; kiểm nguồn chính thức, artifact metadata, nhà phát hành, rồi review diff. Khi đổi Spring Boot BOM, nhiều transitive artifacts có thể thay, cần cập nhật verification metadata và audit cùng lockfiles.

### 18.3. Không dùng dynamic versions trong release

Tránh:

```kotlin
implementation("org.springframework.boot:spring-boot-starter-web:3.+")
implementation("org.example:helper:latest.release")
```

Những ví dụ phản diện này làm version phụ thuộc repository metadata/time. Với Spring Boot-managed artifacts, **không ghi version** khi BOM đủ quản lý; với library bên ngoài BOM, pin release/constraints và dùng locking khi phù hợp.

### 18.4. Không “fix” verification mismatch bằng cách tắt security

Nếu checksum không khớp sau upgrade, có thể là artifact mới hợp lệ, metadata khác, mirror sai hoặc tấn công supply chain. Đọc Gradle verification report, kiểm nguồn và chỉ update metadata sau xác minh. Không đổi `verificationMode=off` cho CI chỉ để build xanh.

## 19. Nâng Spring Boot 3.5 lên 4.x không chỉ đổi một chuỗi version

Spring Boot 4.1.x đã có tài liệu riêng với nhiều thay đổi về module/starter names và Jakarta/Spring Framework ecosystems. Tài liệu Boot4.1.2 hiện công bố hỗ trợ **Gradle8.14+ và Gradle9.x**, Java17 trở lên theo system requirements; chính sách áp dụng cho project phải kiểm release tương ứng.

**Đừng copy nguyên code Boot3.5 vào Boot4 và chỉ thay version.** Ví dụ Spring Boot4 giới thiệu/ưu tiên `spring-boot-starter-webmvc` trong khi `spring-boot-starter-web` được ghi là deprecated trong tài liệu Boot4. Test slices/import packages có thể thay đổi.

Checklist upgrade:

1. Đọc release notes/migration guide từ Boot3.5 → Boot4.
2. Xác định JDK và Gradle Wrapper tối thiểu mà Boot4 yêu cầu.
3. Thống kê plugins tích hợp: Spring Cloud, Kotlin, Hibernate, Security, OpenAPI, Flyway, native-image.
4. Nâng **Boot Gradle plugin và Spring Boot BOM cùng release**, tốt nhất qua một catalog version.
5. Chuyển starters/auto-configuration/test dependencies theo tài liệu major mới.
6. Kiểm source compile và imports theo Spring Framework/Jakarta versions.
7. Chạy `dependencies`/`dependencyInsight` để xác nhận Jackson/Spring/JUnit versions.
8. Xử lý loại bỏ overrides/constraints không còn cần.
9. Update lockfiles và verification metadata sau review.
10. Chạy unit/integration/contract tests và `bootJar`.
11. Chạy executable JAR smoke test ở Java runtimes được hỗ trợ.
12. Kiểm metrics/logging/management endpoints nếu app có Actuator.
13. Đảm bảo Docker/native-image/runtime packaging tương thích.
14. Review vulnerability report: dependency mới không đồng nghĩa tất cả CVEs đã được xử lý.
15. Chỉ release khi qua compatibility matrix và môi trường staging.

**Đối với bài học này, giữ Boot3.5.16 demo độc lập để không trộn Boot3 và Boot4 APIs trong cùng một project.**

## 20. Groovy DSL tương đương ở mức cơ chế

Nhiều Spring Boot repositories vẫn dùng `build.gradle` Groovy DSL. Cơ chế vẫn là Boot plugin + native platform:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

group = 'com.example'
version = '0.1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.16')
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.5.16')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

**Đây là một `build.gradle` thay thế cho Kotlin DSL file**, không để cả hai files cùng một project rồi mong Gradle merge. Các Java sources và settings giữ như phần 6. Groovy `implementation platform(...)` tương đương Kotlin `implementation(platform(...))`, không thay semantics dependency resolution.

## 21. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm |
| --- | --- | --- |
| `Could not find ...starter-web:.` | Khai báo starter không version nhưng chưa có BOM/DM | Import platform trên đúng configuration hoặc apply DM |
| Version Boot plugin khác BOM | Literal versions ở hai nơi | Dùng catalog một version hoặc BOM_COORDINATES |
| `NoSuchMethodError` sau upgrade | Resolved Spring/Jackson family versions lệch | `dependencyInsight`, constraints, Boot BOM alignment |
| `ClassNotFoundException` ở runtime | Thiếu runtime module, exclude sai hoặc scope sai | `runtimeClasspath` và contents `bootJar` |
| JUnit không được phát hiện | Chưa `useJUnitPlatform()` hoặc thiếu test engine/launcher | `testRuntimeClasspath` và Test task |
| `@WebMvcTest` import không tồn tại khi dùng Boot4 | Boot4 đổi module/test APIs | Đọc migration guide, không copy Boot3 imports |
| Maven Central tải được nhưng version vẫn missing | Repository khác version selection; BOM chưa có | `platform`, config scope, alias |
| IDE hiện một version, runtime thấy version khác | Requested vs resolved, IDE chưa sync | Gradle dependency report là nguồn sự thật |
| `dependencies` toàn thấy `(c)` | BOM constraints, không phải artifacts tất cả đều được tải | Đọc subtree và `dependencyInsight` |
| `spring-core` chọn version cao hơn BOM | Transitive stronger version/conflict | `dependencyInsight --dependency spring-core` |
| `enforcedPlatform` gây xung đột public library | Cưỡng chế version leak downstream | Dùng `platform` hoặc constraints đúng scope |
| DM plugin auto import không xảy ra | Chỉ áp Boot plugin, chưa apply DM | Kiểm `plugins`/`apply(plugin=...)` |
| Property `slf4j.version` không có tác dụng | Đang dùng native Gradle platform | Dùng Gradle constraints/upgrade BOM |
| Root có BOM nhưng subproject không nhận | Không khai báo platform vào subproject config | Tách project/config scopes |
| Starter bên ngoài Boot BOM missing version | BOM không quản lý mọi artifact | Pin riêng/nhập BOM phù hợp |
| Spring Cloud runtime incompatibility | Dùng release train không khớp Boot | Kiểm Spring Cloud compatibility table |
| Gradle plugin resolution fail | Plugin Portal/settings plugin repositories/Gradle version | `plugins`, `pluginManagement.repositories` |
| Dependency resolution 401/403 | Maven mirror/auth sai | Repository settings, credentials |
| `bootJar` bị thiếu | Chưa apply Boot plugin/Java plugin hoặc task disabled | `./gradlew tasks` và plugin setup |
| `jar` không chạy bằng `java -jar` | Plain JAR không là Boot executable | Dùng `bootJar` |
| `test NO-SOURCE` | File test sai `src/test/java` | Kiểm sourceSets/packages |
| CVE scanner vẫn báo version cũ | Lockfile chưa cập nhật hoặc override/constraint giữ cũ | Resolve runtime graph, refresh locks |
| Build pass local, fail CI | JDK/Gradle Wrapper/repo/caches khác | `./gradlew --version`, toolchains, flags |
| Cache làm thấy dependency cũ | Dynamic version metadata/lockfiles/repository state | Kiểm Gradle refresh semantics, không xóa bừa |
| Error `No matching Java toolchain` | JDK17 chưa có/provisioning chưa setup | `javaToolchains`/JAVA_HOME/CI |
| Nâng plugin Boot3.5 → Boot4 nhưng giữ all test imports | Breaking changes major | Migration guide và Boot4 test starters |
| Locking fail khi tăng BOM | Lockfile cũ inject strict versions | Regenerate/review `--write-locks` |
| Verification checksum fail | Artifact mới/changed/mirror issue | Validate artifact trước khi update metadata |
| Một dependency có hai versions trong tree | Multiple paths/requests | `dependencyInsight` từng configuration |
| Giảm version bằng `force` rồi app runtime crash | Constraint không bảo đảm binary compat | Bỏ force, nâng Boot/test full graph |
| Tool `dependencyManagement` không tồn tại | Dùng native platform không có Spring DM plugin | Dùng Gradle `dependencies`/`dependencyInsight` |

### 21.1. Runbook ngắn khi nâng Spring Boot rồi build đỏ

1. Ghi lại exact Gradle Wrapper/JDK và Boot plugin/BOM versions.
2. Kiểm `settings.gradle.kts`, repositories và plugin management.
3. Xem error xảy ra **khi resolve plugin**, **resolve dependency**, compile hay runtime.
4. Chạy `./gradlew dependencies --configuration runtimeClasspath`.
5. Chạy `./gradlew dependencyInsight --dependency <module> --configuration runtimeClasspath` với artifact thật.
6. So selected version với official managed dependency coordinates.
7. Kiểm mọi force/exclude/strict constraint và imported BOM khác.
8. Kiểm scope: `compileClasspath` vs `runtimeClasspath` vs `testRuntimeClasspath`.
9. Kiểm các modules sử dụng BOM cùng release.
10. Thay một yếu tố và chạy `test bootJar`.
11. Chạy lại không cache khi cần xác minh một lỗi cache-specific.
12. Nếu sửa security, update locks/checksums với review.
13. Không xóa quality gates hoặc exclude critical library để “làm xanh”.
14. Thêm regression test nếu bug có thể tái diễn.

## 22. Bài tập tự luyện

### Bài 1 — bỏ platform để hiểu BOM

Trong một **copy sandbox** của demo, tạm bỏ hai `platform(...)` declarations, giữ starters versionless. Chạy `./gradlew dependencies --configuration runtimeClasspath` và quan sát resolution failure (tùy dependency state). Khôi phục platform và chạy lại.

**Mục tiêu:** hiểu Boot plugin không tự cung cấp mọi managed version nếu bạn không áp một dependency management mechanism.

### Bài 2 — so hai chiến lược

Tạo hai bản copy của demo: A dùng `platform`; B apply `io.spring.dependency-management`. Chạy `dependencies`, `dependencyInsight` và `test`. Ghi điểm giống/khác, không chạy cả hai kiểu trong cùng bản thử nghiệm.

### Bài 3 — tìm Jackson version thật

```bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Ghi **requested/selected/reason** và so với Boot3.5.16 managed coordinates. Không đoán version theo trí nhớ.

### Bài 4 — thêm version catalog

Chuyển plugin/BOM/starters sang `libs.versions.toml`. Chỉ chỉnh một `spring-boot` version entry; kiểm plugin/BOM đồng bộ bằng dependency graph sau upgrade. Không đổi version trong production ngay khi chưa đọc release notes.

### Bài 5 — multi-project scopes

Tạo `:app`/`:core`, đặt BOM đúng cho project cần nó. Trong một lần thử, bỏ platform khỏi `:core` nhưng vẫn khai báo versionless Spring dependency. Xem configuration nào fail và vì sao root/app BOM không tự “bao phủ” mọi module.

### Bài 6 — thêm third-party library

Chọn một artifact **thật sự không được Boot BOM quản lý** (tra official managed coordinates trước). Ghim version qua version catalog, chạy dependencyInsight. Phân biệt managed và unmanaged dependencies.

### Bài 7 — constraint có reason

Trong sandbox thêm một explicit constraint cho một artifact đã chọn, dùng `because(...)`. Quan sát `dependencyInsight` báo selection reason. Bỏ constraint và xác nhận trở về Boot-managed behavior.

### Bài 8 — test lockfiles

Bật `dependencyLocking`, chạy `./gradlew test bootJar --write-locks`, commit thử trong branch và đọc diff sau khi tăng Boot patch version. Không tự sửa lockfile thủ công nếu có tool hỗ trợ sinh lại.

### Bài 9 — nhận diện lỗi Boot major upgrade

Trong một branch riêng, chuẩn bị đổi sang Boot4.x. Tra danh sách starters/test imports/deprecation. Không dùng nguyên `@WebMvcTest` Boot3.5 imports khi Boot4 API đã chuyển; ghi migration tasks trước khi đổi version.

### Bài 10 — runtime smoke

Chạy `bootJar`, `java -jar`, gọi `GET /hello`, kiểm exact response. Nếu Gradle `test` pass nhưng JAR không chạy, tìm packaging/runtimeClasspath problem thay vì chỉ xem test report.

## 23. Câu hỏi tự kiểm tra

1. **BOM làm gì?** Đưa bộ managed dependency versions/constraints cho các artifacts trong graph.
2. **BOM tự thêm `starter-web` không?** Không; bạn vẫn cần implementation declaration.
3. **Spring Boot Gradle Plugin và BOM có phải một không?** Không; plugin làm build integration, BOM làm version management.
4. **Áp chỉ Boot plugin có tự quản mọi dependency không?** Không nên giả định; cần DM plugin hoặc native BOM.
5. **`platform` khác `enforcedPlatform` thế nào?** Native constraints/recommendations vs cưỡng chế mạnh.
6. **Version catalog có cưỡng chế resolved version không?** Không; nó khai báo coordinates/requested versions.
7. **Muốn hai nơi cùng Boot version trong catalog?** Dùng một `version.ref` cho plugin và BOM aliases.
8. **BOM ở `implementation` có tự áp cho mọi detached configuration không?** Không.
9. **`testImplementation(platform(...))` giúp gì?** Làm Boot version management tường minh trong test graph.
10. **Lệnh nào xem runtime dependency tree?** `dependencies --configuration runtimeClasspath`.
11. **Lệnh nào giải thích version Jackson đã chọn?** `dependencyInsight --dependency jackson-databind --configuration runtimeClasspath`.
12. **`buildEnvironment` khác `dependencies`?** Nó chủ yếu cho buildscript classpath.
13. **Khi Gradle chọn version cao hơn BOM, BOM hỏng?** Không nhất thiết; normal conflict resolution có thể chọn khác.
14. **Tại sao không force mọi versions về BOM?** Có thể gây xung đột downstream và che compatibility issue.
15. **Có thể dùng DM plugin để override version qua BOM property?** Có, với property được Boot BOM công bố.
16. **Có thể dùng tương tự khi chỉ dùng `platform`?** Không; dùng Gradle-native mechanism.
17. **`SpringBootPlugin.BOM_COORDINATES` giúp gì?** Tham chiếu BOM version khớp Boot plugin.
18. **Library public có nên xuất `enforcedPlatform` của Boot ra consumer?** Thường không nếu không có contract rõ.
19. **Nếu một artifact không nằm trong BOM?** Khai báo version riêng hoặc BOM/constraint phù hợp.
20. **Spring Cloud BOM có thể ghép tùy ý với Boot?** Không; phải kiểm release train compatibility.
21. **Dependency locking có thay checksum verification không?** Không; locking pin selected versions, verification kiểm artifacts.
22. **`--write-locks` có tự resolve mọi config trong mọi project không?** Chỉ các configs được resolve ở invocation/tác vụ phù hợp.
23. **Vì sao không dùng version `3.+` cho release?** Không tái lập theo thời gian.
24. **Boot3.5 → Boot4 chỉ đổi plugin version là đủ?** Không; migration ảnh hưởng modules/starters/test imports và compatibility.
25. **Một build xanh đã đủ chứng minh dependency đúng?** Không; cần dependency graph, tests, runtime smoke và security review khi áp dụng.

## 24. Checklist trước khi merge thay đổi dependency

- [ ] Spring Boot Plugin/BOM sử dụng version phù hợp với nhau.
- [ ] Chỉ dùng một dependency management strategy có chủ đích.
- [ ] Các Boot-managed starters không bị hardcode versions lặp lại.
- [ ] Version catalog có một nguồn Spring Boot version khi dùng catalog.
- [ ] Platform áp ở đúng main/test/custom configurations.
- [ ] Mọi thư viện ngoài BOM có version/constraint rõ.
- [ ] Đã kiểm requested vs selected versions bằng dependencyInsight.
- [ ] Không có `force`/`enforcedPlatform` không giải thích được.
- [ ] Không có exclude làm mất runtime classes.
- [ ] Multi-project libraries có public API/constraints đúng phạm vi.
- [ ] Spring Cloud BOM tương thích Boot release.
- [ ] Gradle Wrapper và Java toolchain đáp ứng Boot plugin requirements.
- [ ] Có unit/web-layer/integration tests phù hợp.
- [ ] `bootJar`/`java -jar` chạy được trên runtime hỗ trợ.
- [ ] Các thay đổi Boot major đã đọc migration notes.
- [ ] Lockfiles được sinh lại và review nếu build bật locking.
- [ ] Verification metadata cập nhật chỉ sau xác minh nguồn.
- [ ] Không dùng dynamic versions/SNAPSHOT trong release nếu không có chính sách.
- [ ] Repositories/mirrors/credentials dùng đúng môi trường.
- [ ] Không tắt test/verification chỉ để bỏ lỗi resolution.
- [ ] Dependency vulnerability report được đánh giá.
- [ ] Changelog/PR nêu lý do version override nếu có.
- [ ] CI có Gradle/JDK/runtime smoke đúng hợp đồng.
- [ ] Build reproducibility và output artifact được kiểm.
- [ ] Có phương án rollback nếu nâng một family dependencies gây lỗi.

## 25. Ghi nhớ

- **Spring Boot BOM là nguồn quản lý phiên bản cho một tập dependencies đã được Spring Boot kiểm thử cùng nhau**.
- **Plugin version, BOM version và resolved version là ba khái niệm khác nhau**.
- **Boot plugin một mình không thay BOM import**; dùng `platform` hoặc `io.spring.dependency-management`.
- **Gradle native `platform(...)` là cơ chế chuẩn, dễ kiểm scope và thường nhẹ hơn**; DM plugin có property-based overrides.
- **Version catalog centralizes aliases/versions nhưng không ép Gradle chọn version**; BOM/platform/constraints mới tham gia resolution.
- **Khai báo BOM đúng configuration**: main, test, annotation processor và integration test có thể khác nhau.
- **Đọc `dependencies` và `dependencyInsight` thay vì đoán transitive versions**.
- **Không lạm dụng `enforcedPlatform`, `strictly`, `force` hoặc excludes** khi chưa có compatibility evidence.
- **Ứng dụng và reusable library không có cùng quyền áp BOM lên consumers**.
- **Spring Boot major upgrades phải đi cùng starter/test/Gradle/JDK compatibility review**.
- **Lockfiles và checksum verification bổ sung tính tái lập/an ninh**, không thay thế BOM.
- **Build đúng trước; chỉ tối ưu hoặc ghi đè managed versions khi có lý do, test và CI evidence**.

## Tài liệu chính thức

- [Spring Boot 3.5 — Gradle Plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/): plugin requirements, Boot Gradle integration.
- [Spring Boot 3.5 — Getting Started with Gradle](https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html): cách apply Boot plugin và dependency management.
- [Spring Boot — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html): Spring Dependency Management plugin vs Gradle native BOM, BOM_COORDINATES, override.
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): artifacts và versions thực sự do BOM quản lý.
- [Spring Boot 3.5 — Managed Dependency Properties](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/properties.html): BOM property names cho DM plugin.
- [Spring Boot 4.1 — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html): curated BOM, starters và thay đổi ở Boot4.
- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java/Gradle requirements cho Boot4, cần kiểm theo release.
- [Gradle — Platforms and BOM Import](https://docs.gradle.org/current/userguide/platforms.html): platform/enforcedPlatform semantics.
- [Gradle — Using Catalogs with Platforms](https://docs.gradle.org/current/userguide/centralizing_catalog_platform.html): catalog aliases vs resolved dependency graph.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): TOML aliases, versions/plugins/libraries, accessors.
- [Gradle — Dependency Constraints](https://docs.gradle.org/current/userguide/dependency_constraints.html): version requirements, strictly, because.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencies/dependencyInsight and selection reasons.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): `gradle.lockfile` và `--write-locks`.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): SHA checksums, trust-on-first-use và verification metadata.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): api/implementation scopes for published libraries.
- [Spring Cloud — Supported Release Trains](https://spring.io/projects/spring-cloud): chọn Cloud BOM tương thích Spring Boot.
