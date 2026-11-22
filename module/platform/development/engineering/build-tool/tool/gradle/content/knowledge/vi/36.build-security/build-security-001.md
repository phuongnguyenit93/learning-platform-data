# Build script và plugin là mã có quyền thực thi trên máy build: nguyên tắc An toàn build với Gradle

## 1. Bản chất của một Gradle build

Khi người dùng gõ `./gradlew test`, Gradle không chỉ đọc một file cấu hình tĩnh rồi chạy Java compiler. Các file `settings.gradle`, `build.gradle`, scripts bổ sung, `buildSrc`, included builds và binary plugins là **mã có thể thực thi**. Chúng có thể gọi Java/Groovy APIs, chạy tiến trình, truy cập filesystem, đọc môi trường và kết nối mạng trong phạm vi **quyền của tài khoản đang chạy Gradle**.

Đây là nguyên tắc quan trọng của chủ đề **An toàn build**:

> **Chạy build của một repository chưa được tin cậy là cho mã từ repository đó chạy trên laptop hoặc CI runner của bạn.** Gradle DSL không tự cung cấp một sandbox hệ điều hành để giới hạn quyền của build scripts hoặc plugins.

Điều này xảy ra ngay cả trước khi task `compileJava`, `test` hoặc `build` thực thi. Trong configuration phase, Gradle đánh giá build scripts và áp plugins. Một plugin có thể thực hiện logic ngay trong `Plugin.apply(Project)`. Khi IDE tự chạy Gradle sync, build logic cũng có thể chạy. Wrapper shell/JAR thậm chí được thực thi **trước** mọi Gradle build logic.

### 1.1. Mục tiêu bài học

Sau bài này, bạn có thể:
1. Giải thích vì sao build scripts/plugins là executable code và không tự được sandbox.
2. Phân biệt Wrapper bootstrap, initialization, configuration, task execution và configuration cache reuse.
3. Nhận biết các điểm mã chạy: `gradlew`, `settings.gradle`, `build.gradle`, `buildSrc`, included builds, init scripts, plugins, annotation processors và tasks.
4. Đánh giá quyền OS/CI runner, secrets, filesystem, network và Gradle User Home.
5. Viết và chạy **Gradle Groovy DSL + Java 17 lab** có local Java plugin vô hại chứng minh `Plugin.apply` chạy ngay khi cấu hình, còn `@TaskAction` chỉ chạy khi task được chọn.
6. Kiểm tra Wrapper JAR và Gradle distribution SHA-256 như hai ranh giới bootstrap khác nhau.
7. Kiểm soát plugin/dependency repositories, versions, verification metadata và build caches.
8. Thiết kế CI ít quyền cho Pull Request và tách riêng release pipeline.
9. Tránh những giả định sai về `--offline`, `--dry-run`, `--no-daemon` và `--configuration-cache`.
10. Biết phải làm gì nếu nghi build script/plugin đã truy cập dữ liệu trái phép.

Bài dùng Gradle Wrapper tương thích với **Java 17**, Java source có thể chạy bằng `javac`/`java` độc lập, và các ví dụ plugin chỉ ghi log vô hại; **không có ví dụ đọc credentials hay exfiltrate dữ liệu**.

## 2. Mô hình trust boundaries trong Gradle

Một lần chạy Gradle có thể đi qua các tầng sau:

~~~text
Developer hoặc CI runner
        |
        v
gradlew / gradlew.bat            (shell/batch executable)
        |
        v
gradle-wrapper.jar               (Java executable binary)
        |
        v
Gradle distribution / daemon
        |
        v
init scripts + settings.gradle   (initialization/configuration)
        |
        +--> pluginManagement, settings plugins
        +--> buildSrc / included plugin builds
        |
        v
build.gradle + binary plugins    (configuration)
        |
        +--> Plugin.apply(Project) chạy
        +--> task registration/configuration
        |
        v
Selected tasks                    (execution)
        |
        +--> @TaskAction, Test, JavaCompile, Exec...
        |
        v
Build outputs, reports, caches, published artifacts
~~~

Đây là **mô hình khái niệm**, không phải mọi dự án đều có tất cả tầng và không khẳng định thứ tự chi tiết của từng included build. Nhưng điểm chung là có nhiều đoạn mã chạy **trước** task action.

### 2.1. `settings.gradle` cũng là code

~~~groovy
rootProject.name = 'security-lab'

println '[demo/settings] settings.gradle đang được đánh giá'
~~~

Dòng `println` chạy khi Gradle đánh giá settings. Nó không nằm trong task nào. Nếu thay bằng thao tác I/O có side effect, side effect cũng xảy ra sớm. Vì vậy review settings scripts với mức tin cậy như các scripts automation khác.

### 2.2. `build.gradle` không chỉ chứa “khai báo”

~~~groovy
plugins {
    id 'java'
}

tasks.register('hello') {
    doLast {
        println 'Hello Gradle'
    }
}
~~~

Trong ví dụ:
- Plugin `java` được áp khi cấu hình project.
- `tasks.register` đăng ký task, thường trì hoãn configuration cho đến lúc cần.
- Code trong `doLast` chạy khi `hello` được thực thi.

Nhưng build.gradle còn có thể chứa Groovy statements **nằm ngoài** các task actions. Một plugin Java binary có thể làm việc ngay trong `apply`. Không thể suy ra quyền chỉ từ tên task.

### 2.3. `help` không phải chế độ sandbox

Các lệnh sau có thể đánh giá build scripts/plugins:

~~~bash
./gradlew help
./gradlew tasks
./gradlew dependencies
./gradlew build --dry-run
~~~

`--dry-run` không chạy task actions thông thường nhưng không ngăn Gradle configuration code. `--offline` giới hạn dependency resolution network, **không chặn mã plugin hoặc script đã nằm trong classpath**, cũng không phải OS firewall. `--no-daemon` thay process lifecycle, **không tước quyền** mã build có trong invocation.

