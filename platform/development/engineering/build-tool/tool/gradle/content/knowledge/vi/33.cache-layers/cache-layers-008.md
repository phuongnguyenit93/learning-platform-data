# Chẩn đoán cache miss, cache sai và trường hợp cần tắt cache có phạm vi trong Gradle

## 1. Mục tiêu và tư duy đúng khi xử lý cache

Khi Gradle build chậm hoặc tạo kết quả không đúng, một phản xạ phổ biến là chạy `clean`, `--refresh-dependencies`, xóa `~/.gradle/caches`, rồi kết luận “lỗi cache”. Cách này thường phá bằng chứng chẩn đoán, khiến build tốn thời gian hơn và không sửa được **nguồn gốc** của vấn đề: một input chưa được khai báo, một tác vụ không deterministic, một thuộc tính môi trường biến động hoặc một lớp cache khác với lớp ta đang nghĩ tới.

Bài học này tập trung ba tình huống:

1. **Cache miss không mong đợi:** một task lẽ ra tái sử dụng output nhưng bị chạy lại hoặc không tìm thấy entry phù hợp.
2. **Cache hit sai / kết quả cũ không đúng:** Gradle ghi `UP-TO-DATE` hay `FROM-CACHE` nhưng nội dung artifact không phản ánh thay đổi thực tế.
3. **Không nên cache hoặc cần tắt tạm đúng phạm vi:** một task phụ thuộc thời gian, mạng, trạng thái bên ngoài, có side effect hoặc plugin chưa tương thích Configuration Cache.

