# Đăng ký task bằng tasks.register và lấy tham chiếu bằng tasks.named trong Gradle

## 1. Vì sao Gradle có register và named?

Trong Gradle, **Task** là một công việc có thể được chọn chạy: biên dịch Java, kiểm thử, copy file, đóng gói hoặc in báo cáo. Một dự án nhiều module có thể có hàng trăm hay hàng nghìn task, nhưng khi chạy `./gradlew :app:test`, Gradle không cần cấu hình đầy đủ mọi task khác.

Hai API quan trọng để tránh công việc cấu hình không cần thiết là:

- **`tasks.register("name")`:** đăng ký **task mới** trong `TaskContainer` của project. Trả về `TaskProvider<Task>` hoặc `TaskProvider<T>` cho loại task cụ thể, cho phép Gradle trì hoãn tạo/cấu hình instance.
- **`tasks.named("name")`:** truy xuất **tham chiếu tới task đã tồn tại/đã đăng ký** trong container đó. Trả về `TaskProvider` để cấu hình thêm hoặc truyền cho API khác mà không bắt buộc hiện thực hóa task.
- **`TaskProvider<T>`:** một *lazy handle* (tham chiếu trì hoãn) tới task có kiểu `T`; dùng được với `dependsOn`, `configure` và nhiều API liên quan.

Điểm cần thuộc: **register = định nghĩa task mới; named = tìm task đã biết; cả hai trả provider, không phải chạy task ngay.** Đây là nền tảng của *Task Configuration Avoidance*, một thực hành được Gradle khuyến nghị.

Sau bài này, bạn có thể tự viết `tasks.register` cho task riêng, cấu hình task plugin cung cấp bằng `tasks.named`, nối task qua `TaskProvider`, hiểu việc nào chạy ở configuration và việc nào chạy ở execution, đồng thời tránh API tạo task sớm.

## 2. Mô hình Project → TaskContainer → TaskProvider → Task

Mỗi `Project` sở hữu một `TaskContainer`. Tên task là duy nhất **trong từng project**; hai project khác nhau có thể cùng có task `test`.

```text
Gradle build
├── Project :                       (root)
│   └── tasks: TaskContainer
│       ├── register("prepare")     → TaskProvider cho :prepare
│       └── named("prepare")        → provider của cùng :prepare
└── Project :app
    └── tasks: TaskContainer
        └── register("prepare")     → provider cho :app:prepare
```

Đường dẫn task (*task path*) bao gồm project path: `:prepare` khác `:app:prepare`. Khi gọi `tasks.named("prepare")` từ `app/build.gradle.kts`, API tra cứu trong task container của `:app`, không tự động tìm `:prepare` ở root.

Có ba mốc rất dễ bị lẫn:

1. **Registration:** Gradle ghi nhận tên, kiểu và configuration action của task; `TaskProvider` đã có thể được chuyền đi.
2. **Realization/configuration:** khi task thật sự cần, Gradle tạo Task instance và áp dụng các configuration action đã đăng ký.
3. **Execution:** khi task nằm trong đồ thị thực thi và đủ điều kiện chạy, Gradle gọi task actions như `doFirst`/`doLast` hoặc `@TaskAction`.

Một task có thể đã **realized** nhưng chưa hề được **executed**. Chạy `tasks --all` hoặc plugin khác truy cập task có thể gây realization; vì vậy không nên suy luận rằng task ngoài đồ thị chắc chắn chưa từng được cấu hình.

## 3. tasks.register: đăng ký task mới

### 3.1. Cú pháp Groovy DSL

Trong `build.gradle`:

```groovy
tasks.register('hello') {
    group = 'learning'
    description = 'In lời chào'

    doLast {
        println 'Hello from Gradle'
    }
}
```

Ở đây `'hello'` là tên task; `group` và `description` là metadata giúp dễ tìm trong `./gradlew tasks`; `doLast` gắn một action vào task.

