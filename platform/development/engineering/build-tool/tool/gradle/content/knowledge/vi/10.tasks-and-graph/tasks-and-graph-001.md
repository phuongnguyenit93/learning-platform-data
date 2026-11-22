# Task có hành động và lifecycle task dùng để nhóm công việc trong Gradle

## 1. Mục tiêu: phân biệt “làm việc” với “điều phối việc”

Một build Gradle có thể chứa hàng chục hoặc hàng nghìn task. Khi nhập `./gradlew build`, Gradle không chạy một khối lệnh khổng lồ có tên `build`: nó tìm **task được yêu cầu**, mở rộng các quan hệ phụ thuộc thành **đồ thị task** rồi chạy những task cần thiết theo thứ tự hợp lệ.

Có hai vai trò quan trọng:

- **Actionable task (task có hành động):** thực sự thực hiện một công việc như tạo file, biên dịch Java, chạy test, kiểm tra định dạng, đóng gói JAR. Công việc có thể do action `doFirst`/`doLast`, method có annotation `@TaskAction`, hoặc implementation của task type/plugin cung cấp.
- **Lifecycle task (task vòng đời/điều phối):** có ý nghĩa như một **điểm vào nhóm công việc**, thông thường **không có action của chính nó**. Task này dùng `dependsOn` để yêu cầu những task khác. Ví dụ Base plugin cung cấp `check`, `assemble`, `build`.

**Điều cần nhớ:** hai loại trên là **cách phân loại theo vai trò**, không phải hai lớp Java/Groovy hoàn toàn tách biệt. Một `Task` có thể có không hoặc nhiều action; nếu bạn gắn `doLast` vào một lifecycle task, nó đã có action và không còn là lifecycle task thuần túy. Việc đặt tên task `buildAll` không tự làm nó thành task điều phối.

Sau bài học, bạn sẽ biết tạo task có action, tạo task gom việc, đọc quan hệ `dependsOn`, phân biệt dependency với ordering, sử dụng task provider để cấu hình lazy và kết nối output/verification vào các lifecycle task chuẩn.

**Bối cảnh:** ví dụ dùng **Gradle Groovy DSL** (`build.gradle`), chạy với Gradle Wrapper. Trên Linux/macOS: `./gradlew`. Trên Windows PowerShell: `.\gradlew.bat`. Các task demo thuần Groovy không cần source Java; phần liên hệ với Java plugin dùng Java 17+.

## 2. Task có những thành phần nào?

Một task có thể có:

| Thành phần | Tác dụng |
| --- | --- |
| **Identity** | Tên `name` và đường dẫn `path` như `:verifyCode` hoặc `:app:test` |
| **Type** | Ví dụ `DefaultTask`, `Test`, `JavaCompile`, `Jar`, `Copy`, `Delete`; type có thể cung cấp hành vi |
| **Configuration** | `group`, `description`, input/output, điều kiện chạy, quan hệ với task khác |
| **Actions** | Công việc chạy ở execution phase, ví dụ closure `doLast` hoặc method `@TaskAction` |
| **Dependencies** | Những task **phải hoàn thành trước** task này, khai báo qua `dependsOn` hoặc quan hệ input/output do Gradle suy ra |
| **Ordering/finalization** | `mustRunAfter`, `shouldRunAfter`, `finalizedBy`; mỗi cơ chế có ý nghĩa riêng |

Đọc đoạn mã sau:

~~~groovy
tasks.register('hello') {
    group = 'demo'
    description = 'In lời chào khi chạy task'

    doLast {
        println 'Xin chào từ task hello'
    }
}
~~~

- `tasks.register('hello')` **đăng ký task lazily** và trả một `TaskProvider`.
- `group` và `description` là **cấu hình** để task dễ tìm qua `tasks`.
- `doLast { ... }` gắn **action**; mã `println` chạy **khi task thực thi**, không phải ngay lúc Gradle đọc mọi dòng trong script.
- `./gradlew hello --quiet` in đúng một dòng từ action:

~~~text
Xin chào từ task hello
~~~

Một task đăng ký như sau lại là task **không có action của riêng nó**:

~~~groovy
tasks.register('allChecks') {
    group = 'verification'
    description = 'Điểm vào nhóm kiểm tra'
    dependsOn tasks.named('hello')
}
~~~

`allChecks` yêu cầu `hello` chạy nhưng tự nó không in gì. Tên `allChecks` là ví dụ, không có tác dụng đặc biệt nếu bạn không khai báo quan hệ. Trong phần này, `hello` phải được đăng ký trước để `tasks.named('hello')` tìm thấy.

## 3. Action là gì? `doFirst`, `doLast`, `@TaskAction`

### 3.1. Action chạy ở execution phase

Trong Groovy DSL, hai cách phổ biến để thêm action vào một task là:

~~~groovy
tasks.register('actionOrder') {
    doLast {
        println 'last-A'
    }
    doFirst {
        println 'first-A'
    }
    doFirst {
        println 'first-B'
    }
    doLast {
        println 'last-B'
    }
}
~~~

Chạy:

~~~bash
./gradlew actionOrder --quiet
~~~

**Stdout từ task:**

~~~text
first-B
first-A
last-A
last-B
~~~

`doFirst` chèn action vào **đầu** chuỗi action, nên khi gọi hai lần, action `first-B` được chèn phía trước `first-A`. `doLast` nối action vào **cuối**, vì vậy `last-A` chạy trước `last-B`.

Đây là thứ tự **các action trong cùng một task**. Đừng áp quy tắc đó để suy diễn thứ tự giữa những task độc lập: thứ tự task phụ thuộc vào **task graph**.

### 3.2. Action trong task type

Các plugin thường cung cấp task type đã có hành vi, chẳng hạn `JavaCompile` (biên dịch Java), `Test` (chạy test), `Jar` (tạo JAR), `Copy` (sao chép file). Khi viết custom task type, bạn có thể định nghĩa method `@TaskAction` thay vì chỉ gắn `doLast`.

Ví dụ lớp minh họa cách viết custom task type (được sử dụng đầy đủ ở phần 7):

~~~groovy
abstract class PrintMessage extends DefaultTask {
    @Input
    abstract Property<String> getMessage()

    @TaskAction
    void printIt() {
        println message.get()
    }
}
~~~

Đoạn này là **một phần script**; nó cần import `DefaultTask`, `Property`, `Input`, `TaskAction` và đăng ký một instance task ở phần khác. `@Input` khai báo dữ liệu ảnh hưởng kết quả; `@TaskAction` đánh dấu method chạy khi task thực thi. Một task type có thể chứa nhiều action, nhưng chỉ nên thêm những action thực sự thuộc cùng một đơn vị công việc.

### 3.3. Lỗi thường gặp: đặt side effect trong cấu hình

Ví dụ **không nên viết** nếu bạn chỉ muốn tạo file lúc chạy task:

~~~groovy
tasks.register('wrongWrite') {
    def file = layout.buildDirectory.file('wrong.txt').get().asFile
    file.parentFile.mkdirs()
    file.text = 'wrong phase'
}
~~~

Mã ghi file nằm trong **configuration closure** của task. Nó có thể chạy khi task được realize/configure, không nhất thiết khi task `wrongWrite` được thực thi. Với task registration lazy, lúc nó chạy càng khó đoán nếu bạn dựa vào nó như action.

Hướng đúng:

~~~groovy
def outputFile = layout.buildDirectory.file('demo/correct.txt')

tasks.register('writeFile') {
    outputs.file(outputFile)

    doLast {
        def target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.setText('Đúng thời điểm\n', 'UTF-8')
        println 'wrote=' + target.name
    }
}
~~~

`outputs.file` giúp Gradle biết output của task. Ví dụ này dùng closure để học điểm khác nhau giữa configuration/action; với task sản xuất file dùng lại nhiều lần, phần 7 minh họa cách mạnh hơn: **typed task properties + `@Input`/`@OutputFile` + `@TaskAction`**.

## 4. Lifecycle task: gom công việc mà không tự làm việc

Một lifecycle task hợp lý chỉ mô tả **cái gì phải hoàn tất** trước khi một mốc được coi là đạt. Ví dụ:

~~~text
                      releaseReady
                      /          \
                 packageApp    qualityGate
                     |              |
                 makeArchive      runChecks

(actionable)          ^              ^
                       \____________/
                       lifecycle tasks gom các nhánh công việc
~~~

Sơ đồ chỉ để minh họa: tên `releaseReady`, `packageApp`, `qualityGate` là do tác giả build đặt; chúng không tự có trong Gradle. Nếu bạn muốn `releaseReady` gom các nhánh công việc, hãy tạo quan hệ `dependsOn`.

Các lợi ích:
- **Một lệnh ổn định** cho người học hoặc CI: `./gradlew releaseReady`.
- Không buộc người chạy nhớ thứ tự hàng loạt lệnh shell.
- Cho phép bổ sung plugin/task mới vào nhóm mà không thay giao diện chính.
- Tận dụng cơ chế Gradle để chỉ thực thi task cần thiết và dùng lại output khi hợp lệ.
- Có thể tách mốc kiểm tra (`check`) với mốc tạo sản phẩm (`assemble`).

**Lưu ý:** lifecycle task không đảm bảo tất cả công việc liên quan tự xuất hiện. Nếu quên gắn một kiểm tra vào `check`, `./gradlew check` vẫn có thể báo thành công dù kiểm tra đó không chạy.

## 5. Phòng thực hành 1: tự tạo task có action và task gom việc

