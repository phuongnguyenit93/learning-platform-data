# Tác động của nội dung tệp, đường dẫn và thuộc tính đến trạng thái task trong Gradle

## 1. Tổng quan trong chủ đề Build tăng dần

**Build tăng dần** (*incremental build*) là khả năng Gradle tránh tính lại những kết quả còn hợp lệ. Một lần chạy Gradle có thể chứa task được thực thi, task `UP-TO-DATE`, task `FROM-CACHE`, task `NO-SOURCE` hoặc task `SKIPPED`. Điều quyết định không phải “source code trông có vẻ giống nhau” mà là **hợp đồng inputs/outputs** và thông tin thực thi Gradle lưu được.

Khi tác giả custom task khai sai inputs, có hai nhóm lỗi:
- **Chạy lại thừa:** sửa một file không liên quan hoặc chuyển checkout root path cũng làm task chạy lại.
- **Bỏ qua sai:** file/flag ảnh hưởng output đã đổi nhưng task vẫn `UP-TO-DATE`, dẫn tới artifact cũ.

Bài này giải thích ba nguồn ảnh hưởng lớn nhất đến trạng thái task:

1. **Nội dung tệp:** bytes của source, template, config, resource hoặc JAR dependency.
2. **Đường dẫn:** full path, relative path, file basename hoặc việc bỏ qua path.
3. **Thuộc tính:** scalar value như `mode`, `recipient`, `targetJavaVersion`, compiler options, charset, environment-derived setting và tool version.

Các yếu tố khác cũng quan trọng: **task implementation**, task actions, declared outputs, build cache, Gradle history và điều kiện `onlyIf`.

### 1.1. Mục tiêu bài học

