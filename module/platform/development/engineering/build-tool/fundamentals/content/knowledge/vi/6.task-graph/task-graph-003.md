# Phân biệt phụ thuộc tác vụ với phụ thuộc thư viện

Trong một dự án Java, từ “dependency” thường xuất hiện ở nhiều ngữ cảnh. Ta có thể nói ứng dụng phụ thuộc vào một thư viện để gọi API, đồng thời task biên dịch phụ thuộc vào task sinh mã nguồn để có đủ tệp đầu vào. Hai quan hệ này có liên quan đến quá trình build, nhưng chúng mô tả hai vấn đề khác nhau.

**Phụ thuộc thư viện** mô tả một thành phần cần có để mã nguồn được biên dịch, ứng dụng được chạy hoặc kiểm thử được thực hiện. **Phụ thuộc tác vụ** mô tả một công việc build phải được thực hiện trước một công việc khác, thường vì công việc sau cần đầu ra của công việc trước.

Nếu nhầm hai loại quan hệ, ta dễ thêm dependency vào sai vị trí, tạo thứ tự task không cần thiết, thiếu thư viện lúc chạy hoặc hiểu sai vì sao một module khác được build trước. Bài này giải thích hai loại phụ thuộc trong Gradle và Maven, cách chúng tác động đến build và cách kiểm tra từng loại.

## 1. Hai loại phụ thuộc trả lời hai câu hỏi khác nhau

Hãy xét một ứng dụng `shop-app` sử dụng thư viện `domain` và thư viện bên ngoài `jackson-databind`. Trước khi đóng gói ứng dụng, build tool cần biên dịch mã nguồn, xử lý tài nguyên, chạy kiểm thử và tạo JAR.

Có hai câu hỏi riêng:

- **Ứng dụng cần những thư viện nào?** `shop-app` cần lớp của `domain` và API của Jackson. Đây là quan hệ phụ thuộc thư viện.
- **Công việc nào cần chạy trước?** Task biên dịch cần có mã nguồn và dependency phù hợp; task đóng gói cần các lớp đã biên dịch và tài nguyên. Đây là quan hệ phụ thuộc tác vụ.

Có thể hình dung hai đồ thị như sau:

```text
ĐỒ THỊ PHỤ THUỘC THƯ VIỆN

shop-app
  ├── domain
  └── jackson-databind
        └── jackson-core


ĐỒ THỊ PHỤ THUỘC TÁC VỤ

compileJava
      |
      v
classes
      |
      v
jar
      |
      v
assemble
```

Đồ thị thư viện mô tả quan hệ giữa module/artifact và được dùng để phân giải classpath hoặc module path. Đồ thị tác vụ mô tả các task cần thực thi và thứ tự thực thi của chúng. Đồ thị task thực tế có thể có nhiều nhánh: biên dịch mã chính, xử lý tài nguyên, biên dịch test, chạy test, kiểm tra và đóng gói.

Hai đồ thị có thể liên kết với nhau. Ví dụ, một Gradle project dependency trỏ đến artifact do project khác tạo ra có thể khiến Gradle suy ra task tạo artifact đó cần chạy. Nhưng bản thân hai quan hệ vẫn có ý nghĩa khác nhau: một bên nói ứng dụng cần artifact nào, bên kia nói cần thực hiện công việc nào để tạo artifact.

## 2. Phụ thuộc thư viện là gì?

Phụ thuộc thư viện (library dependency) là một thư viện hoặc module mà project cần sử dụng. Thư viện có thể chứa class, interface, annotation, tài nguyên hoặc metadata mà mã nguồn cần trong quá trình compile, runtime hoặc test.

Một dependency thường được xác định bằng tọa độ artifact. Ví dụ với Maven:

```text
com.fasterxml.jackson.core:jackson-databind:2.17.2
```

Ba thành phần chính là:

- `groupId`: nhóm hoặc tổ chức phát hành artifact.
- `artifactId`: tên artifact.
- `version`: phiên bản cần sử dụng.

Với Gradle, có thể khai báo dependency ngoài bằng tọa độ tương tự. Với dự án nhiều module, dependency cũng có thể trỏ đến project khác trong cùng build.

### 2.1. Dependency ảnh hưởng đến classpath như thế nào?

Khi compiler biên dịch một lớp có câu lệnh import hoặc tham chiếu đến kiểu của thư viện, compiler phải tìm được định nghĩa của kiểu đó. Dependency phù hợp được đưa vào compile classpath.

