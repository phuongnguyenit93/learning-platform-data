# Tránh truy cập Project, trạng thái toàn cục và dữ liệu không được theo dõi lúc thực thi trong Gradle

## 1. Mục tiêu bài học và bối cảnh

Gradle không chỉ chạy tuần tự các lệnh trong `build.gradle`. Nó xây dựng một **mô hình cấu hình**, chọn những tasks cần thiết, rồi kiểm tra inputs/outputs để quyết định task có cần thực thi hay có thể dùng lại kết quả. Khi bật **Configuration Cache**, Gradle còn có thể lưu lại trạng thái cấu hình để tái sử dụng ở lần chạy tiếp theo. Khi bật **Build Cache**, Gradle có thể khôi phục outputs của một task cacheable từ lần build trước, thậm chí từ một workspace khác.

Ba cơ chế này chỉ an toàn khi task **không dựa vào trạng thái ẩn**. Một task có thể chạy đúng lần đầu nhưng sai ở lần thứ hai nếu bên trong `@TaskAction` hoặc `doLast` nó:

- Truy cập `Project` để đọc `project.version`, `project.file(...)`, `project.configurations`, `project.rootDir`, hoặc gọi `project.copy`/`project.exec`.
- Đọc hoặc thay đổi `static` fields, singleton mutable maps/counters, global variables hoặc state trong Gradle Daemon.
- Gọi `System.getenv`, `System.getProperty`, `Instant.now`, `Random`, filesystem/API/network mà không biến những dữ liệu ảnh hưởng output thành **task inputs**.
- Tạo files ngoài `@OutputFile`/`@OutputDirectory`, hoặc đọc files không khai `@InputFile`/`@InputDirectory`.
- Dựa vào working directory, absolute path, locale, timezone hoặc tool version không được mô hình hóa.
- Gọi subprocess có kết quả ảnh hưởng outputs mà không công bố đầy đủ executable, arguments, input files, environment và expected outputs.
- Che triệu chứng bằng cách tắt cache hoặc ép `outputs.upToDateWhen { false }`, thay vì sửa contracts.

Bài thuộc chủ đề **Các lớp cache** trong **Build Tool Gradle**, với đề bài **“Tránh truy cập Project, trạng thái toàn cục và dữ liệu không được theo dõi lúc thực thi”**. Nội dung không chỉ giới thiệu cú pháp Gradle mà giải thích **vì sao** lỗi xảy ra, **thay thế bằng API nào**, **phân biệt các lớp cache**, **cách kiểm chứng bằng lệnh và bài test**, và **khi nào thực sự không nên cache task**.

### Kết quả cần đạt

Sau bài này, người học có thể:

1. Phân biệt giai đoạn configuration và execution; biết lúc nào dùng `Project` hợp lệ.
2. Hiểu vì sao truy cập `Project` trong task action vi phạm yêu cầu của Configuration Cache.
3. Khai dữ liệu task phụ thuộc bằng `@Input`, `@InputFile`, `@InputDirectory`, `@Classpath`, `@OutputFile`, `@OutputDirectory` và `@PathSensitive` khi phù hợp.
4. Dùng `Property<T>`, `RegularFileProperty`, `DirectoryProperty` và `ProviderFactory` để truyền giá trị từ configuration sang task execution.
5. Tránh mutable static/global state, chia sẻ tài nguyên qua **Gradle Build Services** nếu thật sự cần.
6. Phân biệt **task up-to-date checks**, **Build Cache**, **Configuration Cache** và **dependency cache**.
7. Tự làm ví dụ Java 17 + Groovy DSL có task `@CacheableTask` tạo file UTF-8 từ input file và environment provider, không chạm `Project` trong `@TaskAction`.
8. Thử input thay đổi, cache hits, missing outputs và Configuration Cache reuse mà không phỏng đoán kết quả.
9. Chẩn đoán cache không an toàn bằng `--configuration-cache`, `--build-cache`, `--info`, task validation và TestKit.
10. Biết nhận diện tác vụ có side effects, secrets hoặc thời gian thực nên **không** được cache outputs như một công việc thuần túy.

**Môi trường thực hành:** Gradle Wrapper hợp lệ, bản Gradle tương thích Java 17, JDK 17, Maven Central khi cần tải JUnit. Lệnh Unix dùng `./gradlew`; Windows PowerShell dùng `.\gradlew.bat`. Các ví dụ dùng Gradle Groovy DSL; Kotlin DSL sẽ có bản đối chiếu ngắn ở phần sau.

## 2. Bốn lớp cache/khả năng tránh làm lại việc: không được trộn lẫn

| Cơ chế | Tái sử dụng cái gì? | Điều kiện chủ chốt | Kết quả có thể thấy |
| --- | --- | --- | --- |
| **Configuration Cache** | Kết quả configuration: task graph/configured task state | Build scripts, plugin code, configuration inputs và compatibility hợp lệ | Thông báo tái sử dụng configuration cache |
| **Task up-to-date checks** | Output đã có trong **cùng workspace** | Inputs/outputs và local execution history phù hợp | `UP-TO-DATE` |
| **Build Cache** | Task outputs đã được lưu theo cache key | Task cacheable, inputs đủ và cùng nội dung/implementation | `FROM-CACHE` |
| **Dependency cache** | External modules/JARs/metadata đã tải | Repository resolution/caching policies | Tránh tải dependency lặp lại; không phải task output reuse |

Bốn cơ chế có quan hệ nhưng khác mục tiêu:

~~~text
Gradle invocation
       |
       v
Configuration Cache?
       |    cache hit -> khôi phục configured task graph
       |    cache miss -> chạy configuration và lưu graph nếu hợp lệ
       v
Task graph
       |
       +--> Task A: UP-TO-DATE? ------> không chạy action
       |
       +--> Task B: Build Cache hit? -> FROM-CACHE, khôi phục outputs
       |
       +--> Task C: cần chạy -------> @TaskAction / doLast
       |
       v
Artifact dependencies dùng dependency cache khi resolution cần thiết
~~~

**Không đồng nhất các signal:**

- `UP-TO-DATE` là kết quả local history và outputs hiện tại, không phải đồng nghĩa `FROM-CACHE`.
- `FROM-CACHE` cho biết output được lấy từ Build Cache, không chứng minh Configuration Cache hit.
- Configuration Cache hit **không bảo đảm** tasks đều up-to-date: thay một task input có thể khiến task chạy lại dù configuration state được tái sử dụng.
- Task không có outputs vẫn có thể được cấu hình cache-friendly nhưng **không có artifact hữu ích để Build Cache tái sử dụng**.
- Dependency cache có thể giúp không tải lại JUnit nhưng hoàn toàn không bảo đảm `test` hoặc task tùy chỉnh đã pass.

**Điểm an toàn cần nhớ:** Configuration Cache quan tâm đến **khả năng lưu và tái tạo mô hình cấu hình**; Build Cache/up-to-date quan tâm đến **tính đầy đủ và ổn định của quan hệ input → output**. Một task có thể tương thích Configuration Cache nhưng **sai Build Cache** nếu có input ẩn.

## 3. Hai giai đoạn và ranh giới của Project API

Gradle có hai giai đoạn thường được nhắc tới:

1. **Configuration phase:** đánh giá `settings.gradle`/`build.gradle`, apply plugins, đăng ký/configure tasks, nối providers và task dependencies.
2. **Execution phase:** chạy các actions của tasks đã được chọn, có thể chạy song song và có thể không chạy nếu up-to-date/cache hit.

Task class được tạo và cấu hình trong build script. Trong configuration, **truy cập `Project` là hợp lệ và thường cần thiết** để xác định:

- `project.version`, `project.group` hoặc project directory.
- `project.layout`, `project.providers` và các extension.
- `tasks.register` hoặc `tasks.named`.
- Java toolchain, configurations và dependency declarations.
- Input providers được nối vào task properties.

**Giới hạn quan trọng:** không truy cập đối tượng `Project` từ **`@TaskAction`**, `doFirst`, `doLast` hay task property bị serialize vào Configuration Cache. Task nên nhận **những giá trị đã được mô hình hóa** và dịch vụ được Gradle inject, thay vì đi tìm lại Project khi chạy.

### 3.1. Anti-pattern: đọc Project.version từ task action

~~~groovy
tasks.register('badVersionReport') {
    doLast {
        // KHÔNG NÊN: Project được truy cập trong execution.
        def currentVersion = project.version
        def destination = project.file("$buildDir/version.txt")
        destination.parentFile.mkdirs()
        destination.text = currentVersion.toString()
    }
}
~~~

Vì sao sai?

1. `project.version` là truy cập Project mutable model khi task chạy, không phù hợp yêu cầu Configuration Cache.
2. `project.file` và `buildDir` gắn task action với Project/build script state.
3. Version **không được khai là task input**, nên up-to-date/Build Cache có thể coi hai lần build khác version là giống nhau.
4. File đầu ra **không được khai là `@OutputFile`**, nên Gradle không biết cần kiểm tra/restore output nào.
5. Task dùng closure capture Gradle model trong `doLast`, dễ gây lỗi serialization khi bật Configuration Cache.

Ngay cả khi hôm nay task tạo đúng file, đó chưa phải bằng chứng task đáng tin khi cache, chạy song song hoặc chạy trong CI.

### 3.2. Cách đúng: chuyển giá trị thành declared input

Bản dùng typed task:

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

abstract class WriteVersionTask extends DefaultTask {
    @Input
    abstract Property<String> getReleaseVersion()

    @OutputFile
    abstract RegularFileProperty getDestination()

    @TaskAction
    void writeVersion() {
        def path = destination.get().asFile.toPath()
        java.nio.file.Files.createDirectories(path.parent)
        java.nio.file.Files.writeString(
            path,
            releaseVersion.get() + '\n',
            java.nio.charset.StandardCharsets.UTF_8
        )
    }
}

tasks.register('writeVersion', WriteVersionTask) {
    // Truy cập project.version trong CONFIGURATION để wire @Input.
    releaseVersion.set(project.version.toString())
    destination.set(layout.buildDirectory.file('version.txt'))
}
~~~

