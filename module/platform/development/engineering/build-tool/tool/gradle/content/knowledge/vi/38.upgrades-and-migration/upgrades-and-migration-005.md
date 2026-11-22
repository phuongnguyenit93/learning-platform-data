# Chuyển từ API cấu hình sớm sang lazy configuration trong Gradle

## 1. Vấn đề nâng cấp: vì sao build chưa chạy task đã chậm?

Một project Java gồm hàng chục module và nhiều Gradle plugins. Developer chạy:

~~~bash
./gradlew help
~~~

Lệnh chỉ cần hiển thị trợ giúp, nhưng project mất nhiều giây để tạo/configure hundreds of tasks, đọc file cấu hình, resolve dependencies và tính đường dẫn cho những task chẳng được yêu cầu. Trong quá khứ build script có thể sử dụng:

~~~kotlin
tasks.create("generateReport") {
    // configure task ngay lúc create được gọi
}

tasks.getByName("test") {
    // lấy task instance, có thể buộc task được tạo/configure
}

tasks.withType<JavaCompile>().all {
    // eager configuration action
}
~~~

Khi nâng Gradle hoặc hiện đại hóa build logic, nên chuyển dần sang:

~~~kotlin
val report = tasks.register("generateReport") {
    // chỉ chạy configuration khi task thật sự được realized
}

tasks.named("test") {
    // cấu hình task theo provider, chưa cần lấy instance
}

tasks.withType<JavaCompile>().configureEach {
    // áp dụng cho mỗi matching task khi nó được realized
}
~~~

**Lazy configuration không có nghĩa “Gradle không bao giờ cấu hình task”.** Nó có nghĩa Gradle **trì hoãn tạo và cấu hình task cho đến khi task đó cần thiết**. Khi bạn chạy `test`, các tasks thuộc graph của `test` vẫn được configured; những tasks không liên quan có thể giữ ở trạng thái chỉ mới đăng ký.

Bài Knowledge thuộc chủ đề **Nâng cấp và di chuyển** của module **Build Tool Gradle**. Nó cung cấp cách chuyển **eager task APIs → configuration avoidance APIs**, sau đó nâng tiếp sang **lazy properties/Provider API**. Hai phần liên quan nhưng không đồng nhất.

### 1.1. Bạn sẽ học được gì?

Sau bài này, bạn có thể:

1. Phân biệt task **registered**, **realized/configured**, **executed** và **skipped**.
2. Chuyển `tasks.create` thành `tasks.register` khi phù hợp.
3. Thay `getByName`/`getAt`/`tasks["name"]` bằng `tasks.named` mà không gọi `get()` quá sớm.
4. Thay `tasks.all`/`withType(...).all` bằng `configureEach` và hiểu sự khác biệt với `matching`.
5. Dùng `TaskProvider<T>` để khai `dependsOn`, `finalizedBy`, `mustRunAfter` và `shouldRunAfter`.
6. Hiểu lúc nào `TaskProvider.get()`, `tasks.getByName` và iteration buộc task realization.
7. Dùng `Property<T>`, `Provider<T>`, `RegularFileProperty`, `DirectoryProperty` và `ConfigurableFileCollection` để khai managed inputs/outputs.
8. So sánh `set(...)`, `convention(...)`, `map(...)`, `flatMap(...)`, `orElse(...)` và `zip(...)`.
9. Wire producer output → consumer input, để Gradle suy ra **implicit task dependency** thay vì hard-coded file paths.
10. Chuyển code khỏi `afterEvaluate`, `gradle.taskGraph.whenReady` và cross-project mutation dễ gây order-dependence.
11. Tránh resolve configuration, gọi `Provider.get()` hoặc đọc I/O/network trong configuration phase không cần thiết.
12. Phân biệt configuration avoidance với **Configuration Cache**, **Build Cache**, **Daemon** và **up-to-date checks**.
13. Viết custom typed Gradle tasks cho Java 17, chạy được với `gradle`/Wrapper, có output chính xác.
14. Đo số task được realized trong `help`, kiểm correctness bằng tests và so cold/warm configuration time.
15. Nhận diện những bẫy migration khiến task không được configure, output thiếu hoặc build order phụ thuộc may rủi.

## 2. Bốn trạng thái liên quan tới task

Khi đọc Gradle log, đừng nhầm “task có trong project” với “task action đã chạy”.

### 2.1. Registered — đã biết task name/type/provider

~~~kotlin
val exportDocs = tasks.register("exportDocs")
~~~

Gradle đã biết tên `exportDocs` và có `TaskProvider<Task>`. Task object có thể **chưa được tạo** và configuration action có thể **chưa chạy**.

### 2.2. Realized/configured — task object đã được tạo

Khi Gradle cần task instance (vì task nằm trong execution graph hoặc API eager yêu cầu), nó thực hiện các configuration actions đã đăng ký. Ví dụ:

~~~kotlin
val exportDocs = tasks.register("exportDocs") {
    println("EXPORT_CONFIGURED=YES")
}
~~~

Dòng `EXPORT_CONFIGURED=YES` chạy khi task được realized/configured, **không** phải khi task action thực thi.

### 2.3. Executed — task actions thật sự chạy

~~~kotlin
val exportDocs = tasks.register("exportDocs") {
    println("EXPORT_CONFIGURED=YES")
    doLast {
        println("EXPORT_EXECUTED=YES")
    }
}
~~~

Nếu task được yêu cầu và không skipped, action `doLast` chạy. Khi gọi `./gradlew help`, `exportDocs` có thể không realized và không in cả hai dòng.

### 2.4. Skipped — task có trong graph nhưng action không cần chạy

Khi task có khai input/output, Gradle có thể báo:

~~~text
> Task :compileJava UP-TO-DATE
> Task :processResources NO-SOURCE
> Task :compileTestJava FROM-CACHE
~~~

Các task có thể đã được realized/configured để tạo graph, nhưng action không thực thi do skip/cache/source state. **Configuration avoidance** quyết định task nào cần **tạo/cấu hình**; **up-to-date/build-cache checks** quyết định task action có cần **chạy** không.

### 2.5. Ma trận thuật ngữ

| Thuật ngữ | Đã có task object? | Configuration action có thể chạy? | Task action chạy? |
| --- | --- | --- | --- |
| Registered only | Có provider, chưa chắc có object | Có thể chưa | Chưa |
| Realized/configured | Có | Có | Chưa chắc |
| Executed | Có | Có | Có |
| UP-TO-DATE/FROM-CACHE | Có trong graph | Có | Không cần chạy task action |
| Không liên quan build graph | Có thể chỉ registered | Có thể không | Không |

Đây là mô hình để hiểu hành vi; Gradle engine có thể có các bước nội bộ khác nhau giữa releases.

## 3. Vì sao eager task APIs tốn thời gian?

Giả sử plugin tạo 500 tasks bằng:

~~~kotlin
for (index in 1..500) {
    tasks.create("report" + index) {
        // Tưởng chỉ là khai báo, nhưng đây là eager creation
        description = "Report number " + index
    }
}
~~~

Trong quá trình configuration, Gradle phải tạo/configure từng task mặc dù developer chỉ chạy `help`. Nếu mỗi configuration action còn đọc file, scan disk, query dependency hoặc tạo model lớn, startup cost tăng theo số task.

Với lazy registration:

~~~kotlin
for (index in 1..500) {
    tasks.register("report" + index) {
        description = "Report number " + index
    }
}
~~~

Gradle biết 500 task names/providers nhưng chưa nhất thiết tạo 500 task objects. Chi phí configuration có thể giảm đáng kể khi không cần tất cả tasks. **Không hứa giảm từ 5 giây xuống 0 giây** vì settings/plugins/project configuration vẫn tồn tại.

### 3.1. Task registration không bằng execution

`tasks.register` không bắt đầu thread, không đọc file ngay trong action và không chạy `doLast`. Task instance chỉ cần tạo khi task được yêu cầu hoặc một API buộc realization.

### 3.2. Đừng tạo “task khổng lồ” để tránh overhead

Gộp hàng trăm tasks thành một task action có switch-case không phải phương án mặc định: nó làm mất fine-grained inputs/outputs, task parallelism, up-to-date checks và khả năng chẩn đoán. Thường hãy giữ tasks có trách nhiệm rõ ràng và **đăng ký lazy**.

## 4. Eager API → Lazy API: bảng migration

| Mẫu cũ (eager) | Mẫu ưu tiên (lazy) | Lưu ý |
| --- | --- | --- |
| `tasks.create("x")` | `tasks.register("x")` | Trả TaskProvider thay vì Task |
| `tasks.create("x", MyTask::class.java)` | `tasks.register<MyTask>("x")` | Kotlin DSL type-safe |
| `tasks.getByName("x") { ... }` | `tasks.named("x") { ... }` | named không cần realize ngay |
| `tasks.getByName("x")` | `tasks.named("x")` | Giữ TaskProvider, đừng gọi get lập tức |
| `tasks.withType(X::class.java).all { ... }` | `tasks.withType<X>().configureEach { ... }` | Avoid eager type-wide configuration |
| `tasks.all { ... }` | `tasks.configureEach { ... }` | Chỉ khi hành vi áp cho mọi task |
| `tasks.withType(X::class.java) { ... }` | `tasks.withType<X>().configureEach { ... }` | Action overload có thể eager |
| `tasks["x"]` dùng để mutate | `tasks.named("x") { ... }` | Tránh instant task lookup |
| `val t: Task = tasks.create("x")` | `val t: TaskProvider<Task> = tasks.register("x")` | Update types/call sites |
| `dependsOn(tasks.getByName("x"))` | `dependsOn(tasks.named("x"))` | TaskProvider được chấp nhận |

**Không** thay `tasks.getByName("x")` bằng `tasks.named("x").get()` ngay trong configuration: nó vẫn buộc task object được tạo. Lazy API chỉ có ích khi **giữ provider** đến lúc Gradle thực sự cần giá trị.

