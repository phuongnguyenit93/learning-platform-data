# Tạo source set bổ sung và nối vào task kiểm tra, đóng gói trong dự án Java Gradle

## 1. Bối cảnh, mục tiêu và kết quả cần đạt

Trong dự án Java dùng Gradle, hai thư mục **src/main/java** và **src/test/java** thường đủ cho ứng dụng đơn giản. Nhưng một dự án có thể cần thêm **integration tests**, **contract tests**, **functional tests**, một bộ **CLI hỗ trợ vận hành** hoặc một tập mã nguồn dùng để đóng gói riêng. Những phần này không nhất thiết nên trộn với source production hoặc unit tests.

**Source set bổ sung** cho phép Gradle quản lý một nhóm Java source và resources riêng, có **compile classpath**, **runtime classpath**, các configuration khai báo dependency, output directory và các task biên dịch/xử lý resources riêng. Tuy nhiên, **tạo source set mới chưa đủ để Gradle tự chạy integration tests hoặc đưa output đó vào artifact**. Người viết build phải nối source set vào **Test/JavaExec/Jar** và vào lifecycle task **check/assemble** theo mục đích.

Bài này thuộc nhóm **Dự án Java**, tập trung vào đúng yêu cầu: **Tạo source set bổ sung và nối vào task kiểm tra, đóng gói**.

Sau bài học, bạn có thể:

1. Hiểu **SourceSet**, **SourceSetContainer**, **SourceDirectorySet** và **SourceSetOutput**.
2. Phân biệt source set mặc định **main**, **test** với source set tự thêm như **integrationTest** và **tools**.
3. Biết những task/configurations Gradle tạo theo quy ước, và những task **không** được tạo tự động.
4. Cấu hình **compileClasspath/runtimeClasspath** để source bổ sung dùng được production code nhưng không đưa test code vào production classpath.
5. Khai báo JUnit Jupiter riêng cho **integrationTestImplementation/integrationTestRuntimeOnly**, đăng ký task **integrationTest** và nối nó vào **check**.
6. Tạo một **toolsJar** từ source set **tools**, nối nó vào **assemble** và kiểm tra artifact bên trong **build/libs**.
7. Hiểu vì sao **jar** thông thường chỉ chứa **main output**, còn output bổ sung phải được đóng gói có chủ đích.
8. Chạy ví dụ đầy đủ **Java 17 + Gradle Groovy DSL** với main, unit test, integration test, tools và resources.
9. Thực hiện lệnh **javac --release 17**/**java** để xác minh phần Java độc lập, đồng thời dùng Gradle Wrapper kiểm tra task graph/packaging.
10. Khắc phục lỗi **cannot find symbol**, **No tests found**, thiếu launcher, classpath không đủ, task chưa nối **check/assemble**, duplicate entries và lỗi publication.

## 2. Source set là gì?

Một **source set** là tập mã nguồn và resources phục vụ một phần của chương trình JVM. Java plugin tạo sẵn source sets:

- **main**: mã production và tài nguyên production.
- **test**: mã unit test và resources phục vụ test.

Source set biết các thông tin như:

- **java.srcDirs**: thư mục chứa Java source.
- **resources.srcDirs**: thư mục resource.
- **compileClasspath**: classpath cần khi biên dịch Java source của set đó.
- **runtimeClasspath**: classpath cần khi chạy mã của set đó.
- **output.classesDirs**: output class directories.
- **output.resourcesDir** và **output**: output Java classes cùng resources đã xử lý.
- **annotationProcessorPath**: processor path dành riêng cho source set nếu cần annotation processing.

Ở mức ý tưởng:

~~~text
SourceSet: integrationTest
    |
    +-- src/integrationTest/java
    +-- src/integrationTest/resources
    |
    +-- compileClasspath
    +-- runtimeClasspath
    |
    +-- Gradle tự tạo compileIntegrationTestJava
    +-- Gradle tự tạo processIntegrationTestResources
    +-- Gradle tự tạo integrationTestClasses
    |
    +-- build/classes/java/integrationTest
    +-- build/resources/integrationTest
    |
    +-- Cần tự đăng ký Test task integrationTest
    +-- Cần tự nối vào check nếu CI phải chạy suite này
~~~

**Source set không phải subproject, plugin, variant hay task**. Một project có thể có nhiều source sets; một build có thể có nhiều projects; một source set có thể phục vụ nhiều task.

## 3. Những gì Java plugin tạo tự động

Khi áp dụng:

~~~groovy
plugins {
    id 'java'
}
~~~

Gradle tạo source sets **main**, **test** và các task/configurations theo quy ước. Với source set tự tạo **integrationTest**, Java plugin cũng đăng ký nhiều task liên quan đến biên dịch và xử lý resources.

| Source set | Java source mặc định | Compile Java task | Resources task | Tổng hợp classes |
| --- | --- | --- | --- | --- |
| **main** | src/main/java | **compileJava** | **processResources** | **classes** |
| **test** | src/test/java | **compileTestJava** | **processTestResources** | **testClasses** |
| **integrationTest** | src/integrationTest/java | **compileIntegrationTestJava** | **processIntegrationTestResources** | **integrationTestClasses** |
| **tools** | src/tools/java | **compileToolsJava** | **processToolsResources** | **toolsClasses** |

Tên được tạo theo **source set name**, với **main** và **test** có các quy ước truyền thống. Tên bạn chọn quyết định các task mà Gradle sẽ tạo; source set **intTest** sinh tên dạng **compileIntTestJava**, khác **compileIntegrationTestJava**.

### 3.1. Configuration tự tạo khi thêm source set

Một source set **integrationTest** thông thường có các configurations như:

~~~text
integrationTestImplementation
integrationTestCompileOnly
integrationTestRuntimeOnly
integrationTestAnnotationProcessor
integrationTestCompileClasspath
integrationTestRuntimeClasspath
~~~

Tương tự với **tools**:

~~~text
toolsImplementation
toolsCompileOnly
toolsRuntimeOnly
toolsAnnotationProcessor
toolsCompileClasspath
toolsRuntimeClasspath
~~~

**...Implementation** và **...RuntimeOnly** là nơi khai báo dependencies. **...CompileClasspath** và **...RuntimeClasspath** là configurations có vai trò resolve để Gradle lấy dependency graph/artifacts.

**Không nhầm** tên configuration với tên task. Không thể chạy **./gradlew integrationTestImplementation** như một task để tải dependencies. Thay vào đó, chọn task compile/test hoặc báo cáo:

~~~bash
./gradlew dependencies --configuration integrationTestRuntimeClasspath
~~~

### 3.2. Điều Java plugin không tự tạo

Chỉ viết:

~~~groovy
sourceSets {
    integrationTest
}
~~~

**không đủ** để có một **Test task integrationTest** đúng classpath, không nối suite đó vào **check**, và không làm **jar** tự đóng gói classes của integrationTest.

Để chạy integration tests, phải đăng ký một task kiểu **Test** (hoặc sử dụng JVM Test Suite plugin) với:

- **testClassesDirs**: những compiled test classes cần thực thi;
- **classpath**: output và libraries để forked test JVM chạy;
- framework tương ứng, ví dụ **useJUnitPlatform()** cho JUnit 5.

Để nối vào pipeline, phải cấu hình **check.dependsOn(...)**. Để đóng gói source bổ sung, phải cấu hình task **Jar/Zip/War** hoặc plugin/variant phù hợp và nối vào **assemble** khi thật sự muốn artifact đó nằm trong bước đóng gói.

## 4. Phân biệt main, test, integrationTest và tools

Bốn source sets trong ví dụ sẽ có các trách nhiệm:

| Source set | Mục đích | Có nên vào JAR production? | Cách dùng |
| --- | --- | --- | --- |
| **main** | API và logic sản phẩm | Có, mặc định | **jar**, **run**, **compileJava** |
| **test** | Unit tests | Không | Task **test** |
| **integrationTest** | Kiểm tra sự phối hợp và resource fixture | Không | Task **integrationTest**, gắn **check** |
| **tools** | CLI/hỗ trợ vận hành được đóng gói riêng | Chỉ trong JAR riêng theo thiết kế | **runTools**, **toolsJar**, gắn **assemble** |

**Source set không quyết định có đóng gói hay không một cách thần kỳ.** Task đóng gói lấy file collection nào thì chứa output của collection đó. Java plugin cấu hình JAR mặc định lấy **sourceSets.main.output**. Muốn thêm output khác phải chỉ rõ **from(...)** hoặc tạo archive task khác.

### 4.1. Khi nào thêm source set thay vì subproject?

**Thêm source set** khi mã thuộc cùng module/ownership/version nhưng có vòng đời và classpath khác, ví dụ integration tests hoặc CLI nội bộ.

**Thêm subproject** khi phần mã có API, nhiệm vụ phát hành, dependency graph, ownership hoặc versioning độc lập; ví dụ thư viện API được nhiều ứng dụng dùng, công cụ build cần xuất bản riêng hoặc bộ integration tests rất lớn.

**Dùng JVM Test Suite plugin** khi mục tiêu chủ yếu là thêm các test suites và muốn Gradle mô hình hóa suites/targets/dependencies mà không phải nối thủ công mọi Test task.

**Dùng Java Test Fixtures plugin** khi cần chia sẻ test helpers cho các module khác qua variant/capability test fixtures. Đừng biến source set **integrationTest** thành một dependency public chỉ vì nó có class files.

## 5. Tạo source set mới bằng Groovy DSL

Ví dụ tối giản:

~~~groovy
plugins {
    id 'java'
}

sourceSets {
    integrationTest {
        java.srcDir 'src/integrationTest/java'
        resources.srcDir 'src/integrationTest/resources'

        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}
~~~

Gradle mặc định nhận đường dẫn **src/integrationTest/java** và **src/integrationTest/resources** theo convention; hai dòng **srcDir** ở đây có tính minh họa, hữu ích khi nhóm muốn cấu hình path tường minh.

Với **sourceSets.main.output**:

- **compileClasspath += ...** cho phép code integrationTest tham chiếu các class production.
- **runtimeClasspath += ...** cho phép integration test JVM nạp được class production khi chạy.
- **+=** bổ sung file collection vào classpath vốn đã có, **không ghi đè** dependencies mặc định của source set.

**Không nên** viết:

~~~groovy
sourceSets.integrationTest.compileClasspath = sourceSets.main.output
~~~

nếu mục tiêu chỉ là bổ sung production classes. Gán bằng **=** có thể làm mất classpath chứa dependencies của integrationTest và gây lỗi compiler không tìm thấy JUnit hay thư viện khác.

### 5.1. Thư mục source có thể đổi tên

Nếu project dùng cấu trúc khác, ví dụ **integration-tests/src/java**:

~~~groovy
sourceSets {
    integrationTest {
        java.setSrcDirs(['integration-tests/src/java'])
        resources.setSrcDirs(['integration-tests/src/resources'])
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}
~~~

Đây là **cấu hình thay thế** cho bài lab, không chạy đồng thời với cấu hình dùng **src/integrationTest/**. **setSrcDirs** thay toàn bộ danh sách source directories; **srcDir** bổ sung một đường dẫn. Nếu dùng cả hai mà không hiểu thứ tự có thể giữ lại hoặc xóa nhầm thư mục cần compile.

Không đưa **src/main/java** vào tập **integrationTest.java.srcDirs** chỉ để integration test nhìn thấy production code; làm vậy compile có thể lặp source và tạo classes trùng. Dùng **sourceSets.main.output** trên classpath thay vì biên dịch lại source main.

## 6. Kết nối dependencies giữa source sets

### 6.1. Dependencies của mỗi source set là độc lập

Mặc định source set bổ sung có configurations của chính nó. Muốn dùng JUnit Jupiter trong integration tests, cần khai báo:

~~~groovy
dependencies {
    integrationTestImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    integrationTestRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}
~~~

Không đủ khi chỉ có:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}
~~~

vì **testImplementation** thuộc source set **test**; nó không tự thành dependency của **integrationTest** nếu bạn chưa cấu hình kế thừa.

### 6.2. Kế thừa dependency scopes khi hợp lý

Khi integration tests cần những dependencies mà production code sử dụng, có thể cấu hình:

~~~groovy
configurations {
    integrationTestImplementation.extendsFrom implementation
    integrationTestRuntimeOnly.extendsFrom runtimeOnly
}
~~~

Đây là cách đã được tài liệu Gradle hướng dẫn. Nó có nghĩa dependencies trong **implementation** cũng được khai báo gián tiếp cho integration test compile/runtime scope, và dependencies trong **runtimeOnly** được đưa vào runtime scope tương ứng.

Nếu integration tests thật sự cần toàn bộ unit test dependencies, có thể thay/điều chỉnh thành:

~~~groovy
configurations {
    integrationTestImplementation.extendsFrom testImplementation
}
~~~

**Không bắt buộc** phải kế thừa testImplementation. Việc thừa hưởng mọi test utility có thể kéo nhiều libraries không cần thiết vào integration suite, tăng thời gian resolve và tạo khó khăn về version.

**extendsFrom** kế thừa dependency declarations và ràng buộc liên quan theo API, **không trộn hai source sets thành một** và không làm **integrationTest** tự chạy. Khi source set cần class production, bạn vẫn phải nối main output trên compile/runtime classpath nếu dùng cách kiểm thử trực tiếp.

### 6.3. Hạn chế classpath leakage

Không dùng:

~~~groovy
sourceSets.integrationTest.runtimeClasspath += configurations.testRuntimeClasspath
~~~

nếu chỉ cần một vài thư viện test cụ thể. Lấy toàn bộ runtimeClasspath của unit tests có thể đưa unit-test classes/libraries không cần sang integrationTest và che việc thiếu dependency trực tiếp. Hãy mô hình hóa dependencies theo source set hoặc kế thừa phạm vi thật sự phù hợp.

Trong monorepo, đừng cho **toolsImplementation** kế thừa **testImplementation** chỉ vì một công cụ hỗ trợ cần dùng API của app. Đó là hai loại công việc khác nhau.

## 7. Nối source set integrationTest vào task Test

### 7.1. Đăng ký task test tùy chỉnh

Sau khi đã định nghĩa **sourceSets.integrationTest**:

~~~groovy
def integrationTestTask = tasks.register('integrationTest', Test) {
    description = 'Runs integration tests'
    group = 'verification'

    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath

    useJUnitPlatform()
    shouldRunAfter(tasks.named('test'))
}
~~~

Các dòng quan trọng:

- **tasks.register** đăng ký task lazily, trả một **TaskProvider**.
- **testClassesDirs** là những output directories chứa compiled test classes. Không đặt thành thư mục source Java.
- **classpath** có compiled integrationTest classes, resources, main output và libraries đã khai báo.
- **useJUnitPlatform()** bật JUnit Platform cho JUnit Jupiter tests.
- **shouldRunAfter(test)** ưu tiên integration tests sau unit tests khi cả hai được chọn trong task graph. Nó **không tự thêm test task vào graph**.

Với Gradle 9.x, phải đặc biệt cẩn thận cấu hình **testClassesDirs** và **classpath** cho custom Test tasks; không giả định mọi Test task đều tự dùng source set **test** như legacy versions.

### 7.2. Nối vào check lifecycle task

~~~groovy
tasks.named('check') {
    dependsOn(integrationTestTask)
}
~~~

Từ đó:

~~~text
check
  |
  +-- test                   # Java plugin nối sẵn
  |
  +-- integrationTest        # do bạn nối thêm
        |
        +-- compileIntegrationTestJava
        +-- processIntegrationTestResources
        +-- integrationTestClasses
~~~

**check** là lifecycle task kiểm tra chất lượng. Nếu CI chạy **./gradlew check**, integrationTest sẽ có mặt trong graph. Nếu chỉ chạy **./gradlew test**, integrationTest **không** tự chạy vì đó là một task riêng.

Task dependencies có thể được Gradle suy ra từ built-by file collections như source set outputs. Để làm quan hệ rõ ràng trong build phức tạp, có thể khai báo:

~~~groovy
tasks.named('integrationTest', Test) {
    dependsOn(tasks.named('integrationTestClasses'))
}
~~~

Đây là cấu hình **bổ sung, không thay thế** testClassesDirs/classpath. Trong lab đầy đủ sẽ có dependency này để dễ hiểu.

### 7.3. shouldRunAfter khác dependsOn/mustRunAfter

| Cấu hình | Ý nghĩa |
| --- | --- |
| **dependsOn(test)** | Chọn integrationTest thì test được đưa vào graph như dependency |
| **shouldRunAfter(test)** | Nếu cả hai cùng được chạy, ưu tiên test chạy trước; không tự thêm task test |
| **mustRunAfter(test)** | Khi cả hai được chọn, áp thứ tự mạnh hơn; không tự thêm task |
| **check.dependsOn(integrationTest)** | Chọn check thì integrationTest được đưa vào graph |
| **test.finalizedBy(integrationTest)** | Có thể lên lịch finalizer; thường không phù hợp làm quality gate thay check |

Đối với integration tests thường lâu hơn unit tests, **shouldRunAfter(test)** giúp có cơ hội phát hiện unit test failure sớm mà vẫn cho scheduler linh hoạt hơn **mustRunAfter**. Không nhầm **shouldRunAfter** với bảo đảm test task sẽ luôn được thực thi trong mọi lệnh.

### 7.4. Test task có thể SKIPPED hoặc NO-SOURCE

Một task **integrationTest** tồn tại trong danh sách tasks không đồng nghĩa có test case. Nếu **src/integrationTest/java** rỗng, Gradle có thể báo **NO-SOURCE** ở compile hoặc **NO-SOURCE/SKIPPED** với test task. Nếu classes có nhưng JUnit engine/launcher thiếu, test task có thể fail hoặc không phát hiện test như bạn mong đợi.

Phải kiểm tra cả **compiled classes**, **testClassesDirs**, **classpath**, **useJUnitPlatform**, **JUnit Engine** và **Launcher**. Không dùng một trạng thái BUILD SUCCESSFUL để kết luận mọi integration test đã chạy, nếu báo cáo test cho thấy 0 tests.

## 8. Nối source set bổ sung vào đóng gói

### 8.1. jar mặc định chỉ dùng main

Java plugin thường cấu hình:

~~~text
jar
   from sourceSets.main.output
   -> build/libs/<project>-<version>.jar
~~~

**test**, **integrationTest** và **tools** không được tự đóng gói vào JAR chính chỉ vì source sets đó tồn tại.

Điều này quan trọng cho bảo mật và maintainability:

- Không đưa test source, fixture credentials hoặc test resources vào production artifact.
- Không làm CLI nội bộ xuất hiện trong JAR chính nếu nó không thuộc API production.
- Không biến những dependency chỉ dùng để test thành runtime dependencies của người dùng thư viện.
- Không làm JAR chứa duplicate classes/resources ngoài ý muốn.

### 8.2. Tạo JAR riêng từ một source set

Nếu có source set **tools**:

~~~groovy
def toolsJarTask = tasks.register('toolsJar', Jar) {
    group = 'build'
    description = 'Đóng gói mã tools riêng'
    archiveClassifier.set('tools')
    from(sourceSets.tools.output)
}
~~~

**sourceSets.tools.output** bao gồm compiled classes và processed resources của tools. Task Jar nhận file collection gắn với source set output; Gradle có thể suy ra dependencies build inputs. Nếu muốn rõ ràng, thêm **dependsOn(tasks.named('toolsClasses'))**.

**archiveClassifier.set('tools')** khiến output có tên như **source-set-lab-1.0.0-tools.jar** khi project name/version tương ứng. Nó **không** tự gồm application main JAR hay external runtime dependencies; đây không phải fat/uber JAR.

### 8.3. Nối toolsJar vào assemble

~~~groovy
tasks.named('assemble') {
    dependsOn(toolsJarTask)
}
~~~

Theo Java plugin lifecycle:

~~~text
build
  |
  +-- check
  |     +-- test
  |     +-- integrationTest (do bạn nối)
  |
  +-- assemble
        +-- jar           (sourceSets.main.output)
        +-- toolsJar      (sourceSets.tools.output; do bạn nối)
~~~

**build** thường phụ thuộc **check** và **assemble**, nên một lệnh **./gradlew build** có thể thực hiện cả integration tests và tạo toolsJar nếu những nối task trên đã được thiết lập.

Đừng nhầm:

- **tasks.register('toolsJar', Jar)** tạo một task có thể chạy trực tiếp;
- **assemble.dependsOn(toolsJar)** làm đóng gói bổ sung nằm trong lifecycle assemble;
- **check.dependsOn(integrationTest)** làm kiểm tra bổ sung nằm trong lifecycle check;
- **publishing** là một hệ thống khác: tạo toolsJar không tự publish artifact đó.

### 8.4. Thêm vào JAR chính: có thể, nhưng phải có lý do

Nếu thật sự cần đưa tools output vào JAR production:

~~~groovy
tasks.named('jar', Jar) {
    from(sourceSets.tools.output)
}
~~~

Đây là **phương án thay thế** so với toolsJar riêng; **không áp dụng đồng thời vào lab** nếu muốn giữ hai JAR tách biệt. Merging có thể dẫn đến:

- Class/resource name collisions;
- Cần chính sách **duplicatesStrategy** khi có file trùng;
- Runtime dependency của tools không được đóng gói tự động chỉ bằng **from(tools.output)**;
- Artifact production chứa mã vận hành hoặc tài nguyên không nên công khai.

**Tuyệt đối tránh thêm sourceSets.integrationTest.output vào JAR chính** nếu nó chứa test code, test fixtures, dữ liệu giả hoặc credentials. Chỉ đóng gói tài nguyên/test utilities khi có mục đích và kiểm soát rõ.

### 8.5. Một JAR bổ sung không tự tạo variant/publishing

**toolsJar** là một archive task. Nó không tự trở thành outgoing variant của Java component và cũng không tự được xuất bản bằng **maven-publish**. Nếu người tiêu dùng bên ngoài phải chọn một artifact tools riêng, cần:

- Cấu hình **MavenPublication** và artifact nếu chỉ muốn thêm một classifier artifact;
- Hoặc tạo **feature variant/consumable configuration** có attributes, capabilities và dependencies khi cần variant-aware resolution;
- Kiểm tra Gradle Module Metadata/POM và hành vi của consumers;
- Không tự coi việc task có output trong **build/libs** là artifact đã được publish.

Ví dụ **chỉ minh họa publishing**, yêu cầu thêm plugin **maven-publish** và repositories/credentials phù hợp:

~~~groovy
publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            artifact(tasks.named('toolsJar'))
        }
    }
}
~~~

Không dùng snippet publishing này trong lab chính, vì lab chỉ kiểm tra local assemble. Nó có thể thêm classifier artifact vào publication, nhưng không tự diễn đạt một feature variant đầy đủ cho dependency resolution của consumer Gradle.

## 9. Ví dụ hoàn chỉnh Java 17: source sets integrationTest và tools

Bài thực hành tạo **một project Java** với hai source sets bổ sung:

- **integrationTest**: JUnit 5 test, kiểm tra class production và một fixture resource;
- **tools**: Java CLI dùng class production và một tool resource, đóng gói ra **toolsJar** riêng.

Project sử dụng **application** plugin để có task **run** cho main source set, Java 17 toolchain, JUnit Jupiter dependency từ Maven Central và Gradle Groovy DSL.

### 9.1. Cấu trúc thư mục

~~~text
source-set-lab/
├── settings.gradle
├── build.gradle
├── gradlew                    # Wrapper được sinh một lần
├── gradlew.bat                # Wrapper được sinh một lần
├── gradle/wrapper/...         # Wrapper được sinh một lần
└── src/
    ├── main/
    │   └── java/demo/
    │       ├── Greeting.java
    │       └── Main.java
    ├── test/
    │   └── java/demo/GreetingTest.java
    ├── integrationTest/
    │   ├── java/demo/integration/FlowIntegrationTest.java
    │   └── resources/flow/status.txt
    └── tools/
        ├── java/demo/tools/ToolMain.java
        └── resources/tool.properties
~~~

Chọn Gradle Wrapper tương thích với JDK đang chạy Gradle và Java 17 toolchain. Nếu bắt đầu từ repo mới không có Wrapper, dùng Gradle CLI đã được cài để chạy **gradle wrapper**, sau đó commit **gradlew**, **gradlew.bat** và **gradle/wrapper/**. Không cần tạo **src/main/resources** nếu project không có resource production.

### 9.2. settings.gradle

~~~groovy
dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS

    repositories {
        mavenCentral()
    }
}

rootProject.name = 'source-set-lab'
~~~

**mavenCentral()** dùng để tải JUnit dependencies. **FAIL_ON_PROJECT_REPOS** giúp tránh thêm repository trong build.gradle không kiểm soát. Lab không sử dụng external Gradle plugin; **application** là core plugin, nên không cần plugin portal để giải quyết một plugin bên ngoài.

### 9.3. build.gradle — cấu hình hoàn chỉnh

~~~groovy
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
    mainClass = 'demo.Main'
}

// Tạo 2 source sets ngoài main và test.
sourceSets {
    integrationTest {
        java.srcDir 'src/integrationTest/java'
        resources.srcDir 'src/integrationTest/resources'

        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }

    tools {
        java.srcDir 'src/tools/java'
        resources.srcDir 'src/tools/resources'

        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}

// Kế thừa dependency của production khi phù hợp.
configurations {
    integrationTestImplementation.extendsFrom implementation
    integrationTestRuntimeOnly.extendsFrom runtimeOnly

    toolsImplementation.extendsFrom implementation
    toolsRuntimeOnly.extendsFrom runtimeOnly
}

// Mỗi test source set có dependency JUnit riêng.
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'

    integrationTestImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    integrationTestRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

def integrationTestTask = tasks.register('integrationTest', Test) {
    description = 'Chạy integration tests'
    group = 'verification'

    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath

    dependsOn(tasks.named('integrationTestClasses'))
    shouldRunAfter(tasks.named('test'))
    useJUnitPlatform()
}

tasks.named('check') {
    dependsOn(integrationTestTask)
}

def toolsJarTask = tasks.register('toolsJar', Jar) {
    group = 'build'
    description = 'Đóng gói riêng source set tools'
    archiveClassifier.set('tools')

    from(sourceSets.tools.output)
    dependsOn(tasks.named('toolsClasses'))
}

tasks.named('assemble') {
    dependsOn(toolsJarTask)
}

tasks.register('runTools', JavaExec) {
    group = 'application'
    description = 'Chạy CLI từ source set tools'
    mainClass.set('demo.tools.ToolMain')
    classpath = sourceSets.tools.runtimeClasspath
    dependsOn(tasks.named('toolsClasses'))
}
~~~

Đây là **toàn bộ build.gradle** cho lab, không phải một phần phụ thuộc vào file plugin custom khác.

Giải thích các mối nối chính:

1. **application** áp dụng các khả năng Java plugin và tạo **run**, **jar**, **check**, **assemble**, **build** cùng những task liên quan.
2. **sourceSets.integrationTest** và **sourceSets.tools** tạo model riêng; chúng không tự đưa mã vào main.
3. **compileClasspath += sourceSets.main.output** giúp compilation của hai source sets phụ nhìn thấy **demo.Greeting**.
4. **runtimeClasspath += sourceSets.main.output** cung cấp production classes/resources khi chạy integration tests hoặc ToolMain.
5. **configurations.extendsFrom** chỉ chia sẻ dependency declarations từ production scopes, không nhập mã nguồn vào nhau.
6. **integrationTestImplementation** và **integrationTestRuntimeOnly** thêm JUnit riêng cho integrationTest, không dựa vào việc testImplementation sẽ tự được kế thừa.
7. **integrationTestTask** cung cấp test class dirs, classpath và framework; sau đó **check.dependsOn(integrationTestTask)** biến suite thành quality gate.
8. **toolsJarTask** đóng gói **tools.output**, đặt classifier **tools** và nối vào **assemble**.
9. **runTools** chạy ToolMain bằng tools.runtimeClasspath; nó không yêu cầu Java application plugin phải biết mainClass của tools.
10. **shouldRunAfter** chỉ ưu tiên thứ tự giữa unit/integration test khi chúng cùng được chọn; không thêm phụ thuộc giữa hai test suites.

### 9.4. src/main/java/demo/Greeting.java

~~~java
package demo;

public final class Greeting {
    private Greeting() {
    }

    public static String say(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Class **Greeting** là mã production của source set main, được cả unit test, integration test và tools sử dụng.

### 9.5. src/main/java/demo/Main.java

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("APP=" + Greeting.say("Gradle"));
    }
}
~~~

**Main** là entrypoint của application plugin. Task **run** dùng **application.mainClass** để khởi chạy.

### 9.6. src/test/java/demo/GreetingTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {
    @Test
    void greetsByName() {
        assertEquals("Xin chào, Gradle!", Greeting.say("Gradle"));
    }
}
~~~

Task **test** do Java plugin tạo dùng **src/test/java** và **testImplementation/testRuntimeOnly** trong build.gradle. Đây là unit test, **không phải** integrationTest chỉ vì class name kết thúc bằng Test.

### 9.7. src/integrationTest/java/demo/integration/FlowIntegrationTest.java

~~~java
package demo.integration;

import demo.Greeting;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class FlowIntegrationTest {
    @Test
    void greetsAndLoadsFixture() throws IOException {
        assertEquals(
                "Xin chào, Integration!",
                Greeting.say("Integration"));

        try (InputStream input = getClass()
                .getResourceAsStream("/flow/status.txt")) {
            assertNotNull(input, "Missing integration fixture");

            String fixture = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8).strip();

            assertEquals("PING-OK", fixture);
        }
    }
}
~~~

Điểm kiểm chứng:

- **demo.Greeting** đến từ **sourceSets.main.output** trên integrationTest compile/runtime classpaths.
- **org.junit.jupiter.api.Test** đến từ **integrationTestImplementation**.
- **/flow/status.txt** đến từ **processIntegrationTestResources**, được cung cấp trên runtimeClasspath của integrationTest.
- **assertNotNull** giúp lỗi resource rõ ràng nếu thiếu; **try-with-resources** đóng InputStream.
- **readAllBytes()** và **strip()** được Java 17 hỗ trợ.
- Unit-test task **test** không tự quét **src/integrationTest/java**; test này thuộc riêng task integrationTest.

