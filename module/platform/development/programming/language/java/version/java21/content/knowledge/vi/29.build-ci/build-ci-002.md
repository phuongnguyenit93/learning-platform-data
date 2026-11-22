# Đồng bộ compile, test, integration test và đóng gói trên Java 21

Một pipeline Java 21 đáng tin cậy cần dùng cùng một mục tiêu Java cho toàn bộ vòng đời: biên dịch mã nguồn, chạy unit test, chạy integration test và tạo artifact để triển khai. Chỉ đặt source hoặc target bằng 21 là chưa đủ; compiler có thể dùng API mới hơn, test có thể chạy trên JVM khác và bước đóng gói có thể lấy nhầm output được build bằng JDK khác.

Nên chuẩn hóa JDK 21 bằng toolchain hoặc môi trường CI được kiểm soát, đặt --release 21 cho compiler, chạy test trên Java 21, thực hiện integration test trong lifecycle bắt buộc và chỉ đóng gói artifact sau khi các bước kiểm tra thành công. Bài viết trình bày cách đồng bộ với Maven và Gradle, cùng các nguyên tắc áp dụng cho CI.

## 1. Phân biệt JDK dùng để build, compiler target và runtime

Trong pipeline có ba khái niệm cần tách biệt:

| Thành phần | Vai trò | Cần kiểm soát điều gì? |
|---|---|---|
| JDK chạy build tool | JVM chạy Maven/Gradle, plugin và một phần build logic | Phiên bản JDK mà agent CI dùng để khởi chạy build |
| Compiler/toolchain | JDK thực hiện biên dịch source và test source | Compiler phù hợp Java 21 và API/bytecode đích |
| Test/deployment runtime | JVM chạy unit test, integration test và ứng dụng | Runtime thực tế hỗ trợ class file và API mà ứng dụng sử dụng |

Ba thành phần có thể dùng cùng JDK 21, đây là cấu hình đơn giản và dễ kiểm soát nhất khi nâng cấp lên Java 21. Một số build tool có thể chạy trên JDK mới hơn nhưng dùng toolchain JDK 21 để compile hoặc test; khi đó cần cấu hình tường minh và xác nhận plugin tương thích với JVM chạy build.

Đặc biệt, --release 21 không tự chọn JVM chạy Maven/Gradle, không buộc test chạy trên Java 21 và không thay thế toolchain. Nó giới hạn API Java có thể tham chiếu và tạo bytecode theo release 21.

## 2. Vì sao nên dùng --release 21?

Khi compile, có ba tùy chọn thường được nhắc đến:

- --source 21: giới hạn cú pháp ngôn ngữ được chấp nhận.
- --target 21: tạo class file cho nền tảng Java 21.
- --release 21: kết hợp source level, target class-file version và tập API Java SE được hỗ trợ trong release 21.

Với ứng dụng phát hành cho Java 21, --release 21 thường là lựa chọn phù hợp nhất. Nếu chỉ đặt source và target khi compiler chạy trên JDK mới hơn, mã có thể vô tình tham chiếu API chỉ xuất hiện ở release mới hơn rồi không chạy được trên Java 21.

Ví dụ:

~~~bash
javac --release 21 -d out src/com/example/App.java
~~~

Class file được tạo có major version 65. Runtime Java 21 hiểu class file này; runtime cũ hơn Java 21 không được bảo đảm chạy được.

Có thể kiểm tra class file:

~~~bash
javap -verbose out/com/example/App.class
~~~

Trong output, tìm major version: 65.

### --release không kiểm soát mọi dependency

--release 21 áp dụng cho mã được biên dịch bởi javac. Nó không bảo đảm:

- Dependency bên thứ ba có bytecode tương thích Java 21.
- Annotation processor chạy được trên JDK của build.
- Maven/Gradle plugin tương thích với JDK đang chạy build.
- Test và integration test được thực thi trên Java 21.
- Runtime production có đủ module, native library hoặc cấu hình mà ứng dụng cần.

Vì vậy, vẫn phải kiểm tra dependency, plugin, processor và runtime riêng.

## 3. Chuẩn hóa JDK trong môi trường CI

Mỗi job cần chọn JDK rõ ràng trước khi chạy build. Không dựa vào JDK mặc định cài trên runner hoặc biến môi trường được cấu hình ngầm.

