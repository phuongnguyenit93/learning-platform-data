# Build toàn bộ và build tăng dần

Gradle tránh lặp lại những công việc đã hoàn thành và còn kết quả hợp lệ. Khi chạy lệnh build, Gradle tạo task graph, kiểm tra input và output của từng task, rồi quyết định task nào cần thực thi, task nào đã up-to-date và task nào có thể khôi phục kết quả từ build cache.

Build toàn bộ thường là build từ trạng thái sạch, hay dùng lệnh:

~~~bash
./gradlew clean build
~~~

Build tăng dần tận dụng lịch sử build và output trước đó:

~~~bash
./gradlew build
~~~

Hai cách chạy phục vụ mục đích khác nhau. Build sạch giúp xác minh quá trình tạo output từ đầu; build tăng dần giúp vòng lặp phát triển nhanh hơn khi chỉ một phần đầu vào thay đổi.

## 1. Build task và task graph

Task build là lifecycle task gom các công việc cần thiết, thường gồm kiểm tra và đóng gói. Nó không có nghĩa mọi task trong dự án đều phải thực thi action ở mỗi lần chạy.

Ví dụ task graph rút gọn:

~~~text
build
├── check
│   └── test
│       ├── compileTestJava
│       └── processTestResources
└── assemble
    └── jar
        └── classes
            ├── compileJava
            └── processResources
~~~

Gradle chọn task từ lệnh gọi và các quan hệ dependency. Task không thuộc graph sẽ không chạy, dù được khai báo trong build script.

Xem kế hoạch mà không thực hiện task action:

~~~bash
./gradlew build --dry-run --console=plain
~~~

Trong dry run, task được liệt kê với trạng thái SKIPPED do action không được thực thi ở chế độ xem thử. Đây không phải bằng chứng task sẽ là UP-TO-DATE trong lần chạy thật.

## 2. Build toàn bộ

Lệnh:

~~~bash
./gradlew clean build
~~~

chạy task clean trước build. Task clean thường xóa thư mục build của project, bao gồm class đã biên dịch, resource đã xử lý, report và artifact được tạo ở lần trước.

Sau đó Gradle thực hiện các task cần thiết để tạo lại output. Cách này hữu ích khi:

- Xác nhận project build được từ trạng thái không có output cục bộ.
- Nghi ngờ output cũ không phản ánh source hiện tại.
- Thay đổi plugin hoặc cấu hình build.
- Kiểm tra quy trình build trước khi phát hành.
- Điều tra lỗi chỉ xuất hiện khi tạo lại artifact.

Clean build không xóa mọi cache Gradle. Dependency đã tải, Gradle User Home, daemon, configuration cache và build cache có thể vẫn tồn tại. Nếu build cache bật, Gradle có thể khôi phục output từ cache sau khi clean.

Vì vậy, clean build không nhất thiết có nghĩa mọi task action đều chạy lại.

## 3. Build tăng dần

Lệnh thường dùng:

~~~bash
./gradlew build
~~~

Gradle kiểm tra trạng thái của các task dựa trên input, output và lịch sử thực thi. Nếu một task không có thay đổi liên quan và output vẫn hợp lệ, task có thể được đánh dấu UP-TO-DATE.

Ví dụ:

~~~text
> Task :compileJava UP-TO-DATE
> Task :processResources UP-TO-DATE
> Task :classes UP-TO-DATE
> Task :test UP-TO-DATE
> Task :jar UP-TO-DATE

BUILD SUCCESSFUL
~~~

Các task vẫn thuộc graph. Gradle đã kiểm tra và kết luận không cần chạy action của chúng.

Nếu chỉ một file Java thay đổi, compileJava có thể chạy lại và các task downstream được xem xét dựa trên output mới. Task xử lý resource có thể vẫn UP-TO-DATE nếu resource không thay đổi.

## 4. Up-to-date checking

Gradle theo dõi input và output của task. Khi input không đổi và output cục bộ còn hợp lệ, task có thể được bỏ qua.

