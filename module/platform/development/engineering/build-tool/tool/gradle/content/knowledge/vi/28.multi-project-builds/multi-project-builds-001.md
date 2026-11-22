# Khi nào tách module và cách xác định ranh giới phụ thuộc trong Gradle

## 1. Bài toán: khi một ứng dụng Java lớn lên

Một dự án Java nhỏ thường chỉ cần một `build.gradle.kts` và một tập `src/main/java`. Khi số lượng tính năng, teams, dependencies và entry points tăng, tất cả mã trong một source set có thể bắt đầu gây khó khăn:

- Thay đổi một lớp persistence làm bộ phận khác phải recompile hoặc kiểm tra lại nhiều hơn cần thiết.
- Code domain vô tình import HTTP framework/JDBC driver vì mọi thư viện cùng nằm trên compile classpath.
- Business rule vừa được dùng ở CLI vừa được dùng ở web server, nhưng mỗi nơi copy một phiên bản.
- Một service phụ thuộc trực tiếp vào DTO nội bộ hoặc repository class của service khác.
- Unit tests muốn chạy nhanh nhưng phụ thuộc container/database setup của cả ứng dụng.
- Public API thay đổi không được review như một contract; code ở nhiều nơi dựa vào implementation details.
- Một module `common` phình ra và mọi thành phần đều phụ thuộc nó.

**Tách module** là tạo ra các thành phần có trách nhiệm rõ, một public API cần thiết và hướng dependency được quản lý. Trong Gradle, một cách phổ biến là **multi-project build**: cùng một `settings.gradle(.kts)` khai báo nhiều subprojects, mỗi project có plugins, dependencies và tasks riêng.

Điều quan trọng: **không phải nhiều module luôn tốt hơn**. Một subproject mới có chi phí build configuration, classpath, dependency graph, API coordination, testing và maintenance. Nếu tách chỉ vì số file Java nhiều, hoặc vì muốn mỗi package có build script riêng, hệ thống có thể khó phát triển hơn.

Mục tiêu của bài này:

1. Hiểu khi nào module boundary đáng tạo và khi nào chưa.
2. Phân biệt Gradle subproject, Java package, source set, JPMS module và composite build.
3. Đánh giá cohesion, coupling, ownership, change patterns và public contract.
4. Vẽ directed acyclic graph (DAG) để kiểm soát hướng phụ thuộc.
5. Viết `settings.include` và `dependencies { implementation(project(":...")) }`.
6. Hiểu `java-library` với `api`/`implementation`/`compileOnlyApi`.
7. Chạy ví dụ Java 17+ đầy đủ gồm `:domain`, `:service`, `:app`.
8. Kiểm tra dependencies, task graph, variants, tests và performance.
9. Tách dần một monolith mà không phá hợp đồng của consumer.

## 2. Có bao nhiêu loại “module”?

Từ module được dùng cho nhiều thứ. Phân biệt trước khi ra quyết định.

| Đơn vị | Cách khai báo | Ranh giới thực tế |
| --- | --- | --- |
| Java package | `package demo.domain;` | Namespace và một số Java visibility rules |
| Source set | `sourceSets.main`, `sourceSets.test` | Nguồn, compilation tasks và classpaths theo nhóm |
| Gradle subproject | `include(":domain")` trong settings | Plugins, dependencies, tasks, outgoing variants/artifacts riêng |
| Java JPMS module | `module-info.java` | Java language/runtime module visibility qua `requires`, `exports`, `opens` |
| Included build | `includeBuild("build-logic")` | Một Gradle build riêng được phối hợp qua composite builds |
| Binary module phát hành | Maven artifact với group:name:version | API/version/compatibility với consumer độc lập |
| Deployable service | Container/process/release độc lập | Network, dữ liệu, vận hành và deployment contracts |

**Gradle subproject không tự tạo Java JPMS module.** Không có `module-info.java` thì project Java thông thường vẫn chạy trên classpath. Ngược lại, một subproject có thể chứa Java module descriptor khi thật sự cần JPMS.

Một package mới có thể giúp code dễ tìm, nhưng các public classes của một source set vẫn nhìn thấy nhau trên cùng compile classpath. Subproject tạo ra **ranh giới dependency** rõ hơn: consumer phải khai báo project dependency để truy cập classes/variants.

### 2.1. Một root project có thể không có Java source

~~~text
modular-greeter/
├── settings.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── domain/
│   ├── build.gradle.kts
│   └── src/main/java/...
├── service/
│   ├── build.gradle.kts
│   └── src/main/java/...
└── app/
    ├── build.gradle.kts
    └── src/main/java/...
~~~

Root chỉ quản lý settings và Wrapper là hợp lệ; không bắt buộc có root `build.gradle.kts` hoặc root `src/main/java`. Một số dự án đặt build conventions ở root hoặc included build riêng, nhưng không nên vô tình biến root thành một module nghiệp vụ khổng lồ.

### 2.2. Subproject không đồng nghĩa microservice

Ba Gradle projects vẫn có thể được đóng gói thành **một ứng dụng JVM** và deploy cùng nhau. Nếu muốn ba services có database, network API, version và release độc lập, đó là vấn đề kiến trúc rộng hơn Gradle multi-project. Module boundary giúp cấu trúc code, không tự cấp operational independence.

## 3. Khi nào nên tách một module mới?

Hãy tìm **tín hiệu trách nhiệm và dependency**, không tìm một ngưỡng số class cứng.

| Tín hiệu | Ví dụ | Giá trị của module boundary |
| --- | --- | --- |
| Trách nhiệm nghiệp vụ độc lập | Pricing, inventory, identity | Bảo vệ rules và public API |
| Tập dependencies khác | Domain không cần HTTP/JDBC, adapter cần | Tránh leak framework vào domain |
| Tốc độ thay đổi khác nhau | UI đổi thường xuyên, core ổn định | Giảm lan truyền rebuild/review |
| Reuse có thật | CLI và HTTP server dùng chung validation | Không copy logic sang nhiều apps |
| Team ownership rõ | Nhóm payment, nhóm analytics | Contract và review trách nhiệm |
| Tests có mức cô lập khác | Pure unit tests và DB integration tests | Chạy targeted tests nhanh |
| Cần public binary API | Library cho nhiều ứng dụng | Version/compatibility policy |
| Có nhiều executable | Worker, CLI, server | Module entry points có plugin riêng |
| Consumer chỉ cần interface | Adapter có thể thay triển khai | Dependency inversion rõ hơn |