### 4.1. Không phải mọi API có tên “configure” đều lazy

Ví dụ:

~~~kotlin
tasks.withType<JavaCompile>().all {
    options.encoding = "UTF-8"
}
~~~

`all` có thể eagerly configure registered tasks. Migrate thành:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

`configureEach` đăng ký configuration action để chạy trên từng task phù hợp **khi task được realized**, kể cả tasks được đăng ký sau đó.

### 4.2. Tên tác vụ phải có thật

~~~kotlin
tasks.named("test") {
    // ...
}
~~~

chỉ hợp lệ khi task `test` đã được đăng ký bởi Java plugin hoặc plugin khác. Nếu áp `base` plugin mà không có `test`, `named("test")` có thể fail. Lazy không phải cách né lỗi tên task không tồn tại.

### 4.3. Không thay "create" trong mọi ngữ cảnh bằng register vô điều kiện

Trong plugin nội bộ, có thể có code thực sự **cần task object ngay** và phải tương tác với legacy API không nhận provider. Migration đòi sửa call sites và kiểm semantics, không chỉ search-replace. Nếu không thể đổi ngay, giữ một eager boundary được document và có test, rồi chuyển phần còn lại sang provider.

## 5. Đúng cách với tasks.register

### 5.1. Một task tạo khi cần

~~~kotlin
val generateIndex = tasks.register("generateIndex") {
    group = "documentation"
    description = "Creates an index when requested"
    doLast {
        println("INDEX_GENERATED=YES")
    }
}
~~~

`generateIndex` là `TaskProvider<Task>`. Trong một project tối giản:

~~~bash
gradle help --quiet
~~~

không yêu cầu task đó nên action `doLast` không chạy. Khi:

~~~bash
gradle generateIndex --quiet
~~~

stdout từ task action:

~~~text
INDEX_GENERATED=YES
~~~

Nếu build có unrelated plugins/tasks in logs, stdout có thể chứa thêm dòng; marker này có ý nghĩa trong project mẫu tối giản.

### 5.2. Type-safe TaskProvider

~~~kotlin
val compile = tasks.named<JavaCompile>("compileJava")
~~~

Đây là snippet cho project đã áp Java plugin và import `JavaCompile`. `compile` là `TaskProvider<JavaCompile>`, chưa phải task instance.

Cấu hình:

~~~kotlin
tasks.named<JavaCompile>("compileJava") {
    options.encoding = "UTF-8"
    options.release.set(17)
}
~~~

Trên một project Java toolchain17, Gradle chỉ áp cấu hình này khi `compileJava` được realized. Nếu invocation là `help`, không cần configure compiler chỉ để đặt encoding.

### 5.3. TaskProvider.configure

~~~kotlin
val compile = tasks.named<JavaCompile>("compileJava")

compile.configure {
    options.encoding = "UTF-8"
}
~~~

`configure { }` đăng ký action để configure task vào thời điểm cần thiết. Đừng viết:

~~~kotlin
compile.get().options.encoding = "UTF-8"
~~~

trong build script nếu không có lý do thật sự cần tạo task instance ngay.

### 5.4. TaskProvider không phải Future để làm async programming

Provider mô tả **lazy value/lazy task reference** trong Gradle model, không phải JavaScript Promise, Java Future hoặc background task executor. Gọi `get()` có thể làm Gradle **realize** task/compute value đồng bộ khi cần, không làm task action chạy ngay.

## 6. tasks.named thay getByName

### 6.1. Anti-pattern

~~~kotlin
val testTask = tasks.getByName("test")
testTask.group = "verification"
~~~

Code lấy task object trong configuration và có thể buộc realization.

### 6.2. Tương đương lazy

~~~kotlin
tasks.named<Test>("test") {
    group = "verification"
}
~~~

Đây là snippet cho Java plugin với `Test` type đã có, không phải complete project. Sự thay đổi giữ nguyên ý nghĩa cấu hình task nhưng tránh tạo instance sớm.

### 6.3. Đừng gọi named rồi get

~~~kotlin
val testProvider = tasks.named<Test>("test")

// Không nên gọi khi chỉ cần cấu hình:
val taskNow = testProvider.get()
~~~

`get()` trả concrete task instance và buộc realization. `named` không phải phép màu khi lập tức unwrap.

### 6.4. Khi nào get() có thể hợp lệ?

- Một API bên ngoài chỉ chấp nhận `Task` instance, không nhận Provider.
- Trong custom tooling/test code bạn thực sự cần inspect concrete task sau khi nó được tạo.
- Tại một boundary có chủ đích, sau khi đã đo cost và đảm bảo ordering.

Nhưng **không** dùng `get()` chỉ để đọc output path, đặt dependsOn hoặc thêm configuration action: Gradle có APIs lazy tương ứng.

## 7. configureEach thay all và withType action

### 7.1. Bẫy phổ biến

~~~kotlin
tasks.withType<Test>().all {
    maxHeapSize = "512m"
}
~~~

Có thể cause eager configuration của matching tasks trong build.

### 7.2. Sửa

~~~kotlin
tasks.withType<Test>().configureEach {
    maxHeapSize = "512m"
}
~~~

Gradle áp dụng config khi từng Test task được realized. Nếu plugin tạo nhiều Test suites hoặc custom Test tasks sau này, `configureEach` vẫn có thể áp đúng từng task.

### 7.3. Filter bằng matching

~~~kotlin
tasks.withType<Test>()
    .matching { it.name.endsWith("IntegrationTest") }
    .configureEach {
        maxHeapSize = "1g"
    }
~~~

Đây là snippet minh họa cần `Test` imports/Java plugin. Predicate chạy khi cần xác định task phù hợp; **đừng** làm database query/network I/O trong predicate. Các container APIs/predicates khác có thể có realization semantics riêng, do đó xem Gradle docs trước khi viết filtering phức tạp.

### 7.4. Không mutate một task khác trong configureEach

Anti-pattern:

~~~kotlin
val checkTask = tasks.named("check")
tasks.withType<Test>().configureEach {
    // Đừng unwrap/mutate task khác trong action này.
    checkTask.get().dependsOn(this)
}
~~~

Configuration action của Test task có thể chạy muộn, chạy theo thứ tự khác, hoặc không chạy. Mutate task `check` từ đây làm task graph phụ thuộc realization order. Thay vào đó, configure **chính check task**:

~~~kotlin
val tests = tasks.withType<Test>()

tasks.named("check") {
    dependsOn(tests)
}
~~~

Đây là **fragment** cho project có `check` và các Test tasks. `dependsOn` nhận TaskCollection; hãy hiểu việc kết nối tất cả Test tasks vào check có thể không đúng cho mọi project. Với một task duy nhất, dùng `TaskProvider` cụ thể.

### 7.5. Đặt configuration action lên đối tượng đang được cấu hình

Nguyên tắc migration:

> Action dùng để cấu hình task X chỉ nên mutate X; muốn thay task Y thì khai riêng `tasks.named("Y") { ... }`.

Nó làm ordering rõ ràng, tránh cyclic realization và thuận lợi cho parallel/configuration caching.

## 8. Quan hệ task graph và Provider

### 8.1. dependsOn với TaskProvider

~~~kotlin
val generate = tasks.register("generate") {
    doLast { println("GENERATE=YES") }
}

tasks.register("packageOutput") {
    dependsOn(generate)
    doLast { println("PACKAGE=YES") }
}
~~~

`dependsOn(generate)` giữ reference lazy. Không cần `generate.get()`.

Khi chạy:

~~~bash
gradle packageOutput --quiet
~~~

stdout action theo dependency ordering:

~~~text
GENERATE=YES
PACKAGE=YES
~~~

Ví dụ này chỉ minh họa graph ordering; chưa khai file outputs, không phải mô hình task production để cache.

### 8.2. mustRunAfter và shouldRunAfter

~~~kotlin
val lint = tasks.register("lint")
val test = tasks.register("myTest")

test.configure {
    mustRunAfter(lint)
}
~~~

`mustRunAfter` chỉ thiết lập thứ tự **nếu cả hai task đã được scheduled**, không tự đưa `lint` vào task graph. `shouldRunAfter` là soft ordering constraint, có thể bị bỏ qua trong một số trường hợp để tránh deadlock/đáp ứng scheduling. `dependsOn` là hard dependency nên producer task sẽ được scheduled khi consumer chạy.

### 8.3. finalizedBy

~~~kotlin
val report = tasks.register("report")

tasks.register("verify") {
    finalizedBy(report)
}
~~~

`finalizedBy` kết nối finalizer, nên khi `verify` được scheduled và reached, Gradle thường scheduling `report` để chạy sau theo semantics finalizer. Không nên dùng finalizer để thay cho **file input→output dependency**; file wiring bằng Provider an toàn hơn.

### 8.4. Đừng dùng String path nếu đã có TaskProvider

~~~kotlin
val producer = tasks.register("producer")
tasks.register("consumer") {
    dependsOn(producer)
}
~~~

Tốt hơn `dependsOn("producer")` khi code sẵn có provider: refactoring task names có thể dễ hơn, types rõ hơn. String paths vẫn hợp lệ trong nhiều trường hợp, nhưng provider giúp làm rõ identity và tránh eager instance access.

## 9. Lazy task registration khác lazy properties

Có **hai tầng tránh cấu hình sớm**:

1. **Task Configuration Avoidance**: không instantiate/configure task chưa cần — `tasks.register`, `tasks.named`, `configureEach`.
2. **Lazy Properties/Providers**: không tính/đọc giá trị input trước khi cần — `Property<T>`, `Provider<T>`, `DirectoryProperty`, `RegularFileProperty`.

Nếu bạn chuyển hết sang `tasks.register` nhưng configuration action vẫn gọi `providers.gradleProperty("secret").get()` và đọc files ngay khi task được realized, build có thể vẫn eager resolve values, gây vấn đề Configuration Cache hoặc performance.

