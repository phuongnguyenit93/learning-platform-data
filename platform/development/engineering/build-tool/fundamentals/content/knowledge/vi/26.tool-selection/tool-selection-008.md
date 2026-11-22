# Giữ nguyên hợp đồng đầu ra và kiểm chứng sau chuyển đổi

Khi chuyển một dự án Java từ Maven sang Gradle, từ Gradle sang Maven hoặc sang một hệ thống build khác, công việc không kết thúc ở chỗ lệnh build mới chạy thành công. Build tool là một phần của quy trình tạo và phân phối phần mềm. Nó quyết định artifact nào được tạo, tên và tọa độ của artifact, nội dung JAR, metadata dependency, cách chạy test, cách publish và nhiều thông tin mà consumer hoặc hệ thống vận hành đang dựa vào.

Một dự án có thể biên dịch thành công sau chuyển đổi nhưng vẫn phá vỡ hợp đồng đầu ra: tên JAR đổi, classifier biến mất, resource bị lọc mất, manifest thiếu `Main-Class`, POM không còn dependency cần thiết, sources JAR không được publish hoặc task release bỏ qua integration test. Những thay đổi này có thể làm ứng dụng downstream không resolve được dependency, runtime không khởi động hoặc pipeline phát hành tạo ra artifact không còn tương thích.

Vì vậy, mục tiêu của chuyển đổi là **giữ nguyên những hành vi đầu ra mà consumer và quy trình phát hành cần**, đồng thời kiểm chứng chúng bằng bằng chứng có thể lặp lại. Bài học này trình bày cách xác định hợp đồng đầu ra, lập baseline trước chuyển đổi, ánh xạ cấu hình giữa build tool, so sánh artifact và kiểm tra hành vi sau chuyển đổi.

## 1. Hợp đồng đầu ra của build là gì?

Hợp đồng đầu ra (output contract) là tập hợp những đặc điểm của artifact và quy trình build mà consumer, developer, CI, hệ thống triển khai hoặc quy trình phát hành đang phụ thuộc vào.

Hợp đồng này rộng hơn việc “tạo được một file JAR”. Nó có thể bao gồm:

- Tọa độ artifact: group, artifact/module name, version, packaging hoặc extension.
- Tên file, classifier và tập artifact phụ được phát hành.
- Nội dung archive: class, resource, manifest, service descriptor và metadata.
- API/ABI mà consumer sử dụng.
- Dependency metadata trong POM hoặc Gradle Module Metadata.
- Cấu hình runtime, entry point và cách khởi chạy.
- Test, verification, code analysis và các gate bắt buộc.
- Repository đích, publication, checksum, chữ ký và provenance.
- Quy tắc versioning, snapshot/release và tính bất biến của artifact.
- Khả năng tái lập build và thông tin truy vết về source commit/CI.

Ví dụ, một thư viện Java đang được consumer khai báo như sau:

```groovy
dependencies {
    implementation 'com.example.orders:order-api:2.3.0'
}
```

Consumer phụ thuộc vào tọa độ `com.example.orders:order-api:2.3.0` và metadata của module đó. Nếu build tool mới publish artifact với `artifactId` thành `orders-api-core`, dù JAR chứa cùng class, consumer cũ vẫn không resolve được tọa độ ban đầu.

Tương tự, một ứng dụng được triển khai bằng:

```bash
java -jar order-service-2.3.0.jar
```

có thể phụ thuộc vào tên file, manifest `Main-Class` và dependency đã được đóng gói. Thay đổi bất kỳ thành phần nào trong hợp đồng này đều có thể làm hỏng deployment.

## 2. Phân biệt đầu ra nội bộ và hợp đồng công khai

Không phải mọi file trong thư mục build đều là hợp đồng công khai. Một số output chỉ là dữ liệu trung gian để task tiếp theo sử dụng; một số khác được publish hoặc chuyển sang hệ thống khác.

| Nhóm đầu ra | Ví dụ | Mức độ phụ thuộc thường gặp |
|---|---|---|
| Artifact công khai | JAR, WAR, POM, Gradle Module Metadata | Consumer, repository và deployment. |
| Artifact bổ sung | Sources JAR, Javadoc JAR, test fixture JAR | Developer, IDE, consumer hoặc quy trình kiểm tra. |
| Nội dung archive | Class, resource, manifest, `META-INF/services` | Runtime, framework và classloader. |
| Dependency metadata | Transitive dependencies, scopes, variants, capabilities | Build của consumer. |
| Verification result | Test report, coverage, static analysis report | CI gate và release approval. |
| Release metadata | Checksum, signature, SBOM, provenance | Security, compliance và vận hành. |
| Output trung gian | Generated source, compiled classes, task state | Các task trong cùng build. |

Khi chuyển đổi, hãy xác định output nào là contract mà bên ngoài đang sử dụng. Có thể thay đổi thư mục output nội bộ nếu không ảnh hưởng consumer và task tích hợp, nhưng phải giữ hoặc chủ động version hóa những thay đổi đối với artifact công khai.

### 2.1. Consumer là ai?

Một output có thể có nhiều consumer:

- Module khác trong cùng multi-module build.
- Dự án khác tải dependency từ artifact repository.
- Ứng dụng runtime hoặc container image.
- IDE dùng sources/Javadoc và metadata.
- CI job downstream lấy artifact từ job upstream.
- Hệ thống deployment, signing hoặc vulnerability scanning.
- Nhóm vận hành cần biết version, commit và cách khởi chạy.

Hãy xác định consumer thực tế trước khi quyết định một thay đổi có tương thích hay không. Một file có vẻ “chỉ là metadata” với build team có thể là đầu vào bắt buộc của công cụ khác.

## 3. Những phần cần giữ ổn định khi đổi build tool

### 3.1. Artifact coordinates và tên file

Với Maven, cần giữ các trường GAV và packaging nếu consumer đang dùng chúng:

```xml
<groupId>com.example.orders</groupId>
<artifactId>order-api</artifactId>
<version>2.3.0</version>
<packaging>jar</packaging>
```

Với Gradle, các giá trị tương ứng được cấu hình qua `group`, `name`/`artifactId` của publication và `version`:

```groovy
group = 'com.example.orders'
version = '2.3.0'

publishing {
    publications {
        create('mavenJava', MavenPublication) {
            from components.java
            artifactId = 'order-api'
        }
    }
}
```

Không nên dựa vào tên project hoặc tên thư mục để suy ra artifact ID. Hãy cấu hình rõ nếu tên module công khai cần khác tên project nội bộ.

### 3.2. Classifier và extension

Một module có thể publish nhiều artifact cùng tọa độ version nhưng khác classifier hoặc extension:

```text
order-api-2.3.0.jar
order-api-2.3.0-sources.jar
order-api-2.3.0-javadoc.jar
order-api-2.3.0-tests.jar
```

Nếu build tool mới chỉ publish JAR chính mà bỏ sources/Javadoc/test fixture artifact, consumer hoặc quy trình downstream có thể bị ảnh hưởng. Ghi nhận rõ classifier, extension và cách tạo từng artifact.

### 3.3. Nội dung JAR/WAR

Giữ các thành phần cần thiết:

- Class đã biên dịch và package path.
- Resource của main/test theo đúng phạm vi.
- `META-INF/services` và metadata framework.
- Manifest attributes và main class.
- License/NOTICE và metadata module khi cần.
- Multi-release entries nếu artifact hỗ trợ nhiều Java runtime.

Không chỉ so sánh kích thước file. Một JAR có kích thước gần như cũ vẫn có thể thiếu class hoặc resource quan trọng.

### 3.4. Dependency metadata

POM hoặc Gradle Module Metadata có thể mô tả dependency transitive, scope/configuration, variant, optional dependency, exclusions và capabilities. Nếu build tool mới publish metadata khác, consumer có thể resolve classpath khác dù JAR chính không thay đổi.

Đặc biệt cần xem:

- Dependency `api` so với `implementation` trong Gradle.
- Scope `compile`, `runtime`, `provided`, `test` trong Maven.
- Optional dependency và exclusions.
- Version constraints, BOM/platform và dependency management.
- Gradle variants, attributes và capabilities.
- Artifact classifiers và publication component.

## 4. Lập baseline trước khi chuyển đổi

Baseline là hồ sơ ghi lại hành vi hiện tại của build trước khi thay đổi. Không nên dựa vào trí nhớ hoặc chỉ đọc build script; cần ghi nhận đầu ra thực tế từ một revision xác định.

Một baseline hữu ích có thể gồm:

| Nhóm | Bằng chứng cần lưu |
|---|---|
| Source revision | Commit SHA, tag/ref và trạng thái working tree. |
| Toolchain | JDK, Maven/Gradle version, plugin version và OS. |
| Build commands | Các lệnh compile, test, package, verify và publish đang dùng. |
| Artifact inventory | Tên file, tọa độ, classifier, extension và digest. |
| Archive inventory | Danh sách class/resource, manifest và service descriptors. |
| Dependency graph | Dependency trực tiếp/transitive và metadata được publish. |
| Test behavior | Test suites, report, số lượng pass/fail/skip và profile. |
| Release behavior | Repository, snapshot/release policy, signing và checksum. |
| CI behavior | Workflow, required checks, artifact handoff và retention. |

Baseline nên được tạo từ build sạch và revision đã xác định. Nếu artifact hiện tại đã được publish, tải artifact từ repository về để so sánh với file local; đừng giả định file local chính là file consumer đang nhận.

### 4.1. Ghi nhận các lệnh build thực tế

Ví dụ với Maven:

```bash
./mvnw clean verify
./mvnw package
./mvnw deploy
```

Ví dụ với Gradle:

```bash
./gradlew clean build
./gradlew check
./gradlew publish
```

Không phải dự án nào cũng dùng tất cả lệnh trên. Hãy ghi đúng lệnh CI và developer đang sử dụng, cùng profile, property, environment và task/goal bổ sung.

### 4.2. Lưu inventory artifact

Một inventory đơn giản có thể ghi:

```text
groupId:       com.example.orders
artifactId:    order-api
version:       2.3.0
packaging:     jar
files:
  - order-api-2.3.0.jar
  - order-api-2.3.0-sources.jar
  - order-api-2.3.0-javadoc.jar
  - order-api-2.3.0.pom
```

