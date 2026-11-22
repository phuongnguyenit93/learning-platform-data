# Xác định dependency cần nâng cấp trước khi đổi JDK

## 1. Vì sao phải khảo sát dependency trước khi nâng JDK?

Nâng JDK không đơn thuần là thay `JAVA_HOME`, đổi Docker base image hoặc chỉnh `sourceCompatibility`. Một ứng dụng Java thường phụ thuộc vào nhiều lớp thành phần: công cụ build, plugin, compiler, annotation processor, framework, thư viện runtime, driver, agent, native code và các dependency bắc cầu (*transitive dependencies*). Chỉ một mắt xích không hỗ trợ JDK đích cũng có thể làm cả migration thất bại.

Ví dụ, khi chuyển từ JDK 17 sang JDK 21:

- Gradle/Maven hoặc plugin build có thể chưa chạy được trên build JVM mới.
- Annotation processor hoặc compiler extension sử dụng API nội bộ của `javac` và lỗi khi biên dịch.
- Framework kéo theo một bytecode library không đọc được định dạng class file mới.
- Một thư viện dùng reflection sâu vào package JDK bị đóng gói chặt hơn và gặp `InaccessibleObjectException`.
- Driver, TLS provider, thư viện native hoặc APM agent cần phiên bản khác để hoạt động trên runtime mới.
- Dependency vẫn dựa vào module từng đi kèm JDK cũ nhưng đã bị loại bỏ ở JDK đích.
- Version thực tế của dependency bắc cầu khác bản mong đợi vì BOM, constraints hoặc conflict resolution.

Nếu đổi JDK trước rồi xử lý từng stack trace, nhóm sẽ phải sửa lỗi theo phản ứng: nâng build plugin, lại phát hiện annotation processor, tiếp đến framework, driver và agent. Cách có kiểm soát hơn là **lập bản đồ toàn bộ dependency và xác định những thành phần phải nâng cấp trước khi chuyển môi trường**.

Trong bài này, từ *dependency* không chỉ chỉ những JAR khai báo trong `implementation` hay `<dependencies>`. Nó bao gồm bất kỳ thành phần nào ứng dụng cần để **biên dịch, kiểm thử, đóng gói, khởi động và chạy ổn định trên JDK mục tiêu**.

## 2. Đầu ra mong đợi của một đợt kiểm kê

Sau khảo sát, nhóm nên trả lời được:

1. **Ứng dụng đang dùng thành phần nào, phiên bản nào?** Bao gồm direct, transitive, build plugins, test, agents, native và các thư viện nằm trong artifact đóng gói.
2. **Thành phần nào thực sự không tương thích JDK đích?** Dựa vào vendor support matrix, release notes và bằng chứng chạy thử, không chỉ phỏng đoán.
3. **Thành phần nào phải nâng trước?** Chẳng hạn build tool không khởi động, processor không thể compile, framework không thể start.
4. **Thành phần nào có thể giữ nguyên?** Thư viện đang được hỗ trợ, phù hợp JDK đích và không gây blocker có thể chưa cần nâng.
5. **Nâng theo thứ tự nào?** Xét ràng buộc giữa framework/BOM, plugin, compiler, runtime và native components.
6. **Chứng minh hoàn thành ra sao?** Kết quả resolution, compatibility tests, integration tests, artifact/runtime thực tế và kế hoạch rollout.

Đầu ra quan trọng nhất là **bảng quyết định dependency**: hiện trạng, phiên bản mục tiêu, lý do thay đổi, blocker, người chịu trách nhiệm, bằng chứng và thứ tự thực hiện. Một danh sách các phiên bản “mới nhất” không đáp ứng mục tiêu này.

## 3. Phân loại dependency theo vai trò

| Nhóm | Ví dụ | Ảnh hưởng chủ yếu |
| --- | --- | --- |
| Build tool | Gradle Wrapper, Maven Wrapper | Khởi động và điều phối build |
| Build plugin | Spring Boot plugin, shading, code quality, container plugin | Configuration và các build tasks |
| Compiler/toolchain | `javac`, Kotlin/Scala compiler, toolchain | Phân tích và tạo bytecode |
| Annotation processor | Lombok, MapStruct processor, custom APT | Sinh mã và xử lý annotation |
| Compile dependency | API trong compile classpath | Kiểm tra chữ ký, generics, source compatibility |
| Runtime library | ORM, JSON, logging, HTTP, messaging | Class loading và chức năng runtime |
| Test dependency | JUnit, Mockito, coverage, test runner | Phát hiện/chạy tests |
| Bytecode/instrumentation | ASM, Byte Buddy, Javassist, Java agents | Đọc, sinh hoặc thay đổi bytecode |
| Native component | JNI/JNA, native drivers, platform libraries | ABI, CPU, OS và liên kết native |
| Platform/BOM | Framework BOM, Maven dependencyManagement, Gradle platform | Chọn tổ hợp phiên bản |
| Internal library | Company SDK, shared starter, DTO | API/ABI/hành vi giữa module |
| Deployment runtime | JRE/container image, `jlink`, agents từ hạ tầng | Khả năng chạy trong production |

Các nhóm có thể chồng nhau. Ví dụ một starter có dependency trực tiếp ở `runtimeClasspath`, nhưng đồng thời kéo nhiều thư viện bắc cầu và được quản lý bằng BOM. Một APM agent có thể không xuất hiện trong build file vì được hạ tầng thêm qua startup flags.

Vì vậy, không lấy một báo cáo `runtimeClasspath` rồi kết luận đã kiểm kê đủ toàn bộ dependency liên quan migration.

## 4. Phân biệt JDK chạy build, compiler JDK và runtime JDK

Câu “dự án dùng Java 21” chưa nói rõ:

- **Build JVM:** JVM chạy Gradle hoặc Maven cùng các plugin của chúng.
- **Compiler JDK:** JDK cung cấp `javac` hoặc compiler toolchain được lựa chọn.
- **Target release:** mức Java API và bytecode artifact hướng tới, ví dụ `--release 17`.
- **Test JVM:** JVM chạy các test, có thể được chọn riêng.
- **Application runtime:** JVM thực tế trong container, VM hoặc runtime image production.

Ví dụ CI có thể chạy Gradle trên JDK 21, dùng compiler toolchain JDK 21 và `--release 17` để phát hành library vẫn hỗ trợ Java 17. Một plugin build cần hỗ trợ **JVM của Gradle**; trong khi runtime library phải phù hợp với **JVM thấp nhất mà artifact còn cam kết hỗ trợ**. Annotation processor lại phải tương thích với **compiler được chọn**.

Lệnh khảo sát tham khảo:

~~~bash
java -version
javac -version
./gradlew --version
mvn -version
~~~

`java -version` trong terminal không chứng minh IDE, Gradle daemon, Maven compiler plugin hoặc container production đang dùng cùng JDK. Cần ghi các vai trò thành từng trường riêng:

~~~text
Build JVM:         JDK ...
Build tool:        Gradle/Maven ...
Compiler toolchain: JDK ...
Release target:    Java ...
Unit/IT JVM:       JDK ...
Production runtime: JDK/JRE ...
~~~

## 5. Chốt JDK đích và chính sách hỗ trợ trước khi chọn version

Trước khi đánh giá một dependency, xác định:

- JDK nguồn và đích, ví dụ 17 → 21.
- JDK vendor/distribution nếu có ràng buộc.
- Mức Java tối thiểu sản phẩm vẫn phải hỗ trợ.
- Có cần chạy trên nhiều JDK trong giai đoạn chuyển tiếp không?
- Runtime production là JDK đầy đủ, JRE image hay `jlink` image?
- Framework major hiện tại có được phép thay đổi?
- Có rolling deployment, rollback và consumer dùng chung library không?
- Những luồng nghiệp vụ nào bắt buộc phải hoạt động trước cutover?

Thư viện bản mới nhất có thể yêu cầu Java tối thiểu cao hơn sản phẩm, hoặc kéo một framework major đổi API/namespace không nằm trong phạm vi migration. Do đó **phiên bản mục tiêu là phiên bản được hỗ trợ và phù hợp toàn hệ**, không mặc định là số lớn nhất.

### 5.1. Bằng chứng hỗ trợ cần tìm

Với thành phần quan trọng, đối chiếu:

1. Compatibility matrix của nhà cung cấp với JDK và framework mục tiêu.
2. Release notes, upgrade guide và breaking changes.
3. Chính sách bảo trì/EOL của nhánh phiên bản.
4. Issue tracker về JDK đích, bytecode, reflection, JNI hoặc memory model.
5. BOM/platform và tập phiên bản được nhà cung cấp kiểm thử.
6. Test thực tế của ứng dụng.

Không suy ra “hỗ trợ Java 21” chỉ vì JAR chứa class-file version 52 (Java 8). JVM mới có thể nạp bytecode cũ, nhưng thư viện vẫn có thể dùng API nội bộ bị thay đổi hoặc phụ thuộc hành vi không còn được bảo đảm.

## 6. Bước 1: Kiểm kê direct và transitive dependencies

### 6.1. Với Gradle

Các configuration thường cần khảo sát gồm `compileClasspath`, `runtimeClasspath`, `testCompileClasspath`, `testRuntimeClasspath`, `annotationProcessor` cùng các configuration do plugin tạo.

Lệnh tham khảo:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew :service-a:dependencies --configuration runtimeClasspath
~~~

Trong dự án nhiều module, phải xem graph của từng module quan trọng, vì dependency của module A không nhất thiết giống module B.

Để tìm lý do một phiên bản được chọn:

~~~bash
./gradlew dependencyInsight \
    --dependency byte-buddy \
    --configuration testRuntimeClasspath
~~~

`dependencyInsight` cho biết đường phụ thuộc, quá trình resolution, version conflicts và một số constraint. Báo cáo này quan trọng vì version thực tế được Gradle resolve có thể khác số version viết trực tiếp trong build file.

Đừng quên **plugin/buildscript classpath**. Một dependency lỗi trong Gradle daemon có thể không xuất hiện ở `runtimeClasspath` của application.

### 6.2. Với Maven

Dependency Maven có thể đến từ POM trực tiếp, parent POM, `dependencyManagement`, BOM import và các profile. Những scope như `compile`, `runtime`, `provided` và `test` ảnh hưởng cách dependency có mặt ở từng giai đoạn.

Lệnh tham khảo:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
mvn help:effective-pom
~~~

`dependency:tree` hiển thị cây phụ thuộc đã được Maven giải quyết trong cấu hình đó. `effective-pom` giúp thấy cấu hình sau khi áp dụng parent, profile và management.

Plugin Maven có dependency và version riêng. Nâng một library trong `<dependencies>` không tự nâng `maven-compiler-plugin`, `maven-surefire-plugin`, `maven-failsafe-plugin`, `maven-shade-plugin` hay các plugin code generation.

### 6.3. Dependency bắc cầu mới là blocker thường gặp

Ví dụ:

~~~text
orders-service
 └── framework-starter
      ├── framework-core
      ├── json-runtime
      └── bytecode-engine:old
~~~

Ứng dụng không khai báo `bytecode-engine` trực tiếp nhưng framework sử dụng nó. Nếu bản cũ không hiểu class file mới, lỗi có thể xuất hiện khi framework sinh proxy, scan annotation hoặc chạy test.

