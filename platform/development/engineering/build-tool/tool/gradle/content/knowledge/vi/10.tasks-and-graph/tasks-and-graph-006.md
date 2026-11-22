# Dependency ngầm qua đầu vào, đầu ra và Provider của task trong Gradle

## 1. Bài toán và mục tiêu

Trong Gradle, một task có thể **tạo file**, còn task khác **đọc file vừa được tạo**. Ví dụ: `generateGreeting` ghi `build/generated/greeting.txt`, sau đó `consumeGreeting` đọc nội dung. Đây là quan hệ dữ liệu *producer → consumer*. Nếu chạy consumer trước khi producer tạo file, build có thể lỗi; nếu chỉ vô tình chạy đúng thứ tự ở máy phát triển, CI hoặc chế độ parallel có thể bộc lộ lỗi.

Gradle hỗ trợ **task dependency ngầm (implicit/inferred task dependency)**: khi thuộc tính đầu vào của consumer được nối trực tiếp đến **thuộc tính đầu ra của producer còn giữ thông tin về task nguồn**, Gradle tự thêm cạnh vào đồ thị task. Bạn không phải gõ `dependsOn` bằng tay cho quan hệ dữ liệu này.

Sau bài học, bạn sẽ:

1. Phân biệt **dependency giữa các task** với dependency thư viện và với việc chỉ sắp xếp thứ tự.
2. Khai báo `@Input`, `@InputFile`, `@OutputFile` và dùng `RegularFileProperty` để mô hình hóa dữ liệu.
3. Nối `TaskProvider` của producer với input của consumer bằng `flatMap` mà không gọi `get()` sớm.
4. Dùng `map` để biến đổi đầu ra thành dữ liệu đầu vào khác trong khi giữ nguồn gốc task.
5. Giải thích vì sao một path trùng tên file output, một `File` thô hay `providers.provider { ... }` không tự tạo dependency.
6. Quan sát đồ thị bằng `--dry-run`, kiểm tra chạy thực tế và phân biệt `UP-TO-DATE` với việc task không thuộc đồ thị.

**Phạm vi:** ví dụ chính dùng **Gradle Groovy DSL** trong `build.gradle`, task API hiện đại và Gradle Wrapper. Cú pháp `build.gradle.kts` (Kotlin DSL) khác. Bài không nói về khai báo thư viện trong `dependencies { implementation '...' }`: đó là một loại quan hệ khác.

## 2. Task dependency ngầm là gì?

Giả sử có hai task:

- **Producer:** `generateGreeting` ghi một file có thể thay đổi theo cấu hình.
- **Consumer:** `consumeGreeting` đọc file đó và in nội dung.

Quan hệ mong muốn:

```text
generateGreeting (@OutputFile)
         |
         | outputFile: RegularFileProperty
         v
producer.flatMap { it.outputFile }: Provider<RegularFile>
         |
         | inputFile.set(...)
         v
consumeGreeting (@InputFile)
```

Khi yêu cầu chạy `consumeGreeting`, Gradle có đủ thông tin để lập đồ thị:

```text
:generateGreeting  ──dữ liệu đầu ra──>  :consumeGreeting
       chạy trước                       chạy sau
```

Task dependency **không đồng nghĩa “task producer sẽ chạy action mỗi lần”**. Nó có nghĩa producer thuộc đồ thị và Gradle đảm bảo tác vụ phụ thuộc được xử lý theo thứ tự phù hợp. Nếu đầu vào/đầu ra không đổi và producer được xác nhận `UP-TO-DATE` (hoặc kết quả lấy từ cache khi đủ điều kiện), action của producer có thể được bỏ qua trong lần build đó. Consumer vẫn có dữ liệu đầu vào để dùng.

Đây là một phần trong mô hình dữ liệu của Gradle: input/output annotations giúp **kiểm tra thay đổi** (*up-to-date checking*), còn thông tin task nguồn đi theo Provider giúp **xác lập quan hệ producer–consumer**. Cần cả hai mặt; chỉ ghi cùng đường dẫn file không đảm bảo Gradle biết file đó do task nào tạo.

## 3. Phân biệt các quan hệ trong đồ thị task