**Ví dụ:** luật tính thuế là logic nghiệp vụ thuần Java, không nên bị buộc compile cùng JDBC driver hoặc web controller. Một module `:tax-domain` có thể tách khỏi `:tax-jdbc` và `:tax-web`. Các adapters phụ thuộc domain API; domain không import ngược adapter.

### 3.1. Khi chưa nên tách

- CLI nhỏ với 5–10 classes, cùng vòng đời và không có consumer khác.
- Mọi class thay đổi trong cùng một use case, ranh giới còn biến động liên tục.
- Module dự kiến chỉ để chứa một helper rất nhỏ dùng một lần.
- Một “module interface” không có contract consumer thực tế.
- Việc tách tạo nhiều project 2 class nhưng mỗi thay đổi phải chỉnh ba public APIs.
- Bài toán hiện tại là tên package khó hiểu; refactor packages có thể đủ.
- Không có tests cho API hiện tại, tách ồ ạt sẽ làm khó xác nhận không đổi behavior.

Tách module nên **giảm coupling ròng**, không chỉ chuyển coupling sang nhiều build scripts và project paths.

## 4. Cohesion, coupling và ownership

**High cohesion** nghĩa là nội dung module cùng phục vụ một trách nhiệm thống nhất. **Low coupling** nghĩa là module chỉ biết những interfaces/contracts thật sự cần của module khác.

Ba câu hỏi tốt để kiểm tra boundary:

1. **Lý do thay đổi:** nhóm classes trong module có thường đổi cùng nhau vì một nhu cầu nghiệp vụ không?
2. **Quyền sở hữu:** team nào chịu trách nhiệm API/data của module?
3. **Phụ thuộc:** có thể thay implementation nội bộ mà không sửa consumers không?

Một module `:shared` chứa `StringUtils`, repository implementation, security token logic và billing rules là **low cohesion**. Vì ai cũng dùng “shared”, thay đổi ở đó có thể ảnh hưởng toàn build: **high coupling**.

### 4.1. Coupling không chỉ là Java import

Hai modules không import lẫn nhau vẫn có thể bị gắn chặt bởi:

- Shared database tables bị sửa trực tiếp không qua data owner.
- Reading `../other-module/build/generated/config.json`.
- Cùng ghi một tmp file hoặc port trong tests.
- Dựa vào global singleton/state của một runtime container.
- Hợp đồng message format không được version hóa.
- “Service A luôn chạy trước Service B” nhưng không có readiness protocol.
- Cùng secrets/config file copy vào hai modules mà không quản lý.

Tách thư mục Gradle không loại bỏ được các hidden dependencies. Khi review architecture, cần xem cả data, runtime, build và test boundaries.

### 4.2. Package/module naming

Tên module nên diễn tả **trách nhiệm**, ví dụ `:billing-domain`, `:billing-jdbc`, `:cli`. Tránh names không rõ như `:misc` hoặc `:everything-shared`. Tên Gradle project path và Java package không bắt buộc giống nhau, nhưng nên có mapping nhất quán để developer đọc dễ.

## 5. Vẽ DAG phụ thuộc trước khi viết code

Mũi tên trong bài mang nghĩa **“consumer phụ thuộc producer”**:

~~~text
:app
  |
  v
:service
  |
  v
:domain
~~~

- `:app` được phép biết contract của `:service`.
- `:service` được phép biết domain types.
- `:domain` **không** được phụ thuộc ngược vào service hoặc app.
- Graph không có chu trình, nên là **directed acyclic graph (DAG)**.

Một dependency matrix:

| Consumer / Producer | :domain | :service | :app |
| --- | --- | --- | --- |
| **:domain** | — | Không | Không |
| **:service** | Có | — | Không |
| **:app** | Có qua service public API | Có | — |

Nếu app sử dụng domain public API **ngoài** hợp đồng do service cung cấp, có thể khai báo thêm direct `implementation(project(":domain"))` để làm rõ dependency chủ ý. Không nên phụ thuộc ngầm vào một transitive library khi nó là dependency thật sự của chính app.

### 5.1. Cycle là dấu hiệu kiến trúc, không phải vấn đề thứ tự task

Sai:

~~~text
:domain -> :service -> :domain
~~~

Điều này thường xuất hiện khi domain cố khởi tạo một concrete service, trong khi service lại sử dụng domain model. Đừng chữa bằng `mustRunAfter` hoặc `dependsOn`: thứ tự task không biến circular source dependency thành architecture hợp lệ. Cần chuyển contract xuống abstraction ổn định hoặc thay ownership của classes.

### 5.2. Dependency inversion không có nghĩa tạo một module chứa mọi interfaces

Nếu domain cần một storage operation, hãy định nghĩa interface port ở tầng được consumer sở hữu rồi adapter triển khai. Không mặc định dựng một `:interfaces` chung cho mọi class. Chỉ tách interface thành module riêng khi có lý do quản lý API, reuse hoặc release xác đáng.

## 6. Ví dụ đầy đủ: ba module Java 17+ chạy được

Đây là một demo hoàn chỉnh và **không dùng third-party production dependency** để tập trung vào Gradle module graph. Ba module:

- `:domain`: record `Greeting`.
- `:service`: `GreetingService` với public method trả về `Greeting`.
- `:app`: CLI Main sử dụng service rồi in kết quả.

Chúng được build cùng một Gradle multi-project, nhưng mỗi module có plugins và dependencies riêng.

### 6.1. Cấu trúc file

~~~text
modular-greeter/
├── settings.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── domain/
│   ├── build.gradle.kts
│   └── src/main/java/demo/domain/Greeting.java
├── service/
│   ├── build.gradle.kts
│   └── src/main/java/demo/service/GreetingService.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/app/Main.java
~~~

Yêu cầu có **Gradle Wrapper hợp lệ** và JDK 17 hoặc toolchain Java 17 provision đúng. Không thể tạo Wrapper bằng cách đặt tên một file trống là `gradlew`.

### 6.2. settings.gradle.kts

~~~kotlin
rootProject.name = "modular-greeter"
include(":domain", ":service", ":app")
~~~