Đây là **trích đoạn task type** khi đặt trong `build.gradle` Groovy, không phải phần của demo chính ở mục 8. Sự chuyển đổi cốt lõi:

- `Project` được đọc trong **configuration** để nối `releaseVersion`.
- Task action chỉ đọc `releaseVersion.get()` và `destination.get()` của **chính task**.
- `@Input` làm version tham gia input snapshot.
- `@OutputFile` công bố artifact được tạo.
- `Files.writeString` làm I/O theo đường dẫn đầu ra đã được cấu hình.

**Nuance:** đọc trực tiếp một số Gradle project properties hoặc file/environment ở configuration time có thể trở thành **configuration inputs** được Gradle theo dõi. Tuy nhiên task output vẫn cần **task inputs riêng** để up-to-date/Build Cache biết giá trị nào quyết định output. Đừng dựa vào Configuration Cache auto-tracking để thay khai input của task.

### 3.3. Project.getLogger khác Task.getLogger

Không cần `project.logger` trong task action. `DefaultTask` đã có `logger`:

~~~groovy
@TaskAction
void run() {
    logger.lifecycle('Task action is running')
}
~~~

Đây là đoạn method minh họa bên trong một task type. Tương tự, thay vì `project.file('...')`, hãy truyền `RegularFileProperty`/`DirectoryProperty` từ configuration. Thay vì `project.exec`, hãy inject `ExecOperations` khi thực sự cần chạy subprocess.

## 4. Các biểu hiện của lỗi Project-at-execution

| Code trong task action | Vấn đề | Thiết kế thay thế |
| --- | --- | --- |
| `project.version` | Đọc mutable Gradle Project model | `@Input Property<String>` nối tại configuration |
| `project.file('config.txt')` | Lấy path qua Project khi execution | `@InputFile RegularFileProperty` |
| `project.buildDir` | Dựa vào Project/buildDir mutable state | `@OutputFile` hoặc `@OutputDirectory` từ `layout.buildDirectory` |
| `project.configurations.runtimeClasspath` | Truy cập dependency model sai giai đoạn | `@Classpath ConfigurableFileCollection` được wire trước |
| `project.copy { }` | File operation thông qua Project | `FileSystemOperations.copy` được service inject |
| `project.exec { }` | External process qua Project | `ExecOperations.exec` hoặc task `Exec` |
| `project.rootProject` | Đụng mutable model của project khác | Inputs/file locations do consumer wire, không cross-project lookup |
| `tasks.getByName(...)` trong action | Lôi task model khi execution | Declare task output/provider dependency trong configuration |
| `afterEvaluate` để cất Project vào static map | Vừa mutable state vừa lifecycle fragile | Typed provider/task input, convention plugin |
| Closure `doLast` capture `Project`/`Task` khác | Khó serialization, Configuration Cache violation | Custom typed task, chỉ capture immutable/serializable values nếu cần |

Không phải tất cả truy cập `Task` đều bị cấm trong task action: sử dụng **chính task** qua `logger`, getters của task inputs/outputs và những injected services được hỗ trợ là bình thường. Ranh giới là **Project model và live mutable state không thể tái dựng đúng từ cached task graph**, cùng các APIs Gradle không cho phép khi execution.

### 4.1. Vì sao một bản sửa “capture Project vào biến cục bộ” chưa chắc đúng?

Ví dụ:

~~~groovy
def p = project
tasks.register('stillWrong') {
    doLast {
        logger.quiet(p.version.toString())
    }
}
~~~

Đổi tên `project` thành `p` chỉ đổi cách capture. Closure vẫn giữ một tham chiếu đến **Project object**, khiến task action không phù hợp Configuration Cache. Cần capture một **giá trị tách rời**, và nếu output phụ thuộc giá trị đó, khai nó thành input.

Một cách khắc phục có thể là đọc `project.version.toString()` lúc configuration và truyền string vào task property. Nhưng đừng chỉ capture string vào `doLast` mà quên khai `@Input`: task sẽ không có hợp đồng đầy đủ về dữ liệu nó sử dụng.

## 5. Trạng thái toàn cục: vì sao static/singleton không phải nguồn sự thật của task?

Gradle Daemon có thể tồn tại qua nhiều invocations. Tasks có thể thực thi song song; Configuration Cache có thể khôi phục task graph trong một vòng đời JVM khác; Build Cache có thể chuyển outputs giữa CI agents. Do đó **static mutable state** hoặc một singleton giữ thông tin từ tasks trước không phải dữ liệu đáng tin để quyết định outputs.

Anti-pattern:

~~~groovy
class GlobalBuildCounter {
    static int count = 0
}

tasks.register('badCounter') {
    doLast {
        GlobalBuildCounter.count++
        logger.lifecycle('count=' + GlobalBuildCounter.count)
    }
}
~~~

Lệnh chạy lần một có thể in `1`, lần sau trong cùng Daemon có thể in giá trị khác; nhưng nếu Gradle khởi tạo classloader mới, dùng daemon khác hoặc Configuration Cache reuse theo cơ chế khác, giá trị cũng có thể quay về `1`. **Không có hợp đồng bảo đảm** static counter được duy trì giữa builds.

Nếu một task cacheable dùng counter đó để tạo file nhưng không khai input đại diện cho counter, cùng cache key có thể sinh outputs khác nhau. Đây là **vi phạm tính deterministic**; không thể sửa bằng cách đánh dấu `@CacheableTask`.

### 5.1. Những nguồn global state khác cũng nguy hiểm

- Mutable singleton maps, arrays hoặc caches chia sẻ giữa tasks.
- `System.setProperty` để giao tiếp giữa tasks.
- Thay `user.dir`, global locale hoặc timezone của process.
- Biến static giữ một kết nối HTTP/database/socket.
- Java `ThreadLocal` giả định task luôn chạy trên một thread cố định.
- `Random` không seed cố định, `UUID.randomUUID()` và thời gian hiện tại khi output phải reproducible.
- Thông tin host name, PID, temporary directory, absolute workspace path có thể khác máy.
- Reading mutable service state mà task output phụ thuộc nhưng không khai tracked inputs.

Không đồng nghĩa mọi static **constant** đều sai: một `static final String SUFFIX = '!'` bất biến có thể an toàn. Vấn đề là **trạng thái thay đổi ảnh hưởng kết quả và không nằm trong input contract**, nhất là khi nhiều tasks và nhiều Gradle invocations.

### 5.2. Khi cần chia sẻ tài nguyên: dùng Gradle Build Services

Nếu nhiều tasks phải dùng chung **một tài nguyên tại execution** (rate limiter, HTTP client có giới hạn kết nối, expensive scanner, coordination lock), Gradle có **shared build services**:

1. Viết class implements `BuildService<Parameters>`.
2. Đăng ký qua `gradle.sharedServices.registerIfAbsent(...)` trong configuration.
3. Nối service provider đến task qua property được hỗ trợ, thường `@ServiceReference` hoặc `@Internal`.
4. Có thể cấu hình `maxParallelUsages` để giới hạn số tasks đồng thời.
5. Để Gradle quản lý lifecycle và tạo lại service khi cần, kể cả trên Configuration Cache hit.

Build Service **không phải** cách thay task inputs. Nếu service đọc dữ liệu ảnh hưởng output (ví dụ version của database schema), task vẫn cần một **giá trị đầu vào được theo dõi**. Một service được dùng để chia sẻ kết nối hoặc đồng bộ có thể không cần là task input; dữ liệu nó trả về mà làm đổi artifact thì cần được mô hình hóa theo quy tắc cache.

### 5.3. Ví dụ Build Service có giới hạn đồng thời

Mẫu kiến trúc minh họa, không thuộc demo chạy đầy đủ:

~~~groovy
import org.gradle.api.services.BuildService
import org.gradle.api.services.BuildServiceParameters
import org.gradle.api.services.ServiceReference
import org.gradle.api.provider.Property

abstract class ApiPermitService
        implements BuildService<BuildServiceParameters.None>, AutoCloseable {
    @Override
    void close() {
        // Đóng tài nguyên ngoài nếu đã mở, không phụ thuộc task ordering.
    }
}

def permit = gradle.sharedServices.registerIfAbsent(
    'apiPermit', ApiPermitService
) {
    maxParallelUsages = 1
}
~~~

Task consumer cần property dùng annotation `@ServiceReference` hoặc `@Internal` theo API; việc gắn provider và tạo HTTP client phụ thuộc triển khai. **Không** lấy một static `ApiPermitService.INSTANCE` làm “cache” dùng chung. Nếu service được dùng cho network side effects, task gọi API thường **không phù hợp Build Cache** trừ khi được chứng minh là thuần túy và inputs/outputs đầy đủ.

## 6. Dữ liệu không được theo dõi: lỗi correctness, không chỉ lỗi performance

Một task cacheable có thể được mô hình hóa như:

~~~text
Output = f(
    task implementation,
    declared scalar inputs,
    declared input files,
    normalized classpaths,
    tool/runtime versions,
    declared environment influences
)
~~~

Nếu task thật sự đọc thêm dữ liệu `hiddenInput`:

~~~text
Output = f(declaredInputs, hiddenInput)
~~~

nhưng cache key chỉ tính `declaredInputs`, **hai lần chạy có cùng cache key nhưng output khác nhau**. Khi Gradle lấy lại kết quả cũ từ Build Cache hoặc đánh dấu UP-TO-DATE, artifact có thể sai và không có exception nào xuất hiện.

### 6.1. Anti-pattern: đọc environment variable trực tiếp trong action

~~~groovy
tasks.register('badEnvReport') {
    outputs.file(layout.buildDirectory.file('env.txt'))

    doLast {
        // Không được khai như một task input.
        def value = System.getenv('REPORT_LABEL') ?: 'local'
        def result = layout.buildDirectory.file('env.txt').get().asFile
        result.parentFile.mkdirs()
        result.text = value
    }
}
~~~

