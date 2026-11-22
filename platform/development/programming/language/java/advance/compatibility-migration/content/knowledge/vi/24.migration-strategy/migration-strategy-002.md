# Nâng cấp công cụ và dependency theo thứ tự phụ thuộc

Trong một dự án Java lớn, việc đổi phiên bản JDK thường kéo theo hàng loạt quyết định: phải nâng Maven hay Gradle trước, compiler plugin nào hỗ trợ bytecode mới, JUnit và công cụ coverage có chạy được trên JVM đích không, framework cần phiên bản Java tối thiểu nào, và các dependency do BOM quản lý có được nâng đồng bộ hay không. Nếu thay tất cả version cùng lúc, một lỗi `NoSuchMethodError` hoặc `UnsupportedClassVersionError` xuất hiện ở cuối pipeline rất khó truy ngược về thay đổi ban đầu.

Vì vậy, **thứ tự nâng cấp phải dựa trên quan hệ phụ thuộc và yêu cầu tương thích, không dựa đơn thuần vào tên công cụ hoặc độ mới của phiên bản**. Mục tiêu là xây dựng chuỗi thay đổi mà tại mỗi chặng, công cụ build có thể chạy, mã có thể biên dịch, test được khám phá đúng, artifact có thể đóng gói và ứng dụng có thể khởi động trong một tổ hợp phiên bản được hỗ trợ.

Bài học thuộc chương **Chiến lược chuyển đổi** của module **Java Advance Compatibility Migration**. Trọng tâm là phương pháp lập bản đồ dependency, sắp xếp các bước nâng JDK, build tool, plugin, thư viện và framework theo điều kiện tiên quyết; sau đó chứng minh từng bước bằng kết quả build, kiểm thử và runtime thay vì chỉ dựa vào một lần build xanh.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt phụ thuộc giữa **các thành phần của ứng dụng** với phụ thuộc giữa **các bước migration**.
- Lập dependency graph có chiều, xác định bước nào bắt buộc thực hiện trước và tìm đường đi nâng cấp khả thi.
- Kiểm kê JDK, Maven/Gradle, plugins, annotation processors, test engines, agents, framework BOM và runtime dependencies.
- Hiểu tại sao JVM chạy build, JDK biên dịch, JDK chạy test và JDK production có thể khác nhau.
- Chọn các chặng nâng cấp dựa trên compatibility matrix và minimum Java version.
- Dùng dependency tree, effective POM, dependency insight và locking để phát hiện version lệch, dependency trùng và phụ thuộc bắc cầu.
- Tách bước nâng toolchain, nâng thư viện, đổi API và đổi hành vi để dễ điều tra regression.
- Thiết kế quality gate, rollback và báo cáo cho từng chặng migration.
- Xử lý các tình huống khó như vòng phụ thuộc, plugin không hỗ trợ JDK mới, code generation, Jakarta namespace và thư viện đã hết hỗ trợ.

## 2. Hai loại quan hệ phụ thuộc cần phân biệt

### 2.1. Dependency graph của phần mềm

Đây là quan hệ giữa module, thư viện và công cụ khi xây dựng/chạy chương trình.

Ví dụ:

```text
order-service
├── spring-like-framework
│   ├── dependency-injection-core
│   ├── web-runtime
│   └── logging-api
├── persistence-module
│   ├── orm-provider
│   └── jdbc-driver
├── json-library
└── test-tooling
    ├── junit-platform
    ├── mocking-library
    └── coverage-agent
```

Graph cho biết thư viện nào được đưa vào compile/runtime/test classpath và version có thể do dependency management quyết định. Một dependency của dependency khác thường được gọi là **transitive dependency**.

### 2.2. Dependency graph của kế hoạch migration

Graph thứ hai mô tả **bước nâng cấp nào cần có kết quả của bước khác**.

Ví dụ:

```text
Kiểm kê hiện trạng
       |
       v
Chọn JDK đích và compatibility constraints
       |
       +--------------------------+
       |                          |
       v                          v
Build tool hỗ trợ JDK       Test tools hỗ trợ JDK
       |                          |
       +------------+-------------+
                    |
                    v
        Framework/dependency baseline
                    |
                    v
          Sửa source/config/API
                    |
                    v
           Integration verification
                    |
                    v
           Packaging và deployment
```

Sơ đồ trên là minh họa, không phải thứ tự cố định cho mọi dự án. Có trường hợp framework mới yêu cầu JDK mới trước; có trường hợp Gradle cũ không thể chạy trên JDK mới nên phải nâng Gradle wrapper **khi vẫn dùng JDK cũ** trước. Quan hệ tiên quyết phải được lấy từ tài liệu tương thích và điều kiện thực tế của dự án.

### 2.3. Cạnh “A phải có trước B” là gì?

Nên định nghĩa quan hệ một cách rõ ràng:

```text
A -> B
nghĩa là hoàn thành/đạt điều kiện A trước khi thực hiện hoặc xác nhận B.
```

Ví dụ:

- Maven Compiler Plugin hỗ trợ `--release` và class-file target yêu cầu phải có trước khi build mã mới.
- Mockito/Byte Buddy phiên bản hỗ trợ class-file JDK đích phải có trước khi kết luận test mocking chạy được trên JDK đó.
- Servlet container hỗ trợ Jakarta Servlet API tương ứng phải có trước khi triển khai ứng dụng đã chuyển từ `javax.servlet` sang `jakarta.servlet`.
- Schema/database migration có contract tương thích phải được chuẩn bị trước khi đưa code mới vào production.

Đây là **phụ thuộc triển khai**. Chúng khác với một dependency được khai báo trong `pom.xml` hoặc `build.gradle`.

## 3. Không tồn tại một thứ tự “nâng JDK trước” áp dụng cho mọi dự án

### 3.1. Tương thích là một bài toán nhiều chiều

Cần kiểm tra ít nhất các chiều:

| Thành phần | Ràng buộc phải xác minh |
| --- | --- |
| JDK chạy Maven/Gradle | Build tool và plugin có chạy trên JVM này không? |
| JDK dùng để compile | Compiler có hỗ trợ source/API/class-file level yêu cầu không? |
| Java release của artifact | Bytecode và API có tương thích mức Java mà sản phẩm cam kết không? |
| JDK chạy unit/integration test | JUnit engine, mocking agent và coverage agent có hỗ trợ không? |
| Framework/application runtime | Version framework có hỗ trợ JDK, servlet container, module system và dependency thực tế không? |
| Code generation | Annotation processor, parser/bytecode generator có đọc/ghi được class file mới không? |
| Packaging | Plugin shading, native packaging, Docker image, buildpack có hỗ trợ đầu ra không? |
| Production runtime | OS/container/JDK vendor, TLS, CPU architecture và thư viện native phù hợp không? |

Một tổ hợp có thể compile thành công nhưng fail khi chạy test; một tổ hợp khác test pass nhưng server production không còn đáp ứng minimum version.

### 3.2. Thí dụ hai thứ tự hợp lệ khác nhau

**Trường hợp A: build tool quá cũ để chạy JDK mới**

```text
Bản hiện tại: JDK cũ + Gradle wrapper cũ
                  |
                  v
Nâng Gradle wrapper lên bản hỗ trợ cả JDK cũ và JDK đích
                  |
                  v
Nâng plugin và test dependencies tương thích
                  |
                  v
Đổi JDK chạy build/runtime
                  |
                  v
Sửa source, test, đóng gói và triển khai
```

Nếu đổi JDK chạy Gradle trước, Gradle có thể thất bại ngay ở giai đoạn cấu hình build, chưa tới bước compile.

**Trường hợp B: framework mới yêu cầu JDK cao hơn**

```text
Framework cũ + JDK cũ
        |
        v
Nâng build/test tool đủ chạy với cả hai trạng thái
        |
        v
Chuẩn bị JDK mới và toolchain
        |
        v
Nâng framework sang dòng bắt buộc JDK mới
        |
        v
Sửa API/config và integration tests
```

