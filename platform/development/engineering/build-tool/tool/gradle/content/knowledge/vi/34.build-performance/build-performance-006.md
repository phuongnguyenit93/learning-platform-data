# Dùng --profile và Build Scan với cân nhắc dữ liệu được chia sẻ

## 1. Bài toán: Gradle build chậm nhưng chưa biết chậm ở đâu

Một build Java có thể tiêu thời gian ở Gradle/JVM startup, settings, `buildSrc`, áp dụng plugins, cấu hình hàng trăm projects, giải quyết dependency metadata, tải JAR, compile, chạy test hoặc đóng gói. Dòng `BUILD SUCCESSFUL in ...` chỉ cho biết tổng thời gian một invocation, không cho biết bottleneck.

Gradle cung cấp hai công cụ quan sát quan trọng:

- **`--profile`**: sinh **HTML report local** về các giai đoạn và tasks. Cách mở đầu phù hợp khi chỉ cần phân tích nội bộ, chưa muốn phát tán build metadata.
- **Build Scan** (thường kích hoạt bằng **`--scan`** hoặc plugin **Develocity**): ghi nhận build chi tiết để xem performance, timeline, dependencies, cache outcomes, tests, environment và lỗi. Khi xuất bản, dữ liệu được **truyền đến Build Scan/Develocity server** và người được phép có thể xem qua URL.

**Nguyên tắc quan trọng nhất:** Build Scan hữu ích hơn khi điều tra sâu, nhưng không nên tự publish scan từ code/CI/khách hàng nhạy cảm chỉ để chia sẻ link. Hãy chọn **local-first**, xem dữ liệu nào sắp được chia sẻ, xác định endpoint/quyền xem và chỉ publish khi policy/consent đã đáp ứng.

Sau bài thuộc **Build Tool Gradle → Hiệu năng build**, bạn có thể:

1. Tạo, mở và đọc đúng báo cáo `--profile`.
2. Phân biệt startup, configuration, dependency resolution và task execution; hiểu wall-clock khác tổng durations của tasks chạy song song.
3. Lập benchmark công bằng giữa clean, warm, incremental và cache-enabled builds.
4. Dùng Build Scan để tìm long-running tasks, critical path, configuration bottleneck, cache misses và test failures.
5. Nhận biết các trường thông tin Scan có thể ghi lại: project/task/test names, repository URLs, console logs, stack traces, user home, username/host/IP, Gradle/JDK/OS.
6. Chọn giữa public-link service và private Develocity server; hiểu private URL không đồng nghĩa chỉ owner xem.
7. Dùng `--no-scan`, Develocity publishing policy, capture toggles và obfuscation đúng phạm vi.
8. Biết quy trình phê duyệt, giới hạn người nhận, lưu trữ và phản ứng nếu vô tình chia sẻ dữ liệu nhạy cảm.

Ví dụ dùng **Gradle Groovy DSL**, **Java 17+** và Gradle Wrapper. Những lệnh `--scan` là **tùy chọn, chỉ chạy trên project không nhạy cảm hoặc đã được phép publish**.

## 2. So sánh --profile và Build Scan

| Tiêu chí | Local `--profile` | Build Scan / `--scan` |
| --- | --- | --- |
| Mục tiêu | Tổng quan timing và giai đoạn build. | Phân tích sâu, phối hợp điều tra qua URL. |
| Lệnh | `./gradlew build --profile` | `./gradlew build --scan` |
| Output | HTML trong `build/reports/profile` của root project. | Metadata/scan được publish tới service rồi có URL. |
| Tự upload? | **Không do riêng flag --profile**. | **Có** khi scan publication thành công. |
| Task-level detail | Có breakdown cơ bản. | Có timeline, dependencies, cache outcomes, test và môi trường tùy plugin/version. |
| Xem offline | HTML local có thể mở offline. | Cần truy cập server chứa scan. |
| Phạm vi chia sẻ | Chỉ local tới khi user/CI upload/copy HTML. | Public scan link hoặc quyền trên private server. |
| Cần consent? | Không có consent Build Scan service chỉ vì profile local. | Public service có thể yêu cầu chấp thuận Terms of Service. |
| Dữ liệu nhạy cảm | Tên project, tasks/scripts và timing vẫn có thể lộ khi chia sẻ HTML. | Console/test output, failure metadata, host/user/IP, dependencies và nhiều thông tin khác. |
| Hạn chế | Không phải method-level CPU/heap profiler. | Không phải security sandbox; không tự tối ưu build; publication có tác động network. |
| Khi nên ưu tiên | Bước đầu, dự án chưa có approval. | Cần breakdown sâu và đã review data/server/access. |

**Ngoại lệ cần nhớ:** nếu project/CI **đã cấu hình Develocity tự publish mọi build**, thì ngay cả lệnh chỉ có `--profile` vẫn có thể kèm scan publication từ cấu hình đó. Vì vậy phải kiểm tra settings/CI integration; đừng tuyên bố mọi invocation không có `--scan` đều an toàn tuyệt đối.

## 3. Build lifecycle và cách đọc thời gian

Đường đi đơn giản của một Gradle invocation:

```text
./gradlew <tasks>
    |
    +-- Startup: JVM, daemon, init scripts, wrapper
    |
    +-- Initialization: settings, projects, buildSrc/build logic
    |
    +-- Configuration: plugins, scripts, tasks, task graph
    |
    +-- Execution: resolving classpaths, compile/test/package
    |
    +-- Local HTML profile, hoặc published Build Scan nếu được phép
```

Đây là sơ đồ giải thích, không phải thứ tự bất biến: dependency resolution có thể xảy ra ngay lúc configuration hoặc trong execution, và nhiều tasks chạy song song.

### 3.1. Wall-clock không bằng tổng task durations

Nếu `:core:compileJava` chạy 9 giây, `:app:compileJava` 8 giây và `:api:test` 14 giây, bạn **không thể** kết luận build mất 31 giây. Task executions có thể chồng lấp; startup/configuration vẫn tiêu thời gian ngoài task timings.

