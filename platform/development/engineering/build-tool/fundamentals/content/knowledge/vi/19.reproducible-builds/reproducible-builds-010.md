# Cân bằng tính tái lập với khả năng cập nhật phụ thuộc

Một dự án Java cần hai điều tưởng như đối lập. Khi chạy lại build trên máy khác hoặc vài tuần sau, nhóm muốn nhận được cùng một tập thư viện và kết quả có thể dự đoán. Nhưng nhóm cũng cần cập nhật thư viện để nhận bản vá bảo mật, sửa lỗi và cải tiến mới. Nếu mọi dependency luôn tự động chuyển sang bản mới nhất, build có thể thay đổi dù mã nguồn không đổi. Nếu khóa mọi thứ quá lâu, dự án có thể tiếp tục dùng phiên bản đã lỗi thời hoặc có lỗ hổng.

Đây là bài toán cân bằng giữa **tính tái lập** (*reproducibility*) và **khả năng cập nhật** (*freshness*). Cách tiếp cận thực tế là tách thời điểm chọn phiên bản khỏi thời điểm thực thi build: trong một build đã được chấp nhận, dependency được cố định và có thể xác minh; việc tìm phiên bản mới diễn ra theo một quy trình cập nhật có chủ đích, được kiểm thử và review.

## 1. Tính tái lập và khả năng cập nhật là gì?

**Tính tái lập** là khả năng chạy lại quy trình build với cùng đầu vào đã kiểm soát và nhận được cùng dependency graph, hành vi build và, trong mục tiêu nghiêm ngặt hơn, cùng artifact đầu ra theo từng byte.

**Khả năng cập nhật** là khả năng phát hiện, đánh giá và tiếp nhận phiên bản mới của thư viện, plugin hoặc công cụ build khi chúng được phát hành.

Hai mục tiêu này cần được quản lý ở hai thời điểm khác nhau:

```text
Thời điểm tìm bản mới                 Thời điểm build đã được chấp nhận
        |                                          |
        v                                          v
Kiểm tra phiên bản mới                    Dùng version đã khóa
        |                                          |
        v                                          v
Đánh giá release note, CVE                Resolve đúng dependency graph
        |                                          |
        v                                          v
Tạo thay đổi dependency                    Compile / test / package
        |                                          |
        v                                          v
Review và kiểm thử                         Build có thể tái lập
        |                                          |
        +----------> Cập nhật lock/policy <--------+
```

Build thông thường nên ưu tiên kết quả ổn định. Một công việc cập nhật riêng có thể chủ động kiểm tra phiên bản mới rồi tạo thay đổi để nhóm xem xét.

## 2. Phân biệt pin phiên bản, version alignment và dependency locking

Ba khái niệm thường được dùng cùng nhau nhưng giải quyết những vấn đề khác nhau.

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| Pin version | Chỉ định phiên bản trực tiếp trong khai báo dependency | `implementation 'org.example:library:2.4.1'` |
| Platform/BOM hoặc constraint | Quản lý một nhóm version tương thích | Jackson BOM quản lý các module Jackson |
| Dependency locking | Ghi lại phiên bản thực tế được resolve trong configuration | Gradle `gradle.lockfile` |
| Dependency verification | Kiểm tra artifact tải về khớp checksum hoặc chữ ký đã tin cậy | Gradle `verification-metadata.xml` |

Pin version làm rõ yêu cầu trực tiếp. Platform/BOM giúp các thư viện liên quan dùng bộ phiên bản phù hợp. Locking ghi nhận kết quả resolution, bao gồm cả nhiều dependency bắc cầu. Verification giúp phát hiện artifact tải về không đúng nội dung đã được chấp nhận.

Không nên xem một trong các cơ chế này là thay thế hoàn toàn cho những cơ chế còn lại. Một dự án có thể pin dependency trực tiếp nhưng vẫn nhận phiên bản bắc cầu khác khi metadata thay đổi. Lockfile có thể cố định phiên bản nhưng không tự chứng minh file JAR tải về là artifact đáng tin cậy. Checksum xác minh nội dung artifact nhưng không quyết định phiên bản nào là phù hợp về mặt tương thích.

## 3. Vì sao không nên luôn dùng phiên bản mới nhất?

Giả sử build script khai báo:

```groovy
dependencies {
    implementation 'com.example:payment-client:latest.release'
}
```

Ngày hôm nay, repository có thể resolve dependency thành `4.2.0`. Tuần sau, nhà cung cấp phát hành `4.3.0`; cùng một build script có thể resolve thành phiên bản mới mà không có thay đổi trong repository của dự án.

Điều đó có thể dẫn đến:

- Build hôm nay pass nhưng ngày mai fail.
- API thay đổi khiến mã nguồn không còn biên dịch.
- Hành vi runtime thay đổi dù commit không đổi.
- Dependency bắc cầu được nâng theo và gây xung đột.
- CI và máy phát triển resolve ở các thời điểm khác nhau.
- Khó xác định artifact nào đã được dùng để tạo bản phát hành.