Khi ứng dụng chạy, JVM cũng cần tìm được các lớp mà ứng dụng sử dụng. Dependency cần thiết ở runtime phải có trên runtime classpath hoặc module path, hoặc được đóng gói theo cơ chế phân phối của ứng dụng.

Vì vậy, một thư viện có thể cần cho compile, runtime, cả hai hoặc chỉ cho test. Build tool dùng cấu hình/scope để biết dependency được sử dụng ở giai đoạn nào và có được truyền tiếp cho consumer hay không.

### 2.2. Các cấu hình dependency thường gặp trong Gradle

Với Gradle Java plugin, một số configuration thường gặp là:

| Configuration | Ý nghĩa tổng quát |
|---|---|
| `implementation` | Dependency cần cho implementation của project; có trong compile/runtime classpath của project, nhưng không được công khai như API compile của consumer qua Java Library semantics |
| `api` | Dependency thuộc API mà consumer cần nhìn thấy khi compile; thường dùng với Java Library plugin |
| `compileOnly` | Cần khi biên dịch nhưng không tự đưa vào runtime classpath thông thường |
| `runtimeOnly` | Cần lúc chạy nhưng không cần để biên dịch mã nguồn chính |
| `testImplementation` | Cần để biên dịch và chạy mã nguồn test |
| `testRuntimeOnly` | Chỉ cần khi chạy test |

Ví dụ `build.gradle.kts`:

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.2")
    compileOnly("org.projectlombok:lombok:1.18.34")
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.0")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.0")
}

tasks.test {
    useJUnitPlatform()
}
```

Các cấu hình này mô tả **thư viện cần thiết cho từng classpath**, không phải tên task. Việc khai báo `implementation(...)` không tương đương với `dependsOn(...)`.

### 2.3. Dependency giữa các Gradle project

Trong multi-project build, một project có thể sử dụng artifact của project khác:

```kotlin
dependencies {
    implementation(project(":domain"))
}
```

Giả sử `:app` sử dụng các class công khai từ `:domain`. Khai báo trên đưa artifact/variant phù hợp của `:domain` vào dependency graph của `:app`.

Khi Gradle phân giải project dependency, nó biết artifact đó được tạo từ project nào và có thể suy ra các task producer cần thiết để cung cấp artifact. Ví dụ, task biên dịch hoặc đóng gói của `:domain` có thể được đưa vào task graph khi task của `:app` cần artifact tương ứng. Chi tiết task producer được chọn phụ thuộc variant và cấu hình plugin.

Điểm quan trọng: `implementation(project(":domain"))` diễn tả `:app` cần thư viện/module `:domain`. Gradle dùng quan hệ đó để phân giải artifact và kết nối các công việc tạo artifact khi cần. Đây không phải cú pháp khai báo tùy ý rằng mọi task trong `:domain` phải chạy trước mọi task trong `:app`.

## 3. Phụ thuộc tác vụ là gì?

Task dependency (phụ thuộc tác vụ) mô tả rằng để hoàn thành một task, Gradle cần thực hiện một task khác trước. Task phụ thuộc vào đầu ra hoặc kết quả công việc của task kia.

Ví dụ:

```text
generateSources
       |
       v
compileJava
       |
       v
jar
```

Nếu `compileJava` cần các tệp Java do `generateSources` tạo ra, task sinh mã phải được đưa vào graph và hoàn thành trước khi compiler chạy.

Trong Gradle, có thể khai báo quan hệ này bằng `dependsOn`:

```kotlin
tasks.register("generateSources") {
    doLast {
        println("Generating source files")
    }
}

tasks.register("prepareCompilation") {
    dependsOn("generateSources")
    doLast {
        println("Compilation prerequisites are ready")
    }
}
```

Khi yêu cầu chạy `prepareCompilation`, Gradle cũng đưa `generateSources` vào task graph và thực hiện nó trước. Nếu chỉ yêu cầu một task không phụ thuộc vào hai task trên, `generateSources` không tự chạy.

### 3.1. `dependsOn` tạo quan hệ thực thi

`dependsOn` có nghĩa task hiện tại cần các task được chỉ định thực hiện trước. Có thể truyền tên task, task object, task provider hoặc các notation dependency mà Gradle hỗ trợ.

Ví dụ với task provider trong Kotlin DSL:

```kotlin
val generateReport = tasks.register("generateReport") {
    val reportFile = layout.buildDirectory.file("generated/report.txt")
    outputs.file(reportFile)

    doLast {
        val file = reportFile.get().asFile
        file.parentFile.mkdirs()
        file.writeText("Build report")
    }
}