Nếu project publish Gradle Module Metadata, hãy ghi cả `.module` file. Nếu có SBOM, signature hoặc provenance, ghi tên và vị trí của chúng.

## 5. Chuyển đổi không có nghĩa là sao chép cú pháp

Maven và Gradle có mô hình khác nhau. Khi chuyển đổi, cần ánh xạ **ý nghĩa và hành vi**, không chỉ chuyển từng đoạn XML sang Groovy/Kotlin hoặc ngược lại.

Ví dụ:

| Mục tiêu | Maven | Gradle |
|---|---|---|
| Khai báo dependency | `<dependencies>` | `dependencies {}` |
| Quản lý version tập trung | `dependencyManagement`/BOM | Platform/constraints/version catalog |
| Java source roots | `<sourceDirectory>` và plugin | `sourceSets` |
| Resource filtering | Maven Resources Plugin | `processResources` và `expand`/filter |
| Unit tests | Surefire | `Test` task |
| Integration tests | Failsafe/profile/plugin | Source set và Test task riêng hoặc plugin |
| Publish Maven artifact | `distributionManagement`/Deploy Plugin | `maven-publish` |
| Java version | Compiler Plugin/toolchain | Java toolchain |
| Multi-module | Aggregator/reactor | Multi-project build/composite build |

Hai hàng có tên gần nhau không nhất thiết có semantics giống nhau. Ví dụ, Maven lifecycle phase `verify` và Gradle task `check` không phải hai tên có thể thay thế máy móc. Hãy so sánh các task/goal thực sự được chạy và kết quả mà chúng tạo ra.

## 6. Giữ hợp đồng dependency khi chuyển đổi

Dependency metadata là một phần của API dành cho build consumer. Một thư viện có thể compile thành công trong project của chính nó nhưng consumer bị lỗi vì metadata publish không còn khai báo dependency cần thiết.

### 6.1. Maven scope và Gradle configurations

