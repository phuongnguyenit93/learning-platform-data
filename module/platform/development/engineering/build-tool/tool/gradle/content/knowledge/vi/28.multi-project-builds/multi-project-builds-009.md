# Thiết kế đồ thị module để kiểm thử và build có thể thực thi độc lập trong Gradle

## 1. Bài toán: nhiều module nhưng mỗi module vẫn có thể được kiểm tra riêng

Một ứng dụng Java thường bắt đầu với một project duy nhất. Khi codebase lớn dần, một file `build.gradle` và một source set `main` khó thể hiện rõ ranh giới giữa domain logic, dịch vụ, ứng dụng chạy, adapter, thư viện dùng chung và test utilities. Gradle hỗ trợ **multi-project build** để phân rã một build thành các **subprojects/modules** có mã nguồn, plugins, dependencies và tasks riêng.

Nhưng chỉ chia thư mục chưa đủ. Nếu mọi module dùng chung classpath tùy tiện, đọc trực tiếp source/output của nhau hoặc ép `build` module này chạy toàn bộ `build` module khác, các module chỉ “độc lập trên danh nghĩa”. Một sửa đổi nhỏ có thể kéo cả repository chạy tests, tạo dependency cycle và gây khó khăn khi cô lập lỗi.

Mục tiêu của bài học thuộc nhóm **Build nhiều dự án** trong **Build Tool Gradle** là thiết kế được **đồ thị module có hướng, không chu trình**, với những đặc tính:

1. Module có **trách nhiệm và API boundary rõ ràng**.
2. Dependency giữa modules được khai báo bằng `project(':module')` và đúng configuration như `api`, `implementation`, `testImplementation`.
3. Từ root repository, có thể chạy **`:module:test`**, **`:module:check`** hoặc **`:module:build`** mà không chủ động yêu cầu tests của mọi module khác.
4. Gradle vẫn **tự chuẩn bị production artifact của dependencies upstream** khi test/compile module đang xét. “Độc lập khi gọi” không có nghĩa module phải tự biên dịch khi vắng mọi dependency.
5. Có thể chạy **toàn bộ tests/builds** bằng task selector từ root để bảo đảm toàn hệ thống.
6. Có chiến lược cho integration tests, test fixtures, shared build conventions, CI và module dependency graph checks.
7. Các lệnh trong bài có thể thực hành trên project **Java 17 + Groovy DSL + JUnit Jupiter** hoàn chỉnh.

**Quan trọng:** “kiểm thử và build thực thi độc lập” là khả năng **chọn đúng mục tiêu và giới hạn phạm vi công việc**. Module `:cli` phụ thuộc `:service` vẫn cần compiled classes/JAR của `:service` trước khi chạy; đó là **dependency thật**. Điều phải tránh là vô tình kéo thêm `:service:test`, `:core:test`, deployment hoặc publish tasks chỉ để chạy `:cli:test`.

## 2. Phân biệt ba đồ thị

| Đồ thị | Node | Edge | Giải quyết câu hỏi |
| --- | --- | --- | --- |
| **Module/project dependency graph** | `:core`, `:service`, `:cli` | Module nào phụ thuộc module nào | Ai được phép dùng API của ai? |
| **Task execution graph (DAG)** | `:cli:test`, `:service:jar`, `:core:compileJava` | Task nào phải chạy/hoàn thành trước task khác | Lệnh này sẽ thực hiện những công việc nào? |
| **External dependency graph** | `org.junit.jupiter:junit-jupiter:5.12.0`, thư viện Maven khác | Thư viện/version nào phụ thuộc thư viện khác | Tại sao JAR/version đó ở classpath? |

Trong một Gradle multi-project build, một **project dependency** như:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

vừa thể hiện dependency module, vừa làm Gradle biết cần lấy **outgoing variant/artifact** của `:core` cho compile/runtime classpath của consumer. Gradle tự sinh những **task dependencies cần thiết** từ mối quan hệ producer–consumer đó. Không cần tự gọi `:core:build` trong `:service:compileJava`.

Ví dụ đồ thị sau dùng quy ước **A → B nghĩa A phụ thuộc B**:

~~~text
:cli  -------->  :service  -------->  :core
  |                  |                  |
  v                  v                  v
CLI entry point   Application logic  Domain utility
~~~

Trong đó:

- `:core` không phụ thuộc `:service` hoặc `:cli`.
- `:service` dùng API của `:core`.
- `:cli` dùng API của `:service`.
- Không có chiều ngược lại từ `:core` tới `:cli`.

Như vậy graph **không có cycle**. Nếu `:core` lại thêm `implementation project(':cli')`, thiết kế tạo vòng dependency logic và Gradle có thể không giải quyết được task graph/artifact cycle.

### 2.1. Thứ tự thư mục không tạo dependency

Các dòng sau chỉ **khai báo module tồn tại**:

~~~groovy
include 'core', 'service', 'cli'
~~~

Chúng không tự diễn đạt `:cli` dùng `:service`. Dependency chỉ xuất hiện khi khai đúng trong `dependencies { ... }` hoặc qua mô hình biến thể/tác vụ tương đương. Nếu file `settings.gradle` liệt kê `core` trước `service`, đó **không phải** quy tắc buộc compile core trước service.

### 2.2. Module dependency khác task dependency thủ công

Sai lầm thường gặp:

~~~groovy
// Cách làm KHÔNG nên dùng để mô tả phụ thuộc API Java:
tasks.named('compileJava') {
    dependsOn(':core:build')
}
~~~

Đoạn này ràng buộc Java compiler của consumer với **toàn bộ build** upstream, gồm `check`, `test`, `jar` và các verification khác có thể được gắn vào. Nó vừa thiếu cách đưa API classes lên classpath, vừa khiến một test của downstream có thể vô tình kéo full upstream tests.

Đúng hơn:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

Khi đó Gradle dựa trên component variants và artifact producers của `:core` để hình thành classpath lẫn task graph. Chỉ dùng dependency task-to-task trực tiếp khi thực sự có quan hệ **công việc** (không phải dependency module API) và đã cân nhắc project isolation.

## 3. Tổ chức module theo trách nhiệm và chiều phụ thuộc

Một modularization tốt không nhất thiết càng nhiều module càng tốt. Mỗi module nên có **lý do tồn tại rõ ràng**: domain, use cases, adapters, CLI/UI, data integrations hoặc thư viện chia sẻ ổn định.

Ví dụ ba module trong bài:

| Module | Chứa | Được dùng bởi | Không nên biết tới |
| --- | --- | --- | --- |
| `:core` | Hàm normalize tên, domain utility Java thuần | `:service` | CLI, deployment, database |
| `:service` | Greeting use case, gọi core | `:cli` | CLI argument parsing |
| `:cli` | Java `main`, đọc arguments và in stdout | Không module nào trong demo | Các chi tiết nội bộ không cần thiết của core |

Sơ đồ layer:

~~~text
               +-----------------+
               | :cli            |
               | entry point     |
               +--------+--------+
                        |
                        v
               +-----------------+
               | :service        |
               | use-case logic  |
               +--------+--------+
                        |
                        v
               +-----------------+
               | :core           |
               | pure Java logic |
               +-----------------+
~~~

