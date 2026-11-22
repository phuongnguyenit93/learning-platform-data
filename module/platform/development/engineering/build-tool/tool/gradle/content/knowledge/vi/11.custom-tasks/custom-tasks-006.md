# Chuẩn hóa đường dẫn, nội dung và ảnh hưởng đến tính tái sử dụng của custom task Gradle

## 1. Mục tiêu và ý tưởng trung tâm

Khi bạn viết một custom task Gradle để sinh tài liệu, tạo mã nguồn, biên dịch dữ liệu hoặc đóng gói artifact, có một câu hỏi quan trọng: **hai lần chạy có cùng dữ liệu đầu vào có tạo ra cùng kết quả không, kể cả khi vị trí checkout, hệ điều hành hoặc môi trường CI khác nhau?**

Gradle không đơn thuần so sánh thời gian sửa file. Với task khai báo input/output hợp lệ, nó có thể tạo **fingerprint** từ input, kiểm tra up-to-date và, với task có thể cache, dùng lại output của lần thực thi trước. Tuy nhiên đường dẫn tuyệt đối, cách xuống dòng, encoding, thứ tự file và dữ liệu môi trường không được khai báo có thể làm giảm khả năng sử dụng lại kết quả hoặc gây cache hit không chính xác.

Bài này tập trung vào ba nhóm:

1. **Chuẩn hóa đường dẫn đầu vào**: dùng `@PathSensitive` và `PathSensitivity` để mô tả phần nào của đường dẫn thực sự ảnh hưởng output.
2. **Chuẩn hóa nội dung**: ví dụ line endings, classpath normalization và cách tạo nội dung/archives xác định để hai môi trường cho cùng kết quả.
3. **Tái sử dụng đúng**: phân biệt up-to-date check, local/remote build cache, tính relocatable, cache correctness và khả năng tái sử dụng custom task ở nhiều project.

**Định nghĩa thực hành:** Hai bộ input được khai báo là *tương đương* nếu custom task sẽ tạo ra cùng output logic/bytes cho cả hai, theo hợp đồng của task. Bạn chỉ được yêu cầu Gradle bỏ qua khác biệt đầu vào (qua normalization) khi giả định tương đương này **thật sự đúng**.

### Sau bài học bạn cần làm được

- Giải thích vì sao dùng absolute path làm cache kém hiệu quả khi CI checkout ở hai thư mục khác nhau.
- Chọn chính xác `ABSOLUTE`, `RELATIVE`, `NAME_ONLY` hay `NONE` theo hành vi task.
- Dùng `@InputFile`, `@InputFiles`, `@Input`, `@OutputFile`, `@PathSensitive`, `@NormalizeLineEndings` trong custom task.
- Nói rõ khác nhau giữa **chuẩn hóa input fingerprint** và **thực sự chuẩn hóa bytes output**.
- Tạo task có `@CacheableTask`, khai báo đầu vào/đầu ra, tạo kết quả tái lập bằng UTF-8 và LF.
- Kiểm tra `UP-TO-DATE` so với `FROM-CACHE` bằng lệnh Gradle; nhận ra cache miss hợp lệ và nguy cơ cache hit sai.
- Thiết kế task có thể tái sử dụng ở nhiều thư mục và project mà không đọc ngầm thời gian, biến môi trường hoặc đường dẫn máy.

Các ví dụ dùng **Groovy DSL** (`build.gradle`), **Gradle Wrapper**, JDK 17+ cho code Java hoặc API Java của custom task. Lệnh Linux/macOS bắt đầu bằng `./gradlew`; trong Windows PowerShell dùng `.\gradlew.bat`.

## 2. Đầu vào, đầu ra và cách Gradle quyết định có chạy task

Một task đơn giản chỉ in một dòng:

~~~groovy
tasks.register('greet') {
    doLast {
        println 'Hello'
    }
}
~~~

Không mô tả được sản phẩm lưu trên đĩa và cũng không có đủ thông tin để tận dụng up-to-date checks cho artifact.

Ngược lại, một task sinh file có thể khai báo:

- **`@Input`**: giá trị dữ liệu như tên báo cáo, chế độ, version, flags.
- **`@InputFile` / `@InputFiles` / `@InputDirectory`**: file hoặc directory đầu vào; với file input, Gradle theo dõi nội dung và cách đường dẫn được chuẩn hóa.
- **`@OutputFile` / `@OutputDirectory`**: file hoặc directory kết quả.
- **`@TaskAction`**: mã chạy lúc task thực thi.
- **`@CacheableTask`**: xác nhận task type đáp ứng hợp đồng caching, miễn các điều kiện còn lại hợp lệ.

Một chu kỳ tổng quát:

~~~text
Khai báo task và properties
          |
          v
Task được chọn trong task graph
          |
          v
Gradle đọc snapshot input (giá trị, nội dung, đường dẫn đã normalize)
          |
          +---- output đang hợp lệ? ----> UP-TO-DATE
          |
          +---- build cache có entry phù hợp? ----> FROM-CACHE (restore output)
          |
          v
      Thực thi @TaskAction
          |
          v
Tạo/snapshot output -> ghi cache nếu task đủ điều kiện
~~~

Đây là sơ đồ khái niệm. Cơ chế task execution của Gradle còn có điều kiện skip, incremental APIs, task history, task validation và các nguyên nhân không cache được.

### 2.1. Ba tính chất không đồng nghĩa

| Thuộc tính | Câu hỏi nó trả lời |
| --- | --- |
| **Correctness** | Input được khai báo và cách fingerprint có đủ để không dùng nhầm một kết quả? |
| **Reproducibility** | Cùng input logic có tạo ra output giống nhau (thường theo bytes) trên những lần/môi trường tương đương? |
| **Relocatability** | Task có tránh phụ thuộc vào vị trí tuyệt đối của thư mục project, để cache có thể dùng lại sau khi chuyển checkout? |

Một task có thể **deterministic** nhưng không relocatable: nó luôn ghi nguyên absolute path vào report. Một task có thể **relocatable** nhưng không deterministic: nó ghi thời gian hiện tại vào file. Một task có thể tạo output deterministic nhưng thiếu input declaration, khiến cache cho kết quả sai khi thay đổi dữ liệu ngầm.

