# Phát hiện deprecation trước khi nâng cấp Gradle

Một build đang báo **`BUILD SUCCESSFUL`** không có nghĩa nó đã sẵn sàng cho phiên bản Gradle tiếp theo. Gradle thường **đánh dấu tính năng/API là deprecated trước khi loại bỏ hoặc thay đổi hành vi**. Ở phiên bản hiện tại, build có thể vẫn chạy; sau khi nâng Gradle Wrapper, chính lời gọi đó có thể biến thành lỗi configuration, task execution hoặc plugin compilation. Việc **kiểm tra deprecation trước khi nâng cấp** giúp chuyển một lần nâng cấp “cầu may” thành một chuỗi thay đổi có chứng cứ, có người chịu trách nhiệm và có kiểm thử hồi quy.

Bài thuộc phần **Nâng cấp và di chuyển** của chủ đề *Build Tool Gradle*. Trọng tâm là cơ chế cảnh báo deprecation, cách thu thập thông tin bằng **`--warning-mode=all`, `--warning-mode=fail`, Problems Report, Build Scan**, cách phát hiện trong mọi task path chứ không chỉ `help`, cách xác định cảnh báo do chính build logic hay third-party plugin, cách lập kế hoạch sửa trước khi nâng Gradle Wrapper, và cách tạo một CI gate. Có **ví dụ Gradle Kotlin DSL + Java 17 + JUnit 5 chạy được** với tình huống deprecated task thật trong Gradle 9.x, kèm phiên bản sửa đúng, lệnh Bash/PowerShell, expected output, lỗi phổ biến và bài tập.

**Bối cảnh phiên bản:** tài liệu chính thức tại thời điểm biên soạn tháng 11/2026 giới thiệu **Gradle 9.9.0**. Một số deprecations trong dòng 9.x được tài liệu chỉ rõ sẽ trở thành lỗi hoặc bị loại bỏ ở **Gradle 10**; một số khác dự kiến ở **Gradle 11**. Không tự mặc định mọi deprecation đều bị xóa ngay ở bản kế tiếp. Khi làm dự án thật, luôn tra *Upgrade Guide* của **phiên bản đang chạy** và **phiên bản mục tiêu**, cũng như tương thích JDK/plugin, trước khi nâng.

## 1. Deprecation là gì, vì sao phải xử lý trước?

**Deprecation** là thông báo rằng một API, cú pháp, task, hành vi hay tính năng **không còn được khuyến khích sử dụng và có kế hoạch thay đổi/loại bỏ**. Đây là tín hiệu sớm, không nhất thiết là lỗi ở phiên bản Gradle đang dùng.

Ví dụ tiến trình khái niệm:

~~~text
Gradle phiên bản X:
  legacy behavior vẫn chạy
  => warning: feature deprecated
  => docs hướng dẫn migration

Gradle phiên bản Y (ở tương lai):
  behavior/API bị xóa hoặc thay đổi
  => build đang dùng legacy behavior có thể fail

Migration an toàn:
  phát hiện warning khi vẫn ở X
  -> tìm owner và khuyến nghị thay thế
  -> sửa build logic/plugin
  -> test behavior trên X
  -> mới thử nâng Wrapper lên Y
~~~

Một số khác biệt quan trọng:

| Khái niệm | Ví dụ | Điều cần làm |
| --- | --- | --- |
| Gradle deprecation | Task `buildNeeded` đang deprecated trong Gradle 9.x | Tra Gradle Upgrade Guide, dùng task/workflow thay thế |
| Plugin deprecation | Plugin bên thứ ba gọi Gradle API deprecated | Nâng plugin, xem changelog; nếu tự viết plugin thì sửa API |
| Java `@Deprecated` | Java source dùng API JDK deprecated | Compiler `-Xlint:deprecation`, xét Java/JDK migration riêng |
| Kotlin/Groovy compiler warning | Script/plugin compile với API đã đánh dấu deprecated | Sửa mã build logic theo API tương ứng |
| Breaking change không có warning | Internal Gradle API biến đổi, plugin không tương thích | Chạy compatibility smoke tests; deprecation audit không bảo đảm bắt hết |
| Task validation problem | Task thiếu `@Input`/`@OutputFile` hoặc implicit dependency | Sửa task model; không phải mọi validation problem đều là deprecation |
| Configuration Cache problem | Task action truy cập `Project` model sai lifecycle | Sửa build logic; một số hành vi có thể đồng thời bị deprecated |

**Deprecation warning không phải “test fail” theo mặc định.** Task có thể hoàn thành, tạo JAR hợp lệ nhưng cuối log vẫn có summary “Deprecated Gradle features were used ...”. Đó là khoản nợ nâng cấp cần ghi nhận.

## 2. Ba nguồn cảnh báo chính trong Gradle build

1. **Build scripts/settings/init scripts**: `build.gradle.kts`, `settings.gradle.kts`, `gradle.properties`, init scripts trong `~/.gradle/init.d` hoặc CI.
2. **Build logic/plugin code**: `buildSrc`, included build `build-logic`, precompiled convention plugin, binary plugin Java/Kotlin/Groovy, các third-party Gradle plugins.
3. **Cách sử dụng một task/feature**: lệnh CLI hoặc task graph lựa chọn deprecated tasks/configurations, publication, composite build, Tooling API model resolution.

Vì sao một lần chạy `./gradlew help` chưa đủ?
- Nó **chủ yếu đi qua settings/configuration** và có thể không chọn một task deprecated.
- Một plugin có thể chỉ gọi deprecated API khi `publish`, `test`, `check`, `distZip` hoặc custom task chạy.
- Một deprecation có thể chỉ xảy ra khi IDE dùng Tooling API để đồng bộ project model, không phải khi CLI chạy `help`.
- CI release và local dev có thể dùng init scripts, environment variables, project properties hoặc Gradle plugins khác nhau.

Vì vậy cần **quét theo các đường đi thực tế**, sau đó tổng hợp tập cảnh báo và owner; không dùng duy nhất một câu lệnh làm bằng chứng “toàn dự án không có deprecation”.

## 3. `--warning-mode`: lệnh quan trọng nhất

Gradle CLI có tùy chọn `--warning-mode=<mode>` với bốn mode:

| Mode | Cách hiển thị | Khi dùng |
| --- | --- | --- |
| `summary` | Ẩn chi tiết từng warning, hiện summary cuối build | Mặc định cho log gọn |
| `all` | In chi tiết những warnings Gradle báo qua cơ chế này | **Audit/chẩn đoán** trước nâng cấp |
| `fail` | In warnings và **làm build thất bại khi có warning thuộc hệ thống cảnh báo này** | **Quality gate** sau khi đã xử lý |
| `none` | Không in warnings/summary | Chỉ phù hợp trường hợp rất đặc biệt; không nên dùng khi audit |

Đây là warning mode của **Gradle**, không tự động biến mọi dòng `logger.warn` tùy ý của plugin, mọi cảnh báo `javac` hoặc mọi log của shell command thành một deprecation có khả năng được gate. Hãy phân biệt hệ thống warning/reporting thực tế.

Bash hoặc PowerShell từ project root:

~~~bash
./gradlew help --warning-mode=all
./gradlew build --warning-mode=all
./gradlew test --warning-mode=fail
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat help --warning-mode=all
.\gradlew.bat build --warning-mode=all
.\gradlew.bat test --warning-mode=fail
~~~

Dạng tương đương bằng Gradle system property:

~~~bash
./gradlew help -Dorg.gradle.warning.mode=all
~~~

Hoặc đặt trong `gradle.properties`:

~~~properties
org.gradle.warning.mode=all
~~~

**`org.gradle.warning.mode=all` là thuộc tính cấu hình warning mode, không phải tham số `@Input` của JavaCompile hay Java test.** Khi cần đổi tạm trên một invocation, CLI `--warning-mode=all` thường rõ ràng hơn sửa file shared properties.

### Có nên giữ `warning.mode=fail` luôn trong project?

