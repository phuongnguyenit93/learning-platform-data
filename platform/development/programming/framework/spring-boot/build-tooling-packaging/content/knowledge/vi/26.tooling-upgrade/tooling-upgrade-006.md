# So sánh dependency graph, nội dung artifact và kết quả kiểm tra sau nâng cấp Spring Boot

## 1. Mục tiêu: chứng minh bản nâng cấp thay đổi những gì

Trong nhóm **Nâng cấp công cụ**, bài học này trình bày cách so sánh một ứng dụng Spring Boot trước và sau khi nâng cấp Spring Boot, JDK, Maven/Gradle plugin hoặc dependency platform. Một lần nâng cấp có thể chỉ sửa một version trong build file nhưng làm thay đổi nhiều dependency bắc cầu, nội dung executable JAR, manifest, runtime behavior và kết quả test.

Không nên kết luận nâng cấp thành công chỉ vì lệnh build trả exit code 0. Cần thu thập và đối chiếu ba nhóm bằng chứng độc lập:

1. **Dependency graph:** thư viện nào được resolve, version nào được chọn, scope/configuration nào sử dụng chúng và vì sao có version đó.
2. **Artifact contents:** JAR/WAR cuối thực sự chứa class, resource, nested libraries, metadata và manifest nào.
3. **Test results:** test nào đã chạy, số lượng pass/fail/error/skipped, integration test, smoke test và các lỗi runtime sau nâng cấp.

Mục tiêu không phải làm cho hai bản build có mọi byte giống nhau. Khi nâng version, dependency JAR và một số metadata tất nhiên thay đổi. Mục tiêu là giải thích được từng khác biệt, xác nhận những thay đổi được mong đợi, phát hiện thay đổi ngoài ý muốn và chứng minh ứng dụng vẫn đáp ứng hợp đồng vận hành.

**Bộ phiên bản minh họa:** Java 17, Spring Boot 3.3.5, Maven 3.9.x hoặc Gradle 8.5. Đây là bộ version cố định để ví dụ nhất quán; quy trình so sánh áp dụng tương tự cho các version khác.

## 2. Ba lớp bằng chứng phải được so sánh riêng

| Nhóm bằng chứng | Câu hỏi cần trả lời | Công cụ thường dùng | Kết quả lưu |
| --- | --- | --- | --- |
| **Dependency graph** | Dependency trực tiếp/bắc cầu nào được chọn? Có eviction, conflict, override hoặc scope thay đổi không? | Maven dependency:tree/effective-pom; Gradle dependencies/dependencyInsight | JSON/text graph, effective POM, lockfile |
| **Artifact contents** | Archive có đúng class, resource, launcher, manifest và runtime library không? | jar tf, unzip, javap, checksum | Entry list, nested library list, manifest, SHA-256 |
| **Test results** | Test suite nào thực sự chạy? Failures/errors/skips có thay đổi không? App có khởi động và chạy smoke test không? | Surefire/Failsafe, Gradle Test, JUnit XML, smoke test | XML/HTML reports, log, summary |

Ba lớp có quan hệ nhưng không thay thế nhau:

- Dependency graph cho biết **build tool đã resolve** gì.
- Artifact inspection cho biết **file đã đóng gói** gì.
- Test results cho biết **hành vi đã được kiểm tra** ra sao.

Ví dụ, dependency graph có thể chứa dependency ở test scope nhưng dependency đó không được đưa vào executable JAR. Ngược lại, JAR có thể thiếu một library do packaging/exclusion dù dependency graph runtime nhìn vẫn đúng. Test pass cũng không chứng minh mọi dependency đã được đóng gói đúng nếu test không chạm tới code path đó.

## 3. Hiểu tác động của Spring Boot BOM trước khi so sánh

Spring Boot cung cấp một tập dependency versions được quản lý và kiểm thử cùng release thông qua BOM **spring-boot-dependencies**. Khi nâng Spring Boot version, nhiều dependency Spring và third-party có thể được nâng đồng bộ, dù các dòng khai báo dependency trực tiếp trong dự án không đổi.

Điều này tạo ra hai loại thay đổi:

- **Thay đổi trực tiếp:** nhóm sửa version của Spring Boot, plugin, JDK hoặc một dependency cụ thể.
- **Thay đổi bắc cầu/được quản lý:** BOM hoặc resolution rules chọn version mới cho dependency mà project không khai báo trực tiếp.

Ví dụ, project khai báo **spring-boot-starter-web** nhưng không ghi version cho **spring-web**, **spring-core**, Jackson hoặc Tomcat. Version của các thư viện này được quản lý bởi dependency management của Spring Boot. Khi nâng BOM, dependency graph có thể thay đổi theo.

### 3.1. Không override version nếu chưa hiểu BOM

Một override trực tiếp có thể làm dependency lệch khỏi bộ version Spring Boot đã kiểm thử. Chỉ override khi có lý do rõ ràng như security fix, compatibility requirement hoặc bug đã được xác minh; ghi lại lý do và test tương ứng.

Trong Maven, kiểm tra dependencyManagement, properties và effective POM. Trong Gradle, kiểm tra platform/BOM, constraints, resolution rules và dependencyInsight.

### 3.2. Phân biệt plugin version và library version

Các version sau có thể độc lập:

- Spring Boot application/BOM version.
- Spring Boot Maven Plugin hoặc Gradle Plugin version.
- Maven/Gradle wrapper version.
- JDK distribution/version.
- Plugin phân tích, test, coverage, packaging và security scanning.

