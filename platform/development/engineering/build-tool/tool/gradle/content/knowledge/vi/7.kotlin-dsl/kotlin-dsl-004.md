# Truy cập task, extension và container bằng API có kiểu trong Gradle Kotlin DSL

## 1. Vì sao việc truy cập có kiểu quan trọng?

Khi làm việc với Gradle, ta thường muốn trả lời những câu hỏi rất cụ thể: “Task biên dịch Java nằm ở đâu?”, “Làm sao thay đổi Java toolchain?”, “Source set `main` đang lấy mã từ thư mục nào?”, “Đăng ký một task `Copy` mới mà vẫn tận dụng được các thuộc tính của `Copy` như thế nào?”.

Trong Gradle Kotlin DSL (`build.gradle.kts`), các thành phần này thuộc một **mô hình đối tượng có kiểu**:

- **Task:** công việc Gradle có thể xử lý, ví dụ `compileJava`, `test`, `jar`, `Copy` tùy chỉnh.
- **Extension:** đối tượng cấu hình do plugin hoặc build script thêm vào project, ví dụ `java` do Java plugin cung cấp.
- **Container:** tập hợp đối tượng có tên như `tasks`, `sourceSets` và `configurations`, có API để đăng ký, tìm và cấu hình phần tử.
- **Provider/Property:** cách biểu diễn tham chiếu đến đối tượng hoặc giá trị có thể được cung cấp về sau, giúp Gradle trì hoãn công việc cấu hình và liên kết dữ liệu giữa các task.

Thay vì thao tác với một bản đồ thuộc tính động hoặc chuyển kiểu thủ công, ta có thể dùng các API rõ ràng về kiểu như:

```kotlin
tasks.named<JavaCompile>("compileJava") {
    options.encoding = "UTF-8"
}

extensions.configure<JavaPluginExtension> {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

sourceSets.named("main") {
    java.srcDir("src/extra/java")
}
```

Đây là **ba đoạn minh họa cho một project đã áp dụng plugin `java`**. Các kiểu `JavaCompile` và `JavaPluginExtension` cần được import trong ngữ cảnh không có import ngầm tương ứng; mục 8 đưa ra một file `build.gradle.kts` độc lập đầy đủ.

API có kiểu giúp IDE gợi ý phương thức/thuộc tính và phát hiện nhiều lỗi cú pháp hoặc sai kiểu ở thời điểm biên dịch build script. Tuy nhiên, **chuỗi tên như `"compileJava"` vẫn là dữ liệu**: nếu viết sai tên, Gradle thường chỉ phát hiện khi tra cứu/configuration. “Có kiểu” không đồng nghĩa mọi tên hoặc mọi điều kiện thực thi đều được kiểm tra tĩnh.

## 2. Từ `plugins` đến mô hình có kiểu

Bắt đầu với file `build.gradle.kts`:

```kotlin
plugins {
    java
}
```

Khi Java plugin được áp dụng, project có thêm:

| Thành phần | Bản chất | Ví dụ truy cập Kotlin DSL |
| --- | --- | --- |
| `java` | Extension cấu hình Java toolchain, source JAR... | `java { ... }` |
| `sourceSets` | Container các source set như `main` và `test` | `sourceSets.named("main")` |
| `tasks` | Task container của project | `tasks.named<JavaCompile>("compileJava")` |
| `configurations` | Container cấu hình dependency | `configurations.named("testImplementation")` |
| `dependencies` | Bộ xử lý khai báo dependency | `dependencies { testImplementation("...") }` |

Không phải mọi đối tượng kể trên đều do Java plugin tạo từ đầu: chẳng hạn `tasks` và `configurations` là thành phần của mô hình Project, còn plugin bổ sung task/cấu hình/extension cụ thể. Java plugin làm cho những tên liên quan đến Java trở nên có ý nghĩa trong project.

Gradle Kotlin DSL cung cấp hai cách truy cập có kiểu cần phân biệt:

1. **Accessor sinh tự động (type-safe model accessor):** Ví dụ `java { ... }` hoặc `sourceSets { ... }`. Gradle sinh các hàm/thuộc tính dựa trên mô hình đã biết sau khi xử lý khối `plugins`.
2. **API có kiểu tường minh:** Ví dụ `extensions.configure<JavaPluginExtension> { ... }` và `tasks.named<JavaCompile>("compileJava")`. Ta chỉ rõ kiểu mà Gradle phải tìm/cấu hình.

Hai cách có thể cùng cấu hình một đối tượng. Accessor ngắn gọn khi có sẵn; API tường minh rất hữu ích trong logic dùng chung, plugin, trường hợp truy cập động hoặc nơi IDE không tìm thấy accessor.

**Điểm cốt lõi:** Trong Kotlin DSL, các accessor sinh tự động dựa trên mô hình project biết được **sau khối `plugins`**, không phải cứ có một tên chuỗi xuất hiện ở bất cứ đâu trong script là Gradle tạo accessor. Đặc biệt, plugin chỉ được áp dụng bằng `apply(plugin = "java")` ở thân script không làm Gradle tự sinh lại accessor `java { ... }` cho chính script đó. Khi gặp trường hợp này, nên chuyển plugin sang `plugins` nếu phù hợp, hoặc dùng API tường minh sau khi plugin đã được áp dụng.

