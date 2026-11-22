
# Kiểm chứng artifact trên JDK tối thiểu được hỗ trợ

Khi một thư viện hoặc ứng dụng công bố hỗ trợ Java từ một phiên bản tối thiểu, nhóm phát triển cần chứng minh artifact phát hành thực sự chạy được trên phiên bản đó. Việc biên dịch thành công bằng JDK mới hoặc đặt target bytecode ở mức cũ hơn chưa đủ để chứng minh khả năng tương thích.

Ví dụ, nhóm có thể build bằng JDK 21 nhưng cam kết hỗ trợ runtime Java 17. Compiler có thể tạo bytecode Java 17 và giới hạn API Java SE được phép tham chiếu, nhưng một dependency được biên dịch cho Java 21, một class được nạp động, một Java agent hoặc một native library vẫn có thể khiến ứng dụng thất bại trên Java 17.

Kiểm chứng phải được thực hiện trên **artifact cuối cùng đã đóng gói**, bằng **JDK tối thiểu thực sự được hỗ trợ**, trong môi trường có cấu hình gần với môi trường triển khai. Kết quả cần gắn với đúng file artifact, phiên bản JDK, dependency, hệ điều hành và kiến trúc đã thử nghiệm.

## 1. Xác định chính xác điều cần chứng minh

Trước khi chạy test, cần định nghĩa rõ tuyên bố tương thích của sản phẩm.

Ví dụ một thư viện công bố:

> Hỗ trợ runtime Java 17 trở lên.

Điều đó có nghĩa consumer có thể dùng artifact trên Java 17, nếu đáp ứng các điều kiện và dependency được công bố. Nó không tự động có nghĩa:

- Mọi phiên bản JDK 17 của mọi nhà cung cấp đều đã được kiểm thử.
- Build tool và plugin đều chạy được trên JDK 17.
- Mọi hệ điều hành và kiến trúc CPU đều được hỗ trợ.
- Mọi dependency tùy chọn hoặc plugin bên ngoài đều tương thích.
- Ứng dụng có thể dùng API chỉ xuất hiện từ Java 21 rồi vẫn chạy trên Java 17.
- Artifact được build bằng JDK 21 đương nhiên chạy trên Java 17.

Cần tách các khái niệm sau:

| Khái niệm | Câu hỏi cần trả lời |
|---|---|
| Build JDK | JDK nào chạy Gradle/Maven, compiler và plugin? |
| Compiler target | Mã nguồn được phép dùng cú pháp và API Java nào? |
| Bytecode target | Class file đầu ra tương thích với phiên bản Java nào? |
| Runtime baseline | JDK thấp nhất mà sản phẩm cam kết hỗ trợ là phiên bản nào? |
| Dependency baseline | Mọi dependency runtime có hỗ trợ cùng baseline không? |
| Environment baseline | OS, CPU, native library và cấu hình nào nằm trong phạm vi hỗ trợ? |
| Artifact identity | File nào đã được kiểm thử và có đúng là file được phát hành không? |

Một ma trận ví dụ:

| Thành phần | Giá trị |
|---|---|
| JDK dùng để build | 21 |
| Compiler/API release | 17 |
| Runtime tối thiểu công bố | 17 |
| Dependency runtime | Tất cả phải hỗ trợ Java 17 |
| Runtime kiểm chứng | JDK 17 |
| Runtime kiểm chứng bổ sung | JDK 21 |
| Artifact | Chính xác JAR/WAR/ZIP được đưa vào phát hành |

Nếu sản phẩm hỗ trợ nhiều nền tảng, cần mở rộng ma trận theo OS và CPU. Không nên gộp “Java 17” thành một kết quả chung khi native library hoặc hành vi hệ thống phụ thuộc nền tảng.

## 2. Vì sao target bytecode chưa đủ?

### 2.1. Bytecode chỉ là một phần của hợp đồng

Mỗi file class có major version. JVM chỉ nạp được class file nằm trong phạm vi phiên bản mà nó hỗ trợ. Một số mốc:

| Java | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Nếu class được biên dịch cho Java 21 được nạp trên JVM 17, ứng dụng có thể gặp:

~~~
java.lang.UnsupportedClassVersionError
~~~

Đặt target Java 17 cho source của ứng dụng chỉ điều chỉnh các class do compiler đó tạo ra. Nó không tự chuyển bytecode của dependency bên ngoài về Java 17.

