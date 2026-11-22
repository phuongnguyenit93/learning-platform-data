# Kiểm tra dependency và plugin codegen

Trong một dịch vụ Spring gRPC, mã nguồn ứng dụng chỉ là một phần của chuỗi cung ứng phần mềm. Quá trình build còn tải thư viện Spring và gRPC, chạy plugin của Gradle hoặc Maven, gọi trình biên dịch Protocol Buffers (`protoc`) và plugin sinh mã gRPC như `protoc-gen-grpc-java`. Các thành phần chạy trong lúc build có thể thực thi mã trên máy phát triển hoặc runner CI, vì vậy chúng cũng cần được kiểm soát như dependency lúc chạy.

Mục tiêu của việc kiểm tra là biết chính xác thành phần nào được tải, phiên bản đến từ đâu, các phiên bản có tương thích hay không, artifact có bị thay thế hay không và có lỗ hổng đã biết nào cần xử lý. Với Spring gRPC, cần kiểm tra riêng thư viện runtime, plugin build và công cụ sinh mã; một BOM quản lý thư viện runtime không tự động khóa phiên bản plugin hoặc `protoc`.

## 1. Nhận diện các thành phần trong chuỗi build

| Nhóm | Ví dụ trong dự án Spring gRPC | Nội dung cần kiểm tra |
|---|---|---|
| Thư viện ứng dụng | Spring gRPC starter, `grpc-protobuf`, `grpc-stub`, `grpc-netty-shaded`, `protobuf-java` | Phiên bản trực tiếp và bắc cầu, nguồn artifact, CVE, khả năng tương thích với Spring Boot và JDK |
| Plugin build | `com.google.protobuf` của Gradle hoặc `protobuf-maven-plugin`; Spring Boot Gradle/Maven plugin | Phiên bản plugin, plugin dependency, repository phân phối và checksum |
| Công cụ codegen | `com.google.protobuf:protoc`, `io.grpc:protoc-gen-grpc-java` | Phiên bản compiler/generator, artifact theo hệ điều hành và kiến trúc, tính toàn vẹn của binary |
| Mã được sinh | Java message class và gRPC stub từ các file `.proto` | Mã được sinh từ schema và toolchain đã duyệt; build lại phải cho kết quả nhất quán |

`protoc` và `protoc-gen-grpc-java` là hai công cụ khác nhau: `protoc` đọc schema Protocol Buffers, còn plugin gRPC sinh service descriptor, client stub và server base class. Plugin Gradle/Maven điều phối quá trình này. Nếu chỉ kiểm tra `runtimeClasspath` thì có thể bỏ sót rủi ro nằm trong plugin hoặc binary codegen.

Các module gRPC nên dùng một bộ phiên bản đã được xác nhận tương thích. Có thể dùng `io.grpc:grpc-bom` để đồng bộ các thư viện runtime của gRPC. BOM này không quản lý phiên bản plugin Gradle/Maven, `protoc` hay `protoc-gen-grpc-java`; các thành phần đó vẫn phải được khai báo và duyệt riêng. Phiên bản Spring gRPC starter cần theo bộ phiên bản Spring Boot mà dự án hỗ trợ.

## 2. Nguyên tắc kiểm soát dependency

**Khai báo phiên bản tường minh.** Không dùng phiên bản động như `1.+`, `latest.release`, khoảng phiên bản rộng hoặc snapshot trong build phát hành. Khóa phiên bản của plugin, compiler, generator và thư viện. Khi nâng cấp, thay đổi có chủ đích theo từng nhóm để có thể xác định thành phần nào làm thay đổi dependency graph.

**Giới hạn nguồn tải artifact.** Chỉ cấu hình repository được tổ chức chấp thuận, chẳng hạn Maven Central hoặc mirror nội bộ. Không thêm repository tùy tiện từ một URL trong hướng dẫn trên mạng. Kiểm tra cả repository dùng để resolve plugin và repository dùng để resolve thư viện: Gradle có `pluginManagement.repositories` riêng; Maven có thể cấu hình mirror trong `settings.xml`.

**Khóa kết quả resolve và xác minh tính toàn vẹn.** Lockfile ghi lại phiên bản dependency đã được chọn; checksum hoặc chữ ký giúp phát hiện artifact khác với artifact đã duyệt. Lockfile không chứng minh artifact an toàn, còn checksum chỉ có ý nghĩa khi giá trị chuẩn được lấy từ nguồn đáng tin cậy và được review.

**Kiểm tra dependency bắc cầu.** Một thư viện trực tiếp có thể kéo theo nhiều thư viện khác. Cần xem toàn bộ cây dependency, xác định lý do một phiên bản được chọn và phát hiện xung đột. Tránh dùng `force` hoặc exclusion toàn cục chỉ để làm build xanh khi chưa hiểu tác động.

