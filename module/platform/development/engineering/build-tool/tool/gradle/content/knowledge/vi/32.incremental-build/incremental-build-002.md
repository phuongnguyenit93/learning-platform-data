# Phân biệt task không cần chạy với kết quả lấy từ build cache trong Gradle

## 1. Bối cảnh và mục tiêu học tập

Trong một dự án Java có hàng trăm Gradle tasks, câu hỏi “tại sao task không chạy?” có nhiều đáp án. Hai kết quả đặc biệt dễ bị nhầm:

- **UP-TO-DATE** — Gradle có bằng chứng rằng đầu vào và đầu ra của task **vẫn hợp lệ tại workspace này** so với execution history đã lưu; không cần chạy action.
- **FROM-CACHE** — Gradle nhận ra một task cần kết quả nhưng **tìm được output tương đương trong build cache**, rồi khôi phục output thay vì chạy action.

Cả hai tiết kiệm thời gian, song **UP-TO-DATE không phải một cache hit**. Build cache còn có thể cung cấp kết quả từ workspace, branch hoặc CI agent khác; up-to-date check thường dựa trên trạng thái đang có trong workspace hiện tại. Phân biệt sai sẽ dẫn đến phân tích performance sai, cấu hình remote cache không cần thiết hoặc đánh giá thiếu chính xác mức độ kiểm thử trên CI.

Bài thuộc nhóm **Build tăng dần** của **Build Tool Gradle**, trực tiếp trả lời đề bài **“Phân biệt task không cần chạy với kết quả lấy từ build cache”**.

Sau bài này, bạn có thể:

1. Giải thích task selection, inputs/outputs, execution history, fingerprints và build cache key.
2. Phân biệt **UP-TO-DATE**, **FROM-CACHE**, **NO-SOURCE**, **SKIPPED**, **FAILED**, task chạy thật và task không có trong graph.
3. Hiểu tại sao tắt build cache vẫn nhận UP-TO-DATE.
4. Hiểu tại sao clean rồi chạy lại vẫn có thể FROM-CACHE.
5. Dùng chính xác **--build-cache**, **--no-build-cache**, **--rerun-tasks**, **--info** và **--console=plain**.
6. Tạo **Java 17 custom @CacheableTask** với @Input, @InputFile, @OutputFile và PathSensitivity.
7. Thực hành chuỗi EXECUTED → UP-TO-DATE → FROM-CACHE, đổi input gây cache miss rồi quay về một cache entry cũ.
8. Phân biệt Gradle task output cache, dependency cache, configuration cache và incremental compilation bên trong task.
9. Nhận diện undeclared inputs, nondeterminism, absolute paths, non-cacheable tasks, security threats và remote-cache misses.
10. Thiết kế quy trình CI tận dụng cache nhưng không làm sai correctness hoặc che test failures.

## 2. Sơ đồ quyết định ở mức khái niệm

~~~text
Yêu cầu: ./gradlew generateGreeting --build-cache
                      |
                      v
              Task có được chọn?
                  /       \
                Không     Có
                 |         |
          Không có outcome v
                    Có điều kiện skip/no source?
                         /          \
                       Có            Không
                        |              |
                  SKIPPED hoặc         v
                   NO-SOURCE    Inputs/outputs tại
                                workspace vẫn đúng?
                                   /       \
                                 Có         Không
                                  |           |
                             UP-TO-DATE       v
                                       Cache được bật?
                                       Task cacheable?
                                            |
                                       Có cache hit?
                                         /      \
                                       Có       Không
                                        |         |
                                    FROM-CACHE   Task chạy
                                    restore      actions
                                    outputs      có thể store
~~~

Sơ đồ là mô hình học tập, không phải bảo đảm thứ tự nội bộ của mọi plugin. Task còn có điều kiện onlyIf, enabled, source filtering, custom up-to-date predicates, validation rules và task-type behavior riêng.

### 2.1. Task chưa được chọn không có outcome

Nếu người dùng yêu cầu **:compileJava**, task **:test** có thể không nằm trong graph. Không thể nói “test UP-TO-DATE” chỉ vì lần build đó không hiển thị **:test**. **Task avoidance/selection** diễn ra trước vấn đề output có được tái sử dụng hay không.

### 2.2. UP-TO-DATE không lấy một bản output mới từ cache

Nếu kết quả hiện tại đã đủ, Gradle skip action. Một task nhận UP-TO-DATE **không chứng minh** cache đã bật, có cache entry hay đã tải tệp từ server.

### 2.3. FROM-CACHE phải có output được khôi phục

Khi task hợp lệ để caching, build cache được bật và key trùng, Gradle có thể phục hồi outputs. Trong trường hợp đó action không chạy, nên những side effects không nằm trong declared outputs cũng **không được thực hiện**.

## 3. Bảng phân biệt mọi trạng thái thường gặp

| Outcome/hiển thị | Task action chạy? | Ý nghĩa | Có chứng minh build-cache hit? |
| --- | --- | --- | --- |
| **UP-TO-DATE** | Không | Outputs hiện có hợp lệ với execution history và inputs | **Không** |
| **FROM-CACHE** | Không | Outputs được restore từ local/remote build cache | **Có** |
| **NO-SOURCE** | Không | Không có source files phù hợp để xử lý | Không |
| **SKIPPED** | Không | Bị bỏ qua theo onlyIf, enabled hoặc điều kiện tương tự | Không |
| **> Task :compileJava** không suffix | Thường có | Task actions thực thi | Không |
| **FAILED** | Có lỗi trong task/build | Task không hoàn tất thành công | Không |
| Task không xuất hiện | Không được chọn trong invocation | Không có outcome để đánh giá | Không |
| **UP-TO-DATE** của task lifecycle không có actions | Không có action hữu ích | Không tự chứng minh binary/test được tạo mới | Không |

**Không có suffix** vẫn có thể là task được thực thi *incrementally bên trong*, chứ không phải nhất thiết xử lý lại tất cả input files.

### 3.1. Những kết luận sai

Sai: “compileJava UP-TO-DATE là do Gradle lấy class từ cache.”

Đúng: Các compiled class outputs tại workspace vẫn hợp lệ; không cần restore.

Sai: “test FROM-CACHE nghĩa là tests vừa chạy thành công trên runner này.”

Đúng: Outputs của lần test phù hợp trước đó được khôi phục. Tùy release policy, team có thể cần một job chạy tests thật.

Sai: “build success là tất cả tests đã được thực thi.”

Đúng: Một số tasks có thể NO-SOURCE, SKIPPED, UP-TO-DATE hoặc FROM-CACHE. Phải kiểm tra đúng task outcomes và JUnit XML counts.

## 4. Task inputs, outputs và snapshots

Gradle tối ưu task execution nhờ **mô hình inputs/outputs**.

Ví dụ JavaCompile:

~~~text
Inputs:
  src/main/java/**/*.java
  Java toolchain / compiler options
  compileClasspath
  annotation processor setup
  implementation của task

Task action:
  gọi compiler / incremental compiler

Outputs:
  build/classes/java/main/**/*.class
~~~

Một lần task chạy thành công, Gradle có thể ghi fingerprints của inputs và outputs. Ở invocation sau, Gradle so sánh các fingerprints/state với history đã lưu. Nếu không có thay đổi liên quan, Gradle đánh dấu UP-TO-DATE và không chạy actions.

### 4.1. Input fingerprint gồm những gì?

Tùy task, fingerprint có thể liên quan:

- File contents/hash.
- Normalized file paths.
- Thứ tự classpath nếu thứ tự có ý nghĩa.
- Scalar parameters và property values.
- Compiler flags, Java version, toolchain, locale/encoding khi chúng tác động output.
- Task implementation/action implementation.
- Các input values được khai báo qua annotations hoặc TaskInputs DSL.