### 3.2. Cú pháp Kotlin DSL

Trong `build.gradle.kts`:

```kotlin
tasks.register("hello") {
    group = "learning"
    description = "In lời chào"

    doLast {
        println("Hello from Gradle")
    }
}
```

Groovy cho phép dấu nháy đơn và gọi `println` bỏ ngoặc; Kotlin dùng chuỗi nháy kép và `println(...)`. Dù cách viết khác, Gradle API và ngữ nghĩa đăng ký task giống nhau.

Lệnh `./gradlew -q hello` (macOS/Linux) hoặc `gradlew.bat -q hello` (Windows) sẽ cho dòng stdout của task:

```text
Hello from Gradle
```

Để chạy, dự án phải có Gradle Wrapper và Gradle/JDK tương thích. Nếu làm từ một thư mục học tập chưa có wrapper, hãy dùng Gradle cài sẵn chạy `gradle wrapper` một lần tại root rồi sử dụng wrapper được tạo ra.

### 3.3. Kết quả trả về là TaskProvider

**Groovy:**

```groovy
def helloProvider = tasks.register('hello') {
    doLast { println 'Hello' }
}
```

**Kotlin:**

```kotlin
val helloProvider = tasks.register("hello") {
    doLast { println("Hello") }
}
```

`helloProvider` là **TaskProvider**, không phải Task instance được tạo ra ngay. Việc giữ provider giúp cấu hình và xây dựng đồ thị mà không cần ép task được hiện thực hóa.

**Không đăng ký trùng:** trong cùng Project, gọi `tasks.register("hello")` thêm lần nữa sẽ báo task cùng tên đã tồn tại. Nếu muốn bổ sung cấu hình, dùng `tasks.named("hello")` hoặc `helloProvider.configure { ... }`.

### 3.4. Task có loại cụ thể

Gradle cung cấp những task type như `Copy`, `Zip` và (với plugin liên quan) `JavaCompile`, `Test`.

**Groovy:**

```groovy
tasks.register('copyDocs', Copy) {
    from 'docs'
    into layout.buildDirectory.dir('copied-docs')
}
```

**Kotlin:**

```kotlin
tasks.register<Copy>("copyDocs") {
    from("docs")
    into(layout.buildDirectory.dir("copied-docs"))
}
```

Trong Groovy, `Copy` là tham số kiểu; trong Kotlin, `<Copy>` là tham số generic. Cả hai cho Gradle biết task này là task sao chép có các API `from` và `into`. `TaskProvider<Copy>` cung cấp tham chiếu có kiểu.

Ví dụ copy này là đoạn cấu hình; nếu thư mục `docs` không có file thì không có file đầu vào để chép. Khi xây task thật, khai báo inputs/outputs thích hợp để Gradle xét up-to-date và cache theo đúng task type.

## 4. tasks.named: lấy tham chiếu và cấu hình task đã có

Giả sử task `hello` đã được đăng ký:

**Groovy DSL:**

```groovy
tasks.register('hello') {
    doLast { println 'Hello' }
}

tasks.named('hello') {
    group = 'learning'
    description = 'Task đã có, được cấu hình bổ sung'
}
```

**Kotlin DSL:**

```kotlin
tasks.register("hello") {
    doLast { println("Hello") }
}

tasks.named("hello") {
    group = "learning"
    description = "Task đã có, được cấu hình bổ sung"
}
```

`tasks.named` **không tạo task mới**. Nó lấy một provider cho task tên `hello` và đăng ký configuration action. `group`/`description` được áp khi task cần hiện thực hóa. `named` không thực thi action `doLast`.

Bạn cũng có thể giữ provider rồi cấu hình:

**Groovy:**

```groovy
def hello = tasks.named('hello')
hello.configure {
    description = 'Được cấu hình qua TaskProvider'
}
```

**Kotlin:**

```kotlin
val hello = tasks.named("hello")
hello.configure {
    description = "Được cấu hình qua TaskProvider"
}
```

