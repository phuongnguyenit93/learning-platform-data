# Định danh sản phẩm bằng nguồn, toolchain, cấu hình build và checksum

Một file native executable hoặc container image chỉ có tên và version chưa đủ để truy vết. Khi phát hiện lỗi production hoặc lỗ hổng trong một dependency, đội vận hành cần trả lời được: binary này được tạo từ commit nào, bằng GraalVM/JDK và compiler nào, dùng dependency và reachability metadata nào, với những build options nào, cho kiến trúc nào, và các byte đang chạy có đúng là artifact đã được kiểm thử hay không.

Với ứng dụng Spring Boot được biên dịch bằng **Spring AOT và GraalVM Native Image**, cần định danh sản phẩm từ bốn nhóm dữ liệu: **source revision**, **toolchain**, **build configuration/dependencies** và **artifact digest**. CI/CD nên ghi nhận các dữ liệu đó trong build manifest, tạo SBOM/provenance attestation, xác minh chữ ký và checksum, rồi phát hành/deploy đúng artifact theo digest.

Bài học thuộc chương **CI/CD** của module **`SPRING_BOOT_NATIVE_IMAGE`**. Module hướng dẫn biên dịch Spring Boot thành GraalVM Native Image để đánh giá startup/memory, thực hành Maven/Gradle, reflection/resource hints, kiểm thử tương thích, đóng gói container và vận hành bản native. Bài này tập trung vào việc gắn danh tính có thể kiểm chứng cho binary và image qua toàn bộ pipeline.

## 1. Định danh artifact, checksum và provenance là ba khái niệm khác nhau

Một quy trình release đáng tin cậy cần phân biệt:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Artifact identity | Chính xác sản phẩm nào đang được nói tới? | `orders-service:1.4.0`, target `linux/amd64` |
| Checksum/digest | Các byte có khớp với fingerprint đã biết không? | SHA-256 của executable hoặc OCI manifest |
| Build provenance | Artifact được tạo từ đâu, bằng gì và theo quy trình nào? | Commit, builder identity, toolchain, dependencies, build parameters |
| Signature/attestation | Ai hoặc nền tảng nào xác nhận metadata gắn với digest này? | Signed in-toto/SLSA provenance |
| SBOM | Những thành phần phần mềm nào có trong artifact hoặc đã tham gia build? | SPDX/CycloneDX dependency inventory |

Checksum giúp phát hiện byte bị thay đổi khi so sánh với một giá trị tin cậy. Nhưng một file `artifact.sha256` được lưu cạnh binary không tự chứng minh ai tạo binary: người thay binary cũng có thể thay file checksum. Provenance ghi lại quan hệ giữa source, builder, inputs và output; chữ ký của một builder đáng tin cậy giúp xác thực attestation đó.

SBOM và provenance cũng không thay thế nhau. SBOM mô tả thành phần phần mềm; provenance mô tả quá trình tạo artifact. Cả hai đều nên gắn với digest của đúng artifact được phát hành.

## 2. Mô hình định danh sản phẩm Native Image

Có thể biểu diễn một build release bằng tuple:

\[
\text{Product Identity} =
(\text{name},\text{version},\text{source},\text{toolchain},
\text{dependencies},\text{configuration},\text{platform},\text{digest})
\]

Với Spring Boot Native Image, mỗi trường có ý nghĩa cụ thể:

| Nhóm | Dữ liệu cần ghi |
|---|---|
| Product | Service name, release version, build ID, artifact type |
| Source | Repository URI, Git commit SHA, tree SHA, tag, trạng thái working tree, submodule revisions |
| Toolchain | Builder image digest, OS baseline, CPU architecture, JDK/GraalVM version, `native-image` version, C/C++ compiler/linker, Maven/Gradle và plugin versions |
| Dependencies | Dependency tree, lockfiles, checksum/signature verification metadata, SBOM |
| Build configuration | Spring profiles dùng khi AOT, Maven/Gradle task/profile, Native Image arguments, build properties, RuntimeHints/reachability metadata |
| Target | `linux/amd64`, `linux/arm64`, libc baseline, dynamic/static linking |
| Output | Native executable SHA-256, container OCI digest, SBOM digest, provenance reference |

Một release cho amd64 và một release cho arm64 là hai binary khác nhau, có digest khác nhau, dù chúng dùng cùng source commit và version. Nếu phát hành multi-architecture image, OCI manifest list có digest riêng trỏ tới các platform manifests.

Không dùng tag như `latest` hoặc version string làm danh tính duy nhất. Tag có thể được di chuyển sang image khác; digest xác định nội dung manifest cụ thể.

