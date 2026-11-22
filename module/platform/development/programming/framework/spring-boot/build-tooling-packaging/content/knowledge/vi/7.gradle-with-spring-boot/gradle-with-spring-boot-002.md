# Đối chiếu cú pháp Groovy DSL và Kotlin DSL cho cấu hình Gradle phổ biến trong Spring Boot

## 1. Mục tiêu và điều cần hiểu trước

Gradle cho phép viết logic cấu hình build bằng **Groovy DSL** hoặc **Kotlin DSL**. Hai DSL đều điều khiển cùng mô hình Gradle: project, plugin, repository, dependency, configuration, task, toolchain và build lifecycle. Khác biệt chủ yếu nằm ở **ngôn ngữ viết script, cách gọi API, cách định kiểu, khả năng kiểm tra cú pháp và các cơ chế accessor**.

Bài này giúp bạn:

- Nhận diện đúng cặp tệp `build.gradle`/`settings.gradle` (Groovy DSL) và `build.gradle.kts`/`settings.gradle.kts` (Kotlin DSL).
- Viết hai cấu hình **tương đương về hành vi** cho ứng dụng Spring Boot dùng Java 17.
- Chuyển đổi cú pháp của `plugins`, `repositories`, `dependencies`, Java toolchain, test, task configuration, Spring Boot packaging, Gradle properties, project con và version catalog.
- Phân biệt chỗ chỉ thay cú pháp với chỗ cần hiểu **kiểu dữ liệu hoặc semantics của Gradle**.
- Kiểm chứng bằng wrapper, task graph và dependency resolution; tránh chuyển script bằng tìm-thay chuỗi máy móc.

**Ngữ cảnh:** minh họa dự án Java + Spring Boot, Spring Boot Gradle Plugin `3.3.13`, Spring dependency-management plugin `1.1.7` và Java 17. Phiên bản được dùng làm ví dụ đối chiếu, không phải tuyên bố phiên bản mới nhất. Khi thực hiện trên repository thật, giữ nguyên các version được project/CI phê duyệt và chọn Gradle wrapper tương thích.

**Điều rất dễ nhầm:** dùng `build.gradle.kts` **không có nghĩa application source phải viết bằng Kotlin**. Một ứng dụng Java vẫn có thể build bằng Kotlin DSL; muốn viết application bằng Kotlin còn cần Kotlin compiler plugin và các dependency phù hợp.

## 2. Cùng một project, khác đuôi tệp cấu hình

| Mục đích | Groovy DSL | Kotlin DSL |
| --- | --- | --- |
| Cấu hình dự án | `build.gradle` | `build.gradle.kts` |
| Cấu hình root, include modules | `settings.gradle` | `settings.gradle.kts` |
| Logic build tái sử dụng | Script `.gradle` hoặc plugin Groovy | Script `.gradle.kts` hoặc plugin Kotlin |
| Chạy task | `./gradlew build` | `./gradlew build` |
| Properties key-value | `gradle.properties` | `gradle.properties` (giống nhau) |
| Version catalog | `gradle/libs.versions.toml` | `gradle/libs.versions.toml` (giống nhau) |
| Ngôn ngữ script | Groovy, thường dynamic | Kotlin, được compile/type-check |

Gradle **chọn DSL qua đuôi tệp**, không qua nội dung ghi trong script. Không được đổi tên `build.gradle` thành `build.gradle.kts` rồi giữ nguyên mọi cú pháp Groovy. Kotlin DSL cần dấu ngoặc, dấu ngoặc kép, khai báo kiểu và cú pháp API Kotlin tương ứng.

Một build nhiều module có thể có các subproject dùng hai DSL khác nhau; nhưng ở **cùng một project**, chỉ nên duy trì một tệp build chính rõ ràng để tránh hai nguồn cấu hình gây hiểu nhầm. Ví dụ dưới đây dùng hai thư mục độc lập để so sánh, không đặt đồng thời hai bản cùng tên logic vào cùng một module.

## 3. Cặp ví dụ hoàn chỉnh có cùng hành vi

Mục tiêu của cả hai cấu hình:

1. Build ứng dụng Java 17 và Spring Boot 3.3.13.
2. Tải dependency `spring-boot-starter-web` và `spring-boot-starter-test`.
3. Quản lý dependency version bằng `io.spring.dependency-management` và BOM Spring Boot.
4. Sử dụng Maven Central; bật JUnit Platform.
5. Tạo executable JAR bằng `bootJar` và chạy `test`/`build` bằng Gradle wrapper.

### 3.1. Cặp settings: tên project

**Groovy DSL — `settings.gradle`**

~~~groovy
rootProject.name = 'demo'
~~~

**Kotlin DSL — `settings.gradle.kts`**

~~~kotlin
rootProject.name = "demo"
~~~

Hai dòng có cùng ý nghĩa. Khác biệt ở đây chủ yếu là dấu nháy: Groovy chấp nhận chuỗi single-quoted; Kotlin dùng double-quoted string. `rootProject.name` không phải tên package Java; nó xác định tên root project Gradle, có thể ảnh hưởng convention đặt tên archive.

### 3.2. Bản build Groovy hoàn chỉnh — `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 3.3. Bản build Kotlin hoàn chỉnh — `build.gradle.kts`

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
~~~

