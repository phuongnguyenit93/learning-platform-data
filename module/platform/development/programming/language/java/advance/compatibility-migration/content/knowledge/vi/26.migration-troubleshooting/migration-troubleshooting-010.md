# Khác biệt chỉ xảy ra trong CI hoặc container

Trong quá trình **Java Advance Compatibility Migration**, một tình huống rất thường gặp là cùng một commit chạy tốt trên laptop nhưng lại thất bại trong CI, Docker hoặc Kubernetes. Chẳng hạn unit test pass trên IDE nhưng fail dưới Maven Surefire; ứng dụng khởi động bằng `java -jar` trên host nhưng container báo thiếu class; request HTTPS chạy tốt trên máy cá nhân nhưng ném `SSLHandshakeException` trong image mới; hoặc JDK mới dùng ít heap hơn nhưng pod lại bị `OOMKilled`.

Không thể kết luận “JDK mới lỗi” chỉ vì sự cố xuất hiện sau khi nâng JDK. Môi trường Java bao gồm nhiều thành phần: **JDK launcher, compiler và test fork; framework/dependencies; OS và CPU architecture; base image và native libraries; CPU/memory/PID limits; filesystem; locale/timezone/charset; DNS/proxy/CA/truststore; secrets/config; và lịch chạy test song song**. Một thay đổi ở bất kỳ tầng nào cũng có thể khiến local và CI khác kết quả.

Bài **Khác biệt chỉ xảy ra trong CI hoặc container**, thuộc chương **Chẩn đoán lỗi**, trình bày phương pháp có hệ thống để xác định nguyên nhân: chia lỗi theo giai đoạn, thu fingerprint của process thật, so sánh điều kiện local–CI–container, tái hiện có kiểm soát, sửa đúng tầng và thêm regression test. Mục tiêu không phải “làm CI xanh bằng mọi giá”, mà là có đủ bằng chứng rằng hệ thống tương thích và an toàn trên runtime Java mới.

## 1. Hiểu đúng “local pass, CI fail”

“Local pass” có thể là một trong nhiều kết quả rất khác:
- IDE chạy test bằng JDK 21, trong khi CI chạy JDK 17.
- Developer dùng dependency đã lưu trong Maven/Gradle cache.
- Local chạy profile `dev`, còn CI dùng `test` và Kubernetes dùng `prod`.
- Laptop có database hoặc proxy cục bộ; CI không có.
- Local là macOS/Windows với filesystem không phân biệt hoa thường; CI là Linux.
- Local chạy một test riêng; CI chạy nhiều test forks đồng thời.
- Local có nhiều CPU/RAM; container chỉ được 1 vCPU và 768 MiB RAM.
- Local có CA certificate nội bộ, nhưng Java truststore trong image không có.
- Local x86_64; deployment node là arm64 với native binary khác.

Vì vậy cần thay câu hỏi “tại sao CI sai?” bằng:

> Cùng artifact và cùng dữ liệu, **điều kiện nào khác nhau giữa process thành công và process thất bại**?

### 1.1. Phân loại điểm thất bại trước khi điều tra

| Giai đoạn | Dấu hiệu | Tầng ưu tiên kiểm |
|---|---|---|
| Dependency resolve | 401/403, artifact not found, timeout | Repository, proxy, credentials, cache |
| Compilation | Invalid target release, missing API | Compiler JDK, `--release`, plugin, classpath |
| Test discovery | 0 tests executed, test engine missing | JUnit/Surefire/Gradle runner |
| Test execution | Flaky assertion, thread timeout | Concurrency, clock, data, resources |
| Image build | Package install, platform error | Dockerfile, base image, architecture |
| JVM startup | Unsupported option, class version | Java launcher, VM flags, bytecode |
| Application startup | Bean creation, SSL/JDBC errors | Config, secrets, dependency, network |
| Runtime | OOMKilled, 503, DNS/HTTP failures | Cgroups, networking, downstream |
| Performance | CI chậm, p99 tăng | CPU throttling, GC, load differences |
| Shutdown | Pod bị kill, job trùng | PID 1, SIGTERM, checkpoint, lifecycle |

Phải thu **root-cause stack trace và giai đoạn lỗi**. Dòng cuối “BUILD FAILED” không đủ dữ liệu để chọn giải pháp.

## 2. Lập ma trận khác biệt local–CI–container

Một bảng minh họa:

| Thành phần | Local | CI runner | Container/K8s |
|---|---|---|---|
| JDK của shell | JDK 21 | JDK 17? | Không nhất thiết có shell |
| Compiler JDK | Toolchain 17 | Toolchain 17? | Artifact đã biên dịch |
| Test JVM | IDE JDK 21 | Surefire JDK 17? | Custom test image? |
| OS/architecture | Windows x64 | Linux x64 | Linux arm64? |
| CPU | Nhiều cores | Shared runner | Quota 1 core |
| RAM | 16 GiB | 4 GiB | 768 MiB limit |
| Timezone | Local timezone | UTC | UTC hoặc cấu hình |
| Charset | Theo JDK/OS | UTF-8? | UTF-8? |
| Filesystem | Case-insensitive | Case-sensitive | Có thể read-only |
| Certificates | Corporate CA | Runner CA | JDK truststore của image |
| Network | Proxy/VPN local | CI egress | DNS/service mesh/NetworkPolicy |
| Config | IDE hoặc .env | CI variables | ConfigMap/Secret |
| Concurrency | Test chạy riêng | Parallel forks | Replicas/worker pools |

Dấu hỏi nghĩa là **cần đo**, không được điền theo trí nhớ. Bảng còn cần commit SHA, artifact checksum, Docker image digest và timestamps để tránh so hai lần chạy khác code.

### 2.1. Ba nguồn sai lệch cần tách

1. **Artifact khác**: khác commit, dependency graph, build cache, compiler hoặc generated code.
2. **Runtime khác**: khác Java vendor/build, VM arguments, OS/architecture, native libraries.
3. **Environment khác**: khác quota, file, network, certificates, secrets, timezone hoặc traffic.

Nếu thay cùng lúc JDK, framework và Docker base image, kết quả là một **migration bundle**. Chưa có cơ sở gán mọi lỗi riêng cho JDK.

## 3. Thu fingerprint của đúng process

Trên máy phù hợp:

~~~bash
java -version
which java
uname -a
uname -m
id
pwd
~~~

Các lệnh hữu ích nhưng có giới hạn. `java -version` từ shell của CI chỉ phản ánh executable mà **shell gọi**, không tự chứng minh Maven test fork hoặc JVM trong Kubernetes pod dùng đúng Java đó.