Các selector linh hoạt như `1.+`, `latest.release` hoặc version range có thể hữu ích trong một quy trình tìm bản mới, nhưng làm kết quả resolution phụ thuộc vào trạng thái repository và thời điểm kiểm tra. Không nên để chúng tự do quyết định dependency của một build phát hành mà không có cơ chế khóa hoặc kiểm soát tương ứng.

## 4. Exact version và version range

### Exact version

```groovy
dependencies {
    implementation 'com.example:payment-client:4.2.1'
}
```

Khai báo này yêu cầu một version cụ thể. Nó dễ đọc, dễ review và không tự chuyển sang version khác chỉ vì repository có bản mới.

Tuy nhiên, exact version cho dependency trực tiếp chưa chắc đã cố định toàn bộ dependency graph. Các dependency bắc cầu, version được quản lý bởi platform, plugin và metadata repository vẫn cần được xem xét.

### Dynamic version

```groovy
dependencies {
    implementation 'com.example:payment-client:4.+'
}
```

Gradle có thể chọn phiên bản mới nhất phù hợp với selector `4.+` tại thời điểm resolve. Kết quả có thể thay đổi theo thời gian.

### Version range

```groovy
dependencies {
    implementation 'com.example:payment-client:[4.1,5.0)'
}
```

Range biểu thị một tập version được chấp nhận, trong ví dụ là từ `4.1` trở lên nhưng nhỏ hơn `5.0`. Range vẫn cho phép build chọn nhiều version khác nhau theo trạng thái repository và quy tắc resolution.

Version range đôi khi hữu ích khi phát triển thư viện hoặc muốn thể hiện giới hạn tương thích, nhưng ứng dụng cần kết quả có thể tái lập nên quản lý version đã resolve bằng locking hoặc chính sách tương đương.

### Không giả định mọi dự án tuân theo SemVer hoàn hảo

Tên version có thể trông như `MAJOR.MINOR.PATCH`, nhưng không phải mọi nhà cung cấp đều tuân thủ Semantic Versioning giống nhau. Ngay cả khi tuân thủ, một bản cập nhật minor vẫn có thể thay đổi hành vi, yêu cầu runtime hoặc dependency bắc cầu. Hãy đọc release note và kiểm thử thay vì chỉ dựa vào số version.

## 5. Snapshot và release artifact

Trong Maven ecosystem, hậu tố `SNAPSHOT` biểu thị phiên bản phát triển chưa phải release cố định:

```text
com.example:payment-client:4.3-SNAPSHOT
```

Repository có thể cập nhật nội dung của snapshot theo thời gian. Metadata repository có thể ánh xạ tên `4.3-SNAPSHOT` đến các snapshot artifact có timestamp/build number khác nhau.

Điều đó có nghĩa hai lần resolve cùng tọa độ `4.3-SNAPSHOT` có thể nhận nội dung khác nhau nếu nhà phát hành đã publish snapshot mới.

Release version như `4.2.1` theo chính sách repository chuẩn thường được xem là bất biến sau khi phát hành. Không nên ghi đè nội dung của release artifact đã publish. Nếu cần sửa, nhà cung cấp nên phát hành version mới.

### Khi nào dùng snapshot?

Snapshot có thể phù hợp khi:

- Phối hợp phát triển giữa các module hoặc nhóm chưa phát hành release.
- Kiểm tra một thay đổi upstream trước khi có bản release chính thức.
- Thử nghiệm tích hợp trong môi trường development.

Snapshot không phù hợp làm dependency mặc định cho release build vì nội dung có thể thay đổi mà version string vẫn giữ nguyên.

### Quy tắc thực tế

- Dùng release version cho build phát hành và build cần tái lập.
- Giới hạn snapshot ở nhánh hoặc pipeline phát triển cần thử nghiệm.
- Ghi lại commit/build metadata của snapshot nếu dùng trong kiểm thử tích hợp.
- Không dùng snapshot làm nền tảng không kiểm soát cho production release.

## 6. Gradle cache và thời điểm kiểm tra phiên bản mới

Gradle lưu metadata và artifact đã tải để tránh truy cập repository ở mọi lần build. Với dynamic version và changing module, Gradle còn cache kết quả kiểm tra theo khoảng thời gian.

Một số khái niệm:

- **Dynamic version:** selector có thể khớp nhiều version, ví dụ `1.+`.
- **Changing module:** tọa độ có thể giữ nguyên nhưng nội dung thay đổi, ví dụ Maven snapshot.
- **Dependency cache:** dữ liệu Gradle đã tải hoặc đã resolve, dùng để tăng tốc các lần build sau.

Theo mặc định phổ biến, Gradle cache kết quả dynamic version và changing module trong một khoảng thời gian (thường là 24 giờ). Vì vậy, ngay cả khi repository đã có bản mới, Gradle không nhất thiết kiểm tra lại ngay ở lần build tiếp theo.

### Làm mới dependency metadata

Khi cần kiểm tra lại repository:

```bash
./gradlew build --refresh-dependencies
```

`--refresh-dependencies` yêu cầu Gradle làm mới trạng thái dependency cache và kiểm tra lại metadata/artifact cần thiết. Tùy checksum và nội dung cache, Gradle có thể không tải lại mọi file JAR nếu artifact hiện có vẫn khớp; tùy chọn này không có nghĩa luôn tải lại toàn bộ mọi dependency từ đầu.

