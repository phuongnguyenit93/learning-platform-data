# Tác vụ build là gì và cách xác định một đơn vị công việc

Trong Gradle, **task** là một đơn vị công việc mà build có thể lựa chọn, sắp xếp và thực thi. Một task có thể biên dịch mã nguồn, chạy kiểm thử, sao chép file, tạo JAR, sinh tài liệu hoặc điều phối nhiều task khác. Khi đọc build script hay log, xác định đúng task giúp trả lời ba câu hỏi: công việc nào đang được yêu cầu, task cụ thể thuộc project nào, và điều kiện nào khiến task đó chạy.

Task là khái niệm trung tâm của quá trình thực thi build, nhưng không phải mọi task đều trực tiếp xử lý file. Có task thực hiện công việc thật; cũng có task tổng hợp chỉ kết nối các công việc khác thành một mục tiêu dễ gọi như **build**, **check** hoặc **assemble**.

## 1. Task là một đơn vị công việc do Gradle quản lý

Một task là một đối tượng trong Gradle model. Task có tên, thuộc về một project, có thể có group và description, có các action để thực hiện công việc, đồng thời có thể khai báo input, output và quan hệ với task khác.

Ví dụ, khi project áp dụng Java plugin, Gradle thường cung cấp những task như:

| Task | Công việc chính |
|---|---|
| **compileJava** | Biên dịch mã nguồn Java chính |
| **processResources** | Xử lý và sao chép resource chính |
| **classes** | Gom các công việc tạo class chính |
| **compileTestJava** | Biên dịch mã nguồn test |
| **test** | Chạy kiểm thử |
| **jar** | Đóng gói class và resource thành JAR |
| **assemble** | Gom các công việc tạo artifact |
| **check** | Gom các công việc kiểm tra |
| **build** | Mục tiêu build tổng hợp, thường kết hợp đóng gói và kiểm tra |

Tên và task cụ thể phụ thuộc plugin đã áp dụng. Một project không áp dụng Java plugin có thể không có compileJava hoặc jar. Plugin khác có thể tạo thêm task riêng, chẳng hạn Spring Boot plugin cung cấp bootJar cho executable JAR.

Có thể hình dung một task theo cấu trúc:

~~~text
Task
 |
 +-- Identity
 |    +-- project path
 |    +-- task name
 |
 +-- Configuration
 |    +-- group / description
 |    +-- task properties
 |    +-- input / output
 |
 +-- Actions
 |    +-- action chạy trước
 |    +-- action chính
 |    +-- action chạy sau
 |
 +-- Relationships
      +-- dependsOn
      +-- ordering constraints
      +-- finalizers
~~~

Đây là mô hình khái niệm. Task type và plugin quyết định các property, action và quan hệ thực tế của task.

### Task có thể làm việc hoặc điều phối

Có hai nhóm vai trò thường gặp:

- **Task thực hiện công việc**: trực tiếp biên dịch, kiểm tra, sao chép, sinh file hoặc đóng gói.
- **Lifecycle/aggregate task**: biểu diễn một mục tiêu lớn bằng cách phụ thuộc vào nhiều task khác.

Ví dụ, compileJava thực hiện biên dịch Java. Trong khi đó, classes thường gom các công việc cần thiết để tạo class chính. build là task tổng hợp, kết nối các công việc đóng gói và kiểm tra.

Vì vậy, gọi build vẫn là gọi một task, dù phần lớn công việc thực tế được thực hiện bởi những task khác trong graph. Task tổng hợp có thể không có action riêng để xử lý dữ liệu.

## 2. Phân biệt task type, task instance và task path

Ba thuật ngữ này giúp xác định chính xác một đơn vị công việc.

### Task type

**Task type** là lớp mô tả hành vi và các thuộc tính của một loại task. Ví dụ:

| Task type | Vai trò |
|---|---|
| **DefaultTask** | Loại task cơ sở thường dùng cho task tùy chỉnh |
| **Copy** | Sao chép file theo cấu hình |
| **JavaCompile** | Biên dịch Java |
| **Test** | Chạy test |
| **Jar** | Tạo JAR |
| **Delete** | Xóa file hoặc thư mục theo cấu hình |

