# Đánh giá tính tương đương khi chuyển đổi công cụ build

Chuyển một dự án Java từ Gradle sang Maven, Ant hoặc Bazel không chỉ là đổi cú pháp khai báo dependency và task. Hai công cụ có thể tạo ra cùng một file JAR trong trường hợp đơn giản nhưng vẫn khác nhau về dependency resolution, thứ tự thực thi, cách xử lý annotation processor, test discovery, resource filtering, publication metadata, cache và mức độ cô lập. Những khác biệt này có thể làm artifact chạy khác, pipeline bỏ sót kiểm tra hoặc việc phát hành không còn tương đương với trước.

**Tính tương đương khi chuyển đổi công cụ build** là mức độ mà công cụ mới giữ được các hành vi và cam kết quan trọng của build cũ trong những điều kiện đầu vào đã xác định. Việc đánh giá cần dựa trên đầu ra, dependency graph, hành vi task, test, publication và quy trình vận hành, không chỉ dựa trên việc build mới kết thúc thành công.

Bài học này trình bày cách xác định hợp đồng build, so sánh các công cụ, nhận diện những khác biệt dễ bị bỏ sót và tổ chức migration có thể kiểm chứng.

## 1. “Tương đương” cần được định nghĩa trước

Không có một định nghĩa duy nhất về build tương đương. Mức cần giữ phụ thuộc mục tiêu của dự án.

Ví dụ, một thư viện Java có thể yêu cầu:

- Source code biên dịch với cùng Java language level và API target.
- Cùng public API và binary compatibility.
- Dependency runtime và dependency được công bố cho consumer không đổi ngoài các thay đổi đã duyệt.
- Test được phát hiện và thực thi với cùng phạm vi.
- JAR có cùng class, resource, manifest và service descriptors.
- Publication có cùng Maven coordinates, variants/metadata và checksums.
- CI vẫn kiểm tra format, static analysis, tests, signing và release gates.
- Build có thể tái lập từ source revision và toolchain đã pin.

Một ứng dụng nội bộ có thể không cần giữ publication metadata cho consumer bên ngoài, nhưng vẫn cần giữ cách đóng gói, runtime classpath, integration tests, container image và deployment behavior.

Vì vậy, trước khi chuyển đổi, hãy ghi rõ điều gì phải giống nhau và điều gì được phép thay đổi.

### Các mức tương đương

| Mức | Điều cần giữ | Ví dụ xác nhận |
|---|---|---|
| Source compatibility | Source cũ tiếp tục biên dịch | Compile cùng source và Java target |
| Binary compatibility | Bytecode/ABI tương thích với consumer hiện tại | So sánh public API, chạy consumer compatibility tests |
| Runtime compatibility | Ứng dụng chạy với dependency và resources phù hợp | Kiểm tra runtime classpath, smoke/integration tests |
| Artifact equivalence | Gói tạo ra chứa đúng nội dung và metadata cần thiết | So sánh entry, manifest, service files, archive |
| Dependency equivalence | Các dependency được resolve và công bố đúng ý định | So sánh graph, scopes/configurations, metadata |
| Workflow equivalence | Các bước build, test, verify, package, publish được thực hiện đúng | So sánh pipeline và release gates |
| Operational equivalence | Cache, incremental build, local/CI behavior và reproducibility đáp ứng mục tiêu | Build sạch, build tăng dần, offline và CI runs |

Không phải dự án nào cũng cần byte-for-byte identical archive. Nếu công cụ mới tạo timestamp hoặc metadata archive khác nhưng nội dung chạy và contract phát hành vẫn đúng, có thể chấp nhận khác biệt đó. Điều quan trọng là phân loại rõ khác biệt nào vô hại, khác biệt nào phá contract.

## 2. Bắt đầu từ hợp đồng build hiện tại

Trước khi chọn công cụ mới, hãy kiểm kê build cũ. Build script là một phần của hợp đồng kỹ thuật: nó mô tả cách source trở thành artifact và những kiểm tra cần hoàn tất trước khi phát hành.

Một bản kiểm kê nên ghi:

1. Các module/project và quan hệ phụ thuộc giữa chúng.
2. Source sets, source roots và resource directories.
3. Java version, compiler options và toolchain.
4. Dependency trực tiếp, dependency bắc cầu, repository và version policy.
5. Annotation processors, code generators và generated sources.
6. Compile, test, integration test, static analysis và verification tasks.
7. Resource filtering, file copying, packaging và archive customization.
8. JAR/WAR/distribution/container outputs.
9. Publication coordinates, metadata, signing và repository destinations.
10. CI workflows, environment variables, credentials và release conditions.
11. Build cache, incremental behavior, offline requirements và reproducibility.
12. Các task custom, script shell và công cụ ngoài.

Không chỉ đọc build file chính. Gradle có thể chứa convention plugins, build logic trong buildSrc hoặc included builds; Maven có thể dùng parent POM, profiles và plugin executions; Ant có thể import build file khác và gọi script bên ngoài; Bazel có thể dùng macros, rules và toolchains từ module/repository khác.

