# Thu gọn trường hợp lỗi và tái hiện bản dựng độc lập ngoài IDE

## 1. Mục tiêu

Một ứng dụng Spring Boot có thể chạy tốt trong IDE nhưng thất bại khi build từ terminal hoặc CI. Cũng có trường hợp IDE báo lỗi trong khi Gradle/Maven build thành công. Nguyên nhân thường nằm ở khác biệt JDK, build tool, project model, dependency classpath, annotation processing, profiles, environment variables, working directory, cache hoặc incremental compilation.

**Tái hiện độc lập ngoài IDE** nghĩa là chạy lại đúng build bằng Gradle/Maven Wrapper từ terminal, trên đúng commit và với các đầu vào được ghi nhận. Mục tiêu là thu hẹp lỗi đến một task/giai đoạn có thể kiểm chứng, rồi tạo được một lần chạy lặp lại cho thấy lỗi còn tồn tại hoặc đã biến mất.

Quy trình trong bài:

1. Ghi nhận chính xác triệu chứng, commit, task và môi trường.
2. Phân loại lỗi: IDE import/sync, compile, test, packaging, dependency resolution hay runtime.
3. Chạy build bằng Wrapper ngoài IDE, từ root project.
4. So sánh JDK chạy build tool với compiler toolchain và Java target.
5. Tách ảnh hưởng của incremental outputs, build cache, dependency cache và repository.
6. Tái hiện trên clean checkout hoặc runner sạch mà không xóa dữ liệu người dùng.
7. Thu nhỏ task/module/configuration gây lỗi, giữ nguyên điều kiện cần thiết.
8. Ghi lại command, logs, environment và kết quả để CI hoặc developer khác chạy lại.

**Phiên bản minh họa:** Java 17, Spring Boot 3.3.13, Gradle 8.8 và Maven 3.9.9. Đây là bộ phiên bản dùng trong ví dụ, không phải tuyên bố bản mới nhất. Khi áp dụng, dùng Wrapper và plugin versions thực tế của repository.

## 2. Phân loại lỗi trước khi chạy lệnh

Đừng bắt đầu bằng cách xóa toàn bộ cache hoặc nâng JDK. Trước tiên xác định lỗi xảy ra ở giai đoạn nào.

| Giai đoạn | Dấu hiệu | Câu hỏi đầu tiên |
| --- | --- | --- |
| IDE import/sync | IDE không nhận module, dependency hoặc task | Wrapper build ngoài IDE có thành công không? |
| Configuration | Gradle/Maven không đọc build script/POM | Đúng root directory, Wrapper và plugin versions chưa? |
| Dependency resolution | Không tải được plugin/library, checksum hoặc TLS fail | Repository, proxy, credentials, version có giống CI không? |
| Compile | Java/Kotlin compiler báo lỗi | JDK/compiler toolchain, source set, annotation processor nào được dùng? |
| Test | Unit/integration test fail hoặc timeout | Test nào fail, có phụ thuộc Docker/DB/timezone/port không? |
| Packaging | Không tạo executable Boot JAR hoặc image | Task/goal repackage, resources và runtime dependencies có đúng không? |
| Runtime | Build xanh nhưng ứng dụng không start | Java runtime, external config, classpath và environment có giống deploy không? |

Phân biệt **IDE build** với **IDE run**. Nhiều IDE có thể dùng compiler riêng hoặc classpath model do IDE quản lý; nút Run có thể chạy main class từ output directory thay vì executable Boot JAR. Vì vậy “chạy được trong IDE” không đồng nghĩa JAR đã đóng gói đúng.

Ngược lại, nếu Wrapper build ngoài IDE pass nhưng IDE gạch đỏ source, kiểm project sync, language level, annotation processing và IDE JDK trước khi thay build script.

## 3. Ghi lại một lần tái hiện có thể so sánh

Trước khi thay đổi code/config, lưu các dữ kiện sau:

- Repository và commit SHA.
- Branch/tag, working tree có thay đổi hay không.
- Command đầy đủ, working directory và exit code.
- Gradle/Maven Wrapper version.
- JDK vendor, full version, architecture và JVM chạy build tool.
- Compiler toolchain, release target và test JVM nếu khác.
- OS/architecture, locale, timezone và encoding liên quan.
- Profiles, system properties và environment variables cần thiết.
- Dependency lockfiles, verification metadata và repository/mirror.
- Task/module cụ thể và log lỗi đầu tiên cùng phần `Caused by`.

Các lệnh Git cơ bản:

~~~bash
git rev-parse HEAD
git status --short
git diff --stat
git diff
~~~

`git status` và `git diff` giúp phát hiện build đang chạy trên working tree đã sửa. Không đưa file secret hoặc output nhạy cảm vào báo cáo. Nếu cần tái hiện đúng commit đã phát hành, dùng clean checkout/branch riêng thay vì vô tình build các thay đổi chưa commit.

