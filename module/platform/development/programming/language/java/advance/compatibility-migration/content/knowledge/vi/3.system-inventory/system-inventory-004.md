# Thu thập cây dependency, plugin build và công cụ sinh mã

Trong một đợt Java compatibility migration, việc kiểm kê phiên bản JDK và mã nguồn mới chỉ cho biết một phần của hệ thống. Kết quả build và khả năng chạy ứng dụng còn phụ thuộc vào thư viện mà ứng dụng nạp, plugin mà Gradle hoặc Maven sử dụng, annotation processor và các công cụ tạo mã nguồn hay tài nguyên. Một dependency có thể không xuất hiện trong file khai báo trực tiếp nhưng vẫn được kéo vào qua nhiều tầng phụ thuộc. Một plugin build cũng có thể chạy trên JDK của tiến trình build, trong khi ứng dụng được biên dịch hoặc chạy trên một JDK khác.

Vì vậy, khảo sát hệ thống cần thu thập được ba nhóm thông tin liên quan nhưng độc lập: **dependency của ứng dụng**, **plugin và logic của hệ thống build**, và **công cụ sinh mã**. Mỗi nhóm phải có phiên bản, nguồn khai báo, môi trường thực thi, phạm vi ảnh hưởng và bằng chứng xác minh. Kết quả kiểm kê này là đầu vào để xác định thành phần nào hỗ trợ JDK đích, thành phần nào cần nâng cấp và những thay đổi nào có thể làm thay đổi mã nguồn hoặc artifact được phát hành.

## 1. Phân biệt ba nhóm cần khảo sát

### 1.1. Dependency của ứng dụng

Dependency ứng dụng là thư viện mà mã nguồn hoặc runtime của module cần để biên dịch, kiểm thử hay thực thi. Ví dụ gồm Spring Framework, thư viện JSON, JDBC driver, logging API, client HTTP, thư viện bảo mật và thư viện nghiệp vụ dùng chung.

Dependency có thể được khai báo trực tiếp trong `build.gradle`, `build.gradle.kts` hoặc `pom.xml`, nhưng đồ thị thực tế còn bao gồm dependency bắc cầu (transitive dependencies). Nếu ứng dụng khai báo thư viện A, A có thể kéo B và B tiếp tục kéo C. Khi đó ứng dụng có thể nạp C dù không có dòng khai báo C trong file build của module.

Không phải mọi dependency đều được dùng trong cùng một giai đoạn:

| Nhóm | Mục đích | Ví dụ cấu hình thường gặp |
|---|---|---|
| Compile/API | Cần để biên dịch mã nguồn hoặc được lộ ra qua API của module | Gradle `api`, `implementation`; Maven `compile` |
| Runtime | Cần khi chạy ứng dụng nhưng không nhất thiết có trên compile classpath | Gradle `runtimeOnly`; Maven `runtime` |
| Compile-only | Cần lúc biên dịch nhưng được cung cấp bởi môi trường hoặc thành phần khác khi chạy | Gradle `compileOnly`; Maven `provided` |
| Test | Chỉ dùng trong mã kiểm thử | Gradle `testImplementation`, `testRuntimeOnly`; Maven `test` |
| Annotation processing | Chạy trong compiler để phân tích annotation và sinh mã | Gradle `annotationProcessor`; Maven Compiler Plugin processor path |
| Build logic | Dùng để cấu hình và thực thi build, không phải thư viện runtime của ứng dụng | Gradle plugin/buildscript; Maven build plugin |

Tên configuration và scope có thể khác tùy plugin, ngôn ngữ và phiên bản build tool. Cần đọc cấu hình thực tế của dự án thay vì suy luận chỉ từ tên thư viện.

### 1.2. Plugin và logic build

Plugin build mở rộng Gradle hoặc Maven để cung cấp task, goal, quy tắc biên dịch, kiểm thử, đóng gói, phân tích mã, tạo tài liệu và phát hành artifact. Ví dụ: plugin Java, Spring Boot, Kotlin, JaCoCo, Checkstyle, SpotBugs, Sonar, plugin tạo Docker image hoặc plugin nội bộ của tổ chức.

Plugin thường chạy trong tiến trình build và có thể dùng API của Gradle/Maven, thư viện bytecode, ASM, Groovy, Kotlin hoặc API của JDK. Vì vậy, plugin có thể không tương thích với JDK chạy build dù dependency ứng dụng hoàn toàn tương thích. Plugin cũng có thể yêu cầu phiên bản Gradle/Maven tối thiểu hoặc phụ thuộc vào plugin khác.

Với Gradle, cần phân biệt ít nhất hai cơ chế khai báo:

- Plugin DSL, thường nằm trong `plugins {}` và được định danh bằng plugin id cùng version.
- Cơ chế cũ `buildscript { dependencies { classpath(...) } }`, nơi plugin hoặc thư viện build được đưa vào buildscript classpath.

Plugin DSL có thể được phân giải qua `pluginManagement.repositories` trong `settings.gradle` hoặc `settings.gradle.kts`. Plugin được áp dụng từ `buildSrc`, included build hay convention plugin nội bộ cũng cần được kiểm kê. Lệnh xem `buildEnvironment` không đại diện đầy đủ cho tất cả plugin khai báo qua Plugin DSL.

Với Maven, plugin được khai báo trong `build/plugins` hoặc `build/pluginManagement` của POM, có thể được kế thừa từ parent POM hoặc kích hoạt theo profile. Dependency của plugin có classpath riêng với dependency của ứng dụng. Không được nhầm một Maven build plugin với thư viện mà ứng dụng đóng gói khi chạy.

### 1.3. Công cụ sinh mã

Công cụ sinh mã tạo ra Java source, bytecode, resource, schema hoặc tài liệu từ annotation, schema, model hay định nghĩa API. Một số công cụ hoạt động trong compiler, một số chạy ở task/goal riêng, một số chạy trước khi compile và một số chạy trong quy trình đóng gói.

