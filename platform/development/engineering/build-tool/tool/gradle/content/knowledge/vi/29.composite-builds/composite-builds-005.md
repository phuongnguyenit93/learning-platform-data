# Tham chiếu task giữa các included build trong Gradle Composite Build

## Mục tiêu bài học

Trong Gradle, một **multi-project build** gồm nhiều project chung một build, còn **composite build** kết hợp nhiều **Gradle build độc lập** qua **includeBuild(...)**. Mỗi included build có settings.gradle(.kts), project hierarchy, task graph, repositories và logic cấu hình riêng. Bạn có thể muốn root build điều phối những task ở một hoặc nhiều included builds, chẳng hạn:

- Chạy **:tools:validateStamp** ở included build tools.
- Chạy **:product:app:run** ở included build product.
- Định nghĩa một root task **runProduct** để người dùng chỉ cần gọi ./gradlew runProduct.
- Gộp nhiều bước kiểm tra thành một task trong build điều phối, mà không biến tất cả included builds thành subprojects.

Gradle cung cấp API chính thức:

~~~groovy
tasks.register('runProduct') {
    dependsOn gradle.includedBuild('product').task(':app:run')
}
~~~

**gradle.includedBuild('product')** trả về một **IncludedBuild**; **task(':app:run')** tạo **TaskReference** tới task bên trong build đó. **dependsOn** chấp nhận TaskReference và Gradle đưa task tương ứng vào task graph của composite. Đây không phải **TaskProvider** của project hiện tại và không phải cách truy cập để chỉnh sửa trực tiếp task của build khác.

Sau bài học, bạn có thể:

1. Phân biệt **subproject** và **included build**, cùng không gian tên của build path/task path.
2. Viết **includeBuild(...)** trong settings và hiểu đường dẫn tương đối so với settings directory.
3. Dùng **gradle.includedBuild(name).task(path)** và **gradle.includedBuilds** để tạo task dependencies an toàn.
4. Phân biệt cách gọi CLI **:build-name:subproject:task** và internal path **:subproject:task**.
5. Hiểu **TaskReference**, **TaskProvider**, **Task**, **ProjectDependency** và **external module dependency** khác nhau thế nào.
6. Dùng **dependsOn** để bảo đảm task được chạy, phân biệt nó với **mustRunAfter/shouldRunAfter** chỉ điều phối thứ tự.
7. Xây dựng composite lab chạy được với **hai included builds** và **ứng dụng Java 17**.
8. Hiểu vì sao root task có hai dependsOn không bảo đảm thứ tự giữa hai dependencies.
9. Chẩn đoán lỗi **unknown included build name**, **unknown task path**, **namespace collision** và cấu hình composite thiếu.
10. Biết khi nào cần **dependency substitution**/artifact contract thay vì cố chuyển task output qua TaskReference.
11. Nắm các giới hạn về configuration isolation, command-line tasks, configuration cache và CI.
12. Dùng cả **Groovy DSL** và **Kotlin DSL**, cùng checklist kiểm tra trong dự án thật.

Ví dụ chính dùng **Gradle Groovy DSL** và **Java 17+**. Lab dùng các core Gradle plugins và không có dependency bên ngoài như JUnit, vì vậy việc compile Java source không cần Maven Central. Nếu Gradle Wrapper chưa được cache, máy vẫn có thể cần tải Gradle distribution; cần một Gradle version tương thích với Java 17.

---

## 1. Phân biệt multi-project build và composite build

### 1.1. Multi-project build

Trong một multi-project build:

~~~text
my-build/
├── settings.gradle
├── build.gradle
├── app/
│   └── build.gradle
└── library/
    └── build.gradle
~~~

settings.gradle:

~~~groovy
rootProject.name = 'my-build'
include 'app', 'library'
~~~

**:app** và **:library** là **subprojects** trong cùng một build. Từ app, bạn có thể khai báo:

~~~groovy
dependencies {
    implementation project(':library')
}
~~~

vì :library nằm trong project hierarchy của build hiện tại.

### 1.2. Composite build

Trong composite:

~~~text
composite-root/
├── settings.gradle
├── build.gradle
├── tools/
│   ├── settings.gradle
│   └── build.gradle
└── product/
    ├── settings.gradle
    ├── build.gradle
    └── app/
        └── build.gradle
~~~

Root settings.gradle:

~~~groovy
rootProject.name = 'composite-root'

includeBuild 'tools'
includeBuild 'product'
~~~

**tools** và **product** là **included builds**, không phải subprojects **:tools** và **:product** của root. Chúng có settings files riêng. **product** lại có subproject **:app** bên trong build product.

**Sai**: trong root dùng **project(':product:app')** như một Project object. Project path được giải quyết trong hierarchy của root build, không nhảy qua ranh giới included build.

**Đúng** khi cần một task: dùng **gradle.includedBuild('product').task(':app:run')**.

**Đúng** khi cần code library thuộc included build: dùng module coordinates và dependency substitution, được giải thích ở phần 9.

### 1.3. So sánh nhanh

| Tiêu chí | Multi-project | Composite |
| --- | --- | --- |
| Đơn vị được include | Project qua **include(...)** | Build qua **includeBuild(...)** |
| Settings | Các subprojects chung một settings | Mỗi included build có settings riêng |
| Project path trong root | **project(':library')** hợp lệ nếu include | Không có **project(':product:app')** chỉ vì includeBuild |
| Project dependency | **implementation project(':library')** | External coordinates + substitution khi cần code |
| Tham chiếu task từ root | **tasks.named(...)** hoặc task path của project cùng build | **gradle.includedBuild(...).task(...)** |
| Cấu hình project khác | Có một số APIs trong cùng build, nhưng nên tránh coupling | Không cấu hình trực tiếp Project/Task của included build |
| Repositories và version catalogs | Theo settings/conventions của build | Không tự chia sẻ giữa các builds |
| Task CLI | **:app:run** | **:product:app:run** từ composite root |
| Dùng thích hợp | Các module có cùng lifecycle/settings | Các build phát triển độc lập, build logic hoặc co-development |

### 1.4. Một included build vẫn có thể là multi-project

Composite không có nghĩa mỗi included build chỉ có một project. Nếu **product/settings.gradle** chứa:

~~~groovy
rootProject.name = 'product'
include 'app'
~~~

thì **product** vừa là một independent Gradle build, vừa có một subproject **:app**. Lệnh ở root composite:

~~~bash
./gradlew :product:app:run
~~~

được Gradle hiểu bằng cách phân giải **build-tree path**; còn **task(':app:run')** bên trong IncludedBuild API nhận **task path nội bộ của product build**.

---

## 2. Khai báo includeBuild chính xác

### 2.1. Đường dẫn includeBuild là filesystem directory

Root **settings.gradle**:

~~~groovy
rootProject.name = 'composite-root'
includeBuild 'tools'
includeBuild 'product'
~~~

**includeBuild('tools')** tham chiếu thư mục tools/ tính từ thư mục chứa root settings.gradle. Nó **không** phải project path và không tự đọc một JAR.

Đường dẫn ngoài root cũng hợp lệ:

~~~groovy
includeBuild '../shared-tools'
~~~

Nhưng hardcode absolute path kiểu **/home/alice/work/shared-tools** làm build không portable. Trong monorepo, nên dùng relative paths rõ và đảm bảo các thư mục được checkout đầy đủ.

### 2.2. Included build có settings và build script riêng

Ví dụ **tools/settings.gradle**:

~~~groovy
rootProject.name = 'tools'
~~~

Ví dụ **product/settings.gradle**:

~~~groovy
rootProject.name = 'product'
include 'app'
~~~

Root **composite-root/settings.gradle** không dùng **include 'tools', 'product'** để khai báo chúng như subprojects. Hãy dùng **includeBuild** khi thực sự muốn giữ ranh giới builds.

### 2.3. Included build name và namespace

Gradle sử dụng một **build path/name** để phân biệt included builds trong build tree. Tài liệu Gradle hiện đại mô tả build path thường được suy ra từ thư mục included build, và bạn có thể đổi tên để tránh xung đột:

~~~groovy
includeBuild('tools') {
    name = 'shared-tools'
}
~~~

Lúc này từ including build dùng:

~~~groovy
gradle.includedBuild('shared-tools').task(':help')
~~~

và CLI build-tree path:

~~~bash
./gradlew :shared-tools:help
~~~