### 3.1. Một probe Java tối giản

~~~java
import java.nio.charset.Charset;
import java.time.ZoneId;
import java.util.Locale;

public final class RuntimeFingerprint {
    public static void main(String[] args) {
        show("java.version", System.getProperty("java.version"));
        show("java.runtime.version",
                System.getProperty("java.runtime.version"));
        show("java.vendor", System.getProperty("java.vendor"));
        show("java.home", System.getProperty("java.home"));
        show("os.name", System.getProperty("os.name"));
        show("os.arch", System.getProperty("os.arch"));
        show("user.dir", System.getProperty("user.dir"));
        show("file.encoding", System.getProperty("file.encoding"));
        show("charset", Charset.defaultCharset().name());
        show("timezone", ZoneId.systemDefault().getId());
        show("locale", Locale.getDefault().toLanguageTag());
        show("processors",
                Runtime.getRuntime().availableProcessors());
        show("maxHeapBytes", Runtime.getRuntime().maxMemory());
        show("pid", ProcessHandle.current().pid());
    }

    private static void show(String key, Object value) {
        System.out.println(key + "=" + value);
    }
}
~~~

Đoạn này dùng `ProcessHandle` (Java 9+) và không cần thư viện ngoài. Khi muốn hiểu **test JVM**, chạy probe trong cùng test fork; khi muốn hiểu **app container**, chạy probe trong runtime image hoặc log allowlist thông tin tương ứng từ application.

Không dump toàn bộ `System.getenv()`, `System.getProperties()` hoặc JVM input arguments lên CI logs công khai: chúng có thể chứa token, password, host nội bộ, key hoặc thông tin cấu hình nhạy cảm. Chỉ in **allowlisted non-secret keys** và redaction nếu cần.

### 3.2. Run manifest có thể tái lập

~~~yaml
runId: "ci-java-migration-001"
commit: "REPLACE_WITH_COMMIT_SHA"
artifactSha256: "REPLACE_WITH_HASH"
imageDigest: "REPLACE_WITH_IMAGE_DIGEST"
jdk:
  vendor: "REPLACE_WITH_VENDOR"
  runtimeVersion: "REPLACE_WITH_BUILD"
buildTool: "REPLACE_WITH_GRADLE_OR_MAVEN_VERSION"
osArchitecture: "linux-amd64"
profile: "test"
resourceLimits:
  cpu: "1"
  memory: "768Mi"
failingStage: "integration-test"
traceReference: "REPLACE_WITH_SAFE_LOG_LINK"
~~~

Đây là mẫu metadata, không phải file của một công cụ mặc định. Hash/version phải lấy từ artifact thật, không dùng placeholder khi kết luận.

## 4. Có thể có nhiều JVM trong một pipeline

Sơ đồ:

~~~text
CI runner
   |
   +-- Maven hoặc Gradle launcher JVM
   |
   +-- Compiler JDK / toolchain
   |
   +-- Unit test JVM fork
   |
   +-- Integration test JVM fork
   |
   +-- Docker application JVM
~~~

Mỗi process có thể dùng Java khác nhau. Một property `JAVA_HOME` ở runner không phải bằng chứng đầy đủ khi Gradle toolchains, Maven Toolchains, container image hoặc IDE config chọn runtime riêng.

### 4.1. Triệu chứng sai Java version

- `UnsupportedClassVersionError`: runtime đang load class file mới hơn khả năng hỗ trợ.
- `invalid target release` hoặc `release version ... not supported`: compiler không hiểu target release.
- `Unrecognized VM option`: VM flag không tồn tại trên JVM đang chạy.
- `ClassNotFoundException`/`NoClassDefFoundError`: thiếu runtime class hoặc API/module.
- `NoSuchMethodError`: binary linkage mismatch, có thể do dependency version chứ không nhất thiết JDK.
- Test pass IDE nhưng CI fail khi mock/final class: có thể test VM hoặc Mockito/Byte Buddy khác.

### 4.2. Kiểm tra class-file version

~~~bash
javap -verbose -classpath target/classes com.example.Main
~~~

Một số mốc:
 
| Java | Class-file major |
|---:|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

`--release 17` giới hạn source/API/class-file target cho code được compiler xử lý, nhưng không tự bảo đảm mọi dependency runtime cũng là Java 17-compatible. Một thư viện bắc cầu được build bằng class-file 65 có thể gây lỗi khi chạy trên JVM 17.

### 4.3. Gradle: daemon, compiler và test launcher

~~~bash
./gradlew --version
./gradlew javaToolchains
./gradlew test --info
~~~

Điều cần đối chiếu:
- JDK chạy daemon.
- `JavaCompile.javaCompiler`.
- `Test.javaLauncher` và `Test.jvmArgs`.
- Custom `integrationTest` tasks/test suites.
- IDE test runner nếu bypass Gradle.
- Plugin và wrapper versions.

Một lỗi chỉ ở CI có thể do CI dùng test launcher Java 17 còn developer chạy test bằng IDE JDK 21, dù build script có toolchain compile 17.

### 4.4. Maven: launcher, compiler và Surefire

~~~bash
./mvnw -version
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Xem compiler plugin `release`/`source`/`target`, Maven Toolchains, Surefire/Failsafe fork configuration, `argLine`, active profiles và effective dependency graph.

`-Dmaven.compiler.release=17` không tự thay JDK đang chạy Maven hoặc Surefire fork. Khi nâng JDK, đừng chỉ sửa compiler target rồi coi tất cả JVM trong pipeline đã chuyển.

## 5. Build image không phải runtime image

Docker multi-stage có thể dùng **JDK đầy đủ** để build rồi **JRE/jlink/runtime image tối giản** để chạy app:

~~~dockerfile
# Ví dụ minh họa; trong production pin image digest.
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace
COPY . .
RUN ./mvnw -B -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/target/app.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Dockerfile mẫu cần điều chỉnh tên artifact, file permissions, dependency caching và security profile. `-DskipTests` trong build stage **không chứng minh** test đã pass; nếu dùng, test phải chạy ở bước pipeline khác.

Khác biệt dễ gây lỗi:
- Runtime image thiếu `javac`, `jar`, `jcmd`, `bash`, `curl`.
- Runtime image không có CA certificate/truststore phù hợp.
- Thư viện native tồn tại ở build stage nhưng không được copy vào runtime.
- User non-root không đọc/ghi được file cần thiết.
- `WORKDIR` khác local path.
- Multi-platform build tạo image sai architecture.
- JRE là version/vendor khác JDK build.

