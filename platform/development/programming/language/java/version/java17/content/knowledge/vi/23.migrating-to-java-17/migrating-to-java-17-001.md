# Kiểm kê mã nguồn, dependency, plugin và môi trường chạy khi nâng cấp lên Java 17

Nâng cấp ứng dụng lên Java 17 không chỉ là đổi JDK rồi chạy lại lệnh build. Source code có thể gọi API đã bị loại khỏi JDK; dependency có thể chưa hỗ trợ Java 17; plugin build có thể yêu cầu JDK khác; runtime production có thể truyền JVM flag cũ hoặc dựa vào hành vi không còn được hỗ trợ.

Trước khi migration, hãy lập một bản kiểm kê có bằng chứng cho bốn nhóm:

1. **Mã nguồn:** API JDK, API deprecated/removed, JDK internal API, reflection, module và native code.
2. **Dependency:** thư viện trực tiếp/bắc cầu, framework, driver, agent và các thành phần chạy cùng ứng dụng.
3. **Plugin và công cụ build:** Gradle/Maven, compiler, test framework, annotation processor, code generator, static analysis, packaging và CI tools.
4. **Môi trường chạy:** JDK distribution, JVM options, container/OS/CPU/memory, TLS/certificate, locale/timezone, environment variables, filesystem và dịch vụ bên ngoài.

Mục tiêu là xác định ứng dụng đang phụ thuộc vào điều gì, phần nào có nguy cơ không tương thích, ai chịu trách nhiệm xử lý và bằng chứng nào chứng minh một mục đã được xác nhận. Đây là bước chuẩn bị trước migration; chưa nên nâng version hàng loạt khi chưa hiểu dependency và workload thực tế.

## 1. Xác định phạm vi và baseline

Bắt đầu bằng việc xác định ứng dụng, artifact và môi trường nằm trong phạm vi nâng cấp. Ghi nhận repository, source revision/commit, tên service/module, artifact đầu ra, JDK hiện tại, build tool, profile build và môi trường deploy.

Không giả định mọi module trong monorepo dùng cùng JDK hoặc build profile. Một module có thể đang dùng Java 8, module khác Java 11 và module khác đã dùng Java 17. Kiểm kê theo module/service thay vì chỉ nhìn root project.

### 1.1. Tách ba phiên bản Java

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| JDK chạy build | Gradle/Maven và plugin đang chạy trên JDK nào? |
| JDK compile/test toolchain | Compiler và test task sử dụng JDK nào? |
| Runtime JDK | Staging/production thực tế chạy bằng JDK nào? |
| Release target | Source, bytecode và API mục tiêu đang ở phiên bản nào? |

Ba lớp đầu không nhất thiết giống nhau. Gradle daemon có thể chạy trên một JDK, compiler task dùng toolchain khác, còn artifact được biên dịch với release target thấp hơn. Khi hướng tới Java 17, phải xác nhận cả khả năng chạy build tool, biên dịch và chạy artifact.

### 1.2. Thu thập baseline

Trước khi thay đổi, lưu lại:

- Build command, build result và thời gian build.
- Unit/integration test result.
- Startup time và shutdown behavior.
- CPU, memory, heap và GC behavior.
- Request latency p50/p95/p99, throughput và error rate.
- Log, exception và warning quan trọng.
- JVM flags, system properties và environment variables.
- Kết quả smoke test và performance test.

Baseline giúp phân biệt regression do thay đổi Java với vấn đề đã tồn tại. Nếu không có số liệu trước nâng cấp, đánh giá “Java 17 chạy tốt” dễ chỉ dựa vào cảm nhận hoặc việc ứng dụng khởi động thành công.

## 2. Kiểm kê mã nguồn Java

Mục tiêu là tìm các điểm mã nguồn có thể bị ảnh hưởng bởi thay đổi JDK, module system, API và hành vi runtime. Không chỉ tìm import: API có thể được gọi bằng tên đầy đủ, reflection, service loading, generated source hoặc thư viện nội bộ.

### 2.1. API deprecated, deprecated for removal và removed

Cần phân biệt:

- **Deprecated:** API vẫn tồn tại nhưng không được khuyến nghị cho code mới.
- **Deprecated for removal:** API có cảnh báo sẽ bị loại bỏ trong tương lai; nên ưu tiên đánh giá.
- **Removed:** API hoặc module không còn trong JDK; source/dependency gọi trực tiếp có thể không compile hoặc không chạy được.

JDK cung cấp `jdeprscan` để quét bytecode đã biên dịch:

```bash
jdeprscan --release 17 path/to/application.jar
jdeprscan --release 17 --for-removal path/to/application.jar
```

Lệnh thứ hai tập trung vào API deprecated for removal. Dùng cú pháp phù hợp theo `jdeprscan --help` của JDK đang sử dụng; lưu lại phiên bản công cụ và output để tái hiện.

`jdeprscan` phân tích class/JAR đã biên dịch. Nó không thay thế việc tìm source code, cấu hình, reflection string hoặc API được gọi gián tiếp qua framework. Dependency bắc cầu vẫn có thể gọi API deprecated dù source ứng dụng không import API đó.

### 2.2. JDK internal API

Các package nội bộ như `sun.*` hoặc implementation-specific API không phải hợp đồng công khai ổn định. Dùng `jdeps` để tìm tham chiếu tới JDK internals:

```bash
jdeps --multi-release 17 --jdk-internals path/to/application.jar
```

Với mỗi kết quả, ghi class gọi API, internal package/class được dùng, dependency sở hữu code đó và API công khai có thể thay thế.

Java 17 áp dụng strong encapsulation đối với JDK internals theo JEP 403. Không dùng `--illegal-access=permit` như giải pháp migration: tùy chọn này không còn mở rộng quyền truy cập như ở JDK cũ. Ưu tiên nâng cấp hoặc thay thế thành phần; chỉ cân nhắc `--add-exports` hoặc `--add-opens` có phạm vi hẹp khi có lý do kỹ thuật rõ ràng và kế hoạch loại bỏ.

### 2.3. Module/API từng đi kèm JDK cũ

Nếu ứng dụng được nâng từ Java 8 hoặc JDK cũ, kiểm tra các API từng được đóng gói cùng JDK nhưng đã tách hoặc loại bỏ. Ví dụ:

- Các module Java EE/CORBA như JAXB, JAX-WS, Activation và CORBA đã được tách khỏi JDK từ các bản Java trước Java 17.
- Nashorn JavaScript engine đã bị loại bỏ khỏi JDK từ Java 15.
- CMS garbage collector đã bị loại bỏ từ Java 14.
- Pack200 tools/API đã bị loại bỏ từ Java 14.
- RMI Activation đã bị loại bỏ từ Java 15.

Nếu ứng dụng còn dùng các thành phần này, xác định dependency thay thế hoặc loại bỏ chức năng tương ứng trước khi chạy trên Java 17.

Không suy luận rằng mọi package bắt đầu bằng `javax.` đều đã bị loại. Java SE vẫn có nhiều package javax được hỗ trợ, ví dụ `javax.crypto`, `javax.naming` và `javax.sql`. Chỉ xử lý package thực sự không còn được JDK cung cấp hoặc thuộc API framework đã thay đổi.

Không thay hàng loạt `javax` thành `jakarta` bằng search/replace. Việc chuyển Java EE sang Jakarta EE là thay đổi framework/platform riêng, phụ thuộc phiên bản API và application server; nó không phải quy tắc chung của Java 17.

### 2.4. Reflection và truy cập sâu

Tìm các đoạn code sử dụng:

- `Class.forName()` với tên lớp lấy từ cấu hình.
- `getDeclaredField()`, `getDeclaredMethod()` và `setAccessible(true)`.
- Reflection vào package JDK hoặc package thuộc module khác.
- Framework tự tạo proxy hoặc truy cập field private.
- Cấu hình `--add-opens` và `--add-exports`.

Strong encapsulation có thể làm những truy cập sâu từng hoạt động trên JDK cũ bị chặn. Ghi rõ module nguồn, package, module đích và mục đích truy cập.

| Thành phần | Package/class | Cách truy cập | Mục đích | Hướng xử lý |
| --- | --- | --- | --- | --- |
| Framework JSON | Package model | Reflection vào field | Serialize/deserialize | Kiểm tra phiên bản framework và yêu cầu opens. |
| Thư viện cũ | JDK internal package | Reflection | Đọc trạng thái nội bộ | Nâng cấp/thay thế thư viện. |
| Plugin test | Package private của ứng dụng | Reflection | Test fixture | Kiểm tra module test và test runtime. |

Không mở toàn bộ module cho mọi thành phần chỉ để làm mất lỗi. Nếu cần opens, giới hạn đúng package và đúng module framework.

### 2.5. API và hành vi runtime cần xem xét

Ngoài API bị loại bỏ, kiểm tra các điểm có thể thay đổi hành vi:

- Charset mặc định và cách đọc/ghi file.
- Timezone, locale và format ngày giờ.
- TLS protocol, cipher suite, certificate và trust store.
- Serialization và module encapsulation.
- Garbage collector và JVM flags.
- Process, thread và container resource awareness.
- Security provider và thuật toán bị giới hạn.
- Class loading, service loading và resource lookup.

Nhiều vấn đề chỉ xuất hiện runtime: TLS tới server cũ, parse dữ liệu sai charset hoặc framework cố truy cập private member.

## 3. Phân tích dependency ở mức module bằng jdeps

`jdeps` phân tích phụ thuộc giữa class/package/module trong bytecode. Công cụ giúp trả lời ứng dụng tham chiếu package nào và module JDK nào.

```bash
# Tóm tắt dependency
jdeps --summary path/to/application.jar

# Phân tích đệ quy
jdeps --recursive --summary path/to/application.jar

# In các module cần thiết
jdeps --multi-release 17 --print-module-deps path/to/application.jar

# Tìm dependency bị thiếu
jdeps --missing-deps path/to/application.jar

# Tìm JDK internal API
jdeps --multi-release 17 --jdk-internals path/to/application.jar
```

Dùng `--multi-release 17` khi phân tích multi-release JAR theo runtime mục tiêu. Với ứng dụng gồm nhiều JAR, cung cấp classpath/module-path phù hợp; phân tích một JAR riêng có thể báo dependency thiếu chỉ vì chưa đưa thư viện liên quan vào lệnh.

### 3.1. Giới hạn của phân tích tĩnh