`named` cần **task đã được biết tới khi gọi lookup**. Nếu task không tồn tại, nó báo lỗi; không âm thầm tạo task mới và không tự chờ plugin chưa áp dụng. Khi muốn cấu hình task do plugin cung cấp, hãy áp dụng plugin phù hợp trước.

### 4.1. So sánh trực tiếp

| Mục đích | Sử dụng | Điều kiện và kết quả |
| --- | --- | --- |
| Tạo task `report` mới | `tasks.register("report")` | Tên chưa tồn tại; trả `TaskProvider`. |
| Cấu hình task `report` đã được đăng ký | `tasks.named("report") { ... }` | Task phải tồn tại; không tạo task mới. |
| Cấu hình task plugin `test` | `tasks.named<Test>("test") { ... }` (Kotlin) | Plugin cung cấp task `test` và loại đúng. |
| Lấy task vừa đăng ký để kết nối task khác | Giữ provider do `register` trả về | Không cần tra cứu tên lại. |
| Lấy Task instance vì API thật sự yêu cầu | `tasks.named("report").get()` | Có thể buộc realization; tránh khi không cần. |

### 4.2. named nhiều lần vẫn cấu hình cùng task

**Kotlin:**

```kotlin
tasks.register("greet") {
    doLast { println("Hello Earth") }
}

tasks.named("greet") {
    doFirst { println("Hello Venus") }
}

tasks.named("greet") {
    doLast { println("Hello Mars") }
}

tasks.named("greet") {
    doLast { println("Hello Jupiter") }
}
```

Khi chạy `./gradlew -q greet`, các action cho stdout:

```text
Hello Venus
Hello Earth
Hello Mars
Hello Jupiter
```

`doFirst` đưa action lên trước; `doLast` bổ sung vào cuối danh sách action. Những lệnh `named` ở đây bổ sung cấu hình cho cùng task đã đăng ký; chúng không chạy task khi được gọi.

## 5. Configuration avoidance: lazy thật sự nghĩa là gì?

API cũ như `tasks.create("x")` hoặc cú pháp Groovy `task x { ... }` tạo task sớm (*eager*) ngay trong quá trình cấu hình. Trong build lớn, điều đó khiến Gradle tốn công tạo/configure cả những task không được chạy.

`register` trì hoãn việc khởi tạo instance tới khi Task được yêu cầu. Những tình huống thường khiến task phải realized là người dùng chọn task, một task mạnh phụ thuộc nó trong graph, hoặc build logic gọi API cần Task instance như `get()`/`getByName()`.

```text
Gradle đánh giá build script
    |
    +--> tasks.register("a")  ----> TaskProvider a
    +--> tasks.register("b")  ----> TaskProvider b
    +--> tasks.named("a")     ----> cùng provider của a
    |
Người dùng yêu cầu: ./gradlew a
    |
    +--> Gradle tính graph và realization các task cần thiết
    +--> Cấu hình a
    +--> Thực thi action a nếu đủ điều kiện
    |
    +--> b có thể vẫn chưa realized
```

**“Có thể” rất quan trọng:** plugin hoặc API eager khác vẫn có thể khiến `b` realized. Cơ chế configuration avoidance giảm công việc không cần thiết, không đảm bảo tất cả task không chạy đều chưa được tạo.

### 5.1. Configuration action khác execution action

**Kotlin DSL:**

```kotlin
tasks.register("probe") {
    println("CONFIGURE probe")

    doLast {
        println("EXECUTE probe")
    }
}
```

**Groovy DSL:**

```groovy
tasks.register('probe') {
    println 'CONFIGURE probe'

    doLast {
        println 'EXECUTE probe'
    }
}
```

