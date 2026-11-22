# Xây dựng lớp DefaultTask và hành động @TaskAction trong Gradle

## Mục tiêu bài học

Khi Gradle không có sẵn task phù hợp, bạn có thể định nghĩa **một loại task tùy chỉnh** bằng cách tạo lớp kế thừa **DefaultTask**, khai báo input/output và viết phương thức gắn **@TaskAction** để Gradle biết công việc nào phải thực hiện. Đây là nền tảng để viết task sinh mã, tạo báo cáo, chuyển đổi tài nguyên, kiểm tra chất lượng hoặc đóng gói kết quả riêng của dự án.

Sau bài này, bạn có thể:

1. Phân biệt **task instance**, **task type** và **task action**; biết khi nào nên dùng **doLast** và khi nào nên tạo lớp kế thừa **DefaultTask**.
2. Viết lớp **DefaultTask** trong Groovy DSL hoặc Java 17+, dùng **@TaskAction** đúng vị trí.
3. Khai báo input/output bằng **Property<T>**, **RegularFileProperty**, **@Input**, **@InputFile**, **@OutputFile** và các annotation thích hợp.
4. Đăng ký task bằng **tasks.register(...)**, cấu hình giá trị bằng Provider/Property và chạy task qua Gradle Wrapper.
5. Kiểm chứng file đầu ra, quan sát **UP-TO-DATE**, nhận biết những điều kiện để task có thể dùng build cache.
6. Đưa mã task dùng chung vào **buildSrc** hoặc build logic/convention plugin thay vì sao chép giữa nhiều script.
7. Xử lý những lỗi phổ biến liên quan đến annotation, getter, signature của **@TaskAction**, thứ tự thực thi và configuration cache.

Bài dùng Gradle **Groovy DSL** làm đường dẫn thực hành chính và có ví dụ lớp Java **17+**. Khi dự án sử dụng **Kotlin DSL**, cấu trúc API tương tự nhưng cú pháp đăng ký task khác; phần cuối có đối chiếu.

## 1. Hiểu ba khái niệm trước khi viết code

### 1.1. Task type, task instance, task action

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Task type** | Lớp mô tả cấu trúc và hành vi chung của task | **DefaultTask**, **Copy**, **Test**, **WriteGreetingTask** |
| **Task instance** | Một task cụ thể có tên và cấu hình trong một project | **:writeGreeting**, **:generateReport** |
| **Task action** | Đoạn công việc chạy ở **execution phase** khi task được thực thi | Method có **@TaskAction** hoặc closure **doLast { ... }** |
| **Task input/output** | Dữ liệu và hiện vật để Gradle kiểm tra thay đổi, sắp xếp dependency và tối ưu build | **@Input Property<String>**, **@OutputFile RegularFileProperty** |

**DefaultTask** là lớp cơ sở thông dụng của Gradle. Một instance **DefaultTask** không tự thực hiện công việc có ý nghĩa nếu bạn chưa thêm action. Bạn có thể gắn action bằng **doLast** hoặc định nghĩa **task type** riêng có method được annotate **@TaskAction**.

Ví dụ đơn giản, không cần lớp mới:

~~~groovy
// build.gradle
tasks.register('hello') {
    doLast {
        println 'Hello from doLast'
    }
}
~~~

Đó là một task loại **DefaultTask** với action được gắn từ build script. Nó hợp lý cho thao tác ngắn hoặc minh họa, nhưng nếu cần nhiều input/output, kiểm tra tính hợp lệ và tái sử dụng ở nhiều module, nên tạo lớp riêng.

### 1.2. Luồng từ cấu hình tới thực thi

~~~text
Gradle initialization
        ↓
Gradle configuration
  • đọc build scripts
  • đăng ký task và cấu hình Property/Provider
  • xác định loại task, input/output, quan hệ task
        ↓
Gradle execution (chỉ task được chọn)
  • kiểm tra điều kiện bỏ qua / UP-TO-DATE / cache
  • chạy @TaskAction hoặc các action đã thêm nếu cần
  • ghi nhận trạng thái input/output
~~~

**Chú ý:** nội dung method có **@TaskAction** không được chạy chỉ vì Gradle đang đọc build script. Nó chạy khi task tương ứng thực sự được thực thi và không bị bỏ qua. Một task có thể bị Gradle kết luận **UP-TO-DATE**, **FROM-CACHE**, **SKIPPED** hoặc **NO-SOURCE**, tùy điều kiện.

## 2. Ví dụ đầu tiên: lớp DefaultTask trong build.gradle

Tạo dự án thực hành có Gradle Wrapper hợp lệ. Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'custom-task-lab'
~~~

Tệp **build.gradle**:

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

abstract class SayHelloTask extends DefaultTask {

    @Input
    abstract Property<String> getRecipient()

    @TaskAction
    void sayHello() {
        println "Hello, ${recipient.get()}!"
    }
}

tasks.register('sayHello', SayHelloTask) {
    recipient.convention('Gradle')
}
~~~

Trên Linux/macOS:

~~~bash
./gradlew sayHello
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat sayHello
~~~

**Dòng do action in ra** ở cấu hình mặc định:

~~~text
Hello, Gradle!
~~~

Gradle còn in thông tin về task và trạng thái build, vì thế dòng trên chỉ là phần stdout do code của chúng ta tạo ra.

Giải thích:

1. **abstract class SayHelloTask extends DefaultTask** tạo một **loại task** mới. Tên **SayHelloTask** là tên class; **sayHello** cuối script mới là tên task được đăng ký.
2. **@Input** đánh dấu thuộc tính **recipient** là input dạng giá trị. Gradle có thể theo dõi thay đổi của input này.
3. **abstract Property<String> getRecipient()** là getter được Gradle cung cấp implementation trong task type dạng managed property. Vì thế bạn không cần tự viết field và setter.
4. **@TaskAction** đánh dấu **void sayHello()** là một hành động của task. Tên method không bắt buộc là **execute**, **run** hay **action**.
5. **recipient.get()** lấy giá trị khi action chạy; tránh lấy nó sớm ở top-level build script.
6. **tasks.register('sayHello', SayHelloTask)** đăng ký task một cách lazy và trả về **TaskProvider<SayHelloTask>**.
7. **recipient.convention('Gradle')** đặt **giá trị mặc định**; giá trị do người cấu hình task đặt sau này có thể thay thế convention.