### 9.1. Provider<T>

`Provider<T>` là giao diện đọc giá trị có thể được tính lazily:

~~~kotlin
val channel: Provider<String> =
    providers.gradleProperty("channel").orElse("stable")
~~~

`channel` chưa bắt buộc phải được đọc ngay. Khi consumer cần giá trị, Gradle tính theo provider chain.

### 9.2. Property<T>

`Property<T>` có thể nhận value hoặc Provider:

~~~kotlin
abstract val channel: Property<String>
~~~

Khi dùng trong typed Gradle task (và khai `@Input`), Gradle biết đây là input cần fingerprint.

### 9.3. set và convention

- `property.set("x")`: explicit value, thường override trước đó.
- `property.set(provider)`: link property tới nguồn lazy.
- `property.convention("x")`: default fallback khi chưa có explicit set.
- `property.convention(provider)`: default cũng có thể lazy.
- `property.get()`: truy giá trị hiện tại, có thể force evaluation.
- `property.orNull`: đọc giá trị hoặc null, **cũng là read** chứ không tự động lazy.

Ví dụ fragment:

~~~kotlin
message.convention(
    providers.gradleProperty("message")
        .orElse("hello lazy gradle")
)
~~~

Khi user truyền `-Pmessage="custom"`, provider trả giá trị user; nếu không, trả default. Đặt bằng `convention` cho phép consumer/plugin user `set` explicit sau đó.

### 9.4. map: transform một Provider

~~~kotlin
val raw = providers.gradleProperty("mode").orElse("dev")
val upper: Provider<String> =
    raw.map { value -> value.uppercase() }
~~~

`upper` lazily lấy `raw` rồi transform; không cần `raw.get().uppercase()` trong configuration.

### 9.5. flatMap: value trả về là Provider khác

~~~kotlin
val generatedTask = tasks.named<GenerateMessage>("generateMessage")
val generatedFile: Provider<RegularFile> =
    generatedTask.flatMap { it.outputFile }
~~~

Đây là **fragment** khi `GenerateMessage` đã được khai, và `outputFile` là `RegularFileProperty`. `flatMap` giúp giữ provider of output và thông tin producer task cho dependent input.

Không thay bằng:

~~~kotlin
val output = generatedTask.get().outputFile.get().asFile
~~~

trong top-level build script nếu bạn muốn tránh task realization và eager output path resolution.

### 9.6. zip và composition

~~~kotlin
val a = providers.gradleProperty("first").orElse("A")
val b = providers.gradleProperty("second").orElse("B")
val combined = a.zip(b) { x, y -> x + ":" + y }
~~~

`combined` phụ thuộc hai providers, chỉ tính khi consumer yêu cầu. Đây là fragment Kotlin DSL sử dụng Gradle `Provider.zip`.

### 9.7. Provider API không loại bỏ tất cả configuration work

Nếu plugin apply chính nó tốn 2 giây hoặc settings script phải tính dependency graph lớn, chỉ dùng `Property<T>` sẽ không khiến Gradle bỏ qua toàn bộ configuration. Tối ưu cần profiling đúng bottleneck.

## 10. File inputs/outputs dùng Property model

Một custom task nên khai đầy đủ:

~~~kotlin
@CacheableTask
abstract class GenerateMessage : DefaultTask() {
    @get:Input
    abstract val message: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        // Dùng message.get() và outputFile.get() khi execution
    }
}
~~~

Đây là **skeleton**, đầy đủ runnable class sẽ ở phần 13.

- `@Input`: input values.
- `@OutputFile`: output artifact path Gradle quản lý.
- `@TaskAction`: execution logic.
- `@CacheableTask`: thông báo task output có thể cache nếu deterministic, khai inputs đúng và build cache enabled.
- `RegularFileProperty`: managed lazy output path; có thể nhận provider từ `layout.buildDirectory.file(...)`.
- `Property<String>`: input value có thể lấy từ Gradle property.

### 10.1. Output provider giữ implicit task dependency

~~~kotlin
consumer.inputFile.set(
    producer.flatMap { it.outputFile }
)
~~~

Khi một producer task output được wire vào consumer `@InputFile`, Gradle có đủ thông tin để suy ra **producer phải chạy trước consumer**. Nó cũng cho phép output path thay đổi qua một provider chain mà consumer vẫn theo đúng output.

### 10.2. Tại sao chỉ dùng file path string là dễ lỗi?

Anti-pattern:

~~~kotlin
tasks.register("consume") {
    doLast {
        val content = file("build/generated/message.txt").readText()
        println(content)
    }
}
~~~

Đây là **anti-pattern**, không phải solution production. File read xảy ra trong task action nhưng `Project.file(...)` bị truy cập từ action có thể không tương thích Configuration Cache; không khai `@InputFile`; không suy ra producer dependency. Nếu chạy consumer trước producer, có thể file chưa tồn tại.

### 10.3. Cách đúng

- Producer khai `@OutputFile`.
- Consumer khai `@InputFile` cùng path-sensitivity đúng.
- Consumer nhận `producer.flatMap { it.outputFile }`.
- Task action chỉ đọc managed property/file đã khai.
- Gradle tự xây task graph và input fingerprints.

## 11. Không gọi get() trong configuration một cách thiếu kiểm soát

### 11.1. Gọi get() với TaskProvider

~~~kotlin
val report = tasks.register("report")
// Eager boundary:
val concrete = report.get()
~~~

`get()` buộc task created/configured. Nếu chỉ muốn khai dependency:

~~~kotlin
tasks.register("aggregate") {
    dependsOn(report)
}
~~~

### 11.2. Gọi get() với Provider

~~~kotlin
val config = providers.gradleProperty("config").orElse("default")
// Không nên eager read khi chỉ muốn nối property:
val chosen = config.get()
~~~

Thay bằng:

~~~kotlin
tasks.register<GenerateMessage>("generateMessage") {
    message.set(config)
}
~~~

Để task action gọi `message.get()` khi task chạy; việc Gradle tính fingerprints có thể đọc value vào thời điểm cần thiết trước action.

### 11.3. get() trong TaskAction thường là đúng

~~~kotlin
@TaskAction
fun work() {
    val value = message.get()
    // Xử lý task input được khai
}
~~~

Managed input values được yêu cầu trong execution, lúc đó đọc là bình thường. Cần tránh đọc undeclared external state, Project API hoặc biến global biến động ở action.

### 11.4. Khác biệt về missing values

`Provider.get()` có thể ném lỗi nếu không có giá trị. Dùng `orElse(default)`, `orNull` hoặc `isPresent` tùy semantics, đồng thời khai input là required/optional đúng. **Không** đưa default giả nguy hiểm cho credentials hoặc đường file bắt buộc chỉ để build không fail.

## 12. Tránh afterEvaluate và taskGraph.whenReady như một “migration shortcut”

### 12.1. Vì sao afterEvaluate thường bị lạm dụng?

Code cũ:

~~~kotlin
afterEvaluate {
    tasks.getByName("compileJava") {
        // Đợi plugin tạo task rồi mới cấu hình
    }
}
~~~

Mẫu này khiến configuration phụ thuộc thứ tự callback, Gradle project evaluation state, composite plugins và có thể buộc task realization. Với Configuration Cache, lifecycle callbacks còn có constraints riêng.

### 12.2. Khi plugin Java đã apply

~~~kotlin
plugins {
    java
}

tasks.named<JavaCompile>("compileJava") {
    options.encoding = "UTF-8"
}
~~~

Không cần `afterEvaluate`: Java plugin đã register task. Cấu hình được trì hoãn bằng `named`.

### 12.3. Khi một plugin có thể apply muộn

Một plugin/convention script có thể dùng:

~~~kotlin
pluginManager.withPlugin("java") {
    tasks.withType<JavaCompile>().configureEach {
        options.encoding = "UTF-8"
    }
}
~~~

`withPlugin` đăng ký callback khi plugin với ID đó đã được apply. Khi callback chạy, ta chỉ **đăng ký configureEach action** cho JavaCompile tasks, không cần lấy task object ngay. Đây là fragment cho Kotlin DSL có import `JavaCompile`.

### 12.4. Tránh taskGraph.whenReady

`gradle.taskGraph.whenReady { ... }` là pattern lịch sử để sửa tasks khi graph đã dựng. Nó gây phụ thuộc lifecycle và không phù hợp nhiều Configuration Cache use cases. Thay vì chờ “taskGraph ready” để đổi property:

- Khai property trong task type.
- Configure task bằng `named`/`configureEach`.
- Nối producer→consumer với providers.
- Dùng Gradle services/Build Services cho execution coordination cần thiết.
- Dùng TaskProvider relationships cho ordering.

Đừng dùng callback để mutate output path sau khi task inputs/outputs đã được snapshot.

### 12.5. Tránh eager Project API trong task actions

Gradle docs khuyến cáo tránh truy `project` trong `@TaskAction` vì Configuration Cache task state phải serializable/isolated. Nếu task cần `project.version`, truyền từ configuration vào một `@Input Property<String>` qua Provider, rồi action đọc property.

## 13. Lab đầy đủ: Java 17 + hai typed tasks + lazyProbe

Lab này được thiết kế để **quan sát riêng ba điều**:

1. Task `lazyProbe` đã được **register** nhưng không configure khi chỉ chạy `help`.
2. `uppercaseMessage` nhận input từ `generateMessage` qua `flatMap`; Gradle suy ra producer task dependency và thực thi đúng thứ tự.
3. Java application `Main` đọc resource do `generateMessage` tạo và `processResources` copy, cho thấy lazy wiring có hiệu lực trong một Java17 build thật.

### 13.1. Cấu trúc project

~~~text
lazy-migration-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    └── main/
        └── java/
            └── demo/
                └── lazy/
                    ├── Main.java
                    └── StandaloneCheck.java
~~~

