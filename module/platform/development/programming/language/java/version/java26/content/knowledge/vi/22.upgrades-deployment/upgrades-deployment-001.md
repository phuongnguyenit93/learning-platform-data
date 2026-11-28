# Kiểm kê runtime, thư viện, plugin và cấu hình JVM

Nâng cấp Java thành công bắt đầu từ việc biết chính xác ứng dụng đang chạy bằng JDK nào, được build bằng công cụ nào, nạp những thư viện và plugin nào, và JVM nhận cấu hình từ đâu. Chỉ đọc pom.xml hoặc build.gradle chưa đủ: JDK dùng để chạy service có thể khác JDK dùng để build; dependency khai báo trực tiếp có thể kéo theo nhiều dependency bắc cầu; plugin có thể được nạp từ parent build, settings, init script hoặc môi trường triển khai; JVM options có thể đến từ command line, biến môi trường, service manager và container.

Bài học này xây dựng quy trình kiểm kê trước khi nâng cấp lên JDK 26. Mục tiêu là tạo được một bản kê có bằng chứng, xác định rủi ro tương thích và chuẩn bị bộ kiểm thử cho đúng runtime sẽ triển khai. Nội dung ưu tiên công cụ JDK và lệnh Maven/Gradle còn được dùng hiện nay; không dựa vào các cơ chế triển khai Java đã bị loại bỏ như Applet hoặc Java Web Start.

## 1. Vì sao phải kiểm kê trước khi nâng cấp?

Một ứng dụng Java thực tế là tổ hợp nhiều lớp:

~~~text
Máy / Container / OS / CPU
          |
          v
JDK runtime + JVM options + security properties
          |
          v
Application entry point / classpath / module path
          |
          +--> Application libraries
          +--> Frameworks and runtime plugins
          +--> Java agents / native libraries
          +--> Service providers / JDBC drivers
          |
          v
External services and data stores

Build environment:
JDK toolchain + Maven/Gradle + build plugins
          |
          v
Source code + annotation processors + dependencies
          |
          v
JAR / module / custom runtime image / container image
~~~

Một thay đổi ở bất kỳ lớp nào cũng có thể làm ứng dụng không khởi động, không liên kết được class, thay đổi hành vi hoặc suy giảm hiệu năng. Ví dụ:

- Build thành công bằng JDK 26 nhưng service vẫn chạy JDK cũ do PATH hoặc service definition trỏ sang runtime khác.
- Thư viện trực tiếp hỗ trợ JDK 26 nhưng một dependency bắc cầu vẫn gọi API đã bị loại bỏ.
- Maven compiler plugin hoặc Gradle plugin quá cũ không hiểu JDK mới.
- Một agent APM hoặc profiler không tương thích với bytecode/JVM mới.
- Ứng dụng phụ thuộc sun.*, jdk.internal.*, reflection vào package không mở hoặc các tùy chọn --add-opens tồn tại từ nhiều năm trước.
- Container có JDK đúng version nhưng thiếu module, native library, CA certificate hoặc cấu hình timezone mà ứng dụng cần.

Kiểm kê tạo ra đường cơ sở để so sánh trước/sau. Không chỉ ghi “Java 26”; cần ghi vendor, full build, runtime image, toolchain, dependency graph, plugin version và các JVM options thực tế.

## 2. Chốt phạm vi và phiên bản đích

Trước khi thu thập dữ liệu, xác định các ứng dụng, service, batch job, worker, migration tool và môi trường nằm trong đợt nâng cấp. Một repository có thể chứa nhiều module chạy trên các JDK khác nhau.

Tạo phạm vi rõ ràng:

| Phạm vi | Cần xác định |
|---|---|
| Ứng dụng | Tên service, entry point, module/repository và chủ sở hữu |
| Môi trường | Local, CI, test, staging, production, container hoặc máy ảo |
| Build | JDK dùng để chạy Maven/Gradle và JDK compiler toolchain |
| Runtime | JDK thực tế của từng tiến trình đang chạy |
| Target | JDK/vendor/build sẽ được kiểm thử và triển khai |
| Packaging | JAR, WAR, application server, jlink image, jpackage hoặc container |
| Ngoại vi | Database, message broker, HTTP service, HSM, native library và hệ điều hành |

Phân biệt ba lựa chọn thường bị gộp làm một:

1. **Build JDK:** chạy Maven/Gradle và compiler.
2. **Compile target:** mức Java API và bytecode mà ứng dụng yêu cầu.
3. **Runtime JDK:** JDK thực sự chạy ứng dụng ở môi trường triển khai.

Chúng có thể khác nhau. Ví dụ, build bằng JDK 26 với --release 25 vẫn tạo ứng dụng nhắm tới Java 25; runtime JDK 26 có thể chạy bytecode đó. Ngược lại, biên dịch bằng JDK 26 và dùng API chỉ có từ Java 26 thì runtime Java 25 không thể chạy ứng dụng đó.

## 3. Kiểm kê JDK, JVM và môi trường hệ điều hành

### 3.1. Kiểm tra JDK được tìm thấy qua PATH

Trên Windows PowerShell:

~~~powershell
Get-Command java -All
Get-Command javac -All
where.exe java
where.exe javac

java --version
javac --version
java -XshowSettings:properties -version
java --list-modules
~~~

Trên Linux/macOS:

~~~bash
command -v java
command -v javac
type -a java
java --version
javac --version
java -XshowSettings:properties -version
java --list-modules
~~~

Ghi nhận ít nhất:

| Thuộc tính | Ý nghĩa |
|---|---|
| java.version | Phiên bản Java runtime |
| java.runtime.version | Full runtime version/build string |
| java.vendor | Nhà cung cấp JDK |
| java.vm.name | Tên implementation JVM |
| java.vm.version | Phiên bản VM |
| java.home | Thư mục runtime thực tế |
| os.name, os.version | Hệ điều hành |
| os.arch | Kiến trúc CPU |
| file.encoding | Charset mặc định |
| user.timezone | Timezone hiệu lực nếu được thiết lập |
| java.class.path | Classpath mà process nhận được |