Đây là công cụ chẩn đoán hoặc cập nhật có chủ đích, không nên thêm vào mọi lệnh build thông thường vì có thể làm tăng truy cập mạng và thời gian build.

### Cấu hình thời gian cache cho changing module

Nếu một project development cần nhận snapshot nhanh hơn, Gradle cho phép cấu hình thời gian cache:

```groovy
configurations.configureEach {
    resolutionStrategy {
        cacheChangingModulesFor 10, 'minutes'
    }
}
```

Với dynamic version:

```groovy
configurations.configureEach {
    resolutionStrategy {
        cacheDynamicVersionsFor 30, 'minutes'
    }
}
```

Ví dụ này rút ngắn khoảng cache tương ứng. Đặt TTL quá thấp có thể khiến build liên tục hỏi repository, làm pipeline chậm và phụ thuộc mạng nhiều hơn. Chỉ nên thay đổi khi có nhu cầu thực tế và phạm vi rõ ràng.

## 7. Dependency locking trong Gradle

Dependency locking ghi lại phiên bản đã được Gradle resolve cho các configuration được bật locking. Nhờ đó, lần build sau có thể dùng lại các version đã chấp nhận thay vì resolve lại theo selector linh hoạt hoặc metadata mới.

### Bật locking

Trong `build.gradle`:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Trong `build.gradle.kts`:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

`lockAllConfigurations()` yêu cầu bật locking cho các configuration của project. Cấu hình cần được áp dụng ở những project muốn quản lý lock state; trong multi-project, không nên giả định chỉ khai báo ở root là tự động quản lý mọi subproject nếu build logic không áp dụng cấu hình đó cho chúng.

### Tạo hoặc cập nhật lock state

Chạy một task thực sự resolve configuration và thêm `--write-locks`:

```bash
./gradlew build --write-locks
```

Gradle ghi các phiên bản đã resolve vào lock state cho configuration được bật locking và đã được resolve trong lần chạy đó. Với Gradle hiện đại, file mặc định thường là `gradle.lockfile` trong thư mục project. Các build cũ có thể có định dạng lockfile theo từng configuration trong `gradle/dependency-locks/`.

Đưa lockfile vào version control để những máy và CI khác dùng cùng kết quả đã được review. Nếu một configuration chưa được resolve trong lần tạo lock state, có thể chưa có đầy đủ lock entries cho configuration đó; cần chạy những task phù hợp để bao phủ các configuration cần khóa.

### Cập nhật lock state có chủ đích

Khi muốn nâng cấp dependency:

1. Sửa version trực tiếp, platform/BOM hoặc constraint.
2. Chạy task resolve tương ứng với `--write-locks`.
3. Review diff của lockfile để thấy version nào thay đổi.
4. Chạy compile, unit test và integration test phù hợp.
5. Commit thay đổi build script cùng lockfile.

Không nên xóa toàn bộ lockfile mỗi lần cập nhật. Giữ diff nhỏ giúp reviewer nhận ra dependency nào đã thay đổi và vì sao.

### Locking không đóng băng nội dung artifact

Lockfile chủ yếu ghi nhận phiên bản được resolve. Nếu repository cho phép ghi đè một artifact release cùng tọa độ, hoặc một module thay đổi nội dung mà không đổi version, lockfile không tự bảo đảm byte content không thay đổi. Vì vậy, cần kết hợp repository bất biến và dependency verification khi yêu cầu chuỗi cung ứng phần mềm nghiêm ngặt.

## 8. Dependency verification trong Gradle

Dependency verification giúp xác minh artifact được tải có khớp checksum hoặc chữ ký đã được chấp nhận hay không. Gradle lưu metadata xác minh trong file:

```text
gradle/verification-metadata.xml
```

Có thể tạo metadata ban đầu bằng lệnh:

```bash
./gradlew --write-verification-metadata sha256 help
```

Gradle resolve các dependency cần cho task `help` và ghi checksum cho những artifact được quan sát trong lần chạy đó. Trong thực tế, cần chạy các task/configuration liên quan để metadata bao phủ dependency của build, rồi review file được tạo.

**Quan trọng:** tạo checksum từ artifact vừa tải không tự chứng minh artifact đó đáng tin cậy. Cần đối chiếu checksum/chữ ký với nguồn phát hành đáng tin cậy, quy trình nội bộ hoặc dữ liệu đã được xác minh. Sau khi metadata được review và commit, Gradle có thể kiểm tra những artifact được resolve trong các lần build sau.

Dependency verification bổ sung cho locking:

- Locking trả lời: phiên bản nào được chọn?
- Verification trả lời: artifact nhận được có đúng nội dung đã được chấp nhận không?

## 9. Platform/BOM và version catalog trong quy trình tái lập

Version catalog giúp tập trung tọa độ và version alias:

```toml
[versions]
jackson = "2.17.2"

[libraries]
jackson-bom = { module = "com.fasterxml.jackson:jackson-bom", version.ref = "jackson" }
jackson-databind = { module = "com.fasterxml.jackson.core:jackson-databind" }
jackson-jsr310 = { module = "com.fasterxml.jackson.datatype:jackson-datatype-jsr310" }
```

