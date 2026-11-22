# Phân biệt `apiElements`, `runtimeElements` và các variant Java trong Gradle

## 1. Mục tiêu: một thư viện Java không chỉ có “một JAR”

Khi project `:app` khai báo `implementation project(':library')`, Gradle không đơn thuần lấy một file JAR rồi kết thúc. Gradle cần trả lời: **Consumer đang biên dịch, chạy chương trình, lấy source, lấy Javadoc hay cần một tính năng đặc biệt của thư viện?** Từ đó Gradle chọn **variant** do producer công bố và nhận đúng dependencies/artifacts tương ứng.

Hai variant chủ chốt của **Java Library plugin** là:

- **`apiElements`**: phần thư viện được công bố cho **consumer compile**; thuộc tính `org.gradle.usage=java-api`. Nó mô tả **API dependencies**, không tự làm lộ tất cả implementation dependencies của producer.
- **`runtimeElements`**: phần thư viện được công bố cho **consumer runtime**; thuộc tính `org.gradle.usage=java-runtime`. Nó mang những dependencies cần thiết để code chạy, bao gồm implementation/runtime-only dependencies.

Ngoài hai variant chính còn có **`sourcesElements`**, **`javadocElements`**, **`testFixturesApiElements`**, **`testFixturesRuntimeElements`**, custom **feature variants**, cùng **secondary artifact sets** như `classes` và `resources`. Không phải loại nào cũng cung cấp binary JAR hoặc mang cùng capability.

**Mục tiêu hoàn thành bài:** bạn nhận diện được configuration nào **khai báo** dependency, configuration nào **yêu cầu** dependency, configuration nào **công bố** variant; dùng `outgoingVariants` và `resolvableConfigurations` để đọc attributes; phân biệt API/runtime/test fixtures/documentation/secondary artifacts; chạy được bài thực hành Java 17 để tự kiểm chứng.

Ví dụ dùng **Gradle Groovy DSL** (`build.gradle`, `settings.gradle`), Gradle Wrapper, JDK 17+ với Gradle tương thích. Linux/macOS dùng `./gradlew`; Windows PowerShell dùng `.\gradlew.bat`.

## 2. Bốn khái niệm cần tách riêng

| Khái niệm | Bản chất | Ví dụ |
| --- | --- | --- |
| **Component** | Một phiên bản module/project được chọn trong dependency graph | `org.example:engine:1.0` hoặc component `project(':engine')` |
| **Variant** | Một mặt có thể tiêu thụ của component, có attributes, capabilities, dependencies/artifacts riêng | `apiElements`, `runtimeElements`, `testFixturesRuntimeElements` |
| **Configuration** | Model Gradle để khai báo, resolve hoặc công bố dependencies/variants; vai trò tùy cách dùng | `implementation`, `compileClasspath`, `apiElements` |
| **Artifact (hoặc artifact set)** | File/thư mục thực tế mà consumer sử dụng sau artifact selection | JAR, classes directory, resources directory, sources JAR |

Một **component** có thể có nhiều variants. Một **variant** có thể mang tập dependencies khác và công bố một hay nhiều artifacts. **Variant selection** có thể diễn ra trước khi Gradle tải artifact. Vì thế không nên dùng lẫn “chọn component”, “chọn variant” và “chọn JAR”.

Ví dụ logic:

~~~text
Consumer :app
   |
   | cần compileClasspath:
   |   usage=java-api
   v
Component :engine
   +-- apiElements         <-- selected cho API usage
   |     dependencies: api + compileOnlyApi (tùy khai báo)
   |     artifact set: jar / classes directory tùy nhu cầu
   |
   | cần runtimeClasspath:
   |   usage=java-runtime
   v
   +-- runtimeElements     <-- selected cho runtime usage
         dependencies: api + implementation + runtimeOnly cần khi chạy
         artifact set: jar hoặc artifacts phù hợp
~~~

Hai mũi tên tương ứng **hai lần resolution theo consumer configuration khác nhau**. Đừng hình dung một single compile/run graph dùng chung cho toàn build.

## 3. Declarable, resolvable và consumable configurations

Một nguồn nhầm lẫn rất phổ biến: `api`, `implementation`, `compileClasspath` và `apiElements` không cùng vai trò.

| Configuration / nhóm | Vai trò | Bạn làm gì với nó? |
| --- | --- | --- |
| `api` | **Declarable** (Java Library) | Khai dependency là một phần API mà consumer cần khi compile |
| `implementation` | **Declarable** | Khai dependency cần để build/triển khai thư viện, không phải API được công khai |
| `compileOnly` | **Declarable** | Cần khi compile project nhưng không đưa vào runtime theo quan hệ mặc định |
| `compileOnlyApi` | **Declarable** (Java Library) | Dependency xuất hiện trong API compile của consumers nhưng không mang vào runtime như dependency bình thường |
| `runtimeOnly` | **Declarable** | Chỉ cần khi chạy |
| `testImplementation`, `testRuntimeOnly` | **Declarable** | Phụ thuộc cho test, không tự công bố làm API chính |
| `compileClasspath` | **Resolvable** | Consumer yêu cầu các thành phần/files để compile |
| `runtimeClasspath` | **Resolvable** | Consumer yêu cầu các thành phần/files để chạy |
| `testCompileClasspath`, `testRuntimeClasspath` | **Resolvable** | Consumer test compile/test runtime |
| `apiElements` | **Consumable** | Producer cung cấp Java API-facing variant |
| `runtimeElements` | **Consumable** | Producer cung cấp Java runtime-facing variant |

**Mấu chốt:** `implementation` là nơi **khai báo**, không phải một classpath cho phép gọi `resolve()` tùy ý. `apiElements` là **đầu ra hợp đồng** của producer, không phải nơi consumer cần khai `implementation 'g:n:v'`. Lệnh báo cáo phải dùng `compileClasspath`/`runtimeClasspath` ở consumer và `outgoingVariants` ở producer.

### 3.1. Vai trò và các flags kỹ thuật

Configurations có các thuộc tính như `canBeResolved`, `canBeConsumed` và `canBeDeclared` trong Gradle hiện đại. Với model mới, nên thiết kế một configuration theo **một trách nhiệm rõ ràng** thay vì vừa nhận dependency, vừa resolve, vừa công bố một cách tùy tiện. Các plugins Java đã thiết lập đúng vai trò; đừng sửa flags của `apiElements`/`runtimeElements` chỉ vì một báo cáo không như mong đợi.

### 3.2. `extendsFrom` không tự tạo “loại classpath” mới

Gradle nối các dependency scopes vào resolvable/consumable configurations theo model plugin. Ví dụ Java Library:

- `compileClasspath` dùng các dependencies cần để biên dịch project hiện tại.
- `apiElements` công bố những gì **consumer cần để compile API** của producer (bao gồm `api` và các dependency API-only đặc thù).
- `runtimeElements` công bố những gì **consumer cần khi chạy producer**, nên gồm dependencies từ `api`, `implementation` và `runtimeOnly` theo quan hệ plugin.

Mối quan hệ không nên suy luận đơn giản bằng cách thấy tên “runtimeElements extends runtimeOnly, implementation” rồi kết luận `api` bị mất: trong Java Library, các dependency scopes có quan hệ kế thừa phù hợp để API dependencies cũng cần ở runtime.

## 4. Chính xác `apiElements` cho consumer cái gì?

Với **`java-library` plugin**, `apiElements` là variant phục vụ tiêu thụ API.

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api project(':contract')
    implementation project(':helper')
}
~~~

Đây là **snippet** thuộc project producer đã có hai subprojects `:contract`/`:helper`. Khi consumer dựa vào `project(':engine')`:

- Gradle thường chọn `:engine` **`apiElements`** cho `compileClasspath` của consumer.
- Component `:contract` thuộc API dependency nên **consumer compile** cũng cần nhìn thấy nó.
- Component `:helper` là implementation dependency nội bộ của engine, nên **không được tự công bố** sang compile classpath của consumer thông qua `:engine`.
- Engine vẫn compile được vì **compile classpath của chính engine** có cả API và implementation dependencies cần thiết.

### 4.1. Tại sao API boundary quan trọng?

Giả sử public type `Greeter` implements interface `Greeting` từ `:contract`. Khi app khai kiểu `Greeting`, compiler của app cần biết `Greeting` là gì; nếu contract bị giấu sau implementation, compile có thể thất bại. Ngược lại, `Formatter` chỉ được dùng trong method body của Greeter thì app không cần nó lúc compile — implementation hợp lý hơn.

Phân tách này:
- Giảm dependency leakage vào consumer compile classpath.
- Giúp compile avoidance: đổi implementation của thư viện có thể không buộc consumer phải compile lại nếu API không đổi (còn tùy nội dung ABI và task inputs).
- Làm rõ public API và implementation details.
- Tăng chất lượng metadata khi publish thư viện.

**Không phải cứ class nằm trong JAR của thư viện là dependency vào mọi thư viện mà class đó sử dụng phải là `api`.** Xét chữ ký public API và điều gì consumer phải thấy khi compile.

### 4.2. `compileOnlyApi` khác `api`

Một số API đề cập đến annotation/type mà consumer cần lúc compile, nhưng thư viện không muốn mang dependency đó vào runtime. Với Gradle Java Library phù hợp, có `compileOnlyApi`:

~~~groovy
dependencies {
    compileOnlyApi 'org.example:annotations:1.0'
}
~~~

Đây là **snippet có tọa độ giả định**, cần repository chứa module thật mới resolve được. Ý nghĩa: annotation/types cần cho consumer compile có thể được công bố qua API elements, nhưng không tự kéo dependency ấy vào runtime graph như `api` thông thường. Không dùng `compileOnlyApi` để giấu runtime dependency thực sự: nếu code cần class khi chạy, phải khai runtime dependency phù hợp.

### 4.3. `apiElements` không nhất thiết chuyển “api.jar”

Trong nhiều project Java:
- `apiElements` chính có thể công bố **JAR của main component**.
- Nó cũng có thể có **secondary variant/artifact set `classes`**, để consumer compile dùng classes directory.
- Secondary artifact set thường **giữ dependencies của variant chính**, nhưng thay dạng artifact file/thư mục; nó **không tự là một dependency scope khác**.

Vì vậy đừng khẳng định “chọn apiElements = chắc chắn build JAR trước mọi consumer compile”. Với project dependencies, Gradle có thể dùng compiled classes directory để tiết kiệm tạo JAR trong quá trình biên dịch.

## 5. Chính xác `runtimeElements` cho consumer cái gì?

`runtimeElements` có `org.gradle.usage=java-runtime` và công bố những gì cần thiết để tiêu thụ thư viện khi **chạy**.

~~~groovy
dependencies {
    api project(':contract')
    implementation project(':helper')
    runtimeOnly 'org.example:runtime-adapter:1.0'
}
~~~

Đây là **snippet minh họa**, không chạy độc lập vì tọa độ `runtime-adapter` giả định. Thông thường, consumer runtime graph của engine sẽ nhận:
- `:contract` (API dependency vẫn cần lúc runtime nếu bytecode tham chiếu nó).
- `:helper` (implementation dependency cần lúc runtime).
- `runtime-adapter` nếu có thực và được khai `runtimeOnly`.

Consumer **compile** không được tự thêm `:helper` và `runtime-adapter` từ runtimeElements. Nếu app code cố import `helper.Formatter` vì “chương trình có thể chạy”, compile vẫn phải có dependency compile phù hợp; đó không phải phép sử dụng API sạch nếu helper là nội bộ.

### 5.1. JAR vật lý có thể giống nhau, metadata khác nhau

Hai variants của cùng main component có thể đưa **cùng một JAR binary** ra bên ngoài; khác nhau chủ yếu ở:
- **Usage attribute**.
- **Dependencies/constraints** được công bố.
- Có thể có artifacts/secondary variants được lựa chọn khác tùy plugin/consumer.

Không nên nghĩ luôn tồn tại file `engine-api.jar` và `engine-runtime.jar`. Java Library plugin thông thường không tạo hai JAR riêng chỉ vì có hai variants. Biến thể ở đây mô tả **hợp đồng tiêu thụ**, không mặc định có hai gói nhị phân độc lập.

## 6. Consumer chọn variant bằng attributes, không chọn tùy hứng theo tên

Gradle là công cụ **variant-aware dependency resolution**. Consumer mang **requested attributes**, producer công bố **offered attributes**, và Gradle dùng **compatibility/disambiguation rules** để chọn ứng viên phù hợp.

### 6.1. Attributes tiêu biểu của JVM ecosystem

| Attribute | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `org.gradle.usage` | `java-api`, `java-runtime` | Consumer cần compile API hay chạy |
| `org.gradle.category` | `library`, `platform`, `documentation`, `verification` | Loại tài nguyên được cung cấp |
| `org.gradle.libraryelements` | `jar`, `classes`, `resources` | Dạng artifact binary/classes/resources |
| `org.gradle.dependency.bundling` | `external`, `embedded`, `shadowed` | Phụ thuộc được giữ ngoài hay gộp vào artifact |
| `org.gradle.jvm.version` | `8`, `11`, `17` | Mức JVM compatibility của producer/consumer |
| `org.gradle.jvm.environment` | `standard-jvm`, môi trường JVM khác | Môi trường tương thích |
| `org.gradle.docstype` | `sources`, `javadoc` | Kiểu tài liệu khi category là documentation |
| Plugin-defined attributes | Build type, target OS/architecture, test fixture kinds | Hợp đồng khác do plugin quy định |