Ở đây, không thể đưa framework mới vào runtime JDK cũ nếu nó đã tăng Java baseline. Một số bước có thể thực hiện trên nhánh/staging trong cùng release; thứ tự vẫn được quyết định bởi compatibility, không phải một mẹo máy móc.

### 3.3. Chọn “trạng thái trung gian được hỗ trợ”

Mỗi chặng migration nên tạo ra một trạng thái có thể kiểm chứng:

```text
S0: Tổ hợp cũ đang chạy ổn định
S1: Tooling mới, ứng dụng/JDK cũ vẫn build được
S2: JDK đích, framework đang ở tổ hợp được hỗ trợ
S3: Framework và dependency đích, source/config đã chuyển
S4: Tổ hợp mới đã qua kiểm thử và sẵn sàng rollout
```

Không phải mọi dự án đều có đủ S1–S4 và không phải tất cả trạng thái trung gian đều cần được phát hành. Nhưng **đừng chấp nhận một trạng thái trung gian không được hỗ trợ như bằng chứng production-ready**; nếu phải dùng tạm để thực hiện migration, ghi rõ giới hạn và không triển khai nó.

## 4. Bước 1: kiểm kê “bốn JVM” và công cụ thực tế

### 4.1. JVM chạy build tool

Maven hoặc Gradle chạy bên trong một JVM. Nó có thể khác JDK mà project dùng để compile nhờ Maven Toolchains hoặc Gradle Java Toolchains.

Ví dụ các lệnh quan sát:

```bash
java -version
javac -version
mvn -version
```

Đối với Gradle:

```bash
./gradlew --version
```

Ở Windows dùng lệnh tương ứng với wrapper trong dự án, chẳng hạn `gradlew.bat --version`.

Các lệnh giúp chụp baseline, nhưng chưa chứng minh plugin compiler hoặc test process dùng đúng JVM đó.

### 4.2. JDK biên dịch mã

Ví dụ Maven:

```xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>
```

`--release 17` điều khiển mức source, target class file và API Java SE được phép sử dụng trong compile theo contract của compiler. Nó **không** tự chứng minh dependency bên thứ ba hoặc test runtime có minimum Java đúng.

Một JDK mới hơn có thể compile artifact nhắm Java 17. Nhưng nếu code vô tình phụ thuộc vào dependency đã được biên dịch cho Java 21, sản phẩm không thể chạy trên Java 17 chỉ vì thuộc tính `release` bằng 17.

### 4.3. JDK chạy test

Maven Surefire/Failsafe có thể fork JVM; Gradle có thể dùng Java toolchain cho `Test` task. Các agent như JaCoCo hoặc thư viện bytecode như Byte Buddy chạy trong chính JVM test.

Vì vậy, ngoài `mvn -version`, phải xác minh phiên bản JVM được **test launcher** khởi chạy và các JVM arguments thực tế.

### 4.4. JDK chạy production

Một CI agent có thể dùng JDK 21, trong khi Docker image chạy Java 17. Nếu compiler tạo bytecode Java 21 hoặc dependency yêu cầu Java 21, triển khai có thể thất bại với `UnsupportedClassVersionError`.

Ghi thông tin runtime production từ image/deployment manifest và phép đo khi process thực sự chạy. Không chỉ dựa vào tên tag Docker image hoặc biến `JAVA_HOME` trên máy developer.

### 4.5. JVM của codegen và các tool phụ

Annotation processors, compiler plugins, Kotlin/Groovy/Scala compilers, schema generators, API clients, bytecode enhancement tools hoặc test agents có thể có minimum JDK riêng.

Một build có thể lỗi trong processor trước khi mã ứng dụng được biên dịch, dù Java source hoàn toàn hợp lệ.

## 5. Bước 2: thu thập dependency graph và version thực được chọn

### 5.1. Maven: POM khai báo không phải luôn là kết quả cuối

Version có thể đến từ:

- `dependencies` ở module.
- `dependencyManagement` và imported BOM.
- Parent POM.
- Dependency transitive.
- Profile hoặc properties.
- Plugin dependency và plugin management.

Các lệnh hữu ích:

```bash
mvn dependency:tree
mvn dependency:tree -Dscope=test
mvn help:effective-pom
```

Hãy đọc **effective POM** để biết cấu hình đã kế thừa và đọc dependency tree để xác định version thực sự được giải quyết.

Maven thường áp dụng quy tắc mediation như nearest definition khi có nhiều đường đến các phiên bản khác nhau, cùng các quy tắc dependency management liên quan. Do đó, việc có một phiên bản trong transitive POM chưa có nghĩa đó là version thực sẽ hiện diện.

### 5.2. Gradle: configuration và variant matter

Ví dụ:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight \
  --dependency example-library \
  --configuration runtimeClasspath