`./gradlew --version` thường không evaluate toàn bộ project scripts, nhưng **vẫn thực thi Wrapper script/JAR và Gradle bootstrap**. Không dùng lệnh đó để tự kiểm tra một Wrapper chưa tin cậy.

### 2.4. Configuration cache không biến code thành an toàn

Gradle configuration cache có thể bỏ configuration phase khi reuse entry hợp lệ. Tuy nhiên lần cache miss/khởi tạo đầu tiên vẫn chạy scripts và apply plugins. Cache chỉ tối ưu việc cấu hình, không sandbox; cache entries còn có rủi ro riêng về secrets và nội dung task state.

## 3. Các nguồn executable code cần review

| Nguồn | Ví dụ | Ý nghĩa an toàn |
| --- | --- | --- |
| Wrapper shell/batch | `gradlew`, `gradlew.bat` | Code đầu tiên được chạy khi gọi Wrapper |
| Wrapper Java binary | `gradle/wrapper/gradle-wrapper.jar` | Thực thi trước distribution verification |
| Gradle settings | `settings.gradle(.kts)` | Có thể chạy logic trong initialization |
| Project build script | `build.gradle(.kts)` | Groovy/Kotlin code trong configuration |
| Init scripts | `~/.gradle/init.d/*.gradle`, `-I` | Có thể áp dụng cho nhiều builds của user |
| `buildSrc` | `buildSrc/src/main/java` | Code chạy trong build runtime khi được sử dụng |
| Included builds | `pluginManagement.includeBuild('build-logic')` | Build logic từ source độc lập được load |
| Binary plugins | JAR và transitive dependencies | Implementation có thể chạy khi apply |
| Precompiled convention plugins | Code từ included build | Cũng là plugin code, không tự sandbox |
| Remote script plugin | `apply from:` | Nguồn script khác có thể thực thi |
| Compile-time processors | Annotation processor JAR | Code được chạy trong compilation |
| Test code/tools | JUnit, code generators | Code được chạy trên runner khi tasks thực thi |
| Tasks | `@TaskAction`, `Exec`, `JavaExec` | Có thể gọi OS/process/network tùy quyền |

**Không đánh đồng** tải một JAR về với việc nó chắc chắn chạy ngay. Một Java library dependency có thể chỉ được dùng ở runtime; còn một plugin dependency được load trong configuration hoặc annotation processor được gọi ở compile phase. Phải đánh giá **đường đi từ artifact đến điểm thực thi**.

### 3.1. `buildSrc` và included builds

`buildSrc` được Gradle xử lý để cung cấp build logic; source trong đó không phải “chỉ để hỗ trợ IDE”. Included build cũng có Gradle settings/build files, plugin implementations và external dependencies riêng. Một PR thay `buildSrc` hoặc `build-logic` có thể thay code chạy trên CI trước khi tests bắt đầu.

### 3.2. Init scripts

Gradle User Home, thường là `~/.gradle`, lưu init scripts, caches, daemon logs, Wrapper distributions và `gradle.properties`. Init scripts có thể xuất phát từ `GRADLE_USER_HOME/init.d` hoặc được đưa qua command-line. Nếu shared CI runner cho các jobs có độ tin cậy khác nhau cùng ghi Gradle User Home, một job có thể làm ảnh hưởng job khác.

### 3.3. Plugin DSL và plugin marker

~~~groovy
plugins {
    id 'dev.example.quality' version '2.4.0'
}
~~~

Đây chỉ là **cú pháp minh họa**, không khuyến khích tải plugin ID này. Plugin resolution có thể tìm một marker module dẫn tới implementation JAR và transitive classpath. Cố định version giảm tự thay đổi nhưng không chứng minh plugin code đã được review. Phải xem ID, nhà phát hành, repository, marker mapping và dependencies.

### 3.4. Convention plugin không phải bản cấu hình vô hại

Một convention plugin trong monorepo có thể giúp chuẩn hóa Java toolchain, tests và artifacts. Nhưng nó vẫn là executable code. Review quyền của plugin giống các automation scripts khác: nó chạy ở đâu, đọc gì, ghi gì, có network/process calls không, có truy cập project khác không.

## 4. Mã Gradle có những quyền gì?

Một Gradle daemon/JVM và subprocess của nó thường hoạt động với **quyền của OS user/CI service account** đã chạy Gradle. Nếu user có quyền đọc/ghi dữ liệu nào, code build có thể tận dụng quyền đó, trừ khi OS/container/network policy giới hạn.

Ví dụ quyền có thể tồn tại:
- Đọc/sửa workspace files.
- Đọc files trong home directory mà user được phép truy cập.
- Lấy environment variables, system properties và Gradle properties.
- Sử dụng credentials được cấp cho build job.
- Truy cập network và service endpoints mà runner cho phép.
- Thực thi subprocess thông qua các Java/Groovy/Gradle APIs.
- Ghi vào artifacts/reports/caches.
- Truy cập Docker socket hoặc mounted volumes nếu CI đã cấp.

**Gradle Plugin Portal, Maven Central hoặc checksum đúng không tước những quyền này của plugin.** Chính trust policy, OS permissions, container isolation và CI separation mới giới hạn hậu quả.

### 4.1. Least privilege

Một unit-test job thường **không cần**:
- Production cloud credentials.
- Signing keys và package publish tokens.
- SSH private keys có quyền deploy.
- Docker daemon socket của host.
- Mutable caches của release job.
- Quyền root/Administrator.
- Write access vào protected branch.

Sử dụng read-only repository token, runner/container ephemeral, hạn chế network egress, chỉ mount những directory cần thiết. Đừng dùng một CI job nhiều quyền để chạy mã Pull Request chưa được duyệt rồi hy vọng quality gate phát hiện mọi hành vi.