## 3. Ghi nhận source revision

Build release nên bắt đầu từ một commit bất biến. CI cần ghi nhận:

- Repository URI.
- Commit SHA đầy đủ, không chỉ short SHA.
- Git tree SHA hoặc source archive checksum.
- Release tag và version.
- Trạng thái working tree có sạch hay không.
- Commit SHA của submodules và revision của Git LFS objects nếu dự án dùng chúng.

Ví dụ kiểm tra source trong Linux CI:

~~~bash
git rev-parse HEAD
git rev-parse HEAD^{tree}
git status --porcelain
git submodule status --recursive
~~~

Pipeline release nên fail nếu `git status --porcelain` trả về thay đổi không được ghi nhận. Một build từ working tree có file sửa cục bộ hoặc generated file không được commit sẽ khó tái tạo từ commit SHA.

Nếu cần source archive checksum:

~~~bash
git archive --format=tar HEAD | sha256sum
~~~

Lưu ý `git archive` không tự đóng gói nội dung submodule như file thường; phải ghi nhận submodule revision riêng hoặc tạo source bundle theo quy trình đã định. Với Git LFS, ghi lại object IDs và bảo đảm CI đã checkout đúng object bytes.

### Build ID

Build ID nên phân biệt từng lần thực thi pipeline, kể cả khi cùng commit được build lại. Ví dụ:

~~~text
orders-service-1.4.0+git.7f2a9c1-build.1842
~~~

Build ID dùng để truy vấn log CI, không thay cho commit SHA hoặc artifact digest. Hai lần build từ cùng commit có thể tạo ra hai output khác nhau nếu toolchain, dependency, environment hoặc build parameters khác nhau.

## 4. Định danh toolchain và builder image

Native Image phụ thuộc nhiều hơn JDK version. Kết quả có thể thay đổi khi nâng GraalVM, Native Build Tools, Spring Boot plugin, compiler, linker, hệ điều hành hoặc kiến trúc CPU.

CI nên lưu ít nhất:

~~~bash
java -version
native-image --version
mvn -version
cc --version
ld --version
uname -a
~~~

Nếu dùng Gradle, lưu `./gradlew --version` và version của plugin Native Build Tools. Với Maven, lưu Maven Wrapper version, Spring Boot Maven plugin và `native-maven-plugin` version.

### Pin builder image bằng digest

Tag như `ghcr.io/graalvm/native-image-community:21-ol9` thuận tiện để đọc nhưng có thể được cập nhật. Với release pipeline, pin image digest:

~~~dockerfile
FROM ghcr.io/graalvm/native-image-community:21-ol9@sha256:<BUILDER_IMAGE_DIGEST> AS builder
~~~

Thay `<BUILDER_IMAGE_DIGEST>` bằng digest đã được CI/registry xác minh. Ghi lại cả image reference và digest trong build manifest. Runtime base image cũng cần được pin và ghi nhận.

Đối với native compiler, ghi rõ:

- GraalVM distribution và version.
- `native-image --version`.
- JDK feature version.
- Compiler/linker version.
- Builder OS, glibc/musl baseline và architecture.
- Native Build Tools plugin version.

Hai build cùng source nhưng dùng toolchain khác nhau không nên được coi là cùng một build recipe.

## 5. Định danh dependencies và xác minh tính toàn vẹn

Version string cho biết dependency được yêu cầu, nhưng chưa đủ để xác minh bytes tải về. CI cần cố định dependency graph và kiểm tra artifact đầu vào.

### 5.1. Maven

Với Maven:

- Pin version cho dependency, Maven plugin và build extension.
- Tránh version range và `SNAPSHOT` trong release build.
- Dùng Maven Wrapper và cố định Maven distribution.
- Dùng repository manager nội bộ hoặc repository đã được kiểm soát.
- Cấu hình checksum policy là `fail` cho repository khi chính sách yêu cầu.
- Lưu dependency tree/effective POM làm bằng chứng của dependency graph.

Ví dụ cấu hình checksum policy cho repository:

~~~xml
<repositories>
    <repository>
        <id>central</id>
        <url>https://repo.maven.apache.org/maven2</url>
        <releases>
            <enabled>true</enabled>
            <checksumPolicy>fail</checksumPolicy>
        </releases>
        <snapshots>
            <enabled>false</enabled>
        </snapshots>
    </repository>
</repositories>
~~~

`checksumPolicy=fail` khiến Maven dừng khi checksum repository cung cấp bị thiếu hoặc không khớp theo chính sách đó. Nó không thay thế xác minh chữ ký của publisher hay kiểm tra nguồn repository; checksum lấy từ cùng repository vẫn cần được đánh giá trong trust model của tổ chức.