**Không sửa lỗi bằng cách chỉ bật `--build-cache`**. Build cache chỉ đáng tin khi hợp đồng input/output và hành vi task đúng.

## 3. Vì sao đường dẫn làm ảnh hưởng đến cache?

Giả sử một máy có source:

~~~text
/home/alice/work/demo/docs/source.txt
~~~

và máy CI có file cùng nội dung tại:

~~~text
/agent/work/42/demo/docs/source.txt
~~~

Nếu task chỉ đọc **nội dung** hai file để sinh cùng file Markdown, phần `/home/alice/work` và `/agent/work/42` không có ý nghĩa nghiệp vụ. Nhưng nếu fingerprint bao gồm absolute path, hai lần chạy có thể tạo **khác cache key**, dù bytes source giống hệt.

Ngược lại, một task tạo danh sách file với relative path, ví dụ `chapter/intro.md` và `guide/intro.md`, phải phân biệt hai file này: nếu chỉ xét filename `intro.md` hoặc nội dung mà bỏ path, bạn có thể tạo báo cáo hoặc thứ tự kết quả sai.

**Quy tắc:** Chọn path sensitivity dựa trên những phần đường dẫn **thực sự thay đổi output** của task, không dựa trên mong muốn “cache hit càng nhiều càng tốt”.

### 3.1. `PathSensitivity`

| Giá trị | Gradle dùng gì khi fingerprint path? | Khi phù hợp |
| --- | --- | --- |
| `ABSOLUTE` | Đường dẫn tuyệt đối | Output thực sự phụ thuộc vào vị trí tuyệt đối; thường làm task khó tái sử dụng giữa checkout |
| `RELATIVE` | Phần đường dẫn tương đối theo gốc của tập file input được khai báo | Output phụ thuộc cấu trúc thư mục/nesting tương đối nhưng không phụ thuộc vị trí root checkout |
| `NAME_ONLY` | Chỉ tên file/thư mục ở cuối path; bỏ phần thư mục cha | Output chỉ quan tâm tên file, không quan tâm vị trí hoặc cấu trúc thư mục |
| `NONE` | Không sử dụng tên/đường dẫn file khi fingerprint | Output chỉ phụ thuộc **nội dung**, không sử dụng cả basename hay relative path |

Gradle vẫn theo dõi **nội dung file** khi áp dụng các lựa chọn trên; `NONE` **không** có nghĩa “bỏ qua thay đổi nội dung”. Path sensitivity quyết định phần đường dẫn được tính vào input fingerprint.

### 3.2. Chọn dựa trên output, không theo thói quen

**Ví dụ A — render nội dung một file, không in tên nguồn:** Đọc `docs/source.txt` rồi sinh `notes.md` dựa duy nhất vào text. Tên `source.txt` không xuất hiện trong output. Có thể chọn `@PathSensitive(PathSensitivity.NONE)`.

**Ví dụ B — mục lục giữ cấu trúc thư mục:** Với `docs/guide/start.md` và `docs/api/start.md`, output sinh link `guide/start` và `api/start`. Chọn `RELATIVE`. Không chọn `NAME_ONLY`, vì cả hai đều là `start.md`.

**Ví dụ C — processor chọn behavior theo basename:** Nếu phần logic phân biệt `config.xml` với `settings.xml` nhưng bỏ qua folder, `NAME_ONLY` có thể phù hợp. Hãy chắc chắn không có hai file trùng tên cần phân biệt.

**Ví dụ D — task in đường dẫn tuyệt đối vào report:** `ABSOLUTE` phản ánh đúng tính phụ thuộc vào path. Nhưng task sẽ khó dùng cache xuyên checkout. Giải pháp tốt hơn thường là **thay đổi format output thành relative path**, rồi dùng `RELATIVE`, thay vì khai báo giả `NONE` để ép cache hit.

### 3.3. Hai lỗi nguy hiểm

1. **Khai `NONE` nhưng output chứa tên nguồn**. Đổi `report-a.txt` thành `report-b.txt` mà nội dung không đổi có thể khiến fingerprint coi hai đầu vào tương đương, trong khi output lẽ ra thay đổi. Đó là **cache hit sai**.
2. **Khai `NAME_ONLY` cho cây thư mục có đường dẫn tương đối quan trọng**. Hai file `a/readme.md`, `b/readme.md` cùng basename có thể bị xem không đúng sự khác nhau cần thiết; logic sinh link/manifest theo thư mục sẽ sai. Chọn `RELATIVE` để phản ánh dữ liệu thực.

Không “chữa” bằng cách thêm `clean` trước mỗi lần build: hành vi snapshot sai vẫn là sai, chỉ bị che bởi việc buộc chạy lại task.

## 4. Cấu hình Path Sensitivity trong custom task

### 4.1. Annotations trong typed task

Với custom task Java/Groovy có một file đầu vào:

~~~groovy
@InputFile
@PathSensitive(PathSensitivity.RELATIVE)
abstract RegularFileProperty getSourceFile()
~~~

Với file collection:

~~~groovy
@InputFiles
@PathSensitive(PathSensitivity.RELATIVE)
abstract ConfigurableFileCollection getSourceFiles()
~~~

Hai đoạn này **chưa phải lớp chạy độc lập**: cần import các annotation/type Gradle, class kế thừa `DefaultTask`, khai báo `@TaskAction` và đăng ký task. Bài chạy đầy đủ ở phần 7.

### 4.2. Runtime input declaration thay vì annotation

Nếu viết task bằng `tasks.register` và cần khai báo input file trực tiếp:

~~~groovy
import org.gradle.api.tasks.PathSensitivity

tasks.register('inspectSource') {
    def selectedFile = layout.projectDirectory.file('docs/source.txt')

    inputs.file(selectedFile)
        .withPropertyName('sourceFile')
        .withPathSensitivity(PathSensitivity.RELATIVE)

    doLast {
        println 'source exists=' + selectedFile.get().asFile.isFile()
    }
}
~~~

Đây là **build.gradle snippet** (không phải toàn bộ bài chạy). Nó giả sử `docs/source.txt` tồn tại. `withPropertyName` tạo tên dễ đọc cho input property; `withPathSensitivity` nêu rõ cách fingerprint path. Task chỉ in trạng thái tồn tại; nếu muốn cache artifact, phải tạo output và khai báo nó.