`include(...)` đăng ký các projects và Gradle paths. **Nó không tự khai báo các cạnh dependency**. Những cạnh đó thuộc `dependencies` của project consumer.

### 6.3. domain/build.gradle.kts

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}
~~~

**domain/src/main/java/demo/domain/Greeting.java:**

~~~java
package demo.domain;

public record Greeting(String text) {
}
~~~

`record` có trong Java 17. Module domain không có task `run` hay method main; dùng `java-library` là phù hợp. Nó không import các classes từ service/app, không cần repository cấu hình vì chỉ dùng JDK.

### 6.4. service/build.gradle.kts

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

dependencies {
    api(project(":domain"))
}
~~~

**service/src/main/java/demo/service/GreetingService.java:**

~~~java
package demo.service;

import demo.domain.Greeting;

public final class GreetingService {
    public Greeting greet(String name) {
        return new Greeting("Hello, " + name + "!");
    }
}
~~~

`:service` có public method trả type `Greeting` từ `:domain`. Vì vậy `api(project(":domain"))` là hợp đồng đúng. Nếu dùng `implementation`, chính service có thể compile, nhưng consumer compile public method có thể thiếu type `Greeting` trên classpath.

### 6.5. app/build.gradle.kts

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    application
}

version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

dependencies {
    implementation(project(":service"))
}

application {
    mainClass.set("demo.app.Main")
    applicationName = "greeter"
}
~~~

**app/src/main/java/demo/app/Main.java:**

~~~java
package demo.app;

import demo.domain.Greeting;
import demo.service.GreetingService;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "Gradle" : args[0];

        GreetingService service = new GreetingService();
        Greeting result = service.greet(name);

        System.out.println(result.text());
    }
}
~~~

App chỉ chịu trách nhiệm entry point, CLI arguments và output. Logic tạo lời chào nằm ở service; domain record làm value contract.

### 6.6. Chạy bằng Gradle

Linux/macOS:

~~~bash
./gradlew :app:run --args="Ada" --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :app:run --args="Ada" --console=plain
~~~

**Dòng do Java Main in ra:**

~~~text
Hello, Ada!
~~~

Nếu không truyền args:

~~~bash
./gradlew :app:run --console=plain
~~~

**Dòng do Java Main in:**

~~~text
Hello, Gradle!
~~~

Console Gradle còn có task status, warning hoặc BUILD SUCCESSFUL thay đổi theo môi trường. Các dòng nêu trên là **stdout từ chương trình**, không phải mô phỏng toàn bộ build log.

### 6.7. Task graph do project dependency tạo

~~~text
:domain:compileJava
         |
         v
:service:compileJava
         |
         v
:app:compileJava
         |
         v
      :app:run
~~~

Đây là **sơ đồ phụ thuộc logic của compile outputs**, không phải khẳng định Gradle luôn xây `jar` mỗi bước hay task graph có đúng bốn nodes. Java plugin còn có tasks resources/classes và Gradle có thể chọn classes directories/JAR variants theo consumer, version và cấu hình.

Bạn có thể quan sát:

~~~bash
./gradlew :app:compileJava --dry-run
./gradlew :app:run --dry-run
./gradlew :app:build --console=plain
~~~

`--dry-run` chỉ lập task graph (thường hiện SKIPPED), không chạy Java. Muốn xác nhận kết quả phải chạy `:app:run` thật.

### 6.8. Build và phân phối

Với Application plugin:

~~~bash
./gradlew :app:installDist
~~~

Dự kiến có launcher:

~~~text
app/build/install/greeter/bin/greeter
app/build/install/greeter/bin/greeter.bat
app/build/install/greeter/lib/...
~~~

Phần `lib` chứa artifacts/dependencies cần chạy app. Không có nghĩa :domain hay :service là services deploy độc lập. Launcher cần Java runtime tương thích trên máy đích, trừ khi có provisioning/bundling JVM riêng.

## 7. Kiểm tra bằng javac/java không phụ thuộc Gradle

Vì demo không có external library, bạn cũng có thể tự compile ba modules để thấy Gradle đang tự động quản lý điều gì.

Linux/macOS, chạy từ root:

~~~bash
mkdir -p out/domain out/service out/app

javac --release 17 -encoding UTF-8 \
    -d out/domain \
    domain/src/main/java/demo/domain/Greeting.java

javac --release 17 -encoding UTF-8 \
    -cp out/domain \
    -d out/service \
    service/src/main/java/demo/service/GreetingService.java

javac --release 17 -encoding UTF-8 \
    -cp out/domain:out/service \
    -d out/app \
    app/src/main/java/demo/app/Main.java

java -cp out/app:out/service:out/domain demo.app.Main Ada
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out\domain,out\service,out\app | Out-Null

javac --release 17 -encoding UTF-8 -d out\domain domain\src\main\java\demo\domain\Greeting.java

javac --release 17 -encoding UTF-8 -cp out\domain -d out\service service\src\main\java\demo\service\GreetingService.java

javac --release 17 -encoding UTF-8 -cp "out\domain;out\service" -d out\app app\src\main\java\demo\app\Main.java

java -cp "out\app;out\service;out\domain" demo.app.Main Ada
~~~

**Stdout chính xác:**

~~~text
Hello, Ada!
~~~

Những lệnh này minh họa thứ tự biên dịch và compile/runtime classpath. Output `out/` do bạn tạo thủ công, khác với `build/` do Gradle quản lý. Khi dùng Gradle, không hardcode đường dẫn classes/JAR của project sibling để lắp classpath; dùng `project(":...")`.

## 8. api hay implementation: quyết định bởi public ABI

Trong Java Library plugin:

- `api`: dependency có type xuất hiện trong **public API/ABI** của module (public method return/parameter, supertype, interface, public field hoặc annotation cần để compile).
- `implementation`: dependency chỉ cần cho **code nội bộ** của module, không nên lộ vào downstream compile classpath.

Ví dụ service:

~~~kotlin
dependencies {
    api(project(":domain"))
}
~~~

vì public method:

~~~java
public Greeting greet(String name)
~~~

trả về `demo.domain.Greeting`. App import `Greeting` và compile được nhờ service expose API dependency.

### 8.1. Sai scope có thể dẫn tới compile failure

Thử **thay thế tạm** trong `service/build.gradle.kts`:

~~~kotlin
dependencies {
    implementation(project(":domain"))
}
~~~

