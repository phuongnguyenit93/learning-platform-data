# Cú pháp Kotlin cần thiết cho build script .gradle.kts

## 1. Mục tiêu của bài học

**Gradle Kotlin DSL** cho phép viết cấu hình Gradle bằng cú pháp Kotlin trong các tệp như `build.gradle.kts` và `settings.gradle.kts`. Để sử dụng thành thạo, không cần học toàn bộ ngôn ngữ Kotlin trước; nhưng cần hiểu những cấu trúc Kotlin thường xuất hiện trong script và cách chúng tương tác với API Gradle.

Sau bài này, bạn có thể:

- Đọc cú pháp `plugins { }`, `repositories { }`, `dependencies { }`, `java { }` và `tasks { }` trong `build.gradle.kts`.
- Sử dụng hàm, chuỗi, biến `val`/`var`, lambda, generic type và receiver trong một build script.
- Phân biệt phép gán Kotlin thông thường với việc cấu hình `Property<T>` và `Provider<T>` của Gradle.
- Đăng ký task bằng `tasks.register(...)`, cấu hình task có sẵn bằng `tasks.named(...)` và khai báo `dependsOn(...)`.
- Dịch được các mẫu Groovy DSL phổ biến sang Kotlin DSL mà không sao chép nguyên cú pháp.
- Tạo, chạy và tự kiểm tra một ứng dụng Java 17 có cấu hình `build.gradle.kts` hoàn chỉnh.

**Giới hạn phạm vi:** Bài tập trung vào Kotlin dùng để *mô tả build*. Nó không đòi hỏi viết ứng dụng bằng Kotlin, không đi sâu cú pháp nâng cao như coroutines hoặc metaprogramming, cũng không coi script Gradle là chương trình Kotlin `main()` thông thường.

## 2. Kotlin DSL là gì? Nó chạy ở đâu?

Gradle hỗ trợ hai DSL phổ biến:

| Vai trò | Groovy DSL | Kotlin DSL |
| --- | --- | --- |
| Cấu hình một project | `build.gradle` | `build.gradle.kts` |
| Cấu hình cấu trúc build | `settings.gradle` | `settings.gradle.kts` |
| Tập lệnh khởi tạo tùy chọn | `init.gradle` | `init.gradle.kts` |
| Ngôn ngữ cú pháp | Groovy | Kotlin |
| API Gradle cốt lõi | Cùng hệ API Gradle | Cùng hệ API Gradle |

Đuôi `.kts` là **Kotlin script**. Gradle biên dịch và đánh giá script theo vòng đời build; các đối tượng `Project`, `Settings`, `Task`, `Provider`, `Configuration` đến từ Gradle và các plugin.

Ví dụ tệp `build.gradle.kts` ngắn:

~~~kotlin
plugins {
    id("java")
}

group = "com.example"
version = "1.0.0"

repositories {
    mavenCentral()
}
~~~

Các dòng trên **không biên dịch một file Kotlin của ứng dụng**. Chúng khai báo project, áp dụng Java plugin và cấu hình repository. Bạn hoàn toàn có thể dùng `build.gradle.kts` để build **mã nguồn Java** trong `src/main/java` mà không có file `.kt` nào.

Ngược lại, khi muốn **biên dịch mã nguồn Kotlin**, cần plugin phù hợp, chẳng hạn Kotlin JVM plugin; chỉ đổi tên `build.gradle` sang `build.gradle.kts` không tự thêm khả năng compile Kotlin source.

Các file trong cùng multi-project build có thể dùng DSL khác nhau, nhưng nhóm thường chọn một kiểu nhất quán để giảm công sức bảo trì.

## 3. Kiến thức Kotlin tối thiểu: giá trị, biến, kiểu

### 3.1. `val`, `var` và phép gán `=`

Trong Kotlin:

- `val`: tham chiếu chỉ được gán một lần; ưu tiên dùng cho giá trị không cần gán lại.
- `var`: biến có thể được gán lại.
- `=`: phép gán thông thường; trong các Gradle DSL extension, nó cũng thường là cú pháp gán property Kotlin khi API hỗ trợ.

Ví dụ mã Kotlin minh họa (có thể đặt trong một đoạn xử lý script):

~~~kotlin
val moduleName = "catalog"
val javaVersion: Int = 17

var buildMode = "debug"
buildMode = "release"

println("$moduleName, Java $javaVersion, mode=$buildMode")
~~~

Dòng được in:

~~~text
catalog, Java 17, mode=release
~~~

Kotlin thường tự suy ra kiểu: `val moduleName = "catalog"` là một `String`, `val javaVersion = 17` là `Int`. Khi cần, khai báo kiểu tường minh bằng `:` như `val javaVersion: Int = 17`.

**Không nhầm `val` với bất biến sâu của đối tượng:** `val items = mutableListOf("app")` cấm gán lại biến `items` sang list khác, nhưng vẫn có thể gọi `items.add("lib")` vì đối tượng là mutable. Trong build scripts, ưu tiên cấu hình bằng API của Gradle hơn là thay đổi tùy tiện các collection dùng nội bộ.

### 3.2. Tên, dấu chấm phẩy, comment

Kotlin dùng dấu ngoặc `()` khi gọi hàm có đối số:

~~~kotlin
println("Build started")
val names = listOf("app", "library")
val count = names.size
~~~

Dấu chấm phẩy cuối dòng thường **không cần**. Comment:

~~~kotlin
// Comment một dòng.

/*
Comment
nhiều dòng.
*/
~~~

Tên thông thường dùng chữ cái, chữ số và gạch dưới; phân biệt chữ hoa/chữ thường. Kotlin cũng cho phép *backtick identifiers* để dùng tên không hợp lệ như identifier bình thường, ví dụ `val ` (một số DSL plugin dựng sẵn sử dụng tên bao trong backtick); với script mới, nên đặt tên đơn giản và rõ nghĩa.

### 3.3. Chuỗi: dấu nháy đôi là bắt buộc cho String

~~~kotlin
val pluginId = "java"
val version = "1.0.0"
val firstLetter: Char = 'j'
~~~

Trong Kotlin, `"java"` là `String`; `'j'` là `Char`. Viết `'java'` là sai vì char literal chứa nhiều ký tự. Đây là lỗi rất phổ biến khi sao chép cấu hình Groovy sang Kotlin DSL:

~~~groovy
// Groovy DSL
plugins { id 'java' }
dependencies { implementation 'org.example:tool:1.0' }
~~~