Cách khai báo annotation trên typed task thích hợp hơn khi logic được chia sẻ cho nhiều project, vì input/output trở thành **hợp đồng có kiểu** của task.

### 4.3. `RELATIVE` trong tập file cần cấu trúc

Ví dụ trong một build có tài liệu:

~~~text
docs/
├── guide/intro.md
├── guide/install.md
└── api/intro.md
~~~

Muốn tạo site map:

~~~text
api/intro.md
guide/install.md
guide/intro.md
~~~

Bạn phải giữ relative path và sắp xếp ổn định. Tên `intro.md` một mình không đủ phân biệt hai file. Cũng không nên đưa `C:\agent\work\demo\docs\guide\intro.md` vào output, vì máy khác sẽ sinh bytes khác dù nội dung và cấu trúc giống nhau.

## 5. Chuẩn hóa nội dung: line endings, encoding và dữ liệu ngầm

**Path normalization** chỉ là một phần. Hai file trông giống nhau trong editor có thể có bytes khác:

- Linux/macOS thường dùng LF (`\n`), trong khi Windows có thể dùng CRLF (`\r\n`).
- File có thể dùng UTF-8, UTF-8 với BOM hoặc encoding khác.
- Một số công cụ ghi thời gian tạo, absolute path, timezone, username hoặc thứ tự ngẫu nhiên vào artifact.
- Khi sinh danh sách từ file set, thứ tự duyệt filesystem có thể khác giữa OS/máy.

Nếu task chỉ quan tâm văn bản theo các dòng, CRLF và LF có thể được xem là tương đương. Nhưng nếu task **đóng gói nguyên bytes source** vào artifact thì CRLF và LF **không** tương đương.

### 5.1. `@NormalizeLineEndings` làm gì?

Gradle cung cấp annotation `@NormalizeLineEndings` cho input file properties để **bỏ qua khác biệt kiểu xuống dòng khi fingerprint nội dung file**, khi có thể áp dụng.

~~~groovy
@InputFile
@PathSensitive(PathSensitivity.NONE)
@NormalizeLineEndings
abstract RegularFileProperty getSourceText()
~~~

Điều rất dễ nhầm: annotation này **không sửa file trên đĩa, không chuyển bytes input được task đọc thành LF, cũng không tự đổi bytes output**. Nó chỉ thay đổi cách Gradle **nhận diện input nào là tương đương** để up-to-date/build cache.

Do đó, nếu task dùng `@NormalizeLineEndings` nhưng copy nguyên bytes source ra output, một lần input CRLF và một lần input LF có thể cho output khác trong khi fingerprint được coi như nhau. Cách khai báo đó **không đúng**. Task cần thực sự **chuẩn hóa output** hoặc bỏ annotation nếu bytes line ending là một phần kết quả.

### 5.2. Chuẩn hóa line ending nhất quán trong code

Khi text thuộc phạm vi được phép chuẩn hóa, ví dụ xử lý Markdown source:

~~~groovy
String rawText = Files.readString(sourceFile.get().asFile.toPath(),
                                  StandardCharsets.UTF_8)
String normalizedText = rawText
    .replace("\r\n", "\n")
    .replace("\r", "\n")
~~~

- Đọc file bằng UTF-8 rõ ràng, không dựa vào encoding mặc định của máy.
- Chuyển CRLF và CR đơn lẻ thành LF trong **dữ liệu mà task thực sự dùng**.
- Khi ghi output, chọn UTF-8 và LF, đừng để platform tự chèn separator khác.
- Chỉ làm như vậy khi nội dung nghiệp vụ cho phép bỏ khác biệt line ending. Với bài test byte-for-byte hoặc file nhị phân, không được coi mọi line ending tương đương.

**Đối với Unicode normalization (NFC/NFD):** Đây là một khái niệm khác với line ending. Gradle không mặc định coi mọi chuỗi Unicode có dạng tổ hợp khác nhau là cùng bytes. Nếu bài toán cần chuẩn hóa Unicode, logic xử lý, định dạng đầu ra và phương pháp khai báo input phải tương thích; **không giả định `@NormalizeLineEndings` xử lý NFC/NFD**.

### 5.3. Không chuẩn hóa quá mức

Việc loại bỏ dấu cách ở cuối dòng, sắp xếp lại các dòng, xóa comment hoặc chuyển chữ hoa sang chữ thường có thể làm thay đổi **ngữ nghĩa** của mã/configuration. Nếu thực sự muốn coi hai input tương đương sau phép biến đổi đó, hãy thiết kế cả logic transform và cách Gradle biết input theo cùng một hợp đồng. Đừng chỉ thay file trên đường output rồi bỏ qua input chưa khai báo. Với task xử lý Java source, khoảng trắng/comment thay đổi có thể không làm đổi bytecode, nhưng không có nghĩa mọi custom task tạo docs, reports hay archive đều được quyền bỏ qua.

## 6. Build cache, up-to-date và tính relocatable

### 6.1. Hai tầng dùng lại kết quả

**Up-to-date check:** Trong cùng task history/workspace, Gradle nhìn input/output đã khai báo và có thể bỏ qua action khi kết quả vẫn hợp lệ. Dòng log `UP-TO-DATE` là tình huống bình thường.

**Build cache:** Gradle có thể lưu output của task đủ điều kiện theo fingerprint và task implementation rồi **khôi phục** tại lần chạy khác. Dòng `FROM-CACHE` cho biết output đã được lấy từ cache thay vì chạy action.

Không phải mọi task có `@OutputFile` đều tự cache được. Task type phải được coi là cacheable (ví dụ annotation `@CacheableTask` hoặc cơ chế caching được bật đúng); ngoài ra còn phải có input/output hợp lệ, không có lý do Gradle tắt cache và có build cache được bật.

~~~properties
# gradle.properties
org.gradle.caching=true
~~~

Hoặc chạy với option `--build-cache`:

~~~bash
./gradlew renderNotes --build-cache
~~~

**Quan trọng:** Bật build cache **không** đảm bảo `FROM-CACHE`. Có thể task đang up-to-date, task chưa được cache, input đổi, cache entry chưa có hoặc cache không dùng được. Khi demo ở một workspace, hãy đọc log trạng thái thay vì chỉ đọc `BUILD SUCCESSFUL`.

