# Lập danh mục JDK nguồn, thành phần ứng dụng và các môi trường cần nâng cấp

Một đợt nâng cấp JDK không chỉ thay executable `java`. Ứng dụng thường được biên dịch bởi một JDK, kiểm thử trên JDK khác, chạy trong container với runtime riêng và phụ thuộc vào nhiều thành phần như framework, driver, agent, thư viện native, script vận hành và hệ điều hành. Nếu chỉ kiểm tra source code hoặc một máy developer, nhiều điểm phụ thuộc vẫn có thể bị bỏ sót.

Bài này thuộc chương **Tác động nâng cấp** của module **JAVA_VERSION_JAVA25**. Mục tiêu là lập một danh mục có thể kiểm tra được cho toàn bộ đường đi từ source tới production: JDK nào đang được dùng, thành phần nào phụ thuộc vào runtime, môi trường nào cần nâng cấp, ai chịu trách nhiệm, bằng chứng tương thích nằm ở đâu và phần nào cần xử lý trước khi chuyển đổi.

**Phạm vi thời điểm:** nội dung được biên soạn ngày 27-11-2026. Theo trang tải xuống Oracle, JDK 27 là bản phát hành mới nhất, còn JDK 25 là bản LTS mới nhất. Điều đó không tự quyết định JDK đích cho mọi tổ chức: cần căn cứ vào chính sách hỗ trợ, vendor, thời gian cập nhật, nền tảng triển khai và yêu cầu vận hành. Ghi lại full version string của từng runtime thay vì chỉ ghi “Java 25” hoặc “JDK 27”.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt JDK của developer, build tool, compiler, test runner và production runtime.
2. Ghi nhận vendor, distribution, full build, kiến trúc CPU và hệ điều hành của từng môi trường.
3. Lập danh sách ứng dụng, service, batch job, công cụ và dependency cần nâng cấp.
4. Xác định source/bytecode target, preview API, module path và các cờ JVM đang được sử dụng.
5. Kiểm tra phụ thuộc JDK-internal API, API deprecated, native access và Java agent.
6. Kiểm kê database driver, TLS, crypto provider, thư viện native và dịch vụ bên ngoài.
7. Lập ma trận môi trường development, CI, test, staging, production và disaster recovery.
8. Dùng java, jcmd, jdeps, jdeprscan và jnativescan để thu thập bằng chứng.
9. Đánh giá rủi ro theo mức ảnh hưởng, khả năng xảy ra và phạm vi triển khai.
10. Tạo kế hoạch nâng cấp, kiểm thử, rollout và rollback dựa trên danh mục thực tế.

## 2. Xác định chính xác phạm vi nâng cấp

Trước khi thu thập dữ liệu, hãy xác định hệ thống nào nằm trong đợt nâng cấp. Một hệ thống có thể có nhiều tiến trình Java và mỗi tiến trình có vòng đời triển khai riêng.

Phạm vi tối thiểu cần xem xét:

- Ứng dụng web/API và từng microservice.
- Worker, message consumer, scheduler và batch job.
- Công cụ migration dữ liệu, database migration và command-line utility.
- Build agent, CI runner, test runner và công cụ tạo artifact.
- Application server, servlet container hoặc nền tảng tích hợp.
- Monitoring, APM, profiler, coverage agent và security agent chạy trong JVM.
- Script khởi động, script quản trị, cron job và tác vụ bảo trì.
- Công cụ đóng gói runtime riêng, ví dụ custom image được tạo bằng jlink.
- Tiến trình Java phụ trợ nằm trong container sidecar hoặc nền tảng quản trị.

Không gộp nhiều service vào một dòng “backend”. Mỗi artifact hoặc process có thể dùng JDK, cờ JVM, thư viện và môi trường khác nhau.

### 2.1. Phân biệt sáu lớp phiên bản

| Lớp | Cần ghi nhận | Vì sao quan trọng |
|---|---|---|
| Developer JDK | JDK trong IDE và terminal của developer | Quyết định compiler, language server và khả năng chạy công cụ |
| Build JDK | JDK chạy Maven, Gradle, Ant hoặc build script | Plugin và annotation processor có thể phụ thuộc JDK |
| Compiler/toolchain JDK | JDK thực sự chạy javac | Có thể khác JDK chạy build daemon |
| Compile target | Giá trị --release hoặc cấu hình tương đương | Quyết định API Java và bytecode mục tiêu |
| Test JDK | JDK chạy unit, integration, test fork và benchmark | Test plugin có thể khởi chạy JVM riêng |
| Production runtime | JDK trong máy chủ, VM hoặc container | Đây là môi trường thực thi người dùng đang sử dụng |

Ví dụ một dự án có thể được build bằng JDK 25, dùng --release 21, chạy test trên JDK 25 và deploy trên JDK 21. Đây là bốn thông tin khác nhau. Ghi một trường duy nhất javaVersion=25 sẽ không thể hiện chính xác cấu hình đó.

### 2.2. Phân biệt phiên bản source và runtime

Với javac, ưu tiên --release để cố định ngôn ngữ, API Java SE và bytecode target:

```bash
javac --release 25 -d out src/main/java/example/Main.java
```

Không trộn --release với -source hoặc -target. Nếu sử dụng preview feature, phải ghi rõ JDK phát hành preview và cờ compile/runtime tương ứng. Preview API gắn với phiên bản phát hành cụ thể; không giả định class file preview của JDK cũ có thể chạy trên JDK mới.

## 3. Chọn JDK đích và baseline cần so sánh

Danh mục phải lưu cả runtime hiện tại và runtime đích. Không nên chỉ ghi “nâng lên Java mới nhất”.

Các câu hỏi cần chốt:

- Đích là JDK 25 LTS, một feature release mới hơn hay một vendor distribution cụ thể?
- Tổ chức cần hỗ trợ dài hạn, lịch cập nhật nhanh hay đồng bộ với nền tảng cloud?
- Vendor có cung cấp bản build cho OS và kiến trúc CPU đang dùng không?
- Có cam kết hỗ trợ thương mại, security update và thời hạn hỗ trợ phù hợp không?
- Có cần cùng vendor giữa developer, CI và production không?
- Artifact có cần chạy trên nhiều runtime hoặc nhiều vendor không?
- Container base image, application server và native library có hỗ trợ JDK đích không?

### 3.1. Ghi nhận vendor và full build

Không coi các bản phân phối JDK là giống nhau chỉ vì cùng phiên bản Java SE. Cần ghi:

- Vendor/distribution và nguồn tải.
- Full version string, build number và update level.
- Runtime image đầy đủ hay custom image.
- Kiến trúc CPU, ví dụ x86-64 hoặc AArch64.
- Loại runtime: HotSpot hay JVM implementation khác.
- Các module đã được đóng gói hoặc loại khỏi custom runtime.
- Chính sách cập nhật security và người chịu trách nhiệm cập nhật.

Tại ngày 27-11-2026, trang Oracle Downloads liệt kê JDK 27 là bản mới nhất và JDK 25 là bản LTS mới nhất. Consolidated release notes của JDK 25 cũng liệt kê bản BPR 25.0.5.1.1 có thay đổi ngày 24-11-2026. Vì vậy, báo cáo nâng cấp cần lưu kết quả java --version của đúng artifact đang cài, không chỉ ghi số major hoặc lấy nhãn trên trang tải xuống làm full build string.

### 3.2. Bảng so sánh baseline và target

| Thuộc tính | Baseline | Target | Bằng chứng |
|---|---|---|---|
| Vendor | Vendor hiện tại | Vendor dự kiến | java --version |
| Full version/build | Chuỗi đầy đủ | Chuỗi đầy đủ | java --version, release notes |
| JDK role | Build/runtime/test | Build/runtime/test | Toolchain và deployment config |
| Compile target | --release hiện tại | --release dự kiến | Build configuration |
| OS/architecture | Nền tảng hiện tại | Nền tảng hỗ trợ | Host/container metadata |
| JVM options | Cờ đang chạy | Cờ đã rà soát | jcmd VM.flags |
| Dependencies | Phiên bản hiện tại | Phiên bản đã xác nhận | Dependency tree, vendor matrix |
| Native components | Agent và thư viện native | Bản tương thích | Native scan, runtime test |
| Support policy | Chính sách hiện tại | Chính sách đích | Vendor support page |

## 4. Kiểm kê JDK đang chạy ở từng process

Thu thập dữ liệu từ tiến trình thực tế. Thông tin từ terminal developer có thể không giống runtime trong container hoặc service manager.

### 4.1. Xác định JDK của terminal và build agent

Chạy trên từng máy developer và CI runner:

```bash
java --version
javac --version
```

Trên Linux/macOS, dùng which java và which javac để xác định đường dẫn executable. Trên Windows PowerShell, Get-Command java và Get-Command javac có thể giúp kiểm tra command được phân giải từ PATH.

Thu thập thêm cấu hình build:

- JAVA_HOME.
- PATH và đường dẫn JDK thực tế.
- Maven/Gradle toolchain.
- JDK của daemon hoặc wrapper.
- JDK dùng để chạy annotation processor, code generator và compiler plugin.
- JDK được IDE chọn cho project và cho build tool.

### 4.2. Xác định runtime của process đang chạy

Liệt kê JVM trên máy:

```bash
jcmd -l
```

Với từng PID thuộc ứng dụng, thu thập:

```bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags -all
jcmd <pid> VM.system_properties
```

Các lệnh trên giúp xác định runtime version, command line, cờ JVM và system properties của process. Chạy bằng user có quyền attach phù hợp và trên đúng host/container namespace. Không dùng PID lấy từ máy khác hoặc từ host khi process nằm trong namespace riêng mà công cụ không nhìn thấy.

Nếu service được khởi chạy qua systemd, Windows Service, Kubernetes hoặc một platform manager, hãy lưu cả cấu hình launcher/manifest vì nó cho biết JDK path và environment variables thực tế.

### 4.3. Ghi nhận thuộc tính runtime

Các thông tin nên có trong hồ sơ:

- java.home, java.version, java.vendor, java.vm.name.
- os.name, os.version, os.arch.
- user.language, user.country, user.timezone.
- file.encoding, native.encoding, stdin.encoding, stdout.encoding, stderr.encoding nếu có.
- java.library.path.
- java.class.path, module path và module options.
- Heap min/max, collector và các tùy chọn GC.
- JFR, heap dump, error log và diagnostic options.
- Environment variables được launcher chuyển vào JVM.

Không lưu secret, mật khẩu, token hoặc giá trị nhạy cảm trong báo cáo. Với system properties và command line, hãy che credential trước khi chia sẻ.

## 5. Lập danh mục thành phần ứng dụng

Với mỗi ứng dụng, chia thành các nhóm có thể kiểm tra độc lập.

| Nhóm | Thành phần cần liệt kê | Ví dụ |
|---|---|---|
| Application artifact | JAR/WAR/EAR, executable image | API service, batch worker |
| Framework | Framework và runtime container | Web framework, dependency injection, persistence |
| Runtime libraries | Thư viện trực tiếp và bắc cầu | JSON, logging, validation, HTTP client |
| Database | JDBC driver, pool, migration tool | PostgreSQL driver, connection pool |
| Messaging | Client và serialization library | Kafka, AMQP, messaging client |
| Security | TLS, crypto, authentication, SSO | Provider, keystore, token client |
| Native integration | JNI, FFM, native library | Compression, image, database client |
| JVM agents | Agent gắn vào JVM | APM, profiler, coverage, security |
| Build/test | Compiler plugin, test engine, generator | Maven/Gradle plugin, JUnit, Mockito |
| Operations | Script, CLI, monitoring tool | Backup, diagnostics, deployment utility |

