# Tránh afterEvaluate, thứ tự cấu hình ngầm và truy cập nội bộ project khác

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Build nhiều dự án

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Hiểu ba giai đoạn Gradle **initialization – configuration – execution** và phân biệt **project evaluation order** với **task execution order**.
2. Giải thích **Project.afterEvaluate** làm gì, không làm gì và lý do việc lạm dụng nó tạo phụ thuộc cấu hình khó kiểm soát.
3. Phát hiện anti-pattern: root **allprojects/subprojects configuration injection**, **evaluationDependsOn**, rootProject.ext/version, **project(':core').tasks/extensions/configurations**, tasks.getByName và Provider.get quá sớm.
4. Phân biệt **khai báo project dependency** qua implementation project(':core') với **đọc trực tiếp mutable Project state** của project khác.
5. Dùng **pluginManager.withPlugin**, **tasks.register**, **tasks.named**, **configureEach**, **Provider** và managed task inputs/outputs thay cho callback vòng đời không cần thiết.
6. Chia sẻ Java 17 toolchain, compiler encoding và quy ước build bằng **precompiled Groovy convention plugin** trong included build **build-logic**; từng module tự áp plugin.
7. Tạo dự án **Gradle Groovy DSL + Java 17** có :core và :app, chạy chương trình với stdout xác định, không dùng afterEvaluate, evaluationDependsOn hoặc đọc task nội bộ của project khác.
8. Biết khi nào dùng **task path string** để lên lịch lifecycle task, và khi nào buộc phải dùng **outgoing variant + artifact dependency** để truyền file giữa projects.
9. Thực hành mô hình **consumable / dependencyScope / resolvable configurations** trong Gradle 9.9 để đưa ZIP hướng dẫn từ :core sang :app mà không biết output directory nội bộ của producer.
10. Hiểu **Isolated Projects** (incubating trong Gradle 9.9), **Configuration Cache**, Configuration on Demand và parallelism: những API nào hạn chế cross-project state access.
11. Chẩn đoán lỗi **cannot access Project state on another project**, afterEvaluate đăng ký trễ, task not found, archive producer không tồn tại, sai variant attributes và task dependencies thiếu.
12. Xây checklist migration cho multi-project build lớn từ cấu hình ngầm sang các hợp đồng được khai báo rõ.

**Nguyên tắc:** Mỗi project **tự cấu hình những task, extensions, dependencies và artifacts của chính mình**. Project khác giao tiếp qua **dependency management và outgoing variants**; chỉ dùng task paths để orchestration khi không tiêu thụ dữ liệu. Khi cần quy ước chung, dùng **convention plugin** để từng project tự áp dụng, thay vì root script đi sửa những projects khác.

## 1. Gradle multi-project không phải một chuỗi build.gradle chạy tuyến tính

Một invocation:

~~~bash
./gradlew :app:run
~~~

đi qua những giai đoạn:

~~~text
1. INITIALIZATION
   settings.gradle:
       rootProject.name
       include('core','app')
       pluginManagement { includeBuild('build-logic') }

2. CONFIGURATION
   Gradle tạo/cấu hình mô hình Project và tasks
       :core (java-library)
       :app (application)
   Resolve dependencies và tạo task graph cần thiết

3. EXECUTION
   Thực thi các tasks theo graph và up-to-date/cache state
       producer outputs nếu cần
       :app:compileJava
       :app:run
~~~

Trong configuration phase, Gradle **không tự gọi các Java task actions** chỉ vì đã nhìn thấy dòng tasks.register hoặc một plugins block. Khi execution phase bắt đầu, Gradle xét **task dependencies**, inputs/outputs và cache để quyết định task nào phải chạy.

### 1.1. Project evaluation khác task execution

| Hoạt động | Giai đoạn | Ý nghĩa |
|---|---|---|
| include('core','app') | Initialization | Hai project paths tồn tại |
| Apply java-library cho :core | Configuration | Đăng ký Java model ở core |
| Apply application cho :app | Configuration | Đăng ký Java model và task run |
| dependencies { implementation project(':core') } | Configuration | App yêu cầu Java component/variant của core |
| tasks.register('generateDoc') | Configuration | Trả TaskProvider, task chưa chắc realized |
| :core:compileJava | Execution | Sản xuất classes của core nếu cần |
| :app:compileJava | Execution | Biên dịch app bằng compile classpath đã chọn |
| :app:run | Execution | Chạy Main.main nếu task thực thi |

**Không có quy tắc chung rằng project có tên đứng trước trong settings phải chạy tất cả tasks trước project còn lại.** Project evaluation order và task execution ordering là hai vấn đề khác nhau.

Ví dụ core phải được compile trước app khi app cần core classes là do **dependency graph**. Nếu một file build.gradle tình cờ được đánh giá trước file khác, điều đó không thay thế hợp đồng dependency.

### 1.2. Các dạng coupling ẩn

Một build có thể hoạt động trên máy phát triển nhưng khó mở rộng khi chứa:

- Root build.gradle áp plugin vào subprojects bằng subprojects { apply plugin: ... }.
- :app đọc rootProject.ext.javaLevel hoặc rootProject.version.
- :app gọi project(':core').tasks.named('jar').get() để lấy file.
- Root hoặc một plugin dùng afterEvaluate để đoán các plugins/tasks đã xuất hiện.
- Một module dùng evaluationDependsOn(':core') rồi lấy mutable extension từ core.
- Custom task đọc file ../core/build/generated/... mà không khai báo producer artifact.
- Task đang cấu hình gọi getByName hoặc TaskProvider.get() khiến task realized sớm.
- Logic “chờ cho project khác xong” được diễn đạt bằng sleep, callback, thứ tự include hoặc forced evaluation.

**Nguy cơ:** Các project bị phụ thuộc vào thời điểm đăng ký/chạy cấu hình nội bộ. Điều đó cản trở configuration avoidance, caching, parallelism và đặc biệt vi phạm giới hạn của Isolated Projects khi đọc mutable state của project khác.

## 2. afterEvaluate làm gì, không làm gì?

Project.afterEvaluate(Closure/Action) thêm callback **chạy sau khi project mục tiêu được đánh giá**. Nó vẫn thuộc **configuration phase**, không phải execution phase.

Ví dụ:

~~~groovy
afterEvaluate {
    println 'Project build script evaluation finished'
}
~~~

Callback này:

- Chạy sau khi build script của **project ấy** đã được đánh giá, nếu được đăng ký đúng lúc.
- **Không** chờ tất cả subprojects cấu hình xong.
- **Không** chờ :core:jar, :app:compileJava hoặc :app:run thực thi.
- **Không** cho phép một project truy cập mutable state của project khác khi Isolated Projects bật.
- **Không** tự giải quyết producer/consumer task dependency.
- **Không** đảm bảo một plugin sẽ tạo ra task/extension mà code của bạn đang tìm nếu plugin ấy chưa được áp.

### 2.1. Mẫu thường gặp nhưng không nên dùng

~~~groovy
// Anti-pattern dùng trong build Java.
afterEvaluate {
    tasks.getByName('compileJava').options.encoding = 'UTF-8'
}
~~~

Vấn đề:
1. getByName là API eager, khiến task object có thể bị realized.
2. Lý do trì hoãn là không rõ: chỉ cần Java Plugin có mặt đã đủ.
3. Callback có thể được đăng ký ở thời điểm project đã evaluated.
4. Nếu code nằm trong lazy task configuration action, afterEvaluate có thể không phù hợp với vòng đời task.
5. Cấu hình khó đọc vì phải xem cả build.gradle lẫn callback để biết giá trị cuối cùng.
6. Plugin khác có thể cấu hình property ở thứ tự khác bạn tưởng.

**Thay bằng:**

~~~groovy
pluginManager.withPlugin('java') {
    tasks.named('compileJava', JavaCompile) {
        options.encoding = 'UTF-8'
    }
}
~~~

Callback phản ứng **khi Java Plugin xuất hiện trong cùng project**, chứ không đợi “mọi thứ” xong. tasks.named giữ task configuration lazy.

Nếu file đã có:

~~~groovy
plugins {
    id 'java'
}
~~~

thì thường chỉ cần:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Không cần callback nào, vì Java plugin đã được áp qua plugins block.