Không được quên một biến môi trường, file cấu hình hay tham số **thực sự ảnh hưởng đầu ra** rồi kỳ vọng Gradle tự biết.

### 4.2. Output fingerprint gồm những gì?

Gradle biết các file/directory được khai báo là outputs, nên có thể phát hiện outputs bị mất hoặc thay đổi. Ví dụ compileJava sẽ cần xây lại outputs nếu các class files bị xóa; nếu cache có entry phù hợp, có thể restore thay vì compile.

Một task tự ghi vào **src/** hoặc một thư mục chung nhưng không khai báo output có thể phá khả năng theo dõi. Nên dùng output directory riêng dưới **build/** và nối task producers/consumers bằng Provider APIs.

### 4.3. Task không có output

Một custom doLast task chỉ in log hoặc gọi API mà không khai báo output không thể sử dụng file up-to-date checking như một compiler task. Một số task lifecycle không có actions lại có thể hiện UP-TO-DATE vì không có hành động phải làm; đừng kết luận mọi task không khai báo outputs có chung một outcome.

### 4.4. Incremental không đồng nghĩa cache

**Incremental build** giúp tránh làm lại những task có inputs/outputs không đổi và cũng có thể giúp task chạy xử lý một phần thay đổi. **Task output caching** giúp reuse kết quả hoàn chỉnh của một task execution từ cache key khớp. Hai cơ chế bổ trợ nhau, không phải một.

## 5. Build cache key là gì?

Gradle tính cache key để định danh một bộ kết quả task theo những điều kiện đầu vào.

Các thành phần quan trọng gồm:

1. Task type/implementation.
2. Task action implementation.
3. Implementation classpath và code/plugin versions khi ảnh hưởng execution.
4. Tên output properties.
5. Tên và giá trị input properties.
6. Fingerprints của input file collections, classpaths và normalized file paths.

Khi một task có cùng key với kết quả đã cache, Gradle có thể lấy output mà không thực thi task action.

**Cache key không chỉ là checksum của một file Java.** Nếu Java source không đổi nhưng compiler options, toolchain, dependencies, annotation processors hoặc implementation thay đổi, key có thể khác.

### 5.1. Cache key không bắt buộc gắn với task name duy nhất

Hai tasks ở những projects khác nhau có thể reuse kết quả nếu task implementation và mọi inputs/cache-key components thực sự tương đương. Đó là lý do Gradle build cache hữu ích cho workspaces, branches và CI agents khác nhau.

### 5.2. Không cache mọi task tùy tiện

Cache có ích với compilation, deterministic code generation và static-analysis tasks có inputs đầy đủ. Nhưng **Copy/Sync** thường có execution cost rẻ hơn cache transfer; **publish/deploy**, thay database, gửi thông báo và các operations có side effects thường không phù hợp.

## 6. UP-TO-DATE và FROM-CACHE qua chuỗi thời gian

Giả sử task nhận input **S**, output **O**, cache key **K**:

~~~text
Lần 1:
  Output O chưa có.
  Task EXECUTED -> tạo O.
  Cache enabled -> store output theo K.

Lần 2:
  S không đổi, O vẫn ở workspace.
  Gradle kiểm tra history -> UP-TO-DATE.

Lần 3:
  clean -> build/ bị xóa.
  Cache K còn ở local build cache.

Lần 4:
  S không đổi, O không còn.
  Cache lookup K -> FROM-CACHE, restore O.

Lần 5:
  Không sửa gì sau restore.
  O hợp lệ -> thường UP-TO-DATE.
~~~

**clean không xóa local build cache theo mặc định.** Clean thường xóa **build/**, còn local build cache thông thường ở Gradle User Home hoặc một đường dẫn đã cấu hình.

### 6.1. FROM-CACHE không được bảo đảm sau clean

Nếu task không cacheable, cache chưa bật khi execution đầu tiên, entry không tồn tại, key thay đổi, cache bị xóa hoặc remote cache không truy cập được, task phải thực thi.

### 6.2. Có thể FROM-CACHE mà không clean

Giả sử:

~~~text
recipient=Gradle -> output K1 -> cached
recipient=Java   -> output K2 -> cached
recipient=Gradle -> inputs trở về K1
                   hiện tại output vẫn là kết quả K2
                   -> FROM-CACHE nếu entry K1 còn
~~~

Cache giữ kết quả cho các **input states khác nhau**, không chỉ phục hồi sau clean.

## 7. Các tùy chọn Gradle cần nhớ

| Tùy chọn | Tác dụng | Không có nghĩa là |
| --- | --- | --- |
| **--build-cache** | Bật task output caching cho invocation | Mọi task sẽ FROM-CACHE |
| **--no-build-cache** | Tắt task output build cache trong invocation | Tắt UP-TO-DATE checks |
| **org.gradle.caching=true** | Bật build cache mặc định từ gradle.properties | Custom tasks tự nhiên cacheable |
| **--rerun-tasks** | Ép task được chọn và dependencies thực thi, bỏ qua up-to-date skipping | Xóa cache directory |
| **--no-build-cache --rerun-tasks** | Thí nghiệm buộc actions chạy mà không restore cache | Xóa tất cả outputs |
| **clean** | Xóa build outputs mà clean task quản lý | Xóa Gradle user home/cache entries |
| **--info** | In thêm reason của up-to-date/cache decision | Bật cache |
| **--console=plain** | Hiển thị log ổn định hơn cho CI | Thay đổi task semantics |
| **--offline** | Chế độ không kết nối mạng cho dependency resolution | Tắt local build cache |
| **--refresh-dependencies** | Kiểm tra/cập nhật dependency resolution | Xóa toàn bộ task output cache |
| **--configuration-cache** | Reuse configuration phase khi hợp lệ | Task FROM-CACHE |
| **-x test** | Loại task khỏi graph | Test UP-TO-DATE hoặc FROM-CACHE |

Theo tài liệu Gradle, build cache **không bật mặc định**. Dùng **--build-cache** hoặc thêm **org.gradle.caching=true** trong Gradle properties; chọn một chính sách có kiểm soát.

### 7.1. --no-build-cache nhưng vẫn UP-TO-DATE

~~~bash
./gradlew compileJava --no-build-cache
./gradlew compileJava --no-build-cache
~~~

Nếu input/output state không đổi, lần thứ hai vẫn có thể UP-TO-DATE. Đây là bằng chứng trực tiếp rằng hai cơ chế độc lập.

### 7.2. --rerun-tasks không phải clean

~~~bash
./gradlew compileJava --rerun-tasks --no-build-cache
~~~

Task được yêu cầu thực thi lại dù outputs tồn tại, nhưng không vì thế xóa mọi thứ trong **build/**. Chỉ dùng khi cần debug hoặc policy bắt buộc execution mới.

## 8. Lab Java 17: custom cacheable task đầy đủ

Ta xây một dự án nhỏ **cache-outcomes-lab**, gồm:

- Java 17 application **demo.cache.App** với stdout xác định.
- JUnit Jupiter tests để kiểm tra application.
- Custom Gradle task **generateGreeting** viết bằng Java trong **buildSrc**.
- File input template: **config/greeting-template.txt**.
- Scalar input property **recipient**.
- Output: **build/generated/greeting.txt**.
- Local build cache riêng: **.gradle/lab-task-cache**.
- Log **ACTION_EXECUTED: generateGreeting** chỉ xuất hiện khi task action chạy.

Mục đích lab là quan sát sự khác nhau giữa skip do **UP-TO-DATE** và restore do **FROM-CACHE**, không phụ thuộc remote-cache server.

### 8.1. Cây thư mục

~~~text
cache-outcomes-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── .gitignore
├── config/greeting-template.txt
├── buildSrc/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/java/org/example/build/GenerateGreeting.java
└── src/
    ├── main/java/demo/cache/App.java
    └── test/java/demo/cache/AppTest.java
~~~

Cần JDK 17 và một Gradle Wrapper tương thích. Nếu chưa có Wrapper, chạy **gradle wrapper** bằng Gradle CLI đã cài phù hợp, rồi commit script/JAR/properties của Wrapper. **buildSrc** được Gradle tự phát hiện và compile trước khi cấu hình main build, nên class **GenerateGreeting** có trên build script classpath.

Trong hệ thống lớn, hãy cân nhắc chuyển task type vào **build-logic**/convention plugin thay vì tích lũy quá nhiều buildSrc scripts. Lab ưu tiên tính trực quan.