Sau khi dọn hết warnings và có baseline sạch, có thể đưa `--warning-mode=fail` vào CI gate. Nhưng nếu nhiều dependencies/plugins bên thứ ba vẫn phát cảnh báo mà team chưa kiểm soát được, bật fail toàn build ngay có thể khóa mọi PR. Hãy **phân loại/sửa/upgrade plugins trước**, thiết lập lịch xử lý, sau đó mới chuyển từ monitor sang gate.

Không dùng `--warning-mode=none` để “giải quyết” deprecation: nó chỉ **ẩn tín hiệu**, không cập nhật API hay giảm rủi ro khi nâng Wrapper.

## 4. Console summary và ý nghĩa thật

Với default `summary`, bạn có thể chỉ thấy một thông báo dạng:

~~~text
Deprecated Gradle features were used in this build,
making it incompatible with Gradle 10.
~~~

Đây là **dạng thông báo minh họa** cho Gradle 9.x; lời văn, link/documentation target và con số major có thể đổi theo version. Thông báo ở cuối không nói:
- File và dòng nào gây warning.
- Là plugin của tổ chức hay third-party plugin.
- Warning được phát trong configuration hay execution.
- Task nào phải chạy để tái hiện.
- Có bao nhiêu unique deprecation types.

Vì vậy bước kế tiếp là chạy **cùng task invocation** với `--warning-mode=all` và mở Problems Report, không phỏng đoán từ summary.

**Một build thành công cộng summary deprecation là “build hiện tại chạy được nhưng chưa chứng minh tương thích target major”.** Đừng chuyển nó thành lời khẳng định “đã support Gradle 10”.

## 5. Problems Report trong Gradle 9.x

Gradle có Problems API để tập trung thông tin các vấn đề phát sinh, trong đó có deprecations. Khi problems được báo, Gradle hiện có thể tạo HTML report mặc định tại:

~~~text
build/reports/problems-report.html
~~~

Đường dẫn trên thường tính từ **root build**. Với included builds/composite/multi-root setup, cần xem link/path Gradle in cuối build thay vì giả định mọi report cùng một folder. Nếu không có problems được báo, report có thể **không được tạo**.

Cách dùng:

~~~bash
./gradlew help --warning-mode=all --console=plain
./gradlew build --warning-mode=all --console=plain
~~~

Sau đó tìm link `problems-report.html` trong log và mở bằng browser. Trong report:
- Xem **problem group**; ví dụ Gradle deprecations.
- Đọc **contextual label**, severity và documentation link.
- Tìm location/source lines khi Gradle thu thập được.
- Gom các occurrences theo loại; không chỉ nhìn tổng số.
- Ghi nhận task/plugin nào gây ra để triage.

Gradle hiện có `--problems-report` (mặc định bật) và `--no-problems-report` để kiểm soát tạo HTML. **Không thêm `--no-problems-report` vào deprecation audit**, vì bạn sẽ mất một nguồn thông tin hữu ích.

### Giới hạn stack/source location

Theo Gradle 9.9, khi chạy `--warning-mode=all` hoặc `--warning-mode=fail`, Gradle cố xác định source location cho mọi vấn đề; với số lượng problems rất lớn, nó có giới hạn thu thập stack (ví dụ ngưỡng mặc định 50, và có cách giảm độ dài trace sau ngưỡng). Không kỳ vọng mọi occurrence đều có một stacktrace đầy đủ trong trường hợp hàng nghìn warnings.

**Không thêm một flag nội bộ ít được tài liệu hóa để “bắt Gradle in stacktrace mọi deprecation”** làm policy CI. Dùng tài liệu công khai: `--warning-mode=all`, Problems Report và Build Scan khi được phép.

## 6. Build Scan: một công cụ audit bổ sung

Gradle Upgrade Guide khuyên chạy:

~~~bash
./gradlew help --scan
~~~

và xem **Deprecations view** của Build Scan nếu build thực sự publish scan. Build Scan có thể liên kết deprecation với tasks, source/plugin và phân tích invocation sâu hơn console.

**Lưu ý:**
- `--scan`/Develocity configuration có thể **gửi metadata của build** tới dịch vụ scan.
- Việc publish/terms/server phụ thuộc cấu hình Gradle và chính sách tổ chức.
- Không tự bật trên public service khi repository có thông tin nhạy cảm mà chưa được chấp thuận.
- Scan từ `help` vẫn không thay thế việc chạy các task paths khác.

Nếu không được phép upload scan, **console `--warning-mode=all` + HTML Problems Report nội bộ** vẫn là quy trình hợp lệ.

Nguồn chính thức: [Gradle 9.x Upgrade Guide](https://docs.gradle.org/current/userguide/upgrading_version_9.html) và [Problems API](https://docs.gradle.org/current/userguide/reporting_problems.html).

## 7. Ví dụ runnable: Java 17 + Gradle 9.x phát hiện deprecated task

Tình huống cố ý: dự án Java 17 dùng `application` plugin, có một Java main và unit tests thật. Ta chạy task **`buildNeeded`** để quan sát deprecation trong Gradle 9.x, rồi chuyển sang task `build` để không còn phụ thuộc task sẽ bị loại bỏ ở Gradle 10.

### 7.1. Cây thư mục

~~~text
gradle-deprecation-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/demo/upgrade/
    │   ├── Greeting.java
    │   └── Main.java
    └── test/java/demo/upgrade/
        └── GreetingTest.java
~~~

Bài sử dụng **Gradle 9.9.0** để minh họa cảnh báo cụ thể; nếu project đang chạy Gradle 8.x hoặc tương lai đã nâng major10+, không kỳ vọng task/warning đó hoạt động giống hệt. Chuẩn bị Gradle Wrapper hợp lệ và JDK 17; Maven Central cần truy cập ít nhất một lần để resolve JUnit dependencies.

### 7.2. `settings.gradle.kts` — toàn bộ

~~~kotlin
rootProject.name = "gradle-deprecation-lab"
~~~

### 7.3. `build.gradle.kts` — toàn bộ

~~~kotlin
plugins {
    application
}

group = "dev.learning"
version = "1.0.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}

application {
    mainClass.set("demo.upgrade.Main")
}
~~~

Giải thích:
- `application` áp dụng Java plugin, tạo các tasks `run`, `test` (qua Java plugin), `build` và `buildNeeded` (task legacy có trong dòng9).
- Java 17 **toolchain** quyết định compiler/test JVM theo semantics Gradle Java plugin. Nó không có nghĩa Daemon JVM phải là 17 nếu Gradle version cho phép JDK khác.
- JUnit BOM `5.11.4` cố định compatible versions; Jupiter + Platform Launcher làm Gradle Test task chạy JUnit5.
- `tasks.test.useJUnitPlatform()` là yêu cầu quan trọng nếu test engine là Jupiter.
- File này **không tự gọi API deprecated**. Cảnh báo xuất hiện khi **bạn chọn một task deprecated**, giúp quan sát rõ mối quan hệ giữa task coverage và warning discovery.

### 7.4. `src/main/java/demo/upgrade/Greeting.java`

~~~java
package demo.upgrade;

public final class Greeting {
    private Greeting() {
    }

    public static String say(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                "name must not be blank"
            );
        }
        return "Hello, " + name + "!";
    }
}
~~~

### 7.5. `src/main/java/demo/upgrade/Main.java`

~~~java
package demo.upgrade;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.say("Gradle upgrade"));
    }
}
~~~

### 7.6. `src/test/java/demo/upgrade/GreetingTest.java`

~~~java
package demo.upgrade;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

public final class GreetingTest {
    @Test
    void formatsGreeting() {
        assertEquals(
            "Hello, Gradle upgrade!",
            Greeting.say("Gradle upgrade")
        );
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
            IllegalArgumentException.class,
            () -> Greeting.say(" ")
        );
    }
}
~~~

Đây là các Java source files hoàn chỉnh. Một unit test kiểm tra giá trị trả về, test còn lại kiểm tra invalid input. Chúng không dùng deprecated JDK APIs nên loại cảnh báo của bài tập sẽ tập trung vào **Gradle task usage**.

### 7.7. Kiểm tra build tốt ở phiên bản hiện tại

Linux/macOS:

~~~bash
./gradlew --version
./gradlew clean build --warning-mode=all --console=plain
./gradlew run --quiet
~~~

PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean build --warning-mode=all --console=plain
.\gradlew.bat run --quiet
~~~

