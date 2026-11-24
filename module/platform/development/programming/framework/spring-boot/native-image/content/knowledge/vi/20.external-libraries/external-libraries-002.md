# Xác định hỗ trợ native theo đúng phiên bản thư viện

## 1. Vì sao phải kiểm tra đúng phiên bản?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng **Spring AOT** rồi biên dịch thành **GraalVM Native Image** để đánh giá tính tương thích, thời gian khởi động, bộ nhớ, đóng gói container và vận hành. Một ứng dụng thường dùng nhiều thư viện ngoài: JSON, logging, database driver, cache client, HTTP client, telemetry, security, template engine và các starter Spring Boot. Khả năng chạy native phụ thuộc vào **phiên bản artifact thực sự được phân giải**, không chỉ tên thư viện.

Một thư viện có thể hỗ trợ native ở version mới nhưng thiếu metadata ở version cũ. Một release có thể hỗ trợ JDK hoặc Spring Framework nhất định, trong khi release khác đã đổi API, reflection behavior hoặc cách đóng gói tài nguyên. Ngoài ra, một dependency có thể chạy tốt trên JVM nhưng native build thất bại vì class/member/resource chỉ được truy cập động.

Do đó, câu hỏi “thư viện X có hỗ trợ Native Image không?” cần được cụ thể hóa thành:

- Artifact nào đang được dùng: group, artifact, version, classifier và scope?
- Version đó có được nhà phát hành xác nhận hỗ trợ GraalVM Native Image không?
- Metadata native được đóng gói trong JAR, lấy từ GraalVM Reachability Metadata Repository hay do ứng dụng tự cung cấp?
- Metadata đó có áp dụng cho version đang dùng và GraalVM/toolchain hiện tại không?
- Các tính năng mà ứng dụng thực sự sử dụng đã được kiểm thử trên native executable chưa?

Sau bài học, người học có thể:

1. Truy ra phiên bản thực tế của dependency trực tiếp và dependency bắc cầu.
2. Đọc bằng chứng native support từ tài liệu nhà phát hành, JAR và metadata repository.
3. Phân biệt “có metadata”, “đã được kiểm thử native” và “được nhà cung cấp hỗ trợ”.
4. Đánh giá rủi ro theo từng tính năng, không chỉ theo tên dependency.
5. Kiểm tra tương thích giữa thư viện, Spring Boot, Spring Framework, JDK, GraalVM và hệ điều hành đích.
6. Tạo compatibility ledger có bằng chứng, mức tin cậy và hành động tiếp theo.
7. Xác nhận kết luận bằng native build và test các đường chạy thực tế.

> **Nguyên tắc:** không gắn nhãn “native-compatible” cho một thư viện chỉ vì ứng dụng JVM chạy được, hoặc vì một version khác của thư viện đã có metadata. Kết luận phải gắn với đúng tọa độ artifact, version, toolchain và tính năng được kiểm thử.

## 2. Native compatibility gồm nhiều lớp bằng chứng

Không có một thuộc tính duy nhất trong POM hoặc tên artifact bảo đảm thư viện chạy native. Cần xem xét nhiều lớp:

| Lớp | Câu hỏi cần trả lời | Bằng chứng nên tìm |
| --- | --- | --- |
| Nhà phát hành | Vendor có công bố hỗ trợ Native Image cho release này không? | Compatibility matrix, release notes, tài liệu native chính thức. |
| Artifact | JAR đang dùng có chứa metadata native không? | `META-INF/native-image/`, reachability metadata, `native-image.properties`. |
| Metadata repository | Có cấu hình cho đúng tọa độ và version không? | GraalVM Reachability Metadata Repository và log plugin tải metadata. |
| Spring AOT | Thư viện có tích hợp Spring AOT hoặc cung cấp runtime hints không? | Hướng dẫn của vendor, Spring AOT integration, generated hints. |
| Toolchain | Version thư viện có tương thích JDK/GraalVM/Spring đang build không? | Version matrix và log native build. |
| Runtime feature | Những tính năng ứng dụng dùng có hoạt động trong native không? | Native integration tests, smoke tests, issue/known limitations. |
| Platform | Binary và native dependency có phù hợp OS/architecture/libc đích không? | Build image cho platform đích, kiểm tra shared libraries và container tests. |

Có ba kết luận thường bị nhầm:

- **Có metadata:** một số truy cập động đã được mô tả cho Native Image. Điều này chưa chứng minh mọi tính năng của thư viện hoạt động.
- **Đã build/test được:** một cấu hình và bộ test cụ thể đã chạy thành công. Điều này chưa đồng nghĩa vendor cam kết hỗ trợ mọi môi trường.
- **Được nhà phát hành hỗ trợ:** vendor công bố phạm vi hỗ trợ rõ ràng, thường kèm version/JDK/GraalVM matrix. Vẫn cần kiểm thử tích hợp trong ứng dụng thực tế.

Một thư viện có thể tương thích native dù không có file `META-INF/native-image` riêng nếu nó không cần truy cập động hoặc các truy cập đã được xử lý bởi framework/tooling. Ngược lại, một JAR có metadata vẫn có thể thiếu metadata cho feature chưa được mô tả.

## 3. Bắt đầu từ dependency graph thực tế

Trước khi tra cứu native support, phải xác định đúng dependency graph mà build sử dụng. Khai báo trong `pom.xml` hoặc `build.gradle` chưa đủ vì dependency management, exclusions, constraints, platform/BOM và transitive dependencies có thể thay đổi version cuối cùng.

### 3.1. Maven: xem cây dependency

Chạy từ thư mục project:

~~~bash
./mvnw dependency:tree
~~~

Để xem chi tiết các dependency và đường đi bắc cầu:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Lọc một thư viện cụ thể:

~~~bash
./mvnw dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

Kiểm tra các dependency bị conflict, omitted hoặc version được chọn. `dependency:tree` cho biết quan hệ phân giải; hãy lưu output cùng commit/build profile để người khác có thể tái lập.

Có thể xuất classpath runtime để tìm JAR thực tế:

~~~bash
./mvnw dependency:build-classpath \
  -DincludeScope=runtime \
  -Dmdep.outputFile=target/runtime-classpath.txt
~~~

Classpath này hữu ích để xác định đường dẫn artifact đã phân giải. Nếu dự án dùng profile Maven, chạy lệnh với cùng profile và properties như native build.

### 3.2. Gradle: xem runtimeClasspath

Xem cây dependency:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Xem vì sao một version được chọn:

~~~bash
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
~~~

Lặp lại với dependency cần kiểm tra. `dependencyInsight` giúp phát hiện version bị nâng/hạ bởi constraint, platform, force rule hoặc dependency bắc cầu.

Nếu ứng dụng có nhiều source set hoặc configuration, `runtimeClasspath` có thể chưa đại diện cho classpath native task. Xem task graph và cấu hình của `nativeCompile`; ghi rõ configuration mà native plugin sử dụng.

### 3.3. Kiểm tra đúng artifact, không chỉ đúng tên thư viện

Một thư viện có thể phát hành nhiều artifact:

- Core module và integration module.
- Starter và implementation module.
- JDBC driver và connection pool.
- JAR thuần Java và artifact có classifier/native binary riêng.
- Phiên bản community và enterprise.
- Module optional chỉ được tải khi bật một feature.

Metadata của `library-core` không mặc nhiên áp dụng cho `library-jdbc` hoặc `library-spring-boot-starter`. Hãy kiểm tra từng artifact xuất hiện trong dependency graph và xác định module thực sự được gọi trong runtime.

## 4. Tra cứu bằng chứng từ nhà phát hành

Ưu tiên tài liệu chính thức của nhà phát hành cho **đúng version**. Tìm các nội dung:

1. Native Image/GraalVM support statement.
2. Version compatibility matrix: JDK, Spring Boot, Spring Framework, GraalVM và OS.
3. Release notes cho version đang dùng và các version trung gian có thay đổi native support.
4. Hướng dẫn AOT, reflection/resource configuration hoặc plugin cần thiết.
5. Known limitations: dynamic class loading, scripting, JNI, runtime compilation, serialization, proxy, cryptography, filesystem hoặc networking.
6. Cách test chính thức: native test suite, sample app, container image hoặc CI job.

### 4.1. Đọc tuyên bố hỗ trợ có phạm vi

Một tuyên bố “supports GraalVM” có thể chỉ nói thư viện đã được thử với một GraalVM/JDK nhất định. Hãy tìm xem tuyên bố có chỉ rõ:

- Version thư viện tối thiểu hoặc dải version được hỗ trợ.
- GraalVM distribution và release.
- JDK version.
- Spring Boot/Spring Framework version.
- OS/architecture.
- Các module/feature nằm trong phạm vi.
- Có yêu cầu metadata riêng hoặc build profile không.