Không dùng `git clean -xfd` như bước chẩn đoán mặc định: lệnh đó xóa cả file untracked/ignored, có thể làm mất dữ liệu local. Chọn một checkout mới hoặc worktree riêng để giữ nguyên workspace đang làm việc.

## 4. Chạy Gradle độc lập ngoài IDE

### 4.1. Luôn bắt đầu từ Gradle Wrapper

Từ thư mục root chứa `gradlew`:

~~~bash
./gradlew --version
./gradlew --no-daemon --console=plain --stacktrace clean test bootJar
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat --no-daemon --console=plain --stacktrace clean test bootJar
~~~

Giải thích:

- `./gradlew` dùng đúng Gradle distribution trong `gradle/wrapper/gradle-wrapper.properties`.
- `--no-daemon` giảm phụ thuộc vào daemon tồn tại lâu giữa các lần chạy; Gradle vẫn có thể tạo single-use daemon khi cần JVM arguments.
- `--console=plain` giúp log dễ đọc/lưu trong CI.
- `--stacktrace` in stack trace khi build fail.
- `clean test bootJar` kiểm tra compile/test/package theo task graph của project.

Nếu dự án có nhiều module, gọi task đúng module, ví dụ:

~~~bash
./gradlew --no-daemon --console=plain :service:clean :service:test :service:bootJar
~~~

`service` chỉ là tên module minh họa. Xem `./gradlew projects` và `./gradlew tasks --all` để tìm project/task path thật.

### 4.2. Phân tách task để tìm điểm fail

Thay vì luôn chạy cả build, chạy từng lớp:

~~~bash
./gradlew --no-daemon --console=plain help
./gradlew --no-daemon --console=plain :service:compileJava
./gradlew --no-daemon --console=plain :service:test
./gradlew --no-daemon --console=plain :service:bootJar
~~~

Cách đọc:

- `help` fail: thường nằm ở settings/build script, plugin resolution hoặc configuration.
- `compileJava` fail: tập trung source, JDK/toolchain, generated sources và annotation processors.
- `test` fail: tập trung test runtime, fixtures, external services và tính ổn định của tests.
- `bootJar` fail sau khi test pass: xem packaging, resources, duplicate entries và task configuration.

Gradle có thể cấu hình toàn bộ project trước khi chạy một task; do đó task compile fail chưa chắc lỗi nằm trong file Java. Đọc phần đầu log và stack trace để tìm task/action đầu tiên thất bại.

### 4.3. Dùng log chi tiết đúng lúc

~~~bash
./gradlew --no-daemon --console=plain --stacktrace --info :service:compileJava
~~~

`--info` tăng thông tin về task execution và dependency resolution. Chỉ dùng `--debug` khi cần thiết vì log rất dài và có thể chứa đường dẫn, property hoặc dữ liệu nhạy cảm. Không đăng nguyên log công khai trước khi rà soát secrets, URLs nội bộ và tokens.

Gradle Build Scan có thể giúp phân tích task graph/performance, nhưng việc publish scan có thể gửi metadata ra dịch vụ bên ngoài. Chỉ bật theo policy bảo mật của tổ chức.

### 4.4. Buộc chạy lại task để loại trừ incremental/cache

~~~bash
./gradlew --no-daemon --console=plain --rerun-tasks --no-build-cache :service:test
~~~

- `--rerun-tasks` yêu cầu chạy lại tasks thay vì dùng trạng thái up-to-date.
- `--no-build-cache` ngăn lấy task outputs từ Gradle build cache cho invocation này.
- `clean` xóa project build outputs theo task clean; không xóa toàn bộ Gradle User Home.

Nếu lỗi chỉ xuất hiện khi dùng incremental compilation hoặc cache, giữ nguyên command tối thiểu tái hiện và kiểm task inputs/outputs, generated sources, plugin behavior. Không kết luận “cache hỏng” chỉ vì build lại một lần thì pass.

### 4.5. Kiểm tra dependency resolution riêng

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Thay `spring-core` bằng artifact nghi ngờ. Xem version được chọn, lý do conflict resolution, constraints, BOM/platform và repository. Nếu lỗi là dependency download:

~~~bash
./gradlew --refresh-dependencies :service:compileJava
~~~

`--refresh-dependencies` yêu cầu Gradle kiểm tra lại dependency metadata/artifacts theo cơ chế cache; không phải lệnh xóa sạch mọi cache và cũng không chữa được repository/proxy sai. Chỉ dùng khi có lý do nghi ngờ metadata hoặc artifact cache stale.

### 4.6. Offline mode là một phép thử riêng

~~~bash
./gradlew --offline :service:compileJava
~~~

