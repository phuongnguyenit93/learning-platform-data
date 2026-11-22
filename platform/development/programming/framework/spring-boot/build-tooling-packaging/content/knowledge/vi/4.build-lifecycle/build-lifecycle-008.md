# Xác định đầu vào, đầu ra và trạng thái thành công của từng giai đoạn build Spring Boot

## 1. Mục tiêu và phạm vi

Một lệnh như `mvn clean verify` hoặc `./gradlew clean build` thường chỉ cho thấy kết quả tổng thể `BUILD SUCCESS` hay `BUILD SUCCESSFUL`. Muốn kiểm soát chất lượng, cần biết **mỗi giai đoạn nhận gì, tạo gì và dựa vào bằng chứng nào để coi là thành công**.

Sau bài này, bạn có thể:

1. Vẽ đường đi của mã nguồn Spring Boot từ checkout, resolve dependency, biên dịch, kiểm thử, đóng gói đến phát hành.
2. Xác định **input**, **output**, **điều kiện PASS**, **dấu hiệu FAIL/SKIP** và **bằng chứng kiểm chứng** cho từng giai đoạn.
3. Ánh xạ cùng một hoạt động sang **Maven phase/plugin goal** và **Gradle task**, đồng thời phân biệt đúng Maven lifecycle với Gradle build lifecycle.
4. Thiết kế cổng chất lượng cho CI để tránh coi “build xanh” đồng nghĩa với “đã chạy đủ test”, “JAR chạy được” hoặc “dịch vụ đã sẵn sàng”.
5. Điều tra sự cố từ giai đoạn hỏng đầu tiên thay vì chỉ đọc dòng lỗi cuối cùng.

**Phạm vi chính:** ứng dụng Java/Spring Boot đóng gói executable JAR bằng Maven hoặc Gradle. Ví dụ dùng Java 17+ và Spring Boot 4.1.2. Với bản Spring Boot khác, cần tra yêu cầu Java, phiên bản build tool, starter, plugin và tên task tương ứng.

## 2. Khung tư duy: một giai đoạn có năm thuộc tính

Dùng biểu mẫu sau cho bất kỳ giai đoạn nào:

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| **Input** | Giai đoạn này cần những tệp, phiên bản công cụ, cấu hình, artifact, dịch vụ hoặc quyền nào? |
| **Xử lý** | Maven goal, Gradle task, compiler, test runner hay hệ thống ngoài thực hiện việc gì? |
| **Output** | Kết quả có thể kiểm tra là class, resource, test report, JAR, image, checksum, publication hay deployment record nào? |
| **PASS** | Điều kiện cụ thể để chuyển sang giai đoạn sau là gì? Có cần kiểm tra thêm ngoài exit code 0 không? |
| **FAIL / SKIP** | Điều gì khiến giai đoạn lỗi, bị bỏ qua hoặc không có công việc? Trạng thái đó được phép trong hoàn cảnh nào? |

Một giai đoạn có thể kết thúc **thành công hợp lệ nhưng không sinh tệp mới**; ví dụ Maven `validate` kiểm tra tính hợp lệ, Gradle task `processResources NO-SOURCE` khi project không có resource. Ngược lại, một giai đoạn có thể có sẵn tệp kết quả từ lần build trước nhưng **lần chạy hiện tại không thành công**. Vì vậy phải kết hợp log của lần chạy, điều kiện chạy task và hiện trạng output.

**Định nghĩa hoàn tất (Definition of Done) dùng trong bài:**

> Một giai đoạn PASS khi input thiết yếu hợp lệ, các bước bắt buộc đã thực hiện hoặc được phép tái sử dụng, kết quả đạt tiêu chí đã định và có bằng chứng để truy nguyên. Một giai đoạn bị skip chỉ được coi là PASS nếu chính sách dự án cho phép skip đó.

Đừng biến mọi dòng `SKIPPED` thành PASS; nếu chính sách yêu cầu unit test mà nó bị bỏ qua, cổng chất lượng phải báo **chưa đạt** dù build tool trả mã 0.

## 3. Bản đồ đường đi của một artifact

~~~text
Mã nguồn + pom.xml/build.gradle + wrapper + cấu hình + JDK
                           |
                           v
             [0] Checkout / khởi tạo build
                           |
                           v
             [1] Validate / cấu hình task
                           |
                           v
             [2] Resolve dependency + plugin
                           |
                           v
             [3] Generate sources + process resources
                           |
                           v
             [4] Compile mã sản phẩm
                           |
                           v
             [5] Compile tests -> chạy tests -> reports
                           |
                           v
             [6] Tạo JAR/WAR -> Spring Boot executable JAR
                           |
                           v
             [7] Verify / integration / smoke checks
                           |
                           v
             [8] Publish artifact / image (nếu yêu cầu)
                           |
                           v
             [9] Deploy -> xác nhận runtime readiness
~~~

Đây là **pipeline logic** để quan sát đầu vào/đầu ra; không phải danh sách phase chính thức giống nhau cho hai công cụ:

- **Maven** có các lifecycle `clean`, `default`, `site`. Lifecycle `default` chứa những **phase có thứ tự** như `validate`, `process-resources`, `compile`, `test`, `package`, `verify`, `install`, `deploy`. Goal của plugin được gắn vào phase. Gọi `mvn verify` sẽ chạy các phase cần thiết trước `verify`; `mvn clean verify` chạy thêm lifecycle `clean`.
- **Gradle** có ba **giai đoạn nội bộ**: initialization, configuration, execution. Trong execution, Gradle chạy **task graph** theo dependency và các task được yêu cầu, ví dụ `compileJava`, `test`, `bootJar`, `check`, `build`. Không có mặc định một dãy task “bắt buộc” luôn giống Maven phase.
- **Spring Boot plugin** bổ sung hoạt động đóng gói executable JAR, chạy ứng dụng và tạo container image; việc bật các hoạt động phát hành/kiểm thử bổ sung tùy vào cấu hình cụ thể.

