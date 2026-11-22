# Tạo mã nguồn và nối đầu ra generator vào source set trong Gradle Java

## 1. Mục tiêu và tình huống sử dụng

Trong dự án Java, không phải toàn bộ file **.java** đều do lập trình viên viết tay. Nhiều file có thể được sinh tự động từ **schema**, **OpenAPI specification**, **Protocol Buffers**, **mẫu template**, cấu hình tính năng, mã định danh lỗi hoặc thông tin API được quản lý ở một nguồn dữ liệu khác. Nếu code generator được tích hợp đúng vào Gradle, việc biên dịch sẽ tự chạy generator khi cần, nhận các file mới như source Java, đồng thời tận dụng kiểm tra **UP-TO-DATE**, **build cache** và dependency graph.

Ngược lại, nếu generator tạo file trong một task nhưng **compileJava** không biết task đó, bạn có thể gặp lỗi **cannot find symbol** khi chạy từ môi trường sạch; còn ở máy developer thì build “tình cờ” thành công vì có generated files cũ. Đây là dấu hiệu quan hệ **producer → consumer** chưa được khai báo đúng, không phải lỗi của Java compiler.

Bài học thuộc nhóm **Biên dịch và tài nguyên**, giải quyết trực tiếp câu hỏi: **Làm thế nào tạo mã nguồn và nối đầu ra của generator vào source set để Gradle tự xây đúng task graph, biên dịch và đóng gói?**

Sau bài học, bạn sẽ có thể:

1. Phân biệt **file dữ liệu đầu vào**, **task sinh mã**, **thư mục generated Java source**, **source set** và **JavaCompile task**.
2. Khai báo generator task với **@InputFile**, **@PathSensitive**, **@OutputDirectory**, **@TaskAction** và **Property/Provider**.
3. Đăng ký task lười bằng **tasks.register** và dùng **TaskProvider** nối output vào **sourceSets.main.java.srcDir(...)**.
4. Hiểu tại sao cách nối qua TaskProvider có thể mang theo **task dependency** và tránh lỗi implicit dependency.
5. Biết khi nào **compileJava.dependsOn(generateTask)** cần thiết, khi nào nên ưu tiên wiring dữ liệu thay vì nối thứ tự thủ công.
6. Viết và chạy demo **Java 17** trong đó **config/answer.txt** chứa **42**, generator tạo **GeneratedAnswer.java**, và ứng dụng in **ANSWER=42**.
7. Quan sát việc thay giá trị input thành **73** khiến generator và compiler cập nhật output đúng.
8. Phân biệt generated source **main**, **test**, **integrationTest**, generated resources và mã do **annotation processor** sinh.
9. Kiểm tra nội dung JAR, cây task, lỗi configuration cache và cơ chế incremental/build cache.
10. Xử lý các antipattern: ghi vào **src/main/java**, chỉ thêm đường dẫn string, trỏ vào file .java thay vì source root, dùng **fileTree** mất metadata dependency, và nhiều generator cùng ghi một output directory.

## 2. Mô hình: một task tạo dữ liệu, task khác sử dụng

### 2.1. Pipeline lý tưởng

~~~text
config/answer.txt
      |
      | @InputFile
      v
generateAnswerSource  (custom generator task)
      |
      | @OutputDirectory
      v
build/generated/sources/answer/main/java/
    demo/generated/GeneratedAnswer.java
      |
      | sourceSets.main.java.srcDir(generateAnswerSource)
      v
sourceSets.main.java
      |
      v
compileJava
      |
      v
build/classes/java/main/
    demo/generated/GeneratedAnswer.class
      |
      +------> run (Main sử dụng GeneratedAnswer)
      |
      +------> jar (JAR chính có GeneratedAnswer.class)
~~~

Mối liên hệ cần khai báo **không chỉ là thứ tự**. Gradle phải biết:

- **Generator đọc cái gì?** Ví dụ một file cấu hình, schema hoặc templates.
- **Generator xuất cái gì?** Một thư mục nguồn Java có cấu trúc package.
- **Consumer dùng output qua đâu?** SourceDirectorySet **main.java**, **test.java** hoặc source set khác.
- **Task nào tạo output đó?** Metadata của TaskProvider hoặc Provider xuất phát từ task producer.
- **Thay đổi nào làm output phải sinh lại?** Các input file, compiler settings, generator version và tham số nghiệp vụ.

Khi quan hệ dữ liệu được mô hình hóa bằng Gradle API, task **compileJava** có thể được thực thi sau generator do **implicit dependency**. Khi input không đổi và output vẫn hợp lệ, Gradle có thể bỏ qua việc chạy lại generator.

### 2.2. Chỗ nào là task, chỗ nào là file?

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Input source data** | Nguồn sự thật cho quá trình sinh | config/answer.txt, schema.json, openapi.yaml |
| **Generator task** | Đọc input, tạo source files | generateAnswerSource |
| **TaskProvider** | Tham chiếu lazy và dependency metadata của generator | tasks.register(...) |
| **Generated source root** | Thư mục gốc chứa các Java packages | build/generated/sources/answer/main/java |
| **Generated Java file** | Một file .java trong source root | demo/generated/GeneratedAnswer.java |
| **SourceSet** | Nhóm source/resources và classpaths của Java plugin | sourceSets.main |
| **SourceDirectorySet** | Danh sách thư mục Java source mà compiler đọc | sourceSets.main.java |
| **JavaCompile** | Biên dịch mọi nguồn Java được cấu hình | compileJava |
| **Class output** | .class files sau khi compile | build/classes/java/main |
| **JAR task** | Đóng gói compiled main output | jar |

