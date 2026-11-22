# Mô hình task và đồ thị phụ thuộc của Gradle

## 1. Tư duy nền tảng: Gradle thực thi một đồ thị, không chạy tuần tự từng dòng trong build script

**Task** là một đơn vị công việc của Gradle, chẳng hạn `compileJava`, `test`, `jar`, `bootJar`, `check`, `build` hoặc task tự viết để sinh mã, kiểm tra chất lượng, đóng gói và xuất bản artifact. Mỗi task có tên, đường dẫn trong project, kiểu, cấu hình, các action thực thi, các quan hệ với task khác, cùng thông tin input/output nếu được khai báo.

**Task graph** (đồ thị task) là tập các task được Gradle chọn cho **một lần gọi lệnh build**, cộng với những quan hệ quyết định task nào cần xuất hiện và thứ tự hợp lệ để chạy. Gradle xem đây là một **đồ thị có hướng không chu trình (DAG)**. Khi chạy `./gradlew build`, Gradle không lấy tất cả task trong project rồi chạy lần lượt: nó xác định các task được yêu cầu, lần theo các quan hệ cần thiết và thực thi tập task liên quan. Task không nằm trong đồ thị thường không chạy.

Ví dụ về một đồ thị minh họa:

```text
prepareSources ──> compileSources ──> packageApp ──> release
       └───────> verifySources ────────────────────┘
```

Quy ước mũi tên `A ──> B` ở đây có nghĩa **B cần A hoàn thành trước**. `release` phụ thuộc cả `packageApp` và `verifySources`, còn hai nhánh sau `prepareSources` không có thứ tự cố định với nhau. Gradle có thể quyết định thứ tự hợp lệ khác nhau, nhất là khi bật chế độ thực thi song song.

**Phân biệt ba khái niệm:**

- **Task được đăng ký/định nghĩa:** có mặt trong mô hình build; chưa chắc được cấu hình đầy đủ hoặc chạy.
- **Task nằm trong đồ thị được chọn:** Gradle xác định task này thuộc công việc cần thực hiện trong lần build hiện tại.
- **Task action thực sự chạy:** chỉ xảy ra nếu không bị `SKIPPED`, `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE` hoặc điều kiện khác ngăn action. Một task có thể có mặt trong đồ thị nhưng không làm công việc mới.

Điều này giải thích vì sao một lần gọi `build` có nhiều task liên quan, nhưng lần chạy tiếp theo có thể kết thúc nhanh hơn dù cấu trúc đồ thị tương tự.

## 2. Task nằm ở đâu trong vòng đời bản dựng?

Gradle phân biệt các giai đoạn:

1. **Initialization (khởi tạo):** đọc thông tin project từ `settings.gradle` / `settings.gradle.kts`, xác định root project, các subproject và cấu trúc build.
2. **Configuration (cấu hình):** áp dụng plugin, xử lý build script và định nghĩa/cấu hình các task cần thiết. Gradle tính toán đồ thị công việc của lần gọi lệnh, gồm dependency và thứ tự.
3. **Execution (thực thi):** chạy action của các task trong đồ thị theo quan hệ đã thiết lập, có xét input/output, cache và điều kiện bỏ qua.

Sơ đồ:

```text
gradlew <requested-task>
        |
        v
 Initialization: xác định project
        |
        v
 Configuration: áp dụng plugin, đăng ký/cấu hình task,
                xác định các quan hệ và đồ thị công việc
        |
        v
 Execution: thực hiện/skip task theo DAG
        |
        v
 Kết quả build: SUCCESS hoặc FAILED
```

Cần lưu ý **configuration cache** có thể lưu và khôi phục kết quả cấu hình: khi cache hợp lệ, Gradle bỏ qua phần lớn công việc configuration truyền thống và khôi phục đồ thị đã lưu. Vì vậy không được thiết kế logic build dựa vào việc một đoạn trong build script chắc chắn sẽ chạy lại mỗi lần.

Trong `build.gradle.kts`:

```kotlin
tasks.register("hello") {
    group = "demo"
    description = "In ra lời chào khi task được thực thi"

    doLast {
        println("Hello Gradle")
    }
}
```

`group` và `description` là **cấu hình task**. Khối `doLast { ... }` thêm một action vào task; `println` bên trong chỉ thực hiện khi action được chạy. Khối cấu hình truyền cho `tasks.register` được trì hoãn đến khi task cần cấu hình. Đừng đặt thao tác mạng, ghi file hoặc publish artifact trực tiếp ở cấp script hay trong khối configuration, vì chúng có thể xảy ra khi chỉ chạy `help` hoặc khi Gradle chuẩn bị đồ thị.