Get-Command, where.exe hoặc command -v chỉ cho biết executable tìm thấy trong shell hiện tại. Nó không chứng minh service đang chạy dùng cùng executable. Service manager, IDE, container entrypoint, CI runner hoặc wrapper script có thể đặt JAVA_HOME và PATH khác.

### 3.2. Kiểm tra JDK của build tool

Maven:

~~~powershell
mvn -version
~~~

Gradle:

~~~powershell
.\gradlew.bat --version
~~~

Lệnh trên cho biết JVM mà Maven hoặc Gradle launcher đang dùng. Build tool có thể tiếp tục chọn compiler toolchain riêng theo cấu hình dự án. Vì vậy, cần kiểm tra cả toolchain trong pom.xml, settings.xml, build.gradle và gradle.properties.

Ghi lại:

- JDK vendor và full version.
- Maven/Gradle version.
- Maven Wrapper hoặc Gradle Wrapper version.
- Compiler toolchain và release target.
- JDK được CI runner và IDE sử dụng.
- JDK trong image triển khai.

Không kết luận build tương thích chỉ vì java --version trong terminal trả về 26.

### 3.3. Kiểm tra tiến trình đang chạy

Dùng công cụ JDK cùng máy với JVM đích:

~~~powershell
jcmd -l
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags -all
jcmd <pid> VM.system_properties
jcmd <pid> VM.info
~~~

Ý nghĩa:

| Lệnh | Dữ liệu thu được |
|---|---|
| jcmd -l | Các JVM process mà công cụ có thể nhìn thấy |
| VM.version | Runtime/VM version của process |
| VM.command_line | Main class/JAR và command-line arguments |
| VM.flags -all | Các VM flags và giá trị hiện tại |
| VM.system_properties | System properties của process |
| VM.info | Thông tin môi trường và trạng thái JVM |

Chạy jcmd trên cùng máy với JVM và bằng effective user/group phù hợp với process. Trong container riêng, chạy công cụ trong đúng container hoặc dùng cách quản trị được nền tảng hỗ trợ; jcmd -l trên host có thể không liệt kê process nằm trong một Docker namespace riêng.

Các kết quả VM.command_line và VM.system_properties có thể chứa password, token, URL có credential, đường dẫn nội bộ hoặc thông tin nhạy cảm. Chỉ lưu bản đã rà soát và che giá trị bí mật trước khi đưa vào ticket, artifact CI hoặc tài liệu chia sẻ.

### 3.4. Kiểm tra runtime image và module

Với runtime image chuẩn:

~~~powershell
java --list-modules
~~~

Nếu ứng dụng được đóng gói bằng jlink, kiểm tra danh sách module thực tế trong image đó, không suy ra từ JDK đầy đủ ở máy build. Có thể dùng jdeps --print-module-deps để tìm module cần thiết từ bytecode và dependency đã cung cấp.

Với JAR/module:

~~~powershell
jar --describe-module --file .\app.jar
jdeps --multi-release 26 --list-deps .\app.jar
jdeps --multi-release 26 --print-module-deps .\app.jar
~~~

Một JAR không có module descriptor có thể trở thành automatic module khi đặt trên module path. Ghi nhận module name, automatic module name, multi-release entries và các requires, uses, provides nếu có. Không chỉ nhìn tên file JAR để xác định module.

## 4. Kiểm kê dependency trực tiếp và bắc cầu

Dependency inventory phải phản ánh dependency đã được resolve, không chỉ danh sách khai báo. Một thư viện có thể xuất hiện do framework, BOM, plugin hoặc dependency bắc cầu; phiên bản thực tế có thể khác phiên bản người viết build file tưởng rằng đang dùng.

Mỗi dependency cần có các trường:

- Group/artifact/name và version đã resolve.
- Scope/configuration: compile, runtime, test, provided hoặc tương đương.
- Nguồn khai báo: module, BOM, version catalog, parent build hoặc plugin.
- Quan hệ direct/transitive.
- Module name và multi-release JAR nếu có.
- Native component hoặc service provider đi kèm.
- Trạng thái hỗ trợ JDK 26 theo tài liệu nhà cung cấp.
- Lỗ hổng bảo mật, license và người chịu trách nhiệm nâng cấp.

### 4.1. Maven

Các lệnh hữu ích:

~~~powershell
mvn -version
mvn help:active-profiles
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn dependency:tree -Dverbose
mvn dependency:resolve-plugins
~~~

Dùng kết quả để kiểm tra:

- Dependency trực tiếp và bắc cầu đã resolve.
- Phiên bản được chọn sau dependency mediation.
- BOM và dependencyManagement.
- Plugin build, plugin reporting và dependency của plugin.
- Profile kích hoạt theo môi trường.
- Parent POM và cấu hình compiler/surefire/failsafe.

dependency:tree tập trung vào dependency của project. dependency:resolve-plugins giúp kiểm kê plugin và dependency của plugin. Để kiểm tra plugin khai báo, hãy đọc effective POM, bao gồm build/plugins, pluginManagement, reporting và các extension. Cũng kiểm tra .mvn/extensions.xml, Maven Wrapper, parent POM và settings/profile áp dụng từ môi trường build.

Không chỉ kiểm tra POM con. Một plugin hoặc version có thể được kế thừa từ parent POM hoặc profile; một extension có thể thay đổi hành vi Maven trước khi project model được xử lý.

### 4.2. Gradle

Các lệnh hữu ích:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat :app:dependencies --configuration compileClasspath
.\gradlew.bat :app:dependencies --configuration runtimeClasspath
.\gradlew.bat :app:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
.\gradlew.bat buildEnvironment
~~~

Thay :app bằng project path thật. Dùng dependencyInsight để xác định vì sao một version được chọn, ví dụ do constraint, conflict resolution, platform/BOM hoặc dependency bắc cầu.