tasks.register("verifyReport") {
    dependsOn(generateReport)
    val reportFile = layout.buildDirectory.file("generated/report.txt")
    inputs.file(reportFile)

    doLast {
        check(reportFile.get().asFile.exists())
        println("Report exists")
    }
}
```

Khi chạy `verifyReport`, Gradle chạy `generateReport` trước. Task tạo báo cáo khai báo output; task kiểm tra khai báo input và quan hệ phụ thuộc. Ví dụ được rút gọn để minh họa task graph; trong build thực tế nên dùng task type có kiểu input/output rõ ràng, tránh viết logic file trực tiếp trong build script nếu có thể.

### 3.2. Thứ tự tác vụ không đồng nghĩa với phụ thuộc tác vụ

Gradle có các API liên quan đến thứ tự task. Chúng không có cùng ý nghĩa với `dependsOn`.

| API | Ý nghĩa | Có tự đưa task được nhắc đến vào graph? |
|---|---|---|
| `dependsOn` | Task hiện tại cần task kia hoàn thành trước | Có |
| `mustRunAfter` | Nếu cả hai task đều được chọn, task hiện tại phải chạy sau task kia | Không |
| `shouldRunAfter` | Đề xuất thứ tự nếu có thể; Gradle có thể bỏ qua để tránh deadlock/cycle hoặc khi chạy song song | Không |
| `finalizedBy` | Đăng ký task finalizer chạy sau task được finalize khi task đó được thực thi | Có, finalizer được đưa vào graph theo quan hệ này |

Ví dụ:

```kotlin
tasks.named("integrationTest") {
    mustRunAfter("test")
}
```

Nếu chỉ chạy `integrationTest`, task `test` không tự được chạy. `mustRunAfter` chỉ ràng buộc thứ tự khi cả hai task đã được đưa vào graph vì lý do khác.

Nếu muốn `test` thực sự được chạy trước `integrationTest`, có thể dùng:

```kotlin
tasks.named("integrationTest") {
    dependsOn("test")
}
```

`finalizedBy` hữu ích cho tác vụ dọn dẹp hoặc thu thập kết quả cần chạy sau một task, kể cả khi task chính kết thúc thất bại theo quy tắc finalizer của Gradle:

```kotlin
tasks.named("integrationTest") {
    finalizedBy("collectTestLogs")
}
```

Không nên dùng `mustRunAfter` như cách thay thế `dependsOn` khi task hiện tại thực sự cần đầu ra của task kia. Làm vậy có thể khiến task tiêu thụ chạy mà task tạo đầu vào chưa hề được chạy.

## 4. Gradle kết nối task với đầu vào và đầu ra

Task thường có input và output. Khi task A tạo file mà task B sử dụng, quan hệ dữ liệu giữa chúng cần được mô tả để Gradle biết khi nào phải chạy task A và khi nào task B có thể được thực hiện.

```text
Task A
  outputs.file("build/generated/config.json")
             |
             | file được tạo
             v
Task B
  inputs.file("build/generated/config.json")
```

Chỉ khai báo cùng một đường dẫn file ở hai task chưa chắc đã đủ để Gradle suy ra task producer trong mọi cách cấu hình. Nên truyền output qua `Provider`/`TaskProvider`, hoặc dùng `builtBy`/task dependency phù hợp để giữ thông tin producer và tránh phụ thuộc thủ công vào đường dẫn rời rạc.

Ví dụ khái niệm với task output được tham chiếu qua task provider:

```kotlin
val generateConfig = tasks.register("generateConfig") {
    val outputFile = layout.buildDirectory.file("generated/config.json")
    outputs.file(outputFile)

    doLast {
        val file = outputFile.get().asFile
        file.parentFile.mkdirs()
        file.writeText("{\"mode\":\"demo\"}")
    }
}