Một bước xác nhận môi trường nên in ra:

~~~bash
java -version
javac -version
~~~

Với Maven:

~~~bash
./mvnw --version
~~~

Với Gradle:

~~~bash
./gradlew --version
~~~

Các output này giúp xác nhận JVM chạy build tool. Nếu dùng toolchain khác với JVM chạy build, cần kiểm tra thêm compiler/test launcher mà toolchain đã chọn.

### Quy tắc cho runner

1. Cài JDK 21 từ distribution được tổ chức chấp thuận.
2. Đặt JAVA_HOME và PATH cho đúng JDK trước khi gọi wrapper.
3. Dùng Maven Wrapper hoặc Gradle Wrapper được commit trong repository.
4. Không tải một phiên bản build tool không cố định ở mỗi lần chạy.
5. Ghi lại JDK vendor, phiên bản đầy đủ và build tool version trong log CI.
6. Dùng cache dependency theo key có xét build tool, JDK và lock/config dependency; không cache output build cũ giữa các JDK hoặc commit không tương thích.

Nếu dự án hỗ trợ nhiều JDK, hãy có job riêng cho từng runtime mục tiêu. Job chính tạo artifact Java 21 nên phải compile và kiểm thử theo Java 21; job kiểm tra tương thích với JDK mới hơn có thể chạy bổ sung nhưng không thay thế job Java 21.

## 4. Cấu hình Maven cho Java 21

Với Maven, đặt release level trong cấu hình chung và pin phiên bản plugin. Ví dụ dưới đây dùng Maven Compiler Plugin và Surefire/Failsafe phiên bản hỗ trợ Java 21; hãy cập nhật theo phiên bản ổn định được tổ chức phê duyệt và giữ version rõ ràng trong repository.

~~~xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>21</release>
                <encoding>UTF-8</encoding>
            </configuration>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.4</version>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-failsafe-plugin</artifactId>
            <version>3.5.4</version>
            <executions>
                <execution>
                    <goals>
                        <goal>integration-test</goal>
                        <goal>verify</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Các version trong ví dụ là mốc cấu hình cụ thể, không có nghĩa chúng luôn là bản mới nhất. Dự án nên quản lý plugin version tập trung, cập nhật bảo mật và xác nhận compatibility trước khi nâng version.

### Compile và unit test

Maven Compiler Plugin biên dịch main source và test source theo cấu hình release. Surefire chạy unit test trong phase test. Test engine, ví dụ JUnit Jupiter, phải được khai báo trong dependency của dự án; chỉ cấu hình Surefire không tự thêm test framework.

Chạy:

~~~bash
./mvnw --batch-mode --no-transfer-progress clean test
~~~

Lệnh này dọn output cũ, compile và chạy unit test. Nó chưa chạy các goal integration test của Failsafe vì lifecycle dừng ở phase test.

### Integration test và verify

Failsafe chạy integration test trong phase integration-test và tổng hợp kết quả ở phase verify. Nên chạy lifecycle đến verify:

~~~bash
./mvnw --batch-mode --no-transfer-progress clean verify
~~~

Không dùng riêng mvn integration-test làm lệnh CI thông thường nếu quy trình còn cần phase post-integration-test để dọn dịch vụ hoặc verify để Failsafe xác nhận kết quả. verify chạy qua các phase trước đó theo Maven lifecycle, bao gồm compile, test và package.

Lưu ý thứ tự lifecycle: Maven tạo JAR/WAR ở phase package, trước integration-test. Failsafe chạy integration test sau khi artifact đã được tạo và báo kết quả cuối ở verify. Vì vậy, artifact có thể tồn tại trong thư mục target dù integration test thất bại; CI chỉ được publish artifact khi toàn bộ lệnh verify kết thúc thành công.

Theo quy ước đặt tên, unit test thường dùng hậu tố Test, còn integration test có thể dùng IT, ITCase hoặc cấu hình include/exclude phù hợp trong Failsafe. Điều quan trọng là hai nhóm được phân tách rõ và CI thực sự chạy cả hai.

### Toolchain Maven

Nếu build process chạy trên một JDK khác nhưng cần dùng compiler hoặc test JDK 21, cấu hình Maven Toolchains và khai báo JDK 21 trong file toolchain của môi trường build. Không commit đường dẫn JDK tuyệt đối của máy developer vào repository. CI cần cung cấp JDK đúng vị trí và xác nhận Maven đã chọn toolchain đó.

