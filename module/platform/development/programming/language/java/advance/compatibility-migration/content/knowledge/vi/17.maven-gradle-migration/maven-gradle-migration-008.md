# Nâng cấp plugin build, plugin nội bộ và script không còn tương thích

Một dự án Java có thể dùng mã nguồn hợp lệ, dependency runtime đúng và compiler target phù hợp nhưng vẫn **không build được sau khi đổi JDK hoặc nâng Maven/Gradle**. Nguyên nhân thường nằm ở lớp công cụ: plugin biên dịch, plugin test, plugin đóng gói, annotation processor, plugin nội bộ, script Groovy/Kotlin, shell script CI hoặc cấu hình đã dựa vào những API và hành vi cũ của build tool.

Ví dụ, ứng dụng đang chuyển từ JDK 17 lên 21 nhưng Gradle Wrapper chưa hỗ trợ chạy bằng JDK 21; một plugin bytecode enhancement chưa nhận diện class-file version mới; script tự viết gọi một API Gradle đã bị xóa; hoặc plugin Maven được compile cho JDK cao hơn JVM đang chạy Maven. Tất cả có thể thất bại **trước khi ứng dụng được thực thi**. Một số lỗi chỉ xuất hiện ở CI sạch, khi bật configuration cache, trên Windows, trong Docker hoặc tại task tạo package.

Trong Java Advance Compatibility Migration, cần xem **build system là một chương trình phần mềm độc lập có runtime, dependency graph và vòng đời nâng cấp riêng**. Bài học này hướng dẫn kiểm kê, nâng cấp và kiểm chứng các plugin build, plugin nội bộ và script cũ trên Maven/Gradle mà không nhầm lẫn với compatibility của application runtime.

## 1. Các lớp phiên bản phải tách biệt

Một build Java thực tế thường có nhiều phiên bản độc lập:

| Lớp | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| JDK chạy build tool | JVM chạy Gradle Daemon hoặc Maven | Build tool và plugin có chạy được trên JDK này? |
| Maven/Gradle distribution | Maven Wrapper, Gradle Wrapper | Phiên bản build tool có hỗ trợ JVM, DSL, plugin API mới? |
| Compiler/toolchain | JDK mà `javac` hoặc compiler task chọn | Source được compile bằng compiler nào? |
| Target language/API | `--release 17` hoặc `--release 21` | Artifact đầu ra phải hỗ trợ runtime nào? |
| Build plugins | Compiler, test, codegen, shading, publishing | Plugin có tương thích build tool và JVM chạy plugin? |
| Internal plugins | Convention plugin, plugin nội bộ phát hành JAR | Có phụ thuộc API nội bộ hoặc được build cho JDK quá mới? |
| Build scripts | `pom.xml`, `build.gradle`, `build.gradle.kts` | DSL và task wiring có còn hợp lệ? |
| Plugin/tool dependencies | ASM, Groovy, Kotlin, generator, formatter | Runtime classpath riêng của plugin có đúng không? |
| Test JVM | JVM do Surefire/Failsafe hoặc Gradle Test task sử dụng | Test có chạy trên JDK mục tiêu? |
| Production JVM | JRE/container chạy ứng dụng | Artifact và dependency runtime có tương thích? |

Điểm quan trọng: **Nâng JDK dùng để compile source không tự nâng Gradle, Maven hoặc các plugin**. Ngược lại, nâng Gradle Wrapper không tự nâng runtime của ứng dụng.

Nếu Gradle Daemon đang chạy bằng JDK 17, một plugin nội bộ được biên dịch thành class file Java 21 có thể ném `UnsupportedClassVersionError` ngay khi plugin được nạp, dù dự án muốn compile application bằng toolchain JDK 21. Đây là vấn đề ở *plugin runtime*, không phải ở bytecode của application.

## 2. Mô hình chạy build: Maven và Gradle khác nhau

### 2.1. Maven: core, plugin realm và forked process

Maven chạy bằng một JVM được chọn qua `JAVA_HOME`, Maven Wrapper hoặc môi trường thực thi. Maven core đọc POM, giải quyết lifecycle và nạp plugin theo cơ chế class realm riêng.

Một plugin như `maven-compiler-plugin`, `maven-surefire-plugin` hay một Mojo nội bộ có thể:

- Chạy trong JVM của Maven.
- Nạp dependency chỉ thuộc plugin realm.
- Khởi chạy process/forked JVM khác để compile hoặc test.
- Sử dụng Toolchains để chọn một JDK khác cho bước cụ thể.

Vì vậy cần kiểm tra riêng JVM chạy Maven, JDK compiler, JVM test và dependency của plugin. Chỉ xem `java -version` trong terminal chưa chắc nói được Maven fork/test dùng JDK nào.

### 2.2. Gradle: client, Daemon, plugins và toolchains

Gradle Wrapper chọn distribution; Gradle Daemon chạy bằng một JVM cụ thể. Gradle plugin được nạp vào build runtime, sử dụng Gradle API và dependency classpath riêng theo cách plugin được khai báo. Java toolchains có thể chọn compiler, test launcher hoặc executable khác với JDK của Daemon.

Ví dụ:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Cấu hình trên có thể cho phép compiler JDK 21 tạo bytecode và giới hạn API Java 17, **nhưng không chứng minh Gradle Daemon đang chạy bằng JDK 21**. Ngược lại, nếu Daemon chạy JDK 21 mà một plugin nội bộ chỉ tương thích với Gradle API cũ, plugin vẫn có thể lỗi trong configuration phase.

Gradle Wrapper, plugin portal, settings plugin, convention plugin và application dependencies là các lớp riêng cần điều tra.

### 2.3. Bảng lỗi theo vị trí

| Khi lỗi xuất hiện | Vùng cần xem trước | Ví dụ triệu chứng |
|---|---|---|
| Trước khi Gradle cấu hình project | Wrapper/JDK/Gradle distribution | Unsupported Java runtime hoặc lỗi Groovy/Kotlin init |
| Ngay khi apply plugin | Plugin binary, Gradle API, plugin dependency | `NoSuchMethodError` ở Gradle internal class |
| Trong Maven plugin execution | Mojo, plugin realm, plugin dependency | `PluginExecutionException`, `ClassNotFoundException` |
| Trong compile task | Compiler/toolchain, processor, source level | `invalid target release` hoặc processor failure |
| Trong test task | Test runner, mocking/agent, test JVM | Discovery failure, bytecode instrumentation error |
| Trong code generation | Generator/tooling và schema inputs | Main class không tìm thấy, output không được đăng ký |
| Trong package/shadow/shade | Archive API, resource merging, bytecode tooling | Service metadata mất, class version không được hiểu |
| Chỉ trên CI | JDK/OS/script/cache/environment | `JAVA_HOME`, path quoting, credentials, daemon |
| Chỉ ở production | Application runtime/dependency | Lỗi linkage từ JAR đã đóng gói |

Một thông báo lỗi có thể bộc lộ tại task sau nhưng nguyên nhân từ configuration phase trước. Cần đọc *stack trace đầu tiên* và toàn bộ chuỗi `Caused by` thay vì chỉ xem dòng cuối.

## 3. Kiểm kê build trước khi thay version

### 3.1. Những file cần nhận diện

Với Maven, thường là:

```text
.mvn/wrapper/maven-wrapper.properties
.mvn/maven.config
.mvn/jvm.config
pom.xml
parent-pom/pom.xml
module-a/pom.xml
module-b/pom.xml
settings.xml (nếu được quản lý riêng ở CI/user)
```

Với Gradle:

```text
gradle/wrapper/gradle-wrapper.properties
settings.gradle hoặc settings.gradle.kts
build.gradle hoặc build.gradle.kts
gradle.properties
gradle/libs.versions.toml
buildSrc/
build-logic/ hoặc included builds
convention-plugins/
init scripts ở CI/user Gradle home
```

Ngoài ra cần kiểm tra shell script, PowerShell, batch file, Dockerfile, CI pipeline, container image, task code generation, publication và quality gate.

Đây là danh sách nơi cần khảo sát về mặt phương pháp. Trong mỗi nhiệm vụ thực tế, chỉ đọc/đụng các file được giao quyền và phạm vi phù hợp; không giả định mọi repository đều có cấu trúc này.

### 3.2. Plugin inventory phải mô tả nhiều chiều

Một bảng kiểm kê hữu ích:

| Plugin/task | Version hiện tại | Nguồn khai báo | JVM chạy | API phụ thuộc | Owner |
|---|---|---|---|---|---|
| Compiler plugin | Từ parent/pluginManagement | Maven build | Maven JVM hoặc compiler fork | Maven Compiler API, `javac` | Build team |
| Test runner | Được ghim trực tiếp | Maven/Gradle | Forked test JVM | JUnit, agents, instrumentation | QA |
| Shadow/shade | Plugin portal/repo | Build runtime | Gradle Daemon/Maven JVM | Archive, transformer | Platform |
| XJC/OpenAPI codegen | Build plugin | Generator JVM | External tool | JAXB, schemas | Domain team |
| Internal conventions | Included build hoặc artifact | Gradle Daemon | Gradle API, Kotlin/Groovy DSL | Build platform |
| Release/publish | CI profile | Build runtime/CI | Repository credentials, signing | Release team |

Cần ghi cả plugin bị **apply gián tiếp**. Một parent POM có thể tự cấu hình lifecycle plugin; một Gradle settings plugin hoặc convention plugin có thể apply plugin khác. Version catalog có thể đặt alias nhưng version được resolution thực tế còn phụ thuộc plugin management strategy.

### 3.3. Lệnh điều tra tham khảo

Maven:

```bash
./mvnw -version
./mvnw help:effective-pom
./mvnw help:effective-settings
./mvnw dependency:tree
```

Gradle:

```bash
./gradlew --version
./gradlew projects
./gradlew help --stacktrace
./gradlew buildEnvironment
```

Lưu ý đây là các lệnh minh họa để sử dụng trong quy trình migration, **không phải yêu cầu chạy ngay khi soạn tài liệu**. Trên Windows dùng `mvnw.cmd` hoặc `gradlew.bat` nếu phù hợp. `buildEnvironment` phản ánh một số classpath buildscript nhưng không đủ để mô tả mọi plugin từ Plugin DSL hoặc included build; xem `pluginManagement` và từng plugin declaration để hoàn thiện inventory.

## 4. Thứ tự nâng cấp: đừng thay toàn bộ cùng lúc

Một hướng giảm rủi ro là chia tiến trình:

1. **Chụp baseline**: JDK cũ, Wrapper, plugin versions, dependency graph, test/report và artifact checksum.
2. **Xác định target matrix**: JDK chạy build, JDK compiler, JDK runtime, Maven/Gradle và plugin.
3. **Nâng Wrapper nếu cần**: chọn distribution hỗ trợ JVM mục tiêu và được tổ chức chấp thuận.
4. **Nâng plugin ngoài**: compiler, test, codegen, shading, quality/security, publish.
5. **Sửa plugin nội bộ và build scripts**: thay API/DSL deprecated, lifecycle và lazy configuration.
6. **Kiểm chứng cấu hình và compilation**: module main, test, generated source.
7. **Kiểm chứng package và runtime**: chạy artifact thật trên JDK đích.
8. **Thêm CI matrix, rollback và guardrail**: giữ bằng chứng theo commit.

Một số bước có thể phải gộp vì plugin mới yêu cầu build tool mới và build tool mới chỉ hỗ trợ JDK nhất định. Hãy ghi **dependency giữa bước nâng cấp** trước khi quyết định thứ tự; không mặc định có thể nâng plugin độc lập trong mọi trường hợp.

Mục tiêu là giảm số biến thay đổi đồng thời, không phải cứng nhắc giữ một tool cũ đã hết hỗ trợ.

## 5. Nâng Gradle Wrapper và tương thích JDK

### 5.1. Wrapper là điểm neo của bản Gradle

File `gradle/wrapper/gradle-wrapper.properties` quy định distribution URL:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-<approved-version>-bin.zip
```

Phần `<approved-version>` là placeholder. Không thay trực tiếp bằng một số phiên bản tùy tiện rồi mặc định hoạt động. Cần đối chiếu bảng hỗ trợ **JDK dùng chạy Gradle** với JDK **toolchain/compiler được hỗ trợ** ở bản Gradle mục tiêu.

Ở các release Gradle, hỗ trợ dùng một JDK làm toolchain có thể xuất hiện trước khi hỗ trợ chạy chính Gradle Daemon bằng JDK đó. Vì vậy các câu hỏi “Gradle này compile Java 21 được không?” và “Gradle này chạy trên Java 21 được không?” có thể có câu trả lời khác nhau.

### 5.2. Quy trình cập nhật Wrapper

Trong môi trường được phép chạy build, thường dùng task Wrapper do Gradle cung cấp:

```bash
./gradlew wrapper --gradle-version <approved-version>
```

Tùy tình trạng Wrapper cũ, cần dùng một JDK tương thích để khởi động Gradle cũ trước khi cập nhật. Kiểm tra và commit những thay đổi Wrapper được tạo ra (script, JAR và properties) theo chính sách repository; không chỉ commit URL nếu quy trình yêu cầu đồng bộ Wrapper files.

Trong môi trường có chính sách supply chain, cấu hình và xác minh distribution checksum (ví dụ `distributionSha256Sum` nếu hỗ trợ) theo tài liệu chính thức, kiểm tra URL nguồn và tránh sử dụng bản phân phối không được tổ chức chấp thuận.

### 5.3. Không ép Daemon và compiler luôn cùng JDK

Một cấu hình an toàn khi cần hỗ trợ application Java 17 nhưng dùng compiler JDK 21 có thể là:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Cần xác minh bản Gradle chạy với JDK Daemon đã chọn, đồng thời hỗ trợ toolchain Java 21. `options.release` giúp giới hạn language/bytecode/platform API cho Java source compilation đó, nhưng không điều chỉnh plugin binary hoặc Kotlin/Groovy compiler task riêng.

### 5.4. Dấu hiệu Gradle Wrapper quá cũ

- Build thất bại ngay khi daemon khởi động trên JDK mới.
- Groovy/ASM trong distribution không hiểu class-file major version của JDK.
- Plugin DSL hoặc Kotlin DSL biên dịch thất bại vì tổ hợp Gradle/JDK không được hỗ trợ.
- Java toolchain không nhận JDK mới.
- Cảnh báo hoặc lỗi API đã bị xóa khi nâng qua nhiều major version.
- Configuration cache hoặc property validation không tương thích với script/plugin hiện tại.

Không sửa các lỗi này bằng cách hạ source/target compatibility của application; chúng ở tầng build runtime và build tool API.

## 6. Maven Wrapper, Maven runtime và plugin compatibility

### 6.1. Maven Wrapper và Maven core

Maven Wrapper giúp repository chọn bản Maven được chốt. Tuy nhiên, Maven core có minimum supported Java version và một số plugin có minimum Java/Maven version riêng. Hãy xác minh ba điều kiện:

1. Maven distribution chạy được trên JDK mục tiêu.
2. Plugin version hỗ trợ Maven core đang dùng.
3. Plugin và dependency của plugin chạy được trên JVM của Maven.

Ví dụ, một Maven plugin mới được compile với Java 21 không thể chạy trong Maven JVM Java 17 chỉ vì application compiler đang dùng toolchain Java 21.

### 6.2. PluginManagement không phải dependencyManagement

Maven dependency BOM thường quản lý dependency của project; plugin versions nằm ở `pluginManagement` hoặc `build/plugins`.

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>${compiler.plugin.version}</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${surefire.plugin.version}</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Các properties là placeholders cần được định nghĩa, và version chọn theo compatibility matrix của JDK/Maven/framework. Nếu plugin chưa được kích hoạt ở `build/plugins` hoặc lifecycle binding phù hợp, chỉ khai báo `pluginManagement` không đảm bảo mọi goal sẽ chạy.

### 6.3. Compiler Plugin: tách build JDK và target release

Ví dụ:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Khi compiler chạy bằng JDK phù hợp và hỗ trợ `--release`, cấu hình này hướng tới class-file và API Java 17. Nhưng compiler plugin version vẫn cần tương thích Maven/JDK, và annotation processors có thể chạy trong compiler process với compatibility constraints riêng.

Nếu ứng dụng cần dùng API Java 21, chọn release 21 và kiểm tra các module consumer. Không đặt `release=17` rồi cố gọi `Thread.ofVirtual()` bằng cách hack bootclasspath.

### 6.4. Surefire và Failsafe

Maven Surefire/Failsafe cần version hỗ trợ test framework, JVM mục tiêu và cơ chế fork. Các tình huống hay gặp:

- Test không được discovery do JUnit Platform/provider không phù hợp.
- Forked JVM thất bại ngay khi nạp test agent hoặc bytecode instrumentation.
- Plugin cũ không hiểu option JVM mới hoặc class-file version.
- Test process dùng JDK khác Maven JVM ngoài dự kiến.
- `argLine` không được truyền đúng sau khi thêm JaCoCo hoặc instrumentation.
- Integration tests không chạy do execution phase hoặc plugin configuration đổi.

Một build “SUCCESS” nhưng chạy **0 tests** không chứng minh compatibility. Cần đọc test reports, test count, skipped tests và các task/goal thực sự được thực hiện.

## 7. Nâng plugin Gradle bên ngoài

### 7.1. Plugin DSL và plugin repositories

Một project Gradle có thể khai báo:

```groovy
plugins {
    id "com.example.static-analysis" version "2.4.0"
}
```

Ví dụ plugin/version mang tính giả định. Plugin resolution có thể đi qua Gradle Plugin Portal, corporate mirror hoặc custom repository được cấu hình tại `settings.gradle(.kts)` trong `pluginManagement`:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
        maven {
            url = uri("https://repo.example.org/gradle-plugins")
        }
    }
}
```