Một task biên dịch Java có thể phụ thuộc vào:

- Tệp source trong source set.
- Compile classpath.
- Compiler options.
- Compiler hoặc task implementation.
- Các property khác ảnh hưởng đến kết quả.

Nếu các yếu tố liên quan không thay đổi, Gradle có thể dùng output hiện tại.

Để cơ chế này đáng tin cậy, task cần khai báo đầy đủ dữ liệu mà nó đọc và tạo. Nếu task đọc một file nhưng không khai báo file đó là input, Gradle có thể không phát hiện khi file thay đổi. Ngược lại, nếu khai báo input quá rộng hoặc không ổn định, task có thể chạy lại dù thay đổi không ảnh hưởng kết quả.

Task không có output được khai báo thường không thể được xem là up-to-date theo cách thông thường. Không nên khai báo output giả chỉ để khiến task được bỏ qua.

## 5. Khai báo input và output cho custom task

Gradle cung cấp annotation để mô tả dữ liệu task sử dụng và tạo ra.

| Annotation | Ý nghĩa |
|---|---|
| @Input | Giá trị đơn như chuỗi, số hoặc boolean |
| @InputFile | Một tệp đầu vào |
| @InputFiles | Tập hợp tệp đầu vào |
| @InputDirectory | Thư mục đầu vào |
| @OutputFile | Tệp đầu ra |
| @OutputDirectory | Thư mục đầu ra |
| @Nested | Đối tượng lồng nhau có các property được theo dõi |
| @Internal | Property không dùng làm input/output fingerprint |
| @LocalState | Trạng thái cục bộ của task, không phải output chia sẻ như build cache |

Ví dụ task tạo file từ một giá trị:

~~~kotlin
abstract class GenerateGreeting : DefaultTask() {
    @get:Input
    abstract val greeting: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        outputFile.get().asFile.apply {
            parentFile.mkdirs()
            writeText(greeting.get())
        }
    }
}
~~~

Đăng ký task:

~~~kotlin
tasks.register<GenerateGreeting>("generateGreeting") {
    greeting.set("Hello Gradle")
    outputFile.set(layout.buildDirectory.file("generated/greeting.txt"))
}
~~~

Gradle biết task đọc property greeting và tạo file đầu ra. Nếu giá trị và output không đổi, task có thể được đánh dấu up-to-date.

Custom task trong dự án thực tế nên được đặt trong build logic hoặc convention plugin phù hợp, thay vì đưa nhiều logic vào build script.

## 6. Incremental task và InputChanges

Up-to-date checking có thể bỏ qua toàn bộ task khi không có thay đổi. Nhưng nếu một vài input thay đổi, task vẫn cần chạy. Một **incremental task** có thể xử lý riêng các file được thêm, sửa hoặc xóa.

Giả sử task chuyển các file văn bản thành file viết hoa:

~~~text
src/text/
├── a.txt
├── b.txt
└── c.txt
~~~

Output:

~~~text
build/processed/
├── a.txt.upper
├── b.txt.upper
└── c.txt.upper
~~~

Nếu chỉ b.txt thay đổi, task có thể chỉ xử lý lại file đó. Nếu c.txt bị xóa, task cần xóa output c.txt.upper tương ứng.

Gradle cung cấp InputChanges. Input file hoặc directory phải được đánh dấu Incremental và có path sensitivity phù hợp.

Ví dụ task Kotlin minh họa, đặt trong build logic hoặc convention plugin:

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Incremental
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.ChangeType
import org.gradle.work.InputChanges

@CacheableTask
abstract class ProcessTextFiles : DefaultTask() {
    @get:InputDirectory
    @get:Incremental
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sourceDirectory: DirectoryProperty

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun process(changes: InputChanges) {
        val outputRoot = outputDirectory.get().asFile

        if (!changes.isIncremental) {
            outputRoot.deleteRecursively()
        }

        val sourceTree = sourceDirectory.get().asFileTree

        changes.getFileChanges(sourceTree).forEach { change ->
            val output = outputRoot.resolve(change.normalizedPath + ".upper")

            when (change.changeType) {
                ChangeType.REMOVED -> output.delete()
                else -> {
                    output.parentFile.mkdirs()
                    output.writeText(change.file.readText().uppercase())
                }
            }
        }
    }
}
~~~