Tên attribute thường là **chìa khóa model**, không đồng nghĩa với tên configuration. Ví dụ `apiElements` thường mang Usage `java-api`, nhưng variant do plugin khác cung cấp cũng có thể dùng `java-api` với các attributes/capabilities khác.

### 6.2. Compatibility khác equality

Giả sử consumer yêu cầu Java 17, producer có library target Java 11. Với các rules tương thích JVM thông thường, consumer Java 17 có thể dùng library target Java 11. Ngược lại, consumer chỉ chấp nhận Java 11 không thể mặc nhiên tiêu thụ binary chỉ chạy được trên Java 17.

~~~text
Consumer Java 17 + producer JVM 11 -> có thể compatible
Consumer Java 11 + producer JVM 17 -> thường incompatible
~~~

Gradle còn xét usage, category, bundling, library elements và các attributes khác. Nếu không có variant phù hợp, báo `No matching variant`; nếu còn nhiều variant tương thích mà Gradle không chọn được một, có thể báo ambiguity. **Không sửa lỗi bằng cách đổi tên dependency configuration**; cần đối chiếu attributes hai phía.

### 6.3. Một điều cần phân biệt: Java API và compile classpath của producer

`apiElements` được chọn **khi một consumer biên dịch chống lại API** của producer. Nhưng **`:engine:compileClasspath`** của engine là resolvable configuration để engine tự compile, chứa những dependencies engine cần, kể cả implementation. Không suy ra rằng vì engine compile thành công thì mọi consumer compile cũng thấy cùng classpath.

## 7. Phòng thực hành hoàn chỉnh Java 17: API, implementation, runtime, docs và test fixtures

Để không phụ thuộc Maven Central, bài thực hành dùng **bốn project Gradle nội bộ**. Nó đồng thời cho thấy `apiElements`, `runtimeElements`, documentation variants và test-fixtures variants.

### 7.1. Sơ đồ project

~~~text
java-variants-lab/
├── settings.gradle
├── build.gradle
├── contract/
│   ├── build.gradle
│   └── src/main/java/demo/contract/Greeting.java
├── helper/
│   ├── build.gradle
│   └── src/main/java/demo/helper/Formatter.java
├── engine/
│   ├── build.gradle
│   ├── src/main/java/demo/engine/DefaultGreeting.java
│   └── src/testFixtures/java/demo/engine/fixtures/GreetingFixture.java
├── app/
│   ├── build.gradle
│   ├── src/main/java/demo/app/App.java
│   └── src/test/java/demo/app/FixtureProbe.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Nếu chưa có Gradle Wrapper, dùng Gradle đã cài tạm để chạy `gradle wrapper`, rồi lưu bộ Wrapper trong repository. Build yêu cầu JDK 17 (hoặc cấu hình Java toolchains provisioning để cung cấp JDK tương ứng). Ví dụ không tải **dependency thư viện ngoài**, nhưng Gradle vẫn cần JDK/toolchain phù hợp.

### 7.2. Root settings và root build script

**`settings.gradle`:**

~~~groovy
rootProject.name = 'java-variants-lab'
include 'contract', 'helper', 'engine', 'app'
~~~

**`build.gradle` tại root:**

~~~groovy
subprojects {
    group = 'org.example'
    version = '1.0'
}
~~~

Dòng ở root dùng để đặt group/version nhất quán cho các components để khi xem `outgoingVariants`, default capability có coordinates dễ hiểu như `org.example:engine:1.0`. **Không có `allprojects.repositories`** vì bài thực hành chỉ dùng local project dependencies.

### 7.3. Module `:contract` — public interface

**`contract/build.gradle`:**

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**`contract/src/main/java/demo/contract/Greeting.java`:**

~~~java
package demo.contract;

public interface Greeting {
    String say();
}
~~~

Module này cung cấp API type `Greeting`. Public API của `DefaultGreeting` ở engine sẽ tham chiếu interface này, nên engine cần export `:contract` cho consumer compile.

### 7.4. Module `:helper` — implementation detail

**`helper/build.gradle`:**

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**`helper/src/main/java/demo/helper/Formatter.java`:**

~~~java
package demo.helper;

public final class Formatter {
    private Formatter() {
    }

    public static String decorate(String value) {
        return "Java variant OK: " + value;
    }
}
~~~

`Formatter` là implementation helper. Đối với consumer trực tiếp sử dụng `DefaultGreeting.say()`, việc có `Formatter` trên **runtime classpath** quan trọng, nhưng không cần trên consumer **compile classpath**.

### 7.5. Module `:engine` — công bố cả main API/runtime và test fixtures

**`engine/build.gradle` (toàn bộ):**

~~~groovy
plugins {
    id 'java-library'
    id 'java-test-fixtures'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withSourcesJar()
    withJavadocJar()
}

dependencies {
    api project(':contract')
    implementation project(':helper')
}
~~~

Các ý nghĩa:
- `java-library` cung cấp `api`/`implementation` và hai outgoing main variants `apiElements`/`runtimeElements`.
- `api project(':contract')` công bố interface của contract tới consumer compile.
- `implementation project(':helper')` cho phép engine compile/chạy với helper nhưng giấu dependency này khỏi **consumer compile** thông qua engine.
- `java-test-fixtures` tạo source set `testFixtures` và các outgoing variants của fixtures.
- `withSourcesJar()` tạo sources JAR và documentation variant liên quan.
- `withJavadocJar()` tạo Javadoc JAR và documentation variant liên quan. Task Javadoc cần JDK phù hợp và có thể sinh warnings riêng tùy JDK/doclint.

**`engine/src/main/java/demo/engine/DefaultGreeting.java`:**

~~~java
package demo.engine;

import demo.contract.Greeting;
import demo.helper.Formatter;

public final class DefaultGreeting implements Greeting {
    @Override
    public String say() {
        return Formatter.decorate("Gradle");
    }
}
~~~

**`engine/src/testFixtures/java/demo/engine/fixtures/GreetingFixture.java`:**

~~~java
package demo.engine.fixtures;

public final class GreetingFixture {
    private GreetingFixture() {
    }

    public static String expectedMessage() {
        return "Java variant OK: Gradle";
    }
}
~~~