### 5.1. Lấy dependency tree

Với Maven:

```bash
mvn dependency:tree
mvn help:effective-pom
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew buildEnvironment
```

Chụp dependency tree cho từng module và configuration liên quan. runtimeClasspath không bao gồm tất cả dependency dùng ở test, build plugin hoặc annotation processor. Hãy lưu riêng compile, runtime, test, annotation processor và plugin dependency khi chúng được sử dụng.

Với artifact được tải trực tiếp hoặc thư viện nội bộ, ghi version, checksum, nơi phát hành, người sở hữu và nguồn cập nhật. Dependency không có version rõ ràng hoặc không còn maintainer cần được đánh dấu để xử lý trước.

### 5.2. Những phiên bản phải kiểm tra

- Framework hỗ trợ JDK đích.
- Application server hoặc servlet container hỗ trợ runtime đích.
- Build tool và plugin chạy được trên JDK dùng để build.
- Test framework và mock/instrumentation library tương thích với bytecode mới.
- Annotation processor, code generator và compiler plugin.
- JDBC driver và database connection pool.
- Logging backend, JSON/XML parser và HTTP client.
- APM, tracing, profiler và security agent.
- Native library và wrapper Java của thư viện đó.

Không kết luận một dependency tương thích chỉ vì nó compile được. Kiểm tra release notes của vendor, compatibility matrix và test thực tế trên đúng OS/architecture.

## 6. Kiểm kê source code, API và module

Phân loại những phần source phụ thuộc trực tiếp vào phiên bản JDK.

### 6.1. Source level, API target và bytecode

Ghi cho từng module:

- JDK dùng để compile.
- --release hoặc cấu hình source compatibility.
- Bytecode target.
- Module descriptor và module path.
- Multi-release JAR nếu có.
- Preview feature hoặc incubator module.
- Compiler warning và API deprecated.

Với Java 25, một số tính năng đã trở thành API/ngôn ngữ ổn định như Module Import Declarations, Compact Source Files và Instance Main Methods, Flexible Constructor Bodies, Key Derivation API, AOT cache và JFR Method Timing/Tracing. Một số tính năng khác vẫn ở preview trong JDK 25, chẳng hạn Structured Concurrency và Stable Values. Khi kiểm kê, hãy ghi rõ source có sử dụng preview API nào, JEP nào và --enable-preview đang xuất hiện ở compile/test/runtime hay không.

Không coi --enable-preview là một cờ cấu hình chung có thể giữ nguyên qua nhiều JDK. Preview gắn với release cụ thể; source phải được đánh giá và biên dịch lại theo JDK đích.

### 6.2. JDK internal API và encapsulation

Kiểm tra code hoặc thư viện sử dụng package nội bộ của JDK, reflective access tới implementation detail hoặc cờ mở module.

Các dấu hiệu cần thu thập:

- Import từ sun.*, com.sun.* hoặc package nội bộ.
- --add-exports, --add-opens, --add-reads.
- Reflection truy cập field/method không public.
- Unsafe, VarHandle, JNI hoặc FFM.
- Bytecode instrumentation và class transformation.
- Cấu hình module path, automatic module và unnamed module.

Các cờ mở module đang có cần được ghi kèm lý do, module được mở, consumer và thời hạn loại bỏ. Coi một cờ mở rộng quyền truy cập là một dependency cần xử lý, không phải bằng chứng rằng thư viện đã tương thích lâu dài.

### 6.3. Công cụ phân tích dependency

jdeps có thể phân tích dependency package/class và phát hiện tham chiếu tới JDK internal API:

```bash
jdeps --multi-release 25 --jdk-internals -R --class-path "lib/*" app.jar
```

Có thể xem dependency module:

```bash
jdeps --multi-release 25 --list-deps --recursive --class-path "lib/*" app.jar
```

Với multi-release JAR, đặt --multi-release theo release đang đánh giá để phân tích đúng phiên bản class được chọn. Tùy hệ điều hành, dấu phân cách class path là ; trên Windows và : trên Linux/macOS.

Dùng jdeprscan để tìm API deprecated trong bytecode:

```bash
jdeprscan --for-removal --class-path "lib/*" app.jar
```

Có thể lấy danh sách API được đánh dấu for-removal trong Java 25 bằng:

```bash
jdeprscan --release 25 --list --for-removal
```

Các lệnh này giúp ưu tiên xử lý API có rủi ro cao. Kết quả phân tích tĩnh không thể phát hiện mọi lời gọi qua reflection, dynamic class generation, cấu hình bên ngoài hoặc code được tải sau khi process khởi động. Kết hợp với runtime test và log.

## 7. Kiểm kê JNI, FFM, native library và Java agent

Đây là nhóm dễ bị bỏ quên vì không nằm trong dependency tree Java thông thường.

### 7.1. Native access

Lập danh sách:

- JAR có khai báo native method.
- JNI library được load bằng System.load hoặc System.loadLibrary.
- Thư viện dùng Foreign Function & Memory API.
- Thư viện native .so, .dll, .dylib.
- Thư viện được gọi gián tiếp bởi driver, compression, image hoặc crypto provider.
- Module hoặc classpath entry cần quyền native access.
- Phiên bản binary theo OS và CPU architecture.

JDK 24 trở đi phát cảnh báo về các thao tác native access qua JNI/FFM nhằm chuẩn bị cho việc hạn chế chặt hơn. JDK 25 hỗ trợ --enable-native-access để cấp quyền theo module và --illegal-native-access để điều khiển cách xử lý truy cập chưa được cấp quyền.

### 7.2. Quét native access

Dùng jnativescan để tìm restricted method và khai báo native trong JAR:

```bash
jnativescan --class-path "app.jar:lib/*" --release 25
jnativescan --class-path "app.jar:lib/*" --release 25 --print-native-access
```