Đây là **anti-pattern** vì có thể capture Project `layout` vào action và đọc `REPORT_LABEL` không được công bố là input. Khi thay env nhưng source files không đổi, cơ chế up-to-date có thể quyết định task không cần chạy.

**Cách đúng:** nối giá trị qua `providers.environmentVariable('REPORT_LABEL').orElse('local')` trong **configuration**, đặt vào `@Input Property<String>` của task. Task action chỉ gọi `label.get()`. Khi label đổi, input snapshot đổi, task chạy lại hoặc cache key khác.

### 6.2. Đọc environment tại configuration không luôn bị cấm

Điểm dễ nhầm: Gradle Configuration Cache có thể theo dõi **đọc environment variables và system properties tại configuration time**, kể cả qua một số Java/Groovy APIs, nhờ instrumentation. Khi giá trị đổi, configuration cache có thể bị invalidated.

Nhưng cách này **thường kém tối ưu** khi environment chỉ ảnh hưởng output của một task:

~~~groovy
// Eager, có thể biến env thành configuration input:
def label = System.getenv('REPORT_LABEL') ?: 'local'
~~~

Tốt hơn:

~~~groovy
// Lazy provider được nối vào @Input của task:
def labelProvider = providers.environmentVariable('REPORT_LABEL')
    .orElse('local')
~~~

Khi provider được wire và **chỉ đọc tại execution**, thay env có thể chỉ làm task input đổi mà **không cần invalidated toàn bộ Configuration Cache**. Việc Gradle quản lý configuration-time reads không thay thế input declaration của task.

### 6.3. Anti-pattern: đọc file ngoài input files

~~~groovy
@TaskAction
void generate() {
    def config = new File('/tmp/custom-tool/config.txt').text
    // Kết quả file output phụ thuộc config nhưng config không được khai input.
}
~~~

Ví dụ minh họa đoạn method, không chạy độc lập. Nếu file bên ngoài đổi, Gradle không biết output cần tái tạo. Giải pháp: khai `@InputFile` với `RegularFileProperty` hoặc `@InputDirectory`/`ConfigurableFileCollection` cho mọi files có ảnh hưởng. Với file optional, dùng `@Optional` theo đúng semantics và phải thiết kế rõ khi file không tồn tại.

### 6.4. Anti-pattern: timestamp/randomness trong artifact reproducible

~~~groovy
@TaskAction
void generate() {
    def id = java.util.UUID.randomUUID()
    // Dùng id để ghi output nhưng không khai input.
}
~~~

Task output khác mỗi lần dù declared inputs giống nhau. Nếu thực sự cần artifact reproducible, đưa seed/identifier thành `@Input` và dùng thuật toán xác định. Nếu output cố ý là timestamp/session ID không cache được, **không đánh dấu `@CacheableTask`** và không giả định up-to-date.

### 6.5. Subprocess và network

Dùng service `ExecOperations` để chạy lệnh bên ngoài là cách thân thiện hơn với Gradle APIs so với `project.exec` trong task action. Nhưng **ExecOperations không tự làm dữ liệu bên ngoài được theo dõi**:

- Executable path/version cần được xác định rõ.
- Arguments/environment variables ảnh hưởng output cần được khai `@Input`.
- Input files/directories cần `@InputFiles`/`@InputDirectory`.
- Output artifacts cần `@OutputFile`/`@OutputDirectory`.
- Đọc network state không ổn định khó cache an toàn; nên cân nhắc task non-cacheable hoặc snapshot external data thành artifact input có phiên bản.

Một task gọi service trả dữ liệu mới mỗi invocation nhưng coi kết quả là cacheable theo cùng key sẽ sai, dù code không đụng `Project`.

## 7. Task contract: input/output properties và annotations

Gradle custom task nên có một **khai báo tường minh** về những gì nó dùng và tạo. Các annotations thông dụng:

| Annotation | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `@Input` | Scalar/serializable value mà output phụ thuộc | `Property<String>` version, mode, flags |
| `@InputFile` | Một file nguồn | YAML/JSON config, template |
| `@InputFiles` | Tập các files | Source files, templates, dependency files |
| `@InputDirectory` | Thư mục đầu vào | Assets tree |
| `@Classpath` | File collection được normalized theo semantics classpath | Tool/library classpath |
| `@CompileClasspath` | Classpath input được normalized theo ABI Java compile khi phù hợp | Java compiler-related classpath |
| `@OutputFile` | Một file sinh ra | `build/generated/result.txt` |
| `@OutputDirectory` | Một thư mục output | `build/generated/pages` |
| `@Optional` | Input property được phép không có giá trị | Optional config file |
| `@PathSensitive` | Cách path ảnh hưởng input identity | `RELATIVE`, `NAME_ONLY`, `NONE`, `ABSOLUTE` |
| `@IgnoreEmptyDirectories` | Bỏ qua empty dirs khi xác định input file set | File trees |
| `@SkipWhenEmpty` | Bỏ task nếu collection input không có source files phù hợp | Source-processing tasks |
| `@Internal` | Property không phải task input/output | Injected service/implementation detail |
| `@LocalState` | File/directory state cục bộ không phải portable output | Local working cache |
| `@Destroys` | Vị trí bị xóa bởi task | Clean-like task |

**Cảnh báo về `@Internal`:** nếu một giá trị **thực sự quyết định output**, gắn `@Internal` là khai sai hợp đồng. `@Internal` không phải cách che input để Gradle “bớt theo dõi” nhưng vẫn cache đúng.

### 7.1. File path normalization ảnh hưởng remote Build Cache

Một input file ở:

~~~text
/home/alice/work/demo/src/message/name.txt
~~~

và một file tương đương ở:

~~~text
C:\ci\agent\demo\src\message\name.txt
~~~

có cùng nội dung nhưng absolute path khác nhau. Nếu task cache key phụ thuộc absolute path, hai build có thể không dùng chung cache, dù semantics giống hệt.

Với input file nằm trong project và chỉ nội dung/relative location có ý nghĩa, thường dùng:

~~~groovy
@InputFile
@PathSensitive(PathSensitivity.RELATIVE)
abstract RegularFileProperty getNameFile()
~~~

Khi path tương đối trong input snapshot được giữ ổn định, Build Cache có cơ hội reuse qua workspace khác. Nhưng **RELATIVE không phải luôn đúng**: nếu bản thân absolute location là kết quả cần tạo, phải đánh giá lại tính relocatable; không cố “ẩn” thông tin path thực sự ảnh hưởng output.

### 7.2. Vì sao @Classpath có semantics riêng?

Classpath jar files thường có metadata ZIP, tên file và thứ tự ảnh hưởng Java linkage theo những cách khác một input file tùy ý. `@Classpath` dùng normalization tương ứng, giúp loại bớt một số thay đổi không ảnh hưởng semantics. `@CompileClasspath` được thiết kế cho ABI-sensitive classpath inputs khi phù hợp.

Không gắn `@Classpath` vào mọi folder tùy ý: nếu task đọc một JSON template, dùng `@InputFile`/`@PathSensitive` rõ ràng. Nếu task dùng tool JARs, Java classpath thực sự, `@Classpath` mới phù hợp.

### 7.3. Đừng khai output chồng lấn

Nếu hai tasks cùng ghi:

~~~text
build/generated/result.txt
~~~

Gradle khó xác định task nào sở hữu output và trạng thái up-to-date/caching có thể không đúng hoặc bị vô hiệu hóa. Nên cấp output riêng từng task:

~~~text
build/generated/taskA/result.txt
build/generated/taskB/result.txt
~~~

Nếu task B cần output task A, wire **Provider của output task A** làm input của B thay vì dùng path hard-coded và tự phỏng đoán thứ tự chạy.

### 7.4. Default không đồng nghĩa tracking

Task `DefaultTask` có thể chạy action mà không khai inputs/outputs. Nó không tự trở thành cacheable. `@CacheableTask` là **opt-in** cho custom task type, chỉ nên dùng khi output hoàn toàn xác định bởi các inputs được khai và task implementation.

Đặt `@CacheableTask` khi input thiếu thường nguy hiểm hơn không đặt: Gradle có thể khôi phục **output sai một cách “thành công”**. Một số built-in tasks không cacheable mặc định do side effects/cost profile. `@DisableCachingByDefault` hoặc một task non-cacheable rõ lý do có thể là lựa chọn đúng.

## 8. Demo thực hành: Java 17 + Groovy DSL + cacheable custom task

Ta xây **một Gradle project chạy được** trong đó custom task tạo file lời chào từ:

- Input file `src/message/name.txt`.
- Environment variable `GREETING_SUFFIX` (nếu vắng, dùng `!`).
- Output file `build/generated/greeting.txt`.

Task action **không truy cập Project**, không dùng static state và không đọc env trực tiếp. Các nguồn quyết định output được khai qua `@InputFile`/`@Input`, output khai `@OutputFile`. Một class Java 17 riêng đọc file kết quả và in stdout. JUnit test kiểm hàm đọc file, còn Gradle commands kiểm cache behavior.

### 8.1. Cấu trúc project

~~~text
cache-safe-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── src/
│   ├── message/
│   │   └── name.txt
│   ├── main/
│   │   └── java/demo/ReadGreeting.java
│   └── test/
│       └── java/demo/ReadGreetingTest.java
└── build/             (được Gradle tạo; không commit)
~~~

**Gradle Wrapper** phải được tạo hợp lệ bằng Gradle; `gradlew`, `gradlew.bat`, `gradle-wrapper.jar` và `gradle-wrapper.properties` không được thay bằng file rỗng. Chọn Gradle distribution tương thích Java 17 và JDK 17 toolchain hiện có.

### 8.2. `settings.gradle`

~~~groovy
rootProject.name = 'cache-safe-lab'
~~~

### 8.3. `build.gradle` hoàn chỉnh

~~~groovy
import java.nio.charset.StandardCharsets
import java.nio.file.Files

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