~~~kotlin
// Kotlin DSL
plugins { id("java") }
dependencies { implementation("org.example:tool:1.0") }
~~~

Dòng `implementation(...)` chỉ hợp lệ khi plugin đã tạo configuration đó (ví dụ Java plugin) và có repository/dependency thích hợp; đây là minh họa **cú pháp**, không phải ví dụ dự án độc lập với tọa độ `org.example:tool:1.0`.

### 3.4. String templates: `$name` và `${expression}`

Kotlin cho phép nối thông tin vào chuỗi:

~~~kotlin
val name = "api"
val count = 3

println("Project: $name")
println("Uppercase: ${name.uppercase()}")
println("Count next: ${count + 1}")
~~~

Stdout:

~~~text
Project: api
Uppercase: API
Count next: 4
~~~

Khi chỉ nội suy tên biến đơn giản, dùng `$name`. Khi cần biểu thức, dùng `${...}`. Đừng nhầm với ký hiệu `$` trong cú pháp shell hoặc biến môi trường.

Kotlin có raw string ba dấu nháy đôi:

~~~kotlin
val message = """
    First line
    Second line
""".trimIndent()

println(message)
~~~

Stdout:

~~~text
First line
Second line
~~~

Raw string hữu ích khi cấu hình văn bản nhiều dòng, nhưng vẫn hỗ trợ string interpolation. Để tạo ký tự dollar thật trong string thông thường, dùng `\$`. Đừng tùy tiện dùng raw string cho đường dẫn hệ thống khi API Gradle đã có `file(...)` và `layout.projectDirectory`.

## 4. Gọi hàm, named arguments và generic type

### 4.1. Hàm và đối số

Kotlin gọi hàm bằng ngoặc đơn:

~~~kotlin
println("Hello")
val files = files("README.md", "LICENSE")
val projectPath = project(":library")
~~~

Trong `build.gradle.kts`, `files(...)` và `project(...)` là các API Gradle có sẵn trong ngữ cảnh project script; chúng không phải hàm Kotlin độc lập dùng được ở mọi ứng dụng.

Khi API cung cấp tham số tên, Kotlin có thể dùng **named arguments**:

~~~kotlin
apply(plugin = "java")
~~~

Đây là ví dụ cú pháp hợp lệ để áp dụng plugin trong project script, nhưng trong một build script mới nên ưu tiên `plugins { id("java") }` vì Gradle có thể tạo **type-safe accessors** cho các phần model do plugin đóng góp.

### 4.2. Hàm tự định nghĩa trong build script

~~~kotlin
fun artifactName(module: String, version: String): String {
    return "$module-$version.jar"
}

println(artifactName("app", "1.0"))
~~~

Stdout:

~~~text
app-1.0.jar
~~~

`fun` khai báo hàm; `module: String` chỉ ra kiểu tham số và `: String` sau dấu `)` là kiểu trả về. Có thể dùng dạng expression body ngắn hơn:

~~~kotlin
fun artifactName(module: String, version: String) =
    "$module-$version.jar"
~~~

Trong build script nhỏ, hàm helper có thể giúp tránh lặp. Với build logic lớn, hãy chuyển thành plugin/convention plugin được quản lý riêng; đừng khiến root `build.gradle.kts` trở thành một thư viện utility dài, khó kiểm thử.

### 4.3. Generic type trong API Gradle

Kotlin sử dụng `<T>` biểu diễn kiểu tổng quát:

~~~kotlin
val modules: List<String> = listOf("app", "library")
val count: Int = modules.size
~~~

Khi thao tác task, bạn sẽ gặp:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

`JavaCompile` là một loại task Gradle. `withType<JavaCompile>()` lọc những task đúng loại; `configureEach` cấu hình lười những task tương ứng khi chúng cần được hiện thực hóa. Tệp build script cần biết kiểu `JavaCompile` (có thể import tường minh `org.gradle.api.tasks.compile.JavaCompile`); và project cần áp dụng plugin tạo task biên dịch nếu muốn có task thực tế để cấu hình.

Tương tự, `tasks.named<Test>("test") { ... }` yêu cầu một task tên `test` có kiểu `Test`. Một task chưa tồn tại thì `named` không tự tạo nó; cần plugin hoặc bước đăng ký task trước.

## 5. Lambda, trailing lambda và receiver: chìa khóa đọc Gradle DSL

Phần lớn các khối Kotlin DSL là **lời gọi hàm có lambda**. Ví dụ:

~~~kotlin
repositories {
    mavenCentral()
}
~~~

Nó là cách viết ngắn gọn của việc truyền lambda cho một API cấu hình repository. Lambda được đặt sau lời gọi hàm khi là tham số cuối (*trailing lambda*). Trong lambda, receiver là đối tượng mà Gradle muốn bạn cấu hình; vì vậy có thể viết `mavenCentral()` hoặc `group = "learning"` mà không luôn phải ghi rõ tên receiver.

Ví dụ:

~~~kotlin
tasks.register("greet") {
    group = "learning"
    description = "In thông điệp"

    doLast {
        println("Hello from task")
    }
}
~~~

Tách ý nghĩa:

1. `tasks.register("greet")` đăng ký task và nhận lambda cấu hình.
2. Trong lambda cấu hình, `group` và `description` thuộc task đang được cấu hình.
3. `doLast { ... }` thêm **task action**.
4. Dòng `println("Hello from task")` trong `doLast` chỉ chạy khi task thật sự được thực thi.

### 5.1. Lambda có tham số rõ ràng

Với list Kotlin thường dùng:

~~~kotlin
val modules = listOf("api", "web")
modules.forEach { module ->
    println("Module: $module")
}
~~~

Stdout:

~~~text
Module: api
Module: web
~~~

`module ->` khai báo tham số lambda. Với một tham số, Kotlin có biến ngầm `it`:

~~~kotlin
listOf("api", "web").forEach {
    println(it)
}
~~~

**Khác biệt cần nhớ:** `forEach { module -> ... }` có *tham số lambda*. Nhiều block Gradle như `tasks.register { ... }` là *lambda có receiver*, cho phép truy cập trực tiếp thuộc tính của đối tượng đang cấu hình. Không thể tùy tiện thay thế mọi block bằng `it` như thể chúng cùng loại.

### 5.2. Ngữ cảnh lồng nhau

~~~kotlin
tasks.register("sample") {
    group = "learning"

    doLast {
        println("Task action executed")
    }
}
~~~