Dùng **final image thực sự deploy** để tái hiện, không chỉ chạy ứng dụng từ `target/classes` trên host.

## 6. OS, CPU architecture, libc và native code

Java bytecode có tính portable nhưng nhiều ứng dụng dùng native components: JNI/JNA, Netty native transport, RocksDB, compression, SQLite, crypto provider, media tools hoặc các executable bên ngoài JVM.

### 6.1. x86_64 so với arm64

Ví dụ:
- Laptop dùng x86_64.
- CI node chạy arm64.
- Dependency chỉ chứa `linux-x86_64` native binary.

Có thể gặp:

~~~text
java.lang.UnsatisfiedLinkError:
  no some_native_lib in java.library.path
~~~

hoặc:

~~~text
Exec format error
~~~

Cần so `os.arch`, `uname -m`, image manifest architecture và native dependency classifier. Thêm `java.library.path` không giúp JVM chạy binary sai CPU architecture.

### 6.2. Alpine/musl so với glibc

Alpine Linux thường dùng musl libc; nhiều thư viện native Java được đóng gói cho glibc. Có thể build Java source thành công nhưng runtime không load được JNI.

Các hướng:
- Chọn native dependency có hỗ trợ musl.
- Chọn base image glibc khi phù hợp.
- Kiểm tra JNI provider, native classifier, ABI.
- Chạy test trên image/arch mục tiêu.
- Không copy bừa thư viện hệ thống rồi bỏ qua provenance/security updates.

### 6.3. Jlink image thiếu module

Runtime image tạo bằng `jlink` có thể thiếu module:
- `java.sql` (JDBC).
- `java.naming` (JNDI).
- `java.management` và monitoring.
- `java.instrument` nếu một agent cần.
- Module JDK khác dùng bởi thư viện/framework.

Thử startup và integration test trên image cuối. `jdeps` hỗ trợ phân tích tham chiếu tĩnh, nhưng không bao phủ mọi reflective loading, plugin discovery hoặc service provider trong runtime.

## 7. Container CPU quota và hiệu ứng timeout

Một bài test có thể chạy nhanh trên laptop nhưng rất chậm trong CI khi CPU hạn chế. Các nguyên nhân:
- CPU quota 1 vCPU trong khi JVM sinh nhiều threads.
- GC/JIT compiler chiếm CPU trong warm-up.
- Test forks tranh quota.
- Node có noisy neighbors.
- Kubernetes CPU throttling.
- CPU architecture khác có instruction throughput khác.

### 7.1. Cores của host không bằng quota container

Host có 32 cores không có nghĩa một pod được phép dùng 32 cores. JVM phiên bản mới thường nhận diện container limits, nhưng behavior phụ thuộc vendor/JDK update và cgroups v1/v2.

Trong môi trường Linux có cgroups v2:

~~~bash
cat /proc/self/cgroup
cat /sys/fs/cgroup/cpu.max
cat /sys/fs/cgroup/memory.max
~~~

Nếu file không tồn tại có thể container đang dùng cgroups v1 hoặc mount khác; không kết luận “không có limit” ngay.

Đối chiếu:
- `Runtime.availableProcessors()`.
- CPU requests/limits và cpuset.
- CPU usage theo core-seconds.
- CPU throttled periods/time.
- Thread count, executor queues và latency.
- Test concurrency/fork settings.

### 7.2. -XX:ActiveProcessorCount để thử một giả thuyết

Trên HotSpot phù hợp, `-XX:ActiveProcessorCount=N` có thể giới hạn số processors JVM báo để điều chỉnh một số ergonomics. Đây có thể là **phép thử có kiểm soát**, không phải biện pháp production nên áp dụng mù quáng. Nếu thay option, cần ghi rằng cấu hình JDK đã thay và chạy benchmark lại trên workload/limits thực.

## 8. Memory: phân biệt Java OOME và OOMKilled

Một pod bị kill khi heap chưa đầy không hẳn là bug GC. Java process dùng nhiều loại memory:

~~~text
JVM process memory
   |
   +-- Java heap
   +-- Metaspace / class metadata
   +-- Code cache
   +-- Thread stacks
   +-- Direct buffers / off-heap caches
   +-- JNI/native allocations
   +-- Runtime internal structures
~~~

Một container có memory limit 1 GiB nhưng đặt `-Xmx1g` có thể vượt limit vì không để headroom cho non-heap/native memory.

| Hiện tượng | Khả năng cần kiểm |
|---|---|
| `OutOfMemoryError: Java heap space` | Heap limit, allocation pressure, leaks |
| `OutOfMemoryError: Metaspace` | Classloading/metaspace cap |
| `OutOfMemoryError: Direct buffer memory` | NIO/direct allocations |
| `unable to create native thread` | Native memory, PID/thread limit |
| Exit 137 | SIGKILL; **có thể** OOM kill |
| Pod reason `OOMKilled` | Container memory vượt policy/limit |
| RSS tăng, heap ổn định | Native/direct/thread allocations hoặc page accounting |

**Exit 137 không tự chứng minh OOM**: cần xem Pod status, container events, cgroup counters và logs.

### 8.1. JDK ergonomics ảnh hưởng max heap

Nếu không pin `-Xmx`, JVM có thể tự chọn heap dựa trên memory limit/JDK flags. Khi nâng runtime, max heap có thể đổi. So:
- JDK vendor/build.
- `-Xms`, `-Xmx`, `-XX:MaxRAMPercentage` hoặc flags tương ứng.
- `Runtime.maxMemory()`.
- Heap used/committed/max.
- RSS/container working set.
- GC logs và thread counts.

Không tuyên bố “JDK mới leak” chỉ vì RSS tăng nếu heap sizing, allocation rate hoặc workload cũng thay.

### 8.2. Native Memory Tracking

Trên HotSpot hỗ trợ:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Khi `jcmd` có mặt và quyền cho phép:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

NMT có overhead và không phản ánh mọi native allocation bên ngoài JVM; cần hiểu giới hạn. Nếu runtime image tối giản không có `jcmd`, có thể dùng image debug tương đương khi được phép và ghi rõ điều kiện khác.

## 9. PID limit, ulimit và thread starvation

Một CI runner có thể giới hạn số process/PID thấp hơn laptop, trong khi JUnit test parallel, Maven forks, Gradle workers hoặc server thread pools tạo nhiều threads.