plugins {
    id 'java'
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

@CacheableTask
abstract class GenerateGreeting extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract RegularFileProperty getNameFile()

    @Input
    abstract Property<String> getSuffix()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        def source = nameFile.get().asFile.toPath()
        def destination = outputFile.get().asFile.toPath()

        String name = Files.readString(
            source,
            StandardCharsets.UTF_8
        ).strip()

        if (name.isEmpty()) {
            name = 'bạn'
        }

        String result = 'Xin chào, ' + name + suffix.get() + '\n'

        Files.createDirectories(destination.parent)
        Files.writeString(
            destination,
            result,
            StandardCharsets.UTF_8
        )
    }
}

tasks.register('generateGreeting', GenerateGreeting) {
    nameFile.set(
        layout.projectDirectory.file('src/message/name.txt')
    )

    suffix.set(
        providers.environmentVariable('GREETING_SUFFIX')
            .orElse('!')
    )

    outputFile.set(
        layout.buildDirectory.file('generated/greeting.txt')
    )
}
~~~

**Điểm chủ chốt ở file này:**

1. `plugins { id 'java' }` cung cấp Java compile/test lifecycle cho Java 17 reader/test. Custom task không buộc phải là Java compile task.
2. `@CacheableTask` đánh dấu task type đủ điều kiện lưu/khôi phục outputs qua Build Cache nếu mọi hợp đồng đúng.
3. `@InputFile` chỉ ra source file; `@PathSensitive(RELATIVE)` tránh đưa absolute workspace root vào input identity khi path tương đối mới là điều quan trọng.
4. `@Input Property<String> suffix` chỉ ra biến môi trường có ảnh hưởng thực sự đến output.
5. `@OutputFile RegularFileProperty outputFile` công bố file được tạo.
6. `@TaskAction` dùng `nameFile.get()`, `suffix.get()`, `outputFile.get()` — **chỉ task properties**, không gọi `project.file` hoặc `project.layout`.
7. `Files.readString`/`Files.writeString` dùng explicit UTF-8; output dùng ký tự `\n` cố định để ổn định giữa các OS.
8. `layout.projectDirectory`/`layout.buildDirectory`/`providers.environmentVariable` được dùng trong **configuration action** của `tasks.register` để wire input/output providers, không bị truy cập trong task action.
9. `orElse('!')` tạo kết quả xác định khi `GREETING_SUFFIX` vắng mặt.
10. Không có network, timestamp, random hay global mutable state ảnh hưởng output.

**Giới hạn:** Demo xử lý một input file duy nhất. Trong công việc thực tế, nếu task còn đọc template files, plugin configuration file hoặc tool executable, **mỗi nguồn đó phải được khai thêm**. Đừng suy một task luôn cache-correct chỉ vì class có ba annotations.

### 8.4. `src/message/name.txt`

~~~text
Linh
~~~

File có thể kết thúc bằng newline thông thường. `String.strip()` loại whitespace đầu/cuối, nên input `Linh` hoặc `Linh\n` đều dẫn tới tên `Linh`.

### 8.5. `src/main/java/demo/ReadGreeting.java`

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ReadGreeting {
    private ReadGreeting() {
    }

    public static String read(Path file) throws IOException {
        return Files.readString(file, StandardCharsets.UTF_8)
            .stripTrailing();
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Provide the generated greeting file path"
            );
        }

        System.out.println(read(Path.of(args[0])));
    }
}
~~~

`ReadGreeting` dùng Java 17 standard library, đọc file output và bỏ newline phía sau trước khi in. Nó **không phải custom Gradle task**, nên không có `Project` hoặc Gradle APIs trong Java source. Đường dẫn file được truyền qua CLI argument, giúp chứng minh output của task đã thực sự tồn tại.

### 8.6. `src/test/java/demo/ReadGreetingTest.java`

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ReadGreetingTest {
    @TempDir
    Path temporaryDirectory;

    @Test
    void readsUtf8Greeting() throws IOException {
        Path input = temporaryDirectory.resolve("greeting.txt");
        Files.writeString(
            input,
            "Xin chào, Linh!\n",
            StandardCharsets.UTF_8
        );

        assertEquals(
            "Xin chào, Linh!",
            ReadGreeting.read(input)
        );
    }
}
~~~

Đây là JUnit Jupiter test kiểm hàm Java đọc UTF-8, **không phải** một Gradle TestKit test. Việc `test` pass không đủ chứng minh `GenerateGreeting` khai đúng mọi inputs hoặc Configuration Cache reuse; các phần sau bổ sung những phép kiểm đó.

### 8.7. Chạy project lần đầu

Nếu biến môi trường `GREETING_SUFFIX` chưa được đặt:

~~~bash
./gradlew clean classes test generateGreeting \
    --configuration-cache --build-cache --info
~~~

PowerShell:

~~~powershell
.\gradlew.bat clean classes test generateGreeting --configuration-cache --build-cache --info
~~~

Lệnh đầu có nhiều tasks (clean, compileJava, test, generateGreeting). `generateGreeting` đọc file `src/message/name.txt` và tạo:

~~~text
build/generated/greeting.txt
~~~

Nội dung file **chính xác**:

~~~text
Xin chào, Linh!
~~~

Do trong code task thêm `\n`, file kết thúc bằng một ký tự line feed. Từ terminal Linux/macOS có thể đọc file bằng `cat build/generated/greeting.txt`; trên PowerShell dùng `Get-Content build/generated/greeting.txt`.

### 8.8. Chạy Java 17 reader để xác minh artifact

~~~bash
java -cp build/classes/java/main demo.ReadGreeting \
    build/generated/greeting.txt
~~~

Stdout Java main:

~~~text
Xin chào, Linh!
~~~

Lệnh `java` chỉ chạy reader class đã được `./gradlew classes` compile, **không tự gọi `generateGreeting`**. Nếu output chưa có, lệnh Java sẽ ném IOException; trước đó phải chạy task tạo file.

### 8.9. Kiểm Java bằng `javac`/`java` độc lập

Nếu không muốn dùng Gradle JavaCompile để kiểm chính Java source:

~~~bash
mkdir -p manual-classes

javac -encoding UTF-8 -d manual-classes \
    src/main/java/demo/ReadGreeting.java

java -cp manual-classes demo.ReadGreeting \
    build/generated/greeting.txt
~~~

Stdout vẫn là:

~~~text
Xin chào, Linh!
~~~

**Lưu ý:** `javac`/`java` không thực thi custom task. Đây chỉ là kiểm Java 17 reader. Output `build/generated/greeting.txt` vẫn cần được tạo bởi Gradle task trước. Trên Windows PowerShell, thay line continuation cho phù hợp và dùng đường dẫn Windows nếu muốn; riêng command Java này chỉ dùng một classpath entry nên không phải sửa dấu phân cách nhiều entries.

### 8.10. Bật/tắt suffix và kiểm input được theo dõi

Trên Linux/macOS:

~~~bash
GREETING_SUFFIX='!!!' ./gradlew generateGreeting \
    --configuration-cache --build-cache --info
~~~

Task output khi `GREETING_SUFFIX=!!!`:

~~~text
Xin chào, Linh!!!
~~~

Ở Windows PowerShell:

~~~powershell
$env:GREETING_SUFFIX = "!!!"
.\gradlew.bat generateGreeting --configuration-cache --build-cache --info
Get-Content build/generated/greeting.txt
Remove-Item Env:GREETING_SUFFIX
~~~

Khi suffix đổi từ `!` sang `!!!`, `@Input suffix` đổi, do đó task không được coi là có cùng input snapshot. Gradle sẽ chạy lại hoặc khôi phục đúng cached output cho **key của suffix mới** nếu đã có. Không buộc Configuration Cache phải invalidated chỉ vì value của execution-time provider thay đổi.

Sau khi gỡ env var, chạy:

~~~bash
./gradlew generateGreeting --configuration-cache --build-cache --info
~~~

Output quay về `Xin chào, Linh!` nếu Gradle chạy hoặc restore đúng key. **Không được hứa task action chắc chắn chạy lại**: khi Build Cache đã lưu đúng output cho suffix `!`, Gradle có thể khôi phục nhanh mà vẫn đúng.

### 8.11. Thay input file để chứng minh task không bỏ sót dữ liệu

Sửa `src/message/name.txt` thành:

~~~text
Mai
~~~

Rồi chạy:

~~~bash
./gradlew generateGreeting --configuration-cache --build-cache --info
~~~

Với suffix vắng mặt, nội dung mong đợi:

~~~text
Xin chào, Mai!
~~~

Vì `@InputFile` snapshot nội dung file đã thay, task không được dùng lại output `Linh` khi chưa có cache key tương ứng `Mai`. Trường hợp đã từng có cache entry cho `Mai` thì `FROM-CACHE` vẫn có thể xuất hiện, nhưng file đúng phải là `Mai`.

### 8.12. Phân biệt `UP-TO-DATE` và `FROM-CACHE` trên chính demo

Lần đầu một input configuration chưa có output/history:

~~~bash
./gradlew generateGreeting --build-cache --info
~~~

Task thường chạy action, tạo file và có thể store cache entry.

Chạy **lại đúng cùng inputs** trong cùng workspace:

~~~bash
./gradlew generateGreeting --build-cache --info
~~~

Kết quả thường là `UP-TO-DATE` vì outputs đã tồn tại và inputs không đổi.

Nếu xóa **chỉ generated output** hoặc chạy `clean`, rồi chạy lại cùng input:

~~~bash
./gradlew clean generateGreeting --build-cache --info
~~~

Gradle có thể lấy outputs qua Build Cache và báo `FROM-CACHE`, miễn task thật sự cacheable, cache enabled, cache entry tồn tại và không có yếu tố làm cache key thay đổi. Nếu miss, task action có thể chạy. Không suy `clean` làm Configuration Cache bắt buộc hit hoặc miss; việc thay command-line target còn có thể dẫn đến cache entry configuration khác.

**Thông điệp:** `UP-TO-DATE`/`FROM-CACHE` đều là các cách **không chạy action**, nhưng dựa trên hai cơ chế khác nhau. Test correctness bằng **nội dung output**, không chỉ bằng status.