Ví dụ một thư viện Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.example</groupId>
        <artifactId>logging-api</artifactId>
        <version>1.2.0</version>
        <scope>compile</scope>
    </dependency>

    <dependency>
        <groupId>org.example</groupId>
        <artifactId>metrics-runtime</artifactId>
        <version>3.1.0</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Gradle Java Library có thể diễn đạt dependency API và implementation:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.example:logging-api:1.2.0'
    implementation 'org.example:metrics-runtime:3.1.0'
}
```

Đây là ánh xạ theo ý nghĩa ở mức khái quát. Scope/variant thực tế cần xem xét dựa trên API mà library expose, cách consumer sử dụng và metadata được publish.

### 6.2. Kiểm tra consumer thực tế

Tạo một project consumer nhỏ chỉ khai báo artifact đã publish từ build mới. Không để consumer dùng project dependency trực tiếp hoặc source folder của producer, vì điều đó có thể che giấu metadata publish bị thiếu.

Consumer test nên kiểm tra:

- Dependency có resolve từ repository không?
- Compile có nhìn thấy các kiểu dữ liệu public cần thiết không?
- Runtime có đủ implementation/resource không?
- Exclusions và version constraints có hành vi như trước không?
- Consumer dùng Maven và Gradle có cùng nhận được classpath mong đợi không?

## 7. Giữ source/resource và nội dung archive

Khi đổi build tool, hãy so sánh source roots, resource roots, include/exclude và filtering.

Các điểm dễ sai:

- Resource test bị đưa vào artifact production.
- Resource chính bị bỏ vì include pattern quá hẹp.
- File filtering thay placeholder khác nhau giữa hai công cụ.
- Generated source không được tạo trước compile.
- `META-INF/services` bị ghi đè khi tạo fat JAR.
- Manifest mất main class hoặc custom attribute.
- Multi-release JAR entries hoặc module descriptor bị loại.

Ví dụ, Maven có thể lọc resource trong một thư mục được chỉ định, trong khi Gradle `processResources` áp dụng filtering trên một tập file khác. Nếu chỉ chuyển cú pháp mà không giữ cùng tập file và placeholder, artifact có thể khác.

Hãy xác định đường dẫn classpath cuối cùng mà ứng dụng sử dụng. `src/main/resources/config/app.yml` thường trở thành `config/app.yml` trong JAR; kiểm tra cả đường dẫn lẫn nội dung.

## 8. Giữ hợp đồng test và verification

Build mới cần thực hiện các gate tương đương với build cũ. So sánh theo hành vi, không chỉ theo tên task.

| Kiểm tra | Câu hỏi cần trả lời |
|---|---|
| Compile | Có biên dịch cùng source roots, Java release và annotation processors không? |
| Unit tests | Cùng test classes và test resources có được chạy không? |
| Integration tests | Các test cần database/container/service có được chạy ở đúng phase/task không? |
| Static analysis | Checkstyle, SpotBugs, PMD, lint hoặc công cụ nội bộ còn được gọi không? |
| Coverage | Report có được tạo và CI có nhận đúng vị trí không? |
| Packaging | Archive có được tạo sau các bước verification bắt buộc không? |
| Security/license scan | Các gate có chạy trên đúng artifact/dependency graph không? |
| Release validation | Version, metadata, signature và provenance có được kiểm tra không? |

Ví dụ, Maven `verify` thường đi qua các phase trước đó trong default lifecycle, nhưng plugin executions và profile quyết định công việc cụ thể. Gradle `build` thường phụ thuộc `check` và `assemble`, nhưng build script có thể tùy chỉnh. Không nên kết luận hai lệnh tương đương chỉ vì cả hai đều kết thúc với trạng thái thành công.

### 8.1. Kiểm tra test bị skip

Hãy ghi lại số test pass, fail, skipped và excluded. Một build có thể thành công vì test không được lên lịch hoặc bị bỏ qua bằng property. Nếu baseline chạy integration test nhưng build mới chỉ chạy unit test, output có thể không còn được kiểm chứng ở cùng mức.

### 8.2. Kiểm tra test report và coverage report

CI có thể dựa vào vị trí và định dạng report. Nếu đường dẫn đổi, pipeline có thể không upload report hoặc coverage service không nhận dữ liệu dù test đã chạy.

Ghi lại:

- Đường dẫn XML/HTML test report.
- Đường dẫn coverage report.
- Tên suite/task/goal.
- Cách CI thu thập report và xác định trạng thái.

## 9. Giữ hợp đồng publication và repository

Chuyển build tool có thể làm thay đổi cách artifact được publish.

Với Maven, cần xem:

- `distributionManagement` và server ID.
- Release và snapshot repository.
- POM được deploy và dependency metadata.
- Sources/Javadoc artifacts.
- Checksum, signature và staging/release behavior.

Với Gradle, cần xem:

- `maven-publish` publications và components.
- `artifactId`, `group`, `version`.
- POM customization và Gradle Module Metadata.
- Repository URL, credentials và publish tasks.
- Sources/Javadoc variants và artifact classifiers.
- Signing plugin/task nếu có.

Một số repository có chính sách yêu cầu POM, checksum, signature hoặc staging promotion. Hãy kiểm tra hợp đồng với repository manager và pipeline hiện tại trước khi chuyển đổi.

### 9.1. Không publish trực tiếp trong giai đoạn so sánh

Trong giai đoạn migration, có thể publish vào repository thử nghiệm hoặc local staging riêng. Không dùng cùng tọa độ release trong repository production để thử nghiệm, vì release version nên bất biến.

### 9.2. Giữ release bất biến

Nếu build mới tạo artifact khác dưới cùng GAV/version, consumer có thể nhận nội dung khác nhau tùy cache và thời điểm tải. Dùng version thử nghiệm hoặc repository tạm; chỉ phát hành version chính thức khi đã hoàn tất so sánh và được duyệt.

## 10. Kiểm chứng sau chuyển đổi theo nhiều lớp

Không có một phép so sánh duy nhất đủ để chứng minh hợp đồng đầu ra được giữ nguyên. Nên kiểm chứng theo nhiều lớp:

1. **Metadata:** tọa độ, tên file, classifier, extension, manifest và publication metadata.
2. **Archive structure:** danh sách class/resource, service descriptors, module entries và license files.
3. **Dependency contract:** POM/Gradle metadata và classpath consumer thực tế.
4. **API/ABI:** public API và binary compatibility.
5. **Runtime behavior:** khởi động ứng dụng, đọc resource, load service và chạy luồng chính.
6. **Verification behavior:** test, coverage, static analysis và security checks.
7. **Release behavior:** publish, checksum, signature, provenance và repository retrieval.
8. **Reproducibility:** build lặp lại và so sánh digest hoặc nội dung đã chuẩn hóa.

## 11. So sánh artifact bằng công cụ JDK

### 11.1. Liệt kê nội dung JAR

```bash
jar tf build/libs/order-api-2.3.0.jar > new-jar-entries.txt
jar tf baseline/order-api-2.3.0.jar > old-jar-entries.txt
diff -u old-jar-entries.txt new-jar-entries.txt
```

Trên Windows PowerShell có thể dùng `Compare-Object` để so sánh hai danh sách. Hãy chú ý thứ tự entry: nếu mục tiêu chỉ là so sánh tập đường dẫn, có thể chuẩn hóa thứ tự trước khi diff.

### 11.2. Đọc manifest

```bash
unzip -p build/libs/order-api-2.3.0.jar META-INF/MANIFEST.MF
```

So sánh các attribute quan trọng như `Main-Class`, `Implementation-Version`, `Automatic-Module-Name`, `Multi-Release` và custom build metadata.

### 11.3. So sánh checksum

```bash
sha256sum baseline/order-api-2.3.0.jar
sha256sum build/libs/order-api-2.3.0.jar
```

Digest khác nhau cho biết byte khác nhau, nhưng không tự chứng minh artifact mới sai. Archive có thể chứa timestamp, thứ tự ZIP entry hoặc metadata build khác nhau dù class/resource tương đương. Cần kết hợp digest với structural/semantic comparison.

## 12. So sánh nội dung archive sau khi chuẩn hóa

Để so sánh sâu, có thể giải nén hai JAR vào thư mục tạm rồi so sánh nội dung từng entry:

```bash
mkdir old-unpacked new-unpacked
(cd old-unpacked && jar xf ../baseline/order-api-2.3.0.jar)
(cd new-unpacked && jar xf ../build/libs/order-api-2.3.0.jar)
diff -ru old-unpacked new-unpacked
```

Trên Windows có thể dùng `jar xf` trong hai thư mục riêng và `Compare-Object`, hoặc công cụ diff directory.

Khi so sánh, phân loại khác biệt:

- Khác biệt mong đợi do timestamp/manifest build metadata.
- Khác biệt do compiler/JDK hoặc bytecode target.
- Khác biệt không mong muốn ở class/resource.
- Metadata bị thiếu hoặc thừa.
- File phụ được tạo thêm/bỏ đi.

Không nên xóa khác biệt khỏi báo cáo chỉ vì chúng làm digest không khớp. Hãy xác định nguyên nhân và quyết định khác biệt nào được chấp nhận.

## 13. Kiểm tra API và binary compatibility

Một thư viện có thể có cùng tọa độ nhưng thay đổi public API. Consumer đã compile với bản cũ có thể gặp `NoSuchMethodError`, `NoClassDefFoundError` hoặc lỗi linkage khi chạy với artifact mới.

Có thể dùng công cụ API comparison hoặc binary compatibility validator để so sánh public API giữa artifact baseline và artifact sau chuyển đổi. Những điều cần xem:

- Public/protected class, method, field và constructor.
- Generic signatures và annotations có ý nghĩa với consumer.
- Superclass/interface hierarchy.
- Checked exceptions và visibility.
- Module exports và service declarations.
- Java bytecode target và runtime compatibility.

Nếu mục tiêu migration chỉ là thay build tool, API không nên thay đổi ngoài dự kiến. Nếu API có thay đổi, hãy xử lý như một thay đổi sản phẩm/versioning riêng, không gộp âm thầm vào migration.

## 14. Kiểm tra consumer bằng artifact đã publish

Một producer build pass chưa đủ. Hãy tạo một project consumer nhỏ, chỉ dùng artifact được publish từ build mới trong repository thử nghiệm.

Ví dụ consumer Maven:

```xml
<dependency>
    <groupId>com.example.orders</groupId>
    <artifactId>order-api</artifactId>
    <version>2.3.0-migration-test</version>
