# Quản lý dependency lock, provenance và cập nhật bảo mật của JDK

Build Java 21 có thể thay đổi kết quả theo thời gian nếu dependency dùng version range hoặc dynamic version, plugin build tự cập nhật, JDK trên CI không được kiểm soát, hoặc artifact tải về bị thay thế. Một pipeline an toàn cần trả lời ba câu hỏi: build đã dùng dependency và JDK nào; artifact đến từ đâu và có đúng nội dung được phê duyệt không; khi có bản vá bảo mật mới, nhóm phát triển phát hiện, kiểm thử và triển khai như thế nào.

Ba câu hỏi này không thể giải quyết bằng một file lock duy nhất. Dependency lock cố định phiên bản đã resolve; checksum/signature kiểm tra artifact; provenance ghi lại nguồn và quá trình tạo artifact; quy trình cập nhật JDK bảo đảm runtime không ở lại trên security baseline cũ.

## 1. Phân biệt dependency lock, verification và provenance

| Cơ chế | Bảo đảm chính | Không tự bảo đảm |
|---|---|---|
| Dependency locking | Cùng build resolve cùng phiên bản module đã khóa | Artifact tải về đúng nội dung hoặc an toàn |
| Checksum verification | Nội dung artifact khớp digest đã được phê duyệt | Người tạo artifact là ai nếu digest lấy từ nguồn không đáng tin |
| Signature verification | Artifact được ký bởi khóa công khai được tin cậy | Khóa ký chưa bị xâm phạm hoặc mã nguồn không có lỗ hổng |
| SBOM | Liệt kê component, phiên bản và quan hệ dependency | Nguồn gốc build hoặc tính toàn vẹn của artifact |
| Build provenance/attestation | Ghi nhận source, builder, quy trình và materials tạo ra output | Output tự động an toàn; attestation vẫn cần được xác minh |

Một quy trình supply-chain tốt kết hợp các lớp này. Lockfile giúp review việc nâng phiên bản, verification metadata phát hiện JAR bị thay đổi, SBOM giúp tra cứu component bị ảnh hưởng bởi CVE, còn provenance giúp xác minh artifact được tạo từ commit và workflow đã được chấp thuận.

## 2. Vì sao phải khóa dependency đã resolve?

Một khai báo dependency dùng version động có thể resolve ra kết quả khác ở những lần build khác nhau:

~~~kotlin
dependencies {
    // Version động: kết quả có thể thay đổi khi repository xuất hiện bản mới.
    implementation("org.example:library:1.+")
}
~~~

Khi phiên bản mới được publish, cùng một commit có thể resolve sang dependency khác. Dependency bắc cầu cũng có thể thay đổi do graph hoặc metadata repository thay đổi.

Với build release, nên:

- Khai báo version rõ ràng hoặc dùng BOM đã được pin phiên bản.
- Khóa phiên bản đã resolve, gồm cả dependency bắc cầu.
- Pin version của build plugin và công cụ build.
- Tránh SNAPSHOT, latest.release, version range và dynamic version trong artifact phát hành.
- Review lockfile khi nâng cấp dependency; không tự động chấp nhận thay đổi không rõ nguyên nhân.

Locking làm cho thay đổi dependency trở thành một diff có thể review. Nó không có nghĩa giữ dependency cũ mãi mãi: lockfile phải được cập nhật có chủ đích để nhận bản vá bảo mật.

## 3. Bật dependency locking trong Gradle

Gradle hỗ trợ dependency locking cho các configuration. Có thể bật khóa cho mọi configuration trong build.gradle.kts:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau đó chạy build để ghi lại các phiên bản đã resolve:

~~~bash
./gradlew dependencies --write-locks
~~~

Gradle tạo file lock như gradle.lockfile ở project hoặc subproject tương ứng. Đưa lockfile vào version control để các máy developer và CI dùng cùng resolved versions.

Ví dụ một lockfile có dạng:

~~~text
org.example:library:1.8.4=compileClasspath,runtimeClasspath
org.example:codec:2.3.1=runtimeClasspath
empty=
~~~

