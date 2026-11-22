# Vì sao cấu hình lười cần thiết trong build có khả năng mở rộng

## 1. Vấn đề thực tế và mục tiêu

Một dự án Java nhỏ có thể chỉ có một module và vài chục task. Nhưng một repository lớn có thể gồm hàng chục hoặc hàng trăm project, nhiều plugin, task kiểm thử, tạo mã nguồn, tài liệu, đóng gói và xuất bản. Khi lập trình viên chỉ muốn chạy **:app:test**, nếu Gradle vẫn tạo và cấu hình tất cả task không liên quan, thời gian chờ tăng lên dù phần mã nguồn cần kiểm tra rất nhỏ.

**Cấu hình lười (lazy configuration)** là cách mô tả các đối tượng, task và giá trị sao cho Gradle chỉ hiện thực, cấu hình và tính toán những phần thực sự cần cho build được yêu cầu. Nó không có nghĩa Gradle không cấu hình gì; nó cho phép tránh những công việc chưa cần thiết và giữ quan hệ giữa các phần cấu hình rõ ràng.

Bài học giúp bạn:

- Phân biệt **project configuration**, **task registration**, **task realization**, **task configuration** và **task execution**.
- Giải thích vì sao chi phí cấu hình tăng theo quy mô build và vì sao cơ chế tránh cấu hình task làm vòng phản hồi ngắn hơn.
- Sử dụng **tasks.register**, **tasks.named**, **configureEach** và **TaskProvider**; nhận biết các API eager.
- Dùng **Provider<T>**, **Property<T>**, **map**, **flatMap**, **convention** và **set(provider)** để liên kết dữ liệu mà không đọc quá sớm.
- Phân biệt task configuration avoidance với **configuration cache**, **up-to-date checks** và **build cache**.
- Tự chạy một ví dụ Java 17, kiểm tra task nào được cấu hình/thực thi và đánh giá cách thiết kế build dễ mở rộng.

## 2. Chi phí xuất hiện ở đâu trong vòng đời Gradle?

Gradle thường xử lý build theo ba giai đoạn lớn:

~~~text
INITIALIZATION
  - Xác định settings và project tham gia build
                   |
                   v
CONFIGURATION
  - Áp dụng build script/plugin
  - Đăng ký task, extension và khai báo quan hệ
  - Hiện thực/cấu hình những task cần thiết
  - Tính toán task graph
                   |
                   v
EXECUTION
  - Chạy những task được chọn và dependency cần thiết
  - Tạo output, chạy kiểm thử, đóng gói...
~~~

Trong một build có nhiều module, không chỉ **compileJava** và **test** tiêu tốn thời gian. Các đoạn mã chạy khi cấu hình project cũng có chi phí: khởi tạo plugin, đăng ký/hiện thực task, tìm file, tính đường dẫn, giải quyết dependency quá sớm, gọi tiến trình bên ngoài hoặc thực hiện truy cập mạng.

Nếu có 200 module, mỗi module khai báo 30 task thì sơ đồ build đã có thể chứa khoảng **6.000 task được khai báo**. Con số này chỉ là tình huống minh họa, không phải quy tắc Gradle; task thực tế phụ thuộc plugin và thiết kế repo. Nếu mỗi task bị hiện thực và cấu hình ngay cả khi không được yêu cầu, lượng công việc vô ích tăng mạnh.

Một mô hình khái niệm:

~~~text
Tổng thời gian phản hồi
≈ initialization
+ cấu hình project/plugin liên quan
+ hiện thực và cấu hình task cần thiết
+ lập kế hoạch thực thi
+ thời gian chạy task thực tế
+ chi phí I/O/cache/mạng
~~~

Đây là cách phân tích, **không phải công thức đo thời gian chính xác**. Trong Gradle, các bước có thể tối ưu, chạy song song, được cache hoặc chịu ảnh hưởng bởi daemon, JVM, cấu hình môi trường và plugin. Điểm quan trọng: **giảm thời gian chạy task không tự giải quyết thời gian cấu hình**, nhất là với lệnh rất ngắn như **help**, **tasks** hoặc một unit test nhỏ.

## 3. “Đăng ký”, “hiện thực”, “cấu hình” và “chạy” là các việc khác nhau

Giả sử có task tên **generateDocs**:

1. **Đăng ký (register):** Gradle biết có task tên generateDocs và giữ một **TaskProvider** có thể truyền cho nơi khác.
2. **Hiện thực (realize/create):** đối tượng **Task** thật được tạo khi cần.
3. **Cấu hình (configure):** các action khai báo thuộc tính, input, output, dependency cho task được áp dụng.
4. **Thực thi (execute):** action như **doLast** hoặc **@TaskAction** thực sự chạy để làm việc.

Tạo một task bằng **tasks.create(...)** thường hiện thực/cấu hình nó ngay. Tạo bằng **tasks.register(...)** có thể để nó ở trạng thái **chỉ được đăng ký** nếu lệnh build không cần task đó.

Ví dụ Groovy DSL:

~~~groovy
tasks.register('generateDocs') {
    println 'CONFIG: generateDocs'
    doLast {
        println 'EXEC: generateDocs'
    }
}
~~~