### 6.2. Vì sao cache key thay đổi?

Những yếu tố có thể tham gia xác định kết quả/cache key:

- Giá trị `@Input`.
- Nội dung file/directory đầu vào, kèm path sensitivity, normalization tương ứng.
- Implementation của task/action và những yếu tố Gradle cần để xác định hành vi.
- Danh tính/nội dung classpath liên quan nếu task dùng công cụ ngoài.
- Những input property khác ảnh hưởng output.

Chỉ đổi đường dẫn checkout **có thể** không đổi key nếu task được thiết kế relocatable và normalization đúng; nhưng điều đó không giúp ích nếu task vẫn đọc `System.getenv`, `Instant.now()`, `File.absolutePath` hoặc các tệp không khai báo.

Một remote cache dùng chung còn có vấn đề **tin cậy**: chỉ chia sẻ cache với nguồn/CI đáng tin; cache entry phải được tạo bởi build đáng tin cậy và version/task implementation tương thích.

### 6.3. Relocatability khác reproducible output

Ví dụ sinh báo cáo chứa:

~~~text
Source: /home/developer/work/demo/docs/source.txt
~~~

Trên CI, dòng này thành:

~~~text
Source: /agent/workspace/demo/docs/source.txt
~~~

Dù task chỉ có input file content giống nhau, output vẫn khác. Nếu bạn khai `@PathSensitive(NONE)`, Gradle có thể coi input tương đương, trong khi output không tương đương: **hợp đồng cache sai**.

Cách sửa:
- Nếu cần định danh nguồn, ghi `docs/source.txt` (relative path nhất quán), đồng thời dùng `RELATIVE` hoặc khai báo relative path cần thiết thành input.
- Nếu report chỉ cần nội dung, bỏ source path ra khỏi output; khi đó `NONE` hợp lý.
- Không đưa absolute path, tên user/host, random ID hoặc timestamp vào output nếu không phải dữ liệu nghiệp vụ.
- Nếu output bắt buộc chứa giá trị thay đổi, hãy khai báo nó thành input; chấp nhận giảm reuse thay vì giả vờ output deterministic.

## 7. Phòng thực hành hoàn chỉnh: custom task chuẩn hóa text và hỗ trợ caching

Bài này tạo một **cacheable typed task**: đọc `docs/source.txt` bằng UTF-8, chuẩn hóa line endings thành LF, thêm heading và ghi `build/generated/notes.md`. Task **không sử dụng tên hay đường dẫn của file nguồn** để tạo bytes output, nên `PathSensitivity.NONE` hợp lý cho một source file.

### 7.1. Cấu trúc

~~~text
normalized-task-lab/
├── settings.gradle
├── gradle.properties
├── build.gradle
├── docs/
│   └── source.txt
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
~~~

Nếu chưa có Wrapper, hãy có một bản Gradle đã cài để chạy `gradle wrapper` một lần, rồi commit các file Wrapper. Ví dụ sử dụng API Java trong custom task, nên môi trường chạy Gradle phải có JDK tương thích; Java 17+ phù hợp với Gradle phiên bản hiện đại hỗ trợ JDK đó.

**`settings.gradle`:**

~~~groovy
rootProject.name = 'normalized-task-lab'
~~~

**`gradle.properties`:**

~~~properties
org.gradle.caching=true
notesHeading=Ghi chú dự án
~~~

**`docs/source.txt`:**

~~~text
Dòng thứ nhất.
Dòng thứ hai.
~~~

Đặt nội dung bằng text editor với encoding UTF-8; dùng LF hoặc CRLF để thử. File nên có một ký tự xuống dòng cuối file.

### 7.2. `build.gradle` đầy đủ

~~~groovy
import java.nio.charset.StandardCharsets
import java.nio.file.Files

import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.NormalizeLineEndings
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

plugins {
    id 'base'
}

@CacheableTask
abstract class RenderNotes extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.NONE)
    @NormalizeLineEndings
    abstract RegularFileProperty getSourceFile()

    @Input
    abstract Property<String> getHeading()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void render() {
        String original = Files.readString(
            sourceFile.get().asFile.toPath(),
            StandardCharsets.UTF_8
        )

        String normalized = original
            .replace("\r\n", "\n")
            .replace("\r", "\n")

        if (!normalized.endsWith("\n")) {
            normalized += "\n"
        }

        String result = '# ' + heading.get() + '\n\n' + normalized

        File target = outputFile.get().asFile
        Files.createDirectories(target.toPath().getParent())
        Files.writeString(
            target.toPath(),
            result,
            StandardCharsets.UTF_8
        )

        println 'generated=' + target.name
    }
}

def renderNotes = tasks.register('renderNotes', RenderNotes) {
    group = 'documentation'
    description = 'Sinh Markdown ổn định từ dữ liệu văn bản'

    sourceFile.set(layout.projectDirectory.file('docs/source.txt'))
    heading.set(
        providers.gradleProperty('notesHeading').orElse('Ghi chú')
    )
    outputFile.set(layout.buildDirectory.file('generated/notes.md'))
}

tasks.named('assemble') {
    dependsOn renderNotes
}
~~~

**Điểm kiểm tra kỹ thuật:**

1. `@CacheableTask` đánh dấu task type có thể cache khi hợp đồng đầu vào/đầu ra đúng. Đây không phải lời hứa mọi môi trường luôn cache hit.
2. `sourceFile` là `@InputFile`, có `@PathSensitive(NONE)` vì tên/path input **không** được dùng để sinh output, và có `@NormalizeLineEndings` vì chính task **đã chuyển** line endings sang LF.
3. `heading` là `@Input`: thay `notesHeading` sẽ đổi output, nên cần khiến cache key thay đổi.
4. `outputFile` là `@OutputFile`, cho Gradle biết file phải kiểm tra và lưu/khôi phục từ cache. Đường dẫn output được cấp qua `layout.buildDirectory`, không phải hardcode thư mục home của máy.
5. `Files.readString`/`writeString` với `StandardCharsets.UTF_8` tránh phụ thuộc vào platform default charset.
6. Code không dùng timestamp, random ID, tên máy, absolute source path hoặc một biến môi trường ngầm.
7. `tasks.register`/`TaskProvider` giúp cấu hình lazy, còn `@TaskAction` chỉ thực hiện khi Gradle thực thi task.
8. `assemble` là lifecycle task gom artifact; nó được nối với `renderNotes`. Không thêm action ghi file trực tiếp vào `assemble`.

