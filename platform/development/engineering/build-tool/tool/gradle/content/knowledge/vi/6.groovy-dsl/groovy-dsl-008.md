# Lỗi thường gặp do tên thuộc tính, kiểu dữ liệu và thời điểm cấu hình trong Gradle Groovy DSL

## 1. Mục tiêu bài học

Gradle Groovy DSL dùng cú pháp ngắn gọn, ví dụ **version = '1.0'**, **dependencies { implementation 'group:module:version' }** hoặc **tasks.register('hello') { ... }**. Sự linh hoạt của Groovy tạo ra ba loại lỗi rất phổ biến:

- **Tên thuộc tính**: tên có đúng chính tả và thuộc Project, plugin extension, task, đối tượng trong block hay biến Groovy không?
- **Kiểu dữ liệu**: giá trị đang là String, Integer, Boolean, File, Provider, Property hay một loại đối tượng có kiểu khác?
- **Thời điểm cấu hình**: lúc truy cập giá trị, plugin/task đã được tạo chưa; logic đang chạy ở configuration hay execution; giá trị đã được cung cấp hoặc khóa chưa?

Bài học giúp bạn phân biệt nguyên nhân thực của **unknown property**, **could not find method**, **cannot set value**, **no value available** và tình trạng “build thành công nhưng hành vi sai”. Bạn sẽ biết cách tra API, sửa đúng đối tượng và áp dụng các API lazy hiện đại mà không cần dựa vào **afterEvaluate** cho mọi tình huống.

## 2. Cơ chế tên thuộc tính trong Groovy DSL

### 2.1. Không phải mọi tên đều thuộc Project

Ở cấp cao nhất của **build.gradle**, **version** và **group** thông thường là thuộc tính của đối tượng **Project**:

~~~groovy
group = 'com.example'
version = '1.0.0'

println project.group
println project.version
~~~

Nhưng khi vào block cấu hình task:

~~~groovy
tasks.register('inspect') {
    group = 'verification'
    description = 'Kiểm tra cấu hình'
    doLast {
        println 'Inspection complete'
    }
}
~~~

**group** ở đây là **Task.group**, không phải **Project.group**. Nếu cần cả hai, viết rõ:

~~~groovy
project.group = 'com.example'

tasks.register('inspect') {
    group = 'verification'
}
~~~

Sự trùng tên tạo ra lỗi khó thấy: hai giá trị đều hợp lệ, build vẫn có thể chạy, nhưng module được publish với group hoặc task được hiển thị ở nhóm sai nếu đặt nhầm block.

Trong **application { ... }**, một tên như **mainClass** thuộc Application plugin extension; trong **dependencies { ... }**, **implementation** được giải quyết trên dependency handler với configuration tương ứng; trong **tasks.named('jar') { ... }**, **archiveBaseName** thuộc archive task. Một tên có nghĩa ở một block không bảo đảm có nghĩa ở block khác.

### 2.2. Property syntax, getter/setter và method call

Groovy cho phép viết **project.version** thay **project.getVersion()**, và **project.version = '1.0'** thay **project.setVersion('1.0')** khi API có các getter/setter thích hợp. Nhưng những lời gọi sau có ý nghĩa khác nhau:

~~~groovy
repositories {
    mavenCentral()           // gọi phương thức
}

version = '1.0'              // gán property
~~~

Viết nhầm **mavenCentral = true** hoặc **version('1.0')** có thể gây lỗi do đang gọi sai loại API. Khi Javadoc chỉ hiện method **getX()**, **setX(...)**, hãy đối chiếu với Groovy DSL Reference để xác định tên property. Tên Groovy phân biệt chữ hoa/thường: **mainClass** khác **mainclass** và **archiveBaseName** khác **archiveBasename**.

### 2.3. Local variable, extra property, build property

Ba trường hợp sau không đồng nghĩa:

~~~groovy
def localTag = 'preview'           // biến local của script
ext.releaseChannel = 'preview'    // extra property gắn trên Project
def releaseTag = providers.gradleProperty('release.tag').orElse('dev')
~~~

- **localTag** là biến lexical của Groovy; không tự trở thành project property.
- **releaseChannel** là extra property gắn trên đối tượng Project; chỗ khác muốn đọc phải truy cập đúng đối tượng và phạm vi.
- **releaseTag** ở ví dụ là **Provider<String>** được tạo từ Gradle property cấp build, có mặc định **dev**.