Bài này **chạy được độc lập** với Base plugin, không cần Java source hoặc dependency ngoài.

### 5.1. Cấu trúc

~~~text
task-graph-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Nếu chưa có Wrapper, dùng một bản Gradle đã cài để chạy `gradle wrapper` một lần, rồi giữ các tệp Wrapper trong repository.

**`settings.gradle`:**

~~~groovy
rootProject.name = 'task-graph-lab'
~~~

**`build.gradle` (toàn bộ file):**

~~~groovy
plugins {
    id 'base'
}

def prepareTask = tasks.register('prepareMessage') {
    group = 'lab'
    description = 'Chuẩn bị trước xử lý'

    doLast {
        println '1. prepare'
    }
}

def processTask = tasks.register('processMessage') {
    group = 'lab'
    description = 'Xử lý sau prepareMessage'
    dependsOn prepareTask

    doFirst {
        println '2. process starts'
    }
    doLast {
        println '3. process completes'
    }
}

def verifyTask = tasks.register('verifyMessage') {
    group = 'verification'
    description = 'Xác minh sau processMessage'
    dependsOn processTask

    doLast {
        println '4. verify'
    }
}

tasks.register('lessonPipeline') {
    group = 'lab'
    description = 'Task gom prepare, process và verify'
    dependsOn verifyTask
}
~~~

### 5.2. Chạy và hiểu kết quả

~~~bash
./gradlew tasks
./gradlew lessonPipeline --dry-run
./gradlew lessonPipeline --quiet
~~~

Khi chạy `lessonPipeline --quiet`, các dòng **stdout của những action** là:

~~~text
1. prepare
2. process starts
3. process completes
4. verify
~~~

Đây là output do script in; Gradle có thể có log khác nếu bạn bỏ `--quiet`.

Giải thích từng quan hệ:

~~~text
:lessonPipeline
      |
      v dependsOn
:verifyMessage     (action: "4. verify")
      |
      v dependsOn
:processMessage    (actions: "2. process starts" và "3. process completes")
      |
      v dependsOn
:prepareMessage    (action: "1. prepare")
~~~

Mũi tên biểu thị **“task ở trên phụ thuộc task ở dưới”**. Gradle chạy theo thứ tự **ngược chiều từ lá lên**: chuẩn bị → xử lý → xác minh → lifecycle task kết thúc.

`lessonPipeline` không có `doLast` nên **không có stdout riêng**. `--dry-run` chỉ lập danh sách task và có thể hiện trạng thái `SKIPPED` do mô phỏng; nó **không chạy action**, nên không in các dòng `1. prepare`...`4. verify`.

**Tự thay đổi:** Thêm một task `documentMessage` có `doLast`, rồi gắn nó vào `lessonPipeline` bằng `dependsOn`. Nếu `documentMessage` không phụ thuộc `verifyMessage`, đừng viết đáp án dựa vào một thứ tự log duy nhất: hai nhánh độc lập không có thứ tự bắt buộc.

## 6. Đọc đồ thị: dependency khác ordering và finalization

### 6.1. `dependsOn`: yêu cầu một task khác được chạy

~~~groovy
def taskA = tasks.register('taskA') {
    doLast { println 'A' }
}

tasks.register('taskB') {
    dependsOn taskA
    doLast { println 'B' }
}
~~~

`./gradlew taskB --quiet` in `A` rồi `B`. Task `taskA` được yêu cầu dù bạn chỉ nhập lệnh gọi `taskB`. `dependsOn` mang ý nghĩa **phụ thuộc mạnh**, nên các task liên quan phải được đưa vào graph.

Nếu một task phụ thuộc vào hai task độc lập:

~~~groovy
tasks.register('taskC') {
    doLast { println 'C' }
}

tasks.register('allWork') {
    dependsOn tasks.named('taskA'), tasks.named('taskC')
}
~~~

`allWork` cần cả `taskA` và `taskC`, nhưng **không có bảo đảm “A trước C”** chỉ vì bạn khai báo A rồi C. Gradle có thể chọn thứ tự hợp lệ dựa trên graph, tính song song và thông tin scheduling.

### 6.2. `mustRunAfter` và `shouldRunAfter`: yêu cầu/ưu tiên thứ tự, không tự kéo task vào graph

~~~groovy
tasks.named('taskC') {
    mustRunAfter tasks.named('taskA')
}
~~~

Nếu một lệnh yêu cầu **cả hai** `taskA` và `taskC`, `mustRunAfter` buộc `taskA` hoàn thành trước `taskC`. Nhưng `./gradlew taskC` **không tự chạy `taskA`**, vì `mustRunAfter` không đồng nghĩa `dependsOn`.

