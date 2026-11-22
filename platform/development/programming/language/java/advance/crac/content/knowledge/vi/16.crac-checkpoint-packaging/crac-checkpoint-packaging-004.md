# Gắn phiên bản, mã nguồn và thông tin môi trường vào bản phát hành ảnh

Checkpoint của CRaC lưu trạng thái một tiến trình Java tại một thời điểm. Khi đóng gói checkpoint để triển khai, đội vận hành cần biết ảnh đó được tạo từ phiên bản ứng dụng nào, mã nguồn ở commit nào, dùng dependency và JDK nào, được tạo trên môi trường nào và cần runtime nào để restore. Nếu thiếu thông tin này, một file checkpoint có thể tồn tại nhưng rất khó xác định nguồn gốc, đánh giá khả năng tương thích hoặc truy vết lỗi khi triển khai.

Một bản phát hành checkpoint nên đi kèm thông tin provenance (nguồn gốc bản dựng), danh sách thành phần phần mềm, checksum và chữ ký. Có thể nhúng thông tin build ổn định vào ứng dụng, đồng thời đóng gói một manifest bên ngoài để mô tả checkpoint cụ thể và môi trường tạo ảnh. Hai phần này bổ sung cho nhau: build info nhận diện ứng dụng; release manifest nhận diện artifact checkpoint và điều kiện triển khai của nó.

## 1. Phân biệt ứng dụng, container image và checkpoint image

Trong quy trình CRaC, từ image có thể chỉ nhiều loại artifact khác nhau:

- **Application artifact:** JAR, WAR hoặc bộ file ứng dụng được biên dịch và đóng gói.
- **Container image:** filesystem và cấu hình được đóng gói theo định dạng OCI để tạo container.
- **Checkpoint image:** ảnh trạng thái tiến trình được CRaC runtime tạo ra, thường gồm dữ liệu bộ nhớ và các thành phần cần thiết để restore tiến trình.
- **Release bundle:** gói phát hành kết hợp checkpoint artifact với manifest, checksum, chữ ký, SBOM và tài liệu liên quan.

Các artifact này không thay thế nhau. Container image nhận diện môi trường filesystem và ứng dụng; checkpoint image nhận diện trạng thái tiến trình đã chạy. Một checkpoint có thể phụ thuộc chặt vào runtime, hệ điều hành, kiến trúc CPU và cách các tài nguyên được xử lý tại thời điểm checkpoint. Vì vậy, chỉ gắn tag cho container image là chưa đủ để quản lý phiên bản checkpoint.

Một gói phát hành có thể có cấu trúc:

~~~text
release/
  application.jar
  checkpoint/
    checkpoint-data
    checkpoint-metadata
  checkpoint-manifest.json
  checkpoint-manifest.sig
  sbom.cdx.json
  checksums.txt
~~~

Tên file checkpoint thực tế và cấu trúc thư mục phụ thuộc CRaC implementation hoặc công cụ checkpoint đang dùng. Không nên giả định mọi runtime đều tạo cùng một tên file hoặc cùng định dạng.

## 2. Ba nhóm thông tin cần gắn với bản phát hành

Thông tin phát hành nên được chia thành ba nhóm để dễ truy xuất.

### Danh tính phiên bản và mã nguồn

Nhóm này trả lời câu hỏi: checkpoint chứa ứng dụng nào và được build từ source nào?

- Tên ứng dụng và module.
- Phiên bản phát hành, ví dụ 2.4.1.
- Build number hoặc CI run ID.
- Git commit SHA đầy đủ.
- Git tag hoặc release branch.
- Trạng thái working tree khi build: clean hay dirty.
- Hash của source archive hoặc patch nếu bản build không xuất phát từ commit sạch.
- Phiên bản Gradle/Maven và build plugin quan trọng.
- Hash của dependency lockfile.
- SBOM mô tả dependency và phiên bản thư viện.

Git commit SHA là định danh quan trọng, nhưng chỉ đáng tin khi bản dựng thực sự được tạo từ nội dung commit đó. Nếu working tree có thay đổi chưa commit, cần ghi nhận dirty state và lưu patch/source snapshot tương ứng hoặc từ chối phát hành theo chính sách CI.

### Thông tin runtime và môi trường tạo checkpoint