Nếu không có yêu cầu chạy Maven trên JDK khác, cách đơn giản nhất là chạy chính Maven Wrapper bằng JDK 21 trong CI và xác nhận qua ./mvnw --version.

## 5. Cấu hình Gradle Java toolchain

Với Gradle, dùng Java toolchain để chọn JDK cho compile và test. Đồng thời đặt options.release để giới hạn API và bytecode về Java 21.

Ví dụ Kotlin DSL trong build.gradle.kts:

~~~kotlin
import org.gradle.language.base.plugins.LifecycleBasePlugin

plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
    options.encoding = "UTF-8"
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

Java toolchain giúp Gradle chọn JDK 21 cho compiler và test launcher. options.release.set(21) giữ API/bytecode mục tiêu rõ ràng ngay cả khi cấu hình build được thay đổi sau này.

Gradle Wrapper phải dùng phiên bản còn được hỗ trợ và tương thích với JDK chạy Gradle. Gradle 8.5 trở lên hỗ trợ chạy Gradle trên JDK 21; Java 21 toolchain được hỗ trợ từ Gradle 8.4. Đây là các mốc hỗ trợ tối thiểu, không phải khuyến nghị giữ build tool ở phiên bản cũ. Nên nâng wrapper lên release ổn định hiện hành đã được dự án kiểm thử.

### Tách integration test bằng source set

Nếu dự án cần source set riêng cho integration test, có thể tạo task và gắn vào lifecycle check:

~~~kotlin
val integrationTestSourceSet = sourceSets.create("integrationTest") {
    compileClasspath += sourceSets.main.get().output
    runtimeClasspath += sourceSets.main.get().output
}

configurations[integrationTestSourceSet.implementationConfigurationName]
    .extendsFrom(configurations.testImplementation.get())
configurations[integrationTestSourceSet.runtimeOnlyConfigurationName]
    .extendsFrom(configurations.testRuntimeOnly.get())

val integrationTest by tasks.registering(Test::class) {
    description = "Runs integration tests."
    group = LifecycleBasePlugin.VERIFICATION_GROUP
    dependsOn(integrationTestSourceSet.classesTaskName)
    testClassesDirs = integrationTestSourceSet.output.classesDirs
    classpath = integrationTestSourceSet.runtimeClasspath
    shouldRunAfter(tasks.test)
    useJUnitPlatform()
}

tasks.named("check") {
    dependsOn(integrationTest)
}
~~~

Source set này tạo cấu hình compile/runtime riêng và kế thừa các dependency test cần dùng. Có thể bổ sung Testcontainers, driver hoặc fixture riêng cho integration test mà không đưa các dependency đó vào runtime production.

Với Gradle, check chạy unit test và các verification task được gắn vào nó. build bao gồm check và assemble, nên thường là lifecycle phù hợp để CI vừa xác minh vừa đóng gói.

## 6. Phân tách unit test và integration test

Unit test và integration test có mục tiêu, chi phí và dependency khác nhau:

| Tiêu chí | Unit test | Integration test |
|---|---|---|
| Phạm vi | Một class hoặc đơn vị nhỏ | Nhiều thành phần thực sự phối hợp |
| Dependency ngoài | Thường dùng fake/mock | Có thể dùng database, broker, HTTP service hoặc filesystem thật |
| Thời gian | Nhanh, chạy thường xuyên | Chậm hơn, cần khởi tạo và dọn môi trường |
| Tính ổn định | Cần độc lập, deterministic | Cần kiểm soát readiness, timeout, port và dữ liệu |
| Vị trí trong CI | Mỗi commit/PR | Mỗi PR hoặc pipeline theo chính sách dự án |

Unit test nên xác minh logic, edge case và lỗi mà không cần khởi động hạ tầng bên ngoài. Integration test xác minh giao tiếp thật giữa các thành phần, cấu hình runtime, schema và hành vi của dependency.

### Cấu hình integration environment

Khi integration test cần database hoặc message broker:

- Dùng instance tạm thời, container hoặc service riêng cho job.
- Pin image/version của dependency để kết quả có thể tái lập.
- Chờ health check/readiness trước khi chạy test.
- Tạo database/schema hoặc topic riêng cho job; tránh dùng chung dữ liệu giữa các pipeline.
- Đặt timeout cho kết nối và thao tác để test không treo vô hạn.
- Dọn tài nguyên trong teardown/finally, kể cả khi test thất bại.
- Không dùng credential production trong CI.

Nếu dùng Testcontainers, xác nhận Docker/container runtime có sẵn trên runner và phiên bản Testcontainers tương thích JDK 21. Nếu runner không hỗ trợ container, dùng service container do CI cung cấp hoặc môi trường integration chuyên biệt.

### Không để integration test phụ thuộc thứ tự

Test nên tự tạo dữ liệu cần thiết và dọn dữ liệu sau khi chạy. Không để test B chỉ chạy đúng sau test A đã tạo record. Nếu chạy song song, dùng schema/database/namespace riêng hoặc khóa dữ liệu theo test để tránh race condition.

## 7. Đảm bảo integration test chạy trên đúng Java 21

Một lỗi phổ biến là compile bằng Java 21 nhưng test fork chạy bằng JDK khác. Điều này có thể khiến test không phát hiện lỗi runtime trên Java 21 hoặc khiến CI xanh trên JDK mới hơn trong khi production dùng Java 21.

Kiểm tra:

1. JVM chạy Maven/Gradle.
2. JDK được toolchain chọn cho compile.
3. JVM launcher được Surefire/Failsafe hoặc Gradle Test dùng.
4. JVM chạy ứng dụng trong integration test, nếu test khởi chạy tiến trình riêng/container.
5. JVM thực tế của image hoặc môi trường deployment.

Với Maven, nếu CI đã chạy Maven Wrapper bằng JDK 21, Surefire và Failsafe thông thường sẽ dùng JVM đó trừ khi có toolchain hoặc cấu hình fork khác. Với Gradle, toolchain cấu hình trong Java plugin được dùng cho compile và test task.

Nếu integration test khởi chạy ứng dụng qua Docker image, kiểm tra base image runtime và chạy smoke test trên chính image đó. Việc test trên JVM của runner không chứng minh image production cũng dùng đúng Java.

## 8. Đóng gói artifact sau khi kiểm tra

Artifact Java thường là JAR hoặc WAR. Bước package phải sử dụng output của cùng build; tránh chạy một lệnh build riêng sau test bằng JDK hoặc dependency khác. Với Maven, package diễn ra trước integration-test trong lifecycle; với Gradle, assemble và verification có thể được lập lịch độc lập. Trong cả hai trường hợp, CI chỉ publish artifact khi mọi bước bắt buộc đều thành công.

Với Maven:

~~~bash
./mvnw --batch-mode --no-transfer-progress clean verify
~~~

JAR thường được tạo trong target/. Với Gradle:

~~~bash
./gradlew --no-daemon clean build
~~~

JAR thường được tạo trong build/libs/.

### Kiểm tra artifact

Sau khi package, kiểm tra:

- Tên, version và loại artifact đúng với release.
- Manifest có các thuộc tính cần thiết, ví dụ Main-Class nếu tạo executable JAR.
- Class file mục tiêu có major version 65 nếu artifact được compile cho Java 21.
- Dependency runtime được đóng gói hoặc được cung cấp theo đúng chiến lược triển khai.
- Không có test report, file tạm, private key, password hoặc secret trong artifact.
- Smoke test có thể khởi chạy artifact với Java 21 trong môi trường tương đương production.

Có thể xem nội dung JAR:

~~~bash
jar --list --file target/application.jar
javap -verbose -classpath target/application.jar com.example.Application
~~~

Đường dẫn và tên class cần thay theo artifact thực tế. Với ứng dụng Gradle, đổi đường dẫn sang file trong build/libs/.

### Test classpath không nhất thiết là artifact đã đóng gói

Integration test mặc định có thể chạy trên test classpath gồm class output và dependency, không nhất thiết khởi chạy đúng file JAR/WAR cuối cùng. Nếu mục tiêu là xác nhận artifact có thể chạy, hãy thêm smoke test riêng: khởi chạy JAR/container đã đóng gói, chờ health endpoint hoặc kiểm tra hành vi chính, rồi dừng tiến trình.

## 9. Đồng bộ cấu hình đóng gói và runtime