Trên Windows, thay dấu : bằng dấu ; trong class path. Nếu ứng dụng dùng module path, truyền cấu hình --module-path và --add-modules phù hợp để quét đúng graph module.

Sau khi xác định module cần native access, thử chạy trong staging với chế độ nghiêm ngặt:

```bash
java --illegal-native-access=deny \
     --enable-native-access=com.example.nativebridge \
     -jar app.jar
```

Tên module trong ví dụ chỉ minh họa. Thay bằng module đã được quét và xác nhận. Với code trên classpath, ALL-UNNAMED có thể được dùng trong bài kiểm thử, nhưng nên thu hẹp quyền theo module khi có thể. Không cấp quyền rộng chỉ để làm biến mất cảnh báo.

### 7.3. Java agent và instrumentation

Ghi tất cả agent trong cấu hình khởi động:

- -javaagent.
- -agentlib.
- -agentpath.
- Agent được attach vào JVM sau khi process đã chạy.
- Agent do APM, profiler, test coverage, mocking framework hoặc security product cung cấp.

JEP 451 đã đưa cảnh báo cho việc nạp agent động vào JVM đang chạy. Vì vậy, inventory phải phân biệt agent được nạp lúc startup với agent được attach sau đó. Kiểm tra release notes và chính sách của agent vendor cho JDK đích; xác nhận quy trình attach/diagnostics vẫn hoạt động theo cấu hình được phê duyệt.

### 7.4. Các câu hỏi nghiệm thu native

- Tất cả native library có binary cho kiến trúc đích không?
- Có phụ thuộc glibc/musl hoặc system library cụ thể không?
- Quyền native access đã được cấp đúng module chưa?
- Có warning native access khi chạy integration test không?
- Agent có hỗ trợ phiên bản JDK và bytecode mới không?
- Có thao tác attach động trong production không?
- Có thể chạy ứng dụng trong chế độ native access nghiêm ngặt ở staging không?

## 8. Kiểm kê JVM options và cấu hình khởi động

Thu thập tất cả cờ JVM từ command line, environment variable, service manager, container manifest và script.

### 8.1. Nhóm tùy chọn cần lưu

| Nhóm | Thuộc tính cần ghi |
|---|---|
| Heap | -Xms, -Xmx, MaxRAMPercentage |
| Garbage collector | Collector, region/heap tuning, pause goal |
| Thread/CPU | ActiveProcessorCount, stack size, thread limit |
| Class/module | Module path, --add-modules, --add-opens, --add-exports |
| Preview | --enable-preview, incubator module |
| Native | --enable-native-access, --illegal-native-access |
| Agents | -javaagent, -agentlib, -agentpath |
| Security/TLS | Truststore, keystore, provider, TLS properties |
| Locale/encoding | Locale, timezone, charset và stream encoding |
| Diagnostics | JFR, GC log, heap dump, fatal error log |
| Startup | CDS/AOT cache, classpath, launcher arguments |

### 8.2. Kiểm tra option bị bỏ qua hoặc không còn hợp lệ

Chạy ứng dụng trên JDK đích và lưu toàn bộ stderr/stdout lúc startup. Tìm:

- Warning về VM option đã deprecated hoặc obsolete.
- Option không còn được nhận diện.
- Option không còn tác dụng.
- Option xung đột giữa các cờ.
- Thay đổi mặc định của GC hoặc runtime.
- Module không tìm thấy hoặc package không được export/open.
- Preview feature chưa được bật hoặc không đúng release.

Không sao chép nguyên bộ JVM flags từ máy cũ sang máy mới. Mỗi flag phải có owner, mục đích, bằng chứng cần thiết và quyết định giữ/sửa/xóa.

### 8.3. Kiểm tra cấu hình GC

Ghi collector, heap size, pause goal, log configuration và số liệu vận hành hiện tại. Khi nâng cấp, so sánh cùng workload về throughput, latency, allocation rate, heap occupancy, pause time và CPU. Không dùng một con số GC count đơn lẻ để quyết định collector tốt hơn.

Nếu hệ thống dùng custom GC log parser, kiểm tra định dạng unified logging và cấu hình -Xlog trên runtime đích. Đảm bảo log vẫn được lưu, rotate và thu thập bởi hệ thống quan sát.

## 9. Kiểm kê môi trường cần nâng cấp

Không phải mọi môi trường đều có cùng JDK. Tạo ma trận theo từng stage và từng process.

| Môi trường | Thành phần cần kiểm tra | Bằng chứng |
|---|---|---|
| Developer workstation | JDK, IDE, language server, build tool | java --version, IDE project SDK |
| CI runner | JDK build, Maven/Gradle, cache | Build log và toolchain config |
| Test runner | JDK test JVM, test fork, integration test | Test process version và JVM args |
| Artifact builder | JDK, compiler, annotation processor | Build manifest và artifact metadata |
| Local container | Base image, runtime, native library | Image digest, OS/arch |
| QA/staging | Runtime, flags, secrets, certificate, monitoring | Deployment manifest và startup log |
| Production | Runtime từng replica, node pool, container | Runtime inventory và process command line |
| Batch/scheduler | JDK của từng job và script | Job definition, cron/service config |
| Disaster recovery | Image, JDK, secrets và cấu hình dự phòng | DR inventory và kết quả diễn tập |
| Operations | JDK của diagnostic tool, APM và admin utility | Tool version và compatibility matrix |

### 9.1. Không bỏ sót job chạy ngoài service chính

Các thành phần thường bị bỏ sót:

- Cron job chỉ chạy ban đêm hoặc cuối tháng.
- Script backup/restore và data migration.
- Công cụ import/export.
- Job tạo báo cáo hoặc xử lý file lớn.
- Tool ký số, kiểm tra chứng thư và rotate key.
- Process khởi động cùng máy nhưng không nằm trong deployment pipeline chính.
- JDK nhúng trong ứng dụng desktop hoặc runtime image riêng.