Một task dài chưa chắc nằm trên **critical path** làm build kết thúc muộn. Build Scan timeline hữu ích để xem dependency relationships, overlaps và khoảng chờ. Local profile giúp nhận diện vùng lớn trước.

### 3.2. Outcomes cho biết có thật sự làm việc hay không

| Task outcome | Ý nghĩa |
| --- | --- |
| `SUCCESS` | Task đã chạy thành công. |
| `UP-TO-DATE` | Output local còn và input/output snapshots vẫn hợp lệ; không phải build-cache restoration. |
| `FROM-CACHE` | Output được khôi phục từ local/remote build cache. |
| `NO-SOURCE` | Source processing task không có source. |
| `SKIPPED` | Bỏ qua theo điều kiện/disabled/skip reason. |
| `FAILED` | Task không hoàn tất thành công. |

Chạy `build` lần đầu với nhiều tasks `SUCCESS` không cùng workload hiệu dụng với lần sau có nhiều `UP-TO-DATE`. Trước khi so thời gian phải ghi rõ cache mode và task outcomes.

## 4. Tạo HTML profile report local

### 4.1. Lệnh chuẩn

Linux/macOS:

```bash
./gradlew help --profile --console=plain
./gradlew build --profile --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat help --profile --console=plain
.\gradlew.bat build --profile --console=plain
```

`help` thường có rất ít task execution và giúp quan sát startup/configuration. `build` thực thi các tasks phù hợp với plugins của project. Hai lệnh **không đo cùng workload**; không so chúng như một benchmark trước/sau.

Đường dẫn mặc định:

```text
<root-project>/
└── build/
    └── reports/
        └── profile/
            ├── profile-<timestamp>.html
            └── ...
```

`profile-<timestamp>.html` là **mẫu tên có timestamp**; không phải tên file literal. Mỗi invocation có thể tạo report mới. Đừng mở nhầm báo cáo cũ và kết luận optimization đã thành công.

### 4.2. Tìm report vừa sinh

Linux/macOS:

```bash
ls -lt build/reports/profile/
```

Windows PowerShell:

```powershell
Get-ChildItem .\build\reports\profile -Filter '*.html' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 5 Name, LastWriteTime
```

Đây là lệnh **đọc file local**, không tải dữ liệu lên cloud. Có thể mở HTML bằng trình duyệt trên máy. Nhưng nếu tự động upload toàn bộ `build/reports/**` lên CI artifacts hoặc public issue, báo cáo local cũng có thể trở thành dữ liệu chia sẻ.

### 4.3. Những mục thường có trong report

| Khu vực | Quan sát | Hướng tìm nguyên nhân |
| --- | --- | --- |
| **Startup** | JVM startup, Gradle Daemon, init scripts, Wrapper bootstrap. | Cold daemon, JDK, init script, network tải distribution. |
| **Settings and buildSrc** | Settings processing và build logic từ buildSrc. | Script I/O, buildSrc recompilation, plugin classpath. |
| **Loading Projects** | Khởi tạo project hierarchy. | Có quá nhiều modules không cần thiết? |
| **Configuring Projects** | Đọc build scripts/plugins, cấu hình tasks. | Eager task realization, cross-project configuration, callbacks. |
| **Dependency Resolution** | Các bước resolve metadata/artifacts (tùy version/report). | Network/proxy/repos, dynamic versions, credentials, mirror. |
| **Task Execution** | Tasks thực thi và timings. | Compile/test/codegen nặng, không up-to-date, cache misses. |

Bố cục cụ thể khác giữa Gradle versions. Không đòi profile HTML có đúng các tabs chi tiết như Build Scan.

### 4.4. Startup hoặc configuration cao

Nếu `./gradlew help --profile` đã chậm trong khi không compile code:

1. Kiểm tra `./gradlew --version` và JVM Daemon có bị khởi tạo mới mỗi lần không.
2. Kiểm tra `settings.gradle`, `buildSrc` hoặc included `build-logic` có chạy I/O/network/compilation không.
3. Cân nhắc lazy task APIs `tasks.register`, `tasks.named`, `configureEach` thay cho eager `create` hoặc `tasks.all`.
4. Xem plugins nào áp dụng trên quá nhiều subprojects.
5. Thử Configuration Cache nếu build logic tương thích, nhưng kiểm tra reports của Gradle thay vì bật bằng mọi giá.
6. Nếu cần CPU profiling trong plugin code, dùng Gradle Profiler/JFR/async-profiler chứ không suy luận từ thời gian tổng.

### 4.5. Task Execution cao

Nếu `:app:test` chiếm nhiều thời gian:

- Task có chạy thật hay đã UP-TO-DATE/FROM-CACHE?
- Có integration test phụ thuộc network/external services không?
- JVM forks/maxParallelForks đang phù hợp CPU/RAM chưa?
- Annotation processors, compilation options, JDK hoặc GC có ảnh hưởng không?
- Có task nào nối trước test làm critical path dài hơn không?
- Tăng `org.gradle.workers.max` có gây contention thay vì tăng tốc không?

Đừng tối ưu Java source khi bottleneck ở repository DNS hoặc Gradle plugin configuration.

## 5. Lab Java 17+ chạy được mà không cần Build Scan

Để luyện `--profile` an toàn, tạo một project Java không phụ thuộc thư viện Maven bên ngoài.

### 5.1. Cấu trúc

```text
profile-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/main/java/example/ProfileDemo.java
```

Cần JDK 17+ và Gradle Wrapper compatible. Wrapper files được tạo qua `gradle wrapper` hoặc `gradle init` bằng Gradle cài sẵn; chỉ tạo build.gradle không tự sinh Wrapper.

### 5.2. settings.gradle

```groovy
rootProject.name = 'profile-lab'
```

### 5.3. build.gradle hoàn chỉnh