**providers.gradleProperty('key')** có thể đọc từ **-P**, các nguồn Gradle property có quy định ưu tiên và **gradle.properties** phù hợp. Nó không tự đọc mọi extra property hoặc **gradle.properties** của từng thư mục subproject. Trong Gradle 9.x, tra property động theo cha ở multi-project đã bị deprecated; nên dùng input cấp build rõ ràng hoặc truyền cấu hình tường minh thay vì ngầm tìm ở parent.

## 3. Lỗi tên thuộc tính và cách sửa

### 3.1. Sai chính tả hoặc tên API đã đổi

**Đoạn sai để nhận biết lỗi, không đưa vào build chạy thật:**

~~~groovy
plugins {
    id 'application'
}

application {
    mainClas = 'demo.Main' // sai: thiếu chữ s
}
~~~

**Đúng:**

~~~groovy
application {
    mainClass = 'demo.Main'
}
~~~

Nếu báo **Could not set unknown property 'mainClas' for extension ...**, kiểm tra tên theo đúng tài liệu plugin và bản Gradle hiện dùng. Đừng đổi bừa một tên API theo ví dụ cũ trên Internet.

Với task **Jar**, property hiện đại là **archiveBaseName**:

~~~groovy
plugins {
    id 'java'
}

tasks.named('jar', Jar) {
    archiveBaseName.set('sample-library')
}
~~~

Tên **archiveBaseNames** hoặc **archiveBasename** không tương đương. Mỗi **Property<T>** có kiểu dữ liệu và API riêng; cách viết **set(...)** làm rõ đang cấu hình property chứ không gọi hàm bất kỳ.

### 3.2. Plugin chưa tạo ra block hoặc configuration

Ví dụ sau sai vì chưa áp dụng plugin tương ứng:

~~~groovy
application {
    mainClass = 'demo.Main'
}
~~~

**application** không phải từ khóa của ngôn ngữ Groovy, mà là DSL block do plugin cung cấp. Cấu hình đúng:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.Main'
}
~~~

Tương tự, configuration **implementation** trong **dependencies { implementation '...' }** được cung cấp bởi plugin hỗ trợ Java (chẳng hạn **java**, **java-library**, **application**). Khi gặp **Could not find method implementation() on dependency handler**, xác minh plugin và block trước khi sửa tọa độ dependency.

### 3.3. Có property nhưng đang cấu hình sai đối tượng

Ví dụ:

~~~groovy
version = '2.0'

tasks.register('packageReport') {
    version = '4.0'
}
~~~

Đây không phải ví dụ cần chạy: **Task** thông thường không có property **version** của Project. Thay vì đặt version trong task, hãy dùng **project.version = '2.0'** bên ngoài block task; nếu task cần đọc version, truyền một giá trị đầu vào rõ ràng.

Mẫu kiểm tra khi có lỗi property:

1. Xem **đối tượng** được nhắc tới trong thông báo: root project, task, extension, dependencies hoặc settings.
2. Kiểm tra **plugin** đã được áp dụng và phiên bản plugin có hỗ trợ property đó.
3. Tra **Groovy DSL Reference** hoặc Javadoc của đúng đối tượng.
4. Kiểm tra dấu hoa/thường, các hậu tố **Name**, **File**, **Directory**, tên singular/plural.
5. Xác định xem đây là property **được đọc**, **được gán** hay **phương thức có tham số**.

### 3.4. Tên task và tên project không phải cùng một namespace

**project(':utils')** chỉ một subproject đã được include trong **settings.gradle**; **tasks.named('utils')** tìm một task tên **utils**. Nếu không có task **test** ở project hiện tại, **tasks.named('test')** thất bại dù subproject khác có task **:service:test**. Dùng:

~~~bash
./gradlew projects
./gradlew tasks --all
./gradlew :service:tasks --all
~~~

Lệnh cuối chỉ hợp lệ khi **:service** thực sự tồn tại. Trong build nhiều module, nên gọi task với path đầy đủ **:module:task** và tránh suy đoán tên từ thư mục vật lý.

## 4. Lỗi kiểu dữ liệu: String, Boolean, Integer, File và Provider