```

Một module có thể resolve các dependency khác nhau giữa compile, runtime và test. `dependencyInsight` giúp giải thích lý do Gradle chọn một version trong configuration cụ thể.

Các project dùng version catalog, constraints, platforms, enforced platforms hoặc dependency locking cần kiểm tra thêm những nơi đó. Một version xuất hiện ở `libs.versions.toml` chưa đủ chứng minh mọi configuration đã chọn đúng version kỳ vọng.

### 5.3. Kiểm kê plugin riêng với application dependencies

Cần có hai danh sách:

**Application dependencies:** framework, database driver, JSON library, logging, HTTP client, messaging, security...

**Build/test plugins and tools:** compiler plugin, Surefire/Failsafe, JaCoCo, Maven Shade, Gradle plugins, annotation processors, code generators, static analysis, native-image toolchain...

Lỗi thường gặp là nâng thư viện runtime xong mới phát hiện Maven plugin không hiểu class-file version của JDK đích. Việc tách danh sách cho phép xử lý toolchain prerequisites từ sớm.

### 5.4. Chụp trước/sau có thể so sánh

Bản baseline nên lưu:

- Version trực tiếp và bắc cầu của dependency quan trọng.
- Origin của version (parent/BOM/platform/override).
- Test-only và runtime-only dependencies.
- Plugin version và custom JVM arguments.
- Checksums/lockfiles khi dự án có áp dụng.
- Version framework/application server.
- Các dependency bị duplicate hoặc có nhiều bản `.jar` trong deployment.

Khi so sánh, tập trung vào **những version thay đổi ngoài chủ đích**. Nâng một BOM có thể làm dịch chuyển hàng chục dependency, kể cả những thành phần mà source dự án không import trực tiếp.

## 6. Bước 3: tạo ma trận tương thích có bằng chứng

### 6.1. Một hàng cho mỗi thành phần cần nâng

| Thành phần | Hiện tại | Mục tiêu | Minimum JDK / hỗ trợ | Bị chặn bởi | Bằng chứng xác minh |
| --- | --- | --- | --- | --- | --- |
| JDK runtime | JDK nguồn | JDK đích | Mức yêu cầu của sản phẩm | Container, native library | Startup và integration tests |
| Gradle/Maven | Bản nguồn | Bản được chọn | Có chạy được trên JDK đích? | JVM chạy build | Version log + build |
| Compiler plugin | Bản nguồn | Bản hỗ trợ target | Hỗ trợ `--release`/class file? | Build tool/JDK compiler | Compile + inspect bytecode |
| JUnit/engine | Bản nguồn | Dòng tương thích | Test JVM minimum | Surefire/Gradle Test | Test discovery + report |
| Mockito/Byte Buddy | Bản nguồn | Dòng hỗ trợ JDK đích | Class-file parser/agent support | Test JVM | Mock/instrumentation tests |
| JaCoCo | Bản nguồn | Dòng hỗ trợ bytecode | Class-file version | Test plugin/JVM | Coverage report |
| Framework BOM | Bản nguồn | Dòng đích | Java baseline + extension compatibility | Build tool, JDK | Dependency graph + startup |
| Persistence/HTTP libs | Bản nguồn | Dòng đích | Framework/API/driver requirements | BOM, runtime | Integration/contract tests |
| Packaging/deploy | Bản nguồn | Bản đích | Jar/module/image support | Toolchain/JDK | Smoke test artifact |

Điền version thật từ tài liệu đúng phiên bản của nhà cung cấp và kết quả đo của dự án. Không dùng một nhãn “latest” làm trạng thái mục tiêu vì nội dung nhãn đó có thể đổi giữa các lần build.

### 6.2. Phân biệt minimum, supported và tested

Ba khái niệm khác nhau:

- **Minimum JDK:** phiên bản thấp nhất mà một thư viện công bố hoặc class file có thể chạy.
- **Supported JDK:** tập phiên bản được nhà cung cấp cam kết hoặc mô tả hỗ trợ.
- **Tested JDK:** tập phiên bản mà đội dự án đã chạy kiểm thử với artifact của mình.

Một dependency có minimum Java 11 không đồng nghĩa vendor cam kết nó hoạt động trên mọi JDK tương lai. Tương tự, mã chạy được trên JDK 21 trong một smoke test chưa đủ để kết luận đầy đủ support.

### 6.3. Phân loại ràng buộc cứng và mềm

**Ràng buộc cứng** cần được đáp ứng trước chặng phụ thuộc:

- Tool không chạy được trên JVM đang chọn.
- Framework yêu cầu JDK tối thiểu cao hơn runtime hiện tại.
- Plugin không hỗ trợ class-file version cần compile/inspect.
- API `javax.*`/`jakarta.*` hoặc module system không tương thích.
- Runtime không có dependency bắt buộc.

**Ràng buộc mềm** cần quản trị nhưng có thể cho phép chạy tạm với rủi ro rõ:

- Warning deprecated API.
- Plugin cũ nhưng chưa gây lỗi trong phạm vi đã thử; cần kiểm tra support policy.
- Performance giảm nhẹ trong ngưỡng chấp nhận.
- Extension chưa có chứng nhận vendor nhưng đã qua bộ test đại diện.

Không biến tất cả cảnh báo thành lỗi chặn nếu chưa xác định chính sách; cũng không bỏ qua ràng buộc cứng chỉ vì build đang tạm xanh.

## 7. Bước 4: xây dựng thứ tự nâng cấp theo đồ thị có hướng

### 7.1. Xác định nút và cạnh

Ví dụ kế hoạch:

```text
Nút A: Nâng Gradle wrapper để chạy được trên JDK đích
Nút B: Nâng compiler/test/coverage plugins
Nút C: Thiết lập JDK toolchain đích
Nút D: Nâng framework platform/BOM
Nút E: Nâng thư viện mở rộng theo BOM
Nút F: Sửa source + configuration
Nút G: Chạy integration/contract test
Nút H: Đổi deployment runtime
```

Một số cạnh có thể là:

```text
A -> B
A -> C
B -> G
C -> D
D -> E
D -> F
E -> G
F -> G
G -> H
```

Nếu trong dự án thực tế framework mới chỉ build được sau khi nâng JDK, thêm cạnh `C -> D`. Nếu migration guide yêu cầu một bước chuyển API trước khi đổi BOM, cần biểu diễn dependency đó thay vì áp dụng máy móc sơ đồ.

### 7.2. Topological ordering

Với đồ thị phụ thuộc **không có chu trình**, có thể dùng cách sắp xếp topo để chọn một thứ tự hợp lệ: ở mỗi bước, ưu tiên những nút mà tất cả prerequisites đã hoàn thành.

```text
Sẵn sàng: A
Làm A
Sẵn sàng: B, C
Làm B và C (có thể là hai nhánh độc lập)
Sẵn sàng: D
Làm D
Sẵn sàng: E, F
Làm E và F
Sẵn sàng: G
Làm G
Sẵn sàng: H
Làm H
```

Điều này **không** có nghĩa phải commit tất cả thành một thao tác lớn. Có thể chia PR/CI gate theo từng “wave”, ghi baseline và kết quả của từng wave.

### 7.3. Nếu đồ thị có chu trình

Ví dụ:

```text
Framework mới cần JDK mới
        ^
        |
Build plugin mới cần framework mới
        ^
        |
Build tool mới cần JDK mới
```

Khi có chu trình dependency thực sự, sắp xếp topo không còn tồn tại. Cần tìm cách **phá chu trình**:

- Tìm phiên bản trung gian hỗ trợ cả framework cũ và mới.
- Tách mã nguồn/migration tool thành task chạy độc lập với build chính.
- Nâng build tool trên JDK cũ trước, rồi nâng JDK.
- Tách một module chung hoặc thư viện làm adapter có contract ổn định.
- Chạy một bước code transformation có kiểm soát trước khi đổi runtime.
- Nhờ vendor xác nhận đường nâng cấp hoặc chọn lại version đích.

Không cưỡng ép bằng cách dùng tổ hợp version chưa được hỗ trợ rồi gọi nó là bước đã được xác minh.

### 7.4. Giữ “đường kiểm chứng” cho mỗi wave

Mỗi wave nên có:

1. Đầu vào phiên bản cụ thể.
2. Danh sách dependency thay đổi.
3. Lý do thay đổi và các prerequisite đã đáp ứng.
4. Phép build/test phù hợp.
5. Tiêu chí pass/fail.
6. Cách rollback về trạng thái trước wave.
7. Người phụ trách.

Nếu một wave thay quá nhiều version độc lập, giảm phạm vi để lỗi còn có thể truy nguyên.

## 8. Thứ tự thực tế giữa build tool, plugin và JDK

### 8.1. Nâng build tool trước khi đổi JVM chạy build khi cần

Ví dụ một Gradle wrapper cũ không thể chạy trên JDK mới. Thứ tự hợp lý là:

```text
JDK hiện tại + wrapper cũ
          |
          v
Nâng wrapper tới phiên bản hỗ trợ cả trạng thái hiện tại và trạng thái đích
          |
          v
Build được với JDK hiện tại
          |
          v
Đổi JDK chạy Gradle / toolchain và test lại
```

Nên dùng Gradle Wrapper của dự án để CI và developer cùng sử dụng phiên bản thống nhất. Không đặt hy vọng vào một Gradle được cài sẵn khác nhau trên mỗi máy.

Với Maven, cần kiểm tra Java baseline của Maven distribution cùng Maven plugins. Nâng Maven launcher chưa đảm bảo mọi plugin đều đã hỗ trợ JDK mới.

### 8.2. Nâng plugin hiểu class-file format

Các plugin có thể đọc hoặc biến đổi bytecode, chẳng hạn:

- Maven Compiler Plugin / Gradle Java plugin và compiler toolchain.
- JaCoCo, code coverage, instrumentation.
- Byte Buddy, ASM, mocking library.
- Maven Shade/Gradle Shadow, bytecode relocation.
- Obfuscator, scanner, bytecode analyzer.
- Kotlin/Groovy/Scala compiler và plugin tương ứng.

Nếu một công cụ chỉ hỗ trợ class file đến Java 17 nhưng JDK mới tạo Java 21 class files, plugin có thể thất bại khi scan class dù `javac` chạy thành công.

Do đó, quyết định phiên bản plugin dựa trên **class-file version nó phải xử lý**, không chỉ minimum JDK của plugin.

### 8.3. Nâng test infrastructure trước khi tin kết quả test

Một thứ tự có ý nghĩa:

```text
Test runner/plugin có hỗ trợ JDK đích
          |
          v
JUnit Platform và đúng test engine
          |
          v
Mocking/coverage agents có thể chạy trên JDK đích
          |
          v
Unit/integration tests thực sự được khám phá
          |
          v