**Stdout chính xác do Java `Main.main()` in ra**:

~~~text
Hello, Gradle upgrade!
~~~

Gradle `test` cần chạy và PASS hai tests khi dependencies/toolchain đầy đủ. Báo cáo test mặc định thường tại:

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-demo.upgrade.GreetingTest.xml
~~~

Số tasks executed, download progress và file metadata phụ thuộc môi trường, không dùng làm stdout cố định.

### 7.8. Chạy một task deprecated cố ý

**Chỉ khi Wrapper là Gradle 9.x có task legacy này**, chạy:

~~~bash
./gradlew buildNeeded --warning-mode=all --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat buildNeeded --warning-mode=all --console=plain
~~~

Gradle 9.x ghi nhận việc sử dụng `buildNeeded`/`buildDependents` là deprecated. Theo Upgrade Guide, chúng **sẽ bị loại bỏ ở Gradle 10**. Với `--warning-mode=all`, kỳ vọng sẽ thấy một thông báo **có ý nghĩa** tương tự:

~~~text
The buildNeeded task has been deprecated.
It will be removed in Gradle 10.
~~~

Đây là **thông báo tóm tắt về nội dung**, không phải trích dẫn bảo đảm byte-for-byte: Gradle có thể thêm documentation link/location hoặc wording khác theo patch version. Một lần chạy vẫn có thể **BUILD SUCCESSFUL** trên Gradle9 vì deprecated chưa đồng nghĩa removed. Nếu không thấy warning trong demo, xem Wrapper version, task đã thực sự được chọn hay chưa, và Problems Report.

### 7.9. Chuyển warning thành quality gate

~~~bash
./gradlew buildNeeded --warning-mode=fail --console=plain
~~~

Ở Gradle 9.x phát cảnh báo về deprecated task, invocation **sẽ fail do warning-mode gate**, ngay cả khi JavaCompile/JUnit work đã thành công. Không nhầm failure này với Java test assertion failure.

Sau đó dùng lệnh hiện đại phù hợp một project:

~~~bash
./gradlew build --warning-mode=fail --console=plain
~~~

Nếu không có warnings khác (từ plugins, Gradle environment, JDK hoặc init scripts), lệnh cuối có thể **BUILD SUCCESSFUL**. Đây là cách chứng minh đã bỏ phụ thuộc trực tiếp vào `buildNeeded` trong workflow demo. Với multi-project dependencies, ý nghĩa `buildNeeded` có thể rộng hơn; phần 9 trình bày lựa chọn thay thế theo mục tiêu, **không đổi một cách máy móc nếu cần tasks của downstream projects**.

### 7.10. Kiểm tra lần thứ hai: “không warning” khác “không chạy test”

Sau lần `build` thứ nhất, chạy:

~~~bash
./gradlew build --warning-mode=fail --console=plain
~~~

Nhiều task có thể `UP-TO-DATE`. Điều này là bình thường và không tự chứng minh code test vừa được execute lại. Nếu bạn đang audit **warnings chỉ xuất hiện trong task actions**, dùng một invocation buộc tasks thực thi:

~~~bash
./gradlew build --warning-mode=all \
    --rerun-tasks --console=plain
~~~

`--rerun-tasks` có thể làm build tốn thời gian hơn, dùng cho chẩn đoán trên branch/CI riêng. Nó **không sửa deprecated API** và không thay thế việc quét thêm các task paths như publishing/codegen/quality checks.

## 8. Vì sao `help` có thể “sạch” nhưng `buildNeeded` báo warning?

Trong ví dụ:
- `./gradlew help --warning-mode=all`: cấu hình build, không chọn deprecated task `buildNeeded`.
- `./gradlew build --warning-mode=all`: build/test/assemble theo lifecycle hiện đại.
- `./gradlew buildNeeded --warning-mode=all`: có task usage Gradle 9.x đã deprecated.
- `./gradlew buildNeeded --warning-mode=fail`: fail khi cảnh báo được ghi nhận.

Điều này chứng minh **coverage quan trọng hơn số lần chạy cùng một task**. Một audit chỉ gọi `help` có thể bỏ sót deprecation ở task action, Gradle plugin hook hoặc một task name deprecated nhưng ít được dùng.

Để kiểm tra repository thật, hãy tổng hợp những công việc thực sự có trong project:
- `help`/`tasks` để kiểm tra configuration.
- `build`, `check`, `test`, các test suites khác nếu chúng tồn tại.
- `publishToMavenLocal` hoặc publication tasks an toàn nếu cần phát hiện publishing APIs; tránh tự publish lên production.
- `jar`/`distZip`/`bootJar`/`shadowJar` nếu plugin/ứng dụng thực sự cung cấp tasks đó.
- `buildEnvironment`/`dependencies` khi muốn xem resolution, nhưng chúng không thay thế full build.
- `build-logic:build`/`buildSrc` outputs khi có composite/included builds.
- IDE sync nếu deprecation liên quan Tooling API models.

**Không chạy các tên tasks tùy đoán như `bootJar`/`integrationTest` trong dự án chưa áp dụng plugin tương ứng**; nếu task không tồn tại, đó là “Task not found”, không phải Gradle deprecation.

## 9. `buildNeeded`/`buildDependents`: hiểu behavior trước khi thay

Theo Gradle 9.x Upgrade Guide:
- `buildNeeded` từng xây current project cộng các project dependencies cần thiết theo graph tương ứng.
- `buildDependents` từng xây current project cộng các projects phụ thuộc ngược vào nó.
- Hai tasks legacy này deprecated, được dự kiến **remove trong Gradle 10** vì không phù hợp một số build isolation/configuration strategies và quá cứng so với use cases thực tế.

Với **một project** như demo, thay `buildNeeded` bằng `build` thường đúng mục đích.

Với **multi-project build**:

~~~text
root
  :api
  :service -> dependsOn :api
  :web -> dependsOn :service
~~~

Nếu bạn muốn:
- **Build/test một project và project dependency artifacts cần thiết**: dùng `./gradlew :service:build`; Gradle tự chạy producer tasks cần thiết cho dependency graph.
- **Test tất cả projects**: dùng `./gradlew test` từ root nếu task selector tìm được `test` ở những projects mong muốn, hoặc một lifecycle aggregate task rõ ràng.
- **Kiểm tra tác động ngược upstream/downstream**: dùng CI affected-project analysis/impact graph hoặc tập tasks có chủ đích, không suy `build` tự tương đương toàn bộ `buildDependents`.
- **Tổng hợp test results từ project dependencies**: xem Test Report Aggregation khi mục tiêu thật sự là aggregate tests.

**Không tuyên bố có một thay thế 1:1 cho `buildDependents`.** Tài liệu Gradle nói không có direct replacement; chọn theo nhu cầu thực tế và kiểm chứng task graph.

## 10. Ví dụ deprecation thật: thay thao tác Build Cache qua StartParameter

Một anti-pattern trong Gradle build logic cũ:

~~~kotlin
// settings.gradle.kts hoặc init script legacy — ví dụ deprecated.
// KHÔNG ghép vào project demo ở phần 7.
gradle.startParameter.buildCacheEnabled = true
~~~

Theo Gradle 9.x Upgrade Guide, **bật Build Cache bằng cách mutate StartParameter từ build logic** bị deprecated và dự kiến loại bỏ ở Gradle10. Đây không phải nơi hợp lệ để “ép” CLI caching policy.

Cách thay thế: trong `gradle.properties` (chỉ khi team muốn mặc định bật cache):

~~~properties
org.gradle.caching=true
~~~

Hoặc cho một invocation:

~~~bash
./gradlew build --build-cache
./gradlew build --no-build-cache
~~~

**Giải thích:** Build Cache enablement là lựa chọn của invocation hoặc Gradle property, không phải một mutable StartParameter mà script được phép override. Đây là deprecation của **build logic/API**, không phải một lỗi Java application source.

Đừng ghép cả legacy và modern config cùng lúc rồi nói đã sửa; phải loại bỏ đoạn mutate StartParameter hoặc thư viện/plugin vẫn thực thi nó.

## 11. Ví dụ deprecation: dependency notation bằng Project object