### 7.3. Chạy và kiểm tra output

~~~bash
./gradlew clean renderNotes --info
./gradlew renderNotes --info
./gradlew clean renderNotes --build-cache --info
~~~

Dòng stdout từ action khi task thực sự chạy lần đầu:

~~~text
generated=notes.md
~~~

Nội dung kỳ vọng của **`build/generated/notes.md`** (không phải Gradle console log):

~~~markdown
# Ghi chú dự án

Dòng thứ nhất.
Dòng thứ hai.
~~~

Kết quả task phụ thuộc tình trạng cache:
- Lần đầu trên môi trường sạch, chưa có cache entry: `renderNotes` thực thi action và tạo output.
- Lần thứ hai không đổi input/output: Gradle có thể đánh dấu `UP-TO-DATE`; dòng `generated=...` không được in lại.
- Sau `clean`, output bị xóa. Nếu cache enabled và cache entry hợp lệ, Gradle có thể báo `FROM-CACHE` và khôi phục file mà không gọi action. Nếu không, task chạy lại; đây cũng là hành vi hợp lệ.
- `./gradlew assemble` cũng yêu cầu `renderNotes`, vì đã khai báo `dependsOn`. Plugin Base không tự tạo task sinh Markdown nếu bạn không nối nó vào.

Để xem tổng quan:
~~~bash
./gradlew tasks --all
./gradlew assemble --dry-run
./gradlew renderNotes --info
~~~

`--dry-run` chỉ quan sát graph; **không** chứng minh bytes được normalize hay cache hoạt động, vì các action không chạy.

### 7.4. Thí nghiệm thay line ending

1. Lưu `docs/source.txt` ở dạng LF; chạy `./gradlew renderNotes --info` và lưu nội dung `notes.md`.
2. Đổi **chỉ** line ending của source thành CRLF; không đổi nội dung ký tự.
3. Chạy lại cùng lệnh, theo dõi state và so sánh bytes `notes.md`.

Vì annotation `@NormalizeLineEndings` và logic sinh output cùng coi LF/CRLF là tương đương, task có thể up-to-date hoặc dùng cache sau thay đổi line ending (tùy trạng thái). Khi task thực thi lại thì output vẫn là LF theo thiết kế. Đừng hiểu rằng Gradle đã sửa `docs/source.txt`: source **giữ nguyên** cách xuống dòng do editor ghi.

### 7.5. Thí nghiệm thay tên file hoặc checkout

Với typed task ở trên, bạn có thể sửa `sourceFile.set(...)` để tham chiếu một file khác có **cùng nội dung** (không dùng tên mới trong output). `NONE` cho phép không coi tên/path input là khác biệt khi fingerprint. Nhưng nếu file khác có nội dung khác, input fingerprint vẫn đổi.

Muốn thử *relocation thực sự*, tạo một checkout sạch thứ hai ở đường dẫn khác; sử dụng cùng code task, input, Gradle User Home/cache và các điều kiện tác động đến output. Khi cùng cache có entry và cấu hình input chuẩn, task **có cơ hội** dùng lại output. Chỉ copy thư mục mà mang theo cả `.gradle` và `build` cũ không phải phép thử tốt cho khả năng reuse xuyên checkout, vì có thể lẫn local task history/up-to-date state.

### 7.6. Thí nghiệm thay input có ý nghĩa

~~~bash
./gradlew renderNotes -PnotesHeading=Phát hành --info
~~~

Giá trị heading trở thành `Phát hành`. Vì `heading` là `@Input`, cache key cần thay đổi so với heading `Ghi chú dự án`. Bạn sẽ có Markdown đầu ra bắt đầu bằng:

~~~markdown
# Phát hành
~~~

Nếu đổi nội dung `docs/source.txt` từ `Dòng thứ hai.` sang `Dòng khác.`, task cũng phải chạy hoặc tải **cache entry tương ứng với nội dung mới**, không được dùng output cũ.

## 8. Bài thực hành mở rộng: nhiều file và đường dẫn tương đối

Bài chính có **một file input** nên `NONE` phù hợp. Nhưng khi tạo mục lục theo cấu trúc file, cần `RELATIVE`.

Giả sử:
~~~text
docs/
├── api/intro.md
├── guide/intro.md
└── guide/setup.md
~~~

Đầu ra mong muốn:

~~~text
api/intro.md
guide/intro.md
guide/setup.md
~~~

Nếu task chỉ dùng nội dung mà bỏ path, hai file cùng tên `intro.md` dễ bị nhập nhằng. Với một custom task type, khai báo input:

~~~groovy
@InputFiles
@PathSensitive(PathSensitivity.RELATIVE)
abstract ConfigurableFileCollection getSourceFiles()
~~~

Trong script cấu hình task, có thể cấp dữ liệu bằng:

~~~groovy
sourceFiles.from(fileTree('docs') {
    include '**/*.md'
})
~~~

**Đây là đoạn cấu hình minh họa, không phải toàn bộ class**. Task vẫn phải dùng các relative path đúng để sinh manifest, và tự đảm bảo thứ tự ổn định:

- Chuyển đường dẫn về dạng relative với root logic `docs/`.
- Thay dấu phân cách hệ điều hành bằng `/` trong output.
- **Sắp xếp** theo relative path trước khi ghi.
- Dùng UTF-8 và LF.
- Không đưa đường dẫn tuyệt đối hoặc thứ tự duyệt `FileTree` ngẫu nhiên vào report.

Ví dụ phép biến đổi trong code Java/Groovy của task (giả sử đã có biến `rootDir` và `candidate` là các đối tượng `File` hợp lệ):

~~~groovy
String relativePath = rootDir.toPath()
    .relativize(candidate.toPath())
    .toString()
    .replace('\\', '/')
~~~