### 4.1. Chuỗi 'false' vẫn là truthy trong Groovy

Đây là lỗi nguy hiểm vì code có thể **không báo lỗi**:

~~~groovy
def enabled = 'false'
if (enabled) {
    println 'BẬT'
}
~~~

**Stdout:**

~~~text
BẬT
~~~

Groovy xem **String không rỗng** là true khi kiểm tra truthiness. Trong khi đó **-Pfeature.enabled=false** đưa vào một chuỗi **'false'**, không phải Boolean false. Vì thế viết **if (project.findProperty('feature.enabled'))** có thể chạy nhầm nhánh.

Hãy parse nghiêm ngặt:

~~~groovy
def featureEnabled = providers.gradleProperty('feature.enabled').map { raw ->
    if (raw != 'true' && raw != 'false') {
        throw new GradleException('feature.enabled phải là true hoặc false')
    }
    raw == 'true'
}.orElse(false)
~~~

Đây là **Provider<Boolean>** có mặc định false. Đọc giá trị ở nơi thực sự cần. Cách **Boolean.parseBoolean('typo')** trả về false cho chuỗi bất kỳ không phải **true** nên có thể che giấu lỗi cấu hình; khi người dùng chỉ được nhập hai lựa chọn, hãy validate như trên.

### 4.2. Project property chứa số vẫn thường là chuỗi

File **gradle.properties**:

~~~properties
demo.repeat=3
~~~

Đừng mặc định đây là kiểu int. Có thể map và kiểm tra phạm vi:

~~~groovy
def repeatCount = providers.gradleProperty('demo.repeat').map { raw ->
    int parsed = Integer.parseInt(raw)
    if (parsed < 1 || parsed > 5) {
        throw new GradleException('demo.repeat phải nằm trong [1, 5]')
    }
    parsed
}.orElse(2)
~~~

**repeatCount** là Provider đại diện cho Integer. Nếu **-Pdemo.repeat=abc**, **Integer.parseInt** thất bại khi provider được tính; lỗi thuộc input build, không phải lỗi class Java. Nếu không truyền property, giá trị mặc định là 2.

### 4.3. Provider<T> khác Property<T>

| Loại | Bản chất | Cách dùng |
| --- | --- | --- |
| **String**, **int**, **boolean** | Giá trị trực tiếp | Khởi tạo và sử dụng theo kiểu |
| **Provider<T>** | Giá trị có thể được tính sau; thường chỉ đọc | **map**, **flatMap**, **orElse**, **get** |
| **Property<T>** | Property có kiểu, có thể cấu hình bằng giá trị hoặc Provider | **set**, **convention**, **get** |
| **DirectoryProperty**, **RegularFileProperty** | Property thể hiện thư mục/file trong mô hình Gradle | **set**, **dir**, **file** theo API |
| **ListProperty<T>**, **SetProperty<T>**, **MapProperty<K,V>** | Collection property có kiểu | **add**, **addAll**, **put**, **set** |

**Property.set(value)** ghi giá trị; **Property.set(provider)** liên kết đến nguồn giá trị. **Property.convention(default)** đặt mặc định có thể bị ghi đè. **Provider.orElse(default)** cung cấp fallback; **Provider.get()** đọc giá trị thực và có thể thất bại nếu không có dữ liệu.

Ví dụ cho task Java:

~~~groovy
tasks.named('jar', Jar) {
    archiveBaseName.set('dsl-library')
}
~~~

Property này nhận **String**, không phải một Integer, File hoặc boolean tùy ý. Một số API Groovy có thể chuyển kiểu ngầm; đừng trông chờ phép chuyển kiểu tự động khi giá trị đi qua Property/Provider có type rõ ràng.

### 4.4. File path không đồng nghĩa một String hoặc DirectoryProperty

~~~groovy
def pathText = 'reports'                         // String
def pathFile = file('reports')                   // java.io.File
def outputDir = layout.buildDirectory.dir('reports') // Provider<Directory>
~~~

Khi cấu hình task **Copy**, dùng method của chính task:

~~~groovy
tasks.register('copyReports', Copy) {
    from('src/report-templates')
    into(layout.buildDirectory.dir('reports'))
}
~~~