`jdeps` không thể tìm đầy đủ mọi dependency được tạo hoặc nạp động. Kiểm tra bổ sung:

- Reflection dựa trên tên class trong properties/YAML/XML.
- Service Provider Interface và `ServiceLoader`.
- Class được tải qua plugin directory hoặc custom class loader.
- Annotation processor tạo source/class lúc build.
- JNI/JNA và native library.
- Bytecode được generate lúc runtime.
- Framework scanning classpath.
- Dependency chỉ xuất hiện trong profile hoặc feature ít được bật.

`jdeps` là bằng chứng quan trọng, không phải danh sách dependency đầy đủ của ứng dụng.

## 4. Kiểm kê dependency trực tiếp và bắc cầu

Với mỗi dependency, ghi nhận tọa độ/version, scope, direct/transitive, Java tối thiểu được hỗ trợ, framework compatibility, maintenance status, security advisory, module name, native component và các yêu cầu reflection/class loading.

### 4.1. Gradle dependency graph

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Với multi-project build, kiểm tra từng subproject và configuration quan trọng. `runtimeClasspath` không bao gồm mọi dependency test, plugin hoặc annotation processor.

### 4.2. Maven dependency graph

```bash
./mvnw dependency:tree
./mvnw dependency:tree -Dscope=runtime
./mvnw help:effective-pom
```

`dependency:tree` cho biết dependency trực tiếp/bắc cầu; `effective-pom` cho thấy cấu hình sau khi áp dụng parent POM, properties và profiles. Chạy trong các profile CI/production vì graph có thể thay đổi theo profile.

### 4.3. Compile và runtime dependency

Một thư viện có thể compile thành công nhưng lỗi khi chạy vì dependency chỉ có trong compile scope, bị loại khỏi package hoặc khác version giữa môi trường.

Kiểm kê riêng:

- Compile classpath.
- Runtime classpath/module path.
- Test classpath.
- Annotation processor path.
- Plugin classpath.
- Application server-provided libraries.
- Dependency được đóng gói trong fat JAR hoặc image.

Không chỉ kiểm tra root `pom.xml` hoặc `build.gradle`; hãy xác định artifact cuối cùng thực sự mang theo những thư viện nào.

## 5. Đánh giá từng dependency có tương thích Java 17 không

Một dependency nên được xem là sẵn sàng khi có bằng chứng phù hợp:

- Nhà cung cấp công bố hỗ trợ Java 17 cho version đang dùng.
- Release notes nêu các thay đổi liên quan JDK 17.
- CI của thư viện chạy test trên Java 17.
- Artifact không phụ thuộc JDK internal API đã bị đóng.
- Integration test của ứng dụng chạy qua với version đó.
- Không có security issue chưa xử lý.

Không kết luận tương thích chỉ vì thư viện tải được hoặc compile được. Một thư viện cũ có thể lỗi khi reflection, TLS, class loading hoặc native code được thực thi.

| Nhóm | Tiêu chí | Hành động |
| --- | --- | --- |
| Compatible | Nhà cung cấp hỗ trợ Java 17 và test ứng dụng thành công. | Giữ version hoặc nâng cấp có chủ đích. |
| Compatible with constraints | Chạy được nhưng cần flag/cấu hình/version cụ thể. | Ghi constraint, owner và kế hoạch bỏ workaround. |
| Upgrade required | Version hiện tại không hỗ trợ Java 17 hoặc có lỗi đã xác nhận. | Chọn version thay thế và regression test. |
| Replace/remove | Không còn maintenance hoặc không có bản tương thích. | Thay thế hoặc loại bỏ. |
| Unknown | Chưa có tài liệu hoặc bằng chứng runtime. | Tạo test/POC; không tự đánh dấu compatible. |

Ngoài business library, kiểm tra logging, JSON/XML serializer, database driver, ORM, HTTP/messaging client, SDK cloud, web framework, dependency injection, proxy framework, cache, scheduler, security provider, monitoring agent, native access và testing framework.

Agent APM/profiler/bytecode instrumentation có thể không xuất hiện trong dependency compile nhưng vẫn chạy trong JVM. Chúng cần version tương thích Java 17.

## 6. Kiểm kê framework và application server

Framework thường dùng reflection, proxy, annotation scanning và bytecode generation. Ghi nhận framework/module/version, Java support matrix, servlet/Jakarta API, application server/container, integration module và yêu cầu module opens.

### 6.1. Servlet và Jakarta namespace

Nếu ứng dụng chạy trong servlet container/application server, ghi nhận phiên bản container và namespace API đang dùng.

`javax.servlet` và `jakarta.servlet` là hai namespace khác nhau. Chuyển từ Java EE sang Jakarta EE có thể yêu cầu thay đổi namespace và framework; đó là bước migration nền tảng riêng, không tự động phát sinh chỉ vì đổi JDK lên Java 17.

Phân biệt API do server cung cấp với dependency đóng gói trong ứng dụng. Ghi rõ scope `provided` hoặc tương đương và version server thực tế.

### 6.2. Reflection và proxy của framework

Kiểm tra cấu hình `--add-opens`, `--add-exports`, reflection vào JDK packages, proxy generation, bytecode enhancement, ORM instrumentation và serialization.