Đây chỉ là **một biểu thức minh họa**, không dùng trực tiếp `rootDir`/`candidate` khi chưa khai báo chúng. Cần bảo đảm các đường dẫn cùng hệ thống gốc và file thực sự nằm trong cây tài liệu. Nếu output phụ thuộc tên file hoặc thứ tự, phải phản ánh các yếu tố đó vào input fingerprint; đừng gắn `NONE` cho task chỉ để tăng cache hit.

## 9. Classpath normalization: cùng thư viện nhưng layout khác

Với custom task chạy tool/compiler, file input có thể là classpath hoặc compile classpath. Gradle cung cấp cách fingerprint phù hợp hơn so với coi mọi JAR như một file bất kỳ.

| Annotation | Ý tưởng | Dùng khi |
| --- | --- | --- |
| `@Classpath` | Normalization dành cho classpath, xem xét thứ tự/phần nội dung liên quan classpath thay vì phụ thuộc vào đường dẫn tuyệt đối của mỗi JAR | Task chạy công cụ, phân tích hoặc load class dựa vào runtime classpath |
| `@CompileClasspath` | Normalization dành cho compile classpath, có thể bỏ qua một số thay đổi implementation không ảnh hưởng ABI/việc compile | Task có kết quả chỉ phụ thuộc vào thông tin compile-relevant của dependency |

Snippet trong **custom task type** (không phải build.gradle chạy độc lập):

~~~groovy
@Classpath
abstract ConfigurableFileCollection getToolClasspath()

@CompileClasspath
abstract ConfigurableFileCollection getJavaCompileClasspath()
~~~

**Không nhầm:** `@CompileClasspath` không có nghĩa “bỏ qua mọi thay đổi JAR”. Nó chỉ phù hợp khi task thực sự không cần chi tiết implementation mà normalization bỏ qua. Nếu task phân tích bytecode/private method hoặc scan toàn bộ nội dung JAR, dùng `@Classpath` hoặc tập file input/normalization thích hợp thay vì `@CompileClasspath`.

Classpath normalization khác path sensitivity cho source tree. Một tool xử lý Markdown không cần `@Classpath` chỉ vì project có dependency Java.

## 10. Reproducible output: chuẩn hóa nhiều hơn input path

Ngay cả khi input fingerprint hợp lý, output vẫn có thể chứa dữ liệu không ổn định.

### 10.1. Nguồn bất định thường gặp

| Nguồn | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `new Date()`, `Instant.now()`, timestamp build | Hai lần chạy cùng input có bytes output khác | Loại khỏi output hoặc khai báo thời điểm như `@Input` nếu nghiệp vụ cần |
| Random/UUID không có seed cố định | Output khác nhau khó debug/cache | Không đưa random vào artifact; nếu cần, khai báo seed rõ ràng |
| `File.absolutePath` | Cache giữa checkout khác nhau không an toàn hoặc không tái sử dụng | Chuyển về relative path đúng khi nghiệp vụ cho phép |
| `File.separator` hoặc `System.lineSeparator()` được ghi vào file | Output khác OS | Dùng `/` cho logical paths, `\n` cho text nếu định dạng cho phép |
| Platform default encoding | Bytes khác trên các máy có charset khác nhau | Chỉ định `UTF-8` khi đọc/ghi |
| Thứ tự duyệt filesystem/Set/Map không được ổn định | Danh sách/manifest thay thứ tự | Sort theo key/relative path trước khi ghi |
| Timezone/locale mặc định | Date, số, chữ hoa/thường khác môi trường | Chọn `Locale`/`ZoneId` tường minh, khai báo input nếu giá trị thay đổi output |
| Đọc env/system property không khai báo | Cache hit có thể sai khi CI thay cấu hình | Đưa qua Provider và `@Input` tương ứng |
| Công cụ ngoài/JDK khác nhưng chưa khai báo | Cùng input file mà tool tạo output khác | Khai báo tool version/toolchain/classpath và tham số |
| File permission, metadata khi đóng gói | Archive khác bytes giữa máy hoặc lần chạy | Dùng cấu hình reproducible archives, chuẩn hóa metadata |

Không phải mọi khác biệt đều cần bỏ: ví dụ một chữ ký số có timestamp có thể có mục tiêu bảo mật riêng. Khi output **cố ý không deterministic**, phải thiết kế để tránh cache không đúng (có thể không đánh dấu task cacheable).

### 10.2. ZIP/JAR/TAR: thứ tự file và timestamp

Với archive tasks của Gradle, có thể cấu hình thêm các thuộc tính phục vụ reproducible archives:

~~~groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Đây là **snippet thêm vào build.gradle** khi có archive tasks. Nó giúp kiểm soát file timestamps và thứ tự archive entries. Nhưng còn nhiều yếu tố khác, như nội dung files được đóng gói, toolchain, manifest và dữ liệu tạo động; hai flags không tự bảo đảm mọi artifact giống nhau theo bytes.

### 10.3. Sự liên hệ giữa normalization và correctness

Bảng quy tắc nhanh:

| Đổi input | Task output có đổi hợp lệ? | Fingerprint nên phản ánh? |
| --- | --- | --- |
| Đổi absolute checkout root, logic chỉ dùng nội dung file | Không | Bỏ root/path (ví dụ `NONE`) |
| Đổi relative path nhưng task tạo sitemap theo path đó | Có | Dùng `RELATIVE` |
| Đổi basename dùng làm tên section | Có | Ít nhất `NAME_ONLY` |
| Đổi LF thành CRLF, task sinh output theo LF | Không | `@NormalizeLineEndings` phù hợp |
| Đổi LF thành CRLF, task copy nguyên bytes | Có | Không bỏ qua thay đổi line ending |
| Đổi text heading | Có | Khai `@Input` cho heading |
| Đổi compiler/tool version làm đổi output | Có thể | Khai toolchain/version/classpath phù hợp |
| Đổi `build/` output location, bytes output không phụ thuộc path | Không | Cấp `@OutputFile` qua Gradle property; không nhúng output absolute path |

Bạn có thể dùng bảng này làm checklist trước khi đặt `@CacheableTask`.

## 11. Configuration cache không phải build cache

Hai tính năng thường cùng được nói tới nhưng giải quyết hai chi phí khác nhau:

- **Build cache:** lưu/khôi phục **kết quả task execution**, phụ thuộc vào input/output và implementation.
- **Configuration cache:** lưu lại **mô hình cấu hình task graph** để lần chạy sau không phải cấu hình lại project không đổi.