tasks.register("consumeConfig") {
    dependsOn(generateConfig)
    val inputFile = layout.buildDirectory.file("generated/config.json")
    inputs.file(inputFile)

    doLast {
        println(inputFile.get().asFile.readText())
    }
}
```

Ở đây `dependsOn` thể hiện rõ thứ tự producer/consumer. Trong các task type và API Gradle chuyên biệt, output có thể được truyền trực tiếp bằng provider để quan hệ task được suy ra tự động. Ví dụ, các task `JavaCompile`, `Jar`, `Copy` và nhiều task plugin chuẩn đã khai báo input/output theo mô hình này.

Việc khai báo input/output còn giúp Gradle:

- Xác định task có cần chạy lại hay không.
- Bỏ qua task khi output còn hợp lệ và input không đổi (`UP-TO-DATE`).
- Sử dụng build cache cho task cacheable.
- Lập lịch task theo quan hệ producer/consumer.
- Hỗ trợ thực thi song song khi các task không có xung đột và có thể chạy độc lập.

Không nên thêm `dependsOn` giữa hai task chỉ vì muốn chúng chạy theo một thứ tự tùy ý. Trước tiên hãy xác định task sau có thật sự cần task trước hoặc output của nó hay không. Nếu chỉ cần ràng buộc thứ tự khi cả hai đã được chọn, API ordering là đúng ý nghĩa hơn.

## 5. Một ví dụ Gradle kết hợp cả hai loại dependency

Giả sử dự án có hai project `:domain` và `:app`. Ứng dụng cần class của `:domain`, thư viện Jackson và cần sinh thêm source trước khi compile.

Trong `app/build.gradle.kts`:

```kotlin
plugins {
    java
}

dependencies {
    implementation(project(":domain"))
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.2")
}

val generateSources = tasks.register("generateSources") {
    val generatedDir = layout.buildDirectory.dir("generated/sources/demo")
    outputs.dir(generatedDir)

    doLast {
        val dir = generatedDir.get().asFile
        dir.mkdirs()
        dir.resolve("GeneratedMarker.java").writeText(
            "package demo; public class GeneratedMarker {}"
        )
    }
}

tasks.named("compileJava") {
    dependsOn(generateSources)
}
```

Trong ví dụ:

- `implementation(project(":domain"))` là dependency giữa các project/artifact. Nó làm artifact của `:domain` trở thành dependency của `:app`.
- `implementation("...jackson-databind...")` là dependency thư viện ngoài. Nó ảnh hưởng đến classpath của `:app`.
- `dependsOn(generateSources)` là quan hệ task. Nó yêu cầu task sinh source được thực hiện trước `compileJava`.
- `outputs.dir(...)` khai báo đầu ra của task sinh source. Một dự án thực tế cần tích hợp thư mục generated source vào source set/Java source của compiler, ví dụ thông qua `source(...)` hoặc cấu hình source set phù hợp. Khai báo `dependsOn` một mình chỉ bảo đảm task chạy trước; nó không tự làm compiler nhận diện mọi thư mục vừa sinh.

Ví dụ này cho thấy ba việc có thể cùng xuất hiện trong một build nhưng không nên gọi chung là một loại dependency.

## 6. Phụ thuộc thư viện trong Maven

Maven khai báo dependency của project trong `pom.xml`. Mỗi dependency có tọa độ artifact và có thể có scope.

Ví dụ:

```xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>2.17.2</version>
    </dependency>

    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.0</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Các scope thông dụng:

| Scope | Compile classpath | Runtime classpath | Test classpath | Có truyền tiếp theo quy tắc scope? |
|---|---|---|---|---|
| `compile` (mặc định) | Có | Có | Có | Có, theo quy tắc transitive của Maven |
| `provided` | Có | Không trên runtime classpath thông thường của project | Có | Không truyền như compile dependency thông thường |
| `runtime` | Không cho compile source chính | Có | Có | Có theo quy tắc scope |
| `test` | Không | Không | Có | Không truyền cho consumer thông thường |
| `system` | Có | Có | Có | Không được khuyến nghị; dùng đường dẫn cục bộ và không được phân giải từ repository như dependency thông thường |
| `import` | Dùng trong `dependencyManagement` với POM type để nhập BOM | Không phải scope classpath trực tiếp | Không phải scope classpath trực tiếp | Dùng để quản lý phiên bản dependency |

Dependency mặc định có scope `compile` nếu không khai báo scope. Maven cũng hỗ trợ dependency transitive: dependency mà thư viện trực tiếp khai báo có thể được đưa vào dependency graph của project, theo quy tắc scope và exclusions.

Scope là thuộc tính của quan hệ dependency thư viện. Nó không chỉ định Maven chạy plugin goal nào hoặc task nào trước task nào.

