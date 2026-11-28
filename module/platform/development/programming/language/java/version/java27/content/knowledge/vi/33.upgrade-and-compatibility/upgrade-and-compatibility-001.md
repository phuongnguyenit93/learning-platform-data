# Lập danh mục JDK, thư viện, framework và công cụ cần tương thích khi nâng cấp lên Java 27

Nâng cấp một ứng dụng lên **Java 27** không chỉ là thay `JAVA_HOME` rồi biên dịch lại. Một hệ thống còn phụ thuộc vào JDK dùng để build, JDK thực thi, thư viện trực tiếp và bắc cầu, framework, plugin build, công cụ sinh mã, test runner, Java agent, native library, container image và hạ tầng CI/CD. Chỉ một thành phần chưa hỗ trợ Java 27 cũng có thể làm ứng dụng không khởi động, biên dịch thất bại, báo lỗi khi chạy hoặc thay đổi hành vi nghiệp vụ.

Bài thuộc chương **Nâng cấp và tương thích Java 27**, trong lộ trình **Java 27 và các kiến thức liên quan**. Chủ đề trực tiếp là **lập danh mục những thành phần phải kiểm tra khả năng tương thích**, chứ không phải tự động nâng mọi dependency lên bản mới nhất.

**Nguyên tắc phạm vi:** chỉ hướng dẫn và sử dụng API, công cụ, kỹ thuật còn phù hợp hiện nay; không giới thiệu cơ chế cũ đã bị loại bỏ như giải pháp nên áp dụng. Những cấu hình chưa được kiểm chứng phải được đánh dấu **chưa xác minh**, không được suy đoán là tương thích.

**Mốc tham chiếu:** Java 27 được phát hành ngày **15/09/2026**. Tài liệu chính thức dùng để xác minh thay đổi là **JDK 27 Release Notes** và **Oracle JDK Migration Guide, Release 27**. Tình trạng hỗ trợ của thư viện/framework thay đổi theo thời gian nên luôn kiểm tra release notes và compatibility matrix đúng phiên bản được sử dụng.

## 1. Vì sao cần danh mục trước khi sửa mã?

Giả sử một dịch vụ Java hiện chạy trên JDK 21. Đội phát triển đổi container base image sang JDK 27 và thấy:

- Mã ứng dụng biên dịch thành công nhưng plugin tạo mã nguồn không nhận dạng cú pháp/class-file mới.
- Test thất bại vì công cụ mock/bytecode instrumentation chưa nhận dạng **class-file major version 71**.
- IDE chạy được ứng dụng nhưng CI vẫn dùng JDK cũ để build.
- Một framework hỗ trợ Java 27 trong phiên bản mới, song dự án đang khóa phiên bản cũ.
- Một Java agent gắn vào JVM không hỗ trợ phiên bản runtime mới.
- Một thư viện native chỉ được đóng gói cho Linux x64 trong khi deployment cần Linux ARM64.
- Ứng dụng chạy được nhưng định dạng ngày giờ, TLS, mã hóa hoặc reflection khác trước.

Nếu không có danh mục, mỗi lỗi mới xuất hiện lại trở thành một bất ngờ. Một danh mục tốt giúp trả lời:

1. **Chúng ta đang dùng thành phần nào, phiên bản nào và ở đâu?**
2. **Nó tương thích với Java 27 theo bằng chứng nào?**
3. **Thành phần đó trực tiếp hay bắc cầu, do nhóm nào sở hữu?**
4. **Nếu không tương thích, phải nâng phiên bản, thay thế hay cấu hình lại?**
5. **Làm sao chứng minh đã kiểm tra và có thể rollback?**

### 1.1. Sơ đồ phạm vi kiểm kê

~~~text
                      Dịch vụ Java
                           |
         +-----------------+------------------+
         |                 |                  |
     Nguồn/mã          Build và CI         Runtime/deploy
         |                 |                  |
  Source/bytecode      Maven/Gradle         JDK/JRE/JVM flags
  Libraries            Wrapper/plugin       Container image
  Framework            Compiler/test        Agent/profiler
  Code generation      Toolchains           Native libs/OS
         |                 |                  |
         +-----------------+------------------+
                           |
                 Compatibility inventory
          ID / Version / Owner / Evidence / Risk
                           |
                Test matrix / Decision / Gate
~~~

Một danh mục phải chứa **thông tin hành động được**, không chỉ là một danh sách tên thư viện không có phiên bản, môi trường hoặc bằng chứng hỗ trợ.

## 2. Kết quả đầu ra mong muốn của một cuộc kiểm kê

Cuối bước kiểm kê, nhóm cần có tối thiểu:

- Danh sách **ứng dụng/module** và đường đi build/deploy của từng ứng dụng.
- Danh sách **JDK** đang dùng: build, unit test, integration test, runtime, developer/IDE, CI, container.
- Danh sách **framework và dependency**: trực tiếp, bắc cầu, có điều kiện, runtime-only, test-only.
- Danh sách **plugin/công cụ**: Maven/Gradle, compiler, annotation processor, code generator, linter, quality gate, coverage, bytecode transformer, packaging, deployment.
- Danh sách **native integration**: JNI, Foreign Function and Memory API, JNA hoặc thư viện hệ điều hành nếu có.
- Bằng chứng về **mức hỗ trợ**: release note, compatibility matrix, hướng dẫn vendor hoặc kết quả kiểm thử được gắn phiên bản.
- Trạng thái từng hạng mục: **đã xác nhận**, **đang thử nghiệm**, **cần cập nhật**, **bị chặn** hoặc **chưa biết**.
- Owner, mức ưu tiên, hành động tiếp theo, hạn xử lý và đường dẫn chứng cứ.
- Danh sách **những kiểm thử phải chạy** cùng kế hoạch rollback.

### 2.1. Không nhầm “đã liệt kê” với “đã tương thích”

| Trạng thái | Có nghĩa |
|---|---|
| Đã phát hiện | Biết thành phần đang tồn tại trong hệ thống |
| Đã xác định phiên bản | Biết đúng artifact, version và scope |
| Có tuyên bố hỗ trợ | Tìm thấy tài liệu vendor phù hợp |
| Đã kiểm thử | Chạy thành công workload phù hợp trên Java 27 |
| Đủ điều kiện triển khai | Đạt toàn bộ gate về build, test, vận hành, bảo mật, rollback |

Một dependency có thể xuất hiện trong danh mục nhưng **chưa hề được kiểm chứng**. Không đánh đồng số mục đã điền với tỷ lệ sẵn sàng nâng cấp.

## 3. Các chiều tương thích cần phân biệt

Khả năng tương thích không phải một thuộc tính duy nhất.

| Loại | Câu hỏi trọng tâm | Ví dụ |
|---|---|---|
| **Source compatibility** | Mã nguồn có biên dịch bằng compiler mục tiêu không? | Thay đổi API, từ khóa, lint |
| **Binary compatibility** | Bytecode có được runtime/linker đọc và liên kết không? | `UnsupportedClassVersionError`, `NoSuchMethodError` |
| **Behavioral compatibility** | Cùng mã có cùng hành vi nghiệp vụ quan trọng không? | Ngày giờ, locale, TLS, serialization |
| **Toolchain compatibility** | Build/test/plugin có chạy với JDK 27 không? | Maven/Gradle daemon, compiler, processor |
| **Framework/library compatibility** | Phiên bản đang khóa có được bảo đảm/test trên JDK 27 không? | Framework bootstrapping, reflection |
| **Operational compatibility** | Image, agent, container, monitoring có vận hành đúng không? | Startup flags, JFR agent, CDS |
| **Platform/ABI compatibility** | Native library có hỗ trợ OS/CPU/JDK và ABI không? | Linux x64 và Linux ARM64 |
| **Supportability** | Vendor có hỗ trợ chính thức khi phát sinh lỗi không? | Support matrix, maintenance policy |

Một ứng dụng có thể **build được nhưng runtime không chạy**, hoặc runtime chạy được nhưng không được vendor hỗ trợ. Cả hai tình huống phải được ghi riêng.

### 3.1. Chạy bytecode cũ trên Java 27 khác biên dịch lại cho Java 27

Có ít nhất ba chiến lược:

1. **Chỉ đổi runtime:** thử chạy artifact đã biên dịch cho JDK cũ trên JDK 27.
2. **Đổi compiler/toolchain nhưng giữ target cũ:** biên dịch bằng JDK 27 với `--release 21` nếu yêu cầu tiếp tục hỗ trợ Java 21.
3. **Đổi cả runtime và target lên 27:** biên dịch với `--release 27`, sinh bytecode Java 27 và chỉ chạy trên runtime hỗ trợ class-file version tương ứng.

Oracle Migration Guide khuyến nghị **thử chạy ứng dụng trên JDK mới trước khi nhất thiết phải biên dịch lại**, rồi cập nhật thư viện, compile và chạy `jdeps` theo vòng lặp. Điều này cho phép phân biệt lỗi runtime với lỗi compiler/build tool.

## 4. Đặt baseline và đích nâng cấp

Trước khi liệt kê dependency, hãy trả lời:

| Trường thông tin | Ví dụ minh họa |
|---|---|
| Ứng dụng | `billing-service` |
| Mã nguồn đang dùng | Commit/tag cụ thể |
| Runtime hiện tại | Java 21 (ví dụ, phải xác minh ở dự án thật) |
| Đích thử nghiệm | Java 27 |
| Target bytecode hiện tại | Java 17/21/25 hoặc giá trị thực tế |
| Target bytecode dự kiến | Giữ cũ hoặc chuyển sang 27 |
| JDK vendor/build hiện tại | Vendor + full version/build |
| JDK vendor/build đích | Vendor + full version/build |
| Các OS/architecture phải hỗ trợ | Linux x64, ARM64, Windows,… thực tế |
| Phạm vi rollout | Dev → CI → staging → canary → production |
| Người chịu trách nhiệm | Owner kỹ thuật xác định |
| Tiêu chí rollback | Mốc và điều kiện phục hồi đã thống nhất |

**Không giả định Java 21 là baseline của mọi hệ thống.** Đó chỉ là ví dụ. Một ứng dụng có thể đến từ Java 8/11/17/25/26, và số bước migration phụ thuộc điểm xuất phát.

