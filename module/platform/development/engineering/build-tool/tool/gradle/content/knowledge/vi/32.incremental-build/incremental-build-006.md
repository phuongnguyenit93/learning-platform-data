# Thiết kế task cacheable bằng @CacheableTask trong Gradle

## Mục tiêu bài học

Một build Gradle có thể chạy nhanh hơn nhờ **up-to-date checks** và **build cache**, nhưng hai cơ chế này không giống nhau. Khi bạn phát triển custom task dùng để sinh code, biến đổi nội dung, phân tích tài liệu hoặc tạo artifact, chỉ có method **@TaskAction** là chưa đủ để Gradle tái sử dụng kết quả an toàn. Bạn phải khai báo **toàn bộ inputs, outputs**, bảo đảm kết quả **deterministic** (cùng inputs tạo cùng bytes), **relocatable** (đổi đường dẫn workspace mà kết quả không đổi) và đánh dấu task type có thể cache bằng **@CacheableTask**.

Ví dụ đúng về ý tưởng:

~~~java
@CacheableTask
public abstract class GenerateIndex extends DefaultTask {
    @InputDirectory
    @PathSensitive(PathSensitivity.RELATIVE)
    public abstract DirectoryProperty getInputDirectory();

    @Input
    public abstract Property<String> getHeading();

    @OutputFile
    public abstract RegularFileProperty getOutputFile();
}
~~~

Các annotations này mô tả một phần **hợp đồng với Gradle**. Phần còn lại nằm ở mã **@TaskAction**: không đọc input ngầm, không ghi output ngoài khai báo, không nhúng timestamp/absolute path/random value và không dựa vào thứ tự duyệt file không ổn định.

Sau bài này bạn có thể:

1. Phân biệt **UP-TO-DATE**, **FROM-CACHE**, **EXECUTED**, **NO-SOURCE** và **SKIPPED**.
2. Giải thích build cache key gồm task implementation/action, input property names/values, output property names và normalized file snapshots.
3. Biết vì sao **@CacheableTask** chỉ là lời cam kết “task type có thể cache”, còn **--build-cache** hoặc **org.gradle.caching=true** mới bật cơ chế cache cho invocation.
4. Dùng đúng **@Input**, **@InputFile**, **@InputFiles**, **@InputDirectory**, **@OutputFile**, **@OutputDirectory**, **@Nested**, **@Internal** và các annotations bổ trợ.
5. Thiết kế file input path normalization bằng **@PathSensitive(PathSensitivity.RELATIVE)** để cache có thể được dùng lại giữa các workspace.
6. Hiểu **@Classpath**, **@CompileClasspath**, **@IgnoreEmptyDirectories**, **@NormalizeLineEndings**, **@SkipWhenEmpty** và **@Incremental** khi phù hợp.
7. Viết custom Gradle task bằng **Java 17** với **Gradle-managed properties** và code transform hoàn toàn deterministic.
8. Chạy lab độc lập bằng Gradle Wrapper và kiểm tra output từ source files thật.
9. Biên dịch/chạy phần thuật toán Java thuần bằng **javac/java** với stdout chính xác, không cần Gradle API cho bước đó.
10. Tự chứng minh cache hit bằng chạy lần đầu, UP-TO-DATE, clean + FROM-CACHE, thay đổi input và thử ở thư mục khác.
11. Hiểu vì sao output bị chồng lấn, input ẩn, environment dependence hay task viết ra ngoài output directory làm cache không đáng tin.
12. Thiết kế TestKit/integration tests cho cacheable task, kiểm tra kết quả tái lập và tính relocatable.
13. Phân biệt **build cache** với **configuration cache** và incremental processing của task.
14. Chọn khi nào **không nên** cache, kể cả task Copy/Sync, network call, release/upload hoặc thao tác có side effects.
15. Chẩn đoán task bị tắt caching, cache misses hoặc cache hit sai bằng các công cụ Gradle.

Ví dụ chính dùng **Groovy DSL + Java 17**. Có phần Kotlin DSL. Cần **Gradle Wrapper** hỗ trợ chạy trên JDK 17 và core Gradle plugins. Lab không cần Maven Central để biên dịch chính ứng dụng bởi **buildSrc** dùng **gradleApi()** có sẵn từ Gradle distribution; nếu Wrapper distribution chưa có trong máy, máy vẫn có thể cần kết nối mạng để tải Gradle.

---

## 1. Vì sao phải thiết kế task cacheable?

Xem pipeline:

~~~text
src/notes/guide.txt  \
src/notes/intro.txt   ---> GenerateIndex ---> build/generated/index.txt
heading="CACHE DEMO"  /
~~~

Giả sử mỗi lần task chạy mất 30 giây, và cùng inputs luôn sinh cùng index.txt. Trong cùng workspace, sau lần chạy đầu, Gradle có thể bỏ qua lần sau nếu inputs/outputs không đổi (**UP-TO-DATE**). Nhưng khi xóa build/ hoặc checkout repository trong workspace mới, kết quả local trước đó không còn; khi bật **build cache**, Gradle có thể lấy output từ một lần chạy đã được cache (**FROM-CACHE**) thay vì chạy lại.

### 1.1. Ba cơ chế liên quan nhưng không đồng nhất

| Cơ chế | Kiểm tra điều gì? | Dấu hiệu thường thấy | Phạm vi |
| --- | --- | --- | --- |
| **Up-to-date check** | Inputs và outputs so với trạng thái được Gradle lưu ở workspace hiện tại | **UP-TO-DATE** | Workspace/build state hiện tại |
| **Build cache** | Có artifact outputs cho cache key tương ứng không? | **FROM-CACHE** | Local/remote cache, có thể qua nhiều workspaces/máy |
| **Incremental task execution** | InputChanges nào được thêm/sửa/xóa từ lần trước? | Task thực thi xử lý một phần | Cần task hỗ trợ InputChanges, không đồng nghĩa cache hit |

**@CacheableTask** phục vụ build cache, **không tự khiến một task chạy incremental**. Một task cacheable có thể luôn đọc lại toàn bộ inputs khi cần thực thi; đó là hợp lệ.

### 1.2. Điều kiện thực tế để tái sử dụng kết quả

Một task được cache đúng thường cần:

- **Task type opt-in** qua @CacheableTask (hoặc runtime API phù hợp).
- **Build cache được bật**.
- **Tất cả inputs ảnh hưởng output đã khai báo**.
- **Tất cả outputs được task sở hữu đã khai báo**.
- **Output deterministic**, không chứa nguồn ngẫu nhiên/time/environment không được khai báo.
- **Inputs được normalize phù hợp** để các workspace giống nhau dùng chung key.
- **Outputs không bị task khác ghi chồng**.
- **Gradle không có validation problem/điều kiện vô hiệu cache**.
- **Cache có entry matching key** để xảy ra FROM-CACHE; nếu miss, task vẫn có thể chạy và lưu kết quả.

Do đó **“đã ghi @CacheableTask” không bảo đảm sẽ xuất hiện FROM-CACHE**.

### 1.3. Task không được cache vẫn có thể UP-TO-DATE

Custom task có @Input/@OutputFile đúng, nhưng không @CacheableTask, vẫn có thể được Gradle coi UP-TO-DATE trong workspace hiện tại. Sau **clean**, nó phải thực thi lại vì output bị xóa; nó không tự khôi phục từ build cache.

Đây là một trong những lỗi hiểu nhầm phổ biến: thấy **UP-TO-DATE** rồi báo rằng build cache đã hoạt động.

### 1.4. Cache không chứng minh code đúng

Nếu task sai logic và sinh một file không đúng, cache có thể lưu và lặp lại **chính file sai ấy**. Build cache tối ưu việc tái sử dụng những outputs được tuyên bố, **không xác nhận correctness** của transformation. Cần tests riêng cho thuật toán và task wiring.

---

## 2. Build cache key được tạo từ đâu?

Theo tài liệu Gradle, cache key của task phụ thuộc vào các thành phần như:

- **Task implementation** và classpath của implementation.
- **Implementations của task actions**.
- **Tên output properties**.
- **Tên và giá trị của input properties**.
- **Fingerprints/normalized paths/content của input files**.
- Những phần liên quan build logic/classpath khác có tác động đến việc thực thi.

Một cách hình dung:

~~~text
cacheKey = H(
    taskTypeImplementation,
    taskActionsImplementation,
    outputPropertyNames,
    inputPropertyNames,
    inputValues,
    normalizedInputFileSnapshots,
    relevantImplementationClasspath
)
~~~

Đây là **mô hình giải thích**, không phải API tính hash hay thuật toán hashing được Gradle cam kết. Không tự tạo key bằng cách hash mỗi source file rồi cho rằng đủ an toàn.

### 2.1. Những điều không nhất thiết thuộc cache key

Gradle có thể chia sẻ outputs giữa **hai tasks khác tên**, thậm chí khác project path, khi task implementation, input/output property contracts và input fingerprints tương thích. **Task path** không mặc nhiên là thành phần của cache key.

Ví dụ, nếu task ở **:app** và **:service** cùng tạo một index deterministic với cùng inputs, Gradle có thể tái sử dụng cache entry khi các điều kiện khớp.

**Không đưa task path vào output** nếu bạn muốn cùng inputs tạo cùng result giữa projects nhưng task path lại không được khai báo là @Input. Nếu output thực sự cần khác theo module name, hãy khai báo **moduleName** như một @Input cụ thể.