Trong block ngoài, `group` là thuộc tính của task. Trong block `doLast`, hành động diễn ra ở execution. Trong `java { toolchain { ... } }`, receiver ở mỗi cấp khác nhau: Java extension rồi Java toolchain spec.

Khi gặp lỗi `Unresolved reference`, hãy xem mình đang nằm trong receiver nào và plugin có cung cấp API đó không. Đây thường là vấn đề **ngữ cảnh DSL**, không phải lỗi “Kotlin không hỗ trợ Gradle”.

## 6. Mẫu Kotlin DSL cần thuộc cho năm loại cấu hình chính

### 6.1. `plugins { }`

~~~kotlin
plugins {
    id("java")
    id("application")
}
~~~

`id("java")` áp dụng Java plugin, `id("application")` áp dụng Application plugin, trong đó Application plugin đã áp dụng các khả năng Java cần thiết. Viết cả hai trong ví dụ này vẫn hợp lệ nhưng thông thường chỉ `id("application")` là đủ.

Với plugin bên ngoài, cú pháp thường là:

~~~kotlin
plugins {
    id("some.external.plugin") version "1.2.3"
}
~~~

Đây là **minh họa ngữ pháp plugin DSL**: plugin ID `some.external.plugin` không được xác nhận là plugin tồn tại. Trong dự án thật, thay bằng ID/version có thực và cấu hình plugin repository thích hợp. Không đưa ví dụ giả này vào build chạy.

Không đặt các dòng mã tùy ý trước block `plugins` của build script. Block này có quy tắc cú pháp và thứ tự riêng để Gradle xử lý plugin resolution và tạo accessors.

### 6.2. `repositories { }`

~~~kotlin
repositories {
    mavenCentral()
}
~~~

Đây là nơi khai báo repository dùng để phân giải **dependencies của project**. Cấu hình repository tìm **plugin** có thể đặt tại `pluginManagement { repositories { ... } }` trong `settings.gradle.kts`; hai phạm vi khác nhau.

Ví dụ settings:

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = "sample"
~~~

Trong project không dùng plugin bên ngoài, bạn có thể không cần `pluginManagement` tự viết. Chỉ thêm repository thực sự cần, theo chính sách nguồn tin cậy của dự án.

### 6.3. `dependencies { }`

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
}
~~~

Đây là cấu hình dependencies **khi đã áp dụng Java plugin hoặc plugin tạo hai configuration tương ứng**. Tọa độ dạng `group:artifact:version` là chuỗi Kotlin được truyền cho hàm Gradle. Không có dấu nháy đơn và không bỏ cặp ngoặc.

Dự án thực tế cần `repositories { mavenCentral() }` (hoặc repository phù hợp) để tải dependency bên ngoài. `testImplementation` thêm thư viện vào classpath kiểm thử; chỉ khai báo JUnit Jupiter chưa đảm bảo task test được cấu hình chạy JUnit Platform. Phần 10 trình bày ví dụ cấu hình test đầy đủ hơn.

**Project dependency** trong multi-project build:

~~~kotlin
dependencies {
    implementation(project(":library"))
}
~~~

`project(":library")` là lời gọi Gradle giải quyết project path; dấu `:` không phải filesystem separator. Phải có `include(":library")` trong settings của build đó.

### 6.4. `java { toolchain { } }`

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

`languageVersion` là một `Property<JavaLanguageVersion>`, vì vậy gọi `set(...)` với giá trị có kiểu thích hợp. Nó khác `val javaVersion = 17`: một bên cấu hình thuộc tính có cơ chế quản lý giá trị của Gradle, bên kia chỉ là biến Kotlin.

Toolchain là yêu cầu JDK phù hợp để thực hiện tác vụ Java. Nếu máy chưa có JDK 17 và chưa cấu hình cơ chế tự cung cấp, Gradle có thể thông báo không tìm thấy toolchain. **Java toolchain không thay thế sự cần thiết phải dùng bản JDK đủ mới để khởi chạy chính Gradle.**

### 6.5. `tasks { }` và task action

~~~kotlin
tasks.register("hello") {
    group = "learning"
    description = "Minh họa Kotlin DSL"

    doLast {
        println("Hello, Gradle Kotlin DSL!")
    }
}
~~~

Chạy `gradle --quiet hello` từ root sẽ in:

~~~text
Hello, Gradle Kotlin DSL!
~~~

`group` giúp phân loại task khi liệt kê bằng `gradle tasks`; `description` giúp người dùng hiểu mục tiêu. Task mới được đăng ký trong configuration, còn `doLast` được thực thi khi task cần chạy.

## 7. Phân biệt gán thuộc tính Kotlin với Gradle Property/Provider

Đây là ranh giới quan trọng nhất sau việc hiểu lambda.

### 7.1. Gán trực tiếp một thuộc tính thông thường

~~~kotlin
group = "com.example"
version = "1.0.0"

tasks.register("sample") {
    group = "learning"
    description = "Sample task"
}
~~~

Những thuộc tính kiểu `String` thông thường này có thể gán với `=` trong ngữ cảnh DSL tương ứng.

### 7.2. `Property<T>` và `set(...)`

Nhiều cấu hình hiện đại của Gradle dùng `Property<T>`, `ListProperty<T>`, `DirectoryProperty`, `RegularFileProperty`, v.v.:

~~~kotlin
application {
    mainClass.set("example.Main")
}

tasks.named<Jar>("jar") {
    archiveFileName.set("example.jar")
    destinationDirectory.set(layout.buildDirectory.dir("packages"))
}
~~~

Ví dụ cần có plugin `application`/`java` để hai extension và task liên quan tồn tại. Những lời gọi `set(...)` cấu hình đối tượng Gradle được quản lý, có thể nhận giá trị hoặc một `Provider` phù hợp.

Một số phiên bản Gradle/Kotlin DSL hỗ trợ cú pháp gán lười `property = value` cho Gradle managed properties. Tuy nhiên, **`set(...)` là cách rõ ràng và dễ nhận biết** khi học `Property<T>` và khi đối chiếu API. Không nên suy ra rằng mọi property đều là một `var` Kotlin thông thường.

### 7.3. `Provider<T>`: giữ giá trị có thể tính sau

~~~kotlin
val audience = providers.gradleProperty("audience").orElse("team")

tasks.register("greetAudience") {
    doLast {
        println("Hello, ${audience.get()}!")
    }
}
~~~

Chạy:

~~~bash
gradle --quiet greetAudience
gradle --quiet greetAudience -Paudience=Java
~~~

Lần lượt, stdout task là:

~~~text
Hello, team!
~~~

và:

~~~text
Hello, Java!
~~~

Giải thích:

- `providers.gradleProperty("audience")` tạo provider đọc thuộc tính Gradle có tên `audience`.
- `orElse("team")` cung cấp giá trị mặc định khi property không có.
- `get()` đọc giá trị provider khi action cần nó.
- `-Paudience=Java` truyền project property từ CLI. Nó **không đồng nghĩa** với biến môi trường hệ điều hành.

Một `Provider<T>` thường để Gradle theo dõi phụ thuộc giữa các giá trị và hỗ trợ cấu hình lười. Tránh gọi `get()` sớm ngay ở top-level chỉ để in debug, vì việc này có thể ép đánh giá giá trị trước thời điểm cần thiết.

### 7.4. Layout API và xử lý file

~~~kotlin
val reportFile = layout.buildDirectory.file("reports/summary.txt")

tasks.register("writeSummary") {
    outputs.file(reportFile)

    doLast {
        val destination = reportFile.get().asFile
        destination.parentFile.mkdirs()
        destination.writeText("Build summary", Charsets.UTF_8)
    }
}
~~~

Đoạn này là một **task Gradle** có thể thêm vào `build.gradle.kts`. Chạy:

~~~bash
gradle writeSummary
~~~

Nó tạo file `build/reports/summary.txt` chứa chính xác:

~~~text
Build summary
~~~

Khác biệt quan trọng: `layout.buildDirectory.file(...)` tạo provider đường dẫn, `outputs.file(...)` khai báo output cho Gradle, còn thao tác ghi file được đặt trong `doLast`. Vì nội dung cố định và output được khai báo, task có thể được đánh dấu up-to-date ở lần chạy sau nếu input/output không thay đổi. Với task thực tế, cần khai báo input thay đổi của mình thay vì chỉ trông vào output.

**Không nên** đưa `file("build/reports/summary.txt").writeText(...)` ngay vào phần top-level của build script. Khi đó file bị viết trong configuration, ngay cả khi bạn chỉ muốn xem danh sách task.

## 8. Đăng ký, cấu hình và nối quan hệ task bằng Kotlin

### 8.1. `register` để tạo task; `named` để cấu hình task đã có

~~~kotlin
val prepare = tasks.register("prepare") {
    doLast {
        println("Prepare")
    }
}

tasks.register("deliver") {
    dependsOn(prepare)

    doLast {
        println("Deliver")
    }
}
~~~

Chạy `gradle --quiet deliver`:

~~~text
Prepare
Deliver
~~~

`prepare` là một `TaskProvider<Task>` do `tasks.register` trả về. `dependsOn(prepare)` dùng provider trực tiếp; không cần `prepare.get()`. `get()` có thể khiến task được hiện thực hóa sớm khi không cần thiết.

Để cấu hình task hiện có:

~~~kotlin
tasks.named("deliver") {
    description = "Chạy prepare rồi deliver"
}
~~~

`named(...)` tìm task đã được đăng ký; nó không phải lệnh tạo task mới. Với task có kiểu rõ ràng:

~~~kotlin
tasks.named<Test>("test") {
    useJUnitPlatform()
}
~~~

Đây là một **đoạn bổ sung**, chỉ chạy khi plugin đã tạo task `test`. Nó đòi hỏi kiểu `Test` từ `org.gradle.api.tasks.testing.Test`, được Gradle cung cấp qua API/import tương ứng.

### 8.2. Tạo task theo kiểu có sẵn

~~~kotlin
tasks.register<Copy>("copyGuides") {
    from(layout.projectDirectory.dir("guides"))
    into(layout.buildDirectory.dir("collected-guides"))
}
~~~

`Copy` là task type Gradle. Tác vụ sẽ copy các file từ thư mục `guides` ở project vào thư mục trong `build`. Đây là đoạn minh họa; nếu `guides` chưa tồn tại hoặc không có file, task có thể không có nguồn để copy. Trong trường hợp tập tin đầu vào thực sự là một output của task khác, nên truyền Provider được nối đúng quan hệ thay vì cố đoán thứ tự bằng lệnh.

### 8.3. Cấu hình tất cả task của một kiểu, theo cách lười

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

Cấu hình này áp dụng cho những task biên dịch Java đang tồn tại hoặc được đăng ký sau đó, khi chúng được cấu hình. Cần import `JavaCompile` nếu IDE/Gradle không cung cấp qua implicit imports:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
~~~

Cú pháp `<JavaCompile>` là generic Kotlin. Nó chọn **kiểu task**, không phải biểu thức XML hoặc ký hiệu HTML.

### 8.4. `dependsOn` khác `mustRunAfter`

~~~kotlin
val checkInputs = tasks.register("checkInputs") {
    doLast { println("Check inputs") }
}

tasks.register("releaseBundle") {
    dependsOn(checkInputs)
    doLast { println("Release bundle") }
}
~~~

`dependsOn` yêu cầu task phụ thuộc. Nếu chỉ viết `mustRunAfter(checkInputs)`, Gradle bảo đảm thứ tự **nếu cả hai task được chọn**, nhưng không tự kéo `checkInputs` vào graph.

Nếu task tạo file cho task khác, thường cần quan hệ dependency hoặc liên kết input/output có thể suy ra dependency; dùng `mustRunAfter` chỉ để chữa một build phụ thuộc file mà chưa khai báo đúng là dễ gây lỗi.

## 9. Ví dụ Java 17 hoàn chỉnh dùng .gradle.kts

Phần này là dự án **chạy được**; nó minh họa cách Kotlin DSL cấu hình một ứng dụng Java đơn giản. Mã ứng dụng là Java, còn file build là Kotlin DSL.

### 9.1. Cấu trúc thư mục

~~~text
kotlin-dsl-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
~~~

Yêu cầu:

- Một bản Gradle tương thích và JDK 17 (có thể dùng Gradle Wrapper đã được chuẩn bị).
- Không cần tải dependency ngoài để chạy mã Java cơ bản vì chỉ dùng Java Standard Library và plugin Gradle có sẵn.
- Cấu trúc thư mục trùng chính xác với package/class trong các tệp bên dưới.

### 9.2. settings.gradle.kts

~~~kotlin
rootProject.name = "kotlin-dsl-lab"
~~~