Chọn chiều dependency từ lớp **ở ngoài** vào lớp **ổn định hơn ở trong**. Đây là ví dụ dễ học, không phải kiến trúc duy nhất. Trong dự án enterprise, có thể dùng dependency inversion: core định nghĩa interfaces, adapter triển khai interfaces, composition root wire implementations. Khi đó graph phải vẫn không cycle.

### 3.1. Khi nào nên tách module?

Một module riêng có ý nghĩa khi có một hoặc nhiều đặc điểm:

- Public API/contract cần được kiểm soát.
- Cần kiểm thử riêng với ít test runtime dependencies.
- Có vòng đời release hoặc ownership tương đối độc lập.
- Có build toolchain hoặc plugin phù hợp một loại artifact.
- Có nhu cầu tái sử dụng ở nhiều modules.
- Có thể xác định rõ những module nào được phép phụ thuộc nó.

Không nên tách chỉ vì một package có vài file. Quá nhiều modules nhỏ làm tăng configuration overhead và chi phí duy trì dependency graph. Tìm ranh giới **đủ ổn định** để API ít phải đổi, rồi đo thời gian build/test để điều chỉnh.

### 3.2. Ranh giới public API

Giữ classes/private helpers nội bộ trong `:core` khi `:service` không cần chúng. Dùng `java-library` để có `api`/`implementation`; điều này giúp tránh lộ dependencies thực thi vào compile classpath của consumer khi chúng không cần thiết.

Một module không nên import trực tiếp class từ `src/main/java` của module khác bằng đường dẫn file. Nếu cần API, khai báo **project dependency**; nếu cần test fixture, dùng cơ chế test fixtures hoặc published test utility variant phù hợp.

## 4. Gradle settings và project paths

Trong root `settings.gradle`:

~~~groovy
rootProject.name = 'module-graph-lab'

include 'core', 'service', 'cli'
~~~

Từ đó các project paths là:

~~~text
:
├── :core
├── :service
└── :cli
~~~

`:` là root project. `:core:test` nghĩa **task test của project core**; `:service:build` là build của service. Nếu một module lồng thư mục `features/payment`, có thể khai báo `include 'features:payment'` để có path `:features:payment`.

**Project path không nhất thiết là relative file path** khi có custom `projectDir` hoặc composite build. Với layout mặc định, Gradle ánh xạ `:service` tới root directory `service/`.

Lệnh xem project paths:

~~~bash
./gradlew projects
~~~

Lệnh xem task của đúng module:

~~~bash
./gradlew :core:tasks --all
./gradlew :service:tasks --all
./gradlew :cli:tasks --all
~~~

Tránh giả định một task `build` ở root đồng nghĩa task `:build`. Đây là hai cách chọn task khác nhau trong multi-project build.

## 5. Hai kiểu chạy: task path cụ thể và task selector

Đây là phần quyết định “thực thi độc lập” có hoạt động như mong muốn hay không.

### 5.1. Chạy đúng test của một module

Từ **root repository**:

~~~bash
./gradlew :core:test
./gradlew :service:test
./gradlew :cli:test
~~~

Mỗi lệnh **chọn task test của đúng subproject** được chỉ định. Gradle vẫn kéo task producer từ dependencies upstream nếu cần compile/runtime artifacts.

Ví dụ, `:cli:test` có thể phải chuẩn bị `:service:jar` và `:core:jar` hoặc những task output variant tương ứng. Nhưng nó **không tự động chọn `:service:test` và `:core:test`**, chỉ vì `:cli` phụ thuộc `:service`.

Sự khác biệt cần nhớ:

| Điều gì? | Khi gọi `:cli:test` |
| --- | --- |
| Chạy `:cli:test` | Có, nếu test task có việc |
| Compile/prepare `:cli` test classes | Có theo task graph |
| Chuẩn bị production outputs của `:service`/`:core` | Có khi cần theo project dependency |
| Chạy `:service:test` | **Không mặc định** |
| Chạy `:core:test` | **Không mặc định** |
| Publish mọi artifact lên repository | **Không mặc định** |
| Chạy `:cli:run` | Không |

Task graph thực tế phụ thuộc Gradle version, selected variants, build cache và những plugins được áp dụng, nên không cam kết lúc nào cũng có chính xác cùng tên producer task.

### 5.2. Chạy build riêng một module

~~~bash
./gradlew :core:build
./gradlew :service:build
./gradlew :cli:build
~~~

`:service:build` chọn lifecycle `build` của service, trong Java project thường gồm `assemble` và `check` (ví dụ `jar` và `test`). Nó có thể build **production artifacts của `:core`** cần cho compile/test, nhưng không mặc định chạy toàn bộ `:core:check`/`:core:build`.

Do vậy, với mục tiêu “tất cả modules phải pass tests trước release”, chạy **tất cả build/check tasks** chứ không suy một leaf-module build đã xác minh trọn vẹn các upstream modules.

### 5.3. Chạy mọi module bằng task selector

Khi đứng tại root của multi-project build:

~~~bash
./gradlew test
./gradlew build
~~~

Theo Gradle task selector semantics, `test` từ root chọn task tên `test` trong các subprojects có task đó; `build` tương tự. Đây là **cách tổng hợp kiểm thử/build từ root**, khác với `:cli:test` hoặc `:cli:build`.

Một ngoại lệ quan trọng: một số selectors như `help` hoặc `dependencies` có cách hiển thị/selection đặc biệt để tránh báo cáo quá nhiều projects. Khi cần đọc dependency report của một module, dùng path đầy đủ.

Nếu root **không áp dụng `java`** thì có thể không có `:test`/`:build` ở root; tuy nhiên task selector `test` hoặc `build` vẫn có thể chọn subproject tasks. **Không thay `./gradlew test` bằng `./gradlew :test`** nếu mục tiêu là toàn bộ modules; `:test` là đường dẫn đến một task trong root project.

### 5.4. Chạy nhiều mục tiêu một lần

~~~bash
./gradlew :core:test :service:test :cli:test
./gradlew :core:build :service:build :cli:build
~~~

Gradle hợp nhất task DAG của các mục tiêu được chọn; task production dependency dùng chung không cần bị chạy hành động hai lần chỉ vì có nhiều consumers. So với ba Gradle invocations riêng, một invocation có thể giảm thời gian khởi động và reuse thông tin graph.

Đối với CI, chọn **explicit task paths** khi cần danh sách modules cố định, hoặc root selector `test`/`build` khi muốn tự mở rộng cho tất cả Java modules hiện diện.

## 6. Demo hoàn chỉnh: ba module Java 17 có tests độc lập

Ta sẽ tạo build tên `module-graph-lab` với ba modules:

~~~text
module-graph-lab/
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
│       ├── main/java/demo/core/NameFormatter.java
│       └── test/java/demo/core/NameFormatterTest.java
├── service/
│   ├── build.gradle
│   └── src/
│       ├── main/java/demo/service/GreetingService.java
│       └── test/java/demo/service/GreetingServiceTest.java
└── cli/
    ├── build.gradle
    └── src/
        ├── main/java/demo/cli/Main.java
        └── test/java/demo/cli/MainSmokeTest.java
~~~