Nhóm này trả lời câu hỏi: tiến trình được tạo và checkpoint trên nền tảng nào?

- JDK vendor, phiên bản đầy đủ, build number và runtime version.
- CRaC API/runtime hoặc checkpoint implementation cùng phiên bản.
- JVM flags có ảnh hưởng tới runtime, class loading, JIT hoặc checkpoint.
- Hệ điều hành, phiên bản distribution và kernel.
- Kiến trúc CPU, ví dụ x86_64 hoặc aarch64.
- libc và các thư viện native quan trọng nếu môi trường phụ thuộc chúng.
- Container base image và digest bất biến.
- Các đặc điểm CPU hoặc nền tảng mà runtime yêu cầu để restore.
- Thông tin công cụ tạo checkpoint và cách gọi checkpoint.

Không nên chỉ ghi Java 21 hoặc Linux. Hai bản JDK cùng feature release có thể khác vendor, build, CRaC patch hoặc native library. Hãy ghi phiên bản đầy đủ và runtime thực sự đã chạy ứng dụng.

### Thông tin checkpoint và đóng gói

Nhóm này trả lời câu hỏi: artifact nào được tạo, khi nào và được kiểm chứng ra sao?

- ID duy nhất của checkpoint/release.
- Thời điểm checkpoint được tạo theo UTC.
- Phiên bản ứng dụng được checkpoint.
- Đường dẫn tương đối, kích thước và SHA-256 của từng file checkpoint.
- SHA-256 của archive hoặc release bundle sau khi đóng gói.
- Trạng thái bước chuẩn bị checkpoint và phiên bản quy trình warmup.
- Phiên bản manifest schema.
- Thời điểm và danh tính pipeline phát hành.
- Chữ ký manifest hoặc chữ ký artifact.

Thời điểm build và thời điểm checkpoint là hai mốc khác nhau. Có thể build JAR trước, chạy ứng dụng và warmup, rồi mới tạo checkpoint. Cần ghi riêng các timestamp này để truy vết chính xác.

## 3. Vì sao phải ghi nhận cả mã nguồn và môi trường?

Khi một checkpoint restore thất bại, chỉ biết phiên bản ứng dụng thường chưa đủ để tìm nguyên nhân. Ví dụ:

- Một dependency native được cập nhật dù source Java không đổi.
- CI dùng JDK vendor/build khác với môi trường đã tạo checkpoint.
- Container base image được thay đổi nhưng tag vẫn giữ nguyên.
- Kernel hoặc kiến trúc CPU của host restore khác môi trường đã checkpoint.
- Một patch chưa commit đã được đưa vào JAR.
- Secret hoặc cấu hình động thay đổi giữa lúc tạo checkpoint và lúc restore.

Commit SHA giúp truy ra source. Dependency lock và SBOM giúp xác định thư viện. JDK/CRaC runtime cùng OS/kernel giúp đối chiếu khả năng tương thích. Digest xác nhận chính xác file checkpoint nào được triển khai.

Thông tin môi trường là bằng chứng để so sánh, không phải một lời khẳng định rằng mọi host có cùng tên OS hoặc cùng major JDK chắc chắn tương thích. Các điều kiện tương thích cụ thể phụ thuộc CRaC runtime, checkpoint tool, vendor và nền tảng triển khai. Phải kiểm thử restore trên môi trường mục tiêu.

## 4. Nhúng build identity vào application artifact

Ứng dụng nên mang theo một định danh build bất biến để có thể tự báo phiên bản đang chạy. Có thể tạo resource như build-info.properties trong JAR.

Ví dụ nội dung:

~~~properties
app.name=order-service
app.version=2.4.1
build.id=ci-18427
git.commit=8f6a9f4b3c2d1e0a...
git.dirty=false
build.jdk=21.0.x+build
build.gradle=8.x
dependency.lock.sha256=...
~~~

Các giá trị trên chỉ minh họa định dạng. Pipeline cần điền giá trị thật từ source control và môi trường build. Nếu một giá trị không có, ghi rõ unknown hoặc không đưa field đó vào; không tự đoán.

### Tạo build-info.properties bằng Gradle

Một cách là truyền metadata từ CI qua environment variable rồi tạo resource trong quá trình build. Ví dụ dưới đây dùng Gradle Groovy DSL:

~~~groovy
def buildInfoDir = layout.buildDirectory.dir("generated/build-info")
def gitCommit = providers.environmentVariable("GIT_COMMIT")
        .orElse("unknown")
def buildId = providers.environmentVariable("BUILD_ID")
        .orElse("local")
def gitDirty = providers.environmentVariable("GIT_DIRTY")
        .orElse("unknown")
def appVersion = project.version.toString()

tasks.register("generateBuildInfo") {
    inputs.property("gitCommit", gitCommit)
    inputs.property("buildId", buildId)
    inputs.property("gitDirty", gitDirty)
    inputs.property("appVersion", appVersion)

    outputs.file(buildInfoDir.map {
        it.file("build-info.properties")
    })

    doLast {
        def output = buildInfoDir.get()
                .file("build-info.properties").asFile
        output.parentFile.mkdirs()
        output.text = [
                "app.name=" + project.name,
                "app.version=" + appVersion,
                "build.id=" + buildId.get(),
                "git.commit=" + gitCommit.get(),
                "git.dirty=" + gitDirty.get()
        ].join(System.lineSeparator()) + System.lineSeparator()
    }
}

sourceSets.main.resources.srcDir(buildInfoDir)
tasks.named("processResources") {
    dependsOn("generateBuildInfo")
}
~~~

Pipeline phải thiết lập GIT_COMMIT, BUILD_ID và GIT_DIRTY từ chính checkout đang được build. Không nên lấy commit SHA từ một biến CI không được ràng buộc với workspace thực tế. Nếu dự án dùng Kotlin DSL hoặc build convention plugin, chuyển cách tạo resource sang cấu hình tương ứng.

Với build có yêu cầu reproducible, không nên nhúng timestamp hiện tại vào resource theo cách làm thay đổi JAR ở mỗi lần build cùng source. Thời điểm build có thể được lưu trong release manifest hoặc lấy từ SOURCE_DATE_EPOCH theo quy ước của pipeline. Build ID và commit SHA vẫn cần đủ để phân biệt các lần phát hành.

### Đọc build info khi ứng dụng chạy

Ứng dụng có thể đọc resource để log hoặc hiển thị trong endpoint chẩn đoán:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class BuildInfo {
    private static final Properties VALUES = load();

    private BuildInfo() {}

    private static Properties load() {
        Properties properties = new Properties();
        try (InputStream input =
                     BuildInfo.class.getResourceAsStream(
                             "/build-info.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "build-info.properties is missing");
            }
            properties.load(input);
            return properties;
        } catch (IOException error) {
            throw new IllegalStateException(
                    "Cannot read build information", error);
        }
    }

    public static String version() {
        return VALUES.getProperty("app.version", "unknown");
    }

    public static String commit() {
        return VALUES.getProperty("git.commit", "unknown");
    }

    public static String buildId() {
        return VALUES.getProperty("build.id", "unknown");
    }
}
~~~

Có thể log version, commit và build ID lúc startup hoặc expose qua một endpoint nội bộ có kiểm soát. Không đưa secret, environment đầy đủ, token hoặc connection string vào build info.

Build info trong JAR nhận diện ứng dụng đã được build. Nó không thể tự nhận diện digest của checkpoint cuối cùng vì checkpoint chỉ được tạo sau khi ứng dụng đã chạy.

## 5. Tạo release manifest cho checkpoint

Sau khi tạo checkpoint, pipeline tạo manifest bên ngoài mô tả chính artifact checkpoint. Manifest có thể là JSON, YAML hoặc định dạng metadata đã được tổ chức quy định. JSON thuận tiện cho CI, công cụ kiểm tra và hệ thống lưu artifact.

Ví dụ:

~~~json
{
  "schemaVersion": "1",
  "release": {
    "name": "order-service",
    "version": "2.4.1",
    "buildId": "ci-18427",
    "createdAt": "2026-11-13T07:00:00Z"
  },
  "source": {
    "repository": "https://example.invalid/platform/order-service",
    "commit": "8f6a9f4b3c2d1e0a...",
    "tag": "v2.4.1",
    "workingTreeClean": true,
    "dependencyLockSha256": "..."
  },
  "application": {
    "artifact": "application.jar",
    "sha256": "..."
  },
  "checkpoint": {
    "id": "order-service-2.4.1-20261113T070000Z",
    "createdAt": "2026-11-13T07:00:00Z",
    "implementation": "vendor-crac-runtime",
    "runtimeVersion": "recorded-full-version",
    "files": [
      {
        "path": "checkpoint/checkpoint-data",
        "sizeBytes": 123456789,
        "sha256": "..."
      }
    ]
  },
  "environment": {
    "jdkVendor": "recorded-vendor",
    "javaRuntimeVersion": "recorded-full-version",
    "cracRuntimeVersion": "recorded-version",
    "os": "recorded-distribution-and-version",
    "kernel": "recorded-kernel-version",
    "architecture": "x86_64",
    "libc": "recorded-libc-version",
    "containerBaseImage": "registry.example/app-base@sha256:..."
  },
  "provenance": {
    "pipeline": "release-pipeline",
    "runId": "18427",
    "sbom": "sbom.cdx.json",
    "signature": "checkpoint-manifest.sig"
  }
}
~~~

Đây là schema minh họa, không phải định dạng manifest bắt buộc của CRaC. Tên implementation, runtime version, OS, kernel và các giá trị digest phải lấy từ môi trường thực tế. Nếu checkpoint gồm nhiều file, liệt kê tất cả file cần thiết hoặc tạo một archive bất biến rồi ghi digest của archive.

Không nên đặt một giá trị giả như latest vào manifest. Dùng version cụ thể, commit SHA đầy đủ và digest bất biến. Nếu trường nào không áp dụng, có thể bỏ hoặc ghi unknown theo schema đã thống nhất.

## 6. Gắn manifest với đúng checkpoint artifact

Manifest chỉ hữu ích nếu có thể chứng minh nó mô tả đúng artifact đang triển khai. Hãy tính SHA-256 cho checkpoint files hoặc archive sau khi checkpoint và đóng gói hoàn tất.

Ví dụ trên Linux:

~~~shell
sha256sum application.jar
sha256sum checkpoint/*
sha256sum release.tar
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\application.jar
Get-FileHash -Algorithm SHA256 -LiteralPath .\release.zip
~~~

Nếu checkpoint là một thư mục có nhiều file, pipeline cần tạo danh sách đường dẫn tương đối, kích thước và hash cho từng file. Không chỉ hash tên thư mục; thư mục không phải một byte stream bất biến. Một lựa chọn khác là đóng gói checkpoint vào archive, tính hash archive và bảo đảm archive được tạo xong trước khi ký manifest.

Không nhúng digest của checkpoint vào chính file checkpoint theo cách tạo vòng phụ thuộc. Cũng không chỉnh sửa nội dung checkpoint sau khi đã tính hash. Thay vào đó:

1. Tạo checkpoint.
2. Đóng gói các file checkpoint.
3. Tính hash của từng file hoặc archive.
4. Tạo manifest tham chiếu đến các hash đó.
5. Ký manifest.
6. Phát hành bundle bất biến.

Build info được nhúng trong JAR có thể chứa commit và version. Release manifest bên ngoài liên kết JAR đó với checkpoint cụ thể bằng digest và thông tin môi trường.

## 7. Ghi nhận thông tin môi trường tại đúng thời điểm

Thông tin cần thu thập tại thời điểm build có thể khác thông tin cần thu thập khi chạy ứng dụng và khi tạo checkpoint.

| Thời điểm | Thông tin nên ghi |
|---|---|
| Source checkout | Commit SHA, tag, trạng thái dirty, submodule revision, source archive hash |
| Build | JDK compiler/vendor/version, Gradle/Maven version, build ID, dependency lock hash, SBOM |
| Runtime startup | Java runtime version, JVM flags, classpath/module path, CRaC runtime identity |
| Checkpoint | Timestamp UTC, checkpoint tool/implementation, runtime build, OS/kernel, architecture, container digest, checkpoint file inventory |
| Restore target | Runtime và host thực tế, container digest, kết quả xác minh tương thích, thời gian restore và readiness |

Một số thông tin có thể lấy bằng lệnh hoặc API hệ thống. Ví dụ:

~~~shell
java -version
java -XshowSettings:properties -version
uname -a
uname -m
~~~

Các lệnh uname phù hợp với Linux/Unix. Trên Windows, dùng công cụ hệ thống tương ứng để ghi phiên bản OS và kiến trúc. Với container, ghi cả digest của image đã pull, không chỉ tag có thể bị thay đổi.

JVM có thể in một phần system properties, nhưng không phải mọi thông tin môi trường đều có thể lấy chính xác từ Java API. CI hoặc checkpoint launcher thường là nơi phù hợp để thu thập kernel, container digest, CPU architecture và phiên bản công cụ checkpoint.

Không cần thu thập toàn bộ environment variables. Chỉ ghi các tên biến không nhạy cảm cần cho khả năng tái lập. Với secret, chỉ ghi định danh phiên bản hoặc revision nếu chính sách cho phép; không ghi giá trị secret, password, token hoặc private key.

## 8. OCI labels và liên kết với container image

Nếu checkpoint được tạo bên trong container, container image cũng nên có metadata nhận diện source và release. OCI image annotations/labels phổ biến gồm:

- org.opencontainers.image.title
- org.opencontainers.image.description
- org.opencontainers.image.version
- org.opencontainers.image.revision
- org.opencontainers.image.source
- org.opencontainers.image.created
- org.opencontainers.image.licenses

Ví dụ Dockerfile:

~~~dockerfile
ARG APP_VERSION
ARG GIT_COMMIT
ARG BUILD_CREATED

LABEL org.opencontainers.image.title="order-service" \
      org.opencontainers.image.version="$APP_VERSION" \
      org.opencontainers.image.revision="$GIT_COMMIT" \
      org.opencontainers.image.created="$BUILD_CREATED"
~~~

Giá trị ARG phải được truyền từ pipeline đã xác minh source checkout. Khi phát hành, lưu digest OCI image thực tế. Tag như order-service:2.4.1 thuận tiện cho con người nhưng có thể được gán lại; digest sha256 là định danh bất biến của nội dung image.

Checkpoint manifest cần tham chiếu container image digest đã dùng để tạo checkpoint. Khi restore, so sánh digest và các thông tin runtime theo compatibility policy. OCI labels chỉ là metadata; chúng không tự bảo đảm checkpoint có thể restore trên container đó.

## 9. SBOM và provenance của dependency

SBOM (Software Bill of Materials) mô tả các thành phần phần mềm có trong artifact, ví dụ thư viện Java, native library và phiên bản dependency. Có thể dùng định dạng SPDX hoặc CycloneDX theo chính sách tổ chức.

Đối với ứng dụng Java, nên ghi:

- Dependency trực tiếp và dependency bắc cầu.
- Phiên bản thực tế đã resolve.
- Hash hoặc revision của dependency lockfile.
- Plugin/build tool quan trọng.
- Native library và thành phần runtime có ảnh hưởng tới checkpoint.
- JDK vendor/build và CRaC implementation.

Lockfile giúp tái tạo graph dependency, còn SBOM giúp người vận hành và công cụ bảo mật biết những thành phần nào đã được đóng gói. Hai thứ bổ sung cho nhau.

Provenance mô tả cách artifact được tạo: pipeline nào chạy, source revision nào được checkout, builder identity nào thực hiện build, tham số nào được sử dụng và artifact đầu ra có digest gì. Nếu tổ chức có hệ thống attestation như SLSA provenance hoặc định dạng tương đương, hãy liên kết manifest checkpoint với attestation đó.

## 10. Chữ ký và tính toàn vẹn của release bundle

Checksum giúp phát hiện file bị thay đổi ngoài dự kiến. Chữ ký số giúp xác minh manifest được phát hành bởi pipeline hoặc danh tính được tin cậy.

Quy trình phát hành có thể là:

~~~text
Source commit đã xác định
       |
       v
Build application.jar
       |
       v
Tạo build-info và SBOM
       |
       v
Chạy ứng dụng bằng JDK/CRaC runtime đã chọn
       |
       v
Warmup và chuẩn bị Resource
       |
       v
Tạo checkpoint
       |
       v
Tính SHA-256 cho artifact
       |
       v
Tạo checkpoint-manifest.json
       |
       v
Ký manifest và kiểm tra chữ ký
       |
       v
Phát hành release bundle bất biến
~~~

Khóa ký nên được quản lý trong hệ thống CI hoặc dịch vụ ký tin cậy, không lưu trong source repository hay checkpoint image. Quyền ký phát hành cần giới hạn cho pipeline và danh tính được phê duyệt.

Khi triển khai, xác minh chữ ký manifest, kiểm tra hash artifact, xác nhận commit/version và kiểm tra runtime compatibility trước khi restore. Nếu bất kỳ hash nào không khớp, không sử dụng bundle đó.

## 11. Quy tắc tương thích môi trường restore

Thông tin môi trường giúp xây dựng chính sách tương thích. Không nên chỉ so sánh chuỗi phiên bản rồi kết luận tương thích.

Các chiều cần đánh giá:

| Chiều | Câu hỏi cần xác minh |
|---|---|
| JDK vendor/build | Runtime restore có đúng bản JDK/CRaC build được hỗ trợ không? |
| CRaC implementation | Checkpoint được tạo và restore bằng implementation/phiên bản nào? |
| OS và kernel | Kernel đích có hỗ trợ cơ chế checkpoint/restore và các resource cần thiết không? |
| CPU architecture | Kiến trúc và đặc điểm CPU có tương thích với mã máy/runtime trong checkpoint không? |
| Native libraries | Shared library, libc và ABI cần thiết có sẵn và tương thích không? |
| Container filesystem | Đường dẫn, mount, permission, file và thư viện cần thiết có tồn tại không? |
| Cấu hình và secret | Endpoint, credential, certificate và cấu hình hiện tại có còn hợp lệ không? |
| Tài nguyên bên ngoài | Database, broker, socket, lock và các dependency đã được phục hồi theo chính sách chưa? |

Một số nền tảng có thể cho phép restore trên nhiều host tương tự; nền tảng khác yêu cầu điều kiện chặt hơn. Hãy theo tài liệu của đúng CRaC distribution và checkpoint tool. Ghi nhận môi trường nguồn và môi trường đích để khi có lỗi có thể xác định khác biệt.

Không nên gắn checkpoint vào tag container có thể bị thay thế hoặc để một release tự chọn runtime mới nhất. Hãy pin JDK/container bằng phiên bản và digest đã kiểm chứng. Nâng JDK, kernel hoặc base image cần tạo và kiểm thử checkpoint mới theo quy trình phát hành.

## 12. Không đưa cấu hình nhạy cảm vào manifest

Manifest phục vụ truy vết và triển khai, không phải kho secret. Không đưa các giá trị sau vào manifest, log hoặc tên artifact:

- Password database.
- API key, bearer token hoặc session token.
- Private key, certificate private material.
- Nội dung secret file.
- Connection string có credential.
- Giá trị environment không được phép công khai.

Nếu cần biết secret nào đã được dùng, chỉ ghi secret reference, version ID hoặc revision không nhạy cảm theo chính sách của secret manager. Secret có thể đã được nạp vào heap trước checkpoint, nên checkpoint image cũng phải được bảo vệ và phân quyền như một artifact chứa thông tin xác thực.

Không đưa hostname nội bộ, địa chỉ IP hoặc thông tin topology chi tiết vào manifest công khai nếu không cần thiết. Có thể lưu bản manifest vận hành ở kho nội bộ được kiểm soát quyền truy cập.

## 13. Quy trình đóng gói và kiểm tra trước phát hành

Một pipeline có thể triển khai theo các bước:

1. Checkout source tại commit cụ thể; xác nhận working tree sạch hoặc lưu patch nếu cho phép build dirty.
2. Ghi nhận commit, tag, submodule revision và build ID.
3. Build ứng dụng bằng JDK và build tool đã pin.
4. Tạo build-info.properties trong JAR; sinh SBOM và lưu dependency lock hash.
5. Tạo container image với OCI labels và lưu digest bất biến.
6. Khởi chạy bằng đúng JDK/CRaC runtime; thực hiện warmup và chuẩn bị tài nguyên theo hướng dẫn.
7. Tạo checkpoint trong môi trường được kiểm soát.
8. Thu thập runtime, OS, kernel, CPU architecture và thông tin checkpoint tool tại thời điểm tạo ảnh.
9. Tạo inventory file checkpoint, tính SHA-256 và đóng gói release bundle.
10. Tạo manifest liên kết application digest, container digest, source revision và checkpoint digest.
11. Ký manifest, xác minh chữ ký và lưu bundle cùng SBOM/provenance.
12. Kiểm tra restore bằng đúng runtime và môi trường mục tiêu trước khi quảng bá release.

Mỗi lần checkpoint mới nên có ID duy nhất, ngay cả khi application version không thay đổi. Một ứng dụng có thể tạo nhiều checkpoint từ cùng một JAR nhưng ở những thời điểm hoặc môi trường khác nhau; không nên ghi đè checkpoint cũ dưới cùng một tên artifact.

## 14. Kiểm tra sau khi triển khai và restore

Trước khi restore:

- Xác minh chữ ký manifest.
- Tính lại hash và so sánh với manifest.
- Xác nhận application version, commit SHA và container digest.
- Kiểm tra JDK/CRaC runtime, OS/kernel và kiến trúc theo compatibility policy.
- Xác nhận checkpoint files đầy đủ và quyền truy cập đúng.

Sau restore:

- Log release ID, build ID, commit và checkpoint ID.
- Xác minh các dependency bên ngoài đã kết nối hoặc được làm mới.
- Kiểm tra cấu hình và secret hiện tại.
- Kiểm tra readiness trước khi nhận traffic.
- Ghi nhận restore duration và kết quả phục hồi.
- Liên kết log, metric và trace với release ID/checkpoint ID.

Nếu runtime sau restore không khớp policy, không cố ép restore chỉ vì manifest có cùng application version. Quay về quy trình tạo checkpoint trên môi trường tương thích hoặc khởi chạy ứng dụng theo cold-start path đã được hỗ trợ.

## 15. Những lỗi thường gặp

**Chỉ gắn version vào tên file checkpoint.**

Tên file không chứng minh nguồn gốc. Cần commit SHA, build ID, runtime, môi trường, digest và manifest có thể xác minh.

**Chỉ ghi Java 21.**

Feature release không đủ để nhận diện vendor, build, CRaC patch và runtime thực tế. Ghi phiên bản đầy đủ và implementation.

**Dùng tag container làm định danh duy nhất.**

Tag có thể được gán lại. Lưu OCI digest để nhận diện chính xác container image đã dùng.

**Bỏ qua trạng thái working tree.**

Một commit SHA không mô tả patch chưa commit. Ghi dirty state và source snapshot tương ứng hoặc từ chối phát hành dirty build.

**Đưa checkpoint hash vào chính checkpoint.**

Điều đó tạo vòng phụ thuộc khi tính hash. Lưu hash trong manifest bên ngoài sau khi checkpoint artifact đã hoàn tất.

**Sửa manifest sau khi ký.**

Mọi thay đổi metadata sau khi ký làm chữ ký không còn hợp lệ. Tạo manifest mới, tính lại digest và ký lại theo quy trình.

**Đưa secret vào build info hoặc manifest.**

Artifact có thể được sao chép tới nhiều môi trường. Chỉ ghi secret reference/version nếu được phép, không ghi giá trị.

**Cho rằng cùng OS và JDK major version là đủ tương thích.**

Kernel, vendor build, native library, CPU architecture và CRaC implementation cũng có thể ảnh hưởng. Kiểm thử restore trên đúng môi trường mục tiêu.

**Không kiểm thử restore trước khi phát hành.**

Manifest và checksum không chứng minh checkpoint có thể restore. Cần có bước restore integration test và readiness validation.

## 16. Kết luận

Một bản phát hành checkpoint cần nhận diện được cả source, application build, runtime tạo ảnh, môi trường hệ điều hành và chính checkpoint artifact. Hãy nhúng build identity ổn định vào application artifact, tạo manifest bên ngoài sau khi checkpoint để ghi runtime/environment và hash, đồng thời đính kèm SBOM, provenance và chữ ký.

Manifest cần liên kết commit SHA, build ID, application/container digest và checkpoint digest. Thông tin môi trường giúp đánh giá tương thích, còn checksum và chữ ký giúp xác minh tính toàn vẹn và nguồn phát hành. Không đưa secret vào metadata; bảo vệ checkpoint image và chỉ restore khi artifact đã được xác minh trên runtime/môi trường được hỗ trợ.