**Tách quyền của build khỏi quyền vận hành.** Plugin và codegen chạy trong môi trường build. CI nên dùng runner có vòng đời ngắn, quyền ghi tối thiểu và không cấp secret triển khai hoặc credential production cho job chạy mã từ pull request chưa tin cậy.

## 3. Kiểm tra với Gradle

### 3.1. Khóa phiên bản runtime và codegen

Ví dụ dưới đây dùng Gradle Kotlin DSL. Các chuỗi trong dấu `<...>` là chỗ điền phiên bản đã được nhóm dự án phê duyệt; không sao chép chúng thành phiên bản thực tế.

```kotlin
plugins {
    java
    id("com.google.protobuf") version "<pinned-protobuf-gradle-plugin-version>"
}

val grpcVersion = "<approved-grpc-version>"
val protobufVersion = "<approved-protobuf-version>"

dependencies {
    // BOM đồng bộ các thư viện runtime của gRPC.
    implementation(platform("io.grpc:grpc-bom:$grpcVersion"))
    implementation("io.grpc:grpc-protobuf")
    implementation("io.grpc:grpc-stub")
    runtimeOnly("io.grpc:grpc-netty-shaded")

    // Khai báo Spring gRPC starter theo BOM/ma trận tương thích
    // Spring Boot được dự án sử dụng.
}

protobuf {
    // Compiler Protocol Buffers.
    protoc {
        artifact = "com.google.protobuf:protoc:$protobufVersion"
    }

    // Generator tạo Java service stub cho gRPC.
    plugins {
        id("grpc") {
            artifact = "io.grpc:protoc-gen-grpc-java:$grpcVersion"
        }
    }

    generateProtoTasks {
        all().configureEach {
            plugins {
                id("grpc")
            }
        }
    }
}
```

Ví dụ này thể hiện bốn điểm cần review độc lập: phiên bản plugin protobuf của Gradle, phiên bản `protoc`, phiên bản `protoc-gen-grpc-java` và BOM của thư viện gRPC runtime. Chọn chúng theo ma trận tương thích của dự án. Mã được sinh phải biên dịch được với phiên bản `protobuf-java` và gRPC runtime tương ứng; không giả định rằng mọi phiên bản mới nhất đều tương thích với nhau.

Trong `settings.gradle.kts`, giới hạn nơi Gradle tìm plugin. Ví dụ, chỉ khai báo Gradle Plugin Portal hoặc mirror nội bộ đã được phê duyệt trong `pluginManagement.repositories`. Cấu hình repository dependency trong `dependencyResolutionManagement.repositories` riêng và cân nhắc `RepositoriesMode.FAIL_ON_PROJECT_REPOS` để module con không tự ý thêm nguồn tải.

### 3.2. Xem cây dependency và plugin classpath

Chạy các lệnh sau từ thư mục chứa Gradle Wrapper:

```bash
# Xem dependency runtime đã resolve.
./gradlew dependencies --configuration runtimeClasspath

# Tìm lý do một phiên bản cụ thể được chọn.
./gradlew dependencyInsight \
  --dependency grpc-netty-shaded \
  --configuration runtimeClasspath

# Xem dependency khai báo qua buildscript classpath.
./gradlew buildEnvironment

# Xem log resolve plugin và chạy codegen.
./gradlew --info generateProto
```

`dependencies` và `dependencyInsight` giúp phát hiện phiên bản bắc cầu hoặc xung đột trong cấu hình ứng dụng. `buildEnvironment` tập trung vào buildscript classpath; với plugin được khai báo qua `plugins {}`, hãy kiểm tra thêm phần `pluginManagement`, phiên bản trong build file và log resolve plugin. Không kết luận rằng plugin classpath sạch chỉ từ báo cáo `runtimeClasspath`.

### 3.3. Bật dependency locking và verification

Có thể bật locking cho các configuration được resolve trong build:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Sau đó chạy build với `--write-locks` và commit lockfile được tạo. Khi cần cập nhật, review diff lockfile cùng với thay đổi build file; không tự động chấp nhận mọi phiên bản mới.

Gradle hỗ trợ tạo metadata checksum để xác minh artifact. Khởi tạo metadata trong một lần resolve có kiểm soát:

```bash
./gradlew --write-verification-metadata sha256 clean generateProto test
```

Review `gradle/verification-metadata.xml`, xác nhận nguồn và checksum của từng artifact, rồi commit file này. Trong CI, yêu cầu xác minh nghiêm ngặt:

```bash
./gradlew --dependency-verification=strict clean generateProto test
```

Nếu verification thất bại, hãy xác minh artifact và nguồn phân phối trước khi cập nhật checksum. Không xử lý bằng cách xóa metadata hoặc tắt chế độ strict để bỏ qua lỗi. Cũng cần khóa và xác minh Gradle Wrapper distribution bằng `distributionSha256Sum` trong `gradle/wrapper/gradle-wrapper.properties`; việc xác minh dependency không thay thế kiểm tra bản phân phối Gradle.