Ghi dependency graph:

~~~bash
./mvnw -B -ntp dependency:tree \
  -DoutputFile=target/dependency-tree.txt
~~~

Pin Maven Wrapper distribution bằng checksum trong `.mvn/wrapper/maven-wrapper.properties` nếu quy trình wrapper của dự án hỗ trợ property `distributionSha256Sum`. Kiểm tra plugin version và cấu hình build cùng source; không chỉ pin dependency ứng dụng mà bỏ quên plugin tạo ra native binary.

### 5.2. Gradle dependency locking và verification

Gradle có hai cơ chế bổ sung:

- **Dependency locking:** cố định phiên bản dependency đã resolve.
- **Dependency verification:** kiểm tra checksum và/hoặc chữ ký của artifact tải về.

Bật dependency locking:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Tạo hoặc cập nhật lock state sau khi đã review dependency:

~~~bash
./gradlew dependencies --write-locks
~~~

Tạo verification metadata SHA-256:

~~~bash
./gradlew --write-verification-metadata sha256 build
~~~

Gradle ghi metadata tại:

~~~text
gradle/verification-metadata.xml
~~~

Commit lockfiles và verification metadata vào source control. Khi dependency hoặc plugin thay đổi, review checksum mới trước khi chấp nhận. Bootstrap verification metadata từ repository hiện tại không tự chứng minh repository đó đáng tin cậy; cần xác minh nguồn artifact, đặc biệt với dependency quan trọng.

Nếu publisher cung cấp chữ ký và tổ chức có trusted keys, bật signature verification cùng checksum verification. Checksum xác nhận nội dung; chữ ký giúp xác minh publisher theo trust store đã cấu hình.

## 6. Định danh cấu hình build

Một source commit có thể tạo ra nhiều native executable khác nhau nếu build properties khác nhau. Hãy ghi nhận:

- Maven profile hoặc Gradle task được gọi.
- Spring profiles và properties được dùng khi chạy Spring AOT processing.
- Native Image arguments, GC, optimization level, PGO profile và target architecture.
- Runtime hints, reachability metadata và resource configuration.
- Environment variables ảnh hưởng build.
- Build scripts, wrapper configuration và plugin versions.
- Dockerfile, `.dockerignore`, builder/runtime image references.

Ví dụ một build configuration cho production:

~~~text
Build command: ./mvnw -Pnative -DskipTests native:compile
Spring AOT profile: production
Target: linux/amd64
GraalVM: Java 21, GraalVM release đã pin
Native Image flags: --gc=<approved-gc>, <approved-options>
Builder image: ghcr.io/graalvm/native-image-community@sha256:...
~~~

Đây là ví dụ mô tả; command và profile phải phản ánh chính xác dự án. Nếu build AOT với profile `production` nhưng runtime lại cần bean set của profile `staging`, phải tạo build variant riêng hoặc xác nhận hai profile không làm thay đổi bean topology.

### Không ghi secret vào provenance

Build parameters và environment metadata cần đủ để tái tạo build, nhưng không được ghi password, token, private key, signing credential hoặc nội dung secret vào manifest/attestation. Dùng secret mount hoặc secret store của CI. Ghi tên secret reference/version nếu policy cho phép, không ghi giá trị secret.

Nếu Docker BuildKit tạo provenance `mode=max`, nhiều build arguments và thông tin build được ghi nhận chi tiết hơn. Vì vậy, không truyền secret qua Docker `ARG` hoặc `ENV`; dùng BuildKit secret mount.

## 7. Tạo build manifest cho native executable

Một file `build-info.json` là bản tóm tắt dễ đọc cho con người và hệ thống release. Nó không thay thế SLSA provenance đã ký, nhưng giúp đội vận hành tra cứu nhanh.

Ví dụ:

~~~json
{
  "schemaVersion": 1,
  "product": {
    "name": "orders-service",
    "version": "1.4.0",
    "buildId": "orders-service-1.4.0-build-1842",
    "artifactType": "graalvm-native-executable"
  },
  "source": {
    "repository": "https://github.com/acme/orders-service",
    "revision": "7f2a9c1d...full-commit-sha",
    "tree": "ab81e0...git-tree-sha",
    "dirty": false
  },
  "toolchain": {
    "builderImage": "ghcr.io/graalvm/native-image-community:21-ol9@sha256:...",
    "javaVersion": "21",
    "graalvmVersion": "recorded-version",
    "nativeImageVersion": "recorded-version",
    "nativeBuildToolsVersion": "recorded-version",
    "compiler": "recorded-compiler-version",
    "platform": "linux/amd64"
  },
  "build": {
    "command": "./mvnw -Pnative native:compile",
    "springAotProfile": "production",
    "nativeImageArguments": ["--gc=<approved-gc>"],
    "buildConfigurationSha256": "<sha256>",
    "dependencyManifestSha256": "<sha256>"
  },
  "artifact": {
    "file": "orders-service",
    "sha256": "<sha256-of-native-executable>"
  }
}
~~~

