# Cấu hình được nạp khi nào và công việc thực thi diễn ra khi nào

Trong Gradle, một lệnh build không chạy toàn bộ file build script theo kiểu “đọc đến đâu làm công việc đến đó”. Gradle chia một lần build thành các giai đoạn có trách nhiệm khác nhau. Trước tiên, Gradle xác định build gồm những project nào; tiếp theo, nó nạp và cấu hình build logic để biết những task nào tồn tại và chúng liên hệ với nhau ra sao; cuối cùng, Gradle thực thi các task được chọn.

Sự khác biệt này rất quan trọng khi viết build.gradle hoặc plugin. Một dòng code nằm trực tiếp ở cấp cao nhất của build script thường chạy trong giai đoạn cấu hình. Một đoạn code nằm trong doLast hoặc phương thức @TaskAction mới là công việc của task khi bước thực thi diễn ra. Nếu đặt thao tác sai giai đoạn, build có thể chậm, tạo side effect không mong muốn, đọc dữ liệu quá sớm hoặc không tận dụng được khả năng cache của Gradle.

Bài học này giải thích thời điểm cấu hình được nạp, thời điểm task được tạo và cấu hình, lúc task graph được xác định, và khi nào các hành động thực sự chạy.

## 1. Ba giai đoạn chính của một lần build

Gradle tổ chức vòng đời build thành ba giai đoạn chính:

1. **Initialization (khởi tạo):** xác định build và các project tham gia.
2. **Configuration (cấu hình):** nạp build scripts, áp dụng plugin, tạo/cấu hình task và xác định quan hệ giữa chúng.
3. **Execution (thực thi):** chạy các task cần thiết theo task graph đã xác định.

~~~mermaid
flowchart TD
    A["Gradle Wrapper / Gradle CLI"] --> B["Initialization"]
    B --> C["Đọc settings và xác định projects"]
    C --> D["Configuration"]
    D --> E["Nạp build scripts và plugins"]
    E --> F["Đăng ký, cấu hình tasks"]
    F --> G["Xác định task graph"]
    G --> H["Execution"]
    H --> I["Chạy task actions"]
    I --> J["Build result, outputs và reports"]
~~~

Có thể nhớ ba giai đoạn bằng ba câu hỏi:

| Giai đoạn | Câu hỏi cần trả lời |
|---|---|
| Initialization | Build gồm những project nào? |
| Configuration | Cần làm những task nào và chúng phụ thuộc nhau ra sao? |
| Execution | Các task đã chọn cần thực hiện công việc gì? |

Ví dụ, khi chạy:

~~~bash
./gradlew :orders-service:build
~~~

Gradle cần biết project orders-service tồn tại ở đâu, plugin nào áp dụng cho project đó, task build được nối với những task nào, và cuối cùng thực thi các task cần thiết như compile, test hoặc assemble theo cấu hình hiện hành.

Không phải mọi dòng code trong build script đều là công việc build được thực hiện ở giai đoạn Execution. Nhiều dòng chỉ mô tả hoặc cấu hình công việc cho những task sẽ chạy sau đó.

## 2. Initialization: Gradle xác định build và project

Giai đoạn Initialization bắt đầu trước khi Gradle cấu hình các project. Gradle xác định build root, đọc settings script và xây dựng mô hình project.

File quan trọng nhất trong giai đoạn này thường là:

- settings.gradle hoặc settings.gradle.kts.
- Các thiết lập plugin management và repository dành cho plugin.
- Các lệnh include hoặc includeBuild để khai báo project/build liên quan.
- Init script được cấu hình cho môi trường Gradle, nếu có.

Ví dụ settings script:

~~~groovy
rootProject.name = 'commerce-platform'

include 'orders-service'
include 'catalog-service'
include 'shared-library'
~~~

Đoạn này khai báo tên root project và các subproject. Nó không biên dịch Java, không chạy test và không tạo JAR. Nó giúp Gradle biết cấu trúc build để có thể tiếp tục cấu hình.