| Cơ chế | Gradle làm gì? | Có tự đưa task khác vào đồ thị? | Khi nên dùng |
| --- | --- | --- | --- |
| **Implicit dependency qua Provider output → input** | Suy ra task nguồn cần hoàn tất trước khi consumer đọc kết quả. | **Có**, dựa trên nguồn gốc của Provider/file collection. | Một task thật sự tiêu thụ output của task khác. |
| `dependsOn(taskProvider)` | Khai báo dependency task bằng tên/đối tượng. | **Có**. | Điều phối khi cần thực hiện task tiên quyết mà không có liên kết dữ liệu rõ ràng; thường dùng cho lifecycle/aggregate task. |
| `mustRunAfter(taskProvider)` | Bắt buộc thứ tự **nếu cả hai** đã thuộc đồ thị. | **Không**. | Hai task phải tránh chạy sai thứ tự nhưng task sau không nhất thiết cần task trước. |
| `shouldRunAfter(taskProvider)` | Gợi ý thứ tự mềm; Gradle có thể bỏ qua nếu cần. | **Không**. | Thứ tự ưu tiên, không phải ràng buộc dữ liệu. |
| `finalizedBy(taskProvider)` | Sắp xếp một finalizer chạy sau task được finalize trong những điều kiện Gradle quy định. | Được dùng cho cleanup/finalization. | Không thay thế quan hệ file input/output. |

Ví dụ nếu `verifyAll` là task tổng hợp chỉ gom các bước, `dependsOn('test', 'check')` có thể hợp lý. Nếu `consumer` **đọc outputFile** của `producer`, ưu tiên nối chính output đó vào input. Việc chỉ `dependsOn(producer)` đảm bảo thứ tự nhưng không nói cho Gradle consumer thực sự cần **file nào**.

**Không nhầm “dependency ngầm” với thứ tự task hiển thị ngẫu nhiên trong log.** Đồ thị phải được khai báo/suy ra từ dữ liệu, không được dựa vào thứ tự đăng ký task hoặc thứ tự viết code trong `build.gradle`.

## 4. Ba thành phần cốt lõi: output, Provider, input

### 4.1. Producer công bố output bằng annotation và property đúng kiểu

Task tự tạo file nên khai báo thuộc tính đầu ra trực tiếp:

```groovy
abstract class GenerateGreeting extends DefaultTask {
    @Input
    abstract Property<String> getMessageText()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        File file = outputFile.get().asFile
        file.parentFile.mkdirs()
        file.setText(messageText.get() + '\n', 'UTF-8')
    }
}
```

Giải thích:

- `@Input` trên `Property<String>` cho Gradle biết text là dữ liệu đầu vào của task.
- `@OutputFile` trên **abstract getter** `RegularFileProperty` mô tả file được tạo ra, cho Gradle nhận diện output thuộc về producer.
- `@TaskAction` là thân công việc thực thi; `outputFile.get()` và `messageText.get()` được gọi **trong task action**, không lấy giá trị quá sớm khi cấu hình.
- Đặt file bên dưới `layout.buildDirectory` để vị trí output thuộc thư mục build do Gradle quản lý. Việc tạo thư mục cha bằng `mkdirs()` có chủ đích và được thực hiện lúc action chạy.

**Chú ý:** `@OutputFile` phải đặt trên getter property Gradle có thể theo dõi. Một getter chỉ tự trả về `Provider<RegularFile>` được tạo từ `map` mà không có output property trực tiếp có thể làm mất dependency metadata trong một số trường hợp; cách đơn giản và đáng tin là **abstract `RegularFileProperty` được annotate trực tiếp**.

### 4.2. Consumer công bố input bằng annotation và property đúng kiểu

```groovy
abstract class ConsumeGreeting extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.NONE)
    abstract RegularFileProperty getInputFile()

    @TaskAction
    void consume() {
        String text = inputFile.get().asFile.getText('UTF-8').trim()
        logger.quiet("consumer: ${text}")
    }
}
```