### 4.1. Tách runtime JDK khỏi target bytecode

- **JDK chạy build tool**: phiên bản Java thực thi Maven/Gradle.
- **JDK compiler/toolchain**: phiên bản `javac` thực sự biên dịch.
- **`--release`/target bytecode**: phiên bản Java tối thiểu dự kiến cho output.
- **JDK chạy test**: runtime dùng cho unit/integration tests.
- **JDK production**: runtime của dịch vụ trong môi trường triển khai.

Năm giá trị này **có thể khác nhau**. Nếu không tách, một báo cáo “đã build bằng Java 27” chưa nói ứng dụng thực sự đang chạy hay test trên Java 27.

## 5. Kiểm kê JDK trên mọi môi trường

Mỗi môi trường cần ghi rõ JDK được chọn bằng cách nào.

| Nơi sử dụng | Cần thu thập | Rủi ro thường gặp |
|---|---|---|
| Developer workstation | JDK của shell, IDE, project SDK | `JAVA_HOME` khác IDE SDK |
| Build agent | JDK chạy Maven/Gradle, toolchain được resolve | CI vẫn dùng JDK cũ |
| Unit test runner | Runtime do test plugin chạy | Test fork dùng Java khác |
| Integration test | JDK của app under test và service phụ trợ | Test chỉ kiểm một phía |
| Staging | Base image, runtime build, JVM flags | Image/tag bị trôi |
| Production | Image digest, vendor, full JDK patch/build, CPU/OS | Không giống staging |
| Batch/scheduler | Java command, cron/job image, launcher | Lịch chạy chưa được cập nhật |
| Native-image pipeline nếu dùng | Công cụ tạo native image và runtime platform | Không đồng nhất với HotSpot JVM |

### 5.1. Các lệnh quan sát cơ bản

~~~shell
java -version
java --version
javac -version
java -XshowSettings:properties -version
~~~

Trong `java -XshowSettings:properties -version`, xem các trường `java.home`, `java.version`, `java.vendor`, `os.name` và `os.arch`. Đọc log đầu ra của command thay vì chỉ dựa vào biến môi trường.

Trong môi trường Windows, kiểm tra nơi shell tìm `java`:

~~~powershell
Get-Command java
Get-Command javac
$env:JAVA_HOME
~~~

Trên Linux/macOS:

~~~shell
command -v java
command -v javac
printf '%s\n' "$JAVA_HOME"
~~~

Các lệnh này chỉ để **quan sát**. Không sửa `PATH` hoặc `JAVA_HOME` trước khi đã ghi lại baseline.

### 5.2. Ghi full build, không chỉ “27”

Hai JDK đều hiển thị phiên bản feature `27` nhưng có thể khác vendor, bản cập nhật vá lỗi, build hoặc cấu hình crypto/provider. Ghi full output phiên bản, vendor và nguồn phân phối. Khi kiểm kê JDK sản xuất, version **không tự đủ** để biết chính sách hỗ trợ hay giấy phép sử dụng.

### 5.3. Quản lý nhiều JDK song song

Trong giai đoạn nâng cấp, có thể phải giữ cả baseline và target để chạy test chéo. Dùng cơ chế JDK/toolchain pinning của hệ thống build, container image digest hoặc môi trường runner cụ thể.

Đừng thay JDK toàn máy và quên ghi lại cách rollback. **Mục tiêu là tái lập được**, không phải ép mọi developer dùng một cài đặt thủ công khó kiểm chứng.

## 6. Kiểm kê compiler target và tương thích class-file

Java 27 sử dụng **class-file major version 71** cho bytecode thông thường được tạo ra ở mức tương ứng Java 27. Những runtime cũ hơn không đọc được class-file mới này.

| Java release | Class-file major version |
|---|---:|
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |
| Java 26 | 70 |
| **Java 27** | **71** |

Khi runtime cũ gặp class có major version không hỗ trợ, thường xuất hiện lỗi:

~~~text
java.lang.UnsupportedClassVersionError:
... has been compiled by a more recent version of the Java Runtime
~~~

Không được kết luận “Java 27 không tương thích” khi lỗi thật ra đến từ **cách build target**: có thể build dùng `--release 27` nhưng deploy vẫn chạy JDK 21.

### 6.1. Dùng --release thay vì chỉ source/target

~~~shell
javac --release 27 -encoding UTF-8 -d out src/Main.java
~~~

`--release` điều chỉnh ngôn ngữ, class-file version và **API nền tảng Java SE có thể tham chiếu** cho release mục tiêu. Nếu dự án phải hỗ trợ Java 21 khi compile bằng JDK 27:

~~~shell
javac --release 21 -encoding UTF-8 -d out src/Main.java
~~~

`--release 21` không đảm bảo tất cả third-party JAR cũng tương thích Java 21; phải kiểm tra bytecode và API của dependency riêng.

Tránh thiết lập riêng lẻ `-source`/`-target` như một giải pháp kiểm tra API đầy đủ của bản Java cũ. Theo tài liệu Maven Compiler, `--release` là cơ chế nên dùng khi muốn build đúng API của release đích.

### 6.2. Kiểm tra output thực tế

~~~shell
javap -verbose -classpath out Main
~~~

Trong output, tìm dòng:

~~~text
major version: 71
~~~

Đây là giá trị minh họa cho class được build với Java 27. Một class trong thư viện có thể có major thấp hơn; **không phải toàn bộ classpath phải được recompile lên major 71** để chạy trên JDK 27.

### 6.3. Multi-release JAR

Một JAR có thể chứa các class dưới `META-INF/versions/…` để JVM chọn phần phù hợp theo runtime. Khi kiểm kê, cần nhận biết loại artifact này; kiểm tra **đường code thực sự được chọn trên JDK 27**, không chỉ class ở root JAR.

`jdeps` có tùy chọn `--multi-release` để phân tích đúng phiên bản mục tiêu. Với thư viện đã có multi-release JAR, hãy đọc metadata/manifest và hướng dẫn vendor trước khi thay đổi cách đóng gói.

## 7. Phân loại dependency theo vai trò

Một ứng dụng có thể dùng hàng trăm hoặc hàng nghìn dependency nếu tính cả transitive dependencies. Không chỉ liệt kê những thư viện developer nhớ tên.

| Nhóm | Ví dụ khái niệm | Vì sao cần kiểm tra |
|---|---|---|
| Runtime library | JSON, logging, HTTP, database client | API, reflection, TLS, class loading |
| Framework | Web, DI, persistence, messaging | Bootstrapping, module/reflection và support matrix |
| Direct dependency | Khai báo trực tiếp trong build | Được nhóm chủ động chọn phiên bản |
| Transitive dependency | Được kéo theo từ dependency khác | Có thể chứa bytecode, CVE hoặc API không tương thích |
| Build-time dependency | Code generator, compiler plugin | Phải chạy trên build JDK |
| Annotation processor | Lombok, MapStruct processor, Dagger,… nếu thực sự dùng | Tương tác compiler/JDK internals |
| Test-only dependency | JUnit, Mockito, Testcontainers,… nếu thực sự dùng | Test runner, bytecode agent, container |
| Runtime agent | APM, instrumentation, coverage agent | Hook vào JVM và class-file version |
| Native dependency | JNI/JNA/FFM, thư viện C/C++ | OS/architecture, ABI, native access |
| Packaging/deployment | jlink, jpackage, Docker plugin, native-image | Tạo artifact và runtime image |
| Operability/security | TLS provider, metrics, logging appender | Startup, security, timezone, behavior |

**Ví dụ tên công cụ trong bài không đồng nghĩa tất cả dự án đều sử dụng chúng.** Chỉ đưa vào danh mục của hệ thống những thành phần được phát hiện từ build/deploy/runtime hoặc được owner xác nhận.

### 7.1. Direct và transitive có owner khác nhau

Một nhóm chỉ thay trực tiếp `framework-starter` nhưng starter đó kéo theo parser bytecode cũ có thể vẫn lỗi trên Java 27. Cần ghi:

- Đường dependency nào mang nó vào.
- Phiên bản **được resolve thực tế** sau dependency management, BOM, constraints và conflict resolution.
- Scope/classifier/variant đang được dùng.
- Version mới phù hợp được framework/vendor quản lý.
- Owner của hành động nâng hoặc exclude dependency.

Không nâng riêng một transitive dependency **ngược với BOM** nếu chưa kiểm tra tương thích của toàn bộ bộ thư viện.

## 8. Thu thập dependency từ Maven

Trong dự án Maven, có thể bắt đầu:

~~~shell
mvn --version
mvn dependency:tree
~~~

Đây là lệnh để **người học chạy trong dự án Maven của họ**; không phải bằng chứng rằng mọi dự án dùng Maven. Khi cần tập trung vào runtime scope, cần xem cấu hình và classpath do Maven resolve; cây mặc định có thể chứa nhiều loại dependency.

Để hiển thị dependency theo scope/định dạng:

~~~shell
mvn dependency:tree -Dscope=runtime
mvn dependency:tree -Dverbose
~~~

Việc hỗ trợ/ý nghĩa một số option phụ thuộc phiên bản **Maven Dependency Plugin**. Nếu option không khả dụng, xem `mvn help:describe` hoặc tài liệu plugin đúng phiên bản.

### 8.1. Phân biệt POM khai báo và phiên bản thực sự dùng

~~~xml
<dependencyManagement>
    <!-- BOM có thể kiểm soát version của nhiều artifacts. -->
</dependencyManagement>

<dependencies>
    <!-- Có dependency không tự khai báo version. -->
</dependencies>
~~~

Đoạn XML này chỉ là sơ đồ khái niệm, **không phải một POM hoàn chỉnh**.

Một dependency không khai báo version trong `pom.xml` có thể nhận version từ parent POM hoặc BOM. Kiểm kê phải ghi **resolved version**, không ghi `unknown` chỉ vì source file không chứa số phiên bản.

Nếu dự án dùng nhiều profile Maven, cần quét theo **profile thực sự được kích hoạt** trong CI và production build.

### 8.2. Maven build JDK và compiler target