Service vẫn nhìn thấy domain để compile. Nhưng app sử dụng public type `Greeting` có thể nhận compile error vì domain bị ẩn khỏi **consumer compileClasspath**. Đây là bài học về API exposure, không phải “Gradle chạy tasks sai thứ tự”. Trả lại `api(project(":domain"))` sau thí nghiệm.

Nếu không muốn app phụ thuộc domain type, thiết kế service facade trả JDK type thay thế:

~~~java
public String greetText(String name) {
    return new Greeting("Hello, " + name + "!").text();
}
~~~

Đây là **method snippet minh họa**, không có trong demo mục 6 trừ khi thêm. Khi public API của service không còn lộ domain types, `:domain` có thể trở thành `implementation` nếu các public signatures khác cũng không lộ nó.

### 8.2. Ma trận chọn configuration

| Loại dependency | Configuration hợp lý |
| --- | --- |
| Public method return/parameter type từ library khác | `api` |
| Public superclass/interface type | `api` |
| Library chỉ dùng trong method body | `implementation` |
| JDBC driver chỉ tải khi chạy | `runtimeOnly` nếu code compile không trực tiếp cần type |
| Annotation/type cần consumer compile nhưng không cần runtime | `compileOnlyApi` khi thật sự phù hợp |
| Dependency chỉ cần compile module, không cần runtime | `compileOnly` |
| JUnit/Mockito chỉ dùng trong test | `testImplementation` |
| Library chỉ dùng khi chạy tests | `testRuntimeOnly` |

**Ưu tiên `implementation` nếu không cần expose.** Dùng `api` cho mọi thứ khiến classpath downstream lớn, tăng coupling và hạn chế compile avoidance. Ngược lại, cố ép mọi dependency vào `implementation` có thể làm public API không biên dịch được ở consumers.

### 8.3. implementation không biến mất ở runtime

Dependency `implementation` không được export như compile API nhưng vẫn có thể nằm trong **runtime variant** của library. Vì vậy, “internal” không có nghĩa “runtime app sẽ không cần nó”. Java Library plugin mô hình hóa compile và runtime metadata khác nhau.

### 8.4. api không phải fat JAR

`api(project(":domain"))` không merge lớp domain vào file JAR của service. Nó là dependency metadata/variant contract. Khi dùng Application plugin hoặc publishing, Gradle dựng runtime graph và phân phối artifacts theo model. Muốn fat/uber JAR cần packaging strategy riêng.

## 9. apiElements và runtimeElements: cơ chế Gradle làm việc

Một project dependency không chỉ trỏ vào `../service/build/libs/service.jar`. Gradle sử dụng **variant-aware resolution** để chọn artifacts phù hợp consumer.

| Outgoing variant | Consumer dùng cho | Tập dependency |
| --- | --- | --- |
| `apiElements` | Compile against library API | `api` và những type compile-only API phù hợp |
| `runtimeElements` | Chạy library | `api`, `implementation`, `runtimeOnly` theo Gradle model |

Với Java Library plugin, Gradle có thể cung cấp class directories hoặc JAR phù hợp compile/runtime consumer. Không nên giả định `:app:compileJava` luôn chạy `:domain:jar`. Đây là lý do hardcode sibling output path vừa giòn vừa không tận dụng được variant metadata.

**Anti-pattern:**

~~~kotlin
tasks.named("compileJava") {
    dependsOn(":domain:jar", ":service:jar")
}
~~~

Task dependency này chỉ nói “các tasks cần chạy”, không tự **thêm type vào compiler classpath**. Hãy dùng:

~~~kotlin
dependencies {
    implementation(project(":service"))
}
~~~

và để Gradle quyết định artifacts/tasks tương ứng.

### 9.1. Nếu module công bố output không phải JAR

Một project có thể tạo schema ZIP, generated API descriptor hoặc codegen bundle. Trong trường hợp consumer cần artifact đó, mô hình hóa qua **outgoing configuration/variant** hoặc task output provider có provenance. Đừng đọc thẳng `../producer/build/generated/schema.json` rồi dùng `mustRunAfter`; đường dẫn cứng không bảo đảm correct tasks/classpath metadata.

## 10. Hướng phụ thuộc trong kiến trúc nhiều tầng

Một cách minh họa:

~~~text
entrypoints / adapters  ---> application services ---> domain
                 \                         |
                  \                        v
                   ---> infrastructure implementing ports
~~~

Sơ đồ chỉ mô tả **quy tắc kiến trúc**, không phải một code snippet Gradle để paste. Một số ứng dụng dùng hexagonal/clean architecture cho phép infrastructure adapter phụ thuộc **port do application/domain sở hữu**. Application composer ở tầng ngoài chọn adapter implementation.

Ví dụ domain có port:

~~~java
package demo.domain;

public interface GreetingStore {
    void save(Greeting greeting);
}
~~~

Đây là **snippet mở rộng**, không thuộc mã demo runnable. Module `:jdbc-adapter` có thể triển khai `GreetingStore` và phụ thuộc `:domain`. Domain không được import `JdbcGreetingStore` hoặc JDBC driver để khởi tạo concrete adapter.

Nếu app phải wire hai implementation, composition root ở `:app` chịu trách nhiệm lựa chọn runtime implementation. Không để domain viết:

~~~java
// ANTI-PATTERN: domain khong nen buoc vao JDBC adapter.
import demo.jdbc.JdbcGreetingStore;
~~~

Điều đó đảo hướng coupling. Tuy nhiên, không nhất thiết phải tách `:ports` khỏi `:domain` nếu chỉ có một contract nhỏ; số module nên theo ownership và nhu cầu thực tế.

## 11. Theo feature, theo layer hay mô hình lai?

| Chiến lược | Ví dụ | Phù hợp khi |
| --- | --- | --- |
| Theo feature | `:orders`, `:inventory`, `:payments` | Bounded contexts/team ownership rõ |
| Theo layer | `:domain`, `:service`, `:persistence`, `:web` | Muốn kiểm soát dependency rules giữa layers |
| Lai | `:orders-domain`, `:orders-jdbc`, `:orders-api` | Feature lớn có interfaces và adapters khác nhau |
| Theo deployable | `:cli`, `:server`, `:worker` | Nhiều executables dùng chung library |
| Theo thư viện reusable | `:money`, `:time-api` | Contracts nhỏ ổn định dùng nhiều nơi |