### 2.2. Vì sao afterEvaluate có thể lỗi khi dùng task configuration avoidance?

tasks.register trả **TaskProvider**. Task configuration closure có thể chỉ thực hiện lúc task được realized, muộn hơn project evaluation. Nếu bên trong closure đó bạn mới gọi project.afterEvaluate, Gradle có thể thông báo không thể đăng ký callback vì project đã evaluated.

~~~groovy
// Anti-pattern. Không sao chép vào build thật.
tasks.register('lateTask') {
    afterEvaluate {
        println 'Too late for this kind of lifecycle wiring'
    }
}
~~~

Không sửa bằng cách eager-realize tất cả tasks hoặc gọi task.get() chỉ để afterEvaluate chạy sớm hơn. **Hãy chuyển giá trị sang Provider, callback plugin hoặc task configuration đúng thời điểm.**

### 2.3. afterEvaluate có bị cấm trong mọi Gradle mode không?

**Không.** API vẫn tồn tại. Một số plugin legacy có thể dùng nó trong các tình huống đặc biệt cần tổng hợp cấu hình sau khi một Project được đánh giá. Tuy nhiên, tài liệu Gradle Task Configuration Avoidance cảnh báo rõ việc phối hợp afterEvaluate với task registration lazy.

Không nên chuyển một nhận xét thiết kế thành quy tắc sai rằng “gặp chữ afterEvaluate là build chắc chắn fail” hoặc “Configuration Cache luôn cấm mọi afterEvaluate”. Cần đánh giá từng API/Gradle version. Nhưng với bài toán Java multi-project thông thường, **convention plugin + TaskProvider + dependencies** là kiến trúc bền hơn.

## 3. evaluationDependsOn và thứ tự cấu hình ngầm

Một đoạn trong :app/build.gradle có thể như sau:

~~~groovy
// Anti-pattern: chỉ ép core evaluation để đọc một property.
evaluationDependsOn(':core')
def otherVersion = project(':core').version
~~~

evaluationDependsOn(':core') yêu cầu Gradle đánh giá project :core trước project hiện tại. Nó **không** tạo dependency rằng core Java classes hoặc JAR phải được tạo trước app compiler.

Dù code trên hết báo lỗi “core chưa được đánh giá”, vấn đề thiết kế còn nguyên:

- :app đọc **mutable Project.version của :core**.
- :app biết và phụ thuộc nội bộ cấu hình của :core.
- Build bị thêm configuration-order coupling.
- Isolated Projects vẫn có thể báo violation khi :app đọc mutable state cross-project.
- Cấu hình project phải đánh giá sớm, có thể ảnh hưởng các tối ưu.
- Cần thay contract đúng, không chỉ thay thứ tự.

### 3.1. Cần phân biệt cái gì đang được chờ

| Bạn đang cần gì? | Giải pháp phù hợp |
|---|---|
| Java classes hoặc API của :core | dependencies { implementation project(':core') } |
| ZIP, schema, generated sources của :core | Consumable outgoing variant và consumer resolvable dependency |
| Java 17/encoding cho nhiều projects | Convention plugin, từng project tự áp |
| Giá trị cấu hình chung như release version | Gradle property/Provider đọc từ project hiện tại |
| Một lifecycle task ở project khác phải chạy | dependsOn(':core:check') nếu chỉ cần lên lịch |
| Plugin Java được áp trước khi cấu hình compileJava | plugins block hoặc pluginManager.withPlugin('java') |
| Task đã được đăng ký nhưng chưa realized | TaskProvider/tasks.named/configureEach |
| File generated phải được đọc đúng sau producer | Output property và Provider-backed wiring, qua variant nếu xuyên project |

**Không dùng evaluationDependsOn để khắc phục lỗi thiếu task dependency.** Cả hai có tên gần giống nhưng giải quyết những việc khác nhau.

### 3.2. Đừng nhầm thứ tự include

~~~groovy
include('core', 'app')
~~~

liệt kê projects của build. Nó không phải contract “core hoàn tất configuration và execution trước app”. Thay đổi thứ tự include không phải giải pháp cho dependency thiếu, đặc biệt khi build bật configuration isolation/parallelism.

## 4. Project dependency khác trực tiếp truy cập Project state

### 4.1. Project dependency hợp lệ

~~~groovy
// app/build.gradle
dependencies {
    implementation project(':core')
}
~~~

Gradle biểu diễn **module dependency**. :core phải công bố Java component/variants phù hợp, và Gradle quyết định artifact nào cần trên app compile/runtime classpath. JavaCompile và các producer outputs được nối qua mô hình dependency.

Đây **không phải** thao tác app đọc :core.tasks hoặc :core.extensions. Gradle được thiết kế để cho phép những dependency declarations giữa projects.

### 4.2. Cross-project mutable state access

~~~groovy
// Anti-pattern trong :app.
def jarTask = project(':core').tasks.named('jar')
def archive = jarTask.get().archiveFile.get().asFile

tasks.register('inspectCoreJar') {
    inputs.file(archive)
    doLast {
        println archive.name
    }
}
~~~

Vấn đề:
- project(':core').tasks là mutable state của một Project khác.
- jarTask.get() có thể eager-realize task, không giữ lazy.
- File path cố định lấy sớm có thể lỗi với tool/plugin variant thay đổi.
- app biết tên task và nội bộ artifact của core.
- Việc khai báo inputs.file(File) chưa chứng minh producer wiring và build dependencies đúng.
- Isolated Projects **không cho phép** truy cập tasks container của project khác như thế.

Nếu app chỉ muốn dùng Java API: **implementation project(':core')** đã đủ. Nếu muốn một file ngoài Java JAR: **outgoing artifact/variant** (mục 8).

### 4.3. Cấu hình chéo từ root cũng là coupling

~~~groovy
// root/build.gradle — anti-pattern minh họa.
subprojects {
    apply plugin: 'java'
    tasks.withType(JavaCompile) {
        options.encoding = 'UTF-8'
    }
}
~~~

Root **inject** cấu hình vào subprojects. Nhìn vào :app/build.gradle, người đọc không hiểu vì sao Java plugin hoặc options xuất hiện. Một module chuyên tạo tài liệu cũng có thể bị apply Java dù không cần.

Gradle hiện khuyến nghị **convention plugins** thay cho allprojects/subprojects configuration injection. Từng module áp plugin mô tả quy ước mình thật sự cần.

### 4.4. RootProject getter không phải tất cả đều giống nhau

Trong Isolated Projects:

| Đọc từ :app | Tình trạng khái quát |
|---|---|
| rootProject.version | Mutable state của Project khác, bị hạn chế |
| rootProject.group | Mutable state, bị hạn chế |
| rootProject.ext.anything | Mutable extra properties, bị hạn chế |
| rootProject.tasks/extensions/configurations | Mutable containers, bị hạn chế |
| rootProject.layout/providers | Mutable services state, bị hạn chế |
| rootProject.path/name | Immutable project identity, thường cho phép |
| rootProject.projectDir/rootDir | Immutable location info, thường cho phép |

Không nên nói “mọi tham chiếu rootProject đều bất hợp lệ”. Gradle có **IsolatedProject** view cho những thông tin immutable nếu thật sự cần. Nhưng **ưu tiên vẫn là không dùng Project objects làm kênh truyền dữ liệu giữa modules**.

## 5. Chia sẻ quy ước đúng: convention plugin

Conventions là hành vi build dùng chung, ví dụ:
- Java 17 toolchain.
- Compiler encoding UTF-8.
- JUnit/quality checks.
- Group/version naming policy.
- Javadoc/packaging/release practices.
- Custom tasks/extension defaults.

Thay vì root đi cấu hình nhiều child projects, hãy đóng những chính sách này vào **precompiled convention plugin**. Mỗi project tự khai báo nó cần plugin nào.

### 5.1. buildSrc và included build build-logic