Sau khi học, bạn sẽ:
- Hiểu input/output fingerprint và dự đoán kết quả up-to-date checks.
- Dùng đúng `@Input`, `@InputFile`, `@InputFiles`, `@InputDirectory`, `@OutputFile`, `@OutputDirectory`.
- Chọn đúng `PathSensitivity.ABSOLUTE`, `PathSensitivity.RELATIVE`, `PathSensitivity.NAME_ONLY`, `PathSensitivity.NONE`.
- Phân biệt file contents, file path và `Property<String>`; tránh undeclared inputs.
- Hiểu normalization của line endings, empty directories và Java classpath.
- Chạy ví dụ **Gradle Groovy DSL và Java 17** có kết quả stdout chính xác.
- Dùng `InputChanges` để thực thi tăng dần từng file, bao gồm thêm/sửa/xóa.
- Nhận diện `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, `SKIPPED` và các nguyên nhân task chạy lại.
- Debug bằng `--info`, `--rerun-tasks`, so sánh output contents và kiểm thử nhiều tình huống.

Bài dùng Gradle Wrapper tương thích với JDK 17. Linux/macOS chạy `./gradlew`; Windows PowerShell chạy `.\gradlew.bat`.

## 2. Task inputs và outputs: mô hình đơn giản

Một task thường biến đổi:

~~~text
Input files + input properties + implementation
                     |
                     v
                Task action
                     |
                     v
              Output file / dir
~~~

Ví dụ:

~~~text
inputs/template.txt          = "Hello, {name}!\n"
recipient                    = "Gradle"
prefix                       = "Result: "
task                         = renderMessage
build/generated/message.txt  = "Result: Hello, Gradle!\n"
~~~

Gradle ghi input fingerprint trước khi chạy task, rồi output snapshot sau khi task hoàn thành thành công. Ở lần sau, Gradle so sánh:
- Tên và giá trị input properties.
- Input files và những thành phần path/content mà normalization policy yêu cầu.
- Task action/implementation fingerprint.
- Output properties và trạng thái outputs đã có.
- Điều kiện execution khác như forced rerun, skip predicates và cache.

Nếu còn tương đương, Gradle có thể không chạy TaskAction:

~~~text
> Task :renderMessage UP-TO-DATE
~~~

**Đó không phải một bài kiểm thử nghiệp vụ.** Gradle tin vào hợp đồng bạn khai. Nếu task action đọc thứ gì đó không được khai input, snapshot không thể bảo đảm kết quả chính xác.

### 2.1. Build tăng dần ở cấp task không đòi bật build cache

Gradle có up-to-date checking theo mặc định. Một custom task có input/output declarations hợp lệ có thể `UP-TO-DATE` dù bạn không chạy `--build-cache`.

### 2.2. Task không khai output

~~~groovy
tasks.register('printHello') {
    doLast {
        println 'Hello'
    }
}
~~~

Task này chỉ in console, không khai output. Gradle không có một output artifact để xác minh đã làm xong, nên task thường chạy mỗi lần được yêu cầu. Không khai một output file “giả” chỉ để ép nó `UP-TO-DATE`. Nếu có file thật được tạo, phải khai chính file đó.

### 2.3. Fingerprint không chỉ là file hash

Ngay cả khi input bytes không đổi, Gradle có thể thấy task implementation đã đổi do bạn sửa custom task source/build logic. Nếu output thiếu, bị sửa ngoài Gradle hoặc một configuration property đổi, task cũng có lý do chạy lại.

### 2.4. Tối ưu fingerprint dựa trên metadata

Gradle snapshot file contents nhưng có thể tái sử dụng fingerprint cũ khi metadata như `lastModified` và `size` cho thấy file chưa thay. Nếu một công cụ sửa bytes mà cố giữ cả mtime/size không đổi, Gradle có thể không nhìn thấy thay đổi trong vài tình huống. **Không tự giả mạo mtime** để tránh Gradle kiểm tra file; điều đó làm build thiếu tin cậy.

## 3. Nội dung tệp thay đổi như thế nào?

Giả sử file `inputs/template.txt` ban đầu có:

~~~text
Hello, {name}!
~~~

Đầu ra:

~~~text
Result: Hello, Gradle!
~~~

Sau khi sửa file thành:

~~~text
Welcome, {name}!
~~~

thì task đọc nội dung mới phải tạo:

~~~text
Result: Welcome, Gradle!
~~~

Nếu input được khai `@InputFile`, Gradle nhận diện input file content changed và xét task lại.

| Thay đổi | Tác động điển hình |
| --- | --- |
| Sửa text, thêm/xóa một dòng | File contents fingerprint khác, task phải xét lại |
| Đổi charset bytes | Có thể khiến fingerprint khác |
| Đổi CRLF↔LF | Thường là contents khác, trừ normalization đặc biệt |
| Chỉ đổi mtime, bytes y hệt | Không nhất thiết out-of-date |
| Xóa required input file | Input validation có thể fail |
| Sửa file mà task action đọc nhưng không khai input | Gradle có thể `UP-TO-DATE` sai |
| Copy file sang path khác với bytes giữ nguyên | Tùy path sensitivity |
| Thêm file vào file collection | Tập inputs có thể đổi |
| Thay đổi file ngoài declared input set | Không tự ảnh hưởng task |

### 3.1. `@InputFile` không giống `@Input Property<String> path`

**Đúng** khi action cần đọc bytes của template:

~~~groovy
@InputFile
@PathSensitive(PathSensitivity.NONE)
abstract RegularFileProperty getTemplateFile()
~~~

**Sai** nếu chỉ theo dõi một chuỗi path:

~~~groovy
@Input
abstract Property<String> getTemplatePath()
~~~

Nếu `templatePath` vẫn là `inputs/template.txt` nhưng bytes bên trong thay đổi, `@Input` string value vẫn y như cũ. Gradle không tự snapshot file contents dựa trên một input string. Cần file-input property thích hợp.

**Không gắn `@Input` trực tiếp lên kiểu `File`** để thay thế file snapshot; dùng `@InputFile` hoặc `@InputDirectory`/`@InputFiles`.

### 3.2. Các annotations phổ biến

| Annotation | Kiểu thường dùng | Ý nghĩa |
| --- | --- | --- |
| `@Input` | `Property<String>`/`Property<Boolean>`, number, enum | Scalar task input |
| `@InputFile` | `RegularFileProperty` | Một file input |
| `@InputFiles` | `ConfigurableFileCollection` | File collection |
| `@InputDirectory` | `DirectoryProperty` | Input tree |
| `@OutputFile` | `RegularFileProperty` | Output file |
| `@OutputDirectory` | `DirectoryProperty` | Output directory |
| `@Nested` | Nested annotated bean | Nhóm input properties |
| `@Internal` | Property không ảnh hưởng output | Không fingerprint |
| `@Optional` | Input/output modifier | Cho phép thiếu khi hợp lệ |
| `@Incremental` | File input/dir | Hỗ trợ InputChanges |
| `@SkipWhenEmpty` | File input/dir | NO-SOURCE nếu trống theo rule |

Khai dư một input cũng có hại: task sẽ chạy lại khi thứ không ảnh hưởng kết quả thay đổi. Hãy khai **đủ và đúng**, không phải “càng nhiều inputs càng tốt”.

## 4. Đường dẫn và PathSensitivity

Gradle phân biệt path normalization với content hash. Mỗi file input có thể được so đường dẫn theo một trong bốn chính sách:

| Enum | Phần path quan tâm | Tình huống phù hợp |
| --- | --- | --- |
| `PathSensitivity.ABSOLUTE` | Toàn bộ absolute path | Rất hiếm, output thực sự phụ thuộc vị trí tuyệt đối |
| `PathSensitivity.RELATIVE` | Relative path từ input root | Source/resources tree giữ hierarchy |
| `PathSensitivity.NAME_ONLY` | Chỉ basename | Chỉ khi file/directory name đủ định danh |
| `PathSensitivity.NONE` | Bỏ qua path, vẫn xét contents | Một template/config file không dùng path |

### 4.1. ABSOLUTE: làm project khó relocatable

~~~groovy
@InputFile
@PathSensitive(PathSensitivity.ABSOLUTE)
abstract RegularFileProperty getConfig()
~~~

Nếu cùng bytes nhưng đặt file tại:
- `/home/alice/work/config.json`.
- `/agent/project/config.json`.

thì full paths khác nhau; task có thể out-of-date hoặc build cache key không tái sử dụng được giữa workspace roots. Default path sensitivity khi không khai annotation có thể là ABSOLUTE.

**Chỉ dùng ABSOLUTE** khi output thật sự phụ thuộc absolute location. Thường tốt hơn là **bỏ đường dẫn tuyệt đối khỏi output** để cache relocatable và tránh lộ thông tin máy.

### 4.2. RELATIVE: cấu trúc thư mục có nghĩa

Input:

~~~text
inputs/pages/
├── docs/intro.txt
└── guide/intro.txt
~~~

Output:

~~~text
build/upper/
├── docs/intro.txt
└── guide/intro.txt
~~~

Dù hai files có cùng basename `intro.txt`, directory path phân biệt chúng. Nếu move `docs/intro.txt` sang `archive/intro.txt` thì output mapping cũng phải đổi.

~~~groovy
@InputDirectory
@PathSensitive(PathSensitivity.RELATIVE)
abstract DirectoryProperty getInputDirectory()
~~~

Từ một checkout root khác nhưng giữ relative structure, normalized input paths có thể tương đương.

### 4.3. NAME_ONLY: đừng bỏ nhầm folder identity

`PathSensitivity.NAME_ONLY` chỉ xét file/directory names, không xét full relative hierarchy. Nếu action tạo output file dựa trên relative path, NAME_ONLY là sai. Nó dễ tạo ambiguity khi hai files ở `a/config.yml` và `b/config.yml` có cùng basename.

Chỉ chọn NAME_ONLY khi **tên đơn** thật sự đủ thông tin để xác định output và file set không có xung đột có ý nghĩa.

### 4.4. NONE: path-independent task

~~~groovy
@InputFile
@PathSensitive(PathSensitivity.NONE)
abstract RegularFileProperty getTemplateFile()
~~~

Khi task chỉ đọc bytes của file, không dùng name/path cho output, NONE là lựa chọn tốt. Di chuyển file sang thư mục khác mà giữ cùng bytes **không phải** một input change có ý nghĩa.

Nhưng **NONE không bỏ qua contents**: đổi file từ `Hello` sang `Welcome` vẫn phải xét lại.

**Không chọn NONE** nếu:
- Task đưa file name/path vào generated report.
- Output directory tree phụ thuộc input relative path.
- Tên resource là part of key.
- Hai files cùng contents nhưng identity khác làm output khác.

### 4.5. Quy tắc quyết định

Với **một input file** chỉ dùng content → thường `NONE`.

Với **directory tree** cần giữ relative layout → thường `RELATIVE`.

Với **Java classpath** → dùng `@Classpath`/`@CompileClasspath` chuyên dụng.

Chỉ dùng `ABSOLUTE`/`NAME_ONLY` khi thật sự có semantics tương ứng. Path normalization không phải công cụ “bật tăng tốc”; nó là một phần của **hợp đồng kết quả**.

## 5. Thuộc tính scalar thay đổi task state

Một task có thể cần các cấu hình:

~~~text
recipient = "Gradle"
prefix    = "Result: "
mode      = "normal"
encoding  = "UTF-8"
~~~

Một `Property<String>` ảnh hưởng output nên được annotate:

~~~groovy
@Input
abstract Property<String> getRecipient()
~~~

Với Gradle Provider API:

~~~groovy
recipient.set(
    providers.gradleProperty('recipient').orElse('Gradle')
)
~~~

Lệnh `-Precipient=Lan` làm input value khác baseline. Gradle có thể chạy lại task ngay cả khi input template bytes/path giữ nguyên.

### 5.1. Input ẩn từ environment

**Sai về input model:**

~~~groovy
doLast {
    def mode = System.getenv('BUILD_MODE')
    // mode ảnh hưởng output nhưng không được khai task input.
}
~~~

**Tốt hơn:** lấy mode bằng `providers.environmentVariable('BUILD_MODE')`, gán vào `@Input Property<String>` của typed task. Provider giúp giữ ngữ nghĩa lazy/configurable; điều kiện chính là **giá trị ảnh hưởng output được khai trong input model**.

### 5.2. Task property nào không là input?

Nếu `verbose` chỉ thay logging verbosity nhưng không thay artifact bytes, khai nó `@Input` có thể gây rerun vô ích. Có thể dùng `@Internal`/`@Console` phù hợp. Ngược lại, đánh `@Internal` cho mode ảnh hưởng output tạo nguy cơ stale result.

### 5.3. Nested properties và tính đầy đủ

Nếu task có nhiều options (language, compress, includeHeaders), có thể dùng `@Nested` bean với annotated getters bên trong. Đừng cho một arbitrary mutable object vào `@Input` mà không có serialization/fingerprint model đáng tin.

### 5.4. Task implementation cũng có dấu vân tay

Sửa class, task action hoặc implementation classpath có thể làm Gradle coi task khác logic trước đó. Đây là lý do khi debug cần xem `--info`: task re-execution có thể do implementation change chứ không do template content.

## 6. Bài thực hành hoàn chỉnh: Groovy DSL và Java 17

Bài lab gồm:
- Một Gradle task tạo UTF-8 file từ template.
- Input file `@PathSensitive(NONE)`.
- Hai scalar `@Input` là recipient và prefix.
- Output `@OutputFile`.
- Một Java 17 program in chính xác output file.
- Những thao tác có kiểm soát để đổi contents, path, properties.

### 6.1. Cấu trúc

~~~text
incremental-lab/
├── settings.gradle
├── build.gradle
├── inputs/template.txt
├── src/main/java/demo/MessageViewer.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Yêu cầu Gradle Wrapper tương thích JDK17. Nếu chưa có wrapper, sử dụng Gradle đã cài và chạy `gradle wrapper` để tạo bộ files rồi commit. Không cần external dependencies/plugins ngoài.

### 6.2. `settings.gradle`

~~~groovy
rootProject.name = 'incremental-lab'
~~~

### 6.3. `inputs/template.txt`

~~~text
Hello, {name}!
~~~

Lưu UTF-8, có newline cuối file.

### 6.4. `build.gradle` — toàn bộ

~~~groovy
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path

import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

plugins {
    id 'base'
}

abstract class RenderMessageTask extends DefaultTask {

    @InputFile
    @PathSensitive(PathSensitivity.NONE)
    abstract RegularFileProperty getTemplateFile()

    @Input
    abstract Property<String> getRecipient()

    @Input
    abstract Property<String> getPrefix()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void render() {
        Path input = getTemplateFile().get().asFile.toPath()
        String template = Files.readString(
            input,
            StandardCharsets.UTF_8
        ).stripTrailing()

        String result = getPrefix().get()
            + template.replace('{name}', getRecipient().get())
            + '\n'

        Path output = getOutputFile().get().asFile.toPath()
        Files.createDirectories(output.getParent())
        Files.writeString(
            output,
            result,
            StandardCharsets.UTF_8
        )
    }
}

tasks.register('renderMessage', RenderMessageTask) {
    group = 'documentation'
    description = 'Render a UTF-8 message'

    def path = providers.gradleProperty('templatePath')
        .orElse('inputs/template.txt')
        .get()

    templateFile.set(layout.projectDirectory.file(path))
    recipient.set(
        providers.gradleProperty('recipient').orElse('Gradle')
    )
    prefix.set(
        providers.gradleProperty('prefix').orElse('Result: ')
    )
    outputFile.set(
        layout.buildDirectory.file('generated/message.txt')
    )
}
~~~

**Giải thích:**

1. Core plugin `base` cung cấp task `clean`, không cần tải external dependencies.
2. `RenderMessageTask` là custom typed task.
3. `@InputFile` khiến Gradle snapshot template bytes.
4. `PathSensitivity.NONE` hợp lệ vì action không dùng file path/name khi tính result.
5. `recipient` và `prefix` có `@Input`; đổi giá trị phải ảnh hưởng task state.
6. `outputFile` là `@OutputFile` được Gradle theo dõi và tạo dưới `build/`.
7. `Files.readString/writeString(...UTF_8)` bỏ phụ thuộc charset mặc định.
8. `String.stripTrailing()` là Java 11+ API, chạy trên JDK17 và bỏ trailing whitespace trong template.
9. TaskAction thêm đúng một `\n` ở cuối output.
10. `tasks.register` không eager-create task.
11. `templatePath` dùng chọn file input; output không nhúng source path.
12. Không ghi source tree. Không có network/timestamp/random input ẩn.
13. Không đánh dấu `@CacheableTask` chỉ vì muốn cache hits; phần này học up-to-date checking trước.

### 6.5. `src/main/java/demo/MessageViewer.java`

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class MessageViewer {

    private MessageViewer() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Expected exactly one input file"
            );
        }

        String message = Files.readString(
            Path.of(args[0]),
            StandardCharsets.UTF_8
        );

        System.out.print(message);
    }
}
~~~

Đây là Java 17 program độc lập với Gradle API. Nó in **đúng bytes được giải mã UTF-8** từ file output (không tự thêm newline), giúp kiểm tra kết quả mà không dự đoán Gradle log.

### 6.6. Chạy đầu tiên

~~~bash
./gradlew renderMessage --console=plain
javac --release 17 -encoding UTF-8 -d out src/main/java/demo/MessageViewer.java
java -cp out demo.MessageViewer build/generated/message.txt
~~~

**Stdout chính xác của Java program**:

~~~text
Result: Hello, Gradle!
~~~

Ở lần đầu khi output chưa có, Gradle thường chạy task để tạo `build/generated/message.txt`. File có LF cuối.

### 6.7. Chạy lại với cùng inputs

~~~bash
./gradlew renderMessage --console=plain
~~~

Nếu task history/output hợp lệ, Gradle thường báo:

~~~text
> Task :renderMessage UP-TO-DATE
~~~

Task action không chạy. Điều này không đòi build cache.

### 6.8. Sửa file contents, giữ path

Sửa `inputs/template.txt` thành:

~~~text
Welcome, {name}!
~~~

Chạy:

~~~bash
./gradlew renderMessage --info
java -cp out demo.MessageViewer build/generated/message.txt
~~~

**Stdout Java**:

~~~text
Result: Welcome, Gradle!
~~~

Bởi content input đổi, Gradle phải xét task lại.

### 6.9. Đổi recipient property

Vẫn giữ template `Welcome, {name}!`:

~~~bash
./gradlew renderMessage -Precipient=Lan --info
java -cp out demo.MessageViewer build/generated/message.txt
~~~

**Stdout Java**:

~~~text
Result: Welcome, Lan!
~~~

Đổi prefix:

~~~bash
./gradlew renderMessage -Precipient=Lan -Pprefix=Note: --info
java -cp out demo.MessageViewer build/generated/message.txt
~~~

**Stdout Java**:

~~~text
Note: Welcome, Lan!
~~~

Input file bytes/path không đổi; scalar `@Input` values đổi nên output cần được tạo lại.

### 6.10. Chuyển input path, giữ bytes

Tạo `inputs/template-copy.txt` có cùng bytes:

~~~bash
cp inputs/template.txt inputs/template-copy.txt
~~~

PowerShell:

~~~powershell
Copy-Item 'inputs/template.txt' 'inputs/template-copy.txt'
~~~

Để đảm bảo so sánh chỉ là path change, chạy một lần với default recipient/prefix rồi chọn copy:

~~~bash
./gradlew renderMessage --info
./gradlew renderMessage -PtemplatePath=inputs/template-copy.txt --info
~~~

Task có `@PathSensitive(NONE)`, action không in path/name vào output, hai files cùng content. Do đó path-only change **không nhất thiết** làm task chạy; với mọi yếu tố khác không đổi, task có thể `UP-TO-DATE`.

Nếu sửa code task hoặc xóa output giữa hai lệnh, bạn đã đổi thêm yếu tố khác nên không được kết luận từ path sensitivity đơn thuần.

### 6.11. Xóa output

~~~bash
./gradlew clean renderMessage
~~~

Hoặc tự xóa riêng `build/generated/message.txt` (khi không có dữ liệu người dùng cần giữ). Gradle phải tạo output lại, hoặc phục hồi nếu task eligible cho cache và có hit. Task lab không bật cacheable opt-in nên thường thực thi.

### 6.12. Bảng dự đoán của lab

| Hành động | Kết quả có ý nghĩa |
| --- | --- |
| Run đầu | File chứa `Result: Hello, Gradle!` |
| Run lại nguyên trạng | `UP-TO-DATE` nếu history hợp lệ |
| Đổi template thành Welcome | File chứa `Result: Welcome, Gradle!` |
| `-Precipient=Lan` | File chứa `Result: Welcome, Lan!` |
| `-Precipient=Lan -Pprefix=Note:` | File chứa `Note: Welcome, Lan!` |
| `-PtemplatePath` chọn file cùng bytes | Có thể `UP-TO-DATE` với NONE |
| Xóa output | Task chạy lại hoặc cache restore |
| `--rerun-tasks` | Task action được chạy lại |

Không cần assert toàn bộ Gradle task logs là stdout cố định. Các chuỗi trên là **nội dung output file/Java MessageViewer**, không phải thông báo do Gradle tự in.

## 7. File collection và input directory

Task xử lý nhiều files thường cần `@InputFiles` hoặc `@InputDirectory`. Giả sử:

~~~text
inputs/pages/
├── docs/intro.txt
└── guides/setup.txt

build/upper/
├── docs/intro.txt
└── guides/setup.txt
~~~

Vì output giữ relative paths, nên dùng:

~~~groovy
@InputDirectory
@PathSensitive(PathSensitivity.RELATIVE)
abstract DirectoryProperty getSourceDirectory()

@OutputDirectory
abstract DirectoryProperty getDestinationDirectory()
~~~

**`@InputDirectory`** theo dõi directory contents; **`RELATIVE`** bảo toàn identity của nested files. Đổi `docs/intro.txt` thành `archive/intro.txt` là thay đổi có ý nghĩa dù bytes giống.

### 7.1. Empty directories

Nếu task chỉ quan tâm các files, thêm directory rỗng không ảnh hưởng output. Có thể dùng:

~~~groovy
@InputDirectory
@IgnoreEmptyDirectories
@PathSensitive(PathSensitivity.RELATIVE)
abstract DirectoryProperty getSourceDirectory()
~~~

`@IgnoreEmptyDirectories` bỏ khác biệt empty dirs khi snapshot input. Nếu task cần sinh empty output dirs, dùng annotation này sẽ sai.

### 7.2. No source

~~~groovy
@InputFiles
@SkipWhenEmpty
@PathSensitive(PathSensitivity.RELATIVE)
abstract ConfigurableFileCollection getSourceFiles()
~~~

Với file collection trống, task có thể được skip với `NO-SOURCE`. `@SkipWhenEmpty` cũng hàm ý `@Incremental` behavior cho input ấy. Không dùng khi output rỗng vẫn là một artifact cần tạo.

### 7.3. Thứ tự file collection và classpath

`@InputFiles` thường không có semantics order như Java classpath. Nếu task concatenate nhiều files theo order, phải kiểm soát order deterministic và mô hình input order thích hợp. `@Classpath` thì **order-sensitive**, vì Java chọn class/resource dựa trên thứ tự entries.

## 8. Java classpath normalization: `@Classpath` và `@CompileClasspath`

Không nên dùng `@InputFiles` chung khi input thật sự là Java classpath có semantics riêng.

| Annotation | Dùng với | Điểm cần nhớ |
| --- | --- | --- |
| `@InputFiles` | Generic file collection | File inputs/path normalization thông thường |
| `@Classpath` | Runtime/test/tool classpath | Entry order ảnh hưởng; jar names/zip timestamps có thể bỏ qua khi không ảnh hưởng semantics |
| `@CompileClasspath` | Java compile classpath | Có thể bỏ qua implementation-only changes không ảnh hưởng ABI |

### 8.1. Runtime classpath

Thay thứ tự `a.jar:b.jar` thành `b.jar:a.jar` có thể đổi class/resource được JVM load. `@Classpath` nhận diện điều này là thay đổi có ý nghĩa.

Gradle normalize classpath archives để những thay đổi ZIP timestamps/entry order không liên quan ít làm invalidation. Không đồng nhất điều đó với raw byte equivalence của JAR.

### 8.2. Compile avoidance và ABI

Một dependency chỉ đổi private implementation mà public ABI không đổi có thể không cần compile consumer Java lại. `@CompileClasspath` hỗ trợ ABI-oriented fingerprinting, giảm compile tasks bị invalidate vô ích.

Tuy nhiên runtime reflection/resources, annotation processors và plugin-specific compiler behavior có thể có yêu cầu khác. Không tùy tiện gắn `@CompileClasspath` cho một tool đọc toàn bộ JAR contents.

## 9. Content normalization

### 9.1. `@NormalizeLineEndings`

Nếu task phân tích text sau khi normalize CRLF/LF, có thể khai:

~~~groovy
@InputFiles
@NormalizeLineEndings
@PathSensitive(PathSensitivity.RELATIVE)
abstract ConfigurableFileCollection getTextFiles()
~~~

Gradle có thể coi CRLF/LF là cùng input về mặt fingerprint. **Chỉ đúng khi output task không phụ thuộc bytes line endings gốc.** Nếu task copy raw bytes giữ CRLF/LF, dùng annotation này có thể dẫn đến stale output.

### 9.2. `@IgnoreEmptyDirectories`

Bỏ ảnh hưởng của empty directory nodes, nhưng không bỏ file contents hoặc relative file path. Nếu action tạo output dù chỉ có empty dirs, không được ignore.

### 9.3. Runtime classpath resource normalization

Snippet nâng cao:

~~~groovy
normalization {
    runtimeClasspath {
        ignore 'build-info.properties'
    }
}
~~~

Nó phù hợp nếu file build-info là metadata audit không ảnh hưởng kết quả runtime test. **Không dùng** nếu tests đọc build-info để quyết định behavior. Input normalization phải phản ánh ngữ nghĩa thật, không phải che mọi thay đổi để tăng cache hits.

## 10. Task-level up-to-date khác xử lý tăng dần từng file

Một task có `@InputFile`/`@OutputFile` vẫn có thể hoạt động tăng dần ở **cấp task**: giữa hai builds không đổi, action được skip.

Nhưng khi một input file đổi, task ấy vẫn xử lý toàn bộ file. Với hàng nghìn input files, muốn chỉ xử lý files mới/sửa/xóa cần dùng **`InputChanges` API**.

Điều kiện:
- Đánh dấu file input `@Incremental` hoặc `@SkipWhenEmpty`.
- Một `@TaskAction` nhận `InputChanges`.
- Gọi `inputChanges.getFileChanges(inputProperty)`.
- Xử lý `ADDED`, `MODIFIED`, `REMOVED`.
- Khi non-incremental, xử lý tất cả input files được báo là `ADDED`.
- Có output mapping và cleanup cho removed files.

### 10.1. Khi nào xử lý không incremental?

`InputChanges.isIncremental()` có thể false khi:
- Chưa có execution history.
- `--rerun-tasks`.
- Gradle version thay đổi/history không tương thích.
- Scalar `@Input` đổi.
- Non-incremental input đổi.
- Output bị xóa/chỉnh hoặc `upToDateWhen` buộc chạy.

Khi false, `getFileChanges` báo mọi input file hiện tại như `ADDED` để task dựng lại output. Với `PathSensitivity.NONE`, thay file có thể cho cặp `REMOVED` + `ADDED` thay vì `MODIFIED` do path không được dùng làm identity.

## 11. Ví dụ nâng cao `InputChanges` xử lý directory từng file

Đây là **phần mở rộng** của lab, thêm imports vào đầu `build.gradle` và class/task sau `plugins {}`. Nó không thay thế `RenderMessageTask`.

### 11.1. Imports mở rộng

~~~groovy
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.util.Locale
import org.gradle.api.GradleException
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.FileType
import org.gradle.api.tasks.Incremental
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.IgnoreEmptyDirectories
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.ChangeType
import org.gradle.work.InputChanges
~~~

Các imports đã có sẵn trong build.gradle chính không cần lặp.

### 11.2. Typed task

~~~groovy
abstract class UppercaseDirectoryTask extends DefaultTask {

    @Incremental
    @InputDirectory
    @PathSensitive(PathSensitivity.RELATIVE)
    @IgnoreEmptyDirectories
    abstract DirectoryProperty getSourceDirectory()

    @OutputDirectory
    abstract DirectoryProperty getDestinationDirectory()

    @TaskAction
    void process(InputChanges inputChanges) {
        Path root = getDestinationDirectory().get().asFile
            .toPath().toAbsolutePath().normalize()
        Files.createDirectories(root)

        inputChanges.getFileChanges(getSourceDirectory()).each { change ->
            if (change.fileType == FileType.DIRECTORY) {
                return
            }

            Path dest = root.resolve(change.normalizedPath).normalize()
            if (!dest.startsWith(root)) {
                throw new GradleException('Invalid output path')
            }

            if (change.changeType == ChangeType.REMOVED) {
                Files.deleteIfExists(dest)
            } else {
                Files.createDirectories(dest.parent)
                String source = Files.readString(
                    change.file.toPath(),
                    StandardCharsets.UTF_8
                )
                Files.writeString(
                    dest,
                    source.toUpperCase(Locale.ROOT),
                    StandardCharsets.UTF_8
                )
            }
        }
    }
}

tasks.register('uppercasePages', UppercaseDirectoryTask) {
    sourceDirectory.set(
        layout.projectDirectory.dir('inputs/pages')
    )
    destinationDirectory.set(
        layout.buildDirectory.dir('upper')
    )
}
~~~

### 11.3. Cách chạy

Tạo:

~~~text
inputs/pages/docs/intro.txt      (nội dung hello)
inputs/pages/guides/setup.txt    (nội dung gradle)
~~~

Chạy:

~~~bash
./gradlew uppercasePages
~~~

Outputs:

~~~text
build/upper/docs/intro.txt       (nội dung HELLO)
build/upper/guides/setup.txt     (nội dung GRADLE)
~~~

Đây là file content mô tả, không phải stdout của task.

**Cơ chế:**
- `getFileChanges(getSourceDirectory())` dùng managed property đã annotate `@Incremental`.
- `PathSensitivity.RELATIVE` giữ relative identity khi tính dest.
- `FileType.DIRECTORY` được bỏ qua vì task chỉ xử lý files.
- `ChangeType.REMOVED` xóa output file tương ứng.
- `ADDED` và `MODIFIED` viết text uppercase bằng UTF-8.
- `Locale.ROOT` không phụ thuộc default locale.
- `startsWith(root)` kiểm tra một phần path traversal, nhưng không phải security sandbox chống symlink/untrusted filesystem.

Thử sửa một input, thêm input khác, rồi xóa input thứ ba. Khi Gradle có đủ incremental history, task xử lý phần thay đổi thay vì mọi files. Nếu output dir bị xóa, Gradle phải rebuild và có thể báo toàn bộ files `ADDED`.

Nếu muốn log mỗi change, **đặt bên trong vòng lặp**:

~~~groovy
logger.lifecycle(
    'Changed: ' + change.changeType + ' ' + change.normalizedPath
)
~~~

Không mong đợi log events sẵn có nếu bạn chưa thêm đoạn log này. Khi task `UP-TO-DATE`, TaskAction không chạy nên cũng không có event log từ action.

## 12. Build cache, task outcomes và configuration cache

| Nhãn | Ý nghĩa |
| --- | --- |
| `UP-TO-DATE` | Task action bỏ qua nhờ local execution history và unchanged inputs/outputs |
| `FROM-CACHE` | Output task được khôi phục từ cache |
| `NO-SOURCE` | Không có source input cần xử lý |
| `SKIPPED` | Task bị bỏ qua do điều kiện `onlyIf`/`enabled` hoặc tương đương |
| `FAILED` | Task validation/action thất bại |
| Không có skip label | Task đã thực thi |

### 12.1. Build cache

Chạy một build có `build` task với:

~~~bash
./gradlew build --build-cache
~~~

Gradle có thể restore outputs của các tasks eligible và cacheable nếu cache hit. Custom task **không tự cache** chỉ vì có `@Input`/`@OutputFile`; thường phải opt-in caching bằng `@CacheableTask` sau khi review determinism, relocatability, side effects và output ownership.

`FROM-CACHE` khác `UP-TO-DATE`: cache restore không cần local execution history hợp lệ của workspace hiện tại. Task được reuse từ normalized inputs/implementation và cache key tương ứng.

### 12.2. Relocatability và path sensitivity

Khi chuyển project sang workspace root khác:
- `PathSensitivity.ABSOLUTE` có thể khiến input fingerprints khác.
- `RELATIVE`/`NONE` có thể làm normalized fingerprints tương đương.
- Nhưng workspace mới không tự có **local task history**, vì vậy không nhất thiết thấy `UP-TO-DATE` ngay lần đầu.
- Với task cacheable và cache hit, có thể thấy `FROM-CACHE`.

Đừng coi “cùng file bytes” là đảm bảo cache reuse nếu task implementation, scalar inputs hoặc output policy khác.

### 12.3. Configuration cache

Configuration cache tái dùng configuration/task graph state, hoàn toàn khác với:
- Up-to-date checks.
- Build cache.
- File-level incremental `InputChanges`.

Một Gradle run có thể reuse configuration cache nhưng `recipient` mới khiến `renderMessage` chạy lại. Ngược lại, configuration cache miss không tự buộc task action chạy nếu inputs/outputs vẫn up-to-date.

### 12.4. `--rerun-tasks`

~~~bash
./gradlew renderMessage --rerun-tasks
~~~

Forces task execution, không sửa model input thiếu. Với `InputChanges` task, có thể dẫn đến non-incremental full processing.

### 12.5. `--dry-run`

~~~bash
./gradlew renderMessage --dry-run
~~~

Chỉ cho thấy task graph, **không thực thi action và không kiểm tra output contents**. Nó không thay thế phép thử up-to-date hoặc Java viewer.

## 13. Undeclared inputs: vì sao task bị `UP-TO-DATE` sai?

Một số input ẩn hay gặp:

| Input ẩn | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| File config action tự đọc | Sửa file nhưng Gradle không nhận | `@InputFile` hoặc runtime API `inputs.file` |
| `System.getenv("MODE")` | Env thay đổi nhưng task không biết | Provider env → `@Input` |
| System property | Mode/tool option bị ẩn | Gradle provider/input property phù hợp |
| External tool version | Tool đổi output | Tool classpath/args/implementation tracked |
| Network response | Không reproducible | Có artifact snapshot/version input rõ hoặc non-cacheable |
| Clock/random | Output không ổn định | Tránh hoặc thiết kế execution semantics có chủ đích |
| Default charset | Output khác OS | Pin UTF-8/JDK/toolchain |
| Working directory | Relative path đổi theo caller | `layout.projectDirectory` và file property |
| Relative source file path | Output path phụ thuộc path nhưng fingerprint bỏ | Dùng `PathSensitivity.RELATIVE` |

Dùng `@Internal` để che thiếu annotation không làm task đúng. Tăng cache hit bằng cách khai thiếu input có thể tạo **wrong output**, không phải optimization.

## 14. Những nguyên nhân chạy lại thừa

### 14.1. Input tree quá rộng

Task chỉ đọc `config.json` nhưng khai cả project root làm `@InputDirectory`. Mọi thay đổi source/README không liên quan đều có thể invalidation. Thu hẹp input files.

### 14.2. Default ABSOLUTE

Cùng source nhưng hai checkout paths khác nhau. Nếu output không chứa absolute path, dùng NONE hoặc RELATIVE thích hợp.

### 14.3. Property thay mỗi invocation

Task có `@Input buildTimestamp` trong khi output không cần timestamp. Khi timestamp đổi, task luôn out-of-date. Bỏ property nếu không ảnh hưởng output hoặc thiết kế lại audit metadata.

### 14.4. Generator upstream không deterministic

Một generated JSON có `generatedAt` thay mỗi run khiến downstream file contents đổi liên tục. Không dạy downstream ignore content; trước hết ổn định generator hoặc tách timestamp khỏi artifact mang ý nghĩa build.

### 14.5. Output bị ghi đè bởi task khác

Task A sở hữu `build/generated`, task B cũng ghi vào đó, có thể khiến A thấy output changed/missing. Sửa ownership, không cố `upToDateWhen { true }`.

### 14.6. Implementation đổi

Custom plugin/task class thay đổi → Gradle có thể fingerprint task implementation khác. Đây không phải lỗi file contents/path.

## 15. Input/output ownership và producer-consumer dependencies

Một task khác có thể copy output của `renderMessage`:

~~~groovy
tasks.register('copyMessage', Copy) {
    from(tasks.named('renderMessage')) {
        rename { 'message-copy.txt' }
    }
    into(layout.buildDirectory.dir('copies'))
}
~~~

`Copy.from(taskProvider)` giúp Gradle tìm task output và suy ra producer-consumer dependency. Task downstream không cần hard-code input file path.

**Thiếu an toàn:**

~~~groovy
tasks.register('copyMessageBad', Copy) {
    from('build/generated/message.txt')
    into('build/copies')
}
~~~

Không có producer relation trực tiếp; file có thể chưa tồn tại hoặc Gradle báo implicit dependency problem. `mustRunAfter` không thay thế data dependency.

### 15.1. Không chồng lấn output

Một task khai `@OutputDirectory build/generated` và task khác khai `@OutputFile build/generated/message.txt` có overlapping outputs. `Sync`/`clean`/parallel execution/cache snapshots dễ gây xung đột. Mỗi task nên có output directory/file riêng.

### 15.2. Output content mới ảnh hưởng downstream

Nếu producer chạy lại nhưng tạo cùng bytes, consumer có thể vẫn `UP-TO-DATE`. Nếu producer output bytes khác, downstream input snapshot khác nên phải được xét lại. Đây là cốt lõi của build tăng dần theo chuỗi tác vụ.

## 16. Chẩn đoán trạng thái task với công cụ Gradle

~~~bash
./gradlew renderMessage --info
./gradlew renderMessage --console=verbose
./gradlew renderMessage --rerun-tasks
./gradlew clean renderMessage
./gradlew tasks --all
./gradlew help --configuration-cache
~~~

- `--info` thường cho thấy lý do task out-of-date, input property changed, file input changed, output missing hoặc implementation changed.
- `--console=verbose` giúp xem task outcomes.
- `--rerun-tasks` buộc task chạy, hữu ích khi nghi ngờ stale output nhưng không sửa input declaration.
- `clean renderMessage` xóa outputs rồi tạo lại.
- `tasks --all` kiểm tra tên task.
- `--configuration-cache` kiểm tra configuration reuse, không thay up-to-date semantics.

Nên kiểm tra **nội dung file** bằng Java viewer, `sha256sum` hoặc PowerShell `Get-FileHash`, chứ không chỉ nhìn file mtime. Gradle `--debug` có thể in thông tin nhạy cảm; cẩn trọng khi chia sẻ logs/build scans.

### 16.1. Vì sao không nên luôn chạy clean?

`clean build` hữu ích để xác minh reproducibility hoặc điều tra lỗi, nhưng xóa local outputs khiến Gradle không thể sử dụng nhiều cơ hội up-to-date. Trong CI, có thể kết hợp clean verification với build cache nếu policy cho phép; không dùng `--rerun-tasks` mọi lần khi không cần.

### 16.2. Output directory có file mới

Gradle có quy tắc đặc biệt: file được thêm bên ngoài vào output directory không phải lúc nào cũng làm task out-of-date, để tránh can thiệp không cần thiết giữa tasks. Điều này **không phải lời khuyên** cho phép nhiều task dùng chung một output directory. Giữ ownership duy nhất là chính sách an toàn hơn.

## 17. Bảng tổng hợp các thay đổi và kết quả

Giả sử task từng chạy thành công, output còn hợp lệ và không có cache restore khác:

| Thay đổi | Tác động lên task |
| --- | --- |
| Chạy lại không đổi gì | `UP-TO-DATE` |
| Đổi template bytes | Task chạy |
| Đổi `-Precipient` | Task chạy |
| Đổi `-Pprefix` | Task chạy |
| Đổi file path cùng bytes, `NONE` | Có thể `UP-TO-DATE` |
| Đổi file path, `ABSOLUTE` | Task chạy |
| Đổi relative path trong input directory với `RELATIVE` | Task chạy |
| Chỉ touch mtime, contents không đổi | Thường `UP-TO-DATE` |
| Xóa required input file | Validation fail |
| Xóa output file | Task chạy hoặc cache restore |
| `--rerun-tasks` | Forced task execution |
| Empty source collection với `@SkipWhenEmpty` | `NO-SOURCE` |
| `onlyIf { false }` | `SKIPPED` |
| Cacheable task có cache hit nhưng thiếu local output | `FROM-CACHE` |
| Implementation code đổi | Có thể chạy lại |

Không có một outcome duy nhất cho mọi máy nếu build khác Gradle version/history, enabled caching, dependencies hoặc task implementation.

## 18. Bài tập và đáp án

### Bài 1 — File content
**Hỏi:** `template.txt` giữ tên, đổi `Hello` thành `Welcome`. Gradle có cơ sở chạy lại không?

**Đáp án:** Có, `@InputFile` theo dõi contents.

### Bài 2 — Timestamp
**Hỏi:** Chỉ `touch` input file, bytes y hệt. Chắc chắn task chạy lại?

**Đáp án:** Không, mtime có thể khiến rehash nhưng normalized content fingerprint không đổi.

### Bài 3 — Property
**Hỏi:** Recipient đổi `Gradle` → `Mai`, được annotate `@Input`. Kết quả?

**Đáp án:** Task bị xét out-of-date vì input scalar value đổi.

### Bài 4 — NONE
**Hỏi:** Task đọc template, không quan tâm tên/path. Policy?

**Đáp án:** `PathSensitivity.NONE`.

### Bài 5 — RELATIVE
**Hỏi:** Task tạo output folder structure theo relative input paths. Policy?

**Đáp án:** `PathSensitivity.RELATIVE`.

### Bài 6 — NAME_ONLY
**Hỏi:** Có `a/x.txt` và `b/x.txt`, output giữ hai thư mục. Có nên dùng NAME_ONLY?

**Đáp án:** Không, folder identity quan trọng.

### Bài 7 — ABSOLUTE
**Hỏi:** Cùng file bytes nhưng CI checkout root khác, policy ABSOLUTE ảnh hưởng ra sao?

**Đáp án:** Full path khác có thể invalidation/cache miss.

### Bài 8 — Missing input
**Hỏi:** Task đọc env MODE nhưng không khai. Nguy cơ?

**Đáp án:** Task có thể `UP-TO-DATE` sai; khai Provider + `@Input`.

### Bài 9 — Output mất
**Hỏi:** Inputs không đổi, output bị xóa. Có giữ `UP-TO-DATE` không?

**Đáp án:** Không theo history thông thường; task chạy hoặc cache restore.

### Bài 10 — Classpath
**Hỏi:** Vì sao `@Classpath` quan tâm thứ tự entries?

**Đáp án:** JVM class/resource lookup có thể phụ thuộc classpath order.

### Bài 11 — Compile ABI
**Hỏi:** Dependency đổi private method body, public ABI giữ nguyên. `@CompileClasspath` có thể tránh rerun?

**Đáp án:** Có trong những trường hợp compile-avoidance phù hợp.

### Bài 12 — Normalize line endings
**Hỏi:** Task copy nguyên bytes input. Có nên ignore CRLF/LF?

**Đáp án:** Không, output byte content khác.

### Bài 13 — InputChanges
**Hỏi:** Task xử lý nhiều files và cần xóa output khi source bị xóa. Sử dụng gì?

**Đáp án:** `InputChanges.getFileChanges` và xử lý `ChangeType.REMOVED`.

### Bài 14 — Non-incremental
**Hỏi:** Scalar property đổi trong incremental task. Chỉ xử lý file changed có đủ không?

**Đáp án:** Không. Task có thể phải full rebuild vì scalar đổi có thể ảnh hưởng mọi output.

### Bài 15 — Build cache
**Hỏi:** `FROM-CACHE` là TaskAction incremental?

**Đáp án:** Không. Gradle phục hồi cached outputs, thường không chạy TaskAction.

### Bài 16 — Configuration cache
**Hỏi:** Reuse configuration cache đồng nghĩa task `UP-TO-DATE`?

**Đáp án:** Không. Configuration reuse và task input/output fingerprints là hai vấn đề khác.

### Bài 17 — `@SkipWhenEmpty`
**Hỏi:** No source files thì outcome thường gì?

**Đáp án:** `NO-SOURCE` khi thỏa empty-source conditions.

### Bài 18 — Thực hành
1. Tạo lab Java 17 đầy đủ phần 6.
2. Chạy Gradle task hai lần; kiểm tra lần hai `UP-TO-DATE`.
3. Đổi file content; xem output Java17 đổi.
4. Đổi recipient, prefix; so stdout.
5. Copy template sang path mới cùng bytes; thử `-PtemplatePath`.
6. Xóa output, chạy lại.
7. Thử advanced `uppercasePages` với ADDED/MODIFIED/REMOVED.
8. So sánh `@PathSensitive(NONE)` và `RELATIVE` trong các trường hợp có ý nghĩa.
9. Kiểm tra `--info` khi có task rerun.
10. Giải thích sự khác nhau giữa up-to-date, FROM-CACHE, configuration cache và file-level incremental processing.

**Tiêu chí đạt:** Bạn có thể giải thích vì sao từng thay đổi content/path/property ảnh hưởng task state, chọn đúng annotations và có ví dụ Java17 chạy ra stdout dự kiến.

## 19. Checklist trước khi dùng task trong dự án thật

- [ ] Input file contents được khai `@InputFile`/`@InputFiles`/`@InputDirectory`.
- [ ] Scalar options ảnh hưởng output khai `@Input`/nested input đúng.
- [ ] Path sensitivity hợp semantics: NONE cho file path-independent, RELATIVE cho directory tree.
- [ ] Không bỏ file name/path nếu output phụ thuộc nó.
- [ ] Không giữ ABSOLUTE mặc định khi không cần.
- [ ] Dùng `@Classpath`/`@CompileClasspath` cho đúng JVM classpath behavior.
- [ ] Nếu normalize CRLF/LF, output thật sự không phụ thuộc line endings gốc.
- [ ] Nếu ignore empty dirs, task không cần tạo output empty folders.
- [ ] Nếu skip when empty, không cần tạo artifact khi input trống.
- [ ] `InputChanges` task xử lý ADDED/MODIFIED/REMOVED và non-incremental rebuild.
- [ ] Outputs được khai rõ và có owner duy nhất.
- [ ] Không có undeclared env/network/time/file input.
- [ ] Inputs/outputs dùng Gradle Providers/task dependency wiring khi phù hợp.
- [ ] Có tests thay content, path, property, xóa output, rerun.
- [ ] Task implementation, compiler/toolchain versions và generator config được quản lý.
- [ ] Không coi cache hits là bằng chứng đúng nghiệp vụ.
- [ ] Không chữa thiếu input bằng `@Internal` hoặc `upToDateWhen { true }`.
- [ ] Logs/Build Scans không lộ secrets.
- [ ] Release/CI có artifact provenance và rebuild policy rõ.

## 20. Tài liệu Gradle chính thức

- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): input/output declarations, fingerprinting, path sensitivity, normalization.
- [Gradle — Advanced Tasks](https://docs.gradle.org/current/userguide/custom_tasks.html): `InputChanges`/`FileChange`.
- [Gradle — Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html): cache key, relocatability và content normalization.
- [Gradle — Incremental Builds and Build Caching Basic](https://docs.gradle.org/current/userguide/gradle_optimizations.html): `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): NONE/RELATIVE recommendations.
- [Gradle API — PathSensitivity](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/PathSensitivity.html): ABSOLUTE/RELATIVE/NAME_ONLY/NONE.
- [Gradle API — InputChanges](https://docs.gradle.org/current/javadoc/org/gradle/work/InputChanges.html): incremental file event API.
- [Gradle API — SkipWhenEmpty](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/SkipWhenEmpty.html): no-source and incremental semantics.
- [Gradle API — IgnoreEmptyDirectories](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/IgnoreEmptyDirectories.html): bỏ empty directory changes.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): typed task/annotations.
- [Gradle — Lazy Configuration](https://docs.gradle.org/current/userguide/lazy_configuration.html): managed properties/Providers.
- [Gradle — Task Validation](https://docs.gradle.org/current/userguide/validation_problems.html): missing inputs/outputs and dependency diagnostics.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration reuse.