Bạn sẽ biết cách:
- Phân biệt **up-to-date checks**, **Build Cache**, **Configuration Cache**, **dependency cache** và một số optimizations liên quan.
- Diễn giải `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, `SKIPPED`, `EXECUTED` thay vì gọi chung là “cache”.
- Chạy một quy trình điều tra có kiểm soát trước khi đụng cache directories.
- Dùng `--info`, `--console=plain`, `-Dorg.gradle.caching.debug=true`, Gradle/Develocity Build Scan và Configuration Cache report để tìm input hoặc implementation thay đổi.
- Xác định cache key dựa trên task implementation, input values/file fingerprints và output property names; hiểu `@PathSensitive`/`@Classpath`.
- Tạo custom `@CacheableTask` **Java 17** với inputs/outputs khai báo đúng; chứng minh `EXECUTED → UP-TO-DATE → FROM-CACHE`.
- Dùng `--no-build-cache`, `--no-configuration-cache`, `--rerun-tasks`, `--rerun`, `outputs.doNotCacheIf` và `notCompatibleWithConfigurationCache` đúng nhu cầu.
- Phân biệt việc refresh **dependency resolution** với việc vô hiệu hóa **task output caching**.
- Xử lý nguy cơ remote/shared cache và bảo toàn chứng cứ trong CI.

Bài sử dụng **Gradle Kotlin DSL** và **Java 17**, với nguồn tham chiếu Gradle chính thức. Các lệnh Linux/macOS sử dụng `./gradlew`; Windows PowerShell dùng `.\gradlew.bat`. Những ví dụ nói đến trạng thái task mô tả **kết quả dự kiến trong môi trường sạch và ổn định**, không cam kết mọi dòng console giống nhau ở mọi bản Gradle.

## 2. Các lớp cache: cùng từ “cache” nhưng phục vụ những việc khác nhau

| Lớp/cơ chế | Lưu hoặc theo dõi gì? | Dấu hiệu | Tắt/điều tra |
| --- | --- | --- | --- |
| **Up-to-date checks** (incremental build) | Fingerprints của inputs và outputs của task từ build trước trong workspace. | `UP-TO-DATE` | `--rerun-tasks` hoặc `--rerun` để cưỡng bức chạy, kiểm tra declared inputs/outputs. |
| **Build Cache** | Outputs của cacheable tasks và cacheable artifact transforms, cục bộ hoặc remote, theo cache key. | `FROM-CACHE` | `--no-build-cache`; `outputs.doNotCacheIf` cho task cụ thể. |
| **Configuration Cache** | Trạng thái cấu hình, task graph và task configuration state của một invocation. | `Reusing configuration cache.` | `--no-configuration-cache`, report tương thích và `notCompatibleWithConfigurationCache`. |
| **Dependency Cache** | Module metadata, artifact downloads, dynamic/changing version resolution trong Gradle User Home. | Có thể không cần tải mạng. | `--refresh-dependencies`, `--offline`, `dependencyInsight`; TTL cho dynamic/changing. |
| **Compiler incremental state** | Phần state phục vụ biên dịch từng phần do Gradle/compiler plugins quản lý. | Chỉ compile phần cần thiết. | Phân tích JavaCompile/Kotlin compile logs và incremental compiler options; không đồng nhất với Build Cache. |
| **File-system watching/VFS** | Trạng thái file system trong bộ nhớ để Gradle giảm công snapshot. | Không có nhãn `FROM-CACHE` riêng. | Kiểm tra file watching nếu có nghi vấn file không được nhận diện; tránh nhầm với dependency cache. |
| **Gradle Daemon** | JVM process chạy Gradle, có thể giữ JIT/in-memory state. | Daemon reuse. | `./gradlew --stop` dừng daemon, **không** xóa Build Cache/dependency cache. |

**Ba kết quả không tương đương:**

- `UP-TO-DATE`: task output ở workspace vẫn được coi hợp lệ dựa trên inputs/outputs đã track; không cần tải kết quả từ Build Cache.
- `FROM-CACHE`: Gradle lấy task outputs từ Build Cache thay vì chạy task action.
- `Reusing configuration cache.`: Gradle bỏ qua lại phần cấu hình build; **không nói** task outputs đã up-to-date hay from-cache.

Một invocation có thể **reuse Configuration Cache** nhưng vẫn **execute** JavaCompile; hoặc phải chạy configuration lại nhưng vẫn nhận `FROM-CACHE` cho JavaCompile. Vì thế phải xác định đúng **lớp cache** trước khi điều tra.

### 2.1. Những tính năng mặc định

Theo tài liệu CLI Gradle hiện hành:
- Up-to-date/incremental build là cơ chế mặc định, không phải một switch tùy chọn giống Build Cache.
- `--build-cache` và `--no-build-cache` bật/tắt Build Cache cho invocation; mặc định Build Cache là **off** nếu không cấu hình `org.gradle.caching=true`.
- `--configuration-cache` và `--no-configuration-cache` bật/tắt Configuration Cache; mặc định **off** nếu không cấu hình `org.gradle.configuration-cache=true`.
- Plugin/build của tổ chức có thể đã đặt các giá trị này trong `gradle.properties`, nên đừng suy đoán “mặc định hiện hành” đồng nghĩa thiết lập trên máy bạn.

Ví dụ `gradle.properties`:

~~~properties
org.gradle.caching=true
org.gradle.configuration-cache=true
~~~

Đây là **mảnh cấu hình tùy chọn**, không bắt buộc cho lab. Các flags trên CLI có thể ghi đè để điều tra một lần.

## 3. Đọc outcome của từng task đúng cách

Giả sử `:app:compileJava` có outputs là class files.

| Outcome/hiển thị | Ý nghĩa phổ biến | Có phải cache hit? |
| --- | --- | --- |
| `> Task :app:compileJava`, không có suffix | Task action được thực thi, có thể incremental bên trong. | Không phải output cache hit. |
| `> Task :app:compileJava UP-TO-DATE` | Inputs/outputs không đổi từ lần chạy trước trong workspace. | Không phải `FROM-CACHE`. |
| `> Task :app:compileJava FROM-CACHE` | Task outputs được khôi phục từ Build Cache. | **Có**, build cache hit. |
| `> Task :app:compileJava NO-SOURCE` | Task không có input source để xử lý. | Không phải build cache hit. |
| `> Task :foo SKIPPED` | Điều kiện skip như `onlyIf`; task action không chạy. | Không phải build cache hit. |
| `> Task :foo FAILED` | Task fail. | Không phải cache success. |
| Không xuất hiện trong output | Task có thể không nằm trong graph; output CLI/quiet filtering. | Chưa đủ bằng chứng. |

Một task không khai báo outputs hoặc chỉ tạo side effects có thể **thực thi mỗi lần**. Điều đó không nhất thiết là “Gradle cache hỏng”; có thể task không đủ điều kiện up-to-date hoặc không nên cache.

### 3.1. Khi một task được execute có thể vẫn “incremental”

`JavaCompile` có thể thực thi action nhưng chỉ compile một phần classes thay đổi. “Executed” không đồng nghĩa “compile sạch mọi source” và không cho biết Build Cache sai. Muốn biết phạm vi compile, đọc `--info`/compiler logs và Java incremental compilation docs.

### 3.2. Output tồn tại nhưng task vẫn chạy

Các nguyên nhân phổ biến:
- Input property/hash khác.
- Task implementation hoặc action classpath khác.
- Output bị xóa, sửa, hoặc không được Gradle track đầy đủ.
- Task không có stable outputs, bị disable caching/up-to-date logic.
- Task không cacheable hoặc task validation báo problem.
- Input là generated file với timestamps/bytes biến động.
- Đổi Gradle/plugin/buildSrc/JDK làm cache key khác.

**Đừng coi “output file còn nằm trên disk” là bằng chứng task phải `UP-TO-DATE`**. Gradle còn kiểm tra fingerprints/implementation/outputs model.

## 4. Quy trình điều tra có kiểm soát: bắt đầu từ tầng thấp nhất

Mục tiêu là thay **một biến mỗi lần** và lưu lại lệnh/đầu ra. Mẫu cơ bản:

~~~bash
# Xác định toolchain/runtime và danh sách tasks.
./gradlew --version
./gradlew help --task compileJava

# Bắt đầu với Build Cache và Configuration Cache tắt cho invocation.
./gradlew :app:assemble --no-build-cache --no-configuration-cache --info --console=plain

# Không thay source, chạy lại để kiểm tra UP-TO-DATE.
./gradlew :app:assemble --no-build-cache --no-configuration-cache --info --console=plain
~~~

Đây là **mẫu cho project có `:app:assemble`**, không phải lab đơn project ở mục 9. Nếu build không có subproject `:app`, dùng full task path của task thật (ví dụ `:renderGreeting`).

**Bước tiếp theo**, khi incremental checks hoạt động:

~~~bash
# Bật Build Cache riêng; giữ Configuration Cache tắt.
./gradlew :app:assemble --build-cache --no-configuration-cache --info --console=plain

# Clean workspace outputs, sau đó thử phục hồi từ Build Cache.
./gradlew :app:clean :app:assemble --build-cache --no-configuration-cache --info --console=plain
~~~

`clean` xóa task build outputs theo project, **không có nghĩa** đã xóa cache entries ở Gradle User Home. Nếu một task cacheable đã được lưu và không đổi cache key, sau `clean` có thể thấy `FROM-CACHE`. Nếu task vốn không cacheable, không có kết quả đó là bình thường.

### 4.1. Chẩn đoán thứ tự ưu tiên

1. Có đúng task path và đúng Gradle Wrapper chưa?
2. Task thực sự nằm trong graph hay bị skip?
3. Nếu task chạy lại khi inputs không đổi, kiểm tra incremental up-to-date **không có Build Cache** trước.
4. Nếu up-to-date ổn, bật Build Cache và thử **clean + cache restore**.
5. Nếu miss, so sánh cache key, task/action implementation, input hash và outputs.
6. Nếu hit nhưng artifact sai, nghi **undeclared input, nondeterminism hoặc stale external state**; chứng minh bằng thay đổi input mà Gradle không nhận.
7. Nếu issue là “Gradle cấu hình lại tất cả”, kiểm tra **Configuration Cache** thay vì sửa JavaCompile output cache.
8. Nếu lỗi là dependency tải cũ, kiểm tra dependency cache và repository metadata, không xóa build cache.

### 4.2. Tránh phá bằng chứng

Không xóa `~/.gradle/caches` trước khi thu thập:
- Hai lệnh có đủ flags tương ứng.
- Gradle/JDK/plugin versions.
- Task path, outcome, thời gian.
- `--info` output hoặc Build Scan comparison.
- Hash của output nếu nghi sai.
- Input file checksums hoặc diff của commit/source.
- Build Cache key diagnostics nếu cần.

Khi xóa sạch ngay từ đầu, mất dấu cache key và fingerprint gây ra hit/miss; lần sau lỗi có thể tái hiện khó hơn.

## 5. Build Cache key gồm những gì?

Cacheable task được Gradle gán **cache key** dựa trên những thứ ảnh hưởng output:

~~~text
Task action/type implementation + classloader classpath
     + các output property names
     + input property names và values
     + input file fingerprints/normalization
     + task/plugin/build logic identity cần thiết
                    |
                    v
              Build Cache key
                    |
          +---------+---------+
          |                   |
     key đã có             key chưa có
          |                   |
      FROM-CACHE            execute
                          (có thể store)
~~~

Theo Gradle Build Cache docs:
- Task path **không phải** một input của Build Cache key. Hai tasks khác paths có thể chia sẻ outputs khi implementation, inputs và outputs contract tương đương.
- Task implementation/actions (class names/classpath) ảnh hưởng key; đổi buildSrc, plugin, Gradle version hoặc thêm `doFirst`/`doLast` có thể làm key đổi.
- Những files khai báo `@InputFiles`/`@InputFile` thường cần path normalization phù hợp để cache **relocatable** giữa workspaces.
- Output property names có trong key; đổi tên property dù output path cùng chỗ có thể gây miss.
- Untracked output-affecting input sẽ **không** tham gia key và gây nguy cơ **hit sai**.
- Input thừa/không ảnh hưởng output vẫn tham gia key và gây miss không cần thiết.

### 5.1. Debug cache keys bằng Gradle logs

~~~bash
./gradlew :app:compileJava \
  --build-cache \
  --no-configuration-cache \
  -Dorg.gradle.caching.debug=true \
  --info --console=plain
~~~

PowerShell gọn một dòng:

~~~powershell
.\gradlew.bat :app:compileJava --build-cache --no-configuration-cache -Dorg.gradle.caching.debug=true --info --console=plain
~~~

Log thường chứa cache key, fingerprints cho input properties, output names và implementation fingerprints. Bạn cần **so sánh hai invocations có kết quả khác nhau**, không chỉ nhìn thấy hai key khác rồi nói “do Gradle bug”.

### 5.2. Cách tìm khác biệt có ích

Từ key/hashes của lần A và B:

1. So sánh implementation type và action implementation classpath. Nếu khác, tìm Gradle version/plugin/buildSrc/build-logic change.
2. So sánh output property names. Có task plugin nào đổi output model không?
3. So sánh value input hash: flags, locale, target JDK, generator options, version, environment vars đã khai báo.
4. So sánh input file fingerprint, path sensitivity và file contents.
5. Nếu chưa thấy nguyên nhân, kiểm tra artifact transforms, generated upstream outputs, classpath ordering và normalization rules.
6. Khi có Build Scan/Develocity comparison, đối chiếu task fingerprint; tránh publish scan chứa secrets/tokens hoặc đường dẫn nhạy cảm lên service không được phép.

Một downstream task có thể miss vì upstream code generator phát file khác do timestamp. Tập trung vào **task đầu tiên** trong chain có output hoặc cache key bất thường, không chạy đi sửa tất cả những task bị cascade.

## 6. Những nguyên nhân cache miss phổ biến

### 6.1. Input không ổn định

Ví dụ:

~~~kotlin
tasks.jar {
    manifest {
        attributes(
            "Build-Time" to System.currentTimeMillis().toString()
        )
    }
}
~~~

Đây là **mảnh phản ví dụ**: build timestamp biến đổi mỗi invocation, làm input/manifest bytes khác, dẫn đến miss hoặc outputs không deterministic. Nếu muốn reproducible JAR, bỏ timestamp hoặc chỉ dùng metadata được quản lý như release version/commit cố định.

Tương tự:
- random UUID trong file generated.
- absolute temp path chứa số process.
- random test order/seed không được khai báo.
- host-specific username/home path.
- JDK vendor/version không giống giữa máy.
- source generator đọc file chưa khai báo hoặc HTTP response biến động.

### 6.2. Path sensitivity không phù hợp

Một task đọc file `config/greeting.txt` nhưng dùng absolute path fingerprint sẽ có cache key khác khi checkout:

~~~text
/home/dev-a/repo/config/greeting.txt
/agent/work/42/repo/config/greeting.txt
~~~

dù bytes giống nhau. Với file input tương đối project source, thường dùng:

~~~java
@InputFile
@PathSensitive(PathSensitivity.RELATIVE)
public abstract RegularFileProperty getInputFile();
~~~

Cần imports của Gradle API, và getter thuộc custom Gradle task type. **Không dùng `PathSensitivity.NONE` một cách tùy tiện** nếu output phụ thuộc tên/path: bỏ path khỏi key có thể tạo cache hit sai.

### 6.3. Java classpath và compiler khác

`JavaCompile` phụ thuộc Java source, compiler/toolchain, compile classpath, annotation processor/options và các implementation inputs khác. Thay dependency version hoặc generated classpath có thể gây miss.

Với Java build:
- Dùng Java toolchains có version rõ.
- Pin Gradle Wrapper và plugin versions.
- Kiểm soát annotation processors.
- Không nhét artifact biến động/ngẫu nhiên vào compile classpath.
- Kiểm tra dependency graph bằng `dependencies`/`dependencyInsight` thay vì đoán từ filename.
- Không “fix” miss bằng cách exclude dependency cần thiết khỏi classpath.

### 6.4. Input thừa trong task

Một task chạy tests có thể vô tình đưa toàn bộ test reports vào classpath hoặc `@InputFiles`, khiến thay đổi một file không liên quan gây rerun. Giải pháp là **thu hẹp** inputs đúng tới những files có ảnh hưởng logic, không bỏ input thật sự cần.

### 6.5. Output overlap và undeclared files

Hai tasks cùng ghi `build/generated`, trong khi chỉ một task khai báo output directory đó, có thể gây:
- Gradle phát hiện overlapping outputs và tắt một số optimizations.
- Task sau ghi đè/nhặt nhầm file task trước.
- Cache restore chép outputs lẫn nội dung khác.
- Build không tái lập giữa parallel/CI.

Dùng **output files/directories duy nhất mỗi task**, ví dụ:

~~~text
build/generated/api-contract/
build/generated/feature-flags/
build/reports/quality/
~~~

và kết nối producer–consumer qua TaskProvider output property thay vì hard-code shared path. Tốt nhất một task sở hữu một output path cụ thể.

## 7. Cache hit sai còn nguy hiểm hơn cache miss

Cache miss là vấn đề hiệu năng. **Cache hit sai là lỗi tính đúng đắn**: Gradle không chạy action hoặc lấy artifact cũ trong khi một yếu tố thực sự ảnh hưởng output đã thay đổi.

Ví dụ code generator có logic:

~~~java
String suffix = System.getenv("REPORT_SUFFIX");
String result = inputText + suffix;
~~~

nhưng task chỉ khai báo input `inputText`, không khai báo `REPORT_SUFFIX`. Khi biến môi trường đổi từ `A` sang `B`:
- Nếu output ở workspace vẫn được coi up-to-date, `UP-TO-DATE` có thể giữ output A.
- Sau clean, Build Cache key vẫn không đổi nên có thể `FROM-CACHE` output A.
- Tắt Build Cache **chưa đủ** nếu up-to-date check vẫn thiếu input.
- Cache rất có thể không bị “corrupt” ở cấp storage; task **khai báo sai hợp đồng**.

### 7.1. Sửa bằng input có tracking

Trong custom Gradle task Java:

~~~java
@Input
public abstract Property<String> getSuffix();
~~~

Trong consumer Kotlin DSL:

~~~kotlin
tasks.named<MyReportTask>("report") {
    suffix.set(
        providers.environmentVariable("REPORT_SUFFIX")
            .orElse("")
    )
}
~~~

Đây là **mảnh code** giả định `MyReportTask` đã được định nghĩa và thực sự dùng `getSuffix().get()` để tạo output. `providers.environmentVariable(...)` đưa biến môi trường thành một Provider; khi được nối vào input `@Input`, Gradle có thể fingerprint giá trị tương ứng cho task.

Chỉ thêm một biến vào environment ở CLI mà **không** khai báo nó là task input không bảo đảm up-to-date/cache key thay đổi.

### 7.2. Nondeterministic output

Một task có tất cả inputs khai báo đúng nhưng vẫn tạo bytes khác nhau cho cùng inputs do:
- nhúng thời gian hiện tại;
- duyệt `HashMap`/filesystem không ổn định;
- số random chưa seed;
- kết quả service sống;
- thứ tự concurrency không deterministic;
- JAR/ZIP timestamps/path/permissions;
- generated metadata chứa absolute working directory.

Nếu không thể làm output deterministic, task **không nên publish result vào shared Build Cache**. Tắt cache cục bộ có phạm vi hoặc thiết kế output ổn định; nếu task không thể up-to-date đúng cũng cần điều chỉnh cơ chế up-to-date riêng.

### 7.3. Xác minh đúng thay vì chỉ nhìn task outcome

Một quy trình:

1. Chạy một lần với `--no-build-cache --no-configuration-cache --rerun-tasks`.
2. Ghi SHA-256/contents của output chuẩn.
3. Thay **một input có ảnh hưởng thực** (chẳng hạn env var).
4. Chạy lại bình thường, xem Gradle có invalidate output không.
5. Clean output, bật Build Cache rồi chạy lại.
6. So sánh bytes/artifact checksums với output đúng theo input mới.
7. Nếu output sai, bổ sung input tracking hoặc tắt cache cho task khi chưa sửa được.

Chỉ dựa vào `BUILD SUCCESSFUL` không chứng minh artifact đúng: Gradle chỉ tin thông tin inputs/outputs mà plugin/task cung cấp.

## 8. Lab Java 17 hoàn chỉnh: một cacheable custom task

Bài lab này cung cấp một **tác vụ cacheable có đủ inputs/outputs** để phân biệt các outcomes. Custom task type viết bằng Java 17 trong `buildSrc`; root Gradle project đăng ký task bằng Kotlin DSL. Một chương trình Java 17 nhỏ đọc artifact để kiểm tra bytes.

### 8.1. Cấu trúc thư mục

~~~text
cache-diagnostics-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── config/greeting.txt
├── src/main/java/demo/ReadReport.java
└── buildSrc/
    ├── build.gradle.kts
    └── src/main/java/demo/build/GreetingReportTask.java
~~~

Gradle nhận diện `buildSrc` như một build riêng và đưa classes của nó lên classpath root build scripts. Không cần `include("buildSrc")` hoặc `includeBuild("buildSrc")` trong Settings cho ví dụ này.

**Điều kiện:** Gradle Wrapper đã được tạo, JDK 17 sẵn có/được provision. Custom task không cần external Maven dependencies; `gradleApi()` từ Gradle distribution cung cấp các task annotations/classes. Nếu môi trường chưa có Gradle Wrapper, tạo bằng bản Gradle đã cài trên máy hoặc dùng Gradle init/wrapper theo tài liệu chính thức trước bài lab.

### 8.2. `settings.gradle.kts`

~~~kotlin
rootProject.name = "cache-diagnostics-lab"
~~~

### 8.3. `buildSrc/build.gradle.kts`

~~~kotlin
plugins {
    `java-library`
}

dependencies {
    implementation(gradleApi())
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

`buildSrc` compile Java task type. Đây là code **build logic**: Java classes tạo ra không tự được đóng vào JAR của ứng dụng bên ngoài. `gradleApi()` cung cấp `DefaultTask`, `Property`, `@CacheableTask` và APIs liên quan.

### 8.4. `buildSrc/src/main/java/demo/build/GreetingReportTask.java`

~~~java
package demo.build;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.api.DefaultTask;
import org.gradle.api.GradleException;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.CacheableTask;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.InputFile;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.PathSensitive;
import org.gradle.api.tasks.PathSensitivity;
import org.gradle.api.tasks.TaskAction;

@CacheableTask
public abstract class GreetingReportTask extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.RELATIVE)
    public abstract RegularFileProperty getSourceFile();

    @Input
    public abstract Property<String> getTag();

    @OutputFile
    public abstract RegularFileProperty getReportFile();

    @TaskAction
    public void generate() {
        Path source = getSourceFile().get().getAsFile().toPath();
        Path target = getReportFile().get().getAsFile().toPath();

        try {
            String text = Files.readString(
                source, StandardCharsets.UTF_8
            ).strip();

            String report =
                "TAG=" + getTag().get() + "\n"
                + "TEXT=" + text + "\n";

            Files.createDirectories(target.getParent());
            Files.writeString(
                target, report, StandardCharsets.UTF_8
            );
        } catch (IOException cause) {
            throw new GradleException(
                "Cannot generate greeting report for " + getPath()
                + ". Check input file and output permissions.",
                cause
            );
        }
    }
}
~~~

**Tại sao task có thể cache an toàn trong phạm vi này?**

- `@CacheableTask` cho phép task output caching nếu toàn bộ task/model đáp ứng điều kiện Gradle.
- `@InputFile` đánh dấu **nội dung nguồn** là input.
- `@PathSensitive(RELATIVE)` không để absolute checkout path vô cớ làm cache miss giữa hai workspaces.
- `@Input` đánh dấu `tag` ảnh hưởng report bytes.
- `@OutputFile` khai báo chính xác file tạo ra, để Gradle track/store/restore.
- File output có newline cố định `\n` thay vì `System.lineSeparator()`, giảm khác biệt bytes giữa OS.
- `UTF-8` được đặt tường minh.
- Không đọc clock, random, network hoặc secrets chưa khai báo.
- Task action chỉ đọc `Property`/file paths, không gọi `getProject()`.
- `Files.createDirectories(...)` thực hiện trong execution và output path thuộc task, tránh side effect trong configuration.

**Lưu ý:** Java `String.strip()` loại whitespace ở đầu/cuối text; đây là **logic transformation của bài lab**. Nếu yêu cầu giữ nguyên whitespace, bỏ `strip()` và cập nhật expected stdout/tests tương ứng. Đổi algorithm output trong custom task implementation sẽ được Gradle fingerprint qua implementation metadata.

### 8.5. Root `build.gradle.kts`

~~~kotlin
import demo.build.GreetingReportTask

plugins {
    base
}

tasks.register<GreetingReportTask>("renderGreeting") {
    group = "verification"
    description = "Generates a reproducible greeting report"

    sourceFile.set(
        layout.projectDirectory.file("config/greeting.txt")
    )

    tag.set(
        providers.gradleProperty("reportTag")
            .orElse("LAB")
    )

    reportFile.set(
        layout.buildDirectory.file("reports/greeting.txt")
    )
}
~~~

`tag` sử dụng Provider của project property `reportTag`, nên thay `-PreportTag=...` sẽ làm declared input thay đổi và cache key khác. Output path cố định và thuộc riêng task này. Root `base` cung cấp `clean` để xóa project `build/` nhưng **không xóa Gradle User Home cache**.

### 8.6. `config/greeting.txt`

~~~text
Hello cache
~~~

File có thể kết thúc bằng newline. `strip()` xử lý để report luôn như expected.

### 8.7. Java 17 consumer `src/main/java/demo/ReadReport.java`

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ReadReport {
    private ReadReport() {
    }

    public static void main(String[] args) throws Exception {
        Path report = Path.of(
            args.length > 0
                ? args[0]
                : "build/reports/greeting.txt"
        );

        System.out.print(
            Files.readString(report, StandardCharsets.UTF_8)
        );
    }
}
~~~

Chương trình đọc **file do Gradle task sinh**. Nó không phụ thuộc trực tiếp vào Gradle APIs. Nếu task report chưa tạo file, Java sẽ ném `NoSuchFileException`; đó là expected khi thiếu artifact, không phải lý do vô hiệu hóa Build Cache.

### 8.8. Chạy bốn lượt và xem outcome

Từ root trên Linux/macOS:

~~~bash
# 1. Tạo output từ đầu mà không dùng hai cache của Gradle.
./gradlew clean renderGreeting \
  --no-build-cache --no-configuration-cache \
  --console=plain

# 2. Không thay đổi gì: up-to-date check thường bỏ qua action.
./gradlew renderGreeting \
  --no-build-cache --no-configuration-cache \
  --console=plain

# 3. Clean output rồi bật Build Cache để tạo/cache artifact.
./gradlew clean renderGreeting \
  --build-cache --no-configuration-cache \
  --console=plain

# 4. Clean output lần nữa, thử lấy artifact từ Build Cache.
./gradlew clean renderGreeting \
  --build-cache --no-configuration-cache \
  --console=plain
~~~

Dấu `\` là cách nối lệnh trong shell Linux/macOS, **không dùng y nguyên trong PowerShell**. Trên Windows PowerShell dùng:

~~~powershell
.\gradlew.bat clean renderGreeting --no-build-cache --no-configuration-cache --console=plain
.\gradlew.bat renderGreeting --no-build-cache --no-configuration-cache --console=plain
.\gradlew.bat clean renderGreeting --build-cache --no-configuration-cache --console=plain
.\gradlew.bat clean renderGreeting --build-cache --no-configuration-cache --console=plain
~~~

**Kỳ vọng thông thường, giả định fresh local cache và inputs không đổi:**

| Lượt | Task `:renderGreeting` | Lý do |
| --- | --- | --- |
| 1 | Được thực thi, không suffix `FROM-CACHE`. | Output chưa có; Build Cache tắt. |
| 2 | `UP-TO-DATE`. | Same workspace, same inputs/outputs. |
| 3 | Thực thi và có thể store vào Build Cache. | `clean` xóa output, lượt 1 không lưu cache. |
| 4 | `FROM-CACHE`. | Output đã store ở lượt 3, key không đổi. |

Đây là **mô hình chẩn đoán**, không một transcript bất biến. Nếu máy đã có cache entry cho cùng task implementation/inputs từ một lần chạy trước, **lượt 3** có thể `FROM-CACHE` ngay. BuildSrc compilation/tasks của Gradle có outcomes riêng, không phải task `renderGreeting` của bảng.

**Tránh vô tình làm kết quả khác:** đừng sửa `buildSrc`/Gradle Wrapper/build.gradle.kts giữa các lượt, thay `reportTag`, đổi Java compiler, chạy `--rerun-tasks` hoặc thay file greeting khi muốn test identical inputs.

### 8.9. Kiểm tra chính xác bytes output bằng `javac`/`java`

Linux/macOS:

~~~bash
mkdir -p build/manual-classes
javac -encoding UTF-8 -d build/manual-classes \
  src/main/java/demo/ReadReport.java

java -cp build/manual-classes \
  demo.ReadReport build/reports/greeting.txt
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/manual-classes | Out-Null
javac -encoding UTF-8 -d build/manual-classes src/main/java/demo/ReadReport.java
java -cp build/manual-classes demo.ReadReport build/reports/greeting.txt
~~~

**Stdout của Java main chính xác hai dòng:**

~~~text
TAG=LAB
TEXT=Hello cache
~~~

Chương trình in file có newline cuối; không in log Gradle. Cả Java source/task code dùng APIs có trên Java 17, nhưng **chỉ có thể xác nhận build logic task hoạt động thật** bằng Gradle Wrapper trong môi trường đủ JDK, chứ `javac` của ReadReport chỉ kiểm chứng file reader.

### 8.10. Thay một input và chứng minh invalidation

Linux/macOS, sửa `config/greeting.txt` thành:

~~~text
Hello changed
~~~

Sau đó:

~~~bash
./gradlew renderGreeting --build-cache --no-configuration-cache
java -cp build/manual-classes demo.ReadReport build/reports/greeting.txt
~~~

Expected Java stdout:

~~~text
TAG=LAB
TEXT=Hello changed
~~~

Vì input file bytes khác, `:renderGreeting` không được tái sử dụng output `Hello cache`. Trên một cache đã từng chứa entry cho new inputs, task có thể `FROM-CACHE` output mới; điều quan trọng là **artifact khớp input hiện tại**, không phải bắt buộc nhìn thấy `EXECUTED`.

Có thể thay value input bằng `-P`:

~~~bash
./gradlew renderGreeting -PreportTag=CI \
  --build-cache --no-configuration-cache
~~~

Khi file đang có `Hello changed`, output trở thành:

~~~text
TAG=CI
TEXT=Hello changed
~~~

`tag` là `@Input` nên Gradle biết phải invalidate/match một cache key tương ứng. Kết quả có thể là execute hoặc hit một entry đã được tạo trước với đúng tag đó.

## 9. Chẩn đoán cache miss ở custom task

Lab có `@CacheableTask` nhưng một thay đổi tưởng vô hại vẫn có thể gây miss:
- Thay implementation ở `buildSrc/GreetingReportTask.java` làm action classpath/fingerprint đổi.
- Thêm một `doLast { ... }` vào cacheable task, khiến action implementation thay đổi.
- Đổi `tag`/`reportTag`.
- Đổi `config/greeting.txt` bytes.
- Đổi tên output property `getReportFile` hoặc khai báo thêm input.
- Di chuyển source input sang path khác khi path normalization/relative filename khác.
- Chuyển compiler/Gradle version hoặc library plugin implementation.

### Xem key và fingerprints của chính task

~~~bash
./gradlew renderGreeting --build-cache \
  --no-configuration-cache \
  -Dorg.gradle.caching.debug=true \
  --info --console=plain
~~~

Chạy lại với `-PreportTag=CI` và so input values. Không cần xóa cache để nhìn keys. Kết quả log có thể chứa đường dẫn/cấu hình: xem lại trước khi đưa vào ticket công khai.

### Cache miss do root task không đủ điều kiện cache

`@CacheableTask` chỉ là opt-in. Gradle vẫn có thể tắt caching nếu:
- Task output không khai báo đúng.
- Gradle không fingerprint được task implementation.
- Có overlapping outputs.
- Task type/plugin khai báo lý do không cache.
- `outputs.doNotCacheIf` predicate trả `true`.
- Caching bị tắt toàn build bằng `--no-build-cache`.
- Validation problem ảnh hưởng task optimizations.

Nếu một custom task **không** có `@CacheableTask`, nó không tự được cache chỉ vì có `@OutputFile`. `outputs.cacheIf(...)` có thể opt-in theo điều kiện, nhưng chỉ làm vậy khi chắc chắn task deterministic/relocatable và tests cho reuse đúng.

## 10. Cách tắt Build Cache đúng phạm vi

### 10.1. Cho một lần chạy: `--no-build-cache`

~~~bash
./gradlew :app:compileJava --no-build-cache
~~~

Phù hợp khi muốn so sánh compilation không phục hồi outputs từ cache. **Vẫn có thể `UP-TO-DATE`** nếu output hiện tại ở workspace hợp lệ, vì tùy chọn chỉ tắt Build Cache chứ không tắt up-to-date checking.

Muốn ép chạy thực sự:

~~~bash
./gradlew :app:compileJava \
  --no-build-cache --rerun-tasks
~~~

`--rerun-tasks` bỏ up-to-date checks và Build Cache reuse cho tasks trong invocation; nó có thể buộc các task dependencies chạy lại và tốn thời gian. Nó **không tự tắt Configuration Cache**: thêm `--no-configuration-cache` nếu cũng cần kiểm tra configuration path.

### 10.2. Ép **một task cụ thể** chạy lại bằng `--rerun`

Gradle hiện hành có built-in task option `--rerun`:

~~~bash
./gradlew :app:test --rerun
~~~

Dùng khi muốn re-execute một task cụ thể mà không ép mọi task prerequisites giống `--rerun-tasks`. Chỉ dùng với task/plugin/Gradle version hỗ trợ built-in option đó; kiểm tra `./gradlew help --task test` nếu không chắc.

Đây là công cụ **diagnostic**, không nên làm defaults CI trên mọi task nếu không có yêu cầu thực sự.

### 10.3. Tắt task output caching có điều kiện: `doNotCacheIf`

Trong **lab mục 8**, có thể bổ sung vào root `build.gradle.kts`:

~~~kotlin
tasks.named<GreetingReportTask>("renderGreeting") {
    outputs.doNotCacheIf(
        "Temporary investigation of external state"
    ) {
        true
    }
}
~~~

Điều này chỉ **ngăn task output caching cho task được chọn** khi predicate là `true`. Nó không tắt Build Cache cho toàn build, không xóa entry cũ, không có tác dụng lên dependency cache và không vô hiệu hóa Configuration Cache.

**Quan trọng:** `doNotCacheIf` chỉ ảnh hưởng **Build Cache**, nên task vẫn có thể `UP-TO-DATE` và không chạy actions. Nếu input thực sự không được track và artifact sai, chỉ thêm doNotCacheIf **không đủ**.

Khi điều tra task phụ thuộc external state chưa được model hóa, có thể bổ sung:

~~~kotlin
tasks.named<GreetingReportTask>("renderGreeting") {
    outputs.doNotCacheIf("External state is not yet modeled") {
        true
    }

    outputs.upToDateWhen {
        false
    }
}
~~~

Đây là **cấu hình tạm thời**, không phải chính sách cache khuyến nghị cho task deterministic trong lab. `upToDateWhen { false }` ép up-to-date check trả false; kết hợp doNotCacheIf thì task action phải chạy khi task được chọn, trừ các điều kiện skip khác. Cách sửa bền vững là **khai báo đầy đủ input rồi bỏ hai workarounds**.

### 10.4. `cacheIf` không phải phép thần

`outputs.cacheIf("reason") { predicate }` có thể cho phép cache một task type chưa `@CacheableTask` nếu predicate đúng. Nhưng:
- Không dùng cho task download/deploy/email chỉ vì nó “chạy lâu”.
- Phải kiểm tra input/output contract, determinism, relocatability và side effects.
- Một predicate trả true không biến output của network service thành deterministic.
- Gradle có thể vẫn từ chối caching do constraints/validation khác.

Với custom task tự viết, ưu tiên thiết kế rõ `@CacheableTask` khi cache an toàn, hoặc `@DisableCachingByDefault(because = "...")` để document lý do không cache theo default. Annotation `@DisableCachingByDefault` không phải lệnh xóa cache; runtime build logic có thể override trong những điều kiện cụ thể.

## 11. Trường hợp **nên tắt cache** thay vì cố đạt 100% hit

| Tình huống | Vì sao task không nên output-cache? | Giải pháp |
| --- | --- | --- |
| Deploy production, gửi email, publish artifact lên server | Side effect bên ngoài không nằm trong file outputs. | Không cache action publish; task cần chạy theo explicit invocation. |
| Database migration, cập nhật HTTP service | Trạng thái bên ngoài thay đổi ngoài Gradle. | Kiểm soát idempotence/transaction; không dùng cache hit như bằng chứng server đã cập nhật. |
| Tests gọi live API với dữ liệu luôn đổi | Output phụ thuộc thời điểm/network không được mô hình hóa. | Separate integration tests; chạy có chủ đích; đừng lưu shared cache results như deterministic. |
| Generator dùng timestamp/random | Same inputs có thể tạo bytes khác. | Loại nondeterminism hoặc disable cache/up-to-date khi không thể. |
| Tác vụ copy/sync file rất nhanh | Tải/lưu cache có thể tốn hơn chạy. | Không opt-in caching chỉ vì có outputs. |
| Tác vụ có secrets chưa thể fingerprint an toàn | Cache key/result có thể lộ dữ liệu hoặc cross-user unsafe. | Thiết kế secret handling/partition cache, không push remote output nhạy cảm. |
| Plugin bên thứ ba khai báo thiếu inputs/outputs | Cache hit sai. | Tạm doNotCacheIf có scope, báo issue upstream, thêm contract tests. |
| Task hiện không tương thích Configuration Cache | Task state không serialize/reuse đúng. | `notCompatibleWithConfigurationCache(reason)` tạm thời; sửa task API sau. |

Cần tách rõ **Build Cache** khỏi **up-to-date checks**: một task publish side effect dù có file log output vẫn không nên bị skip chỉ vì file log không đổi. Để thiết kế task này, thường không gắn `@CacheableTask`, không dùng file output giả như dấu đã publish, và cần semantics luôn thực thi khi người dùng gọi (đúng task type và up-to-date policy).

**Không** dùng `-x test` hoặc `onlyIf { false }` để giải quyết cache miss: đó là **bỏ task**, khác với chạy task nhưng không reuse outputs. Trong CI cần bảo đảm tests được chạy, việc skip vô điều kiện có thể tạo false-positive.

## 12. Tắt Configuration Cache và đánh dấu task không tương thích

### 12.1. Một invocation

~~~bash
./gradlew :app:build --no-configuration-cache
~~~

Lệnh ép Gradle cấu hình lại build, **không** tắt Build Cache; `:app:compileJava` vẫn có thể `FROM-CACHE` khi `--build-cache`/`org.gradle.caching=true` đang bật.

Có thể tách riêng:

~~~bash
./gradlew :app:build \
  --no-configuration-cache --build-cache
~~~

cho phép reuse task outputs nhưng không reuse configuration state.

Ngược lại:

~~~bash
./gradlew :app:build \
  --configuration-cache --no-build-cache
~~~

có thể reuse configuration, còn task output Build Cache tắt. **Hai lớp cache độc lập.**

### 12.2. Chẩn đoán Configuration Cache miss

~~~bash
./gradlew :app:build --configuration-cache --info
./gradlew :app:build --configuration-cache --info
~~~

Nếu lần hai không thấy `Reusing configuration cache.`, đọc thông điệp `configuration cache cannot be reused because ...` và HTML report được Gradle link. Những nguyên nhân có thể:
- Build script/settings/init script/plugin classpath đổi.
- System property/environment variable bị đọc trong configuration và thay giá trị mỗi lần.
- CLI task selection khác.
- Project dependency graph hoặc build logic thay.
- Task chứa object không serializable hoặc đọc `Project` trong `@TaskAction`.
- Build logic cố ý phụ thuộc timestamp/dynamic external state trong configuration.
- Cache entry bị vô hiệu hóa khi configuration inputs thay đổi chính đáng.

Đừng thấy “configuration cache miss” rồi vội tắt `--build-cache`, vì nó không liên quan trực tiếp.

### 12.3. Report và cảnh báo tạm

~~~bash
./gradlew :app:build \
  --configuration-cache \
  --configuration-cache-problems=warn
~~~

Warning mode chỉ nên dùng **trong lúc điều tra/chuyển đổi**, không phải cách permanent ignore. Gradle có thể lưu entry dù có problems, dẫn đến reuse trạng thái không đầy đủ và build sai khó phát hiện. Với CI validation, giữ default `problems=fail`.

### 12.4. Task-level opt-out của Configuration Cache

Trong project có task legacy không tương thích:

~~~kotlin
tasks.named("legacyGenerate") {
    notCompatibleWithConfigurationCache(
        "Reads Project model during task execution"
    )
}
~~~

Đây là **mảnh build script minh họa**, giả định task `legacyGenerate` tồn tại. Theo Gradle docs, khi task incompatible được chọn và chạy, những problems từ task đó không nhất thiết làm toàn build fail; **Configuration Cache entry của invocation bị discard** để không reuse state nguy hiểm. Các tasks khác vẫn có thể chạy, nhưng không thể giữ/reuse một entry cho graph có task incompatible đó.

**Đừng nhầm** `notCompatibleWithConfigurationCache` với `outputs.doNotCacheIf`:
- Cái đầu liên quan **configuration state serialization/reuse**.
- Cái sau liên quan **caching task outputs**.
- Nếu task lỗi vì untracked input ảnh hưởng output, `notCompatibleWithConfigurationCache` **không** sửa Build Cache correctness.

### 12.5. Cần xác minh hai lần

Một task có thể pass khi Configuration Cache mới **store**, nhưng fail khi **reuse**. Vì thế functional test phải chạy cùng task set **hai lần** với `--configuration-cache` và kiểm tra lần hai reuse được, kết quả đúng; nếu cần đảm bảo task action thật sự được kiểm tra, chạy `--rerun-tasks` ở lượt đầu theo hướng dẫn của Gradle.

## 13. Dependency Cache: khi artifact/version cũ không cập nhật

Gradle dependency cache nằm phần lớn trong Gradle User Home, ví dụ:

~~~text
~/.gradle/caches/modules-2
~~~

Nó lưu download artifacts/module metadata và một số kết quả dependency resolution. Nó **khác** task output Build Cache: xóa `build/` không tự xóa dependency cache.

### 13.1. Trường hợp điển hình

- Maven SNAPSHOT hoặc dependency được đánh dấu `changing` đổi bytes mà giữ version.
- Dynamic version `1.+` có bản mới nhưng cached resolution chưa hết TTL.
- Repo metadata/artifact không nhất quán giữa mirror/repositories.
- Artifact coordinate đã được publish lại trái best practices.
- `--offline` đang dùng module có trong cache, không hỏi server.

Theo tài liệu Gradle hiện hành, dynamic/changing modules mặc định có cache TTL **24 giờ**. Đây không phải quy tắc mọi fixed-version release artifacts phải tải lại sau 24 giờ.

### 13.2. `--refresh-dependencies`

~~~bash
./gradlew :app:dependencies \
  --configuration runtimeClasspath \
  --refresh-dependencies
~~~

Tùy target:
- Gradle revalidate dependency resolution metadata, dynamic/changing versions và artifact freshness theo configured repositories.
- Nó có thể sử dụng HTTP HEAD/metadata/checksums để **không tải lại bytes khi artifact giống nhau**.
- Nó **không** dọn Build Cache hoặc Configuration Cache.
- Nó **không** thay thế dependency locking/verification.
- Nó không nên được bật mọi CI build vì network overhead và che upstream publishing issues.

Khi cần giảm TTL cho một configuration, ví dụ:

~~~kotlin
configurations.configureEach {
    resolutionStrategy.cacheDynamicVersionsFor(
        10, "minutes"
    )
    resolutionStrategy.cacheChangingModulesFor(
        4, "hours"
    )
}
~~~

Đây là **mảnh cấu hình optional**. TTL ngắn làm tăng yêu cầu mạng, không bảo đảm repository publish đúng hoặc artifact integrity an toàn. Với builds reproducible, ưu tiên version cố định, dependency locking và verification.

### 13.3. `--offline` không phải refresh

~~~bash
./gradlew :app:build --offline
~~~

Khi offline, Gradle chỉ dùng dependencies có trong cache và fail nếu thiếu artifact/metadata cần. Nó **không** kiểm tra remote có version mới. Nếu ai đó nói “tôi đã thêm `--offline` nhưng dependency vẫn cũ”, đó là expected.

### 13.4. Diagnostic commands

~~~bash
./gradlew :app:dependencies \
  --configuration runtimeClasspath

./gradlew :app:dependencyInsight \
  --configuration runtimeClasspath \
  --dependency some-library

./gradlew :app:build --refresh-dependencies --info
~~~

Nếu CI thiếu dependency version, đọc `dependencyInsight` và repository metadata trước khi đụng `~/.gradle/caches/modules-2`. Không xóa global dependency cache vì một task JavaCompile cache miss nếu không có bằng chứng liên quan.

## 14. Remote Build Cache: miss do không có entry hay do cache không sử dụng được?

Local Build Cache và remote Build Cache cùng dựa vào cache keys, nhưng remote thêm yếu tố:
- Network permissions/credentials.
- Server reachability/timeout.
- Cache read/write policy (CI push, dev pull).
- Incompatible cache namespace/tenant.
- Retention/pruning trên server.
- Artifact size/bandwidth và cache hit hiệu quả kinh tế.
- Remote cache trust/security, integrity và provenance.

Một remote miss có thể chỉ do **không ai push key đó**, không phải bug của Gradle. Trước khi yêu cầu “clear remote cache”:
1. Có Gradle Build Cache bật không?
2. Local/remote cache enabled đúng build invocation không?
3. Consumer có quyền read, CI có quyền push không?
4. Producer và consumer cache key có giống không?
5. Có thay buildSrc/plugin/JDK/source normalization không?
6. Entry có bị evict theo retention không?
7. Build Cache error logs có network/auth/timeout không?
8. Artifact chứa dữ liệu nhạy cảm hoặc output không deterministic không?

### 14.1. CI push, developer pull

Một policy thường gặp:
- CI trên branch đáng tin/đã kiểm thử có thể push remote cache.
- Developer builds thường **pull**, không push shared cache.
- Pull request từ source không tin cậy nên hạn chế write remote cache để tránh poisoning.
- Remote cache chứa task outputs: cần bảo vệ quyền truy cập và không đưa secrets vào artifacts.

Ví dụ conceptual Settings Kotlin DSL:

~~~kotlin
import org.gradle.caching.http.HttpBuildCache

buildCache {
    local {
        isEnabled = true
    }

    remote<HttpBuildCache> {
        url = uri(
            providers.gradleProperty("remoteCacheUrl").get()
        )
        isPush = providers.environmentVariable("CI_TRUSTED")
            .map { it == "true" }
            .orElse(false)
            .get()
    }
}
~~~

**Đây là mảnh cấu hình chỉ dùng khi đã cung cấp remoteCacheUrl và server đúng.** `remoteCacheUrl`/`CI_TRUSTED` là conventions minh họa; chúng không tự tồn tại. Credentials/certificates/HTTPS/trust cần cấu hình theo Gradle HTTP Build Cache docs và chính sách tổ chức. Đừng dùng `http://` cho shared cache không được bảo vệ, đừng hard-code password/token. `isPush=false` chỉ tắt **ghi remote**, vẫn có thể đọc remote/local khi enabled.

