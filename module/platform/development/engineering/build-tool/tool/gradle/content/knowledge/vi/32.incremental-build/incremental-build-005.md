# Input normalization và PathSensitivity trong Gradle

## 1. Vấn đề: vì sao cùng dữ liệu mà Gradle vẫn chạy lại task?

Giả sử hai developer checkout cùng một project:

~~~text
/home/alice/work/demo/src/templates/email.txt
/opt/ci/build/demo/src/templates/email.txt
~~~

Hai file `email.txt` có **cùng nội dung bytes**. Developer A chạy một task xử lý template, output đã nằm trong Gradle build cache. Nhưng máy CI vẫn chạy lại task thay vì lấy output từ cache. Một nguyên nhân thường gặp: Gradle nhận diện input file không chỉ bằng **nội dung**, mà còn có thể bằng **đường dẫn**, và mặc định input file không khai path sensitivity dùng đường dẫn tuyệt đối.

Một vấn đề đối nghịch cũng nguy hiểm: developer cố tối ưu cache bằng cách bảo Gradle **bỏ qua toàn bộ đường dẫn**, trong khi task thật sự tạo output theo cấu trúc thư mục. Khi đó hai bộ inputs khác nhau có thể được xem là giống nhau về fingerprint và Gradle có nguy cơ bỏ qua một lần chạy cần thiết hoặc phục hồi output không đúng.

**Input normalization** và **`PathSensitivity`** giúp Gradle trả lời câu hỏi:

> “Đối với task này, phần nào của đường dẫn hoặc nội dung input thực sự ảnh hưởng đến output?”

Bài học thuộc chủ đề **Build tăng dần** của module **Build Tool Gradle**. Trọng tâm là quan hệ giữa input fingerprinting, up-to-date checks, build cache, file path normalization, classpath normalization và tính đúng đắn của custom tasks.

### 1.1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích task inputs/outputs và cơ chế snapshot/fingerprint mà Gradle dùng.
2. Phân biệt **`UP-TO-DATE`**, **`FROM-CACHE`**, **`NO-SOURCE`**, thực thi thật và Configuration Cache.
3. Nắm chính xác bốn giá trị `PathSensitivity.ABSOLUTE`, `RELATIVE`, `NAME_ONLY`, `NONE`.
4. Chọn path sensitivity từ **hành vi của task**, không phải từ mong muốn tăng số cache hit.
5. Hiểu `@InputFile`, `@InputDirectory`, `@InputFiles`, `@PathSensitive`, `@OutputFile` và `@CacheableTask`.
6. Biết `@Classpath`/`@CompileClasspath` khác @PathSensitive ra sao.
7. Cấu hình runtime classpath normalization, bỏ qua metadata thực sự không ảnh hưởng kết quả.
8. Sử dụng `@NormalizeLineEndings`, `@IgnoreEmptyDirectories` và nhận diện nguy cơ false cache hits.
9. Viết typed task trong Gradle Kotlin DSL chạy với Java 17, cho kết quả deterministic.
10. Thử relocation, đổi nội dung, rename, thêm/xóa files và kiểm task outcomes.
11. Chẩn đoán cache miss bằng `--info`, build cache key inputs và Gradle reports.
12. Phân biệt cacheability, reproducibility, relocatability và incremental execution.
13. Viết một Java 17 program độc lập mô phỏng các chiến lược so sánh path.
14. Áp dụng nguyên tắc vào Java compile/runtime classpaths, CI và multi-project builds.

## 2. Ba cơ chế cần phân biệt ngay từ đầu

### 2.1. Up-to-date checks

Sau khi một task chạy thành công và Gradle biết **inputs + outputs**, lần sau Gradle có thể kiểm tra:

- Task implementation có thay đổi không?
- Input values hoặc file fingerprints có thay đổi không?
- Outputs có còn ở vị trí, trạng thái và nội dung phù hợp không?
- Những yếu tố khác ảnh hưởng tới task state có đổi không?

Nếu không đổi, Gradle có thể bỏ qua execution và hiển thị:

~~~text
> Task :renderIndex UP-TO-DATE
~~~

Kết quả này dựa trên **local execution history và output state**. Không cần task phải có `@CacheableTask` hay bật shared build cache mới có cơ hội `UP-TO-DATE`.

### 2.2. Task output build cache

Nếu task **được phép cache**, Gradle tính một cache key từ task implementation, input property names/values, normalized input files và những yếu tố liên quan. Nếu tìm thấy outputs khớp key trong cache, task có thể lấy output thay vì chạy lại:

~~~text
> Task :renderIndex FROM-CACHE
~~~

Build cache có thể là local hoặc remote tùy cấu hình. Có thể bật bằng:

~~~bash
gradle --build-cache renderIndex
~~~

hoặc `gradle.properties`:

~~~properties
org.gradle.caching=true
~~~

`@CacheableTask` thể hiện task type đủ điều kiện caching, nhưng **không bảo đảm cache hit**: task phải có outputs, implementation/cache inputs phù hợp và build cache được bật. Một task có inputs chưa khai báo, output không deterministic hoặc external side effects không nên được cache dù nó trông nhanh hơn.

### 2.3. Incremental execution

Một số task nhận thông tin **những file nào thay đổi** qua `InputChanges`, rồi chỉ xử lý phần bị ảnh hưởng. Ví dụ compiler Gradle có thể recompile tập classes cần thiết thay vì toàn bộ code.

**Incremental execution ≠ up-to-date skip ≠ build cache reuse.**

- `UP-TO-DATE`: không chạy task action.
- `FROM-CACHE`: khôi phục outputs từ cache, không chạy action.
- Incremental execution: task action **có chạy**, nhưng xử lý một phần thay vì tất cả.
- Full execution: task action chạy để tạo lại outputs.
- Configuration Cache: tái sử dụng **kết quả configuration/task graph**, không phải output file cache.

Path normalization ảnh hưởng cách Gradle nhận diện input changes, nhưng **không tự biến custom task thành incremental task**.

## 3. Input fingerprint có những thành phần nào?

Một task đơn giản có:

~~~text
Input values:
  prefix = INDEX_V1

Input file tree:
  src/records/a.txt        content = apple
  src/records/sub/b.txt    content = banana

Task implementation:
  RenderIndex

Output:
  build/generated/index.txt
~~~

Gradle biết những properties đã khai báo qua annotations hoặc runtime API. Với file inputs, Gradle tạo snapshots/fingerprints liên quan tới:

- **Nội dung file** hoặc normalized representation của nội dung.
- **Phần đường dẫn được khai quan trọng**: tuyệt đối, tương đối, tên cuối hoặc không tính path.
- Tính chất của input file tree, tùy annotation/options.
- Với classpaths, **thứ tự entries và những quy tắc chuẩn hóa chuyên biệt**.
- Các giá trị input khác, task implementation/action classpath và tên output properties.

**Không phải mọi thông tin trên filesystem đều là input**. Nếu task đọc environment variable, current time, network, system property, Git HEAD hoặc một file không khai báo, Gradle có thể không nhận ra sự thay đổi. Normalization đúng không chữa được **undeclared inputs**.

### 3.1. Đường dẫn input và đường dẫn output không cùng vai trò

`@PathSensitive` dành cho **file input fingerprints**, không tự động thay output path, không tự đổi file name khi task chạy. `@OutputFile` và `@OutputDirectory` giúp Gradle quản lý output state. Task action vẫn đọc file bằng đường dẫn thật mà property trỏ tới.

Ví dụ task có `@PathSensitive(NONE)` nhưng action dùng `inputFile.get().asFile.name` để đặt tên output. Khi tên file đổi, Gradle có thể không nhận ra đó là input quan trọng. Đây là một **khai báo sai semantic inputs**, không phải lỗi Gradle.

## 4. Bốn giá trị của PathSensitivity

Enum `org.gradle.api.tasks.PathSensitivity` có bốn mức:

| Chiến lược | Phần path được xét | Điển hình |
| --- | --- | --- |
| `ABSOLUTE` | Toàn bộ đường dẫn tuyệt đối | Khi chính absolute location ảnh hưởng output; hiếm cho cache chia sẻ |
| `RELATIVE` | Path tương đối so với hierarchy/input root | Thư mục templates, resources, source trees |
| `NAME_ONLY` | Chỉ tên file/thư mục, không xét các parent paths | Khi output thực sự chỉ quan tâm basename |
| `NONE` | Không xét path; file content vẫn được xét | Một input file mà output chỉ phụ thuộc bytes |

Nếu không gắn `@PathSensitive` cho file input, Gradle dùng **`ABSOLUTE` theo mặc định**. Vì vậy các tasks tự viết dễ không relocatable dù code hoạt động tốt.

### 4.1. ABSOLUTE — xét full path

~~~kotlin
@get:InputFile
@get:PathSensitive(PathSensitivity.ABSOLUTE)
abstract val inputFile: RegularFileProperty
~~~

Ví dụ:

~~~text
/home/alice/project/input.txt
/agent/work/project/input.txt
~~~

Nội dung có thể giống nhau nhưng **normalized paths khác**. Task output cache thường không tái sử dụng giữa hai workspaces nếu phụ thuộc absolute input path.

**Khi nào đúng?** Khi task thật sự đưa full absolute path vào output hoặc hành vi phụ thuộc vị trí thực. Dù vậy, output phụ thuộc absolute path cần được cân nhắc vì khó tái lập qua CI machines. Trước khi chấp nhận ABSOLUTE, xem có thể thiết kế output dùng relative path hoặc khai path thành `@Input` rõ ràng hay không.

### 4.2. RELATIVE — xét đường dẫn trong input hierarchy

~~~kotlin
@get:InputDirectory
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val sourceDirectory: DirectoryProperty
~~~

Hai cây:

~~~text
/home/alice/demo/src/templates/
├── mail/welcome.txt
└── web/index.html

/ci/work/demo/src/templates/
├── mail/welcome.txt
└── web/index.html
~~~

sẽ có cùng normalized entry paths:

~~~text
mail/welcome.txt
web/index.html
~~~

nếu contents tương ứng giống nhau. **Root directory absolute location không ảnh hưởng**, nhưng relative structure **có ảnh hưởng**.

Nếu đổi:

~~~text
mail/welcome.txt
~~~

thành:

~~~text
archive/welcome.txt
~~~

Gradle nhận ra normalized path đã khác; hợp lý nếu task copy files, generate index theo path, build asset manifest hoặc tạo archive giữ thư mục tương đối.

**Chi tiết:** với **file nằm trực tiếp ở root của input file collection**, `RELATIVE` có thể dùng tên file làm normalized path; với **input directory root**, normalized root path là chuỗi rỗng, còn files con dùng path tương đối đến root. Không hiểu `RELATIVE` chỉ là “lấy tên file cuối”.

### 4.3. NAME_ONLY — chỉ xét basename

~~~kotlin
@get:InputFiles
@get:PathSensitive(PathSensitivity.NAME_ONLY)
abstract val resources: ConfigurableFileCollection
~~~

Ví dụ:

~~~text
templates/email.txt
templates/archive/email.txt
~~~

Hai entries có tên cuối là `email.txt`. Nếu task chỉ quan tâm basename và content, việc chuyển parent directory có thể không thay đổi normalized inputs.

**Nguy cơ:** task copy ra cùng cấu trúc folder, tạo routing key theo parent directory hoặc process filename theo relative path sẽ có kết quả khác khi file di chuyển. Khi đó `NAME_ONLY` quá lỏng, có nguy cơ false cache hit.

Trong phần lớn directory-tree tasks, `RELATIVE` an toàn và hữu ích hơn `NAME_ONLY`.

### 4.4. NONE — bỏ path khỏi fingerprint, không bỏ nội dung

~~~kotlin
@get:InputFile
@get:PathSensitive(PathSensitivity.NONE)
abstract val inputFile: RegularFileProperty
~~~

File:

~~~text
/home/alice/demo/config.txt
/ci/build/demo/options.txt
~~~

Nếu bytes giống nhau và output task chỉ phụ thuộc bytes, Gradle có thể coi phần input file này tương đương dù tên/đường dẫn khác. **`NONE` không có nghĩa “không kiểm file thay đổi”**: đổi bytes vẫn phải làm fingerprint thay đổi.

Sử dụng phù hợp:

- Tính SHA-256 của một file bất kể tên.
- Parse một file cấu hình và xuất ra kết quả **không bao gồm đường dẫn/tên file**.
- Transform nội dung một file duy nhất thành fixed output format.

Không phù hợp nếu:

- Output cần chèn `inputFile.name`.
- Task tạo mapping giữa path và contents.
- Task xử lý nhiều files cùng bytes nhưng output cần phân biệt danh tính của từng file.
- Logic phụ thuộc vị trí file, ví dụ relative imports/include resolution.

### 4.5. Chọn mức nào là “đúng nhất”?

Câu hỏi đầu tiên **không phải** “mức nào nhanh nhất”, mà là:

> Nếu giữ nguyên bytes nhưng đổi đường dẫn theo cách này, task output có phải được phép giữ nguyên 100% hay không?

- Output khác do full location → cân nhắc `ABSOLUTE`.
- Output khác do relative hierarchy → `RELATIVE`.
- Output chỉ khác do basename → `NAME_ONLY`.
- Output không phụ thuộc path → `NONE`.

Mỗi mức chỉ đúng nếu **task implementation thực sự tuân thủ** điều đã khai.

## 5. Sơ đồ trực quan: di chuyển cùng file

Giả sử hai input có cùng bytes:

~~~text
Build A: /home/alice/app/templates/mail/notice.txt
Build B: /ci/jobs/app/templates/mail/notice.txt
~~~

Dùng input root `templates`.

| Mode | A vs B có cùng normalized path không? | Vì sao? |
| --- | --- | --- |
| ABSOLUTE | Không | `/home/alice/...` khác `/ci/jobs/...` |
| RELATIVE | Có | Cùng `mail/notice.txt` |
| NAME_ONLY | Có | Cùng `notice.txt` |
| NONE | Có | Path bị bỏ khỏi fingerprint |

Nếu đổi riêng B thành:

~~~text
/ci/jobs/app/templates/other/notice.txt
~~~

thì:

- `ABSOLUTE` khác.
- `RELATIVE` khác: `mail/notice.txt` vs `other/notice.txt`.
- `NAME_ONLY` vẫn cùng tên `notice.txt`.
- `NONE` vẫn bỏ qua path.

Nếu bytes thay đổi, cả bốn **vẫn nhận thấy content change** trong trường hợp file input thông thường; trừ những quy tắc **content normalization** khác được cấu hình để bỏ qua phần nội dung đó.

## 6. File input annotations cần biết

### 6.1. @InputFile

Một file đơn:

~~~kotlin
@get:InputFile
@get:PathSensitive(PathSensitivity.NONE)
abstract val configFile: RegularFileProperty
~~~

`RegularFileProperty` phù hợp hơn raw mutable `File` trong typed Gradle task; có thể set bằng Provider của một producer task để Gradle suy ra dependency.

### 6.2. @InputDirectory

Một directory tree:

~~~kotlin
@get:InputDirectory
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val templates: DirectoryProperty
~~~

Gradle snapshot các files trong directory, với normalized paths phù hợp RELATIVE. Nếu task đọc từ outside directory, phải khai thêm những file inputs khác.

### 6.3. @InputFiles

Một tập file/directory inputs:

~~~kotlin
@get:InputFiles
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val sourceFiles: ConfigurableFileCollection
~~~

`@InputFiles` cho phép collections, nhưng hãy chú ý **collection roots và relative semantics**. Nếu paths từ nhiều roots khác nhau nhưng task cần phân biệt nguồn, có thể khai các properties riêng hoặc explicit identity input.

### 6.4. @Input value

~~~kotlin
@get:Input
abstract val outputPrefix: Property<String>
~~~

Một phần behavior phụ thuộc `outputPrefix`; phải khai `@Input` để việc đổi giá trị làm Gradle nhận ra input đổi. Không cố lạm dụng `PathSensitivity` để đại diện cho những cấu hình logic như encoding, locale, formatter mode, JVM target hoặc algorithm name.

### 6.5. @OutputFile và @OutputDirectory

~~~kotlin
@get:OutputFile
abstract val resultFile: RegularFileProperty
~~~

Khi một task có declared outputs, Gradle mới có cơ sở quản lý up-to-date state và build cache outputs. **Không bao giờ** cho hai cacheable tasks ghi đè cùng một output file hoặc overlap output directories không kiểm soát.

### 6.6. @CacheableTask

~~~kotlin
@CacheableTask
abstract class HashInputs : DefaultTask() {
    // khai inputs, outputs và @TaskAction phù hợp
}
~~~

Đây là **fragment minh họa**, không phải class chạy độc lập. `@CacheableTask` cho Gradle biết task implementation có tính chất phù hợp để output cache, nhưng trách nhiệm đúng/sai thuộc người viết task.

### 6.7. @IgnoreEmptyDirectories, @SkipWhenEmpty và @Optional

- `@IgnoreEmptyDirectories`: bỏ những khác biệt chỉ do empty directories khỏi input tracking khi được hỗ trợ cho file properties thích hợp.
- `@SkipWhenEmpty`: khi file input collection không có source phù hợp, task có thể bị skip với outcome `NO-SOURCE`. Nó còn có ý nghĩa xử lý output stale theo lifecycle.
- `@Optional`: input property có thể không được cung cấp; **không đồng nghĩa** bỏ qua thay đổi nội dung khi có file.
- `@NormalizeLineEndings`: làm cho line ending differences được coi tương đương trong fingerprint của file inputs được gắn annotation.

Không trộn các annotation vì chỉ muốn “tăng cache”; mỗi annotation là một **khẳng định về semantic inputs**.

## 7. @Classpath và @CompileClasspath không phải một dạng PathSensitivity

Gradle có xử lý chuyên biệt cho Java/JVM classpaths. Hai annotations:

~~~kotlin
@get:Classpath
abstract val runtimeClasspath: ConfigurableFileCollection
~~~

và:

~~~kotlin
@get:CompileClasspath
abstract val compileClasspath: ConfigurableFileCollection
~~~

cung cấp normalization sâu hơn path handling thông thường.

### 7.1. @Classpath: runtime classpath fingerprint

Với runtime classpath, Gradle hiểu:

- Tên và absolute location của JAR/directory **ở cấp classpath entry** thường không quan trọng.
- **Thứ tự classpath entries quan trọng**: cùng class có thể được tìm thấy ở entry trước, ảnh hưởng runtime.
- Khi inspect JAR/ZIP classpath, Gradle có thể bỏ qua archive entry timestamps và thứ tự các entries bên trong archive.
- Nhưng contents có ý nghĩa của class/resources vẫn được tính, trừ khi bạn cấu hình normalization thêm.

Ví dụ cùng JAR được rebuild với khác ZIP timestamps nhưng classes/resources bytes giống nhau: `@Classpath` có thể xem là tương đương. Ngược lại, đổi nội dung `application.properties` mà test đọc có thể làm fingerprint khác.

**Đừng** thay `@Classpath` bằng `@PathSensitive(NONE)` trên một tập JAR files: bạn sẽ mất semantic classpath ordering và archive normalization chuyên biệt.

### 7.2. @CompileClasspath: xem API/ABI quan trọng cho compile

`@CompileClasspath` sử dụng normalization phục vụ compile avoidance. Tại sao?