Đăng ký task:

~~~kotlin
tasks.register<ProcessTextFiles>("processTextFiles") {
    sourceDirectory.set(layout.projectDirectory.dir("src/text"))
    outputDirectory.set(layout.buildDirectory.dir("processed"))
}
~~~

Trong ví dụ:

- @InputDirectory khai báo thư mục nguồn.
- @Incremental cho biết task có thể nhận danh sách thay đổi.
- @PathSensitive(PathSensitivity.RELATIVE) xét đường dẫn tương đối với input root.
- @OutputDirectory khai báo thư mục kết quả.
- InputChanges cung cấp các file đã thêm, sửa hoặc xóa.
- File bị xóa phải kéo theo việc xóa output tương ứng.
- Khi không có lịch sử incremental hợp lệ, task xóa output cũ và xử lý lại toàn bộ input hiện có.

Đây là ví dụ minh họa API. Task thực tế cần xử lý lỗi I/O, encoding, tên output, file trùng đường dẫn và các loại input cụ thể.

Các loại thay đổi:

| ChangeType | Ý nghĩa | Hành động thường cần |
|---|---|---|
| ADDED | File mới | Tạo output tương ứng |
| MODIFIED | File thay đổi | Cập nhật output tương ứng |
| REMOVED | File bị xóa | Xóa output cũ tương ứng |

Nếu task bỏ qua REMOVED, output cũ có thể còn sót lại và làm artifact chứa dữ liệu không còn trong source.

## 7. Incremental Java compilation

Gradle Java plugin hỗ trợ incremental compilation. Khi source thay đổi, Gradle có thể phân tích quan hệ giữa các class để giới hạn phạm vi biên dịch lại.

Ví dụ:

~~~text
src/main/java/
├── com/example/model/Customer.java
├── com/example/service/CustomerService.java
└── com/example/app/Main.java
~~~

Nếu chỉ thay đổi phần thân một method trong Customer mà không làm thay đổi API công khai, compiler có thể chỉ cần biên dịch lại class thay đổi.

Nếu thay đổi public method hoặc kiểu dữ liệu mà class khác phụ thuộc, phạm vi biên dịch lại có thể mở rộng đến các source bị ảnh hưởng.

Không nên giả định mọi lần sửa một file chỉ biên dịch đúng một file. Gradle có thể phải biên dịch lại nhiều class khi thay đổi ảnh hưởng đến ABI hoặc dependency analysis.

Một số nguyên nhân khiến compileJava chạy lại:

- Source Java thay đổi.
- Compile classpath thay đổi.
- Compiler options hoặc toolchain thay đổi.
- Annotation processor hoặc processor path thay đổi.
- Input khác được khai báo cho task thay đổi.
- Output bị xóa hoặc không còn hợp lệ.
- Không có lịch sử task phù hợp.

Nếu chỉ thay đổi resource, task xử lý resource có thể chạy lại trong khi compileJava vẫn up-to-date.

## 8. Build cache

Build cache cho phép Gradle lưu output của task theo input và task implementation. Khi một lần build khác có cùng cache key và output phù hợp, Gradle có thể khôi phục output thay vì chạy action.

Ví dụ:

~~~text
> Task :compileJava FROM-CACHE
> Task :processResources UP-TO-DATE
> Task :jar
~~~

**FROM-CACHE** nghĩa là Gradle khôi phục output từ build cache. **UP-TO-DATE** nghĩa output cục bộ đã hợp lệ. Cả hai đều tránh thực hiện action nhưng nguồn kết quả khác nhau.

Bật build cache bằng command line:

~~~bash
./gradlew build --build-cache
~~~

Hoặc trong gradle.properties:

~~~properties
org.gradle.caching=true
~~~