**Không tiếp tục dùng 'tools'** trong includedBuild(name) nếu đã đổi tên build path theo cấu hình hiện hành. Nên đồng bộ tên giữa settings, build script và CI.

### 2.4. Các tên phải duy nhất

Gradle yêu cầu **unique build paths** và không để included build path đụng namespace của một project trong root build. Ví dụ root đã có project **:tools**, lại thêm included build path **:tools**, có thể gây collision.

Giải pháp:
- Đổi tên included build path bằng **name = 'aux-tools'**.
- Hoặc đổi project path nếu kiến trúc cho phép.
- Đừng cố xử lý collision bằng việc dựa vào task abbreviation; abbreviation không thay unique identity requirement.

### 2.5. Lựa chọn --include-build trên CLI

Gradle có CLI:

~~~bash
./gradlew --include-build ../shared-tools help
~~~

Đây là cách tạo composite **cho invocation hiện tại** và hỗ trợ dependency substitution. Nhưng nếu build script cố định tham chiếu **gradle.includedBuild('shared-tools')**, CI cần một build name luôn có mặt. Khi đó, đưa includeBuild vào settings thường dễ tái lập và dễ review hơn.

**Plugin builds** có thể cần khai báo **includeBuild(...) trong pluginManagement** để cung cấp plugin được áp qua plugins DSL. Đây là use case riêng, không phải cách mặc định để tham chiếu mọi task Java.

---

## 3. IncludedBuild và TaskReference API

### 3.1. Truy cập included build qua Gradle object

Trong root build.gradle:

~~~groovy
def productBuild = gradle.includedBuild('product')
def runTaskRef = productBuild.task(':app:run')

tasks.register('runProduct') {
    dependsOn runTaskRef
}
~~~

Ở đây:

- **gradle** là Gradle instance của build đang cấu hình.
- **includedBuild('product')** trả về **IncludedBuild**.
- **task(':app:run')** trả về **TaskReference**.
- **dependsOn** chấp nhận TaskReference, nên khi gọi runProduct Gradle thực thi task được tham chiếu theo graph.

### 3.2. TaskReference không phải TaskProvider

Các APIs khác nhau:

| Đối tượng | Ví dụ | Nó đại diện cho gì? |
| --- | --- | --- |
| **Task** | Một task đã được realized trong project hiện tại | Task object có actions, properties, inputs/outputs |
| **TaskProvider** | tasks.named('build') | Provider của task được Gradle quản lý trong TaskContainer hiện tại |
| **TaskReference** | gradle.includedBuild('product').task(':app:run') | Reference tới task của một included build |
| **ProjectDependency** | project(':library') | Dependency tới project trong cùng build |
| **ModuleDependency** | 'com.example:library:1.0' | Module coordinates được resolution/substitution |

**TaskReference** giúp tạo task dependency mà không expose Task object của included build sang root. Nó **không được dùng như một TaskProvider để gọi configure/get/outputs** của task bên kia.

### 3.3. Cú pháp đúng trong Groovy DSL

~~~groovy
tasks.register('runProduct') {
    dependsOn gradle.includedBuild('product').task(':app:run')
}
~~~

Hoặc dạng method call rõ ràng:

~~~groovy
tasks.register('runProduct') {
    dependsOn(
        gradle.includedBuild('product').task(':app:run')
    )
}
~~~

Cả hai biểu đạt cùng ý nghĩa: task runProduct phụ thuộc task **:app:run** trong included build product.

### 3.4. Cú pháp đúng trong Kotlin DSL

~~~kotlin
tasks.register("runProduct") {
    dependsOn(gradle.includedBuild("product").task(":app:run"))
}
~~~

Đây là đối ứng trực tiếp với Groovy. Dùng **TaskReference** như tham số dependsOn, không cần lấy Task object từ included build.

### 3.5. Các properties chính của IncludedBuild

API **IncludedBuild** có:

- **name**: tên included build.
- **projectDir**: thư mục root của included build.
- **task(path)**: reference tới task trong build ấy.

**gradle.includedBuilds** trả collection các included builds được biết trong build hiện tại. Không nên nhầm danh sách này với **allprojects**, **subprojects** hay những projects thuộc một included build khác.

### 3.6. Khi tên không khớp

Nếu bạn viết:

~~~groovy
gradle.includedBuild('unknown-build').task(':help')
~~~

nhưng chưa include một build tên unknown-build, Gradle có thể ném **UnknownDomainObjectException** từ includedBuild(name). Lỗi này nói về **build name không tồn tại**, không phải nhiệm vụ help của Gradle bị thiếu.

Vì thế khi debug, kiểm tra settings.gradle và **includeBuild name** trước khi kiểm tra task path.

---

## 4. Hai lớp đường dẫn task: CLI và IncludedBuild.task

Đây là quy tắc quan trọng nhất để tránh tham chiếu sai task.

Giả sử composite root include **product**, và product include subproject **app**.

### 4.1. Đường dẫn dùng trên CLI từ composite root

~~~bash
./gradlew :product:app:run
~~~

Ý nghĩa:

~~~text
:product   = build path/name của included build
:app       = project path trong product build
:run       = task name trong project app
~~~

### 4.2. Đường dẫn truyền vào IncludedBuild.task

~~~groovy
gradle.includedBuild('product').task(':app:run')
~~~

Bên trong **task(':app:run')**, đường dẫn đã được tính **tương đối với root của included build product**, dưới dạng absolute project task path. **Không thêm prefix product lần thứ hai**.

Sai:

~~~groovy
gradle.includedBuild('product').task(':product:app:run')
~~~

Vì included build product không có project con **:product** trong hierarchy của nó.

### 4.3. Task root của included build

Build **tools** có task ở root tên writeStamp.

CLI từ composite root:

~~~bash
./gradlew :tools:writeStamp
~~~

API trong root build script:

~~~groovy
gradle.includedBuild('tools').task(':writeStamp')
~~~

Một cách nhớ: **CLI cần build prefix**, còn **IncludedBuild.task() đã biết build prefix qua includedBuild(name)**.

### 4.4. Khi included build có nhiều subprojects

Nếu **product/settings.gradle**:

~~~groovy
rootProject.name = 'product'
include 'app', 'shared'
~~~

Task **:shared:compileJava** trong product build được root tham chiếu bằng:

~~~groovy
gradle.includedBuild('product').task(':shared:compileJava')
~~~

và trên CLI:

~~~bash
./gradlew :product:shared:compileJava
~~~

Ví dụ này chỉ chạy nếu shared có Java plugin và task compileJava thực sự tồn tại.

### 4.5. Không lấy subproject bằng project() xuyên build

Sai:

~~~groovy
dependencies {
    implementation project(':product:app')
}
~~~

**:product:app** là build-tree path cho CLI, nhưng không phải project path thuộc root build. Muốn dùng library từ included build, hãy dựa vào **external module coordinates + dependency substitution**. Muốn chạy task của nó, dùng **TaskReference**.

---

## 5. Lab chạy được: composite root + tools + product

Lab có ba Gradle builds: **composite-root** (build điều phối), **tools** (included build gốc có task ghi/kiểm tra file), **product** (included build có subproject app Java 17).

Hai included builds **độc lập về tác vụ**. Product Java app không đọc file tools tạo, nên root có thể dependsOn cả hai mà không áp đặt thứ tự giữa chúng. Đây là thiết kế có chủ đích để làm rõ semantics của **dependsOn**.

### 5.1. Cấu trúc thư mục

~~~text
composite-task-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── tools/
│   ├── settings.gradle
│   └── build.gradle
└── product/
    ├── settings.gradle
    ├── build.gradle
    └── app/
        ├── build.gradle
        └── src/main/java/lab/app/Main.java
~~~

**Wrapper** phải được Gradle tạo hoặc lấy từ project tin cậy; đây là file thực tế bắt buộc khi chạy **./gradlew**. Không tự chế gradle-wrapper.jar. JDK 17 phải có sẵn hoặc toolchain auto-provisioning được cấu hình; bản lab dưới đây giả định JDK17 đã có.

### 5.2. composite-task-lab/settings.gradle

~~~groovy
rootProject.name = 'composite-task-lab'

includeBuild 'tools'
includeBuild 'product'
~~~

Đừng thay **includeBuild** bằng **include 'tools', 'product'**, vì điều đó tạo một multi-project build khác kiến trúc.

### 5.3. tools/settings.gradle

~~~groovy
rootProject.name = 'tools'
~~~