Root không cần áp dụng Java plugin; mỗi module tự áp dụng đúng plugin của mình. Gradle Wrapper phải là **file hợp lệ được Gradle tạo ra**, không phải bốn file rỗng. Ví dụ chọn JUnit Jupiter 5.12.0 và JUnit Platform Launcher 1.12.0; cần Maven Central để resolve dependencies lần đầu. Mọi source ở đây dùng Java 17, Groovy DSL.

### 6.1. Root `settings.gradle`

~~~groovy
rootProject.name = 'module-graph-lab'

include 'core', 'service', 'cli'
~~~

Đây là file settings duy nhất cho demo. Không cần đặt `subprojects { apply plugin: 'java' }` trong root `build.gradle`; module tự xác định plugin/tùy chọn phù hợp.

### 6.2. `core/build.gradle`: module độc lập không có project dependency

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

`java-library` tạo Java source sets, `api`/`implementation` model và task `test`/`build`. Vì core không khai project dependencies, nó có thể được biên dịch/test mà không cần service hoặc cli.

`testImplementation` và `testRuntimeOnly` chỉ cấp JUnit cho core tests. Khi một module khác khai `implementation project(':core')`, nó không tự nhận JUnit dependencies dùng riêng để kiểm tra core.

### 6.3. `core/src/main/java/demo/core/NameFormatter.java`

~~~java
package demo.core;

public final class NameFormatter {
    private NameFormatter() {
    }

    public static String normalize(String raw) {
        if (raw == null) {
            return "guest";
        }

        String trimmed = raw.strip();
        return trimmed.isEmpty() ? "guest" : trimmed;
    }
}
~~~

`String.strip()` có từ Java 11 nên hợp lệ với Java 17. Class này không cần external library. Nó là **API tối thiểu** cho consumer và có thể test bằng unit test độc lập.

### 6.4. `core/src/test/java/demo/core/NameFormatterTest.java`

~~~java
package demo.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class NameFormatterTest {
    @Test
    void stripsSpace() {
        assertEquals("Ada", NameFormatter.normalize("  Ada  "));
    }

    @Test
    void fallsBackForNull() {
        assertEquals("guest", NameFormatter.normalize(null));
    }

    @Test
    void fallsBackForBlank() {
        assertEquals("guest", NameFormatter.normalize("   "));
    }
}
~~~

Chạy:

~~~bash
./gradlew :core:test
~~~

Task này thực thi **ba JUnit Jupiter tests thuộc core** và không yêu cầu `:service:test`/`:cli:test`. Nếu một assertion fail, lỗi nằm trong phạm vi core; đây là lợi ích đầu tiên của việc tách module có test boundary.

### 6.5. `service/build.gradle`: dependency xuống core

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

`implementation project(':core')` nói rằng code của service cần core **để implementation của service hoạt động**, nhưng public method signatures không nhất thiết phải công bố core types cho consumer bên ngoài. Gradle tự resolve variant và producer tasks của `:core` khi biên dịch service.

Không cần:

~~~groovy
// Sai mục đích; không đưa vào build.gradle demo.
tasks.named('compileJava') {
    dependsOn(':core:build')
}
~~~

Đoạn trên ép chạy cả quality/tests của core và không mô hình hóa API/classpath đúng cách.

### 6.6. `service/src/main/java/demo/service/GreetingService.java`

~~~java
package demo.service;

import demo.core.NameFormatter;

public final class GreetingService {
    public String greet(String rawName) {
        return "Hello, " + NameFormatter.normalize(rawName) + "!";
    }
}
~~~

`GreetingService` trả về `String`. Class `NameFormatter` được dùng **bên trong implementation**; public method không expose `NameFormatter` kiểu input/output. Vì vậy `implementation project(':core')` phù hợp.

Nếu public API của service có method trả/nhận một public type từ core, hãy cân nhắc `api project(':core')` trong java-library: consumers cần core API type trên compile classpath. Đó là mô hình khác với demo hiện tại.

### 6.7. `service/src/test/java/demo/service/GreetingServiceTest.java`

~~~java
package demo.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingServiceTest {
    private final GreetingService service = new GreetingService();

    @Test
    void greetsNamedUser() {
        assertEquals("Hello, Ada!", service.greet(" Ada "));
    }

    @Test
    void greetsGuest() {
        assertEquals("Hello, guest!", service.greet(null));
    }
}
~~~

Test này chỉ import service class và JUnit. Core utility được gọi **gián tiếp** qua service logic, nhưng không cần chạy `:core:test` riêng trong cùng invocation.

Chạy:

~~~bash
./gradlew :service:test
~~~

Gradle chuẩn bị upstream production outputs của core nếu cần; không tự chạy ba unit tests thuộc core. Trong CI, muốn core test cũng pass, chạy thêm `:core:test` hoặc root selector `test`.

### 6.8. `cli/build.gradle`: ứng dụng JVM dùng service

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

Application plugin áp dụng khả năng Java cần thiết và cung cấp task `run`, distribution/start scripts. `implementation project(':service')` đưa service API và transitive runtime dependencies (core) vào runtime classpath của cli.

**Không cần khai thêm `implementation project(':core')` trong cli** vì cli không import core API trực tiếp; service implementation ở runtime có thể dùng core qua transitive dependency. Nếu cli thực sự cần import core trực tiếp, hãy xem lại layer boundary: có nên cho phép cli biết core không? Nếu có, khai dependency tường minh theo thiết kế.

### 6.9. `cli/src/main/java/demo/cli/Main.java`

~~~java
package demo.cli;

import demo.service.GreetingService;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String rawName = args.length == 0 ? null : args[0];
        System.out.println(new GreetingService().greet(rawName));
    }
}
~~~

Với Java 17, class này biên dịch được và chạy bằng classpath chứa cli, service và core outputs/artifacts.

### 6.10. `cli/src/test/java/demo/cli/MainSmokeTest.java`

~~~java
package demo.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;

import demo.service.GreetingService;
import org.junit.jupiter.api.Test;

class MainSmokeTest {
    @Test
    void serviceIsAvailableToCli() {
        assertEquals(
            "Hello, Linh!",
            new GreetingService().greet(" Linh ")
        );
    }
}
~~~

Smoke test này xác minh **cli test classpath** thấy được service API và runtime có core. Nó không can thiệp `System.out` hay test các side effects của CLI; tránh biến test thành phụ thuộc global mutable stdout, nhất là khi chạy parallel tests.

### 6.11. Chạy từng module độc lập

Từ root repository:

~~~bash
./gradlew :core:test
./gradlew :service:test
./gradlew :cli:test
~~~

Các kết quả mong đợi nếu file đúng và JUnit resolve thành công:

| Lệnh | Test class được chọn | Số test methods | Tests upstream có được tự chọn? |
| --- | --- | ---: | --- |
| `:core:test` | `NameFormatterTest` | 3 | Không có upstream |
| `:service:test` | `GreetingServiceTest` | 2 | **Không chọn** `:core:test` |
| `:cli:test` | `MainSmokeTest` | 1 | **Không chọn** `:core:test`/`:service:test` |

Số lượng tests này đúng với **source demo**, không phải con số chung Gradle. Các invocation có thể có nhiều producer tasks ở upstream như `:core:compileJava`, `:core:jar`, `:service:compileJava` hoặc tương đương theo variants; đó là công việc cần thiết để chạy đúng module tests.

