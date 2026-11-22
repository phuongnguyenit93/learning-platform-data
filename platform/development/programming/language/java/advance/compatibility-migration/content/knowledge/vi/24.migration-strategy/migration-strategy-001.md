# Chạy artifact hiện tại trên JDK đích trước khi quyết định biên dịch lại

Một dự án Java muốn nâng JDK thường bắt đầu bằng việc đổi phiên bản compiler, Maven/Gradle Wrapper, plugin và hàng loạt dependency. Cách làm đó có thể dẫn đến kết quả tốt, nhưng cũng khiến nhóm thay đổi **runtime, build tool, bytecode, dependency graph và source code cùng lúc**. Khi có sự cố, việc xác định nguyên nhân trở nên khó khăn: lỗi phát sinh do JVM mới, thư viện mới, cấu hình JVM, hay binary do compiler mới tạo ra?

Trong **Java Advance Compatibility Migration**, một chiến lược thực dụng là **chạy nguyên artifact đang phát hành trên JDK đích trước khi quyết định có cần biên dịch lại**. Nếu đang chạy JDK 17 và muốn lên JDK 21, hãy thử dùng chính JAR/WAR và tập thư viện của release hiện tại trên runtime Java 21, trong môi trường kiểm thử được kiểm soát. Câu hỏi ban đầu rất cụ thể:

> Binary và deployment bundle hiện tại có thể vận hành đúng trên JDK đích mà không phải đổi source hoặc rebuild ứng dụng không?

Kết quả có thể là **có**, **có với điều kiện thay runtime configuration**, **cần bổ sung dependency/runtime provider**, hoặc **cần thay code và build lại**. Mỗi đáp án dẫn tới một phạm vi migration khác nhau. Runtime-first không thay thế công việc nâng cấp dài hạn; nó giúp xác định việc nào thực sự cần làm, theo thứ tự có ít biến số và dễ rollback.

Bài này hướng dẫn từ việc đóng băng artifact, kiểm tra class-file compatibility, thử chạy trên JDK mới, kiểm chứng hành vi và vận hành, đến phân tích lỗi và quyết định khi nào mới nên recompile.

## 1. Vì sao phải thử runtime trước build?

### 1.1. Java chạy bytecode, không chạy trực tiếp source

Sau khi biên dịch, mã Java trở thành class files hoặc các artifact chứa bytecode. JVM thực thi những class đã được biên dịch này. Khi thay Java runtime, JVM không tự gọi lại `javac` để biên dịch toàn bộ application source.

Vì vậy, một ứng dụng đã biên dịch cho Java 17 **có thể** chạy trên Java 21 mà không phải build lại. Sự tương thích phải được kiểm tra, vì bytecode còn tham chiếu đến class, method, interface, provider, tài nguyên và hành vi runtime.

Không nên nhầm:

- **Source compatibility:** mã nguồn còn compile với compiler/API mới không?
- **Binary compatibility:** class file và các symbolic references còn link với runtime/library mới không?
- **Behavioral compatibility:** kết quả, lỗi và side effects có giống contract không?
- **Operational compatibility:** startup, performance, security, memory, agents và hệ thống xung quanh có hoạt động ổn định không?
- **Build compatibility:** build tool/plugins có chạy được trên JDK mới không?

Kiểm thử artifact hiện tại tập trung vào binary, behavioral và operational compatibility. Nó **không cần chứng minh** Gradle/Maven cũ đã chạy được trên JDK mới.

### 1.2. Hai hướng migration có mức rủi ro khác nhau

```text
Hướng thường gặp:
  Đổi JDK + đổi Gradle/Maven + nâng dependencies
      + compile lại + đổi application image
                         |
                         v
              Test: PASS hoặc FAIL
                         |
                         v
              Khó cô lập nguyên nhân

Hướng runtime-first:
  Artifact release A + dependency set D + JDK cũ
                         |
                    BASELINE
                         |
                         v
  Artifact release A + dependency set D + JDK đích
                         |
                    TEST/ĐỐI CHIẾU
                         |
                         v
        Chỉ sửa thứ thực sự không tương thích
                         |
                         v
         Recompile khi có lý do và bằng chứng
```

Hướng thứ hai không nói rằng mọi nâng cấp có thể làm thành từng bước riêng biệt. Một framework hoặc application server có thể bắt buộc nâng cùng JDK. Nhưng những dependency bắt buộc như vậy cần được **ghi rõ là biến số riêng**, không vô tình trộn vào phép thử.

### 1.3. Khi nào runtime-first hữu ích nhất?

Phương pháp này có giá trị cao đối với:

- Service lâu năm hoạt động ổn định, chỉ cần đổi JDK vì security/support policy.
- Dự án nhiều thư viện, plugin build hoặc code generator cũ.
- Hệ thống có yêu cầu rollback nhanh và giảm thay đổi nghiệp vụ.
- Nhóm muốn tách nhiệm vụ runtime migration khỏi build modernization.
- Nhiều service dùng chung một JDK image, cần xác định phạm vi nào chạy được nguyên binary.
- Bản build lịch sử khó tái tạo, nhưng release artifact và bộ runtime libraries vẫn còn.
- Đợt nâng JDK 17 → 21, nơi nhiều ứng dụng không cần sử dụng API Java 21 ngay lập tức.

Nếu artifact hiện tại đã có lỗ hổng nghiêm trọng hoặc framework hết hỗ trợ, việc chạy được trên JDK mới **không đủ** để công bố ứng dụng được hỗ trợ; phương pháp này vẫn là bước chẩn đoán có giá trị, không phải lý do trì hoãn xử lý bảo mật.

## 2. Định nghĩa đúng artifact cần giữ nguyên

### 2.1. Không phải lúc nào artifact chỉ là một JAR

| Mô hình triển khai | Đơn vị phải đóng băng để thử |
|---|---|
| Executable fat JAR | JAR, launcher/manifest, embedded libraries và resources |
| Thin JAR | Main JAR, toàn bộ `lib/`, classpath và startup script |
| Spring Boot executable JAR | JAR có launcher và nested libraries |
| WAR | WAR, application server/container version và shared libraries |
| EAR | EAR modules, server library layer và class loader policy |
| Application distribution | `bin/` scripts, `lib/` dependencies, config templates |
| Container | Application layers, runtime image, entrypoint và runtime config |
| Java agent | Agent JAR, manifest, attached/instrumented target JVM |
| Native-image executable | Không phải bytecode chạy trên JVM thường; dùng quy trình khác |

Với thin JAR, chỉ giữ checksum của `app.jar` trong khi thay toàn bộ JAR trong `lib/` là **không còn giữ nguyên runtime dependency graph**. Với WAR, thay server từ Java EE namespace `javax.*` sang Jakarta EE `jakarta.*` là migration framework/platform lớn hơn thay JDK.

### 2.2. Định danh bằng checksum

Ví dụ Linux/macOS:

```bash
sha256sum app.jar
sha256sum lib/*.jar
```

Ví dụ PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 .\app.jar
Get-ChildItem .\lib\*.jar |
    Get-FileHash -Algorithm SHA256