### 14.2. Khi nghi cache poisoning

Nếu output `FROM-CACHE` sai dù cache key giống nhau:
1. Dừng việc **push** kết quả nghi sai lên remote ngay.
2. Thu thập cache key và producer build/Gradle/JDK/plugin IDs (không công bố secrets).
3. Chạy control với `--no-build-cache --rerun-tasks` từ source/inputs giống nhau.
4. So sánh hashes/contents của output.
5. Tìm input bỏ sót, nondeterminism và task implementation differences trước.
6. Nếu bằng chứng chỉ ra server-side corruption, liên hệ người quản trị cache để quarantine/invalidate **entry hoặc namespace có liên quan**, không phá mọi cache của cả tổ chức.
7. Sau sửa, thêm cache correctness tests, restrict remote write permissions và kiểm thử cross-machine.

**Không** coi remote cache là storage tin cậy cho secret files; data governance và access control quan trọng không kém hiệu năng.

## 15. Những trường hợp có vẻ “cache sai” nhưng thực ra không phải lỗi

| Quan sát | Giải thích có thể đúng |
| --- | --- |
| Chạy `./gradlew build` lần hai và task `UP-TO-DATE` | Up-to-date checks hoạt động, không nhất thiết có Build Cache. |
| `./gradlew clean build` vẫn có `FROM-CACHE` | Clean xóa workspace outputs, cache entries còn. |
| `--no-build-cache` nhưng task `UP-TO-DATE` | Tắt Build Cache không tắt incremental checks. |
| `--no-configuration-cache` nhưng `FROM-CACHE` | Hai caches độc lập. |
| `--configuration-cache` thành công, lần sau chạy lại configuration | Có configuration input đổi hoặc incompatibility; đọc reason. |
| `--rerun-tasks` làm build lâu hơn | Cưỡng bức actions chạy, bỏ optimizations theo ý định. |
| Task `Copy` luôn execute/không `FROM-CACHE` | Task có thể không có caching value, và built-in Copy không được cache mặc định. |
| `test` không chạy ở project thiếu source/tests | `NO-SOURCE` là expected. |
| `test` không chạy do `onlyIf` | `SKIPPED` khác `UP-TO-DATE`. |
| `dependencyInsight` cho fixed version không đổi | Dependency graph/version lock chưa thay, không phải stale task cache. |
| `--offline` khiến module cũ tiếp tục được dùng | Offline chỉ dùng cache local. |
| Task output khác dù cache key giống | Có thể undeclared input hoặc nondeterminism — **lỗi correctness nghiêm trọng**. |
| Chuyển checkout path gây miss | Absolute path sensitivity hoặc build logic/env input thay. |
| Plugin nâng version làm nhiều miss | Implementation/classloader fingerprint khác là lý do hợp lệ. |