```groovy
plugins {
    id 'application'
}

group = 'example'
version = '1.0.0'

application {
    mainClass = 'example.ProfileDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

`application` áp Java plugin và tạo tasks `compileJava`, `run`, `jar`, `build`. `application.mainClass` là entry point cho `run`; không khẳng định plain JAR đã có manifest Main-Class. `options.release=17` biên dịch nhắm Java 17 nhưng **không tự tải JDK**. Không cần `repositories` vì source dùng Java standard library.

### 5.4. src/main/java/example/ProfileDemo.java

```java
package example;

public final class ProfileDemo {
    private ProfileDemo() {
    }

    public static void main(String[] args) {
        int end = args.length == 0
                ? 100
                : Integer.parseInt(args[0]);

        if (end < 1) {
            throw new IllegalArgumentException(
                    "end must be positive");
        }

        long sum = 0;
        for (int i = 1; i <= end; i++) {
            sum += i;
        }
        System.out.println("sum(1.." + end + ")=" + sum);
    }
}
```

Mã Java 17+ hợp lệ. `sum = 100 * 101 / 2 = 5050` khi end=100.

### 5.5. Build, chạy và đọc stdout

Linux/macOS:

```bash
./gradlew clean run --args="100" --profile --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat clean run --args="100" --profile --console=plain
```

**Stdout riêng của phương thức Java main:**

```text
sum(1..100)=5050
```

Đây không phải toàn bộ Gradle console transcript: Gradle còn in task logs và đường dẫn profile report. Không bịa thông báo `BUILD SUCCESSFUL in Ns` cố định.

Không truyền argument:

```bash
./gradlew -q run
```

Stdout Java:

```text
sum(1..100)=5050
```

Truyền end=10:

```bash
./gradlew -q run --args="10"
```

Stdout Java:

```text
sum(1..10)=55
```

### 5.6. So sánh cold/warm tasks

```bash
./gradlew clean build --profile --console=plain
./gradlew build --profile --console=plain
./gradlew build --profile --console=plain
```

Lệnh đầu làm project outputs bị dọn rồi thực hiện build; hai lệnh sau có thể dùng up-to-date checks và caches. Đây là **các tình huống khác nhau theo trạng thái outputs**, không chứng minh code sau sửa nhanh hơn. Trên máy đã có build cache warm, ngay cả clean build cũng có thể `FROM-CACHE` thay vì execute, tùy tasks.

Để xem startup/configuration nhiều hơn:

```bash
./gradlew help --profile --console=plain
./gradlew help --profile --console=plain
```

Lần đầu có thể chậm hơn do daemon/JVM/caches cold. Dùng cùng Wrapper, JDK và môi trường rồi mới giải thích kết quả.

### 5.7. Thay source để xem compilation

Sửa có chủ đích `ProfileDemo.java`, sau đó:

```bash
./gradlew build --profile --console=plain
```

Task `compileJava` có thể chạy lại vì source input đổi, trong khi configuration/time của tasks khác vẫn có thể tương tự. Không so sánh hai lần chạy mà một lần có `compileJava SUCCESS`, lần kia `UP-TO-DATE` rồi gọi đó là optimization compiler.

## 6. Benchmark đúng trước khi tối ưu

Một lần profile chỉ là **một mẫu**, không phải benchmark khoa học. Lập bảng thông tin tối thiểu:

| Trường | Nên ghi |
| --- | --- |
| Workload | Task request chính xác: `:app:test`, `build`, `help`. |
| Source | Git commit/branch và relevant build scripts. |
| Tools | Gradle Wrapper version, JDK vendor/version, OS. |
| Hardware | CPU/RAM class, SSD/HDD, CI runner type. |
| Daemon/cache | Cold/warm daemon, dependency cache, build cache, configuration cache. |
| Parallelism | `org.gradle.parallel`, worker count, test forks. |
| Network | Repository mirror/proxy/offline state. |
| Measurements | Wall-clock, phase durations, task outcomes, N runs, median/spread. |
| Data handling | Local HTML vs published scan, approved server/access. |

### 6.1. Phương pháp thực hành

1. Pin Wrapper, JDK và commit.
2. Định nghĩa benchmark scenario: **clean**, **warm** hoặc **incremental after source change**.
3. Warm Gradle Daemon/caches nếu định đo warm build; ngược lại ghi rõ cold state.
4. Chạy nhiều samples, bỏ warm-up nếu phù hợp, so median thay vì số nhanh nhất.
5. Đọc tasks `SUCCESS`/`UP-TO-DATE`/`FROM-CACHE`; đừng so những execution states khác nhau như cùng workload.
6. Thay **một yếu tố** (plugin config, test suite, repository, JVM args) và đo lại.
7. Kiểm tra correctness: tests/build outputs còn PASS.
8. Khi cần scenarios và nhiều runs tự động, dùng **Gradle Profiler**.

**Sai lệch phổ biến:** so build vừa tải Gradle Wrapper/dependencies với build đã warm, so một lần `clean` với lần khác không clean, hoặc dùng CPU-saturated CI runner cho một mẫu. Không đổ mọi chênh lệch cho Gradle.

## 7. Build Scan: khả năng quan sát chi tiết

Build Scan là bản ghi build trên dịch vụ Gradle/Develocity. Khi được publish và người xem có quyền:

- **Performance:** breakdown startup/configuration/dependency resolution/task execution.
- **Task timeline:** tasks chạy song song, bottlenecks, critical path, waiting.
- **Task details:** task outcomes, cache operations/keys và task dependency relationships.
- **Dependencies:** dependency modules/versions, origin repositories, downloads, resolution errors.
- **Tests:** test method/class names, duration, failures và console/test outputs theo capture policy.
- **Environment:** Gradle version, Java/JVM, OS, daemon, hardware/resources tùy plugin.
- **Console:** build logs, warnings, failures và stack traces.
- **Configuration:** plugin/script application costs, configuration cache diagnostics (tùy phiên bản/plugin).

Không nhầm Build Scan với một file HTML nằm trong root project. **Khi publish**, scan data rời build runner và đến server; URL chỉ có nghĩa sau khi publication thành công.

### 7.1. Khi nào Build Scan bổ sung được câu trả lời?

Nếu `--profile` cho thấy task execution lớn mà không biết task nào chặn others, Build Scan timeline/critical path giúp xem overlap và task dependencies. Nếu configuration phase lớn, scan có thể chi tiết hóa plugin/scripts được áp dụng. Nếu CI chậm hơn local, so Gradle/JDK, resource usage, dependency download, test duration và cache outcomes.

Build Scan **không tự sửa hiệu năng**, không thay CPU profiler method-level và không thay kiểm thử build correctness. Nếu cần flame graph, dùng JFR/async-profiler/Gradle Profiler với quyền phù hợp.

## 8. Dùng --scan: publication là hành động chia sẻ

Chỉ chạy trên **public demo/approved build**:

```bash
./gradlew build --scan
```

Windows:

```powershell
.\gradlew.bat build --scan
```

Gradle có thể yêu cầu chấp thuận Terms of Service của dịch vụ. Sau **khi xuất bản thành công**, console cho URL dạng:

```text
Publishing Build Scan...
https://gradle.com/s/<scan-id>
```

Đây chỉ là **mẫu URL**, không phải một scan thật. Không đồng ý điều khoản hoặc publish data nội bộ thay người khác khi chưa có quyền. Gradle 9.x có thể tự áp dụng Develocity plugin khi dùng `--scan` nếu build chưa áp plugin; chi tiết/version tùy Gradle distribution và configuration.

### 8.1. Quy tắc an toàn

- **Đừng** tự publish code/CI chứa customer names, incident descriptions, private repositories hoặc secrets.
- **Đừng** nghĩ scan an toàn tuyệt đối vì URL khó đoán.
- **Đừng** chia sẻ link ở public GitHub issue/PR comment/Slack ngoài tổ chức nếu không được cho phép.
- **Đừng** mặc định capture toggles hoặc obfuscation che tất cả dữ liệu.
- **Đừng** dùng `--quiet` thay cho thiết kế log không rò rỉ.

Nếu không chắc, **không dùng --scan**, dùng `--profile` và xin phê duyệt cho bước chuyên sâu.

### 8.2. Khi chỉ muốn local profile mà build có auto-publishing

Một số project/CI đã apply Develocity plugin với chính sách publish tất cả. Theo Develocity docs, `--no-scan` có thể suppress việc publication cho một invocation:

```bash
./gradlew build --no-scan --profile --console=plain
```

Lệnh này vẫn tạo local profile. Tuy nhiên CI wrapper hoặc automation ngoài Gradle có thể có thêm policy riêng, nên cần xác minh. `--no-scan` **không thu hồi scan đã publish trước đây** và không có nghĩa local report vô hại nếu đem upload ở nơi khác.

## 9. Build Scan có thể thu thập dữ liệu gì?

Theo **Develocity Gradle Plugin 4.5 User Manual, Appendix B: Captured Information**, các nhóm tiêu biểu:

| Nhóm | Dữ liệu có thể có | Rủi ro khi chia sẻ |
| --- | --- | --- |
| Build identifiers | Project names, paths, requested tasks, options. | Codename/khách hàng/kiến trúc nội bộ. |
| Gradle plugins | Plugin IDs, versions, implementation classes/origins. | Công cụ nội bộ hoặc dependency vulnerabilities. |
| Dependencies | Group/name/version, origin repositories, artifact size, resolution errors, download URLs. | Domain private repo, dependency graph. |
| Task metadata | Task paths, outcomes, dependencies, build cache keys, names của input/output properties. | Quy trình build và tên artifacts; không mặc định mọi property **value** đều capture. |
| Tests | Test class/method names, durations, failures, output. | Names/exception payloads có thể chứa dữ liệu nhạy cảm. |
| Console | Build output, compiler diagnostics, deprecation, stack traces. | Snippets của source, tokens, secrets in nhầm. |
| Environment | User home path, username, hostnames, local IPs, OS, JDK/JVM, CPU/RAM. | Định danh máy/người, thông tin mạng. |
| Resources | CPU/memory/disk/network usage, external process names tùy version/config. | Tiết lộ workload hoặc công cụ của runner. |
| Custom enrichment | Tags, custom values, links đến CI/VCS/deploy. | Người cấu hình có thể tự đưa secrets vào scan. |

Tài liệu nói **không thu thập toàn bộ actual source files và output artifacts mặc định** như việc upload nguyên repository. Nhưng **compiler errors, stack traces và test failures có thể làm lộ source snippets hoặc dữ liệu nhạy cảm**. Không được nói “không upload source” đồng nghĩa “không thể lộ nội dung mã”.

Tương tự, **tên các task input/output properties** được capture không đồng nghĩa tất cả **giá trị** của chúng đều bị capture tự động. Nhưng nếu giá trị được in trong log, lỗi, CLI hoặc custom value thì vẫn có thể lộ.

### 9.1. Phản ví dụ: in bí mật vào log

```groovy
// PHẢN VÍ DỤ - không sử dụng trong build thật.
tasks.register('debugApiToken') {
    doLast {
        println System.getenv('API_TOKEN')
    }
}
```

Nếu task này được gọi, output có thể xuất hiện trong console/Build Scan. `--quiet` không phải redaction guarantee; các errors/test logs vẫn có thể bị capture.

Cách đúng: dùng CI secret management, Gradle credential providers và không in token hoặc truyền plaintext secret qua CLI flags như `-Ppassword=...` hay `-Dtoken=...`. Khi cần chẩn đoán, chỉ log trạng thái **có/không**, không log giá trị hoặc hash có thể đối chiếu bí mật.

### 9.2. Test failures có thể lộ dữ liệu dù source không upload

Ví dụ **giả lập**:

```text
Expected customer endpoint: private.api.example.internal
Actual customer endpoint:   staging.api.example.internal
```

Một test failure như vậy có thể tiết lộ môi trường/deployment ngay trong error message. Nếu error thật chứa access token, chỉ tắt `testLogging` **chưa chắc loại bỏ toàn bộ failure metadata**.

## 10. Ai xem được scan sau khi publish?

### 10.1. Public-link Build Scan

Docs Develocity mô tả các scan trên dịch vụ public là **viewable by anyone with its URL**. URL độc nhất/khó đoán, không nhất thiết xuất hiện trong danh sách public, nhưng **người có link có thể xem**. Đây không phải mức bảo vệ tương đương authenticated RBAC chỉ chủ sở hữu.

Nếu URL bị paste vào public bug tracker, CI job logs, PR comment hoặc chat bên ngoài, người đọc ở đó có thể truy cập dữ liệu.

### 10.2. Self-hosted Develocity server

Một tổ chức có thể dùng endpoint Develocity nội bộ với SSO, access controls và retention policy. Nhưng self-hosted **không tự bảo đảm** chỉ owner xem; quyền truy cập tùy cấu hình server. Docs mô tả scans trên Develocity installation có thể xem bởi người truy cập được server, trừ khi server có thêm restrictions.

Trước khi publish, kiểm tra endpoint đúng domain allowlist, HTTPS/certificate, login/SSO/RBAC, anonymous access, audit logs, retention, backup, data residency và quyền người nhận. Không chuyển từ private server lỗi sang public service như một workaround thiếu phê duyệt.

## 11. Xuất bản đến Develocity server đã được duyệt

### 11.1. CLI cho Gradle 9.5+

Tài liệu Gradle 9.5.0+ hỗ trợ publication tới server cụ thể bằng option:

```bash
./gradlew build --develocity-url=https://develocity.example.com
```

Domain **develocity.example.com chỉ minh họa**, không phải server của bạn. Lệnh này có thể **publish scan** và không được chạy nếu chưa được phê duyệt.

Khi dùng Gradle auto-applied Develocity plugin, có thể chọn version compatible:

```bash
./gradlew build \
  --develocity-url=https://develocity.example.com \
  --develocity-plugin-version=4.5.1