### Xác định điểm bắt đầu và điểm kết thúc

Hãy ghi rõ invocation chuẩn của build cũ:

~~~bash
./gradlew clean build
~~~

Nhưng cũng cần ghi các invocation thường dùng trong phát triển và phát hành:

~~~bash
./gradlew :app:compileJava
./gradlew test
./gradlew check
./gradlew assemble
./gradlew publish
~~~

Các lệnh trên chỉ minh họa một dự án Gradle. Dự án thực tế có thể có task riêng. Cần xác định ai gọi task nào, trong tình huống nào và output nào được tiêu thụ ở bước sau.

## 3. Xây dựng ma trận hành vi trước khi so sánh cú pháp

Một ma trận hành vi giúp phát hiện phần chưa được chuyển đổi.

| Hành vi build | Công cụ cũ | Công cụ mới | Cách xác minh |
|---|---|---|---|
| Compile main source | Task/configuration hiện tại | Plugin/goal/rule tương ứng | So sánh compiler, source roots và class output |
| Process resources | Filtering/copy rules | Resource processing mới | So sánh nội dung resource đã xử lý |
| Compile test source | Test compile configuration | Test compiler setup | So sánh test class output và test dependencies |
| Run unit tests | Test task/provider | Test goal/rule | So sánh test discovery, filters và reports |
| Annotation processing | Processor path và options | Processor configuration tương ứng | So sánh generated source và compiler diagnostics |
| Package JAR | Archive task | Package goal/rule | So sánh archive entries, manifest và service files |
| Dependency resolution | Configuration/variant rules | Scope/profile/dependency management | So sánh resolved coordinates và transitive graph |
| Publish | Publication component/metadata | Deploy/publish plugin hoặc rule | Kiểm tra POM, metadata, signatures và coordinates |
| Static analysis | Verification tasks | Plugin goals/rules | Xác nhận cùng rule set và source coverage |
| Release | CI task graph | CI stages mới | So sánh approval, signing và artifact promotion |

Điền ma trận bằng hành vi thực tế. Nếu một hàng chưa có mapping, đó là một gap cần giải quyết hoặc một thay đổi cần được phê duyệt.

### Không dùng tên task làm bằng chứng tương đương

Task Gradle tên test và Maven goal test đều có thể chạy unit tests, nhưng test provider, discovery engine, include/exclude filters, fork settings, system properties và report behavior có thể khác.

Tương tự, Gradle task jar và Maven goal package đều có thể tạo JAR nhưng manifest, archive timestamp, resource filtering, generated sources và plugin executions có thể khác.

Tên gần giống chỉ là gợi ý để điều tra, không chứng minh hai bước có cùng semantics.

## 4. Hiểu mô hình thực thi của từng công cụ

Các build tools có mô hình khác nhau. Cần hiểu mô hình trước khi chuyển đổi.

| Công cụ | Mô hình chính | Điểm cần đánh giá |
|---|---|---|
| Gradle | Task graph, configurations, providers, plugins, incremental inputs/outputs | Task dependencies, variants, lazy configuration, cacheability |
| Maven | Lifecycle phases, goals, plugin executions, dependency scopes | Phase binding, effective POM, plugin versions, profiles |
| Ant | Targets, tasks, properties, explicit dependencies | Target graph, mutable properties, file operations, custom scripts |
| Bazel | Targets, declared inputs/outputs, rules, toolchains, action graph | Hermeticity, sandboxing, remote cache, visibility, reproducibility |

Không có công cụ nào tự động đảm bảo mọi build đều nhanh, an toàn hoặc tái lập. Kết quả phụ thuộc cách cấu hình, plugin/rules, toolchain và CI environment.

### Gradle: task graph và configurations

Gradle mô tả công việc bằng task và quan hệ giữa chúng. Task có thể khai báo inputs, outputs, dependencies và sử dụng providers để nối producer với consumer.

Ví dụ:

~~~kotlin
tasks.register<Jar>("bundleApi") {
    from(sourceSets.main.get().output)
    archiveClassifier.set("api")
}
~~~

Gradle có thể thực thi task producer cần thiết, bỏ qua task up-to-date và dùng build cache nếu task được khai báo đúng. Configuration avoidance và provider API giúp trì hoãn việc tạo/cấu hình task.

### Maven: lifecycle và plugin goals

Maven thường tổ chức công việc theo lifecycle như validate, compile, test, package, verify, install và deploy. Plugin goals được bind vào phase.

Ví dụ:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>21</release>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Khi chạy phase package, Maven thực thi các phase trước đó trong lifecycle tương ứng. Việc migration cần map task graph Gradle sang lifecycle phases và plugin executions Maven, không chỉ đổi tên task thành goal.

### Ant: target graph tường minh

Ant thường mô tả target và dependency giữa target:

~~~xml
<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"/>
</target>

<target name="jar" depends="compile">
    <jar destfile="build/app.jar"
         basedir="build/classes"/>
</target>
~~~