Không có công thức tuyệt đối. Đừng tạo `:all-services` và `:all-repositories` theo technology mà để mọi feature phải đi qua đó nếu mục tiêu là ownership theo bounded context.

### 11.1. Đừng tạo một module shared khổng lồ

Module `:common` thường thành nơi đổ mọi utility lẫn business model, rồi mọi module lại cần `:common`. Về lâu dài thay đổi một class ở đó có thể khuấy động toàn build. Nên chia thành các **contracts thực sự có nghĩa** hoặc chuyển logic về owner đúng thay vì nuôi một module chung không biên giới.

### 11.2. Không nên tách chỉ để “tránh import” nội bộ

Tách một class vào project riêng có thể làm developer phải định nghĩa public API không cần thiết. Nếu hai classes thực sự cùng trách nhiệm và luôn thay đổi cùng nhau, giữ cùng module và dùng package-private visibility có thể tốt hơn.

## 12. Cross-feature dependency phải có contract

Ví dụ ứng dụng có `:orders` và `:inventory`. Khi Order use case cần biết tồn kho, không nên kéo nguyên DB repository private của inventory vào order module.

Những lựa chọn:

- Dùng API/port nhỏ với phương thức như `isAvailable(productId)`, ownership rõ.
- Nếu cùng một process, interface module ổn định hoặc provider injection phù hợp.
- Nếu khác deployables, dùng HTTP/gRPC/events theo policy và consumer contract tests.
- Nếu chia sẻ một value object thực sự mang meaning chung, có thể có module contract nhỏ.

**Không đồng nhất deployment dependency với Java project dependency.** Một HTTP client của remote service không cần import executable server class hoặc kéo toàn bộ server runtime library vào consumer.

### 12.1. Data ownership

Hai modules không import nhau nhưng cùng sửa một database table vẫn có coupling. Một boundary tốt xác định entity/data owner, migration policy, và cách các consumers tương tác qua contracts. Nếu chưa thể kiểm soát shared database, split Gradle project chỉ là tổ chức source, không phải cô lập nghiệp vụ hoàn toàn.

## 13. Hiệu năng build: lợi ích có điều kiện

Gradle hỗ trợ compile avoidance, incremental compilation, task output caching và parallel work. Modularization **có thể** giúp giới hạn phần việc cần làm khi thay một module.

Ví dụ:

~~~text
             +--> :feature-a
:shared-api --|
             +--> :feature-b
~~~

Nếu feature-a và feature-b độc lập, Gradle có cơ hội build song song những tasks không phụ thuộc nhau. Nếu chỉ sửa implementation nội bộ và API/ABI không đổi, downstream Java compilation có thể được tránh.

Nhưng module mới cũng thêm:

- Project/plugin configuration overhead.
- Classpath variant/dependency resolution.
- Task graph nodes.
- Metadata và API compatibility coordination.
- File snapshotting costs, nhất là build rất lớn.
- Khả năng anti-pattern `subprojects { ... }` cấu hình eager.

**Không kết luận “tách module sẽ tăng tốc gấp N lần” khi chưa đo.** So cùng Gradle Wrapper/JDK, cùng task, clean/warm cache, CPU/memory và CI runner.

### 13.1. API vs implementation tác động compile avoidance

Một thay đổi nội bộ `implementation` thường không cần làm downstream compile lại nếu public ABI không đổi và Gradle nhận biết phù hợp. Nhưng public API change có thể làm recompilation lan sang modules consumer. Bởi vậy định nghĩa API đúng vừa làm kiến trúc rõ vừa có thể cải thiện build performance.

### 13.2. Lệnh đo/quan sát

~~~bash
./gradlew :app:build --dry-run
./gradlew :app:build --parallel --console=plain
./gradlew :service:compileJava --info --console=plain
~~~

`--dry-run` cho graph, **không đo thời gian compile thật**. `--parallel` cho phép tasks độc lập chạy song song khi Gradle/resource policy hỗ trợ, không chữa race do tasks cùng ghi output directory.

### 13.3. Configuration Cache và Build Cache là hai thứ khác

- **Configuration Cache:** tái sử dụng cấu hình task graph khi đủ điều kiện.
- **Build Cache:** tái sử dụng outputs của work đã cacheable/đủ input fingerprints.
- **Dependency cache:** giữ artifacts/metadata đã resolve.

Thêm nhiều modules không tự làm cả ba cache hoạt động. Cần plugin APIs tương thích, task inputs/outputs đầy đủ và không phụ thuộc hidden state.

## 14. Convention plugins: dùng để chia sẻ build logic, không làm feature module

Trong demo, Java toolchain và encoding lặp ở ba build scripts để các files dễ hiểu độc lập. Với 30 modules, các đoạn lặp như vậy nên chuyển vào **convention plugin** có tên rõ như `company.java-library-conventions` hoặc `company.java-application-conventions`.

Một hướng là included build `build-logic`, chứa các plugins rồi được đăng ký theo cấu trúc `pluginManagement.includeBuild(...)` phù hợp. `buildSrc` cũng có thể chứa shared build logic, nhưng Gradle best practices hiện đại thường ưu tiên convention plugins có tổ chức, tránh root script quá lớn.

**Đừng áp dụng Application plugin vào mọi module:**

~~~kotlin
// ANTI-PATTERN cho build co library + executable.
subprojects {
    apply(plugin = "application")
}
~~~

Library `:domain` không có entry point và không cần `run`/distribution. Với module riêng, plugin selection là một phần của boundary.

### 14.1. Version catalog không tạo dependency boundary

`gradle/libs.versions.toml` quản lý aliases/versions cho external dependencies và plugins. Nó **không** tự biến common code thành library, không ngăn cycle, không quyết định public API. Dùng version catalog cho dependency version policy; dùng `project(":...")` và library scopes cho internal graph.

## 15. Cách xem Gradle graph và phát hiện rò rỉ dependency

Chạy từ root demo:

~~~bash
./gradlew projects
./gradlew :app:tasks
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :service:dependencies --configuration compileClasspath
./gradlew :service:outgoingVariants
~~~

Tác dụng:

- `projects` xác nhận `:domain`/`:service`/`:app` đã được `include`.
- `:app:tasks` thấy task `run` do Application plugin cung cấp.
- `:app:dependencies --configuration compileClasspath` kiểm tra compile graph app.
- `:app:dependencies --configuration runtimeClasspath` kiểm tra runtime graph app, có thể nhiều dependencies hơn.
- `:service:dependencies` cho biết service cần domain.
- `:service:outgoingVariants` hiển thị producer attributes/artifacts theo plugin/Gradle version.

Đừng viết một “expected console log” cố định: thứ tự và chi tiết chọn variant khác nhau theo Gradle, tình trạng cache và project settings.

`dependencyInsight` hỗ trợ tìm lý do chọn dependency:

~~~bash
./gradlew :app:dependencyInsight \
    --configuration compileClasspath \
    --dependency domain
~~~

Trong ví dụ, filter theo `domain` có thể hiển thị project dependency tương ứng. Nếu project khác dùng module tên khác hoặc không có match, kết quả sẽ khác. Khi cần kiểm tra một external library, dùng group/name filter phù hợp.

### 15.1. Rò rỉ API biểu hiện thế nào?

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| App không thấy type trong service public method | Service dùng `implementation` thay vì `api` | Expose đúng API dependency hoặc đổi contract |
| Domain compile thấy JDBC/web classes | Tầng domain đang depend adapter | Xem lại ownership/interfaces |
| Client compileClasspath có quá nhiều thư viện nội bộ | Lạm dụng `api` | Chuyển phần chỉ dùng trong body sang `implementation` |
| App runtime thiếu một JAR | Dùng `compileOnly` sai hoặc dependency metadata sai | Kiểm tra `runtimeClasspath` và scopes |
| Graph có `:domain` phụ thuộc `:app` | Dependency direction bị đảo | Tách port hoặc chuyển logic |
| Build fail với Project path not found | Thiếu include/sai path | Xem `settings.gradle.kts` và `projects` |
| Script cố đọc sibling build output | Hardcoded artifact path | Project dependency hoặc outgoing artifact variant |
| Đổi một module làm mọi modules compile lại | ABI thay đổi/graph quá rộng | Tối giản API, đo task inputs |

### 15.2. Vì sao thêm dependsOn không sửa classpath?

Sai hướng:

~~~kotlin
tasks.named("compileJava") {
    dependsOn(":domain:jar")
}
~~~

Câu này chỉ yêu cầu task khác chạy trước. Nó **không cấp API elements, runtime elements hoặc dependency transitivity** cho consumer. Đúng hơn là `api(project(":domain"))` hoặc `implementation(project(":domain"))` ở dependency block phù hợp.

## 16. Testing strategy khi đã tách module

Module boundary cần được kiểm tra bằng tests ở đúng mức:

| Module | Tests nên có |
| --- | --- |
| :domain | Pure unit tests cho invariants, value objects |
| :service | Use-case unit tests, fake ports, API contract tests |
| :app | CLI/main wiring, smoke tests, integration |
| :jdbc-adapter | DB integration tests với schema/transactions isolation |
| Cross-module | Consumer-driven contract và end-to-end tests khi cần |

**Bài demo ban đầu không chứa test source**. Nếu gọi `./gradlew :service:test`, Gradle có thể báo `NO-SOURCE`. Đừng xem `NO-SOURCE` là bằng chứng đã test service.

### 16.1. Bổ sung test thực sự vào :service

Thêm đoạn này vào `service/build.gradle.kts`, **giữ dependency `api(project(":domain"))` có sẵn**:

~~~kotlin
repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Đây là snippet bổ sung, cần Maven Central hoặc mirror hợp lệ và Gradle Wrapper tương thích. Version JUnit được pin cho ví dụ, không phải khẳng định latest.

Thêm file `service/src/test/java/demo/service/GreetingServiceTest.java`:

~~~java
package demo.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class GreetingServiceTest {
    @Test
    void returnsGreeting() {
        GreetingService service = new GreetingService();
        assertEquals("Hello, Ada!", service.greet("Ada").text());
    }
}
~~~

Chạy:

~~~bash
./gradlew :service:test
./gradlew :service:test --tests "demo.service.GreetingServiceTest"
~~~

Test không cần khởi động CLI application. `testImplementation` được dùng cho JUnit của module service, không phải public API dependency của service. Đừng đưa JUnit vào `api`.

### 16.2. Contract test khác implementation test

Một test xác nhận `service.greet("Ada").text()` trả đúng chuỗi là behavior contract. Dù service implementation đổi mà method signature không đổi, integration consumer vẫn có thể bị ảnh hưởng. Compile avoidance không thay thế contract/end-to-end verification.

## 17. Tách dần monolith: lộ trình ít rủi ro

Giả sử code hiện tại:

~~~text
src/main/java/com/acme/
├── Main.java
├── Greeting.java
├── GreetingService.java
├── JdbcRepository.java
├── RestController.java
└── util/...
~~~

Không nên di chuyển hàng trăm files cùng lúc với thay đổi business behavior. Hãy tách từng bước.

### Bước 1 — Ghi baseline

- Clean build/tests hiện tại có PASS không?
- Có smoke test cho entry point không?
- Dependency graph hiện tại gồm những external libraries nào?
- Gradle Wrapper/JDK/toolchain versions nào đang dùng?
- Có generated sources/resources hoặc plugins đặc biệt không?
- Build time và task cache behavior baseline thế nào?

### Bước 2 — Lập bảng responsibility và imports

| Nhóm | Responsibility | Dependencies | Module hướng đến |
| --- | --- | --- | --- |
| Greeting | Domain value | JDK | :domain |
| GreetingService | Use case | Greeting | :service |
| Main | CLI bootstrap | Service API | :app |
| JdbcRepository | Persistence | JDBC/DB | :jdbc-adapter nếu đủ lý do |
| RestController | HTTP adapter | Web framework, service | :web hoặc :app |

Hãy xác định **cạnh cần có**, không chỉ tên thư mục.

### Bước 3 — Tách leaf/stable module trước

Di chuyển domain value objects/rules ít dependency sang `:domain`. Không đổi business behavior nếu mục tiêu là modularization. Chạy domain compile/tests.

### Bước 4 — Tách service

Đưa use cases sang `:service`, xác định public contract với domain. Chọn `api`/`implementation` dựa trên method signatures thực sự, không đoán.

### Bước 5 — Đưa entry point về app