Các giá trị trong dấu `<...>` là placeholder cần được pipeline thay bằng dữ liệu thực. Không commit một manifest có version hoặc checksum giả vào release.

Manifest nên được lưu cạnh executable trong release bundle hoặc trong artifact metadata store. Nếu muốn đóng gói `build-info.json` vào container image, cần hiểu rằng nội dung file sẽ trở thành một phần của image và làm thay đổi image digest. Có thể giữ manifest ở ngoài image rồi gắn attestation vào digest cuối cùng.

Không nhúng digest của chính binary vào bên trong binary trước khi tính digest; việc đó tạo quan hệ tự tham chiếu. Tạo sidecar manifest sau khi binary đã build xong.

## 8. Hash các build inputs

Ngoài Git commit, có thể tạo file checksum cho các file mô tả build:

~~~bash
sha256sum pom.xml \
  .mvn/wrapper/maven-wrapper.properties \
  Dockerfile \
  .dockerignore \
  > build-inputs.sha256
~~~

Với Gradle:

~~~bash
sha256sum settings.gradle build.gradle gradle.properties \
  gradle.lockfile gradle/verification-metadata.xml \
  Dockerfile .dockerignore \
  > build-inputs.sha256
~~~

Điều chỉnh danh sách theo các file thực sự tồn tại trong project. Với Kotlin DSL, thêm `settings.gradle.kts` và `build.gradle.kts`; với multi-project, thêm build files của các subprojects và included builds. Nếu có custom reachability metadata, resource config hoặc Native Image arguments trong file riêng, đưa chúng vào input set.

Git commit đã định danh các file được track trong repository; file checksum bổ sung giúp xác minh các build inputs cụ thể trong artifact bundle. Nếu build tạo generated source hoặc tải toolchain ngoài repository, cần ghi nhận chúng trong provenance/dependency manifest.

## 9. Tạo SHA-256 cho native executable

Sau khi native compile hoàn tất, tính checksum cho executable:

~~~bash
sha256sum target/orders-service > target/orders-service.sha256
~~~

Với Gradle, thay đường dẫn bằng output binary thực tế, ví dụ:

~~~bash
sha256sum build/native/nativeCompile/orders-service \
  > build/native/nativeCompile/orders-service.sha256
~~~

Xác minh trước khi publish:

~~~bash
sha256sum --check target/orders-service.sha256
~~~

Trên PowerShell:

~~~powershell
Get-FileHash .\target\orders-service -Algorithm SHA256
~~~

SHA-256 là fingerprint của bytes tại thời điểm tính. Nếu executable thay đổi dù chỉ một byte, digest gần như chắc chắn đổi. Không dùng MD5 hoặc SHA-1 cho định danh bảo mật mới.

Lưu checksum sidecar trong cùng release bundle, nhưng bảo vệ bundle bằng chữ ký/attestation hoặc lưu checksum trong hệ thống metadata đáng tin cậy. Nếu checksum và binary được tải từ cùng một nơi không xác thực, attacker có thể thay cả hai.

## 10. Định danh container image bằng OCI digest

Sau khi đóng gói executable vào container, image có digest riêng. Digest này định danh manifest/config/layers của OCI image, không phải checksum của riêng executable.

Build và push image bằng Docker Buildx:

~~~bash
docker buildx build \
  --platform linux/amd64 \
  --provenance=mode=max \
  --sbom=true \
  --tag ghcr.io/acme/orders-service:1.4.0 \
  --push \
  --metadata-file buildx-metadata.json \
  .
~~~

Lấy digest từ metadata output:

~~~bash
jq -r '."containerimage.digest"' buildx-metadata.json
~~~

Lưu image reference dạng:

~~~text
ghcr.io/acme/orders-service@sha256:<OCI_IMAGE_DIGEST>
~~~

Triển khai theo digest thay vì chỉ theo tag. Tag `1.4.0` hữu ích cho con người, nhưng có thể bị registry policy hoặc người có quyền ghi di chuyển. Digest bất biến giúp xác định đúng nội dung image đã được kiểm thử.