## 9. Một ví dụ sai và đúng về môi trường, file và output

### 9.1. Cách sai: đủ để chạy lần đầu, nhưng input ẩn

~~~groovy
tasks.register('badGreeting') {
    outputs.file(layout.buildDirectory.file('bad/greeting.txt'))

    doLast {
        // Sai: Đọc environment trực tiếp lúc execution.
        String suffix = System.getenv('GREETING_SUFFIX') ?: '!'

        // Sai: Đọc file nguồn nhưng không khai inputs.file.
        String name = new File('src/message/name.txt').text.strip()

        // Sai: dùng project/buildDir trong execution.
        def output = project.file("$buildDir/bad/greeting.txt")
        output.parentFile.mkdirs()
        output.text = 'Xin chào, ' + name + suffix
    }
}
~~~

Ngay cả khi `outputs.file` có khai output, Gradle **không biết** việc đổi `name.txt` hoặc `GREETING_SUFFIX` có ảnh hưởng tới output, vì chưa khai chúng là inputs. `Project` trong `doLast` còn không tương thích Configuration Cache.

### 9.2. Cách đúng: task action thuần theo inputs/outputs

Ở `GenerateGreeting`:

~~~groovy
@InputFile
@PathSensitive(PathSensitivity.RELATIVE)
abstract RegularFileProperty getNameFile()

@Input
abstract Property<String> getSuffix()

@OutputFile
abstract RegularFileProperty getOutputFile()
~~~

và:

~~~groovy
tasks.register('generateGreeting', GenerateGreeting) {
    nameFile.set(layout.projectDirectory.file('src/message/name.txt'))
    suffix.set(providers.environmentVariable('GREETING_SUFFIX').orElse('!'))
    outputFile.set(layout.buildDirectory.file('generated/greeting.txt'))
}
~~~

Task action chỉ đọc typed properties. Toàn bộ những dữ liệu làm đổi output ở demo đã được khai. Nếu sau này thêm một template hoặc CLI flag, phải bổ sung input property cho nó.

### 9.3. Khi đọc file configuration tại configuration time có thật sự sai?

Gradle hiện đại dùng instrumentation để theo dõi nhiều **configuration-time file reads**. Ví dụ:

~~~groovy
def flags = file('tool.conf').text
~~~

nếu nằm trong configuration, có thể được ghi nhận là một **configuration input**, khiến Configuration Cache invalidated khi file đổi. Điều này khác với đọc file ngầm trong task action mà không khai input. Tuy nhiên đọc file cấu hình thường xuyên đổi tại configuration có thể làm reconfiguration không cần thiết.

Với text file đơn giản, dùng:

~~~groovy
def contentProvider = providers.fileContents(
    layout.projectDirectory.file('tool.conf')
).asText
~~~

Nếu provider được wire vào `@Input Property<String>` của một task và chỉ đọc khi execution, thay file có thể chỉ ảnh hưởng task đó mà không bắt cả build reconfigure. Nhưng hãy xác định đúng file type, encoding và liệu đầu vào nên là `@InputFile` (giữ file identity/path/content) hay `@Input` (giữ text value) theo semantics thực tế.

## 10. Trạng thái có thể thay đổi ngoài task: nguồn gây cache sai khó nhận ra

Không phải mọi dữ liệu task đọc đều đến từ một file tĩnh. Các nguồn sau thường bị bỏ sót:

| Nguồn | Rủi ro | Hướng làm đúng |
| --- | --- | --- |
| `System.getenv('MODE')` trong action | Env đổi nhưng input key không đổi | `providers.environmentVariable` → `@Input` |
| `System.getProperty('region')` | JVM property của Daemon không ổn định qua environments | `providers.systemProperty` → `@Input` |
| `Instant.now()` | Mỗi lần có timestamp mới | Input build-time có chủ đích hoặc task non-cacheable |
| `UUID.randomUUID()` | Output nondeterministic | Seed/ID đã khai hoặc không cache |
| `Locale.getDefault()` | Formatting khác CI/máy dev | Dùng `Locale.ROOT`/locale như `@Input` |
| `ZoneId.systemDefault()` | Date/time khác timezone | Cố định zone hoặc khai zone input |
| OS line separator | Byte output khác Windows/Linux | Explicit `\n` nếu artifact cần identical bytes |
| Absolute project dir | Build Cache không relocatable | `PathSensitivity.RELATIVE` và tránh ghi absolute path |
| Network response | Remote dữ liệu thay đổi ngoài Gradle | Snapshot versioned input hoặc non-cacheable fetch |
| External CLI tool | Executable/version/output có thể thay | Khai executable/version/args/files/env; kiểm reproducibility |
| Working directory | Task phụ thuộc nơi shell được gọi | Resolve input/output từ `ProjectLayout` tại configuration |
| File existence check | Input file tree thay nhưng không được theo dõi | Declare file collection/dir input với đúng semantics |
| System temp files | Task khác/OS có thể đổi dữ liệu | Dùng task-owned temporary dirs/local state |
| Shared mutable map | Parallel tasks đua nhau ghi | Typed task properties/BuildService đúng mục đích |

### 10.1. Dữ liệu môi trường trong task output có thể là thông tin nhạy cảm

Không đưa token/password vào task output, logs hoặc shared Build Cache. Dù `providers.environmentVariable('TOKEN')` giúp đọc lazy, nếu nó được gắn `@Input` vào một **cacheable task**, dữ liệu nhạy cảm vẫn có thể tham gia input fingerprinting, các reports/cache metadata và được dùng trong execution. Điều đó không tự đảm bảo an toàn thông tin.

Với task publish/deploy gọi service và dùng credentials:

- Giữ secrets trong CI secret store hoặc Gradle credentials APIs phù hợp.
- Tránh in, serialize hoặc lưu token vào generated artifact.
- Chỉ tạo side effect khi được chọn, không cache output “đã publish” như một pure transform.
- Không coi `@CacheableTask` là lựa chọn mặc định cho upload/release/network mutation.
- Phân biệt task input dùng cho tính toán artifact với runtime credential dùng để gửi artifact.

### 10.2. Không dùng một biến `static` để giao dữ liệu giữa hai tasks

Task A ghi vào static map, task B đọc map là coupling ẩn:

~~~groovy
class Holder {
    static Map<String, String> state = [:]
}
~~~

Nếu Gradle chạy task B mà không chạy A vì `UP-TO-DATE`/`FROM-CACHE`, map có thể trống. Nếu chạy song song, tasks có thể tranh chấp. Nếu Configuration Cache restore, static map không đại diện cho task output đã được cache.

Đúng hơn, để A tạo `@OutputFile`, B nhận `@InputFile` từ provider output của A. Gradle sẽ suy ra task dependency phù hợp và kiểm files để xác định inputs. Nếu cần chia sẻ kết nối, BuildService là mục đích khác và phải giới hạn concurrency/lifecycle.

## 11. Task dependency qua file provider thay vì Project lookup

Giả sử task `generateGreeting` tạo output file, task `verifyGreeting` cần dùng nó. Đừng viết:

~~~groovy
tasks.register('badVerify') {
    doLast {
        // Sai: truy cập Project/tasks trong execution.
        def producer = project.tasks.getByName('generateGreeting')
        // Sai: hard-code đường dẫn và dependency thủ công không đủ.
        logger.quiet(new File('build/generated/greeting.txt').text)
    }
}
~~~

Thay vì lấy task object tại execution, tạo một consumer task có `@InputFile` và wire provider output trong configuration:

~~~groovy
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

abstract class PrintGreetingTask extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract RegularFileProperty getGreetingFile()

    @TaskAction
    void printFile() {
        logger.quiet(
            java.nio.file.Files.readString(
                greetingFile.get().asFile.toPath(),
                java.nio.charset.StandardCharsets.UTF_8
            ).stripTrailing()
        )
    }
}

def generated = tasks.named('generateGreeting', GenerateGreeting)

tasks.register('printGreeting', PrintGreetingTask) {
    greetingFile.set(generated.flatMap { it.outputFile })
}
~~~

**Đây là đoạn mở rộng** có thể thêm vào `build.gradle` demo đã định nghĩa `GenerateGreeting`. Nó khai provider của file output từ producer là input của consumer. Vì producer task output provider được wire đúng, Gradle có thể suy task dependency và kiểm dataflow, không cần gọi `dependsOn('generateGreeting')` nếu model này đã được thiết lập đúng.

Điểm quan trọng: `PrintGreetingTask` chỉ đọc file được declare `@InputFile`; task không gọi `project.tasks` trong `@TaskAction`. Nó **không** đánh dấu cacheable vì không tạo output artifact, chỉ in stdout.

Với đoạn mở rộng đã áp dụng, có thể chạy:

~~~bash
./gradlew -q printGreeting
~~~

Nếu input là `Linh` và suffix mặc định, task in:

~~~text
Xin chào, Linh!
~~~

Task producer có thể là `UP-TO-DATE`/`FROM-CACHE`/executed; consumer vẫn nhận đúng file nhờ provider wiring.

## 12. Khi phải thực hiện file operations hoặc external command

### 12.1. Tránh `project.copy` trong task action

Anti-pattern:

~~~groovy
@TaskAction
void copyFiles() {
    project.copy {
        from 'src/assets'
        into 'build/export'
    }
}
~~~

Dù tính năng copy hợp lệ khi gọi ở configuration/build scripts, truy cập Project từ task action không phù hợp Configuration Cache. Cũng không khai input/output của task.

Thay thế có thể là một task type `Copy`/`Sync` chuẩn, được cấu hình:

~~~groovy
tasks.register('copyAssets', Copy) {
    from(layout.projectDirectory.dir('src/assets'))
    into(layout.buildDirectory.dir('export'))
}
~~~

Đây là **mẫu riêng**: chỉ chạy được khi đã có thư mục source hoặc việc không có source được xử lý theo hành vi Copy task. Task `Copy` có semantics file operation riêng, không tự biến nó thành một cacheable transform; thường việc copy đơn thuần không cần dùng remote Build Cache.