Địa chỉ repository ở ví dụ chỉ minh họa. Trong thực tế cần sử dụng URL, credential và policy chính thức. Nếu plugin marker artifact không được publish hoặc mirror thiếu marker/module, Gradle có thể báo không tìm được plugin dù implementation JAR đã tồn tại.

### 7.2. Version catalog cho plugin aliases

```toml
[versions]
quality-plugin = "2.4.0"

[plugins]
quality = { id = "com.example.static-analysis", version.ref = "quality-plugin" }
```

Trong build script:

```kotlin
plugins {
    alias(libs.plugins.quality)
}
```

Version catalog giảm số nơi gõ version; nó không tự giải quyết Gradle API compatibility, runtime JDK requirement hoặc version conflict bên trong plugin classpath.

### 7.3. Khi nâng plugin qua major version

Đọc release notes và xác định:

- Minimum Gradle version và JDK chạy plugin.
- Plugin ID có đổi không.
- Extension/task/property names có đổi không.
- Task cũ có bị xóa hoặc thay thế không.
- Configuration name và default behavior có đổi không.
- Plugin đã chuyển từ eager sang lazy property API chưa.
- Report paths/output types, publication format hoặc cache behavior thay đổi không.
- Plugin có còn hỗ trợ project multi-module và configuration cache không.

Đừng chỉ đổi version rồi áp dụng mọi đề xuất “quick fix” từ internet mà không biết plugin đang được dùng theo lifecycle nào.

## 8. API Gradle cũ và migration sang Provider API

### 8.1. Lỗi do API Gradle bị deprecated hoặc removed

Gradle phát triển DSL và API qua nhiều release; plugin tự viết có thể dùng property, method hoặc convention cũ không còn được hỗ trợ. Những pattern dễ gặp:

- Truy cập `Project` và task model từ thời điểm configuration không phù hợp.
- Dùng `afterEvaluate` để vá task đã được plugin khác tạo.
- Dùng task/property API đã deprecated.
- Tạo task bằng cấu hình eager ở hàng loạt subprojects.
- Đọc môi trường và file trong configuration phase mà không khai báo inputs.
- Ghi output trực tiếp vào source directory không khai báo outputs.
- Tự tạo task graph bằng `dependsOn` trên tên task hoặc path hardcoded.

Không phải pattern nào cũng bị cấm tuyệt đối. Nhưng khi nâng Gradle, cần chuyển sang API được khuyến nghị và xác định rõ **configuration time** so với **execution time**.

### 8.2. Tránh eager task creation khi không cần

Cách cũ:

```groovy
task generateInfo {
    doLast {
        println "Generating..."
    }
}
```

Một hướng hiện đại hơn:

```groovy
tasks.register("generateInfo") {
    group = "generation"
    description = "Generate a build-info file"

    doLast {
        println "Generating..."
    }
}
```

`tasks.register` tạo task provider và thường giúp lazy configuration. Khi code cần tham chiếu task, ưu tiên provider thay vì buộc task được realize quá sớm.

Ví dụ:

```groovy
def generateInfoTask = tasks.register("generateInfo") {
    doLast {
        println "Generating..."
    }
}

tasks.named("processResources") {
    dependsOn(generateInfoTask)
}
```

Đây là minh họa dependency task. Nếu task tạo file và task khác tiêu thụ nó, nên mô hình hóa output/input provider thay vì chỉ `dependsOn` mà không chỉ rõ artifact.

### 8.3. Task input/output rõ ràng

Một plugin nội bộ tạo file có thể định nghĩa task type:

```java
import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.TaskAction;

public abstract class GenerateBuildInfo extends DefaultTask {
    @Input
    public abstract Property<String> getApplicationName();

    @OutputFile
    public abstract RegularFileProperty getOutputFile();

    @TaskAction
    public void generate() throws java.io.IOException {
        java.io.File file = getOutputFile().get().getAsFile();

        java.nio.file.Files.createDirectories(
            file.toPath().getParent()
        );

        String value = getApplicationName().get() + System.lineSeparator();

        java.nio.file.Files.writeString(
            file.toPath(),
            value,
            java.nio.charset.StandardCharsets.UTF_8
        );
    }
}
```

Trong plugin application:

```java
project.getTasks().register(
    "generateBuildInfo",
    GenerateBuildInfo.class,
    task -> {
        task.getApplicationName().set("order-service");
        task.getOutputFile().set(
            project.getLayout()
                .getBuildDirectory()
                .file("generated/build-info.txt")
        );
    }
);
```

Mẫu này cho Gradle biết input và output để theo dõi thay đổi tốt hơn. Tuy nhiên, muốn task tương thích configuration cache/build cache, cần kiểm tra toàn bộ state, file system interactions và cách truyền provider vào task. Một task hợp lệ về input/output chưa tự động cacheable.