| Đặc điểm | buildSrc | Included build build-logic |
|---|---|---|
| Đưa code vào main build | Tự động nhận diện thư mục buildSrc | Khai báo includeBuild trong settings |
| Tốc độ bắt đầu | Nhanh cho dự án nhỏ/prototype | Cần vài file settings/build logic |
| Phân tách build logic | Có nhưng classpath ảnh hưởng rộng | Ranh giới build độc lập rõ hơn |
| Tái sử dụng/testing/publishing | Có thể làm được | Phù hợp khi mở rộng hoặc publish |
| Khuyến nghị hiện hành | Hợp lý với code đơn giản | Thường ưu tiên cho multi-project lớn |

Gradle **Best Practices for Structuring Builds** khuyến nghị included build **build-logic** trong nhiều tình huống vì rõ ràng và linh hoạt hơn. Không có nghĩa buildSrc bị xóa hoặc mọi project phải chuyển ngay lập tức.

### 5.2. Plugin ID đến từ tên file

Một file:

~~~text
build-logic/src/main/groovy/company.java17-conventions.gradle
~~~

được groovy-gradle-plugin biên dịch thành plugin có ID:

~~~text
company.java17-conventions
~~~

Consumer áp:

~~~groovy
plugins {
    id 'company.java17-conventions'
}
~~~

Đây là **precompiled script plugin**. Không nhầm với legacy script plugin **apply from:**, vốn có cơ chế/cấu trúc khác.

## 6. Bài lab đầy đủ: Gradle Groovy DSL + Java 17

Mục tiêu: tạo Java library :core và Java application :app, chia sẻ toolchain/encoding qua convention plugin, dùng **project dependency** và chạy với kết quả xác định. Không dùng afterEvaluate, evaluationDependsOn, root subprojects {} hay cross-project task lookup.

### 6.1. Cấu trúc

~~~text
decoupled-projects-lab/
├── settings.gradle
├── gradle.properties
├── gradlew                       # nếu đã tạo Wrapper
├── gradlew.bat
├── gradle/wrapper/...
├── build-logic/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/groovy/company.java17-conventions.gradle
├── core/
│   ├── build.gradle
│   ├── API-GUIDE.md               # dùng ở phần nâng cao
│   └── src/main/java/demo/core/Greetings.java
└── app/
    ├── build.gradle
    └── src/main/java/demo/app/Main.java
~~~

Cần JDK/toolchain Java 17 và Gradle Wrapper tương thích. Nếu chưa có Wrapper, dùng Gradle đã cài chạy **gradle wrapper** từ project root rồi dùng ./gradlew hoặc .\gradlew.bat. Phần custom configurations nâng cao sử dụng APIs của Gradle 9.9.

### 6.2. settings.gradle của main build

~~~groovy
pluginManagement {
    includeBuild('build-logic')
}

rootProject.name = 'decoupled-projects-lab'
include('core', 'app')
~~~

- pluginManagement.includeBuild làm convention plugin local khả dụng trong plugins DSL.
- include chỉ đăng ký **hai project :core/:app** trong main build.
- build-logic là **included build**, không phải subproject :build-logic.
- Không cấu hình Java tasks của child ngay ở settings.
- Không cần ép evaluation order.

### 6.3. gradle.properties ở main root

~~~properties
releaseVersion=1.0.0
~~~

Gradle property được các projects trong main build đọc bằng **providers.gradleProperty('releaseVersion')** qua project-local API. Việc này khác với :app đọc **rootProject.version** hoặc **rootProject.ext**.

### 6.4. build-logic/settings.gradle

~~~groovy
rootProject.name = 'build-logic'
~~~

Included build có settings riêng; không include core/app tại đây.

### 6.5. build-logic/build.gradle

~~~groovy
plugins {
    id 'groovy-gradle-plugin'
}
~~~

groovy-gradle-plugin là Gradle core plugin để biên dịch precompiled Groovy DSL script plugins. Trong lab không dùng external plugin repository cho build logic.

### 6.6. build-logic/src/main/groovy/company.java17-conventions.gradle

~~~groovy
plugins {
    id 'java'
}

// Mỗi project tự áp dụng plugin sẽ tự cấu hình chính nó.
group = 'edu.example'
version = providers.gradleProperty('releaseVersion').get()

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

**Vì sao không dùng afterEvaluate?**
- Plugin Java được apply ngay trong plugins block của convention script.
- Java extension đã sẵn sàng để cấu hình toolchain.
- configureEach áp quy tắc cho mọi JavaCompile của **project nhận plugin**, không eager-realize toàn bộ tasks.
- Release version được lấy qua project property chứ không đọc root Project state.
- Plugin code không chạm project(':other').tasks.

**Vì sao ở đây vẫn có get()?** releaseVersion là một project property đã có ở configuration time và dùng để thiết lập **Project.version**. Đây không phải TaskProvider.get() để lấy output chưa được tạo. Với output task/generated files, phải giữ Provider lazy và dùng task property/file collection thay vì get() sớm.

### 6.7. core/build.gradle

~~~groovy
plugins {
    id 'java-library'
    id 'company.java17-conventions'
}
~~~

java-library cho :core có các consumable Java variants (API/runtime); convention plugin cung cấp Java 17/encoding/group/version. Không cần root setup tasks thay cho core.

### 6.8. core/src/main/java/demo/core/Greetings.java

~~~java
package demo.core;

/**
 * API chào hỏi nhỏ dùng trong ví dụ multi-project Gradle.
 *
 * @since 1.0.0
 */
public final class Greetings {
    private Greetings() {
    }

    /**
     * Chào tên không trống sau khi bỏ khoảng trắng hai đầu.
     *
     * @param name tên người nhận
     * @return lời chào
     * @throws IllegalArgumentException nếu name là null hoặc blank
     */
    public static String hello(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name.strip() + "!";
    }

    /**
     * Nhân đôi số nguyên với kiểm tra overflow.
     *
     * @param value giá trị đầu vào
     * @return gấp đôi đầu vào
     * @throws ArithmeticException nếu xảy ra overflow
     */
    public static int twice(int value) {
        return Math.multiplyExact(value, 2);
    }
}
~~~

Code Java 17 hợp lệ. Với " Lan ", method hello trả "Hello, Lan!". Với 3, twice trả 6. Class không phụ thuộc một thư viện ngoài nào.

### 6.9. app/build.gradle

~~~groovy
plugins {
    id 'application'
    id 'company.java17-conventions'
}

application {
    mainClass = 'demo.app.Main'
}

dependencies {
    implementation project(':core')
}
~~~

**Đây là phần quan trọng nhất của lab:**
- :app chỉ dùng công khai **project dependency**.
- Không có project(':core').tasks/getExtensions/getByName.
- Gradle chọn Java compile/runtime variant, tự nối producer task dependencies.
- app không cần biết :core sử dụng JAR hay classes directory cho compile classpath.
- application plugin tạo task :app:run.

### 6.10. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.core.Greetings;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greetings.hello(" Lan "));
        System.out.println("twice=" + Greetings.twice(3));
    }
}
~~~

App chỉ gọi public API của thư viện, không đọc build-model internals của :core.

### 6.11. Chạy ví dụ

Linux/macOS tại main root:

~~~bash
./gradlew :app:run --quiet
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :app:run --quiet
~~~

**Hai dòng stdout do Main.main in chính xác:**

~~~text
Hello, Lan!
twice=6
~~~

Nếu machine không có JDK17 toolchain hoặc Gradle Wrapper không hỗ trợ môi trường, build có thể lỗi trước Main.main; kiểm tra Java toolchain installation/provisioning, không chèn evaluationDependsOn để chữa lỗi JDK.

### 6.12. Quan sát task graph và project dependencies

~~~bash
./gradlew :app:run --dry-run --console=plain
./gradlew :app:compileJava --console=plain
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :core:outgoingVariants
~~~

- --dry-run chỉ **liệt kê task graph dự kiến**, không chạy Java.
- compileClasspath chứa project dependency tới :core và Gradle chọn appropriate Java variant.
- runtimeClasspath cũng chứa :core để app chạy implementation mới.
- :core:outgoingVariants cho thấy những Java component variants core công bố.
- **Không nên khẳng định :core:jar luôn phải chạy trước app:compileJava**; Gradle có thể chọn classes output variant để tránh đóng JAR không cần thiết.
- Thứ tự những task độc lập có thể thay đổi tùy Gradle version/parallelism.

### 6.13. Thay logic nội bộ mà không đổi API