Build này có root project tools, không có subproject bắt buộc.

### 5.4. tools/build.gradle

~~~groovy
plugins {
    id 'base'
}

def stampFile = layout.buildDirectory.file(
    'generated/stamp.txt'
)

tasks.register('writeStamp') {
    group = 'verification'
    description = 'Create a deterministic text stamp'

    outputs.file(stampFile)

    doLast {
        def file = stampFile.get().asFile
        file.parentFile.mkdirs()
        file.setText('STAMP_OK', 'UTF-8')
        println 'Tools: stamp created'
    }
}

tasks.register('validateStamp') {
    group = 'verification'
    description = 'Verify the generated stamp'

    dependsOn tasks.named('writeStamp')
    inputs.file(stampFile)

    doLast {
        def actual = stampFile.get().asFile.getText('UTF-8')
        if (actual != 'STAMP_OK') {
            throw new GradleException('Unexpected stamp content')
        }
        println 'Tools: stamp verified'
    }
}
~~~

Giải thích:
- **writeStamp** là task root của included build tools, dùng Gradle **layout.buildDirectory.file** thay vì hardcode output path trong code của root.
- **outputs.file** khai báo output để Gradle áp dụng up-to-date checks thích hợp.
- **validateStamp** phụ thuộc writeStamp **trong cùng build tools**, do đó có thứ tự nội bộ rõ.
- **inputs.file** chỉ ra dữ liệu validateStamp đọc.
- Không có dự án root composite truy cập trực tiếp đối tượng Task của tools.

File sinh ra trong build tools:

~~~text
tools/build/generated/stamp.txt
~~~

Nội dung đúng là:

~~~text
STAMP_OK
~~~

Với lần chạy mới từ trạng thái chưa có output, writeStamp in:

~~~text
Tools: stamp created
~~~

Với lần chạy sau, **writeStamp có thể UP-TO-DATE** và không in dòng này nữa. **validateStamp** vẫn có thể in:

~~~text
Tools: stamp verified
~~~

Không so khớp toàn bộ Gradle console output byte-for-byte vì trạng thái UP-TO-DATE và task order có thể khác theo môi trường.

### 5.5. product/settings.gradle

~~~groovy
rootProject.name = 'product'

include 'app'
~~~

**app** là subproject thuộc included build product. Build này có thể được mở/chạy độc lập bằng Gradle cài tại máy hoặc Wrapper riêng nếu tổ chức trang bị; composite root wrapper không tự tạo Wrapper file bên trong product.

### 5.6. product/build.gradle

~~~groovy
plugins {
    id 'base'
}
~~~

Đây là root build script tối thiểu cho product. Subproject app sẽ tự áp application plugin.

### 5.7. product/app/build.gradle

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

application {
    mainClass = 'lab.app.Main'
}
~~~

**application plugin** tạo **:app:run** trong included build product. **options.release=17** bảo đảm Java 17 target. Các core plugins không cần Maven Central.

### 5.8. product/app/src/main/java/lab/app/Main.java

~~~java
package lab.app;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("App: composite build OK");
    }
}
~~~

Class Java 17 hợp lệ, không có imports ngoài JDK. Tên file, package và mainClass đã khớp.

### 5.9. composite-task-lab/build.gradle

~~~groovy
plugins {
    id 'base'
}

def stampValidation = gradle.includedBuild('tools')
        .task(':validateStamp')

def appClasses = gradle.includedBuild('product')
        .task(':app:classes')

def appRun = gradle.includedBuild('product')
        .task(':app:run')

tasks.register('runProduct') {
    group = 'verification'
    description = 'Run the Java app in included build product'

    dependsOn appRun

    doLast {
        println 'Root: product run complete'
    }
}

tasks.register('verifyIncludedBuilds') {
    group = 'verification'
    description = 'Verify tools stamp and compile product app'

    dependsOn stampValidation, appClasses

    doLast {
        println 'Root: verification complete'
    }
}

tasks.register('fullDemo') {
    group = 'verification'
    description = 'Run both composite orchestration tasks'

    dependsOn tasks.named('verifyIncludedBuilds'),
              tasks.named('runProduct')

    doLast {
        println 'Root: full demo complete'
    }
}
~~~

Điểm cốt lõi:
- **appRun, appClasses, stampValidation** là TaskReference, không phải Project/Task objects.
- **runProduct** phụ thuộc task :app:run của product.
- **verifyIncludedBuilds** phụ thuộc task :validateStamp của tools **và** :app:classes của product.
- **fullDemo** phụ thuộc hai root tasks; không cố cấu hình task nội bộ của product hoặc tools.
- Product app không phụ thuộc file tools tạo, vì vậy không có data race khi hai branches được chạy song song.

### 5.10. Chạy trực tiếp task của included build từ root

Tại composite-task-lab:

~~~bash
./gradlew :tools:writeStamp
~~~

Khi output chưa có, phần stdout của task:

~~~text
Tools: stamp created
~~~

Tạo file tools/build/generated/stamp.txt chứa **STAMP_OK**.

Chạy:

~~~bash
./gradlew :tools:validateStamp
~~~

Stdout task khi kiểm tra thành công:

~~~text
Tools: stamp verified
~~~

Chạy ứng dụng:

~~~bash
./gradlew :product:app:run
~~~

Stdout của Java main chính xác:

~~~text
App: composite build OK
~~~

Gradle còn có task logs và BUILD SUCCESSFUL; ba khối stdout trên chỉ nêu những dòng do code trong lab in.

### 5.11. Chạy root task tham chiếu included build

~~~bash
./gradlew runProduct
~~~

Phần output có ý nghĩa:

~~~text
App: composite build OK
Root: product run complete
~~~

Vì runProduct **dependsOn appRun**, Java app được chạy trước root doLast. Log Gradle task names còn xuất hiện nhưng không nằm trong hai dòng minh họa.

### 5.12. Chạy root task phụ thuộc hai included builds

~~~bash
./gradlew verifyIncludedBuilds
~~~

Output quan sát gồm (không cam kết thứ tự giữa nhánh compile product và stamp validation):

~~~text
Tools: stamp verified
Root: verification complete
~~~

**Root: verification complete** được in sau khi cả hai dependencies hoàn thành thành công. Task **:product:app:classes** không in stdout của Main vì nó chỉ compile classes, không chạy app.

Khi chạy từ trạng thái sạch, tools writeStamp cũng có thể in **Tools: stamp created**, còn Gradle hiển thị compilation task logs.

### 5.13. Chạy toàn bộ demo

~~~bash
./gradlew fullDemo
~~~

Các dòng từ code root/app/tools có thể gồm:

~~~text
Tools: stamp verified
App: composite build OK
Root: verification complete
Root: product run complete
Root: full demo complete
~~~

**Không dùng đoạn trên như thứ tự stdout bắt buộc**: hai root prerequisite tasks của fullDemo và các dependencies của chúng có thể được Gradle lập lịch theo thứ tự khác, đặc biệt nếu bật parallel execution. Điều chắc chắn là **Root: full demo complete** chỉ in sau khi cả hai root tasks phụ thuộc đã hoàn thành thành công.

### 5.14. Windows PowerShell

Từ thư mục composite-task-lab:

~~~powershell
.\gradlew.bat :tools:writeStamp
.\gradlew.bat :tools:validateStamp
.\gradlew.bat :product:app:run
.\gradlew.bat runProduct
.\gradlew.bat verifyIncludedBuilds
.\gradlew.bat fullDemo
~~~

Java source và Groovy build scripts là như nhau trên Windows. Nếu máy báo không tìm được JDK17 toolchain, chạy **.\gradlew.bat -q javaToolchains** để kiểm tra installation; không thay task path để chữa JDK problem.

### 5.15. Biên dịch Main.java độc lập với javac

Nếu muốn xác nhận mã Java không phụ thuộc Gradle, tại root lab:

Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
    -d out product/app/src/main/java/lab/app/Main.java
java -cp out lab.app.Main
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out product\app\src\main\java\lab\app\Main.java
java -cp out lab.app.Main
~~~

Stdout chính xác:

~~~text
App: composite build OK
~~~

Đây là chương trình Java 17 **runnable độc lập**. Nó kiểm tra source code và output, nhưng **không chứng minh composite task references đã được cấu hình đúng**; phần đó phải xác minh bằng Gradle commands.

---

## 6. dependsOn, mustRunAfter và shouldRunAfter khác nhau ra sao?

### 6.1. dependsOn tạo task dependency

