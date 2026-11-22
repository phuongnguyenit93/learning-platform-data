# Xử lý thay đổi tệp bằng `InputChanges` cho task tăng dần trong Gradle

## 1. Bài toán và mục tiêu

Giả sử một task tùy chỉnh phải chuyển hàng nghìn file `.txt` thành file viết hoa, tạo mã Java từ schema hoặc xử lý từng tài nguyên. Ở lần chạy đầu, Gradle cần xử lý toàn bộ đầu vào. Khi người dùng chỉ sửa **một** file, nếu task luôn duyệt và xử lý lại tất cả file, build sẽ chậm dù công việc thực sự thay đổi rất ít.

Gradle hỗ trợ hai tầng tối ưu khác nhau:

1. **Up-to-date check (incremental build cơ bản):** Gradle so sánh trạng thái đầu vào/đầu ra đã khai báo; nếu không có thay đổi hợp lệ, **bỏ qua cả task action**, có thể hiện `UP-TO-DATE`.
2. **Incremental task action:** khi task **phải chạy**, action nhận `org.gradle.work.InputChanges` để biết **những file cụ thể** có sự kiện `ADDED`, `MODIFIED` hoặc `REMOVED`, rồi chỉ xử lý phần cần thiết.

Bài học tập trung vào tầng thứ hai. Bạn sẽ:

- Khai báo input file/directory và output bằng **typed Gradle properties** cùng annotations.
- Viết `@TaskAction` nhận tham số `InputChanges` do Gradle cung cấp.
- Phân biệt `inputChanges.incremental == true` với `false` và xử lý được cả hai.
- Xử lý chính xác file mới, thay đổi và bị xóa; giữ cấu trúc thư mục bằng `normalizedPath`.
- Hiểu tác động của non-file input, output bị sửa/xóa, `--rerun-tasks`, đổi Gradle version và nguồn dữ liệu chưa có lịch sử.
- Tự kiểm bằng lệnh chạy ở Bash và PowerShell, phân biệt incremental execution, `UP-TO-DATE`, build cache và configuration cache.
- Tránh những lỗi làm task sai kết quả dù log “BUILD SUCCESSFUL”.

**Ý chính:** task tăng dần không có nghĩa “chỉ dùng `getFileChanges` là xong”. Trước tiên phải khai báo **tất cả input và output ảnh hưởng đến kết quả**; sau đó mới tối ưu phần xử lý thay đổi.

## 2. Mô hình hoạt động của Gradle

```text
Task đã đăng ký
      |
      v
Gradle chụp/truy vết các @Input, @InputFiles/@InputDirectory,
@OutputFile/@OutputDirectory và lịch sử từ lần thực thi trước
      |
      +-- Input/output không thay đổi, điều kiện hợp lệ?
      |         |
      |         +-- Có --> Task UP-TO-DATE --> KHÔNG chạy @TaskAction
      |         |
      |         +-- Không --> phải chạy task action
      |                         |
      |                         v
      |                Có đủ lịch sử và chỉ incremental file inputs đổi?
      |                         |
      |                +--------+--------+
      |                |                 |
      |                Có                Không
      |                |                 |
      |                v                 v
      |           isIncremental=true  isIncremental=false
      |           Chỉ báo file đổi   Tất cả file hiện có
      |           ADDED/MODIFIED/    được báo như ADDED
      |           REMOVED
      |                |                 |
      |                +--------+--------+
      |                         v
      |               Tạo/cập nhật/xóa output đúng cách
      |                         |
      v                         v
 Gradle lưu thông tin cần cho lần kế tiếp
```

Sơ đồ trên mô tả logic; trong build bật build cache, Gradle còn có thể **khôi phục output từ cache mà không chạy action**. Thứ tự ưu tiên tối ưu do Gradle quyết định, không nên suy ra mọi lần output thay đổi đều đi qua `@TaskAction`.

**Phân biệt rõ:**

| Cơ chế | Dùng để làm gì? | Có gọi `@TaskAction` không? |
| --- | --- | --- |
| `UP-TO-DATE` | Task có input/output hợp lệ, không cần làm lại | Không |
| Incremental execution | Task phải chạy, nhưng chỉ một phần file đổi | Có, `InputChanges.isIncremental() == true` |
| Non-incremental execution | Task phải tái xử lý toàn bộ input file được báo | Có, `InputChanges.isIncremental() == false` |
| Build cache (`FROM-CACHE`) | Tái sử dụng task outputs đã lưu theo fingerprints | Thường không |
| Configuration cache | Tái sử dụng kết quả **configuration/task graph**, không phải output | Không quyết định riêng task action có chạy hay không |

Task ở chế độ non-incremental **không phải** task làm sai; đó là nhánh hợp lệ khi Gradle không đủ dữ liệu để xác định tập file đổi.

## 3. API và annotations cần biết

| API / annotation | Vai trò |
| --- | --- |
| `@TaskAction` trên method nhận `InputChanges` | Đánh dấu **incremental task action**; Gradle cung cấp đối tượng `InputChanges` khi chạy task |
| `@Incremental` | Đánh dấu input file property có thể được hỏi danh sách thay đổi qua `getFileChanges(...)` |
| `@InputDirectory` | DirectoryProperty là directory đầu vào được Gradle kiểm tra |
| `@InputFiles` | FileCollection/collection file đầu vào; dùng khi source là tập file thay vì một directory |
| `@SkipWhenEmpty` | Trên `@InputFiles` hoặc `@InputDirectory`, yêu cầu skip khi không có nguồn; annotation này **đã hàm ý incremental** |
| `@PathSensitive(PathSensitivity.RELATIVE)` | Chuẩn hóa đường dẫn tương đối để fingerprint và `normalizedPath` ít phụ thuộc đường dẫn tuyệt đối |
| `@OutputDirectory` | Khai báo thư mục output do task chịu trách nhiệm |
| `@Input` | Khai báo input giá trị thông thường, ví dụ tùy chọn prefix hoặc mode |
| `DirectoryProperty` | Provider có kiểu cho thư mục input/output, giữ identity ổn định |
| `InputChanges.isIncremental()` | Cho biết có thể dùng thông tin thay đổi so với lần trước không |
| `InputChanges.getFileChanges(inputDir)` | Trả các `FileChange` cho input đã đánh dấu incremental |
| `FileChange.changeType` | `ADDED`, `MODIFIED` hoặc `REMOVED` |
| `FileChange.file` | Tệp đang thay đổi; **có thể không tồn tại** ở trường hợp `REMOVED` |
| `FileChange.normalizedPath` | Path đã chuẩn hóa theo `PathSensitivity` |
| `FileChange.fileType` | Loại file, thường cần bỏ qua `FileType.DIRECTORY` khi chỉ xử lý file |