Đây là một Kotlin script với receiver là `Settings` của Gradle, không phải cấu hình một Java class.

### 9.3. build.gradle.kts

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id("application")
}

group = "demo"
version = "1.0.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.Main")
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}

tasks.register("helloDsl") {
    group = "learning"
    description = "Kiểm tra task Kotlin DSL tự tạo"

    doLast {
        println("Hello from Kotlin DSL task")
    }
}
~~~

Giải thích từng khối:

1. `import ...JavaCompile` đưa kiểu task vào phạm vi sử dụng.
2. `plugins { id("application") }` áp dụng plugin tạo các task như `run` và hỗ trợ Java.
3. `group` và `version` xác định metadata của project/artifact; chúng không phải tọa độ Maven dependency bên ngoài.
4. `repositories { mavenCentral() }` khai báo nơi lấy dependency khi dự án có thư viện ngoài; ví dụ Java thuần này không cần dependency mạng.
5. `java { toolchain { ... } }` yêu cầu JDK 17 cho tác vụ Java.
6. `application { mainClass.set("demo.Main") }` xác định entrypoint. Đây là tên class **đầy đủ**, gồm package.
7. `tasks.withType<JavaCompile>().configureEach` đặt encoding cho các task biên dịch Java.
8. `tasks.register("helloDsl")` khai báo một task có action in dòng text.

### 9.4. Mã Java

Tệp `src/main/java/demo/Main.java`:

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Hello from Java 17 application");
    }
}
~~~

Tên package `demo` và class `Main` ghép thành `demo.Main`, đúng với cấu hình `mainClass`. Đây là file Java độc lập hợp lệ theo Java 17.

### 9.5. Chạy và kiểm tra stdout

Đứng trong thư mục `kotlin-dsl-lab`:

~~~bash
gradle --quiet helloDsl
gradle --quiet run
gradle --console=plain build
~~~

Output của **lệnh đầu**:

~~~text
Hello from Kotlin DSL task
~~~

Output của **lệnh thứ hai**:

~~~text
Hello from Java 17 application
~~~

Lệnh `gradle build` thực hiện các task build tương ứng và tạo output trong `build/`; log cụ thể phụ thuộc phiên bản Gradle, trạng thái cache và môi trường, nên không có một stdout cố định.

Nếu chưa có Gradle Wrapper, sau khi đã cài Gradle tương thích có thể chạy `gradle wrapper` tại root để tạo file wrapper và commit chúng cùng project. Sau đó dùng:

~~~bash
# macOS / Linux
./gradlew --quiet helloDsl
./gradlew --quiet run
./gradlew build

# Windows (PowerShell hoặc Command Prompt)
gradlew.bat --quiet helloDsl
gradlew.bat --quiet run
gradlew.bat build
~~~

Wrapper giúp mọi người chạy cùng bản Gradle theo cấu hình dự án. Nếu JDK 17 chưa được cài hoặc cơ chế provision toolchain chưa có, `run`/`build` có thể lỗi khi Gradle tìm compiler; đó là vấn đề toolchain, không phải do Kotlin DSL thiếu Java compiler.

### 9.6. Nếu không muốn dùng Gradle, có thể xác nhận riêng file Java

Từ thư mục `kotlin-dsl-lab`, với JDK 17:

~~~bash
javac -d out src/main/java/demo/Main.java
java -cp out demo.Main
~~~

Stdout chính xác:

~~~text
Hello from Java 17 application
~~~

Hai lệnh này kiểm tra tính hợp lệ của mã Java; chúng **không kiểm tra cú pháp build.gradle.kts**. Để xác minh Kotlin DSL, vẫn phải gọi một tác vụ Gradle như `gradle help`, `gradle helloDsl` hoặc `gradle build`.

## 10. Kotlin DSL khi khai báo kiểm thử Java

Khi dự án cần JUnit 5, hãy cấu hình dependency và test task. Đoạn sau **bổ sung** vào `build.gradle.kts` của project đã áp dụng plugin `application` hoặc `java`:

~~~kotlin
dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
~~~

Giải thích:

- `testImplementation(platform(...))` dùng JUnit BOM để quản lý phiên bản các thành phần JUnit.
- `testImplementation("org.junit.jupiter:junit-jupiter")` cung cấp API/engine JUnit Jupiter theo BOM.
- `testRuntimeOnly("org.junit.platform:junit-platform-launcher")` bổ sung platform launcher vào runtime test (hữu ích với Gradle gần đây).
- `useJUnitPlatform()` cấu hình task `test` chạy bằng JUnit Platform.