~~~groovy
tasks.register('runProduct') {
    dependsOn gradle.includedBuild('product').task(':app:run')
}
~~~

Khi yêu cầu runProduct, Gradle phải đưa :app:run vào graph. Nếu :app:run còn phụ thuộc compileJava/classes, những prerequisites đó cũng được thực hiện.

### 6.2. mustRunAfter chỉ là ràng buộc thứ tự

Task API của Gradle chấp nhận **TaskReference** cho task ordering:

~~~groovy
tasks.register('announce') {
    mustRunAfter gradle.includedBuild('product').task(':app:run')

    doLast {
        println 'Announcement task completed'
    }
}
~~~

Nếu **announce** và **product :app:run** cùng có mặt trong task graph, Gradle bắt announce chạy sau appRun. Nhưng lệnh:

~~~bash
./gradlew announce
~~~

không tự kéo appRun vào graph chỉ vì mustRunAfter. Muốn chạy app trước announce một cách tất yếu, dùng **dependsOn**.

### 6.3. shouldRunAfter có tính mềm hơn

~~~groovy
tasks.register('announce') {
    shouldRunAfter gradle.includedBuild('product').task(':app:run')
}
~~~

Nó chỉ định ưu tiên thứ tự khi cả hai tasks cùng được lên lịch; Gradle có thể bỏ qua ưu tiên này trong một số tình huống scheduling, ví dụ để tránh deadlock/cycle khi ràng buộc mềm không thể thỏa.

**shouldRunAfter không kéo task khác vào graph**. Không dùng nó để bảo đảm file producer tồn tại.

### 6.4. Hai dependencies không có thứ tự lẫn nhau

~~~groovy
tasks.register('verifyIncludedBuilds') {
    dependsOn(
        gradle.includedBuild('tools').task(':validateStamp'),
        gradle.includedBuild('product').task(':app:classes')
    )
}
~~~

Gradle bảo đảm verifyIncludedBuilds chỉ chạy sau cả hai tasks. **Nó không bảo đảm tools task chạy trước product task hoặc ngược lại.**

Vì thế lab thiết kế hai nhánh không chia sẻ dữ liệu. Nếu product thật sự cần output do tools sinh trước, chỉ liệt kê cả hai trong dependsOn của root task **không đủ để mô hình hóa một input→output dependency trực tiếp giữa chúng**.

### 6.5. Khi task B cần output của task A thuộc build khác

Đừng tạo một chuỗi dependsOn ở root rồi đoán đó là dependency artifact. Những lựa chọn đúng hơn:

- Đóng output thành **module/artifact được publish hoặc được included build expose qua dependency substitution**, khi nó là library hoặc một component có coordinates.
- Tách tool generation và consumer vào cùng build, dùng **TaskProvider/Provider<File>** hoặc consumable configuration với producer provenance.
- Tạo một contract artifact/repository được quản lý rõ, với version, hash, inputs và lifecycle, thay vì đường dẫn tùy tiện vào build/ của bên kia.
- Nếu thực sự cần orchestration hai giai đoạn, dùng CI workflow có stage dependencies rõ, đồng thời vẫn định nghĩa output artifacts và nơi consumer tải; **không gọi hai Gradle commands liên tiếp trong một Exec task rồi nghĩ có task dependency đầy đủ**.

Quan trọng: **IncludedBuild.task(path) là reference để scheduling, không phải API xuất file outputs** cho consumer.

### 6.6. finalizedBy và cleanup

Gradle có Task.finalizedBy để gắn cleanup/finisher tasks. Nhưng với included build, không nên coi một TaskReference như Task object có thể thêm arbitrary finalizer bên trong included build. Nếu cần cleanup của chính tools, hãy định nghĩa và cấu hình cleanup **trong tools/build.gradle**. Root có thể gọi một task entrypoint hợp lệ của tools; included build tự quản lifecycle nội bộ.

---

## 7. Dùng gradle.includedBuilds khi cần nhiều build

### 7.1. Danh sách included builds

Gradle API:

~~~groovy
def builds = gradle.includedBuilds
~~~

Trả collection các **IncludedBuild** được build hiện tại biết tới. Không trộn với **subprojects** hay toàn bộ nested project hierarchy.

### 7.2. Tham chiếu cùng một task path từ mọi included build

Gradle docs đưa ví dụ Groovy spread operator. Trong lab, mọi Gradle build đều có core **help** task:

~~~groovy
tasks.register('helpIncluded') {
    group = 'help'
    dependsOn gradle.includedBuilds*.task(':help')
}
~~~

Kotlin DSL:

~~~kotlin
tasks.register("helpIncluded") {
    dependsOn(gradle.includedBuilds.map { it.task(":help") })
}
~~~

Dùng:

~~~bash
./gradlew helpIncluded
~~~

Mục đích là minh họa **map IncludedBuild → TaskReference**. Các help tasks của included builds có thể in nhiều đoạn help output; đó là bình thường.

### 7.3. Không dùng tên task chỉ có ở một build cho tất cả

Sai về thiết kế:

~~~groovy
tasks.register('runEverything') {
    dependsOn gradle.includedBuilds*.task(':app:run')
}
~~~

Trong lab, **tools** không có subproject :app và không có :app:run. Khi Gradle resolve/exe task references, build tools có thể báo **task path not found**. Muốn chạy :app:run, chỉ chọn **gradle.includedBuild('product')**.

### 7.4. Khi tên tasks khác nhau

~~~groovy
tasks.register('verifyExplicit') {
    dependsOn(
        gradle.includedBuild('tools').task(':validateStamp'),
        gradle.includedBuild('product').task(':app:classes')
    )
}
~~~

Cách khai báo tường minh phù hợp hơn khi builds có cấu trúc khác nhau. Không dùng wildcard task names rồi tự bỏ qua các builds không có task.

### 7.5. Không dùng gradle.includedBuilds làm scanner toàn filesystem

Collection này chỉ phản ánh builds đã được include trong invocation/settings. Nó **không đi quét mọi thư mục con** hay tìm Gradle projects chưa khai báo. Nếu có một repo mới cần điều phối, phải include đúng trong settings và kiểm soát unique build path.

---

## 8. Task path, build path và namespace collision

### 8.1. Task path có hai hệ quy chiếu

| Mục đích | Ví dụ | Cách hiểu |
| --- | --- | --- |
| Include directory | includeBuild 'product' | Đường dẫn thư mục từ settings |
| Build path/name | product | Định danh included build trong build tree |
| Internal project path | :app | Subproject của product |
| Internal task path | :app:run | Task của project :app trong product |
| Build-tree CLI path | :product:app:run | Đường dẫn đầy đủ từ composite root |
| IncludedBuild API | includedBuild('product').task(':app:run') | Name + internal task path, không lặp prefix |

### 8.2. Root task và included root task có thể cùng tên

Root có **:help**, tools cũng có **:help**. Chúng là hai task identities:

~~~bash
./gradlew :help
./gradlew :tools:help
~~~

Trong API:

~~~groovy
gradle.includedBuild('tools').task(':help')
~~~

không trả root help task. Điều này là chủ ý: task paths được phân biệt bởi build identity.

### 8.3. Collision vì included build name trùng root subproject

Ví dụ root:

~~~groovy
include 'tools'
includeBuild 'tools-build'
~~~

Nếu tools-build được đặt build name tools, namespace có thể trùng root project :tools. Hãy dùng:

~~~groovy
includeBuild('tools-build') {
    name = 'aux-tools'
}
~~~

rồi tham chiếu **gradle.includedBuild('aux-tools')**.

### 8.4. CLI abbreviation không thay identity

Gradle hỗ trợ viết tắt build/project/task paths trong một số trường hợp nếu không mơ hồ. Tuy nhiên trong scripts/CI, dùng **fully qualified paths** và **exact names** để ổn định khi repository thêm tasks mới.

Ví dụ ưu tiên:

~~~bash
./gradlew :product:app:run
~~~

thay vì viết tắt tên trong automation.

---

## 9. Task reference khác dependency substitution

Composite build thường được giới thiệu với **dependency substitution**: build consumer khai báo dependency theo **group:name:version**, Gradle tự dùng project từ included build thay artifact đã publish khi coordinates phù hợp.

Điều này **khác hoàn toàn** với việc root task phụ thuộc một task của included build.

### 9.1. Khi cần thực thi một công việc