~~~shell
mvn --version
~~~

Kiểm tra JDK đang chạy Maven. Sau đó kiểm tra compiler plugin/property:

~~~xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
</properties>
~~~

Đoạn này cần nằm trong `pom.xml` thực và plugin tương thích, không phải một file riêng. Cùng một build có thể **chạy Maven trên JDK 27 nhưng dùng Maven Toolchains để biên dịch bằng một JDK khác**. Hãy ghi cả hai.

### 8.3. Không cập nhật mọi dependency bừa bãi

Một lệnh tự động đề xuất phiên bản mới chỉ là **nguồn gợi ý**, không phải bằng chứng tương thích. Với framework quản lý BOM, việc cập nhật đại trà có thể phá ràng buộc phiên bản.

Quy trình đúng:

1. Xác định artifact và resolved version.
2. Tra compatibility/release note của chủ dự án.
3. Chọn phiên bản cùng nhánh được vendor hỗ trợ.
4. Kiểm tra dependency graph sau thay đổi.
5. Chạy test trên JDK 27 và runtime mục tiêu.

## 9. Thu thập dependency và toolchain từ Gradle

Trong dự án Gradle:

~~~shell
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency some-library --configuration runtimeClasspath
~~~

Tên configuration `runtimeClasspath` phổ biến cho Java/JVM plugin; một dự án Android hoặc Kotlin Multiplatform có thể có configuration khác. `dependencyInsight` cần tên module thực tế thay cho `some-library`.

Trên Windows, wrapper có thể là `gradlew.bat`. Ưu tiên wrapper được commit vào dự án để dùng đúng phiên bản Gradle đã được kiểm soát.

### 9.1. Java 27 và Gradle: kiểm tra daemon lẫn toolchain

Theo **Gradle Compatibility Matrix**, Java 27 được hỗ trợ để chạy Gradle và dùng toolchains từ **Gradle 9.8.0** trở đi; Gradle 9.8.0 được phát hành ngày **24/09/2026**. Đây là dữ kiện được xác nhận từ tài liệu chính thức, không phải suy đoán.

Ví dụ Gradle Kotlin DSL dùng toolchain:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}
~~~

Toolchain trên quyết định JDK được chọn cho các task Java hỗ trợ toolchains, **không tự chứng minh mọi plugin Gradle trong dự án đã hỗ trợ Java 27**. Ngay cả release notes Gradle 9.8.0 cũng lưu ý một số third-party tools có thể chưa tương thích Java 27.

Cần ghi riêng:

- Gradle wrapper version.
- JDK chạy Gradle daemon.
- JDK/toolchain biên dịch source.
- JDK chạy test/worker nếu cấu hình riêng.
- Phiên bản và support của mỗi Gradle plugin.
- Phiên bản Kotlin/Groovy/Android plugin nếu dự án dùng.

### 9.2. Không kết luận mọi phiên bản Gradle cũ hỗ trợ JDK 27

Một bản Gradle cũ có thể dùng toolchain của JDK mới hơn ở một mức độ nào đó, nhưng **không nên gắn nhãn SUPPORTED khi compatibility matrix không xác nhận**. Với Java 27, yêu cầu tối thiểu có bằng chứng chính thức là Gradle 9.8.0 cho việc chạy daemon và toolchains. Đối với phiên bản plugin cụ thể, cần đối chiếu release notes của plugin.

## 10. Kiểm kê framework và BOM

Framework thường có **phiên bản nền tảng được hỗ trợ**, không chỉ một dependency độc lập. Danh mục phải phản ánh tổ hợp framework, runtime và các module liên quan.

Những họ framework có thể có trong dự án (chỉ ghi khi thực sự dùng):

- Spring Framework và Spring Boot.
- Quarkus.
- Micronaut.
- Jakarta EE runtime/application server.
- Helidon, Vert.x và các framework JVM tương đương.
- Hibernate ORM, JPA provider, migration framework.
- gRPC, Netty và thư viện HTTP/network.
- Apache Camel, Kafka client hoặc các thư viện messaging.

Đừng ghi chung “Spring hỗ trợ Java 27” mà không có **dòng sản phẩm và phiên bản cụ thể**. Chẳng hạn Spring Framework X và Spring Boot Y có thể có ma trận hỗ trợ và BOM khác nhau.

### 10.1. Những câu hỏi phải trả lời cho mỗi framework

1. **Phiên bản đang chạy** là gì, được quản lý bởi BOM nào?
2. **Minimum Java** và **maximum tested Java** được vendor công bố là bao nhiêu?
3. Nó hỗ trợ **chạy trên Java 27**, hay còn hỗ trợ **biên dịch target 27**?
4. Cần phiên bản application server, servlet API hoặc persistence provider nào?
5. Có thay đổi API, namespace, bytecode generation, reflection hoặc proxy generation không?
6. Những starter/module phụ có đi cùng nhánh phiên bản được hỗ trợ không?
7. Có yêu cầu native-image/JNI hay công cụ không nằm trong core framework không?
8. Support policy còn hiệu lực cho phiên bản hiện tại không?

### 10.2. Framework “chạy được” chưa chắc được support

Một test khởi động thành công là bằng chứng **smoke test**, nhưng không thay thế tuyên bố hỗ trợ của vendor hoặc test end-to-end cho workload thực. Ngược lại, vendor có thể tuyên bố support nhưng dự án vẫn lỗi do cấu hình hoặc plugin khác.

Ghi cả **vendor support evidence** và **local test result** ở những trường riêng, không chọn một trong hai.

## 11. Kiểm kê công cụ compile, sinh mã và xử lý bytecode

Một nhóm rất dễ bị bỏ sót là công cụ can thiệp trực tiếp vào compiler hoặc class-file.

| Nhóm công cụ | Ví dụ nếu dự án dùng | Điều cần kiểm tra |
|---|---|---|
| Compiler | `javac`, compiler plugin, Kotlin/Scala/Groovy compiler | Có nhận Java 27 source/target và runtime build không? |
| Annotation processor | Lombok, MapStruct processor, Dagger processor | Có hỗ trợ JDK compiler/version hiện tại không? |
| Code generator | OpenAPI Generator, protobuf/Avro generator, jOOQ codegen | Tool dùng JDK nào, generated source có hợp lệ không? |
| Bytecode reader/writer | ASM, Byte Buddy, Javassist | Có hiểu class-file major 71 và attributes liên quan không? |
| Coverage | JaCoCo và agent tương đương | Có instrument class Java 27 không? |
| Mocking | Mockito và bytecode mock maker | Có tạo class/proxy hợp lệ không? |
| Static analysis | Checkstyle, PMD, SpotBugs, Error Prone | Parser/compiler integration có nhận language/class-file mới không? |
| Packaging | Maven Shade, Gradle Shadow, Spring Boot repackage | Có đọc/ghi JAR metadata và bytecode đúng không? |
| Framework enhancer | Hibernate enhancer, dependency injection proxy tools | Có làm việc với Java 27 runtime/bytecode không? |

**Tên công cụ và phiên bản sản phẩm không được tự động coi là đã hỗ trợ Java 27.** Các dự án thường cập nhật hỗ trợ class-file riêng từng release.

### 11.1. Nhiều nguồn bytecode khác nhau

Một ứng dụng có thể vừa biên dịch mã Java ở target 27, vừa:

- Compile Kotlin sang JVM bytecode target thấp hơn.
- Sinh class bằng proxy runtime.
- Instrument bytecode khi chạy test.
- Rewrite class bằng agent hoặc plugin.
- Đóng gói multi-release JAR.
- Tải class động từ plugin khác.

Một build thành công **không đủ** để xác nhận từng đường đi tạo/đọc bytecode đã hỗ trợ major version 71.

### 11.2. Kiểm tra annotation processing

Processor chạy trong ngữ cảnh build/compiler, đôi khi truy cập API bên trong compiler. Một processor cũ có thể hỏng **trước khi ứng dụng được biên dịch**.

Trong danh mục ghi:

- Processor artifact/version.
- Compiler JDK.
- Version plugin khởi chạy processor.
- Support matrix/release notes.
- Có đang dùng JDK internal API hoặc reflective access không.
- Hướng cập nhật và test biên dịch mã sinh ra.

Không giải quyết bằng cách thêm hàng loạt `--add-opens` vĩnh viễn nếu có một bản processor hiện hành hỗ trợ Java 27.
## 12. Kiểm kê công cụ test và kiểm thử tích hợp

Test infrastructure có thể thất bại trên JDK 27 dù production code chạy đúng. Cần tách **công cụ chạy test** khỏi **thư viện được test**.

| Loại | Ví dụ nếu có | Điểm tương thích |
|---|---|---|
| Unit test engine | JUnit Jupiter, TestNG | Runner/engine chạy với JDK nào? |
| Test launcher | Maven Surefire/Failsafe, Gradle Test task | Fork JVM có dùng Java 27 không? |
| Mock/spy | Mockito, Byte Buddy | Tạo/instrument class với major 71? |
| Coverage | JaCoCo, agent coverage | Nhận class-file và JVM runtime? |
| Integration test | Testcontainers, embedded broker/database | Docker/OS/container, client/protocol compatibility |
| Contract test | Pact, Spring Cloud Contract, công cụ tương đương | Plugin, generator, runtime và schema |
| HTTP/UI test | REST client, Selenium/Playwright nếu dùng | JDK client, browser/driver hoặc API |
| Load test | Gatling, JMeter, k6 nếu dùng | JVM của runner (nếu có), plugin, TLS và driver |
| Mutation test | PIT hoặc tương đương | Instrumentation/bytecode compatibility |

Không gán một nhãn `PASS` chung cho tất cả chỉ vì `mvn test` thành công trong môi trường developer. Hãy xem riêng những test profile chạy trong CI, integration test có dịch vụ ngoài và các runner thật.

### 12.1. Kiểm tra JVM của test process

Một build có thể có:

- JDK 27 chạy Maven/Gradle.
- JDK 21 được toolchain chỉ định để compile.
- Một Java executable được test plugin dùng riêng để fork test.
- Container JVM 27 cho application under test.
- JVM 17 chạy một tool kiểm thử hoặc mock server khác.