### Multi-architecture image

Với image multi-arch, digest của manifest list/index xác định tập platform manifests. Từng platform manifest có digest riêng. Lưu cả:

- Index/manifest-list digest được deploy.
- Platform `linux/amd64` hoặc `linux/arm64`.
- Digest của platform manifest tương ứng nếu pipeline cần audit từng binary.

Không coi checksum của executable amd64 là checksum cho arm64. Mỗi binary phải có manifest và test evidence riêng.

## 11. SBOM cho cả build inputs và runtime image

SBOM liệt kê software components như thư viện, version, license và package identifiers. Với Native Image, có hai phạm vi cần quan tâm:

1. **Build-time dependencies:** GraalVM, compiler/linker, Maven/Gradle, plugin, annotation processor và thư viện dùng trong lúc build.
2. **Runtime/application dependencies:** thư viện Java đã được biên dịch vào executable và OS libraries cần khi chạy container.

Multi-stage Dockerfile thường chỉ đưa executable vào final stage. Nếu SBOM tool chỉ scan final stage, nó có thể không thấy Maven/Gradle dependencies và compiler đã tham gia build. Docker BuildKit hỗ trợ SBOM attestation; mặc định việc scan tập trung vào final stage, có thể cấu hình scan context/stage để thu thập thêm build-time materials.

Ví dụ bật SBOM:

~~~bash
docker buildx build --sbom=true --push \
  --tag ghcr.io/acme/orders-service:1.4.0 .
~~~

SBOM nên gắn với đúng image digest và được lưu trong registry/attestation store. Nếu tạo SBOM riêng cho dependency graph Maven/Gradle, lưu digest của SBOM đó trong build manifest hoặc provenance.

SBOM là inventory, không phải kết luận rằng mọi package an toàn. Pipeline vẫn cần vulnerability scanning, license policy và quy trình xử lý CVE.

## 12. Build provenance và in-toto/SLSA attestation

**Provenance** là dữ liệu có thể xác minh về nơi, thời điểm và cách artifact được tạo. SLSA Build Provenance mô tả các nhóm thông tin:

- `builder`: nền tảng/build service đã thực hiện build.
- `buildType`: loại quy trình hoặc template build.
- `externalParameters`: tham số bên ngoài ảnh hưởng build.
- `resolvedDependencies`: các source/dependency inputs đã được resolve.
- `subject`: artifact output được định danh bằng digest.

In-toto Statement gắn `subject` (tên và digest của artifact) với `predicateType` và nội dung provenance. Attestation cần được ký bởi builder hoặc identity được tin cậy để consumer có thể xác minh nguồn gốc.

Ví dụ cấu trúc khái niệm:

~~~json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [
    {
      "name": "orders-service",
      "digest": {
        "sha256": "<native-executable-digest>"
      }
    }
  ],
  "predicateType": "https://slsa.dev/provenance/v1",
  "predicate": {
    "buildDefinition": {
      "buildType": "https://example.com/buildtypes/spring-boot-native/v1",
      "externalParameters": {
        "sourceRevision": "<full-git-commit>",
        "target": "linux/amd64",
        "buildProfile": "production"
      },
      "resolvedDependencies": []
    },
    "runDetails": {
      "builder": {
        "id": "https://ci.example.com/builders/native-release"
      }
    }
  }
}
~~~

Đây là ví dụ để hiểu cấu trúc, không phải attestation có thể tự tin cậy. Trong production, dùng CI platform hoặc BuildKit tạo provenance, sau đó ký attestation bằng identity của builder hoặc CI signing service đã được tin cậy. Không tự điền `builder.id` rồi coi JSON tự tạo là bằng chứng có nguồn gốc đáng tin.

### BuildKit provenance

Docker Buildx có thể gắn provenance attestation vào image:

~~~bash
docker buildx build \
  --provenance=mode=max \
  --sbom=true \
  --push \
  --tag ghcr.io/acme/orders-service:1.4.0 \
  .
~~~

`mode=max` ghi chi tiết hơn về build parameters và materials so với mức tối thiểu. Hãy tránh secret trong build args/environment vì metadata chi tiết có thể làm lộ thông tin cấu hình. Attestation được gắn với image; khi push lên registry hỗ trợ OCI referrers/attestations, giữ nguyên digest và metadata liên quan.

## 13. Ký artifact và xác minh attestation

Pipeline nên tạo chữ ký hoặc signed attestation sau khi xác định digest. Có thể dùng keyless signing qua OIDC/Sigstore hoặc key quản lý bởi KMS/HSM theo chính sách tổ chức.

