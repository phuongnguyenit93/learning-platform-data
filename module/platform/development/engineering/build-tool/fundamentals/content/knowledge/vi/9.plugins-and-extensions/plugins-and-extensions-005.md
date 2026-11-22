# Chọn cấu hình plugin sẵn có hay viết tác vụ tùy chỉnh

Build tool thường cung cấp plugin để xử lý những công việc phổ biến như biên dịch Java, chạy kiểm thử, đóng gói JAR, tạo tài liệu hoặc kiểm tra chất lượng mã nguồn. Khi một dự án cần thay đổi cách các công việc đó hoạt động, lựa chọn đầu tiên thường là cấu hình plugin đã có. Chỉ khi build cần thực hiện một công việc riêng mà plugin hiện tại không cung cấp, ta mới nên cân nhắc viết task tùy chỉnh.

Quyết định này ảnh hưởng trực tiếp đến độ phức tạp của build, khả năng tái sử dụng, tính ổn định và chi phí bảo trì. Một task tự viết có thể giải quyết yêu cầu rất chính xác, nhưng cũng khiến nhóm phải chịu trách nhiệm về đầu vào, đầu ra, dependency, cache, tương thích Gradle và cách kiểm thử task đó. Ngược lại, plugin sẵn có thường đã xử lý nhiều chi tiết mà dự án không cần tự xây dựng lại.

## 1. Plugin và task trong Gradle có vai trò gì?

**Plugin** là phần mở rộng bổ sung khả năng và quy ước cho build. Một plugin có thể:

- Tạo extension để người dùng khai báo cấu hình ở một nơi có cấu trúc.
- Đăng ký task và nối các task thành quy trình build.
- Tạo source set, dependency configuration hoặc thành phần build.
- Áp dụng quy ước về thư mục, tên artifact và đầu ra.
- Tích hợp với plugin khác để cung cấp một quy trình hoàn chỉnh.

**Task** là một đơn vị công việc trong task graph. Ví dụ, plugin Java tạo các task như `compileJava`, `processResources`, `test` và `jar`. Khi chạy task, Gradle thực thi hành động của nó sau khi các dependency cần thiết đã hoàn thành.

Có thể hình dung mối quan hệ như sau:

```text
Build script
    |
    v
Áp dụng plugin
    |
    +--> Tạo extension / cấu hình mặc định
    |
    +--> Đăng ký task và dependency
    |
    v
Người dùng cấu hình plugin và task
    |
    v
Gradle xây dựng task graph
    |
    v
Thực thi các task cần thiết
```

Thông thường, dự án sử dụng plugin để có một tập hợp khả năng và cấu hình các task do plugin quản lý. Viết một task riêng là cách bổ sung một đơn vị công việc; viết plugin riêng là cách đóng gói cấu hình và task thành một khả năng có thể áp dụng lại.

## 2. Ưu tiên cấu hình plugin sẵn có khi nào?

Hãy tìm hiểu plugin hiện có trước khi tự viết task. Nếu yêu cầu chỉ là thay đổi một tham số, đường dẫn, phiên bản, định dạng hoặc hành vi đã được plugin hỗ trợ, cấu hình plugin thường là lựa chọn phù hợp.

Ví dụ, một dự án Java cần chọn JDK 21. Không cần viết task để tìm `javac` hoặc tự gọi compiler. Plugin Java đã hỗ trợ Java toolchain:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Ở đây, plugin `java` cung cấp mô hình Java và các task liên quan. Khối `java {}` cấu hình toolchain. Build không cần một task mới chỉ để thực hiện lựa chọn phiên bản Java.

Một ví dụ khác là thay đổi tên artifact JAR. Plugin Java đã tạo task `jar`, vì vậy chỉ cần cấu hình task đó:

```groovy
tasks.named('jar', Jar) {
    archiveBaseName = 'catalog-service'
    archiveVersion = '2.4.0'
}
```

Đoạn cấu hình trên sử dụng task `jar` do plugin Java cung cấp. Nó không tạo một task đóng gói thứ hai và không tự sao chép logic đóng gói JAR.

Các trường hợp thường nên dùng cấu hình plugin:

- Chọn phiên bản Java hoặc toolchain.
- Thay đổi source directory hoặc resource directory theo API của plugin.
- Cấu hình dependency, repository hoặc variant.
- Đổi tên, loại hoặc metadata của artifact.
- Bật/tắt tính năng plugin đã hỗ trợ.
- Điều chỉnh test framework, báo cáo kiểm thử hoặc tùy chọn compiler.
- Thay đổi thư mục đầu ra hoặc định dạng mà plugin đã cung cấp thuộc tính cấu hình.

Khi một plugin đã có API cấu hình chính thức cho yêu cầu, dùng API đó giúp build diễn đạt ý định rõ hơn và giữ được các dependency, task graph, cache behavior mà plugin đã thiết kế.

## 3. Cách tìm khả năng cấu hình trước khi viết task

Không nên kết luận plugin không hỗ trợ một yêu cầu chỉ vì chưa thấy thuộc tính ngay trong `build.gradle`. Có thể kiểm tra theo trình tự sau:

### Xác định plugin nào sở hữu công việc

Đọc khối `plugins {}` và các plugin được áp dụng gián tiếp bởi convention plugin. Xác định task hiện tại được tạo bởi plugin nào và loại task tương ứng là gì.

Ví dụ:

```groovy
plugins {
    id 'java'
    id 'application'
}
```

Plugin `java` cung cấp khả năng biên dịch, kiểm thử và đóng gói Java. Plugin `application` bổ sung mô hình ứng dụng có điểm vào và các task liên quan đến chạy hoặc phân phối ứng dụng.

### Tìm extension và task type

Tài liệu plugin thường mô tả extension, thuộc tính, task và cách cấu hình. Với Gradle, có thể xem task graph hoặc danh sách task bằng các lệnh như:

```bash
./gradlew tasks
./gradlew tasks --all
./gradlew help --task jar
```

Trên Windows:

```powershell
.\gradlew.bat tasks
.\gradlew.bat tasks --all
.\gradlew.bat help --task jar
```

Các lệnh này giúp khám phá task và mô tả task. Tài liệu plugin và API của task type vẫn là nơi xác nhận thuộc tính nào được hỗ trợ và ý nghĩa của chúng.

### Kiểm tra API công khai trước khi can thiệp sâu

Ưu tiên extension và property công khai. Tránh sửa trực tiếp trường nội bộ, gọi API chưa được hỗ trợ hoặc phụ thuộc vào tên task nội bộ không có cam kết ổn định. Một cấu hình dựa trên implementation detail có thể hỏng khi nâng cấp plugin dù yêu cầu nghiệp vụ không đổi.

### Tìm plugin chuyên dụng đã có

Nếu yêu cầu thuộc một lĩnh vực phổ biến nhưng plugin hiện tại không xử lý, hãy xem có plugin chuyên dụng phù hợp không. Ví dụ: sinh mã từ OpenAPI, kiểm tra dependency, tạo container image hoặc phân tích chất lượng mã. Một plugin chuyên dụng thường đã đóng gói các task, input/output và tích hợp cần thiết.

Khi chọn plugin bên ngoài, cần cân nhắc mức độ duy trì, tài liệu, tương thích Gradle, giấy phép, quyền truy cập và nguồn phát hành. Không nên thêm plugin chỉ vì nó có tên gần giống yêu cầu; cần xác nhận nó thực sự hỗ trợ hành vi dự án cần.

## 4. Khi nào cần viết task tùy chỉnh?

Task tùy chỉnh phù hợp khi build cần thực hiện một thao tác có ý nghĩa riêng đối với dự án và không được plugin hiện có cung cấp qua cấu hình.

Ví dụ:

- Sinh một tệp metadata nội bộ từ dữ liệu module.
- Kiểm tra một quy ước riêng của repository trước khi đóng gói.
- Chuyển đổi một định dạng dữ liệu đặc thù sang định dạng mà ứng dụng sử dụng.
- Tổng hợp nhiều đầu ra thành một catalog theo quy tắc nghiệp vụ của dự án.
- Tạo báo cáo nội bộ từ các tệp đầu vào đã được khai báo.
- Kiểm tra tính nhất quán giữa các file cấu hình riêng của tổ chức.

Điểm chung là task thực hiện một công việc có đầu vào, đầu ra và kết quả xác định được. Task mới cần có lý do tồn tại rõ ràng, không chỉ là cách viết lại một task đã có.