Trong Greetings.hello, tạm đổi:

~~~java
return "Hi, " + name.strip() + "!";
~~~

Giữ nguyên app/Main.java rồi chạy:

~~~bash
./gradlew :app:run --quiet
~~~

**Stdout:**

~~~text
Hi, Lan!
twice=6
~~~

Mô hình project dependency bảo đảm app dùng phiên bản library hiện tại. Nếu public ABI của Greetings không đổi và những inputs khác ổn định, Gradle còn có thể dùng **compile avoidance** để tránh compile lại app; tuy nhiên app runtime vẫn phản ánh implementation mới.

Trước khi tiếp tục bài thực hành khác, trả code về:

~~~java
return "Hello, " + name.strip() + "!";
~~~

### 6.14. Kiểm tra cấu hình dự án độc lập

Chạy:

~~~bash
./gradlew :core:classes
./gradlew :app:classes
./gradlew :app:run --console=plain
~~~

Mỗi task dùng model của project sở hữu nó; task dependencies được Gradle quản lý. Không cần parent script ép core evaluation trước app bằng afterEvaluate hoặc evaluationDependsOn.

## 7. Truyền dữ liệu giữa projects: dùng variant, không dùng Project.tasks

Project dependency **implementation project(':core')** đủ để tiêu thụ **Java API**. Nhưng đôi khi consumer cần một **ZIP hướng dẫn, schema JSON, generated sources hoặc tài nguyên dữ liệu** từ producer.

Đoạn sau là **anti-pattern** trong :app:

~~~groovy
// Không dùng: truy cập task provider nội bộ của Project khác.
def zipPath = project(':core')
        .tasks.named('apiGuideZip')
        .get().archiveFile.get().asFile

tasks.register('copyGuide', Copy) {
    from(zipPath)
    into(layout.buildDirectory.dir('collected-guide'))
}
~~~

Nó có thể:
- Vi phạm Isolated Projects vì đọc :core.tasks.
- Realize producer task quá sớm.
- Làm app phụ thuộc task name và archive path nội bộ core.
- Chỉ truyền một File, không diễn đạt rõ artifact variant/producer contract.
- Dễ lỗi khi :core đổi output path hoặc task plugin.

**Cách đúng:** :core công bố **outgoing variant**, :app khai báo một **project dependency** với attributes phù hợp. Gradle tự đưa producer artifact vào task graph.

### 7.1. Phần nâng cao dành cho Gradle 9.9

Các factory APIs **configurations.consumable**, **dependencyScope** và **resolvable** được tài liệu Gradle hiện hành đánh dấu **incubating**. Dùng Gradle 9.9 cho đoạn sau và kiểm tra compatibility khi dùng bản cũ hơn.

Phần này **bổ sung vào dự án đang có** ở mục 6, không thay đổi settings.gradle hoặc convention plugin.

### 7.2. core/API-GUIDE.md

~~~markdown
# Core API Guide

The demo.core.Greetings class has two public methods:

- hello(name) returns a greeting for a nonblank recipient.
- twice(value) multiplies an integer by two with overflow checking.

This guide is published as a separate outgoing ZIP artifact.
~~~

Tệp nằm ở **core/API-GUIDE.md**. Nó không phải Java source, không được tự đưa vào binary JAR.

### 7.3. Bổ sung cuối core/build.gradle

Giữ nguyên plugins block. Thêm:

~~~groovy
// Producer sở hữu task và output.
def apiGuideZip = tasks.register('apiGuideZip', Zip) {
    archiveFileName.set('api-guide.zip')
    destinationDirectory.set(layout.buildDirectory.dir('guides'))
    from('API-GUIDE.md')
}

// Variant của producer được chọn bằng attribute khác biệt
// với standard Java JAR/classes variants.
configurations.consumable('apiGuideElements') {
    attributes {
        attribute(
            org.gradle.api.attributes.LibraryElements.LIBRARY_ELEMENTS_ATTRIBUTE,
            objects.named(
                org.gradle.api.attributes.LibraryElements,
                'api-guide-zip'
            )
        )
    }
}

artifacts {
    add('apiGuideElements', apiGuideZip)
}
~~~

**Giải thích:**
- tasks.register trả TaskProvider, không chạy ZIP lúc configuration.
- archiveFileName và destinationDirectory xác định **core/build/guides/api-guide.zip**.
- consumable configuration để **xuất artifact cho consumer**, không phải để core tự resolve.
- LibraryElements=api-guide-zip phân biệt ZIP tùy chỉnh với binary Java variants.
- artifacts.add(..., apiGuideZip) gắn artifact với producer TaskProvider; Gradle có thể suy ra task dependency khi consumer resolve.

### 7.4. Bổ sung cuối app/build.gradle

~~~groovy
// Configuration dùng để khai báo dependency; không resolve trực tiếp.
def guideRequests =
        configurations.dependencyScope('guideRequests').get()

// Configuration chỉ để resolve artifact phù hợp.
def guideFiles = configurations.resolvable('guideFiles') {
    extendsFrom guideRequests
    attributes {
        attribute(
            org.gradle.api.attributes.LibraryElements.LIBRARY_ELEMENTS_ATTRIBUTE,
            objects.named(
                org.gradle.api.attributes.LibraryElements,
                'api-guide-zip'
            )
        )
    }
}.get()

dependencies {
    add('guideRequests', project(':core'))
}

tasks.register('collectGuide', Copy) {
    from(guideFiles)
    into(layout.buildDirectory.dir('collected-guide'))
}
~~~

**Cơ chế:** app yêu cầu project :core qua dependency management, kèm attribute của variant ZIP. Gradle giải quyết **apiGuideElements** của core và xây producer artifact task trước khi Copy lấy file. App không chạm :core.tasks hoặc :core.layout.

**Lưu ý:** .get() trên configuration factory trong đoạn trên lấy **Configuration object của chính :app** để khai báo graph, không phải đọc TaskProvider of another Project. Không gọi Configuration.getFiles() ngay tại configuration time; resolution được trì hoãn tới thời điểm task cần files.

### 7.5. Chạy và kiểm tra

Linux/macOS:

~~~bash
./gradlew :app:collectGuide --console=plain
jar --list --file app/build/collected-guide/api-guide.zip
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :app:collectGuide --console=plain
jar --list --file app\build\collected-guide\api-guide.zip
~~~

ZIP entry cần có:

~~~text
API-GUIDE.md
~~~

Dùng Gradle reports:

~~~bash
./gradlew :core:outgoingVariants --variant apiGuideElements
./gradlew :app:resolvableConfigurations --configuration guideFiles
~~~

Quan sát producer attribute và consumer attribute cùng là **api-guide-zip**, và outgoing artifact gắn với apiGuideZip task.

### 7.6. Khi variant matching không tìm thấy artifact

Một consumer đòi LibraryElements=api-guide-zip nhưng producer không công bố variant tương thích sẽ gặp **variant selection/resolution error**, không nên âm thầm lấy JAR khác mục đích.

Kiểm tra:
- Task apiGuideZip có được đăng ký trong :core?
- Producer configuration có **canBeConsumed=true** không?
- artifacts.add có gắn đúng task provider?
- Producer/consumer attribute names, types, values có khớp?
- Consumer configuration có **canBeResolved=true** không?
- Project dependency tới đúng ':core'?
- Task Copy lấy FileCollection của guideFiles, không đọc một path string ngoài graph?

**Không dùng evaluationDependsOn(':core') làm cách sửa variant mismatch**.

## 8. dependsOn bằng task path: khi nào hợp lý?

Theo Gradle Isolated Projects documentation, **tham chiếu task object của project khác** không được phép:

~~~groovy
// Vi phạm: đọc :core.tasks.
tasks.register('qualityGate') {
    dependsOn(project(':core').tasks.named('check'))
}
~~~

Nhưng **task path string** có thể dùng cho **lifecycle aggregation**:

~~~groovy
tasks.register('qualityGate') {
    dependsOn(':core:check', tasks.named('check'))
}
~~~

Điều này chỉ yêu cầu :core:check và app:check cùng tham gia graph đúng dependency; task path được Gradle resolve mà không giao nội bộ Project object cho app.

