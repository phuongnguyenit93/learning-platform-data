# Khai báo đầu ra bằng @OutputFile, @OutputFiles và @OutputDirectory

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Task tùy chỉnh

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao custom task phải khai báo **đầu ra (outputs)** chứ không chỉ viết file trong @TaskAction.
2. Phân biệt chính xác **@OutputFile** cho một file, **@OutputFiles** cho một tập file, và **@OutputDirectory** cho một thư mục đầu ra.
3. Chọn đúng **RegularFileProperty**, **ConfigurableFileCollection** và **DirectoryProperty**, đồng thời biết vị trí đặt annotation trên getter của task type.
4. Hiểu Gradle dùng **inputs + outputs** để quyết định UP-TO-DATE, kiểm tra output, nhận biết xung đột và liên kết dependency giữa các task.
5. Viết và chạy custom task Groovy DSL trên một dự án Java 17: sinh một file, nhiều file được khai báo trước, một cây thư mục và một consumer task.
6. Xử lý lỗi thường gặp: ghi sai vị trí, output trùng nhau, khai báo thiếu input, dùng FileTree cho @OutputFiles, nghĩ @Output... tự bật build cache, hoặc đọc đầu ra trước khi producer chạy.

**Thông điệp chính:** Annotation mô tả **hợp đồng đầu ra** của task. Gradle biết *task nào sở hữu output nào*, nhưng chỉ khi bạn khai báo đúng. Task code vẫn phải thực sự tạo nội dung; annotation không tự sinh dữ liệu.

## 1. Đầu ra của task là gì?

Một custom task thường biến dữ liệu đầu vào thành một hoặc nhiều kết quả trên đĩa:

~~~text
              Inputs                          Outputs
   Property<String> title       +-----> build/generated/one/report.txt
   InputFile template ----------|-----> build/generated/many/a.txt
   Tool settings ---------------|-----> build/generated/many/b.txt
                                +-----> build/generated/site/
                                            index.txt
                                            assets/info.txt
~~~

Ví dụ task sinh báo cáo có đầu vào title. Nếu title không đổi và file báo cáo vẫn còn nguyên, Gradle có thể **bỏ qua** việc chạy lại task. Nếu title thay đổi hoặc file output bị xóa/chỉnh sửa, Gradle có lý do để thực thi lại.

Vì vậy, task tốt cần mô tả hai phía:

- **Đầu vào (inputs):** những giá trị/file thực sự quyết định output. Ví dụ @Input cho tiêu đề hoặc @InputFile cho template.
- **Đầu ra (outputs):** các file/thư mục task thực sự tạo và quản lý. Ví dụ @OutputFile cho báo cáo duy nhất.

Không khai báo output thì Gradle thiếu dữ liệu để thực hiện cơ chế UP-TO-DATE chuẩn cho task. Khai báo output sai hoặc không đầy đủ có thể làm task chạy lại không cần thiết, hoặc tệ hơn là bị bỏ qua khi nội dung đáng ra phải thay đổi.

### 1.1. Các loại annotation chính

| Annotation | Ý nghĩa | Kiểu thuộc tính hiện đại nên dùng | Khi nào chọn? |
|---|---|---|---|
| **@OutputFile** | Một file kết quả | RegularFileProperty | Sinh một báo cáo, manifest, JSON, text, file ZIP... |
| **@OutputFiles** | Một hoặc nhiều file đầu ra riêng lẻ | ConfigurableFileCollection | Danh sách file có thể xác định trước khi task thực thi |
| **@OutputDirectory** | Một thư mục, bao gồm những file/thư mục con task quản lý | DirectoryProperty | Sinh một cây file, website, bộ class/resources đã chuyển đổi |
| **@OutputDirectories** | Nhiều thư mục đầu ra | ConfigurableFileCollection | Ít gặp hơn, khi task thực sự sở hữu nhiều thư mục phân biệt |

**Không nhầm @OutputFiles với @OutputDirectory:** Ba file có thể được mô tả là một collection file nếu danh sách đã biết. Ngược lại, nếu task tạo số lượng/tên file bên trong một cây thư mục và không thể khai báo từng đường dẫn trước khi chạy, @OutputDirectory thường thể hiện hợp đồng đúng hơn.

### 1.2. Vì sao dùng Property API thay vì File thông thường?

Gradle chấp nhận một số kiểu khai báo file đầu ra, nhưng trong build logic hiện đại nên ưu tiên các managed property:

~~~groovy
@OutputFile
abstract RegularFileProperty getReportFile()

@OutputFiles
abstract ConfigurableFileCollection getResultFiles()

@OutputDirectory
abstract DirectoryProperty getDestinationDirectory()
~~~

- **RegularFileProperty** giữ tham chiếu đến một file đơn và được nối với Provider/TaskProvider.
- **ConfigurableFileCollection** chứa tập file, hỗ trợ from(...) để thêm nguồn và truy vấn files khi thực thi.
- **DirectoryProperty** mô tả một thư mục; có thể dùng các API layout để chỉ định thư mục con/file con mà không tạo đường dẫn tuyệt đối cứng.
- **abstract getter** cho phép Gradle cấp implementation/property phù hợp, thay vì task phải tự new các đối tượng đó.

Annotation nên được đặt trên **getter thuộc tính** trong class task Java/Groovy (và ở property tương ứng theo cú pháp ngôn ngữ). Chỉ gắn annotation lên một setter hoặc lên một field trong Java có thể khiến Gradle không nhận như bạn kỳ vọng.

## 2. @OutputFile: một file kết quả rõ ràng

### 2.1. Cấu trúc

~~~groovy
abstract class CreateSummary extends DefaultTask {
    @Input
    abstract Property<String> getTitle()

    @OutputFile
    abstract RegularFileProperty getSummaryFile()

    @TaskAction
    void createSummary() {
        File output = summaryFile.get().asFile
        output.parentFile.mkdirs()
        output.setText('title=' + title.get() + '\n', 'UTF-8')
    }
}
~~~

Đây là **định nghĩa task type**, chưa phải toàn bộ build script chạy độc lập. Task type cần được đặt trong build.gradle hoặc plugin và đăng ký kèm giá trị cho title, summaryFile.

Giải thích:

- @Input báo Gradle rằng **title** ảnh hưởng đến nội dung kết quả.
- @OutputFile khẳng định **summaryFile là một file**, không phải thư mục.
- summaryFile.get().asFile chỉ biến đường dẫn được cấp bằng Provider thành java.io.File khi action thực thi.
- TaskAction thực sự ghi nội dung. Nếu chỉ có annotation mà không ghi file, Gradle không tự tạo báo cáo có nội dung thay bạn.
- output.parentFile.mkdirs() đảm bảo thư mục cha có sẵn. Gradle cũng có cơ chế tạo parent cho @OutputFile trong các trường hợp phù hợp, nhưng code tự kiểm tra thư mục cha vẫn dễ hiểu và không nên dựa vào việc file đã tồn tại.

Đăng ký với layout.buildDirectory thay vì đường dẫn cố định:

~~~groovy
tasks.register('createSummary', CreateSummary) {
    title.convention('Java 17')
    summaryFile.set(
        layout.buildDirectory.file('generated/summary/report.txt')
    )
}
~~~