Một ứng dụng có thể có:

- Class chính được biên dịch ở major version 61.
- Dependency A được biên dịch ở major version 61.
- Dependency B được biên dịch ở major version 65.
- Một plugin được tải từ thư mục mở rộng và cũng có major version 65.

JVM 17 vẫn có thể thất bại khi nạp dependency B hoặc plugin, dù các class còn lại đều ở major version 61.

### 2.2. API Java SE cũng cần đúng phiên bản

Một class có major version phù hợp vẫn có thể tham chiếu đến API chỉ tồn tại trên JDK mới hơn. Ví dụ, compiler mới có thể biên dịch một lời gọi API mới nếu chỉ giới hạn bytecode bằng target mà không giới hạn tập API.

Với JDK hiện đại, nên dùng `--release` để giới hạn đồng thời:

1. Quy tắc ngôn ngữ Java.
2. Tập API Java SE được phép tham chiếu.
3. Phiên bản bytecode đầu ra.

Ví dụ:

~~~
javac --release 17 -d out src/com/example/App.java
~~~

Tuy nhiên, `--release 17` chỉ kiểm soát phần compile được áp dụng. Nó không xác minh mọi dependency, reflection, class được sinh động, Java agent hay native library trong artifact cuối cùng.

### 2.3. Dependency có thể đặt baseline cao hơn ứng dụng

Giả sử ứng dụng được biên dịch với `--release 17`, nhưng một thư viện runtime yêu cầu Java 21. Ứng dụng vẫn có thể build thành công nếu compiler chỉ cần API của thư viện ở thời điểm compile và không kiểm tra mức Java tối thiểu của toàn bộ bytecode.

Khi chạy trên Java 17, class của thư viện có thể không được nạp. Vì vậy, baseline của sản phẩm bị giới hạn bởi thành phần runtime có yêu cầu Java cao nhất trong các đường chạy thực tế.

Cần kiểm tra cả dependency trực tiếp, bắc cầu, plugin và module được nạp động.

## 3. Cấu hình build để nhắm đến JDK tối thiểu

### 3.1. Gradle: tách build toolchain và target release

Một dự án có thể dùng JDK 21 để chạy quá trình build nhưng tạo bytecode tương thích Java 17:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Trong cấu hình này:

- Gradle chọn JDK 21 làm toolchain biên dịch.
- Compiler áp dụng giới hạn Java 17 cho source, API Java SE và bytecode.
- Các task biên dịch Java áp dụng cấu hình này, bao gồm cả test source nếu chúng cũng là task JavaCompile.

Phiên bản JDK chạy Gradle vẫn là một vấn đề riêng. Gradle Wrapper, plugin và convention plugin có thể yêu cầu JDK mới hơn baseline runtime của ứng dụng. Vì vậy, cần ghi riêng JDK chạy build và JDK chạy sản phẩm.

### 3.2. Chạy test bằng đúng JDK tối thiểu

Nếu chỉ build test bằng JDK 21 và chạy test trên JDK 21, ta chưa chứng minh runtime Java 17 hoạt động.

Có thể cấu hình Gradle test launcher để chạy test trên JDK 17:

~~~groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Cấu hình này cần JDK 17 có sẵn hoặc được toolchain provisioning cung cấp. Cần kiểm tra log để xác nhận JVM thực sự được dùng cho tiến trình test.

Với integration test, hãy bảo đảm test process đang chạy đúng artifact đã đóng gói. Một test chỉ gọi class trong source set hoặc output directory có thể bỏ qua lỗi đóng gói, thiếu resource hoặc dependency runtime.

### 3.3. Maven: compiler release và runtime test

Với Maven Compiler Plugin, có thể khai báo release mục tiêu:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Điều này giúp compiler áp dụng mức ngôn ngữ, API Java SE và bytecode của Java 17 khi dùng JDK phù hợp.

Để kiểm thử trên JDK 17, cần cấu hình môi trường hoặc Maven Toolchains/Surefire phù hợp để tiến trình test sử dụng JDK 17. Việc đặt compiler release không tự chuyển JVM chạy Maven hoặc forked test sang JDK 17.

### 3.4. Kiểm soát mọi compiler trong dự án

Dự án đa ngôn ngữ hoặc đa module cần kiểm tra riêng từng compiler:

- Java compiler: `options.release` hoặc compiler release.
- Kotlin compiler: JVM target và tập API/JDK được tham chiếu.
- Groovy compiler: target bytecode và runtime dependency.
- Scala compiler: target bytecode và phiên bản Scala hỗ trợ JDK.
- Code generator và annotation processor: JDK chạy processor và class file được tạo ra.

Không nên giả định một cấu hình JavaCompile tự áp dụng cho mọi compiler khác. Hãy kiểm tra output của từng module và test trên JDK tối thiểu.

## 4. Xác định đúng artifact cần kiểm chứng

Một trong những sai sót phổ biến là kiểm thử class trong thư mục build nhưng phát hành một JAR/WAR khác. Artifact có thể khác vì:

- Dependency được đóng gói hoặc loại trừ khác nhau.
- Resource không được copy.
- Manifest hoặc module descriptor khác.
- Class được relocate, shade hoặc transform.
- Plugin được đưa vào một thư mục riêng.
- Native library được đóng gói theo classifier hoặc platform.
- Executable JAR chứa dependency lồng nhau.
- Quá trình đóng gói tạo thêm metadata hoặc code sinh tự động.

Vì vậy, quy trình cần xác định artifact đầu ra chính xác, ví dụ:

~~~
build/libs/application-1.2.0.jar
~~~

Tạo checksum trước khi kiểm thử và ghi lại cùng báo cáo:

~~~
sha256sum build/libs/application-1.2.0.jar
~~~

Trên Windows có thể dùng:

~~~
Get-FileHash .\build\libs\application-1.2.0.jar -Algorithm SHA256
~~~

Sau khi test, đối chiếu checksum của file được kiểm thử với file chuẩn bị phát hành. Nếu artifact thay đổi sau kiểm thử, kết quả trước đó không còn chứng minh cho file mới.

### 4.1. Kiểm tra nội dung JAR/WAR

Liệt kê nội dung:

~~~
jar tf application.jar
~~~

Kiểm tra:

- Class ứng dụng.
- Resource cấu hình và file metadata.
- Dependency được đóng gói.
- Service provider trong `META-INF/services`.
- Module descriptor `module-info.class`.
- Manifest.
- Các file native như `.dll`, `.so`, `.dylib`.
- Các class hoặc resource được tạo trong quá trình build.

Với executable JAR dùng cơ chế nested JAR, cần xem cấu trúc đóng gói của framework. Một số công cụ phân tích bytecode không tự quét sâu tất cả JAR lồng nhau.

### 4.2. Kiểm tra phiên bản class file

Dùng `javap` để xem major version của class:

~~~
javap -verbose -classpath application.jar com.example.Application
~~~

Trong kết quả, tìm:

~~~
major version: 61
~~~

Major version 61 tương ứng Java 17. Cần kiểm tra các class quan trọng trong dependency, plugin và module nội bộ. Một class đại diện đạt major version 61 không chứng minh toàn bộ JAR đều đạt.

Nếu artifact có nhiều dependency, có thể trích xuất từng JAR rồi kiểm tra class file hoặc dùng công cụ phân tích bytecode phù hợp để lập báo cáo toàn bộ.

## 5. Kiểm tra dependency trên baseline

### 5.1. Xem dependency graph runtime

Với Gradle:

~~~
./gradlew dependencies --configuration runtimeClasspath
~~~

Để tìm lý do một dependency được chọn:

~~~
./gradlew dependencyInsight --dependency artifact-name --configuration runtimeClasspath
~~~

Với Maven:

~~~
mvn dependency:tree -Dscope=runtime
~~~

Ghi lại dependency trực tiếp và bắc cầu, bao gồm:

- Group, artifact và version.
- Scope/configuration.
- Phiên bản thực tế được resolve.
- Dependency bị loại trừ hoặc thay thế.
- Module hoặc plugin chỉ được nạp ở một môi trường.
- Dependency được cung cấp bên ngoài artifact.

### 5.2. Xác minh Java tối thiểu của từng dependency

Không phải dependency nào cũng khai báo rõ Java baseline trong metadata. Cần kiểm tra:

- Tài liệu yêu cầu Java của nhà phát hành.
- Release note và migration guide.
- Class file major version.
- API Java SE được tham chiếu.
- Native binary và platform classifier.
- Các dependency bắc cầu của chính thư viện đó.