## 7. Maven tổ chức công việc build như thế nào?

Maven dùng **build lifecycle**, gồm các phase có thứ tự. Plugin cung cấp các goal và có thể gắn goal vào một phase. Khi gọi một phase, Maven thực hiện các phase đứng trước trong lifecycle tương ứng và các goal được bind vào chúng.

Ví dụ lệnh:

```bash
./mvnw clean package
```

Maven thực hiện lifecycle `clean` để xóa output cũ, sau đó đi qua các phase của default lifecycle đến `package`. Các plugin có thể thực hiện goal ở những phase như `compile`, `test`, `package`.

Một số phase quen thuộc trong default lifecycle:

| Phase | Mục đích tổng quát |
|---|---|
| `validate` | Kiểm tra project có đầy đủ thông tin cần thiết |
| `compile` | Biên dịch mã nguồn chính |
| `test` | Chạy kiểm thử đơn vị |
| `package` | Đóng gói artifact |
| `verify` | Chạy các kiểm tra bổ sung để xác nhận package hợp lệ |
| `install` | Cài artifact vào local repository |
| `deploy` | Đưa artifact lên remote repository |

Maven không cung cấp task graph tùy biến theo cùng mô hình task của Gradle. Thứ tự công việc thường được biểu diễn qua phase của lifecycle, plugin goal được bind vào phase và thứ tự module trong reactor. Vì vậy, khi nói về Maven, nên phân biệt dependency artifact trong POM với thứ tự thực thi phase/goal của build lifecycle.

### 7.1. Plugin goal không phải library dependency của ứng dụng

Plugin thực hiện công việc build. Ví dụ, Maven Compiler Plugin biên dịch mã nguồn, Maven Surefire Plugin chạy test, Maven JAR Plugin đóng gói JAR.

Một cấu hình plugin có thể như sau:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>21</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Plugin này là công cụ build được Maven gọi. Nó không phải thư viện mà ứng dụng cần import để chạy. Dependency của plugin, nếu có, phục vụ môi trường thực thi plugin; chúng cũng khác với dependency của project trong phần `<dependencies>`.

### 7.2. Dependency giữa các Maven module ảnh hưởng đến thứ tự reactor

Trong Maven multi-module build, nếu module `app` khai báo dependency đến artifact do module `domain` tạo ra và cả hai cùng thuộc reactor, Maven có thể sắp xếp `domain` trước `app` dựa trên quan hệ project dependency.

Ví dụ POM của `app`:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>domain</artifactId>
        <version>${project.version}</version>
    </dependency>
</dependencies>
```

Root aggregator có thể khai báo các module:

```xml
<packaging>pom</packaging>

<modules>
    <module>domain</module>
    <module>app</module>