**Hai script ở trên có cùng mục đích build.** Trong bản Kotlin, `Test` là kiểu Gradle test task; khai báo `tasks.named<Test>("test")` cho Kotlin compiler biết task có phương thức `useJUnitPlatform()`. Trong bản Groovy, lời gọi `tasks.named('test')` được xử lý bằng Groovy/Gradle DSL theo kiểu linh hoạt hơn.

**Vì sao bản Kotlin dùng `languageVersion.set(...)`?** Gradle API biểu diễn cấu hình toolchain bằng kiểu `Property<JavaLanguageVersion>`. Gọi `set` là cách rõ ràng và tương thích rộng với Gradle 8.x. Các bản Gradle mới hỗ trợ lazy property assignment, vì thế đôi khi bạn còn gặp `languageVersion = JavaLanguageVersion.of(17)` trong Kotlin DSL; hãy dùng một kiểu nhất quán với Gradle wrapper của dự án.

**Không thêm version cho hai Spring Boot starter trong ví dụ:** plugin `io.spring.dependency-management` kết hợp với Spring Boot Gradle Plugin để import BOM phù hợp; vì vậy các version do BOM quản lý có thể được lược bỏ. Chỉ áp dụng Spring Boot Gradle Plugin **không đồng nghĩa** mọi dependency version đều tự được quản lý nếu project không dùng dependency-management plugin hoặc Gradle BOM.

### 3.4. Source Java dùng chung cho hai project

Để minh chứng rằng DSL không quyết định ngôn ngữ application, cả hai project dùng chính xác mã Java sau. Tạo file `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Tạo file `src/main/java/com/example/demo/PingController.java`:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Khi project có JDK phù hợp, Gradle wrapper và kết nối repository, hai script đều cấu hình được một ứng dụng Spring MVC. Lệnh trong thư mục project:

~~~bash
./gradlew --version
./gradlew test
./gradlew bootJar
./gradlew build
./gradlew bootRun
~~~

Trên Windows PowerShell, sử dụng `.\gradlew.bat` thay cho `./gradlew`. Nếu chưa có Gradle wrapper, bạn cần tạo/cung cấp wrapper hoặc dùng Gradle đã cài đúng phiên bản; **một tệp build.gradle không tự sinh ra gradlew**.

Với `bootRun` hoạt động trên HTTP port mặc định 8080, request `GET http://localhost:8080/ping` có body chính xác:

~~~text
pong
~~~

`bootJar` tạo executable Boot JAR trong `build/libs` (tên theo project/version/classifier). `build` thường chạy `assemble` lẫn `check` theo Java lifecycle; gọi `bootJar` đơn lẻ không bảo đảm test suite đã chạy.

## 4. Quy tắc chuyển cú pháp cốt lõi

| Ý định | Groovy DSL | Kotlin DSL |
| --- | --- | --- |
| Chuỗi cố định | `'demo'` hoặc `"demo"` | `"demo"` |
| Plugin id | `id 'java'` | `id("java")` hoặc accessor `java` |
| Plugin có version | `id 'org.springframework.boot' version '3.3.13'` | `id("org.springframework.boot") version "3.3.13"` |
| Gọi hàm cấu hình | `implementation 'g:a:v'` | `implementation("g:a:v")` |
| Tham số đặt tên | `someMethod key: 'value'` khi API Groovy hỗ trợ | `someMethod(key = "value")` khi API Kotlin có tham số tương ứng |
| Khai báo biến cục bộ | `def env = 'dev'` | `val env = "dev"` hoặc `var env = "dev"` |
| Boolean | `enabled = false` | `enabled = false` |
| Test task có kiểu | `tasks.named('test') { ... }` | `tasks.named<Test>("test") { ... }` |
| Property API | `languageVersion = JavaLanguageVersion.of(17)` | `languageVersion.set(JavaLanguageVersion.of(17))` |
| Đọc property lazy | `providers.gradleProperty('env')` | `providers.gradleProperty("env")` |
| Comment | `// ghi chú` hoặc `/* ... */` | `// ghi chú` hoặc `/* ... */` |

Đây là **bảng đối chiếu thường gặp**, không phải bộ chuyển đổi văn bản bảo đảm đúng cho mọi plugin. Kotlin DSL làm việc với static types: đôi khi Groovy viết `foo 'bar'` nhưng Kotlin phải tìm đúng function/property, kiểu `Provider` hoặc extension do plugin định nghĩa. Có những Groovy dynamic methods không có Kotlin accessor tương ứng; lúc đó cần dùng Gradle API chính thức hoặc `configure<T>` đúng kiểu.

**Điểm cần nhấn mạnh về `val`:** Kotlin `val` không thể gán lại biến, nhưng đối tượng mà nó trỏ tới vẫn có thể là một `Property` thay đổi được qua `set`. “Dùng `val`” không có nghĩa mọi giá trị cấu hình Gradle đều bất biến.

## 5. Plugins: cùng plugin ID, khác cách khai báo

### Groovy DSL

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}
~~~

### Kotlin DSL

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}
~~~