Nâng nhiều nhóm cùng lúc khiến khó xác định nguyên nhân của một regression. Nếu có thể, chia thành các bước riêng: nâng JDK, nâng build tool, nâng Spring Boot/BOM, rồi nâng các plugin phụ trợ.

## 4. Thiết lập phép so sánh công bằng trước và sau nâng cấp

### 4.1. Chọn hai revision có thể truy vết

Tạo hai revision:

- **Before:** commit ổn định trước khi nâng cấp.
- **After:** commit chỉ chứa thay đổi nâng cấp đang đánh giá.

Tốt nhất dùng hai Git worktree hoặc hai checkout riêng để output không ghi đè lên nhau. Ví dụ:

~~~bash
git worktree add ../catalog-before COMMIT_BEFORE_UPGRADE
git worktree add ../catalog-after COMMIT_AFTER_UPGRADE
~~~

Thay hai tên commit mẫu bằng SHA thực tế của repository. Nếu không muốn tạo worktree, dùng hai branch/checkout riêng và sao lưu evidence ra thư mục độc lập trước khi chạy clean.

### 4.2. Giữ nguyên những điều kiện không thuộc phạm vi nâng cấp

Để phép so sánh có ý nghĩa, cố định hoặc ghi nhận:

- Cùng commit mã nguồn ứng dụng, ngoại trừ thay đổi build/version cần đánh giá.
- Cùng JDK major và distribution; nếu nâng JDK, ghi đó là một biến độc lập.
- Cùng Maven/Gradle command, profiles, properties và test filters.
- Cùng OS/architecture nếu native dependencies hoặc platform-specific resolution có ảnh hưởng.
- Cùng repository mirrors, credentials policy và nguồn artifact.
- Cùng môi trường kiểm thử, database/schema, service containers và environment variables.
- Cùng quy tắc dependency lock/verification.
- Cùng cách tạo executable JAR/WAR và classifier.

Không dùng **-DskipTests**, **-Dmaven.test.skip=true**, **-x test** hoặc profile bỏ test ở một phía rồi so trực tiếp với phía còn lại. Không thêm **-U** tùy tiện vào một lần build Maven vì nó yêu cầu cập nhật snapshot/repository metadata và có thể làm dependency graph thay đổi ngoài ý muốn.

### 4.3. Ghi lại môi trường của từng lần build

Linux/macOS:

~~~bash
git rev-parse HEAD
java -version
./mvnw --version
./gradlew --version
~~~

Chỉ chạy lệnh wrapper tương ứng với build system của project. Lưu stdout/stderr cùng evidence của revision đó.

Cần ghi nhận thêm:

- Commit SHA và branch/tag.
- Version Spring Boot/BOM.
- Version Maven/Gradle wrapper và plugin.
- JDK vendor, version và architecture.
- Build profile/task/flags.
- Kết quả test.
- Artifact filename và SHA-256.

**Nếu vừa nâng Java 17 lên Java 21 vừa nâng Spring Boot**, hãy xem đây là một phép nâng cấp nhiều biến. Khi có regression, cần build trung gian với chỉ một biến thay đổi để tìm nguyên nhân.

## 5. Maven: ghi lại effective POM và dependency graph

Maven có hai góc nhìn quan trọng:

- **Effective POM:** kết quả sau khi hợp nhất parent POM, properties, dependency management, plugin management và active profiles.
- **Dependency tree:** graph dependency được Maven resolve cho module đang build, bao gồm quan hệ trực tiếp và bắc cầu.

### 5.1. Effective POM

Lệnh:

~~~bash
./mvnw -pl app org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose -Doutput=target/effective-pom.xml
~~~

**-Dverbose** thêm comment chỉ ra nguồn gốc các phần tử trong effective POM. File này giúp tìm:

- Spring Boot parent/BOM version đang được áp dụng.
- Dependency versions được quản lý.
- Properties override version.
- Active profiles.
- Maven plugin versions/configuration.
- Execution của Spring Boot repackage.
- Exclusions, scopes và plugin configuration inherited.

Nếu project multi-module và app phụ thuộc module local, hãy build reactor theo quy trình của project trước; effective POM nên được thu thập cho module ứng dụng thực sự được đóng gói. Không chỉ đọc root aggregator rồi kết luận effective configuration của app giống hệt.

### 5.2. Dependency tree dạng JSON

Dùng Maven Dependency Plugin phiên bản 3.11.0 trong ví dụ:

~~~bash
./mvnw -pl app org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose -DoutputType=json -DoutputFile=target/dependency-tree.json
~~~

JSON output được hỗ trợ từ Maven Dependency Plugin 3.7.0 trở lên. **-Dverbose** yêu cầu hiển thị cả node bị omitted do conflict mediation; đây là thông tin hữu ích khi điều tra vì sao một version được chọn.

Với project multi-module có dependency vào module khác trong reactor, chạy từ root và chọn cả module cần thiết:

~~~bash
./mvnw -pl app -am org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose -DoutputType=json -DoutputFile=target/dependency-tree.json
~~~

**-pl app** chọn module ứng dụng, **-am** build các module reactor cần thiết. Nếu tên module hoặc đường dẫn module khác, thay bằng selector đúng của project. Kiểm tra output được tạo trong app/target/ hoặc target directory của module theo working directory thực tế.

### 5.3. Phân biệt graph đầy đủ và runtime graph

Graph đầy đủ giúp nhìn thấy các scope; runtime graph tập trung vào những dependency có thể tham gia runtime:

~~~bash
./mvnw -pl app org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dscope=runtime -Dverbose -DoutputFile=target/runtime-dependency-tree.txt
~~~

Có thể lưu thêm compile/test graph theo mục tiêu điều tra, nhưng phải dùng cùng tham số ở before và after. Không so graph mặc định của một revision với graph runtime-only của revision còn lại.

### 5.4. Đọc kết quả Maven

Ví dụ minh họa cấu trúc output:

~~~text
com.example:catalog-app:jar:1.0.0
+- org.springframework.boot:spring-boot-starter-web:jar:...
|  +- org.springframework:spring-web:jar:...
|  \- com.fasterxml.jackson.core:jackson-databind:jar:...
\- org.springframework.boot:spring-boot-starter-test:jar:...:test
~~~

Các điểm cần so:

- Dependency trực tiếp mới được thêm hoặc bị xóa.
- Dependency transitive mới xuất hiện hoặc biến mất.
- Version được chọn thay đổi.
- Dependency bị omitted do conflict.
- Scope đổi giữa compile/runtime/test/provided.
- Exclusion hoặc optional dependency làm thay đổi nhánh.
- Dependency version bị override so với Boot BOM.
- Nhiều version của cùng artifact xuất hiện ở các module khác nhau.

Maven dùng dependency mediation để chọn version khi có nhiều đường yêu cầu cùng artifact. Dòng verbose như **omitted for conflict with ...** giúp giải thích version bị loại; đừng coi mọi omitted node là lỗi. Cần xác định version được chọn có phù hợp và có regression test tương ứng hay không.

### 5.5. Lệnh điều tra một dependency cụ thể

Ví dụ cần điều tra Jackson:

~~~bash
./mvnw -pl app org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

Đổi includes sang groupId/artifactId cần kiểm tra. Có thể dùng lệnh tương tự cho Spring Framework, Tomcat, Logback, Netty, Hibernate hoặc thư viện nội bộ.

### 5.6. Maven dependency:analyze chỉ là bằng chứng bổ sung

~~~bash
./mvnw -pl app org.apache.maven.plugins:maven-dependency-plugin:3.11.0:analyze
~~~

Goal này tìm dependency khai báo nhưng không dùng hoặc dùng nhưng chưa khai báo theo phân tích bytecode. Nó có thể tạo false positive với reflection, annotation scanning, ServiceLoader, Spring auto-configuration hoặc code được gọi gián tiếp. Dùng để điều tra, không tự động xóa dependency chỉ vì analyzer báo unused.

## 6. Gradle: ghi lại dependency graph và lý do chọn version

Gradle cung cấp task **dependencies** để xem cây dependency và **dependencyInsight** để giải thích một module cụ thể được chọn như thế nào.

### 6.1. Xuất graph theo từng configuration

Tại root Gradle project:

~~~bash
./gradlew :app:dependencies --configuration compileClasspath --console=plain > evidence-compile.txt
./gradlew :app:dependencies --configuration runtimeClasspath --console=plain > evidence-runtime.txt
./gradlew :app:dependencies --configuration testRuntimeClasspath --console=plain > evidence-test-runtime.txt
~~~

Các configuration có ý nghĩa khác nhau:

- **compileClasspath:** dependency cần để compile source chính.
- **runtimeClasspath:** dependency cần khi chạy ứng dụng.
- **testRuntimeClasspath:** dependency dùng để chạy test, bao gồm test framework và runtime dependency của app.

Đối chiếu cùng configuration ở hai revision. Không so compileClasspath trước nâng cấp với runtimeClasspath sau nâng cấp.

### 6.2. dependencyInsight: tại sao version này được chọn?

Ví dụ điều tra Spring Core:

~~~bash
./gradlew :app:dependencyInsight --dependency org.springframework:spring-core --configuration runtimeClasspath
~~~

Hoặc Jackson:

~~~bash
./gradlew :app:dependencyInsight --dependency com.fasterxml.jackson.core:jackson-databind --configuration runtimeClasspath
~~~

Output có thể cho biết:

- Version được yêu cầu trực tiếp hoặc bắc cầu.
- Conflict resolution chọn version nào.
- Constraint/BOM tham gia ra sao.
- Version bị force hoặc selected by rule.
- Module nào kéo dependency vào graph.
- Variant attributes được yêu cầu và cung cấp.

Đây là khác biệt quan trọng so với chỉ nhìn dòng implementation trong build.gradle: dòng khai báo không thể hiện đầy đủ kết quả resolution.

### 6.3. Đọc các dấu hiệu trong Gradle graph

Gradle dependency report dùng ký hiệu như:

- **(*)**: subtree dependency lặp đã được mở rộng ở nơi khác.
- **(c)**: dependency constraint, không phải một dependency artifact độc lập.
- **(n)**: dependency/configuration không thể resolve.

Một node lặp với (*) không có nghĩa dependency bị loại. Một constraint (c) không có nghĩa archive chứa thêm một JAR. Đọc graph cùng dependencyInsight để xác định version thực tế.

### 6.4. Dependency locking

Khi cần giữ dependency resolution ổn định, Gradle hỗ trợ dependency locking. Ví dụ trong build.gradle:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Tạo hoặc cập nhật lock state khi resolve các configuration:

~~~bash
./gradlew :app:dependencies --write-locks
~~~