~~~groovy
tasks.register('runProduct') {
    dependsOn gradle.includedBuild('product').task(':app:run')
}
~~~

Mục đích là **chạy task**, không đưa product classes lên compiler classpath của root.

### 9.2. Khi cần dùng code của included build

Trong root consumer build có Java plugin, ví dụ:

~~~groovy
dependencies {
    implementation 'org.example:shared-utils:1.0'
}
~~~

Nếu settings include một build có project **group='org.example'**, **project.name='shared-utils'**, Gradle có thể thay module dependency bằng local project theo default substitution.

**Không dùng**:

~~~groovy
dependencies {
    implementation project(':shared-utils')
}
~~~

nếu shared-utils chỉ là **included build**, không phải subproject trong cùng build. Cách này thường gây **UnknownProjectException**.

### 9.3. Ví dụ substitution tối thiểu (một tình huống riêng)

Cấu trúc ý tưởng:

~~~text
consumer/
├── settings.gradle
└── build.gradle
shared-utils/
├── settings.gradle
└── build.gradle
~~~

**shared-utils/settings.gradle**:

~~~groovy
rootProject.name = 'shared-utils'
~~~

**shared-utils/build.gradle**:

~~~groovy
plugins {
    id 'java-library'
}

group = 'org.example'
version = '1.0'
~~~

**consumer/settings.gradle**:

~~~groovy
rootProject.name = 'consumer'
includeBuild '../shared-utils'
~~~

**consumer/build.gradle**:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.example:shared-utils:1.0'
}
~~~

Đây là **fragment dependency substitution**, chưa có source files nên không phải một app runnable độc lập. Nó cho thấy **module coordinates** được dùng cho code dependencies. Để sử dụng thực tế, producer phải có class code và consumer có Java source cần dependency, cả hai builds phải có plugin/compatibility phù hợp.

### 9.4. Explicit dependency substitution khi coordinates khác

Gradle thường suy ra substitution từ **project.group:project.name**. Nếu published coordinates không khớp, có thể khai báo trong **consumer settings.gradle**:

~~~groovy
includeBuild('../shared-utils') {
    dependencySubstitution {
        substitute module('org.example:shared-api') using project(':')
    }
}
~~~

Đây là một fragment alternative, không dùng đồng thời với includeBuild cùng path lần nữa trong ví dụ trước. **project(':')** ở đây thuộc included build được cấu hình trong substitution block, không phải root consumer.

### 9.5. TaskReference không phải artifact dependency

Không có cú pháp hợp lệ như:

~~~groovy
dependencies {
    implementation gradle.includedBuild('shared-utils').task(':jar')
}
~~~

để thay một Java library dependency đầy đủ. TaskReference không có group/name/version, API/runtime variants hoặc transitive dependency metadata. Muốn library code, dùng module coordinates hoặc trong cùng build project dependency; muốn chạy một task, dùng TaskReference trong dependsOn.

### 9.6. Một build logic plugin cũng có ranh giới riêng

Ví dụ để dùng convention plugin được định nghĩa trong included build, khai báo trong **settings.gradle**:

~~~groovy
pluginManagement {
    includeBuild('build-logic')
}
~~~

Rồi project áp plugin bằng **plugins { id 'org.example.conventions' }** nếu included plugin build thực sự công bố plugin id đó. Đây là **plugin resolution**, không phải việc root gọi một task tùy ý của build-logic.

Không tự thêm task dependency tới build-logic:jar chỉ để plugins DSL tìm được plugin; Gradle có cơ chế plugin resolution riêng.

---

## 10. Cách kiểm tra task graph đúng

### 10.1. Kiểm tra included builds đã được nhận

Từ composite root:

~~~bash
./gradlew projects
~~~

Tài liệu/console Gradle cho thông tin về builds/projects đã được include theo phiên bản. Nếu không chắc tên task, gọi trực tiếp help hoặc tasks của included build theo CLI build-tree path.

~~~bash
./gradlew :tools:tasks --all
./gradlew :product:app:tasks --all
~~~

Với lab, cần thấy **writeStamp**, **validateStamp** trong tools và **run**, **classes**, **compileJava** ở product app.

### 10.2. Kiểm tra task existence trước khi đoán thứ tự

~~~bash
./gradlew :tools:help
./gradlew :product:app:help
~~~

Hai lệnh chứng minh build-tree paths resolution thành công; chúng không chứng minh :app:run chạy hay stamp được tạo.

### 10.3. Xem graph bằng --dry-run

~~~bash
./gradlew runProduct --dry-run
./gradlew verifyIncludedBuilds --dry-run
./gradlew fullDemo --dry-run
~~~

**--dry-run không thực thi actions**: nó chỉ hiển thị tasks sẽ được schedule. Không có stamp.txt mới, không có stdout Java Main thực tế, không có bytecode mới.

### 10.4. Chạy thực tế với --info

~~~bash
./gradlew runProduct --info
./gradlew verifyIncludedBuilds --info
~~~

**--info** giúp xem thông tin task scheduling, up-to-date checks, Java toolchain selection. Khi chia sẻ log cho bên ngoài, phải lọc thông tin nhạy cảm nếu build thực có repository credentials/paths nội bộ.

### 10.5. Kiểm tra bản chất độc lập của included builds

Lệnh:

~~~bash
./gradlew :tools:validateStamp
~~~

không cần chạy product app. Lệnh:

~~~bash
./gradlew :product:app:run
~~~

không cần chạy tools writeStamp. Đây là đặc điểm của lab: hai included builds được điều phối bởi root khi cần, nhưng tự thân không bị ghép artifact data graph không cần thiết.

### 10.6. Dùng --exclude-task có đầy đủ path

Tài liệu Gradle nêu khi exclude included build task từ CLI, dùng **fully qualified task path**. Ví dụ:

~~~bash
./gradlew fullDemo --exclude-task :product:app:run
~~~

**Đây chỉ là thử nghiệm điều tra**, không phải phương án xác minh fullDemo đã chạy đúng; khi exclude task quan trọng, kết quả có thể không còn đáp ứng mục đích run application. Không đưa --exclude-task vào CI để che một task lỗi.

---

## 11. Cấu hình độc lập: thuộc tính nào không được chia sẻ?

Gradle docs nhấn mạnh included builds **được cấu hình độc lập**. Một root build không mặc nhiên đẩy repositories, pluginManagement, dependency versions hoặc custom build properties trong root gradle.properties sang included builds.

### 11.1. Repository và plugin management

Nếu tools/product cần external dependencies, mỗi build cần repository/configuration phù hợp. Ví dụ chỉ root đặt **repositories { mavenCentral() }** không làm included build tự có Maven Central.

Tương tự, plugin IDs/versions catalog của root không tự trở thành version catalog của included build khác. Để chia sẻ policy, dùng convention plugins hoặc cấu hình được quản trị rõ.

### 11.2. gradle.properties

Custom property trong **root gradle.properties** không tự xuất hiện ở included build. Property truyền qua **-P** trên command line có thể được truyền xuống composite theo Gradle semantics; Gradle runtime properties đặc biệt có cách áp dụng chung theo invocation.

Đừng làm included build phụ thuộc ngầm vào biến mà chỉ một developer có trong root gradle.properties. Tài liệu hóa mỗi build hoặc dùng môi trường/cơ chế plugin chung được chấp thuận.

### 11.3. TaskReference không phá ranh giới configuration

Một đoạn:

~~~groovy
gradle.includedBuild('product').task(':app:run')
~~~

không trao quyền cho root sửa:

- application.mainClass của product.
- compileJava.options.release trong product.
- product.repositories.
- Test task maxHeapSize của included build.
- Output directory của task app:run.

Muốn thay những thứ đó, sửa build script/plugin của **product** hoặc thiết kế một extension/convention/plugin được áp bên đó. Giữ ranh giới cấu hình giúp composite builds hoạt động độc lập và có cơ hội tận dụng caching/parallelism.

### 11.4. Composite root không luôn cần source code

Một root chỉ điều phối tasks có thể chỉ áp **base** plugin, như lab. Nó không cần compileJava, implementation configuration hay application.mainClass. Tránh áp Java plugin cho root chỉ để tạo task điều phối included builds.

### 11.5. Ranh giới bảo mật

Nếu included build lấy plugins từ plugin repositories hoặc chạy arbitrary Gradle tasks, chúng có thể thực thi build logic với quyền môi trường đang dùng. **includeBuild không phải sandbox bảo mật**. Kiểm tra trust của repository included build và không truyền credentials không cần thiết.