Ví dụ này chỉ tạo kết quả hữu ích nếu có thư mục nguồn; đây là đoạn **minh họa API**, không phải ứng dụng độc lập. Không nhầm **into** với property tên **outputDirectory** của loại task khác. Nếu API yêu cầu **RegularFileProperty**, hãy dùng một file provider phù hợp; nếu API yêu cầu **DirectoryProperty**, dùng directory provider.

### 4.5. Dấu nháy đơn và kép thay đổi giá trị String

~~~groovy
def moduleName = 'billing'
println 'module=$moduleName'
println "module=$moduleName"
~~~

**Stdout:**

~~~text
module=$moduleName
module=billing
~~~

Chuỗi nháy đơn giữ nguyên ký tự **$**; chuỗi nháy kép (GString) cho phép nội suy. Khi build artifact hoặc đường dẫn chứa version, lỗi dấu nháy có thể làm tên file mang ký tự **$** thay vì giá trị. Với giá trị lấy từ Provider, ưu tiên **map** để biến đổi lazily, tránh ép nó thành GString rồi đọc ngay ở configuration.

### 4.6. Java toolchain cần kiểu đúng

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**JavaLanguageVersion.of(17)** tạo đối tượng đúng loại. Nó không đồng nghĩa mọi property tên **languageVersion** đều có thể nhận chuỗi **'17'**. Tra chính API của plugin. Trong ví dụ này, **version = '1.0'** ở project lại hợp lý vì đó là phiên bản artifact, không phải JavaLanguageVersion.

## 5. Lỗi thời điểm: configuration, execution và lazy API

### 5.1. Ba phase của Gradle

~~~text
INITIALIZATION
  settings.gradle(.kts) -> xác định các project tham gia
         |
         v
CONFIGURATION
  build.gradle(.kts) -> plugin, extension, task, dependency, provider wiring
         |
         v
EXECUTION
  chạy task action cần thiết, xử lý input và tạo output
~~~

Mã top-level của build script chạy khi project được cấu hình. Code trong **doLast { ... }** chỉ chạy nếu task được thực thi. Với **tasks.register**, closure cấu hình task có thể không chạy cho đến khi task cần được hiện thực.

~~~groovy
println 'CONFIG: đánh giá build script'

tasks.register('phaseDemo') {
    println 'CONFIG: cấu hình phaseDemo'
    doLast {
        println 'EXEC: chạy phaseDemo'
    }
}
~~~

Khi gọi **./gradlew -q help**, phần top-level có thể in; **phaseDemo** không cần chạy. Khi gọi **./gradlew -q phaseDemo** trong build sạch không dùng configuration cache, ba dòng thường xuất hiện theo thứ tự CONFIG build, CONFIG task, EXEC task. Khi configuration cache được tái sử dụng, các bước cấu hình có thể không chạy lại, vì thế không đặt logic nghiệp vụ vào **println** hoặc side effect tại configuration.

### 5.2. tasks.register, tasks.named và TaskProvider

**tasks.register('taskName')** trả về **TaskProvider**, giúp Gradle không cần hiện thực/configure task khi nó không cần tham gia build. **tasks.create('taskName')** hiện thực task eager. **tasks.named('existingTask')** lấy provider của task đã đăng ký; nếu không có task đó, lệnh có thể thất bại.

Ví dụ chạy được trong build Gradle có cấu hình cơ bản:

~~~groovy
def reportTask = tasks.register('report') {
    doLast {
        println 'Báo cáo'
    }
}

tasks.register('verifyReport') {
    dependsOn(reportTask)
    doLast {
        println 'Xác nhận'
    }
}
~~~

**./gradlew -q verifyReport** in từ hai task action:

~~~text
Báo cáo
Xác nhận
~~~

Quan hệ **dependsOn(reportTask)** chấp nhận TaskProvider. Không cần **reportTask.get()** để buộc tạo task ngay trong configuration. **get()** có thể gây eager realization, làm chậm cấu hình và ảnh hưởng các task khác.

### 5.3. tasks.named và configureEach thay cho eager configuration

Nếu Java plugin đã được áp dụng:

~~~groovy
tasks.named('jar', Jar) {
    archiveBaseName.set('my-library')
}

tasks.withType(Test).configureEach {
    maxHeapSize = '512m'
}
~~~