Ưu tiên nâng framework lên bản hỗ trợ Java 17. Nếu vẫn cần mở package, ghi package, module framework, lý do và thời hạn xem xét lại. Không dùng một danh sách mở rộng cho toàn bộ JDK như cấu hình lâu dài.

## 7. Kiểm kê plugin và công cụ build

Plugin build cũng là code chạy trên JDK và có thể dùng API đã thay đổi. Dependency runtime tương thích không bảo đảm plugin cũ chạy được trên JDK 17.

Lập danh sách:

- Gradle/Maven wrapper và version.
- Compiler plugin.
- Test runner/test framework.
- Annotation processor.
- Code generator.
- Static analysis/linter.
- Coverage tool.
- Packaging/shading/fat JAR plugin.
- Javadoc/source archive plugin.
- Container/image build plugin.
- Database migration plugin.
- Quality/security scan plugin.
- Plugin nội bộ và convention plugin.

Với từng plugin, ghi version, JDK tối thiểu để chạy, build tool version tương thích và bằng chứng trên Java 17.

### 7.1. Gradle

```bash
./gradlew --version
./gradlew tasks
./gradlew buildEnvironment
```

`buildEnvironment` giúp xem buildscript classpath; nó không thay thế kiểm tra plugin DSL và plugin resolution ở mọi subproject. Xem `settings.gradle`, `settings.gradle.kts`, version catalog và convention plugin.

Gradle daemon JVM và Java toolchain là hai cấu hình khác nhau. Gradle 7.3 trở lên hỗ trợ chạy Gradle trên Java 17. Nếu wrapper cũ hơn, kiểm tra compatibility matrix của đúng phiên bản Gradle và nâng wrapper trước khi chuyển daemon sang JDK 17.

Trong build script, kiểm tra plugin DSL, buildscript dependencies, custom task dùng internal Gradle API, toolchain/compiler options, test JVM args, annotation processor và task gọi JDK executable riêng.

Không nâng Gradle wrapper, plugin và dependency cùng lúc nếu chưa có baseline. Thay đổi theo từng nhóm giúp xác định nguyên nhân khi build lỗi.

### 7.2. Maven

```bash
./mvnw --version
./mvnw help:effective-pom
./mvnw dependency:resolve-plugins
```

Xem plugin trong parent POM, pluginManagement, profile và build extensions. Pin version plugin rõ ràng; không phụ thuộc version mặc định có thể thay đổi theo Maven super POM hoặc môi trường.

Phân biệt Maven runtime JDK với JDK mà compiler/test plugin sử dụng. Nếu dùng Maven Toolchains, kiểm tra `toolchains.xml` và JDK thực sự được chọn.

### 7.3. Annotation processor và code generator

Các công cụ như Lombok, MapStruct, Dagger, QueryDSL hoặc generator nội bộ có thể chạy trong compile phase và phụ thuộc compiler/JDK.

Ghi processor version, JDK support, compiler plugin, processor path, generated source location và kết quả clean build trên Java 17. Nếu CI tạo code mới, xác minh generation có thể tái hiện và không phụ thuộc JDK cũ.

## 8. Kiểm kê test, quality và coverage tooling

Test framework có thể dùng reflection sâu hoặc instrument bytecode. Kiểm tra JUnit/TestNG, Mockito/Byte Buddy/CGLIB, coverage, test container, embedded server, integration test, static analysis và test JVM arguments.

Đặc biệt kiểm tra test dựa vào private reflection, mock final class, dynamic agent attachment hoặc bytecode instrumentation. Nếu test chạy trên JDK 17 nhưng coverage/mocking plugin chưa hỗ trợ, build có thể chỉ thất bại ở bước test.

Ghi riêng test nào chạy trong CI và test nào chỉ chạy thủ công. Một suite không được thực thi thường xuyên không phải bằng chứng tương thích đáng tin cậy.

## 9. Kiểm kê Java agent, native library và công cụ ngoài JVM

### 9.1. Java agents

Tìm các tham số `-javaagent:`, `-agentlib:` và `-agentpath:`. Agent có thể là APM, tracing, profiler, security monitor, coverage hoặc bytecode transformer.

Ghi version, vendor, cách nạp, JVM support matrix và cấu hình. Agent không tương thích có thể làm JVM không khởi động, biến đổi bytecode lỗi hoặc gây ảnh hưởng hiệu năng.

### 9.2. JNI/JNA và native libraries

Kiểm kê `System.loadLibrary()`, `System.load()`, JNI/JNA dependency, native library trong JAR, binary theo OS/architecture, libc/OpenSSL và đường dẫn `java.library.path`.

Java 17 không làm native binary cũ tự tương thích. Kiểm tra OS, CPU architecture, ABI và version native library. Với container, kiểm tra cả base image và thư viện hệ thống bên trong image.

### 9.3. Công cụ ngoài JVM

Ứng dụng/build có thể gọi `keytool`, `jarsigner`, `jlink`, `jdeps`, shell script, Node/Python, cloud/database CLI hoặc Docker/BuildKit. Ghi version và nguồn cài đặt. Không giả định chúng tự đổi theo `JAVA_HOME`.

## 10. Kiểm kê JVM options và runtime flags

Runtime production có thể dùng flags được tích lũy qua nhiều năm. Một số flag đã bị loại bỏ, đổi ý nghĩa hoặc không còn phù hợp với Java 17.