### 6.12. Chạy từng build riêng và toàn bộ build

~~~bash
./gradlew :core:build
./gradlew :service:build
./gradlew :cli:build
~~~

Khác với:

~~~bash
./gradlew build
~~~

Khi chạy task selector `build` từ root, Gradle chọn các build tasks trong subprojects có task đó. Đây là mục tiêu kiểm tra **toàn bộ modules**. Một `:cli:build` riêng không tự bảo đảm hai module upstream đã chạy tất cả unit tests của chúng.

Bạn có thể chọn:

~~~bash
./gradlew test
~~~

từ root để chạy tests của cả ba modules theo task selector semantics. Trong demo có **6 test methods** tổng cộng: 3 ở core, 2 ở service và 1 ở cli.

### 6.13. Chạy ứng dụng và stdout thực tế

~~~bash
./gradlew :cli:run
./gradlew :cli:run --args="Linh"
~~~

Ngoài các dòng log của Gradle, stdout của Java `Main` lần lượt là:

~~~text
Hello, guest!
~~~

và:

~~~text
Hello, Linh!
~~~

Nếu chạy `./gradlew :core:run` hoặc `:service:run`, chúng **không có task run** mặc định, vì chỉ áp dụng `java-library`. Đây là một ranh giới plugin/task phù hợp loại module, không phải lỗi cấu hình.

### 6.14. Chạy Java bằng `javac`/`java` trực tiếp để kiểm API boundaries

Các production classes trong demo chỉ dùng Java standard library. Nếu muốn tự kiểm compile chain mà không cần JUnit/Gradle, trên Linux/macOS từ root:

~~~bash
mkdir -p manual-out/core manual-out/service manual-out/cli

javac -encoding UTF-8 -d manual-out/core \
    core/src/main/java/demo/core/NameFormatter.java

javac -encoding UTF-8 \
    -cp manual-out/core \
    -d manual-out/service \
    service/src/main/java/demo/service/GreetingService.java

javac -encoding UTF-8 \
    -cp "manual-out/core:manual-out/service" \
    -d manual-out/cli \
    cli/src/main/java/demo/cli/Main.java

java -cp "manual-out/core:manual-out/service:manual-out/cli" \
    demo.cli.Main Linh
~~~

Stdout đúng của lệnh `java` cuối:

~~~text
Hello, Linh!
~~~

Đây là thí nghiệm cho thấy thứ tự **core → service → cli** và classpath cần những compiled outputs nào. Nó không thay thế Gradle, vì trong dự án thật còn có third-party dependencies, generated sources, resources, JUnit và Gradle task caching.

Trên Windows PowerShell, tạo ba thư mục `manual-out/core`, `manual-out/service`, `manual-out/cli` trước; dùng `;` để tách các classpath entries thay dấu `:`. Shell `javac` phải có JDK17 trên PATH; Gradle toolchain không tự sửa PATH của terminal.

### 6.15. Không cố build từng subproject như một repository độc lập

“Có thể chạy `:service:test` độc lập” nghĩa là **chọn test task service từ shared root Gradle build**. Nó không có nghĩa chỉ copy riêng thư mục `service/` sang máy khác sẽ build được nếu không còn `settings.gradle` và `:core` dependency. Có ba mức độ:

| Mức | Ý nghĩa | Demo hỗ trợ? |
| --- | --- | --- |
| **Task selection độc lập** | Từ root chọn riêng `:service:test` hoặc `:service:build` | Có |
| **Build logic ownership** | Mỗi module có plugins/deps/test tasks riêng | Có |
| **Repository isolation thực sự** | Module build được sau khi tách thành repo khác, dùng published dependencies/composite build | Không tự động; cần migration |

Khi cần repository isolation, có thể publish `:core` như Maven module rồi cho service dùng coordinate/version ổn định, hoặc dùng composite builds với dependency substitution phù hợp. Đừng quảng cáo một subproject còn tham chiếu `project(':core')` là có thể tách khỏi root mà không sửa gì.

## 7. Đọc đồ thị thực tế và phát hiện coupling ngoài ý muốn

### 7.1. `projects` cho thấy project hierarchy, không phải tất cả dependency edges

~~~bash
./gradlew projects
~~~

Bạn sẽ thấy `:core`, `:service` và `:cli`, nhưng **không suy ra từ thứ tự liệt kê** rằng cli phụ thuộc service. Dùng dependency reports cho từng project để thấy classpath relationships.

### 7.2. `dependencies` và `dependencyInsight`

~~~bash
./gradlew :service:dependencies --configuration compileClasspath
./gradlew :cli:dependencies --configuration runtimeClasspath
./gradlew :cli:dependencies --configuration testRuntimeClasspath
~~~

Trong `:service:compileClasspath`, bạn sẽ thấy project dependency đến `:core`. Trong `:cli:runtimeClasspath`, quan hệ runtime transitive tới `:service` và `:core` sẽ xuất hiện theo variant metadata.

Nếu cần điều tra một dependency cụ thể:

~~~bash
./gradlew :cli:dependencyInsight \
    --dependency core \
    --configuration runtimeClasspath
~~~

`dependencyInsight` giải thích vì sao một dependency/variant được chọn. Nó **không phải task graph viewer**. Sự khác biệt module dependency và task graph là căn bản khi debug “vì sao Gradle build module kia?”.

### 7.3. `--dry-run` để thấy task execution graph mà không chạy actions

~~~bash
./gradlew :core:test --dry-run
./gradlew :service:test --dry-run
./gradlew :cli:test --dry-run
./gradlew :cli:build --dry-run
./gradlew test --dry-run
~~~

Quan sát:

- `:core:test` không cần chọn service/cli tasks.
- `:service:test` có thể chọn core production tasks, **không** core test.
- `:cli:test` có thể chọn service/core production tasks, **không** chọn upstream tests.
- `:cli:build` chỉ là build goal của cli cùng production dependency closure.
- Root selector `test` chọn tests ở cả ba modules.

`--dry-run` chỉ lập kế hoạch và **không thực thi task actions**; nó có thể hiển thị `SKIPPED` cho tất cả tasks trong dry-run. Không dùng kết quả ấy làm bằng chứng JUnit tests đã pass.

### 7.4. `--info` để hiểu task vì sao chạy lại

~~~bash
./gradlew :cli:test --info
./gradlew :service:build --info
~~~

`--info` có thể cho biết một task bị `UP-TO-DATE`, `NO-SOURCE`, lấy output `FROM-CACHE` hoặc phải chạy vì input/classpath thay đổi. Các test reports theo module thường là:

~~~text
core/build/reports/tests/test/index.html
service/build/reports/tests/test/index.html
cli/build/reports/tests/test/index.html
~~~

Một báo cáo test của `:cli` không tự tổng hợp results của `:service`/`:core`. Nếu muốn một report tổng hợp cho CI, dùng test report aggregation phù hợp, không dựa vào một thư mục report chung rồi copy tùy tiện.

### 7.5. Thêm giới hạn trên test scope

Chọn một class duy nhất:

~~~bash
./gradlew :core:test --tests 'demo.core.NameFormatterTest'
./gradlew :service:test --tests 'demo.service.GreetingServiceTest'
./gradlew :cli:test --tests 'demo.cli.MainSmokeTest'
~~~