Các ví dụ thường gặp:

- **Lombok:** annotation processor tạo mã truy cập, constructor, builder và các thành phần khác từ annotation.
- **MapStruct:** annotation processor tạo implementation cho mapper interface.
- **QueryDSL hoặc công cụ metamodel:** tạo class biểu diễn entity hay truy vấn từ model và annotation.
- **OpenAPI Generator:** tạo client, server interface, model hoặc tài liệu từ OpenAPI specification.
- **Protocol Buffers / gRPC:** tạo Java class và stub từ file `.proto`.
- **Avro:** tạo Java class từ schema Avro.
- **jOOQ code generation:** tạo Java representation từ schema cơ sở dữ liệu.
- **ANTLR:** tạo lexer/parser từ grammar.
- **Các công cụ nội bộ:** tạo source, resource, registry, metadata hoặc cấu hình từ YAML/JSON/schema riêng.

Một công cụ có thể vừa là plugin build vừa là generator. Ví dụ, OpenAPI Generator có thể được tích hợp dưới dạng Gradle plugin hoặc Maven plugin; phần tạo mã là chức năng generator, còn plugin là cơ chế để build tool gọi chức năng đó. Khi kiểm kê, ghi nhận cả hai vai trò và phiên bản thực tế được thực thi.

## 2. Chuẩn bị phạm vi và bằng chứng khảo sát

Trước khi chạy lệnh, xác định module, subproject, Maven module và các build logic dùng chung thuộc phạm vi migration. Với repository nhiều module, không chỉ khảo sát module ứng dụng đầu tiên. Một module dùng chung hoặc convention plugin có thể tác động tới hàng chục module khác.

Nên chuẩn bị danh sách sau:

- Tên module/project và đường dẫn build file.
- Build tool và phiên bản Wrapper đang dùng.
- JDK chạy build, JDK compiler/toolchain và JDK runtime dự kiến.
- Các profile, flavor, target hoặc biến cấu hình làm thay đổi dependency graph.
- Các môi trường build có khác biệt: local, CI, release, container hoặc build trên hệ điều hành khác.
- Những task/goal chính mà CI chạy để compile, test, package, generate và publish.

Ghi lại commit hoặc tag đang khảo sát. Nếu dependency được thay đổi giữa hai lần chạy, kết quả sẽ không còn cùng một baseline. Với mỗi lệnh, lưu command line, thư mục chạy, thời điểm, phiên bản tool và phần output cần thiết. Không cần đưa toàn bộ log dài vào bảng kiểm kê; hãy lưu artifact log riêng và trỏ tới vị trí của nó.

Không đưa token, mật khẩu, private key, thông tin đăng nhập repository hoặc URL chứa credential vào báo cáo. Một số log debug và file effective settings có thể hiển thị thông tin nhạy cảm. Chỉ lưu bản đã lọc hoặc metadata cần thiết, theo chính sách bảo mật của tổ chức.

## 3. Thu thập dependency graph bằng Gradle

### 3.1. Xác định project và configuration

Trước tiên, xác định các project mà build nhận diện:

```bash
./gradlew --version
./gradlew projects
```

`--version` cho biết phiên bản Gradle và thông tin JVM mà Gradle đang sử dụng. Lệnh `projects` liệt kê các project trong build. Trên Windows có thể dùng `gradlew.bat` thay cho `./gradlew`.

Với từng project quan trọng, xem các task và configuration mà plugin đã tạo. Một số configuration phổ biến của Java là:

| Configuration | Nội dung cần khảo sát |
|---|---|
| `compileClasspath` | Dependency cần thiết để biên dịch mã nguồn chính |
| `runtimeClasspath` | Dependency runtime của ứng dụng |
| `testCompileClasspath` | Dependency cần thiết để biên dịch test |
| `testRuntimeClasspath` | Dependency dùng khi chạy test |
| `annotationProcessor` | Processor chạy khi biên dịch mã nguồn chính |
| `testAnnotationProcessor` | Processor chạy khi biên dịch mã test |

Project dùng Kotlin KAPT, KSP, Android plugin hoặc plugin chuyên biệt có thể có configuration khác như `kapt`, `kaptTest`, `ksp` hay configuration do plugin tự định nghĩa. Phải khảo sát configuration thực sự tồn tại và được sử dụng.

### 3.2. In dependency tree

Lệnh `dependencies` hiển thị đồ thị dependency của một project hoặc configuration:

```bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
./gradlew :app:dependencies --configuration annotationProcessor
```

Thay `:app` bằng project path thực tế. Nếu cần khảo sát nhiều module, chạy cho từng module nằm trong phạm vi thay vì chỉ dựa vào đồ thị của root project.

Một dependency tree rút gọn có thể trông như sau:

```text
runtimeClasspath - Runtime classpath of source set 'main'.
+--- org.example:service-client:2.4.0
|    +--- org.example:http-core:1.8.0
|    \--- com.fasterxml.jackson.core:jackson-databind:2.17.1
|         +--- com.fasterxml.jackson.core:jackson-annotations:2.17.1
|         \--- com.fasterxml.jackson.core:jackson-core:2.17.1
\--- org.slf4j:slf4j-api:2.0.13
```

Đồ thị này cho thấy dependency trực tiếp và các nhánh bắc cầu. Khi cùng một module được yêu cầu ở nhiều phiên bản, Gradle có thể chọn một phiên bản theo conflict resolution, constraint, rule hoặc cấu hình resolution của build. Vì vậy, cây dependency phản ánh **phiên bản được chọn**, không chỉ là các version được ghi trong file khai báo.

Một số ký hiệu thường gặp trong output Gradle:

- `group:artifact:version`: module dependency và phiên bản được chọn.
- `requested -> selected`: phiên bản được yêu cầu đã được thay bằng phiên bản được chọn.
- `(c)`: constraint, tức ràng buộc phiên bản chứ không nhất thiết là dependency trực tiếp.
- `(*)`: nhánh đã được hiển thị ở vị trí khác nên không in lặp lại toàn bộ.
- `FAILED`: dependency không phân giải được; cần xem nguyên nhân và repository.
- `strictly`, `prefer`, `reject` hoặc thông tin selection reason: dấu hiệu có rule điều khiển việc chọn phiên bản.

Không được đọc mũi tên `->` như một lỗi. Nó cho biết yêu cầu và kết quả chọn khác nhau; cần tìm lý do và xác nhận kết quả đó có chủ đích hay không.

### 3.3. Truy nguyên một dependency cụ thể

Khi phát hiện thư viện có nguy cơ không tương thích, dùng `dependencyInsight` để biết dependency nào kéo nó vào và vì sao Gradle chọn phiên bản hiện tại:

```bash
./gradlew :app:dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
```

Trên Windows PowerShell, có thể viết lệnh trên một dòng hoặc dùng dấu backtick tiếp dòng của PowerShell. Ví dụ một dòng:

```powershell
.\gradlew.bat :app:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Lặp lại với configuration phù hợp. Phiên bản trong `compileClasspath` có thể khác với phiên bản trong `runtimeClasspath` hoặc test classpath nếu các nhánh dependency và rule resolution khác nhau.

Khi đọc kết quả, tìm các thông tin:

- Dependency được yêu cầu từ module nào.
- Có bao nhiêu đường dẫn đưa thư viện vào graph.
- Phiên bản được yêu cầu và phiên bản được chọn.
- Phiên bản được chọn do conflict resolution, constraint, platform/BOM, force, substitution hay rule nào.
- Có dependency bị loại trừ hoặc thay thế không.

Nếu thư viện chỉ xuất hiện trong test classpath, chưa thể kết luận rằng nó được đóng gói trong ứng dụng. Nếu thư viện xuất hiện trong `runtimeClasspath`, cần xác định nó có thực sự được đưa vào artifact cuối hay được cung cấp bởi môi trường triển khai.

### 3.4. Kiểm kê dependency của buildscript và plugin

Với Gradle, lệnh sau hữu ích để xem buildscript classpath:

```bash
./gradlew buildEnvironment
./gradlew :app:buildEnvironment
```

Tuy nhiên, kết quả này không phải danh sách đầy đủ plugin được áp dụng bằng Plugin DSL. Vì thế cần đọc thêm:

- `settings.gradle` hoặc `settings.gradle.kts`, đặc biệt `pluginManagement` và repository dùng để phân giải plugin.
- `plugins {}` trong root và từng subproject build file.
- `buildscript { dependencies { classpath(...) } }` trong các build file.
- `gradle/libs.versions.toml` nếu dùng version catalog để khai báo plugin/dependency.
- `buildSrc/`, convention plugin và included build được khai báo trong `includeBuild(...)`.
- Plugin được áp dụng có điều kiện theo property, environment hoặc cấu hình build.

`buildEnvironment` có thể cho thấy dependency của buildscript nhưng không đủ để kết luận rằng không có plugin DSL. Plugin DSL thường được phân giải theo cơ chế plugin marker và repository trong `pluginManagement`; cần ghi lại id/version khai báo và nguồn phân giải. Với plugin nội bộ, cần kiểm tra cả source build và dependency của build đó.

Nếu cần hiểu quá trình phân giải plugin, có thể chạy một task cấu hình nhẹ với log thông tin:

```bash
./gradlew help --info
```

Output có thể rất dài và thay đổi theo phiên bản Gradle. Chỉ trích xuất các dòng liên quan đến plugin resolution và repository. Tránh lưu log debug chưa lọc vì có thể chứa thông tin nội bộ.

## 4. Thu thập dependency graph bằng Maven

### 4.1. Xem dependency tree

Với Maven Wrapper, các lệnh cơ bản gồm:

```bash
./mvnw -version
./mvnw dependency:tree
./mvnw dependency:tree -Dverbose
```

Trong multi-module project, có thể chạy từ root để khảo sát các module hoặc dùng `-pl` để chọn project cụ thể:

```bash
./mvnw -pl app dependency:tree
./mvnw -pl app dependency:tree -Dscope=runtime
./mvnw -pl app dependency:tree -Dincludes=org.example:service-client
```

`-Dverbose` bổ sung thông tin về các dependency bị loại khỏi cây kết quả, hữu ích khi cần hiểu xung đột. Có thể dùng `-Dincludes` để tập trung vào một group/artifact thay vì đọc toàn bộ cây lớn.

Maven phân giải dependency qua các scope như `compile`, `provided`, `runtime`, `test`, `system` và `import` trong trường hợp BOM. Scope ảnh hưởng đến khả năng truyền dependency và classpath của từng giai đoạn. Cần đọc cây kết quả cùng POM hiệu lực để hiểu dependency được kế thừa, quản lý hoặc loại trừ ở đâu.

### 4.2. Hiểu cách Maven chọn phiên bản

Khi cùng một artifact được yêu cầu ở nhiều phiên bản, Maven áp dụng quy tắc mediation, trong đó đường dẫn gần nhất thường được ưu tiên; dependency management có thể quản lý hoặc ghi đè version. Vì vậy, version ghi trong POM của một thư viện con chưa chắc là version cuối cùng được dùng.

Trong output verbose, chú ý các nhánh bị omitted vì conflict hoặc duplicate. Hãy xác định:

- Artifact được yêu cầu qua những đường dẫn nào.
- Phiên bản nào được chọn và phiên bản nào bị loại.
- Dependency management của parent POM hoặc BOM có điều khiển version không.
- Có exclusion nào làm mất dependency mà thư viện kỳ vọng không.
- Module khác trong cùng reactor có chọn version khác hay không.

Không nên chỉ sửa version tại nơi xuất hiện đầu tiên. Cần xác định nơi quản lý version có chủ đích, thường là `dependencyManagement`, BOM hoặc parent POM.

### 4.3. Thu thập POM hiệu lực và plugin

POM thực tế có thể được hình thành từ parent POM, property, profile, dependency management và plugin management. Dùng:

```bash
./mvnw help:effective-pom
./mvnw help:effective-pom -Dverbose
./mvnw dependency:resolve-plugins
```

Effective POM cho biết cấu hình sau khi Maven áp dụng kế thừa và profile đang hoạt động. `dependency:resolve-plugins` hỗ trợ phân giải dependency của các build plugin. Cần kiểm tra cả:

- `build/plugins` và `build/pluginManagement`.
- Plugin khai báo ở parent POM và plugin được module con kế thừa.
- Plugin version, execution, goal, phase và cấu hình riêng.
- Profile kích hoạt theo property, JDK, OS hoặc file hiện diện.
- Dependency khai báo bên trong từng plugin.
- Plugin extension hoặc lifecycle mapping nếu dự án có sử dụng.

Plugin dependency có class realm riêng. Nó không mặc nhiên trở thành dependency runtime của ứng dụng. Khi một plugin dùng thư viện bytecode hoặc API JDK cũ, lỗi có thể xuất hiện lúc chạy Maven goal ngay cả khi dependency tree của ứng dụng không có thư viện đó.

`help:effective-pom` và log Maven có thể chứa đường dẫn nội bộ, URL repository hoặc property nhạy cảm. Trước khi chia sẻ, lọc thông tin xác thực và chỉ giữ các trường cần cho kiểm kê.

## 5. Kiểm kê plugin build theo khả năng tương thích

Danh sách plugin chỉ có giá trị khi đi kèm bối cảnh thực thi. Với mỗi plugin, ghi ít nhất:

| Trường | Ý nghĩa |
|---|---|
| Plugin id hoặc tọa độ | Gradle plugin id hoặc Maven `groupId:artifactId` |
| Version | Version được khai báo và version thực sự được phân giải |
| Nguồn khai báo | Root build, subproject, parent POM, plugin management, convention plugin |
| Nguồn phân phối | Plugin Portal, Maven repository, repository nội bộ hoặc build logic local |
| Vai trò | Compile, test, package, quality, code generation, container, publish... |
| Giai đoạn chạy | Configuration, task/goal, lifecycle phase hoặc CI stage |
| JDK chạy build | JDK mà plugin thực sự chạy trong tiến trình build |
| Yêu cầu tool | Phiên bản Gradle/Maven tối thiểu, JDK hỗ trợ và plugin phụ thuộc |
| Bằng chứng | Release notes, compatibility matrix, log build và kết quả thử nghiệm |

Các nhóm plugin thường cần chú ý trong Java migration:

- Java/Kotlin compiler và language plugin.
- Spring Boot, application packaging và executable archive.
- Test framework integration, test runner và test fixture.
- Coverage, static analysis, lint và quality gate.
- Annotation processing hoặc generator integration.
- Javadoc, documentation, API/spec generation.
- Database migration, schema inspection và jOOQ generation.
- Container image, deployment và release/publishing.
- Plugin nội bộ, convention plugin và plugin do nhóm tự viết.

### 5.1. Kiểm tra quan hệ giữa plugin và JDK

Plugin có thể bị ràng buộc bởi nhiều phiên bản khác nhau:

1. JDK dùng để khởi chạy Gradle hoặc Maven.
2. Phiên bản Gradle/Maven mà plugin hỗ trợ.
3. JDK mà task/plugin dùng để fork tiến trình con, nếu có.
4. Toolchain compiler dùng để biên dịch ứng dụng.
5. Phiên bản Java mà mã được sinh ra hoặc được biên dịch tới.

Ví dụ, một plugin có thể chạy trên JDK 21 nhưng tạo source code hướng tới Java 17; một plugin khác có thể gọi API JDK mới trong tiến trình build và vì thế không chạy trên JDK 17 dù ứng dụng vẫn target Java 17. Phải ghi riêng từng quan hệ, không suy ra khả năng tương thích của plugin từ `sourceCompatibility` hoặc `targetCompatibility`.

### 5.2. Đánh giá plugin cũ hoặc ít được duy trì

Với plugin không còn release gần đây, không có ma trận hỗ trợ rõ ràng hoặc phụ thuộc vào API nội bộ, cần xác định:

- Plugin còn được dùng trong CI hoặc chỉ tồn tại trong build file.
- Task/goal nào thực sự gọi plugin.
- Có thể thay thế bằng chức năng chính thức của Gradle/Maven hoặc công cụ đang được duy trì không.
- Plugin có thể được nâng độc lập hay cần thay đổi cấu hình/build logic.
- Nếu phải giữ lại, có thể cô lập plugin trong một task hoặc tiến trình con không.
- Cần test nào để chứng minh plugin vẫn tạo ra artifact đúng.

Không nên xóa plugin chỉ vì không thấy mã nguồn ứng dụng gọi trực tiếp. Plugin có thể tạo resource, sửa manifest, sinh metadata hoặc thiết lập quy trình phát hành. Trước khi loại bỏ, phải truy tìm task/goal và tác động của nó trong pipeline.

## 6. Thu thập công cụ sinh mã và đầu ra được tạo

### 6.1. Lập danh sách generator

Tìm generator qua nhiều vị trí, không chỉ tìm từ khóa `generate` trong source code:

- Dependency configuration dành cho annotation processor.
- Gradle task và plugin có tên chứa `generate`, `compile`, `schema`, `openapi`, `proto`, `avro`, `jooq` hoặc tương tự.
- Maven plugin execution, đặc biệt `generate-sources`, `generate-resources`, `process-sources` và `compile`.
- `annotationProcessorPaths` hoặc cấu hình compiler plugin.
- Thư mục source được khai báo thêm như generated source directory.
- File schema, specification, grammar, template và cấu hình generator.
- Script shell, script Gradle, Maven profile hoặc CI step chạy generator ngoài lifecycle chính.

Ví dụ, generator có thể không xuất hiện trong dependency tree runtime nhưng vẫn là thành phần thiết yếu để compile vì nó tạo ra Java source trước khi compiler chạy.

### 6.2. Phân biệt annotation processor và generator task

Annotation processor được compiler gọi trong quá trình compile. Processor thường đọc annotation và type model, sau đó sinh source hoặc resource vào generated output directory. Ví dụ, Lombok và MapStruct thường được cấu hình trên annotation processor path. Dependency processor cần được tách khỏi dependency runtime của ứng dụng.

Generator task/goal chạy như một bước riêng. Nó có thể đọc schema hoặc OpenAPI file, tải template, áp dụng option và ghi source vào một thư mục được compiler nhận biết. Ví dụ, OpenAPI Generator, Protobuf, Avro, ANTLR hoặc jOOQ có thể được gọi theo cách này tùy build tool và plugin.

Một công cụ có thể dùng cả hai mô hình hoặc tích hợp theo cách riêng. Hãy xác định cơ chế thực tế của dự án thay vì phân loại chỉ theo tên sản phẩm.

### 6.3. Ghi nhận cấu hình và input của generator

Với từng generator, thu thập:

- Tên công cụ, plugin/processor và version.
- JDK chạy generator và JDK/toolchain dùng để compile output.
- Input: annotation, Java type, OpenAPI document, `.proto`, schema, database metadata, grammar, YAML/JSON hoặc template.
- Cấu hình: package name, naming strategy, nullable handling, date/time mapping, serialization, framework target và option tương thích.
- Output directory, source set hoặc source root được thêm vào build.
- Task/goal gọi generator và thứ tự phụ thuộc với compile/package.
- Cách generator xử lý file cũ, file bị xóa và output không còn được sinh ra.
- Có kiểm tra output được tạo lại ổn định hay không.

Đối với generator đọc database hoặc dịch vụ ngoài, ghi cả phiên bản database, schema snapshot, quyền truy cập và nguồn dữ liệu. Không lưu password hoặc secret; chỉ lưu tên connection/profile và cách môi trường cung cấp credential.

### 6.4. Xác định quyền sở hữu generated source

Generated source thường không phải nội dung được lập trình viên sửa trực tiếp. Cần biết:

- Thư mục output có được commit vào Git không.
- Source of truth là schema/specification/annotation hay chính file Java được sinh.
- Có bước chỉnh sửa thủ công sau khi generator chạy không.
- Có file generated nào được đưa vào artifact phát hành.
- Quy trình build sạch có thể tái tạo đầy đủ output không.

Nếu file được sinh và có chỉnh tay, phải ghi rõ cơ chế merge hoặc source of truth. Nếu chỉ sửa file generated mà không sửa input hoặc template, lần generate kế tiếp có thể ghi đè thay đổi. Trong migration, cần so sánh output trước/sau khi nâng generator để phát hiện thay đổi API, kiểu dữ liệu, annotation, import hoặc cấu trúc package.

## 7. Các rủi ro tương thích đặc thù của công cụ sinh mã

Generator không chỉ cần chạy được trên JDK mới. Output của nó còn phải tương thích với compiler, framework, thư viện runtime và mức Java mà module cam kết.

### 7.1. JDK thực thi generator

Một generator có thể chạy trong cùng tiến trình Gradle/Maven, trong compiler, hoặc được fork thành tiến trình riêng. Nếu chạy cùng tiến trình, nó chịu ràng buộc bởi JDK chạy build. Nếu fork, cần kiểm tra executable/JDK được chọn, JVM options và classpath của tiến trình con.

Không giả định rằng cấu hình Java toolchain của compiler tự động điều khiển JDK chạy mọi generator. Một số plugin hỗ trợ toolchain riêng; một số dùng JVM của Gradle/Maven; một số tự tìm `JAVA_HOME`. Cần kiểm tra tài liệu plugin và log thực thi.

### 7.2. Tương thích giữa processor và compiler

Annotation processor dùng compiler API, `javax.lang.model`, `com.sun.source` hoặc các API liên quan. Khi nâng JDK/compiler, processor cũ có thể gặp lỗi truy cập module, lỗi reflection, lỗi type model hoặc không hiểu cấu trúc mới của ngôn ngữ.

Các dấu hiệu thường gặp:

- `IllegalAccessError`, `InaccessibleObjectException` hoặc lỗi truy cập package nội bộ.
- Processor không được phát hiện hoặc không chạy.
- Lỗi khi xử lý record, sealed class, generic type hoặc annotation mới.
- Generated source thiếu method, sai type hoặc có annotation không còn phù hợp.
- Lỗi chỉ xuất hiện khi chạy compile trên JDK đích, dù source của ứng dụng không thay đổi.

Khi gặp lỗi, cần xác định stack trace thuộc compiler, processor hay plugin tích hợp processor. Không vội thêm `--add-opens` trên toàn bộ build. Ưu tiên nâng processor lên phiên bản hỗ trợ, thay thế công cụ hoặc áp dụng cấu hình mở module giới hạn khi có căn cứ và kế hoạch gỡ bỏ.

### 7.3. Tương thích của generated source

Generated source có thể dùng API chỉ tồn tại trên JDK mới hơn, cú pháp ngôn ngữ mới hơn hoặc annotation/framework version khác. Cần xác minh:

- Source level và API target mà generator hướng tới.
- Output có biên dịch được bằng compiler/toolchain đã chốt không.
- Generated class có phụ thuộc vào runtime library tương ứng không.
- Output có tương thích với version framework và serialization contract hiện tại không.
- Generator có tạo ra warning hoặc API deprecated mới không.

Một generator chạy thành công chỉ chứng minh nó đã tạo file; không chứng minh file đó đúng hoặc tương thích. Bằng chứng cần có compile output, test cho hành vi được sinh và kiểm tra artifact cuối.

### 7.4. Tính tái lập và độ ổn định của output

Chạy generator hai lần trên cùng input, cùng version và cùng cấu hình để kiểm tra output có ổn định hay không. Output có thể khác vì timestamp, thứ tự file, môi trường locale, timezone, đường dẫn tuyệt đối, database metadata hoặc phiên bản template.

Nếu output không ổn định, hãy tìm nguồn biến thiên và xác định nó có ảnh hưởng artifact hay không. Với generator có output được commit, diff sau mỗi lần chạy là bằng chứng hữu ích để phát hiện thay đổi ngoài dự kiến.

### 7.5. Rủi ro bảo mật và nguồn đầu vào

Generator có thể thực thi code trong plugin, template hoặc processor; nó cũng có thể truy cập database, repository hay file hệ thống. Cần kiểm tra nguồn tải công cụ, version được pin, repository được phép sử dụng, quyền của CI và nội dung đầu vào. Không chạy generator từ nguồn không tin cậy trong môi trường có secret production.

## 8. Kiểm tra version management, BOM và độ tái lập dependency

Dependency tree là ảnh chụp graph tại một lần build. Để kết quả migration có thể tái lập, cần hiểu nơi quản lý version và cơ chế khóa dependency.

### 8.1. Gradle version catalog, platform và constraints

Gradle project có thể quản lý version trong `gradle/libs.versions.toml`, platform/BOM, dependency constraints, resolution strategy hoặc convention plugin. Version catalog giúp tập trung alias và version, nhưng không tự động chứng minh rằng mọi dependency bắc cầu đã được khóa.

Kiểm tra:

- Version catalog và plugin aliases.
- `platform(...)` hoặc `enforcedPlatform(...)` và BOM được import.
- `constraints {}` và dependency constraints do plugin thêm.
- `resolutionStrategy.force`, substitution và component selection rules.
- Dependency lock files nếu dự án bật dependency locking.
- Dependency verification metadata nếu dự án dùng verification.

Nếu dependency locking được bật, cần xác định lock state có được cập nhật và commit cùng thay đổi hay không. Nếu dùng verification metadata, cần biết checksum/signature có bao phủ artifact mới không. Không nên tắt cơ chế verification chỉ để build vượt qua lỗi phân giải.

### 8.2. Maven BOM và dependencyManagement

Maven có thể tập trung quản lý version qua parent POM và BOM được import bằng scope `import`. `dependencyManagement` quản lý version mà không tự thêm dependency vào classpath. Một dependency chỉ được đưa vào graph khi được khai báo ở nơi cần dùng hoặc được kế thừa theo cấu hình phù hợp.

Khi nâng framework hoặc JDK, cần kiểm tra BOM đang quản lý các thư viện nền tảng nào, version override nào đã được dự án thêm và plugin version có được quản lý riêng hay không. Không nên nâng một thư viện vượt khỏi BOM mà không xác minh tương thích của toàn bộ nhóm thư viện liên quan.

### 8.3. Repository và nguồn phân phối

Ghi nhận repository được dùng để tải dependency và plugin: Maven Central, Gradle Plugin Portal, repository nội bộ, mirror hoặc artifact registry. Cùng một tọa độ có thể được phân phối qua nhiều nguồn; quy tắc repository và mirror ảnh hưởng khả năng tái lập và độ tin cậy.

Không ghi credential vào báo cáo. Chỉ ghi tên repository, loại repository, thứ tự/ưu tiên phân giải và chính sách kiểm soát. Nếu một dependency chỉ có ở repository nội bộ, cần xác nhận repository đó vẫn cung cấp artifact tương ứng trong CI và môi trường release.

## 9. Quy trình khảo sát thực tế theo từng bước

Có thể áp dụng quy trình sau cho mỗi module hoặc nhóm module có cùng build logic.

### Bước 1: Chốt baseline

Ghi commit, build tool version, JDK chạy build, project path và profile/variant đang khảo sát. Xác định đúng command mà CI dùng để build module.

### Bước 2: Lập danh sách dependency configuration

Với Gradle, liệt kê các configuration compile, runtime, test, processor và configuration đặc thù. Với Maven, xác định scope, profile và module reactor liên quan.

### Bước 3: Xuất dependency graph

Chạy lệnh `dependencies`/`dependencyInsight` hoặc `dependency:tree` cho các configuration cần thiết. Lưu output và truy nguyên những thư viện có nhiều version, thư viện nền tảng và thư viện đã biết có vấn đề tương thích.

### Bước 4: Lập danh sách plugin

Đọc khai báo plugin ở root và module con, plugin management, buildscript classpath, parent POM, pluginManagement, convention plugin và included build. Ghi version và task/goal mà plugin cung cấp.

### Bước 5: Tìm generator và processor

Khảo sát annotation processor path, KAPT/KSP, compiler plugin, generator task/goal, source set generated và script chạy ngoài lifecycle. Ghi input, output, version, JDK thực thi và cách tái tạo.

### Bước 6: Đối chiếu hỗ trợ

Với từng thành phần, kiểm tra tài liệu chính thức về JDK, Gradle/Maven và framework được hỗ trợ. Tách rõ trạng thái “nhà cung cấp công bố hỗ trợ” với “dự án đã chạy kiểm chứng”.

### Bước 7: Xác nhận trên build sạch

Sau khi đã có baseline, có thể chạy quy trình build sạch trong môi trường khảo sát để xác minh dependency được tải lại và generator tạo lại output. Bước này thuộc hoạt động kiểm chứng; cần dùng đúng command/pipeline được nhóm cho phép và lưu kết quả. Trong giai đoạn thu thập ban đầu, không tự thay đổi version hay cấu hình chỉ để làm build xanh.

### Bước 8: Ghi khoảng trống và chủ sở hữu

Mọi version không rõ nguồn, plugin không rõ tác dụng, generator không rõ input hoặc dependency chưa xác định khả năng hỗ trợ phải được ghi thành mục cần làm rõ. Gán module, owner và bằng chứng cần bổ sung.

## 10. Mẫu bảng kiểm kê

### 10.1. Bảng dependency ứng dụng

| Module | Configuration/scope | Group:artifact | Version yêu cầu | Version được chọn | Nguồn khai báo/đường dẫn | Vai trò | JDK đích | Trạng thái |
|---|---|---|---|---|---|---|---|---|
| app | runtimeClasspath | `org.example:client` | 2.x | 2.x | khai báo trực tiếp | HTTP client | cần xác minh | Chưa xác định |
| app | runtimeClasspath | `com.example:core` | 1.x | 1.x | bắc cầu qua client | core API | cần xác minh | Chưa xác định |
| app | annotationProcessor | `org.example:processor` | 3.x | 3.x | processor config | Sinh mã | cần xác minh | Chưa xác định |

Các version trong bảng trên chỉ minh họa cấu trúc; phải thay bằng dữ liệu lấy từ build thực tế. Nếu cùng một artifact xuất hiện ở nhiều configuration, ghi thành các dòng riêng hoặc liên kết tới từng graph để không đánh đồng classpath.

### 10.2. Bảng plugin build

| Build/module | Plugin id hoặc tọa độ | Version | Nguồn khai báo | Task/goal | JDK/Build tool yêu cầu | Bằng chứng hỗ trợ |
|---|---|---|---|---|---|---|
| root | plugin Java | version thực tế | root build | compile/test/jar | Gradle và JDK thực tế | release notes + build log |
| app | plugin framework | version thực tế | module build | package/run | ma trận framework | tài liệu chính thức |
| build logic | convention plugin nội bộ | commit/version | included build | cấu hình module | JDK chạy Gradle | source và build test |

### 10.3. Bảng công cụ sinh mã

| Generator/processor | Version | Cách gọi | Input | Output | JDK thực thi | Source of truth | Cách kiểm chứng |
|---|---|---|---|---|---|---|---|
| Processor A | version thực tế | annotation processing | Java annotation/type | Java source | compiler/build JDK | source + annotation | compile và test generated behavior |
| Generator B | version thực tế | Gradle task/Maven goal | API/schema file | client/model source | plugin/build JDK | schema/spec | diff output và compile |
| Generator C | version thực tế | task/goal ngoài compiler | database schema | metamodel source | JDK của task | database/schema snapshot | generate sạch và integration test |

### 10.4. Bảng vấn đề tương thích

| ID | Thành phần | Hiện tượng/bằng chứng | Phạm vi ảnh hưởng | Mức ưu tiên | Việc cần làm | Điều kiện đóng |
|---|---|---|---|---|---|---|
| COMPAT-DEP-001 | Dependency X | Chưa xác nhận hỗ trợ JDK đích | Module A, B | Cần đánh giá | Kiểm tra release notes và thử nghiệm | Có nguồn hỗ trợ và kết quả test |
| COMPAT-PLUGIN-001 | Plugin Y | Yêu cầu Gradle cũ | Build root | Cao nếu chặn nâng Wrapper | Tìm version/plugin thay thế | Build trên Wrapper đích thành công |
| COMPAT-GEN-001 | Processor Z | Lỗi truy cập compiler API | Module C | Chặn compile nếu tái hiện | Nâng processor hoặc thay thế | Generated source compile và test đạt |

## 11. Ví dụ đọc một vấn đề từ dependency graph đến migration

Giả sử module `billing-service` chạy trên JDK cũ và dependency tree cho thấy thư viện `proxy-engine` được kéo vào qua `data-client`. Khi thử build bằng JDK đích, compile test hoặc test khởi động gặp lỗi truy cập API nội bộ của JDK.

Không nên sửa ngay mã `billing-service`, vì thư viện gây lỗi có thể là dependency bắc cầu. Quy trình truy nguyên:

1. Xác định configuration gây lỗi: `compileClasspath`, `testRuntimeClasspath`, `annotationProcessor` hay build plugin classpath.
2. Chạy `dependencyInsight` hoặc `dependency:tree -Dverbose` để tìm đường dẫn từ `billing-service` tới `proxy-engine`.
3. Ghi version được yêu cầu, version được chọn, nơi quản lý version và lý do chọn.
4. Xác định thư viện thuộc runtime ứng dụng, processor hay plugin build. Mỗi trường hợp có cách nâng cấp và kiểm thử khác nhau.
5. Kiểm tra version mới của `data-client`/`proxy-engine`, ma trận JDK hỗ trợ và quan hệ với framework hiện tại.
6. Nếu thư viện nằm trong plugin build, kiểm tra compatibility của plugin với Gradle/Maven và JDK chạy build. Nếu nằm trong runtime, kiểm tra artifact đóng gói và hành vi ứng dụng.
7. Nâng cấp trong phạm vi nhỏ, tạo lại dependency graph và so sánh version được chọn.
8. Chạy build, test và smoke test trên JDK đích; lưu log và cập nhật trạng thái vấn đề.

Một tình huống khác: ứng dụng compile thất bại vì MapStruct processor không tương thích với compiler mới. Dependency runtime có thể hoàn toàn bình thường. Cần kiểm tra annotation processor configuration, version processor, plugin compiler và generated source. Nâng thư viện MapStruct runtime mà không nâng processor tương ứng có thể không giải quyết lỗi, vì thành phần trực tiếp thực thi trong compiler là processor.

Hai ví dụ này cho thấy việc phân loại đúng configuration và classpath quyết định hướng xử lý. Chỉ tìm tên thư viện trong `build.gradle` hoặc `pom.xml` có thể bỏ sót nguồn gây lỗi thật sự.

## 12. Những lỗi khảo sát thường gặp

| Cách làm chưa đủ | Vì sao dễ sai | Cách khảo sát phù hợp |
|---|---|---|
| Chỉ đọc dependency khai báo trực tiếp | Bỏ sót dependency bắc cầu và version được chọn | Xuất graph cho từng configuration/scope |
| Chỉ chạy `dependencies` ở root | Root graph có thể không đại diện classpath của từng module | Khảo sát từng project/module liên quan |
| Chỉ xem `runtimeClasspath` | Bỏ sót processor, test dependency và build plugin | Thu thập compile, runtime, test, processor và build logic |
| Coi `buildEnvironment` là toàn bộ Gradle plugin | Plugin DSL được phân giải theo cơ chế riêng | Đọc `plugins {}`, `pluginManagement`, version catalog và included build |
| Chỉ đọc POM của module Maven | Bỏ sót parent, profile và plugin management | Lấy effective POM cùng dependency tree và plugin resolution |
| Gộp plugin dependency vào dependency ứng dụng | Nhầm classpath build với artifact runtime | Ghi riêng plugin, plugin dependency và application dependency |
| Coi generator chỉ là một thư viện | Bỏ sót task/goal, input và output được tạo | Kiểm kê cơ chế gọi, source set và generated output |
| Chỉ kiểm tra generator chạy được | Output có thể không compile hoặc đổi hành vi | Compile generated source, test và so sánh output |
| Ghi version trong file build là version thực tế | Version có thể bị BOM, constraint hoặc conflict resolution thay đổi | Xác minh version được chọn trong graph |
| Chạy debug log rồi lưu nguyên văn | Có thể lộ URL nội bộ hoặc thông tin xác thực | Lọc log và loại bỏ dữ liệu nhạy cảm |
| Nâng tất cả thư viện/plugin cùng lúc | Khó truy nguyên nguyên nhân regression | Chia thay đổi theo nhóm và giữ bằng chứng từng bước |

## 13. Tiêu chí hoàn thành khảo sát

Việc thu thập được xem là đủ để chuyển sang phân tích tương thích khi nhóm có thể trả lời bằng bằng chứng cho các câu hỏi sau:

- Đã xác định đầy đủ module và build logic nằm trong phạm vi chưa?
- Đã biết dependency trực tiếp và bắc cầu được chọn cho compile, runtime, test và processor chưa?
- Đã truy nguyên được các version bị thay thế, ép chọn, loại trừ hoặc quản lý qua BOM/constraint chưa?
- Đã lập danh sách plugin Gradle/Maven, version, nguồn khai báo, task/goal và yêu cầu JDK/build tool chưa?
- Đã kiểm tra plugin DSL, buildscript, parent POM, plugin management, convention plugin và included build chưa?
- Đã tìm thấy annotation processor, KAPT/KSP và các generator task/goal chạy ngoài compiler chưa?
- Đã ghi input, output, version, JDK thực thi và source of truth của từng generator chưa?
- Đã phân biệt dependency runtime với processor/plugin dependency chưa?
- Đã lưu baseline, command, output và nguồn bằng chứng có thể truy vết chưa?
- Những phần chưa xác định đã có owner và hành động tiếp theo chưa?

Không nên chuyển một thành phần sang trạng thái “tương thích” chỉ vì version của nó đã được ghi nhận. Cần có nguồn công bố hỗ trợ phù hợp và/hoặc kết quả kiểm chứng trên tổ hợp đích theo tiêu chí của dự án. Nếu chưa có tài liệu hoặc môi trường thử nghiệm, ghi rõ “chưa xác định” để đưa vào gap/risk register.

## 14. Đầu ra bàn giao cho bước phân tích tương thích

Sau khảo sát, nhóm nên có một bộ hồ sơ có thể tái sử dụng:

1. **Danh mục module/build:** module path, build tool, Wrapper version, JDK chạy build và các profile/variant liên quan.
2. **Dependency inventory:** dependency graph theo configuration/scope, version được yêu cầu và được chọn, đường dẫn phụ thuộc và nơi quản lý version.
3. **Plugin inventory:** plugin id/tọa độ, version, nguồn phân giải, task/goal, dependency riêng và yêu cầu JDK/build tool.
4. **Generator inventory:** processor/generator, version, input, output, cách gọi, JDK thực thi, source of truth và kiểm tra tái lập.
5. **Version governance:** BOM, version catalog, dependency constraints, lock files, verification metadata, repository và policy liên quan.
6. **Evidence archive:** command, log đã lọc, effective POM, dependency tree, release notes và kết quả thử nghiệm.
7. **Gap register:** thành phần chưa hỗ trợ hoặc chưa xác định, phạm vi ảnh hưởng, mức ưu tiên, owner và tiêu chí đóng.

### Checklist bàn giao

- [ ] Baseline gắn với commit và cấu hình build xác định.
- [ ] Dependency graph đã được thu thập cho các classpath/configuration cần thiết.
- [ ] Dependency bắc cầu và lý do chọn version đã được truy nguyên cho thành phần quan trọng.
- [ ] Plugin build được thống kê riêng với dependency ứng dụng.
- [ ] Plugin DSL, buildscript, plugin management và build logic nội bộ đã được xem xét.
- [ ] Annotation processor và công cụ sinh mã đã được nhận diện.
- [ ] Input, output, JDK thực thi và cách tái tạo output của generator đã được ghi lại.
- [ ] BOM, version catalog, constraints, lock và verification policy đã được kiểm tra.
- [ ] Bằng chứng đã được lưu an toàn, không chứa credential hoặc secret.
- [ ] Mọi khoảng trống đều có người phụ trách và bước xác minh tiếp theo.

Thu thập dependency tree, plugin build và công cụ sinh mã giúp nhóm nhìn thấy toàn bộ thành phần tham gia vào quá trình tạo và chạy ứng dụng. Khi tách đúng classpath, truy nguyên version được chọn và xác định generator thực thi ở đâu, nhóm có thể tìm ra nguyên nhân tương thích ở đúng tầng. Đây là nền tảng để lập ma trận hỗ trợ, đánh giá rủi ro và thiết kế các bước migration có thể kiểm chứng.