Lập danh sách từ scheduler, service manager, container registry và hệ thống monitoring; đừng chỉ dựa vào danh sách repository.

## 10. Kiểm kê OS, CPU, container và tài nguyên

JDK runtime và native dependencies phụ thuộc vào nền tảng thực thi.

### 10.1. OS và kiến trúc

Với từng environment, ghi:

- OS distribution và phiên bản.
- Kernel version.
- CPU architecture: x86-64, AArch64 hoặc kiến trúc được hỗ trợ khác.
- CPU model và instruction set quan trọng.
- libc/runtime dependency của native library.
- Filesystem, mount option và quyền truy cập.
- Thư mục tạm và dung lượng đĩa.
- CA bundle của hệ điều hành.
- Font và desktop subsystem nếu ứng dụng có xử lý đồ họa/PDF.

Kiểm tra trang Certified System Configurations hoặc support matrix của vendor JDK. Một JDK có thể tải được trên OS nhưng không đồng nghĩa nền tảng đó nằm trong phạm vi hỗ trợ chính thức.

### 10.2. Container và orchestration

Ghi lại:

- Base image và image digest.
- JDK package hoặc runtime image bên trong.
- glibc/musl và native packages.
- CPU request/limit và memory request/limit.
- Cgroup version và cách runtime nhìn nhận CPU/memory.
- Read-only filesystem, user/group và Linux capabilities.
- Mount cho truststore, keystore, timezone và config.
- Startup probe, readiness probe và liveness probe.
- Shutdown grace period và tín hiệu kết thúc process.

Cần kiểm tra JVM ergonomics khi chạy dưới cgroup limit. Cùng -Xmx nhưng khác memory limit có thể tạo kết quả OOM hoặc native memory pressure khác nhau. Không chỉ test bằng JVM trên máy developer rồi suy rộng sang container.

### 10.3. Native memory và headroom

Ghi riêng:

- Heap max.
- Metaspace và compressed class space.
- Thread stacks.
- Code cache.
- Direct buffer.
- Native library allocation.
- Agent/profiler memory.
- Container RSS và memory limit.

Một runtime mới có thể thay đổi footprint hoặc hành vi JIT/GC. Để lại headroom cho native memory và burst; không đặt heap max bằng toàn bộ memory limit của container.

## 11. Kiểm kê hệ thống bên ngoài và tích hợp

JDK upgrade có thể làm thay đổi hành vi ở ranh giới giữa ứng dụng và hệ thống khác.

### 11.1. Database và message broker

Với từng database/broker, ghi:

- Server version và protocol.
- JDBC/messaging driver.
- TLS mode, cipher suite và certificate chain.
- Authentication mechanism.
- Connection pool.
- Serialization format.
- Timeout, retry, keep-alive và failover behavior.
- Native client nếu có.

Kiểm thử cả connection mới, connection pool reuse, failover, transaction, large payload và shutdown.

### 11.2. TLS, certificate và crypto provider

Inventory cần có:

- Truststore/keystore type và vị trí.
- Certificate chain, CA và ngày hết hạn.
- Crypto provider và thứ tự provider.
- PKCS#11/HSM integration.
- TLS protocol/cipher đang được thương lượng.
- Algorithm constraint và security property.
- FIPS hoặc compliance mode nếu áp dụng.
- Code ký số, xác minh chữ ký và dẫn xuất khóa.

Chạy kiểm thử handshake với từng endpoint quan trọng. Một ứng dụng khởi động được không chứng minh mọi certificate, provider hoặc HSM operation đều hoạt động.

### 11.3. HTTP, DNS và hệ thống bên ngoài

Ghi các dependency tới:

- REST/SOAP endpoint.
- Proxy và outbound gateway.
- DNS resolver và hosts mapping.
- LDAP/identity provider.
- Object storage và file server.
- SMTP, webhook và dịch vụ ký số.
- API gateway, service mesh và load balancer.

Kiểm thử timeout, DNS resolution, proxy authentication, TLS handshake, redirect và connection reuse trên runtime đích.

## 12. Kiểm kê locale, timezone và encoding

Đây là nhóm có thể tạo behavioral incompatibility dù source code không đổi.

### 12.1. Charset

Default charset của Java SE là UTF-8 từ JDK 18. Khi nâng cấp từ runtime cũ, kiểm tra mọi điểm đọc/ghi file, CSV, text protocol, log, stdin/stdout và tích hợp với hệ thống ngoài.

Trong JDK 25, các stream chuẩn có thể sử dụng charset riêng qua stdin.encoding, stdout.encoding và stderr.encoding; chúng không nhất thiết giống file.encoding hoặc Charset.defaultCharset().

Hãy ghi rõ charset ở ranh giới dữ liệu thay vì dựa vào mặc định. Kiểm thử file có tiếng Việt, ký tự ngoài BMP, BOM, newline và dữ liệu do hệ thống Windows/Linux tạo ra.

### 12.2. Locale và timezone

JDK 25 cập nhật locale data lên CLDR 47. Format ngày, giờ, tiền tệ, tên timezone và một số quy tắc ngôn ngữ có thể thay đổi theo dữ liệu locale mới.

Kiểm tra:

- Locale.getDefault() và locale theo request.
- ZoneId.systemDefault() và user.timezone.
- Date/time parsing và formatting.
- Number/currency formatting.
- Ngôn ngữ, tên quốc gia và timezone display name.
- Sort/collation nếu kết quả được lưu hoặc dùng làm khóa.
- Báo cáo, hóa đơn, email và dữ liệu xuất cho đối tác.

Đặc biệt kiểm tra nơi ứng dụng parse lại chuỗi đã format. Không dùng chuỗi hiển thị theo locale làm định dạng trao đổi dữ liệu giữa hệ thống nếu có thể dùng định dạng chuẩn.

## 13. Kiểm kê observability và vận hành