Compile đúng Java 21 vẫn chưa đủ nếu runtime image thiếu thành phần cần thiết. Cần đồng bộ:

- JDK/JRE runtime version và vendor theo chính sách.
- Base image và OS libraries.
- JVM flags, system properties và environment variables.
- Module cần thiết nếu dùng custom runtime image.
- Native library và kiến trúc CPU.
- Timezone, locale, encoding và certificate trust store.
- File cấu hình được mount khi deploy, không nhúng secret vào JAR.

Nếu tạo custom runtime image bằng jlink, kiểm tra module closure và chạy integration/smoke test trên image đã tạo. jlink chỉ đóng gói module runtime; nó không tự bảo đảm mọi native dependency hoặc cấu hình hệ điều hành đã có.

Không giả định artifact chạy được trên mọi JDK chỉ vì class file version là 65. Ứng dụng còn có thể phụ thuộc API, module, provider, native code hoặc behavior cụ thể của runtime.

## 10. Reproducible build và quản lý dependency

Để hai lần build từ cùng source có kết quả gần như giống nhau:

- Dùng wrapper và pin build tool version.
- Khóa dependency version; tránh version động như latest hoặc range không kiểm soát.
- Quản lý plugin version tường minh.
- Dùng dependency lock hoặc dependency management phù hợp với build tool.
- Đặt encoding và locale nhất quán.
- Cấu hình archive timestamp/file order theo cơ chế reproducible của build tool.
- Không đưa thời gian build, hostname, secret hoặc dữ liệu môi trường ngẫu nhiên vào artifact nếu không cần.

Maven hỗ trợ thuộc tính project.build.outputTimestamp để chuẩn hóa timestamp archive:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Giá trị cần được cố định theo chính sách build của dự án; không thay bằng thời điểm chạy build. Với Gradle, kiểm tra cấu hình archive tasks và dependency locking của phiên bản Gradle đang dùng.

Reproducible build giúp xác minh artifact, so sánh kết quả giữa CI và máy developer, và giảm khác biệt không cần thiết giữa các lần phát hành.

## 11. Pipeline CI tham khảo

Một pipeline Java 21 có thể tổ chức thành các bước:

~~~text
Checkout source
      |
      v
Select JDK 21 + build wrapper
      |
      v
Print java/javac/build-tool versions
      |
      v
Resolve locked dependencies
      |
      v
Compile main + test sources (--release 21)
      |
      v
Run unit tests
      |
      v
Create package artifact
      |
      v
Start integration dependencies
      |
      v
Run integration tests on Java 21
      |
      v
Smoke test packaged artifact
      |
      v
Publish reports + artifact only if all checks pass
~~~

Với Maven, lệnh CI thông thường:

~~~bash
./mvnw --batch-mode --no-transfer-progress clean verify
~~~

Với Gradle:

~~~bash
./gradlew --no-daemon clean build
~~~

Các lệnh này chỉ đảm bảo integration test được chạy nếu lifecycle/plugin/task đã được cấu hình đúng. CI cần lưu test report và fail job khi compile, unit test, integration test hoặc package/smoke test thất bại.

### Chạy artifact một lần, promote cùng artifact

Sau khi pipeline tạo artifact đã kiểm thử, publish chính artifact đó vào kho lưu trữ và promote cùng digest qua staging/production. Không rebuild riêng ở từng môi trường, vì lần build mới có thể lấy dependency, timestamp, JDK hoặc cấu hình khác.

Nếu cấu hình runtime thay đổi theo môi trường, đưa cấu hình ra ngoài artifact và quản lý bằng deployment configuration/secret manager. Ghi checksum hoặc digest của artifact để truy vết chính xác binary đã được triển khai.

## 12. Preview features và Java 21

Không bật preview features chỉ để build một dự án Java 21 thông thường. Các feature đã final trong Java 21 dùng trực tiếp với --release 21, không cần --enable-preview.

Nếu dự án chủ động dùng preview feature của Java 21, phải bật preview khi compile và khi chạy trên đúng release tương ứng. Preview class file của một release không được xem là artifact tương thích để chạy trên các release khác. Điều này làm tăng độ phức tạp của CI và deployment; chỉ sử dụng khi có quyết định kỹ thuật rõ ràng và chấp nhận giới hạn vòng đời của preview API.