## 3. Ví dụ Gradle Kotlin DSL có thể chạy độc lập: đồ thị phụ thuộc

Tạo một thư mục rỗng với hai file:

**`settings.gradle.kts`**

```kotlin
rootProject.name = "task-graph-demo"
```

**`build.gradle.kts`**

```kotlin
val prepare = tasks.register("prepare") {
    group = "demo"
    description = "Chuẩn bị dữ liệu trước khi biên dịch"
    doLast {
        println("prepare")
    }
}

val compile = tasks.register("compileDemo") {
    group = "demo"
    description = "Giả lập bước biên dịch"
    dependsOn(prepare)
    doLast {
        println("compileDemo")
    }
}

tasks.register("packageDemo") {
    group = "demo"
    description = "Giả lập bước đóng gói"
    dependsOn(compile)
    doLast {
        println("packageDemo")
    }
}
```

Đây là project Gradle đơn giản, **không cần source Java hay plugin Spring Boot**. Cần một bản Gradle tương thích với JVM đang dùng. Nếu project có Gradle Wrapper thì sử dụng lệnh `./gradlew`; nếu chưa có wrapper, có thể dùng bản Gradle đã cài trên máy bằng lệnh `gradle`, hoặc tạo wrapper bằng `gradle wrapper` trước rồi dùng wrapper từ lần sau.

Chạy:

```bash
gradle -q packageDemo
```

**Stdout của các action trong ví dụ (với `-q` để ẩn log thông thường):**

```text
prepare
compileDemo
packageDemo
```

Ba task chạy theo chuỗi:

```text
:prepare --> :compileDemo --> :packageDemo
```

Mặc dù lệnh chỉ yêu cầu `packageDemo`, Gradle vẫn đưa `compileDemo` và `prepare` vào đồ thị vì quan hệ `dependsOn`. Chạy riêng `gradle -q prepare` thì chỉ in `prepare`. Chạy `gradle -q compileDemo` thì in `prepare`, tiếp theo là `compileDemo`. Không cần tự gọi tất cả task theo đúng thứ tự trên CLI.

Để xem kế hoạch thực thi mà **không thực hiện action**:

```bash
gradle packageDemo --dry-run
```

Kết quả hiển thị task được chọn với trạng thái như `SKIPPED` do dry run. Không nhầm `--dry-run` với build đã thực thi thành công: nó giúp quan sát đồ thị, không xác nhận mã biên dịch hay test chạy được.

### Nếu viết bằng Groovy DSL

Tương đương với ví dụ trên trong **`build.gradle`** (đổi `settings.gradle.kts` sang `settings.gradle` nếu muốn dùng Groovy thống nhất):

```groovy
def prepare = tasks.register('prepare') {
    group = 'demo'
    description = 'Chuẩn bị dữ liệu'
    doLast {
        println 'prepare'
    }
}

def compile = tasks.register('compileDemo') {
    group = 'demo'
    dependsOn prepare
    doLast {
        println 'compileDemo'
    }
}

tasks.register('packageDemo') {
    group = 'demo'
    dependsOn compile
    doLast {
        println 'packageDemo'
    }
}
```

Chọn **một** ngôn ngữ DSL cho file build; không dán cả hai ví dụ vào cùng project.

## 4. Các loại quan hệ quyết định đồ thị

Không phải phương thức nào trông giống “chạy sau” cũng tạo dependency.

| API | Khi chỉ yêu cầu task B thì có tự đưa A vào đồ thị? | Ý nghĩa |
| --- | --- | --- |
| `B.dependsOn(A)` | **Có** | B cần A làm xong; A là prerequisite thực sự. |
| `B.mustRunAfter(A)` | **Không** | Chỉ ràng buộc thứ tự nếu cả A và B đều có trong đồ thị. |
| `B.shouldRunAfter(A)` | **Không** | Gợi ý thứ tự mềm nếu cả hai cùng xuất hiện; có thể bị bỏ qua để tránh vòng hoặc tối ưu song song. |
| `A.finalizedBy(B)` | **Có**, khi A được lên lịch | B là finalizer chạy sau A, thường dùng dọn dẹp kể cả khi A thất bại. |
| Input của B lấy từ output của A qua `Provider` | **Có thể tự suy ra A** | Gradle nhận biết task producer nhờ metadata của provider; ít phải viết `dependsOn` bằng tay. |

### 4.1. `dependsOn`: phụ thuộc bắt buộc