Target jar phụ thuộc compile. Build script có thể chứa nhiều thao tác file imperative, property expansion và target condition. Khi chuyển từ Ant, cần chuyển cả thứ tự thao tác và side effects, không chỉ chuyển danh sách target.

### Bazel: targets và actions với inputs/outputs khai báo

Bazel mô tả target và rule; rule tạo actions có input/output xác định. Mô hình này thường nhấn mạnh declared dependencies, sandboxing và cache.

Ví dụ BUILD file đơn giản:

~~~python
java_library(
    name = "domain",
    srcs = glob(["src/main/java/**/*.java"]),
    deps = [
        "//third_party:annotations",
    ],
)
~~~

Cấu hình thực tế còn phụ thuộc ruleset, toolchain, module/repository configuration và conventions của workspace. Khi chuyển sang Bazel, cần xác định mọi file/tool mà action đọc và mọi output mà action tạo. Những input không khai báo có thể khiến sandbox hoặc cache behavior khác mong đợi.

## 5. Dependency scope không thể chuyển đổi bằng tên tương tự

Dependency scope/configuration là một trong những phần dễ sai nhất khi đổi công cụ.

Gradle Java Plugin có các configuration như:

- implementation
- api (với Java Library Plugin)
- compileOnly
- runtimeOnly
- testImplementation
- testRuntimeOnly
- annotationProcessor
- testAnnotationProcessor

Maven có các dependency scopes như:

- compile
- provided
- runtime
- test
- system
- import (trong dependencyManagement cho BOM)

Hai mô hình có điểm tương đồng nhưng không hoàn toàn ánh xạ một-một.

| Nhu cầu | Gradle thường dùng | Maven thường dùng | Lưu ý |
|---|---|---|---|
| Dependency nội bộ compile và runtime | implementation | compile | Phạm vi truyền sang consumer có khác biệt theo loại component và metadata |
| Dependency thuộc public API library | api | compile dependency được công bố | Cần kiểm tra POM/metadata và compile classpath consumer |
| API do môi trường chạy cung cấp | compileOnly | provided | Phải xác nhận runtime container thật sự cung cấp |
| Chỉ cần lúc chạy | runtimeOnly | runtime | Kiểm tra test/runtime package |
| Chỉ dùng trong test | testImplementation | test | Kiểm tra test runtime và transitive behavior |
| Annotation processor | annotationProcessor | maven-compiler-plugin annotationProcessorPaths hoặc cơ chế tương ứng | Processor path cần được tách khỏi application runtime |

Không giả định scope có cùng tên sẽ có cùng transitivity hoặc publication semantics.

### Ví dụ: compileOnly và provided

Một thư viện Servlet API có thể được khai báo là compileOnly trong Gradle vì application server cung cấp nó lúc runtime. Trong Maven, provided có mục đích gần tương tự. Nhưng cần kiểm tra packaging, test runtime và container thực tế.

Nếu application chạy độc lập mà không có container cung cấp API đó, cấu hình compileOnly/provided có thể khiến runtime thiếu class.

### Ví dụ: api và Maven compile

Gradle api của Java Library công khai dependency qua API của thư viện cho consumer compile. Maven compile scope có semantics transitive khác với Gradle implementation. Nếu chuyển một Java library, cần kiểm tra consumer compile classpath và POM được publish, không chỉ compile nội bộ thành công.

## 6. Dependency resolution và version selection

Cùng khai báo dependency trực tiếp không bảo đảm hai công cụ resolve cùng graph.

Gradle có conflict resolution, constraints, platforms, rich versions, component metadata rules, dependency substitution, capabilities và variant-aware selection.

Maven có dependency mediation, nearest-definition behavior, dependencyManagement, exclusions, optional dependencies và profiles.

Bazel thường yêu cầu dependencies/rules được khai báo theo cơ chế repository/module và ruleset, với version pinning tùy cách quản lý module.

Các câu hỏi cần trả lời:

- Version nào thực sự được chọn khi nhiều dependency yêu cầu cùng module?
- Có BOM/platform hoặc dependencyManagement không?
- Exclusion có cùng phạm vi không?
- Optional dependency được consumer xử lý ra sao?
- Dependency có classifier, variant hoặc capability đặc biệt không?
- Repository order và metadata có ảnh hưởng resolution không?
- Snapshot/dynamic versions có được dùng không?
- Local repository/cache có làm kết quả khác giữa máy không?

### So sánh resolved graph, không chỉ declaration

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Với Bazel, dùng query/cquery theo target và configuration phù hợp:

~~~bash
bazel query 'deps(//app:app)'
~~~

Các lệnh này không có output cùng định dạng và semantics. Hãy chuẩn hóa kết quả thành danh sách tọa độ/version/role cần so sánh, sau đó giải thích mọi khác biệt có chủ đích.

## 7. Plugin và extension cũng là dependency của build

Một build không chỉ phụ thuộc thư viện ứng dụng. Plugin có thể thực thi code, thêm task, sửa output hoặc thay đổi dependency resolution.

Khi chuyển đổi, hãy lập inventory:

- Compiler plugin hoặc Java compile configuration.
- Test runner/provider.
- Code coverage.
- Static analysis và lint.
- Formatter.
- Annotation processing và code generation.
- Resource filtering.
- Packaging, shading và assembly.
- Publishing, signing và release.
- Container/image build.
- License, vulnerability và policy checks.

Không nên chỉ tìm một plugin mới có tên gần giống plugin cũ. Hãy so sánh:
- Phiên bản và JDK compatibility.
- Default behavior.
- Input/output directories.
- Include/exclude patterns.
- Failure conditions và exit codes.
- Report formats.
- Incremental/cache behavior.
- CI integration và credentials.
- Publication side effects.

Một plugin có thể thực hiện cùng mục tiêu nhưng dùng default rules khác. Ví dụ formatter có thể dùng line length khác; test plugin có thể chọn engine khác; shading plugin có thể xử lý service descriptors khác.

## 8. Compile equivalence: compiler và source layout

Để compile tương đương, cần giữ đúng những thuộc tính ảnh hưởng bytecode và API:

- JDK compiler/toolchain version và vendor nếu cần.
- Java source/target hoặc --release.
- Encoding.
- Compiler arguments.
- Annotation processors và processor options.
- Generated source directories.
- Compiler warnings và failure policy.
- Source roots và exclusions.
- Module path/classpath behavior.
- Multi-release JAR configuration nếu có.

Ví dụ Gradle:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(21)
}
~~~

Ví dụ Maven:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.13.0</version>
  <configuration>
    <release>21</release>
    <encoding>UTF-8</encoding>
  </configuration>
</plugin>
~~~

Hai cấu hình trông tương tự nhưng vẫn cần xác nhận JDK thực tế được dùng, annotation processor, compiler implementation và các compiler flags bổ sung.

### Annotation processing

Gradle thường tách processor bằng annotationProcessor và testAnnotationProcessor. Maven Compiler Plugin có cấu hình annotationProcessorPaths ở những version phù hợp. Nếu chuyển mà chỉ thêm processor JAR vào dependency thường, processor có thể xuất hiện trên runtime classpath hoặc bị phát hiện khác dự kiến.

Hãy so sánh:
- Processor artifact và version.
- Processor path và transitive dependencies.
- Compiler options -A...
- Generated source output.
- Processor discovery và service registration.
- Test source processing.
- JDK compatibility.

Generated source cần được tái tạo và compile ở công cụ mới. Không nên commit generated output chỉ để che việc processor chưa được cấu hình đúng.

## 9. Resource processing và packaging equivalence

Resource processing có thể thay đổi artifact mà không tạo compile error.

Các behavior cần kiểm tra:

- Source resource directories.
- Include/exclude patterns.
- Filtering và property expansion.
- Encoding.
- File rename/copy rules.
- Duplicate resource handling.
- Service descriptors.
- Manifest attributes.
- Archive timestamps và entry ordering.
- Shading/relocation.
- Multi-release JAR entries.
- Distribution layout.

Ví dụ Maven resource filtering:

~~~xml
<resources>
  <resource>
    <directory>src/main/resources</directory>
    <filtering>true</filtering>
  </resource>
</resources>
~~~

Trong Gradle, filtering thường được cấu hình qua processResources/CopySpec. Cú pháp và escaping khác nhau; token @APP_VERSION@ có thể bị xử lý ở một giai đoạn khác hoặc bị thay bằng giá trị khác.

Không so sánh file JAR bằng cách chỉ nhìn kích thước. Hãy liệt kê archive entries, giải nén và so nội dung class/resource quan trọng.

~~~bash
jar tf build/libs/app.jar
unzip -p build/libs/app.jar META-INF/MANIFEST.MF
~~~

Với hai artifact:

~~~bash
sha256sum old-build/app.jar new-build/app.jar
~~~

Checksum khác không nhất thiết là lỗi chức năng; cần tìm khác biệt entry và metadata để phân loại.

## 10. Test equivalence: cùng tên test không có nghĩa cùng phạm vi

Test là một vùng migration có rủi ro cao vì build mới có thể báo success dù ít test hơn được phát hiện.

Cần so sánh:

- Unit test source roots.
- Integration test source sets/profiles.
- Test engine và provider versions.
- JUnit 4/JUnit 5/TestNG discovery.
- Include/exclude patterns.
- Tags/groups/categories.
- Test filters.
- Fork count và parallel execution.
- JVM arguments và system properties.
- Environment variables.
- Working directory.
- Test fixtures và generated test sources.
- Test reports, skipped/failed counts.
- Retry/quarantine behavior.
- Testcontainers hoặc external services.

Ví dụ Gradle:

~~~kotlin
tasks.test {
    useJUnitPlatform()
    maxParallelForks = 2
    systemProperty("user.timezone", "UTC")
}
~~~

Ví dụ Maven Surefire:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <version>3.5.2</version>
  <configuration>
    <systemPropertyVariables>
      <user.timezone>UTC</user.timezone>
    </systemPropertyVariables>
  </configuration>