### 4.2. Secrets không nằm trong Git vẫn có thể bị đọc

CI thường đưa secret vào môi trường dưới dạng variables, files hoặc cloud identity. Plugin chạy trong cùng environment có thể truy cập theo quyền process. Việc một secret được masking trong logs **không** ngăn code đọc nó. Không cung cấp secret cho bước Gradle verification nếu bước đó không thực sự cần.

## 5. Lab Java 17 an toàn: chứng minh code chạy trước TaskAction

Ta viết một local binary Gradle plugin:
- Plugin chỉ ghi hai loại log: configuration và task execution.
- Không truy cập credential, không network/exec, không ghi file ngoài build.
- Khi chạy `help`, plugin `apply` vẫn chạy dù task demo chưa chạy.
- Một Java 17 application có stdout chính xác để người học phân biệt app output với Gradle logs.

### 5.1. Cấu trúc

~~~text
security-boundaries-lab/
├── settings.gradle
├── build.gradle
├── build-logic/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/java/dev/example/buildlogic/StageAuditPlugin.java
├── src/main/java/dev/example/app/App.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Cần Gradle Wrapper được xác minh trước khi chạy, cùng JDK17. Gradle 8.14.3 hoặc bản tương thích được dùng làm ví dụ, không phải yêu cầu rằng 8.14.3 là bản mới nhất.

### 5.2. Root `settings.gradle`

~~~groovy
pluginManagement {
    includeBuild('build-logic')
}

rootProject.name = 'security-boundaries-lab'

println '[demo/settings] settings.gradle đang được đánh giá'
~~~

Lưu ý `pluginManagement.includeBuild` đăng ký một **plugin-producing included build**, không phải khai `include 'build-logic'` thành subproject. Dòng `println` vô hại ở configuration/initialization và giúp thấy rõ thời điểm evaluation.

### 5.3. `build-logic/settings.gradle`

~~~groovy
rootProject.name = 'security-build-logic'
~~~

### 5.4. `build-logic/build.gradle`

~~~groovy
plugins {
    id 'java-gradle-plugin'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

gradlePlugin {
    plugins {
        register('stageAuditPlugin') {
            id = 'dev.example.stage-audit'
            implementationClass =
                'dev.example.buildlogic.StageAuditPlugin'
        }
    }
}
~~~

`java-gradle-plugin` cung cấp Gradle API cho Java source và sinh descriptor mapping plugin ID sang implementation class. Vì plugin code nằm trong included build được review, không cần tải unknown third-party plugin. Tuy nhiên chính Java class vẫn được Gradle load và thực thi.

### 5.5. `build-logic/src/main/java/dev/example/buildlogic/StageAuditPlugin.java`

~~~java
package dev.example.buildlogic;

import org.gradle.api.DefaultTask;
import org.gradle.api.Plugin;
import org.gradle.api.Project;
import org.gradle.api.tasks.TaskAction;

/** Harmless training plugin: logs only. */
public final class StageAuditPlugin implements Plugin<Project> {

    @Override
    public void apply(Project project) {
        project.getLogger().lifecycle(
            "[demo/config] Plugin.apply đang chạy lúc cấu hình"
        );

        project.getTasks().register(
            "stageAudit",
            StageAuditTask.class,
            task -> {
                task.setGroup("verification");
                task.setDescription(
                    "Observe task execution phase without side effects"
                );
            }
        );
    }

    public abstract static class StageAuditTask extends DefaultTask {

        @TaskAction
        public void audit() {
            getLogger().lifecycle(
                "[demo/task] stageAudit đang chạy lúc thực thi"
            );
        }
    }
}
~~~

Giải thích:
- `StageAuditPlugin implements Plugin<Project>` là plugin binary class.
- `apply(Project)` được Gradle gọi khi áp plugin ở configuration phase.
- `getLogger().lifecycle` chỉ tạo một log có thể quan sát; không đọc file/process/network.
- `tasks.register` lazy đăng ký task `stageAudit`.
- Nested static `StageAuditTask` là Gradle task implementation.
- `@TaskAction` chỉ chạy khi task được chọn để thực thi.
- Plugin source không thể biên dịch chỉ với JDK standard classpath vì phụ thuộc Gradle APIs; `java-gradle-plugin` cung cấp chúng.

**Liên hệ security:** Một plugin có thể làm hơn việc ghi log trong `apply` vì đây là Java code có quyền của build process. Lab **chỉ** ghi log để minh họa mà không chạm dữ liệu nhạy cảm.

### 5.6. Root `build.gradle`

~~~groovy
plugins {
    id 'application'
    id 'dev.example.stage-audit'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}

application {
    mainClass = 'dev.example.app.App'
}
~~~

`application` là core plugin tạo Java source sets và `run` task. `dev.example.stage-audit` được resolve từ `build-logic`. Không dùng third-party dependency trong lab. Java toolchain chọn compiler/runtime, **không làm plugin mất OS privileges**.

### 5.7. `src/main/java/dev/example/app/App.java`

~~~java
package dev.example.app;

public final class App {

    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Security boundary demo: OK");
    }
}
~~~

Mã Java là một chương trình đầy đủ, biên dịch độc lập.

### 5.8. Chạy `help`: configuration code thực thi

~~~bash
./gradlew help --no-configuration-cache --console=plain
~~~

Các **dòng demo** có thể quan sát trong log:

~~~text
[demo/settings] settings.gradle đang được đánh giá
[demo/config] Plugin.apply đang chạy lúc cấu hình
~~~

Không có dòng `[demo/task]` do `stageAudit` không được chọn. Gradle có thể in thêm task/build logs hoặc output của included build; không coi hai dòng trên là **toàn bộ stdout byte-for-byte**.

`--no-configuration-cache` giúp tránh trường hợp lần sau Gradle reuse configuration cache và không chạy lại `apply` trong thí nghiệm. Không nên hiểu flag này là cơ chế sandbox.

