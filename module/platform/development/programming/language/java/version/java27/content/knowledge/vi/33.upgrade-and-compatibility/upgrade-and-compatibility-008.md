# Lập ma trận build, kiểm thử hồi quy và đo hiệu năng trước khi chuyển đổi

> **Phạm vi:** Java 27 — chương **Nâng cấp và tương thích Java 27**. Bài học hướng dẫn thiết kế **ma trận thử nghiệm có thể tái hiện**, đánh giá tương thích nguồn/nhị phân/hành vi, kiểm thử hồi quy chức năng và so sánh hiệu năng trước khi chuyển runtime hoặc toolchain sang JDK 27. Nguyên tắc là **giữ một đường baseline chạy trên JDK hiện tại, đổi từng biến có kiểm soát, dùng tiêu chí đạt/không đạt định lượng và chuẩn bị rollback**. Các công cụ và API trình bày đều còn sử dụng được; thay đổi cụ thể của Java 27 được đối chiếu với **Oracle JDK Migration Guide 27**, release notes và tài liệu công cụ chính thức.

## 1. Vì sao không nên chỉ đổi JAVA_HOME và chạy một lần?

Một dịch vụ có thể khởi động thành công trên JDK 27 nhưng vẫn gặp:

- Một thư viện gọi API đã bị loại bỏ hoặc hành vi thư viện bị thay đổi.
- Test fixtures và build plugins chưa đọc được class-file version của Java 27.
- Mã dùng reflection sâu, JNI/FFM hoặc class loading động có hành vi khác.
- Thay đổi định dạng thời gian, locale, timezone, TLS/certificate hoặc truy vấn database.
- Kết quả JSON, SQL, số học, sorting, encoding hoặc quy tắc HTTP khác baseline.
- Độ trễ p99, GC pauses hoặc memory RSS thay đổi dưới tải cao.
- Một bản đóng gói chạy trên developer laptop nhưng không chạy trong container production.
- Hệ thống giám sát, agent, profiler hoặc logging plugin bị lỗi dù request chính vẫn trả thành công.

Đặc biệt, có **ba kiểu tương thích khác nhau** cần đánh giá độc lập:

| Tầng | Câu hỏi | Ví dụ lỗi |
| --- | --- | --- |
| **Source compatibility** | Mã nguồn cũ có còn biên dịch được khi dùng compiler/API JDK 27? | Compile errors, type inference hoặc API bị loại bỏ |
| **Binary compatibility** | Class/JAR đã biên dịch có còn load/link trên runtime JDK 27? | `NoSuchMethodError`, `NoClassDefFoundError`, `UnsupportedClassVersionError` |
| **Behavioral compatibility** | Khi chạy cùng workload, hệ thống còn trả kết quả và hiệu năng đúng contract? | Thay đổi locale/HTTP path matching, security defaults, timing/GC |

**Quy tắc:** build xanh **không chứng minh** runtime đúng; runtime khởi động **không chứng minh** nghiệp vụ đúng; hồi quy chức năng đạt **không chứng minh** latency/memory đạt.

### 1.1. Kết quả bàn giao phải là một quyết định có căn cứ

Sau chiến dịch đánh giá, nhóm cần có:

1. Ma trận `JDK × build tool × OS/arch × dependency set × test suite` với những ô đã chạy thật.
2. Danh mục warnings, breakages, incompatible dependencies và người phụ trách.
3. Reports về unit/integration/contract/end-to-end/security tests.
4. Baseline và candidate performance trên cùng workload/hạ tầng.
5. Các **release gates** và ngưỡng dừng/rollback đã được thống nhất **trước khi đo**.
6. Bộ artifact, flags, dependency lock versions và kết quả đo đủ để tái hiện.
7. Quyết định: **GO**, **NO-GO** hoặc **GO WITH CONDITIONS** kèm rủi ro.

Không dùng câu “chạy được trên máy tôi” làm biên bản chấp nhận nâng cấp.

## 2. Xác định phạm vi thay đổi trước khi lập ma trận

Một lần “nâng Java” có thể đồng thời thay đổi nhiều thành phần. Cần phân biệt:

~~~text
                TRẠNG THÁI HIỆN TẠI
  Source code ─── Dependency graph ─── Build plugins
       │                  │                   │
       ▼                  ▼                   ▼
  javac release       Framework/ORM       Maven/Gradle
       │                  │                   │
       └───────── Build artifact ────────────┘
                              │
                              ▼
                 Runtime JDK + VM flags
                              │
                              ▼
                    OS/CPU/container
                              │
                              ▼
                DB, network, TLS, external APIs
                              │
                              ▼
                  Observed behavior/metrics
~~~

Mỗi thay đổi bổ sung làm khó việc quy trách nhiệm cho regression. Vì vậy nên **tách thời điểm**:

- **R0 / Baseline:** artifact hiện đang chạy, JDK hiện tại, dependencies và flags hiện tại.
- **R1 / Runtime-only:** **chính bytecode/JAR của R0** nhưng chạy trên JDK 27. Không đồng thời đổi major framework version nếu chưa bắt buộc.
- **R2 / Rebuild-only:** biên dịch lại với compiler/toolchain JDK 27, giữ source logic và dependency set có thể so sánh, vẫn chạy trên JDK 27.
- **R3 / Compatibility fixes:** áp dụng những thay đổi thư viện/build/flags cần thiết, có changelog riêng; chạy lại full test + performance.
- **R4 / Adoption (tùy chọn):** dùng Java 27 language/library features mới. Đây là dự án riêng, **không bắt buộc** để hoàn tất runtime migration.

**Oracle JDK Migration Guide 27 khuyến nghị thử chạy ứng dụng trên JDK mới trước khi compile lại**, sau đó cập nhật thư viện, biên dịch và phân tích dependencies theo vòng lặp. Cách tiếp cận này giúp phân biệt binary/runtime compatibility với vấn đề compile-time.

### 2.1. Đừng giả định bản Java trước đó là Java 21

Ví dụ trong bài dùng **JDK 21 làm baseline** vì đây là một mốc thường gặp, nhưng bạn có thể thay bằng JDK 17, 25 hoặc 26 đang chạy thật. Ma trận phải ghi **patch level, vendor và runtime options cụ thể**, không chỉ “21” hoặc “27”.

JDK 27 là một release theo cadence 6 tháng, **không** phải bản LTS mới theo mọi vendor. Vòng đời hỗ trợ và thời hạn vá bảo mật khác nhau theo vendor/phân phối. Trước khi chuyển production, xác minh chính sách support và lộ trình nâng cấp kế tiếp của tổ chức.

## 3. Lập bản kiểm kê (inventory) trước khi đo

### 3.1. Thông tin cần lưu cho từng dịch vụ

| Nhóm | Dữ liệu bắt buộc |
| --- | --- |
| Runtime | `java -version`, vendor/build, `JAVA_HOME`, GC, JVM flags, security properties |
| Build | Maven/Gradle/Wrapper version, compiler/toolchains, plugin versions, annotation processors |
| Artifact | Commit SHA, artifact coordinates, hash, `--release`/major version, packaging |
| Dependencies | Direct/transitive JAR versions, JNI/native libs, agents, framework, JDBC driver |
| Platform | OS, architecture, CPU model/quota, RAM/cgroup limits, container base image |
| Traffic | Arrival rate, concurrency, peak/steady workload, request/response sizes |
| Storage/IO | DB topology, connection pools, filesystem, TLS, DNS, downstream timeouts |
| Tests | Unit, integration, end-to-end, contract, concurrency, localization, security |
| Observability | Metrics names, JFR/GC logs, tracing sampling, latency histograms |
| Rollback | Đường quay về runtime cũ, database schema compatibility, deployment strategy |

Dữ liệu này là **đầu vào của phép so sánh**. Nếu baseline và candidate dùng khác CPU quota hoặc database dataset, kết luận chênh lệch 5% latency thường không đáng tin.

### 3.2. Lệnh xác nhận JDK và môi trường

Trên đúng máy/container cần kiểm thử:

~~~bash
java -version
javac -version
jcmd -l
~~~

Kiểm tra thêm **đúng process** khi server đang chạy:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
~~~

Thận trọng: `VM.command_line`/`VM.system_properties` có thể chứa URL nội bộ, token, system property bí mật. Đừng đẩy nguyên output vào issue/CI artifacts công khai; áp dụng masking và quyền truy cập phù hợp.

Nếu không có `jcmd` trong minimal runtime image hoặc container, dùng JDK diagnostic tool có quyền attach thích hợp, JFR startup recording hoặc metrics có sẵn. **Không** suy diễn runtime hiện tại từ một `java` trên developer PATH.

### 3.3. Giữ nguyên input, dataset và workload

Baseline nên lưu:

- Git commit/tag và artifact checksum.
- Dependency lock/effective dependency tree.
- Seeds của random generators và cách tạo dataset test.
- API fixtures, serialized payloads, DB schema/migrations.
- Traffic replay distribution (method, size, hot/cold keys, think time).
- Một bảng JVM flags được **giải thích**, không copy những flag lỗi thời qua release mới.
- Nơi và thời gian đo, patch version, OS/kernel/container cgroup quota.

Không nhúng credentials hay production user data chưa được phép vào bộ benchmark. Tạo dữ liệu tổng hợp hoặc bản sao đã khử nhạy cảm.

## 4. Thiết kế ma trận tương thích tối thiểu

Một ma trận tốt là **có chủ đích**. Không cần chạy mọi tổ hợp lý thuyết, nhưng phải bao phủ các khác biệt có thể ảnh hưởng deployment.

### 4.1. Ma trận phát triển theo giai đoạn

| Mã ô | Compiler/toolchain | Build artifact | Runtime | Mục tiêu |
| --- | --- | --- | --- | --- |
| **M0** | JDK hiện tại, ví dụ 21 | Artifact cũ A | JDK 21 | **Baseline**: chứng minh workflow và kết quả hiện trạng |
| **M1** | **Không rebuild** | **Chính artifact A** | **JDK 27** | Kiểm tra binary + runtime/behavior compatibility |
| **M2** | JDK 27, `--release 21` nếu hỗ trợ source/API | Artifact B | JDK 21 | Kiểm tra **tương thích ngược** nếu vẫn hỗ trợ runtime cũ |
| **M3** | JDK 27, `--release 21` | Artifact B | JDK 27 | Tách ảnh hưởng compiler mới với target cũ |
| **M4** | JDK 27, `--release 27` | Artifact C | JDK 27 | Trạng thái đích sau rebuild |
| **M5** | JDK 27 + bộ dependencies/plugins đã nâng | Artifact D | JDK 27 | Đánh giá những compatibility fixes bắt buộc |