Fixture class là tiện ích để **consumer tests** dùng chung. Nó **không** phải một phần main API variant. Source set và capability của fixtures được cung cấp qua plugin riêng; chỉ khi consumer yêu cầu test fixtures thì Gradle mới chọn variant tương ứng.

### 7.6. Module `:app` — consumer

**`app/build.gradle` (toàn bộ):**

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':engine')
    testImplementation testFixtures(project(':engine'))
}

application {
    mainClass = 'demo.app.App'
}
~~~

**`app/src/main/java/demo/app/App.java`:**

~~~java
package demo.app;

import demo.contract.Greeting;
import demo.engine.DefaultGreeting;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        Greeting greeting = new DefaultGreeting();
        System.out.println(greeting.say());
    }
}
~~~

**`app/src/test/java/demo/app/FixtureProbe.java`:**

~~~java
package demo.app;

import demo.engine.DefaultGreeting;
import demo.engine.fixtures.GreetingFixture;

public final class FixtureProbe {
    private FixtureProbe() {
    }

    public static boolean matches() {
        String actual = new DefaultGreeting().say();
        return GreetingFixture.expectedMessage().equals(actual);
    }
}
~~~

`FixtureProbe` chỉ là class trong test source set; nó **không có `@Test`** và không được Gradle tự chạy như một JUnit test. Ta dùng nó để chứng minh **test compiler thấy fixture variant** qua `testImplementation testFixtures(project(':engine'))`. Muốn kiểm thử thực sự có assertion/running, phải bổ sung JUnit/TestNG framework và test runner configuration tương ứng.

### 7.7. Lệnh chạy và stdout chính xác

Từ root của `java-variants-lab`:

~~~bash
./gradlew :app:run --quiet
./gradlew :app:compileTestJava
~~~

**Stdout của chương trình `App.main` (không tính log Gradle):**

~~~text
Java variant OK: Gradle
~~~

- `:app:run` dùng runtime classpath, nên có engine, contract và helper cần thiết.
- `:app:compileTestJava` biên dịch `FixtureProbe` nhờ test fixture variant được yêu cầu; **không in output của `FixtureProbe.matches()`**, vì chưa gọi method.
- Không cần công bố/sử dụng `:engine:runtimeElements` bằng tên thủ công; consumer attributes và capability selection tự xử lý.

### 7.8. Dự đoán hai dependency graph

Chạy:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testCompileClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
~~~

**Kết quả logic kỳ vọng** (sơ đồ giản lược, không phải stdout nguyên văn của task `dependencies`):

~~~text
:app:compileClasspath [usage=java-api]
  \-- project :engine [main apiElements]
       \-- project :contract [API dependency]

:app:runtimeClasspath [usage=java-runtime]
  \-- project :engine [main runtimeElements]
       +-- project :contract [API dependency vẫn cần runtime]
       \-- project :helper   [implementation dependency cần runtime]

:app:testCompileClasspath
  +-- dependencies từ main compile context
  \-- testFixtures(project(':engine'))
       \-- selected testFixturesApiElements (fixture API)

:app:testRuntimeClasspath
  +-- main runtime dependencies
  \-- testFixtures(project(':engine'))
       \-- selected testFixturesRuntimeElements (fixture runtime)
~~~

Điểm quan trọng:
1. `:app:compileClasspath` **có `:contract`**, **không phải tự có `:helper`** từ engine's implementation.
2. `:app:runtimeClasspath` cần `:helper` để `DefaultGreeting.say()` có thể gọi `Formatter.decorate(...)`.
3. `testFixtures` là một **capability khác** của cùng component `:engine`, không phải artifact thay thế hoàn toàn main feature.
4. Test classpath còn kế thừa những cấu hình dành riêng cho test; sơ đồ là mô hình để hiểu khác biệt, không ghi mọi task/plugin-specific edge.

### 7.9. Quan sát producer và consumer attributes

Chạy:

~~~bash
./gradlew :engine:outgoingVariants
./gradlew :engine:outgoingVariants --variant apiElements
./gradlew :engine:outgoingVariants --variant runtimeElements
./gradlew :engine:outgoingVariants --variant sourcesElements
./gradlew :engine:outgoingVariants --variant javadocElements

./gradlew :app:resolvableConfigurations
./gradlew :app:dependencyInsight --configuration compileClasspath --dependency engine --all-variants
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency engine --all-variants
~~~

`outgoingVariants` ở **producer** cho biết những variants engine công bố, cùng attributes, capabilities, artifact sets. `resolvableConfigurations` ở **consumer** cho biết attributes mà app yêu cầu. `dependencyInsight --all-variants` giúp điều tra variant selection và version reasons theo Gradle version/report support.

Với test fixtures, có thể xem:

~~~bash
./gradlew :engine:outgoingVariants --variant testFixturesApiElements
./gradlew :engine:outgoingVariants --variant testFixturesRuntimeElements
~~~

Kết quả **không cần khớp từng dòng trên mọi Gradle version**. Hãy tìm các tín hiệu:
- `apiElements` có `org.gradle.usage=java-api`.
- `runtimeElements` có `org.gradle.usage=java-runtime`.
- Cả hai main variants thường mang default capability `org.example:engine:1.0`.
- Fixture variants có capability phân biệt, theo convention như `org.example:engine-test-fixtures:1.0`.
- `sourcesElements`/`javadocElements` có `org.gradle.category=documentation` và `org.gradle.docstype` phù hợp.

### 7.10. Thực nghiệm sai một dòng `api`

Thử thay tạm trong `engine/build.gradle`:

~~~groovy
dependencies {
    implementation project(':contract')
    implementation project(':helper')
}
~~~

Sau đó chạy:

~~~bash
./gradlew :app:compileJava
~~~

**Dự kiến compile lỗi:** code trong app cần biết interface `demo.contract.Greeting`, nhưng engine không còn công bố `:contract` qua API. Vì vậy `:app:compileClasspath` thiếu type mà App sử dụng. Lỗi chi tiết của javac có thể thay đổi, không có một stdout lỗi duy nhất trên mọi JDK. Khôi phục `api project(':contract')` sau thí nghiệm, rồi chạy lại `:app:run`.

**Lưu ý:** thay đổi này chỉ minh họa tại sao public API dependencies cần được export. Trong code thực tế, quyết định `api`/`implementation` dựa trên **public signature** và nhu cầu compile của consumer, không dựa trên mong muốn làm output build xanh.

## 8. `classes`, `resources`: secondary variants khác với main variants

Một báo cáo `outgoingVariants` của Java library thường cho thấy:

~~~text
Variant apiElements:
  org.gradle.usage=java-api
  main artifact: library.jar
  secondary artifact set: classes

Variant runtimeElements:
  org.gradle.usage=java-runtime
  main artifact: library.jar
  secondary artifact sets: classes, resources
~~~

Tên chi tiết và artifact sets có thể khác theo Gradle version/plugin, nhưng mô hình rất quan trọng:

- **Primary variant** được chọn trong **graph resolution** để quyết định dependencies/capabilities.
- **Secondary variants / artifact sets** là những lựa chọn **dạng artifact**, thường xét trong artifact selection sau graph resolution.
- Một classes directory được cung cấp qua secondary set **không tương đương** một component mới hay một “api-elements module” khác.
- Consumer compile có thể lấy **classes directory** thay vì phải ép tạo JAR; consumer runtime có thể ưu tiên JAR hoặc một artifact set phù hợp.
- Attribute `org.gradle.libraryelements` mô tả dạng cần thiết (`classes`, `jar`, `resources`...), nhưng vẫn phải tương thích với usage/category và các attributes khác.

### 8.1. Tại sao Gradle dùng classes directory?

Trong multi-project build, Gradle biết project producer đang compile classes. Nó có thể nối output của `compileJava` trực tiếp vào classpath của consumer để tránh tạo và giải nén JAR không cần thiết khi compile. Kết quả **vẫn phải tuân theo task dependencies/producer outputs**; không có chuyện consumer tự đoán ngẫu nhiên đường dẫn `build/classes` rồi đọc trước khi producer compile xong.

### 8.2. Primary variant nào có artifacts giống nhau?

`apiElements` và `runtimeElements` trong Java Library plugin thường công bố **cùng một main JAR**. Sự khác nhau đáng kể nằm ở Usage và transitive dependencies. Khi xem `:engine:outgoingVariants`, có thể cả hai phần đều liệt kê `engine-1.0.jar`; đây là hành vi đúng. Muốn phân biệt hãy nhìn **attributes và dependencies**, không chỉ tên artifact.

### 8.3. Primary/secondary không phải tên bắt buộc của mọi plugin

Plugin Android/Kotlin Multiplatform/Native có nhiều variants và attributes khác nhau. Một Gradle module từ Maven POM không nhất thiết có cấu trúc outgoing variants giống một **local Java project component**. Đừng ép mọi ecosystem phải có `apiElements`/`runtimeElements` đúng tên đó.

## 9. `sourcesElements` và `javadocElements` là documentation variants

Với Java plugin hỗ trợ:

~~~groovy
plugins {
    id 'java-library'
}

java {
    withSourcesJar()
    withJavadocJar()
}
~~~

Đây là **snippet chạy trong một Java Library project** có source code hợp lệ. Nó đăng ký việc tạo:
- **Sources JAR**: chứa source code để IDE/documentation tooling khai thác.
- **Javadoc JAR**: chứa tài liệu Javadoc được sinh.

Gradle công bố documentation variants tương ứng, thường có:

| Variant | Category | Docs type | Artifact |
| --- | --- | --- | --- |
| `sourcesElements` | `documentation` | `sources` | `*-sources.jar` |
| `javadocElements` | `documentation` | `javadoc` | `*-javadoc.jar` |

**Không nhầm**:
- `sourcesElements` không phải dependency scope để app compile Java source thay cho compiled classes.
- `javadocElements` không phải runtime variant, không chứa runtime dependencies của app.
- Không nên thêm `implementation files('engine-sources.jar')` để có docs variant. Tooling/IDE hoặc artifact view có thể yêu cầu documentation attributes phù hợp.
- Chúng khác với **`mainSourceElements`** nếu Gradle report hiển thị variant/category `verification` cho source dirs; nguồn verification phục vụ mục đích khác và không đồng nghĩa sources JAR publication.

### 9.1. Khi nào tạo docs variants?

Nếu bạn publish library hoặc cần IDE/consumer tải source/Javadoc, bật `withSourcesJar()` và `withJavadocJar()` có ích. Với một app nội bộ không publish, không phải lúc nào cũng cần tạo các JAR bổ sung. **Sources/Javadoc metadata** được Gradle Module Metadata hỗ trợ chi tiết; Maven POM/classifiers có thể biểu đạt artifact tài liệu theo cơ chế khác.

### 9.2. Kiểm chứng artifacts

Trong project thực hành, chạy:

~~~bash
./gradlew :engine:sourcesJar :engine:javadocJar
~~~

Bạn sẽ có artifacts có tên theo Gradle archive naming như `engine-1.0-sources.jar` và `engine-1.0-javadoc.jar` dưới `engine/build/libs/` (nếu group/version và archive settings giữ nguyên như bài lab). Javadoc generation cần compiler/doc toolchain thích hợp; warnings không đồng nghĩa artifact có API/runtime dependency khác.

## 10. `testFixturesApiElements` và `testFixturesRuntimeElements`: tính năng cho tests

### 10.1. Plugin và source set

Plugin `java-test-fixtures` bổ sung source set:

~~~text
src/testFixtures/java/
src/testFixtures/resources/
~~~

Nó cùng các dependency scopes như:
- `testFixturesApi`: dependency public API của fixtures.
- `testFixturesImplementation`: dependency implementation của fixtures.
- `testFixturesRuntimeOnly`: dependency chỉ dùng khi chạy fixtures.

Và outgoing variants:
- `testFixturesApiElements` — phục vụ consumer compile fixture API.
- `testFixturesRuntimeElements` — phục vụ consumer chạy code fixtures.

**Hai fixtures variants không “thay thế” main api/runtime variants**. Đây là một *feature* khác được phân biệt bằng capability, ví dụ `org.example:engine-test-fixtures:1.0`. Default capability main là `org.example:engine:1.0`.

### 10.2. Consumer phải yêu cầu feature fixture

~~~groovy
dependencies {
    implementation project(':engine')
    testImplementation testFixtures(project(':engine'))
}
~~~

Đây là snippet thuộc app có Java plugin và engine có `java-test-fixtures`. Dòng một yêu cầu **main feature**. Dòng hai yêu cầu **test fixtures feature** cho test classpath. Không dùng `implementation testFixtures(project(':engine'))` nếu fixtures chỉ dành cho tests, vì như thế sẽ đưa test-only utilities vào main code.

### 10.3. Compile-vs-runtime của fixtures

Giống main Java library:
- Fixture **API** cần được công bố cho consumer compile tests.
- Fixture implementation dependencies không nên làm rò rỉ vào consumer test compile classpath nếu chúng chỉ cần lúc thực thi.
- Khi test chạy, fixture runtime variant sẽ cung cấp những dependencies cần thiết.