Một task có thể chạy tốt với build cache nhưng không tương thích configuration cache nếu action lưu/truy cập trạng thái không hợp lệ từ `Project`, `Settings` hay build script.

Các nguyên tắc có ích cho cả hai:

1. Dùng task type có property rõ ràng, ví dụ `Property<String>`, `RegularFileProperty`, `ConfigurableFileCollection`.
2. Dùng `providers.gradleProperty(...)`, `providers.environmentVariable(...)`, `layout.*` để cấp giá trị cho task khi cấu hình.
3. Không giữ reference tới `Project`/script/service không hỗ trợ trong `@TaskAction`.
4. Không đọc file, network, user home hoặc timestamp ngầm trong action nếu chưa khai báo phụ thuộc phù hợp.
5. Dùng `tasks.register`, `tasks.named`, `configureEach` để tránh cấu hình task không cần thiết.
6. Thử `--configuration-cache` và kiểm tra report thực tế; **build-cache hit không phải bằng chứng configuration cache tương thích**.

Ví dụ kiểm chứng:

~~~bash
./gradlew renderNotes --configuration-cache
./gradlew renderNotes --configuration-cache
~~~

Ở lần sau, nếu không có configuration inputs làm invalidation và mọi task/logic tương thích, Gradle có thể reuse configuration cache. Kết quả execution có thể đồng thời `UP-TO-DATE` hoặc `FROM-CACHE` tùy trạng thái.

## 12. Task tái sử dụng qua nhiều project: contract trước implementation

Để custom task dùng được trong nhiều module/repository, hãy thiết kế API của task trước:

| Thuộc tính | Thiết kế nên có |
| --- | --- |
| Input text/template | `@InputFile` + normalization đúng ý nghĩa; nhận file từ `RegularFileProperty` |
| Nhiều source files | `@InputFiles` + `PathSensitivity.RELATIVE` nếu output cần cấu trúc |
| Cờ, format, heading, tool version | `@Input` với `Property<T>` |
| Classpath của tool | `@Classpath` hoặc `@CompileClasspath` theo cách tool dùng library |
| Output | `@OutputFile`/`@OutputDirectory`, cấp từ `layout.buildDirectory` |
| Side effects không mô tả được | Tránh trong task cacheable; nếu không thể, đừng bật caching như thể có thể |
| Repo-/OS-specific paths | Cố gắng chuyển thành relative logical path |
| Credentials, token | Xử lý qua cơ chế an toàn; không embed vào output hoặc log |

Khi logic đã ổn định, bạn có thể chuyển custom task type từ inline `build.gradle` sang **build logic tái sử dụng** (chẳng hạn convention plugin hoặc included build). Mỗi project chỉ cần đăng ký/configure task và cấp các input bằng Provider. Việc reuse code giữa project không tự đảm bảo reuse output cache: task implementation và input vẫn phải đáp ứng cùng hợp đồng.

**Đừng nhầm cấu trúc thư mục với cache correctness:** Một plugin áp dụng cho mười module có thể tạo mười task tên giống nhau, nhưng input và output khác nhau. Gradle không dùng kết quả của module A cho module B trừ khi cache key thực sự mô tả cùng kết quả và cơ chế cache cho phép reuse.

## 13. Chẩn đoán khi task không tái sử dụng được

### 13.1. Các lệnh quan sát

~~~bash
./gradlew renderNotes --info
./gradlew clean renderNotes --build-cache --info
./gradlew renderNotes --rerun-tasks --info
./gradlew renderNotes --no-build-cache --info
./gradlew renderNotes --configuration-cache --info
~~~

- `--info` giúp đọc lý do task chạy/không up-to-date và hành vi cache.
- `clean` xóa output hiện tại, **không tự xóa build cache** của Gradle.
- `--build-cache` bật sử dụng cache cho lần chạy.
- `--rerun-tasks` yêu cầu chạy lại task ngay cả khi up-to-date; dùng để kiểm tra hành vi thực thi, **không** coi là phép thử cache hit.
- `--no-build-cache` tắt build cache cho lần chạy, phù hợp khi so sánh kết quả task tự chạy.
- `--configuration-cache` kiểm tra riêng khả năng lưu/khôi phục configuration state.

### 13.2. Đọc trạng thái

| Task state | Cách hiểu |
| --- | --- |
| `UP-TO-DATE` | Có output và snapshot input/output cho phép bỏ qua action trong lần chạy |
| `FROM-CACHE` | Output lấy từ cache entry phù hợp |
| `NO-SOURCE` | Task xử lý file không có source phù hợp; kiểm tra input file collection |
| `SKIPPED` | Task bỏ qua theo điều kiện/chế độ; ví dụ `--dry-run` |
| `FAILED` | Task thực thi lỗi; cần xem task path và nguyên nhân |
| `BUILD SUCCESSFUL` | Graph được yêu cầu đã hoàn tất, không khẳng định task này chạy lại hay cache hit |

### 13.3. Tình huống và nguyên nhân

**Tình huống A: cùng source trên CI nhưng lần nào cũng rebuild.**

Kiểm tra:
- Task type đã cacheable và build cache đã bật?
- `@PathSensitive` đang dùng `ABSOLUTE` hoặc output có nhúng path?
- Root checkout khác, nhưng task lại đọc `projectDir.absolutePath`?
- JDK/tool version khác hoặc một input có timestamp/UUID?
- Có cache chung được đọc không, hay mỗi CI job có cache rỗng?

**Tình huống B: task báo `FROM-CACHE` nhưng output sai tên file.**

Khả năng: task đã dùng `PathSensitivity.NONE` hoặc `NAME_ONLY` dù basename/relative path có ảnh hưởng output; nguồn input thực sự chưa khai báo hết. Đây là bug về **cache correctness**, không phải Gradle “đọc nhầm cache”.

**Tình huống C: chỉ đổi LF/CRLF nhưng cache miss.**

Kiểm tra annotation `@NormalizeLineEndings` đã đặt trên đúng input property chưa; còn các input khác nào thay đổi không; tool khác có ghi metadata/encoding khác vào file? **Không được** thêm annotation một cách mù quáng nếu output là raw bytes.