## 4. Ma trận đầu vào, đầu ra và điều kiện PASS theo giai đoạn

| Giai đoạn logic | Input chính | Output kỳ vọng | Tiêu chí PASS có thể chứng minh | Maven / Gradle thường gặp |
| --- | --- | --- | --- | --- |
| **0. Checkout & environment** | Commit, source tree, wrapper, JDK, env, repository credentials khi cần | Workspace đúng commit; JDK/build tool khả dụng | Commit đúng, wrapper chạy, Java đáp ứng yêu cầu, không thiếu biến cần thiết | `./mvnw -version` / `./gradlew --version` và CI checkout |
| **1. Validate & configure** | POM hoặc settings/build scripts, profiles, plugin declarations | Effective model hoặc task graph được cấu hình | Cấu hình hợp lệ; plugin được nạp; không có lỗi parse/config | `validate` / initialization + configuration |
| **2. Dependency resolution** | Coordinates, BOM, repository, credentials, cache | Dependency graph và artifact đã phân giải | Mọi module/plugin cần thiết được resolve đúng phiên bản, không có conflict nghiêm trọng | Maven resolve / Gradle resolve khi task cần |
| **3. Generate & resources** | Generator inputs, `src/main/resources`, filtering values | Generated source, resources ở build output | Generator hoàn tất; resource cần thiết được copy/filter; không thiếu asset quan trọng | `generate-sources`, `process-resources` / generate task, `processResources` |
| **4. Compile production** | `src/main/java`, generated sources, compile classpath, JDK | `.class` + metadata compile | Không lỗi compile, release tương thích, class được tạo khi có source | `compile` / `compileJava` |
| **5. Compile & run tests** | Test sources, test classpath, runtime, fixtures | Test classes, JUnit XML, logs | Test bắt buộc được phát hiện và chạy; 0 failure/error theo policy | `test-compile`, `test` / `compileTestJava`, `test` |
| **6. Package** | Compiled classes, resources, runtime dependencies, manifest, Boot plugin | JAR/WAR và executable archive | Archive tạo mới/được tái sử dụng hợp lệ, mở được, cấu trúc Boot đúng và `java -jar` có khả năng khởi động | `package` + `repackage` / `bootJar` |
| **7. Verify** | Artifact đã package, kiểm tra tích hợp, quality rules | Report integration/verification, kết luận gate | Mọi kiểm tra **được cấu hình và bắt buộc** đều đạt; không skip trái policy | `verify` + plugin bound / `check` và task riêng |
| **8. Publish** | Artifact đã duyệt, version, credentials, repository/image registry | Maven coordinates/metadata hoặc image digest xuất hiện ở đích | Upload thành công, tọa độ/checksum/digest truy xuất được | `install`, `deploy` / `publishToMavenLocal`, `publish` |
| **9. Deploy & readiness** | Artifact/image được duyệt, cấu hình môi trường, secrets, hạ tầng | Release đang chạy, log và health status | Quy trình deploy hoàn tất, probe readiness/smoke thực tế đạt | CI/CD hoặc công cụ triển khai ngoài build tool |

**Quan trọng:** Không phải tất cả các giai đoạn này đều được kích hoạt trong một lệnh. Ví dụ `mvn clean package` dừng trước `verify`; `./gradlew bootJar` không tự có nghĩa đã chạy unit test; `./gradlew build` không mặc định publish; `java -jar` thành công lúc khởi động không tự chứng minh readiness trong production.

## 5. Giai đoạn 0 — xác định đầu vào của bản dựng

### Input

- Repository ở **một commit cụ thể**, cùng các submodule/file được tracking cần cho build.
- `pom.xml` hoặc `build.gradle`/`build.gradle.kts`, `settings.gradle`, `gradle.properties`; Maven/Gradle Wrapper nếu có.
- Java/JDK mà bản build tool và Spring Boot plugin hỗ trợ; toolchain JDK cho compile/test nếu khác.
- Cấu hình dependency repositories, proxy, private artifact credentials, env variables chỉ khi thực sự cần.
- Thông tin phiên bản, build profile, feature flags cho quá trình build, dữ liệu sinh code và file tài nguyên.

### Output và PASS

Đầu ra chưa phải là JAR mà là **workspace có thể tái dựng**: checkout đúng commit, wrapper có thể chạy, các điều kiện tiên quyết được xác định. Trong CI nên lưu commit SHA, Java runtime, phiên bản Maven/Gradle và danh sách profile/property build (không ghi secrets vào log).

~~~bash
# Chạy tại thư mục gốc dự án có wrapper tương ứng
git rev-parse HEAD
java -version
./mvnw -version
# hoặc
./gradlew --version
~~~

**PASS:** repository đúng bản cần build, wrapper khởi động được, Java và môi trường đáp ứng yêu cầu. **FAIL:** checkout sai commit, wrapper thiếu quyền chạy, Java quá cũ, registry riêng không khả dụng. **Lưu ý:** Java dùng để chạy Maven/Gradle và Java Toolchain dùng để biên dịch có thể khác nhau; đừng suy ra compiler từ một lệnh `java -version`.

## 6. Giai đoạn 1 — validate, initialize, configure

### Maven