Không nên lập tức ép `bytecode-engine` sang major version mới khi framework cha chưa hỗ trợ tổ hợp đó. Trước hết kiểm tra framework/BOM có nhánh được công bố tương thích với JDK mục tiêu hay không.

## 7. Bước 2: Xác định build tool và plugin cần nâng trước

Build tool là cổng vào pipeline. Nếu Gradle/Maven không chạy được bằng JVM mới, nhóm chưa thể kiểm tra các thay đổi còn lại.

### 7.1. Gradle Wrapper

Version sử dụng trong dự án được quản lý qua Gradle Wrapper, thường trong `gradle/wrapper/gradle-wrapper.properties`. Đối chiếu Gradle **Java compatibility matrix** để phân biệt:

- Gradle có thể **chạy trên** JDK đích hay chưa.
- Gradle có thể dùng JDK đích làm **toolchain biên dịch/test** hay chưa.

Hai khả năng này có thể xuất hiện ở các phiên bản Gradle khác nhau. Vì thế, không dùng kết luận “toolchains hỗ trợ Java 21” để khẳng định Gradle daemon của bản đó có thể chạy bằng Java 21.

Plugin cần khảo sát:

- Framework plugin, dependency-management plugin.
- Kotlin/Groovy/Scala build integration.
- Checkstyle/PMD/SpotBugs/Error Prone.
- JaCoCo và các công cụ coverage.
- Packaging, shading, native image, Docker/container build.
- OpenAPI/protobuf/gRPC generators.
- Convention plugins, `buildSrc` và plugin nội bộ.

Nâng Gradle Wrapper cũng có thể thay DSL behavior hoặc yêu cầu plugin APIs khác. Nên chọn tổ hợp **JDK ↔ Gradle ↔ plugin** được hỗ trợ, không chỉ nâng wrapper rồi xử lý các plugin một cách ngẫu nhiên.

### 7.2. Maven Wrapper và plugins

Với Maven, kiểm tra Maven Core, Maven Wrapper, Compiler Plugin, Surefire/Failsafe, Shade/JAR, Resources và các plugin sinh mã. Cố định plugin versions qua `pluginManagement` hoặc cơ chế tương ứng để CI/developer không resolve theo những mặc định khác nhau.

Một plugin có thể chạy trên Maven phiên bản hiện tại nhưng không tương thích JDK mới. Một plugin khác có thể hỗ trợ JDK mới nhưng yêu cầu Maven Core mới hơn. Hãy kiểm tra cả hai điều kiện.

### 7.3. Compiler toolchain không tự sửa build JVM

Ví dụ Gradle Groovy DSL:

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

Cấu hình này minh họa compiler JDK 21 phát hành artifact Java 17, **không tự quyết định JVM khởi chạy Gradle**. Nếu Gradle/plugin không hỗ trợ JDK mà build đang chạy, compile task có thể chưa được thực hiện.

## 8. Bước 3: Kiểm tra annotation processor và compiler extensions

Đây là nhóm thường gây lỗi khi nâng compiler JDK vì một số processor hoặc plugin sử dụng API compiler nội bộ:

- Lombok.
- MapStruct annotation processor.
- Dagger, AutoValue, custom APT.
- Error Prone hoặc các compiler plugins.
- Kotlin kapt/KSP trong dự án Java/Kotlin.
- Công cụ sinh mã nội bộ truy cập `com.sun.tools.javac.*`.

Ví dụ triệu chứng:

~~~text
java.lang.IllegalAccessError:
module jdk.compiler does not export com.sun.tools.javac.*
~~~

Hoặc:

~~~text
java.lang.NoSuchFieldError: ... javac tree ...
~~~

Đây có thể là incompatibility của processor, không phải lỗi source của ứng dụng.

### 8.1. Cách ghi nhận processor

| Processor/plugin | Module | Compiler JDK mục tiêu | Bằng chứng yêu cầu |
| --- | --- | --- | --- |
| Lombok | Entity/DTO | JDK đích | Vendor support và compile test |
| MapStruct processor | Mapper | JDK đích | Generated code và mapper tests |
| Custom APT | Shared modules | JDK đích | Không phụ thuộc compiler internals |
| Error Prone | CI build | JDK/compiler tương ứng | Plugin/compiler integration |

Với Gradle, xem `annotationProcessor` và `testAnnotationProcessor`. Với Maven, xem annotation processor paths trong Maven Compiler Plugin và cấu hình plugin liên quan.

Đừng chỉ yêu cầu compile pass. Nếu processor sinh API khác trước, consumer có thể bị ảnh hưởng về source, binary hoặc behavior.

## 9. Bước 4: Xác định framework/BOM là điểm neo

Framework nền thường quyết định một bộ dependency liên kết với nhau:

~~~text
Framework/BOM
 ├─ Framework core
 ├─ JSON & validation
 ├─ ORM & JDBC integration
 ├─ Embedded web server
 ├─ Logging & tracing
 └─ Test libraries
~~~

Ví dụ các hệ sinh thái cần đối chiếu gồm Spring Boot/Spring Framework, Jakarta EE, Hibernate, Netty, Jackson và các stack reactive hoặc messaging.

Nâng platform/BOM đến nhánh được vendor xác nhận hỗ trợ JDK đích thường có cơ sở hơn việc tự override nhiều transitive dependencies.

Tuy nhiên BOM không bảo đảm tất cả:

- Một số dependencies nằm ngoài BOM.
- Plugin build có version management riêng.
- Explicit constraints/forced versions có thể ghi đè.
- Multi-module projects có thể áp dụng platform khác nhau.
- Shaded/native components có thể không rõ trong cây phụ thuộc.