App dùng Application plugin và project dependency tới service. Không để domain import ngược Main, HTTP controller hoặc database implementation.

### Bước 6 — Verification theo module và tổng thể

~~~bash
./gradlew :domain:build
./gradlew :service:build
./gradlew :app:run --args="Ada"
./gradlew build
~~~

Ở root multi-project, `build` là task selector thường chạy các build tasks tương ứng trong hierarchy, nhưng nếu cần phạm vi cụ thể hãy gọi fully qualified task path.

### Bước 7 — Xóa hidden coupling và đo lại

- Tìm sibling `build/` paths hoặc duplicate resource names.
- Chặn import ngược adapter vào core.
- Tách shared DB ownership và API contracts.
- So compileClasspath/runtimeClasspath trước/sau.
- Giữ artifact API/versions nhất quán với consumers.
- Đo thời gian clean/warm build, test duration và CI task graph.
- Thêm architecture tests/rules nếu tổ chức có công cụ phù hợp.

## 18. Khi nào chọn composite build hoặc published artifact?

| Trường hợp | Mô hình phù hợp |
| --- | --- |
| Modules nằm trong cùng repository và release train | Multi-project với `include(":x")` |
| Shared Gradle build conventions | `build-logic` included build hoặc `buildSrc` |
| Hai builds có settings/lifecycle riêng nhưng cần cùng phát triển | Composite build `includeBuild("...")` |
| Library dùng từ nhiều repositories/teams | Publish binary với Gradle Module Metadata/POM |
| Deployable services không có Java classpath chung | Network/API contracts thay vì kéo executable project vào classpath |
| Chỉ cần thêm integration tests trong một module | Custom source set/JVM test suite thay vì project mới |

`include(":domain")` khác `includeBuild("domain")`: một cái tạo subproject của build hiện tại, một cái kết hợp một Gradle build riêng. Không dùng composite build chỉ để né refactor dependency cycle trong cùng codebase.

### 18.1. Independent release cần nhiều hơn tách project

Nếu các modules sẽ được publish độc lập, cần semantic versioning, compatibility tests, deprecation policy, dependency constraints/locking, artifact signing/verification và CI release orchestration. Một project dependency trong monorepo không tự bảo đảm binary sẽ tương thích khi published separately.

## 19. Anti-patterns khi modularize

**Anti-pattern A — Một module cho mỗi Java package.** Package count không chứng minh cohesion. Quá nhiều subprojects làm tăng coordination cost.

**Anti-pattern B — Root áp dụng mọi plugin.** `application` chỉ ở executable module, `java-library` ở libraries.

**Anti-pattern C — Dùng `api` cho tất cả dependencies.** Downstream compile classpath bị mở rộng và ràng buộc chặt với implementation details.

**Anti-pattern D — Cố dùng implementation khi public signature lộ type.** Consumer không compile được; thiết kế lại API hoặc dùng api đúng.

**Anti-pattern E — Thêm `dependsOn` thay project dependency.** Task order không mang variant/classpath metadata.

**Anti-pattern F — Dựng `:common` chứa mọi helper/DTO/repository.** Ownership và coupling không kiểm soát.

**Anti-pattern G — Domain import database adapter.** Đảo chiều dependency, khó test và reuse.

**Anti-pattern H — Dùng cùng database schema như không có boundary.** Hidden data coupling vẫn tồn tại.

**Anti-pattern I — Split modules để “tự có microservices”.** Operational boundary cần networking/version/deployment contracts riêng.

**Anti-pattern J — Tách mọi thứ trong một commit và đổi business logic cùng lúc.** Khó kiểm tra regression; tách từng boundary có tests.

**Anti-pattern K — Hardcode sibling artifact output.** Build layout thay đổi sẽ làm consumer fail; dùng project dependency/variant.

**Anti-pattern L — Đọc build success là đủ.** Chưa chắc có tests; `NO-SOURCE`/`UP-TO-DATE` phải được hiểu đúng.

## 20. Bài tập tự kiểm tra có đáp án

**Câu 1.** Dự án CLI 5 classes, không reuse, mỗi thay đổi đều sửa cả 5. Nên tạo 5 modules không?  
**Đáp án:** thường không, package/source set là đủ; thiếu boundary giá trị rõ.

**Câu 2.** Core rules không cần JDBC, nhưng app dùng JDBC. Có lý do tách?  
**Đáp án:** có, core nên giữ độc lập framework/DB adapter khi cohesion/coupling hợp lý.

**Câu 3.** `include(":domain", ":service", ":app")` nằm trong file nào?  
**Đáp án:** `settings.gradle.kts` ở root.

**Câu 4.** Có `include(":service")` thì :app tự import được service classes không?  
**Đáp án:** không, cần khai báo `implementation(project(":service"))`.

**Câu 5.** :service gọi domain model trong public return type. Scope nào?  
**Đáp án:** `api(project(":domain"))`.

**Câu 6.** Domain type chỉ dùng trong implementation body, không lộ public API. Scope nào thường phù hợp?  
**Đáp án:** `implementation`.

**Câu 7.** `implementation` có luôn loại runtime dependency không?  
**Đáp án:** không; library runtime variant có thể bao gồm nó.

**Câu 8.** Thay `api` thành `implementation` tại :service và :app không compile `Greeting`. Hướng sửa?  
**Đáp án:** khôi phục api đúng public contract hoặc đổi service API không expose Greeting.

**Câu 9.** Demo `./gradlew :app:run --args="Ada"` in gì?  
**Đáp án:** `Hello, Ada!`.

**Câu 10.** Không có argument thì in gì?  
**Đáp án:** `Hello, Gradle!`.

**Câu 11.** Module library có cần application `run` task không?  
**Đáp án:** không; `java-library` phù hợp, còn `:app` dùng `application`.

**Câu 12.** :app phụ thuộc :service và :service phụ thuộc :domain. Có cần `:app:compileJava.dependsOn(":domain:jar")` không?  
**Đáp án:** không; project dependencies/variants thiết lập tasks cần thiết.

**Câu 13.** :domain phụ thuộc :app và :app phụ thuộc :domain là lỗi gì?  
**Đáp án:** circular dependency; cần refactor ownership/abstraction.

**Câu 14.** Lệnh xem projects được include?  
**Đáp án:** `./gradlew projects`.