`mvn validate` thực hiện các goal được bind tới phase `validate` và các phase trước đó của lifecycle phù hợp. Nó kiểm tra model và những gì plugin được bind quyết định kiểm tra. **Không được coi `validate` là kiểm định toàn diện về code, tests hoặc production readiness**.

Input là POM, parent, profiles, plugin settings; output là model/build configuration hợp lệ để tiến hành giai đoạn sau. Có thể xem effective POM:

~~~bash
mvn help:effective-pom
mvn validate
~~~

**PASS:** không có lỗi parsing POM, parent/module resolution, thiếu plugin bắt buộc hoặc rule validate đã cấu hình. Lưu ý một POM parse được không chứng minh source compile được.

### Gradle

Ba giai đoạn nội bộ của Gradle:

1. **Initialization:** xác định build, settings và các project.
2. **Configuration:** đánh giá build script, áp dụng plugin, đăng ký và cấu hình các task cần thiết (có thể lazy configuration và configuration cache).
3. **Execution:** xác định task graph cần chạy, resolve input cần thiết và chạy task theo dependency.

Đầu ra configuration là **mô hình build/task graph có thể thực thi**; không nhất thiết có JAR/class mới. Cách xem task:

~~~bash
./gradlew tasks
./gradlew help
./gradlew build --dry-run
~~~

`--dry-run` cho phép xem nhiệm vụ dự kiến mà **không thực thi các task thực**; vì vậy nó **không phải bằng chứng compile/test/package PASS**. Khi dùng configuration cache, Gradle có thể khôi phục cấu hình đã lưu thay vì cấu hình lại từ đầu; việc tái sử dụng hợp lệ không tương đương giai đoạn bị lỗi.

## 7. Giai đoạn 2 — phân giải dependency và plugin

**Input:** starter/dependency coordinates, Maven BOM hoặc Gradle platform, plugin versions, dependency constraints, repositories, scopes/configurations, credentials nếu cần. Build tool hình thành resolved dependency graph và tải những artifact chưa có trong cache.

- **Maven:** xem `mvn dependency:tree`; Maven dependencyManagement quyết định phiên bản mặc định cho dependency được quản lý.
- **Gradle:** xem `./gradlew dependencies --configuration runtimeClasspath` hoặc `./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath`.

~~~bash
mvn dependency:tree
# Hoặc trong dự án Gradle:
./gradlew dependencies --configuration runtimeClasspath
~~~

**Output:** bộ artifact/metadata được resolve hợp lệ trong cache/repository và dependency graph thực tế. **PASS:** tất cả dependency cần cho task đã được phân giải, không còn artifact missing, lỗi SSL/auth, hoặc xung đột dependency vượt ngưỡng được policy cho phép.

**Khác biệt cần nhớ:** dependency resolution có thể xảy ra tại thời điểm khác nhau tùy plugin/task và caching; đó không luôn là một “phase resolve” hiển thị độc lập. Một lệnh xem dependency graph chỉ chứng minh cấu hình tương ứng, không chứng minh mọi classpath của mọi task giống hệt nó.

**Ví dụ lỗi:** starter được khai báo đúng nhưng BOM/parent không quản lý version; private registry từ chối quyền; hai thư viện kéo các API không tương thích. Không sửa lỗi bằng cách kiểm tra lại JAR: nó hỏng **trước** khâu đóng gói.

## 8. Giai đoạn 3 — sinh mã nguồn và xử lý resources

### Input

- `src/main/resources/**`, cấu hình ứng dụng mẫu, schema/OpenAPI/protobuf, file generator, build properties dùng cho filtering.
- Codegen plugin/task nếu dự án có; không phải mọi Spring Boot project đều cần generate source.

### Maven và Gradle

| Việc | Maven | Gradle |
| --- | --- | --- |
| Sinh mã trước compile | Goal tự cấu hình tại `generate-sources`/phase thích hợp | Custom/plugin generate task có dependency với `compileJava` |
| Đưa resource vào output | `resources:resources` thường ở `process-resources` | `processResources` |
| Resources đã xử lý | Thường là `target/classes/...` | Thường là `build/resources/main/...` |
| Generated source | Đường dẫn do plugin cấu hình, ví dụ dưới `target/generated-sources` | Đường dẫn do task/plugin cấu hình, thường dưới `build/generated/...` |

**PASS:** các generator bắt buộc hoàn tất, output có nội dung theo schema/contract, resources cần thiết được copy/filter đúng. **FAIL:** schema sai, template thiếu, biến filtering không được cung cấp, resource bị thay sai môi trường.

Nếu project thực sự không có resources, Gradle có thể báo `processResources NO-SOURCE`. Đây có thể là trạng thái **bình thường**. Nhưng nếu cấu hình CI yêu cầu `application.yml` mà task đột nhiên `NO-SOURCE`, phải coi là **bằng chứng thiếu input**.

Không đặt bí mật production vào resources được đóng gói cùng JAR. Build artifact nên được cấu hình theo môi trường ở lúc triển khai nếu khả thi.

## 9. Giai đoạn 4 — biên dịch mã sản phẩm

**Input:** Java source, generated source, compile classpath, compiler JDK, Java release target và annotation processors. **Output:** class files, metadata do processor tạo và kết quả compile.

- Maven: thường ở `target/classes/` nhờ `maven-compiler-plugin` tại `compile`.
- Gradle: thường ở `build/classes/java/main/` qua `compileJava`. Resources có thể nằm ở `build/resources/main/`.
- Cấu hình tương thích Java: Maven `maven.compiler.release`; Gradle `options.release`/Java Toolchains.