Yêu cầu: Java 17+, bản Gradle hỗ trợ JDK running Gradle và Java17 toolchains. Lab chỉ dùng **core Application plugin** và Java standard library, không cần tải dependency Maven. Nếu project có Wrapper thì dùng `./gradlew` (Windows `gradlew.bat`); khi chưa có Wrapper, dùng `gradle` cài sẵn.

### 13.2. settings.gradle.kts

~~~kotlin
rootProject.name = "lazy-migration-lab"
~~~

### 13.3. build.gradle.kts — toàn bộ file

~~~kotlin
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.util.Locale
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.language.jvm.tasks.ProcessResources

plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}

application {
    mainClass.set("demo.lazy.Main")
}

@CacheableTask
abstract class GenerateMessage : DefaultTask() {
    @get:Input
    abstract val message: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val target = outputFile.get().asFile.toPath()
        Files.createDirectories(target.parent)
        Files.writeString(
            target,
            message.get() + "\n",
            StandardCharsets.UTF_8
        )
    }
}

@CacheableTask
abstract class UppercaseMessage : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val inputFile: RegularFileProperty

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun convert() {
        val source = Files.readString(
            inputFile.get().asFile.toPath(),
            StandardCharsets.UTF_8
        ).trimEnd('\r', '\n')

        val result = source.uppercase(Locale.ROOT)
        val target = outputFile.get().asFile.toPath()
        Files.createDirectories(target.parent)
        Files.writeString(
            target,
            result + "\n",
            StandardCharsets.UTF_8
        )

        println("TRANSFORM_RESULT=" + result)
    }
}

// Chỉ đăng ký; task chưa cần realized ngay.
val generator = tasks.register<GenerateMessage>("generateMessage") {
    group = "documentation"
    message.convention(
        providers.gradleProperty("message")
            .orElse("hello lazy gradle")
    )
    outputFile.convention(
        layout.buildDirectory.file("generated/messages/message.txt")
    )
}

tasks.register<UppercaseMessage>("uppercaseMessage") {
    group = "verification"
    inputFile.set(generator.flatMap { it.outputFile })
    outputFile.set(
        layout.buildDirectory.file("generated/messages/upper.txt")
    )
}

// Provider output làm nguồn CopySpec; Gradle biết producer.
tasks.named<ProcessResources>("processResources") {
    from(generator.flatMap { it.outputFile }) {
        into("messages")
    }
}

// Task riêng để nhìn rõ CONFIGURATION khác EXECUTION.
tasks.register("lazyProbe") {
    group = "verification"
    println("PROBE_CONFIGURATION=YES")
    doLast {
        println("PROBE_EXECUTION=YES")
    }
}
~~~

### 13.4. Tại sao đây là cấu hình lazy thật?

- `tasks.register<GenerateMessage>` trả `TaskProvider<GenerateMessage>` thay vì instance.
- `message.convention(providers.gradleProperty(...).orElse(...))` giữ giá trị đến từ Provider và có default.
- `outputFile.convention(layout.buildDirectory.file(...))` giữ output path lazily.
- `inputFile.set(generator.flatMap { it.outputFile })` tạo **dependency mang output producer identity**; không cần `dependsOn(generator)` tường minh.
- `tasks.named<ProcessResources>("processResources")` cấu hình một task tồn tại của Application/Java plugin mà không eager instantiate nó.
- `from(generator.flatMap { it.outputFile })` copy generated file vào `build/resources/main/messages/message.txt`; Gradle theo dõi producer identity.
- `@CacheableTask` hợp lệ vì outputs phụ thuộc declared inputs, deterministic text encoding và không chứa timestamps/random.
- `@PathSensitive(NONE)` trong UppercaseMessage đúng vì transform chỉ dùng bytes của một single input file; filename không vào output.
- `tasks.withType<JavaCompile>().configureEach` áp encoding/Java release khi cần compile, không eager-configure mọi compiler task.
- `lazyProbe` in marker **trong configuration action**, rồi action marker **trong doLast**; chúng là instrumentation học tập, không phải pattern production để log mọi task.

### 13.5. src/main/java/demo/lazy/Main.java

~~~java
package demo.lazy;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        try (InputStream input = Main.class.getResourceAsStream(
                "/messages/message.txt")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing generated resource: messages/message.txt");
            }

            String content = new String(
                    input.readAllBytes(), StandardCharsets.UTF_8)
                    .stripTrailing();

            System.out.println("JAVA_APP=" + content);
        }
    }
}
~~~

Khi Gradle thực thi `run`, Application plugin chuẩn bị `classes`/`processResources` và runtime classpath; file `message.txt` được copy vào resources, nên `getResourceAsStream` lấy được. Không cần hard-code `build/generated` path trong Java code; Java application đọc classpath resource đúng nghĩa.

### 13.6. src/main/java/demo/lazy/StandaloneCheck.java

~~~java
package demo.lazy;

import java.util.Locale;

public final class StandaloneCheck {
    private StandaloneCheck() {
    }

    public static void main(String[] args) {
        String raw = "hello lazy gradle";
        System.out.println(
                "STANDALONE=" + raw.toUpperCase(Locale.ROOT)
        );
    }
}
~~~

Đây là chương trình Java 17 độc lập, không cần Gradle hay generated resource để chạy. Nó cho phép kiểm `javac`/`java` nhanh và có stdout cố định.

### 13.7. Chạy thử 1: help không cần lazyProbe

Từ thư mục `lazy-migration-lab`:

~~~bash
gradle help --quiet
~~~

Gradle hiển thị phần help mặc định. Trong build tối giản, **không xuất hiện**:

~~~text
PROBE_CONFIGURATION=YES
PROBE_EXECUTION=YES
~~~

vì `lazyProbe` chỉ được registered, chưa phải task cần thiết trong `help` graph. Nếu một plugin khác chủ động realize toàn bộ tasks, bạn có thể vẫn thấy marker configuration; đó là tín hiệu cần điều tra.

### 13.8. Chạy thử 2: yêu cầu lazyProbe

~~~bash
gradle lazyProbe --quiet
~~~

Trong lab này, hai marker được in **theo thứ tự**:

~~~text
PROBE_CONFIGURATION=YES
PROBE_EXECUTION=YES
~~~

Dòng đầu phát ra lúc task được configured; dòng sau khi `doLast` action chạy. Nếu dùng Configuration Cache có cache hit, configuration phase có thể không chạy lại và marker đầu có thể vắng; để quan sát đúng sự khác biệt, không bật Configuration Cache trong test này hoặc thêm `--no-configuration-cache`.

### 13.9. Chạy thử 3: implicit producer dependency

~~~bash
gradle clean uppercaseMessage --quiet
~~~

Ở lần thực thi task action, marker:

~~~text
TRANSFORM_RESULT=HELLO LAZY GRADLE
~~~

Gradle cần `generateMessage` trước `uppercaseMessage` vì consumer file property nhận provider của producer output. Output files:

~~~text
build/generated/messages/message.txt
build/generated/messages/upper.txt
~~~

Nội dung `message.txt`:

~~~text
hello lazy gradle
~~~

Nội dung `upper.txt`:

~~~text
HELLO LAZY GRADLE
~~~

Hai files có newline cuối dòng. Nếu bỏ `clean` và chạy `uppercaseMessage` lần hai, Gradle có thể báo `UP-TO-DATE` và action không in marker nữa; đó là **task output avoidance**, không phải mất TaskProvider wiring.

### 13.10. Chạy thử 4: Java application đọc generated resource

~~~bash
gradle clean run --quiet
~~~

Stdout ổn định từ Java main:

~~~text
JAVA_APP=hello lazy gradle
~~~

Task `run` lấy classpath từ Application plugin; `processResources` cần output của `generateMessage`. Nếu bạn tự chạy `java -cp build/classes/java/main demo.lazy.Main` mà không thêm `build/resources/main` vào classpath, program sẽ fail vì thiếu resource — đó là classpath của lệnh Java thủ công, không phải lỗi Gradle lazy configuration.

### 13.11. Chạy thử 5: truyền property lazily

~~~bash
gradle clean uppercaseMessage -Pmessage="welcome team" --quiet
~~~

Khi `GenerateMessage.message` nhận property mới và task chạy, stdout:

~~~text
TRANSFORM_RESULT=WELCOME TEAM
~~~

Output file cũng đổi thành `WELCOME TEAM`. `-Pmessage` là **Gradle project property**; nếu consumer dùng `message.convention(providers.gradleProperty(...))`, Gradle nhận input value thay đổi và up-to-date/build-cache keys tương ứng.

### 13.12. Chạy thử 6: kiểm task graph mà không thực thi actions

~~~bash
gradle uppercaseMessage --dry-run --console=plain
~~~

Gradle hiển thị các task được scheduled, ví dụ `:generateMessage` và `:uppercaseMessage`, nhưng không chạy actions và không tạo files nếu chúng chưa tồn tại. `--dry-run` hữu ích để kiểm implicit dependency; nó **không chứng minh output contents đúng**.

### 13.13. Chạy thử 7: xem task outcomes

~~~bash
gradle uppercaseMessage --info --console=plain
~~~

Quan sát lý do task UP-TO-DATE hoặc re-executed, dependency graph và inputs/outputs. Sau first build thành công, lần sau có thể skipped. Không xem `--info` text là API contract vì wording thay theo version.

### 13.14. Chạy thử 8: Configuration Cache

~~~bash
gradle uppercaseMessage --configuration-cache --console=plain
gradle uppercaseMessage --configuration-cache --console=plain
~~~

Lần đầu Gradle có thể lưu configuration/task graph; lần sau có thể reuse nếu inputs/config không đổi và build logic đáp ứng constraints. Đây là cơ chế **khác với lazy registration**. Nếu test bằng `lazyProbe`, marker configuration không in lần sau chưa chắc có nghĩa task không được realized; có thể vì Configuration Cache đã reuse state.

### 13.15. Chạy javac/java độc lập, không cần Gradle