Ví dụ, dự án muốn tạo `build/generated/source-index.txt`, liệt kê tên các tệp Java trong source directory để phục vụ một bước đóng gói nội bộ. Plugin Java không có thuộc tính cấu hình sẵn để tạo đúng báo cáo riêng này. Ta có thể viết task:

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

abstract class GenerateSourceIndex extends DefaultTask {
    @InputFiles
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract ConfigurableFileCollection getSourceFiles()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        List<String> names = sourceFiles.files
            .findAll { it.isFile() }
            .collect { it.name }
            .sort()

        File output = outputFile.get().asFile
        output.parentFile.mkdirs()
        output.setText(names.join('\n') + '\n', 'UTF-8')
    }
}

tasks.register('generateSourceIndex', GenerateSourceIndex) {
    sourceFiles.from(fileTree('src/main/java') {
        include '**/*.java'
    })
    outputFile.set(layout.buildDirectory.file('generated/source-index.txt'))
}
```

Task này khai báo rõ input file collection và output file. Nó sắp xếp tên tệp trước khi ghi để kết quả ổn định khi thứ tự duyệt file system thay đổi. Đầu ra nằm trong `build/`, không ghi vào source tree.

Đây là ví dụ minh họa một công việc riêng. Trong một dự án lớn, task class nên được đặt trong build logic phù hợp, có kiểm thử và API cấu hình rõ ràng, thay vì lặp lại class trong nhiều build script.

## 5. Phân biệt cấu hình task có sẵn với tạo task mới

Hai đoạn sau có vẻ gần nhau nhưng ý nghĩa khác nhau.

**Cấu hình task đã tồn tại:**

```groovy
tasks.named('jar', Jar) {
    archiveClassifier = 'app'
}
```

Đoạn này lấy task `jar` do plugin Java đăng ký và thay đổi thuộc tính của nó. Task graph vẫn có một task đóng gói JAR theo vai trò đó.

**Đăng ký task mới:**

```groovy
tasks.register('copyApplicationJar', Copy) {
    from(tasks.named('jar').flatMap { it.archiveFile })
    into(layout.buildDirectory.dir('distribution'))
}
```

Đoạn này tạo thêm một task `copyApplicationJar` để sao chép artifact đã được task `jar` tạo. Đây là công việc riêng nên nó có một tên, đầu vào và mục đích riêng.

Nếu mục tiêu chỉ là đổi tên artifact, task sao chép mới là không cần thiết. Nếu mục tiêu là đưa JAR vào một thư mục phân phối khác, task sao chép có thể có ý nghĩa. Hãy đặt tên task theo công việc thực tế và dùng API task provider để nối đầu ra với đầu vào.

## 6. Không dùng task tùy chỉnh để thay thế cấu hình đơn giản

Một lỗi thiết kế thường gặp là viết task gọi trực tiếp công cụ dòng lệnh để làm việc mà plugin đã hỗ trợ.

Ví dụ, tự gọi `javac` bằng `Exec` để biên dịch Java:

```groovy
tasks.register('compileManually', Exec) {
    commandLine 'javac', '-d', 'build/classes', 'src/main/java/App.java'
}
```

Đây là cách làm thiếu nhiều thông tin mà plugin Java đã quản lý: source set, classpath, toolchain, incremental compilation, dependency giữa task, compiler options, annotation processor và các tích hợp khác. Khi dự án lớn lên, nhóm sẽ phải tự bổ sung từng phần và dễ tạo ra một quy trình biên dịch khác với quy ước chuẩn.

Nếu yêu cầu là biên dịch Java, hãy dùng plugin Java và cấu hình task/compiler phù hợp. `Exec` chỉ nên được dùng khi thật sự cần gọi một chương trình bên ngoài mà build model không có API tích hợp thích hợp, và khi đầu vào/đầu ra của lệnh đó được khai báo chính xác.

Tương tự, không nên tự tạo task đóng gói JAR bằng cách zip thư mục class nếu plugin Java đã cung cấp task `jar` và các thuộc tính cấu hình tương ứng. Task tùy chỉnh chỉ hợp lý khi sản phẩm cần tạo có quy tắc khác thực sự.

## 7. Khi nào cần convention plugin hoặc custom plugin?

Một task tùy chỉnh giải quyết một đơn vị công việc. Nếu cùng một cấu hình hoặc nhóm task được lặp lại ở nhiều module, việc sao chép các khối `tasks.register(...)` sẽ làm build script dài và dễ lệch nhau.

Khi logic build cần được tái sử dụng, hãy cân nhắc đóng gói nó thành plugin:

- **Convention plugin:** áp dụng các quy ước và cấu hình thống nhất cho một nhóm project, ví dụ tất cả module Java dùng cùng toolchain, test configuration và quy tắc đóng gói.
- **Custom plugin:** cung cấp một khả năng build mới, có thể gồm extension, task, dependency configuration và tích hợp với plugin khác.

Ví dụ, nếu mười module đều cần tạo source index theo cùng một quy tắc, có thể đặt task type `GenerateSourceIndex` và plugin đăng ký task cho từng module. Người dùng chỉ cần áp dụng plugin:

```groovy
plugins {
    id 'com.example.source-index'
}
```

Plugin chịu trách nhiệm chọn source set, cấu hình output path và nối task vào lifecycle phù hợp. Các module không phải sao chép implementation.

Một dấu hiệu nên tách plugin là khi logic:

- Được dùng ở nhiều project hoặc nhiều repository.
- Có nhiều tùy chọn cấu hình cần một API ổn định.
- Đăng ký một nhóm task có quan hệ với nhau.
- Cần kiểm thử độc lập và versioning.
- Có trách nhiệm build rõ ràng, đủ lớn để tồn tại lâu dài.

Không cần tạo plugin riêng cho một thao tác rất nhỏ chỉ xuất hiện một lần. Có thể bắt đầu bằng task cục bộ, sau đó trích xuất thành convention plugin khi nhu cầu tái sử dụng thực sự xuất hiện.

## 8. Cấu hình plugin và task theo cách an toàn với Gradle

Khi cấu hình task đã tồn tại, ưu tiên API lazy như `tasks.named(...)` thay vì truy cập task eager không cần thiết. Khi đăng ký task mới, ưu tiên `tasks.register(...)` và giữ lại `TaskProvider`.

Ví dụ:

```groovy
def indexTask = tasks.register('generateSourceIndex', GenerateSourceIndex) {
    sourceFiles.from(fileTree('src/main/java') {
        include '**/*.java'
    })
    outputFile.set(layout.buildDirectory.file('generated/source-index.txt'))
}