## 3. Task có kiểu: `tasks.named<T>`, `tasks.register<T>` và `tasks.withType<T>`

Task container `tasks` thuộc project và chứa các task có tên. Kiểu tác vụ `JavaCompile` có thuộc tính biên dịch Java; `Test` có API chạy test; `Copy` có API sao chép file. Khi biết kiểu, ta truy cập được API chuyên biệt thay vì chỉ các thuộc tính của kiểu `Task` chung.

### 3.1. Cấu hình một task đã tồn tại với `named<T>`

```kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    java
}

tasks.named<JavaCompile>("compileJava") {
    options.encoding = "UTF-8"
}
```

Ý nghĩa:

- Java plugin cung cấp task `compileJava` khi dùng Java source set mặc định.
- `named<JavaCompile>("compileJava")` trả về một `TaskProvider<JavaCompile>`, để cấu hình task theo nhu cầu.
- Trong khối cấu hình, Kotlin biết đối tượng là `JavaCompile` nên có thuộc tính `options.encoding`.
- Việc dùng `named` không tự yêu cầu Gradle thực thi `compileJava`. Nó chỉ tham chiếu/cấu hình task đã được đăng ký.

Với task kiểm thử được tạo bởi Java plugin, sử dụng đúng kiểu:

```kotlin
import org.gradle.api.tasks.testing.Test

tasks.named<Test>("test") {
    useJUnitPlatform()
}
```

Đoạn này **chỉ cấu hình cách chạy test**; để JUnit 5 hoạt động, project còn cần khai báo dependency JUnit phù hợp. Nếu viết `tasks.named("test") { useJUnitPlatform() }`, Kotlin có thể không tìm thấy phương thức chuyên biệt vì receiver lúc đó chỉ được biết là `Task`. Tham số kiểu `<Test>` làm rõ API mà khối cần sử dụng.

### 3.2. Đăng ký task mới có kiểu với `register<T>`

```kotlin
import org.gradle.api.tasks.Copy

val stageDocs = tasks.register<Copy>("stageDocs") {
    group = "documentation"
    description = "Sao chép tài liệu vào thư mục build"

    from(layout.projectDirectory.file("docs/guide.txt"))
    into(layout.buildDirectory.dir("staged-docs"))
}
```

`stageDocs` là một `TaskProvider<Copy>`, không phải kết quả đã sao chép file. Các phương thức `from` và `into` có sẵn vì task có kiểu `Copy`. Khai báo `layout.buildDirectory.dir(...)` dùng đối tượng do Gradle cung cấp để biểu diễn đầu ra trong thư mục build, thay cho đường dẫn tuyệt đối.

Một task khác có thể phụ thuộc vào provider ấy:

```kotlin
tasks.register("prepareStudy") {
    dependsOn(stageDocs)
    doLast {
        println("Da chuan bi tai lieu")
    }
}
```

Nếu chạy `prepareStudy`, Gradle xử lý `stageDocs` trước nhờ `dependsOn(stageDocs)`. Khi chỉ đọc hoặc cấu hình script, hành động sao chép chưa diễn ra.

### 3.3. Cấu hình mọi task thuộc một kiểu với `withType<T>().configureEach`

```kotlin
import org.gradle.api.tasks.compile.JavaCompile

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
```

Điểm khác với `named`:

- `named("compileJava")` nhắm **một task có tên**; cần task đó tồn tại khi tra cứu.
- `withType<JavaCompile>()` chọn **tập task có kiểu phù hợp**, ví dụ task biên dịch mã chính, mã test và những task biên dịch Java được đăng ký thêm.
- `configureEach` thiết lập quy tắc cấu hình theo nhu cầu cho các phần tử phù hợp mà không chủ động hiện thực hóa tất cả task ngay lúc cấu hình.

Đây là lựa chọn thường phù hợp cho quy ước chung giữa nhiều task, nhưng có thể tác động nhiều task hơn dự kiến. Nếu chỉ muốn điều chỉnh phần `main`, hãy dùng `tasks.named<JavaCompile>("compileJava")`.

### 3.4. Vì sao tránh `getByName`/`create` khi không cần?

So sánh:

| API | Trường hợp phù hợp | Lưu ý |
| --- | --- | --- |
| `tasks.named<T>("x")` | Task đã đăng ký; cần cấu hình hoặc giữ provider | Không yêu cầu lập tức lấy đối tượng task |
| `tasks.register<T>("x")` | Đăng ký task mới có kiểu | Cho phép cấu hình theo nhu cầu |
| `tasks.withType<T>().configureEach` | Áp dụng quy tắc cho các task cùng kiểu | Không ép toàn bộ task phù hợp được hiện thực hóa ngay |
| `tasks.getByName("x")` | Thực sự cần đối tượng task ở thời điểm cấu hình | Có thể hiện thực hóa task sớm |
| `tasks.create("x")` | API tạo task trực tiếp theo lối cũ | Ưu tiên `register` với task mới |
| `provider.get()` | Cần giá trị/đối tượng thật ngay lúc đọc | Gọi quá sớm có thể làm mất tính trì hoãn |

Không phải mọi lần gọi `get()` đều sai; điều cần tránh là **ép lấy đối tượng hoặc giá trị trước khi Gradle thực sự cần**. Tham chiếu provider và cấu hình qua API có kiểu thường vừa rõ ràng vừa phù hợp với cơ chế tối ưu Gradle.