Trong build script:

```groovy
dependencies {
    implementation platform(libs.jackson.bom)
    implementation libs.jackson.databind
    implementation libs.jackson.jsr310
}
```

Version catalog giúp người đọc thấy version được quản lý ở đâu. BOM cung cấp constraint để các module Jackson được căn chỉnh. Lockfile ghi lại kết quả thực tế được resolve, kể cả dependency bắc cầu.

Khi nâng Jackson, nhóm thay version trong catalog, kiểm tra BOM mới, cập nhật lock state và chạy test. Không cần tự sửa version của từng artifact nếu BOM quản lý chúng.

## 10. Maven: version cố định và dependencyManagement

Maven thường dùng version cụ thể trong dependency hoặc quản lý version tập trung qua parent POM/BOM.

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.fasterxml.jackson</groupId>
            <artifactId>jackson-bom</artifactId>
            <version>2.17.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

BOM giúp quản lý version của nhóm artifact. Các dependency vẫn cần được khai báo trong `<dependencies>` nếu project sử dụng chúng.

Trong Maven, exact release version và BOM giúp build dễ dự đoán hơn. Tuy nhiên, Maven không có lockfile tích hợp theo cùng mô hình Gradle dependency locking trong mọi dự án. Để tái lập resolution, cần quản lý version trực tiếp, BOM, repository và plugin versions rõ ràng; có thể bổ sung công cụ hoặc plugin ghi nhận dependency graph nếu tổ chức cần.

## 11. Maven SNAPSHOT và chính sách cập nhật repository

Maven hỗ trợ `SNAPSHOT` để tiêu thụ artifact đang phát triển:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>payment-client</artifactId>
    <version>4.3-SNAPSHOT</version>
</dependency>
```

Repository có thể publish snapshot mới và cập nhật metadata để Maven tìm được bản mới. Tần suất Maven kiểm tra repository được điều khiển bởi `updatePolicy` trong cấu hình repository, ví dụ `always`, `daily`, `interval:X` hoặc `never` theo cú pháp Maven.

Ví dụ:

```xml
<repositories>
    <repository>
        <id>company-snapshots</id>
        <url>https://repo.example.com/maven-snapshots</url>
        <snapshots>
            <enabled>true</enabled>
            <updatePolicy>interval:30</updatePolicy>
        </snapshots>
    </repository>
</repositories>
```

`interval:30` yêu cầu kiểm tra theo khoảng thời gian 30 phút. Repository release và snapshot nên được tách chính sách; không nên bật snapshot ở mọi repository chỉ để build tự nhận bản mới.

### Buộc Maven kiểm tra cập nhật

```bash
mvn -U verify
```

`-U` yêu cầu Maven kiểm tra các snapshot đã cập nhật và các release bị thiếu trong local repository. Nó hữu ích khi cần làm mới trạng thái dependency, nhưng không nên thêm vào mọi lần build phát hành nếu mục tiêu là giữ môi trường ổn định.

## 12. Maven version ranges và dependency convergence

Maven cũng hỗ trợ version range, ví dụ:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>payment-client</artifactId>
    <version>[4.1,5.0)</version>
</dependency>
```

Range cho phép Maven chọn một version phù hợp trong khoảng. Kết quả có thể thay đổi khi repository xuất hiện bản mới, nên cần thận trọng nếu build phải tái lập.

Maven Enforcer Plugin có các rule giúp kiểm soát dependency graph, ví dụ `dependencyConvergence` để phát hiện cùng một dependency được yêu cầu với các version khác nhau theo những đường khác nhau. Rule này không thay thế BOM hoặc version management, nhưng giúp phát hiện xung đột sớm.

Ví dụ cấu hình minh họa:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>enforce-dependency-convergence</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <dependencyConvergence />
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Khi áp dụng rule, cần xử lý các version conflict có chủ đích bằng dependency management, exclusions hoặc nâng cấp thư viện phù hợp. Không nên thêm exclusion ngẫu nhiên chỉ để làm Enforcer pass.

## 13. Cố định plugin và build tool cũng quan trọng như dependency ứng dụng

Một build có thể pin mọi thư viện ứng dụng nhưng vẫn thay đổi nếu plugin hoặc build tool tự được nâng cấp.

Những thành phần cần quản lý:

- Gradle Wrapper distribution version.
- Maven Wrapper distribution version.
- Gradle plugin version trong `plugins {}` hoặc plugin management.
- Maven plugin version trong POM/parent POM.
- JDK/toolchain dùng để biên dịch và chạy test.
- Annotation processor và compiler plugin.
- Container image hoặc môi trường CI nếu build chạy trong container.