- `@InputFile` nói rằng task cần một **file tồn tại** khi chạy, Gradle có thể theo dõi nội dung file để đánh giá input thay đổi.
- `@PathSensitive(PathSensitivity.NONE)` cho phép coi trọng nội dung hơn đường dẫn tuyệt đối trong quyết định up-to-date; thích hợp khi tên/vị trí file không làm thay đổi ý nghĩa của đầu vào. Nếu tên/đường dẫn tương đối có ý nghĩa, chọn mức `RELATIVE` hoặc chính sách phù hợp.
- `inputFile.get()` được gọi trong `@TaskAction` sau khi Gradle đã xử lý các dependency trong đồ thị; đây là thời điểm phù hợp để đọc file.
- Chỉ có annotation `@InputFile` **chưa đủ** để suy ra producer. Consumer phải nhận một giá trị còn giữ nguồn gốc của producer.

Với nhiều file có thể sử dụng `@InputFiles`/`ConfigurableFileCollection`, với thư mục dùng `@InputDirectory`/`DirectoryProperty`. Đối với Java classpath, các annotation `@Classpath`, `@CompileClasspath` thể hiện thêm ngữ nghĩa về nội dung classpath.

### 4.3. TaskProvider và flatMap giữ quan hệ nguồn gốc

`tasks.register('generateGreeting', GenerateGreeting)` trả về `TaskProvider<GenerateGreeting>`, một tham chiếu để cấu hình/lấy task một cách lazy. Không cần gọi `producer.get()` để lấy instance task khi nối dữ liệu.

Cú pháp đúng:

```groovy
def producer = tasks.register('generateGreeting', GenerateGreeting) {
    messageText.set('Hello from Gradle')
    outputFile.set(layout.buildDirectory.file('generated/greeting.txt'))
}

tasks.register('consumeGreeting', ConsumeGreeting) {
    inputFile.set(producer.flatMap { it.outputFile })
}
```

Cách đọc dòng quan trọng nhất:

1. `producer` là `TaskProvider` của task tạo file.
2. `producer.flatMap { it.outputFile }` lấy **Provider của output** từ task mà vẫn giữ được provenance (*thông tin file do task nào tạo*).
3. `inputFile.set(...)` nối `Provider<RegularFile>` đó với input của consumer.
4. Gradle tự suy ra cạnh `generateGreeting → consumeGreeting`; không cần thêm `dependsOn` cho quan hệ dữ liệu này.

**Phân biệt `map` và `flatMap`:** khi callback trả về một **Provider**, dùng `flatMap` để tránh tạo Provider lồng nhau. Nếu callback trả về một **giá trị thường** (ví dụ `String`, `File` từ một output getter cũ), dùng `map`. Khi nối output kiểu `RegularFileProperty` của Gradle, `flatMap { it.outputFile }` là lựa chọn đúng.

## 5. Ví dụ thực hành hoàn chỉnh: chạy consumer, Gradle tự chạy producer

Tạo một dự án Gradle thực hành riêng có `gradlew`, `gradlew.bat` và file `settings.gradle`. Thay nội dung **`build.gradle`** bằng mã dưới đây. Đây là **một file Groovy DSL độc lập**, không cần thư viện bên thứ ba:

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

abstract class GenerateGreeting extends DefaultTask {
    @Input
    abstract Property<String> getMessageText()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        File target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.setText(messageText.get() + '\n', 'UTF-8')
        logger.quiet('producer: wrote greeting.txt')
    }
}

abstract class ConsumeGreeting extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.NONE)
    abstract RegularFileProperty getInputFile()

    @TaskAction
    void consume() {
        String value = inputFile.get().asFile.getText('UTF-8').trim()
        logger.quiet("consumer: ${value}")
    }
}

def producer = tasks.register('generateGreeting', GenerateGreeting) {
    messageText.set('Hello from Gradle')
    outputFile.set(layout.buildDirectory.file('generated/greeting.txt'))
}