## 4. Extension có kiểu: `java { }` và `extensions.getByType<T>()`

**Extension** là đối tượng cấu hình được gắn vào một model Gradle, phổ biến nhất là project. Ví dụ Java plugin cung cấp `JavaPluginExtension` để cấu hình Java toolchain và các lựa chọn liên quan.

Cách ngắn gọn nhờ accessor:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
    withSourcesJar()
}
```

`java { }` ở đây là accessor của extension đã được plugin bổ sung, còn `toolchain.languageVersion` là thuộc tính có kiểu tương ứng. `languageVersion.set(...)` thiết lập yêu cầu Java 17 cho toolchain theo mô hình Provider API; để Gradle thực sự tìm được JDK phù hợp, môi trường cần có JDK hoặc cấu hình giải pháp cấp phát toolchain.

Khi cần truy cập trực tiếp theo kiểu, cú pháp tương đương là:

```kotlin
import org.gradle.api.plugins.JavaPluginExtension

extensions.configure<JavaPluginExtension> {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
    withSourcesJar()
}
```

Hai cách đều hướng tới đối tượng cấu hình Java của project. **Đừng đặt cả hai khối với những giá trị mâu thuẫn** nếu không có lý do. Chọn cách dễ đọc nhất phù hợp bối cảnh.

Có thể lấy chính đối tượng extension:

```kotlin
import org.gradle.api.plugins.JavaPluginExtension

val javaExtension: JavaPluginExtension =
    extensions.getByType<JavaPluginExtension>()

javaExtension.toolchain.languageVersion.set(JavaLanguageVersion.of(17))
```

Ở đây `getByType` tìm extension có kiểu yêu cầu; nếu không tồn tại, nó phát sinh lỗi. Khi một plugin là tùy chọn, `findByType<JavaPluginExtension>()` cho phép kiểm tra kết quả null. Không nên dùng `getByType` rồi giả định đối tượng chắc chắn tồn tại ở mọi project.

### Extension do chính build script tạo

Giả sử muốn khai báo tiêu đề bài học dưới dạng một extension tùy chỉnh:

```kotlin
import org.gradle.api.provider.Property

abstract class LessonOptions {
    abstract val headline: Property<String>
}

val lessonOptions =
    extensions.create("lessonOptions", LessonOptions::class.java)

lessonOptions.headline.convention("Kotlin DSL typed API")
lessonOptions.headline.set("Gradle API co kieu")
```

Đây là **đoạn mã có thể bổ sung vào thân `build.gradle.kts`**, sau phần khai báo plugin; Gradle quản lý giá trị thuộc tính `Property<String>` của lớp trừu tượng do nó tạo. `convention` đặt giá trị mặc định, còn `set` đặt giá trị cấu hình hiện tại.

Điểm dễ mắc lỗi: vì `lessonOptions` được tạo ở **thân cùng script**, đừng giả định ngay tại đó đã có accessor sinh tự động `lessonOptions { ... }`. Truy cập qua biến `lessonOptions` hoặc API `extensions` là cách rõ ràng hơn. Khi extension được plugin công bố đủ sớm trong giai đoạn sinh schema của một script tiêu thụ, accessor tương ứng có thể xuất hiện.

Có thể cấu hình extension theo kiểu sau khi nó được tạo:

```kotlin
extensions.configure<LessonOptions> {
    headline.set("Noi dung tu extension")
}
```

Câu lệnh này yêu cầu một extension `LessonOptions` đang có trong container của project. Khi có nhiều đối tượng cùng loại nhưng khác tên, cần xác định đúng đối tượng/đường truy cập để tránh nhầm lẫn.

## 5. Container có kiểu: tập đối tượng được quản lý theo tên

Một **container** không phải một task duy nhất mà là tập các đối tượng Gradle quản lý. Kiểu container phổ biến là `NamedDomainObjectContainer<T>`: các phần tử có tên và có kiểu `T`.

Ví dụ đáng nhớ:

| Container | Phần tử tiêu biểu | Thao tác thường dùng |
| --- | --- | --- |
| `tasks` | `Task`, `JavaCompile`, `Test`, `Copy`... | `named`, `register`, `withType` |
| `sourceSets` | `SourceSet` như `main`, `test` | `named`, `create`, `configureEach` |
| `configurations` | `Configuration` như `compileClasspath`, `testImplementation` | `named`, `register` (khi cần cấu hình mới) |
| Container do plugin tự định nghĩa | Một kiểu phần tử có tên của plugin đó | API phụ thuộc kiểu và hợp đồng plugin |

**Task container** có khả năng quản lý `TaskProvider`; không nên đồng nhất máy móc mọi container với `TaskContainer`. Tuy vậy, tư duy chung là dùng **kiểu phần tử + tên + API cấu hình thích hợp**.

### 5.1. Truy cập source set bằng `named`

Khi project áp dụng Java plugin:

```kotlin
sourceSets {
    named("main") {
        java.srcDir("src/extra/java")
    }

    named("test") {
        resources.srcDir("src/test/fixtures")
    }
}
```

`sourceSets` là accessor của `SourceSetContainer`. Trong `named("main") { ... }`, receiver được biết là một `SourceSet`, nên thuộc tính `java` và `resources` có API tương ứng để thêm thư mục nguồn.

- `srcDir(...)` **bổ sung** thư mục vào tập nguồn tương ứng; không tự loại `src/main/java` hoặc `src/test/resources` mặc định.
- `sourceSets.named("main")` chỉ tham chiếu một source set đã có; gõ sai tên sẽ dẫn đến lỗi tra cứu khi cấu hình.
- Đăng ký hoặc tạo source set khác, ví dụ `integrationTest`, đòi hỏi thiết lập classpath/task phù hợp; chỉ thêm thư mục không tự khiến Java plugin chạy mọi bài integration test.

Cũng có thể truy cập container theo kiểu tường minh, khi accessor `sourceSets` không khả dụng:

```kotlin
import org.gradle.api.tasks.SourceSetContainer