Với GitHub Actions, artifact attestation có thể gắn provenance với binary hoặc container image. Workflow cần quyền phù hợp, ví dụ `id-token: write`, `contents: read`, `attestations: write`; việc tạo attestation được thực hiện bằng action hỗ trợ của nền tảng.

Xác minh attestation của binary bằng GitHub CLI:

~~~bash
gh attestation verify target/orders-service \
  -R acme/orders-service
~~~

Xác minh attestation của container image:

~~~bash
gh attestation verify \
  oci://ghcr.io/acme/orders-service:1.4.0 \
  -R acme/orders-service
~~~

Sau khi verify chữ ký, consumer vẫn cần kiểm tra policy:

- Repository/source revision có đúng repository được phép không?
- Commit có nằm trong branch/tag đã được phê duyệt không?
- Builder identity có nằm trong allowlist không?
- Workflow/build type có phải release workflow tin cậy không?
- Toolchain, target platform và build parameters có đúng policy không?
- Subject digest trong attestation có trùng digest artifact đang deploy không?
- Dependency/SBOM có vi phạm vulnerability hoặc license policy không?

Attestation không bảo đảm artifact không có lỗ hổng. Nó giúp xác minh artifact được tạo ở đâu và bằng quy trình nào; consumer vẫn phải đánh giá source, dependency và kết quả kiểm thử.

## 14. CI pipeline cho Spring Boot Native Image

Một pipeline release có thể chia thành các gate sau:

~~~mermaid
flowchart TD
    A["Checkout immutable commit"] --> B["Verify clean tree + source identity"]
    B --> C["Pin builder/toolchain"]
    C --> D["Verify dependencies + lock/checksum"]
    D --> E["Run JVM tests + AOT/native tests"]
    E --> F["Build native executable"]
    F --> G["Create build manifest + SHA-256"]
    G --> H["Generate SBOM + provenance"]
    H --> I["Build OCI image + record digest"]
    I --> J["Sign/attest exact digest"]
    J --> K["Verify signature + release policy"]
    K --> L["Deploy by immutable digest"]
~~~

Ví dụ các bước shell cho Linux runner:

~~~bash
set -euo pipefail

# 1. Source identity
GIT_COMMIT="$(git rev-parse HEAD)"
GIT_TREE="$(git rev-parse HEAD^{tree})"
test -z "$(git status --porcelain)"

# 2. Toolchain identity
java -version
native-image --version
./mvnw -version

# 3. Dependency graph
./mvnw -B -ntp dependency:tree \
  -DoutputFile=target/dependency-tree.txt

# 4. Build and test (use the project's approved native profile)
./mvnw -B -ntp verify
./mvnw -B -ntp -Pnative -DskipTests native:compile

# 5. Artifact checksum
sha256sum target/orders-service \
  > target/orders-service.sha256
sha256sum --check target/orders-service.sha256

# 6. Hash important build inputs
sha256sum pom.xml Dockerfile \
  .mvn/wrapper/maven-wrapper.properties \
  > target/build-inputs.sha256
~~~

Command cụ thể phụ thuộc cách project cấu hình Maven Native Build Tools; một số project gắn native compile vào `package`, project khác dùng goal/task riêng. Pipeline cần dùng đúng một build definition đã được review và ghi lại command thực tế. Không chạy hai native build liên tiếp với cấu hình khác nhau rồi chỉ lưu checksum của output cuối.

Sau khi tạo executable, pipeline tạo `build-info.json`, SBOM và provenance; sau đó đóng gói image, lấy OCI digest, ký/attest digest và chạy policy verification trước deploy.

### Release gates đề xuất

| Gate | Điều kiện pass |
|---|---|
| Source | Commit đầy đủ, working tree sạch, submodules/LFS đúng revision |
| Toolchain | Builder image digest và compiler/tool versions nằm trong allowlist |
| Dependencies | Lock/verification/checksum pass; không có dependency chưa review |
| Tests | JVM, AOT và native integration tests pass theo release policy |
| Binary | Executable tồn tại, đúng target, SHA-256 được ghi nhận |
| SBOM | SBOM được tạo, parse được và qua vulnerability/license policy |
| Provenance | Attestation có chữ ký hợp lệ và subject digest đúng |
| Container | Image scan pass, OCI digest được lưu |
| Deployment | Policy verification pass; deploy bằng digest đã xác minh |

## 15. Reproducible build và ý nghĩa của việc build lại

Một build reproducible có thể tạo ra artifact có cùng bytes khi dùng cùng source, build instructions và môi trường tương đương. Đây là mức kiểm chứng mạnh hơn việc ghi lại version và checksum của một lần build.