TaskReference chỉ là cơ chế scheduling, không tự kiểm chứng nội dung source build.

---

## 12. Khi nhiều included builds có task cùng tên

### 12.1. Cùng tên task nhưng khác build

Giả sử tools và product root đều có task **:help**. Dùng:

~~~groovy
tasks.register('allHelp') {
    dependsOn(
        gradle.includedBuild('tools').task(':help'),
        gradle.includedBuild('product').task(':help')
    )
}
~~~

Gradle phân biệt bằng identity của từng IncludedBuild. Task names giống nhau không gây collision nếu build paths duy nhất.

### 12.2. Pattern cho một task phổ biến

~~~groovy
tasks.register('helpIncluded') {
    dependsOn gradle.includedBuilds*.task(':help')
}
~~~

Chỉ phù hợp khi mọi included builds có task path **:help**. Với task custom như **:validateStamp**, đừng nhân lên mọi build khi các build không cung cấp task ấy.

### 12.3. Có thể dùng map/filter chọn build theo tên

Ví dụ trong root Groovy DSL:

~~~groovy
def selected = gradle.includedBuilds.findAll {
    it.name in ['tools', 'product']
}

tasks.register('selectedHelp') {
    dependsOn selected.collect { it.task(':help') }
}
~~~

Đây là fragment cho lab, dùng API IncludedBuild.name; mọi build được chọn đều có help. Cách này có ích khi monorepo có nhiều included builds nhưng root chỉ muốn điều phối một nhóm có chính sách được khai báo.

**Không dùng build directory glob** để tìm names mà chưa được include; đó không phải Gradle included build discovery.

---

## 13. Điều phối publishing, verification và release tasks

### 13.1. Tạo một root verification entrypoint

Root có thể phụ thuộc Test/check tasks của included builds:

~~~groovy
tasks.register('checkComposite') {
    group = 'verification'

    dependsOn(
        gradle.includedBuild('tools').task(':validateStamp'),
        gradle.includedBuild('product').task(':app:check')
    )
}
~~~

Trong lab, **:app:check** là task lifecycle từ Java plugin của application project. **Nó có thể không chạy bài test nào** vì lab không có src/test/java. Vì vậy checkComposite thành công không có nghĩa đã có unit test coverage; nó chỉ xác nhận những tasks hiện hữu hoàn thành theo cấu hình.

### 13.2. Không giả định mọi included build có :check

Một included build có thể chỉ áp một plugin tùy chỉnh, không có task :check mà bạn mong đợi. Nếu viết **gradle.includedBuilds*.task(':check')** nhưng một build không có :check, build sẽ lỗi. Hãy liệt kê explicit paths cho mỗi included build theo hợp đồng kiểm tra đã biết.

### 13.3. CI có thể gọi root entrypoint

Ví dụ:

~~~bash
./gradlew verifyIncludedBuilds
./gradlew runProduct
~~~

CI không cần tự đi vào từng included directory nếu root task đã mô tả dependencies rõ. Nhưng root task phải được review để chắc rằng nó kéo đúng tests/builds/artifacts; một task orchestration bị thiếu dependency có thể báo xanh dù bỏ qua một build.

### 13.4. Publishing từ nhiều builds

Gradle docs có mẫu root task phụ thuộc cùng publish task path trong mọi included builds:

~~~groovy
tasks.register('publishDeps') {
    dependsOn gradle.includedBuilds*.task(
        ':publishMavenPublicationToMavenRepository'
    )
}
~~~

**Đây là ví dụ minh họa từ tài liệu**, không runnable trong lab vì tools và product chưa áp maven-publish, chưa định nghĩa publications/repositories. Nếu dùng thật, mỗi included build phải có task path đúng, credentials riêng và policy release thích hợp.

**Publish nhiều builds không là transaction nguyên tử**. Nếu một included build publish thành công rồi build khác thất bại, bạn có thể bị trạng thái release dở dang. Cần versioning, promotion/repository staging, checksums, rollback/cleanup strategy và CI controls.

### 13.5. Task reference không tự truyền output file

Dù root:

~~~groovy
dependsOn gradle.includedBuild('tools').task(':writeStamp')
~~~

nó chỉ bảo đảm task được thực thi trước root task phụ thuộc. Nếu root muốn đọc file stamp, vẫn phải có một **input contract/path hoặc artifact mechanism** được khai báo đúng. Không giả định TaskReference có thuộc tính **outputFile** hoặc **archiveFile** để lấy qua IncludedBuild API.

Một giải pháp output sharing bền vững là để producer công bố library/artifact versioned, consumer dùng module dependency/substitution, hoặc đặt producer/consumer task outputs trong cùng build và dùng Provider API. Đừng dựa vào raw path phía bên kia như một API ổn định.

---

## 14. Performance, caching và cấu hình

### 14.1. Included builds có tính độc lập

Mỗi included build giữ settings/repositories/build logic riêng và Gradle có thể cấu hình/thực thi task graph của nhiều builds trong một invocation. Điều này cho phép tổ chức monorepo theo domain/ownership, nhưng cũng có overhead khi quá nhiều builds được include mà không cần thiết.

### 14.2. TaskReference không yêu cầu eagerly realize Task khác

**IncludedBuild.task(path)** cung cấp TaskReference để Gradle kết nối task dependency. Nó không tương đương việc root gọi **otherProject.tasks.getByName(...)** và truy cập Task object sớm. Đây là cách thích hợp khi root chỉ muốn điều phối.

### 14.3. Configuration cache

Khi bật configuration cache, tránh các pattern không được hỗ trợ như đọc Gradle/Project mutable model tùy tiện trong **doLast** hoặc triển khai cross-project configuration. Tạo TaskReferences trong configuration phase như lab, rồi đưa chúng vào **dependsOn**, là hướng thiết kế rõ hơn.

Ví dụ không nên làm:

~~~groovy
tasks.register('runProduct') {
    doLast {
        // Không phải cách đúng để chạy task ở included build.
        gradle.includedBuild('product').task(':app:run')
    }
}
~~~

Dòng trong doLast chỉ yêu cầu một reference, **không tự lập lịch hay thực thi task**; tại thời điểm task action chạy, task graph đã được xác định. Cách đúng là **dependsOn reference** tại configuration.

### 14.4. Incremental và UP-TO-DATE

Trong tools task, **outputs.file(stampFile)** giúp Gradle có dữ liệu output để làm up-to-date checking. Chạy writeStamp nhiều lần không nhất thiết in lại “stamp created”. Vì vậy khi kiểm chứng lab, xét trạng thái task và nội dung file, không chỉ stdout của task doLast.

### 14.5. Parallel execution và thứ tự

Nếu root task phụ thuộc hai included builds độc lập, Gradle có thể thực thi các nhánh trong thứ tự khác nhau hoặc song song theo khả năng. Không dùng thứ tự log làm API và không dựa vào “Gradle tình cờ chạy tools trước product” để đảm bảo sản phẩm hợp lệ.

### 14.6. Một included build xuất hiện trong nhiều composite invocations

Tài liệu Gradle cảnh báo nhiều composite invocations chạy song song mà cùng include một build có thể gây vấn đề về project locking; không giả định Gradle chia sẻ lock toàn cục cho shared included build giữa các invocations. CI nên điều phối workspace và state để tránh cùng ghi vào build directory của included build từ nhiều jobs/processes độc lập.

### 14.7. Không tự chạy Gradle bên trong Gradle nếu có API

Anti-pattern:

~~~groovy
tasks.register('runProduct') {
    doLast {
        exec {
            commandLine './gradlew', ':product:app:run'
        }
    }
}
~~~

Cách này làm nested Gradle invocation, thêm overhead, khó quản lý cache/parallel scheduling/error propagation, không thể hiện task dependency thực sự. Với composite task đã có API chính thức, dùng **dependsOn gradle.includedBuild(...).task(...)**.

Đoạn anti-pattern còn phụ thuộc OS và có thể không chạy trên Windows. Không dùng nó làm script của lab.

---

## 15. Kotlin DSL đầy đủ cho root và settings

Nếu chuyển lab sang Kotlin DSL, cấu trúc builds vẫn tương tự nhưng mỗi file settings.gradle/build.gradle được thay bằng settings.gradle.kts/build.gradle.kts. **Không để đồng thời hai settings files với nội dung mâu thuẫn**.

### 15.1. Root settings.gradle.kts