tasks.named('check') {
    dependsOn(indexTask)
}
```

`tasks.register` đăng ký task theo cơ chế lazy. Task không cần được tạo và cấu hình hoàn chỉnh ngay trong giai đoạn configuration nếu build chưa cần nó. `tasks.named` cũng cho phép cấu hình task hiện có mà không yêu cầu tạo tất cả task ngay lập tức.

Với plugin do bên thứ ba cung cấp, hãy sử dụng task type hoặc extension công khai. Tránh tìm task bằng cách quét tên rồi sửa thuộc tính nội bộ không có cam kết API. Nếu plugin cung cấp provider của output, hãy nối provider đó trực tiếp sang input của task tiêu thụ.

## 9. Khai báo input và output khi viết task tùy chỉnh

Task tùy chỉnh cần mô tả những dữ liệu quyết định kết quả. Đây là điều kiện để Gradle thực hiện up-to-date checking, caching và lập task graph chính xác.

Các annotation thường gặp:

| Annotation | Ý nghĩa |
|---|---|
| `@Input` | Một giá trị đơn giản ảnh hưởng đến kết quả |
| `@InputFile` | Một tệp đầu vào |
| `@InputFiles` | Một tập hợp tệp đầu vào |
| `@InputDirectory` | Một thư mục đầu vào |
| `@Classpath` | Các tệp được sử dụng như classpath |
| `@OutputFile` | Một tệp do task tạo hoặc cập nhật |
| `@OutputDirectory` | Một thư mục đầu ra do task quản lý |
| `@Internal` | Thuộc tính nội bộ, không tham gia fingerprint input/output |
| `@Nested` | Một nhóm thuộc tính có cấu trúc cần được Gradle kiểm tra tiếp |

Ví dụ, nếu task đọc template và một giá trị tên module để sinh tệp, cả template và tên module đều là input. Nếu chỉ khai báo output mà bỏ qua template, Gradle có thể không biết rằng thay đổi template cần làm task chạy lại.

Với input file, cần chọn path sensitivity phù hợp. `PathSensitivity.RELATIVE` thường hữu ích khi vị trí tương đối trong cây input có ý nghĩa nhưng đường dẫn tuyệt đối của workspace không nên làm thay đổi kết quả cache. Nếu đường dẫn tuyệt đối là một phần của ngữ nghĩa, lựa chọn sensitivity phải phản ánh điều đó.

Đầu ra cũng phải đúng với hành vi thực tế. Nếu task ghi nhiều file trong một cây, khai báo output directory mà task thực sự sở hữu. Không khai báo một thư mục cha rộng chứa đầu ra của nhiều task độc lập.

## 10. Tính xác định, idempotency và side effect

Một task tốt nên tạo cùng kết quả khi đầu vào và cấu hình giống nhau. Nếu task phụ thuộc vào thời gian hiện tại, thứ tự duyệt file không ổn định, biến môi trường không khai báo hoặc dữ liệu mạng không được mô hình hóa, build cache và incremental build có thể cho kết quả sai.

Ví dụ, task tạo danh sách file nên sắp xếp danh sách trước khi ghi. Task tạo JSON nên có thứ tự key/record ổn định nếu định dạng cho phép. Task không nên đọc một biến môi trường tùy ý trong `doLast` mà không khai báo nó là input.

**Idempotency** có nghĩa là chạy lại với cùng đầu vào không làm kết quả tích lũy sai lệch. Ví dụ, ghi nối thêm một dòng vào output mỗi lần task chạy có thể tạo dữ liệu lặp. Thông thường, task generator nên tạo lại nội dung từ input và ghi thành kết quả hoàn chỉnh.

Các side effect như gửi request, publish artifact, xóa dữ liệu bên ngoài hoặc cập nhật hệ thống từ xa cần được mô hình hóa rõ. Không nên đưa chúng vào một task được kỳ vọng chạy thường xuyên, có thể được cache hoặc tự động chạy lại mà không có chính sách kiểm soát phù hợp.

## 11. Kiểm thử task và plugin tùy chỉnh

Khi task trở thành một phần của build logic được tái sử dụng, cần kiểm thử hành vi của nó. Có thể dùng Gradle TestKit để chạy build mẫu trong một project tạm và quan sát kết quả.

Những tình huống đáng kiểm tra:

- Task tạo đúng đầu ra khi chạy lần đầu.
- Thay đổi input làm task chạy lại và nội dung output được cập nhật.
- Không thay đổi input thì task có thể được đánh dấu `UP-TO-DATE` khi phù hợp.
- Đầu ra cũ không còn cần thiết được xử lý đúng.
- Task consumer nhận đúng output và có dependency phù hợp.
- Hai task độc lập không ghi chồng đầu ra.
- Cấu hình sai hoặc thiếu input bắt buộc tạo thông báo lỗi rõ ràng.
- Plugin áp dụng được trong project mẫu và không phụ thuộc vào thứ tự cấu hình ngẫu nhiên.

Không nên kiểm thử chỉ bằng cách gọi method nội bộ của task. Cần có ít nhất một kiểm thử qua Gradle build thực tế để xác nhận cách task được đăng ký, cấu hình và thực thi trong task graph.

## 12. Cân nhắc chi phí bảo trì và tương thích

Trước khi tự viết task, hãy cân nhắc ai sẽ duy trì nó và trong bao lâu. Task đơn giản có thể nhanh chóng trở thành một phần quan trọng của pipeline phát hành. Khi đó, cần theo dõi:

- API Gradle mà task sử dụng.
- Phiên bản Gradle tối thiểu được hỗ trợ.
- Tương thích với configuration cache nếu dự án yêu cầu.
- Tương thích với build cache và parallel execution.
- Tính đúng đắn của input/output declaration.
- Khả năng chạy trên Windows, Linux và macOS nếu repository hỗ trợ nhiều hệ điều hành.
- Cách phát hành và nâng cấp plugin nếu logic được chia sẻ.

Task viết bằng `doLast` có thể phù hợp với thao tác nhỏ, cục bộ và ít cần tái sử dụng. Khi logic lớn hơn, nên dùng task type có property được khai báo rõ, tách implementation khỏi build script và kiểm thử bằng TestKit.

Nếu plugin hiện có hỗ trợ yêu cầu nhưng API cấu hình chưa rõ, hãy đọc tài liệu hoặc kiểm tra implementation công khai trước khi viết task thay thế. Việc tự tạo task có thể làm mất tích hợp với task graph mà plugin đã cung cấp.

## 13. Maven: cấu hình plugin hay viết Mojo riêng?

Maven cũng có cùng lựa chọn ở cấp khái niệm. Trước tiên, cấu hình plugin và goal có sẵn trong `pom.xml`. Ví dụ, Maven Compiler Plugin có thể được cấu hình để chọn release Java:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>21</release>
    </configuration>
</plugin>
```