## 4. Kiểm tra với Maven

Với Maven, đặt phiên bản thư viện runtime trong `dependencyManagement` và import BOM gRPC. Khai báo phiên bản plugin trong `pluginManagement` hoặc trực tiếp tại plugin được sử dụng. Ví dụ cấu hình codegen sau dùng các property để phiên bản được review tại một nơi:

```xml
<properties>
    <grpc.version>approved-grpc-version</grpc.version>
    <protobuf.version>approved-protobuf-version</protobuf.version>
    <protobuf.maven.plugin.version>approved-plugin-version</protobuf.maven.plugin.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.grpc</groupId>
            <artifactId>grpc-bom</artifactId>
            <version>${grpc.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<build>
    <plugins>
        <plugin>
            <groupId>org.xolstice.maven.plugins</groupId>
            <artifactId>protobuf-maven-plugin</artifactId>
            <version>${protobuf.maven.plugin.version}</version>
            <configuration>
                <protocArtifact>com.google.protobuf:protoc:${protobuf.version}:exe:${os.detected.classifier}</protocArtifact>
                <pluginId>grpc-java</pluginId>
                <pluginArtifact>io.grpc:protoc-gen-grpc-java:${grpc.version}:exe:${os.detected.classifier}</pluginArtifact>
            </configuration>
            <executions>
                <execution>
                    <goals>
                        <goal>compile</goal>
                        <goal>compile-custom</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

`os.detected.classifier` thường được cung cấp bởi `os-maven-plugin`. Nếu dự án dùng extension này, cũng phải khóa phiên bản của extension. Artifact `protoc` và `protoc-gen-grpc-java` là executable theo nền tảng; kiểm tra classifier được resolve trên runner CI và không để build âm thầm tải binary khác với binary đã duyệt.

Các lệnh hữu ích:

```bash
# Cây dependency ứng dụng, gồm cả dependency bắc cầu.
mvn dependency:tree -Dverbose

# POM hiệu lực sau khi kế thừa parent và profile.
mvn help:effective-pom

# Resolve dependency của Maven build plugin.
mvn dependency:resolve-plugins

