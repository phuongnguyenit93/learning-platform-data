# Đánh giá Isolated Projects theo khả năng hỗ trợ của phiên bản Gradle đang sử dụng

## 1. Vấn đề cần giải quyết

Trong một Gradle multi-project build, các subprojects có thể phụ thuộc nhau về Java library, plugin và artifact. Tuy nhiên **phụ thuộc code** không đồng nghĩa với việc build script của một project phải trực tiếp đọc/ghi cấu hình mutable của project khác.

Một root `build.gradle` có kiểu:

~~~groovy
subprojects {
    apply plugin: 'java-library'
    tasks.withType(JavaCompile).configureEach {
        options.encoding = 'UTF-8'
    }
}
~~~

là ví dụ **cross-project configuration**: script từ root sửa trạng thái những project khác. Kiểu xây dựng này có thể chạy tuần tự, nhưng khó bảo đảm tính độc lập khi cấu hình nhiều projects cùng lúc.

**Isolated Projects** là tính năng Gradle dùng các ranh giới nghiêm ngặt đối với truy cập mutable state giữa projects/builds để cấu hình projects song song an toàn, giúp cải thiện **configuration phase**, đặc biệt ở large builds và IDE sync. Tính năng dựa vào **Configuration Cache** nhưng không phải Build Cache, không phải incremental compilation và không phải chỉ thêm `--parallel`.

Bài học thuộc nhóm **Hiệu năng build**, chủ đề **“Đánh giá Isolated Projects theo khả năng hỗ trợ của phiên bản sử dụng”**. Trọng tâm là **đánh giá có điều kiện**: xác định Gradle Wrapper version, kiểm feature lifecycle, các cờ/version requirements, plugin/IDE compatibility, constraints, benchmark và khả năng dùng trong môi trường thực tế. Không khuyến khích bật một feature incubating trên mọi CI/release mà chưa có bằng chứng tương thích.

### Các mốc và kết luận quan trọng

- **Gradle 9.7.0** (công bố tháng 8/2026) nâng Isolated Projects từ **experimental** lên **incubating**.
- Theo tài liệu **Gradle 9.9.0** được tham chiếu cho bài học (tháng 11/2026), tính năng vẫn **incubating** và mặc định **tắt**, chưa nên coi là giải pháp production universal.
- **Gradle 9.7+** có cờ `--isolated-projects` và property `org.gradle.isolated-projects=true`; có diagnostics mode `org.gradle.isolated-projects.diagnostics=true`.
- Các bản **trước 9.7** từng có property thử nghiệm `org.gradle.unsafe.isolated-projects=true`, nhưng **không được giả định** hỗ trợ cờ/diagnostics mới. Phải đối chiếu **versioned docs** của Gradle Wrapper thực tế.
- Bật Isolated Projects **tự bật Configuration Cache**. Tắt Configuration Cache tường minh cùng lúc là không hợp lệ.
- Lợi ích chủ yếu là **parallel project configuration** và, với tooling hỗ trợ, **IDE sync/model building**. Isolated Projects không tự làm JavaCompile hoặc JUnit tests thực thi nhanh hơn.
- Gradle khi feature còn incubating **không khuyến nghị dùng nó để sinh production artifacts**. Có thể khảo sát trên local/developer workflows; không dùng mode bỏ qua violations để release.
- Các dự án cùng dùng Gradle 9.7+ có thể khác nhau về compatibility do Android/Kotlin/third-party plugins, build logic riêng và IDE versions.

Sau bài, bạn sẽ biết cách kiểm phiên bản, phân loại API được phép/cấm, cấu hình thử trên demo Java 17, làm diagnostics, di trú build logic và lập báo cáo quyết định có dữ liệu đo.

## 2. Kiểm version thật của project trước khi bàn tính năng

**Gradle Wrapper** trong source repository quyết định distribution mà CI/developer dùng khi gọi `./gradlew`; lệnh `gradle --version` trên PATH có thể là Gradle version khác.

Linux/macOS:

~~~bash
./gradlew --version
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
~~~

Kiểm file:

~~~text
gradle/wrapper/gradle-wrapper.properties
~~~

Ví dụ nội dung của một Wrapper dùng Gradle 9.9.0:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
~~~

`distributionUrl` là một ví dụ về distribution đã được chọn, **không phải** lệnh buộc project của bạn nâng ngay lên version đó. Mọi nâng cấp cần kiểm Gradle compatibility, plugin support, JDK và CI trước.

### 2.1. Những dữ liệu cần ghi lại

| Thông tin | Tại sao quan trọng |
| --- | --- |
| Gradle Wrapper distribution (ví dụ 9.9.0) | Quyết định CLI flag, feature status, constraints |
| Gradle Daemon JVM | Gradle cần runtime phù hợp |
| Java toolchain | `JavaCompile`/`Test` có thể dùng JDK 17 độc lập Daemon JVM |
| Groovy DSL/Kotlin DSL | Ảnh hưởng cú pháp migration |
| Số subprojects | Quy mô configuration workload |
| Third-party plugins và versions | Có thể chưa hỗ trợ Isolated Projects |
| Included build `build-logic`/`buildSrc` | Có thể gây cache invalidation/coupling |
| Android Studio/IntelliJ IDEA version | IDE sync/model builder behavior |
| Configuration Cache hiện tại | Prerequisite cần đạt |
| CPU/worker count/RAM của máy | Ảnh hưởng parallel project configuration |
| Workflow cần tối ưu | `help`, unit test, CI, IDE sync hoặc publish |
| Chính sách production | Feature còn incubating, phải xem release risk |

### 2.2. Ma trận trạng thái theo dòng version

| Gradle version | Cách hiểu tính năng | Hành động đề xuất |
| --- | --- | --- |
| Version chưa có Isolated Projects | Không có tính năng để bật | Tập trung Configuration Cache, caching và nâng cấp có kiểm |
| Một số bản Gradle 8.x có preview | **Experimental/pre-alpha** và API/flags thay đổi mạnh | Chỉ đánh giá trong sandbox, đọc đúng tài liệu bản đó |
| Gradle 9.0–9.6 | Giai đoạn experimental | Không lấy cờ/tài liệu của 9.7+ áp máy móc |
| **Gradle 9.7+** | **Incubating** với cờ mới, diagnostics và constraints nghiêm hơn | Phù hợp đánh giá có kiểm, chưa đồng nghĩa production-ready |
| Gradle tương lai | Lifecycle/support có thể thay đổi | Kiểm release notes mới rồi đánh giá lại |

Cần phân biệt **Gradle hỗ trợ API của Isolated Projects** và **plugin của tổ chức hỗ trợ Isolated Projects**. Có flag hợp lệ không có nghĩa một plugin do bên thứ ba viết đã tuân mọi ranh giới.

### 2.3. Cách chọn versioned documentation

Dùng:

~~~text
https://docs.gradle.org/9.7.1/userguide/isolated_projects.html
https://docs.gradle.org/9.9.0/userguide/isolated_projects.html
~~~

theo version đang dùng, thay vì chỉ xem:

~~~text
https://docs.gradle.org/current/userguide/isolated_projects.html
~~~

Trang `current` có thể mô tả behavior mới mà Wrapper cũ chưa hỗ trợ. Với versions thử nghiệm, còn có các property `org.gradle.unsafe...` mà bản mới đã deprecated. Khi viết quyết định kiến trúc, ghi **ngày đọc tài liệu, Gradle version, plugin/IDE versions**.

---

## 3. Cơ chế: Isolated Projects tăng tốc phần nào của Gradle?

Một invocation có các giai đoạn:

~~~text
Initialization
     |
     v
Settings / project structure
     |
     v