`--tests` là filter của Gradle `Test` task, không phải cách phân rã module tự động. Nếu pattern không khớp class/method, Gradle có thể báo không tìm thấy tests; hãy kiểm Java package và source set.

## 8. `api`, `implementation` và rò rỉ compile classpath

Với `java-library`:

- `api project(':core')`: consumer của service được thấy core API types khi compile; dùng khi public API của service **phơi bày core types**.
- `implementation project(':core')`: service cần core để triển khai nhưng không công bố core như một phần public compile API của service; vẫn có core trong runtime dependency closure.
- `compileOnly`: chỉ cần khi compile; không tự đưa dependency vào runtime.
- `runtimeOnly`: chỉ cần khi chạy.
- `testImplementation`: dependencies chỉ cho test compile/runtime.
- `testRuntimeOnly`: dependencies chỉ cho test runtime.

### 8.1. Khi nào nên đổi sang `api`?

Demo service:

~~~java
public String greet(String rawName)
~~~

chỉ expose `String`, nên `implementation project(':core')` là lựa chọn tốt. Trong một thiết kế khác, giả sử core có type `GreetingResult` và service có public API:

~~~java
// Trích đoạn ví dụ kiến trúc, không phải source của demo runnable.
public GreetingResult createGreeting(String rawName)
~~~

với `GreetingResult` nằm trong `:core`. Khi đó consumer phải biết core type để compile. Service nên xem `api project(':core')`, hoặc thiết kế lại API để không rò rỉ core-specific contract. Đừng thay tất cả `implementation` thành `api` vì “cách đó compile được”: nó làm compile classpaths rộng hơn và tăng coupling.

### 8.2. Độ lớn classpath và build avoidance

Một module dùng `api` quá nhiều sẽ khiến transitive compile classpaths tăng, làm nhiều modules phải kiểm tra recompilation khi upstream public APIs đổi. `implementation` cho dependencies nội bộ có thể giúp giảm sự lan truyền ABI và tận dụng **compilation avoidance** khi phù hợp.

Nhưng đừng hứa “implementation thì core không bao giờ được build”: service runtime vẫn cần core artifact. Những thay đổi trong core có thể làm service tests phải chạy lại khi runtime classpath inputs thay đổi, dù service Java sources không cần recompile.

### 8.3. Tránh file-based dependency tới outputs của module khác

Ví dụ **không nên dùng**:

~~~groovy
dependencies {
    implementation files('../core/build/libs/core.jar')
}
~~~

Điều này phụ thuộc tên JAR và trạng thái file đã tồn tại, mất thông tin variant/transitive dependencies và có thể không tự build producer. Gradle project dependency:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

là cách phù hợp hơn trong cùng multi-project build. Nếu `:core` là project ở repository ngoài, dùng published Maven coordinate hoặc composite build có mô hình thay thế dependency.

## 9. Tách dependencies dùng cho test khỏi production graph

Một module kiểm thử độc lập nên có **test sources và test dependencies riêng**:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.0'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Junit test framework chỉ tham gia test runtime của module; không nên khai vào `api` hoặc `implementation` của thư viện sản phẩm nếu business API không yêu cầu nó. Khi service tests cần fake/stub, tạo ở `service/src/test/java`, hoặc dùng fixtures có module/contracts được thiết kế rõ.

### 9.1. Không tham chiếu trực tiếp `core/src/test/java`

Sai lầm thường gặp:

~~~groovy
// Không nên dán vào project: coupling trực tiếp tới source test module khác.
sourceSets {
    test {
        java.srcDirs += '../core/src/test/java'
    }
}
~~~

Cách này trộn test sources, làm tests bị compile/chạy lặp hoặc sai namespace/ownership. Nếu nhiều modules cần một bộ **test data builders** ổn định, dùng **Java Test Fixtures plugin**.

### 9.2. Test fixtures là variant phụ thuộc riêng

Trích đoạn cho module `:core` khi muốn chia sẻ test utilities:

~~~groovy
plugins {
    id 'java-library'
    id 'java-test-fixtures'
}

dependencies {
    testFixturesImplementation 'org.junit.jupiter:junit-jupiter-api:5.12.0'
}
~~~

Các test fixture sources thông thường nằm ở:

~~~text
core/src/testFixtures/java/
core/src/testFixtures/resources/
~~~

Consumer `:service` có thể dùng:

~~~groovy
dependencies {
    testImplementation testFixtures(project(':core'))
}
~~~

Đây là **mẫu mở rộng**, không phải một phần của demo runnable ba modules (demo không có test fixtures files). Java Test Fixtures plugin tạo variant cho fixture, giúp không cần copy test source dirs giữa modules. Chỉ dùng fixture contract khi nó thật sự được chia sẻ; không biến toàn bộ nội bộ của core thành public testing API.

Nếu `testFixtures` code của core import JUnit types trong **public API** fixture, xem xét `testFixturesApi` thay vì `testFixturesImplementation`; scope phải khớp thứ mà consumers cần compile. Còn nếu chỉ dùng JUnit trong implementation fixtures, giữ scope nhỏ nhất.

### 9.3. Integration tests không phải unit tests của upstream

Có thể tổ chức:

~~~text
core/src/test/java/          unit tests của core
service/src/test/java/       unit tests của service
cli/src/test/java/           smoke tests của CLI
integration-tests/           cross-module scenarios
~~~

Nếu integration test cần service và core thật, có thể tạo module `:integration-tests` với dependencies phù hợp hoặc JVM Test Suite riêng. **Không gắn integration tests đắt đỏ vào `:core:test`** nếu mục tiêu là test core nhanh và độc lập.

Việc `:integration-tests:test` cần production outputs của cli/service/core là hợp lý; đó là **integration boundary**. Hãy định nghĩa task/lifecycle riêng và chọn khi CI policy yêu cầu, thay vì làm mọi `:core:test` thành end-to-end test toàn hệ thống.

## 10. CI: chọn phạm vi nhỏ, vẫn bảo đảm chất lượng toàn repo

Một dự án nhiều module thường cần hai mức chạy:

1. **Fast feedback**: test/build module vừa sửa cùng các dependencies cần thiết.
2. **Full verification**: test/build toàn bộ modules để bắt lỗi lan truyền, đặc biệt trên protected branch và release.

Mẫu lệnh:

| Tình huống | Lệnh |
| --- | --- |
| Sửa logic core, muốn unit test core nhanh | `./gradlew :core:test` |
| Sửa service, muốn test service | `./gradlew :service:test` |
| Sửa CLI, muốn smoke test CLI | `./gradlew :cli:test` |
| Merge vào main, chạy tất cả modules | `./gradlew build` |
| Chỉ kiểm toàn bộ unit tests | `./gradlew test` |
| Xem task closure trước khi tối ưu CI | `./gradlew :cli:test --dry-run` |
| CI release yêu cầu all checks rõ ràng | `./gradlew :core:check :service:check :cli:check` |
| Muốn chạy CLI và kiểm stdout | `./gradlew :cli:run --args="Linh"` |