**Phân biệt:**
- **Được phép dùng task path** khi chỉ cần schedule/orchestrate lifecycle tasks.
- **Không nên dùng task path một mình** khi consumer phải đọc output producer.
- **Không phải mọi cross-project dependency đều bị cấm**; Gradle cung cấp các dependency contracts chính thức.

### 8.1. dependsOn khác mustRunAfter và evaluationDependsOn

| API | Điều nó thực sự bảo đảm |
|---|---|
| dependsOn(':core:check') | Thêm task :core:check làm dependency được lên lịch |
| mustRunAfter(':core:check') | Chỉ ràng buộc thứ tự nếu cả hai tasks đã được lên lịch |
| shouldRunAfter(':core:check') | Ưu tiên thứ tự mềm khi có thể |
| finalizedBy(otherTask) | Đăng ký task finalizer theo lifecycle task |
| evaluationDependsOn(':core') | Yêu cầu **project evaluation** đi trước, không phải task execution |
| implementation project(':core') | Phụ thuộc vào Java component/variant của project :core |
| dependency tới outgoing variant | Phụ thuộc artifact producer cụ thể qua dependency resolution |

Không dùng mustRunAfter để kỳ vọng :core:jar chắc chắn chạy; không dùng evaluationDependsOn để kỳ vọng output file đã tồn tại. Nếu consumer thực sự cần producer file, **artifact dependency** mới là mối liên hệ đúng.

## 9. Provider và TaskProvider: tránh eager access

Một TaskProvider giữ reference tới task đăng ký lười. Trong **cùng project**:

~~~groovy
def generateDoc = tasks.register('generateDoc') {
    def output = layout.buildDirectory.file('generated/message.txt')
    outputs.file(output)

    doLast {
        def target = output.get().asFile
        target.parentFile.mkdirs()
        target.text = 'Hello from Gradle\n'
    }
}

tasks.register('collectDoc', Copy) {
    from(generateDoc)
    into(layout.buildDirectory.dir('collected'))
}
~~~

Đây là một **đoạn thực hành thay thế trong cùng project**, không phải phần bắt buộc của lab chính. Nó cho thấy:
- generateDoc là TaskProvider.
- File output được khai báo thay vì tự ghi vào một file vô danh.
- Copy.from(TaskProvider) nhận producer output/files và Gradle có thể suy ra dependency.
- Không đọc file đã generate ở configuration phase.
- Không lấy Project.tasks của project khác.

**Không nhầm:** doLast chỉ chạy trong execution phase; gọi TaskProvider.get() làm task realized nhưng không tự gọi doLast.

### 9.1. Mẫu eager nên tránh

~~~groovy
// Anti-pattern:
def taskInstance = tasks.getByName('generateDoc')
def filePath = tasks.named('generateDoc').get()
~~~

Cả hai đều có thể eager-realize task. Nếu chỉ cần dependsOn hoặc task output, giữ **TaskProvider** và dùng lazy properties.

### 9.2. tasks.withType.configureEach

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

Mọi JavaCompile task thuộc **project hiện tại** được cấu hình khi được realized. Không cần afterEvaluate để đợi plugins đăng ký tasks.

### 9.3. Khi plugin được áp muộn

~~~groovy
pluginManager.withPlugin('java') {
    tasks.named('compileJava', JavaCompile) {
        options.encoding = 'UTF-8'
    }
}
~~~

withPlugin phản ứng với Java Plugin, không tạo plugin. Nếu convention plugin cần Java model chắc chắn, áp **id 'java'** trước như lab, không cần callback.

### 9.4. Build script đọc generated file quá sớm

~~~groovy
// Anti-pattern: file có thể chưa tồn tại trong configuration phase.
def content = file('build/generated/data.txt').text
~~~

Dù bạn bọc dòng này bằng afterEvaluate, file generated vẫn có thể chưa tồn tại vì **task actions chưa chạy**. Đúng cách là task có @OutputFile/@OutputDirectory, consumer có @InputFile/@InputFiles và Provider-backed file property; khi qua projects, dùng dependency artifact contract.

## 10. Version và common properties không cần rootProject.ext

Một cấu hình cũ:

~~~groovy
// root/build.gradle
ext.javaLevel = 17

// :app/build.gradle — anti-pattern
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(rootProject.ext.javaLevel)
    }
}
~~~

:app đang đọc extra properties của root Project (mutable state). Thay bằng một Gradle property trong **root gradle.properties**:

~~~properties
javaLevel=17
~~~

và từ **project hiện tại** hoặc convention plugin:

~~~groovy
def javaLevel = providers.gradleProperty('javaLevel')
        .map { Integer.parseInt(it) }

java {
    toolchain {
        languageVersion = javaLevel.map {
            JavaLanguageVersion.of(it)
        }
    }
}
~~~

Đây là **phương án thay thế** cho config Java 17 hardcoded trong lab, không cần chèn đồng thời.

**Ý nghĩa:**
- providers thuộc target project.
- Value đi vào Java extension qua Provider.
- Không tham chiếu rootProject.ext/otherProject.extensions.
- Dễ override bằng property/env/CI policy đúng phạm vi.
- Không ép evaluation order.

**Không đồng nhất Project.version với root Gradle property:** một plugin có thể set Project.version của chính project đó từ providers.gradleProperty('releaseVersion'), như lab. Đọc rootProject.version từ child là trường hợp khác về ownership.

## 11. Isolated Projects: điều gì bị giới hạn?

Theo Gradle 9.9, **Isolated Projects là tính năng incubating** (được thăng từ experimental lên incubating trong Gradle 9.7). Nó nhằm cho phép các projects được cấu hình song song, độc lập với mutable state của projects khác.

Bật thử nếu Gradle Wrapper hỗ trợ:

~~~bash
./gradlew :app:run --isolated-projects
~~~

hoặc trong gradle.properties:

~~~properties
org.gradle.isolated-projects=true
~~~

**Không bắt buộc bật trong mọi production build ngay**, vì tính năng còn incubating và plugin ecosystem có thể cần migration.

### 11.1. Những truy cập cross-project mutable state không được phép

Trong :app configuration logic, các truy cập sau là vấn đề:

- project(':core').tasks.
- project(':core').extensions.
- project(':core').configurations.
- project(':core').plugins.
- project(':core').repositories.
- project(':core').layout hoặc providers.
- rootProject.version.
- rootProject.group.
- rootProject.ext.
- project(':core').buildDir.

Đó là **mutable state** của project khác. Isolated Projects có thể phát hiện violation ngay cả khi code **chỉ đọc** chứ không sửa.

Ví dụ:

~~~groovy
// :app/build.gradle — Isolated Projects violation.
def sharedVersion = rootProject.version
~~~

Lỗi có thể nêu project :app không được truy cập Project.version trên project ':'.

### 11.2. Thông tin bất biến được phép nhưng nên hạn chế

Một số metadata được thiết lập trong settings rồi bất biến:
- name, displayName, path, buildTreePath, depth.
- projectDir, buildFile, rootDir.
- Cấu trúc cây projects ở mức thông tin immutable.

**Không suy rằng mọi getter của Project đều không hợp lệ.** Gradle có API **IsolatedProject** (qua project.isolated) chỉ expose những dữ liệu an toàn khi phải đọc project identity từ ngoài.

Ngược lại **version/group/buildDir/layout** thuộc mutable state; chúng không được tự coi là immutable chỉ vì người viết hiếm khi thay đổi.

### 11.3. Task paths và project dependencies là những contract được hỗ trợ

- dependsOn(':core:check') là task path declaration.
- implementation project(':core') là project dependency declaration.
- Outgoing variant là artifact producer contract.

Chúng không yêu cầu app trực tiếp đọc/mutate :core.tasks hoặc :core.extensions.

### 11.4. Các giới hạn hiện hành

Gradle Isolated Projects hiện hành:
- Có thể cấu hình projects song song, theo parent/child constraints.
- **Tất cả projects vẫn được cấu hình**, không chỉ projects nằm trên task dependency path.
- Configuration on Demand bị bỏ qua khi Isolated Projects bật.
- Parallelism điều chỉnh bởi org.gradle.workers.max.
- Có thêm memory trade-offs và một số giới hạn về plugin resolution/lifecycle callbacks.
- Violations thường được báo theo cơ chế Configuration Cache problems.