val sourceSetContainer = extensions.getByType<SourceSetContainer>()

sourceSetContainer.named("main") {
    java.srcDir("src/extra/java")
}
```

Kiểu `SourceSetContainer` do Java plugin cung cấp, nên cần bảo đảm plugin đã áp dụng trước khi tìm extension này.

### 5.2. Truy cập cấu hình phụ thuộc bằng container

```kotlin
val testImplementationConfiguration =
    configurations.named("testImplementation")
```

Giá trị trả về là provider của một `Configuration`. Cấu hình `testImplementation` thường do Java plugin thêm vào; nó biểu diễn nhóm phụ thuộc cần thiết cho việc biên dịch/chạy test, **không phải task có thể thực thi**.

Để khai báo dependency, dùng DSL được tạo khi Java plugin đã được áp dụng:

```kotlin
repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.2")
}
```

Nếu đang viết logic chung không có accessor `testImplementation(...)`, có thể dùng API chung của dependency handler, ví dụ `dependencies.add("testImplementation", "org.junit.jupiter:junit-jupiter:5.10.2")` sau khi cấu hình này tồn tại. Không nhầm `configurations.named("testImplementation")` với lệnh làm Gradle tải dependency ngay lập tức: nó chỉ lấy tham chiếu đến một cấu hình.

### 5.3. Phân biệt `named`, `register`, `create`

- **`named("x")`:** tìm và cấu hình phần tử có tên đã được đăng ký; hữu ích khi plugin đã tạo sẵn đối tượng.
- **`register("x")`:** đăng ký phần tử mới theo mô hình có thể trì hoãn khi container hỗ trợ; phù hợp với task và nhiều container tương ứng.
- **`create("x")`:** tạo trực tiếp phần tử; trong các container hỗ trợ cả hai cách, có thể làm đối tượng được tạo/cấu hình sớm.
- **`configureEach { ... }`:** áp dụng cấu hình cho phần tử của tập hợp theo nhu cầu, thay vì ép tất cả đối tượng được hiện thực hóa ngay để lặp.

API nào thực sự khả dụng phụ thuộc kiểu container. Không tự giả định một container bất kỳ đều có tất cả phương thức của `TaskContainer`.

## 6. `Provider<T>` và `Property<T>`: nối các thành phần mà vẫn giữ tính trì hoãn

Khi gặp API có kiểu trong Gradle Kotlin DSL, người học thường thấy `Property<String>`, `Provider<Directory>`, `TaskProvider<Copy>`, v.v. Chúng giữ thông tin **kiểu giá trị** và cho phép Gradle cung cấp/đánh giá giá trị khi cần.

Ví dụ:

```kotlin
val docsOutput = layout.buildDirectory.dir("staged-docs")

tasks.register<Copy>("stageDocs") {
    from(layout.projectDirectory.file("docs/guide.txt"))
    into(docsOutput)
}
```

`docsOutput` là provider của một thư mục dưới `build`. Gradle có thể dùng provider đó làm đường dẫn đầu ra của task mà không phải chắp nối chuỗi từ đường dẫn làm việc.

Phân biệt các phương thức:

| Phương thức | Ý nghĩa |
| --- | --- |
| `property.set(value)` | Thiết lập giá trị hoặc một provider cung cấp giá trị |
| `property.convention(value)` | Thiết lập giá trị mặc định, có thể bị cấu hình tường minh thay thế |
| `provider.map { ... }` | Tạo provider mới bằng cách biến đổi giá trị |
| `provider.flatMap { ... }` | Tạo provider mới khi phép biến đổi trả về provider khác |
| `provider.get()` | Yêu cầu giá trị hiện tại; có thể khiến giá trị được tính/đối tượng được hiện thực hóa |

Ví dụ biến đổi provider:

```kotlin
val title: Provider<String> = providers.provider {
    "Gradle Kotlin DSL"
}