**PASS:** compiler kết thúc không lỗi; tất cả lớp bắt buộc có mặt, đúng release/bytecode target, generated annotations/metadata không thiếu. Nếu task trả code 0 nhưng source cần thiết không được include do cấu hình sai, kiểm tra đầu ra và cấu trúc source set, không chỉ xem status.

~~~bash
mvn compile
# Hoặc:
./gradlew compileJava

# Sau khi có class thực tế, kiểm tra mức bytecode:
javap -verbose target/classes/dev/example/Hello.class
# Gradle tương ứng: build/classes/java/main/dev/example/Hello.class
~~~

`javap` hiển thị `major version` của class. Ví dụ Java 17 là major **61**, Java 21 là major **65**. Đừng lấy major version làm bằng chứng về bản JDK **chạy công cụ build**; nó chỉ biểu thị class-file target.

## 10. Giai đoạn 5 — biên dịch và chạy kiểm thử

### Input

Test source `src/test/java`, classpath cho test, dữ liệu fixture, môi trường test, mock/test services, JDK test. Output gồm compiled test classes và test reports.

| Kiểm thử | Maven | Gradle |
| --- | --- | --- |
| Biên dịch test | `test-compile`, thường `compiler:testCompile` | `compileTestJava` |
| Chạy unit tests | `test`, thường `surefire:test` | `test` |
| Unit test reports | `target/surefire-reports/` | `build/test-results/test/` và `build/reports/tests/test/` |
| Integration tests | Failsafe ở `integration-test` / `verify` **nếu được cấu hình** | Custom `integrationTest` hoặc task do plugin/build script định nghĩa |
| Gate chung | `mvn verify` chạy tới phase verify | `./gradlew check`/`build` chạy các task gắn vào graph |

**PASS tối thiểu:** test bắt buộc **được phát hiện**, thực thi theo policy, không có failure/error và test report có kết quả. Nếu yêu cầu integration test thì phải có task/goal, môi trường và báo cáo tương ứng.

Lỗi suy luận thường gặp:

- `BUILD SUCCESS` khi dự án **không có test** hoặc test bị skip **không** chứng minh “mọi test pass”.
- Maven `-DskipTests` thường bỏ chạy unit tests của Surefire nhưng vẫn compile test; `-Dmaven.test.skip=true` bỏ cả compile test. Với Failsafe đời mới, thuộc tính skip unit/integration có khác biệt: kiểm tra đúng phiên bản plugin và lựa chọn `-DskipITs` khi cần.
- `./gradlew build -x test` có thể xanh vì task test bị loại khỏi graph; nếu test bắt buộc, CI phải **cấm** lựa chọn đó.
- Gradle `NO-SOURCE` cho test compile/test có thể chấp nhận trong module không có test, nhưng module bắt buộc test thì phải đánh dấu **policy fail**.
- Integration test không tự tồn tại chỉ vì lệnh mang tên `verify` (Maven) hoặc `check` (Gradle). Phải kết nối plugin/task vào lifecycle.

Vì vậy điều kiện PASS của test gồm **count**, **fail/error/skipped**, **đúng suite**, **đúng môi trường** và **đã thực sự chạy hoặc tái sử dụng kết quả hợp lệ** theo policy.

## 11. Giai đoạn 6 — package thành executable Spring Boot JAR

### Input

Class files đã compile, processed resources, runtime dependencies, main application class và cấu hình Boot packaging plugin.

**Maven:** `jar:jar` tạo JAR gốc theo lifecycle `package`; `spring-boot:repackage` biến JAR/WAR hiện có thành executable archive nếu execution đã được cấu hình. Với `spring-boot-starter-parent` và plugin Spring Boot đã khai báo, goal repackage thường được bind sẵn. Nếu chỉ import BOM mà không dùng parent Boot, cần tự cấu hình plugin/execution.

**Gradle:** task `bootJar` tạo executable archive khi áp dụng Spring Boot Gradle plugin cùng Java plugin. `jar` thuần và `bootJar` có vai trò khác nhau. Task `build`/`assemble` được plugin wiring thích hợp để tạo artifact; vẫn nên kiểm tra chính xác task graph của project.

| Loại output | Maven (thông thường) | Gradle (thông thường) |
| --- | --- | --- |
| Class biên dịch | `target/classes/` | `build/classes/java/main/` |
| Archive executable | `target/<artifactId>-<version>.jar` | `build/libs/<project>-<version>.jar` |
| Nested runtime dependencies | `BOOT-INF/lib/` | `BOOT-INF/lib/` |
| Application classes | `BOOT-INF/classes/` | `BOOT-INF/classes/` |
| Launch manifest | `META-INF/MANIFEST.MF` | `META-INF/MANIFEST.MF` |

**PASS giai đoạn đóng gói:** file JAR tồn tại trong đúng vị trí cho build hiện tại, có dung lượng hợp lý, `jar tf` đọc được, chứa Boot loader/class/runtime dependency phù hợp, manifest xác định entry point, và có thể chạy bằng Java runtime đáp ứng yêu cầu.

~~~bash
# Maven
mvn clean package
jar tf target/demo-0.0.1-SNAPSHOT.jar

# Gradle
./gradlew clean bootJar
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
~~~

**Không nhầm:** một lệnh `mvn package` exit 0 có thể chỉ tạo JAR thường nếu Spring Boot Maven Plugin không được bind. Một file JAR có tên đúng vẫn có thể thiếu dependency hoặc sai main class. Bằng chứng tốt hơn là kiểm tra archive **và** thử `java -jar`/smoke test.

## 12. Giai đoạn 7 — xác minh artifact, integration test và cổng chất lượng