So sánh số test và hành vi trước/sau migration
```

Điều nguy hiểm là `BUILD SUCCESS` nhưng `Tests run: 0` sau khi đổi JUnit provider hoặc include patterns. Chỉ khi đã có engine phù hợp và report xác nhận số bài test được chạy thì test mới có giá trị làm quality gate cho những wave sau.

### 8.4. Không nâng toolchain vô điều kiện

Có những plugin build hoặc framework quá cũ chỉ chạy được trên JDK nguồn. Nếu không thể nâng tất cả cùng lúc, có thể dùng:

- JDK chạy build tool khác JDK dùng để compile qua toolchain.
- Một nhánh build trung gian.
- Phiên bản plugin chuyển tiếp hỗ trợ cả hai.
- Chuyển đổi source/config trước khi nâng runtime.

Tuy nhiên, phải tuân thủ khả năng thực tế của Maven/Gradle/plugin. Không giả định toolchain giải quyết được một plugin vốn tự chạy trong JVM của build tool và gọi JDK internals.

## 9. BOM, platform và việc nâng dependency theo nhóm

### 9.1. BOM là “đơn vị tương thích” khi framework quản lý phiên bản

Nhiều framework phát hành một BOM hoặc platform mang bộ phiên bản đã được xác định để cùng làm việc. Trong Maven, một BOM có thể được import vào `dependencyManagement`; trong Gradle, có thể dùng `platform(...)` hoặc cơ chế plugin/framework tương ứng.

Ví dụ Maven với tọa độ giả định:

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.example.platform</groupId>
      <artifactId>example-bom</artifactId>
      <version>3.0.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>com.example.platform</groupId>
    <artifactId>example-web-starter</artifactId>
  </dependency>
</dependencies>
```

Ví dụ chỉ minh họa cơ chế BOM, không đại diện một artifact công bố thực tế.

BOM giúp kiểm soát version của các dependency thuộc phạm vi nó quản lý. Nhưng nó **không bảo đảm** mọi plugin Maven, mọi thư viện bên thứ ba và mọi runtime container cũng được BOM quản lý.

### 9.2. Gradle platform và dependency locking

Ví dụ:

```groovy
dependencies {
    implementation platform('com.example.platform:example-bom:3.0.0')
    implementation 'com.example.platform:example-web-starter'
}
```

Với một dự án thật, kiểm tra version catalog, constraints, dependency locking và các override. Một dependency có thể được chọn bởi nhiều ràng buộc; kết quả được resolve mới là thông tin quan trọng.

Khi nâng BOM, có thể cần cập nhật lockfiles theo quy trình được kiểm soát. Không xóa toàn bộ lockfile để ép build “chạy qua” nếu chưa đối chiếu version thay đổi.

### 9.3. Tại sao không nâng từng JAR thuộc framework một cách tùy ý?

Một nhóm module framework có thể chia sẻ API nội bộ hoặc extension points chỉ tương thích trong một dải version. Nếu core ở major mới nhưng starter hoặc module security vẫn ở major cũ, code có thể compile nhưng runtime lỗi:

```text
java.lang.NoSuchMethodError
java.lang.NoClassDefFoundError
java.lang.IncompatibleClassChangeError
```

Do đó, với framework có platform/BOM chính thức, **nâng nhóm dependency theo tổ hợp mà framework hướng dẫn**, trừ khi có lý do và bằng chứng để override.

### 9.4. Dependency được quản lý và dependency không được quản lý

Mỗi lần nâng BOM, phân nhóm:

1. Component do BOM quản lý và dự kiến nâng cùng.
2. Component có override riêng vì yêu cầu bảo mật hoặc tương thích.
3. Component nằm ngoài BOM, phải tự kiểm tra compatibility.
4. Build plugin không thuộc dependency management của BOM.
5. Runtime/library do application server cung cấp, không nằm trong artifact.
6. Native library, agent và tool được triển khai ngoài Java dependency graph.

Một BOM mới không tự nâng ứng dụng server đang chạy trên máy, cũng không tự sửa custom class loader hoặc JDK container image.

## 10. Code generation và annotation processing nên nâng ở đâu?

### 10.1. Processor phải hiểu API và ngôn ngữ hiện tại

Một số dự án dùng:

- Lombok hoặc annotation processor tạo boilerplate.
- MapStruct hoặc code mapper.
- JPA metamodel generator.
- Query code generation.
- OpenAPI/gRPC/Protobuf generators.
- Kotlin KAPT/KSP hoặc tool tương đương.
- Framework AOT và build-time augmentation.

Các công cụ này có thể phụ thuộc vào compiler internals, AST, reflection hoặc API annotation của một framework cụ thể. Khi đổi JDK/framework, chúng có thể cần nâng trước khi mã ứng dụng compile được.

### 10.2. Tách generated source khỏi source thủ công

Một pipeline điển hình:

```text
JDK + build tool + annotation processor
                 |
                 v
          Generated source
                 |
                 v
          Compile ứng dụng
                 |
                 v
          Package/run/test
```

Nếu generated code còn import package cũ `javax.*` trong khi framework đích yêu cầu `jakarta.*`, sửa import của source thủ công sẽ không đủ. Cần nâng generator/template hoặc thay cấu hình của generator trước.

Không sửa bằng tay file generated mỗi lần build; thay đổi phải đến từ **nguồn sinh mã và generator version**.

### 10.3. Kiểm tra generated artifacts có còn phù hợp không

Sau khi nâng công cụ, cần xác minh:

- Generated source khớp API framework đích.
- Annotation và nullability semantics đúng.
- Compiler target/class-file level phù hợp.
- Không xuất hiện duplicate generated class.
- Source generated được đặt trên đúng compile source set.
- Kết quả không thay đổi ngầm schema/API contract.
- Runtime không còn cần processor mà trước đây vô tình bị đóng gói như dependency production.

Khi một generator tạo schema hoặc database migration, cần có cơ chế review riêng vì thay đổi có thể ảnh hưởng dữ liệu.

## 11. Jakarta, JPMS và các chặng nâng framework

### 11.1. Java baseline của framework quyết định đường đi

Ví dụ nhiều dòng framework mới tăng minimum JDK. Nếu framework đích yêu cầu Java 17, không thể triển khai nó trên Java 11 dù compiler trên developer laptop chạy bằng JDK 21.

Cần đối chiếu:

- Framework core.
- Servlet/application server.
- ORM/JPA provider.
- Security integration.
- Bean Validation và serialization.
- Message broker client.
- Monitoring/test libraries.

Không đủ để kiểm tra một dòng “supports Java 17” trong tài liệu core rồi kết luận mọi extension cũng tương thích.

### 11.2. Namespace `javax` → `jakarta`

Một số thế hệ Jakarta EE và framework liên quan đổi nhiều API từ `javax.*` sang `jakarta.*`.

Ví dụ:

```java
// API Java EE cũ trong một số hệ sinh thái
import javax.persistence.Entity;
import javax.servlet.http.HttpServletRequest;

// API Jakarta tương ứng trong dòng mới
import jakarta.persistence.Entity;
import jakarta.servlet.http.HttpServletRequest;
```

Đây là một thay đổi source/API ecosystem, không đơn thuần là nâng JDK. Thứ tự nâng phải đảm bảo framework, servlet container, ORM, validation provider và dependency bên thứ ba cùng thuộc tổ hợp hỗ trợ namespace phù hợp.

**Không thay toàn bộ `javax.*` thành `jakarta.*`.** Những API thuộc Java SE như `javax.sql.DataSource` hoặc `javax.crypto` vẫn là `javax.*`.

### 11.3. JPMS và reflection

Khi chuyển sang Java 9+ hoặc đưa JAR lên module path, named modules có thể siết `exports`/`opens`. Một thư viện reflection cũ có thể báo `InaccessibleObjectException` hoặc `IllegalAccessError`.

Không nên thêm `--add-opens` bừa bãi trước khi thử nâng framework. Nếu cần workaround, ghi rõ:

- JDK/source module và package.
- Target named module hoặc `ALL-UNNAMED`.
- Component gây lỗi.
- JVM cần flag (build/test/app).
- Version được hỗ trợ để loại bỏ workaround.

Nâng một dependency để bỏ việc truy cập API nội bộ có thể là bước tiên quyết của việc nâng JDK production.

## 12. Tách các scope phụ thuộc khi đưa lên JDK mới

### 12.1. Compile-time khác runtime

Một thư viện chỉ được cần để biên dịch, ví dụ annotation API hoặc processor, không nhất thiết phải có mặt ở runtime. Ngược lại, JDBC driver hoặc JUnit engine có thể cần ở runtime nhưng mã source không import trực tiếp.

Nếu scope sai, có thể gặp:

- Compile thành công nhưng runtime thiếu class.
- Runtime chứa hai implementation cùng service.
- Processor bị đưa nhầm vào production artifact.
- Test classpath có bản dependency khác runtime classpath.
- Library “provided” bởi server bị đóng gói thêm và xung đột class loader.

### 12.2. Maven scopes

Maven thường có `compile`, `provided`, `runtime`, `test` và các phạm vi khác với ý nghĩa khác nhau. Khi migration, cần đối chiếu scope với cách đóng gói thực tế.

Ví dụ servlet API do application server cung cấp có thể được khai báo theo scope phù hợp với server, nhưng nếu chạy embedded container thì packaging/dependency lại khác. Đừng áp dụng một quy tắc `provided` cho mọi hệ thống web.

### 12.3. Gradle configurations

Gradle phân biệt `implementation`, `api` (với `java-library`), `compileOnly`, `runtimeOnly`, `testImplementation` và `testRuntimeOnly`.

Nếu JUnit Jupiter API hiện diện trong `testImplementation` nhưng engine không có ở `testRuntimeOnly` hoặc dependency tương ứng, test có thể compile nhưng launcher không thực thi được.

### 12.4. Dependency “ở ngoài build”

Một số runtime dependencies không thể hiện trong application POM:

- JAR do application server cung cấp.
- Java agents hoặc monitoring libraries.
- Plugin JAR đặt trong volume riêng.
- JDBC driver được cài trực tiếp vào server.
- Native libraries.
- JDK modules hoặc command-line flags.
- Sidecar/container image cung cấp tài nguyên.

Chúng phải có trong ma trận nâng cấp dù không xuất hiện trong dependency tree của ứng dụng.

## 13. Quy trình nâng thư viện không phá tương thích ngoài ý muốn

### 13.1. Nâng dependency theo nhóm nhỏ

Một cách phân chia wave:

1. Build/test tooling prerequisites.
2. Dependency bảo mật hoặc thay thế thư viện không còn hỗ trợ, trong phạm vi tương thích hiện tại.
3. Framework BOM/platform đích cùng core dependencies.
4. Extensions: security, ORM, web, messaging, serialization.
5. Application source/config/API changes.
6. Packaging, deployment image và production runtime.
7. Dọn dependency/flags tạm thời sau khi ổn định.

Thứ tự có thể thay đổi tùy dependency graph, nhưng nên giữ **các phần có quan hệ rất chặt** trong cùng một wave kiểm chứng để tránh tổ hợp chưa được hỗ trợ.

### 13.2. SemVer không phải bảo đảm tuyệt đối

Semantic Versioning có thể giúp dự đoán phạm vi thay đổi, nhưng một dependency tuân SemVer không loại bỏ mọi rủi ro. Một patch có thể sửa lỗi làm behavior khác trước; một thư viện không tuân SemVer chặt có thể đổi API trong minor release.

Vì vậy mỗi lần nâng version cần đọc:

- Release notes.
- Migration guide nếu có.
- Minimum JDK.
- Deprecated/removed APIs.
- Security advisories.
- Compatibility của dependency bắc cầu.
- Known issues và behavioral changes.

Đừng dùng nguyên tắc “minor luôn an toàn” để bỏ qua test.

### 13.3. Source, binary và behavioral compatibility

| Loại | Câu hỏi | Cách xác minh |
| --- | --- | --- |
| Source | Code cũ có compile với API mới không? | Recompile từng module/client. |
| Binary | JAR client cũ có liên kết với library mới không? | Binary compatibility checks và chạy client đã compile. |
| Behavior | Kết quả, exception, protocol, transaction có giữ contract không? | Regression/integration/contract tests. |
| Operational | Startup, resource use, health, monitoring có còn đúng không? | Staging/canary/observability. |
| Data | Schema, serialization và dữ liệu lịch sử có tương thích không? | Migration test/backup/restore validation. |

Một dependency upgrade có thể source-compatible nhưng behavior-incompatible. Chỉ chạy `mvn compile` không đủ để đánh giá toàn bộ.

### 13.4. Classpath conflicts và version convergence

Đặc biệt chú ý khi nhiều module kéo cùng thư viện ở các version khác nhau. Với Maven/Gradle, cần xác minh version được resolve và nguyên nhân version ấy được chọn.

Có thể cân nhắc enforcement/convergence rules hoặc dependency constraints phù hợp. Nhưng việc ép mọi nhóm phụ thuộc về **một version bất kỳ** không bảo đảm tương thích nếu một thư viện thực sự cần một API cũ đã bị xóa.

Khi không thể thống nhất, cân nhắc nâng upstream dependency, thay thư viện, classloader isolation hoặc shading có kiểm soát. Shading là giải pháp tốn công bảo trì vì reflection, service metadata và binary compatibility có thể bị ảnh hưởng.

## 14. Test infrastructure như một prerequisite của mọi wave

### 14.1. Không thể tin chất lượng wave nếu test runner đã lỗi

Khi nâng JDK, bộ test có thể lỗi hoặc âm thầm không chạy vì:

- Surefire/Failsafe cũ không nhận đúng test engine.
- Jupiter API có mặt nhưng thiếu Jupiter engine.
- Vintage không được cấu hình nên JUnit 4 tests biến mất.
- Mockito/Byte Buddy chưa hỗ trợ class-file format.
- JaCoCo agent không instrument được class mới.
- Testcontainers/framework integration chưa tương thích môi trường.
- JVM args cho test fork khác runtime dự kiến.

Vì vậy cần nâng **test toolchain đủ để giữ baseline test coverage** trước khi dùng kết quả test đánh giá thay đổi framework/dependency khác.

### 14.2. Tách Surefire và Failsafe trong Maven

Maven Surefire thường chạy unit test trong pha `test`. Maven Failsafe được dùng cho integration tests với goals `integration-test` và `verify` khi cấu hình tương ứng.

Ví dụ:

```bash
mvn test
mvn verify
```

`mvn test` không có nghĩa mọi `*IT` đã chạy. `mvn verify` chỉ thực sự kiểm chứng integration tests khi Failsafe được bind và source/test naming tương ứng đã được cấu hình đúng.

Khi migration, so sánh cả báo cáo unit và integration test. Một build thành công nhưng có `Tests run: 0` là một tín hiệu cần điều tra, không phải thành công.

### 14.3. Kiểm soát test coverage

Nếu JaCoCo hoặc instrumentation agent không hoạt động trên JDK đích, coverage report có thể thiếu/0 hoặc job có thể lỗi trước khi test bắt đầu.

Không vội hạ coverage threshold hay tắt agent. Kiểm tra Java compatibility của agent và cách kết hợp `argLine`/JVM arguments của test launcher.

### 14.4. Ma trận kiểm chứng trước/sau

| Stage | Cần chứng minh |
| --- | --- |
| Compile | Correct JDK/toolchain; source và dependency tương thích. |
| Unit tests | Test engine phát hiện đúng test; số lượng không giảm ngoài kế hoạch. |
| Integration tests | DB, messaging, web, serialization và framework extension hoạt động. |
| Contract tests | API/wire format không phá consumer. |
| Package | JAR/WAR/native image chứa đúng classes/resources/services. |
| Runtime smoke | Artifact khởi động bằng JDK/container đích. |
| Load/security tests | Latency, throughput, authentication/authorization đáp ứng policy. |