### 2.1. Khi muốn đổi nội dung lời chào

Sửa phần đăng ký thành:

~~~groovy
tasks.register('sayHello', SayHelloTask) {
    recipient.set('Lan')
}
~~~

Dòng do action in ra khi thực thi sẽ là:

~~~text
Hello, Lan!
~~~

**set(...)** đặt giá trị cụ thể, còn **convention(...)** đặt giá trị mặc định. Với bài tập này, dùng một trong hai tùy mục đích; không cần tự khai báo constructor của task.

### 2.2. Tại sao ví dụ in console chưa đủ cho task production?

Task chỉ in console không có hiện vật output để Gradle kiểm tra xem có cần chạy lại. Annotation **@Input** có ích cho mô hình task, nhưng **UP-TO-DATE** đòi hỏi những điều kiện khác, đặc biệt là outputs được theo dõi hoặc cơ chế được Gradle hỗ trợ phù hợp. Đừng coi ví dụ in console là một task cacheable chỉ vì có **@Input**.

Khi tác vụ thực sự sinh file hoặc thư mục, cần khai báo output và viết file vào vị trí được Gradle quản lý. Phần tiếp theo xây dựng task kiểu đó bằng Java.

## 3. @TaskAction: hợp đồng và vòng đời của hành động

**@TaskAction** là annotation của Gradle nằm trong package **org.gradle.api.tasks**. Nó đánh dấu method instance mà Gradle sẽ gọi khi thực hiện task.

Ví dụ Java rút gọn minh họa cú pháp:

~~~java
import org.gradle.api.DefaultTask;
import org.gradle.api.tasks.TaskAction;

public abstract class SimpleTask extends DefaultTask {
    @TaskAction
    public void runTask() {
        getLogger().lifecycle("Executing SimpleTask");
    }
}
~~~

Đây là **định nghĩa task type**; để chạy được bạn còn cần **classpath Gradle API**, nơi lưu source và lệnh đăng ký task. Ví dụ hoàn chỉnh có đầy đủ file nằm ở mục 4.

Một số nguyên tắc:

- Method action bình thường có **kiểu trả về void**, **không có tham số**; nếu triển khai task có **incremental inputs**, có thể sử dụng tham số **InputChanges** đúng API Gradle. Không truyền String, Project, Task hoặc File tùy ý làm tham số method **@TaskAction**.
- **@TaskAction** annotate **method**, không annotate class, field, getter input hay lời gọi **tasks.register(...)**.
- Method là hành vi của **task type**; mỗi task instance của cùng type sẽ thực thi hành vi đó bằng input/output của **chính instance**.
- Nếu action ném exception không được xử lý, task thất bại và Gradle báo lỗi. Không che lỗi bằng cách nuốt exception rồi tuyên bố thành công.
- Có thể bổ sung action thông qua **doFirst/doLast**, nhưng khi task type đã có **@TaskAction**, hãy giữ logic chính trong type và chỉ thêm hook có mục đích rõ ràng; tránh tạo trình tự khó đoán bằng nhiều action rời.
- **@TaskAction** không có nghĩa được gọi trong configuration phase. Khác biệt giữa cấu hình và execution là điều cần nhớ khi đặt lệnh I/O.

### 3.1. Sai khác với constructor và cấu hình task

Đây là những nhiệm vụ riêng biệt:

| Vị trí code | Nên làm | Tránh |
| --- | --- | --- |
| Constructor/injected properties | Thiết lập convention không phụ thuộc trạng thái ngoài, khởi tạo mô hình task | Đọc file runtime, chạy process hoặc ghi output |
| **tasks.register { ... }** | Nối Provider, đặt input/output, group/description | Ép lấy kết quả task khác bằng get() quá sớm |
| **@TaskAction** | Thực hiện công việc: đọc input đã khai báo, tạo output đã khai báo | Dựa vào Project mutable state, ghi ra file không khai báo |
| **doLast** | Hành động đơn giản hoặc hook bổ sung có lý do | Sao chép lại toàn bộ business logic của task type dùng chung |

Một cách tự kiểm tra: **nếu đang cấu hình tên file đích**, hãy dùng **outputFile.set(...)** trong registration; **nếu đang thực sự viết bytes ra file**, việc đó thuộc **@TaskAction**.

## 4. Ví dụ Java 17+ đầy đủ: sinh file lời chào

Mục tiêu: triển khai một lớp **WriteGreetingTask** có **@Input** cho tên người được chào và **@OutputFile** cho file kết quả. Khi chạy, task tạo file **build/greetings/hello.txt** với nội dung đúng **Hello, Lan!** kèm một ký tự xuống dòng.

### 4.1. Cấu trúc tệp

~~~text
custom-task-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── buildSrc/
    ├── build.gradle
    └── src/main/java/org/example/build/WriteGreetingTask.java
~~~