Cả hai cách đều áp dụng Java plugin, Spring Boot plugin và dependency-management plugin. Spring Boot plugin tạo các task như `bootJar` khi nhận diện Java plugin. Nếu không áp dụng Java/Kotlin JVM/War plugin thích hợp, chỉ có Spring Boot plugin không bảo đảm có đủ source model hay task packaging.

Có thể thấy Kotlin DSL viết `java` thay cho `id("java")` trong `plugins`, nhờ typed accessor của Gradle dành cho core plugin. Tuy nhiên không thể tùy tiện viết tên plugin của bên thứ ba như biến Kotlin nếu không có accessor; `id("org.springframework.boot")` là dạng nhất quán, dễ đọc.

**Không nhầm plugin Groovy với Groovy DSL:** một dự án chỉ dùng Java plugin vẫn có thể được cấu hình bằng `build.gradle`. “Groovy DSL” là ngôn ngữ script build, còn `id 'groovy'` là plugin hỗ trợ **biên dịch source Groovy** của ứng dụng.

### Dùng `apply` thay vì `plugins`

Trong Groovy có thể gặp:

~~~groovy
apply plugin: 'java'
~~~

Trong Kotlin:

~~~kotlin
apply(plugin = "java")
~~~

Nhưng đối với cấu hình Spring Boot thông thường, ưu tiên `plugins { ... }` vì Gradle giải quyết plugin sớm, Kotlin DSL có thể sinh **type-safe accessors** trong lúc compile script. Khi plugin được apply bằng cơ chế imperative sau thời điểm hình thành accessors, Kotlin DSL có thể không nhận được các accessor như mong đợi; phải dùng Gradle API theo tên/kiểu thích hợp.

**Không dán cả `apply(plugin=...)` và `plugins` cho cùng plugin mà không có mục đích.** Chỉ một cách áp dụng rõ ràng là đủ cho các ví dụ phổ biến.

## 6. Repositories: DSL đổi nhưng nơi tải artifact không đổi

**Groovy DSL:**

~~~groovy
repositories {
    mavenCentral()
    maven {
        url = uri('https://repo.example.com/releases')
    }
}
~~~

**Kotlin DSL:**

~~~kotlin
repositories {
    mavenCentral()
    maven {
        url = uri("https://repo.example.com/releases")
    }
}
~~~

Repository `https://repo.example.com/releases` là **địa chỉ minh họa**, chưa có cơ sở khẳng định nó tồn tại; trong dự án thật thay bằng repository được quản trị. Không cần thêm repository giả này vào hai build script hoàn chỉnh ở mục 3. Cả hai DSL dùng `mavenCentral()` giống hệt.

Lưu ý hai hệ repository khác nhau:

- `pluginManagement.repositories` trong settings xác định nguồn resolve plugin của `plugins`.
- `repositories` trong build hoặc `dependencyResolutionManagement.repositories` trong settings xác định nguồn resolve dependencies của ứng dụng.

Ví dụ muốn chỉ định repository cho plugin trong `settings.gradle`:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
rootProject.name = 'demo'
~~~

Bản `settings.gradle.kts` tương ứng:

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
rootProject.name = "demo"
~~~

Đây là **hai file settings thay thế** cho bản tối giản ở mục 3.1, không phải nội dung thêm vào sau hai khối settings đồng thời. Khi cấu hình corporate mirror, cần đặt repository đúng loại: `mavenCentral()` trong dependencies block không tự giải quyết mọi plugin version được công bố trên Plugin Portal.

## 7. Dependencies: ngôn ngữ cú pháp khác, scope Gradle giống nhau

**Groovy:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

**Kotlin:**

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

Đây là hai **fragments minh họa**; thêm PostgreSQL runtimeOnly chỉ khi ứng dụng thật dùng JDBC/PostgreSQL. Các dependency `spring-boot-starter-web`, `spring-boot-starter-test` và `org.postgresql:postgresql` thuộc nhóm được Spring Boot 3.3 BOM quản lý trong cấu hình ví dụ.

| Configuration | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `implementation` | Cần khi compile/run mã chính | Không tự xuất bản API dependency của library như `api` |
| `compileOnly` | Cần biên dịch nhưng không là runtime dependency | Ví dụ annotation API/runtime do môi trường khác cung cấp |
| `runtimeOnly` | Chỉ cần lúc chạy, không cần trực tiếp để compile mã chính | JDBC driver là trường hợp thường gặp |
| `testImplementation` | Dùng khi biên dịch và chạy tests | Spring Boot test starter |
| `testRuntimeOnly` | Chỉ cần ở runtime test | Khi cấu hình test engine/runtime riêng |
| `api` | Expose dependency đến consumer của library | Cần `java-library` plugin; không có trong Java plugin tối giản |

**Cẩn trọng:** Groovy `implementation 'g:a:v'` không phải là “biến implementation gán chuỗi”; đây là lời gọi Gradle DSL. Kotlin `implementation("g:a:v")` là lời gọi function/type-safe accessor được Gradle tạo khi configuration tồn tại.

Nếu Kotlin DSL báo `Unresolved reference: implementation`, nguyên nhân có thể là chưa apply Java/JVM plugin khi script được compile, block đặt sai vị trí, hoặc chưa hoàn tất Gradle sync; không sửa bằng cách đổi dấu nháy ngẫu nhiên.