## 16. Vì sao không nên xóa cache directory bừa bãi?

Các thư mục thông thường:

~~~text
<project>/.gradle/
    configuration-cache/
    các state nội bộ theo Gradle version

<project>/build/
    classes/
    reports/
    generated/
    các outputs do tasks tạo

<Gradle User Home>/caches/
    modules-2/  (dependencies/artifacts)
    build-cache-*/ (local task outputs theo cấu hình)
    metadata và caches nội bộ khác
~~~

**Xóa từng thư mục có tác động khác nhau:**
- `./gradlew clean`: xóa build output của project có task clean, không xóa Gradle User Home dependencies/build cache.
- Xóa `.gradle/configuration-cache` (chỉ khi cần): làm mất persisted configuration state cho build đó.
- Xóa một local task-output Build Cache entry: làm mất khả năng `FROM-CACHE` từ entry đó, không chữa undeclared input.
- Xóa `modules-2`: Gradle phải re-resolve/download nhiều dependencies, có thể làm offline builds fail.
- `./gradlew --stop`: dừng daemon, không xóa cache.
- `--refresh-dependencies`: revalidate dependency metadata/artifacts; không đồng nghĩa “force re-download toàn bộ”.
- `--rerun-tasks`: buộc tasks thực thi, không xóa cache directories.