Chữ `A/B/C/D` là **nhãn artifact theo ma trận**, không mặc định các artifacts khác nhau nếu compiler tạo bytecode giống nhau. Mỗi artifact phải có checksum và commit/dependency set tương ứng.

**Chú ý:** nếu phát hành vẫn cần chạy trên JDK 21, `--release 27` tạo class file major **71** và **không** chạy được trên JVM 21 (major **65**). Ô `M2` quan trọng khi hỗ trợ đồng thời cả hai runtime, còn `M4` chỉ hợp lệ nếu deployment cho phép Java 27 runtime.

### 4.2. Ma trận hệ điều hành và kiến trúc

| Platform | Ô tối thiểu nên chọn | Lý do |
| --- | --- | --- |
| Linux x86-64 container giống production | M0/M1/M4/M5 | Base image, cgroups, native libs, TLS |
| Linux AArch64 nếu production dùng | M1/M4/M5 | Native artifacts, CPU architecture và JIT |
| Windows desktop/server nếu triển khai | M1/M4 | Filesystem, process behavior, timezone, paths |
| macOS nếu là nền tảng sản phẩm | M1/M4 | Signing, native libraries và runtime |
| CI ephemeral runner | M0/M1/M4 | Reproducibility, toolchain resolution, reports |
| Custom `jlink` image | M4/M5 trên **image đã link** | Runtime thiếu modules/services so với full JDK |

Không cần thêm mọi OS không được sản phẩm hỗ trợ; ngược lại **không được bỏ** một platform sản xuất chỉ vì unit tests trên Linux đã qua.

### 4.3. Tổ chức ưu tiên để tránh bùng nổ tổ hợp

Thay vì Cartesian product của mọi dependency version × JDK × OS × GC × workload:

1. **Gate 1:** chạy M0, M1 trên platform chính.
2. **Gate 2:** chạy M2/M3 nếu cần backward compatibility.
3. **Gate 3:** chạy M4 và M5 trên platform chính, then thêm OS/arch production còn lại.
4. **Gate 4:** mở rộng sang GC, JVM flags, các external systems có rủi ro cao.
5. **Gate 5:** mới thử nghiệm canary với traffic thật.

**Pairwise coverage** có ích cho tổ hợp phụ, nhưng **không thay thế** những tổ hợp critical path có nguy cơ cao (JDBC/native/crypto/runtime image).

## 5. Ghi ma trận thành dữ liệu có thể vận hành

Ma trận nên nằm trong tài liệu/CI configuration có tên ô và expected outputs rõ ràng. Ví dụ YAML **minh họa** (không phải syntax mặc định của GitHub Actions/GitLab CI):

~~~yaml
migration:
  targetJdk: "27"
  referenceRuntime: "21"
  platform: "linux-amd64"
  codeRevision: "REPLACE_WITH_COMMIT_SHA"
  workloadProfile: "replay-v1"
  cells:
    - id: M0
      compiler: "21"
      release: "21"
      runtime: "21"
      artifact: "baseline-A.jar"
      suites: [unit, integration, contract, smoke]
    - id: M1
      compiler: "21"
      release: "21"
      runtime: "27"
      artifact: "baseline-A.jar"
      suites: [unit, integration, contract, smoke, performance]
    - id: M4
      compiler: "27"
      release: "27"
      runtime: "27"
      artifact: "candidate-C.jar"
      suites: [unit, integration, contract, smoke, security, performance]
  gates:
    functionalRegressions: 0
    unresolvedCriticalVulnerabilities: 0
    p95LatencyRelativeMax: 1.05
    p99LatencyRelativeMax: 1.10
    throughputRelativeMin: 0.97
~~~

Các con số `1.05`, `1.10`, `0.97` là **ngưỡng ví dụ**, không phải SLO mặc định của Java 27. Phải thống nhất với chủ sở hữu dịch vụ dựa trên baseline variability, độ rủi ro và business requirements trước khi chạy đo.

Ma trận cần ghi thêm **PASS/FAIL/SKIP**, test report URI, environment, SHA, compiler/daemon/toolchain versions, người phê duyệt và lý do SKIP. Không tô “PASS” một ô **chưa chạy**.

### 5.1. Ô bị bỏ qua không được ngầm coi là đạt

Nếu một CI runner không thể cấp JDK 27 hoặc driver chưa hỗ trợ:

~~~text
M4 / linux-arm64 / integration-db = BLOCKED
Reason: JDBC native library for ARM64 unavailable
Owner: data-platform
Decision: NO-GO for ARM64 deployment
~~~

**BLOCKED** khác **FAILED** và **PASS**. Rủi ro chưa được kiểm chứng không biến mất chỉ vì build trên platform khác xanh.

## 6. Kiểm tra build tool và compiler trước khi chạy matrix

Đổi JDK runtime và đổi compiler là hai việc khác nhau; phải ghi lại cả hai.

### 6.1. Maven: compiler --release và JVM chạy Maven

Trong `pom.xml`, một cấu hình compile Java 27 điển hình:

~~~xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Cần Maven Compiler Plugin được duy trì và phiên bản đã được xác minh tương thích với JDK 27. **Khai `release=27` không tự tải JDK 27**. Dùng `mvn -version` để biết Java version mà Maven process đang sử dụng; nếu tổ chức dùng Maven Toolchains, phải kiểm tra JDK thực sự được compiler plugin chọn.

Lệnh kiểm tra:

~~~bash
mvn -version
mvn --batch-mode --no-transfer-progress verify
~~~

Lệnh `verify` chạy các checks/plugins **đã được cấu hình**; không tự chứng minh dự án có integration/performance suite.

Nếu artifact vẫn cần tương thích Java 21, dùng:

~~~xml
<maven.compiler.release>21</maven.compiler.release>
~~~

và biên dịch bằng compiler đủ mới hỗ trợ `--release 21`, đồng thời chạy tests trên runtime JDK 21 **và** JDK 27. Không được đổi `release` rồi bỏ bước kiểm thử backward compatibility.

### 6.2. Gradle: xác nhận compatibility matrix Java 27

Theo **Gradle Compatibility Matrix (9.9.2)**, **Gradle 9.8.0 trở lên** hỗ trợ Java 27 cả cho **toolchains** và **chạy Gradle**. Bản Gradle 9.8.0 đã phát hành ngày 24/09/2026; ưu tiên patch release hiện hành đã được nhóm phê duyệt thay vì mặc định dùng bản đầu tiên.