Task type định nghĩa những gì task có thể làm và những property mà task có thể sử dụng. Plugin thường đăng ký các task instance dựa trên những type này.

### Task instance

**Task instance** là một task cụ thể được đăng ký trong một project. Ví dụ, project Java có thể có task tên compileJava với type JavaCompile.

Một type có thể được dùng để tạo nhiều instance. Ví dụ, một build có nhiều source set hoặc nhiều project có thể có nhiều task biên dịch khác nhau.

Có thể đọc quan hệ như sau:

~~~text
Task type: JavaCompile
       |
       +--> :app:compileJava
       |
       +--> :app:compileTestJava
       |
       +--> :library:compileJava
~~~

Các task trên có thể cùng dùng type JavaCompile nhưng là các instance khác nhau. Mỗi instance có cấu hình, input, output và vị trí trong build riêng.

### Task path

**Task path** là định danh của task trong toàn bộ build. Nó kết hợp đường dẫn project với tên task.

| Task path | Ý nghĩa |
|---|---|
| **:compileJava** | Task compileJava trong root project |
| **:app:compileJava** | Task compileJava trong project app |
| **:library:compileJava** | Task compileJava trong project library |
| **:app:test** | Task test trong project app |

Dấu hai chấm đầu tiên biểu thị root của build; các phần tiếp theo xác định project và task. Với build nhiều project, task name có thể lặp lại ở nhiều project. Task path giúp phân biệt chúng.

Ví dụ, hai project app và library đều có task test. Gọi:

~~~shell
./gradlew :app:test
~~~

sẽ chọn task test của project app. Gọi:

~~~shell
./gradlew :library:test
~~~

sẽ chọn task tương ứng trong project library.

Nếu chỉ gọi tên task không kèm project path, Gradle có thể chọn các task cùng tên ở nhiều project theo quy tắc task selection. Khi cần nhắm chính xác một đơn vị công việc, dùng task path đầy đủ.

## 3. Cách tìm và xác định task trong một build

Khi tiếp nhận một build lạ, không nên đoán task dựa trên tên file hoặc tên plugin. Hãy dùng Gradle để liệt kê task, xem thông tin và xác định task path.

### Liệt kê task của build

~~~shell
./gradlew tasks
~~~

Lệnh này hiển thị những task được phân nhóm và giới thiệu cho người dùng trong build. Các task thường được chia theo group như Build, Verification, Help hoặc Documentation.

Muốn xem cả task không thuộc group được hiển thị mặc định:

~~~shell
./gradlew tasks --all
~~~

Trong build nhiều project, có thể liệt kê task của một project cụ thể:

~~~shell
./gradlew :app:tasks --all
~~~

Lệnh này giúp thu hẹp danh sách vào project app.

### Xem chi tiết một task

Khi đã biết tên task, dùng task help:

~~~shell
./gradlew help --task test
~~~

Với project cụ thể:

~~~shell
./gradlew :app:help --task test
~~~

Thông tin thường giúp nhận biết task type, group, description, đường dẫn và cách sử dụng. Nội dung hiển thị tùy task và phiên bản Gradle.

### Xem task graph dự kiến

Dùng **--dry-run** để yêu cầu Gradle hiển thị những task sẽ được lên lịch mà không thực thi action thông thường của chúng:

~~~shell
./gradlew :app:test --dry-run
~~~

Đây là cách hữu ích để thấy một task kéo theo những task phụ thuộc nào. Ví dụ, yêu cầu :app:test có thể đưa các task biên dịch mã nguồn chính, xử lý resource, biên dịch test và chuẩn bị classpath vào graph.

--dry-run cho biết graph dự kiến theo cấu hình hiện tại; nó không chứng minh rằng các task sẽ chạy thành công khi thực thi thật.

### Dùng log để hiểu task đang chạy

~~~shell
./gradlew :app:test --info
~~~

Log mức --info cung cấp thêm thông tin về cấu hình và quá trình thực thi. Khi cần xem kết quả ngắn gọn, có thể dùng:

~~~shell
./gradlew :app:test --console=plain
~~~

Một số câu hỏi nên được trả lời khi tìm task:

1. Task thuộc root project hay subproject nào?
2. Task có được plugin nào tạo ra?
3. Task type là gì?
4. Task có group và description không?
5. Task có action riêng hay chủ yếu điều phối task khác?
6. Task phụ thuộc vào những task nào?
7. Task đọc input nào và tạo output nào?
8. Task có được chọn vào graph khi chạy lệnh hiện tại không?

Không phải lúc nào cũng cần trả lời đủ tám câu hỏi. Với một task quen thuộc như test, task path và task graph có thể đã đủ. Với task tùy chỉnh hoặc task thất bại, cần xem thêm type, property và action.

## 4. Một task được cấu hình và thực thi khi nào?

Task tham gia vào Gradle build lifecycle, nhưng việc **đăng ký**, **cấu hình** và **thực thi** là các hoạt động khác nhau.

### Đăng ký task

Đăng ký task làm cho task xuất hiện trong model của project. Ví dụ:

~~~groovy
tasks.register('sayHello') {
    group = 'help'
    description = 'Prints a greeting'
    doLast {
        println 'Hello from Gradle'
    }
}
~~~

Đoạn này đăng ký task tên sayHello. Task có group và description để dễ tìm trong danh sách. Action in lời chào chỉ được thực hiện khi task được chọn vào graph và chạy.

Đăng ký task không có nghĩa task chạy ngay tại thời điểm build script được đọc.

### Cấu hình task

Cấu hình task là thiết lập property, input, output, group, description và hành vi của task. Ví dụ:

~~~groovy
tasks.named('sayHello') {
    description = 'Prints a greeting from the build'
}
~~~

tasks.named(...) lấy provider của task đã đăng ký để cấu hình nó. Cách này hỗ trợ cơ chế trì hoãn realization của Gradle.

### Thực thi task

Khi task được chọn vào graph và Gradle bước sang execution phase, các action của task mới được thực thi theo thứ tự.

Ví dụ:

~~~shell
./gradlew sayHello
~~~

Nếu chỉ chạy:

~~~shell
./gradlew tasks
~~~

thì task sayHello có thể được liệt kê, nhưng action in lời chào không chạy. Lệnh tasks chỉ yêu cầu task liệt kê task.

### Ba mốc cần phân biệt

| Mốc | Điều xảy ra | Có chạy công việc chính không? |
|---|---|---|
| Registration | Task được đăng ký trong project | Không |
| Configuration | Property và hành vi của task được thiết lập | Thông thường không |
| Execution | Task action được thực thi khi task có trong graph | Có, trừ khi task bị skip hoặc không có action cần chạy |

Build script được đánh giá trong configuration phase. Task action được chạy trong execution phase. Một task có thể được đăng ký và cấu hình nhưng không được chọn vào graph của lệnh hiện tại.

## 5. Task action: nơi công việc thực sự diễn ra

Một task có thể có một hoặc nhiều action. Action là phần logic Gradle thực hiện khi task chạy.

Với task khai báo trực tiếp trong build script, có thể thêm action bằng **doFirst** và **doLast**:

~~~groovy
tasks.register('showBuildSteps') {
    doFirst {
        println 'Starting task'
    }

    doLast {
        println 'Task work completed'
    }
}
~~~

doFirst thêm action vào đầu chuỗi action; doLast thêm action vào cuối chuỗi. Nhiều action có thể được thêm vào cùng một task.

Cách này phù hợp cho task đơn giản, thử nghiệm hoặc thao tác ngắn. Với công việc có input/output rõ ràng và cần tái sử dụng, nên tạo task type riêng.

### Một task có thể không có action riêng

Task tổng hợp có thể chủ yếu khai báo dependsOn để kết nối các task khác:

~~~groovy
tasks.register('verifyAndPackage') {
    dependsOn 'test', 'jar'
}
~~~

Khi chạy verifyAndPackage, Gradle đưa test và jar cùng các dependency của chúng vào graph. Task tổng hợp đóng vai trò một điểm gọi chung.

Đây vẫn là một task hợp lệ dù nó không trực tiếp đọc hoặc ghi file. Giá trị của nó nằm ở việc đặt tên cho một mục tiêu và gom các công việc liên quan.

### Điều kiện bỏ qua task