Để `InputChanges.getFileChanges(...)` hoạt động, **tham số phải là đúng input file property** có annotation `@Incremental` hoặc `@SkipWhenEmpty`. Đừng truyền một `files(...)` mới tạo tùy ý từ đường dẫn tương tự: property cần có **identity ổn định** để Gradle khớp nó với metadata đã thu thập.

**Giới hạn chữ ký:** chỉ nên có **một incremental task action** trong một task; method đó nhận **một tham số `InputChanges`**. Không tự gọi constructor `InputChanges`, không lấy `InputChanges` trong phase configuration, và không đưa nó vào `doLast { ... }` như tham số tùy ý. API nằm trong `org.gradle.work`, không nhầm với `org.gradle.api.tasks.incremental` của những ví dụ Gradle rất cũ.

## 4. Ví dụ độc lập: chuyển `.txt` sang chữ hoa theo từng file

Ví dụ dưới đây dùng **Gradle Groovy DSL**, không cần plugin bên ngoài, không yêu cầu code Java ứng dụng. Task `uppercaseIncremental` đọc các file dưới `inputs/`, ghi output tương ứng dưới `build/uppercase/`, có thể xử lý các thay đổi kể cả **xóa file**. Các file con giữ nguyên cấu trúc thư mục.

### 4.1. Tạo cấu trúc

```text
inputchanges-demo/
├── settings.gradle
├── build.gradle
├── inputs/
│   └── first.txt
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'inputchanges-demo'
```

`inputs/first.txt`, lưu dưới dạng UTF-8 với nội dung:

```text
hello gradle
```

Có thể để một newline ở cuối file; không ảnh hưởng ý nghĩa ví dụ. Nếu repository đã có Gradle Wrapper, dùng Wrapper được commit. Nếu làm thư mục hoàn toàn mới, cần cài Gradle tạm để chạy `gradle wrapper` lần đầu rồi dùng `./gradlew` hoặc `.\gradlew.bat` cho các lệnh tiếp theo. Ví dụ phù hợp với Gradle hiện đại có `InputChanges` (API từ Gradle 5.4); dùng Wrapper và JDK phiên bản được Gradle tương ứng hỗ trợ.

### 4.2. Toàn bộ `build.gradle` chạy được

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.GradleException
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.FileType
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.ChangeType
import org.gradle.work.Incremental
import org.gradle.work.InputChanges
import java.util.Locale

abstract class UppercaseIncrementalTask extends DefaultTask {

    @Incremental
    @InputDirectory
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract DirectoryProperty getSourceDir()

    @OutputDirectory
    abstract DirectoryProperty getDestinationDir()

    @Input
    abstract Property<String> getPrefix()

    @TaskAction
    void transform(InputChanges inputChanges) {
        println(inputChanges.incremental
            ? 'MODE=INCREMENTAL'
            : 'MODE=FULL'
        )

        inputChanges.getFileChanges(sourceDir).each { change ->
            // Sự kiện directory không phải tệp văn bản cần chuyển đổi.
            if (change.fileType == FileType.DIRECTORY) {
                return
            }

            // Relative path tạo tên output ổn định theo inputDir.
            String relativePath = change.normalizedPath
            File target = destinationDir.file(relativePath).get().asFile

            switch (change.changeType) {
                case ChangeType.REMOVED:
                    // Input đã bị xóa: không cố đọc change.file!
                    if (target.exists() && !target.delete()) {
                        throw new GradleException(
                            "Cannot delete output: ${target}"
                        )
                    }
                    println("REMOVED: ${relativePath}")
                    break

                case ChangeType.ADDED:
                case ChangeType.MODIFIED:
                    // Input vẫn tồn tại: tạo/cập nhật đúng một output.
                    if (!target.parentFile.exists() &&
                            !target.parentFile.mkdirs()) {
                        throw new GradleException(
                            "Cannot create output directory: ${target.parent}"
                        )
                    }
                    String transformed = prefix.get() +
                        change.file.getText('UTF-8')
                            .toUpperCase(Locale.ROOT)
                    target.setText(transformed, 'UTF-8')
                    println("${change.changeType}: ${relativePath}")
                    break
            }
        }
    }
}