</dependency>
```

Consumer Gradle:

```groovy
dependencies {
    implementation 'com.example.orders:order-api:2.3.0-migration-test'
}
```

Kiểm tra consumer:

- Resolve artifact từ repository như người dùng thực tế.
- Compile code sử dụng public API.
- Chạy test cần dependency runtime.
- Đọc resource và service provider.
- Kiểm tra dependency graph và version mediation.
- Xác nhận sources/Javadoc metadata nếu đó là một phần hợp đồng.

Không dùng `project(':order-api')` trong consumer test nếu mục tiêu là xác minh publication metadata. Project dependency có thể bỏ qua lỗi trong POM hoặc Gradle Module Metadata.

## 15. Kiểm chứng runtime và packaging

Với application, hãy chạy artifact sau chuyển đổi trong môi trường gần production.

Ví dụ:

```bash
java -jar build/libs/order-service-2.3.0.jar
```

Kiểm tra:

- Manifest có main class đúng.
- Dependency cần thiết có mặt trên runtime classpath hoặc được đóng gói đúng.
- Resource cấu hình được tìm thấy.
- SPI/framework metadata được merge đúng.
- Native library hoặc file phụ được đóng gói/đặt đúng vị trí.
- Shutdown hook, logging và startup behavior vẫn hoạt động.

Với library, tạo integration test consumer. Với application, thực hiện smoke test hoặc deployment thử nghiệm bằng chính artifact đã tạo, không chỉ chạy class từ IDE.

## 16. So sánh kết quả CI trước và sau chuyển đổi

CI là nơi xác nhận build mới hoạt động trong môi trường sạch và tự động. Hãy chạy hai pipeline trên cùng commit hoặc cùng source snapshot để giảm khác biệt đầu vào.

Một bảng so sánh có thể gồm:

| Hạng mục | Build cũ | Build mới | Kết quả mong muốn |
|---|---|---|---|
| JDK/toolchain | Ghi nhận baseline | Ghi nhận cấu hình mới | Tương đương hoặc thay đổi có chủ đích. |
| Compile | Thành công | Thành công | Cùng source/API và target phù hợp. |
| Unit tests | Pass/fail/skip count | Pass/fail/skip count | Không bỏ sót test; khác biệt được giải thích. |
| Integration tests | Các suite đã chạy | Các suite đã chạy | Cùng gate bắt buộc. |
| Static analysis | Report/status | Report/status | Không mất gate hoặc report. |
| Artifact set | Danh sách file | Danh sách file | Cùng contract hoặc thay đổi được duyệt. |
| Coordinates | GAV/variant | GAV/variant | Giữ tương thích consumer. |
| Archive contents | Inventory | Inventory | Khác biệt có giải thích. |
| Dependency metadata | POM/Gradle metadata | Metadata mới | Consumer nhận classpath tương đương. |
| Publish | Repository/credentials | Repository/credentials | Đúng đích và policy. |
| Digest/provenance | Record cũ | Record mới | Đầy đủ, truy vết được. |

Đừng so sánh hai build trên hai commit khác nhau nếu mục tiêu là cô lập ảnh hưởng của build tool. Nếu không thể dùng cùng commit do source migration cần thay đổi build files, hãy giữ phần mã ứng dụng giống nhau và ghi lại mọi thay đổi bắt buộc.

## 17. Chạy song song build cũ và build mới

Trong giai đoạn chuyển đổi, có thể chạy hai build trên cùng revision hoặc hai worktree riêng:

```text
Source revision / application code
          |
          +--> Build tool cũ --> baseline artifacts/reports
          |
          +--> Build tool mới --> candidate artifacts/reports
                                  |
                                  +--> compare contracts