### 8.2. settings.gradle

~~~groovy
dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'cache-outcomes-lab'

buildCache {
    local {
        enabled = true
        push = true
        directory = file('.gradle/lab-task-cache')
    }
}
~~~

- **mavenCentral()** là nơi resolve JUnit 5 dependencies của app.
- **local.enabled/push** quy định local cache được đọc/ghi nếu build cache được bật ở cấp Gradle invocation.
- **directory** đưa cache vào vùng **.gradle** của lab, tách khỏi output **build/**.
- Các lệnh trong lab vẫn dùng **--build-cache** để bật caching rõ ràng; cấu hình nơi lưu cache không thay thế cờ bật này.
- Trong dự án thật, có thể dùng local cache mặc định tại Gradle User Home thay vì đưa cache vào thư mục repo.

### 8.3. build.gradle

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.cache.App'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release.set(17)
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.register(
        'generateGreeting',
        org.example.build.GenerateGreeting) {
    recipient.set(
        providers.gradleProperty('recipient').getOrElse('Gradle'))
    templateFile.set(
        layout.projectDirectory.file('config/greeting-template.txt'))
    outputFile.set(
        layout.buildDirectory.file('generated/greeting.txt'))
}
~~~

Custom task đăng ký lazy qua **tasks.register**. Values được gắn vào typed properties, và Gradle sẽ biết **recipient** cùng **templateFile** là inputs, **outputFile** là output khi nhìn các annotations của task type.

**application plugin** cung cấp task **run** để chạy Java Main, còn **generateGreeting** là một task sinh file text độc lập. Không nhầm task output cache của GenerateGreeting với Java dependency caches.

### 8.4. buildSrc/settings.gradle

~~~groovy
rootProject.name = 'buildSrc'
~~~

### 8.5. buildSrc/build.gradle

~~~groovy
plugins {
    id 'java'
}

dependencies {
    implementation gradleApi()
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release.set(17)
}
~~~

Dependency **gradleApi()** cho phép code trong buildSrc import **DefaultTask**, **Property**, **RegularFileProperty** và annotations của Gradle API. Vì chạy Java 17, buildSrc source cũng dùng Java 17 syntax tiêu chuẩn.

### 8.6. buildSrc/src/main/java/org/example/build/GenerateGreeting.java

~~~java
package org.example.build;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.CacheableTask;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.InputFile;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.PathSensitive;
import org.gradle.api.tasks.PathSensitivity;
import org.gradle.api.tasks.TaskAction;

@CacheableTask
public abstract class GenerateGreeting extends DefaultTask {

    @Input
    public abstract Property<String> getRecipient();

    @InputFile
    @PathSensitive(PathSensitivity.RELATIVE)
    public abstract RegularFileProperty getTemplateFile();

    @OutputFile
    public abstract RegularFileProperty getOutputFile();

    @TaskAction
    public void generate() throws IOException {
        Path template = getTemplateFile()
                .get().getAsFile().toPath();

        String pattern = Files.readString(
                template, StandardCharsets.UTF_8).strip();

        String result = String.format(
                Locale.ROOT, pattern, getRecipient().get());

        Path destination = getOutputFile()
                .get().getAsFile().toPath();

        Files.createDirectories(destination.getParent());

        Files.writeString(
                destination,
                result + "\n",
                StandardCharsets.UTF_8);

        getLogger().lifecycle(
                "ACTION_EXECUTED: generateGreeting");
    }
}
~~~

Đây là **một Java task class hoàn chỉnh**, không phải pseudocode.

**Từng annotation có trách nhiệm cụ thể:**

- **@CacheableTask**: task type opt-in để outputs có thể lưu/khôi phục qua build cache.
- **@Input**: recipient là giá trị ảnh hưởng output content.
- **@InputFile**: template file content ảnh hưởng output.
- **@PathSensitive(PathSensitivity.RELATIVE)**: đường dẫn input được normalize theo đường dẫn tương đối; giúp giảm phụ thuộc vào absolute workspace path khi không cần.
- **@OutputFile**: Gradle biết output nào cần fingerprint và restore.
- **@TaskAction**: chỉ thực thi khi task không được bỏ qua/restore.
- **UTF-8** và newline cố định **"\n"** tránh sai khác do default charset/OS line endings.
- **Locale.ROOT** giúp quá trình String.format không phụ thuộc locale hệ thống.

**Giới hạn rõ ràng:** Input template của bài học là tệp tin tin cậy có một placeholder **%s**. Với template tùy ý có nhiều format specifiers, phải có validation hoặc dùng templating library phù hợp. Không dùng task này để render dữ liệu nhạy cảm rồi đẩy lên shared remote cache.

### 8.7. config/greeting-template.txt

~~~text
Xin chào, %s!
~~~

### 8.8. src/main/java/demo/cache/App.java

~~~java
package demo.cache;

public final class App {
    private App() {
    }

    public static String title(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(
                    "text must not be blank");
        }
        return "APP=" + text.strip();
    }

    public static void main(String[] args) {
        System.out.println(title(" Gradle 17 "));
    }
}
~~~

Stdout chính xác:

~~~text
APP=Gradle 17
~~~

### 8.9. src/test/java/demo/cache/AppTest.java

~~~java
package demo.cache;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AppTest {
    @Test
    void formatsTitle() {
        assertEquals(
                "APP=Gradle 17",
                App.title(" Gradle 17 "));
    }

    @Test
    void rejectsBlankText() {
        assertThrows(
                IllegalArgumentException.class,
                () -> App.title("   "));
    }
}
~~~

Hai JUnit tests được thiết kế để pass khi chạy qua Gradle **test**. Với project này, JUnit dependencies chỉ nằm trên **testImplementation/testRuntimeOnly**, không đi vào runtime classpath của app production.

### 8.10. .gitignore

~~~gitignore
.gradle/
build/
buildSrc/build/
out/
~~~

**Không commit** cache blobs, generated files hoặc compiler outputs. Cache không thay thế source code, artifact repository, checksum hoặc release provenance.

## 9. Thí nghiệm thứ nhất — chạy task action thật

Từ root của **cache-outcomes-lab/** trên Linux/macOS:

~~~bash
./gradlew clean generateGreeting \
  --build-cache \
  --console=plain \
  --info
~~~

Trong checkout sạch và cache chưa có entry khớp, bạn sẽ thấy tương tự:

~~~text
> Task :generateGreeting
ACTION_EXECUTED: generateGreeting
BUILD SUCCESSFUL
~~~

Tệp được tạo:

~~~text
build/generated/greeting.txt
~~~

Nội dung chính xác:

~~~text
Xin chào, Gradle!
~~~

**Đây là kết quả dự kiến của source Java**, không phải log đã đo trên một máy cụ thể. Console có thể có thêm task lines và thông tin buildSrc. Nếu cache đã từng được làm nóng, ngay lần đầu của một phiên mới cũng có thể nhận FROM-CACHE sau clean.

### 9.1. Đọc output

Linux/macOS:

~~~bash
cat build/generated/greeting.txt
~~~

Windows PowerShell:

~~~powershell
Get-Content -Encoding UTF8 build\generated\greeting.txt
~~~

Chỉ đọc file không phân biệt được task execution hay cache restore. Hãy quan sát nhãn task và logger **ACTION_EXECUTED**.

## 10. Thí nghiệm thứ hai — UP-TO-DATE

Không sửa bất kỳ source hoặc input nào:

~~~bash
./gradlew generateGreeting \
  --build-cache \
  --console=plain \
  --info
~~~

Kỳ vọng:

~~~text
> Task :generateGreeting UP-TO-DATE
~~~

Lần này không có:

~~~text
ACTION_EXECUTED: generateGreeting
~~~

**Nguyên nhân:** recipient vẫn là Gradle, template chưa đổi, task implementation ổn định và output file còn đúng trong workspace.

### 10.1. Tắt cache vẫn có UP-TO-DATE

~~~bash
./gradlew generateGreeting \
  --no-build-cache \
  --console=plain
~~~

Với inputs/outputs không đổi, outcome vẫn có thể là:

~~~text
> Task :generateGreeting UP-TO-DATE
~~~

Đây là thí nghiệm tốt nhất để chống nhầm lẫn: **UP-TO-DATE không cần build cache đang bật**.

## 11. Thí nghiệm thứ ba — clean rồi FROM-CACHE

~~~bash
./gradlew clean --console=plain

./gradlew generateGreeting \
  --build-cache \
  --console=plain \
  --info
~~~

**clean** xóa **build/generated/greeting.txt**, nhưng **.gradle/lab-task-cache** được cấu hình bên ngoài build directory nên entry cũ có thể còn.

Nếu local cache có entry đúng key, outcome dự kiến:

~~~text
> Task :generateGreeting FROM-CACHE
~~~

Task action không chạy, nhưng **build/generated/greeting.txt** được khôi phục với nội dung:

~~~text
Xin chào, Gradle!
~~~

Đây là trường hợp chỉ nhờ **build cache** mà output trở lại workspace.

### 11.1. Sau FROM-CACHE có thể UP-TO-DATE

Chạy lại:

~~~bash
./gradlew generateGreeting --build-cache --console=plain
~~~

Nếu output đã được restore đúng và không đổi input, Gradle thường trả **UP-TO-DATE**. Không có lý do phải restore lại một file đang tồn tại hợp lệ.

### 11.2. Nếu lại thấy EXECUTED?

Kiểm tra **--info** và những điều kiện:

- Có bật --build-cache ở lần task execution trước để lưu entry?
- Task có đủ @Input/@Output và @CacheableTask?
- Cache entry có bị dọn/xóa?
- buildSrc implementation có bị sửa?
- Input template hoặc recipient có khác?
- Gradle/Java/Gradle API classpath khác?
- Cache bị vô hiệu hóa vì validation hoặc configuration?
- Cấu hình cache directory có đúng không?

Đừng cố thay cache key bằng tay hoặc copy arbitrary cache blobs để ép FROM-CACHE.

## 12. Thí nghiệm thứ tư — đổi recipient

~~~bash
./gradlew generateGreeting \
  -Precipient=Java \
  --build-cache \
  --console=plain \
  --info
~~~

Nếu chưa có cache entry cho recipient mới, task action chạy:

~~~text
> Task :generateGreeting
ACTION_EXECUTED: generateGreeting
~~~

Output mới:

~~~text
Xin chào, Java!
~~~

**@Input** khiến Gradle nhận thấy recipient thay từ **Gradle** sang **Java**. Kết quả output cũ không còn đúng cho input mới.

Bây giờ đổi về input ban đầu:

~~~bash
./gradlew generateGreeting \
  -Precipient=Gradle \
  --build-cache \
  --console=plain \
  --info
~~~

Nếu entry cho recipient=Gradle vẫn còn, Gradle có thể nhận **FROM-CACHE** mà **không cần clean**: nó restore một kết quả cũ phù hợp key, thay cho output Java hiện tại.

~~~text
K1: recipient=Gradle -> "Xin chào, Gradle!"
K2: recipient=Java   -> "Xin chào, Java!"
Quay lại K1           -> cache K1 được tái dùng
~~~

**Điều kiện “cache entry vẫn tồn tại” phải được giữ rõ.** Không tuyên bố luôn FROM-CACHE nếu cache bị dọn hoặc task implementation thay đổi.

## 13. Thí nghiệm thứ năm — đổi nội dung input file

Tạm đổi template:

~~~text
Chào mừng, %s!
~~~

Chạy:

~~~bash
./gradlew generateGreeting \
  --build-cache \
  --console=plain \
  --info
~~~

Output mới nếu recipient vẫn là Gradle:

~~~text
Chào mừng, Gradle!
~~~

**Vì sao?** Template có @InputFile; đổi file content làm input fingerprint khác, nên task không UP-TO-DATE theo trạng thái cũ. Nếu chưa có cache entry cho template mới, action chạy.

Khôi phục template ban đầu và chạy lần nữa; nếu entry cũ còn, có thể FROM-CACHE. Nếu các trạng thái/history đã được thay đổi bởi một hoạt động khác, hãy phân tích task outcome thực thay vì ép kết quả.

### 13.1. Path sensitivity

Một số kiểu normalization:

| Kiểu | Semantics điển hình | Cẩn trọng |
| --- | --- | --- |
| **ABSOLUTE** | Absolute path là một phần ý nghĩa input | Cache kém khi chuyển workspace |
| **RELATIVE** | Relative path và content có ý nghĩa | Đổi đường dẫn tương đối có thể đổi fingerprint |
| **NAME_ONLY** | Basename và content là đủ | File cùng tên trong các thư mục khác dễ va chạm |
| **NONE** | Chỉ content quan trọng, path không liên quan | Sai nếu output chứa hoặc dùng input path |

Chọn **@PathSensitive** theo hành vi thật, không chỉ để tăng cache hits. Nếu output chứa absolute paths của máy developer, việc khai báo NONE hoặc RELATIVE sai cách có thể phục hồi output không hợp lệ ở máy khác.

## 14. Thí nghiệm thứ sáu — ép task chạy, không dùng cache

### 14.1. Không có output và cache tắt

~~~bash
./gradlew clean --console=plain
./gradlew generateGreeting --no-build-cache --console=plain
~~~

Vì output đã bị clean và không được restore từ cache, task cần chạy action; logger **ACTION_EXECUTED** sẽ xuất hiện.

### 14.2. Không cần xóa output vẫn ép chạy

~~~bash
./gradlew generateGreeting \
  --rerun-tasks \
  --no-build-cache \
  --console=plain
~~~

Lệnh này buộc task chạy lại thay vì dùng up-to-date/cache reuse, nhưng **không tự xóa toàn bộ build directory**.

### 14.3. Không biến các cờ debug thành mặc định production

Nếu mọi CI run đều dùng clean + --rerun-tasks --no-build-cache không cần thiết, bạn sẽ đánh mất khả năng tăng tốc mà Gradle cung cấp. Chỉ buộc execution mới cho những quality gates hoặc investigations có lý do rõ.

## 15. Chạy ứng dụng Java 17

Gradle:

~~~bash
./gradlew test
./gradlew -q run
~~~

Stdout của Java Main:

~~~text
APP=Gradle 17
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat -q run
~~~

### 15.1. javac/java độc lập

Từ root, Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -d out src/main/java/demo/cache/App.java
java -cp out demo.cache.App
~~~

Windows:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src\main\java\demo\cache\App.java
java -cp out demo.cache.App
~~~

Stdout:

~~~text
APP=Gradle 17
~~~

**Điều được kiểm chứng:** Source Java 17 compile và run đúng.

**Điều chưa được kiểm chứng:** Gradle task annotation processing, cache key, local cache restore, JUnit tests, buildSrc wiring hoặc CI cache policy. Muốn chứng minh chúng hoạt động, cần chạy Gradle Wrapper và đọc outcome/results thực.

## 16. Gradle JavaCompile cũng là một ví dụ thực tế

Gradle JavaCompile là một loại built-in cacheable task. Có thể thử:

~~~bash
./gradlew compileJava --build-cache --console=plain
./gradlew compileJava --build-cache --console=plain
./gradlew clean --console=plain
./gradlew compileJava --build-cache --console=plain
~~~

Một chuỗi outcome có thể là:

~~~text
> Task :compileJava
> Task :compileJava UP-TO-DATE
> Task :compileJava FROM-CACHE
~~~

Đây là các dòng **minh họa** (mỗi dòng đến từ một invocation khác). Nếu cache đã ấm, input khác, compiler options đổi hoặc output bị plugin can thiệp, quan sát thực có thể khác.

**Không suy mọi task Java đều cacheable.** Jar, Copy, lifecycle tasks và Test có đặc tính chi phí, caching opt-in và output model khác nhau.

### 16.1. Test cacheability và correctness

Test task built-in hỗ trợ caching, nhưng tests phụ thuộc database ngoài, clock, environment, browser, locale, services hoặc port ngẫu nhiên có thể không an toàn nếu các điều kiện không được mô hình hóa. Cần:

- Cô lập test environment.
- Khai báo test JVM args/system properties có ảnh hưởng.
- Dùng fixtures deterministic.
- Tránh test phụ thuộc network state chưa được khai báo.
- Vô hiệu cache của tests không thể deterministic nếu policy yêu cầu.
- Có job kiểm thử release thật trong environment đáng tin khi cần.

## 17. Custom @CacheableTask phải thật sự deterministic

Thêm annotation không làm task đúng một cách kỳ diệu.

### 17.1. Undeclared environment input

Nếu task đọc:

~~~java
String region = System.getenv("BUILD_REGION");
~~~

bên trong action, rồi ghi region vào output nhưng không khai báo **@Input**, Gradle có thể UP-TO-DATE sai hoặc lấy FROM-CACHE của region khác. Đây là lỗi **correctness nghiêm trọng**.

Cách đúng là mô hình hóa region thành **Property<String> @Input** và cấp qua Provider environment variable; task action chỉ đọc property. Tuy nhiên, đừng đưa secrets trực tiếp vào cache key/output nếu điều đó làm lộ dữ liệu.

### 17.2. Thiếu output declaration

Nếu action ghi:

~~~text
build/generated/report.txt
~~~

nhưng task type không khai báo @OutputFile/@OutputDirectory, Gradle không biết phải theo dõi hoặc restore file nào. Task có thể không được tối ưu hợp lệ và dễ xảy ra overlap.

### 17.3. Không ghi ngoài declared outputs

Nếu custom task vừa tạo **build/generated/result.txt**, vừa sửa **src/main/java/App.java**, cache restoration không tái diễn side effect sửa source, và lần build sau có thể không đúng. Hãy đặt generated sources dưới build/ và nối vào sourceSets bằng Provider/TaskProvider.

### 17.4. Clock, randomness và network

Một task lấy **currentTimeMillis()** hoặc ngẫu nhiên làm output mà không khai báo chúng là inputs sẽ không deterministic. Tác vụ deploy, gửi email, thực thi database migrations hoặc gọi remote APIs có external side effects không nên được coi là task có thể phục hồi đầy đủ bằng một cache blob.

### 17.5. Output phụ thuộc filesystem/OS/JDK

Lỗi thường gặp:

- File output dùng default charset khác UTF-8.
- Dùng **System.lineSeparator()** nên output khác CRLF/LF.
- Ghi absolute path của workspace vào artifact.
- Compiler/JDK version khác nhau.
- Task dùng locale/timezone mặc định.
- Classpath hoặc resource order chưa ổn định.
- Output chứa timestamp/random value.

Để cache reuse đúng giữa máy, cần ổn định hoặc khai báo các yếu tố có ảnh hưởng. Có thể dùng **@NormalizeLineEndings** và classpath normalization khi đúng semantics, không nên dùng để che những khác biệt quan trọng.

### 17.6. Sai PathSensitivity

Nếu output là JSON chứa path source, nhưng file input được đánh dấu **PathSensitivity.NONE**, hai đường dẫn khác nhau có thể bị xem là cùng input khi thực tế output khác. Không tối ưu cache bằng cách đánh đổi tính đúng đắn.

### 17.7. Task implementation phải theo dõi được

Gradle theo dõi implementation/action code. Nếu plugin sử dụng untracked/unknown classloader hoặc lambda implementation không thể fingerprint ổn định, caching và thậm chí up-to-date checks có thể bị vô hiệu. Đọc warnings trong **--info** và task validation report.

## 18. Incremental task execution là tầng thứ ba

Đôi khi một task vẫn chạy nhưng chỉ xử lý những file đã thay đổi.

~~~text
A.java không đổi
B.java đổi implementation
compileJava được thực thi

> Task :compileJava

Compiler có thể chỉ compile những phần cần thiết.
~~~

Task outcome lúc này không phải UP-TO-DATE vì action đã chạy. Tuy nhiên, công việc bên trong có thể incremental.

Gradle cung cấp **InputChanges** cho custom incremental tasks, giúp phát hiện files ADDED/MODIFIED/REMOVED. Một ví dụ API minh họa:

~~~java
@TaskAction
public void execute(InputChanges changes) {
    // Duyệt thay đổi của các input file properties,
    // xử lý từng file thay vì xử lý toàn bộ tập.
}
~~~

**Snippet trên không độc lập:** Cần task class, annotations, import **org.gradle.work.InputChanges** và file input properties thích hợp. Không thêm nó vào GenerateGreeting của lab, vì task đó tạo đúng một output nhỏ từ một template.

**FROM-CACHE:** Action không chạy, nên cũng không có incremental processing trong action của invocation đó.

## 19. Cache của những task khác nhau

| Loại task | Có thể cache? | Lưu ý |
| --- | --- | --- |
| **JavaCompile** | Có, built-in cacheable | Compiler, flags, classpath, JDK ảnh hưởng key |
| **Javadoc** | Có, built-in cacheable | Tool/options/source inputs cần ổn định |
| **Test** | Có, built-in cacheable | Cần deterministic tests và environment modeling |
| **Checkstyle/PMD/CodeNarc** | Nhiều built-in tasks hỗ trợ | Rules và tool versions ảnh hưởng output |
| **JacocoReport** | Có hỗ trợ | Dữ liệu test execution/classes/source ảnh hưởng |
| **Copy / Sync** | Thường không cache mặc định | I/O local có thể rẻ hơn restore |
| **Jar** | Không tự suy là cacheable | Up-to-date/reproducible archives vẫn hữu ích |
| **Custom @CacheableTask** | Có điều kiện | Declared inputs/outputs, correct implementation |
| **Publish/deploy** | Không nên cache side effects | Remote state/credentials không được restore bằng file |
| **Lifecycle build/check/classes** | Không phải một artifact action riêng | Có thể UP-TO-DATE mà không có cache hit |

**Lợi ích cache không phải vô điều kiện.** Một task Copy vài bytes tốn vài mili-giây có thể chậm hơn nếu phải tar/upload/download/unpack output.

## 20. Local build cache khác output directory

Trong lab:

~~~text
build/generated/greeting.txt     <-- output đang ở workspace
.gradle/lab-task-cache/          <-- các cached entries
~~~

Thông thường, Gradle local build cache được quản lý trong **Gradle User Home**. Gradle có cleanup/retention policy; entry có thể bị xóa, khiến cache miss dù inputs không đổi.

### 20.1. Vì sao build/ không phải local cache?

**build/** chứa kết quả có thể được tiêu thụ trực tiếp bởi tasks/ứng dụng. Khi clean, output này biến mất.

**Local build cache** giữ các entries theo keys, không phải “bản sao trực tiếp” với path giống build/ mà developer cần thao tác. Không viết code đọc trực tiếp internal cache files như một public API.

### 20.2. Đừng commit cache blobs

Cache có thể chứa generated outputs, test artifacts và trong task sai thiết kế có cả dữ liệu nhạy cảm. Không đưa **.gradle/** hoặc **~/.gradle/** lên Git hay vào public CI artifacts.

### 20.3. Caching thực sự giúp nhanh khi nào?

So sánh:

~~~text
UP-TO-DATE = fingerprint kiểm tra, không cần restore
FROM-CACHE local = lookup + đọc/unpack/copy
FROM-CACHE remote = lookup + network transfer + unpack
EXECUTED = chạy logic thật + có thể store cache
~~~

Bởi vậy UP-TO-DATE thường ít tốn công hơn FROM-CACHE. Với tasks rẻ, remote restore có thể chậm hơn thực thi.

## 21. Remote build cache và CI

Remote build cache cho phép nhiều agents/workspaces chia sẻ task outputs khi key khớp:

~~~text
Trusted CI
   |
   +-- cache miss -> execute -> push K
   |
   v
HTTPS remote cache
   |
   +--> Dev A đọc K -> FROM-CACHE
   |
   +--> CI B đọc K -> FROM-CACHE
~~~

### 21.1. Local và remote cache

| Khía cạnh | Local | Remote |
| --- | --- | --- |
| Vị trí | Máy hiện tại | Cache server |
| Giá trị | Branch switching và repeated builds | Chia sẻ giữa team/CI agents |
| Chi phí | Disk I/O | Network/auth/unpack |
| Access | Filesystem permissions | TLS, credentials, server policy |
| Retention | Local cleanup | Server retention/quota |
| Bảo mật | Không làm lộ dữ liệu local | Có rủi ro cache poisoning/secret leakage |
| Push | Local process theo cấu hình | Chỉ trusted identities nên được ghi |

Gradle có thể thử local trước, sau đó remote nếu local miss. Remote hit có thể được lưu lại local để lần sau nhanh hơn.

### 21.2. Chỉ trusted CI được push remote cache

Một chính sách hợp lý:

- Protected CI builds được phép **push**, với service identity và quyền phù hợp.
- Developer và untrusted PR builds dùng **read-only** hoặc không được truy cập cache nhạy cảm.
- Server kiểm soát TLS, credentials, audit và quota.
- Không cho fork/unreviewed code đưa cache entry tùy ý để trusted jobs tiêu thụ.
- Không cache files chứa secrets/PII hoặc generated credentials.

**Cache poisoning** có thể xảy ra nếu bên không tin cậy có quyền ghi output giả dưới key. Caching cần nằm trong threat model của software supply chain.

### 21.3. Cấu hình remote theo Settings API

Khi có cache server thật, Gradle hỗ trợ **buildCache { remote(HttpBuildCache) { ... } }**. Ví dụ cấu hình dạng tham khảo:

~~~groovy
def endpoint =
        providers.gradleProperty('remoteCacheUrl').orNull

if (endpoint != null) {
    buildCache {
        remote(HttpBuildCache) {
            url = uri(endpoint)
            push = false
        }
    }
}
~~~

Đây là **snippet mở rộng**, không thuộc lab đầy đủ vì cần URL service thực. Trong production phải thêm authentication/secret management theo API và chỉ cho phép push bởi **trusted CI server credentials**. Không dùng project property do PR tùy ý đặt để tự cấp quyền ghi.

Không bật **allowUntrustedServer** hoặc vô hiệu TLS verification để né lỗi chứng chỉ. Sửa CA trust store và cache endpoint đúng.

## 22. Dependency cache và configuration cache khác task output cache

| Cơ chế | Lưu cái gì? | Dấu hiệu |
| --- | --- | --- |
| **Up-to-date history** | Inputs/outputs hiện hành được theo dõi tại workspace | UP-TO-DATE |
| **Task output build cache** | Cached outputs của tasks theo key | FROM-CACHE |
| **Dependency cache** | Downloaded JARs, metadata và resolution state | Không đồng nghĩa FROM-CACHE |
| **Configuration cache** | Kết quả configuration/task graph khi hợp lệ | Configuration cache entry reused |
| **Incremental compiler state** | Dữ liệu phục vụ compile một phần | Task có thể vẫn EXECUTED |
| **Gradle daemon/VFS** | Process và filesystem-state optimization | Không tự là task output cache |

### 22.1. Tải JUnit dependency từ cache không phải test FROM-CACHE

Gradle có thể sử dụng JUnit JAR đã được download ở dependency cache, nhưng **test** vẫn chạy action. Đây là việc tái sử dụng một dependency artifact, khác hoàn toàn việc restore test report/task outputs.

### 22.2. Configuration cache reuse không chứng minh task output reuse

Ví dụ:

~~~text
Configuration cache entry reused.
> Task :compileJava
~~~

Gradle không cần cấu hình lại task graph, nhưng compileJava vẫn có thể thực thi. Ngược lại, task có thể FROM-CACHE dù configuration cache tắt.

### 22.3. --refresh-dependencies không phải xóa task output cache

Cờ này ảnh hưởng trạng thái dependency resolution. Không dùng nó như một lệnh “ép compileJava chạy lại”, và không xóa cả Gradle user home khi chỉ cần xem một input thay đổi.

## 23. Debug khi task đáng lẽ UP-TO-DATE nhưng vẫn chạy

Kiểm tra theo thứ tự:

1. Lệnh thực tế có dùng **--rerun-tasks** không?
2. Input file hoặc scalar property nào đã đổi?
3. Output file có bị xóa/sửa bởi task khác hoặc shell script không?
4. Task implementation/buildSrc/plugin version có đổi không?
5. Java toolchain, compiler options hoặc dependency graph có khác không?
6. Task action có undeclared input nào như clock/env/absolute path không?
7. Có task output validation warning hoặc overlapping directories không?
8. Task có **outputs.upToDateWhen { false }** hoặc **doNotTrackState** không?
9. CI checkout mới có mất workspace history không?
10. Có task no-source/skip rules thay vì up-to-date không?

Dùng:

~~~bash
./gradlew generateGreeting \
  --no-build-cache \
  --info \
  --console=plain
~~~

Quan sát cụ thể lý do task executed hoặc UP-TO-DATE, không đoán từ thời gian chạy ngắn.

### 23.1. Không lạm dụng upToDateWhen

~~~groovy
tasks.named('generateGreeting') {
    outputs.upToDateWhen { false }
}
~~~

Đây là **antipattern minh họa** nếu mục tiêu chỉ là ép task chạy mà chưa hiểu inputs. Nó có thể vô hiệu up-to-date skipping. Cần sửa mô hình inputs/outputs hoặc dùng **--rerun-tasks** khi chỉ debug.

### 23.2. Task thực sự không thể track state

**doNotTrackState(...)** hoặc **@UntrackedTask** phù hợp cho task có external state khó mô hình hóa hoặc công cụ tự quản lý state. Những task đó thường không có up-to-date/build-cache reuse chuẩn. Không giả đánh dấu @CacheableTask là đủ để “cache” một thao tác deploy.

## 24. Debug khi cache bật nhưng không thấy FROM-CACHE

Những điều kiện cần kiểm tra:

- Cache có bật bởi CLI/property không?
- Task type có @CacheableTask hoặc một caching rule hợp lệ không?
- Task có declared outputs và không vi phạm validation?
- Task có thật sự không UP-TO-DATE? Nếu UP-TO-DATE, cache lookup không cần.
- Input fingerprint và implementation có giống một entry cũ không?
- Cache entry có bị cleanup/eviction không?
- Local/remote cache có readable không?
- Network/TLS/authentication của remote cache có hoạt động không?
- Task có bị skip bởi onlyIf/no-source không?
- Task execution lần trước có thành công và được lưu cache không?
- Task output có chứa nondeterminism không?
- File path sensitivity và classpath normalization có phù hợp không?

### 24.1. Một bảng lệnh chẩn đoán

~~~bash
./gradlew generateGreeting \
  --build-cache --info --console=plain

./gradlew generateGreeting \
  --no-build-cache --info --console=plain

./gradlew clean generateGreeting \
  --build-cache --info --console=plain

./gradlew generateGreeting \
  --rerun-tasks --no-build-cache \
  --info --console=plain
~~~

Hãy chạy chúng trong **lab riêng**, không thực hiện clean trên workspace chứa outputs quan trọng chưa được backup.

### 24.2. “Caching disabled for task”

Gradle có thể không cache vì task chưa opt-in, không có outputs, có validation problem, source/action implementation không theo dõi được, caching rule bị disable hoặc task thuộc loại không nên cache. **--info** và task validation giúp tìm lý do cụ thể.

Một cache miss hoàn toàn có thể là **hành vi đúng** khi input thay đổi. Đừng tối ưu số lượng cache hits bằng cách bỏ qua một input quan trọng.

## 25. Các lỗi và cách sửa

| Vấn đề | Nguyên nhân/hiểu nhầm | Cách xử lý |
| --- | --- | --- |
| UP-TO-DATE được gọi là cache hit | Output đang hợp lệ tại workspace | Phân biệt nhãn và execution history |
| FROM-CACHE được gọi là task execution | Action thực ra không chạy | Kiểm tra logs và restored outputs |
| Clean xong không compile | Cache entry phù hợp đã tồn tại | Đây có thể là FROM-CACHE đúng |
| --no-build-cache vẫn UP-TO-DATE | Incremental up-to-date checks độc lập | Không nhầm cờ cache |
| Không có FROM-CACHE dù bật cache | Output đã UP-TO-DATE | Không cần cache restore |
| Task luôn execute | Thiếu declared outputs hoặc model không ổn định | Sửa inputs/outputs |
| @CacheableTask không có hit | Validation, disabled caching, key khác | Đọc --info và cacheability reason |
| NoClassDefFoundError sau cache hit | Dependency/model sai hoặc outputs cũ | Kiểm tra task inputs, artifact content, dependency graph |
| NO-SOURCE được tính test pass | Không có tests/source thực thi | Kiểm tra JUnit counts/source sets |
| SKIPPED bị hiểu là up-to-date | Task bị onlyIf/skip condition | Xem task condition |
| Cache hit nhưng output khác môi trường | Undeclared env/path/JDK input | Mô hình hóa hoặc disable caching |
| Remote cache không hit | Auth/TLS/retention/key mismatch | Kiểm tra server và --info |
| Remote cache bị đầu độc | Untrusted writers | Server permissions và trusted CI push |
| Cache chứa secret | Task cache output nhạy cảm | Không cache secret-dependent tasks |
| --refresh-dependencies không làm task rerun | Dependency cache khác build cache | Dùng đúng flags/debug |
| Configuration cache reused nhưng task chạy | Config state khác task output state | Phân biệt hai cache |
| Task output bị task khác ghi đè | Output ownership overlap | Tách output locations/producers |
| Cache từ Windows không hợp Linux | Charset/newline/native binaries | Normalize hoặc khai báo platform input |
| --rerun-tasks khiến build chậm | Ép actions, bỏ qua tối ưu | Chỉ dùng khi cần |
| Cache miss sau sửa buildSrc | Implementation classpath đổi | Đây thường là invalidation đúng |
| FROM-CACHE không nhanh | Tệp lớn/network cost cao | Đo download/unpack vs execution |
| Task action được bỏ qua khi deploy | Đã cache task có side effect | Thiết kế publish/deploy không-cache |
| Cache hit được coi là code an toàn | Caching không phải security scan | Giữ tests, review, SBOM và provenance |

## 26. CI minh họa cho bài học

Tạo **.github/workflows/cache-lab.yml** nếu muốn quan sát trong một GitHub Actions run:

~~~yaml
name: Gradle caching lab

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Gradle setup
        uses: gradle/actions/setup-gradle@v6

      - name: Build and test
        run: |
          ./gradlew --no-daemon test generateGreeting \
            --build-cache --console=plain --info

      - name: Observe up-to-date task
        run: |
          ./gradlew --no-daemon generateGreeting \
            --build-cache --console=plain --info

      - name: Validate output bytes
        shell: bash
        run: |
          actual="$(cat build/generated/greeting.txt)"
          test "$actual" = 'Xin chào, Gradle!'

      - name: Preserve test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: java-cache-lab-reports
          path: |
            build/reports/tests/**
            build/test-results/test/TEST-*.xml
          if-no-files-found: warn
          retention-days: 14
~~~

**Workflow này chủ yếu chứng minh UP-TO-DATE trong cùng job.** Nó không giả rằng một ephemeral runner đã có remote-cache entry để FROM-CACHE giữa các CI runs. Nếu tổ chức muốn reuse remote cache, phải cấu hình endpoint/auth/retention phù hợp và đo cache hit thực.

### 26.1. Giữ quality gate đúng

- Test failures vẫn làm Gradle process exit nonzero.
- Không thêm **|| true** hoặc **continue-on-error** chỉ để pipeline xanh.
- Upload reports có **if: always()**, nhưng không tự tạo test reports nếu task chưa thực thi.
- Cache hit không thay signing/release checks.
- Untrusted PR jobs không được ghi vào shared trusted cache.
- Không upload Gradle user home hoặc secret credentials.

### 26.2. Chỉ đo có ý nghĩa

Theo dõi số task EXECUTED, UP-TO-DATE, FROM-CACHE; thời gian cấu hình; thời gian lookup/upload/download; kích thước cache entries; critical path của build và tỷ lệ miss vì input changes. Không lấy một benchmark cold start làm kết luận tổng quát.

## 27. Bài tập thực hành

### Bài 1 — Đọc outcome

Cho:

~~~text
> Task :compileJava UP-TO-DATE
> Task :processResources NO-SOURCE
> Task :test FROM-CACHE
> Task :publish
~~~

Xác định task nào restore output, task nào không có source và task nào có thể đã thực thi action. Có thể kết luận tests chạy ở job này không?

### Bài 2 — Tắt cache nhưng còn up-to-date

Chạy GenerateGreeting hai lần với **--no-build-cache**. Giải thích vì sao lần hai vẫn có thể UP-TO-DATE.

### Bài 3 — Clean và restore

Bật build cache, chạy task để tạo entry, clean, rồi gọi task với --build-cache. Xem label và nội dung output.

### Bài 4 — Input property

Thay recipient từ Gradle sang Java, quan sát output và outcome. Quay lại Gradle; giải thích khi nào có thể FROM-CACHE.

### Bài 5 — Input file

Đổi nội dung template, chạy lại task. Vì sao đây là cache miss hợp lệ?

### Bài 6 — JavaCompile

Sửa implementation của App.java, chạy **compileJava --info**. Phân biệt task execution với incremental compilation bên trong.

### Bài 7 — No-source

Tạo một Java project không có test sources; chạy **test**. Vì sao NO-SOURCE không chứng minh test pass?

### Bài 8 — Undeclared input

Trong branch thử nghiệm, đọc một environment variable trong @TaskAction nhưng không khai báo input. Giải thích vì sao output có thể sai do up-to-date/cache reuse. Sửa bằng Provider/property hoặc tắt caching nếu task phụ thuộc secret/external state.

### Bài 9 — Rerun

Chạy **--rerun-tasks --no-build-cache**; xác nhận logger ACTION_EXECUTED xuất hiện khi task actions chạy.

### Bài 10 — Cross-workspace

Copy lab sang đường dẫn khác nhưng dùng cùng build cache policy. Giải thích ý nghĩa **PathSensitivity.RELATIVE** và các yếu tố khác có thể khiến cache key khác.

### Bài 11 — Remote threat model

Thiết kế chính sách “trusted CI push, developer/untrusted PR read-only”. Rủi ro gì xảy ra nếu PR có thể push cache entry mà protected release jobs sẽ dùng?

### Bài 12 — Side-effect task

Một task gửi email, deploy container, hoặc chạy migration có nên @CacheableTask không? Vì sao file outputs không đại diện đầy đủ trạng thái remote?

### Bài 13 — Configuration cache

Bật --configuration-cache trên build hỗ trợ, so sánh thông báo configuration-cache reuse với FROM-CACHE. Hai kết quả thuộc hai giai đoạn nào?

### Bài 14 — JDK/OS

Thử chạy Java task ở hai môi trường, một bên dùng UTF-8/newline cố định, bên khác dùng platform defaults. Khác biệt đó có thể làm cache reuse sai hoặc miss thế nào?

### Bài 15 — Đo hiệu suất

So sánh một task JavaCompile tốn nhiều giây và một Copy task vài milliseconds. Khi nào download cache entry chậm hơn thực thi action?

## 28. Câu hỏi tự kiểm tra

1. UP-TO-DATE có nghĩa gì?
2. FROM-CACHE có nghĩa gì?
3. Hai outcome đó có chạy @TaskAction không?
4. Vì sao UP-TO-DATE không chứng minh cache hit?
5. Vì sao FROM-CACHE không nhất thiết download từ Internet?
6. Build cache mặc định có bật không?
7. Cờ nào bật task output caching?
8. Gradle property nào bật cache mặc định?
9. --no-build-cache có tắt up-to-date checking không?
10. clean có xóa cache entries mặc định không?
11. Vì sao task sau clean có thể FROM-CACHE?
12. Cache key phụ thuộc những thông tin gì?
13. Vì sao một task cùng source nhưng đổi compiler flags có thể miss?
14. @CacheableTask tự động làm custom task an toàn không?
15. @Input trong lab chứa gì?
16. @InputFile trong lab chỉ vào file nào?
17. @OutputFile có vai trò gì?
18. PathSensitivity.RELATIVE khác ABSOLUTE thế nào?
19. Đổi recipient tác động tới key như thế nào?
20. Quay lại recipient cũ có thể FROM-CACHE không?
21. Task không có trong graph có outcome gì?
22. NO-SOURCE khác UP-TO-DATE thế nào?
23. SKIPPED khác FROM-CACHE ở đâu?
24. --rerun-tasks giúp điều tra điều gì?
25. Task chạy incremental bên trong có phải UP-TO-DATE không?
26. Test FROM-CACHE có thực thi tests trong job hiện tại không?
27. Dependency cache khác task output cache thế nào?
28. Configuration cache khác task output cache thế nào?
29. Vì sao không cache publish/deploy?
30. Rủi ro của undeclared environment input?
31. Vì sao UTF-8 và newline cố định hỗ trợ caching?
32. Cache hit có tự chứng minh mã không có CVE không?
33. Remote cache poisoning là gì?
34. Khi nào một cache hit có thể chậm hơn execute?
35. Lệnh nào kiểm tra Java 17 độc lập với Gradle?

**Đáp án gợi ý:** (1) outputs tại workspace hợp lệ; (2) outputs từ local/remote cache; (3) không; (4) không có restore; (5) có local cache; (6) không; (7) --build-cache; (8) org.gradle.caching=true; (9) không; (10) không; (11) cache entry vẫn còn; (12) implementation/inputs/output property names; (13) compiler flags là inputs; (14) không; (15) recipient; (16) greeting-template.txt; (17) output được tracking/restore; (18) normalized path semantics; (19) key mới; (20) có nếu entry phù hợp; (21) không có outcome; (22) thiếu sources so với outputs hợp lệ; (23) conditional skip so với restore; (24) ép action execution; (25) không; (26) không; (27) downloaded dependencies so với task outputs; (28) configuration graph so với outputs; (29) external side effects; (30) stale/incorrect cached outputs; (31) deterministic bytes; (32) không; (33) output giả từ untrusted writer; (34) cache transfer cost cao; (35) javac --release 17 và java -cp.

## 29. Checklist trước khi tin một cache hit

- [ ] Task được chọn đúng trong graph.
- [ ] Không đồng nhất UP-TO-DATE với FROM-CACHE.
- [ ] NO-SOURCE/SKIPPED không bị diễn giải thành kiểm thử thành công.
- [ ] Build cache bật bằng flag hoặc property phù hợp.
- [ ] Cacheable task có inputs/outputs đầy đủ và validation sạch.
- [ ] Output không phụ thuộc clock/random/network/environment chưa khai báo.
- [ ] Output nằm trong directory do task sở hữu.
- [ ] Path normalization đúng với semantics.
- [ ] Java toolchain/compiler flags/classpath được theo dõi.
- [ ] Custom task có @CacheableTask khi thật sự deterministic.
- [ ] Caching không được áp dụng tùy tiện cho publish/deploy.
- [ ] Cache output không chứa secrets hoặc PII trái policy.
- [ ] Test tasks phụ thuộc external state được cô lập hoặc tắt cache.
- [ ] Có thí nghiệm hai lần cùng input cho UP-TO-DATE.
- [ ] Có thí nghiệm clean rồi cache restore.
- [ ] Có thí nghiệm đổi input và quay về input cũ.
- [ ] --rerun-tasks --no-build-cache dùng để kiểm chứng action khi cần.
- [ ] Không dùng clean/rerun thường xuyên thiếu lý do.
- [ ] Phân biệt configuration cache và dependency cache.
- [ ] Local cache retention và disk usage được quản lý.
- [ ] Remote cache dùng TLS, auth và least-privilege writers.
- [ ] Untrusted PR/fork không được poison trusted cache.
- [ ] Build artifact/test report được kiểm tra bằng bytes và counts.
- [ ] CI không che test failures vì cache/skip.
- [ ] Công cụ đo tính performance xét cả restore/store cost.
- [ ] Gradle Wrapper/JDK/plugin versions tương thích giữa các environments.
- [ ] Cache correctness được kiểm tra trên fresh/relocated workspaces.

## 30. Tài liệu chính thức

- [Gradle — Incremental Builds and Build Caching](https://docs.gradle.org/current/userguide/gradle_optimizations.html)
- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html)
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle — Important Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html)
- [Gradle — Debugging Build Cache Misses](https://docs.gradle.org/current/userguide/build_cache_debugging.html)
- [Gradle — Understanding Tasks](https://docs.gradle.org/current/userguide/more_about_tasks.html)
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html)
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html)
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html)

**Kết luận:** **UP-TO-DATE** có nghĩa Gradle **không cần chạy lại vì outputs hiện tại còn hợp lệ**. **FROM-CACHE** có nghĩa Gradle **không chạy actions mà phục hồi outputs từ build cache**. Hai cơ chế khác nhau nhưng bổ trợ: incremental up-to-date checks tận dụng kết quả đang có, build cache mang kết quả từ các builds/workspaces trước đến nơi cần chúng. Muốn sử dụng đúng, phải khai báo đầy đủ task inputs/outputs, chỉ cache công việc deterministic, dùng đúng flags, hiểu clean không xóa cache và đọc outcomes/actual files thay vì suy diễn từ tốc độ build.