JDK mới phải tiếp tục được quan sát và hỗ trợ bởi công cụ production.

Ghi lại:

- APM agent và phiên bản.
- Metrics exporter và JMX integration.
- OpenTelemetry SDK/agent nếu có.
- JFR recording và quy trình dump.
- GC log parser và dashboard.
- Heap dump analyzer.
- Thread dump và diagnostic command.
- Alert theo CPU, heap, native memory, latency và error rate.
- Log collector, rotation và retention.
- Health/readiness endpoint.
- Crash dump, core dump và quy trình incident response.

Kiểm tra xem agent có phụ thuộc bytecode layout, JDK internal API, dynamic attach hoặc native library không. Xác nhận dashboard không bị thay đổi do metric name, GC event hoặc runtime attribute thay đổi.

## 14. Tạo inventory có thể bàn giao

Một danh mục tốt phải giúp một người khác biết thành phần nào cần thay đổi, ai phụ trách và làm sao xác minh.

### 14.1. Các trường tối thiểu

| Trường | Nội dung |
|---|---|
| System ID | Mã ứng dụng/service/job |
| Component | Process, artifact, agent hoặc dependency |
| Owner | Nhóm/người chịu trách nhiệm |
| Environment | Dev, CI, test, staging, prod, DR |
| Current JDK | Vendor, distribution, full version/build |
| Target JDK | Vendor và full build dự kiến |
| JDK role | Developer/build/compiler/test/runtime |
| Source/API target | --release, bytecode, module path |
| Artifact | Version, checksum, registry/repository |
| Dependencies | Direct/transitive, framework, driver, plugin |
| JVM options | Heap, GC, module, preview, native, agent |
| Native access | JNI/FFM, native library, module grant |
| OS/architecture | OS, kernel, CPU, container base |
| External systems | DB, broker, TLS, HSM, endpoint |
| Locale/runtime config | Charset, locale, timezone |
| Risk | Mức độ, lý do và phạm vi ảnh hưởng |
| Evidence | Scan, release note, test, vendor matrix |
| Action | Upgrade, replace, configure, retest |
| Rollback | Phiên bản/cấu hình có thể quay lại |
| Status | Not assessed, blocked, ready, verified |

### 14.2. Ví dụ danh mục

| Component | Current | Target | Rủi ro ban đầu | Bằng chứng cần có |
|---|---|---|---|---|
| Order API | JDK runtime hiện tại | JDK mục tiêu | Cao nếu dùng preview/native | Startup, API scan, integration/load test |
| Pricing worker | JDK runtime hiện tại | JDK mục tiêu | Trung bình | Batch replay, allocation, GC |
| JDBC driver | Phiên bản đang chạy | Phiên bản hỗ trợ JDK đích | Cao nếu TLS/driver không tương thích | Vendor matrix, DB integration |
| APM agent | Phiên bản hiện tại | Agent được hỗ trợ | Cao nếu bytecode instrumentation | Agent release note, startup/attach test |
| CI runner | JDK build hiện tại | JDK build đích | Trung bình | Build/test pipeline |
| Container image | Base image hiện tại | Image có JDK đích | Cao nếu native OS dependency | Image scan, smoke test |
| Nightly job | JDK từ script | JDK đích | Dễ bị bỏ sót | Scheduler inventory và replay |

Các mức rủi ro trong bảng chỉ là ví dụ để điền dữ liệu. Phải chấm lại theo hệ thống thật.

### 14.3. Quản lý trạng thái

Dùng một trạng thái thống nhất:

- **Not inventoried:** chưa thu thập đủ dữ liệu.
- **Inventoried:** đã ghi nhận owner, version và môi trường.
- **Needs vendor confirmation:** chưa có bằng chứng tương thích.
- **Blocked:** có dependency hoặc thay đổi cần xử lý trước.
- **Ready for test:** đã có target build và test plan.
- **Verified:** đã qua kiểm thử trên target.
- **Rolled out:** đã triển khai theo phạm vi được phê duyệt.
- **Rolled back:** đã quay lại baseline và lưu nguyên nhân.

Không đánh dấu Verified chỉ vì artifact compile thành công.

## 15. Chấm điểm rủi ro nâng cấp

Dùng hai trục để xếp ưu tiên:

- **Khả năng xảy ra (1–5):** mức độ có khả năng gặp lỗi khi nâng cấp.
- **Ảnh hưởng (1–5):** mức độ ảnh hưởng tới người dùng, dữ liệu, bảo mật hoặc khả năng khôi phục.

Điểm rủi ro tham khảo:

```text
Risk score = Likelihood × Impact

1–4   : Low
5–9   : Moderate
10–15 : High
16–25 : Critical
```

### 15.1. Dấu hiệu làm tăng rủi ro

- Dùng JDK internal API hoặc reflective access.
- Có --add-opens/--add-exports không có owner.
- Có preview/incubator API.
- Có JNI, FFM hoặc native library chưa xác nhận.
- Agent chưa có compatibility statement cho target JDK.
- Dùng Security Manager hoặc policy configuration không còn được hỗ trợ.
- Có custom runtime image thiếu module hoặc native dependency.
- Có driver, provider, HSM hoặc TLS endpoint quan trọng.
- Không có integration test hoặc workload replay.
- Có nhiều JDK khác nhau giữa build, test và production.
- Không có phương án rollback khả thi.

### 15.2. Ưu tiên xử lý

| Mức | Hành động |
|---|---|
| Critical | Không rollout diện rộng; cần xử lý blocker hoặc xác nhận vendor trước |
| High | Cần test chuyên biệt và owner chấp thuận |
| Moderate | Đưa vào regression suite và theo dõi khi canary |
| Low | Ghi nhận bằng chứng và xác minh trong kiểm thử chung |

Điểm số không thay thế đánh giá chuyên môn. Một lỗi bảo mật hoặc mất dữ liệu có thể cần ưu tiên cao dù xác suất thấp.