Gradle Wrapper giúp nhóm dùng cùng phiên bản Gradle:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.10.2-bin.zip
distributionSha256Sum=<sha256 đã xác minh>
```

`distributionSha256Sum` có thể dùng để kiểm tra checksum của distribution tải về. Giá trị phải được lấy và xác minh từ nguồn đáng tin cậy; không dùng một placeholder như ví dụ trong file thực tế.

Với Maven, dùng Maven Wrapper và pin phiên bản Maven trong cấu hình wrapper. Trong POM, nên chỉ định version cho plugin quan trọng thay vì để Maven tự chọn phiên bản mặc định khác nhau theo môi trường.

## 14. Tái lập build không chỉ là khóa dependency

Lockfile là một phần quan trọng nhưng chưa đủ để bảo đảm artifact tạo ra giống hệt giữa hai lần build.

Những yếu tố khác có thể ảnh hưởng:

- Phiên bản JDK, compiler và toolchain.
- Phiên bản build tool và plugin.
- Hệ điều hành, kiến trúc CPU và filesystem.
- Locale, timezone và encoding.
- Biến môi trường và cấu hình ngoài repository.
- Thời gian tạo archive hoặc thứ tự entry trong JAR.
- Dữ liệu tải từ mạng trong lúc build.
- Script sinh version hoặc metadata dựa trên timestamp.

Ví dụ, hai build dùng cùng dependency graph nhưng tạo JAR với timestamp khác nhau có thể tạo ra hai file byte khác nhau. Một số plugin hỗ trợ cấu hình timestamp cố định hoặc reproducible archive để giảm khác biệt này.

Với Maven, thuộc tính `project.build.outputTimestamp` có thể được dùng bởi các plugin đóng gói hỗ trợ reproducible archive:

```xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

Giá trị thực tế nên được quản lý theo quy ước của dự án. Cần kiểm tra các plugin tạo archive có hỗ trợ thuộc tính này hay không.

Với Gradle, cần xem tài liệu của task/plugin đóng gói để xác nhận các thuộc tính như timestamp và thứ tự archive entry có được chuẩn hóa hay không. Không nên giả định chỉ cần lock dependency là đã có byte-for-byte reproducibility.

## 15. Chiến lược cập nhật dependency có kiểm soát

Một quy trình cập nhật tốt không chờ đến khi dự án quá cũ mới nâng cấp toàn bộ. Thay vào đó, nhóm tạo nhịp cập nhật thường xuyên và có phạm vi rõ ràng.

### Bước 1: phát hiện phiên bản mới

Sử dụng công cụ kiểm tra dependency update hoặc quy trình định kỳ để biết:

- Có release mới không?
- Có bản vá bảo mật không?
- Dependency nào đã hết hỗ trợ?
- Có phiên bản nào không còn tương thích với JDK hoặc framework hiện tại?

### Bước 2: phân loại mức ưu tiên

Không phải mọi bản cập nhật đều có mức độ khẩn cấp giống nhau.

| Loại cập nhật | Cách ưu tiên thường gặp |
|---|---|
| Bản vá bảo mật nghiêm trọng | Đánh giá và xử lý sớm theo quy trình security response |
| Bug fix ảnh hưởng chức năng đang dùng | Ưu tiên theo mức độ ảnh hưởng và khả năng tái hiện |
| Minor/feature release | Lên lịch cập nhật và kiểm tra compatibility |
| Major release | Lập kế hoạch migration, đọc breaking changes và kiểm thử rộng |
| Plugin/build tool update | Kiểm tra tác động lên task graph, compiler, cache và CI |

### Bước 3: tạo thay đổi nhỏ và dễ review

Ưu tiên cập nhật từng nhóm liên quan. Nếu nâng đồng thời JDK, Gradle, Spring, Jackson và plugin test trong một thay đổi lớn, khi build lỗi sẽ khó xác định nguyên nhân.

### Bước 4: kiểm tra dependency graph

Xác nhận version được chọn, dependency bắc cầu và xung đột sau khi cập nhật. Không chỉ đọc version khai báo trực tiếp.

### Bước 5: chạy test theo rủi ro

Chạy compile, unit test, integration test, compatibility test hoặc full build tùy loại dependency. Thư viện serialization, database driver, security hoặc framework thường cần kiểm thử tích hợp phù hợp.

### Bước 6: cập nhật lockfile và verification metadata

Nếu dùng Gradle locking, ghi lock state mới. Nếu artifact mới cần dependency verification, xác minh checksum/chữ ký và cập nhật metadata sau review.

### Bước 7: review và hợp nhất

Review release note, changelog, kết quả CI, diff dependency graph và lý do nâng cấp. Sau khi chấp nhận, build thường quay lại dùng phiên bản đã khóa.

## 16. Tự động hóa phát hiện cập nhật

Các công cụ như Renovate hoặc Dependabot có thể định kỳ kiểm tra dependency và tạo pull request cập nhật version. Chúng giúp phát hiện bản mới đều đặn nhưng không thay thế việc review và kiểm thử.

Một cấu hình thực tế có thể:

- Gom các patch update ít rủi ro theo nhóm.
- Tách major update thành pull request riêng.
- Tạo pull request bảo mật ngay khi có cảnh báo phù hợp.
- Giới hạn số pull request mở đồng thời.
- Chạy compile/test và kiểm tra dependency convergence tự động.
- Yêu cầu review khi thay đổi BOM, plugin hoặc toolchain.