Nếu tài liệu chỉ nói “native-ready” mà không có version matrix, ghi nhận là **bằng chứng chưa đủ chi tiết** và xác minh bằng artifact/test. Không tự mở rộng tuyên bố đó sang tất cả version.

### 4.2. Kiểm tra release notes

Các thay đổi quan trọng có thể xuất hiện trong release notes:

- Bổ sung GraalVM reachability metadata.
- Thêm Spring `RuntimeHintsRegistrar` hoặc `@RegisterReflectionForBinding`.
- Thay đổi cách đọc resource hoặc load class.
- Thêm module hỗ trợ AOT.
- Loại bỏ API cũ hoặc nâng baseline JDK.
- Sửa lỗi chỉ xảy ra trong native executable.

Nếu version hiện tại chưa hỗ trợ, xác định version đầu tiên bổ sung hỗ trợ và kiểm tra các breaking changes khi nâng cấp. Không tự động chọn version mới nhất nếu nó không tương thích với Spring Boot/JDK đang dùng.

## 5. Kiểm tra metadata được đóng gói trong JAR

Một thư viện có thể phân phối reachability metadata ngay trong artifact. Vị trí thường gặp:

~~~text
some-library-2.4.0.jar
├── com/vendor/library/...
└── META-INF/
    └── native-image/
        └── com.vendor/
            └── some-library/
                ├── reachability-metadata.json
                └── native-image.properties
~~~

Cấu trúc thư mục con có thể khác giữa artifact; điểm quan trọng là metadata nằm dưới `META-INF/native-image/` ở root của classpath entry theo định dạng Native Image hỗ trợ.

### 5.1. Liệt kê nội dung JAR

Sau khi xác định đường dẫn JAR trong dependency classpath:

~~~bash
jar tf /path/to/some-library-2.4.0.jar
~~~

Lọc phần metadata:

~~~bash
jar tf /path/to/some-library-2.4.0.jar | grep 'META-INF/native-image/'
~~~

Nếu dùng PowerShell, có thể thay `grep` bằng `Select-String`. `/path/to/...` chỉ là placeholder; thay bằng đường dẫn JAR thực tế đã phân giải.

### 5.2. Kiểm tra nội dung metadata

Nếu có `reachability-metadata.json`, đọc file để biết nó mô tả gì:

- Reflection: class, constructor, method, field và mức truy cập.
- Resources: pattern hoặc resource cụ thể.
- Dynamic proxy: tổ hợp interface.
- Serialization: kiểu được hỗ trợ.
- JNI: class/member được truy cập từ native code.
- Resource bundles: bundle cần được đóng gói.
- Condition/version: phạm vi áp dụng nếu schema hỗ trợ điều kiện.

Không kết luận “đã hỗ trợ native hoàn toàn” chỉ vì thấy file JSON. Kiểm tra metadata có đúng class/member mà feature của ứng dụng dùng hay không. Một file có thể chỉ bao phủ một phần thư viện hoặc chỉ một integration module.

### 5.3. Kiểm tra native-image.properties

Một dependency có thể chứa:

~~~properties
Args = --some-native-image-option
~~~

File này có thể bổ sung Native Image build arguments cho artifact. Đọc kỹ từng argument vì một tùy chọn trong dependency có thể ảnh hưởng mọi ứng dụng tiêu thụ nó. Nếu metadata yêu cầu flag toàn cục, ghi nhận rõ nguồn cấu hình và xác minh flag còn hợp lệ trong GraalVM version đang dùng.

Không sao chép file metadata từ một version JAR khác rồi cho rằng nó tương thích. Cấu hình có thể dùng tên class/member đã thay đổi hoặc schema không được GraalVM hiện tại chấp nhận.

### 5.4. Spring Boot executable JAR có nested dependencies

JAR do Spring Boot repackage thường có cấu trúc:

~~~text
application.jar
├── META-INF/
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    └── lib/
        ├── some-library-2.4.0.jar
        └── another-library-1.8.0.jar
~~~

Lệnh `jar tf application.jar` chỉ cho biết các nested JAR tồn tại. Nó không tự hiển thị toàn bộ nội dung `META-INF/native-image` bên trong từng dependency JAR.

Có thể trích một nested JAR ra file tạm rồi kiểm tra riêng:

~~~bash
unzip -p application.jar BOOT-INF/lib/some-library-2.4.0.jar \
  > target/some-library-2.4.0.jar