## 15. Một ví dụ có chặng: nâng hệ thống Java 11 sang Java 17

### 15.1. Bối cảnh giả định

Giả sử một dịch vụ có các thành phần:

```text
Ứng dụng: inventory-service
JDK nguồn: 11
Mục tiêu: JDK 17
Build: Gradle wrapper cũ
Framework: dòng A
Security extension: dòng S
ORM: dòng O
Tests: JUnit 4 + Jupiter, Mockito, JaCoCo
Deploy: Docker container
```

Các tên A/S/O chỉ là ký hiệu minh họa, không đại diện version thật.

### 15.2. Vấn đề phát hiện trong khảo sát

- Gradle wrapper hiện tại không hỗ trợ chạy trên JDK 17.
- Một plugin code generation dùng API JDK/compiler cũ.
- Coverage agent chưa hỗ trợ bytecode/JVM đích.
- Framework dòng B mới hỗ trợ JDK 17 và có thay đổi cấu hình bảo mật.
- ORM extension phải nâng theo framework B.
- Container image production vẫn là Java 11.
- Một số unit tests JUnit 4 chỉ chạy nhờ Vintage/runner cũ.

### 15.3. Đồ thị phụ thuộc migration

```text
A. Nâng wrapper, giữ JDK 11
       |
       +--> B. Nâng codegen/bytecode tooling
       |
       +--> C. Nâng test runner/engine/JaCoCo
                    |
                    v
D. Chuẩn bị JDK 17 toolchain và kiểm thử baseline
                    |
                    v
E. Nâng framework BOM A -> B
       |
       +--> F. Nâng security/ORM extensions tương ứng
                    |
                    v
G. Sửa source và cấu hình theo migration guide
                    |
                    v
H. Unit + integration + contract tests trên JDK 17
                    |
                    v
I. Build artifact + container image JDK 17
                    |
                    v
J. Staging/canary + metrics + quyết định rollout
```

Đây là một đường đi có thể hợp lý nếu các version trung gian được nhà cung cấp hỗ trợ. Không dùng nó thay cho compatibility matrix thật. Nếu framework A không hỗ trợ chạy trên JDK 17, bước D cần được thay bằng bước chuẩn bị toolchain/compile riêng hoặc thực hiện đồng thời với bước E trên một nhánh migration được kiểm thử.

### 15.4. Kế hoạch từng wave

| Wave | Thay đổi | Gate trước khi tiếp tục |
| --- | --- | --- |
| 0 | Chụp baseline JDK, dependency graph, test reports | Có thể lặp lại kết quả baseline. |
| 1 | Nâng wrapper và plugin ở JDK 11 | Build và tests hiện tại vẫn chạy. |
| 2 | Chuẩn bị JDK 17 và test tools | Test runner thực sự khám phá đúng bộ test. |
| 3 | Nâng framework BOM + extensions bắt buộc | Compile, startup, security/ORM integration tests. |
| 4 | Sửa source/API/config | Contract/regression tests, không còn old configs bị bỏ qua. |
| 5 | Đổi container runtime và đóng gói | JDK trong image đúng, artifact chạy được. |
| 6 | Staging và canary | Không vượt ngưỡng lỗi/latency, có rollback. |

### 15.5. Kết luận của ví dụ

Nếu nâng image Java 17 trước khi thay wrapper, pipeline có thể không chạy. Nếu nâng framework trước khi JDK đủ version, runtime có thể lỗi class file. Nếu nâng tất cả cùng lúc, một vấn đề JUnit engine có thể khiến test “xanh giả” và che mất regression ở framework.

Trình tự theo prerequisite giúp tách các loại lỗi và tạo bằng chứng ở mỗi wave.

## 16. Maven: ví dụ chuẩn hóa plugin và Java release

Một cấu hình Maven minh họa mức Java nguồn/đích và khai báo plugin có phiên bản:

```xml
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>inventory-service</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-failsafe-plugin</artifactId>
        <version>3.5.2</version>
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
</project>
```

Các version chỉ là ví dụ để minh họa **việc khóa plugin**; trước khi dùng trong dự án thật phải kiểm tra support matrix với JDK/Maven và framework hiện tại.

Cấu hình trên không tự khai báo JUnit engine, test framework dependencies, ORM và runtime dependencies. Muốn `mvn verify` có giá trị, cần đủ test dependencies, test sources và môi trường integration test thực tế.

### 16.1. Maven Compiler Plugin không thay Maven runtime

`maven.compiler.release` chỉ điều chỉnh cách compiler biên dịch theo Java release đích. Nó không thay phiên bản Java chạy Maven. Nếu một Maven plugin cần Java 17 nhưng Maven đang chạy trên Java 11, plugin có thể không được nạp.

### 16.2. Parent và pluginManagement

Trong multi-module Maven project, có thể khai báo plugin versions trong parent `pluginManagement` rồi để module dùng plugin theo cấu hình phù hợp. Tuy nhiên một entry trong `pluginManagement` không tự kích hoạt mọi plugin goal cho mọi module.

Khi audit, đọc effective POM của từng module quan trọng để xác định plugin thực thi và cấu hình đã kế thừa.

### 16.3. Multi-module dependency ordering

Các Maven modules có thể phụ thuộc nhau:

```text
shared-api -> data-access -> order-service
```

Công cụ reactor có thể sắp xếp thứ tự build theo dependency nội bộ. Nhưng **thứ tự build** không tự quyết định thứ tự nâng major framework hoặc JDK; cần riêng một migration plan cho version và contract của các modules.

Trong một mono-repo, nên xây dựng khả năng release/consume ổn định cho shared API trước khi module phụ thuộc chuyển sang API mới.

## 17. Gradle: wrapper, toolchain và dependency constraints

### 17.1. Wrapper và Java toolchain là hai trục khác nhau

Ví dụ Gradle Groovy DSL:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Java toolchain cho phép một số task Java sử dụng JDK được chọn, nhưng không có nghĩa mọi Gradle plugin sẽ chạy trên JDK toolchain. Gradle daemon/build logic vẫn có JVM chạy Gradle và cần được hỗ trợ bởi wrapper/plugin.

### 17.2. Dependency constraint

Ví dụ minh họa:

```groovy
dependencies {
    implementation 'com.example:client-api:2.0.0'

    constraints {
        implementation('com.example:shared-codec:3.0.0') {
            because 'Version duoc kiem tra voi client-api 2.0.0'
        }
    }
}
```

Constraint thể hiện yêu cầu version trong dependency resolution, nhưng không tự chứng minh binary compatibility. Khi thêm constraint, kiểm tra `dependencyInsight` và chạy test của các consumer liên quan.

### 17.3. Dependency locking

Nếu dự án dùng dependency locking, việc nâng BOM hoặc plugin có thể đòi cập nhật lock state. Nên:

1. Chụp lockfile hiện tại.
2. Thực hiện một wave nâng cấp.
3. Tạo/cập nhật lock state theo quy trình dự án.
4. Review diff của version được thay.
5. Chạy tests.
6. Commit lockfiles cùng change set có giải thích.

Đừng xóa lockfiles chỉ để giải quyết resolution error mà chưa biết dependency nào sẽ bị đổi.

### 17.4. Toolchain trong CI

CI phải có JDK phù hợp hoặc cơ chế provision được kiểm soát. Nếu một task yêu cầu Java 17 toolchain nhưng CI không có JDK phù hợp, build có thể lỗi ngay trước compilation.

Dùng wrapper và cấu hình version/toolchain rõ ràng giúp tránh “máy developer chạy, CI thất bại” do sử dụng tool khác nhau.

## 18. Dependency graph giữa các module và dịch vụ

### 18.1. Shared library trước, consumers sau

Nếu `shared-api` được nhiều dịch vụ dùng, thay public API của nó có thể kéo theo thay đổi đồng loạt.