Trong `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 27
}
~~~

Nếu vẫn cần Java 21 API/class-file target, giữ toolchain 27 nhưng đổi `options.release = 21` và kiểm thử với runtime 21. **Gradle toolchain 27** quyết định compiler được chọn; **`options.release`** kiểm soát source/API/classfile target. Chúng không phải một thiết lập giống nhau.

Kiểm tra:

~~~bash
./gradlew --version
./gradlew --no-daemon clean build
~~~

Windows PowerShell dùng `.\gradlew.bat`. Nếu JDK toolchain chưa được cài hoặc provision, build có thể thất bại trước khi compile. Nếu dự án dùng annotation processors, Kotlin/Groovy/Scala plugin hoặc bytecode instrumentation, xác minh **từng plugin** hỗ trợ Java 27; Gradle core tương thích **không bảo đảm** mọi plugin bên thứ ba cũng vậy.

### 6.3. Tạm thời không nâng cùng lúc nhiều yếu tố

| Bước | JDK | Build tool | Framework/dependencies | Mục tiêu |
| --- | --- | --- | --- | --- |
| Baseline | Current | Current | Current | Xác nhận hiện trạng |
| Runtime-only | **27** | Không rebuild | **Giữ nguyên** | Xem runtime compatibility |
| Build tool upgrade | 27 | Phiên bản tương thích | Chỉ nâng khi cần | Tách lỗi build engine |
| Library fixes | 27 | Đã ổn định | Nâng mục tiêu | Xem ABI/behavior |
| Optimization | 27 | Đã ổn định | Đã ổn định | Đo hiệu năng sau chức năng |

Có trường hợp phải đổi framework trước để ứng dụng khởi động trên Java 27. Khi đó ghi rõ **dependency change set**, so sánh nhiều baseline phụ và tránh kết luận mọi chênh lệch là do JDK.

## 7. Kiểm tra artifact, dependency graph và class-file version

Trước khi chạy regression suite, cần biết **chính artifact nào** và **bộ dependencies nào** được đưa vào từng ô của ma trận.

### 7.1. Kiểm tra đúng class file

~~~bash
jar --list --file app.jar
javap -verbose path/to/Main.class
~~~

Trong output `javap -verbose`, tìm `major version`:

| Java target | Class-file major |
| --- | ---: |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |
| 26 | 70 |
| **27** | **71** |

Một class file major **71** không chạy trên JVM 21 chỉ vì code không dùng tính năng Java 27. **`--release 21`** mới là cơ chế biên dịch source/classfile/API phù hợp khi hỗ trợ runtime 21. Artifact có nhiều modules hoặc multi-release JARs cần kiểm tra **từng variant** thực sự được runtime chọn.

### 7.2. Phân tích JDK internal APIs

~~~bash
jdeps --jdk-internals --multi-release 27 app.jar
~~~

Nếu app có third-party dependencies:

~~~bash
jdeps --multi-release 27 --class-path "lib/*" --jdk-internals app.jar
~~~

Lệnh ví dụ cho Unix shell (đặt classpath trong dấu ngoặc kép để tránh shell tự expand). Trên Windows cũng có thể dùng `"lib/*"` khi mục tiêu là tất cả JARs trong thư mục. `jdeps` giúp phát hiện tham chiếu **tĩnh** tới internal JDK APIs; nó **không tìm được mọi hành động reflection**, native invocation hoặc những class names chỉ nằm trong config.

Không xem `--add-opens`/`--add-exports` là giải pháp dài hạn để tiếp tục dùng unsupported internal APIs. Nếu framework cũ đòi flag tạm thời, lưu owner, lý do và ngày loại bỏ; ưu tiên cập nhật thư viện dùng API được hỗ trợ.

### 7.3. Quét API deprecated và đã đánh dấu for removal

~~~bash
jdeprscan --for-removal --class-path "lib/*" app.jar
~~~

`jdeprscan` phân tích những Java SE APIs được đánh dấu deprecated-for-removal. Nó **không** quét deprecations của mọi thư viện bên ngoài JDK và **không** phát hiện hết hành vi gọi gián tiếp. Phải bổ sung static analysis/check dependency vulnerabilities của toolchain hiện tại.

Nếu quét bị báo thiếu class:

- Kiểm tra lại `--class-path`, modular dependencies và version JAR.
- Không đánh dấu kết quả “sạch” khi scanner chưa phân tích được đủ input.
- Với ứng dụng modular, sử dụng các tùy chọn module path phù hợp theo `jdeprscan --help` của JDK 27.

### 7.4. Dependency resolution là một dữ liệu kiểm thử

Với Maven:

~~~bash
mvn -version
mvn dependency:tree
mvn help:effective-pom
~~~

Với Gradle:

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency slf4j-api
~~~

Một lần nâng plugin/framework có thể đổi cả transitive dependencies, security providers hoặc JDBC drivers. Nếu giữ JDK cố định mà dependency graph đã đổi, **chênh lệch kết quả không thể chỉ quy về JDK**.

Khi giữ baseline, lưu `group:artifact:version`, checksums, repository provenance và runtime dependency graph. Nếu có plugin bytecode generator/coverage instrumentation, ghi cả version để phân biệt lỗi của plugin với lỗi bytecode do Java 27 tạo.

## 8. Những thay đổi Java 27 cần đưa vào regression checklist

Không phải mọi ứng dụng đều chịu ảnh hưởng những thay đổi này. Chọn test theo API/framework/flags đang **thực sự sử dụng**, không thêm cơ học mọi test cho mọi hệ thống.

### 8.1. Một số thay đổi cụ thể của JDK 27

| Thay đổi theo release notes Java 27 | Nhóm test nên có | Hướng xử lý |
| --- | --- | --- |
| Bỏ các flags `-noverify`, `-Xverify:none`, `-verifyremote` và `-noclassgc` | **Startup smoke** và kiểm tra toàn bộ JVM arguments | Xóa flags không còn được hỗ trợ; không bypass verifier |
| Bỏ thử nghiệm **JVMCI** và các modules/flags tương ứng | Startup/agent/JIT-plugin compatibility | Nâng cấp hoặc loại integration phụ thuộc JVMCI nội bộ |
| `java.locale.useOldISOCodes` không còn tác dụng | Locale/language-tag tests | Dùng mã ngôn ngữ chuẩn mới (`he`, `yi`, `id`) |
| JDK `HttpServer` đổi xử lý đường dẫn từ **string-prefix** sang **path-prefix** | Routing/authz boundary tests | Kiểm tra `/foo` khác `/foobar`, đừng dựa hành vi cũ |
| CLDR/locale data và timezone database được cập nhật | Format/parse date, currency, locale, DST | Dùng expected behavior theo contract và ghi tzdb version |
| **Compact object headers được bật mặc định** trong HotSpot (JEP 534) | Heap/RSS/GC, tool/agent compatibility | So sánh memory và profiler/agent behavior |
| G1 thay đổi giá trị mặc định `MinHeapFreeRatio`/`MaxHeapFreeRatio` | Heap resizing/GC regression | Ghi GC options và đo theo workload |
| Cảnh báo về deep reflection sửa `final` fields | Serialization/ORM/DI/reflection tests | Sửa thư viện/code; tránh tắt cảnh báo đại trà |

Các ví dụ trên được xác minh từ **Oracle JDK 27 Migration Guide và Release Notes (tháng 9/2026)**. Những bug fixes hoặc updates ở patch release có thể bổ sung thay đổi; vì vậy ma trận phải ghi **full runtime version**, không chỉ feature version `27`.

### 8.2. Startup smoke với flags hiện tại

Việc đầu tiên sau khi chuyển JDK:

~~~bash
java -version
java -XshowSettings:properties -version
java -jar app.jar
~~~

Dòng `java -jar app.jar` là **ví dụ cho executable JAR có `Main-Class` và runtime dependencies phù hợp**. Nếu artifact dùng modular launch, dùng `java --module-path ... --module module/main`; nếu là container hoặc framework launcher, chạy đúng entrypoint thật.

Khi JVM không khởi động:

- Xem thông báo `Unrecognized VM option` trước khi điều tra Java source.
- Kiểm tra service manager, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` và container environment.
- Không đổi cùng lúc GC, heap, agent và runtime chỉ để làm warning biến mất.
- Loại bỏ flags bị xóa thay vì cố tìm một flag “tắt verification” thay thế.

### 8.3. Ví dụ hợp đồng HTTP path

Nếu dùng **JDK built-in `com.sun.net.httpserver.HttpServer`**, phải thử những đường dẫn có prefix gần giống:

| Context khai báo | Request path | Kết quả routing cần xác định trên JDK 27 |
| --- | --- | --- |
| `/api` | `/api` | Context tương ứng |
| `/api` | `/api/orders` | Context tương ứng |
| `/api` | `/apix` | **Không** match chỉ vì cùng tiền tố chuỗi |
| `/admin` | `/administrator` | **Không** match chỉ vì cùng tiền tố chuỗi |

Những dòng này minh họa thay đổi **path-prefix matching**. Nếu ứng dụng dùng Netty, Servlet container hoặc routing framework khác, **không áp dụng** thay đổi của JDK `HttpServer` cho chúng một cách máy móc. Dù framework nào, authorization tests vẫn nên kiểm tra overlapping paths để tránh lỗi security.

### 8.4. Final fields và reflection

Nếu ORM/serializer/DI framework dùng deep reflection để thay đổi `final` fields, Java 27 có thể phát cảnh báo về việc cần chuẩn bị cho những hạn chế tương lai. Hãy:

1. Chạy integration tests trên **bản framework hiện hành được hỗ trợ**.
2. Ghi warning stacks và API liên quan.
3. Ưu tiên constructors, records và những cơ chế khởi tạo được hỗ trợ thay vì mutate `final`.
4. Chỉ xem flags cho phép ngoại lệ có phạm vi hẹp theo **JEP 500** nếu library thực sự cần và tổ chức chấp nhận rủi ro.
5. Đừng dùng `--add-opens` như cam kết vĩnh viễn rằng mọi final-field mutation sẽ được phép.

### 8.5. Không trộn preview features vào migration bắt buộc

Java 27 có những **preview** features riêng. Chúng không phải điều kiện để chạy artifact cũ trên JDK 27. Nếu nhóm muốn thử preview:

- Tách một nhánh/ma trận riêng.
- Biên dịch và chạy với `--enable-preview` theo release đích.
- Không đưa class file preview vào ứng dụng production mặc định khi chưa có chính sách quản lý vòng đời.
- Đừng cho rằng bytecode preview Java 27 chạy trên JDK 26 hoặc JDK 28 giống hệt.

Mục tiêu của bài là **chuyển đổi an toàn**, không phải ép chuyển source sang feature chưa final.

## 9. Xây dựng chiến lược kiểm thử hồi quy nhiều lớp

Một test suite đủ tin cậy cần kiểm tra từ những logic đơn lẻ tới hoạt động của cả hệ thống.

| Lớp kiểm thử | Điều cần bắt | Ví dụ |
| --- | --- | --- |
| Compile/API checks | Source/API/annotation processor incompatibility | `javac --release`, build plugins |
| Unit tests | Logic xác định, edge cases | Parse, số học, mapping, validation |
| Component tests | Tương tác vài class/module với test doubles | JSON serializer, cache logic |
| Contract tests | Request/response/event schema compatibility | HTTP DTO, Kafka/AMQP schemas, Protobuf |
| Integration tests | Library ↔ DB/broker/TLS/filesystem | JDBC transaction, connection pool, TLS handshake |
| End-to-end tests | User flow thực qua nhiều services | Login → create order → retrieve |
| Concurrency tests | Locking, ordering, race/deadlock, cancellation | Executor/virtual threads, transactional retries |
| Migration-specific tests | Những thay đổi JDK 27 thực sự ảnh hưởng | Locale, built-in HttpServer, JVM flags, reflection |
| Security tests | TLS, certificate, authz, crypto providers | HTTPS, token verification, path traversal |
| Performance tests | Throughput, latency, memory, GC, CPU | Replay workload tại tải đại diện |
| Resilience tests | Timeout/retries/partial failures/rollback | DB outage, downstream errors, restart |

**Định nghĩa pass trước khi chạy:** test assertions phải có expected result dựa trên nghiệp vụ, không chỉ chạy rồi chụp snapshot ngẫu nhiên từ runtime hiện tại.

### 9.1. Prioritize theo mức độ rủi ro

Ví dụ ưu tiên cao cho ứng dụng backend:

- Dữ liệu tiền tệ, thuế, rounding và `BigDecimal`.
- Date/time parsing, DST, timezone conversion và lưu UTC.
- Serialization, reflection, dependency injection, polymorphic DTOs.
- TLS, certificate chain, truststore và authentication.
- SQL transactions, JDBC driver, isolation, unique constraints.
- HTTP request paths, proxy headers và authorization.
- Background jobs, scheduler, retries, virtual threads và interruption.
- Native libraries/FFM/JNI, instrumentation agents.
- Custom `jlink` runtime image và service providers.

Với CLI app thuần không có DB/network, bỏ test DB là hợp lý — nhưng vẫn cần kiểm tra file encoding/paths, runtime packaging và input/output behavior.

## 10. Viết assertions ổn định qua nhiều runtime

Một regression test tốt nên phụ thuộc **hợp đồng** thay vì chi tiết không được đặc tả.

### 10.1. Ví dụ unit test với JUnit Jupiter

Giả sử module đã khai báo `org.junit.jupiter:junit-jupiter` và test engine/plugin tương thích trong Maven/Gradle; ví dụ này **không tự quản lý dependencies**. File `src/test/java/com/example/MoneyContractTest.java`:

~~~java
package com.example;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import java.math.RoundingMode;
import org.junit.jupiter.api.Test;

final class MoneyContractTest {
    static BigDecimal roundCurrency(BigDecimal value) {
        if (value == null) {
            throw new IllegalArgumentException("value");
        }
        return value.setScale(2, RoundingMode.HALF_EVEN);
    }