**Cảnh báo quan trọng:** chỉ chạy `:core:test` sau một thay đổi public API của core chưa chắc bảo đảm service/cli vẫn compile hoặc tests pass. API change có thể phá downstream consumers. CI selective cần **impact analysis theo dependency graph**, không chỉ test module “changed”.

### 10.1. Tính tập modules bị ảnh hưởng

Với graph:

~~~text
:cli  → :service → :core
~~~

Nếu thay:

- **`:cli`**: thông thường chỉ `:cli` và integration scenarios phụ thuộc CLI chịu tác động.
- **`:service`**: test `:service` và `:cli` có thể bị ảnh hưởng vì cli dùng service.
- **`:core`**: cả `:core`, `:service`, `:cli` có thể bị ảnh hưởng.

**Tập ảnh hưởng để test** thường là module thay đổi + **reverse dependents** (các module ở phía trên dùng nó), không chỉ dependency closure ở phía dưới. Trong khi đó **task producer closure** khi chạy test một module đi **xuống upstream** để chuẩn bị artifacts. Hai hướng này khác nhau.

Ví dụ nếu thay core, một chiến lược CI thận trọng:

~~~bash
./gradlew :core:test :service:test :cli:test
~~~

Nếu chỉ thay CLI Java main, chạy `:cli:test` có thể đủ cho fast PR feedback, nhưng vẫn có thể cần full build theo branch policy.

### 10.2. Không xây heuristic “sửa thư mục nào chỉ test thư mục đó” mà không hiểu ABI

Một thay đổi nhỏ ở core có thể sửa public method, exceptions, semantics hoặc resource behavior; service/cli tests cần bắt regressions. Ngược lại, một comment-only change có thể không yêu cầu toàn bộ tests. Một hệ thống impact analysis tin cậy cần khai dependency DAG, paths, ABI changes và chính sách release.

Nếu chưa có tooling impact analysis đáng tin, ưu tiên full verification trên protected branch; đừng đánh đổi tính đúng đắn chỉ để giảm vài phút CI.

### 10.3. Một invocation có thể giảm chi phí so với nhiều invocation

Lệnh:

~~~bash
./gradlew :core:test :service:test :cli:test
~~~

có thể tốt hơn ba bước CI độc lập nếu tất cả được chạy trong cùng máy, vì dùng chung Gradle Daemon, configuration và task graph. Tuy nhiên tách jobs theo module có thể giúp cô lập log và chạy parallel CI; cần cân đối chi phí máy, artifact caching và dependencies.

Không thực thi `--parallel` chỉ để “thấy nhanh hơn”: nó chỉ tăng khả năng chạy tasks độc lập cùng lúc, vẫn tuân DAG và bị giới hạn workers/memory. Đo hiệu năng thực tế trước khi đặt mặc định.

## 11. Hiểu task graph và trạng thái thực thi

Một task thuộc graph không có nghĩa task action sẽ chạy lại:

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `UP-TO-DATE` | Inputs/outputs và history không đổi | `:core:compileJava` khi Java source/classpath không đổi |
| `NO-SOURCE` | Task không có source input phù hợp | `processResources` khi không có resource files |
| `FROM-CACHE` | Output task cacheable được khôi phục từ Build Cache | Compiled classes từ cache |
| `SKIPPED` | Action bị bỏ theo điều kiện/quy tắc; dry-run cũng không chạy actions | `onlyIf` false hoặc dry-run |
| `FAILED` | Task không hoàn tất | JUnit assertion fail, Java compiler error |

**Build Cache** có thể tái sử dụng outputs của task đã được tính cache key đúng. **Configuration Cache** tái sử dụng trạng thái configuration/task graph. Chúng khác với **dependency cache** lưu JAR/metadata tải từ Maven Central.

### 11.1. Upstream production tasks được tái sử dụng thế nào?

Khi chạy:

~~~bash
./gradlew :service:test
./gradlew :cli:test
~~~

ở lần thứ hai, nhiều task upstream có thể `UP-TO-DATE` thay vì compile lại. Đây là hành vi đúng. Đừng ép `clean` trước mọi lần test để “chắc chắn” các modules có build; làm vậy phá lợi ích incremental/up-to-date.

### 11.2. Gradle không bảo đảm mọi project đều được test khi một leaf task được chọn

Ví dụ:

~~~bash
./gradlew :cli:build
~~~

có thể được đánh dấu thành công dù `:core:test` đang chứa một assertion fail **mà không được chọn trong invocation đó**. Đây là lý do cần phân biệt mục tiêu **module-level verification** với **repository-wide verification**; không phải lỗi Gradle.

Đừng sửa bằng cách thêm `dependsOn(':core:build')` vào mỗi downstream build: như vậy làm phát sinh coupling chéo và khó mở rộng. Hãy dùng root task selector/CI target riêng để chạy tất cả tests.

## 12. Giảm coupling build logic giữa projects

Mỗi subproject nên khai báo plugins, repositories, dependencies và task config liên quan trong chính scope của mình hoặc qua **convention plugin** được áp dụng rõ ràng.

### 12.1. Vấn đề của `allprojects`/`subprojects` điều chỉnh mutable state

Ví dụ:

~~~groovy
// Anti-pattern trong build logic mở rộng:
subprojects {
    tasks.named('test') {
        useJUnitPlatform()
    }
}
~~~

Đoạn này vừa giả định mọi subproject đều có `test` task, vừa là **cross-project configuration** từ root. Nó có thể gây khó khăn cho Isolated Projects và cấu hình song song khi dự án mở rộng.

Nên đóng gói Java conventions thành plugin dùng lại như `company.java-library-conventions` hoặc `company.java-test-conventions`, rồi **mỗi module áp dụng vào chính nó**. Khi đó shared policy được quản lý tập trung nhưng không cần đọc/đổi mutable state của project khác.

### 12.2. Convention plugins thay cho copy–paste dài hạn

Ví dụ **trích đoạn kiến trúc**, không phải phần của demo ba module runnable:

~~~text
build-logic/
  build.gradle
  src/main/groovy/company.java-library-conventions.gradle
core/build.gradle
service/build.gradle
cli/build.gradle
~~~

`build-logic/build.gradle` có thể apply `groovy-gradle-plugin`; root `settings.gradle` dùng `pluginManagement { includeBuild('build-logic') }`, rồi core/service apply plugin convention. Nội dung quy ước có thể đặt Java 17 toolchain, JUnit versions và `useJUnitPlatform()` tập trung.

Trong demo đầu tiên, ba file build.gradle có một ít cấu hình lặp để người học **nhìn rõ tính độc lập** của từng module. Khi chuyển sang production, hãy đưa phần trùng vào convention plugins đã được test; đừng mặc định copy–paste vô hạn.

### 12.3. Isolated Projects và configuration cache

Gradle có tính năng **Isolated Projects** (trạng thái hỗ trợ/phạm vi có thể thay đổi theo phiên bản). Khi bật, build logic trong một project không được tự ý đọc/đổi mutable state của project khác trong configuration. Đây là lý do chiến lược convention plugins và declarative project dependencies thường phù hợp hơn root script can thiệp xuyên module.

**Không khẳng định** mọi phiên bản Gradle đều có cùng hỗ trợ isolated projects hoặc bật mặc định. Đọc tài liệu của Gradle distribution đang dùng, kiểm `--version` và migration guide, rồi test dần. Không nhầm isolated project configuration với việc test tasks của modules có thể chạy độc lập.