Các dấu hiệu:
- `OutOfMemoryError: unable to create native thread`.
- Test treo vì executor không có worker.
- Port/socket/file descriptor exhausted.
- Container không spawn subprocess.
- JVM/JIT/GC threads đẩy process gần PID limit.

Kiểm tra PID cgroup, thread count, file descriptor limit, executor queue, fork count và native memory. Không chỉ tăng `-Xmx`; heap limit không giải quyết được mọi resource limit.

### 9.1. Virtual threads không loại bỏ mọi giới hạn

Trên JDK hỗ trợ virtual threads, ứng dụng có thể có nhiều virtual threads nhưng vẫn dùng carrier/platform threads, sockets, direct memory và downstream connection pools. Nếu đổi concurrency model khi nâng JDK, đó là thay đổi hành vi/tài nguyên **thêm ngoài việc đổi Java runtime**. Cần test trên container quota thật.

## 10. Filesystem: case sensitivity, paths và working directory

### 10.1. Case-sensitive paths

Một test:

~~~java
getClass().getResourceAsStream("/fixtures/Order.JSON");
~~~

nhưng file có tên:

~~~text
src/test/resources/fixtures/order.json
~~~

có thể hoạt động ở một filesystem case-insensitive và fail trên Linux. Cách sửa là thống nhất tên, không giả định OS tự sửa case.

### 10.2. Relative paths

~~~java
new java.io.File("config/orders.yml");
~~~

phụ thuộc `user.dir`. IDE có thể đặt working directory ở repository root; Docker `WORKDIR` lại là `/app`. Maven multi-module test task còn có thể dùng module dir.

Nếu file là resource trong JAR, ưu tiên classpath resource. Nếu là external config, quy định absolute path/mount. Temp file nên dùng API tạo path riêng và cleanup.

### 10.3. Non-root, read-only filesystem

Khi chuyển image chạy root sang non-root:
- `/app/logs` có thể không ghi được.
- Temp directory không tồn tại/writable.
- Native library extraction thất bại.
- File keystore không đọc được.
- Shell entrypoint thiếu executable bit.
- User home/caches không writable.

Trong Kubernetes, `readOnlyRootFilesystem: true` cũng có thể khiến application/framework không ghi được file tạm.

Hướng xử lý:
- Tạo đúng writable temp volume.
- Chọn UID/GID và ownership phù hợp.
- Ghi log ra stdout/stderr khi có thể.
- Đặt `java.io.tmpdir` có chủ đích nếu cần.
- Không chuyển production container trở lại root chỉ để che lỗi phân quyền.

### 10.4. Line endings và Git checkout

Windows có thể dùng CRLF; Linux scripts thường cần LF. Một entrypoint có thể fail với:

~~~text
/bin/sh^M: bad interpreter
~~~

Kiểm Git line-ending policy, executable bit, shebang và cách đóng gói file. Với fixtures dùng để kiểm binary compatibility, so SHA-256 của **bytes thật**, không chỉ diff nội dung hiển thị.

### 10.5. Port collision

Test hard-code port 8080 có thể pass local nhưng fail CI khi nhiều workers chạy song song. Dùng port 0/random host port mapping thông qua web/test framework; tránh cách “mở socket lấy số port rồi đóng trước khi server bind” vì có race.

## 11. Charset, locale và timezone

Local chạy ở một timezone/locale, CI thường dùng UTC hoặc locale mặc định khác. Một test liên quan ngày, tiền tệ hoặc Unicode có thể thất bại dù nghiệp vụ không đổi.

### 11.1. JEP 400: default charset

JDK 18 chuẩn hóa default charset thành UTF-8 trong nhiều tình huống thông thường theo JEP 400. Code:

~~~java
String text = new String(bytes);
~~~

có thể cho kết quả khác khi legacy files dùng encoding khác. Hãy chọn explicit charset theo **format contract**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String text = Files.readString(
        Path.of("fixtures/order.txt"),
        StandardCharsets.UTF_8
);
~~~

Nếu dữ liệu cũ vốn dùng Windows-1252, cần đọc bằng charset đó theo hợp đồng. Không dùng UTF-8 mù quáng chỉ vì JDK mới mặc định như vậy.

### 11.2. Clock và timezone

Test dễ lỗi:

~~~java
assertEquals("2026-11-12",
        java.time.LocalDate.now().toString());
~~~

Khi chạy gần nửa đêm hoặc trên UTC, kết quả có thể khác. Inject `Clock`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

Clock clock = Clock.fixed(
        Instant.parse("2026-11-12T00:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh")
);

LocalDate date = LocalDate.now(clock);
~~~

Contract có thể lưu instant ở UTC nhưng tính business day theo timezone cụ thể. Không mặc định “mọi thứ phải UTC” khi nghiệp vụ cần local date.

### 11.3. Locale và Unicode

Thay locale mặc định có thể ảnh hưởng:
- Decimal/grouping separators.
- Date format.
- Upper/lowercase.
- Resource bundles.
- Sorting/collation.
- Unicode normalization.

Với identifiers không phụ thuộc ngôn ngữ, thường dùng `Locale.ROOT` cho case conversion khi phù hợp. Với văn bản người dùng, cần xử lý đúng locale/Unicode semantics theo nghiệp vụ.

## 12. TLS, truststore và CA certificates

Nếu host HTTPS chạy được trên laptop nhưng trong container ném:

~~~text
javax.net.ssl.SSLHandshakeException
PKIX path building failed
unable to find valid certification path
~~~

có thể do:
- Corporate CA chỉ được cài trên host.
- Java truststore trong image thiếu CA.
- Server gửi certificate chain chưa đủ.
- Hostname/SAN không khớp.
- TLS protocol/cipher defaults khác.
- Certificate expired hoặc clock lệch.
- mTLS client certificate/keystore chưa được mount.
- Service mesh/proxy chặn hoặc thay endpoint.

### 12.1. Java truststore khác OS CA bundle

Tùy Java distribution, Java TLS có thể dùng truststore riêng hoặc có cơ chế tích hợp với OS store. Không thể khẳng định `curl` thành công là `HttpClient`/JDBC TLS cũng thành công.

Kiểm:
- `java.home` và Java truststore path.
- `javax.net.ssl.trustStore`/`trustStoreType` khi được cấu hình.
- CA chain và hostname.
- Proxy, SNI/ALPN/mTLS.
- JDK security policy và certificate validity.

**Không dùng TrustManager tin mọi certificate, không bỏ hostname verification** để làm CI xanh. Cần cấp đúng CA/keystore theo policy.

## 13. DNS, proxy, network policy và localhost