Với composite build, includeBuild đưa một build độc lập khác vào quan hệ phối hợp với build hiện tại. Đây cũng là thông tin về cấu trúc build, không phải một yêu cầu trực tiếp để thực thi toàn bộ task của build được include.

### 2.1. Initialization không phải nơi xử lý nghiệp vụ của task

Settings script có thể chứa logic để chọn project, cấu hình plugin resolution hoặc điều chỉnh cấu trúc build. Tuy nhiên, không nên biến settings script thành nơi biên dịch, đọc/ghi dữ liệu ứng dụng hoặc chạy những thao tác có side effect của từng task.

Ví dụ, đoạn sau thuộc trách nhiệm cấu trúc build:

~~~groovy
include 'orders-service'
include 'shared-library'
~~~

Trong khi đó, việc biên dịch source nên thuộc task compile trong project phù hợp. Tách đúng trách nhiệm giúp Gradle hiểu cấu trúc build trước khi xác định công việc cần chạy.

## 3. Configuration: nạp build logic và mô tả công việc

Sau Initialization, Gradle chuyển sang Configuration. Đây là lúc Gradle đánh giá build scripts của các project cần cấu hình, áp dụng plugin, tạo extension, đăng ký task, thiết lập dependency và các quy tắc khác.

Ví dụ:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.0'
}

tasks.test {
    useJUnitPlatform()
}
~~~

Những dòng trên mô tả cách project được cấu hình:

- Áp dụng Java plugin.
- Đặt group và version.
- Khai báo repository.
- Khai báo dependency.
- Cấu hình task test sử dụng JUnit Platform.

Chúng không trực tiếp chạy toàn bộ test ngay tại vị trí khai báo. Chúng chuẩn bị mô hình để Gradle biết khi task test được thực thi thì task đó phải dùng cấu hình nào.

### 3.1. Code ở cấp cao nhất của build script chạy trong Configuration

Xét ví dụ:

~~~groovy
println 'Evaluating orders-service build script'

tasks.register('showMessage') {
    doLast {
        println 'Hello from task execution'
    }
}

println 'Finished configuring orders-service'
~~~

Khi project được cấu hình và task showMessage được chạy, có thể quan sát thứ tự khái quát:

~~~text
Evaluating orders-service build script
Finished configuring orders-service
Hello from task execution
~~~

Hai lệnh println ở cấp cao nhất là code trong build script nên chạy khi script được đánh giá ở Configuration. Lệnh println nằm trong doLast là task action nên chạy ở Execution nếu task được chọn và không bị skip.

Đây là điểm phân biệt cốt lõi:

| Vị trí code | Thời điểm thường chạy | Vai trò |
|---|---|---|
| Code trực tiếp ở cấp cao nhất build script | Configuration | Thiết lập project/build model |
| Nội dung cấu hình trong plugin hoặc extension | Configuration | Mô tả hành vi build |
| Closure cấu hình task | Khi task được cấu hình/realize | Thiết lập task |
| doFirst / doLast | Execution | Thực hiện task action |
| Phương thức @TaskAction | Execution | Thực hiện logic chính của custom task |

Closure cấu hình task không tự động đồng nghĩa với task action. Nội dung trong closure cấu hình dùng để thiết lập thuộc tính, input, output hoặc action của task. Muốn thực hiện công việc khi task chạy, cần đặt code vào action thích hợp.

### 3.2. Cấu hình dependency không có nghĩa dependency đã được dùng trong ứng dụng

Khai báo:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

đưa dependency vào mô hình cấu hình của Gradle. Việc resolve một configuration và tải artifact có thể diễn ra khi configuration đó được tiêu thụ bởi task hoặc logic khác. Không nên suy luận rằng chỉ vì build script đã khai báo dependency thì mọi thư viện đã được tải và đưa vào mọi classpath.

Gradle sử dụng dependency configuration để phân biệt các mục đích như compile, runtime và test. Task tiêu thụ configuration phù hợp sẽ xác định dependency cần thiết cho công việc của nó.

## 4. Execution: khi task thực sự làm việc

Sau Configuration, Gradle xác định task graph cho yêu cầu build hiện tại. Task graph gồm các task được yêu cầu trực tiếp và những task cần thiết thông qua quan hệ phụ thuộc.