Định dạng thực tế do Gradle sinh ra; không nên tự viết hoặc chỉnh lockfile bằng tay nếu không hiểu configuration liên quan. Khi thêm dependency hoặc đổi version, chạy build với --write-locks, review diff rồi commit lockfile cùng thay đổi build script.

Các lưu ý:

- Lock chỉ ghi các configuration thực sự được resolve trong build đã chạy.
- Chạy task khác có thể resolve configuration chưa xuất hiện trong lockfile.
- Plugin DSL, plugin management và build logic cần được pin/kiểm soát riêng. lockAllConfigurations() áp dụng cho project configurations nhưng không tự khóa buildscript classpath; nếu cần khóa classpath của script plugin, phải bật locking cho configuration đó trong buildscript.
- Dynamic version vẫn có thể xuất hiện trong quá trình phát triển, nhưng release build nên dùng lock state đã review.

Ví dụ bật locking cho classpath của buildscript:

~~~kotlin
buildscript {
    configurations.classpath {
        resolutionStrategy.activateDependencyLocking()
    }
}
~~~

## 4. Khóa dependency và xác minh artifact trong Gradle là hai việc riêng

Gradle dependency locking cố định **version**. Dependency verification kiểm tra **artifact được tải về** có khớp checksum hoặc chữ ký đã phê duyệt không.

File cấu hình verification nằm tại:

~~~text
gradle/verification-metadata.xml
~~~

Có thể tạo metadata checksum SHA-256 cho các dependency và plugin đã được resolve:

~~~bash
./gradlew --write-verification-metadata sha256 help
~~~

Nếu nhà phát hành cung cấp PGP signature và nhóm có quy trình xác minh key phù hợp, có thể tạo metadata cho cả checksum và chữ ký:

~~~bash
./gradlew --write-verification-metadata sha256,pgp help
~~~

Khi file verification metadata tồn tại, Gradle áp dụng kiểm tra cho các artifact thuộc dependency management. Chế độ mặc định là **strict**; checksum hoặc signature không khớp sẽ làm build thất bại.

Không dùng kết quả bootstrap một cách mù quáng. Lệnh tạo metadata lấy artifact từ repository hiện tại rồi ghi digest tương ứng. Nếu repository hoặc artifact đã bị xâm phạm trước lúc bootstrap, digest được sinh ra có thể phê duyệt chính artifact độc hại đó. Hãy review nguồn tải, checksum/signature độc lập và diff của verification-metadata.xml trước khi commit.

Checksum SHA-256/SHA-512 phù hợp cho kiểm tra toàn vẹn hiện nay. Không dùng MD5 hoặc SHA-1 làm cơ chế xác minh bảo mật mới.

Gradle không xác minh các dependency thay đổi như SNAPSHOT theo cùng cơ chế này, vì nội dung của chúng có thể thay đổi. Đây là thêm một lý do để không dùng SNAPSHOT trong release build.

## 5. Kiểm soát plugin và repository

Plugin build có quyền thực thi trong quá trình build, vì vậy cần được quản lý như dependency quan trọng:

- Pin version trong plugins {} hoặc pluginManagement {}.
- Không dùng version động cho plugin trong release build.
- Giới hạn repository được phép resolve plugin và dependency.
- Ưu tiên repository manager nội bộ có audit, cache và chính sách allowlist.
- Bật dependency verification cho plugin artifacts nếu dùng Gradle.
- Review thay đổi build logic, convention plugin, buildSrc và included build như review mã ứng dụng.

Không nên để build tự lấy dependency từ repository bất kỳ do từng project hoặc plugin thêm vào. Repository không được kiểm soát làm tăng nguy cơ dependency confusion và khiến provenance khó xác minh.

## 6. Quản lý dependency trong Maven

Maven quản lý dependency bằng POM, dependencyManagement, BOM và cơ chế mediation của dependency graph. Maven không tự sinh một lockfile chuẩn theo mô hình gradle.lockfile của Gradle; dependencyManagement/BOM quản lý version được khai báo nhưng không tự ghi lại toàn bộ graph đã resolve thành một lock state. Không nên giả định pom.xml tự động đóng vai trò lockfile tương đương Gradle.