Task có thể được cấu hình để không thực thi trong một số điều kiện:

~~~groovy
tasks.register('publishPreview') {
    onlyIf {
        project.hasProperty('preview')
    }

    doLast {
        println 'Publishing preview'
    }
}
~~~

Trong ví dụ này, action chỉ chạy khi project property preview tồn tại. Nếu điều kiện onlyIf trả về false, Gradle bỏ qua task.

Ngoài ra, task có thể bị vô hiệu hóa bằng thuộc tính enabled = false, không có source để xử lý, hoặc được đánh dấu up-to-date/tái sử dụng output từ cache. Do đó, task xuất hiện trong graph không đồng nghĩa action của nó luôn chạy.

## 6. Input và output xác định công việc của task

Để hiểu một task thực sự làm gì, hãy xem dữ liệu task đọc và dữ liệu task tạo ra.

- **Input** là dữ liệu ảnh hưởng đến kết quả, ví dụ file nguồn, cấu hình, phiên bản hoặc chuỗi đầu vào.
- **Output** là kết quả task tạo ra, ví dụ file class, JAR, báo cáo hoặc thư mục được sinh.
- **Task action** đọc input, thực hiện xử lý và tạo output.

Ví dụ với task sao chép:

~~~groovy
tasks.register('copyConfiguration', Copy) {
    from 'src/main/config'
    into layout.buildDirectory.dir('copied-config')
}
~~~

Task copyConfiguration có input là nội dung trong src/main/config và output là thư mục cấu hình đã sao chép dưới build/copied-config.

Khi input/output được khai báo đúng, Gradle có thể xác định task có cần chạy lại hay không. Nếu dữ liệu đầu vào không thay đổi và output vẫn hợp lệ, task có thể được đánh dấu UP-TO-DATE. Nếu có output tương ứng trong build cache và task đáp ứng điều kiện cache, Gradle có thể khôi phục output với trạng thái FROM-CACHE.

Một task không khai báo đầy đủ input/output sẽ hạn chế khả năng kiểm tra up-to-date và sử dụng build cache an toàn. Gradle không thể suy luận đáng tin cậy mọi file mà một đoạn logic tùy ý đọc hoặc ghi.

### Input/output trong task type

Với task type tùy chỉnh, các property có thể được đánh dấu bằng annotation để Gradle hiểu vai trò của chúng:

| Annotation | Ý nghĩa |
|---|---|
| **@Input** | Giá trị input đơn giản ảnh hưởng đến kết quả |
| **@InputFile** | Một file input |
| **@InputFiles** | Nhiều file input |
| **@InputDirectory** | Một thư mục input |
| **@OutputFile** | Một file output |
| **@OutputDirectory** | Một thư mục output |
| **@Internal** | Property nội bộ không tham gia fingerprint input/output |
| **@Optional** | Input/output tương ứng có thể không được cung cấp trong trường hợp được hỗ trợ |

Các annotation cần đặt trên property/getter phù hợp của task type. Việc khai báo phải phản ánh đúng dữ liệu mà action thực sự sử dụng.

## 7. Tạo task tùy chỉnh đơn giản

Khi cần thêm một công việc riêng cho project, có thể đăng ký task trực tiếp bằng Gradle DSL.

Ví dụ:

~~~groovy
tasks.register('printEnvironment') {
    group = 'help'
    description = 'Prints the selected build environment'

    doLast {
        def environmentName = project.findProperty('environmentName') ?: 'local'
        println 'Build environment: ' + environmentName
    }
}
~~~

Chạy task:

~~~shell
./gradlew printEnvironment
~~~

Truyền property:

~~~shell
./gradlew -PenvironmentName=staging printEnvironment
~~~

Build script có thể đọc project property environmentName để chọn cấu hình phù hợp. Với thông tin nhạy cảm, nên dùng secret store của CI hoặc cơ chế quản lý credential phù hợp, tránh ghi mật khẩu/token vào source code hoặc log.

### Khi nào nên tạo task type riêng?

Nên cân nhắc task type riêng khi:

- Công việc có nhiều property hoặc cần cấu hình ở nhiều project.
- Công việc có input/output cần khai báo rõ.
- Cần tái sử dụng trong nhiều build script.
- Cần kiểm soát up-to-date behavior hoặc build cache.
- Muốn tách logic thực thi khỏi cấu hình build script.
- Công việc cần được kiểm thử hoặc đóng gói thành plugin.

Task type riêng giúp mô tả một loại công việc; mỗi project có thể đăng ký instance với cấu hình khác nhau.

## 8. Tạo task type bằng DefaultTask

Với Groovy DSL, có thể định nghĩa một lớp kế thừa DefaultTask, khai báo property và một phương thức mang @TaskAction.

Ví dụ sau tạo file lời chào:

~~~groovy
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

abstract class GenerateGreeting extends DefaultTask {
    @Input
    abstract Property<String> getGreeting()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        def destination = outputFile.get().asFile
        destination.parentFile.mkdirs()
        destination.text = greeting.get() + System.lineSeparator()
    }
}

tasks.register('generateGreeting', GenerateGreeting) {
    greeting.set('Hello from a typed Gradle task')
    outputFile.set(layout.buildDirectory.file('generated/greeting.txt'))
}
~~~

Khi chạy:

~~~shell
./gradlew generateGreeting
~~~

Gradle thực hiện các bước:

1. Tạo task instance generateGreeting từ type GenerateGreeting.
2. Cấu hình property greeting với nội dung cần ghi.
3. Cấu hình output file dưới thư mục build.
4. Khi task được chọn vào graph, gọi phương thức generate mang @TaskAction.
5. Action tạo thư mục cha nếu cần rồi ghi nội dung vào file output.

Ở đây:

- **Property<String>** biểu diễn một giá trị input có thể được Gradle quản lý.
- **RegularFileProperty** biểu diễn một file output.
- **@Input** giúp Gradle nhận diện nội dung lời chào là input.
- **@OutputFile** giúp Gradle nhận diện file được tạo là output.
- **@TaskAction** đánh dấu phương thức chứa công việc thực thi.

Đây là ví dụ minh họa cấu trúc task type. Trong plugin dùng thực tế, cần cân nhắc cách xử lý encoding, lỗi I/O, tính xác định của output, file tạm và yêu cầu cache. Không nên để action phụ thuộc vào dữ liệu bên ngoài không được khai báo như input.

### Vì sao dùng property do Gradle quản lý?

Các kiểu property như Property<T>, DirectoryProperty và RegularFileProperty giúp Gradle quản lý giá trị, hỗ trợ provider, trì hoãn việc tính toán và nối output của task này với input của task khác.

Ví dụ, output của một task có thể được cung cấp cho task tiếp theo bằng provider thay vì tự ghép đường dẫn chuỗi. Cách này làm cho quan hệ dữ liệu rõ hơn và giúp Gradle hiểu dependency giữa các công việc.

## 9. Đăng ký task theo cách lazy

Gradle cung cấp hai API thường gặp để làm việc với task:

| API | Mục đích |
|---|---|
| **tasks.register(name, type)** | Đăng ký task và trả về TaskProvider; task được tạo khi cần |
| **tasks.named(name)** | Lấy provider của task đã đăng ký để cấu hình/tham chiếu |
| **tasks.create(name, type)** | Tạo task ngay; cách eager thường ít được ưu tiên trong build hiện đại |
| **tasks.getByName(name)** | Lấy task instance và có thể làm task được realize ngay |

Ví dụ:

~~~groovy
def reportTask = tasks.register('generateReport') {
    group = 'verification'
    description = 'Generates a local report'

    doLast {
        println 'Report generated'
    }
}

tasks.register('showReportHint') {
    doLast {
        println 'Run generateReport to create the report'
    }
}
~~~

tasks.register trả về TaskProvider. Provider cho phép tham chiếu task mà chưa cần tạo task instance ngay lập tức.

Khi cần cấu hình task đã đăng ký:

~~~groovy
tasks.named('generateReport') {
    description = 'Generates the verification report'
}
~~~

Cách đăng ký lazy giúp build tránh tạo và cấu hình những task không cần thiết. Điều này đặc biệt có ích trong build nhiều project hoặc có nhiều plugin.

### configureEach

Khi cần cấu hình mọi task thuộc một type, có thể dùng configureEach:

~~~groovy
tasks.withType(Test).configureEach {
    maxParallelForks = 2
}
~~~

Cách này áp dụng cấu hình cho các task type Test khi chúng được realize, đồng thời hỗ trợ configuration avoidance. Nó thường phù hợp hơn việc duyệt và buộc tạo mọi task ngay trong configuration phase.

### Không thực thi công việc trong configuration phase

Một lỗi thiết kế phổ biến là đặt thao tác đọc/ghi file hoặc chạy lệnh bên ngoài trực tiếp trong phần cấu hình build script:

~~~groovy
println 'This runs while the project is being configured'
~~~

Code cấu hình được đánh giá trong configuration phase, kể cả khi task chứa nó không được chọn. Công việc thực tế nên đặt trong task action để Gradle chỉ thực hiện khi task cần chạy.

Điều này giúp build dễ dự đoán, nhanh hơn và phù hợp với configuration cache hơn. Với task tùy chỉnh, tránh lưu trực tiếp trạng thái project hoặc truy cập model Gradle không an toàn bên trong action; hãy đưa dữ liệu cần thiết qua task property.

## 10. Task dependency và quan hệ thứ tự

Task có thể liên kết với nhau để tạo thành task graph.

### dependsOn: phụ thuộc thực thi

dependsOn nói rằng task hiện tại cần task khác được thực hiện trước:

~~~groovy
tasks.register('packagePreview') {
    dependsOn tasks.named('test')
    dependsOn tasks.named('jar')
}
~~~

Khi yêu cầu packagePreview, Gradle đưa test và jar vào graph cùng những task mà chúng phụ thuộc.

Quan hệ này thể hiện rằng công việc cần thiết phải hoàn thành trước khi task hiện tại có thể được xem là hoàn tất.

### mustRunAfter và shouldRunAfter: ràng buộc thứ tự

mustRunAfter và shouldRunAfter điều chỉnh thứ tự giữa các task khi cả hai đã được chọn vào graph. Chúng không tự thêm task còn thiếu vào graph.

Ví dụ:

~~~groovy
tasks.named('integrationTest') {
    mustRunAfter tasks.named('test')
}
~~~

Nếu cả test và integrationTest đều được chọn, Gradle sắp xếp integrationTest chạy sau test. Nếu chỉ yêu cầu integrationTest, quan hệ này không tự đưa test vào graph.

shouldRunAfter là ràng buộc mềm hơn; Gradle có thể bỏ qua trong một số tình huống để giải quyết graph.

### finalizedBy: task kết thúc

finalizedBy đăng ký task finalizer chạy sau task được finalize khi task đó thực thi. Nó thường được dùng cho việc dọn dẹp, tổng kết hoặc thu thập kết quả:

~~~groovy
tasks.register('cleanupPreview') {
    doLast {
        println 'Cleanup completed'
    }
}

tasks.register('runPreview') {
    doLast {
        println 'Preview work completed'
    }
    finalizedBy 'cleanupPreview'
}
~~~

Task finalizer giúp gắn một công việc hậu xử lý với task chính. Cần thiết kế cẩn thận để tránh tạo chu trình hoặc khiến việc dọn dẹp xóa mất output cần giữ lại.

### So sánh nhanh

| Quan hệ | Thêm task vào graph? | Vai trò |
|---|---|---|
| **dependsOn** | Có | Biểu diễn dependency thực thi |
| **mustRunAfter** | Không | Bắt buộc thứ tự nếu cả hai được chọn |
| **shouldRunAfter** | Không | Đề nghị thứ tự nếu cả hai được chọn |
| **finalizedBy** | Có, khi task được finalize chạy | Chạy công việc kết thúc |

Đừng dùng quan hệ thứ tự thay cho dependency. Nếu task B thực sự cần output của task A, hãy biểu diễn quan hệ dữ liệu hoặc dependency phù hợp để Gradle biết A phải được thực hiện.

## 11. Task graph và một đơn vị công việc được chọn như thế nào?

**Task graph** là đồ thị các task mà Gradle cần thực thi cho một lần gọi build. Gradle bắt đầu từ task được yêu cầu, lần theo các quan hệ dependency và finalizer phù hợp, sau đó sắp xếp graph theo các ràng buộc thứ tự.