**Chú ý:** Java compiler cần nhìn thấy **source root** chứa phần đầu của đường dẫn package. Nếu generated file có package **demo.generated**, phải nằm ở một source root bên trên **demo/generated/**. Không thêm riêng đường dẫn đến **GeneratedAnswer.java** như thể nó là root chứa các package khác.

## 3. Source set và source directories trong Java plugin

Java plugin mặc định có:

~~~text
src/main/java
src/main/resources
src/test/java
src/test/resources
~~~

Cấu hình source set **main**:

~~~groovy
plugins {
    id 'java'
}

sourceSets {
    main {
        java.srcDir('src/extra/java')
    }
}
~~~

Dòng **java.srcDir(...)** thêm một source directory ngoài đường dẫn mặc định. Nó **không xóa** **src/main/java**.

Ngược lại:

~~~groovy
sourceSets {
    main {
        java.setSrcDirs(['src/extra/java'])
    }
}
~~~

là cách **thay thế** toàn bộ danh sách thư mục Java source bằng một danh sách mới. Nếu lỡ dùng **setSrcDirs** thay **srcDir** khi chỉ muốn thêm generated sources, chương trình handwritten có thể không còn được biên dịch.

### 3.1. Bản thân thư mục tĩnh không nói ai tạo ra nó

Ví dụ:

~~~groovy
sourceSets.main.java.srcDir(
        "$buildDir/generated/sources/answer/main/java")
~~~

có thể khiến Java plugin tìm **.java** tại đường dẫn này **nếu chúng đã tồn tại**. Tuy nhiên, một chuỗi đường dẫn đơn thuần **không gắn với generator task**, nên chưa giúp Gradle biết task nào phải chạy để tạo file.

Đó là lý do **build sạch thất bại nhưng build lần hai đôi khi thành công**: bạn đã mô tả đường dẫn source nhưng thiếu provenance của nó. Cách tốt hơn là nối **TaskProvider** (hoặc một provider output có liên kết task hợp lệ) vào **SourceDirectorySet**.

### 3.2. Không viết generated sources vào source tree

Thư mục nên dùng:

~~~text
build/generated/sources/<generator-name>/<source-set>/java
~~~

Ví dụ:

~~~text
build/generated/sources/answer/main/java
~~~

Nên tránh:

~~~text
src/main/java/demo/generated/GeneratedAnswer.java
~~~

nếu file đó được generator ghi tự động. Ghi output vào source tree dễ tạo:

- File thay đổi liên tục trong Git.
- Merge conflict giữa các developer/CI.
- IDE nhận generated source như file viết tay.
- Lỗi stale source khi schema đổi và generator không xóa file cũ.
- Nhiều task cùng ghi/đọc thư mục không có ownership rõ.
- Khó phân biệt source gốc với output của build.

Generated output nên nằm dưới **layout.buildDirectory** để việc **clean** và tính toán output của Gradle nhất quán hơn.

## 4. Chọn mô hình generator task

### 4.1. Task kiểu riêng với managed properties

Một custom task có thể định nghĩa:

~~~groovy
@InputFile
@PathSensitive(PathSensitivity.RELATIVE)
abstract RegularFileProperty getSpecFile()

@OutputDirectory
abstract DirectoryProperty getGeneratedSourcesDir()
~~~

Các annotation giải thích rõ:

- **@InputFile:** file dữ liệu mà generator đọc; Gradle kiểm tra file có tồn tại và theo dõi nội dung.
- **@PathSensitive(PathSensitivity.RELATIVE):** fingerprint đường dẫn đầu vào theo đường dẫn tương đối, thuận lợi hơn khi build di chuyển thư mục.
- **@OutputDirectory:** một directory chứa file Java do generator sở hữu.
- **RegularFileProperty/DirectoryProperty:** những property được Gradle quản lý, có thể nhận Provider thay vì hardcode đường dẫn.
- **@TaskAction:** method chạy khi task thực sự được chọn và cần làm việc.

Đoạn trên chỉ là **minh họa getter cần đặt trong một custom task class**. Mục 8 cung cấp một **build.gradle hoàn chỉnh** với các imports và logic sinh file.

### 4.2. Vì sao DirectoryProperty thay vì String?

Ví dụ:

~~~groovy
generatedSourcesDir.set(
        layout.buildDirectory.dir(
            'generated/sources/answer/main/java'))
~~~

Giá trị xuất phát từ **ProjectLayout.buildDirectory** nên nếu root build thay đổi build directory hợp lệ, đường dẫn được theo dõi qua Provider. Nó còn thể hiện đúng **kiểu thư mục**, thay vì một chuỗi có thể là thư mục hoặc file.

Tránh lấy **layout.buildDirectory.get().asFile** quá sớm ở configuration chỉ để ghép các chuỗi path bằng tay. Nếu người dùng đổi buildDirectory hoặc dùng configuration cache, cách dùng Provider phù hợp hơn.

### 4.3. Đầu vào phải đại diện cho mọi thứ quyết định output

Nếu generator đọc **schema.json** và **template.tpl**, hãy khai báo cả hai là inputs. Nếu output còn phụ thuộc vào **packageName**, **generatorVersion** hoặc **languageTarget**, khai báo các input values tương ứng bằng **@Input** hoặc task properties hỗ trợ. Nếu generator dùng external executable, cần mô hình hóa tool classpath/version và args.

**Không khai báo mỗi @OutputDirectory rồi coi output là cacheable**: Gradle sẽ không biết khi nào phải sinh lại khi schema hoặc template thay đổi.

## 5. Nối TaskProvider vào sourceSets.main.java

Mô hình cần nhớ:

~~~groovy
def generateAnswerSource = tasks.register(
        'generateAnswerSource',
        GenerateAnswerSource) {
    specFile.set(layout.projectDirectory.file('config/answer.txt'))
    generatedSourcesDir.set(
            layout.buildDirectory.dir(
                'generated/sources/answer/main/java'))
}

sourceSets.main.java.srcDir(generateAnswerSource)
~~~

**GenerateAnswerSource** là custom task class được định nghĩa đầy đủ trong ví dụ ở mục 8. Ở đây tập trung vào cách wiring.

**TaskProvider** là một tham chiếu tới task đã được đăng ký, không yêu cầu Gradle hiện thực mọi task ngay tại cấu hình. Khi dùng provider của task trong API file collection/source directories hỗ trợ task outputs, Gradle nhận được:

1. **Đường dẫn output mà source set phải đọc.**
2. **Quan hệ built-by**: output đó do task nào tạo.

Vì vậy **compileJava** có thể nhận ra nó phải chạy **generateAnswerSource** trước khi biên dịch. Đây là **data dependency**, không chỉ một câu lệnh “chạy A trước B” thiếu liên kết file.

### 5.1. Tại sao task cần output directory rõ ràng?

**srcDir(taskProvider)** sử dụng output file collection của task. Nếu task có duy nhất một **@OutputDirectory** chứa Java source, Gradle có thể dùng nó làm source root phù hợp.

Nếu task có **nhiều outputs** (Java files, generated resources, metadata), **không truyền thẳng toàn bộ task outputs vào java.srcDir** vì compiler có thể quét nhầm resources hoặc thư mục khác. Khi đó lấy một output property cụ thể từ provider và bảo đảm giữ task dependency metadata; ví dụ:

~~~groovy
sourceSets.main.java.srcDir(
        generateTask.flatMap { it.generatedSourcesDir })
~~~

**Đây là đoạn minh họa**: nó yêu cầu **generateTask** cung cấp một DirectoryProperty tên **generatedSourcesDir** được đánh dấu **@OutputDirectory**, và API wiring phải giữ provider liên kết producer task. Với trường hợp một output source directory duy nhất, **srcDir(generateTask)** là mô hình đơn giản và minh bạch nhất.

### 5.2. Chỉ dependsOn chưa diễn đạt đầy đủ dữ liệu

Một workaround thường thấy:

~~~groovy
tasks.named('compileJava') {
    dependsOn(tasks.named('generateAnswerSource'))
}

sourceSets.main.java.srcDir(
        layout.buildDirectory.dir(
            'generated/sources/answer/main/java'))
~~~

Cách này **có thể hoạt động** nếu đường dẫn và task thực sự khớp. Nhưng có hai nguồn cấu hình độc lập:

- Task cần chạy trước được khai báo ở **dependsOn**.
- Thư mục source được khai báo bằng path tĩnh.

Nếu đổi output directory của task mà quên đổi source directory, build vẫn chạy generator nhưng compiler đọc sai chỗ. **Wiring từ task provider hoặc output provider duy nhất** giúp giảm nguy cơ lệch.

**dependsOn** vẫn hữu ích khi cần thứ tự nghiệp vụ, khi plugin/API không truyền task dependency metadata, hoặc khi bạn phải nối task thủ công vì hệ thống generator bên ngoài. Tuy nhiên, ưu tiên **đầu ra producer → đầu vào consumer** khi có thể.

### 5.3. shouldRunAfter không thay dependsOn

Nếu viết:

~~~groovy
tasks.named('compileJava') {
    shouldRunAfter(tasks.named('generateAnswerSource'))
}
~~~

thì Gradle **không tự thêm generator vào task graph** khi chạy compileJava; nó chỉ gợi ý thứ tự **nếu cả hai task đều được chọn**. Không dùng shouldRunAfter/mustRunAfter như một cơ chế producer-consumer dependency.

## 6. Output directory ownership và tính đúng đắn của task graph

### 6.1. Một task nên sở hữu một vùng output riêng

Lý tưởng:

~~~text
build/generated/sources/answer/main/java     <- generateAnswerSource
build/generated/sources/openapi/main/java    <- generateOpenApiSource
build/generated/sources/protobuf/main/java   <- generateProtoSource
~~~

Không nên cho ba generator độc lập cùng ghi vào:

~~~text
build/generated/sources/main/java
~~~

với output directory trùng nhau, vì:

- Một task có thể ghi đè file của task khác.
- UP-TO-DATE/cache khó xác định file nào thuộc producer nào.
- Parallel execution có thể gặp overlapping outputs.
- Việc xóa stale files của một generator có thể xóa output của generator khác.
- Gradle có thể phát hiện và báo vấn đề ownership hoặc giảm tối ưu.

**Mỗi task sở hữu output riêng** rồi thêm nhiều output providers vào source set:

~~~groovy
sourceSets.main.java.srcDir(generateApi)
sourceSets.main.java.srcDir(generateMessages)
~~~

Hai dòng chỉ là **minh họa**, yêu cầu đã đăng ký hai task phù hợp và đầu ra là Java source directories.

### 6.2. Không đặt output trùng compiled classes

Source generator tạo **.java**:

~~~text
build/generated/sources/...
~~~

JavaCompile tạo **.class**:

~~~text
build/classes/java/main/...
~~~

Không cho generator ghi file **.java** vào **build/classes/java/main** hoặc vào output directory của task compileJava. Compiler output và source generation là hai bước/owners khác nhau.

### 6.3. Không đưa source file vào root sai

Sai:

~~~text
source root = build/generated/sources/answer/main/java/demo/generated
file = GeneratedAnswer.java
package demo.generated;
~~~

Nếu dùng thư mục **demo/generated** làm source root, javac/IDE có thể hiển thị cấu trúc package sai. Đúng:

~~~text
source root = build/generated/sources/answer/main/java
file = demo/generated/GeneratedAnswer.java
package demo.generated;
~~~

## 7. Một ví dụ sai và cách sửa

### 7.1. Antipattern: ghi generated Java vào src/main/java

~~~groovy
tasks.register('generateAnswerSource') {
    doLast {
        file('src/main/java/demo/generated').mkdirs()
        file('src/main/java/demo/generated/GeneratedAnswer.java')
                .text = 'package demo.generated; class GeneratedAnswer {}'
    }
}
~~~

**Đây là đoạn cố ý minh họa cách làm không nên dùng**, chưa phải chương trình đầy đủ. Nó có những vấn đề:

- Không khai báo input/output của generator task.
- Chỉnh sửa source tree làm thay đổi file Git-tracked/untracked.
- Không bảo đảm compileJava phụ thuộc generator.
- File có thể còn lại sau **clean**.
- Không có encoding và API source ổn định.

### 7.2. Antipattern: chỉ thêm một chuỗi path

~~~groovy
sourceSets.main.java.srcDir(
        'build/generated/sources/answer/main/java')
~~~

Nếu generator là task khác mà chưa được nối, lệnh **./gradlew clean compileJava** có thể không chạy generator trước compiler. Build cũ có source tồn tại khiến lỗi khó tái hiện.

### 7.3. Cách nên làm: task output có provenance

~~~groovy
def generator = tasks.register(
        'generateAnswerSource',
        GenerateAnswerSource) {
    specFile.set(layout.projectDirectory.file('config/answer.txt'))
    generatedSourcesDir.set(
            layout.buildDirectory.dir(
                'generated/sources/answer/main/java'))
}

sourceSets.main.java.srcDir(generator)
~~~

Với **@InputFile**, **@OutputDirectory**, task class rõ và wiring TaskProvider, Gradle hiểu generator là producer. Kết quả của mã nguồn generated trở thành một phần compilation inputs và được JavaCompile quản lý tự nhiên.

## 8. Ví dụ Gradle + Java 17 hoàn chỉnh, không cần thư viện bên ngoài

Ví dụ này chỉ dùng **application** core plugin và Java standard library. Đầu vào là một file text chứa số nguyên; generator tạo một Java class có method **value()**. Ứng dụng Java gọi method đó.

**Điểm kiểm chứng:** chạy **./gradlew clean run** trên project mới vẫn thành công dù trước đó không có **GeneratedAnswer.java**. Generator được tự động đưa vào task graph nhờ **sourceSets.main.java.srcDir(generateAnswerSource)**.

### 8.1. Cây thư mục

~~~text
generated-source-lab/
├── settings.gradle
├── build.gradle
├── gradlew                      # sinh bằng Gradle Wrapper
├── gradlew.bat                  # sinh bằng Gradle Wrapper
├── gradle/wrapper/...           # sinh bằng Gradle Wrapper
├── config/
│   └── answer.txt
└── src/
    └── main/
        └── java/
            └── demo/
                └── app/
                    └── Main.java
~~~

**Không** tạo thủ công **src/main/java/demo/generated/GeneratedAnswer.java**. File đó được generator tạo ở **build/generated/sources/answer/main/java/demo/generated/GeneratedAnswer.java**.

Nếu repository chưa có Wrapper, dùng một Gradle CLI đã cài tương thích để chạy **gradle wrapper** một lần, rồi commit các Wrapper files. Các bước còn lại dùng **./gradlew** (Unix) hoặc **.\gradlew.bat** (Windows). Cần Gradle version phù hợp với JDK chạy Gradle và Java 17 toolchain sẵn có hoặc được cấp phát đúng.

### 8.2. settings.gradle

~~~groovy
rootProject.name = 'generated-source-lab'
~~~

Ví dụ không tải external Maven dependencies nên không cần thêm **repositories** block. Core plugin **application** có trong Gradle distribution.

### 8.3. config/answer.txt

Tệp UTF-8 này chỉ chứa số nguyên và dấu xuống dòng cuối:

~~~text
42
~~~

Generator đọc nội dung, trim khoảng trắng và kiểm tra bằng **Integer.parseInt**. Cấu hình là nguồn sự thật: thay **42** bằng **73** thì source generated cũng phải đổi.

### 8.4. build.gradle — toàn bộ cấu hình có thể dùng

~~~groovy
import java.nio.charset.StandardCharsets
import java.nio.file.Files

import org.gradle.api.DefaultTask
import org.gradle.api.GradleException
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

plugins {
    id 'application'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.app.Main'
}

@CacheableTask
abstract class GenerateAnswerSource extends DefaultTask {

    @InputFile
    @PathSensitive(PathSensitivity.RELATIVE)
    abstract RegularFileProperty getSpecFile()

    @OutputDirectory
    abstract DirectoryProperty getGeneratedSourcesDir()

    @TaskAction
    void generate() {
        String raw = Files.readString(
                specFile.get().asFile.toPath(),
                StandardCharsets.UTF_8).trim()

        int number
        try {
            number = Integer.parseInt(raw)
        } catch (NumberFormatException ex) {
            throw new GradleException(
                    'config/answer.txt phải chứa số nguyên int', ex)
        }

        File generatedFile = generatedSourcesDir
                .file('demo/generated/GeneratedAnswer.java')
                .get()
                .asFile

        Files.createDirectories(
                generatedFile.parentFile.toPath())

        String javaSource =
                'package demo.generated;\n' +
                'public final class GeneratedAnswer {\n' +
                '  private GeneratedAnswer() {}\n' +
                '  public static int value() { return ' +
                number + '; }\n' +
                '}\n'

        Files.writeString(
                generatedFile.toPath(),
                javaSource,
                StandardCharsets.UTF_8)
    }
}

def generateAnswerSource = tasks.register(
        'generateAnswerSource',
        GenerateAnswerSource) {

    group = 'code generation'
    description = 'Tạo GeneratedAnswer.java từ config/answer.txt'

    specFile.set(
            layout.projectDirectory.file('config/answer.txt'))

    generatedSourcesDir.set(
            layout.buildDirectory.dir(
                    'generated/sources/answer/main/java'))
}

// Quan trọng: thêm task producer, không chỉ một path string.
sourceSets.main.java.srcDir(generateAnswerSource)
~~~

Đây là **toàn bộ build.gradle** cho project demo. Chỉ có một output directory của generator; vì vậy truyền **TaskProvider** trực tiếp cho **srcDir** là rõ ràng và thích hợp.

### 8.5. Giải thích custom task line by line

**@CacheableTask:** khai báo rằng task được thiết kế để có thể lưu/tái sử dụng output từ build cache nếu input và các điều kiện caching của Gradle hợp lệ. Đây không phải lời hứa rằng task luôn có cache hit; local up-to-date checks, task implementation tracking và build cache policy vẫn quyết định outcome.

**@InputFile + @PathSensitive(RELATIVE):** Gradle biết file **config/answer.txt** là input và theo dõi thay đổi nội dung. Việc đặt file path qua **layout.projectDirectory.file(...)** giúp cấu hình nguồn gốc rõ ràng.

**@OutputDirectory:** Gradle biết task sở hữu thư mục **build/generated/sources/answer/main/java**. Không khai báo một file generated trong source tree là output.

**@TaskAction:** chỉ khi Gradle thực sự chạy action, code mới đọc file, kiểm tra số, tạo thư mục cha và ghi Java source. Không đọc/ghi file này tại lúc Gradle cấu hình script.

**Integer.parseInt:** chấp nhận các số nguyên nằm trong phạm vi Java **int**. Nếu input không hợp lệ hoặc vượt phạm vi, task ném **GradleException** với thông báo phù hợp; không tự sinh mã sai.

**Files.writeString(..., UTF_8):** mã generated chỉ có chữ ASCII nên không phụ thuộc vào default system encoding. Khi generated Java có tiếng Việt, quy định encoding tường minh vẫn là lựa chọn đúng.

**GeneratedAnswer:** class có private constructor và một **public static int value()**. Tên package/đường dẫn generated file khớp chính xác.

**sourceSets.main.java.srcDir(generateAnswerSource):** liên kết output có metadata của generator với Java sources của main; từ đó khi compiler cần source, Gradle có thể đưa generator vào task graph.

### 8.6. src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.generated.GeneratedAnswer;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("ANSWER=" + GeneratedAnswer.value());
    }
}
~~~

**GeneratedAnswer** chưa tồn tại trong source tree của project. Việc **compileJava** thành công là bằng chứng rằng generator output đã có trên source set khi compilation diễn ra. File generated được compiler xử lý như các file Java khác.

### 8.7. Lệnh chạy Gradle trên Linux/macOS

~~~bash
./gradlew --version
./gradlew tasks --all
./gradlew compileJava --dry-run
./gradlew clean compileJava
./gradlew -q run
./gradlew jar
~~~

Trong output **compileJava --dry-run** trên một build mới, bạn sẽ thấy generator được lập lịch trước **compileJava**, dù tên/chi tiết task graph có thể khác tùy Gradle version.

Khi chạy **clean compileJava**, Gradle phải sinh file:

~~~text
build/generated/sources/answer/main/java/
    demo/generated/GeneratedAnswer.java
~~~

Và compiled class:

~~~text
build/classes/java/main/
    demo/generated/GeneratedAnswer.class
~~~

Dòng stdout **chính xác của Java Main** khi gọi **./gradlew -q run** với input **42**:

~~~text
ANSWER=42
~~~

Gradle có thể in thêm warnings hoặc log của daemon; đoạn trên chỉ mô tả dòng do Java source in.

### 8.8. Lệnh trên Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat tasks --all
.\gradlew.bat compileJava --dry-run
.\gradlew.bat clean compileJava
.\gradlew.bat -q run
.\gradlew.bat jar
~~~

Đọc file Java generated:

~~~powershell
Get-Content build\generated\sources\answer\main\java\demo\generated\GeneratedAnswer.java
~~~

Trên Linux/macOS:

~~~bash
cat build/generated/sources/answer/main/java/demo/generated/GeneratedAnswer.java
~~~

### 8.9. Nội dung file GeneratedAnswer.java khi input = 42

~~~java
package demo.generated;
public final class GeneratedAnswer {
  private GeneratedAnswer() {}
  public static int value() { return 42; }
}
~~~

Đây là output **xác định trước từ input**, không phải file cần bạn tạo trong **src/main/java**. Khi kiểm tra nội dung file sau compilation, method **value()** phải chứa đúng giá trị đã cấu hình.

### 8.10. Thay input và quan sát incremental build

Thay file **config/answer.txt** từ **42** sang:

~~~text
73
~~~

Trên Linux/macOS:

~~~bash
printf '73\n' > config/answer.txt
./gradlew -q run
~~~

Trên Windows PowerShell:

~~~powershell
Set-Content -Path config\answer.txt -Value '73' -Encoding Ascii
.\gradlew.bat -q run
~~~

Stdout mới của ứng dụng:

~~~text
ANSWER=73
~~~

Giải thích chuỗi tác động:

1. **config/answer.txt** thay đổi → generator **@InputFile** khác.
2. Generator chạy lại và ghi **GeneratedAnswer.java** với **return 73**.
3. JavaCompile thấy generated source thay đổi nên biên dịch source cần thiết.
4. Task run chạy code đã biên dịch và in **ANSWER=73**.

Nếu lặp lại cùng lệnh khi không thay input, **generateAnswerSource** có thể là **UP-TO-DATE**. Nó không cần chạy action lại chỉ để sinh cùng file một lần nữa.

**Lưu ý:** nếu bạn chạy **./gradlew compileJava --dry-run**, task action không thực sự chạy; dùng nó để xem graph, không để chứng minh nội dung source thay đổi.

### 8.11. Đọc JAR và phân biệt source với class

Sau:

~~~bash
./gradlew jar
jar tf build/libs/generated-source-lab-1.0.0.jar
~~~

JAR mặc định của Java/Application plugin đóng gói **compiled main output**, vì vậy phải có entry:

~~~text
demo/generated/GeneratedAnswer.class
~~~

Không đòi có **GeneratedAnswer.java** trong production JAR, vì đó là source file dùng để compile, không phải resource cần đóng gói mặc định.

Có thể thấy cả:

~~~text
demo/app/Main.class
~~~

JAR không tự có **Main-Class** manifest phù hợp để chạy bằng **java -jar** chỉ vì plugin application biết **mainClass**; cách kiểm tra đơn giản:

~~~bash
java -cp build/libs/generated-source-lab-1.0.0.jar demo.app.Main
~~~

Stdout (với input 73 đã build):

~~~text
ANSWER=73
~~~

### 8.12. Biên dịch Java 17 trực tiếp bằng javac/java

Sau khi Gradle generator đã tạo **GeneratedAnswer.java**, bạn cũng có thể xác minh hai class Java bằng JDK mà không chạy JavaCompile của Gradle:

Linux/macOS:

~~~bash
./gradlew generateAnswerSource
mkdir -p out

javac --release 17 -d out \
  build/generated/sources/answer/main/java/demo/generated/GeneratedAnswer.java \
  src/main/java/demo/app/Main.java

java -cp out demo.app.Main
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat generateAnswerSource
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -d out build\generated\sources\answer\main\java\demo\generated\GeneratedAnswer.java src\main\java\demo\app\Main.java

java -cp out demo.app.Main
~~~

Nếu **config/answer.txt** vẫn chứa 73 và generator đã chạy thành công, dòng stdout là:

~~~text
ANSWER=73
~~~

**Ý nghĩa của hai kiểm thử khác nhau:** javac/java thủ công xác minh **Java source generated có cú pháp hợp lệ**. Chỉ lệnh Gradle **clean compileJava**/**run** mới kiểm tra đầy đủ việc **nối TaskProvider vào source set**, tự xây dependency graph và dùng Gradle compilation tasks.