### 12.4. Đừng dùng `evaluationDependsOn` để chữa module wiring

Nếu một project cần biết giá trị của project khác chỉ để xác định JAR path, thường nên chuyển sang **project dependency/outgoing variant** hoặc shared convention plugin. `evaluationDependsOn` can thiệp thứ tự cấu hình chứ không thể thay thế dependency metadata và có thể làm mất khả năng configuration isolation.

Tương tự, truy cập `project(':core').tasks.getByName('jar')` từ script của cli để lấy output là dạng coupling chặt; ưu tiên `implementation project(':core')` hoặc artifact/variant riêng nếu consumer cần output đặc biệt.

## 13. Thiết kế đồ thị không chu trình và kiểm boundaries

### 13.1. Phát hiện cycle

Giả sử:

~~~text
:core → :service → :cli → :core
~~~

Ở đây cycle làm module không có hướng build hợp lý. Nếu core cần một interface do service triển khai, hãy đưa **interface/contract** vào core (hoặc một module api thuần), để service implement nó, cli wire service; không ép core phụ thuộc service implementation.

Một refactor thường dùng:

~~~text
          :cli
            |
            v
        :service
            |
            v
        :core-api
~~~

và adapter implementation nằm ở module ngoài cùng tùy architecture. Điều cần bảo đảm là graph của project dependencies vẫn không cycle.

### 13.2. Không biến `common` thành một “god module”

Nếu mọi module đều thêm `implementation project(':common')`, rồi `common` chứa database, Spring, UI helpers, logging, HTTP và domain logic, `common` trở thành điểm ghép chặt. Mỗi thay đổi có thể invalidate nhiều downstream classpaths/tests.

Chỉ tách thư viện dùng chung khi có **contract rõ, ít dependencies và owner**. Nếu một helper quá nhỏ và chỉ được dùng ở một module, có thể để ở module đó thay vì ép mọi thứ vào common.

### 13.3. Module independence khác microservices independence

Ba Gradle subprojects trong demo vẫn là **một build và một repository**. Chúng không phải ba microservices deploy riêng chỉ vì có `:core`/`:service`/`:cli`. Deployment boundary, runtime network boundary và release ownership cần thiết kế riêng. Hãy gọi đúng khái niệm để tránh biến mọi module thành một service phức tạp.

## 14. Khi nào dùng composite build?

Multi-project build dùng:

~~~groovy
include 'core', 'service', 'cli'
~~~

để khai các subprojects thuộc cùng một Gradle build. Khi có **hai Gradle builds độc lập**, có thể dùng **composite build**:

~~~groovy
includeBuild('../shared-library')
~~~

Đây là trích đoạn từ `settings.gradle` của một build khác, không phải file demo chính. Composite build có cơ chế dependency substitution từ published module coordinate sang source build được include khi phù hợp. Nó giúp các repository/builds phát triển cùng nhau mà vẫn có build identity riêng.

Không tự thay mọi `project(':core')` thành `includeBuild`: đó là giải pháp cho một ranh giới build khác, đòi hỏi coordinate matching, plugin management và dependency substitution đúng. Chỉ chọn composite khi tách build thật sự có lợi.

## 15. Quy trình chẩn đoán khi chỉ test một module mà Gradle chạy quá nhiều

| Hiện tượng | Nguyên nhân thường gặp | Hướng giải quyết |
| --- | --- | --- |
| `:cli:test` kéo `:core:jar`/`:service:jar` | Project dependencies cần production artifacts | **Bình thường**, kiểm đúng variants |
| `:cli:test` kéo `:core:test` | Task wiring thủ công hay dependency vào upstream `build` | Kiểm `dependsOn`/custom plugins, bỏ ép test nếu không phải requirement |
| `:service:test` fail vì core compile error | Service cần core artifact, upstream source không compile | Sửa core hoặc điều chỉnh contract |
| `:cli:build` pass nhưng `:core:test` fail ở lệnh riêng | Chỉ chọn leaf build, không chọn upstream verification | CI full verification dùng root selector `build` |
| Root `test` chạy tất cả tests | Task selector từ root | Dùng `:module:test` cho module riêng |
| `:test` không tìm thấy | Root không có task `test` | Dùng `test` hoặc `:module:test` |
| `:cli:test` không thấy `GreetingService` | Thiếu `implementation project(':service')` | Khai project dependency và kiểm compileClasspath |
| `GreetingService` chạy nhưng thiếu core runtime | Dependency wiring sai/đã exclude core variant | Kiểm `:cli:runtimeClasspath`/`:service:runtimeClasspath` |
| Lỗi circular task dependency | Cycle trong project/module dependencies hoặc task dependsOn | Vẽ graph, tách contract, bỏ chiều phụ thuộc ngược |
| Module không thấy JUnit | Chỉ khai JUnit ở module khác | Khai `testImplementation` của module đang test |
| Module mới không có `test` task | Chưa apply Java/test plugin phù hợp | Kiểm `plugins` của module, `tasks --all` |
| `:cli:run` không tồn tại | Không apply `application` trong cli | Apply Application plugin/configure mainClass |
| Tests trùng nhau nhiều modules | Copy source test directories giữa modules | Tách fixtures, không gom src/test thủ công |
| Gradle build chậm vì `clean` luôn chạy | Mất incremental/up-to-date | Chỉ clean khi có lý do |
| Cross-project configuration warning | Root script đọc/đổi state subprojects | Dùng convention plugins, sửa theo isolated-project guidelines |
| `--parallel` không tăng tốc | DAG quá tuyến tính hoặc thiếu workers/memory | Đo task graph, giảm coupling, tăng independent branches |
| Module split nhưng API bị lộ quá nhiều | Dùng `api` cho mọi dependency | Giữ `implementation` cho internal deps |
| Consumer chỉ chạy được sau manual copy JAR | Dùng `files('../...jar')` thay vì project dependency | Dùng outgoing variant hoặc `project(':...')` |
| Báo cáo test module này lẫn module khác | Gộp output folder/test source sets không đúng | Để mỗi module có `build/` và report riêng |
| CI chọn module theo changed directory nên bỏ sót regression | Thiếu reverse-dependency impact analysis | Test modules phụ thuộc module đã đổi, và full gate ở protected branch |

### 15.1. Debug step-by-step

~~~text
1. settings.gradle có include module đúng?
                  |
                  v
2. Đã khai implementation/api/testImplementation đúng project paths?
                  |
                  v
3. ./gradlew projects hiển thị đúng project hierarchy?
                  |
                  v
4. :module:dependencies --configuration compileClasspath/runtimeClasspath?
                  |
                  v
5. :module:test --dry-run có task nào được chọn?
                  |
                  v
6. Upstream tasks đó là artifact producer hay upstream test/check?
                  |
                  v
7. Tại sao task chạy lại? --info, UP-TO-DATE, FROM-CACHE?
                  |
                  v
8. Đã chọn mục tiêu local-module hay repo-wide verification?
~~~

## 16. Thực hành nâng cao và câu hỏi tự đánh giá

### Bài 1 — phân biệt project graph và task graph