Thu thập cấu hình từ startup script, service definition, Dockerfile, Kubernetes manifests/Helm values, CI/CD, application server và environment variables như `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, `_JAVA_OPTIONS`.

| Nhóm | Ví dụ cần ghi nhận |
| --- | --- |
| Heap | `-Xms`, `-Xmx`, `-XX:MaxRAMPercentage` |
| GC | Collector flags, pause/throughput goals, GC logging |
| Module/reflection | `--add-opens`, `--add-exports` |
| Security/TLS | Trust store, keystore, provider, disabled algorithms |
| System properties | `-D...`, locale, timezone, proxy |
| Agents | `-javaagent`, `-agentlib`, `-agentpath` |
| Diagnostics | JFR, heap dump, error file, GC log |

### 10.1. Flags đã bị loại bỏ hoặc không còn tác dụng

Không sao chép nguyên bộ JVM options từ JDK cũ sang Java 17 mà không kiểm tra.

CMS GC đã bị loại bỏ khỏi HotSpot trước Java 17. Nếu startup script còn `-XX:+UseConcMarkSweepGC` hoặc CMS tuning flags, cần loại bỏ và chọn collector hiện hành sau khi đo workload.

`--illegal-access` không còn là cách mở quyền truy cập nội bộ trong Java 17. Để xử lý lỗi reflection, nâng dependency hoặc xác định đúng package/module cần mở.

Kiểm tra option trên JVM hiện tại:

```bash
java -XX:+PrintFlagsFinal -version
java -Xlog:help
java --help
```

Có thể kiểm tra startup command của ứng dụng trong staging và xem warning/error khi JVM nhận flags. Không chỉ dựa vào việc một flag có xuất hiện trong file cấu hình.

### 10.2. GC và memory settings

Ghi collector đang dùng, `-Xms`/`-Xmx`, pause/throughput goal, GC logging, heap dump, container memory limit, direct memory, native memory và số thread.

Không đổi GC chỉ vì nâng JDK. Xác nhận workload và baseline trước; sau nâng cấp so sánh GC pause, allocation rate, throughput và latency.

## 11. Kiểm kê môi trường chạy

Một ứng dụng có thể build thành công trên JDK 17 nhưng lỗi khi deploy vì runtime environment khác máy developer. Lập bảng riêng cho local, test, CI, QA/staging, performance test, production và disaster recovery.

Với từng môi trường, ghi OS, architecture, JDK distribution/build, CPU, memory, container image, JVM args, certificates, environment variables và service endpoints.

### 11.1. OS và kiến trúc CPU

Kiểm tra Windows/Linux/macOS và version, x86_64/AArch64, kernel/libc khi có native library, file permissions, path separator, filesystem case sensitivity, process signal và service manager.

Không dùng kết quả Windows để kết luận Linux production sẽ giống hệt nếu ứng dụng dùng native library, path, shell command hoặc filesystem behavior phụ thuộc nền tảng.

### 11.2. Container và resource limits

Ghi base image/digest, JDK/JRE distribution, CPU quota/request, memory limit, entrypoint, user, mounted volume, secret, health check và shutdown grace period.

Trên Linux container được hỗ trợ, JVM có thể nhận biết container resource limits và dùng thông tin đó cho ergonomics. Tuy vậy, phải xác nhận JVM thực tế nhìn thấy bao nhiêu CPU và memory; đừng suy luận từ cấu hình host.

```bash
java -version
java -XshowSettings:system -version
java -XX:+PrintCommandLineFlags -version
```

Các lệnh giúp kiểm tra thông tin runtime và flags được chọn. Kết quả phụ thuộc nền tảng và quyền truy cập container metadata.

### 11.3. Environment variables và system properties

Ghi các biến ảnh hưởng runtime như `JAVA_HOME`, `PATH`, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, proxy, truststore, locale/timezone, application profile, database/message broker endpoint và feature flags.

Không ghi secret vào inventory hoặc log. Chỉ ghi tên biến, nguồn cấp, môi trường áp dụng và owner; giá trị bí mật nằm trong secret manager hoặc cơ chế bảo mật phù hợp.

## 12. Kiểm tra TLS, certificate và kết nối ngoài

Thay đổi JDK có thể đi kèm thay đổi TLS implementation, security provider, trust store và danh sách thuật toán được phép. Endpoint cũ có thể chỉ hỗ trợ protocol/cipher không còn được client chấp nhận.

Kiểm kê:

- Endpoint HTTPS, database TLS, LDAP, message broker và API bên ngoài.
- TLS version và cipher suite.
- Certificate chain và CA trust.
- Keystore/truststore type, format và vị trí.
- Certificate expiration/rotation.
- Custom security provider.
- Mutual TLS, proxy và network inspection.
- Security properties và thuật toán bị giới hạn.

Không hạ security policy hoặc bật lại thuật toán yếu chỉ để làm kết nối cũ hoạt động. Xác định endpoint, server version và certificate chain; phối hợp nâng cấp server hoặc cấu hình trust/security phù hợp.

Với lỗi TLS, ghi exception đầy đủ, peer/endpoint, thời điểm, protocol và certificate chain (không chia sẻ private key). Chạy integration test từ đúng runtime image Java 17.

## 13. Kiểm tra charset, locale và timezone

Ứng dụng có thể phụ thuộc default charset, locale hoặc timezone của máy. Kiểm tra:

- `new String(byte[])` hoặc `String.getBytes()` không truyền charset.
- `FileReader`/`FileWriter` dùng default charset.
- Format số/ngày giờ không truyền `Locale`.
- Dùng `ZoneId.systemDefault()` hoặc `TimeZone.getDefault()`.
- Parse ngày giờ không có zone/offset.
- Resource được sinh trên Windows và chạy trên Linux.

Có thể in thông tin runtime:

```java
System.out.println("Java version: " + Runtime.version());
System.out.println("Default charset: " + java.nio.charset.Charset.defaultCharset());
System.out.println("Default locale: " + java.util.Locale.getDefault());
System.out.println("Default zone: " + java.time.ZoneId.systemDefault());
```

Với dữ liệu trao đổi/file cần ổn định, truyền rõ charset như UTF-8. Với thời gian tuyệt đối, ưu tiên `Instant`; với lịch địa phương, quản lý `ZoneId` rõ ràng. Không giả định timezone container giống timezone máy developer.

## 14. Kiểm kê database, messaging và dịch vụ tích hợp

Các kết nối ngoài JVM là một phần của runtime. Java 17 có thể làm lộ vấn đề ở driver, TLS, authentication hoặc framework tích hợp.

| Hệ thống | Thông tin cần kiểm kê |
| --- | --- |
| Database | Driver/version, database version, TLS, authentication, pool, dialect, JDBC URL properties |
| Message broker | Client version, protocol, TLS, authentication, serializer và retry policy |
| Cache | Client version, topology, TLS, timeout và serialization format |
| HTTP API | Client library/version, TLS, proxy, timeout, redirect và certificate |
| LDAP/SSO | Provider, TLS, truststore và authentication flow |
| File/object storage | SDK version, endpoint, native dependency và credential provider |

Một driver có thể hỗ trợ Java 17 nhưng không hỗ trợ database server hoặc TLS policy hiện tại. Kiểm tra cả hai phía và chạy integration test từ môi trường staging tương đương production.

## 15. Kiểm kê deployment, startup và shutdown

Theo dõi toàn bộ đường đi từ build đến process thực tế:

- CI artifact được tạo ở đâu.
- Artifact được đóng gói vào image như thế nào.
- Image tag/digest được deploy ra sao.
- JVM command line do entrypoint/orchestrator tạo.
- Secret/certificate được mount lúc nào.
- Health check kiểm tra điều kiện nào.
- Process nhận SIGTERM và shutdown ra sao.
- Grace period có đủ để hoàn tất request và flush dữ liệu không.
- Rollback dùng image/JDK/artifact nào.

Kiểm tra startup script có gọi JDK bằng absolute path hoặc dựa vào thư mục cài đặt cụ thể không. Nếu đổi base image, xác nhận timezone data, CA certificates, native libraries và công cụ chẩn đoán cần thiết vẫn có mặt.

## 16. Lập ma trận kiểm kê và đánh giá rủi ro

Mỗi mục cần có bằng chứng, owner và trạng thái; không chỉ giữ một danh sách tên package/dependency.

| Nhóm | Thành phần | Version/hiện trạng | Bằng chứng | Rủi ro | Owner | Trạng thái |
| --- | --- | --- | --- | --- | --- | --- |
| Source | Internal JDK API | Package/class cụ thể | jdeps output | Cao | Team A | Cần xử lý |
| Dependency | ORM | Version hiện tại | Release notes + integration test | Trung bình/Cao | Team B | Chưa xác nhận |
| Plugin | Compiler plugin | Version hiện tại | Build trên JDK 17 | Trung bình | Build team | Đã xác nhận |
| Runtime | Java agent | Version deploy | Vendor support matrix | Cao | Platform | Cần nâng cấp |
| Environment | TLS endpoint | Protocol/certificate | Integration test | Trung bình | Infra | Đang kiểm tra |

### 16.1. Phân loại rủi ro

- **High:** có thể làm build thất bại, JVM không khởi động, security suy yếu hoặc chức năng quan trọng bị lỗi.
- **Medium:** có thể gây lỗi ở một profile, endpoint, loại dữ liệu hoặc làm suy giảm hiệu năng.
- **Low:** không ảnh hưởng trực tiếp hiện tại nhưng cần cập nhật hoặc có nguy cơ khi đổi môi trường.

Đánh giá dựa trên bằng chứng. Một dependency chưa có thông tin Java 17 là `Unknown`, không tự động là `Compatible` chỉ vì chưa thấy lỗi.

### 16.2. Trạng thái kiểm kê

| Trạng thái | Ý nghĩa |
| --- | --- |
| Not inventoried | Chưa thu thập thông tin. |
| Inventoried | Đã ghi nhận version/cấu hình và nguồn bằng chứng. |
| Needs assessment | Có thông tin nhưng chưa đủ kết luận tương thích. |
| Upgrade required | Đã xác nhận cần nâng version hoặc thay thế. |
| Verified on Java 17 | Đã chạy test phù hợp trên JDK 17 và lưu bằng chứng. |
| Accepted constraint | Có giới hạn đã hiểu, owner và biện pháp kiểm soát được phê duyệt. |
| Removed | Thành phần không còn được dùng và đã gỡ khỏi build/deployment. |

Không đánh dấu `Verified on Java 17` chỉ vì compiler không báo lỗi. Xác định mức test: compile, unit, integration, startup, smoke, performance hoặc production canary.

## 17. Quy trình kiểm kê theo từng vòng

### Vòng 1 — inventory tĩnh

1. Xác định repository, module và source revision.
2. Thu thập JDK, Gradle/Maven wrapper và build profiles.
3. Xuất dependency graph.
4. Liệt kê plugin, annotation processor, agent và native library.
5. Chạy `jdeps` và `jdeprscan` trên artifact hiện tại.
6. Tìm JVM flags, environment variables và module options trong deployment config.

Kết quả là danh sách thành phần và nghi vấn cần xác minh, chưa phải kết luận tương thích.

### Vòng 2 — đối chiếu tài liệu hỗ trợ

Với từng dependency/plugin:

1. Xác định version chính xác.
2. Tìm Java 17 support matrix/release notes của nhà cung cấp.
3. Kiểm tra issue tracker hoặc advisory liên quan.
4. Xác định version thay thế nếu bản hiện tại không hỗ trợ.
5. Ghi constraint và người chịu trách nhiệm.

Không dùng tài liệu của phiên bản mới nhất để suy ra phiên bản cũ cũng tương thích. Bằng chứng phải khớp artifact/version cụ thể.

### Vòng 3 — xác minh trên JDK 17

1. Cài đúng JDK 17 distribution/build đã chọn.
2. Chạy build bằng wrapper.
3. Chạy unit test và integration test.
4. Khởi động ứng dụng bằng runtime image dự kiến.
5. Kiểm tra database, messaging, HTTP/TLS và file storage.
6. Kiểm tra startup/shutdown, logging, metrics và agent.
7. Chạy smoke/performance test so với baseline.

Ghi lại workaround như `--add-opens`, thay truststore hoặc JVM flags. Không để workaround chỉ tồn tại trong lệnh chạy của một developer.

### Vòng 4 — chốt kế hoạch migration

Nhóm mục có thể giữ, cần nâng version, cần thay thế/loại bỏ, cần sửa source, cần thay đổi deployment và còn unknown. Mỗi mục có owner, deadline, acceptance criteria và phương án rollback phù hợp.

## 18. Các lệnh kiểm kê tham khảo

### JDK và runtime

```bash
java -version
javac -version
jcmd -l
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> VM.command_line
```

`jcmd` cần quyền attach phù hợp; một số môi trường production có thể tắt attach hoặc chạy trong container riêng.

### API và dependency tĩnh

```bash
jdeprscan --release 17 application.jar
jdeprscan --release 17 --for-removal application.jar
jdeps --multi-release 17 --summary application.jar
jdeps --multi-release 17 --recursive --print-module-deps application.jar
jdeps --multi-release 17 --jdk-internals application.jar
jdeps --missing-deps application.jar
```

### Gradle

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew buildEnvironment
./gradlew dependencyInsight --dependency <name> --configuration runtimeClasspath
```