Configuration
  +-- apply plugins
  +-- setup project models
  +-- register/configure tasks
  +-- resolve some configuration inputs
  +-- build task graph
     |
     v
Execution
  +-- compile Java
  +-- run JUnit tests
  +-- package files
  +-- publish, nếu task được chọn
~~~

Isolated Projects chủ yếu cải thiện **cấu hình từng project** bằng cách cho phép các project configuration units chạy song song, với điều kiện build logic của project này không trực tiếp đọc/ghi mutable state của project khác.

### 3.1. Các cơ chế thường bị nhầm lẫn

| Cơ chế | Công việc chính | Liên hệ Isolated Projects |
| --- | --- | --- |
| **Configuration Cache** | Tái dùng configured task graph để bỏ configuration ở cache hit | **Prerequisite** |
| **Isolated Projects** | Enforce ranh giới project/build để parallel configuration | Nội dung bài |
| **Build Cache** | Khôi phục task outputs theo declared inputs/cache key | Khác giai đoạn và mục tiêu |
| Up-to-date checks | Bỏ task action khi outputs/inputs không đổi | Không phải Isolated Projects |
| Incremental compilation | Giảm compilation work | Không phải Isolated Projects |
| Dependency cache | Tái dùng external dependencies đã tải | Không phải Isolated Projects |
| `--parallel` | Task parallelism trong các chế độ Gradle | Không tự bật project isolation |
| Configuration on Demand | Tìm cách bỏ cấu hình projects không cần | Khác, hiện bị bỏ qua khi Isolated Projects bật |
| Gradle Daemon | Tiết kiệm startup/hỗ trợ reuse JVM | Có thể dùng cùng lúc |
| IDE tooling model cache | Tái dùng một số IDE sync models tùy mode | Lợi ích liên quan nhưng theo support matrix |

Một build có thể đã **Configuration Cache hit** nên gần như không cấu hình lại, lúc đó việc bật Isolated Projects không làm phần configuration nhanh thêm đáng kể. Thử nghiệm hiệu năng phải tách **cache miss/cold configuration** và **cache hit/warm configuration**.

### 3.2. Không phải mọi thứ đều parallel

Theo tài liệu Gradle 9.9, trong task invocation:

- Project configurations có thể chạy song song.
- Task/work graph discovery có những phần **tuần tự**.
- Việc store work graph có thể parallel hơn.
- Execution phase **không được tăng tốc trực tiếp** bởi Isolated Projects.
- Projects con cần parent project hoàn thành configuration trước khi bắt đầu.
- Hiện tại **tất cả projects vẫn được cấu hình** khi configuration chạy; chưa tự động bỏ các subprojects không cần.
- Included build changes có thể invalidate cached results rộng.
- Cấu hình song song có thể **tốn thêm RAM** và tăng contention.

### 3.3. Tính khả năng cải thiện theo phần thời gian

Một mô hình đơn giản là:

\[
S_{\text{total}} \approx \frac{1}{(1-p) + p/S_{\text{config}}}
\]

Trong đó `p` là tỷ lệ thời gian của phần có thể cải thiện và `S_config` là speedup của phần đó.

Nếu chỉ 40% thời gian invocation có thể cải thiện và phần đó nhanh gấp đôi:

\[
S_{\text{total}} \approx \frac{1}{0.6+0.4/2}=1.25
\]

Đây là **minh họa lý thuyết**, không phải benchmark thực tế trên Gradle project. Phần task execution, downloads, test duration hoặc IDE model building có thể chi phối tổng thời gian.

---

## 4. Ranh giới Isolated Projects: điều gì được phép, điều gì bị cấm?

Isolated Projects áp constraint lên **project-scoped vs build-scoped mutable state** trong configuration.

Những nhóm chính:

1. **Cross-project access:** Project `:cli` đọc/ghi mutable data của `:service` hoặc root `:`.
2. **Project-to-build access:** project script đụng build-scoped mutable state trên `gradle`/listeners/extensions.
3. **Cross-build access:** một included build đụng mutable state build khác.
4. **Build-to-project access:** settings/build callback capture shared mutable state rồi sử dụng không an toàn khi project configurations chạy song song.

### 4.1. Ví dụ cross-project sai

Trong `cli/build.gradle`:

~~~groovy
plugins {
    id 'application'
}

// VI PHẠM: :cli đọc mutable property "version" của root project.
def versionFromRoot = rootProject.version

// VI PHẠM: :cli truy cập tasks container của :core.
def coreTasks = project(':core').tasks
~~~

`rootProject.version` là mutable state của project khác, dù chỉ đọc. `project(':core').tasks` cũng là mutable model. Dưới Isolated Projects 9.7+ Gradle có thể fail và báo problem, ví dụ thông điệp rút gọn:

~~~text
Project ':cli' cannot access 'Project.version'
functionality on another project ':'
~~~

Thông điệp chính xác còn tùy version/path; cần xem **Configuration Cache HTML problems report**.

### 4.2. Truy cập immutable và declarative dependency vẫn hợp lệ

| API/data | Đánh giá |
| --- | --- |
| `project(':core').name`/`path` | Immutable identity; có những getter được phép, nhưng hạn chế lookup không cần thiết |
| `project(':core').projectDir` | Immutable path theo constraints hiện hành |
| `project(':core').version`/`group` | Mutable; **không đọc** |
| `project(':core').tasks` | Mutable; **không đọc** |
| `project(':core').configurations`/`extensions`/`plugins` | Mutable; **không đọc** |
| `rootProject.layout`/`providers` | Mutable project-scoped services; không lấy từ project khác |
| `project.isolated.rootProject.projectDirectory` | Safe immutable view được Gradle document |
| `implementation project(':core')` | **Declarative project dependency bình thường**, không phải violation |

**Rất quan trọng:** `implementation project(':core')` là cách Gradle tiêu chuẩn để khai API/artifact dependency giữa subprojects. Isolated Projects không cấm nó và không yêu cầu bạn đổi tất cả `project(...)` dependencies sang external Maven coordinates.

### 4.3. Root cross-project configuration là anti-pattern

Đoạn code sau trong root script dễ gây Isolated Projects violations:

~~~groovy
subprojects {
    apply plugin: 'java-library'
    group = 'org.example.academy'

    tasks.withType(JavaCompile).configureEach {
        options.encoding = 'UTF-8'
    }
}
~~~

Root script tạo/mutate plugin/Group/Task model của child projects. Nó có thể vận hành tuần tự nhưng không an toàn cho parallel project configuration.

**Cách thay:** mỗi subproject áp dụng convention plugin do nhóm xây dựng, hoặc cấu hình project riêng. Mục tiêu là **chia sẻ chính sách**, không chia sẻ quyền tùy tiện sửa mutable state của project khác.

### 4.4. Không phải mọi `Gradle` API đều bị cấm

Một số API truy cập mutable build scope như `gradle.extensions`, `gradle.beforeProject`/`afterProject` hoặc đăng ký listeners từ project script có thể vi phạm constraints. Tuy nhiên đọc một số immutable data như `gradle.gradleVersion` có thể được phép.

Không viết quy tắc sai kiểu “không được gọi bất cứ `gradle` API nào”. Cần kiểm **API cụ thể, scope cụ thể và version**. Với lifecycle callbacks, Gradle cung cấp `gradle.lifecycle.beforeProject`/`afterProject` theo pattern **đăng ký từ settings**, không dùng project script đăng ký build listener tùy ý.

---

## 5. Cách bật theo version và điều kiện tiên quyết

### 5.1. Gradle 9.7+ — dùng cờ hiện đại

Bật cho một invocation:

~~~bash
./gradlew help --isolated-projects
~~~

Bật cho một module task:

~~~bash
./gradlew :cli:test --isolated-projects
~~~