### 9.8. src/integrationTest/resources/flow/status.txt

Nội dung file UTF-8, một dòng:

~~~text
PING-OK
~~~

Gradle sẽ copy/process resource đó vào output resources của integrationTest. Trong runtime classpath, đường dẫn resource **/flow/status.txt** tương ứng với **flow/status.txt** ở thư mục resource root.

### 9.9. src/tools/java/demo/tools/ToolMain.java

~~~java
package demo.tools;

import demo.Greeting;
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class ToolMain {
    private ToolMain() {
    }

    public static void main(String[] args) throws IOException {
        Properties config = new Properties();

        try (InputStream input = ToolMain.class
                .getResourceAsStream("/tool.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing tool.properties");
            }
            config.load(input);
        }

        String mode = config.getProperty("mode");
        if (mode == null || mode.isBlank()) {
            throw new IllegalStateException("Missing mode");
        }

        System.out.println(
                "TOOL[" + mode + "] " + Greeting.say("Tools"));
    }
}
~~~

**ToolMain** thuộc source set **tools**, không thuộc main. Khi biên dịch nó, class **Greeting** có sẵn nhờ **tools.compileClasspath += main.output**. Khi chạy nó, **Greeting** và tool.properties có sẵn nhờ tools.runtimeClasspath.