Linux/macOS từ project root:

~~~bash
mkdir -p manual-out
javac --release 17 -d manual-out \
    src/main/java/demo/lazy/StandaloneCheck.java
java -cp manual-out demo.lazy.StandaloneCheck
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force manual-out | Out-Null

javac --release 17 -d manual-out src\main\java\demo\lazy\StandaloneCheck.java

java -cp manual-out demo.lazy.StandaloneCheck
~~~

Khi dùng Java17, stdout **chính xác**:

~~~text
STANDALONE=HELLO LAZY GRADLE
~~~

Điều này chứng minh Java source độc lập compile/run. Nó **không** chứng minh Gradle task graph hay Configuration Cache; các mục 13.7–13.14 mới là thí nghiệm Gradle.

## 14. Trước/sau: Java plugin trong một repo thực tế

### 14.1. Trước khi migrate

~~~kotlin
plugins {
    java
}

val sourceJar = tasks.create("sourceArchive", Jar::class.java) {
    archiveClassifier.set("sources")
    from(sourceSets.main.get().allSource)
}

tasks.getByName("assemble").dependsOn(sourceJar)
~~~

Đây là snippet legacy: `create` tạo task eager; `getByName` buộc realization của `assemble`; `sourceSets.main.get()` đọc source set object ngay trong configuration. Nếu chỉ chạy `help`, có thể tốn công cấu hình `sourceArchive` không cần thiết.

### 14.2. Sau khi migrate

~~~kotlin
plugins {
    java
}

val sourceArchive = tasks.register<Jar>("sourceArchive") {
    archiveClassifier.set("sources")
    from(sourceSets.main.get().allSource)
}

tasks.named("assemble") {
    dependsOn(sourceArchive)
}
~~~

Dù `sourceSets.main.get()` xuất hiện, nó **nằm trong deferred task configuration action**, không phải top-level eager evaluation. Migrate thêm Provider wiring khi source data thực sự cần lazy hơn.

### 14.3. Sử dụng built-in sourcesJar nếu hợp lệ

Trong Java plugin hiện đại, có thể thay custom task tự viết:

~~~kotlin
java {
    withSourcesJar()
}
~~~

Gradle sẽ đăng ký task nguồn tương ứng. Trong project publish library, đây thường là API ưu tiên hơn việc tự tạo Jar task, nhưng cần kiểm publish variants/artifact contract. Mục tiêu migration không phải nhất thiết giữ mọi custom task khi Gradle đã có API chuẩn.

### 14.4. Khi plugin đã có task name

Nếu plugin/Gradle đã đăng ký `sourcesJar`, không đăng ký task khác cùng tên. Dùng `tasks.named<Jar>("sourcesJar") { ... }` khi muốn configure task đã có. Task name collision không được sửa bằng cách dùng `getByName`.

## 15. Migrate producer/consumer từ eager file paths

### 15.1. Before: hard-coded file và dependsOn thủ công

~~~kotlin
val generator = tasks.create("generateConfig") {
    doLast {
        file("build/generated/config.txt")
            .writeText("value=123")
    }
}

tasks.create("consumeConfig") {
    dependsOn(generator)
    doLast {
        println(
            file("build/generated/config.txt").readText()
        )
    }
}
~~~

Đây là **anti-pattern chỉ minh họa**, không dùng cho production:

- Hai tasks được created eagerly.
- Không khai `@InputFile` hoặc `@OutputFile`.
- Hard-code output path ở hai nơi.
- `Project.file` bị gọi trong actions (vấn đề Configuration Cache).
- Không có input fingerprints để Gradle skip đúng.
- Cần maintain `dependsOn` bằng tay; đổi output path dễ lệch consumer.

### 15.2. After: typed tasks + Provider wiring

~~~kotlin
val generator = tasks.register<GenerateMessage>("generateConfig") {
    message.convention("value=123")
    outputFile.convention(
        layout.buildDirectory.file("generated/config.txt")
    )
}

tasks.register<UppercaseMessage>("consumeConfig") {
    inputFile.set(generator.flatMap { it.outputFile })
    outputFile.set(
        layout.buildDirectory.file("generated/config-uppercase.txt")
    )
}
~~~

Đây là **fragment dùng typed classes của lab**, không phải một build script độc lập thứ hai. Task properties đã khai inputs/outputs; file path dùng `layout.buildDirectory`; task dependency được suy ra qua provider producer output.

### 15.3. Đổi build directory không sửa mọi task

Nếu output được đặt qua `layout.buildDirectory.file("...")`, khi build directory được đổi trong cấu hình project, provider chain có thể tự cập nhật theo contract. Hard-coded `file("build/...")` sẽ không tự theo vị trí mới.

### 15.4. Không nhầm inputFile.set(File) với producer provider

Nếu consumer chỉ:

~~~kotlin
inputFile.set(
    layout.buildDirectory.file("generated/config.txt")
)
~~~

nó biết đường file nhưng **không tự biết task nào tạo file**. Với producer output provider:

~~~kotlin
inputFile.set(
    generator.flatMap { it.outputFile }
)
~~~

Gradle có thông tin provenance để suy ra dependency. Nếu đi qua `File.absolutePath` hoặc string, metadata producer dễ bị đánh mất.

### 15.5. FileCollection và task output

Với nhiều producer tasks, có thể wire `ConfigurableFileCollection.from(taskProviders)`, hoặc dùng từng output property providers, tùy API và semantics. Tránh ghép paths bằng raw file lists rồi lạm dụng `dependsOn` thủ công.

## 16. Lazy task configuration vs task dependencies: một câu hỏi logic

Hãy xét:

~~~kotlin
val a = tasks.register("a")
val b = tasks.register("b") {
    dependsOn(a)
}
~~~

Khi chỉ chạy `help`:

- Gradle **biết** `a` và `b`.
- Không vì `b.dependsOn(a)` mà chắc chắn phải realize cả hai ngay.
- Không có task action của `a`/`b` chạy nếu chúng không được scheduled.

Khi chạy `b`:

- `b` cần realized để tạo graph.
- Strong dependency `a` cũng cần được realized và scheduled.
- Task actions chạy theo dependency order, trừ khi bị skip/up-to-date/failed.

Với:

~~~kotlin
val a = tasks.register("a")
tasks.register("b") {
    mustRunAfter(a)
}
~~~

`mustRunAfter` **không tự schedule a** khi chỉ chạy `b`. Đó là ordering relationship, không phải dependency. Đừng thay `dependsOn` bằng `mustRunAfter` với hy vọng tăng laziness mà làm mất file producer requirement.

## 17. Cách migrate plugin apply code

### 17.1. Eager plugin code kiểu cũ

~~~kotlin
class BuildPlugin : Plugin<Project> {
    override fun apply(project: Project) {
        project.tasks.create("verifyApi") {
            // eager
        }
    }
}
~~~

Đây là **Kotlin source fragment** cần Gradle API imports, không phải Java17 standalone program. Khi plugin apply trên nhiều modules, mỗi project eager-create task ngay cả khi chỉ chạy `help`.

### 17.2. Lazy plugin registration

~~~kotlin
class BuildPlugin : Plugin<Project> {
    override fun apply(project: Project) {
        project.tasks.register("verifyApi") {
            group = "verification"
            description = "Checks API when explicitly requested"
            doLast {
                println("VERIFY_API=YES")
            }
        }
    }
}
~~~

Cải thiện creation, nhưng để hỗ trợ Configuration Cache và production-quality outputs, cần tiến thêm một bước: custom typed task với managed input/output properties, không capture `Project` trong task action.

### 17.3. Plugin extension với Property

Một extension kiểu Kotlin/Java Gradle API có:

~~~kotlin
abstract class ReportExtension {
    abstract val title: Property<String>
}
~~~

và task:

~~~kotlin
@CacheableTask
abstract class ReportTask : DefaultTask() {
    @get:Input
    abstract val title: Property<String>

    @get:OutputFile
    abstract val reportFile: RegularFileProperty

    @TaskAction
    fun runReport() {
        val target = reportFile.get().asFile.toPath()
        Files.createDirectories(target.parent)
        Files.writeString(
            target,
            title.get() + "\n",
            StandardCharsets.UTF_8
        )
    }
}
~~~

Các fragments trên cần imports như `DefaultTask`, `Property`, `Files`, `StandardCharsets` và annotations. Không coi chúng là file độc lập nếu thiếu boilerplate.

Plugin apply wiring:

~~~kotlin
val ext = project.extensions.create(
    "reportConfig", ReportExtension::class.java
)
ext.title.convention("Summary")

project.tasks.register(
    "report", ReportTask::class.java
) {
    it.title.convention(ext.title)
    it.reportFile.convention(
        project.layout.buildDirectory.file("reports/summary.txt")
    )
}
~~~

Đây là snippet Kotlin **plugin class apply**; type references tương ứng phải được định nghĩa trong plugin project. Task action chỉ dùng properties, không truy `project`. Consumer có thể override extension title trước khi property được finalized.

### 17.4. Không đọc extension value ngay khi apply

Anti-pattern:

~~~kotlin
val titleNow = ext.title.get()
project.tasks.register("report") {
    // titleNow bị khóa vào giá trị lấy sớm
}
~~~

Nếu build author sau đó viết `reportConfig { title.set("Custom") }`, giá trị `titleNow` có thể đã được resolve trước override. Dùng `task.title.convention(ext.title)` hoặc `set(ext.title)` theo contract, giữ provider chain.

### 17.5. pluginManager.withPlugin đúng nơi

Để configure JavaCompile khi plugin Java được apply:

~~~kotlin
project.pluginManager.withPlugin("java") {
    project.tasks.withType(JavaCompile::class.java)
        .configureEach {
            it.options.encoding = "UTF-8"
        }
}
~~~

Đây là plugin source fragment; `Project` access trong `apply`/configuration là bình thường. Vấn đề là truy `Project` trong `@TaskAction` hoặc capture một model object vào serialized task state.