Nếu cần cho IDE sync, đặt property:

~~~properties
org.gradle.isolated-projects=true
~~~

trong `gradle.properties` theo chính sách rollout. Vì property file của repository thường được commit, đừng thêm nó vào shared build trước khi mọi người đồng ý và đánh giá correctness. Nên thử local workspace/CI experiment lane.

Isolated Projects tự kích hoạt **Configuration Cache**, do đó không thể cố dùng:

~~~properties
org.gradle.isolated-projects=true
org.gradle.configuration-cache=false
~~~

đồng thời. Đây không phải hai tính năng độc lập có thể ghép trái ngược.

### 5.2. Gradle trước 9.7 — tránh lẫn cờ mới và cờ thử nghiệm

Có các bản trước đây sử dụng property legacy:

~~~properties
org.gradle.unsafe.isolated-projects=true
~~~

Dòng Gradle 9.7+ vẫn chấp nhận legacy alias nhưng đã deprecated; tên mới được ưu tiên. **Trên bản trước 9.7, phải đọc tài liệu đúng bản**. Một số CLI option như `--isolated-projects` hoặc diagnostics mode hiện đại có thể chưa hỗ trợ.

Nếu Gradle báo:

~~~text
Unknown command-line option '--isolated-projects'
~~~

hãy kiểm `./gradlew --version` trước. Không tự kết luận source Java hoặc Gradle project đã sai.

### 5.3. Gradle 9.7+ có strict violations

Theo tài liệu 9.7+, khi vi phạm Isolated Projects constraint, Gradle mặc định **fail**. Cờ Configuration Cache cũ `--configuration-cache-problems=warn` **không hạ các Isolated Projects violations thành warnings**. Để khảo sát, sử dụng Diagnostics mode thay vì biến warning thành “thành công”.

### 5.4. Cần hoàn tất Configuration Cache compatibility trước

Trước:

~~~bash
./gradlew help --configuration-cache --info
./gradlew help --configuration-cache --info
~~~

Sau đó thực hiện workflow thật:

~~~bash
./gradlew :cli:test --configuration-cache --info
./gradlew :cli:test --configuration-cache --info
~~~

Nếu build có task action đọc Project, unsupported listener/captured Gradle mutable model hoặc configuration-time side effects không phù hợp, phải giải quyết trước. Configuration Cache pass **chưa chắc** Isolated Projects pass, vì cross-project mutable configuration rules nghiêm hơn.

---

## 6. Demo Java 17 multi-project tương thích về kiến trúc

Demo dùng **ba subprojects**:

~~~text
isolated-lab/
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── core/
│   ├── build.gradle
│   └── src/
│       ├── main/java/demo/core/NameNormalizer.java
│       └── test/java/demo/core/NameNormalizerTest.java
├── service/
│   ├── build.gradle
│   └── src/
│       ├── main/java/demo/service/GreetingService.java
│       └── test/java/demo/service/GreetingServiceTest.java
└── cli/
    ├── build.gradle
    └── src/
        ├── main/java/demo/cli/Main.java
        └── test/java/demo/cli/CliSmokeTest.java
~~~

Gradle Wrapper files phải được sinh thật bằng `gradle wrapper` hoặc phân phối Wrapper đáng tin, **không phải file rỗng**. Cần Gradle 9.7+ để dùng `--isolated-projects` theo lệnh hiện đại và Java 17 toolchain để biên dịch source. JUnit dependencies lần đầu có thể cần mạng/Maven Central.

### 6.1. `settings.gradle`

~~~groovy
rootProject.name = 'isolated-lab'
include 'core', 'service', 'cli'
~~~

Đây là multi-project structure. Không có `subprojects { ... }` root script sửa models của các child projects.

Dependency graph:

~~~text
:cli  -->  :service  -->  :core
~~~

Mũi tên nghĩa project bên trái **phụ thuộc** module bên phải. Các dependency declarations thực tế nằm ở build scripts.

### 6.2. `core/build.gradle`