`dependsOn` mô tả **điều kiện tiên quyết**: chạy `packageDemo` thì phải làm `compileDemo` trước. Task A được lên lịch vì task B cần kết quả của nó, dù A có thể bị đánh dấu `UP-TO-DATE` nên không thực sự chạy action.

Đồ thị không cho phép chu trình như:

```text
A dependsOn B
B dependsOn A
```

Nếu tạo chu trình phụ thuộc, Gradle báo lỗi cycle; không có thứ tự thực thi hợp lệ.

### 4.2. `mustRunAfter` và `shouldRunAfter`: thứ tự, không phải dependency

Dùng ví dụ riêng sau, thêm vào `build.gradle.kts` của project demo hoặc tạo project mới:

```kotlin
val audit = tasks.register("audit") {
    doLast {
        println("audit")
    }
}

tasks.register("publishDemo") {
    mustRunAfter(audit)
    doLast {
        println("publishDemo")
    }
}
```

Khi gọi riêng:

```bash
gradle -q publishDemo
```

Output:

```text
publishDemo
```

`audit` **không chạy** vì `mustRunAfter` không kéo task này vào đồ thị. Khi gọi cả hai, kể cả đảo thứ tự trên dòng lệnh:

```bash
gradle -q publishDemo audit
```

Output:

```text
audit
publishDemo
```

Nếu đổi thành `shouldRunAfter(audit)` thì thông thường Gradle ưu tiên chạy `audit` trước `publishDemo`, nhưng đó **không phải bảo đảm tuyệt đối**. Gradle có thể bỏ qua quan hệ `shouldRunAfter` nếu gây chu trình thứ tự hoặc để tránh nhàn rỗi khi chạy song song. Khi dữ liệu của B thực sự đòi kết quả A, phải dùng `dependsOn` hoặc nối input/output; `mustRunAfter` không bảo đảm A sẽ được chạy.

Một hệ quả về failure: dù `mustRunAfter` yêu cầu A đứng trước B nếu cùng có mặt, `--continue` vẫn có thể cho B chạy khi A lỗi và hai task **không phụ thuộc dữ liệu vào nhau**. Chỉ `dependsOn` mới biểu đạt A là điều kiện thành công cần thiết cho B.

### 4.3. `finalizedBy`: làm việc dọn dẹp sau một task

`finalizedBy` thường dùng khi một task mở tài nguyên tạm và cần chạy task dọn dẹp sau đó:

```kotlin
val runChecks = tasks.register("runChecks") {
    doLast {
        println("checks")
    }
}

val cleanTemporary = tasks.register("cleanTemporary") {
    doLast {
        println("cleanup")
    }
}

runChecks.configure {
    finalizedBy(cleanTemporary)
}
```

```bash
gradle -q runChecks
```

Output:

```text
checks
cleanup
```

Gradle tự thêm `cleanTemporary` vào đồ thị vì `runChecks` được lên lịch; finalizer thường vẫn chạy khi task được finalize bị lỗi hoặc được xem là `UP-TO-DATE`. Đây là cơ chế quản lý vòng đời resource của task, nhưng không thể bảo đảm dọn dẹp trong mọi trường hợp hệ điều hành giết tiến trình hoặc máy mất điện. Với dịch vụ chạy chung trong nhiều test và build song song, nên xem xét Gradle Shared Build Services hoặc test fixture phù hợp, thay vì dùng global script state.

### 4.4. Dependency ngầm qua producer/consumer

Khi task B khai báo input lấy từ output provider của task A, Gradle có thể suy ra quan hệ mà không cần `dependsOn` viết tay. Cách này giúp dữ liệu và thứ tự thực thi được định nghĩa cùng một chỗ, tránh tình huống B chờ A nhưng đọc nhầm file khác.

Ngược lại, nếu tự nối bằng hardcoded path đến file do task khác tạo mà không mang metadata producer, Gradle có thể không biết dependency; chạy B độc lập sẽ lỗi “file chưa tồn tại” hoặc dùng dữ liệu cũ.

## 5. Ví dụ có input/output thật: đồ thị tự suy ra qua Provider

Ví dụ này **thay thế toàn bộ file `build.gradle.kts` của demo** nếu muốn chạy độc lập, không dán nối vào ví dụ cùng tên. Nó định nghĩa hai custom task type với input/output rõ ràng:

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

abstract class GenerateGreeting : DefaultTask() {
    @get:Input
    abstract val message: Property<String>

    @get:OutputFile
    abstract val targetFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val file = targetFile.get().asFile
        file.parentFile.mkdirs()
        file.writeText(message.get() + "\n")
    }
}

abstract class PrintGreeting : DefaultTask() {
    @get:InputFile
    abstract val sourceFile: RegularFileProperty