**tasks.named** phù hợp khi chỉ nhắm đúng một task. **tasks.withType(Test).configureEach** phù hợp khi nhiều task cùng kiểu có thể được đăng ký về sau và muốn cấu hình khi cần. Đoạn **tasks.withType(Test) { ... }** kiểu cũ có thể khiến task bị hiện thực sớm.

Nếu plugin **java** chỉ được áp dụng có điều kiện:

~~~groovy
pluginManager.withPlugin('java') {
    tasks.named('jar', Jar) {
        archiveBaseName.set('my-library')
    }
}
~~~

Callback chỉ thực hiện khi plugin tương ứng xuất hiện. Nếu build luôn có **plugins { id 'java' }**, cách cấu hình trực tiếp đơn giản hơn.

### 5.4. Không dùng afterEvaluate như “thuốc chữa mọi lỗi”

Ví dụ cách sửa thiếu cơ sở:

~~~groovy
afterEvaluate {
    tasks.named('jar', Jar) {
        archiveBaseName.set('library')
    }
}
~~~

**afterEvaluate** trì hoãn callback đến sau khi project được đánh giá nhưng không làm tên property đúng hơn, không tự tạo task thiếu plugin và có thể tạo phụ thuộc thứ tự khó kiểm soát. Gradle khuyến nghị dùng **Provider/Property**, **register/named/configureEach**, hoặc callback **pluginManager.withPlugin**. Chỉ cân nhắc **afterEvaluate** trong trường hợp thật sự được API và thiết kế yêu cầu, sau khi xác định vấn đề.

### 5.5. Provider.get() quá sớm

**Dễ lỗi:**

~~~groovy
def tag = providers.gradleProperty('release.tag').get()
~~~

Nếu không có property **release.tag**, lời gọi có thể báo **Cannot query the value ... because it has no value available**. Đọc ngay ở configuration cũng làm mất tính lazy.

**Tốt khi có mặc định:**

~~~groovy
def tag = providers.gradleProperty('release.tag').orElse('dev')

tasks.register('showTag') {
    doLast {
        println('tag=' + tag.get())
    }
}
~~~

Nếu tag bắt buộc, hãy thiết kế validation với thông báo rõ tên input thiếu; không lặng lẽ mặc định **dev** cho một yêu cầu release production. Cũng đừng suy rằng **mọi get() tự khóa property**: lỗi **value is final and cannot be changed** phụ thuộc trạng thái finalize/disallowChanges hoặc chu kỳ sử dụng property, cần tra nguồn gốc việc khóa.

### 5.6. Cấu hình sau khi giá trị đã khóa

Một số property có thể được finalize bởi Gradle/plugin hoặc bởi logic sử dụng. Khi cố đổi sau đó, thông báo thường nhắc **final and cannot be changed**. Hướng xử lý:

- Cấu hình bằng **set(provider)** hoặc **convention(...)** từ sớm.
- Chỉ đọc giá trị vào thời điểm cần thiết, thường là task action.
- Tránh gán cùng property ở nhiều callback có thứ tự không rõ.
- Tránh chỉnh sửa model của task khác từ **doLast**.
- Nếu task A cần output task B, kết nối qua Provider có task dependency đúng API thay vì đọc file output trước khi task B chạy.

Thay đổi thứ tự dòng ngẫu nhiên có thể làm lỗi tạm biến mất nhưng không giải quyết coupling và lazy behavior.

## 6. Ma trận triệu chứng và nguyên nhân