### 8.4. Vì sao `project` trong task action có thể gây vấn đề?

Một closure/task action phụ thuộc trực tiếp vào `project`, script instance hoặc object không serializable có thể vi phạm yêu cầu của Gradle configuration cache. Plugin hiện đại nên truyền dữ liệu cần thiết qua typed properties và provider, thay vì truy cập model lúc execution.

Thay vì:

```groovy
tasks.register("badTask") {
    doLast {
        println project.name
    }
}
```

nên tạo giá trị input tại configuration phase và sử dụng property của task type hoặc provider theo API được hỗ trợ. Chi tiết triển khai cần kiểm tra theo Gradle version, vì một số dạng closure và implicit capture hoạt động khác nhau giữa Groovy DSL, Kotlin DSL và plugin code.

## 9. Configuration cache, build cache và incremental build

### 9.1. Ba khái niệm khác nhau

- **Configuration cache** lưu kết quả cấu hình build để những lần chạy tương thích không phải cấu hình lại toàn bộ dự án.
- **Build cache** có thể tái sử dụng output của các task cacheable với input tương đương.
- **Incremental build** giúp bỏ qua hoặc xử lý phần thay đổi khi task inputs/outputs không đổi theo điều kiện.

Một plugin có thể chạy thành công bình thường nhưng lỗi khi bật configuration cache vì giữ tham chiếu đến `Project`, đọc environment không được theo dõi hoặc truy cập configuration state trong task action.

### 9.2. Những hành vi plugin dễ gây lỗi cache

- Đọc biến môi trường hoặc file cấu hình tại configuration phase mà không khai báo dependency phù hợp.
- Dùng static mutable state để lưu thông tin xuyên build.
- Giữ `Project`, `Gradle` hoặc service không được hỗ trợ trong task action.
- Thực thi external process không khai báo input/output.
- Tạo file trong configuration phase.
- Ghi trực tiếp vào thư mục source hoặc output của task khác.
- Dựa vào timestamp hoặc network response không được quản lý.
- Sử dụng listener/callback không tương thích với phiên bản Gradle/cache mode.

Không nên sửa bằng cách tắt toàn bộ cache vĩnh viễn nếu mục tiêu dài hạn là reproducible và nhanh. Có thể tạm tắt có ghi nhận rủi ro để unblock migration, nhưng cần backlog nâng plugin và kiểm tra lại theo chính sách.

### 9.3. Mô hình hóa external tool execution

Nếu một task gọi XJC, protoc, OpenAPI Generator hoặc CLI khác, hãy ghi rõ:

- Executable/tool version.
- Tool classpath hoặc executable location.
- Input schemas/config.
- Output directory.
- JDK hoặc runtime dùng chạy tool.
- Environment variables ảnh hưởng output.
- Working directory và encoding.
- Các nguồn external network nếu không thể tránh.

Task có side effect không được khai báo có thể bị cache sai hoặc chạy không như dự kiến khi Gradle đổi task graph.

## 10. Nâng plugin nội bộ trong Gradle

### 10.1. Ba hình thức thường gặp

| Hình thức | Đặc điểm | Rủi ro migration |
|---|---|---|
| `buildSrc` | Tự động tham gia build logic của repository | Thay đổi có thể ảnh hưởng mọi project, compile JDK riêng |
| Included build `build-logic` | Build riêng cung cấp convention plugins | Plugin API/JDK và dependency riêng |
| Published binary plugin | Artifact có plugin marker và implementation JAR | Binary compatibility, repository, classloader, release management |

Precompiled script plugin cũng là build logic. Kotlin/Groovy DSL trong đó có thể cần nâng cú pháp hoặc dependency khi Gradle/Kotlin embedded versions thay đổi.

### 10.2. Build logic cần version matrix riêng

Ví dụ tổ chức chạy Gradle Daemon trên JDK 17 nhưng dùng toolchain JDK 21 cho application. Nếu build logic được compile thành bytecode 21, Gradle Daemon JDK 17 không nạp được plugin.

Do đó, với published plugin nội bộ cần ghi:

- JDK tối thiểu để chạy plugin.
- Gradle version range được hỗ trợ.
- Java/Groovy/Kotlin bytecode target của plugin.
- Phiên bản Gradle API mà plugin được compile/test.
- Internal dependencies của plugin, nhất là ASM, Kotlin, Groovy.
- Có dùng Gradle internal APIs không.
- Test matrix với các phiên bản Gradle còn được hỗ trợ.

Không đồng nhất target Java của application với target Java của plugin. Chúng có thể khác, và chính sách của plugin thường cần hỗ trợ nhiều project/runtime.

### 10.3. Plugin ID và semantic versioning

Nếu plugin nội bộ được publish:

```groovy
plugins {
    id "com.example.build.java-conventions" version "3.0.0"
}
```

thì plugin ID và version là interface với consumer. Đổi plugin ID làm consumer không resolve được plugin nếu không cập nhật build scripts; đổi task/extension names cũng là source/build-script breaking change.

Plugin versioning cần migration notes giống library API:

- Plugin ID và marker artifact.
- Minimum Gradle/JDK requirements.
- Extension DSL cũ/mới.
- Task names, arguments và lifecycle changes.
- Default configurations.
- Binary compatibility với build logic consumer.
- Publishing/mirror requirements.

### 10.4. Tránh dựa vào Gradle internal APIs

Plugin có thể từng dùng các class nằm trong package `org.gradle.internal.*` hoặc API không được công bố ổn định. Khi Gradle nâng major version, các class/method này có thể bị đổi/xóa, làm phát sinh `NoClassDefFoundError`/`NoSuchMethodError` ngay khi apply.

Hướng sửa bền vững là chuyển sang public Gradle API hoặc extension point được hỗ trợ. Dùng reflection vào internal API hoặc `--add-opens` để buộc plugin cũ hoạt động chỉ là giải pháp tạm có rủi ro cao, không phải chiến lược lâu dài.

### 10.5. Convention plugin thay cho script lặp lại

Nếu nhiều module copy chung đoạn build script, có thể tách cấu hình thành convention plugin:

```groovy
// Cấu trúc minh họa tại plugin nội bộ
class JavaConventionsPlugin implements Plugin<Project> {
    void apply(Project project) {
        project.getPluginManager().apply("java");

        project.getTasks().withType(JavaCompile.class)
            .configureEach(task ->
                task.getOptions().getRelease().set(17)
            );
    }
}
```

Cần import các Gradle API classes và cấu hình plugin packaging đúng. Mã ví dụ thể hiện ý tưởng, không phải implementation đầy đủ cho mọi Gradle version.

Lợi ích là một nơi kiểm soát JDK policy, compiler flags, test conventions và report outputs. Rủi ro là mọi module cùng phụ thuộc plugin này; thay đổi cần có test fixture và rollout theo version.

## 11. Nâng plugin Maven nội bộ

### 11.1. Maven Mojo là code chạy trong plugin runtime

Một plugin nội bộ thường dùng Maven Plugin API/annotations để khai báo goal (Mojo). Ví dụ:

```java
import org.apache.maven.plugin.AbstractMojo;
import org.apache.maven.plugin.MojoExecutionException;
import org.apache.maven.plugins.annotations.Mojo;
import org.apache.maven.plugins.annotations.Parameter;

@Mojo(name = "report-build-info")
public class ReportBuildInfoMojo extends AbstractMojo {
    @Parameter(property = "app.name", defaultValue = "unknown")
    private String applicationName;

    @Override
    public void execute() throws MojoExecutionException {
        getLog().info("Application: " + applicationName);
    }
}
```

Mã ví dụ cần được đặt trong Maven plugin project có packaging, annotations và plugin descriptor generation phù hợp.