- Với **./gradlew -q help** trong một build không có cấu hình khác cưỡng bức hiện thực **generateDocs**, không cần in hai dòng nói trên.
- Với **./gradlew -q generateDocs**, Gradle phải hiện thực/cấu hình và chạy task, nên các dòng **CONFIG: generateDocs** rồi **EXEC: generateDocs** xuất hiện trong trường hợp cấu hình cache không được tái sử dụng.
- **doLast** chỉ chạy khi task thực thi. Closure truyền vào **register** là **configuration action** và có thể chạy sau thời điểm build script được đánh giá, hoặc không chạy nếu task không cần.

Không nên dựa vào **println** trong configuration để thực hiện nghiệp vụ. Nó chỉ hữu ích để quan sát cơ chế; khi configuration cache hoạt động, phần cấu hình có thể được tái sử dụng mà không in lại.

## 4. Vì sao eager configuration làm build khó mở rộng?

### 4.1. Bài toán task không liên quan

Giả sử build có các task phục vụ công việc độc lập:

~~~text
:app:test
:app:integrationTest
:app:dockerImage
:app:publish
:service:generateApiDocs
:service:verifyArchitecture
...
~~~

Khi chạy **:app:test**, phần lớn task trong danh sách không tham gia task graph. Nếu plugin hoặc build script dùng cách tạo/cấu hình eager, Gradle vẫn có thể tốn thời gian hiện thực và xử lý cấu hình của chúng. Một task có thể cần tính đường dẫn, khởi tạo đối tượng lớn hoặc gọi dependency resolution; nhân lên trên nhiều module sẽ thành chi phí đáng kể.

**Không được suy ra rằng mọi task có trong project đều sẽ thực thi.** Eager configuration làm tăng công việc ở **configuration**, dù **execution** vẫn chỉ chạy task được chọn và quan hệ phụ thuộc của nó.

### 4.2. Task configuration avoidance

Gradle cung cấp bộ API thường gọi là **configuration avoidance**:

| Công việc | API nên ưu tiên | API eager nên hạn chế |
| --- | --- | --- |
| Tạo task mới | **tasks.register('name')** | **tasks.create('name')**, cú pháp **task name** |
| Cấu hình task có sẵn theo tên | **tasks.named('name') { ... }** | **tasks.getByName('name')**, gọi task theo tên trần gây hiện thực |
| Cấu hình mọi task thuộc một kiểu | **tasks.withType(Test).configureEach { ... }** | **tasks.withType(Test) { ... }** hoặc duyệt tất cả task |
| Cấu hình từng task trong collection | **configureEach { ... }** | **all { ... }**, **whenTaskAdded { ... }** |
| Giữ tham chiếu task | **TaskProvider** | Buộc lấy Task bằng **provider.get()** trong configuration |
| Khai báo task dependency | **dependsOn(taskProvider)** | Ép hiện thực task rồi mới nối dependency |

Một task được **register** vẫn có tên và được Gradle nhận diện. Bạn có thể khai báo dependency vào **TaskProvider** mà chưa cần lấy Task instance:

~~~groovy
def generate = tasks.register('generate') {
    doLast {
        println 'Generated'
    }
}

tasks.register('consume') {
    dependsOn(generate)
    doLast {
        println 'Consumed'
    }
}
~~~

Chạy **./gradlew -q consume**:

~~~text
Generated
Consumed
~~~

Quan hệ **dependsOn(generate)** bắt buộc task **generate** chạy trước task **consume**; nó không yêu cầu gọi **generate.get()** trong configuration.

### 4.3. Không phải gọi register là đã lười hoàn toàn

Ví dụ phản tác dụng:

~~~groovy
def report = tasks.register('report') {
    doLast { println 'Report' }
}

report.get() // ép hiện thực task ngay lúc cấu hình build script
~~~

**tasks.register** đã tạo provider, nhưng **get()** ngay sau đó khiến task bị hiện thực. Tương tự, duyệt **tasks.all { ... }** hoặc dùng phương thức eager có thể làm các task đã đăng ký lười bị hiện thực hàng loạt.

Nguyên tắc là: **truyền tham chiếu và mô tả quan hệ**, chỉ lấy giá trị hay đối tượng thật khi Gradle cần thực thi hoặc API không thể tránh được. Việc loại bỏ các điểm hiện thực sớm thường quan trọng không kém việc thay **create** bằng **register**.

## 5. Provider API giúp cấu hình lười cả dữ liệu

Task configuration avoidance xử lý **khi nào task object được tạo/cấu hình**. **Provider API** xử lý **khi nào một giá trị được tính hoặc đọc**, và cách các giá trị liên kết với nhau.

### 5.1. Từ giá trị eager sang Provider

Cách dễ gây vấn đề:

~~~groovy
def label = project.findProperty('build.label') ?: 'local'

tasks.register('showLabel') {
    doLast {
        println 'label=' + label
    }
}
~~~

**findProperty** đọc đầu vào ngay trong configuration. Đoạn này có thể vẫn hoạt động, nhưng việc tính toán/read diễn ra sớm. Cách lười hơn:

~~~groovy
def label = providers.gradleProperty('build.label').orElse('local')

tasks.register('showLabel') {
    doLast {
        println 'label=' + label.get()
    }
}
~~~

**providers.gradleProperty** tạo **Provider<String>** cho Gradle property; **orElse('local')** có mặc định. Giá trị thực chỉ được yêu cầu trong task action. Khi chạy **./gradlew -q showLabel -Pbuild.label=CI**, dòng do task in là:

~~~text
label=CI
~~~