```

Lưu checksum ở baseline và môi trường thử. Nếu dùng container, ghi **image digest**, không chỉ tên tag có thể thay đổi như `latest`.

Khi test yêu cầu giữ nguyên binary, không chạy task build ghi đè output. Lấy artifact từ release repository hoặc build đã được kiểm chứng, rồi copy và xác nhận checksum.

### 2.3. Giữ đúng cách launch

Một executable JAR có thể khởi động bằng:

```bash
java -jar app.jar
```

Nhưng một thin JAR có thể dùng:

```bash
java -cp "app.jar:lib/*" com.example.Main
```

Dấu phân tách classpath trên Windows thường là `;` thay vì `:`. Một Spring Boot JAR có launcher riêng, không nên giải nén rồi đổi main class tùy ý. Mục tiêu là **giữ launcher semantics** của release đang chạy và chỉ đổi JVM thực thi.

## 3. Lập baseline trước khi chuyển JDK

### 3.1. Một baseline tái lập được phải có gì?

Tối thiểu:

1. Application release ID, git commit và artifact checksum.
2. Version của dependency runtime, bao gồm transitive dependencies.
3. Java vendor, major/update/build của runtime cũ.
4. JVM flags, system properties, environment variables liên quan.
5. OS, kiến trúc CPU, container/base image, CPU/memory limits.
6. Framework/application server version và cấu hình.
7. JDBC/HTTP/queue drivers, native libraries và Java agents.
8. Database schema, cấu hình endpoint, TLS/truststore.
9. Startup/health, kết quả tests hiện tại, error baseline.
10. Performance baseline: p95/p99, throughput, CPU/GC/memory.
11. Tình trạng batch jobs, scheduler, file imports/exports.
12. Chính sách dữ liệu, rollback và những phiên bản cùng tồn tại.

Không đưa password, token hoặc private keys vào hồ sơ. Chỉ ghi nguồn cấu hình và metadata cần thiết để tái tạo bằng cơ chế quản lý secrets được phép.

### 3.2. Đừng xem kết quả từ tuần trước là baseline hoàn toàn tương đương

Nếu artifact không đổi nhưng database, external services, container image hoặc traffic mix đã thay đổi, kết quả runtime cũ chưa chắc đối chiếu trực tiếp với runtime mới được.

Tốt nhất chạy **baseline và target gần nhau trong thời gian** với cùng fixtures và môi trường test tương đương. Nếu không thể, ghi rõ khác biệt còn tồn tại.

### 3.3. Kiểm tra JVM nào thực sự chạy ứng dụng

```bash
java -version
```

chỉ cho biết JVM được shell tìm thấy. Trong CI, service manager, Docker hoặc Kubernetes, ứng dụng có thể dùng JVM khác.

Ưu tiên path cụ thể:

```bash
"$TARGET_JDK/bin/java" -version
"$TARGET_JDK/bin/java" -jar app.jar
```

PowerShell:

```powershell
& "$env:TARGET_JDK\bin\java.exe" -version
& "$env:TARGET_JDK\bin\java.exe" -jar .\app.jar
```

Các biến `TARGET_JDK` là placeholder minh họa. Ngoài ra kiểm tra `JAVA_HOME`, `PATH`, `JAVA_TOOL_OPTIONS` và `JDK_JAVA_OPTIONS`. Một số biến có thể chèn JVM options ngoài script và làm sai giả định “chỉ đổi JDK”.

## 4. Hiểu giới hạn class-file compatibility

### 4.1. JDK mới thường có thể đọc class file cũ

Ví dụ:

| Phiên bản Java dùng để tạo class file | Major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

JVM JDK 21 hỗ trợ class-file versions cũ trong phạm vi compatibility. Vì thế một JAR được biên dịch bằng JDK 8 hoặc 17 **không cần mặc định compile lại** chỉ để Java 21 đọc được class file.

Tuy nhiên, JVM có đọc được bytecode không đồng nghĩa mọi method reference còn resolve hoặc mọi behavior còn phù hợp.

### 4.2. Hướng ngược lại không tự hoạt động

Nếu artifact được build cho Java 21 (class-file major 65), chạy trên Java 17 có thể gặp:

```text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version
  of the Java Runtime (class file version 65.0)
```

Lựa chọn hợp lý:

- Dùng runtime Java 21 hoặc mới hơn phù hợp.
- Recompile với `--release 17` **nếu source/dependencies cho phép**.
- Phát hành binary riêng theo minimum supported JDK.
- Thay source nếu đang dùng Java 21 APIs/language features không có trong Java 17.

Không có JVM flag như `--add-opens` có thể biến class file major 65 thành major 61.

### 4.3. Xem bytecode khi cần

```bash
javap -classpath app.jar -verbose com.example.Main
```

Trong output có trường `major version`. Với fat JAR/framework layout đặc thù, cần chỉ đúng class path hoặc dùng công cụ đọc archive phù hợp.

Một class không đại diện mọi class của artifact: dependencies, generated classes, multi-release entries hoặc shaded code có thể mang major version khác.

### 4.4. Multi-release JAR là trường hợp đặc biệt

Một JAR có manifest `Multi-Release: true` có thể chứa:

```text
META-INF/versions/9/
META-INF/versions/11/
META-INF/versions/17/
META-INF/versions/21/
```

Cùng checksum nhưng JDK 17 và 21 có thể chọn implementation khác nhau. Vì vậy, khi một hàm chạy khác trên runtime mới, kiểm tra multi-release JAR trước khi quy nguyên nhân cho bytecode compiler hoặc JIT.

## 5. Kiểm tra artifact trước khi chạy thử

### 5.1. Xem archive và manifest

```bash
jar tf app.jar
```

Kiểm tra:

- Main-Class và launcher.
- Nested JARs hoặc classpath metadata.
- `META-INF/services/` cho ServiceLoader.
- `META-INF/versions/` cho multi-release JAR.
- `module-info.class` hoặc Automatic-Module-Name.
- Các native resources và cấu hình được đóng trong artifact.
- Các dependencies vốn do JDK cũ cung cấp.

Không sửa archive trong bước preflight; mục tiêu là nhận diện những điểm có thể ảnh hưởng runtime.

### 5.2. Phân tích static dependencies bằng jdeps

Ví dụ:

```bash
jdeps --jdk-internals app.jar
jdeps --recursive app.jar
jdeps --multi-release 21 --recursive app.jar
```

Một số dự án cần thêm classpath/module path để `jdeps` phân tích đúng dependencies. Đừng xem output trống như bằng chứng ứng dụng hoàn toàn tương thích: `jdeps` chủ yếu quan sát static bytecode dependencies, không phát hiện đầy đủ reflection, JNI, code generation hay class names đọc từ configuration.

### 5.3. Không bắt buộc chuyển classpath sang module path

Một Java 8 JAR không có module descriptor vẫn có thể chạy trên classpath trong JDK hiện đại. Chuyển sang JPMS/module path là một thay đổi có ý nghĩa riêng, không phải điều kiện mặc định để nâng JDK.

Nếu artifact đang chạy bằng classpath, hãy giữ nguyên cách launch trong phép thử đầu. Chỉ thử module path khi có mục tiêu rõ và ghi nhận đó là một biến khác.

## 6. Thiết kế phép thử cô lập đúng biến số

### 6.1. Ma trận tối thiểu

| Biến | Baseline | Runtime probe |
|---|---|---|
| App source revision | A | A |
| App artifact checksum | X | X |
| Dependency artifacts | D | D |
| Business config | C | C |
| Database/test data | S | S |
| OS/container | E | E, nếu khả thi |
| JDK runtime | Old | Target |
| Build/recompile | Không | Không |

Thay đổi duy nhất được mong đợi là JDK runtime. Nếu chuyển base image làm thay certificate store hoặc libc, phải ghi khác biệt đó và diễn giải kết quả phù hợp.

### 6.2. Không chạy build trong runtime-only probe

Nếu thực hiện:

```bash
./gradlew clean build
java -jar build/libs/app.jar
```

trên JDK mới, đây là phép thử **build + run**, không phải “chạy artifact hiện tại”. Build plugin, annotation processor, compiler và dependency resolution có thể tạo binary mới.

Trong phép thử runtime-only, lấy binary release cũ, giữ checksum và chạy nó trực tiếp. Build modernization là nhiệm vụ khác sau khi đã có baseline runtime.

### 6.3. Thử trong môi trường an toàn

Không cho một artifact chưa được kiểm chứng ghi vào database production hoặc gửi payment/email/queue message thật. Dùng staging/sandbox với dữ liệu đại diện, tài khoản test và cơ chế reset state.

Một smoke test quá đơn giản có thể không phát hiện lỗi; nhưng test phá hủy dữ liệu thật cũng không phù hợp. Cần điều phối quyền và phạm vi test theo chính sách vận hành.

## 7. Lần chạy đầu trên JDK đích

### 7.1. Giữ command line semantics

Ví dụ:

```bash
"$TARGET_JDK/bin/java" \
  -Xms512m \
  -Xmx2g \
  -jar app.jar \
  --app.profile=staging