Khi nâng Maven/JDK, plugin nội bộ có thể lỗi vì:

- Compile target của plugin cao hơn JVM chạy Maven.
- Dùng Maven core/internal API không tương thích.
- Plugin descriptor không được sinh hoặc không khớp goal.
- Dependency của plugin conflict trong plugin realm.
- Reflection truy cập JDK internals bị chặn.
- Cách đọc project/session/repository thay đổi.
- Generator hoặc process invocation phụ thuộc OS/JDK cũ.

### 11.2. Quản lý dependency riêng của plugin

Ví dụ một Maven plugin có `pom.xml` riêng với:

```xml
<packaging>maven-plugin</packaging>

<dependencies>
    <dependency>
        <groupId>org.apache.maven</groupId>
        <artifactId>maven-plugin-api</artifactId>
        <version>${maven.plugin.api.version}</version>
        <scope>provided</scope>
    </dependency>
    <dependency>
        <groupId>org.apache.maven.plugin-tools</groupId>
        <artifactId>maven-plugin-annotations</artifactId>
        <version>${plugin.annotations.version}</version>
        <scope>provided</scope>
    </dependency>
</dependencies>
```

Đây chỉ là cấu trúc minh họa; version phải được chọn dựa trên Maven core/plugin tooling được hỗ trợ. Không lấy `maven-plugin-api` từ một phiên bản tùy ý chỉ vì ứng dụng production dùng JDK 21.

Plugin dependencies chạy trong plugin realm, khác với dependencies của project tiêu thụ plugin. Một library bị thiếu ở plugin realm không nhất thiết được giải quyết bằng cách thêm nó vào project `<dependencies>`.

### 11.3. Plugin test và Invoker test

Một plugin nội bộ nên có:

- Unit tests cho logic độc lập.
- Plugin testing harness hoặc fixture thích hợp để tạo Maven project/session giả lập.
- Maven Invoker-style integration tests để chạy plugin trên fixture project thật.
- Test với Maven/JDK versions được công bố hỗ trợ.
- Test malformed/missing config, multi-module, inherited POM và execution phases.
- Test artifact publication/plugin descriptor.

Không chỉ test method `execute()` bằng mock rồi kết luận plugin sẽ load đúng ở Maven release mới. Phải chạy ít nhất một consumer fixture thực tế.

## 12. Groovy và Kotlin DSL khi nâng Gradle

### 12.1. Groovy DSL có thể che lỗi đến runtime configuration

Groovy build scripts có khả năng dynamic dispatch. Một property hoặc method cũ đôi khi chỉ phát hiện lỗi khi script được thực thi trên Gradle mới:

```text
Could not find method someOldConfiguration() for arguments ...
```

Khi thấy lỗi này, kiểm tra task/plugin DSL đã đổi, object owner, plugin applied order và compatibility version. Không suy đoán đây là lỗi Java source.

### 12.2. Kotlin DSL có static typing nhưng vẫn phụ thuộc Gradle APIs

Kotlin DSL được biên dịch với Kotlin compiler/embedded APIs của Gradle distribution. Khi Gradle nâng, Kotlin DSL type-safe accessors, APIs hoặc những import cũ có thể không còn compile.

Ví dụ idiom sử dụng task provider:

```kotlin
tasks.register("showBuildInfo") {
    group = "help"

    doLast {
        println("Build info generated")
    }
}
```

Nếu một accessor không xuất hiện, có thể do plugin chưa apply đúng vị trí hoặc extension được tạo động không hỗ trợ cách truy cập như mong đợi. Đừng mặc định mọi lỗi Kotlin DSL là lỗi Kotlin language version.

### 12.3. Tránh tham chiếu thẳng vào implementation detail của DSL

Nếu script truy cập object nội bộ, extension private hoặc biến toàn cục bị phụ thuộc vào thứ tự apply plugin, một bản build tool mới có thể làm hành vi thay đổi. Chuyển sang:

- Public extension/task APIs.
- Typed providers/properties.
- Lazy task registration.
- Explicit plugin dependencies và plugin application.
- Convention plugin thay vì duplicate script magic.
- Version catalog và build logic được pin version.

Không nhất thiết chuyển tất cả Groovy DSL sang Kotlin DSL trong cùng đợt nâng JDK. Migration DSL là một thay đổi riêng, chỉ nên gộp nếu có lý do và kiểm chứng được.

## 13. Script shell, PowerShell và CI pipelines

### 13.1. Script ngoài build system có thể là nguồn bất tương thích

Một dự án có thể không dùng plugin đặc biệt nhưng script CI vẫn hardcode JDK:

```bash
export JAVA_HOME=/opt/jdk8
$JAVA_HOME/bin/xjc ...
$JAVA_HOME/bin/wsimport ...
```

Trên JDK 11+ những tool JAXB/JAX-WS không còn bundled trong JDK; script phải dùng generator bên ngoài với version được quản lý. Tương tự, script gọi `jre/bin/java` hoặc công cụ Java cũ có thể không còn phù hợp với layout của JDK mới.

Các dấu hiệu khác:

- `JAVA_HOME` hoặc `PATH` bị ghi đè ở một stage.
- Dùng lệnh Linux trong PowerShell hoặc `cmd.exe`.
- Path chứa dấu cách nhưng không quote.
- Script giả định `bash` có sẵn trên Windows.
- Hardcode đường dẫn cache/distro của Gradle.
- Gradle task rename nhưng pipeline vẫn gọi tên cũ.
- Maven goal/profile cũ bị xóa hoặc đổi execution.
- Script sử dụng Java options không còn được hỗ trợ.
- Dockerfile dùng base JDK image nhưng runtime stage thiếu CA/cert/tool.

### 13.2. Sử dụng Wrapper nhất quán

Trong repository có Wrapper, ưu tiên:

```bash
./gradlew build
./mvnw verify
```

Trên Windows:

```powershell
.\gradlew.bat build
.\mvnw.cmd verify
```

Wrapper giúp cố định build tool distribution theo repository. Nó không tự cố định JDK; JDK phải được quản lý ở CI, toolchain/Toolchains hoặc container image.

### 13.3. Quote path và xử lý exit code

Một script tốt cần truyền đường dẫn như argument riêng, không nối chuỗi shell tùy tiện. Ví dụ PowerShell:

```powershell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-21"
& "$env:JAVA_HOME\bin\java.exe" -version

if ($LASTEXITCODE -ne 0) {
    throw "Java command failed"
}
```

Lưu ý `$LASTEXITCODE` phản ánh native process gần nhất; trong script dài phải kiểm tra ngay sau lệnh cần quan sát. Với Bash, có thể dùng `set -euo pipefail` trong ngữ cảnh thích hợp, nhưng vẫn phải quản lý expected non-zero exits, pipelines và cleanup.

### 13.4. Không hardcode secrets trong scripts

Plugin publishing, artifact upload và signing cần credentials. Khi nâng plugin, cấu hình authentication có thể đổi. Không đặt token trong `build.gradle`, `pom.xml`, log CI hoặc source script.

Sử dụng secret store, CI credentials và provider/environment mechanisms phù hợp. Với Gradle, có thể dùng provider API để tránh đọc credentials sớm không cần thiết. Với Maven, dùng settings/server credentials theo chính sách tổ chức.

## 14. Plugin code generation và annotation processing

### 14.1. Generator là một toolchain riêng

XJC, JAX-WS, OpenAPI Generator, Protobuf, Avro, MapStruct và các annotation processors có thể có:

- Plugin/CLI version.
- Runtime JDK requirement.
- Input schema/API version.
- Generated source language level.
- Runtime dependency của generated code.
- Build plugin execution phase/task.
- Generated output directory.

Nâng JDK có thể khiến generator cũ không chạy, hoặc generator mới tạo source dùng API/annotation không khớp runtime. Ví dụ generator Jakarta tạo imports `jakarta.*`, còn dependency application vẫn dùng `javax.*`.

### 14.2. Generated source phải nằm trong source roots

Maven plugin có thể thêm generated sources vào compile source roots; Gradle task nên cung cấp output directory cho source set hoặc compiler task.

Với Gradle, ý tưởng:

```groovy
def generateApi = tasks.register("generateApi") {
    def outDir = layout.buildDirectory.dir("generated/sources/api/main")
    outputs.dir(outDir)

    doLast {
        // Gọi tool code generation tại execution time,
        // và ghi vào outDir đã khai báo.
    }
}

sourceSets {
    main {
        java.srcDir(layout.buildDirectory.dir("generated/sources/api/main"))
    }
}

tasks.named("compileJava") {
    dependsOn(generateApi)
}
```

Đây chỉ là mô hình task dependency; implementation thực tế cần định nghĩa inputs, tool classpath và tránh truy cập `project` trong task actions nếu muốn tương thích configuration cache. Tốt hơn là dùng plugin generator có public APIs được duy trì.

### 14.3. Đừng giữ generated output bẩn

Một build từng generate file cũ có thể tiếp tục compile vì output chưa bị xóa. CI sạch lại thất bại do generator mới không tạo file đó. Khi migration cần kiểm tra clean build trên môi trường độc lập.

Nếu source generated được commit trong repository, cần quy định version tool và quy trình regenerate có thể tái lập, tránh sửa trực tiếp file generated rồi mất thay đổi lần build sau.

## 15. Plugin kiểm thử và instrumentation trên JDK mới

### 15.1. Bytecode library không hiểu class-file version mới

Mocking framework, JaCoCo, Byte Buddy, ASM, Groovy/Kotlin compiler, coverage/instrumentation plugin và agent có thể đọc/sửa bytecode. Khi JDK nâng, class-file major version mới có thể vượt khả năng của phiên bản tooling cũ.

Triệu chứng có thể xuất hiện dưới dạng:

```text
Unsupported class file major version 65
```

Java 21 sử dụng class-file major version 65. Tuy nhiên, lỗi này có thể do **tool đọc class file** chưa hỗ trợ major 65, không nhất thiết do JVM runtime không hỗ trợ class đó.

Cách xử lý:

1. Xác định thư viện/plugin nào đang đọc class file.
2. Kiểm tra version thực tế trong plugin/test classpath.
3. Chọn bản tooling hỗ trợ JDK/bytecode mục tiêu.
4. Kiểm tra dependency conflict với ASM/Byte Buddy transitive.
5. Chạy lại coverage/mock/test instrumentation trên class file thực tế.

Không nên ép application bytecode xuống Java 17 chỉ để tránh nâng một plugin nếu sản phẩm thực sự cần Java 21 features.

### 15.2. Java agents và dynamic attach

JDK hiện đại có chính sách/cảnh báo liên quan dynamic agent loading. Trên JDK 21, JEP 451 cảnh báo về dynamic loading của agents trong một số tình huống. Một số test libraries dựa vào dynamic attach để bật inline mocking hoặc instrumentation.

Phân biệt:

- Startup agents được cấu hình qua `-javaagent`.
- Dynamic agent attach trong quá trình JVM đang chạy.
- Agent library có hỗ trợ JDK version/bytecode target.
- Policy của CI/container cho phép attach hay không.

Không tắt cảnh báo bảo mật hoặc mở quyền attach đại trà khi chưa xác định yêu cầu thực tế của test framework. Ưu tiên version framework/agent phù hợp và cấu hình startup agent khi được nhà cung cấp khuyến nghị.

### 15.3. Java 21 test compatibility không chỉ là JUnit

Nếu JUnit Platform mới hoạt động nhưng JaCoCo cũ thất bại, hoặc coverage pass nhưng Mockito agent lỗi, cần nâng những thành phần riêng. Các plugin không cùng một vòng đời release và không thể được giải quyết chỉ bằng BOM application nếu plugin realm khác.

## 16. Plugin quality, formatting, linting và publishing

### 16.1. Static analysis

Checkstyle, PMD, SpotBugs, Error Prone, Sonar tooling và các công cụ tương tự có khả năng phân tích source/bytecode khác nhau. Khi source level tăng:

- Tool parser có thể không hiểu cú pháp ngôn ngữ mới.
- Bytecode analyzer có thể không hiểu class-file version mới.
- Rule configuration cũ có thể bị deprecated/xóa.
- Baseline suppression file có thể không còn được chấp nhận.
- JDK runtime tối thiểu của tool thay đổi.

Không nên tắt toàn bộ quality gate chỉ vì tool cũ chưa hỗ trợ JDK. Có thể tách lộ trình cập nhật rules và tool version, lưu baseline cảnh báo và giải quyết các thay đổi được xác định.

### 16.2. Formatting

Một formatter nâng major version có thể thay output hàng trăm file dù source semantics không đổi. Tách commit format-only khỏi commit compatibility khi khả thi; ghim formatter version, IDE integration và CI hook thống nhất.

Nếu không thể tách, ghi rõ phạm vi formatting và không đánh đồng diff lớn với thay đổi logic.

### 16.3. Shading, shadowing và packaging

Plugin tạo fat JAR/uber-JAR có thể:

- Đổi task name hoặc archive property API.
- Thay behavior merge `META-INF/services`.
- Gây conflict duplicate classes.
- Relocate packages khác trước.
- Strip `Signature`, module metadata hoặc manifest attributes.
- Không nhận class-file version mới khi transform.
- Ghi đè artifact/publishing configuration.

Sau khi nâng plugin packaging, cần kiểm tra artifact thực tế: JAR contents, classpaths, services, module descriptor, startup và integration tests. Build thành công không chứng minh runtime JAR đúng.

### 16.4. Publishing và signing

Plugin publish có thể thay default repository, credentials API, publication metadata, POM/BOM conversion hoặc signing behavior. Cần xác nhận:

- Group/artifact/version và classifier.
- Gradle Module Metadata/Maven POM được tạo.
- Checksums/signatures và SBOM nếu có.
- Repository URL, staging, release/snapshot policy.
- Khả năng consumer resolve artifact từ mirror.
- Không publish nhầm file test/generated hoặc chứa secret.

Đừng coi bước publish là an toàn chỉ vì trước đây script chạy được. Nên dùng staging/test repository theo quy trình khi đổi release plugin.

## 17. Cách chẩn đoán các lỗi phổ biến