### 7.1. Quản lý version: plugin hay Gradle native BOM?

Ở ví dụ mục 3, `io.spring.dependency-management` cùng Spring Boot plugin import Spring Boot BOM. Đây là một cách phổ biến. Một cách khác là dùng **Gradle native platform**; hai DSL như sau.

**Groovy — ví dụ thay thế, không dùng đồng thời hai cơ chế chỉ để “nhân đôi” BOM:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

**Kotlin — cấu hình tương đương:**

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.13"))
    implementation("org.springframework.boot:spring-boot-starter-web")

    testImplementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.13"))
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Ở cách này, import BOM riêng cho `implementation` và `testImplementation` để các configuration có constraints phù hợp (theo quan hệ kế thừa của từng configuration). `platform` áp dụng các constraints do BOM cung cấp; **nó không ép tuyệt đối mọi version** nếu có conflict hoặc constraint mạnh hơn. `enforcedPlatform` có semantics cưỡng bức hơn và có thể gây tác động tới consumers, vì vậy không dùng như lựa chọn mặc định.

**BOM không tự thêm starter vào classpath.** Dù chọn cách nào, bạn vẫn khai báo dependency cần dùng. Nếu tự khai báo version không tương thích với Spring Boot BOM, cần kiểm tra dependency graph và lý do chọn version thay vì quy lỗi cho cú pháp DSL.

## 8. Java version và toolchain

**Groovy:**

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**Kotlin:**

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Cả hai đặt Java toolchain language version 17. Gradle toolchain cho phép build dùng JDK phù hợp để compile/test/task theo cấu hình, có thể khác JVM chạy Gradle daemon. Việc khai báo toolchain **không bảo đảm** JVM 17 có sẵn hay toolchain resolver đã được cấu hình tải JDK; xem `./gradlew javaToolchains` để biết Gradle tìm được JDK nào.

Nếu cần đặt encoding biên dịch:

**Groovy:**

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

**Kotlin:**

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

Đây là các fragment bổ sung vào build script có Java plugin. Groovy đặt kiểu task `JavaCompile` làm tham số cho `withType`; Kotlin dùng generic `withType<JavaCompile>()`. Trên các script Gradle Kotlin DSL chuẩn, `JavaCompile` thuộc kiểu API đã được Gradle cung cấp trong imports; nếu có build logic khác, dùng đầy đủ class `org.gradle.api.tasks.compile.JavaCompile`.

Cần phân biệt với cấu hình `sourceCompatibility = JavaVersion.VERSION_17` và `targetCompatibility`: những giá trị này nói về mức biên dịch/bytecode, không thay thế việc chọn đúng JVM/toolchain chạy compiler. Với Gradle hiện đại, toolchain là lựa chọn rõ ràng hơn khi cần nhất quán môi trường build.

## 9. Test: khác biệt cú pháp do Kotlin cần kiểu task

**Groovy:**

~~~groovy
tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<Test>("test") {
    useJUnitPlatform()
    testLogging {
        events("passed", "failed", "skipped")
    }
}
~~~

Đoạn code cấu hình JUnit Platform và các event log. Với Spring Boot 3.3 `spring-boot-starter-test` cung cấp JUnit Jupiter; gọi `useJUnitPlatform()` giúp Gradle chạy JUnit 5 tests.

Tại sao Kotlin cần `<Test>`? Với `tasks.named("test")` không có generic, biến task có thể chỉ được nhìn dưới kiểu chung `Task`, không expose `useJUnitPlatform()` hay `testLogging`. Khai báo `tasks.named<Test>("test")` yêu cầu đúng kiểu Gradle task. Một lựa chọn không cần tên task là:

~~~kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

Bản Groovy tương đương:

~~~groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

`configureEach` là kiểu cấu hình lazy, thường thích hợp hơn `tasks.all` khi muốn tránh hiện thực hóa mọi task sớm. Nếu project dùng plugin tạo các task test khác, `withType<Test>()` có thể áp dụng cho **mọi Test task**, trong khi `named<Test>("test")` chỉ chỉnh task mang tên `test`.

**Kiểm chứng hành vi:** chạy `./gradlew test`, quan sát Gradle có biên dịch/chạy test theo JUnit Platform hay không. Thành công của `bootJar` không chứng minh test đã chạy; `build` theo Java plugin thường nối `assemble` và `check`.

## 10. Đặt tên archive Spring Boot: `bootJar` và task typing

Một ví dụ tùy chỉnh file executable JAR thành `demo-app.jar`.

**Groovy:**