Với Maven, có thể cấu hình reproducible archive timestamp:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Giá trị timestamp phải được quản lý nhất quán theo release/build policy. Maven yêu cầu các plugin đóng gói hỗ trợ reproducible mode; có thể kiểm tra archive build bằng:

~~~bash
./mvnw clean install
./mvnw clean verify artifact:compare
~~~

Kiểm tra này hữu ích cho Maven artifacts như JAR, nhưng không tự chứng minh GraalVM native executable reproducible. Với native binary, cần build lại trong môi trường độc lập nhưng được pin tương đương rồi so sánh SHA-256 trực tiếp.

Native Image có thể phụ thuộc vào OS image, compiler/linker, architecture, file path, timestamps, PGO profile và các build inputs khác. Vì vậy:

- Pin builder image bằng digest.
- Pin plugin và dependency versions.
- Cố định build arguments và environment ảnh hưởng output.
- Tránh đọc file không được version hóa từ runner.
- Không dùng dependency động hoặc `SNAPSHOT` cho release.
- Ghi rõ target architecture và libc baseline.
- So sánh output của independent rebuild trước khi tuyên bố reproducible.

Nếu hai build có checksum khác nhau, không nhất thiết artifact bị xâm phạm; có thể build chưa reproducible. Cần so sánh provenance, build inputs và environment để xác định nguồn khác biệt.

## 16. Promote cùng một artifact qua các môi trường

Một lỗi thường gặp là build lại binary cho staging rồi build lại lần nữa cho production. Hai lần build có thể khác digest dù cùng version và source commit.

Quy trình promotion an toàn hơn:

1. Build một lần từ commit đã phê duyệt.
2. Tạo binary, container image, SBOM và provenance.
3. Chạy test/scan trên đúng digest đó.
4. Đưa cùng OCI digest qua staging và production.
5. Thay đổi runtime configuration bằng environment/secret/config store.
6. Không rebuild chỉ để đổi environment-specific secrets hoặc endpoint runtime.

Nếu Spring AOT profile hoặc property làm thay đổi bean topology, đó là build-time input. Khi staging và production cần bean set khác nhau, tạo artifact variant riêng và định danh riêng; không âm thầm đổi property runtime rồi kỳ vọng AOT tái tạo bean definitions.

Deploy theo digest:

~~~text
ghcr.io/acme/orders-service@sha256:<verified-image-digest>
~~~

Lưu lại release record gồm source commit, build ID, binary digest, image digest, attestation reference, SBOM digest, target platform và deployment environment.

## 17. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Cùng version nhưng binary digest khác | Toolchain, dependency, build flags hoặc environment khác | So sánh manifest/provenance của hai build |
| Checksum sidecar pass nhưng không biết ai tạo artifact | Hash không có chữ ký hoặc trust anchor | Verify signed attestation và builder identity |
| Git commit giống nhau nhưng output khác | Working tree dirty, submodule/LFS hoặc generated input khác | Kiểm tra tree, clean state và resolved dependencies |
| Nâng GraalVM làm digest thay đổi | Compiler/toolchain thay đổi output | Ghi toolchain version, build lại test và tạo release mới |
| Gradle resolve dependency version khác giữa CI và local | Chưa bật dependency locking | Commit lockfiles và bật lockAllConfigurations |
| Dependency tải về có checksum khác | Artifact/cache/repository bị thay đổi hoặc metadata sai | Fail build, kiểm tra repository và xác minh thủ công |
| Maven checksum policy chỉ cảnh báo | Repository policy đang dùng `warn` | Chuyển sang `fail` theo release policy |
| Provenance có subject digest không khớp image | Attestation tạo cho tag hoặc artifact khác | Gắn attestation vào đúng digest được push |
| SBOM không có build-time dependencies | Chỉ scan final stage của multi-stage image | Scan builder/context hoặc tạo build-time SBOM riêng |
| Image tag đúng nhưng deploy bytes khác | Tag mutable đã bị di chuyển | Deploy và audit theo OCI digest |
| Multi-arch release thiếu một platform | Chỉ một kiến trúc được build/test | Build artifact riêng và verify từng platform manifest |
| Build manifest chứa secret | Ghi raw environment/build args | Xóa secret khỏi metadata; dùng secret mount và rotate secret nếu đã lộ |

## 18. Checklist định danh release