## 9. Generated source thuộc source set main như thế nào?

### 9.1. Handwritten và generated Java cùng được compile

Sau khi wiring:

~~~text
sourceSets.main.java
    |
    +-- src/main/java
    |      demo/app/Main.java
    |
    +-- build/generated/sources/answer/main/java
           demo/generated/GeneratedAnswer.java
                 |
                 v
              compileJava
                 |
                 v
           build/classes/java/main
~~~

**sourceSets.main.java.srcDir(...)** thêm một source root mới, không tạo một **source set thứ hai**. Các file generated thuộc **main source set**, nên JavaCompile biên dịch cùng các handwritten sources, và Java plugin đóng gói **classes** vào JAR chính như bình thường.

### 9.2. Khi nào nên tạo source set riêng?

Nếu mã generated là một phần public/product API, việc nối nó vào **main** thường hợp lý.

Nếu mã generated chỉ dành cho test fixtures, integration test hoặc công cụ build-time, cân nhắc nối nó vào **test.java** hoặc source set riêng. Đừng đưa code test scaffolding vào main JAR rồi vô tình publish ra ngoài.

Ví dụ gắn một task **đã được định nghĩa phù hợp** vào source set test:

~~~groovy
sourceSets.test.java.srcDir(generateTestSource)
~~~