## 18. Configuration Cache: liên quan nhưng khác lazy configuration

**Task configuration avoidance** làm giảm số tasks phải instantiate/configure trên invocation đang cấu hình.

**Configuration Cache** lưu kết quả configuration/task graph để invocation sau có thể **không cấu hình lại** khi cache hit.

| Cơ chế | Tối ưu cái gì? | Ví dụ |
| --- | --- | --- |
| Task configuration avoidance | Không realize/configure tasks không cần | `register`, `named`, `configureEach` |
| Lazy properties | Không tính value trước khi cần | `Property`, `Provider.map`/`flatMap` |
| Configuration Cache | Reuse configured graph ở lần chạy sau | `--configuration-cache` |
| Build Cache | Reuse task outputs | `--build-cache` |
| Up-to-date checks | Skip unchanged task action | `UP-TO-DATE` |
| Daemon | Reuse JVM/JIT/in-memory caches | Gradle Daemon PID |

### 18.1. Lazy không tự động Configuration Cache compatible

Một task được register lazy nhưng action gọi:

~~~kotlin
tasks.register("badAction") {
    doLast {
        println(project.name)
    }
}
~~~

đang truy `Project` trong task action. Với Configuration Cache, đây là pattern bị hạn chế. Sửa bằng typed `@Input Property<String>` được set khi configuration và action chỉ đọc property, hoặc trong snippet đơn giản capture một serializable value đúng cách (vẫn cần kiểm task state).

### 18.2. Configuration Cache không thay task lazy

Nếu một build eager-create hàng nghìn tasks ở **lần cache miss**, lần đầu vẫn chậm. Cải thiện task configuration avoidance giúp miss path nhanh hơn và giảm model work. Khi Configuration Cache hit, configuration có thể bị skip, nhưng không vì vậy mà migration eager API trở thành vô nghĩa.

### 18.3. Chẩn đoán Configuration Cache

~~~bash
gradle uppercaseMessage --configuration-cache
gradle uppercaseMessage --configuration-cache
~~~

Quan sát "configuration cache stored/reused" trong output Gradle version tương ứng. Với lỗi, đọc report trong project `build/reports/configuration-cache` hoặc đường report được Gradle in; không đoán mọi report path giống nhau trên tất cả versions.

### 18.4. Không sửa bằng warnings mode vô hạn

Một số phiên bản Gradle hỗ trợ tùy chọn về configuration-cache problems. Việc bật chế độ bỏ qua warnings để có “cache hit” không phải migration hoàn chỉnh. Giải quyết vấn đề plugin/tasks với Provider/managed state và kiểm correctness.

### 18.5. Cập nhật lưu ý theo Gradle mới

Gradle docs hiện hành nhấn mạnh Configuration Cache có những behavior riêng khi serialize dependency configurations, và với các bản Gradle hiện đại việc sync IDE không mặc nhiên hưởng lợi từ Configuration Cache, trong khi task execution được IDE delegate cho Gradle có thể sử dụng nó. Đừng đồng nhất “IDE sync nhanh” với “Configuration Cache hit”; đọc docs đúng Gradle Wrapper version.

## 19. Migration không được đánh đổi correctness

### 19.1. Configuration action có thể không chạy

Trong eager build, một task configuration action có thể được tác giả dùng như side effect:

~~~kotlin
tasks.create("collectOutputs") {
    allOutputs.add("build/reports/output.txt")
}
~~~

Nếu migrate thành `tasks.register`, action có thể **không chạy** với `help` hoặc một build không yêu cầu task. Nếu `allOutputs` được dùng cho logic khác trong configuration, hành vi sẽ khác.

**Sửa:** đưa shared model state vào extension/provider/task inputs rõ ràng, không dựa vào side effects của task configuration action.

### 19.2. Configuration order không được giả định

Với lazy APIs, action có thể chạy sớm, muộn hoặc không chạy. Không dùng side effects trong `tasks.register("x") { ... }` để mặc định một task khác đã được configure.

### 19.3. Configuration action chỉ nên mutate current task

Ví dụ dễ sai:

~~~kotlin
val assembleTask = tasks.named("assemble")

tasks.register("docs") {
    assembleTask.get().dependsOn(this)
}
~~~

Khi `docs` configuration chạy, nó force realize `assemble` và mutate cross-task state. Thay bằng:

~~~kotlin
val docs = tasks.register("docs")

tasks.named("assemble") {
    dependsOn(docs)
}
~~~

Ngoài ra cần tự hỏi liệu `assemble` có nên luôn phụ thuộc docs không. Nếu không, đừng nối task graph chỉ để giữ legacy behavior vô nghĩa.

### 19.4. Provider có thể bị đọc quá sớm qua string interpolation

Anti-pattern:

~~~kotlin
val outputProvider =
    layout.buildDirectory.file("generated/output.txt")

println("Output is " + outputProvider.get().asFile)
~~~

Chỉ để log một đường file mà đã resolve Provider. Khi có configuration-time variable provider, thói quen này có thể ảnh hưởng performance/cache inputs và khiến build phụ thuộc evaluation order. Nếu cần log, dùng task action hoặc Gradle APIs có mục đích, không force values trong build logic thường xuyên.

### 19.5. Lazy does not mean thread-safe automatically

Nếu custom plugin có mutable shared collections/variables bên ngoài task instances, lazy configuration có thể làm ordering khó đoán hơn. Configuration Cache/parallel execution còn đặt ra isolation constraints. Nên dùng immutable provider chains, declarative task graphs và shared Build Services khi thật sự cần phối hợp resources.

## 20. Multi-project builds và configuration avoidance

Trong multi-project project:

~~~text
root/
├── settings.gradle.kts
├── build-logic/
├── api/
├── service/
└── app/
~~~

Một root script cũ:

~~~kotlin
subprojects {
    tasks.withType<JavaCompile>().all {
        options.encoding = "UTF-8"
    }
}
~~~

có thể eagerly configure JavaCompile tasks trên nhiều modules. Nó còn tạo cross-project configuration coupling, không thuận lợi cho Isolated Projects và configuration optimization.

### 20.1. Migrate bước nhỏ

Bước đầu:

~~~kotlin
subprojects {
    tasks.withType<JavaCompile>().configureEach {
        options.encoding = "UTF-8"
    }
}
~~~

Ít nhất không eagerly realize matching tasks chỉ vì `all`. Nhưng root `subprojects` mutation vẫn tạo coupling.

### 20.2. Convention plugin tốt hơn khi scale

Nên đóng gói rule vào **convention plugin** và apply ở modules cần Java compilation. Trong mỗi project, plugin:

~~~kotlin
pluginManager.withPlugin("java") {
    tasks.withType<JavaCompile>().configureEach {
        options.encoding = "UTF-8"
    }
}
~~~

Không cần root project đi cấu hình task objects của sibling projects. Tùy build-logic design, dùng precompiled script plugin hoặc binary plugin. Đảm bảo plugin được apply ở đúng modules.

### 20.3. Task configuration avoidance không phải configuration-on-demand

Gradle từng có mode **configure-on-demand**/isolated project model khác. `tasks.register` không tự bảo Gradle chỉ configure project `:app` và bỏ mọi subprojects. Nó chỉ tránh eager **task object configuration** nơi có thể. Multi-project configuration cần giải quyết riêng qua convention plugins, build structure, Configuration Cache/Isolated Projects theo Gradle version.

### 20.4. Included builds và composite builds

Included build có settings/buildscripts/task graph riêng. Một dependency được substituted bằng included build có thể yêu cầu tasks ở included build khi consumer cần artifact. Không coi task trong included build “không chạy” chỉ vì root build `help` không thấy nó; cần xem task graph thật.

## 21. Cách đo kết quả migration

### 21.1. Dùng help để đo configuration work

Gradle documentation khuyên dùng `help` làm baseline vì nó là task nhẹ và không đòi tạo compiler/test tasks của application.

~~~bash
gradle help --console=plain
~~~

So before/after về task created/configured count (nếu profiling/Build Scan có), elapsed time và logs. Nếu không có instrumentation, đừng giả số tasks mà chỉ dựa một timing.

### 21.2. So sample nhiều lần

Một lần đo không đủ vì Daemon/JIT/wrapper/dependency caches khác nhau. Với repo dùng Wrapper:

~~~bash
./gradlew --stop

./gradlew help --console=plain
./gradlew help --console=plain
./gradlew help --console=plain
~~~

Dùng để quan sát cold/warm effects. Muốn so migration, dùng cùng Gradle/JDK/flags và nhiều repeats, không tự stop giữa các warm iterations.

### 21.3. Build Scan/Develocity

Nếu tổ chức có quyền dùng scan:

~~~bash
./gradlew help --scan
~~~

Gradle/Develocity có thể cung cấp configuration time, task configuration details, task graph và cache insights tùy tool version. Không upload build scans chứa metadata nhạy cảm ra public khi chưa có policy.

### 21.4. Profile CLI

~~~bash
./gradlew help --profile
~~~

Gradle có profiling report, có thể giúp phân biệt configuration/task execution chi phí chính. Đừng dựa hoàn toàn vào milliseconds của một run nếu OS filesystem/network đang có biến động.

### 21.5. Benchmark đúng metric

| Metric | Vì sao quan trọng |
| --- | --- |
| Configuration elapsed time | Có giảm khi tránh eager tasks? |
| Tasks created/configured | Có giảm cho `help`/unrelated task? |
| Requested task graph | Có mất dependency/task ordering không? |
| Task outcome | Có correctness/up-to-date/cache behavior không? |
| Output bytes | File generated/compiled có giữ nguyên contract không? |
| Configuration Cache reports | Có task action capture Project/unsupported state? |
| Peak memory | Lazy migration có giảm allocations/RSS không? |
| IDE sync | Model import có nhận đúng tasks/source roots không? |
| CI | Build/test/release artifacts có giống trước không? |