- [ ] Có service name, version và build ID duy nhất.
- [ ] Có repository URI, full commit SHA và Git tree SHA.
- [ ] Working tree sạch; submodule và Git LFS revisions đã được ghi nhận.
- [ ] GraalVM builder image được pin bằng digest.
- [ ] JDK, GraalVM, Native Image, compiler/linker và Native Build Tools versions đã ghi lại.
- [ ] Maven plugin/dependency versions được pin hoặc Gradle lock state được commit.
- [ ] Dependency verification metadata được review và áp dụng trong CI.
- [ ] Spring AOT profile, Native Image flags, RuntimeHints và target platform được ghi nhận.
- [ ] Build manifest không chứa secret.
- [ ] Native executable có SHA-256 sidecar và được verify trước publish.
- [ ] SBOM bao phủ runtime components và build-time materials theo policy.
- [ ] Provenance attestation gắn đúng subject digest.
- [ ] Attestation signature và builder identity được xác minh.
- [ ] OCI image digest được lưu và deploy theo digest.
- [ ] Multi-arch artifacts được build/test riêng cho từng kiến trúc.
- [ ] Có release record liên kết source, binary, image, SBOM, attestation và deployment.

## 19. Bài tập tự kiểm tra

**Câu 1.** SHA-256 của executable có chứng minh binary được build từ commit đã phê duyệt không?

**Gợi ý:** không. Nó định danh bytes; cần provenance/attestation đã ký để liên kết digest với source và builder.

**Câu 2.** Vì sao phải ghi nhận cả `native-image --version` và builder image digest?

**Gợi ý:** version mô tả tool; image digest xác định chính xác builder filesystem và các package/toolchain nằm trong image.

**Câu 3.** Gradle dependency locking và dependency verification khác nhau thế nào?

**Gợi ý:** locking cố định version đã resolve; verification kiểm tra checksum/chữ ký của artifact được tải.

**Câu 4.** Vì sao `build-info.json` không nên chứa digest của chính nó?

**Gợi ý:** digest tự tham chiếu tạo vòng lặp; tạo manifest sau khi artifact đã có digest và giữ checksum manifest ở sidecar/attestation riêng.

**Câu 5.** SBOM của final container có chắc chắn chứa Maven/Gradle build dependencies không?

**Gợi ý:** không. Multi-stage build có thể bỏ builder stage khỏi final image scan; cần thu thập build-time materials riêng hoặc cấu hình scan thêm stage/context.

**Câu 6.** Vì sao deploy theo OCI digest an toàn hơn chỉ dùng tag?

**Gợi ý:** tag có thể được di chuyển; digest xác định nội dung manifest cụ thể đã được xác minh.

**Câu 7.** Hai lần build cùng commit nhưng checksum native executable khác nhau có nghĩa là bị tấn công không?

**Gợi ý:** chưa thể kết luận. Có thể do toolchain, environment hoặc build inputs khác; so sánh provenance và thử independent rebuild.

## 20. Tài liệu tham khảo

- [SLSA — Build Provenance v1.2](https://slsa.dev/spec/v1.2/build-provenance): builder, build definition, parameters, resolved dependencies và artifact subjects.
- [SLSA — Verifying Artifacts](https://slsa.dev/spec/v1.2/verifying-artifacts): xác minh chữ ký, builder identity, build type và parameters.
- [in-toto — Attestation Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md): cách gắn subject digest với predicate.
- [Docker — Build attestations](https://docs.docker.com/build/metadata/attestations/): SBOM/provenance attestations và cách gắn với image.
- [Docker — Provenance attestations](https://docs.docker.com/build/metadata/attestations/slsa-provenance/): build parameters, materials và SLSA provenance.
- [Docker — SBOM attestations](https://docs.docker.com/build/metadata/attestations/sbom/): SPDX SBOM, scan final stage và build-time dependencies.
- [Gradle — Dependency verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum và signature verification.
- [Gradle — Dependency locking](https://docs.gradle.org/current/userguide/dependency_locking.html): cố định dependency versions.
- [Maven — Reproducible Builds](https://maven.apache.org/guides/mini/guide-reproducible-builds.html): reproducible archive timestamp và cách so sánh build.
- [Maven — Settings reference](https://maven.apache.org/settings.html): checksum policy cho repository artifacts.
- [GitHub — Artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations): tạo và verify provenance attestation cho binary/container image.

**Ghi nhớ:** Định danh release Native Image phải nối được source commit, toolchain, dependency graph, build configuration, target platform và digest của đúng output. SHA-256 xác nhận bytes; SBOM mô tả thành phần; provenance đã ký liên kết artifact với quy trình build. CI cần xác minh tất cả các bằng chứng đó trước khi promote cùng OCI digest qua staging và production.