- `println("CONFIGURE probe")` nằm trong cấu hình task; chạy khi Gradle hiện thực hóa/cấu hình task, **không nhất thiết** ngay khi đọc câu lệnh `register`.
- `println("EXECUTE probe")` nằm trong `doLast`; chỉ chạy khi action được thực thi.
- Gọi `tasks.named("probe")` không tự chạy hai dòng `println`.
- Gọi `tasks.named("probe").get()` yêu cầu Task instance, có thể khiến dòng `CONFIGURE` chạy, nhưng **không** chạy action `EXECUTE`.

Trong ví dụ tối giản, `./gradlew -q probe` in `CONFIGURE probe` và `EXECUTE probe` theo thứ tự. Đừng đặt thao tác nghiệp vụ như ghi file/gọi mạng vào configuration action chỉ vì Gradle cho phép gọi mã ở đó.

### 5.2. Vì sao tránh .get()?

`TaskProvider.get()` trả Task instance, nên dùng nó có thể làm task realized sớm. Các API như `dependsOn` có thể tiếp nhận provider trực tiếp, vì vậy thường **không cần** `.get()`.

Ví dụ nên tránh nếu mục tiêu chỉ là liên kết phụ thuộc:

```kotlin
val compile = tasks.register("prepare")
tasks.register("report") {
    dependsOn(compile.get())    // Buộc lấy instance của prepare
}
```

Viết đúng theo provider:

```kotlin
val prepare = tasks.register("prepare")
tasks.register("report") {
    dependsOn(prepare)
}
```

Khi thực sự cần Task instance cho một API chỉ chấp nhận Task, `.get()` vẫn hợp lệ; hãy hiểu chi phí realization và không gọi nó như bước bắt buộc sau `register` hoặc `named`.

## 6. Ví dụ hoàn chỉnh Groovy/Kotlin chạy được

Bài tập sử dụng **base plugin** có sẵn trong Gradle, không cần dependency tải từ bên ngoài. Chỉ dùng **một** trong hai file build theo DSL chọn; không để `build.gradle` và `build.gradle.kts` cùng làm hai bản cấu hình active trong một project.

### 6.1. Tên project trong settings

Nếu chọn Groovy, tạo `settings.gradle`:

```groovy
rootProject.name = 'task-provider-lab'
```

Nếu chọn Kotlin, tạo `settings.gradle.kts`:

```kotlin
rootProject.name = "task-provider-lab"
```

### 6.2. Cấu hình Groovy — build.gradle

```groovy
plugins {
    id 'base'
}

// Đăng ký một task và giữ TaskProvider.
def prepareData = tasks.register('prepareData') {
    group = 'learning'
    description = 'Chuẩn bị dữ liệu'
    doLast {
        println 'prepareData: ready'
    }
}

// Task này sẽ cần prepareData trước khi chạy.
tasks.register('showReport') {
    group = 'learning'
    dependsOn prepareData
    doLast {
        println 'showReport: done'
    }
}

// Tìm TaskProvider của showReport để cấu hình bổ sung.
tasks.named('showReport') {
    description = 'In báo cáo sau bước chuẩn bị'
    doFirst {
        println 'showReport: start'
    }
}

// Một task không nằm trong đồ thị của showReport.
tasks.register('unusedTask') {
    group = 'learning'
    doLast {
        println 'unusedTask: executed'
    }
}
```

### 6.3. Cấu hình Kotlin — build.gradle.kts

```kotlin
plugins {
    id("base")
}

val prepareData = tasks.register("prepareData") {
    group = "learning"
    description = "Chuẩn bị dữ liệu"
    doLast {
        println("prepareData: ready")
    }
}

tasks.register("showReport") {
    group = "learning"
    dependsOn(prepareData)
    doLast {
        println("showReport: done")
    }
}

tasks.named("showReport") {
    description = "In báo cáo sau bước chuẩn bị"
    doFirst {
        println("showReport: start")
    }
}

tasks.register("unusedTask") {
    group = "learning"
    doLast {
        println("unusedTask: executed")
    }
}
```

### 6.4. Chạy và đọc stdout