Kiểm tra các vị trí sau:

- Khối plugins {} trong build.gradle/build.gradle.kts.
- pluginManagement {} và plugins {} trong settings.gradle/settings.gradle.kts.
- buildscript { dependencies { classpath(...) } }.
- buildSrc, included builds và convention plugins.
- Version catalogs như gradle/libs.versions.toml.
- Gradle Wrapper và các file gradle.properties.
- Init scripts trong môi trường CI hoặc máy build.
- Annotation processor và compiler plugin configurations.

buildEnvironment cho biết buildscript classpath; nó không thay thế việc kiểm tra plugin DSL và plugin resolution trong settings. Cần ghi cả repository plugin, version và cơ chế quản lý version.

### 4.3. Nhóm thư viện cần kiểm tra riêng

| Nhóm | Ví dụ thành phần cần kiểm kê | Rủi ro khi đổi JDK |
|---|---|---|
| Framework ứng dụng | Web framework, dependency injection, ORM | Reflection, proxy, bytecode generation, module access |
| Logging/observability | Logging API/backend, bridge, tracing, APM | Agent instrumentation, classloader và module access |
| HTTP/network | HTTP client, Netty, native transport | TLS, ALPN, native library và protocol |
| Database | JDBC driver, connection pool, ORM | Driver compatibility, TLS, LOB, module loading |
| Serialization | JSON, XML, Avro, Protobuf | Reflection, annotation processing, generated code |
| Security/crypto | Provider, PKCS#11, HSM integration | Algorithm policy, provider, native library, key format |
| Messaging | Kafka/RabbitMQ client, JMS | TLS, serialization và dependency bắc cầu |
| Testing | JUnit, Mockito, test engine, coverage | Agent, instrumentation và module access |
| Build/compiler | Compiler plugin, annotation processor, Kotlin/Scala plugin | JDK toolchain, bytecode target, compiler internals |
| Native integration | JNI/JNA, compression, image, database native client | OS, CPU architecture, ABI và shared library |

Đối với từng thư viện quan trọng, tra tài liệu hỗ trợ của đúng phiên bản và kiểm thử trên đúng JDK vendor/build. Câu “hỗ trợ Java 17+” không luôn chứng minh tương thích với mọi thay đổi ở Java 26, đặc biệt với agent, framework sử dụng reflection sâu hoặc thư viện có native code.

## 5. Kiểm kê build plugin, annotation processor và runtime plugin

Từ “plugin” có thể chỉ nhiều cơ chế khác nhau. Hãy chia nhóm để tránh bỏ sót:

| Nhóm | Thời điểm hoạt động | Ví dụ vị trí cần kiểm tra |
|---|---|---|
| Maven/Gradle build plugin | Trong build | pom.xml, build.gradle, settings, parent POM |
| Compiler plugin | Khi biên dịch | Compiler plugin config, Kotlin/Scala compiler |
| Annotation processor | Khi biên dịch | annotationProcessor, annotationProcessorPaths, processor path |
| Test plugin/engine | Khi test | Surefire/Failsafe, JUnit Platform engine, test runtime |
| Java agent | Khi JVM khởi động/chạy | -javaagent, manifest Premain-Class, Agent-Class |
| Native agent | Khi JVM khởi động | -agentlib, -agentpath |
| Runtime plugin | Khi ứng dụng chạy | SPI, ServiceLoader, module provides/uses, thư mục plugin |
| IDE plugin | Trên máy phát triển | IDE extension, compiler integration, formatter |

### 5.1. Java agent và native agent

Tìm các tham số:

~~~text
-javaagent:<path>[=<options>]
-agentlib:<name>[=<options>]
-agentpath:<path>[=<options>]
~~~

Các agent thường gặp gồm APM, tracing, profiler, coverage, security instrumentation và bytecode enhancement. Ghi lại tên, version, checksum, nguồn tải, cách cấu hình, thứ tự nạp và môi trường nào bật agent.

Agent có thể biến đổi bytecode hoặc phụ thuộc API nội bộ của JVM. Một ứng dụng khởi chạy thành công khi không có agent chưa đủ để xác nhận production tương thích nếu production luôn bật agent.

### 5.2. Annotation processor và compiler extension

Annotation processor chạy trong quá trình compile, có thể sinh source/class hoặc kiểm tra code. Ghi lại:

- Tên và version processor.
- Compiler JDK được dùng.
- Processor path và thứ tự xử lý nếu có.
- Generated sources có được commit hay tạo lại trong build.
- Plugin compiler và cấu hình incremental compilation.
- Processor có phụ thuộc com.sun.tools.javac.* hoặc API nội bộ hay không.

Không nhầm annotation processor với dependency runtime. Một processor có thể không được đóng gói trong ứng dụng nhưng vẫn là thành phần bắt buộc để build tái lập được.

### 5.3. Runtime plugin và Java SPI

Ứng dụng có thể nạp provider qua ServiceLoader, META-INF/services, module descriptor uses/provides, classloader tùy chỉnh hoặc thư mục plugin. Hãy kiểm tra:

- Service interface và implementation provider.
- Module nào khai báo uses/provides.
- JAR nào chứa META-INF/services.
- Quy tắc classloader và thứ tự nạp.
- Cấu hình bật/tắt plugin theo môi trường.
- Plugin có nạp native library hoặc reflection vào package nội bộ không.

Nếu plugin được tải động từ thư mục ngoài artifact chính, phải kiểm kê cả nội dung thư mục đó, version và checksum. Chỉ ghi dependency trong pom.xml/build.gradle sẽ bỏ sót nhóm plugin này.

## 6. Kiểm tra phụ thuộc JDK internal API và API đã deprecated

### 6.1. Dùng jdeps để tìm internal API

jdeps phân tích dependency ở mức package/class. Ví dụ:

~~~powershell
jdeps --multi-release 26 --jdk-internals --recursive --class-path "lib/*" .\target\app.jar
~~~