```

Hai build nên dùng output directory riêng, repository thử nghiệm riêng và version thử nghiệm không xung đột. Không để hai build ghi đè cùng artifact hoặc cùng output folder.

### 17.1. Cùng source, khác build configuration

Nếu chuyển từ Maven sang Gradle, có thể giữ POM cũ trong một nhánh/worktree và thêm Gradle build ở nhánh khác. Chạy cả hai trên cùng commit của mã ứng dụng để so sánh artifact.

Nếu chuyển dần theo module, cần ghi rõ module nào đã chuyển và module nào vẫn dùng build cũ. Không để hai hệ thống cùng publish cùng tọa độ release trong thời gian thử nghiệm.

### 17.2. Không để hai build làm thay đổi source lẫn nhau

Generated source, version file hoặc resource filtering có thể sửa workspace. Dùng worktree hoặc checkout riêng để hai build không ghi đè đầu vào của nhau. Nếu cùng workspace, hãy bảo đảm output directory và file sinh ra tách biệt.

## 18. Kiểm tra reproducibility và tính xác định

Nếu hai lần build cùng source và inputs tạo artifact khác nhau, cần xác định khác biệt có ý nghĩa hay chỉ là metadata không ổn định.

Các nguồn khác biệt thường gặp:

- Timestamp trong ZIP entry hoặc manifest.
- Thứ tự archive entries.
- Absolute path trong debug information hoặc generated file.
- JDK/compiler/plugin version.
- Dependency version động hoặc snapshot thay đổi.
- Locale, timezone và encoding.
- Build number hoặc CI run ID được ghi vào resource.
- Generated code phụ thuộc môi trường.

Build reproducible không nhất thiết yêu cầu mọi file byte giống nhau nếu quy trình có metadata theo lần chạy. Tuy nhiên, phải biết rõ phần nào được phép thay đổi và phần nào cần ổn định. Với artifact release, hãy ưu tiên xác định inputs và kiểm soát nguồn tạo output.

### 18.1. Tách metadata truy vết khỏi nội dung cần tái lập

Nếu ghi CI run ID hoặc thời gian build vào JAR, hai lần build khác run có thể tạo digest khác nhau. Có thể vẫn đạt yêu cầu traceability nhưng không đạt byte-for-byte reproducibility.

Hãy quyết định:

- Metadata nào phải nằm trong artifact?
- Metadata nào có thể lưu trong provenance bên ngoài?
- Có cần cùng source/inputs tạo đúng cùng digest không?
- Nếu digest khác, cách xác định khác biệt hợp lệ là gì?

Không nên bỏ metadata truy vết chỉ để digest giống nhau nếu quy trình release yêu cầu provenance. Có thể lưu build run metadata trong attestation gắn với digest thay vì nhúng tất cả vào archive.

## 19. Bảo toàn signing, checksum và provenance

Build tool mới phải giữ được bước xác minh nguồn gốc và tính toàn vẹn nếu quy trình cũ đang dùng.

Kiểm tra:

- Artifact có được ký sau khi mọi biến đổi/đóng gói hoàn tất không?
- Checksum được tính trên đúng file được publish không?
- Signature có được upload cùng artifact và metadata không?
- Provenance gắn đúng digest, commit và builder identity không?
- SBOM mô tả đúng dependency graph của artifact cuối không?
- Consumer có thể xác minh signature/attestation bằng trust policy hiện tại không?

Không chuyển nguyên một bước ký trước khi shading/repackaging nếu bước sau làm thay đổi bytes. Artifact cuối cùng phải được ký sau các biến đổi nội dung.

## 20. Release migration theo từng giai đoạn

Một lộ trình an toàn có thể chia thành các giai đoạn:

1. **Inventory:** ghi lại artifact, metadata, task/goal, CI gate và consumer.
2. **Baseline:** build sạch bằng hệ thống cũ và lưu artifact/report/digest.
3. **Parallel implementation:** tạo cấu hình build mới mà không thay đổi contract công khai.
4. **Local verification:** compile, test, package và so sánh archive.
5. **Consumer verification:** publish thử vào repository cách ly và kiểm tra bằng project consumer.
6. **CI comparison:** chạy build cũ và mới trên cùng source revision, so sánh report và output.
7. **Release rehearsal:** kiểm tra version, tag, signing, checksum, provenance và quyền publish trên môi trường thử.
8. **Cutover:** chuyển pipeline chính sang build mới sau khi các gate đạt yêu cầu.
9. **Observation:** theo dõi consumer, deployment và lỗi runtime sau cutover.
10. **Retirement:** chỉ gỡ build cũ sau khi xác nhận không còn consumer hoặc quy trình phụ thuộc.

Không nên xóa build cũ ngay khi build mới chạy được. Giữ một khoảng thời gian quan sát và có kế hoạch quay lại nếu contract bị phá vỡ.

## 21. Tiêu chí chấp nhận sau chuyển đổi

Trước khi coi migration hoàn tất, nhóm có thể yêu cầu các điều kiện sau:

- Tất cả tọa độ artifact công khai giữ nguyên hoặc đã có kế hoạch version/breaking change được duyệt.
- Tên file, classifier và extension cần thiết vẫn được tạo.
- Nội dung archive có các class/resource/metadata cần thiết.
- Manifest và runtime entry point hoạt động.
- Dependency metadata được consumer Maven/Gradle resolve đúng.
- Unit/integration/verification gates bắt buộc đều chạy và có report.
- Publish vào đúng repository với release/snapshot policy phù hợp.
- Checksum, signature, SBOM và provenance được tạo/xác minh theo yêu cầu.
- Artifact sau publish có digest khớp với artifact đã kiểm tra.
- CI có thể tái hiện build từ checkout sạch và wrapper/toolchain đã khóa.
- Các khác biệt đã được ghi nhận, giải thích và chấp thuận.

Tiêu chí cần được điều chỉnh theo loại project. Một library, application, plugin và platform/BOM có các hợp đồng đầu ra khác nhau.

## 22. Ví dụ: chuyển một library từ Maven sang Gradle

Giả sử library cũ có:

```text
GAV: com.example.orders:order-api:2.3.0
Files:
  order-api-2.3.0.jar
  order-api-2.3.0-sources.jar
  order-api-2.3.0-javadoc.jar
  order-api-2.3.0.pom