tasks.register('uppercaseIncremental', UppercaseIncrementalTask) {
    group = 'learning'
    description = 'Viết hoa các file văn bản theo thay đổi đầu vào'

    sourceDir.set(layout.projectDirectory.dir('inputs'))
    destinationDir.set(layout.buildDirectory.dir('uppercase'))
    prefix.set(providers.gradleProperty('prefix').orElse(''))
}
```

**Những chi tiết không thể bỏ qua:**

1. `@Incremental` + `@InputDirectory` cho Gradle biết `sourceDir` là **file input dùng để truy vấn thay đổi**, không chỉ một thư mục để task tự duyệt.
2. `@PathSensitive(PathSensitivity.RELATIVE)` dùng đường dẫn tương đối từ input root. Ví dụ `inputs/nested/a.txt` tương ứng `build/uppercase/nested/a.txt`. Đường dẫn dưới root được Gradle chuẩn hóa, tránh mang đường dẫn tuyệt đối máy developer vào output mapping.
3. `@OutputDirectory` để Gradle theo dõi output. Không ghi file vào `inputs/`, vì vừa sửa input vừa xử lý nó có thể tạo vòng cập nhật liên tục.
4. `@Input` trên `prefix` bảo đảm khi tùy chọn này đổi, Gradle biết kết quả chuyển đổi có thể đổi **với mọi file**, không thể chỉ lấy file vừa sửa.
5. Trong `REMOVED` dùng `normalizedPath` để tìm và **xóa output cũ**; không đọc `change.file.text` vì file nguồn có thể không tồn tại.
6. Trong `ADDED` và `MODIFIED`, task chỉ xử lý file tương ứng; dùng `UTF-8` và `Locale.ROOT` để tránh hành vi khác nhau giữa môi trường ngôn ngữ và encoding.
7. `DirectoryProperty` giữ đối tượng property ổn định; `getFileChanges(sourceDir)` nhận **chính property** đã gắn annotation.
8. `tasks.register(...)` tạo task theo cơ chế lazy, không tự realize task lúc cấu hình build.
9. Các file output đặt trong `layout.buildDirectory`; hãy coi thư mục `build/uppercase` là vùng output **chỉ do task này sở hữu**.

**Phạm vi của ví dụ:** chỉ phù hợp với **text UTF-8**. Một file nhị phân bị đưa vào `inputs/` không nên xử lý bằng `getText` và `setText`; với build thật có thể dùng `FileTree` + input filtering hoặc kiểm tra extension/type trước khi chuyển đổi và khai báo đầy đủ logic đó. Cũng cần quy định rõ cách xử lý symlink, file permission và tên file không hợp lệ trên OS nếu dữ liệu có thể đến từ người dùng không tin cậy.

## 5. Kịch bản kiểm chứng `ADDED`, `MODIFIED` và `REMOVED`

Các kết quả dưới đây giả định mỗi lần chỉ thay đổi đúng file được nêu, dùng cùng phiên bản Gradle/đường dẫn build và không có process khác sửa output. `-q` ẩn phần lớn log Gradle để dễ nhìn dòng của task.

### 5.1. Lần đầu: không có lịch sử -> chạy toàn bộ

```bash
./gradlew -q uppercaseIncremental
```

Các dòng do task in:

```text
MODE=FULL
ADDED: first.txt
```

Đọc file:

```bash
cat build/uppercase/first.txt
```

Nội dung:

```text
HELLO GRADLE
```

**Vì sao `MODE=FULL`?** Chưa có lịch sử thực thi để Gradle so sánh, nên `inputChanges.incremental == false`. Khi đó `getFileChanges(sourceDir)` báo **mọi file hiện có** như `ADDED`, dù người dùng chưa “thêm” chúng trong lượt chạy này.

Nếu source file có newline, output cũng chứa newline. Kết quả phía trên trình bày nội dung nhìn thấy, không ép câu trả lời chứa byte newline đặc biệt.

### 5.2. Lần hai: không thay đổi -> task bị `UP-TO-DATE`

```bash
./gradlew uppercaseIncremental --console=plain
```

Gradle có thể in dòng tương tự:

```text
> Task :uppercaseIncremental UP-TO-DATE
```

**Không có** `MODE=INCREMENTAL` hay `ADDED`: Gradle **không gọi action**, nên không thể có một danh sách `getFileChanges` của lần này. Lệnh `-q` có thể không in gì khi task được bỏ qua; không hiểu “không in” là “task bị mất”.

### 5.3. Sửa đúng một file -> `MODIFIED`

Trên Linux/macOS với Bash/zsh:

```bash
printf 'changed data\n' > inputs/first.txt
./gradlew -q uppercaseIncremental
cat build/uppercase/first.txt
```

Dòng từ task (không bao gồm dòng do `cat`):

```text
MODE=INCREMENTAL
MODIFIED: first.txt
```

Nội dung output:

```text
CHANGED DATA
```

Gradle chỉ báo file có nội dung thay đổi; task không duyệt và chuyển đổi lại các file chưa đổi.

### 5.4. Thêm file mới -> `ADDED`

```bash
printf 'second\n' > inputs/second.txt
./gradlew -q uppercaseIncremental
cat build/uppercase/second.txt
```

Dòng từ task:

```text
MODE=INCREMENTAL
ADDED: second.txt
```

File mới có nội dung:

```text
SECOND
```

Task chỉ tạo `build/uppercase/second.txt`, vẫn giữ output `first.txt` hợp lệ từ lần trước.

### 5.5. Xóa file nguồn -> `REMOVED` và xóa output tương ứng

```bash
rm inputs/second.txt
./gradlew -q uppercaseIncremental
test ! -e build/uppercase/second.txt && echo 'Output removed'
```

Các dòng do task in:

```text
MODE=INCREMENTAL
REMOVED: second.txt
```

Dòng cuối do lệnh `test/echo` in:

```text
Output removed
```

Nếu chỉ xử lý ADDED/MODIFIED mà bỏ qua `REMOVED`, file `second.txt` cũ vẫn nằm trong output, dễ bị đóng gói nhầm vào artifact. **Đây là lỗi logic rất thường gặp ở custom incremental task**.

### 5.6. Đổi non-file input -> Gradle phải xử lý toàn bộ

`prefix` được khai báo bằng `@Input` và ảnh hưởng đến mọi output. Chạy:

```bash
./gradlew -q uppercaseIncremental -Pprefix=CI-
cat build/uppercase/first.txt
```

Phần stdout task kỳ vọng:

```text
MODE=FULL
ADDED: first.txt
```

Nội dung file:

```text
CI-CHANGED DATA
```

Dù nội dung `inputs/first.txt` không đổi so với lần trước, **giá trị `prefix` đổi** khiến Gradle không thể khẳng định chỉ một số file bị ảnh hưởng. Nó báo mọi source file hiện có là `ADDED` trong **non-incremental execution**. Khi quay lại default bằng cách bỏ `-Pprefix`, một lần xử lý toàn bộ có thể diễn ra nữa do input giá trị đổi ngược.

Đây là lý do bắt buộc khai báo **non-file inputs** có tác động tới output, thay vì đọc `System.getenv` hoặc `project.findProperty` trực tiếp trong task action mà Gradle không biết.

### 5.7. Xóa/sửa output hoặc yêu cầu chạy lại -> non-incremental

```bash
./gradlew -q uppercaseIncremental --rerun-tasks
```

Lượt chạy này thường in:

```text
MODE=FULL
ADDED: first.txt
```

Tương tự, khi file output do task quản lý bị sửa/xóa ngoài Gradle, lần chạy kế tiếp có thể phải **rebuild toàn bộ** vì Gradle không thể suy ra mapping giữa thay đổi output tùy ý và từng input file.

Theo hợp đồng incremental tasks của Gradle, khi chuyển sang non-incremental execution, Gradle xử lý việc loại bỏ **output cũ của task** trước khi action tái sinh kết quả. Action trong ví dụ chỉ cần đi qua tất cả đầu vào được báo `ADDED`; **không tự xóa tất cả output trong mọi lượt chạy incremental**, vì làm thế sẽ mất những file output hợp lệ tương ứng với input không đổi.

## 6. Thực hành trên Windows PowerShell

Các **Gradle task declarations không đổi** giữa Linux, macOS và Windows. Chỉ cú pháp shell và đường dẫn khi thao tác file khác nhau.

Tại root thư mục demo:

```powershell
.\gradlew.bat -q uppercaseIncremental
Get-Content build\uppercase\first.txt
```

Để sửa file nguồn và chạy lại, có thể viết UTF-8 (không BOM) bằng .NET:

```powershell
[System.IO.File]::WriteAllText(
    (Join-Path (Get-Location) 'inputs\first.txt'),
    "updated on windows" + [Environment]::NewLine,
    (New-Object System.Text.UTF8Encoding($false))
)
.\gradlew.bat -q uppercaseIncremental
Get-Content build\uppercase\first.txt
```

Phần log của task trong điều kiện có lịch sử hợp lệ:

```text
MODE=INCREMENTAL
MODIFIED: first.txt
```

Nội dung output tương ứng:

```text
UPDATED ON WINDOWS
```

Thêm file bằng `[IO.File]::WriteAllText(...)`; xóa bằng `Remove-Item inputs\second.txt`. Sau mỗi thay đổi, gọi `.\gradlew.bat -q uppercaseIncremental`. Trong Command Prompt, dùng `gradlew.bat` (không có `.\` nếu đang ở thư mục chứa script). Không dùng cú pháp `printf`, `rm` hoặc `BUILD_ID=x command` của Bash nguyên xi trong PowerShell.

**Lưu ý ký tự xuống dòng:** Windows thường dùng CRLF, Linux/macOS thường dùng LF. Vì `getText`, `toUpperCase`, `setText` **không thay đổi newline**, output giữ kiểu newline của nguồn. Hai file có nội dung nhìn thấy giống nhau nhưng bytes LF/CRLF khác vẫn có thể tạo `MODIFIED`. Nếu ứng dụng coi LF và CRLF tương đương, cân nhắc `@NormalizeLineEndings` hoặc bước chuẩn hóa output được tài liệu hóa, nhưng đừng âm thầm biến đổi dữ liệu ngoài yêu cầu.

## 7. Vì sao phải có `@Incremental` hoặc `@SkipWhenEmpty`?

Một task có `@InputDirectory` hoặc `@InputFiles`, `@OutputDirectory` và `@TaskAction` **chưa đủ** để hỏi `getFileChanges(...)` từng file trong incremental action. Property cần annotation:

```groovy
@Incremental
@InputDirectory
@PathSensitive(PathSensitivity.RELATIVE)
abstract DirectoryProperty getSourceDir()
```

`@Incremental` cho Gradle biết file input đó có thể phân tích thay đổi để task action sử dụng. Nếu không có, `getFileChanges(sourceDir)` có thể không hợp lệ cho property này. Nếu bạn cần skip khi không có nguồn:

```groovy
@SkipWhenEmpty
@InputDirectory
@PathSensitive(PathSensitivity.RELATIVE)
abstract DirectoryProperty getSourceDir()
```

`@SkipWhenEmpty` **hàm ý `@Incremental`** theo API; không cần đặt cả hai chỉ để yêu cầu truy vết file changes. Khi tất cả input file properties mang `@SkipWhenEmpty` đều rỗng, task thường có outcome `NO-SOURCE` và không chạy action. Trong ví dụ chính chọn `@Incremental` để có thể quan sát cả nhánh không có sự kiện; với pipeline không có source thì `@SkipWhenEmpty` thường hợp hơn.

**Không dùng `@Input` cho DirectoryProperty khi mục tiêu là snapshot nội dung file:** `@Input` dùng cho giá trị; đối với file content phải khai báo `@InputFile`/`@InputFiles`/`@InputDirectory` phù hợp. File chỉ tham gia dưới dạng chuỗi đường dẫn không đảm bảo Gradle kiểm tra thay đổi nội dung.

### 7.1. Khi đầu vào là `ConfigurableFileCollection`

Một task có thể nhận file từ nhiều nguồn:

```groovy
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.work.Incremental