### 9.10. src/tools/resources/tool.properties

~~~properties
mode=DEMO
~~~

File dùng ký tự ASCII nên **Properties.load(InputStream)** đọc đúng không cần quan tâm charset đặc biệt. Nếu thay bằng nội dung Unicode phức tạp, nên xem cơ chế đọc properties theo định dạng/cách mã hóa mong muốn, thay vì giả định Properties.load(InputStream) dùng UTF-8.

### 9.11. Lệnh chạy trên Linux/macOS

~~~bash
./gradlew --version
./gradlew sourceSets
./gradlew tasks --all
./gradlew compileIntegrationTestJava
./gradlew integrationTest
./gradlew check
./gradlew toolsClasses
./gradlew toolsJar
./gradlew assemble
./gradlew clean build
./gradlew -q run
./gradlew -q runTools
~~~

**Dòng stdout chính xác của Java Main qua task run:**

~~~text
APP=Xin chào, Gradle!
~~~

**Dòng stdout chính xác của Java ToolMain qua task runTools:**

~~~text
TOOL[DEMO] Xin chào, Tools!
~~~

Gradle vẫn có thể in thêm log task, daemon, cảnh báo và thông báo thành công. Hai block trên là **stdout do Java source in**, không phải toàn bộ console output của lệnh Gradle.

Sau **./gradlew clean build**, với mã và JUnit dependencies có thể resolve, unit test và integration test đều được chạy do **check**, và cả hai JAR được tạo do **assemble**.

Với một lần build thành công, các artifact mong đợi là:

~~~text
build/libs/source-set-lab-1.0.0.jar
build/libs/source-set-lab-1.0.0-tools.jar
~~~

Để xem contents:

~~~bash
jar tf build/libs/source-set-lab-1.0.0.jar
jar tf build/libs/source-set-lab-1.0.0-tools.jar
~~~

