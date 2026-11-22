# Lập danh mục ứng dụng, dependency, plugin và agent cần nâng cấp

## 1. Vì sao phải lập danh mục trước khi nâng cấp?

Nâng cấp lên Java 21 không chỉ là đổi phiên bản JDK trong một lệnh build. Một hệ thống thường gồm nhiều ứng dụng, job nền, công cụ build, thư viện bắc cầu, plugin, Java agent, native library và môi trường triển khai. Chỉ một thành phần không tương thích cũng có thể làm build thất bại, khiến ứng dụng không khởi động hoặc gây lỗi chỉ xuất hiện khi một tính năng hiếm được sử dụng.

Danh mục migration (migration inventory) giúp trả lời:

- Có những JVM application nào cần chuyển sang Java 21?
- Ứng dụng đang build, test và chạy bằng JDK nào?
- Dependency trực tiếp và bắc cầu nào cần xác minh hoặc nâng phiên bản?
- Maven/Gradle plugin, compiler, test runner và annotation processor có hỗ trợ JDK mục tiêu không?
- Agent, profiler, APM, coverage tool hoặc native library nào được nạp vào JVM?
- Thành phần nào đã được kiểm thử, thành phần nào còn thiếu bằng chứng và ai chịu trách nhiệm?

Lập danh mục trước khi sửa code để xác định phạm vi và thứ tự nâng cấp. Không nên nâng tất cả dependency cùng lúc nếu chưa biết thành phần nào thực sự gây lỗi; hãy dùng inventory để cô lập thay đổi và theo dõi bằng chứng tương thích.

## 2. Xác định phạm vi ứng dụng và tiến trình JVM

Đầu tiên, liệt kê mọi thứ thực sự chạy trên JVM trong môi trường phát triển, kiểm thử, staging và production. Không chỉ tìm các service chính.

| Nhóm | Ví dụ cần đưa vào danh mục |
|---|---|
| Ứng dụng chạy lâu dài | REST API, worker, scheduler, consumer, batch service |
| Ứng dụng chạy theo lệnh | CLI, migration utility, data import/export, admin tool |
| Tác vụ theo lịch | Cron job, ETL, report generator, housekeeping job |
| Kiểm thử | Unit test, integration test, contract test, performance test |
| Build và release | Maven/Gradle process, code generator, packaging/signing task |
| Công cụ vận hành | Migration tool, database tool, diagnostic utility, deployment helper |
| Thành phần nhúng JVM | Plugin chạy trong host application, embedded server hoặc scripting runtime |

Với mỗi ứng dụng, xác định nơi JVM được khởi chạy: systemd/service manager, container entrypoint, Kubernetes workload, application server, CI runner, IDE hoặc script vận hành. Một ứng dụng có thể có nhiều process với JDK và JVM arguments khác nhau, ví dụ process chạy service và process chạy migration job.

Không gộp nhiều tiến trình vào một dòng inventory nếu chúng có cấu hình, chủ sở hữu hoặc vòng đời phát hành khác nhau. Một batch job chạy JDK riêng có thể cần kế hoạch nâng cấp khác với API service cùng repository.

## 3. Phân biệt JDK dùng để build, toolchain và runtime

Một nguyên nhân thường gặp khiến migration bị bỏ sót là nhầm lẫn JDK chạy build với JDK dùng để biên dịch và JDK chạy ứng dụng.

| Thành phần | Câu hỏi cần ghi nhận |
|---|---|
| Build JVM | Maven/Gradle daemon hoặc build process đang chạy bằng JDK nào? |
| Compiler toolchain | `javac` nào biên dịch source? Có toolchain được cấu hình rõ không? |
| Source/API target | Source language level và Java API target là bao nhiêu? |
| Test JVM | Unit/integration test chạy bằng JDK nào? Có forked test process không? |
| Runtime JVM | Container, VM hoặc server production sử dụng JDK vendor/build nào? |
| Diagnostic JVM | JFR, profiler, attach tool và script vận hành dùng JDK nào? |

Ví dụ, Gradle daemon có thể chạy bằng một JDK, trong khi Java toolchain được cấu hình để biên dịch và chạy test bằng JDK 21. Ngược lại, build thành công trên máy developer không chứng minh container production đang dùng đúng runtime.

Khi chuyển target lên Java 21, cần hiểu vai trò của `--release`:

```bash
javac --release 21 -d out src/main/java/example/App.java
```