`shouldRunAfter` chỉ gợi ý thứ tự và có thể bị Gradle bỏ qua nếu cần để tránh vấn đề đồ thị/đáp ứng scheduling. Nó cũng không kéo task khác vào graph. Nếu có **đầu vào thật sự** từ task A cho task C, hãy dùng `dependsOn` hoặc output-to-input wiring đúng, đừng chỉ dựa vào ordering.

### 6.3. `finalizedBy`: công việc theo sau, thường dành cho cleanup

~~~groovy
tasks.register('removeTemporaryMarker') {
    doLast { println 'cleanup' }
}

tasks.register('runSession') {
    doLast { println 'session' }
    finalizedBy tasks.named('removeTemporaryMarker')
}
~~~

Khi chạy `./gradlew runSession --quiet`, output của hai action là:

~~~text
session
cleanup
~~~

`finalizedBy` gắn một **finalizer task** sau task chính. Đây không phải cách khai báo “cleanup phải chạy trước runSession”; và cũng không thay thế `dependsOn` để chuẩn bị input. Gradle sử dụng finalizer cho công việc dọn dẹp sau task, kể cả một số trường hợp task được hoàn thành với lỗi. Đừng dùng finalizer để ngụy tạo một bước verification mà phải chặn build trước khi phát hành.

### 6.4. `onlyIf` và `enabled`: điều kiện thực thi riêng với dependency

~~~groovy
tasks.register('optionalReport') {
    onlyIf { providers.gradleProperty('reportEnabled').orElse('false').get() == 'true' }
    doLast { println 'report generated' }
}
~~~

`./gradlew optionalReport` không in dòng report nếu không có `-PreportEnabled=true`, nhưng việc một task bị skip **không cho phép kết luận toàn bộ các dependency của nó sẽ tự bị skip**. Task graph có thể đã lập và những dependency vẫn được chạy. Đây là lý do không gắn các hiệu ứng phụ không cần thiết vào nhánh chỉ “có vẻ sẽ không chạy”.

Không nhầm `onlyIf` với tạo task conditionally bằng `if (...) { tasks.register(...) }`: cách thứ hai thay đổi **cấu trúc task graph** ngay từ cấu hình.

## 7. Phòng thực hành 2: task tạo file thật và lifecycle task kiểm chứng

Ví dụ phần 5 dùng `println` để minh họa. Trong dự án thực tế, task nên có **inputs/outputs rõ ràng** để Gradle kiểm tra up-to-date, thực thi lại khi cần và có cơ hội sử dụng build cache khi được hỗ trợ.

### 7.1. Một project Base plugin với custom task type

Tạo thư mục `task-artifact-lab` gồm `settings.gradle` và `build.gradle`, dùng Wrapper như phần 5.

**`settings.gradle`:**

~~~groovy
rootProject.name = 'task-artifact-lab'
~~~

**`build.gradle` — toàn bộ script Groovy DSL:**

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.GradleException
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

plugins {
    id 'base'
}

abstract class GenerateSummary extends DefaultTask {
    @Input
    abstract Property<String> getSummaryText()

    @OutputFile
    abstract RegularFileProperty getDestination()

    @TaskAction
    void generate() {
        File file = destination.get().asFile
        file.parentFile.mkdirs()
        file.setText(summaryText.get() + '\n', 'UTF-8')
        println 'generated=' + file.name
    }
}

def reportFile = layout.buildDirectory.file('reports/lesson-status.txt')

def generateTask = tasks.register('generateSummary', GenerateSummary) {
    group = 'distribution'
    description = 'Tạo artifact văn bản từ task có kiểu'
    summaryText.set('ready')
    destination.set(reportFile)
}

def verifyTask = tasks.register('verifySummary') {
    group = 'verification'
    description = 'Kiểm tra nội dung artifact đã tạo'
    dependsOn generateTask
    inputs.file(reportFile)

    doLast {
        File file = reportFile.get().asFile
        if (file.getText('UTF-8') != 'ready\n') {
            throw new GradleException('Report content mismatch')
        }
        println 'verified=OK'
    }
}

tasks.named('assemble') {
    dependsOn generateTask
}

tasks.named('check') {
    dependsOn verifyTask
}
~~~

**Vì sao đây là mô hình đúng?**

1. `GenerateSummary` là **task type có action** `@TaskAction`.
2. `summaryText` là `Property<String>` được đánh dấu `@Input`, `destination` là `RegularFileProperty` được đánh dấu `@OutputFile`. Gradle biết đầu vào/đầu ra cần theo dõi.
3. `layout.buildDirectory.file(...)` trả provider chỉ đến file trong build directory; script không tự ghi file khi đang configuration.
4. `tasks.register('generateSummary', GenerateSummary)` trả `TaskProvider`, không ép khởi tạo task từ sớm.
5. `verifySummary` có action kiểm chứng. `dependsOn generateTask` bảo đảm artifact cần kiểm tra được tạo trước; `inputs.file(reportFile)` mô tả input mà task đọc.
6. `assemble` là lifecycle task tạo sản phẩm: nó phụ thuộc `generateSummary`.
7. `check` là lifecycle task kiểm tra: nó phụ thuộc `verifySummary`.
8. `build` đã được Base plugin cấu hình phụ thuộc cả `assemble` và `check`, nên **không cần** thêm `dependsOn` trực tiếp vào `build`.