Nếu custom task thực sự cần copy/sync khi execution, có thể dùng injected `FileSystemOperations` thay vì `Project.copy`:

~~~groovy
import javax.inject.Inject
import org.gradle.api.file.FileSystemOperations

abstract class MyFileTask extends DefaultTask {
    @Inject
    abstract FileSystemOperations getFileSystemOperations()

    @TaskAction
    void act() {
        // Dùng fileSystemOperations.copy { ... }
        // với paths lấy từ @InputFiles/@OutputDirectory đã khai.
    }
}
~~~

Đây là **khung code**: muốn chạy thì phải khai đầy đủ typed input/output properties và implementation copy tương ứng. Injection service không thay cho hợp đồng tracking.

### 12.2. Tránh `project.exec` trong task action

Anti-pattern:

~~~groovy
@TaskAction
void runExternalTool() {
    project.exec {
        commandLine 'some-tool', '--flag'
    }
}
~~~

Hướng phù hợp hơn cho custom task:

~~~groovy
import javax.inject.Inject
import org.gradle.process.ExecOperations

abstract class MyExecTask extends DefaultTask {
    @Inject
    abstract ExecOperations getExecOperations()

    @TaskAction
    void act() {
        // execOperations.exec { commandLine(...) }
        // Dùng @Input cho executable/version/args/env và
        // @InputFiles/@OutputFile cho các file liên quan.
    }
}
~~~

**Không biến ví dụ khung trên thành một custom task hoàn chỉnh** nếu chưa cung cấp inputs/outputs. `ExecOperations` giúp gọi process đúng API service từ task action, nhưng một process bất kỳ có thể nondeterministic hoặc có side effects. Nếu mục tiêu chỉ chạy executable theo Gradle lifecycle, dùng built-in `Exec`/`JavaExec` task khi phù hợp.

### 12.3. Process chạy trong configuration khác execution

Với Configuration Cache, Gradle khuyên **không gọi trực tiếp** `ProcessBuilder`, `Runtime.exec`, Groovy `execute()` hoặc `ExecOperations.exec` tại configuration time để tính ra configuration state. Các API đó có thể không cung cấp input tracking phù hợp.

Khi cần lấy stdout từ lệnh nhanh như `git rev-parse` để quyết định configuration, cân nhắc `providers.exec(...)` hoặc một `ValueSource`. Nếu value được đọc tại configuration, Gradle có thể coi nó là configuration input và phải xác định lại value ở những build tiếp theo để kiểm cache validity. Vì vậy đừng dùng một process cực chậm để đọc version nếu có thể dùng file property/CI-provided property ổn định.

**Phân biệt:** `ExecOperations.exec` trong **task action** với inputs/outputs được khai là mẫu thực thi công việc; `providers.exec`/`ValueSource` giải quyết bài toán **configuration-time computed value**. Chúng không có cùng mục đích.

## 13. Configuration Cache: lưu task graph chứ không lưu Project object

Configuration Cache lưu kết quả cấu hình để Gradle có thể bỏ qua việc chạy lại toàn bộ configuration trong invocation tương thích. Để có thể serialize/restore graph:

- Task actions không được truy cập các Gradle model objects không hỗ trợ ở execution như `Project` hoặc `Settings`.
- Task fields không nên giữ live JVM resources như `Thread`, `Socket`, `ClassLoader`, `OutputStream`, locks và mutable process state.
- Những nguồn cấu hình bên ngoài cần được theo dõi như **configuration inputs**.
- Build logic nên tránh listeners/callbacks hoặc work patterns không được Configuration Cache hỗ trợ.
- Task actions cần phụ thuộc vào chính typed task properties, providers và injected services phù hợp.

### 13.1. “Configuration Cache enabled” không đồng nghĩa sẽ hit

Lệnh:

~~~bash
./gradlew generateGreeting --configuration-cache --info
~~~

có thể lưu cache entry sau lần đầu, nhưng lần sau chỉ hit nếu build logic/configuration inputs/selection tương ứng và môi trường phù hợp. Những thay đổi có thể invalidate:

- `settings.gradle`/`build.gradle` hoặc included build plugin code.
- Gradle init scripts, `gradle.properties`, version catalogs/dependency verification configs khi liên quan.
- File/environment/system property được đọc ở configuration.
- Gradle distribution/Daemon JVM hoặc một số yếu tố môi trường.
- Task selection hoặc CLI options làm thay đổi cấu hình cần lưu.

Nếu lần thứ hai bị cache miss, đó chưa chắc là lỗi của `GenerateGreeting`: đọc configuration cache report để xác định nguyên nhân.

### 13.2. Bản thân Configuration Cache có thể nhận diện một số file/env reads

Không nên nói “Gradle không bao giờ biết bạn đọc `System.getenv` hoặc `new File(...).text` khi configuration”. Gradle hiện đại instrument nhiều reads này và liệt kê chúng như configuration inputs. Nhưng:

1. Tracking có giới hạn và phụ thuộc cách đọc; lệnh/process tùy ý có thể thoát khỏi tracking.
2. Eager configuration reads có thể làm invalidate toàn bộ configuration khi chỉ một task cần thay đổi.
3. Task outputs vẫn cần **declared task inputs/outputs** riêng.
4. Security cần lưu ý: cache state có thể chứa dữ liệu nhạy cảm đã đọc ở configuration.

Với file text simple, `providers.fileContents(...).asText` là một lựa chọn lazy. Với env, `providers.environmentVariable(...)`; với system property, `providers.systemProperty(...)`. Với complex read/process, `ValueSource` có thể là lựa chọn đúng.

### 13.3. Không dựa vào serialization tình cờ của Groovy closures

Một `doLast` capture một `Project`, `Task` khác, arbitrary classloader hoặc static singleton có thể thất bại khi Gradle lưu task graph. Ngay cả khi một build script pass hiện tại, Gradle version mới hoặc parallel execution có thể bộc lộ lỗi.

Thực hành tốt hơn là **plugin task classes riêng** với Gradle managed properties. Trong demo, class `GenerateGreeting` nằm trong `build.gradle` để người mới dễ copy thực hành; khi policy/caching behavior quan trọng cho nhiều modules, đưa task type sang **build-logic plugin project** và test riêng để tránh trộn code dài vào main script.

## 14. Cacheable không phải luôn đúng: xác định tính thuần và side effects

Một task nên xem xét `@CacheableTask` khi:

1. Có **ít nhất một output artifact hữu ích** đã khai.
2. Với cùng inputs/task implementation/toolchain dependencies, output **lặp lại được**.
3. Không có ngoại tác cần xảy ra ở mỗi invocation.
4. Những dữ liệu khác máy (paths, locale, env, OS/tool versions) đã được normalize hoặc khai input.
5. Task không viết vào file ngoài vùng output đã khai.
6. Việc restore output từ Build Cache hoàn toàn thay thế được việc chạy task action.

### 14.1. Những task thường không nên cache như pure transform

- Publish/release/upload artifact tới remote repository.
- Deploy application lên server, restart service hoặc gửi email.
- Task thực hiện migration database.
- Task có side effect ghi hệ thống bên ngoài mà không thể phục hồi chỉ bằng output files.
- Task đo live metrics/time, sinh UUID ngẫu nhiên để tạo định danh session.
- Task chỉ in log hoặc thực hiện cleanup.
- Task dùng token/credentials hoặc network state không có snapshot inputs đủ.

Đừng bọc chúng trong `@CacheableTask` chỉ để CI “nhanh hơn”. Nếu Build Cache hit khiến action không chạy, side effect quan trọng có thể **không xảy ra**. Một task non-cacheable với mô tả rõ có thể là thiết kế đúng hơn.

### 14.2. Up-to-date checking cũng có thể cần tắt có chủ đích

Một task upload có thể không có outputs Gradle quản lý; không nên giả định file local marker `uploaded.txt` là bằng chứng remote state đã đúng mãi mãi. Có trường hợp cần task luôn chạy khi được chọn hoặc kiểm remote state qua API có chủ đích.

Tuy nhiên `outputs.upToDateWhen { false }`/`@UntrackedTask` không nên trở thành biện pháp “sửa” mọi task chưa khai inputs. Chúng làm mất tối ưu hóa và có thể che thiếu sót correctness. Chỉ dùng khi thật sự có side-effect hoặc dữ liệu không thể mô hình hóa một cách đáng tin cậy, và document rõ lý do.

## 15. Tối ưu cache không làm mất correctness

### 15.1. Relocatable builds

Một task có thể cacheable nhưng không **relocatable** nếu output chứa:

~~~text
/home/worker-01/repo
~~~

ở máy A, còn máy B phải có:

~~~text
D:\ci\repo
~~~

Trong ví dụ `GenerateGreeting`, output chỉ phụ thuộc nội dung file và suffix, **không chứa absolute path**. `@PathSensitive(RELATIVE)` giúp cho input file có semantics tương đối theo workspace. Nếu cần in path tuyệt đối vào output, path đó trở thành dữ liệu ngữ nghĩa và phải được khai, hoặc chấp nhận task không remote-cache-friendly.

### 15.2. Cross-platform newline/encoding

Nếu task dùng `System.lineSeparator()`, cùng input có thể sinh CRLF trên Windows và LF trên Linux. Nếu Build Cache chia sẻ giữa các OS, artifact bytes khác nhau có thể gây sai hoặc cache misses.

Trong demo:

~~~groovy
String result = 'Xin chào, ' + name + suffix.get() + '\n'
Files.writeString(destination, result, StandardCharsets.UTF_8)
~~~

chọn rõ LF/UTF-8, nên bytes ổn định cho nội dung này. Không mặc định dùng `File.text` với encoding hệ thống khi artifact cần reproducible across CI/developer environments.

### 15.3. Toolchain và thư viện ngoài

Nếu task gọi compiler/analyzer khác phiên bản giữa dev/CI, cùng source files chưa chắc sinh output giống nhau. Những tools do Gradle quản lý có thể có tracking/toolchain integration chuyên biệt. Với custom task, bạn phải xác định version/executable flags phù hợp làm inputs. Nếu dependency chỉ được lưu trong static map “current tool version”, Build Cache không biết thay đổi ấy.