    @TaskAction
    fun printMessage() {
        println(sourceFile.get().asFile.readText().trimEnd())
    }
}

val generateGreeting = tasks.register<GenerateGreeting>("generateGreeting") {
    message.set("Hello Gradle")
    targetFile.set(layout.buildDirectory.file("generated/greeting.txt"))
}

tasks.register<PrintGreeting>("printGreeting") {
    sourceFile.set(generateGreeting.flatMap { it.targetFile })
}
```

Chạy:

```bash
gradle -q printGreeting
```

**Stdout chính xác của ví dụ:** `Hello Gradle`.

Khi `printGreeting` được chọn, `generateGreeting` cũng được lên lịch vì thuộc tính `sourceFile` trỏ tới provider của `generateGreeting.targetFile`. File tạo ra nằm dưới `build/generated/greeting.txt`. Task `generateGreeting` đã khai báo `@Input` và `@OutputFile` nên Gradle có thể xác định nó có cần thực thi lại; `printGreeting` không khai báo output, vì chỉ in ra console nên thông thường vẫn chạy action mỗi lần.

Chạy thêm:

```bash
gradle printGreeting --info
```

Ở lần chạy thứ hai nếu input và output không đổi, task sinh file thường hiện `UP-TO-DATE`, còn task in nội dung vẫn thực hiện. Trạng thái có thể thay đổi nếu xóa file, đổi input, đổi code action, thay Gradle version hoặc bật build cache. Điểm quan trọng là **đồ thị vẫn mô tả producer → consumer, dù producer được bỏ qua action nhờ kiểm tra đầu vào/đầu ra**.

### Vì sao ví dụ dùng `Property` và `RegularFileProperty`?

- `Property<String>` giúp input được khai báo và cấu hình lười bằng `set`/`Provider`.
- `RegularFileProperty` biểu diễn file output/input và lưu thông tin producer.
- `@TaskAction` giúp gom logic thực thi vào task type, không trộn với configuration script.
- `@Input` / `@InputFile` / `@OutputFile` giúp Gradle theo dõi thay đổi để tránh chạy lại và hỗ trợ cache theo yêu cầu.

Đây là hướng thiết kế phù hợp hơn cho task quan trọng, dùng lại nhiều nơi hoặc cần tương thích **configuration cache**. Trong task action, tránh truy cập trực tiếp `project`, `gradle`, `rootProject` hoặc đọc biến mutable/global state từ build script; dùng API task properties và service tương thích để mô tả dữ liệu cần dùng.

## 6. Task declaration, registration và configuration avoidance

### Eager và lazy

Gradle hỗ trợ các API dạng:

- `tasks.create("name")`: tạo/configure task theo cách eager, có thể làm build chậm nếu nhiều task không liên quan.
- `tasks.register("name")`: đăng ký task **lười** và trả về `TaskProvider<T>`; Gradle chỉ realize/configure khi cần.
- `tasks.named("existingTask") { ... }`: cấu hình task đã đăng ký/tồn tại theo cách lười.
- `tasks.registering` và `tasks.existing`: các convenience delegate thường gặp trong Kotlin DSL.
- `tasks.getByName("name")` hoặc `tasks.named("name").get()`: buộc lấy task instance, có thể khiến realize sớm; tránh khi có thể truyền `TaskProvider` trực tiếp.

Ví dụ nên dùng khi muốn nối một task chuẩn với task tự tạo:

```kotlin
val validateDocs = tasks.register("validateDocs") {
    group = "verification"
    description = "Kiểm tra tài liệu trước khi chạy check"
    doLast {
        println("docs checked")
    }
}