abstract class MultiSourceTask extends DefaultTask {
    @Incremental
    @InputFiles
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract ConfigurableFileCollection getSources()

    @TaskAction
    void process(InputChanges changes) {
        changes.getFileChanges(sources).each { change ->
            // Xử lý change.file, change.changeType, change.normalizedPath.
        }
    }
}
```

Đây là **trích đoạn giải thích API**, chưa phải task production hoàn chỉnh: cần khai báo output, logic mapping/xóa output và những imports khác trong class. `InputChanges.getFileChanges(FileCollection)` hỗ trợ `ConfigurableFileCollection` khi property được đánh dấu incremental. Nếu các file đến từ nhiều root có đường dẫn giống nhau, phải giải quyết **output name collisions**; không được mặc định mọi `normalizedPath` là duy nhất khi thay đổi root/sensitivity.

### 7.2. Nhiều input properties

Có thể có một `@InputFiles` chứa Java files và một `@InputFiles` chứa JSON schemas; mỗi property phải có annotation/phạm vi thích hợp, và action có thể gọi `getFileChanges` **cho từng property riêng**. Nếu một input **không incremental** đổi, Gradle có thể chuyển cả task sang `isIncremental=false`, chứ không cho bạn danh sách thay đổi đáng tin của phần còn lại.

Không trộn hai loại file khác nhau vào một collection rồi dùng `.endsWith(...)` ngầm để dự đoán role nếu việc phân loại cần tính ổn định. Tên property và output mapping phải nói rõ loại dữ liệu nào tạo ra file nào.

## 8. `PathSensitivity` và `normalizedPath` quyết định tính đúng đắn

`normalizedPath` là path do Gradle tạo dựa trên chiến lược chuẩn hóa đầu vào, **không đơn giản là `change.file.absolutePath`**.

| Chiến lược | Ý nghĩa | Khi nên xem xét |
| --- | --- | --- |
| `PathSensitivity.RELATIVE` | So sánh relative path, bỏ phần root tuyệt đối | Thường phù hợp cho thư mục input có cấu trúc lồng |
| `PathSensitivity.NAME_ONLY` | Quan tâm tên file, không phân biệt cây thư mục đầy đủ | Chỉ phù hợp khi tên file đủ để nhận diện, tránh va chạm |
| `PathSensitivity.NONE` | Không coi file path là thành phần quan trọng của fingerprint | Khi output hoàn toàn không phụ thuộc tên/path input |
| `PathSensitivity.ABSOLUTE` | Path tuyệt đối ảnh hưởng fingerprint | Chỉ khi đường dẫn thực sự là phần kết quả; ít portable |

Ví dụ có:

```text
inputs/a/info.txt
inputs/b/info.txt
```

Nếu output yêu cầu giữ hai nhánh `a` và `b`, hãy dùng `RELATIVE`. Dùng `NAME_ONLY` rồi ghi `outputDir.file(change.normalizedPath)` có thể làm hai input khác nhau cùng trỏ vào một output `info.txt`, gây ghi đè hoặc xóa nhầm. `NONE` có thể báo một lần sửa như cặp `ADDED` + `REMOVED` thay vì `MODIFIED` theo hợp đồng `getFileChanges`; vì thế logic xử lý file cần chấp nhận tập sự kiện thực tế do Gradle báo.

**Đừng xem normalizedPath là path tuyệt đối hoặc URL.** Với task sinh artifact, dùng `DirectoryProperty.file(relativePath)` và đảm bảo output thuộc thư mục task sở hữu. Trong môi trường nhiều root, cần chiến lược tên ổn định và không collision. Với nội dung không tin cậy, validate đường dẫn/traversal và không để task ghi ngoài output root.

## 9. Xử lý `REMOVED` và đổi tên tệp

Gradle cung cấp **ba loại thay đổi**:

- `ChangeType.ADDED`: một file hiện có trong snapshot mới nhưng không tương ứng snapshot trước, hoặc **toàn bộ file** khi chạy non-incremental.
- `ChangeType.MODIFIED`: file tồn tại ở cả hai snapshot nhưng metadata/contents được theo dõi thay đổi theo normalization.
- `ChangeType.REMOVED`: file có trong snapshot trước nhưng không còn trong snapshot mới.

**Không có `ChangeType.RENAMED`.** Khi người dùng đổi tên `a.txt` thành `b.txt`, Gradle thường báo `REMOVED: a.txt` và `ADDED: b.txt`. Task phải **xóa output cũ** và tạo output mới theo đường dẫn mới. Nếu lỡ chỉ xử lý `MODIFIED`, artifact sau nhiều lần đổi tên sẽ tích lũy file rác.

Một lỗi phổ biến:

```groovy
// Sai: change.file có thể đã bị xóa!
if (change.changeType == ChangeType.REMOVED) {
    println change.file.text
}
```

Sửa:

```groovy
// Đúng hướng: mapping path cũ -> output cũ, không đọc input đã xóa.
if (change.changeType == ChangeType.REMOVED) {
    File stale = destinationDir.file(change.normalizedPath).get().asFile
    if (stale.exists() && !stale.delete()) {
        throw new GradleException("Cannot delete ${stale}")
    }
}
```

Đoạn trên **cần các property/imports và context từ task đầy đủ ở phần 4**. Sau khi xóa file, có thể còn thư mục output rỗng. Có thể dọn thư mục trống nằm **bên trong output root** bằng logic riêng, nhưng không xóa thư mục mà task khác đang sở hữu hoặc xóa cả build root theo phản xạ.

## 10. Những trường hợp khiến `isIncremental == false`

Task action phải xử lý được trạng thái **không thể phân tích incremental**. Những lý do thường gặp:

| Tình huống | Điều Gradle có thể quyết định |
| --- | --- |
| Lần chạy đầu tiên, không có execution history | `false`, tất cả file hiện có báo `ADDED` |
| Chạy bằng Gradle version khác so với lịch sử trước | Có thể không tái sử dụng lịch sử task, phải chạy full |
| `--rerun-tasks` | Bỏ qua tối ưu up-to-date, incremental action nhận thông tin non-incremental |
| Input giá trị `@Input` đổi, ví dụ `prefix` | Mọi output có thể bị ảnh hưởng, phải xử lý lại |
| Một file input **không** đánh dấu incremental đổi | Không đủ cơ sở xác định tập thay đổi an toàn, thường full |
| Output file/thư mục do task quản lý bị sửa hoặc thiếu | Trạng thái output không khớp lịch sử; Gradle phải tạo lại |
| Tiêu chí `upToDateWhen` tùy chỉnh trả `false` | Task bị yêu cầu làm lại, không có danh sách change incremental đáng tin |
| Xóa `build/`/clean, đổi vị trí checkout với lịch sử không phù hợp | Thiếu lịch sử/output trước đó, full |

Khi `isIncremental=false`, lời gọi `getFileChanges(sourceDir)` **không có nghĩa danh sách “file được thêm mới từ filesystem”**. Nó trả về toàn bộ file input hiện tại với `ChangeType.ADDED` để task có thể rebuild đầy đủ.

**Output cleanup:** tài liệu Gradle về incremental tasks mô tả Gradle tự loại bỏ output cũ khi task chạy non-incrementally. Vì thế ví dụ chính không tự `deleteRecursively()` output ở mọi lần chạy. Nếu task còn tạo dữ liệu ngoài `@OutputDirectory`, Gradle không thể bảo vệ hoặc dọn dẹp dữ liệu không khai báo; đây là dấu hiệu cần sửa model outputs chứ không phải thêm lệnh xóa tùy ý.

## 11. Incremental execution không thay cho quản lý task inputs/outputs

### 11.1. Đừng đọc file ngầm ngoài property đã khai báo

```groovy
// Anti-pattern: Gradle chỉ thấy sourceDir, nhưng task còn đọc file khác.
def extraRules = file('/home/alice/custom-rules.txt').text
```

Nếu output phụ thuộc `custom-rules.txt` mà task không khai báo file là input, Gradle có thể coi task `UP-TO-DATE` sai hoặc chạy incremental khi lẽ ra phải full. Giải pháp: đưa rule file vào `RegularFileProperty` với `@InputFile`, hoặc đưa checksum/content đã xác định vào `@Input`, tùy nội dung và ngữ nghĩa. Nếu rule file ảnh hưởng **tất cả file**, thay đổi rule thường yêu cầu **full rebuild**, không chỉ xử lý một source file.

### 11.2. Không lấy dữ liệu từ `Project` trong task action khi cần configuration cache

Trong task action, tránh đọc `project.file(...)`, `project.findProperty(...)` hoặc tự duyệt task/project model. Tập trung vào **input properties của task**. Cấu hình file paths/Providers trong `tasks.register { ... }`; task đọc property đã được inject/wire khi thực thi. Đây cũng là cơ sở để task dễ kiểm thử và cấu hình cache tương thích hơn.

### 11.3. Đăng ký output đầy đủ và không dùng chung tùy tiện

Nếu hai task cùng khai báo một `@OutputDirectory` rồi cùng ghi file, Gradle khó xác định ai sở hữu output, làm suy yếu incremental/build cache và có thể xảy ra race. Hãy phân vùng thư mục output theo task, hoặc thiết kế producer/consumer rõ ràng. Cũng đừng cho task vừa dùng `@InputDirectory` vừa ghi ngay dưới directory input, vì một lần sinh output sẽ trở thành **input change của chính nó**.

### 11.4. Không dựa vào thứ tự các `FileChange`

`InputChanges.getFileChanges(...)` cung cấp iterable các sự kiện; không coi thứ tự liệt kê là contract nghiệp vụ, nhất là khi có nhiều file hoặc directory lồng nhau. Nếu thứ tự xử lý tác động đến nội dung chung, phải thiết kế thứ tự deterministic hoặc thay mô hình incremental thành tổng hợp có kiểm soát.

Trong demo, mỗi file input tạo một output độc lập nên thứ tự xử lý không ảnh hưởng kết quả. Các ví dụ stdout chỉ dự đoán thứ tự khi **một file duy nhất thay đổi**.

## 12. Khi nào nên và không nên dùng `InputChanges`?

**Rất phù hợp:**

- Mỗi `.proto`/schema tạo một file mã nguồn độc lập và mapping có thể xác định.
- Mỗi file asset tạo một asset được tối ưu hóa, giữ cùng relative path.
- Mỗi tài liệu Markdown tạo một file HTML tương ứng và dễ xóa khi tài liệu nguồn bị xóa.
- Tập file lớn, thời gian xử lý mỗi file đáng kể, chỉ một số ít file đổi giữa các lần build.

**Cần thận trọng hoặc full rebuild có thể hợp lý hơn:**

- Một file thay đổi làm ảnh hưởng đến **mọi** output, ví dụ index toàn cục hoặc bundle chứa tất cả source.
- Xử lý phụ thuộc thứ tự, nội dung các file liên quan lẫn nhau, hoặc output tạo từ tổng hợp N file.
- Số file rất nhỏ, chi phí snapshot/mapping/cleanup lớn hơn chi phí làm lại.
- Task dùng công cụ bên ngoài có side effect, trạng thái không deterministic hoặc không mô tả được outputs.
- Build từ file thay đổi theo thời gian, network hay môi trường mà không thể khai báo thành input có thể fingerprint.

Với task tổng hợp một file từ nhiều nguồn, có thể dùng `InputChanges` để biết phần nào đổi nhưng vẫn cần **tính lại toàn bộ output**; tối ưu hóa partial chỉ đúng nếu thuật toán có thể cập nhật an toàn. Đừng tối ưu trước khi đo thời gian và xác định chính xác dependency dữ liệu.

## 13. Ghép output Provider sang task khác

Với Gradle, một pipeline mạnh hơn “task A chạy trước B” là **task B nhận provider của output task A**. Ví dụ có task tạo ra một directory và một task tiêu thụ nó, ta có thể nối các file properties trong configuration để Gradle suy ra dependency:

```groovy
// Trích đoạn minh họa trong cùng build.gradle với class ở phần 4.
def transform = tasks.named('uppercaseIncremental', UppercaseIncrementalTask)