**Tình huống D: task báo `UP-TO-DATE` sau khi sửa tool script bên ngoài.**

Kiểm tra tool file/version có được khai báo như input hoặc classpath chưa. Nếu script được đọc/exec nhưng không xuất hiện trong fingerprint, cache và up-to-date có thể sai.

**Tình huống E: archive khác bytes giữa hai lần tạo.**

Kiểm tra thứ tự file, timestamps, manifest, encoding, file permissions, absolute paths, tool version và input ngầm. Bật reproducible archive flags chỉ là một phần; so sánh hash và phân tích từng entry để tìm dữ liệu thay đổi.

**Tình huống F: task chỉ chạy một lần nhưng vẫn báo thành công sau khi thay đổi env.**

Kiểm tra task có đọc env trực tiếp mà không khai báo nó là input không. Ví dụ sai:

~~~groovy
tasks.register('wrongEnvTask') {
    doLast {
        println System.getenv('REPORT_MODE')
    }
}
~~~

Đây là task in log không cache artifact, nhưng minh họa một input ngầm. Nếu output artifact phụ thuộc `REPORT_MODE`, nên thêm property của task được cấp từ `providers.environmentVariable('REPORT_MODE')` và đánh dấu `@Input`.

## 14. Bài tập tự luyện có đáp án

### Bài 1. Chọn PathSensitivity

Một custom task đọc `docs/a/readme.md`, chỉ lấy nội dung bytes rồi tạo `summary.txt`, không ghi tên file. Đổi file input sang `docs/b/other.md` có cùng nội dung. Có thể chọn gì?

**Đáp án:** `NONE` có thể đúng vì output không phụ thuộc tên/path, miễn task thực sự không dùng path làm dữ liệu và không có input ngầm.

### Bài 2. Bẫy NAME_ONLY

Task quét `docs/api/intro.md` và `docs/guide/intro.md` để sinh sitemap chứa relative paths. Chọn `NAME_ONLY` được không?

**Đáp án:** Không. Hai file trùng basename nhưng directory có ý nghĩa. Chọn `RELATIVE` và sinh/sắp xếp output theo relative path ổn định.

### Bài 3. Annotation không rewrite output

Một task có `@NormalizeLineEndings`, nhưng hành động copy nguyên source bytes ra output. Với CRLF/LF, cache có thể không chính xác ở đâu?

**Đáp án:** Gradle có thể xem input tương đương trong khi bytes output khác. Cần bỏ normalization annotation hoặc thay đổi task để output cũng được normalize theo cùng ngữ nghĩa.

### Bài 4. Reproducible và cacheable

Task sinh file có `@InputFile`, `@OutputFile` nhưng ghi `Instant.now()` vào nội dung mỗi lần thực thi. Vì sao không nên đánh dấu cacheable?

**Đáp án:** Thời gian không được khai báo như input làm cùng fingerprint có thể ứng với output khác; kết quả không deterministic. Loại timestamp hoặc biến thời gian thành input có chủ đích khi phù hợp.

### Bài 5. Đọc task status

Bạn chạy `./gradlew renderNotes`, lần hai nhận `UP-TO-DATE`. Sau `./gradlew clean renderNotes --build-cache`, nhận `FROM-CACHE`. Hai trạng thái chứng minh điều gì?

**Đáp án:** Lần hai, output hiện hữu được Gradle chấp nhận; lần sau clean, output được khôi phục từ cache entry. Không có action bắt buộc được chạy trong hai trường hợp này.

### Bài 6. Task output độc lập đường dẫn

Task đặt output vào `build/generated/notes.md`, nhưng bytes file lại chứa `/home/user/project/docs/source.txt`. Task có relocatable không nếu khai `NONE`?

**Đáp án:** Không đúng hợp đồng: output vẫn phụ thuộc absolute input path. Cần loại path hoặc dùng relative path có khai báo input tương ứng; `NONE` không “tẩy” dependency thật.

### Bài 7. Tool version

Custom task gọi một external compiler nhưng không khai version/tool path. Vì sao cache reuse có nguy cơ sai?

**Đáp án:** Thay compiler có thể thay bytes output dù declared inputs giống nhau. Cần đưa tool implementation/classpath/version và cấu hình liên quan vào task inputs theo API phù hợp, hoặc tắt cache khi không bảo đảm điều kiện.

### Bài 8. Thực hành chứng minh

Với project phần 7:
1. Chạy `renderNotes` lần đầu và xem output.
2. Chạy lần hai, quan sát `UP-TO-DATE` nếu điều kiện giữ nguyên.
3. Chạy `clean renderNotes --build-cache`, kiểm tra `FROM-CACHE` khi entry phù hợp có trong cache.
4. Đổi chỉ line endings của `docs/source.txt` và xác nhận output LF.
5. Đổi `-PnotesHeading=Khác`, quan sát đầu ra thay đổi và Gradle đánh giá input khác.
6. Đem source sang checkout sạch khác, cấu hình cache chung, xem khả năng khôi phục.

**Tiêu chí hoàn thành:** Bạn nói được “đường dẫn nào có ý nghĩa”, hiểu `@NormalizeLineEndings` chỉ đổi fingerprint chứ không đổi file, thiết kế được task tạo output deterministic, kiểm chứng được up-to-date/cache và phân biệt reuse code với reuse task output.

## Tài liệu Gradle chính thức

- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): input/output declarations và up-to-date checks.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): nguyên tắc reuse task output.
- [Gradle — Task Output Caching](https://docs.gradle.org/current/userguide/build_cache_concepts.html): cache key, correctness, relocatability và output caching.
- [Gradle — Runtime API: PathSensitivity](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/PathSensitivity.html): các lựa chọn ABSOLUTE, RELATIVE, NAME_ONLY, NONE.
- [Gradle — Annotation: PathSensitive](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/PathSensitive.html): fingerprint path ở file input.
- [Gradle — Annotation: NormalizeLineEndings](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/NormalizeLineEndings.html): chuẩn hóa line ending trong fingerprint.
- [Gradle — Authoring Tasks](https://docs.gradle.org/current/userguide/writing_tasks.html): task type, properties, actions.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): khác biệt với task output build cache.
- [Gradle — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): normalized file inputs và reproducible archives.