```

Các tham số chỉ minh họa. Trong migration thật, dùng heap/flags đã được baseline xác định thay vì tự chọn một giá trị mới khiến hiệu năng không so sánh được.

Nếu JVM từ chối một option đã bị loại bỏ, xử lý nó như **runtime launch configuration issue**, ghi rõ flag nào được thay đổi. Không mở source code chỉ để giải quyết một option không còn hợp lệ.

### 7.2. Tách log từng lần chạy

```text
evidence/
  baseline/
    java-version.txt
    launch-command.txt
    stdout.log
    errors.log
    test-results/
    metrics/
  target/
    java-version.txt
    launch-command.txt
    stdout.log
    errors.log
    test-results/
    metrics/
```

Nếu test nhiều JDK update/vendor, thêm version vào đường dẫn evidence. Cần giữ timestamp, checksum và environment metadata để có thể tái hiện.

### 7.3. Startup thành công chưa đủ

Một service có thể boot và trả `/health` thành công nhưng chưa thực thi:

- ORM mapping hoặc database write.
- Serialization XML/JAXB/Jackson.
- TLS/mTLS client handshake.
- Native compression/crypto.
- Queue listener.
- Scheduler và batch job.
- Class loading qua reflection.
- ServiceLoader/provider.
- Feature-specific code path.
- Reload cấu hình, retry và graceful shutdown.

Do đó, pass startup chỉ là bước mở đầu.

## 8. Các tầng kiểm chứng nên có

### Tầng 0: JVM và startup

Xác nhận JVM chấp nhận flags, nạp main class/module, khởi tạo framework và không có fatal error.

### Tầng 1: Smoke tests

Gọi một tập chức năng cơ bản đại diện:

- Health và version endpoints.
- Read-only API.
- Một workflow ghi dữ liệu staging có thể hoàn tác.
- Database/cache connection.
- Authentication và HTTPS sandbox call.

### Tầng 2: Integration và contract tests

Kiểm tra XML/JSON, database, queue, REST/SOAP, transaction, OAuth/TLS, file encoding, cache/session và business invariants. So sánh response, side effects và error mapping chứ không chỉ HTTP status.

### Tầng 3: Hiệu năng và tài nguyên

Đo startup, time to readiness, warm-up, throughput, latency p50/p95/p99, error rate, CPU/JIT, GC, memory RSS, threads và file descriptors. JDK target có thể đạt throughput tốt hơn sau warm-up nhưng có cold latency kém hơn.

### Tầng 4: Soak và failure recovery

Duy trì tải phù hợp, thử long-lived connections, DNS/TLS changes, database reconnect, pod restarts, shutdown, timeout và resource leaks. Đây là nơi những bất tương thích chỉ xuất hiện sau vài giờ có thể bộc lộ.

Mỗi hệ thống chọn tầng kiểm chứng theo rủi ro. Không cần làm mọi bài kiểm thử cho một CLI đơn giản, nhưng cũng không được dùng một lần gọi health endpoint để kết luận service tài chính production tương thích.

## 9. Runtime JDK mới có thể thiếu API từng được bundled

### 9.1. JEP 320 và JDK 11

Từ JDK 11, các module Java EE/CORBA trước đây đi kèm JDK, bao gồm JAXB, JAX-WS, Activation trong phạm vi liên quan, bị loại bỏ khỏi bản phân phối JDK.

Một binary Java 8 có thể gặp:

```text
java.lang.NoClassDefFoundError:
  javax/xml/bind/JAXBContext
```

hoặc:

```text
java.lang.ClassNotFoundException:
  javax.activation.DataHandler