Các file **gradlew**, **gradlew.bat** và **gradle/wrapper/** thuộc **Gradle Wrapper hợp lệ** của dự án. Có thể tạo chúng từ một project Gradle đã được khởi tạo hoặc dùng lệnh Wrapper theo quy trình của nhóm; không tự soạn một Wrapper JAR.

Thư mục **buildSrc** được Gradle tự nhận diện như build logic riêng. Source Java ở đó được biên dịch trước khi build script chính cần sử dụng class **WriteGreetingTask**.

### 4.2. settings.gradle

~~~groovy
rootProject.name = 'custom-task-lab'
~~~

### 4.3. buildSrc/build.gradle

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation gradleApi()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

- Plugin **java** biên dịch lớp Java trong buildSrc.
- **gradleApi()** đưa API Gradle vào compile classpath của build logic; source có thể import **DefaultTask**, **Property**, **TaskAction**.
- Toolchain yêu cầu Java 17 cho biên dịch lớp trong ví dụ. Gradle cần JDK tương thích để tự chạy, và cần cung cấp JDK 17 cho toolchain (đã cài hoặc đã cấu hình cơ chế cung cấp).
- Nếu dự án đang dùng convention plugin/build logic với cách tổ chức khác, áp dụng tương đương trong build đó; không cần tạo buildSrc thứ hai.

### 4.4. WriteGreetingTask.java

Tạo đúng đường dẫn **buildSrc/src/main/java/org/example/build/WriteGreetingTask.java**:

~~~java
package org.example.build;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.TaskAction;

public abstract class WriteGreetingTask extends DefaultTask {

    @Input
    public abstract Property<String> getNameToGreet();

    @OutputFile
    public abstract RegularFileProperty getDestinationFile();

    @TaskAction
    public void writeGreeting() throws IOException {
        String name = getNameToGreet().get();
        Path destination = getDestinationFile()
                .get()
                .getAsFile()
                .toPath();

        Path parent = destination.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }

        String text = "Hello, " + name + "!\n";
        Files.writeString(
                destination,
                text,
                StandardCharsets.UTF_8
        );
    }
}
~~~

Giải thích những điểm quan trọng:

1. **package org.example.build** phải phù hợp với đường dẫn thư mục dưới **src/main/java**.
2. **extends DefaultTask** biến lớp thành task type; **abstract** cho phép Gradle tạo implementation của abstract managed-property getters.
3. **@Input** nằm trên **getNameToGreet()**, kiểu **Property<String>**. Gradle theo dõi giá trị chuỗi được cấu hình.
4. **@OutputFile** nằm trên **getDestinationFile()**, kiểu **RegularFileProperty**. Gradle theo dõi file output mà task tuyên bố sẽ tạo.
5. **@TaskAction** nằm trên **writeGreeting()**. Method không tham số, trả **void**, khai báo **throws IOException** để lỗi I/O được báo đúng.
6. **getNameToGreet().get()** và **getDestinationFile().get()** nằm trong execution action, không ép lấy input/output ở configuration phase.
7. **Files.createDirectories(parent)** đảm bảo thư mục đích tồn tại.
8. **Files.writeString(...)** là API Java (có từ Java 11, tương thích Java 17); dùng UTF-8 tường minh.
9. Chuỗi kết quả dùng **\n** cố định để output xác định, không lệ thuộc vào loại hệ điều hành; file kết thúc bằng một LF.
10. Action chỉ thực hiện công việc đã khai báo; không đọc **project.file(...)**, không dùng **System.getenv(...)** không theo dõi, và không ghi một file phụ không được annotate.

Đây là lớp Java hợp lệ khi biên dịch **trong môi trường buildSrc có Gradle API**. Nếu gọi **javac WriteGreetingTask.java** riêng bên ngoài mà không cấp Gradle API trên classpath, lệnh sẽ không compile — điều đó khác với lỗi cú pháp của class.

### 4.5. build.gradle ở root và đăng ký task

~~~groovy
import org.example.build.WriteGreetingTask

tasks.register('writeGreeting', WriteGreetingTask) {
    group = 'documentation'
    description = 'Sinh lời chào vào build/greetings/hello.txt'

    nameToGreet.set(
        providers.gradleProperty('who').orElse('Lan')
    )
    destinationFile.set(
        layout.buildDirectory.file('greetings/hello.txt')
    )
}
~~~

Phân tích:

- **tasks.register('writeGreeting', WriteGreetingTask)** đăng ký instance tên **writeGreeting**, thuộc loại custom task **WriteGreetingTask**.
- **group/description** hỗ trợ hiển thị trong **./gradlew tasks**; không phải input của task.
- **nameToGreet.set(provider)** truyền **Provider<String>** vào Property mà không gọi **get()** ở cấu hình.
- **providers.gradleProperty('who')** đọc property tùy chọn từ **-Pwho=...**; **orElse('Lan')** cung cấp default.
- **layout.buildDirectory.file('greetings/hello.txt')** là Provider cho vị trí file bên trong thư mục build, thường là **build/greetings/hello.txt**.
- **destinationFile.set(...)** nối nơi xuất file vào **RegularFileProperty**.
- Việc đăng ký không tự thực thi task; Gradle chỉ chạy task khi nó được chọn trực tiếp hoặc cần thiết theo dependency graph.

### 4.6. Chạy và xác nhận output

Linux/macOS:

~~~bash
./gradlew writeGreeting
cat build/greetings/hello.txt
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat writeGreeting
Get-Content .\build\greetings\hello.txt
~~~

**Nội dung hiển thị của file** (không phải toàn bộ Gradle console log):

~~~text
Hello, Lan!
~~~

File thật kết thúc bằng một **LF**, theo chuỗi **"Hello, Lan!\n"** trong Java.

Thử đổi input:

~~~bash
./gradlew writeGreeting -Pwho=Mai
cat build/greetings/hello.txt
~~~

Windows:

~~~powershell
.\gradlew.bat writeGreeting -Pwho=Mai
Get-Content .\build\greetings\hello.txt
~~~

Kết quả nội dung file:

~~~text
Hello, Mai!
~~~

Gradle phát hiện input **nameToGreet** thay đổi từ **Lan** thành **Mai** và có thể chạy task để cập nhật output. Khi chạy lại với cùng input, implementation và output không đổi, Gradle có cơ sở để báo task **UP-TO-DATE**. Trạng thái chính xác phụ thuộc điều kiện build; không mặc định mọi lần chạy thứ hai đều có cùng log hay cache behavior.

## 5. Cách viết task type bằng Groovy thay vì Java

Nếu chỉ có một build đơn giản, bạn có thể định nghĩa trực tiếp task type trong **build.gradle** dưới dạng lớp Groovy:

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

abstract class EchoTask extends DefaultTask {

    @Input
    abstract Property<String> getMessage()

    @TaskAction
    void echo() {
        println "Message: ${message.get()}"
    }
}

tasks.register('echoMessage', EchoTask) {
    message.set('Hello from Groovy task')
}
~~~

Chạy:

~~~bash
./gradlew echoMessage
~~~

Dòng action in:

~~~text
Message: Hello from Groovy task
~~~

Đây là **ví dụ độc lập khác**; không cần bổ sung vào dự án Java ở mục 4. Hai cách đều tạo lớp kế thừa DefaultTask và dùng **@TaskAction**. Với lớp Java có package rõ, build logic tái sử dụng và kiểm thử thường dễ tổ chức hơn khi dự án lớn; với bài học ngắn, lớp Groovy trong script giúp quan sát cú pháp.

Cần lưu ý **Groovy script class** và **Java class** khác nhau về cú pháp: Groovy bỏ dấu chấm phẩy, cho phép string interpolation, và getter có thể viết **abstract Property<String> getMessage()**. Java cần **public**, dấu **;**, import và method đầy đủ.

## 6. Đăng ký một loại task nhiều lần

Một **task type** có thể tạo nhiều instance với những input/output khác nhau. Sau ví dụ Java ở mục 4, bổ sung vào **build.gradle**:

~~~groovy
tasks.register('writeGreetingForTeam', WriteGreetingTask) {
    group = 'documentation'

    nameToGreet.set('Team')
    destinationFile.set(
        layout.buildDirectory.file('greetings/team.txt')
    )
}
~~~

Từ root:

~~~bash
./gradlew writeGreeting writeGreetingForTeam
~~~

Với hai task:

| Task instance | Input **nameToGreet** | Output |
| --- | --- | --- |
| **writeGreeting** | **Lan** theo mặc định hoặc giá trị **-Pwho** | **build/greetings/hello.txt** |
| **writeGreetingForTeam** | **Team** | **build/greetings/team.txt** |

File team chứa:

~~~text
Hello, Team!
~~~

**Cùng một lớp**, nhưng mỗi task instance có input/output riêng. Không đăng ký hai task cùng ghi vào **cùng một file output**, trừ khi mô hình bạn thiết kế thật sự xử lý sự chia sẻ đó. Hai task ghi chồng output dễ dẫn đến validation lỗi, thứ tự không rõ hoặc trạng thái UP-TO-DATE thiếu tin cậy.

## 7. Annotation input/output: Gradle cần biết những gì?

Nếu task có hành vi ghi file, Gradle cần biết dữ liệu nào ảnh hưởng kết quả và nơi nào được tạo ra. Annotation nằm trên **getter/property** của task type, không nằm trên method **@TaskAction** trừ chính annotation TaskAction.

| Annotation | Áp dụng cho | Ví dụ ý nghĩa |
| --- | --- | --- |
| **@Input** | Giá trị đầu vào đơn giản như String/Number/Boolean/enum, thường bọc trong Property | Tên người nhận, phiên bản mục tiêu, chế độ build |
| **@InputFile** | Một file đầu vào hiện có | File template |
| **@InputFiles** | Tập file đầu vào | Danh sách source/assets |
| **@InputDirectory** | Một thư mục đầu vào | Thư mục chứa templates |
| **@Classpath** | Các file/thư mục thuộc runtime classpath | Artifact thư viện cần kiểm soát nội dung |
| **@CompileClasspath** | Classpath cho biên dịch Java | Phụ thuộc compile ở dạng Gradle hiểu |
| **@OutputFile** | Một file do task tạo | **greetings/hello.txt** |
| **@OutputDirectory** | Một thư mục output | Thư mục chứa các file sinh ra |
| **@Optional** | Kết hợp với input phù hợp khi nó có thể thiếu | Template phụ không bắt buộc |
| **@Nested** | Object phức hợp có các input được annotate bên trong | Cấu hình generator lồng nhau |
| **@Internal** | Thuộc tính không tham gia mô hình input/output | Trạng thái phụ được tính từ property khác |
| **@TaskAction** | Method hành động của task | **writeGreeting()** |

**Không dùng @Input cho mọi kiểu bất kể ý nghĩa.** File input nên dùng **@InputFile/@InputFiles** và cân nhắc **@PathSensitive(PathSensitivity.RELATIVE)** khi tính di động của build cần path normalization. Với task sinh file, dùng **@OutputFile** hoặc **@OutputDirectory** thay vì chỉ đánh dấu chuỗi đường dẫn output là **@Input**.

### 7.1. Vì sao annotation phải đặt trên getter?

Với Java managed properties:

~~~java
@Input
public abstract Property<String> getNameToGreet();

@OutputFile
public abstract RegularFileProperty getDestinationFile();
~~~

Đây là chữ ký getter của task type. Gradle truy vấn những getter này để xác định property của task. Đặt **@Input** lên **setter** hoặc một Java field không có getter đã annotate có thể bị Gradle bỏ qua hoặc tạo lỗi validation. Đặt **@TaskAction** lên getter cũng không biến nó thành một input có thể theo dõi.

Với một field cần được dùng nội bộ và không nên theo dõi, dùng **@Internal** đúng chỗ nếu Gradle yêu cầu phân loại getter đó. Tránh dùng @Internal để che input thực tế, vì khi giá trị thay đổi Gradle có thể bỏ qua việc chạy lại task.

### 7.2. Nếu chưa có giá trị input?

Nếu **getNameToGreet()** là Property chưa được set và không có convention, **getNameToGreet().get()** trong action sẽ báo lỗi. Với input bắt buộc, đây có thể là lỗi hợp lý: task không đủ cấu hình.

Nếu input tùy chọn, hãy dùng **@Optional** phù hợp và xử lý tình trạng không có giá trị bằng **getOrElse(...)** hoặc logic kiểm tra; không chỉ bỏ annotation để tránh lỗi. Với file input, **@InputFile** mặc định có cơ chế kiểm tra file tồn tại và đúng loại khi task chạy; dùng **@Optional** khi thiếu file là trường hợp hợp lệ.

## 8. Kết nối output task này với input task khác

Một ưu điểm của task type có annotation là Gradle có thể suy ra **task dependency** khi input task sau lấy output Provider của task trước.

Giả sử có thêm loại **ReadGreetingTask**, lưu tại **buildSrc/src/main/java/org/example/build/ReadGreetingTask.java**:

~~~java
package org.example.build;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.tasks.InputFile;
import org.gradle.api.tasks.TaskAction;

public abstract class ReadGreetingTask extends DefaultTask {

    @InputFile
    public abstract RegularFileProperty getSourceFile();

    @TaskAction
    public void printFile() throws IOException {
        String text = Files.readString(
                getSourceFile().get().getAsFile().toPath(),
                StandardCharsets.UTF_8
        );
        getLogger().lifecycle(text.trim());
    }
}
~~~

Bổ sung vào **build.gradle** sau khi đã đăng ký **writeGreeting**:

~~~groovy
import org.example.build.ReadGreetingTask

def producer = tasks.named('writeGreeting', WriteGreetingTask)

tasks.register('showGeneratedGreeting', ReadGreetingTask) {
    sourceFile.set(
        producer.flatMap { task -> task.destinationFile }
    )
}
~~~

Lệnh:

~~~bash
./gradlew showGeneratedGreeting
~~~

Thông điệp được action **ReadGreetingTask** ghi ở mức **lifecycle**:

~~~text
Hello, Lan!
~~~

Nếu thêm log task của Gradle, vẫn có thể thấy cả **:writeGreeting** và **:showGeneratedGreeting**. Đây là điểm cần kiểm tra:

- **producer** là TaskProvider, không bắt buộc hiện thực hóa task ngay.
- **flatMap** lấy **RegularFileProperty** được annotate **@OutputFile** từ producer.
- **sourceFile.set(...)** truyền Provider đó vào **@InputFile** của consumer.
- Gradle có thể suy ra dependency cần thiết để producer tạo file trước khi consumer đọc nó; không cần tự thêm **dependsOn('writeGreeting')** khi quan hệ output/input đã được mô hình hóa đầy đủ.
- Hai task đang **khác loại**, nhưng đều kế thừa DefaultTask và đều có method @TaskAction của riêng mình.

**Điều kiện:** quan hệ dependency suy ra khi bạn thực sự truyền Provider/output đúng cách. Nếu thay bằng một path string độc lập:

~~~groovy
// Dạng chỉ truyền path: không tự mang thông tin producer.
sourceFile.set(layout.projectDirectory.file('build/greetings/hello.txt'))
~~~

Gradle không thể chỉ dựa vào tên file đó để biết task nào phải chạy trước. Trong tình huống này còn sai về vị trí root khi project có cấu hình buildDirectory khác. Hãy nối từ **producer.flatMap { it.destinationFile }**.

### 8.1. Phân biệt dependsOn, mustRunAfter và finalizedBy

- **dependsOn**: tạo quan hệ phụ thuộc; task phụ thuộc được đưa vào task graph khi task chính được chọn.
- **mustRunAfter**: ràng buộc thứ tự **nếu cả hai task đã nằm trong graph**, không tự đưa task khác vào graph.
- **finalizedBy**: khai báo task finalizer theo semantics Gradle, ví dụ dọn dẹp sau một task.
- Kết nối Provider từ **@OutputFile** sang **@InputFile** vừa biểu đạt **dữ liệu** vừa hỗ trợ Gradle suy ra quan hệ task một cách đáng tin cậy.

Khi dependency xuất phát từ dữ liệu, cách nối Provider là lựa chọn tự nhiên. Dùng **dependsOn** tường minh cho quan hệ lifecycle hay công việc không thể mô tả qua input/output.

## 9. UP-TO-DATE, build cache và incremental execution

### 9.1. Up-to-date check hoạt động thế nào?

Nếu task khai báo đúng inputs/outputs và không có yếu tố khác buộc chạy lại, Gradle có thể lưu fingerprint và so sánh giữa các lần chạy.

- **Lần chạy đầu:** output chưa tồn tại, task thường thực thi và tạo file.
- **Lần tiếp theo cùng input và output còn nguyên:** Gradle có thể báo **UP-TO-DATE**, không gọi @TaskAction.
- **Đổi -Pwho=Mai:** input **nameToGreet** đổi, Gradle có lý do chạy lại task.
- **Xóa file output:** output không còn, Gradle có thể cần thực thi để tái tạo.

Lệnh quan sát:

~~~bash
./gradlew writeGreeting --info
./gradlew writeGreeting --info
./gradlew writeGreeting --rerun-tasks
~~~

**--rerun-tasks** yêu cầu thực hiện lại task thay vì tái sử dụng trạng thái UP-TO-DATE. Nó hữu ích để kiểm tra action, nhưng không phải phương án sửa thiết kế input/output sai.

**UP-TO-DATE không có nghĩa task chắc chắn cacheable.** Gradle có thể bỏ qua action vì output đã cập nhật, nhưng việc lưu/khôi phục output qua **build cache** cần điều kiện riêng. Với custom task, có thể opt-in bằng **@CacheableTask** khi implementation là deterministic và tuân thủ quy tắc caching.

### 9.2. @CacheableTask không phải chỉ là một công tắc tốc độ

Trước khi đánh dấu cacheable, kiểm tra:

1. Inputs khai báo đầy đủ, kể cả những lựa chọn ảnh hưởng file output.
2. Outputs khai báo đúng và không ghi file bên ngoài.
3. Action deterministic với input đã khai báo: cùng input → cùng output có ý nghĩa.
4. Không nhúng timestamp, đường dẫn máy cá nhân hoặc secret thay đổi vào output nếu không được mô hình hóa đúng.
5. Tránh shared mutable state và tác dụng phụ không được khai báo.

Nếu task chỉ in console hoặc chạy hệ thống ngoài không được kiểm soát, **@CacheableTask** thường không mang ý nghĩa phù hợp. Với task tạo file, hãy kiểm chứng UP-TO-DATE trước rồi mới quyết định có cần caching không.

### 9.3. Incremental execution là khả năng khác

Task có inputs/outputs được annotate có thể được Gradle xem xét **up-to-date**; điều đó **không tự khiến code xử lý từng file thay đổi**.

Để xử lý incremental file changes, Gradle cung cấp **InputChanges** cho phương thức action và các annotation tương ứng, chẳng hạn **@Incremental** hoặc **@SkipWhenEmpty** với input file collections thích hợp. Khi đó task implementation phải xử lý added/modified/removed files và các lần chạy không incremental. Đây là bước nâng cao sau khi đã hiểu task type, action và mô hình input/output.

## 10. Task configuration avoidance: đăng ký lười và thời điểm truy vấn

Ưu tiên:

~~~groovy
def greetingTask = tasks.register('writeGreeting', WriteGreetingTask) {
    nameToGreet.set(
        providers.gradleProperty('who').orElse('Lan')
    )
    destinationFile.set(
        layout.buildDirectory.file('greetings/hello.txt')
    )
}
~~~

**tasks.register** trả TaskProvider. Thao tác cấu hình được Gradle xử lý theo cơ chế lazy, giúp tránh hiện thực hóa những task không cần trong invocation.

Hạn chế thao tác:

~~~groovy
// Không nên ép hiện thực hóa task chỉ để đọc output ở configuration phase.
def path = tasks.named('writeGreeting', WriteGreetingTask)
    .get()
    .destinationFile
    .get()
    .asFile
~~~

Vấn đề là **.get()** trên TaskProvider/Property có thể buộc hiện thực hóa task và lấy giá trị sớm; hơn nữa, file output có thể **chưa được tạo**. Nếu muốn đưa output vào task khác, giữ chuỗi Provider:

~~~groovy
def producer = tasks.named('writeGreeting', WriteGreetingTask)
def generatedFile = producer.flatMap { task ->
    task.destinationFile
}
~~~

Sau đó nối **generatedFile** vào input Property của task consumer, thay vì tự kiểm tra File.exists() ngay ở configuration.

### 10.1. convention và set

~~~groovy
// Trong closure cấu hình task
nameToGreet.convention('Lan')
nameToGreet.set(providers.gradleProperty('who').orElse('Lan'))
~~~

- **convention** đặt giá trị mặc định; cấu hình bên ngoài có thể đặt giá trị khác.
- **set** đặt giá trị mới từ literal hoặc Provider; giá trị dẫn xuất vẫn được nối theo mô hình lazy.
- Đừng gán cả hai chỉ để trông “đầy đủ”; dùng theo nhu cầu. Ví dụ production thường đặt convention trong task class/plugin, còn build script quyết định override theo môi trường.

### 10.2. Task type vs tên task

Bạn có thể có:

~~~groovy
tasks.register('prepareNotes', WriteGreetingTask) {
    nameToGreet.set('Notes')
    destinationFile.set(layout.buildDirectory.file('greetings/notes.txt'))
}
~~~

**prepareNotes** là tên task instance; **WriteGreetingTask** là loại của nó; **writeGreeting()** bên trong Java là tên method action. Đó là ba cái tên có vai trò khác nhau, không cần giống nhau.

## 11. Configuration cache và cách giữ action đúng trách nhiệm

Configuration cache giúp Gradle tái sử dụng trạng thái cấu hình khi build đáp ứng điều kiện. Task type tốt cần tránh phụ thuộc lén vào Project mutable state trong execution action.

**Ưu tiên:**

- Truyền dữ liệu vào task bằng **@Input Property<T>** hoặc file inputs thích hợp.
- Chọn output bằng **@OutputFile/@OutputDirectory** và **layout.buildDirectory**.
- Đặt business logic và file I/O vào method **@TaskAction**.
- Truy cập **getNameToGreet().get()** / **getDestinationFile().get()** trong action.
- Sử dụng **getLogger()** nếu muốn in thông báo; không cần tự lấy toàn bộ **Project** trong action.
- Dùng Java standard library thuần cho logic biến đổi file khi thích hợp.

**Hạn chế:**

~~~groovy
// Ví dụ xấu về tư duy: action đọc Project trực tiếp để tìm config.
@TaskAction
void executeWork() {
    println project.findProperty('who')
}
~~~

Ví dụ này chỉ minh họa lỗi thiết kế, không phải task class hoàn chỉnh. Đọc mutable Project trong execution action có thể vi phạm yêu cầu configuration cache hoặc khiến input thực tế không được khai báo. Thay bằng **Property<String>** được cấu hình trước như ví dụ Java.

Tương tự, dùng **System.getenv(...)** hoặc đọc network trong action mà không khai báo input có thể làm Gradle không phát hiện thay đổi. Nếu cần environment variable, hãy cung cấp thông qua **providers.environmentVariable(...)** và gắn vào Property được annotate. Nếu cần chạy công cụ ngoài, xem các API **ExecOperations** được inject hoặc task type Gradle tương ứng; không tự chạy process thiếu mô hình input/output.

## 12. Khi nào dùng doLast và khi nào dùng @TaskAction?

| Tiêu chí | **tasks.register('x') { doLast { ... } }** | **class X extends DefaultTask { @TaskAction ... }** |
| --- | --- | --- |
| Mục tiêu | Công việc nhỏ, thí nghiệm, hook đơn giản | Hành vi có cấu trúc và cần tái sử dụng |
| Cách đóng gói | Logic nằm trong build script | Logic nằm trong task type |
| Input/output | Có thể khai báo qua **inputs/outputs** API nhưng dễ phân tán | Dễ diễn đạt bằng getter typed + annotation |
| Kiểm thử riêng | Thường cần dựng script hoặc kiểm thử tích hợp | Có thể kiểm thử class/task bằng Gradle TestKit |
| Dùng ở nhiều project | Dễ lặp code | Có thể đưa vào **buildSrc** hoặc convention plugin |
| Configuration cache | Dễ vô tình capture Project/script state | Dễ tránh hơn khi dùng task properties và action chỉ đọc inputs |

**doFirst/doLast** không “sai”; chúng là API Gradle hợp lệ. Với logic tạo output có nhiều input, một class riêng khiến hợp đồng của task dễ hiểu và dễ bảo trì hơn.

Nếu Gradle đã có type **Copy**, **Delete**, **Sync**, **Exec**, **JavaExec** hoặc plugin phù hợp, cân nhắc dùng type sẵn có thay vì tạo lại hành vi chung. Một task tùy chỉnh nên giải quyết công việc mà API hiện tại chưa cung cấp trực tiếp hoặc cần kiểm soát riêng.

## 13. Groovy DSL và Kotlin DSL: so sánh cách viết

### 13.1. Groovy DSL

~~~groovy
abstract class PrintMessage extends DefaultTask {
    @Input
    abstract Property<String> getMessage()

    @TaskAction
    void printMessage() {
        println message.get()
    }
}

tasks.register('printMessage', PrintMessage) {
    message.set('Hello')
}
~~~

Đây là một **đoạn minh họa** cần các import thích hợp trong một build.gradle Groovy; nguyên tắc cùng ví dụ đầu bài.

### 13.2. Kotlin DSL

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

abstract class PrintMessage : DefaultTask() {
    @get:Input
    abstract val message: Property<String>

    @TaskAction
    fun printMessage() {
        println(message.get())
    }
}

tasks.register<PrintMessage>("printMessage") {
    message.set("Hello")
}
~~~

Trong Kotlin DSL:

- Task type là **abstract class PrintMessage : DefaultTask()**.
- Input property có annotation **@get:Input** trên getter của Kotlin property.
- **@TaskAction fun printMessage()** là hành động của task.
- **tasks.register<PrintMessage>("printMessage")** đăng ký task theo type-safe syntax.
- Không dùng **id 'java'** hay **tasks.register('x', Type)** từ Groovy để dán nguyên vào Kotlin DSL.

Lúc chạy task, phần code in:

~~~text
Hello
~~~

Đây là phần stdout của action, không bao gồm Gradle task log.

## 14. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Task được liệt kê nhưng không làm gì | Type chỉ kế thừa DefaultTask, chưa có action | Thêm **@TaskAction** hoặc **doLast** hợp lệ |
| Không tìm thấy **WriteGreetingTask** trong build.gradle | Đặt file Java sai package/path hoặc buildSrc chưa compile | Kiểm tra **package**, **src/main/java**, **buildSrc/build.gradle**, import |
| **Cannot create task of type ...** | Task class không công khai/không hợp lệ, abstract getter/constructor không đúng | Dùng **public abstract class** trong Java, getter Property phù hợp, tránh constructor tùy ý |
| Gradle báo **@TaskAction invalid method** | Method có kiểu trả về/đối số không được API hỗ trợ | Dùng **public void action()**, hoặc InputChanges theo cơ chế incremental |
| Task action không chạy lần thứ hai | Task đủ điều kiện **UP-TO-DATE** hoặc được khôi phục cache | Xem trạng thái task và output; **--rerun-tasks** nếu cần kiểm chứng |
| **Cannot query the value ... because it has no value** | Input Property chưa được set và không có convention | Cấu hình **set/provider/convention**, hoặc đánh dấu tùy chọn đúng |
| File output không được tạo nơi dự tính | Đường dẫn thực không khớp destinationFile | Dùng **layout.buildDirectory.file(...)**, kiểm tra giá trị Property và code ghi file |
| Input đổi nhưng task không chạy lại | Input không được annotate/khai báo đúng | Đặt **@Input** lên getter, không dùng @Internal cho input thực |
| Gradle cảnh báo annotation ở setter/field | Annotation đặt sai vị trí | Dời annotation vào getter trong Java hoặc target getter của Kotlin |
| **@InputFile** validation failed | Input file không tồn tại hoặc sai loại | Nối producer output, sửa path hoặc dùng **@Optional** khi thiếu là hợp lệ |
| Task B đọc file trước task A tạo ra | Truyền path thô, không có quan hệ dependency | Nối output Provider của A vào input Property của B hoặc khai báo dependency phù hợp |
| Cấu hình build chậm | Dùng **tasks.getByName/TaskProvider.get()** sớm | Ưu tiên **tasks.register/named**, Provider/flatMap |
| Configuration cache lỗi do Project access | Task action đọc **project** hoặc giữ captured state không được phép | Chuyển state thành annotated task inputs, tránh gọi Project lúc execution |
| Hai task tranh chấp file đầu ra | Cùng ghi một output path | Chọn output riêng hoặc thiết kế quan hệ và ownership rõ |
| Task dùng @CacheableTask nhưng kết quả không tái lập | Inputs thiếu hoặc action có side effects | Hoàn thiện mô hình input/output và deterministic behavior trước khi cache |

### 14.1. Cách debug nhanh có hệ thống

1. Kiểm tra **task name/type**: **./gradlew tasks --all** hoặc **./gradlew help --task writeGreeting** nếu task thuộc root.
2. Kiểm tra lỗi compile của build logic **buildSrc** trước khi phân tích task action.
3. Kiểm tra **@TaskAction** có được đặt đúng trên method hợp lệ và class task có được đăng ký bằng đúng type không.
4. Xem các getter **@Input/@Output** có giá trị và được annotate đúng không.
5. Chạy task với **--info** để xem lý do Gradle thực thi hay bỏ qua.
6. Với action đã qua kiểm tra, dùng **--rerun-tasks** khi cần xác minh việc chạy lại.
7. Kiểm tra file output thực tế và so sánh với input, thay vì chỉ dựa vào log **BUILD SUCCESSFUL**.
8. Nếu lỗi configuration cache, kiểm tra việc action đọc Project/Gradle model và biến dữ liệu được capture.

## 15. Bài tập thực hành

### Bài 1 — Xác định ba tên

Với:

~~~groovy
tasks.register('makeGreeting', WriteGreetingTask) {
    nameToGreet.set('Mai')
    destinationFile.set(layout.buildDirectory.file('greetings/mai.txt'))
}
~~~

Hỏi: **makeGreeting**, **WriteGreetingTask** và **writeGreeting()** trong file Java lần lượt là gì?

**Đáp án:** tên **task instance**, tên **task type/class**, và tên **method action**. Khi gọi **./gradlew makeGreeting**, Gradle chạy action thuộc task type này nếu không bỏ qua task.

### Bài 2 — Điều nào nằm trong configuration, điều nào trong execution?

~~~groovy
tasks.register('writeGreeting', WriteGreetingTask) {
    nameToGreet.set('An')
    destinationFile.set(layout.buildDirectory.file('greetings/an.txt'))
}
~~~

**Đáp án:** hai lời gọi **set(...)** nằm trong closure cấu hình task. Việc đọc tên và **Files.writeString** trong method có **@TaskAction** thuộc execution. Đăng ký task không tự ghi file.

### Bài 3 — Vì sao task không có @OutputFile khó UP-TO-DATE?

Một task chỉ gọi **println** và khai báo **@Input**. **Đáp án:** Gradle không có output file/directory được theo dõi để xác nhận hiện vật đã cập nhật; không nên dùng đây là minh họa cho caching hay up-to-date của task sinh file.

### Bài 4 — Viết task instance thứ hai

Tạo task tên **writeGreetingForTeam**, dùng **WriteGreetingTask**, input **Team**, output **build/greetings/team.txt**. **Đáp án:** xem đầy đủ đoạn **tasks.register('writeGreetingForTeam', WriteGreetingTask)** ở mục 6. Nội dung file phải là **Hello, Team!** cộng một ký tự LF.

### Bài 5 — Sửa method có signature không hợp lệ

Giả sử task class có:

~~~java
@TaskAction
public String generate(String name) {
    return name;
}
~~~

**Đáp án:** đây là method action sai kiểu; hãy dùng **void generate()**, chuyển **name** thành **@Input Property<String> getNameToGreet()** và đọc **getNameToGreet().get()** trong action.

### Bài 6 — Nối producer và consumer

Task **writeGreeting** có output **destinationFile**. Task **showGeneratedGreeting** có input **sourceFile**. **Đáp án:** **sourceFile.set(producer.flatMap { it.destinationFile })** giữ Provider và task dependency; không tự thay bằng chuỗi path giống nhau.

### Bài 7 — Kiểm chứng input thay đổi

Chạy lần lượt:

~~~bash
./gradlew writeGreeting -Pwho=Lan
./gradlew writeGreeting -Pwho=Lan
./gradlew writeGreeting -Pwho=Mai
~~~

**Kết quả mong đợi:** lần đầu tạo file, lần hai có thể **UP-TO-DATE** nếu điều kiện giữ nguyên, lần ba thay đổi content thành **Hello, Mai!**. Trạng thái chính xác vẫn phụ thuộc build/cache và đầu ra thực tế.

## 16. Checklist khi tự viết DefaultTask

- Đã chọn đúng vấn đề cần **custom task** thay vì dùng task có sẵn chưa?
- Class có **extends DefaultTask**, phạm vi truy cập và package hợp lệ chưa?
- Các getter **Property<T>**, **RegularFileProperty**, **DirectoryProperty** có kiểu đúng và được Gradle cung cấp implementation chưa?
- Mọi input thực sự ảnh hưởng output đã khai báo bằng annotation đúng chưa?
- Mọi file hoặc thư mục do action tạo đã khai báo output chưa?
- Method **@TaskAction** là instance method có signature Gradle hỗ trợ và thực hiện đúng việc chưa?
- Việc đọc input/output xảy ra trong action, không ép Provider.get() quá sớm chưa?
- **tasks.register** được dùng cho lazy registration chưa?
- Output của producer đã nối sang consumer qua Provider hoặc dependency rõ ràng chưa?
- Có thể kiểm tra file đầu ra và lý do task UP-TO-DATE bằng lệnh Wrapper chưa?
- Logic có tránh access Project mutable state trong execution và tác dụng phụ không khai báo không?
- Nếu muốn dùng nhiều module, đã cân nhắc đưa type vào **buildSrc** hoặc convention plugin chưa?

## Tài liệu tham khảo chính thức

- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): tạo class kế thừa DefaultTask, task action và inputs/outputs.
- [Gradle — Creating and Registering Tasks](https://docs.gradle.org/current/userguide/writing_tasks.html): tasks.register, DefaultTask, doFirst/doLast.
- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): annotations, UP-TO-DATE checks, inferred dependencies.
- [Gradle — Custom Tasks / Advanced Tasks](https://docs.gradle.org/current/userguide/custom_tasks.html): InputChanges và incremental task action.
- [Gradle — Sharing Build Logic using buildSrc](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): tổ chức buildSrc, code dùng chung.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): TaskProvider, register/named và lối cấu hình lazy.
- [Gradle — Provider API](https://docs.gradle.org/current/userguide/properties_providers.html): Property, Provider và liên kết output/input.
- [Gradle API — TaskAction](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/TaskAction.html): annotation method action.

**Điều cốt lõi:** lớp **DefaultTask** mô tả *loại công việc*, input/output mô tả *dữ liệu của công việc*, **tasks.register** tạo *task instance* một cách lười, còn **@TaskAction** mô tả *hành động thực thi*. Khi bốn phần được thiết kế nhất quán, Gradle có đủ thông tin để sắp xếp task, kiểm tra thay đổi và chạy build đáng tin cậy.