Ví dụ:

~~~bash
./gradlew :orders-service:build
~~~

Task build là task được yêu cầu. Với Java plugin, lifecycle task build thường liên kết đến các bước verification và assembly. Task graph có thể chứa các task như:

~~~text
:orders-service:compileJava
:orders-service:processResources
:orders-service:classes
:orders-service:compileTestJava
:orders-service:processTestResources
:orders-service:test
:orders-service:jar
:orders-service:check
:orders-service:assemble
:orders-service:build
~~~

Danh sách thực tế phụ thuộc plugin và cấu hình. Gradle sắp xếp thứ tự theo quan hệ dependency và các ràng buộc ordering.

Trong Execution, Gradle kiểm tra trạng thái task và chạy action cần thiết. Một task có thể:

- Thực thi action vì output cần được tạo/cập nhật.
- Được đánh dấu UP-TO-DATE vì input/output không thay đổi theo mô hình task.
- Khôi phục output từ build cache (FROM-CACHE).
- Bị skip theo điều kiện.
- Không có source phù hợp (NO-SOURCE).
- Thất bại (FAILED).

Vì vậy, Execution không có nghĩa mọi task trong graph đều chạy action. Gradle có thể xác định output đã hợp lệ và bỏ qua việc thực thi lại.

### 4.1. Task action chạy ở đâu?

Với task được viết bằng DSL, có thể khai báo action:

~~~groovy
tasks.register('generateGreeting') {
    doLast {
        println 'Generating greeting...'
        def output = layout.buildDirectory.file('generated/greeting.txt').get().asFile
        output.parentFile.mkdirs()
        output.text = 'Hello Gradle'
    }
}
~~~

Closure bên trong doLast là công việc được thực hiện khi task chạy. Nếu task không được chọn, closure này không chạy. Nếu task bị skip hoặc output được tái sử dụng theo cơ chế phù hợp, action cũng có thể không được gọi.

Một task có thể có nhiều action. doFirst thêm action chạy trước các action khác, còn doLast thêm action ở cuối. Chúng đều là action của task trong Execution, khác với code cấu hình ở bên ngoài.

### 4.2. Custom task với @TaskAction

Khi cần đóng gói logic build thành một task có input/output rõ ràng, có thể định nghĩa task type:

~~~groovy
abstract class GenerateGreeting extends DefaultTask {
    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @Input
    abstract Property<String> getMessage()

    @TaskAction
    void generate() {
        def file = outputFile.get().asFile
        file.parentFile.mkdirs()
        file.text = message.get()
    }
}

tasks.register('generateGreeting', GenerateGreeting) {
    outputFile.set(layout.buildDirectory.file('generated/greeting.txt'))
    message.set('Hello from a custom task')
}
~~~

Trong ví dụ:

- Lớp task định nghĩa thuộc tính input và output.
- Closure trong tasks.register cấu hình task.
- Phương thức generate() được đánh dấu @TaskAction.
- Gradle gọi phương thức đó khi task thực sự được thực thi.

Việc khai báo input/output giúp Gradle hiểu task đọc dữ liệu gì và tạo file nào. Đây là nền tảng để incremental build và build cache hoạt động đúng.

## 5. Task registration, task configuration và task execution là ba việc khác nhau

Khi đọc Gradle build script, cần phân biệt ba hoạt động:

1. **Registration:** thông báo với Gradle rằng một task có tên và kiểu cụ thể tồn tại.
2. **Configuration:** thiết lập thuộc tính và hành vi của task.
3. **Execution:** chạy các action của task khi task được chọn và cần thực thi.

Ví dụ:

~~~groovy
def greetingTask = tasks.register('greet') {
    group = 'help'
    description = 'Prints a greeting'
    doLast {
        println 'Hello'
    }
}
~~~

tasks.register đăng ký task theo cách lazy. Gradle trả về TaskProvider để tham chiếu task mà không nhất thiết phải tạo/realize đối tượng task ngay tại thời điểm đăng ký.

Task chỉ chạy khi được đưa vào task graph và cần thực thi. Đăng ký task không có nghĩa task đã chạy.