### 7.2. Lệnh kiểm chứng và đầu ra

Chạy từ project root:

~~~bash
./gradlew clean build --quiet
~~~

Trong điều kiện mặc định, hai dòng **stdout từ task actions** là:

~~~text
generated=lesson-status.txt
verified=OK
~~~

Sau khi chạy, file `build/reports/lesson-status.txt` có nội dung một dòng `ready` và ký tự xuống dòng. `--quiet` tắt phần lớn log thông thường của Gradle; nếu bỏ `--quiet` bạn còn thấy thông tin task/trạng thái.

Thử tiếp:

~~~bash
./gradlew assemble
./gradlew check
./gradlew build
~~~

- `assemble` chỉ yêu cầu nhánh tạo sản phẩm (`generateSummary`). Nó **không** tự yêu cầu `verifySummary`.
- `check` yêu cầu nhánh kiểm tra; vì `verifySummary` phụ thuộc `generateSummary`, nhánh này cũng yêu cầu output tồn tại.
- `build` gom cả hai. Nếu output không đổi, `generateSummary` có thể là `UP-TO-DATE`, nên **không nhất thiết in lại dòng `generated=...` ở mỗi lần chạy**.
- `verifySummary` là task kiểm tra không khai báo output riêng, nên trong ví dụ nó có action kiểm tra mỗi lần được yêu cầu (trừ khi bị skip vì lý do khác).
- Nếu sửa `summaryText.set('ready')` thành `summaryText.set('changed')` mà không cập nhật điều kiện kiểm chứng, lần build sau sẽ chạy lại phần tạo file rồi **thất bại tại `verifySummary`**.

**Giải thích độ tin cậy:** Ví dụ sử dụng `@Input`/`@OutputFile` để Gradle biết khi nào action tạo artifact có thể bỏ qua do output hợp lệ. Điều đó **khác** với khẳng định mọi task đều build-cache được. Muốn cache result xuyên workspace/máy, cần task type phù hợp, cache được bật, input/output xác định, không có side effect không được khai báo; annotation `@CacheableTask` chỉ nên dùng khi task thực sự đáp ứng hợp đồng cache.

### 7.3. Tại sao không đưa mọi action vào `build { doLast { ... } }`?

~~~groovy
tasks.named('build') {
    doLast {
        println 'A very late action'
    }
}
~~~

Đoạn trên hợp lệ về cú pháp, nhưng **thường không phải cách thiết kế tốt** để tổ chức build:
- `build` từ task gom việc thành task **có action riêng**, làm mờ trách nhiệm.
- Action đặt ở đây không thể được chạy riêng bằng một task có tên mô tả chức năng.
- Input/output của phần việc đó khó nhìn hơn nếu bạn không tạo task type chuyên biệt.
- `assemble` và `check` sẽ **không** tự gọi action đó khi chạy độc lập.

Tốt hơn: tạo `generateSummary`, `verifySummary` theo từng trách nhiệm và gắn vào lifecycle task phù hợp. Điều đó cho phép lập graph chính xác và chỉ chạy phần cần thiết.

## 8. Lifecycle task chuẩn đến từ plugin nào?

Base plugin đóng vai trò nền tảng cho các lifecycle tasks được nhiều plugin khác sử dụng:

| Task | Vai trò chuẩn | Quan hệ chính |
| --- | --- | --- |
| `clean` | Task `Delete` xóa build directory của project (mặc định `build/`) | Task có hành động xóa, không phải lifecycle aggregator thuần túy |
| `assemble` | Gom các task tạo artifact/đầu ra dùng được | Khi có Java plugin, thường phụ thuộc `jar` |
| `check` | Gom các task kiểm tra/xác minh | Khi có Java plugin, thường phụ thuộc `test` |
| `build` | Điểm vào build tổng hợp | **`dependsOn check, assemble`** |

Đây là lý do **`clean` không nằm trong `build` mặc định**. Nếu muốn xóa output rồi build, chạy `./gradlew clean build`; `./gradlew build` thông thường tận dụng up-to-date checks để tránh làm lại việc không cần thiết.

### 8.1. Khi chỉ áp dụng Base plugin

~~~groovy
plugins {
    id 'base'
}
~~~

Project có `clean`, `assemble`, `check`, `build`. Nhưng Base plugin **không tự thêm `compileJava`, `test`, `jar`**. Vì vậy `./gradlew build` có thể thành công gần như không thực hiện công việc hữu ích nếu bạn không thêm plugin/actionable tasks. `BUILD SUCCESSFUL` chỉ có nghĩa các task được yêu cầu đã hoàn thành hợp lệ.