Giai đoạn này trả lời “artifact **đạt tiêu chí để phát hành** hay chưa?” Input là artifact đã package, quality rules, báo cáo unit test, integration test và môi trường kiểm chứng.

**Maven:** `mvn verify` đi qua các phase trước đến `verify`; nếu cấu hình Maven Failsafe hoặc một plugin chất lượng tại các phase thích hợp, các kiểm tra đó mới thực thi. Nếu không bind integration test, `verify` không tự tạo và chạy integration suite.

**Gradle:** `check` là lifecycle task thường kết nối verification task; `build` thường phụ thuộc `assemble` và `check` trong Java plugin. Quality plugins (Checkstyle, SpotBugs, JaCoCo, integration test source set riêng...) phải được cấu hình và nối vào graph. Chỉ vì tên task `check` tồn tại không có nghĩa tất cả loại kiểm tra đã được thiết lập.

**Tiêu chí PASS mẫu cho service Spring Boot:**

1. Tests bắt buộc được chạy và report xác nhận không lỗi.
2. Static analysis hoặc code coverage đạt ngưỡng **nếu chính sách quy định**.
3. Executable archive đúng tên/version, không thiếu runtime dependency.
4. Smoke test ứng dụng chạy thử với profile/test environment, endpoint cần thiết trả giá trị mong đợi.
5. Nếu có integration suite, báo cáo và môi trường cần thiết hợp lệ.

Ngưỡng coverage, policy bảo mật và yêu cầu license **phải do dự án đặt**, không phải hành vi mặc định của Maven/Gradle/Spring Boot.

**PASS của `verify` hoặc `check` chỉ có ý nghĩa theo các goal/task đang được bind**, do đó cần audit cấu hình và log để biết chính xác tiêu chí nào đã được áp dụng.

## 13. Giai đoạn 8 — install, publish, release, image

Đây là bước **tùy chọn và có tác động bên ngoài**; chạy nó khi pipeline thực sự cần phát hành.

### Maven

- `mvn install`: sau các phase trước, cài artifact vào **local Maven repository** (`~/.m2/repository` mặc định). Đây là output cục bộ, **không** chứng minh artifact đã được publish ra server công ty.
- `mvn deploy`: chạy các phase trước và upload vào **remote repository** theo cấu hình `distributionManagement`/repository và credentials thích hợp. Output là artifact/metadata ở remote repository.
- Nếu muốn cổng quality trước phát hành, chạy `verify` với kiểm tra bắt buộc trước, và chỉ cho phép `deploy` khi đạt.

### Gradle

- `publishToMavenLocal`/`publish` là các task của `maven-publish` khi áp dụng plugin và cấu hình publication/repository.
- `build` không đồng nghĩa `publish`. Task publish cần quyền và version/repository đúng; việc chạy thành công nên kiểm chứng artifact/metadata ở đích.

### Container image Spring Boot

- Maven Spring Boot plugin có goal `build-image`; Gradle Spring Boot plugin có task `bootBuildImage`. Chúng tạo OCI image bằng cơ chế buildpacks trong cấu hình được hỗ trợ; thường cần container runtime/daemon hoặc dịch vụ builder phù hợp.
- **Output là image có tag/digest**, chưa chắc đã được push vào registry. Cần phân biệt **build image**, **push image** và **deploy image**.

**PASS cho phát hành:** artifact hoặc image đã xuất hiện ở hệ thống đích, tọa độ version/tag/digest đúng, có quyền truy xuất, checksum hoặc digest nhất quán; chính sách ký, scan, provenance được đáp ứng nếu yêu cầu. Chỉ thấy dòng “publish task completed” mà remote registry không truy xuất được là bằng chứng chưa đủ cho việc phân phối.

Đừng tự đưa secrets/cấu hình môi trường production vào artifact log hoặc commit; cung cấp credentials bằng cơ chế bảo mật của CI/CD.

## 14. Giai đoạn 9 — chạy và xác minh dịch vụ

Packaging tạo file chạy được, nhưng **build success không phải production success**. Giai đoạn deploy nhận artifact/image đã duyệt, cấu hình profile, kết nối database và các dịch vụ ngoài, hạ tầng/secret. Output là **instance đang chạy** và dữ liệu quan sát được.

Các mức kiểm chứng khác nhau:

- **Artifact-level:** `jar tf` mở được, manifest và thư viện đúng.
- **Process-level:** `java -jar` chạy lên, tiến trình tồn tại, không thoát vì cấu hình sai.
- **Application-level:** endpoint khởi động, route trả đúng kết quả, profile và config cần thiết hợp lệ.
- **Readiness-level:** health/readiness probe mà hệ thống triển khai kiểm tra đạt; database, message broker hoặc dependency quan trọng có trạng thái phù hợp với policy.
- **Release-level:** rollout và smoke/regression checks ở môi trường thật đạt; theo dõi logs/metrics/alerts sau deploy.

Spring Boot Actuator có thể cung cấp endpoint health/readiness khi được thêm dependency và cấu hình phù hợp. **Không được giả định endpoint `/actuator/health` tự có** trong mọi dự án. Ngay cả HTTP 200 ở một route cũng không tự chứng minh mọi dependency production đang lành mạnh.

## 15. Ví dụ xuyên suốt: một ứng dụng Spring Boot dùng cả Maven và Gradle

Ví dụ dưới đây có **một controller và một unit test**. Ta dùng cùng mã Java cho hai lựa chọn build khác nhau; trong một dự án thực tế nên dùng **một hệ thống build chủ đạo** hoặc xác định rõ quy trình nếu duy trì cả hai.