Lợi ích không chỉ ở thời gian: nguồn dữ liệu và chỗ sử dụng được mô tả rõ, dễ kết nối tiếp qua **map**, **flatMap**, property của task và cơ chế theo dõi input.

### 5.2. Provider<T> và Property<T> khác nhau

| Kiểu | Trách nhiệm | Thao tác chính |
| --- | --- | --- |
| **Provider<T>** | Cung cấp một giá trị có thể tính khi cần, thường chỉ đọc | **map**, **flatMap**, **orElse**, **get** |
| **Property<T>** | Property có kiểu, nhận giá trị hoặc nguồn Provider | **set**, **convention**, **get** |
| **RegularFileProperty** | Property cho file trong mô hình Gradle | **set**, truy cập file qua provider |
| **DirectoryProperty** | Property cho thư mục trong mô hình Gradle | **set**, **dir** |
| **ListProperty<T>**, **MapProperty<K,V>** | Collection property có kiểu | **add**, **put**, **set** |

- **set(value)** thiết lập một giá trị trực tiếp.
- **set(provider)** liên kết property với một nguồn có thể tính sau.
- **convention(defaultValue)** đặt mặc định nếu bên ngoài không cung cấp giá trị khác.
- **orElse(defaultValue)** tạo Provider có fallback.
- **get()** yêu cầu giá trị ngay; có thể gây lỗi khi Provider không có giá trị, hoặc kích hoạt công việc quá sớm nếu gọi ở configuration.

Cách thiết kế task hiện đại thường sử dụng **Property<T>** cho input, **RegularFileProperty/DirectoryProperty** cho output, với **@Input**, **@OutputFile**, **@OutputDirectory** để Gradle biết dữ liệu phục vụ việc gì.

### 5.3. map và flatMap để biến đổi hoặc nối nguồn giá trị

**map** chuyển một giá trị được cung cấp thành giá trị khác:

~~~groovy
def component = providers.gradleProperty('component').orElse('api')
def archiveName = component.map { value ->
    value + '-distribution'
}
~~~

**archiveName** vẫn là một **Provider<String>**. Không cần **component.get()** trong configuration. Nếu thành phần khác cần tên đó:

~~~groovy
tasks.named('jar', Jar) {
    archiveBaseName.set(archiveName)
}
~~~

Đoạn **tasks.named('jar', Jar)** yêu cầu Java plugin đã tạo task **jar**, ví dụ có **plugins { id 'java' }**; đây là ví dụ về wiring Provider, không phải một file build độc lập.

**flatMap** phù hợp khi phép chuyển đổi trả về **một Provider khác** và bạn muốn một chuỗi Provider phẳng. Trong những tình huống kết nối task output, thường có dạng:

~~~groovy
def outputFileProvider = producerTask.flatMap { task ->
    task.outputFile
}
~~~

Đây là đoạn minh họa: **producerTask** phải là **TaskProvider** của task có **outputFile** thuộc loại RegularFileProperty hoặc Provider<RegularFile>. Không có những khai báo đó thì đoạn trên không chạy độc lập.

### 5.4. “Wiring sớm, đọc muộn”

Mô hình tốt:

~~~text
Gradle property / environment provider
                |
                v
       map / flatMap / orElse
                |
                v
       Property<T> của task
                |
                v
      Task action đọc giá trị
~~~

Cách phản tác dụng là lấy giá trị ngay rồi gán vào biến hoặc file:

~~~groovy
def path = layout.buildDirectory.file('report.txt').get().asFile
~~~

Lệnh **get()** này có thể hợp lệ về mặt cú pháp nhưng đã biến nguồn lazy thành giá trị File ngay trong configuration. Khi task cần file của task khác, việc đọc đầu ra trước khi task tạo ra là sai về thời điểm. Dùng Provider để nối dữ liệu; Gradle có thể suy ra quan hệ task từ provider mang thông tin producer phù hợp.

**Không phải mọi Provider tự tạo task dependency.** Provider lấy từ một String hoặc từ **providers.gradleProperty** không tự nói “phải chạy task X”. Dependency tự động chỉ có khi nguồn Provider gắn được với task producer/output theo API của Gradle; trường hợp khác, vẫn phải khai báo **dependsOn** hoặc dùng API file collection builtBy phù hợp.

## 6. Ví dụ Gradle hoàn chỉnh: project Java 17 và task lười

Ví dụ sau dùng **Groovy DSL**, có root project, Java library **:core** và ứng dụng **:app**. Project chính là nơi Gradle chọn và cấu hình task theo nhu cầu. Ta tạo thêm một task tùy chọn ở root để quan sát sự khác nhau giữa đăng ký và thực thi.

### 6.1. Cấu trúc thư mục

~~~text
lazy-build-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── core/
│   ├── build.gradle
│   └── src/main/java/lab/core/Greeting.java
└── app/
    ├── build.gradle
    └── src/main/java/lab/app/Main.java
~~~