Đừng nói Isolated Projects tự động “không cấu hình project không dùng đến” trong Gradle 9.9; đây là hiểu nhầm với Configuration on Demand.

## 12. Configuration Cache, Isolated Projects và --parallel khác nhau

| Cơ chế | Mục tiêu | Có tự sửa cross-project coupling không? |
|---|---|---|
| **Configuration Cache** | Tái sử dụng kết quả configuration và task graph trong invocation tiếp theo | Không; có rules riêng về task state và model |
| **Isolated Projects** | Ràng buộc project state isolation, hỗ trợ parallel configuration | Phát hiện/loại các kiểu cross-project mutable access không an toàn |
| **--parallel** | Tận dụng concurrent task execution khi graph cho phép | Không; task dependencies/outputs phải đúng |
| **Configuration on Demand** | Giảm số projects phải cấu hình theo requested tasks | Bị cross-project coupling hạn chế; bị bỏ qua khi Isolated Projects bật ở Gradle 9.9 |

Thử riêng từng mode:

~~~bash
./gradlew :app:run --console=plain
./gradlew :app:run --configuration-cache --console=plain
./gradlew :app:run --isolated-projects --console=plain
./gradlew :app:run --parallel --console=plain
~~~

**Một build có thể PASS Configuration Cache nhưng FAIL Isolated Projects**, vì hai cơ chế kiểm soát vấn đề khác nhau. Ngược lại, build không đọc mutable Project state của project khác vẫn có thể có task action vi phạm Configuration Cache do giữ Project reference.

### 12.1. Đừng capture Project trong task actions

~~~groovy
// Anti-pattern đối với Configuration Cache.
tasks.register('printVersionBad') {
    doLast {
        println project.version
    }
}
~~~

Đây là một task action dùng Project reference trong execution phase. Đối với task type nghiêm túc, nên khai báo input:

~~~java
import org.gradle.api.DefaultTask;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.TaskAction;

public abstract class PrintVersionTask extends DefaultTask {
    @Input
    public abstract Property<String> getReleaseVersion();

    @TaskAction
    public void printVersion() {
        getLogger().quiet("release=" + getReleaseVersion().get());
    }
}
~~~

**Snippet Java trên là custom Gradle task class**, phải được biên dịch trong build-logic/buildSrc hoặc plugin project; **không** đặt thẳng vào app/src/main/java rồi mong Gradle tự nhận nó là task.

Trong project đã có class này trên build logic classpath:

~~~groovy
tasks.register('printRelease', PrintVersionTask) {
    releaseVersion.set(providers.gradleProperty('releaseVersion'))
}
~~~

Với releaseVersion=1.0.0, task action in:

~~~text
release=1.0.0
~~~

Task dùng managed Property và @Input, không cần đọc Project object trong @TaskAction. Điều này phục vụ Configuration Cache và task input modeling, **không phải cùng một vấn đề** với cross-project tasks access.

## 13. Migration map cho những anti-pattern thường gặp

| Anti-pattern hiện tại | Phân tích rủi ro | Thay thế |
|---|---|---|
| afterEvaluate { tasks.getByName('compileJava') ... } | Eager task realization và phụ thuộc lifecycle | pluginManager.withPlugin + tasks.named |
| tasks.create('generateSpec') | Eager task creation | tasks.register |
| tasks.all { ... } | Eager configuration | tasks.configureEach |
| tasks.withType(JavaCompile) { ... } | Eager configure matching tasks | tasks.withType(JavaCompile).configureEach |
| evaluationDependsOn(':core') | Configuration-order coupling | Project dependency/artifact contract |
| project(':core').tasks.named('jar') | Cross-project mutable state | project dependency / outgoing variant |
| rootProject.ext.sharedValue | Cross-project mutable extra property | providers.gradleProperty của target |
| rootProject.version | Cross-project mutable state | Set version từ project property qua convention |
| root subprojects { apply plugin: ... } | Root inject configuration ngầm | Convention plugin mỗi module tự áp |
| dependsOn(':core:generate') + hardcoded output | Task order không mô hình hóa artifact | Outgoing artifact dependency |
| mustRunAfter(':core:generate') rồi đọc file | Không tạo task dependency | dependsOn hoặc data dependency phù hợp |
| Read generated file khi configuration | File chưa được tạo | Provider/managed input-output task properties |
| Build logic giữ Project trong doLast | Configuration Cache problem | Task type @Input/@Output, injected services |
| gradle.projectsEvaluated { inspect others } | Global mutable model coupling | Aggregation qua public variants/artifacts |
| Plugin phụ thuộc thứ tự apply | Task/extension có thể chưa tồn tại | withPlugin/withId, plugin composition |

**Không phải mọi API trong cột đầu đều bị Gradle cấm tuyệt đối ở mọi mode.** Bảng hướng tới thiết kế ít coupling và tương thích tốt hơn với các cơ chế tối ưu hiện hành.

## 14. Quy trình migration có thể kiểm chứng

### Bước 1 — Ghi nhận trạng thái đang chạy đúng

Trước khi sửa build lớn, lưu:
- Gradle Wrapper version/JDK/toolchain.
- Task graph và project dependencies.
- Test outcomes và những quality gates.
- Artifact outputs, Java stdout và packaging.
- Configuration time/Task realization profile khi cần đo hiệu năng.

Ví dụ:

~~~bash
./gradlew :app:run --console=plain
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :core:outgoingVariants
~~~

### Bước 2 — Tìm các dấu hiệu coupling

Tìm trong build.gradle, build logic hoặc plugins:
- afterEvaluate / beforeEvaluate / projectsEvaluated.
- evaluationDependsOn / evaluationDependsOnChildren.
- rootProject.ext/version, project(':x').tasks/configurations/extensions.
- subprojects/allprojects blocks.
- getByName, TaskProvider.get, tasks.create.
- Hardcoded ../other/build/... file paths.
- Task actions truy cập project hoặc gradle global state.

Danh sách chỉ để **review**, không tự đánh dấu mọi occurrence là lỗi nếu chưa xem ngữ cảnh.

### Bước 3 — Tách shared conventions

Tạo build-logic convention plugins cho:
- Java toolchain, compilation flags.
- Testing/quality.
- Publishing/release.
- Module-specific custom tasks.

Để mỗi subproject apply plugins đúng vai trò. Gỡ root injection sau khi xác nhận không module nào mất cấu hình.

### Bước 4 — Tách cross-project data flows

Với mỗi dòng đọc state của project khác:
- Java API/bytecode → **implementation project(':producer')**.
- Schema/generated files → **outgoing variant/artifact**.
- Shared settings → **Gradle property/Provider** ở target.
- Lifecycle fan-out → **task path string** hoặc aggregation plugin.
- Plugin ordering → **pluginManager.withPlugin**.

### Bước 5 — Bỏ afterEvaluate và eager APIs

Thay:
- afterEvaluate bằng lazy task configuration/plugin callbacks.
- tasks.create bằng tasks.register.
- tasks.getByName bằng tasks.named.
- withType closure eager bằng configureEach.
- evaluationDependsOn bằng dependency/variant relationships.

### Bước 6 — Kiểm tra qua nhiều execution modes

~~~bash
./gradlew :app:run --console=plain
./gradlew :app:run --configuration-cache --console=plain
./gradlew :app:run --isolated-projects --console=plain
./gradlew :app:run --parallel --console=plain
~~~

Đọc các violations cụ thể; không coi một mode PASS là mọi tối ưu khác đều PASS. Nếu plugin chưa hỗ trợ Isolated Projects đang incubating, ghi lại compatibility gap và xử lý theo upstream/upgrade roadmap.

### Bước 7 — Kiểm tra correctness trước performance

- Java app stdout có còn chính xác không?
- Artifacts và metadata/variants có đủ không?
- Tests được chạy theo yêu cầu hay chỉ UP-TO-DATE/FROM-CACHE?
- Các task input/output dependencies còn đúng không?
- Chạy trên clean CI workspace có pass không?
- Parallel build có race/shared output folder không?
- Có thêm eager task realization hay config time regression không?

**Không tối ưu bằng cách xóa task dependencies hoặc thay bằng thứ tự ngầm.** Build nhanh mà có stale outputs là build không đúng.