Một chiến lược an toàn:

1. Thêm API mới theo cách giữ backward compatibility nếu có thể.
2. Phát hành shared library với adapter hoặc API song song.
3. Nâng từng consumer theo kế hoạch.
4. Theo dõi consumer còn dùng API cũ.
5. Chỉ loại API cũ khi chính sách compatibility cho phép.

Đây là thứ tự nâng **theo dependency graph của tổ chức**, không chỉ thư viện Maven của một ứng dụng.

### 18.2. Database schema và message contract

Thay ORM hoặc serializer có thể làm thay schema hoặc wire format. Trong hệ phân tán, không thể luôn nâng tất cả service đồng thời.

Nên ưu tiên pattern mở rộng trước, thu hẹp sau (*expand–migrate–contract*) khi phù hợp:

```text
Mở rộng schema/protocol tương thích
        |
        v
Triển khai producer/consumer đọc cả dạng cũ và mới nếu cần
        |
        v
Chuyển dữ liệu và traffic
        |
        v
Xác minh không còn consumer cũ
        |
        v
Loại bỏ schema/API cũ ở release phù hợp
```

Cách này bảo vệ rollout từng phần và rollback tốt hơn thay đổi phá tương thích ngay lập tức.

### 18.3. Version skew giữa các service

Ngay cả khi một service đã hoàn tất migration, service khác có thể chạy bản cũ. Phải test các tổ hợp phiên bản **mới–cũ** trong khoảng rollout thực tế, đặc biệt với authentication, JSON payload, Kafka/queue schemas hoặc database shared state.

## 19. Xử lý blocker theo nhóm nguyên nhân

| Triệu chứng | Lớp nguyên nhân | Hướng chẩn đoán |
| --- | --- | --- |
| Gradle/Maven không khởi động trên JDK mới | Build tool JVM compatibility | Xem wrapper/distribution support và version plugin. |
| `invalid target release` | Compiler JDK không hỗ trợ `--release`/target | Kiểm tra `javac -version` và toolchain compiler. |
| `UnsupportedClassVersionError` | JVM chạy thấp hơn bytecode được nạp | Kiểm tra class-file version và JDK test/runtime. |
| `NoSuchMethodError` | Binary API mismatch hoặc dependency mediation | Xác định JAR thực được nạp và dependency tree. |
| `NoClassDefFoundError` | Class thiếu hoặc dependency/runtime path sai | Kiểm tra scope, packaging, class loader và module path. |
| `InaccessibleObjectException` | Reflection bị JPMS chặn | Nâng library/framework; xử lý `opens` khi cần. |
| `ServiceConfigurationError` | SPI/provider metadata không đúng | Kiểm tra `META-INF/services`, shading và provider class. |
| Build xanh nhưng `Tests run: 0` | Test engine/provider/include filters | Kiểm tra Surefire/Failsafe/JUnit Platform và report. |
| JaCoCo/Mockito fail trên JDK mới | Bytecode/agent chưa hỗ trợ | Nâng đúng JaCoCo/Byte Buddy/ASM/Mockito. |
| Generated source còn `javax.*` | Generator/template cũ | Nâng processor/codegen và source API đích. |
| Runtime chỉ hỏng ở production | Dependency/container/JDK lệch CI | So image, classpath, native libs và configs. |
| API output khác dù compile pass | Behavioral change của framework/dependency | Regression/contract/security/integration test. |
| Version bất ngờ trong artifact | BOM override/lockfile/transitive resolution | Effective POM, dependencyInsight, packaging inspect. |

Không xử lý lỗi bằng cách tăng một lúc tất cả phiên bản đến “mới nhất”. Cần phân loại lỗi thuộc lớp nào và sửa đúng prerequisite bị thiếu.

## 20. Quy trình phân tích khi có vòng phụ thuộc khó gỡ

### 20.1. Ví dụ một blocker

Một dự án có:

- Plugin codegen cũ không chạy trên JDK mới.
- Plugin codegen mới chỉ hỗ trợ một dòng framework mới.
- Framework mới yêu cầu source đã chuyển namespace.
- Source cũ chỉ sinh được với plugin codegen cũ.

Một cách tiếp cận khả thi là tạo chặng:

1. Giữ JDK cũ để sinh source hiện tại và lưu artifact baseline.
2. Nâng plugin/generator tới một phiên bản hỗ trợ chuyển đổi hoặc thay generator nếu không có đường tương thích.
3. Chuyển templates/source annotations theo guide.
4. Nâng framework và compiler toolchain trên branch có bản generated code mới.
5. Biên dịch và test trên JDK đích.

Nếu không có phiên bản trung gian, có thể cần tách generator thành module/tool chạy độc lập hoặc cập nhật source thủ công có kiểm soát **ở nguồn template**, không sửa output sinh ra rồi mất thay đổi ở lần build sau.

### 20.2. Khi dependency không còn được duy trì

Nếu một thư viện không hỗ trợ JDK đích và không có bản nâng cấp:

- Xem có thể thay bằng thư viện khác không.
- Viết adapter để giảm API surface và chuyển dần.
- Tách thành service/worker chạy runtime cũ trong thời hạn giới hạn, nếu chính sách bảo mật cho phép.
- Dùng class-loader isolation hoặc shading chỉ khi thực sự phù hợp.
- Loại bỏ tính năng không còn cần.

Đừng tự coi shading hay `--add-opens` là phương án bảo đảm tồn tại lâu dài; chúng không khắc phục mọi vấn đề bytecode, native, API removal hoặc bảo mật.

### 20.3. Quyết định phải có owner và deadline

Với blocker chưa xử lý được, ghi:

```text
Blocked component:
Current version:
Required target:
Blocking constraint:
Supported intermediate version:
Owner:
Mitigation / alternative:
Risk accepted by:
Review date:
Verification evidence:
```

Không để các workaround tồn tại vô thời hạn mà không có người chịu trách nhiệm.

## 21. Thiết kế quality gate cho từng wave

### 21.1. Gate kỹ thuật

Một wave có thể yêu cầu:

- Dependency resolution thành công, không còn version conflict ngoài ý muốn.
- Build tool hoạt động trên JVM đã chọn.
- Java source biên dịch với release mong muốn.
- Test suite được khám phá đủ, số lượng giảm có lý do.
- Không có lỗi bytecode agent, annotation processor và packaging.
- Artifact cuối chứa các resource và providers cần thiết.
- Runtime smoke pass trên JDK/container đích.

### 21.2. Gate nghiệp vụ

Nếu wave liên quan framework hoặc persistence:

- API contract vẫn đúng.
- Authentication/authorization không mở quyền ngoài policy.
- Database queries, transactions và schema hoạt động.
- Message serialization tương thích producer/consumer.
- Retry, timeout, idempotency đúng.
- Performance p95/p99 và resource use trong ngưỡng.
- Log/metrics/traces vẫn đáp ứng vận hành.

### 21.3. Gate bảo mật và dependency inventory

Khi cập nhật dependencies:

- Xác định những bản còn CVE chưa xử lý.
- Kiểm tra license/NOTICE.
- Cập nhật SBOM và dependency lock state.
- Không để bản dependency nguy hiểm bị embed trong shaded JAR mà scanner không nhìn thấy.
- Kiểm tra JDK/runtime image còn trong chính sách hỗ trợ.

### 21.4. Gate công bố và rollback

Trước rollout production:

- Có changelog theo wave.
- Có deployment artifact và cấu hình tương ứng.
- Có giới hạn canary/feature flag khi cần.
- Có tiêu chí rollback dựa trên số liệu.
- Có phương án với dữ liệu/schema không rollback trực tiếp.
- Có người chịu trách nhiệm quyết định chốt chặng.

## 22. Mẫu migration worksheet theo thứ tự phụ thuộc

Có thể dùng một bảng như sau:

| ID | Bước | Prerequisites | Component/version | Hành động | Bằng chứng | Trạng thái |
| --- | --- | --- | --- | --- | --- | --- |
| M-01 | Baseline | Không | JDK, framework, build | Thu thập version và reports | Log, dependency graph | Pending |
| M-02 | Nâng build wrapper | M-01 | Gradle/Maven | Chọn version hỗ trợ trạng thái nguồn và đích | Build cũ vẫn pass | Pending |
| M-03 | Nâng compiler/codegen | M-02 | Plugins/processors | Đảm bảo compile target được hỗ trợ | Compile và generated-source checks | Pending |
| M-04 | Nâng test tooling | M-02 | JUnit/agents | Cài đúng engine và tool bytecode | Test counts và coverage | Pending |
| M-05 | Chuẩn bị JDK đích | M-02,M-03,M-04 | Toolchain/runtime | Kiểm tra JDK và baseline tests | Toolchain log và smoke tests | Pending |
| M-06 | Nâng platform/BOM | M-05 hoặc prereq thực tế | Framework | Áp dụng guide, ghi version diff | Dependency graph | Pending |
| M-07 | Nâng extensions | M-06 | ORM/security/web | Chọn tổ hợp tương thích | Integration tests | Pending |
| M-08 | Sửa API/config | M-06,M-07 | Source/config | Rename/replace/migrate semantics | Compile, contract/security tests | Pending |
| M-09 | Đổi artifact/image | M-08 | Package/deploy | Build và test runtime đích | Startup/health/performance | Pending |
| M-10 | Rollout | M-09 | Production | Canary và theo dõi | Metrics, rollback proof | Pending |

Đây là mẫu **khởi tạo**, không phải lịch áp dụng cứng. Trong dự án thật, sửa prerequisites để biểu thị đúng sự phụ thuộc; ví dụ có thể cần đổi namespace trước một phần framework upgrade hoặc nâng JDK ở một chặng khác.

### 22.1. Thêm trạng thái có ý nghĩa

Các trạng thái hữu ích:

- `PENDING`: chưa bắt đầu.
- `READY`: mọi prerequisite đã đạt.
- `BLOCKED`: có ràng buộc chưa đáp ứng.
- `IN_PROGRESS`: đang thay đổi.
- `VALIDATED`: đã qua gate của wave.
- `ROLLED_BACK`: đã hoàn tác.
- `WAIVED`: chưa hoàn thành nhưng có phê duyệt và bằng chứng rủi ro.

Không tự đổi `BLOCKED` sang `VALIDATED` chỉ vì một nhánh test bị skip.

## 23. Những sai lầm thường gặp

### 23.1. Nâng mọi version cùng lúc

Khi hàng trăm dependency và plugin thay đổi trong một commit, một lỗi runtime rất khó truy nguồn. Nên nâng theo wave gắn với prerequisites và có báo cáo before/after.

### 23.2. Chỉ nâng JDK nhưng giữ tooling quá cũ

Compiler plugin, JaCoCo hoặc mocking framework có thể không hỗ trợ bytecode mới. Chọn JDK đích cần đi kèm kiểm tra toolchain.

### 23.3. Coi Maven/Gradle runtime và Java toolchain là một

JDK chạy build tool không nhất thiết là JDK biên dịch hoặc chạy test. Phải đo từng JVM trong CI và production.

### 23.4. Nâng BOM nhưng vẫn override nhiều thư viện cũ

BOM mới có thể bị vô hiệu một phần bởi version override, transitive dependency và plugin độc lập. Đọc effective POM/dependency insight mới biết version cuối.

### 23.5. Thêm `--add-opens` để chữa mọi lỗi

JPMS access chỉ là một lớp vấn đề. `UnsupportedClassVersionError`, `NoSuchMethodError`, plugin codegen lỗi hoặc `ServiceLoader` thiếu provider không được sửa bằng cách mở package bừa bãi.

### 23.6. Bỏ qua test engine

Chỉ nâng JUnit API mà không có engine/provider tương ứng có thể khiến build không chạy test. Cần đối chiếu test report, không chỉ exit code.

### 23.7. Sửa generated source thay vì generator

Lần build sau sẽ tạo lại mã cũ và mất patch. Nên nâng processor/template/extension từ nguồn.

### 23.8. Giả định SemVer hoặc release notes đủ bảo đảm behavior

Một version nhỏ có thể thay đổi mặc định hoặc vá lỗi làm output khác. Phải chạy regression và contract tests có ý nghĩa.

### 23.9. Đồng nhất dependency trong POM với runtime thật

Application server, container, plugin directory và Java agents có thể mang dependency riêng. Cần kiểm kê runtime deployed classpath, không chỉ file build.

### 23.10. Quên rollback dữ liệu và contract liên dịch vụ

Code rollback nhanh không đồng nghĩa database schema, message format hoặc serialized payload có thể quay lại ngay. Kế hoạch nâng phải tính cả consumers đang chạy bản cũ.

## 24. Checklist trước khi chốt chiến lược nâng cấp

- [ ] Đã có JDK nguồn/đích và phạm vi Java support rõ ràng.
- [ ] Đã xác nhận JVM chạy Maven/Gradle, compiler, test và production.
- [ ] Đã liệt kê build plugins, code generators, test engines, agents và dependencies.
- [ ] Đã lưu dependency tree/effective POM hoặc Gradle dependency insight/lockfiles.
- [ ] Đã tách tool dependencies khỏi runtime/test dependencies.
- [ ] Đã đối chiếu minimum/supported/tested Java cho từng component quan trọng.
- [ ] Đã xác định framework BOM/platform và những override nằm ngoài BOM.
- [ ] Đã lập migration dependency graph với ý nghĩa cạnh rõ ràng.
- [ ] Đã xác định chặng trung gian được hỗ trợ và xử lý các vòng dependency nếu có.
- [ ] Đã thiết kế wave nâng wrapper/plugins/JDK/framework/extensions/source/deploy phù hợp.
- [ ] Đã kiểm tra annotation processors, generated sources và bytecode tools.
- [ ] Đã đánh giá Jakarta, JPMS, reflection, native libraries và service metadata khi liên quan.
- [ ] Đã cấu hình test runner đúng engine; số test không giảm ngoài chủ đích.
- [ ] Đã kiểm tra source/binary/behavioral compatibility cho dependencies được nâng.
- [ ] Đã thử integration, contract, security và performance tests trên runtime đích.
- [ ] Đã kiểm tra artifact đóng gói và container/application server thực tế.
- [ ] Đã có version lock, SBOM, license và báo cáo bảo mật phù hợp.
- [ ] Đã ghi blockers, workaround, owner, deadline và bằng chứng.
- [ ] Đã định nghĩa rollout/canary/rollback và phương án với dữ liệu không tương thích ngược.
- [ ] Đã cập nhật CI, tài liệu nâng cấp và trạng thái kiểm chứng của từng wave.

## 25. Kết luận

**Nâng cấp công cụ và dependency theo thứ tự phụ thuộc** là cách biến một migration phức tạp thành chuỗi thay đổi có thể giải thích và kiểm chứng. Thay vì hỏi “nâng JDK hay framework trước?”, hãy hỏi: **trạng thái nào đang được hỗ trợ, thành phần nào là prerequisite cho trạng thái tiếp theo, và phép kiểm thử nào chứng minh chặng đó đã đạt?**

Trong Java Advance Compatibility Migration, hãy bắt đầu bằng dependency graph và compatibility matrix, nâng những công cụ cần thiết để build/test đáng tin, chọn phiên bản framework/dependency đồng bộ, rồi chuyển source, runtime và deployment theo các wave có gate rõ ràng. Khi mỗi bước có bằng chứng, blocker và đường rollback, nhóm phát triển có thể kiểm soát cả tương thích kỹ thuật lẫn rủi ro vận hành thay vì hy vọng một lần cập nhật hàng loạt sẽ thành công.