--jdk-internals tìm dependency tới API nội bộ JDK. --multi-release 26 chọn view phù hợp khi phân tích multi-release JAR. Cung cấp classpath/module path đủ để phân giải dependency; nếu thiếu thư viện, kết quả có thể báo missing dependencies.

Có thể xem module dependencies:

~~~powershell
jdeps --multi-release 26 --list-deps .\target\app.jar
jdeps --multi-release 26 --print-module-deps .\target\app.jar
~~~

--print-module-deps hữu ích khi chuẩn bị custom runtime image bằng jlink.

Giới hạn của jdeps:

- Phân tích tĩnh bytecode, không thực thi mọi nhánh.
- Có thể không phát hiện tên class/method được tạo động qua reflection.
- Không thay thế kiểm thử runtime, JNI/native analysis hoặc kiểm tra plugin được tải từ ngoài.
- Cần phân tích cả JAR của ứng dụng và các thư viện quan trọng, không chỉ một JAR đầu ra.

Nếu phát hiện sun.*, jdk.internal.* hoặc package nội bộ khác, ưu tiên thay bằng API Java SE được hỗ trợ hoặc nâng thư viện sở hữu dependency. Các tùy chọn --add-exports và --add-opens có thể là giải pháp chuyển tiếp trong trường hợp có lý do kỹ thuật, nhưng cần ghi rõ package, module, caller, chủ sở hữu và thời hạn loại bỏ. Không biến danh sách mở package thành cấu hình mặc định lâu dài.

### 6.2. Dùng jdeprscan để tìm Java SE API deprecated

Ví dụ:

~~~powershell
jdeprscan --for-removal .\target\app.jar
jdeprscan --class-path "lib/*" --for-removal .\target\app.jar
~~~

jdeprscan quét việc sử dụng API deprecated thuộc Java SE. Nó không báo API deprecated của thư viện bên thứ ba. Khi quét JAR có dependency, cung cấp classpath phù hợp để công cụ phân giải class.

Để xem cú pháp được JDK đang dùng hỗ trợ:

~~~powershell
jdeprscan --help
~~~

Lưu ý --release của jdeprscan dùng để so sánh các bộ API lịch sử được công cụ hỗ trợ; không tự thêm --release 26 vào lệnh quét nếu help của bản JDK hiện tại không liệt kê giá trị đó. Khi cần kiểm tra API bị loại bỏ trong JDK 26, đối chiếu Migration Guide và Removed APIs của đúng release, sau đó quét artifact bằng công cụ tương thích.

### 6.3. Các thay đổi cần đưa vào checklist JDK 26

JDK 26 đã loại bỏ một số API cũ. Ví dụ đáng chú ý:

- Package java.applet, bao gồm Applet và các kiểu liên quan.
- javax.swing.JApplet.
- java.lang.Thread.stop().
- Một số method cũ liên quan TTL/multicast socket và finalization.

Danh sách đầy đủ nằm trong phần Removed APIs của Oracle JDK 26 Migration Guide. Không dựa vào ví dụ trong bài để thay thế danh sách chính thức; hãy kiểm tra toàn bộ API mà ứng dụng và dependency sử dụng.

Ngoài API bị loại bỏ, hãy kiểm tra API deprecated for removal, các API thay đổi hành vi và các tùy chọn JVM đã obsolete. Một chương trình có thể biên dịch nhưng vẫn thất bại khi reflection, class loading hoặc đường chạy ít được test được kích hoạt.

## 7. Kiểm kê toàn bộ cấu hình JVM

Không phải mọi JVM option đều nằm trong command line mà developer nhìn thấy. Nguồn cấu hình có thể gồm:

- Command line của service hoặc container entrypoint.
- Biến môi trường JDK_JAVA_OPTIONS và JAVA_TOOL_OPTIONS.
- Script khởi động, systemd, Windows service wrapper hoặc application server.
- Dockerfile, Compose, Kubernetes Deployment/StatefulSet, Helm chart.
- File cấu hình JVM options do nền tảng triển khai nạp.
- Application properties và system properties truyền bằng -D.
- Security properties trong JDK.
- Runtime management thay đổi một số flag qua diagnostic command.

JAVA_OPTS thường là biến do script hoặc build/deploy wrapper tự quy ước; Java launcher không tự đọc biến này như một biến chuẩn. Phải kiểm tra script thực tế để biết nó được truyền vào lệnh java hay không.

### 7.1. Nhóm JVM options cần ghi nhận

| Nhóm | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| Heap | -Xms, -Xmx, -XX:MaxRAMPercentage | Giới hạn heap có phù hợp container memory không? |
| Garbage collector | -XX:+UseG1GC, -XX:+UseZGC | Collector nào được chọn và có chủ đích không? |
| Thread/stack | -Xss, giới hạn thread | Native memory và số thread có phù hợp không? |
| JIT/compiler | -XX:TieredCompilation, compiler directives | Có override mặc định hoặc dùng flag không còn hỗ trợ không? |
| Module/access | --add-modules, --add-opens, --add-exports | Module/package nào đang được mở và vì sao? |
| Preview/incubator | --enable-preview, --add-modules jdk.incubator.* | Có phụ thuộc API chưa ổn định không? |
| Agent | -javaagent, -agentlib, -agentpath | Agent nào instrument process? |
| Logging/diagnostics | -Xlog, JFR, heap dump options | Log và dump được ghi ở đâu, dung lượng/retention ra sao? |
| Security | Truststore, keystore, provider và security properties | TLS/crypto có cùng cấu hình ở mọi môi trường không? |
| Locale/time | -Duser.language, -Duser.country, -Duser.timezone | Format ngày, số, tiền tệ và timezone có nhất quán không? |
| Encoding | -Dfile.encoding và cấu hình giao thức | Các hệ thống trao đổi dữ liệu có dùng cùng encoding không? |

Ghi cả giá trị cấu hình lẫn nguồn của giá trị. Một giá trị trong Dockerfile có thể bị ghi đè bởi Helm chart; một biến môi trường trong production có thể khác staging.