</modules>
```

Reactor sắp xếp các project theo quan hệ phụ thuộc và một số quan hệ build khác để project cung cấp dependency được xử lý trước consumer khi cần. Đây là thứ tự giữa các Maven project trong một reactor build, không phải cú pháp khai báo task dependency tùy ý như Gradle `dependsOn`.

## 8. Dependency của ứng dụng, dependency của build tool và task dependency

Ngoài hai loại chính, còn có một nhóm dễ bị nhầm: **dependency của chính build tool hoặc plugin**.

| Loại | Ví dụ | Dùng để làm gì? |
|---|---|---|
| Library dependency của project | Jackson, JUnit, project `:domain` | Cung cấp class/API cho compile, runtime hoặc test |
| Task dependency / quan hệ build | `compileJava.dependsOn(generateSources)` | Bảo đảm task cần thiết được thực hiện trước |
| Build plugin/tool dependency | Gradle plugin, Maven plugin, plugin classpath dependency | Cung cấp công cụ và logic để cấu hình hoặc thực hiện build |

Trong Gradle, plugin có thể được khai báo qua `plugins {}`; build logic cũ hoặc đặc thù có thể sử dụng `buildscript { dependencies { classpath(...) } }`. Dependency trong buildscript classpath dùng để chạy build logic, không phải dependency runtime của ứng dụng.

Trong Maven, plugin được khai báo trong `build/plugins` hoặc được quản lý qua `pluginManagement`. Các dependency khai báo bên trong một plugin là dependency phục vụ plugin. Chúng không tự động trở thành dependency của ứng dụng.

Khi tìm một tên thư viện trong repository, hãy xem nó xuất hiện trong cấu hình nào. Cùng một tọa độ Maven có thể xuất hiện trong project dependency, plugin dependency hoặc buildscript classpath nhưng mang ý nghĩa khác nhau.

## 9. So sánh cách biểu diễn giữa Gradle và Maven

| Khía cạnh | Gradle | Maven |
|---|---|---|
| Khai báo thư viện project | `dependencies { implementation(...) }` | `<dependencies><dependency>...` |
| Phân loại classpath | Configurations như `implementation`, `runtimeOnly`, `testImplementation` | Scopes như `compile`, `runtime`, `test`, `provided` |
| Phụ thuộc giữa module | `implementation(project(":domain"))` hoặc configuration phù hợp | Dependency tọa độ artifact của module khác |
| Điều phối công việc build | Task graph | Lifecycle phase và plugin goal |
| Khai báo task prerequisite | `dependsOn(...)` | Thường gắn goal vào phase hoặc dùng plugin/lifecycle phù hợp; không có API tổng quát tương đương `dependsOn` trong POM chuẩn |
| Ràng buộc thứ tự task | `mustRunAfter`, `shouldRunAfter` | Thứ tự phase/goal và reactor; plugin có cơ chế cấu hình riêng |
| Xem dependency graph | `dependencies`, `dependencyInsight` | `dependency:tree` |
| Xem công việc sẽ chạy | `--dry-run` hoặc task graph tooling | Lifecycle/goal, log Maven và effective POM |

Không nên dịch máy móc một cấu hình từ Gradle sang Maven hoặc ngược lại. Gradle cho phép định nghĩa task graph linh hoạt; Maven dựa trên lifecycle và plugin convention. Hai công cụ cùng giải quyết việc build nhưng mô hình điều phối không giống nhau.

## 10. Cách kiểm tra hai loại dependency

Khi build có lỗi, hãy chọn lệnh kiểm tra theo câu hỏi cần trả lời.

### 10.1. Kiểm tra dependency graph của Gradle

Xem dependency của một configuration:

```bash
./gradlew :app:dependencies --configuration compileClasspath
```

Xem dependency nào kéo một thư viện cụ thể vào graph:

```bash
./gradlew :app:dependencyInsight \
    --dependency jackson-databind \
    --configuration runtimeClasspath