Trong Docker, `localhost` trỏ vào network namespace của container, không tự trỏ tới host database hay service của container khác.

Ví dụ local config:

~~~text
jdbc:postgresql://localhost:5432/orders
~~~

có thể fail CI khi PostgreSQL chạy ở service `postgres` hoặc một pod khác. Dùng địa chỉ service name đúng topology.

Các yếu tố khác:
- Kubernetes DNS search domains.
- IPv4/IPv6 resolution.
- `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`.
- Java `http.proxyHost`, `https.proxyHost`, `http.nonProxyHosts`.
- NetworkPolicy và egress firewall.
- Sidecar/service mesh và mTLS.
- Load balancer/ingress routing.

### 13.1. Proxy env không mặc định áp dụng mọi Java HTTP client

Một số CLI đọc `HTTPS_PROXY`; Java client có thể dựa vào JVM properties hoặc ProxySelector. Không suy rằng `curl` pass đồng nghĩa Java pass. So **chính HTTP client implementation** của ứng dụng.

### 13.2. Bảng lỗi mạng

| Dấu hiệu | Tầng ưu tiên kiểm |
|---|---|
| `UnknownHostException` | DNS |
| `ConnectException: Connection refused` | Host/port/listener |
| `SocketTimeoutException` | Network/server latency/timeout |
| `SSLHandshakeException` | TLS CA/hostname/protocol/mTLS |
| HTTP 401/403 | Authentication/authorization |
| HTTP 407 | Proxy authentication |
| HTTP 429/503 | Rate limit/upstream capacity |
| HTTP 502/504 | Gateway/upstream failure |

Đọc nested root cause và thời điểm lỗi trước khi chọn giải pháp.

## 14. Secrets, profiles và property precedence

Local thường có `.env`, IDE run configuration hoặc credential helper; CI sử dụng runner secrets; Kubernetes dùng Secret/ConfigMap.

Các triệu chứng:
- API trả 401 vì token không được cấp.
- Framework không bật đúng profile.
- Application chọn DB embedded thay DB dự kiến.
- Cấu hình mTLS certificate path thiếu mount.
- Feature flag khác dẫn đến auto-configuration khác.
- Config placeholder sử dụng default không mong muốn.

### 14.1. Kiểm sự hiện diện, không in giá trị bí mật

~~~java
String token = System.getenv("PAYMENT_API_TOKEN");
if (token == null || token.isBlank()) {
    throw new IllegalStateException(
            "PAYMENT_API_TOKEN is required"
    );
}
~~~

Lỗi có thể ghi **tên biến thiếu**, không log token. Khi diagnostic, kiểm source precedence và effective value của **non-secret keys** cần thiết.

### 14.2. Đọc đúng framework version

Spring Boot và các framework khác có nhiều property sources. Thứ tự ưu tiên có thể thay theo version và config-data mechanism. Cùng một `application.yml` không đảm bảo cùng effective config khi environment variables, command-line args hoặc remote config khác.

Một bài chẩn đoán nên ghi:
- Active profiles.
- Những config sources đã nạp.
- Non-secret effective values.
- Property names đã đổi/deprecated khi nâng framework.
- Bean/auto-configuration conditions trong runtime.
- Secrets có mặt hay không, không tiết lộ values.

## 15. Dependency cache và build reproducibility

Local có thể dùng artifact trong `~/.m2` hoặc Gradle cache, còn CI clean runner phải resolve từ repository. Điều này làm lộ:
- Unpublished local `mvn install` dependency.
- SNAPSHOT version khác.
- Dynamic version range resolve khác.
- BOM/plugin/transitive graph khác.
- Artifact repository credentials thiếu.
- Proxy/mirror trả kết quả khác.
- Cache cũ che lỗi class-file version.

### 15.1. So dependency graph

~~~bash
./mvnw dependency:tree
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency byte-buddy \
  --configuration testRuntimeClasspath
~~~

Đây là lệnh hướng dẫn cho dự án thực, không phải hoạt động cần chạy khi soạn bài. Pin versions và locks/checksums theo build policy. Đừng so code dependency declarations mà bỏ qua **resolved dependency versions**.

### 15.2. Tắt cache chỉ để khoanh vùng

Chạy clean build hoặc Gradle `--no-build-cache` có thể giúp kiểm chứng giả thuyết, nhưng xóa cache mọi lần không phải fix nguyên nhân. Có thể tăng thời gian build và tạo network variability. Nên giữ cache keys theo tool/JDK, dependency verification, version locking và artifact provenance.

## 16. Test runner: pass local vì không chạy cùng test suite

Một ứng dụng có thể:
- IDE chạy JUnit 5.
- CI Maven Surefire quá cũ không discover đúng engine.
- Gradle thiếu `useJUnitPlatform()`.
- Integration tests thuộc Failsafe nhưng pipeline chỉ chạy Surefire.
- CI chỉ report một số test do includes/tags/excludes.
- Coverage Java agent hoặc Mockito agent không được truyền vào test fork.

**BUILD SUCCESS với 0 tests không phải bằng chứng tương thích.**

### 16.1. Gradle và JUnit Platform

~~~kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

Ví dụ áp dụng cho Gradle Kotlin DSL có JUnit 5 engine phù hợp. Cần kiểm custom test suites/tasks và resolved test runtime classpath.

### 16.2. Maven Surefire/Failsafe

Kiểm plugin/provider versions, forks, test includes/excludes và `argLine`. Nếu JaCoCo và Mockito cùng cần `-javaagent`, không ghi đè `argLine` một cách vô ý khiến agent khác biến mất.

## 17. Race conditions và flaky tests

CI có thể chạy song song hơn hoặc bị CPU throttling, khiến bug về timing/ordering lộ ra.

### 17.1. Không dùng sleep cố định để đợi async completion

Tránh:

~~~java
Thread.sleep(100);
assertEquals("DONE", task.status());
~~~

Trên CI 1 vCPU, task có thể chưa được schedule. Ưu tiên future, latch hoặc condition polling với deadline hữu hạn:

~~~java
String result = future.get(
        5, java.util.concurrent.TimeUnit.SECONDS
);
assertEquals("DONE", result);
~~~

Ví dụ giả định `future` đã được tạo. Đây không phải giấy phép tăng timeout vô hạn: nếu có deadlock hoặc queue starvation, cần thread dump và nguyên nhân thật.

### 17.2. Global mutable state