</plugin>
~~~

Cấu hình minh họa không chứng minh test discovery tương đương. Hãy so sánh danh sách test thực tế được chạy và report counts.

### Unit test và integration test

Gradle có thể dùng source set/task riêng cho integrationTest. Maven có thể dùng Failsafe Plugin với integration-test và verify phases hoặc một profile riêng. Ant/Bazel có mô hình khác.

Phải xác nhận invocation release chạy đúng integration tests. Nếu build mới chỉ chạy unit tests nhưng bỏ integration tests, build có thể nhanh hơn nhưng không tương đương.

## 11. Lifecycle và task ordering

Gradle task graph không giống Maven lifecycle phase hoặc Ant target graph.

Ví dụ:
- Gradle check thường gom các verification tasks được gắn vào lifecycle.
- Maven verify chạy các phase trước đó trong default lifecycle, bao gồm test và package theo bindings đã cấu hình.
- Ant chỉ chạy những target được yêu cầu cùng dependencies của chúng.
- Bazel chạy actions cần cho target được yêu cầu.

Vì vậy, mapping một task Gradle sang một Maven phase có thể làm chạy thêm hoặc bỏ sót bước.

### Lập bảng mapping lifecycle

| Mục tiêu | Gradle thường gặp | Maven thường gặp | Cần xác minh |
|---|---|---|---|
| Kiểm tra cấu hình cơ bản | help/validate task custom | validate | Plugin/custom validation |
| Compile | compileJava | compile | Source/target/toolchain |
| Unit tests | test | test | Provider, filters, test count |
| Package | jar/war/assemble | package | Archive contents |
| Verification | check | verify | Tất cả checks và reports |
| Lưu vào local artifact repository | publishToMavenLocal | install | Coordinates và metadata |
| Publish lên remote repository | publish | deploy | Credentials, signing, POM/metadata |

Các phase/task mặc định có thể được thay đổi bởi plugin và project configuration. Bảng này là điểm bắt đầu để lập mapping, không phải quy tắc thay thế mọi build.

## 12. Multi-module và project boundaries

Multi-project Gradle build, Maven reactor và Bazel target graph đều có thể biểu diễn module dependencies, nhưng cách lập kế hoạch và công bố module khác nhau.

Gradle dùng settings để include projects và project dependencies/variants. Maven reactor xác định các module từ aggregator POM và sắp xếp build theo quan hệ dependency/plugin extension. Bazel dùng labels và target dependencies.

Khi chuyển đổi, cần xác nhận:

- Module nào là library, application, plugin hoặc distribution.
- Dependency direction có giữ nguyên không.
- Build order được suy ra từ dependency hay viết thủ công.
- Có module chỉ chứa test/integration tooling không.
- Artifact coordinates và module names có giữ nguyên không.
- Có cycle hoặc dependency implicit trước đây không.
- Cross-module test fixtures và generated outputs được nối đúng không.

Không nên gom tất cả module vào một build script mới chỉ để đơn giản hóa. Việc thay đổi module boundaries có thể ảnh hưởng API, dependency visibility, build parallelism và ownership.

### Mapping multi-module Gradle sang Maven reactor

Gradle settings:

~~~kotlin
rootProject.name = "order-system"
include(":domain", ":application")
~~~

Maven aggregator POM:

~~~xml
<packaging>pom</packaging>
<modules>
  <module>domain</module>
  <module>application</module>
</modules>
~~~

Maven reactor sẽ build module theo dependency relationships và reactor ordering. Cần xác nhận parent POM, dependencyManagement và module dependencies được khai báo đúng; thứ tự trong danh sách modules không nên được dùng như cơ chế duy nhất để diễn tả dependency.

## 13. Publication equivalence: POM và metadata rất quan trọng

Với thư viện Java, build thành công và tạo JAR đúng chưa đủ. Consumer còn nhận publication metadata.

Cần so sánh:
- Group, artifact, version và packaging.
- POM dependencies và scopes.
- Optional dependencies và exclusions.
- Dependency management/BOM imports.
- Gradle Module Metadata nếu được publish.
- Classifiers và attached artifacts.
- Sources/Javadoc JAR.
- Signatures/checksums.
- Repository destination và repository layout.
- Snapshot/release behavior.
- Version mapping và publication variants.

Gradle Maven Publish Plugin có thể publish POM và Gradle Module Metadata. Maven deploy plugin có thể tạo POM và deploy artifact theo Maven lifecycle. Hai kết quả có thể khác về metadata ngay cả khi JAR giống nhau.

### Consumer test là bằng chứng quan trọng

Tạo một project consumer độc lập, khai báo dependency tới artifact được publish vào staging/local repository, rồi:
- Resolve dependency.
- Compile code sử dụng public API.
- Chạy test/runtime.
- Kiểm tra transitive dependencies.
- Xác minh classifier và metadata được chọn.

Đây là cách phát hiện lỗi không thấy khi build module producer một mình, ví dụ public API phụ thuộc type không được công bố hoặc scope runtime sai.

## 14. Incremental build và cache không có mapping một-một