| Thông báo hoặc hành vi | Nguyên nhân hay gặp | Hướng kiểm tra |
| --- | --- | --- |
| **Could not get unknown property 'x'** | Sai tên, thiếu khai báo, scope/owner không đúng | Xem Project/Task/Extension được nhắc; tra API/plugin |
| **Could not set unknown property 'x'** | Không có setter, sai block hoặc property cũ | Kiểm tra tên property và kiểu đối tượng |
| **Could not find method foo()** | Nhầm method/property, thiếu plugin, sai argument | Xem signature của method và cấu hình plugin |
| **Could not find method implementation()** | Plugin Java không tạo configuration implementation | Thêm đúng plugin nếu module cần Java; không sửa repository một cách tùy tiện |
| **No signature of method ...** | Số lượng hoặc kiểu tham số sai | Kiểm tra overload API, String/number/File/Provider |
| **Cannot set value ... using instance of ...** | Giá trị không khớp **Property<T>** | Dùng đúng type, **set** và Provider thích hợp |
| **'false' nhưng điều kiện vẫn đúng** | String không rỗng là truthy | Parse boolean rõ ràng, validate input |
| **No value available** | **Provider.get()** với property thiếu | **orElse** khi có mặc định hoặc lỗi đầu vào có ngữ cảnh |
| **final and cannot be changed** | Cấu hình muộn sau khi property bị khóa | Tìm điểm finalize, wire sớm và đọc muộn |
| **Task with name 'test' not found** | Plugin/task chưa được đăng ký, sai project | Dùng **tasks --all**, **projects**, đúng task path |
| **Task chưa chạy nhưng code đã in** | Side effect nằm ở top-level configuration | Đặt công việc vào task action |
| **Task đã register nhưng chưa in gì** | Task chưa cần hiện thực hoặc chưa chạy | Gọi đúng task và đặt action trong **doLast** |
| **Build chậm vì nhiều task cấu hình** | **create**, **getByName**, **TaskProvider.get**, **all** | Dùng lazy APIs **register/named/configureEach** |

Nguyên văn lỗi tùy Gradle/plugin version; bảng này là cách định hướng, không phải khẳng định mọi Gradle đều in đúng từng chữ.

## 7. Ví dụ Java 17 và build.gradle hoàn chỉnh

Đây là project **độc lập có thể chạy**, dùng Application plugin và Groovy DSL. Nó minh họa các giải pháp đúng: plugin tạo extension, Java toolchain có type, parse tham số **-P**, task action đọc Provider ở đúng thời điểm, và cấu hình tên JAR bằng Property<String>.

### 7.1. Cấu trúc

~~~text
groovy-dsl-lab/
├── settings.gradle
├── build.gradle
├── gradlew                       # Sinh bằng Gradle Wrapper
├── gradlew.bat                   # Sinh bằng Gradle Wrapper
├── gradle/wrapper/...            # Sinh bằng Gradle Wrapper
└── src/main/java/demo/GroovyDslApp.java
~~~

Nếu máy đã có Gradle CLI, chạy **gradle wrapper** một lần trong root để sinh Wrapper; sau đó dùng Wrapper. Cần JDK có thể chạy bản Gradle được chọn và Java 17 toolchain có sẵn hoặc được cấu hình provisioning phù hợp.

**settings.gradle:**

~~~groovy
rootProject.name = 'groovy-dsl-lab'
~~~

**build.gradle:**

~~~groovy
plugins {
    id 'application'
}

group = 'com.example.learning'
version = '1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.GroovyDslApp'
}

def repeatCount = providers.gradleProperty('demo.repeat').map { raw ->
    int count = Integer.parseInt(raw)
    if (count < 1 || count > 5) {
        throw new GradleException('demo.repeat phải từ 1 đến 5')
    }
    count
}.orElse(2)

def label = providers.gradleProperty('demo.label').orElse('Groovy DSL')

tasks.register('explainConfig') {
    group = 'help'
    description = 'Hiển thị cấu hình an toàn'

    doLast {
        println('label=' + label.get())
        println('repeat=' + repeatCount.get())
    }
}

tasks.named('jar', Jar) {
    archiveBaseName.set('dsl-safety')
}
~~~

**src/main/java/demo/GroovyDslApp.java:**

~~~java
package demo;

public final class GroovyDslApp {
    private GroovyDslApp() {
    }

    public static void main(String[] args) {
        System.out.println("Groovy DSL: Java 17 OK");
    }
}
~~~

File Java phải đúng package và class. Plugin **application** áp dụng hỗ trợ Java, tạo task **run** và **jar**; vì vậy các block **java**, **application**, **tasks.named('jar', Jar)** hợp lệ. **repeatCount** và **label** là Provider; task **explainConfig** đọc chúng khi chạy.

### 7.2. Lệnh chạy và output

**Linux/macOS:**

~~~bash
./gradlew -q explainConfig
./gradlew -q explainConfig -Pdemo.repeat=3 -Pdemo.label=CI
./gradlew -q run
./gradlew jar
~~~

**Windows PowerShell:**