jar tf target/some-library-2.4.0.jar | grep 'META-INF/native-image/'
~~~

Trên Windows, dùng công cụ ZIP tương ứng hoặc PowerShell để trích nested JAR. Với native compilation tích hợp Spring Boot, plugin cần chuẩn bị classpath phù hợp; hãy kiểm tra log native task và output AOT thay vì suy luận từ archive listing đơn lẻ.

## 6. Tra cứu GraalVM Reachability Metadata Repository

Không phải thư viện nào cũng phát hành metadata native trong chính JAR. **GraalVM Reachability Metadata Repository** là kho metadata do cộng đồng duy trì cho một số thư viện bên thứ ba. Kho này có thể bổ sung cấu hình reflection, resource, proxy, serialization hoặc JNI cho các artifact/version được liệt kê.

Trang dự án:

- [GraalVM Reachability Metadata Repository](https://github.com/oracle/graalvm-reachability-metadata)

Khi tra cứu:

1. Tìm đúng groupId và artifactId.
2. Kiểm tra version hoặc version range mà metadata áp dụng.
3. Xem các loại metadata được cung cấp.
4. Đọc ghi chú, điều kiện và test nếu có.
5. Xác nhận Native Build Tools version của dự án có tích hợp/được cấu hình để sử dụng repository theo cách đang giả định.
6. Kiểm tra log build để biết metadata đã được lấy và đưa vào native analysis chưa.

Metadata repository không phải registry chứa mọi thư viện Java. Không tìm thấy entry **không chứng minh** thư viện không tương thích; nó chỉ có nghĩa chưa có bằng chứng metadata từ repository cho artifact đó. Thư viện có thể không cần metadata, tự đóng gói metadata trong JAR, dùng Spring hints hoặc chưa được cộng đồng bổ sung.

### 6.1. Version range cần được đọc cẩn thận

Một entry metadata có thể áp dụng cho một dải version, không nhất thiết chỉ một version duy nhất. Hãy đọc điều kiện version mà repository công bố. Không tự suy luận rằng metadata của `2.3.x` luôn an toàn cho `2.4.x`, hoặc metadata của version mới luôn tương thích với version cũ.

Nếu dependency được nâng version nhưng metadata repository chưa cập nhật, native build có thể:
- Không áp dụng metadata vì version nằm ngoài dải.
- Áp dụng metadata nhưng tên class/member đã thay đổi.
- Build thành công nhưng thiếu cấu hình cho feature mới.
- Báo lỗi schema hoặc option không còn được hỗ trợ.

### 6.2. Xác nhận plugin thực sự sử dụng metadata

Native Build Tools có thể tích hợp với reachability metadata repository tùy version và cấu hình. Đừng chỉ thấy repository có entry rồi mặc định plugin đã tải nó. Xác nhận:

- Version GraalVM Native Build Tools Maven/Gradle đang dùng.
- Cấu hình repository/metadata trong plugin theo tài liệu của version đó.
- Log tải metadata hoặc các configuration files được đưa vào native build.
- Kết quả khi chạy feature tương ứng trong native executable.

Nếu plugin version không tự động dùng repository, cần cấu hình theo tài liệu hoặc đưa metadata vào project theo cách được hỗ trợ. Tránh tải file thủ công rồi thêm flag tùy tiện mà không lưu nguồn/version của metadata.

## 7. Kiểm tra Spring AOT và tích hợp của thư viện

Đối với ứng dụng Spring Boot, thư viện có thể hỗ trợ native thông qua:

- Spring `RuntimeHintsRegistrar`.
- Annotation như `@RegisterReflectionForBinding`.
- Spring AOT contribution hoặc integration module.
- GraalVM reachability metadata đóng gói trong JAR.
- Metadata từ Reachability Metadata Repository.
- Cấu hình do ứng dụng bổ sung khi thư viện chưa cung cấp đủ.

### 7.1. Xác định nguồn hints

Nếu thư viện có Spring integration, kiểm tra tài liệu xem nó tự đăng ký hints hay cần import cấu hình. Một số hints chỉ được phát hiện khi auto-configuration hoặc bean configuration tương ứng có mặt trong application context được AOT xử lý.

Nếu thư viện chỉ cung cấp một registrar nhưng application context không import/scan cấu hình liên quan, registrar có thể không được gọi. Xác minh bằng AOT output, build log hoặc test `RuntimeHintsPredicates`.

### 7.2. Phân biệt metadata thư viện và metadata ứng dụng

Metadata trong dependency JAR mô tả nhu cầu của thư viện. Runtime hints do ứng dụng khai báo mô tả những truy cập động riêng của ứng dụng hoặc phần tích hợp mà thư viện không thể biết.

Ví dụ: thư viện JSON đã có metadata cho các class nội bộ, nhưng ứng dụng gửi một subtype `PaymentPlugin` được chọn từ property. Ứng dụng vẫn phải bảo đảm subtype của chính nó được reach và có constructor/member cần thiết. Không chờ metadata của thư viện bên ngoài tự đoán class nghiệp vụ của ứng dụng.

### 7.3. Không thêm hints quá rộng để che thiếu hỗ trợ

Nếu thư viện thiếu metadata, tìm đúng thao tác gây lỗi:
- Reflection trên class nào?
- Constructor/method/field nào được gọi?
- Resource path nào được đọc?
- Proxy gồm interface nào?
- Serialization type nào được dùng?
- JNI library nào được load?

Bổ sung hints tối thiểu cho các điểm đó, rồi ghi rõ đây là metadata do ứng dụng duy trì. Không đăng ký toàn bộ package hoặc toàn bộ member nếu chưa có lý do.

## 8. Kiểm tra các phụ thuộc đặc biệt

Một số nhóm thư viện có rủi ro native riêng, cần kiểm tra sâu hơn ngoài reflection metadata.

| Nhóm thư viện | Những điểm cần xác minh |
| --- | --- |
| JDBC/database driver | Driver class loading, service provider, JNI/native transport, TLS/certificate, DNS và database integration tests. |
| Logging | Service loader, resource bundles, config file, plugin discovery, appender native dependency. |
| JSON/XML/serialization | DTO constructors, reflection, generic signatures, subtype registration, resource/schema và custom serializer. |
| ORM/data access | Entity introspection, proxy/lazy loading, bytecode enhancement, JDBC driver và query path. |
| Cache/message broker | Client transport, Netty/native transport, TLS, DNS, compression, serializer và connection lifecycle. |
| HTTP client | TLS provider, proxy configuration, DNS resolver, native transport, service loading và resource certificates. |
| Metrics/tracing | Service loader, reflection, runtime instrumentation, exporters, native libraries và shutdown hooks. |
| Scripting/expression engine | Runtime compilation, dynamic class loading, bytecode generation và script engine. |
| Image/document/PDF processing | JNI, codecs, fonts, resource files, native binary và OS packages. |
| Cryptography | Provider discovery, native crypto library, entropy source, certificate store và FIPS/provider constraints. |

Ví dụ, một JDBC driver có thể có metadata reflection đầy đủ nhưng vẫn phụ thuộc native library cho transport. Ngược lại, driver thuần Java có thể build được nhưng cần service provider/resource metadata để tự đăng ký. Kiểm tra feature thật thay vì gán nhãn chung cho toàn bộ nhóm.

## 9. Xây dựng compatibility matrix cho đúng toolchain

Một thư viện chỉ có ý nghĩa native support trong một tổ hợp môi trường cụ thể. Ghi lại tối thiểu:

| Thành phần | Thông tin cần chốt |
| --- | --- |
| Spring Boot | Version chính xác và BOM/platform đang quản lý dependency. |
| Spring Framework | Version thực tế được Spring Boot kéo vào. |
| JDK | Vendor, major version và toolchain được dùng để build. |
| GraalVM | Distribution, release, `native-image --version`. |
| Native Build Tools | Maven/Gradle plugin version và cấu hình metadata repository. |
| Thư viện ngoài | GroupId, artifactId, version, classifier, scope. |
| OS/architecture | OS, CPU architecture, libc/base image nếu liên quan. |
| Build mode | Native compile trực tiếp hay Buildpacks/container builder. |
| Feature coverage | Những API/feature của thư viện đã chạy trong native tests. |

### 9.1. Lấy version từ toolchain thực tế

Có thể ghi lại:

~~~bash
java -version
native-image --version
./mvnw -version
./gradlew --version
~~~

Các lệnh này cho biết môi trường shell. Plugin có thể dùng toolchain được cấu hình riêng, vì vậy hãy kiểm tra log native build để xác nhận JDK/GraalVM mà plugin thực sự gọi.

### 9.2. Phân biệt build host và target runtime

Native executable thường gắn với OS/architecture và các native libraries mà nó được build cho. Một build thành công trên Linux x86_64 không chứng minh executable chạy trên Linux ARM64, Windows hoặc Alpine/musl.

Nếu deploy bằng container, xác minh:
- Builder image và runtime image có tương thích không.
- OS/architecture của executable khớp image đích.
- glibc/musl và shared libraries cần thiết có mặt.
- Native library của dependency được đóng gói và load đúng.
- TLS certificate, timezone data, font, codec hoặc file hệ thống có sẵn.

## 10. Kiểm chứng theo tính năng, không chỉ theo dependency

Sau khi thu thập bằng chứng tài liệu và metadata, phải chạy thử các đường đi mà ứng dụng thực sự sử dụng. Một thư viện có thể chỉ dùng được một phần trong native mode.

### 10.1. Xác định feature inventory

Với mỗi dependency, ghi:

1. Các API được gọi trực tiếp.
2. Feature được kích hoạt qua cấu hình hoặc auto-configuration.
3. Đường truy cập động: reflection, resource, proxy, serialization, service loader, JNI.
4. Các module optional được bật.
5. Những profile hoặc deployment environment làm thay đổi feature.
6. Các integration point bên ngoài: database, broker, HTTP service, file system.

Không cần kiểm thử mọi API công khai của thư viện; cần kiểm thử toàn bộ feature mà ứng dụng phụ thuộc vào.

### 10.2. Dùng JVM làm baseline

Chạy cùng bộ test trên JVM trước. Lưu JSON fixtures, input, environment variables, cấu hình và kết quả mong đợi. Khi native test fail, baseline giúp phân biệt:
- Lỗi logic/dữ liệu đã có trên JVM.
- Khác biệt do type erasure hoặc cấu hình generic.
- Thiếu reflection/resource/proxy metadata.
- Lỗi native library, linker hoặc OS.
- Lỗi do khác profile/configuration.

### 10.3. Native smoke và integration tests

Với mỗi dependency quan trọng, có ít nhất một test native chạy qua feature chính. Ví dụ:

- JSON: bind DTO, generic collection, custom serializer và subtype.
- JDBC: load driver, mở kết nối, query, transaction và close.
- HTTP client: TLS, DNS, proxy và request/response.
- Logging: load cấu hình, service provider, ghi log và shutdown.
- ORM: khởi tạo context, query entity, proxy/lazy loading nếu được dùng.
- Broker: connect, publish, consume, retry và graceful shutdown.

Native build pass chỉ chứng minh compilation hoàn tất. Native smoke test pass chỉ chứng minh các đường đã chạy hoạt động trong điều kiện test. Ghi rõ phần chưa được kiểm chứng.

### 10.4. Native Image tracing agent là bằng chứng bổ trợ

Tracing agent có thể ghi nhận reflection/resource/proxy/serialization access trong những scenario JVM đã chạy và tạo metadata gợi ý. Dùng nó để tìm điểm truy cập bị bỏ sót, nhưng cần nhớ:

- Luồng chưa chạy sẽ không xuất hiện trong output.
- Agent có thể tạo metadata rộng hơn nhu cầu thật.
- Metadata sinh ra cần review, kiểm tra version/schema và chuyển vào đúng vị trí được hỗ trợ.
- Agent không chứng minh vendor hỗ trợ thư viện hoặc mọi feature native.

Dùng tracing agent cùng tài liệu vendor, metadata có sẵn, unit tests và native integration tests.

## 11. Phân loại kết quả và quyết định sử dụng

Có thể dùng các trạng thái sau trong compatibility ledger:

| Trạng thái | Ý nghĩa | Hành động |
| --- | --- | --- |
| Vendor-supported | Nhà phát hành xác nhận hỗ trợ đúng version/toolchain trong phạm vi cụ thể. | Kiểm tra version matrix và chạy test tích hợp ứng dụng. |
| Metadata-present | Có metadata trong JAR hoặc repository phù hợp với version. | Xác nhận plugin sử dụng metadata và test feature. |
| Tested-in-project | Native build và các feature test của ứng dụng đã pass. | Ghi lại cấu hình, platform và phạm vi test. |
| Partial | Chỉ một số module/feature chạy native hoặc có giới hạn được biết. | Chỉ bật phần đã kiểm thử; cô lập hoặc thay thế feature còn thiếu. |
| Unknown | Chưa có bằng chứng đủ tin cậy cho đúng version. | Tạo spike/test nhỏ, hỏi vendor hoặc kiểm tra metadata. |
| Incompatible | Có bằng chứng lỗi hoặc vendor tuyên bố không hỗ trợ tổ hợp này. | Nâng version, cấu hình bổ sung, thay thế dependency hoặc dùng JVM mode. |

Không biến trạng thái `Unknown` thành `Incompatible`. Thiếu metadata trong repository không phải bằng chứng chắc chắn rằng thư viện không chạy native. Ngược lại, metadata tồn tại cũng không đủ để nâng trạng thái thành `Vendor-supported`.

### 11.1. Ví dụ bảng đánh giá

| Dependency | Version phân giải | Bằng chứng | Feature đã test | Trạng thái |
| --- | --- | --- | --- | --- |
| JSON library | Version thực tế từ dependency tree | Vendor docs + metadata JAR | DTO, generic list, subtype | Tested-in-project |
| JDBC driver | Version thực tế từ BOM | Vendor matrix | Connect/query/transaction | Vendor-supported + tested |
| Image codec | Version thực tế | Không thấy metadata; có JNI | Decode PNG/JPEG trong native | Unknown |
| Scripting engine | Version thực tế | Tài liệu nêu runtime compiler | Evaluate script | Incompatible hoặc Partial theo test/vendor scope |

Các dòng trên chỉ minh họa cách ghi; không phải kết luận cho một thư viện cụ thể. Khi dùng trong dự án, thay bằng artifact/version và bằng chứng thật.

## 12. Ghi lại compatibility ledger có thể tái lập

Một bảng ledger tốt nên có các cột:

~~~text
groupId
artifactId
versionResolved
classifier
scope
directOrTransitive
introducedBy
vendorNativeStatement
vendorDocsUrl
jarMetadataPresent
metadataRepositoryEntry
metadataVersionRange
springAotIntegration
graalvmVersion
jdkVersion
nativeBuildPluginVersion
targetOS
targetArchitecture
featuresUsed
nativeTests
knownLimitations
status
owner
lastVerifiedCommit
verifiedAt
nextAction
~~~

Ghi URL và release note cụ thể, không chỉ tên trang tài liệu chung. Lưu output `dependency:tree` hoặc `dependencyInsight` cùng commit. Khi nâng dependency hoặc GraalVM, đánh giá lại những dòng có thay đổi version hoặc phạm vi hỗ trợ.

### 12.1. Khi nào cần kiểm tra lại?

Tạo lại đánh giá khi:
- Nâng Spring Boot BOM hoặc Spring Framework.
- Nâng version thư viện trực tiếp/bắc cầu.
- Nâng GraalVM/JDK hoặc Native Build Tools.
- Đổi base image, OS, CPU architecture hoặc libc.
- Bật thêm module/feature mới.
- Thay đổi serializer, transport, TLS provider hoặc native dependency.
- Metadata repository cập nhật version range hoặc sửa metadata.

Không tái sử dụng kết quả cũ nếu dependency graph hoặc toolchain đã thay đổi đáng kể.

## 13. Bài thực hành: kiểm toán native support cho dependency graph

**Bối cảnh:** một dịch vụ Spring Boot dùng JSON, JDBC, HTTP client, logging và telemetry. Ứng dụng JVM hoạt động, nhưng nhóm chưa biết version nào trong dependency graph có native metadata hoặc feature nào cần cấu hình bổ sung.

### Nhiệm vụ

1. Chạy `dependency:tree -Dverbose` hoặc `dependencies --configuration runtimeClasspath` và lưu dependency graph.
2. Chọn ít nhất năm dependency quan trọng, gồm một dependency bắc cầu và một dependency có khả năng dùng JNI/native library.
3. Ghi groupId, artifactId, version, classifier và scope được phân giải.
4. Tra tài liệu nhà phát hành và release notes cho đúng version; lưu JDK/Spring/GraalVM compatibility matrix nếu có.
5. Kiểm tra từng JAR tại `META-INF/native-image/`; đọc metadata và ghi loại truy cập được mô tả.
6. Tra GraalVM Reachability Metadata Repository; xác nhận version range và Native Build Tools có thực sự sử dụng entry.
7. Xác định Spring AOT integration, runtime hints hoặc metadata do ứng dụng cần bổ sung.
8. Chốt GraalVM/JDK/plugin version và platform đích.
9. Viết native smoke/integration tests cho feature thực tế của từng dependency quan trọng.
10. Phân loại từng dependency theo trạng thái Vendor-supported, Metadata-present, Tested-in-project, Partial, Unknown hoặc Incompatible.
11. Tạo compatibility ledger, ghi rõ bằng chứng và việc cần làm trước khi phát hành.

### Hồ sơ kết quả

| Bằng chứng | Nội dung cần lưu |
| --- | --- |
| Dependency graph | Output Maven/Gradle và commit tương ứng. |
| Artifact identity | Group, artifact, version, classifier, scope. |
| Vendor support | URL tài liệu, release note và phạm vi version/platform. |
| JAR metadata | File list, nội dung và loại hints. |
| Repository metadata | Entry, version range và bằng chứng plugin đã dùng. |
| Toolchain | JDK, GraalVM, Native Build Tools, Spring Boot. |
| Feature inventory | API/feature thật sự được ứng dụng sử dụng. |
| Native tests | Lệnh chạy, test report, OS/architecture và kết quả. |
| Known limitations | Feature chưa hỗ trợ, workaround và rủi ro còn lại. |
| Decision | Trạng thái, owner, ngày xác minh và next action. |

### Tiêu chí hoàn thành

- [ ] Truy ra đúng version thực tế của dependency trực tiếp và bắc cầu.
- [ ] Phân biệt artifact có metadata với artifact được vendor hỗ trợ native.
- [ ] Kiểm tra metadata JAR và repository theo đúng version range.
- [ ] Xác nhận Native Build Tools thực sự sử dụng metadata dự kiến.
- [ ] Có compatibility matrix cho JDK, Spring Boot, GraalVM, plugin và platform.
- [ ] Native tests bao phủ feature quan trọng của dependency.
- [ ] Ledger ghi bằng chứng, trạng thái, giới hạn và next action.
- [ ] Không kết luận incompatible chỉ vì repository không có metadata.

## 14. Câu hỏi tự đánh giá

1. Vì sao khai báo dependency trong `pom.xml` chưa đủ để xác định version mà native build sử dụng?
2. Metadata trong JAR của `library-core` có tự áp dụng cho `library-jdbc` không?
3. Khác nhau giữa `Metadata-present`, `Vendor-supported` và `Tested-in-project` là gì?
4. Vì sao không tìm thấy dependency trong GraalVM Reachability Metadata Repository chưa chứng minh dependency không tương thích?
5. Khi nào cần kiểm tra nested JAR trong `BOOT-INF/lib`?
6. Vì sao metadata repository version range cần được đối chiếu với version phân giải thực tế?
7. Một dependency có metadata reflection nhưng dùng JNI có thể vẫn gặp lỗi nào?
8. Vì sao native build pass không chứng minh mọi feature của thư viện chạy được?
9. Những thành phần nào cần được ghi trong compatibility matrix ngoài version của thư viện?
10. Khi nào phải chạy lại compatibility assessment?

## 15. Tài liệu chính thức

Các trang và repository có thể thay đổi theo release. Khi thực hiện đánh giá, chọn tài liệu khớp version thư viện và toolchain:

- [GraalVM Reachability Metadata Repository](https://github.com/oracle/graalvm-reachability-metadata): metadata do cộng đồng duy trì cho các thư viện Java.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): định dạng, vị trí và cách cung cấp metadata.
- [GraalVM Native Build Tools](https://graalvm.github.io/native-build-tools/latest/): plugin Maven/Gradle và tích hợp native build.
- [Spring Boot — GraalVM Native Image](https://docs.spring.io/spring-boot/reference/packaging/native-image/index.html): Spring AOT, native compilation và đóng gói.
- [Spring Framework — Ahead-of-Time Processing](https://docs.spring.io/spring-framework/reference/core/aot.html): runtime hints và đóng góp AOT.
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): xem dependency graph Maven.
- [Gradle — Viewing and debugging dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependency insight và version selection.
- Tài liệu compatibility matrix, release notes và native image guide của **nhà phát hành từng thư viện**: dùng trang chính thức của đúng artifact/version đang phân giải.

**Điểm cần nhớ:** native support là kết luận gắn với version artifact, toolchain, platform và feature được sử dụng. Hãy bắt đầu từ dependency graph thực tế, xác minh metadata và tuyên bố của nhà phát hành, rồi chạy native tests và ghi lại bằng chứng trong compatibility ledger.