val upperTitle: Provider<String> = title.map { it.uppercase() }
```

Đây là mã minh họa được đặt trong `build.gradle.kts` hoặc logic Gradle có import `org.gradle.api.provider.Provider` khi cần. Nó xây dựng quan hệ giữa provider và giá trị. Không nên lạm dụng `get()` ở cấp cấu hình, vì làm như vậy có thể khiến giá trị được tính quá sớm, giảm lợi ích trì hoãn hoặc tạo điều kiện không phù hợp với configuration cache.

**Quan hệ dữ liệu và quan hệ thứ tự là hai vấn đề liên quan:** dùng `dependsOn` để xác định task cần chạy trước; dùng input/output và provider để biểu đạt file/giá trị mà task tiêu thụ. Nếu task A tạo file cho task B, cách tốt là cho B nhận provider của output A khi API hỗ trợ, thay vì hard-code tên file và tự hy vọng A đã chạy.

## 7. Accessor sinh tự động: khi nào có, khi nào không?

Trong Kotlin DSL, những tên như `java`, `sourceSets`, `implementation` và một số accessor task/cấu hình do plugin tạo sẽ được Gradle cung cấp dựa trên mô hình có thể biết lúc biên dịch script.

Có thể hình dung:

```text
plugins { java }
       |
       v
Áp dụng plugin trong giai đoạn xác định schema
       |
       v
Gradle biết java extension, sourceSets, configurations, task...
       |
       v
Sinh type-safe accessors cho phần tử phù hợp
       |
       v
Biên dịch phần còn lại của build.gradle.kts
       |
       v
java { ... }, sourceSets { ... }, testImplementation(...) có thể dùng
```

Trong khi đó:

```kotlin
// Đoạn minh họa tình huống khó sử dụng accessor:
apply(plugin = "java")
```

Phần thân script được biên dịch theo schema đã có trước đó; việc áp dụng plugin muộn không bảo đảm `java { ... }` hay `sourceSets { ... }` được sinh cho script hiện tại. Để cấu hình Java plugin khi phải áp dụng bằng `apply`, có thể gọi API tường minh **sau khi plugin đã được áp dụng**:

```kotlin
import org.gradle.api.plugins.JavaPluginExtension

apply(plugin = "java")

extensions.configure<JavaPluginExtension> {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}
```

Đoạn này là một ví dụ **thay thế** cho `plugins { java }` ở script riêng; đừng chép cả hai cách áp dụng plugin vào một ví dụ mà không có lý do.

Một trường hợp tương tự xảy ra với extension hoặc task được tạo ở thân script. Nếu plugin tùy chỉnh công bố extension/task từ khối `plugins`, Gradle có thể tạo accessor. Nếu ta tạo chúng sau lúc schema đã được xác định, hãy dùng biến giữ đối tượng hoặc các API như `extensions.getByType<T>()`, `tasks.named<T>(...)`. Đây là lý do cú pháp `extensions.configure<SomeExtension>` quan trọng ngay cả khi bạn quen viết DSL ngắn.

**Giới hạn cần hiểu:** Accessor giúp truy cập một phần mô hình có tên và kiểu đã biết; nó không làm cho dữ liệu động, chuỗi tên nhập từ người dùng hoặc hành vi plugin tùy chỉnh trở thành hoàn toàn an toàn ở thời điểm biên dịch.

## 8. Dự án hoàn chỉnh có thể chạy: typed task, extension và source-set container

Ví dụ này dùng **Gradle Kotlin DSL và Java 17**. Ta sẽ:

1. Áp dụng Java plugin để có `java` extension, `sourceSets` và `compileJava`.
2. Dùng accessor `java { }` để đặt toolchain.
3. Dùng container `sourceSets.named("main")` để thêm một nguồn Java.
4. Cấu hình task theo kiểu `JavaCompile`.
5. Đăng ký `Copy` có kiểu và tạo quan hệ phụ thuộc bằng `TaskProvider`.
6. Tạo extension có kiểu `LessonOptions` và task có kiểu `PrintHeadline` dùng `Property<String>`.

Cây file đầu vào:

```text
typed-api-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── docs/
│   └── guide.txt
├── src/
│   ├── main/java/demo/Main.java
│   └── extra/java/demo/Helper.java
└── build/                     (Gradle sinh ra sau khi chạy)
```

**File `settings.gradle.kts`:**

```kotlin
rootProject.name = "typed-api-demo"
```

**File `build.gradle.kts`:**

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Copy
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    java
}

// Extension riêng do build script đăng ký.
abstract class LessonOptions {
    abstract val headline: Property<String>
}

// Task riêng, có input khai báo bằng API có kiểu.
abstract class PrintHeadline : DefaultTask() {
    @get:Input
    abstract val headline: Property<String>

    @TaskAction
    fun printHeadline() {
        println("[LESSON] " + headline.get())
    }
}

val lessonOptions =
    extensions.create("lessonOptions", LessonOptions::class.java)

lessonOptions.headline.convention("Kotlin DSL typed API")

// Accessor sinh tự động từ Java plugin.
java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

// SourceSetContainer: thêm nguồn Java ngoài src/main/java.
sourceSets {
    named("main") {
        java.srcDir("src/extra/java")
    }
}

// TaskContainer: cấu hình task do Java plugin cung cấp.
tasks.named<JavaCompile>("compileJava") {
    options.encoding = "UTF-8"
}

// Đăng ký task Copy và giữ provider thay vì buộc lấy Task.
val stageDocs = tasks.register<Copy>("stageDocs") {
    group = "learning"
    description = "Đưa guide.txt vào build/staged-docs"
    from(layout.projectDirectory.file("docs/guide.txt"))
    into(layout.buildDirectory.dir("staged-docs"))
}

// Task mới phụ thuộc vào provider của stageDocs.
tasks.register("prepareStudy") {
    group = "learning"
    dependsOn(stageDocs)
    doLast {
        println("[STAGE] docs ready")
    }
}

// Task riêng nhận giá trị từ extension qua Property<T>.
tasks.register<PrintHeadline>("printHeadline") {
    group = "learning"
    headline.set(lessonOptions.headline)
}
```