Một thư viện có thể chứa class Java 17 nhưng một nhánh runtime chỉ được gọi trong chức năng hiếm lại tham chiếu API mới hơn. Do đó, phân tích tĩnh cần đi kèm kiểm thử.

### 5.3. Dùng jdeps để phân tích phụ thuộc

Ví dụ:

~~~
jdeps --recursive --class-path "lib/*" application.jar
~~~

Để xem dependency đến JDK internal API:

~~~
jdeps --jdk-internals --recursive application.jar
~~~

Với multi-release JAR, có thể chỉ định góc nhìn của runtime:

~~~
jdeps --multi-release 17 --recursive application.jar
~~~

Tùy cấu trúc đóng gói, classpath và module path cần được cung cấp chính xác. Công cụ không tự đảm bảo đã phân tích mọi class được nạp động hoặc mọi nested JAR.

### 5.4. API đã deprecated hoặc bị xóa

Chạy công cụ deprecation scan theo release mục tiêu:

~~~
jdeprscan --release 17 application.jar
~~~

Tập trung vào API dự kiến loại bỏ:

~~~
jdeprscan --release 17 --for-removal application.jar
~~~

Các kết quả này bổ sung cho kiểm tra baseline. API deprecated không nhất thiết khiến ứng dụng không chạy trên Java 17, nhưng có thể báo trước một migration cần thực hiện ở release sau.

## 6. Kiểm chứng Multi-Release JAR

Multi-Release JAR cho phép một thư viện đóng gói các phiên bản class khác nhau theo từng phiên bản Java. Các class nền nằm ở gốc JAR; class thay thế theo phiên bản nằm trong:

~~~
META-INF/versions/<N>/
~~~

Manifest cần khai báo:

~~~
Multi-Release: true
~~~

Ví dụ cấu trúc:

~~~
library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 17/
│       │   └── com/example/Feature.class
│       └── 21/
│           └── com/example/Feature.class
└── com/
    └── example/
        └── Feature.class
~~~

Khi chạy trên Java 17, JVM chọn class nền hoặc class trong thư mục phiên bản 17 theo quy tắc multi-release. Class trong thư mục 21 không được chọn bởi runtime Java 17.

Vì vậy, cần xác nhận:

1. Class nền tương thích với JDK tối thiểu.
2. Các class trong thư mục phiên bản được biên dịch cho đúng mức Java tương ứng.
3. Manifest khai báo Multi-Release đúng.
4. API giữa các phiên bản class giữ hợp đồng tương thích cần thiết.
5. Test trên JDK tối thiểu thực sự chọn đúng implementation nền.
6. Test trên JDK mới hơn xác nhận implementation theo phiên bản mới hoạt động.

Không được chỉ kiểm tra class trong `META-INF/versions/21` rồi kết luận JAR hỗ trợ Java 17. Cần xác minh đường chạy mà JVM 17 thực sự lựa chọn.

## 7. Chạy artifact trên JDK tối thiểu

Đây là bước xác minh trực tiếp quan trọng nhất. Dùng đúng file artifact đã xác định ở phần trước và chạy bằng JDK tối thiểu được hỗ trợ.

Trước tiên, xác nhận runtime:

~~~
java -version
~~~

Nếu có nhiều JDK trên máy, gọi đường dẫn executable cụ thể để tránh vô tình dùng bản Java mới hơn:

~~~
/opt/jdk-17/bin/java -version
/opt/jdk-17/bin/java -jar application.jar
~~~

Đối với Windows, dùng đường dẫn đến `java.exe` thuộc JDK 17 đã cài.

### 7.1. Kiểm tra khởi động

Xác nhận:

- JVM khởi động thành công.
- Main class được tìm thấy.
- Dependency và resource được nạp.
- Application context hoặc container khởi tạo thành công.
- Không có lỗi class version, missing class hoặc missing method.
- Agent và native library được nạp nếu cấu hình yêu cầu.
- Health check đạt trạng thái sẵn sàng.

Khởi động thành công mới chỉ chứng minh các thành phần được kích hoạt trong giai đoạn startup.

### 7.2. Kiểm tra chức năng

Chạy các luồng đại diện cho ứng dụng:

- API hoặc command chính.
- Truy cập database và message broker.
- Serialization/deserialization.
- Reflection, proxy và dependency injection.
- Plugin hoặc module nạp động.
- Scheduled job và background worker.
- Logging, metrics, tracing.
- Tích hợp native hoặc gọi tiến trình ngoài.