### Maven

```bash
./mvnw --version
./mvnw dependency:tree
./mvnw dependency:tree -Dscope=runtime
./mvnw help:effective-pom
./mvnw dependency:resolve-plugins
```

### Artifact và module

```bash
jar --describe-module --file application.jar
jar tf application.jar
javap -verbose -classpath application.jar com.example.Main
```

`jar --describe-module` giúp xem module descriptor hoặc automatic module information; `javap -verbose` cho biết bytecode metadata như major version. Với Java 17, class file version là 61. Fat JAR có thể chứa nhiều thư viện; kiểm tra từng dependency khi cần.

Không phải lệnh nào cũng áp dụng cho mọi project. Ghi command, JDK/tool version, input artifact và output để kết quả có thể tái hiện.

## 19. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách tránh |
| --- | --- | --- |
| Chỉ đổi `JAVA_HOME` rồi build | Bỏ sót plugin, dependency và runtime flags. | Kiểm kê source, dependency, build và runtime. |
| Chỉ xem dependency trực tiếp | Bỏ sót transitive dependency và plugin classpath. | Xuất graph cho compile/runtime/test/plugin. |
| Chỉ chạy `jdeps` | Bỏ sót reflection, SPI, JNI và code generation. | Kết hợp static scan, config search và runtime test. |
| Coi mọi `javax.*` là lỗi thời | Có thể thay nhầm Java SE API vẫn được hỗ trợ. | Kiểm tra package cụ thể và nguồn cung cấp API. |
| Thay toàn bộ `javax` thành `jakarta` | Làm hỏng code dùng Java SE hoặc framework chưa chuyển namespace. | Xác định đúng framework/API và migration riêng. |
| Giữ nguyên mọi JVM flag cũ | JVM có thể từ chối option hoặc dùng cấu hình không còn ý nghĩa. | Thu thập command line và kiểm tra từng flag trên JDK 17. |
| Dùng `--illegal-access` để sửa reflection | Không khôi phục hành vi mở package trên Java 17. | Nâng dependency hoặc giới hạn opens theo module/package. |
| Chỉ kiểm tra compile | Bỏ sót lỗi runtime, TLS, serialization và native library. | Chạy integration, startup và smoke test trên runtime 17. |
| Không kiểm tra Java agent | Agent có thể chặn startup hoặc biến đổi bytecode lỗi. | Kiểm kê `-javaagent` và native agent. |
| Chỉ kiểm tra máy developer | CI/production có thể dùng JDK, OS và flags khác. | Kiểm tra đúng CI và runtime image. |
| Không lưu bằng chứng | Không biết ai xác nhận và bằng cách nào. | Ghi version, command, output, owner và trạng thái. |