| Triệu chứng | Vùng nguyên nhân thường gặp | Bước xử lý đầu tiên |
|---|---|---|
| Gradle không khởi động trên JDK 21 | Wrapper/distribution chưa hỗ trợ JVM chạy Gradle | Xác minh bảng hỗ trợ Gradle-JDK, dùng Wrapper phù hợp |
| `UnsupportedClassVersionError` khi apply plugin | Plugin được compile cho JDK mới hơn Daemon/Maven JVM | Xác minh plugin major version và JVM thực thi |
| `NoSuchMethodError` với `org.gradle.*` | Plugin gọi Gradle API cũ/khác version | Xác định plugin, nâng hoặc sửa dùng public API |
| `NoClassDefFoundError` trong Maven plugin | Thiếu dependency ở plugin realm hoặc plugin binary lệch | Xem full `Caused by` và plugin dependencies |
| `Could not find method ...` trong Gradle | DSL/API/plugin extension cũ | Kiểm tra release notes và plugin apply order |
| `UnknownPluginException` | Plugin ID/marker/repository sai | Kiểm tra `pluginManagement` và repository mirror |
| `invalid target release: 21` | Compiler thực tế không phải JDK 21 | Kiểm tra toolchain/Toolchains và process JDK |
| `Unsupported class file major version 65` trong coverage | Bytecode tool cũ | Nâng agent/ASM/Byte Buddy/coverage plugin |
| Không có test nào chạy | Test provider/framework/lifecycle sai | Kiểm tra test reports, task/goal và test count |
| `Permission denied` trên `gradlew` | Script executable permission hoặc môi trường | Kiểm tra file mode và CI shell |
| `xjc`/`wsimport` không tìm thấy | JDK mới không bundled tool | Dùng generator bên ngoài đã pin version |
| Configuration cache failure | Task/plugin giữ state không hợp lệ | Sửa Provider API và task inputs |
| CI fail, local pass | JDK/OS/environment/credentials khác | So sánh environment matrix, wrapper và clean build |
| Fat JAR chạy lỗi nhưng unit test pass | Packaging/shading/provider metadata | Kiểm tra artifact cuối và runtime classpath |
| Plugin publish lỗi xác thực | Credential/repository config thay đổi | Kiểm tra secret injection và policy, không log token |

Đây là những hướng điều tra, không phải ánh xạ nguyên nhân tuyệt đối. Luôn đọc lỗi cụ thể và phiên bản thực tế.

## 18. Quy trình xử lý một plugin không tương thích

### Bước 1: Xác định plugin thực sự gây lỗi

Lấy exception đầu tiên với stack trace đầy đủ. Xác định plugin ID, group/artifact/version, task/goal, plugin realm/classloader và JDK chạy nó.

Gradle thường hỗ trợ:

```bash
./gradlew <task> --stacktrace --info
```

Maven thường hỗ trợ:

```bash
./mvnw <goal> -e
```

Chế độ debug chi tiết hơn có thể tiết lộ đường dẫn, repository, metadata và đôi khi secret nên chỉ dùng trong môi trường kiểm soát.

### Bước 2: Kiểm tra compatibility matrix của plugin

Đọc minimum/maximum Gradle/Maven/JDK requirements, release notes và migration guide. Không chọn version chỉ theo số mới nhất; chọn version **được hỗ trợ bởi stack đang mục tiêu hóa**.

### Bước 3: Phân loại loại lỗi

- Binary plugin không load được.
- Plugin load được nhưng configuration DSL lỗi.
- Task execution lỗi.
- Generated output không đúng.
- Test/package/publish output bị thay đổi.

Mỗi loại cần cách sửa khác nhau. Ví dụ lỗi plugin binary không load không thể sửa bằng thay `sourceCompatibility` của module chính.

### Bước 4: Đánh giá sửa trực tiếp hay thay plugin

Nếu plugin bên thứ ba không còn được duy trì:

1. Có version fork/vender patch được tổ chức hỗ trợ không?
2. Có plugin thay thế được bảo trì và hỗ trợ stack mục tiêu không?
3. Có thể chuyển logic sang API chuẩn của Gradle/Maven không?
4. Cần giữ output contract nào để consumer không bị ảnh hưởng?
5. Có rủi ro pháp lý, bản quyền, license hoặc bảo mật khi sử dụng bản fork không?

Nếu thay plugin, xem đó là một **thay đổi công cụ và output semantics**, không chỉ là đổi coordinate.

### Bước 5: Xác định thay đổi build script

Đổi extension/property/task/goal, loại bỏ deprecated APIs, cập nhật lazy configuration và build logic. Với Gradle, ưu tiên public Provider/Property APIs. Với Maven, cập nhật plugin executions và lifecycle bindings.

### Bước 6: Kiểm chứng từng tầng

- Plugin resolve.
- Plugin apply/configure.
- Task/goal thực thi.
- Output được tạo đúng.
- Source/generated source compile.
- Test framework/coverage chạy.
- Package artifact.
- Runtime smoke/integration.
- Publication metadata nếu có.

### Bước 7: Ghi migration note và rollback

Lưu version cũ/mới, lý do thay đổi, breaking DSL, output thay đổi, task name thay đổi, test report và hướng rollback. Plugin thường dùng bởi nhiều module nên cần thông báo consumer nội bộ.

## 19. Ví dụ xuyên suốt: Gradle plugin nội bộ sau khi nâng JDK

Giả sử repository gồm nhiều service dùng plugin `com.example.build.java-conventions`. Baseline: Gradle cũ, Daemon JDK 17, application target Java 17. Mục tiêu: build trên JDK 21 và một số service target Java 21.

### 19.1. Triệu chứng

Sau khi đổi Gradle Wrapper/JDK, build báo một lỗi tương tự:

```text
java.lang.NoSuchMethodError:
  '... org.gradle.api.internal...someOldMethod(...)'
```

Tên method trong ví dụ là placeholder. Stack trace trỏ tới JAR của plugin nội bộ. Điều này gợi ý plugin đang dùng API internal/khác phiên bản của Gradle.

### 19.2. Cách xử lý

1. Xác định version plugin nội bộ và Gradle API nó được compile dựa trên.
2. Kiểm tra `org.gradle.internal.*` hoặc các API đã deprecated trong source plugin.
3. Thay bằng API công khai, typed task properties và provider wiring.
4. Chốt JDK/bytecode target của **plugin runtime** riêng với application.
5. Test plugin trên Gradle distribution/JDK combinations được công bố hỗ trợ.
6. Tạo consumer fixture có task `compileJava`, `test`, `jar` và custom codegen.
7. Publish version plugin mới kèm migration note.
8. Nâng các service consumer theo từng nhóm, kiểm tra clean CI build và packaged artifact.

Nếu cần chuyển đổi task name/extension property, có thể giữ alias hoặc deprecation bridge trong một release chuyển tiếp. Nhưng không nên giữ mã gọi Gradle internal API đã bị xóa chỉ để tránh cập nhật consumer.

### 19.3. Phân biệt plugin JDK với application JDK

Một số service vẫn cần chạy Java 17. Plugin Gradle chạy trong Daemon JDK được chọn, còn compiler task có thể dùng toolchain JDK 21 với `options.release=17`. Cần đảm bảo plugin không vô tình buộc mọi service target Java 21 chỉ vì Daemon chạy trên 21.

Nên để convention plugin đọc cấu hình release từ extension hoặc convention có chủ đích, thay vì hardcode version theo JVM đang chạy Gradle.

## 20. Ví dụ xuyên suốt: Maven plugin cũ và generator

Một dự án SOAP/JAXB từng build trên JDK 8 bằng Maven plugin hoặc script gọi `JAVA_HOME/bin/wsimport`. Khi chuyển sang JDK 21, công cụ này không còn trong JDK và generated source không được tạo.

Một hướng migration:

1. Ghi WSDL/XSD, binding files và generated source baseline.
2. Chọn tool bên ngoài như JAX-WS RI tools hoặc CXF codegen theo framework.
3. Chọn thế hệ `javax.*` hoặc `jakarta.*` nhất quán với runtime.
4. Cấu hình Maven plugin goal trong phase `generate-sources`.
5. Pin version plugin/tool và dependency của generator.
6. Xác minh generated source roots, import và class names.
7. Compile lại với JDK target, chạy SOAP contract tests.
8. Kiểm tra plugin publish và artifact dependency metadata nếu shared client được phát hành.

Việc đổi generator có thể thay Java method signatures, annotations hoặc WSDL binding; cần xem diff và consumer compatibility. Không sửa generated source trực tiếp để che nguyên nhân.