Gradle có incremental task execution và build cache. Maven có thể dùng plugin/compiler incremental behavior, local repository và các cache riêng; Bazel nhấn mạnh action cache và remote cache; Ant thường phụ thuộc task-level up-to-date checks và file timestamps.

Không thể giả định chuyển công cụ sẽ giữ cùng cache hit rate hoặc cùng cách xác định stale output.

Cần đánh giá:
- Task nào được bỏ qua khi input không đổi?
- File nào được coi là input?
- Output nào được task sở hữu?
- Thay đổi source có làm chạy lại đúng task không?
- Xóa source có loại output cũ không?
- Cache key có chứa toolchain và parameters cần thiết không?
- Remote cache có quyền ghi/đọc được kiểm soát không?
- Build sạch và build tăng dần có tạo cùng nội dung output không?

Một công cụ mới có thể chạy lại nhiều việc hơn mà vẫn đúng chức năng. Đó là khác biệt hiệu năng, không nhất thiết là sai tương đương. Nhưng nếu build mới bỏ qua task cần chạy do input không khai báo, đó là lỗi correctness.

## 15. Hermeticity và reproducibility

Các công cụ có mức hỗ trợ khác nhau cho sandboxing, declared inputs và remote execution.

Bazel thường khuyến khích rules khai báo đầy đủ inputs/outputs và chạy actions trong sandbox theo cấu hình. Gradle hỗ trợ task input/output annotations, build cache, toolchains và có thể chạy trong container/network-restricted environment. Maven và Ant cũng có thể được cô lập bằng container, dependency controls và task/plugin configuration, nhưng cần đánh giá hành vi plugin và script.

Đừng so sánh bằng slogan “tool A hermetic hơn tool B”. Hãy kiểm tra build cụ thể:

- Dependency và plugin versions có pin không?
- Toolchain có xác định không?
- Task có đọc file ngoài repository không?
- Có network access không được khai báo không?
- Archive timestamps và ordering có ổn định không?
- Environment variables và locale có được kiểm soát không?
- Hai workspace sạch có tạo artifact giống nhau không?

Nếu chuyển từ Gradle sang Bazel, việc phải khai báo inputs/outputs tường minh có thể làm lộ những dependency ẩn mà build cũ vô tình dựa vào. Đó là thông tin hữu ích, nhưng cần ngân sách để sửa build rules và tool wrappers.

## 16. Security và supply-chain controls

Một build tương đương cần giữ các kiểm soát bảo mật đang có.

So sánh:
- Repository allowlists và content filters.
- Dependency locking/version constraints.
- Checksum/signature verification.
- Secret handling và credential scopes.
- Plugin/ruleset provenance.
- Build sandbox/network access.
- SBOM generation.
- Vulnerability/license scanning.
- Artifact signing và build provenance.
- Release approval và immutable artifact promotion.

Nếu công cụ mới không có plugin tương đương, có thể tích hợp scanner hoặc verifier như một bước CI độc lập. Nhưng cần giữ đúng failure policy: nếu build cũ fail release khi có critical vulnerability, build mới không được biến scanner thành bước advisory mà không có quyết định thay đổi policy.

Không đặt credentials publish vào mọi task. Cấp quyền tối thiểu cho stage cần publish/sign và chỉ sau khi verification gates hoàn tất.

## 17. Các khác biệt thường bị bỏ sót khi migration

| Khu vực | Khác biệt có thể xảy ra | Hậu quả |
|---|---|---|
| Version conflict | Gradle và Maven chọn dependency khác | Runtime behavior hoặc API khác |
| Transitivity | Scope/exclusion semantics khác | Thiếu hoặc thừa dependency |
| Annotation processing | Processor path/discovery khác | Generated code thiếu hoặc khác |
| Resource filtering | Token syntax/encoding khác | Config trong artifact sai |
| Test discovery | Provider/filter khác | Test không chạy nhưng build vẫn xanh |
| Integration tests | Lifecycle/profile mapping sai | Release thiếu kiểm tra |
| Service files | Merge behavior khác | ServiceLoader không tìm thấy provider |
| Manifest | Default attributes khác | Startup/metadata behavior thay đổi |
| Shading | Relocation/resource transformers khác | Class/resource collision |
| JPMS | Module path inference khác | Module readability/access error |
| Publication | POM/Gradle metadata khác | Consumer resolve sai |
| Archive metadata | Timestamp/order/permissions khác | Checksum khác hoặc reproducibility giảm |
| Build cache | Input/output model khác | Build chậm hoặc stale output |
| CI profiles | Environment variables/profile activation khác | Build local và release không giống |
| Toolchain | JDK được chọn khác | Bytecode hoặc compiler diagnostics khác |

Đây là các khu vực cần chủ động kiểm tra, không phải khẳng định rằng mọi migration đều gặp tất cả khác biệt.

## 18. Thiết kế bộ kiểm chứng tương đương

Trước khi chuyển hoàn toàn, hãy tạo một bộ kiểm chứng có thể chạy trên cả build cũ và build mới.