~~~kotlin
rootProject.name = "composite-task-lab"

includeBuild("tools")
includeBuild("product")
~~~

### 15.2. Root build.gradle.kts

~~~kotlin
plugins {
    base
}

val stampValidation =
    gradle.includedBuild("tools").task(":validateStamp")

val appClasses =
    gradle.includedBuild("product").task(":app:classes")

val appRun =
    gradle.includedBuild("product").task(":app:run")

tasks.register("runProduct") {
    group = "verification"
    description = "Run the Java app in product included build"

    dependsOn(appRun)

    doLast {
        println("Root: product run complete")
    }
}

val verifyIncludedBuilds = tasks.register(
    "verifyIncludedBuilds"
) {
    group = "verification"
    dependsOn(stampValidation, appClasses)

    doLast {
        println("Root: verification complete")
    }
}

val runProduct = tasks.named("runProduct")

tasks.register("fullDemo") {
    dependsOn(verifyIncludedBuilds, runProduct)

    doLast {
        println("Root: full demo complete")
    }
}

tasks.register("helpIncluded") {
    dependsOn(
        gradle.includedBuilds.map { it.task(":help") }
    )
}
~~~

Các **TaskReference** trong Kotlin DSL được truyền nguyên vẹn vào dependsOn, không cần ép kiểu TaskProvider.

### 15.3. tools/build.gradle.kts

~~~kotlin
plugins {
    base
}

val stampFile = layout.buildDirectory.file(
    "generated/stamp.txt"
)

val writeStamp = tasks.register("writeStamp") {
    group = "verification"
    outputs.file(stampFile)

    doLast {
        val file = stampFile.get().asFile
        file.parentFile.mkdirs()
        file.writeText("STAMP_OK", Charsets.UTF_8)
        println("Tools: stamp created")
    }
}

tasks.register("validateStamp") {
    group = "verification"
    dependsOn(writeStamp)
    inputs.file(stampFile)

    doLast {
        val actual = stampFile.get().asFile.readText(
            Charsets.UTF_8
        )
        if (actual != "STAMP_OK") {
            throw GradleException("Unexpected stamp content")
        }
        println("Tools: stamp verified")
    }
}
~~~

### 15.4. product/settings.gradle.kts

~~~kotlin
rootProject.name = "product"

include("app")
~~~

### 15.5. product/app/build.gradle.kts

~~~kotlin
plugins {
    application
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
    options.encoding = "UTF-8"
}

application {
    mainClass = "lab.app.Main"
}
~~~

product/build.gradle.kts có thể chỉ là:

~~~kotlin
plugins {
    base
}
~~~

Java source **product/app/src/main/java/lab/app/Main.java** không đổi; chạy **./gradlew runProduct** và **./gradlew fullDemo** như Groovy DSL.

### 15.6. Đổi tên included build trong Kotlin DSL

~~~kotlin
includeBuild("tools") {
    name = "aux-tools"
}
~~~

Khi đó root build.gradle.kts dùng **gradle.includedBuild("aux-tools")** chứ không dùng "tools", và CLI dùng **:aux-tools:writeStamp**.

---

## 16. Troubleshooting theo thông báo và triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| **Included build not found** | Sai name hoặc thiếu includeBuild | Kiểm tra settings và tên included build |
| **UnknownDomainObjectException** tại includedBuild(name) | Không có IncludedBuild với tên đó | Dùng đúng build path/name hoặc cấu hình includeBuild |
| **Task not found** ở product | task(':product:app:run') lặp build prefix | Đổi thành task(':app:run') |
| **Task not found :app:run** | product chưa include app hoặc chưa áp application plugin | Xem product/settings.gradle, app/build.gradle |
| **project(':product:app') không tồn tại** | Nhầm composite với multi-project | Dùng IncludedBuild task reference hoặc module coords/substitution |
| **Cannot resolve implementation project(':tools')** | tools là included build, không phải subproject | Dùng external coordinates nếu cần code |
| Root task chạy nhưng included task không chạy | Dùng shouldRunAfter thay dependsOn hoặc chỉ gọi reference trong doLast | Đặt dependsOn trong task configuration |
| TaskReference không có configure() | Nó không phải TaskProvider | Cấu hình task trong included build của nó |
| TaskReference không có outputs.files | Không expose Task object/outputs | Dùng artifact contract hoặc project dependency |
| FullDemo outputs không cùng thứ tự | Hai dependencies độc lập | Không dựa vào log order; model data dependencies đúng |
| Stamp không in “created” lần hai | Task UP-TO-DATE | Kiểm tra file hoặc clean output đúng mục đích |
| Không thấy Main stdout khi chạy :app:classes | classes chỉ compile | Dùng :app:run |
| App JDK/toolchain not found | Thiếu JDK17 hoặc resolver | Cài toolchain hoặc cấu hình provisioning |
| CLI :product:app:run thất bại | Build path hoặc project/task path sai | Dùng :product:app:tasks --all |
| Build name collision | Included path trùng root project hoặc included build khác | Đổi includeBuild name |
| --include-build trên CLI nhưng script không thấy tên | Included build không được cấu hình như dự kiến | Dùng settings includeBuild ổn định và đúng name |
| Plugin trong build-logic không resolve | Chưa include plugin build đúng pluginManagement phase | Đưa pluginManagement.includeBuild vào settings |
| CI root có Maven Central nhưng included không | Builds có config độc lập | Cấu hình repositories trong từng build |
| Project property root không thấy ở included | Custom gradle.properties không tự chia sẻ | CLI -P/environment/convention plugin theo policy |
| gradle.includedBuilds*.task(':publish') fail | Một included build thiếu task cùng tên | Chọn explicit known task paths |
| Build chạy hai included builds tuần tự một cách tình cờ | Không có true dependency edge giữa chúng | Không dựa vào thứ tự quan sát; thiết kế artifact dependency |
| File output không xuất hiện ở root | TaskReference chỉ scheduling, không expose outputs | Xuất bản artifact hoặc đặt contract rõ |
| Nested Gradle invocation gây cache/lock issues | Exec gọi Gradle trong Gradle | Dùng TaskReference và một invocation |
| Các composite jobs cùng ghi output directory | Shared included build giữa parallel invocations | CI workspace isolation/locks có kiểm soát |
| Code của included build không có trong compile classpath | Task dependency không phải module dependency | Dùng group:name:version và substitution |
| Thay build name làm hỏng CLI | Hardcode old path | Cập nhật includedBuild(name) và CI references |
| gradle.tasks.named(':product:app:run') không tìm thấy | TaskContainer local không quản lý included task | gradle.includedBuild('product').task(':app:run') |

### 16.1. Chuỗi debug hiệu quả

1. Kiểm tra composite root **settings.gradle** có includeBuild đúng thư mục.
2. Xác nhận included build tự có **settings.gradle** và project path mong muốn.
3. Dùng **./gradlew :product:app:tasks --all** để kiểm tra task có tồn tại.
4. Dùng CLI fully qualified path chạy task trực tiếp.
5. Chuyển task path thành reference dạng **includedBuild(name).task(':internal:path')**.
6. Kiểm tra root **dependsOn** thay vì mustRunAfter/shouldRunAfter.
7. Dùng **--dry-run** xem graph, rồi chạy thật để kiểm chứng stdout/artifact.
8. Nếu lỗi là classpath/dependency, dùng dependency substitution chứ không thêm một task reference.
9. Nếu lỗi là task output/data dependency, thiết kế producer/consumer contract thay vì chỉ thêm hai independent prerequisites.
10. Kiểm tra build name collisions, toolchain và configuration isolation nếu vẫn lỗi.

---

## 17. Bài tập thực hành có đáp án

### Bài 1 — Included build và subproject

Root settings:

~~~groovy
includeBuild 'product'
~~~

Có thể viết **implementation project(':product')** không?

**Đáp án:** không, trừ khi root đồng thời có một subproject thật sự tên :product. includeBuild không đưa product vào root Project hierarchy. Với code dependency dùng external coordinates/substitution; với task dùng IncludedBuild.task.

### Bài 2 — Đường dẫn đúng

CLI từ root là **:product:app:run**. Trong API phải viết gì?

**Đáp án:** **gradle.includedBuild('product').task(':app:run')**, không được lặp prefix product.

### Bài 3 — Included root task

CLI là **:tools:writeStamp**. API?

**Đáp án:** **gradle.includedBuild('tools').task(':writeStamp')**.