Build cache có thể là local hoặc remote. Local cache hữu ích giữa các lần build trên cùng máy. Remote cache cho phép máy phát triển và CI dùng chung output được tạo bởi build tương thích.

Task chỉ nên cache khi cùng input và implementation luôn tạo output tương đương. Không nên cache task phụ thuộc vào dữ liệu không khai báo như thời gian hiện tại, biến môi trường không được theo dõi, trạng thái dịch vụ từ xa, random value hoặc thông tin máy cục bộ.

Với custom task, @CacheableTask thể hiện task có thể dùng build cache. Nếu task có side effect hoặc output không xác định, không nên gắn annotation này chỉ để tăng tốc.

## 9. Up-to-date checking và build cache khác nhau

| Cơ chế | Điều kiện | Kết quả |
|---|---|---|
| Up-to-date checking | Output cục bộ còn hợp lệ và input không đổi | Bỏ qua action, dùng output hiện có |
| Build cache | Cache có output cho key tương ứng | Khôi phục output từ cache |
| Incremental task action | Task cần chạy và hỗ trợ InputChanges | Xử lý phần input thay đổi |
| Task không incremental | Task cần chạy nhưng không hỗ trợ xử lý từng phần | Thực hiện lại action theo logic task |

Ví dụ:

1. Lần đầu, Gradle chạy compileJava và có thể lưu output vào cache.
2. Lần sau trên cùng workspace, nếu input/output không đổi, compileJava có thể là UP-TO-DATE.
3. Nếu output cục bộ bị xóa nhưng cache có kết quả phù hợp, task có thể là FROM-CACHE.
4. Nếu input thay đổi, cache key thay đổi; Gradle chạy task hoặc tìm output cache phù hợp với input mới.
5. Nếu task incremental, action có thể chỉ xử lý các file thay đổi.

## 10. Configuration cache

Configuration cache lưu kết quả cấu hình build để những lần chạy sau có thể giảm công việc cấu hình.

Bật bằng command line:

~~~bash
./gradlew build --configuration-cache
~~~

Hoặc trong gradle.properties:

~~~properties
org.gradle.configuration-cache=true
~~~

Configuration cache khác build cache:

| Cơ chế | Lưu gì? | Giai đoạn được tối ưu |
|---|---|---|
| Configuration cache | Kết quả cấu hình build và mô hình task phù hợp | Configuration phase |
| Build cache | Output của task có thể cache | Execution phase |
| Up-to-date checking | Trạng thái input/output và lịch sử task | Tránh chạy task action |
| Dependency cache | Metadata và artifact đã phân giải/tải về | Dependency resolution |

Khi configuration cache được tái sử dụng, Gradle vẫn cần xác định task graph và kiểm tra trạng thái task. Configuration cache không có nghĩa mọi task được bỏ qua.

Một build có thể dùng configuration cache nhưng không bật build cache, hoặc bật build cache nhưng configuration cache chưa được tái sử dụng.

## 11. Gradle daemon, file system watching và parallel execution

Các cơ chế này cũng giúp build nhanh hơn nhưng không phải bản thân incremental build.

**Gradle daemon** là tiến trình JVM chạy nền, giúp giảm chi phí khởi động JVM và tái sử dụng môi trường giữa các lần gọi Gradle. Daemon không có nghĩa task action tự động bị bỏ qua.

**File system watching** giúp Gradle theo dõi thay đổi filesystem và giảm chi phí quét file trong một số build. Nó không thay thế khai báo input/output và không tự làm task trở thành incremental.

Tùy chọn parallel:

~~~bash
./gradlew build --parallel
~~~

cho phép Gradle thực thi các project độc lập song song khi graph và cấu hình cho phép. Task có quan hệ dependency vẫn tuân theo thứ tự hợp lệ. Task dùng chung tài nguyên hoặc ghi cùng output phải được thiết kế cẩn thận để tránh race condition.

## 12. Vì sao task chạy lại dù source không thay đổi?

Nếu task liên tục chạy lại, hãy tìm nguyên nhân input hoặc output thay đổi.