Với external published library, consumer cần metadata mô tả fixture capability. Việc một Maven artifact tình cờ có classifier `test-fixtures` **không** bảo đảm Gradle tự tìm được fixture variant nếu publisher không cung cấp metadata/capability phù hợp.

### 10.4. Khi publish fixtures

`java-test-fixtures` có thể công bố fixture variants vào Java component publication. Nếu tổ chức không muốn public fixtures, cần cấu hình bỏ qua variants khỏi publication. Ví dụ **chỉ thêm vào build script có java-test-fixtures, java-library và maven-publish**:

~~~groovy
components.java.withVariantsFromConfiguration(
    configurations.testFixturesApiElements
) { skip() }

components.java.withVariantsFromConfiguration(
    configurations.testFixturesRuntimeElements
) { skip() }
~~~

Không cần đoạn này trong bài lab vì bài lab không publish. Việc bỏ publish fixtures **không nhất thiết loại bỏ khả năng tiêu thụ fixtures qua project dependency trong cùng build**; scope của cấu hình publish và project consumption cần phân biệt.

## 11. Feature variants khác: capability định danh một tính năng tùy chọn

Java Library plugin hỗ trợ đăng ký **feature variant** cho tính năng bổ sung. Ví dụ thư viện có module lõi và optional JSON support.

**Snippet minh họa** trong `build.gradle` của một Java Library project có plugin tương ứng (không phải project lab đầy đủ):

~~~groovy
plugins {
    id 'java-library'
}

java {
    registerFeature('jsonSupport') {
        usingSourceSet(sourceSets.create('jsonSupport'))
    }
}
~~~

Khi đăng ký feature tên `jsonSupport`, Gradle có thể tạo các scopes `jsonSupportApi`, `jsonSupportImplementation`, `jsonSupportRuntimeOnly` và outgoing `jsonSupportApiElements`, `jsonSupportRuntimeElements`.

Producer có thể công bố capability riêng theo naming convention, ví dụ `org.example:engine-json-support:1.0` cho component `org.example:engine:1.0`. Consumer phải yêu cầu tính năng ấy qua **capability** (hoặc cơ chế cấp dependency tương ứng), không nên nghĩ rằng tên `jsonSupportRuntimeElements` tự hiện trong mọi app runtime graph.

**Snippet consumer**, với giả định producer đã đăng ký feature và group/version như trên:

~~~groovy
dependencies {
    implementation project(':engine')

    runtimeOnly(project(':engine')) {
        capabilities {
            requireCapability('org.example:engine-json-support')
        }
    }
}
~~~

Đây là **ví dụ tham khảo**; muốn chạy được cần source set `jsonSupport` chứa code/artifact thích hợp và dependencies thực của feature. Không đặt giả định là một dependency chỉ cần `project(':engine')` sẽ tự được thêm mọi optional features.

### 11.1. Default capability và custom capability

Thông thường main variants của `org.example:engine:1.0` công bố default capability có identity `org.example:engine:1.0`. Một feature khác có capability `org.example:engine-json-support:1.0`. Nhờ đó consumer có thể chọn main feature và optional feature theo chính sách.

**Một số pitfalls:**
- Hai implementations khác nhau công bố cùng capability có thể gây **capability conflict**; Gradle cần quy tắc lựa chọn phù hợp.
- Hai variants có cùng attributes và capabilities mà cùng hợp lệ có thể gây ambiguity.
- Không được coi capability là package Java hay module name viết bằng dấu chấm; nó là **một khả năng được producer công bố**.
- Khi publish, Gradle Module Metadata giữ thông tin feature/variant phong phú hơn Maven POM truyền thống. Tùy định dạng publication, consumer có thể không giữ được đầy đủ variant selection semantics.

## 12. Maven POM, Gradle Module Metadata và publication

### 12.1. Project dependency khác published Maven dependency

Với `project(':engine')`, Gradle đã biết trực tiếp model producer và variants được plugin tạo.

Với external coordinate `org.example:engine:1.0`, Gradle phải đọc metadata repository. Nếu publisher có **Gradle Module Metadata** (`.module`), consumer có thể biết các variants, attributes, capabilities, dependency constraints và artifacts như producer công bố.

Nếu publisher chỉ có **Maven POM**, Gradle có thể **suy ra compile/runtime variants** từ Maven scopes; tên/semantics không nhất thiết trùng chính xác những gì `outgoingVariants` của local producer hiển thị. POM không biểu đạt đầy đủ custom capabilities/feature variants như GMM.

### 12.2. Maven publishing snippet

Trong `engine/build.gradle`, nếu muốn xuất bản library (không yêu cầu thực hiện trong bài lab), có thể thêm `maven-publish`:

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

publishing {
    publications {
        library(MavenPublication) {
            from components.java
        }
    }
}
~~~

Đây là **snippet minh họa**; khi dùng thực tế còn cần group/version, target repository, credentials, chính sách release và cách publish variants phù hợp. Không chạy upload tới kho production chỉ để thử variant report. Plugin Maven Publish xuất bản metadata/artifacts theo cấu hình; không phải mọi dạng phụ của Java library đều thành một Maven artifact chính khác nhau.

### 12.3. Classifier không đồng nghĩa capability

Một JAR có classifier `sources`, `javadoc` hoặc `test-fixtures` chỉ là cách đặt tên artifact trong repository. **Variant-aware selection** còn phụ thuộc metadata, category, usage, capabilities và dependency sets. Trong repo chỉ có POM, tên classifier tự nó không truyền đầy đủ mọi quy tắc selection của Gradle.

## 13. Các Java variants ít được nói tới

### 13.1. `mainSourceElements`

Một số Gradle versions hiển thị **`mainSourceElements`**, với category `verification` và verification type dành cho main sources. Nó có thể chứa các source directories, không phải sources JAR. Đây thường là variant phục vụ công cụ verification và có quy tắc tiêu thụ/publication riêng.

**Phân biệt:**
- `mainSourceElements`: source directories để verification/tooling theo model plugin.
- `sourcesElements`: documentation variant, thường đi cùng `*-sources.jar` khi bật `withSourcesJar()`.
- `apiElements`: compiled Java API-facing consumption.

Đừng cho rằng mọi variant được in bởi `outgoingVariants` đều sẽ được publish hoặc mọi IDE đều cần chúng. Một số entries có nhãn nội bộ/không publish.

### 13.2. `java-platform`

Gradle có Java Platform plugin để công bố dependency constraints/BOM-like platforms. Nó không nhất thiết cung cấp binary JAR như Java Library. **Category=platform** của variant khác **Category=library**; vì vậy consumer thường dùng `platform(...)` khi cần platform constraint, không dùng `implementation '...'` rồi hy vọng nhận class files.