### 5.1. tasks.register và tasks.create

Hai API này có hành vi khác nhau:

| API | Hành vi | Khi nào phù hợp |
|---|---|---|
| tasks.register("name") | Đăng ký task lazy qua TaskProvider | Cách ưu tiên trong build logic hiện đại |
| tasks.create("name") | Tạo và realize task ngay | Chỉ dùng khi cần tạo task eager hoặc trong API cũ cần tương thích |

Ví dụ lazy:

~~~groovy
def packageTask = tasks.register('packageDistribution') {
    doLast {
        println 'Packaging distribution'
    }
}
~~~

Ví dụ eager:

~~~groovy
def packageTask = tasks.create('packageDistribution') {
    doLast {
        println 'Packaging distribution'
    }
}
~~~

Cả hai ví dụ đều định nghĩa action; không ví dụ nào thực thi action ngay chỉ vì task được đăng ký/tạo. Khác biệt nằm ở thời điểm task object được realize và chi phí cấu hình.

Với build có nhiều project và nhiều task, đăng ký lazy giúp Gradle tránh cấu hình những task không cần thiết khi chúng không được sử dụng. Đây là một phần quan trọng của configuration avoidance.

### 5.2. tasks.named tham chiếu task đã đăng ký

Nếu task đã tồn tại, có thể cấu hình nó thông qua tasks.named:

~~~groovy
tasks.named('test') {
    useJUnitPlatform()
}
~~~

Cách này tạo tham chiếu lazy tới task có tên test. Nó thường được ưu tiên hơn việc lấy task object trực tiếp nếu mục tiêu chỉ là cấu hình task.

Với task mới đăng ký, có thể dùng TaskProvider để nối quan hệ hoặc cấu hình tiếp:

~~~groovy
def generateTask = tasks.register('generateMetadata') {
    doLast {
        println 'Generate metadata'
    }
}

tasks.register('packageMetadata') {
    dependsOn(generateTask)
    doLast {
        println 'Package metadata'
    }
}
~~~

Task packageMetadata phụ thuộc generateMetadata. Khi chạy task package, Gradle đưa task sinh metadata vào graph và đảm bảo dependency chạy trước theo quan hệ task.

## 6. Task graph được xác định trước khi thực thi

Task graph là tập hợp task cần thực hiện cho invocation hiện tại cùng với các quan hệ phụ thuộc và ordering. Gradle phải biết graph trước khi bắt đầu chạy các task action.

Ví dụ:

~~~groovy
tasks.register('prepare') {
    doLast {
        println 'Prepare inputs'
    }
}

tasks.register('compileCustom') {
    dependsOn('prepare')
    doLast {
        println 'Compile custom sources'
    }
}

tasks.register('packageCustom') {
    dependsOn('compileCustom')
    doLast {
        println 'Package custom output'
    }
}
~~~

Nếu gọi:

~~~bash
./gradlew packageCustom
~~~

Gradle xác định graph có prepare, compileCustom và packageCustom. Quan hệ dependsOn làm cho task phụ thuộc được đưa vào graph và thực thi trước task phụ thuộc vào nó.

Có ba khái niệm cần phân biệt:

- dependsOn tạo quan hệ phụ thuộc: task được phụ thuộc cần tham gia graph.
- mustRunAfter quy định thứ tự nếu cả hai task đã có trong graph, nhưng tự nó không thêm task còn thiếu.
- shouldRunAfter đưa ra gợi ý thứ tự mềm nếu phù hợp; nó cũng không tự thêm task vào graph.

Ví dụ:

~~~groovy
tasks.named('packageCustom') {
    mustRunAfter('verifyCustom')
}
~~~

Đoạn này không bảo đảm verifyCustom sẽ chạy khi chỉ gọi packageCustom. Muốn bắt buộc verification tham gia graph, cần khai báo dependency hoặc một lifecycle task phù hợp.

Task finalizer cũng có thể được cấu hình bằng finalizedBy để chạy một task sau task được finalize, ví dụ dọn tài nguyên test. Finalizer có quy tắc riêng và cần được dùng cẩn thận để bảo đảm cleanup phù hợp ngay cả khi task chính thất bại.