Các trường hợp thường gặp:

- Task đọc file nhưng file chưa được khai báo là input.
- Task ghi output ra ngoài output directory đã khai báo.
- Output bị task khác hoặc người dùng xóa.
- Input chứa timestamp hoặc giá trị thay đổi mỗi lần build.
- Classpath hoặc compiler options thay đổi.
- Plugin hoặc task implementation thay đổi.
- Task không khai báo output.
- Task có side effect không được mô tả trong input/output.
- Task được cấu hình để luôn chạy lại theo điều kiện riêng.

Chạy log chi tiết:

~~~bash
./gradlew build --info --console=plain
~~~

Với task cụ thể:

~~~bash
./gradlew :app:compileJava --info --console=plain
~~~

Log giúp xác định input property thay đổi, output không tồn tại hoặc task không có history.

## 13. Vì sao task không chạy dù file đã thay đổi?

Trường hợp này thường cho thấy input không được khai báo đúng hoặc thay đổi không nằm trong phạm vi task theo dõi.

Ví dụ custom task đọc file cấu hình qua đường dẫn hard-code nhưng không khai báo file đó là input. Gradle không biết nội dung file ảnh hưởng đến kết quả, nên có thể coi task vẫn up-to-date.

Cách xử lý:

1. Xác định mọi file, property và môi trường ảnh hưởng đến kết quả.
2. Khai báo chúng thành input bằng annotation hoặc API task phù hợp.
3. Đảm bảo output được khai báo chính xác.
4. Tránh đọc file ngoài project mà không mô tả dependency.
5. Chạy lại task và quan sát trạng thái.

Nếu task cần đọc biến môi trường, đưa giá trị đó thành input property thay vì truy cập trực tiếp giữa task action. Khi giá trị thay đổi, Gradle có dữ liệu để tính lại trạng thái task.

## 14. Path sensitivity và khả năng tái sử dụng cache

Đối với file input, Gradle cần biết đường dẫn có phải là một phần của kết quả hay không.

Một số lựa chọn:

- **ABSOLUTE:** xét đường dẫn tuyệt đối; hai workspace khác nhau có thể tạo fingerprint khác.
- **RELATIVE:** xét đường dẫn tương đối với input root; phù hợp khi cấu trúc giống nhau nhưng checkout path khác.
- **NAME_ONLY:** chỉ xét tên file.
- **NONE:** không xét đường dẫn, chỉ xét nội dung theo semantics phù hợp.

Ví dụ:

~~~kotlin
@get:InputFiles
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val sourceFiles: ConfigurableFileCollection
~~~

Chọn path sensitivity dựa trên việc đường dẫn có ảnh hưởng đến kết quả hay không. Không nên chọn NONE chỉ để tăng cache hit nếu task thực sự cần phân biệt vị trí file.

Path sensitivity phù hợp có thể giúp output cache được tái sử dụng giữa các máy có workspace path khác nhau, miễn là các input và môi trường còn lại tương thích.

## 15. Những thay đổi nào có thể làm task chạy lại?

| Thay đổi | Task có thể bị ảnh hưởng |
|---|---|
| Sửa file Java | compileJava và task phụ thuộc output compile |
| Sửa file resource | processResources và task đóng gói |
| Sửa file test | compileTestJava, test |
| Thay dependency version | Task dùng compile/runtime classpath liên quan |
| Thay compiler options | Task biên dịch tương ứng |
| Thay file cấu hình được khai báo là input | Task đọc cấu hình đó |
| Xóa output build | Task tạo output đó |
| Thay task implementation hoặc plugin | Task liên quan và cache key |
| Sửa file không thuộc input của task | Task đó có thể không cần chạy lại |

Gradle không nhất thiết chạy lại toàn bộ build khi một file thay đổi. Chỉ những task có dependency trực tiếp hoặc gián tiếp với input bị ảnh hưởng mới cần xem xét lại.

## 16. clean, rerun-tasks và no-build-cache