## 16. Quy trình sử dụng inventory trong một đợt nâng cấp

### Bước 1 — Chụp baseline

Thu thập runtime version, command line, flags, properties, dependency tree, OS, container và môi trường bên ngoài. Lưu thời điểm chụp và artifact checksum.

### Bước 2 — Chốt target

Chọn vendor/build và runtime target cho từng role. Xác minh platform support, security update, framework compatibility và chính sách vận hành.

### Bước 3 — Phân tích tĩnh

Chạy jdeps, jdeprscan, jnativescan; rà soát source, module flags, preview API, dependency metadata và agent configuration.

### Bước 4 — Chạy ứng dụng trên target

Thử chạy artifact hiện tại trên JDK đích trong môi trường test tương đương. Lưu startup warning, missing class, reflective access, native access, TLS error và runtime behavior. Chỉ sau đó mới quyết định phần source cần biên dịch lại hoặc dependency cần nâng cấp.

### Bước 5 — Cập nhật build và dependencies

Cập nhật toolchain, build plugin, framework, driver, agent và native package. Biên dịch theo --release đã chọn. Ghi checksum artifact mới.

### Bước 6 — Kiểm thử theo môi trường

Chạy unit, integration, contract, security, locale, load, performance, failover và shutdown test. Đưa test vào đúng container/OS/architecture dự kiến triển khai.

### Bước 7 — Canary và rollout

Triển khai một nhóm nhỏ trước. So sánh error rate, latency p50/p95/p99, throughput, CPU, heap, native memory, GC và startup. Chỉ mở rộng khi số liệu nằm trong ngưỡng đã thống nhất.

### Bước 8 — Cập nhật inventory sau triển khai

Ghi full runtime build thực tế, image digest, cờ JVM, test evidence, ngày rollout, owner và rollback reference. Inventory là tài liệu sống, cần cập nhật khi JDK hoặc dependency đổi phiên bản.

## 17. Các lỗi thường gặp khi lập danh mục

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ ghi major version | Không biết vendor, update hoặc build | Lưu full version string |
| Đồng nhất build JDK với runtime JDK | Bỏ sót test fork và production image | Tách từng JDK role |
| Chỉ kiểm kê direct dependencies | Bỏ sót dependency bắc cầu | Lưu dependency tree theo configuration |
| Chỉ kiểm tra source | Bỏ sót reflection và runtime configuration | Kết hợp static scan với runtime test |
| Quên agent/APM | Startup hoặc instrumentation có thể lỗi | Kiểm kê agent và cách nạp |
| Quên native library | Chạy được ở dev nhưng lỗi ở container khác | Quét JNI/FFM và kiểm tra architecture |
| Chỉ nâng cấp CI | Production vẫn dùng runtime cũ | Kiểm tra từng deployment environment |
| Chỉ test compile | Không thấy lỗi TLS, locale, GC, shutdown | Chạy integration và workload test |
| Dùng chung một file cấu hình JVM cho mọi role | Build/test/prod nhận cờ không phù hợp | Quản lý cấu hình theo process |
| Coi warning là vô hại | Bỏ qua thay đổi sắp thành lỗi | Gán owner và deadline cho warning |
| Không lưu bằng chứng | Không thể audit hoặc lặp lại kết quả | Gắn log, scan và test report vào inventory |
| Không có rollback | Sự cố kéo dài khi rollout | Chuẩn bị image và cấu hình baseline |

## 18. Ma trận nghiệm thu

| Mã | Kịch bản | Kết quả kỳ vọng |
|---|---|---|
| JDK-INV-01 | Kiểm kê tất cả service, worker và batch job | Không còn process Java ngoài danh sách |
| JDK-INV-02 | Ghi developer/build/compiler/test/runtime JDK | Các role được phân biệt rõ |
| JDK-INV-03 | Ghi vendor, distribution và full build | Có bằng chứng java --version |
| JDK-INV-04 | Ghi --release và bytecode target | Compile target được xác nhận |
| JDK-INV-05 | Kiểm kê preview/incubator API | Có JEP, JDK release và cờ tương ứng |
| JDK-INV-06 | Xuất dependency tree Maven/Gradle | Có direct/transitive và build/test dependency |
| JDK-INV-07 | Chạy jdeps --jdk-internals | Có danh sách JDK internal dependency |
| JDK-INV-08 | Chạy jdeprscan | Có danh sách API deprecated/for-removal |
| JDK-INV-09 | Chạy jnativescan | Có danh sách JNI/FFM/native access |
| JDK-INV-10 | Rà soát Java agent | Có version và cách nạp từng agent |
| JDK-INV-11 | Thu thập JVM flags và system properties | Có command line, flags và properties đã che secret |
| JDK-INV-12 | Kiểm tra OS/CPU/container | Có OS, architecture, image digest và resource limit |
| JDK-INV-13 | Kiểm kê TLS/crypto/database/message broker | Có driver, provider, endpoint và test owner |
| JDK-INV-14 | Kiểm tra locale/timezone/charset | Có regression test cho dữ liệu địa phương |
| JDK-INV-15 | Kiểm tra observability | Agent, metrics, JFR, log và dashboard hoạt động |
| JDK-INV-16 | Kiểm tra staging với native access nghiêm ngặt | Không còn truy cập native chưa được phân loại |
| JDK-INV-17 | Chạy build và test trên JDK đích | Artifact và test runner dùng đúng toolchain |
| JDK-INV-18 | Chạy integration/load test trên target environment | Có số liệu latency, throughput, GC và memory |
| JDK-INV-19 | Kiểm tra DR và job ngoài service | Môi trường dự phòng và lịch chạy đã được xác nhận |
| JDK-INV-20 | Kiểm tra rollback | Có image, JDK và cấu hình baseline để phục hồi |

## 19. Bài thực hành tổng hợp

### Bài A — Lập inventory cho một service

Chọn một service có API, database và message broker.