## 20. Tiêu chí hoàn tất kiểm kê

Có thể xem inventory đủ để lập kế hoạch migration khi:

- Tất cả module/service trong phạm vi có source revision và owner.
- JDK hiện tại, target JDK và release target được ghi rõ.
- Build tool, wrapper, plugin và compiler/test toolchain được liệt kê.
- Dependency trực tiếp/bắc cầu và runtime graph đã được xuất.
- Dependency/framework có hỗ trợ Java 17 hoặc trạng thái Unknown được ghi rõ.
- JDK internal API, deprecated/removed API và reflection risk đã được rà soát.
- Java agent, native library và công cụ ngoài JVM đã được liệt kê.
- Runtime flags và environment variables đã thu thập từ deployment thực tế.
- OS, architecture, container image, CPU/memory limits và TLS endpoints được ghi nhận.
- Test baseline và chỉ số hiệu năng trước nâng cấp đã lưu.
- Mỗi rủi ro có owner, hướng xử lý và acceptance criteria.
- Không còn mục Unknown ảnh hưởng cao mà không có kế hoạch xác minh.

Sau inventory, nhóm mới lập thứ tự nâng cấp: build tool, plugin/dependency, source code, runtime và kiểm thử. Không biến danh sách kiểm kê thành một lần nâng version hàng loạt thiếu kiểm soát.