Test đặt `System.setProperty` hoặc thay static singleton có thể fail khi chạy song song. Mặc dù try/finally restore value giúp giảm leak ở test tuần tự, **system properties vẫn là shared global state**; nên inject config hoặc cô lập process nếu cần test thay đổi global state.

### 17.3. File và port collisions

Nếu hai test cùng viết `/tmp/output.json` hoặc bind port 8080, một test có thể xóa/chiếm tài nguyên của test kia. Dùng unique temp directories và test server port 0.

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ExportTest {
    @TempDir Path temporaryDirectory;

    @Test
    void writesInIsolatedDirectory() throws Exception {
        Path output = temporaryDirectory.resolve("out.txt");
        Files.writeString(output, "OK");
        assertEquals("OK", Files.readString(output));
    }
}
~~~

Container vẫn cần writable temp volume nếu root filesystem read-only. Đừng chọn random port bằng cách bind rồi đóng socket trước khi service thực bind: có race.

### 17.4. Test order và random

Không dựa vào iteration order của `HashMap` nếu contract không bảo đảm thứ tự. Với randomized tests, ghi seed để tái hiện. Nếu test date/time, dùng injected Clock. Khi test đầy đủ suite, kiểm môi trường cleanup để không rò state giữa test classes.

## 18. Mockito, Byte Buddy và Java agent

Một test có thể fail trên JDK/container mới khi Mockito inline mock maker hoặc Byte Buddy không khởi tạo được.

Cần phân biệt:
- Byte Buddy version có hiểu class-file version của JDK mới?
- Mockito version có hỗ trợ JDK/test runtime không?
- Test cần inline mock (final/static/constructor) hay subclass mock?
- Agent được cấu hình lúc startup hay dùng self-attach?
- JVM có policy hạn chế dynamic attach?
- Agent JAR có tồn tại tại path của **test fork** trong container?
- `-javaagent` có vô tình đặt ở build JVM thay vì test JVM?

JDK 21 bắt đầu cảnh báo dynamic agent loading theo JEP 451 trong môi trường phù hợp. **Không khẳng định mọi JDK 21+ đều đã chặn dynamic attach theo mặc định**; chính sách phụ thuộc release/vendor. Với Mockito version hỗ trợ, startup `-javaagent` vào JVM test là cách rõ hơn việc dựa vào self-attach.

### 18.1. JPMS khác agent attachment

`InaccessibleObjectException` có thể do reflective access tới module/package không open. `--add-opens` là một biện pháp giới hạn theo package/target, không sửa thiếu Java agent, bytecode tooling version hay API đã bị xóa.

Đừng copy rộng các `--add-opens` từ IDE config sang production `JAVA_TOOL_OPTIONS` mà chưa xác minh thư viện nào cần và rủi ro bảo mật.

## 19. Docker entrypoint và process lifecycle

App chạy đúng bằng:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

nhưng không chắc chạy đúng trong Docker nếu ENTRYPOINT/CMD quoting sai.

### 19.1. Exec form

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Dạng này cung cấp argv rõ ràng và thường giúp Java process nhận signals trực tiếp.

### 19.2. Shell form

~~~dockerfile
ENTRYPOINT java -jar /app/app.jar
~~~

Shell có thể đứng trung gian, làm quoting/variable expansion và signal handling khác. Nếu dùng shell entrypoint, cần `exec` với argv được xử lý an toàn; không ghép một chuỗi shell command từ untrusted values.

### 19.3. SIGTERM và graceful shutdown

Kubernetes thường gửi SIGTERM, chờ grace period rồi SIGKILL. Nếu Java không nhận signal hoặc job không checkpoint đúng, deployment có thể tạo duplicate processing.

Test:
- Entrypoint/PID tree.
- Readiness trước khi nhận traffic và khi shutdown.
- Termination grace period.
- Executor/HTTP server stop.
- Message offset/checkpoint/idempotent restart.

`JAVA_TOOL_OPTIONS` có thể tác động nhiều Java processes trong container, kể cả tooling; cần xác minh đúng scope của flags.

## 20. Clock skew, certificate validity và distributed state

Timezone không giống clock skew:
- **Timezone** là cách biểu diễn giờ địa phương.
- **Clock skew** là chênh lệch thời gian thật giữa hai host.
- **Monotonic clock** dùng để đo khoảng thời gian.
- **Wall clock** dùng cho token/certificate expiration.

JWT `nbf`/`exp`, signed requests và TLS certificate validation có thể fail nếu clock container host lệch. Thay `TZ` không sửa clock skew. Khi unit test cần kiểm expiry, inject Clock fixed; khi integration test, quan sát timestamp của cả issuer và verifier cùng host time sync.

## 21. Testcontainers và Docker-in-Docker

Testcontainers có thể pass laptop nhưng fail CI vì:
- Docker daemon/socket không có.
- Runner thiếu quyền.
- Docker-in-Docker chưa cấu hình.
- Rootless Docker hoặc network policy khác.
- Registry auth/rate limit.
- Image sai architecture.
- Database container chưa ready.
- Cleanup sidecar bị chặn.
- Nested container không kết nối host-mapped ports.

Nếu Testcontainers không tạo được DB container, **application JDBC logic chưa được kiểm tra**. Đừng sửa Hibernate chỉ để chữa lỗi Docker socket.

Nên ghi:
- Docker provider/host.
- Runner permissions và security policy.
- Testcontainers version.
- Image digest.
- Network/port mapping.
- Health/readiness strategy.
- Cleanup và parallelism.

Không cấp `--privileged` hoặc mount Docker socket vào mọi CI job mặc định; quyền Docker là quyền nhạy cảm. Dùng runner được phê duyệt.

## 22. CI timeout và retries

Timeout có thể do:
- CPU throttling hoặc thiếu threads.
- JIT warm-up/cache cold.
- Slow image pulls/registry.
- Network/proxy/dependency.
- Deadlock/connection pool starvation.
- CI job time limit quá nhỏ.
- Test chờ external service không được khởi tạo.

Tăng timeout một chút có thể giúp quan sát, nhưng **không sửa nguyên nhân** nếu có deadlock hoặc unbounded retries. Cần thread dump, queues, timestamps, CPU/memory và dependency latency.

Retries nên áp dụng cho lỗi transient được xác định, có số lần/backoff, có idempotency và không che flaky assertion. Không retry toàn bộ test suite vô hạn cho tới khi xanh.

## 23. Quy trình chẩn đoán từng bước

~~~text
Bước 1: Phân loại lỗi
          |
          v
Bước 2: Thu logs + fingerprint
          |
          v
Bước 3: So artifact/JDK/image/config/resources
          |
          v