### 15.1. Các tệp Java

Cấu trúc:

~~~text
demo/
├── src/main/java/dev/example/DemoApplication.java
├── src/main/java/dev/example/Greeting.java
└── src/test/java/dev/example/GreetingTest.java
~~~

**`src/main/java/dev/example/DemoApplication.java`**

~~~java
package dev.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return Greeting.message();
    }
}
~~~

**`src/main/java/dev/example/Greeting.java`**

~~~java
package dev.example;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello pipeline";
    }
}
~~~

**`src/test/java/dev/example/GreetingTest.java`**

~~~java
package dev.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("Hello pipeline", Greeting.message());
    }
}
~~~

Test là unit test cho `Greeting.message()`, **chưa** phải HTTP integration test. Muốn khẳng định route `/hello` thực sự phục vụ HTTP phải chạy app và gửi request, hoặc viết thêm integration test phù hợp.

### 15.2. Cách A: Maven với Spring Boot parent

**`pom.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Cần cài Maven và JDK thỏa yêu cầu; Spring Boot parent quản lý dependency và cấu hình các plugin liên quan. Ví dụ không sử dụng wrapper vì ta chưa tạo file wrapper; trong dự án có wrapper có thể thay `mvn` bằng `./mvnw`.

**Chạy theo từng cổng:**

~~~bash
mvn validate
mvn dependency:tree
mvn compile
mvn test
mvn clean verify

# Kiểm tra executable artifact do Spring Boot plugin tạo
jar tf target/demo-0.0.1-SNAPSHOT.jar
java -jar target/demo-0.0.1-SNAPSHOT.jar
~~~

Trong terminal khác:

~~~bash
curl -s http://localhost:8080/hello
~~~

**HTTP response body chính xác:**

~~~text
Hello pipeline
~~~

Chuỗi response không chứa ký tự newline; công cụ terminal có thể thêm lời nhắc hoặc hiệu ứng hiển thị khác. Output nguyên lệnh Maven phụ thuộc bản plugin, cache và môi trường nên **không thể coi một transcript log cố định là stdout bắt buộc**.

**Quan sát input/output:**

1. `validate`: POM hợp lệ; chưa đòi hỏi file class.
2. `compile`: tạo class ở `target/classes/dev/example/`.
3. `test`: biên dịch/running unit test, báo cáo ở `target/surefire-reports/`; kiểm tra test count và failures.
4. `package` xảy ra trên đường đi tới `verify`: Boot plugin tạo `target/demo-0.0.1-SNAPSHOT.jar` với `BOOT-INF/classes` và `BOOT-INF/lib`.
5. `verify`: những goal verification **đã cấu hình** phải thành công; ví dụ này chưa cấu hình integration test độc lập.
6. `java -jar` + `curl`: smoke test xác nhận runtime và endpoint thực sự hoạt động ở profile/port đang chạy.

### 15.3. Cách B: Gradle Groovy DSL

Giữ ba file Java, bỏ `pom.xml` khi dùng riêng Gradle. Tạo thêm:

**`settings.gradle`**

~~~groovy
rootProject.name = 'demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Yêu cầu Gradle phiên bản được Spring Boot 4.1.2 hỗ trợ, JDK 17 có thể được toolchain tìm thấy và runtime chạy Gradle tương thích. Nếu project đã có wrapper:

~~~bash
./gradlew tasks
./gradlew dependencies --configuration runtimeClasspath
./gradlew compileJava
./gradlew test
./gradlew clean build

jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar
~~~

Trong terminal khác:

~~~bash
curl -s http://localhost:8080/hello
~~~

Response body dự kiến cũng chính xác `Hello pipeline`. Trên Windows dùng `gradlew.bat`. Với Gradle, task `build` tổng hợp các task assemble/verification khi project được cấu hình như ví dụ; quan sát task graph thực tế trong log để biết chính xác `bootJar`, `test` được gọi.

## 16. Cách biến ma trận thành kiểm chứng tự động trên CI

Chính sách tối thiểu cho một project Spring Boot có unit test bắt buộc:

~~~text
GATE A — Build inputs
    Đúng commit, wrapper, JDK, khóa repo được cấu hình hợp lệ
    -> FAIL nếu thiếu bất kỳ điều kiện bắt buộc

GATE B — Resolve + compile
    Dependency graph được resolve, compile thành công, class đúng release
    -> FAIL nếu thiếu class cần thiết hoặc compiler lỗi

GATE C — Unit tests
    Bắt buộc test task chạy; số test > 0; số failed = 0
    -> FAIL khi test bị skip trái policy, hoặc test runner không phát hiện test

GATE D — Artifact
    executable JAR tồn tại, mở được, có main class/runtime libs
    -> FAIL nếu chỉ có plain JAR hoặc JAR sai version

GATE E — Smoke / integration
    start app ở môi trường kiểm thử và gọi endpoint bắt buộc
    -> FAIL nếu process exit, timeout, HTTP body/status khác contract

GATE F — Publication / deployment (nếu có)
    chỉ chạy khi Gate A..E đạt và có approval/credential phù hợp
    -> FAIL nếu registry/deploy health không xác nhận được output
~~~

Trong CI nên lưu các **bằng chứng**: SHA/commit, phiên bản JDK/build tool, resolved dependency report khi cần, JUnit XML, file artifact, checksum SHA-256, image digest nếu có, smoke-test status, link build và deployed environment. Tránh ghi password/token; không cần log mọi biến môi trường.

### Pipeline shell minh họa (không thay thế cấu hình CI hoàn chỉnh)

~~~bash
# Maven
mvn clean verify

# Chỉ khi lệnh trên thành công, kiểm tra artifact:
jar tf target/demo-0.0.1-SNAPSHOT.jar
# Sau đó chạy một smoke-test có timeout và cleanup process rõ ràng trong CI.
~~~

~~~bash
# Gradle
./gradlew clean build

# Chỉ khi lệnh trên thành công, kiểm tra artifact:
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
# Sau đó chạy một smoke-test có timeout và cleanup process rõ ràng trong CI.
~~~

Hai script trên chỉ minh họa **thứ tự build → kiểm tra archive**, **chưa hoàn chỉnh** vì thiếu assertion nội dung JAR, launch app, kiểm tra HTTP, môi trường CI, credentials và cleanup. Để làm gate thật, script/CI phải dừng khi command exit khác 0, kiểm tra nội dung kết quả, chạy smoke test với timeout và hủy tiến trình sau kiểm thử. Nếu cần publish, thêm bước publish riêng sau khi mọi gate bắt buộc đạt.

## 17. Đọc trạng thái Maven và Gradle cho chính xác

### 17.1. Maven

- `[INFO] BUILD SUCCESS`: các goal được Maven thực thi trong lần gọi đã kết thúc thành công theo logic của chúng.
- `[ERROR] BUILD FAILURE`: ít nhất một goal/lỗi setup làm build dừng; tìm **goal và phase lỗi đầu tiên**.
- `No tests to run` hoặc thông báo skip của Surefire: **không chứng minh test PASS**; kiểm tra test count, policy và runner.
- `Nothing to compile`: hợp lệ nếu không đổi source và output còn nhất quán, hoặc module không có source; đáng nghi nếu dự án bắt buộc có class mà đường dẫn source bị sai.
- `mvn package`: không chạy các phase sau `package` như `verify` và `deploy`. `mvn verify` cũng không tự upload remote artifact.

### 17.2. Gradle

| Nhãn task | Ý nghĩa | Đánh giá khi task bắt buộc |
| --- | --- | --- |
| Không nhãn / `EXECUTED` | Actions được chạy | PASS khi action và assertion đạt |
| `UP-TO-DATE` | Gradle xác định inputs/outputs không cần chạy lại | Có thể PASS khi output hợp lệ và chính sách cho phép incremental |
| `FROM-CACHE` | Outputs được khôi phục từ build cache | Có thể PASS khi cache tin cậy, output/metadata phù hợp |
| `NO-SOURCE` | Task không có source để xử lý | PASS khi không cần source; FAIL nếu nguồn bắt buộc |
| `SKIPPED` | Task không chạy do điều kiện/exclusion | Xem policy; không tự gán PASS |
| `FAILED` | Task thất bại | FAIL; điều tra lỗi và task phụ thuộc |

Một task Gradle có thể bị skip do cache nhưng **toàn bộ build vẫn xanh một cách hợp lệ**. Tuy nhiên với các bước nhạy cảm như kiểm thử an ninh, policy có thể yêu cầu chạy mới, cấm `-x test`, hoặc tắt một số cache trong CI release.

`./gradlew --dry-run build` chỉ hiển thị tác vụ dự định chạy, **không** tạo file output thực sự và không chứng minh PASS.

### 17.3. Phân biệt “trạng thái kỹ thuật” và “trạng thái chất lượng”

~~~text
Task status: SKIPPED
  |
  +--> Skip hợp lệ vì module không có test? --> Policy PASS có điều kiện
  |
  +--> Test là bắt buộc nhưng bị -x test? --> Policy FAIL

Task status: UP-TO-DATE
  |
  +--> Inputs không đổi, artifact đúng? --> Policy PASS
  |
  +--> CI cần chạy scanner mới? --> Không đủ bằng chứng; buộc chạy

Tool status: BUILD SUCCESS
  |
  +--> JAR có thật, executable, test pass? --> Đạt build gate
  |
  +--> Thiếu test hoặc artifact sai? --> Build gate riêng phải FAIL
~~~

**Tóm lại:** mã trả về 0 là dữ liệu kỹ thuật; “đạt chuẩn release” là kết luận từ những tiêu chí kiểm chứng mà đội dự án định nghĩa.

## 18. Xử lý sự cố theo giai đoạn hỏng đầu tiên

| Triệu chứng | Giai đoạn ưu tiên kiểm tra | Bằng chứng / hướng giải quyết |
| --- | --- | --- |
| POM invalid hoặc Gradle không configure được | 1 | Syntax POM/build script, plugin loader, JDK chạy build |
| `Could not resolve dependency` / `Artifact not found` | 2 | Repository URL, BOM, versions, credentials, network |
| Generated class/resource không tìm thấy | 3 | Codegen task/goal có chạy trước compile không, source-set configuration |
| `cannot find symbol` / `invalid target release` | 4 | Compiler classpath, source/import, JDK Toolchain, release |
| `Tests run: 0` dù bắt buộc có test | 5 | Test runner, patterns, JUnit engine, skip flags, test discovery |
| Test report có failure/error | 5 | Assertion, fixture, DB/test isolation; ưu tiên failure gốc |
| `no main manifest attribute` hoặc không chạy `java -jar` | 6 | Thiếu Boot repackage/bootJar, sai JAR hoặc manifest |
| `verify` xanh nhưng không có integration-test report | 7 | Chưa bind Failsafe hoặc chưa nối integration task vào `check` |
| `401 Unauthorized` lúc publish | 8 | Credentials, server repository, permission, profile/secret |
| Container image build xanh nhưng chưa có trên registry | 8 | Chưa push image; phân biệt local image với remote image |
| HTTP endpoint lỗi sau deploy dù build xanh | 9 | Runtime config, Java, dependency service, readiness/smoke |

**Chiến lược điều tra:** ghi nhận giai đoạn đầu tiên không đạt, kiểm tra input của giai đoạn đó, đối chiếu output thực tế, sửa một nguyên nhân có thể kiểm chứng, chạy lại đúng gate và những giai đoạn phụ thuộc. Không cần xóa toàn bộ cache mỗi lần; chỉ xóa khi có bằng chứng cache/đầu ra bị lỗi hoặc muốn kiểm tra khả năng tái dựng sạch.

## 19. Multi-module: PASS phải xét theo module và artifact đích

Trong monorepo/multi-module, các module có vai trò khác nhau:

- `common` hoặc `domain` là library: PASS package có thể là JAR **thường**, không cần Boot loader hoặc `java -jar`.
- `service` có `main`: cần executable Spring Boot archive và smoke test.
- `integration-tests` có thể chỉ chạy suite; `NO-SOURCE` ở `compileJava` không tự là lỗi nếu mục đích module là test artifact khác.

**Maven reactor:** một lệnh ở root có thể chạy nhiều module; xem module nào FAIL/SKIPPED trong reactor summary. **Gradle multi-project:** task có path, ví dụ `:service:bootJar` hoặc `:common:jar`; log BUILD SUCCESSFUL ở root phải được kiểm tra với những task được yêu cầu.

Bản phát hành cần ghi **artifact đích cụ thể** (group/artifact/version hoặc path/digest), không kết luận từ việc “toàn repository build xanh” mà bỏ qua module dịch vụ cần deploy.

## 20. Bài tập tự kiểm tra

1. **Chạy `mvn package` và nhận `BUILD SUCCESS`. Có chắc giai đoạn `verify` và integration tests đã chạy chưa?** Không. `package` dừng trước `verify`; integration tests chỉ chạy nếu có plugin/goal được cấu hình.
2. **`./gradlew bootJar` xanh. Có chắc `test` đã chạy không?** Không. `bootJar` tạo archive và các task phụ thuộc của nó; test chỉ chạy nếu graph có `test`.
3. **`processResources NO-SOURCE` là FAIL?** Không tự động. Nếu không có resource cần xử lý thì bình thường; nếu project bắt buộc resource thì policy phải FAIL.
4. **`UP-TO-DATE` có phải task vừa thực thi actions không?** Không; Gradle đã xác định output/input không cần làm lại.
5. **Tại sao unit test `GreetingTest` pass chưa chứng minh endpoint `/hello` pass?** Vì test gọi method trực tiếp, chưa khởi chạy server hay gửi HTTP request.
6. **`java -jar` chạy được chứng minh readiness production không?** Không; còn config, dịch vụ ngoài, health/readiness probes và rollout.
7. **Maven `install` và `deploy` khác nhau thế nào?** Install đưa artifact vào local repository; deploy publish tới remote repository.
8. **Có hai JAR `demo-...-plain.jar` và `demo-....jar`. Nên kiểm tra file nào để chạy Spring Boot?** Kiểm tra executable archive do `bootJar` tạo, xác nhận layout và chạy `java -jar`.
9. **Build report `Tests run: 0` và exit code 0. Gate test bắt buộc nên làm gì?** Đánh FAIL, điều tra test discovery/configuration.
10. **Build đã upload image tag `latest`. Làm sao chứng minh deploy đúng image?** Ghi và so khớp digest/immutable tag với release record, kiểm tra registry và runtime deployment.

## 21. Checklist áp dụng ngay vào dự án

- [ ] Xác định commit, wrapper, JVM chạy build và compiler/toolchain.
- [ ] Tài liệu hóa input và output quan trọng của từng phase/task.
- [ ] Phân biệt phase Maven, task Gradle và ba giai đoạn nội bộ Gradle.
- [ ] Kiểm tra dependency graph đã resolve và phiên bản được chọn.
- [ ] Đảm bảo generated sources/resources nằm trong nguồn compile/package.
- [ ] Kiểm tra output class và Java release target.
- [ ] Có test report và test count phù hợp; không bỏ qua test bắt buộc.
- [ ] Phân biệt plain JAR và Spring Boot executable JAR; kiểm tra Boot layout.
- [ ] Dùng artifact smoke test để kiểm chứng process và HTTP contract.
- [ ] Có quality gate tường minh cho integration, static analysis, coverage nếu cần.
- [ ] Chỉ publish/deploy sau khi artifact và các gate bắt buộc PASS.
- [ ] Ghi version/digest/checksum, lưu reports và link build để truy nguyên.
- [ ] Dùng tiêu chí FAIL/SKIP/UP-TO-DATE/FROM-CACHE đúng theo policy.

**Điểm cốt lõi:** đối với mỗi giai đoạn, hãy luôn nối **Input → xử lý → Output → Bằng chứng PASS/FAIL**. Maven/Gradle cho biết điều gì đã chạy theo cấu hình, còn tiêu chí release của dự án xác định **đủ điều kiện để đi tiếp** hay chưa.

## 22. Tài liệu chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Surefire Plugin — Running Tests and Reports](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Maven Surefire Plugin — Skipping Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html)
- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html)
- [Gradle — Understanding Tasks and Task Outcomes](https://docs.gradle.org/current/userguide/more_about_tasks.html)
- [Gradle — Incremental Builds and Build Cache](https://docs.gradle.org/current/userguide/gradle_optimizations.html)
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
- [Spring Boot Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
- [Spring Boot — Build Systems and Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