// Chỉ áp dụng nếu plugin 'java' đã tạo task 'check':
tasks.named("check") {
    dependsOn(validateDocs)
}
```

Khai báo plugin Java ở đầu `build.gradle.kts` để đoạn trên chạy trong project độc lập:

```kotlin
plugins {
    java
}
```

Khi chạy `gradle check`, Gradle thêm `validateDocs` vào đồ thị; các task kiểm thử/kiểm tra khác do Java plugin tạo cũng có thể xuất hiện. `tasks.named("check")` không tự tạo task `check`: task đó phải có từ plugin hoặc một khai báo khác.

**Không cần dùng `get()` để nối dependency:** viết `dependsOn(validateDocs)` hoặc `dependsOn(tasks.named("validateDocs"))` là đủ. Chọn provider tránh cấu hình sớm không cần thiết.

### Không nhầm configuration action và execution action

`tasks.register("x") { println("configured") }` đặt lời in trong **configuration**; có thể xuất hiện khi Gradle realize task x để tính toán đồ thị. `tasks.register("x") { doLast { println("executed") } }` đặt lời in trong **execution**. Với configuration cache, log ở configuration có thể biến mất ở những lần build cache-hit; đây không phải Gradle bỏ task.

Tương tự, `doFirst { ... }` thêm action ở đầu danh sách action của task và `doLast { ... }` thêm ở cuối. Các action trong cùng một task chạy theo thứ tự action list, còn thứ tự **giữa các task** do graph quyết định.

## 7. Đồ thị task của Java và Spring Boot được ghép từ plugin

Các plugin cung cấp task và quan hệ có sẵn:

- **Java plugin:** tạo những task thường gặp như `compileJava`, `processResources`, `classes`, `jar`, `test`, `check`, `assemble` và `build`. Task lifecycle như `build` thường không có action chính: chúng **phụ thuộc** các task xử lý thực sự.
- **Spring Boot Gradle plugin:** bổ sung `bootJar` cho project Java hoặc `bootWar` với War plugin, `bootRun` để chạy ứng dụng, và `bootBuildImage` để dựng OCI image khi điều kiện plugin/task phù hợp. Quan hệ giữa các task phụ thuộc version và cấu hình plugin.
- **Plugin của đội dự án:** có thể thêm task sinh source, format/checkstyle, integration test, SBOM, publish image hoặc deploy.

Trong ứng dụng Spring Boot, đọc tên task không đủ để suy luận rằng `bootRun` bắt buộc tạo executable JAR trước khi chạy: `bootRun` có thể dùng class/resource của source set trực tiếp. Tương tự, không mặc định `build` sẽ publish lên registry hoặc deploy production. Các bước publish/deploy chỉ chạy khi plugin và build logic khai báo rõ.

Ví dụ minh họa custom task quality gate trong project đã bật Java plugin:

```kotlin
plugins {
    java
}

val verifyPackaging = tasks.register("verifyPackaging") {
    group = "verification"
    description = "Chạy kiểm tra riêng trước khi build hoàn tất"
    doLast {
        println("packaging verified")
    }
}