Nếu dependency class thay **implementation of private methods** nhưng không đổi public ABI mà consumer source dùng, consumer Java không cần compile lại trong nhiều trường hợp. Gradle có thể tránh compilation task không cần thiết.

Thông thường compile classpath normalization bỏ qua:

- Những resource files không tác động đến Java compilation của task.
- ZIP timestamps/entry order.
- Bytecode implementation details không làm thay đổi relevant ABI.

Và tập trung vào:

- Class signatures/public/protected API và các elements Gradle xác định có ý nghĩa cho compile.
- Constants/annotations/type metadata khi có thể tác động tới compiled consumer.
- Thứ tự classpath entries do resolution semantics.

**Giới hạn:** Không suy luận “mọi thay đổi method body luôn bị bỏ qua” cho mọi compiler, annotation processor, language hoặc bytecode feature. Compiler/plugins có thể đọc resource hoặc implementation details; khi đó `@CompileClasspath` có thể **quá lỏng**, cần khai thêm inputs đúng hoặc dùng `@Classpath`. Đối với JavaCompile built-in, Gradle có kiến thức riêng về incremental compilation và ABI.

### 7.3. Khi nào dùng annotation nào?

| Đầu vào thực tế | Annotation thường phù hợp |
| --- | --- |
| Một config file, output không phụ thuộc tên/path | `@InputFile + @PathSensitive(NONE)` |
| Một directory giữ hierarchy trong output | `@InputDirectory + @PathSensitive(RELATIVE)` |
| Các files được copy và đổi parent path là thay đổi thật | `@InputFiles + @PathSensitive(RELATIVE)` |
| Java runtime classpath dùng để chạy tests/tools | `@Classpath` |
| Java compile classpath mà task chỉ quan tâm compile API | `@CompileClasspath` |
| Một value như formatVersion/encoding/algorithm | `@Input` |
| A jar file cần phân tích raw ZIP bytes | `@InputFile + @PathSensitive(NONE)`, **không** @Classpath nếu ZIP metadata bytes quan trọng |

### 7.4. Đừng bỏ qua đường dẫn của native tool một cách mù quáng

Native compiler, code generator, Python/Ruby tasks hoặc custom processors có thể phản ứng với relative file paths/filenames khác Java tooling. `@Classpath` được thiết kế cho JVM classpath semantics; không áp nó cho tập arbitrary files chỉ vì muốn cache hit.

## 8. Content normalization: không chỉ đường dẫn

Path normalization trả lời “đường dẫn nào quan trọng”; content normalization trả lời “phần nội dung nào quan trọng đối với output”.

### 8.1. Runtime classpath normalization

Giả sử một JAR có file:

~~~text
build-info.properties
~~~

với dữ liệu biến động:

~~~properties
ci.job.id=12345
build.timestamp=2026-11-09T09:00:00Z
~~~

Nếu test **không đọc và không phụ thuộc** file này, mỗi build tạo lại JAR có thể gây cache miss không cần thiết. Gradle cho phép cấu hình:

~~~kotlin
normalization {
    runtimeClasspath {
        ignore("build-info.properties")
    }
}
~~~

Đối với các runtime classpath inputs trong project, file matching pattern bị bỏ khỏi **normalized fingerprint**. **File thật vẫn nằm trong JAR** và runtime vẫn có thể đọc nó. Normalization không rewrite archive, không xóa resource và không tự thay đổi runtime dependency graph.

### 8.2. Pattern có thể khớp nhiều archive entries

Ví dụ:

~~~kotlin
normalization {
    runtimeClasspath {
        ignore("META-INF/build-info.properties")
        ignore("**/generated-build-id.txt")
    }
}
~~~

Patterns có thể được dùng cho archive entries và resources theo Gradle runtime classpath normalization rules. Hãy chọn pattern hẹp. Nếu `**/generated-build-id.txt` vô tình match resource test thực sự dùng, cache sẽ không invalidated khi resource thay đổi.

### 8.3. META-INF normalization

Gradle hỗ trợ chọn lọc metadata không ảnh hưởng kết quả:

~~~kotlin
normalization {
    runtimeClasspath {
        metaInf {
            ignoreAttribute("Build-Time")
            ignoreProperty("ci.job.id")
        }
    }
}
~~~

`ignoreAttribute` xử lý named manifest attributes theo normalization semantics; `ignoreProperty` xử lý matching properties keys trong `META-INF`. Những rule này **không có nghĩa tất cả metadata bị bỏ qua**, và không tự thay đổi file JAR.

Chỉ dùng khi đã chứng minh test/process không dùng những metadata đó. Nếu application đọc `Package.getImplementationVersion()`, manifest Implementation-Version có thể quan trọng. **Đừng** ignore mọi manifest hoặc `META-INF/**` chỉ để tăng cache hits; plugin descriptors, services và security metadata có thể ảnh hưởng runtime.

### 8.4. Properties normalization

Với classpath normalization, Gradle có thể đọc `.properties` và bỏ qua khác biệt về comment, whitespace và ordering các properties trong normalized view, theo rules hiện hành. Có thể cấu hình bỏ một số keys không có ảnh hưởng; những files không parse hợp lệ có thể được xử lý theo raw contents.

**Không nhầm** runtimeClasspath-normalized properties với task đọc một file `@InputFile` thông thường. Một task hash raw bytes phải nhận thấy thay đổi comment/whitespace; nếu muốn semantic properties fingerprint, bạn phải khai và xử lý theo logic thích hợp.

### 8.5. Thế nào là “irrelevant”?

Một trường chỉ irrelevant nếu **đổi trường đó mà không đổi observable task output** với mọi trường hợp mà task cam kết xử lý.

Ví dụ có thể irrelevant:

- Build timestamp chỉ để audit, test không bao giờ đọc.
- Comment trong properties khi runtime parser chỉ dùng key-value semantics.
- ZIP entry timestamps khi runtime chỉ quan tâm extracted bytes.

Ví dụ quan trọng:

- `META-INF/services/*`: service discovery phụ thuộc nội dung.
- `META-INF/MANIFEST.MF`: Main-Class, class-path, multi-release metadata có thể quyết định runtime behavior.
- `application.properties`: application runtime behavior.
- File path mà task đưa vào generated output.
- Content hashes trong signature/checksum workflows.

Dùng chính sách **an toàn trước, tối ưu sau**.

## 9. NormalizeLineEndings: CRLF và LF

Một file text có thể được checkout trên Windows dưới dạng CRLF, còn Linux dùng LF. Nếu task tạo output **giống nhau** sau khi normalizing line endings, có thể khai:

~~~kotlin
@get:InputDirectory
@get:PathSensitive(PathSensitivity.RELATIVE)
@get:NormalizeLineEndings
abstract val sourceDirectory: DirectoryProperty
~~~

Gradle xem những khác biệt line endings thuộc phạm vi annotation là tương đương trong input fingerprints.

**Điều kiện bắt buộc:** task action cũng phải xử lý hai input dạng khác nhau để tạo **cùng output**. Nếu action copy raw bytes, CRLF vs LF vẫn thay đổi output, khi đó `@NormalizeLineEndings` là khai báo sai và có thể dẫn đến false cache hit.

Trong lab ở mục 12, code cố ý chuẩn hóa CRLF/CR về LF trước khi tạo output.

### 9.1. NormalizeLineEndings không phải whitespace normalization tổng quát

Nó không tự bỏ qua:

- Dấu cách trong nội dung.
- Thay đổi chữ cái.
- Thay đổi encoding.
- Thay đổi filename.
- Thêm/bớt dòng dữ liệu có ý nghĩa.

Đừng gắn annotation này cho binary resources không có khái niệm text line endings theo định dạng của task.

## 10. @IgnoreEmptyDirectories và @SkipWhenEmpty

Một directory source có thể chứa một thư mục trống:

~~~text
src/templates/
├── mail/
│   └── welcome.txt
└── unused/
    └── (rỗng)
~~~

Nếu task chỉ liệt kê/copy **files**, empty directory không ảnh hưởng output. `@IgnoreEmptyDirectories` giúp Gradle không coi empty directory structure là thay đổi quan trọng.

~~~kotlin
@get:InputDirectory
@get:PathSensitive(PathSensitivity.RELATIVE)
@get:IgnoreEmptyDirectories
abstract val sourceDirectory: DirectoryProperty
~~~

Nếu task tạo empty directories trong output, annotation có thể không phù hợp. **Task action và declaration phải đồng thuận**.

`@SkipWhenEmpty` là chuyện khác. Nó diễn đạt rằng nếu source input empty, task có thể được skip. Nếu task **phải** tạo một file rỗng hoặc header-only report ngay cả khi input directory trống, đừng dùng skip-when-empty tùy tiện.

## 11. Mini-project chạy được: hai cacheable tasks, hai path semantics

Mục này cung cấp **một project Gradle Kotlin DSL đầy đủ**, chạy được bằng Gradle hỗ trợ JDK 17.

Task thứ nhất `renderIndex` đọc một directory tree và tạo index chứa **relative paths** → dùng `PathSensitivity.RELATIVE`.

Task thứ hai `hashInput` đọc một file và tạo SHA-256 của **raw bytes**, không ghi tên/đường dẫn vào kết quả → dùng `PathSensitivity.NONE`.

Cả hai là typed tasks có `@CacheableTask` và declared inputs/outputs.

### 11.1. Cấu trúc project

~~~text
normalization-lab/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    └── records/
        ├── a.txt
        └── sub/
            └── b.txt
~~~

File `a.txt` chứa:

~~~text
apple
~~~

File `sub/b.txt` chứa:

~~~text
banana
~~~