```

Class file Java 8 vẫn được JDK 21 nạp; vấn đề là **runtime API/provider không có**, không phải bytecode quá cũ.

### 9.2. Quyết định sau khi gặp lỗi

1. Xác định caller và class thật sự bị thiếu.
2. Kiểm tra API đã nằm trong dependency JAR cũ hay lấy từ JDK 8.
3. Chọn external API/runtime implementation đúng thế hệ namespace.
4. Thử thêm dependency trong một nhánh kiểm chứng mới.
5. Chạy lại XML/SOAP/attachment contract tests.
6. Chỉ chuyển source sang `jakarta.*` khi framework/roadmap yêu cầu.

Một khi bổ sung runtime JAR hoặc repackage, **deployment bundle không còn giữ nguyên**. Phải ghi phép thử mới là runtime adaptation, không mô tả tiếp như artifact unchanged.

### 9.3. Không thể bật module đã mất bằng flag

```bash
java --add-modules java.xml.bind -jar app.jar
```

không khôi phục `java.xml.bind` trên JDK không còn module đó. Cần dependency ngoài JDK hoặc source/framework migration phù hợp.

## 10. Reflection và encapsulation của JDK

### 10.1. InaccessibleObjectException

JDK mới siết strong encapsulation với JDK internals. Một framework cũ dùng deep reflection vào `java.base` có thể lỗi:

```text
java.lang.reflect.InaccessibleObjectException:
module java.base does not "opens java.lang" to ...
```

JDK 17 là mốc liên quan JEP 403. Lỗi runtime này có thể xuất hiện dù artifact được biên dịch bằng JDK cũ và class-file version hợp lệ.

### 10.2. Workaround là bằng chứng, không phải đích đến

Để xác nhận nguyên nhân trong môi trường thử, có thể mở **đúng package cần thiết**:

```bash
--add-opens java.base/java.lang=ALL-UNNAMED
```

Nếu sử dụng named modules, target có thể là module cụ thể. Đừng mở hàng loạt package chỉ để làm hết warning. Flag mở quyền reflection không sửa API đã bị xóa và không bảo đảm thư viện cũ được hỗ trợ lâu dài.

Quy trình hợp lý:

- Tìm library/agent gây reflective access.
- Xác minh vendor version hỗ trợ JDK đích.
- Thử workaround giới hạn nếu cần cô lập.
- Ghi workaround với owner/thời hạn.
- Nâng dependency và bỏ workaround trong phase riêng.

### 10.3. Không quy mọi reflection issue cho application source

Exception có thể phát sinh trong dependency, serializer, ORM, DI framework, mocking library hoặc agent. Recompile application source có thể **không thay đổi** điều này. Cần tìm đúng component gọi reflection.

## 11. JVM flags, defaults và startup configuration

### 11.1. Flag cũ có thể bị từ chối

Qua nhiều release, các flags liên quan GC, memory, compiler hoặc module access có thể bị xóa hoặc đổi default. Nếu JVM dừng ngay vì `Unrecognized VM option`, phân loại đó là **launch configuration incompatibility**.

Ghi:

- Flag cũ.
- Phiên bản JDK cũ/mới.
- Nơi khai báo: startup script, container, Helm chart, service manager.
- Phương án được vendor hỗ trợ.
- Ảnh hưởng tới performance/monitoring sau khi thay.

Không giữ flag cũ bằng cách sửa application Java source.

### 11.2. Cẩn thận với các flags ẩn trong môi trường

Kiểm tra `JAVA_TOOL_OPTIONS` và `JDK_JAVA_OPTIONS`. Chúng có thể khiến cùng command line nhìn thấy trong pipeline chạy với options khác nhau.

Với server, Java arguments có thể đến từ service manager hoặc container entrypoint. Cần xác nhận **process command line của JVM thật**, không chỉ script template.

### 11.3. Cấu hình bảo mật không nên nới lỏng vô căn cứ

Nếu runtime mới từ chối TLS certificate hoặc thuật toán yếu, không tắt validation để đạt smoke test. Sửa certificate chain, server policy, truststore hoặc thư viện phù hợp với yêu cầu bảo mật.

## 12. Charset, locale và timezone

### 12.1. JEP 400: default charset UTF-8 từ JDK 18

Đặc biệt khi nâng JDK 17 → 21, các API dựa vào default charset có thể hoạt động khác nếu môi trường cũ dùng encoding không phải UTF-8.

Ví dụ:

```java
String text = new String(bytes);
byte[] encoded = text.getBytes();
```

Nếu dữ liệu cũ là encoding khác, source này không chỉ rõ hợp đồng encoding. Bản runtime mới có thể đọc sai dấu, tạo dữ liệu đầu ra khác hoặc thất bại ở bước parse.

Cần nhớ: những API như `Files.readString(Path)` vốn đã dùng UTF-8 theo contract, không phải mọi file read đều thay đổi vì JEP 400.

### 12.2. Hướng sửa bền vững

```java
String text = new String(bytes, StandardCharsets.UTF_8);
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);
```

Nếu dữ liệu legacy dùng charset khác, phải chọn charset đúng theo nguồn. Việc sửa source là một lý do **có cơ sở** để compile lại, sau khi runtime-only probe chứng minh khác biệt.

Không tự đặt `file.encoding` toàn JVM chỉ để che một file legacy rồi không kiểm tra các luồng dữ liệu khác.

### 12.3. Locale/timezone data

Nâng JDK có thể cập nhật timezone database hoặc Unicode/locale data. Những trường hợp cần thử:

- Format ngày/giờ có timezone.
- Lịch thanh toán/tác vụ theo daylight saving time.
- CSV/Excel exports theo locale.
- Case conversion và sorting tiếng Việt.
- Number, decimal, currency formatting.
- JSON/XML timestamps và dữ liệu lưu dài hạn.

Một thay đổi có thể là cập nhật dữ liệu nền tảng đúng, nhưng vẫn cần được đánh giá theo business contract và backward compatibility.

## 13. TLS, DNS, network và I/O

### 13.1. TLS có thể thay đổi khi source không đổi

JDK mới hoặc update có thể cập nhật truststore/cipher/security policy. Triệu chứng:

```text
javax.net.ssl.SSLHandshakeException
PKIX path building failed
Received fatal alert: handshake_failure
```

Trước khi recompile:

1. Xác định endpoint và proxy thật.
2. Kiểm tra certificate chain, truststore và hostname.
3. So sánh TLS protocol/cipher được hỗ trợ.
4. Xác định thay đổi do JDK, base image hay server.
5. Sửa cấu hình/hạ tầng theo chính sách bảo mật.
6. Chạy lại integration tests.

### 13.2. DNS và IP family

Nếu JDK runtime chuyển cùng với OS/container image mới, DNS resolver, IPv4/IPv6 preference hoặc search domain có thể khác. Một service bind `127.0.0.1` không mặc nhiên lắng nghe `::1`. Kiểm tra hostname, port, cache, network namespace và routing trước khi gán lỗi cho code.

### 13.3. TCP/UDP edge cases

Một lần `InputStream.read(buffer)` không bảo đảm trả đủ message; UDP không bảo đảm giao hàng. Sự khác biệt timing/network stack có thể làm lộ bug cũ trong framing, timeout hoặc concurrent close.

Nếu lỗi xuất hiện sau đổi JDK, kiểm tra API contract và input conditions. Không kết luận JDK phá hợp đồng chỉ vì code đã “tình cờ chạy được” trên baseline.

## 14. Native libraries và agents

### 14.1. JNI/JNA và OS ABI

Một JAR Java có thể chạy được trên JVM mới nhưng native library không nạp vì thiếu binary, architecture sai hoặc linked dependencies không tương thích.

Lỗi thường gặp:

```text
java.lang.UnsatisfiedLinkError
```

hoặc JVM native crash. Kiểm tra library path, version, checksum, OS/CPU ABI, architecture và wrapper behavior. Có trường hợp chỉ cần update native runtime library; cũng có trường hợp phải sửa JNI/JNA bridge.

### 14.2. Java agents

Metrics agent, tracing agent, bytecode instrumentation và attach tooling có vòng đời hỗ trợ JDK riêng. Chúng có thể dùng ASM/Byte Buddy hoặc JVMTI. Nếu agent không hỗ trợ JDK đích, lỗi có thể xuất hiện ngay khi JVM startup dù business JAR vẫn hợp lệ.

Nên kiểm tra:

- Agent version và minimum/maximum supported JDK.
- Class-file version mà agent có thể instrument.
- Startup `-javaagent` vs dynamic attach.
- Module access và security policy.
- Compatibility trong đúng container/runtime.

JDK 21 có JEP 451 liên quan cảnh báo khi dynamic agent loading. Phân biệt warning mới với lỗi fatal và không bỏ observability production chỉ để tắt warning.

### 14.3. Không mặc định phải chuyển native code sang FFM

FFM API final từ JDK 22. Nếu mục tiêu chỉ là chạy Java 17 artifact trên Java 21, việc chuyển JNI sang FFM không phải điều kiện mặc định. Native bridge migration có yêu cầu ABI, ownership, callback và platform testing riêng; tách thành dự án khác khi phù hợp.

## 15. Application server và mô hình triển khai

### 15.1. WAR không chạy độc lập như JAR

Nếu artifact là WAR, runtime owner là application server hoặc servlet container. Để kiểm thử ảnh hưởng **chỉ JDK**:

- Giữ nguyên WAR checksum.
- Giữ server version nếu server hỗ trợ cả hai JDK.
- Giữ shared libraries, data sources, deployment descriptors.
- Thay JVM chạy server.
- Deploy và chạy contract tests.

Nếu server cũ không hỗ trợ JDK đích thì không thể làm phép thử hoàn toàn cô lập. Khi đó cần ghi rõ **JDK + server migration**.

### 15.2. Java EE javax và Jakarta jakarta không binary-compatible

Một WAR dùng `javax.servlet.*` không tự chạy trên một container chỉ hỗ trợ `jakarta.servlet.*`. Hai package là binary names khác nhau.

Nếu việc nâng server buộc chuyển namespace, cần source/framework/dependency migration; scope Maven `provided` không ánh xạ hai API thành một.

### 15.3. Executable JAR với embedded container

Một Spring Boot executable JAR có thể chứa embedded servlet engine. Khi chạy nguyên JAR trên JDK đích, giữ nguyên embedded engine là một phần quan trọng của phép thử.

Nếu sau đó nâng Spring Boot major version, serializer, embedded engine và Servlet API có thể thay đổi. Đó là **framework/packaging migration**, phải test riêng.

## 16. Các lỗi runtime điển hình và cách phân loại

| Triệu chứng | Tầng cần xem | Có phải lập tức recompile? |
|---|---|---|
| `Unrecognized VM option` | JVM startup flags | Không, xem cấu hình |
| `UnsupportedClassVersionError` | Class-file level cao hơn runtime | Dùng JDK đúng hoặc build target thấp hơn |
| `ClassNotFoundException` | Dynamic classpath/provider/classloader | Chưa, tìm class và loader |
| `NoClassDefFoundError` | Runtime linkage hoặc initialization | Chưa, xem root cause |
| `NoSuchMethodError` | API/implementation binary mismatch | Chưa, kiểm tra dependency graph |
| `NoSuchFieldError` | Field descriptor/version mismatch | Chưa, xem JAR thực |
| `AbstractMethodError` | Interface implementation không khớp | Thường sửa dependency trước |
| `IllegalAccessError` | Binary/module access | Điều tra module/classloader |
| `InaccessibleObjectException` | Deep reflection bị chặn | Nâng framework hoặc workaround giới hạn |
| `ServiceConfigurationError` | SPI/provider resources | Kiểm tra provider và packaging |
| `UnsatisfiedLinkError` | Native library/ABI/path | Kiểm tra native binary trước |
| `ExceptionInInitializerError` | Static initialization failure | Xem exception gốc |
| `SSLHandshakeException` | TLS/certificate/security | Kiểm tra truststore/server |
| Dữ liệu text sai encoding | Default charset/locale | Có thể cần source fix sau khi xác nhận |
| Fat JAR chạy nhưng WAR fail | Container/classloader/provider | Kiểm tra deployment target |
| Cold-start latency cao | JIT/GC/class loading/CPU | Đo và cô lập |
| Performance regression | JVM/OS/dependency/backend | Không sửa code trước khi có bằng chứng |

Bảng chỉ gợi ý điểm điều tra. Mỗi loại lỗi có nhiều root causes và cần full stack trace, artifact details và môi trường tái hiện.

## 17. Phương pháp điều tra lỗi theo tầng

### Bước 1. Đọc lỗi gốc

Lấy full stack trace và chuỗi `Caused by`. Xác định lỗi ở JVM launch, class loading, framework bootstrap hay request path.

### Bước 2. Xác định đúng class/method

Nếu báo `NoSuchMethodError`, tìm caller và callee được nạp từ JAR nào. Nếu `ClassNotFoundException`, kiểm tra dynamic lookup và classloader.

### Bước 3. Kiểm tra dependency versions thực

Cùng application checksum không bảo đảm classpath giống nhau nếu thư viện được lấy từ server/shared directory. Với thin JAR, xác nhận tất cả dependencies giữ nguyên.

### Bước 4. Xác định mức thay đổi JDK

Kiểm tra module/API bị loại bỏ, reflection access, native flags, security defaults, timezone/charset và agents.

### Bước 5. Tái hiện ở tình huống nhỏ

Ví dụ một API endpoint sử dụng JAXB hoặc một test fixture có ký tự Unicode. Tái hiện cụ thể giúp tránh đổi framework toàn bộ để sửa một lỗi.

### Bước 6. Thử giải pháp nhỏ nhất có căn cứ

Nếu thiếu runtime provider thì bổ sung đúng runtime dependency ở nhánh thử mới; nếu source xử lý charset sai thì sửa source; nếu JDK flag sai thì sửa startup config.

### Bước 7. Chạy lại toàn bộ các gate liên quan

Một workaround có thể khiến startup pass nhưng làm behavior hoặc bảo mật khác. Sau thay đổi phải test chức năng, contract, resource và performance trong phạm vi có rủi ro.

## 18. Chẩn đoán bằng công cụ runtime

### 18.1. Quan sát JVM/version

```bash
"$TARGET_JDK/bin/java" -version
"$TARGET_JDK/bin/java" -XshowSettings:properties -version
```

Properties có thể chứa environment paths, vì vậy cần lọc thông tin trước khi chia sẻ.

Với một process JVM có quyền truy cập thích hợp:

```bash
jcmd <pid> help
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
```

Lệnh có thể khác theo JDK/build, và image runtime tối giản có thể không cung cấp `jcmd`.

### 18.2. Quan sát classloading

Trên HotSpot hiện đại, có thể dùng:

```bash
java -Xlog:class+load=info -jar app.jar
```

để quan sát class được nạp từ nguồn nào. Log có thể rất lớn; sử dụng trong chẩn đoán có kiểm soát, đặc biệt với server nhiều classloader.

### 18.3. GC logging và JFR

```bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
```

JFR có thể bắt startup và runtime behavior:

```bash
java \
  -XX:StartFlightRecording=filename=target.jfr,settings=profile \
  -jar app.jar