Ví dụ:

~~~text
                packagePreview
                 /          \
                v            v
              test           jar
                |             |
                v             v
          testClasses       classes
                |             |
                v             v
         compileTestJava  compileJava
                |
                v
          test dependencies
~~~

Đây là sơ đồ minh họa. Graph thực tế có thể có nhiều nhánh hơn, ví dụ xử lý resource, tạo mã nguồn, kiểm tra định dạng hoặc task do plugin bổ sung.

### Từ lệnh đến graph

Giả sử chạy:

~~~shell
./gradlew :app:build
~~~

Có thể lần theo các bước:

1. Gradle xác định task path :app:build.
2. Task đó được tìm trong project app.
3. Gradle xác định các dependency của task, chẳng hạn assemble và check.
4. Gradle tiếp tục mở rộng graph bằng dependency của các task con.
5. Các ràng buộc thứ tự và finalizer được áp dụng.
6. Gradle thực thi các task đủ điều kiện theo graph.

Task không có trong graph của lệnh này sẽ không chạy chỉ vì nó tồn tại trong project hoặc được liệt kê bởi tasks --all.

### Task graph không phải danh sách mọi task

Một build có thể đăng ký hàng trăm task nhưng mỗi lệnh chỉ chọn một phần nhỏ. Ví dụ:

- **./gradlew :app:compileJava** chọn công việc cần cho compile Java của app.
- **./gradlew :app:test** chọn công việc cần cho test của app, bao gồm các task biên dịch liên quan.
- **./gradlew :app:build** chọn mục tiêu build tổng hợp của app.
- **./gradlew tasks --all** liệt kê task nhưng không có nghĩa tất cả task đó sẽ thực thi.

Đây là lý do cần phân biệt **task tồn tại trong project** với **task được chọn vào task graph**.

## 12. Kết quả thực thi và trạng thái của task

Sau khi Gradle xử lý một task, log hoặc API có thể thể hiện trạng thái tương ứng.

| Trạng thái | Ý nghĩa |
|---|---|
| **Executed / SUCCESS** | Task đã thực hiện action và hoàn tất thành công |
| **FAILED** | Task thực thi nhưng phát sinh lỗi |
| **UP-TO-DATE** | Input/output không thay đổi theo kiểm tra của Gradle nên không cần chạy lại |
| **FROM-CACHE** | Output phù hợp được khôi phục từ build cache |
| **NO-SOURCE** | Không có source input để task xử lý |
| **SKIPPED** | Task bị bỏ qua theo điều kiện hoặc cấu hình |

Tên hiển thị trong console có thể khác cách biểu diễn trong API hoặc phiên bản Gradle. Ví dụ, task thành công thường được hiển thị bằng dòng task không có hậu tố đặc biệt; UP-TO-DATE và FROM-CACHE có hậu tố riêng.

Cần đọc trạng thái cùng với task path và log:

- **UP-TO-DATE** không có nghĩa task không được Gradle xét đến. Gradle đã kiểm tra task và xác định output còn hợp lệ.
- **FROM-CACHE** cho biết output được khôi phục từ cache thay vì thực thi action.
- **NO-SOURCE** có thể là kết quả hợp lệ nếu task không có file nguồn.
- **SKIPPED** cần xem điều kiện bỏ qua hoặc cấu hình liên quan.
- **FAILED** cần xem exception và task path để xác định công việc nào thất bại.

Một task có thể thành công nhưng build tổng thể vẫn thất bại vì task khác trong graph gặp lỗi. Vì vậy, khi đọc log cần tìm task đầu tiên thất bại và quan hệ của nó với task được yêu cầu.

## 13. Cách đọc một task từ build script

Khi nhìn thấy một task trong build script, hãy lần theo các thành phần sau:

~~~groovy
tasks.register('generateIndex') {
    group = 'documentation'
    description = 'Generates an index file'

    inputs.files(fileTree('docs'))
    outputs.file(layout.buildDirectory.file('generated/index.txt'))

    doLast {
        def files = fileTree('docs').files.sort()
        def output = layout.buildDirectory.file('generated/index.txt').get().asFile
        output.parentFile.mkdirs()
        output.text = files.collect { it.name }.join(System.lineSeparator())
    }
}
~~~