Trong các code blocks trên, editor thường thêm newline cuối file. `renderIndex` sẽ normalize line endings và bỏ trailing newline để output minh họa có thể xác định. Nếu file có nội dung khác, output thay theo.

### 11.2. settings.gradle.kts

~~~kotlin
rootProject.name = "normalization-lab"
~~~

### 11.3. build.gradle.kts đầy đủ

~~~kotlin
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.security.MessageDigest
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.IgnoreEmptyDirectories
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.NormalizeLineEndings
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

plugins {
    id("base")
}

@CacheableTask
abstract class RenderIndex : DefaultTask() {
    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    @get:IgnoreEmptyDirectories
    @get:NormalizeLineEndings
    abstract val sourceDirectory: DirectoryProperty

    @get:Input
    abstract val prefix: Property<String>

    @get:OutputFile
    abstract val resultFile: RegularFileProperty

    @TaskAction
    fun render() {
        val root = sourceDirectory.get().asFile.toPath()
        val records = mutableListOf<String>()

        Files.walk(root).use { paths ->
            paths.filter { Files.isRegularFile(it) }
                .forEach { file ->
                    val relative = root.relativize(file)
                        .toString().replace('\\', '/')
                    val content = Files.readString(
                        file, StandardCharsets.UTF_8
                    )
                        .replace("\r\n", "\n")
                        .replace('\r', '\n')
                        .trimEnd('\n')
                        .replace("\\", "\\\\")
                        .replace("\n", "\\n")

                    records.add(relative + "=" + content)
                }
        }

        records.sort()
        val output = prefix.get() + "\n" +
            records.joinToString(separator = "\n", postfix = "\n")

        val target = resultFile.get().asFile.toPath()
        Files.createDirectories(target.parent)
        Files.writeString(target, output, StandardCharsets.UTF_8)
    }
}

@CacheableTask
abstract class HashInput : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val inputFile: RegularFileProperty

    @get:OutputFile
    abstract val digestFile: RegularFileProperty

    @TaskAction
    fun hash() {
        val bytes = Files.readAllBytes(inputFile.get().asFile.toPath())
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(bytes)
        val hex = digest.joinToString("") { byte ->
            "%02x".format(byte.toInt() and 0xff)
        }

        val target = digestFile.get().asFile.toPath()
        Files.createDirectories(target.parent)
        Files.writeString(
            target, hex + "\n", StandardCharsets.UTF_8
        )
    }
}

tasks.register<RenderIndex>("renderIndex") {
    group = "verification"
    description = "Generates an index using relative paths"

    sourceDirectory.set(
        layout.projectDirectory.dir("src/records")
    )
    prefix.set("INDEX_V1")
    resultFile.set(
        layout.buildDirectory.file("generated/index.txt")
    )
}

tasks.register<HashInput>("hashInput") {
    group = "verification"
    description = "Hashes one file ignoring its name and path"

    inputFile.set(
        layout.projectDirectory.file("src/records/a.txt")
    )
    digestFile.set(
        layout.buildDirectory.file("hash/a.sha256")
    )
}
~~~

**Chú ý:** Đây là toàn bộ file `build.gradle.kts` cho bài lab. Không cần Java source để thực hiện hai Gradle tasks; code task types viết bằng Kotlin DSL build logic và sử dụng **JDK 17 standard library**. Mục 18 cung cấp thêm một chương trình Java 17 độc lập có `javac`/`java`.

### 11.4. Vì sao renderIndex dùng RELATIVE?

Output chứa:

~~~text
a.txt
sub/b.txt
~~~

Nếu đổi `sub/b.txt` thành `archive/b.txt`, output cần đổi path. Do đó `NAME_ONLY` hoặc `NONE` là **không đúng**. Nếu di chuyển toàn bộ workspace từ `/home/alice` sang `/ci/agent` mà relative files/contents không đổi, output phải giống nhau, vì thế `ABSOLUTE` không cần thiết.

### 11.5. Vì sao hashInput dùng NONE?

Task hash raw `bytes` và chỉ xuất chuỗi digest, không ghi input filename. Hai file:

~~~text
src/records/a.txt
src/renamed/input-data.txt
~~~

nếu bytes giống nhau, output hash giống nhau. Không cần đưa đường dẫn vào cache key. `PathSensitivity.NONE` là semantic declaration chính xác **vì implementation tuân thủ**.

Nếu sửa task để output thành `filename + ":" + hex`, phải thay path sensitivity hoặc khai filename làm `@Input` riêng.

### 11.6. Vì sao renderIndex normalized line endings?

Task đọc UTF-8 text:

~~~kotlin
.replace("\r\n", "\n")
.replace('\r', '\n')
~~~

Sau đó mới tạo output. Vì vậy CRLF/LF không làm thay đổi output khi logical lines giống nhau. Annotation `@NormalizeLineEndings` nhất quán với behavior.

`trimEnd('\n')` làm output index bỏ newline cuối nội dung mỗi file. Điều này **không có nghĩa Gradle tự bỏ qua những newline khác biệt khác**. Thay đổi số trailing blank lines có thể vẫn gây fingerprint khác, dù action có thể xuất giống nhau; đó là cache miss không cần thiết chứ không gây sai output. Khi muốn normalization phức tạp hơn, nên thiết kế input model/transform rõ ràng.

### 11.7. Task output deterministic

`records.sort()` bảo đảm file iteration order của `Files.walk` (không được hứa là ổn định) không làm output đổi thứ tự. `Files.writeString` ghi UTF-8, header/records không chứa current time, absolute path, env biến động hay random numbers.

Đối với `hashInput`, SHA-256 của bytes là deterministic. Hai tasks không viết chồng lên cùng output path.

### 11.8. Giới hạn demo

- Source files được giả định là UTF-8 text hợp lệ.
- Thư mục không dùng symlink/phức tạp permission behavior.
- Ví dụ dùng JDK 17 trở lên và Gradle version hỗ trợ APIs.
- Cache relocation có thể phụ thuộc thêm task implementation classpath/toolchain/Gradle version; path sensitivity đúng **chưa tự bảo đảm** cache hit qua mọi máy.
- Đây là ví dụ hiểu input normalization, không phải full production file indexing tool.

## 12. Chạy lab và đọc kết quả chính xác

Đứng trong `normalization-lab`. Nếu project mới chưa có Gradle Wrapper thì dùng bản Gradle đã cài:

~~~bash
gradle --build-cache clean renderIndex hashInput
~~~

Sau khi thành công, file:

~~~text
build/generated/index.txt
~~~

có **nội dung chính xác** (với files mẫu đã khai):

~~~text
INDEX_V1
a.txt=apple
sub/b.txt=banana
~~~

Đây là **nội dung file**, không phải toàn bộ stdout Gradle. Hash output:

~~~text
build/hash/a.sha256
~~~

chứa một chuỗi SHA-256 hex của bytes thật trong `src/records/a.txt` và một newline. **Không cung cấp hash cố định giả** vì việc file có newline cuối hay không làm bytes và digest khác nhau.

### 12.1. Đọc outputs

Linux/macOS:

~~~bash
cat build/generated/index.txt
cat build/hash/a.sha256
~~~

Windows PowerShell:

~~~powershell
Get-Content .\build\generated\index.txt
Get-Content .\build\hash\a.sha256
~~~

### 12.2. Chạy lần hai không đổi inputs

~~~bash
gradle --build-cache renderIndex hashInput
~~~

Nếu không có gì thay đổi và output files còn nguyên, Gradle thường hiển thị:

~~~text
> Task :renderIndex UP-TO-DATE
> Task :hashInput UP-TO-DATE
~~~

Outcome này không phải hứa hẹn cho mọi phiên bản/toolchain hoặc khi input/output đã bị thay. Hãy nhìn task outcomes thực tế của môi trường bạn.

### 12.3. Xóa outputs rồi thử build cache

~~~bash
gradle --build-cache clean renderIndex hashInput
~~~

Nếu đã có matching cache entries, hai tasks có thể hiển thị:

~~~text
> Task :renderIndex FROM-CACHE
> Task :hashInput FROM-CACHE
~~~

`clean` xóa build outputs nhưng **không** xóa local build cache. Nếu cache chưa được populate, task có thể thực thi bình thường; `FROM-CACHE` không phải kết quả chắc chắn sau một lần chạy.

### 12.4. Bật --info để tìm lý do execution

~~~bash
gradle --build-cache renderIndex --info
~~~

Gradle có thể in những lý do task không up-to-date, cache không được dùng hoặc input property changed. Các thông điệp cụ thể thay theo Gradle version và task implementation; không dùng một literal log line làm API contract.

### 12.5. Một tài liệu hữu ích để kiểm lẫn lộn

**`UP-TO-DATE` không chứng minh build cache hoạt động.**

**`FROM-CACHE` không chứng minh task action vừa chạy.**

**`EXECUTED` không đồng nghĩa Gradle bỏ qua normalization** — đôi khi input thật sự đã thay đổi hoặc không có matching cache entry.

## 13. Thí nghiệm thay đổi file paths và bytes

Với project lab đúng như mục 11, các thí nghiệm dưới đây giúp thấy sự khác biệt giữa `NONE` và `RELATIVE`. Làm từng thí nghiệm và **khôi phục** file/build script trước khi thử bước khác.

### 13.1. Thay đổi bytes của input

Đổi `src/records/a.txt` từ:

~~~text
apple
~~~

thành:

~~~text
orange
~~~

Chạy:

~~~bash
gradle --build-cache renderIndex hashInput
~~~

Hai tasks đều phải xét input content khác (trừ cache có output matching cho content mới): `renderIndex` tạo line `a.txt=orange`, `hashInput` tạo SHA-256 mới. Đây là bằng chứng `NONE` **không bỏ kiểm content**.

### 13.2. Đổi relative hierarchy

Giữ bytes của `b.txt` nhưng chuyển:

~~~text
src/records/sub/b.txt
~~~

thành:

~~~text
src/records/archived/b.txt
~~~

`renderIndex` dùng `RELATIVE`. Nội dung output phải đổi từ:

~~~text
sub/b.txt=banana
~~~

thành:

~~~text
archived/b.txt=banana
~~~

Nếu khai sai `NONE`/`NAME_ONLY` cho directory tree, Gradle có thể xem normalized inputs không đổi dù output logic đã đổi.

### 13.3. Đổi absolute checkout root

Copy **toàn bộ project** sang directory khác với cùng input files, build script và Gradle toolchain. Vì `renderIndex` dùng `RELATIVE` và `hashInput` dùng `NONE`, bản thân hai file-input properties không làm cache key lệ thuộc absolute checkout path.

Tuy nhiên để **thực sự đạt FROM-CACHE** còn cần:

- Task implementation/cache key giống.
- Cùng Gradle/plugin versions phù hợp.
- Các other declared inputs giống.
- Output caching được bật và cache entry tồn tại.
- Không có absolute path trong input properties khác/task implementation.
- Output bytes ổn định và không có external side effects.

Đừng coi “copy project, chưa thấy FROM-CACHE” là bằng chứng PathSensitivity không hoạt động; cần đọc diagnostics.

### 13.4. Thay tên input file nhưng giữ bytes

Giả sử `hashInput` được cấu hình để dùng file `src/copy/renamed.txt` với **bytes giống a.txt**. Vì task chỉ tạo raw SHA-256, `NONE` là đúng: basename change không làm thay đổi file input normalized fingerprint.

Với `renderIndex`, rename `a.txt` thành `first.txt` sẽ đổi output index, vì output giữ relative filename. `RELATIVE` nhận diện điều đó.

### 13.5. Thay line endings

Chuyển `a.txt` từ LF sang CRLF nhưng không đổi logical text. Vì `renderIndex` khai `@NormalizeLineEndings` và task action normalize line endings, output logic không đổi. `hashInput` **đọc raw bytes** và không khai line-ending normalization, nên SHA-256 của raw file bytes sẽ khác.

Đây là bài kiểm **hai tasks dùng cùng file nhưng có input semantics khác nhau**. Không có một “global normalization đúng cho mọi consumer”.

### 13.6. Thêm empty folder

Tạo `src/records/unused/` trống. `renderIndex` không đọc empty directories để tạo records và có `@IgnoreEmptyDirectories`, nên thay đổi chỉ ở thư mục rỗng không nên làm nhiệm vụ đổi output. Nếu task thực tế cần reproduce empty directory layout thì **không** dùng annotation này.

## 14. Java 17 độc lập: mô phỏng khác biệt path fingerprints

`PathSensitivity` là Gradle API, nhưng có thể minh họa ý nghĩa **bằng Java 17 thuần JDK**. Chương trình sau tự tạo các files ở hai checkout roots khác nhau, so absolute/relative/base names và raw bytes, in kết quả xác định. Nó **không gọi Gradle internals**, chỉ minh họa semantic so sánh.

### 14.1. PathComparisonDemo.java

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.Objects;
import java.util.stream.Stream;

public final class PathComparisonDemo {
    private PathComparisonDemo() {
    }