```

JFR/GC logs giúp đánh giá startup, allocation, GC, JIT activity và resource pressure theo JDK/settings hỗ trợ. Không xem một JFR event là bằng chứng duy nhất về nguyên nhân latency. Cần đối chiếu application metrics và tải bên ngoài.

## 19. Chạy artifact cũ có thể vẫn không đáp ứng chính sách hỗ trợ

### 19.1. Technical compatibility khác vendor support

Một framework/version cũ có thể chạy qua smoke và integration tests trên JDK 21, nhưng vendor chưa công bố hỗ trợ JDK đó.

Phân biệt:

- **Thực tế kỹ thuật:** binary đã vượt các bài kiểm chứng nào?
- **Chính sách hỗ trợ:** framework/vendor có cho phép tổ hợp không?
- **Bảo mật:** dependency có còn nhận fixes?
- **Vận hành:** nhóm có đủ khả năng xử lý sự cố nếu vendor không hỗ trợ không?

Một sản phẩm có yêu cầu compliance có thể bắt buộc nâng framework dù runtime-only test pass. Đây là quyết định support/security, không phải bằng chứng JDK cũ compile source tốt hơn.

### 19.2. Runtime-first là phép thử, không phải lời hứa giữ JAR cũ vô thời hạn

Sau khi nâng runtime thành công, vẫn nên có kế hoạch nâng Maven/Gradle, plugins, framework và dependencies theo chính sách dài hạn.

Điểm khác biệt là **làm theo phase có evidence**, giảm số biến đồng thời.

## 20. Chọn nhánh xử lý sau kết quả thử

| Kết quả | Diễn giải | Hành động tiếp |
|---|---|---|
| Startup + contract + SLO đạt | Binary phù hợp trong phạm vi test | Cân nhắc runtime-only rollout |
| Startup đạt, nhiều path chưa test | Bằng chứng chưa đủ | Bổ sung integration/contract tests |
| JVM flag không hợp lệ | Launch config | Sửa flags và thử lại |
| Thiếu JAXB/JAX-WS runtime | API/provider không còn bundled | Thêm dependency ngoài JDK ở nhánh mới |
| Reflection bị chặn | Framework/agent dùng JDK internals | Giải pháp phiên bản mới hoặc `--add-opens` giới hạn |
| Native library fail | OS/ABI/native dependency | Thay native runtime, có thể cần bridge change |
| TLS fail | Cert/protocol/truststore | Sửa hạ tầng/chính sách bảo mật |
| Dữ liệu mã hóa sai | Charset/locale contract | Có thể cần code fix/recompile |
| Bytecode mới hơn JVM | Class-file target không phù hợp | Nâng runtime hoặc compile cho target thấp |
| Regression hiệu năng | JIT/GC/resource/backend | Đo và cô lập, không tự đổi source |
| Application server unsupported | Runtime platform | Lập kế hoạch server/framework migration |
| Framework policy không cho phép | Support/compliance | Nâng framework và kiểm tra lại |

Một phép thử thành công không khẳng định không bao giờ cần recompile. Nó xác nhận **khả năng chạy của release artifact cụ thể trên JDK đích với điều kiện đã kiểm chứng**.

## 21. Ba cấp thay đổi sau baseline

### 21.1. Cấp A — Runtime-only

Application artifact, dependencies và business config được giữ nguyên; thay JDK runtime. Một số launch flags có thể buộc phải đổi để JVM start, nhưng phải ghi rõ là thay đổi cấu hình kèm theo.

Đây là phạm vi nhỏ nhất, thường dễ rollback nhất.

### 21.2. Cấp B — Runtime/packaging adaptation

Không sửa source nhưng có thể:

- Thêm JAXB/JAX-WS/Activation runtime dependencies.
- Nâng một native JAR hoặc agent.
- Chỉnh truststore và runtime configuration.
- Repackage thin JAR/distribution hoặc cập nhật thư viện runtime.
- Thay container base image có support JDK mới.

Khi thay dependency hoặc package, checksum deployment bundle không còn giống baseline. Cần gọi đúng là **artifact adaptation** và lưu evidence riêng.

### 21.3. Cấp C — Recompile/source migration

Khi phải đổi import, sử dụng API mới, sửa logic encoding, cập nhật framework major hoặc thay bytecode target, nhóm sẽ tạo artifact mới.

Phân biệt hai việc:

- **Recompile cùng source:** thay compiler/toolchain hoặc packaging, không sửa business code.
- **Source migration:** đổi source/config/generated code rồi mới compile.

Cấp C có phạm vi test rộng hơn, đặc biệt nếu API/public signatures, serialized form hoặc consumer compatibility thay đổi.

## 22. Tại sao recompile cùng source vẫn cần test riêng?

Một lần recompile có thể thay:

- Class-file major version.
- Compiler-emitted bytecode.
- Annotation processor output.
- Default `serialVersionUID` khi class không định nghĩa tường minh.
- Build-time generated resources.
- Manifest và launcher metadata.
- Resolved transitive dependencies.
- Compiler flags, parameter/debug metadata.
- Multi-release JAR entries.
- Packaging layout và service descriptors.

Không phải các thay đổi này sẽ xảy ra trong mọi build, nhưng recompile đã thêm một biến cần kiểm chứng.

Nếu nguyên artifact chạy tốt trên Java 21 mà Gradle plugin cũ không chạy trên JDK 21, đó có thể chỉ là **build tool migration issue**. Kết quả runtime-first giúp tách việc nâng Gradle/Maven khỏi việc đổi production JVM.

## 23. Compiler JDK, source level, target và --release

### 23.1. Cần phân biệt rõ

- **Build JVM:** JDK đang chạy Maven/Gradle.
- **Compiler JDK:** JDK cung cấp `javac` cho JavaCompile.
- **Language level:** cú pháp Java source được chấp nhận.
- **Target class-file level:** bytecode được tạo.
- **Java platform API level:** API chuẩn mà code được phép dùng.
- **Minimum runtime JDK:** JVM thấp nhất phải chạy được artifact.

Một JDK mới có thể compile source cho Java cũ khi hỗ trợ release target đó.

### 23.2. Ví dụ --release

```bash
javac --release 17 -d out src/com/example/Main.java
```

Trên JDK thích hợp, `--release 17` giới hạn language/bytecode/platform API cho Java 17 trong phạm vi của compiler. Nhưng nó **không** đảm bảo mọi third-party dependency JAR có bytecode phù hợp Java 17.

Cần kiểm tra min supported JDK của dependencies và chạy artifact trên runtime thấp nhất thực tế.

### 23.3. Không phải cứ chạy Java 21 là cần target 21

Một service muốn dùng JDK 21 làm runtime nhưng vẫn phải rollback Java 17 có thể chọn giữ bytecode target 17. Chỉ cần target Java 21 khi sản phẩm thật sự dùng language/API features của Java 21 hoặc support policy yêu cầu.

Thay compiler target là quyết định compatibility với consumers, không chỉ chỉnh version để “đồng bộ số”.

## 24. Case study A — JAR Java 17 chạy được trên Java 21

Giả sử một service có:

```text
Application: order-service-4.8.1.jar
Built with: JDK 17
Runtime baseline: JDK 17
Target runtime: JDK 21
Packaging: executable JAR
SHA-256: X
```

Thử nghiệm:

1. Lấy artifact phát hành, ghi checksum X.
2. Chạy baseline trên JDK 17 và lưu test/metrics.
3. Copy nguyên JAR sang staging dùng JDK 21, kiểm tra checksum X.
4. Dùng cùng config/services/test data.
5. Chạy startup + smoke.
6. Gọi các đường đặt hàng, thanh toán sandbox, inventory và batch.
7. Test serialization/file/TLS, error handling, graceful shutdown.
8. Đo cold starts, p99, CPU/GC và soak.
9. So sánh với baseline.

Nếu mọi gate đạt, có thể **nâng runtime trước và giữ JAR**. Sau đó thực hiện build-tool/dependency modernization trong phase khác.

Nếu chỉ p99 lúc autoscaling tăng, cần đánh giá warm-up/CPU thay vì mặc định phải recompile code.

## 25. Case study B — JAR Java 8 lỗi JAXB trên Java 21

Baseline Java 8 có class dùng `javax.xml.bind.JAXBContext`. Chạy nguyên binary trên Java 21 báo:

```text
NoClassDefFoundError: javax/xml/bind/JAXBContext
```

Đây là dấu hiệu thiếu API/runtime sau khi JDK 11 loại bỏ module liên quan. Thực hiện:

1. Xác nhận bytecode Java 8 vẫn load được.
2. Xác định JAXB API/runtime đã được cung cấp từ đâu ở baseline.
3. Chọn dependency JAXB thế hệ `javax` phù hợp.
4. Thử bổ sung dependency trên runtime classpath trong nhánh mới.
5. Test marshal/unmarshal và các schema/contract XML thực.
6. Nếu framework mới bắt buộc `jakarta`, chuyển sang source/API migration riêng.

Không cần ngay lập tức đổi source thành `jakarta.xml.bind.*` chỉ vì JDK 21 không bundled JAXB.

## 26. Case study C — WAR và application server

Một WAR cũ chạy trên Jakarta/Java EE server version S, Java 11. Muốn đổi lên Java 21:

- Nếu S hỗ trợ Java 21, thử **nguyên WAR + server S**, chỉ thay JVM.
- Nếu S không hỗ trợ Java 21, bắt buộc nâng server và ghi nhận đây là **JDK + server migration**.
- Nếu server mới chuyển từ `javax.servlet` sang `jakarta.servlet`, có khả năng phải đổi source/framework.
- Nếu server cung cấp API/provider mới, WAR có thể xung đột với những JAR ở `WEB-INF/lib`.

Đừng kết luận “artifact cũ không tương thích Java 21” khi nguyên nhân là application server không hỗ trợ Java 21 hoặc Servlet namespace generation khác.

## 27. Dữ liệu lưu trữ và rollback

### 27.1. Runtime-only vẫn có thể đổi dữ liệu đầu ra

Cùng JAR nhưng default charset, timezone database hoặc provider behavior khác có thể làm file hoặc message được ghi ra khác nhau.

Cần test:

- Đọc file legacy đã tạo dưới JDK cũ.
- Ghi file trên JDK mới, đọc bằng bản cũ nếu rollback yêu cầu.
- Session/cache Java serialization.
- Queue message schema.
- Database date/time và decimal mapping.
- XML/JSON encode/decode.
- Native compression và checksum routines.

### 27.2. Hai chiều compatibility

- **Backward read:** phiên bản mới đọc dữ liệu được tạo từ bản cũ.
- **Forward read:** phiên bản cũ đọc dữ liệu mới tạo sau upgrade.

Nếu rolling deployment hoặc rollback có hai runtime cùng dùng shared state, cần xác định có phải hỗ trợ cả hai chiều không. Một phép thử startup không trả lời câu hỏi này.

### 27.3. Rollback phải giữ cả runtime và môi trường

Rollback không chỉ là giữ JAR cũ. Nếu nâng runtime image hoặc application server, cần giữ:

- Image/JDK baseline.
- Launcher/JVM flags.
- Server/container version.
- Library bundles và config tương ứng.
- Kế hoạch xử lý dữ liệu được ghi trong giai đoạn mới.

Nếu server cũ không thể đọc state mới, rollback có thể phải kèm data migration hoặc cơ chế dual-write/compatibility.

## 28. Kiểm chứng hiệu năng không phải chỉ so một số throughput

### 28.1. Cold và steady

JIT tối ưu dần code khi chạy; một JDK mới có thể có đường warm-up khác. Đo:

- JVM/app startup.
- Time to readiness.
- First-request latency.
- Time to stable SLO.
- Throughput sau warm-up.
- p95/p99 trong giai đoạn cold và steady.

Một service có steady throughput tốt nhưng cold p99 rất xấu có thể vẫn không phù hợp với autoscaling policy.

### 28.2. Đừng nhầm JIT với GC/OS/backend

Khi hiệu năng khác:

- Xem compiler/JIT CPU và compilation events nếu có lý do.
- Xem GC pauses và allocation.
- Xem CPU throttling trong container.
- Xem DB/queue/network latency.
- Xem class loading và lazy initialization.
- Chạy lặp lại, không chỉ một lần test.

Cùng một commit nhưng khác hardware, CPU quota hoặc base image có thể tạo chênh lệch đáng kể không xuất phát trực tiếp từ JDK compiler.

### 28.3. Dùng SLO làm ngưỡng quyết định

Báo cáo cần bao gồm error/timeout rate và latency percentiles, không chỉ requests per second. Thay JDK runtime nên được đánh giá theo **hành vi người dùng và chi phí vận hành**, không chỉ benchmark nhỏ trong IDE.

## 29. Phép thử phải có giới hạn kết luận rõ ràng

| Bằng chứng | Có thể kết luận | Không thể kết luận |
|---|---|---|
| JVM start | Runtime chấp nhận launcher và nạp một phần code | Mọi business path hoạt động |
| Health trả 200 | Health path hoạt động | Database writes/queue/serialization đều đúng |
| Integration pass | Các contract được thử đạt | Những path không được thử cũng đạt |
| Performance đạt trên staging | Workload/host được thử đáp ứng ngưỡng | Mọi production traffic đều tương đương |
| Artifact checksum giống | Application bytes không đổi | OS, JDK, libs ngoài hoặc server không đổi |
| jdeps không báo internals | Không phát hiện static dependency liên quan | Reflection/native hoàn toàn không có |
| Vendor support document | Tổ hợp được hỗ trợ theo tài liệu | Không còn bug hay regression thực tế |

Nên ghi phạm vi test, sample counts, environment và những rủi ro còn mở. Việc công bố “compatible” không kèm điều kiện rất dễ tạo hiểu nhầm.

## 30. Đề xuất cấu trúc báo cáo kỹ thuật

```yaml
migration_probe:
  objective: "Run existing artifact on target JDK first"
  application:
    release: "4.8.1"
    artifact: "order-service.jar"
    sha256: "<same-hash>"
    dependency_manifest: "<manifest-reference>"
  baseline:
    jdk: "<vendor-version-build>"
    image_digest: "<baseline-digest>"
  target:
    jdk: "<vendor-version-build>"
    image_digest: "<target-digest>"
  unchanged:
    application_binary: true
    runtime_dependency_set: true
    business_config: true
  known_environment_differences:
    - "JDK runtime"
  tests:
    startup: "PASS"
    smoke: "PASS"
    contract: "PASS"
    performance: "PENDING"
  result: "INCOMPLETE"
  decision:
    branch: "more-verification-required"
    owner: "<owner>"