Một mô hình legacy (Groovy DSL **minh họa**, không phải phần runnable Java17 project ở trên):

~~~groovy
// build.gradle (Groovy DSL legacy)
def target = project(":library")

dependencies {
    implementation(target) // Deprecated: Project object as notation
}
~~~

Theo Gradle 9.x Upgrade Guide, truyền `Project` object trực tiếp vào dependency notation bị deprecated và sẽ trở thành lỗi trong Gradle10. Cách diễn đạt rõ dependency đúng là:

~~~kotlin
// build.gradle.kts trong project có :library
dependencies {
    implementation(project(":library"))
}
~~~

Đây là **mảnh Kotlin DSL cho multi-project build**; cần có `include("library")` trong settings và cấu hình dependency phù hợp. Hai dòng trông gần giống nhưng khác:
- `project(":library")` trong `dependencies` của `DependencyHandler` tạo **ProjectDependency** theo Gradle API.
- Chuyển nguyên một `Project` instance như một notation bất kỳ là hành vi deprecated.

**Không sửa bằng cách đổi sang absolute path của JAR file**. Cách đó làm mất variant-aware dependency resolution và task producer metadata.

## 12. Ví dụ deprecation: parallel model building khi IDE sync

Gradle 9.x có deprecation liên quan implicit coupling giữa:
- `org.gradle.parallel`: parallel task/project work theo semantics của Gradle.
- `org.gradle.tooling.parallel`: parallel model building khi Tooling API client (thường là IDE sync) yêu cầu.

Một legacy `gradle.properties`:

~~~properties
org.gradle.parallel=true
~~~

trong một số IDE model-building invocations có thể kích hoạt deprecation khi `org.gradle.tooling.parallel` **không được đặt tường minh**. Gradle 9.x Upgrade Guide giải thích behavior implicit này sẽ không còn hợp lệ ở Gradle10.

Nếu muốn cả hai bật:

~~~properties
org.gradle.parallel=true
org.gradle.tooling.parallel=true
~~~

Hoặc nếu không muốn parallel Tooling API models:

~~~properties
org.gradle.parallel=true
org.gradle.tooling.parallel=false
~~~

**Đây là hai phương án thay thế, không phải đặt hai giá trị `tooling.parallel` cùng lúc.** Và không khẳng định `./gradlew help` luôn phát warning này; nó được mô tả trong trường hợp **model building** qua Tooling API client. Vì vậy phải kiểm tra cả **IDE Gradle Sync**.

## 13. Deprecated API chỉ xuất hiện trong task action

Tài liệu Gradle 9.x mô tả nhiều thao tác Gradle model bị deprecated khi gọi **lúc task action chạy**, chẳng hạn:
- `Task.getDependsOn()`/`getTaskDependencies()`/`getMustRunAfter()` trong action.
- `Task.getExtensions()` trong action.
- Truy cập injected `Project`/`Gradle` service trong action.

Những API này có thể hợp lệ ở configuration phase nhưng **không phù hợp execution-time isolation** và dự kiến thành lỗi trong Gradle10. Với Configuration Cache bật, một số trường hợp đã được báo là **Configuration Cache problem** thay vì deprecation warning.

Mảnh lỗi minh họa:

~~~kotlin
tasks.register("legacyReport") {
    doLast {
        println("Depends on: " + taskDependencies
            .getDependencies(this).map { it.name })
    }
}
~~~

Đây là **mảnh intentionally deprecated**, không đưa vào `build.gradle.kts` runnable của phần 7. Nó đọc task dependency model trong execution phase.

Cách đúng là cấu hình task input data trước lúc task action, hoặc dùng custom task typed properties:

~~~kotlin
abstract class ReportNames : DefaultTask() {
    @get:Input
    abstract val names: ListProperty<String>

    @TaskAction
    fun report() {
        println(names.get().joinToString(", "))
    }
}

tasks.register<ReportNames>("reportNames") {
    names.set(listOf("compileJava", "test"))
}
~~~

Đây là **mảnh class + registration** cần imports `DefaultTask`, `ListProperty`, `Input`, `TaskAction` nếu đặt trong file độc lập. Nó **không query dynamic Gradle model bên trong task action**, chỉ đọc input đã được mô hình hóa. Trong project thật, `names` phải được derive từ contract tương ứng, không nhầm một danh sách string với task dependency edges.

### Vì sao việc chạy Configuration Cache lại quan trọng?

Gradle đang hướng tới model mà task actions không được chạm live `Project`/`Gradle` model. Bật:

~~~bash
./gradlew test --configuration-cache
./gradlew test --configuration-cache
~~~

giúp phát hiện thêm **configuration-cache incompatibilities**, nhưng **không thay thế** `--warning-mode=all` khi audit deprecations. Một lỗi có thể hiện dưới dạng Configuration Cache problem khi CC bật, trong khi xuất hiện dưới dạng deprecation warning khi CC tắt.

Để chẩn đoán đầy đủ, trong audit nên chạy **cả có và không có Configuration Cache** theo scope hợp lý.

## 14. Task được đăng ký không đồng nghĩa task đã được kiểm tra

Gradle có **lazy task registration**. Một plugin có thể đăng ký `publishArtifacts` mà không hiện thực hóa hay thực thi nó khi `help` chạy. Nếu deprecated API chỉ nằm trong plugin code khi task được realized hoặc action chạy, audit `help` không kích hoạt đường code ấy.

Mô hình:

~~~text
settings evaluation
   -> root/project configuration
      -> task registered lazily
         -> task realized/configured khi cần
            -> task action chạy nếu selected
               -> deprecated API có thể bị gọi ở đây
~~~

Vì vậy nên phân chia audit thành các tầng:
1. **Configuration baseline**: `help`, plugin resolution, settings, root/build logic.
2. **Build/test**: `build`/`test`/`check`.
3. **Packaging/publishing**: các tasks thực sự dùng của dự án, trong môi trường không làm phát hành production nhầm.
4. **Additional plugins**: lint, codegen, documentation, Docker, native packaging, dependency analysis.
5. **Tooling clients**: IDE sync, composite builds, configuration cache.
6. **CI environment**: trusted env/properties/Java/OS matrix.

Nếu một task có **side effect** (deploy, email, production publish, destructive DB), đừng gọi nó trên môi trường thật chỉ để bắt warning. Dùng sandbox/staging, mock endpoints hoặc chỉ audit configuration phần có thể an toàn, rồi ghi nhận phần không thể kích hoạt.

## 15. Gradle wrapper upgrade đúng quy trình

**Không nên sửa `distributionUrl` sang major mới ngay khi summary báo warnings.** Hướng an toàn:

~~~text
A. Đang trên version cũ
   -> kiểm kê warnings, plugins, tests, JDK compatibility

B. Sửa deprecations trong source / upgrade third-party plugins
   -> kiểm tra lại trên Gradle hiện tại

C. Thử Gradle mục tiêu trên branch riêng
   -> wrapper upgrade, smoke, full suite và CI

D. Chốt release
   -> commit Wrapper files, docs, CI pins và rollback plan
~~~

Với wrapper Gradle 9.9.0 trong ví dụ:

~~~bash
./gradlew :wrapper --gradle-version 9.9.0 \
    --distribution-type bin
./gradlew --version
~~~