### 15.4. Output directory và local state

Chỉ khai thư mục `build/generated` làm một output chung cho nhiều tasks dễ gây overlap. Nếu một tool tạo temporary cache cục bộ không portable, có thể khai `@LocalState` và không coi nó là published output. Gradle có cơ chế dọn local state khi restore cached outputs. Không đọc những temporary files như input ẩn nếu chúng làm thay đổi generated artifacts.

## 16. Testing: chứng minh task đúng khi reuse, không chỉ pass lần đầu

### 16.1. Bộ kiểm tra bằng CLI

| Mục tiêu | Cách kiểm | Điều mong đợi |
| --- | --- | --- |
| First run đúng | `generateGreeting` | Output UTF-8 đúng tên/suffix |
| Unchanged inputs | Chạy lại cùng lệnh | Thường `UP-TO-DATE` |
| Restore build output | `clean generateGreeting --build-cache` | Có thể `FROM-CACHE` nếu entry hợp lệ |
| Input file changed | Sửa `src/message/name.txt` | Output phản ánh tên mới |
| Env var changed | Đặt `GREETING_SUFFIX=!!!` | Output phản ánh suffix mới |
| No Project at execution | `--configuration-cache` | Không có configuration-cache problem tương ứng |
| Configuration Cache reuse | Chạy hai lần cùng goal | Có thể reuse nếu build compatibility hợp lệ |
| Portable output | Chạy trong copy/moved workspace | Nội dung giống với cùng inputs |
| Output ownership | Xóa generated file, chạy lại | Gradle tái tạo hoặc restore đúng file |
| Cache disabling | `--no-build-cache` | Output vẫn đúng khi action chạy |
| Test suite | `./gradlew test` | JUnit tests pass, không phụ thuộc generated file nếu test không dùng nó |

### 16.2. Cách quan sát chi tiết

~~~bash
./gradlew generateGreeting \
    --configuration-cache --build-cache --info --stacktrace
~~~

Xem:

- Thông báo store/reuse Configuration Cache.
- Task execution history và lý do task not up-to-date.
- `UP-TO-DATE` hay `FROM-CACHE` nếu có.
- Task validation warnings/errors.
- Report HTML khi có Configuration Cache problems.
- Output file thực tế có nội dung đúng hay không.

`--info` giúp tìm nguyên nhân, nhưng **không nên parser log text như API ổn định**: Gradle version có thể đổi wording. Với automated regression tests, Gradle TestKit `TaskOutcome` là API tốt hơn khi kiểm task states.

### 16.3. TestKit dùng để kiểm caching behavior

Một Gradle plugin hoặc custom task được chia sẻ qua nhiều modules nên có **functional tests**. Một chiến lược TestKit:

1. Tạo fixture build trong `@TempDir`.
2. Áp plugin có task type cần test.
3. Tạo input file và chạy task bằng `GradleRunner`.
4. Assert output file bytes và task outcome sau lần đầu.
5. Chạy lại cùng inputs, assert `TaskOutcome.UP_TO_DATE` khi phù hợp.
6. Xóa output, chạy lại với `--build-cache`, assert correctness và kiểm `FROM_CACHE` nếu cache enabled/entry được lưu trong fixture.
7. Đổi input file/env và chạy lại, assert output đổi đúng.
8. Di chuyển fixture sang root path khác để kiểm relocatable caching.
9. Test `--configuration-cache` hai lần và không có compatibility problems.

Trích đoạn **Java 17 TestKit** minh họa core assertions (đặt trong một plugin test project có `gradleTestKit()` và JUnit Jupiter; cần fixture tạo plugin/task và inputs đúng):

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.gradle.testkit.runner.TaskOutcome;

import java.io.File;

class ExampleTestKitAssertion {
    static TaskOutcome runTask(File fixtureDir) {
        BuildResult result = GradleRunner.create()
            .withProjectDir(fixtureDir)
            .withArguments(
                "generateGreeting",
                "--build-cache",
                "--stacktrace"
            )
            .build();

        return result.task(":generateGreeting").getOutcome();
    }

    static void assertSecondRunUpToDate(File fixtureDir) {
        runTask(fixtureDir);
        assertEquals(
            TaskOutcome.UP_TO_DATE,
            runTask(fixtureDir)
        );
    }
}
~~~

**Đoạn trên là một helper minh họa, không phải standalone JUnit test class**: phải tạo đúng fixture files, copy task/plugin implementation, cung cấp JDK17 và kiểm lệnh được hỗ trợ. `TaskOutcome.FROM_CACHE` có thể dùng cho test sau khi xóa outputs với cache entry hợp lệ, nhưng không nên assert nó nếu chưa setup cache store/restore rõ.

### 16.4. Đừng chỉ assert task outcome

Một task sai có thể `UP-TO-DATE` dù file output chứa nội dung cũ, vì inputs bị khai thiếu. Vì vậy TestKit phải assert cả **file contents** sau khi đổi inputs. Chẳng hạn đặt suffix `!!!`, đọc `build/generated/greeting.txt` và xác nhận là `Xin chào, Linh!!!`; không chỉ thấy `SUCCESS` rồi coi là đúng.

### 16.5. Tránh flaky tests với environment/daemon

Khi TestKit test environment variables, sử dụng cơ chế cấu hình fixture/process environment được GradleRunner version hỗ trợ, tránh sửa `System.getenv` toàn JVM hoặc dựa vào host environment không kiểm soát. Nếu dùng shared Build Cache trong CI, cần tách cache namespaces/test fixtures để test không vô tình lấy một artifact cùng key từ người khác rồi làm assertion về execution count sai.

## 17. Những lỗi phổ biến và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Giải pháp |
| --- | --- | --- |
| Configuration Cache báo `invocation of Task.project at execution time` | Task action đọc Project | Đưa giá trị vào typed `@Input` khi configuration |
| Project bị capture trong `doLast` | Closure giữ tham chiếu Gradle model | Dùng custom task type với managed properties |
| `project.file`/`project.copy` trong `@TaskAction` | Gọi Project API ở execution | `RegularFileProperty`/`FileSystemOperations` |
| `project.exec` trong action | Project API không hợp lệ ở execution | `ExecOperations` hoặc built-in `Exec` |
| Task `UP-TO-DATE` dù env đã đổi | Env không được khai task input | `providers.environmentVariable` → `@Input` |
| Task không chạy lại khi template file đổi | Thiếu `@InputFile`/`@InputFiles` | Khai đúng files và path normalization |
| Build Cache restore output “của người khác” | Cache key thiếu inputs/implementation không deterministic | Sửa contract, vô hiệu hóa cache đến khi an toàn |
| Static counter khác giữa invocations | JVM/classloader/Daemon lifecycle không ổn định | Không dùng static state làm output input |
| Parallel tasks gây race trên global map | State shared không được đồng bộ/mô hình hóa | BuildService cho tài nguyên; file producer/consumer providers cho dữ liệu |
| Output khác Windows và Linux | Encoding/line endings/locale/timezone | Cố định hoặc khai input môi trường |
| Remote cache thường MISS | Absolute path trong input fingerprint | `@PathSensitive(RELATIVE)` khi semantics phù hợp |
| Task có output nhưng Gradle không restore | Chưa `@CacheableTask`, cache disabled hoặc cache miss | Kiểm annotations, `--build-cache --info` |
| Task không cacheable mặc dù annotated | Input validation fail/overlapping outputs hoặc cache disabled | Sửa task properties/outputs và warnings |
| `@Input` trên file path string nhưng file content không được track | Chỉ khai path scalar | Dùng `@InputFile`/`@InputDirectory` |
| `@Internal` che dữ liệu quan trọng | Property quyết định output nhưng bị loại khỏi key | Chuyển về `@Input` hoặc đúng file annotation |
| Configuration Cache miss thường xuyên | Eager config input thay đổi hoặc build logic đổi | Dùng lazy providers, xem configuration inputs report |
| Build logic chạy external command tại configuration | Process APIs không theo dõi đúng | `providers.exec` hoặc `ValueSource` khi phù hợp |
| Task action tự ghi file ngoài outputs | Undeclared output/side effects | Khai đúng `@OutputFile`/`@OutputDirectory` hoặc non-cacheable |
| Publish task bị skip vì cache | Side-effect task bị đánh dấu cacheable sai | Không dùng Build Cache cho deploy/upload semantics |
| Task cần JDK17 nhưng Gradle dùng JVM khác | Toolchain/Daemon/CLI Java khác nhau | Kiểm Gradle `--version`, Java toolchain và task runtime |
| TestKit báo plugin/task không thấy | Fixture thiếu plugin source/ID | Setup plugin-under-test classpath và files đúng |
| Configuration Cache chỉ báo lỗi khi bật flag | Vi phạm vốn đã có nhưng trước đó không được kiểm | Xem problems report và sửa build logic |
| Files đã bị xóa nhưng marker local còn | “Manual success flag” không phải real output | Khai output thật, không thay Gradle tracking bằng sentinel |

### 17.1. Một chuỗi debug có thể áp dụng ngay

~~~text
Task cho output không như kỳ vọng?
             |
             v
Trong task action có truy cập Project/Settings/Task khác?
             |
      +------+------+
      |             |
     Có            Không
      |             |
      v             v
Chuyển sang      So danh sách nguồn dữ liệu thực tế:
typed inputs     files/env/system props/time/CLI/tool/network
      |             |
      +------+------+
             |
             v
Mọi nguồn quyết định output đã là @Input/@InputFile/...?
             |
             v
Mọi file được tạo đã có @OutputFile/@OutputDirectory?
             |
             v
Task có deterministic, relocatable, side-effect-free?
             |
             v
Chạy --configuration-cache --build-cache --info
             |
             v
Đổi từng input và assert nội dung output, rồi TestKit
~~~

### 17.2. Những điều không nên làm để “chữa” cache