JAR chính nên có **demo/Main.class**, **demo/Greeting.class**, còn tools JAR nên có **demo/tools/ToolMain.class** và **tool.properties**. Đừng yêu cầu danh sách in đúng thứ tự vì JAR có thể chứa manifest/directory entries và thứ tự tùy công cụ.

**Không nên thấy FlowIntegrationTest.class hay GreetingTest.class trong production JAR hoặc tools JAR.** Nếu thấy, hãy xem task Jar có vô tình lấy **sourceSets.test.output** hoặc **sourceSets.integrationTest.output** không.

### 9.12. Chạy hai JAR bằng Java launcher

**JAR chính** không nhất thiết có manifest **Main-Class** để chạy bằng **java -jar** chỉ vì Gradle biết **application.mainClass**. Dùng classpath và tên main class tường minh:

~~~bash
java -cp build/libs/source-set-lab-1.0.0.jar demo.Main
~~~

Kết quả:

~~~text
APP=Xin chào, Gradle!
~~~

**ToolMain cần cả tools JAR và main JAR** vì tools JAR không chứa Greeter:

~~~bash
java -cp "build/libs/source-set-lab-1.0.0.jar:build/libs/source-set-lab-1.0.0-tools.jar" demo.tools.ToolMain
~~~

Kết quả:

~~~text
TOOL[DEMO] Xin chào, Tools!
~~~

Dấu **:** là phân tách classpath trên Linux/macOS. Đừng dùng lệnh **java -jar tools.jar** và mong nó tự tìm main JAR; classifier không tự thiết lập runtime classpath hoặc manifest Main-Class.

### 9.13. Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat sourceSets
.\gradlew.bat tasks --all
.\gradlew.bat integrationTest
.\gradlew.bat check
.\gradlew.bat toolsJar
.\gradlew.bat assemble
.\gradlew.bat clean build
.\gradlew.bat -q run
.\gradlew.bat -q runTools

jar tf build\libs\source-set-lab-1.0.0.jar
jar tf build\libs\source-set-lab-1.0.0-tools.jar

java -cp "build\libs\source-set-lab-1.0.0.jar;build\libs\source-set-lab-1.0.0-tools.jar" demo.tools.ToolMain
~~~

Trên Windows, dấu phân tách classpath là **;**. Nếu PowerShell hiển thị dấu tiếng Việt sai, kiểm tra cấu hình terminal/encoding mà không sửa sai classpath hoặc source.

### 9.14. Kiểm chứng Java 17 bằng javac/java độc lập

Để kiểm tra Java source code production và tools mà không phụ thuộc Gradle tasks, chạy tại thư mục project.

Linux/macOS:

~~~bash
mkdir -p out

javac --release 17 -d out \
  src/main/java/demo/Greeting.java \
  src/main/java/demo/Main.java \
  src/tools/java/demo/tools/ToolMain.java

cp src/tools/resources/tool.properties out/tool.properties

java -cp out demo.Main
java -cp out demo.tools.ToolMain
~~~

Stdout theo thứ tự:

~~~text
APP=Xin chào, Gradle!
TOOL[DEMO] Xin chào, Tools!
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -d out src\main\java\demo\Greeting.java src\main\java\demo\Main.java src\tools\java\demo\tools\ToolMain.java

Copy-Item src\tools\resources\tool.properties out\tool.properties

java -cp out demo.Main
java -cp out demo.tools.ToolMain
~~~

**Các lệnh javac trên cố ý không biên dịch các file JUnit**, vì JUnit classes cần external JAR classpath. Để xác minh integration test compilation, test execution, source sets, classpath wiring và packaging, dùng **Gradle Wrapper** như mục 9.11/9.13. Không coi bài test javac độc lập là bằng chứng cho configuration Gradle đã đúng.

## 10. Kiểm chứng source sets, classpaths và task graph

### 10.1. Task sourceSets

Java plugin cung cấp báo cáo:

~~~bash
./gradlew sourceSets
~~~

Nó mô tả các source sets và thông tin liên quan. Khi gặp lỗi đặt tên thư mục, đối chiếu directory thực tế với output của report.

### 10.2. Danh sách task

~~~bash
./gradlew tasks --all
~~~

Kiểm tra các task:

~~~text
compileJava
compileTestJava
compileIntegrationTestJava
compileToolsJava
processIntegrationTestResources
processToolsResources
integrationTestClasses
toolsClasses
integrationTest
toolsJar
runTools
check
assemble
build
~~~

Danh sách này mô tả **những task mà lab có**. Chúng không phải tất cả đều được thực thi mỗi khi bạn gọi **tasks --all**; đó là task discovery, không phải task execution.

### 10.3. Dependency reports theo source set

~~~bash
./gradlew dependencies --configuration integrationTestCompileClasspath
./gradlew dependencies --configuration integrationTestRuntimeClasspath
./gradlew dependencies --configuration toolsCompileClasspath
./gradlew dependencies --configuration toolsRuntimeClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Theo thiết kế:

- **integrationTestCompileClasspath** có JUnit và main output theo cách source set được cấu hình.
- **integrationTestRuntimeClasspath** có integrationTest output, main output, JUnit API/engine/launcher và dependencies cần thiết.
- **toolsCompileClasspath/toolsRuntimeClasspath** phục vụ ToolMain, không cần có JUnit.
- **runtimeClasspath** của main không cần đưa integrationTest hoặc tools outputs vào.

Lưu ý **dependencies report** chủ yếu mô tả dependency graph, không luôn liệt kê rõ file directories như **sourceSets.main.output** đã thêm bằng **+=**. Khi cần xem từng file path, kiểm tra **JavaCompile.classpath** hoặc **JavaExec/Test.classpath** phù hợp, tránh in thông tin nhạy cảm trên CI.

### 10.4. Dry run để đọc task graph

~~~bash
./gradlew check --dry-run
./gradlew assemble --dry-run
./gradlew build --dry-run
~~~

**--dry-run** cho phép quan sát tasks được lên lịch mà không chạy actions bình thường. Dùng nó để xác nhận:

- **check** có integrationTest;
- **assemble** có toolsJar;
- **build** có cả hai nhánh check và assemble;
- task compile/process classes của source set có trong graph khi cần.

**--dry-run không chứng minh JUnit thực sự chạy hoặc JAR có nội dung đúng.** Phải chạy build thực và kiểm tra reports/artifacts. Thứ tự console không phải một API ổn định để ứng dụng phụ thuộc.

### 10.5. Test reports