tasks.register('consumeGreeting', ConsumeGreeting) {
    inputFile.set(producer.flatMap { it.outputFile })
}
```

**Không có `dependsOn` trong ví dụ.** Đồ thị được suy ra từ output `@OutputFile` của producer được nối vào input `@InputFile` của consumer.

### 5.1. Xem đồ thị trước khi chạy bằng --dry-run

Linux/macOS:

```bash
./gradlew consumeGreeting --dry-run --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat consumeGreeting --dry-run --console=plain
```

Trong kết quả `--dry-run`, bạn sẽ thấy hai task theo đúng thứ tự, thường tương tự:

```text
:generateGreeting SKIPPED
:consumeGreeting SKIPPED
```

**`SKIPPED` ở đây là do chế độ dry-run**, không có file được tạo hoặc đọc. Những dòng thông tin khác (daemon, task summary...) phụ thuộc bản Gradle; hai dòng trên chỉ minh họa phần liên quan đến đồ thị. `--dry-run` giúp xác nhận task nào sẽ được đưa vào graph; không chứng minh action đã chạy.

### 5.2. Chạy thật trên thư mục build sạch

Linux/macOS:

```bash
./gradlew -q consumeGreeting --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat -q consumeGreeting --console=plain
```

Với project thực hành mới chưa có output và cấu hình đúng, **các dòng do task tự in** sẽ là:

```text
producer: wrote greeting.txt
consumer: Hello from Gradle
```

Task tạo file chạy trước, consumer đọc file sau. Nội dung file `build/generated/greeting.txt` là `Hello from Gradle` kèm xuống dòng. Khi chạy lại cùng cấu hình, `generateGreeting` có thể được đánh dấu `UP-TO-DATE` và **không in dòng producer**; `consumeGreeting` vẫn thực thi vì nó không khai báo output. Do đó **không dùng số dòng logger để suy đoán producer có trong đồ thị hay không**.

Để quan sát trạng thái task ở lần chạy thứ hai, bỏ `-q`:

```bash
./gradlew consumeGreeting --console=plain
```

Gradle có thể cho thấy `:generateGreeting UP-TO-DATE`, còn consumer chạy và in thông điệp. Đây là up-to-date checking, không có nghĩa Gradle đã bỏ quan hệ dependency.

### 5.3. Thay đổi giá trị đầu vào của producer

Trong block `generateGreeting`, đổi:

```groovy
messageText.set('Hello from Gradle')
```

thành:

```groovy
messageText.set('Hello again')
```

Sau đó chạy lại `./gradlew -q consumeGreeting --console=plain`. Dự kiến producer phải tạo lại file và consumer in `consumer: Hello again`. Nhờ `@Input` và `@OutputFile`, Gradle nhận biết sự thay đổi ảnh hưởng đến output; nhờ Provider nối với input, consumer nhận đúng file sau khi nó được tạo.

## 6. map, flatMap và Provider: giữ lazy wiring

### 6.1. flatMap cho output property thuộc task

Đây là pattern thường được khuyến nghị:

```groovy
def generated = tasks.named('generateGreeting', GenerateGreeting)
def generatedFile = generated.flatMap { it.outputFile }
// generatedFile: Provider<RegularFile>

tasks.named('consumeGreeting', ConsumeGreeting) {
    inputFile.set(generatedFile)
}
```

Đoạn này là **minh họa thay thế phần wiring trong ví dụ chính**; không dán thêm một block cùng tên nếu đang dùng nguyên file mục 5. Nó giữ kết nối task nguồn mà không lấy file ra sớm.

### 6.2. map cho phép chuyển output thành giá trị khác

Không phải consumer nào cũng cần kiểu `RegularFileProperty`. Một task có thể cần nội dung text làm `@Input Property<String>`:

```groovy
abstract class PrintGreetingText extends DefaultTask {
    @Input
    abstract Property<String> getTextInput()

    @TaskAction
    void printText() {
        logger.quiet("text: ${textInput.get()}")
    }
}