## 21. Bài thực hành

### Bài 1 — tạo inventory cho một ứng dụng

Chọn một service. Ghi source revision, JDK hiện tại, build tool, module, artifact, runtime command và deployment environment. Xác định thông tin nào chưa có bằng chứng.

### Bài 2 — phân tích API

Build ứng dụng bằng JDK hiện tại, sau đó chạy `jdeprscan --release 17` và `jdeps --jdk-internals` trên artifact. Phân loại kết quả thành deprecated, removed/unsupported và internal API. Ghi rõ giới hạn của từng công cụ.

### Bài 3 — xuất dependency graph

Với Gradle, chạy `dependencies` cho runtime/test configuration; với Maven, chạy `dependency:tree`. Tìm một dependency bắc cầu và xác định thư viện nào đưa nó vào.

### Bài 4 — kiểm tra plugin

Liệt kê compiler, test, coverage, annotation processor và packaging plugin. Tra tài liệu hỗ trợ Java 17 theo đúng version đang dùng. Ghi plugin cần nâng cấp trước khi chuyển build JVM.

### Bài 5 — kiểm kê runtime flags

Thu thập command line từ startup script, container manifest và `jcmd VM.command_line`. Tìm flag cũ, module access option, GC option và Java agent. Xác minh từng flag trên JDK 17 trong staging.

### Bài 6 — kiểm tra môi trường tích hợp

Chọn database, HTTP endpoint và message broker quan trọng. Ghi driver/client version, TLS protocol, certificate source và timeout. Chạy integration test từ runtime image Java 17 dự kiến.

### Bài 7 — hoàn thiện risk register

Với mỗi vấn đề, ghi impact, likelihood, evidence, owner, proposed action và acceptance criteria. Không đánh dấu tương thích khi mới có giả định hoặc chưa chạy test.

## 22. Ghi nhớ nhanh

| Nhóm | Cần kiểm kê | Công cụ/bằng chứng |
| --- | --- | --- |
| Source/API | Deprecated, removed, JDK internals, reflection, module | `jdeprscan`, `jdeps`, source/config search |
| Dependency | Direct/transitive, framework, driver, agent | Gradle dependencies/dependencyInsight, Maven dependency:tree, vendor support matrix |
| Plugin/build | Wrapper, compiler, test, processor, generator, packaging | Gradle/Maven wrapper, effective POM, buildEnvironment, plugin release notes |
| Native/agent | JNI/JNA, `-javaagent`, native libraries | Startup config, image inspection, vendor compatibility |
| Runtime | JDK distribution, flags, heap/GC, properties | `java -version`, `jcmd`, runtime command line |
| Environment | OS, architecture, container, CPU/memory | Image digest, deployment manifests, container runtime data |
| Integration | TLS, certificates, DB, messaging, HTTP | Integration tests, connection config, server/client support matrix |
| Evidence | Baseline, test results, risk, owner | Inventory register, CI logs, metrics và acceptance criteria |

**Nguyên tắc cốt lõi:** Trước khi nâng cấp lên Java 17, hãy biết chính xác source code, dependency graph, plugin/build tool và runtime environment đang sử dụng. Dùng `jdeps` và `jdeprscan` để tìm dấu hiệu ở bytecode, nhưng vẫn kiểm tra reflection, SPI, agent, native library và deployment config. Mỗi mục cần version cụ thể, bằng chứng tương thích, owner và trạng thái rõ ràng. Khi inventory đã đủ và baseline được lưu, nhóm mới có thể migration theo từng bước và xác nhận kết quả bằng test cùng số liệu runtime.