# Chạy sinh mã, compile và test từ trạng thái sạch.
mvn clean generate-sources test
```

`dependency:tree` chủ yếu phản ánh dependency của project; dùng `dependency:resolve-plugins` để kiểm tra dependency của plugin. `help:effective-pom` giúp phát hiện plugin version đến từ parent POM hoặc profile. Có thể cấu hình Maven Enforcer để bắt buộc khai báo plugin version, kiểm tra dependency convergence và ngăn dependency snapshot trong build phát hành. Với Maven Wrapper, khóa checksum bản phân phối trong `.mvn/wrapper/maven-wrapper.properties` bằng `distributionSha256Sum` nếu phiên bản Wrapper của dự án hỗ trợ thuộc tính này.

Repository Maven nên đi qua mirror được quản lý trong `settings.xml`. Có thể đặt checksum policy là `fail` cho repository để Maven từ chối artifact không có checksum hợp lệ do repository cung cấp. Đây là một lớp kiểm tra; với artifact quan trọng, vẫn cần xác minh checksum/chữ ký theo quy trình nội bộ và giữ bằng chứng nguồn gốc.

## 5. Quét lỗ hổng và kiểm tra mã được sinh

### 5.1. Quét cả dependency lúc build

Sử dụng công cụ SCA được tổ chức chấp thuận để quét dependency trực tiếp và bắc cầu, ví dụ OWASP Dependency-Check hoặc công cụ tương đương trong CI. Kết quả cần bao gồm các thư viện runtime, plugin build và công cụ codegen trong phạm vi mà scanner hỗ trợ. Một báo cáo quét dependency ứng dụng không mặc nhiên bao gồm toàn bộ plugin classpath hoặc binary được tải để chạy codegen; đối chiếu báo cáo với danh sách plugin và tool đã resolve.

Với mỗi cảnh báo CVE, xác minh tọa độ artifact, phiên bản bị ảnh hưởng, phiên bản đã sửa, mức độ khai thác và việc thành phần có thực sự nằm trong build đang phát hành hay không. Ưu tiên nâng cấp lên bản đã vá. Nếu phải suppress false positive, ghi lý do, người chịu trách nhiệm, phạm vi artifact và ngày hết hạn; không dùng suppression chung cho cả nhóm dependency.

Tạo SBOM cho build hoặc release nếu quy trình dự án yêu cầu. SBOM cần thể hiện các thành phần thực sự được đóng gói và, khi công cụ hỗ trợ, các công cụ build quan trọng. Giữ lại báo cáo SCA, SBOM, lockfile và verification metadata làm bằng chứng cho lần build.

### 5.2. Xác minh đầu ra codegen

Sau khi nâng cấp `protoc`, plugin protobuf hoặc `protoc-gen-grpc-java`:

1. Xem diff của file `.proto` và cấu hình plugin để xác định đầu vào thay đổi.
2. Xóa output cũ rồi sinh lại mã bằng đúng Wrapper và toolchain đã khóa.
3. Kiểm tra mã sinh ra thuộc package và source set mong đợi; không chỉnh tay file sinh tự động.
4. Compile và chạy test để phát hiện khác biệt API giữa generated code và runtime.
5. Nếu repository lưu generated source, review diff và xác nhận diff có thể tái tạo từ schema cùng phiên bản tool. Nếu không lưu, bảo đảm build luôn sinh mã từ schema trong pipeline.

Generated source là đầu ra của compiler và generator, nên việc review diff không thay thế kiểm tra nguồn gốc của hai công cụ đó. Khi build từ pull request không đáng tin cậy, chạy codegen trong runner cách ly, không gắn secret triển khai hoặc quyền truy cập production.

## 6. Quy trình review khi thay đổi dependency hoặc codegen

| Bước | Việc cần làm | Bằng chứng cần giữ |
|---|---|---|
| 1. Xác định thay đổi | Ghi rõ lý do nâng cấp, artifact, phiên bản cũ/mới và repository nguồn | Diff build file, parent POM hoặc version catalog |
| 2. Kiểm tra resolve | Xem cây dependency runtime, plugin dependency và codegen artifact | Output `dependencies`, `dependencyInsight` hoặc `dependency:resolve-plugins` |
| 3. Kiểm tra tương thích | Đối chiếu Spring Boot, Spring gRPC, gRPC runtime, protobuf runtime, compiler và generator | Ma trận tương thích hoặc ghi chú nâng cấp đã được duyệt |
| 4. Kiểm tra an toàn | Xác minh checksum/chữ ký, quét CVE và xem thay đổi license nếu quy trình yêu cầu | Verification metadata, báo cáo SCA và kết quả review nguồn tải |
| 5. Kiểm tra đầu ra | Sinh lại mã, compile và chạy test từ trạng thái sạch | Log CI, kết quả test và diff generated source nếu có |
| 6. Khóa kết quả | Cập nhật lockfile và metadata sau khi review thành công | Lockfile, checksum metadata, SBOM và mã commit |

Nếu một plugin mới kéo thêm dependency lạ, dừng việc chấp nhận thay đổi cho đến khi xác định được dependency đó đến từ plugin nào, được tải từ repository nào và có cần thiết cho build hay không. Dùng `dependencyInsight` với dependency ứng dụng hoặc `dependency:resolve-plugins` với Maven plugin để truy ngược nguồn; đối chiếu với diff lockfile và log resolve. Nếu không xác minh được nguồn hoặc tính toàn vẹn, không đưa artifact đó vào pipeline phát hành.

## 7. Checklist trước khi đưa build vào CI

- [ ] Tất cả plugin Gradle/Maven đều có phiên bản cố định và nguồn phân phối được duyệt.
- [ ] `protoc` và `protoc-gen-grpc-java` được khóa phiên bản, đúng classifier và tương thích với runtime.
- [ ] Spring gRPC starter, Spring Boot và thư viện gRPC dùng bộ phiên bản tương thích; BOM được áp dụng đúng phạm vi.
- [ ] Đã xem dependency bắc cầu và dependency của plugin build, không chỉ `runtimeClasspath` hoặc `dependency:tree` của ứng dụng.
- [ ] Lockfile và checksum/verification metadata đã được review, commit và xác minh trong CI.
- [ ] Wrapper Gradle/Maven được khóa phiên bản và checksum phân phối.
- [ ] Kết quả quét lỗ hổng đã được xử lý; suppression có lý do và thời hạn.
- [ ] Build sạch sinh mã, compile và test thành công trên runner được hỗ trợ.
- [ ] Job build chạy với quyền tối thiểu và không đưa secret production vào bước thực thi plugin/codegen từ mã chưa tin cậy.

## Tài liệu tham khảo

- [Gradle — Dependency verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Gradle — Dependency locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle — Plugin management](https://docs.gradle.org/current/userguide/plugins_intermediate.html)
- [Maven — Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/)
- [Maven — Enforcer Plugin](https://maven.apache.org/enforcer/maven-enforcer-plugin/)
- [Protocol Buffers — Java generated code](https://protobuf.dev/reference/java/java-generated/)
- [gRPC — Java generated code](https://grpc.io/docs/languages/java/generated-code/)
- [OWASP Dependency-Check](https://owasp.org/www-project-dependency-check/)