Đối với thư viện, tạo một consumer sample độc lập sử dụng artifact đã phát hành. Consumer nên được compile và chạy trên JDK tối thiểu để kiểm tra đúng cách mà người dùng thư viện tích hợp.

### 7.3. Kiểm tra shutdown và lỗi vận hành

Không dừng ở kiểm tra startup. Hãy xác nhận:

- Graceful shutdown.
- Hook giải phóng tài nguyên.
- Thread và executor được đóng.
- Connection pool được giải phóng.
- File, socket và native resource không bị rò rỉ.
- Ứng dụng có thể restart.
- Logging và diagnostics hoạt động trên runtime tối thiểu.

Một ứng dụng có thể khởi động tốt nhưng gặp lỗi khi đóng hoặc khi xử lý tải thực tế.

## 8. Kiểm thử trên đúng môi trường triển khai

JDK tối thiểu là một trục của ma trận. OS, CPU và image cũng có thể ảnh hưởng.

| Trục | Ví dụ cần kiểm tra |
|---|---|
| Java runtime | JDK 17, JDK 21 |
| Nhà cung cấp | Bản phân phối JDK được công bố hỗ trợ |
| OS | Linux, Windows, macOS nếu sản phẩm hỗ trợ |
| CPU | x86-64, ARM64 |
| Container | Base image, libc và thư viện hệ thống |
| Runtime config | JVM flags, environment variables, truststore |
| Dependency | Runtime classpath, plugin và native library |

Không nhất thiết mọi tổ hợp đều phải test nếu sản phẩm chỉ hỗ trợ một số môi trường cụ thể. Nhưng ma trận hỗ trợ phải được công bố rõ và CI phải kiểm tra các tổ hợp đại diện quan trọng.

### 8.1. Container test

Nên chạy artifact trong image có đúng JDK tối thiểu:

~~~
docker run --rm \
  -v "$PWD/build/libs/application.jar:/app/application.jar:ro" \
  -w /app \
  eclipse-temurin:17-jre \
  java -jar application.jar
~~~

Ví dụ trên minh họa Linux shell và image Java 17. Cần thay image, volume mount và lệnh theo hệ điều hành, kiến trúc và quy trình triển khai của dự án.

Nếu production dùng image tối giản, hãy test chính image đó. Một image JDK đầy đủ có thể chứa công cụ hoặc thư viện hệ thống mà image JRE/minimal không có.

### 8.2. Encoding, timezone và locale

Kiểm tra dữ liệu tiếng Việt, ngày giờ, timezone và filesystem trên môi trường đích. Nếu ứng dụng dựa vào mặc định của OS, kết quả có thể khác giữa máy phát triển và production.

Ưu tiên khai báo encoding và timezone rõ ràng trong code hoặc cấu hình. Ghi nhận giá trị mặc định runtime nếu ứng dụng cần dựa vào chúng.

### 8.3. TLS và chứng chỉ

JDK tối thiểu có thể có truststore, thuật toán bảo mật hoặc chính sách TLS khác với JDK mới. Cần kiểm tra kết nối tới database, API bên ngoài, broker và dịch vụ nội bộ.

Đừng chỉ kiểm tra HTTP không mã hóa hoặc mock server nếu production sử dụng TLS. Kiểm thử với chứng chỉ và truststore phù hợp môi trường triển khai.

## 9. Kiểm tra các thành phần có thể bị bỏ sót

### 9.1. Reflection và module access

Kiểm tra các luồng dùng `setAccessible`, `trySetAccessible`, MethodHandles, ORM, serializer và framework proxy. Chạy trên JDK tối thiểu để phát hiện lỗi như:

~~~
java.lang.reflect.InaccessibleObjectException
~~~

Ghi lại package/module cần mở nếu có. Không thêm quyền mở rộng tùy tiện chỉ để làm test qua.

### 9.2. Java agent

Nếu ứng dụng dùng `-javaagent`, hãy chạy chính agent đó trên JDK tối thiểu và xác nhận:

- Agent nạp thành công.
- Transformer hoạt động.
- Bytecode sau biến đổi vẫn hợp lệ.
- Các agent khác không xung đột thứ tự.
- Attach API hoạt động nếu sản phẩm cần dynamic attach.

### 9.3. Native library