### 2.2. Output location thường không là input

**Tên output property** tham gia vào cache key, còn **absolute output path** thường không được dùng như một semantic input. Điều này cho phép Gradle khôi phục cùng bytes vào **build/generated/index.txt** trong workspace khác.

Sai:

~~~java
content.append(getOutputFile().get().getAsFile().getAbsolutePath());
~~~

nếu output được cache mà output path không được khai báo là input có ý nghĩa. Nó tạo bytes khác nhau giữa máy A và máy B dù Gradle nghĩ task inputs giống nhau.

**Quy tắc:** đường dẫn output là **địa chỉ đặt kết quả**, không phải dữ liệu nội dung kết quả, trừ khi API thực sự cần và bạn model nó thành input phù hợp.

### 2.3. Có input ẩn sẽ gây false cache hit

Ví dụ:

~~~java
String locale = Locale.getDefault().toString();
String output = text.toUpperCase();
~~~

Nếu môi trường locale khác nhưng Gradle không biết locale đó là input, một cache entry có thể được reuse sai. Sửa bằng **Locale.ROOT** khi business semantics không phụ thuộc locale, hoặc khai báo locale như @Input nếu thực sự là một lựa chọn có chủ đích.

Tương tự với **System.getenv**, **System.getProperty**, **git rev-parse**, **currentTimeMillis**, **Random**, external service responses, current working directory, process command flags, compiler/tool versions.

### 2.4. Input biến động liên tục làm cache miss liên tục

Nếu task nhận **System.currentTimeMillis()** làm input mỗi lần chạy, key sẽ khác liên tục. Điều đó có thể giữ correctness nhưng phá giá trị caching. Nếu timestamp không thuộc sản phẩm về mặt nghiệp vụ, **loại timestamp khỏi output** thường tốt hơn là biến nó thành @Input.

### 2.5. @CacheableTask không được tự kế thừa

Theo Gradle Build Cache docs, **@CacheableTask không được thừa kế tự động bởi subclasses** theo semantics annotation này. Nếu định nghĩa subclass custom của một task class cacheable, hãy xem lại contract và quyết định opt-in rõ; không mặc nhiên mọi subclass đều an toàn để cache.

---

## 3. Các annotations inputs/outputs cần biết

| Annotation | Loại property thích hợp | Tác dụng |
| --- | --- | --- |
| **@Input** | Property<String>, Property<Boolean>, giá trị serializable | Giá trị cấu hình ảnh hưởng output |
| **@InputFile** | RegularFileProperty/File | Một file đầu vào |
| **@InputFiles** | ConfigurableFileCollection/Iterable files | Nhiều files/directories đầu vào |
| **@InputDirectory** | DirectoryProperty/directory | Một thư mục đầu vào |
| **@OutputFile** | RegularFileProperty/file | Một file do task tạo và sở hữu |
| **@OutputDirectory** | DirectoryProperty/directory | Thư mục outputs do task sở hữu |
| **@Nested** | Object/beans chứa annotated properties | Gradle đi sâu fingerprint nested inputs |
| **@Internal** | Task property không phải input/output | Không tính vào fingerprints |
| **@Optional** | Input property có thể vắng | Điều chỉnh validation cho input tùy chọn |
| **@LocalState** | Local workspace state | Scratch/state phục vụ task, không phải cacheable output |
| **@Destroys** | File/directory bị phá hủy | Mô tả các path bị task xóa, giúp scheduling safety |

**Không dùng @Internal cho dữ liệu ảnh hưởng output** chỉ để tránh cache miss. Điều đó che một input khỏi Gradle và có thể dẫn đến cache hit không đúng.

### 3.1. Ví dụ một task có tất cả dữ liệu thiết yếu

~~~java
@CacheableTask
public abstract class GenerateIndex extends DefaultTask {

    @InputDirectory
    @PathSensitive(PathSensitivity.RELATIVE)
    public abstract DirectoryProperty getInputDirectory();

    @Input
    public abstract Property<String> getHeading();

    @OutputFile
    public abstract RegularFileProperty getOutputFile();
}
~~~

Các getter phải được annotated đúng, không đặt @Input lên một arbitrary setter rồi kỳ vọng Gradle hiểu. Gradle validation còn kiểm tra loại property và các annotation không hợp lệ trước khi task chạy.

### 3.2. Gradle-managed properties và lazy configuration

Ưu tiên:

~~~java
public abstract Property<String> getHeading();
public abstract DirectoryProperty getInputDirectory();
public abstract RegularFileProperty getOutputFile();
~~~

trong **abstract DefaultTask subclass**, để Gradle tạo implementation của managed properties. Lúc task configuration dùng **set(...)** với Provider/Directory/RegularFile abstractions, tránh tự kiểm tra path hoặc đọc file từ sớm.

### 3.3. File input path sensitivity

File path có thể được fingerprint theo:

| PathSensitivity | Ý nghĩa | Khi nào phù hợp |
| --- | --- | --- |
| **ABSOLUTE** | Cả absolute path được xem là input | Chỉ khi path thật sự ảnh hưởng outputs; giảm tính relocatable |
| **RELATIVE** | Đường dẫn tương đối trong input root/collection quan trọng | Source trees, directory input mà relative layout có ý nghĩa |
| **NAME_ONLY** | Chỉ tên file quan trọng | Một số transformations ít gặp; dễ collision |
| **NONE** | Không quan tâm path, chỉ nội dung | Input file độc lập khi filename không ảnh hưởng output |

Gradle best practices thường khuyên **NONE cho file đơn không cần path** và **RELATIVE cho input directory/tree**. Không chọn NONE cho một cây thư mục mà relative path quyết định output.

### 3.4. @PathSensitive(RELATIVE) không tự làm output relocatable

Nếu input path được fingerprint tương đối nhưng task action vẫn ghi **root.toAbsolutePath()** vào file kết quả, cache key giống nhau giữa hai workspaces mà bytes output khác nhau. Vì vậy **normalization và implementation phải tương thích**.

### 3.5. @Classpath khác @InputFiles

Khi task tiêu thụ Java runtime classpath, dùng:

~~~java
@Classpath
public abstract ConfigurableFileCollection getRuntimeClasspath();
~~~

**@Classpath** hiểu các JARs/class directories theo rules cho Java classpath, bao gồm thứ tự classpath và normalization cho những thay đổi không ảnh hưởng semantics. **@CompileClasspath** dành cho task có kết quả chỉ phụ thuộc ABI của dependencies, ví dụ compilation tránh recompile khi implementation của library đổi nhưng public ABI không.

Không tùy tiện gắn @CompileClasspath cho một bytecode transformer/runner cần method bodies: điều đó có thể bỏ qua sự thay đổi implementation quan trọng.

### 3.6. @IgnoreEmptyDirectories

Với input directory:

~~~java
@InputDirectory
@PathSensitive(PathSensitivity.RELATIVE)
@IgnoreEmptyDirectories
public abstract DirectoryProperty getInputDirectory();
~~~

Annotation này giúp fingerprint không bị invalidated bởi chỉ việc thêm/xóa những **empty directories** nếu task cũng bỏ qua chúng. Nếu output thực sự ghi danh sách cả empty directories, bạn không nên ignore chúng.

### 3.7. @NormalizeLineEndings

Với file input mang nội dung text, Gradle có **@NormalizeLineEndings** để coi CRLF/LF tương đương khi tính fingerprints. **Chỉ dùng nếu task output cũng độc lập với kiểu line ending của input**. Nếu task copy raw bytes và output khác khi source có CRLF, normalize fingerprint mà không normalize output sẽ gây false cache hits.

### 3.8. @SkipWhenEmpty và NO-SOURCE

FileCollection:

~~~java
@InputFiles
@SkipWhenEmpty
@PathSensitive(PathSensitivity.RELATIVE)
public abstract ConfigurableFileCollection getSourceFiles();
~~~

Có thể khiến task bị SKIPPED với outcome **NO-SOURCE** khi không có source files theo contract. Điều này phù hợp với compiler/transformer không cần tạo output nếu không có input, nhưng **không phù hợp** với task vẫn phải tạo một file header rỗng khi input empty.

Lab dùng **@InputDirectory** mà **không @SkipWhenEmpty** vì nếu thư mục không chứa file, task vẫn tạo index header. Đây là quyết định semantics, không phải thiếu optimization.

### 3.9. @Incremental và InputChanges

Một task xử lý từng file có thể dùng **@Incremental** cùng input files và **InputChanges** ở @TaskAction để chỉ xử lý added/modified/removed files, giữ output state thích hợp. Điều đó độc lập với @CacheableTask. Một task cần đảm bảo full rebuild khi **InputChanges.isIncremental() == false**.

---

## 4. Thiết kế cacheable task: tiêu chuẩn correctness

### 4.1. Deterministic output

Với inputs giống nhau, task phải tạo **cùng bytes**:

~~~text
Input set A, implementation V1 ---> output bytes X
Input set A, implementation V1 ---> output bytes X
~~~

Không thêm:
- Timestamp hiện tại.
- Random UUID.
- Absolute path workspace.
- Task path hoặc project name không khai báo input.
- Username/hostname/environment nếu không phải input có kiểm soát.
- Thứ tự duyệt filesystem bất định.
- Encoding hoặc locale theo default máy.

### 4.2. Relocatable output

Một developer checkout ở:

~~~text
/home/dev/work/cache-lab
~~~