## 15. Troubleshooting theo triệu chứng

### Lỗi 1 — Project ':app' cannot access Project.version on another project ':'

**Nguyên nhân:** :app đọc rootProject.version, mutable state của project khác khi Isolated Projects bật.

**Cách sửa:** Đưa version vào Gradle property và set trên project hiện tại qua convention plugin; không dùng evaluationDependsOn(':') để né lỗi.

### Lỗi 2 — Cannot access Project.tasks on another project

**Nguyên nhân:** :app gọi project(':core').tasks hoặc root truy cập tasks của child.

**Cách sửa:** Dùng implementation project(':core') để tiêu thụ Java component; outgoing variant để truyền artifact; string task path cho lifecycle aggregator.

### Lỗi 3 — Task named compileJava not found

**Nguyên nhân:** Java Plugin chưa áp trong project có task đó, tên task khác hoặc logic bị đặt ở project sai.

**Cách sửa:** Áp đúng plugin, dùng pluginManager.withPlugin('java') và tasks.named trong project ấy; kiểm tra :project:tasks --all. Không thêm afterEvaluate mù quáng.

### Lỗi 4 — Cannot call Project.afterEvaluate because project already evaluated

**Nguyên nhân:** Callback được đăng ký quá trễ, thường khi lazy task configure action mới chạy.

**Cách sửa:** Chuyển logic sang Provider/TaskProvider/plugin callbacks; không eager-realize mọi task để lách lifecycle.

### Lỗi 5 — project(':core').version khác kỳ vọng sau migration

**Nguyên nhân:** Project.version của :core chỉ được set trong chính project/convention; root.version không còn là nguồn bị đọc trực tiếp.

**Cách sửa:** Mỗi project dùng chung releaseVersion Gradle property hoặc một quy tắc versioning có ownership rõ, tránh rootProject.version access.

### Lỗi 6 — app không dùng implementation mới của core

**Nguyên nhân có thể:** Runtime classpath dùng JAR đã publish cũ, duplicate class names hoặc dependency không phải project(':core').

**Cách sửa:** Kiểm tra :app:dependencies --configuration runtimeClasspath, selected variant, actual classes/JAR. Không chữa bằng evaluationDependsOn.

### Lỗi 7 — --parallel gây lỗi file chưa sinh

**Nguyên nhân:** Task consumer đọc output producer bằng đường dẫn cứng; không khai báo data dependency, hoặc tasks ghi cùng output folder.

**Cách sửa:** Producer có output property, consumer resolve artifact/provider; mỗi task giữ output riêng, Gradle biết dependency graph.

### Lỗi 8 — Copy task phụ thuộc :core:apiGuideZip nhưng thiếu artifact

**Nguyên nhân:** Chỉ có dependsOn path, còn đường dẫn file sai/không thuộc đúng producer output.

**Cách sửa:** Expose ZIP qua consumable variant và resolve bằng configuration; không hardcode ../core/build/guides path trong consumer.

### Lỗi 9 — No matching variant of project ':core' was found

**Nguyên nhân:** Consumer yêu cầu attribute api-guide-zip nhưng producer chưa expose configuration phù hợp, configuration không consumable hoặc attributes/types khác nhau.

**Cách sửa:** Xem :core:outgoingVariants và :app:resolvableConfigurations; kiểm tra artifact, LibraryElements attribute, producer/consumer roles và project dependency.

### Lỗi 10 — build-logic plugin ID không tìm thấy

**Nguyên nhân:** Thiếu pluginManagement.includeBuild('build-logic'), thiếu groovy-gradle-plugin hoặc file đặt sai src/main/groovy và ID không khớp.

**Cách sửa:** Kiểm tra bốn file settings/build-logic/convention script và plugins block của subproject; không thêm unrelated Maven repositories để tìm plugin local.

### Lỗi 11 — Chỉ chạy :app:compileJava mà build còn cấu hình nhiều projects

**Nguyên nhân:** Multi-project build và active Gradle mode có thể cấu hình nhiều projects. Isolated Projects 9.9 hiện vẫn cấu hình tất cả projects.

**Cách sửa:** Đo config overhead, modularize shared logic, giảm eager operations; không giả định Configuration on Demand khi Isolated Projects bật.

### Lỗi 12 — Configuration Cache fail dù không truy cập Project khác

**Nguyên nhân:** Task action giữ Project/Gradle/Settings references hoặc unsupported state, khác với cross-project mutable access.

**Cách sửa:** Custom task type với managed inputs/outputs và injected services; xem configuration cache report.

### Lỗi 13 — :core:jar không chạy khi app compile

**Giải thích:** Gradle có thể dùng classes output variant thay vì JAR cho Java compile. Đây có thể là tối ưu bình thường.

**Cách xử lý:** Xem :core:outgoingVariants và :app:compileClasspath; không thêm dependsOn(':core:jar') chỉ để làm log giống mong đợi.

### Lỗi 14 — Root subprojects {} gây plugin áp cả module không cần Java

**Nguyên nhân:** Root inject common configuration vào mọi child, không theo role.

**Cách sửa:** Convention plugins theo module role, từng child tự áp.

### Lỗi 15 — mustRunAfter không khiến task kia chạy

**Nguyên nhân:** Ordering rule không tạo dependency.

**Cách sửa:** dependsOn nếu cần lifecycle task, dependency/variant nếu cần sản phẩm của task.

### Lỗi 16 — TaskProvider.get() làm chậm configuration

**Nguyên nhân:** Task realized khi không cần; getByName, tasks.all, withType closure eager có thể gây cascade.

**Cách sửa:** tasks.register, tasks.named, configureEach; giữ Provider tới khi có task cần thực sự dùng giá trị.

### Lỗi 17 — afterEvaluate set toolchain nhưng plugin khác ghi đè

**Nguyên nhân:** Nhiều callbacks/plugins set cùng property theo các thứ tự không hiển nhiên; afterEvaluate không phải bảo đảm precedence toàn cục.

**Cách sửa:** Định nghĩa ownership qua convention/plugin APIs, dùng convention thay vì ép set ở nhiều nơi và cấu hình đúng lifecycle của plugin.

### Lỗi 18 — Đổi thứ tự include thì build đổi kết quả

**Nguyên nhân:** Build đang phụ thuộc thứ tự configuration/injection hoặc global mutable state.

**Cách sửa:** Audit cross-project references, thay bằng dependencies và plugin conventions; tests chạy trên nhiều mode để phát hiện implicit order.

### Lỗi 19 — Biến Gradle property không được đọc trong included build

**Nguyên nhân:** Included build có settings/Gradle property context riêng. Đọc value ở thời điểm/đối tượng không đúng.

**Cách sửa:** Trong convention plugin đã **được apply vào target project**, dùng target providers.gradleProperty; còn cấu hình của chính build-logic/settings.gradle phải có input của included build riêng khi cần.

### Lỗi 20 — --dry-run hiển thị task graph nhưng không có Java stdout

**Nguyên nhân:** --dry-run không thực thi tasks.

**Cách sửa:** Chạy :app:run thật và xác minh stdout; task outcomes UP-TO-DATE/FROM-CACHE/executed cũng cần được đọc chính xác.

## 16. Checklist review multi-project build

1. Đã phân định rõ project owners và public artifacts/variants?
2. settings.gradle chỉ include projects và included builds thật sự cần?
3. Mỗi module tự apply đúng plugins theo vai trò?
4. Có convention plugins cho Java toolchain/quality/build policies?
5. Có code trong :app đọc rootProject.version/ext hoặc :core.tasks không?
6. Có subprojects/allprojects blocks chỉ để inject task/plugin config không?
7. Có afterEvaluate chỉ để đợi plugin/task xuất hiện không?
8. Có evaluationDependsOn chỉ để đọc property/artifact của project khác không?
9. Cross-project Java API dùng implementation/api project dependency?
10. Custom file sharing dùng outgoing variants/attributes?
11. Consumer không hardcode producer build/ paths?
12. Task producers khai báo outputs, consumers khai báo inputs?
13. TaskProviders được giữ lazy, tránh .get() eager không cần?
14. tasks.withType dùng configureEach thay vì eager closure?
15. withPlugin/withId gắn callback vào plugin lifecycle đúng project?
16. Task lifecycle orchestration dùng task paths, không đọc task objects cross-project?
17. Shared version/settings được project tự đọc từ Gradle properties/Provider?
18. Task actions không capture Project references khi nhắm Configuration Cache?
19. Đã kiểm tra outgoingVariants/resolvableConfigurations/compileClasspath?
20. Đã chạy --configuration-cache, --isolated-projects (nếu version hỗ trợ) và --parallel để phát hiện vấn đề?
21. Đã kiểm tra test/CI gates và Java outputs sau migration?
22. Có tài liệu giải thích ownership và đường dữ liệu giữa projects không?