Maven chọn dependency bắc cầu theo quy tắc mediation, thường ưu tiên định nghĩa gần root nhất trong dependency tree. Vì vậy, thêm một dependency khác có thể làm thay đổi version được chọn dù version khai báo trực tiếp không đổi. Enforcer convergence và dependency tree giúp phát hiện, giải thích thay đổi đó.

Để build Maven dễ tái lập hơn:

- Khai báo version tường minh cho dependency trực tiếp.
- Import BOM có version cố định để quản lý một nhóm dependency tương thích.
- Pin version của Maven plugin trong build/plugins và pluginManagement.
- Tránh SNAPSHOT, version range và version không xác định trong release.
- Dùng Maven Enforcer để kiểm tra dependency convergence, upper bounds và phiên bản JDK.
- Kiểm soát repository/mirror trong Maven settings và repository manager.
- Lưu kết quả dependency tree hoặc SBOM cùng thông tin build để hỗ trợ điều tra.

Ví dụ import một BOM với version cố định:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.example</groupId>
            <artifactId>platform-bom</artifactId>
            <version>1.2.3</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Pin version BOM giúp quản lý tập phiên bản dependency nhất quán. Tuy nhiên, cần kiểm tra dependency tree sau khi nâng BOM vì một BOM có thể thay đổi nhiều dependency bắc cầu cùng lúc.

## 7. Dùng Maven Enforcer để chặn dependency graph không nhất quán

Maven Enforcer Plugin có các rule hữu ích:

- dependencyConvergence: phát hiện cùng một dependency bị resolve thành nhiều version trong graph.
- requireUpperBoundDeps: kiểm tra version được chọn không thấp hơn version cao hơn được yêu cầu từ nhánh bắc cầu.
- requireJavaVersion: kiểm tra JDK chạy Maven nằm trong miền phiên bản cho phép.
- requirePluginVersions: yêu cầu plugin được khai báo version rõ ràng.

Ví dụ cấu hình:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-enforcer-plugin</artifactId>
            <version>3.6.3</version>
            <executions>
                <execution>
                    <id>enforce-build-policy</id>
                    <goals>
                        <goal>enforce</goal>
                    </goals>
                    <configuration>
                        <rules>
                            <requireJavaVersion>
                                <version>[21,22)</version>
                            </requireJavaVersion>
                            <dependencyConvergence/>
                            <requireUpperBoundDeps/>
                            <requirePluginVersions/>
                        </rules>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Rule convergence có thể phát hiện xung đột version nhưng không tự chứng minh dependency an toàn. Rule upper bound cũng không có nghĩa version mới hơn luôn tốt hơn; compatibility, CVE, release notes và test vẫn phải được đánh giá.

Kiểm tra dependency tree khi cần hiểu nguồn của một dependency bắc cầu:

~~~bash
mvn dependency:tree
~~~

## 8. Pin Maven Wrapper và công cụ build

Maven Wrapper giúp nhóm thống nhất phiên bản Maven được sử dụng thay vì phụ thuộc Maven cài sẵn trên máy developer hoặc runner.

Trong .mvn/wrapper/maven-wrapper.properties, pin distribution URL và checksum:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.11/apache-maven-3.9.11-bin.zip
distributionSha256Sum=<sha256-da-duoc-xac-minh-tu-nguon-tin-cay>
~~~

Checksum phải được lấy và xác minh từ nguồn phát hành đáng tin cậy, không lấy từ cùng một mirror chưa được kiểm soát với file tải về. Version Maven Wrapper và wrapper JAR cũng là một phần của toolchain cần được review, cập nhật và kiểm soát trong source control.

Gradle cũng nên dùng Gradle Wrapper với distribution version cố định và checksum distribution được cấu hình trong gradle-wrapper.properties. Không để CI tự chọn bản Gradle mới nhất theo thời gian.

## 9. Phân biệt version Java 21 với patch version của JDK

Java toolchain yêu cầu Java 21 thường chỉ bảo đảm major release, không tự động pin chính xác vendor, patch level và build number.