### Bài 4 — TaskReference có thể configure JavaExec không?

**Đáp án:** không. Nó không phải TaskProvider hoặc Task object; chỉnh **app:run** trong product/app/build.gradle hay convention plugin được áp ở đó.

### Bài 5 — Root dependsOn hai included tasks

Có chắc A chạy trước B?

**Đáp án:** không. Chắc chắn root dependent task chạy sau cả hai khi cả hai thành công. Dependencies độc lập không có order guarantee lẫn nhau.

### Bài 6 — mustRunAfter kéo task vào graph?

**Đáp án:** không. Nó áp thứ tự khi cả hai tasks cùng có mặt trong graph. dependsOn mới tạo task dependency.

### Bài 7 — shouldRunAfter là hard guarantee?

**Đáp án:** không. Nó mềm hơn mustRunAfter, có thể bị bỏ qua khi cần.

### Bài 8 — Một build không có :publish

Có thể gọi **gradle.includedBuilds*.task(':publish')**?

**Đáp án:** chỉ khi mọi included builds tương ứng đều có :publish. Không được giả định task custom có mặt trong tất cả builds.

### Bài 9 — TaskReference có file output cho consumer không?

**Đáp án:** không. IncludedBuild.task trả reference để scheduling. Nếu cần artifacts qua build boundary, dùng dependency/artifact contract đúng hoặc tái cấu trúc.

### Bài 10 — CLI --dry-run có tạo file stamp không?

**Đáp án:** không. Dry-run chỉ hiển thị task scheduling. Phải chạy thật mới có output.

### Bài 11 — Java class Main in gì?

Với source lab không đổi, chạy **./gradlew :product:app:run**.

**Đáp án:** stdout do Java code in **App: composite build OK**.

### Bài 12 — Vì sao :product:app:classes không in Java main?

**Đáp án:** classes/compileJava chỉ compile nguồn, không thực thi main method. Dùng :app:run.

### Bài 13 — includeBuild khác include?

**Đáp án:** includeBuild thêm một Gradle build riêng; include thêm project vào hiện tại. Chúng có project/task namespace và config khác nhau.

### Bài 14 — Build name rename

Root settings đặt **includeBuild('tools') { name = 'aux-tools' }**. API?

**Đáp án:** **gradle.includedBuild('aux-tools').task(':writeStamp')**. CLI path **:aux-tools:writeStamp**.

### Bài 15 — Shared repository config?

Root khai báo Maven Central thì product tự có Maven Central không?

**Đáp án:** không. Included builds được cấu hình độc lập; product cần repositories riêng nếu có external modules.

### Bài 16 — Plugin build được include ra sao?

**Đáp án:** nếu định dùng plugin từ included build cho plugins DSL, Gradle docs khuyến nghị include plugin build trong **pluginManagement** ở settings; không cần phụ thuộc thủ công vào plugin jar task.

### Bài 17 — Code dependency vs task dependency

Root muốn dùng class từ included build trong compileJava.

**Đáp án:** dependency theo **group:name:version** với composite substitution; không phải **dependsOn includedBuild.task(':jar')** đơn độc.

### Bài 18 — Build khác tự bị thay đổi configuration?

Root gọi TaskReference tới product:run có thể sửa JDK product sang 21 không?

**Đáp án:** không. TaskReference không expose configuration. Product tự quản toolchain và tasks.

### Bài 19 — Included build ngoài root

**includeBuild('../shared-tools')** được tính relative với đâu?

**Đáp án:** thư mục chứa root settings.gradle(.kts).

### Bài 20 — Nhiều composite CI jobs cùng dùng một included build directory

Có cần lưu ý gì?

**Đáp án:** có. Gradle docs cảnh báo shared included builds giữa parallel Gradle invocations có thể có locking conflicts. Dùng workspace isolation hoặc CI synchronization phù hợp.

### Bài 21 — Composite task thành công mà chưa chạy tests

**Đáp án:** xem root task có dependsOn đúng test/check tasks thực sự không. Nếu chỉ gọi :app:classes như lab thì mới chứng minh compile, không chứng minh unit/integration tests tồn tại hay pass.

### Bài 22 — Khi nào không dùng cross-build TaskReference?

**Đáp án:** khi mục tiêu là tiêu thụ artifact/module versioned, cần transitive metadata/variants, hoặc cần output property để modeling inputs. Hãy dùng dependency model/production contract, không lạm dụng task scheduling.

---

## 18. Checklist trước khi merge vào CI

- [ ] Included build được khai báo đúng bằng **includeBuild** trong settings.
- [ ] Included build có settings file và project/task hierarchy đúng.
- [ ] Build name/path không đụng root project paths hoặc included builds khác.
- [ ] Task reference dùng **gradle.includedBuild(name).task(':internal:path')**.
- [ ] Không lặp build prefix trong path truyền vào task(...).
- [ ] CLI từ root dùng fully qualified build-tree paths.
- [ ] Không nhầm **TaskReference** với Task/TaskProvider.
- [ ] Root task dùng **dependsOn** cho công việc bắt buộc.
- [ ] **mustRunAfter/shouldRunAfter** không bị dùng thay dependsOn.
- [ ] Hai prerequisite tasks độc lập không bị giả định có thứ tự.
- [ ] Nếu cần output task xuyên build, có artifact/data contract thay vì raw path.
- [ ] Nếu cần code của included build, dùng coordinates/substitution.
- [ ] Không dùng **project(':included-build:module')** xuyên build boundary.
- [ ] Không truy cập **otherProject.tasks** để cấu hình included builds.
- [ ] Không tạo nested Gradle invocation trong Exec khi TaskReference đủ dùng.
- [ ] Không giả định root repositories/gradle.properties được chia sẻ.
- [ ] Plugin builds được include đúng pluginManagement khi cần.
- [ ] Mọi task path trong gradle.includedBuilds map đều tồn tại ở builds được chọn.
- [ ] Task graph đã được xem bằng dry-run, sau đó chạy thật.
- [ ] Java toolchain và Gradle Wrapper tương thích với CI runner.
- [ ] Tests có thực sự chạy nếu root task tên verify/check?
- [ ] Outputs được khai báo inputs/outputs cho incremental/up-to-date behavior.
- [ ] CI không sử dụng cùng build directory của included build trong nhiều jobs không phối hợp.
- [ ] Changes build name/settings được phản ánh trong scripts/CI.
- [ ] Không dùng task orchestration như bằng chứng dependency substitution đã hoạt động.
- [ ] Không coi BUILD SUCCESSFUL khi không có tests là chứng chỉ chất lượng.

## Tài liệu chính thức của Gradle

- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): includeBuild, task CLI, gradle.includedBuild(...).task(...), gradle.includedBuilds, dependency substitution, build identity và limitations.
- [Gradle — IncludedBuild API](https://docs.gradle.org/current/javadoc/org/gradle/api/initialization/IncludedBuild.html): name, projectDir và task(path) trả TaskReference.
- [Gradle — Gradle API](https://docs.gradle.org/current/javadoc/org/gradle/api/invocation/Gradle.html): includedBuild(String), getIncludedBuilds(), build identity.
- [Gradle — Task API](https://docs.gradle.org/current/javadoc/org/gradle/api/Task.html): dependsOn, mustRunAfter, shouldRunAfter, TaskReference trong dependency/ordering.
- [Gradle — Structuring Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds_intermediate.html): so sánh multi-project và included build/buil​d-logic.
- [Gradle — Dependency Substitution](https://docs.gradle.org/current/userguide/resolution_rules.html): module coordinates, project substitution và variant-aware resolution.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): JavaExec task run và mainClass.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): Java version selection theo toolchain.
- [Gradle — Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): JDK và Gradle Wrapper versions.

**Kết luận:** Để một build điều phối task của included build khác, dùng **gradle.includedBuild('tên-build').task(':đường-dẫn-bên-trong')** và đưa **TaskReference** vào **dependsOn**. Phân biệt rõ **build-tree path trên CLI** với **task path nội bộ**, và đừng xem TaskReference như TaskProvider để đọc outputs hay chỉnh cấu hình của build khác. Khi cần **code/artifact dependencies**, dùng dependency substitution hoặc hợp đồng artifact thích hợp; khi cần **chạy công việc**, dùng task reference. Một composite build tốt giữ các builds độc lập về cấu hình và tạo quan hệ đúng trong graph, không chỉ dựa vào thứ tự lệnh hoặc vị trí thư mục.