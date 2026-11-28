# Đối chiếu thay đổi của Java 27 với phiên bản nguồn đang sử dụng

Nâng ứng dụng lên **Java 27** không chỉ là thay JAVA_HOME hoặc sửa một con số trong file build. Điều cần chứng minh là: **mã nguồn, bytecode, thư viện, hành vi runtime và quy trình vận hành còn phù hợp với yêu cầu của dự án hay không?**

Ví dụ, một ứng dụng Java 21 có thể chạy trên JDK 27 mà không cần biên dịch lại, nhưng vẫn có thể gặp vấn đề ở ORM dùng deep reflection, startup flag cũ, TLS, agent đọc bytecode hoặc khác biệt về locale và hiệu năng. Ngược lại, một ứng dụng được biên dịch trên JDK 27 không tự chạy được trên runtime 21 nếu tạo class file dành riêng cho 27.

Bài thuộc chương **Nâng cấp và tương thích Java 27** của học phần **JAVA_VERSION_JAVA27 — Java 27 và các kiến thức liên quan**. Đề bài là **đối chiếu thay đổi của Java 27 với phiên bản nguồn đang sử dụng**. Bài không giả định source baseline luôn là Java 8, 17, 21 hay 25. Các tính năng đã final, có thể dùng trong Java 27 được phân biệt với các thử nghiệm preview/incubator và những cơ chế legacy cần loại bỏ, không phải khuyến nghị áp dụng mới.

Mục tiêu học tập:

- Xác nhận phiên bản nguồn, phiên bản build, mức API và runtime thực tế.
- Phân biệt tương thích mã nguồn, nhị phân, hành vi và vận hành.
- Lập bản đồ các thay đổi từ **baseline B** tới Java 27 qua tất cả release trung gian.
- Hiểu những điểm mới chính thức của JDK 27 và mức ổn định của chúng.
- Dùng **javac --release**, **jdeps**, **jdeprscan** và các công cụ JDK hiện hành.
- Kiểm tra dependency, JVM flags, reflection, bảo mật, GC, locale và native integration.
- Xây ma trận kiểm thử và quy trình rollout/rollback dựa trên bằng chứng.

## 1. Nguồn đối chiếu không chỉ là phiên bản java -version

Một dự án thường có nhiều mức phiên bản Java khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ minh họa |
|---|---|---|
| **Build JDK** | JDK chạy javac và build plugins | JDK 27 |
| **Source level** | Cú pháp/ngôn ngữ được phép sử dụng | Java 21 |
| **API baseline** | API Java SE tối thiểu có thể sử dụng | Java SE 21 |
| **Class-file target** | Mức bytecode được tạo | Major version 65 |
| **Runtime JDK** | JVM và thư viện nền khi chạy | JDK 21 hoặc JDK 27 |
| **Library baseline** | Bản Java tối thiểu mà thư viện hứa hỗ trợ | Java 17 |
| **Toolchain CI** | Maven/Gradle/JDK thực tế trong pipeline | Có thể khác máy local |

Ví dụ: **biên dịch bằng JDK 27 với --release 21** là một lựa chọn có chủ đích để vẫn phát hành code hỗ trợ Java 21. Nếu muốn sử dụng API chỉ có trong Java 27, phải **nâng mức API và runtime được cam kết** hoặc xây giải pháp phân nhánh tương thích rõ ràng.

Đừng nhìn thấy JDK 27 trong IDE rồi kết luận rằng ứng dụng đã hoàn tất migration.

## 2. Lập baseline trước khi đọc release notes

Nguồn xác định baseline nên là **cấu hình dự án và artifact đã được kiểm chứng**, không chỉ trí nhớ của người phát triển.

Cần kiểm kê:

1. **Java tối thiểu được công bố hỗ trợ** cho người dùng hoặc các service nội bộ.
2. **JDK đang build và đang chạy production**, bao gồm update version và vendor.
3. **Maven/Gradle toolchain** cùng compiler release/source/target.
4. **Base image runtime**, kiến trúc CPU, OS, container CPU/RAM limits.
5. **Dependency tree** cả direct và transitive.
6. **JVM options, Java agents, annotation processors và JNI libraries**.
7. **Định dạng dữ liệu** trao đổi với database/service khác.
8. **Số liệu baseline** cho unit tests, integration tests, latency, GC, heap và CPU.
9. **Phiên bản artifact và môi trường rollback**.

Ví dụ một báo cáo:

| Thuộc tính | Giá trị minh họa |
|---|---|
| Source/API baseline | 21 |
| Build JDK hiện tại | 21.0.x |
| Runtime production | 21.0.x |
| Target runtime thử nghiệm | 27.x |
| Runtime tối thiểu muốn giữ | 21 |
| Kế hoạch sau migration | Giữ API 21, đổi runtime thành 27 |
| Điều kiện không được thay đổi | API công khai, định dạng dữ liệu, SLO |

Các con số trên là **ví dụ**, không phải trạng thái một dự án cụ thể.

Với repository nhiều module, xác nhận baseline **theo từng module**; tránh áp một con số chung nếu một module là thư viện hỗ trợ Java cũ trong khi một ứng dụng backend đã nâng lên Java 27.

## 3. Java 27 và các mốc phát hành

**JDK 27 GA ngày 15/09/2026**, tương ứng đặc tả **Java SE 27 / JSR 402**. Đây là **feature release không thuộc nhánh LTS theo lịch Java thông thường**; lựa chọn cho production còn phụ thuộc chính sách hỗ trợ của nhà cung cấp JDK và chu kỳ nâng cấp của tổ chức.

Cần phân biệt:

- **Java SE 27 specification**: hợp đồng ngôn ngữ, API chuẩn và JVM.
- **JDK 27 implementation**: javac, java, JFR, GCs, các thư viện thực thi và tooling.
- **Các update 27.x**: sửa lỗi, cập nhật bảo mật, timezone và những thay đổi phù hợp chính sách cập nhật.

Khi đánh giá, lấy **JDK 27 Release Notes** và **Oracle JDK Migration Guide 27** làm nguồn chính, sau đó đối chiếu release notes **từng bản trung gian**.

**Không nhầm tính năng có mặt trong Java 27 với tính năng lần đầu được thêm ở Java 27.** Ví dụ virtual threads đã final ở Java 21, FFM API final ở Java 22 và Markdown documentation comments xuất hiện từ Java 23.

## 4. Bốn lớp tương thích phải được kiểm chứng

| Loại tương thích | Câu hỏi kiểm tra | Ví dụ sự cố |
|---|---|---|
| **Source** | Source cũ có compile với compiler mới không? | Cú pháp, từ khóa, API bị xóa |
| **Binary** | Class file và JAR đã build có link với runtime mới không? | NoSuchMethodError, NoClassDefFoundError |
| **Behavioral** | Cùng input có hành vi đúng không? | TLS, locale, timezone, serialization, concurrency |
| **Operational** | Startup, build, metrics, container và observability còn đúng không? | JVM flag bị loại, agent không hỗ trợ, GC khác |