Đây là **mẫu ý tưởng**, không phải đoạn chạy độc lập: **generateTestSource** phải là TaskProvider tạo **một source directory riêng** cho test, không dùng chung output directory hoặc fully qualified class name với generator main một cách ngẫu nhiên.

### 9.3. Generated source không phải generated resources

Nếu generator tạo **.java**, nối vào:

~~~groovy
sourceSets.main.java.srcDir(generateJavaSources)
~~~

Nếu nó tạo **.properties**, **.json** hoặc resource files để đóng gói theo classpath:

~~~groovy
sourceSets.main.resources.srcDir(generateResources)
~~~

**generateJavaSources** và **generateResources** phải là những tasks/providers có outputs phù hợp. Không trỏ một thư mục chứa lẫn Java source và resource output vào cả **java** lẫn **resources** vì dễ gây duplicate inputs/packaging bất ngờ.

### 9.4. Phân biệt generated source của compiler

Annotation processors, chẳng hạn MapStruct, có thể tạo .java trong quá trình **compileJava** bằng **javac annotation processing**. JavaCompile task quản lý output của annotation processing theo cách riêng; bạn thường chỉ cần:

~~~groovy
dependencies {
    annotationProcessor 'group:processor-artifact:version'
}
~~~

Đoạn này là **cú pháp minh họa**, tọa độ giả. Không tạo một task **generate...** riêng chỉ để chép thư mục **build/generated/sources/annotationProcessor/java/main** vào source set main khi javac đã quản lý lifecycle của generated annotation sources.