Nếu offline build fail vì dependency chưa có trong cache, điều đó chỉ cho biết cache local không đủ. Nó **không chứng minh** build online sẽ fail hoặc dependency version sai. Dùng offline mode để chẩn đoán khả năng phụ thuộc network/cache, không dùng nó làm bước build chuẩn nếu CI cần tải dependencies.

## 5. Chạy Maven độc lập ngoài IDE

### 5.1. Maven Wrapper

Từ root chứa `mvnw`:

~~~bash
./mvnw --version
./mvnw -B -ntp -e clean verify
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd -B -ntp -e clean verify
~~~

Ý nghĩa:

- `./mvnw` pin Maven distribution của project.
- `-B` bật batch mode, phù hợp CI.
- `-ntp` giảm transfer progress noise.
- `-e` in exception details.
- `clean verify` chạy lifecycle phases đến verify theo cấu hình POM.

Nếu chỉ muốn kiểm compile/package mà không chạy test execution:

~~~bash
./mvnw -B -ntp -DskipTests package
~~~

`-DskipTests` bỏ qua chạy tests nhưng thông thường vẫn compile test sources. `-Dmaven.test.skip=true` có thể bỏ cả test compilation; không dùng hai lựa chọn như thể chúng tương đương. Release gate cuối cùng vẫn phải chạy tests theo policy.

### 5.2. Tách Maven phases

~~~bash
./mvnw -B -ntp validate
./mvnw -B -ntp -DskipTests compile
./mvnw -B -ntp test
./mvnw -B -ntp package
./mvnw -B -ntp verify
~~~

Nếu `validate` fail, xem POM/profiles/plugins. `compile` fail tập trung Java compiler/source/generated code. `test` fail tập trung test runtime. `package` fail có thể do Spring Boot repackage/packaging plugin. `verify` có thể chạy integration/quality gates được cấu hình riêng.

### 5.3. Effective POM và active profiles

~~~bash
./mvnw -B -ntp help:active-profiles
./mvnw -B -ntp help:effective-pom -Doutput=target/effective-pom.xml
~~~

Effective POM cho thấy cấu hình sau khi kế thừa parent, profiles và plugin management. So sánh local/CI để phát hiện profile tự kích hoạt theo JDK, OS hoặc property. File effective POM có thể chứa URLs/properties nội bộ; rà soát trước khi chia sẻ.

### 5.4. Dependency tree

~~~bash
./mvnw -B -ntp dependency:tree -Dscope=runtime
~~~

Nếu một dependency cụ thể có version bất ngờ, kiểm dependency management, exclusions, BOM import và transitive paths. Không nâng hàng loạt dependencies chỉ để làm log sạch; xác định artifact gây xung đột trước.

### 5.5. Maven debug log

~~~bash
./mvnw -B -ntp -X -DskipTests compile
~~~

`-X` in debug details của Maven/plugin/resolver và có thể làm lộ environment, repository URLs hoặc properties. Chỉ dùng trong môi trường an toàn, rà soát/redact trước khi gửi log. Bắt đầu với `-e`; bật `-X` khi stack trace thông thường chưa đủ.

## 6. So sánh JDK của IDE, build tool và compiler

Một project có thể có nhiều Java installations cùng lúc:

| Giá trị | Ý nghĩa | Cách kiểm tra |
| --- | --- | --- |
| IDE Project SDK | JDK mà IDE dùng để phân tích/chạy code | IDE project settings |
| IDE Gradle JVM | JVM chạy Gradle khi build từ IDE | IDE Gradle settings |
| Gradle launcher/daemon JVM | JVM chạy Gradle process ngoài IDE | `./gradlew --version` |
| Gradle Java toolchain | JDK được JavaCompile/Test tasks chọn | `./gradlew javaToolchains` |
| Maven JVM | JVM chạy Maven process | `./mvnw --version` |
| Maven compiler/toolchain | JDK dùng để compile khi cấu hình toolchain | POM và Maven Toolchains |
| Runtime JVM | JVM chạy JAR/container sau deploy | `java -version` hoặc runtime diagnostics |

### 6.1. Gradle toolchain và release

Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Kotlin DSL:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Toolchain chọn JDK cho task; `options.release` ràng buộc Java APIs và bytecode target. Nếu IDE dùng compiler riêng, hãy cấu hình IDE delegate build/run cho Gradle hoặc đồng bộ language level/annotation processing để kết quả không khác CLI.

### 6.2. Maven compiler release và toolchains

Trong POM:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Thuộc tính release không cài JDK. Maven Compiler Plugin cần JDK đủ khả năng hỗ trợ `--release 17`. Nếu Maven process chạy bằng JDK khác, xem Maven Toolchains Plugin và file `toolchains.xml` trên runner. Không commit absolute JDK paths của máy developer vào repository.

### 6.3. Chạy probe Java độc lập

Tạo file `BuildEnvironmentProbe.java`:

~~~java
public final class BuildEnvironmentProbe {