`--release 21` chọn source rules, class-file target và tập Java SE API được phép dùng cho release 21. Nó hữu ích hơn việc chỉ đặt `-source` và `-target` riêng lẻ khi cần bảo đảm code không vô tình tham chiếu API của JDK mới hơn. Nó không chọn JDK runtime để triển khai ứng dụng.

Trong Maven, kiểm tra `maven-compiler-plugin` và cấu hình `release`; trong Gradle, kiểm tra Java toolchain và `options.release`. Đồng thời xác nhận test task cũng chạy trên đúng JDK mục tiêu. Không chỉ đổi `JAVA_HOME` rồi giả định mọi task đã dùng Java 21.

## 4. Lập danh mục dependency trực tiếp và bắc cầu

Dependency inventory phải bao gồm các dependency theo từng scope/configuration, không chỉ các thư viện được import trong source.

Các nhóm nên kiểm tra:

- Runtime dependency: framework, HTTP client, JDBC driver, ORM, serialization, logging và messaging client.
- Compile-time dependency: API, annotation, code-generation API và thư viện được dùng khi biên dịch.
- Test dependency: JUnit, Mockito, MockK, test container, mock server, coverage và assertion library.
- Annotation processor/compiler plugin: Lombok, MapStruct, Error Prone, Checker Framework hoặc processor riêng.
- Build-time dependency: code generator, shading, packaging, signing, bytecode enhancement và documentation tool.
- Native/transitive dependency: thư viện JNI/JNA, thư viện platform-specific và các artifact được nạp động.

Với mỗi dependency, ghi version đang dùng, version dự kiến, scope, nguồn kéo vào (direct/transitive), chức năng được sử dụng, bằng chứng hỗ trợ Java 21 và hành động cần làm.

### 4.1. Kiểm tra dependency graph bằng Maven

In cây dependency của project:

```bash
mvn dependency:tree
```

Có thể giới hạn theo scope hoặc tìm một artifact cụ thể:

```bash
mvn dependency:tree -Dscope=runtime
mvn dependency:tree -Dscope=test
mvn dependency:tree -Dincludes=groupId:artifactId
```

Khi một thư viện chỉ xuất hiện trong test runtime, không nhất thiết phải nâng nó cùng runtime dependency của ứng dụng. Ngược lại, dependency được đóng gói vào fat JAR hoặc container image phải được kiểm tra theo đúng artifact triển khai.

### 4.2. Kiểm tra dependency graph bằng Gradle

Liệt kê configuration tương ứng:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

Truy ngược nguồn của một dependency:

```bash
./gradlew dependencyInsight --dependency byte-buddy --configuration testRuntimeClasspath
```

Trên Windows có thể dùng `gradlew.bat`. Thay configuration theo project thực tế, vì Android, plugin, integration test hoặc custom source set có thể có classpath riêng.

### 4.3. Không chỉ dựa vào file khai báo

Dependency tree cho biết quan hệ được build tool giải quyết, nhưng chưa chắc phản ánh toàn bộ thành phần được triển khai. Kiểm tra thêm:

- Fat JAR, shaded JAR, WAR/EAR và thư mục `lib` trong image.
- Dependency được tải bằng classloader tùy chỉnh hoặc plugin runtime.
- JAR được copy thủ công vào server hoặc mount từ volume.
- Dependency lockfile, BOM và version catalog.
- SBOM hoặc danh sách artifact được tạo ở pipeline release.

Nếu có nhiều module, tạo inventory theo từng deployable artifact. Không lấy dependency tree của root project rồi coi đó là toàn bộ dependency của mọi service.

## 5. Kiểm tra framework và thư viện tích hợp

Một thư viện có thể biên dịch được với Java 21 nhưng vẫn gặp vấn đề lúc chạy do reflection, bytecode generation, classloader, TLS, serialization hoặc thay đổi hành vi runtime. Với mỗi framework, kiểm tra release notes và compatibility matrix của đúng phiên bản.

Các nhóm quan trọng:

| Nhóm | Ví dụ cần xác minh |
|---|---|
| Application framework | Spring, Jakarta EE runtime, Quarkus, Micronaut hoặc framework nội bộ |
| Server/container | Servlet container, application server, embedded server và plugin container |
| Database | JDBC driver, connection pool, ORM, migration tool và database client |
| Messaging | Kafka/RabbitMQ client, JMS implementation và serialization format |
| HTTP/network | HTTP client, Netty, TLS provider, proxy integration và DNS resolver |
| Serialization | Jackson, JSON-B, protobuf, Avro, Kryo hoặc thư viện binary format |
| Logging/metrics/tracing | SLF4J implementation, Log4j, OpenTelemetry, APM SDK và exporter |
| Security | Authentication provider, crypto provider, keystore/truststore và SSO client |
| Test/mocking | JUnit, Mockito, MockK, Byte Buddy, ASM và test runtime |

Không chỉ kiểm tra “thư viện hỗ trợ Java 21”. Cần xác minh cả framework version, JDK support range, phiên bản dependency bắc cầu và tính năng ứng dụng thực sự sử dụng. Một thư viện có thể hỗ trợ JDK 21 nhưng phiên bản cũ đang dùng trong ứng dụng đã hết hỗ trợ hoặc chứa lỗi đã được sửa ở bản mới.

## 6. Lập danh mục Maven/Gradle plugin và build extension

Build có thể thất bại trước khi source code được biên dịch vì plugin hoặc build extension chạy bằng JDK mới chưa tương thích.

### 6.1. Maven

Kiểm tra cả Maven distribution/wrapper và plugin trong `pom.xml`, parent POM, profile, plugin management và extension. Những plugin thường cần xác minh gồm:

- `maven-compiler-plugin`: compiler JDK, `release`, annotation processing.
- `maven-surefire-plugin` và `maven-failsafe-plugin`: test JVM, fork, module path và provider.
- `maven-enforcer-plugin`: rule về JDK, Maven và dependency convergence.
- `maven-jar-plugin`, `maven-war-plugin`, `maven-shade-plugin`: đóng gói và manifest.
- `maven-javadoc-plugin`: doclet và JDK API compatibility.
- `maven-checkstyle-plugin`, SpotBugs, PMD và các static analysis plugin.
- JaCoCo hoặc coverage plugin khác: agent và khả năng instrument class file.
- Plugin tạo source/resource, ORM metamodel, protobuf hoặc client code.

Ghi lại Maven Wrapper version và Maven runtime JDK. Plugin có thể được quản lý tập trung trong parent POM hoặc được thêm qua build extension nên tìm trong một `pom.xml` duy nhất là chưa đủ.

### 6.2. Gradle

Kiểm tra Gradle Wrapper, Gradle daemon JVM, Java toolchain, plugin DSL, legacy buildscript classpath và custom plugin nội bộ.

Các nhóm thường gặp:

- Java/application/library plugin và compiler/test task.
- Kotlin/Groovy/Scala plugin nếu build có nhiều ngôn ngữ JVM.
- Spring Boot, Shadow, application packaging và distribution plugin.
- JaCoCo, test logger, mutation testing và static analysis plugin.
- Code generation, annotation processor và bytecode enhancement.
- Custom Gradle plugin hoặc convention plugin trong `buildSrc`/included build.

Kiểm tra compatibility matrix của Gradle để xác nhận phiên bản nào có thể chạy trên JDK 21 và phiên bản nào có thể dùng Java 21 toolchain. Đây là hai điều kiện khác nhau; một Gradle release có thể hỗ trợ toolchain JDK 21 trước khi chính Gradle daemon có thể chạy trên JDK đó.

### 6.3. Build plugin cũng là dependency cần quản lý

Plugin thường kéo theo thư viện bytecode, ASM, Groovy, Kotlin, parser hoặc agent riêng. Khi plugin lỗi trên Java 21, hãy xác định lỗi đến từ plugin, dependency của plugin, build daemon hay application source. Nâng plugin có thể thay đổi cả dependency graph của build process, do đó lưu lại phiên bản và output của từng lần thử.

## 7. Lập danh mục Java agent và công cụ instrumentation

Agent cần được inventory riêng vì chúng chạy trong hoặc tác động trực tiếp đến JVM, có thể instrument class, quan sát runtime hoặc thay đổi hành vi thực thi.

Tìm các cách nạp agent trong script, manifest, container command, service configuration và CI:

| Cơ chế | Dấu hiệu cần tìm | Thời điểm nạp |
|---|---|---|
| Java startup agent | `-javaagent:/path/agent.jar` | Khi JVM khởi động, gọi `premain` |
| Native JVM TI agent | `-agentlib:name` hoặc `-agentpath:/path/library` | Khi JVM khởi động |
| Dynamic Java agent | Attach API, `VirtualMachine.loadAgent`, `agentmain` | Sau khi JVM đã chạy |
| Dynamic native agent | Attach/serviceability tooling nạp native agent | Sau khi JVM đã chạy |