Các tùy chọn này có tác động khác nhau.

**clean**:

~~~bash
./gradlew clean build
~~~

Xóa output build theo task clean rồi chạy build. Cache trong Gradle User Home không nhất thiết bị xóa. Nếu build cache bật, Gradle có thể khôi phục output phù hợp.

**rerun-tasks**:

~~~bash
./gradlew build --rerun-tasks
~~~

Yêu cầu Gradle thực thi lại task thay vì dựa vào trạng thái up-to-date thông thường.

**no-build-cache**:

~~~bash
./gradlew build --no-build-cache
~~~

Tắt sử dụng build cache cho lần chạy này.

Nếu mục tiêu là xóa output project, yêu cầu task chạy lại và không lấy output từ build cache:

~~~bash
./gradlew clean build --rerun-tasks --no-build-cache
~~~

Lệnh này vẫn không xóa dependency cache hoặc toàn bộ Gradle User Home. Nó cũng không đồng nghĩa xóa configuration cache. Nếu muốn kiểm tra cấu hình build từ đầu, có thể tắt riêng configuration cache:

~~~bash
./gradlew clean build --rerun-tasks --no-build-cache --no-configuration-cache
~~~

Không nên dùng các tùy chọn này cho mọi build hằng ngày. Chúng hữu ích khi chẩn đoán hoặc xác minh; build tăng dần thông thường nên tận dụng các cơ chế tối ưu.

## 17. Dependency cache khác build cache

Gradle có thể lưu metadata và artifact dependency đã tải về để không phải truy vấn repository hoặc tải lại JAR mỗi lần.

Đây là dependency cache, khác với build cache:

- Dependency cache giữ metadata và artifact từ repository.
- Build cache giữ output của task có thể tái sử dụng.
- Configuration cache giữ kết quả cấu hình build.
- Task history và snapshot hỗ trợ up-to-date checking.

Nếu nghi ngờ dependency metadata cũ, có thể dùng:

~~~bash
./gradlew build --refresh-dependencies
~~~

Tùy chọn này yêu cầu Gradle kiểm tra lại thông tin dependency. Nó không có nghĩa mọi artifact chắc chắn được tải lại toàn bộ; Gradle có thể dùng metadata và checksum để xác định artifact còn hợp lệ.

Xóa dependency cache không phải cách thông thường để buộc task chạy lại.

## 18. Best practices để incremental build đáng tin cậy

- Khai báo đầy đủ input và output của custom task.
- Giữ task có tính xác định: cùng input nên tạo output tương đương.
- Không ghi file ngoài output đã khai báo.
- Dùng lazy configuration và tasks.register khi phù hợp.
- Chỉ đánh dấu cacheable khi task an toàn để chia sẻ output.
- Xử lý đầy đủ file bị xóa trong incremental task.
- Không phụ thuộc vào thứ tự task không được khai báo.
- Kiểm tra cả incremental build và clean build trên CI.
- Tránh đưa timestamp, random value hoặc đường dẫn máy cục bộ vào output nếu chúng không phải yêu cầu thực tế.
- Cô lập tài nguyên dùng chung trước khi bật parallel execution.

Lazy task registration giúp Gradle tránh cấu hình task không cần thiết, nhưng không tự làm task action trở thành incremental.

Task có side effect như gửi email hoặc cập nhật hệ thống bên ngoài không nên được cache như task tạo file thuần túy. Nếu có thể, tách bước tạo artifact xác định khỏi bước phát hành có side effect.

## 19. Ví dụ một vòng đời build tăng dần

Giả sử project Java có ba task chính:

- compileJava: biên dịch source Java.
- processResources: sao chép và xử lý resource.
- jar: đóng gói output của main.

### Lần đầu

~~~bash
./gradlew build
~~~

Gradle chưa có output hoặc history hợp lệ nên các task cần thiết được thực thi:

~~~text
> Task :compileJava
> Task :processResources
> Task :classes
> Task :jar
> Task :test
> Task :check
> Task :build

BUILD SUCCESSFUL
~~~