Cần ghi **từng runtime có ảnh hưởng đến kết luận**. Nếu test fork vẫn chạy Java 21 thì kết quả `PASS` chưa kiểm chứng hành vi Java 27.

### 12.2. Phân biệt kết quả ba tầng

1. **Compile-time test:** test source biên dịch được.
2. **Runtime test:** unit test thực sự chạy trên Java 27.
3. **Integration/e2e test:** ứng dụng cùng dependency thực tế tương tác đúng với database, queue, TLS, external services trong môi trường gần production.

Mỗi tầng phải có command/log/build ID riêng; không gộp các kết quả khác nhau vào một ô chung.

## 13. Kiểm kê IDE, developer tooling và script hỗ trợ

Toolchain không chỉ sống trong CI. Khi nâng Java 27, đội phát triển còn dùng:

- IntelliJ IDEA, Eclipse, Apache NetBeans hoặc IDE thực tế.
- Java Language Server, debugger, profiler và editor integration.
- Maven/Gradle integration trong IDE.
- Code formatters, import organizers, static analysis và source generation.
- SDK manager/JDK discovery và IDE project SDK.
- Shell script, PowerShell, launcher, file `.env`, Docker Compose.
- Git hooks và công cụ pre-commit.
- Các tool chạy Java độc lập, đôi khi được gọi từ script mà không xuất hiện trong dependency graph.

### 13.1. IDE có thể chạy bằng một JDK nhưng build bằng JDK khác

Ví dụ cần ghi đồng thời:

| Thành phần | JDK đang dùng |
|---|---|
| IDE runtime | JDK do IDE đóng gói hoặc cấu hình |
| Project SDK | JDK theo project |
| Maven/Gradle importer | JDK theo cấu hình IDE |
| Gradle daemon | JVM chạy Gradle |
| Compiler toolchain | Java 27 hoặc version khác |
| Test runner | JVM thực tế khi chạy test |

IDE có thể nhận syntax Java 27 nhưng Gradle plugin kèm theo chưa hỗ trợ. Ngược lại, build CLI có thể thành công còn IDE báo lỗi parser chưa nhận syntax mới. Cả hai là hạng mục kiểm kê khác nhau.

### 13.2. Ghi bằng chứng đúng phiên bản IDE/plugin

Không ghi “IDE đã cập nhật” mà không có tên sản phẩm, phiên bản, plugin và thời điểm kiểm chứng. Một extension hoặc code style tool có thể cập nhật độc lập với IDE.

**Không suy diễn từ hỗ trợ Java source sang hỗ trợ tất cả công cụ phân tích source**. Linter và formatter thường có vòng đời parser riêng.

## 14. Quét API nội bộ, deprecated API và module dependencies của JDK

Ngoài dependency của bên thứ ba, ứng dụng có thể phụ thuộc vào API JDK nội bộ hoặc API bị deprecate/removed.

Các công cụ hiện hành trong JDK hữu ích cho kiểm tra gồm:

- **`jdeps`**: phân tích phụ thuộc class/module; có chế độ phát hiện JDK internal API.
- **`jdeprscan`**: phát hiện việc tham chiếu tới API Java SE bị deprecated, theo phạm vi công cụ hỗ trợ.
- **`javap`**: xem class-file version và cấu trúc class.
- **`jar`**: xem metadata JAR, module descriptor, manifest.
- **`java --version`**: xác nhận runtime đích.

### 14.1. Phát hiện JDK internal API

Ví dụ với JAR ứng dụng bình thường và dependency JAR nằm trong thư mục `lib`:

~~~shell
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
~~~

Đây là **mẫu lệnh cần điều chỉnh cho bố cục artifact thật**. Nếu ứng dụng dùng module path, có nhiều JAR/module hoặc dependency nằm trong fat JAR lồng nhau, phải xác định lại cách cung cấp classpath/modulepath cho công cụ.

`jdeps` là static analysis. Nó **không thể phát hiện đầy đủ** mọi class/hàm được tạo hoặc tải thông qua reflection, service loader, native, bytecode generation hoặc plugin runtime.

### 14.2. Kiểm tra deprecated Java SE APIs

~~~shell
jdeprscan --release 27 --class-path "lib/*" app.jar
~~~

Thao tác này giúp tạo danh sách API có thể cần thay thế theo chính sách tương lai. **Deprecated không đồng nghĩa removed**: không tự báo tất cả warning là blocker. Ghi mức độ deprecation, có `forRemoval` hay không, phạm vi code và kế hoạch xử lý.

Đối với những API đã **bị xóa** trước Java 27, ứng dụng có thể lỗi khi compile hoặc link; cần tra JDK 27 Migration Guide và release notes theo từng bước từ baseline lên target.

### 14.3. Phân tích multi-release JAR

~~~shell
jdeps --multi-release 27 --jdk-internals --class-path "lib/*" app.jar
~~~

Lựa chọn `--multi-release 27` hữu ích khi một JAR chứa class ở `META-INF/versions/...`. Nhớ kiểm tra **phiên bản class được chọn khi thực thi trên JDK 27**, không chỉ class gốc.

### 14.4. Không dừng ở kết quả quét tĩnh

Một thư viện có thể dùng reflection vào package đóng của JDK hoặc instrument bytecode runtime. `jdeps` có thể không nhận diện đường đi đó. Bổ sung:

- Log runtime khi startup/test trên JDK 27.
- Test các code path ít chạy.
- Review agent, mocker, proxy framework và annotation processor.
- Soát những flag `--add-opens`, `--add-exports` hiện có.
- Xem hướng dẫn nâng cấp của vendor có nhắc đến strong encapsulation hay không.

## 15. Kiểm kê JVM options và thay đổi hành vi

Nhiều vấn đề migration đến từ **cấu hình runtime**, không phải thư viện.

### 15.1. Nhóm flags nên kiểm kê

| Nhóm | Những gì cần lưu |
|---|---|
| Memory | `-Xms`, `-Xmx`, heap/non-heap/native memory settings |
| GC | Collector, tuning flags, GC logging |
| Module encapsulation | `--add-opens`, `--add-exports`, `--add-reads` |
| Native access | `--enable-native-access`, `--illegal-native-access` |
| Agents | `-javaagent`, `-agentlib`, `-agentpath` |
| Preview | `--enable-preview` nếu thực sự dùng preview features |
| TLS/security | Keystore/truststore, security properties, providers |
| Locale/timezone | `user.timezone`, locale/charset và chính sách dữ liệu |
| Observability | JFR, unified logging, diagnostics |
| Startup | Class path/module path, main module/class, argument files |

Không sao chép toàn bộ JVM flags cũ vào Java 27 rồi coi đó là thiết lập chuẩn. Một số flag có thể bị bỏ, đổi mặc định hoặc không còn phù hợp. Kiểm tra **JDK 27 Release Notes** và **Migration Guide** để xác minh từng flag quan trọng.

### 15.2. Phát hiện “chạy được nhưng vẫn rủi ro”

Ví dụ startup log có warning về native access hoặc truy cập module, nhưng ứng dụng vẫn khởi động. Warning là **bằng chứng cần đánh giá**, không phải `PASS` để bỏ qua vô thời hạn.

Tương tự, việc thêm `--add-opens=java.base/...=ALL-UNNAMED` có thể tạm giải quyết lỗi reflection, nhưng không xác nhận framework/library đã hỗ trợ chính thức JDK 27. Cần tìm bản tương thích để giảm dần quyền mở rộng không cần thiết.

### 15.3. Native access trong Java hiện đại

Khi ứng dụng gọi restricted methods của FFM/JNI hoặc load native library, có thể cần quyền `--enable-native-access=<module>` hay `ALL-UNNAMED`. Để kiểm tra phụ thuộc quyền chưa khai báo, có thể nghiên cứu chạy test với chế độ:

~~~shell
java --illegal-native-access=deny -jar app.jar
~~~

**Đây là lệnh kiểm tra có thể làm ứng dụng thất bại nếu còn illegal native access**, không nên áp dụng thẳng vào production chưa được thử nghiệm. Khi cần native access hợp lệ, phải cấp cho module được phép.

### 15.4. Final-field mutation và reflective access

JDK 27 Migration Guide có nội dung về **những hạn chế đối với việc sửa final field**, bên cạnh các thay đổi quyền truy cập và native code. Khi ứng dụng dùng serializer, ORM, dependency injection hoặc reflection phức tạp, cần đọc **hướng dẫn và warning thực tế của JDK 27**. Không tự suy đoán một cách khắc phục chung chỉ bằng việc mở module.

Kiểm kê thành phần nào cần reflective access và mục đích cụ thể; tìm đường cập nhật library trước khi thêm flag cấp quyền rộng.

## 16. Kiểm kê hành vi security, locale và dữ liệu

Ngay cả khi build/test smoke thành công, các thay đổi behavior vẫn có thể ảnh hưởng dữ liệu hoặc giao tiếp với hệ thống khác.

| Miền | Rủi ro cần kiểm tra |
|---|---|
| TLS/PKI | Protocol/cipher/provider/truststore thay đổi |
| Certificate | Chuỗi chứng chỉ, thuật toán chữ ký, expiry |
| Locale/CLDR | Format số, ngày tháng, tên vùng |
| Timezone | Cơ sở dữ liệu múi giờ thay đổi |
| Charset | Encoding file/console, giả định về default charset |
| Date/time | Serialization, parse và format có theo locale/timezone? |
| JDBC/data types | Driver và mapping timestamp/decimal |
| Serialization | JSON/XML/Protobuf/Java serialization nếu hệ thống dùng |
| Reflection | Private member access, proxy, module boundaries |
| ServiceLoader | Module service provider resolution |
| Logging | Timestamp, encoder, async appender |
| Permissions | Native access, security providers, file/network permissions |

Ví dụ: hai hệ thống dùng cùng mã nhưng cài các bản timezone data khác nhau có thể cho kết quả chuyển đổi lịch sử/thời gian địa phương khác nhau. Không coi đó chỉ là “lỗi formatter” nếu nghiệp vụ thực sự lưu dữ liệu mốc thời gian.

### 16.1. Phương pháp kiểm chứng behavior