Sau khi đổi BOM, phải **đọc lại resolved dependency graph** để xác nhận tổ hợp thực tế.

### 9.1. Tách framework major migration khỏi JDK migration

Nâng framework major có thể kéo theo:

- Đổi namespace ở những API chuyển từ Java EE sang Jakarta EE (ví dụ `javax.persistence` sang `jakarta.persistence` khi chọn thế hệ Jakarta tương ứng).
- Thay đổi key cấu hình, validation và security defaults.
- Method/class bị loại bỏ.
- Thay đổi serializer, transaction, exception mapping.
- Tăng mức Java tối thiểu.

Đây không phải các vấn đề chỉ do nâng JDK. Khi lên kế hoạch, ghi rõ hạng mục nào là **JDK compatibility blocker** và hạng mục nào là **framework breaking change** để có test, owner và rollback thích hợp.

### 9.2. Không biến mọi `javax.*` thành `jakarta.*`

Không phải package bắt đầu bằng `javax` đều thuộc cùng hệ sinh thái. Một số API `javax.*` là Java SE API; các API Java EE/Jakarta EE có lịch sử/module riêng. Ví dụ JAXB từng có trong một số bản JDK cũ nhưng không còn được đóng gói trong JDK 11+, nên ứng dụng có thể cần dependency riêng. Chuyển namespace persistence/servlet là việc thuộc thế hệ API/framework tương ứng, không phải thao tác tìm-thay chung vì số JDK tăng.

## 10. Bước 5: Phát hiện sử dụng JDK internals và reflection

Các thư viện cũ có thể sử dụng `sun.misc.Unsafe`, `jdk.internal.*`, deep reflection hoặc những API không được hỗ trợ. Khi JDK thay đổi đóng gói module hoặc loại bỏ API, lỗi có thể xảy ra tại runtime.

### 10.1. Phân tích tĩnh bằng `jdeps`

Các lệnh tham khảo:

~~~bash
jdeps --jdk-internals library.jar
jdeps --jdk-internals --recursive application.jar
jdeps --multi-release 21 --jdk-internals dependency.jar
~~~

Với multi-release JAR, nên chỉ định release cần khảo sát. `jdeps` phân tích liên kết/class files nhưng không bảo đảm phát hiện mọi reflection động, JNI, bytecode sinh runtime hoặc agent được nạp ngoài build.

### 10.2. Đọc triệu chứng đúng tầng

| Triệu chứng | Khả năng nguyên nhân | Cách điều tra |
| --- | --- | --- |
| `InaccessibleObjectException` | Deep reflection vào package không mở | Class/module và dependency trong stack trace |
| `IllegalAccessError` | Access control hoặc module access khi liên kết | Caller, target và quyền module |
| `NoClassDefFoundError` | Class không tồn tại trên runtime path, initializer lỗi | Artifact/class loader/module dependencies |
| `NoSuchMethodError` | Lệch API/ABI do version conflict | Method descriptor và resolved graph |
| `UnsupportedClassVersionError` | Bytecode mới hơn JVM runtime | Class-file major version |
| Lỗi parser class file/ASM | Thư viện không nhận class-file format mới | Bytecode library do framework/plugin kéo vào |

Không nên kết luận mọi lỗi trong bảng do JDK mới; classpath hoặc dependency graph lệch cũng có thể tạo đúng triệu chứng đó.

### 10.3. `--add-opens` không phải một bản nâng cấp

Một số JVM flags như `--add-opens` hoặc `--add-exports` có thể là workaround có phạm vi, nhưng không bảo đảm API nội bộ còn ổn định hoặc tồn tại. Nếu phải dùng, ghi lý do, chủ sở hữu, giới hạn sử dụng và mốc loại bỏ. Không thay `sun.misc.Unsafe` bằng `jdk.internal.misc.Unsafe` rồi coi đó là giải pháp dài hạn.

## 11. Bước 6: Kiểm tra thư viện bytecode và instrumentation

Những nhóm đáng chú ý:

- ASM, Byte Buddy, Javassist.
- Runtime proxies, AOP, ORM bytecode enhancement.
- Mockito, test mocking/agents.
- JaCoCo hoặc coverage agents.
- Classpath scanners và DI frameworks.
- Compiler/codegen pipelines.

Một thư viện có thể chạy bình thường với class-file version cũ nhưng không phân tích được class file do compiler mới tạo.

| Java release | Class-file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Có thể kiểm tra artifact:

~~~bash
javap -classpath application.jar -verbose com.example.Main
~~~

Tìm `major version`. Tuy nhiên, class-file target tương thích **không tự chứng minh** ứng dụng dùng đúng Java SE APIs hoặc không bị runtime reflection/native lỗi.

Nếu Mockito hoặc coverage agent lỗi trong unit tests, điều đó không mặc nhiên chứng minh production runtime library bị lỗi. Phải phân loại đúng **test-time blocker** và **runtime blocker**.

## 12. Bước 7: JDBC, native libraries và JVM agents

### 12.1. JDBC và database

Đối chiếu driver version với vendor support, database server version, authentication, TLS/certificate, timezone, encoding, connection pool và ORM integration. Compile thành công không chứng minh connection/transaction paths hoạt động trên JDK mới.

### 12.2. JNI/JNA và native binaries

Các thành phần native chịu ràng buộc CPU architecture, OS, JDK/JNI, shared library ABI và base image. Một JAR có thể chứa binary cho nhiều platform hoặc cần cài thư viện hệ điều hành bên ngoài.

Không chỉ nhìn số version JAR; phải test trên **container/host runtime** thực tế.

### 12.3. APM, profiler, security, coverage agents

Agent có thể được thêm khi khởi động JVM, nằm ngoài `pom.xml`/`build.gradle`:

~~~text
JAVA_TOOL_OPTIONS
JDK_JAVA_OPTIONS
-javaagent:/opt/agents/agent.jar
container entrypoint / platform injection
~~~

Chúng có thể instrument class file, dùng internal APIs hoặc làm thay đổi startup/performance. Khi nâng JDK, cần xác nhận vendor hỗ trợ agent và kiểm thử startup, tracing/metrics cùng overhead vận hành.

Tắt agent để khoanh vùng lỗi không phải bằng chứng cấu hình production đã sẵn sàng.

## 13. Bước 8: JDK modules và những API đã bị loại bỏ

Khi nâng từ những JDK cũ, ứng dụng có thể gặp API không còn được JDK đóng gói, chẳng hạn một số module Java EE/CORBA bị loại bỏ từ Java 11. Ứng dụng dùng JAXB/JAX-WS hoặc công nghệ legacy cần xác định dependency độc lập phù hợp.

Kiểm tra:

- Những package/module từng được JDK cũ cung cấp.
- JavaFX nếu trước đây dựa vào distribution có bundling.
- Module graph của ứng dụng.
- `jlink` runtime image có đủ modules/providers không.
- API deprecated for removal hoặc đã remove theo JDK mục tiêu.

Lệnh tham khảo:

~~~bash
jdeps --print-module-deps application.jar
jdeps --missing-deps application.jar
~~~

`jdeps` không thể tự suy ra mọi service loading, reflection hoặc native dynamic dependency. Đối với `jlink` image, phải chạy integration tests trên image cuối thay vì chỉ dùng full JDK trong CI.

## 14. Rủi ro version conflicts và resolution rules

Ví dụ:

~~~text
orders-service
 ├── library-a
 │    └── common-core:2.x
 └── library-b
      └── common-core:1.x
~~~

Build tool chọn một phiên bản của `common-core` theo cơ chế resolution/management. Nếu một consumer cần API không có trong phiên bản được chọn, có thể gặp `NoSuchMethodError` hoặc thay đổi behavior.

Đặc biệt quan tâm:

- Logging facade/binding.
- JSON modules (core, databind, annotations).
- Bytecode libraries.
- HTTP/Netty stack.
- Guava/utility libraries.
- Jakarta API và ORM integration.
- Telemetry/tracing modules.

Với dependency constraints, `force`, `strictly`, Gradle locking, Maven `dependencyManagement` hoặc BOM overrides, ghi:

1. Ai yêu cầu version nào.
2. Version nào được resolve thật.
3. Rule nào chọn/ép version.
4. Ai phụ thuộc API của version cụ thể.
5. Có phù hợp framework/BOM mục tiêu không.

Một override được thêm trong quá khứ để xử lý CVE có thể không còn cần thiết sau khi nâng framework. Rà soát các ngoại lệ thay vì giữ nguyên cơ học.

## 15. Bảo mật, support lifecycle và SBOM

Tương thích JDK chỉ là một chiều của quyết định. Còn cần xem:

- Nhánh version có đang được bảo trì và nhận bản vá không.
- Có CVE hoặc advisory liên quan không.
- License và chính sách tổ chức.
- Artifact provenance và repository đáng tin cậy.
- Transitive dependencies đi kèm.
- Khả năng kiểm kê qua SBOM (Software Bill of Materials).

Một dependency có CVE chưa vá **không đồng nghĩa** nó là JDK compatibility blocker; ngược lại một dependency không có CVE được biết đến vẫn có thể không chạy trên JDK đích.

Nên ghi riêng:

~~~text
Reason for upgrade:
  JDK compatibility / security advisory /
  vendor support lifecycle / framework alignment
~~~

Nếu cần bản vá bảo mật khẩn cấp, có thể phải ưu tiên thay ngay trước migration JDK. Khi có thể, tách patch bảo mật khỏi framework major upgrade để dễ khoanh vùng regression.

SBOM hữu ích khi báo cáo đúng artifact đóng gói; với shaded JAR và native components, có thể phải bổ sung kiểm kê ngoài resolved dependency tree.

## 16. Phân loại mức độ blocker

| Mức | Ý nghĩa | Ví dụ | Hành động |
| --- | --- | --- | --- |
| P0 — Blocking | Không thể build/start hoặc chức năng trọng yếu thất bại trên JDK đích | Build plugin không khởi động, processor lỗi | Thay/nâng trước cutover |
| P1 — High risk | Chưa có mức hỗ trợ/bằng chứng đủ cho luồng production quan trọng | JDBC/agent chưa xác nhận | Khắc phục hoặc kiểm chứng trước triển khai |
| P2 — Planned | Không chặn ngay nhưng có rủi ro support hoặc vận hành | Nhánh version sắp EOL | Lên kế hoạch kiểm soát |
| P3 — Defer | Đã tương thích, có bằng chứng phù hợp, chưa cần nâng | Utility library ổn định | Giữ version, ghi lý do |

Đây là cách phân loại minh họa, không phải tiêu chuẩn bắt buộc. Điều quan trọng là tránh tình trạng “thấy bản mới thì nâng hết”.

### 16.1. Các cấp độ bằng chứng

- **Vendor-supported:** nhà cung cấp công bố hỗ trợ JDK mục tiêu.
- **Observed working:** ứng dụng đã vượt qua một tập kiểm thử cụ thể.
- **Untested:** chưa đủ dữ liệu.
- **Known incompatible:** có giới hạn hỗ trợ hoặc lỗi tái hiện rõ.

“Đang chạy được” không đồng nghĩa “được vendor hỗ trợ”. Nếu chấp nhận dependency không có support chính thức, cần ghi owner, phạm vi test, rủi ro và kế hoạch xử lý.