### 8.2. Khi dùng Java plugin

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Java plugin thêm các task như `compileJava`, `test`, `jar` và kết nối vào các lifecycle tasks: `check` yêu cầu `test`, `assemble` yêu cầu `jar`, `build` gom cả hai. Các task compile/test còn có những dependency cần để có classpath và output hợp lệ.

Ví dụ Java 17 độc lập, đặt tại **`src/main/java/demo/Hello.java`**:

~~~java
package demo;

public final class Hello {
    private Hello() {
    }

    public static void main(String[] args) {
        System.out.println("Hello Gradle");
    }
}
~~~

Nếu dùng build script `plugins { id 'java' }` và toolchain Java 17 ở trên, chạy:

~~~bash
./gradlew assemble
java -cp build/classes/java/main demo.Hello
~~~

**Stdout chính xác của Java application:**

~~~text
Hello Gradle
~~~

`assemble` gọi task sản xuất JAR/class cần thiết, nhưng **không tự chạy main**. Để có task `run`, bạn cần Application plugin và cấu hình `mainClass` phù hợp. `build` không tự mang nghĩa “chạy chương trình”.

### 8.3. Khi dùng Application plugin

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.Hello'
}
~~~

Đây là **build.gradle thay thế** cho ví dụ Java plugin trên (giữ file `Hello.java`). Application plugin áp dụng Java và Distribution plugin, bổ sung `run` và các task tạo phân phối như `distZip`, `distTar`. `assemble` có thể yêu cầu các task tạo phân phối cùng JAR, còn `check` vẫn gom kiểm thử. `build` tiếp tục là điểm vào chung. `run` là task có hành động riêng, không tự là dependency của `build`.

## 9. Thêm task của dự án vào `check` hoặc `assemble` đúng mục đích

Nguyên tắc thực tiễn:

- **Task tạo sản phẩm** (file, archive, distribution): gắn vào `assemble` khi output phải là một phần của gói tiêu chuẩn.
- **Task xác minh** (unit test, lint, kiểm tra metadata/hợp đồng): gắn vào `check` khi CI phải từ chối build nếu sai.
- **Task triển khai** (deploy/publish ra hệ thống ngoài): thường là mục tiêu có tên riêng, cần điều kiện/quyền rõ; không đưa vào `build` chỉ vì muốn “tất cả chạy”.
- **Task dọn dẹp**: dùng task riêng như `clean` hoặc `finalizedBy` phù hợp; tránh xóa dữ liệu trong configuration closure.

Ví dụ bổ sung vào **dự án đã áp dụng Java plugin**:

~~~groovy
def verifySourceLayout = tasks.register('verifySourceLayout') {
    group = 'verification'
    description = 'Kiểm tra thư mục source Java chính tồn tại'

    doLast {
        println 'source-layout-check'
    }
}

tasks.named('check') {
    dependsOn verifySourceLayout
}
~~~

Đây là **đoạn demo về nối graph**; action chỉ in một dấu hiệu, **chưa kiểm tra thư mục thật**. Trong dự án thực tế, thay bằng task xác minh có input, logic kiểm tra và thông báo lỗi cụ thể. Sau khi nối, cả `./gradlew check` và `./gradlew build` đều yêu cầu `verifySourceLayout`; `./gradlew assemble` không tự yêu cầu task kiểm tra đó.

Khi viết convention plugin cho nhiều project, cách tiếp cận cũng giống vậy: tạo task chuyên trách, rồi đăng ký nó vào lifecycle task thích hợp bằng `TaskProvider`.

## 10. Build nhiều project: task selector và đường dẫn

Giả sử `settings.gradle` của một build có:

~~~groovy
rootProject.name = 'multi-task-demo'
include 'core', 'app'
~~~

`:core` dùng `java-library`; `:app` dùng `application` và có dependency mã tới `:core`.

~~~bash
./gradlew projects
./gradlew build
./gradlew :core:check
./gradlew :app:assemble
./gradlew :app:build
./gradlew :app:clean
~~~

Giải thích:
- `build` (không có đường dẫn đầy đủ) là **task selector**: từ root, nó có thể chọn các task tên `build` ở root và những subprojects liên quan.
- `:core:check` nhắm riêng lifecycle `check` của project `core`, cùng các dependency cần thiết.
- `:app:assemble` tạo artifact của `app` và những task dependency để tạo chúng; **không** đồng nghĩa chạy tất cả test của mọi project.
- `:app:build` yêu cầu `:app:check` và `:app:assemble`. Nếu app có `implementation project(':core')`, Gradle sẽ dựng những task `:core` cần cho compile/package **nhưng không mặc nhiên chạy `:core:check` chỉ vì dependency mã**.
- `:app:clean` dọn build directory của riêng `app`. Task selector `clean` từ root có thể chọn clean ở nhiều subproject.