~~~groovy
tasks.named('bootJar') {
    archiveFileName = 'demo-app.jar'
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<org.springframework.boot.gradle.tasks.bundling.BootJar>("bootJar") {
    archiveFileName.set("demo-app.jar")
}
~~~

Đoạn Kotlin dùng tên class đầy đủ `BootJar` để có thể sao chép mà không thêm import. Nếu muốn gọn hơn, thêm `import org.springframework.boot.gradle.tasks.bundling.BootJar` **ở đầu** `build.gradle.kts`, rồi dùng `tasks.named<BootJar>("bootJar")`.

Cần biết:

- `bootJar` tạo Spring Boot executable JAR; `jar` là task JAR thông thường của Java plugin.
- Spring Boot Gradle Plugin 3.3 thường đặt classifier `plain` cho regular JAR để tránh đè lên executable JAR. Ví dụ: `demo-0.0.1-SNAPSHOT.jar` và `demo-0.0.1-SNAPSHOT-plain.jar`.
- `bootWar` xuất hiện khi cấu hình War plugin. Groovy/Kotlin khác DSL, **không khác cơ chế đóng gói**.
- Chỉ chỉnh `archiveFileName` ở `bootJar` khi thật sự cần tên output cụ thể; phải đảm bảo các task publish hoặc CI tham chiếu đúng artifact.

Để tùy chỉnh main class được Boot plugin dùng, có thể dùng:

**Groovy:**

~~~groovy
springBoot {
    mainClass = 'com.example.demo.DemoApplication'
}
~~~

**Kotlin:**

~~~kotlin
springBoot {
    mainClass.set("com.example.demo.DemoApplication")
}
~~~

Các fragment này bổ sung vào script có Spring Boot plugin. Với ví dụ một entrypoint ở mục 3, plugin thường tìm main class tự động; khai báo tường minh hữu ích khi có nhiều main classes hoặc cần rõ ràng trong CI. Đặt sai package/class sẽ khiến Boot run/packaging không tìm được entrypoint.

### WAR và provided runtime

Nếu ứng dụng Servlet cần tạo executable WAR, áp dụng `war` plugin trong cả hai DSL.

**Groovy fragment:**

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

**Kotlin fragment:**

~~~kotlin
plugins {
    id("java")
    id("war")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
}
~~~

**Hai đoạn này là fragment minh họa phần khác với JAR**. Khi chuyển build ví dụ ở mục 3 thành WAR, sửa `plugins` và `dependencies` hiện tại, giữ các phần project/repository/toolchain cần thiết; không thêm khối `plugins` thứ hai vào một build script. Nếu cần deploy WAR vào servlet container bên ngoài, ứng dụng Servlet thông thường còn cần `SpringBootServletInitializer` và phiên bản container tương thích. Chỉ đổi DSL không thay đổi yêu cầu runtime này.

## 11. Gradle properties, môi trường và logic điều kiện

Đối với lựa chọn môi trường build, nên đọc **Gradle project property** bằng Provider API, giúp hỗ trợ lazy evaluation và configuration cache.

Trong `gradle.properties` (dùng chung cả hai DSL):

~~~properties
buildFlavor=local
org.gradle.caching=true
~~~

**Groovy fragment:**

~~~groovy
def buildFlavor = providers.gradleProperty('buildFlavor').orElse('local')

tasks.register('showBuildFlavor') {
    doLast {
        println 'Build flavor: ' + buildFlavor.get()
    }
}
~~~

**Kotlin fragment:**

~~~kotlin
val buildFlavor = providers.gradleProperty("buildFlavor").orElse("local")

tasks.register("showBuildFlavor") {
    doLast {
        println("Build flavor: " + buildFlavor.get())
    }
}
~~~

Cùng chạy:

~~~bash
./gradlew showBuildFlavor
./gradlew showBuildFlavor -PbuildFlavor=ci
~~~

Với `buildFlavor=local` trong `gradle.properties`, kết quả body dòng log từ task custom sẽ có:

~~~text
Build flavor: local
~~~

Truyền `-PbuildFlavor=ci` trên CLI cho dòng:

~~~text
Build flavor: ci
~~~

Các log khác của Gradle có thể xuất hiện quanh dòng đó. Provider `orElse("local")` có giá trị mặc định nếu không có property. Cú pháp Groovy `def` khác Kotlin `val`, nhưng bản chất vẫn là `Provider<String>` từ Gradle API.

**Cảnh báo ngữ nghĩa:** Gradle `-PbuildFlavor=ci` là project property, không tự kích hoạt **Spring profile** `ci` khi chạy ứng dụng. Để bật profile Spring Boot, phải truyền cấu hình Spring runtime phù hợp (ví dụ tham số ứng dụng) qua `bootRun`/`java -jar` theo cách mà build đã thiết lập. Đừng nhầm “build environment property” với “Spring Environment profile”.

Với thông tin bí mật như password/token repository, tránh đặt hardcode trong `build.gradle`/`build.gradle.kts` hoặc commit `gradle.properties` chứa credential thật; dùng cơ chế secret được nhóm quản lý và không in chúng ra log.

## 12. Multi-project settings: `include`, project dependency và root/subproject

**Groovy `settings.gradle`:**

~~~groovy
rootProject.name = 'demo-multi'
include 'common', 'app'
~~~

**Kotlin `settings.gradle.kts`:**

~~~kotlin
rootProject.name = "demo-multi"
include("common", "app")
~~~

Hai settings định nghĩa các project `:common` và `:app` nếu thư mục/project descriptors tương ứng tồn tại. Không dùng `include("common", "app")` trong build.gradle để thay settings: Gradle xác lập build/project tree qua settings trước khi evaluate build scripts.

Nếu `app` cần dùng `common`:

**Groovy `app/build.gradle` fragment:**

~~~groovy
dependencies {
    implementation project(':common')
}
~~~

**Kotlin `app/build.gradle.kts` fragment:**

~~~kotlin
dependencies {
    implementation(project(":common"))
}
~~~

Ở đây `project(":common")` biểu diễn **project dependency**, không phải tọa độ module Maven trên Internet. `:common` cần được `settings` include và cung cấp variant/artifact phù hợp (thường qua Java/Java Library plugin). Một project chỉ là thư viện có thể dùng `java-library` mà không áp dụng Spring Boot plugin hoặc tạo Boot executable archive.

Ví dụ chạy task trên module app:

~~~bash
./gradlew :app:bootJar
./gradlew :app:build
~~~

Nếu build gốc chứa Groovy/Kotlin DSL trộn giữa các subproject thì cú pháp mỗi tệp phải phù hợp đuôi của chính tệp; task path `:app:bootJar` vẫn như nhau.

## 13. Version Catalog dùng chung cho cả hai DSL

Gradle có thể gom dependency/plugin coordinates vào `gradle/libs.versions.toml`. File TOML **không đổi cú pháp theo build script Groovy hay Kotlin**.

Ví dụ `gradle/libs.versions.toml`:

~~~toml
[versions]
springBoot = "3.3.13"
springDependencyManagement = "1.1.7"

[plugins]
springBoot = { id = "org.springframework.boot", version.ref = "springBoot" }
springDependencyManagement = { id = "io.spring.dependency-management", version.ref = "springDependencyManagement" }

[libraries]
commonsLang3 = { module = "org.apache.commons:commons-lang3", version = "3.14.0" }
~~~

Bản Groovy dùng aliases:

~~~groovy
plugins {
    id 'java'
    alias(libs.plugins.springBoot)
    alias(libs.plugins.springDependencyManagement)
}

dependencies {
    implementation libs.commonsLang3
}
~~~

Bản Kotlin:

~~~kotlin
plugins {
    id("java")
    alias(libs.plugins.springBoot)
    alias(libs.plugins.springDependencyManagement)
}

dependencies {
    implementation(libs.commonsLang3)
}
~~~

Đây là **fragments chỉ để diễn giải version catalog**, không phải thay thế nguyên hai build.gradle đầy đủ ở mục 3. Trên một project thật, cần giữ `repositories` và các dependency starter cùng Java/toolchain. Trong ví dụ, version của thư viện `commons-lang3` được khai báo tường minh để thể hiện catalog; trước khi đưa vào ứng dụng Spring Boot thật, phải kiểm tra phiên bản này có phù hợp với dependency constraints/BOM và nhu cầu mã nguồn hay không.

Version Catalog cung cấp **type-safe accessors** (như `libs.plugins.springBoot`), giúp IDE completion và tập trung declarations, nhưng **không ép phiên bản cuối cùng được chọn** trong mọi dependency conflict. Gradle vẫn giải quyết theo graph/constraints; kiểm tra bằng `dependencies` hoặc `dependencyInsight`.

Tránh hiểu rằng catalog khiến hai ngôn ngữ DSL giống hệt: cách gọi `implementation libs.commonsLang3` và `implementation(libs.commonsLang3)` vẫn khác nhau, còn tên accessors lấy từ alias trong TOML.

## 14. Task registration và tránh cấu hình quá sớm

Một tác vụ custom đơn giản:

**Groovy:**

~~~groovy
tasks.register('hello') {
    group = 'verification'
    description = 'In mot dong thong bao'
    doLast {
        println 'Hello Gradle'
    }
}
~~~

**Kotlin:**

~~~kotlin
tasks.register("hello") {
    group = "verification"
    description = "In mot dong thong bao"
    doLast {
        println("Hello Gradle")
    }
}
~~~

Khi chạy:

~~~bash
./gradlew hello
~~~

Dòng output do task tự in:

~~~text
Hello Gradle
~~~

Về Gradle API, `tasks.register` dùng lazy task registration; `tasks.named` lấy `TaskProvider` của task đã có; `configureEach` chỉ cấu hình matching tasks khi cần. Không nên đổi mọi lời gọi thành `tasks.create`/`tasks.getByName` chỉ để copy cú pháp Groovy sang Kotlin vì các phương thức eager có thể làm hiệu năng configuration xấu đi.

Nếu cần truy cập thuộc tính chuyên biệt của task, Kotlin phải có đúng generic/class. Ví dụ:

**Groovy:**

~~~groovy
tasks.named('jar') {
    archiveFileName = 'library.jar'
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<Jar>("jar") {
    archiveFileName.set("library.jar")
}
~~~

`Jar` là kiểu task Gradle Java plugin. Kotlin có thể viết đầy đủ `org.gradle.jvm.tasks.Jar` nếu imports không nhận diện; với Gradle Kotlin DSL thông dụng, kiểu `Jar` có sẵn trong default imports. Task `jar` phải tồn tại và cần đúng plugin.

## 15. Các lỗi phổ biến khi chuyển từ Groovy sang Kotlin DSL

| Biểu hiện | Gốc vấn đề | Cách sửa |
| --- | --- | --- |
| `Expecting an element` ở `id 'java'` | Copy cú pháp Groovy vào `.gradle.kts` | Viết `id("java")` |
| `Too many characters in a character literal` | Kotlin hiểu single quotes là `Char` (một ký tự) | Dùng double-quoted string như `"java"` |
| `Unresolved reference: implementation` | Plugin tạo configuration chưa sẵn hoặc script đặt sai chỗ | Apply Java/JVM plugin trong `plugins`, kiểm tra sync |
| `Unresolved reference: useJUnitPlatform` | `tasks.named("test")` chỉ nhìn thấy kiểu `Task` | Viết `tasks.named<Test>("test")` hoặc `tasks.withType<Test>()` |
| `Unresolved reference: bootJar` | Spring Boot plugin/Java plugin chưa áp dụng hoặc typed accessor chưa có | Kiểm tra plugin, dùng `tasks.named<BootJar>("bootJar")` đúng kiểu |
| `No value passed for parameter` | Kotlin yêu cầu method arguments và API cụ thể | Đọc Gradle Kotlin DSL API; thay Groovy named-arg syntax đúng cách |
| `Cannot set the value of read-only property` | Nhầm property/provider API hoặc setter không tồn tại | Dùng `.set(...)` với `Property<T>` hoặc API của plugin đúng phiên bản |
| `Could not find method implementation()` trong Groovy | Plugin tạo configuration chưa áp dụng hoặc dependencies block đặt sai | Kiểm tra Java plugin, cấu trúc script |
| `Plugin [id: ...] was not found` | Plugin repository/version sai, offline/proxy | Kiểm tra `pluginManagement.repositories` và wrapper |
| `Could not find ... artifact` | Dependency repository hoặc BOM/managed version thiếu | Kiểm tra `repositories`, dependencyManagement/BOM, `dependencyInsight` |
| JVM lỗi dù toolchain đặt Java 17 | JVM chạy Gradle khác JDK dùng compiler, hoặc toolchain chưa được phát hiện | Chạy `./gradlew --version`, `./gradlew javaToolchains` |
| IDE Groovy build chạy nhưng Kotlin import lỗi | Kotlin script được compile/type-check; plugin accessors/API cần type rõ | Đọc lỗi compile tại dòng .kts, sửa bằng Gradle typed API |
| Sau đổi DSL artifact/version thay đổi | Khi chuyển đổi đã sửa semantics, plugin/order/properties | So sánh plugins, dependencies, task graph và output cả hai bản |

**Không có quy tắc “chỉ thêm ngoặc và đổi single quotes thành double quotes” đủ cho mọi plugin.** Khi build dùng Groovy metaprogramming hoặc plugin tự tạo dynamic extension, cần tìm tài liệu Kotlin DSL của chính plugin đó hoặc viết typed configuration phù hợp. Tránh tùy tiện dùng Groovy bridge khi Gradle API đã có lựa chọn typed rõ ràng.

## 16. Kiểm chứng hai DSL cho cùng một yêu cầu build

Tạo hai thư mục riêng, mỗi thư mục chứa một cặp settings/build script ở mục 3 và cùng mã Java. Sử dụng **cùng Gradle wrapper version, JDK, Spring Boot plugin version và dependency repositories** trước khi so sánh.

### 16.1. Chẩn đoán cấu hình và tasks

~~~bash
./gradlew --version
./gradlew projects
./gradlew tasks --all
./gradlew javaToolchains
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

- `--version`: Gradle distribution và JVM đang chạy Gradle.
- `projects`: root và subprojects được include.
- `tasks --all`: các task có trong model, bao gồm `bootRun`/`bootJar` nếu plugin được áp dụng.
- `javaToolchains`: các JDK được Gradle phát hiện hoặc cấu hình.
- `dependencies`: dependency graph đã giải quyết theo configuration.
- `dependencyInsight`: lý do Gradle chọn một phiên bản module (ví dụ `spring-core`).

Nếu CLI không có `gradlew` do project chưa tạo wrapper, phải tạo/cấp wrapper theo quy trình thay vì coi tệp `.gradle` tự tạo wrapper. Với Windows, đổi sang `.\gradlew.bat`.

### 16.2. Chạy test, packaging và ứng dụng

~~~bash
./gradlew clean test
./gradlew bootJar
./gradlew build
./gradlew bootRun
~~~

Mỗi dòng minh họa một điểm kiểm tra; không bắt buộc chạy cả bốn tuần tự khi đã có bằng chứng tương ứng. `bootJar` tạo executable JAR nhưng không mặc nhiên chạy test; `build` thường gồm cả `assemble` và `check`. Khi chạy `bootRun`, gọi `/ping` để xác minh ứng dụng Spring Boot thực sự chạy.

Hai project Groovy/Kotlin DSL được coi là tương đương khi cùng input/environment và cùng loại task tạo ra **kết quả có ý nghĩa tương đương**, chứ không nhất thiết byte-for-byte JAR giống nhau do timestamp, metadata, cache hoặc thứ tự đóng gói. So sánh task graph, dependency versions, Java target và chức năng runtime.

### 16.3. Chuyển đổi trên repository đang có

Quy trình thực tế:

1. Ghi lại Gradle wrapper, JDK và lệnh build/CI đang dùng; giữ nguyên plugin/dependency versions.
2. Tạo bản sao hoặc branch an toàn trước khi đổi build script; không xóa file gốc khi chưa có build mới được xác minh.
3. Chuyển `settings.gradle` → `settings.gradle.kts` và `build.gradle` → `build.gradle.kts` theo từng block: plugins → repositories → dependencies → toolchain → tasks.
4. Với mỗi API Groovy dynamic, kiểm tra Kotlin type/generic tương ứng. Không suy diễn mọi `foo bar` đều chuyển được thành `foo("bar")`.
5. Chạy `./gradlew help` hoặc `./gradlew tasks` để kiểm tra script compile/configuration; sau đó `dependencies`/`dependencyInsight` và `build`.
6. So sánh task names, dependency graph, artifact names/type và kết quả test trước khi loại bỏ script cũ. Cập nhật CI/IDE nếu chúng đang tham chiếu trực tiếp tên file hoặc conventions của script.

Dùng `--stacktrace` khi gặp lỗi compile/configuration cần chi tiết; không cần mở rộng tới `--debug` ở mọi lần kiểm tra.

## 17. Bài tập thực hành

**Bài 1 — Chuyển cú pháp:** chuyển fragment Groovy sau sang Kotlin DSL và giải thích từng thay đổi.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Đáp án:**

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
tasks.named<Test>("test") {
    useJUnitPlatform()
}
~~~

Điều kiện: project đã apply Java/JVM plugin và Spring Boot dependency management/BOM để dependency được resolve. Thay đổi gồm cách gọi function, dấu nháy và khai báo kiểu `Test`; phạm vi dependency `implementation` không thay đổi.

**Bài 2 — Sửa lỗi Kotlin DSL:** vì sao đoạn sau sai?

~~~kotlin
plugins {
    id 'java'
}
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**Đáp án:** `id 'java'` và `implementation '...'` là Groovy syntax. Trong `.gradle.kts` phải dùng `id("java")` và `implementation("...")`; đồng thời phải cấu hình Spring Boot plugin/BOM hoặc version dependency để có build Spring Boot đầy đủ.

**Bài 3 — Toolchain:** tại sao `./gradlew --version` có thể báo JVM 21 trong khi `java.toolchain` yêu cầu Java 17?

**Đáp án:** Gradle daemon/client có thể chạy trên JVM 21, còn Java toolchain điều khiển compiler/test launcher của task theo cấu hình. Phải xem `./gradlew javaToolchains` và task log để biết Gradle đang dùng JDK nào.

**Bài 4 — Packaging:** build.gradle.kts có `bootJar` và `jar`. File nào dành cho `java -jar` khi có cả `demo-0.0.1-SNAPSHOT.jar` và `demo-0.0.1-SNAPSHOT-plain.jar`?

**Đáp án:** theo cấu hình Spring Boot Gradle Plugin 3.3 mặc định, output của `bootJar` thường là file không có classifier, còn `jar` thường tạo `-plain.jar`. Tuy nhiên vẫn phải xác minh output configuration, Boot archive structure và log trước khi publish.

**Bài 5 — Version Catalog:** giải thích vì sao `libs.commonsLang3` xuất hiện được trong cả `build.gradle` và `build.gradle.kts`.

**Đáp án:** Gradle sinh type-safe accessor từ alias trong `gradle/libs.versions.toml`. Hai DSL dùng cùng catalog và dependency coordinates; cú pháp gọi configuration khác nhau.

**Bài 6 — Gradle property so với Spring profile:** chạy `./gradlew bootRun -PbuildFlavor=dev` có tự làm `spring.profiles.active=dev`?

**Đáp án:** không. `buildFlavor` chỉ là Gradle project property; cần code build hoặc tham số JVM/application truyền cấu hình Spring runtime phù hợp thì Spring profile mới thay đổi.

**Tiêu chí hoàn thành:** bạn viết được hai cặp `settings.gradle`/`build.gradle` và `settings.gradle.kts`/`build.gradle.kts` tương đương; biết chuyển các block phổ biến; giải thích được vì sao Kotlin DSL cần typed `Test`/`BootJar` hoặc `Property.set`; kiểm chứng được task graph, dependency versions và executable Boot JAR.

## 18. Tài liệu chính thức

- Gradle Kotlin DSL Primer: https://docs.gradle.org/current/userguide/kotlin_dsl.html
- Gradle Migrating Build Logic from Groovy to Kotlin: https://docs.gradle.org/current/userguide/migrating_from_groovy_to_kotlin_dsl.html
- Gradle Version Catalogs: https://docs.gradle.org/current/userguide/version_catalogs.html
- Gradle Build Environment Configuration: https://docs.gradle.org/current/userguide/project_properties.html
- Spring Boot 3.3.13 Gradle Plugin — Getting Started: https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html
- Spring Boot Gradle Plugin — Managing Dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Spring Boot 3.3 Gradle Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html

Tài liệu Gradle “current” thay đổi theo phiên bản phát hành; khi dự án dùng Gradle wrapper cụ thể, tra đúng phiên bản của Gradle và Spring Boot plugin trước khi áp dụng API/syntax mới. **Chuyển Groovy DSL sang Kotlin DSL là chuyển cách biểu đạt cùng Gradle build model; hành vi cuối cùng phải được chứng minh bằng task, dependency và artifact đã thực thi.**