## 7. Lazy configuration và Provider API

Gradle khuyến khích mô hình lazy để chỉ cấu hình và lấy giá trị khi cần. Các API như TaskProvider và Provider cho phép mô tả một giá trị sẽ được cung cấp sau này mà không cần lấy giá trị ngay lập tức.

Ví dụ:

~~~groovy
def targetName = providers.gradleProperty('targetName')
    .orElse('local')

tasks.register('showTarget') {
    doLast {
        println 'Target: ' + targetName.get()
    }
}
~~~

providers.gradleProperty tạo Provider cho Gradle property. orElse cung cấp giá trị mặc định nếu property không được truyền. Giá trị được lấy bằng get() trong task action, vì vậy việc tiêu thụ giá trị diễn ra khi task chạy.

Có thể gọi:

~~~bash
./gradlew showTarget -PtargetName=staging
~~~

Kết quả sẽ sử dụng giá trị staging. Nếu không truyền property, giá trị mặc định local được dùng.

### 7.1. Đọc giá trị sớm có thể làm mất tính lazy

Xét ví dụ:

~~~groovy
def targetName = providers.gradleProperty('targetName').orElse('local').get()

tasks.register('showTarget') {
    doLast {
        println 'Target: ' + targetName
    }
}
~~~

Ở đây, get() được gọi trực tiếp khi build script được đánh giá. Giá trị được resolve trong Configuration. Điều này có thể phù hợp nếu cấu hình project thực sự cần quyết định ngay dựa trên giá trị đó, nhưng không nên làm nếu chỉ cần giá trị khi task thực thi.

Khi lấy giá trị sớm, build logic có thể:

- Đọc dữ liệu không cần thiết cho task đang được gọi.
- Khiến việc cấu hình phụ thuộc vào trạng thái môi trường.
- Tạo thêm công việc trong Configuration.
- Làm giảm khả năng tái sử dụng configuration cache.
- Khó phân biệt input của task với trạng thái bên ngoài.

Một nguyên tắc hữu ích: giữ giá trị dưới dạng Provider hoặc Property càng lâu càng phù hợp; chỉ resolve khi có lý do rõ ràng và tại giai đoạn cần sử dụng.

### 7.2. Provider cho biến môi trường

Gradle cung cấp API để đọc biến môi trường:

~~~groovy
def deployRegion = providers.environmentVariable('DEPLOY_REGION')
    .orElse('local')

tasks.register('showRegion') {
    doLast {
        println 'Deploy region: ' + deployRegion.get()
    }
}
~~~

Provider mô tả nguồn giá trị. Nếu gọi get() ngay ở cấp cao nhất, giá trị sẽ được lấy trong Configuration. Nếu giữ Provider và tiêu thụ trong task action, giá trị được lấy khi task action chạy.

Với task cần biến môi trường làm input, nên khai báo nó như một property input của task. Điều đó giúp Gradle biết giá trị nào ảnh hưởng tới output và hỗ trợ up-to-date checking chính xác hơn.

Không nên đọc toàn bộ environment và để task phụ thuộc ngầm vào nhiều biến không được mô tả. Hãy xác định rõ biến nào thực sự là input.

## 8. Những thao tác nào nên chạy ở Configuration, thao tác nào nên chạy ở Execution?

Một cách phân chia thực tế:

| Công việc | Giai đoạn phù hợp | Lý do |
|---|---|---|
| Đặt group/version của project | Configuration | Là metadata của project |
| Áp dụng plugin | Configuration | Plugin bổ sung model và task |
| Khai báo dependency | Configuration | Mô tả dependency graph |
| Đăng ký task và cấu hình thuộc tính | Configuration | Chuẩn bị task model |
| Xác định task phụ thuộc nhau | Configuration/task graph | Gradle cần graph trước khi chạy |
| Biên dịch Java | Execution | Là công việc của compile task |
| Chạy test | Execution | Là action của test task |
| Sinh file output | Execution | Tạo output theo input của task |
| Đóng gói JAR | Execution | Tạo artifact |
| Upload/publish artifact | Execution của task/job phù hợp | Có side effect cần điều kiện rõ ràng |
| Xóa output của task clean | Execution | Là action của clean task |