**Câu 15.** Lệnh xem compileClasspath của :app?  
**Đáp án:** `./gradlew :app:dependencies --configuration compileClasspath`.

**Câu 16.** Lệnh xem outgoing variants của :service?  
**Đáp án:** `./gradlew :service:outgoingVariants`.

**Câu 17.** Root có bắt buộc source Java không?  
**Đáp án:** không.

**Câu 18.** `java-library` có tự tạo `module-info.java` cho JPMS không?  
**Đáp án:** không; hai mô hình khác nhau.

**Câu 19.** Dự án có 30 modules lặp toolchain/encoding. Giải pháp tốt?  
**Đáp án:** convention plugin có phạm vi áp dụng rõ.

**Câu 20.** Module :common chứa DB, HTTP và domain rules; đây có phải cohesion tốt?  
**Đáp án:** không; nên xác định lại responsibilities/ownership.

**Câu 21.** Service implementation đổi nhưng public ABI không đổi; downstream luôn cần recompile không?  
**Đáp án:** không nhất thiết; Gradle compile avoidance có thể tránh khi input/ABI cho phép, nhưng vẫn phải kiểm tra behavior.

**Câu 22.** :service:test báo NO-SOURCE. Có nghĩa tests PASS không?  
**Đáp án:** không, chưa có test sources để chạy.

**Câu 23.** Hai modules không import nhau nhưng cùng sửa một bảng DB. Có independent không?  
**Đáp án:** chưa, shared data ownership là coupling ẩn.

**Câu 24.** Dự án muốn hai services deploy độc lập. Tách hai Gradle subprojects đã đủ không?  
**Đáp án:** không; phải có versioned APIs, data/network/CI/deployment contracts.

**Câu 25.** Task `mustRunAfter(":domain:jar")` có giúp app compile được domain type không?  
**Đáp án:** không; chỉ sắp thứ tự khi tasks đã có trong graph.

**Câu 26.** :app dùng domain API trực tiếp ngoài service contract. Có nên khai báo direct dependency?  
**Đáp án:** có thể nên thêm `implementation(project(":domain"))` để biểu diễn dependency chủ ý.

**Câu 27.** Khi refactor monolith, nên đổi mọi business logic cùng lúc tách module không?  
**Đáp án:** không; chuyển boundary nhỏ, giữ behavior, thêm tests và làm từng bước.

**Câu 28.** Vì sao không dùng một Gradle subproject riêng để chứa mỗi JUnit test class?  
**Đáp án:** overhead không có giá trị rõ; dùng source sets/test suites và test filtering.

## 21. Checklist quyết định và triển khai

- [ ] Module mới có responsibility/owner cụ thể, không chỉ vì số file lớn?
- [ ] Có lợi ích dependency isolation, reuse hoặc API stability đo được?
- [ ] Đã cân nhắc package/source set thay vì subproject mới?
- [ ] Mỗi module có public API đủ nhỏ và consumer được xác định?
- [ ] Module graph là DAG, không có chiều import ngược?
- [ ] Domain không phụ thuộc ngược entrypoint, web/DB adapter?
- [ ] Các shared DTO/data contracts có ownership rõ?
- [ ] Không có `:common` phình to không mục đích?
- [ ] `settings.include` đăng ký project paths đúng?
- [ ] `project(":...")` biểu diễn dependencies, không dùng sibling file paths?
- [ ] Dùng `java-library` cho libraries và `application` cho executable?
- [ ] Dùng `api` đúng public signatures, `implementation` cho nội bộ?
- [ ] `runtimeOnly`, `compileOnlyApi`, `testImplementation` có scope hợp lý?
- [ ] Đã kiểm tra compileClasspath và runtimeClasspath của consumers?
- [ ] Đã kiểm tra `apiElements`, `runtimeElements`/outgoingVariants?
- [ ] Tests unit/service/contract/integration nằm ở module thích hợp?
- [ ] Không tính NO-SOURCE là test coverage?
- [ ] Không ép mọi module dùng cùng plugin qua root `subprojects` rộng?
- [ ] Build logic chung được chia sẻ qua convention plugin khi cần?
- [ ] Multi-project khác JPMS/composite build/independent deploy đã được phân biệt?
- [ ] Đã lập baseline performance và so task graph trước/sau split?
- [ ] Có xử lý hidden dependencies: DB, temp files, generated outputs?
- [ ] API compatibility/release policy rõ nếu modules publish độc lập?
- [ ] Refactor có các bước nhỏ, kiểm chứng được bằng tests?
- [ ] JDK/Gradle Wrapper/dependency versions được kiểm soát?

## 22. Tài liệu chính thức

- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): `include`, project descriptors và project dependencies.
- [Gradle — Structuring Multi-Project Builds](https://docs.gradle.org/current/userguide/intro_multi_project_builds.html): root/subprojects, project paths, convention builds.
- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): modularization, root structure và build logic.
- [Gradle — Declaring Dependencies Between Subprojects](https://docs.gradle.org/current/userguide/declaring_dependencies_between_subprojects.html): `project(":...")`, task graph, output artifacts.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `api`/`implementation`, ABI, variants và compile avoidance.
- [Gradle — Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): source sets, classpaths và tests.
- [Gradle — Dependency Management](https://docs.gradle.org/current/userguide/dependency_management.html): project/external dependencies và resolution.
- [Gradle — Dependency Inspection](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`/`dependencyInsight`.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): Java compiler/launcher.
- [Gradle — Performance](https://docs.gradle.org/current/userguide/performance.html): compile avoidance/incremental/parallel.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): `includeBuild` và nhiều builds.
- [Gradle — Sharing Build Logic](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): convention plugins/`buildSrc`.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): `run` và distribution cho executable modules.

**Kết luận:** tách module khi có **ranh giới trách nhiệm và dependency thực sự**, không phải chỉ vì code nhiều. Vẽ DAG, đặt domain/contract về phía ổn định, để app và adapters phụ thuộc vào contracts thay vì ngược lại. Dùng `settings.include` để khai báo projects và `project(":...")` với `java-library`/`api`/`implementation` đúng semantics để Gradle quản lý compile/runtime variants và task graph. Tách dần, kiểm chứng từng module và đo performance; module boundary chỉ thành công khi giảm coupling, rõ ownership và giữ API đủ ổn định cho consumers.