Có thể phân tích task generateIndex như sau:

| Thành phần | Điều cần xác định |
|---|---|
| Tên | generateIndex |
| Project | Project chứa đoạn đăng ký task |
| Type | Task mặc định khi đăng ký bằng closure không chỉ định type |
| Group | documentation |
| Description | Tạo file index |
| Input | Các file trong thư mục docs |
| Output | File build/generated/index.txt |
| Action | Lấy danh sách file, sắp xếp tên và ghi vào output |
| Điều kiện thực thi | Task phải được yêu cầu hoặc được dependency đưa vào graph |

Ví dụ này nhằm minh họa cách nhận diện đơn vị công việc. Với task dùng thực tế, nên ưu tiên property input/output được quản lý và khai báo rõ ràng; không nên đọc cùng một input qua nhiều cách khác nhau nếu có thể dùng property đã khai báo. Nếu task cần cache, phải bảo đảm mọi yếu tố ảnh hưởng đến output được khai báo chính xác và task đáp ứng yêu cầu cacheability.

## 14. Những nhầm lẫn thường gặp

| Dễ nhầm | Cách hiểu đúng |
|---|---|
| Task type chính là task | Type là lớp mô tả hành vi; task instance là công việc cụ thể |
| Task name là định danh duy nhất toàn build | Tên task có thể lặp lại ở nhiều project; task path xác định chính xác vị trí |
| Đăng ký task nghĩa là task đã chạy | Registration chỉ đưa task vào model; task cần được chọn vào graph mới thực thi |
| Mọi task đều trực tiếp xử lý file | Task tổng hợp có thể chỉ điều phối task khác |
| tasks --all chạy tất cả task | Lệnh này liệt kê task; nó không thực thi toàn bộ danh sách |
| mustRunAfter tương đương dependsOn | Một cái chỉ sắp xếp thứ tự; một cái tạo dependency thực thi |
| Task xuất hiện trong graph luôn chạy action | Task có thể up-to-date, lấy từ cache, không có source hoặc bị skip |
| Mọi logic nên đặt trong build script | Logic công việc nên đặt trong task action hoặc task type để chỉ chạy khi task được thực thi |
| tasks.create và tasks.register giống nhau về thời điểm tạo | register hỗ trợ lazy registration; create tạo task ngay |
| Task thành công nghĩa là toàn build thành công | Một task có thể thành công trong khi task khác trong graph thất bại |

## 15. Quy trình xác định một đơn vị công việc

Khi cần hiểu hoặc điều tra một task, có thể đi theo trình tự thực tế sau:

1. **Xác định lệnh Gradle**: lệnh gọi task nào, có truyền project path hay không.
2. **Xác định task path**: tìm task thuộc root project hay subproject.
3. **Tìm task definition**: dùng tasks --all và help --task; tìm nơi plugin hoặc build script đăng ký task nếu cần.
4. **Xác định type**: task mặc định, task type do Gradle cung cấp hay custom task type.
5. **Đọc cấu hình**: group, description, property, input, output và điều kiện.
6. **Đọc action**: xác định công việc thực sự được thực hiện.
7. **Lần theo dependency**: xem task nào cần chạy trước và quan hệ nào chỉ điều chỉnh thứ tự.
8. **Xem graph và trạng thái**: dùng --dry-run, --info và kết quả task để hiểu hành vi trong lần build cụ thể.

Ví dụ, với lệnh:

~~~shell
./gradlew :app:generateIndex --info
~~~

cần xác định task generateIndex thuộc project app, tìm nơi đăng ký task, xem input/output và action, rồi đọc log để biết task có chạy hay được đánh dấu up-to-date hoặc skip. Nếu task phụ thuộc vào task khác, hãy mở rộng điều tra theo graph.

Một đơn vị công việc chỉ được hiểu đầy đủ khi biết **nó là task nào, thuộc project nào, được tạo từ type nào, xử lý input/output nào, có action gì và được đưa vào graph bằng cách nào**. Những thông tin đó tạo thành nền tảng để đọc build script, dự đoán lệnh Gradle và điều tra lỗi thực thi.