và CI checkout ở:

~~~text
C:\agent\work\cache-lab
~~~

phải tạo **cùng nội dung output** khi source bytes và semantic inputs giống nhau. Sắp xếp file theo **relative path** và dùng dấu **/** để hiển thị đường dẫn giúp output không phụ thuộc OS.

### 4.3. Complete input declaration

Nếu kết quả đọc:
- File text.
- Config values.
- External templates.
- Tool/version.
- Environment selector.
- Classpath.

thì mỗi thứ có thể làm thay đổi output phải được mô hình hóa là input tương ứng. Không đọc file thứ hai ngoài getInputDirectory mà không khai báo nó; không chạy script từ network nếu network response không có provenance/version.

### 4.4. Complete output declaration

Nếu task tạo:
- index.txt;
- metadata.json;
- archive.zip;

thì phải khai báo cả ba outputs hoặc sở hữu một **OutputDirectory** riêng chứa chúng. Không viết tùy tiện vào source directory, temp của project khác, hoặc thư mục trùng với output của task khác.

### 4.5. Output ownership và overlapping outputs

Hai tasks cùng ghi **build/generated/index.txt** hoặc cùng sở hữu một output directory gây khó cho Gradle biết file nào thuộc task nào. Gradle có thể tắt caching của tasks có overlapping outputs để tránh cache khôi phục sai.

Tốt hơn:

~~~text
build/generated/indexMain/index.txt
build/generated/indexDocs/index.txt
~~~

và mỗi task có output property riêng. Nếu hai tasks cần hợp nhất kết quả, tạo **aggregation task thứ ba** tiêu thụ outputs của hai tasks qua Provider API.

### 4.6. Không dựa vào stale outputs

Task action nên ghi đầy đủ output **từ inputs hiện tại**. Nếu một file input biến mất, output không được giữ lại nội dung cũ. Với @OutputDirectory, xóa stale files hoặc tạo output directory riêng được quản lý đúng trong full rebuild. Build cache sẽ khôi phục snapshot outputs, nên task phải có clear ownership.

---

## 5. Lab Java 17 hoàn chỉnh: @CacheableTask + deterministic index

Lab dùng **buildSrc** để biên dịch Java custom task type bằng Gradle API. Logic tạo index được đặt trong class Java thuần **IndexBuilder**, để có thể kiểm thử độc lập với Gradle bằng **javac/java**.

### 5.1. Cấu trúc thư mục

~~~text
cacheable-task-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── src/notes/
│   ├── guide.txt
│   └── intro.txt
└── buildSrc/
    ├── build.gradle
    └── src/main/java/demo/cache/
        ├── IndexBuilder.java
        └── GenerateIndex.java
~~~

**Gradle Wrapper** cần được tạo bằng Gradle hoặc lấy từ project tin cậy, không tự viết JAR. Giữ đủ package directories và tên files như trong sơ đồ. **buildSrc** là build logic project được Gradle xử lý tự động; mã trong buildSrc có thể dùng làm task type trong root build.gradle.

### 5.2. settings.gradle

~~~groovy
rootProject.name = 'cacheable-task-lab'
~~~

### 5.3. build.gradle của root

~~~groovy
plugins {
    id 'base'
}

tasks.register('generateIndex', demo.cache.GenerateIndex) {
    group = 'documentation'
    description = 'Generate a deterministic notes index'

    inputDirectory.set(
        layout.projectDirectory.dir('src/notes')
    )
    heading.set('CACHE DEMO')
    outputFile.set(
        layout.buildDirectory.file('generated/index.txt')
    )
}
~~~

**base** plugin cung cấp task **clean**. **tasks.register** là lazy task registration. Gradle nhận một typed custom task class từ **buildSrc** và cung cấp three managed properties.

Các tên properties trong task class phải là **getInputDirectory**, **getHeading**, **getOutputFile** để Gradle introspection nhận biết và DSL Groovy có accessors đúng.

### 5.4. buildSrc/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation gradleApi()
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}
~~~

**gradleApi()** cung cấp types như DefaultTask, CacheableTask, DirectoryProperty, @TaskAction. Nó lấy từ Gradle distribution và không cần một external Maven module download riêng.

**options.release = 17** yêu cầu compiler có hỗ trợ Java 17; nếu Gradle daemon đang chạy trên JDK17+, ví dụ hợp lệ. Nếu team dùng Gradle chạy trên JDK mới hơn, có thể bổ sung Java toolchain cho buildSrc để đảm bảo compiler phù hợp.

### 5.5. src/notes/guide.txt

Tạo file UTF-8 với nội dung:

~~~text
gradle
~~~

### 5.6. src/notes/intro.txt

Tạo file UTF-8 với nội dung:

~~~text
hello
~~~

Dòng cuối file có hoặc không có ký tự newline đều được logic **strip()** xử lý nhất quán. Không để file phụ khác trong src/notes nếu muốn so output chính xác theo ví dụ.

### 5.7. buildSrc/src/main/java/demo/cache/IndexBuilder.java

~~~java
package demo.cache;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;

public final class IndexBuilder {
    private IndexBuilder() {
    }

    public static String render(Path root, String heading)
            throws IOException {

        List<Path> files;

        try (Stream<Path> walk = Files.walk(root)) {
            files = walk
                    .filter(Files::isRegularFile)
                    .sorted(Comparator.comparing(path ->
                            root.relativize(path)
                                    .toString()
                                    .replace('\\', '/')
                    ))
                    .toList();
        }

        StringBuilder output = new StringBuilder()
                .append("# ")
                .append(heading)
                .append('\n');

        for (Path file : files) {
            String relativePath = root.relativize(file)
                    .toString()
                    .replace('\\', '/');

            String text = Files.readString(
                    file,
                    StandardCharsets.UTF_8
            ).strip().toUpperCase(Locale.ROOT);

            output.append(relativePath)
                    .append(" = ")
                    .append(text)
                    .append('\n');
        }

        return output.toString();
    }

    public static void main(String[] args)
            throws IOException {

        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: IndexBuilder <notes-directory>"
            );
        }

        System.out.print(
                render(Path.of(args[0]), "CACHE DEMO")
        );
    }
}
~~~

**Đây là một Java 17 class độc lập**, không import Gradle API. Thuật toán:

1. Dùng **Files.walk** để lấy files trong input directory.
2. Chỉ chọn regular files; empty directories không xuất hiện trong output.
3. Sắp xếp theo **relative paths** đã normalize dấu slash.
4. Đọc UTF-8, **strip()** whitespace đầu/cuối và **toUpperCase(Locale.ROOT)** để không phụ thuộc locale mặc định của OS.
5. Dùng newline cố định **'\n'**.
6. Không ghi absolute paths, timestamps, random IDs hoặc current date vào result.

**Điểm correctness:** Gradle task input property sẽ đánh dấu **toàn bộ thư mục** là input; thuật toán đọc mọi regular file trong thư mục. Không có file bên ngoài thư mục bị đọc ngầm. Nếu bổ sung file mới, input snapshot thay đổi và index thay đổi.

### 5.8. buildSrc/src/main/java/demo/cache/GenerateIndex.java

~~~java
package demo.cache;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.api.DefaultTask;
import org.gradle.api.file.DirectoryProperty;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.CacheableTask;
import org.gradle.api.tasks.IgnoreEmptyDirectories;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.InputDirectory;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.PathSensitive;
import org.gradle.api.tasks.PathSensitivity;
import org.gradle.api.tasks.TaskAction;

@CacheableTask
public abstract class GenerateIndex extends DefaultTask {

    @InputDirectory
    @PathSensitive(PathSensitivity.RELATIVE)
    @IgnoreEmptyDirectories
    public abstract DirectoryProperty getInputDirectory();

    @Input
    public abstract Property<String> getHeading();

    @OutputFile
    public abstract RegularFileProperty getOutputFile();

    @TaskAction
    public void generate() throws IOException {
        Path input = getInputDirectory()
                .get().getAsFile().toPath();

        String content = IndexBuilder.render(
                input,
                getHeading().get()
        );

        Path output = getOutputFile()
                .get().getAsFile().toPath();

        Files.createDirectories(output.getParent());
        Files.writeString(
                output,
                content,
                StandardCharsets.UTF_8
        );

        getLogger().lifecycle(
                "Generated {}",
                output.getFileName()
        );
    }
}
~~~

**Những điểm quyết định khả năng cache**:

- **@CacheableTask** trên **task type**: opt-in cho Gradle output cache.
- **@InputDirectory**: mọi file trong root input directory được snapshot; nếu file thay đổi, key có thể thay.
- **@PathSensitive(RELATIVE)**: tránh đưa absolute source root vào fingerprints.
- **@IgnoreEmptyDirectories**: không invalidated khi chỉ thêm/xóa folder trống vì IndexBuilder không ghi folder trống vào output.
- **@Input Property<String>**: heading thay đổi sẽ làm content khác, nên phải được fingerprint.
- **@OutputFile**: Gradle biết nơi chứa artifact, có thể snapshot/restore nó.
- **@TaskAction**: làm việc trong execution phase, không tự chạy ở configuration.
- **Gradle-managed Property APIs**: hỗ trợ lazy configuration và task validation.
- Không sử dụng Project object trong task action, không ghi file ngoài output property.

**Không làm Gradle task bằng cách tự chèn @CacheableTask vào IndexBuilder**. IndexBuilder là utility Java thuần; chỉ **GenerateIndex extends DefaultTask** mới là task class.

### 5.9. Chạy lab lần đầu

Linux/macOS:

~~~bash
./gradlew generateIndex --build-cache
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat generateIndex --build-cache
~~~

Nếu source/outputs chưa tồn tại và chưa có cache entry cho key tương ứng, Gradle **thực thi** task. Dòng do task action in:

~~~text
Generated index.txt
~~~

File kết quả:

~~~text
build/generated/index.txt
~~~

Nội dung của file (không phải toàn bộ Gradle stdout):

~~~text
# CACHE DEMO
guide.txt = GRADLE
intro.txt = HELLO
~~~

Lệnh Gradle còn có thể in task names và BUILD SUCCESSFUL. Không so transcript nguyên văn vì log level/daemon/caching khác nhau.

### 5.10. Chạy lại khi không đổi input/output

~~~bash
./gradlew generateIndex --build-cache
~~~

Gradle thường báo:

~~~text
> Task :generateIndex UP-TO-DATE
~~~

Do output vẫn có và fingerprints không đổi, task action không chạy; **không có dòng mới Generated index.txt** từ @TaskAction. Đây là **up-to-date check**, chưa phải FROM-CACHE.

### 5.11. Clean rồi yêu cầu lại cùng output

~~~bash
./gradlew clean generateIndex --build-cache --info
~~~

Vì **clean** xóa build/ nên local output không còn, nhưng nếu cache entry của lần chạy trước đã được lưu và còn hợp lệ, Gradle thường báo:

~~~text
> Task :generateIndex FROM-CACHE
~~~

File **build/generated/index.txt** được restore với nội dung chính xác như trước. Task action không chạy, nên không cần in **Generated index.txt** ở lượt FROM-CACHE.

**Nếu thấy EXECUTED** thay vì FROM-CACHE, không vội đánh dấu task sai: có thể cache entry chưa tồn tại, cache bị disable, implementation classpath hoặc input fingerprints thay đổi, task validation/caching conditions khác, cache bị eviction, hoặc đang dùng một Gradle User Home/cache khác. Xem **--info** để hiểu lý do.

### 5.12. Thay đổi @Input value heading

Trong root build.gradle:

~~~groovy
heading.set('DOCS INDEX')
~~~

Giữ nguyên những cấu hình khác, chạy:

~~~bash
./gradlew generateIndex --build-cache
~~~

Key khác vì **heading** là @Input. Nếu chưa có cache entry cho key mới, task execute và file đổi thành:

~~~text
# DOCS INDEX
guide.txt = GRADLE
intro.txt = HELLO
~~~

Đổi heading trở lại CACHE DEMO sau đó có thể khôi phục entry trước; kết quả cụ thể phụ thuộc Gradle state/up-to-date/cache available.

### 5.13. Thay nội dung file input

Giữ heading CACHE DEMO, sửa **src/notes/intro.txt** từ hello thành welcome, rồi chạy:

~~~bash
./gradlew generateIndex --build-cache
~~~

Nếu chưa có entry cho inputs mới, output:

~~~text
# CACHE DEMO
guide.txt = GRADLE
intro.txt = WELCOME
~~~

**InputDirectory** đã khai báo nên Gradle nhận ra nội dung input thay đổi. Nếu task vẫn UP-TO-DATE dù file thật sự thay và timestamp/hash state được cập nhật chính xác, cần điều tra file path/fingerprint/task execution graph.

### 5.14. Thêm file vào thư mục con

Ví dụ tạo:

~~~text
src/notes/advanced/cache.txt
~~~

nội dung:

~~~text
reuse
~~~

Khi render, output sort theo relative path:

~~~text
# CACHE DEMO
advanced/cache.txt = REUSE
guide.txt = GRADLE
intro.txt = HELLO
~~~

Đây là output nếu heading CACHE DEMO, intro.txt đã hoàn nguyên hello và chỉ thêm file advanced/cache.txt. Dấu slash được normalize để output ổn định giữa Windows và Unix.

### 5.15. Thử output bị chỉnh sửa

Sau build thành công, sửa trực tiếp **build/generated/index.txt**. Chạy lại generateIndex với caching bật. Gradle sẽ thấy output fingerprint không khớp state trước đó và không nên coi task UP-TO-DATE; nếu cache entry matching key còn, có thể restore output chuẩn FROM-CACHE, nếu không task execute.

**Không dùng sửa output bằng tay làm policy cập nhật tài liệu**. Output được task sở hữu nên source of truth phải ở inputs **src/notes** và **heading**.

---

## 6. Java 17: biên dịch thuật toán bằng javac/java

Vì **IndexBuilder.java không dùng Gradle API**, bạn có thể kiểm tra thuật toán tách biệt. Đây là một kiểm chứng hữu ích cho deterministic output.

### 6.1. Linux/macOS

Từ root lab:

~~~bash
mkdir -p out

javac --release 17 -encoding UTF-8 -d out \
    buildSrc/src/main/java/demo/cache/IndexBuilder.java

java -cp out demo.cache.IndexBuilder src/notes
~~~

Với hai input files nguyên bản, stdout **chính xác**:

~~~text
# CACHE DEMO
guide.txt = GRADLE
intro.txt = HELLO
~~~

### 6.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -encoding UTF-8 -d out buildSrc\src\main\java\demo\cache\IndexBuilder.java

java -cp out demo.cache.IndexBuilder src\notes
~~~

Stdout giống Linux/macOS khi source bytes như nhau.

### 6.3. Không thể compile GenerateIndex.java chỉ bằng javac thuần

Class **GenerateIndex** import Gradle API types như **DefaultTask**, **Property**, **@CacheableTask**. Nếu gọi **javac GenerateIndex.java** không cung cấp Gradle API classpath, compiler sẽ báo thiếu packages org.gradle.api. Đó không phải lỗi của task: **buildSrc Gradle build** có **implementation gradleApi()** để cung cấp đúng classpath.

Bạn đã tách được:
- **IndexBuilder**: pure Java logic, dễ test độc lập.
- **GenerateIndex**: Gradle adapter task, chịu trách nhiệm input/output declarations, execution và caching.

Kiến trúc này thuận tiện cho unit/functional testing và hạn chế Gradle API leakage vào business transformation.

---

## 7. Kotlin DSL tương đương cho task

Giữ nguyên hai Java classes trong buildSrc. Thay **settings.gradle** bằng **settings.gradle.kts**:

~~~kotlin
rootProject.name = "cacheable-task-lab"
~~~

Root **build.gradle.kts**:

~~~kotlin
plugins {
    base
}

tasks.register<demo.cache.GenerateIndex>("generateIndex") {
    group = "documentation"
    description = "Generate a deterministic notes index"

    inputDirectory.set(
        layout.projectDirectory.dir("src/notes")
    )
    heading.set("CACHE DEMO")
    outputFile.set(
        layout.buildDirectory.file("generated/index.txt")
    )
}
~~~

buildSrc **build.gradle.kts**:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    implementation(gradleApi())
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
    options.encoding = "UTF-8"
}
~~~

**Không để đồng thời hai versions settings.gradle/settings.gradle.kts hoặc build.gradle/build.gradle.kts có logic mâu thuẫn** khi chuyển đổi lab. Gradle Java task annotations, cache key, output file và Java source không thay đổi chỉ vì script chuyển từ Groovy sang Kotlin.

---

## 8. Quan sát task states và lệnh chẩn đoán

### 8.1. Bảng trạng thái

| Outcome | Ý nghĩa | Có chạy @TaskAction? |
| --- | --- | --- |
| **EXECUTED** (không có state suffix) | Task đã chạy | Thông thường có |
| **UP-TO-DATE** | Inputs/outputs khớp history trong workspace | Không |
| **FROM-CACHE** | Output được restore từ build cache | Không |
| **NO-SOURCE** | Task được skip do input source rỗng theo semantics của task | Không |
| **SKIPPED** | Task có điều kiện skip, ví dụ onlyIf false | Không |
| **FAILED** | Task execution/validation thất bại | Có thể fail trước hoặc trong action |

Lưu ý: **NO-SOURCE** không phải dấu hiệu rằng custom task đã sinh output header; với lab input directory rỗng vẫn có thể generate index header, vì ta không dùng @SkipWhenEmpty.

### 8.2. Lệnh chính

~~~bash
./gradlew generateIndex --build-cache --info
./gradlew clean generateIndex --build-cache --info
./gradlew generateIndex --no-build-cache --info
./gradlew generateIndex --rerun-tasks --info
./gradlew help --task generateIndex
./gradlew tasks --all
~~~

Ý nghĩa:

- **--build-cache**: bật task output cache cho invocation này.
- **--no-build-cache**: tắt cache trong invocation, không nhất thiết tắt up-to-date check.
- **--rerun-tasks**: buộc tasks chạy lại thay vì reuse UP-TO-DATE/FROM-CACHE như bình thường; dùng để điều tra output correctness.
- **--info**: xem nguyên nhân task execute, cache disabled, cache key/inputs thay đổi ở mức Gradle log cung cấp.
- **help --task**: kiểm tra task type, description/options.
- **tasks --all**: kiểm tra task registration.

### 8.3. Phân biệt cache enabled và cacheable

Hai câu hỏi riêng:

1. Build cache có bật qua **--build-cache** hoặc **org.gradle.caching=true** không?
2. Task type có được phép cache qua **@CacheableTask** hoặc runtime API **outputs.cacheIf** không?

Nếu chỉ có một trong hai, task chưa chắc được cache. Các nguyên nhân khác như validation failures và overlapping outputs còn có thể tắt cache.

### 8.4. Xem lý do caching disabled

Với **--info**, Gradle thường có thông báo thuộc dạng:

~~~text
Caching disabled for task ':someTask' because: ...
~~~

Phần **...** ở đây là mô tả khái niệm, không phải một log cố định; Gradle có thể nói task không được cache mặc định, có overlapping outputs, validation issues, no outputs, hoặc custom cache condition không đạt.

Đừng chỉ nhìn **BUILD SUCCESSFUL**; phải kiểm tra từng task outcome khi đánh giá lợi ích caching.

### 8.5. Khi cache miss, inspect cái gì?

Kiểm tra theo thứ tự:
1. Task implementation/classpath có đổi không?
2. Input values như heading/version/flags có đổi không?
3. File input content/relative path có đổi không?
4. PathSensitive có vô tình dùng ABSOLUTE không?
5. Có tính hostname/time/environment vào input hoặc output không?
6. Có output bị task khác ghi chồng không?
7. Cache entry có tồn tại trong local/remote cache đã cấu hình không?
8. Gradle đã từng lưu entry từ lần trước chưa?
9. Java/JDK/Gradle/plugin versions có tương thích không?
10. Một task validation warning có tắt optimization không?

Không cố sửa miss bằng cách “bỏ bớt @Input” nếu giá trị bị bỏ thực sự ảnh hưởng output.

---

## 9. Thiết kế relocalizable cache giữa hai workspaces

### 9.1. Vì sao RELATIVE quan trọng?

Hai dev có project ở:

~~~text
/home/alice/work/cacheable-task-lab
/home/bob/sandbox/cacheable-task-lab
~~~

Nội dung:

~~~text
src/notes/guide.txt = "gradle"
src/notes/intro.txt = "hello"
~~~

không đổi. Nếu task fingerprint tuyệt đối từng file, hai workspaces tạo different keys chỉ vì root paths khác. **@PathSensitive(RELATIVE)** bỏ absolute input root khi fingerprints và dùng relative file paths quan trọng.

### 9.2. Thuật toán cũng phải dùng relative path

Code trong IndexBuilder:

~~~java
root.relativize(file).toString().replace('\\', '/')
~~~

Đây là lựa chọn phù hợp. Nếu thay bằng:

~~~java
file.toAbsolutePath().toString()
~~~

thì output bytes khác giữa workspaces, mặc dù task input fingerprint RELATIVE giống nhau. Đó là **false cache-hit risk** nếu @Input không model output-affecting absolute path, nên không được dùng.

### 9.3. Quy trình test relocation

1. Chạy lab ở workspace A với **--build-cache** để seed cache.
2. Copy **source files, Gradle scripts, buildSrc source và Wrapper** sang một workspace B khác đường dẫn (không cần copy build/ outputs).
3. Sử dụng cùng Gradle user home/build cache store hoặc một shared remote cache được cấu hình đúng.
4. Chạy **generateIndex --build-cache --info** ở B.
5. Kiểm tra output bytes/counters bằng lệnh đọc file.
6. Quan sát **FROM-CACHE** nếu tất cả cache key components khớp và cache entry có thể truy cập. Nếu miss, điều tra implementation classpath/buildSrc differences, Gradle/JDK versions và file fingerprints trước khi kết luận RELATIVE sai.
7. Dù cache hit hay miss, **output content phải đúng và không chứa absolute path**.

Gradle docs khuyên **functional tests cho relocatability**, không dùng một lời khẳng định “annotated RELATIVE là xong”.

### 9.4. Kiểm tra bytes trên Unix và Windows

Linux/macOS:

~~~bash
sha256sum build/generated/index.txt
~~~

Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 .\build\generated\index.txt
~~~

Hash của **cùng file bytes** phải khớp dù vị trí khác nhau. Giá trị hash cụ thể không được hardcode ở bài học vì newline/data changes sẽ thay nó; so kết quả từ hai lần chạy hoặc hai workspaces được kiểm soát.

---

## 10. Các input annotations nâng cao và sai lầm thường gặp

### 10.1. @InputFile cho một config cụ thể

~~~java
@InputFile
@PathSensitive(PathSensitivity.NONE)
public abstract RegularFileProperty getConfigFile();
~~~

Phù hợp khi output chỉ quan tâm **nội dung file**, không phải tên hoặc đường dẫn của file config. Nếu tên file ảnh hưởng output naming, path sensitivity NONE không còn chính xác; khai báo tên/output relationship phù hợp.

### 10.2. @InputFiles với fileTree

~~~java
@InputFiles
@PathSensitive(PathSensitivity.RELATIVE)
public abstract ConfigurableFileCollection getTemplates();
~~~

Trong build script:

~~~groovy
tasks.named('renderTemplates') {
    templates.from(fileTree('src/templates') {
        include '**/*.tmpl'
    })
}
~~~