Khi một nhóm lifecycle toàn repo phải chắc chắn kiểm tra cả app và core, hãy chạy task selector `check` từ root hoặc xây một điểm vào aggregator ở root có dependency tường minh tới các đường dẫn task phù hợp.

## 11. Kiểm tra graph thay vì đoán theo tên

Những lệnh hữu ích:

| Lệnh | Dùng để |
| --- | --- |
| `./gradlew tasks` | Xem các task theo group/description trong project hiện tại |
| `./gradlew tasks --all` | Xem cả task ít nổi bật và task của plugin |
| `./gradlew help --task lessonPipeline` | Xem mô tả task theo tên (khi task tồn tại) |
| `./gradlew lessonPipeline --dry-run` | Kiểm tra các task được chọn và thứ tự mô phỏng, không chạy action |
| `./gradlew build --info` | Xem chi tiết hơn về task selection, input/up-to-date checks |
| `./gradlew generateSummary --rerun-tasks` | Buộc chạy lại task dù output có thể up-to-date |
| `./gradlew clean build` | Xóa output rồi thực hiện build lại khi thật sự cần |
| `./gradlew :app:check` | Nhắm đích danh task `check` của project `app` |

**Các trạng thái cần hiểu:**

| Trạng thái | Ý nghĩa |
| --- | --- |
| `UP-TO-DATE` | Gradle nhận thấy input/output phù hợp nên bỏ qua action, **không phải thất bại** |
| `FROM-CACHE` | Output được phục hồi từ build cache thay vì chạy lại action |
| `NO-SOURCE` | Task xử lý source không thấy nguồn phù hợp |
| `SKIPPED` | Task/action bị bỏ qua vì điều kiện hoặc chế độ, chẳng hạn dry-run |
| `FAILED` | Một task thất bại; đọc task path và exception của task đó |
| `BUILD SUCCESSFUL` | Những task được yêu cầu đã hoàn thành hợp lệ, **không chứng minh mọi kiểm tra ngoài graph đã chạy** |

### Tình huống “tại sao lifecycle task không làm gì?”

1. Chỉ có Base plugin, `check` chưa được nối vào task kiểm tra nào.
2. Một plugin hoặc script tạo task có action nhưng không gắn nó vào `check`/`assemble`.
3. Bạn chạy lifecycle task ở **project khác** với nơi định nghĩa action.
4. Task kiểm tra bị điều kiện `onlyIf` hoặc `enabled=false` bỏ qua.
5. Task đã `UP-TO-DATE` hoặc output được lấy từ cache.
6. Bạn chỉ gọi `--dry-run` nên không có action thực thi.
7. Task chạy nhưng không tạo output/log mà bạn đang mong đợi.

Cách tìm nguyên nhân: xác minh plugin và task bằng `tasks --all` → xem graph với `--dry-run` → xem `--info` khi chạy thật → kiểm tra task path, input/output và điều kiện chạy. Đừng thêm `doLast` vào lifecycle task chỉ để “thấy một dòng log”.

## 12. Các sai lầm thiết kế và hướng sửa

| Cách hiểu/cách viết sai | Vì sao sai | Cách làm phù hợp |
| --- | --- | --- |
| “Đặt task tên `release` thì Gradle tự biết cần build/test trước” | Tên không tạo dependency | Dùng `dependsOn` hoặc nối input/output rõ ràng |
| “Trong `dependsOn A, B` thì A luôn chạy trước B” | A và B là hai nhánh độc lập nếu không có edge | Khai báo dependency thực hoặc ordering nếu cả hai đều được chọn |
| “`mustRunAfter` tự chạy task được nhắc tới” | Chỉ ràng buộc thứ tự, không yêu cầu task xuất hiện | Dùng `dependsOn` khi công việc kia bắt buộc |
| “Cứ viết `println` trong `tasks.register {}` là nó chạy lúc task chạy” | Đó có thể là mã **cấu hình** | Đặt hành động trong `doLast`/`doFirst`/`@TaskAction` |
| “Mọi task đều sẽ được cấu hình ngay khi Gradle đọc script” | `tasks.register` và `named` là lazy APIs | Giữ tham chiếu `TaskProvider`, tránh `.get()` không cần thiết |
| “Task tạo file không khai báo output vẫn có cache đúng” | Gradle không biết đủ input/output để quyết định cache/up-to-date | Khai báo `@Input`/`@OutputFile` hoặc inputs/outputs API |
| “`assemble` luôn chạy unit test” | Nó gom artifact; Java plugin nối test vào `check` | Chạy `check` hoặc `build` cho kiểm chứng |
| “`build` tự chạy mọi task tùy biến trong project” | Chỉ task có trong graph mới được yêu cầu | Nối task mới vào `check`/`assemble` hoặc workflow rõ ràng |
| “`build` tự gọi `clean`” | `clean` là task độc lập | Gọi `clean build` khi cần dọn output |
| “Gắn một action deployment vào `build` là đủ” | Trộn build và side effect ngoài hệ thống, khó kiểm soát | Dùng task publish/deploy riêng với quyền và điều kiện thích hợp |
| “`:app:build` đương nhiên test mọi project dependency” | Dependency artifact khác với yêu cầu chạy verification | Gọi root `check` hoặc aggregator kiểm tra toàn bộ project |
| “`BUILD SUCCESSFUL` chứng minh artifact đã kiểm thử đủ” | Lifecycle task chỉ gom những task được nối đúng | Kiểm tra graph, kết quả test, report và chính sách CI |