- Lưu **golden test cases** từ baseline cho những định dạng có yêu cầu ổn định.
- Chạy lại dưới JDK 27 với cùng input và cấu hình timezone/locale tường minh.
- Phân biệt khác biệt **hợp lệ theo chuẩn mới** với **regression nghiệp vụ**.
- Xem upstream release notes trước khi sửa test cho qua.

Không sửa kỳ vọng của test chỉ để nó PASS khi chưa đánh giá tác động của thay đổi.

## 17. Kiểm kê native libraries, JNI, FFM và kiến trúc máy

Một phụ thuộc native có nhiều chiều mà một tọa độ Maven không mô tả hết:

| Trường cần ghi | Ví dụ nội dung |
|---|---|
| Java wrapper artifact | Tên/version thư viện Java nếu có |
| Native binary | File `.so`, `.dylib`, `.dll` |
| Nguồn tải | Package, container, vendor release |
| OS/architecture | Linux x64/ARM64, Windows x64, macOS ARM64,… |
| ABI / libc | glibc/musl hoặc yêu cầu runtime thực tế |
| Cách load | JNI, JNA, FFM, `System.loadLibrary` |
| Native permission | Module nào cần native access |
| Runtime test | Tải được thư viện, gọi được API, shutdown an toàn |
| Ownership | Ai phát hành và cập nhật native binary |

Một bản Java wrapper “hỗ trợ Java 27” **không đồng nghĩa** mọi native binary đi kèm đều hỗ trợ OS/CPU của production.

### 17.1. Bối cảnh FFM và JNI

- **FFM API** là API hiện hành, ổn định từ Java 22; dùng các thành phần thuộc `java.lang.foreign`.
- **JNI** vẫn được hỗ trợ nhưng những thao tác native cần tuân theo cơ chế quyền của JDK hiện đại.
- Native code có thể gây crash JVM hoặc memory corruption nếu sai con trỏ/ABI.
- Khi nâng JDK, kiểm tra native access warning, callback, direct buffer, library loading và cleanup.

Đừng đề xuất thay toàn bộ JNI bằng FFM chỉ để nâng Java 27 khi code JNI hiện tại vẫn được hỗ trợ và đã kiểm chứng. Việc đổi binding là **một dự án riêng** cần đánh giá chi phí/rủi ro.

## 18. Kiểm kê CI/CD, container, runtime image và môi trường deploy

Một hệ thống nâng thành công phải đi từ source đến artifact production.

~~~text
Source → Build image/runner → Compile & Test → Artifact
                                    |
                                    v
                              Docker/OCI image
                                    |
                           Staging → Canary → Prod
                                    |
                              JDK runtime thực
~~~

### 18.1. Những điểm phải ghi vào danh mục

- GitHub Actions, GitLab CI, Jenkins, Azure Pipelines hoặc hệ thống CI thực tế.
- Runner OS/architecture/JDK provisioning.
- Maven/Gradle wrapper version và build cache.
- Dockerfile multi-stage: JDK ở **build stage** và JRE/JDK ở **runtime stage**.
- Artifact repository, container registry và image digest.
- Docker/Kubernetes manifests, Helm values, entrypoint/startup flags.
- `jlink` runtime image, `jpackage` app image hoặc native executable nếu có.
- JVM agent APM, monitoring sidecar hoặc script startup.
- Scanner SBOM/CVE/signature của dependency và image.
- Tác vụ batch và scheduled job nằm ngoài đường deploy HTTP chính.

### 18.2. Docker multi-stage có thể dùng hai Java khác nhau

~~~dockerfile
# Minh họa cấu trúc, KHÔNG phải Dockerfile để build ngay:
FROM <trusted-jdk-27-build-image> AS build
# ... build artifact tại đây ...

FROM <trusted-jdk-27-runtime-image>
# ... copy đúng artifact và cấu hình runtime ...
~~~

Các chuỗi trong dấu ngoặc là placeholder, không phải tên image thật. Khi triển khai, dùng image vendor đáng tin cậy có Java 27, phiên bản/kiến trúc phù hợp và **pin digest** nếu cần build tái lập. Không chỉ dựa vào tag dễ thay đổi.

### 18.3. Application runtime khác tool runtime

Một pipeline CI có thể dùng JDK 27 để build nhưng dùng một tool tạo SBOM chạy bằng JDK khác; điều này không nhất thiết sai. Quan trọng là phải biết **tool nào chạy trên JDK nào** và tool có hỗ trợ runtime/bytecode của đầu vào hay không.

Nếu container image không cài đủ `javac`, `jdeps` hoặc `jcmd`, không nên ép quét từ production runtime. Thực hiện static analysis và diagnostics ở build/test environment phù hợp, còn production runtime có thể giữ tối giản.

## 19. SBOM, lockfile và tính đầy đủ của danh mục

**Software Bill of Materials (SBOM)** giúp liệt kê thành phần phần mềm, phiên bản và quan hệ phụ thuộc của artifact. SBOM là nguồn đầu vào mạnh cho danh mục nhưng **không đủ một mình** để chứng minh Java 27 compatibility.

Cần phân biệt:

- **Declared dependencies:** dependency khai báo trong source/build file.
- **Resolved dependencies:** artifact thực được lấy sau BOM/constraints/conflict resolution.
- **Packaged dependencies:** thư viện thực nằm trong JAR/image.
- **Loaded dependencies:** code được runtime thực sự load, có thể còn có plugin/agent/native binary.
- **Transitive dependencies:** những dependency đến từ dependency khác.

Một SBOM do build tạo có thể thiếu tài nguyên tải động hoặc system libraries. Ngược lại, một SBOM image có thể chứa package OS không liên quan đến Java bytecode nhưng lại quan trọng với native bindings.

### 19.1. Khóa và truy nguyên artifact

Danh mục tốt cần gắn với:

- GAV coordinates (Maven) hoặc module/variant tương ứng (Gradle).
- Exact version hoặc hash/digest.
- Repository/registry và nguồn download.
- License/maintenance status khi cần.
- Checksum hoặc signature policy.
- Mối quan hệ direct/transitive và component nào kéo dependency vào.

Đừng chỉ ghi “thư viện X phiên bản latest”: từ `latest` không thể tái lập một build.

## 20. Mẫu schema cho danh mục tương thích

Có thể lưu danh mục dưới dạng spreadsheet, CSV, YAML, issue tracker hoặc bảng trong kho tài liệu. Không bắt buộc một định dạng, nhưng phải có khóa nhận dạng và bằng chứng kiểm tra.

| Trường | Ý nghĩa |
|---|---|
| `component_id` | ID ổn định, duy nhất cho mục kiểm kê |
| `service` | Dịch vụ/module sử dụng |
| `category` | JDK, dependency, framework, plugin, test, agent, native,… |
| `coordinates` | Maven GAV, image digest, tên tool hoặc native binary |
| `scope` | compile/runtime/test/build/CI/production |
| `current_version` | Phiên bản được resolve/đang chạy |
| `target_version` | Bản dự kiến sau nâng cấp |
| `jdk_context` | Build JDK, test JDK, runtime JDK hoặc kết hợp |
| `platform` | OS/architecture nếu có |
| `dependency_path` | Vì sao thành phần xuất hiện |
| `compatibility_claim` | Vendor hỗ trợ/có giới hạn/không rõ |
| `evidence_uri` | Release note/compatibility matrix/ticket test |
| `evidence_checked_at` | Ngày kiểm tra bằng chứng |
| `local_test_result` | Chưa chạy/PASS/FAIL kèm run ID |
| `risk` | Mức nghiêm trọng/tác động |
| `status` | Trạng thái xử lý |
| `owner` | Người/nhóm chịu trách nhiệm |
| `next_action` | Hành động và điều kiện hoàn tất |
| `deadline` | Mốc dự kiến |
| `notes` | Giới hạn, giả định, blocker |

### 20.1. Ví dụ CSV của schema

~~~csv
component_id,service,category,coordinates,scope,current_version,target_version,jdk_context,platform,status,owner,evidence_uri
jdk-runtime,billing-service,JDK,<runtime-image-digest>,production,<verify>,27,runtime,linux-amd64,NEEDS_TEST,platform-team,<release-note-link>
build-gradle,billing-service,build-tool,Gradle-wrapper,build,<verify>,9.8.0,daemon,linux-amd64,NEEDS_TEST,build-team,https://docs.gradle.org/current/userguide/compatibility.html
web-framework,billing-service,framework,<artifact-coordinate>,runtime,<verify>,<approved-version>,runtime,linux-amd64,UNKNOWN,service-team,<vendor-matrix-link>
bytecode-agent,billing-service,agent,<agent-coordinate>,runtime,<verify>,<approved-version>,runtime,linux-amd64,UNKNOWN,observability-team,<agent-release-note>
~~~

**Đây là dữ liệu minh họa, không phải kết quả quét một dự án có thật.** Những giá trị trong dấu ngoặc là placeholder phải thay sau khi quan sát thật. Đặc biệt, Gradle 9.8.0 là mốc có xác nhận hỗ trợ Java 27, nhưng dự án mẫu vẫn ở trạng thái `NEEDS_TEST` cho đến khi thực chạy thử nghiệm.

### 20.2. Một component có thể có nhiều bản ghi

Nếu một thư viện cùng tọa độ nhưng được dùng ở hai service có runtime, scope hoặc owner khác nhau, có thể cần hai bản ghi liên kết cùng `component_id` gốc. Mỗi bản ghi phải rõ **môi trường nào đang được đánh giá**.

Không gộp `javaagent` runtime và dependency test ở cùng một dòng nếu chúng có yêu cầu tương thích khác nhau.

## 21. Bằng chứng hỗ trợ và chất lượng nguồn

Không phải thông tin nào cũng có giá trị chứng minh như nhau.