Không nên tự động merge mọi dependency update chỉ dựa trên việc version mới tồn tại. Cần cân nhắc mức độ quan trọng của thư viện, khả năng tương thích và chất lượng test của dự án.

## 17. Tách build thường ngày và job kiểm tra cập nhật

Một mô hình dễ vận hành là có hai loại pipeline:

```text
Pull request / commit build
    |
    +--> Dùng version và lockfile đã review
    +--> Không tự nâng dependency
    +--> Compile, test, package
    +--> Lưu kết quả có thể tái lập

Scheduled dependency update
    |
    +--> Kiểm tra version mới và advisory
    +--> Tạo thay đổi dependency
    +--> Cập nhật lockfile/verification metadata
    +--> Chạy test và phân tích graph
    +--> Mở PR để review
```

Nhờ vậy, build của một commit không tự đổi dependency theo thời gian. Khả năng cập nhật vẫn được duy trì qua một quy trình chủ động, có bằng chứng và có người chịu trách nhiệm.

## 18. Chính sách cho môi trường development, CI và release

Không phải mọi môi trường đều cần cùng mức độ linh hoạt.

| Môi trường | Chính sách dependency phù hợp |
|---|---|
| Local development thông thường | Dùng version đã commit và lockfile để tái hiện CI |
| Thử nghiệm nâng cấp | Có thể refresh metadata hoặc dùng snapshot trong nhánh riêng |
| Pull request CI | Dùng dependency đã được review; không tự resolve bản mới không kiểm soát |
| Scheduled update job | Chủ động tìm version mới, cập nhật lock state và tạo thay đổi reviewable |
| Release build | Ưu tiên release artifact bất biến, dependency graph đã khóa và verification đã thiết lập |
| Hotfix bảo mật | Có thể cập nhật ngoài lịch định kỳ nhưng vẫn cần kiểm tra graph và test liên quan |

Nếu một nhóm cần thử nghiệm snapshot, hãy đặt nó trong configuration hoặc pipeline phát triển riêng. Không để snapshot vô tình lan sang release build.

## 19. Ví dụ Gradle: pin, lock, verify và cập nhật

Giả sử ứng dụng dùng Jackson và một thư viện nội bộ.

`gradle/libs.versions.toml`:

```toml
[versions]
jackson = "2.17.2"
payment = "4.2.1"

[libraries]
jackson-bom = { module = "com.fasterxml.jackson:jackson-bom", version.ref = "jackson" }
jackson-databind = { module = "com.fasterxml.jackson.core:jackson-databind" }
payment-client = { module = "com.example:payment-client", version.ref = "payment" }
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
    maven {
        url = uri('https://repo.example.com/releases')
    }
}

dependencies {
    implementation platform(libs.jackson.bom)
    implementation libs.jackson.databind
    implementation libs.payment.client
}

dependencyLocking {
    lockAllConfigurations()
}
```

Quy trình:

```bash
# Resolve dependency và ghi lock state
./gradlew build --write-locks

# Kiểm tra dependency graph
./gradlew dependencies --configuration runtimeClasspath

# Chạy test theo cấu hình hiện tại
./gradlew test

# Khi chủ động cần refresh metadata từ repository
./gradlew build --refresh-dependencies
```

Sau lệnh refresh, nếu version được resolve thay đổi theo selector hoặc metadata, cần xem xét diff và cập nhật lock state bằng `--write-locks` sau khi đã quyết định chấp nhận thay đổi. Không dùng `--refresh-dependencies` như một bước mặc định trong mọi build CI.

## 20. Ví dụ Maven: quản lý release và snapshot riêng

Một dự án Maven có thể dùng release dependency trong build thông thường:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>payment-client</artifactId>
    <version>4.2.1</version>
</dependency>
```

Trong một profile development riêng, có thể tạm sử dụng snapshot:

```xml
<profiles>
    <profile>
        <id>use-payment-snapshot</id>
        <activation>
            <property>
                <name>usePaymentSnapshot</name>
            </property>
        </activation>
        <dependencies>
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>payment-client</artifactId>
                <version>4.3-SNAPSHOT</version>
            </dependency>
        </dependencies>
    </profile>