## 17. Bài tập thực hành

**Bài 1.** afterEvaluate chạy sau khi project được đánh giá hay sau khi tất cả tasks đã thực thi? Nó có tự đợi tất cả subprojects hoàn thành không?

**Bài 2.** Trong :app, implementation project(':core') có phải đọc trực tiếp :core.tasks không?

**Bài 3.** Vì sao gọi project(':core').tasks.named('jar').get() nguy hiểm với Isolated Projects?

**Bài 4.** Cấu hình UTF-8 cho mọi JavaCompile trong project nên dùng API nào thay afterEvaluate?

**Bài 5.** tasks.register tạo TaskProvider hay lập tức chạy doLast?

**Bài 6.** Vì sao root subprojects { apply plugin: 'java' } kém minh bạch hơn convention plugin được từng module tự áp?

**Bài 7.** App cần Java API từ core, có cần dependsOn(':core:jar') không?

**Bài 8.** App cần ZIP output từ core, nhưng không được đọc core.tasks. Có những bước producer/consumer nào?

**Bài 9.** evaluationDependsOn(':core') có thay thế dependency giữa core:compileJava và app:compileJava không?

**Bài 10.** RootProject.version và rootProject.path có cùng quy tắc trong Isolated Projects không?

**Bài 11.** pluginManager.withPlugin('java') khác việc apply plugin: 'java' ra sao?

**Bài 12.** Configuration Cache và Isolated Projects có phải một tính năng không?

**Bài 13.** Isolated Projects trong Gradle 9.9 có tự skip cấu hình các projects không nằm trong task graph không?

**Bài 14.** dependsOn(':core:check') có được phép trong Isolated Projects không, và khi nào nó chưa đủ?

**Bài 15.** Vì sao mustRunAfter không bảo đảm producer task thực sự chạy?

**Bài 16.** Nếu app phải copy artifact api-guide.zip, vì sao cần outgoing variant và resolvable configuration?

**Bài 17.** canBeConsumed, canBeResolved và dependencyScope ứng với những vai trò nào?

**Bài 18.** Nếu consumer request LibraryElements=api-guide-zip nhưng producer chỉ expose JAR, kết quả phù hợp là gì?

**Bài 19.** Vì sao TaskProvider.get() quá sớm làm mất lợi ích configuration avoidance?

**Bài 20.** Khi version nằm trong gradle.properties của main build, convention plugin áp vào app có thể lấy version bằng API nào không cần rootProject.version?

**Bài 21.** Nếu code task doLast dùng project.version và Configuration Cache báo lỗi, nên thiết kế custom task type thế nào?

**Bài 22.** Nêu ba bước migration quan trọng nhất khi một build có afterEvaluate/evaluationDependsOn và root subprojects configuration.

### Gợi ý đáp án

1. **Sau evaluation của chính project**, trong configuration phase; không chờ mọi subprojects hoặc task execution.
2. **Không.** Đây là project dependency declaration chính thức của Gradle.
3. Truy cập mutable tasks container của project khác, và get() còn eager-realize task.
4. **tasks.withType(JavaCompile).configureEach**, đặt ở project hoặc convention plugin.
5. register trả **TaskProvider**; doLast chỉ chạy trong execution phase khi task thực sự thực thi.
6. Root injection ẩn cấu hình, gây coupling; conventions diễn đạt ownership/opt-in rõ.
7. **Không.** implementation project(':core') để Gradle chọn đúng variant và producer outputs.
8. Core tạo TaskProvider artifact và consumable variant; app khai báo dependency + resolvable configuration chọn attribute phù hợp rồi Copy.from(FileCollection).
9. **Không.** evaluationDependsOn chỉ tác động evaluation order.
10. **Không.** version mutable; path là immutable identity và thường được phép.
11. withPlugin phản ứng khi plugin được áp; apply plugin chủ động áp.
12. **Không.** Configuration Cache cache configuration/task graph; Isolated Projects hạn chế cross-project mutable state và hỗ trợ parallel config.
13. **Không trong Gradle 9.9**; tất cả projects vẫn được cấu hình, Configuration on Demand bị bỏ qua.
14. **Có**, để lên lịch lifecycle task theo path; không đủ khi thực sự cần data artifact.
15. mustRunAfter chỉ thứ tự **nếu cả hai task đã nằm trong graph**, không tạo dependency.
16. Artifact contract cho phép Gradle chọn/producer đúng ZIP, tránh hardcoded path và cross-project state.
17. Producer expose qua consumable; consumer resolve qua resolvable; dependencies được khai báo qua dependencyScope khi dùng role-based factories.
18. Variant resolution **không tìm được artifact tương thích** (thường báo lỗi) chứ không được tự chọn JAR khác mục đích.
19. .get() khiến task được realized, tăng cấu hình không cần thiết.
20. **providers.gradleProperty('releaseVersion')** trên target project.
21. Managed task @Input Property<String>, set từ Provider ở configuration, task action chỉ dùng property.get() và Logger.
22. Ghi baseline, thay root injection bằng convention plugins, thay cross-project state access bằng project dependencies/outgoing variants rồi test configuration modes.

## Tài liệu tham khảo chính thức

- [Gradle User Manual — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): initialization, configuration, execution và afterEvaluate.
- [Gradle User Manual — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): project structure và task/project dependency model.
- [Gradle User Manual — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): tasks.register, tasks.named, configureEach và afterEvaluate pitfalls.
- [Gradle User Manual — Isolated Projects](https://docs.gradle.org/current/userguide/isolated_projects.html): mutable Project state constraints, task path exceptions và Gradle 9.9 limitations.
- [Gradle User Manual — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration state reuse.
- [Gradle User Manual — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): task state/captured Project references.
- [Gradle User Manual — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): included build build-logic và convention plugin guidance.
- [Gradle User Manual — Sharing Build Logic Between Subprojects](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): vì sao tránh allprojects/subprojects injection.
- [Gradle User Manual — Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html): precompiled script plugins theo module.
- [Gradle User Manual — Groovy Gradle Plugin](https://docs.gradle.org/current/userguide/groovy_gradle_plugin.html): cách tạo convention plugins Groovy DSL.
- [Gradle User Manual — How to Share Outputs Between Projects](https://docs.gradle.org/current/userguide/how_to_share_outputs_between_projects.html): producer/consumer configurations, variant-aware artifacts.
- [Gradle User Manual — Variant-Aware Resolution](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): matching attributes và diagnostics outgoingVariants.
- [Gradle User Manual — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): consumable/dependencyScope/resolvable roles.
- [Gradle User Manual — Configuration on Demand](https://docs.gradle.org/current/userguide/configuration_on_demand.html): decoupled projects và limitations.
- [Gradle API — Project](https://docs.gradle.org/current/javadoc/org/gradle/api/Project.html): afterEvaluate và evaluationDependsOn semantics.

**Ghi nhớ:** **afterEvaluate** chỉ báo project đã được đánh giá, không giải quyết producer/consumer dependencies. **evaluationDependsOn** chỉ ép evaluation order, không hợp thức hóa truy cập mutable state cross-project. **Root allprojects/subprojects injection** nên thay bằng **convention plugins** từng module tự áp. Khi dùng API của module khác, hãy khai báo **project dependency**; khi cần file custom, hãy publish **outgoing variant** và resolve trong consumer. TaskProvider/Provider giúp cấu hình lười; Isolated Projects hỗ trợ phát hiện state coupling. Kiểm tra task graph, dependency variants, Java runtime outputs và từng mode tối ưu sau migration.