### 13.3. `testCompileClasspath` và `testRuntimeClasspath`

Hai resolvable configurations dành cho **test source set** không phải outgoing variants. Chúng kết hợp dependency scopes dành cho test và main theo rules của plugin. Nếu test cần fixtures từ project khác, `testImplementation testFixtures(...)` biểu diễn nhu cầu đó. Không khai dependency của test vào `apiElements` chỉ vì tên có chữ API.

### 13.4. Các Gradle plugins khác

Android có build type/product flavor variants; native ecosystem có OS/architecture; Kotlin Multiplatform có target-specific attributes. Những plugin đó có thể tạo **nhiều** variants và custom capabilities, không bị ràng buộc đúng hai main Java variants. Nguyên tắc chung vẫn là consumer attributes + producer attributes + capabilities + artifact selection.

## 14. Khi nào chọn API và runtime variant không như mong đợi?

### 14.1. `No matching variant`

Ví dụ consumer yêu cầu:
~~~text
org.gradle.usage = java-api
org.gradle.jvm.version = 11
org.gradle.category = library
~~~

Producer chỉ cung cấp variant runtime Java 17 hoặc category không phải library. Không có variant tương thích: Gradle có thể báo `No matching variant` kèm bảng offered/requested attributes.

**Chẩn đoán:** xem `:producer:outgoingVariants`, `:consumer:resolvableConfigurations`, toolchain/target JVM. Sửa attributes/plugin/configuration thật, không sửa ngẫu nhiên dependency name.

### 14.2. `runtimeElements` có helper nhưng `apiElements` không có

Đây **có thể là đúng thiết kế**. Nếu helper không xuất hiện trong public API, engine nên dùng `implementation`. Khi app code cố import helper, compile fail là tín hiệu compile boundary đang được bảo vệ. Nếu helper thực sự là public API, cân nhắc `api` có căn cứ.

### 14.3. Report có JAR nhưng task compile không chạy `jar`

Đó có thể là vì consumer chọn secondary **classes** artifact set thay vì JAR. Sơ đồ graph selection không phải kế hoạch task execution đầy đủ. Dùng `--info` và task graph để xem Gradle đang tiêu thụ output nào; không vội thêm `dependsOn jar` thủ công.

### 14.4. Fixtures không được tìm thấy từ external module

Có thể publisher không công bố capability/Gradle Module Metadata hỗ trợ fixtures, hoặc thiếu artifact. Kiểm tra:
- Producer có áp `java-test-fixtures` không?
- Publication có xuất fixtures variants không?
- Consumer dùng `testFixtures('group:module:version')` hoặc `testFixtures(project(':module'))` đúng chưa?
- Repo có `.module`/metadata phù hợp không?
- Version/capability có khớp không?

**Không sửa bằng cách thêm main JAR vào testImplementation rồi mong nó tự chứa classes của fixtures.**

### 14.5. `sourcesElements` không xuất hiện

Có thể build chưa bật `withSourcesJar()`, Java plugin/version không hỗ trợ hoặc bạn đang xem sai project. Kiểm tra script/plugin và `outgoingVariants --all` nếu phiên bản hỗ trợ; không phải mọi project bắt buộc có sources/Javadoc variants.

### 14.6. Gradle download nhiều JAR dù main class chỉ dùng ít lớp

Runtime graph có thể bao gồm transitive dependencies do `runtimeElements` công bố. Gradle resolve theo dependencies/variants của component, không phân tích tất cả bytecode rồi tự loại mọi thư viện không được main class import. Muốn giảm graph, sửa dependency declarations/publishing metadata, không dùng `exclude` vô tội vạ.

## 15. Công cụ quan sát variant và capability

| Lệnh | Góc nhìn | Mục đích |
| --- | --- | --- |
| `./gradlew :engine:outgoingVariants` | Producer | Liệt kê variants, attributes, capabilities và artifacts |
| `./gradlew :engine:outgoingVariants --variant apiElements` | Producer | Nhìn kỹ contract của main API |
| `./gradlew :engine:outgoingVariants --variant runtimeElements` | Producer | Nhìn main runtime variant |
| `./gradlew :engine:outgoingVariants --variant testFixturesRuntimeElements` | Producer | Nhìn runtime capability/variant của fixtures |
| `./gradlew :app:resolvableConfigurations` | Consumer | Xem những resolvable configurations và requested attributes |
| `./gradlew :app:dependencies --configuration compileClasspath` | Consumer | Xem compile dependency graph |
| `./gradlew :app:dependencies --configuration runtimeClasspath` | Consumer | Xem runtime graph |
| `./gradlew :app:dependencyInsight --configuration compileClasspath --dependency engine --all-variants` | Consumer | Xem selection reasons/variant information khi được hỗ trợ |
| `./gradlew :app:compileJava --info` | Execution | Xem task/compile behavior |
| `./gradlew :app:run --quiet` | Runtime | Kiểm tra chương trình thực chạy |

**Quy trình điều tra ngắn:** (1) xác định consumer configuration, (2) đọc requested attributes, (3) đọc producer variants và capabilities, (4) đọc dependency graph/selection reason, (5) xác định artifact format/task outputs, (6) kiểm chứng compile/runtime/test.

Không dùng `configurations.apiElements.resolve()` như thể `apiElements` là resolvable configuration. Nếu viết Gradle plugin cần đọc programmatically, ưu tiên Gradle `ResolutionResult`/`ArtifactView` trên **resolvable configuration** và các task inputs được nối bằng Provider/FileCollection phù hợp.

## 16. Bảng so sánh cuối cùng