**File `docs/guide.txt`:**

```text
A small guide for Gradle Kotlin DSL.
```

**File `src/extra/java/demo/Helper.java`:**

```java
package demo;

public final class Helper {
    private Helper() {
    }

    public static String message() {
        return "typed Gradle API";
    }
}
```

**File `src/main/java/demo/Main.java`:**

```java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Hello from " + Helper.message());
    }
}
```

**Chuẩn bị môi trường:** Có JDK 17 phù hợp và Gradle hỗ trợ Java 17; dùng Gradle Wrapper của dự án nếu đã có. Với thư mục mới chưa có Wrapper, cài Gradle tương thích rồi chạy `gradle wrapper` một lần để tạo `gradlew`/`gradlew.bat` và `gradle/wrapper`. Nếu không có JDK đáp ứng toolchain, cần cài hoặc cấu hình cấp phát trước. Ví dụ không cần tải dependency bên ngoài vì chỉ dùng Java plugin và thư viện chuẩn.

Trên Linux/macOS chạy từng lệnh trong thư mục project:

```bash
./gradlew -q printHeadline
./gradlew -q prepareStudy
./gradlew -q compileJava
java -cp build/classes/java/main demo.Main
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat -q printHeadline
.\gradlew.bat -q prepareStudy
.\gradlew.bat -q compileJava
java -cp build\classes\java\main demo.Main
```

**Kết quả chuẩn của từng lệnh** khi chạy thành công, tách riêng để không phụ thuộc thứ tự của các task độc lập:

- `printHeadline` in `[LESSON] Kotlin DSL typed API`.
- `prepareStudy` in `[STAGE] docs ready`, đồng thời task `stageDocs` đã sao chép `guide.txt` vào `build/staged-docs/guide.txt`.
- `compileJava` với `-q` thường không in dòng của chương trình `Main` vì chỉ biên dịch, không chạy `main`.
- Lệnh `java -cp ... demo.Main` in `Hello from typed Gradle API`.

Output đáng kiểm tra:

```text
build/
├── classes/java/main/demo/
│   ├── Main.class
│   └── Helper.class
└── staged-docs/
    └── guide.txt
```

`Helper.java` dù nằm ở `src/extra/java` vẫn được biên dịch vì ta đã bổ sung thư mục bằng `sourceSets.named("main")`. Nếu bỏ cấu hình `java.srcDir("src/extra/java")` rồi chạy `./gradlew clean compileJava`, trình biên dịch sẽ không tìm thấy lớp `Helper` mà `Main` cần; đây là cách kiểm chứng vai trò của source-set container.

**Vì sao ví dụ minh họa đúng API có kiểu?**

| Thành phần | Dòng cấu hình | Kiểu được sử dụng |
| --- | --- | --- |
| Extension Java | `java { ... }` | `JavaPluginExtension` qua accessor |
| Container source set | `sourceSets.named("main")` | `SourceSetContainer` / `SourceSet` |
| Task có sẵn | `tasks.named<JavaCompile>("compileJava")` | `TaskProvider<JavaCompile>` |
| Task mới | `tasks.register<Copy>("stageDocs")` | `TaskProvider<Copy>` |
| Phụ thuộc task | `dependsOn(stageDocs)` | Tham chiếu provider của task |
| Extension tự tạo | `extensions.create("lessonOptions", LessonOptions::class.java)` | `LessonOptions` |
| Task tự tạo | `tasks.register<PrintHeadline>(...)` | `PrintHeadline` |
| Đầu vào task | `headline.set(lessonOptions.headline)` | `Property<String>`, giữ quan hệ dữ liệu |

Lớp `PrintHeadline` dùng `@get:Input` trên property Kotlin để Gradle biết đây là đầu vào task, và `@TaskAction` trên hàm thực thi. Task chỉ in ra console, không khai báo file output, nên ví dụ này dùng để minh họa kiểu và thời điểm thực thi; đừng kỳ vọng nó có output file để Gradle bỏ qua nhờ up-to-date check. Với task tạo file thực tế, cần khai báo thêm `@OutputFile` hoặc `@OutputDirectory` thích hợp và giữ công việc xác định.

## 9. Truy cập phần tử có kiểu trong plugin hoặc build logic dùng chung

Một build script đơn giản có thể dùng accessor ngắn như `java { ... }`. Trong logic plugin, convention plugin hoặc hàm tái sử dụng giữa các project, thường phải chỉ rõ model và kiểu:

```kotlin
import org.gradle.api.Project
import org.gradle.api.plugins.JavaPluginExtension
import org.gradle.api.tasks.compile.JavaCompile

fun configureJava(project: Project) {
    project.pluginManager.apply("java")

    project.extensions.configure(
        JavaPluginExtension::class.java
    ) {
        toolchain.languageVersion.set(JavaLanguageVersion.of(17))
    }

    project.tasks.named("compileJava", JavaCompile::class.java) {
        options.encoding = "UTF-8"
    }
}
```