**Lệnh này minh họa cách chuẩn hóa về 9.9.0, không phải yêu cầu nâng mọi dự án lên 9.9.0 vô điều kiện.** Nếu đang ở Gradle 8.x, đọc [Upgrading to Gradle 9.0.0](https://docs.gradle.org/current/userguide/upgrading_major_version_9.html) trước; một số Gradle8 APIs đã bị loại bỏ và không thể tiếp tục chạy khi nhảy thẳng vào 9.x.

Gradle Wrapper docs lưu ý chạy `wrapper` task **lần thứ hai** sau khi Wrapper dùng distribution mới nếu cần cập nhật cả wrapper scripts/JAR, không chỉ properties. Kèm security review và `distributionSha256Sum` theo checksum chính thức của distribution thật.

**Gradle 9.0+ dùng dạng version `X.Y.Z` trong Wrapper properties** (ví dụ `9.9.0`); không chỉ viết `9.9`/`9` trong URL rồi mong Wrapper tự tìm patch.

Đối với Gradle10+ khi được phát hành/trusted và target được chọn, kiểm tra version guide mới nhất trước khi đổi.

## 16. Ưu tiên sửa deprecations theo mức độ ảnh hưởng

Không phải warnings nào cũng có cùng risk:

| Mức | Ví dụ | Hành động |
| --- | --- | --- |
| P0 — breaking ở target major | Feature docs ghi “will be removed in Gradle 10”, target là 10 | Sửa trước khi upgrade |
| P1 — third-party plugin dùng API bị remove | Plugin CI quan trọng chưa hỗ trợ major mới | Upgrade plugin, tìm fork/migration plan |
| P1 — build logic làm sai output/graph | Implicit dependencies, cache-unsafe task APIs | Sửa task model, thêm tests |
| P2 — deprecation ở task hiếm chạy | Publishing/report/plugin management | Lập owner và test scenario riêng |
| P2 — sẽ bị xóa ở major xa hơn | Docs ghi removed in Gradle 11, target là 10 | Có thể ưu tiên thấp hơn nhưng vẫn lập kế hoạch |
| P3 — cosmetic/formatting warning chưa breaking | Warning có hướng dẫn rõ, tác động nhỏ | Sửa cùng batch code cleanup |

**Không dùng riêng chuỗi “Deprecated” để xếp mức**, vì warning có thể có due date và compatibility target khác nhau. Ghi:
- Message và docs URL.
- “will be removed / will become an error in version X” nếu docs xác nhận.
- Affected task/run configuration.
- Owner/team/plugin version.
- Fix/migration ticket.
- Status và validation proof.

### Một mẫu inventory

| Cột | Ví dụ |
| --- | --- |
| `Warning ID / label` | `Gradle > Deprecation > Task usage` |
| `Where detected` | `./gradlew buildNeeded --warning-mode=all` |
| `Source` | Built-in Gradle task; task selection |
| `Target breakage` | Removed in Gradle 10 theo Upgrade Guide |
| `Fix` | Dùng `build`/đổi workflow theo business intent |
| `Owner` | Build/CI maintainers |
| `Regression tests` | `./gradlew build --warning-mode=fail` |
| `Status` | Open / Fixed / Verified |

Bảng này **minh họa**; không khẳng định một chuỗi ID duy nhất là toàn bộ warning text. Gradle 9.9 có thay đổi định dạng Problems API IDs (phần tiếp).

## 17. Gradle 9.9 đổi cách định danh problem trong Problems API

Theo Gradle 9.x Upgrade Guide, Gradle 9.9 đưa deprecation warnings vào **predefined problem group**:

~~~text
Gradle > Deprecation > <kind of deprecation>
~~~

Thay vì kiểu legacy `deprecation:<slug derived from message>`, IDs bây giờ có dạng phân cấp, ví dụ:

~~~text
Trước:
deprecation:the-buildneeded-task-has-been-deprecated

Sau:
Gradle:Deprecation:Task usage
~~~

Chi tiết như task name/configuration được giữ trong **contextual label**, không nhất thiết trong problem name/ID nữa. Đây là vấn đề khi team:
- Dùng Tooling API/Problems API để phân loại warnings.
- Lưu baseline theo old problem ID.
- Có tool parser so raw message và cho rằng một ID = một occurrence.
- Đếm deprecations bằng cách grep một định dạng cũ.

**Đừng cố làm CI quality gate bằng cách đếm IDs mới như unique deprecations từ mọi task**. Cùng kind có thể xuất hiện ở nhiều task contexts; hãy lấy contextual label/documentation/source.

Để đơn giản và ít phụ thuộc format, dùng **`--warning-mode=fail`** cho một invocation được bao phủ đủ task paths, đồng thời dùng Problems Report cho triage. Chỉ viết machine-readable Problems API aggregation khi team thật sự cần dashboard/ownership dài hạn.

## 18. Vì sao “no warnings” vẫn chưa chứng minh upgrade an toàn?

Một build hoàn toàn sạch dưới `--warning-mode=all` có thể vẫn gặp breaking change khi nâng major vì:

1. Plugin dùng **internal Gradle API** không có deprecation compatibility contract.
2. Plugin chưa hỗ trợ embedded Kotlin/Groovy version mới.
3. JVM để chạy Gradle thiếu/không thuộc dải hỗ trợ.
4. Kotlin DSL script không còn compile do type/accessor/API changed.
5. Toolchain/annotation processor/plugins yêu cầu JVM/ASM phiên bản tương thích.
6. Dependency resolution/variant attributes/repositories behavior thay đổi.
7. Configuration Cache, isolated projects hoặc daemon JVM policies khác.
8. Native/Groovy/Android/Kotlin plugin matrix có yêu cầu riêng.
9. CI uses deprecated Gradle CLI options mà audit không chạy tới.
10. Publish/plugin marker artifacts có thể không còn metadata tương thích.

**Deprecation audit là một lớp giảm rủi ro, không phải chứng nhận tương thích.** Vẫn cần build/test/integration tests trên Gradle phiên bản mục tiêu và JDKs mục tiêu.

## 19. Phân biệt warnings do project và warnings do third-party plugin

Khi thấy warning, đặt 5 câu hỏi:

1. **Nó được phát lúc nào?** Settings evaluation, project configuration, task realization, task execution hay IDE model import?
2. **Nguồn ở đâu?** `settings.gradle.kts`, `build.gradle.kts`, `buildSrc`, `build-logic`, plugin JAR, Gradle init scripts?
3. **Ai sở hữu code?** Team hiện tại có thể sửa, hay phải nâng version plugin?
4. **Theo docs, phiên bản nào remove/break?** Tránh đoán.
5. **Có thể tái hiện với one-task invocation?** Nếu có, tạo regression test/smoke command.

Với plugin bên thứ ba:

~~~text
warning stack / source:
  Gradle API (deprecated)
    <- third-party plugin class
       <- build.gradle.kts applying plugin
~~~

Bạn có thể:
- Nâng plugin lên version được nhà phát hành công bố support target Gradle.
- Đọc changelog/release notes và compatibility matrix.
- Nếu plugin chưa có fix, báo upstream issue kèm minimal reproducer/Gradle version.
- Tạm giữ Wrapper version cũ, dùng staging branch hoặc thay plugin nếu business cho phép.
- Với plugin nội bộ, sửa `Plugin<Project>`/custom task types rồi viết TestKit regression test.

**Không sửa build.gradle.kts bằng cách bỏ `plugins { id(...) }` chỉ để warning biến mất** khi plugin đang thực hiện logic bắt buộc của build (codegen/testing/security).

## 20. Tìm warnings từ build logic nội bộ: `buildSrc` và `build-logic`

Build logic có thể nằm ở:
- `buildSrc`: Gradle tự phát hiện và đưa compiled code lên buildscript classpath.
- `build-logic`: included build được khai báo qua `includeBuild` hoặc `pluginManagement.includeBuild`.
- Custom plugin project published dưới plugin ID/version.

Nếu warning stack trỏ tới một task type/plugin class, hãy xác định **build nào compile code đó**. Một included build có **settings/dependencies/Gradle plugin versions riêng**, nên test riêng logic khi cần.

Ví dụ mô hình:

~~~text
main build
  settings.gradle.kts
  :app / :library

included build
  build-logic/settings.gradle.kts
  build-logic/build.gradle.kts
  convention plugins / task classes
~~~

Khi main build gọi `./gradlew build`, chỉ những plugin/tasks được dùng mới có thể phát các warnings tương ứng. Có những build-logic tests/tasks không được chọn bởi main root `build`, cần thêm một **build-logic verification job** riêng theo task path hoặc làm việc trong included build root.

**Không sửa internal Gradle API usage bằng cách thêm `--warning-mode=none` vào build-logic**: sự không tương thích sẽ bộc lộ khi nâng Wrapper.

## 21. Configuration Cache có ảnh hưởng phát hiện deprecation không?

Có. Một số deprecated task/model accesses có warning **khi Configuration Cache tắt**, nhưng được Gradle báo **như Configuration Cache problems** khi bật CC. Ngoài ra khi CC reuse configuration, một số configuration actions không thực thi lại như một lần cache miss.

Vì vậy quy trình audit có thể dùng hai lượt:

**Lượt A — configuration/cache-disabled baseline**

~~~bash
./gradlew help --warning-mode=all \
    --no-configuration-cache --console=plain

./gradlew build --warning-mode=all \
    --no-configuration-cache --console=plain
~~~

**Lượt B — Configuration Cache compatibility**

~~~bash
./gradlew help --configuration-cache \
    --warning-mode=all --console=plain

./gradlew build --configuration-cache \
    --warning-mode=all --console=plain
~~~

Cần chạy hai lần với cùng task/inputs để xem behavior reuse (nếu project hỗ trợ). Nếu B fail với Configuration Cache problems, không coi việc A pass là đủ. Nếu A báo deprecation nhưng B báo CC error cho cùng API usage, đó là **cùng nợ kỹ thuật dưới hai cách kiểm tra**.

### `--rerun-tasks` và `clean` khác nhau

- `--rerun-tasks`: buộc task actions thực thi lại, hữu ích khi deprecation nằm trong action bị skip.
- `clean`: xóa outputs theo Gradle clean task, nhưng action khác vẫn có thể dùng Build Cache; không bảo đảm mọi code path sẽ chạy.
- `--no-build-cache`: tắt output restoration, có thể dùng ở diagnostic khi cần biết action thực thi; nhưng không phải policy bắt buộc để phát hiện tất cả deprecations.
- `--no-configuration-cache`: bảo đảm lần chạy audit đi qua configuration thay vì reuse cached configuration entry.

**Không dùng một bộ flags dài như bùa hộ mệnh.** Chọn flags để kiểm soát đúng loại cache/skipping mà bạn nghi ngờ đang che warning.

## 22. Warnings do Java compiler không phải Gradle deprecations

Một Java source có thể gọi một JDK API `@Deprecated`; `javac` có thể cảnh báo khi bật lint, nhưng **`--warning-mode=fail` là cơ chế Gradle**, không tự bảo đảm rằng mọi compiler warning sẽ làm task `compileJava` fail.

Ví dụ Java:

~~~java
package demo.legacy;

public final class LegacyApi {
    @Deprecated
    public static String oldName() {
        return "old";
    }

    public static String newName() {
        return "new";
    }
}
~~~

Một class khác gọi `LegacyApi.oldName()` có thể được `javac` thông báo deprecated. Để xem chi tiết:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-Xlint:deprecation")
}
~~~