| Bằng chứng | Giá trị | Giới hạn |
|---|---|---|
| Compatibility matrix chính thức của vendor | Mạnh về phạm vi hỗ trợ vendor cam kết | Có thể giới hạn theo version/OS |
| Release notes của đúng phiên bản | Xác nhận thay đổi và yêu cầu nâng cấp | Không đảm bảo mọi tình huống |
| Hướng dẫn migration chính thức | Cho biết đường nâng cấp và rủi ro | Cần đối chiếu cấu hình thực tế |
| Kết quả CI của dự án upstream trên JDK 27 | Bổ sung dữ liệu test | Có thể không bao phủ workload của bạn |
| Test nội bộ trên Java 27 | Mạnh cho cấu hình được thử | Không tự là tuyên bố vendor support |
| Issue/forum của cộng đồng | Gợi ý nguyên nhân và workaround | Không phải xác nhận chính thức |
| Dependency mới nhất trên registry | Biết phiên bản tồn tại | **Không chứng minh hỗ trợ JDK 27** |

### 21.1. Quy tắc trích dẫn trong danh mục

Mỗi dòng cần ghi **URL + thời điểm kiểm tra + phiên bản được tài liệu nói đến**. Ví dụ “Gradle hỗ trợ Java 27” phải gắn với mốc **Gradle 9.8.0 trở lên**, không trỏ tới một trang chủ chung rồi bỏ đi giới hạn version.

Nếu tài liệu vendor chỉ nói “Java 21+” nhưng không xác nhận Java 27 trong compatibility matrix, tùy chính sách dự án có thể ghi `UNDER_TEST` thay vì `SUPPORTED_CONFIRMED`. Không suy diễn rằng dấu cộng luôn có nghĩa mọi major version tương lai đều đã được test.

### 21.2. Thông tin công khai và thông tin triển khai của bạn

Release note là bằng chứng công khai; log test là bằng chứng nội bộ. Một danh mục tốt liên kết cả hai nhưng không đưa token, đường dẫn chứa bí mật, nội dung biến môi trường nhạy cảm hoặc thông tin riêng vào tài liệu chia sẻ rộng rãi.

## 22. Trạng thái công việc: tách support claim và test result

Có thể dùng quy trình trạng thái đơn giản:

~~~text
DISCOVERED
    |
    v
VERSION_IDENTIFIED
    |
    +--> SUPPORTED_BY_VENDOR
    |          |
    |          v
    |       NEEDS_TEST
    |          |
    |     +----+-----+
    |     |          |
    |    PASS       FAIL
    |     |          |
    |     v          v
    |  VERIFIED    BLOCKED
    |
    +--> UNKNOWN / UNSUPPORTED
               |
        investigate/update/replace
               |
               v
            NEEDS_TEST
~~~

Những trạng thái trên **không phải enum do JDK cung cấp** mà là gợi ý quản lý dự án.

Nên lưu **hai trường riêng**:

- `vendor_support_status`: xác nhận/không xác nhận/chưa rõ.
- `local_test_status`: chưa chạy/PASS/FAIL/BLOCKED.

Nhờ vậy tránh việc một test nội bộ PASS bị hiểu thành vendor đã chính thức hỗ trợ, hoặc một vendor claim dẫn đến bỏ qua test.

### 22.1. Mức độ rủi ro

| Mức | Tiêu chí ví dụ | Hành động |
|---|---|---|
| P0 — Blocker | App không build/start; data corruption/security; không có giải pháp | Chặn rollout |
| P1 — High | Core framework/DB driver/agent/native chưa rõ hoặc lỗi test quan trọng | Có owner và kế hoạch sửa trước production |
| P2 — Medium | Build/test tool phụ trợ, rủi ro giới hạn có workaround | Kiểm tra và theo dõi trước gate |
| P3 — Low | Lint/warning không ảnh hưởng release theo đánh giá có chứng cứ | Ghi nhận và lên kế hoạch hợp lý |

Ưu tiên không chỉ dựa vào số lượng dependency. **Một runtime agent duy nhất có thể rủi ro cao hơn hàng trăm thư viện utility đã xác minh**.

## 23. Quy trình thu thập danh mục theo nhiều lớp

Thực hiện theo thứ tự để giảm việc bỏ sót:

1. **Chốt baseline:** application version, JDK hiện tại, vendor, build ID, deployment topology.
2. **Khoanh vùng service/module:** Java process nào nằm trong phạm vi nâng cấp?
3. **Xác định build system:** wrapper Maven/Gradle, toolchains, plugin và profile.
4. **Xuất dependency graph:** direct, transitive, runtime/test/build.
5. **Ghi framework/BOM:** resolved versions và đúng nhánh support.
6. **Ghi code generation/bytecode:** processors, language compilers, mock/coverage/agent.
7. **Ghi native integration:** JNI/FFM/JNA, binaries, OS/CPU/ABI.
8. **Ghi CI/CD/container:** build/runtime image, manifest, JDK flags, sidecars.
9. **Quét JDK internals/deprecation:** `jdeps`, `jdeprscan` và release notes.
10. **Đối chiếu vendor evidence:** support matrix của từng component.
11. **Tạo test matrix:** compile, unit, integration, startup, performance/security.
12. **Gán owner/action:** không để mục `UNKNOWN` vĩnh viễn.
13. **Chạy thử, đính kèm run ID/log:** cập nhật trạng thái dựa trên bằng chứng.
14. **Khóa danh mục theo build artifact:** có revision/digest để truy nguyên.

### 23.1. Không dựa hoàn toàn vào một tool scan

Một công cụ dependency report thường không thấy:

- Image OS packages.
- Java agents thêm qua `JAVA_TOOL_OPTIONS`.
- Native libraries tải khi chạy.
- Plugin được tải qua đường dẫn hoặc URL.
- JVM startup flags từ Kubernetes manifest.
- Một tool riêng do CI job cài ở ngoài build files.
- Những JDK khác được dùng để chạy test riêng.

Vì vậy, danh mục cần kết hợp **static graph, runtime observation, deployment manifest và xác nhận của owner**.
## 24. Ví dụ thực hành: lập danh mục cho một hệ thống giả định

Giả sử một ứng dụng **`orders-api`** đang chạy Java 21 và chuẩn bị thử Java 27. Hệ thống có:

- Dịch vụ web JVM đóng gói thành OCI container.
- Maven build, một framework web/ORM và JDBC driver.
- Thư viện JSON, logging, HTTP client.
- Annotation processor và coverage agent.
- Integration tests dùng container database.
- APM Java agent trên production.
- Một tác vụ batch dùng cùng thư viện ứng dụng.

Đây là **tình huống giả định**; các tọa độ và phiên bản chưa xác định phải được lấy từ dự án thật, không tự điền.

### 24.1. Danh sách hạng mục ban đầu

| ID | Nhóm | Version hiện tại | Target/điều kiện | Bằng chứng cần có | Trạng thái |
|---|---|---|---|---|---|
| JDK-CI | JDK build | Cần kiểm tra runner | JDK 27 | Log `mvn --version`, JDK vendor/build | DISCOVERED |
| JDK-APP | JDK runtime | Ví dụ Java 21 | Java 27 | Image digest, startup log | DISCOVERED |
| MVN-CORE | Build tool | Cần kiểm tra wrapper | Bản chạy được trên JDK 27 | Release notes + build test | UNKNOWN |
| MVN-COMPILER | Build plugin | Cần lấy từ effective POM | `--release` theo target | Plugin support + compile log | UNKNOWN |
| WEB-FW | Framework | Cần lấy resolved version | Bản vendor xác nhận | Compatibility matrix | UNKNOWN |
| ORM | Persistence | Cần lấy resolved version | Tương thích Java 27 | Release notes + DB test | UNKNOWN |
| JDBC | Database driver | Cần lấy resolved version | Driver được hỗ trợ | Vendor matrix + connection test | UNKNOWN |
| JSON | Library | Cần lấy resolved version | Cùng schema | Tests + release notes | UNKNOWN |
| APT | Annotation processor | Cần lấy processor version | Compile JDK 27 | Compile/generated-code test | UNKNOWN |
| COV | Coverage agent | Cần lấy agent version | Class-file major 71 | Agent release + coverage test | UNKNOWN |
| APM | Runtime agent | Cần lấy agent version | JDK 27 runtime | Vendor support + startup/telemetry | UNKNOWN |
| DB-TEST | Integration test | Cần kiểm tra runner/container | Java 27 test path | CI log + DB integration | UNKNOWN |
| BATCH | Batch runtime | Cần kiểm tra image/job | Java 27 | Job execution + schedule | UNKNOWN |

Đừng tự ghi một framework hay driver “tương thích Java 27” nếu chưa xác minh version. **Một trạng thái UNKNOWN chính xác hữu ích hơn một trạng thái PASS giả tạo.**

### 24.2. Gắn nguồn gốc dependency

Giả sử một bytecode library không được khai báo trực tiếp mà được kéo theo bởi framework. Danh mục cần chứa đường đi:

~~~text
orders-api
  └── web-framework-starter (direct)
        └── runtime-proxy-library (transitive)
              └── bytecode-library (transitive)
~~~

Cây trên chỉ minh họa quan hệ; không đại diện một bộ framework thực. Khi mở ticket sửa, xác định rằng version cuối có thể do BOM quản lý và **owner của starter/framework** cần kiểm tra trước khi override bytecode library.

### 24.3. Phân chia owner

| Owner | Trách nhiệm |
|---|---|
| Platform/runtime team | JDK distributions, container runtime, JVM flags |
| Build/Developer Experience | Maven/Gradle wrapper, compiler, CI runners |
| Application team | Framework, app libraries, source compatibility |
| Test/QA team | Test frameworks, coverage, integration matrix |
| Observability team | APM/monitoring/profiler agents |
| Security team | JDK security changes, dependency vulnerabilities, TLS |
| Operations/SRE | Deploy pipeline, rollout, canary, rollback, dashboards |
| Vendor/license owner nếu có | Support policy của runtime/commercial dependencies |

Đây là cách chia nhiệm vụ tham khảo. Trong dự án nhỏ, một người có thể kiêm nhiều vai trò; **mỗi mục vẫn cần một owner chịu trách nhiệm cuối cùng**.

## 25. Đối chiếu bằng chứng trên đúng phiên bản, không chỉ tên sản phẩm

### 25.1. Ví dụ mốc có thể ghi nhận ngay

Theo tài liệu chính thức đã xuất bản tháng 9/2026:

- **JDK 27:** có release notes và migration guide tương ứng bản phát hành 15/09/2026.
- **Gradle:** từ **9.8.0** hỗ trợ Java 27 cho **Gradle daemon và Java toolchains** theo compatibility matrix/release notes.
- **Maven Compiler Plugin:** hỗ trợ cấu hình `--release` để giới hạn language/API/bytecode theo Java release được compiler hỗ trợ.

Đây là **bằng chứng về sản phẩm hoặc chức năng được nêu**, chưa nói dự án cụ thể đang dùng đúng phiên bản hoặc chạy test thành công.

### 25.2. Ví dụ chưa đủ bằng chứng

Những khẳng định sau **không đủ** nếu thiếu kiểm chứng cụ thể:

- “Spring Boot nào cũng chạy trên Java 27.”
- “Phiên bản Lombok hiện tại của dự án chắc chắn dùng được vì ứng dụng từng build trên Java 21.”
- “Tất cả phiên bản Mockito/JaCoCo/ASM sẽ hiểu bytecode version 71.”
- “Mọi Gradle plugin sẽ hoạt động vì Gradle daemon đã hỗ trợ Java 27.”
- “Native binary cho Linux x64 chắc chắn chạy trên Linux ARM64.”
- “Build PASS nên Java agent production cũng tương thích.”

Ghi `UNKNOWN`, bổ sung vendor matrix và thử nghiệm đúng tổ hợp thay vì chọn một con số version theo suy đoán.

## 26. Ma trận kiểm thử tương thích tối thiểu

Nên phân biệt hai trục:

1. **JDK chạy ứng dụng:** baseline và Java 27.
2. **Artifact/build target:** bản hiện tại và bản dự kiến sau nâng cấp.

Một ma trận thí nghiệm tham khảo:

| Thí nghiệm | Build JDK / target | Runtime | Mục tiêu |
|---|---|---|---|
| Baseline | Cấu hình hiện tại | JDK hiện tại | Có số liệu đối chứng |
| Runtime-only | Artifact cũ, không rebuild | **JDK 27** | Phát hiện lỗi startup/behavior runtime |
| Rebuild, target cũ | **JDK 27 / --release cũ** | JDK cũ và/hoặc JDK 27 | Kiểm tra compiler/toolchain nhưng giữ binary target |
| Rebuild, target 27 | **JDK 27 / --release 27** | **JDK 27** | Kiểm tra mã và bytecode target mới |
| CI integration | Build được quản lý | **JDK 27** | Kiểm tra DB, queue, HTTP, TLS, agent |
| Staging/canary | Image/digest mục tiêu | **JDK 27** | Xác nhận rollout/metrics/rollback |

**Không chạy artifact major 71 trên JDK 21** rồi ghi kết quả FAIL như một lỗi ngẫu nhiên cần sửa: đó là giới hạn tương thích bytecode có thể dự đoán trước.

### 26.1. Không nhất thiết phải đổi target lên 27 ngay

Nếu mục tiêu là xác minh production chạy trên runtime Java 27 nhưng vẫn cần giữ khả năng hỗ trợ Java 21 cho một số client hoặc môi trường khác, có thể tạm **giữ `--release 21`**. Tuy nhiên:

- Compiler JDK 27 có thể phát hiện lỗi mới.
- Dependency JAR có thể có class target cao hơn.
- Runtime behavior vẫn có thể khác.
- Không được sử dụng API chỉ có ở Java 27 nếu target cần chạy trên Java 21.

Phải ghi **chính sách target** trong danh mục; không tự hiểu nâng runtime là nâng language level.

## 27. Bộ kiểm thử trước khi xác nhận “READY”

| Gate | Bằng chứng | Nếu không đạt |
|---|---|---|
| G1 — Inventory đầy đủ | Danh sách JDK, direct/transitive libraries, framework, build/test/agent/native | Không bắt đầu rollout |
| G2 — Vendor support | Version và đường link support matrix của thành phần trọng yếu | Điều tra, đổi version hoặc chấp nhận rủi ro có phê duyệt |
| G3 — Build | Build reproducible trên toolchain đã chọn | Sửa compiler/plugin/processor |
| G4 — Unit tests | Test suite chạy thật trên JDK 27 | Sửa behavior hoặc dependency |
| G5 — Integration tests | Database, HTTP, queue, external services tương đương | Phân tích protocol/driver/framework |
| G6 — Runtime startup | App, agent, native lib khởi động và shutdown | Chặn rollout |
| G7 — Security | TLS, cert, auth, data/permission behavior | Chặn rollout nếu rủi ro nghiêm trọng |
| G8 — Operational | Logs, metrics, traces, health probes, container rollout | Chặn rollout nếu thiếu observability |
| G9 — Performance | Độ trễ/throughput/GC/CPU trong ngưỡng hợp lý | Điều tra regression |
| G10 — Recovery | Đã thử rollback/restore trong môi trường phù hợp | Chưa cho triển khai đại trà |

Các gate cần có **owner, run ID, ngày thử, commit, JDK build và artifact digest**. Đừng chỉ dùng một checkbox `PASS` không có log hoặc bối cảnh.

### 27.1. Một startup thành công chưa đủ

Một ứng dụng có thể khởi động nhưng thất bại khi:

- Request chạm đúng code path serialization hiếm.
- Driver làm việc với timestamp hoặc timezone.
- Proxy/mocking sinh bytecode động.
- Java agent instrument class khi endpoint đầu tiên được gọi.
- Native library được lazy-load trong batch job.
- TLS handshake với một đối tác sử dụng thuật toán/protocol cụ thể.

Vì vậy, test cần phản ánh **những đường đi thật sự quan trọng của sản phẩm**, không chỉ health endpoint.

## 28. Chiến lược nâng cấp theo các vòng có thể đảo ngược

Một kế hoạch hợp lý có thể chia:

1. **Khảo sát:** đọc runtime/build metadata và dependency graph, tạo danh mục.
2. **Làm sạch rủi ro rõ ràng:** nâng những component đã được xác định thiếu hỗ trợ trên JDK 27.
3. **Runtime trial:** thử chạy artifact hiện tại trên Java 27 trong test environment.
4. **Build/toolchain trial:** cấu hình compiler/test JDK, giữ hoặc nâng target theo quyết định.
5. **Test đầy đủ:** unit, integration, security, performance, operational.
6. **Staging:** image đích có digest cụ thể, so sánh metrics với baseline.
7. **Canary:** triển khai giới hạn, có criteria và cảnh báo.
8. **Mở rộng:** rollout dần khi đạt gate.
9. **Theo dõi sau triển khai:** incident, memory, GC, latency, errors, agent/telemetry.
10. **Kết thúc:** cập nhật danh mục, lưu bằng chứng và quy trình vận hành mới.

**Bản chất của bài này là lập danh mục để hỗ trợ những bước trên**, không phải tự động thực hiện deploy.

### 28.1. Kế hoạch rollback phải được ghi từ đầu

Khi nâng JDK, rollback có thể là quay về image cũ; nhưng nếu đồng thời thay đổi database schema, protocol hoặc serialization, rollback image đơn thuần **có thể không đủ**.

Cần kiểm kê các dependency có **migration một chiều** và quyết định có tách khỏi đợt nâng JDK hay không.

## 29. Tự động hóa việc giữ danh mục cập nhật

Danh mục viết thủ công một lần sẽ nhanh chóng lỗi thời nếu dependency graph, container image hoặc CI workflow thay đổi.

Các khả năng tự động hóa phù hợp:

- Xuất dependency tree hoặc SBOM theo mỗi build quan trọng.
- Gắn **commit SHA/build ID** với snapshot của danh mục.
- So sánh các phiên bản **được resolve** giữa hai build.
- Cảnh báo khi xuất hiện library/agent mới chưa có owner.
- Đối chiếu image digest và JDK version từ artifact/deploy pipeline.
- Gắn link CI test run với component/status.
- Theo dõi upstream release note cho những blocker quan trọng.
- Định kỳ tái xác minh evidence từng vendor nếu support matrix thay đổi.

### 29.1. Không tự động chuyển UNKNOWN thành PASS

Một script có thể phát hiện rằng thư viện mới có version cao hơn, nhưng **không thể suy ra hỗ trợ Java 27 từ số version** nếu không có quy tắc và nguồn bằng chứng tương ứng.

Tự động hóa nên:

- Gắn trạng thái `NEEDS_REVIEW` khi dependency thay đổi.
- Cập nhật hash/coordinate/version một cách xác định.
- Để owner đánh giá compatibility claim.
- Chỉ đánh dấu local test PASS khi có kết quả test hợp lệ.
- Không ghi đè các quyết định rủi ro thủ công mà không có audit trail.

### 29.2. Quy tắc khi pipeline gặp thành phần mới

~~~text
Dependency graph thay đổi
           |
           v
Có artifact chưa nằm trong inventory?
      |                  |
     Có                Không
      |                  |
      v                  v
DISCOVERED         Cập nhật version/evidence
      |                  |
      +--------+---------+
               |
        Chờ owner review
               |
      Test trên JDK 27
               |
     PASS / FAIL / BLOCKED
~~~

Quy tắc trên giúp việc phát hiện dependency mới không bị biến thành một thay đổi âm thầm trước production.