Nếu yêu cầu là biên dịch theo Java 21, cấu hình goal/plugin đã có là đủ. Không cần viết Maven plugin riêng để gọi `javac`.

Nếu dự án cần một thao tác build đặc thù, có thể viết Maven plugin với một Mojo riêng. Mojo là đơn vị thực thi của Maven plugin, tương tự vai trò một goal. Mojo cần khai báo parameter, input/output và phase phù hợp. Nếu logic được dùng ở nhiều module hoặc nhiều dự án, đóng gói nó thành plugin giúp tái sử dụng và versioning.

Dù dùng Gradle hay Maven, quyết định vẫn dựa trên câu hỏi: yêu cầu đã được plugin hỗ trợ qua cấu hình chưa, hay dự án thực sự cần một công việc mới?

## 14. Quy trình ra quyết định

Có thể dùng quy trình sau trước khi thêm task hoặc plugin:

```text
Xác định yêu cầu build
        |
        v
Plugin hiện tại có hỗ trợ qua extension/property?
        |
   +----+----+
   |         |
  Có        Không
   |         |
   v         v
Cấu hình    Có plugin chuyên dụng phù hợp?
plugin          |
           +----+----+
           |         |
          Có        Không
           |         |
           v         v
       Áp dụng     Có cần một thao tác build riêng?
       plugin            |
                  +------+------+
                  |             |
                 Không         Có
                  |             |
                  v             v
          Xem lại yêu cầu    Viết task tùy chỉnh
                                |
                                v
                      Logic có cần tái sử dụng?
                                |
                         +------+------+
                         |             |
                        Không         Có
                         |             |
                         v             v
                    Task cục bộ   Convention/custom plugin
```