tasks.register('listTransformedFiles') {
    // Đây chỉ là ví dụ đọc output; task production nên dùng typed input
    // để khai báo chính xác dữ liệu tiêu thụ và khả năng caching.
    dependsOn(transform)
    doLast {
        println "Output directory: ${transform.get().destinationDir.get().asFile}"
    }
}
```

Đoạn code này là **minh họa mối quan hệ đơn giản**, không phải ví dụ được khuyến nghị cho task production vì `doLast` truy cập task provider/project model. Với task thực tế, hãy tạo task type có `@InputDirectory DirectoryProperty` và kết nối:

```groovy
// Ý tưởng wiring: consumer có property "inputDir" với @InputDirectory.
consumer.inputDir.set(transform.flatMap { it.destinationDir })
```

`flatMap` từ `TaskProvider` tới `DirectoryProperty` giữ metadata producer; Gradle có thể suy ra dependency cần thiết khi consumer được chọn. Tên `consumer` ở đây là đối tượng/task consumer đã được định nghĩa trong build logic của dự án; **không phải đoạn code độc lập**. Với demo `listTransformedFiles`, chỉ dùng nó để hiểu `dependsOn`, không dùng làm mẫu configuration-cache task action.

**Lựa chọn:** nếu một consumer cần artifact output, ưu tiên input/output Provider; nếu cần thực hiện prerequisite có side effect không mô hình hóa bằng file, `dependsOn` tường minh vẫn có chỗ dùng.

## 14. Đo hiệu quả, test và debug

### 14.1. Bảng lệnh chẩn đoán

| Câu hỏi | Lệnh |
| --- | --- |
| Gradle dùng phiên bản nào? | `./gradlew --version` |
| Task có trong build không? | `./gradlew tasks --all` |
| Task lần hai có `UP-TO-DATE` không? | `./gradlew uppercaseIncremental --console=plain` |
| Vì sao task chạy lại? | `./gradlew uppercaseIncremental --info` |
| Muốn cố tình thử non-incremental? | `./gradlew uppercaseIncremental --rerun-tasks` |
| Có thể reuse configuration không? | Chạy hai lần `./gradlew uppercaseIncremental --configuration-cache` |
| Muốn xem dạng hiển thị task graph mà không chạy action? | `./gradlew uppercaseIncremental --dry-run` |

**Không trộn nhầm các công cụ:** `--dry-run` không thực thi action nên **không thể kiểm tra `InputChanges`**; `--rerun-tasks` làm non-incremental nên **không dùng để chứng minh phần xử lý từng file**; `--info` hữu ích để Gradle giải thích lý do không up-to-date.

### 14.2. Kịch bản kiểm thử tối thiểu cho task tăng dần

1. **Clean build:** tạo input file rồi chạy task lần đầu; `isIncremental=false`, tất cả đầu vào được xử lý.
2. **No change:** chạy lần hai; task được skip nếu metadata/output hợp lệ.
3. **Modify:** sửa một file trong nhiều file; chỉ output tương ứng đổi, output khác giữ nguyên.
4. **Add:** thêm source mới; có output mới mà không rebuild những output cũ.
5. **Remove:** xóa source; output tương ứng được xóa, không còn file stale.
6. **Rename:** đổi tên source; output cũ biến mất, output mới xuất hiện.
7. **Non-file property:** đổi `-Pprefix`; mọi source được tái xử lý (full).
8. **Output corruption:** sửa hoặc xóa output ngoài Gradle; chạy lại để xác nhận task rebuild, không giữ artifact sai.
9. **Different OS:** chạy cùng repo trên Windows/Linux/macOS để kiểm tra encoding, path, case sensitivity và permission.
10. **Cache compatibility:** bật `--configuration-cache` và kiểm tra task action không truy cập project state trái quy tắc; build cache là phép thử riêng.

Tập trung xác minh **nội dung output và tính đúng khi xóa file**, không chỉ dựa vào số dòng log. Sử dụng thư mục test riêng tránh làm hỏng nguồn sản xuất.

### 14.3. Khi muốn có unit/integration test thật

Đối với task reusable đóng gói thành **binary plugin** hoặc convention plugin, có thể viết test bằng **Gradle TestKit**: tạo project tạm, chạy task, sửa/đổi tên/xóa file, chạy lại, kiểm tra task outcome và nội dung file output sau mỗi lần. TestKit giúp bảo vệ behavior của task khi nâng Gradle/Java và bắt lỗi “stale outputs” mà demo chạy tay dễ bỏ qua.

Nếu logic xử lý mỗi file phức tạp, tách thuật toán ra khỏi Gradle API thành class thuần Java/Kotlin và unit test riêng; task `@TaskAction` chỉ điều phối InputChanges + file I/O. Việc này giữ mô hình build dễ đọc và tiết kiệm chi phí kiểm thử.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `getFileChanges` báo lỗi property không incremental | Thiếu `@Incremental`/`@SkipWhenEmpty` hoặc truyền không đúng property | Đánh dấu `@InputFiles`/`@InputDirectory` phù hợp, truyền đúng property |
| Task luôn `MODE=FULL` | Mỗi lần chạy đều thiếu lịch sử, đổi input giá trị, output bị sửa, `--rerun-tasks`, hoặc non-incremental input đổi | Dùng `--info` và kiểm tra output ownership, inputs, Gradle version |
| Task không chạy khi file không đổi | Gradle đã đánh dấu `UP-TO-DATE` | Đây là tối ưu đúng; không dùng task log làm điều kiện kiểm thử duy nhất |
| Đổi nội dung file mà task không chạy | File không được khai báo input, hoặc task snapshot/normalization sai | Dùng đúng `@InputDirectory`/`@InputFiles` và file property |
| Xóa input nhưng output vẫn tồn tại | Bỏ qua `ChangeType.REMOVED` | Dùng `normalizedPath` tìm và xóa output cũ |
| Task lỗi `FileNotFoundException` khi remove | Đọc `change.file` cho `REMOVED` | Không mở file đã xóa; chỉ dùng path của nó để xóa output |
| Đổi tên input làm tích lũy file cũ | Không xử lý cả remove/add | Kiểm tra mapping và output cleanup |
| Output bị mất của file không đổi | Task tự xóa cả outputDir trong lần incremental | Chỉ sửa/xóa output được `getFileChanges` báo; rebuild toàn bộ khi non-incremental |
| Hai input khác folder ghi chung một output | `PathSensitivity.NAME_ONLY` hoặc mapping không duy nhất | Dùng `RELATIVE`, xác định namespace cho từng root |
| Không thấy `MODIFIED` mà thấy remove/add | Dùng `PathSensitivity.NONE` hoặc path normalization khiến identity đổi | Đọc `getFileChanges` như change events, xử lý add/remove đúng |
| File rỗng/không có source | `@InputDirectory` trỏ directory thiếu, hoặc task không thiết kế nhánh no-source | Xác định required input, cân nhắc `@SkipWhenEmpty` và `NO-SOURCE` |
| Task hoạt động local nhưng CI khác | Đường dẫn tuyệt đối, default charset, locale, file path case, JDK/Gradle version khác | Dùng Gradle Wrapper, UTF-8, `Locale.ROOT`, relative paths, multi-OS CI |
| Task `UP-TO-DATE` dù flag ảnh hưởng output đổi | Flag chưa có `@Input` | Thêm typed Property + `@Input`, nối Provider từ `-P`/Gradle properties |
| Build cache tái sử dụng output không đúng | Input/output hoặc side effect chưa được mô tả đủ | Hoàn thiện task contract, kiểm tra cacheability trước khi bật `@CacheableTask` |
| Configuration cache lỗi | Task action truy cập `Project`/Gradle model hoặc dữ liệu ngoài contract | Chuyển sang typed task inputs/outputs, sửa theo configuration cache report |

## 16. Checklist nghiệm thu

- **Input file property** có `@InputFiles` hoặc `@InputDirectory`, thêm `@Incremental` hoặc `@SkipWhenEmpty` và path sensitivity phù hợp.
- **Output property** có `@OutputFile`/`@OutputDirectory`, task sở hữu riêng path đầu ra.
- **Non-file inputs** ảnh hưởng kết quả có `@Input`, không đọc ngầm trong action.
- **Action** nhận đúng một tham số `InputChanges` và dùng `getFileChanges` trên chính property đã khai báo.
- **`ADDED`/`MODIFIED`:** tạo hoặc cập nhật đúng output; **`REMOVED`:** xóa output stale mà không đọc file đã xóa.
- **`isIncremental=false`:** có thể rebuild toàn bộ, không giả định mọi thay đổi đều là từng file riêng lẻ.
- **Path mapping** deterministic, không collision, không hardcode absolute path.
- **Encoding/locale** không phụ thuộc máy; dùng Gradle Wrapper/JDK tương thích.
- **Không có side effect ẩn** như ghi ngoài output dir, sửa input, lấy network/random/secret không khai báo.
- **Test đầy đủ**: lần đầu, không đổi, sửa, thêm, xóa, đổi tên, đổi non-file input, hỏng output và build sạch trên CI.
- **Hiểu rõ các lớp cache**: `UP-TO-DATE`, incremental processing, build cache và configuration cache không giống nhau.

## 17. Ghi nhớ

- `InputChanges` tối ưu **bên trong một task đang được thực thi**, không thay thế up-to-date check.
- `@Incremental`/`@SkipWhenEmpty` đánh dấu **file input** cho phép xem sự kiện thay đổi qua `getFileChanges`.
- `isIncremental=true`: dùng danh sách `ADDED`/`MODIFIED`/`REMOVED` để cập nhật đúng phần output. `false`: xem mọi input file như `ADDED` để rebuild toàn bộ.
- `REMOVED` phải xóa output cũ; không đọc file đã bị xóa. Rename thường là remove + add.
- `@Input` giá trị và `@OutputDirectory` quyết định Gradle có thể phát hiện thay đổi đúng không.
- `@PathSensitive(RELATIVE)` giúp output mapping theo cấu trúc thư mục, nhưng vẫn cần tránh va chạm nếu nhiều nguồn.
- Cấu hình task bằng `tasks.register` và Provider; để action chỉ dùng typed task properties nhằm phù hợp configuration cache.
- Bắt đầu bằng tính **đúng**, đo performance rồi mới tối ưu incremental.

## Tài liệu chính thức

- [Gradle — Advanced Tasks: Incremental tasks](https://docs.gradle.org/current/userguide/custom_tasks.html#incremental_tasks): ví dụ `InputChanges`, `@Incremental`, nguyên nhân non-incremental, các kịch bản ADD/MODIFY/REMOVE.
- [Gradle — InputChanges API](https://docs.gradle.org/current/javadoc/org/gradle/work/InputChanges.html): hợp đồng `isIncremental` và `getFileChanges`.
- [Gradle — FileChange API](https://docs.gradle.org/current/javadoc/org/gradle/work/FileChange.html): `changeType`, `normalizedPath`, `fileType` và `file`.
- [Gradle — SkipWhenEmpty API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/SkipWhenEmpty.html): `NO-SOURCE`, điều kiện sử dụng và tính incremental ngầm định.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): task inputs/outputs và custom task design.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_builds.html): đầu vào, đầu ra, path normalization, up-to-date.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): cache task outputs và cacheability.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): cache của configuration/task graph và các giới hạn đối với task action.