Khi mã được tạo bởi **external task** trước compile (OpenAPI, Proto, template generator), mô hình producer task → source set là phù hợp. Với annotation processing do compiler thực thi, mô hình khác: generated Java là output nội bộ của JavaCompile/annotation processor rounds.

## 10. Nhiều generator và nhiều source sets

### 10.1. Mỗi generator có output riêng

Một project có thể dùng:

~~~text
generateApiCode       -> build/generated/sources/api/main/java
generateDomainModels  -> build/generated/sources/domain/main/java
generateTestClients   -> build/generated/sources/clients/test/java
~~~

Nếu tasks đã được đăng ký đúng, bạn có thể nối:

~~~groovy
sourceSets.main.java.srcDir(generateApiCode)
sourceSets.main.java.srcDir(generateDomainModels)
sourceSets.test.java.srcDir(generateTestClients)
~~~

Đây là **minh họa wiring**, không phải sample chạy độc lập. Các task names và output properties phải tồn tại trong build.

### 10.2. Generated tests có thể phụ thuộc main generated classes

Nếu **test** code dùng **GeneratedAnswer** của main, Java plugin thường đã đưa main output vào classpath của test theo conventions. Không nhất thiết phải chạy một bản copy của generator main cho test.

Nếu test source cần **một generated class khác chỉ dành cho test**, đăng ký generator thứ hai có:

- Output directory riêng **build/generated/sources/<name>/test/java**.
- Package/class name không va chạm với generated main.
- Input riêng nếu nội dung khác.
- Wiring **sourceSets.test.java.srcDir(testTaskProvider)**.

Hạn chế việc để cùng một generator task ghi hai output directories của main/test mà không khai báo cả hai, vì compiler tasks khác nhau có thể đòi thứ tự và dữ liệu khác nhau.

### 10.3. Source set integrationTest

Nếu project đã tự tạo **integrationTest**:

~~~groovy
sourceSets {
    integrationTest {
        java.srcDir('src/integrationTest/java')
        resources.srcDir('src/integrationTest/resources')
    }
}
~~~

bạn có thể thêm:

~~~groovy
sourceSets.integrationTest.java.srcDir(
        generateIntegrationClients)
~~~

**generateIntegrationClients** là TaskProvider được định nghĩa ở nơi khác và có output directory cho Java source. Java plugin tạo **compileIntegrationTestJava**, nhưng để **chạy** integration tests vẫn cần một Test task phù hợp, hoặc JVM Test Suite plugin. Nối generator vào source set chỉ giải quyết bước biên dịch mã generated, **không tự làm integration tests chạy trong check**.

### 10.4. Không gộp source sets qua cách thêm source dirs

Nếu code generator cho **main** được chia sẻ với **test**, hãy để test classpath dùng compiled main output theo conventions, không add source directory main lần thứ hai vào test source roots. Biên dịch lại cùng một .java trong hai source sets có thể tạo class files trùng, tốn thời gian và gây khó hiểu khi debug.

## 11. Khai báo producer-consumer dependency đúng hơn

### 11.1. TaskProvider mang nguồn gốc dữ liệu

Trong lab:

~~~groovy
def producer = tasks.register(
        'generateAnswerSource',
        GenerateAnswerSource) {
    generatedSourcesDir.set(
        layout.buildDirectory.dir('generated/sources/answer/main/java'))
}

sourceSets.main.java.srcDir(producer)
~~~

Khi Gradle chuyển task outputs thành FileCollection dùng làm source, thông tin **builtBy** được giữ. Đây là mẫu đơn giản cho một task output directory.

### 11.2. Output Provider phù hợp khi task có nhiều loại outputs

Giả sử task có:

~~~groovy
@OutputDirectory
abstract DirectoryProperty getJavaOutput()

@OutputDirectory
abstract DirectoryProperty getResourceOutput()
~~~

Bạn cần chỉ định output Java thay vì cả task:

~~~groovy
sourceSets.main.java.srcDir(
    generateTask.flatMap { it.javaOutput })

sourceSets.main.resources.srcDir(
    generateTask.flatMap { it.resourceOutput })
~~~

Đây là **đoạn minh họa về API**, yêu cầu task class đã khai báo các properties như trên. Cần giữ dependency metadata qua Provider có liên kết task. Nếu chuyển provider thành path string hoặc **FileTree** tùy ý, Gradle có thể không còn thấy quan hệ built-by.

### 11.3. fileTree sai cách có thể mất task dependency

Mẫu có rủi ro:

~~~groovy
sourceSets.main.java.srcDir(
    fileTree(layout.buildDirectory.dir(
        'generated/sources/answer/main/java')))
~~~

Một **FileTree** tự tạo từ path không nhất thiết chứa thông tin task nào tạo các file trong nó. Ngoài ra **srcDir** cần source directory, không phải list file tùy ý. Hãy truyền **TaskProvider** hoặc output **DirectoryProperty** từ task.

Khi API tiêu thụ bắt buộc FileTree và bạn không thể giữ built-by tự nhiên, Gradle có **builtBy** hoặc một **dependsOn** tường minh, nhưng cần đặt có chủ đích và xác minh bằng **--dry-run** cùng clean build.

### 11.4. Thời điểm tính giá trị

Tránh:

~~~groovy
def dir = generateAnswerSource.get()
        .generatedSourcesDir.get().asFile
sourceSets.main.java.srcDir(dir)
~~~

Lời gọi **get()** ở configuration làm task realization/đọc property sớm và chuyển thành file path, có thể mất dependency metadata. Nếu plugin khác chưa cấu hình xong output, build dễ chịu ảnh hưởng thứ tự. Nên để provider lazy.

### 11.5. Không dùng afterEvaluate để chờ generator

Nếu generator do một plugin tạo, có thể dùng:

~~~groovy
plugins.withId('my.generator.plugin') {
    def task = tasks.named('generateApiSource')
    sourceSets.main.java.srcDir(task)
}
~~~

Đây là **snippet minh họa**: plugin ID và task name không tồn tại mặc định. Cơ chế **withId** giúp chạy cấu hình khi plugin đã được áp dụng, thay vì đẩy toàn bộ wiring vào **afterEvaluate** và giải quyết vấn đề bằng thời điểm cấu hình không ổn định.

## 12. Generated source và task incremental/up-to-date

### 12.1. UP-TO-DATE không có nghĩa task không được nối

Ở lần đầu:

~~~text
> Task :generateAnswerSource
> Task :compileJava
~~~

Lần sau nếu input/output không đổi:

~~~text
> Task :generateAnswerSource UP-TO-DATE
> Task :compileJava UP-TO-DATE
~~~

Đây là **dạng log minh họa**, không phải toàn bộ output cố định. Nếu Gradle không cần chạy task action vì output vẫn hợp lệ, đó là hành vi mong muốn.

### 12.2. Task inputs là mọi dữ liệu ảnh hưởng output

Trong ví dụ, **config/answer.txt** ảnh hưởng đến giá trị returned by **GeneratedAnswer.value()**, vì thế được đánh dấu **@InputFile**.

Nếu nâng generator thành công cụ thật dùng thêm template và lựa chọn package:

~~~groovy
@InputFile
@PathSensitive(PathSensitivity.RELATIVE)
abstract RegularFileProperty getTemplateFile()

@Input
abstract Property<String> getPackageName()
~~~

Đây là **snippet mở rộng** bên trong custom task class, chưa có logic chạy. Muốn correct caching, task action phải thực sự đọc cả template/packageName; output không được phụ thuộc dữ liệu không khai báo.

### 12.3. Incremental task vs up-to-date checks

Hai khái niệm khác nhau:

- **UP-TO-DATE:** nếu inputs/outputs đã được tracking và không đổi, Gradle có thể bỏ qua task action.
- **Incremental work:** nếu input collection chỉ đổi một vài file, task có thể xử lý riêng phần thay đổi nhờ **InputChanges**/**@Incremental**. Task demo đơn giản luôn viết lại một Java file khi cần chạy.
- **Build cache:** có thể phục hồi outputs từ cache khi task được phép cache, inputs/implementation phù hợp và cache hit.
- **Configuration cache:** lưu/tái sử dụng trạng thái cấu hình, không thay thế generated source task hoặc biên dịch.

**@CacheableTask** không đồng nghĩa một generator tự động tối ưu xử lý từng schema file. Nếu generator tạo 5.000 classes và chỉ một schema thay đổi, cần thiết kế incremental processing có ý thức hoặc tách generator tasks/output ownership để giảm phạm vi làm lại.

### 12.4. Khi input bị xóa hoặc đổi tên

Một generator có thể sinh nhiều file. Nếu schema **X** bị xóa, file **XGenerated.java** cũ phải không còn trong output hợp lệ. Nếu generator chỉ ghi thêm file mới mà không xóa output stale, compiler có thể biên dịch các classes không còn được mô tả bởi input.

Giải pháp phù hợp tùy generator:

1. Mỗi task sở hữu một output directory riêng.
2. Rebuild đầy đủ, xóa stale files **chỉ bên trong directory mà task sở hữu** khi cần.
3. Hoặc incremental generator quản lý mapping input → outputs và loại bỏ outputs của inputs đã xóa.
4. Không xóa toàn bộ **build/generated** vì có thể xóa output của task khác.
5. Kiểm tra behavior khi input thêm/sửa/xóa, không chỉ trường hợp sửa 42 thành 73.

Với demo một generated file có tên cố định, tình huống stale nhiều classes không phát sinh.

### 12.5. Bảo đảm output xác định

Một generator dễ cache/reproduce nên:

- Không chèn timestamp hiện tại hoặc random UUID vào generated source nếu đó không phải input có chủ đích.
- Dùng thứ tự sắp xếp ổn định khi sinh nhiều field/method.
- Dùng newline/encoding nhất quán.
- Không ghi absolute path của máy developer vào generated code.
- Không tải dữ liệu mạng ẩn từ task action, trừ khi quản lý nguồn dữ liệu/cache đúng.
- Xử lý input lỗi bằng GradleException rõ và không để lại output trông hợp lệ nhưng thiếu nội dung.

## 13. Nguồn generated và đóng gói Java artifact

### 13.1. class files được đưa vào JAR tự nhiên

Vì generated Java nằm trong **sourceSets.main.java**, output của **compileJava** có cả handwritten và generated class files. Task **jar** của Java plugin thường lấy **sourceSets.main.output** để đóng gói:

~~~text
GeneratedAnswer.java  --compileJava--> GeneratedAnswer.class
Main.java             --compileJava--> Main.class
                                           |
                                           v
                                 generated-source-lab-1.0.0.jar
~~~

Không cần:

~~~groovy
tasks.named('jar') {
    from(layout.buildDirectory.dir('generated/sources/answer/main/java'))
}
~~~

nếu mục tiêu là cung cấp **compiled classes**. Đoạn trên đưa **.java source files** trực tiếp vào JAR production, dễ gây nhầm hoặc trùng file; nó không phải bước cần có để cho class generated được đóng gói.

### 13.2. Nếu muốn source JAR

Một Java library có thể bật:

~~~groovy
java {
    withSourcesJar()
}
~~~

Tùy mô hình project/plugin và các source roots được khai báo, task **sourcesJar** có thể thu thập cả generated Java sources từ main SourceDirectorySet. Hãy kiểm tra thực tế bằng:

~~~bash
./gradlew sourcesJar
jar tf build/libs/generated-source-lab-1.0.0-sources.jar
~~~

Không ép mỗi consumer production tải source JAR chỉ vì generated Java tồn tại. Source JAR phục vụ developer tooling/debugging, không thay compiled class artifact.

### 13.3. Generated resources cần nối vào resources

Nếu generator tạo **config.json** để ứng dụng đọc từ classpath:

~~~groovy
sourceSets.main.resources.srcDir(generateConfigResources)
~~~

Sau đó **processResources** có thể nhận generated resources, **jar** chứa processed resources. Nhưng phải tạo một task output directory khác với Java source generator. Trong dự án dùng nhiều codegen plugins, kiểm tra kỹ chúng đã tự nối source directories trước khi thêm wiring thủ công, tránh duplicate source roots.

### 13.4. Publication cần metadata phù hợp

Sự có mặt của **GeneratedAnswer.class** trong JAR không nói gì về whether Maven publication đã được cấu hình. Nếu producer library publish artifact, task jar và component Java sẽ quyết định phần mã được xuất bản; Gradle Module Metadata/POM và các variants cần được kiểm tra riêng khi plugin tạo thêm feature/artifact.

Một generated source class là một phần của classpath/JAR khi được biên dịch, **không tự là một variant mới**. Phân biệt:

- **Generator task:** tạo .java.
- **SourceSet:** tập nguồn cần compiler đọc.
- **JavaCompile:** tạo .class.
- **Jar/Publication:** tạo/phát hành artifact.
- **Variant:** cách component được cung cấp cho consumer theo attributes/capabilities.

## 14. Dùng generator của bên thứ ba: OpenAPI, Protobuf, ANTLR

Trong sản phẩm, generator thường là một plugin/thư viện bên ngoài, không phải task class tự viết trong build.gradle. Quy tắc wiring vẫn giống nhau:

1. Xác định **tên task generator** và đúng **output directory property** do plugin cung cấp.
2. Xác nhận plugin đã tự thêm generated source directory vào source set hay chưa.
3. Nếu chưa, kết nối **TaskProvider/output Provider** vào **sourceSets.main.java.srcDir(...)** hoặc API được plugin hỗ trợ.
4. Đảm bảo generator input schema/templates và output dir được khai báo.
5. Dùng **clean compileJava --dry-run** để xem graph, rồi clean compile thật để kiểm tra.
6. Kiểm tra source package, compiler version, runtime library của generated code.
7. Không hardcode thư mục output chỉ dựa vào tài liệu của phiên bản plugin khác.

### 14.1. OpenAPI generator

Một task OpenAPI có thể tạo cả Java sources, build files, metadata hoặc tài liệu. Không truyền **toàn bộ output root** vào sourceSets.main.java nếu nó chứa nhiều loại file. Chọn đúng directory chứa **src/main/java** của code generated, và phải giữ task dependency từ producer.

Plugin OpenAPI có thể tự có task compile/packaging hỗ trợ; hãy xem API của plugin version hiện tại trước khi viết một quan hệ dependsOn thủ công. Output directory và layout khác nhau theo lựa chọn generator/library.

### 14.2. Protocol Buffers

Protobuf plugin thường quản lý **generateProto** và generated source roots của Java source sets. Nếu plugin đã wiring tự động, thêm lần nữa dễ trùng compilation inputs hoặc duplicate source roots. Không chạy riêng protoc bằng **doLast** khi plugin đã cung cấp task và input/output tracking chuyên dụng.

Generated Java của protobuf có thể cần runtime library **protobuf-java** đúng phiên bản; việc sinh được .java **không bảo đảm** compile được nếu thiếu runtime/API dependency.

### 14.3. ANTLR, JAXB, WSDL

Các công cụ parser/contract generation có package naming, encoding, template/source compatibility và runtime dependencies riêng. Một số Gradle plugins đã tự tạo source set wiring; một số chỉ có generator task. Quy tắc chung: **output riêng, task producer hợp lệ, consumer source set biết output và runtime dependencies được khai báo riêng**.

## 15. Kotlin, Android và annotation processing có ngoại lệ

### 15.1. Kotlin JVM

**sourceSets.main.java.srcDir(...)** là cơ chế của Java plugin/Java sources. Nếu generator tạo **.kt**, chỉ thêm nó vào **Java SourceDirectorySet** không đủ để Kotlin compiler nhận toàn bộ generated Kotlin source.

Với Kotlin JVM plugin, xem API **kotlin.sourceSets** và cách plugin có thể gắn generated Kotlin source directories với KotlinCompile tasks. Nếu dùng **KSP** hoặc **kapt**, các toolchains/plugin tạo generated sources và tự quản lý task dependency theo cơ chế của chúng.

### 15.2. Android Gradle Plugin

Android có **variants** (debug/release/flavor) và source-generation APIs đặc thù, chẳng hạn variant sources generated directories. Không áp dụng máy móc **sourceSets.main.java.srcDir(...)** của Java plugin cho mọi Android variant; có thể làm code debug lẫn release hoặc task chưa được nối đúng.

Với Android Gradle Plugin mới, ưu tiên API generated source directory của Android Components để attach task output theo từng variant, thay vì tự thêm một thư mục chung vào main.

### 15.3. Annotation processor chạy bên trong javac

Nếu cần tạo Java source dựa trên annotations trong **src/main/java**, các JSR 269 processors chạy trong **compileJava** khi được khai báo trên **annotationProcessor** classpath. Nó không phải một Gradle generator task độc lập xuất hiện trước compiler.

Một source-generation plugin ngoài javac khác về thứ tự và outputs. Tránh “chữa” lỗi MapStruct/Lombok bằng cách copy thư mục annotationProcessor generated source sang **src/main/java** hoặc thêm trực tiếp vào sourceSet rồi làm compiler xử lý cùng file hai lần.

## 16. Diagnostics: xác nhận wiring, không đoán từ file cũ

### 16.1. Kiểm tra task graph

~~~bash
./gradlew tasks --all
./gradlew compileJava --dry-run
./gradlew compileJava --info
~~~

Trong lab, **compileJava --dry-run** phải có **generateAnswerSource** nằm trong task graph. Nếu không, kiểm tra **sourceSets.main.java.srcDir(generateAnswerSource)** và output annotation.

Lưu ý **--dry-run** không thực thi generator action và không bảo đảm generated Java hợp lệ. Cần chạy **clean compileJava** thật để kiểm tra.

### 16.2. Kiểm tra output directory và generated file

~~~bash
./gradlew generateAnswerSource
./gradlew compileJava
~~~

Kiểm tra:

~~~text
build/generated/sources/answer/main/java/demo/generated/GeneratedAnswer.java
build/classes/java/main/demo/generated/GeneratedAnswer.class
~~~

Nếu file .java có nhưng .class không có, xem log **compileJava**, package/path và compilation errors.

### 16.3. Kiểm tra nguồn thực tế của compilation

Báo cáo Java plugin:

~~~bash
./gradlew sourceSets
~~~

có thể giúp quan sát source roots của main và test. Kiểm tra đường dẫn generated source root thay vì chỉ kiểm tra một file đã tồn tại.

Trong build script thử nghiệm, có thể tạm in:

~~~groovy
tasks.named('compileJava', JavaCompile) {
    doFirst {
        logger.lifecycle(
            "Java source count: " + source.files.size())
    }
}
~~~

Đây là **snippet chẩn đoán**, không cần giữ lâu dài. Nó có thể làm Gradle hiện thực danh sách source file trong task execution và log không phải một API được kiểm thử tự động. Không dùng nó thay việc xác minh output artifact và task graph.

### 16.4. Kiểm tra trạng thái và cache

~~~bash
./gradlew generateAnswerSource --info
./gradlew generateAnswerSource --info
./gradlew generateAnswerSource --rerun-tasks --info
./gradlew clean run
~~~

**--rerun-tasks** buộc tasks được lên lịch làm việc lại theo cơ chế Gradle, hữu ích khi điều tra action. Nó không sửa quan hệ producer-consumer nếu source set vẫn chỉ chứa một đường dẫn không có task dependency.

**--refresh-dependencies** liên quan resolution của external dependencies, không giải quyết việc Gradle chưa biết generator task là producer của Java source.

## 17. Bảng lỗi và hướng khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| **cannot find symbol GeneratedAnswer** trên clean build | Generated directory chưa nối source set hoặc producer chưa chạy | Nối **TaskProvider** vào **sourceSets.main.java.srcDir(...)** |
| Build lần hai thành công, lần đầu thất bại | Source generated cũ tồn tại; thiếu task dependency | Chạy **clean compileJava**, sửa producer-consumer wiring |
| **generateAnswerSource** không nằm trong compileJava graph | Chỉ thêm path string, task output bị mất provenance | Dùng **srcDir(taskProvider)**/Provider có built-by |
| Gradle cảnh báo **implicit dependency** | Consumer đọc output của task khác mà không khai báo quan hệ | Truyền output provider/task provider; dependsOn nếu thật sự cần |
| **No source** ở compileJava | Source root trỏ sai thư mục hoặc generator không tạo file | Kiểm tra **package path**, @OutputDirectory, sourceSets |
| **Not a Java source file** hoặc compiler lỗi syntax | Generator viết code invalid/encoding sai | Kiểm tra generated .java bằng javac --release 17 |
| **Input file does not exist** | config/answer.txt chưa tạo hoặc path sai | Tạo input đúng, dùng layout.projectDirectory.file |
| **Integer.parseInt** lỗi | Dữ liệu đầu vào không phải Java int | Sửa input hoặc đổi kiểu/validation của generator |
| Generator luôn chạy | Input/output không được tracking đúng hoặc generator nondeterministic | @InputFile/@OutputDirectory, deterministic output |
| Generator báo UP-TO-DATE nhưng output sai | Quên khai báo input thực hoặc đọc dữ liệu ngoài task inputs | Khai báo đầy đủ input properties, tránh side effects ẩn |
| Class generated trùng class viết tay | Trùng package + class name | Đổi tên/package, chỉ để một nguồn tạo FQCN đó |
| Hai generators ghi cùng thư mục | Overlapping outputs | Tách output directories theo task/source set |
| **NoClassDefFoundError** khi chạy app | Generated class được compile sai scope hoặc không đóng gói | Kiểm tra main output và JAR/classpath |
| **java -jar** lỗi no main manifest | JAR chưa cấu hình entrypoint manifest | Dùng **run** hoặc **java -cp ... demo.app.Main** |
| Generated Java compile nhưng runtime thiếu library | Code generated tham chiếu thư viện ngoài chưa được khai báo | Thêm implementation/runtimeOnly phù hợp |
| Gradle configuration cache error | Task action dùng Project/runtime model hoặc eager IO sai chỗ | Đưa dữ liệu qua managed properties, dùng TaskAction |
| File generated tồn tại sau khi input xóa | Stale outputs không được dọn | Quản lý output ownership và file removal |
| IDE không nhìn thấy generated class | IDE chưa sync sourceSet/plugin wiring | Reload Gradle project, kiểm tra generated root |
| Test code không nhìn thấy generated test class | Generator gắn nhầm main/test scope | Dùng **sourceSets.test.java.srcDir(testTaskProvider)** |
| Android/Kotlin source không được biên dịch | Dùng Java source set wiring sai ecosystem | Dùng Kotlin/Android variant-specific APIs |
| JAR chứa file .java ngoài ý muốn | Thêm raw generated sources vào jar.from | Để JavaCompile tạo .class và jar dùng main.output |
| Task không chạy khi chỉ gọi help | Generator được đăng ký lazy nhưng không nằm trong graph | Đây có thể là hành vi đúng; kiểm tra khi compileJava |
| Generated output không cache được | Chưa đủ metadata/validation hoặc task không cacheable | Kiểm tra @CacheableTask, input/output, implementation |
| Generated code khác nhau trên CI | Generator dùng timestamp, absolute path, locale, platform-specific data | Dùng deterministic output và khai báo các inputs |