### 7.2. Thu thập VM flags

Đối với process đang chạy:

~~~powershell
jcmd <pid> VM.flags -all
jcmd <pid> VM.command_line
~~~

Đối với một lần khởi động thử:

~~~powershell
java -XX:+PrintCommandLineFlags -version
java -XX:+PrintFlagsFinal -version
~~~

PrintCommandLineFlags giúp quan sát các flag JVM chọn theo ergonomics. PrintFlagsFinal hiển thị giá trị flag cuối cùng của lần khởi chạy kiểm tra. Các giá trị ergonomics phụ thuộc phần cứng, container limits và build JDK; không sao chép nguyên cấu hình từ máy phát triển sang production mà không đo lại.

Khi nâng JDK, xem cảnh báo startup về VM options obsolete/unsupported. Nếu JVM không khởi động, kiểm tra option bị loại bỏ, GC option cũ, flag không còn tồn tại hoặc giá trị vượt phạm vi. Không giữ một flag chỉ vì nó từng xuất hiện trong cấu hình nhiều năm trước.

### 7.3. Các tùy chọn module access cần rà soát

Tìm trong toàn bộ startup configuration:

~~~text
--add-opens
--add-exports
--add-reads
--patch-module
--add-modules
--enable-preview
~~~

Với từng option, ghi:

- Module/package được tác động.
- Module hoặc thư viện caller.
- Lý do cần quyền truy cập.
- Có thể nâng thư viện hoặc chuyển sang API public hay không.
- Phiên bản nào dự kiến loại bỏ workaround.
- Test nào chứng minh có thể bỏ option.

Không dựa vào --illegal-access như cách mở toàn bộ package nội bộ. Đây là tùy chọn cũ đã obsolete/ignored trên các JDK hiện đại và không phải giải pháp tương thích cho JDK 26.

## 8. Kiểm tra preview feature và incubator module

Một bản inventory cần phân biệt API chính thức với API đang preview hoặc incubator. Việc code biên dịch được trên máy developer không chứng minh production runtime đã được cấu hình đúng.

### Ví dụ feature Java 26 cần ghi trong inventory

| Feature | JEP | Trạng thái ở JDK 26 | Điều cần ghi nhận |
|---|---|---|---|
| HTTP/3 cho HTTP Client | 517 | API chuẩn, không phải preview | Client implementation, protocol negotiation, proxy, TLS và server tương thích |
| Primitive types trong pattern, instanceof và switch | 530 | Fourth Preview | Source set dùng feature, compiler/runtime flags và kế hoạch theo dõi JDK 27 |
| Structured Concurrency | 525 | Sixth Preview | API preview, cancellation/error semantics và `--enable-preview` ở compile/runtime |
| Vector API | 529 | Eleventh Incubator | Module `jdk.incubator.vector`, CPU architecture và fallback khi không có vector instruction phù hợp |
| Lazy Constants | 526 | Second Preview | API preview, thời điểm khởi tạo và khả năng thay đổi giữa các release |
| PEM Encodings of Cryptographic Objects | 524 | Second Preview | API preview, loại key/certificate và chính sách bảo mật |
| AOT Object Caching with Any GC | 516 | Cải tiến HotSpot runtime | JDK build, GC, quy trình tạo cache và tính tương thích của artifact |
| G1 giảm đồng bộ hóa | 522 | Cải tiến HotSpot runtime | Collector thực tế, workload và benchmark trước/sau |

Trạng thái ở bảng là của JDK 26 GA. Không suy luận trạng thái ở JDK 27 từ bảng này; tra JEP/release notes của target runtime và biên dịch, kiểm thử lại theo release đó.

### Preview feature

Nếu code dùng preview feature của JDK 26:

- Compile với --enable-preview --release 26.
- Chạy bằng JDK 26 với --enable-preview.
- Ghi nhận JEP, feature, source set và module sử dụng.
- Xác định kế hoạch bỏ preview hoặc nâng cấp theo release tiếp theo.

Preview feature có thể thay đổi hoặc bị loại bỏ giữa các release. Khi chuyển sang JDK 27, phải đọc trạng thái JEP ở JDK 27 và biên dịch/test lại theo release mới. Không coi preview class file của JDK 26 là artifact dùng lâu dài cho các runtime tương lai.

### Incubator module

Incubator API có thể nằm trong module riêng và cần khai báo module khi compile/runtime. Ví dụ Vector API ở JDK 26 vẫn là incubator:

~~~powershell
javac --add-modules jdk.incubator.vector --release 26 App.java
java --add-modules jdk.incubator.vector App
~~~

Kiểm kê module incubator, tên module, JEP, flags và dependency cụ thể. Không đưa incubator API vào public contract hoặc thư viện dùng chung nếu chưa chấp nhận chi phí thay đổi API khi nâng JDK.

### Mẫu ghi nhận

| Feature/API | JEP | Trạng thái ở target JDK | Module/flag | Người sở hữu | Kế hoạch |
|---|---|---|---|---|---|
| API chuẩn | JEP nếu có | Final | Không cần preview | Team ứng dụng | Có thể dùng theo API contract |
| Preview | JEP | Preview lần N | --enable-preview | Team ứng dụng | Đánh giá mỗi release |
| Incubator | JEP | Incubator lần N | --add-modules ... | Team ứng dụng | Theo dõi thay đổi và giới hạn phạm vi |

## 9. Kiểm kê native library, JNI và runtime dependency bên ngoài

Các thư viện native không được thể hiện đầy đủ trong Maven/Gradle dependency tree. Chúng có thể được tải bằng System.loadLibrary(), JNA, JNI, provider mật mã, Netty native transport, compression library hoặc thư viện do vendor cài trên máy.

Ghi nhận:

- Tên file native (.dll, .so, .dylib) và version.
- Nguồn đóng gói: trong JAR, trong container image hay cài trên host.
- CPU architecture và ABI.
- OS version, libc và các shared library phụ thuộc.
- Cách xác định đường dẫn (java.library.path, biến môi trường, absolute path).
- Quyền đọc/ghi và yêu cầu hệ thống.
- Hỗ trợ của nhà cung cấp đối với JDK 26 và OS đích.

Không giả định một native binary chạy được trên mọi JDK chỉ vì Java wrapper compile thành công. Đổi CPU architecture, base image hoặc libc có thể làm native component lỗi ngay khi load.

## 10. Kiểm kê container và cấu hình triển khai

Nếu ứng dụng chạy trong container, runtime thật là JDK và hệ điều hành bên trong image. JDK trên host không đại diện cho JDK trong container.

Kiểm tra:

- Base image và immutable digest.
- JDK distribution, vendor, full build và module list.
- OS distribution/version, architecture, libc.
- CA certificates, timezone database và locale packages.
- Native libraries, fonts hoặc package hệ thống mà ứng dụng cần.
- Container memory/CPU limits và JVM container awareness.
- Entrypoint, command, environment variables và mounted configuration.
- Read-only filesystem, user ID, file permissions và thư mục ghi heap dump/JFR/log.
- Health check, graceful shutdown và signal handling.
- Helm values, Kubernetes resource requests/limits và rollout strategy.

Nếu dùng custom runtime image, kiểm tra module list và service provider được giữ lại. Image được tạo bằng jlink có thể thiếu module mà một plugin hoặc driver chỉ nạp động ở production.

Không lưu secret thật trong inventory. Chỉ ghi tên secret/config key, nguồn quản lý và người sở hữu.

## 11. Kiểm kê security provider, TLS và trust material

Runtime JDK mới có thể đi kèm thay đổi provider, thuật toán bị disabled, TLS protocol/cipher support, certificate validation hoặc truststore. Hãy ghi nhận:

- Security providers đã đăng ký và provider được ứng dụng chọn.
- JDBC/HTTP client TLS configuration.
- Truststore/keystore type, vị trí và cơ chế cấp phát.
- CA certificates và chu kỳ cập nhật.
- Custom provider, PKCS#11, HSM và native library.
- Security properties được override.
- Thuật toán/cipher/protocol được ứng dụng cấu hình tường minh.
- Certificate chain, hostname verification và mutual TLS.
- Cách xoay vòng key/certificate và cách triển khai secret.

Với Oracle JDK 26, kiểm tra thêm security property `jdk.crypto.disabledAlgorithms` ở tầng JCA/JCE. Phân biệt nó với `jdk.tls.disabledAlgorithms` (TLS/DTLS), `jdk.certpath.disabledAlgorithms` (kiểm tra certificate path) và `crypto.policy` (giới hạn độ mạnh/key size theo jurisdiction policy). Đây là các lớp chính sách khác nhau; provider hỗ trợ một thuật toán không đồng nghĩa runtime cho phép dùng thuật toán đó. Với JDK distribution khác, xác minh property và hành vi theo tài liệu của vendor.

Kiểm tra các file security configuration được runtime sử dụng và mọi override qua system property. Không copy toàn bộ java.security từ JDK cũ sang JDK mới; file đó có thể bỏ lỡ property mới hoặc giữ lại cấu hình không còn phù hợp. Ưu tiên override tối thiểu và có lý do.

Một kết nối TLS thành công trong staging chỉ có ý nghĩa nếu staging dùng cùng loại truststore, provider, certificate chain và security properties với production.

## 12. Kiểm tra compiler target và bytecode

Compiler target cần được ghi riêng với runtime JDK. Với JDK 11 trở lên, ưu tiên --release thay vì ghép -source và -target, vì --release giới hạn cả ngôn ngữ, bytecode và Java SE API theo release đích.

Ví dụ compile code nhắm Java 26:

~~~powershell
javac --release 26 -d out .\src\Main.java
~~~

Ví dụ build bằng JDK 26 nhưng vẫn nhắm Java 25:

~~~powershell
javac --release 25 -d out .\src\Main.java
~~~

Trong Maven, kiểm tra cấu hình compiler plugin và maven.compiler.release. Trong Gradle, kiểm tra Java toolchain và options.release. Ghi rõ cấu hình cho main, test, generated source, integration test và các module con.

Nếu cần xác định bytecode target của một class:

~~~powershell
javap -verbose -classpath .\target\classes example.Main
~~~

Tìm major version trong output. Đối với multi-release JAR, kiểm tra cả base entries và các thư mục META-INF/versions/. Một JAR có thể chứa bytecode khác nhau cho các runtime khác nhau; phải phân tích với jdeps --multi-release phù hợp.

## 13. Xác định rủi ro theo mức ưu tiên

Không phải mọi khác biệt đều là blocker. Phân loại theo tác động và khả năng phát hiện:

| Mức | Dấu hiệu | Hành động |
|---|---|---|
| Critical | API đã bị loại bỏ, JVM không khởi động, agent/native binary không load, security policy chặn chức năng thiết yếu | Phải xử lý trước khi triển khai |
| High | JDK internal API, reflection phụ thuộc --add-opens, plugin chưa xác nhận hỗ trợ, dependency thiếu bản tương thích | Có kế hoạch nâng cấp và integration test |
| Medium | Deprecated API, option obsolete, warning từ compiler/runtime, khác biệt locale/timezone | Sửa hoặc ghi nhận quyết định và test hồi quy |
| Low | Công cụ phát triển hoặc IDE plugin không ảnh hưởng artifact/runtime | Cập nhật theo lịch công cụ |

Một dòng inventory chỉ được coi là đã kiểm tra khi có bằng chứng: tài liệu hỗ trợ, issue tracker/vendor statement, test trên đúng runtime hoặc kết quả phân tích tĩnh. Không đánh dấu “compatible” chỉ dựa trên suy đoán từ số version.

## 14. Quy trình kiểm kê trước và trong đợt nâng cấp

Thực hiện theo thứ tự sau để kết quả có thể so sánh:

1. **Chụp baseline:** lưu phiên bản JDK, vendor, build, OS/CPU, container digest và build tool trước khi thay đổi.
2. **Xác định runtime thật:** kiểm tra process bằng jcmd và môi trường deploy, không chỉ shell developer.
3. **Thu dependency graph:** lấy direct/transitive dependencies theo từng configuration.
4. **Thu plugin graph:** build plugins, compiler plugins, processors, agents và runtime plugins.
5. **Kiểm tra API:** chạy jdeps, jdeprscan và đối chiếu Removed APIs/Deprecated APIs.
6. **Thu JVM options:** command line, flags, system properties, environment variables và module access options.
7. **Kiểm tra native/security:** provider, TLS, truststore, JNI và HSM.
8. **Đối chiếu target:** xác nhận mọi component có version hỗ trợ JDK đích.
9. **Lập danh sách blocker:** gán người sở hữu, mức độ, giải pháp và test xác nhận.
10. **Chạy thử có kiểm soát:** build, test, start service, smoke test và quan sát log trên đúng runtime image.
11. **Chụp baseline mới:** lặp lại inventory sau nâng cấp và so sánh khác biệt.
12. **Phê duyệt triển khai:** chỉ chuyển bước khi blocker critical/high đã được xử lý hoặc có chấp thuận rủi ro rõ ràng.

Oracle Migration Guide cũng khuyến nghị thử chạy ứng dụng trên JDK mới trước, sau đó cập nhật thư viện/công cụ, compile lại khi cần và phân tích dependency bằng jdeps. Đây là quy trình lặp; một lần khởi động thành công không thay thế các bước kiểm tra còn lại.

## 15. Ma trận kiểm thử sau khi kiểm kê

Sau khi lập inventory, tạo test matrix gắn với thành phần có rủi ro:

| Khu vực | Kiểm thử cần có | Bằng chứng |
|---|---|---|
| Runtime startup | Khởi động bằng đúng JDK/vendor/image và JVM options | Startup log, process version |
| Build | Build sạch bằng wrapper/toolchain đã chốt | Build log, compiler release |
| Dependency | Unit/integration test với dependency đã resolve | Test report, dependency lock |
| Plugin/agent | Khởi động cùng agent và runtime plugin như production | Agent log, plugin load log |
| Reflection/module | Test proxy, DI, serializer, ORM và các package access | Không còn illegal-access workaround ngoài danh sách |
| Database | Kết nối, transaction, migration, pool và driver | Integration test |
| TLS/security | HTTPS, mTLS, truststore, provider và key operation | TLS test, provider inventory |
| Native | Load native library trên đúng OS/CPU | Native load test |
| Performance | Startup, heap, GC, throughput và latency | Benchmark có baseline |
| Container | Resource limit, signal, filesystem và health check | Container smoke test |
| Locale/time | Ngày giờ, số, tiền tệ, encoding và timezone | Regression fixtures |
| Observability | Log, metrics, tracing, JFR/APM | Agent/telemetry verification |

Với production-like test, giữ cùng JVM options, environment variables, resource limits, secret mounting method và startup command. Nếu test bỏ agent hoặc chạy ngoài container, hãy ghi rõ phần đó chưa được xác minh.

## 16. Mẫu inventory có thể dùng trong dự án

Mỗi thành phần nên có một dòng trong bảng kiểm kê hoặc SBOM liên kết với hồ sơ triển khai:

| Trường | Nội dung |
|---|---|
| Component | Tên JDK, thư viện, plugin, agent hoặc native binary |
| Type | Runtime, dependency, build plugin, processor, agent, provider, native |
| Current version | Version/build hiện tại |
| Target version | Version dự kiến sau nâng cấp |
| Source | Repository, image, vendor download hoặc hệ thống quản lý |
| Scope | Build, compile, test, runtime, production hoặc nhiều môi trường |
| Configuration | JVM option, module, profile, environment key hoặc plugin config |
| JDK support evidence | Tài liệu vendor, release note, test hoặc issue đã xác nhận |
| Risk | Critical/High/Medium/Low |
| Owner | Team hoặc người chịu trách nhiệm |
| Action | Upgrade, replace, remove, retain hoặc investigate |
| Validation | Lệnh/test/report chứng minh kết quả |
| Status | Not checked, Investigating, Blocked, Verified |

Một inventory hữu ích phải trả lời được: “Process production đang chạy JDK nào?”, “Dependency này được đưa vào từ đâu?”, “Plugin này chạy ở build hay runtime?”, “Option này được cấu hình ở file nào?” và “Bằng chứng nào xác nhận nó tương thích với JDK đích?”.

## 17. Chọn phiên bản JDK và support horizon

Không chọn JDK chỉ vì đó là số version mới nhất. Cần xét thời gian hỗ trợ của nhà cung cấp, nhịp phát hành, khả năng vá bảo mật, hỗ trợ framework/driver và chu kỳ nâng cấp của tổ chức.

Theo Oracle Java SE Support Roadmap cập nhật ngày 20-10-2026:

| Release | Phân loại theo roadmap Oracle | Mốc Premier Support của Oracle |
|---|---|---|
| JDK 25 | LTS | Đến tháng 9-2030 |
| JDK 26 | Non-LTS | Đến tháng 9-2026 |
| JDK 27 | Non-LTS | Đến tháng 3-2027 |

Tại thời điểm cuối tháng 11-2026, mốc Premier Support Oracle cho JDK 26 đã qua. Điều này không có nghĩa mọi bản phân phối JDK 26 đều ngừng cập nhật cùng ngày; lịch hỗ trợ, điều khoản license và patch cadence phụ thuộc nhà cung cấp JDK và hợp đồng của tổ chức.

Vì vậy, inventory phải ghi vendor + distribution + exact build + support channel, không chỉ ghi “Java 26”. Nếu mục tiêu là production dài hạn, đánh giá JDK LTS mà nhà cung cấp của tổ chức hỗ trợ; nếu cần tính năng ở feature release, phải chấp nhận chu kỳ nâng cấp ngắn và có lịch cập nhật rõ ràng.