## 17. Xác định thứ tự nâng theo quan hệ ràng buộc

Một luồng quyết định thường gặp:

~~~mermaid
flowchart TD
    A[Chốt JDK mục tiêu và Java minimum] --> B[Kiểm kê resolved dependencies]
    B --> C[Build tool và plugin có chạy được?]
    C --> D[Compiler/annotation processors tương thích?]
    D --> E[Chọn framework và BOM]
    E --> F[Giải quyết transitive conflicts]
    F --> G[Runtime drivers, bytecode, native, agents]
    G --> H[Build và test trên JDK đích]
    H --> I[Canary và rollout]
~~~

Các bước có thể cần lặp; ví dụ framework/BOM mới có thể yêu cầu plugin mới, còn processor cần nâng trước khi build chạy. Vì thế nên nhìn thứ tự trên như **dependency chain**, không phải một checklist bắt buộc đi đúng một lần.

Chiến lược thực tế:

1. **Khảo sát toàn bộ** và chốt constraint trước khi đổi version.
2. **Ổn định hệ build** để có pipeline kiểm thử trên JDK đích.
3. **Chọn framework/BOM mục tiêu** theo vendor support.
4. **Giải quyết transitive runtime blockers** theo graph đã resolve.
5. **Kiểm thử xuyên tầng** rồi mới thay runtime production.
6. **Tách commit/PR theo phạm vi rõ** để có thể bisect và rollback từng thay đổi.

## 18. Ví dụ ma trận ra quyết định trước Java 17 → 21

| Thành phần | Quan hệ JDK 21 cần xác minh | Hành động dự kiến | Bằng chứng |
| --- | --- | --- | --- |
| Gradle Wrapper | Có chạy trên build JVM 21? | Nâng nếu matrix yêu cầu | Wrapper version, clean build |
| Build plugins | Có hỗ trợ Gradle/JDK mới? | Nâng đúng plugin | Plugin releases, build tasks |
| Lombok | Có tương thích compiler JDK 21? | Nâng bản được xác nhận | Biên dịch generated models |
| ASM/Byte Buddy | Có đọc/sinh class-file 65? | Nâng qua platform/plugin thích hợp | Test instrumentation/proxy |
| Framework/BOM | Có nhánh hỗ trợ JDK 21? | Chọn platform phù hợp | Vendor docs, integration |
| JDBC driver | TLS/auth/transaction trên JDK 21? | Chọn driver được hỗ trợ | Integration DB thật |
| APM agent | Agent instrumentation trên JVM 21? | Nâng agent nếu cần | Startup, traces và metrics |
| Internal SDK | Có JDK internals/ABI cũ? | Kiểm kê và test consumer | `jdeps`, compatibility tests |
| Utility library | Có hỗ trợ, test pass và không conflict? | Có thể giữ nguyên | Resolved graph và tests |

Không có số version mục tiêu cố định trong bảng vì phiên bản phù hợp phụ thuộc dự án, framework, JDK tối thiểu và thông tin hỗ trợ tại thời điểm migration.

### 18.1. Trường hợp không cần nâng

Một thư viện utility thuần Java sử dụng API công khai ổn định, vẫn được bảo trì và chạy qua tests trên JDK đích. Nếu không có blocker, security requirement hoặc conflict, **giữ phiên bản cũ** có thể là lựa chọn ít rủi ro hơn nâng không có mục tiêu.

### 18.2. Trường hợp phải nâng ngay

Processor cũ ném `IllegalAccessError` khi dùng compiler JDK 21 và mọi module đều phụ thuộc generated code. Đây là blocker ở compile stage, nên phải chọn processor version tương thích hoặc loại bỏ phụ thuộc API nội bộ trước khi chuyển compiler.

### 18.3. Trường hợp nên nâng platform

Framework cũ kéo theo cả server, JSON stack và bytecode engine không được hỗ trợ trên JDK đích. Nếu có framework/BOM tương thích được vendor cung cấp, nâng theo tổ hợp đó thường hợp lý hơn ép từng transitive version. Breaking changes của framework phải được ghi nhận riêng.

## 19. Không coi “latest” là tiêu chí lựa chọn

Công cụ tìm bản mới có thể đề xuất:

~~~text
library-a: 2.8 -> 3.0
library-b: 4.1 -> 4.9
framework: 5.x -> 6.x
~~~

Danh sách này **không chứng minh** các bản mới chạy trên JDK mục tiêu, phù hợp BOM, giữ nguyên API, đáp ứng mức Java tối thiểu hoặc không kéo breaking changes khác.

Trước khi chọn, hỏi:

~~~text
Is this version supported on target JDK?
Is it supported with the selected framework/BOM?
Does it preserve minimum Java runtime?
What are the documented breaking changes?
Which tests prove critical behavior?
~~~

Không phải mọi Java library đều tuân thủ Semantic Versioning đầy đủ. Ngay cả một patch release cũng cần được kiểm thử theo những hành vi sản phẩm phụ thuộc.

## 20. Làm cho dependency graph có thể tái lập

Một bản kiểm kê nhanh lỗi thời nếu CI và developer resolve ra các dependency graphs khác nhau.

Với Gradle, có thể cân nhắc:

- Version catalogs cho khai báo tập trung.
- Platform/BOM và dependency constraints.
- Dependency locking.
- Dependency verification.
- Wrapper version cố định.

Với Maven:

- Parent POM và `dependencyManagement`.
- BOM import.
- `pluginManagement`.
- Maven Wrapper.
- Enforcer rules và repository policy phù hợp.