Đây là hướng dẫn lựa chọn, không phải quy tắc máy móc. Có thể có plugin chuyên dụng nhưng không phù hợp về bảo trì, bảo mật hoặc tương thích. Cũng có thể yêu cầu cần nhiều task riêng rồi được đóng gói thành plugin. Điều quan trọng là xác định rõ phạm vi và trách nhiệm trước khi triển khai.

## 15. Bảng so sánh các lựa chọn

| Lựa chọn | Khi phù hợp | Ưu điểm | Chi phí cần cân nhắc |
|---|---|---|---|
| Cấu hình plugin sẵn có | Plugin đã hỗ trợ hành vi cần thiết | Ít code, tận dụng task graph và tích hợp hiện có | Cần hiểu đúng API và giới hạn plugin |
| Dùng plugin chuyên dụng | Công việc phổ biến có plugin được duy trì tốt | Không phải tự xây dựng toàn bộ workflow | Thêm dependency plugin và phụ thuộc vào vòng đời của nó |
| Task tùy chỉnh cục bộ | Một thao tác riêng, phạm vi một project | Đúng nhu cầu, có thể triển khai nhanh | Nhóm phải duy trì logic và input/output |
| Convention plugin | Quy tắc build dùng lại trong nhiều module | Cấu hình nhất quán, giảm sao chép | Cần thiết kế API, versioning và kiểm thử |
| Custom plugin đầy đủ | Một khả năng build mới có nhiều task/extension | Đóng gói trách nhiệm rõ, tái sử dụng rộng | Chi phí phát triển và tương thích cao hơn |

## 16. Ví dụ quyết định trong một dự án Java

Giả sử dự án có ba yêu cầu:

**Yêu cầu A: đổi phiên bản Java sang 21.** Plugin Java hỗ trợ toolchain. Chọn cấu hình plugin, không viết task mới.

**Yêu cầu B: đổi tên file JAR và thêm classifier `all`.** Nếu task/plugin đóng gói hiện có hỗ trợ các thuộc tính cần thiết, hãy cấu hình task đó hoặc dùng plugin đóng gói phù hợp. Không tạo task JAR mới chỉ để thay đổi tên.