tasks.named("check") {
    dependsOn(verifyPackaging)
}
```

Nếu chạy `gradle -q check`, đoạn `packaging verified` sẽ được in khi `verifyPackaging` thực thi. Nhưng sẽ còn những task khác thuộc đồ thị `check`, và chúng có thể bị `NO-SOURCE` nếu project chưa có Java source/test. Không nên đưa một stdout đầy đủ cố định cho toàn bộ `check`, bởi đồ thị phụ thuộc plugin, mã nguồn và project.

Với project nhiều module:

```text
repo/
├── settings.gradle.kts
├── build.gradle.kts
├── core/build.gradle.kts
└── app/build.gradle.kts
```

Một task có path duy nhất như `:core:jar` hay `:app:bootJar`. Module `app` phụ thuộc module `core` ở cấp **project dependency** có thể kéo theo các task producer của module `core` thông qua biến thể/artifact. Tuy vậy, dependency project Java (`implementation(project(":core"))`) **không đồng nghĩa** với việc chạy `:core:build` đầy đủ; Gradle thường chỉ cần artifact và các task producer tương ứng. Để biết chính xác, phải kiểm tra đồ thị thực tế, vì nó còn phụ thuộc plugin, variant và task được gọi.

## 8. Task graph khác dependency graph của thư viện

Gradle có ít nhất hai loại quan hệ cần phân biệt:

1. **Task dependency graph:** `:app:compileJava` có thể cần output của một task sinh source hoặc producer ở module khác. Đây là đồ thị **công việc sẽ thực hiện**.
2. **Dependency graph của component/library:** `spring-boot-starter-web` kéo theo Spring Framework, logging hoặc servlet stack tùy phiên bản; đây là đồ thị **module/artifact và phiên bản** được giải quyết từ repositories.

Hai đồ thị có liên hệ (resolving dependency có thể dẫn đến producer task khi phụ thuộc project/variant) nhưng không phải cùng một thứ. Khi debug:

```bash
gradle :app:build --dry-run
gradle :app:dependencies --configuration runtimeClasspath
```

Lệnh thứ nhất **quan sát task đã được lên lịch**; lệnh thứ hai **in dependency tree của cấu hình runtimeClasspath**. Ví dụ thứ hai chỉ hợp lệ khi project `:app` có configuration `runtimeClasspath`, thường do Java/Java Library plugin cung cấp. Không đọc output `dependencies` rồi kết luận đó là thứ tự thực thi task.

Một nuance quan trọng: Gradle có thể trì hoãn dependency resolution đến lúc cần artifact. Khi dùng configuration cache, nhiều thông tin cần để lưu đồ thị phải được giải quyết trong giai đoạn chuẩn bị cache. Vì vậy tránh cưỡng bức `configurations.runtimeClasspath.get().files` trong top-level build script chỉ để “xem thử” dependency: thao tác này có thể khiến configuration nặng và phá tính lazy.

## 9. Task được chọn nhưng action không chạy: UP-TO-DATE, FROM-CACHE, SKIPPED, NO-SOURCE

Các trạng thái thường thấy trong console không nên diễn giải thành “task không thuộc graph”.

| Trạng thái | Ý nghĩa thường gặp | Nên kiểm tra gì? |
| --- | --- | --- |
| `UP-TO-DATE` | Input, output và thông tin theo dõi đáp ứng điều kiện không cần chạy lại action | Đã khai báo inputs/outputs đúng chưa? File output còn nguyên? |
| `FROM-CACHE` | Gradle khôi phục kết quả từ build cache hợp lệ | Cache bật chưa, task có cacheable không, cache key gồm gì? |
| `NO-SOURCE` | Task xử lý nguồn nhưng không có source để làm | Source set/path đúng chưa, có mã nguồn/test không? |
| `SKIPPED` | Task bị bỏ qua do `onlyIf`, `enabled=false`, `--dry-run` hoặc lý do khác | Dùng `--info` để xem lý do, kiểm tra predicate |
| `FAILED` | Task action hoặc phần thực thi có lỗi | Xem task path, root cause, `--stacktrace`, `--info` |
| Không xuất hiện | Task không được đưa vào graph của lần chạy này, hoặc bị cấu hình/task selection khác loại bỏ | Xem task được yêu cầu và quan hệ `dependsOn` |

**Build cache** và **configuration cache** là hai tầng khác nhau:

- Build cache lưu/khôi phục **kết quả task** đủ điều kiện dựa trên inputs, implementation và điều kiện liên quan; tác động đến công việc ở execution.
- Configuration cache lưu/khôi phục **mô hình đã cấu hình, đồ thị task và trạng thái task** cho một lời gọi build phù hợp; tác động đến chi phí configuration.

Chạy để khảo sát hiệu năng (tùy Gradle/plugin có hỗ trợ):

```bash
gradle build --build-cache --configuration-cache
gradle build --build-cache --configuration-cache
```

Không kết luận “lần hai chắc chắn nhanh và toàn bộ task UP-TO-DATE”: build logic, input từ môi trường, plugin, task không cacheable hoặc cache incompatibility có thể làm kết quả khác nhau. Đọc log để biết cấu hình có được tái sử dụng và từng task có được skip/cache hay không.

## 10. Kiểm soát execution: onlyIf, enabled, failure và parallel

### 10.1. `onlyIf` và `enabled`

Task có thể được chọn vào graph nhưng action bị bỏ qua:

```kotlin
tasks.register("optionalReport") {
    val requested = providers.gradleProperty("withReport")
    onlyIf("requires -PwithReport") {
        requested.isPresent
    }
    doLast {
        println("report generated")
    }
}
```

`gradle optionalReport` thường báo `SKIPPED`; `gradle -q optionalReport -PwithReport` in `report generated`. Dùng `onlyIf` để kiểm tra điều kiện gần thời điểm task chạy, tránh logic kiểu “nếu chưa có file thì đăng ký task” dựa trên trạng thái filesystem tạm thời ở configuration.

`enabled = false` cũng ngăn thực thi action, nhưng **không tự xóa mọi prerequisite khỏi đồ thị**. Nếu muốn tắt cả một nhánh công việc, hãy tổ chức task selection hoặc dependency có điều kiện phù hợp; đừng nghĩ tắt một task luôn khiến tất cả dependency của nó biến mất.

### 10.2. Task lỗi và `--continue`

Mặc định Gradle dừng khi gặp failure và không thực thi các task không thể tiếp tục hợp lệ. Với:

```bash
gradle build --continue
```

Gradle cố thực thi các task khác **không phụ thuộc vào task đã thất bại**, nhằm thu thêm lỗi trong một lần build. Các dependent cần task thất bại vẫn không thể coi như đã thành công. `--continue` không biến build lỗi thành thành công và không bảo đảm mọi task còn lại sẽ chạy.

### 10.3. Thực thi song song

DAG định nghĩa **những ràng buộc bắt buộc**, không cam kết một thứ tự duy nhất cho các task độc lập. `--parallel` cho phép Gradle sử dụng thêm mức song song khi điều kiện cho phép; hiệu quả phụ thuộc phiên bản Gradle, configuration cache, cấu hình project, worker và task. Không nên lập trình task cùng sửa một file chung, dùng chung cổng cố định hoặc dựa vào output của task khác mà không khai báo dependency/input. Lỗi “lúc pass, lúc fail” khi bật parallel thường gợi ý thiếu dependency hoặc chia sẻ state không an toàn.

Thứ tự giữa `test` và `lint` nếu cả hai được chạy nhưng độc lập có thể thay đổi; hãy dùng `mustRunAfter` **chỉ khi** thứ tự thực sự cần, hoặc dùng `dependsOn` khi có quan hệ dữ liệu/công việc bắt buộc.

## 11. Cách đọc đồ thị task trên một project thực tế

Bắt đầu với Gradle Wrapper của repository để giữ Gradle version thống nhất. Các lệnh mẫu dưới đây dùng `./gradlew` (Windows: `gradlew.bat`).

| Cần biết | Lệnh | Giải thích |
| --- | --- | --- |
| Task nào có thể gọi? | `./gradlew tasks` | Liệt kê task theo nhóm thường thấy của project hiện tại. |
| Task nào nữa? | `./gradlew tasks --all` | Hiển thị thêm task; không phải đồ thị dependency của một build cụ thể. |
| Task này làm gì? | `./gradlew help --task bootJar` | Mô tả task nếu task đó tồn tại trong project/plugin hiện tại. |
| Lệnh build sẽ lên lịch task nào? | `./gradlew :app:build --dry-run` | Quan sát tập task của lời gọi này, không chạy action. |
| Theo dõi nguyên nhân skip/configuration? | `./gradlew :app:build --info` | Có thêm thông tin chọn task, inputs, skip và cache. |
| Cần stack trace khi lỗi? | `./gradlew :app:build --stacktrace` | Hiển thị exception chain. |
| Điều tra các module phụ thuộc? | `./gradlew :app:dependencies --configuration runtimeClasspath` | Quan sát dependency **thư viện**, không phải task DAG. |
| Kiểm tra compatibility config cache? | `./gradlew :app:build --configuration-cache` | Phát hiện task/build logic không tuân thủ yêu cầu cache. |

**`:app:build` là ví dụ path:** chỉ dùng khi có subproject tên `app`. Nếu project một module ở root, thay bằng `build`. Tương tự `bootJar` chỉ tồn tại khi plugin Spring Boot và Java phù hợp đã tạo task đó.

### Quy trình tìm nguyên nhân một task chạy “ngoài dự kiến”

1. Xác định chính xác **lệnh gọi và task path** (`:app:test` khác `:core:test`).
2. Chạy `--dry-run` với **cùng tập task CLI** để xem những task nào được chọn.
3. Đọc `dependsOn`, provider input/output và quan hệ task do plugin thêm; chỉ xem `mustRunAfter` không giải thích được vì sao task xuất hiện.
4. Chạy `--info` nếu task bị `UP-TO-DATE`, `SKIPPED` hay cache; xác định lý do thực tế.
5. Nếu task chạy thừa, tìm đoạn eager task creation, dependency không cần thiết hoặc task lifecycle “ôm” quá rộng. Nếu task không chạy mà file cần thiết chưa có, tìm output wiring/`dependsOn` bị thiếu.
6. Với failure khó tái hiện, thử clean, tắt parallel hoặc cache **chỉ như biện pháp khoanh vùng**, sau đó sửa nguyên nhân input/output/dependency thật sự. Đừng mặc định giải pháp là tắt cache vĩnh viễn.

## 12. Sai lầm phổ biến và cách sửa

**Sai lầm 1: “Mọi task trong `build.gradle` được chạy theo thứ tự khai báo.”** Không đúng. Build script tạo mô hình task, còn graph và các quan hệ quyết định thứ tự. Giải pháp: `dependsOn` hoặc producer/consumer provider, không dựa vào vị trí dòng.

**Sai lầm 2: “`mustRunAfter` sẽ làm task A chạy trước.”** Chỉ đúng về **thứ tự khi A đã ở trong graph**; nó không thêm A. Khi B thực sự cần artifact của A, dùng dependency.

**Sai lầm 3: “`task.dependsOn(foo)` chứng minh task foo thực thi action trong mọi build.”** Foo có thể ở graph nhưng `UP-TO-DATE`/`FROM-CACHE`/`SKIPPED`. Hãy kiểm tra output, input và trạng thái Gradle.

**Sai lầm 4: “Đặt công việc trong khối `tasks.register` cũng giống `doLast`.”** Cấu hình và thực thi là hai giai đoạn khác nhau. Công việc tạo file, chạy command hay gửi request phải nằm trong task action hoặc task type phù hợp.

**Sai lầm 5: “Đọc file trong task B bằng đường dẫn trùng output của A là đủ.”** Gradle không chắc suy ra producer nếu chỉ nhận một path rời rạc. Nối input B tới `TaskProvider`/output A và khai báo annotation đầu vào/đầu ra; sau đó dùng `--dry-run` kiểm tra producer thực sự được lên lịch.

**Sai lầm 6: “`tasks.getByName` và `tasks.register` có hiệu năng như nhau.”** Lấy task instance có thể realize task sớm, làm configuration chậm hoặc phá hiệu quả configuration avoidance. Ưu tiên `tasks.named` và `TaskProvider` khi chỉ cần khai báo quan hệ.

**Sai lầm 7: “`--dry-run` pass là code đã build/test đúng.”** Dry run không chạy action. Chỉ là phương pháp kiểm tra scheduling, phải có lần build/test thực để xác nhận artifact và hành vi.

**Sai lầm 8: “`--continue` sẽ bỏ qua lỗi để build thành công.”** Nó chỉ tiếp tục công việc độc lập khi có thể và vẫn báo failure. Dependency lỗi không được tự coi là đã sản xuất output hợp lệ.

**Sai lầm 9: “Build cache và configuration cache là một.”** Chúng cache hai tầng khác nhau; tối ưu một tầng không tự bảo đảm tầng kia. Đọc thông báo cache và sửa task có input/output thiếu hoặc truy cập trạng thái cấu hình sai.

**Sai lầm 10: “`:app:build` luôn gọi `:core:build` vì app phụ thuộc core.”** Trong multi-project Gradle, Gradle có thể chỉ cần những task tạo artifact cần thiết của core, không cần toàn bộ check/test/assemble ở core. Phải xem graph thực tế và variant dependency.

## 13. Checklist thiết kế task cho dự án Spring Boot

- **Đúng công việc:** xác định task là actionable (biên dịch, kiểm tra, đóng gói) hay lifecycle/aggregate (gom các task vào một điểm gọi).
- **Đúng đường dẫn:** dùng path `:module:task` khi có nhiều module; tránh tham chiếu nhầm task cùng tên ở root và subproject.
- **Đúng quan hệ:** dữ liệu bắt buộc → `dependsOn` hoặc provider output; sắp xếp có điều kiện → `mustRunAfter` / `shouldRunAfter`; dọn dẹp → `finalizedBy`.
- **Đúng dữ liệu:** khai báo `@Input`, `@InputFiles`, `@OutputFile`/`@OutputDirectory` và đặc tính path sensitivity khi có giá trị. Không giấu input trong biến môi trường hoặc đọc file ngoài phần đã khai báo.
- **Đúng lifecycle:** công việc có side effect ở execution task; cấu hình lazy bằng `tasks.register`/`named`.
- **Đúng khả năng tái lập:** task không dựa vào biến mutable dùng chung, thời gian hiện tại hay thứ tự ngẫu nhiên nếu không khai báo chúng như input thích hợp.
- **Đúng kiểm chứng:** dùng `--dry-run` xem graph, chạy build thật, quan sát task outcome qua `--info`; thử chạy lại để đánh giá incremental và cache.
- **Đúng môi trường:** ưu tiên Gradle Wrapper, kiểm tra version Gradle/JDK/plugin và đánh giá configuration cache trên repository thực tế.

## 14. Tài liệu chính thức

- Gradle User Manual – [Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html).
- Gradle User Manual – [Creating and Registering Tasks](https://docs.gradle.org/current/userguide/writing_tasks.html).
- Gradle User Manual – [Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html).
- Gradle User Manual – [Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html).
- Gradle User Manual – [Configuring Tasks Lazily](https://docs.gradle.org/current/userguide/lazy_configuration.html).
- Gradle User Manual – [Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html).
- Gradle User Manual – [Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html).
- Gradle API – [Task](https://docs.gradle.org/current/javadoc/org/gradle/api/Task.html).

**Cách hiểu cần giữ:** task là công việc, `dependsOn` và producer/consumer hình thành quan hệ công việc bắt buộc, các ordering API chỉ điều chỉnh trình tự khi thích hợp, còn graph là kế hoạch thực thi **riêng cho từng lần gọi Gradle**. Việc task có ở graph không đồng nghĩa action luôn chạy: Gradle còn kiểm tra đầu vào/đầu ra, skip, cache và điều kiện thực thi để quyết định phần việc thực sự cần làm.