Nếu thật sự cần xóa một cache:
1. Xác định layer và directory chính xác.
2. Không chạy Gradle song song đang ghi thư mục ấy.
3. Có backup/provenance và ghi lại error/log trước.
4. Dùng file deletion trong đúng workspace/Gradle User Home mà bạn kiểm soát.
5. Xóa **nhỏ nhất có thể**, không xóa global caches được chia sẻ bởi CI jobs khác.
6. Thử lại với flags cố định và test output correctness.
7. Nếu lỗi tái phát, sửa task inputs/outputs/configuration thay vì lặp lại thao tác delete.

Đối với Configuration Cache hiện hành, Gradle docs mô tả invalidation thủ công bằng cách xóa `.gradle/configuration-cache` trong root build khi thật sự có input chưa được track và entry không được invalidate tự động. **Đừng** dùng giải pháp này để che một plugin cần được sửa tương thích Configuration Cache.

## 17. CI: vừa tận dụng cache vừa kiểm thử đúng

Một chiến lược thực tế:
- Development loop: Build Cache bật, Configuration Cache bật khi build logic đã tương thích; để Gradle dùng optimizations.
- CI build verification: kiểm tra source/test outputs, không xóa caches tùy tiện.
- Nightly hoặc regression: định kỳ chạy một build **không dùng Build Cache** và cưỡng bức các task quan trọng, so sánh artifacts.
- Remote cache: chỉ trusted CI push, developer/PR pull; kiểm soát write permissions và retention.
- Integration tests với external services: tách task/metadata, tránh cache hoặc luôn revalidate theo policy.
- Build publish/deploy: không coi `FROM-CACHE` của compile/test tương đương server deployment đã xảy ra.
- Upgrade Gradle/plugin/JDK: dự đoán miss hợp lệ do implementation fingerprints, đo lại hit rate sau warmup.