Các agent thường gặp gồm APM, tracing, profiler, code coverage, security monitoring, async profiler, test instrumentation và mocking framework. Ghi lại agent artifact, version, vendor, checksum/source, cách nạp, process áp dụng và tính năng phụ thuộc vào agent.

### 7.1. Lưu ý JEP 451 trong Java 21

Java 21 phát cảnh báo khi Java agent được nạp động vào một JVM đang chạy. Dynamic loading vẫn được cho phép mặc định trong Java 21, nhưng JEP 451 chuẩn bị cho việc yêu cầu opt in rõ ràng ở release tương lai.

Khi thấy warning, hãy ghi lại đường dẫn JAR được nạp. Dùng dependency graph, startup command và trace để xác định thư viện nào kích hoạt attach. `-Djdk.instrument.traceUsage` có thể giúp truy tìm việc sử dụng API `java.lang.instrument`:

```bash
java -Djdk.instrument.traceUsage=true -jar application.jar
```

Nếu dynamic attach là nhu cầu vận hành đã được xác nhận trên HotSpot, Java 21 có thể bật rõ ràng:

```bash
java -XX:+EnableDynamicAgentLoading -jar application.jar
```

Đây là opt in cho dynamic loading, không chuyển agent thành startup agent. Nếu agent hỗ trợ startup, ưu tiên cấu hình nó bằng `-javaagent` trong JVM arguments và xác minh hướng dẫn của vendor. Không bật cờ chỉ để che warning khi chưa biết agent nào đang được nạp.

## 8. Kiểm tra native library và thành phần phụ thuộc nền tảng

Java 21 không làm cho native dependency tự động tương thích. Nếu ứng dụng dùng JNI, JNA, native transport, compression, crypto, database driver có native component hoặc agent native, cần kiểm tra riêng:

- Hệ điều hành và kiến trúc CPU được hỗ trợ (x64, ARM64...).
- ABI, libc và các native dependency hệ thống.
- Phiên bản binary được đóng gói hoặc tải trong runtime.
- `java.library.path`, biến môi trường và vị trí mount library.
- Native agent được nạp qua `-agentlib`/`-agentpath`.
- Hành vi shutdown, signal, thread attach/detach và native memory.

Một JAR có thể chạy trên nhiều JDK nhưng native library bên trong chỉ có binary cho một số OS/architecture. Vì vậy, inventory phải ghi cả platform artifact và image nền production.

## 9. Tìm API nội bộ JDK và API deprecated

Ứng dụng cũ có thể phụ thuộc vào class nội bộ như `sun.*`, `com.sun.*` hoặc API không thuộc Java SE được cam kết ổn định. Strong encapsulation của JDK đã được tăng cường từ các release trước; khi chuyển lên Java 21, các truy cập phản chiếu hoặc compile-time vào internals có thể tiếp tục gây lỗi hoặc cần cấu hình module access.

Có thể dùng `jdeps` để tìm phụ thuộc vào JDK internal API:

```bash
jdeps --jdk-internals --multi-release 21 path/to/application.jar
```

Có thể dùng `jdeprscan` để rà soát việc sử dụng API deprecated theo release mục tiêu:

```bash
jdeprscan --release 21 --for-removal path/to/application.jar
```

Các công cụ phân tích tĩnh có giới hạn: reflection dựa trên tên chuỗi, service loading, class được tải động, generated code hoặc native code có thể không được phát hiện đầy đủ. Hãy bổ sung tìm kiếm source, runtime test và log.

Nếu tạm thời cần `--add-exports` hoặc `--add-opens`, ghi rõ module/package, lý do, dependency sở hữu và kế hoạch loại bỏ. Đây là cấu hình mở quyền truy cập module, không phải bằng chứng rằng dependency đã tương thích lâu dài. Ưu tiên API công khai hoặc phiên bản thư viện đã thay thế truy cập internal.

## 10. Kiểm kê preview feature và incubator API

Java 21 có một số tính năng preview hoặc incubator. Nếu code hoặc dependency sử dụng chúng, cần ghi rõ vì preview API gắn với release cụ thể và có thể thay đổi hoặc bị loại bỏ.