    public static void main(String[] args) {
        System.out.println("java.feature=" + Runtime.version().feature());
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("java.vm.name=" + System.getProperty("java.vm.name"));
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("user.dir=" + System.getProperty("user.dir"));
        System.out.println("file.encoding=" + System.getProperty("file.encoding"));
    }
}
~~~

Biên dịch/chạy bằng JDK 17:

~~~bash
javac --release 17 BuildEnvironmentProbe.java
java BuildEnvironmentProbe
~~~

Output có dạng:

~~~text
java.feature=17
java.version=17.0.x
java.vendor=<vendor của JDK đang chạy>
java.vm.name=<tên JVM>
os.name=<tên hệ điều hành>
os.arch=<kiến trúc>
user.dir=<thư mục chạy>
file.encoding=UTF-8
~~~

Các giá trị trong dấu `<...>` thay đổi theo môi trường; chỉ `java.feature=17` được kỳ vọng khi chạy bằng Java 17. Đây là Java SE program độc lập, không phụ thuộc Spring Boot hay IDE. Nó giúp kiểm JVM thực thi probe, không tự nhận diện JDK mà Gradle toolchain chọn nếu probe không được chạy qua task đó.

## 7. Tái hiện trên clean checkout

Nếu lỗi có thể đến từ file generated, output cũ hoặc thay đổi chưa commit, chạy trên checkout mới. Có thể dùng clone riêng hoặc Git worktree.

Ví dụ tạo worktree tách biệt tại commit cần điều tra:

~~~bash
git worktree add --detach ../repro-build <commit-sha>
cd ../repro-build
git status --short
./gradlew --no-daemon --console=plain clean test bootJar
~~~

`<commit-sha>` là commit thật cần tái hiện, không phải chuỗi có thể copy. Worktree chia sẻ Git object store nhưng có working directory riêng; Gradle/Maven caches vẫn có thể được dùng chung nếu không cô lập.

Để xóa worktree sau khi hoàn tất:

~~~bash
git worktree remove ../repro-build
~~~

Chỉ chạy lệnh remove sau khi xác nhận worktree đó không còn cần thiết và không chứa thay đổi cần giữ. Không xóa worktree của người khác hoặc thư mục chưa được tạo cho lần tái hiện này.

### 7.1. Vì sao clean checkout quan trọng?

Nó giúp loại các nguyên nhân:

- IDE hoặc developer đã tạo generated sources không được commit.
- File ignored local được build script đọc.
- Build output cũ che thiếu task dependency.
- File path khác nhau do case sensitivity.
- Một resource hoặc config có mặt trên máy nhưng không có trong Git.
- Build dựa vào file chưa commit hoặc local plugin.

Nếu lỗi chỉ tái hiện trên checkout sạch, tập trung vào build inputs thực sự được version control hoặc external dependencies. Nếu chỉ tái hiện trên workspace cũ, điều tra ignored/generated files và cache cụ thể thay vì xóa cả repository.

### 7.2. Cô lập Gradle User Home

Để kiểm tra ảnh hưởng của Gradle caches/distribution đã tải, tạo Gradle User Home riêng:

~~~bash
ISOLATED_GRADLE_HOME="$(mktemp -d)"
GRADLE_USER_HOME="$ISOLATED_GRADLE_HOME" ./gradlew --no-daemon --console=plain clean test bootJar
STATUS=$?
rm -rf "$ISOLATED_GRADLE_HOME"
exit "$STATUS"
~~~

Lệnh tạo môi trường Gradle cache mới nên Wrapper có thể tải lại Gradle distribution và dependencies; cần network/repository access. Nếu dùng shell có `set -e`, hãy điều chỉnh cleanup để vẫn chạy khi build fail. Không đặt `GRADLE_USER_HOME` vào thư mục chứa dữ liệu người dùng khác.

### 7.3. Cô lập Maven local repository

~~~bash
ISOLATED_M2="$(mktemp -d)"
./mvnw -B -ntp -Dmaven.repo.local="$ISOLATED_M2" clean verify
STATUS=$?
rm -rf "$ISOLATED_M2"
exit "$STATUS"
~~~

Maven sẽ tải lại artifacts vào local repository tạm. User/global `settings.xml`, mirrors và environment vẫn có thể ảnh hưởng; đây không phải môi trường hoàn toàn độc lập. Nếu lỗi chỉ xảy ra với repository tạm, kiểm quyền truy cập, proxy, credentials và repository policy.

Không xóa `~/.gradle` hoặc `~/.m2` của developer chỉ để thử giả thuyết cache. Cache tạm cho phép kiểm chứng mà không phá dữ liệu hiện tại.

## 8. IDE build khác command line ở đâu?

### 8.1. IDE import/sync

IDE tạo project model từ Gradle/Maven. Nếu sync fail nhưng CLI build pass, kiểm:

- IDE có nhận đúng root project và Wrapper không?
- IDE dùng Gradle JVM/Maven JDK nào?
- IDE có đang offline hoặc dùng repository/mirror khác?
- IDE có import đúng included builds/subprojects không?
- Annotation processing có bật và đúng processor path không?
- IDE cache/index có stale sau khi đổi dependency/plugin không?

Chỉ refresh/reimport project model sau khi xác nhận build script/Wrapper hoạt động ngoài IDE. Không thay source code để chữa một lỗi chỉ nằm ở IDE indexing.

### 8.2. IDE compile khác Gradle/Maven compile

IDE có thể dùng compiler nội bộ, output directory riêng và incremental compiler riêng. Nếu CLI fail còn IDE pass, chạy đúng compile task ngoài IDE và xem annotation processors, generated sources, Java release, source sets và compiler flags.

Nếu CLI pass nhưng IDE compile fail, so sánh project SDK, language level, annotation processing, module classpath và IDE build delegation.

### 8.3. IDE Run khác executable JAR

IDE có thể launch class main từ `build/classes`/`target/classes` cùng IDE-managed classpath. Để xác minh packaging, phải chạy:

~~~bash
java -jar build/libs/app.jar
~~~

hoặc Maven output tương ứng. Không lấy kết quả IDE Run làm bằng chứng `bootJar`/`repackage` đúng.

## 9. Thu nhỏ trường hợp lỗi mà không làm mất nguyên nhân

Một reproducer tốt là nhỏ nhất nhưng vẫn giữ được điều kiện gây lỗi. Nếu xóa dependency/config/plugin gây lỗi, reproducer pass sẽ không còn chứng minh vấn đề ban đầu.

Quy trình:

1. **Chốt baseline:** ghi commit, command, JDK, OS, profile và lỗi nguyên bản.
2. **Tách phase:** configuration → dependency resolution → compile → test → package → runtime.
3. **Tách module/task:** chạy task đúng module, không chạy toàn repository nếu chỉ một module fail.
4. **Tắt một yếu tố có kiểm soát:** ví dụ build cache, incremental task hoặc profile, mỗi lần chỉ thay một yếu tố.
5. **So sánh kết quả:** giữ lại command và log cho cả trạng thái fail/pass.
6. **Tạo reproducer:** chỉ giữ class, dependency, config và task cần để lỗi tái hiện.
7. **Kiểm lại:** chạy reproducer trên clean checkout/runner và ghi điều kiện tối thiểu.

### 9.1. Một biến mỗi lần

Ví dụ lỗi chỉ xảy ra trên Gradle incremental compile. Thử lần lượt:

~~~bash
./gradlew :service:compileJava
./gradlew --rerun-tasks :service:compileJava
./gradlew --rerun-tasks --no-build-cache :service:compileJava
./gradlew clean :service:compileJava
~~~

Nếu chỉ một command pass, ghi rõ trạng thái cache/task và kiểm generated sources/plugin inputs. Không kết luận ngay rằng Gradle compiler bug; có thể task custom khai báo inputs/outputs không đầy đủ.

### 9.2. Tách dependency khỏi code

Nếu compile fail sau khi nâng một library:

~~~bash
./gradlew dependencyInsight --dependency library-name --configuration compileClasspath
~~~

Maven:

~~~bash
./mvnw dependency:tree -Dincludes=groupId:artifactId
~~~

Xác định version được chọn và đường transitive. Sau đó thử pin version trước/sau có kiểm soát, giữ lockfile/commit riêng để biết thay đổi nào làm lỗi xuất hiện.

### 9.3. Giữ nguyên generated sources và annotation processors

Lỗi có thể chỉ xuất hiện khi Lombok, MapStruct hoặc annotation processor tạo code. Kiểm annotation processor path, compiler plugin, generated-source directories và IDE annotation processing. Không xóa generated sources cần thiết khỏi reproducer; thay vào đó chứng minh task tạo chúng chạy đúng từ CLI.

### 9.4. Multi-module project

Gradle:

~~~bash
./gradlew projects
./gradlew :api:compileJava
./gradlew :service:test
./gradlew :service:bootJar
~~~

Maven:

~~~bash
./mvnw -pl service -am -DskipTests package
~~~

`-pl` chọn project/module, `-am` build các module mà module đó phụ thuộc. Thay `api`/`service` bằng tên thật. Nếu task chỉ fail khi chạy root build, kiểm shared convention plugins, root configuration, task ordering và project dependency graph.

## 10. Environment variables, profiles và working directory

### 10.1. Spring profiles

IDE run configuration có thể tự đặt `SPRING_PROFILES_ACTIVE=dev`; terminal không có biến này. Hoặc terminal có `SPRING_CONFIG_LOCATION` trỏ tới file không tồn tại trong CI.

In allowlist biến cần kiểm tra, không dump toàn bộ environment:

~~~bash
printf 'SPRING_PROFILES_ACTIVE=%s\n' "$SPRING_PROFILES_ACTIVE"
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
printf 'TZ=%s\n' "$TZ"
~~~

PowerShell:

~~~powershell
"SPRING_PROFILES_ACTIVE=$env:SPRING_PROFILES_ACTIVE"
"JAVA_HOME=$env:JAVA_HOME"
"TZ=$env:TZ"
~~~

Nếu biến chưa được đặt, shell có thể in chuỗi rỗng; cần phân biệt empty với unset khi ứng dụng có behavior khác nhau. Không in passwords, access tokens, private keys, full Maven settings hoặc toàn bộ environment vào public CI logs.

### 10.2. Working directory và file tương đối

IDE có thể đặt working directory là module root trong khi CLI chạy từ repository root. Các đường dẫn tương đối như `./config/app.yml`, `./data/seed.json` hoặc `./certs/ca.pem` vì vậy có thể resolve khác nhau.

Ghi `pwd`/`Get-Location`, kiểm path được truyền cho app và xác định resource nào phải nằm trong JAR, external config mount hay working directory. Không sửa bằng cách copy mọi file local sang CI; xác định contract cần thiết.

### 10.3. Locale, timezone và encoding

Một task có thể tạo output khác do locale, timezone, default charset hoặc line endings. Nếu output phụ thuộc các yếu tố này, chuẩn hóa rõ trong CI và test trên OS mục tiêu. Không giả định Windows/Linux có cùng path separator, case sensitivity hoặc permission semantics.

### 10.4. Proxy, TLS và repository

Nếu IDE dùng proxy/certificate store riêng còn CLI không dùng, dependency resolution có thể khác. Kiểm:

- Gradle/Maven repository URLs và mirror settings.
- Proxy variables và JVM proxy properties.
- Truststore/corporate CA configuration.
- DNS/firewall/registry access.
- Repository credentials có được inject trong CI không.

Không tắt TLS verification hoặc chuyển sang HTTP để “xem build có chạy không”. Nếu cần kiểm network, dùng approved mirror và CA configuration đúng.

## 11. Phân biệt lỗi build với lỗi runtime

Nếu `clean test bootJar` thành công nhưng ứng dụng không chạy, đó là một failure phase khác. Kiểm JAR:

~~~bash
jar tf build/libs/app.jar
unzip -p build/libs/app.jar META-INF/MANIFEST.MF
java -version
java -jar build/libs/app.jar
~~~

Executable Spring Boot JAR thường có `BOOT-INF/classes`, `BOOT-INF/lib`, `Main-Class` launcher và `Start-Class` application class. Đọc manifest thực tế vì loader class names có thể thay đổi theo Spring Boot version.

Nếu lỗi `UnsupportedClassVersionError`, kiểm `javap -verbose` class liên quan và runtime Java. Nếu lỗi config, kiểm active profile/external file. Nếu lỗi kết nối DB, kiểm URL, credentials, DNS, port và schema. Không thay compiler target khi lỗi thực chất là thiếu runtime config.

Với container image, kiểm image ID/digest, entrypoint, user, port mapping, logs và health endpoint. Host JDK/IDE settings không xác định JVM đã đóng trong image.

## 12. Lưu logs và chia sẻ reproducer an toàn

Một bug report hữu ích có:

- Commit SHA và trạng thái working tree.
- OS/architecture và JDK vendor/full version.
- Gradle/Maven Wrapper version.
- Command đầy đủ, task/module và exit code.
- Phần log đầu tiên báo task fail, stack trace và `Caused by`.
- Profile/config names đã dùng, nhưng không kèm secrets.
- Dependency version liên quan và effective POM/dependency insight khi cần.
- Kết quả trên clean checkout và runner CI.
- Kết quả khi tắt/bật cache/incremental mode nếu có liên quan.

Trước khi gửi log:

- Redact tokens, passwords, authorization headers và private URLs.
- Không gửi `settings.xml`, `gradle.properties`, keystore hoặc `.env` chứa credentials.
- Không chia sẻ Build Scan/CI run private nếu người nhận không có quyền.
- Giữ lại thông tin cần để tái hiện: version, task, module, profile và dependency coordinates.

Nếu bug cần reproducer, tạo một branch/commit riêng có đúng file tối thiểu. Không gửi nguyên repository nếu chỉ cần một class và build script nhỏ.

## 13. CI làm chuẩn tái hiện độc lập

CI nên chạy cùng Wrapper command từ clean checkout để tạo một baseline có thể so sánh:

Gradle:

~~~bash
./gradlew --no-daemon --console=plain clean check bootJar
~~~

Maven:

~~~bash
./mvnw -B -ntp -C clean verify
~~~