## 30. Các lỗi kiểm kê thường gặp

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Chỉ ghi tên JDK “27” | Không biết vendor/patch/build | Ghi full runtime fingerprint |
| Chỉ xem `pom.xml` | Bỏ sót BOM và transitive versions | Lấy resolved dependency tree |
| Chỉ xem build.gradle | Bỏ sót constraints và variants | Dùng `dependencies`/`dependencyInsight` |
| Không kiểm tra test JDK | Unit test có thể vẫn chạy JVM cũ | Ghi JVM của test process |
| Chỉ kiểm framework core | Starter/processor/agent vẫn cũ | Kiểm toàn bộ ecosystem |
| Tưởng Gradle 9.8 giải quyết mọi plugin | Third-party plugin có thể chưa hỗ trợ | Đọc vendor matrix từng plugin |
| Quên annotation processor | Compiler thất bại trước khi build app | Ghi processor/version |
| Quên coverage/agent | Test hoặc prod lỗi class instrumentation | Test agent trên JDK 27 |
| Không quét native binaries | Crash hoặc UnsatisfiedLinkError trên OS/CPU khác | Ghi từng binary/ABI |
| Lạm dụng `--add-opens` | Che dependency chưa tương thích | Cập nhật thư viện và ghi exception tạm |
| Nhầm bytecode target với runtime | `UnsupportedClassVersionError` | Kiểm `--release` và JVM test |
| Bỏ qua multi-release JAR | Phân tích sai class thực thi | Kiểm metadata và `jdeps --multi-release` |
| Chỉ chạy smoke test | Không chạm code path quan trọng | Unit/integration/e2e/operational gates |
| Đánh dấu PASS vì vendor nói supported | Bỏ qua lỗi cấu hình dự án | Ghi vendor claim và local test riêng |
| Đánh dấu PASS vì test nội bộ chạy | Không biết chính sách hỗ trợ vendor | Gắn support matrix |
| Không lưu evidence timestamp | Danh mục cũ không còn đúng | Ngày kiểm tra/đường dẫn/release |
| Cập nhật mọi library lên latest | Version conflict, BOM mismatch | Kế hoạch nâng có chứng cứ |
| Quên container digest | Build/deploy không tái lập | Pin và log image digest |
| Chưa thiết kế rollback | Có thể không quay lại được khi lỗi | Test rollback trước rollout |
| Dùng cảnh báo native access như PASS | Rủi ro bị từ chối ở chính sách nghiêm ngặt hơn | Đánh giá và cấp quyền rõ |
| Không có owner | Mục UNKNOWN tồn tại mãi | Gắn người chịu trách nhiệm |

## 31. Checklist thu thập trước khi thử Java 27

- [ ] Đã liệt kê mọi service, worker, batch job và Java process trong phạm vi chưa?
- [ ] Đã ghi baseline JDK và mục tiêu Java 27 cho từng môi trường chưa?
- [ ] Đã ghi JDK vendor/build và OS/architecture thực tế chưa?
- [ ] Đã phân biệt build JDK, compiler toolchain, test JDK và runtime JDK chưa?
- [ ] Đã xác định `--release`/class-file version thực tế chưa?
- [ ] Có dependency graph của **resolved versions**, không chỉ source declarations?
- [ ] Đã ghi direct/transitive và scope/variant/BOM/constraints chưa?
- [ ] Đã kiểm framework/application server/ORM/database driver đúng phiên bản chưa?
- [ ] Đã kiểm compiler plugin, annotation processor và code generator chưa?
- [ ] Đã kiểm ASM/Byte Buddy/JaCoCo/Mockito hoặc tool tạo bytecode thực sự dùng chưa?
- [ ] Đã kiểm Java agents, profiler, monitoring và test runner chưa?
- [ ] Đã xác định JNI/FFM/JNA/native binaries, OS/CPU/ABI chưa?
- [ ] Đã kiểm image build/runtime, runner JDK, Kubernetes startup flags chưa?
- [ ] Đã quét JDK internal/deprecated API và xem migration guide chưa?
- [ ] Có kiểm tra reflection, native access, TLS, locale/timezone và serialization?
- [ ] Mỗi component có owner và trạng thái xác định chưa?
- [ ] Có URL bằng chứng hỗ trợ đúng version cùng ngày kiểm tra chưa?
- [ ] Có tách vendor support khỏi kết quả test nội bộ chưa?
- [ ] Có danh sách blocker, next action và deadline chưa?
- [ ] Có test matrix baseline/Java27, cùng run ID/log/digest?
- [ ] Có kế hoạch rollout và rollback có thể thử nghiệm?
- [ ] Có snapshot danh mục gắn với source revision và artifact?
- [ ] Không có phiên bản/framework nào được tự gắn “compatible” thiếu chứng cứ?

## 32. Bài tập thực hành

### Bài tập 1: Lập runtime fingerprint

Trên một ứng dụng Java bạn kiểm soát, ghi:

~~~shell
java --version
javac -version
~~~

Nếu dùng Maven, ghi thêm:

~~~shell
mvn --version
mvn dependency:tree
~~~

Nếu dùng Gradle, ghi:

~~~shell
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
~~~

**Yêu cầu:** nêu sự khác nhau giữa JDK của shell, build daemon, compiler toolchain, test JVM và runtime image. Không sửa build files nếu mục đích mới là thu thập baseline.

### Bài tập 2: Truy nguồn một transitive dependency

Chọn một thư viện bytecode/JSON thật sự nằm trong dependency graph. Ghi version, scope, đường dependency và version được BOM/constraint chọn.

**Câu hỏi:** Vì sao chỉ cập nhật phiên bản trực tiếp trong POM/Gradle chưa chắc thay đổi resolved version của dependency transitive?

### Bài tập 3: Đối chiếu support matrix

Chọn ba thành phần trong dự án: một framework, một compiler/codegen tool và một runtime agent. Tìm release note/compatibility matrix chính thức cho từng component.

**Yêu cầu:** phân biệt trạng thái `SUPPORTED_BY_VENDOR`, `UNKNOWN` và `UNSUPPORTED` dựa trên bằng chứng chính xác; không dùng việc phiên bản mới tồn tại làm bằng chứng.

### Bài tập 4: Thử ba chế độ JDK/bytecode

Lần lượt thử:

1. Artifact baseline trên runtime hiện tại.
2. Artifact baseline trên Java 27.
3. Recompile trên Java 27 với target được dự án chấp thuận và chạy test.

**Câu hỏi:** Thí nghiệm nào giúp phân biệt lỗi runtime khỏi lỗi source/compile? Tại sao major version 71 không chạy được trên runtime Java 21?

### Bài tập 5: Phân loại rủi ro

Tạo một bảng 10 hạng mục. Đưa vào ít nhất: JDK runtime, framework, JDBC driver, annotation processor, coverage agent, APM agent, container image và native binary nếu có.

Gán owner, risk, evidence, next action cho từng mục. Đừng đánh dấu `READY` khi chưa có test run phù hợp.

### Bài tập 6: Thực hiện readiness review

Viết báo cáo giả định cho một dịch vụ:

~~~text
Service: <service>
Current JDK: <vendor/build>
Target JDK: <vendor/build 27>
Current bytecode target: <release>
Planned target: <release>
Dependency snapshot: <build-id/SBOM>
Framework/vendor compatibility: <links>
Build/test results: <CI run ids>
Runtime image digest: <digest>
Critical blockers: <list>
Owners: <names/teams>
Rollout gates: <list>
Rollback: <validated procedure>
Decision: READY / NOT_READY / CONDITIONAL
~~~

Chỉ dùng `READY` khi chứng cứ đầy đủ theo tiêu chuẩn dự án. Nếu chưa có log hoặc compatibility claim, ghi `UNKNOWN`/`NOT_READY` thay vì suy đoán.

## 33. Tóm tắt

- Nâng Java 27 là **bài toán của toàn bộ toolchain và runtime**, không chỉ code Java.
- Danh mục phải bao phủ **build JDK, compiler target, test JVM, runtime JDK, direct/transitive dependencies, framework, build plugins, codegen, test/agent/native và deployment**.
- **Class-file major version 71** là định dạng bytecode Java 27; build target và runtime phải tương thích.
- Khi muốn biên dịch theo một release cụ thể, ưu tiên **`--release`** để kiểm soát language, bytecode và API Java SE mục tiêu.
- **Gradle 9.8.0** có xác nhận chính thức hỗ trợ Java 27 cho daemon và toolchains; support của third-party Gradle plugins cần kiểm tra riêng.
- Không mặc định framework, compiler plugin, bytecode tool hay native library phiên bản bất kỳ đều hỗ trợ Java 27.
- Dùng **`jdeps`, `jdeprscan`, dependency tree/SBOM** làm đầu vào, nhưng không quên reflection, agent, native, flags và container.
- Một mục có thể **được vendor hỗ trợ nhưng test nội bộ chưa PASS**, hoặc ngược lại; giữ hai trạng thái riêng.
- Danh mục tốt có **owner, risk, evidence URI/date, next action và test run** trên từng thành phần.
- Kiểm chứng **source, binary, behavioral, toolchain, operational và security compatibility** trước rollout.
- Lưu snapshot theo build ID/artifact digest và **thiết kế rollback** ngay từ đầu.
- Mọi kết luận tương thích phải dựa trên **phiên bản thực tế và chứng cứ có thể kiểm tra**, không dựa vào suy đoán.

## 34. Tài liệu tham khảo chính thức

### Java 27 và công cụ kiểm tra

- [Oracle JDK Migration Guide — Release 27](https://docs.oracle.com/en/java/javase/27/migrate/index.html)
- [Oracle JDK 27 — Preparing for Migration](https://docs.oracle.com/en/java/javase/27/migrate/preparing-migration.html)
- [Oracle JDK 27 Release Notes — 15 September 2026](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Oracle JDK 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [Oracle JDK 27 — The javac Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [Oracle JDK 27 — jdeps](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html)
- [Oracle JDK 27 — jdeprscan](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeprscan.html)
- [Oracle JDK 27 — javap](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javap.html)
- [Java SE 27 — ClassFile API và major version 71](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFile.html)

### Build tools và dependency management

- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [Gradle 9.8.0 Release Notes — Support for Java 27](https://docs.gradle.org/9.8.0/release-notes.html)
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Apache Maven — Compiler Plugin: Setting --release](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/set-compiler-release.html)
- [Apache Maven — Dependency Plugin: dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven — Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/)
- [CycloneDX — SBOM Specification](https://cyclonedx.org/specification/)

### Cách áp dụng nguồn tham khảo

Những liên kết này là **điểm khởi đầu kiểm chứng**. Với Spring Boot, Quarkus, Micronaut, Hibernate, Kotlin, Scala, Lombok, Mockito, JaCoCo, APM và các sản phẩm khác, hãy tìm thêm release notes/compatibility matrix **của đúng phiên bản dự án đang dùng**. Không có một bảng chung cố định có thể thay thế bằng chứng theo phiên bản cho mọi hệ sinh thái Java.