```

POM khai báo `logging-api` là dependency compile và `metrics-runtime` là runtime dependency. Project cũng tạo manifest có implementation version và publish sources/Javadoc.

Build Gradle mới có thể cấu hình:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example.orders'
version = '2.3.0'

java {
    withSourcesJar()
    withJavadocJar()
}

dependencies {
    api 'org.example:logging-api:1.2.0'
    runtimeOnly 'org.example:metrics-runtime:3.1.0'
}

tasks.named('jar') {
    manifest {
        attributes(
            'Implementation-Title': 'order-api',
            'Implementation-Version': project.version
        )
    }
}

publishing {
    publications {
        create('mavenJava', MavenPublication) {
            from components.java
            artifactId = 'order-api'
        }
    }
}
```

Đây là điểm bắt đầu, không phải bằng chứng migration hoàn tất. Cần publish vào repository thử nghiệm, tải POM/Gradle metadata và artifact về, kiểm tra sources/Javadoc JAR, so sánh dependency graph và chạy consumer test.

Nếu consumer Maven cũ chỉ đọc POM còn consumer Gradle mới đọc Gradle Module Metadata, hai nhóm có thể nhìn thấy metadata khác nhau. Hãy kiểm tra cả hai loại consumer để đảm bảo hợp đồng được giữ theo yêu cầu.

## 23. Ví dụ: chuyển một application từ Gradle sang Maven

Giả sử ứng dụng Gradle tạo fat JAR có:

- Tên `order-service-2.3.0-all.jar`.
- Manifest `Main-Class: com.example.orders.Main`.
- Service descriptors được merge.
- Resource `application.yml` được đưa vào archive.
- Unit và integration tests chạy trong CI.

Khi chuyển sang Maven, cần cấu hình Shade Plugin với service transformer, manifest transformer, resource filtering phù hợp và các execution test tương đương. Chỉ khai báo `maven-jar-plugin` rồi chạy `package` có thể tạo JAR thường không chứa dependency, khác hẳn hợp đồng fat JAR ban đầu.

Sau chuyển đổi, kiểm tra:

```bash
jar tf target/order-service-2.3.0.jar
unzip -p target/order-service-2.3.0.jar META-INF/MANIFEST.MF
unzip -p target/order-service-2.3.0.jar META-INF/services/com.example.spi.OrderProvider
java -jar target/order-service-2.3.0.jar
```

Tên file thực tế phụ thuộc cấu hình Maven final name và Shade output. Hãy giữ tên artifact mà deployment pipeline đang mong đợi hoặc cập nhật consumer/deployment contract có chủ đích.

## 24. Rollback và xử lý khác biệt

Trong migration, một khác biệt không nhất thiết là lỗi. Điều quan trọng là phân loại:

| Loại khác biệt | Cách quyết định |
|---|---|
| Khác biệt không mong muốn | Sửa cấu hình mới để khôi phục contract. |
| Khác biệt do metadata thời gian/build ID | Xác định có cần reproducibility byte-for-byte hay không; chuyển metadata phù hợp sang provenance nếu được chấp thuận. |
| Khác biệt API/ABI | Đánh giá như breaking change, versioning và compatibility riêng. |
| Khác biệt dependency graph | Kiểm tra consumer classpath và runtime; sửa scope/configuration. |
| Khác biệt report/task | Xác nhận CI gate vẫn chạy và downstream nhận đúng report. |
| Khác biệt publish/signature | Kiểm tra repository policy, signing order và artifact digest. |