Ghi lại commit SHA, Wrapper version, JDK version/vendor, runner OS/architecture và command. Nếu CI pass nhưng local CLI fail, so sánh các đầu vào này; nếu cả hai fail giống nhau, dùng stack trace/task graph để thu hẹp nguyên nhân.

Không rebuild một artifact khác ở bước smoke/deploy nếu mục tiêu là kiểm chính artifact đã build. Upload/download đúng JAR, xác minh checksum, chạy JAR ngoài IDE và ghi digest. Với image, verify và test đúng digest, không chỉ tag mutable.

Build Scan, effective POM, dependency tree và CI logs có thể giúp chẩn đoán nhưng cần tuân thủ data policy. Không bật quyền publish/signing cho workflow chạy code từ pull request không tin cậy.

## 14. Troubleshooting nhanh

| Triệu chứng | Nguyên nhân thường gặp | Hành động tiếp theo |
| --- | --- | --- |
| IDE pass, `./gradlew` fail | IDE dùng JDK/classpath/profile khác | Chạy Wrapper với `--version`, so sánh toolchain và profile |
| IDE báo lỗi nhưng CLI pass | IDE sync/index/compiler riêng | Reimport đúng Wrapper, kiểm Project SDK và annotation processing |
| Gradle `help` fail | Settings/plugin/configuration | Kiểm root directory, plugin versions và repository |
| Maven `validate` fail | POM/profile/extension | Xem effective POM và active profiles |
| Dependency resolution fail | Proxy/TLS/mirror/credentials/version | Kiểm repository access và trust config |
| `compileJava` fail | Compiler JDK, API release, generated code | Kiểm toolchain, `options.release`, processors |
| Test fail chỉ trên CI | Timezone, ports, Docker, external services, race | Kiểm test assumptions và runner environment |
| `bootJar` fail nhưng compile pass | Packaging/resources/manifest | Kiểm Boot plugin, duplicate resources và archive tasks |
| Build pass khi không clean | Output cũ hoặc task inputs/outputs sai | Thử clean checkout, `--rerun-tasks`, `--no-build-cache` |
| Build fail chỉ khi clean | File generated/ignored hoặc dependency cache | Kiểm generated inputs, repository và task dependencies |
| Build pass với cache, fail cache trống | Phụ thuộc local cache hoặc network/repository | Dùng isolated cache, kiểm mirror và dependency versions |
| Gradle offline fail | Artifact chưa có trong cache | Không coi đây là bằng chứng online build fail |
| Maven dependency version khác IDE | Profile/BOM/settings khác | `help:active-profiles`, `effective-pom`, `dependency:tree` |
| Java class major khác mong đợi | Compiler toolchain/release sai | Kiểm `javap -verbose` và compiler configuration |
| Chỉ module con fail | Project path/parent configuration | Dùng task path chính xác, `-pl ... -am` với Maven |
| JAR chạy trong IDE nhưng `java -jar` fail | Chưa repackage hoặc thiếu runtime dependency | Kiểm executable archive/manifest |
| Local pass, clean checkout fail | File untracked/ignored hoặc generated output | Tạo clean checkout và xác định input thiếu |
| Linux fail, Windows pass | Case-sensitive paths, permissions, shell assumptions | Kiểm tên file, executable bit và native dependencies |
| Debug logs lộ credentials | Log verbosity quá cao hoặc dump environment | Redact logs, chỉ in allowlist diagnostics |

## 15. Bài tập thực hành có đáp án

### Bài 1 — IDE pass, CLI fail

IDE chạy được ứng dụng nhưng `./gradlew clean test` báo compile error. Bạn kiểm tra gì trước?

**Đáp án:** `./gradlew --version`, Java toolchains, compiler release, annotation processors, source sets và đúng project root. IDE có thể dùng compiler/classpath khác.

### Bài 2 — Gradle task up-to-date

Build pass nếu chạy bình thường nhưng fail khi dùng `--rerun-tasks`. Điều đó gợi ý gì?

**Đáp án:** có thể task incremental/cache đang che một vấn đề hoặc task custom khai báo inputs/outputs sai. Giữ command fail và kiểm task outputs/generated sources; không kết luận ngay cache corruption.

### Bài 3 — Maven profile

Local pass nhưng CI fail do thiếu database URL. Cách so sánh profile?

**Đáp án:** dùng `help:active-profiles` và `help:effective-pom`, kiểm environment/system properties và settings. Không đưa password vào log.

### Bài 4 — JDK mismatch

`./gradlew --version` cho thấy Gradle 8.8 nhưng JVM 21. Project compile Java 17. Có chắc build sai không?

**Đáp án:** không. Gradle daemon có thể chạy JDK 21 trong khi Java toolchain compile bằng JDK 17. Kiểm `javaToolchains` và `options.release`, sau đó kiểm bytecode.

### Bài 5 — Build chỉ fail trên clean checkout

Nguyên nhân thường gặp?