```

Theo Gradle documentation, ở cơ chế auto-application với URL, plugin tối thiểu **4.4.0**. Version CLI không ghi đè plugin đã được build settings apply rõ trong mọi trường hợp. Server có thể yêu cầu authentication dù đã có URL.

Windows PowerShell một dòng:

```powershell
.\gradlew.bat build --develocity-url=https://develocity.example.com --develocity-plugin-version=4.5.1
```

Đây là phần **tham khảo cho môi trường được phép publish**, không phải lab bắt buộc.

### 11.2. settings.gradle rõ ràng với Groovy DSL

Một project có server đã được approve có thể khai báo:

```groovy
plugins {
    id 'com.gradle.develocity' version '4.5.1'
}

develocity {
    server = 'https://develocity.example.com'
    buildScan {
        publishing.onlyIf { false }
    }
}

rootProject.name = 'approved-profile-project'
```

Đây là file **settings.gradle độc lập thay thế** cho project phù hợp, không dán đè lên lab `profile-lab` nếu chưa có approval. `publishing.onlyIf { false }` là chính sách **on-demand** theo Develocity docs; user chỉ chủ động thêm `--scan` khi đã được phép, thay vì luôn publish mỗi build.

**Cảnh báo:** một setting trong build script không phải security boundary hoàn toàn nếu users có thể override bằng CLI, CI injection hoặc server policy khác. Nếu tổ chức cần cấm upload, enforce bằng credentials/network/endpoint và governance.

### 11.3. Tắt một phần log capture

Với plugin Develocity 4.5.x đã apply ở settings:

```groovy
develocity {
    buildScan {
        capture {
            buildLogging = false
            testLogging = false
        }
    }
}
```

Đây là **fragment bổ sung** vào cấu hình Develocity đã tồn tại, không cần copy hai blocks khác nhau rồi trông đợi chúng tự merge đúng. Theo docs, tắt test output capture **không xóa mọi test failure**: failure exceptions vẫn được capture. Build metadata, task/dependency names, environment values vẫn có thể còn.

Có thể đặt system properties cho invocation (lệnh **vẫn publish scan**):

```bash
./gradlew build --scan \
  -Dscan.capture-build-logging=false \
  -Dscan.capture-test-logging=false