- Không tắt toàn bộ Configuration Cache chỉ vì một `doLast` đọc `project.version` — sửa task action.
- Không xóa `~/.gradle` liên tục: đó có thể làm lệnh chậm và không chữa khai thiếu input.
- Không gắn `@CacheableTask` lên upload/deploy chỉ để có trạng thái FROM-CACHE.
- Không đánh dấu `@Internal` lên mọi property để qua task validation.
- Không tự đặt `outputs.upToDateWhen { false }` lên mọi task rồi tuyên bố vấn đề đã giải quyết.
- Không dùng `afterEvaluate` để sửa một vi phạm **execution-time**.
- Không sửa vào build output của task khác; dùng task/provider wiring.
- Không coi một log “BUILD SUCCESSFUL” là bằng chứng outputs được tạo từ đúng inputs.

## 18. Bài tập thực hành kèm đáp án

### Bài 1 — Khi nào Project API được phép?

**Câu hỏi:** Có thể viết `tasks.register('x') { outputFile.set(layout.buildDirectory.file('x.txt')) }` không?

**Đáp án:** Có. Trong configuration, dùng ProjectLayout để wire task output là cách phù hợp. Tránh gọi `project.layout` trong `@TaskAction` để tìm output.

### Bài 2 — Vì sao `project.version` trong doLast có thể fail?

Nó truy cập Gradle Project model ở execution, không phù hợp Configuration Cache. Hơn nữa nếu output phụ thuộc version mà không khai `@Input`, cache key sai. Chuyển version thành `Property<String>` có `@Input`, wire ở configuration.

### Bài 3 — Static counter có đáng tin sau cache hit không?

Không. Static mutable state không phải Gradle task output hay persisted contract. Task có thể không chạy khi `UP-TO-DATE`/`FROM-CACHE`, Daemon/classloader cũng có thể thay đổi.

### Bài 4 — Environment đổi mà task UP-TO-DATE?

Đó là dấu hiệu một input bị bỏ sót nếu env thật sự ảnh hưởng output. Dùng `providers.environmentVariable('GREETING_SUFFIX')` và `@Input Property<String>`.

### Bài 5 — Vì sao cần PathSensitivity.RELATIVE?

Nếu input identity chỉ phụ thuộc relative location/content, absolute paths khác nhau trên máy dev/CI không nên tạo cache keys khác. `RELATIVE` giúp việc cache reuse across workspaces khi task outputs thật sự relocatable.

### Bài 6 — Có thể dùng `@Internal` để “tắt tracking” một file mà task cần không?

Không nếu file ảnh hưởng output. `@Internal` loại property khỏi task input/output model, làm cache/up-to-date checks sai.

### Bài 7 — Configuration Cache hit có bảo đảm task không chạy?

Không. Nó chỉ reuse configuration. Task vẫn chạy hoặc restore outputs theo input/output snapshot và task history/Build Cache.

### Bài 8 — Build Cache hit khác UP-TO-DATE?

`UP-TO-DATE` là reuse local output/history trong workspace; `FROM-CACHE` là restore cached outputs theo key. Cả hai có thể tránh chạy action nhưng không có nghĩa giống nhau.

### Bài 9 — Task dùng Instant.now để ghi artifact?

Nếu timestamp phải thay ở mỗi invocation, output không deterministic theo static inputs; không nên cache. Nếu timestamp là build version cố định, đưa nó thành declared `@Input` và kiểm policy về reproducibility.

### Bài 10 — Khi nào dùng Gradle BuildService?

Khi nhiều tasks cần chia sẻ resource/session/permit, nhất là giới hạn concurrency. Nhưng state trả về làm đổi output vẫn phải được khai tracked input, không dùng service để che dependency.

### Bài 11 — Dùng ExecOperations có tự khai inputs không?

Không. Nó là service thực thi external process, không tự đoán executable version, args, env hay files nào quyết định output. Phải khai hoặc không cache khi không thể khai đầy đủ.

### Bài 12 — Tại sao file output cần được công bố?

Gradle phải biết file nào thuộc task để up-to-date check, dọn/restores outputs và phát hiện ownership/overlap. Tự ghi `build/generated/x.txt` mà không có `@OutputFile` làm tracking thiếu.

### Bài 13 — TestKit phải assert điều gì?

Không chỉ task outcome. Cần kiểm output file contents khi source/env thay, `UP_TO_DATE` khi inputs không đổi, cache restore nếu có setup, và chạy với `--configuration-cache` để phát hiện unsupported Gradle model references.

### Bài 14 — Secrets có nên đưa vào cacheable @Input không?

Cẩn trọng. Provider lazy giúp giảm việc serialize raw value ở configuration, nhưng task vẫn có thể có input fingerprint/log/output dính thông tin nhạy cảm. Upload/deploy dùng secrets thường không phải cacheable pure transform; bảo vệ tokens và dùng cơ chế credential phù hợp.

### Bài 15 — Một custom task đọc config file khi configuration có tuyệt đối bị cấm?

Không. Gradle có thể theo dõi configuration-time file read, nhưng điều đó có thể làm invalidate toàn bộ Configuration Cache. Với dữ liệu chỉ cần cho task, nên wire lazy input provider hoặc `@InputFile` để thay đổi chỉ ảnh hưởng task.

### Bài 16 — Chạy `clean` rồi không thấy FROM-CACHE có phải lỗi?

Không nhất thiết. Cache có thể disabled, chưa có entry, task implementation/input key đã đổi, cache eviction hoặc Gradle task không cacheable. Xem `--info` và xác nhận file output đúng.

### Bài 17 — Vì sao dùng UTF-8 và LF cố định?

Để cùng inputs sinh cùng output bytes trên Windows/Linux, giúp reproducibility và cache sharing. Nếu output cần format theo locale/OS, biến ảnh hưởng phải được khai input.

### Bài 18 — Một task chỉ in logger.quiet có nên @CacheableTask?

Không có artifact output có ích để restore; caching task action chỉ in stdout có thể làm mất log ở cache hit. Giữ non-cacheable task phù hợp và không giả mạo output.

### Bài 19 — Consumer có thể dùng Project.tasks.getByName từ action để tìm producer không?

Không nên. Wire provider output của producer vào input của consumer **ở configuration**, tránh Project lookup tại execution và cho Gradle biết task dependency/dataflow.

### Bài 20 — Configuration Cache báo Project access, nên dùng afterEvaluate?

Không. `afterEvaluate` là lifecycle hook configuration và không chữa việc task action đọc Project. Cần chuyển dữ liệu sang typed task properties/services phù hợp.

## 19. Checklist QA cho Gradle task trước khi bật Build Cache

1. Task có mô tả rõ **đầu vào, đầu ra và side effects** không?
2. Mọi task action chỉ đọc task properties/injected services, không truy cập `Project`?
3. Không có closure `doLast`/`doFirst` capture `Project`/`Settings`/Gradle model không hỗ trợ?
4. Scalar config/version/mode được khai `@Input`?
5. Input files/directories được khai `@InputFile`/`@InputFiles`/`@InputDirectory`?
6. Classpaths được normalized bằng `@Classpath`/`@CompileClasspath` khi phù hợp?
7. File/directory outputs được khai `@OutputFile`/`@OutputDirectory`?
8. Task input path sensitivity đã chọn đúng để có thể relocatable?
9. Env/system properties ảnh hưởng output được đưa vào Provider/`@Input`?
10. Không đọc time/random/locale/host/network state như hidden inputs?
11. Không dùng static mutable state để trao đổi dữ liệu giữa tasks?
12. Nếu cần shared resource, có BuildService và limit concurrency phù hợp?
13. Custom task không ghi file ngoài outputs; local state có khai `@LocalState` khi cần?
14. Không có overlapping output directories/files giữa tasks?
15. Nếu gọi external tool, executable/version/flags/files/env được mô hình hóa?
16. Cùng inputs ở hai clean workspaces có sinh byte-identical outputs?
17. Task có thật sự đáng cache (không phải deploy/publish/email/cleanup)?
18. Đã chạy `--configuration-cache` và kiểm report?
19. Đã chạy `--build-cache --info`, kiểm UP-TO-DATE/FROM-CACHE khi phù hợp?
20. Đã thử thay từng input và assert **nội dung output**, không chỉ success status?
21. Nếu shared cache dùng trong CI, đã kiểm không có secrets/unsafe artifact leaks?
22. Có functional TestKit tests để chống tái phát lỗi khi sửa build logic?

## 20. Nguồn tài liệu Gradle chính thức

- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): tránh truy cập `Project` trong task execution, chuyển Project values thành typed inputs.
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): những Gradle model types, live JVM state và external process operations bị giới hạn; theo dõi environment/file/system properties; Providers/ValueSource.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration inputs, cache invalidation, serialization và reports.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): cache key, `@CacheableTask`, output reuse và điều kiện cacheable.
- [Gradle — Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html): repeatable outputs, relocatable inputs, cache misses/hits.
- [Gradle — Common Build Cache Problems](https://docs.gradle.org/current/userguide/common_caching_problems.html): undeclared inputs, environment, line endings, timezone, overlapping outputs và non-repeatable results.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): task classes, annotations, Inputs/Outputs APIs.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): up-to-date checking, declared input/output semantics.
- [Gradle — Shared Build Services](https://docs.gradle.org/current/userguide/build_services.html): sharing resources giữa tasks, lifecycle và `@ServiceReference`.
- [Gradle — Services and Service Injection](https://docs.gradle.org/current/userguide/service_injection.html): `ExecOperations`, `FileSystemOperations`, `ProviderFactory` và supported services.
- [Gradle — Lazy Configuration](https://docs.gradle.org/current/userguide/lazy_configuration.html): `Property<T>`, `Provider<T>`, typed task properties và provider wiring.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `register`, `named` và configuration avoidance.
- [Gradle — TestKit](https://docs.gradle.org/current/userguide/test_kit.html): functional tests, `GradleRunner`/`TaskOutcome`.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): JDK selection cho Java 17 tasks.