Kiểm tra đúng binary được đóng gói và kiến trúc của môi trường. Với JNI/JNA/FFM, gọi ít nhất một luồng thật để xác nhận thư viện được nạp, symbol được resolve và dữ liệu truyền qua biên giới native đúng.

Nếu có binary riêng cho từng OS/CPU, cần test từng nền tảng nằm trong cam kết hỗ trợ.

### 9.4. Class loading và service provider

Kiểm tra service loader, plugin directory, module path, classpath và custom class loader. Một class có thể chỉ được nạp khi gọi một chức năng cụ thể nên startup test không phát hiện được.

## 10. Thiết kế CI để bảo vệ JDK tối thiểu

Một ma trận CI cơ bản có thể build một lần rồi kiểm thử artifact trên các runtime được hỗ trợ:

~~~mermaid
flowchart TD
    A["Checkout source"] --> B["Build bằng JDK build toolchain"]
    B --> C["Đóng gói artifact"]
    C --> D["Tạo checksum và lưu artifact"]
    D --> E["Test artifact trên JDK tối thiểu"]
    D --> F["Test artifact trên JDK mới hơn"]
    E --> G["Tổng hợp kết quả"]
    F --> G
    G --> H{"Tất cả runtime được hỗ trợ đạt?"}
    H -->|Có| I["Cho phép phát hành"]
    H -->|Không| J["Chặn phát hành và điều tra"]
~~~

Điểm quan trọng là các job runtime cần tải hoặc dùng cùng một artifact đã build, không tự build lại source bằng từng JDK rồi test các output khác nhau. Nếu mỗi job tạo artifact riêng, ta đang kiểm tra nhiều sản phẩm khác nhau và có thể bỏ lỡ sai lệch giữa build và release.

Ví dụ các bước:

1. Build artifact trên JDK build đã quy định.
2. Tạo SHA-256 và lưu artifact như một CI output bất biến.
3. Job JDK tối thiểu tải đúng artifact đó.
4. Xác minh checksum trước khi chạy.
5. Chạy smoke test, integration test và các kiểm tra nền tảng.
6. Job JDK mới hơn cũng tải cùng artifact.
7. Tổng hợp báo cáo theo phiên bản Java và môi trường.
8. Chỉ phát hành artifact đã qua các gate bắt buộc.

### 10.1. Ma trận runtime trong GitHub Actions

Có thể biểu diễn các phiên bản runtime bằng matrix:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    java: [17, 21]

steps:
  - uses: actions/setup-java@v4
    with:
      distribution: temurin
      java-version: ${{ matrix.java }}
  - name: Verify runtime
    run: java -version
  - name: Run artifact smoke tests
    run: ./scripts/test-artifact.sh build/libs/application.jar
~~~

Đây chỉ là khung minh họa. Nếu workflow build và test nằm ở job khác nhau, cần upload/download artifact và xác minh checksum. Đừng để bước test vô tình build lại JAR bằng JDK trong matrix.

### 10.2. Lưu bằng chứng kiểm chứng

Mỗi lần CI nên lưu:

- SHA-256 của artifact.
- Phiên bản đầy đủ của JDK và vendor.
- OS và kiến trúc runner.
- Dependency graph hoặc SBOM nếu có.
- Kết quả compiler lint, jdeprscan và jdeps.
- Log startup và test.
- Tham số JVM quan trọng.
- Phiên bản container image hoặc digest.
- Thời điểm chạy và commit nguồn.

Những thông tin này giúp nhóm xác định artifact nào đã được kiểm chứng và tái hiện lỗi sau khi phát hành.

## 11. Tiêu chí đạt và không đạt

### Đạt

Có thể kết luận artifact đạt baseline khi:

- Artifact đúng checksum được dùng trong kiểm thử.
- Runtime là đúng JDK tối thiểu được công bố.
- JVM nạp được toàn bộ class cần thiết trong các đường chạy đã kiểm tra.
- Dependency runtime hỗ trợ baseline.
- Không còn lỗi liên kết do API/class/module thiếu.
- Reflection, agent, plugin và native integration hoạt động trong phạm vi hỗ trợ.
- Các chức năng quan trọng và regression test đạt.
- OS/CPU/image nằm trong ma trận hỗ trợ đã công bố.
- Có log và bằng chứng gắn với artifact.

### Không đạt

Cần chặn phát hành hoặc ghi nhận blocker khi có các trường hợp như:

- `UnsupportedClassVersionError` từ class ứng dụng hoặc dependency.
- `NoSuchMethodError` hoặc `NoClassDefFoundError` trên baseline.
- API hoặc module cần thiết đã bị loại bỏ.
- Reflection bị chặn làm chức năng bắt buộc thất bại.
- Agent không nạp hoặc biến đổi bytecode không hợp lệ.
- Native library sai kiến trúc hoặc thiếu symbol.
- Test nghiệp vụ quan trọng thất bại.
- Artifact được test không trùng checksum với artifact chuẩn bị phát hành.

Nếu một chức năng tùy chọn không nằm trong phạm vi hỗ trợ, phải ghi rõ điều kiện và cách tắt. Không nên ghi nhận toàn bộ sản phẩm “hỗ trợ Java 17” nếu tính năng bắt buộc chỉ chạy từ Java 21.

## 12. Báo cáo kiểm chứng mẫu

Có thể sử dụng mẫu sau để ghi nhận kết quả:

| Trường | Giá trị |
|---|---|
| Product/version | application 1.2.0 |
| Artifact | application-1.2.0.jar |
| SHA-256 | checksum của file đã test |
| Build JDK | JDK 21, vendor và update |
| Compiler release | 17 |
| Runtime tested | JDK 17, vendor và update |
| OS/CPU | Linux x86-64 |
| Container image | Tên tag và digest |
| Dependency status | Đã kiểm tra runtime graph |
| Startup | PASS/FAIL |
| Integration tests | PASS/FAIL |
| Agent/reflection/native | PASS/FAIL/NOT USED |
| Known limitations | Các điều kiện chưa được hỗ trợ |
| Evidence | Link log, test report và artifact metadata |
| Decision | PASS/FAIL/BLOCKED |

Không ghi PASS nếu chưa thực hiện test trên baseline. Nếu một phần chưa kiểm tra, ghi NOT TESTED hoặc UNKNOWN và nêu rõ ảnh hưởng.

## 13. Checklist thực hiện

### Build và artifact

- [ ] Đã xác định JDK chạy build và compiler target.
- [ ] Đã dùng `--release` hoặc cấu hình tương đương cho baseline.
- [ ] Đã kiểm tra compiler của từng ngôn ngữ/module.
- [ ] Đã đóng gói artifact cuối cùng.
- [ ] Đã tạo checksum và lưu đúng artifact được kiểm thử.
- [ ] Đã kiểm tra manifest, resource, service provider, module descriptor và dependency đóng gói.
- [ ] Đã kiểm tra class file version của ứng dụng và dependency.

### Runtime tối thiểu

- [ ] Đã xác nhận `java -version` là JDK tối thiểu được hỗ trợ.
- [ ] Đã chạy chính artifact đã đóng gói.
- [ ] Đã kiểm tra startup và health check.
- [ ] Đã chạy chức năng chính và integration test.
- [ ] Đã kiểm tra shutdown, restart và giải phóng tài nguyên.
- [ ] Đã kiểm tra reflection, agent, plugin và native integration nếu có.
- [ ] Đã test trong OS/CPU/container nằm trong cam kết hỗ trợ.

### CI và bằng chứng

- [ ] Runtime matrix dùng cùng artifact và checksum.
- [ ] Không build lại artifact khác nhau trong từng runtime job khi mục tiêu là kiểm tra cùng một bản phát hành.
- [ ] Đã lưu log, test report và phiên bản JDK.
- [ ] Đã ghi rõ known limitations và phần chưa kiểm thử.
- [ ] Chỉ đánh dấu PASS khi các gate bắt buộc đã đạt.

## Kết luận

Kiểm chứng artifact trên JDK tối thiểu là bước xác nhận trực tiếp cho cam kết tương thích runtime. Compiler target và bytecode version tạo nền tảng, nhưng dependency, API Java SE, reflection, agent, native library, resource đóng gói và môi trường triển khai đều có thể làm artifact thất bại.

Hãy build artifact theo cấu hình đã quy định, định danh bằng checksum, sau đó chạy chính file đó trên JDK tối thiểu trong môi trường đại diện. Kết hợp kiểm tra tĩnh với startup, integration và hành vi thực tế; lưu bằng chứng theo artifact và runtime. Chỉ khi các điều kiện hỗ trợ đã công bố đều được kiểm chứng mới có cơ sở kết luận sản phẩm đáp ứng baseline.