Tại thư mục project có Gradle Wrapper:

```bash
./gradlew -q showReport
```

Stdout do các task action in ra **theo đúng thứ tự**:

```text
prepareData: ready
showReport: start
showReport: done
```

Giải thích:

1. Task `showReport` có `dependsOn(prepareData)`. Vì vậy Gradle phải thực thi `prepareData` trước `showReport`.
2. `doFirst` của `showReport` in `showReport: start` trước `doLast` in `showReport: done`.
3. `unusedTask` đã đăng ký, nhưng không được chọn và không là dependency của `showReport`, nên action của nó không xuất hiện.

Bạn có thể tự kiểm chứng:

```bash
./gradlew tasks --all
./gradlew showReport --dry-run
./gradlew -q unusedTask
```

`tasks --all` liệt kê task và mô tả (nếu có). `--dry-run` cho biết task nào được chọn trong graph nhưng **không chạy task actions**; do đó không mong thấy ba dòng action output khi dùng `--dry-run`. Lệnh cuối in `unusedTask: executed`. Dòng trạng thái do Gradle tự in có thể khác theo phiên bản và cờ log, còn stdout hành vi của ví dụ được giải thích ở trên.

Nếu trên Windows, dùng `gradlew.bat` thay `./gradlew`. Nếu đang ở thư mục mới chưa có Wrapper, chạy `gradle wrapper` bằng Gradle cài sẵn trước.

**Giới hạn ví dụ:** các task này chỉ in chữ; chúng không định nghĩa file đầu vào/đầu ra. Không suy luận chúng tự có incremental build, up-to-date check hoặc build cache giống task biên dịch thực tế.

## 7. Kết nối task bằng TaskProvider: hiểu đúng task graph

### 7.1. Liên kết với provider giữ từ register

**Groovy DSL:**

```groovy
def generate = tasks.register('generate') {
    doLast { println 'generate' }
}

tasks.register('publishResult') {
    dependsOn generate
    doLast { println 'publishResult' }
}
```

**Kotlin DSL:**

```kotlin
val generate = tasks.register("generate") {
    doLast { println("generate") }
}

tasks.register("publishResult") {
    dependsOn(generate)
    doLast { println("publishResult") }
}
```

Khi chạy `publishResult`, action của `generate` đi trước. Provider giúp Gradle biết task dependency mà không bắt người dùng phải gọi `generate.get()`.

### 7.2. Lấy provider bằng named rồi dependsOn

Nếu `generate` đã được đăng ký ở một nơi khác của cùng project:

```kotlin
tasks.register("publishResult") {
    dependsOn(tasks.named("generate"))
    doLast {
        println("publishResult")
    }
}
```

`named` tìm task đã có. Nếu task không tồn tại, lookup có thể lỗi; đừng dùng `register("generate")` lần thứ hai để che lỗi. Với code cùng scope, ưu tiên dùng biến provider từ `register`, tránh phụ thuộc vào string tên.

### 7.3. Quan hệ mạnh và mềm

| API | Ý nghĩa đối với task graph |
| --- | --- |
| `dependsOn(otherProvider)` | Chọn task kia làm prerequisite và thực thi trước task hiện tại. |
| `finalizedBy(otherProvider)` | Gắn finalizer task cần chạy sau task hiện tại theo quy tắc Gradle. |
| `mustRunAfter(otherProvider)` | Áp thứ tự khi cả hai task được chọn; **không tự kéo** task kia vào graph. |
| `shouldRunAfter(otherProvider)` | Gợi ý thứ tự yếu hơn, cũng không tự kéo task khác vào graph. |

Quan hệ thứ tự là nội dung **Task graph**. Chúng khác khai báo thư viện ở `dependencies { implementation(project(":core")) }`, vốn mô tả **software dependency/classpath**. Với project Java sử dụng code từ project khác, cần khai báo project dependency phù hợp, không thay bằng `dependsOn(":core:build")` một cách máy móc.