Đoạn này cần `repositories { mavenCentral() }` hoặc repository tương đương và kết nối đến dependency artifact. Nó **không tự tạo test case**; để thực sự có bài test, bạn cần mã ở `src/test/java`. Ví dụ file `src/test/java/demo/MainTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

final class MainTest {
    @Test
    void additionWorks() {
        assertEquals(4, 2 + 2);
    }
}
~~~

Chạy:

~~~bash
gradle --console=plain test
~~~

Khi test pass, Gradle kết thúc thành công và có thể tạo report trong `build/reports/tests/test/`. Không đưa ra stdout test cố định vì JUnit/Gradle thường không tự in dòng text cho từng assertion và log khác nhau tùy phiên bản.

**Lưu ý cú pháp:** Kotlin DSL không thay đổi cách viết `@Test`, `assertEquals` hoặc package của Java. Nó chỉ cấu hình cách Gradle biên dịch và chạy tập test đó.

## 11. Kotlin DSL trong multi-project build

Giả sử cấu trúc:

~~~text
workshop/
├── settings.gradle.kts
├── build.gradle.kts
├── app/
│   └── build.gradle.kts
└── library/
    └── build.gradle.kts
~~~

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "workshop"
include(":app", ":library")
~~~

`library/build.gradle.kts`:

~~~kotlin
plugins {
    id("java-library")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

`app/build.gradle.kts`:

~~~kotlin
plugins {
    id("application")
}

dependencies {
    implementation(project(":library"))
}

application {
    mainClass.set("example.app.Main")
}
~~~

Các đoạn trên minh họa đúng cú pháp Kotlin DSL cho cấu trúc và project dependency; **chúng chưa phải chương trình chạy hoàn chỉnh**, vì ví dụ chưa cung cấp các file Java tương ứng với `example.app.Main` và class thư viện.

Dòng `include(":app", ":library")` nằm trong **settings script** để đăng ký project. Dòng `implementation(project(":library"))` nằm trong **project build script** của `:app` để khai báo sử dụng output của thư viện. Việc có hai thư mục cạnh nhau không tự tạo dependency giữa chúng.

Chạy từ root:

~~~bash
gradle projects
gradle :app:tasks
~~~

Đường dẫn `:app:tasks` là task path, còn `:app` là project path. Dấu hai chấm không thuộc tên package Java hay đường dẫn thư mục hệ điều hành.

## 12. Type-safe accessors: vì sao IDE gợi ý được `implementation`?

Kotlin DSL dựa trên kiểu tĩnh. Gradle có cơ chế sinh **type-safe model accessors** cho những phần cấu hình được plugin cung cấp mà Gradle có thể biết ở thời điểm thích hợp.

Ví dụ:

~~~kotlin
plugins {
    id("java")
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
~~~

Nhờ plugin `java` đã được áp dụng trong block `plugins`, Gradle biết configuration `implementation` và cho phép Kotlin DSL gọi như một hàm có kiểu. Tương tự, plugin `application` cung cấp extension `application { ... }`.

**Mốc quan trọng:** Nhiều accessors được xác định ngay sau khi xử lý `plugins { ... }`, trước khi đánh giá thân script. Nếu bạn tạo configuration mới về sau trong thân script, accessor type-safe cho tên mới đó thường **không tự xuất hiện**.

Ví dụ:

~~~kotlin
plugins {
    id("java")
}

val reports by configurations.creating

dependencies {
    add("reports", "org.example:tool:1.0")
}
~~~

Đây là ví dụ cách **truy cập configuration bằng tên string** qua API `add(...)`; tọa độ `org.example:tool:1.0` chỉ để minh họa cú pháp. Không nên viết `reports("org.example:tool:1.0")` rồi mặc định cho rằng accessor sẽ tồn tại khi configuration được tạo sau plugin block.

Một khác biệt nữa: nếu áp dụng plugin muộn bằng:

~~~kotlin
apply(plugin = "java")
~~~

thì các accessor dựa trên plugin như `implementation(...)` có thể **không được sinh** trong cùng script. Với build script thông thường, hãy dùng `plugins { id("java") }`. Khi không có type-safe accessor, dùng API theo tên/kiểu, ví dụ `dependencies.add("implementation", "...")` sau khi plugin thực sự đã tạo configuration.

**Hệ quả thực tế:** Thông báo `Unresolved reference: implementation`, `Unresolved reference: application` hoặc `Unresolved reference: java` thường liên quan đến plugin, phạm vi script, thời điểm tạo accessors hoặc tên API; đừng vội sửa thành cú pháp Groovy.

## 13. Bảng chuyển đổi Groovy DSL sang Kotlin DSL

Bảng này giả định đoạn code nằm trong đúng loại script và plugin đã áp dụng khi cần.

| Ý định | Groovy DSL (`.gradle`) | Kotlin DSL (`.gradle.kts`) |
| --- | --- | --- |
| Áp dụng Java plugin | `id 'java'` | `id("java")` |
| Đặt group | `group = 'demo'` | `group = "demo"` |
| In thông báo | `println 'Hello'` | `println("Hello")` |
| Khai báo dependency | `implementation 'g:a:1.0'` | `implementation("g:a:1.0")` |
| Dependency project | `implementation project(':library')` | `implementation(project(":library"))` |
| Khai báo task | `tasks.register('hello') { ... }` | `tasks.register("hello") { ... }` |
| Config task theo tên | `tasks.named('test') { ... }` | `tasks.named<Test>("test") { ... }` |
| Tìm task theo type | `tasks.withType(JavaCompile).configureEach { ... }` | `tasks.withType<JavaCompile>().configureEach { ... }` |
| Tạo string | `'test'` hoặc `"test"` | `"test"` |
| Đặt mainClass | `mainClass = 'demo.Main'` | `mainClass.set("demo.Main")` |
| Đặt JDK toolchain | `languageVersion = JavaLanguageVersion.of(17)` | `languageVersion.set(JavaLanguageVersion.of(17))` |
| Đặt phụ thuộc task | `dependsOn tasks.named('prepare')` | `dependsOn(tasks.named("prepare"))` |

Không sao chép nguyên văn `id 'java'`, `implementation '...'` hay `tasks.register('x')` sang `.gradle.kts`: Kotlin kiểm tra cú pháp và kiểu ngay khi biên dịch script.

Lưu ý: tên chính xác của một số DSL property và cú pháp gán có thể khác tùy phiên bản Gradle/plugin. Khi dịch mã của plugin ngoài, cần tra tài liệu **Kotlin DSL của chính plugin đó**, thay vì giả định mọi Groovy closure đều có phương thức Kotlin cùng tên.

## 14. Điều kiện `if`, `when` và collection trong build script

Kotlin cho phép viết điều kiện thông thường:

~~~kotlin
val mode = "debug"

if (mode == "release") {
    println("Release mode")
} else {
    println("Debug mode")
}
~~~

Stdout:

~~~text
Debug mode
~~~

Có thể dùng `when`:

~~~kotlin
val flavor = "api"
val description = when (flavor) {
    "api" -> "Backend"
    "web" -> "Frontend"
    else -> "Unknown"
}

println(description)
~~~

Stdout:

~~~text
Backend
~~~

Với collection:

~~~kotlin
val modules = listOf("app", "library")
val flags = mapOf("integration" to true, "benchmark" to false)

println(modules.first())
println(flags["integration"])
~~~

Stdout:

~~~text
app
true
~~~

Các cấu trúc này hữu ích khi build logic thực sự cần quyết định cấu hình. Tuy nhiên, các lệnh `println` nằm ở top-level của `build.gradle.kts` thực thi trong **configuration phase**, kể cả khi bạn chỉ gọi `gradle help`. Không đưa công việc tạo artifact, gọi network hay process tốn thời gian vào những nhánh điều kiện top-level; hãy chuyển công việc sang task action và khai báo inputs/outputs.

Khi điều kiện phụ thuộc property người dùng, ưu tiên `providers.gradleProperty(...)` và mô hình Provider thay vì truy cập thông tin động ngoài kiểm soát để tránh ảnh hưởng configuration cache.

## 15. Sử dụng import và các kiểu API Gradle

Kotlin DSL có nhiều implicit imports từ Gradle, nhưng không phải mọi class trong JDK và Gradle plugin đều được tự động import.

Ví dụ:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test
import org.gradle.jvm.tasks.Jar

plugins {
    id("java")
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}

tasks.named<Jar>("jar") {
    archiveFileName.set("demo.jar")
}
~~~

Các import tường minh giúp đọc ví dụ không phụ thuộc vào việc IDE đã gợi ý hay chưa. Ví dụ áp dụng plugin `java` vì plugin này tạo task `test` và `jar`.

Đối với dự án nhiều plugin, kiểm tra chính xác class của API plugin và compatibility với Gradle đang dùng. Đừng import class thuộc internal Kotlin DSL API để làm việc mà public Gradle API đã hỗ trợ.

## 16. Các lỗi thường gặp trong .gradle.kts và cách sửa

### Lỗi 1: `Too many characters in a character literal`

Sai:

~~~kotlin
val name = 'java'
~~~

Đúng:

~~~kotlin
val name = "java"
~~~

`'a'` chỉ dành cho một ký tự `Char`; `"java"` mới là `String`. Khi migrate từ Groovy, phần lớn string literal cần chuyển sang dấu nháy đôi.

### Lỗi 2: `Unresolved reference: implementation`

Nếu chỉ có:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
~~~

nhưng chưa áp dụng plugin tạo configuration `implementation`, Gradle Kotlin DSL có thể báo không nhận diện lời gọi. Sửa bằng cách thêm Java plugin trong `plugins`:

~~~kotlin
plugins {
    id("java")
}
~~~

Hoặc dùng API `dependencies.add("implementation", "...")` **sau khi configuration tồn tại**. Cũng nên kiểm tra bạn có đang viết trong `settings.gradle.kts` (khác receiver với `build.gradle.kts`) hay không.

### Lỗi 3: `Unresolved reference: java` hoặc `application`

Các block extension này do plugin cung cấp. `java { ... }` cần Java plugin hoặc plugin kéo theo Java plugin; `application { ... }` cần Application plugin. Mẫu đúng:

~~~kotlin
plugins {
    id("application")
}

application {
    mainClass.set("demo.Main")
}
~~~

Nếu plugin được áp dụng qua `apply(plugin = "...")` trong thân script, type-safe accessors có thể không được sinh; hãy cân nhắc block `plugins` hoặc API cấu hình extension theo kiểu cụ thể.

### Lỗi 4: `Type mismatch` khi đặt managed property

Sai khi truyền sai kiểu:

~~~kotlin
java {
    toolchain {
        languageVersion.set(17)
    }
}
~~~

Đúng:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

`JavaToolchainSpec.languageVersion` mong đợi `JavaLanguageVersion` (hoặc Provider đúng kiểu), không phải `Int` đơn thuần. Kotlin DSL giúp phát hiện kiểu không hợp lệ ngay khi đánh giá/biên dịch script.

### Lỗi 5: Tham chiếu task trước khi nó tồn tại

~~~kotlin
tasks.named("unknownTask") {
    description = "..."
}
~~~

`named` không tự sinh task. Hãy kiểm tra plugin nào tạo task, chạy `gradle tasks --all` và đối chiếu tên task. Nếu muốn tạo mới, dùng `tasks.register("unknownTask") { ... }`.

### Lỗi 6: Không phân biệt cấu hình và thực thi

~~~kotlin
println("This runs during script configuration")

tasks.register("work") {
    doLast {
        println("This runs when task executes")
    }
}
~~~

Chạy `gradle help` có thể in dòng đầu vì script được cấu hình, nhưng không in dòng trong `doLast` của task `work`. Không kết luận rằng task đã chạy chỉ vì một log trong script xuất hiện.

### Lỗi 7: Truy cập `Provider.get()` quá sớm

Khi bạn gọi `get()` ngay để tìm giá trị ở thời điểm cấu hình, có thể vô tình ép việc tính toán hoặc phá thiết kế cấu hình lười. Nếu một task cần file từ task khác, hãy truyền provider/đường dẫn cấu hình thay vì tìm file tồn tại bằng cách đọc thủ công ngay lúc build script chạy.

### Lỗi 8: Đặt `plugins { }` sau mã top-level tùy ý

Block plugin có các quy tắc parsing và thứ tự. Thường đặt import tường minh (nếu cần) ở đầu, tiếp theo là `plugins`, rồi mới là `group`, `repositories`, `dependencies`, `tasks`.

### Lỗi 9: Nhầm phiên bản Kotlin DSL với Kotlin JVM plugin

Kotlin DSL của Gradle sử dụng cơ chế Kotlin được Gradle tích hợp để biên dịch script. Cấu hình một dự án dùng Kotlin source lại đòi hỏi Kotlin JVM/Multiplatform/Android plugin với phiên bản phù hợp. Hai việc này có liên quan nhưng không đồng nhất. Việc build script có đuôi `.gradle.kts` không có nghĩa project đã dùng Kotlin plugin.

### Lỗi 10: Chép cú pháp plugin Gradle Groovy nguyên xi

Plugin bên ngoài có thể hướng dẫn:

~~~groovy
somePlugin {
    option = 'enabled'
}
~~~

Không đảm bảo thay một cách máy móc thành cùng tên block và `option = "enabled"` luôn hợp lệ trong Kotlin DSL. Cần kiểm tra API extension, kiểu property, phương thức `set`, plugin ID và khả năng sinh accessor. Kotlin DSL dùng kiểm tra kiểu tĩnh nên những chỗ Groovy chấp nhận nhờ dynamic dispatch có thể cần API tường minh.

## 17. Cách tự xác minh file .gradle.kts

Khi đang chỉnh script, làm theo thứ tự thực dụng:

1. **Đúng tên file:** `build.gradle.kts` cho project; `settings.gradle.kts` cho settings.
2. **Có plugin cần thiết:** `plugins { id("java") }` hoặc `id("application")` trước khi dùng `implementation`, `java`, `application`.
3. **Đúng cú pháp Kotlin:** chuỗi dùng `"..."`; lời gọi hàm có `(...)`; managed property dùng `set(...)` khi phù hợp.
4. **Đúng imports/types:** `JavaCompile`, `Test`, `Jar` cần kiểu Gradle tương ứng.
5. **Chạy lệnh nhẹ để kiểm tra script:** `gradle help` hoặc `gradle tasks`; đây là bước phát hiện lỗi cấu hình, chưa chứng minh Java code compile.
6. **Chạy task thật:** `gradle run`, `gradle test` hoặc `gradle build` để kiểm tra end-to-end đúng nội dung.

Lệnh chẩn đoán:

~~~bash
gradle --console=plain help
gradle --console=plain tasks --all
gradle --console=plain build --stacktrace
gradle --console=plain build --info
~~~

Trong repository dùng Wrapper, thay `gradle` bằng `./gradlew` hoặc `gradlew.bat`. Với lỗi syntax Kotlin, lỗi thường hiển thị vị trí dòng/cột trong file `.gradle.kts`; với lỗi plugin/dependency, xem stacktrace và cấu hình repository. Với lỗi Java source, nhìn task `compileJava` và thông báo `javac`.

Để nhận code completion và type-safe navigation, nên mở dự án bằng IDE có hỗ trợ import Gradle model, chẳng hạn IntelliJ IDEA hoặc Android Studio. Nếu IDE báo lỗi mà CLI vẫn build thành công, đồng bộ lại Gradle project và kiểm tra Gradle JVM/Wrapper đang chọn.

## 18. Bài tập tự kiểm tra có đáp án

### Bài 1. Chuyển cú pháp Groovy sang Kotlin DSL

Cho Groovy:

~~~groovy
plugins {
    id 'java'
}
repositories {
    mavenCentral()
}
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}
~~~

Hãy chuyển sang Kotlin DSL.

**Đáp án:**

~~~kotlin
plugins {
    id("java")
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
}
~~~

Để test được thực thi trên JUnit Platform, còn cần cấu hình task `test` và runtime engine/launcher phù hợp như mục 10.

### Bài 2. Phát hiện lỗi kiểu

Đoạn sau sai ở đâu?

~~~kotlin
java {
    toolchain {
        languageVersion.set("17")
    }
}
~~~

**Đáp án:** Giá trị `"17"` là `String`, không phải `JavaLanguageVersion`. Dùng `languageVersion.set(JavaLanguageVersion.of(17))` trong một project có Java plugin.

### Bài 3. Xác định thời điểm chạy

~~~kotlin
println("A")

tasks.register("demo") {
    println("B")
    doLast {
        println("C")
    }
}
~~~

Chạy `gradle --quiet demo`, thứ tự các dòng do ví dụ in là gì?

**Đáp án:** `A`, `B`, `C`. `A` được in khi đánh giá project script; `B` là logic cấu hình task khi task được hiện thực hóa; `C` là task action khi được thực thi. Khi chạy một task không liên quan, `B` có thể không được in nhờ task configuration avoidance và `C` không chạy.

### Bài 4. Tạo dependency task

Bạn có `val check = tasks.register("checkData") { ... }`. Muốn task `publishData` luôn cần `checkData` trước, câu lệnh đúng là gì?

**Đáp án:**

~~~kotlin
tasks.register("publishData") {
    dependsOn(check)
    doLast {
        println("Publish")
    }
}
~~~

`check` ở đây là `TaskProvider`, không cần `get()`.

### Bài 5. Vì sao `project(":library")` không chạy?

Script `app/build.gradle.kts` có:

~~~kotlin
dependencies {
    implementation(project(":library"))
}
~~~

Nhưng `settings.gradle.kts` chỉ có `include(":app")`. Điều gì cần sửa?

**Đáp án:** Thêm `include(":library")` vào settings và bảo đảm thư mục build của thư viện tồn tại, được cấu hình hợp lệ. `project(":library")` tham chiếu project path, không phải tên thư mục tùy ý có thể tự được tìm thấy.

### Bài 6. Điểm khác nhau giữa `val` và `Property<T>`

Xét:

~~~kotlin
val jdk = 17
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(jdk))
    }
}
~~~

Dòng nào khai báo biến Kotlin, dòng nào cấu hình Gradle?

**Đáp án:** `val jdk = 17` khai báo giá trị Kotlin kiểu Int, còn `languageVersion.set(...)` đặt giá trị lên managed property của Java toolchain trong Gradle. Cả hai chạy trong phần cấu hình build nhưng phục vụ vai trò khác nhau.

## 19. Tờ ghi nhớ nhanh

| Thấy trong script | Hãy hiểu |
| --- | --- |
| `plugins { id("java") }` | Áp dụng Gradle plugin |
| `val name = "app"` | Khai báo biến Kotlin chỉ gán một lần |
| `name: String` | Khai báo kiểu tường minh |
| `"Hello, $name"` | Nội suy chuỗi Kotlin |
| `println("...")` | Gọi hàm với dấu ngoặc |
| `repositories { mavenCentral() }` | Lambda cấu hình repository |
| `dependencies { implementation("g:a:v") }` | Hàm thêm module dependency đã có configuration |
| `implementation(project(":library"))` | Thêm dependency tới subproject cùng build |
| `languageVersion.set(JavaLanguageVersion.of(17))` | Đặt managed property có kiểu phù hợp |
| `providers.gradleProperty("x")` | Provider đọc Gradle project property |
| `layout.buildDirectory.file("x")` | Provider trỏ đến output trong build directory |
| `tasks.register("x") { }` | Đăng ký task mới, trả về TaskProvider |
| `tasks.named("x") { }` | Cấu hình task đã tồn tại |
| `tasks.withType<Test>().configureEach { }` | Cấu hình lazy cho task cùng type |
| `dependsOn(taskProvider)` | Thêm quan hệ phụ thuộc task |
| `doLast { ... }` | Thêm action chạy trong execution |

Nhớ ba nguyên tắc xuyên suốt: **Kotlin DSL là Kotlin thực sự được Gradle chạy trong ngữ cảnh của build; hầu hết block DSL là lời gọi API với lambda; và code cấu hình phải được phân biệt với action tạo output.** Khi nắm ba điểm đó, việc đọc `.gradle.kts` sẽ dễ hơn nhiều và các lỗi gõ sai tên, sai kiểu hoặc đặt sai ngữ cảnh sẽ có cách xử lý rõ ràng.

## Tài liệu chính thức

- [Gradle Kotlin DSL Primer](https://docs.gradle.org/current/userguide/kotlin_dsl.html) — cú pháp, type-safe accessors và Provider API.
- [Gradle Kotlin DSL Reference](https://docs.gradle.org/current/kotlin-dsl/index.html) — API theo kiểu khi viết script.
- [Gradle: Writing Build Scripts](https://docs.gradle.org/current/userguide/writing_build_scripts.html) — cấu trúc, script và cấu hình dự án.
- [Gradle: Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html) — `register`, `named`, `configureEach`.
- [Gradle: Working With Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html) — khai báo các loại dependency.