Ví dụ cấu hình Gradle:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Cấu hình trên chọn toolchain thuộc Java 21. Nếu cần cố định vendor, có thể thêm tiêu chí vendor phù hợp với chính sách tổ chức. Tuy vậy, để pin chính xác patch/build, cần kiểm soát nguồn provision JDK hoặc dùng build image bất biến có digest.

CI nên ghi lại ít nhất:

~~~bash
java -version
javac -version
./gradlew --version
~~~

Với Maven:

~~~bash
java -version
javac -version
./mvnw --version
~~~

Tùy chọn --release 21 trong compiler cấu hình API/language/bytecode target của Java 21; nó không tự chọn JDK patch version và cũng không pin runtime production. Hãy quản lý riêng:

1. JDK dùng để chạy build.
2. Java release target dùng để compile.
3. JDK/JRE hoặc runtime image dùng để chạy ứng dụng.

## 10. Xác minh nguồn gốc và tính toàn vẹn của JDK

JDK là một dependency quan trọng của build và runtime. Một JDK bị thay thế có thể ảnh hưởng compiler, test, signing, packaging và ứng dụng được triển khai.

Khi chọn JDK distribution:

- Chọn vendor/build phù hợp chính sách support, licensing, kiến trúc CPU và hệ điều hành.
- Tải từ trang phát hành hoặc repository được tổ chức phê duyệt.
- Xác minh checksum SHA-256 hoặc chữ ký số theo hướng dẫn của vendor.
- Lưu lại vendor, version đầy đủ, build number, OS/architecture và digest.
- Dùng cùng JDK đã được xác minh ở CI và môi trường build release.
- Với container, pin image bằng digest SHA-256, không chỉ pin tag có thể bị thay đổi.

Ví dụ Dockerfile:

~~~dockerfile
FROM registry.example.com/build/jdk21@sha256:<image-digest>

WORKDIR /workspace
COPY . .
RUN ./gradlew --no-daemon clean check
~~~

Tên image và digest trong ví dụ là placeholder. Hãy dùng image đã được tổ chức phê duyệt và lưu digest thực tế trong source control hoặc cấu hình pipeline. Tag như jdk21:latest không đủ để tái lập build.

Lệnh java -version giúp ghi nhận version mà JVM báo cáo, nhưng không xác minh nguồn gốc binary. Cần checksum/signature hoặc attestation riêng.

## 11. Hiểu provenance của dependency và build artifact

Provenance mô tả nguồn gốc và quá trình tạo ra một artifact. Với dependency bên thứ ba, thông tin hữu ích gồm:

- Tọa độ dependency: group, artifact, version, classifier và packaging.
- Repository hoặc registry đã cung cấp artifact.
- SHA-256 digest của file đã tải.
- Chữ ký và fingerprint của khóa ký nếu artifact được ký.
- SBOM hoặc metadata mô tả dependency bắc cầu.

Với artifact do pipeline tạo ra, provenance nên ghi:

- Repository và commit source đã build.
- Workflow/pipeline identity và builder image digest.
- Phiên bản JDK, build tool và plugin.
- Các dependency/materials cùng digest.
- Tham số build quan trọng và kết quả đầu ra cùng digest.

Có thể dùng định dạng attestation theo in-toto/SLSA provenance để máy có thể kiểm tra các trường này. Attestation nên được ký và lưu cùng release artifact hoặc trong registry hỗ trợ OCI referrers/attestations.

Không nhầm provenance với SBOM: SBOM cho biết artifact chứa gì; provenance cho biết artifact được tạo từ đâu và bằng quy trình nào. Hai tài liệu bổ sung cho nhau.

## 12. Kiểm tra checksum, signature và chữ ký số đúng cách

Checksum chỉ có ý nghĩa khi giá trị kỳ vọng đến từ nguồn độc lập đáng tin cậy. Nếu tải JAR và file checksum từ cùng một repository đã bị xâm phạm, kẻ tấn công có thể thay cả hai.

Quy trình xác minh nên:

1. Tải artifact từ repository đã allowlist.
2. Lấy checksum hoặc signature từ kênh phát hành chính thức.
3. Nếu dùng signature, xác minh fingerprint của public key qua kênh độc lập.
4. Tính SHA-256 của artifact đã tải và so sánh với digest đã phê duyệt.
5. Lưu digest cùng lock/verification metadata hoặc manifest release.
6. Chặn pipeline nếu verification thất bại.