**Source compatible chưa chắc behavioral compatible.** Ví dụ đổi default GC không yêu cầu sửa Java source nhưng có thể làm thay đổi CPU, pause và memory footprint.

**Binary compatible cũng không đối xứng:** một class Java 21 thường có thể chạy trên runtime 27, nhưng class được biên dịch cho release 27 không được JVM 21 hỗ trợ.

Nên lập bằng chứng riêng cho từng loại thay vì chỉ ghi một nhãn “compatible”.

## 5. Đối chiếu tập thay đổi từ baseline B tới 27

Quy trình:

~~~text
Lấy baseline B
      |
      v
Liệt kê B+1, B+2, ..., 27
      |
      v
Đọc release notes và migration guide của từng bản
      |
      v
Phân loại: final / preview / removed / default changed
      |
      v
Đối chiếu mã, dependency, startup flags và workload
      |
      v
Chạy tests, phân loại rủi ro, lên kế hoạch remediation
~~~

Ví dụ:

- **Nguồn 26 → 27**: xem trực tiếp JDK 27, plus update release chính xác đang triển khai.
- **Nguồn 25 → 27**: xem cả thay đổi ở JDK 26 lẫn 27.
- **Nguồn 21 → 27**: xem 22, 23, 24, 25, 26 và 27.
- **Nguồn 17 → 27**: cộng thêm các thay đổi 18–21.
- **Nguồn 8 → 27**: xét cả JPMS từ Java 9, strong encapsulation và những loại bỏ tích lũy trong nhiều năm.

**Không chỉ xem chín JEP của Java 27 nếu dự án xuất phát từ phiên bản cũ.**

Có thể lập issue tracker theo các trường: **release xuất hiện**, **component bị ảnh hưởng**, **mức nghiêm trọng**, **điều kiện kích hoạt**, **cách khắc phục**, **test chứng minh**, **owner** và **trạng thái**.

## 6. Chín JEP chính thức của JDK 27

Java 27 GA có **9 JEP nổi bật**: bốn thay đổi final, bốn preview và một incubator.

| JEP | Thay đổi | Trạng thái ở 27 | Cần kiểm tra |
|---|---|---|---|
| **523** | G1 làm GC mặc định trong mọi môi trường | Final | Default GC trên máy ít tài nguyên |
| **527** | Post-Quantum Hybrid Key Exchange for TLS 1.3 | Final | TLS handshake, peer và security policies |
| **531** | Lazy Constants | Third Preview | API còn preview, không mặc định là ổn định |
| **532** | Primitive Types in Patterns, instanceof, switch | Fifth Preview | Cú pháp preview, flags và source compatibility |
| **533** | Structured Concurrency | Seventh Preview | API concurrency còn preview |
| **534** | Compact Object Headers by Default | Final | Heap footprint và profiling |
| **536** | JFR In-Process Data Redaction | Final | Logging/recording dữ liệu nhạy cảm |
| **537** | Vector API | Twelfth Incubator | Module incubator, rủi ro thay đổi |
| **538** | PEM Encodings of Cryptographic Objects | Third Preview | API xử lý PEM còn preview |

**Final** nghĩa tính năng đã được đưa vào platform/implementation theo trạng thái chính thức tương ứng. **Preview/incubator** phục vụ thu thập phản hồi và có thể thay đổi ở các release tiếp theo.

Một số tính năng trải qua nhiều vòng preview trước Java 27; nếu hệ thống dùng bản preview ở Java 25/26, phải kiểm tra lại **chữ ký API và hành vi** trên JDK 27.

## 7. Những thay đổi có thể ảnh hưởng ngay khi chỉ đổi runtime

Khi chạy binary cũ trên JDK 27, đặc biệt chú ý:

- **JEP 523**: G1 được chọn làm GC mặc định trong mọi môi trường được áp dụng.
- **JEP 534**: compact object headers được bật mặc định cho HotSpot trên kiến trúc phù hợp.
- **JEP 527**: lựa chọn thuật toán khi thương lượng TLS 1.3 có thể thay đổi.
- **JEP 536**: JFR redacts một số dữ liệu nhạy cảm trong recordings theo chính sách mặc định.

Các thay đổi này có thể quan sát được mà **không cần sử dụng API Java 27 trong source**.

Với mỗi điểm, trả lời:

1. Có thực sự bật mặc định trên OS/JVM đang chạy không?
2. Ứng dụng có cấu hình tường minh làm ghi đè mặc định không?
3. Cần đo metric hoặc hành vi nào trước/sau?
4. Có liên quan TLS, security policy, agent hay native code không?
5. Có cách rollback an toàn khi bản đích gây vấn đề không?

Không tự động quy mọi thay đổi performance quan sát được thành lỗi của một JEP; cần baseline có kiểm soát.

## 8. Preview/incubator: không trộn với migration ổn định

Những tính năng preview của Java 27 gồm primitive patterns, Lazy Constants, Structured Concurrency và PEM Encoding APIs. Vector API thuộc incubator module.

Ví dụ lệnh dành cho **mã thực sự sử dụng preview**:

~~~text
javac --enable-preview --release 27 -d out PreviewExample.java
java --enable-preview -cp out PreviewExample
~~~

Đây là ví dụ cú pháp lệnh, cần một source PreviewExample.java phù hợp.

Với Vector API incubator, có thể cần module riêng:

~~~text
javac --add-modules jdk.incubator.vector -d out VectorExample.java
java --add-modules jdk.incubator.vector -cp out VectorExample
~~~

**--enable-preview** và **--add-modules** không phải cùng một cơ chế.

Các giới hạn:

- Code preview có thể thay đổi chữ ký hoặc semantics giữa các release.
- Bật preview cần compiler/runtime phù hợp của release tương ứng.
- Bytecode có sử dụng preview không tự trở thành binary portable giữa các JDK khác nhau.
- Incubator module không được xem là API ổn định cho contract hỗ trợ lâu dài.

**Chiến lược hợp lý:** nâng runtime và chứng minh phần code hiện tại chạy đúng trước; đánh giá preview/incubator ở nhánh nghiên cứu riêng nếu cần.

## 9. Những tính năng hiện đại đã final trước JDK 27

Để tránh gắn nhãn sai, một số mốc đáng nhớ:

| Tính năng | Mốc final |
|---|---|
| Switch expressions | Java 14 |
| Records | Java 16 |
| Sealed classes | Java 17 |
| Virtual threads | Java 21 |
| Pattern matching for switch | Java 21 |
| Foreign Function & Memory API | Java 22 |
| Markdown documentation comments | Có từ Java 23 |
| Module import declarations | Java 25 |
| Compact source files và instance main methods | Java 25 |