Một bộ kiểm chứng hữu ích có thể gồm:

### Compile checks
- Cùng source revision.
- Cùng Java release target.
- Cùng compiler options quan trọng.
- Cùng annotation processors và generated source expectations.
- Không có warning/error mới ngoài danh sách được chấp nhận.

### Dependency checks
- So sánh compile/runtime/test dependency graph.
- Xác nhận version selection và exclusions.
- Xác nhận public API dependencies được công bố đúng.
- Xác nhận repository policy.

### Test checks
- So sánh test class/test case được phát hiện.
- So sánh executed/skipped/failed counts.
- Xác nhận unit, integration và acceptance tests.
- So sánh JVM arguments, system properties và environment.

### Artifact checks
- Liệt kê archive entries.
- So sánh class/resource/service descriptors.
- Kiểm tra manifest, classifiers và generated metadata.
- So sánh digest nếu yêu cầu byte-for-byte.
- Nếu digest khác, giải thích từng khác biệt có ý nghĩa.

### Publication checks
- So sánh coordinates.
- So sánh POM và metadata.
- Dùng consumer project để resolve/compile/run.
- Kiểm tra signatures và checksums.

### Pipeline checks
- Xác nhận các release gates vẫn chạy.
- Xác nhận deploy dùng artifact đã build/test.
- Xác nhận provenance, SBOM và signing policy.
- Xác nhận credentials chỉ có ở stage cần thiết.

## 19. Phân biệt khác biệt có thể chấp nhận và regression

Không nên yêu cầu mọi byte của output phải giống nhau nếu công cụ mới có archive format hoặc metadata khác theo thiết kế. Nhưng cũng không nên bỏ qua khác biệt chỉ vì test hiện tại vẫn pass.

Tạo một danh sách chấp nhận khác biệt có lý do:

| Khác biệt | Phân loại | Cần quyết định |
|---|---|---|
| JAR timestamp thay đổi | Có thể là metadata-only | Có yêu cầu reproducible checksum không? |
| Dependency runtime được thêm | Có thể là regression | Có cần thiết cho runtime không? |
| POM scope thay đổi | Có thể phá consumer | Consumer contract có đổi được phê duyệt không? |
| Test count giảm | Regression tiềm ẩn | Test nào bị bỏ qua và vì sao? |
| Generated source khác | Cần điều tra | Do processor version hay compiler behavior? |
| Build nhanh hơn do task bị bỏ | Không tự động là cải thiện | Task đó có thật sự không cần không? |
| Cache hit giảm | Hiệu năng | Input/cache model mới có thể tối ưu không? |
| Module output layout đổi | Có thể chấp nhận | CI/deploy/IDE có phụ thuộc path cũ không? |

Mọi khác biệt nên có owner, lý do, ảnh hưởng và quyết định. Không nên để khác biệt âm thầm đi vào release.

## 20. Quy trình migration từng giai đoạn

Một quy trình có kiểm soát có thể thực hiện như sau:

1. **Đóng băng baseline:** chọn commit, tool versions và môi trường của build hiện tại.
2. **Kiểm kê build contract:** ghi modules, dependencies, tasks, tests, outputs, publication và CI gates.
3. **Xác định mục tiêu:** lý do chuyển đổi là tốc độ, hermeticity, hệ sinh thái, tiêu chuẩn tổ chức hay giảm maintenance?
4. **Chọn công cụ và phiên bản:** kiểm tra plugin/rules support, JDK compatibility và team capability.
5. **Thiết kế mapping:** lập ma trận hành vi cũ/mới và ghi các gap.
6. **Chuyển một module đại diện:** chọn module có compile, test, resources và publication để thử đầy đủ.
7. **So sánh output:** compile, dependency graph, test reports, JAR entries và publication metadata.
8. **Chạy consumer verification:** dùng artifact mới từ staging repository trong project độc lập.
9. **Chuyển các module tiếp theo:** giữ dependency boundaries và release process rõ ràng.
10. **Chạy song song hai pipeline:** cùng source revision và môi trường được kiểm soát.
11. **Đánh giá performance/security:** đo clean/incremental build, cache, network, credentials và provenance.
12. **Chấp nhận sai khác có chủ đích:** ghi nhận và phê duyệt từng khác biệt.
13. **Chuyển CI/release:** chỉ khi parity checks đạt và rollback path rõ ràng.
14. **Loại bỏ build cũ:** sau khi release và consumer migration ổn định, cập nhật documentation và ownership.

Không nên xóa build cũ ngay khi build mới compile được. Giữ baseline trong giai đoạn song song giúp điều tra regression và so sánh artifact.

## 21. Chọn module pilot phù hợp

Module đầu tiên nên đủ đại diện để kiểm tra các phần quan trọng nhưng có phạm vi kiểm soát được.

Một pilot tốt thường có:
- Java source và resource.
- Unit tests.
- Một số dependency bắc cầu.
- Annotation processor hoặc generated code nếu dự án có dùng.
- JAR publication hoặc runtime packaging.
- CI build đơn giản.