Bước 4: Xây giả thuyết có thể kiểm chứng
          |
          v
Bước 5: Tái hiện với thay đổi một biến/lần
          |
          v
Bước 6: Xác nhận root cause
          |
          v
Bước 7: Sửa đúng tầng
          |
          v
Bước 8: Test regression trên CI/container target
~~~

### 23.1. Bước 1: thu lỗi gốc

Ghi:
- Stage, command, exit code.
- Full exception chain và test name.
- Pod/container termination reason khi liên quan.
- Lần cuối pass, lần đầu fail.
- Có lặp lại được hay flaky?
- Ảnh hưởng chỉ một runner/node hay tất cả?
- JDK, app, image, dependency versions.

### 23.2. Bước 2: xác minh artifact

- Commit SHA có giống không?
- JAR/build output checksum?
- Dependency graph đã resolve?
- Docker image digest/architecture?
- Generated code và resources có nằm trong artifact?
- Runtime JDK có đủ class-file/module support?

Nếu artifact khác, phải chốt build reproducibility trước khi so JVM behavior.

### 23.3. Bước 3: xác minh JVM

- Build launcher vs compiler toolchain vs test fork.
- App runtime `java -version` trong image.
- VM options, heap flags, Java agent.
- OS/arch/libc.
- Class-file major và API compatibility.

### 23.4. Bước 4: xác minh environment

- CPU/RAM/PID limits.
- Non-root/read-only permissions.
- Working directory và path case.
- Locale/timezone/charset.
- DNS/proxy/CA.
- Secret presence/active profiles.
- Network and downstream readiness.

### 23.5. Bước 5: thử một giả thuyết

Ví dụ:
- Cố định timezone với test Clock.
- Chạy container cùng CPU quota.
- Thử đúng image ARM64 trên ARM64 node.
- Thêm CA vào Java truststore đúng policy.
- Chạy test tuần tự để xem race xuất hiện/biến mất.
- Pin dependency để loại ảnh hưởng cache.
- Chạy với/không có agent ở test fork, đúng version.

**Một phép thử chỉ có giá trị nếu điều kiện thay đổi được ghi rõ.** Tránh đồng thời nâng library, đổi image và tăng RAM rồi cho rằng đã tìm được root cause.

### 23.6. Bước 6–8: fix và bảo vệ hồi quy

Sửa tại đúng tầng, tạo regression evidence tương ứng:
- Wrong Java runtime → pin toolchain/runtime.
- Encoding → explicit charset.
- Timezone → injected Clock/business zone.
- Path → classpath resource/unique temp dir.
- CPU quota → sizing/concurrency, test at limits.
- JNI arch → native variant phù hợp.
- TLS → CA/truststore và integration test.
- Flaky test → isolation/synchronization.
- Missing dependency → lock/verification.
- Incorrect agent placement → test JVM configuration.

## 24. Tái hiện với final container image

Một lệnh minh họa:

~~~bash
docker run --rm \
  --cpus=1 \
  --memory=768m \
  --read-only \
  --tmpfs /tmp:rw,nosuid,size=128m \
  --user 10001:10001 \
  -e TZ=UTC \
  registry.example/orders:PINNED_TAG
~~~

Mẫu này chỉ áp dụng nếu image hỗ trợ read-only, UID, temp mount và không cần network/volumes khác. Dùng test credentials riêng, **không dùng production secrets** để reproduction local.

### 24.1. Vì sao Docker local vẫn khác Kubernetes?

Ngay cả khi image giống nhau:
- Node CPU architecture/noisy neighbors có thể khác.
- Service mesh và NetworkPolicy khác.
- DNS/search domains khác.
- Secret/volume permissions khác.
- Pod probes, resource policies, HPA khác.
- Storage performance và backend latency khác.

Docker local giúp khoanh vùng, không thay staging/cluster integration verification.

### 24.2. Pin image digest

`latest` tag có thể đổi. Run manifest phải lưu image digest, JDK build, artifact hash và deployment flags. Nếu baseline/candidate đổi cả base image, kết luận cần ghi rõ rằng đó là **JDK + image migration**, chưa cô lập riêng JVM.

## 25. Bảng chẩn đoán nhanh

| Triệu chứng chỉ xảy ra CI/container | Nguyên nhân cần kiểm |
|---|---|
| `UnsupportedClassVersionError` | Runtime JDK thấp hơn class file |
| `invalid target release` | Compiler JDK/toolchain sai |
| `Unrecognized VM option` | JVM flag/vendor/version không hỗ trợ |
| `ClassNotFoundException` | Runtime classpath/module thiếu |
| `NoSuchMethodError` | Binary dependency/API mismatch |
| `UnsatisfiedLinkError` | Native library sai arch/libc/path |
| `Exec format error` | OS architecture của binary/image sai |
| `InaccessibleObjectException` | JPMS opens/reflective access |
| Mockito inline fail | Byte Buddy/agent/test JVM mismatch |
| JUnit chạy 0 tests | Engine/provider/excludes |
| CI test timeout | Throttling, network, race, queue |
| `unable to create native thread` | PID/thread/native memory limit |
| Exit 137 / `OOMKilled` | Cgroup memory/SIGKILL |
| `OutOfMemoryError: Java heap space` | Heap pressure/leak |
| FileNotFoundException | Workdir/mount/case/resource |
| Permission denied | Non-root/read-only filesystem |
| `UnknownHostException` | DNS/network |
| `SSLHandshakeException` | CA/truststore/TLS/mTLS |
| HTTP 401/403 | Env/secret/auth policy |
| JSON/text khác | Charset/default mapper |
| Date assertion lệch | Timezone/locale/clock |
| Local dependency có, CI thiếu | Cache/repository/unpublished artifact |
| Testcontainers không khởi tạo | Docker runner/permissions/network |
| p99 cao trong container | CPU quota/GC/DB/traffic |
| SIGTERM không cleanup | Entrypoint/PID 1/shutdown hook |

Bảng này giúp chọn **phép điều tra đầu**, không chứng minh quan hệ nguyên nhân chỉ từ một loại exception.

## 26. Tình huống 1: IDE pass, CI chạy sai test JDK

Giả sử IDE chạy JUnit 5 trên Java 21 nhưng Maven Surefire trong CI dùng JVM Java 17. Một test dependency có class-file major 65.

**Dấu hiệu:** `UnsupportedClassVersionError`.