File kết quả mong đợi là **build/generated/summary/report.txt**. Với title mặc định, nội dung là:

~~~text
title=Java 17
~~~

File thực có một ký tự xuống dòng ở cuối. Nếu dùng -Ptitle=... mà chưa nối task title với project property, nội dung **không tự đổi**, bởi trong đoạn này title chỉ có convention literal.

### 2.2. Dùng Provider để liên kết cấu hình

Thay cấu hình title bằng một nguồn Gradle:

~~~groovy
tasks.register('createSummary', CreateSummary) {
    title.convention(
        providers.gradleProperty('reportTitle').orElse('Java 17')
    )
    summaryFile.set(
        layout.buildDirectory.file('generated/summary/report.txt')
    )
}
~~~

Giờ chạy -PreportTitle=Kotlin sẽ làm input title thay đổi và task có thể thực thi lại. Điều đó xảy ra vì **input đã được khai báo**, không phải vì @OutputFile tự đọc -P.

**Đừng gọi title.get() khi đang đăng ký task** chỉ để cấu hình file path hoặc String nếu có thể giữ Provider. Lấy giá trị trong @TaskAction hoặc nối Provider vào property khác sẽ giúp Gradle nhìn được quan hệ lazy.

## 3. @OutputFiles: nhiều file đầu ra có danh sách xác định

### 3.1. Khi cần nó

Giả sử task luôn sinh hai báo cáo:

~~~text
build/generated/many/alpha.txt
build/generated/many/beta.txt
~~~

Cả hai file đều do cùng một task quản lý, đều là kết quả đầu ra. Với danh sách này, dùng @OutputFiles trên ConfigurableFileCollection hợp lý:

~~~groovy
abstract class CreatePair extends DefaultTask {
    @Input
    abstract Property<String> getTitle()

    @OutputFiles
    abstract ConfigurableFileCollection getResultFiles()

    @TaskAction
    void generateFiles() {
        resultFiles.files.sort { a, b -> a.name <=> b.name }.each { File f ->
            f.parentFile.mkdirs()
            f.setText(f.name + '=' + title.get() + '\n', 'UTF-8')
        }
    }
}
~~~

Đây là task type minh họa. Cấu hình output nên diễn ra trước execution:

~~~groovy
tasks.register('createPair', CreatePair) {
    title.convention('Java 17')
    resultFiles.from(
        layout.buildDirectory.file('generated/many/alpha.txt'),
        layout.buildDirectory.file('generated/many/beta.txt')
    )
}
~~~

- **resultFiles** là một collection gồm những đường dẫn file đã được Gradle nhận diện.
- from(...) **bổ sung** các file vào collection.
- Task action duyệt các file và thực sự tạo nội dung.
- Thay đổi danh sách đường dẫn hoặc nội dung output có thể khiến Gradle đánh dấu task không còn UP-TO-DATE.
- Trong mã ví dụ, sort theo tên chỉ để thứ tự ghi ổn định, không phải yêu cầu của @OutputFiles.

Với title=Java 17, hai file chứa:

**alpha.txt**

~~~text
alpha.txt=Java 17
~~~

**beta.txt**

~~~text
beta.txt=Java 17
~~~

Chỉ dùng @OutputFiles khi **tập file dự kiến có thể được mô tả trước khi chạy action**, có thể bằng Provider. Nếu task chỉ biết tên file sau khi gọi một API trong execution hoặc số file xuất ra thay đổi tùy nội dung đọc lúc chạy, đừng âm thầm tạo thêm file ngoài danh sách đã khai báo.

### 3.2. Collection khác directory

@OutputFiles không có nghĩa "mọi file trong thư mục bất kỳ". Nó là một tập đường dẫn đầu ra. Nếu bạn chỉ khai báo alpha.txt, nhưng action còn sinh beta.txt, Gradle không có một hợp đồng output đầy đủ.

Việc dùng FileTree làm @OutputFiles không phải mẹo an toàn để “tự động gom mọi output”: **task output caching bị vô hiệu hóa nếu tập output chứa file tree** theo tài liệu @OutputFiles. Với một cây kết quả thực sự thuộc quyền sở hữu của task, nên cân nhắc @OutputDirectory và thư mục dành riêng.

Ngoài ConfigurableFileCollection, annotation @OutputFiles còn có thể được áp dụng cho các dạng collection/map theo API được Gradle hỗ trợ. Với map, key phải là **chuỗi không rỗng** và mỗi value phải resolve được thành file. Bài này dùng managed file collection để ví dụ rõ ràng và dễ theo dõi.

## 4. @OutputDirectory: một cây thư mục kết quả

### 4.1. Trường hợp điển hình

Một task sinh một trang tài liệu kèm nhiều file con:

~~~text
build/generated/site/
├── index.txt
└── details/
    └── notes.txt
~~~

Đầu ra thuộc **một thư mục gốc**. Không nhất thiết phải khai báo hai @OutputFile riêng nếu task thực sự sở hữu và quản lý toàn bộ cây này.

~~~groovy
abstract class CreateSite extends DefaultTask {
    @Input
    abstract Property<String> getTitle()

    @OutputDirectory
    abstract DirectoryProperty getSiteDir()

    @TaskAction
    void createSite() {
        File root = siteDir.get().asFile
        root.mkdirs()

        File index = new File(root, 'index.txt')
        index.setText('index=' + title.get() + '\n', 'UTF-8')

        File notes = new File(root, 'details/notes.txt')
        notes.parentFile.mkdirs()
        notes.setText('details=' + title.get() + '\n', 'UTF-8')
    }
}
~~~

Đăng ký:

~~~groovy
tasks.register('createSite', CreateSite) {
    title.convention('Java 17')
    siteDir.set(
        layout.buildDirectory.dir('generated/site')
    )
}
~~~

**Khác biệt quan trọng:** @OutputDirectory mô tả một **thư mục**. Gradle có thể theo dõi nội dung các file được task tạo trong đó và dùng chúng khi kiểm tra UP-TO-DATE. Đầu ra có thể là nhiều file con, nhiều cấp thư mục mà không phải liệt kê từng tên.

**Nhưng thư mục không phải hộp đựng dữ liệu tùy tiện:** Đừng cho các task khác ghi lung tung vào cùng output directory. Khi hai task cùng sở hữu một thư mục hoặc các đường dẫn đầu ra chồng nhau, Gradle khó tách ai đã tạo file nào; build cache có thể bị vô hiệu hóa vì overlapping outputs, các lượt build song song và việc dọn output cũ có thể không an toàn.

### 4.2. Chọn thư mục riêng cho từng task

Nên:

~~~text
build/generated/createSite/
build/generated/createApiDocs/
build/generated/createClient/
~~~