Đây là **fragment**, chỉ chạy khi task type renderTemplates có property templates và được đăng ký. Nó minh họa cách giới hạn những files thật sự ảnh hưởng output. Không nên fingerprint cả **src/** nếu task chỉ đọc **src/templates/**.

### 10.3. FileTree ordering

Gradle file collection order không nên được ngầm coi là deterministic. Trong task action, nếu output chứa danh sách file, hãy **sort explicit theo stable relative keys**, như IndexBuilder. Chỉ @InputFiles mà không sort không bảo đảm output là cùng một danh sách đúng thứ tự trên các OS.

### 10.4. @Classpath và @CompileClasspath

- **@Classpath**: khi classpath lookup order/implementation bytes có thể ảnh hưởng output.
- **@CompileClasspath**: khi task chỉ phụ thuộc public ABI của classes.
- **@InputFiles**: khi file bytes/paths được xử lý như dữ liệu thông thường.

Không dùng @CompileClasspath để cache task chạy code từ dependency JAR rồi đưa kết quả ra file: nếu code implementation thay đổi nhưng ABI giữ nguyên, task output vẫn có thể đổi, trong khi compile classpath normalization có thể bỏ qua change.

### 10.5. Optional input

~~~java
@Optional
@InputFile
@PathSensitive(PathSensitivity.NONE)
public abstract RegularFileProperty getOptionalConfig();
~~~

Nếu config vắng hợp lệ, action phải xử lý sự vắng mặt nhất quán bằng Provider API như **isPresent()**. Không gọi **get()** vô điều kiện khi property optional chưa có value.

### 10.6. @Internal không phải cách tắt fingerprint bừa bãi

**@Internal** hợp lệ khi property chỉ phục vụ logging/diagnostics không ảnh hưởng outputs, hoặc path được biểu diễn đầy đủ bởi một property khác. Nếu task output dùng giá trị của property nhưng bạn đánh dấu @Internal, cache có thể tái sử dụng sai result.

### 10.7. @Nested và model phức tạp

Khi task có một nested options object gồm các properties, dùng **@Nested** để Gradle đi sâu các annotated inputs trong nested type. Với Map/List cần serialize/stable order và API phù hợp.

Nếu plugin lưu mọi thứ trong một mutable custom Java object không serializable rồi gắn @Input, Gradle validation có thể báo unsupported type. Dùng Gradle-managed Property/MapProperty/ListProperty/Nested types, và test validation.

### 10.8. Default task properties khác output flags

Một task có property chỉ để hiển thị log verbosity mà không ảnh hưởng content output có thể được đánh dấu **@Internal**, tránh miss không cần. Nhưng nếu verbosity làm task sinh thêm/ít artifacts trong outputDirectory, lúc đó nó là @Input.

### 10.9. Thêm @CacheableTask lên kiểu task không có outputs

Task chỉ in log:

~~~java
@TaskAction
public void announce() {
    System.out.println("Hello");
}
~~~

không có file output meaningful để restore, nên caching task outputs thường không đem lại lợi ích. Không đánh dấu @CacheableTask chỉ để làm đẹp báo cáo. Với verification task có side effects (đẩy notification, gửi HTTP request), cache hit có thể bỏ qua side effect nên cần thiết kế khác.

---

## 11. @CacheableTask vs @DisableCachingByDefault và runtime API

### 11.1. Khi dùng @CacheableTask

Dùng cho task:
- Sinh source/documentation ổn định từ inputs.
- Compile/transform code deterministic.
- Chạy analyzer tốn thời gian, tạo report dưới output file/dir, có mọi inputs được capture.
- Tạo resource bundle ổn định có reproducible bytes.

**@CacheableTask** bật caching **theo type mặc định**, khi global cache enabled và không bị điều kiện runtime veto.

### 11.2. Khi không nên cache

Những tasks như **Copy**, **Sync**, một số I/O-only tasks có thể tạo outputs rẻ hơn việc tải cache entry. Tasks gửi release lên server, mở network call, deploy, publish hoặc gửi email có side effects không nên chỉ được modeled là reusable file outputs.

Gradle dùng **@DisableCachingByDefault** trên một số built-in task types để nêu lý do không tự cache, nhưng build logic vẫn có thể bật/tắt theo runtime API trong trường hợp phù hợp.

### 11.3. outputs.cacheIf và outputs.doNotCacheIf

Nếu không sửa được task type, Gradle hỗ trợ runtime API:

~~~groovy
tasks.named('someTask') {
    outputs.cacheIf('outputs are deterministic') {
        true
    }
}
~~~

Đây là **fragment**: phải biết someTask có outputs, inputs khai báo đúng, side effects không tồn tại và task type thật sự safe. **outputs.cacheIf** không tự thêm inputs hoặc outputs.

Khi có điều kiện cụ thể khiến task không cache được:

~~~groovy
tasks.named('someTask') {
    outputs.doNotCacheIf('external service involved') {
        true
    }
}
~~~

Điều kiện và TaskOutputs API được Gradle xét cùng annotation. Không dùng cacheIf true để “ép xanh” một task mà không hiểu hidden inputs.

### 11.4. @CacheableTask là cam kết duy trì lâu dài

Một khi plugin công bố task cacheable, người dùng có thể có cache entries từ versions trước và dùng ở nhiều môi trường. Khi thay implementation/task action hoặc inputs/outputs declarations, Gradle key thay đổi theo metadata; tuy nhiên nếu thay semantic behavior mà không khai báo mọi dependencies, rủi ro vẫn còn.

Có tests bảo đảm deterministic/relocatable là trách nhiệm của plugin author.

---

## 12. Phân biệt build cache và configuration cache

Hai cơ chế tên gần nhau nhưng lưu những thứ khác nhau:

| Khía cạnh | Build cache | Configuration cache |
| --- | --- | --- |
| Mục đích | Reuse **task outputs** | Reuse kết quả **configuration phase** |
| Dấu hiệu | **FROM-CACHE** | Reusing configuration cache |
| Điều kiện chính | Cacheable task, declared inputs/outputs, deterministic outputs | Build logic tương thích configuration cache |
| Kết quả lưu | Generated outputs/artifacts | Work graph/configuration model |
| API cốt lõi | @CacheableTask, TaskOutputs, buildCache settings | Provider API, Task action isolation, @Input/@Output, configuration-cache requirements |
| Có thể dùng độc lập | Có | Có |

### 12.1. @CacheableTask không tự làm configuration cache compatible

Một task có @CacheableTask vẫn có thể phá configuration cache nếu @TaskAction giữ references tới **Project**, **Gradle** mutable model hoặc truy cập những non-serializable objects không được hỗ trợ.

Lab dùng một custom DefaultTask với managed Properties và utility Java thuần để hạn chế các sai lầm này, nhưng vẫn nên chạy configuration-cache checks riêng.

### 12.2. Kiểm tra hai tính năng độc lập

~~~bash
./gradlew generateIndex --build-cache
./gradlew generateIndex --configuration-cache
./gradlew clean generateIndex --build-cache --configuration-cache
~~~

Ở những Gradle versions hỗ trợ, hãy xem cả hai states. Một task có thể FROM-CACHE trong một invocation nhưng Gradle vẫn phải chạy configuration mới vì configuration cache invalid; hai kết quả không mâu thuẫn.

### 12.3. Không bắt giữ Project trong @TaskAction

Anti-pattern:

~~~groovy
tasks.register('badTask') {
    doLast {
        println project.projectDir
    }
}
~~~

Đây chỉ là đoạn **phản ví dụ**; closure task action đọc Project mutable model, có thể không tương thích configuration cache. Với cacheable custom task, lấy giá trị cần thiết trong configuration rồi chuyển vào **Property** có annotation, như heading trong lab.

### 12.4. Configuration cache không sửa hidden inputs

Ngay cả khi Gradle reuse configuration, nếu @TaskAction đọc System.getenv mà không model, task output cache vẫn có thể sai. Hai cơ chế cần được kiểm thử riêng.

---

## 13. Incremental task execution cùng build cache

### 13.1. Một task cacheable không nhất thiết incremental

Lab **GenerateIndex** luôn duyệt toàn bộ src/notes khi nó phải execute. Đây là thiết kế **full rebuild deterministic**, đúng và đủ cho dataset nhỏ.

@CacheableTask giúp reuse output khi đã có cache entry. Nếu input thay đổi nhẹ và cache miss, task sẽ xử lý lại tất cả files; điều này không phải lỗi của cache.

### 13.2. Khi nào cần InputChanges?

Với một task xử lý hàng chục nghìn files và tạo output riêng cho từng input, dùng Gradle **InputChanges** có thể tiết kiệm việc xử lý unchanged files. Một design:

~~~java
@Incremental
@InputFiles
@PathSensitive(PathSensitivity.RELATIVE)
public abstract ConfigurableFileCollection getSources();

@TaskAction
public void transform(InputChanges changes) {
    if (!changes.isIncremental()) {
        // Xây lại toàn bộ output từ source hiện tại.
    } else {
        // Xử lý ADDED/MODIFIED, xóa outputs cho REMOVED.
    }
}
~~~

Đây là **fragment khái niệm**, chưa có class đầy đủ và output mapping. Không copy vào lab GenerateIndex nếu bạn chưa thiết kế per-file outputs.

### 13.3. FROM-CACHE và InputChanges

Nếu task output được restore FROM-CACHE, @TaskAction không chạy, nên InputChanges không cần xử lý gì. Nếu cache miss/task phải chạy và Gradle không có incremental history hợp lệ, action phải làm full rebuild.

Một incremental task không được giả định **changes.isIncremental() luôn true**.

### 13.4. Stale outputs khi files bị xóa

Nếu source **a.txt** bị xóa, incremental task phải xóa generated **a.out** hoặc rebuild output directory theo chính sách. Nếu không, stale files có thể còn trong cache snapshot và gây lỗi downstream.

Lab tạo **một file index.txt từ toàn bộ input tree**, nên full render luôn bỏ những entries có file nguồn đã xóa; không phải tự xóa một generated file cho từng input.

---

## 14. Functional testing và Gradle TestKit

### 14.1. Vì sao chỉ test IndexBuilder chưa đủ?

Unit test IndexBuilder chứng minh output đúng cho inputs cụ thể, nhưng không chứng minh:
- @InputDirectory được Gradle fingerprint đúng.
- @Input heading làm key thay đổi.
- @OutputFile được Gradle snapshot/restore.
- Task type thực sự cacheable.
- @PathSensitive(RELATIVE) cho cache relocation.
- Không có overlapping outputs hoặc task validation errors.

Cần một **functional test** chạy Gradle build thật, hoặc tối thiểu một command-based integration test từ checkout sạch.

### 14.2. Test matrix tối thiểu

| Test | Các bước | Expected |
| --- | --- | --- |
| First execution | clean/empty cache, generateIndex --build-cache | Output đúng, task execute |
| Up-to-date | Chạy lại không đổi inputs | UP-TO-DATE |
| Cache restore | clean rồi generateIndex --build-cache | FROM-CACHE nếu entry available; bytes đúng |
| Changed @Input | Đổi heading | Task execute/cache key mới hoặc hit entry đúng |
| Changed file content | Sửa intro.txt | Output đổi tương ứng |
| Added file | Thêm advanced/cache.txt | Index có thêm entry đúng |
| Removed file | Xóa file nguồn | Index không giữ entry cũ |
| Output tampering | Sửa index.txt | Restore/re-execute, content đúng |
| Relocation | Copy project sang root khác, share cache | Output giống, có thể FROM-CACHE |
| Negative task contract | Bỏ output property/config sai | Gradle validation failure có ý nghĩa |

### 14.3. TestKit với GradleRunner

Gradle TestKit hỗ trợ **GradleRunner** chạy fixture project ở thư mục tạm, có thể assert TaskOutcome:

~~~java
BuildResult result = GradleRunner.create()
        .withProjectDir(fixtureDirectory)
        .withArguments("generateIndex", "--build-cache")
        .build();

assertEquals(
        TaskOutcome.SUCCESS,
        result.task(":generateIndex").getOutcome()
);
~~~

Đây là **fragment cho JUnit/TestKit**, chưa phải class độc lập: fixtureDirectory phải là một project đã có settings/buildSrc/task, imports và JUnit dependencies phù hợp. Khi test cache restore, assert **TaskOutcome.FROM_CACHE** nếu fixture dùng cùng cache và entry có sẵn; khi test local history, assert **TaskOutcome.UP_TO_DATE**. Đừng hardcode TaskOutcome.FROM_CACHE ở first run khi cache có thể đã được seed bởi test trước khác.

### 14.4. Tránh chia sẻ cache state ngẫu nhiên giữa tests

Functional tests muốn kiểm tra first execution nên dùng một Gradle User Home/cache isolated hoặc unique inputs để không bất ngờ FROM-CACHE do test khác. Muốn kiểm tra cross-workspace reuse, cần chủ đích chia sẻ cache nhưng tách project build directories.

### 14.5. Test relocatability và reproducibility

Một test tốt:
1. Tạo fixture A ở đường dẫn khác fixture B.
2. Tạo cùng source bytes và task configuration ở cả hai.
3. Run A để seed cache.
4. Run B dùng cùng cache.
5. Assert B output bytes đúng; nếu dùng GradleRunner và cache state được kiểm soát, kiểm tra FROM_CACHE.
6. Sửa một input trên B; assert output mới tương ứng.
7. Kiểm tra không có absolute path A/B trong output.

**Không chỉ assert cache hit mà bỏ kiểm tra nội dung**. Một cache hit sai vẫn có thể cho TaskOutcome.FROM_CACHE nhưng tạo artifact lỗi.

### 14.6. Plugin code version trong test

Nếu buildSrc source thay đổi, implementation classpath của task có thể thay và key khác. Trong test relocation, đảm bảo hai fixtures dùng **cùng implementation source/binary** để so Gradle build cache, không phải thử hai code versions khác nhau.

---

## 15. CI và local/remote cache

### 15.1. Bật cache bằng CLI

~~~bash
./gradlew generateIndex --build-cache
~~~

Bật caching cho invocation hiện tại, phù hợp khi thử và chưa muốn đổi config của repository.

### 15.2. Bật trong gradle.properties

~~~properties
org.gradle.caching=true
~~~

Giờ các builds sẽ thử dùng cache theo cấu hình, trừ khi gọi **--no-build-cache** hoặc có điều kiện khác. **Đừng đưa org.gradle.caching=true vào một file task input**, nó là cấu hình Gradle invocation.

### 15.3. Local cache

Gradle có local build cache thường được quản lý dưới **Gradle User Home**. Nó có thể chứa outputs của tasks từ nhiều workspaces cùng máy. Nếu một developer dùng **GRADLE_USER_HOME** khác hoặc xóa cache, một expected FROM-CACHE có thể trở thành execution thật.

### 15.4. Remote cache

Tổ chức có thể cấu hình remote build cache service để chia sẻ outputs giữa CI agents/developers. Lợi ích:
- CI build có thể seed cache cho developer.
- Các CI jobs ở máy khác có thể reuse costly compilation/report generation.
- Cache key và normalized inputs giúp tránh phụ thuộc vào absolute workspace paths.

Cần policy:
- Authentication, TLS, access controls.
- Trusted writers và bảo vệ cache poisoning.
- Không cache sensitive secrets trong outputs.
- Push permissions (thường chỉ CI tin cậy được push).
- Data retention/eviction.
- Network latency vs task execution cost.

**@CacheableTask không tự đăng ký remote cache URL hoặc credentials**. Đó là cấu hình build cache riêng ở settings/CI.

### 15.5. Không phải task càng nhiều caching càng nhanh

Một task Copy/Sync có output vài KB, thực thi trong 10 ms, có thể tốn hơn để fingerprint/archive/download cache. Hãy ưu tiên expensive deterministic tasks và đo thời gian bằng build scans/profiler.

### 15.6. Build cache không giống dependency cache

Gradle dependency cache giữ downloaded artifacts/metadata của external modules. Build cache giữ **task outputs** dựa vào cache keys. Xóa dependency cache, local build cache và build/ directory là ba thao tác khác nhau với tác động khác nhau.

### 15.7. CI không được tin vào UP-TO-DATE ở máy dev

Một clean CI workspace có thể không có local task history nhưng vẫn dùng remote build cache; task FROM-CACHE khi entry valid, hoặc execute và lưu entry. Pipeline cần **chạy tests/validation/quality checks** dù các artifact build được cache, và không coi output đã restore như bằng chứng tests hiện tại đã được phát hiện đúng nếu task graph không kéo các tasks verification tương ứng.

---

## 16. Lỗi phổ biến làm cache sai hoặc vô hiệu

| Triệu chứng | Lý do có thể | Cách khắc phục |
| --- | --- | --- |
| Đã có @CacheableTask nhưng không có FROM-CACHE | Chưa bật --build-cache/org.gradle.caching | Bật cache, chạy seed rồi clean/restore |
| Task luôn EXECUTED | Input biến động, output bị sửa/xóa, cache miss | Xem --info, kiểm input/output fingerprints |
| Task chỉ UP-TO-DATE | Output vẫn có ở workspace | Chạy clean + --build-cache để thử restore |
| FROM-CACHE nhưng nội dung sai ở máy B | Hidden absolute path/time/env input | Làm deterministic, khai báo mọi semantic input |
| Không reuse giữa workspaces | ABSOLUTE path sensitivity hoặc implementation classpath khác | RELATIVE/NONE phù hợp, kiểm rebuild/tool versions |
| Thêm empty dir làm rerun | Fingerprinting empty dir | @IgnoreEmptyDirectories nếu output không cần empty dirs |
| Dùng @NormalizeLineEndings nhưng copy raw bytes | Fingerprint coi CRLF/LF như nhau dù output khác | Bỏ normalize hoặc normalize trong action |
| Task thiếu @OutputFile/@OutputDirectory | Gradle không biết output cần snapshot | Khai báo output ownership rõ |
| Task có overlapping outputs | Hai tasks cùng ghi chung path | Tách output location hoặc aggregation task |
| Task tắt cache vì validation problem | Property getter thiếu annotation/type không hợp lệ | Sửa annotations và chạy validation |
| Task dùng System.getenv chưa khai báo | Hidden input | Đưa value vào Property @Input hoặc bỏ phụ thuộc |
| Task ghi currentTimeMillis vào output | Nondeterministic result | Bỏ timestamp hoặc tắt caching khi bắt buộc |
| Task chạy HTTP request | External state không được model | Dùng versioned artifacts/input file hoặc không cache |
| FileTree thứ tự khác giữa OS | Output order không deterministic | Sort relative paths |
| buildSrc đổi làm mất cache hits | Task implementation/classpath thay | Giữ build logic versions ổn định |
| Cache key đổi mỗi commit | Commit hash là @Input | Chỉ thêm hash nếu thực sự xuất hiện trong output |
| Task @InputFile không tồn tại | Gradle input validation fail | Tạo file đúng path hoặc @Optional phù hợp |
| Property @Internal ảnh hưởng output | False cache hit | Chuyển thành @Input hoặc file input annotation |
| Task chỉ in log mà đánh dấu @CacheableTask | Không có material output | Không cache task side effect |
| Kết quả khác theo locale | Locale.getDefault trong action | Dùng Locale.ROOT hoặc @Input locale |
| Kết quả khác theo OS newline | System.lineSeparator() | Dùng '\n' cố định hoặc model platform |
| Output ở ngoài declared directory | Gradle không snapshot đủ file | Khai báo mọi outputs, dùng layout.buildDirectory |
| Task dùng @CompileClasspath sai | Implementation change bị ignore | Dùng @Classpath/@InputFiles khi action phụ thuộc bytecode |
| Caching bị doNotCacheIf | Custom condition | Xem reason, sửa điều kiện khi hợp lý |
| UP-TO-DATE với output sai vì task khác ghi chồng | Output ownership không rõ | Tách outputs, không share directory |
| @SkipWhenEmpty làm mất header report | Task bị NO-SOURCE | Bỏ skip khi empty input vẫn phải tạo file |
| Task chạy incremental mà giữ file cũ | Không xử lý removed inputs | Xóa stale outputs, full rebuild fallback |
| Configuration cache fail dù build cache hit | Task action giữ Project mutable model | Dùng managed Properties và task isolation |
| Remote cache hit từ nguồn không tin cậy | Cache poisoning/misconfigured trust | Giới hạn writers, xác minh artifacts và policies |

### 16.1. Checklist debug ngắn

1. Kiểm tra task được chọn và task action thật sự chạy lúc nào.
2. Kiểm tra **@CacheableTask** đúng trên class thực tế.
3. Xem **--build-cache** hoặc gradle.properties.
4. Xem các @Input/@Output properties và normalizations.
5. Chạy **generateIndex --build-cache --info** lần đầu.
6. Chạy lần hai không đổi, quan sát **UP-TO-DATE**.
7. Chạy **clean generateIndex --build-cache --info**, quan sát **FROM-CACHE** nếu cache entry tồn tại.
8. Kiểm tra bytes report trước/sau, không chỉ state.
9. Sửa heading và một file input, chắc chắn output đổi.
10. Kiểm tra task không đọc network/time/locale/absolute path.
11. Kiểm tra không có overlapping outputs và validation problem.
12. Test cache ở workspace mới; phân biệt cache miss hợp lệ với incorrect task contract.

---

## 17. Bài tập có đáp án

### Bài 1 — @CacheableTask đã đủ chưa?

**Đáp án:** chưa. Cần build cache enabled, declared inputs/outputs chính xác, deterministic/relocatable outputs và cache entry matching key; vẫn có thể execute nếu miss.

### Bài 2 — UP-TO-DATE và FROM-CACHE khác nhau?

**Đáp án:** UP-TO-DATE dựa vào task history/output hiện có trong workspace. FROM-CACHE restore outputs từ build cache theo key khi local outputs không reusable.

### Bài 3 — File output chưa khai báo

Task tạo build/generated/index.txt nhưng không @OutputFile.

**Đáp án:** Gradle không có đầy đủ output contract để snapshot/cache chính xác; thêm RegularFileProperty @OutputFile.

### Bài 4 — Heading ảnh hưởng output

Heading được set trong task nhưng getter @Internal.

**Đáp án:** sai. Vì heading thay đổi bytes output, phải đánh dấu @Input; @Internal sẽ tạo nguy cơ cache hit sai.

### Bài 5 — @PathSensitive(ABSOLUTE) ở hai workspaces

**Đáp án:** absolute path khác làm input fingerprint khác, cản trở cross-workspace reuse. Dùng RELATIVE cho source tree khi relative paths quyết định output.

### Bài 6 — Dùng RELATIVE nhưng action ghi absolute path

**Đáp án:** không an toàn. Gradle có thể coi inputs giống nhau khi outputs khác; dùng relative path trong output hoặc model absolute path như input khi thật sự là semantics.

### Bài 7 — Duyệt directory không sort

**Đáp án:** filesystem traversal order không phải hợp đồng. Sort theo stable relative paths trước khi ghi output.

### Bài 8 — @NormalizeLineEndings là luôn tốt?

**Đáp án:** không. Chỉ dùng khi task output không phụ thuộc CRLF/LF của input; raw copy cần giữ khác biệt hoặc tự normalize bytes trong action.

### Bài 9 — Một task chỉ in "Done"

**Đáp án:** không có output file meaningful để cache; @CacheableTask không làm side effects/log trở thành artifact reusable.

### Bài 10 — Hai tasks ghi chung output directory

**Đáp án:** Gradle có thể disable caching vì overlapping outputs. Tách directories, tạo aggregation task nếu cần ghép.

### Bài 11 — Có thể cache kết quả sau clean?

**Đáp án:** có khi build cache enabled và entry matching key còn tồn tại. Output được restore FROM-CACHE mà không chạy @TaskAction.

### Bài 12 — --no-build-cache có tắt up-to-date check?

**Đáp án:** không tự động. Up-to-date là cơ chế khác; task vẫn có thể UP-TO-DATE.

### Bài 13 — --rerun-tasks dùng khi nào?

**Đáp án:** để buộc task chạy lại khi điều tra output correctness hoặc loại trừ up-to-date/cache reuse, không phải cấu hình tối ưu CI thường trực.

### Bài 14 — FileTree có order bảo đảm không?

**Đáp án:** không nên dựa vào file traversal order. Thuật toán tạo index phải sort explicit.

### Bài 15 — Gradle @Classpath khác @InputFiles?

**Đáp án:** @Classpath dùng normalization cho Java runtime classpath, bao gồm lookup order và JAR semantics; @InputFiles dùng file snapshots/path sensitivity. Chọn theo cách task tiêu thụ dependency files.

### Bài 16 — Khi nào @CompileClasspath nguy hiểm?

**Đáp án:** nếu task output phụ thuộc implementation của class/JAR, vì compile classpath normalization có thể bỏ qua implementation-only changes. Khi đó cần @Classpath hoặc file inputs phù hợp.

### Bài 17 — Task @SkipWhenEmpty và empty source folder?

**Đáp án:** task có thể NO-SOURCE. Nếu vẫn phải tạo header report, không dùng @SkipWhenEmpty như lab.

### Bài 18 — InputChanges có thay @CacheableTask không?

**Đáp án:** không. @Incremental/InputChanges cho xử lý delta; @CacheableTask cho reuse outputs. Hai tính năng độc lập và có thể phối hợp.

### Bài 19 — Task class có time-based output

**Đáp án:** không deterministic; không cache trừ khi dữ liệu time là một semantic input hợp lệ, được capture và có reason để chấp nhận cache misses. Tốt hơn bỏ timestamp nếu không cần.

### Bài 20 — Class Java thuần nào trong lab chạy bằng javac?

**Đáp án:** IndexBuilder.java; GenerateIndex.java cần Gradle API classpath và được buildSrc compile.

### Bài 21 — Stdout từ IndexBuilder là gì?

Với guide.txt=gradle và intro.txt=hello:

~~~text
# CACHE DEMO
guide.txt = GRADLE
intro.txt = HELLO
~~~

### Bài 22 — Tại sao dùng Locale.ROOT?

**Đáp án:** để uppercasing không thay đổi theo locale mặc định của máy, giúp deterministic output và không có hidden environment input.

### Bài 23 — @InputDirectory và @IgnoreEmptyDirectories hợp nhau?

**Đáp án:** có, khi task chỉ xử lý regular files và không sinh output từ empty folder presence. Nếu output cần danh sách empty folders, không được ignore.

### Bài 24 — File cache key có dùng output absolute path?

**Đáp án:** output property name là thành phần quan trọng của key, còn output location thường không được coi là semantic input. Không đưa output absolute path vào bytes nếu muốn relocatability mà không model nó.

### Bài 25 — Cacheable task tự dùng remote cache?

**Đáp án:** không. Cần remote build cache được cấu hình, network/auth/push policy và cache entry; local caching có thể hoạt động độc lập.

### Bài 26 — @Internal cho một option thay đổi output?

**Đáp án:** sai. Property đó phải @Input hoặc annotated input type phù hợp.

### Bài 27 — Task dùng secret để ký artifact

**Đáp án:** cân nhắc không cache public/shared outputs có dữ liệu nhạy cảm hoặc key/nonce; ký thường liên quan secrets, security và nondeterminism. Thiết kế credential handling riêng, có thể disable caching và dùng task hậu xử lý.

### Bài 28 — Cache miss sau khi nâng buildSrc source?

**Đáp án:** task implementation/classpath có thể thay, dẫn đến key mới. Không coi đó là bug khi nâng implementation.

### Bài 29 — Build cache và configuration cache là một?

**Đáp án:** không. Build cache lưu outputs của tasks; configuration cache lưu kết quả configuration phase. Một tính năng bật không có nghĩa tính năng kia tương thích/đã bật.

### Bài 30 — Test relocating cần assert gì?

**Đáp án:** output bytes giống nhau ở hai workspaces, input snapshots đúng, không absolute path leakage, và FROM-CACHE khi đã seed/cache shared với key đúng.

---

## 18. Checklist trước khi phát hành cacheable task/plugin

- [ ] Có lý do performance rõ để cache task này không?
- [ ] Task type cụ thể được annotate @CacheableTask đúng chỗ?
- [ ] Caching chỉ được bật khi task output deterministic và relocatable?
- [ ] Tất cả semantic config inputs annotated @Input hoặc @Nested phù hợp?
- [ ] Input files/dirs được khai báo với đúng File/DirectoryProperty types?
- [ ] PathSensitivity có phản ánh cách task dùng paths?
- [ ] Source tree dùng RELATIVE, independent single file dùng NONE khi phù hợp?
- [ ] Task action không ghi absolute path/current time/default locale/random vào output?
- [ ] Java Charset/Locale được cố định nếu ảnh hưởng output?
- [ ] Thứ tự duyệt Files/Maps/archives stable hay được sort?
- [ ] Không dùng @NormalizeLineEndings nếu output vẫn khác theo CRLF/LF?
- [ ] Mọi outputs được khai báo @OutputFile/@OutputDirectory?
- [ ] Không có hai tasks cùng ghi/chia sẻ output directory không kiểm soát?
- [ ] Không viết outputs bên ngoài declared locations?
- [ ] Input/Output values được set qua Provider API trong configuration?
- [ ] Task action tránh đọc Project mutable model/configuration state?
- [ ] Không có untracked external network/system environment dependencies?
- [ ] Task không gửi notification/deploy/publish như side effect được cache?
- [ ] Có functional test output correctness từ fresh checkout?
- [ ] Có test UP-TO-DATE ở lượt thứ hai?
- [ ] Có test clean + FROM-CACHE khi cache entry sẵn?
- [ ] Có test changed @Input, changed file và deleted file?
- [ ] Có test thay đổi output file từ bên ngoài?
- [ ] Có test relocatability bằng hai workspace roots?
- [ ] Có kiểm tra Gradle validation và --info cache reason?
- [ ] Build cache và configuration cache được test riêng?
- [ ] Có cache trust/remote write policy nếu dùng remote?
- [ ] Java/Gradle/plugin versions hỗ trợ task implementation?
- [ ] Không lẫn lộn cached output với correctness/security/quality gate?
- [ ] Documentation nêu rõ khi nào task chạy, skip hoặc restore outputs?

## Tài liệu Gradle chính thức

- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): enable build cache, @CacheableTask, cacheIf/doNotCacheIf, inputs/outputs và debugging.
- [Gradle — Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html): cache key, repeatable outputs, stable inputs, normalization, relocatability, overlapping outputs và task reuse.
- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): annotations, task validation, input/output snapshots và up-to-date checks.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_builds.html): @InputFiles, @Classpath, @CompileClasspath, @SkipWhenEmpty, InputChanges.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): PathSensitivity.NONE/RELATIVE, lazy registration, modeling task inputs/outputs.
- [Gradle — CacheableTask Javadoc](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/CacheableTask.html): annotation contract, reproducible/relocatable outputs.
- [Gradle — Task Output Caching](https://docs.gradle.org/current/userguide/build_cache.html#sec:task_output_caching): @CacheableTask và cache keys.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): phân biệt configuration graph reuse và task output reuse.
- [Gradle — Gradle TestKit](https://docs.gradle.org/current/userguide/test_kit.html): GradleRunner, functional testing, task outcomes.
- [Gradle — Writing Gradle Plugins](https://docs.gradle.org/current/userguide/custom_plugins.html): custom task types, plugin architecture.
- [Gradle — Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): Gradle Wrapper, Java daemon và toolchain versions.

**Kết luận:** Thiết kế một task thực sự cacheable không đơn giản là thêm **@CacheableTask**. Bạn phải xác định chính xác **mọi input và output**, viết thuật toán **deterministic**, normalize đường dẫn/file semantics để **relocatable**, tách side effects không thể cache và kiểm chứng bằng build thật. **UP-TO-DATE** nghĩa là task có thể bỏ qua nhờ trạng thái output trong workspace; **FROM-CACHE** nghĩa là Gradle thực sự phục hồi output từ một cache entry matching key. Chỉ khi cả **correctness, relocatability và task contracts** đều được kiểm chứng thì build cache mới vừa nhanh vừa đáng tin.