Nếu migration làm hỏng contract sau cutover, rollback cần khôi phục pipeline/build configuration cũ và tiếp tục dùng artifact/version đã phát hành. Không overwrite release artifact đã publish để “sửa” migration; phát hành version mới theo chính sách nếu nội dung cần thay đổi.

## 25. Những hiểu nhầm thường gặp

### “Build mới thành công nghĩa là chuyển đổi hoàn tất”

Không. Build success chỉ cho biết các task/goal được gọi đã hoàn thành theo cấu hình mới. Nó không chứng minh consumer metadata, artifact inventory, runtime behavior hoặc release workflow tương đương.

### “JAR có cùng class là artifact tương đương”

Không nhất thiết. Manifest, resource, service descriptors, dependency metadata, classifier, signature và cách khởi chạy cũng là một phần của hợp đồng.

### “Cùng tên file nghĩa là cùng artifact”

Không. Nội dung byte có thể khác. Hãy dùng digest và kiểm tra nội dung archive.

### “POM và Gradle Module Metadata luôn mô tả dependency giống nhau”

Không. Gradle có variant-aware metadata; Maven consumer chủ yếu dùng POM. Hãy kiểm tra từng loại consumer và metadata được publish.

### “Có thể so sánh hai JAR chỉ bằng SHA-256”

Digest cho biết bytes có giống nhau hay không. Nếu khác, cần structural/semantic comparison để biết khác biệt có ý nghĩa gì. Nếu giống, đó là bằng chứng mạnh về cùng nội dung byte nhưng vẫn cần xác định provenance của file.

### “Chỉ cần chạy unit test sau chuyển đổi”

Không. Cần chạy các verification gate mà release hiện tại yêu cầu, bao gồm integration test, static analysis, packaging và consumer/runtime checks nếu có.

### “Có thể publish thử cùng version release”

Không nên. Release artifact cần bất biến. Hãy dùng version thử nghiệm và repository cách ly cho quá trình so sánh.

## 26. Thực hành: giữ hợp đồng đầu ra khi đổi build tool

Trong một project Java thử nghiệm, hãy mô phỏng chuyển đổi Maven sang Gradle hoặc ngược lại:

1. Chọn commit baseline và ghi lại JDK, build tool version, plugin và lệnh CI.
2. Build sạch bằng hệ thống cũ; lưu artifact, test report, dependency metadata và digest.
3. Lập inventory GAV, tên file, classifier, extension, manifest, resource và dependency graph.
4. Tạo cấu hình build mới với cùng source code và version thử nghiệm.
5. Chạy compile, unit test, integration test và các gate tương đương.
6. Tạo artifact và so sánh danh sách archive entries, manifest và resource.
7. So sánh API/ABI và dependency metadata.
8. Publish vào repository thử nghiệm, sau đó tạo consumer Maven và Gradle để resolve artifact.
9. Chạy smoke/integration test trên artifact đã publish.
10. Kiểm tra checksum, signing, SBOM/provenance nếu dự án có yêu cầu.
11. Chạy CI cũ và mới trên cùng source revision, ghi lại mọi khác biệt.
12. Chỉ cutover khi các khác biệt được giải thích và các tiêu chí chấp nhận đã đạt.

Sau khi thực hành, hãy tự trả lời:

- Hợp đồng đầu ra bao gồm những gì ngoài file JAR?
- Vì sao cần baseline trước khi thay build tool?
- Maven scope và Gradle `api`/`implementation` cần được ánh xạ theo nguyên tắc nào?
- Vì sao consumer test cần dùng artifact đã publish thay vì project dependency?
- Digest khác nhau có luôn nghĩa là migration sai không?
- Làm sao xác nhận integration test và static analysis vẫn chạy?
- Vì sao không nên publish thử vào cùng tọa độ release?
- Làm thế nào để bảo toàn signing, checksum và provenance?
- Điều kiện nào cần đạt trước cutover và rollback?

## 27. Kết luận

Chuyển đổi build tool cần giữ những cam kết mà consumer và quy trình phát hành đang dựa vào: artifact coordinates, tên file/classifier, nội dung archive, dependency metadata, API/ABI, test gates, publication, signature và provenance. Build mới chạy thành công chưa đủ để chứng minh các cam kết đó vẫn được giữ.

Hãy lập baseline từ một source revision xác định, mô tả output contract và consumer, ánh xạ ý nghĩa giữa hai build model, rồi kiểm chứng theo nhiều lớp: metadata, archive structure, dependency graph, API, runtime, CI và release. Dùng artifact thử nghiệm và consumer project thực tế, so sánh digest cùng nội dung đã chuẩn hóa, ghi nhận mọi khác biệt và chỉ cutover khi các tiêu chí chấp nhận đạt yêu cầu. Cách tiếp cận này giúp thay đổi công cụ build mà không làm mất khả năng tương thích, vận hành và truy vết của artifact.