```

Windows PowerShell:

```powershell
.\gradlew.bat build --scan -Dscan.capture-build-logging=false -Dscan.capture-test-logging=false
```

Đây **không phải công thức sanitization hoàn chỉnh**. Nếu không có approval, không chạy lệnh publish; dùng local `--profile`.

### 11.4. Obfuscate một số identifying fields

Develocity hỗ trợ callbacks cho username, hostnames, IPs và external process names:

```groovy
develocity {
    buildScan {
        obfuscation {
            username { name -> 'redacted-user' }
            hostname { host -> 'redacted-host' }
            ipAddresses { addresses ->
                addresses == null
                    ? []
                    : addresses.collect { address -> '0.0.0.0' }
            }
            externalProcessName { process ->
                'redacted-process'
            }
        }
    }
}
```

Đây là **fragment minh họa** cho plugin hỗ trợ các callbacks đó. Nó **không tự sửa** console logs, stacktraces, repository URLs, custom values, user home paths, test names hoặc project names. Nếu build đã in hostname/secret vào log, callback không xóa dòng log ấy.

### 11.5. Chỉ publish theo điều kiện

Ví dụ **fragment** khi team muốn chỉ publish trên CI được kiểm soát:

```groovy
develocity {
    buildScan {
        publishing.onlyIf {
            System.getenv('APPROVED_SCAN') == 'true'
        }
    }
}
```

`APPROVED_SCAN` là **biến do đội tự đặt**, không phải chứng cứ authorization. Developers có thể tự set biến hoặc dùng `--scan` để publish theo policy của plugin. Access controls, egress policy, credentials và review mới là các lớp an toàn thực chất.

### 11.6. Không commit Terms of Service consent thay cho người khác

Develocity docs có ví dụ `termsOfUseUrl` và `termsOfUseAgree` để auto-publish lên public service; tài liệu cũng cảnh báo **đừng commit sự đồng ý Terms of Service vào repository có người khác build**. Việc chấp thuận cần tuân theo quy trình legal/security của tổ chức và ý chí user, không phải chỉ để CI chạy qua prompt.

## 12. Quy trình privacy review trước khi share một Build Scan

| Câu hỏi | Quyết định cần có |
| --- | --- |
| Source/build có thuộc khách hàng/đơn vị đối tác? | Phân loại theo hợp đồng và company policy. |
| Console/test output có secrets/PII? | Sửa nguồn rò rỉ trước; không phụ thuộc chỉ vào mask. |
| Project/task/test names có codename nội bộ? | Cân nhắc có nên publish hoặc dùng riêng endpoint restricted. |
| Dependencies/repo URLs có nội bộ không? | Check private repository domains, artifact names. |
| Username/hostname/IP/user home có cần che? | Dùng obfuscation phù hợp, kiểm tra các fields khác. |
| Custom tags/links/values có nhạy cảm không? | Tắt hoặc sanitize. |
| Endpoint là public hay self-hosted? | Verify allowlist, HTTPS, auth, RBAC. |
| Ai có thể xem URL? | Public-link: bất kỳ ai giữ URL; private: theo policy thật. |
| Retention/deletion/audit? | Có owner, thời hạn, thủ tục xử lý sự cố. |
| Có approval phù hợp? | Nếu chưa: không publish, dùng `--profile` local. |

**Không nhập một raw token vào câu hỏi nhờ hỗ trợ, không đưa private scan URL lên public ticket**, không dán log có dữ liệu cá nhân để hỏi về performance.

### 12.1. CI có thể auto-publish hoặc auto-share link

Xem `settings.gradle`, init scripts, GitHub Actions/GitLab/Jenkins Gradle integration, injected Develocity plugin và PR-comment automation. Ngay cả khi CLI không có `--scan`, scan vẫn có thể được publish nếu plugin được cấu hình mặc định publish all. Một link in ở CI log có mức quyền xem của chính CI logs; người xem log có thể mở public-link scan.

Trong CI có production credentials, release signing keys hoặc customer data, có thể phải cấm scan publication hoàn toàn hoặc chỉ dùng self-hosted server được phép, với logs/test capture hạn chế. Không nghĩ rằng hai flags tắt capture đã che hết mọi failure metadata.

### 12.2. Nếu lỡ publish scan chứa bí mật

1. Dừng lan truyền link, gỡ link khỏi kênh public có thể sửa.
2. Báo security/incident response owner theo quy trình của tổ chức.
3. Nếu secret/token lộ, revoke/rotate ngay theo policy; không chờ scan bị xóa.
4. Liên hệ Develocity server admin hoặc dịch vụ xuất bản về retention/deletion/visibility có thể hỗ trợ.
5. Rà soát URL đã xuất hiện trong CI logs/PR comments/chat và audit truy cập nếu server hỗ trợ.
6. Sửa source leak: println, exception details, test failure assertions, custom scan values, auth.
7. Chỉ publish lại khi đã được review.

**Đừng giả định xóa URL khỏi một chat đã xóa mọi bản sao dữ liệu**, hay scan từng publish có thể được thu hồi tức thì ở mọi nơi.

## 13. Đọc Build Scan có phương pháp

Khi scan đã được publish tới **approved endpoint**:

### 13.1. Performance overview

Mở Performance: so startup, project configuration, dependency resolution và task execution. Nếu configuration chiếm phần lớn, không cố tinh chỉnh `javac` trước khi tối ưu plugins/build logic.

### 13.2. Timeline và critical path

Xem tasks chồng lấp và dependencies. Task dài nhất có nằm trên critical path không? Có tasks chạy tuần tự vì dependency graph, hay đã tận dụng parallelism? Có annotation processor/codegen tạo blockage? Tổng durations không bằng wall-clock.

### 13.3. Cache

Xem `SUCCESS` / `UP-TO-DATE` / `FROM-CACHE`, lý do tasks rerun, local/remote cache key nếu có. Cache hit không chứng minh build code nhanh hơn; cache correctness/input-output modeling quan trọng hơn chỉ tỷ lệ hit.

### 13.4. Dependency resolution

Nếu network downloads nhiều: kiểm tra Gradle User Home persistence, repository order/content filters, dynamic/changing modules, DNS/proxy/auth, plugin repositories khác project repositories. Không bật build cache để “sửa” một dependency missing artifact.

### 13.5. Tests

Xem test classes/methods dài, retries, fork count, failure types. Nếu Scan chứa customer data trong test outputs thì chỉ phân tích trong kênh có quyền, không xuất URL cho người ngoài.

### 13.6. Configuration

Xem plugin/scripts tốn thời gian, tasks realized quá sớm, `buildSrc`/included build logic và khả năng dùng Configuration Cache/convention plugins. Tránh đọc network/time-sensitive state trong configuration phase khi có thể.

## 14. --profile và Build Scan chưa phải mọi loại profiler

### 14.1. Method-level CPU/heap

Local profile và Build Scan thường cho duration theo phase/tasks và một số resource metrics; chúng **không tự là profiler xác định phương thức Java chiếm bao nhiêu CPU/allocations**. Nếu một custom plugin quá chậm và cần flame graphs, dùng **Gradle Profiler**, JFR hoặc async-profiler với scenario được kiểm soát.

### 14.2. Build Scan upload có thể thất bại

Build Scan phụ thuộc server/network/auth/TLS; plugin có thể upload background sau build. Build `SUCCESS` không chắc chắn scan URL đã được publish thành công. CI ephemeral có thể kết thúc trước upload; đọc publication status và plugin docs. Không tự tắt TLS/certificate verification để làm URL hoạt động.

### 14.3. HTML local cũng không mặc nhiên công khai được

File `build/reports/profile/*.html` vẫn có thể mang project/task/script names. Một pipeline upload toàn bộ `build/reports/**` lên artifact store có quyền rộng có thể phát tán báo cáo. **Local** nghĩa là không do riêng `--profile` gửi scan, không nghĩa người khác không thể upload file đó.

## 15. Quy trình kết hợp đo lường và chia sẻ an toàn

**Pha A — local-first:**

1. Xác định task request/Gradle Wrapper/JDK/OS/commit/runner.
2. Kiểm tra auto-publishing plugin và cờ `--no-scan` khi cần.
3. Chạy `--profile` trên đúng workload, giữ report local.
4. Phân biệt startup/configuration/dependency resolution/task execution.
5. Benchmark warm/cold phù hợp với vài lần chạy, ghi median và task outcomes.
6. Chọn giả thuyết tối ưu (plugin eager, dependency network, test slow, cache miss).
7. Đổi một biến, chạy build/tests và đo lại.
8. Chỉ xem xét Build Scan khi local report chưa đủ.

**Pha B — approved Scan:**

1. Review loại data captured và logs/test outputs.
2. Chọn đúng public/private endpoint, check access/retention/consent.
3. Xóa nguồn rò rỉ secrets, cấu hình capture/obfuscation khi phù hợp.
4. Có approval của đúng chủ dữ liệu/security owner.
5. Publish đúng build cần phân tích, xác nhận URL/permissions.
6. Xem task timeline, cache, tests và environment.
7. Chia sẻ link trong kênh được cấp quyền, không public.
8. Ghi chép actionable bottleneck và đo lại cùng scenario.

**Pha C — báo cáo:**

```text
Workload: :app:test
Environment: Gradle Wrapper, JDK, runner class (sanitized)
Scenario: clean or warm; build/configuration cache state
Baseline: median of N comparable runs
Finding: bottleneck phase/task and observed outcomes
Change: one build-logic/dependency/test adjustment
After: median of N comparable runs
Correctness: tests/build PASS
Evidence: local profile or approved restricted scan
Privacy: approved endpoint, allowed audience and retention
```

Đây là **khung báo cáo**, không phải số liệu thật. Không được điền con số suy đoán hoặc đưa hostname/token thực vào báo cáo để tăng mức chi tiết.

## 16. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Không thấy `build/reports/profile` | Chưa dùng `--profile`, build fail quá sớm hoặc root/build directory khác. | Chạy đúng Wrapper, xem Gradle logs/root project. |
| Đọc nhầm profile cũ | Nhiều file timestamp. | Sort mtime, ghi lệnh/thời điểm report. |
| `--profile` không có URL | Bình thường, local HTML không phải Build Scan. | Mở report local. |
| `--scan` không có URL | Terms, auth, network, server/plugin/upload issue. | Xem console/upload logs, kiểm tra endpoint. |
| Scan xuất hiện dù không gõ `--scan` | Develocity/plugin/CI auto-publish. | Kiểm tra settings/init/CI, `--no-scan` khi hỗ trợ. |
| Người ngoài mở được link scan | Public-link endpoint; URL lộ ở logs/chat. | Ngừng chia sẻ, xử lý theo sensitivity và policy. |
| Tắt testLogging mà failure vẫn hiện | Develocity vẫn có thể capture failure metadata. | Không coi capture toggle là total redaction. |
| Obfuscate username nhưng log vẫn lộ | Obfuscation chỉ xử lý field nhất định. | Sửa log từ nguồn, không chỉ callback. |
| `--quiet` còn secrets | Errors/test/plugin output vẫn có thể được capture. | Secret hygiene/credential providers. |
| Startup lần đầu chậm | Cold JVM/daemon/Wrapper. | Đo cold/warm riêng. |
| Warm build nhanh vì UP-TO-DATE | Local outputs vẫn hợp lệ. | Không báo compiler tối ưu khi chưa đo cùng scenario. |
| Sum task durations lớn hơn elapsed | Parallel tasks. | Xem critical path/timeline. |
| Configuration rất chậm | Eager tasks/plugins, settings IO, buildSrc. | Lazy APIs/Configuration Cache phù hợp. |
| Dependency downloads lớn | Cache cold, repo/proxy/network. | Kiểm tra repository/Gradle User Home, không sửa compiler. |
| Self-hosted scan URL không mở | Auth/SSO/network ACL. | Xin đúng quyền; không chuyển sang public scan. |
| `--develocity-url` không nhận | Gradle quá cũ. | CLI chỉ có từ Gradle 9.5+, dùng plugin config tương thích. |
| Plugin/Gradle Develocity không tương thích | Version matrix không khớp. | Pin supported versions và đọc compatibility docs. |

## 17. Bài tập

**Bài 1:** Chạy `./gradlew help --profile`. Report ở đâu? **Root build/reports/profile**; không tự publish vì riêng flag này.

**Bài 2:** Chạy lab `./gradlew -q run --args="10"`. Stdout? **`sum(1..10)=55`**.

**Bài 3:** Vì sao `clean build --profile` và `build --profile` warm không phải benchmark tương đương? **Tasks executed/outcomes khác nhau**.

**Bài 4:** Task A 10s, B 12s và C 8s: elapsed có chắc 30s không? **Không**, tasks có thể song song.

**Bài 5:** Project có dữ liệu khách hàng nhạy cảm, chưa có approval. Chọn gì? **Local --profile**, chưa publish Build Scan.

**Bài 6:** Link scan trên public service chỉ owner xem được? **Không**, ai có URL có thể truy cập.

**Bài 7:** Build Scan không upload toàn bộ source thì có thể lộ source không? **Có thể**, qua errors/log snippets.

**Bài 8:** Cần nêu 5 nhóm có thể capture: **project/task, dependencies, tests/failures, logs, username/host/IP/JDK/OS**.

**Bài 9:** `--no-scan --profile` giải quyết gì? **Local report đồng thời suppress publication khi plugin hỗ trợ**.

**Bài 10:** `publishing.onlyIf { false }` làm gì? **On-demand publishing**, `--scan` vẫn có thể chủ động publish theo docs.

**Bài 11:** `testLogging = false` có loại mọi test failure message không? **Không**.

**Bài 12:** Username obfuscation có sửa username in console không? **Không**.

**Bài 13:** Self-hosted Develocity tự đảm bảo RBAC đúng cho mọi team không? **Không**, phải cấu hình/kiểm tra.

**Bài 14:** Tại sao không dùng `--quiet` để ẩn secrets? **Không phải redaction guarantee**.

**Bài 15:** Configuration phase cao thì tối ưu Java code trước? **Không**, điều tra scripts/plugins/settings/build logic.

**Bài 16:** `UP-TO-DATE` có nghĩa build-cache hit không? **Không**, outputs local còn hợp lệ.

**Bài 17:** Một commit chạy nhanh hơn trên CI mới đã warm cache. Có chứng minh code cải thiện không? **Chưa**, cần so cache conditions tương đương và nhiều mẫu.

**Bài 18:** Scan public URL tự xuất hiện trong CI PR comment. Cần kiểm tra gì? **Endpoint, viewer permissions, metadata/log sensitivity, approval và retention**.

**Bài 19:** Nếu scan chứa token, bước nào? **Ngừng chia sẻ, rotate/revoke, báo incident owner, liên hệ server admin**.

**Bài 20:** Một báo cáo tối ưu tốt ghi gì? **Workload, Wrapper/JDK/commit, scenario, cache modes, N runs/median, task outcomes, evidence và quyền truy cập**.

### Tự kiểm tra nhanh

1. `--profile` tạo HTML report local? **Có**.
2. Đường dẫn mặc định? **build/reports/profile**.
3. `--profile` tự publish Build Scan? **Không do riêng flag**.
4. `--scan` có thể gửi data ra server? **Có**.
5. Public-link scan chỉ owner? **Không**.
6. Develocity internal server tự có hạn chế người xem phù hợp? **Không đảm bảo**.
7. Tên project/task/test có thể có trong scan? **Có**.
8. Compiler/test failures có thể lộ data dù không upload source? **Có**.
9. `--quiet` là biện pháp bảo mật dữ liệu? **Không**.
10. Tắt capture logs có loại mọi failure metadata? **Không**.
11. Obfuscation callbacks che mọi loại data? **Không**.
12. `UP-TO-DATE` giống FROM-CACHE? **Không**.
13. Cộng task durations bằng wall-clock? **Không nếu parallel**.
14. Dùng Build Scan để đo method-level allocation? **Không phải công cụ phù hợp duy nhất**.
15. Build SUCCESS nghĩa scan upload SUCCESS? **Không nhất thiết**.
16. CLI `--develocity-url` được Gradle hỗ trợ từ version nào? **9.5.0+**.
17. `--no-scan` xóa scans cũ? **Không**.
18. HTML local có thể bị lộ nếu CI upload? **Có**.
19. Nên so benchmark như thế nào? **Cùng workload/environment/cache state, nhiều samples**.
20. Chính sách ưu tiên? **Đo local trước, review dữ liệu và quyền truy cập rồi mới publish**.

## 18. Tài liệu chính thức

- **Gradle — Inspecting Builds / Build Scan:** local HTML profile, phase categories, performance overview, Gradle Profiler: https://docs.gradle.org/current/userguide/inspect.html
- **Gradle — Build Scan Basics:** `--scan`, Terms of Service, publishing tới Develocity server: https://docs.gradle.org/current/userguide/build_scans.html
- **Gradle — Troubleshooting Builds:** console/test logs, failures, stack traces và link access cautions: https://docs.gradle.org/current/userguide/troubleshooting.html
- **Gradle — Command-Line Interface:** `--profile`, `--scan`, `--no-scan`, `--console`: https://docs.gradle.org/current/userguide/command_line_interface.html
- **Develocity Gradle Plugin 4.5 User Manual:** publishing policies, capture.buildLogging, capture.testLogging, obfuscation, Appendix B Captured Information và Access: https://docs.develocity.ai/gradle/4.5/gradle-plugin/
- **Develocity Version Compatibility:** plugin/Gradle/server version requirements: https://docs.gradle.com/develocity/compatibility/
- **Gradle Profiler:** repeatable benchmark scenarios/JFR/async-profiler: https://github.com/gradle/gradle-profiler
- **Gradle — Build Performance:** benchmark và tối ưu: https://docs.gradle.org/current/userguide/performance.html
- **Gradle — Build Cache:** cache outcomes/tasks: https://docs.gradle.org/current/userguide/build_cache.html
- **Gradle — Configuration Cache:** cấu hình/task graph reuse: https://docs.gradle.org/current/userguide/configuration_cache.html

**Kết luận:** **`--profile`** cho bạn **báo cáo HTML local** để xác định Gradle startup/configuration/resolution/task execution đang tốn thời gian, là lựa chọn đầu tiên khi chưa có quyền chia sẻ dữ liệu. **Build Scan** cung cấp timeline, caches, tests, dependencies và environmental metadata chi tiết hơn, nhưng **publication có thể gửi dữ liệu build ra server**. Ai có URL public-link có thể xem, và obfuscation/tắt console capture không che mọi failure data. Hãy benchmark trong điều kiện tương đương, bắt đầu local, audit data/endpoint/access/retention, và chỉ chia sẻ scan cho đúng người được phép.