    @Test
    void roundsUsingExplicitPolicy() {
        assertEquals(new BigDecimal("2.34"),
                roundCurrency(new BigDecimal("2.345")));
        assertEquals(new BigDecimal("2.36"),
                roundCurrency(new BigDecimal("2.355")));
    }

    @Test
    void rejectsNull() {
        assertThrows(IllegalArgumentException.class,
                () -> roundCurrency(null));
    }
}
~~~

Ý nghĩa:

- Dùng string constructor của `BigDecimal`, không dùng binary `double` để định nghĩa giá trị tiền tệ mong đợi.
- Có `RoundingMode` explicit.
- `assertEquals` so sánh value **và scale** trong `BigDecimal`, vì vậy ví dụ chủ động thống nhất scale `2`.
- Cùng test chạy trên cả baseline và candidate, tạo cơ sở so sánh không phụ thuộc OS scheduler.

### 10.2. Đừng so sánh trực tiếp những output vốn biến thiên

Những thứ **không nên** dùng làm exact snapshot nếu không có contract quy định:

- Thứ tự iteration của `HashMap`/`HashSet`.
- `Object.toString()` có identity hash; memory addresses.
- Thread names/IDs, thời điểm scheduler quyết định chạy.
- Giá trị `System.currentTimeMillis()` hoặc `Instant.now()` chưa mock.
- Lỗi JVM stack trace với số dòng hoặc phương pháp in khác nhau.
- Default locale/timezone không được cố định trước.
- Nội dung JSON object keys khi schema không ràng buộc thứ tự.

Hãy **chuẩn hóa** dữ liệu chỉ ở những khía cạnh không thuộc contract: so sánh JSON object theo cấu trúc, sắp xếp collections có tính tập hợp, inject `Clock` trong logic thời gian, dùng explicit `Locale`/`ZoneId` khi nghiệp vụ yêu cầu.

Nhưng **không chuẩn hóa mất một regression thật**. Nếu hợp đồng yêu cầu một trường `createdAt` chính xác hoặc thứ tự sort cụ thể, kiểm tra chúng đúng như contract.

### 10.3. Regression với thời gian và múi giờ

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public final class TimeContract {
    public static ZonedDateTime displayInVietnam(Instant instant) {
        return instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
    }
}
~~~

Với code nghiệp vụ dùng timezone cố định, test nhận input `Instant` ổn định và kiểm tra expected calendar fields. Với locale-sensitive rendering, dùng `DateTimeFormatter.withLocale(...)` và `withZone(...)` rõ ràng.

**Phân biệt hai loại thay đổi:**

1. Hành vi định dạng/parse bị thay đổi ngoài dự kiến → regression cần sửa.
2. Timezone/CLDR data được cập nhật hợp lệ vì luật hoặc chuẩn mới → có thể là thay đổi **mong muốn**, cần review contract và golden fixtures trước khi kết luận fail.

## 11. Tạo bộ golden tests và contract fixtures

Một **golden test** lưu input và expected output đã được chủ sở hữu nghiệp vụ duyệt, ví dụ:

~~~text
fixtures/
  requests/
    create-order-valid.json
    create-order-invalid.json
  expected/
    create-order-success.json
    create-order-validation-error.json
  events/
    order-created-v2.json
~~~

Bộ fixture này là mô hình minh họa; không được Worker tạo thêm file theo path trên.

### 11.1. Cách so sánh

- Lấy input giống nhau gửi vào baseline và candidate.
- So sánh response status, headers quan trọng, body schema, error codes.
- Trên event streams, kiểm tra schema/version/key/order contract.
- Với DB writes, kiểm tra trạng thái cuối và side effects, không chỉ HTTP `200`.
- Nếu format cho phép thứ tự keys tùy ý, dùng structural JSON comparison.
- Nếu response chứa timestamps/UUIDs không xác định, inject deterministic clock/ID generator trong test environment.
- Chạy cả **positive cases**, **negative cases** và **security boundary cases**.

### 11.2. Migration không nên thay đổi contract vô tình

Một ứng dụng chỉ nâng JDK nhưng đổi output của endpoint từ `200` thành `201`, đổi error JSON schema hoặc đổi rounding policy là behavioral regression, trừ khi thay đổi đó đã được yêu cầu/chấp nhận riêng.

Quy tắc chấp nhận:

~~~text
Input + dữ liệu + cấu hình giống nhau
           │
           ▼
Baseline JDK → expected contract
Candidate JDK → observed contract
           │
           ▼
Nếu khác nhau:
  ├─ Bug regression → BLOCK
  ├─ Intentional change + approved versioning → ACCEPT riêng
  └─ Environment/test artifact issue → FIX TEST/INFRA
~~~

Đừng “làm xanh” test bằng cách thay expected output theo candidate chưa được review.

## 12. Integration tests: DB, TLS, services và native libraries

### 12.1. Database/JDBC

Ma trận cần kiểm tra **đúng JDBC driver và database version** sản phẩm đang dùng:

- Connection pool acquisition, validation và release khi có lỗi.
- Prepared statements, batch operations, transaction commit/rollback.
- Isolation/locking, deadlock retries, idempotent writes.
- Query/timeouts và cancellation behavior.
- Driver class loading, service provider discovery và native dependencies nếu có.
- Nhiều concurrent requests/virtual threads sử dụng pool có giới hạn.
- Schema migration forward/backward compatibility nếu có canary/rollback.

JDK thay đổi **không tự nâng DB schema**, nhưng có thể buộc nâng ORM/JDBC driver — khi đó cần thêm ô test phân biệt dependency changes.

### 12.2. TLS, truststore và security

Kiểm tra:

- HTTPS mutual TLS/one-way TLS, CA chain, hostname validation.
- Algorithms, providers, keystore/truststore và expired certificate behaviors.
- Client ↔ downstream protocol negotiation.
- Token signing/verification và cipher modes.
- Cấu hình `java.security`, `jdk.tls.disabledAlgorithms` nếu app phụ thuộc.
- FIPS/native security providers khi tổ chức dùng.

Không tắt certificate validation hoặc nới crypto policy chỉ để “hồi quy xanh”. Nếu JDK 27 chặn một thuật toán yếu, phân loại đó là security compatibility work cần xử lý đúng thay vì coi là false alarm.

### 12.3. Native/JNI/FFM và agents

Đây là vùng rủi ro cao vì phụ thuộc implementation/platform:

- JNI/native/JNA/FFM library versions và ABI.
- Profilers/bytecode agents/instrumentation.
- Bytecode generation bởi ORM/proxy/mock frameworks.
- Reflection/module `opens` theo contract.
- Runtime image modules và service providers.
- Container base OS, architecture, libc, native dependencies.

Agent cũ có thể khởi động nhưng làm sai kết quả profiling/coverage hoặc gây overhead đáng kể. Ghi phiên bản agent cùng với JDK và đo lại với **agent bật như production**, không chỉ chạy JVM trần.

## 13. Concurrency, lifecycle và kiểm thử tính bền vững

Một Java upgrade có thể làm thay đổi scheduling/JIT/GC timing mà không sai semantics. Test dựa trên sleep/dự đoán interleaving thường flaky ngay từ trước.

### 13.1. Kiểm thử điều kiện thay vì thời gian sleep cố định

Không nên:

~~~java
// Mã kiểm thử không ổn định:
// startWorker();
// Thread.sleep(200);
// assertEquals(1, sharedCounter.get());
~~~

Thay vào đó, dùng `Future.get()`, `CountDownLatch`, test clock hoặc synchronization primitives để chờ sự kiện có hợp đồng.

Ví dụ Java SE, không cần JUnit:

~~~java
import java.util.ArrayList;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public final class ConcurrencySmoke {
    public static void main(String[] args) throws Exception {
        var count = new AtomicInteger();

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var tasks = new ArrayList<Future<?>>();

            for (int i = 0; i < 1_000; i++) {
                tasks.add(executor.submit(() -> {
                    count.incrementAndGet();
                    return null;
                }));
            }

            for (Future<?> task : tasks) {
                task.get(); // phát hiện exception trong task
            }
        }

        if (count.get() != 1_000) {
            throw new AssertionError(count.get());
        }
        System.out.println("PASS");
    }
}
~~~

Đoạn này dùng virtual threads có từ Java 21; nếu baseline JDK **thấp hơn Java 21**, không chạy được cùng sample trên baseline mà cần test tương đương với một executor phù hợp. Mục đích là **xác nhận task lifecycle và synchronization**, không phải benchmark throughput.

### 13.2. Những điều cần thử dưới tải

- Lock contention, deadlock và repeated retries.
- Thread interruption, task cancellation, timeout propagation.
- Executor shutdown và graceful service shutdown.
- Connection pool exhaustion và memory pressure khi tạo nhiều task.
- ServiceLoader/context propagation/ThreadLocal assumptions.
- Background scheduled tasks, batch jobs và retries.
- Virtual-thread pinning khi có native/foreign code (xem JFR trên JDK 27).

Đối với Java 27, **không mặc định synchronized pin virtual threads** theo lời khuyên dành cho JDK 21–23: JEP 491 đã loại bỏ kiểu pinning do intrinsic monitor thông thường từ JDK 24. Nhưng contention, native blocking và lỗi phối hợp đồng thời vẫn có thể tồn tại.

## 14. Hiệu năng: mục tiêu đo là năng lực hệ thống, không chỉ benchmark một hàm

Một chương trình có thể chạy chức năng đúng trên JDK 27 nhưng tiêu thụ CPU/RAM nhiều hơn hoặc có tail latency lớn hơn. Cần chia **performance** theo cấp:

| Cấp đo | Ví dụ chỉ số | Dùng để trả lời |
| --- | --- | --- |
| Microbenchmark | Nanoseconds/op, operations/sec cho một phép tính | Một thuật toán/thư viện có thay đổi tốc độ không? |
| Component benchmark | Throughput JSON/JDBC/serialization, allocation/op | Một dependency/path quan trọng có regression không? |
| Service load test | Requests/sec, p50/p95/p99, errors, queue length | Dịch vụ có đạt SLO dưới lưu lượng đại diện không? |
| Soak/stability test | RSS, heap usage, GC, thread counts theo giờ | Có leak/fragmentation/GC pressure lâu dài không? |
| Startup/cold-start | Time-to-first-request, peak memory lúc boot | CLI, serverless và rollout có bị chậm không? |
| Resource efficiency | CPU-seconds/request, memory/request, DB connections | Cùng throughput dùng tài nguyên hiệu quả hơn hay kém? |