Không dùng bảng Oracle làm lịch hỗ trợ chung cho Temurin, Corretto, Azul, Red Hat hoặc các vendor khác. Kiểm tra roadmap chính thức của đúng nhà cung cấp đang triển khai.

## 18. Các lỗi thường gặp khi kiểm kê

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| java --version đúng nhưng service chạy JDK khác | PATH/JAVA_HOME của shell khác service/container | Kiểm tra process bằng jcmd và startup definition |
| Maven/Gradle chạy JDK khác compiler | Toolchain hoặc compiler plugin chọn JDK riêng | Kiểm tra wrapper version, toolchain và compiler release |
| Dependency tree thiếu một số thư viện | Chỉ xem direct dependencies hoặc sai configuration | Xuất compile/runtime/test graph và dependency bắc cầu |
| Plugin không xuất hiện trong dependency tree | Plugin được resolve theo cơ chế build plugin riêng | Kiểm tra effective POM, Gradle plugin DSL, settings và extensions |
| Build thành công nhưng runtime lỗi class | Classpath/module path hoặc multi-release JAR khác | Kiểm tra artifact cuối, jdeps và runtime command |
| Chỉ chạy test không agent rồi kết luận đạt | Production bật javaagent/native agent | Chạy test với đúng agent/version |
| jdeps không báo reflection access | Phân tích tĩnh không thấy đường gọi động | Rà soát reflection, ServiceLoader và runtime logs |
| JAR chạy ở máy dev nhưng lỗi container | Thiếu module, native lib, CA cert hoặc OS dependency | Kiểm tra image thực tế và runtime image |
| JVM không khởi động sau nâng cấp | Flag cũ/không hợp lệ hoặc GC option đã bị loại bỏ | Đọc lỗi startup, đối chiếu java command của target JDK |
| Security provider khác giữa môi trường | Provider order, module, native library hoặc config khác nhau | Kiểm tra provider thực tế và security properties |
| Inventory ghi “JDK 26” nhưng không tái lập được | Thiếu vendor, build, image digest hoặc flags | Ghi exact build và nguồn cấu hình |
| Cấu hình có quá nhiều --add-opens | Workaround cũ không có owner hoặc thời hạn | Gắn từng option với dependency và kế hoạch loại bỏ |

## 19. Bài thực hành tổng hợp

Thực hiện trên một ứng dụng Java có Maven hoặc Gradle:

1. Ghi lại java --version, javac --version, java.home, vendor, VM version, OS và architecture.
2. Ghi lại JDK mà Maven/Gradle launcher sử dụng và compiler toolchain.
3. Chạy ứng dụng trong môi trường test; dùng jcmd -l tìm PID và thu VM.version, VM.command_line, VM.flags -all, VM.system_properties.
4. Xuất effective POM và dependency tree của Maven, hoặc dependency graph compile/runtime và build environment của Gradle.
5. Liệt kê build plugins, annotation processors, test engines, Java agents và runtime plugins.
6. Chạy jdeps --jdk-internals trên artifact và dependency quan trọng.
7. Chạy jdeprscan --for-removal và đối chiếu Removed APIs của JDK 26.
8. Tìm --add-opens, --add-exports, --patch-module, --enable-preview, incubator modules và native agent.
9. Kiểm tra security provider, TLS/truststore, JDBC driver và native libraries.
10. Ghi lại container image digest, resource limits, startup command và environment variables.
11. Điền inventory table, gán owner và xếp hạng risk.
12. Chạy smoke/integration/performance test bằng đúng JDK đích và cùng cấu hình production.
13. Lập báo cáo khác biệt trước/sau và xác nhận từng blocker có bằng chứng xử lý.

**Tiêu chí hoàn thành:** xác định được JDK thực tế của build và runtime; biết compiler release; xuất được dependency graph và plugin inventory; nhận diện annotation processor, agent, SPI và native library; tìm được JDK internal/deprecated/removed API; liệt kê JVM options và nguồn cấu hình; phân biệt preview/incubator với API final; kiểm tra container, TLS và provider; đánh giá support horizon của đúng vendor; tạo được bảng rủi ro có owner và test xác nhận.

## 20. Tài liệu tham khảo chính thức

- [Oracle JDK 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/index.html) — quy trình nâng cấp JDK, thay đổi đáng chú ý và các bước chuẩn bị migration.
- [Preparing for Migration – JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/preparing-migration.html) — chạy ứng dụng trên JDK mới, cập nhật thư viện, dùng --release và phân tích jdeps.
- [Removed APIs – JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/removed-apis.html) — API đã bị loại bỏ và API được đề xuất loại bỏ.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html) — thay đổi tương thích, tính năng mới, API và tùy chọn bị loại bỏ/deprecated.
- [The java Command – JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — launcher options, VM flags, preview và môi trường runtime.
- [The jcmd Command – JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html) — chẩn đoán JVM process, command line, VM flags và system properties.
- [The jdeps Command – JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html) — phân tích class/package/module dependency và JDK internal API.
- [The jdeprscan Command – JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeprscan.html) — quét việc sử dụng Java SE deprecated APIs.
- [Java SE Support Roadmap – Oracle](https://www.oracle.com/java/technologies/java-se-support-roadmap.html) — phân loại LTS/non-LTS và mốc hỗ trợ của Oracle; không thay thế roadmap của vendor khác.
- [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/) — dependency tree, resolve dependencies và resolve build plugins.
- [Gradle: Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html) — dependencies, dependencyInsight và build environment.

Kiểm kê hoàn chỉnh phải phản ánh runtime đang chạy, build graph đã resolve và cấu hình thực tế của môi trường triển khai. Hãy lưu version/build, nguồn cấu hình, dependency/plugin owner và bằng chứng kiểm thử cùng nhau; đó là cơ sở để nâng JDK có thể lặp lại, điều tra được và duy trì được sau khi phát hành.