### 21.6. Migration success không đo bằng “ít task chạy” đơn độc

Cấu hình lazy có thể khiến `help` nhanh, nhưng nếu một build `assemble` thực sự cần rất nhiều tasks, các task đó vẫn phải được configured/executed. Mục tiêu là **không làm công việc vô ích**, không phải lược bỏ tasks cần thiết.

## 22. Phương pháp migrate theo từng đợt

### Đợt 1 — Snapshot baseline

Ghi:

- Gradle Wrapper/JDK versions.
- `gradle help` configuration time.
- `gradle test` và `assemble` task outcomes.
- Artifacts/checksums với inputs cố định.
- Build Scan/profile (nếu được phép).
- Configuration Cache diagnostics.
- IDE sync + custom plugin behavior cần giữ.

### Đợt 2 — Chuyển creation APIs

- `tasks.create` → `tasks.register`.
- Chỉnh biến kiểu `Task` → `TaskProvider<Task>` hoặc `TaskProvider<MyTask>`.
- Thay `getByName`→`named`, giữ provider.
- Tránh instant `get()` trong configuration.

### Đợt 3 — Chuyển collection actions

- `tasks.all`→`tasks.configureEach`.
- `tasks.withType<T>().all`→`tasks.withType<T>().configureEach`.
- Bỏ `withType(T::class.java, Action)` eager overload khi thích hợp.
- Kiểm predicate/collection iteration có buộc realization không.
- Tránh cross-task mutation trong actions.

### Đợt 4 — Chuyển inputs/outputs sang Provider API

- Raw `File` fields→`RegularFileProperty` hoặc `DirectoryProperty`.
- Runtime values→`Property<T>` và `@Input`.
- File outputs→`@OutputFile` / `@OutputDirectory`.
- File inputs→`@InputFile`/`@InputFiles` kèm PathSensitivity đúng.
- Output producer→consumer bằng `TaskProvider.flatMap`.
- Tách I/O/network khỏi configuration phase khi được.

### Đợt 5 — Gỡ lifecycle hacks

- Loại `afterEvaluate` dùng để lấy task mà plugin vừa tạo.
- Thay `taskGraph.whenReady` mutation bằng task declarations/Provider.
- Dùng `pluginManager.withPlugin` cho plugin-order dependent wiring.
- Chuyển root `allprojects/subprojects` configuration sang convention plugins khi scale.

### Đợt 6 — Kiểm correctness và performance

- Run `help` để kiểm không configure unrelated tasks.
- Run `test`/`assemble`/`run` và so outputs.
- Run Gradle TestKit functional tests khi có reusable plugin.
- Kiểm Configuration Cache.
- Đọc diagnostics/Build Scan và so before-after.
- Chỉ merge khi behavior không bị thay đổi ngoài chủ đích.

## 23. Groovy DSL migration

Cùng API semantics áp dụng cho Gradle Groovy DSL.

### 23.1. Eager Groovy mẫu cũ

~~~groovy
tasks.create('hello') {
    doLast {
        println 'HELLO=YES'
    }
}

tasks.getByName('test') {
    maxHeapSize = '512m'
}

tasks.withType(JavaCompile).all {
    options.encoding = 'UTF-8'
}
~~~

Đây là **snippet** dành cho project có Java plugin (task `test` tồn tại), không phải complete project.

### 23.2. Lazy Groovy tương đương

~~~groovy
def hello = tasks.register('hello') {
    doLast {
        println 'HELLO=YES'
    }
}