**Câu hỏi:** Vì sao `./gradlew :service:test` có thể thực thi `:core:compileJava` nhưng không thực thi `:core:test`?

**Đáp án:** `service` dùng production artifact của core qua `implementation project(':core')`. Gradle cần producer tasks của core cho test classpath service, nhưng không có task dependency từ service test đến core test. Core test là một **verification goal riêng**.

### Bài 2 — sửa core, module nào có thể bị ảnh hưởng?

Đồ thị `:cli → :service → :core`. Thay public API của core có thể phá compile/runtime ở service và cli. Full impact set có thể gồm cả ba; chỉ chạy `:core:test` chưa đủ bảo đảm tương thích downstream.

### Bài 3 — làm sao chỉ chạy CLI smoke test?

~~~bash
./gradlew :cli:test --tests 'demo.cli.MainSmokeTest'
~~~

Gradle vẫn chuẩn bị service/core production artifacts khi cần. Nó không phải test suite của service và core.

### Bài 4 — test toàn bộ module từ root

~~~bash
./gradlew test
~~~

Chọn tests ở các subprojects. Với demo có tổng cộng 6 test methods. Khác với `./gradlew :cli:test`.

### Bài 5 — cố tình tạo cycle

Thêm `implementation project(':cli')` vào `core/build.gradle` và quan sát failure hoặc cycle diagnostics khi task graph cần resolve. Sửa bằng cách khôi phục hướng dependency ban đầu; không dùng `mustRunAfter` để giấu cycle logic.

### Bài 6 — chọn `api` hay `implementation`

`GreetingService.greet(String)` trả về `String` nhưng dùng `NameFormatter` trong thân hàm: chọn **`implementation project(':core')`**. Nếu public method expose type thuộc core package, xem lại API boundary hoặc dùng **`api project(':core')`**.

### Bài 7 — thử JUnit dependency chỉ ở core

Xóa `testImplementation` trong service rồi chạy `:service:test`. Service test source không tìm `org.junit.jupiter.api.Test`, dù core có JUnit. Tại sao? Vì test-specific dependencies của core không tự trở thành test compile classpath của service.

### Bài 8 — vì sao không dùng `:core:build` như dependency của `:service:compileJava`?

Vì nó ép packaging, tests và checks của core chỉ để compile service, vừa thừa việc vừa không mô hình hóa API/classpath phù hợp. Khai `project(':core')` trong dependency configuration thay thế.

### Bài 9 — kiểm stdout của demo

~~~bash
./gradlew :cli:run --args="Linh"
~~~

Java program in chính xác `Hello, Linh!`. Nếu không truyền args, in `Hello, guest!`. Task `:cli:run` thuộc Application plugin; `:core:run`/`:service:run` không mặc định tồn tại.

### Bài 10 — khi nào dùng test fixtures?

Khi service/cli tests cần **test data builder/helper** được chia sẻ ổn định từ core, áp `java-test-fixtures` ở core và dùng `testImplementation testFixtures(project(':core'))` ở consumer. Tránh copy `core/src/test/java` sang các modules khác.

### Bài 11 — CI changed-files heuristic

Nếu PR chỉ sửa `core/src/main/java`, có nên mặc định chỉ chạy `:core:test`? Không. Core là upstream dependency của service/cli, nên cần đánh giá reverse dependents; protected branch nên chạy full verification.

### Bài 12 — module hoạt động nhưng chạy lệnh `./gradlew :test` thất bại

Root demo không áp Java plugin, nên không có root task `:test`. Cần dùng `./gradlew test` (selector across subprojects) hoặc `./gradlew :core:test` (một module). Prefix colon quyết định project path.

### Bài 13 — so sánh Module Graph và Compile Classpath

`:cli` chỉ khai `implementation project(':service')`; do service khai `implementation project(':core')`, cli **không mặc định có core API trên compile classpath** vì core là implementation detail của service. Nhưng cli runtime classpath vẫn có core để GreetingService chạy được.

### Bài 14 — design criteria khi tách module tiếp

Bạn muốn tách `:service` thành `:greeting-service` và `:account-service`. Trước hết xác định contracts, ownership và dependency directions, tránh hai service modules phụ thuộc vòng lẫn nhau. Sau đó cập nhật `settings.gradle`, dependencies, tests, CI task paths và artifact publishing policy.

## 17. Checklist thiết kế multi-project build có test/build độc lập

1. Mỗi module có trách nhiệm, public API và owner đủ rõ không?
2. Project dependency graph có hướng, không cycle?
3. Dùng `settings.gradle include` đúng project paths, không coi thứ tự include là dependency?
4. Module dùng dependency `project(':module')` thay vì lấy trực tiếp file JAR/output của nhau?
5. `api`/`implementation` được chọn theo public ABI boundary, không expose quá nhiều dependencies?
6. Mỗi Java module tự có `java-library`/`application`, toolchain, test framework và task `test`/`build` thích hợp?
7. `:module:test` có chạy **test của module đó**, chỉ kéo upstream production tasks cần thiết?
8. `:module:build` không vô tình chạy mọi upstream `build`/`test` do custom `dependsOn` sai?
9. Có root selector `test`/`build` để verify repository-wide, không nhầm `:test`/`:build`?
10. Source `src/test` của modules không bị import/copy chéo, test fixtures có variant riêng nếu cần?
11. Integration tests được tổ chức thành mục tiêu riêng khi phục vụ cross-module scenarios?
12. Có cách quan sát graph qua `--dry-run` và dependencies qua `dependencies --configuration`?
13. Khi thay API upstream, CI có kiểm các reverse dependents?
14. Shared build logic được đóng gói convention plugins, tránh `subprojects { }` mutate state chéo?
15. Có Gradle Wrapper và Java 17 toolchain nhất quán giữa dev/CI?
16. Đã phân biệt task selection independence với repository/build isolation thực sự?
17. Parallel execution có được đo hiệu quả, vẫn bảo toàn declared dependencies và input/output?
18. Build Cache/Configuration Cache được hiểu là tối ưu, không phải phép thay thế kiểm thử chất lượng?

## 18. Tài liệu Gradle chính thức

- [Gradle — Structuring Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds_intermediate.html): task selector từ root, project paths và fully qualified task names.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): settings include, project hierarchy và build life cycle.
- [Gradle — Declaring Dependencies Between Subprojects](https://docs.gradle.org/current/userguide/declaring_dependencies_between_subprojects.html): project dependencies và variant-aware artifact producers.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `:subproject:task`, task selectors, `--dry-run`, `--info`.
- [Gradle — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `api` vs `implementation` và consumer classpaths.
- [Gradle — The Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): `run`, mainClass và runtime classpath.
- [Gradle — Java Test Fixtures Plugin](https://docs.gradle.org/current/userguide/java_testing.html#sec:java_test_fixtures): `testFixtures` variants và share test helpers.
- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): tổ chức integration test suites.
- [Gradle — Sharing Build Logic](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): convention plugins và build-logic.
- [Gradle — Isolated Projects](https://docs.gradle.org/current/userguide/isolated_projects.html): ràng buộc project isolation và configuration.
- [Gradle — Gradle Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): tái sử dụng task outputs hợp lệ.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): tái sử dụng trạng thái configuration/task graph.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): khi có nhiều Gradle builds độc lập được kết hợp.