## 13. Bài luyện có đáp án

**Bài 1 — Phân loại:** `clean`, `compileJava`, `test`, `assemble`, `check`, `build` trong dự án Java tương ứng loại gì?

**Đáp án:** `clean` là task `Delete` có hành động; `compileJava`, `test` là actionable tasks do Java plugin tạo; `assemble`, `check`, `build` là lifecycle tasks gom công việc. Chúng có quan hệ do plugin cấu hình, không vì tên giống nhau.

**Bài 2 — Thứ tự action:** Trong một task có hai `doFirst` lần lượt in A, B, rồi một `doLast` in C, stdout khi task thực thi là gì?

**Đáp án:** B, A, C. Các lệnh `doFirst` được chèn vào đầu chuỗi actions.

**Bài 3 — Thứ tự các task:** Task X phụ thuộc A và B, không có quan hệ trực tiếp A ↔ B. Có thể yêu cầu output luôn là A, B, X không?

**Đáp án:** Không. Chỉ chắc cả A và B phải hoàn tất trước X; thứ tự giữa A và B không được cố định. Nếu B dùng output của A, biểu diễn dependency/data wiring B → A.

**Bài 4 — Ordering:** Task B có `mustRunAfter A`. Chạy duy nhất `./gradlew B` có tự chạy A không?

**Đáp án:** Không. Ordering chỉ ảnh hưởng thứ tự nếu các task liên quan đều được chọn.

**Bài 5 — Lifecycle task với output:** Theo script phần 7, `./gradlew assemble` có bắt buộc in dòng `verified=OK` không?

**Đáp án:** Không. `assemble` phụ thuộc `generateSummary`; task `verifySummary` thuộc nhánh `check`. Chạy `./gradlew build` yêu cầu cả hai nhánh.

**Bài 6 — Vì sao `build` không in output thứ hai?** Bạn đã chạy `./gradlew clean build --quiet` thành công, sau đó chạy lại `./gradlew build --quiet`. Dòng `generated=...` có thể vắng mặt nhưng build vẫn thành công. Vì sao?

**Đáp án:** `generateSummary` khai báo input/output và Gradle có thể thấy output đang `UP-TO-DATE` nên không gọi lại `@TaskAction`. Kiểm tra task state trước khi xem đây là lỗi.

**Bài 7 — Tự mở rộng:** Tạo thêm task `checkMetadata` có action xác minh một file cấu hình, gắn vào `check` bằng `TaskProvider`. Chạy `check --dry-run` và `build --dry-run` để thấy task mới nằm trong graph; kiểm chứng `assemble --dry-run` không buộc chạy task này.

**Tiêu chí hoàn thành:** Bạn tự vẽ được task graph, biết đặt action vào execution phase, tạo một lifecycle task chỉ có `dependsOn`, phân biệt dependency/order/finalizer, biết nối kiểm tra vào `check` và artifact vào `assemble`, và có thể giải thích tình huống task không chạy vì `UP-TO-DATE` hoặc không nằm trong graph.

## Tài liệu chính thức để đối chiếu

- [Gradle — Organizing Tasks](https://docs.gradle.org/current/userguide/organizing_tasks.html): actionable task, lifecycle task và tổ chức điểm vào.
- [Gradle — Creating and Registering Tasks](https://docs.gradle.org/current/userguide/writing_tasks.html): tạo task, task type, action, inputs/outputs.
- [Gradle — Task Basics](https://docs.gradle.org/current/userguide/task_basics.html): task graph, thực thi và task dependencies.
- [Gradle — Understanding Tasks](https://docs.gradle.org/current/userguide/more_about_tasks.html): task categories, plugin/task lifecycle.
- [Gradle — The Base Plugin](https://docs.gradle.org/current/userguide/base_plugin.html): `clean`, `assemble`, `check`, `build` và quan hệ giữa chúng.
- [Gradle — Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `register`, `named`, `TaskProvider` và soft/strong relationships.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): up-to-date checks dựa vào inputs/outputs.