Đối với ứng dụng production cần khả năng nâng cấp ổn định, ưu tiên API đã final và không phụ thuộc preview.

## 13. Các lỗi cấu hình thường gặp

| Cấu hình hoặc thao tác | Vấn đề | Cách khắc phục |
|---|---|---|
| Chỉ đặt source=21 và target=21 | Có thể tham chiếu API mới hơn Java 21 nếu compiler chạy trên JDK mới | Dùng --release 21 |
| Chỉ dùng --release 21 | Không buộc JVM chạy test hoặc build tool là Java 21 | Cấu hình JDK/toolchain và kiểm tra runtime |
| CI dùng JDK mặc định của runner | Build thay đổi khi image runner cập nhật | Cài/chọn JDK 21 rõ ràng và log version |
| Chạy mvn test rồi publish artifact | Integration test trong Failsafe có thể chưa chạy | Dùng lifecycle mvn verify |
| Chạy mvn package và nghĩ đã verify | Lifecycle chưa chạy phase verify | Chạy mvn verify |
| Gradle có task integrationTest nhưng không gắn vào check | build có thể bỏ qua integration test | Gắn task vào check hoặc lifecycle CI |
| Compile trên Java 21 nhưng Docker base image cũ | Runtime không hiểu class file version 65 | Dùng runtime Java 21 trở lên và smoke test image |
| Test chỉ chạy trên JDK mới hơn | Có thể bỏ sót vấn đề runtime Java 21 | Chạy test chính trên Java 21 |
| Rebuild artifact khi deploy từng môi trường | Binary giữa staging và production không còn giống nhau | Promote cùng artifact/digest |
| Đưa secret vào resource hoặc manifest | Secret bị lưu trong artifact và có thể bị lộ | Inject secret lúc runtime từ secret manager |

## 14. Checklist trước khi merge pipeline Java 21

- [ ] JDK chạy build tool đã được xác định và log trong CI.
- [ ] Maven Wrapper/Gradle Wrapper được commit và pin phiên bản.
- [ ] Compiler dùng --release 21.
- [ ] Main source và test source đều compile thành công.
- [ ] Unit test chạy trên Java 21.
- [ ] Integration test được gắn vào lifecycle bắt buộc và chạy trên Java 21.
- [ ] Dependency ngoài được khởi tạo, readiness-check và teardown có kiểm soát.
- [ ] Plugin, annotation processor và dependency hỗ trợ JDK mục tiêu.
- [ ] Package chỉ được publish sau khi verify/check và smoke test thành công.
- [ ] Artifact có class file version phù hợp, không chứa secret hoặc file test.
- [ ] Runtime image/deployment dùng Java 21 trở lên và được kiểm thử.
- [ ] CI lưu test report, build log, checksum/digest và artifact.
- [ ] Staging/production promote cùng artifact đã kiểm thử.

## 15. Tổng kết

Để đồng bộ build và CI trên Java 21, hãy kiểm soát riêng JDK chạy build tool, compiler/toolchain và JVM chạy test/deployment. Dùng --release 21 để giới hạn API và bytecode, cấu hình toolchain cho compiler/test, tách unit test khỏi integration test và bảo đảm integration test nằm trong lifecycle CI bắt buộc.

Với Maven, dùng Surefire cho unit test, Failsafe cho integration test và chạy clean verify. Với Gradle, dùng Java toolchain, đặt options.release = 21, gắn integration test vào check và chạy clean build. Chỉ publish artifact sau khi kiểm tra thành công; smoke test file JAR hoặc image đã đóng gói và promote cùng artifact qua các môi trường.

## Tài liệu tham khảo

- [Java SE 21 — javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) — --release, source, target và compiler options.
- [Java SE 21 — java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html) — lựa chọn runtime và JVM options.
- [Maven Compiler Plugin — Setting the --release of the Java Compiler](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html) — cấu hình release trong Maven.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/) — chạy unit test trong Maven lifecycle.
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/) — chạy integration test và xác nhận kết quả ở verify phase.
- [Maven Toolchains Guide](https://maven.apache.org/guides/mini/guide-using-toolchains.html) — chọn JDK toolchain độc lập với JVM chạy Maven.
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html) — chọn JDK cho compile và test.
- [Gradle Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html) — source sets, test task, check và build lifecycle.
- [Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html) — cố định phiên bản Gradle được dùng trong CI.
