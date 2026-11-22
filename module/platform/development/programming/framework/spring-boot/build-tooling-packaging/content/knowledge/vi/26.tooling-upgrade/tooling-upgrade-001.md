# Lập ma trận tương thích trước khi nâng Java, Spring Boot hoặc công cụ build

## 1. Vì sao cần ma trận tương thích?

Nâng Java, Spring Boot, Maven hoặc Gradle là thay đổi có quan hệ phụ thuộc. Dự án có thể compile với JDK mới nhưng Maven Wrapper không chạy được trên JDK đó; Spring Boot có thể hỗ trợ Java mới nhưng Spring Cloud release train đang dùng chưa hỗ trợ; Gradle core có thể tương thích nhưng một plugin build cũ chưa tương thích Gradle major mới; ứng dụng tạo được JAR nhưng production runtime hoặc container lại quá cũ.

Một lần nâng cấp an toàn cần trả lời trước:

- JDK nào chạy Maven hoặc Gradle daemon?
- JDK nào được dùng để compile, chạy test, tạo Javadoc và chạy ứng dụng?
- Bytecode/API target mà artifact phải hỗ trợ là Java version nào?
- Spring Boot version đích yêu cầu Spring Framework, Java, Maven/Gradle và Servlet container ở mức nào?
- Spring Cloud release train, Spring Data, Security, Kafka, Batch, Micrometer và các BOM liên quan có tương thích không?
- Maven/Gradle Wrapper và từng plugin build có hỗ trợ JDK/build-tool version mới không?
- Test libraries, annotation processors, static analysis, code generation, Docker builder và native-image toolchain có theo kịp không?
- CI có thể build, test và package trên ma trận đích không? Có thể rollback bằng artifact/configuration nào?

**Compatibility matrix** là bảng ghi lại các quan hệ này, kèm nguồn xác nhận, trạng thái kiểm chứng, owner và quyết định. Nó giúp nhóm nhìn thấy rủi ro trước khi thay version trong POM hoặc build script.

Bài này đi qua ví dụ nâng từ Spring Boot 3.5 sang Spring Boot 4.1, đồng thời giải thích cách lập ma trận tổng quát cho dự án Maven hoặc Gradle. Các version cụ thể là snapshot tài liệu chính thức được tra cứu ngày **09-11-2026**; hãy kiểm tra lại trang requirements/release notes khi bắt đầu đợt nâng cấp mới.

## 2. Phân biệt các lớp Java version

Không có một biến “Java version” duy nhất. Một dự án có thể dùng các JDK khác nhau cho các mục đích khác nhau.

| Lớp | Câu hỏi | Nơi cấu hình/kiểm tra |
| --- | --- | --- |
| Build JVM | JVM nào chạy Maven hoặc Gradle daemon? | JAVA_HOME, mvn -v, gradle --version, IDE settings |
| Compiler JDK | javac nào thực sự compile source? | Maven Toolchains hoặc Gradle Java Toolchains |
| Test JVM | JVM nào chạy unit/integration tests? | Surefire/Failsafe fork, Gradle test launcher/toolchain |
| Bytecode target | Class file phải chạy được trên Java version nào? | Maven maven.compiler.release, Gradle options.release |
| Application runtime | Production container/VM dùng JRE/JDK nào? | Docker base image, deployment manifest, server config |
| Native-image toolchain | GraalVM/native build tools version nào? | Native Build Tools, GraalVM, builder image |

Ví dụ:

~~~text
Build JVM:          JDK 21
Compiler toolchain: JDK 21
--release target:   Java 17
Test JVM:           JDK 21
Production runtime: Java 17
~~~

Đây là cấu hình hợp lệ nếu mọi framework/plugin hỗ trợ tổ hợp đó. Compiler JDK 21 có thể tạo bytecode Java 17 và kiểm tra API Java 17 bằng `--release 17`. Nhưng điều này không tự bảo đảm Maven/Gradle plugin, annotation processor hoặc framework runtime tương thích.

### 2.1. Build JVM khác compiler toolchain

`java -version` cho biết Java executable mà shell tìm thấy. `mvn -v` cho biết Java runtime Maven đang sử dụng. `./gradlew --version` hiển thị JVM chạy Gradle. IDE có thể cấu hình Gradle JVM riêng, khác `JAVA_HOME`.

Maven Compiler Plugin có thể chọn JDK thông qua Maven Toolchains; Gradle có Java Toolchains. Vì vậy, một máy có thể chạy Maven trên Java 17 nhưng compile/test bằng JDK 21 nếu project cấu hình rõ.

**Đừng kết luận compile target từ JAVA_HOME.** Hãy kiểm tra build JVM, compiler toolchain và `--release`.

### 2.2. Source/target khác --release

Với Java compiler:

- `source` kiểm soát cú pháp/language level.
- `target` kiểm soát class-file bytecode version.
- `--release` kiểm soát language rules, bytecode target và API Java SE được phép sử dụng.

Chỉ đặt source=17 và target=17 không ngăn source gọi API chỉ xuất hiện ở Java 21 nếu compiler JDK là 21. `--release 17` kiểm tra cả API surface của Java 17. Dùng toolchain để chọn JDK compiler, dùng `--release` để xác định compatibility target.

## 3. Đọc ma trận requirements của Spring Boot

Spring Boot công bố system requirements cho từng dòng version. Tại ngày tra cứu 09-11-2026, tài liệu chính thức cho hai dòng minh họa ghi:

| Thành phần | Spring Boot 3.5.16 | Spring Boot 4.1.x (tài liệu 4.1.2) |
| --- | --- | --- |
| Java tối thiểu | 17 | 17 |
| Java tối đa được ghi nhận | 25 | 27 |
| Spring Framework tối thiểu | 6.2.19+ | 7.0.10+ |
| Maven | 3.6.3+ | 3.6.3+ |
| Gradle | 7.6.4+ hoặc 8.4+ trong dòng 8.x | 8.14+ trong dòng 8.x hoặc dòng 9.x |
| Servlet container baseline | Servlet 5.0+; embedded Tomcat 10.1, Jetty 12.0, Undertow 2.3 | Servlet 6.1+; embedded Tomcat 11.0, Jetty 12.1 |

Nguồn: [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html) và [Spring Boot System Requirements](https://docs.spring.io/spring-boot/system-requirements.html).

**Cách đọc bảng:** Java 17 là minimum runtime của cả hai dòng ví dụ; điều đó không có nghĩa mọi dependency bên thứ ba đều hỗ trợ Java 17 hoặc Java 27. Tài liệu Spring Boot cũng lưu ý third-party projects có thể đặt yêu cầu cao hơn.

Đừng dùng bảng này thay cho migration guide. Nó chỉ trả lời yêu cầu nền tảng/build-tool ở mức Spring Boot; nó không kiểm tra plugin, driver, library, application server, native-image hoặc API thay đổi trong code của dự án.

### 3.1. Đừng trộn requirements của hai dòng

Spring Boot 3.5.16 liệt kê Gradle 7.6.4+ hoặc 8.4+ trong dòng 8.x. Spring Boot 4.1.x yêu cầu Gradle 8.14+ hoặc 9.x. Một dự án dùng Gradle 8.3 có thể phù hợp với một số bản Boot 3.x cũ nhưng không đạt minimum của Boot 3.5.16.

Tương tự, việc Gradle 9 chạy được trên JDK 17 không tự chứng minh Spring Boot 3.5 hỗ trợ Gradle 9. Cần giao của các ma trận:

~~~text
Gradle runtime compatibility
             INTERSECT
Spring Boot build-tool support
             INTERSECT
Plugin compatibility
             =
Tổ hợp build có thể được chấp nhận
~~~

## 4. Ma trận Java, Gradle và Maven

### 4.1. Gradle chạy trên JDK nào?

Gradle có hai khái niệm riêng: JVM chạy Gradle và Java toolchain cho compile/test. Theo Gradle Compatibility Matrix 9.9.0:

- Gradle 9.9 chạy trên JVM Java 17 đến Java 27.
- Java 25 có toolchain support từ Gradle 9.1.0.
- Java 26 có toolchain support từ Gradle 9.4.0.
- Java 27 có toolchain support từ Gradle 9.8.0.
- Gradle 8.14 hỗ trợ toolchain Java 24; Java 25 trở lên cần dòng Gradle mới hơn theo bảng tương thích.

Nguồn: [Gradle Compatibility Matrix 9.9](https://docs.gradle.org/9.9.0/userguide/compatibility.html).

Điều này giải thích vì sao cần tách hai cột `Gradle JVM` và `Java toolchain`. Một bản Gradle có thể chạy trên JDK 17 nhưng chưa hỗ trợ toolchain cho Java 27; hoặc toolchain có thể compile Java mới trong khi daemon JVM vẫn cần một phiên bản khác.

### 4.2. Maven core và plugin có yêu cầu riêng

Maven core, Maven Compiler Plugin, Surefire/Failsafe, Spring Boot Maven Plugin, Enforcer và các extension có version/release cycle riêng.

Tài liệu Maven được tra cứu ghi Maven 3.10.0 yêu cầu JDK 8 trở lên; dòng Maven 4.0.0-rc-7 yêu cầu Java 17. Maven 4 có thay đổi lớn và tài liệu migration mô tả cách chuẩn bị, chạy thử song song, rồi mới chuyển hẳn.

Nguồn: [Maven Releases History](https://maven.apache.org/docs/history) và [Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4).

Vì vậy, khi nâng Maven:

1. Kiểm tra JDK chạy Maven core.
2. Kiểm tra Maven Wrapper distribution.
3. Kiểm tra Maven Plugin API/runtime requirement của từng plugin.
4. Kiểm tra extension, core extension và parent POM.
5. Chạy build trên Maven version đích trước khi bỏ version hiện tại.

Không suy ra plugin hỗ trợ Maven 4 chỉ vì Maven 4 có thể chạy trên JDK hiện tại. Plugin có thể phụ thuộc API Maven hoặc Resolver thay đổi.

## 5. Ma trận Spring Cloud và các Spring projects

Spring Boot BOM quản lý một bộ dependency Spring tương thích, nhưng các dự án Spring Cloud có release train riêng. Phải chọn đúng Cloud train theo Boot generation.

Bảng tương thích Spring Cloud công bố:

| Spring Cloud release train | Spring Boot generation |
| --- | --- |
| 2025.1.x (Oakwood) | Boot 4.0.x; Boot 4.1.x bắt đầu từ 2025.1.2 |
| 2025.0.x (Northfields) | Boot 3.5.x |
| 2024.0.x (Moorgate) | Boot 3.4.x |
| 2023.0.x (Leyton) | Boot 3.2.x; Boot 3.3.x từ 2023.0.2 |
| Các train cũ có dấu * | Đã hết vòng đời hỗ trợ theo trang dự án |

Nguồn: [Spring Cloud project – Release Train compatibility](https://spring.io/projects/spring-cloud/) và [Spring Cloud 2025.1.2 release notes](https://spring.io/blog/2026/06/11/spring-cloud-2025-1-2-aka-oakwood-has-been-released/).

Nếu dự án chuyển từ Boot 3.5 sang Boot 4.1, không giữ nguyên Spring Cloud 2025.0.x rồi chỉ đổi Boot parent. Cần chọn train 2025.1.x và kiểm tra service release cụ thể trong reference docs/release notes trước khi pin version. Một release train có thể bổ sung compatibility trong service release; không chỉ nhìn số năm hoặc tên train.

### 5.1. Các BOM và modules cần rà soát

Tùy ứng dụng, ma trận có thể bao gồm:

- spring-boot-dependencies hoặc Spring Boot parent.
- spring-cloud-dependencies.
- Spring Data BOM.
- Spring Security.
- Spring for Apache Kafka / Spring AMQP.
- Spring Batch, Spring Integration, Spring Modulith.
- Micrometer, Micrometer Tracing, Reactor.
- Spring AI hoặc Spring GraphQL nếu có.

Không override tùy tiện spring-core, spring-context, spring-web, spring-test hoặc dependency do Boot BOM quản lý. Nếu một library yêu cầu version khác, hãy kiểm tra compatibility của toàn dependency graph và lý do override.

### 5.2. Framework compatibility không chỉ là compile

Một ứng dụng có thể compile nhưng fail khi startup vì auto-configuration, bean condition, property rename hoặc thư viện tích hợp. Kiểm tra thêm:

- Spring Boot migration guide theo major/minor version.
- Spring Framework migration notes.
- Spring Cloud release train và compatibility verifier.
- Spring Security filter chain, OAuth/JWT integration.
- Spring Data repository/query behavior và database driver.
- Servlet/Jakarta namespace, container version và deployment model.
- Serialization, HTTP client, messaging protocol và configuration changes.

Với major upgrade, phải có integration test trên runtime thật hoặc môi trường tương đương production.

## 6. Compatibility matrix cần bao phủ những trục nào?

Một ma trận hữu ích không chỉ có Java, Boot và build tool. Tối thiểu hãy xem xét các nhóm:

| Nhóm | Những version/thuộc tính cần ghi |
| --- | --- |
| Java | Build JVM, compiler JDK, test JVM, bytecode target, production runtime, vendor/architecture |
| Spring | Boot, Framework, Cloud train, Data/Security/Integration/Kafka/Batch |
| Build system | Maven/Gradle core, Wrapper, JDK runtime, toolchains |
| Build plugins | Compiler, Surefire/Failsafe, Enforcer, Boot plugin, Kotlin, codegen, quality tools |
| Dependencies | BOMs, test libraries, logging, ORM, HTTP clients, database drivers |
| Runtime platform | Tomcat/Jetty/Undertow, servlet/Jakarta level, OS, libc, CPU architecture |
| Container/native | Docker/Buildpacks builder, run image, GraalVM, Native Build Tools |
| CI | Runner image, JDK installations, cache, network/mirror, parallelism |
| IDE/developer | IntelliJ/Eclipse version, IDE build JVM, local wrapper behavior |
| Operations | TLS/truststore, certificates, secrets, deployment manifests, monitoring/agents |

Mỗi dòng nên có trạng thái và evidence. Ví dụ:

| Thành phần | Current | Target | Evidence | Trạng thái |
| --- | --- | --- | --- | --- |
| Build JVM | JDK 17 | JDK 21 | mvn -v, CI image | Verify |
| Bytecode target | Java 17 | Java 17 | Compiler configuration | Keep |
| Spring Boot | 3.5.16 | 4.1.2 | Official requirements + migration guide | Verify |
| Spring Framework | 6.2.x (Boot-managed) | 7.0.10+ (Boot-managed) | Boot BOM/effective POM | Verify |
| Spring Cloud | 2025.0.x | 2025.1.x service release phù hợp | Spring Cloud compatibility table | Verify |
| Maven | 3.9.x | 3.10.x | Maven Wrapper + plugin requirements | Verify |
| Gradle (nếu dùng) | 8.x | 9.x hoặc 8.14+ | Gradle/Boot compatibility matrix | Verify |
| Compiler/Surefire plugins | Version hiện tại | Version tương thích target | Plugin system requirements/release notes | Verify |
| Container runtime | Tomcat 10.1 / Servlet 6.0 | Tomcat 11 / Servlet 6.1 nếu dùng Boot 4 | Runtime image and deployment docs | Verify |

Các giá trị Current ở đây là ví dụ minh họa; thay bằng dữ liệu thật của repository. Không copy bảng mẫu rồi coi là kết quả audit.

### 6.1. Trạng thái nên dùng

Định nghĩa trạng thái thống nhất trong nhóm:

- SUPPORTED: tài liệu chính thức xác nhận và tổ hợp đã được CI kiểm chứng.
- TESTED: đã chạy build/test trên tổ hợp, nhưng chưa có đủ evidence production.
- NEEDS_CHECK: tài liệu hoặc plugin chưa rõ.
- BLOCKED: có yêu cầu version không giao nhau hoặc test fail.
- NOT_USED: dự án không dùng thành phần đó.
- DEPRECATED/EOL: version đã hết vòng đời hỗ trợ hoặc sắp bị loại bỏ.

Không gắn SUPPORTED chỉ vì build thành công trên máy cá nhân. Hãy lưu link tài liệu, CI run, test report và ngày xác minh.

## 7. Lập ma trận từ trạng thái hiện tại

Trước khi sửa file, ghi nhận baseline có thể tái lập:

~~~bash
java -version
javac -version
./mvnw -version
./gradlew --version
docker version
~~~

Chạy các lệnh phù hợp với build system của dự án. Không bắt buộc project phải có cả Maven và Gradle.

### 7.1. Maven inspection

~~~bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw dependency:tree
./mvnw help:active-profiles
./mvnw -B -ntp clean verify
~~~

Ghi lại:

- Parent POM và Spring Boot version.
- Maven Wrapper distribution.
- Compiler release/toolchain.
- Plugin versions sau khi merge từ parent.
- Dependency versions đã resolve.
- Active profiles và repository/mirror.
- Test results, warnings, deprecations và build duration.

### 7.2. Gradle inspection

~~~bash
./gradlew --version
./gradlew javaToolchains
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew tasks --all
./gradlew clean check
~~~

Khi cần biết version nào được chọn và tại sao:

~~~bash
./gradlew dependencyInsight \
    --dependency spring-core \
    --configuration runtimeClasspath
~~~

Ghi lại:

- gradle-wrapper.properties distribution URL/checksum.
- JVM chạy daemon và Java toolchain.
- Plugin versions trong plugins block và version catalog.
- Dependency constraints/platform/BOM.
- Task graph, test workers và warnings.
- Cache, configuration cache và build scan nếu tổ chức dùng.

### 7.3. Đọc dependency tree thay vì chỉ nhìn file build

POM/build.gradle có thể khai báo dependency không có version trực tiếp vì BOM hoặc plugin management quản lý. Version cuối cùng được resolver chọn mới là thứ ứng dụng chạy.

Maven:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Gradle:

~~~bash
./gradlew dependencyInsight \
    --dependency jackson-databind \
    --configuration runtimeClasspath
~~~

Lưu ý dependency mediation, version constraints, exclusions, optional dependencies và transitive dependencies. Một dependency có thể được kéo vào bởi plugin/test library chứ không nằm trực tiếp trong build file.

## 8. Chọn target có căn cứ và tạo ma trận kiểm thử

Giả sử dự án hiện tại:

~~~text
Spring Boot:      3.5.x
Java runtime:     17
Bytecode target:  17
Maven Wrapper:    3.9.x
Spring Cloud:     2025.0.x (nếu dùng)
Production:       Java 17 container
~~~

Mục tiêu đề xuất:

~~~text
Spring Boot:      4.1.x
Java runtime:     17 hoặc 21 (theo runtime policy)
Bytecode target:  17 nếu cần giữ tương thích Java 17
Maven Wrapper:    3.10.x
Spring Cloud:     2025.1.x service release đã xác nhận
Production:       Java 17/21 image được kiểm tra
~~~

Đây là ví dụ chọn target; không phải mọi tổ chức đều cần đổi build JDK và production runtime cùng lúc. Nếu tổ chức cần duy trì ứng dụng chạy trên Java 17, có thể dùng JDK mới hơn để build nhưng giữ `--release 17` sau khi kiểm tra mọi tool/plugin hỗ trợ.

### 8.1. Không chạy full cross-product vô ích

Nếu ma trận có 3 Boot versions × 4 JDKs × 3 Gradle versions × 2 OS × 2 architectures, số tổ hợp là 144. Không phải tổ hợp nào cũng cần chạy ở mọi commit.

Chia ma trận thành các lớp:

- Required build: target chính thức, chạy trên mọi pull request.
- Compatibility smoke: một số JDK/runtime khác để xác nhận support window.
- Migration lane: current và target stack chạy song song trong giai đoạn nâng cấp.
- Nightly/weekly: OS/architecture/plugin combinations ít gặp.
- Release gate: full integration, packaging, security và deployment tests.

Chọn tổ hợp dựa trên support policy, traffic, runtime fleet và rủi ro; ghi rõ tổ hợp nào được test tự động và tổ hợp nào chỉ có tài liệu xác nhận.

## 9. Nâng Java có kiểm soát

Trước khi nâng Java, kiểm tra:

1. Framework và Spring Boot hỗ trợ JDK target.
2. Maven/Gradle core có thể chạy trên JDK mới.
3. Compiler/toolchain plugin chọn đúng JDK.
4. Annotation processors (Lombok, MapStruct, Querydsl...) hỗ trợ compiler mới.
5. Test libraries và bytecode tools (Mockito, Byte Buddy, JaCoCo, ASM) hỗ trợ class file mới.
6. Native libraries, JDBC drivers, cryptography providers và monitoring agents hỗ trợ runtime.
7. Docker base image và OS architecture cung cấp đúng JRE/JDK.
8. IDE và CI runners có cùng cách chọn JDK.

### 9.1. Maven Compiler Plugin: pin release

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Với Spring Boot parent, `java.version` là convention được parent sử dụng cho cấu hình compiler; `maven.compiler.release` thể hiện rõ bytecode/API target. Kiểm tra effective POM để xác nhận plugin thực sự nhận giá trị này.

### 9.2. Maven Toolchains

Maven runtime và compiler JDK có thể khác nhau. File user `~/.m2/toolchains.xml` (Windows: `%USERPROFILE%\.m2\toolchains.xml`) có thể đăng ký JDK:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

Đường dẫn trên chỉ là ví dụ cho Linux; thay bằng đường dẫn JDK thật. Project cần cấu hình Maven Toolchains Plugin và compiler plugin hỗ trợ toolchain selection. Đừng commit đường dẫn máy cá nhân vào POM.

### 9.3. Gradle Java Toolchains và release

Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Kotlin DSL:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Toolchain chọn JDK cho các task được hỗ trợ; `options.release` giới hạn API và bytecode target. Khi nâng lên Java 21, thay cả toolchain và release chỉ khi chính sách sản phẩm cho phép bỏ Java 17 runtime compatibility.

### 9.4. Kiểm tra class file

Nếu nghi ngờ một dependency được compile với Java version cao hơn dự kiến:

~~~bash
javap -verbose -classpath target/classes com.example.Application
~~~

Tìm `major version` trong output. Một số giá trị phổ biến:

| Java release | Class-file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |
| Java 27 | 71 |

Lệnh `javap` trên một class chỉ kiểm tra class đó. Để rà soát toàn bộ dependency graph, dùng `jdeps`/artifact analysis phù hợp và chạy tests trên runtime tối thiểu cần hỗ trợ.

## 10. Nâng Maven/Gradle Wrapper và plugin

Wrapper giúp mọi developer/CI dùng cùng build-tool distribution. Nhưng wrapper không tự nâng plugin.

### 10.1. Maven Wrapper

File `.mvn/wrapper/maven-wrapper.properties` xác định Maven distribution. Sau khi chọn version đích, cập nhật wrapper bằng Maven Wrapper Plugin hoặc cơ chế được nhóm sử dụng; commit cả wrapper scripts và properties theo chuẩn repo.

Kiểm tra:

~~~bash
./mvnw -version
./mvnw -B -ntp clean verify
~~~

Maven Enforcer có thể khóa Maven và Java runtime của Maven:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>enforce-build-environment</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <requireMavenVersion>
                        <version>[3.9.0,4.0.0)</version>
                    </requireMavenVersion>
                    <requireJavaVersion>
                        <version>[17,28)</version>
                    </requireJavaVersion>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Dải version trên chỉ là ví dụ cho policy Maven 3 + Java 17–27. Nếu tổ chức chọn Maven 4, hãy cập nhật range và xác minh plugin/extension trước. `requireJavaVersion` kiểm tra JVM chạy Maven; nó không thay thế kiểm tra compiler toolchain hoặc bytecode target.

### 10.2. Gradle Wrapper

File `gradle/wrapper/gradle-wrapper.properties` chứa distribution URL. Ví dụ:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
~~~

Nếu tổ chức pin `distributionSha256Sum`, cập nhật bằng checksum lấy từ trang release chính thức của đúng distribution. Không tự tạo hoặc đoán checksum.

Chạy:

~~~bash
./gradlew --version
./gradlew help
./gradlew clean check
~~~

Kiểm tra cả plugin DSL, `pluginManagement`, version catalog, convention plugins, `buildSrc` và included builds. Một plugin third-party có thể yêu cầu Gradle thấp hơn hoặc chưa hỗ trợ Gradle 9 dù Gradle core tương thích JDK.

### 10.3. Plugin inventory

Lập danh sách version/owner cho ít nhất:

- Spring Boot Maven/Gradle Plugin.
- Maven Compiler Plugin / Gradle Java plugin.
- Surefire/Failsafe / Gradle Test.
- Maven Enforcer.
- Kotlin plugin và Kotlin compiler nếu có.
- Lombok, MapStruct, Querydsl và annotation processors.
- JaCoCo, Checkstyle, SpotBugs, PMD, Error Prone.
- Jib, Buildpacks, Docker, Native Build Tools.
- OpenAPI/code generation, protobuf, Avro, frontend/node plugins.
- Maven extensions, Gradle init/convention plugins.

Với mỗi plugin, kiểm tra minimum Maven/Gradle, JDK runtime, API changes, deprecation và version tương thích của plugin phụ thuộc. Không chỉ update plugin lên latest mà không xem release notes.

## 11. Spring Boot major upgrade: thay đổi đồng bộ có kiểm soát

Nâng từ Boot 3.x lên Boot 4.x là thay đổi major generation. Cần rà soát migration guide và dependency stack, không chỉ sửa parent version.

Những vùng thường phải kiểm tra:

- Spring Framework generation và API thay đổi.
- Spring Cloud release train.
- Jakarta EE/Servlet APIs và container version.
- Spring Security configuration/filter chain.
- Spring Data repositories, persistence providers và database drivers.
- Jackson/JSON serialization, HTTP clients, validation.
- Observability: Micrometer, tracing, metrics exporters.
- Logging, test libraries, mock frameworks và test instrumentation.
- Auto-configuration, starters, properties và custom configuration.

### 11.1. Jakarta namespace

Spring Boot 3 đã chuyển hệ sinh thái Jakarta cho nhiều API Java EE trước đây. Khi tiếp tục lên Boot 4, kiểm tra API/container baseline tương ứng với generation mới. Không chỉ tìm/replace `javax` thành `jakarta` trong mọi package: một số `javax.*` thuộc Java SE (ví dụ `javax.crypto`, `javax.net`, `javax.sql`) vẫn là namespace hợp lệ.

Rà soát compile errors, imports, transitive dependencies, servlet container và third-party libraries. Dùng migration guide của đúng Boot generation.

### 11.2. Spring Cloud BOM

Maven ví dụ:

~~~xml
<properties>
    <spring-boot.version>4.1.2</spring-boot.version>
    <spring-cloud.version>2025.1.2</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là minh họa BOM import cho dự án không kế thừa Spring Boot parent. Với Spring Boot parent, dùng dependency management do parent cung cấp và import Cloud BOM theo hướng dẫn của dự án; không tạo dependency management trùng lặp thiếu chủ đích.

`2025.1.2` là release train có công bố tương thích Boot 4.1.0. Khi chốt version cho Boot 4.1.2, kiểm tra service release hiện hành và compatibility reference của train. Không suy luận rằng mọi service release 2025.1.x đều tự động hỗ trợ mọi patch Boot 4.1.x.

### 11.3. Không pin từng Spring Framework dependency để “sửa” lỗi

Nếu Boot BOM quản lý Spring Framework 7.0.x, việc tự pin một module Spring 6.2.x có thể tạo binary mismatch. Kiểm tra `dependency:tree`/`dependencyInsight`, xóa override không cần thiết và chọn BOM tương thích trước khi ép version riêng.

## 12. Kiểm tra plugin và dependency ngoài Spring

Các lỗi upgrade thường đến từ thành phần không thuộc Spring Boot core.

| Nhóm | Ví dụ rủi ro | Cách kiểm tra |
| --- | --- | --- |
| Annotation processor | Lombok không hiểu compiler mới | Chạy compile/test với JDK target; kiểm tra release notes |
| Bytecode tools | ASM/Byte Buddy chưa đọc class file mới | Chạy tests, agent và instrumentation |
| Coverage | JaCoCo chưa hỗ trợ JDK/class version mới | Chạy verify và kiểm tra coverage report |
| Mocking | Mockito/Byte Buddy không instrument được class | Test mocks, final classes, inline mock maker |
| Database | JDBC driver/TLS/SQL dialect thay đổi | Integration tests với DB version thật |
| Container | Testcontainers/Docker API mismatch | Chạy test trên CI Docker daemon |
| Security | Spring Security config hoặc crypto provider đổi | AuthN/AuthZ regression tests |
| Messaging | Kafka/Rabbit clients hoặc Spring integration mismatch | Contract/integration tests |
| Observability | Micrometer/agent/exporter mismatch | Startup + metrics/tracing smoke tests |
| Code generation | OpenAPI/protobuf/Avro plugin không tương thích | Regenerate và kiểm tra diff |
| Native | GraalVM/Native Build Tools không tương thích | Native compile và native runtime tests |

**Build thành công không đủ.** Các plugin trên có thể chỉ fail khi chạy một task ít dùng, generate source, instrument test hoặc build native image. Thêm những task đó vào migration validation nếu project sử dụng.

## 13. Kiểm tra runtime/container và deployment platform

Compatibility matrix phải bao gồm nơi artifact thực sự chạy:

- JRE/JDK vendor và patch version.
- Docker base image/tag/digest.
- Linux distribution, glibc/musl và CPU architecture.
- Servlet container/Servlet API nếu deploy WAR hoặc external container.
- Native-image builder và runtime.
- TLS/truststore/certificates, crypto provider và FIPS mode.
- JDBC driver/database version, broker version và external services.
- Kubernetes base image, probes, resource limits, environment variables và secrets.

Ví dụ, Boot 3.5 và Boot 4.1 có Servlet/container baseline khác nhau trong system requirements. Nếu ứng dụng deploy WAR vào external Tomcat, chỉ nâng Spring Boot JAR build không đảm bảo Tomcat production đã đạt yêu cầu.

### 13.1. Container image matrix

| Thuộc tính | Current | Target |
| --- | --- | --- |
| Image base | Tag/digest đang chạy | Tag/digest đã scan |
| JRE | Java 17 vendor/patch | Java 17 hoặc 21 đã test |
| OS/libc | Distribution hiện tại | Distribution target |
| Architecture | amd64 | amd64/arm64 nếu cần |
| Buildpacks/builder | Builder version | Builder version đã xác nhận |
| Runtime port | Port đang expose | Port/service mapping |
| Health endpoint | Probe hiện tại | Probe đã test |
| User | UID/GID | Non-root policy |

Không dùng tag `latest` trong ma trận release nếu cần tái lập. Pin digest khi chính sách container yêu cầu, lưu SBOM/scan result và test image thực tế.

## 14. Quy trình nâng cấp theo từng bước

Một sequence có thể review được:

1. **Baseline:** khóa commit hiện tại, ghi version/toolchain/dependency tree, chạy full tests và lưu CI evidence.
2. **Chọn target:** xác định Boot/Java/build-tool generation dựa trên official requirements, support policy và deadline vận hành.
3. **Ma trận dependency:** xác minh Spring Cloud/BOM, third-party libraries, plugins, drivers và runtime platform.
4. **Build JDK:** chuẩn hóa JDK chạy Maven/Gradle và toolchain trên developer/CI.
5. **Wrapper:** nâng Maven/Gradle Wrapper trong một thay đổi độc lập, chạy build trên version mới.
6. **Plugin build:** cập nhật compiler/test/quality/codegen/container plugins theo compatibility docs.
7. **Java target:** quyết định giữ bytecode target cũ hay nâng; cấu hình --release/toolchain rõ ràng.
8. **Spring Boot:** nâng parent/plugin/BOM và Cloud train phù hợp; xử lý migration guide.
9. **Code/dependencies:** sửa API/config/imports, dependency overrides và deprecated usages.
10. **Verification:** compile, unit tests, integration tests, package, startup smoke, security/coverage/native tasks nếu có.
11. **CI matrix:** chạy current và target lanes song song; xác minh cache, artifacts, reports và runtime images.
12. **Canary/release:** triển khai thử vào môi trường gần production, quan sát metrics/logs/traces và giữ rollback plan.

Có thể gộp một số bước nếu chúng phụ thuộc chặt chẽ, ví dụ Boot và Spring Cloud BOM. Tuy nhiên, giữ lại baseline và test evidence sau mỗi mốc để biết thay đổi nào gây regression.

### 14.1. Vì sao nên nâng Wrapper trước khi đổi Spring Boot?

Nâng wrapper độc lập giúp tách lỗi build-system khỏi lỗi framework. Nếu đổi đồng thời JDK, Gradle, Boot, Cloud, plugins và dependency versions, một build fail có thể có nhiều nguyên nhân. Thứ tự có thể thay đổi theo project; điều quan trọng là mỗi bước có evidence và có thể xác định nguyên nhân.

### 14.2. Khi nào phải nâng Java cùng Boot?

Nếu target Boot yêu cầu Java tối thiểu cao hơn runtime hiện tại, Java upgrade là bắt buộc. Nếu cả hai Boot generations đều hỗ trợ Java hiện tại, có thể giữ runtime/bytecode target trước để cô lập migration framework. Sau khi Boot migration pass, nâng Java runtime trong change riêng để đo được tác động.

## 15. CI matrix: xác minh trên môi trường thực

Ví dụ GitHub Actions kiểm tra Java 17 và 21 cho một target build:

~~~yaml
name: compatibility-check

on:
  pull_request:
  workflow_dispatch:

jobs:
  verify:
    strategy:
      fail-fast: false
      matrix:
        java: [17, 21]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven
      - name: Verify with Maven Wrapper
        run: ./mvnw -B -ntp clean verify
~~~

Đây là ví dụ lane Maven. Nếu dùng Gradle, dùng Gradle setup action/JDK setup tương ứng và chạy `./gradlew clean check`. Kiểm tra action version theo policy CI hiện hành.

### 15.1. Ma trận current và target

| Lane | Boot | Build tool | JDK | Mục đích |
| --- | --- | --- | --- | --- |
| Current | Boot 3.5.x | Wrapper hiện tại | JDK 17 | Baseline/rollback |
| Target | Boot 4.1.x | Wrapper đã nâng | JDK 17 hoặc 21 | Migration validation |
| Compatibility | Boot 4.1.x | Wrapper target | JDK 25 nếu policy cần | Support-window check |

Không bắt buộc mọi lane chạy trên mọi pull request. Dùng required lane cho target, nightly lane cho support-window và release gate cho full integration.

### 15.2. CI cache không được che dependency drift

Sau khi đổi Wrapper, JDK hoặc dependency BOM:

- Kiểm tra cache key có chứa build-tool/JDK/lockfile version phù hợp.
- Xác minh build có thể resolve dependencies trong cache lạnh.
- Không reuse target/Gradle build output từ môi trường khác để tuyên bố clean build pass.
- Lưu dependency lockfiles/verification metadata nếu project dùng.
- Ghi lại artifact checksum, build commit và tool versions.

## 16. Bằng chứng cần có trước khi duyệt nâng cấp

Một migration PR nên có evidence cụ thể:

- Compatibility matrix đã điền Current, Target, status, source và owner.
- Official system requirements/migration guide links.
- Maven/Gradle Wrapper version và JDK build/test/runtime.
- Effective POM hoặc Gradle dependency report.
- Dependency tree/diff và version overrides được giải thích.
- Compiler release/toolchain config.
- Unit + integration + contract tests.
- Package/JAR/WAR/container image build.
- Application startup/readiness/health smoke test.
- Security/coverage/static analysis/code generation tasks.
- Native-image test nếu project sử dụng.
- CI runs trên target JDK/OS/architecture.
- Deployment canary/rollback instructions.

**Không ghi PASS khi chỉ compile pass.** Đặt status theo từng lớp để reviewer thấy rõ phần nào đã được kiểm chứng và phần nào mới dựa vào tài liệu.

## 17. Troubleshooting các lỗi tương thích thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Maven không khởi động trên JDK mới | Maven core hoặc extension không hỗ trợ runtime | mvn -v, Maven requirements và extension versions |
| Gradle daemon báo unsupported Java | Wrapper/Gradle version chưa hỗ trợ JVM chạy daemon | Gradle compatibility matrix, ./gradlew --version |
| Compile báo unsupported class version | Dependency/plugin bytecode cao hơn JDK đang chạy | Xác định class file version, nâng runtime hoặc chọn dependency phù hợp |
| Compile pass nhưng production UnsupportedClassVersionError | Bytecode target cao hơn JVM production | Kiểm tra --release, image JRE và class file |
| NoSuchMethodError/NoClassDefFoundError | Dependency graph bị lệch hoặc binary incompatibility | dependency:tree, dependencyInsight, BOM/version overrides |
| Spring application không startup | Framework/Cloud train/config mismatch hoặc auto-configuration đổi | Migration guide, condition report, logs và BOM |
| Spring Cloud compatibility verifier fail | Boot version không thuộc release train | Chọn đúng Cloud train/service release |
| Servlet API ClassNotFoundException | Container hoặc Servlet/Jakarta generation không tương thích | Servlet baseline, embedded/external container |
| Lombok/MapStruct compile fail | Annotation processor chưa hỗ trợ compiler JDK | Plugin release notes và processor version |
| JaCoCo/Byte Buddy fail | Bytecode instrumentation chưa hỗ trợ class version | Nâng plugin/library và chạy test instrumentation |
| Gradle plugin không resolve | Plugin marker/repository/version sai hoặc plugin không hỗ trợ Gradle mới | pluginManagement, plugin portal docs và release notes |
| Maven plugin báo API incompatibility | Plugin chưa hỗ trợ Maven core mới | Plugin system requirements và Maven compatibility plan |
| Build chỉ fail trong IDE | IDE build JVM hoặc annotation processing khác CLI | Đồng bộ IDE JDK/Gradle JVM và wrapper |
| Docker image chạy local nhưng fail production | Base image, architecture, libc, env hoặc secrets khác | Kiểm tra digest, runtime config và deployment platform |
| Native build fail sau JDK upgrade | GraalVM/Native Build Tools không khớp | Native requirements, builder version và native smoke test |
| Test flaky khi chạy song song | Shared state/port/database hoặc toolchain race | Unique resources, test isolation và concurrency limits |
| Dependency version thay đổi dù POM không đổi | BOM, repository metadata, dynamic/SNAPSHOT version hoặc cache | Pin release, lock dependency, inspect resolved graph |
| Maven Wrapper tải sai distribution | distributionUrl/mirror/cache cũ | Kiểm tra maven-wrapper.properties |
| Gradle Wrapper checksum mismatch | Distribution bị đổi hoặc checksum sai | Dừng build và xác minh checksum từ Gradle release source |

### Trình tự chẩn đoán

1. Lấy java -version, mvn -v hoặc gradle --version.
2. Xác định build JVM, compiler toolchain, bytecode target và production runtime.
3. Kiểm tra Spring Boot system requirements theo version chính xác.
4. Kiểm tra Spring Cloud train và Spring BOMs.
5. Xem effective POM hoặc dependency insight để tìm version thực sự được resolve.
6. Xác minh plugin requirements và wrapper distribution.
7. Chạy compile/test/package tách biệt để xác định phase fail.
8. Chạy application startup và integration tests trên đúng runtime/container.
9. So sánh current/target CI evidence; không bỏ qua lỗi bằng cách tắt verifier hoặc exclude test.

## 18. Rollback và rollout

Một upgrade chưa hoàn tất cho đến khi có cách quay lại nếu production regression xuất hiện.

Trước khi deploy:

- Giữ release artifact của current version và checksum.
- Lưu Docker image digest/tag hiện tại.
- Giữ deployment manifest/config version trước migration.
- Kiểm tra schema/database migration có backward-compatible không.
- Nếu migration DB không thể rollback, dùng expand-and-contract: thêm schema tương thích trước, deploy code, rồi mới xóa schema cũ ở release sau.
- Theo dõi startup failures, latency, error rate, memory, GC, connection pool và message lag.
- Xác định điều kiện rollback và người chịu trách nhiệm.

Không rollback riêng JDK/Boot trong khi artifact đã compile bằng API mới hoặc database schema đã thay đổi không tương thích. Rollback cần khớp cả artifact, runtime image, configuration và data migration.

## 19. Mẫu ma trận để dùng trong dự án

Sao chép cấu trúc này vào migration issue/PR hoặc tài liệu release:

| Nhóm | Current | Target | Yêu cầu nguồn | Evidence thực tế | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Build JVM | | | | | | |
| Compiler JDK/toolchain | | | | | | |
| Test JVM | | | | | | |
| Bytecode release | | | | | | |
| Production JRE/JDK | | | | | | |
| Spring Boot | | | | | | |
| Spring Framework | | | | | | |
| Spring Cloud train | | | | | | |
| Maven/Gradle Wrapper | | | | | | |
| Compiler/Test plugins | | | | | | |
| Annotation/codegen plugins | | | | | | |
| Runtime dependencies/BOMs | | | | | | |
| Database/broker drivers | | | | | | |
| Servlet/container | | | | | | |
| Docker/buildpacks/native | | | | | | |
| CI runner/OS/architecture | | | | | | |
| Security/observability agents | | | | | | |
| Deployment/rollback | | | | | | |

Mỗi hàng phải có owner và evidence trước khi đánh dấu hoàn tất. Nếu không dùng thành phần nào, ghi NOT_USED thay vì để trống để reviewer biết đã xem xét.

## 20. Bài thực hành và tiêu chí hoàn thành

Thực hành trên branch migration thử nghiệm:

1. Ghi lại java -version, javac -version, ./mvnw -version hoặc ./gradlew --version.
2. Lấy Maven effective POM/dependency tree hoặc Gradle toolchains/dependency insight.
3. Điền Current cho Java build JVM, compiler, bytecode, runtime, Spring Boot/Cloud, wrapper, plugins, dependencies và container.
4. Chọn một target Boot/Java/build tool; tìm official system requirements và migration guides theo đúng version.
5. Xác nhận Spring Cloud release train/BOM nếu project có Spring Cloud.
6. Kiểm tra từng plugin (compiler, test, coverage, annotation processor, codegen, container/native) và ghi source/version constraints.
7. Tạo ma trận CI nhỏ cho current và target; giữ một baseline lane để so sánh.
8. Chuẩn hóa JDK/toolchain và bytecode release; chạy clean compile/test.
9. Nâng wrapper trong một change có evidence; chạy clean verify/check.
10. Nâng Boot/BOM và xử lý migration guide; chạy integration/startup tests.
11. Kiểm tra JAR/WAR/container image bằng đúng production runtime và architecture.
12. Kiểm tra security/coverage/native tasks nếu dự án sử dụng.
13. Ghi mọi blocker, workaround, owner và version cần nâng tiếp.
14. Lập rollout/rollback plan có artifact digest và database migration strategy.
15. Chỉ đánh dấu matrix SUPPORTED khi tài liệu và CI evidence đều phù hợp; lưu ngày kiểm tra.

**Đạt yêu cầu khi:** bạn giải thích được khác biệt giữa build JVM, compiler toolchain, bytecode target và runtime; lập được matrix có nguồn chính thức cho Boot/Java/Maven/Gradle/Spring Cloud; phát hiện được plugin/dependency/container chưa tương thích; và có CI evidence cùng rollback plan trước khi nâng cấp production.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.5 – System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot – System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Cloud – Release Train Compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2025.1.2 Release Notes](https://spring.io/blog/2026/06/11/spring-cloud-2025-1-2-aka-oakwood-has-been-released/)
- [Gradle 9.9 – Compatibility Matrix](https://docs.gradle.org/9.9.0/userguide/compatibility.html)
- [Gradle – JVM Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle – Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Apache Maven – Releases History](https://maven.apache.org/docs/history)
- [Apache Maven – Starting with Maven 4](https://maven.apache.org/guides/mini/guide-migration-to-mvn4)
- [Apache Maven Compiler Plugin – Setting the --release of the Java Compiler](https://maven.apache.org/plugins-archives/maven-compiler-plugin-LATEST/examples/set-compiler-release.html)
- [Apache Maven – Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Apache Maven – Plugin Compatibility Plan](https://maven.apache.org/developers/compatibility-plan.html)