Các cơ chế trên có mục đích khác nhau: version catalog không tự ép mọi transitive dependency; locking cố định resolved graph nhưng không xác nhận compatibility. Muốn kiểm tra được migration, còn phải ghi cả JDK/toolchain, plugin, native library và container image versions.

Nên hạn chế dynamic versions và version ranges quá rộng trong giai đoạn kiểm chứng, vì build lại cùng commit nhưng graph thay đổi sẽ rất khó khoanh vùng lỗi.

## 21. Tách ảnh hưởng JDK khỏi ảnh hưởng nâng dependency

Một ma trận có thể giúp xác định nguồn lỗi:

| Case | JDK | Dependency graph | Mục đích |
| --- | --- | --- | --- |
| A | JDK cũ | Graph cũ | Baseline |
| B | JDK mới | Graph cũ | Phát hiện incompatibility của graph cũ với JDK mới |
| C | JDK cũ | Graph mới | Đo tác động của dependency upgrade nếu tổ hợp này được hỗ trợ |
| D | JDK mới | Graph mới | Trạng thái đích |

Không phải mọi ô đều hợp lệ. Nếu graph mới đã yêu cầu JDK mới, ô C là **unsupported combination**, cần ghi rõ thay vì cố chạy.

Ví dụ B fail và D pass: có dấu hiệu dependency upgrade đã xử lý blocker khi chạy JDK mới. Nếu B pass nhưng D có behavior regression, điều tra những thay đổi dependency graph mới trước khi kết luận JDK là nguyên nhân.

Ma trận không thay thế stack trace/compatibility tests, nhưng giúp giữ mỗi phép thử chỉ thay đổi một nhóm biến khi có thể.

## 22. Kiểm thử theo tầng trước cutover

### 22.1. Build và compile

- Build tool khởi động bằng build JVM dự kiến.
- Compiler toolchain/release đúng cấu hình.
- Annotation processors và generated sources hoạt động.
- Plugin code quality/package không bị bỏ qua vì lỗi cấu hình.

### 22.2. Unit và test tooling

- Test engine khám phá và chạy đủ test.
- Mocking, coverage và instrumentation tương thích.
- Test JVM đúng version.
- Không vô tình disable tests để build xanh.

### 22.3. Runtime smoke

- Application khởi động với dependency graph đã đóng gói.
- DI, configuration, logging và service loaders hoạt động.
- Agent và native library tải thành công.
- Các đường request/event chính hoạt động.

### 22.4. Integration

- Database, JDBC transactions và connection pool.
- HTTP/TLS, messaging, cache và external services.
- Serialization/deserialization và dữ liệu lịch sử.
- Reflection, module access và proxy runtime.
- Runtime image/container production thật.

### 22.5. Non-functional

- Startup time, memory/GC, throughput và p95/p99 latency.
- Connection/thread pools, native memory.
- Logs, metrics và traces.
- Security defaults, certificates và audit.

Không phải mọi utility library upgrade đều cần microbenchmark riêng. Nhưng với framework, driver, JNI, Netty, agent hoặc low-level concurrency library, các phép đo non-functional có thể quyết định tính sẵn sàng production.

## 23. Những lỗi thường gặp khi chọn thứ tự nâng cấp

**Chỉ nhìn direct dependencies.** Blocker có thể nằm sâu trong transitive graph. Dùng dependency tree/insight để tìm đường kéo vào.

**Đổi JDK trước khi kiểm tra Gradle/Maven.** Build tool không chạy khiến cả pipeline kẹt; đối chiếu compatibility matrix trước.

**Bỏ qua annotation processors.** Một processor dùng `javac` internals có thể lỗi dù toàn bộ runtime libraries tương thích.

**Nâng mọi thư viện lên latest.** Tăng số biến thay đổi, có thể vi phạm BOM và mở thêm breaking changes.

**Ép ASM/Netty/JSON phiên bản mới bên trong framework cũ.** Không phải tổ hợp nào cũng được nhà cung cấp kiểm thử.

**Đánh đồng test dependency với production dependency.** Lỗi Mockito/coverage agent chỉ ra một lớp vấn đề cụ thể, cần phân loại trước khi sửa.

**Chỉ nhìn `java -version`.** Build JVM, compiler JDK, test JVM và container runtime có thể khác nhau.

**Cho rằng class-file target cũ đảm bảo chạy trên mọi JDK mới.** Reflection/internal APIs/native integration vẫn có thể lỗi.

**Quên agent và native libraries.** Chúng thường được inject ngoài source dependency declarations.

**Đổi tất cả `javax.*` sang `jakarta.*`.** Phải xác định API và framework thế hệ liên quan.

**Chỉ chạy unit tests.** Driver, TLS, container, agent và dữ liệu thường cần integration tests.

**Không lưu resolved graph.** Build mới chọn version khác khiến so sánh JDK thiếu tin cậy.

**Dùng `--add-opens` làm giải pháp lâu dài.** Cờ có thể giúp truy cập tạm thời nhưng không thay bản nâng thư viện được hỗ trợ.

## 24. Checklist trước khi cho phép đổi JDK