### Một checklist điều tra nhanh trong CI

~~~bash
# Xem đúng toolchain/build.
./gradlew --version

# 1. Control: không cache outputs/configuration và ép task actions.
./gradlew :app:build \
  --no-build-cache --no-configuration-cache \
  --rerun-tasks --info --console=plain

# 2. Warm cache: bật Build Cache, giữ configuration độc lập.
./gradlew :app:build \
  --build-cache --no-configuration-cache \
  --info --console=plain

# 3. Re-test outputs reuse sau khi clean.
./gradlew :app:clean :app:build \
  --build-cache --no-configuration-cache \
  --info --console=plain

# 4. Test config-cache store rồi reuse.
./gradlew :app:build --configuration-cache
./gradlew :app:build --configuration-cache
~~~

Đây là **playbook cho project :app có build/clean tasks**. Chỉ chạy khi phù hợp phạm vi CI (có thể tốn nhiều phút hoặc giờ tùy dự án); không phải bước tự động cho mọi developer build. Nếu có external side effects, tránh rerun task publish/deploy trong cùng pipeline không kiểm soát.

**Thứ tự quan trọng:** không dùng `clean` mỗi lần khi muốn đo `UP-TO-DATE`. Dùng clean có chủ đích để đo **Build Cache restoration**.