```

Các lệnh này giúp tìm phiên bản được chọn, dependency bắc cầu và lý do một module/artifact xuất hiện trong configuration.

### 10.2. Kiểm tra task graph của Gradle

Liệt kê task có thể có:

```bash
./gradlew :app:tasks --all
```

Xem các task được lên lịch cho một yêu cầu build mà không thực hiện action của task:

```bash
./gradlew :app:build --dry-run
```

Nếu task không xuất hiện, hãy xem task đó có được chọn trực tiếp, có được task khác phụ thuộc vào hay có được đưa vào graph qua quan hệ producer/consumer hay không. `--dry-run` giúp nhìn thứ tự thực thi dự kiến nhưng không giải thích toàn bộ nguyên nhân của từng dependency; cần xem build script hoặc log phù hợp.

### 10.3. Kiểm tra dependency graph của Maven

Xem cây dependency của project:

```bash
./mvnw dependency:tree
```

Lọc theo artifact nếu cần:

```bash
./mvnw dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
```

Lệnh này hiển thị dependency trực tiếp và bắc cầu cùng scope, giúp tìm thư viện được kéo vào từ đâu.

### 10.4. Kiểm tra công việc build của Maven

Xem effective POM để biết cấu hình sau khi kế thừa parent, áp dụng profile và hợp nhất:

```bash
./mvnw help:effective-pom
```

Khi cần hiểu goal/plugin được gọi ở đâu, xem cấu hình `<build><plugins>`, execution và phase binding trong POM/effective POM. Có thể tăng mức log:

```bash
./mvnw -X verify
```

`-X` tạo log debug rất chi tiết; hãy dùng khi cần điều tra và tránh chia sẻ log nếu chúng có thông tin môi trường nhạy cảm.

## 11. Các nhầm lẫn thường gặp

**Thêm `implementation(...)` rồi mong một task tùy chỉnh tự chạy.** `implementation` khai báo thư viện trên classpath. Nếu task `generateSources` phải chạy trước `compileJava`, cần mô tả quan hệ task hoặc kết nối output/input theo API Gradle.

**Dùng `mustRunAfter` thay cho `dependsOn`.** `mustRunAfter` không tự đưa task prerequisite vào graph. Nếu task B không thể chạy khi task A chưa tạo output, hãy khai báo dependency thực sự.

**Cho rằng dependency thư viện luôn làm mọi task của module cung cấp chạy trước.** Gradle chọn task producer phù hợp với artifact/variant được tiêu thụ. Maven reactor cũng sắp xếp module theo quan hệ cần thiết. Không có nghĩa mọi task của module đó đều phải chạy trước mọi task consumer.

**Cho rằng dependency có trong compile classpath thì chắc chắn có trong runtime.** Một dependency có thể được khai báo `compileOnly` trong Gradle hoặc `provided` trong Maven. Cần kiểm tra đúng runtime configuration/classpath.

**Cho rằng task dependency sẽ cung cấp classpath.** `dependsOn` chỉ thiết lập quan hệ thực thi. Nếu compiler cần một thư viện, phải khai báo dependency trong configuration/scope phù hợp để nó có mặt trên classpath.

**Nhầm Maven plugin với project library.** Plugin cung cấp công việc build; dependency trong `<dependencies>` cung cấp thư viện cho project. Chúng có thể dùng cùng cơ chế artifact repository nhưng thuộc hai phạm vi khác nhau.

**Cho rằng Maven scope là thứ tự phase.** `test` scope chỉ định dependency được dùng trong test classpath. `test` phase là một bước trong lifecycle. Tên giống nhau nhưng ý nghĩa khác nhau.

## 12. Quy trình suy luận khi cần thêm một dependency

Trước khi sửa build file, hãy xác định điều bạn cần:

1. Nếu mã nguồn cần gọi API của thư viện, hãy thêm library dependency vào configuration/scope phù hợp.
2. Nếu một module cần artifact từ module khác, hãy khai báo project/module dependency theo đúng hệ sinh thái.
3. Nếu một công việc build cần output do task khác tạo ra, hãy khai báo task dependency hoặc nối input/output để build tool biết producer.
4. Nếu chỉ cần hai task có thứ tự khi cả hai đã được chọn, hãy dùng ordering constraint phù hợp.
5. Nếu cần công cụ thực hiện build, hãy khai báo plugin hoặc build logic dependency ở đúng phạm vi.
6. Sau đó, kiểm tra đúng graph: dependency tree cho thư viện; task graph/lifecycle và log cho công việc build.

Ví dụ: nếu compiler báo `package com.fasterxml.jackson.databind does not exist`, hãy kiểm tra compile dependency/classpath. Nếu task `compileJava` chạy trước task sinh mã và không tìm thấy tệp generated, hãy kiểm tra task dependency cùng source set/input-output. Hai lỗi có thể cùng xuất hiện trong một lần build nhưng cần sửa ở hai quan hệ khác nhau.

## 13. Những điều cần ghi nhớ

- Phụ thuộc thư viện trả lời câu hỏi project cần artifact hoặc API nào để compile, runtime hay test.
- Phụ thuộc tác vụ trả lời câu hỏi công việc build nào phải được thực hiện để một task khác có thể hoàn thành.
- Gradle biểu diễn library dependency bằng configurations như `implementation`, `api`, `compileOnly`, `runtimeOnly` và project dependency; task dependency thường được khai báo bằng `dependsOn` hoặc suy ra qua quan hệ input/output.
- `mustRunAfter` và `shouldRunAfter` ràng buộc thứ tự nhưng không tự đưa task prerequisite vào graph; `finalizedBy` mô tả công việc chạy sau task được finalize.
- Maven biểu diễn library dependency trong `<dependencies>` bằng scope; build work được điều phối qua lifecycle phase và plugin goal.
- Dependency giữa Maven module có thể ảnh hưởng đến thứ tự reactor; đó vẫn là quan hệ project/artifact trong build nhiều module.
- Plugin dependency và buildscript classpath phục vụ build tool, không tự trở thành library dependency của ứng dụng.
- Dùng dependency tree để điều tra thư viện và task graph/lifecycle để điều tra thứ tự công việc.

Khi đọc một dòng khai báo có chữ “dependency”, hãy xác định nó thuộc project dependency, plugin/build dependency hay task dependency. Sau đó kiểm tra đúng đồ thị mà nó tác động. Phân biệt được hai loại phụ thuộc chính giúp build rõ ràng hơn, tránh thêm quan hệ thừa và tìm đúng nguyên nhân khi compile, test hoặc đóng gói thất bại.