- [ ] Đã chốt JDK nguồn/đích, runtime tối thiểu và môi trường mục tiêu.
- [ ] Phân biệt rõ build JVM, compiler/toolchain, Java release target, test JVM và runtime.
- [ ] Có resolved dependency graph cho compile, runtime và test của các module chính.
- [ ] Build plugins, processors và compiler extensions được kiểm kê riêng.
- [ ] Gradle/Maven wrapper cùng plugin được đối chiếu với Java compatibility matrix.
- [ ] Framework/BOM mục tiêu và những version overrides được xác nhận.
- [ ] Transitive dependencies có rủi ro hoặc conflict được truy ra đầy đủ.
- [ ] Bytecode instrumentation, mocking và coverage agents đã được xem xét.
- [ ] Đã kiểm tra JDK internals, reflection và module changes.
- [ ] JDBC, JNI/native dependencies, APM/agents và container image được xem xét.
- [ ] Mỗi dependency có mức ưu tiên, owner và lý do nâng/giữ rõ ràng.
- [ ] Có bằng chứng vendor support hoặc kết quả test được ghi nhận cụ thể.
- [ ] Đã tách security patches khỏi JDK blockers khi khả thi.
- [ ] Baseline graph và toolchain versions có thể tái lập.
- [ ] Test chạy với đúng JDK và không bị bỏ qua.
- [ ] Integration tests bao phủ database, network, serialization và agents.
- [ ] Runtime image production thực sự nạp đúng artifacts.
- [ ] Có kế hoạch rollback/roll-forward phù hợp với framework và dữ liệu.
- [ ] Release notes nêu những breaking changes đối với consumers.

Checklist là công cụ xác nhận trạng thái sẵn sàng, không biến một lần test pass thành lời cam kết tuyệt đối rằng mọi dependency đều tương thích mọi workload.

## 25. Mẫu phiếu quyết định dependency

Một bản ghi thực tế có thể dùng mẫu:

~~~text
ID: DEP-JDK-012
Component: annotation-processor-x
Coordinates: group:artifact:current-version
Kind: annotationProcessor
Resolved from: build.gradle / platform constraint
Owner: build-platform
Current JDK: 17
Target JDK: 21
Observed issue: fails to access javac internals
Vendor support: target-version supports JDK 21 (needs verification)
Target version: approved compatible release
Priority: P0 blocker
Prerequisites: compiler plugin compatibility
Validation: compile all modules; check generated output
Rollback: restore prior processor and compiler toolchain
Status: pending / in-progress / verified
~~~

Những mục đánh dấu “needs verification” phải có chứng cứ trước khi thành “verified”; ví dụ trên không phải tuyên bố tương thích của một artifact có tên cụ thể.

Ngoài bảng theo artifact, vẽ dependency chain:

~~~text
Target JDK
  ├─ Build tool compatible version
  │   ├─ Build plugins
  │   └─ Annotation processors
  ├─ Framework/BOM compatible branch
  │   ├─ Bytecode engine
  │   ├─ ORM and JDBC
  │   ├─ HTTP/JSON stack
  │   └─ Test ecosystem
  └─ Runtime image
      ├─ Java agents
      ├─ Native libraries
      └─ JDK modules/providers
~~~

Sơ đồ này giúp thấy rằng không thể chọn mỗi dependency độc lập với constraint của các thành phần ở tầng trên.

## 26. Tình huống tổng hợp: backend chưa thể đổi thẳng sang JDK 21

Giả sử một service:

~~~text
orders-service
  build: Gradle Wrapper + code quality plugins
  compiler: javac + Lombok + mapper processor
  runtime: framework server + JSON + ORM + JDBC
  tests: JUnit + Mockito + coverage agent
  deploy: container JRE + APM agent
~~~

Nhóm muốn chuyển từ Java 17 lên 21. Nếu chỉ sửa `JAVA_HOME`, build có thể lỗi vì processor, test có thể lỗi do bytecode instrumentation, hoặc production không khởi động vì agent.

Một kế hoạch có căn cứ:

**Giai đoạn A — Baseline:** lưu dependency trees, JDK/toolchain versions, artifact metadata, build/test results, container image và JVM flags.

**Giai đoạn B — Build:** đối chiếu Gradle Java compatibility matrix, chọn wrapper/plugin được hỗ trợ, kiểm tra processors với compiler mới.

**Giai đoạn C — Platform:** chọn framework/BOM tương thích, so sánh graph trước/sau và ghi những breaking changes ngoài JDK.

**Giai đoạn D — Runtime:** kiểm tra JDBC, HTTP/TLS, JSON, native/JNI và APM agent với runtime image dự kiến.

**Giai đoạn E — Phân loại:** processor không compile → P0; bytecode parser không đọc class-file mới → P0/P1 tùy đường dùng; agent chưa xác nhận hỗ trợ → P1; utility library tương thích → giữ nguyên.

**Giai đoạn F — Kiểm chứng và rollout:** clean build, unit, smoke, integration, một số phép đo vận hành rồi canary. Khi có lỗi, dùng dependency graph và ma trận A/B/C/D để xác định do JDK, framework hay version override.

Đích đến không phải mọi thư viện đều có version mới nhất. Đích đến là một **tổ hợp dependency có thể tái lập, phù hợp support policy và được chứng minh hoạt động trên JDK mục tiêu**.

## 27. Kết luận

Xác định dependency cần nâng cấp **trước khi đổi JDK** là bước giảm rủi ro quan trọng trong Java Advance Compatibility Migration. Hệ dependency bao gồm build tool, compiler processor, framework/BOM, direct/transitive libraries, agents, native components và runtime image. Chỉ đọc các khai báo `implementation` hoặc tìm “latest version” sẽ bỏ sót nhiều blocker.

Quy trình tốt là chốt JDK đích và mức Java hỗ trợ, lấy **resolved dependency graph**, đối chiếu compatibility matrix và release notes, phát hiện vấn đề JDK internals/bytecode/module, phân loại blocker, rồi nâng theo một thứ tự có kiểm soát. Cuối cùng, chạy kiểm thử trên toolchain và runtime image thật để chứng minh tổ hợp mới vận hành đúng.

Một migration thành công không nhất thiết thay tất cả dependency; nó thay **đúng thành phần bắt buộc phải thay**, giữ những phần đã tương thích, tránh nâng cấp không có mục tiêu và tạo đủ bằng chứng để triển khai an toàn.