### 17.1. Quy trình debug nhanh

~~~text
Không tìm được generated class?
          |
          v
A. Input schema/config tồn tại chưa?
          |
          v
B. Generator task có trong tasks --all?
          |
          v
C. Task có @InputFile/@OutputDirectory đúng?
          |
          v
D. compileJava --dry-run có producer trong graph?
          |
          v
E. Output directory là Java SOURCE ROOT hay file path?
          |
          v
F. Generated file có package/FQCN đúng?
          |
          v
G. JavaCompile có chạy và tạo .class không?
          |
          v
H. Main JAR/runtime classpath có .class cần thiết?
          |
          v
I. Sửa input rồi build lại có đổi output đúng?
~~~

Nếu một bước sai, sửa ở bước đó thay vì thêm bừa **dependsOn**, **afterEvaluate** hoặc xóa cache toàn bộ. **Lỗi wiring cần sửa ở wiring**, lỗi generated Java cần sửa ở generator và lỗi runtime dependency cần sửa classpath phù hợp.

## 18. Bài tập củng cố

### Bài 1 — Quan sát implicit task dependency

Giữ demo nguyên trạng. Chạy:

~~~bash
./gradlew compileJava --dry-run
~~~

Xác định **generateAnswerSource** xuất hiện ở vị trí nào. Giải thích vì sao chỉ yêu cầu **compileJava** mà Gradle biết cần sinh source trước.

### Bài 2 — Tạo lỗi thiếu provenance

Thay tạm:

~~~groovy
sourceSets.main.java.srcDir(generateAnswerSource)
~~~

bằng:

~~~groovy
sourceSets.main.java.srcDir(
    layout.buildDirectory.dir(
        'generated/sources/answer/main/java'))
~~~

Chạy **./gradlew clean compileJava** để quan sát sự khác biệt task graph. Sau đó khôi phục wiring TaskProvider. Giải thích vì sao một source path đúng chưa đủ đảm bảo generator được chạy.