1. Ghi developer, build, compiler, test và runtime JDK.
2. Lưu vendor, full version string và OS/architecture.
3. Xuất dependency tree.
4. Lưu JVM command line, flags và system properties.
5. Kiểm kê framework, JDBC driver, message client và APM agent.
6. Ghi target JDK, owner và bằng chứng tương thích.

**Sản phẩm:** một dòng inventory hoàn chỉnh và các file evidence đã che thông tin nhạy cảm.

### Bài B — Kiểm tra dependency và native access

1. Chạy jdeps --jdk-internals.
2. Chạy jdeprscan --for-removal.
3. Chạy jnativescan.
4. Phân loại dependency theo source code, thư viện bên thứ ba và native library.
5. Kiểm tra native access trên staging.
6. Ghi action, owner và test evidence cho từng phát hiện.

**Sản phẩm:** danh sách dependency có rủi ro và kế hoạch xử lý.

### Bài C — Lập ma trận môi trường

Ghi dev, CI, test, staging, production, batch và DR. Với mỗi môi trường, xác định JDK, image digest, CPU/memory limit, flags, certificate, locale và người phụ trách.

**Sản phẩm:** ma trận môi trường và danh sách các nơi chưa đồng nhất.

### Bài D — Chấm điểm và lập kế hoạch

Chọn ít nhất năm dependency hoặc môi trường có rủi ro. Tính likelihood × impact, xác định blocker và thứ tự xử lý. Gắn mỗi action với owner, deadline, test và rollback.

**Sản phẩm:** kế hoạch nâng cấp có thể bàn giao cho nhóm triển khai.

### Bài E — Kiểm tra một bản nâng cấp thử nghiệm

Chạy cùng artifact trên baseline và target JDK trong môi trường tương đương. Thu thập startup, warning, error rate, latency, throughput, heap, native memory, GC và kết quả tích hợp. Cập nhật trạng thái inventory từ Not inventoried tới Verified khi đủ bằng chứng.

**Sản phẩm:** báo cáo so sánh và quyết định có thể tiếp tục canary hay cần xử lý blocker.

## 20. Câu hỏi tự đánh giá

1. Vì sao developer JDK, build JDK, compiler JDK và production runtime có thể khác nhau?
2. --release cung cấp những bảo đảm nào khi biên dịch?
3. Vì sao cần ghi full version string thay vì chỉ major version?
4. Dependency tree runtime có thể bỏ sót những nhóm dependency nào?
5. jdeps --jdk-internals giúp tìm vấn đề gì và giới hạn của nó là gì?
6. Khi nào cần dùng jdeprscan?
7. jnativescan giúp xác định những dependency nào?
8. Vì sao phải phân biệt agent startup và dynamic attach?
9. Native access restrictions ảnh hưởng tới JNI và FFM như thế nào?
10. Vì sao phải kiểm tra Security Manager dependency khi nâng cấp từ runtime cũ?
11. Container CPU/memory limit có thể làm thay đổi hành vi JVM ra sao?
12. Vì sao locale, timezone và charset cần regression test?
13. Vì sao compile pass chưa đủ để đánh dấu dependency Verified?
14. Một inventory cần những trường nào để có thể bàn giao?
15. Vì sao phải kiểm kê cron job, batch và DR riêng?
16. Khi nào một rủi ro cần được coi là blocker cho canary?
17. Những chỉ số nào cần so sánh trước và sau nâng cấp?
18. Vì sao cần lưu image digest, artifact checksum và full JDK build?

**Tiêu chí hoàn thành:** Bạn có danh mục đầy đủ JDK theo từng vai trò, ứng dụng và dependency, native/agent, cấu hình JVM, OS/container và các môi trường triển khai. Mỗi mục có owner, target version, rủi ro và bằng chứng kiểm thử. Nhóm triển khai có thể dùng danh mục đó để quyết định thứ tự nâng cấp, xác minh compatibility và chuẩn bị rollback.

## 21. Nguồn tham khảo chính thức

- [Oracle JDK 25 Migration Guide](https://docs.oracle.com/en/java/javase/25/migrate/index.html)
- [Oracle JDK 25 — Preparing for Migration](https://docs.oracle.com/en/java/javase/25/migrate/preparing-migration.html)
- [Oracle JDK 25 — Significant Changes](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html)
- [Oracle JDK 25 — Removed APIs](https://docs.oracle.com/en/java/javase/25/migrate/removed-apis.html)
- [Oracle JDK 25 — Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/25all-relnotes.html)
- [Oracle Java Downloads — Current JDK and LTS releases](https://www.oracle.com/java/technologies/downloads/)
- [Oracle JDK 25 — java command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [Oracle JDK 25 — jcmd command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html)
- [Oracle JDK 25 — jdeps command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeps.html)
- [Oracle JDK 25 — jdeprscan command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeprscan.html)
- [Oracle JDK 25 — jnativescan command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jnativescan.html)
- [Oracle JDK 25 — Restricted Methods and Native Access](https://docs.oracle.com/en/java/javase/25/core/restricted-methods.html)
- [Oracle JDK 25 — Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/25/security/security-manager-is-permanently-disabled.html)
- [OpenJDK JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472)
- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451)
- [OpenJDK JEP 471 — Deprecate the Memory-Access Methods in sun.misc.Unsafe for Removal](https://openjdk.org/jeps/471)
- [OpenJDK Quality Outreach](https://wiki.openjdk.org/display/quality/Quality+Outreach)

**Điểm cần nhớ:** Danh mục nâng cấp phải theo từng process và từng môi trường. Ghi đủ JDK role, vendor/build, dependency, agent/native access, JVM flags, OS/container và tích hợp bên ngoài. Mỗi phát hiện cần owner, mức rủi ro, bằng chứng và cách kiểm thử; chỉ khi có dữ liệu từ runtime đích mới nên chuyển trạng thái thành Verified.