### 5.9. Chạy task: TaskAction thực thi

~~~bash
./gradlew stageAudit --no-configuration-cache --console=plain
~~~

Các log demo xuất hiện:

~~~text
[demo/settings] settings.gradle đang được đánh giá
[demo/config] Plugin.apply đang chạy lúc cấu hình
[demo/task] stageAudit đang chạy lúc thực thi
~~~

Dòng task chỉ xuất hiện khi task được thực thi. Thứ tự các log khác của Gradle không cố định, nhưng hai pha configuration và execution đã được phân biệt.

### 5.10. Chạy app qua Gradle

~~~bash
./gradlew run --quiet
~~~

**Stdout ứng dụng Java:**

~~~text
Security boundary demo: OK
~~~

`--quiet` ẩn lifecycle logs từ Gradle trong nhiều trường hợp, nhưng plugin `apply` vẫn có thể chạy. Việc không thấy log config trong quiet mode **không chứng minh** plugin không chạy.

### 5.11. Chạy Java độc lập bằng Java 17

~~~bash
javac --release 17 -encoding UTF-8 -d standalone src/main/java/dev/example/app/App.java
java -cp standalone dev.example.app.App
~~~

**Stdout chính xác:**

~~~text
Security boundary demo: OK
~~~

Lệnh Java-only kiểm tra `App.java` mà không chạy Gradle; nó không xác nhận Wrapper hoặc plugin trust chain. Đây là sự khác biệt giữa **chạy code ứng dụng** và **chạy hệ thống build**.

### 5.12. Bài kiểm tra về configuration cache

~~~bash
./gradlew help --configuration-cache
./gradlew help --configuration-cache
~~~

Với configuration cache hợp lệ, lần thứ hai có thể không thấy `[demo/config]` vì Gradle bỏ qua configuration phase. Đây không phải biện pháp ngăn mã nguy hiểm: lần tạo cache vẫn chạy code, và cache có thể miss sau thay đổi build logic.

### 5.13. Những thao tác **không** thực hiện trong lab

Không thay log demo bằng code đọc `System.getenv()` toàn bộ, file credentials, cloud metadata endpoint hay subprocess. Mục đích của lab là **hiểu quyền và thời điểm**, không chứng minh quyền bằng hành vi gây rủi ro. Nếu cần kiểm tra plugin third-party nghi ngờ, thực hiện qua quy trình security review/isolated investigation riêng.

## 6. Wrapper: điểm thực thi trước cả Gradle build scripts

Một repo Gradle đầy đủ có bốn file quan trọng:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

- `gradlew`/`gradlew.bat`: scripts được OS shell/batch thực thi.
- `gradle-wrapper.jar`: Java code tải/chạy distribution.
- `gradle-wrapper.properties`: URL/version/checksum.
- Gradle distribution ZIP: binary build tool chính.

**Review cả bốn files** khi nhận source chưa tin cậy hoặc Pull Request nâng Wrapper. Một script/JAR bị sửa có thể chạy trước mọi Gradle task và trước dependency verification.

### 6.1. Ví dụ Wrapper đã pin với SHA-256 chính thức

Ví dụ **Gradle 8.14.3 binary-only distribution**:

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
distributionSha256Sum=bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