Checksum bảo vệ tính toàn vẹn của nội dung. Signature liên kết artifact với một khóa ký. Cả hai không thay thế kiểm tra CVE hoặc review mã nguồn.

## 13. Sinh và lưu SBOM cho release

SBOM (Software Bill of Materials) là danh sách component của phần mềm. Hai định dạng phổ biến hiện nay là **CycloneDX** và **SPDX**.

Một SBOM hữu ích nên chứa:

- Tên và version của dependency trực tiếp/bắc cầu.
- Package URL (purl) hoặc định danh component tương ứng.
- License nếu có dữ liệu.
- Checksum/digest khi công cụ hỗ trợ.
- Quan hệ dependency và thông tin tool tạo SBOM.

Nên sinh SBOM cho từng release artifact và lưu nó cùng digest của artifact. Khi một thư viện có CVE, có thể truy vấn SBOM để tìm các ứng dụng bị ảnh hưởng.

SBOM ứng dụng Java thường liệt kê dependency trong package; nếu runtime image chứa JDK, cần tạo hoặc lấy thêm SBOM cho container/base image để nhìn thấy JDK và các package hệ điều hành. Không giả định SBOM JAR tự động bao phủ toàn bộ runtime.

## 14. Quản lý cập nhật bảo mật của dependency

Lockfile giúp cố định phiên bản, nhưng nếu không cập nhật lockfile thì lỗ hổng đã biết vẫn còn. Vì vậy, phải có quy trình refresh dependency định kỳ và xử lý bản vá khẩn cấp:

1. Quét dependency trực tiếp, bắc cầu, plugin build và image runtime.
2. Nhận cảnh báo từ vendor/advisory database và công cụ SCA.
3. Xác định component, phiên bản bị ảnh hưởng, mức độ nghiêm trọng và khả năng khai thác trong ứng dụng.
4. Chọn bản vá hoặc version thay thế được vendor khuyến nghị.
5. Cập nhật dependency declaration và lockfile/verification metadata.
6. Review diff dependency tree, release notes và breaking changes.
7. Chạy unit, integration, security và compatibility tests.
8. Tạo artifact mới, SBOM/provenance mới rồi triển khai theo rollout có kiểm soát.

Không chỉ quét dependency runtime. Maven/Gradle plugin, compiler, test framework, annotation processor, build container và CI action đều có thể chạy mã trong pipeline.

## 15. Cập nhật bảo mật JDK 21 theo vendor

JDK 21 là LTS, nhưng LTS không có nghĩa một patch build có thể dùng vô thời hạn. Vendor phát hành các bản update chứa security fix, bug fix và cập nhật dữ liệu nền tảng. Nhóm phát triển cần theo dõi advisory và security baseline của đúng vendor đang dùng.

Quy trình cập nhật JDK:

- Duy trì inventory các JDK build ở developer image, CI runner, build container, staging, production và công cụ đóng gói.
- Theo dõi release notes, CPU/security advisory và thông báo hỗ trợ của vendor.
- Đánh giá CVE theo cả mức độ nghiêm trọng lẫn bề mặt sử dụng trong ứng dụng.
- Cập nhật JDK build trong CI và runtime image; tránh chỉ cập nhật máy developer.
- Chạy test tương thích, TLS/network, serialization, native library và performance regression phù hợp.
- Triển khai canary hoặc theo từng nhóm dịch vụ; có kế hoạch rollback sang image đã được phê duyệt nếu phát sinh lỗi.
- Ghi lại version cũ/mới, digest, advisory liên quan, kết quả test và thời điểm triển khai.

Lịch phát hành khác nhau theo vendor và có thể thay đổi. Oracle thông báo trong năm 2026 kế hoạch tăng các bản security update có mục tiêu theo tháng trong giai đoạn 2027, bên cạnh lịch CPU định kỳ. Đây là chính sách của Oracle, không phải lịch bắt buộc cho mọi OpenJDK distribution. Hãy theo dõi kênh bảo mật chính thức của vendor thực tế thay vì chỉ dựa vào lịch quý cố định.