## 21. CI matrix và release gates cho build tool migration

### 21.1. Chọn ma trận thực tế

Không nhất thiết test mọi tổ hợp JDK/Maven/Gradle/plugin. Nhưng cần ít nhất:

| Tổ hợp | Mục tiêu |
|---|---|
| Build tool cũ + JDK cũ | Baseline để tái hiện |
| Build tool mới + JDK được hỗ trợ | Xác nhận plugin/DSL/tooling |
| Compiler JDK mới + target release cũ (nếu cần) | Giữ runtime compatibility |
| Test JVM mục tiêu | JUnit/agent/coverage integration |
| Runtime production JDK | Chạy artifact cuối |
| Windows/Linux (nếu hỗ trợ cả hai) | Shell/path/script portability |

Nếu plugin nội bộ được công bố hỗ trợ nhiều Gradle releases, cần test nó với từng dòng release được cam kết; không chỉ với bản Gradle của repository tạo plugin.

### 21.2. Các cổng trước khi chấp nhận nâng cấp

1. Wrapper checksum/version và JDK được ghi lại.
2. Plugin resolution thành công từ repository được chấp thuận.
3. Không có plugin binary class-version errors.
4. Configuration phase hợp lệ và không dùng APIs đã bị xóa.
5. Compile cả main/test/generated source.
6. Test count/report hợp lệ; không có silent skip.
7. Coverage/quality gates chạy đúng.
8. Artifact package đúng, không mất `META-INF/services` hoặc resources.
9. Runtime smoke/integration trên JDK mục tiêu thành công.
10. Publication metadata/repository được kiểm chứng nếu pipeline publish.
11. Không ghi credential/token vào log.
12. Có release note, rollback hoặc kế hoạch xử lý lỗi.

### 21.3. Không biến mọi deprecation warning thành một blocker vô hạn

Trong giai đoạn nâng Gradle hoặc Maven, có thể xuất hiện warning từ plugin bên thứ ba chưa có version mới. Ghi warning theo owner, deadline và mức độ ảnh hưởng. Nếu warning báo API sắp bị xóa ở release kế tiếp, cần có kế hoạch thay thế trước khi nâng tiếp.

Không nên bỏ qua warning chỉ vì build đang pass; nó là dữ liệu quan trọng để ước lượng chi phí migration vòng sau.

## 22. Dependency và supply-chain security của plugins

Build plugins có quyền chạy code trong máy build, đọc file, dùng credential và truy cập network theo quyền tiến trình. Vì vậy nâng plugin không chỉ là compatibility mà còn là supply-chain decision.

Cần áp dụng:

- Plugin/version pin có chủ đích.
- Repository allowlist và corporate mirror.
- Kiểm tra checksum/signature khi hệ công cụ hỗ trợ.
- Review nguồn plugin, bảo trì và vulnerability history.
- Hạn chế quyền CI runner/secret exposure.
- Không chạy script remote không kiểm soát chỉ để cài plugin.
- Có khả năng tái tạo build từ Wrapper/plugin/dependency versions.
- Tách credentials của publish khỏi job chỉ cần compile/test.

Một plugin mới giải quyết được Java 21 compatibility nhưng chưa được kiểm tra nguồn gốc không mặc nhiên là lựa chọn an toàn. Các thay đổi dependency của plugin cũng cần được xem xét, đặc biệt nếu plugin kéo thêm toolchain hoặc thực thi binary bên ngoài.

## 23. Checklist nâng cấp plugin và script

### Kiểm kê

- [ ] Đã xác định JDK chạy Maven/Gradle, JDK compiler, JDK test và JDK runtime.
- [ ] Đã ghi Maven/Gradle Wrapper version và nguồn distribution.
- [ ] Đã lập danh sách plugins được khai báo trực tiếp/gián tiếp, gồm settings và convention plugins.
- [ ] Đã xác định plugin nội bộ trong `buildSrc`, included builds hoặc artifact repository.
- [ ] Đã kiểm tra script CI, shell, PowerShell, Dockerfile và process JDK.
- [ ] Đã ghi compatibility matrix Gradle/Maven/JDK/plugin versions.

### Nâng cấp cấu hình và mã build

- [ ] Wrapper version được chọn hỗ trợ JDK chạy build.
- [ ] Compiler, Surefire/Failsafe, test agent và bytecode tools hỗ trợ JDK mục tiêu.
- [ ] Gradle plugin không gọi API internal/deprecated đã bị xóa.
- [ ] Task dùng lazy configuration và khai báo input/output khi phù hợp.
- [ ] Configuration cache issues của internal plugins đã được ghi và xử lý.
- [ ] Maven plugin realm/dependencies đã được kiểm tra riêng với project dependencies.
- [ ] Generated source/task wiring hoạt động từ clean checkout.
- [ ] Plugin ID, extension, task/goal names có migration note khi đổi.
- [ ] Shell scripts quote path, xử lý exit code và không hardcode tool đã bị xóa.
- [ ] Credentials được quản lý bằng secret store, không nằm trong mã nguồn.

### Kiểm chứng

- [ ] Đã xác minh tool/plugin versions thực tế trên CI.
- [ ] Đã kiểm tra configuration/apply plugin trước khi chạy application.
- [ ] Đã compile main/test/generated sources với compiler và target release đúng.
- [ ] Đã kiểm tra test count, report, coverage và quality gates.
- [ ] Đã kiểm tra JAR/WAR/container artifact sau shading/packaging.
- [ ] Đã chạy smoke/integration tests trên JDK runtime mục tiêu.
- [ ] Đã chạy plugin consumer fixture cho internal plugins.
- [ ] Đã kiểm tra build trên các OS được hỗ trợ.
- [ ] Đã review dependency/plugin repository và artifact provenance.
- [ ] Đã lưu baseline, build logs, versions, risk owner và rollback plan.

## 24. Hồ sơ bàn giao cho Prime/build platform team

Một đợt nâng plugin/script nên có các bằng chứng:

1. **Version matrix:** old/new Maven/Gradle Wrapper, JDK build/toolchain/test/runtime, framework và plugin version.
2. **Plugin inventory:** direct, transitive/applied, internal, settings và generation/publish plugins.
3. **Compatibility rationale:** tài liệu hỗ trợ JVM/build tool và release notes được đối chiếu.
4. **Build script diff:** task/extension/goal thay đổi, API deprecated đã thay thế.
5. **Internal plugin evidence:** plugin binary target, Gradle/Maven API usage, consumer fixture và test matrix.
6. **Generated code evidence:** tool version, inputs, output snapshot, source roots.
7. **Resolved dependency graphs:** project runtime, plugin realm/classpath, processor/tool configurations.
8. **Verification records:** clean configuration, compile, test count, coverage, package và runtime.
9. **Supply-chain review:** repositories, distribution/plugin verification, secret handling.
10. **Release plan:** owner, compatibility restrictions, rollout, rollback và deadline xóa workaround.

**Kết luận:** Plugin build, plugin nội bộ và build scripts là một phần của phần mềm phải được nâng cấp cùng Java, chứ không chỉ là “cấu hình phụ”. Maven/Gradle có runtime riêng; plugins có classpath, version và API lifecycle riêng; code generators, test agents và CI scripts lại có nhiều yêu cầu độc lập. Tách rõ các lớp này, chốt compatibility matrix, nâng Wrapper/plugin theo trình tự có kiểm soát và xác minh **artifact cuối trên JDK mục tiêu** sẽ giúp tránh tình trạng source tương thích nhưng pipeline build hoặc phát hành bị đứt gãy.