### Lần thứ hai, không có thay đổi

~~~bash
./gradlew build
~~~

Các task có thể là UP-TO-DATE:

~~~text
> Task :compileJava UP-TO-DATE
> Task :processResources UP-TO-DATE
> Task :classes UP-TO-DATE
> Task :jar UP-TO-DATE
> Task :test UP-TO-DATE
> Task :check UP-TO-DATE
> Task :build

BUILD SUCCESSFUL
~~~

Lifecycle task như build có thể không có action riêng nên output không nhất thiết hiển thị cùng trạng thái như task tạo file.

### Lần thứ ba, chỉ sửa một file Java

Gradle phát hiện source thay đổi. compileJava cần chạy; các task downstream như classes, jar hoặc test được xem xét dựa trên output mới.

~~~text
> Task :compileJava
> Task :processResources UP-TO-DATE
> Task :classes
> Task :jar
> Task :test
> Task :check
> Task :build

BUILD SUCCESSFUL
~~~

Đây là ví dụ minh họa. Trạng thái thực tế phụ thuộc loại thay đổi, dependency, task implementation, cache và các file đầu ra.

### Lần thứ tư, chỉ sửa một resource

Task compileJava có thể vẫn UP-TO-DATE, trong khi processResources và các task đóng gói liên quan chạy lại.

Điều này cho thấy Gradle không chỉ kiểm tra một dấu hiệu chung cho toàn build. Mỗi task có input/output và dependency riêng.

## 20. Đọc task outcome khi điều tra build

| Outcome | Ý nghĩa |
|---|---|
| Không có hậu tố đặc biệt | Task action đã được thực thi |
| **UP-TO-DATE** | Input và output cục bộ còn hợp lệ, không cần chạy action |
| **FROM-CACHE** | Output được khôi phục từ build cache |
| **NO-SOURCE** | Task được chọn nhưng không có source file phù hợp để xử lý |
| **SKIPPED** | Task được chọn nhưng action bị bỏ qua, ví dụ điều kiện onlyIf không thỏa mãn |
| **FAILED** | Task thực thi thất bại |

Phân biệt task không được chọn với task được chọn nhưng không chạy action:

- Nếu task không có trong graph, Gradle không yêu cầu task đó cho lệnh hiện tại.
- Nếu task là UP-TO-DATE, Gradle đã kiểm tra và giữ output hiện tại.
- Nếu task là FROM-CACHE, Gradle đã lấy output phù hợp từ cache.
- Nếu task là SKIPPED, task có trong graph nhưng action không được thực hiện theo điều kiện.
- Nếu task là NO-SOURCE, task không có file nguồn phù hợp.

Khi đọc log, hãy xác định đúng trạng thái thay vì kết luận mọi task không thực thi action đều bị bỏ qua cùng một lý do.

## 21. Quy trình chẩn đoán build chậm hoặc incremental không hoạt động

Có thể điều tra theo trình tự:

1. Chạy đúng task đang chậm, tránh gọi cả build nếu không cần.
2. Dùng --info --console=plain để xem task nào chạy lại và lý do.
3. Kiểm tra task graph bằng --dry-run nếu chưa rõ task nào được chọn.
4. Xem input/output của task và xác định file hoặc property nào thay đổi.
5. Kiểm tra task custom có khai báo đủ input/output không.
6. Kiểm tra output có bị task khác hoặc script ngoài Gradle sửa/xóa không.
7. Xác định task có hỗ trợ incremental action hay chỉ hỗ trợ up-to-date checking.
8. Kiểm tra build cache có bật và task có cacheable không.
9. Kiểm tra configuration cache riêng nếu thời gian cấu hình chiếm phần lớn build.
10. So sánh build tăng dần với clean build để phát hiện output cũ hoặc metadata thiếu.
11. Chạy kiểm thử trên CI từ workspace sạch khi cần xác minh tính tái lập.

Các lệnh hữu ích:

~~~bash
# Xem task được chọn
./gradlew build --dry-run --console=plain