License và thời hạn support cũng có thể khác theo vendor, build và thời điểm phát hành. Ví dụ, Oracle đã thông báo thay đổi điều khoản license cho các bản Oracle JDK 21 phát hành từ tháng 10 năm 2026. Trước khi chuẩn hóa JDK trong CI hoặc phân phối runtime, hãy xác minh license và quyền sử dụng của đúng binary được chọn.

## 16. Tổ chức CI để khóa và cập nhật có kiểm soát

Một pipeline release có thể chia thành các giai đoạn:

~~~mermaid
flowchart TD
    A[Checkout commit] --> B[Chọn JDK và build tool đã pin]
    B --> C[Resolve dependency theo lock state]
    C --> D[Verify checksum và signature]
    D --> E[Compile, test và security scan]
    E --> F[Generate SBOM và provenance]
    F --> G[Package và ký artifact]
    G --> H[Publish theo digest]
    H --> I[Deploy canary và theo dõi]
    I --> J[Rollout hoặc rollback]
~~~

CI nên fail sớm khi:

- Lockfile không khớp với dependency declaration.
- Artifact checksum/signature không khớp verification metadata.
- Build tool hoặc JDK không đúng version policy.
- Dependency/plugin vi phạm Enforcer rule hoặc security policy.
- SBOM/provenance thiếu trường bắt buộc hoặc không xác minh được chữ ký.

Quy trình update dependency/JDK nên chạy riêng theo lịch hoặc khi có advisory, tạo pull request có diff rõ ràng để review. Không tự động sửa lockfile và deploy production chỉ vì có version mới.

## 17. Checklist cho build Java 21 an toàn

- [ ] Pin version dependency trực tiếp, bắc cầu và build plugin.
- [ ] Bật Gradle dependency locking hoặc dùng BOM/Enforcer và quy trình kiểm soát graph phù hợp với Maven.
- [ ] Commit lockfile vào version control và review mỗi lần cập nhật.
- [ ] Bật Gradle dependency verification hoặc xác minh checksum/signature bằng quy trình tương ứng.
- [ ] Không bootstrap checksum từ repository chưa được xác minh.
- [ ] Chỉ resolve artifact từ repository/registry được allowlist.
- [ ] Pin Maven/Gradle Wrapper và xác minh checksum distribution.
- [ ] Ghi rõ JDK vendor, version/build, OS/architecture và digest.
- [ ] Phân biệt toolchain Java 21, compiler --release 21 và runtime production.
- [ ] Pin container image bằng digest thay vì chỉ dùng mutable tag.
- [ ] Sinh SBOM cho release và runtime image.
- [ ] Sinh, ký và xác minh build provenance/attestation.
- [ ] Quét CVE cả dependency, plugin, build image và JDK runtime.
- [ ] Có lịch cập nhật JDK theo advisory của vendor và quy trình xử lý khẩn cấp.
- [ ] Kiểm thử, rollout có kiểm soát và ghi lại quyết định nâng cấp.

## Tài liệu tham khảo

- [Gradle: Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle: Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Apache Maven Enforcer: Dependency Convergence](https://maven.apache.org/components/enforcer/enforcer-rules/dependencyConvergence.html)
- [Apache Maven Enforcer: Require Upper Bound Dependencies](https://maven.apache.org/components/enforcer/enforcer-rules/requireUpperBoundDeps.html)
- [Apache Maven Wrapper](https://maven.apache.org/wrapper/)
- [SLSA: Provenance](https://slsa.dev/spec/v1.1/provenance)
- [in-toto Attestation Framework](https://github.com/in-toto/attestation)
- [CycloneDX Specification](https://cyclonedx.org/specification/overview/)
- [Oracle: Transitioning Java to More Frequent Security Updates](https://blogs.oracle.com/java/transitioning-java-to-more-frequent-security-updates)
- [Oracle: Consolidated JDK 21 Release Notes](https://www.oracle.com/java/technologies/javase/21all-relnotes.html)
- [OpenJDK: JDK Release Information](https://ops.java/releases/)