Không phải mọi API được gọi trong Configuration đều là sai. Configuration chính là nơi mô tả build. Vấn đề là tránh thực hiện công việc nặng hoặc có side effect không thuộc trách nhiệm cấu hình ở giai đoạn này.

### 8.1. Những việc nên tránh ở cấp cao nhất build script

Ví dụ không tốt:

~~~groovy
// Chạy lệnh hệ thống ngay khi build script được đánh giá
def result = 'git rev-parse HEAD'.execute().text.trim()

// Đọc file lớn ngay trong Configuration
def schemaText = file('schema.json').text

// Gọi endpoint mạng ngay trong Configuration
def remoteConfig = new URL('https://example.invalid/config').text
~~~

Những đoạn code này thực hiện process, đọc file hoặc truy cập mạng ngay trong Configuration. Chúng có thể chạy trong các invocation không cần task tương ứng, kéo dài thời gian cấu hình, làm kết quả phụ thuộc vào trạng thái bên ngoài và gây khó khăn cho configuration cache.

Nếu dữ liệu đó thực sự là input của task, hãy đưa thao tác đọc/xử lý vào task action và khai báo input tương ứng. Nếu dữ liệu cần quyết định cấu hình project, hãy cân nhắc một nguồn cấu hình được quản lý rõ ràng, có tính ổn định và phù hợp với configuration cache.

### 8.2. Không dùng afterEvaluate để trì hoãn mọi vấn đề

afterEvaluate đăng ký callback chạy sau khi project được đánh giá trong Configuration. Nó vẫn là cơ chế của giai đoạn cấu hình, không phải task action trong Execution.

Ví dụ:

~~~groovy
afterEvaluate {
    println 'Project evaluation finished'
}
~~~

Đoạn này không chờ đến lúc task chạy. Nó chỉ chạy sau khi phần đánh giá project kết thúc. Lạm dụng afterEvaluate có thể làm thứ tự cấu hình khó hiểu, tạo phụ thuộc giữa project và gây khó tương thích với configuration cache hoặc các mô hình cấu hình mới.

Trong nhiều trường hợp, có thể dùng Provider API, plugin callback phù hợp hoặc cấu hình lazy thay vì dựa vào callback toàn cục sau đánh giá.

## 9. Điều kiện thực thi của task cũng có thời điểm riêng

Một số API không quyết định cấu hình project, nhưng kiểm tra điều kiện ngay trước khi task action chạy.

Ví dụ:

~~~groovy
tasks.register('publishArtifact') {
    onlyIf {
        providers.gradleProperty('publish').orNull == 'true'
    }

    doLast {
        println 'Publishing artifact'
    }
}
~~~

onlyIf kiểm tra điều kiện thực thi của task. Nếu điều kiện không thỏa, task bị skip và action trong doLast không chạy.

Một cách khác là cấu hình thuộc tính enabled của task. Nếu đặt enabled = false trong Configuration, task bị vô hiệu hóa theo cấu hình. Cần phân biệt việc quyết định task có được phép chạy với việc thực hiện công việc bên trong task.

Với logic kiểm tra điều kiện phức tạp, cần tránh truy cập mạng hoặc tạo side effect trong predicate. Hãy thiết kế điều kiện từ input đã biết, có thể quan sát và phù hợp với yêu cầu của Gradle.

## 10. Configuration cache ảnh hưởng thế nào đến thời điểm nạp cấu hình?

Configuration cache cho phép Gradle lưu kết quả của giai đoạn cấu hình để tái sử dụng ở invocation sau khi các điều kiện phù hợp. Khi cache được sử dụng, Gradle có thể bỏ qua việc đánh giá lại build scripts và khôi phục mô hình đã lưu, sau đó tiếp tục Execution.

Ví dụ:

~~~bash
./gradlew :orders-service:build --configuration-cache
~~~