```

Đây là template minh họa. Nếu đã thay runtime dependency, phải sửa giá trị `runtime_dependency_set` thành false hoặc công bố một probe mới. Không ghi PASS khi phần test đang PENDING.

## 31. Quy trình ra quyết định trong dự án thật

### Bước 1 — Chốt mục tiêu

Ví dụ: “Đưa release 4.8.1 từ Java 17 lên Java 21, ưu tiên không sửa source trong đợt đầu; đáp ứng SLO và vendor support policy.”

### Bước 2 — Đóng băng artifact

Lưu checksum, manifest, dependency set, launch command và image digest. Không rebuild.

### Bước 3 — Lấy baseline

Chạy artifact đó trên JDK cũ với test data/traffic đại diện; lưu logs và metrics.

### Bước 4 — Kiểm tra class-file và static dependencies

Xem class-file target, multi-release entries và API internals với công cụ phù hợp.

### Bước 5 — Chạy nguyên artifact trên JDK đích

Giữ cấu hình ứng dụng và external services ổn định, ghi rõ mọi thay đổi bắt buộc của JDK image hoặc JVM flags.

### Bước 6 — Test theo tầng

Startup → smoke → contract/integration → security/data → performance → soak/failover.

### Bước 7 — Phân loại lỗi

Tách launch flag, JDK API removal, dependency/provider, reflection, native/agent, TLS, charset, OS/container và performance.

### Bước 8 — Chọn sửa nhỏ nhất có hỗ trợ

Nếu chỉ cần config, sửa config. Nếu thiếu runtime dependency, bổ sung ở nhánh mới. Nếu API/logic sai, mới sửa source và compile.

### Bước 9 — Đánh giá support/security

Framework, dependencies và JDK runtime phải nằm trong chính sách hỗ trợ phù hợp; một smoke pass không thay thế việc này.

### Bước 10 — Phát hành theo ngưỡng

Canary/blue-green/rolling, giám sát lỗi/latency/cost và có rollback image/JDK cùng state compatibility.

### Bước 11 — Nâng build riêng

Sau khi runtime được xác nhận, nâng Maven/Gradle plugins, annotation processors, toolchains và source targets theo lộ trình có test.

## 32. Những sai lầm thường gặp

| Sai lầm | Hậu quả |
|---|---|
| Recompile trước rồi mới thử runtime | Mất phép thử cô lập tác động JDK |
| Chỉ giữ checksum main JAR, không giữ `lib/` | Dependency graph bị thay mà không biết |
| Tự đổi container image family | CA/libc/OS khác làm sai so sánh |
| Xem class-file cũ là bảo đảm runtime compatibility | JDK APIs/runtime providers có thể đã biến mất |
| Xem `ClassNotFoundException` là lỗi source | Có thể chỉ thiếu runtime dependency |
| Thêm `--add-opens` khắp nơi | Che framework không tương thích và tăng rủi ro |
| Dùng `--add-modules` để gọi module đã bị xóa | Không khôi phục được module |
| Bật trust-all TLS | Tạo lỗ hổng bảo mật và che nguyên nhân |
| Chỉ chạy health check | Không xác minh đường nghiệp vụ hiếm |
| So throughput sau warm-up | Bỏ qua cold startup/autoscaling |
| Đổi JDK, server và framework cùng lúc | Không còn cô lập được biến số |
| Coi JDK 21 runtime là lý do bytecode phải target 21 | Có thể phá khả năng rollback Java 17 |
| Không test persisted state | Rollback có thể đọc dữ liệu sai |
| Nhầm `--release` với kiểm tra third-party dependencies | Binary JAR có thể vẫn yêu cầu runtime cao hơn |
| Xem vendor support là không cần thiết khi test pass | Rủi ro bảo trì/compliance vẫn tồn tại |
| Giữ workaround vĩnh viễn không có owner | Phát sinh compatibility debt |
| Không lưu checksums, logs, versions | Kết quả không thể tái lập |

## 33. Checklist bàn giao

- [ ] Đã xác định artifact release chính xác và nguồn lấy.
- [ ] Đã lưu SHA-256/image digest của artifact và dependencies.
- [ ] Không chạy build/recompile trong runtime-only probe.
- [ ] Đã xác minh JDK process thật ở baseline và target.
- [ ] Đã ghi JVM flags, env vars và khác biệt container/OS.
- [ ] Đã kiểm tra class-file major version của code và dependencies liên quan.
- [ ] Đã kiểm tra multi-release JAR nếu có.
- [ ] Đã xem static JDK internal dependencies và giới hạn của `jdeps`.
- [ ] Đã thử startup và xử lý JVM launch flags cũ.
- [ ] Đã chạy business smoke và integration/contract tests.
- [ ] Đã kiểm tra API/provider từng bundled với JDK cũ khi có.
- [ ] Đã kiểm tra JPMS/reflection và framework compatibility.
- [ ] Đã kiểm tra TLS/truststore, DNS, charset và timezone.
- [ ] Đã kiểm tra JNI/native libraries và Java agents khi có.
- [ ] Đã đo startup/warm-up, p95/p99, throughput, CPU, GC và memory.
- [ ] Đã chạy soak, restart, failure recovery theo nhu cầu.
- [ ] Đã kiểm tra persisted state và khả năng rollback hai chiều.
- [ ] Đã phân loại từng lỗi theo tầng trước khi sửa.
- [ ] Đã tách runtime-only, runtime adaptation và recompile probes.
- [ ] Đã ghi thay đổi dependency/packaging nếu có, không gọi đó là nguyên artifact.
- [ ] Đã đánh giá vendor/framework support và security policy.
- [ ] Có bằng chứng và owner cho flags/workarounds tạm.
- [ ] Có canary thresholds, rollback runtime/image và operational runbook.
- [ ] Chỉ quyết định recompile/source migration khi có lý do rõ ràng.
- [ ] Đã bàn giao kết quả với checksum, versions, test scope và rủi ro còn mở.

**Kết luận:** Chạy artifact hiện tại trên JDK đích trước khi quyết định biên dịch lại là một cách **giảm biến số và lấy bằng chứng sớm**. Nếu nguyên binary đáp ứng chức năng, vận hành và support policy, tổ chức có thể nâng runtime trước, rồi hiện đại hóa build tool và source theo lộ trình riêng. Nếu thất bại, lỗi được phân loại chính xác thành cấu hình JVM, dependency/runtime provider, reflection, native integration, dữ liệu, security hoặc API thật sự cần thay. Cách tiếp cận **kiểm chứng trước, sửa đổi sau** giúp Java compatibility migration dễ truy nguyên, ít rủi ro và có phương án rollback rõ ràng.