Đây là **mảnh Gradle Kotlin DSL** (yêu cầu Java plugin và đúng imports hoặc Kotlin DSL classpath). Nếu muốn compiler warnings làm CI fail, cần chính sách compiler `-Werror` hoặc lint tooling phù hợp, với scope rõ; nó khác deprecation gate của Gradle.

Hãy tách hai bảng audit:
- **Gradle deprecations**: rủi ro khi nâng **Gradle**.
- **Java/JDK deprecated APIs**: rủi ro khi nâng **JDK**.

Một project có thể phải nâng cả Gradle và JDK; không làm gộp mọi warning thành cùng một lỗi mơ hồ.

## 23. Đề xuất quy trình audit theo từng giai đoạn

### Giai đoạn 0 — Chốt phiên bản hiện trạng

~~~bash
./gradlew --version
./gradlew javaToolchains
~~~

Ghi lại Gradle version, Gradle Daemon JVM, project Java Toolchain, OS/runner và plugin versions. Nếu project multi-root, ghi từng build root và Wrapper.

### Giai đoạn 1 — Quét configuration

~~~bash
./gradlew help --warning-mode=all \
    --no-configuration-cache --console=plain
~~~

Đọc console và HTML Problems Report; triage buildscript/settings/plugins warnings.

### Giai đoạn 2 — Quét build/test paths

~~~bash
./gradlew build --warning-mode=all \
    --no-configuration-cache --console=plain
~~~

Tùy project, thêm Gradle tasks có thực: `check`, `test`, `integrationTest`, `distZip`, plugin validate tasks, dependency reports, docs/codegen/quality tasks.

### Giai đoạn 3 — Quét những actions bị skip

Nếu nghi warning nằm trong task action vốn `UP-TO-DATE` hoặc `FROM-CACHE`, audit một tập tasks an toàn với:

~~~bash
./gradlew build --warning-mode=all \
    --rerun-tasks --no-configuration-cache \
    --console=plain
~~~

Không ép production publish/deploy hoặc side-effect tasks chạy thật bằng flags này.

### Giai đoạn 4 — Quét model/IDE/CC

Chạy `--configuration-cache`, IDE Gradle Sync và composite/included builds nếu có. Ghi riêng những issues chỉ có ở Gradle Tooling API.

### Giai đoạn 5 — Phân loại và sửa

Chia theo source/owner, ưu tiên deprecations của target major, nâng third-party plugins trước khi sửa workarounds local, thêm tests.

### Giai đoạn 6 — Gate

~~~bash
./gradlew build --warning-mode=fail \
    --no-configuration-cache --console=plain
~~~

Lưu ý scope của gate chính là **những task paths được chạy**. Nếu gate chỉ chạy `build` mà release dùng `publish`, bạn chưa bảo vệ code path publish. Giữ một danh sách task coverage rõ.

### Giai đoạn 7 — Thử target Wrapper

Nâng Wrapper trên branch riêng, chạy test/matrix, kiểm tra publication/CI/IDE, rollback nếu cần. Chỉ merge khi Gradle target thực tế pass; warning-free current version **không thay thế test compatibility**.

## 24. CI gate trên GitHub Actions

Với repository Java17 có Gradle Wrapper tại root, một workflow riêng `.github/workflows/gradle-deprecations.yml` có thể dùng:

~~~yaml
name: Gradle Deprecation Gate

on:
  pull_request:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  deprecations:
    runs-on: ubuntu-24.04
    timeout-minutes: 25

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up Java 17
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - name: Setup Gradle
        uses: gradle/actions/setup-gradle@v6
        with:
          cache-provider: basic

      - name: Ensure wrapper is executable
        run: chmod +x ./gradlew

      - name: Gate deprecated API usage
        run: |
          ./gradlew help build \
            --warning-mode=fail \
            --no-configuration-cache \
            --console=plain

      - name: Upload Problems Report if present
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: gradle-problems
          path: build/reports/problems-report.html
          if-no-files-found: ignore
          retention-days: 7
~~~

**Đây là workflow cấu trúc hoàn chỉnh cho Gradle Java17 root project**. Những task paths `help` và `build` tồn tại trong Java plugin, không giả định có `publish`, `integrationTest` hoặc `bootJar`. Tùy repository thật, mở rộng coverage phù hợp. `--warning-mode=fail` chỉ bắt những warnings được Gradle ghi nhận ở các paths này.

**Khi nào bật?** Sau khi team đã dọn/triage các warnings, vì gate sẽ fail nếu plugin đang dùng vẫn phát deprecation. Giai đoạn đầu, thay `fail` bằng `all` để **monitor không chặn PR**; lưu report và tạo tickets. Khi baseline sạch, chuyển sang `fail` và đặt GitHub required status check cho job.

**Lưu ý riêng cho demo `buildNeeded`:** workflow trên **không chạy `buildNeeded`**. Do đó nó có thể PASS ngay cả khi một shell script ở nơi khác còn gọi `buildNeeded`. Hãy đưa mọi CLI commands thực tế (developer/CI/release) vào inventory và sửa bỏ legacy task; không dùng gate `help build` để suy không có deprecated tasks ở nơi khác.

### Vì sao CI không nên grep duy nhất chuỗi “deprecated”?

Console wording và Problems API ID có thể đổi qua Gradle versions. Grep `deprecated` cũng có thể bắt nhầm comments/compiler warnings hoặc bỏ sót warnings qua problem report. **`--warning-mode=fail` là hành vi gate chính thức của Gradle**; artifacts/logs phục vụ triage. Một dashboard phân loại nâng cao có thể dùng Problems API/Build Scan nhưng cần biết schema/version.

### Token và artifact security