Ở lần chạy đầu, Gradle thực hiện Configuration và có thể lưu configuration cache nếu build logic tương thích. Ở lần chạy sau với cùng yêu cầu và các input cấu hình không đổi, Gradle có thể tái sử dụng cache.

Điều này làm rõ vì sao không nên đặt side effect tùy tiện ở cấp cao nhất build script. Nếu một build script gửi request mạng, ghi file hoặc đọc trạng thái không được quản lý trong Configuration, việc tái sử dụng kết quả cấu hình có thể khiến hành vi không còn giống kỳ vọng.

Để tương thích tốt hơn với configuration cache:

- Giữ build script tập trung vào việc mô tả project và task.
- Đưa công việc thực thi vào task action.
- Khai báo input/output của task rõ ràng.
- Tránh truy cập trực tiếp đối tượng Gradle hoặc Project từ task action theo cách không được hỗ trợ.
- Tránh dùng mutable global state hoặc static state để truyền dữ liệu giữa các task.
- Sử dụng Provider/Property và các API được Gradle hỗ trợ.
- Kiểm tra thông báo configuration cache khi chạy build với tùy chọn tương ứng.

Configuration cache không phải build cache. Configuration cache lưu kết quả cấu hình build; build cache lưu output của task có thể tái sử dụng. Hai cơ chế phục vụ hai giai đoạn khác nhau.

| Cơ chế | Tái sử dụng điều gì? | Giai đoạn liên quan |
|---|---|---|
| Configuration cache | Kết quả cấu hình/task graph cho invocation phù hợp | Configuration |
| Build cache | Output của task cacheable | Execution |
| Up-to-date checking | Output hiện tại khi input/output chưa thay đổi | Quyết định có cần chạy task ở Execution |

## 11. Cách quan sát thời điểm cấu hình và thực thi

Có thể dùng log đơn giản để hiểu code chạy ở giai đoạn nào.

~~~groovy
println 'CONFIGURATION: build script is being evaluated'

tasks.register('phaseDemo') {
    println 'TASK CONFIGURATION: task is being configured'

    doFirst {
        println 'EXECUTION: first task action'
    }

    doLast {
        println 'EXECUTION: last task action'
    }
}
~~~

Dòng TASK CONFIGURATION chỉ xuất hiện khi task được realize và closure cấu hình được áp dụng. Với task đăng ký lazy, thời điểm này có thể muộn hơn so với lúc script được đánh giá, hoặc task có thể không được realize nếu không cần thiết.

Để quan sát task graph:

~~~bash
./gradlew :orders-service:build --dry-run
~~~

--dry-run giúp hiển thị task dự kiến mà không chạy task action. Gradle vẫn phải thực hiện các bước cần thiết để cấu hình build và xác định graph. Do đó, nếu code cấp cao nhất của build script in log hoặc có side effect, chúng vẫn có thể xảy ra trong dry run.

Để có log chi tiết hơn:

~~~bash
./gradlew :orders-service:build --info
~~~

Có thể bật configuration cache để quan sát việc lưu và tái sử dụng cấu hình:

~~~bash
./gradlew :orders-service:build --configuration-cache
~~~

Khi đọc log, hãy phân biệt thông báo từ build script, thông báo khi task được cấu hình và thông báo từ task action. Chúng có thể xuất hiện trong cùng một terminal nhưng thuộc các giai đoạn khác nhau.

## 12. Ví dụ tổng hợp: một task sinh file

Giả sử dự án cần sinh file metadata từ một Gradle property. Ta muốn:

- Giá trị mặc định là local.
- Người dùng có thể truyền giá trị khác bằng -PtargetName=....
- File output nằm trong build directory.
- Task chỉ tạo file khi task được gọi.
- Gradle biết input và output để đánh giá task.

Một ví dụ task:

~~~groovy
abstract class GenerateTargetMetadata extends DefaultTask {
    @Input
    abstract Property<String> getTargetName()

    @OutputFile
    abstract RegularFileProperty getOutputFile()

    @TaskAction
    void generate() {
        def output = outputFile.get().asFile
        output.parentFile.mkdirs()
        output.text = 'target=' + targetName.get() + '\n'
        logger.lifecycle('Generated metadata for ' + targetName.get())
    }
}