tasks.register('printGreetingText', PrintGreetingText) {
    textInput.set(
        producer.flatMap { it.outputFile }
                .map { file -> file.asFile.getText('UTF-8').trim() }
    )
}
```

Đoạn này có thể **thêm vào cuối** file ví dụ mục 5. Khi chạy `printGreetingText`, Gradle cũng biết phải xử lý `generateGreeting` trước. Kết quả task tự in lần đầu là `text: Hello from Gradle`. Cách này có hai bước:

- `flatMap` lấy output file Provider **có nguồn gốc producer**.
- `map` chuyển `RegularFile` thành `String` bằng việc đọc file **khi giá trị được yêu cầu**, bảo toàn đường nối Provider.

Khi làm việc với output file, chỉ dùng `map { it.asFile.text }` **sau** output-provider chain, không gọi `producer.get().outputFile.get()` rồi đọc file ở pha cấu hình. Nếu các value phụ thuộc vào file do task tạo, việc đọc trước khi producer chạy sẽ sai thời điểm.

### 6.3. Provider tự tạo không tương đương task output Provider

Ví dụ sau **không** cung cấp thông tin nguồn gốc task:

```groovy
def rawFileProvider = providers.provider {
    layout.buildDirectory.file('generated/greeting.txt').get()
}
```

`providers.provider { ... }` là nguồn giá trị tự tạo; bản thân nó không mang quan hệ `generateGreeting`, dù đường dẫn bên trong có tình cờ chỉ đúng file đó. Tương tự, `layout.buildDirectory.file('generated/greeting.txt')` là Provider của **vị trí file**, nhưng không tự nói rằng output thuộc task nào. Chỉ nối đường dẫn mà không gắn output task sẽ mất liên kết quan trọng.

## 7. Vì sao chỉ dùng raw File hoặc trùng đường dẫn không đủ?

### 7.1. Ví dụ sai: input trỏ thẳng vào đường dẫn output

Giả sử cùng một file ví dụ ở mục 5, bạn thay wiring bằng:

```groovy
// PHẢN VÍ DỤ - không chạy như một thiết kế hợp lệ:
tasks.register('brokenConsumer', ConsumeGreeting) {
    inputFile.set(layout.buildDirectory.file('generated/greeting.txt'))
}
```

`brokenConsumer` có `@InputFile` và chỉ vào cùng file output của `generateGreeting`. Nhưng Provider này do **layout** tạo, không được lấy từ `@OutputFile` của producer. Gradle **không tự suy ra cạnh task chỉ bằng việc so trùng path**. Nếu file chưa có, có thể lỗi input không tồn tại; nếu file có sẵn, consumer có thể đọc dữ liệu cũ; Gradle cũng có thể phát hiện và báo vấn đề **implicit dependency** khi thấy file thuộc output của task khác nhưng không có dependency thực sự.

**Đừng “sửa” bằng cách tạo file tay cho đủ tồn tại.** Sửa đúng là:

```groovy
inputFile.set(producer.flatMap { it.outputFile })
```

Lúc này đường dẫn và nguồn gốc producer cùng được giữ lại.

### 7.2. Ví dụ sai: lấy File quá sớm

```groovy
// PHẢN VÍ DỤ - mất lazy wiring và có thể đọc trước khi file tồn tại:
def path = producer.get().outputFile.get().asFile
tasks.register('brokenConsumer', ConsumeGreeting) {
    inputFile.set(path)
}
```

`producer.get()` buộc hiện thực hóa task; `outputFile.get()` lấy giá trị; `asFile` là File thô, **không mang thông tin task sinh ra file**. Ngay cả khi gọi thành công, việc nối File đã tách khỏi Provider nguồn không bảo đảm task dependency. Nếu dùng `path.text` ở đây, có thể đọc trước khi file tồn tại. Nên nối lazily như mục 4/5.

### 7.3. Ví dụ sai: bọc lại file bằng provider không liên quan

```groovy
// PHẢN VÍ DỤ - provider mới không gắn với producer:
def disconnected = providers.provider {
    new File(layout.buildDirectory.get().asFile, 'generated/greeting.txt')
}
tasks.register('brokenConsumer', ConsumeGreeting) {
    inputFile.set(disconnected)
}
```

Provider tự tạo không mặc nhiên giữ dependency của task khác. Trong môi trường sử dụng configuration cache, việc capture `TaskProvider`, `Project` hoặc task khác bên trong `doLast` cũng có thể vi phạm quy tắc serialization và khiến build không tương thích configuration cache.

**Trường hợp ngoại lệ có chủ đích:** một số API file collection của Gradle như `files(task)` hoặc `Copy.from(task)` có thể hiểu **các output được khai báo của task** và mang theo dependency. Đó là cơ chế đặc biệt được API hỗ trợ, không có nghĩa mọi `File` hoặc path trùng tên đều mang task dependency. Khi dùng `Copy` và chỉ cần một file, vẫn nên tham chiếu trực tiếp output Provider đó.

## 8. Task có sẵn: nối output vào Copy/Sync và Archive

Đối với task Gradle có sẵn, không cần viết task class mới nếu API đã hỗ trợ Provider file notation.

**Ví dụ mở rộng** sau có thể thêm vào cuối `build.gradle` mục 5:

```groovy
tasks.register('copyGreeting', Copy) {
    from(producer.flatMap { it.outputFile })
    into(layout.buildDirectory.dir('copied'))
}
```

Chạy:

```bash
./gradlew copyGreeting --console=plain
```

Gradle sẽ xử lý `generateGreeting` trước `copyGreeting` vì source của `Copy` là Provider lấy từ output của producer. File kết quả là `build/copied/greeting.txt`.

Ví dụ với plugin Java đã tạo task `jar` (đoạn riêng, cần `plugins { id 'java' }`):

```groovy
tasks.register('copyJar', Copy) {
    from(tasks.named('jar', Jar).flatMap { it.archiveFile })
    into(layout.buildDirectory.dir('deliverables'))
}
```

`jar.archiveFile` là Provider output archive của task Jar. Không nên thay bằng một đường dẫn đoán sẵn như `file('build/libs/app.jar')`, vì tên JAR có thể thay theo version, classifier và cấu hình plugin, đồng thời đường dẫn đoán không liên kết tới task tạo JAR.

Các configuration chứa artifacts từ project dependency cũng có thể mang build dependencies qua `FileCollection` khi truyền cho task/file APIs đúng cách; nếu ép configuration thành danh sách raw files quá sớm bằng `resolve()` thì có thể mất quan hệ task nguồn. Đây là lý do Gradle khuyến nghị truyền file collection/Provider trực tiếp vào task input.

## 9. Input/output, đồ thị task, up-to-date và build cache

Ba khái niệm hỗ trợ nhau nhưng **không đồng nhất**:

1. **Task graph:** Gradle xác định các task cần thực hiện trước và sau nhau. Provider output → input có thể thêm cạnh ngầm.
2. **Up-to-date checking:** Gradle so sánh input/output và lịch sử thực thi để quyết định action của task cần chạy lại không. `@Input`, `@InputFile`, `@OutputFile` cung cấp metadata cho việc này.
3. **Build cache:** chỉ lưu/tái sử dụng output của task khi tác vụ đủ điều kiện cache và có cấu hình thích hợp; **không phải cứ có `@OutputFile` là task tự động được remote/build cache phục vụ**.

Ví dụ:

- **Lần đầu:** `generateGreeting` tạo file, sau đó `consumeGreeting` đọc.
- **Lần hai, input không đổi:** producer vẫn là dependency nhưng có thể `UP-TO-DATE`; consumer trong ví dụ không có output nên vẫn chạy.
- **Đổi `messageText`:** producer cần cập nhật output; consumer phải đọc file mới.
- **Xóa file output rồi chạy consumer:** producer được yêu cầu tạo lại output.
- **Chạy `--dry-run`:** task action không chạy nên không thể dùng trạng thái đó làm bằng chứng file có nội dung mới.

**Không tự đặt hai task ghi cùng output path.** Đầu ra của các task nên độc lập, rõ owner. Output chồng lấn làm up-to-date, cache và implicit dependency trở nên khó tin cậy; Gradle có thể báo validation problems hoặc vô hiệu hóa một số tối ưu.

### 9.1. Đồ thị hợp lệ chưa chắc output hợp lệ

Một producer có thể chạy đúng thứ tự nhưng không ghi file đúng nơi đã khai báo. Khi đó consumer `@InputFile` có thể báo không tồn tại; việc gắn `dependsOn` không chữa được lỗi khai báo output sai. Đảm bảo `@TaskAction` ghi đúng file được `outputFile.get().asFile` trả về và cập nhật mỗi khi đầu vào ảnh hưởng đến nội dung thay đổi.

`@InputFile` mặc định đòi file tồn tại. Nếu file thực sự optional, phải thiết kế kiểu và cách skip/empty cho phù hợp, không im lặng bỏ qua exception để build có vẻ thành công.

## 10. Lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân cốt lõi | Sửa đúng |
| --- | --- | --- |
| Consumer báo file đầu vào không tồn tại | Chỉ khai báo path; producer chưa nằm trong task graph. | Nối input từ `producer.flatMap { it.outputFile }`. |
| Build chỉ thành công khi gọi `generateGreeting consumeGreeting` theo thứ tự thủ công | Consumer không có dependency metadata. | Dùng output Provider, chỉ gọi `consumeGreeting` cũng phải chạy đúng. |
| Gradle báo “implicit dependencies between tasks” | Một task tiêu thụ output của task khác không có dependency được khai báo/suy ra. | Dùng annotated task output + Provider; có thể bổ sung task dependency tường minh khi API legacy không hỗ trợ wiring. |
| `@InputFile` đã thêm nhưng Gradle vẫn không tự chạy producer | Annotation nói rằng input là file, chưa cho biết *ai* tạo file. | Đổi từ raw File/path sang Provider output có nguồn gốc task. |
| Gọi `producer.get()` rồi lấy `File` ngay ở configuration | Realize task/resolve giá trị sớm, mất lazy và có thể mất nguồn gốc. | Nối trực tiếp `TaskProvider.flatMap`. |
| Dùng `providers.provider { file(...) }` và nghĩ có task dependency | Provider mới độc lập không biết producer. | Lấy từ property `@OutputFile` thực sự. |
| Dùng `flatMap` với getter trả `File` | Callback `flatMap` phải trả Provider. | Với getter trả plain File, dùng `TaskProvider.map { it.file }` hoặc hiện đại hoá output thành RegularFileProperty. |
| Producer chỉ có getter `Provider<RegularFile>` tính toán qua `map` | Gradle có thể không gắn origin task với output derived. | Ưu tiên direct annotated abstract `RegularFileProperty`. |
| Bật `mustRunAfter` mà producer không chạy | Ordering rule không thêm task vào đồ thị. | Cần task dependency thực hoặc wiring output → input. |
| Thêm `dependsOn` nhưng consumer vẫn đọc file cũ | Không gắn input vào đúng property/file output, hoặc producer ghi file khác. | Kiểm tra path và typed property của cả hai task. |
| Cả hai task chạy nhưng output sai trong chế độ parallel | Cạnh phụ thuộc bị thiếu hoặc hai task ghi chồng output. | Chỉ rõ mỗi output owner, nối Provider gốc. |
| Viết logic đọc task khác trong `doLast` bị lỗi configuration cache | Task action capture task/project khác và không có input typed. | Đưa dữ liệu vào `@InputFile`/`Property`, nối lazily ở configuration. |

## 11. Cách kiểm tra và debug mối quan hệ dependency ngầm

### 11.1. Xem task graph

```bash
./gradlew consumeGreeting --dry-run --console=plain
```

Kiểm tra có `generateGreeting` đứng trước `consumeGreeting`. Nếu không có producer, xem lại cách nối `inputFile` và output property, không chỉ nhìn đường dẫn file. `--dry-run` không xác minh output vì các action bị bỏ qua.

### 11.2. Chạy lần đầu và lặp lại

```bash
./gradlew consumeGreeting --console=plain
./gradlew consumeGreeting --console=plain
```

Lần đầu task producer cần tạo file. Lần thứ hai producer có thể up-to-date. Nếu thấy `generateGreeting UP-TO-DATE`, đó vẫn là một node trong graph. Dùng `--info` khi cần lý do up-to-date hoặc task execution chi tiết hơn:

```bash
./gradlew consumeGreeting --info --console=plain
```

### 11.3. Thay input và theo dõi

Đổi `messageText` của producer; chạy consumer lại. File phải được tạo lại và consumer đọc nội dung mới. Nếu không đổi, kiểm tra rằng mọi dữ liệu ảnh hưởng đến output đều được đánh dấu `@Input` hoặc loại input thích hợp và action ghi đúng `@OutputFile`.

### 11.4. Khi graph có vòng lặp

Nếu `A` lấy output của `B`, đồng thời `B` lấy output của `A`, Gradle sẽ nhận một **circular task dependency**. Không thể chữa bằng `mustRunAfter` hoặc đổi thứ tự đăng ký task. Cần thiết kế lại dữ liệu: tách output độc lập, phân giai đoạn hoặc bỏ quan hệ vòng tròn không cần thiết.

## 12. Bài tập tự kiểm tra

**Bài 1 — Dự đoán graph:** Trong mục 5, chỉ gọi `./gradlew consumeGreeting --dry-run`. Có cần gõ `generateGreeting` vào command line không? Vì sao?

**Bài 2 — Anti-pattern:** Thay `inputFile.set(producer.flatMap { it.outputFile })` bằng `inputFile.set(layout.buildDirectory.file('generated/greeting.txt'))`. Dự đoán điều gì có thể xảy ra trên máy mới chưa có file và vì sao path giống nhau không đủ.

**Bài 3 — Rebuild:** Lần đầu chạy consumer, lần hai chạy lại không sửa code, lần ba đổi `messageText`. Dự đoán khi nào producer cần chạy action và khi nào có thể `UP-TO-DATE`. Phân biệt action bị skip với node không có trong graph.

**Bài 4 — map/flatMap:** Điền vào chỗ trống để nối đúng output property:

```groovy
def producer = tasks.named('generateGreeting', GenerateGreeting)
def fileProvider = producer.________ { it.outputFile }
tasks.named('consumeGreeting', ConsumeGreeting) {
    inputFile.set(fileProvider)
}
```

Đáp án: `flatMap`, vì `outputFile` là một `RegularFileProperty` (Provider).

**Bài 5 — Mở rộng:** Thêm `copyGreeting` ở mục 8 rồi chỉ chạy task copy. Xác nhận Gradle tự đưa `generateGreeting` vào graph và tạo file trong `build/copied`.

**Bài 6 — Thiết kế:** Một task sinh JSON và một task upload JSON. Hãy định nghĩa `@OutputFile RegularFileProperty` ở producer, `@InputFile RegularFileProperty` ở consumer và nối bằng Provider. Nếu upload cần secret, yêu cầu secret tại task upload mà không làm task chỉ sinh JSON thất bại khi secret chưa có.

### Câu hỏi nhanh

1. **`@InputFile` có tự suy ra task tạo ra file từ tên path?** Không; cần thông tin origin từ output Provider/file collection hoặc khai báo dependency khác phù hợp.
2. **`mustRunAfter` có tự thêm producer vào graph?** Không.
3. **`dependsOn` có thay metadata của input/output không?** Không; nó chủ yếu xác lập một quan hệ task.
4. **Khi output property là `RegularFileProperty`, nên dùng `map` hay `flatMap` từ TaskProvider?** Thường `flatMap`; `map` để biến đổi giá trị thông thường ở bước sau.
5. **Tại sao không gọi `get()` trên Provider lúc cấu hình?** Có thể đọc quá sớm, realize task và làm mất tính lazy/nguồn gốc task.
6. **Producer `UP-TO-DATE` có nghĩa consumer không phụ thuộc vào producer?** Không; producer vẫn có thể thuộc graph nhưng action được bỏ qua.
7. **Một task có output có tự trở thành build-cacheable không?** Không nhất thiết; cần đủ điều kiện và khai báo/chính sách cache phù hợp.

## 13. Tài liệu chính thức

- **Gradle — Configuring Tasks Lazily**, phần *Working with task inputs and outputs*, implicit dependencies, `TaskProvider`/`flatMap`: https://docs.gradle.org/current/userguide/lazy_configuration.html
- **Gradle — Best Practices for Tasks**, đặc biệt *Avoid DependsOn*, *Wire lazy task outputs using map and flatMap*: https://docs.gradle.org/current/userguide/best_practices_tasks.html
- **Gradle — Implementing Custom Tasks**, annotated inputs/outputs, up-to-date checking: https://docs.gradle.org/current/userguide/implementing_custom_tasks.html
- **Gradle — Configuration Cache Requirements**, nối task input/output thay vì đọc task khác trong action: https://docs.gradle.org/current/userguide/configuration_cache_requirements.html
- **Gradle — Incremental Build**, validation và up-to-date checking: https://docs.gradle.org/current/userguide/incremental_build.html
- **Gradle — Task Validation Problems**, *Implicit dependencies between tasks*: https://docs.gradle.org/current/userguide/validation_problems.html
- **Gradle — Controlling Task Execution**, phân biệt dependency và ordering: https://docs.gradle.org/current/userguide/controlling_task_execution.html

**Kết luận kiến thức:** Dependency ngầm xuất hiện khi Gradle **biết output đến từ task nào** và consumer **nhận đúng Provider/file collection còn giữ quan hệ đó**. Khai báo output/input bằng các typed property, nối `TaskProvider.flatMap` và để Gradle xây task graph; đừng dựa vào một đường dẫn `File` trùng nhau hoặc thứ tự viết script.