Java Test task thường tạo test results và HTML reports dưới **build/test-results/** và **build/reports/tests/** theo tên task:

~~~text
build/test-results/test/
build/test-results/integrationTest/
build/reports/tests/test/
build/reports/tests/integrationTest/
~~~

Đường dẫn có thể thay nếu người dùng cấu hình report destinations khác. Đây là chứng cứ hữu ích để phân biệt “task có trong graph” với “JUnit thực sự phát hiện và chạy test”.

**Đừng đánh đồng** báo cáo test task **test** với **integrationTest**; chúng dùng source sets, classpath và reports riêng. Nếu CI thu thập JUnit XML, phải bao gồm cả hai đường dẫn nếu tổ chức muốn nhìn thấy integration test results.

## 11. JVM Test Suite plugin: phương án khác cho integration tests

Gradle hiện hành cung cấp **JVM Test Suite plugin** để khai báo test suites ở mức cao, thay vì tự tạo từng SourceSet và Test task. Tài liệu mô tả phần này là **incubating** trong một số phiên bản; nên kiểm tra Gradle Wrapper/project plugin version trước khi migrate.

Một đoạn **minh họa phương án thay thế**:

~~~groovy
plugins {
    id 'java-library'
    id 'jvm-test-suite'
}

testing {
    suites {
        test {
            useJUnitJupiter()
        }

        integrationTest(JvmTestSuite) {
            useJUnitJupiter()

            dependencies {
                implementation project()
            }

            targets {
                all {
                    testTask.configure {
                        shouldRunAfter(test)
                    }
                }
            }
        }
    }
}

tasks.named('check') {
    dependsOn(testing.suites.integrationTest)
}
~~~

**Đây không phải khối để dán vào lab mục 9**, vì sẽ tạo cấu hình/task có cùng tên **integrationTest** với cách làm thủ công. Chọn **một** trong hai mô hình cho cùng suite, không đồng thời dùng cả hai.

Ưu điểm của JVM Test Suite:

- Tạo source set, test task và model suite/target theo quy ước;
- DSL cho framework như **useJUnitJupiter()**;
- Khai báo dependencies của suite theo model thống nhất;
- Dễ mở rộng thêm functional/contract suites khi Gradle version/plugin hỗ trợ.

Nhưng nếu bạn cần **source set tools và một JAR riêng**, bạn vẫn phải thiết kế task **Jar/JavaExec** hoặc plugin khác để đóng gói đúng. JVM Test Suite không biến mọi custom source set thành artifact trong assemble.

### 11.1. Manual SourceSet vs JVM Test Suite

| Tiêu chí | Source set + Test task thủ công | JVM Test Suite |
| --- | --- | --- |
| Kiểm soát Java/resources dirs | Cao | Có DSL sources riêng |
| Tự cấu hình testClassesDirs/classpath | Có | Plugin thường làm thay |
| Tích hợp framework/dependencies | Tự cấu hình | DSL tích hợp |
| Nối check | Vẫn cần quyết định | Vẫn cần nối nếu muốn quality gate |
| Dùng cho toolsJar | Rất trực tiếp | Không thay thế Jar task |
| Dễ hiểu Gradle internals | Tốt cho học tập | Tốt cho build suites lớn |
| Mức độ ổn định API | API Java SourceSet lâu đời | Kiểm tra lifecycle/incubating theo Gradle version |

Lab chọn **manual SourceSet** để thấy rõ compile/test/packaging wiring, không vì JVM Test Suite là sai.

## 12. Source set và phiên bản Java/toolchain

Java plugin cho phép cấu hình toolchain:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Trong lab, compilation của main/test/integrationTest/tools dùng Java compile tasks do cùng Java plugin quản lý, nên thông thường cùng toolchain convention. Nếu một source set phải target Java khác, hãy cấu hình **JavaCompile** task tương ứng một cách rõ ràng và kiểm tra API/bytecode compatibility.

Ví dụ minh họa:

~~~groovy
tasks.named('compileToolsJava', JavaCompile) {
    options.release.set(17)
}
~~~

**options.release = 17** chỉ phù hợp khi compiler JDK hỗ trợ **--release 17**; nó không tự tải JDK hoặc làm một tool được viết cho Java 21 chạy trên Java 17. Trong lab chính, Java toolchain 17 đã đủ nên không cần thêm override này.

### 12.1. Java source set không tự cấp quyền truy cập test internals

Source set **integrationTest** trong lab nhìn thấy production output. Nó không tự nhìn thấy **src/test/java** classes. Nếu integration tests cần chia sẻ utility với unit tests, cân nhắc:

- Tách các helpers thành **test fixtures**;
- Tạo source set helpers riêng với scope/lifecycle rõ;
- Hoặc đưa helper vào thư viện kiểm thử độc lập.

Đừng đưa sourceSets.test.output vào mọi integrationTest runtimeClasspath chỉ để nhanh chóng hết lỗi import; điều đó có thể làm integration tests phụ thuộc quá nhiều vào private unit-test helpers và giảm khả năng cô lập.

### 12.2. Java module system và module-info.java

Nếu production dùng **module-info.java** (JPMS), source set bổ sung có thể cần cấu hình **module path**, **--patch-module**, **--add-reads** hoặc cách test như black-box module riêng. Mô hình classpath của lab không dùng JPMS nên chạy như Java classpath app thông thường.

Không tự suy rằng thêm **sourceSets.main.output** vào compileClasspath luôn đủ cho mọi JPMS case. Với integration tests kiểu black-box, có thể build artifact production và gọi nó như external process/API thay vì truy cập internal packages.

## 13. Đóng gói: JAR, distribution, publishing và variants

### 13.1. assemble không đồng nghĩa publish

**assemble** xây dựng artifacts cần thiết trong local build. **publish** (nếu áp dụng maven-publish) upload publications vào một repository. Kết nối **toolsJar** với **assemble** không làm Gradle tự đưa toolsJar vào Maven publication.

Nếu cần publish công cụ, thiết kế publication/artifact một cách riêng và kiểm tra repository credentials/metadata. Đừng thêm file test vào publication vì build local đã sinh nó.

### 13.2. Application distributions không tự gom mọi source set

Application plugin thường tạo distributions cho production application dựa trên main application và dependencies của nó. **toolsJar** được tạo thêm bởi assemble nhưng **không tự được chèn vào application distribution hoặc start scripts**.

Nếu muốn phân phối tool CLI, bạn cần cấu hình distribution riêng, start script riêng, hoặc một plugin/structure phù hợp. Đừng giả định vì **build/libs** có hai JAR nên **installDist** tự chứa đầy đủ và chạy được cả hai entrypoints.

### 13.3. Fat JAR khác toolsJar

Task:

~~~groovy
tasks.register('toolsJar', Jar) {
    archiveClassifier.set('tools')
    from(sourceSets.tools.output)
}
~~~

chỉ lấy output của tools. Nó **không** trộn JARs từ runtimeClasspath. Muốn đóng gói dependency JAR vào cùng artifact cần một chiến lược uber JAR/shadow có kiểm soát, xử lý duplicate resources, licenses, service descriptors và bytecode compatibility. Không nên tự dùng **zipTree** bừa bãi để kéo cả JUnit và production dependencies vào một JAR.

### 13.4. Variants và capabilities

Java Library Plugin công bố các variants như **apiElements/runtimeElements** cho main Java component. Tạo **toolsJar** không tự công bố một variant mới với capability cho tools. Nếu modules khác cần tiêu thụ tools artifact qua variant-aware dependency resolution, nên đăng ký **feature variant** hoặc consumable configuration đúng attributes/capabilities/metadata.

Không nhầm **source set**, **variant** và **artifact**:

- Source set tổ chức source/classes/resources;
- Task Jar lấy output tạo artifact;
- Variant mô tả một cách sử dụng của component và có thể chứa artifact cùng metadata/dependencies;
- Publication xuất bản artifact/metadata cho consumer ngoài build.

Một source set có thể phục vụ nhiều tasks và artifacts; một variant có thể chọn nhiều artifact sets, không nhất thiết 1:1.

## 14. Test reports, coverage và CI quality gates

### 14.1. check là quality gate chung

Sau khi cấu hình:

~~~groovy
tasks.named('check') {
    dependsOn(tasks.named('integrationTest'))
}
~~~

CI chạy **./gradlew check** sẽ lựa chọn cả unit tests và integration tests. Nếu integration test thất bại, build mặc định có exit code không thành công, trừ khi tổ chức cố tình thay đổi **ignoreFailures**, điều thường không nên cho quality gate.

**Không chạy integration tests một cách ngầm định** khi chỉ yêu cầu **:app:run** hoặc **jar** nếu không có dependency nghiệp vụ tương ứng. Tách lifecycle giúp developer có thể chạy nhanh phần mình cần, trong khi CI vẫn chạy check đầy đủ.

### 14.2. Report HTML và XML

Khi CI thu thập reports, cấu hình thu thập:

~~~text
build/test-results/test/*.xml
build/test-results/integrationTest/*.xml
~~~

Dấu **\*** chỉ là glob pattern minh họa, không phải đường dẫn file cố định. Mỗi Test task tạo reports riêng nếu được chạy và reports được bật.

Không giả định **integrationTest** có 0 tests nhưng BUILD SUCCESSFUL là một trạng thái chấp nhận được. Kiểm tra số test cases và outcome thực tế. Trong Gradle hiện đại, test framework runtime dependencies/launcher cần khai báo tường minh; dựa vào dependency bị leak từ Gradle có thể lỗi khi nâng version.

### 14.3. JaCoCo không tự tổng hợp mọi Test task

Nếu dự án dùng **jacoco**, task báo cáo **jacocoTestReport** thường gắn với Test task mặc định hoặc cấu hình cụ thể. Một custom task **integrationTest** có thể cần cấu hình coverage, destination execution data hoặc report aggregation riêng.

Đừng xem coverage report mặc định là đã bao gồm integration tests khi chưa kiểm tra source file/execution data. Nếu muốn aggregate cả unit và integration coverage, hãy cấu hình JaCoCo reporting/aggregation tương ứng và bảo đảm các tasks đã chạy.

### 14.4. Integration tests thường cần tài nguyên ngoài

Khi integration tests cần database, HTTP server hoặc Docker:

- Cấu hình tài nguyên riêng cho mỗi test suite/run;
- Giảm phụ thuộc vào port cố định hoặc shared mutable state;
- Dùng timeout, health check, cleanup;
- Không commit credentials trong **src/integrationTest/resources**;
- Cân nhắc Gradle Build Service hoặc orchestration của CI để quản lý tài nguyên đắt đỏ;
- Giữ **maxParallelForks** và parallelism hợp lý;
- Phân biệt **source set wiring** với **external service lifecycle**.

Tạo source set mới chỉ giúp tổ chức code/gradle tasks; nó không tự khởi động database hoặc bảo đảm test isolation.

## 15. Những lỗi dễ mắc và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách sửa |
| --- | --- | --- |
| **compileIntegrationTestJava cannot find symbol Greeting** | Thiếu main output trên integrationTest compileClasspath | **compileClasspath += sourceSets.main.output** |
| JUnit **org.junit.jupiter.api.Test** không được tìm thấy | Thiếu integrationTestImplementation hoặc source set tạo sau dependencies block | Khai báo source set trước dependencies, thêm JUnit đúng config |
| **ClassNotFoundException** khi chạy integrationTest | runtimeClasspath thiếu main output/JUnit runtime | Nối main.output và integrationTestRuntimeOnly, kiểm tra dependencies |
| **No tests found for given includes** | TestClassesDirs sai, test class không được compile hoặc pattern không khớp | Kiểm tra sourceSet.output.classesDirs, task Test, test filters |
| Task **integrationTest** không tồn tại | Chỉ tạo source set, chưa đăng ký Test task | **tasks.register('integrationTest', Test)** |
| Task tồn tại nhưng **check** không chạy nó | Chưa **check.dependsOn** | Nối task provider vào check |
| JUnit tests không phát hiện | Thiếu useJUnitPlatform hoặc Engine/Launcher | **useJUnitPlatform()**, khai báo JUnit dependencies |
| **toolsJar** không được tạo khi assemble | Chưa nối vào assemble | **assemble.dependsOn(toolsJar)** |
| toolsJar không chứa ToolMain | **from** sai source set output hoặc toolsClasses chưa compile | **from(sourceSets.tools.output)**, kiểm tra toolsClasses |
| toolsJar không chứa tool.properties | Resource đặt sai thư mục hoặc processToolsResources sai | Đặt **src/tools/resources/tool.properties**, kiểm tra task/resources |
| **java -jar tools.jar** lỗi | Thiếu Main-Class/thiếu main JAR/classpath | Dùng **java -cp main.jar:tools.jar demo.tools.ToolMain** |
| **NoClassDefFoundError demo/Greeting** khi chạy toolsJar đơn lẻ | toolsJar không chứa main classes | Thêm main jar vào runtime classpath, không giả là fat JAR |
| Main JAR chứa integration tests | jar task lấy nhầm integrationTest.output | Giữ **jar** trên main, tạo archive riêng nếu cần |
| **Duplicate entry** khi đóng JAR | Trộn outputs có class/resource trùng | Tách outputs, sửa tên file, chỉ dùng duplicatesStrategy có chủ đích |
| Test resources không đọc được | Resource path dùng thiếu dấu / hoặc không nằm trong classpath | Kiểm tra resource root, **getResourceAsStream("/flow/status.txt")** |
| Unit tests và integration tests dùng chung dependencies ngoài ý muốn | extendsFrom quá rộng | Giới hạn declarations theo source set, giảm coupling |
| Integration tests chạy trước unit tests | Không đặt ưu tiên, scheduler khác mong đợi | **shouldRunAfter(test)** khi cùng được chọn |
| Compiler JDK version không phù hợp | Toolchain chưa có/không provision | Cài/cấu hình Java 17 toolchain và Gradle Wrapper tương thích |
| CI chỉ có unit-test report | Không chạy check hoặc không thu thập integrationTest reports | Nối check, collect cả hai test XML directories |
| Gradle **UP-TO-DATE** làm test/compile không in log | Inputs/outputs không đổi, task không cần chạy lại | Kiểm tra task outcome; **--rerun-tasks** chỉ khi cần điều tra |
| toolsJar không có trên Maven repo | assemble khác publish, chưa thêm publication | Cấu hình MavenPublication/artifact/feature phù hợp |
| IntelliJ báo integrationTest là production sources | IDE import chưa nhận diện test source set | Reimport Gradle, đánh dấu test roots theo IDE plugin |
| Việc đổi classpath không có hiệu lực | Thay vì cộng đã overwrite hoặc chỉnh sai source set | Kiểm tra **sourceSets** report và **+=** trên classpaths |

### 15.1. Checklist chẩn đoán theo thứ tự

~~~text
Source set bổ sung không hoạt động?
           |
           v
1. Đang dùng đúng Gradle Wrapper và project root?
           |
           v
2. sourceSets có integrationTest/tools như mong muốn?
           |
           v
3. Java/resources directories có file đúng package/path?
           |
           v
4. compileClasspath có main.output và dependencies cần thiết?
           |
           v
5. runtimeClasspath có output, main.output và runtime libraries?
           |
           v
6. compile...Java / process...Resources / ...Classes chạy tốt?
           |
           v
7. Custom Test/JavaExec/Jar task có classpath/from đúng?
           |
           v
8. check/assemble có dependsOn task bổ sung?
           |
           v
9. Test reports/JAR contents/stdout có đúng thực tế?
           |
           v
10. CI cache, toolchain và external services có được cấu hình?
~~~

### 15.2. Các lệnh cụ thể

~~~bash
./gradlew --version
./gradlew sourceSets
./gradlew tasks --all
./gradlew dependencies --configuration integrationTestRuntimeClasspath
./gradlew compileIntegrationTestJava --info
./gradlew integrationTest --stacktrace
./gradlew check --dry-run
./gradlew assemble --dry-run
./gradlew toolsJar --info
jar tf build/libs/source-set-lab-1.0.0-tools.jar
~~~

Không xóa **~/.gradle**, thay đổi repository hoặc tắt test quality gate chỉ vì một task không chạy. Bắt đầu bằng kiểm tra source set name, task classpath và dependency graph; xác định nguyên nhân trước khi dùng **clean**/**--rerun-tasks**.