Tránh để các task cùng đánh dấu **build/generated/** là output directory rồi viết vào các thư mục con do người khác cũng quản lý, ví dụ:

~~~text
Task A @OutputDirectory -> build/generated/
Task B @OutputDirectory -> build/generated/
~~~

Ngay cả khi task A viết a.txt và task B viết b.txt, Gradle không thể xác định một chủ sở hữu rõ ràng của thư mục và có thể tắt caching cho task vì output overlap. Hãy tách output roots hoặc mô tả các @OutputFile thực sự rời nhau.

### 4.3. Một điều ít trực giác về file thêm vào directory

Đối với output directory, Gradle so sánh dấu vết của những output đã biết từ lần chạy trước. Một số file **mới được người dùng thêm bằng tay** trong directory sau khi task chạy có thể bị Gradle bỏ qua khi quyết định task có UP-TO-DATE hay không, vì file đó không phải output đã được task sinh ở lần trước. Đừng dùng việc thêm một file lạ vào thư mục để khẳng định chắc Gradle phải chạy lại.

Nếu task cần bảo đảm thư mục chỉ chứa những file hợp lệ, hãy thiết kế **quy tắc dọn file thừa có kiểm soát**, hoặc tạo output directory mới/riêng theo nhiệm vụ; không xóa dữ liệu của task khác.

## 5. So sánh ba annotation trong một bảng

| Câu hỏi | @OutputFile | @OutputFiles | @OutputDirectory |
|---|---|---|---|
| Đầu ra được mô tả là gì? | Đúng một file | Một collection các file | Một directory root và các kết quả bên trong |
| Managed property tiêu biểu | RegularFileProperty | ConfigurableFileCollection | DirectoryProperty |
| Ví dụ | report.txt | first.txt, second.txt | docs/index.txt và docs/assets/... |
| Tên file phải biết khi cấu hình? | Đường dẫn file do Property/Provider cung cấp | Các file dự kiến cần xác định khi Gradle đánh giá output | Không phải liệt kê từng file con |
| Gradle theo dõi gì? | Path và nội dung file | Tập path và nội dung các file | Đường dẫn directory và dấu vết các file output bên trong |
| Cách tạo thực tế | Task action ghi file | Task action ghi từng file | Task action ghi bên trong thư mục |
| Cache có tự bật? | Không | Không | Không |
| Khi nào nên tránh? | Task thực sự sinh cả một cây | File list chỉ xuất hiện sau khi action chạy hoặc dùng FileTree một cách thiếu kiểm soát | Nhiều task cùng dùng một directory |
| Output trùng với task khác? | Không nên | Không nên | Không nên |

**Kết luận chọn API:** Hãy mô tả **đúng đơn vị sở hữu kết quả**: một file thì @OutputFile; một danh sách các file đã được xác định thì @OutputFiles; một cây output do task sở hữu thì @OutputDirectory.

## 6. Thực hành hoàn chỉnh — ba loại output trong một dự án Gradle

Phần này là dự án **Gradle Groovy DSL + Java 17** có thể chạy độc lập sau khi chuẩn bị Wrapper/JDK phù hợp. Custom tasks được viết bằng Groovy trong build.gradle; một lớp Java 17 nhỏ đi kèm để thể hiện đây là build của dự án Java, nhưng **các annotation Gradle phải đặt trên task type**, không đặt trên lớp Java ứng dụng.

### 6.1. Cấu trúc dự án

~~~text
gradle-outputs-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/main/java/demo/Main.java
~~~

Nếu dự án mới chưa có Wrapper, lúc đầu chỉ cần settings.gradle, build.gradle và Main.java; dùng bản Gradle đã cài tương thích chạy **gradle wrapper** một lần rồi dùng script Wrapper được sinh. Môi trường cần JDK phù hợp để chạy Gradle và toolchain Java 17 được cài đặt hoặc provision theo cấu hình hiện hành.

**settings.gradle:**

~~~groovy
rootProject.name = 'gradle-outputs-lab'
~~~

**build.gradle — ví dụ đầy đủ:**

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.OutputFiles
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.Main'
}

// Một file kết quả.
abstract class WriteOne extends DefaultTask {
    @Input
    abstract Property<String> getTitle()

    @OutputFile
    abstract RegularFileProperty getReportFile()

    @TaskAction
    void writeReport() {
        File output = reportFile.get().asFile
        output.parentFile.mkdirs()
        output.setText('title=' + title.get() + '\n', 'UTF-8')
        logger.quiet('one=' + output.name)
    }
}

// Một danh sách file kết quả đã xác định.
abstract class WriteMany extends DefaultTask {
    @Input
    abstract Property<String> getTitle()

    @OutputFiles
    abstract ConfigurableFileCollection getReportFiles()

    @TaskAction
    void writeReports() {
        reportFiles.files.sort { a, b -> a.name <=> b.name }.each { File output ->
            output.parentFile.mkdirs()
            output.setText(
                output.name + '=' + title.get() + '\n', 'UTF-8'
            )
        }
        logger.quiet('many=' + reportFiles.files.size())
    }
}

// Một cây thư mục kết quả.
abstract class WriteFolder extends DefaultTask {
    @Input
    abstract Property<String> getTitle()

    @OutputDirectory
    abstract DirectoryProperty getReportDir()

    @TaskAction
    void writeFolder() {
        File root = reportDir.get().asFile
        root.mkdirs()

        new File(root, 'index.txt')
            .setText('index=' + title.get() + '\n', 'UTF-8')

        File notes = new File(root, 'details/notes.txt')
        notes.parentFile.mkdirs()
        notes.setText('details=' + title.get() + '\n', 'UTF-8')

        logger.quiet('directory=' + root.name)
    }
}

// Consumer: nhận file từ producer và được Gradle theo dõi input.
abstract class InspectOne extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract RegularFileProperty getInputFile()

    @TaskAction
    void inspect() {
        logger.quiet('read=' + inputFile.get().asFile.getText('UTF-8').trim())
    }
}

// Nguồn chung cho input; có thể override bằng -PreportTitle=...
def reportTitle = providers.gradleProperty('reportTitle')
    .orElse('Java 17')

def singleTask = tasks.register('writeOne', WriteOne) {
    title.set(reportTitle)
    reportFile.set(
        layout.buildDirectory.file('generated/one/report.txt')
    )
}

tasks.register('writeMany', WriteMany) {
    title.set(reportTitle)
    reportFiles.from(
        layout.buildDirectory.file('generated/many/alpha.txt'),
        layout.buildDirectory.file('generated/many/beta.txt')
    )
}

tasks.register('writeFolder', WriteFolder) {
    title.set(reportTitle)
    reportDir.set(
        layout.buildDirectory.dir('generated/folder')
    )
}

// flatMap nối output chính xác và mang thông tin producer dependency.
tasks.register('inspectOne', InspectOne) {
    inputFile.set(singleTask.flatMap { task -> task.reportFile })
}

// Task tổng hợp chỉ phụ thuộc ba task sinh báo cáo.
tasks.register('allReports') {
    group = 'verification'
    description = 'Sinh ba kiểu đầu ra'
    dependsOn 'writeOne', 'writeMany', 'writeFolder'
}
~~~

**src/main/java/demo/Main.java:**

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Hello from Java 17");
    }
}
~~~

**Điểm cần kiểm tra trước khi chạy:**

- Import có đầy đủ các annotation và managed property.
- Mỗi task type có một hoặc nhiều output property được annotate.
- Những đầu ra có **đường dẫn không trùng nhau**:
  - build/generated/one/report.txt;
  - build/generated/many/alpha.txt và beta.txt;
  - build/generated/folder/ cùng các file con.
- Cả ba task sinh file dùng input title nên thay -PreportTitle làm thay đổi dữ liệu đầu vào.
- Task inspectOne có **@InputFile** và nối đến **@OutputFile** của writeOne bằng TaskProvider.flatMap.
- Dự án Java không cần Maven Central hoặc thư viện ngoài để biên dịch Main; dùng plugin application đi kèm Gradle.

### 6.2. Chạy lần đầu

Linux/macOS:

~~~bash
./gradlew -q allReports
./gradlew -q inspectOne
./gradlew -q run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -q allReports
.\gradlew.bat -q inspectOne
.\gradlew.bat -q run
~~~

Các task allReports có thể được thực thi theo thứ tự khác nhau vì không có ràng buộc thứ tự giữa writeOne, writeMany và writeFolder. **Ba dòng phát ra từ các task action** khi chạy allReports là:

~~~text
one=report.txt
many=2
directory=folder
~~~

Thứ tự ba dòng có thể khác; không nên viết test dựa vào thứ tự đó.

Khi gọi inspectOne, output file được task writeOne tạo sẵn và consumer in:

~~~text
read=title=Java 17
~~~

Trong ví dụ, inspectOne **không** cần một dependsOn('writeOne') riêng: thông tin dependency đi theo singleTask.flatMap { task -> task.reportFile } và kết nối inputFile.set(...). Nếu gọi inspectOne ngay từ đầu khi chưa có report.txt, Gradle cũng có thể lập lịch producer trước consumer.

Chạy run, chương trình Java in:

~~~text
Hello from Java 17
~~~

Đây là stdout của Java main, không phải kết quả Gradle kiểm tra output. Những dòng do logger.quiet phát ra sẽ được hiển thị khi task tương ứng thực thi; Gradle có thể in thêm lỗi/toolchain warning tùy môi trường.

### 6.3. Kiểm tra các file trên đĩa

Sau khi allReports chạy, kết quả kỳ vọng:

~~~text
build/
└── generated/
    ├── one/
    │   └── report.txt
    ├── many/
    │   ├── alpha.txt
    │   └── beta.txt
    └── folder/
        ├── index.txt
        └── details/
            └── notes.txt
~~~

Nội dung:

| File | Dòng nội dung (không hiển thị newline cuối) |
|---|---|
| generated/one/report.txt | title=Java 17 |
| generated/many/alpha.txt | alpha.txt=Java 17 |
| generated/many/beta.txt | beta.txt=Java 17 |
| generated/folder/index.txt | index=Java 17 |
| generated/folder/details/notes.txt | details=Java 17 |

Trong code, mọi file đều được ghi UTF-8 và có một ký tự xuống dòng cuối nội dung. Bạn có thể mở file bằng trình soạn thảo hoặc lệnh của hệ điều hành để xác minh.

### 6.4. Chạy lần hai và quan sát UP-TO-DATE

~~~bash
./gradlew allReports --console=plain
~~~

Nếu không đổi input, code task, Gradle version, file output và môi trường có ảnh hưởng, các task sinh báo cáo thường được báo:

~~~text
> Task :writeOne UP-TO-DATE
> Task :writeMany UP-TO-DATE
> Task :writeFolder UP-TO-DATE
~~~

**Không giả định thứ tự hoặc số lượng các dòng log cố định.** Task allReports là task tổng hợp không có action sinh output; trạng thái/log của nó có thể khác ba task thực sự tạo file.

Tại sao Gradle skip? Vì dấu vết input và output sau lần chạy trước phù hợp với hiện tại. Chỉ **khai báo @Output... mà không khai báo input title** sẽ khiến Gradle không biết title đổi nên ảnh hưởng tới output.

### 6.5. Sửa input và chạy lại

~~~bash
./gradlew -q allReports -PreportTitle=Gradle
./gradlew -q inspectOne -PreportTitle=Gradle
~~~

Ba task sinh output thực thi lại (trừ trường hợp đặc biệt do môi trường/cache khác can thiệp) vì title đã đổi từ Java 17 sang Gradle. Kết quả các file có dòng lần lượt:

~~~text
title=Gradle
alpha.txt=Gradle
beta.txt=Gradle
index=Gradle
details=Gradle
~~~

Task inspectOne in:

~~~text
read=title=Gradle
~~~

Cơ chế là **input @Input**, không phải vì -P tự được hiểu bởi @OutputFile. Build script đã nối Provider của reportTitle tới property title bằng title.set(reportTitle).

### 6.6. Xóa một output để kiểm chứng

Ví dụ trên Linux/macOS (chỉ xóa file trong thư mục thí nghiệm):

~~~bash
rm build/generated/one/report.txt
./gradlew writeOne --console=plain
~~~

Windows PowerShell:

~~~powershell
Remove-Item .\build\generated\one\report.txt
.\gradlew.bat writeOne --console=plain
~~~

Task writeOne phải tạo lại report.txt vì đầu ra đã khai báo không còn tồn tại. Khi một output đã được Gradle theo dõi bị xóa hoặc bị sửa, Gradle có lý do để chạy task lại.

**Không xóa ngẫu nhiên thư mục build của dự án khác** và không dùng lệnh xóa cache Gradle User Home để thử hiện tượng này. Bài tập chỉ thao tác với file được tạo trong dự án lab.

### 6.7. --rerun-tasks và --build-cache

Muốn **cố tình chạy lại** action dù task đã UP-TO-DATE:

~~~bash
./gradlew writeOne --rerun-tasks
~~~

Lệnh này bỏ qua tối ưu UP-TO-DATE và khả năng lấy task output từ build cache cho các task bị buộc rerun. Nó không sửa khai báo output và không cần thiết trong build bình thường.

Nếu bật build cache:

~~~bash
./gradlew writeOne --build-cache
~~~

**Không thể kết luận task tự có FROM-CACHE chỉ nhờ @OutputFile.** Một custom task thường phải được tác giả thiết kế để **cacheable** (ví dụ annotation @CacheableTask trên task type), đáp ứng các điều kiện của Gradle và có input/output chính xác, không đụng output overlap hay trạng thái phụ thuộc môi trường.

Ba annotation trong bài giúp mô tả output; chúng **không** tự làm task eligible cho task output caching ở mọi cấu hình. Với bài lab, điều quan trọng là kiểm chứng UP-TO-DATE chính xác; caching là bước thiết kế bổ sung sau đó.

## 7. Gradle quyết định UP-TO-DATE như thế nào?

Ở mức khái niệm:

1. Trước lần chạy, Gradle xác định những inputs mà task khai báo, output paths mà task sở hữu và thông tin thực thi liên quan.
2. Sau một lần thực thi thành công, Gradle có thể lưu dấu vết (fingerprint) đầu vào và đầu ra.
3. Lượt sau, Gradle so sánh dấu vết hiện tại với lần trước.
4. Nếu các điều kiện phù hợp, task được đánh dấu **UP-TO-DATE** và action không chạy lại.
5. Nếu input hoặc output liên quan thay đổi, task có thể phải thực thi lại.
6. Nếu có task output cache và task đủ điều kiện, Gradle có thể lấy đầu ra từ cache (**FROM-CACHE**) thay vì thực thi action.

Một task có **output khai báo đúng** là điều kiện cơ bản cho UP-TO-DATE trong trường hợp thông thường; nhưng việc skip còn phụ thuộc task implementation, Gradle, logic upToDateWhen, các annotation khác và dữ liệu thực tế.

### 7.1. Khai báo đủ input quan trọng như khai báo output

Ví dụ sai:

~~~groovy
abstract class WrongReport extends DefaultTask {
    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        // Đọc một biến môi trường không khai báo @Input.
        String value = System.getenv('BUILD_LABEL') ?: 'unknown'
        File f = outputFile.get().asFile
        f.parentFile.mkdirs()
        f.setText(value + '\n', 'UTF-8')
    }
}
~~~

Đoạn này minh họa **anti-pattern**, chưa phải một build hoàn chỉnh. Kết quả phụ thuộc BUILD_LABEL nhưng không có property @Input được khai báo tương ứng. Gradle có thể xem task UP-TO-DATE dù BUILD_LABEL đổi, tùy cách hệ thống phát hiện input; đừng dựa vào việc Gradle sẽ đoán mọi giá trị bạn đọc.

Sửa bằng cách tạo một Property<String> có @Input, nối từ Provider môi trường và cho action đọc property:

~~~groovy
abstract class BetterReport extends DefaultTask {
    @Input
    abstract Property<String> getBuildLabel()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        File f = outputFile.get().asFile
        f.parentFile.mkdirs()
        f.setText(buildLabel.get() + '\n', 'UTF-8')
    }
}

tasks.register('betterReport', BetterReport) {
    buildLabel.set(
        providers.environmentVariable('BUILD_LABEL').orElse('unknown')
    )
    outputFile.set(
        layout.buildDirectory.file('generated/better/label.txt')
    )
}
~~~

Đây là một **đoạn task type + đăng ký** có thể thêm vào dự án Gradle hỗ trợ các imports phù hợp ở đầu file. Nguồn environment đi qua Provider, rồi thông qua @Input nên Gradle biết giá trị nào ảnh hưởng kết quả. Nếu tác giả muốn strict reproducibility, còn phải xem cách môi trường được kiểm soát trong CI.

### 7.2. Kết quả không ổn định làm cache kém tin cậy

Không nên sinh một file với timestamp ngẫu nhiên hoặc UUID mới mỗi lần mà vẫn tuyên bố output chỉ phụ thuộc một giá trị title:

~~~groovy
// Anti-pattern: kết quả thay đổi theo đồng hồ, nhưng thời gian không được mô tả như input.
outputFile.get().asFile.text = new Date().toString()
~~~

Nếu cùng inputs nhưng output thay đổi theo thời gian, một cached output của lần chạy trước có thể không tương đương mong muốn hiện tại. Thiết kế task nên **deterministic** nếu muốn áp dụng caching; nếu timestamp là thông tin nghiệp vụ bắt buộc, đưa nó vào input có kiểm soát hoặc không cache task đó tùy mục tiêu.

## 8. Đầu ra có thể suy ra task dependency

Một lợi ích lớn của managed output property là khả năng **nối producer → consumer** bằng Provider thay vì đặt dependsOn bằng tay mọi nơi.

Trong ví dụ hoàn chỉnh:

~~~groovy
def singleTask = tasks.register('writeOne', WriteOne) {
    reportFile.set(
        layout.buildDirectory.file('generated/one/report.txt')
    )
    title.convention('Java 17')
}

tasks.register('inspectOne', InspectOne) {
    inputFile.set(singleTask.flatMap { task -> task.reportFile })
}
~~~

- singleTask là **TaskProvider<WriteOne>**.
- task.reportFile là **RegularFileProperty có @OutputFile** trên getter của task.
- flatMap tạo Provider tới file output mà không gọi singleTask.get() ngay.
- inputFile.set(...) nối file đó vào **@InputFile** của consumer.
- Gradle có thể suy ra quan hệ thực thi giữa consumer và producer: không đọc file trước khi task tạo nó.

Đừng thay nối này bằng code eager:

~~~groovy
// Không nên: lấy File và dùng ngay ở pha configuration.
def f = singleTask.get().reportFile.get().asFile
~~~

Đoạn trên yêu cầu hiện thực hóa/truy vấn quá sớm, và nếu sau đó tự bọc file trong một Provider khác không mang dependency, Gradle có thể mất quan hệ task mà bạn mong đợi. **Đường dẫn có đúng không có nghĩa quan hệ phụ thuộc task đã được khai báo đúng.**

### 8.1. Khi một output directory được consumer dùng làm input

Đối với @OutputDirectory, consumer có thể dùng @InputDirectory với DirectoryProperty:

~~~groovy
abstract class ReadSiteIndex extends DefaultTask {
    @InputDirectory
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract DirectoryProperty getSourceDir()

    @TaskAction
    void readIndex() {
        File f = new File(sourceDir.get().asFile, 'index.txt')
        logger.quiet(f.getText('UTF-8').trim())
    }
}

def siteTask = tasks.named('writeFolder', WriteFolder)

tasks.register('readSiteIndex', ReadSiteIndex) {
    sourceDir.set(siteTask.flatMap { task -> task.reportDir })
}
~~~

Đây là **đoạn bổ sung** cho build.gradle của bài lab; cần import InputDirectory ở đầu file. Do TaskProvider được nối tới output directory của producer, Gradle có thể suy ra dependency. Consumer thực sự đọc index.txt trong thư mục mà producer đã khai báo.

Nếu consumer chỉ cần một file cụ thể trong output directory, bạn có thể thiết kế một RegularFileProperty provider tới file con qua API directory.file(...), nhưng phải giữ đúng dependency và annotation đầu vào. Với nhiều file, dùng InputFiles và file collection được nối từ task producer theo cơ chế Gradle hỗ trợ, tránh tự lấy File bằng get() lúc configuration.

## 9. @OutputFiles khác @OutputDirectory trong tình huống động

Ví dụ task tạo 10 file cấu hình với tên phụ thuộc danh sách các module. Nếu danh sách module đã được cung cấp bằng một Provider trong configuration, bạn **có thể** tính ra một danh sách path có thể mô tả qua @OutputFiles.

Nếu task phải chạy một công cụ chỉ biết tạo ra những file nào **sau khi thực thi**, thì không thể khai báo đúng danh sách @OutputFiles bằng một bước tĩnh trước action. Trong trường hợp task quản lý toàn bộ thư mục output dành riêng, @OutputDirectory thường phù hợp hơn.

**Tuy nhiên, chọn directory không thay cho khai báo input:** Nếu danh sách module ảnh hưởng output, vẫn phải khai báo nó bằng @Input, @InputFiles hoặc các mô hình input tương đương. Gradle cần biết **điều kiện nào thay đổi kết quả**, bất kể kết quả có bao nhiêu file.

### 9.1. Một task vừa có file output vừa có directory output?

Có thể có task sinh một file manifest riêng và một thư mục dữ liệu khác, nếu chúng **không chồng lên nhau** và đều được task quản lý:

~~~groovy
abstract class CompositeOutput extends DefaultTask {
    @OutputFile
    abstract RegularFileProperty getManifestFile()

    @OutputDirectory
    abstract DirectoryProperty getAssetsDir()
}
~~~

Đây là một **skeleton** minh họa kiểu property, không phải task độc lập chạy được vì chưa có @TaskAction và chưa cấu hình đường dẫn. Khi triển khai, nên để manifestFile ở một path riêng, chẳng hạn build/generated/composite/manifest.json và assetsDir ở build/generated/composite/assets; tránh khai báo một directory chứa những file đồng thời được task khác sở hữu.

Với một task tự khai báo cả file và thư mục **trùng lắp nhau**, Gradle và công cụ dọn output khó phân biệt tài nguyên; ưu tiên chọn một đơn vị sở hữu rõ ràng thay vì annotate mọi cấp của cùng một cây.

## 10. @OutputFiles và file tree: hệ quả với build cache

Trong Gradle, **FileTree** là tập file được duyệt theo thư mục và pattern. FileTree rất hữu ích khi đọc input files, nhưng khi dùng trực tiếp như một phần output của @OutputFiles có vấn đề:

- Những file có mặt có thể phụ thuộc vào chính quá trình thực thi task, khiến tập output khó biết trước.
- Tài liệu @OutputFiles quy định **task output caching bị tắt khi tập output chứa file tree**.
- Cách làm này còn có thể khiến ownership/tracking không rõ ràng nếu pattern quét vào khu vực do task khác ghi.

Ví dụ mô tả không khuyến nghị:

~~~groovy
// Anti-pattern: dùng fileTree quét thư mục làm "danh sách output".
// Không phải một đoạn task hoàn chỉnh.
resultFiles.from(fileTree('build/generated/shared'))
~~~

Thay vì vậy:

- Nếu có **hai đường dẫn file xác định**: dùng resultFiles.from(fileAProvider, fileBProvider) với @OutputFiles.
- Nếu một task sở hữu **cả thư mục với cây file thay đổi**: dùng @OutputDirectory trên DirectoryProperty.
- Nếu nhiều task cần ghi kết quả: tách output directories, hoặc khai báo các output file rời nhau, bảo đảm ownership không chồng lắp.

Đừng chọn @OutputFiles chỉ vì muốn “bật cache”: cả @OutputFiles và @OutputDirectory đều là khai báo đầu ra; khả năng cache còn phụ thuộc nhiều điều kiện khác.

## 11. Overlapping outputs và parallel build

Một cấu hình sai phổ biến:

~~~text
Task A -> @OutputFile build/generated/a.txt
Task B -> @OutputDirectory build/generated/
Task C -> @OutputFile build/generated/a.txt
~~~

- A và C cùng khai báo một file, trực tiếp xung đột.
- B khai báo sở hữu cả thư mục bao chứa a.txt, nên đụng output của A/C.
- Khi chạy song song, nhiều task có thể ghi/xóa cùng file; output cache và dọn stale output có thể không an toàn.

Cấu hình tốt hơn:

~~~text
Task A -> build/generated/taskA/a.txt
Task B -> build/generated/taskB/
Task C -> build/generated/taskC/a.txt
~~~

Mỗi task có output path riêng. Khi một task **cần dùng** output của task khác, hãy khai báo qua input provider hoặc dependency phù hợp, không cho consumer đồng thời khai báo output của producer thành output riêng của mình.

### 11.1. Không nhầm đường dẫn con với quyền sở hữu

Một project có thể chia sẻ buildDirectory cho nhiều task nhưng nên đặt đầu ra khác nhau bên dưới nó. Sự tồn tại của build/generated chung **không phải vấn đề** nếu mỗi task đăng ký chính xác những file/directory không đè lên nhau.

Vấn đề là khi bạn annotate **toàn bộ build/generated** là @OutputDirectory của một task, trong lúc task khác cũng ghi một phần bên trong; lúc ấy Gradle không biết mỗi output thuộc về ai và có thể tắt caching.

### 11.2. Vì sao không nên ghi output vào src/main?

Thư mục src/main/java hoặc src/main/resources thường chứa **source do developer quản lý**. Đưa file do task tự sinh vào đó có thể tạo file chưa được ignore, khiến Git bẩn, và khó bảo đảm task dọn đúng kết quả của mình.

Ưu tiên thư mục dưới layout.buildDirectory, ví dụ:

~~~groovy
reportDir.set(layout.buildDirectory.dir('generated/codegen'))
~~~

Nếu task sinh Java source cho compileJava, hãy khai báo output directory của task và **nối task output vào Java source set** theo API của Gradle, để Gradle suy ra dependency thay vì sửa src/main/java bằng tay.

## 12. Annotation output và runtime API: hai cách mô tả cùng thông tin

Bạn không bắt buộc phải tạo custom task class cho mọi tác vụ nhỏ. Với task ad-hoc, Gradle cung cấp runtime API **outputs.file**, **outputs.files**, **outputs.dir**:

~~~groovy
tasks.register('adHocReport') {
    def target = layout.buildDirectory.file('generated/adhoc/report.txt')
    def label = providers.gradleProperty('adHocLabel').orElse('simple')

    inputs.property('label', label)
    outputs.file(target)

    doLast {
        File f = target.get().asFile
        f.parentFile.mkdirs()
        f.setText(label.get() + '\n', 'UTF-8')
    }
}
~~~

Có thể chạy bằng:

~~~bash
./gradlew -q adHocReport
~~~

Nếu không có -PadHocLabel, file build/generated/adhoc/report.txt chứa dòng:

~~~text
simple
~~~

Các cặp tương ứng:

| Trong custom task type | Trong ad-hoc task |
|---|---|
| @Input Property<String> | inputs.property('name', provider) |
| @OutputFile RegularFileProperty | outputs.file(providerOrFile) |
| @OutputFiles ConfigurableFileCollection | outputs.files(fileCollectionOrProviders) |
| @OutputDirectory DirectoryProperty | outputs.dir(directoryProviderOrFile) |

**Ưu tiên custom task type khi task phức tạp hoặc dùng lại nhiều nơi:** annotation cung cấp hợp đồng rõ ràng, kiểm tra input/output và tích hợp tốt với managed Property. Với script ngắn, runtime API vẫn hữu ích nếu bạn khai báo đầy đủ cả input lẫn output.

**Không khai báo output hai lần một cách vô ý:** Nếu property của custom task đã có @OutputFile, không cần thêm outputs.file(...) cho cùng path chỉ để “Gradle thấy chắc hơn”. Hai cơ chế là hai cách đăng ký thông tin; dùng nhất quán để tránh hiểu nhầm.

## 13. Nên hiểu build cache, UP-TO-DATE và incremental execution khác nhau

Ba khái niệm thường bị trộn lẫn:

1. **UP-TO-DATE:** Gradle so sánh inputs/outputs đã ghi nhận và nhận thấy task không cần chạy lại.
2. **FROM-CACHE:** Gradle tái sử dụng output đã cache của task đủ điều kiện khi cache key phù hợp, có thể không cần chạy action.
3. **Incremental execution:** Khi task **phải chạy**, một task type có thể chỉ xử lý những input files thực sự thay đổi thông qua InputChanges nếu đã thiết kế incremental input annotation phù hợp.

**@OutputFile/@OutputFiles/@OutputDirectory không tự biến task thành task incremental theo nghĩa InputChanges.** Chúng khai báo kết quả cần theo dõi. Muốn triển khai incremental processing, cần các @InputFiles/@InputDirectory liên quan, @Incremental hoặc @SkipWhenEmpty nếu phù hợp, và @TaskAction nhận InputChanges để xử lý sự khác biệt.

Ví dụ chọn công cụ:

| Mục tiêu | Cơ chế chính |
|---|---|
| Không chạy lại task khi input/output không đổi | Khai báo inputs + outputs đúng |
| Lấy output từ cache thay vì chạy action | Cacheable task + khai báo input/output đúng + bật cache và đáp ứng điều kiện |
| Chỉ xử lý input files đổi trong một task phải chạy | Incremental task implementation dùng InputChanges |
| Buộc chạy lại task để chẩn đoán | --rerun-tasks |
| Xóa output build do task clean quản lý | clean (không phải xóa dependency cache) |

Không nên chạy --rerun-tasks cho mọi lượt CI vì sẽ bỏ lợi ích UP-TO-DATE và task output cache. Nếu task chạy sai do annotation thiếu, sửa model input/output mới là giải pháp bền vững.

## 14. Các lỗi thường gặp và cách sửa

### Lỗi 1: Task có @OutputFile nhưng luôn chạy lại

**Kiểm tra:** Task có @Input luôn thay đổi không? Có code viết timestamp/random mỗi lần? File output có bị task khác xóa/sửa không? Path output có được cấu hình ổn định không? Task implementation hay Gradle version có thay đổi không? Có --rerun-tasks hoặc outputs.upToDateWhen { false } trong build không?

**Cách sửa:** Thu hẹp đầu vào đúng, tạo đầu ra ổn định, tách ownership và bỏ thao tác ép rerun không cần thiết. Annotation đúng chỉ là một phần của điều kiện UP-TO-DATE.

### Lỗi 2: Task bị UP-TO-DATE dù input nghiệp vụ thay đổi

**Nguyên nhân:** Task đọc environment, file ngoài hoặc property khác nhưng chưa khai báo là input.

**Cách sửa:** Dùng @Input, @InputFile, @InputFiles hoặc annotation phù hợp. Khi đọc file, khai báo path sensitivity/normalization khi cần; đừng kỳ vọng Gradle tự theo dõi mọi lần gọi System.getenv hoặc File.text trong action.

### Lỗi 3: @OutputFile trỏ vào thư mục hoặc @OutputDirectory trỏ vào file

**Nguyên nhân:** Chọn annotation sai loại output.

**Cách sửa:** @OutputFile dùng RegularFileProperty cho file, @OutputDirectory dùng DirectoryProperty cho directory. Kiểm tra path và việc đã tồn tại một file/dir trái kiểu tại đó. Gradle có cơ chế validation output; không nên bỏ qua lỗi.

### Lỗi 4: @OutputFiles thiếu một file task thực sự sinh

**Nguyên nhân:** Danh sách được cấu hình thiếu, hoặc task tạo tên file động sau khi Gradle đã xác định outputs.

**Cách sửa:** Bổ sung tất cả file có thể xác định trước; nếu không thể và task sở hữu cả cây, chuyển sang output directory riêng với @OutputDirectory. Đừng để file sinh ra mà không có ai sở hữu trong mô hình task.

### Lỗi 5: Dùng @OutputFiles trên FileTree nhưng muốn FROM-CACHE

**Nguyên nhân:** FileTree trong tập output làm task output caching bị vô hiệu hóa theo API.

**Cách sửa:** Chuyển sang file collection tường minh hoặc một DirectoryProperty cho toàn bộ output tree tùy bài toán. Sau đó đánh giá khả năng cacheable của task độc lập, không mặc định annotation mới sẽ đủ.

### Lỗi 6: Hai task cùng ghi vào một directory

**Nguyên nhân:** Output overlap; task không có vùng kết quả riêng.

**Cách sửa:** Dùng output paths riêng dưới layout.buildDirectory, chuyển file cần dùng từ producer sang consumer qua Provider. Đừng để hai task cùng sở hữu file nếu một task thực sự chỉ đọc nó.

### Lỗi 7: Consumer chạy trước producer hoặc thiếu file

**Nguyên nhân:** Chỉ truyền đường dẫn String/File thủ công, chưa nối TaskProvider output tới input. Nếu dùng một Provider tự tạo không mang task dependency, Gradle không thể luôn suy ra quan hệ producer.

**Cách sửa:** Dùng taskProvider.flatMap { it.outputFile } với @OutputFile trực tiếp trên getter, rồi inputFile.set(...) vào @InputFile. Đảm bảo consumer task type có annotation đúng và không gọi get() để mở file trong configuration.

### Lỗi 8: Build cache không hoạt động dù task có đủ output annotations

**Nguyên nhân:** Task chưa được opt-in cacheable; input/output không phù hợp; có FileTree trong outputs, output overlap hoặc điều kiện khác của Gradle.

**Cách sửa:** Sau khi xác nhận task deterministic và khai báo input/output hoàn chỉnh, đánh giá @CacheableTask và các giới hạn của caching. Dùng --info để xem lý do Gradle không cache; tránh tuyên bố có cache chỉ vì kết quả UP-TO-DATE.

### Lỗi 9: Task dùng DirectoryProperty nhưng file mới tạo thủ công không làm task rerun

**Giải thích:** Gradle có thể bỏ qua file thêm vào output directory ngoài tập file đã ghi nhận. Đây không phải bằng chứng annotation sai; phải xác định task nào có trách nhiệm quản lý/dọn file ấy.

**Cách sửa:** Giữ output directory riêng và thực hiện việc quản lý file trong action theo hợp đồng của task; không phụ thuộc những file lạ do thao tác bên ngoài.

### Lỗi 10: Code Java ứng dụng bị gắn @OutputFile

**Nguyên nhân:** Nhầm annotation của **Gradle task implementation** với annotation dữ liệu trong mã ứng dụng Java.

**Cách sửa:** Đặt @OutputFile/@OutputFiles/@OutputDirectory trên property của class **extends DefaultTask** (Groovy/Java/Kotlin theo cách xây plugin), không đặt trên class Java main bình thường. Plugin Gradle phải load được class task type trước khi dùng nó.

### Lỗi 11: File output được tạo trong thư mục source được Git theo dõi

**Nguyên nhân:** Task ghi vào src/main/resources hoặc source directory mà không có quyền sở hữu riêng.

**Cách sửa:** Sinh file dưới build/generated...; cấu hình consumer/source set để lấy từ task output. Việc giữ source tree sạch giúp build dễ tái lập và tránh thay đổi repository ngoài ý muốn.

## 15. Checklist đánh giá một custom task có output

Trước khi đưa task vào plugin dùng chung, hãy tự hỏi:

1. **Đầu ra là file, tập file hay directory?** Chọn một annotation tương ứng.
2. **Task có thực sự sinh đúng các file/thư mục khai báo không?** Kiểm tra path, tên file, charset, cách tạo và quyền ghi.
3. **Mọi input ảnh hưởng kết quả đã được khai báo chưa?** Không đọc biến môi trường/file ngoài một cách vô hình.
4. **Đầu ra có thuộc một task duy nhất không?** Kiểm tra tránh trùng file/directory với task khác.
5. **Path có nằm dưới layout.buildDirectory khi phù hợp không?** Tránh đường dẫn tuyệt đối hoặc viết vào source tree.
6. **Có giữ Provider lazy không?** Tránh gọi get() trong configuration khi không cần.
7. **Consumer có nối từ output Provider không?** Ưu tiên inferred task dependency.
8. **Có test UP-TO-DATE không?** Chạy task hai lần, sửa input, xóa output rồi chạy lại.
9. **Có xét đến tính deterministic/cacheability không?** Annotation output không đủ để bật build cache.
10. **Nếu có nhiều file, đã chọn đúng @OutputFiles vs @OutputDirectory chưa?** Đừng dùng FileTree cho output tùy tiện.
11. **Khi task bị lỗi giữa chừng, có để lại output một phần không?** Xem cách hành động task ghi tệp an toàn, validation và khả năng rerun.
12. **Có thông điệp lỗi rõ khi input bắt buộc thiếu không?** Để Gradle phát hiện property chưa được cấu hình, hoặc ném lỗi có ngữ cảnh thích hợp.

## 16. Bài tập tự kiểm tra

**Bài 1.** Một task luôn tạo đúng một file build/generated/report.json. Chọn @OutputFile, @OutputFiles hay @OutputDirectory? Managed property nên dùng là gì?

**Bài 2.** Task sinh ba file fixed: a.txt, b.txt, c.txt. Tên file đã biết trước khi execution. Annotation và property nào diễn tả trực tiếp nhất?

**Bài 3.** Task chạy một công cụ sinh 5–50 file với tên phụ thuộc nội dung input và sở hữu toàn bộ thư mục build/generated/docs. Nếu không thể khai báo danh sách file trước action, nên chọn gì?

**Bài 4.** Một task có @OutputFile cho report.txt nhưng đọc project property reportTitle mà không khai báo @Input. Lần sau chỉ reportTitle đổi, Gradle có bắt buộc biết task phải rerun không?

**Bài 5.** Vì sao hai task khác nhau đều khai báo @OutputDirectory trỏ tới build/generated/ là rủi ro, dù action của chúng viết hai file khác nhau?

**Bài 6.** Một task có @OutputFiles trả FileTree của thư mục build/generated. Điều gì xảy ra với task output caching?

**Bài 7.** Consumer có @InputFile và producer có @OutputFile RegularFileProperty. Cần nối inputFile từ TaskProvider của producer thế nào để Gradle biết dependency?

**Bài 8.** Task đã chạy một lần và không đổi input/output. Lần thứ hai báo UP-TO-DATE. Điều này có chứng minh task cacheable và lấy FROM-CACHE không?

**Bài 9.** @OutputDirectory có tự tạo hàng loạt file index.html, style.css, app.js không? Ai phải viết nội dung các file đó?

**Bài 10.** Bạn sửa input, task thực thi lại toàn bộ, nhưng chỉ muốn xử lý file input thực sự thay đổi. Có thể đạt mục tiêu đó chỉ nhờ @OutputFiles không?

**Bài 11.** Trong dự án Groovy DSL, bạn định khai báo một output là @OutputFile File outputFile = new File('build/a.txt') ngay ở cấp root để ghi file. Có gì kém hơn việc dùng @OutputFile abstract RegularFileProperty getOutputFile() trong custom task type và layout.buildDirectory?

**Bài 12.** Khi chạy ./gradlew inspectOne từ dự án lab mà report.txt chưa tồn tại, tại sao Gradle có thể tự chạy writeOne trước mà không cần dependsOn tường minh trong inspectOne?

### Đáp án gợi ý

1. **@OutputFile + RegularFileProperty**: đúng một file.
2. **@OutputFiles + ConfigurableFileCollection**: mô tả danh sách ba output files đã biết.
3. **@OutputDirectory + DirectoryProperty**, với thư mục chỉ thuộc task đó.
4. **Không**. Nếu reportTitle ảnh hưởng output, phải khai báo @Input/Provider hoặc mô hình tương đương.
5. **Overlap**: Gradle khó phân biệt output ownership, không an toàn cho parallel execution/cache/stale cleanup.
6. **Output caching bị vô hiệu hóa** nếu @OutputFiles chứa FileTree.
7. Ví dụ inputFile.set(producer.flatMap { it.outputFile }) với outputFile là getter annotated @OutputFile.
8. **Không**. UP-TO-DATE và FROM-CACHE khác nhau; task type còn cần đủ điều kiện để cache.
9. **Không**. @OutputDirectory chỉ khai báo; @TaskAction hoặc công cụ được task gọi phải tự viết file.
10. **Không**. Đó là thiết kế incremental input processing qua InputChanges và các annotation input phù hợp.
11. Managed property hỗ trợ lazy configuration, task dependency, đường dẫn linh hoạt; nên khai báo trên task type và gán qua layout.buildDirectory.
12. Vì Provider lấy từ TaskProvider và @OutputFile của producer mang thông tin phụ thuộc đến @InputFile của consumer.

## Tài liệu chính thức để đọc sâu

- [Gradle User Manual — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): các annotation input/output, managed types và task type.
- [Gradle User Manual — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): dấu vết input/output, UP-TO-DATE, validation và inferred dependencies.
- [Gradle User Manual — Creating and Registering Tasks](https://docs.gradle.org/current/userguide/writing_tasks.html): task actions, định nghĩa đầu vào và đầu ra, ví dụ Groovy DSL.
- [Gradle JavaDoc — @OutputFile](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/OutputFile.html): hợp đồng file output đơn.
- [Gradle JavaDoc — @OutputFiles](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/OutputFiles.html): hợp đồng collection output, lưu ý FileTree và caching.
- [Gradle JavaDoc — @OutputDirectory](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/OutputDirectory.html): hợp đồng output directory.
- [Gradle User Manual — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): output riêng, producer/consumer và Provider lazy.
- [Gradle User Manual — Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html): lý do tránh output overlap và phân biệt caching với up-to-date.
- [Gradle User Manual — Custom Tasks](https://docs.gradle.org/current/userguide/custom_tasks.html): incremental task và InputChanges khi muốn xử lý từng input file thay đổi.

**Ghi nhớ:** Chọn @OutputFile cho **một file**, @OutputFiles cho **tập file xác định trước**, @OutputDirectory cho **một cây thư mục**. Dùng RegularFileProperty/ConfigurableFileCollection/DirectoryProperty, khai báo đủ inputs, đặt output paths không chồng nhau, nối producer–consumer bằng Provider và kiểm thử UP-TO-DATE. Annotation đầu ra làm Gradle hiểu **đâu là kết quả của task**, không tự tạo kết quả hoặc bảo đảm caching trong mọi tình huống.