## 18. Kiểm thử cache correctness bằng Gradle TestKit

Khi bạn sở hữu custom plugin/task, bổ sung functional tests thay vì chỉ nhìn logs một lần.

Các ca test cần có:
1. Chạy task lần một, kiểm tra report bytes.
2. Chạy lại không đổi inputs: `TaskOutcome.UP_TO_DATE` khi task có outputs phù hợp.
3. Clean và bật Build Cache: `TaskOutcome.FROM_CACHE` khi đã warm cache.
4. Thay `@Input` value: output đổi đúng, không reuse stale result.
5. Thay `@InputFile` bytes: output đổi.
6. Chạy trong **workspace khác** nhưng cùng relative inputs, kiểm tra relocatable cache key và bytes.
7. Thêm env var **đã khai báo input**: thay env -> invalidate.
8. Giả lập env không khai báo: test phải phát hiện incorrect reuse, sau đó sửa code.
9. Test Configuration Cache hai lần: đầu store, sau reuse.
10. Test Gradle/JDK/plugin version matrix được công bố; cache correctness không đồng nghĩa chỉ chạy trên một máy.

Một Java TestKit fixture có thể kiểm tra outcomes:

~~~java
BuildResult result = GradleRunner.create()
    .withProjectDir(projectDir.toFile())
    .withArguments(
        "renderGreeting",
        "--build-cache",
        "--no-configuration-cache"
    )
    .build();

TaskOutcome outcome = result.task(":renderGreeting")
    .getOutcome();
~~~

Đây là **mảnh Java**, cần imports `GradleRunner`, `BuildResult`, `TaskOutcome`, fixture files và JUnit assertions; không phải class test đầy đủ. Với task outcome, có thể assert `UP_TO_DATE`/`FROM_CACHE` có điều kiện khi setup đã tạo cache entry như kỳ vọng, không ép task luôn FROM_CACHE ở lần đầu.

### Configuration Cache test

~~~java
GradleRunner.create()
    .withProjectDir(projectDir.toFile())
    .withArguments("renderGreeting", "--configuration-cache")
    .build();

BuildResult second = GradleRunner.create()
    .withProjectDir(projectDir.toFile())
    .withArguments("renderGreeting", "--configuration-cache")
    .build();

assertTrue(
    second.getOutput().contains("Reusing configuration cache.")
);
~~~

Đây cũng là **mảnh JUnit TestKit**, giả định `assertTrue` đã import và test fixture ổn định. Chỉ “first run BUILD SUCCESSFUL” chưa chứng minh reusable configuration cache. Trong một số trường hợp cần chạy lần đầu với `--rerun-tasks` để task actions thật sự thực thi và lộ configuration-cache violations.

## 19. Bảng quyết định: tắt gì trước?

| Hiện tượng | Kiểm tra ưu tiên | Tạm tắt đúng scope | Sửa bền vững |
| --- | --- | --- | --- |
| Task output `FROM-CACHE` sai | Hash artifact, declared inputs/outputs, task implementation. | `--no-build-cache` và `--rerun-tasks` cho diagnostic. | Khai báo input bị bỏ sót, deterministic output, tests. |
| Task luôn miss dù cùng source | `org.gradle.caching.debug`, fingerprints, paths. | Không cần tắt; so sánh keys. | Loại volatile inputs, đúng normalization. |
| Task `UP-TO-DATE` nhưng output sai | Inputs missing, output ownership, external state. | `--rerun`/`--rerun-tasks`; task `upToDateWhen { false }` tạm. | Input/output tracking đúng. |
| Task vốn không nên cache (deploy) | Side effects và task type. | `outputs.doNotCacheIf` khi cần. | Không opt-in cache, semantics always-execute/idempotent. |
| Config phase bị reuse sai | Config inputs chưa được track, serialized state. | `--no-configuration-cache`. | Provider APIs, fix CC incompatibility. |
| Một task legacy CC-incompatible | HTML config-cache report. | `notCompatibleWithConfigurationCache(reason)` cho task. | Sửa task để serialize/reuse an toàn. |
| Dependencies SNAPSHOT/dynamic cũ | `dependencies`/`dependencyInsight` và TTL/repository. | `--refresh-dependencies` một invocation. | Dependency locking/verification, tránh mutable releases. |
| Remote cache miss trên CI | Key diff, push/read permissions, retention. | Local-only diagnostic hoặc no remote push. | Cấu hình cache server/policy, stable inputs. |
| Cross-machine misses | Absolute paths, toolchain/platform, file permissions. | No-cache comparison. | Relative path sensitivity, reproducible outputs. |
| Nghi corrupted local configuration entry | Configuration report/integrity check. | Tắt CC cho invocation, chỉ xóa entry liên quan nếu cần. | Sửa serialization/untracked input. |

**Nguyên tắc chung:** tắt cache là **thí nghiệm cô lập vấn đề hoặc chính sách cho task không deterministic**, không thay thế việc làm input/output contract đúng.

## 20. Troubleshooting ngắn