**Yêu cầu C: tạo tệp `module-catalog.json` từ metadata của nhiều module theo schema nội bộ.** Đây là công việc riêng của repository. Mỗi producer nên tạo metadata đầu ra riêng; một task tổng hợp đọc các đầu ra đó, kiểm tra schema, sắp xếp dữ liệu và tạo `module-catalog.json`. Nếu nhiều module dùng cùng logic, đóng gói task và quy tắc cấu hình vào convention plugin.

Ba yêu cầu có vẻ đều liên quan đến build nhưng thuộc ba mức khác nhau: cấu hình tính năng có sẵn, cấu hình task có sẵn và tạo công việc mới. Phân biệt đúng mức giúp tránh thêm code không cần thiết và giữ task graph dễ hiểu.

## 17. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Có thể dùng task tùy chỉnh cho mọi thay đổi build | Thay đổi thuộc tính mà plugin đã hỗ trợ nên được cấu hình qua API của plugin. |
| Plugin và task là hai cách gọi cho cùng một thứ | Plugin bổ sung khả năng/quy ước; task là đơn vị công việc trong task graph. |
| Mỗi yêu cầu mới đều cần một plugin riêng | Một thao tác nhỏ có thể chỉ cần task; plugin phù hợp khi cần đóng gói và tái sử dụng logic. |
| `tasks.named` tạo task mới | Nó tham chiếu task đã được đăng ký để cấu hình hoặc nối dependency. |
| `tasks.register` chạy task ngay lập tức | Nó đăng ký task theo cơ chế lazy; task chỉ thực thi khi được đưa vào task graph. |
| Gọi `Exec` là cách đơn giản thay thế plugin | Lệnh ngoài cần khai báo input/output và không tự có đầy đủ tích hợp của plugin chuyên dụng. |
| Thêm `dependsOn` là đủ để task đúng | Dependency chỉ mô tả quan hệ thực thi; task vẫn phải có input/output và hành vi chính xác. |
| Task chạy thành công một lần nghĩa là đã an toàn | Cần xét incremental build, cache, parallel execution, môi trường khác và lỗi giữa chừng. |

## 18. Những câu hỏi cần trả lời trước khi viết task

Trước khi tạo một task mới, hãy mô tả rõ:

1. **Công việc:** task tạo ra giá trị gì cho quy trình build?
2. **Khả năng hiện có:** plugin nào đang sở hữu công việc liên quan và API nào đã có?
3. **Input:** dữ liệu và cấu hình nào ảnh hưởng đến kết quả?
4. **Output:** task sở hữu chính xác tệp hoặc thư mục nào?
5. **Dependency:** task cần dữ liệu từ task nào và ai tiêu thụ đầu ra của nó?
6. **Tính xác định:** cùng đầu vào có tạo cùng đầu ra không?
7. **Phạm vi tái sử dụng:** chỉ một project, nhiều module hay nhiều repository?
8. **Bảo trì:** ai chịu trách nhiệm tương thích Gradle/Maven và nâng cấp plugin?
9. **Kiểm thử:** làm sao xác nhận task chạy đúng, incremental và trong task graph thật?

Nếu chưa xác định được input/output hoặc không giải thích được vì sao plugin hiện có không đáp ứng yêu cầu, chưa nên bắt đầu viết task. Làm rõ hợp đồng trước sẽ giúp implementation nhỏ hơn và tránh tạo ra một đường build song song khó bảo trì.

## 19. Kết luận lựa chọn trong thực tế

Khi build cần thay đổi một khả năng đã được plugin cung cấp, hãy cấu hình extension hoặc task mà plugin sở hữu. Khi build cần một thao tác riêng có input/output xác định, hãy viết một task tùy chỉnh. Khi thao tác đó hoặc một nhóm quy ước cần được dùng lại ở nhiều module, hãy đóng gói chúng thành convention plugin hoặc custom plugin.

Lựa chọn tốt là lựa chọn giữ được ý nghĩa công việc rõ ràng, khai báo đúng dữ liệu mà task sử dụng và tạo ra, tận dụng được tích hợp của build tool, đồng thời có chi phí bảo trì phù hợp với phạm vi sử dụng. Plugin sẵn có giảm lượng logic phải tự quản lý; task tùy chỉnh mở rộng build khi có yêu cầu thật sự riêng; plugin riêng giúp những mở rộng đó trở thành quy ước dùng chung khi cần thiết.
