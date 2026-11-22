# Thu thập bản tái hiện tối thiểu và log vừa đủ để báo lỗi Gradle

## 1. Mục đích: giúp người khác tái hiện và sửa lỗi, không chỉ gửi ảnh chụp màn hình

Khi Gradle báo **BUILD FAILED**, IDE không đồng bộ được project, dependency resolution thất bại hoặc một test chỉ lỗi trên CI, thông tin “mình chạy không được” thường chưa đủ để người khác tìm nguyên nhân. Ngược lại, gửi cả repository, thư mục **.gradle/**, toàn bộ **--debug** log và biến môi trường lại tạo quá nhiều nhiễu, có thể làm lộ credentials hoặc dữ liệu cá nhân.

Một báo lỗi hiệu quả trả lời được bốn câu hỏi:

1. **Cần thao tác chính xác thế nào để gây ra lỗi?** Người khác có thể copy lệnh và chạy trên một checkout sạch?
2. **Kỳ vọng điều gì?** Task hoặc IDE đáng lẽ hành xử thế nào?
3. **Thực tế xảy ra điều gì?** Thông báo lỗi đầu tiên, task thất bại, dấu hiệu quan sát được là gì?
4. **Điều kiện tối thiểu nào làm lỗi xuất hiện?** Gradle Wrapper, JDK, cấu hình, dependency, source, hệ điều hành và các flags liên quan.

Bài thuộc **Build Tool Gradle**, nhóm **IDE và chẩn đoán**, với đề tài **“Thu thập bản tái hiện tối thiểu và log vừa đủ để báo lỗi”**.

Đầu ra tốt nhất là một **minimal reproducible example (MRE)** cộng với một **bộ bằng chứng vừa đủ**, chứ không phải một tệp log càng lớn càng tốt.

Sau khi học, bạn có thể:

- Phân biệt lỗi IDE import/sync với lỗi build chạy bằng Gradle Wrapper.
- Phân loại lỗi theo initialization, configuration, dependency resolution, task execution và test failure.
- Thu thập Gradle/JVM/toolchain/OS thông tin mà không làm lộ path, username hoặc secrets không cần thiết.
- Tăng mức logging theo từng nấc: failure summary → **--stacktrace** → **--info** → công cụ đặc thù.
- Rút gọn multi-project build tới một project, một task, một dependency hoặc một test vẫn tái hiện.
- Biết những thành phần phải giữ để reproduction còn trung thực: Wrapper, settings, plugin version, repository, source/fixture tối thiểu.
- Chứng minh một failure xảy ra ổn định, ghi số lần thử và phân biệt flaky issue.
- Thiết kế một project Java 17 + JUnit 5 có lỗi cố ý và kiểm thử pass khi không kích hoạt.
- Gửi báo lỗi có steps, expected/actual, environment, log excerpt, phạm vi đã loại trừ, không gửi toàn workspace.
- Giữ nguyên exit status khi lưu log; không làm CI xanh giả.
- Hiểu **--no-daemon**, **--no-build-cache**, **--no-configuration-cache**, **--offline**, **--refresh-dependencies**, **--rerun-tasks** là biến số thí nghiệm, không phải “chữa mọi lỗi”.
- Dùng Build Scan/Develocity có kiểm soát nếu chính sách chia sẻ dữ liệu cho phép.
- Tạo issue report hoặc ticket nội bộ rõ ràng, có khả năng xác minh và cập nhật.

## 2. Ba thành phần của báo lỗi chất lượng

Một báo lỗi tốt luôn có:

**A. Reproduction:** Code, cấu hình và lệnh nhỏ nhất còn gây lỗi. Ví dụ một **build.gradle**, một **settings.gradle**, một Java source và một test class.

**B. Observation:** Log trích đúng đoạn, error message/stack trace có ý nghĩa, task outcome, version và môi trường. Nếu ảnh IDE cần thiết thì chỉ chụp vùng lỗi, không cả desktop hoặc danh sách tài khoản.

**C. Hypothesis và kiểm chứng:** Những thí nghiệm đã thử, mỗi lần đổi một yếu tố. Ví dụ “lỗi xảy ra với Wrapper trên CLI lẫn IDE” đáng giá hơn “đã xóa cache rồi vẫn lỗi” vì nó giúp khoanh vùng.

### 2.1. Tối thiểu không có nghĩa thiếu dữ kiện

Một reproducer chỉ có mỗi Java class nhưng lỗi gốc phụ thuộc Gradle plugin hoặc dependency variant sẽ **không tái hiện được**. Tối thiểu nghĩa là **nhỏ nhất mà vẫn giữ nguyên failure signature và điều kiện gây lỗi**.

### 2.2. Log vừa đủ không có nghĩa che mất nguyên nhân

Một dòng “BUILD FAILED” là quá ít. Một file debug hàng trăm MB có thể là quá nhiều. Tùy loại lỗi, giữ failure report, **What went wrong**, **Where**, **Try**, đoạn **Caused by** liên quan, task name và log lân cận. Nếu bị redaction, nói rõ **[REDACTED]** thay vì xóa ngầm khiến stack trace mất cấu trúc.

### 2.3. Chỉ gửi thông tin bạn có quyền chia sẻ

MRE thường an toàn khi dùng synthetic data. Với công việc nội bộ, không tự gửi source private, private artifact URLs, Build Scan links hoặc logs chứa credentials lên issue tracker công khai. Dùng kênh phù hợp và chỉ chia sẻ thông tin cần thiết theo policy.

## 3. Trước tiên: phân loại hiện tượng

| Hiện tượng | Giai đoạn đáng nghi | Dữ liệu đầu tiên nên thu |
| --- | --- | --- |
| Không chạy được ./gradlew | Wrapper/shell/JVM | OS, quyền file, Wrapper script, thông báo lỗi |
| JAVA_HOME không hợp lệ | JVM khởi chạy Gradle | ./gradlew --version, Java/JDK path đã làm mờ |
| IDE sync không thành công, CLI help vẫn chạy | Tooling API/IDE/Gradle JVM/import | IDE/version, Gradle JVM, sync action, IDE log relevant excerpt |
| ./gradlew help cũng fail | Settings, plugins, build configuration | Failure summary, stacktrace, settings/build logic tối thiểu |
| help pass nhưng compileJava fail | Execution, compiler/dependencies | Task, JDK toolchain, source tối thiểu, compiler diagnostics |
| Could not resolve dependency | Repositories/metadata/auth/variant | Coordinates, repositories, --info có kiểm soát, network/proxy |
| Test fail chỉ ở CI | Test runtime/environment | Test class/method, JUnit failure, JDK/OS/locale/timezone, CI config |
| Task không chạy dù input đổi | UP-TO-DATE/cache/input model | Task outcome, --info, declared inputs/outputs |
| Build chỉ lỗi khi --parallel | Concurrency/shared mutable state | Task graph, max-workers, isolation test |
| Build chỉ lỗi khi configuration cache bật | Configuration-cache compatibility | On/off comparison, problems report |
| Gradle Daemon “disappeared” | Process crash/OOM/native/JVM | Gradle daemon log excerpt, memory/container limits |
| Wrapper tải distribution thất bại | Network/proxy/TLS/checksum | Wrapper properties đã redact, network error, trusted CA |
| Lỗi xuất hiện sau nâng plugin/Gradle | Compatibility/regression | Last known good và first bad versions |

Bước đầu là **đặt tên lỗi chính xác**. Một JUnit assertion fail không tự chứng minh Gradle bị lỗi; nó có thể là lỗi của ứng dụng/test. Một IDE sync issue cũng chưa chắc là compileJava bug.

## 4. Đọc phần failure report trước khi thêm logs

Gradle thường in một failure report ở cuối log. Theo tài liệu Gradle:

- **Where**: file build script và line number khi có thể xác định.
- **What went wrong**: lỗi chính hoặc chuỗi nguyên nhân.
- **Try**: các gợi ý có thể hành động.
- **Exception is**: thông tin stack trace khi bật **--stacktrace**.

Ví dụ **minh họa**, không phải một lần chạy đã được đo:

~~~text
> Task :test FAILED

FAILURE: Build failed with an exception.

* What went wrong:
Execution failed for task ':test'.
> There were failing tests. See the report at:
  build/reports/tests/test/index.html

BUILD FAILED
~~~

Trước khi bật DEBUG, hãy kiểm tra **:test** là task nào, test failure cụ thể ở XML/report và có thể cô lập test method nào.

### 4.1. Từ overview đến nguyên nhân gốc

Một error message từ Gradle có thể chỉ là wrapper:

~~~text
Execution failed for task ':compileJava'.
> Compilation failed; see the compiler error output for details.
~~~

Đoạn có ích hơn có thể là:

~~~text
error: cannot find symbol
  symbol: class MissingType
~~~

Không chỉ gửi hai dòng đầu nếu lỗi thực nằm ở compiler diagnostic phía trên.

### 4.2. Đừng cắt mất ngữ cảnh quan trọng

Khi trích log, giữ vài dòng trước và sau nguyên nhân, task name và Gradle version. Không sửa đường dẫn hoặc đổi tên class khiến developer không thể đối chiếu; nếu phải làm mờ private path, dùng một ký hiệu nhất quán như **/REDACTED_WORKSPACE/** và ghi rõ bạn đã redacted.

## 5. Nấc logging: thêm đúng khi cần

Bắt đầu ở mức thấp và chỉ tăng nếu thực sự thiếu chứng cứ.

| Mức | Lệnh/điều khiển | Dùng khi nào | Nguy cơ/nhiễu |
| --- | --- | --- | --- |
| **0: failure report** | ./gradlew task --console=plain | Hầu hết lỗi rõ ràng | Có thể thiếu nested cause |
| **1: stacktrace** | --stacktrace | Cần nơi phát sinh lỗi và cause chain | Paths/class names có thể riêng tư |
| **2: info** | --info | Plugin/dependency/task inputs/daemon cần thêm detail | Log tăng, URLs/metadata nhạy cảm |
| **3: specific diagnostic** | --dependency-insight, --profile, --tests | Đã khoanh vùng một mảng | Chỉ phù hợp từng loại lỗi |
| **4: Build Scan** | --scan | Cần task timeline, environment, dependency views | Dữ liệu gửi tới dịch vụ/server |
| **5: debug** | --debug | Lỗi hiếm, cần điều tra sâu có kiểm soát | Rất lớn, có thể lộ secrets |
| **JVM debugger/JFR** | org.gradle.debug / Java Flight Recorder | Code path/GC/native issue | Cần quyền, có overhead, không nên publish tùy tiện |

Ví dụ:

~~~bash
./gradlew test --console=plain
./gradlew test --console=plain --stacktrace
./gradlew test --console=plain --info --stacktrace
~~~

**Không tự động thêm mọi flag trong lần đầu.** Một reproducer ít biến số dễ đọc hơn. Gửi lệnh cơ bản gây lỗi, sau đó thêm một lệnh diagnostic có chủ đích.

### 5.1. --console=plain

Giúp output ổn định, không có progress console động; thuận tiện trích log và so giữa các hệ thống. Đây **không phải flag bảo mật** và không làm thay đổi nguyên nhân lỗi.

### 5.2. --stacktrace

Cho biết exception chain và vị trí code nếu lỗi là exception. Không đảm bảo tự chứa compiler diagnostics hoặc test assertion details cần thiết. Nếu Gradle báo thiếu dependency artifact do TLS, hãy giữ đoạn network/repository error, không chỉ 500 stack frames.

### 5.3. --info

Thường dùng để kiểm tra task được coi UP-TO-DATE hay không, dependency lookup, configuration, test process launch và compiler options. Khi gửi log, trích đoạn chứa task/lỗi; giữ file full log **ở nơi được cấp quyền** chỉ khi người xử lý yêu cầu.

### 5.4. --debug

Có thể tiết lộ thông tin nhạy cảm theo cảnh báo Gradle. Không chạy với real publishing credentials trên untrusted CI hoặc tự upload debug log công khai. Nếu phải dùng, chạy ở môi trường thử nghiệm đã sanitize, quyền truy cập giới hạn, retention phù hợp và redact trước khi chia sẻ.

### 5.5. --scan

Build Scan có thể nắm failure stacktrace, console log, task outcomes, dependency/version và environment; trên dịch vụ công khai, người có link có thể xem theo chính sách dịch vụ. **Chỉ xuất bản khi tổ chức cho phép**, dữ liệu đã review và server/access controls phù hợp. Đừng coi một scan link khó đoán là đủ bảo vệ dữ liệu.

## 6. Ghi lại command line chính xác

Một báo lỗi nên có lệnh đầy đủ, bao gồm task path, project directory và flags có tác động.

Nên viết:

~~~bash
./gradlew :app:test \
  --tests 'demo.repro.ReproTest' \
  --console=plain \
  --stacktrace
~~~

Chú thích: lệnh trên là cú pháp chọn test theo class name, yêu cầu project thật có module **:app** và class **demo.repro.ReproTest**. Lab chạy ở root (mục sau) sẽ dùng **:test**, không có :app.

Không nên chỉ viết “chạy Gradle test bằng nút màu xanh trong IDE”. Nút đó có thể sử dụng JUnit runner của IDE chứ không phải Gradle Test task.

### 6.1. Nếu dùng command shell Windows

PowerShell chạy Wrapper:

~~~powershell
.\gradlew.bat test --console=plain --stacktrace
~~~

Linux/macOS:

~~~bash
./gradlew test --console=plain --stacktrace
~~~

Không copy ký hiệu **./** của Linux vào cmd.exe rồi kết luận Windows không hỗ trợ Gradle. Ngược lại, **gradle** có thể là bản Gradle cài toàn máy chứ không phải Wrapper của repo.

### 6.2. Bắt buộc dùng Wrapper trong reproducer

**gradlew** và **gradle/wrapper/gradle-wrapper.properties** xác định Gradle distribution cho dự án. Khi gửi reproducer, nên commit **gradlew**, **gradlew.bat**, Wrapper JAR và properties (khi được phép). Không tự thay Wrapper version để “sửa” báo lỗi mà không ghi nhận vì sẽ thay chính yếu tố cần tái hiện.

### 6.3. Phân biệt root và subproject task

Multi-project:

~~~text
:api:compileJava
:app:test
:build-logic:check
~~~

Task path là dữ kiện quan trọng. Một **test** chạy từ root có thể chọn nhiều tasks khác với **:app:test**. Khi giảm MRE, giữ path chính xác cho tới khi đã chứng minh lỗi vẫn xảy ra trong một project duy nhất.

## 7. Thu môi trường tối thiểu

Trên máy gặp lỗi:

~~~bash
./gradlew --version
~~~

Thường cho biết Gradle version, JVM chạy Gradle, OS và thông tin liên quan. **Chỉ gửi các trường thực sự cần**, chẳng hạn:

~~~text
Gradle Wrapper: 9.x (ghi đúng số in ra)
Gradle JVM: JDK 17, vendor theo lệnh --version
Java toolchain: 17
OS: Linux x86_64 / Windows x64 / macOS ARM64
IDE: IntelliJ IDEA, Buildship/Eclipse hoặc VS Code; ghi version
Task: :test
Command: ./gradlew test -PreproFail=true --console=plain
~~~

Dòng trên chỉ là **khuôn thông tin**, không khẳng định phiên bản Gradle cụ thể của người đọc. Chạy **./gradlew --version** để lấy dữ liệu thật.

### 7.1. Các giá trị thường cần, thường không cần

Nên giữ:
- Gradle Wrapper version.
- JVM chạy Gradle và JDK toolchain biên dịch/test.
- OS/architecture khi vấn đề phụ thuộc nền tảng.
- Plugin/dependency version liên quan.
- Task path và invocation flags.
- Last-known-good/first-bad version nếu đã xác định.
- Proxy/repository category nếu lỗi resolution, nhưng **không** gửi URL có token.

Hạn chế/chỉ chia sẻ có chủ đích:
- Username thật, user home absolute path.
- Machine name, IP nội bộ.
- Full environment dump.
- Access tokens, passwords, cookies, signing keys.
- Private URLs, CI runner IDs, proprietary source names không cần thiết.
- Raw database fixtures, production log bundles.
- Full list tất cả installed applications/processes.

### 7.2. JAVA_HOME và toolchain là hai thứ khác nhau

Gradle có thể chạy bằng một JDK, còn **java.toolchain** chọn compiler/JVM cho project. IDE cũng có **Project SDK**, **Gradle JVM** và test runner riêng.

Ví dụ Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

đảm bảo lựa chọn toolchain yêu cầu Java 17; nó không tự khẳng định Gradle Daemon cũng chạy đúng JDK đó. Với lỗi **UnsupportedClassVersionError**, **release target**, **toolchain download**, hãy ghi rõ JVM nào thực sự được dùng ở từng bước.

### 7.3. Gradle version compatibility

Không đổi JDK hoặc Wrapper một cách ngẫu nhiên. Ghi version trước khi thử. Khi xác định compatibility regression, hãy đổi một biến mỗi lần và chạy cùng task. Gradle 9.x yêu cầu JDK thích hợp để chạy Gradle; thông tin cụ thể theo bản Wrapper nên đối chiếu Gradle compatibility matrix.

## 8. Phân biệt lỗi IDE và lỗi Gradle CLI

Một trong những bước chẩn đoán giá trị nhất:

~~~bash
./gradlew help --console=plain
./gradlew test --console=plain
~~~

So sánh với hành vi **IDE sync/import**, **IDE Run Test**, **IDE delegated Gradle task**.

| Kết quả CLI | Kết quả IDE | Hướng điều tra |
| --- | --- | --- |
| help fail | IDE sync fail | Settings/plugins/build configuration |
| help pass, test fail | IDE test fail | Gradle task, test/dependencies |
| help pass, test pass | IDE sync fail | IDE import, Tooling API, Gradle JVM, plugin compatibility |
| CLI test pass | IDE native JUnit test fail | IDE runner classpath, SDK, working dir |
| CLI test fail | IDE test pass | Task args/env/classpath hoặc runner differences |
| CLI chỉ fail với --configuration-cache | IDE sync bình thường | Configuration-cache behavior, không quy kết IDE |
| Chỉ một máy IDE fail | CI/CLI pass | Local JDK, plugin, proxy, IDE settings, permissions |

### 8.1. IntelliJ IDEA

Các kiểm tra hữu ích:

- IDE và Gradle plugin version.
- Gradle tool window: **Sync All Gradle Projects** nếu project linked.
- Gradle JVM được chọn trong Gradle settings.
- Project SDK và language level.
- Delegated build/run to Gradle hay IDE compiler/runner.
- Run Configuration: Gradle task, args, working directory, environment variables.
- IDE log **đúng đoạn lỗi** chứ không export toàn bộ workspace/system information trước khi cần.

UI labels có thể thay theo IDE version. Dùng những chức năng tương đương thay vì dựa tuyệt đối vào tên nút.

### 8.2. Eclipse/Buildship

Dùng **Gradle > Refresh Gradle Project** (theo phiên bản Buildship/Eclipse), ghi Gradle JVM và Gradle distribution settings. So **Tooling API import** với **./gradlew help**: CLI help pass nhưng Buildship sync fail là dữ liệu phân loại hữu ích, không chứng minh lỗi compiler.

### 8.3. VS Code hoặc editor khác

Ghi extension/version, Java runtime configuration, cách project import Gradle và lệnh thực sự được IDE extension thực thi. Tốt nhất là tạo một CLI reproduction trước để tránh phụ thuộc vào plugin của editor nếu cùng failure xảy ra trên cả hai.

### 8.4. Configuration cache và IDE sync

Theo Gradle docs, project import/sync trong IDE không dùng configuration cache theo cùng cách task execution có thể dùng nó. Vì vậy tắt configuration cache khi một IDE sync fail chưa chắc giải quyết đúng vấn đề. So tasks được IDE ủy quyền chạy qua Gradle với hoạt động model import riêng.

## 9. Phân loại giai đoạn fail bằng lệnh help

~~~bash
./gradlew help --console=plain
~~~

Nếu **help** fail, Gradle chưa cần compile/test application sources để báo lỗi. Xem:

- settings.gradle/settings.gradle.kts.
- pluginManagement và dependencyResolutionManagement.
- Plugin resolution.
- build.gradle/build.gradle.kts.
- buildSrc, included builds và init scripts.
- Configuration-time code và Provider APIs.
- IDE Tooling API model evaluation nếu chỉ lỗi ở IDE.

Nếu **help** pass nhưng **compileJava** fail:

~~~bash
./gradlew compileJava --console=plain --stacktrace
~~~

thì lỗi có khả năng nằm ở task execution, compilation, toolchain hoặc dependencies. **help pass không tự chứng minh toàn bộ configuration model trong mọi invocation giống hệt**, nhưng là bước khoanh vùng rất hiệu quả.

### 9.1. Nếu compileJava pass, test fail

~~~bash
./gradlew test --console=plain --stacktrace
~~~

Kiểm tra **Test task**, JUnit engine, test classpath, Java toolchain, test reports, working directory, environment input và assertion.

### 9.2. Nếu chỉ fail khi publish

Đừng đưa production deploy keys vào MRE. Tạo một local/mocked repository endpoint hoặc test publisher với credentials giả, và chứng minh bug mà không cần truy cập dịch vụ thật. Không chạy task publish thật chỉ để tái hiện issue trong repository public.

## 10. Nguyên tắc rút gọn MRE

Bắt đầu từ failure có thật, loại bỏ từng phần **và chạy lại sau mỗi thay đổi**.

Giữ:

- Settings script cần cho project/plugin management.
- Build script nhỏ nhất.
- Gradle Wrapper scripts/JAR/properties.
- Một source hoặc test file tối thiểu.
- Plugin/dependency versions nếu chúng gây failure.
- Command line tái hiện.
- Synthetic fixture và README hướng dẫn.

Loại khi đã chứng minh không ảnh hưởng:

- Những modules không tham gia lỗi.
- Các tasks unrelated như publishing/coverage/dokku deployment.
- Source files và resources không cần.
- Repositories thừa.
- Tooling integrations không liên quan.
- Third-party plugins không tham gia reproduction.
- IDE settings nếu lỗi tái hiện thuần CLI.
- Sample data thật và secrets.

**Rủi ro khi rút gọn:** xóa mất điều kiện gây lỗi. Nếu bug nằm ở variant-aware dependency resolution, không thể bỏ dependency configuration rồi dùng một file JAR hardcoded. Nếu bug nằm ở included build, phải giữ included build tối thiểu.

### 10.1. Cắt giảm theo phương pháp thử nghiệm

Gợi ý quy trình:

1. Sao chép vào một **repo/reproducer riêng**, không làm hỏng repo production.
2. Chạy baseline và ghi failure signature.
3. Loại khoảng một nửa modules/plugins nghi ngờ.
4. Chạy lại đúng lệnh.
5. Nếu bug vẫn còn, giữ phiên bản nhỏ hơn; nếu biến mất, phục hồi nhóm liên quan.
6. Lặp lại cho đến khi mọi thành phần còn lại đều có lý do tồn tại.
7. Đối chiếu test result với môi trường ban đầu.
8. Chạy từ checkout sạch để phát hiện missing files hoặc hidden local state.

Đây là kiểu **delta debugging**. Quan trọng là không được **đổi bản chất lỗi** trong khi giảm: một NullPointerException mới do xóa nhầm config không chứng minh bug gốc còn tồn tại.

### 10.2. Lập bảng reduction log

| Bước | Thay đổi | Failure signature còn? | Kết luận |
| --- | --- | --- | --- |
| 0 | Project gốc | Có | Baseline |
| 1 | Bỏ module docs | Có | docs không cần |
| 2 | Bỏ plugin publishing | Có | publish không cần |
| 3 | Bỏ plugin Kotlin | Không | Cần xem plugin hoặc nguồn tương tác |
| 4 | Khôi phục Kotlin plugin tối thiểu | Có | Plugin là yếu tố cần giữ |
| 5 | Bỏ resources thừa | Có | Sẵn sàng MRE |

Bảng trên là **ví dụ giả định**, không phải nhật ký đã chạy thật.

## 11. MRE Java 17: tạo lỗi kiểm thử có thể bật/tắt

Ta xây một project Gradle nhỏ, không cần secrets hoặc dịch vụ ngoài. Nó có:

- Một Java 17 class **App** luôn trả kết quả ổn định.
- Một JUnit 5 test xác nhận logic ứng dụng.
- Một JUnit 5 test chỉ thất bại khi bật **-PreproFail=true**.
- Một test failure marker **DEMO_EXPECTED_FAILURE** không chứa dữ liệu nhạy cảm.
- Cấu hình **Test.systemProperty** truyền cờ Gradle vào test JVM.
- Wrapper và lệnh để người khác tái hiện độc lập với IDE.

**Mục đích là minh họa quy trình báo lỗi**. Khi cố tình làm test fail, Gradle đang hoạt động đúng: không coi lỗi cố ý này là Gradle defect.

### 11.1. Cây thư mục

~~~text
gradle-minimal-repro/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/demo/repro/App.java
    └── test/java/demo/repro/ReproTest.java
~~~

Nếu chưa có Wrapper, dùng một Gradle CLI được tin cậy để tạo:

~~~bash
gradle wrapper
~~~

Đảm bảo Wrapper version tương thích JDK 17 rồi commit đầy đủ Wrapper scripts, JAR và properties. Không dùng wrapper JAR tải từ liên kết không rõ nguồn. Trong bug report thực tế hãy ghi **số phiên bản chính xác** từ ./gradlew --version.

### 11.2. settings.gradle

~~~groovy
rootProject.name = 'gradle-minimal-repro'
~~~

### 11.3. build.gradle

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.repro.App'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release.set(17)
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    systemProperty 'repro.fail',
            providers.gradleProperty('reproFail')
                    .getOrElse('false')

    testLogging {
        events 'failed', 'skipped'
        showStandardStreams = false
        exceptionFormat =
            org.gradle.api.tasks.testing.logging
                .TestExceptionFormat.SHORT
    }
}
~~~

**Giải thích:**

- **application** bổ sung Java plugin và task run.
- **java.toolchain 17** chọn JDK Java 17 cho compilation/test.
- **options.release=17** giữ API/classfile target Java 17.
- JUnit Jupiter và JUnit Platform Launcher cho Gradle Test task.
- **providers.gradleProperty('reproFail')** lấy cờ do người dùng truyền, mặc định false.
- **systemProperty 'repro.fail'** truyền cờ vào forked Test JVM.
- **testLogging** chỉ hiện test failures/skips và không bật stdout của tests.
- Không đọc environment secrets; không cần production database, API hoặc repository private.

Cờ **-PreproFail** là một giá trị test-safe, không phải credential. Không truyền mật khẩu thật qua command-line project properties rồi sao chép vào bug report.

### 11.4. src/main/java/demo/repro/App.java

~~~java
package demo.repro;

public final class App {
    private App() {
    }

    public static String message() {
        return "REPRO_OK:17";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

**Stdout chính xác của Java Main:**

~~~text
REPRO_OK:17
~~~

### 11.5. src/test/java/demo/repro/ReproTest.java

~~~java
package demo.repro;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class ReproTest {

    @Test
    void applicationOutputIsStable() {
        assertEquals("REPRO_OK:17", App.message());
    }

    @Test
    void intentionalFailureOnlyWhenRequested() {
        boolean trigger = Boolean.parseBoolean(
                System.getProperty("repro.fail", "false"));

        assertFalse(trigger, "DEMO_EXPECTED_FAILURE");
    }
}
~~~

Có **hai test methods**:

- **applicationOutputIsStable**: luôn pass nếu App giữ nguyên source.
- **intentionalFailureOnlyWhenRequested**: pass khi repro.fail=false, fail khi repro.fail=true và xuất failure marker **DEMO_EXPECTED_FAILURE**.

Cấu hình cho phép chạy lại lỗi mà không sửa source. Dữ liệu của lab hoàn toàn giả và không chứa secret.

## 12. Chạy baseline pass trước khi tạo lỗi

Linux/macOS:

~~~bash
./gradlew clean test --console=plain
./gradlew -q run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test --console=plain
.\gradlew.bat -q run
~~~

Điều kiện kỳ vọng:

- **:compileJava** và **:compileTestJava** thành công.
- **:test** có hai test methods pass.
- Process kết thúc **BUILD SUCCESSFUL**.
- Java Main in đúng **REPRO_OK:17**.

Lệnh trực tiếp để kiểm tra Java không cần Gradle:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -d out src/main/java/demo/repro/App.java
java -cp out demo.repro.App
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src\main\java\demo\repro\App.java
java -cp out demo.repro.App
~~~

Stdout chính xác:

~~~text
REPRO_OK:17
~~~

**Giới hạn của phép thử javac:** nó chỉ chứng minh class Java main chạy được, không xác nhận Gradle Test task/JUnit dependencies, plugin resolution hay Gradle Wrapper.

## 13. Tạo một lỗi có thể tái hiện

Chạy:

~~~bash
./gradlew test \
  -PreproFail=true \
  --console=plain \
  --stacktrace
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test -PreproFail=true --console=plain --stacktrace
~~~

**Kết quả kỳ vọng:**

- :test **FAILED**.
- Có một JUnit assertion failure liên quan method **intentionalFailureOnlyWhenRequested**.
- Failure message chứa marker **DEMO_EXPECTED_FAILURE**.
- Build kết thúc **BUILD FAILED** với exit code khác 0.
- Test thứ nhất vẫn pass, test thứ hai fail.

Những dòng console dưới đây là **minh họa**, không cam kết trật tự hay chi tiết của mọi Gradle version:

~~~text
> Task :test FAILED
ReproTest > intentionalFailureOnlyWhenRequested() FAILED
    org.opentest4j.AssertionFailedError: DEMO_EXPECTED_FAILURE

FAILURE: Build failed with an exception.
* What went wrong:
Execution failed for task ':test'.
BUILD FAILED
~~~

**Đây không phải bug của Gradle.** Nó là test được thiết kế để fail theo input. Khi viết báo lỗi thật, thay marker và nguồn gây lỗi bằng cơ chế lỗi thực tế, nhưng giữ phong cách reproducer tối giản.

### 13.1. Tại sao lệnh này đáng tin hơn “bấm nút Test”?

- Wrapper xác định Gradle version.
- CLI flag kiểm soát trạng thái một cách rõ ràng.
- Test class/method có tên ổn định.
- Không cần biến môi trường ẩn.
- Không phụ thuộc source code production.
- Có thể chạy cùng lệnh trên CI, Linux/macOS và Windows với khác biệt script shell rõ ràng.
- Expected failure signature có marker dễ đối chiếu.

### 13.2. Tạo kiểm chứng đảo ngược

~~~bash
./gradlew test \
  -PreproFail=false \
  --console=plain
~~~

Lần này **BUILD SUCCESSFUL** là kỳ vọng vì hai tests pass. Nếu đổi cờ mà vẫn fail, cần điều tra môi trường/test runner; không đưa ra issue report “đã kiểm soát hoàn toàn” khi chưa thực sự xác minh.

### 13.3. Khi không thấy test failure

Có thể do:

- Test task NO-SOURCE hoặc JUnit engine không phát hiện tests.
- Lệnh chạy IDE native JUnit runner thay vì Gradle Test task, không truyền systemProperty.
- Sai build.gradle hoặc không đứng ở project root.
- Dùng sai flag name (**-PreproFail** khác **-DreproFail**).
- Test configuration bị override.
- Source JUnit class chưa được compile do missing testRuntimeClasspath.
- Build đã fail sớm ở dependency resolution trước khi chạy test.

Đọc task outcomes thay vì tự kết luận bug đã “biến mất”.

## 14. Thu bằng chứng cho lab ở mức tối thiểu

Một bộ chứng cứ mẫu hợp lý:

~~~text
Version:
  ./gradlew --version

Reproducer:
  settings.gradle
  build.gradle
  src/main/java/demo/repro/App.java
  src/test/java/demo/repro/ReproTest.java
  Gradle Wrapper files

Command:
  ./gradlew test -PreproFail=true --console=plain --stacktrace

Expected:
  Two tests pass when -PreproFail=false.
  When true: one intentionally failing test, marker DEMO_EXPECTED_FAILURE.

Actual:
  :test FAILED, JUnit AssertionFailedError:
  DEMO_EXPECTED_FAILURE.

Environment:
  Gradle Wrapper version, JDK Gradle JVM, toolchain 17, OS.
~~~

Khi đã có MRE, người nhận **không cần 20 ảnh chụp màn hình** hoặc toàn bộ ~/.gradle. Gửi một archive nhỏ của source nếu repository không chứa private data, hoặc cung cấp các file như code blocks trong internal ticket.

### 14.1. Lưu log đúng cách nhưng không làm mất exit code

Trên Linux/macOS có thể chuyển stdout+stderr vào file:

~~~bash
./gradlew test \
  -PreproFail=true \
  --console=plain \
  --stacktrace \
  > repro.log 2>&1

result=$?
tail -n 100 repro.log
exit "$result"
~~~

Script này không bật **set -e**, nên có thể thu exit code rồi thoát với cùng code. Không dùng **|| true** để che lỗi; cũng không xem việc file log tồn tại là test success.

Nếu muốn lưu file nhưng vẫn xem console tức thì, có thể dùng **tee** cùng shell pipefail, lưu ý POSIX shells và Bash có cơ chế xử lý pipeline khác nhau. Ví dụ trên ưu tiên rõ ràng, tương thích nhiều shell.

PowerShell:

~~~powershell
& .\gradlew.bat test -PreproFail=true --console=plain --stacktrace *> repro.log
$code = $LASTEXITCODE
Get-Content repro.log -Tail 100
exit $code
~~~

Bước **tail/Get-Content** chỉ dùng với synthetic MRE. Với log từ hệ thống thật, phải **scan/redact trước khi phát tán hoặc in lại** những dòng chứa credentials. File repro.log cũng phải có quyền/retention phù hợp.

### 14.2. Chỉ sao chép phần liên quan

Ví dụ một report thực tế có thể trích:

~~~text
Command: ./gradlew test -PreproFail=true --console=plain
Outcome: > Task :test FAILED
Test: demo.repro.ReproTest.intentionalFailureOnlyWhenRequested
Cause: org.opentest4j.AssertionFailedError: DEMO_EXPECTED_FAILURE
Exit: non-zero
~~~

Đây đủ để người khác chạy lại lab. Khi cần stacktrace đầy đủ, đính kèm bản đã review với quyền hạn thích hợp, không dán mọi thứ lên ticket public.

## 15. Tìm test nhỏ nhất gây lỗi

Nếu suite rất lớn nhưng một test fail, chạy riêng class/method.

Giả sử source là lab:

~~~bash
./gradlew test \
  --tests 'demo.repro.ReproTest.intentionalFailureOnlyWhenRequested' \
  -PreproFail=true \
  --console=plain \
  --stacktrace
~~~

Nếu lỗi vẫn xảy ra, reproducer có thể chỉ cần một test method và các dependencies tối thiểu.

### 15.1. Chú ý khi lỗi phụ thuộc thứ tự test

Một số flaky bugs chỉ xuất hiện khi chạy **cả suite** do shared mutable state, static caches, fixed TCP port hoặc database. Khi chỉ chạy một method, lỗi biến mất. Lúc đó không nên ép MRE về một test; hãy giữ **nhóm test nhỏ nhất** còn kích hoạt interaction.

### 15.2. Chú ý khi lỗi phụ thuộc JVM fork

**maxParallelForks** và **forkEvery** có thể ảnh hưởng concurrency/isolation của Test task. Nếu lỗi chỉ xuất hiện khi hai classes chạy song song, phải giữ cấu hình đó trong MRE và ghi số CPU/worker limits. Đổi maxParallelForks=1 để “sửa” có thể che race condition.

## 16. Tối thiểu hóa dependency resolution failure

Nếu failure xảy ra trước test, chuyển trọng tâm từ test code sang **coordinates/repositories/version resolution**.

Thu:

- Requested dependency coordinate, version constraint.
- Configuration gây lỗi: compileClasspath, runtimeClasspath, testRuntimeClasspath, annotationProcessor.
- Repository type, thứ tự và URL đã sanitize.
- Proxy/TLS/auth method theo loại, không gửi credential.
- Online/offline state.
- Gradle Wrapper version và flags.
- Error 401/403/404/PKIX hoặc variant mismatch chính xác.

Lệnh thường hữu ích:

~~~bash
./gradlew dependencies \
  --configuration testRuntimeClasspath \
  --console=plain
~~~

và với một module có thật:

~~~bash
./gradlew dependencyInsight \
  --dependency junit-jupiter-api \
  --configuration testRuntimeClasspath \
  --console=plain
~~~

Các lệnh dùng cho **root single-project lab**. Trong multi-project build, thêm task path project như **:app:dependencies** và **:app:dependencyInsight**.

### 16.1. dependencies không luôn tải mọi JAR

Báo cáo dependency graph có thể chỉ resolve metadata. Một lỗi tải artifact có thể chỉ xuất hiện khi **compileJava** hoặc **test** thực sự cần JAR file. Đừng thay lỗi download bằng một graph report pass rồi tuyên bố issue resolved.

### 16.2. --offline là một phép thử có điều kiện

~~~bash
./gradlew test --offline --console=plain
~~~

Nếu dependencies còn thiếu trong cache, offline fail là **kết quả bình thường**, không chứng minh root cause ban đầu. Nếu offline pass còn online fail do repository timeout, đó là dấu hiệu hữu ích nhưng vẫn cần xác minh metadata/cache.

### 16.3. --refresh-dependencies không phải lệnh xóa sạch cache

~~~bash
./gradlew test \
  --refresh-dependencies \
  --console=plain
~~~

Gradle có thể kiểm tra metadata/checksums rồi reuse cached artifacts nếu chúng không đổi. Ghi rõ bạn đã bật flag này vì nghi metadata stale; đừng dùng nó mặc định cho mọi reproducer, vì nó thay hành vi resolution và có thể tăng network traffic.

### 16.4. Tránh gửi private repository credentials

Ví dụ một lỗi 401 nên được mô tả như:

~~~text
Repository: internal Maven proxy (hostname redacted)
Requested: org.example:artifact:1.2.3
HTTP status: 401
Authentication type: token
Credential value: REDACTED
~~~

Nếu source private và coordinates cũng bí mật, cần dùng internal support channel hoặc tạo dependency giả trên server sandbox được phép. Không tự động đưa private artifact coordinates vào public issue.

## 17. Lỗi configuration cache: tái hiện bằng A/B

Configuration cache reuse state của configuration phase. Nó không giống task output build cache.

Trường hợp lỗi chỉ xảy ra khi bật:

~~~bash
./gradlew help --configuration-cache --console=plain
./gradlew help --no-configuration-cache --console=plain
~~~

Nếu chỉ **--configuration-cache** fail, ghi hai outcomes và Gradle configuration cache problems report nếu có. Đừng xóa toàn bộ ~/.gradle để làm lỗi biến mất tạm thời.

### 17.1. Lưu configuration-cache problems report có chọn lọc

Gradle có thể tạo reports liên quan đến configuration cache ở **build/reports/configuration-cache/** hoặc những paths được console nêu ra, tùy version. Đính kèm file liên quan sau khi review, không upload mọi file từ .gradle/configuration-cache/ vì đó là internal state và có thể chứa dữ liệu môi trường.

### 17.2. IDE sync và configuration cache

IDE import/sync và Gradle task execution không cùng cơ chế. Theo Gradle docs, IDE sync không dùng configuration cache giống task execution; do vậy “sync fail nhưng --no-configuration-cache giúp task test” không chứng minh configuration cache là nguyên nhân sync.

### 17.3. Không lạm dụng warning mode

**--configuration-cache-problems=warn** không nên được dùng vĩnh viễn để hợp thức hóa cấu hình sai. Khi báo bug, giữ cách Gradle fail ban đầu; chỉ thử warn mode nếu điều tra compatibility có chủ đích, và ghi rõ nó thay điều kiện.

## 18. Lỗi build cache/up-to-date: khi nào phải dùng --rerun-tasks?

Nếu người dùng báo “đã sửa source nhưng task không chạy”, trước tiên xem trạng thái:

~~~bash
./gradlew compileJava --info --console=plain
~~~

- **UP-TO-DATE**: Gradle thấy inputs/outputs hiện hành hợp lệ.
- **FROM-CACHE**: output được khôi phục từ task output build cache.
- Task chạy thật không suffix: có thể incremental compile bên trong.
- **NO-SOURCE/SKIPPED**: kiểm tra source set và skip conditions.

Lệnh chẩn đoán để ép action:

~~~bash
./gradlew compileJava \
  --rerun-tasks \
  --no-build-cache \
  --console=plain
~~~

**Không dùng cờ này ngay từ đầu nếu vấn đề gốc là incremental build bị sai**. Nó che trạng thái task avoidance. Nên giữ hai lượt bằng chứng:

1. Lệnh gốc với --info để thấy Gradle đang skip/cache.
2. Lệnh forced execution riêng để xem bug có phụ thuộc cơ chế incremental/cache không.

### 18.1. Không xóa outputs và caches thiếu kiểm soát

Clean có thể loại bỏ evidence về lỗi chỉ xảy ra trên incremental build. Xóa **~/.gradle/caches/** có thể làm lại hàng nghìn dependency downloads, ảnh hưởng dự án khác và che bug. Thử với **Gradle User Home riêng** hoặc một workspace/repo clone thay vì xóa dữ liệu chung.

## 19. Lỗi Daemon và JVM

Một lỗi như:

~~~text
Gradle build daemon disappeared unexpectedly
~~~

thường cần dữ liệu khác với JUnit assertion:

- Gradle Wrapper version.
- Java runtime chạy Gradle.
- Memory flags: **org.gradle.jvmargs** (đã redact nếu nhạy cảm).
- Container/cgroup memory limit.
- OOM killer event, native crash log nếu có.
- Daemon log excerpt ngay trước khi crash.
- OS/architecture.
- Mức song song, số tasks/JVM test workers.

Gradle Daemon logs thường nằm dưới **GRADLE_USER_HOME/daemon/<version>/**. Không upload toàn Gradle User Home vì có thể chứa credentials/cache/private metadata.

### 19.1. --no-daemon là phép thử, không phải chữa mọi lỗi

~~~bash
./gradlew help --no-daemon --console=plain
~~~

Cờ này yêu cầu không reuse persistent Daemon theo cách thông thường. Trong một số cấu hình JVM, Gradle vẫn có thể khởi tạo **single-use daemon** để chạy build; không mô tả nó như “không có JVM process nền nào”.

Nếu chỉ lỗi với persistent Daemon, xem JDK/JVM args, init scripts và state giữa invocations. Không ép mọi developer build dùng --no-daemon mà chưa hiểu chi phí.

### 19.2. --stop có phạm vi rộng hơn một task

~~~bash
./gradlew --stop
~~~

Dừng Gradle daemons thuộc Gradle version/user home liên quan; có thể ảnh hưởng những builds khác của cùng người dùng. Chỉ chạy khi có lý do, tốt nhất trong workspace/agent được quản lý; không coi --stop là bước đầu của mọi reproducer.

### 19.3. JVM debug

Gradle hỗ trợ debugger cho build logic thông qua **-Dorg.gradle.debug=true**. Một debugger mở cổng hoặc chờ attach làm thay đổi timing và có rủi ro security; chỉ dùng trên máy tin cậy, không mở debug port công khai. Không đưa cờ này vào MRE nếu lỗi có thể được tái hiện bằng logs ngắn.

## 20. Lỗi chỉ xuất hiện trên CI hoặc trên một máy

Tạo một bảng so sánh có kiểm soát:

| Thuộc tính | Local | CI | Ý nghĩa |
| --- | --- | --- | --- |
| Wrapper version | Theo --version | Theo --version | Phải khớp nếu so cùng build |
| JVM chạy Gradle | JDK vendor/version | JDK vendor/version | Có thể khác dù toolchain cùng 17 |
| Java toolchain | 17 | 17 | Kiểm tra path/JDK provisioning |
| OS/architecture | Windows x64 | Linux x64 | File separator/case/permissions khác |
| Locale/timezone | Ghi khi ảnh hưởng | Ghi khi ảnh hưởng | Test formatting/date dễ flake |
| Gradle args | IDE/run config | CI workflow args | --parallel/cache/offline khác |
| Cache state | Warm | Cold/remote cache | Không tự là lỗi correctness |
| Network/proxy | Direct | Proxy/mirror | TLS/repository issues |
| Filesystem | NTFS | ext4/overlayfs | Case sensitivity/permissions |
| Env variables | Local | CI secret store | Không dump raw values |

Không cần thu toàn bộ environment; chỉ ghi **sự khác biệt liên quan đến giả thuyết**.

### 20.1. Khi bug không xảy ra trên máy developer

- Chạy cùng Wrapper.
- Chạy đúng task và flags từ CI.
- Dùng JDK/OS tương đương (container nếu được phép).
- Ghi timezone/locale khi test phụ thuộc.
- Thử fixed input/fixture, clock và random seed.
- Kiểm tra filesystem case sensitivity.
- Thử sạch dependencies/workspace có quản lý.
- Xem test worker parallelism và resource constraints.

### 20.2. Reproducer cần độc lập với secrets thật

Nếu CI issue chỉ xuất hiện khi có secret/token thật, có thể tạo mock server, fake credential và synthetic response body để giữ failure mode. Nếu bug đòi hỏi credential thật và không thể giả lập, báo nội bộ trong kênh được phép thay vì gửi public MRE.

## 21. Lỗi biến mất sau khi “xóa cache”: chưa đủ kết luận

Lệnh:

~~~bash
./gradlew clean
~~~

xóa outputs do clean task quản lý, nhưng **không mặc định xóa local build cache hoặc downloaded dependency cache**. Nếu lỗi biến mất, hãy hỏi:

- Lỗi nằm ở generated output cũ?
- Input/outputs model sai?
- Build cache entry có vấn đề?
- IDE stale import model?
- Dependency metadata có được refresh?
- Daemon/process state thay đổi?
- Một task chỉ chạy khi output không tồn tại?

Không ghi vào ticket “cache hỏng” chỉ dựa trên việc clean giúp.

### 21.1. Tối ưu hóa phép thử

| Thử nghiệm | Điều nó kiểm tra | Điều không chứng minh |
| --- | --- | --- |
| clean test | Output workspace mới | Dependency cache đã xóa |
| --no-build-cache | Không restore task outputs | Task action chắc chắn chạy nếu UP-TO-DATE |
| --rerun-tasks | Bỏ up-to-date task avoidance | Build cache đã được xóa khỏi disk |
| --no-configuration-cache | Không reuse config state | IDE sync không có state |
| --offline | Không resolve qua network | Dependencies ở cache đều đúng phiên bản mong muốn |
| --refresh-dependencies | Kiểm tra dependency freshness | Mọi artifact đều tải lại |
| --no-daemon | Không reuse persistent daemon | Không tạo process JVM nào |
| --max-workers=1 | Giảm concurrency | Bug chắc chắn là race |
| --no-parallel | Tắt parallel project execution | Tất cả Test workers đều tuần tự nếu maxParallelForks>1 |

Mỗi flag là một **biến của thí nghiệm**. Đừng gửi một dòng CLI có 12 flags mà không giải thích chúng đã làm gì.

## 22. Log và dữ liệu nhạy cảm: nguyên tắc thu vừa đủ

Những nơi dễ rò dữ liệu:

- Environment variable dumps và Java system properties.
- URL repository có user/password/query token.
- HTTP authorization headers.
- CI mask placeholders và log sau decoding.
- Stack traces chứa absolute home paths.
- Test assertion messages có email, payload hoặc API token.
- JUnit XML, HTML, Build Scan.
- Daemon logs, configuration cache, ZIP artifacts.
- Plugin-specific debug reports.

### 22.1. Không in secret để kiểm tra nó có tồn tại

Không nên:

~~~groovy
// ANTI-PATTERN: không chạy với credential thật.
logger.lifecycle(System.getenv('PRIVATE_TOKEN'))
~~~

Chỉ kiểm tra trạng thái có/không khi thật sự cần, và cân nhắc rằng ngay cả trạng thái configured cũng là metadata. Không truyền token trong CLI **-Ppassword=...** rồi đưa command vào issue report.

### 22.2. Redact có hệ thống

Trước khi chia sẻ log:

1. Tạo một **bản sao** của log; không chỉnh sửa evidence gốc khi cần bảo toàn.
2. Xác định credentials, PII, private URLs, local usernames và business-sensitive names.
3. Thay bằng marker nhất quán: **[REDACTED_TOKEN]**, **[REDACTED_HOST]**, **[REDACTED_USER]**.
4. Giữ message category, HTTP status, task path và source locations đủ để điều tra.
5. Kiểm tra các dạng encoded/multiline, không chỉ replace đúng một chuỗi token.
6. Đọc lại bản cuối; tránh “redaction” vô tình biến logs thành những nguyên nhân mới không tồn tại.
7. Chia sẻ qua kênh phù hợp và retention hạn chế.

### 22.3. Vì sao không tự động công khai Build Scan?

Gradle docs lưu ý scan có console log, error traces, test result và environment. Trên dịch vụ scan có chia sẻ bằng link, người có link có thể xem dữ liệu. Nội bộ phải có policy; nếu chưa có, đính kèm trích đoạn an toàn và reproduction nhỏ là đủ để mở issue.

### 22.4. Nếu đã lộ token

Không chỉ xóa log. Báo security team, revoke/rotate credentials theo policy, hạn chế quyền truy cập scan/artifacts, đánh giá bản sao CI/backup, sửa nguồn leak, thử lại với synthetic canary. Một credential đã được public phải được xem là có nguy cơ bị sao chép.

## 23. Giữ reproducer có thể chạy từ checkout sạch

Một MRE tốt nên thử:

1. Chuyển vào một **thư mục khác** không có build outputs.
2. Chỉ copy source/config/Wrapper cần thiết.
3. Không copy **.gradle/**, **build/**, **.idea/** hoặc hidden local jars trừ khi chính chúng là điều kiện bug cần mô hình hóa.
4. Ghi JDK requirement và command.
5. Chạy chính xác command đã ghi.
6. Đối chiếu cùng failure signature.
7. Thử một người khác/CI sandbox chạy lại, không cần private credentials.
8. Nếu cần Maven artifact public, pin version và verify source.
9. Ghi môi trường cần thiết một cách ngắn gọn.
10. Nếu không thể tái hiện, giải thích điểm thiếu thay vì tuyên bố ready.

### 23.1. .gitignore cho MRE

~~~gitignore
.gradle/
build/
out/
.idea/
*.iml
repro.log
*.hprof
hs_err_pid*.log
~~~

Không commit generated outputs, cached credential files, heap dumps hay raw logs. Nếu bug chỉ xảy ra khi có file generated, tạo file này bằng script/sample task deterministic và giải thích input thay vì commit ngẫu nhiên cache blob.

### 23.2. Một README có giá trị hơn archive lớn không hướng dẫn

Trong root MRE, viết:

~~~markdown
# Minimal Gradle reproducer

Requirements:
- JDK 17 available
- Compatible Gradle Wrapper included

Steps:
1. Run ./gradlew test -PreproFail=false --console=plain
2. Expect BUILD SUCCESSFUL
3. Run ./gradlew test -PreproFail=true --console=plain
4. Expect :test FAILED with DEMO_EXPECTED_FAILURE

Actual environment:
- Fill using sanitized ./gradlew --version output

No private data, credentials or external services required.
~~~

Trên Windows dùng **.\gradlew.bat**. Trong báo bug thật, thay intentional test failure bằng lỗi gốc đã được tối thiểu hóa.

## 24. Kiểm tra lỗi ở Plugin/Gradle build logic

Nếu lỗi xuất hiện ngay khi apply plugin:

- Giữ đúng plugin ID và version.
- Giữ pluginManagement repositories tối thiểu nếu cần.
- Nếu là binary plugin trong buildSrc/included build, giữ source implementation nhỏ nhất.
- Nếu là convention plugin, giữ file script/plugin minimal, không thay nó bằng plugin khác làm thay đổi classpath.
- Chạy **./gradlew help --stacktrace** để tái hiện configuration phase.
- So sánh cùng Wrapper với last-known-good plugin version.
- Kiểm tra Gradle compatibility matrix và API deprecations.
- Nếu báo bug Gradle core, thử tái hiện mà không có community plugins; nếu không thể, ghi rõ dependency vào plugin.

### 24.1. Một plugin version bump có thể là regression

Thử A/B:

~~~text
A: plugin version X -> pass
B: plugin version Y -> fail
Everything else: same
~~~

Đây là mô hình thí nghiệm, không phải số phiên bản thực tế. Đừng tự kết luận lỗi do Gradle core khi chỉ có community plugin version thay đổi.

### 24.2. Không tắt validation để làm build pass

Nếu Gradle báo task property thiếu annotation hoặc configuration-cache violation, hãy giữ warning/error chính xác và model inputs/outputs đúng. Không dùng **doNotTrackState** hoặc cấu hình warn mode như “giải pháp” nếu chưa hiểu tác động correctness.

## 25. Lỗi chỉ trên một hệ điều hành

### 25.1. Case sensitivity

Windows/macOS có thể case-insensitive tùy filesystem, Linux thường case-sensitive. Nếu source import **Demo.App** nhưng file là **demo/App.java**, vấn đề có thể chỉ thấy ở CI Linux. Reproducer phải giữ tên path và package đúng, đồng thời ghi filesystem behavior.

### 25.2. Executable permission

Trên Linux/macOS:

~~~bash
chmod +x gradlew
./gradlew --version
~~~

Nếu repo đã commit permission sai, sửa executable bit là một thay đổi có chủ đích; ghi nó trong bug report. Trên Windows, dùng **gradlew.bat**, không ép chmod.

### 25.3. Paths, quoting và encoding

- Quote đường dẫn có spaces.
- Đừng hardcode **C:\Users\...** vào cross-platform build.
- Gradle **file(...)** và **layout.projectDirectory** tốt hơn thao tác string path thủ công.
- Java text files dùng UTF-8.
- Test không được mặc định line ending LF/CRLF trừ khi normalize.
- Nếu issue chỉ xảy ra với Unicode filenames hoặc path có dấu, giữ **synthetic Unicode fixture** nhưng không dùng tên người dùng thật.

## 26. Lỗi bị che bởi Task cache/up-to-date

Một bug report về custom task:

~~~text
Expected: output thay đổi khi input đổi
Actual: task UP-TO-DATE và output cũ
~~~

Cần giữ:

- Task type/custom action.
- @Input/@InputFile/@OutputFile annotations hoặc TaskInputs DSL.
- Những files/scalar values ảnh hưởng output.
- Hai invocation với input A → input B.
- Log --info của task decision.
- Contents hoặc checksums của output (không chứa secret).
- Gradle Wrapper version.

Đừng chỉ chạy **--rerun-tasks** trong MRE vì nó có thể làm bug biến mất. Gửi cả command bình thường và command forced execution để chứng minh yếu tố khác biệt.

### 26.1. Khi task được FROM-CACHE

FROM-CACHE nghĩa là outputs được khôi phục từ build cache, không có TaskAction. Nếu bug chỉ xuất hiện khi cache hit, giữ **--build-cache** và cách tạo cache entry an toàn; nếu không, người nhận sẽ không thấy lỗi.

### 26.2. Khi task không có source

Một Test task **NO-SOURCE** không chứng minh tests pass. Nếu người dùng báo test runner không tìm thấy test, giữ cấu hình sourceSets/Test task và test class nhỏ nhất.

## 27. Flaky failure khác deterministic reproducer

Một lỗi xảy ra một lần trên 100 runs cần nhiều dữ kiện hơn một failure luôn xuất hiện.

Ghi:

- Số lần thử và số lần fail.
- Seed/randomized order nếu có.
- maxParallelForks/forkEvery/Gradle max-workers.
- CI resource limits, timezone, locale.
- Shared database/port/temp directories.
- Timestamp (theo giờ UTC) của lần fail, không cần mọi user metadata.
- Phần log liên quan tới failure signature.
- Test source/fixtures có thể tái tạo.

Không viết “reproduces 100%” nếu mới chạy hai lần.

### 27.1. Không ép thành deterministic giả

Nếu đổi testForks=1 làm race biến mất, đó là dữ kiện. Không được gọi “fixed” nếu production vẫn chạy testForks=4. Với flaky bugs, smallest reproducer có thể cần hai tasks đồng thời hoặc một loop chạy nhiều lần.

### 27.2. Mô tả xác suất

Ví dụ minh họa:

~~~text
Runs: 30
Failures: 6
Observed failure rate: 20%
Environment: Linux x64, 4 workers
Signature: resource already in use
~~~

Đây là số **giả định**, không phải kết quả chạy lab.

## 28. Cách gửi báo lỗi trong một issue/ticket

Một template thực tế:

~~~markdown
# Gradle issue: [mô tả ngắn symptom]

## Summary
Một câu về lỗi và điều kiện xuất hiện.

## Environment
- Gradle Wrapper: [số cụ thể]
- Gradle JVM: [vendor/version]
- Java toolchain: [version]
- OS/architecture: [đủ để tái hiện]
- IDE/version: [chỉ nếu liên quan]
- Plugin/dependency versions: [liên quan]

## Reproduction
Link/source của MRE đã sanitized.
1. Chạy ...
2. Chạy ...
3. Quan sát ...

## Expected
Mô tả kết quả mong đợi.

## Actual
Task outcome, exception class/message và failure signature.

## Minimal log excerpt
Chỉ các dòng cần thiết, giữ task path và root cause.

## Isolation attempts
- With / without IDE
- With / without configuration cache
- Other one-variable tests (nếu đã thực hiện)

## Frequency
N lần thử, M lần fail.

## Privacy and attachments
Không có secret/PII; đã kiểm tra các file đính kèm.
~~~

Đây là **mẫu tài liệu để sao chép**, không phải yêu cầu thêm file vào repo của người dùng. Thông tin trong dấu ngoặc vuông cần điền bằng dữ liệu đã được phép chia sẻ, và không nên để placeholder trong issue thực.

### 28.1. Tiêu đề issue tốt

Không nên: **Gradle broken**.

Tốt hơn: **Gradle Test task fails during JUnit Platform execution on JDK 17 when X is enabled**.

Tốt hơn nữa nếu xác định chắc: **Custom Test task loses JVM system property when configuration cache is enabled**. Chỉ mô tả nguyên nhân như sự thật khi đã chứng minh qua MRE; nếu mới nghi ngờ, dùng “appears to” hoặc nêu symptom trước.

### 28.2. Expected và Actual tách riêng

Expected không nên là “build phải thành công” nếu task trong lab được thiết kế để fail. Với bug report thật, hãy mô tả contract rõ ràng: “test task được truyền systemProperty reprodFlag=true, test JVM đọc được giá trị” hoặc “compileJava phải tái compile khi input file đổi”.

## 29. Tối ưu thông tin: lỗi gì thì giữ artifact ấy

| Loại lỗi | Artifact nên gửi | Không cần mặc định |
| --- | --- | --- |
| Compiler | Java source nhỏ, build.gradle, compiler diagnostic | Full JUnit HTML |
| JUnit failure | One test class, test config, failure XML excerpt | Full test suite archive |
| Dependency resolution | Coordinates, repo types/order, resolution cause | Cache directories chứa mọi JAR |
| IDE sync | Sanitized IDE version/settings + sync error + CLI comparison | Project-wide screenshot |
| Configuration cache | Relevant problems report + minimal plugin/task logic | Toàn .gradle/configuration-cache |
| Daemon crash | Tail của daemon log + JDK/memory limits | Full Gradle User Home |
| UP-TO-DATE wrong | Two-run sequence, declared inputs/outputs, --info | --rerun-tasks-only log |
| Performance regression | Same workload/version, profile/timings, repeat count | Một run bất kỳ |
| Build Scan failure | Scan link nếu approved, relevant error sections | Public scan của private repo |
| CI-only failure | Workflow task command, runner/JDK/OS, sanitized failure | Secrets, full env dump |

Mức thu thập phải phù hợp với lỗi, không đính kèm mọi thứ chỉ vì “có thể hữu ích”.

## 30. Những lỗi thường gặp khi làm MRE

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ gửi ảnh BUILD FAILED | Thiếu command/root cause | Gửi Gradle failure report + lệnh |
| Không ghi Wrapper version | Người khác chạy Gradle khác | Gửi Wrapper và --version |
| Lẫn Project SDK và Gradle JVM | Sai kết luận JDK | Ghi từng JVM cụ thể |
| Gửi log --debug toàn bộ | Nhiễu/rủi ro dữ liệu | Bắt đầu --stacktrace/--info |
| Redact quá nhiều | Không đọc được root cause | Marker nhất quán, giữ category |
| Không redact private URL | Rò server/token | Sanitize trước khi chia sẻ |
| Bỏ mất plugin gây lỗi | Reproducer hết fail | Rút gọn từng bước, giữ signature |
| Chỉ chạy khi đã có build/ | Hidden workspace state | Thử fresh checkout |
| Sao chép ~/.gradle vào archive | Cache/secrets/phình to | Chỉ gửi source+Wrapper |
| Đổi 5 flags cùng lúc | Không biết nguyên nhân | A/B một biến mỗi lần |
| Dùng --refresh-dependencies mặc định | Thay network behavior | Chỉ dùng cho resolution issue |
| Dùng --rerun-tasks khi bug up-to-date | Che bug | Giữ lệnh gốc trước |
| Dùng --offline trên cache trống | Tạo lỗi khác | Ghi cache state |
| Chỉ chạy từ IDE | Không biết lỗi Gradle/IDE | Thử Wrapper CLI |
| Tắt parallel để “fix” race | Che race thực | Giữ original concurrency trong MRE |
| Không xác nhận test count | NO-SOURCE/SKIPPED bị gọi pass | Xem JUnit XML/results |
| Không giữ exit code khi tee/log | CI xanh giả | Capture status rồi exit đúng |
| Chọn unrelated stack frames | Không tìm thấy cause | Trích cause chain |
| Gửi toàn JUnit report có PII | Rò dữ liệu thử nghiệm | Synthetic fixtures, sanitize |
| Scan publish không phê duyệt | Có thể gửi nội bộ ra dịch vụ | Xin approval hoặc dùng logs local |
| Xóa logs gốc khi incident | Mất evidence | Quarantine theo runbook |
| Không ghi frequency của flaky bug | Người nhận không tái hiện | N trials/M fails |
| Dùng URL issue MRE cần token thật | Không chạy độc lập | Mock/synthetic dependency |
| Không chạy lại MRE sau khi rút gọn | Bug có thể đã mất | Re-run mỗi lần và khi checkout sạch |
| Đưa lệnh shell không tương thích OS | Người nhận không chạy | Ghi Bash/PowerShell riêng |
| Gửi link chỉ người tạo truy cập được | Maintainer không mở được | Kênh/share permissions phù hợp |

## 31. Bài tập thực hành

### Bài 1 — Reproducer cơ bản

Tạo đầy đủ bốn source/config files của lab; dùng Java 17 và Gradle Wrapper. Chạy pass baseline, rồi bật **-PreproFail=true**. Ghi task name, test method, failure marker và exit code.

### Bài 2 — Giảm log

Chạy với --console=plain, --stacktrace rồi --info. Chọn đoạn ngắn nhất đủ chứng minh test marker và task failure. Nêu vì sao --debug chưa cần thiết.

### Bài 3 — So IDE/CLI

Import lab bằng IDE đang dùng. Chạy :test bằng Gradle task, sau đó chạy JUnit native runner. Kiểm tra **repro.fail** có được truyền tới test JVM không; giải thích chỗ khác biệt nếu có.

### Bài 4 — Đổi Gradle JVM

Ghi --version của Wrapper và Java toolchain. Nếu IDE dùng JDK khác, sửa Gradle JVM cho đồng nhất rồi lặp lại. Không thay Java source trong cùng lần.

### Bài 5 — Đóng gói MRE

Tạo một folder copy chỉ gồm settings.gradle, build.gradle, src/**, Wrapper scripts/JAR/properties. Chạy lại từ đường dẫn mới, không có build/ hoặc .gradle.

### Bài 6 — Test filter

Dùng **--tests** để chỉ chạy intentionalFailureOnlyWhenRequested. Kiểm tra test fail vẫn có cùng marker.

### Bài 7 — Configuration cache A/B

Chạy cùng lệnh với --configuration-cache và --no-configuration-cache. Ghi outputs thật, không kết luận configuration cache lỗi nếu cả hai đều fail do test được thiết kế fail.

### Bài 8 — Cache behavior

Thử --no-build-cache và --rerun-tasks trong lab. Phân biệt test failure cố ý với task outcome và caching; đừng dùng nó để che một incremental build bug ngoài lab.

### Bài 9 — Dependency error khác test error

Trong branch thử nghiệm, đổi JUnit version thành một coordinate không tồn tại. Quan sát lỗi chuyển từ **:test FAILED** sang **dependency resolution FAILED**. Khôi phục dependency thật và ghi lại sự khác nhau.

### Bài 10 — Redaction

Lấy một log giả chứa username, fake token và internal hostname. Làm bản sanitized giữ nguyên HTTP status/task path/cause mà không tiết lộ giá trị.

### Bài 11 — PowerShell capture

Chạy intentional failure qua .\gradlew.bat, redirect *> repro.log, lấy $LASTEXITCODE và thoát cùng code. Vì sao không dùng lệnh luôn trả 0?

### Bài 12 — IDE sync

Chạy ./gradlew help thành công nhưng giả định IDE sync fail. Liệt kê ba thông tin IDE cần thu và vì sao không nhất thiết gửi compiler logs.

### Bài 13 — Plugin interaction

Trong một project thử nghiệm an toàn, thêm plugin rồi gỡ từng phần. Mỗi lần ghi failure signature còn hay mất. Khi plugin là điều kiện cần, giữ version trong MRE.

### Bài 14 — Flaky tests

Giả định tests fail 4/20 lần với maxParallelForks=4 nhưng pass 20/20 với forks=1. Viết issue report mô tả concurrency hypothesis mà không khẳng định đã tìm ra root cause.

### Bài 15 — Confidential repro

Thiết kế cách tạo fixture synthetic cho một bug xảy ra khi payload có Unicode và đường dẫn dài mà không đưa dữ liệu khách hàng vào public issue.

### Bài 16 — Daemon failure

Giả định Gradle Daemon bị OOM-killed trên CI. Chọn excerpt, memory/JVM data nào cần và thông tin nào không được đưa vào issue public.

### Bài 17 — Documentation quality

Đưa MRE cho một đồng đội chỉ biết JDK 17 và Wrapper, không nói miệng. Nếu họ không chạy được, ghi rõ thiếu bước nào và cập nhật README.

## 32. Câu hỏi tự kiểm tra

1. MRE là gì và tiêu chí quan trọng nhất của nó?
2. “Tối thiểu” có nghĩa là chỉ giữ một file Java không?
3. Tại sao Gradle Wrapper phải được giữ trong MRE?
4. ./gradlew --version giúp chứng minh gì?
5. Vì sao Java toolchain và Gradle JVM cần ghi riêng?
6. Vì sao ./gradlew help là phép thử giai đoạn configuration hữu ích?
7. CLI help pass nhưng IDE sync fail gợi ý điều gì?
8. --stacktrace và --info trả lời hai loại câu hỏi khác nhau thế nào?
9. Vì sao không bắt đầu bằng --debug?
10. --console=plain có phải một tùy chọn bảo mật không?
11. Khi nào Build Scan có ích nhưng chưa được phép publish?
12. Vì sao không nên gửi toàn ~/.gradle?
13. Vì sao redaction cần nhất quán?
14. Khi giảm một module, điều gì cần kiểm chứng lại?
15. Khi một lỗi chỉ còn xuất hiện với included build, có thể bỏ included build khỏi MRE không?
16. Lệnh nào bật intentional test failure trong lab?
17. Lệnh nào chạy test pass baseline?
18. Lab chứa mấy JUnit test methods?
19. Marker lỗi mong đợi là gì?
20. Có nên báo intentional JUnit failure là Gradle bug không?
21. Lệnh nào chạy Java App độc lập với Gradle?
22. Stdout chính xác của App là gì?
23. --tests giúp cô lập điều gì?
24. --no-build-cache có luôn buộc task action chạy không?
25. --rerun-tasks có thể che lỗi nào?
26. --offline fail trên dependency cache trống có nghĩa gì?
27. --refresh-dependencies có bắt tải mọi JAR lại không?
28. Configuration cache khác task output build cache thế nào?
29. --no-daemon có bảo đảm không tạo single-use daemon không?
30. Khi nào không nên dừng daemons trên máy dùng chung?
31. Vì sao lỗi chỉ CI cần ghi OS/locale/CPU constraints?
32. Một failure 4/20 lần có phải deterministic không?
33. Vì sao dùng synthetic credentials trong MRE?
34. Vì sao một scan link không thể thay phân quyền?
35. Khi secret đã xuất hiện trong log, thao tác nào quan trọng hơn việc chỉ xóa file?
36. Khi log được redirect, làm sao giữ exit code chính xác?
37. Những mục quan trọng nhất của issue report là gì?
38. Một task NO-SOURCE có chứng minh test pass không?
39. Vì sao thay nhiều flags cùng lúc làm hỏng thí nghiệm?
40. Thế nào là một reproduction đủ tốt để maintainer xử lý?

**Đáp án gợi ý:** (1) ví dụ nhỏ nhất còn tái hiện lỗi; (2) không, giữ điều kiện gây lỗi; (3) cố định Gradle distribution; (4) Gradle runtime/JVM/OS; (5) có thể khác nhau; (6) cô lập config; (7) IDE/Tooling API/import; (8) cause chain so với execution diagnostics; (9) nhiễu/rủi ro lộ secret; (10) không; (11) khi server/policy chưa duyệt; (12) chứa caches/logs/credentials; (13) bảo toàn cấu trúc; (14) cùng failure signature; (15) không nếu nó là điều kiện cần; (16) -PreproFail=true; (17) ./gradlew test -PreproFail=false; (18) hai; (19) DEMO_EXPECTED_FAILURE; (20) không; (21) javac --release 17, java -cp; (22) REPRO_OK:17; (23) một class/method; (24) không, vẫn có UP-TO-DATE; (25) incremental/up-to-date; (26) artifact chưa có, bình thường; (27) không; (28) reuse config so với outputs; (29) không; (30) khi ảnh hưởng builds khác; (31) môi trường khác; (32) không; (33) không rò credential thật; (34) cần access control; (35) revoke/rotate; (36) lấy status và exit cùng code; (37) command, environment, expected, actual, MRE, log excerpt; (38) không; (39) không cô lập nguyên nhân; (40) người khác chạy từ checkout sạch và thấy cùng lỗi.

## 33. Checklist trước khi mở issue

- [ ] Ghi rõ chủ đề: IDE sync, compiler, dependency, test, daemon, cache hay configuration.
- [ ] Có lệnh chính xác sử dụng Gradle Wrapper, không chỉ bản Gradle global.
- [ ] Có expected và actual phân biệt rõ.
- [ ] Có failure signature tái hiện với task/class/method phù hợp.
- [ ] Có số lần tái hiện/tần suất nếu flaky.
- [ ] MRE thật sự nhỏ nhưng không xóa điều kiện gây lỗi.
- [ ] Reproducer chạy từ fresh checkout/folder không có local state ẩn.
- [ ] Có settings.gradle, build.gradle, source/test và Wrapper tối thiểu.
- [ ] Không chứa production credentials, source bí mật hoặc customer PII trái policy.
- [ ] Có Gradle Wrapper version và JVM Gradle runtime.
- [ ] Có Java toolchain version khi có Java compilation/test.
- [ ] Có OS/architecture và IDE version nếu cần.
- [ ] Phân biệt Gradle CLI task với IDE sync/IDE-native runner.
- [ ] Đã thử ./gradlew help để phân loại configuration issue khi phù hợp.
- [ ] Đã đọc failure report trước khi tăng logging.
- [ ] --stacktrace/--info chỉ được dùng khi đem lại chứng cứ cần thiết.
- [ ] Không bật --debug hoặc --scan thiếu approval.
- [ ] Không gửi full environment dumps/Gradle User Home.
- [ ] Logs đã review/redact, giữ root cause và task path.
- [ ] JUnit XML/HTML được kiểm tra nếu đính kèm.
- [ ] Không xóa evidence gốc khi cần incident/forensics.
- [ ] Không áp nhiều flags cùng lúc làm méo điều kiện tái hiện.
- [ ] Những thử nghiệm cache/offline/daemon được ghi như biến số.
- [ ] Không dùng --rerun-tasks để che vấn đề UP-TO-DATE.
- [ ] Không dùng clean/xóa cache làm “chứng minh đã fixed”.
- [ ] Đã kiểm tra test count và failures, tránh nhầm NO-SOURCE.
- [ ] Có một command người nhận có thể copy chạy trực tiếp.
- [ ] Có README ngắn nêu prerequisites, steps và output signature.
- [ ] Có đường chia sẻ repo/log/scan phù hợp với data classification.
- [ ] Đã ghi những thử nghiệm loại trừ nhưng không kết luận quá mức.
- [ ] Có liên hệ owner/maintainer của component đúng loại lỗi.

## 34. Tài liệu tham khảo chính thức

- [Gradle — Troubleshooting Builds](https://docs.gradle.org/current/userguide/troubleshooting.html)
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Gradle — Logging and Output](https://docs.gradle.org/current/userguide/logging.html)
- [Gradle — Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [Gradle — JVM Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — Dependency Resolution](https://docs.gradle.org/current/userguide/dependency_resolution.html)
- [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle — Enable Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_enabling.html)
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle — Troubleshooting Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html)
- [Gradle — Build Scans](https://docs.gradle.org/current/userguide/build_scans.html)
- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html)
- [Gradle — Problems API](https://docs.gradle.org/current/userguide/reporting_problems.html)

**Kết luận:** Một báo lỗi Gradle có giá trị không đo bằng số lượng dòng log. Nó cần **một reproducer nhỏ nhất còn lỗi**, **lệnh chạy chính xác**, **failure signature đủ để tìm nguyên nhân**, **Gradle/JDK/IDE environment liên quan**, **bản trích log đã kiểm tra dữ liệu nhạy cảm** và **những phép thử cô lập một biến**. Hãy phân loại lỗi trước, thử bằng Wrapper CLI, nâng logging theo nhu cầu, kiểm chứng lại sau mỗi bước rút gọn và giữ exit status thật. Khi maintainer có thể chạy reproducer từ checkout sạch và thấy đúng lỗi mà không cần secret hay lịch sử máy của bạn, báo lỗi đã đạt mục tiêu.