**Cách xử lý:**
1. Ghi class gây lỗi.
2. Xác minh JDK của test fork, không chỉ shell.
3. Kiểm tra toolchains và final dependency graph.
4. Chốt runtime floor thực sự cần hỗ trợ.
5. Chọn dependency/test JDK tương thích.
6. Pin plugin/provider versions và test count.
7. Re-run trên CI.

Không tự hạ `--release` ở application source nếu lỗi thực sự từ third-party test dependency hoặc runtime fork.

## 27. Tình huống 2: Container bị OOM kill nhưng heap chưa đầy

Giả sử app có memory limit 768 MiB, dùng heap gần 650 MiB và nhiều direct buffers, native threads.

**Dấu hiệu:** pod restart, có `OOMKilled` hoặc exit 137; Java log không có heap OOME.

**Cách xử lý:**
1. Xem Pod/container status và OOM events.
2. Ghi max heap, RSS và cgroup limits.
3. Xem non-heap/direct/native/thread memory.
4. Kiểm allocation/GC và workload.
5. Điều chỉnh heap/native headroom hoặc sửa leak.
6. So baseline/candidate với cùng limits.
7. Chạy load/soak, quan sát memory trend.

Đừng tăng `-Xmx` trong container nhỏ để sửa kernel OOM kill; việc đó có thể làm áp lực memory nặng hơn.

## 28. Tình huống 3: Chỉ image mới lỗi HTTPS

Giả sử laptop tin corporate CA nhưng runtime image Java 21 chưa được cài đúng truststore.

**Dấu hiệu:** `SSLHandshakeException: PKIX path building failed`.

**Cách xử lý:**
1. Xác nhận endpoint và certificate chain thực trong container.
2. Kiểm Java truststore, CA và proxy.
3. Kiểm hostname, SNI và client certificate nếu mTLS.
4. Kiểm clock và JDK TLS policies.
5. Cấp đúng CA/truststore theo image policy.
6. Chạy integration test trên final image.
7. Không tắt certificate/hostname verification.

## 29. Tình huống 4: Hai test tranh cùng file trong CI

Giả sử test A và B cùng dùng `/tmp/export.json`. Local chạy riêng; CI chạy song song.

**Dấu hiệu:** file bị xóa hoặc ghi sai dữ liệu ngẫu nhiên.

**Cách sửa:** dùng unique temporary directory của từng test, không hard-code global path và cleanup đúng lifecycle. Nếu còn phụ thuộc static singleton/global property, cần inject/cô lập state, không chỉ tăng test retries.

## 30. Checklist trước khi kết luận đã xử lý

- [ ] Đã xác định stage lỗi và root-cause stack trace.
- [ ] Đã có commit, artifact checksum và image digest.
- [ ] Đã xác minh JDK launcher, compiler, test fork và app JVM.
- [ ] Đã kiểm `--release`, class-file major và dependency versions.
- [ ] Đã ghi OS/architecture, base image, libc và native library support.
- [ ] Đã kiểm build stage khác runtime image ở điểm nào.
- [ ] Đã kiểm CPU quota, availableProcessors và throttling.
- [ ] Đã kiểm heap, RSS, non-heap/native memory và OOM reason.
- [ ] Đã kiểm PID/thread/file descriptor limits.
- [ ] Đã kiểm case-sensitive paths, workdir và read-only mounts.
- [ ] Đã kiểm charset/locale/timezone và clock behavior.
- [ ] Đã kiểm DNS, proxy, service names và NetworkPolicy.
- [ ] Đã kiểm Java truststore/CA/TLS và mTLS.
- [ ] Đã kiểm presence/config sources của secrets mà không log values.
- [ ] Đã so resolved Maven/Gradle dependencies và cache behavior.
- [ ] Đã xác minh JUnit test discovery và số test executed.
- [ ] Đã kiểm parallelism, global mutable state, port/file collisions.
- [ ] Đã kiểm Java agent, Mockito/Byte Buddy và JPMS flags khi liên quan.
- [ ] Đã kiểm Docker/Testcontainers privileges và readiness.
- [ ] Đã kiểm entrypoint, argv, PID 1, SIGTERM và shutdown.
- [ ] Đã tái hiện hoặc ghi rõ giới hạn reproduction.
- [ ] Đã thay từng biến để xác nhận root cause.
- [ ] Đã sửa nguyên nhân gốc, không tắt TLS/security hoặc retry vô hạn.
- [ ] Đã thêm regression evidence trên đúng CI/container target.

## 31. Tài liệu tham khảo

- [Java Launcher Reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): JVM flags, launcher và GC logging.
- [JDK jcmd Reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): VM flags, GC và JFR.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset từ JDK 18.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): module access.
- [JEP 451 — Dynamic Loading of Agents](https://openjdk.org/jeps/451): Java agent behavior.
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): compiler/test JDK configuration.
- [Gradle Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): test tasks và JUnit Platform.
- [Maven Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/): release/source/target.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): tests/forks/argLine.
- [Dockerfile Reference](https://docs.docker.com/reference/dockerfile/): USER, WORKDIR, ENTRYPOINT, multi-stage.
- [Kubernetes Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): requests, limits và cgroups.
- [Kubernetes Debug Running Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/): logs, events và debugging.
- [Testcontainers Java](https://java.testcontainers.org/): container-based tests.
- [Mockito API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html): mock maker và agent.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycle, parallel và TempDir.

Các trang tài liệu “current/latest” có thể khác version đang pin. Khi triển khai, dùng tài liệu của **đúng JDK, OS/image, build plugin và framework version**, rồi đối chiếu bằng runtime evidence.

## 32. Kết luận

**Lỗi chỉ xảy ra trong CI hoặc container thường cho thấy các điều kiện thực thi chưa tương đương; không nên mặc định đổ lỗi cho JDK mới.** Cần kiểm riêng artifact và dependency graph, Java compiler/test/runtime, OS và native libs, tài nguyên cgroup, filesystem, charset/timezone, DNS/proxy/CA, secrets/config và cách CI chạy tests song song.

Quy trình đáng tin là **xác định stage lỗi → thu fingerprint và log → lập ma trận khác biệt → tái hiện bằng artifact/image/resources tương đương → thay từng biến có chủ đích → sửa root cause → bổ sung regression test trong CI/container đích**. Thay vì làm pipeline xanh bằng cách tăng timeout vô hạn, bỏ test, tắt TLS verification hoặc chạy container đặc quyền, nhóm cần giữ bằng chứng kỹ thuật đủ để lần nâng Java tiếp theo không lặp lại sự cố “máy tôi vẫn chạy” và không biến workaround thành rủi ro production.