tasks.named('test') {
    maxHeapSize = '512m'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

`tasks.register` trả `TaskProvider`. `tasks.named` và `configureEach` không buộc mọi matching task realized ngay.

### 23.3. Groovy API cho typed tasks

~~~groovy
def generator = tasks.register(
    'generateMessage', GenerateMessage
) {
    message.convention(
        providers.gradleProperty('message')
            .orElse('hello lazy gradle')
    )
    outputFile.convention(
        layout.buildDirectory.file('generated/messages/message.txt')
    )
}

tasks.register('uppercaseMessage', UppercaseMessage) {
    inputFile.set(
        generator.flatMap { it.outputFile }
    )
    outputFile.set(
        layout.buildDirectory.file('generated/messages/upper.txt')
    )
}
~~~

Đây là **fragment** chỉ hợp lệ khi typed task classes `GenerateMessage`/`UppercaseMessage` được định nghĩa trong plugin/buildSrc với cùng input/output property contract; nó **không** phải một Groovy build script chạy độc lập.

### 23.4. Source of truth là build logic, không IDE

Nếu IDE Gradle import/reload thành công sau migration nhưng CLI `test`/`jar` fail, không coi là hoàn thành. IDE model có thể nhận task names mà task dependencies/input file wiring sai. Phải chạy đầy đủ Gradle tasks và tests.

## 24. Lỗi phổ biến khi chuyển từ eager sang lazy

### Lỗi 1. Thay create bằng register nhưng vẫn gọi get ngay

~~~kotlin
val x = tasks.register("x")
x.get()
~~~

**Sửa:** giữ `TaskProvider` và configure/depend qua provider.

### Lỗi 2. getByName vẫn nằm trong plugin

**Sửa:** `named("task")` và `configure { }` hoặc `configureEach`. Chỉ get instance tại boundary có lý do.

### Lỗi 3. withType.all trên nhiều project

**Sửa:** `withType<T>().configureEach`; xem có thể chuyển rule vào convention plugin không.

### Lỗi 4. Đặt side effects trong task configuration

Nếu action không chạy vì task không realized, global mutable state thiếu dữ liệu.

**Sửa:** khai data model ở extension/Provider, không dùng task config action để biến đổi unrelated objects.

### Lỗi 5. Mutate task khác trong một task configuration action

Ordering trở thành ngẫu nhiên và có thể force realization.

**Sửa:** cấu hình task đích qua `tasks.named` riêng.

### Lỗi 6. Dùng taskGraph.whenReady để cấu hình output

Có thể quá muộn và không compatible Configuration Cache.

**Sửa:** khai output provider khi task registration/configuration.

### Lỗi 7. afterEvaluate chỉ để chờ Java plugin

**Sửa:** `plugins { java }` và `tasks.named` hoặc `pluginManager.withPlugin("java")`.

### Lỗi 8. tasks.named với task chưa tồn tại

`named` yêu cầu task đã được registered; nó không tự tạo task.

**Sửa:** apply đúng plugin hoặc đăng ký task, rồi mới configure provider; dùng plugin callbacks khi registration order khác.

### Lỗi 9. Nhầm task registered với task executed

Thấy task trong `gradle tasks` không có nghĩa doLast đã chạy.

**Sửa:** kiểm task path/outcome và action outputs.

### Lỗi 10. Dùng mustRunAfter thay dependsOn

Ordering không tự schedule producer.

**Sửa:** `dependsOn` hoặc output-provider wiring cho real dependencies.

### Lỗi 11. Consumer đọc hard-coded build path

Không theo output directory thay đổi, thiếu implicit task dep.

**Sửa:** `inputFile.set(producer.flatMap { it.outputFile })`.

### Lỗi 12. Properties thiếu @Input/@Output

Gradle không biết file/value nào đổi, skip/cache sai.

**Sửa:** khai managed properties + annotations đầy đủ.

### Lỗi 13. Property.get() quá sớm

Giá trị extension/provider được đọc trước khi build author override.

**Sửa:** `convention(ext.value)`/`set(ext.value)`, tránh top-level get khi không cần.

### Lỗi 14. convention được dùng như hard override

`convention` chỉ cung cấp default; explicit `set` có thể thay.

**Sửa:** quyết định contract: default dùng convention, required override dùng set và validation.

### Lỗi 15. @TaskAction đọc project.version trực tiếp

Vi phạm isolation/Configuration Cache constraints.

**Sửa:** một `@Input Property<String>` được set trong configuration.

### Lỗi 16. Task output phụ thuộc current time/network nhưng @CacheableTask

False cache hit và output không reproducible.

**Sửa:** khai inputs hoặc disable caching cho side effects/nondeterminism.

### Lỗi 17. Quên copy generated resource vào Java runtime classpath

`run` fail "resource not found".

**Sửa:** `processResources.from(producer output provider)` và kiểm `build/resources/main`.

### Lỗi 18. Gọi java -cp chỉ với classes mà không thêm resources

**Sửa:** Gradle `run` hoặc classpath có cả `build/classes/java/main` và `build/resources/main`.

### Lỗi 19. Đo marker cấu hình khi bật Configuration Cache

Configuration marker vắng trên cache hit dễ dẫn tới suy luận sai.

**Sửa:** tắt Configuration Cache khi test riêng task realization, hoặc đọc configuration cache logs.

### Lỗi 20. Chỉ đo một cold invocation

JIT/daemon/dependency cache che kết quả migration.

**Sửa:** nhiều warm/cold iterations với cùng conditions.

### Lỗi 21. Dùng --rerun-tasks để đo configuration time

`--rerun-tasks` buộc task actions, dễ trộn execution cost vào benchmark.

**Sửa:** dùng `help`/profiling và compare tương đương.

### Lỗi 22. Dùng --dry-run để chứng minh output đúng

Dry-run không chạy actions.

**Sửa:** chạy task thật và assert output bytes.

### Lỗi 23. Chuyển register nhưng vẫn eagerly resolve dependencies

~~~kotlin
val jars = configurations.runtimeClasspath.get().files
~~~

đọc configuration files ở top-level có thể force resolution.

**Sửa:** truyền FileCollection/Provider vào annotated task inputs, resolve khi cần.

### Lỗi 24. build logic phụ thuộc task config order

Task B được configure trước A hoặc ngược lại làm output khác.

**Sửa:** dependencies/Provider model, không dựa vào mutable global lists.

### Lỗi 25. tasks.configureEach được dùng để mutate mọi task vô điều kiện

Dù lazy, action vẫn chạy khi nhiều tasks realized, có thể tốn chi phí và làm lệch plugin tasks.

**Sửa:** chỉ configure matching types/tasks, tránh expensive per-task work.

### Lỗi 26. Gộp mọi việc vào một task để giảm configuration

Mất incremental/caching/diagnostics.

**Sửa:** typed granular tasks + lazy registration.

### Lỗi 27. Configuration Cache PASS nên bỏ qua task migration

Cache miss vẫn phải configure, IDE/import có behavior riêng.

**Sửa:** cải thiện cả lazy task model và Configuration Cache compatibility.

### Lỗi 28. Build Cache và Configuration Cache bị nhầm

`FROM-CACHE` là output reuse; configuration cache hit là graph reuse.

**Sửa:** đọc Gradle lifecycle/report tương ứng.

### Lỗi 29. Không kiểm Gradle version compatibility

Gradle legacy release/plugins có APIs khác; plugin cũ có thể dùng deprecated conventions.

**Sửa:** pin Wrapper, đọc upgrade guide của version đích, migrate theo từng bước và chạy TestKit.

### Lỗi 30. Cross-project mutation trong root subprojects

Có thể làm model phụ thuộc evaluation order và hạn chế isolated project performance.

**Sửa:** convention plugins áp riêng từng module.

### Lỗi 31. Tưởng mọi tasks phải in log khi register

Task chưa được realized nên configuration action có thể không chạy.

**Sửa:** đặt instrumentation đúng phase, dùng Build Scan/profiling.

### Lỗi 32. Dùng Provider map nhưng lambda thực hiện network call

Provider transforms nên mô tả value derivation và không tạo side effects không kiểm soát.

**Sửa:** dùng ValueSource/TaskAction với input modeling và security policy phù hợp.

## 25. Bài tập thực hành có đáp án

### Bài 1. create và register khác gì?

**Đáp án:** `create` eager tạo/configure Task; `register` trả TaskProvider, tránh tạo task object cho đến khi cần.

### Bài 2. named có trả task instance?

**Đáp án:** Không. `tasks.named("x")` trả `TaskProvider<Task>`; `get()` mới lấy instance.

### Bài 3. Vì sao named().get() trong configuration vẫn eager?

**Đáp án:** `get()` buộc task object được created/configured.

### Bài 4. Thay withType.all bằng gì?

**Đáp án:** `tasks.withType<T>().configureEach { ... }`.

### Bài 5. Task registered có chạy doLast khi help?

**Đáp án:** Không, trừ khi task được scheduled bởi relationships/plugin behavior đặc biệt.

### Bài 6. Producer TaskProvider dùng trong dependsOn?

**Đáp án:**

~~~kotlin
val producer = tasks.register("producer")
tasks.register("consumer") {
    dependsOn(producer)
}
~~~

Không cần gọi `producer.get()`.

### Bài 7. mustRunAfter có tự chạy producer?

**Đáp án:** Không; chỉ ordering nếu hai tasks đều scheduled.

### Bài 8. Task action marker của lab khi gọi lazyProbe?

**Đáp án:**

~~~text
PROBE_CONFIGURATION=YES
PROBE_EXECUTION=YES
~~~

Hai dòng xuất hiện theo thứ tự khi task được configured rồi executed.

### Bài 9. Vì sao help không in PROBE_CONFIGURATION?

**Đáp án:** Task `lazyProbe` chỉ registered, không cần realized khi chạy `help` trong lab tối giản.

### Bài 10. Chạy uppercaseMessage có phải dependsOn thủ công?

**Đáp án:** Không. `inputFile.set(generator.flatMap { it.outputFile })` cho Gradle suy ra producer task dependency.

### Bài 11. UppercaseMessage output file nào?

**Đáp án:** `build/generated/messages/upper.txt` chứa `HELLO LAZY GRADLE` và newline.

### Bài 12. Expected stdout của gradle run --quiet?

**Đáp án:**

~~~text
JAVA_APP=hello lazy gradle
~~~

### Bài 13. Expected stdout của Java17 standalone?

**Đáp án:**

~~~text
STANDALONE=HELLO LAZY GRADLE
~~~

### Bài 14. Truy Provider property tại thời điểm nào?

**Đáp án:** Càng muộn càng tốt theo semantics; khai task inputs/outputs qua providers và đọc trong task action khi cần.

### Bài 15. convention và set khác nhau?

**Đáp án:** `convention` đặt default, `set` đặt explicit value/provider và có thể override convention.

### Bài 16. map và flatMap?

**Đáp án:** `map` transform T→U, `flatMap` transform T→Provider<U> và flatten provider chain.

### Bài 17. File path string có giữ producer identity không?

**Đáp án:** Không đảm bảo; task output Provider giữ task dependency provenance rõ hơn.

### Bài 18. afterEvaluate có phải bắt buộc để cấu hình compileJava?

**Đáp án:** Không nếu Java plugin đã đăng ký task; dùng `tasks.named<JavaCompile>("compileJava")`.

### Bài 19. Plugin Java apply muộn?

**Đáp án:** Dùng `pluginManager.withPlugin("java")` + `configureEach` phù hợp.

### Bài 20. Configuration Cache có bằng task configuration avoidance?

**Đáp án:** Không. Một bên cache graph giữa invocations, một bên tránh realize tasks không cần trong configuration.

### Bài 21. Lazy task có chắc Configuration Cache compatible?

**Đáp án:** Không nếu action vẫn dùng unsupported Project references/external mutable objects.

### Bài 22. Provider.get() trong TaskAction có lỗi?

**Đáp án:** Không nếu property là declared input và được đọc khi execution; lỗi thường là đọc quá sớm hoặc hidden inputs.

### Bài 23. Bật --dry-run có tạo output files?

**Đáp án:** Không chạy task actions; dùng để kiểm graph, không kiểm output correctness.

### Bài 24. migrate root subprojects hay convention plugin?

**Đáp án:** Bước nhanh có thể dùng configureEach; lâu dài nên áp convention plugin trong đúng subprojects để giảm cross-project coupling.

### Bài 25. Đo migration thành công bằng gì?

**Đáp án:** So tasks realized/configured khi `help`, configuration elapsed time, output correctness, requested task graph, TestKit/CI, Configuration Cache compatibility và peak memory; không chỉ đo một run.

## 26. Checklist code review cho migration

| Câu hỏi | Trạng thái đạt |
| --- | --- |
| Task creation | `tasks.register` thay eager create khi có thể |
| Lookup by name | `tasks.named`; không unwrap `get()` không cần thiết |
| Collection actions | `configureEach` thay `all`/eager withType action |
| Task identity | Provider được giữ qua call sites |
| Task relationships | dependsOn/finalizedBy/mustRunAfter dùng Provider đúng semantics |
| Side effects | Không mutate unrelated task/global state trong configuration action |
| Values | Provider/Property chains, ít eager get() |
| Inputs | `@Input`/`@InputFile`/`@InputFiles` đầy đủ |
| Outputs | `@OutputFile`/`@OutputDirectory` và output paths managed |
| File wiring | Producer.flatMap(outputProperty) → consumer.inputProperty |
| Build directory | `layout.buildDirectory`, không hard-code `build/...` trong actions |
| Plugin ordering | Không lạm dụng `afterEvaluate`; dùng withPlugin khi cần |
| Configuration Cache | Task action không capture Project/unsupported state |
| Build Cache | Cacheable tasks deterministic và declared inputs/outputs |
| Multi-project | Convention plugins thay root cross-project mutation khi scale |
| Testing | `help`/`test`/`assemble`/`run` và correctness tests |
| Performance | Warm/cold comparison, task realization count, profiling |
| Java17 | Toolchain/release target và runnable output được kiểm |
| CI parity | Wrapper, JDK, artifacts và task graph đúng |
| Upgrade safety | Đọc Gradle upgrade guide và plugin compatibility matrix |

**Kết luận:** Chuyển từ API cấu hình sớm sang **lazy configuration** không chỉ là thay `create` bằng `register`. Bạn phải giữ `TaskProvider`, tránh gọi `getByName`/`Provider.get()` quá sớm, thay `all` bằng `configureEach`, chuyển values/files sang **Provider/Property API**, và wire producer outputs tới consumer inputs. Khi đó Gradle có thể tránh tạo/configure tasks không cần, vẫn giữ task dependencies, incremental build và output correctness. Kết hợp đo `help`, functional tests, configuration cache diagnostics và CI parity để bảo đảm migration vừa **nhanh** vừa **đúng**.

## 27. Tài liệu tham khảo chính thức

- [Gradle — Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html) — `register`, `named`, `configureEach`, bảng eager→lazy, migration pitfalls.
- [Gradle — Configuring Tasks Lazily](https://docs.gradle.org/current/userguide/lazy_configuration.html) — Provider/Property APIs, map/flatMap, task output wiring, implicit dependencies.
- [Gradle — Provider API](https://docs.gradle.org/current/userguide/properties_providers.html) — managed properties/Provider evaluation, set/convention/map.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html) — custom typed tasks, inputs/outputs/annotations.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html) — task properties, execution-time Project access, lazy task inputs.
- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html) — initialization/configuration/execution.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html) — task graph reuse, isolated task state, troubleshooting.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html) — output reuse, cacheability và keys.
- [Gradle — Sharing Build Logic](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html) — convention plugins, multi-project best practices.
- [Gradle — Gradle TestKit](https://docs.gradle.org/current/userguide/test_kit.html) — functional testing plugins/build logic.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html) — Java run task và classpath.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html) — Java17 project compiler/runtime configuration.
- [Gradle Javadoc — TaskContainer](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/TaskContainer.html) — register/create/named/getByName semantics.
- [Gradle Javadoc — TaskProvider](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/TaskProvider.html) — lazy task reference.
- [Gradle Javadoc — Provider](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/Provider.html) — map/flatMap/zip/get/orElse.
- [Oracle Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) — `--release 17` và compile.