Lockfile được sinh ra phải được review và commit theo quy trình dự án. Khi nâng Spring Boot/BOM, lock state có thể cần cập nhật vì các version được quản lý thay đổi. Đừng sửa lockfile bằng tay để che conflict; hãy resolve graph, hiểu thay đổi và ghi lại lock state từ build thành công.

**Giới hạn:** dependency locking giúp cố định version đã resolve, nhưng không biến một artifact SNAPSHOT/changing module có cùng tọa độ thành immutable bytes. Với dependency thay đổi nội dung theo thời gian, cần repository/version policy và checksum phù hợp.

### 6.5. So sánh version catalog, platform và constraints

Nếu project dùng **libs.versions.toml**, platform/BOM, dependency constraints hoặc resolution rules, hãy lưu các file đó trong evidence. Một thay đổi version catalog có thể làm đổi nhiều configuration. dependencyInsight giúp xác định version được chọn, còn build script/lockfile cho biết policy đã khai báo.

## 7. Đọc và diễn giải dependency graph sau nâng cấp

### 7.1. Phân loại thay đổi

| Loại thay đổi | Ví dụ | Hành động |
| --- | --- | --- |
| Version tăng theo BOM | Spring Framework hoặc Jackson được Boot quản lý | Kiểm tra compatibility và regression tests |
| Dependency mới | Một starter kéo thêm library bắc cầu | Xác định lý do, runtime footprint và security impact |
| Dependency bị xóa | Plugin/starter mới không còn kéo module cũ | Xác nhận code path không cần nữa |
| Conflict được giải quyết khác | Hai nhánh yêu cầu version khác nhau | Dùng dependencyInsight/verbose tree tìm nguyên nhân |
| Scope/configuration thay đổi | Dependency chuyển compile sang runtime hoặc test | Kiểm tra compile/runtime classpath và packaging |
| Override ngoài BOM | POM property/Gradle constraint ép version | Xác nhận có chủ đích, kiểm tra tương thích |
| Platform-specific variant | Gradle chọn variant theo JVM/OS attributes | So sánh cùng environment/attributes |

### 7.2. Không chỉ đếm số dependency

Số lượng node giảm không đồng nghĩa dependency graph tốt hơn. Một dependency mới có thể kéo thêm nhiều thư viện nhưng là thay đổi hợp lệ. Ngược lại, một library bị bỏ khỏi runtime graph có thể khiến ứng dụng thiếu class khi chạy.

Hãy xem:

- GAV và version được chọn.
- Quan hệ direct/transitive.
- Runtime vs test/compile scope.
- Selection reason và conflict.
- Dependency bị exclude/optional.
- Module nào sử dụng.
- Library có nằm trong artifact cuối không.
- Có vulnerability/license policy mới cần xử lý không.

### 7.3. Đối chiếu dependency graph với BOM

Spring Boot BOM quản lý một bộ version tương thích. Nếu after graph có một library khác version BOM dự kiến, kiểm tra:

- Explicit version trong dependency declaration.
- Property override.
- Parent/BOM import order.
- Dependency management từ corporate parent.
- Gradle platform/enforcedPlatform/constraint.
- Resolution strategy hoặc component selection rule.
- Lockfile cũ chưa được cập nhật.

Không ép version về giá trị của BOM một cách máy móc nếu có lý do compatibility/security đã được phê duyệt; nhưng mọi override cần được ghi rõ và test.

## 8. So sánh nội dung executable JAR/WAR

Dependency graph mô tả resolution. Archive inspection xác nhận những gì thực sự được đóng gói.

### 8.1. Liệt kê toàn bộ JAR entries

Maven:

~~~bash
jar tf target/catalog-app-1.0.0.jar | sort > evidence-jar-entries.txt
~~~

Gradle:

~~~bash
jar tf build/libs/catalog-app-1.0.0.jar | sort > evidence-jar-entries.txt
~~~

Làm việc trong thư mục evidence riêng cho từng revision. jar tf liệt kê nội dung ZIP/JAR mà không giải nén hay sửa archive.

### 8.2. So sánh danh sách nested libraries

Với executable Spring Boot JAR:

~~~bash
jar tf target/catalog-app-1.0.0.jar | grep '^BOOT-INF/lib/.*\.jar$' | sed 's#BOOT-INF/lib/##' | sort > evidence-runtime-libraries.txt
~~~

Làm tương tự cho bản after. Sau đó diff:

~~~bash
diff -u before/runtime-libraries.txt after/runtime-libraries.txt
~~~

Đây là phép so sánh **tên nested JAR**. Nó giúp thấy library nào được thêm, xóa hoặc đổi version. Nếu tên file không đổi nhưng bytes bên trong khác, cần so checksum của nested JAR sau khi trích xuất.

### 8.3. So sánh manifest

~~~bash
unzip -p target/catalog-app-1.0.0.jar META-INF/MANIFEST.MF > evidence-manifest.txt
~~~

Manifest executable Boot JAR thường chứa:

- **Main-Class:** Boot launcher.
- **Start-Class:** main class ứng dụng.
- Build metadata hoặc attributes do plugin bổ sung.

Sau nâng cấp, launcher class có thể thay đổi theo Boot version. Điều quan trọng là manifest vẫn chỉ tới launcher hợp lệ của archive và Start-Class vẫn là entry point mong muốn.

Nếu không có unzip, dùng jar xf trong thư mục tạm để trích META-INF/MANIFEST.MF, sau đó đọc file. Không giải nén vào thư mục đang chứa file cùng tên cần giữ.

### 8.4. Kiểm tra application classes và resources

Trong Boot JAR, application code thường nằm dưới:

~~~text
BOOT-INF/classes/
~~~

Dependency JAR thường nằm dưới:

~~~text
BOOT-INF/lib/
~~~

So sánh những entry quan trọng:

- Main class và các package ứng dụng.
- application.properties/application.yml và profile resources.
- Migration scripts như Flyway/Liquibase.
- Template, static assets và resource cần thiết.
- META-INF/services/ nếu dùng Java ServiceLoader.
- Spring auto-configuration metadata.
- BOOT-INF/classpath.idx hoặc BOOT-INF/layers.idx nếu archive được cấu hình tạo các file này.

Không yêu cầu mọi archive đều có classpath.idx hoặc layers.idx; chúng phụ thuộc packaging configuration. Khi file có mặt ở baseline nhưng biến mất sau nâng cấp, hãy tìm hiểu nguyên nhân thay vì tự kết luận lỗi.

### 8.5. WAR có cấu trúc khác JAR

Nếu sản phẩm là WAR, kiểm tra:

- **WEB-INF/classes/**: application classes/resources.
- **WEB-INF/lib/**: dependencies của web application.
- **WEB-INF/lib-provided/**: có thể chứa provided dependencies trong executable Spring Boot WAR.
- **META-INF/MANIFEST.MF**: manifest của archive.

Không áp dụng lệnh lọc BOOT-INF/lib cho WAR. So sánh archive theo packaging type và đúng contract triển khai.

## 9. Hash và kích thước artifact: dùng đúng mục đích

### 9.1. Tính SHA-256

Linux/macOS:

~~~bash
sha256sum target/catalog-app-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "target\catalog-app-1.0.0.jar"
~~~

Lưu hash của before và after cùng tên artifact, commit SHA và build metadata.

### 9.2. Hash khác nhau không tự động là lỗi

Sau nâng cấp, whole-JAR SHA-256 gần như chắc chắn thay đổi nếu dependency version, manifest, build metadata hoặc timestamp thay đổi. Hash được dùng để:

- Xác nhận file được tải/triển khai chính là file đã kiểm thử.
- Nhận diện artifact cụ thể.
- Phát hiện file bị thay đổi ngoài dự kiến giữa các bước.
- Lưu release evidence.

Không dùng điều kiện **hash before phải bằng hash after** để nghiệm thu một nâng cấp dependency. Hai archive có dependency version khác nhau phải có bytes khác nhau.

### 9.3. So sánh kích thước

Ghi kích thước file và nested libraries. Archive lớn hơn có thể do dependency mới hoặc resource được thêm; archive nhỏ hơn có thể do loại dependency, thay đổi compression hoặc resource bị bỏ. Kích thước chỉ là chỉ báo, không phải quality gate độc lập.

## 10. Kiểm tra bytecode và tương thích Java

Nếu nâng JDK/compiler, kiểm tra bytecode target của application classes:

~~~bash
javap -verbose -classpath target/classes com.example.catalog.CatalogApplication
~~~

Tìm dòng **major version**. Với Java 17, class file major version là **61**. Nếu mục tiêu vẫn là Java 17 mà application class có major version cao hơn, build có thể đã dùng target/toolchain không đúng.

Không suy luận tất cả nested dependencies phải có major version 61. Dependency có thể hỗ trợ nhiều Java version, chứa multi-release JAR hoặc được biên dịch bằng target khác. Hãy kiểm tra application bytecode và compatibility của từng library có yêu cầu đặc biệt.

Nếu nâng Spring Boot nhưng giữ Java 17, xác nhận:

- Build tool và plugin hỗ trợ JDK 17.
- Compiler release/Gradle toolchain vẫn đúng.
- Runtime production sử dụng JRE tương thích.
- Dependency mới không yêu cầu Java version cao hơn mức runtime được hỗ trợ.
- Native library/agent có binary phù hợp OS/architecture.

## 11. So sánh kết quả test sau nâng cấp

### 11.1. Maven Surefire và Failsafe

Chạy:

~~~bash
./mvnw -B -ntp clean verify
~~~

- **Surefire** thường chạy unit tests trong phase test.
- **Failsafe** chạy integration tests nếu project đã cấu hình plugin và bind goals phù hợp vào lifecycle integration-test/verify.
- **verify** chạy các phase trước đó và các verification goals được cấu hình.

Các report thường nằm tại:

~~~text
target/surefire-reports/
target/failsafe-reports/
~~~

JUnit XML report có các thuộc tính quan trọng như tests, failures, errors, skipped và thời gian chạy. So sánh cả hai thư mục nếu dự án có integration tests.

Không giả định mvn verify tự chạy integration tests nếu POM chưa cấu hình Failsafe hoặc test profile tương ứng. Kiểm tra effective POM và log thực thi plugin.

### 11.2. Gradle Test

Chạy:

~~~bash
./gradlew --no-daemon clean check bootJar
~~~

- **test** chạy unit tests.
- **check** gom test và các verification tasks được gắn vào lifecycle.
- **bootJar** tạo executable Spring Boot JAR.

Reports thường nằm tại:

~~~text
build/test-results/test/
build/reports/tests/test/
~~~

Nếu dự án có integration test task riêng, xác nhận task đó được nối vào check hoặc gọi rõ ràng. Một task tồn tại nhưng không nằm trong task graph thì không tự chạy chỉ vì file test đã có trong repository.

### 11.3. So sánh test count, failure, error và skipped

Tạo bảng before/after:

| Chỉ số | Before | After | Cách đánh giá |
| --- | --- | --- | --- |
| Test suites | Số suite trong report | Số suite trong report | Chênh lệch cần giải thích |
| Tests executed | Tổng tests | Tổng tests | Không giảm âm thầm |
| Failures | Assertion failures | Assertion failures | Điều tra từng regression |
| Errors | Exception/setup errors | Exception/setup errors | Kiểm tra API/config/runtime |
| Skipped | Test bị skip | Test bị skip | Xác nhận lý do skip có chủ đích |
| Duration | Thời gian chạy | Thời gian chạy | Điều tra regression hiệu năng lớn |

**Test pass nhưng số lượng giảm** có thể là tín hiệu nguy hiểm: test source set không được nhận, profile thay đổi, filter loại test hoặc engine không còn chạy test cũ. So sánh report names và suite list, không chỉ nhìn chữ BUILD SUCCESSFUL.

### 11.4. Test có thể fail sau nâng cấp vì lý do gì?

- Spring Framework thay đổi validation, binding, transaction hoặc lifecycle.
- Jackson thay đổi serialization/deserialization behavior.
- Hibernate thay đổi SQL generation hoặc type mapping.
- Security framework thay đổi default configuration hoặc matcher behavior.
- Logging bridge/backend thay đổi classpath hoặc binding.
- Servlet/container API thay đổi namespace/behavior.
- JUnit/Surefire/Gradle test engine thay đổi discovery hoặc extension behavior.
- Database driver thay đổi default, timezone, SSL hoặc transaction behavior.

Phân loại failure theo nhóm: compile error, test discovery, assertion, context startup, integration/environment, linkage/classloading hoặc runtime behavior. Sửa nguyên nhân, không chỉ nới assertion để làm test xanh.

### 11.5. Kiểm tra flaky tests

Nếu một test chỉ fail ngẫu nhiên, lưu log, test report, seed/timezone và environment. Chạy lại có kiểm soát để xác định flaky test, nhưng không xóa lần fail đầu khỏi evidence. Phân biệt:

- Regression ổn định: lặp lại ở cùng điều kiện.
- Flaky: không ổn định giữa các lần chạy.
- Environment failure: service container, network, clock, credentials hoặc resource.
- Test discovery change: test không chạy hoặc bị skip.

## 12. Runtime smoke test và contract test

Test suite xanh chưa chứng minh executable artifact chạy được trong môi trường mục tiêu. Chạy artifact sau khi package:

~~~bash
java -jar target/catalog-app-1.0.0.jar
~~~

Đối với ứng dụng command-line, kiểm tra output/exit code. Đối với web service:

1. Khởi động JAR trong test environment.
2. Chờ readiness/health endpoint theo timeout hợp lý.
3. Gọi endpoint quan trọng bằng dữ liệu test.
4. Xác nhận status code, response contract và log.
5. Dừng process sạch sẽ.

Nếu có Spring Boot Actuator, có thể kiểm tra health endpoint đã được bật và expose đúng theo security policy. Không giả định mọi project đều có /actuator/health.

Nên bổ sung consumer/API compatibility tests nếu nâng cấp có thể ảnh hưởng contract với hệ thống khác. Dependency graph và JAR structure không phát hiện được mọi thay đổi về JSON schema, SQL behavior hoặc HTTP semantics.

## 13. Ví dụ Java 17 tối thiểu để xác minh app và test

### 13.1. Application class

File **src/main/java/com/example/catalog/CatalogApplication.java**:

~~~java
package com.example.catalog;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    CommandLineRunner upgradeProof() {
        return args -> System.out.println("UPGRADE_SMOKE_OK");
    }
}
~~~

Đây là Java 17 application class hoàn chỉnh. Khi context khởi động thành công, code in dòng:

~~~text
UPGRADE_SMOKE_OK
~~~

Spring Boot có thể in banner và log khác; dòng trên là output do CommandLineRunner tạo.

### 13.2. Test context

File **src/test/java/com/example/catalog/CatalogApplicationTests.java**:

~~~java
package com.example.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
public class CatalogApplicationTests {

    @Test
    void contextLoads() {
    }
}
~~~

Test này chỉ xác minh context khởi tạo được. Dự án thực tế phải kiểm tra business behavior, repository, HTTP/API, security, database migrations và integrations quan trọng. Không coi một contextLoads test là bằng chứng tương thích toàn hệ thống.

## 14. Quy trình lưu evidence và diff before/after

Mỗi revision nên có thư mục evidence riêng:

~~~text
upgrade-evidence/
├── before/
│   ├── environment.txt
│   ├── effective-pom.xml
│   ├── dependency-tree.json
│   ├── runtime-libraries.txt
│   ├── jar-entries.txt
│   ├── manifest.txt
│   ├── tests/
│   └── artifact.sha256
└── after/
    ├── environment.txt
    ├── effective-pom.xml
    ├── dependency-tree.json
    ├── runtime-libraries.txt
    ├── jar-entries.txt
    ├── manifest.txt
    ├── tests/
    └── artifact.sha256
~~~

Tên file tùy project. Điều quan trọng là giữ output của mỗi revision riêng và không ghi đè baseline bằng clean của lần build sau.

Diff những file có ý nghĩa:

~~~bash
diff -u upgrade-evidence/before/runtime-libraries.txt upgrade-evidence/after/runtime-libraries.txt
diff -u upgrade-evidence/before/jar-entries.txt upgrade-evidence/after/jar-entries.txt
diff -u upgrade-evidence/before/manifest.txt upgrade-evidence/after/manifest.txt
~~~

Đối với dependency graph JSON, dùng JSON-aware diff nếu thứ tự serialization khác nhau nhưng nội dung graph tương đương. Đối với text graph, giữ nguyên command và plugin version; nếu output có path hoặc timestamp, chuẩn hóa phần biến động trước khi diff nhưng không xóa thông tin version/selection reason.

**Không normalize mất bằng chứng.** Đừng xóa version, scope, selected reason, classifier hoặc file path chỉ để diff ngắn hơn.

## 15. Ma trận quyết định sau khi so sánh

| Kết quả | Diễn giải | Quyết định |
| --- | --- | --- |
| Graph thay đổi có lý do, archive đúng, test pass | Upgrade có bằng chứng nhất quán | Có thể tiếp tục release gate |
| Graph đổi version nhưng runtime JAR thiếu library cần thiết | Packaging/exclusion hoặc scope có vấn đề | Block release, sửa packaging |
| Graph gần như không đổi nhưng test fail | Có thể là behavior/plugin/JDK/test engine change | Điều tra test/runtime trước |
| JAR entries đổi nhưng graph không giải thích được | Resource/generated output/packaging/plugin thay đổi | Kiểm tra manifest, plugin và build inputs |
| Test pass nhưng test count giảm | Test discovery/filter/skip thay đổi | Block cho tới khi giải thích được |
| Whole-JAR hash đổi, mọi kiểm tra khác pass | Thường là kết quả bình thường của upgrade | Lưu hash mới, không coi hash mismatch là regression |
| Runtime smoke test fail dù unit tests pass | Artifact hoặc môi trường runtime khác test classpath | Điều tra executable package và configuration |
| Version override nằm ngoài Boot BOM không có lý do | Dependency alignment không rõ ràng | Review override và compatibility tests |

### 15.1. Điều kiện chấp nhận tối thiểu

- Dependency graph before/after đã lưu và mọi thay đổi quan trọng được giải thích.
- Không có dependency conflict/override ngoài chủ đích.
- Runtime dependency graph phù hợp với libraries trong archive.
- Manifest, launcher và application Start-Class đúng.
- Application classes/resources cần thiết có trong artifact.
- Test suites quan trọng đã chạy, không bị skip âm thầm.
- Failure/error bằng 0 hoặc có exception đã được chấp thuận bằng quy trình rõ ràng.
- Smoke/integration tests chạy trong môi trường phù hợp.
- SHA-256 của artifact after được lưu và dùng để xác minh chính file sẽ triển khai.
- Security/license/SBOM checks được chạy theo policy release của tổ chức.

Không nên tự đặt một ngưỡng số dependency tăng/giảm tối đa dùng cho mọi project. Mỗi thay đổi cần đánh giá theo vai trò của library và rủi ro runtime.

## 16. Các lỗi thường gặp khi so sánh sau nâng cấp

**1. So dependency declarations thay vì resolved graph.** POM/build.gradle không thể hiện toàn bộ dependency bắc cầu. Dùng dependency:tree hoặc Gradle dependencies.

**2. Không lưu effective POM.** Parent, BOM và active profiles có thể thay đổi version thực tế. Lưu effective-pom trước/sau.

**3. Maven graph không có omitted nodes.** Thiếu -Dverbose khiến khó nhìn conflict mediation. Bật verbose khi điều tra.

**4. Gradle chỉ xem dependency trực tiếp.** Version được chọn có thể đến từ transitive path, constraint hoặc rule. Dùng dependencyInsight.

**5. So sánh nhầm configuration.** compileClasspath khác runtimeClasspath/testRuntimeClasspath. So đúng loại graph.

**6. Chỉ nâng Spring Boot nhưng không kiểm tra plugin version.** Maven/Gradle plugin cũng ảnh hưởng packaging. Ghi version của từng plugin.

**7. Override version ngoài BOM mà không có test.** Dependency có thể lệch khỏi bộ đã được Boot kiểm thử. Ghi lý do và test tương thích.

**8. Lockfile chưa cập nhật sau nâng cấp.** Gradle có thể tiếp tục dùng version cũ hoặc báo conflict. Review và ghi lock state có chủ đích.

**9. Dùng SNAPSHOT mutable trong phép so sánh.** Cùng tọa độ có thể trả bytes khác giữa hai lần build. Dùng release immutable hoặc ghi checksum thực tế.

**10. Build before và after bằng JDK khác nhau ngoài ý muốn.** Chênh lệch bytecode/test có thể không đến từ Spring Boot. Cố định và ghi JDK.

**11. Chạy profile Maven khác nhau.** Dependency graph và test set có thể khác. Lưu active profiles và command đầy đủ.

**12. Chạy Gradle task khác nhau.** bootJar không tự chứng minh check đã chạy. Dùng clean check bootJar hoặc task graph được định nghĩa rõ.

**13. Chạy mvn package rồi cho rằng integration test đã chạy.** Failsafe thường cần lifecycle đến verify và cấu hình plugin. Kiểm tra effective POM và reports.

**14. Test count giảm nhưng build vẫn xanh.** Có thể test bị skip hoặc không được discover. So XML reports và test filters.

**15. So hash toàn JAR và kết luận nâng cấp thất bại.** Dependency bytes đã thay đổi. Dùng hash để nhận diện artifact, không yêu cầu before/after giống nhau.

**16. Chỉ xem jar tf mà không kiểm tra manifest.** Archive có entries nhưng Start-Class/launcher sai. Đọc META-INF/MANIFEST.MF.

**17. So danh sách BOOT-INF/lib với toàn bộ dependency graph.** Graph chứa test/provided/compile scopes; chỉ runtime package phù hợp được đưa vào executable archive. So đúng scope.

**18. Library bị loại khỏi graph nhưng không biết do exclusion.** Kiểm tra dependency tree/insight và dependency declarations.

**19. Nested JAR cùng tên nhưng bytes khác.** Tên file không đủ chứng minh nội dung. Trích nested archive và tính checksum khi cần.

**20. Artifact bị ghi đè giữa hai lần build.** Lưu baseline và candidate trong thư mục riêng hoặc worktree riêng.

**21. Dùng report cũ còn sót sau clean/build.** Kiểm tra timestamp, run ID và commit SHA của report; clean trước mỗi lần capture.

**22. Không chạy runtime smoke test.** Unit tests có thể không khởi động executable artifact. Chạy đúng JAR/WAR sau package.

**23. App chạy trên test classpath nhưng fail từ java -jar.** Nested dependency, profile hoặc resource có thể khác. Kiểm tra archive thực tế.

**24. Không kiểm tra class file version.** Build có thể vô tình target JDK mới hơn runtime. Dùng javap và xác nhận Java target.

**25. Không kiểm tra auto-configuration/service metadata.** Dependency upgrade có thể thay metadata hoặc ServiceLoader resources. Inspect nested JAR liên quan khi behavior thay đổi.

**26. Test failure bị bỏ qua bằng skip flag.** -DskipTests, maven.test.skip hoặc Gradle -x test làm mất bằng chứng. Ghi rõ mọi skip và không coi đó là test pass.

**27. Dùng test report tổng hợp mà bỏ qua test class.** Một suite có thể fail trong khi tổng quan bị che bởi aggregation. Kiểm tra XML từng module.

**28. Không phân biệt regression với môi trường.** Database/network/credentials/timezone có thể làm test fail. Ghi environment và tái hiện trong cùng điều kiện.

**29. Chỉ kiểm tra số dependency.** Ít hơn không đồng nghĩa tốt hơn. Đánh giá version, scope, selection reason và runtime impact.

**30. Release artifact khác file đã test.** Build lại trong job deploy hoặc copy nhầm file. Deploy đúng artifact đã upload, xác minh checksum và lưu commit provenance.

## 17. Checklist nghiệm thu nâng cấp

- [ ] Có commit before và after rõ ràng.
- [ ] Chỉ thay đổi nâng cấp thuộc phạm vi đã xác định.
- [ ] JDK, OS, build wrapper, profiles và environment được ghi lại.
- [ ] Maven: lưu effective POM và dependency tree.
- [ ] Gradle: lưu compile/runtime/test dependency reports.
- [ ] Các conflict, override, exclusions và transitive changes đã được giải thích.
- [ ] Boot BOM và plugin versions đã được xác nhận.
- [ ] Lockfile được review/cập nhật nếu project dùng dependency locking.
- [ ] Artifact before/after được lưu riêng.
- [ ] JAR/WAR entry lists đã được diff.
- [ ] Nested runtime libraries đã được so sánh.
- [ ] Manifest launcher và Start-Class đúng.
- [ ] Resource/config/migration files quan trọng vẫn có trong archive.
- [ ] Bytecode target phù hợp JDK runtime.
- [ ] Surefire/Failsafe hoặc Gradle test reports đã được lưu.
- [ ] Test counts, failures, errors và skipped đã được so sánh.
- [ ] Integration tests và smoke tests chạy trên artifact sau nâng cấp.
- [ ] SHA-256 của artifact mới được lưu.
- [ ] Security/license/SBOM scan theo release policy.
- [ ] Artifact triển khai chính là file đã qua test và checksum verification.
- [ ] Kết luận release dựa trên bằng chứng, không dựa vào riêng BUILD SUCCESSFUL.

## 18. Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Build Systems and Dependency Management: https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html
- Spring Boot 3.3 — Maven Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/
- Spring Boot 3.3 — Maven Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin Packaging: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Apache Maven Dependency Plugin — dependency:tree: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html
- Apache Maven Dependency Plugin — tree output formats: https://maven.apache.org/plugins/maven-dependency-plugin/examples/tree-mojo.html
- Apache Maven Help Plugin — effective-pom: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Gradle 8.5 — Viewing and Debugging Dependencies: https://docs.gradle.org/8.5/userguide/viewing_debugging_dependencies.html
- Gradle 8.5 — Dependency Locking: https://docs.gradle.org/8.5/userguide/dependency_locking.html
- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven Surefire — Reports: https://maven.apache.org/surefire/maven-surefire-plugin/
- Gradle 8.5 — Java Testing: https://docs.gradle.org/8.5/userguide/java_testing.html
- Oracle Java 17 — jar tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
- Oracle Java 17 — javap tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html

**Kết luận:** So sánh nâng cấp Spring Boot phải dựa trên ba nguồn bằng chứng: **dependency graph đã resolve, nội dung artifact đã đóng gói và kết quả test/runtime sau build**. Hãy giữ môi trường và lệnh build nhất quán, lưu baseline riêng, giải thích mọi thay đổi version/scope/packaging, xác nhận manifest và nested libraries, rồi so sánh test counts cùng failures/skips. SHA-256 xác định đúng file đã kiểm thử và triển khai; nó không phải yêu cầu hai phiên bản trước/sau phải có bytes giống nhau.