### Bài 3 — Đổi input từ 42 thành 73

Sửa **config/answer.txt**, chạy **./gradlew -q run** và kiểm tra output **ANSWER=73**. Mở generated Java source để xác nhận **return 73**. Không tự sửa **GeneratedAnswer.java**.

### Bài 4 — Input lỗi

Đổi input thành:

~~~text
not-a-number
~~~

Chạy **./gradlew generateAnswerSource** và đọc **GradleException**. Vì sao generator cần validate input trước khi tạo file mới? Khôi phục **42** và chạy lại.

### Bài 5 — Thêm generated resource

Viết một task khác xuất **build/generated/resources/main/info.properties** rồi nối TaskProvider của nó vào **sourceSets.main.resources.srcDir(...)**. Chạy **processResources** và **jar**, kiểm tra JAR có **info.properties** mà không có .java file từ thư mục resources.

### Bài 6 — Generated test source

Tạo task sinh **demo.generated.test.TestHelper.java** vào thư mục **build/generated/sources/helper/test/java**, gắn vào **sourceSets.test.java**. Nếu viết JUnit test dùng TestHelper, task nào phải được lên lịch để compileTestJava có thể chạy? Vì sao không cho generator main và test dùng cùng output directory?

### Bài 7 — Hai generators

Thêm generator thứ hai có package/class khác, output directory riêng. Nối cả hai task providers vào **sourceSets.main.java**. Dùng **compileJava --dry-run** và kiểm tra output of **jar**.

### Bài 8 — Xóa input schema

Mở rộng generator để đọc nhiều input files. Xóa một schema rồi chạy lại. Kiểm tra class generated từ schema đã xóa có được dọn đúng hay không, và giải thích vì sao không nên xóa toàn bộ **build/generated/** của những generator khác.

### Bài 9 — Source JAR

Bật **java.withSourcesJar()** cho project Java và quan sát **sourcesJar**. Kiểm tra generated Java được đưa vào nguồn phục vụ developer như thế nào, rồi phân biệt với compiled class trong JAR production.

### Bài 10 — Chuyển thành plugin dùng chung

Đưa custom task **GenerateAnswerSource** từ build.gradle vào plugin build-logic dùng chung; dùng **Plugin<Project>**, **TaskProvider**, managed properties và sourceSet wiring. Không cần nhân bản class generator trong từng subproject nữa. Chú ý plugin classpath, configuration cache và cách các modules cấu hình input/output riêng.

## 19. Câu hỏi kiểm tra kiến thức

1. Source generator task là producer hay consumer của JavaCompile?
2. **@InputFile** và **@OutputDirectory** giải quyết những phần nào của Gradle task model?
3. Vì sao **sourceSets.main.java.srcDir('build/generated/...')** chưa đủ trong clean build?
4. **TaskProvider** khác **Task** được lấy bằng **get()** ở configuration như thế nào?
5. Gradle hiểu task dependency từ sourceSets thông qua thông tin nào?
6. Khi nào cần **compileJava.dependsOn(generateTask)** thủ công?
7. **shouldRunAfter** có tự làm generator được chọn khi compileJava chạy không?
8. Generated Java source root có phải chính file **GeneratedAnswer.java** không?
9. Vì sao không ghi generated files vào **src/main/java**?
10. Nếu generator tạo Java và resource files, có nên add toàn bộ outputs vào **java.srcDir** không?
11. Chạy **jar** có cần thủ công **from(generated Java directory)** không?
12. Vì sao generated class trong JAR là .class chứ không phải .java?
13. Thay **config/answer.txt** từ 42 sang 73 tác động task nào?
14. **@CacheableTask** có đảm bảo generator luôn chạy nhanh hơn không?
15. Khác biệt giữa UP-TO-DATE và xử lý incremental từng file là gì?
16. Khi input schema bị xóa, loại lỗi stale output nào có thể xảy ra?
17. Source set test có tự thấy main generated class khi main đã compile đúng không?
18. Generated source bởi JSR 269 annotation processor có giống external task generation không?
19. Tại sao không áp cùng sourceSets.main.java wiring cho mọi Kotlin/Android variant?
20. Lệnh nào chứng minh task graph; lệnh nào chứng minh code Java generated biên dịch được?

**Đáp án gợi ý:** (1) generator là producer; (2) file đầu vào và directory output được tracking; (3) không có task provenance; (4) provider là tham chiếu lazy, không buộc hiện thực task sớm; (5) task-built-by metadata/Provider; (6) khi producer–consumer relation không tự giữ được hoặc thứ tự nghiệp vụ cần tường minh; (7) không; (8) không, root là thư mục bên trên package path; (9) tránh Git noise, stale source và mất output ownership; (10) không, tách đúng loại source/resource; (11) không, JavaCompile xử lý source, JAR lấy classes; (12) JAR production thường chứa compiled bytecode; (13) generator rồi JavaCompile và run theo graph; (14) không, cache cần điều kiện/hit; (15) bỏ cả task so với xử lý một phần input thay đổi; (16) class cũ còn trong output; (17) thường có main output trong test classpath; (18) khác lifecycle; (19) plugin/variant API khác; (20) --dry-run và clean compileJava/javac.

## 20. Checklist khi triển khai code generation trong CI

- [ ] Generator input schema/templates/configs được mô hình hóa bằng **@InputFile/@InputFiles/@Input/@InputDirectory** phù hợp.
- [ ] Output của generator là **@OutputDirectory** hoặc **@OutputFile** rõ ràng.
- [ ] Mỗi task sở hữu một output location riêng, không ghi đè output của task khác.
- [ ] Generated Java source nằm dưới **layout.buildDirectory**, không ghi vào source tree.
- [ ] Package của generated .java khớp với relative file path bên dưới source root.
- [ ] Dùng **tasks.register** thay vì eager-create khi phù hợp.
- [ ] Nối generator **TaskProvider/output Provider** vào **sourceSets.<name>.java.srcDir(...)**.
- [ ] Không dùng path string hoặc fileTree độc lập làm mất built-by metadata.
- [ ] Chạy **compileJava --dry-run** để xác minh dependency graph trước khi tin build sạch.
- [ ] Chạy **clean compileJava** để bảo đảm không phụ thuộc generated files cũ.
- [ ] Thay input, xác minh output được sinh lại; chạy lại không đổi, kiểm tra UP-TO-DATE.
- [ ] Khi input biến mất/đổi tên, kiểm tra stale generated output được dọn đúng.
- [ ] Generator output deterministic, encoding và thứ tự ổn định.
- [ ] Generated code có Java toolchain và runtime dependencies tương thích.
- [ ] Kiểm tra compiled classes trong JAR, không tự nhét Java source vào production artifact.
- [ ] Nếu dùng multiple source sets, tách output main/test/integrationTest.
- [ ] Nếu plugin codegen tự wiring source set, không add duplicate paths lần nữa.
- [ ] Nếu dùng Kotlin/Android/JSR 269, áp dụng API của ecosystem đúng phiên bản.
- [ ] Configuration cache/build cache compatibility được thử trên Gradle Wrapper của CI.
- [ ] Không xuất secret, đường dẫn nội bộ hoặc credentials vào generated source hoặc build logs.

## 21. Tài liệu tham khảo chính thức

- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — SourceSet API](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.SourceSet.html)
- [Gradle — SourceDirectorySet API](https://docs.gradle.org/current/dsl/org.gradle.api.file.SourceDirectorySet.html)
- [Gradle — Working With Files](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Gradle — Incremental Build: Task Inputs and Outputs](https://docs.gradle.org/current/userguide/incremental_build.html)
- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html)
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html)
- [Gradle — Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html)
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html)
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle — Java Compile Task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.JavaCompile.html)
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)

**Kết luận:** Tạo mã nguồn trong Gradle không chỉ là viết file **.java** vào một thư mục. Cần xây quan hệ **input schema → generator task → output source directory → SourceSet.java → JavaCompile → class/JAR** bằng các API có kiểu và metadata **built-by**. Với **@InputFile**, **@OutputDirectory**, **tasks.register** và **sourceSets.main.java.srcDir(taskProvider)**, Gradle có thể lập thứ tự task đúng, theo dõi thay đổi và biên dịch generated code ngay cả trên build sạch. Thiết kế đúng giúp generator ổn định, tránh stale files và dễ mở rộng từ Java 17 demo sang OpenAPI/Protobuf hoặc plugin build logic lớn hơn.