## 16. Những hiểu lầm cần tránh

| Hiểu lầm | Sự thật |
| --- | --- |
| “Thêm sourceSets.integrationTest thì tự có integrationTest task.” | Compile/classes tasks được tạo; Test task phải cấu hình riêng hoặc dùng JVM Test Suite. |
| “Có testImplementation là integrationTest dùng được JUnit.” | Không tự kế thừa; khai báo integrationTestImplementation hoặc extendsFrom có chủ đích. |
| “Nguồn main phải thêm vào integrationTest.java.srcDirs.” | Không; dùng main.output trên compile/runtime classpaths. |
| “runtimeClasspath = main.output là đủ.” | Dùng **+=** để giữ output và dependencies của chính source set. |
| “shouldRunAfter(test) khiến test luôn chạy trước integrationTest.” | Chỉ ưu tiên khi cả hai được chọn; không tự thêm dependency. |
| “check tự chạy tất cả các Test tasks trong build.” | Không; cần dependsOn hoặc plugin wiring phù hợp. |
| “assemble tự đóng gói mọi source set.” | Không; cần archive task và assemble.dependsOn. |
| “JAR tools có classifier là tự chạy được.” | Không; cần runtime classpath, Main-Class/entrypoint và dependencies phù hợp. |
| “toolsJar là một Gradle variant.” | Nó chỉ là archive task cho tới khi mô hình hóa publication/variant. |
| “Test reports mặc định bao trùm mọi test source set.” | Mỗi Test task tạo results riêng; CI cần thu thập đúng. |
| “sourceSet là subproject.” | Một project có thể có nhiều source sets; subproject là Project riêng. |
| “Java toolchain được cài ngay khi ghi JavaVersion.of(17).” | Toolchain có thể yêu cầu JDK đã cài hoặc provisioning được cấu hình. |
| “Đóng gói integrationTest classes vào main JAR là tiện.” | Có thể lộ test code/fixtures/secrets và làm artifact không đúng vai trò. |
| “build thành công chứng minh 100% tests đã chạy.” | Phải xem task outcomes và report test counts, không chỉ exit code. |

## 17. Bài tập thực hành

### Bài 1 — Đổi tên source set

Đổi **integrationTest** thành **intTest** trong **sourceSets** rồi cập nhật:

- **intTestImplementation**;
- **intTestRuntimeOnly**;
- **compileIntTestJava**, **intTestClasses**;
- **sourceSets.intTest.output.classesDirs**;
- **sourceSets.intTest.runtimeClasspath**.

Nếu giữ task chạy tên **integrationTest** cũng được; tên task **Test** không nhất thiết phải trùng tên source set. Vì sao Gradle tạo compilation tasks theo source set name nhưng custom Test task do bạn đặt tên?

### Bài 2 — Bỏ main output