</profiles>
```

Ví dụ minh họa ý tưởng tách cấu hình phát triển; trong POM thực tế cần tránh khai báo trùng dependency gây khó hiểu và có thể dùng property/profile hoặc module riêng để quản lý rõ hơn.

Kích hoạt profile:

```bash
mvn -DusePaymentSnapshot=true -U verify
```

Release build không bật profile này và tiếp tục dùng release version đã được chấp nhận. Profile snapshot chỉ nên được sử dụng trong môi trường thử nghiệm được kiểm soát.

## 21. Xem dependency graph trước và sau khi cập nhật

### Gradle

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Để xem lý do một version được chọn:

```bash
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
```

`dependencies` cho thấy graph tổng thể của configuration. `dependencyInsight` tập trung vào một module, các yêu cầu version và constraint ảnh hưởng đến kết quả.

### Maven

```bash
mvn dependency:tree
```

Để xem cấu hình sau khi kế thừa parent POM, profile và dependency management:

```bash
mvn help:effective-pom
```

Khi review update, nên lưu lại hoặc so sánh dependency tree trước và sau. Điều này giúp phát hiện một dependency bắc cầu bị nâng hoặc bị loại bỏ ngoài dự kiến.

## 22. Kiểm tra security update mà không phá tính tái lập

Tính tái lập không nên trở thành lý do trì hoãn bản vá bảo mật. Ngược lại, cập nhật khẩn cấp không có kiểm soát có thể đưa thêm rủi ro vào production.

Một quy trình phản ứng:

1. Xác định dependency và phiên bản bị ảnh hưởng từ advisory đáng tin cậy.
2. Xác nhận project có thực sự sử dụng dependency đó, trực tiếp hay bắc cầu.
3. Tìm phiên bản đã vá và kiểm tra yêu cầu Java/API.
4. Cập nhật version hoặc BOM/constraint tại nơi quản lý chính sách.
5. Cập nhật lockfile và verification metadata sau khi xác minh artifact.
6. Chạy test phù hợp, đặc biệt các luồng sử dụng thư viện bị ảnh hưởng.
7. Review dependency graph và phát hành theo quy trình hotfix.
8. Lưu commit, build ID và artifact để truy vết.

Nếu advisory ảnh hưởng dependency bắc cầu, có thể cần nâng thư viện cha, cập nhật platform hoặc áp dụng constraint/exclusion có chủ đích. Không nên chỉ thêm một version override mà không xác nhận tương thích.

## 23. Repository và tính bất biến của artifact

Tính tái lập phụ thuộc vào cách repository quản lý artifact. Một release version nên bất biến: sau khi publish, cùng tọa độ phải luôn trỏ đến cùng nội dung.

Nếu repository cho phép ghi đè release artifact, một build dùng version pin vẫn có thể tải nội dung khác ở lần sau. Điều này làm suy yếu cả lockfile và khả năng truy vết.

Các nguyên tắc quản lý repository:

- Tách repository release và snapshot.
- Cấm redeploy/overwrite release artifact sau khi phát hành.
- Kiểm soát quyền publish và quyền thay đổi metadata.
- Giữ audit log hoặc thông tin provenance khi cần.
- Dùng HTTPS và xác thực repository phù hợp.
- Bật checksum/signature verification khi yêu cầu bảo đảm chuỗi cung ứng.
- Không đưa credential repository vào source code hoặc log.

Một repository nội bộ có thể proxy Maven Central và cache artifact để giảm phụ thuộc mạng, nhưng cần có chính sách đồng bộ, retention và xác minh rõ ràng.

## 24. Những lựa chọn dễ làm mất tính tái lập

| Lựa chọn | Rủi ro | Cách kiểm soát |
|---|---|---|
| `latest.release` hoặc `1.+` trong build phát hành | Version có thể đổi theo thời gian | Pin version và dùng lockfile |
| Maven version range | Resolution có thể chọn bản mới khi repository thay đổi | Dùng exact version/BOM hoặc kiểm soát kết quả resolve |
| SNAPSHOT trong release build | Nội dung có thể đổi dù version string giữ nguyên | Dùng release artifact bất biến |
| Không commit lockfile | Máy khác có thể resolve graph khác | Bật dependency locking và commit lock state |
| Không xác minh artifact | Artifact cùng tọa độ có thể bị thay đổi hoặc thay thế | Dependency verification và repository policy |
| Không pin plugin/build tool | Task behavior có thể thay đổi sau lần resolve khác | Pin plugin version và wrapper distribution |
| Không kiểm soát JDK | Compiler/toolchain có thể khác giữa local và CI | Khai báo toolchain và chuẩn hóa môi trường |
| Tự refresh mọi build | Build thường ngày phụ thuộc repository và mạng | Chỉ refresh trong workflow cập nhật/chẩn đoán |
| Giữ snapshot quá lâu | Khó biết chính xác nội dung đã được dùng | Chỉ dùng snapshot cho development, ghi build metadata |

## 25. Những lựa chọn làm dependency quá cũ

Ngược lại, khóa version mà không có quy trình cập nhật cũng tạo ra rủi ro:

- Bỏ lỡ bản vá bảo mật.
- Dùng API đã deprecated hoặc không còn được hỗ trợ.
- Khó nâng JDK vì thư viện cũ không tương thích.
- Tích lũy nhiều major update khiến migration trở nên lớn và tốn kém.
- Không nhận được bug fix cho lỗi đã biết.
- Các dependency cũ có thể bị repository loại bỏ hoặc không còn được nhà cung cấp hỗ trợ.

Vì vậy, lockfile cần được cập nhật theo lịch. Có thể đặt lịch hàng tuần hoặc hàng tháng tùy mức độ thay đổi của hệ sinh thái và yêu cầu bảo mật. Dependency quan trọng hoặc có advisory nên được theo dõi thường xuyên hơn.

## 26. Một chính sách cân bằng cho nhóm phát triển

Một chính sách đơn giản nhưng có thể vận hành:

**Trong build thông thường:**

- Dùng exact release version hoặc BOM/platform đã được review.
- Bật dependency locking cho các configuration cần tái lập.
- Commit lockfile và verification metadata nếu dự án áp dụng.
- Pin Gradle/Maven wrapper, plugin và JDK/toolchain.
- Không tự refresh dependency ở mọi lần chạy.

**Trong quy trình cập nhật:**

- Kiểm tra version mới theo lịch và advisory bảo mật.
- Tạo PR riêng cho patch/minor/major hoặc nhóm dependency liên quan.
- Review release note, dependency graph và compatibility.
- Cập nhật lockfile cùng thay đổi version policy.
- Chạy test và kiểm tra artifact.

**Trong release:**

- Không dùng snapshot hoặc dynamic selector không được kiểm soát.
- Dùng artifact release bất biến.
- Xác nhận lock state và verification thành công.
- Ghi lại commit, toolchain, build tool và dependency metadata.

Chính sách này giữ build ổn định nhưng vẫn tạo cơ hội cập nhật đều đặn.

## 27. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Pin version trực tiếp là đã khóa toàn bộ graph | Dependency bắc cầu và metadata vẫn cần được quản lý; dùng locking khi cần cố định kết quả resolve. |
| Lockfile bảo đảm artifact không thể bị thay đổi | Lockfile ghi version; repository bất biến và dependency verification bảo vệ nội dung artifact. |
| Version catalog tự khóa dependency | Catalog tập trung alias/version; locking là cơ chế riêng. |
| BOM tự thêm mọi thư viện vào classpath | BOM quản lý version; module vẫn khai báo dependency cần dùng. |
| `--refresh-dependencies` luôn tải lại mọi JAR | Gradle làm mới trạng thái cache và kiểm tra cần thiết; artifact khớp checksum có thể được tái sử dụng. |
| SNAPSHOT là một release cố định | Snapshot có thể được cập nhật dưới cùng version string. |
| Build ổn định nghĩa là không bao giờ nâng dependency | Nên khóa trong mỗi build đã chấp nhận và cập nhật theo quy trình riêng. |
| Cập nhật tự động có thể merge mà không cần test | Bot giúp phát hiện/tạo PR; compatibility và test vẫn cần được kiểm tra. |
| Cùng dependency version đồng nghĩa build byte-for-byte giống nhau | JDK, plugin, OS, timestamp, locale và cấu hình cũng có thể làm artifact khác. |

## 28. Checklist cho một thay đổi dependency

Trước khi chấp nhận một bản cập nhật, hãy xác định:

1. Dependency là direct hay transitive?
2. Nó được quản lý bằng version trực tiếp, version catalog, platform/BOM hay parent POM?
3. Phiên bản mới có thay đổi yêu cầu JDK, API hoặc hành vi không?
4. Có breaking changes hoặc security advisory liên quan không?
5. Dependency graph sau cập nhật có version conflict không?
6. Lockfile đã được cập nhật và diff có hợp lý không?
7. Artifact mới đã được xác minh theo checksum/chữ ký nếu dự án yêu cầu chưa?
8. Plugin, wrapper và toolchain có bị thay đổi ngoài dự kiến không?
9. Unit, integration và contract test phù hợp đã chạy chưa?
10. Build release có dùng release artifact bất biến và tránh snapshot không?
11. CI và máy phát triển có resolve cùng dependency graph không?
12. Thay đổi có thể truy vết theo commit và build metadata không?

## 29. Checklist cho tính tái lập dài hạn

- Version dependency trực tiếp được quản lý rõ ràng.
- Dependency bắc cầu được kiểm soát bằng platform/BOM, constraints và/hoặc locking.
- Lockfile được commit và cập nhật có chủ đích.
- Artifact repository không ghi đè release version.
- Dependency verification được cấu hình khi cần bảo đảm nội dung artifact.
- Không dùng dynamic version hoặc snapshot không kiểm soát trong release.
- Gradle/Maven wrapper và plugin version được pin.
- JDK/toolchain được khai báo nhất quán.
- Build không phụ thuộc dữ liệu mạng hoặc thời gian hiện tại ngoài các input đã khai báo.
- Artifact archive được cấu hình theo hướng reproducible khi yêu cầu.
- Có quy trình cập nhật dependency định kỳ và xử lý security update.
- CI lưu lại dependency graph, lock state và metadata của build khi cần truy vết.

## 30. Nguyên tắc áp dụng trong thực tế

Tính tái lập và khả năng cập nhật không cần loại trừ nhau. Hãy giữ dependency của một build đã được chấp nhận ở trạng thái xác định bằng version policy, lockfile, repository bất biến và verification phù hợp. Đồng thời, tổ chức một quy trình riêng để thường xuyên phát hiện bản mới, đánh giá rủi ro, cập nhật dependency, chạy test và review thay đổi.

Gradle cung cấp version catalog, platform, dependency constraints, dependency locking, dependency verification và cache refresh để hỗ trợ các phần khác nhau của quy trình. Maven dùng exact version, BOM, `dependencyManagement`, repository update policy và các plugin kiểm tra dependency để quản lý resolution. Dù dùng công cụ nào, nguyên tắc chung là: **build thông thường phải ổn định; việc cập nhật phải chủ động, có kiểm chứng và có thể truy vết**.