| Dấu hiệu | Nguyên nhân thường gặp | Việc làm tiếp theo |
| --- | --- | --- |
| `--no-build-cache` mà vẫn `UP-TO-DATE` | Up-to-date checks vẫn bật. | Dùng `--rerun-tasks` nếu muốn action chạy. |
| `clean` nhưng `FROM-CACHE` | Build Cache có entry. | Expected; muốn kiểm tra execute dùng `--no-build-cache`. |
| `--configuration-cache` nhưng compile vẫn chạy | Config Cache không cache outputs. | Xem `:compileJava` inputs/Build Cache riêng. |
| Config Cache không reuse | Configuration inputs thay, task incompatible. | Đọc reason/HTML report; không xóa ngay. |
| Copy task không FROM-CACHE | Không phải mọi tasks mặc định cacheable. | Không force cache nếu không lợi ích/không deterministic. |
| Một generated file chứa timestamp | Input/output không repeatable. | Bỏ timestamp hoặc disable cache/up-to-date đúng scope. |
| BuildSrc đổi làm nhiều cache miss | Task/action implementation classpath thay. | Expected; đo lại sau warmup. |
| Đổi workspace làm misses | Absolute path sensitivity. | `@PathSensitive(RELATIVE)` khi semantics cho phép. |
| `FROM-CACHE` có report cũ | Missing declared input, shared output collision, bad cache entry. | No-cache control, compare artifacts, sửa task model. |
| `--refresh-dependencies` không tải JAR lại | Gradle revalidate, artifact unchanged. | Expected; kiểm tra repo metadata/checksums. |
| `--offline` dùng bản cũ | Cache dependency only. | Bỏ offline, refresh nếu cần. |
| Tắt Build Cache mà kết quả vẫn sai | Up-to-date bug hoặc action logic bug. | Rerun action với CC off rồi inspect. |
| TestKit pass lần đầu, CC lần hai fail | Cache entry serialize/reuse incompatible. | Two-run CC tests, sửa task state. |
| Remote cache phục hồi artifact sai | Cache producer input contract/nondeterminism/poisoning. | Quarantine key/push, so sánh trusted no-cache. |
| Xóa tất cả caches “sửa” tạm | Che triệu chứng, mất evidence. | Thu key/input diffs, tạo regression test. |
| `--stop` không sửa cache miss | Daemon không phải Build Cache. | Xác định đúng cache layer. |

## 21. Checklist review cache của một custom Gradle task

- [ ] Task có output thật và khai báo bằng `@OutputFile`/`@OutputDirectory` phù hợp.
- [ ] Mọi yếu tố ảnh hưởng output được khai báo `@Input`/`@InputFile(s)`/`@Classpath`/`@Nested` theo ngữ nghĩa.
- [ ] Không sử dụng `@Internal` để che input thật.
- [ ] Files có `@PathSensitive` phù hợp, không làm mất path semantics quan trọng.
- [ ] Có thể chạy hai lần cùng inputs và tạo output bytes giống nhau.
- [ ] Không nhúng clock/random/host-specific paths vào output mà không kiểm soát.
- [ ] Không có shared output paths giữa tasks.
- [ ] Build task logic không thay đổi vô cớ giữa máy/CI agents.
- [ ] Chỉ dùng `@CacheableTask` nếu outputs an toàn để store/restore.
- [ ] Tạo cache entry rồi thử restore sau clean.
- [ ] So sánh sha256/artifact contents giữa cache-hit và no-cache execution.
- [ ] Có regression test khi external input đổi.
- [ ] Các task side effects như publish/deploy không bị output cache skip.
- [ ] Khi cần tắt tạm, chọn `doNotCacheIf` cho task, không disable toàn build vô thời hạn.
- [ ] Nếu muốn luôn execute, hiểu thêm up-to-date checks và task skip rules.
- [ ] Không dùng `--refresh-dependencies` để chữa task output cache miss.
- [ ] Configuration Cache được test store **và reuse**.
- [ ] Không persist `configuration-cache-problems=warn` trong CI mà không có kế hoạch sửa.
- [ ] Secrets không đi vào shared cache artifacts/logs.
- [ ] Trusted CI push remote; untrusted builds không tự ý push.
- [ ] Khi nghi miss, giữ logs/cache key trước khi dọn thư mục.
- [ ] Chạy Gradle Wrapper/JDK/plugin versions theo policy, kiểm tra nâng version.

## 22. Câu hỏi tự kiểm tra

1. **`UP-TO-DATE` có chứng minh Build Cache đã hit không?** Không, nó là up-to-date check tại workspace.
2. **`FROM-CACHE` khác gì?** Output được lấy từ Build Cache thay vì chạy task action.
3. **`Reusing configuration cache.` nói điều gì?** Bỏ qua cấu hình lại task graph/state, không nói outputs task đã cache.
4. **`--no-build-cache` có tắt up-to-date checks không?** Không.
5. **`--no-configuration-cache` có chặn FROM-CACHE không?** Không.
6. **`--rerun-tasks` dùng khi nào?** Buộc selected tasks và prerequisites thực thi để đối chiếu action path.
7. **`--rerun` khác `--rerun-tasks` thế nào?** Có thể chỉ định task riêng, tránh ép mọi prerequisites.
8. **Muốn biết task cache key khác ở đâu, dùng gì?** `-Dorg.gradle.caching.debug=true` và so fingerprints/Build Scan.
9. **Task path có là input của Build Cache key không?** Không, nếu task implementations/inputs tương đương có thể chia sẻ kết quả.
10. **Đổi buildSrc có gây cache miss không?** Có thể, vì task/action implementation fingerprint thay.
11. **Input còn thiếu có thể gây triệu chứng gì?** UP-TO-DATE/FROM-CACHE sai dù external value đã đổi.
12. **Input thừa gây gì?** Miss không cần thiết khi input đó đổi.
13. **Vì sao dùng `@PathSensitive(RELATIVE)`?** Cho phép cache key bền qua absolute checkout paths khi relative path semantics đúng.
14. **`@CacheableTask` có bảo đảm task được cache không?** Không; còn validation/predicates/outputs conditions.
15. **`outputs.doNotCacheIf` có tắt up-to-date checks không?** Không.
16. **Muốn task luôn chạy trong tình huống external state chưa track, cần lưu ý gì?** Cả Build Cache lẫn up-to-date; tốt nhất model state đúng.
17. **Vì sao deploy không nên dùng cached task output để xác nhận đã deploy?** Remote side effect không nằm trong file output snapshots.
18. **`notCompatibleWithConfigurationCache` tắt lớp cache nào?** Configuration Cache cho graph có task không tương thích.
19. **`configuration-cache-problems=warn` có phù hợp làm setting lâu dài không?** Không; có nguy cơ reuse state lỗi.
20. **`--refresh-dependencies` có buộc tải lại tất cả JARs không?** Không; Gradle revalidate và tối ưu khi artifact không đổi.
21. **`--offline` làm gì?** Dùng dependency cache local, không hỏi repositories remote.
22. **Dynamic/changing versions default TTL bao lâu theo tài liệu?** 24 giờ, có thể cấu hình riêng.
23. **`clean` xóa Gradle User Home cache không?** Không.
24. **`--stop` có xóa Build Cache không?** Không, nó dừng daemon.
25. **Có nên xóa global caches trước khi lưu logs/cache keys không?** Không.
26. **Tại sao Build Cache hit có thể sai dù storage không corrupt?** Task undeclared input, nondeterministic output, output overlap.
27. **Remote cache nên cho ai push?** Trusted CI theo quyền/namespace policy.
28. **Muốn kiểm chứng cache relocatability, cần gì?** Same logical inputs ở hai workspaces với paths khác, so output/cache reuse.
29. **Test Configuration Cache một lần đã đủ không?** Không; cần store và reuse.
30. **Trong lab, thay `-PreportTag=CI` tác động gì?** Thay declared `@Input`, invalidates/matches cache key khác và đổi dòng TAG trong report.

## 23. Tài liệu Gradle chính thức

- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): task cacheability, `@CacheableTask`, local/remote Build Cache, cache conditions.
- [Gradle — Debugging and Diagnosing Build Cache Misses](https://docs.gradle.org/current/userguide/build_cache_debugging.html): control experiments, `org.gradle.caching.debug`, key/input hash comparisons, cascading misses.
- [Gradle — Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html): cache key, repeatable outputs, stable inputs, why some tasks should not cache.
- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): up-to-date checks, declared inputs/outputs, path normalization, task validation và output ownership.
- [Gradle — Common Caching Problems](https://docs.gradle.org/current/userguide/common_caching_problems.html): nondeterministic generators, untracked environment, custom/third-party task pitfalls.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): riêng biệt với Build Cache, task graph reuse.
- [Gradle — Debugging the Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_debugging.html): reason reporting, HTML reports, `notCompatibleWithConfigurationCache`, Problems warnings và integrity checks.
- [Gradle — Enabling the Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_enabling.html): `--configuration-cache`/`--no-configuration-cache` và invalidation.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): `--offline`, `--refresh-dependencies`, dynamic/changing TTL.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--build-cache`, `--rerun-tasks`, `--rerun`, `--no-configuration-cache`.
- [Gradle — TaskOutputs.doNotCacheIf](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.tasks/-task-outputs/do-not-cache-if.html): conditional disable of task output caching.
- [Gradle — TaskOutputs.cacheIf](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.tasks/-task-outputs/cache-if.html): opt-in caching predicate và cache conditions.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): unique outputs, task input model, safe incremental builds.
- [Gradle — Gradle TestKit](https://docs.gradle.org/current/userguide/test_kit.html): functional tests for Gradle task/cache correctness.