Đây là **hàm minh họa**, không phải một file plugin độc lập hoàn chỉnh: nó phải được đặt trong mã Gradle phù hợp và được gọi với một `Project`. Nó cho thấy API Gradle gốc cũng có phiên bản nhận `Class<T>` tường minh; các cú pháp `named<T>` và `configure<T>` trong `build.gradle.kts` là tiện ích Kotlin DSL để dùng ngắn hơn.

Khi plugin chỉ có thể xuất hiện sau đó, có thể đăng ký cấu hình tại thời điểm plugin được áp dụng thay vì tra cứu trước:

```kotlin
import org.gradle.api.plugins.JavaPluginExtension

pluginManager.withPlugin("java") {
    extensions.configure<JavaPluginExtension> {
        toolchain.languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

Đoạn này phù hợp để đặt trong build logic chạy trên project; khi Java plugin có mặt, khối cấu hình sẽ được áp dụng. Nó tránh lỗi `getByType` khi extension chưa tồn tại vào thời điểm thực thi cấu hình.

Đừng đưa việc cấu hình/hiện thực hóa tất cả task vào `afterEvaluate` một cách máy móc. Với phần lớn quy tắc thông thường, `plugins.withId`/`pluginManager.withPlugin` kết hợp `tasks.named`, `tasks.withType().configureEach` và các provider đã đủ để biểu đạt thời điểm phù hợp.

## 10. Những lỗi hay gặp khi chuyển từ Groovy DSL sang Kotlin DSL

| Lỗi/triệu chứng | Nguyên nhân | Cách giải quyết |
| --- | --- | --- |
| `Unresolved reference: java` khi viết `java { ... }` | Java plugin chưa được công bố qua `plugins` ở điểm sinh accessor hoặc dùng sai phạm vi receiver | Khai báo `plugins { java }` nếu phù hợp, hoặc `extensions.configure<JavaPluginExtension> { ... }` sau khi áp dụng plugin |
| `Unresolved reference: useJUnitPlatform` | Khối đang cấu hình một `Task` chung, không phải kiểu `Test` | Dùng `tasks.named<Test>("test") { useJUnitPlatform() }` |
| `Unresolved reference: from`/`into` | Task được đăng ký như `Task` chung thay vì `Copy` | Dùng `tasks.register<Copy>("name") { ... }` |
| Không tìm thấy task `compileJava` | Project chưa áp dụng Java plugin, sai project hoặc sai tên task | Xác định plugin/đường dẫn project, xem `./gradlew tasks --all` |
| `getByType<JavaPluginExtension>()` thất bại | Extension yêu cầu chưa được đăng ký | Áp dụng plugin trước, hoặc chờ bằng `withPlugin` |
| Tưởng chuỗi `"main"` được kiểm tra lúc biên dịch | `named("main")` vẫn tra cứu theo tên lúc cấu hình | Kiểm tra đúng tên phần tử và dùng accessor có sẵn khi thích hợp |
| Task không chạy dù đã `tasks.register` | Đăng ký không đồng nghĩa yêu cầu thực thi | Chạy task theo tên hoặc khai báo phụ thuộc từ mục tiêu phù hợp |
| Configuration chậm vì gọi `get()` liên tục | Ép hiện thực hóa task hoặc tính provider quá sớm | Dùng `named`, `register`, `configureEach` và truyền provider |
| File sinh không được task sau sử dụng đúng cách | Chỉ ghi đường dẫn chuỗi, không khai báo quan hệ/đầu vào-đầu ra | Kết nối provider output và khai báo input/output cho task |
| Tạo extension mới rồi dùng `myExtension { }` trong cùng script nhưng Kotlin không nhận | Extension được tạo sau giai đoạn sinh accessor | Giữ đối tượng trả về từ `extensions.create` hoặc dùng API theo kiểu |
| Truy cập `sourceSets` mà IDE không biết tên | Chưa có plugin khai báo container hoặc build logic dùng môi trường không có accessor | Dùng Java plugin và `SourceSetContainer` tường minh khi cần |
| Cố chuyển cú pháp Groovy trực tiếp | Kotlin khác về chuỗi, lời gọi hàm và property | Sử dụng `"..."`, `.set(...)`, `register<T>` và Kotlin lambda |

Một chuyển đổi phổ biến:

```groovy
// Groovy DSL (build.gradle)
tasks.named('compileJava') {
    options.encoding = 'UTF-8'
}
```

```kotlin
// Kotlin DSL (build.gradle.kts)
tasks.named<JavaCompile>("compileJava") {
    options.encoding = "UTF-8"
}
```

Ở Kotlin DSL, ta nên chỉ rõ `JavaCompile` khi cần API chuyên biệt. Nếu mã đang chạy trong build script mà các kiểu Gradle chưa có import ngầm, thêm import cho `JavaCompile` để Kotlin biên dịch được. Khác biệt không chỉ là dấu nháy: việc chọn đúng kiểu và API provider giúp script dễ kiểm tra và bảo trì.

## 11. Một quy trình đọc và sửa cấu hình an toàn

Khi cần thay đổi một Gradle Kotlin DSL script chưa quen, hãy làm theo đường đi:

1. **Xác định plugin đang áp dụng.** Không giả định `java`, `sourceSets` hoặc task `test` tồn tại trong mọi project.
2. **Phân loại đối tượng.** Đó là task (`JavaCompile`/`Copy`), extension (`JavaPluginExtension`) hay container (`SourceSetContainer`/`ConfigurationContainer`)?
3. **Chọn accessor/API phù hợp.** Dùng `java { }` nếu có accessor; dùng `extensions.configure<T>` nếu phải tường minh; dùng `tasks.named<T>`/`register<T>` cho task.
4. **Giữ tham chiếu theo nhu cầu.** Ưu tiên `TaskProvider<T>`, `Property<T>`, `Provider<T>`; đừng vội `get()`.
5. **Đảm bảo đúng task và thời điểm.** `named` đòi tên đã tồn tại; `withPlugin` hữu ích nếu plugin tùy chọn/chưa áp dụng; `configureEach` dùng cho cả tập task phù hợp.
6. **Kiểm chứng bằng Gradle.** Chạy `help`, `tasks --all`, task cụ thể hoặc `--dry-run` để thấy kế hoạch, rồi chạy thật và xem output mong muốn.

Các lệnh hữu ích trong ví dụ mục 8:

```bash
./gradlew help
./gradlew tasks --all
./gradlew stageDocs --dry-run
./gradlew printHeadline
./gradlew compileJava
```

`--dry-run` hiển thị task dự kiến được xử lý mà không chạy task action; nó không xác nhận đã tạo file đầu ra. Để kiểm chứng công việc thật, bỏ `--dry-run` và kiểm tra `build/staged-docs/guide.txt` hoặc `build/classes/java/main/demo/Helper.class`.

Nếu Kotlin báo lỗi biên dịch `build.gradle.kts`, hãy sửa tên API/import/kiểu trước khi điều tra hành động task; trong tình huống đó Gradle chưa tới bước thực thi công việc tương ứng.

## 12. Bài tập thực hành và câu hỏi kiểm tra

**Bài tập A — một task có kiểu.** Trong dự án mục 8, thay `tasks.named<JavaCompile>("compileJava")` bằng `tasks.withType<JavaCompile>().configureEach` và giữ cấu hình `options.encoding`. Giải thích vì sao thay đổi này có thể ảnh hưởng cả task biên dịch test nếu project bổ sung source set `test`.

**Bài tập B — accessor so với API tường minh.** Thay khối `java { ... }` bằng `extensions.configure<JavaPluginExtension> { ... }` trong cùng project, thêm import phù hợp và chạy lại `compileJava`. Kiểm tra kết quả khi vẫn dùng JDK 17. Không để hai khối đặt toolchain mâu thuẫn.

**Bài tập C — container có tên.** Đổi source root `src/extra/java` sang `src/shared/java`, di chuyển `Helper.java` và sửa `sourceSets.named("main")`. Chạy `clean compileJava`. Nếu quên cập nhật source set, lỗi nào sẽ xuất hiện và vì sao?

**Bài tập D — extension và task tùy chỉnh.** Sửa `lessonOptions.headline.convention("Kotlin DSL typed API")` thành chuỗi khác. Chạy `printHeadline` và dự đoán output. Sau đó dùng `headline.set("...")` trong task để ghi đè giá trị nhận từ extension; giải thích khác biệt giữa mặc định và giá trị được thiết lập tường minh.

**Bài tập E — chọn API theo trường hợp.** Với một task `test` có sẵn, một task `Copy` mới, một Java extension và một source set `main` đã tồn tại, hãy chọn giữa `named<T>`, `register<T>`, `extensions.configure<T>` và `sourceSets.named`. Giải thích vì sao `tasks.create`/`getByName` không phải lựa chọn mặc định.

**Câu hỏi tự kiểm tra:**

1. `TaskProvider<Copy>` khác đối tượng `Copy` đã được hiện thực hóa ở điểm nào?
2. Vì sao `tasks.named<Test>("test")` hữu ích hơn `tasks.named("test")` khi cần gọi `useJUnitPlatform()`?
3. `java { }` và `extensions.configure<JavaPluginExtension> { }` liên hệ thế nào?
4. `sourceSets.named("main")` khác `tasks.named("compileJava")` về kiểu phần tử?
5. Accessor sinh tự động dựa trên mô hình ở thời điểm nào của Kotlin DSL?
6. Khi extension được tạo trong thân chính `build.gradle.kts`, cách truy cập nào ít phụ thuộc vào accessor tự sinh?
7. `configureEach` có ích gì với configuration avoidance?
8. Một chuỗi tên sai có chắc được trình biên dịch Kotlin phát hiện trước khi Gradle chạy không?
9. `Property<T>` và `Provider<T>` giúp phối hợp giữa extension và task thế nào?
10. Khi một task phải dùng file do task khác sinh, cần mô tả cả những loại quan hệ nào?

**Ghi nhớ:** Trong Kotlin DSL, **kiểu đối tượng quyết định API có thể gọi**, còn **container và provider quyết định cách tìm/cấu hình đối tượng mà vẫn giữ khả năng trì hoãn**. Dùng accessor sinh tự động khi plugin công bố mô hình đủ sớm; dùng `tasks.named<T>`, `tasks.register<T>`, `extensions.configure<T>` và `sourceSets.named` khi cần thao tác tường minh. Sau cùng, hãy xác minh bằng lệnh Gradle và output thật để chắc chắn cấu hình có ý nghĩa như mong đợi.