    public static void main(String[] args) throws IOException {
        Path workspace = Files.createTempDirectory("path-input-demo-");
        try {
            Path rootA = workspace.resolve("checkout-A");
            Path rootB = workspace.resolve("checkout-B");
            Path first = rootA.resolve("templates/mail/notice.txt");
            Path second = rootB.resolve("templates/mail/notice.txt");
            Path moved = rootB.resolve("templates/other/notice.txt");

            Files.createDirectories(first.getParent());
            Files.createDirectories(second.getParent());
            Files.createDirectories(moved.getParent());

            Files.writeString(first, "hello", StandardCharsets.UTF_8);
            Files.writeString(second, "hello", StandardCharsets.UTF_8);
            Files.writeString(moved, "hello", StandardCharsets.UTF_8);

            System.out.println("ABSOLUTE_EQUAL="
                    + first.toAbsolutePath().equals(second.toAbsolutePath()));
            System.out.println("RELATIVE_EQUAL="
                    + rootA.relativize(first).equals(rootB.relativize(second)));
            System.out.println("NAME_ONLY_EQUAL="
                    + first.getFileName().equals(second.getFileName()));
            System.out.println("CONTENT_EQUAL="
                    + Objects.deepEquals(
                            Files.readAllBytes(first),
                            Files.readAllBytes(second)
                    ));
            System.out.println("MOVED_RELATIVE_EQUAL="
                    + rootA.relativize(first).equals(rootB.relativize(moved)));
            System.out.println("MOVED_NAME_ONLY_EQUAL="
                    + first.getFileName().equals(moved.getFileName()));
        } finally {
            try (Stream<Path> paths = Files.walk(workspace)) {
                for (Path path : paths.sorted(Comparator.reverseOrder())
                                      .toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
~~~

**Lưu ý Java arrays:** `Objects.deepEquals(byte[], byte[])` so nội dung array theo deep comparison, nên hợp lệ cho ví dụ. Có thể dùng `java.util.Arrays.equals(...)` để rõ hơn. Cả hai files được ghi cùng raw bytes `hello`.

### 14.2. Compile và run

Linux/macOS:

~~~bash
javac --release 17 PathComparisonDemo.java
java PathComparisonDemo
~~~

Windows PowerShell:

~~~powershell
javac --release 17 .\PathComparisonDemo.java
java PathComparisonDemo
~~~

**Stdout chính xác**:

~~~text
ABSOLUTE_EQUAL=false
RELATIVE_EQUAL=true
NAME_ONLY_EQUAL=true
CONTENT_EQUAL=true
MOVED_RELATIVE_EQUAL=false
MOVED_NAME_ONLY_EQUAL=true
~~~

Cần có quyền tạo/xóa temporary directory của user. Chương trình tạo temp root ngẫu nhiên nhưng **không in root path**, nên stdout ổn định.

### 14.3. Vì sao Java demo không thay task test?

`PathComparisonDemo` chỉ so paths/bytes trực tiếp bằng JDK, **không** tính Gradle task fingerprint/build cache key. Muốn chứng minh task dùng normalization đúng, phải chạy Gradle tasks, thay inputs theo từng thí nghiệm và kiểm outputs/task outcomes. Những yếu tố như task implementation classpath và normalized classpath order không được chương trình mô phỏng.

## 15. Runtime API thay cho annotations

Ngoài typed task class, Gradle cho phép khai task inputs/outputs khi đăng ký:

~~~kotlin
import org.gradle.api.tasks.PathSensitivity

tasks.register("inspectTemplates") {
    inputs.files(fileTree("src/templates"))
        .withPropertyName("templates")
        .withPathSensitivity(PathSensitivity.RELATIVE)
        .ignoreEmptyDirectories()

    outputs.file(
        layout.buildDirectory.file("reports/templates.txt")
    )
}
~~~

**Đây là fragment khai input/output, không phải task đầy đủ:** chưa có `@TaskAction`/`doLast` xử lý files và chưa tạo output. Nó minh họa runtime API `inputs.files(...).withPathSensitivity(...)`.

Khi viết logic có nhiều behaviors, nên dùng typed task class với properties/annotations vì:

- Input/output contract nhìn rõ trong một class.
- Dễ test task implementation.
- Dễ tái sử dụng qua convention/binary plugin.
- Hỗ trợ lazy configuration và task validation tốt hơn.
- Không phải capture `Project`/mutable buildscript state trong task action.

### 15.1. Không khai cùng property hai lần

Nếu task class đã annotate `@get:InputFiles` và lại đăng ký runtime input cùng tên `sourceFiles` một cách trùng lặp, Gradle có thể báo lỗi hoặc tính snapshot không như dự định. Chọn một mô hình khai báo nhất quán cho cùng input property.

### 15.2. Khi nào dùng runtime DSL?

Phù hợp để bổ sung input cho task type có sẵn hoặc thử một ad-hoc task nhỏ. Nhưng task chuyên biệt đáng bảo trì nên gom input/output contract vào class và tránh side effects trong configuration.

## 16. Groovy DSL: cùng semantics

Nếu dự án dùng `build.gradle` thay vì `build.gradle.kts`, annotations `@InputFile`/`@PathSensitive` trong Java/Groovy/Kotlin task types vẫn mang **cùng ý nghĩa**. Cú pháp cấu hình runtime API bằng Groovy:

~~~groovy
import org.gradle.api.tasks.PathSensitivity

tasks.register('inspectTemplates') {
    inputs.files(fileTree('src/templates'))
        .withPropertyName('templates')
        .withPathSensitivity(PathSensitivity.RELATIVE)
        .ignoreEmptyDirectories()

    outputs.file(layout.buildDirectory.file('reports/templates.txt'))
}
~~~

Đây là fragment tương đương mục 15, cũng **chưa có task action**.

### 16.1. Khai normalization runtimeClasspath trong Groovy DSL

~~~groovy
normalization {
    runtimeClasspath {
        ignore 'build-info.properties'
        metaInf {
            ignoreAttribute 'Build-Time'
        }
    }
}
~~~

Tương đương về mục tiêu với Kotlin DSL. Nó tác động **runtime classpath fingerprint** trong project nơi được cấu hình, không tự rewrite Java class files/JAR.

### 16.2. PathSensitive trong Java task type dùng chung với cả hai DSL

~~~java
package demo.gradle;

import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.tasks.InputFile;
import org.gradle.api.tasks.PathSensitive;
import org.gradle.api.tasks.PathSensitivity;

public abstract class ContentTask extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.NONE)
    public abstract RegularFileProperty getInputFile();
}
~~~

Đây là **class skeleton**, không có `@OutputFile` hoặc `@TaskAction` nên không phải runnable task đầy đủ. Nó cho thấy annotations thuộc Gradle task type **không phụ thuộc Groovy/Kotlin DSL** ở consumer.

## 17. RELATIVE có giới hạn với nhiều input roots

Nếu một task nhận hai directories:

~~~text
src/main/resources/config.json
src/test/resources/config.json
~~~

và cấu hình mỗi root riêng, normalized path bên trong cả hai có thể là `config.json`. Nếu output cần phân biệt main/test, hãy:

- Khai hai input properties riêng, ví dụ `mainResources` và `testResources`, hoặc
- Có một root chung mà normalized paths bao gồm `main/resources/...` và `test/resources/...`, hoặc
- Thêm explicit scope/identity input trong task model.

**Không** dựa vào những chi tiết implementation khó đoán để phân biệt inputs có same basename/same relative path khi chính task dùng identity đó.

### 17.1. NAME_ONLY và collision

Nếu collection có:

~~~text
src/main/templates/index.txt
src/test/templates/index.txt
~~~

và task output phụ thuộc **cả path và nội dung theo từng nhóm**, `NAME_ONLY` có thể mất parent hierarchy. Điều này dễ làm Gradle không phát hiện một path move quan trọng.

Để giữ semantics, dùng `RELATIVE` với root đúng hoặc input properties phân tách.

### 17.2. PathSensitivity.NONE không tự loại duplicated files

`NONE` bỏ path, không ra lệnh Gradle **deduplicate input files** theo nội dung, không giảm dung lượng file collection và không tự thay algorithm của task. Nó chỉ quyết định thành phần path trong fingerprints. Đừng dùng NONE để suy ra task sẽ xử lý một file duy nhất từ một tập nhiều file có cùng bytes.

## 18. JavaCompile, tests và archive tasks: áp dụng đúng thực tế

### 18.1. Java compile avoidance

Gradle `JavaCompile` sử dụng compile classpath fingerprint thông minh. Ví dụ module `:api` có class:

~~~java
package demo.api;

public final class MathApi {
    public static int doubleIt(int value) {
        return value * 2;
    }
}
~~~

Consumer `:app` compile với `MathApi.doubleIt(int)`. Nếu `:api` đổi method body từ `return value * 2` sang `return value + value` mà public API signature vẫn giữ, Gradle có thể tránh recompile consumer vì ABI không đổi.

Nhưng `:app` runtime tests vẫn có thể cần chạy lại, bởi behavior dependency thay. Đây là lý do `@CompileClasspath` và `@Classpath` **khác nhau**.

### 18.2. Runtime test classpath

Gradle `Test` task thường có runtime classpath; nếu class bytes đổi thì tests có thể cần chạy lại. Nếu chỉ JAR timestamps/entry ordering đổi nhưng contained entries có cùng semantic contents, runtime classpath normalization có thể tránh rerun không cần thiết.

Không được blanket ignore resources như `META-INF/services/**` vì `ServiceLoader`/framework discovery có thể phụ thuộc chúng.

### 18.3. Resource processing/copy/ZIP

Task copy resources mà output giữ directory hierarchy cần **RELATIVE** (ở custom inputs). Task `jar`/`zip` được Gradle/plug-in implement sẵn với input/output rules chuyên biệt; không thể sửa mọi built-in fingerprint đơn giản bằng cách gắn annotation từ build script.

Nếu task build ZIP mà raw ZIP timestamps là một phần output mong muốn, hãy thiết kế explicit reproducibility. Input normalization không tự sửa output ZIP timestamps.

### 18.4. Gradle archive reproducibility và normalization là hai vấn đề

- **Reproducible archive**: cố làm output ZIP/JAR bytes giống nhau giữa các builds cùng inputs.
- **Classpath normalization**: cho phép Gradle xem hai JAR inputs có semantic contents tương đương dù ZIP timestamps/order khác.

Một JAR không byte-identical vẫn có thể normalized-equivalent cho **runtime classpath**, nhưng đó không chứng minh hai files có cùng SHA-256. Đối với artifact signing/checksum, phải hash **raw bytes**.

## 19. Phân biệt Configuration Cache, Build Cache và fingerprint

| Chức năng | Nội dung được tái sử dụng | PathSensitivity liên quan thế nào? |
| --- | --- | --- |
| Up-to-date check | Bỏ chạy task khi local inputs/outputs không đổi | Dùng normalized input snapshots |
| Build Cache | Phục hồi task output từ cache key | Dùng normalized inputs, quyết định relocatability |
| Incremental task | Chỉ xử lý changed inputs | Path semantics ảnh hưởng file-change identification |
| Configuration Cache | Reuse configuration/task graph | Không phải output file cache; có constraints riêng |
| Dependency cache | Downloaded modules/artifacts | Không phải task output build cache |
| Artifact transforms cache | Transformed dependencies | Có normalization/caching rules riêng |

Đừng thấy một Gradle command nhanh hơn rồi kết luận đúng nhờ `PathSensitivity`. Có thể vì daemon warmed-up, compiler incremental, dependency caches hoặc Configuration Cache.

### 19.1. Configuration Cache được bật bằng lệnh khác

~~~bash
gradle renderIndex --configuration-cache
~~~

Lần thứ hai có thể reuse configuration nếu scripts/tasks đáp ứng constraints. Nhưng output task có thể vẫn EXECUTE nếu input thay. Ngược lại, task có thể `UP-TO-DATE` dù Configuration Cache chưa bật.

### 19.2. Build cache bật độc lập

~~~bash
gradle renderIndex --build-cache
~~~

Có thể kết hợp:

~~~bash
gradle renderIndex --build-cache --configuration-cache
~~~

Chúng tối ưu **hai phần khác nhau** của build lifecycle.

## 20. False cache hits nguy hiểm hơn cache misses

### 20.1. False miss

Task output không đổi, nhưng Gradle coi input khác → chạy lại.

Ví dụ: `ABSOLUTE` thay vì `RELATIVE` khiến workspace relocation làm cache miss. Hậu quả chủ yếu là **chậm hơn**.

### 20.2. False hit

Output **đáng lẽ phải đổi**, nhưng Gradle coi normalized input giống nhau → skip task hoặc phục hồi output cũ.

Ví dụ: Task tạo index chứa relative paths, nhưng khai `@PathSensitive(NONE)` cho directory input. Chuyển `sub/b.txt` sang `archived/b.txt`, giữ bytes; Gradle có thể dùng kết quả cache cũ dù index lẽ ra phải đổi.

Hậu quả có thể là:

- Sai binary/release artifact.
- Resource bị thiếu hoặc đóng gói sai folder.
- Codegen output từ template cũ.
- Tests không chạy lại khi inputs có ảnh hưởng.
- Build thành công giả.
- Lỗi tái hiện rất khó vì hiện ra khi cache đã warm.

**Quy tắc:** nếu chưa chứng minh normalization an toàn, hãy chọn mức bảo thủ hơn rồi tối ưu có kiểm thử.

### 20.3. Rule ignore() cũng có thể tạo false hit

Nếu task test đọc `build-info.properties` để xác định expected behavior nhưng build logic cấu hình:

~~~kotlin
normalization {
    runtimeClasspath {
        ignore("build-info.properties")
    }
}
~~~

thì thay đổi file có thể không invalidated runtime classpath fingerprint. Đó là bug ở build configuration.

**Không** ignore input chỉ vì file hay thay; cần chứng minh file **không ảnh hưởng outputs của consumer task**.

### 20.4. Secrets và network inputs

Task đọc secret token hoặc API response có thể cho output khác dù normalized files không đổi. Cần khai inputs thích hợp và xem có nên **disable caching** không vì security, nondeterminism hoặc side effects. Đừng lưu secrets trong build cache key logs hoặc artifacts một cách bất cẩn.

## 21. Diagnostic workflow khi task rerun bất ngờ

### Bước 1. Xác định task outcome

~~~bash
gradle --build-cache renderIndex --info
~~~

Quan sát EXECUTED, UP-TO-DATE, FROM-CACHE, NO-SOURCE hay SKIPPED thực tế.

### Bước 2. Xem task có declared inputs/outputs đúng không

Kiểm custom task type annotations:

~~~text
@Input / @InputFile / @InputDirectory / @InputFiles
@PathSensitive / @Classpath / @CompileClasspath
@OutputFile / @OutputDirectory
@CacheableTask hoặc caching policy
~~~

Nếu task không khai output, up-to-date/caching behavior khác task có outputs. Không tự gắn `@CacheableTask` vào task có side effects không thể replay.

### Bước 3. Kiểm input content vs metadata

Có file nào bị regenerate mỗi lần build?

- Generated timestamps/UUID.
- ZIP/JAR metadata dù Java classes không đổi.
- Temporary absolute paths.
- Environment variables/Gradle properties.
- Plugin/toolchain version.
- File order không deterministic.
- Untracked generated file.

### Bước 4. Xem normalization mode

Đối với file input, xem `ABSOLUTE` có gây relocation misses không. Với directory tree, `RELATIVE` thường phù hợp. Với raw-byte single-file transform, `NONE` có thể thích hợp.

### Bước 5. Xác minh output không phụ thuộc những thứ đã ignore

Đọc `@TaskAction`/compiler/resource processing logic. Nếu output chèn filename/relative path, đừng ignore phần path đó.

### Bước 6. Dùng build scan / Develocity khi có

Gradle build scan có thể cung cấp phân tích cache key/task inputs và nguyên nhân cache miss. Chỉ dùng dịch vụ được tổ chức cho phép; scans/logs có thể chứa tên đường dẫn, metadata hoặc các dữ liệu nhạy cảm theo cách cấu hình. Không upload diagnostics nội bộ lên trang công khai vô điều kiện.

### Bước 7. Tạo một negative test

Rename path mà task output phải thay, giữ raw bytes giống nhau. Kiểm Gradle nhận ra sự thay đổi. Đây là cách bắt **false hit** rõ hơn việc chỉ đo tốc độ.

## 22. Testing bằng Gradle TestKit

Một reusable plugin/task type nên có functional tests cho caching/relocatability.

### 22.1. Các test cases thiết yếu

1. **First execution**: task tạo output expected.
2. **Second execution**: inputs không đổi → thường `UP-TO-DATE`.
3. **Input content change**: output và task state thay tương ứng.
4. **Relative path rename**: task `RELATIVE` nhận ra change.
5. **Absolute workspace relocation**: task `RELATIVE`/`NONE` có thể reuse cached outputs nếu all other cache key inputs match.
6. **Wrong path normalization negative test**: task output khác nhưng fingerprint không khác → test phải phát hiện bug.
7. **CRLF vs LF**: task có `@NormalizeLineEndings` phải cho same output.
8. **Classpath reorder**: `@Classpath` cần phản ánh runtime search ordering.
9. **ABI-only change**: thử compile avoidance nếu task dùng `@CompileClasspath`.
10. **Declared output cleanup**: task không ghi chồng/đặt output ngoài declared paths.

### 22.2. TestKit approach (pseudo-steps)

Tạo temporary directories A/B, mỗi directory có same build script và source inputs. Dùng GradleRunner chạy:

~~~text
--build-cache renderIndex
--build-cache renderIndex
--build-cache clean renderIndex
~~~

Quan sát `TaskOutcome.SUCCESS`, `TaskOutcome.UP_TO_DATE` hoặc `TaskOutcome.FROM_CACHE` theo trạng thái cache. Với test cross-workspace cần cấu hình **cùng build cache location** cho cả fixtures hoặc dùng shared cache backend; mặc định test temp dirs có thể dùng Gradle user homes khác nhau, làm kết luận sai.

Đây là **quy trình TestKit**, không phải một Java TestKit test độc lập; để chạy cần plugin project và test framework set up. Trọng tâm bài là đảm bảo bài kiểm semantic normalization có tính chẩn đoán, không giả định một outcome cố định khi cache còn lạnh.

### 22.3. Output equality quan trọng hơn chỉ task outcome

Một task có thể `FROM-CACHE` nhưng output **không đúng** do normalization lỏng. Với mọi test task type mới, ngoài outcome cần assert exact output content/bytes. Có thể dùng `Files.readString`/`Files.readAllBytes` trong Java test để so.

## 23. Multi-project build và normalization policy

Trong multi-project Gradle, một custom plugin có thể khai reusable task type cho nhiều modules.

Ví dụ:

~~~text
root/
├── settings.gradle.kts
├── build-logic/
├── api/
└── app/
~~~

Mỗi project dùng convention plugin để tự đăng ký `renderIndex` với local `src/records` và output local `build/generated`. Nếu task type có `@CacheableTask`, `RELATIVE` inputs và deterministic action, các modules/workspaces có thể chia sẻ cache outputs khi cache keys thật sự tương đương.

### 23.1. Cần giữ input identity rõ

Đừng để một convention plugin giả định mọi module có same input tree nếu không đúng. Cho phép mỗi module configure `sourceDirectory` và các semantic inputs qua managed properties.

### 23.2. Cấu hình normalization tập trung nhưng tránh cross-project mutation

Ví dụ convention plugin áp dụng trong mỗi target project:

~~~kotlin
normalization {
    runtimeClasspath {
        ignore("build-info.properties")
    }
}
~~~

Chỉ nên đặt policy này vào plugin **nếu mọi consumer áp plugin thực sự coi file đó irrelevant**. Không dùng `allprojects { }` từ root để bỏ qua metadata trên mọi module có behavior khác nhau.

### 23.3. Task dependencies qua provider outputs

Nếu một task dùng output của task khác:

~~~kotlin
someTask.inputFile.set(
    producerTask.flatMap { it.outputFile }
)
~~~

đây là **mẫu fragment** với typed task properties/producer task providers đã khai ở nơi khác; không phải runnable line độc lập. Gradle suy ra task dependency và snapshot file output thật. Tránh tự tính `file("other/build/...")` trong task action mà không khai dependency/input.

## 24. Những lỗi phổ biến và cách sửa

### Lỗi 1. Không đặt @PathSensitive

`@InputFile` dùng ABSOLUTE mặc định, gây cache miss khi workspace path đổi.

**Sửa:** dùng `NONE` khi output chỉ phụ thuộc bytes của một file, `RELATIVE` khi cần relative path semantics.

### Lỗi 2. Mặc định NONE cho mọi thứ để tăng cache hit

Task giữ folder hierarchy trong output có thể nhận false hit khi file di chuyển.

**Sửa:** chọn theo output behavior; directory trees thường dùng RELATIVE.

### Lỗi 3. Nhầm NONE nghĩa là Gradle bỏ kiểm file

**Sửa:** content vẫn được xét; NONE chỉ ignore path.

### Lỗi 4. Chọn NAME_ONLY cho template hierarchy

`templates/admin/index.html` và `templates/user/index.html` cùng basename; path hierarchy có ý nghĩa.

**Sửa:** dùng RELATIVE, hoặc khai metadata khác nếu thật sự chỉ cần tên.

### Lỗi 5. ABSOLUTE là “an toàn nhất” nên giữ vĩnh viễn

ABSOLUTE có thể đúng về correctness nhưng giảm build cache relocatability.

**Sửa:** kiểm task output có cần absolute path không; chuyển sang relative model khi an toàn.

### Lỗi 6. Gắn @Classpath cho mọi ZIP/JAR input

Task kiểm raw JAR SHA-256/ZIP signatures, nhưng classpath normalization bỏ ZIP timestamps/order.

**Sửa:** dùng raw file input `@InputFile + @PathSensitive(NONE)`.

### Lỗi 7. @CompileClasspath cho runtime test

Test phụ thuộc method behavior/resources; compile ABI normalization có thể bỏ qua thay đổi runtime có nghĩa.

**Sửa:** dùng `@Classpath` cho runtime classpath.

### Lỗi 8. Ignore toàn bộ META-INF

Có thể loại `META-INF/services` hoặc manifest metadata ảnh hưởng runtime ra khỏi fingerprint.

**Sửa:** ignore chỉ attributes/properties đã chứng minh irrelevant.

### Lỗi 9. Bỏ qua build-info.properties dù test đọc nó

**Sửa:** ngừng ignore file, hoặc tách test policy để test có input model đúng.

### Lỗi 10. @NormalizeLineEndings nhưng action copy raw bytes

CRLF vs LF tạo output bytes khác dù Gradle coi input tương đương.

**Sửa:** action cũng normalize output, hoặc bỏ annotation.

### Lỗi 11. Không khai encoding là @Input

Task hành vi phụ thuộc `charset` nhưng đọc biến environment thay vì task property.

**Sửa:** explicit `Property<String>` hoặc enum encoding và `@Input`.

### Lỗi 12. Output chứa currentTimeMillis

Cùng normalized inputs có thể tạo output khác mỗi lần, phá reproducibility.

**Sửa:** bỏ volatile data, tạo deterministic output hoặc đánh dấu task non-cacheable nếu thực sự phụ thuộc thời gian.

### Lỗi 13. Hai tasks ghi chung output directory

Gradle khó xác định task ownership, output caching có thể bị disable.

**Sửa:** dùng outputs tách biệt; một task một output location contract.

### Lỗi 14. Dùng project.file(...) trong TaskAction

Không khai input path bằng managed property, có thể gây Configuration Cache problems và hidden inputs.

**Sửa:** inject `RegularFileProperty/DirectoryProperty`, khai annotation, truy property tại action.

### Lỗi 15. File collection trùng relative paths từ nhiều roots

Task cần phân biệt source categories nhưng fingerprint thiếu identity.

**Sửa:** dùng property names riêng hoặc root paths đầy đủ, bổ sung explicit identity.

### Lỗi 16. Di chuyển file nhưng chỉ so file bytes

Task output chứa relative path nên phải đổi; hash content không đủ.

**Sửa:** RELATIVE thay vì NONE.

### Lỗi 17. Chỉ nhìn UP-TO-DATE rồi kết luận cache tốt

Up-to-date dùng local history, không chứng minh remote/shared cache reuse.

**Sửa:** thử clean + --build-cache và kiểm FROM-CACHE, kiểm output correctness.

### Lỗi 18. Chỉ nhìn FROM-CACHE rồi kết luận output đúng

Normalization khai sai có thể tạo false hit.

**Sửa:** assert exact outputs sau relocation/rename/content changes.

### Lỗi 19. Xóa ~/.gradle để “sửa” cache misses

Việc xóa cache có thể làm chậm hơn và không thay đổi normalized input semantics.

**Sửa:** inspect declared inputs, task implementation và fingerprint diagnostics trước.

### Lỗi 20. Ignore output file path

`@PathSensitive` là annotation cho input files, không thay `@OutputFile`.

**Sửa:** khai outputs rõ, deterministic và không overlapping.

### Lỗi 21. Bật --configuration-cache để chữa build cache

Hai caches khác nhau.

**Sửa:** xác định task output caching vs configuration caching trước khi tối ưu.

### Lỗi 22. Không dùng @CacheableTask nhưng chờ FROM-CACHE

Custom task mặc định không phải mọi loại đều được cache; một số bị disable theo policy.

**Sửa:** đánh giá task có deterministic outputs/declared inputs/outputs hay không, rồi dùng `@CacheableTask` khi phù hợp.

### Lỗi 23. Runtime classpath reorder nhưng vẫn kỳ vọng same fingerprint

Classpath lookup precedence có thể thay đổi behavior.

**Sửa:** @Classpath có xét entry order; không normalize order vô điều kiện.

### Lỗi 24. Chỉ kiểm local workspace

Task gặp cache miss hoặc false hit khi CI checkout path khác.

**Sửa:** functional tests across relocations và shared cache setup rõ ràng.

## 25. Bài tập thực hành có đáp án

### Bài 1 — Chọn mức cho raw SHA-256

Task đọc `config.txt`, chỉ tạo SHA-256 của bytes.

**Đáp án:** `@InputFile + @PathSensitive(NONE)` vì output không chứa filename/path.

### Bài 2 — Chọn mức cho asset index

Task tạo danh sách `relative/path=file-content`.

**Đáp án:** `RELATIVE` vì relative hierarchy là output.

### Bài 3 — Vì sao không chọn ABSOLUTE cho source tree?

**Đáp án:** Full workspace paths khác giữa developer/CI sẽ làm fingerprint khác không cần thiết khi output không phụ thuộc absolute location.

### Bài 4 — NAME_ONLY và rename parent folder

`src/mail/a.txt` đổi thành `src/archive/a.txt`, bytes không đổi.

**Đáp án:** NAME_ONLY có thể coi normalized path không đổi; chỉ đúng nếu output không phụ thuộc parent directories.

### Bài 5 — NONE có theo dõi bytes không?

**Đáp án:** Có. NONE ignore paths, không ignore file contents.

### Bài 6 — Source directory relocation

Hai workspaces chứa cùng `src/templates/sub/t.txt` và bytes giống nhau.

**Đáp án:** RELATIVE fingerprints có thể match; ABSOLUTE fingerprints khác do paths khác.

### Bài 7 — Classpath order

Hai JARs A/B có cùng class name, đổi thứ tự classpath entries.

**Đáp án:** Runtime classpath order quan trọng và `@Classpath` xét order.

### Bài 8 — Compile avoidance

Dependency đổi private method body nhưng giữ public ABI.

**Đáp án:** `@CompileClasspath` có thể xem API tương đương và tránh consumer recompile; runtime behavior/tests có thể vẫn thay.

### Bài 9 — JAR timestamps

Hai JAR chứa cùng class/resources bytes nhưng entry ZIP timestamps khác.

**Đáp án:** `@Classpath` có thể normalize timestamps; raw SHA-256 input phải xem bytes khác.

### Bài 10 — Ignore runtime property

`build-info.properties` đổi CI job ID, test không đọc và output test không phụ thuộc.

**Đáp án:** Có thể cấu hình `normalization.runtimeClasspath.ignore("build-info.properties")` sau khi xác minh an toàn.

### Bài 11 — Test đọc build-info.properties

**Đáp án:** Không ignore file; nếu ignore có nguy cơ false cache hit.

### Bài 12 — CRLF/LF

Task normalize CRLF thành LF trước khi tạo output.

**Đáp án:** Có thể dùng `@NormalizeLineEndings` nếu toàn bộ output semantics nhất quán.

### Bài 13 — Raw copy task

Task copy nguyên bytes, CRLF vs LF tạo output khác.

**Đáp án:** Không dùng `@NormalizeLineEndings` cho source đó.

### Bài 14 — Empty directories

Task chỉ đọc file contents, empty dirs không ảnh hưởng output.

**Đáp án:** `@IgnoreEmptyDirectories` có thể phù hợp.

### Bài 15 — Outcome thứ hai

Lần đầu task chạy, lần sau inputs/outputs không đổi.

**Đáp án:** Thường `UP-TO-DATE` nhờ local execution history; không cần `FROM-CACHE`.

### Bài 16 — Clean rồi chạy với --build-cache

**Đáp án:** Nếu task cacheable và key có entry, có thể `FROM-CACHE`; nếu cache cold sẽ chạy thật.

### Bài 17 — Cross-project build cache

Task chạy trên máy A và B với cùng relative inputs, cache shared, nhưng khác plugin version.

**Đáp án:** Có thể cache miss do implementation classpath/version khác; PathSensitivity đúng là cần thiết nhưng không đủ.

### Bài 18 — Prefix thay đổi

Task `renderIndex` đổi `prefix` từ `INDEX_V1` sang `INDEX_V2`.

**Đáp án:** `@Input` property đổi, Gradle phải tính task input khác và output header phải đổi.

### Bài 19 — Đọc undeclared config

Task action đọc một file ngoài directory đã khai input.

**Đáp án:** Là hidden input; Gradle có thể coi unchanged sai. Khai thêm file input property và path sensitivity đúng.

### Bài 20 — Task output chứa absolute path

Task report in absolute source path nhưng khai RELATIVE.

**Đáp án:** Normalization sai. Thiết kế report không chứa absolute path hoặc khai absolute path như input thật và chấp nhận non-relocatable behavior.

### Bài 21 — False hit hay false miss?

Task output phải đổi nhưng Gradle dùng cache cũ.

**Đáp án:** **False hit**, nguy hiểm về correctness. Task chạy lại dù output không đổi là **false miss**, chủ yếu gây chậm.

### Bài 22 — Java sample expected output

Chạy `PathComparisonDemo.java` của mục 14, dòng `MOVED_RELATIVE_EQUAL` là gì?

**Đáp án:**

~~~text
MOVED_RELATIVE_EQUAL=false
~~~

Vì hierarchy khác (`templates/mail` vs `templates/other`).

## 26. Checklist review custom Gradle task

| Câu hỏi | Khi nào đạt? |
| --- | --- |
| Task outputs đã khai? | `@OutputFile`/`@OutputDirectory` đúng path/ownership |
| Task inputs đã khai đủ? | Không đọc hidden files/env/time/network mà chưa kiểm model |
| Single file path? | Dùng NONE nếu output chỉ phụ thuộc raw contents |
| Directory hierarchy? | Dùng RELATIVE nếu relative structure ảnh hưởng output |
| ABSOLUTE có cần thật? | Chỉ dùng khi absolute location là input semantic |
| NAME_ONLY có thực sự đúng? | Task chỉ quan tâm basename, không parent hierarchy |
| Classpath là JVM classpath? | Dùng @Classpath, order/ZIP normalization đúng |
| Java compile ABI? | Dùng @CompileClasspath nếu chỉ compile API là input semantic |
| Runtime ignore rules? | Chỉ ignore metadata/resource thật sự irrelevant |
| Line endings? | @NormalizeLineEndings đồng thuận task output bytes |
| Empty dirs? | @IgnoreEmptyDirectories chỉ nếu task không tạo/quan tâm empty dirs |
| Cacheable? | @CacheableTask chỉ khi deterministic, replayable, đủ inputs/outputs |
| Stable output? | Sort iteration, pin encoding, không volatile timestamps/UUID |
| Multi-root inputs? | Input identity/path boundaries rõ |
| Test correctness? | Kiểm exact outputs sau rename/move/content change |
| Test cache? | Có case UP-TO-DATE/FROM-CACHE và relocation khi phù hợp |
| Configuration Cache? | Không dùng Project API sai trong task action |
| CI? | Shared cache bảo đảm trust, pin toolchains và kiểm cache keys |

**Kết luận:** `PathSensitivity` không phải “mẹo bật cache”, mà là **lời cam kết về những phần của file path thực sự ảnh hưởng tới output task**. `ABSOLUTE` giữ full path, `RELATIVE` giữ hierarchy tương đối, `NAME_ONLY` giữ basename và `NONE` bỏ path nhưng **vẫn tính content**. Với Java/JVM, `@Classpath` và `@CompileClasspath` cung cấp normalization sâu hơn; `normalization.runtimeClasspath` chỉ nên bỏ qua metadata **đã chứng minh vô nghĩa**. Chọn mức phù hợp với task behavior, khai inputs/outputs rõ và kiểm cả correctness lẫn build-cache reuse — đó mới là cách làm build tăng dần vừa nhanh vừa đáng tin.

## 27. Tài liệu chính thức

- [Gradle — Important Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html) — input normalization, PathSensitivity, runtime/compile classpath và relocatability.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html) — khuyến nghị NONE cho single input files, RELATIVE cho directories, tránh ABSOLUTE không cần thiết.
- [Gradle — Incremental Build and Task Inputs](https://docs.gradle.org/current/userguide/incremental_build.html) — input/output annotations, cache/up-to-date, input normalization và task dependency inference.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_builds.html) — `@Classpath`/`@CompileClasspath`, normalized classpaths, TaskInputs runtime API.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html) — cache keys, @CacheableTask, local/remote cache.
- [Gradle Javadoc — PathSensitivity](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/PathSensitivity.html) — exact meanings của ABSOLUTE, RELATIVE, NAME_ONLY, NONE.
- [Gradle Javadoc — PathSensitive](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/PathSensitive.html) — annotation cho normalized file paths.
- [Gradle Javadoc — NormalizeLineEndings](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/NormalizeLineEndings.html) — line-ending normalization.
- [Gradle Javadoc — RuntimeClasspathNormalization](https://docs.gradle.org/current/javadoc/org/gradle/normalization/RuntimeClasspathNormalization.html) — ignore patterns/properties.
- [Gradle Javadoc — MetaInfNormalization](https://docs.gradle.org/current/javadoc/org/gradle/normalization/MetaInfNormalization.html) — ignoreManifest/ignoreAttribute/ignoreProperty.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html) — typed tasks, properties, annotations và validation.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html) — khác task output caching và yêu cầu cho custom tasks.
- [Gradle — Testing Gradle Plugins](https://docs.gradle.org/current/userguide/testing_gradle_plugins.html) — Gradle TestKit và functional tests cho build logic.
- [Oracle Java SE 17 — Files API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html) — walk/readString/writeString và filesystem operations.