Tránh chọn module rỗng chỉ có một class vì nó không bộc lộ khác biệt về dependency, tests và packaging. Cũng không nhất thiết chọn module phức tạp nhất đầu tiên nếu nó có nhiều plugin custom và hệ thống ngoài.

Sau pilot, ghi lại những gì mapping được, những gap còn lại và công sức chuyển đổi. Dùng dữ liệu đó để ước lượng các module còn lại.

## 22. Đo hiệu năng trên cùng điều kiện

Nếu lý do migration là build performance, hãy so sánh công bằng.

Các điều kiện nên cố định:
- Cùng commit/source tree.
- Cùng máy hoặc loại runner.
- Cùng JDK/toolchain nếu cả hai công cụ hỗ trợ.
- Cùng dependency repository và network conditions.
- Tách clean build và incremental build.
- Tách cache cold và cache warm.
- Cùng số worker/CPU/memory khi có thể.
- Cùng test scope và verification gates.

Đo các chỉ số:
- Configuration/setup time.
- Dependency resolution time.
- Compile time.
- Test time.
- Packaging/publication time.
- Total wall-clock time.
- CPU/memory usage.
- Cache hit/miss.
- Tỷ lệ task/action được thực thi lại.
- Thời gian và độ ổn định của CI.

Không so sánh Gradle build chỉ chạy compile với Maven build chạy verify, vì scope khác nhau. Trước tiên phải so sánh cùng contract; sau đó mới đo riêng các profile sử dụng thường ngày.

## 23. Rollback và coexistence trong giai đoạn chuyển đổi

Trong giai đoạn migration, có thể duy trì hai build entry points tạm thời:

~~~text
./gradlew build
mvn verify
~~~

Nếu CI chạy cả hai, cần bảo đảm:
- Hai build không ghi đè output directory của nhau.
- Không dùng chung thư mục staging có file cũ.
- Cùng commit và dependency inputs được xác định.
- Artifact được đặt tên/đường dẫn riêng.
- Chỉ một pipeline có quyền publish release chính thức.
- Không để cả hai pipeline ghi đè cùng coordinates/version.
- Có tiêu chí rõ để kết thúc giai đoạn song song.

Rollback không chỉ là quay lại build script. Nếu publication metadata, dependency versions hoặc artifact coordinates đã thay đổi, cần đánh giá tác động tới consumer và repository. Giữ artifact cũ bất biến và lưu provenance giúp điều tra khi cần quay lại.

## 24. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Hai công cụ đều tạo JAR nên tương đương | JAR có thể khác class/resource/manifest, dependency và publication metadata. |
| Task và goal có tên giống nhau thì cùng hành vi | Plugin defaults, lifecycle và test provider có thể khác. |
| Đổi Gradle implementation sang Maven compile là mapping đầy đủ | Scope và transitivity không ánh xạ một-một; phải kiểm tra consumer metadata. |
| Build mới thành công nghĩa là test tương đương | Test discovery/filter có thể làm test bị bỏ qua mà build vẫn xanh. |
| Dependency declaration giống nhau thì resolved graph giống nhau | Conflict resolution, BOM, constraints, exclusions và repository metadata có thể khác. |
| Có thể so checksum JAR để kết luận mọi thứ | Checksum khác cần phân tích; checksum giống không chứng minh CI/release workflow tương đương. |
| Build nhanh hơn luôn là tốt hơn | Task hoặc test có thể đã bị bỏ sót. |
| Công cụ mới hermetic hơn theo mặc định | Hermeticity phụ thuộc declared inputs, plugins/rules, network và môi trường thực tế. |
| Có thể chuyển mọi module cùng lúc | Pilot và migration song song giúp giảm phạm vi regression và hỗ trợ rollback. |
| Chỉ cần cập nhật CI command | Cần chuyển cả test, verification, signing, publication, provenance và deployment contract. |

## 25. Nguyên tắc cần ghi nhớ

Đánh giá tính tương đương khi chuyển đổi build tool phải bắt đầu từ hợp đồng build hiện tại: source, toolchain, dependency graph, task/lifecycle, tests, resources, artifacts, publication và CI controls. Mỗi công cụ có mô hình thực thi riêng; Gradle task graph, Maven lifecycle, Ant target graph và Bazel action graph không thể được ánh xạ chỉ bằng tên hoặc cú pháp.

Hãy lập ma trận hành vi cũ/mới, so sánh dependency đã resolve, test thực sự được chạy, nội dung artifact và metadata consumer nhận được. Đo performance trên cùng scope và môi trường; phân loại mọi khác biệt thành thay đổi được chấp nhận hoặc regression cần sửa. Chuyển một module pilot, chạy hai pipeline trên cùng source revision, xác minh consumer và chỉ chuyển release khi các contract quan trọng đã được chứng minh.

Một migration thành công giữ được hành vi mà dự án cần, làm rõ những thay đổi có chủ đích và cung cấp bằng chứng để nhóm tin rằng công cụ mới tạo, kiểm tra và phát hành đúng sản phẩm.