**Đáp án:** build đang dựa vào file untracked/ignored, generated source không được tạo đúng task, config local hoặc dependency chỉ có trong cache. Xác định input thiếu, không copy toàn bộ workspace vào CI.

### Bài 6 — Maven `-DskipTests`

Lệnh này có chứng minh test compile pass không?

**Đáp án:** Maven Surefire thường bỏ chạy tests nhưng vẫn compile test sources. `maven.test.skip=true` có thể bỏ cả test compilation. Đọc plugin behavior và dùng `verify` để release gate.

### Bài 7 — Dependency refresh

Gradle build fail khi tải dependency. Có nên chạy `--refresh-dependencies` ngay?

**Đáp án:** trước hết xác định artifact/version/repository và lỗi network. Chỉ refresh khi nghi ngờ metadata/artifact cache stale; flag không sửa proxy/TLS/credentials hoặc dependency version sai.

### Bài 8 — Debug logs

CI yêu cầu Maven `-X`, có thể upload toàn bộ log công khai không?

**Đáp án:** không. Debug log có thể chứa URLs, properties và dữ liệu nhạy cảm. Rà soát/redact, chỉ chia sẻ với người có quyền.

### Bài 9 — Multi-module

Chỉ module `service` fail nhưng root build có 40 modules. Cách thu hẹp?

**Đáp án:** Gradle dùng `:service:compileJava`/`:service:test`; Maven dùng `-pl service -am` để build module và các module cần thiết.

### Bài 10 — Clean có xóa hết cache không?

**Đáp án:** không. Gradle/Maven `clean` dọn project build outputs (`build/`/`target/`), không xóa toàn bộ Gradle User Home hoặc Maven local repository. Dùng cache riêng nếu cần kiểm giả thuyết.

## 16. Checklist tái hiện lỗi trước khi mở bug/PR

- [ ] Ghi commit SHA, branch và working-tree status.
- [ ] Ghi chính xác command, root directory, task/module và exit code.
- [ ] Dùng Gradle/Maven Wrapper đã commit, không dựa vào global build tool.
- [ ] Ghi JDK vendor/version, JVM chạy build tool và compiler toolchain.
- [ ] Ghi OS/architecture, locale/timezone/encoding khi liên quan.
- [ ] Xác định lỗi thuộc IDE sync, configuration, dependency, compile, test, packaging hay runtime.
- [ ] Thu thập stack trace và `Caused by` đầu tiên có ý nghĩa.
- [ ] Tách task/module để thu hẹp phạm vi.
- [ ] Chỉ thay một yếu tố mỗi lần: cache, profile, JDK, dependency hoặc environment.
- [ ] Dùng clean checkout/worktree để loại file local và generated outputs cũ.
- [ ] Nếu cần, dùng Gradle User Home/Maven local repo tạm; không xóa cache người dùng.
- [ ] Kiểm effective POM, active profiles, dependency tree hoặc Gradle dependency insight khi cần.
- [ ] Kiểm JAR/image thật nếu build pass nhưng runtime fail.
- [ ] Redact secrets trước khi chia sẻ logs, scans hoặc effective configuration.
- [ ] Tạo reproducer tối thiểu nhưng vẫn giữ điều kiện gây lỗi.
- [ ] Xác nhận người khác/CI có thể chạy lại đúng command và nhận cùng kết quả.

**Kết luận:** Để thu hẹp lỗi build, trước hết phân loại failure phase rồi chạy đúng Gradle/Maven Wrapper ngoài IDE trên đúng commit. So sánh JVM chạy build tool với compiler toolchain, tách dependency resolution khỏi compile/test/package, và dùng clean checkout hoặc cache tạm để kiểm chứng giả thuyết mà không phá workspace. Một reproducer tốt giữ nguyên điều kiện gây lỗi, ghi lại command/environment và có thể chạy lại trên CI hoặc máy khác.

## 17. Tài liệu chính thức

- Gradle — Command-Line Interface: https://docs.gradle.org/current/userguide/command_line_interface.html
- Gradle — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Dependency Management: https://docs.gradle.org/current/userguide/dependency_management.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Multi-Project Builds: https://docs.gradle.org/current/userguide/multi_project_builds.html
- Apache Maven — CLI Options: https://maven.apache.org/ref/current/maven-embedder/cli.html
- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — Profiles: https://maven.apache.org/guides/introduction/introduction-to-profiles.html
- Apache Maven — Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Apache Maven — Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains.html
- Spring Boot 3.3 — Gradle Plugin: https://docs.spring.io/spring-boot/3.3/gradle-plugin/
- Spring Boot 3.3 — Maven Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/

Các options CLI và IDE settings thay đổi theo phiên bản. Hãy đối chiếu tài liệu đúng Wrapper/plugin đang pin, lưu command tái hiện chính xác và tránh chia sẻ logs/config có secrets.