## 8. Tránh lỗi cấu hình task khác bên trong configuration action

Một rủi ro đặc trưng của lazy API là configuration action có thể chạy ngay, chạy muộn hoặc không chạy trong lần build đó. Vì vậy **chỉ sửa task đang được cấu hình trong action của nó**, không sửa task khác từ closure của task này.

**Kotlin — cách dễ sai:**

```kotlin
val check = tasks.register("checkCustom")

tasks.register("verifyCustom") {
    // Đang cấu hình verifyCustom nhưng lại sửa checkCustom.
    check.get().dependsOn(this)
}
```

Đoạn trên vừa ép hiện thực hóa `checkCustom` bằng `get()`, vừa chỉ thiết lập dependency khi `verifyCustom` được realized. Nếu chạy `checkCustom` trước khi `verifyCustom` cần được realized, cấu hình quan hệ không như mong đợi.

**Kotlin — cách đúng:**

```kotlin
val verify = tasks.register("verifyCustom") {
    doLast {
        println("verifyCustom")
    }
}

tasks.register("checkCustom") {
    dependsOn(verify)
}
```

Nếu `checkCustom` đã đăng ký trước:

```kotlin
val check = tasks.register("checkCustom")
val verify = tasks.register("verifyCustom")

check.configure {
    dependsOn(verify)
}
```

Trong Groovy, `check.configure { dependsOn verify }` cũng tương tự. **Chỉ cấu hình task mà closure hiện tại thuộc về** là nguyên tắc quan trọng để build có kết quả dự đoán được.

## 9. named với task plugin đã tạo và task có kiểu

Nhiều plugin tạo task tự động. Ví dụ Java plugin cung cấp task `test`, `compileJava`, `jar`. Nếu chỉ muốn cấu hình task `test`, hãy dùng `named`, không gọi `register("test")` trùng tên.

**Groovy DSL:**

```groovy
plugins {
    id 'java'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Kotlin DSL:**

```kotlin
import org.gradle.api.tasks.testing.Test