Workflow read-only `permissions: contents: read` đủ để chạy build/test. Không cần registry/deployment credentials để audit. Tại PR từ fork, không dùng `pull_request_target` checkout untrusted code rồi chạy Gradle với privileged secrets. Problems Report có thể chứa file paths, plugin identifiers hoặc nội dung lỗi nội bộ; không upload rộng hơn cần thiết.

## 25. Giám sát warnings định kỳ có giúp gì?

Với một monorepo nhiều modules hoặc third-party plugins thay đổi thường xuyên:
- Thêm deprecation gate vào pull requests giúp ngăn code mới dùng deprecated Gradle APIs.
- Có thể có CI job định kỳ hoặc manual để chạy **rộng hơn** (integration, plugin compatibility) mà không gây chậm mọi PR.
- Khi phát hành Gradle minor mới, đọc phần **Deprecations** trong Upgrade Guide và so với inventory.
- Khi nâng plugin version, xem warning count/contexts mới và loại warning nào được giải quyết.
- Với plugin nội bộ, thêm Gradle TestKit matrix tests trên current/migration target versions.

Nếu một CI job có deprecation warning, báo đủ **task command, Wrapper version, relevant warning text, documentation link và owner**; đừng chỉ gửi ảnh summary cuối terminal.

## 26. Third-party plugins và Gradle TestKit

Nếu tổ chức phát triển một Gradle plugin, không chỉ test code plugin biên dịch trên Gradle version hiện tại. Dùng **Gradle TestKit** để chạy một consumer fixture build qua `GradleRunner` với các Gradle versions được hỗ trợ.

Mẫu kiến trúc thử nghiệm:

~~~text
plugin-project
  src/main/java/... Plugin implementation
  src/test/java/... TestKit functional tests
  test fixture build:
    settings.gradle.kts
    build.gradle.kts
    java source
  GradleRunner:
    withGradleVersion("<supported Gradle>")
    withPluginClasspath()
    withArguments("help", "--warning-mode=fail")
~~~

Đây là **sơ đồ phương pháp**, không phải code test chạy độc lập. `<supported Gradle>` là ký hiệu cần thay bằng version thực trong CI, không phải một Gradle version được giả định. Một test fixture tốt còn gọi **task thực** của plugin để kích hoạt execution-time warnings và kiểm tra outputs.

Với plugin version matrix:
- Oldest supported Gradle.
- Current stable Gradle.
- Next candidate/RC nếu tổ chức đã xác minh compatibility.
- JDK runtime/toolchain matrix có ý nghĩa.

**Không publish plugin release “hỗ trợ Gradle 10” chỉ vì TestKit tests chạy trên Gradle 9 với `--warning-mode=fail`.** Cần chạy thật trên Gradle10 khi target distribution tồn tại và được chọn.

## 27. Trường hợp task không thể chạy trong audit

Một deprecation có thể nằm trong `publish`, `deploy`, `dropSchema` hoặc cloud resource provisioning. Không gọi tasks này trên production chỉ để thu warning. Thay vào đó:
- Đọc source/plugin implementation và Upgrade Guide.
- Chạy trên staging/mocked repository, disposable database, sandbox credentials.
- Nếu có chế độ `--dry-run`, hiểu nó **không chạy task actions**, nên có thể bỏ sót deprecation chỉ xuất hiện lúc execution.
- Dùng plugin functional tests hoặc Gradle TestKit fixtures.
- Đánh dấu phần **chưa cover** trong inventory/risk review.

Một báo cáo chính xác có thể kết luận: “`help` và `build` warning-free; production publish code path chưa được kiểm tra do side effects”. Kết luận này hữu ích hơn lời tuyên bố tổng quát “không còn deprecation” khi bằng chứng chưa đủ.

## 28. Các lỗi hay gặp khi audit deprecations

| Triệu chứng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| Thấy summary nhưng không thấy vị trí | Mặc định `summary` | Chạy cùng command với `--warning-mode=all` |
| `help` không warning nhưng `publish` có | Deferred task realization/action | Quét tasks thực dùng trong staging |
| `--warning-mode=none` làm log sạch | Chỉ ẩn warning | Đổi sang `all`, sửa nguyên nhân |
| `--warning-mode=fail` làm build đỏ nhưng tests pass | Gate phát hiện deprecation | Đọc warning location, không bỏ gate vô cớ |
| Console báo link Problems Report nhưng không thấy file | Build directory/root khác, report chưa được tạo | Xem path từ log, `--problems-report` |
| Problems Report source line trỏ vào plugin JAR | Third-party plugin gọi deprecated API | Upgrade plugin/issue upstream |
| Warning chỉ khi IntelliJ sync | Tooling API model building | Kiểm tra IDE/`org.gradle.tooling.parallel` |
| Warning chỉ khi Configuration Cache tắt | Task model API access deprecation | Audit cả CC bật/tắt, sửa task action |
| `--rerun-tasks` làm build chậm | Buộc task actions chạy lại | Chỉ dùng khi audit execution deprecation |
| Upgrade Wrapper làm build fail không có warning trước | Removed internal API/breaking change | Compatibility matrix, migration guide, plugin update |
| Gradle CLI `gradle` pass, Wrapper fail | Hai Gradle versions khác nhau | Luôn dùng `./gradlew` |
| Warning “Java deprecated API” | `javac`/JDK category khác | Dùng compiler lint/JDK migration riêng |
| `-Dorg.gradle.warning.mode=all` không áp dụng trong IDE | IDE nhập flags/JVM khác CLI | Kiểm tra Gradle runner settings/invocation |
| Report quá nhiều duplicates | Một kind lặp ở nhiều tasks/projects | Group theo kind + contextual labels/owners |
| Upgraded plugin vẫn warning | Plugin transitive/included logic khác, version chưa đổi | Dependency/plugin resolution, stack/scan |
| Chỉ sửa `build.gradle.kts` nhưng warning còn | init script, `buildSrc`, included build hoặc plugin | Xác định source thật |
| Gradle9 deprecation dự kiến remove ở 11 | Due date không đồng nhất | Tra exact Upgrade Guide, không gán nhầm target |
| CI buildNeeded fail sau nâng Gradle | Task đã bị remove ở target | Thay task workflow trước upgrade |
| Run `help --warning-mode=fail` PASS nhưng CI release fail | Audit coverage hẹp | Thêm publication/integration tests vào safe staging |
| `--scan` không có link hoặc không được phép | Scan publication policy | Dùng local Problems Report/console |
| Cache khiến task action không chạy | `UP-TO-DATE`/`FROM-CACHE` | Dùng `--rerun-tasks` cho safe audit |
| Warning mode fail “không bắt” plugin logger.warn | Không phải Gradle deprecation mechanism | Xem plugin tooling/log separately |
| Một deprecation ID đại diện nhiều tasks | Gradle 9.9 hierarchical IDs | Đọc contextual labels, không dedupe sai |

## 29. Nên lưu chứng cứ audit thế nào?

Một báo cáo nâng cấp nên có:

~~~text
Gradle version: 9.9.0
Target version: 10.x (chỉ khi tổ chức đã chọn target)
JDK for daemon: 17/21 supported by wrapper
Java toolchain: 17
Tasks covered:
  help
  build
  <project-specific safe tasks>
Other paths:
  IDE Sync: covered / not covered
  release publish: staging only / not covered

Warnings:
  - kind + contextual label
  - location / plugin version
  - docs URL and planned removal version
  - owner / issue / fix PR

Result:
  compile/test pass?
  warnings zero in covered tasks?
  Problems Report artifact/log?
  Gradle target compatibility tested yet?
~~~

Đây là **định dạng báo cáo minh họa**, không phải file thực tế do Gradle tự xuất nguyên văn. Quan trọng nhất là tính **có thể tái hiện**: ai đọc cũng biết dùng lệnh nào, phiên bản nào và warning từ đâu.

Nếu team có build dashboard, có thể theo dõi “số unique deprecation kinds” và “số contexts cần sửa” theo thời gian, nhưng đừng cho rằng số warning messages luôn có ý nghĩa so sánh giữa các Gradle versions khi Problems API grouping thay đổi.

## 30. Checklist trước khi nâng Gradle Wrapper