# Xem lý do task chạy lại
./gradlew build --info --console=plain

# Bật build cache
./gradlew build --build-cache

# Xem dependency runtime
./gradlew dependencies --configuration runtimeClasspath

# Build sạch, buộc chạy lại và không dùng build cache
./gradlew clean build --rerun-tasks --no-build-cache
~~~

Nếu build chậm chủ yếu ở configuration phase, hãy xem configuration cache và cấu hình plugin. Nếu chậm ở execution phase, hãy xem task input/output, build cache, incremental task action và khả năng chạy song song.

## 22. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Mỗi lần build đều chạy lại compileJava | Source, classpath hoặc compiler options thay đổi; output thiếu; không có history | Dùng --info và kiểm tra input/output |
| Task custom chạy lại dù file không đổi | Thiếu khai báo input/output hoặc input không ổn định | Dùng annotation và property phù hợp |
| File đã xóa nhưng output vẫn còn | Incremental task không xử lý ChangeType.REMOVED | Xóa output tương ứng khi nhận thay đổi REMOVED |
| Clean build vẫn hiển thị FROM-CACHE | Build cache được bật và có output phù hợp | Dùng --no-build-cache nếu cần chạy action thật |
| Build cache không có tác dụng | Task không cacheable, input/output không đầy đủ hoặc key khác | Kiểm tra cache configuration và task annotations |
| Task bị bỏ qua dù cần chạy | Input không được khai báo hoặc output cũ bị coi là hợp lệ | Bổ sung input và kiểm tra task history |
| Build tăng dần cục bộ thành công nhưng CI lỗi | Workspace cục bộ có output cũ hoặc CI thiếu cấu hình | Chạy clean build và kiểm tra môi trường CI |
| Configuration cache không làm compile nhanh hơn | Configuration cache giảm thời gian cấu hình, không thay thế compile/task execution | Xem riêng execution và build cache |
| Song song hóa gây lỗi không ổn định | Task ghi chung output hoặc dùng tài nguyên dùng chung | Khai báo dependency, cô lập tài nguyên và output |

## 23. Những nguyên tắc cần nhớ

- **build** là lifecycle task; nó không có nghĩa mọi task con phải thực thi action trong mỗi lần chạy.
- **clean build** xóa output project rồi build lại, nhưng build cache vẫn có thể khôi phục output nếu được bật.
- **Incremental build** tận dụng task history, input/output snapshot, up-to-date checking và cache để tránh công việc không cần thiết.
- **UP-TO-DATE** nghĩa output cục bộ còn hợp lệ; **FROM-CACHE** nghĩa output được lấy từ build cache.
- Incremental task dùng **InputChanges** để xử lý file được thêm, sửa hoặc xóa.
- Custom task phải khai báo đầy đủ input/output và xử lý file bị xóa để kết quả đáng tin cậy.
- Java compilation có thể biên dịch lại một phần source tùy quan hệ class và loại thay đổi.
- Build cache lưu output task; configuration cache lưu kết quả cấu hình; dependency cache giữ metadata và artifact dependency.
- Gradle daemon, file system watching và parallel execution giúp tăng tốc theo những cách khác nhau.
- **--rerun-tasks**, **--no-build-cache**, **clean** và **--no-configuration-cache** có tác động riêng; chỉ dùng khi mục tiêu chẩn đoán yêu cầu.
- Task cacheable phải có kết quả xác định từ các input được khai báo.
- Nên kiểm tra cả incremental build lẫn clean build trên CI để phát hiện output cũ và dependency bị khai báo thiếu.

Build tăng dần là một phần quan trọng giúp Gradle giữ vòng lặp phát triển nhanh. Khi task khai báo đúng input và output, Gradle có thể bỏ qua task còn hợp lệ, khôi phục output từ cache hoặc chỉ xử lý phần file thay đổi. Hiểu rõ những cơ chế này giúp nhóm vừa tăng tốc build thường ngày vừa biết cách tạo lại toàn bộ output khi cần xác minh một bản build sạch.