**Không dùng benchmark JMH của một method để kết luận toàn bộ HTTP service nhanh hơn.** Cũng không dùng benchmark HTTP đơn lẻ để giải thích vì sao method nội bộ chậm — cần profiling/JFR để tìm path có ý nghĩa.

### 14.1. Xây performance budget trước khi chạy

Ví dụ **minh họa**, không phải khuyến nghị chung:

| Chỉ số | Ngưỡng mục tiêu ví dụ |
| --- | --- |
| Correctness/error rate | Không có regression chức năng; error rate không vượt SLO |
| Throughput ở điều kiện saturation ổn định | Không thấp hơn baseline quá 3% |
| p95 latency ở **cùng offered load** | Không tăng quá 5% |
| p99 latency ở **cùng offered load** | Không tăng quá 10% |
| Heap live size sau GC ổn định | Không tăng vượt mức ngân sách đã duyệt |
| Peak RSS trong container | Không vượt hard memory limit/headroom |
| GC pause p99 | Không vượt SLO latency được phân bổ |
| Startup time | Không vượt startup readiness budget |

Hãy xem **noise/variance** trong baseline trước khi chọn 3–5–10%. Nếu baseline p99 dao động ±20% theo các lần chạy mà gate đặt 2%, kết quả sẽ báo động giả thường xuyên. Ngược lại, với hệ thống tài chính có hợp đồng độ trễ rất chặt, 10% có thể đã quá cao.

### 14.2. Các kịch bản tải bắt buộc

- **Cold start:** process mới, caches chưa warm, services chưa kết nối đủ.
- **Warm steady state:** tải ổn định sau JVM/JIT/GC warmup.
- **Ramp-up:** tăng lưu lượng từ thấp đến mức mục tiêu có kiểm soát.
- **Peak/burst:** tải cao trong khoảng ngắn, kiểm tra queues/backpressure.
- **Saturation:** xác định giới hạn throughput và điểm error/latency bắt đầu tăng mạnh.
- **Soak:** tải chạy lâu đủ quan sát leak/GC behavior, connection churn.
- **Failure injection:** DB chậm, retry storms, downstream timeout, restart.
- **Mixed workload:** tỷ lệ read/write, kích thước payload, số lượng concurrent tenants đại diện.

Nếu dịch vụ bị giới hạn từ DB hoặc downstream, chỉ thay JDK có thể **không** tăng throughput; sự khác biệt JIT/GC có thể bị che. Cần theo dõi backend latency/resource state song song với app.

## 15. Thiết kế thí nghiệm hiệu năng công bằng

Phép đo chỉ hữu ích nếu sự khác nhau giữa baseline và candidate là **biến đang muốn kiểm tra**.

### 15.1. Giữ điều kiện tương đồng

| Biến | Hành động kiểm soát |
| --- | --- |
| Source code | Dùng cùng commit hoặc diff được giải thích |
| Dependencies | Cùng versions nếu đang so runtime-only |
| JDK | Ghi vendor, feature/patch/build; đây là biến cần đổi |
| OS/CPU | Cùng loại máy, CPU architecture, quota/cgroup, kernel phù hợp |
| CPU frequency/noisy neighbors | Dedicated benchmark runners hoặc kiểm soát variance |
| Heap/GC options | Chọn **hai loại phép thử**: cùng flags nếu hợp lệ, và default được JDK hỗ trợ |
| Dataset/DB | Cùng database snapshot và schema, không dùng live production không kiểm soát |
| Traffic profile | Cùng arrival distribution, request mix, payload sizes |
| Warmup | Cùng quy trình và điều kiện dừng warmup |
| Agents/monitoring | Cùng cấu hình log/tracing/JFR hoặc ghi rõ overhead |
| Concurrency | Cùng offered load để so latency; thêm saturation test riêng |

Đặc biệt **đừng ép tất cả flags cũ sang JDK 27**. Một số flags bị xóa hoặc semantics thay đổi. Có hai phép thử hợp lệ:

1. **Default-to-default:** baseline dùng defaults của JDK hiện tại, candidate dùng defaults JDK 27. Phép thử đánh giá **trải nghiệm nâng runtime thực tế**.
2. **Controlled knobs:** cố định các tham số **còn được hỗ trợ và tương đương**, như heap limits/GC selection khi cần, để phân tích riêng ảnh hưởng của VM. Ghi lý do từng flag.

Một số thay đổi **defaults là chủ đích của JDK 27** (ví dụ compact object headers). Không cố tắt mọi default mới chỉ để làm số liệu giống trước, trừ khi đó là một experiment riêng có lý do rõ.

### 15.2. Thứ tự chạy và độ lặp

Một kế hoạch tối thiểu:

~~~text
Chạy baseline (A) → candidate (B) → B → A
     hoặc
B → A → A → B (theo block)
~~~

Lặp nhiều vòng trong điều kiện tương đương giúp giảm tác động của drift do hạ tầng, nhiệt CPU, cache và sự thay đổi backend. Nếu khả thi, randomize thứ tự A/B theo các vòng và ghi thời điểm.

**Không chỉ chạy A một lần lúc sáng và B một lần lúc chiều rồi nói B chậm hơn 4%.** Sai số thời điểm hoặc shared infrastructure có thể lớn hơn khác biệt JDK.

### 15.3. Open-loop và closed-loop load khác nhau

- **Open-loop / fixed arrival rate:** cố gửi request theo tốc độ đặt trước, kể cả khi response chậm. Phù hợp khi cần quan sát queueing và tail latency khi service quá tải.
- **Closed-loop / fixed concurrent users:** mỗi client gửi request mới sau khi request trước hoàn tất. Dễ kiểm soát số user đồng thời, nhưng offered load **giảm khi hệ thống chậm**, dễ che đuôi phân bố latency nếu chỉ nhìn average.

Cả hai đều có giá trị, nhưng không được so p99 giữa hai kiểu workload mà coi là tương đương. Nếu tool có **coordinated omission** correction, cần hiểu nó làm biến đổi thống kê như thế nào; đảm bảo baseline và candidate được xử lý cùng chính sách.

### 15.4. Warmup và steady state

JVM có tiered compilation, class loading, caches và GC behavior thay đổi trong quá trình khởi động. Thời gian warmup cần dựa trên tín hiệu:

- Request throughput/latency ổn định trong nhiều cửa sổ.
- Compiler activity/CPU và cache hit rates dần ổn định.
- DB pools và kết nối ngoài đã sẵn sàng.
- Không còn initialization/background migration bất thường.

Không áp một số giây warmup cứng cho mọi hệ thống. Với **cold-start benchmark**, lại **không nên warmup trước**; mục tiêu chính là đo đường khởi động thật.

## 16. JVM diagnostics và JFR: giải thích tại sao hiệu năng đổi

### 16.1. Bật GC log thống nhất khi chạy performance test

Ví dụ HotSpot trên JDK hỗ trợ unified logging:

~~~bash
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Các output artifacts `gc.log` chỉ là **file do người học tạo khi thực hành**, không phải file Worker phải ghi vào repository này.

Thu thập:

- GC frequency, pause duration, pause p95/p99.
- Allocation rate, heap occupancy trước/sau collections.
- Heap expansion/shrink behavior, remembered set pressure nếu liên quan.
- Object promotion và old-generation behavior theo collector.
- CPU cost của GC, không chỉ số lần GC.
- RSS và native memory nếu heap nhỏ nhưng process vẫn lớn.

**Tham số `-Xlog:gc*` có thể tạo log lớn.** Trên production cần retention/rotation/cấp quyền và test overhead. Nếu app dùng collector khác G1, hãy phân tích theo event và model của collector đó; đừng áp một cách giải thích G1 lên ZGC.

### 16.2. Ghi JFR khi tải đại diện

Ví dụ khi khởi động:

~~~bash
java -XX:StartFlightRecording:filename=migration.jfr,settings=profile,dumponexit=true -jar app.jar
~~~

Hoặc gắn vào JVM đang chạy:

~~~bash
jcmd <pid> JFR.start name=Migration settings=profile duration=120s filename=migration.jfr
jcmd <pid> JFR.check
~~~

Phân tích:

~~~bash
jfr summary migration.jfr
jfr print --events jdk.CPULoad,jdk.GarbageCollection,jdk.JavaMonitorEnter,jdk.SocketRead migration.jfr
~~~

**Tùy JFR profile/settings**, event có thể không được bật, bị threshold hoặc sampling giới hạn. Không kết luận event không tồn tại chỉ từ recording trống khi chưa kiểm tra cấu hình, cửa sổ ghi và tải thực tế.

JFR hỗ trợ tìm hot methods, allocations, GC pauses, monitor contention, IO và nhiều chẩn đoán JVM khác. Khi nghi virtual-thread pinning, có thể xem `jdk.VirtualThreadPinned`; trên JDK 27, **synchronized thông thường không còn tự tạo loại pinning cũ** từ JDK 21–23 do JEP 491.

### 16.3. Một số lựa chọn đo sâu hơn

| Câu hỏi | Công cụ/nguồn |
| --- | --- |
| JDK thực sự chạy và flags? | `jcmd VM.version`, `VM.flags` |
| JVM CPU/GC allocations? | JFR + unified GC logging |
| Thread contention/deadlocks? | JFR monitor events, thread dump |
| Heap object graph/leak? | Heap dump + profiler, cẩn trọng dữ liệu nhạy cảm |
| Native memory pressure? | RSS/cgroups metrics, JDK Native Memory Tracking nếu đã bật phù hợp |
| Compiled vs interpreted hot path? | JFR profile/JIT diagnostics và controlled profiling |
| Network/DB stalls? | Tracing, JDBC pool metrics, socket JFR events |
| Container CPU throttling? | Host/cgroup metrics và quota |
| Runtime image thiếu service? | Module list, service provider checks và integration tests |

**Đừng kết luận GC gây ra mọi p99 spike** chỉ vì thấy GC gần cùng thời điểm. Cần timeline correlation, measurement và loại trừ network/DB/scheduler/lock bottlenecks.

### 16.4. Đối chiếu thay đổi HotSpot mặc định trong Java 27

Theo Release Notes, Java 27:

- Bật **Compact Object Headers** mặc định trên HotSpot (JEP 534). Có thể làm giảm object header footprint; ảnh hưởng tổng heap phụ thuộc object mix, compressed references, alignment và runtime behavior.
- Thay đổi giá trị mặc định một số cờ heap resizing `MinHeapFreeRatio`/`MaxHeapFreeRatio` của G1. Điều này có thể làm cách heap expansion/shrink thể hiện khác baseline khi ứng dụng gọi `System.gc()` hoặc thay đổi workload.
- Có những thay đổi khác về compiler/runtime/GC; xem patch-specific release notes của **đúng build**.

**Tuyệt đối không chép một kết quả benchmark “JDK 27 nhanh hơn X%” từ internet làm expected result của dự án**. Thực tế phụ thuộc tỷ lệ object nhỏ/lớn, compiler warmup, concurrency, CPU cache, heap size và workload.

## 17. Dùng JMH cho microbenchmark đúng cách

**JMH (Java Microbenchmark Harness)** là công cụ của dự án OpenJDK Code Tools, phù hợp khi cần đo một hàm/đường tính toán nhỏ. Nó **không** phải API chuẩn của JDK mà dự án Java nào cũng có sẵn; cần khai dependency/annotation processor theo hướng dẫn JMH.

JMH quan trọng vì JVM có thể thực hiện:

- Dead-code elimination (bỏ tính toán không quan sát được).
- Constant folding/inlining.
- Warmup và tiered compilation.
- Escape analysis/scalar replacement.
- Speculative optimizations và deoptimization.
- Các tối ưu hóa phụ thuộc benchmark state/scope.

Một vòng lặp `System.nanoTime()` tự viết quanh vài lần gọi method **không đủ** để kết luận hiệu năng Java 21 vs 27.

### 17.1. Ví dụ JMH microbenchmark

Tạo một benchmark trong project **đã cấu hình JMH**:

~~~java
package com.example.bench;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
public class NumberParsingBenchmark {
    @Param({"12345", "98765"})
    public String numberText;

    @Benchmark
    public int parseInteger() {
        return Integer.parseInt(numberText);
    }
}
~~~

Điểm đúng:

- `@State(Scope.Thread)` cung cấp state cho benchmark worker thread.
- `@Param` giúp thử nhiều input, tránh một literal compile-time duy nhất trong method body.
- Trả kết quả để JMH có thể tiêu thụ kết quả theo harness, giảm nguy cơ dead-code elimination không đúng ý định.
- Warmup/forks/measurement được khai tường minh, nhưng **các con số 3/5/1 giây chỉ là mặc định ví dụ**, cần điều chỉnh theo độ ổn định.
- Cần cấu hình **JMH annotation processing**/harness đúng cách; chỉ copy class này vào Java project không có JMH dependency **sẽ không compile**.

### 17.2. Chạy JMH trong hai runtime

Theo hướng dẫn OpenJDK JMH, cách phổ biến là **project benchmark riêng** với cấu hình build/annotation processors phù hợp. Sau khi build thành executable benchmark artifact, có thể dùng **cùng artifact** trên hai JVM:

~~~bash
/path/to/jdk21/bin/java -jar target/benchmarks.jar NumberParsingBenchmark
/path/to/jdk27/bin/java -jar target/benchmarks.jar NumberParsingBenchmark
~~~

Đường dẫn `target/benchmarks.jar` là **convention thường gặp của ví dụ JMH Maven archetype**, không phải file tự động có trong mọi project. Hãy xác nhận JMH harness và classpath thực tế.

Khi so sánh:

- Dùng cùng build artifact, benchmark params, forks, warmup và heap/CPU policy.
- Chạy riêng baseline/candidate theo nhiều vòng thay phiên.
- Xem confidence intervals/variance, không chỉ mean.
- Với allocation-sensitive code, bổ sung GC profiling `-prof gc` nếu profile tương thích.
- Nếu microbenchmark nhanh hơn nhưng service throughput không đổi, có thể path đó không phải bottleneck.
- Nếu performance critical là HTTP+DB, cần thêm macro load tests.

## 18. Cách đọc số liệu và kết luận regression

### 18.1. So sánh tỷ lệ, không chỉ số tuyệt đối

Với số đo có cùng đơn vị và workload:

\`LatencyRatio = p95_candidate / p95_baseline\`

\`ThroughputRatio = throughput_candidate / throughput_baseline\`

Ví dụ **minh họa**:

| Chỉ số | Baseline (M0) | Candidate (M4) | Diễn giải |
| --- | ---: | ---: | --- |
| p95 (ms) | 100 | 104 | Ratio 1,04 → tăng 4% |
| p99 (ms) | 220 | 245 | Ratio ≈1,114 → tăng khoảng 11,4% |
| Throughput (req/s) ở saturation | 1.000 | 975 | Ratio 0,975 → giảm 2,5% |
| Peak RSS (MiB) | 800 | 735 | Giảm khoảng 8,1% |
| Error rate | 0,10% | 0,10% | Không tăng trong ví dụ |

Nếu gate đặt `p95≤1,05`, `p99≤1,10`, `throughput≥0,97` thì ví dụ trên **FAIL ở p99**, dù p95, throughput và RSS đạt.

**Lưu ý:** throughput saturation phải đo ở điều kiện xác định giống nhau, còn p95/p99 cần đo tại **cùng offered load**. Không được lấy p99 của hai điểm tải khác nhau để áp ratio.

### 18.2. Sự khác biệt “có ý nghĩa” cần xét variance

Khi các lần chạy có chênh lệch nhỏ:

- Xem từng vòng A/B, không chỉ trung bình gộp.
- Ước lượng độ biến thiên/confidence interval phù hợp với phân bố và độ tự tương quan.
- Với tail latency, cần đủ số request: p99 trên 100 requests không có độ tin cậy hữu ích.
- Các mẫu trong cùng load test **không nhất thiết độc lập**; không báo cáo CI quá hẹp do coi mỗi request là một thí nghiệm độc lập.
- Theo dõi drift của database, network và shared runner.
- Nếu kết luận chưa chắc chắn, phân loại **INCONCLUSIVE** và đo lại trong điều kiện tốt hơn.

Một “cải thiện” 1% với noise ±5% không đủ để nói JDK mới tốt hơn. Ngược lại, lỗi nghiệp vụ hoặc security boundary không được cho qua chỉ vì mẫu latency đẹp.

### 18.3. Gates nên có hai loại

**Hard gates** (fail là dừng):

- Unit/integration/contract/security regression thật.
- Runtime không khởi động hoặc thiếu dependency thiết yếu.
- Unresolved critical security vulnerability không có quyết định chấp nhận rủi ro.
- Data corruption, transaction inconsistency, authentication/authorization sai.
- Không có đường rollback hoạt động trong phạm vi yêu cầu.

**Soft/review gates** (cần chủ sở hữu quyết định):

- Performance regression nhỏ gần noise floor.
- Tăng memory nhưng vẫn trong resource budget.
- Startup chậm hơn trong tình huống ít quan trọng.
- Logs có warning không ảnh hưởng nghiệp vụ nhưng cần remediation trước hạn.
- Tăng GC pause metrics nhưng p99 request không bị ảnh hưởng rõ.

Không biến mọi số đo thành quy tắc if/else thiếu ngữ cảnh. Mỗi exception cần người phê duyệt, lý do, thời hạn và kế hoạch xử lý.

## 19. Gắn ma trận vào CI mà không tạo build xanh giả

CI cần phân biệt **trạng thái của từng ô**, không chỉ kết quả một lệnh `mvn verify`.

### 19.1. Pipeline đề xuất

~~~text
                   Checkout + inventory
                            │
                            ▼
                   Freeze baseline A
                            │
                 ┌──────────┴─────────┐
                 ▼                    ▼
           JDK hiện tại             JDK 27
            M0 (old A)            M1 (old A)
                 │                    │
                 ├──────────┬─────────┤
                 │          │         │
                 ▼          ▼         ▼
             Unit tests  Contracts   Runtime smoke
                 │          │         │
                 └──────────┴─────────┘
                            │
                            ▼
                     Build M3/M4
                            │
                            ▼
                 Tests + security scan
                            │
                            ▼
                   Performance A/B
                            │
                            ▼
                 Compare release gates
                            │
                   ┌────────┴─────────┐
                   ▼                  ▼
                  GO                NO-GO
                   │                  │
                   ▼                  ▼
                 Canary            Fix/retest
                   │
                   ▼
              Production rollout
~~~

Đây là **logic quy trình**, không phải cú pháp YAML của một CI provider cụ thể. Có thể triển khai bằng GitHub Actions, GitLab CI, Jenkins hoặc hệ thống khác, nhưng phải bảo đảm job M1 chạy **đúng artifact A** đã được M0 kiểm chứng.

### 19.2. Pseudocode CI matrix

Ví dụ YAML **mang tính thuật toán**, không phải file cấu hình có thể copy nguyên vào một CI provider:

~~~yaml
jobs:
  - name: baseline
    id: M0
    runtime: "21"
    compiler: "21"
    artifact: "baseline-A.jar"
    steps: [smoke, unit, integration, contract]

  - name: candidate-runtime-only
    id: M1
    runtime: "27"
    compiler: "21"
    artifact: "baseline-A.jar"
    steps: [smoke, unit, integration, contract, performance]

  - name: candidate-rebuild
    id: M4
    runtime: "27"
    compiler: "27"
    release: "27"
    artifact: "candidate-C.jar"
    steps: [compile, unit, integration, contract, security, performance]

  - name: gate-and-report
    dependsOn: [baseline, candidate-runtime-only, candidate-rebuild]
    steps: [collect-results, compare-to-baseline, decide-go-no-go]
~~~

Đối với test suites cần test classes đã biên dịch, job `mvn test` có thể **recompile test sources**, và như vậy không còn runtime-only test tinh khiết. Để chứng minh M1:

1. Build baseline và lưu immutable app **cùng test artifacts**.
2. Jobs M0/M1 chạy lại **chính các artifacts** trên hai runtimes.
3. Job M4 compile/test lại trên JDK 27.
4. Job tổng hợp gắn mọi report vào mã ô tương ứng.

### 19.3. Mỗi job phải xuất metadata

Ví dụ JSON minh họa:

~~~json
{
  "cell": "M1",
  "gitRevision": "REPLACE_WITH_SHA",
  "artifactSha256": "REPLACE_WITH_HASH",
  "runtime": {
    "feature": 27,
    "vendor": "REPLACE_WITH_VENDOR",
    "fullVersion": "REPLACE_WITH_RUNTIME_VERSION"
  },
  "platform": "linux-amd64",
  "suite": "contract",
  "result": "PASS",
  "tests": {
    "passed": 1250,
    "failed": 0,
    "skipped": 0
  },
  "reportId": "REPLACE_WITH_REPORT_REFERENCE"
}
~~~

Một ô có test **SKIPPED** cần lý do và đánh giá ảnh hưởng coverage. Không gán `skipped=0` bằng cách xóa những tests không chạy được trên JDK 27. Phải lưu failures, warnings và tool versions.

### 19.4. Những biến CI cần kiểm soát

- JDK distribution/version, build tool Wrapper và plugins.
- Source revision cùng dependency graph/lock state.
- OS/container base image, CPU/memory quota.
- Database/test services versions và schema fixtures.
- Secret access policy (không đưa secrets vào reports).
- Test feature flags, clock/locale/timezone theo contract.
- JFR/GC logging options và log retention.
- Trình tự chạy suite, test reports và artifact hashes.

Không dùng latest-tag trôi tự do cho benchmark mà không ghi digest/version thực. Khi JDK patch update khác giữa hai lần đo, đó là một biến cần nêu rõ.

## 20. Canary rollout, rollback và dữ liệu trạng thái

Ma trận CI sạch chỉ chứng minh những tình huống đã được kiểm thử. Trước khi triển khai toàn bộ, cần **canary** hoặc rollout theo giai đoạn phù hợp với tính chất dịch vụ.

### 20.1. Ví dụ rollout có điều kiện

~~~text
0% production       Staging / shadow traffic
     │
     ▼
1–5% canary         Theo dõi error, p95/p99, DB, GC, RSS
     │
     ├─ Gate fail → rollback / stop
     │
     ▼
10–25% traffic      Kiểm tra concurrency cao hơn
     │
     ├─ Gate fail → rollback / stop
     │
     ▼
50% → 100%          Phát hành dần + quan sát
     │
     ▼
Post-release soak   Memory leak, jobs, tải theo chu kỳ
~~~

**Các phần trăm chỉ minh họa.** Hệ thống tài chính hoặc migration dữ liệu nhạy cảm có thể cần shadow reads, blue/green hay cơ chế khác để không nhân đôi side effects.

### 20.2. Tránh shadow traffic làm trùng giao dịch

Replay một GET thuần read-only có thể đơn giản; replay trực tiếp POST tạo đơn hàng, gửi email hoặc thanh toán **có thể tạo giao dịch thật lần hai**.

Cần:

- Cô lập state/database hoặc chặn writes trong shadow.
- Sử dụng idempotency keys nếu business contract hỗ trợ.
- Ẩn/giảm thiểu dữ liệu cá nhân được replay.
- Đảm bảo background jobs không tự chạy cùng input hai lần.
- Không dùng production secrets trong môi trường shadow không có quyền tương đương.

### 20.3. Rollback JDK chưa chắc rollback toàn hệ thống

Nếu ứng dụng Java 27 đã:

- Chạy database migration **không tương thích ngược**.
- Ghi message/event schema mới.
- Lưu dữ liệu serialization định dạng khác.
- Thay đổi cache key hoặc encryption behavior.
- Bật feature flag mà bản cũ không hiểu.

...thì chỉ đổi container/JDK trở lại có thể **không** khôi phục chức năng. Để rollback an toàn:

1. Giữ database migration theo **expand-and-contract** nếu có thể.
2. Dùng message/schema evolution tương thích.
3. Xác minh bản cũ đọc được dữ liệu đã ghi bởi candidate.
4. Ghi rõ thứ tự rollback app, flags, traffic và DB.
5. Diễn tập trên staging với dữ liệu sau migration.
6. Chỉ tắt compatibility mode sau rollback window.

### 20.4. So sánh canary đúng cách

Canary thường nhận một phần traffic, dễ có **traffic selection bias**. Nếu baseline nhận request nặng còn candidate nhận request nhẹ, so p95 trực tiếp sẽ sai.

- Phân tầng theo endpoint, tenant, payload size và request class.
- Dùng cùng metric definitions/histogram boundaries.
- So sánh ở workload tương đương.
- Không kết luận về p99 khi canary mới có ít request.
- Theo dõi error budget, GC/RSS, connection pools và throttling.
- Phân biệt cold-start sau rollout với steady state.

**Release gate phải gắn với ảnh hưởng người dùng**, không chỉ “số metrics của JVM tốt hơn”.

## 21. Khi nào cần dừng chuyển đổi?

Quyết định **NO-GO** hợp lệ khi:

- Các đường code chủ chốt khác contract mà chưa được duyệt.
- Có `LinkageError`/`NoClassDefFoundError` chưa giải quyết.
- Agent/framework/driver chưa tương thích Java 27 trên production platform.
- Không chạy được security/integration suite thiết yếu.
- Có nguy cơ mất dữ liệu, double writes, authorization bypass hoặc TLS validation lỗi.
- Không biết bản runtime chính xác nào sẽ được deploy.
- Candidate vượt resource/latency/error SLO ngoài giới hạn.
- Rollback/forward data compatibility chưa được thử.
- JDK vendor không cung cấp support/patch lifecycle theo chính sách production.

**GO WITH CONDITIONS** chỉ phù hợp khi còn những vấn đề không critical, có owner, deadline, monitoring và rollback rõ. Không dùng nó để bỏ qua lỗi correctness/security.

### 21.1. Mẫu biên bản GO/NO-GO

~~~text
Service: orders-api
Current runtime: JDK 21 (vendor/build...)
Candidate runtime: JDK 27 (vendor/build...)
Commit + artifact hash: ...
Build tool/dependencies: ...
Platforms checked: linux-amd64, linux-arm64
Cells completed: M0, M1, M3, M4, M5
Functional tests: PASS (report...)
Security compatibility: PASS (report...)
Performance: p95 PASS / p99 REVIEW / RSS PASS
GC/JFR investigation: ...
Canary plan: ...
Rollback rehearsal: PASS (timestamp...)
Outstanding issues: ...
Decision: NO-GO / GO / GO WITH CONDITIONS
Owners + approvals: ...
~~~

Đây là template, **không phải báo cáo đo lường thật**. Không điền PASS khi chưa có kết quả tương ứng.

## 22. Bảng chẩn đoán regression khi thử JDK 27

| Triệu chứng | Khả năng nguyên nhân | Bằng chứng cần xem |
| --- | --- | --- |
| `UnsupportedClassVersionError` trên runtime cũ | Artifact target `--release 27` (major 71) | `javap -verbose`, runtime version |
| Build plugin/annotation processor lỗi | Tool/plugin chưa đọc được bytecode/API 27 | Plugin versions, errors, changelog |
| Gradle daemon không chạy trên Java 27 | Gradle quá cũ | Compatibility Matrix (9.8.0+), Wrapper |
| JVM báo `Unrecognized VM option` | Flags đã bị loại bỏ | Java 27 removed options/startup logs |
| `NoSuchMethodError`/`NoClassDefFoundError` | Binary mismatch/missing JAR | Runtime classpath/module graph |
| `InaccessibleObjectException` | Reflection vượt JPMS encapsulation | Stack trace, framework version |
| Warning về `final` field mutation | Deep reflection của ORM/serializer/agent | Warning stack, JEP 500 |
| HTTP context routing khác trước | Built-in JDK `HttpServer` path-prefix matching | Route contract tests |
| Locale/timezone formatted khác | CLDR/tzdb/locale defaults | Explicit Locale/ZoneId, fixtures |
| TLS handshake thất bại | Provider/cert/cipher policy | SSL logs và truststore |
| p99 tăng nhưng CPU không tăng | DB, network, lock contention hoặc queue | Traces, JDBC pool và JFR |
| RSS tăng nhưng heap ổn định | Native memory/metaspace/stack | cgroup/RSS, NMT khi có |
| GC pause thay đổi | GC defaults, heap config hoặc workload drift | GC logs/JFR |
| Virtual-thread throughput giảm | Native blocking, downstream saturation, pinning | JFR `jdk.VirtualThreadPinned` |
| Canary tốt nhưng production fail sau nhiều ngày | Soak test thiếu, periodic jobs/leak | Memory trends và schedule |
| Golden tests khác nhưng nghiệp vụ vẫn đúng | Test dựa vào ordering/time không xác định | Contract và snapshot semantics |
| Regression chỉ trên ARM64 | Native lib/JIT/architecture | OS/arch artifacts, platform tests |
| jlink image thiếu API | Runtime modules/providers thiếu | `image/bin/java --list-modules` |

### 22.1. Suy luận nguyên nhân từ các ô ma trận

~~~text
M0 PASS, M1 FAIL
    → Nghi runtime JDK 27, flags, agent, behavior,
      VM/platform/driver compatibility.

M1 PASS, M3 FAIL
    → Nghi compiler 27 target cũ, build tool/plugin,
      hoặc artifact/dependency graph khác.

M3 PASS, M4 FAIL
    → Nghi API/classfile target 27, packaging hoặc
      khác biệt ở target.

M4 PASS, M5 FAIL
    → Nghi library/framework/plugin upgrades.

M0 và M1 đều FAIL
    → Có thể là fixture/CI/baseline issue;
      không tự động quy lỗi cho JDK 27.
~~~

Đây là **heuristic**, không phải chứng minh. Khi có nhiều yếu tố thay đổi, cần thu hẹp bằng artifacts/môi trường được kiểm soát.
## 23. Case study minh họa: chuyển API backend từ Java 21 lên Java 27

Giả sử một dịch vụ:

- Baseline JDK 21, Maven build, PostgreSQL JDBC driver và JSON library.
- Chạy container Linux AMD64, có JVM metrics và distributed tracing.
- API tạo/đọc đơn hàng, background notifications và HTTPS clients.
- Mục tiêu: chuyển runtime Java 27, **chưa áp dụng tính năng Java 27 mới**.

Đây là **tình huống giả định để học phương pháp**, không phải hệ thống đã được đo hoặc triển khai.

### 23.1. Thử M0/M1

1. Lưu `orders-api-A.jar` từ baseline đã qua QA, hash và test artifacts.
2. Chạy chính artifact đó trên JDK 21 → baseline functional/performance.
3. Chạy **cùng JAR** trên JDK 27 → binary/runtime compatibility.
4. Kiểm tra JVM flags, agents, HTTPS, JDBC, JSON, jobs, authorization và routes.
5. Thu logs, JFR, GC và results gắn với mã ô M0/M1.

Nếu M1 lỗi vì agent cũ dùng **JVMCI** (đã bị loại bỏ ở JDK 27), không kết luận application business code sai. Phân loại là **agent/runtime compatibility**, thay đúng agent theo nhà cung cấp và chạy lại M1 với dependency change được ghi rõ.

### 23.2. Thử M3/M4

1. Dùng compiler JDK 27 nhưng giữ `--release 21` ở M3.
2. Chạy artifact M3 trên runtime 21 và 27 nếu phải hỗ trợ cả hai.
3. Chỉ chuyển sang `--release 27` ở M4 khi tất cả deployments đã dùng runtime Java 27.
4. Xem `javap -verbose` để xác nhận class-file major 71.
5. Nếu buộc nâng library/framework, tách change set và chạy M5.

### 23.3. Đo A/B

Giữ một workload có đặc điểm **ví dụ**:

~~~text
HTTP traffic mix: 70% GET, 25% POST, 5% DELETE
Database snapshot: same anonymized fixture
CPU allocation: same 4 vCPU quota
Memory limit: same 2 GiB
Offered load: same controlled arrival profile
GC logs: enabled and retained
JFR: same profile, same recording window
~~~

Các tỷ lệ/cấu hình chỉ là **giả định minh họa**. Bằng chứng thực cần:

- M0 và M1/M4 ở cùng offered load.
- Latency histograms theo endpoint và toàn service.
- GC/RSS/CPU/DB acquisition metrics.
- Số errors/timeouts/retries.
- Nhiều lần chạy A/B để đánh giá noise.

Nếu p99 của M4 vượt ngưỡng nhưng DB connection wait tăng tương ứng, phải kiểm tra **DB/pool/workload variability** trước khi khẳng định JVM JDK 27 gây chậm. Có thể chạy lại với DB snapshot isolated để loại trừ ảnh hưởng bên ngoài.

### 23.4. Rollout

Chỉ triển khai canary sau khi:

- Hard gates đã đạt.
- Không còn critical compatibility issues.
- Có rollback rehearsal và dữ liệu backward-compatible.
- Monitoring phân tách theo runtime version.
- Có owner đủ quyền quyết định dừng/rollback.

Sau khi canary đạt, tăng dần traffic. Nếu p99/DB errors vượt SLO, rollback hoặc dừng theo policy. **Không xóa baseline runtime artifacts** ngay khi rollout 100% nếu rollback window vẫn mở.

## 24. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Chỉ chạy `java -version` rồi chuyển production | Không xác minh app/dependencies | Dùng M0/M1 và full tests |
| Nâng JDK, framework và DB driver cùng lúc | Không xác định được nguyên nhân regression | Tách các giai đoạn |
| Biên dịch lại ngay từ đầu | Mất phép thử runtime-only | Chạy old artifact trên JDK 27 trước |
| Đặt `--release 27` nhưng vẫn deploy Java 21 | JVM 21 không đọc major 71 | Giữ target 21 nếu còn backward support |
| Gradle core hỗ trợ Java 27 nên mọi plugin cũng hỗ trợ | Plugins có ASM/classfile constraints riêng | Xác minh từng plugin/processor |
| Unit tests xanh nên bỏ integration tests | Không bắt được TLS/DB/OS/native issues | Full risk-based coverage |
| Chụp golden outputs từ candidate rồi ghi đè expected | Che behavioral regression | Review delta theo contract |
| So p99 tại hai tải khác nhau | Sai cơ sở thống kê | Cùng offered load; saturation test riêng |
| JMH tốt hơn nên production chắc chắn nhanh hơn | Microbenchmark không phải service load test | Thêm macro tests |
| Một lần đo là đủ | JIT/GC/cache/CPU noise | Warmup, repetitions và A/B blocks |
| Chỉ quan sát heap mà bỏ RSS/native | Container vẫn có thể OOM | Đo JVM + OS/cgroup |
| Copy mọi flags cũ sang JDK 27 | Có flags đã bị loại bỏ | Rà release notes và đo defaults mới |
| Test full JDK nhưng deploy minimal jlink image | Image có thể thiếu modules/providers | Test đúng image được phát hành |
| Đếm skipped tests là PASS | Coverage gap chưa được xử lý | Báo BLOCKED/SKIPPED minh bạch |
| Không kiểm tra rollback DB schema | Rollback app có thể hỏng dữ liệu | Expand/contract và rehearsal |
| Tắt TLS validation để sửa lỗi sau upgrade | Tạo lỗ hổng | Sửa certificate/provider |
| Thấy một JFR event rồi kết luận nguyên nhân | Tương quan chưa đủ | Stack, timeline, metrics và re-run |
| Đánh giá canary khi lượng traffic rất ít | Tail latency thiếu mẫu | Đủ samples/metrics theo tình huống |
| Không lưu artifact/checksum/toolchain | Không thể tái hiện | Immutable artifacts + metadata |
| Trộn migration với áp dụng preview features | Thêm rủi ro không cần thiết | Tách migration khỏi feature adoption |

## 25. Checklist trước khi phê duyệt Java 27

### 25.1. Build và tương thích

- [ ] Đã ghi JDK vendor/build/patch của baseline và candidate.
- [ ] Đã xác minh Maven/Gradle/Wrapper/plugins tương thích Java 27.
- [ ] Nếu dùng Gradle, bản được chọn đạt mốc hỗ trợ JDK 27 và plugins tương ứng.
- [ ] Compiler toolchain/`--release` đúng runtime support policy.
- [ ] M0 artifact được lưu bất biến; M1 chạy chính artifact đó trên Java 27.
- [ ] Đã quét `jdeps --jdk-internals`/`jdeprscan --for-removal` khi phù hợp.
- [ ] Đã loại bỏ JVM options không được Java 27 hỗ trợ.
- [ ] Đã rà class-file major, dependency graph, JNI/native và agents.
- [ ] Đã phân biệt runtime-only/compile/framework-upgrade changes.

### 25.2. Chức năng, bảo mật và hồi quy

- [ ] Unit/component/contract/integration suites đạt trên các ô liên quan.
- [ ] Đã thử DB transaction, JDBC driver, TLS, HTTP routing và serialization.
- [ ] Locale/date/timezone/number formatting được test nếu ứng dụng phụ thuộc.
- [ ] JDK 27 thay đổi trong built-in HttpServer được kiểm tra nếu đang dùng.
- [ ] Warnings về final-field reflection có owner và phương án xử lý.
- [ ] Concurrency/virtual-thread tests không dựa vào arbitrary sleeps.
- [ ] Canary/shadow mode không nhân đôi side effects.
- [ ] Không có regression về data correctness/authentication/authorization.
- [ ] Các ô BLOCKED/SKIPPED có lý do và owner, không được xem là PASS.

### 25.3. Hiệu năng, vận hành và phát hành

- [ ] Benchmark dùng artifacts/hạ tầng/workload có thể so sánh.
- [ ] Có cold start và warm steady-state tests khi liên quan.
- [ ] Đã thu p50/p95/p99, throughput, errors, CPU, RSS, GC.
- [ ] Có JFR/tracing/pool metrics để lý giải regression.
- [ ] Đã lặp lại phép đo hoặc phân tích độ tin cậy với chênh lệch nhỏ.
- [ ] Performance gates được thống nhất **trước** khi đo.
- [ ] Custom runtime image/container được kiểm thử đúng modules/providers.
- [ ] Có kế hoạch canary và monitoring phân tách theo runtime version.
- [ ] Database schema/event payloads còn tương thích trong rollback window.
- [ ] Rollback rehearsal thành công, artifact cũ vẫn truy cập được.
- [ ] JDK update/support lifecycle phù hợp chính sách tổ chức.
- [ ] Quyết định GO/NO-GO có reports và người phê duyệt.

## 26. Tài liệu chính thức và nguồn tham khảo

### Hướng dẫn nâng cấp Java 27

- [Oracle JDK Migration Guide — Release 27](https://docs.oracle.com/en/java/javase/27/migrate/index.html) — quy trình chuyển JDK, removed APIs/tools và compatibility work.
- [Oracle JDK 27 — Preparing for Migration](https://docs.oracle.com/en/java/javase/27/migrate/preparing-migration.html) — thử chạy ứng dụng trước khi compile lại; update libraries và dùng `jdeps`.
- [Oracle JDK 27 — Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html) — Compact Object Headers, final-field warnings và thay đổi cần đo.
- [Oracle JDK 27 — Removed Tools and Components](https://docs.oracle.com/en/java/javase/27/migrate/removed-tools-components.html) — flags/APIs/tooling bị loại bỏ.
- [Oracle JDK 27 — Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html) — API/VM/security/locale/behavior changes và các bug fixes theo release.

### Build tools, phân tích và kiểm thử

- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) — mốc hỗ trợ JDK 27 (9.8.0 trở lên).
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html) — compiler/runtime toolchains.
- [Apache Maven — Compiler Plugin, --release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html) — source/API/class-file target.
- [Java SE 27 — javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) — `--release`.
- [Java SE 27 — jdeps](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html) — internal API/dependency scanning.
- [Java SE 27 — jdeprscan](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeprscan.html) — Java SE deprecated APIs.
- [Java SE 27 — javap](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javap.html) — major version/method descriptors.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) — giải thích thay đổi virtual-thread pinning từ JDK 24.

### Đo hiệu năng và phát hành

- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh) — microbenchmark harness và lưu ý đo.
- [Java SE 27 — JFR API module](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.jfr/module-summary.html) — các API JFR chính thức.
- [Java SE 27 — jcmd](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html) — VM flags/version, JFR và runtime diagnostics.
- [Java SE 27 — jfr](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jfr.html) — đọc JFR recordings.
- [Java SE 27 — java](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — startup flags, unified logging, runtime.

**Kết luận:** Chuyển sang Java 27 an toàn là một **quy trình có bằng chứng**, không phải thao tác đổi `JAVA_HOME`. Hãy **chạy artifact cũ trên runtime mới trước**, lập ma trận build/runtime/OS có truy vết, kiểm thử hồi quy dựa trên contract, đo hiệu năng bằng workload tương đương với JFR/JMH đúng mục đích. Chỉ triển khai canary khi hard gates đạt, những thay đổi tương thích của JDK 27 đã được xét và rollback đã được diễn tập. Mỗi quyết định GO/NO-GO cần gắn với **artifact, phiên bản, kết quả đo và người chịu trách nhiệm**.