Ví dụ: nếu nguồn là Java 17, có thể cân nhắc dùng virtual threads sau khi nâng. Tuy nhiên, đây là **thay đổi kiến trúc/concurrency riêng**, không phải điều kiện cần để chạy binary cũ trên Java 27.

Nếu nguồn đã là Java 25, các tính năng đã final trước đó có thể đang được sử dụng và trọng tâm đối chiếu là các thay đổi từ **26 và 27**.

## 10. Chọn lộ trình: runtime trước, source sau

Có thể chia migration thành hai mục tiêu.

### A. Giữ source/bytecode cũ, thay runtime

~~~text
Source Java 21
   |
javac --release 21
   |
Artifact tương thích Java 21
   |
java 27: kiểm tra binary, dependencies, runtime behavior
~~~

Lợi ích: giảm số thay đổi trong lần thử nghiệm đầu, dễ xác định lỗi do runtime.

### B. Dùng toolchain mới và thay baseline khi cần

~~~text
JDK 27 compiler
   |
   +-- --release 21 -> Artifact vẫn hướng Java 21
   |
   +-- --release 27 -> Artifact yêu cầu Java 27
~~~

Lựa chọn thứ hai cho phép dùng API/source final ở mức 27 nhưng **tăng yêu cầu Java tối thiểu** nếu đây là artifact được phân phối.

Một thư viện còn tuyên bố hỗ trợ Java 21 **không nên vô tình phát hành bytecode 27** chỉ vì máy build đã chuyển lên JDK 27.

## 11. Dùng javac --release để giữ hợp đồng cũ

Khi build bằng JDK 27 nhưng vẫn hỗ trợ Java 21:

~~~text
javac --release 21 -encoding UTF-8 -d out src/Example.java
~~~

**--release 21** yêu cầu javac tuân theo bộ cú pháp, class-file target và **public Java SE API tương ứng với release 21**.

Chỉ dùng:

~~~text
javac -source 21 -target 21 -d out src/Example.java
~~~

không cung cấp cùng mức bảo đảm ngăn code vô tình tham chiếu API chỉ có ở JDK build mới.

Lưu ý:

- **--release** không được dùng cùng **-source**/**-target** trong một lệnh.
- Các release được một bản javac hỗ trợ là tập hữu hạn; kiểm tra javac --help của đúng bản JDK.
- Thư viện bên ngoài vẫn phải cung cấp bytecode và API tương thích với runtime cũ.
- Build thành công không thay thế test thực tế trên JDK 21 nếu còn cam kết hỗ trợ bản đó.

**Không phải mọi plugin, annotation processor hoặc generated source đều tự tuân theo --release.** Kiểm tra sản phẩm build cuối cùng.

## 12. Class-file version: tại sao runtime cũ từ chối binary mới?

| Java release | Major version thông thường |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |
| 26 | 70 |
| **27** | **71** |

Một class thông thường compile hướng Java 27 có **major version 71**. JVM Java 21 không nạp được class file ở version này.

Lỗi hay gặp:

~~~text
java.lang.UnsupportedClassVersionError
~~~

Kiểm tra class:

~~~text
javap -verbose -classpath build/classes com.example.Main
~~~

Xem dòng **major version**. Với JAR nhiều bản (multi-release JAR), cần xét các lớp theo phiên bản runtime phù hợp.

**Tên file JAR hoặc thông số toolchain không phải bằng chứng chắc chắn** rằng mọi class bên trong đều đúng baseline; kiểm tra artifact thực tế khi cần.

## 13. Ma trận build và runtime cần kiểm tra

Giả sử baseline là Java 21, một ma trận hợp lý:

| Trường hợp | Artifact | Runtime | Mục tiêu |
|---|---|---|---|
| Baseline hiện tại | Build cho 21 | JDK 21 | So sánh chức năng và hiệu năng |
| Runtime migration | Binary cũ cho 21 | JDK 27 | Đánh giá runtime/dependency |
| Toolchain mới, API cũ | JDK 27 --release 21 | JDK 21 | Giữ cam kết hỗ trợ cũ |
| Toolchain mới, runtime mới | JDK 27 --release 21 | JDK 27 | Kiểm tra cross-build |
| Nâng minimum Java | JDK 27 --release 27 | JDK 27 | Chủ động sử dụng Java 27 |
| Preview riêng | JDK 27 có --enable-preview | JDK 27 có --enable-preview | Chỉ thử tính năng preview |

Ma trận này không bắt buộc cho tất cả dự án. Một ứng dụng backend chỉ chạy runtime 27 có thể không cần tiếp tục test trên Java 21 sau khi đã quyết định bỏ baseline đó. Nhưng **một thư viện còn hỗ trợ Java 21 phải giữ kiểm thử trên Java 21 thật**.

Thêm các biến số khi cần: Windows/Linux, x64/ARM64, container CPU quota, database driver, TLS peer và bản update JDK chính xác.

## 14. Maven: compiler release khác JDK chạy Maven

Ví dụ vẫn hỗ trợ Java 21:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

Mức release không nhất thiết phải trùng với JDK đang dùng để build. Nếu nhóm muốn chuyển minimum Java lên 27, có thể cập nhật thành **27**, nhưng đó là một thay đổi API/binary support cần được công bố.

Khi nâng công cụ, kiểm tra:

- **Maven** chạy được trên JDK 27.
- **Maven Compiler Plugin** và toolchains chọn đúng javac.
- **Surefire/Failsafe** chạy tests bằng JDK cần kiểm chứng.
- **Shade/assembly** và những plugin thay đổi class files.
- **Annotation processors**, code generator và generated sources.
- **Javadoc, code coverage, static analysis** và các plugin dùng javac/bytecode API.
- Maven Wrapper, CI images và JAVA_HOME.

Lệnh cơ bản:

~~~text
mvn -version
java -version
javac -version
~~~

Kết quả giúp xác định môi trường nhưng không tự khẳng định mọi plugin đã hỗ trợ runtime 27.

**Không chọn bừa một phiên bản Maven/plugin chỉ vì tên trông mới.** Chọn phiên bản đã được xác nhận hỗ trợ JDK và dự án, sau đó khóa version để build tái lập được.

## 15. Gradle: toolchain và options.release

Ví dụ **build.gradle (Groovy DSL)**:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

Ý nghĩa:

- Toolchain cung cấp **JDK 27** để compile.
- Artifact vẫn nhắm tới Java SE **21**.
- Nếu nâng baseline lên 27, cần thay **options.release = 27**, kiểm thử và công bố minimum runtime mới.

Kiểm tra Gradle Wrapper:

~~~text
./gradlew --version
./gradlew clean test
~~~

Trên Windows có thể dùng **gradlew.bat**.

**Gradle chạy trên JDK 27** và **Gradle dùng JDK 27 làm toolchain** là hai điều kiện khác nhau theo khả năng của phiên bản Gradle. Với dự án có Kotlin/Groovy/plugins phức tạp, kiểm tra release notes của cả plugin và ngôn ngữ.

Dùng Wrapper và build images được kiểm soát, tránh máy local/CI vô tình chạy các version công cụ khác nhau.

## 16. Dependency và transitive dependency thường gây rủi ro

Một ứng dụng có thể không trực tiếp gọi API nội bộ JDK nhưng thư viện vẫn dùng:

- ORM/JPA, serializer, reflection và proxy.
- Framework server, dependency injection.
- HTTP clients, JDBC/database drivers, TLS providers.
- Logging/metrics/tracing, APM agents.
- Bytecode libraries, code instrumentation.
- JNI/native libraries.
- Test runners, mocking, assertion frameworks.
- Annotation processors và build plugins.

Lập danh sách đánh giá:

| Thành phần | Điều cần xác minh | Bằng chứng |
|---|---|---|
| Framework | Bản hỗ trợ JDK 27, không dùng nội bộ bị chặn | Vendor docs và integration test |
| ORM/serializer | Final-field mutation, proxy, reflective access | Test entities, round-trip |
| JDBC driver | TLS, metadata, DB compatibility | Integration test |
| Bytecode tool | Hỗ trợ class-file major 71 | Compatibility release notes |
| APM/agent | JVM internals, tracing và JFR | Staging test |
| Native library | ABI/OS/CPU và quyền native access | Smoke test từng environment |
| Build plugin | Compiler/tooling integration | CI build sạch |

Không bỏ qua **transitive dependencies**. Một framework đã được nâng có thể vẫn kéo một thư viện parser/agent cũ không hiểu Java 27.

**Không bịa phiên bản thư viện “được hỗ trợ” nếu chưa xác minh compatibility matrix**. Với dependency không còn được bảo trì, lập kế hoạch thay thế thay vì che warning vô hạn.

## 17. Dùng jdeps phát hiện JDK internals

**jdeps** là công cụ của JDK phân tích phụ thuộc module/package/class.

Ví dụ với JAR:

~~~text
jdeps --summary app.jar
jdeps --jdk-internals app.jar
~~~

Nếu cần dependency classpath:

~~~text
jdeps --jdk-internals --class-path "lib/*" app.jar
~~~

Với multi-release JAR:

~~~text
jdeps --multi-release 27 --jdk-internals --class-path "lib/*" app.jar
~~~

**--jdk-internals** tìm tham chiếu tĩnh tới JDK internal APIs. Nó hữu ích khi baseline cũ dùng **sun.misc.Unsafe** hoặc những class không nằm trong hợp đồng public Java SE.

Hướng thay thế tùy nhu cầu:

- **java.util.Base64** thay Base64 encoder nội bộ.
- **VarHandle** cho thao tác atomic/memory ordering ở mức biến.
- **Foreign Function & Memory API** cho native/off-heap memory hiện đại.
- API công khai khác hoặc library được duy trì.

**jdeps không nhìn thấy mọi đường reflection, ServiceLoader, native lookup hoặc class name tạo động.** Không kết luận hệ thống sạch chỉ vì tool không hiển thị phụ thuộc nội bộ.

## 18. Dùng jdeprscan cho API deprecated

**jdeprscan** tìm những lời gọi tới API Java SE đã deprecated trong class/JAR:

~~~text
jdeprscan app.jar
jdeprscan --for-removal app.jar
~~~

Nếu có dependency ngoài cần giải quyết type:

~~~text
jdeprscan --class-path "lib/*" app.jar
~~~

Phân biệt:

| Trạng thái | Ý nghĩa |
|---|---|
| **Deprecated** | Vẫn có thể tồn tại, nhưng không nên tiếp tục dựa vào lâu dài |
| **Deprecated for removal** | Có kế hoạch loại trong tương lai, cần ưu tiên migration |
| **Removed** | Có thể gây lỗi compile/link/runtime ở release đã bỏ API |

**jdeprscan không thay thế dependency scanner của bên thứ ba**: phạm vi chính là những API deprecated thuộc Java SE.

Khi công cụ báo không tìm được class, sửa classpath trước khi đánh giá kết quả. Không coi thiếu dữ liệu là bằng chứng không có lỗi.

## 19. Strong encapsulation, modules và deep reflection

Một ứng dụng nguồn cũ có thể truy cập class hoặc field nội bộ JVM bằng reflection. Từ Java 9, module system và quá trình strong encapsulation của JDK làm những cách này ngày càng không phù hợp.

Một lỗi thường gặp:

~~~text
java.lang.reflect.InaccessibleObjectException
~~~

Cách xử lý theo thứ tự ưu tiên:

1. Xác định thư viện và stack trace gây reflection.
2. Nâng thư viện lên bản tương thích với runtime.
3. Dùng API public hoặc extension point được hỗ trợ.
4. Nếu thật sự không thể thay ngay, cân nhắc **--add-opens** hay **--add-exports** trong phạm vi hẹp, có lý do và thời hạn loại bỏ.
5. Kiểm tra lại trên runtime 27 và trong CI.

**Không khuyến nghị thiết kế mới dựa vào access nội bộ JDK**, ngay cả khi có flag tạm thời cho phép.

### Không nhầm exports và opens

- **exports** quyết định khả năng truy cập public types qua module boundary theo hợp đồng JPMS.
- **opens** liên quan quyền deep reflection vào package.

Chọn đúng cách và không mở rộng không cần thiết.

## 20. Final-field mutation warnings từ JDK 26 vẫn cần xử lý ở 27

Khi nâng từ Java 21/25 lên 27, cần lưu ý thay đổi ở **bản trung gian JDK 26**: JVM cảnh báo các thao tác **deep reflection thay đổi final instance fields**.

Ví dụ về hành vi cần điều tra:

~~~java
import java.lang.reflect.Field;

final class Config {
    final int retries = 3;
}

Field field = Config.class.getDeclaredField("retries");
field.setAccessible(true);
// Code cố gán vào final instance field qua reflection.
~~~

Đoạn trên minh họa rủi ro, **không phải cách chỉnh cấu hình được khuyên dùng**.

Để phát hiện trong môi trường kiểm thử:

~~~text
java --illegal-final-field-mutation=debug -jar app.jar
~~~

Có thể kiểm thử tính sẵn sàng cho hạn chế trong tương lai:

~~~text
java --illegal-final-field-mutation=deny -jar app.jar
~~~

**--enable-final-field-mutation** có thể được sử dụng có phạm vi khi chưa thể sửa thư viện, nhưng giải pháp dài hạn vẫn là **nâng cấp/thay thế thư viện gây deep reflection**.

Không ghi rằng final-field mutation warning là tính năng lần đầu xuất hiện trong 27: nó đã bắt đầu ở **JDK 26**. Java 27 là một môi trường cần tiếp tục kiểm thử.

## 21. Removed features và options của JDK 27

Bên cạnh chín JEP, release notes của JDK 27 liệt kê một số removals và thay đổi defaults. Những ví dụ liên quan migration:

| Thay đổi ở 27 | Nguy cơ | Kiểm tra |
|---|---|---|
| Loại bỏ **-noclassgc**, **-noverify**, **-verifyremote**, **-Xverify:none** | JVM startup thất bại nếu script dùng option đã bỏ | Audit startup flags |
| Loại bỏ **ThreadPoolExecutor.finalize()** | Code/lib lệ thuộc lifecycle cũ | Quản lý ExecutorService bằng shutdown/close rõ |
| Loại bỏ launch mechanism **VFORK** trên Linux | Process launcher tùy biến có thể bị ảnh hưởng | ProcessBuilder/OS tests |
| Loại bỏ system property **java.locale.useOldISOCodes** | Hành vi locale/mapping không còn như cấu hình cũ | Locale tests và loại property cũ |
| Một số **JNDI LDAP standard environment properties** không còn được đặt mặc định | LDAP integration có thể thay hành vi | Đặt cấu hình tường minh/test |
| Loại bỏ **JVM Compiler Interface (JVMCI)** | Compiler/tooling dùng giao diện này có thể gặp lỗi | Kiểm tra vendor/runtime và dependency |
| Loại bỏ các translation resources lỗi thời | Hiển thị i18n dùng resource cũ có thể đổi | So sánh golden outputs |

**Đây không phải danh sách mọi thay đổi.** Nếu nguồn là Java 17/21, phải xem thêm removals từ các release trước đó. Release notes của bản update JDK cụ thể còn có thể bổ sung bug fix và thay đổi bảo mật quan trọng.

Không dùng flag legacy khác để “vá” startup mà chưa hiểu ý nghĩa; ưu tiên bỏ cấu hình không còn hợp lệ và kiểm thử lại.

## 22. G1 mặc định trong mọi môi trường: JEP 523

JDK 27 chọn **Garbage-First (G1) GC** làm default trong mọi môi trường thuộc phạm vi tính năng, thay vì một số môi trường tài nguyên hạn chế trước đó được chọn Serial GC.

So sánh trước/sau trên cùng workload:

- GC pause distribution và p95/p99 latency.
- Successful throughput, CPU utilization và CPU throttling.
- Heap used/committed, allocation rate, native RSS.
- Memory footprint trong container ít RAM.
- Hành vi khi tải tăng đột biến và trong soak test.

Ví dụ bật GC log khi chẩn đoán:

~~~text
java -Xlog:gc* -jar app.jar
~~~

**Nếu ứng dụng đã cấu hình collector tường minh**, default GC mới không nhất thiết thay đổi collector đang chạy. Phải kiểm chứng GC thực tế.

Không chọn GC chỉ theo cảm tính: cùng một collector có thể khác hiệu quả giữa dịch vụ CPU-bound, bộ nhớ nhỏ, nhiều object ngắn hạn hoặc workload nhạy cảm tail latency.

## 23. Compact Object Headers mặc định: JEP 534

JDK 27 bật **Compact Object Headers** theo mặc định trong HotSpot ở những nền tảng được hỗ trợ. Trong cấu hình 64-bit phù hợp, bố cục object header có thể giảm từ kích thước thường gặp 96 bit xuống 64 bit theo JEP.

Kết quả có thể ảnh hưởng:

- Heap footprint và mật độ object.
- Cache locality.
- Allocation và GC behavior.
- Latency/throughput của workload nhiều object nhỏ.
- Một số agent/profiler hoặc native tooling phụ thuộc JVM internals.

**Không hứa mọi ứng dụng tiết kiệm một tỷ lệ RAM cố định.** Kết quả phụ thuộc object layout, alignment và dữ liệu thực.

Cách đánh giá:

1. Đo baseline runtime cũ cùng mức tải.
2. Đo JDK 27 với cấu hình mặc định.
3. Quan sát heap/GC/CPU/RSS.
4. Kiểm tra các native agents hoặc tools chuyên sâu.
5. Chỉ thay đổi cấu hình khi có bằng chứng.

Đây là thay đổi HotSpot runtime; không cần viết lại từng class Java để nhận được bố cục mới.

## 24. Hybrid post-quantum TLS 1.3: JEP 527

JDK 27 bổ sung **hybrid key exchange** cho TLS 1.3, kết hợp thuật toán truyền thống và cơ chế kháng lượng tử. Các ứng dụng sử dụng **javax.net.ssl/JSSE** có thể nhận lợi ích từ hỗ trợ này khi các bên thực sự thương lượng được thuật toán phù hợp.

Kiểm tra:

- TLS handshake với đúng upstream/downstream production.
- Proxy, load balancer, gateway, network appliance hỗ trợ.
- Certificate, truststore, keystore và security providers.
- TLS policy/compliance và lựa chọn cipher/key exchange.
- Handshake latency, CPU và kích thước trao đổi.
- Client hoặc server cũ không chấp nhận một số cấu hình.

**Không suy rằng mọi kết nối JDK 27 tự động dùng post-quantum hybrid**. Kết quả phụ thuộc hai đầu giao tiếp và chính sách cấu hình.

Nếu thư viện dùng OpenSSL/native TLS stack riêng, phải kiểm thử cơ chế đó độc lập thay vì suy ra mọi hành vi từ JSSE.

## 25. JFR In-Process Data Redaction: JEP 536

JDK 27 bổ sung redaction cho **một số dữ liệu nhạy cảm** ngay trong quá trình tạo JFR recordings. Theo release notes, JFR có chính sách mặc định xử lý **command-line arguments** và các giá trị khởi tạo của **environment variables/system properties**.

Đối với hệ thống theo dõi hiệu năng:

- Xem recording có che các trường đúng kỳ vọng không.
- Sửa parser/dashboard phụ thuộc vào giá trị bị che.
- Kiểm tra quyền truy cập recording, retention và nơi xuất dữ liệu.
- Không đặt credentials trong logs/JFR custom events mà không có kiểm soát.
- Không tắt redaction chỉ để sửa một dashboard mà bỏ qua an toàn dữ liệu.

**JFR redaction không chứng minh tất cả secret trong mọi custom event đã được loại bỏ.** Ứng dụng vẫn phải quản lý dữ liệu nhạy cảm trong logging/observability.

## 26. Locale, timezone và định dạng dữ liệu

Khi nâng qua nhiều release, dữ liệu **CLDR, timezone/tzdata, currency symbol, date/time format** và những lựa chọn i18n có thể thay đổi dù source API vẫn giống nhau.

Test những trường hợp:

- **DateTimeFormatter** theo locale và zone cụ thể.
- Các mốc daylight saving time và timezone lịch sử.
- Currency/display names và phân tách số.
- **Collator** hoặc sắp xếp chuỗi theo locale.
- Input/outputs phụ thuộc default locale/timezone.
- Property cũ **java.locale.useOldISOCodes** không còn áp dụng trong JDK 27.
- Snapshot tests chứa chuỗi format theo máy.

Ví dụ nên dùng timestamp máy-máy theo chuẩn tường minh:

~~~java
import java.time.Instant;
import java.time.format.DateTimeFormatter;

String stored = DateTimeFormatter.ISO_INSTANT.format(Instant.now());
~~~

Đối với hiển thị cho người dùng, xác định **Locale** và **ZoneId** theo yêu cầu, không phụ thuộc vào default của host nếu không có hợp đồng rõ.

Đừng lưu định dạng chỉ dành cho con người làm wire protocol khi cần độ ổn định qua nhiều phiên bản.

## 27. JNI, FFM, JVM agents và bytecode instrumentation

Ứng dụng gọi native code hoặc dùng công cụ phân tích JVM cần kiểm tra các lớp tương thích riêng:

| Thành phần | Rủi ro | Bằng chứng cần có |
|---|---|---|
| **JNI** | Native ABI, OS/CPU hoặc version library | Smoke/integration test trên target image |
| **Foreign Function & Memory (FFM)** | Native access policy, layout, pointer lifecycle | Test dùng FFM final API và cấu hình đúng |
| **APM/profiler agent** | JVM internals, sự kiện hoặc attach behavior khác | Compatibility list và staging test |
| **Bytecode transformer** | Chưa hiểu class-file major version 71 | Nâng ASM/Byte Buddy/tool tương ứng |
| **ORM/serializer** | Deep reflection, constructor/final-field restrictions | Round-trip data và diagnostics |
| **Native TLS provider** | Không dùng JSSE mặc định | TLS integration test riêng |

**FFM API đã final từ Java 22**, vì vậy nó là lựa chọn hiện hành khi cần thao tác native/off-heap. Tuy nhiên, thay JNI bằng FFM trong cùng đợt nâng runtime có thể mở rộng đáng kể phạm vi thay đổi. Nên xem đó là một dự án hiện đại hóa tách biệt, có benchmark và kiểm thử ABI.

**sun.misc.Unsafe** và các cách thao tác bộ nhớ JDK-internal không nên được sử dụng làm API mới. Ưu tiên **VarHandle**, FFM hoặc API Java SE chuẩn theo loại tác vụ.

## 28. Hệ thống nguồn rất cũ: đừng khôi phục cơ chế legacy

Đối với baseline từ Java 8/11/17, một số thành phần có thể **đã bị loại trước JDK 27**:

- Java Security Manager đã bị thay đổi/loại bỏ như một cơ chế sandbox thực dụng trên các release gần đây.
- Những module Java EE/CORBA từng đi kèm JDK 8 không còn trong Java SE hiện đại.
- Một số JVM flags, launcher tools và API nội bộ đời cũ không còn tồn tại.
- Các nguồn locale legacy đã được thay thế bằng dữ liệu CLDR.
- Một số hành vi reflective access từng hoạt động ở JDK cũ không còn được cho phép mặc định.
- Một số cơ chế finalization đã bị deprecated for removal và không nên làm nền tảng cho cleanup mới.

**Không khuyến nghị thiết kế mới dựa vào Security Manager, applet, Unsupported JDK internals hoặc finalization.** Với ứng dụng cần sandbox, quản lý tài nguyên, native memory hay security policy, hãy dùng các cơ chế hiện hành được hỗ trợ.

Mấu chốt của phép so sánh là xác định **release đầu tiên xuất hiện thay đổi**. Đừng gọi mọi lỗi khi chạy Java 27 là “breaking change của riêng Java 27”.

## 29. Kiểm tra JVM flags, startup scripts và container

Nhiều vấn đề xuất hiện trước khi ứng dụng nhận request.

Kiểm kê toàn bộ nơi cấu hình JVM:

- **JAVA_TOOL_OPTIONS**, **JDK_JAVA_OPTIONS**, launcher script.
- Dockerfile, ENTRYPOINT, Kubernetes manifests, Helm, system services.
- Application server và các file JVM options.
- **-javaagent** và native agent.
- GC, logging, memory limit, CPU quota.
- TLS/truststore và security properties.
- Gradle/Maven daemon JVM settings.

Lệnh xác minh môi trường:

~~~text
java -version
javac -version
java -XshowSettings:vm -version
~~~

Trong môi trường chẩn đoán được phép, có thể xem cấu hình JVM đang chạy bằng:

~~~text
jcmd <PID> VM.flags
~~~

Thay **<PID>** bằng process ID thật. Lệnh chẩn đoán có thể yêu cầu quyền thích hợp và output cần được xử lý theo chính sách bảo mật.

Nếu JVM báo không hiểu một startup option:

1. Tìm nguồn cấu hình thật sự thêm option đó.
2. Đối chiếu mục removed/deprecated options của đúng release.
3. Bỏ hoặc thay thế bằng cách đang được hỗ trợ, có mục đích rõ.
4. Chạy lại smoke test và so sánh metric.

**Không sao chép toàn bộ flags cũ vào JDK 27 mà không đánh giá từng flag.**

## 30. Kiểm thử behavior: build thành công là chưa đủ

Một chiến lược migration nên gồm:

1. **Unit tests**: kết quả và xử lý lỗi.
2. **Integration tests**: database, HTTP, queues, cache, filesystem.
3. **Serialization tests**: JSON, XML và binary formats đang dùng.
4. **Security/TLS tests**: authentication, certificates, truststore, providers.
5. **Reflection/ORM tests**: mapping, proxy, final-field warnings.
6. **Concurrency tests**: task cancellation, executor lifecycle, timeouts.
7. **Internationalization tests**: Locale, ZoneId, DST, currency.
8. **Performance tests**: p95/p99 latency, successful throughput, CPU, heap, GC, RSS.
9. **Startup/deployment tests**: JVM flags, container probes, resources.
10. **Rollback tests**: app/config cũ có thể quay lại khi cần.

Cần giữ dữ liệu và điều kiện chạy **càng giống baseline càng tốt**:

- Cùng request mix, payload sizes và dữ liệu thử.
- Cùng topology/instance count, CPU quota, RAM limit.
- Cùng retry/timeout/rate limit.
- Cùng cache warm-up và kết nối dependency.
- Chỉ thay từng nhóm biến số có chủ đích.

Nếu thay runtime, ORM, framework major version và database schema cùng lúc, khó xác định nguyên nhân khi có sự cố.

### Tests nào dễ bỏ sót?

- Một vài request thành công nhưng phần đuôi p99 chậm.
- Công việc nền không kết thúc khi shutdown.
- Locale test chỉ chạy trên máy của developer.
- Framework dùng reflection chỉ kích hoạt trong một luồng hiếm.
- Native agent chưa được load trong test environment.
- Dependency bị lỗi khi chạy trên kiến trúc ARM64 dù x64 vẫn ổn.

Chọn kịch bản theo những đường code và cấu hình **có thực trong production**.

## 31. Ví dụ Java chạy được từ baseline 17 để đo runtime

Đoạn ví dụ chỉ sử dụng những API có từ Java 17. Khi chạy trên những runtime khác nhau, nó in thông tin **JVM, GC, heap và CPU count**, giúp xác nhận môi trường thật.

Lưu ví dụ minh họa thành **UpgradeProbe.java**:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.util.List;

public final class UpgradeProbe {
    private UpgradeProbe() {}

    public static void main(String[] args) {
        Runtime.Version version = Runtime.version();

        System.out.println("javaFeature=" + version.feature());
        System.out.println(
                "runtimeVersion=" +
                System.getProperty("java.runtime.version"));
        System.out.println(
                "vmName=" + System.getProperty("java.vm.name"));
        System.out.println(
                "classVersion=" +
                System.getProperty("java.class.version"));

        List<GarbageCollectorMXBean> collectors =
                ManagementFactory.getGarbageCollectorMXBeans();

        for (GarbageCollectorMXBean collector : collectors) {
            System.out.println("gc=" + collector.getName());
        }

        MemoryMXBean memoryBean =
                ManagementFactory.getMemoryMXBean();

        MemoryUsage heap = memoryBean.getHeapMemoryUsage();

        System.out.println("heapUsedBytes=" + heap.getUsed());
        System.out.println("heapMaxBytes=" + heap.getMax());
        System.out.println(
                "availableProcessors=" +
                Runtime.getRuntime().availableProcessors());
    }
}
~~~

Biên dịch bằng JDK 27 nhưng giữ mức Java 17:

~~~text
javac --release 17 -encoding UTF-8 -d out UpgradeProbe.java
~~~

Chạy cùng artifact trên runtime baseline và runtime 27:

~~~text
java -cp out UpgradeProbe
~~~

Output phụ thuộc môi trường và thời điểm chạy, **không nên hardcode một giá trị heap/CPU làm kết quả đúng**. Khi chạy trên JDK 27, **javaFeature** thường là 27; danh sách collectors còn phụ thuộc cấu hình collector thật.

### Ví dụ giúp được gì?

- Xác định đang dùng JVM nào.
- Quan sát một số đặc điểm baseline và runtime đích.
- Ghi nhận collector và memory hints để so sánh.

### Ví dụ không chứng minh điều gì?

- Không biết mọi dependency đều tương thích.
- Không đo end-to-end latency hoặc TLS.
- Không kiểm tra mọi reflection path hoặc JNI library.
- Không xác định mọi class file bên trong application artifact.
- Không thay thế full integration/performance tests.

Hãy xem đây là **runtime probe**, không phải công cụ tự động chứng nhận migration.

## 32. Quy trình thực tế: từ Java 21 lên Java 27

Giả sử ứng dụng production đang ở Java 21 và vẫn muốn giữ Java 21 là mức tối thiểu trong giai đoạn đầu.

### Bước 1 — Chụp baseline

Ghi nhận:

~~~text
java -version
mvn -version
~~~

Thu thập build config, test reports, dependency tree, GC/latency/throughput baseline và cấu hình container.

### Bước 2 — Chạy binary cũ trên runtime 27

Dùng artifact hiện tại:

~~~text
java -jar app.jar
~~~

Chạy trên staging với runtime 27; theo dõi startup warnings, flags, reflection, TLS, database/driver, output và hiệu năng.

### Bước 3 — Kiểm kê rủi ro tĩnh

~~~text
jdeps --jdk-internals app.jar
jdeprscan --for-removal app.jar
~~~

Nếu tool báo thiếu type, cung cấp classpath/module path phù hợp. Đừng xem kết quả tĩnh là đầy đủ cho reflection động.

### Bước 4 — Build bằng JDK 27, giữ API baseline 21

~~~text
javac --release 21 -d out src/Example.java
~~~

Lệnh minh họa. Dự án thật nên dùng đúng compiler plugin trong Maven/Gradle. Kiểm thử build mới trên **runtime 21 và 27** nếu vẫn cam kết hỗ trợ cả hai.

### Bước 5 — Quyết định có nâng minimum Java lên 27 không

Nếu muốn dùng API final của Java 27, đánh giá lợi ích, thông báo minimum JDK mới, cập nhật CI/test matrix và release notes của sản phẩm. Preview/incubator nên được đánh giá tách biệt.

### Bước 6 — Canary và rollback

Triển khai một phần nhỏ, so sánh success rate, p95/p99, CPU, heap/GC/RSS và lỗi runtime với nhóm baseline. Chỉ mở rộng khi vượt qua tiêu chí acceptance.

Nếu đợt nâng cấp đi kèm thay đổi schema hoặc định dạng dữ liệu, rollback phải được thiết kế cho cả **dữ liệu**, không chỉ thay JDK.

## 33. Tiêu chí chấp nhận migration

Một ma trận minh họa:

| Nhóm | Điều kiện cần xác minh |
|---|---|
| **Startup** | Không còn lỗi option bị loại; service health checks đạt |
| **Source/binary** | Compile đúng release; không có class version mismatch |
| **Dependencies** | Framework, agent, driver và native libraries được kiểm chứng |
| **Functional** | Unit/integration/contract tests đạt |
| **Security** | TLS/auth/certificates/permissions hoạt động đúng |
| **Diagnostics** | Warnings final-field/native/reflection đã được xử lý |
| **Performance** | p95/p99 và successful throughput đạt SLO |
| **Memory** | Heap, GC, native RSS trong budget |
| **Observability** | Logs/JFR/metrics/traces đủ và không làm lộ secrets |
| **Rollback** | Có đường quay lại đã được kiểm thử |

Mỗi dự án cần ngưỡng và kịch bản cụ thể. Không có một con số CPU hoặc p99 duy nhất thích hợp cho mọi ứng dụng Java.

## 34. Bảng chẩn đoán những lỗi hay gặp

| Triệu chứng | Khả năng cần điều tra | Hướng xử lý |
|---|---|---|
| **UnsupportedClassVersionError** | Class compile cho Java mới hơn runtime | Xem major version, --release |
| **NoClassDefFoundError** | Thiếu class/module/dependency | Xem dependency tree và classpath |
| **NoSuchMethodError** | Binary mismatch giữa library versions | Đồng bộ versions/artifact |
| **IllegalAccessError** | Quyền truy cập/module boundaries | Xem exports và API public |
| **InaccessibleObjectException** | Deep reflection không được phép | Upgrade framework, giảm internals |
| JVM không nhận startup flag | Option đã bị loại | Audit config, bỏ legacy option |
| Warning về final field mutation | ORM/serializer/agent sửa final field qua reflection | Debug/JFR, nâng dependency |
| TLS handshake lỗi | Provider, certificates hoặc peer không phù hợp | Integration test security |
| Locale/timezone output khác | CLDR/tzdata/default locale thay đổi | Explicit Locale/ZoneId, golden tests |
| p99 hoặc GC thay đổi | GC defaults, object header, workload/config | GC logs/JFR, test có kiểm soát |
| Instrumentation fail | Bytecode agent không hỗ trợ classfile 71 | Nâng agent/bytecode tool |
| RSS tăng, heap ổn | Native/off-heap/process memory | NMT/OS/container metrics |
| CI khác local | JDK, plugin hoặc image khác | Lock toolchain và build environment |

**Tương quan không chứng minh nguyên nhân.** Một lỗi chỉ xuất hiện sau migration có thể đến từ dependency, OS, dữ liệu hoặc thay đổi cấu hình đi kèm.

## 35. Anti-pattern cần tránh

- Đổi **JDK, framework major version, database schema và kiến trúc concurrency cùng lúc** mà không có baseline.
- Build bằng JDK 27 rồi vô tình phát hành bytecode 27 cho thư viện còn hỗ trợ Java 17/21.
- Tắt warnings hoặc mở tràn lan package nội bộ JDK để che sự cố reflection.
- Sử dụng preview API trong production mà không kiểm soát phiên bản.
- Chỉ chạy unit tests rồi coi hệ thống tương thích.
- Chỉ đo throughput, không đo tail latency và error rate.
- Bỏ qua Java agents, annotation processors hoặc native libraries.
- Cho rằng mọi thay đổi từ Java 17 trở đi đều là thay đổi riêng của Java 27.
- Không đo locale/timezone hoặc TLS ở các môi trường thật.
- Không có rollback khi cập nhật runtime hoặc định dạng dữ liệu.
- Đặt yêu cầu tối thiểu Java mới mà không thông báo người dùng thư viện.

Migration hiệu quả thường **ít thay đổi cùng lúc, có bằng chứng trước/sau và có cơ chế dừng an toàn**.

## 36. Checklist đối chiếu Java nguồn với Java 27

- [ ] Xác nhận source/API baseline, build JDK, runtime JDK và vendor.
- [ ] Kiểm kê tất cả release trung gian giữa baseline và Java 27.
- [ ] Đọc JDK 27 Release Notes, Migration Guide và release notes trung gian.
- [ ] Tách source/binary/behavioral/operational compatibility.
- [ ] Quyết định có giữ minimum Java cũ không.
- [ ] Dùng javac --release đúng với API/bytecode được cam kết.
- [ ] Kiểm thử artifact trên mọi runtime còn được hỗ trợ.
- [ ] Kiểm tra classfile major version và multi-release JAR khi cần.
- [ ] Xác nhận Maven/Gradle, compiler plugins, test runner, CI toolchain.
- [ ] Inventory cả direct và transitive dependencies.
- [ ] Chạy jdeps --jdk-internals và đánh giá reflection động.
- [ ] Chạy jdeprscan, ưu tiên deprecated-for-removal.
- [ ] Kiểm tra final-field mutation warnings qua ORM/serializer.
- [ ] Xóa hoặc thay JVM startup flags đã bị loại.
- [ ] Đo GC/compact-header ảnh hưởng tới latency và memory.
- [ ] Test TLS 1.3, security providers và certificates.
- [ ] Đánh giá JFR redaction/observability và dữ liệu nhạy cảm.
- [ ] Test i18n/timezone, serialization và data contracts.
- [ ] Xác nhận native libraries, agents và bytecode tooling hỗ trợ 27.
- [ ] Không bật preview/incubator vô tình trong production.
- [ ] Chạy functional/integration/performance/soak và recovery tests.
- [ ] Có canary rollout, tiêu chí acceptance và rollback.
- [ ] Cập nhật release notes của sản phẩm và minimum supported Java.
- [ ] Ghi nhận evidence, owner và kết quả từng hạng mục.

## 37. Tài liệu chính thức để đối chiếu

Các nguồn nên dùng khi đánh giá Java 27:

- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): JEP, tính năng, removals và thay đổi hành vi của JDK 27.
- [JDK 27 Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html): GA và các update releases của nhánh 27.
- [Oracle JDK Migration Guide — Release 27](https://docs.oracle.com/en/java/javase/27/migrate/): hướng dẫn migration và khả năng tương thích.
- [Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html): các điểm thay đổi nổi bật trong 27.
- [Preparing for Migration](https://docs.oracle.com/en/java/javase/27/migrate/preparing-migration.html): chạy binary cũ, update dependencies, javac và jdeps.
- [Removed Tools and Components](https://docs.oracle.com/en/java/javase/27/migrate/removed-tools-components.html): các thành phần bị loại qua các bản Java.
- [Preparing for final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/27/migrate/preparing-final-field-mutation-restrictions.html): warnings, debug và giảm phụ thuộc deep reflection.
- [The javac Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): --release, --enable-preview và compilation.
- [The jdeps Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html): dependency và JDK internals.
- [The jdeprscan Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeprscan.html): Java SE deprecated API usage.
- [Preview Features — Java 27](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html): quy tắc preview.
- [OpenJDK JEP Index](https://openjdk.org/jeps/0): kiểm tra JEP và vòng đời đề xuất.

Khi triển khai, cần đọc **release notes của bản cập nhật JDK chính xác** sẽ đưa vào production, không chỉ release notes của JDK 27 GA.

## Kết luận

Đối chiếu thay đổi của Java 27 phải bắt đầu từ **phiên bản nguồn thật của dự án và hợp đồng tương thích đã công bố**. Ba lớp **source, binary, behavioral compatibility** cùng với khả năng vận hành quyết định ứng dụng đã sẵn sàng nâng cấp hay chưa.

JDK 27 mang những điểm đáng chú ý như **G1 mặc định trong mọi môi trường**, **Compact Object Headers mặc định**, **hybrid post-quantum key exchange cho TLS 1.3** và **JFR in-process data redaction**. Các preview/incubator trong 27 phải được dùng có chủ đích và không nên nhầm với API final. Nếu nguồn nằm trước Java 26, còn phải xét những thay đổi trung gian, gồm cảnh báo final-field mutation và các API/flags đã bị loại từ trước.

Quy trình bền vững là **xác nhận baseline → chạy binary cũ trên runtime 27 → kiểm kê dependencies và JDK internals → build đúng --release → kiểm thử chức năng, bảo mật và hiệu năng → canary và rollback**. Chỉ khi mỗi giai đoạn có bằng chứng tương ứng, nhóm phát triển mới có thể nói ứng dụng **tương thích Java 27**, thay vì chỉ nói rằng nó “đã build bằng JDK 27”.