Đây là SHA-256 chính thức của **đúng `gradle-8.14.3-bin.zip`**, tra từ [Gradle Release Checksums](https://gradle.org/release-checksums/). **Không** giữ hash này nếu đổi sang `-all.zip` hoặc version khác.

`distributionSha256Sum` kiểm tra downloaded distribution ZIP khi Wrapper tải distribution mới; không tự kiểm tra Wrapper JAR/script, plugin JAR hay các cache entries khác.

### 6.2. Wrapper JAR checksum khác ZIP checksum

Official Gradle 8.14.3 Wrapper JAR checksum là:

~~~text
7d3a4ac4de1c32b59bc6a4eb8ecb8e612ccd0cf1ae1e99f66902da64df296172
~~~

Tính SHA-256 file trong repository bằng công cụ hệ điều hành:

~~~bash
sha256sum gradle/wrapper/gradle-wrapper.jar
~~~

PowerShell:

~~~powershell
(Get-FileHash 'gradle/wrapper/gradle-wrapper.jar' -Algorithm SHA256).Hash.ToLower()
~~~

So sánh với official release checksums. Lưu ý `gradle-wrapper.jar` có thể được sinh từ một version khác so với version trong `distributionUrl` nếu project chỉ cập nhật properties; khi ấy phải xác định JAR có nằm trong danh sách official của **version đã sinh JAR** không. Không ghi đè JAR bằng một binary không rõ nguồn để làm hash “đúng”.

### 6.3. Không chạy Wrapper lạ để tự kiểm tra

Không khởi động `./gradlew --version` hoặc `./gradlew wrapper` của repository chưa tin trước khi đọc/đối chiếu Wrapper scripts/JAR. Lệnh đó đã thực thi bootstrap code. Dùng file inspection và hash tools độc lập trước, hoặc trusted CI validation step.

### 6.4. CI Wrapper validation

Gradle `setup-gradle` GitHub Action phiên bản hỗ trợ có thể tự validate Wrapper JAR checksums trước khi chạy build. Kết hợp với `distributionSha256Sum` và source review. Hai lớp bảo vệ **không thay thế nhau**.

## 7. Plugins/dependencies: nguồn cung cấp JAR cũng là trust boundary

### 7.1. Plugin resolution vs library resolution

Trong `settings.gradle` của một build minh họa **khác lab phần 5**:

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'reviewed-build'
~~~

- `pluginManagement.repositories` chỉ rõ nơi tìm **plugins**.
- `dependencyResolutionManagement.repositories` chỉ rõ nơi tìm **library dependencies**.
- `RepositoriesMode.FAIL_ON_PROJECT_REPOS` ngăn subprojects tự đưa thêm repository khác ngoài policy.
- Nguồn Gradle Plugin Portal/Maven Central là repository công khai hợp lệ, **không phải sự bảo đảm rằng mọi plugin/library đều là mã an toàn**.
- Với doanh nghiệp, có thể dùng private Maven mirror/repository content filters và `exclusiveContent` để tránh internal coordinates bị public repository giả mạo.

Đừng copy đoạn settings này chồng lên lab phần 5 mà bỏ mất `pluginManagement.includeBuild('build-logic')`; đây là **cấu hình mẫu theo ngữ cảnh khác**.

### 7.2. Pin versions và kiểm soát nhà phát hành

Khi thêm plugin:
1. Xác nhận plugin ID, publisher và release source.
2. Review binary/plugin source, release notes và transitive dependencies.
3. Pin version chính xác; tránh dynamic versions như `+` hoặc `latest.release` trong release pipelines.
4. Dùng trusted repositories qua HTTPS.
5. Kiểm soát plugin marker artifact và mapping tới implementation JAR.
6. Có security upgrade/rollback process và test plugin trong runner ít quyền.

Plugin “format”, “lint”, “license” hay “test” vẫn là code. Tên plugin không xác định mức độ quyền.

### 7.3. Dependency verification

Gradle dùng:

~~~text
gradle/verification-metadata.xml
~~~

để khai checksums/signatures của external artifacts. Theo Gradle docs, dependency verification có thể áp cho cả project/settings plugins được resolve qua Gradle dependency engine, ngoài library JARs/POM/metadata.

Tạo baseline **chỉ trên build đã được review/trusted**:

~~~bash
./gradlew --write-verification-metadata sha256 help
~~~

Sau khi sinh file, phải:
- Review diff.
- Đối chiếu critical checksums với trusted upstream.
- Xác nhận đúng IDs/versions/repositories.
- Commit verification metadata.
- Chạy strict verification trong CI.

~~~bash
./gradlew --dependency-verification strict check
~~~

**Giới hạn rất quan trọng:** lệnh bootstrap metadata cũng chạy Wrapper + configuration code. Nó **không phải công cụ quét an toàn để thực thi repo lạ**. Nếu artifact đã bị tamper ở thời điểm bootstrap, Gradle có thể ghi checksum của artifact xấu; vì thế phải review metadata trước khi tin.

### 7.4. Checksum không phải một code-security audit

- Checksum/signature verification bảo vệ **integrity/provenance** theo metadata đã tin.
- Nó không phát hiện mọi CVE hoặc mã cố ý gây hại.
- Nó không sandbox `Plugin.apply`.
- Nó không bảo vệ Wrapper script/JAR được chạy trước.
- Nó không làm local `buildSrc`/included build source code trở thành trusted.
- Nó có các giới hạn với changing/SNAPSHOT/local artifacts.
- Một plugin có checksum “đúng” vẫn có thể có logic không được phép theo tổ chức.

### 7.5. Locking khác verification

**Dependency locking** kiểm soát **version graph**. **Dependency verification** kiểm soát **bytes/signatures** của artifacts. **Vulnerability scanning** kiểm tra rủi ro đã biết. **OS/CI isolation** giới hạn hậu quả khi một thành phần vẫn không đáng tin.

Cần kết hợp bốn lớp thay vì trông chờ một feature duy nhất.

## 8. Gradle User Home, caches và secrets

### 8.1. `GRADLE_USER_HOME`

Thông thường `~/.gradle` lưu:
- `gradle.properties` (có thể chứa credentials plaintext).
- `init.d` scripts.
- Downloaded Gradle distributions.
- Plugin/dependency caches.
- JDK toolchains đã provision.
- Daemon logs/registries.

Nếu nhiều jobs có mức tin cậy khác nhau dùng chung **writable** Gradle User Home, job ít tin cậy có thể ảnh hưởng job nhiều quyền. Dùng home riêng theo job/trust domain và OS permissions thích hợp.

Trên Linux/macOS, các lệnh minh họa thiết lập quyền owner:

~~~bash
chmod 700 "$HOME/.gradle"
chmod 600 "$HOME/.gradle/gradle.properties"
~~~

Chỉ chạy khi files/directories tồn tại và có quyền; Windows dùng ACL thích hợp. Đây là biện pháp bảo vệ file access, không thay thế code review.

### 8.2. Secrets và Gradle properties

Không commit password/token vào repository `gradle.properties`, `build.gradle` hoặc scripts CI. Ưu tiên CI secrets store và Gradle credentials API/lazy Provider wiring. Nhưng nếu mã độc đã chạy với cùng OS user, một Provider không phải sandbox ngăn đọc các secrets được cấp cho process. **Đừng đưa secrets vào job nếu job không cần chúng.**

### 8.3. Configuration cache có thể chứa dữ liệu nhạy cảm

Configuration cache có thể serialize configured task state và những giá trị được lưu vào đó, được Gradle mã hóa theo cơ chế riêng. Key và caches dưới Gradle User Home/build directory cần được bảo vệ; nếu attacker có cả key và cached data, dữ liệu có thể bị đọc.

Không chia sẻ untrusted/trusted jobs cùng `.gradle/configuration-cache` hoặc encryption key. Tránh eagerly resolve secrets trong configuration phase. Xem [Configuration Cache Security](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html).

### 8.4. Build cache poisoning

Local/remote build caches có thể chứa outputs từ task đã chạy; nếu cache writes không phân tách trust domains, một build không đáng tin có thể ảnh hưởng outputs của build khác. Cần:
- Không cho untrusted PR ghi remote cache của release.
- Giới hạn cache permissions/keys.
- Đảm bảo tasks có đầy đủ input declarations.
- Không coi cache hit là bằng chứng output đã qua review.
- Kiểm tra provenance/hash của release artifact.

### 8.5. Gradle daemon

Daemon tái sử dụng JVM/process để tăng tốc. `--no-daemon` có thể thay process lifetime nhưng **không làm build code mất quyền trong phiên chạy**. Với shared CI agents, bảo vệ OS user/Gradle home/process isolation.

## 9. CI workflow: tách untrusted PR khỏi trusted release

Một Pull Request có thể sửa build scripts, Wrapper, CI YAML, plugin source hoặc test code. Vì vậy cần chọn **permissions trước khi chạy Gradle**, không đợi tests PASS rồi mới nghĩ tới bảo mật.

### 9.1. GitHub Actions verification ít quyền

~~~yaml
name: Verify Gradle

on:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Validate Gradle Wrapper and prepare cache
        uses: gradle/actions/setup-gradle@v4
        with:
          gradle-version: wrapper
          cache-read-only: true

      - name: Run checks without deployment credentials
        run: ./gradlew check --dependency-verification strict
~~~

Giải thích:
- `pull_request` + `contents: read` phù hợp workflow kiểm chứng cơ bản, không có publishing token.
- `gradle/actions/setup-gradle` phiên bản hỗ trợ có Wrapper validation.
- `cache-read-only: true` hạn chế write vào cache do action quản lý; **không** thay runner isolation.
- `check` do Java/Application plugin cung cấp, phù hợp lab phần 5.
- Strict verification yêu cầu verification metadata đã được review để phát huy đầy đủ; flag không tự sinh metadata.
- Action tags là lựa chọn minh họa; production nên cân nhắc pin full commit SHAs theo chính sách.
- Dù job không có secrets, build code vẫn chạy trên runner. Giới hạn permissions, network và mounts vẫn quan trọng.

### 9.2. Tránh một bẫy đặc biệt: `pull_request_target`

GitHub `pull_request_target` có quyền/trust semantics khác `pull_request`. Nếu workflow dùng event này trong context có quyền cao, checkout và thực thi untrusted PR head bằng Gradle thì mã PR có thể chạy với các quyền ấy. Không thiết kế pipeline kiểu đó. Khi cần workflow privileged, phải tách nguồn code được chạy và quy trình approval/trust boundaries một cách rõ ràng.

### 9.3. Release/deploy pipeline riêng

Release job nên:
1. Chỉ chạy từ reviewed/protected revision/tag.
2. Validate Wrapper/integrity/dependency metadata.
3. Chạy full tests, scans, quality gates.
4. Tạo artifacts có source/version provenance.
5. Cấp signing/cloud/publishing credentials **đúng bước và đúng scope**.
6. Không chạy untrusted PR build logic trong môi trường chứa release secrets.
7. Không publish artifacts từ untrusted job nếu chưa có provenance/verification thích hợp.
8. Không dùng cache writable của PR như trusted release cache.

Chỉ thêm `if: success()` cuối job **không bảo vệ secret** nếu untrusted build code đã chạy trước đó trong cùng job có secret.

### 9.4. GitLab/Jenkins/container

Nguyên tắc tương tự:
- Dùng ephemeral runner hoặc container ít quyền.
- Không chạy Gradle bằng root/Administrator khi không cần.
- Không mount Docker socket, SSH keys hoặc host home vào untrusted job.
- Cấp `GRADLE_USER_HOME` riêng cho trust domain.
- Chỉ cho jobs đã review quyền publish/deploy.
- Hạn chế network egress nếu môi trường cho phép.
- Archive logs/reports nhưng không chia sẻ secrets.
- Bảo vệ caches, dependency mirrors và artifact repositories.

## 10. Những thay đổi cần review như privileged code

Khi Pull Request thay đổi một trong các nhóm sau, review không chỉ để “build còn chạy”:

- `gradlew`, `gradlew.bat`, `gradle-wrapper.jar`, `gradle-wrapper.properties`.
- `settings.gradle(.kts)` và `build.gradle(.kts)` mọi subprojects.
- `buildSrc/**` hoặc `build-logic/**`, custom Java/Groovy/Kotlin Gradle plugins.
- `gradle/libs.versions.toml` khi đổi plugin/dependency versions.
- `gradle/verification-metadata.xml`, dependency locks.
- `gradle.properties`, init scripts nếu có trong source/CI image.
- `.github/workflows/**`, `Jenkinsfile`, `.gitlab-ci.yml`.
- Dockerfiles, build images, toolchain resolver plugins.
- Annotation processors, test runners, code generation tools.

### 10.1. Câu hỏi review

1. Đoạn code mới chạy ở bootstrap/configuration/execution?
2. Nó cần đọc file nào, biến môi trường nào, network endpoint nào?
3. Có gọi subprocess hoặc write directory ngoài build output không?
4. Có plugin/repository/version mới chưa được review không?
5. Có thể chạy khi developer mở IDE sync hoặc `./gradlew help` không?
6. CI job nào sẽ thực thi nó, với token/cloud role gì?
7. Gradle User Home/caches có bị thay đổi/ghi chung giữa trust domains không?
8. Có tắt dependency verification, thay Wrapper checksum hoặc nới repositories không?
9. Output và logs có thể chứa secrets không?
10. Có phương án rollback/hạn chế ảnh hưởng nếu plugin bị compromise không?

### 10.2. Dấu hiệu nên điều tra

- Repository mới không có trong allowlist, qua plain HTTP.
- Plugin ID/publisher thay bất thường hoặc dependency dynamic version.
- Obfuscated/encoded script code không có lý do.
- Remote `apply from:` chưa được review.
- `buildSrc` hoặc included build cố truy cập secrets/environment khi configuration.
- Wrapper JAR/script đổi dù PR được mô tả là chỉ sửa docs.
- Init scripts mới trong shared runner home.
- CI workflow cấp token write/cloud production cho unit tests.
- Verification chuyển sang `lenient`/`off` chỉ để bỏ lỗi checksum.
- Logs hoặc artifacts có credential/absolute path/provenance bất thường.

Một dấu hiệu **không tự chứng minh mã độc**. Có plugins hợp lệ cần network/Exec; nhưng quyền, nguồn và mục đích phải được giải thích rõ.

## 11. Xử lý khi nghi ngờ build script/plugin bị xâm nhập

1. Dừng thực thi Gradle trên máy/runner bị nghi ngờ, không “chạy thêm lần nữa” với nhiều quyền để debug.
2. Cô lập runner/workspace/Gradle User Home theo incident-response policy.
3. Thu hồi/rotate credentials có thể bị lộ; rà soát audit logs và cloud access.
4. Lưu evidence cần thiết: commit SHA, diff, artifact hashes, CI logs, repository URLs, plugin IDs.
5. Đối chiếu Wrapper JAR và distribution checksums bằng trusted tools/sources **ngoài** build nghi ngờ.
6. Review settings/build/init scripts, `buildSrc`, included builds và plugin/transitive dependencies.
7. Kiểm tra remote caches/artifact repositories nếu job từng có quyền ghi.
8. Chỉ tái chạy trong môi trường điều tra cô lập, không có production secrets.
9. Xác định root cause, sửa quyền, nguồn plugin, verification metadata và CI isolation.
10. Không promote/reuse artifacts từ compromised build cho release trước khi khẳng định provenance.
11. Ghi lessons learned và kiểm tra lại toàn bộ pipeline trust boundaries.

Không dùng `./gradlew help --info` trên repo nghi ngờ như một cách “phân tích vô hại” khi chưa xử lý threat model.

## 12. Những hiểu lầm phổ biến

| Ngộ nhận | Điều đúng |
| --- | --- |
| “Build script chỉ khai cấu hình” | Là Groovy/Kotlin code thực thi |
| “Chỉ TaskAction mới chạy code” | Settings/scripts/plugins đã có thể chạy trước |
| “`./gradlew help` chắc chắn an toàn” | Có configuration và plugin application |
| “`--dry-run` biến build thành read-only” | Chỉ không thực thi task actions thông thường |
| “`--offline` chặn mọi network code” | Không phải OS firewall/sandbox |
| “`--no-daemon` làm mã build ít quyền hơn” | Chỉ thay process lifetime |
| “Plugin Portal tự sandbox plugins” | Không; plugin có quyền build process |
| “Pin version là đủ” | Cần source/integrity/review và isolation |
| “Dependency verification phát hiện mọi CVE” | Chỉ xác minh artifacts theo trusted metadata |
| “Checksum ZIP bảo vệ Wrapper JAR” | Hai thành phần bootstrap khác nhau |
| “`buildSrc` là code nội bộ nên không cần review” | Vẫn chạy trong build runtime |
| “Configuration cache hit nghĩa là plugin vô hại” | Code đã chạy khi tạo cache và sẽ chạy khi miss |
| “CI tests PASS chứng minh build an toàn” | Security/trust/provenance là các yêu cầu riêng |
| “Không có secret trong Git nên mã build không đọc secret được” | CI process có thể vẫn có secrets qua env/files/identity |

## 13. Bài tập có lời giải

### Bài 1 — `help` và plugin
**Hỏi:** Project áp plugin `dev.example.stage-audit`. `./gradlew help` có chạy `Plugin.apply` không?

**Đáp án:** Có khi build được cấu hình. `stageAudit` task action không chạy nếu task không được chọn.

### Bài 2 — Wrapper bootstrap
**Hỏi:** Có nên chạy `./gradlew --version` của một repository chưa kiểm chứng rồi mới kiểm tra JAR checksum?

**Đáp án:** Không. Wrapper script/JAR đã thực thi trước khi output version được in.

### Bài 3 — `buildSrc`
**Hỏi:** PR chỉ thay `buildSrc/src/main/java`, không thay application source. Có cần security review?

**Đáp án:** Có. Nó có thể thay executable build logic được chạy trên CI.

### Bài 4 — Init scripts
**Hỏi:** Vì sao tránh chung writable `GRADLE_USER_HOME` giữa PR và release jobs?

**Đáp án:** Home chứa init scripts, caches và có thể có credentials. Job thấp quyền có thể ảnh hưởng job nhiều quyền.

### Bài 5 — Plugin marker
**Hỏi:** Một plugin ID/version trong `plugins {}` có thể kéo theo JAR nào?

**Đáp án:** Plugin marker metadata có thể chỉ tới implementation artifact và transitive dependencies; phải xác minh mapping/source.

### Bài 6 — Dependency verification
**Hỏi:** `verification-metadata.xml` có làm code `build.gradle` ở repo untrusted trở thành an toàn không?

**Đáp án:** Không. Local build script là executable source code, không được sandbox bởi artifact checksums.

### Bài 7 — Checksum
**Hỏi:** Distribution URL trỏ `gradle-8.14.3-all.zip` nhưng checksum lấy từ `-bin.zip` thì sao?

**Đáp án:** Hash mismatch, Wrapper download verification thất bại. Mỗi ZIP có checksum riêng.

### Bài 8 — PR secrets
**Hỏi:** Có nên truyền production registry token cho `./gradlew test` của fork PR?

**Đáp án:** Không. Build code có thể đọc token trước khi tests chạy.

### Bài 9 — `pull_request_target`
**Hỏi:** Nguy cơ khi checkout untrusted PR head và chạy Gradle trong privileged job của event này?

**Đáp án:** Mã PR có thể thực thi với quyền cao của job; phải tách trust boundary.

### Bài 10 — Offline
**Hỏi:** `--offline` có ngăn local plugin dùng OS APIs không?

**Đáp án:** Không. Offline chỉ tác động dependency resolution, không sandbox code.

### Bài 11 — Configuration cache
**Hỏi:** Vì sao lần thứ hai có thể không thấy log `Plugin.apply`?

**Đáp án:** Configuration cache reuse hoặc logging level; không chứng minh code không chạy ở lần đầu.

### Bài 12 — Lab `help`
**Hỏi:** Chạy `help --no-configuration-cache` có những demo log nào?

**Đáp án:** `[demo/settings] settings.gradle đang được đánh giá` và `[demo/config] Plugin.apply đang chạy lúc cấu hình`, không có log task action.

### Bài 13 — Lab `stageAudit`
**Hỏi:** Chạy `stageAudit --no-configuration-cache` thêm log nào?

**Đáp án:** `[demo/task] stageAudit đang chạy lúc thực thi`.

### Bài 14 — Java stdout
**Hỏi:** Java `App.main` in chính xác gì?

**Đáp án:** Một dòng `Security boundary demo: OK` có newline cuối.

### Bài 15 — Code review
**Hỏi:** Một plugin mới có checksum đúng. Có cần review/least privilege không?

**Đáp án:** Có. Checksum xác minh bytes theo metadata, không đánh giá hành vi code.

### Bài 16 — Incident
**Hỏi:** Nghi plugin đã truy cập secrets trong release runner. Có nên tiếp tục chạy Gradle với `--info` trên runner đó?

**Đáp án:** Không. Dừng/cô lập và xử lý secrets/evidence trước; phân tích trên môi trường cô lập.

### Bài 17 — Thực hành end-to-end
1. Tạo đủ files phần 5, dùng Wrapper/JDK17 từ nguồn tin cậy.
2. Kiểm tra Wrapper script/JAR và SHA-256.
3. Chạy `./gradlew help --no-configuration-cache --console=plain`.
4. Xác nhận log settings/plugin đã xuất hiện nhưng task action chưa chạy.
5. Chạy `./gradlew stageAudit --no-configuration-cache --console=plain`; kiểm tra log task.
6. Chạy `./gradlew run --quiet`; đối chiếu stdout Java.
7. Chạy `javac`/`java` độc lập; đối chiếu stdout.
8. Chạy `help --configuration-cache` hai lần; giải thích khi cache reuse.
9. Phân tích một PR giả định thêm plugin/repository mới **mà không tải hoặc thực thi nó**, liệt kê các bước review.
10. Thiết kế PR verification read-only, không có publish secrets, và trusted release job tách rời.
11. Giải thích giới hạn của dependency verification và Wrapper checksum.
12. Viết checklist phản ứng khi checksum mismatch hoặc build artifact provenance bị nghi ngờ.

**Tiêu chí đạt:** Người học phân biệt được quyền của executable build code, các pha thực thi, trust boundary của Wrapper/plugins/CI, và áp dụng được nguyên tắc giảm quyền trước khi chạy Gradle.

## 14. Checklist An toàn build cho dự án thực

- [ ] Không chạy Wrapper của repository chưa tin trước khi kiểm tra scripts/JAR.
- [ ] Wrapper distribution URL pin version exact và có official `distributionSha256Sum`.
- [ ] Wrapper JAR được đối chiếu official checksum/CI validation.
- [ ] Gradle distribution còn nhận security fixes phù hợp policy.
- [ ] `settings.gradle`/`build.gradle`/`buildSrc`/included builds/init scripts được review như code.
- [ ] Các plugin IDs, versions, publishers và transitive classpaths được kiểm tra.
- [ ] Repositories tập trung, HTTPS, filter/exclusive content khi cần.
- [ ] Dynamic plugin/dependency versions được hạn chế.
- [ ] Dependency verification metadata được review, strict mode trên CI.
- [ ] Dependency locking/vulnerability scanning được dùng theo build policy.
- [ ] Không xem checksum verification như sandbox hay full code audit.
- [ ] Untrusted PR build dùng runner ephemeral và read-only credentials.
- [ ] Không có production/deploy secrets trong untrusted Gradle jobs.
- [ ] Release workflow chỉ chạy reviewed/trusted source.
- [ ] Gradle User Home/init scripts/caches không chia sẻ writable giữa trust domains.
- [ ] Không mount Docker socket/SSH keys/host volumes khi không cần.
- [ ] Gradle configuration cache có permissions/encryption key policy rõ.
- [ ] Logs, Build Scans, test reports không lộ secrets.
- [ ] Không dựa vào `--offline`/`--dry-run`/`--no-daemon` để tự bảo vệ.
- [ ] Annotation processors/test tools/custom Exec được xem là build-time executable code.
- [ ] Có incident response và artifact provenance nếu build supply chain bị nghi ngờ.

## 15. Tài liệu Gradle chính thức

- [Gradle — Securing Gradle Builds](https://docs.gradle.org/current/userguide/security.html): tổng quan bảo vệ repositories, dependencies và build tool.
- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html): build scripts không sandbox, Wrapper, init scripts, User Home, caches và daemon.
- [Gradle — Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html): tránh chạy untrusted Wrapper và review build logic.
- [Gradle — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html): repositories, HTTPS, filters và exclusive content.
- [Gradle — Securing Dependencies](https://docs.gradle.org/current/userguide/dependency_verification.html): metadata, SHA-256/PGP và strict verification.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): scripts/JAR/distribution integrity.
- [Gradle — Release Checksums](https://gradle.org/release-checksums/): official Gradle ZIP/Wrapper JAR SHA-256.
- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): initialization, configuration, execution.
- [Gradle — Implementing Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins.html): `Plugin<Project>` behavior.
- [Gradle — Java Gradle Plugin Development Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html): plugin ID, implementation class, generated descriptor.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): included plugin builds.
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): secrets trong cache.
- [Gradle — Gradle Directory Layout](https://docs.gradle.org/current/userguide/directory_layout.html): User Home và init scripts.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): kiểm soát resolved versions.