Tạm xóa:

~~~groovy
compileClasspath += sourceSets.main.output
~~~

khỏi source set integrationTest rồi chạy **compileIntegrationTestJava**. Vì sao import **demo.Greeting** lỗi? Khôi phục và giải thích khác nhau giữa việc nối **compiled main output** với việc copy **src/main/java** vào integrationTest source dirs.

### Bài 3 — Bỏ runtime classpath

Tạm bỏ:

~~~groovy
runtimeClasspath += sourceSets.main.output
~~~

khỏi integrationTest rồi chạy **integrationTest**. Nếu compilation vẫn thành công, tại sao runtime có thể không nạp được class production? Khôi phục dòng cấu hình.

### Bài 4 — Bỏ JUnit runtime launcher

Tạm xóa:

~~~groovy
integrationTestRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
~~~

Thử **integrationTest** trên Gradle hiện hành. Ghi nhận lỗi hoặc warning về JUnit Platform runtime/launcher nếu xảy ra, rồi khôi phục. Đừng chỉ thêm JUnit vào testImplementation của source set test để sửa integrationTest.

### Bài 5 — Không nối check

Tạm xóa:

~~~groovy
tasks.named('check') {
    dependsOn(integrationTestTask)
}
~~~

Chạy **check --dry-run**. Vì sao **integrationTest** không nằm trong graph mặc dù task vẫn tồn tại? Khôi phục dependsOn trước khi dùng CI.

### Bài 6 — Không nối assemble

Bỏ **assemble.dependsOn(toolsJarTask)**, chạy **clean assemble** và kiểm tra **build/libs**. Vì sao default main JAR vẫn được tạo nhưng toolsJar có thể không có? Khôi phục nối task.

### Bài 7 — Kiểm tra nội dung artifact

Chạy **clean build**, sau đó:

~~~bash
jar tf build/libs/source-set-lab-1.0.0.jar
jar tf build/libs/source-set-lab-1.0.0-tools.jar
~~~

Liệt kê những class/resource thuộc main và tools; kiểm tra không có JUnit test classes trong hai JARs. Nếu cố tình thêm **from(sourceSets.integrationTest.output)** vào JAR chính, vì sao đó có thể là một lỗi chất lượng hoặc bảo mật?

### Bài 8 — Thêm resource riêng

Thêm file **src/tools/resources/version.txt** và cập nhật ToolMain đọc resource đó. Vì sao cần **processToolsResources** và tools runtimeClasspath, còn **compileToolsJava** không trực tiếp biên dịch file .txt?

### Bài 9 — Thử hướng JVM Test Suite

Tạo một branch thử nghiệm, chuyển integrationTest từ manual source set + Test task sang **JVM Test Suite**. Giữ **toolsJar** theo cách hiện tại. So sánh số dòng cấu hình, API compatibility và điểm nào vẫn phải cấu hình để nối check/assemble.

## 18. Câu hỏi tự kiểm tra

1. Source set là gì? Nó khác Project và Task như thế nào?
2. Java plugin tạo mặc định những source sets nào?
3. Tạo **sourceSets.integrationTest** làm xuất hiện những compile/resource/classes tasks nào?
4. Vì sao không tự có một **Test task integrationTest** được nối vào **check**?
5. **compileClasspath += sourceSets.main.output** giải quyết vấn đề gì?
6. Vì sao dùng **+=** an toàn hơn gán bằng **=** khi chỉ thêm main output?
7. **integrationTestImplementation** có tự kế thừa **testImplementation** không?
8. Khi nào nên dùng **extendsFrom implementation** hoặc **extendsFrom testImplementation**?
9. Hai property bắt buộc cần đặc biệt chú ý trên custom Test task là gì?
10. **useJUnitPlatform()** giải quyết phần nào khi dùng JUnit 5?
11. **shouldRunAfter** có tự làm task dependency không?
12. Khi nào **check** chạy integrationTest?
13. **jar** mặc định đóng gói output source set nào?
14. **toolsJar** được tạo khi nào và vì sao cần **assemble.dependsOn**?
15. Vì sao toolsJar không chạy độc lập nếu ToolMain dùng Greeting?
16. **archiveClassifier** quyết định điều gì, và không quyết định điều gì?
17. **build** khác **publish** ở điểm nào?
18. **JVM Test Suite** có thay thế Jar task cho tools source set không?
19. Nếu muốn dùng Java 17 nhưng Gradle báo toolchain không tìm thấy, nên kiểm tra gì?
20. Để chắc integrationTest thực sự chạy, nên đọc thông tin nào ngoài BUILD SUCCESSFUL?

**Đáp án gợi ý:** (1) nhóm Java source/resources/classpaths/output trong một project; (2) main/test; (3) compileIntegrationTestJava, processIntegrationTestResources, integrationTestClasses và configs liên quan; (4) Java plugin chỉ tự wiring test mặc định, custom suite phải cấu hình; (5) cho integration code tham chiếu production classes; (6) giữ classpath mặc định và dependencies; (7) không; (8) khi thật sự cần chia sẻ dependency scope đã xác định; (9) testClassesDirs và classpath; (10) chọn JUnit Platform để chạy Jupiter; (11) không; (12) khi check.dependsOn(integrationTestTask); (13) main.output; (14) task có thể chạy trực tiếp, muốn assemble chạy thì thêm dependency; (15) class Greeting nằm ở main JAR, cần cả hai trên classpath; (16) tên classifier của artifact, không thêm runtime dependencies/manifest/variant; (17) build tạo local outputs, publish đẩy publication tới repo; (18) không; (19) JDK/toolchain/Gradle version/provisioning; (20) test reports, test counts và task outcomes.

## 19. Checklist trước khi đưa source set mới vào CI

- [ ] Source set có tên rõ, đúng thư mục Java/resources và package.
- [ ] Compile/runtime classpaths chứa production output khi cần, không copy production source để biên dịch hai lần.
- [ ] Dependencies được khai báo ở đúng **<sourceSet>Implementation**/**<sourceSet>RuntimeOnly**.
- [ ] Không để unit-test dependencies lan sang integrationTest nếu không cần.
- [ ] Custom Test task có **testClassesDirs**, **classpath**, **useJUnitPlatform()** đúng.
- [ ] **check** đã phụ thuộc integrationTest nếu CI phải coi nó là quality gate.
- [ ] **shouldRunAfter** chỉ dùng để ưu tiên thứ tự, không thay dependsOn.
- [ ] Custom JavaExec task có mainClass, runtimeClasspath và output classes.
- [ ] JAR mặc định chứa main output; JAR riêng lấy đúng **sourceSets.tools.output**.
- [ ] **assemble** đã nối toolsJar nếu archive đó phải được build cùng các artifacts.
- [ ] JARs không chứa mã kiểm thử, resources nhạy cảm hoặc duplicate entries.
- [ ] Không nhầm thêm archive task với công bố Gradle variant/publication.
- [ ] Gradle Wrapper/JDK 17 toolchain đủ và phù hợp với CI runner.
- [ ] CI thu thập XML/HTML reports cho cả test và integrationTest.
- [ ] Test suite report thực sự có test cases; không chỉ nhìn task xuất hiện.
- [ ] Configuration cache/build cache và test isolation được kiểm tra theo yêu cầu của dự án.
- [ ] Khi áp dụng với Kotlin/Android/JPMS, kiểm tra plugin-specific source-set/variant/module-path APIs thay vì sao chép nguyên mẫu Java thuần.

## 20. Tài liệu Gradle chính thức

- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html)
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle — SourceSet API](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.SourceSet.html)
- [Gradle — SourceSetContainer API](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.SourceSetContainer.html)
- [Gradle — Test Task API](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html)
- [Gradle — Jar Task API](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html)
- [Gradle — Creating and Registering Tasks](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html)
- [Gradle — Managing Dependencies of JVM Projects](https://docs.gradle.org/current/userguide/dependency_management_for_java_projects.html)
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html)

**Ghi nhớ:** Thêm source set mới trong Java Gradle build tạo **một hệ thống source, resources, classpaths và compile tasks riêng**. Nhưng việc đưa nó vào quy trình của dự án phải được **wiring rõ ràng**: test source set cần **Test task + check.dependsOn**, artifact source set cần **Jar task + assemble.dependsOn**, còn runtime cần **JavaExec hoặc classpath đúng**. Giữ ranh giới giữa production, unit test, integration test và tools giúp classpath sạch, test reports đáng tin, JAR không lẫn mã không cần thiết và CI có quality gate đầy đủ.