~~~powershell
.\gradlew.bat -q explainConfig
.\gradlew.bat -q explainConfig -Pdemo.repeat=3 -Pdemo.label=CI
.\gradlew.bat -q run
.\gradlew.bat jar
~~~

Không có **demo.repeat** hoặc **demo.label** từ nguồn Gradle property nào, stdout **action explainConfig** mặc định là:

~~~text
label=Groovy DSL
repeat=2
~~~

Khi truyền **-Pdemo.repeat=3 -Pdemo.label=CI**, stdout action là:

~~~text
label=CI
repeat=3
~~~

Dòng do Java main in ra khi gọi **run**:

~~~text
Groovy DSL: Java 17 OK
~~~

Gradle có thể in thêm log task hoặc cảnh báo ngoài stdout ứng dụng. Khi **jar** thành công, file dự kiến là:

~~~text
build/libs/dsl-safety-1.0.jar
~~~

Đây là JAR thông thường, không tự động là fat JAR hoặc có manifest **Main-Class** để dùng trực tiếp **java -jar**. Chạy ứng dụng bằng **run** như trên.

Bạn có thể kiểm tra Java độc lập với Gradle:

~~~bash
mkdir -p out
javac --release 17 -d out src/main/java/demo/GroovyDslApp.java
java -cp out demo.GroovyDslApp
~~~

Lệnh **java** cũng in chính xác **Groovy DSL: Java 17 OK**. Trên PowerShell tạo thư mục bằng **New-Item -ItemType Directory -Force out** trước khi gọi **javac** và **java** tương đương. Biên dịch tay chỉ xác minh Java source, còn xác minh Groovy DSL cần chạy task Gradle.

### 7.3. Thử lỗi có kiểm soát

Chỉ thử một lỗi mỗi lần và hoàn tác trước khi làm lỗi khác:

1. **Sai tên:** đổi **mainClass** thành **mainClas**, chạy **./gradlew help --stacktrace**; lỗi thuộc extension.
2. **Thiếu plugin:** bỏ **id 'application'** nhưng giữ **application { ... }**; Gradle không còn extension (và cũng có thể thiếu cấu hình Java/task).
3. **Sai kiểu số:** chạy **./gradlew -q explainConfig -Pdemo.repeat=abc**; provider thất bại ở parse số.
4. **Sai miền giá trị:** chạy **./gradlew -q explainConfig -Pdemo.repeat=10**; validation **1..5** từ chối.
5. **Sai tên task:** đổi **tasks.named('jar', Jar)** thành **tasks.named('missingJar', Jar)**; Gradle không có task ấy.
6. **Sai thời điểm:** thêm **println 'CONFIG'** ở top-level rồi gọi **./gradlew -q help**; thấy side effect dù không gọi task **explainConfig**. Xóa dòng sau khi quan sát.

Không đưa những ví dụ cố ý lỗi vào bản chạy chuẩn cùng lúc vì bạn sẽ không tách được nguyên nhân đầu tiên và những lỗi dây chuyền.

## 8. Quy trình chẩn đoán theo ba câu hỏi

**Bước 1 — xác minh phiên bản và build:**

~~~bash
./gradlew --version
./gradlew help
~~~

Nếu file build lỗi ở subproject, kiểm tra đúng root và module trước khi tiếp tục.

**Bước 2 — lấy log đủ ngữ cảnh:**

~~~bash
./gradlew help --stacktrace
./gradlew help --warning-mode all
./gradlew tasks --all
~~~

Nếu lỗi nằm ở task action, thay **help** bằng task có lỗi. **--stacktrace** chỉ nơi phát sinh, **--warning-mode all** giúp phát hiện API deprecated. Không đăng toàn bộ log chứa credential lên nơi công khai.

**Bước 3 — phân loại:**

- **Tên:** đang trỏ tới Project, extension, task, DependencyHandler hay biến local? Có plugin tạo property đó chưa? Tên có đúng chữ hoa/thường không?
- **Kiểu:** là String hay Boolean? Số lấy từ **-P** đã parse chưa? API yêu cầu **Property<T>**, Provider hay File?
- **Thời điểm:** code chạy ở phase nào? Task đã được register chưa? Có đọc **get()** trước khi có giá trị? Property đã finalized? Có dựa vào **afterEvaluate** khó dự đoán không?