plugins {
    id("java")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
```

Ở đây `Test` là type của task test. Với Kotlin, dạng `tasks.named<Test>("test")` giúp compiler nhận phương thức `useJUnitPlatform()` trên `Test`. Mẫu này là **cấu hình**, chưa phải chương trình test đầy đủ: muốn chạy test thật cần source test và dependency/runtime engine tương ứng.

Nếu task/plugin chưa tồn tại tại thời điểm gọi `named`, bạn sẽ gặp lỗi. Hãy áp dụng plugin đúng project trước khi tra cứu task. Kotlin DSL cũng có thể cung cấp accessor như `tasks.test { ... }` nếu plugin và schema cho phép, nhưng `named<Test>` thể hiện rõ logic tra cứu theo tên và kiểu.

### Cấu hình cả nhóm task: withType + configureEach

Nếu muốn mọi JavaCompile task dùng UTF-8:

**Groovy DSL:**

```groovy
plugins {
    id 'java'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

**Kotlin DSL:**

```kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id("java")
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
```

`tasks.named("compileJava")` nhắm **một task cụ thể**; `tasks.withType<JavaCompile>().configureEach` áp dụng cho **các task có type tương ứng** theo cách trì hoãn. Tránh `tasks.all { ... }` và dạng callback eager của `withType(...) { ... }` nếu mục tiêu là giữ configuration avoidance.

## 10. Phân biệt lazy và eager API khi đọc build cũ

| API | Hiệu ứng điển hình | Khuyến nghị |
| --- | --- | --- |
| `tasks.register("x")` | Đăng ký task mới, trả provider. | Ưu tiên khi tạo task. |
| `tasks.named("x")` | Lấy provider của task đã có. | Ưu tiên khi tham chiếu/cấu hình task. |
| `task("x")` hoặc Groovy `task x` | Cách tạo task cũ, thường eager. | Đổi sang `register` khi phù hợp. |
| `tasks.create("x")` | Tạo và cấu hình task sớm. | Tránh trong cấu hình bình thường. |
| `tasks.getByName("x")` | Lấy instance task, có thể gây realization. | Dùng `named` nếu chỉ cần tham chiếu. |
| `tasks.findByName("x")` | Lookup instance, cũng có thể khiến task realized. | Cân nhắc API lazy hoặc kiểm tra plugin. |
| `tasks.named("x").get()` | Ép TaskProvider cấp Task instance. | Chỉ dùng khi API thật sự đòi instance. |
| `tasks.withType(Type).configureEach { ... }` | Cấu hình từng task cùng type khi cần. | Ưu tiên khi cấu hình nhóm. |
| `tasks.all { ... }` | Có thể hiện thực hóa/configure mọi task đã đăng ký. | Đổi sang `configureEach` khi phù hợp. |

Khi sửa build script cũ, chỉ thay `create` bằng `register` có thể **chưa đủ**: nếu phần còn lại vẫn gọi `getByName`, `all` hoặc lấy instance sớm, nhiều task vẫn bị realized. Hiệu quả đến từ cả đường đi **tạo → tham chiếu → cấu hình → liên kết** đều dùng API phù hợp.

## 11. Task path trong multi-project build

Giả sử `settings.gradle`:

```groovy
rootProject.name = 'demo'
include 'core', 'app'
```

Trong `core/build.gradle`, `tasks.register('prepare')` tạo task `:core:prepare`. Trong `app/build.gradle`, cùng tên `tasks.register('prepare')` lại tạo task `:app:prepare`.

```bash
./gradlew :core:prepare
./gradlew :app:prepare
```

Đây là hai lệnh gọi hai task khác nhau. `tasks.named("prepare")` trong `app/build.gradle.kts` sẽ nhìn vào task container của `:app`. Khi báo lỗi `Task with name ... not found`, hãy xác nhận **tên task và Project chứa task** trước khi tạo thêm một task trùng nhiệm vụ.

Quan hệ giữa project cần dựa vào artifact/producer task đúng ngữ cảnh. Ví dụ `implementation(project(":core"))` của Java plugin cho phép Gradle chọn artifact/producer cần thiết; nó giải quyết vấn đề khác với việc “đảm bảo `:core:build` chạy trước `:app:build`” một cách thủ công. Chỉ tạo quan hệ task xuyên project nếu yêu cầu công việc thực sự đòi hỏi.

## 12. Lệnh quan sát và kiểm tra thực hành

Với ví dụ mục 6:

```bash
./gradlew help
./gradlew tasks --all
./gradlew showReport --dry-run
./gradlew -q showReport
./gradlew -q unusedTask
```

Cách đọc kết quả:

- `help` thường là một phép thử tốt để phát hiện build logic cấu hình task không liên quan, nhưng không phải bằng chứng chắc chắn rằng không có task nào realized.
- `tasks --all` cho thấy task được biết đến và giúp kiểm tra tên/nhóm/mô tả; bản thân lệnh liệt kê task có thể ảnh hưởng đến realization tùy cơ chế Gradle.
- `--dry-run` thể hiện graph dự kiến, **không thực thi task actions**. Configuration action vẫn có thể chạy trong quá trình Gradle tính graph.
- `-q showReport` chạy thật với log Gradle gọn, cho stdout ba dòng ở mục 6.
- `-q unusedTask` chạy task không phụ thuộc vào `showReport` và in `unusedTask: executed`.

Để đo **số task realized** và xác định code nào ép realization trong dự án lớn, dùng công cụ phân tích cấu hình/Build Scan khi môi trường cho phép. So sánh với baseline; đừng dựa chỉ vào số dòng log hay thời gian một lần chạy ngẫu nhiên.

## 13. Những lỗi thường gặp và cách xử lý

| Lỗi / hiện tượng | Vì sao xảy ra | Cách khắc phục |
| --- | --- | --- |
| `Cannot add task 'x' ... already exists` | Gọi `register("x")` với tên đã tồn tại. | Dùng `named("x")` để cấu hình, không đăng ký lần hai. |
| `Task with name 'x' not found` | `named` chạy khi task chưa được đăng ký, sai plugin hoặc project. | Kiểm tra thứ tự apply plugin, tên task và `:module:tasks --all`. |
| `Unresolved reference: useJUnitPlatform` | Kotlin đang nhìn task như `Task` chung. | Dùng `tasks.named<Test>("test")` và import `Test`. |
| Task được cấu hình khi chạy `help` | `get()`, `create`, `getByName`, `all` hoặc plugin query eager. | Giữ provider, dùng `register`/`named`/`configureEach`. |
| Task action không chạy với `--dry-run` | Dry-run chỉ dựng graph. | Chạy task thật và kiểm tra stdout/artifact. |
| `println` chạy khi tính graph | Nó ở configuration closure, không trong `doLast`. | Đặt công việc thực thi trong action/Task type. |
| `checkCustom` thiếu dependency của `verifyCustom` | Chỉnh task check trong config action của task verify chưa realized. | Cấu hình quan hệ trên chính check bằng `dependsOn(verifyProvider)`. |
| Task ở sai module | Tên giống nhau nhưng `TaskContainer` khác nhau. | Xác nhận `:core:task` và `:app:task`. |
| Tưởng `dependsOn` là dependency thư viện | Task graph khác software classpath dependency. | Dùng `dependencies` với plugin/configuration phù hợp. |
| Task không có `UP-TO-DATE` | Task tùy biến không khai báo input/output phù hợp. | Dùng task type và khai báo input/output, kiểm tra cơ chế cache. |
| `register` dùng rồi vẫn chậm | Phần khác của build ép task realized sớm. | Rà soát `getByName`, `.get()`, `tasks.all`, callback eager và plugin. |

## 14. Checklist để viết task đúng

1. **Task mới hay có sẵn?** Mới thì `register`, đã tồn tại thì `named`.
2. **Thuộc Project nào?** Xác định task path và nơi đăng ký plugin.
3. **Loại Task nào?** Dùng `register<Copy>` / `named<Test>` trong Kotlin khi cần API riêng của type.
4. **Task có dependency nào?** Truyền provider vào `dependsOn`/các API phù hợp; hạn chế `.get()`.
5. **Cấu hình hay thực thi?** `group`/`description` trong configuration; xử lý thật trong `doLast`/task action.
6. **Có đang sửa task khác trong configuration action?** Di chuyển logic sang configuration action của chính task cần thay đổi.
7. **Cấu hình một hay nhiều task?** `named` cho task cụ thể; `withType(...).configureEach` cho nhóm.
8. **Đã kiểm tra graph và action?** Chạy `tasks --all`, `--dry-run` rồi task thật. Với task tạo artifact, kiểm tra input/output, test và cache nếu có.

**Ghi nhớ:** `register` trả **TaskProvider cho một task mới**, `named` trả **TaskProvider cho task đã có**. Việc sử dụng provider xuyên suốt quá trình cấu hình/định nghĩa quan hệ giúp Gradle tránh tạo và cấu hình task không cần thiết, trong khi các action vẫn được thực thi đúng theo đồ thị task khi người dùng yêu cầu.

### Tài liệu chính thức

- [Gradle — Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html) — cơ chế configuration avoidance và các API lazy/eager.
- [Gradle — Creating and Registering Tasks](https://docs.gradle.org/current/userguide/writing_tasks.html) — ví dụ register, named và task action.
- [Gradle — TaskContainer API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/TaskContainer.html) — chữ ký, kiểu trả về và lỗi khi trùng tên.
- [Gradle — Task Configuration Avoidance Migration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html#sec:task_configuration_avoidance_migration) — cách chuyển từ tạo/cấu hình eager sang dùng provider.