Trong Java 21, ví dụ có các preview feature như String Templates, Structured Concurrency, Scoped Values, Unnamed Patterns and Variables, và Foreign Function & Memory API; Vector API ở trạng thái incubator. Các tính năng đã được final trong Java 21 như Record Patterns và Pattern Matching for `switch` không cần `--enable-preview`.

Kiểm tra:

- Source có dùng preview API hoặc syntax không?
- Compiler task có `--enable-preview` không?
- Test/runtime process có `--enable-preview` tương ứng không?
- Dependency có bytecode hoặc API phụ thuộc preview/incubator không?
- Nâng lên JDK release khác có cần viết lại hoặc biên dịch lại phần đó không?

Không bật `--enable-preview` đại trà chỉ để làm build qua. Chỉ bật khi tính năng preview thực sự là một phần có chủ đích của ứng dụng, và ghi nhận rủi ro phải cập nhật khi đổi JDK release.

## 11. Kiểm tra runtime image, container và cấu hình triển khai

Inventory phải đi tới đúng artifact được deploy. Kiểm tra:

- Base image và JDK distribution/version tag.
- Image digest hoặc package version thực tế, tránh chỉ ghi tag trôi nổi.
- Startup command, `JAVA_HOME`, `PATH` và JVM arguments.
- Environment variables, truststore, keystore và security provider.
- CPU/memory limit, container user, filesystem và quyền ghi.
- Liveness/readiness probe, graceful shutdown và signal handling.
- Script migration database, init container, sidecar và job chạy một lần.

Một pipeline có thể build bằng Java 21 nhưng image production vẫn dùng JDK cũ nếu Dockerfile hoặc deployment manifest không được cập nhật. Cũng có thể runtime image đã chuyển Java 21 nhưng sidecar hoặc migration job vẫn dùng image riêng với JDK khác.

## 12. Mẫu migration inventory

Nên lưu inventory trong hệ thống quản lý migration của nhóm để có owner, trạng thái và bằng chứng. Mỗi dòng tương ứng một thành phần có thể được nâng cấp hoặc xác minh độc lập.

| Trường | Nội dung |
|---|---|
| Component ID | Tên duy nhất của ứng dụng, module, dependency, plugin hoặc agent |
| Component type | Application / dependency / build plugin / agent / native / runtime image |
| Owner | Nhóm hoặc người chịu trách nhiệm |
| Current version | JDK/library/plugin/agent version hiện tại |
| Target version | Phiên bản hoặc compatibility target cần dùng |
| Scope | Build / compile / test / runtime / production / CI |
| Usage | Chức năng hoặc module đang sử dụng thành phần |
| Java 21 evidence | Compatibility matrix, release note, vendor support hoặc test result |
| Action | Keep / upgrade / replace / remove / investigate |
| Validation | Build, test, smoke, integration, load hoặc startup test |
| Status | Not started / investigating / ready / validated / blocked |
| Evidence link | Log, report, PR, SBOM hoặc tài liệu nhà cung cấp |

Ví dụ minh họa:

| Component | Type/scope | Current | Target/action | Validation |
|---|---|---|---|---|
| `catalog-api` | Application/runtime | JDK 17 | Chạy trên JDK 21 | Startup + integration + load test |
| `jdbc-driver` | Runtime dependency | Version đang dùng | Xác minh support Java 21; nâng nếu cần | Database integration test |
| `maven-surefire-plugin` | Build/test plugin | Version đang dùng | Xác minh test fork trên JDK 21 | Unit + integration test |
| `byte-buddy-agent` | Test agent | Version đang dùng | Xác minh cách attach/startup theo framework | Test có inline mocking |
| `native-transport` | Native dependency | Binary hiện tại | Xác minh OS/architecture và ABI | Container smoke test |

Các dòng trên chỉ là ví dụ cách ghi. Hãy điền version và kết quả kiểm chứng từ chính dependency graph và artifact của dự án; không suy đoán target version từ ví dụ.

## 13. Ma trận xác minh sau khi lập danh mục

Không đánh dấu một thành phần “compatible” chỉ vì build thành công. Chọn test theo phạm vi sử dụng:

| Phạm vi | Bằng chứng tối thiểu |
|---|---|
| Build tool/plugin | Build sạch trên JDK 21; compiler và packaging hoàn tất |
| Unit/test dependency | Toàn bộ test liên quan chạy trên đúng test JVM; agent warning/lỗi được giải thích |
| Runtime dependency | Startup, class loading, reflection, serialization và luồng nghiệp vụ chính hoạt động |
| Database/messaging/HTTP | Integration test với driver/client và dependency thực tế |
| Native/agent | Nạp thành công trên OS/architecture đích; chức năng instrumentation hoạt động |
| Container/deployment | Image đúng JDK, startup command, health check, graceful shutdown và quyền hệ thống đúng |
| Production behavior | Canary/smoke, error rate, latency, GC và resource metrics đạt tiêu chí |

Với thành phần chỉ được dùng ở một nhánh hiếm, thêm test kích hoạt nhánh đó. Test startup thông thường không thể xác nhận một native library hoặc agent được nạp muộn sẽ hoạt động.

## 14. Quy trình lập danh mục theo thứ tự

1. **Liệt kê deployable**: service, worker, batch, CLI, test runtime và công cụ vận hành.
2. **Ghi JDK theo từng process**: build JVM, compiler toolchain, test JVM và production runtime.
3. **Xuất dependency graph**: direct/transitive theo compile, runtime, test và custom configuration.
4. **Liệt kê build plugin**: Maven/Gradle wrapper, plugin, extension, annotation processor và custom build logic.
5. **Tìm agent**: startup flags, Attach API, warning JEP 451, profiler, APM, coverage và mocking.
6. **Tìm native/internal/preview**: JNI/JNA, JDK internals, deprecated API, preview/incubator và module access flags.
7. **Kiểm tra artifact triển khai**: JAR/WAR/image, startup scripts, base image, environment và deployment manifest.
8. **Đối chiếu compatibility evidence**: support matrix, release notes, issue tracker và test với JDK 21.
9. **Gán owner và hành động**: upgrade, replace, remove hoặc investigate; ghi blocker và dependency liên quan.
10. **Chạy validation theo phạm vi**: build, test, integration, native/agent smoke, deployment và performance baseline.

## 15. Checklist hoàn tất inventory

Trước khi chuyển sang bước nâng cấp, xác nhận:

- [ ] Đã liệt kê tất cả JVM application, job, CLI và test process.
- [ ] Đã ghi riêng JDK build, compiler toolchain, test JVM và production runtime.
- [ ] Đã kiểm tra direct/transitive dependency ở mọi scope/configuration.
- [ ] Đã kiểm tra artifact đóng gói và dependency được tải động.
- [ ] Đã liệt kê Maven/Gradle wrapper, plugin, extension và annotation processor.
- [ ] Đã liệt kê Java agent, native agent và cách nạp của từng agent.
- [ ] Đã điều tra warning dynamic attach theo JEP 451 nếu xuất hiện.
- [ ] Đã rà soát native library, JDK internal API và preview/incubator usage.
- [ ] Đã xác minh container image, startup flags, truststore và deployment scripts.
- [ ] Mỗi thành phần có owner, action, status và bằng chứng Java 21.
- [ ] Đã xác định thành phần chưa tương thích hoặc chưa đủ bằng chứng làm blocker.

## 16. Tài liệu tham khảo chính thức

- [Java SE 21 Migration Guide](https://docs.oracle.com/en/java/javase/21/migrate/): thay đổi cần kiểm tra khi chuyển ứng dụng sang JDK 21.
- [Java SE 21 `jdeps` tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html): phân tích dependency và JDK internal API.
- [Java SE 21 `jdeprscan` tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeprscan.html): rà soát việc sử dụng API deprecated.
- [Java SE 21 `javac` tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `--release`, source và target platform.
- [JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451): cảnh báo và chính sách dynamic agent loading.
- [Java SE 21 Instrumentation API](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): startup và dynamic Java agent.
- [Java SE 21 Attach API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): attach vào JVM đang chạy.
- [Gradle Java compatibility](https://docs.gradle.org/current/userguide/compatibility.html): phân biệt Java version dùng để chạy Gradle và Java toolchain.

Migration inventory tốt phải bao phủ toàn bộ đường đi từ build đến runtime: ứng dụng, JDK/toolchain, dependency, plugin, agent, native library và deployment image. Khi mỗi thành phần có owner, phiên bản hiện tại, mục tiêu, bằng chứng tương thích Java 21 và bước xác minh cụ thể, nhóm có thể nâng cấp có kiểm soát, xử lý blocker đúng nơi và tránh bỏ sót lỗi chỉ xuất hiện trong test hoặc production.