| Variant / cấu hình | Vai trò | Usage/Category điển hình | Consumer dùng khi |
| --- | --- | --- | --- |
| `apiElements` | Outgoing/consumable, **main feature** | `java-api` / `library` | Biên dịch chống lại public API |
| `runtimeElements` | Outgoing/consumable, **main feature** | `java-runtime` / `library` | Chạy thư viện |
| `sourcesElements` | Outgoing documentation variant | `documentation`, `docstype=sources` | Tải source JAR để xem mã |
| `javadocElements` | Outgoing documentation variant | `documentation`, `docstype=javadoc` | Tải Javadoc |
| `testFixturesApiElements` | Outgoing fixture feature | `java-api` / `library`, capability fixtures | Compile tests sử dụng fixture API |
| `testFixturesRuntimeElements` | Outgoing fixture feature | `java-runtime` / `library`, capability fixtures | Runtime tests sử dụng fixtures |
| `jsonSupportApiElements` (ví dụ) | Outgoing optional feature | `java-api` / `library`, custom capability | Compile với optional feature |
| `jsonSupportRuntimeElements` (ví dụ) | Outgoing optional feature | `java-runtime` / `library`, custom capability | Chạy optional feature |
| Secondary `classes` / `resources` | **Artifact set** của main variant | Library elements `classes` / `resources` | Lấy class/resource directories thay vì JAR |
| `mainSourceElements` (nếu có) | Verification/internal-oriented variant | `verification` | Công cụ kiểm chứng cần source directories |
| `compileClasspath` | Incoming/resolvable | Thường `java-api` / `library` | Consumer cần files để compile |
| `runtimeClasspath` | Incoming/resolvable | Thường `java-runtime` / `library` | Consumer cần files để chạy |
| `api` / `implementation` | Declarable dependency scopes | Không phải outgoing variants | Producer khai rõ API vs nội bộ |

**Ba quy tắc không được nhầm:**
1. `apiElements`/`runtimeElements` **không phải** hai file JAR bắt buộc khác nhau.
2. `api`/`implementation` **không phải** các variants consumer chọn; chúng là dependency scopes của producer.
3. `classes`/`resources` **không phải** một feature khác có capability riêng, mà thường là artifact sets phụ của một variant.

## 17. Bài tập có đáp án

### Bài 1 — Ai cần thấy helper?

`:engine` có `api project(':contract')` và `implementation project(':helper')`. `:app` khai `implementation project(':engine')`. Có `:helper` trên `:app:compileClasspath` không?

**Đáp án:** Thông thường **không**. Consumer compile chọn engine `apiElements`, không tự nhận implementation-only helper. Runtime graph của app sẽ có helper vì engine cần nó để chạy.

### Bài 2 — Tại sao API compile khác runtime?

Hai outgoing variants cùng công bố `engine-1.0.jar`, vậy chúng có giống hệt nhau không?

**Đáp án:** Không. `org.gradle.usage` và transitive dependency sets có thể khác. File JAR giống không có nghĩa variant contract giống.

### Bài 3 — Không cần tạo JAR lúc compile?

`:app:compileJava` hoàn thành khi engine đã compile classes, nhưng chưa thấy `:engine:jar` thực thi. Điều đó có trái với `apiElements` không?

**Đáp án:** Không. Artifact selection có thể dùng **secondary classes directory** của Java API variant. Graph vẫn có cùng dependency semantics.

### Bài 4 — Nguồn docs

Bật `java.withSourcesJar()` làm `sourcesElements` thay thế `apiElements` không?

**Đáp án:** Không. Nó thêm documentation variant để tooling tải sources JAR; consumer biên dịch bình thường vẫn chọn Java API-facing variant.

### Bài 5 — Test fixtures

Vì sao `testImplementation testFixtures(project(':engine'))` khác `testImplementation project(':engine')`?

**Đáp án:** Dòng đầu yêu cầu fixtures **capability**, chọn test-fixtures variants. Dòng sau yêu cầu main capability của engine; main library JAR không bắt buộc chứa fixture classes.

### Bài 6 — Tính tương thích JVM

Consumer Java 11 yêu cầu library producer Java 17. Lỗi có thể xảy ra ở tầng nào?

**Đáp án:** **Variant compatibility/attribute matching** theo JVM target. Không nhất thiết phải đến bước Java compiler mới báo lỗi.

### Bài 7 — Thực hành

Trong project phần 7:
1. Chạy `:app:run` và ghi dòng stdout.
2. Chạy `:app:dependencies --configuration compileClasspath`; chỉ ra vì sao có contract nhưng không có helper.
3. Chạy cùng lệnh cho runtimeClasspath; chỉ ra helper được kéo vào từ variant nào.
4. Chạy `:engine:outgoingVariants`; tìm `apiElements`, `runtimeElements`, `sourcesElements`, `javadocElements` và fixtures.
5. Chạy `:app:compileTestJava`, xác nhận `FixtureProbe` compile khi có `testImplementation testFixtures(...)`.
6. Bỏ tạm testFixtures dependency, chạy lại compileTestJava; quan sát lỗi thiếu `GreetingFixture` rồi khôi phục dependency.
7. Đổi engine `api project(':contract')` thành `implementation`; quan sát app compile và giải thích API boundary.

### Bài 8 — Custom feature

Một library có JSON support optional. Chỉ khai `implementation project(':engine')` đã có feature JSON chưa?

**Đáp án:** Không mặc nhiên. Nếu JSON support được mô hình bằng **feature capability** riêng, consumer phải yêu cầu capability ấy và Gradle phải có variant tương thích.

### Bài 9 — Publication

Repository chỉ có Maven POM và classifier `test-fixtures`. Có thể luôn viết `testFixtures('g:n:v')` thành công không?

**Đáp án:** Không. Cần metadata/capability tương ứng để Gradle nhận diện variant; artifact classifier đơn lẻ không biểu đạt đầy đủ model.

### Bài 10 — Chuẩn đoán nhanh

Gradle báo `No matching variant` dù JAR của module tồn tại. Tại sao vẫn có thể lỗi?

**Đáp án:** Artifact tồn tại không chứng minh có variant với **Usage, Category, JVM version, LibraryElements, Capability** phù hợp. Cần xem requested/offered attributes trước khi thay repository hay version.

**Tiêu chí đạt:** Bạn tự giải thích được bốn câu liên tiếp: **consumer yêu cầu attributes gì, producer công bố variants/capabilities gì, Gradle chọn graph variant nào, và artifact set/file nào thực sự đi vào compiler/runtime?**

## 18. Tài liệu Gradle chính thức

- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `api`/`implementation`, `apiElements`/`runtimeElements` và cấu hình.
- [Gradle — Variant Selection and Attribute Matching](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): attributes, compatibility, secondary variants, reports.
- [Gradle — Variants and Attributes](https://docs.gradle.org/current/userguide/variant_attributes.html): standard attributes, Maven/Gradle variant mapping.
- [Gradle — How to Create Feature Variants for a Library](https://docs.gradle.org/current/userguide/how_to_create_feature_variants_of_a_library.html): `registerFeature`, capabilities, publishing.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `java-test-fixtures`, fixture dependencies/capabilities.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): configurations, tasks, `withSourcesJar`/`withJavadocJar`.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`, `dependencyInsight`, variant diagnostics.
- [Gradle — Variant-aware Artifact Resolution](https://docs.gradle.org/current/userguide/artifact_resolution.html): artifact sets và artifact selection.
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html): publication của variants, dependencies, capabilities.