tasks.register('generateTargetMetadata', GenerateTargetMetadata) {
    targetName.convention(
        providers.gradleProperty('targetName').orElse('local')
    )
    outputFile.set(
        layout.buildDirectory.file('generated/metadata/target.properties')
    )
}
~~~

Khi chạy:

~~~bash
./gradlew generateTargetMetadata -PtargetName=staging
~~~

Diễn biến khái quát:

1. Initialization xác định build và project.
2. Configuration áp dụng plugin và đăng ký task generateTargetMetadata.
3. Gradle xây dựng task graph từ yêu cầu command line.
4. Gradle xác định task có cần thực thi hay output có thể tái sử dụng.
5. Nếu task cần chạy, @TaskAction thực hiện việc ghi file.
6. File output xuất hiện trong build directory của project.

Nếu chỉ chạy một task khác không phụ thuộc generateTargetMetadata, task này không cần được thực thi. Nhờ đăng ký lazy và khai báo input/output, build không phải tạo file metadata trong mọi invocation.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Build script được đọc là task đã chạy | Build script thường được đánh giá trong Configuration để tạo mô hình build |
| Code ở cấp cao nhất build.gradle chạy khi task thực thi | Code đó thường chạy trong Configuration |
| Closure của tasks.register là task action | Closure này cấu hình task; action cần nằm trong doLast, doFirst hoặc @TaskAction |
| Đăng ký task nghĩa là task sẽ chạy | Task chỉ chạy nếu được đưa vào graph và cần thực thi |
| dependsOn chỉ sắp xếp thứ tự | Nó tạo quan hệ phụ thuộc và đưa task cần thiết vào graph |
| mustRunAfter tự thêm task vào graph | Nó chỉ quy định thứ tự nếu cả hai task đã có trong graph |
| --dry-run bỏ qua Configuration | Gradle vẫn cần cấu hình build và xác định task graph |
| clean buộc mọi task thực thi lại | Build cache hoặc các cơ chế khác vẫn có thể tái sử dụng output |
| afterEvaluate là cách chạy logic trong Execution | Nó vẫn thuộc Configuration |
| Configuration cache và build cache là một | Một bên tái sử dụng cấu hình, bên kia tái sử dụng output task |

## 14. Checklist xác định đúng thời điểm thực thi

Khi viết hoặc đọc build logic, hãy tự hỏi:

- [ ] Đoạn code này đang mô tả cấu hình project hay thực hiện công việc?
- [ ] Code ở cấp cao nhất có đọc file, gọi process hoặc truy cập mạng không cần thiết không?
- [ ] Task được đăng ký lazy bằng tasks.register khi phù hợp không?
- [ ] Closure cấu hình task có bị nhầm với task action không?
- [ ] Công việc tạo file/biên dịch/test/package đã nằm trong task action phù hợp chưa?
- [ ] Task có khai báo input/output để Gradle hiểu tác động của nó không?
- [ ] Quan hệ giữa task dùng dependsOn, mustRunAfter và finalizedBy đúng mục đích không?
- [ ] Giá trị từ Gradle property hoặc environment có bị resolve quá sớm không?
- [ ] Logic cấu hình có tương thích với configuration cache không?
- [ ] Đã dùng --dry-run, --info hoặc configuration cache để quan sát khi cần chưa?

## Kết luận

Gradle nạp cấu hình và thực thi công việc ở những giai đoạn khác nhau. Initialization xác định build và project; Configuration đánh giá build scripts, áp dụng plugin, đăng ký/cấu hình task và xác định task graph; Execution chạy action của những task được chọn và cần thực thi.

Code ở cấp cao nhất build script thường thuộc Configuration. Closure cấu hình task thiết lập thuộc tính và hành vi; doFirst, doLast và @TaskAction mới là nơi thực hiện công việc của task. Khi giữ đúng ranh giới này, build logic dễ hiểu hơn, task được cấu hình lazy hiệu quả hơn, input/output rõ ràng hơn và configuration cache có cơ hội hoạt động tốt hơn.