~~~groovy
plugins {
    id 'java-library'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`core` tự áp Java Library plugin, khai toolchain và JUnit. Không đọc mutable data của root hoặc service/cli.

### 6.3. `core/src/main/java/demo/core/NameNormalizer.java`

~~~java
package demo.core;

public final class NameNormalizer {
    private NameNormalizer() {
    }

    public static String normalize(String input) {
        if (input == null) {
            return "bạn";
        }

        String name = input.strip();
        return name.isEmpty() ? "bạn" : name;
    }
}
~~~

Java 17 hỗ trợ `String.strip()`. Hàm xử lý tên rỗng/null, không cần external production dependencies.

### 6.4. `core/src/test/java/demo/core/NameNormalizerTest.java`

~~~java
package demo.core;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class NameNormalizerTest {
    @Test
    void trimsWhitespace() {
        assertEquals("Linh", NameNormalizer.normalize(" Linh "));
    }

    @Test
    void defaultsOnBlank() {
        assertEquals("bạn", NameNormalizer.normalize("   "));
    }

    @Test
    void defaultsOnNull() {
        assertEquals("bạn", NameNormalizer.normalize(null));
    }
}
~~~

Ba JUnit Jupiter tests thuộc module core.

### 6.5. `service/build.gradle`

~~~groovy
plugins {
    id 'java-library'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

dependencies {
    implementation project(':core')

    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`implementation project(':core')` là **declarative project dependency**, nên Gradle quản lý classpath/artifact producers đúng cách. Nó không đồng nghĩa service đang đọc `project(':core').tasks` hay `project(':core').version`.

### 6.6. `service/src/main/java/demo/service/GreetingService.java`

~~~java
package demo.service;

import demo.core.NameNormalizer;

public final class GreetingService {
    public String greet(String rawName) {
        return "Xin chào, " + NameNormalizer.normalize(rawName) + "!";
    }
}
~~~

Public API service chỉ dùng `String`, còn core là internal implementation dependency.

### 6.7. `service/src/test/java/demo/service/GreetingServiceTest.java`

~~~java
package demo.service;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GreetingServiceTest {
    private final GreetingService service = new GreetingService();

    @Test
    void greetsNamedUser() {
        assertEquals("Xin chào, Mai!", service.greet(" Mai "));
    }

    @Test
    void greetsGuest() {
        assertEquals("Xin chào, bạn!", service.greet(null));
    }
}
~~~

Service có hai JUnit test methods.

### 6.8. `cli/build.gradle`

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

dependencies {
    implementation project(':service')

    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}

application {
    mainClass = 'demo.cli.Main'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

CLI project khai dependency tới service. Service runtime variant có dependency core; không cần root script ép `cli` đọc configurations/tasks của upstream project.

### 6.9. `cli/src/main/java/demo/cli/Main.java`

~~~java
package demo.cli;

import demo.service.GreetingService;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String user = args.length == 0 ? "Gradle" : args[0];
        System.out.println(new GreetingService().greet(user));
    }
}
~~~

### 6.10. `cli/src/test/java/demo/cli/CliSmokeTest.java`

~~~java
package demo.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;

import demo.service.GreetingService;
import org.junit.jupiter.api.Test;

class CliSmokeTest {
    @Test
    void canCallService() {
        assertEquals(
            "Xin chào, Linh!",
            new GreetingService().greet(" Linh ")
        );
    }
}
~~~

CLI có một test. Tổng số methods trong ba modules là **6**.

### 6.11. Chạy baseline không Isolated Projects

Từ root:

~~~bash
./gradlew :core:test
./gradlew :service:test
./gradlew :cli:test
./gradlew test
./gradlew :cli:run --args="Linh"
~~~

Khi JDK/JUnit resolve và source đúng, root `test` chạy sáu methods. Java main của command cuối in:

~~~text
Xin chào, Linh!
~~~

Không truyền args:

~~~bash
./gradlew :cli:run
~~~

Java stdout:

~~~text
Xin chào, Gradle!
~~~

**Đây là expected outputs của demo**, không phải kết quả đã chạy trên hệ thống của người học. Build tool outputs như task progress/BUILD SUCCESSFUL xuất hiện ngoài stdout của Java main.

### 6.12. Chạy cùng tasks với Isolated Projects (Gradle 9.7+)

~~~bash
./gradlew help --isolated-projects
./gradlew :core:test --isolated-projects
./gradlew :service:test --isolated-projects
./gradlew :cli:test --isolated-projects
./gradlew test --isolated-projects
./gradlew :cli:run --args="Linh" --isolated-projects
~~~

Kỳ vọng chức năng Java/JUnit giữ nguyên khi build logic tuân constraints và plugin versions tương thích. Nếu command báo Isolated Projects violation, xem report. Nếu báo unknown flag, kiểm Wrapper version.

Đừng dùng một demo ba modules để suy tốc độ cho codebase 500 modules: với dự án nhỏ, overhead parallelization có thể lớn hơn lợi ích.

### 6.13. Kiểm riêng mã Java 17 bằng javac/java

Trên Linux/macOS, từ root:

~~~bash
mkdir -p manual/core manual/service manual/cli

javac -encoding UTF-8 \
    -d manual/core \
    core/src/main/java/demo/core/NameNormalizer.java

javac -encoding UTF-8 \
    -cp manual/core \
    -d manual/service \
    service/src/main/java/demo/service/GreetingService.java

javac -encoding UTF-8 \
    -cp "manual/core:manual/service" \
    -d manual/cli \
    cli/src/main/java/demo/cli/Main.java

java -cp "manual/core:manual/service:manual/cli" \
    demo.cli.Main Linh
~~~

Stdout:

~~~text
Xin chào, Linh!
~~~

Lệnh này kiểm tính runnable của Java source và dependency classpath, **không chạy Gradle**. Nó không thể chứng minh Isolated Projects compatibility. Trên Windows dùng classpath separator `;` thay `:`, và dùng PowerShell continuation phù hợp.

---

## 7. Thử tạo một violation — chỉ trong bản sao để học

Sau khi lưu demo đúng ở trên, thử **trên branch/worktree riêng** thêm vào `cli/build.gradle`:

~~~groovy
// Anti-pattern; phải xóa sau thí nghiệm.
def rootReleaseVersion = rootProject.version
println('Root version: ' + rootReleaseVersion)
~~~

Chạy:

~~~bash
./gradlew help --isolated-projects
~~~

Trong Gradle 9.7+ Isolated Projects, build có thể fail do project `:cli` đọc mutable `version` của root `:`. Violation là **cross-project access**, không phải Java source error.

### 7.1. Sửa đúng: project-local input thay vì root Project

Đặt giá trị chung vào `gradle.properties` theo chính sách build (ví dụ trích đoạn):

~~~properties
libraryVersion=1.2.3
libraryGroup=org.example.academy
~~~

Trong **mỗi module cần tọa độ publish**:

~~~groovy
group = providers.gradleProperty('libraryGroup').get()
version = providers.gradleProperty('libraryVersion').get()
~~~

Values đến từ Gradle property model ở scope của project đang cấu hình, không truy cập `rootProject.version`. Đây là **mẫu mở rộng**, không bắt buộc cho demo không publish; modules release độc lập có thể dùng version sources riêng.

### 7.2. Không sửa bằng cách chuyển sang Project khác

Thay `rootProject.version` bằng:

~~~groovy
def otherVersion = project(':core').version
~~~

vẫn là cross-project mutable state read. Cần thay **cách chia sẻ cấu hình**, không thay project bị đọc.

### 7.3. Dùng `IsolatedProject` khi thật sự chỉ cần immutable data

Gradle cung cấp safe view `IsolatedProject` để đọc một số immutable project data:

~~~groovy
def rootDirectory = project.isolated.rootProject.projectDirectory
~~~

Đây là trích đoạn configuration theo tài liệu Gradle hiện hành. Không thể dùng safe view để tùy ý lấy root tasks, group hay version: chính **giới hạn dữ liệu** của IsolatedProject là mục đích thiết kế.

### 7.4. Project dependency declarations vẫn an toàn

Đây là khai báo bình thường:

~~~groovy
dependencies {
    implementation project(':service')
}
~~~

Nó khác việc làm:

~~~groovy
// Anti-pattern:
def serviceClasspath =
    project(':service').configurations.runtimeClasspath
~~~

Cách thứ hai đọc mutable configuration container của project khác. Đối với dependency, hãy dựa trên variant-aware project dependency model và để Gradle tự chuẩn bị producer outputs.

---

## 8. Chuyển cross-project root conventions sang convention plugins

Một nguồn violations phổ biến là root `subprojects { }` hoặc `allprojects { }` can thiệp mutable state của các modules. Khi chia sẻ build logic lâu dài, **convention plugins** là lựa chọn phù hợp hơn.

### 8.1. Mô hình trước và sau

**Trước**:

~~~groovy
// Root build.gradle: cross-project mutation.
subprojects {
    apply plugin: 'java-library'
    tasks.withType(JavaCompile).configureEach {
        options.encoding = 'UTF-8'
    }
}
~~~

**Sau**: mỗi project tự apply một plugin quy ước:

~~~groovy
// core/build.gradle — trích đoạn.
plugins {
    id 'java-library'
    id 'demo.java-conventions'
}
~~~

Plugin `demo.java-conventions` cấu hình **chính Project mà nó được apply**; không cần root đi sửa tất cả task containers khác.

### 8.2. Bộ khung build-logic included build

Cấu trúc:

~~~text
isolated-lab/
├── settings.gradle
├── build-logic/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/groovy/demo.java-conventions.gradle
├── core/build.gradle
├── service/build.gradle
└── cli/build.gradle
~~~

Root `settings.gradle` dạng mở rộng:

~~~groovy
pluginManagement {
    includeBuild('build-logic')
}

rootProject.name = 'isolated-lab'
include 'core', 'service', 'cli'
~~~

`build-logic/settings.gradle`:

~~~groovy
rootProject.name = 'build-logic'
~~~

`build-logic/build.gradle`:

~~~groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}
~~~

`build-logic/src/main/groovy/demo.java-conventions.gradle`:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

Một subproject apply:

~~~groovy
plugins {
    id 'java-library'
    id 'demo.java-conventions'
}
~~~

Đây là **mẫu migration**, không dán song song lên bộ demo đã có cùng cấu hình mà chưa loại trùng. JUnit dependencies và repositories vẫn cần khai theo mô hình tổ chức. Khi nhiều module cần plugins khác nhau, tách `java-library-conventions` và `application-conventions` thay vì ép library thành application.

### 8.3. Convention plugin không tự bảo đảm tương thích

Ngay cả khi logic nằm trong plugin, đoạn sau vẫn nguy hiểm:

~~~groovy
// Anti-pattern trong plugin/build script:
def other = project.project(':core').tasks
~~~

Tính cô lập đến từ **hành vi API**, không chỉ từ file extension hoặc vị trí build-logic. Cần chạy diagnostics cả với custom convention plugins và third-party plugins.

---

## 9. Settings lifecycle callbacks và giới hạn resolution

Gradle có `gradle.lifecycle.beforeProject`/`afterProject` giúp triển khai các callbacks có ranh giới state phù hợp hơn khi cần cấu hình nhiều projects từ settings.

Ví dụ **trích đoạn Gradle 9.7+** trong `settings.gradle`:

~~~groovy
gradle.lifecycle.beforeProject {
    group = 'org.example.academy'
}
~~~

Callback cấu hình chính target project đang được Gradle đưa vào, không capture root mutable Project để thay đổi child state. Tuy nhiên convention plugin per module thường dễ hiểu và có owner rõ hơn khi config là Java/quality policy.

### 9.1. Một bẫy: lifecycle callback không tự resolve lazy plugins

Nếu plugin `demo.java-conventions` được cung cấp từ:

~~~groovy
pluginManagement {
    includeBuild('build-logic')
}
~~~

thì một callback `beforeProject` đăng ký trực tiếp từ settings **không tự resolve classpath của plugin đó**:

~~~groovy
// Có thể không hoạt động nếu plugin classpath chưa được resolve:
gradle.lifecycle.beforeProject {
    apply plugin: 'demo.java-conventions'
}
~~~

Theo tài liệu Gradle, hướng giải quyết:

- Apply plugin rõ qua `plugins { id 'demo.java-conventions' }` trong subproject; **đơn giản nhất**.
- Đăng ký callback từ **settings convention plugin** đã có plugin classpath.
- Hoặc pre-resolve plugin trong settings `plugins { id '...' apply false }` theo versioned docs, sau đó mới apply trong callback.

Đừng vội chuyển convention plugins sang buildSrc chỉ để né một limitation nếu included build-logic đã là kiến trúc phù hợp.

### 9.2. `IsolatedProject` là “safe view”, không phải quyền quản trị xuyên project

Nếu cần root project directory:

~~~groovy
gradle.lifecycle.beforeProject {
    def rootDirView =
        project.isolated.rootProject.projectDirectory
    println('Root directory: ' + rootDirView)
}
~~~

Đây là đoạn tham khảo configuration; nó chỉ đọc immutable path. Không biến thành `rootProject.version` hoặc `rootProject.tasks` vì các property đó mutable.

---

## 10. Diagnostics mode: tìm incompatibilities theo version

### 10.1. Lệnh trên Gradle 9.7+

~~~bash
./gradlew help \
    --isolated-projects \
    -Dorg.gradle.isolated-projects.diagnostics=true
~~~

Windows:

~~~powershell
.\gradlew.bat help --isolated-projects -Dorg.gradle.isolated-projects.diagnostics=true
~~~

Diagnostics mode cấu hình projects **tuần tự** để liệt kê nhiều violations theo thứ tự dễ tái hiện. Nó không phải một cách bật performance tối đa; cấu hình tuần tự và một số optimizations bị tắt để có báo cáo đầy đủ. **Không benchmark speedup bằng diagnostics mode**.

### 10.2. Quét nhiều workflows

~~~bash
./gradlew help --isolated-projects \
    -Dorg.gradle.isolated-projects.diagnostics=true

./gradlew :core:test --isolated-projects \
    -Dorg.gradle.isolated-projects.diagnostics=true

./gradlew :cli:test --isolated-projects \
    -Dorg.gradle.isolated-projects.diagnostics=true

./gradlew test --isolated-projects \
    -Dorg.gradle.isolated-projects.diagnostics=true
~~~

Đọc **Configuration Cache HTML problems report** được Gradle dẫn trong output. Nếu chỉ `help` không báo violation, vẫn cần test JavaCompile/JUnit/IDE sync vì lazy configuration hoặc plugin-specific build logic có thể chưa được kích hoạt.

### 10.3. Quy trình khắc phục một violation

1. Ghi lại Wrapper version, plugin versions, JDK, task path.
2. Đọc report, tìm project/build scope và dòng build script/plugin.
3. Phân loại cross-project, project-to-build, cross-build hoặc callback shared state.
4. Nếu do custom root config, chuyển sang convention plugin.
5. Nếu do đọc root/group/version, dùng explicit Gradle properties/providers hoặc safe immutable view.
6. Nếu do vendor plugin, tìm bản hỗ trợ hoặc báo bug có minimal reproducer.
7. Test lại diagnostics với workflow vừa lỗi.
8. Khi hết violations, chạy Isolated Projects mode chuẩn **không diagnostics** để kiểm correctness và performance.
9. So outputs với baseline không bật feature.
10. Ghi kết luận/owner/next version để follow-up.

**Một report pass không chứng minh mọi khả năng build logic đã được kích hoạt.** Bất kỳ plugin cấu hình lazy nào cũng có thể chỉ bộc lộ lỗi ở task/IDE model khác.

### 10.4. Không dùng warning mode cũ như migration solution

Trên 9.7+, `--configuration-cache-problems=warn` không tự hạ Isolated Projects violations. Mode dành cho migration là **diagnostics**, không phải “bỏ qua lỗi để xanh CI”.

### 10.5. Chế độ nguy hiểm chỉ dùng để ước lượng, tuyệt đối không dùng release

Một tùy chọn trên 9.7+:

~~~bash
./gradlew help --isolated-projects \
    -Dorg.gradle.isolated-projects.dangerously-ignore-problems=true
~~~

cho phép **tạm bỏ qua một số violations** để ước lượng performance trước khi sửa toàn bộ build logic. Gradle cảnh báo outputs có thể **không đáng tin**, và concurrency errors vẫn có thể làm build fail.

Không commit:

~~~properties
org.gradle.isolated-projects.dangerously-ignore-problems=true
~~~

như policy dài hạn. Không tạo/publish production artifacts, deploy, sign hoặc release trong mode này; nếu bỏ qua violations, không dùng `BUILD SUCCESSFUL` làm bằng chứng correctness.

---

## 11. IDE sync khác CLI tasks

Isolated Projects được thiết kế có lợi cho large builds và IDE tooling models. Tuy nhiên IDE import/sync không phải cùng code path với `./gradlew help`.

### 11.1. Mốc trong tài liệu Gradle 9.9

Tài liệu hiện hành đề cập parallel tooling model building có thể được kích hoạt tự động với:

- Android Studio **Electric Eel (2022.1.1)** trở lên.
- IntelliJ IDEA **2026.1.1** trở lên.

Ở một số IntelliJ versions trước đó, có thể cần tùy chọn **Enable parallel Gradle model fetching**. Những mốc này là thông tin từ docs của một Gradle version, **không thay thế** test IDE+plugin+Gradle thực tế.

### 11.2. Để IDE thấy feature, dùng property file

Một CLI run:

~~~bash
./gradlew help --isolated-projects
~~~

không có nghĩa IDE sync cũng bật Isolated Projects. Theo docs, IDE sync cần:

~~~properties
org.gradle.isolated-projects=true
~~~

trong `gradle.properties`. Nên thử ở workspace riêng, tránh commit vào shared repository khi chưa có approval/policy. Nếu cần rollback, xóa dòng hoặc đặt false khi version hỗ trợ.

### 11.3. Chỉ số cần đo IDE

| Loại đo | Tại sao |
| --- | --- |
| First/fresh import | Giá trị khi dựng mô hình lần đầu |
| Warm sync | Có thể tái sử dụng tooling models |
| Sync sau sửa build script | Kiểm invalidation/configuration |
| Sync sau đổi included build-logic | Kiểm cache invalidation rộng |
| IDE CPU/RAM | Parallel model building có thể tăng áp lực RAM |
| Số violations | Không được bỏ qua |
| Kết quả source sets/dependencies | Phải đúng so với baseline |
| Loop/re-sync warnings | Bộc lộ compatibility bugs |
| Gradle/IDE/plugin versions | Cần để tái hiện |

Không lấy benchmark được Gradle team công bố rồi gán như tốc độ chắc chắn của mọi dự án. Số modules, logic configuration, disk/RAM, Gradle version và IDE tooling model requests đều ảnh hưởng.

---

## 12. Benchmark Isolated Projects có công bằng không?

### 12.1. So với Configuration Cache baseline, không so với một mode yếu hơn

Trên Gradle 9.7+:

**Baseline A: có Configuration Cache, không Isolated Projects:**

~~~bash
./gradlew help --configuration-cache \
    --no-isolated-projects --profile
~~~

**Thử nghiệm B: bật Isolated Projects:**

~~~bash
./gradlew help --isolated-projects --profile
~~~

`--profile` tạo report thời gian Gradle; `--scan`/Develocity có timeline chi tiết hơn nếu policy tổ chức cho phép. Cần so cùng version, máy, Daemon, plugin, source, task selection, cache states và measurement method.

### 12.2. Cold/miss và warm/hit là hai tình huống khác nhau

- **Configuration Cache miss:** Gradle phải cấu hình lại projects. Đây là nơi Isolated Projects có cơ hội tăng tốc.
- **Configuration Cache hit:** Gradle khôi phục state, bỏ phần cấu hình. Bật Isolated Projects có thể không thêm khác biệt lớn.
- **Task execution:** vẫn chịu tác động Build Cache, up-to-date checks, JUnit runtime và I/O. Không quy mọi total time difference cho Isolated Projects.

Không dùng `--rerun-tasks` để tuyên bố đã ép configuration miss: nó ảnh hưởng task execution, không bảo đảm configuration inputs thay đổi. Nếu thiết kế benchmark cần miss có kiểm soát, ghi rõ fixture/input nào được thay và làm như nhau cho hai mode.

### 12.3. Template số liệu cần tự điền sau khi chạy

| Workflow | Chế độ | Config median | Total median | p95 | RAM peak | Violations |
| --- | --- | --- | --- | --- | --- | --- |
| `help`, cache miss | Baseline CC | Đo thực tế | Đo thực tế | Đo | Đo | 0 |
| `help`, cache miss | Isolated Projects | Đo thực tế | Đo thực tế | Đo | Đo | 0 |
| `:cli:test`, cache miss | Baseline CC | Đo thực tế | Đo thực tế | Đo | Đo | 0 |
| `:cli:test`, cache miss | Isolated Projects | Đo thực tế | Đo thực tế | Đo | Đo | 0 |
| IDE sync sau build edit | Baseline | Đo thực tế | Đo thực tế | Đo | Đo | 0 |
| IDE sync sau build edit | Isolated Projects | Đo thực tế | Đo thực tế | Đo | Đo | 0 |

**Không có số liệu đo giả trong bài.** Tất cả ô “Đo thực tế” là dữ liệu cần thu từ project của người học. Chạy nhiều vòng, tính median/p95 và ghi cache-hit ratio để tránh so sánh sai.

### 12.4. Những gì giới hạn speedup

Theo tài liệu hiện hành:

1. Tất cả projects vẫn được cấu hình khi cần cấu hình.
2. Child project cần parent project configured trước.
3. Work graph discovery có thể là bottleneck tuần tự, đặc biệt root selector `check`/`test` nhiều modules.
4. Project configuration parallelism bị giới hạn bởi `org.gradle.workers.max`.
5. Parallelism dùng thêm memory, có thể tăng GC/CPU contention.
6. Included build changes có thể invalidate nhiều cached entries.
7. IDE model caching không phải remote cache dùng chung mọi máy.
8. Configuration Cache hit vốn bỏ configuration, nên lợi ích còn ít.
9. Feature mới có overhead và plugin compatibility constraints.
10. Cấu hình đơn giản ở ít module có thể không đo ra lợi ích đáng kể.

### 12.5. `--parallel`, workers và Configuration on Demand

Cờ `--parallel` trước đây liên quan task execution. Khi Isolated Projects bật ở Gradle hiện hành, `--parallel` **bị bỏ qua** và không tự tạo thêm parallel project configuration speedup. `org.gradle.workers.max` mới là một giới hạn quan trọng của số work units có thể chạy cùng lúc.

Ví dụ:

~~~properties
org.gradle.workers.max=4
~~~

là giới hạn bốn workers cho Gradle, không đồng nghĩa luôn có bốn projects cấu hình thực sự đồng thời. Parent ordering, plugin locks và RAM vẫn ảnh hưởng.

Configuration on Demand cũng **bị bỏ qua** khi Isolated Projects bật theo docs hiện hành: nó không tự loại bỏ configuration của modules không cần. Đừng nhầm parallel configuration với project configuration avoidance.

---

## 13. Thay đổi hành vi theo Gradle 9.x: parent project property lookup

Trước đây một số Groovy DSL property lookups có thể tìm implicit property/method trên parent project. Với Isolated Projects, Gradle không làm lookup ngầm này theo cách đó. Tài liệu đề cập deprecation của hành vi cũ từ Gradle 9.6.

Ví dụ:

~~~groovy
def endpoint = findProperty('apiEndpoint')
~~~

có thể thấy kết quả khác tùy property được định nghĩa từ đâu và Gradle mode. Điều đó **không có nghĩa** mọi Gradle property đều biến mất: `gradle.properties` và `providers.gradleProperty` vẫn là cơ chế chia sẻ cấu hình được hỗ trợ. Hãy rõ source/scope của giá trị, tránh dựa vào parent mutable Project state.

### 13.1. Dùng Provider thay implicit lookup

~~~groovy
def endpointProvider =
    providers.gradleProperty('apiEndpoint')
        .orElse('https://example.org/api')
~~~

`example.org` dành cho ví dụ kỹ thuật. Khi giá trị chỉ được task dùng ở execution, wire provider vào typed `@Input Property<String>` thay vì đọc `get()` từ configuration nếu không cần. Đừng dùng root `ext` map chứa mutable config rồi truy cập từ subprojects.

### 13.2. Feature preview giúp đồng bộ behavior khi version hỗ trợ

Tài liệu Gradle 9.x có gợi ý:

~~~groovy
// settings.gradle — chỉ khi Gradle Wrapper hỗ trợ preview.
enableFeaturePreview('NO_IMPLICIT_LOOKUP_IN_PARENT_PROJECTS')
~~~

Không copy vào Gradle 8.x hoặc version chưa có feature preview này. Nếu báo unknown feature preview, kiểm tài liệu của version đó.

### 13.3. Các constraints được bổ sung theo release

Trong lịch sử versioned docs:

- Gradle 9.2 bổ sung constraint cho một số `TaskContainer.findByPath/getByPath` cross-project lookups.
- Gradle 9.4 cải thiện việc gộp/deduplicate violations.
- Dòng Gradle 9.6 thay đổi deprecations/parent lookups và tiếp tục chặt chẽ hơn.
- **Gradle 9.7** có trạng thái incubating, cờ property mới và diagnostics được mô tả rõ ràng.

Vì vậy “đã pass trên Gradle 9.7” chưa phải bảo đảm “sẽ pass mọi minor update”. Nâng Gradle cần chạy lại diagnostics/compatibility tests.

---

## 14. Quy trình thử nghiệm an toàn trước production

### Giai đoạn A — Inventory và Configuration Cache

1. Kiểm Wrapper/JDK/IDE/plugin versions.
2. Chạy baseline `help`, `:cli:test`, root `test` và IDE sync.
3. Bật Configuration Cache riêng, sửa violations của nó trước.
4. Thu baseline performance cùng RAM/CPU.
5. Không sửa production publish job.

### Giai đoạn B — Diagnostics và migration

1. Bật `--isolated-projects` trên Gradle 9.7+.
2. Khi fail, dùng `org.gradle.isolated-projects.diagnostics=true`.
3. Đọc HTML report, ưu tiên sửa root cross-project state access.
4. Di trú sang convention plugins hoặc state-isolating callbacks.
5. Upgrade plugins hoặc mở issue cho vendor có minimal reproducer.
6. Quét `help`, module tests, root tests và IDE sync.

### Giai đoạn C — Local opt-in/performance assessment

1. Khi violations của workflows mục tiêu đã hết, tắt diagnostics.
2. Chạy Isolated Projects mode chuẩn trong worktree/local environment.
3. So outputs/tests/classpaths với baseline.
4. Đo cold/warm configuration và IDE sync có cùng máy/version.
5. Kiểm RAM/CPU để không làm máy developer hoặc CI agent quá tải.
6. Ghi số liệu, rủi ro còn tồn tại và đường rollback.

### Giai đoạn D — Quyết định và giám sát

Nếu feature còn **incubating và chưa được Gradle khuyến nghị cho production artifacts**, không dùng nó làm mặc định cho release pipeline. Có thể giữ local experimentation và đợi thêm vendor/Gradle support, nếu tổ chức chấp nhận rủi ro.

Tính năng tương lai có thể thay lifecycle, API hoặc hạn chế. Mỗi khi nâng Wrapper/IDE/plugins, cần **đánh giá lại**, không dùng kết luận của version cũ mãi.

### 14.1. Rollback

Nếu chỉ bật bằng CLI, bỏ `--isolated-projects`. Nếu dùng property:

~~~properties
org.gradle.isolated-projects=false
~~~

hoặc xóa dòng đã thêm. Kiểm không có alias `org.gradle.unsafe.isolated-projects` xung đột từ môi trường khác. Trên Gradle 9.7+ có thể thử explicitly:

~~~bash
./gradlew help --no-isolated-projects
~~~

Không để property `dangerously-ignore-problems` trong shared build sau khi hoàn tất thử nghiệm.

---

## 15. Định nghĩa tương thích: không chỉ BUILD SUCCESSFUL

Một lần `./gradlew help --isolated-projects` báo `BUILD SUCCESSFUL` chưa bảo đảm toàn build logic tương thích. Lazy plugin/task configuration có thể chỉ bộc lộ violations khi run specific tasks hoặc IDE models.

Checklist hành vi cần xác nhận:

| Kiểm tra | Mục tiêu |
| --- | --- |
| `help` | Basic project configuration |
| `:core:compileJava` | Core Java plugin/toolchain |
| `:service:test` | Project dependency/Test task configuration |
| `:cli:run` | Application plugin/task/runtime model |
| Root `test`/`check` | All subprojects và work graph |
| IDE sync | Tooling model builders |
| Sửa build-logic | Cache invalidation/plugin load |
| Nâng vendor plugin | Support/version regressions |
| So outputs | Không có artifact sai/missing |
| Benchmark | Có lợi ích thực tế, không chỉ cờ hợp lệ |

### 15.1. Task dependency graph vẫn cần đúng

Nếu một task của `:cli` dùng generated file của `:core`, nên wire task output providers hoặc declared project artifact dependencies, không lấy `project(':core').tasks.getByName(...)` rồi tự hard-code file path. Isolated Projects yêu cầu **tránh mutable model coupling**, không thay thế Gradle task graph.

### 15.2. Build logic cần theo dõi plugin compatibility

Một plugin chỉ áp vào Android projects có thể fail IDE sync dù Java module tests pass. Hãy phân quyền xử lý:

- Internal convention plugin: build team sửa/test.
- External plugin: kiểm release notes/upgrades và báo issue.
- IDE plugin/model builder: phối hợp team IDE/language plugin.
- Gradle Wrapper: build/release engineer quyết định upgrade.
- Product CI: giữ đường baseline production artifacts đã xác minh.

### 15.3. Khi nào chưa nên bật?

- Wrapper không hỗ trợ feature/cờ.
- Configuration Cache chưa pass.
- Third-party plugin quan trọng incompatibility.
- IDE sync có lỗi hoặc module models thiếu.
- Memory/GC tăng gây chậm hơn.
- Codebase quá nhỏ, không có configuration bottleneck.
- Release artifacts cần đúng khi Gradle chưa khuyến nghị feature cho production.
- Chỉ có cách bật `dangerously-ignore-problems` mới pass.

“Chưa bật” là kết luận đánh giá hợp lệ và có thể ghi nguyên nhân/điều kiện xem xét lại.

---

## 16. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `Unknown command-line option '--isolated-projects'` | Wrapper quá cũ | `./gradlew --version`; tài liệu đúng version |
| Property mới không bật feature | Version cũ/alias conflict | Kiểm `org.gradle.isolated-projects` và legacy property |
| Isolated Projects + Configuration Cache disabled báo lỗi | Tính năng yêu cầu Configuration Cache | Không tắt CC khi bật isolation |
| `Project ':cli' cannot access Project.version...` | Cross-project mutable read | Project-local property/Provider/convention |
| `Project ':cli' cannot access TaskContainer...` | Lookup task của module khác | Task output Provider/project dependency |
| Nhiều lỗi từ `subprojects` | Root mutate child project models | Apply convention plugin trong từng module |
| Lỗi build-scope listeners | Callback đăng ký sai scope | Settings lifecycle API |
| `Plugin with id ... not found` từ beforeProject | Lazy plugin resolution chưa xảy ra | Apply per module hoặc settings convention plugin |
| `help` pass, `test` fail | Lazy tasks/plugin code paths khác | Diagnostics từng workflow |
| CLI pass, IDE sync fail | Tooling model/IDE/plugin support khác | Plugin/IDE version matrix |
| Diagnostics mode chậm | Cấu hình tuần tự để report lỗi | Không dùng mode đó benchmark |
| Mode nguy hiểm pass nhưng outputs sai | Bỏ qua constraints | Không tin artifact, sửa violations |
| `--parallel` không tăng speed | Cờ bị bỏ qua trong mode isolated | Đo actual configuration work |
| Configuration on Demand không bỏ modules | Current limitation | Không hứa project avoidance |
| Gradle Daemon dùng nhiều RAM | Parallel project config | Điều chỉnh workers/RAM, đo lại |
| Đổi included build làm config cache invalidated rộng | Current limitation | Quan sát tần suất invalidation, đổi kiến trúc khi có ích |
| Root property lookup đổi behavior | No implicit parent lookup | Explicit Gradle providers |
| `project(':core')` bị nhầm là sai | Confuse project dependency vs mutable access | Declarative dependency là hợp lệ |
| Java toolchain not found | JDK/resolver issue riêng | Cấu hình JDK17, không đổ lỗi Isolated Projects |
| TestKit pass bản cũ nhưng fail bản mới | Constraints/Gradle API changed | Support matrix, compatibility tests |
| Chạy sạch lần hai nhưng không nhanh | Overhead/bottleneck nằm ở execution | Đo config vs exec, không đánh giá chỉ bằng total time |
| Plugin vendor chưa hỗ trợ | Classpath/Project mutable access | Upgrade, issue report, tạm hoãn adoption |

### 16.1. Debug decision tree

~~~text
1. Wrapper version được xác nhận?
           |
           v
2. Version có hỗ trợ cờ/property nào?
           |
           v
3. Configuration Cache đã compatible?
           |
           v
4. Plugins và IDE có support matrix?
           |
           v
5. help --isolated-projects + diagnostics (9.7+)
           |
           v
6. Cross-project state, build-scope hay vendor issue?
           |
           v
7. Convention plugin / safe Provider / isolated view
           |
           v
8. Test module tasks + root test + IDE sync
           |
           v
9. So outputs/correctness + benchmark cold/miss
           |
           v
10. Local opt-in, tiếp tục migration, hoặc rollback
~~~

---

## 17. Bài tập tự đánh giá

### Bài 1 — Isolated Projects có mặc định bật trong Gradle 9.7 không?

**Không.** 9.7 nâng lên incubating; phải opt-in. Trạng thái incubating không đồng nghĩa mọi plugin đã hỗ trợ.

### Bài 2 — Có thể dùng `--isolated-projects` với mọi Gradle 8.x?

**Không.** Cần đọc đúng versioned docs và kiểm Wrapper. Một số bản thử nghiệm dùng `org.gradle.unsafe.isolated-projects`, có thể không có cờ mới.

### Bài 3 — Isolated Projects và Build Cache có cùng tác dụng?

**Không.** Isolated Projects tối ưu project configuration, Build Cache reuse task outputs.

### Bài 4 — Configuration Cache hit có làm Isolated Projects vô ích?

Không tuyệt đối, nhưng phần cấu hình đã được bỏ thì không còn nhiều thứ để parallelize. Cần đo miss scenarios/IDE sync.

### Bài 5 — `rootProject.version` có an toàn vì chỉ đọc?

**Không.** `version` là mutable project state. Đọc từ child project vẫn vi phạm ranh giới isolation.

### Bài 6 — `implementation project(':core')` có vi phạm không?

**Không.** Đó là declarative Gradle dependency API, không phải đọc mutable project model.

### Bài 7 — Tại sao nên dùng convention plugin?

Vì mỗi module tự apply plugin và plugin chỉ cấu hình target project. Không cần root `subprojects` block mutate state child projects.

### Bài 8 — Diagnostics mode có dùng để so tốc độ với baseline?

**Không.** Nó cố ý chạy configuration tuần tự để phát hiện nhiều violations. Tắt diagnostics mới benchmark speed.

### Bài 9 — `dangerously-ignore-problems` có thể dùng publish artifacts không?

**Không.** Nó bỏ qua safety guards và output có thể sai. Không dùng nó cho production hoặc signing/release.

### Bài 10 — IDE sync có tự bật khi CLI `help --isolated-projects` chạy một lần?

Không. IDE sync cần property `org.gradle.isolated-projects=true` trong file phù hợp và IDE/plugin support thực tế.

### Bài 11 — Vì sao `--parallel` không làm config nhanh hơn trong mode isolated?

Theo behavior Gradle hiện hành, flag Parallel Execution bị bỏ qua trong mode Isolated Projects. Configuration concurrency được feature và worker settings quản lý.

### Bài 12 — Test `:cli:run` pass có đủ chứng minh toàn repository compatible?

Không. Còn các tasks khác và IDE models có thể trigger build logic riêng. Cần tests/workflow matrix.

### Bài 13 — Bật `org.gradle.configuration-cache=false` cùng Isolated Projects?

Không được; Isolated Projects dựa trên Configuration Cache.

### Bài 14 — Có thể thay root `version` bằng `project(':core').version`?

Không. Chỉ đổi chỗ đọc mutable state; cần chuyển sang provider/config source độc lập.

### Bài 15 — Khi nào nên nâng Gradle trước khi đánh giá?

Nếu Wrapper quá cũ/experimental API thiếu diagnostics và môi trường cho phép nâng với đầy đủ tests. Không nâng chỉ để xem báo cáo khi production plugins chưa tương thích.

### Bài 16 — Nếu subproject có nhiều versions từ root property lookups?

Kiểm implicit parent lookup changes (Gradle 9.6+), dùng explicit `providers.gradleProperty` hoặc project-local convention policy.

### Bài 17 — Vì sao build 3 modules có thể không tăng tốc?

Quá ít configuration work; overhead parallel configuration có thể tương đối lớn. Đo trên workload thật.

### Bài 18 — Chế độ Isolated Projects có tránh cấu hình modules không liên quan không?

Theo Gradle docs hiện hành: **chưa**. Tất cả projects được cấu hình khi configuration chạy; Configuration on Demand bị bỏ qua.

### Bài 19 — Khi vendor plugin có violations thì làm gì?

Ghi version/stacktrace, tìm bản sửa, báo maintainer với minimal reproducer, hoãn rollout nếu plugin là critical.

### Bài 20 — Một quyết định “chưa bật” có phải lỗi không?

Không. Nếu feature còn incubating, ảnh hưởng correctness hoặc release policy chưa cho phép, kết luận trì hoãn kèm evidence là lựa chọn có trách nhiệm.

## 18. Checklist trước khi kết luận có nên dùng Isolated Projects

1. Đã kiểm `./gradlew --version` và gradle-wrapper.properties?
2. Đã dùng tài liệu Gradle **đúng version**?
3. Biết Gradle 9.7 là mốc chuyển experimental → incubating?
4. Đã xác nhận flag/property phù hợp Wrapper đang dùng?
5. Không lẫn property legacy và new property với giá trị trái nhau?
6. Configuration Cache đã pass cho workflows cần đánh giá?
7. Có inventory plugins/IDE/JDK/support status?
8. Đã loại root cross-project mutation phổ biến?
9. Không còn `rootProject.version`, `project(':x').tasks` mutable cross-project access?
10. Có convention plugins hoặc state-isolating callbacks đúng scope?
11. `IsolatedProject` chỉ được dùng cho safe immutable data?
12. Đã kiểm plugin resolution nếu dùng settings lifecycle callbacks?
13. Đã xử lý implicit parent property lookup/deprecations theo version?
14. Đã dùng diagnostics mode và đọc HTML problems reports?
15. Có test Java compile, JUnit, application run và full task selector?
16. Có test IDE sync bằng IDE/plugin versions thật?
17. Đã so expected stdout/outputs với baseline?
18. Benchmark có phân biệt cold/miss và warm/hit?
19. Đã đo median/p95, CPU/RAM và worker count?
20. Không dùng `dangerously-ignore-problems` cho production artifacts?
21. Có rollback option và người chịu trách nhiệm theo dõi release notes?
22. Có support matrix khi nâng Gradle minor versions?
23. Lợi ích hiệu năng có thật trong workload của project?
24. Kết luận có nêu **rõ điều kiện áp dụng** thay vì hứa speedup mặc định?

## 19. Tài liệu tham khảo chính thức

- [Gradle — Isolated Projects, version 9.9](https://docs.gradle.org/9.9.0/userguide/isolated_projects.html): constraints, diagnostics, limits, IDE sync và migration.
- [Gradle — Isolated Projects, current docs](https://docs.gradle.org/current/userguide/isolated_projects.html): cập nhật gần nhất; cần đối chiếu với Wrapper.
- [Gradle Blog — Introducing Isolated Projects (6/8/2026)](https://blog.gradle.org/introducing-isolated-projects): nâng experimental → incubating trong Gradle 9.7, cảnh báo production artifacts.
- [Gradle 9.7.1 Release Notes](https://docs.gradle.org/9.7.1/release-notes.html): Incubating status, strict violations và deprecated legacy property aliases.
- [Gradle — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): Isolated Projects property và workers.max.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): cache key/configuration reuse/task graph.
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): unsupported model references/listeners.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): settings include, project paths.
- [Gradle — Project Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies_between_subprojects.html): `implementation project(':module')`.
- [Gradle — Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html): reusable build logic ở target project.
- [Gradle — Sharing Build Logic](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): included build `build-logic`.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): version-specific CLI flags.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): pin distribution.
- [Gradle — Performance](https://docs.gradle.org/current/userguide/performance.html): profiling bottlenecks.

**Thông điệp kết thúc:** Đánh giá Isolated Projects phải bắt đầu từ **Gradle Wrapper version**, sau đó là Configuration Cache compatibility, plugin/IDE support, diagnostics, output correctness và benchmark đo được. Cờ mới không phải lời hứa nhanh hơn hay sẵn sàng production; khi feature incubating, chọn local opt-in hoặc trì hoãn có thể đúng hơn bật mặc định.