**Bước 4 — sửa đúng nguồn và kiểm chứng:** sửa một vấn đề, chạy lại **help** (kiểm tra configuration), task cụ thể (kiểm tra execution), rồi **test/build** của dự án. Không dùng **clean** hoặc xóa cache để che lỗi tên property.

~~~text
Lỗi DSL?
    |
    +--> Unknown property / method
    |       kiểm tra tên + scope + plugin
    |
    +--> Argument type / cannot set
    |       kiểm tra String / boolean / số / Provider / Property
    |
    +--> No value / task missing / finalized
            kiểm tra register/named + phase + lazy wiring
    |
    v
Chỉnh đúng đối tượng, đúng type, đúng thời điểm
    |
    v
help -> task liên quan -> test/build
~~~

## 9. Các nguyên tắc cần ghi nhớ

- Dùng **tên API chính xác** từ phiên bản Gradle/plugin đang chạy; sai một chữ cũng có thể tạo một property không tồn tại.
- Đặt cấu hình trên đúng chủ sở hữu: **Project.group** khác **Task.group**; **application.mainClass** khác một tên không rõ scope.
- Với giá trị từ **-P** hoặc **gradle.properties**, hãy **parse và validate** kiểu Boolean/Integer trước khi ra quyết định.
- Ưu tiên **Provider/Property** cho giá trị có thể tính sau; dùng **set/map/flatMap/orElse/convention** theo API và tránh **get()** ở configuration nếu chưa cần.
- Tạo và cấu hình task bằng **register**, **named**, **configureEach**; chỉ dùng eager API khi thực sự có lý do.
- Giữ **side effect** trong task action, không vô tình chạy khi gọi **help**.
- Hạn chế **afterEvaluate** và đổi giá trị sau khi finalized.
- Dùng **Gradle Wrapper**, kiểm tra plugin/JDK tương thích và xem warning khi nâng phiên bản.

## 10. Câu hỏi kiểm tra

1. Vì sao **group** trong block **tasks.register** không nhất thiết là **Project.group**?
2. Tại sao **-Pfeature.enabled=false** có thể khiến **if (value)** vẫn đúng?
3. Khác nhau giữa **def x**, **ext.x** và **providers.gradleProperty('x')**?
4. Vì sao **tasks.named('test')** có thể lỗi dù task **:service:test** tồn tại?
5. **Provider.get()**, **Property.set()** và **orElse()** dùng để làm gì?
6. Vì sao **tasks.register** tốt hơn **tasks.create** cho phần lớn custom task?
7. Vì sao **afterEvaluate** hiếm khi là giải pháp tốt cho lỗi tên hoặc kiểu?
8. Khi gặp thông báo **final and cannot be changed**, cần điều tra thứ tự cấu hình và cơ chế nào?

**Gợi ý:** (1) closure task có chủ sở hữu khác; (2) 'false' là String không rỗng; (3) biến lexical, extra property, Provider của Gradle property build-level; (4) task phụ thuộc project và plugin; (5) đọc, gán và giá trị mặc định; (6) tránh hiện thực task không cần; (7) không sửa tên/type và dễ tạo phụ thuộc thứ tự; (8) thời điểm finalize/disallowChanges và cách wiring provider.

## 11. Tài liệu chính thức

- [Gradle — Groovy Build Script Primer](https://docs.gradle.org/current/userguide/groovy_build_script_primer.html)
- [Gradle — Writing Build Scripts](https://docs.gradle.org/current/userguide/writing_build_scripts_intermediate.html)
- [Gradle — Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html)
- [Gradle — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html)
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html)
- [Gradle — Creating and Registering Tasks](https://docs.gradle.org/current/userguide/writing_tasks.html)
- [Gradle — Working With Files](https://docs.gradle.org/current/userguide/working_with_files.html)
- [Gradle — General Best Practices](https://docs.gradle.org/current/userguide/best_practices_general.html)
- [Gradle — Upgrading Within Gradle 9](https://docs.gradle.org/current/userguide/upgrading_version_9.html)

**Cốt lõi:** khi Groovy DSL lỗi, hãy xác minh **đúng tên trên đúng đối tượng**, **đúng kiểu giá trị** và **đúng thời điểm cung cấp/đọc cấu hình**. Tách ba câu hỏi này giúp sửa nguyên nhân và giữ build nhất quán từ máy cá nhân đến CI.