Các file **gradlew**, **gradlew.bat**, **gradle/wrapper/** được tạo từ Gradle Wrapper. Nếu bắt đầu project mới và đã cài Gradle CLI, chạy **gradle wrapper** một lần, sau đó dùng Wrapper của repo cho mọi lệnh. Cần JDK có thể chạy bản Gradle được chọn và Java 17 toolchain có sẵn hoặc được provisioning qua cấu hình.

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'lazy-build-lab'
include ':core', ':app'
~~~

Settings khai báo hai subproject. Việc có hai project trong cấu trúc build không đồng nghĩa tất cả task của chúng phải được hiện thực hoặc thực thi trong mọi lời gọi.

### 6.3. build.gradle ở root

~~~groovy
plugins {
    id 'base'
}

def banner = providers.gradleProperty('lab.banner').orElse('Lazy build')

tasks.register('showBanner') {
    group = 'help'
    description = 'In giá trị từ Provider'

    doLast {
        println 'Banner: ' + banner.get()
    }
}

tasks.register('optionalAudit') {
    group = 'verification'
    description = 'Task minh họa chỉ cấu hình khi cần'

    println 'CONFIG: optionalAudit'

    doLast {
        println 'EXEC: optionalAudit'
    }
}
~~~

**Giải thích:**

- **base** cung cấp các lifecycle task cơ bản, không biến root thành Java application.
- **banner** là Provider; đọc trong action **showBanner**.
- **optionalAudit** được đăng ký bằng **register**. Dòng **CONFIG** nằm trong configuration action của task, còn **EXEC** nằm trong task action.
- Nếu chạy **./gradlew -q help**, Gradle không cần cấu hình **optionalAudit** vì lệnh chỉ yêu cầu help, trừ trường hợp có plugin/cấu hình khác đã yêu cầu hiện thực task.
- Nếu chạy **./gradlew -q optionalAudit**, task cần được cấu hình và thực thi nên trong điều kiện cấu hình thông thường có hai dòng **CONFIG** và **EXEC** theo đúng thứ tự.

### 6.4. core/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**core/src/main/java/lab/core/Greeting.java**

~~~java
package lab.core;

public final class Greeting {
    private Greeting() {
    }

    public static String forName(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

### 6.5. app/build.gradle

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':core')
}

application {
    mainClass = 'lab.app.Main'
}
~~~

**app/src/main/java/lab/app/Main.java**

~~~java
package lab.app;

import lab.core.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.forName("Gradle"));
    }
}
~~~

Java plugin của **:core** và Application plugin của **:app** đăng ký nhiều task. Khi bạn chạy **:app:run**, Gradle cần task **run** cùng các bước tạo classpath; vì **:app** có **implementation project(':core')**, task cần thiết để cung cấp JAR/classes của **:core** có thể tham gia task graph. Task root **optionalAudit** không cần chạy.

### 6.6. Lệnh chạy và kết quả

**Linux/macOS:**

~~~bash
./gradlew projects
./gradlew -q help
./gradlew -q showBanner
./gradlew -q showBanner -Plab.banner=CI
./gradlew -q optionalAudit
./gradlew -q :app:run
~~~

**Windows PowerShell:**

~~~powershell
.\gradlew.bat projects
.\gradlew.bat -q help
.\gradlew.bat -q showBanner
.\gradlew.bat -q showBanner -Plab.banner=CI
.\gradlew.bat -q optionalAudit
.\gradlew.bat -q :app:run
~~~

**Đầu ra do action showBanner in, khi không có thuộc tính lab.banner từ bất kỳ nguồn Gradle property nào:**

~~~text
Banner: Lazy build
~~~

**Đầu ra action showBanner khi truyền -Plab.banner=CI:**

~~~text
Banner: CI
~~~

**Hai dòng do cấu hình và action của optionalAudit in khi gọi task đó trong build chưa tái sử dụng configuration cache:**

~~~text
CONFIG: optionalAudit
EXEC: optionalAudit
~~~

**Stdout của chương trình Java khi chạy :app:run:**

~~~text
Xin chào, Gradle!
~~~

Gradle có thể in thêm log, thông báo về daemon, task, cache hoặc các lời nhắc hệ thống. Các khối output trên chỉ mô tả những dòng do ví dụ của chúng ta chủ động in, không giả định toàn bộ log Gradle bất biến.

Chạy **./gradlew -q help** không có nghĩa Gradle đã chạy test hoặc compile; dù đã biết cấu trúc **:core** và **:app**, các task build thực tế chỉ được lựa chọn nếu lệnh hoặc dependency yêu cầu.

### 6.7. Kiểm chứng Java độc lập bằng javac

Để phân biệt logic Java với Gradle DSL, có thể biên dịch mã thuần bằng JDK:

~~~bash
mkdir -p out
javac --release 17 -d out core/src/main/java/lab/core/Greeting.java app/src/main/java/lab/app/Main.java
java -cp out lab.app.Main
~~~

**Stdout:**

~~~text
Xin chào, Gradle!
~~~

Trên Windows PowerShell, tạo thư mục **out** bằng **New-Item -ItemType Directory -Force out** rồi dùng **javac** và **java** với các tham số tương đương. Phần biên dịch tay chứng minh Java source đúng, còn task **:app:run** mới kiểm chứng plugin, project dependency và cách Gradle xử lý build.

## 7. Ví dụ dữ liệu đầu vào và file đầu ra bằng Provider

Khi build lớn dần, nhiều task không chỉ in thông báo mà còn tạo file. Gradle cần biết rõ **đầu vào**, **đầu ra** và **quan hệ producer–consumer**. Nếu đọc file vào lúc configuration trước khi task producer tạo nó, build dễ sai thứ tự và khó tối ưu.

Ví dụ dưới đây là **một đoạn build.gradle độc lập thay thế cho ví dụ root ở mục 6.3**; nó minh họa custom task có kiểu, nên không ghép nguyên hai file build.gradle của hai mục vào cùng vị trí. Có thể dùng nó trong một project Gradle mới (settings bất kỳ) để chạy các task mẫu.

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

plugins {
    id 'base'
}

abstract class WriteMessage extends DefaultTask {
    @Input
    abstract Property<String> getMessage()

    @OutputFile
    abstract RegularFileProperty getDestination()

    @TaskAction
    void writeMessage() {
        File target = destination.get().asFile
        target.parentFile.mkdirs()
        target.setText(message.get() + '\n', 'UTF-8')
    }
}

def sourceText = providers.gradleProperty('message.text').orElse('Hello from Gradle')

def producer = tasks.register('writeMessage', WriteMessage) {
    message.convention(sourceText)
    destination.set(layout.buildDirectory.file('generated/message.txt'))
}

tasks.register('printMessage') {
    def producedFile = producer.flatMap { task -> task.destination }
    inputs.file(producedFile)

    doLast {
        println producedFile.get().asFile.getText('UTF-8').trim()
    }
}
~~~

Điểm thiết kế:

1. **WriteMessage** là custom task có **@Input Property<String>** và **@OutputFile RegularFileProperty**, để Gradle biết giá trị cần thiết và file được tạo.
2. **sourceText** là Provider, không cần tính ngay.
3. **producer** là TaskProvider tạo bằng **register**.
4. **producer.flatMap** lấy Provider của output từ task producer, giữ được mối liên hệ với task tạo file.
5. **inputs.file(producedFile)** khai báo file input của **printMessage**. Khi Gradle nhận ra file input provider gắn với output task producer, task dependency được suy ra cho graph phù hợp.
6. **doLast** chỉ đọc file khi task chạy, sau khi producer đã tạo output; không dùng File IO ở cấu hình.

Chạy:

~~~bash
./gradlew -q printMessage
./gradlew -q printMessage -Pmessage.text=FromCI
~~~

**Các dòng do task printMessage in lần lượt trong hai lời gọi:**

~~~text
Hello from Gradle
~~~

và:

~~~text
FromCI
~~~

Task **writeMessage** tạo file **build/generated/message.txt** tương ứng. Khi input không đổi và output hợp lệ, các task có khai báo input/output đầy đủ có thể được đánh dấu up-to-date; điều này phụ thuộc việc Gradle nhận diện trạng thái đầu vào/đầu ra, không phải bảo đảm lần nào cũng giống nhau.

Trong dự án thực tế, tốt nhất tạo các task type tái sử dụng trong **build-logic** hoặc plugin thay vì chép cùng một class vào rất nhiều **build.gradle**. Việc đó giữ cấu hình nhất quán và giảm trùng lặp logic.

## 8. Tối ưu hóa ở các lớp khác nhau: đừng gộp tất cả thành “lazy”

| Cơ chế | Cắt giảm việc gì? | Khi hữu ích? | Giới hạn |
| --- | --- | --- | --- |
| **Task configuration avoidance** | Không hiện thực/cấu hình task không cần. | Build có nhiều task, lệnh ngắn, nhiều module. | Không tự bỏ việc đánh giá build script của tất cả project. |
| **Provider/Property** | Hoãn tính giá trị, mô tả nguồn dữ liệu và liên kết task input/output. | Giá trị đến từ CLI, môi trường, task khác hoặc output file. | **get()** hoặc side effect sai thời điểm vẫn gây eager work. |
| **Configuration cache** | Lưu và tái sử dụng kết quả configuration/task graph khi input liên quan không đổi. | Chạy các lệnh build lặp lại. | Build logic/plugin phải tương thích; khi cache miss vẫn phải cấu hình. |
| **Up-to-date checks** | Bỏ qua thực thi task nếu input/output phù hợp trạng thái trước. | Chạy lại trên workspace ít thay đổi. | Không thay thế configuration avoidance hoặc cấu hình task graph. |
| **Build cache** | Tái sử dụng output task đủ điều kiện từ cache. | Build lặp trên local/CI, có thể chia sẻ cache. | Task phải khai báo input/output và phù hợp cơ chế cache. |
| **Parallel execution** | Chạy các task/project độc lập đồng thời khi an toàn. | Máy nhiều CPU, task độc lập. | Không khắc phục mã configuration phụ thuộc state mutable/sai thread. |

**Tình huống quan trọng:** Một build chạy lại nhanh nhờ **build cache** nhưng lệnh **help** vẫn chậm vì script cấu hình hàng nghìn task theo cách eager. Ngược lại, một build có registration rất lazy vẫn phải chạy compile/test mất thời gian khi source thay đổi.

### 8.1. Configuration cache không thay thế configuration avoidance

Bạn có thể kiểm tra configuration cache:

~~~bash
./gradlew help --configuration-cache
./gradlew help --configuration-cache
~~~

Lần đầu có thể lưu entry, lần sau có thể tái sử dụng nếu input cấu hình không đổi và build logic/plugin tương thích. Configuration cache lưu **kết quả của configuration** để tránh phải làm lại; task configuration avoidance giảm **chi phí cấu hình khi cần tính lại** (chẳng hạn cache miss hoặc lần chạy đầu). Chúng bổ trợ nhau.

Không giả định cấu hình lười tự khiến plugin tương thích configuration cache. Các action truy cập **Project** từ execution, giữ đối tượng không được hỗ trợ, gọi network hoặc đọc state ngoài nguồn input đã theo dõi vẫn có thể gây vấn đề. Khi bật cache, đọc báo cáo lỗi và sửa đúng nơi thay vì bật chế độ bỏ qua lỗi vĩnh viễn.

### 8.2. Provider không tự động làm mọi thứ song song

Provider mô tả dữ liệu có thể cung cấp sau; nó không phải thread hoặc Future chạy bất đồng bộ. **map** và **flatMap** có thể được đánh giá khi Gradle cần giá trị, nhưng chúng không có nghĩa một phép tính nặng được chạy ở luồng nền miễn phí. Đừng đặt truy cập mạng, đọc hàng nghìn file hoặc khởi chạy shell bên trong Provider chỉ vì hy vọng nó sẽ nhanh hơn.

Lợi ích cốt lõi là **tránh tính khi không dùng** và **liên kết dữ liệu có thể kiểm tra**, không phải tự tăng CPU hoặc tự chuyển việc sang một tiến trình khác.

## 9. Thiết kế Gradle build có khả năng mở rộng

### 9.1. Giữ cấu hình project gọn và có mục đích

Một plugin được áp dụng cho từng module có thể đăng ký nhiều task. Hãy tránh việc mọi module đều tính cấu hình nặng khi không cần:

- Chỉ áp dụng plugin cho những project có đúng nhu cầu; ví dụ không phải mọi module đều cần plugin publish, Docker hoặc report.
- Đặt code dùng chung trong **convention plugin** hoặc build logic tái sử dụng khi đủ ổn định.
- Đăng ký task qua **register** và cấu hình tập task qua **configureEach**.
- Dùng **pluginManager.withPlugin('java') { ... }** khi muốn điều chỉnh task chỉ lúc một plugin thực sự xuất hiện.
- Tránh duyệt tất cả task/project, giải quyết mọi configuration hoặc đọc toàn bộ filesystem ở top-level.
- Tách test nhanh và test chuyên sâu theo task/quality gate rõ ràng, để một lệnh nhỏ không kéo theo công việc không liên quan.

### 9.2. Cấu hình của task nên chỉ sửa chính task đó

Một antipattern trong cấu hình lười:

~~~groovy
def checkTask = tasks.register('checkX')

tasks.register('verifyX') {
    checkTask.get().dependsOn(this)
}
~~~

Ở đây configuration action của **verifyX** thay đổi **checkX**. Vì **verifyX** có thể được cấu hình muộn hoặc không được cấu hình, việc thêm quan hệ phụ thuộc này không đáng tin và **get()** còn cưỡng bức hiện thực task khác.

Mẫu đúng:

~~~groovy
def verifyTask = tasks.register('verifyX') {
    doLast {
        println 'Verified'
    }
}

tasks.register('checkX') {
    dependsOn(verifyTask)
    doLast {
        println 'Checked'
    }
}
~~~

Task **checkX** tự khai báo dependency trong configuration action **của chính nó**. **./gradlew -q checkX** in:

~~~text
Verified
Checked
~~~

Quan hệ rõ ràng, không cần hiện thực **verifyX** trước thời điểm cần thiết.

### 9.3. Phân biệt dependsOn và mustRunAfter

**dependsOn(taskProvider)** buộc task dependency tham gia graph khi task consumer được chọn. **mustRunAfter(taskProvider)** chỉ quy định thứ tự **nếu cả hai task đều đã được chọn**; nó không tự bắt task kia chạy. Ví dụ:

~~~groovy
def prepare = tasks.register('prepare') {
    doLast { println 'Prepare' }
}

tasks.register('packageData') {
    dependsOn(prepare)
    doLast { println 'Package' }
}

tasks.register('inspectData') {
    mustRunAfter(prepare)
    doLast { println 'Inspect' }
}
~~~

Chạy **./gradlew -q inspectData** chỉ cần in **Inspect**; **prepare** không tự chạy vì **mustRunAfter** không tạo dependency. Chạy **./gradlew -q packageData** in **Prepare** rồi **Package**. Sử dụng **dependsOn** cho quan hệ cần dữ liệu; chỉ dùng **mustRunAfter** nếu thứ tự có ý nghĩa khi hai task độc lập cùng được chọn.

### 9.4. Đừng đánh đổi correctness để lấy tốc độ

Một task cấu hình nhanh nhưng không khai báo input/output hoặc có side effect ngoài phạm vi sẽ khiến up-to-date/build cache sai. Đừng đọc output task khác trước khi nó chạy, đừng nhét secret vào log, đừng tự động xóa file của module khác trong configuration, và đừng bỏ task quality gate bắt buộc để “giảm task graph”.

Cấu hình lười tốt phải giữ **đúng quan hệ phụ thuộc, đúng dữ liệu, đúng kết quả**. Hiệu năng là hệ quả của một mô hình build rõ ràng và ít công việc dư thừa.

## 10. Đo lường và xác nhận lợi ích

### 10.1. Tránh so sánh một lần chạy duy nhất

Thời gian Gradle phụ thuộc daemon/JVM warm-up, cache, hệ điều hành, CPU, I/O, tốc độ tải dependency và trạng thái source. Để đánh giá thay đổi:

1. Dùng cùng **Gradle Wrapper**, JDK, cùng máy hoặc runner, cùng input build.
2. Chọn một lệnh rẻ như **./gradlew help** để quan sát configuration overhead.
3. Chọn một lệnh thực như **:app:compileJava**, **:app:test** hoặc **:app:run** để quan sát nhu cầu task thực tế.
4. Chạy lặp vài lần, ghi nhận median hoặc phân bố thời gian thay vì so một kết quả duy nhất.
5. Chia điều kiện **configuration cache bật/tắt** rõ ràng; cache hit và cache miss không cùng bài kiểm tra.
6. Dùng **Build Scan** hoặc báo cáo profiling để xem task được hiện thực ở giai đoạn nào; tôn trọng quy định chia sẻ build scan/log của nhóm.

### 10.2. Lệnh quan sát phù hợp

~~~bash
./gradlew help
./gradlew :app:run --dry-run
./gradlew :app:build
./gradlew help --configuration-cache
./gradlew help --configuration-cache
~~~

**--dry-run** mô phỏng các task được chọn mà không chạy action của task, giúp quan sát task graph nhưng **không chứng minh việc cấu hình lười đã loại bỏ hoàn toàn cấu hình của mọi task**.

Một **Build Scan** có thể cho biết task nào được tạo ngay, được hiện thực trong configuration, được tạo lúc lập task graph, hoặc không được tạo. Mục tiêu thường là giảm task được tạo/cấu hình quá sớm; không nên đo thành công bằng việc tổng số task “được đăng ký” nhỏ nhất, vì có nhiều task hợp lệ mà build cần biết.

Có thể dùng **--profile** để nhận báo cáo thời gian trong một số phiên bản/build, nhưng tính năng và mức chi tiết thay đổi theo Gradle; ưu tiên công cụ profiling chính thức được hỗ trợ bởi phiên bản thực tế của repo. Nếu phải dùng **--scan**, xác nhận có quyền gửi metadata build lên dịch vụ scan theo chính sách của tổ chức.

### 10.3. Ví dụ phân tích trước–sau

Giả sử sau khi chuyển plugin tự viết từ **tasks.create** sang **tasks.register**, và bỏ **tasks.all { ... }** để dùng **configureEach**, một lệnh **help** hiện thực ít task hơn. Đó là **bằng chứng trực tiếp về lượng configuration work**, nhưng chưa đủ kết luận mọi build nhanh hơn: các plugin khác, project configuration, cache, I/O và test execution vẫn có thể chi phối.

Đánh giá tốt cần cả **số task realized/configured**, **thời gian configuration**, **tổng thời gian một số lệnh đại diện**, và **tính đúng đắn** của output/test. Nếu task graph khác ngoài dự kiến, ưu tiên sửa quan hệ dependency thay vì tuyên bố đó là tối ưu hóa.

## 11. Những lỗi thường gặp khi chuyển sang cấu hình lười

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Chuyển **create** sang **register** nhưng thời gian không cải thiện | Vẫn gọi **get()**, **all()**, duyệt task hoặc plugin khác cấu hình eager | Tra điểm task bị hiện thực; dùng provider và **configureEach** xuyên suốt |
| Task custom không chạy khi gọi task khác | Quan hệ **dependsOn** được đặt trong configuration action của task có thể không được hiện thực | Cho task consumer tự khai báo dependency và dùng TaskProvider |
| **Task with name ... not found** | **named** được gọi trước khi task/plugin tạo tên đó | Kiểm tra plugin, task name và thời điểm đăng ký; dùng callback plugin khi cần |
| **No value available** | **get()** khi Provider chưa có giá trị | **orElse**, **convention** hoặc validate input bắt buộc |
| Task chạy trước khi file input được tạo | Đọc File trực tiếp, không khai báo input/output hoặc dependency | Dùng RegularFileProperty và Provider có thông tin producer hoặc **dependsOn** |
| **afterEvaluate** bắt đầu có hành vi khó đoán | Đang dựa vào thứ tự các callback/instance được tạo eager | Chuyển sang API lazy và cấu hình task ở đúng nơi |
| **Configuration cache** báo lỗi | Execution action tham chiếu Project hoặc state không phù hợp; đọc input ngoài kiểm soát | Đọc báo cáo cache, tách cấu hình khỏi action, dùng task property có kiểu |
| Build nhanh khi chạy lại nhưng lần đầu chậm | Được hưởng cache hit, nhưng configuration cache miss vẫn đắt | Tối ưu eager configuration và xem thời gian ở điều kiện cache miss |
| Thấy task không chạy trong **help** và nghĩ task mất | Task vẫn đăng ký nhưng không được chọn/realize | Dùng **tasks** để xác định, gọi đúng task khi cần |
| Task đăng ký hàng nghìn lần và khởi động vẫn chậm | Bản thân đăng ký, plugin/script hoặc project evaluation vẫn có chi phí | Giảm cấu hình dư thừa, cân nhắc phạm vi plugin/task, profile |
| Task output thay đổi nhưng Gradle không biết | Input/output khai báo thiếu hoặc side effect ngoài mô hình | Chỉnh khai báo task inputs/outputs, tránh cache sai |
| Chuyển sang Provider nhưng code khó đọc | Chuỗi biến đổi dài, nhiều nguồn không rõ ràng | Đặt tên provider theo nghiệp vụ, tách convention plugin, thêm validation |

**Lưu ý:** Không sửa lỗi “thiếu output” bằng cách gọi **provider.get()** ở top-level để xem tệp rồi tự chạy task thủ công. Điều đó thường làm sai thứ tự hoặc cấu hình lại quá sớm. Bắt đầu từ **đối tượng nào tạo file**, **đối tượng nào cần file**, và nối bằng API Gradle có theo dõi dependency.

## 12. Câu hỏi và bài tập củng cố

### Bài tập A: Quan sát task được hiện thực

Trong ví dụ **lazy-build-lab**, chạy **./gradlew -q help**, sau đó **./gradlew -q optionalAudit**. Ghi lại sự xuất hiện của dòng **CONFIG: optionalAudit** và **EXEC: optionalAudit**. Thử thêm một dòng **println** ở top-level **build.gradle** để thấy khác biệt giữa **project configuration** và **task configuration**. Xóa dòng sau khi quan sát.

### Bài tập B: Chuyển đoạn eager thành lazy

Cho đoạn cũ:

~~~groovy
def packageTask = tasks.create('packageX') {
    doLast { println 'Package X' }
}

tasks.all {
    group = 'misc'
}

tasks.create('verifyX') {
    dependsOn(packageTask)
}
~~~

Hãy thay bằng **register** và **configureEach**, giữ quan hệ dependency. Nếu đổi group tất cả task chỉ để thuận tiện hiển thị, hãy cân nhắc lại nhu cầu: việc ghi đè group của mọi task plugin có thể gây bất ngờ. Quan trọng nhất là không ép hiện thực mọi task trong configuration.

Một lời giải cho phần API (giữ yêu cầu đổi group của đề bài):

~~~groovy
def packageTask = tasks.register('packageX') {
    doLast { println 'Package X' }
}

tasks.configureEach {
    group = 'misc'
}

tasks.register('verifyX') {
    dependsOn(packageTask)
}
~~~

### Bài tập C: Provider và đầu vào CLI

Với **showBanner** của ví dụ Java 17, chạy:

~~~bash
./gradlew -q showBanner
./gradlew -q showBanner -Plab.banner=Release
~~~

So sánh output và giải thích vì sao **banner** không cần được đọc ở đầu **build.gradle**. Nếu muốn viết thành file, hãy tạo task type có **@Input Property<String>** và **@OutputFile RegularFileProperty**, giống mẫu mục 7.

### Bài tập D: Phân biệt các cache

Chạy **:app:build** hai lần khi không đổi source rồi so sánh các task **UP-TO-DATE**; nếu build cache được cấu hình và task phù hợp, cũng có thể thấy **FROM-CACHE**. Tiếp theo chạy **help --configuration-cache** hai lần. Tự ghi nhận mỗi cơ chế bỏ qua công việc nào và vì sao kết quả có thể khác nhau giữa các máy.

### Câu hỏi tự kiểm tra

1. **TaskProvider** có ý nghĩa gì và vì sao thường không cần gọi **get()**?
2. **tasks.register** có luôn bảo đảm không tốn chi phí configuration không?
3. Khác biệt giữa **tasks.withType(Test).configureEach { ... }** và **tasks.withType(Test) { ... }**?
4. Khi nào **Provider.map** phù hợp hơn **Provider.flatMap**?
5. **dependsOn(taskProvider)** khác **mustRunAfter(taskProvider)** như thế nào?
6. Vì sao **configuration cache** và **task configuration avoidance** bổ trợ nhau?
7. Một Provider lấy từ **-P** có tự động chứng minh cần chạy một task producer không?
8. Vì sao chuyển **tasks.create** sang **tasks.register** có thể làm lộ lỗi phụ thuộc vào thứ tự cấu hình?
9. Nên dùng dữ liệu gì để đánh giá lợi ích của chuyển đổi lazy?

**Gợi ý đáp án:** (1) tham chiếu task không buộc hiện thực; (2) không, vẫn có chi phí đăng ký và có thể bị cưỡng bức hiện thực; (3) configureEach trì hoãn action theo từng task cần thiết, cách cũ có thể cấu hình eagerly; (4) map đổi T thành U, flatMap nối T tới một Provider<U>; (5) dependsOn bắt task trước chạy, mustRunAfter chỉ xếp thứ tự khi cả hai cùng chạy; (6) lazy tối ưu cache miss và cấu hình lần đầu, cache tái sử dụng cấu hình sau; (7) không; (8) task không cần thiết có thể không được tạo nên side effect đặt sai chỗ biến mất; (9) số task realized/configured, thời gian, task graph và kết quả test.

## 13. Kết luận

Cấu hình lười cần thiết cho build có khả năng mở rộng vì **chi phí khai báo và cấu hình hàng nghìn task có thể vượt xa phần công việc mà một lệnh thực sự cần**. Gradle cho phép đăng ký task qua **TaskProvider**, cấu hình bằng **named/configureEach**, và liên kết dữ liệu qua **Provider/Property** để task, giá trị và file được sử dụng khi cần.

Mục tiêu cuối cùng không chỉ là giảm vài dòng log hoặc bỏ bớt task khỏi danh sách. Một build tốt phải có **task graph đúng**, **input/output được khai báo chính xác**, **thời gian cấu hình hợp lý**, **cơ chế cache có thể kiểm chứng** và **logic không phụ thuộc vào thời điểm task tình cờ được tạo**. Những nền tảng này giúp một lệnh nhỏ vẫn phản hồi nhanh khi repository phát triển từ một module thành hàng trăm module.

### Tài liệu Gradle chính thức

- [Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html)
- [Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html)
- [Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html)
- [Best Practices for Performance](https://docs.gradle.org/current/userguide/best_practices_performance.html)
- [Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html)
- [Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html)
- [Working with Task Inputs and Outputs](https://docs.gradle.org/current/userguide/incremental_build.html)