- [ ] Đã ghi version hiện tại bằng `./gradlew --version`.
- [ ] Đã đọc Upgrade Guide của target, **bao gồm từng minor/major nhảy qua**.
- [ ] Gradle Daemon JVM và Java toolchain nằm trong compatibility ranges.
- [ ] Plugin versions (Android, Kotlin, Spring, quality, publishing, codegen...) hỗ trợ target.
- [ ] Đã chạy `help --warning-mode=all` để quét configuration.
- [ ] Đã chạy `build`/`check`/`test` và project-specific tasks có thật.
- [ ] Đã kiểm tra build-logic/buildSrc/included builds và các plugin tests.
- [ ] Đã kiểm tra IDE sync khi Tooling API behavior liên quan.
- [ ] Đã đọc Problems Report và phân loại contexts/source locations.
- [ ] Đã xét Build Scan nếu security/privacy policy cho phép.
- [ ] Không nhầm `--warning-mode=none` là giải pháp.
- [ ] Không dùng Gradle `logger.warn` làm proxy duy nhất cho deprecation gate.
- [ ] Các warnings có owner, target removal version, fix và test.
- [ ] Deprecated built-in tasks như `buildNeeded` đã được thay đúng nghiệp vụ.
- [ ] Config cache/incremental/Build Cache behaviors được kiểm thử riêng.
- [ ] Không có task action truy cập Gradle model APIs bị deprecated.
- [ ] Không mutate Gradle StartParameter để thay invocation caching policy.
- [ ] Không có third-party plugin chưa tương thích mà chưa có migration plan.
- [ ] Đã tách compile/JDK deprecations khỏi Gradle API deprecations.
- [ ] Đã thử `--warning-mode=fail` trên những task paths cần gate.
- [ ] CI gate có report/log để truy dấu, không bỏ qua warnings bằng flags ẩn.
- [ ] Các side-effect tasks được thử an toàn ở staging hoặc ghi nhận thiếu coverage.
- [ ] Chỉ sau đó mới nâng Wrapper trong một branch riêng.
- [ ] Wrapper scripts/JAR/properties được cập nhật và review đúng quy trình.
- [ ] Full CI/test/publishing smoke tests chạy thật trên target Gradle.
- [ ] Có rollback plan nếu plugin ecosystem hoặc CI environment chưa đáp ứng.

## 31. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `BUILD SUCCESSFUL` vẫn có thể nguy hiểm trước major upgrade?

**Đáp:** Deprecated API/feature có thể còn chạy ở phiên bản hiện tại nhưng bị xóa ở phiên bản mục tiêu; success không chứng minh compatibility.

**Câu 2.** `summary` và `all` khác nhau thế nào?

**Đáp:** `summary` chỉ hiển thị tóm tắt ở cuối; `all` in các warnings Gradle report, hữu ích để xác định vấn đề.

**Câu 3.** `--warning-mode=fail` có sửa deprecations không?

**Đáp:** Không. Nó khiến invocation fail khi warnings được Gradle phát qua cơ chế warning liên quan, phù hợp quality gate.

**Câu 4.** Vì sao một lệnh `./gradlew help --warning-mode=all` chưa đủ?

**Đáp:** Nó không chạy mọi task actions/selected paths, nên có thể bỏ warnings chỉ được phát khi packaging, publishing hoặc test.

**Câu 5.** Problems Report thường ở đâu?

**Đáp:** `build/reports/problems-report.html` cho root build khi có problems, hoặc path cụ thể Gradle in log.

**Câu 6.** `--scan` có luôn nên bật cho repo nội bộ không?

**Đáp:** Không. Build Scan có data publication/privacy implications; phải kiểm tra chính sách và chỉ publish khi được phép.

**Câu 7.** `buildNeeded` trong Gradle 9.x có hướng đi thế nào?

**Đáp:** Deprecated và dự kiến remove ở Gradle10; chọn `build`/project-specific tasks hoặc mechanism khác theo nghiệp vụ.

**Câu 8.** `buildDependents` có direct replacement không?

**Đáp:** Không, theo Upgrade Guide. Cần định nghĩa affected-project/testing strategy phù hợp.

**Câu 9.** Một dependency notation bằng `Project` object có tương đương `implementation(project(":lib"))` không?

**Đáp:** Không: truyền `Project` object như notation bị deprecated; `project(...)` trong dependency handler mô tả ProjectDependency đúng API.

**Câu 10.** Vì sao đổi `org.gradle.parallel=true` có thể gây IDE warning mà CLI `help` không?

**Đáp:** Một deprecation liên quan `org.gradle.tooling.parallel` chỉ phát khi Tooling API parallel model building được kích hoạt theo điều kiện; không phải mọi invocation đều làm điều đó.

**Câu 11.** Java compiler warning về `@Deprecated` có được Gradle warning mode gate toàn bộ không?

**Đáp:** Không đảm bảo. Cần `-Xlint:deprecation` và compile policy nếu mục tiêu là Java/JDK API deprecations.

**Câu 12.** Khi task action đọc Gradle Project model, CC bật và tắt khác thế nào?

**Đáp:** Có thể báo Configuration Cache problem khi CC bật, deprecation warning khi CC tắt; phải kiểm tra cả hai nếu cần coverage.

**Câu 13.** `--dry-run` có đủ bắt execution-time warnings không?

**Đáp:** Không. Dry run không thực thi task actions nên có thể bỏ sót deprecation chỉ xảy ra khi action chạy.

**Câu 14.** Vì sao warning-free ở Gradle 9 chưa bảo đảm Gradle10 compatible?

**Đáp:** Có breaking changes/plugin internal API/JVM requirements không được phát warning ở đường code đã thử.

**Câu 15.** Nếu warning do third-party plugin, cần làm gì?

**Đáp:** Kiểm tra plugin version/changelog, nâng lên release hỗ trợ target, báo upstream hoặc lập migration plan; đừng tắt warning để né.

**Câu 16.** Một deprecation ID mới ở Gradle 9.9 có thể che nhiều occurrences không?

**Đáp:** Có. IDs phân nhóm theo kind; contextual label chứa chi tiết như tên task/configuration, nên phải xem cả contexts.

**Câu 17.** Lúc nào nên chuyển CI từ `--warning-mode=all` sang `fail`?

**Đáp:** Khi đã triage/fix baseline warnings và có coverage đủ; `fail` là gate, không phải cách tự sửa code.

**Câu 18.** Để phát hiện API deprecated trước upgrade, có cần `clean` mọi lần không?

**Đáp:** Không. Chỉ dùng clean/rerun/cache flags theo mục tiêu; task execution coverage và proper modeling quan trọng hơn.

## 32. Tài liệu chính thức và đường dẫn tra cứu

- [Gradle — Command-Line Interface: Showing or hiding warnings](https://docs.gradle.org/current/userguide/command_line_interface.html): `--warning-mode`, các modes `summary/all/fail/none` và `org.gradle.warning.mode`.
- [Gradle — Upgrading within Gradle 9.x](https://docs.gradle.org/current/userguide/upgrading_version_9.html): deprecations cụ thể, kế hoạch remove, Build Scan/`help --warning-mode=all`, Problems IDs Gradle 9.9.
- [Gradle — Upgrading to Gradle 9.0](https://docs.gradle.org/current/userguide/upgrading_major_version_9.html): các breaking changes Gradle8→9, các APIs đã bị loại bỏ.
- [Gradle — Reporting Problems](https://docs.gradle.org/current/userguide/reporting_problems.html): Problems API, HTML report, source location và console rendering.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): nâng Wrapper, version pins, update scripts/JAR.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): JVM Gradle runtime/toolchains compatibility.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): các hạn chế task model và configuration reuse.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): task output reuse, cacheability và controls.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): tác vụ lazy registration và realization.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): `useJUnitPlatform`, test filtering và reports.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): Java17 compiler/test runtime selection.
- [Gradle — Gradle TestKit](https://docs.gradle.org/current/userguide/test_kit.html): plugin compatibility tests và GradleRunner.
- [GitHub Docs — Workflow Syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): PR/push triggers, permissions, job status, artifacts.
- [Gradle Actions repository](https://github.com/gradle/actions): `setup-gradle`, Wrapper validation và caching.
