# Truy vết bản phát hành từ mã nguồn tới JDK và checkpoint

Với Java CRaC (Coordinated Restore at Checkpoint), một bản phát hành không chỉ là file JAR hoặc container image. Ứng dụng còn phụ thuộc vào JDK cụ thể, bản build có CRaC, thư viện native, cấu hình JVM, môi trường kernel/CRIU và trạng thái tiến trình được lưu trong checkpoint. Nếu không lưu quan hệ giữa những thành phần này, khi một Pod gặp lỗi hoặc cần rollback, nhóm vận hành khó xác định checkpoint được tạo từ mã nguồn nào, bằng JDK nào và có phù hợp với node đang restore hay không.

Truy vết bản phát hành là khả năng đi từ một checkpoint đang chạy ngược về đúng source commit, build, dependency, image, JDK và môi trường tạo ảnh; đồng thời đi xuôi từ một commit đến mọi artifact và checkpoint được tạo ra từ nó. Mỗi mắt xích cần có định danh bất biến, checksum hoặc chữ ký, thông tin build và mối liên hệ rõ ràng với mắt xích trước đó.

Một chuỗi truy vết điển hình:

~~~text
Git commit
   |
   v
CI run + build toolchain + dependency lock
   |
   v
JAR / application artifact + SBOM + build provenance
   |
   v
OCI image digest + exact JDK/CRaC + native runtime
   |
   v
Warm-up profile + runtime configuration
   |
   v
Checkpoint files + checkpoint manifest + signatures
   |
   v
Restore target (kernel / CRIU / CPU / container runtime)
   |
   v
Running Pod + release identity + restore attempt
~~~

Mục tiêu là để người vận hành có thể trả lời chính xác: Pod này chạy source commit nào? Checkpoint được tạo bởi JDK build nào? Image và native libraries có đúng với manifest không? Ảnh này được restore trên node pool nào? Nếu cần rollback, artifact nào đã được kiểm chứng?

## 1. Vì sao CRaC cần truy vết sâu hơn một bản phát hành Java thông thường?

Trong triển khai Java thông thường, nhóm phát hành thường truy vết từ source commit đến JAR hoặc container image. Khi khởi động, JVM bắt đầu từ đầu và tạo runtime state mới.

Với CRaC, checkpoint lưu trạng thái một tiến trình đã chạy. Trạng thái đó có thể chứa:

- Heap và object graph của ứng dụng.
- Class metadata và trạng thái class initialization.
- JIT-compiled code và runtime metadata.
- Thread state, stack và một số trạng thái native.
- Các object client, cache và cấu hình đã được nạp.
- Trạng thái liên quan đến thư viện native và resource đã mở, tùy khả năng hỗ trợ.

Checkpoint vì vậy gắn với một tổ hợp đầu vào và môi trường tạo ảnh. Cùng một JAR có thể được chạy với hai JDK build khác nhau, JVM flags khác nhau, native dependency khác nhau hoặc CPU feature khác nhau. Những khác biệt này có thể ảnh hưởng đến khả năng restore và hành vi sau restore.

### 1.1. JAR không xác định đầy đủ runtime

Một file JAR không cho biết đầy đủ:

- JDK vendor, version và build number.
- JDK có CRaC support và patch nào.
- JVM flags và GC configuration.
- Base image và OS package.
- glibc hoặc musl version.
- OpenSSL, zlib và native library.
- CPU architecture và baseline instruction set.
- Kernel, CRIU, container runtime và security policy.

Vì vậy, chỉ lưu version ứng dụng như 2.4.1 là chưa đủ để xác định checkpoint có thể restore ở đâu.

### 1.2. Checkpoint là artifact có lineage riêng

Checkpoint phải có định danh riêng, liên kết đến release mà nó được tạo ra. Một release có thể tạo nhiều checkpoint do khác:

- Warm-up profile.
- Cấu hình runtime.
- Node pool hoặc CPU baseline.
- JDK/CRaC build.
- Kernel/CRIU environment.
- Bộ dữ liệu hoặc cấu hình warm-up.

Không nên dùng cùng một tên artifact cho các ảnh khác nhau. Mỗi checkpoint cần một checkpoint ID và digest riêng, ngay cả khi chúng xuất phát từ cùng source commit.

### 1.3. Truy vết giúp xử lý sự cố và rollback

Khi restore thất bại, lineage giúp khoanh vùng:

- Source thay đổi hay dependency thay đổi?
- JDK build có khác với bản đã kiểm thử?
- Checkpoint có bị thay đổi hoặc hỏng trong quá trình lưu trữ?
- Node restore có khác kernel, CPU hoặc CRIU baseline?
- Warm-up đã nạp cấu hình hoặc secret nào?
- Pod có dùng đúng checkpoint của release hiện tại không?

Khi rollback, có thể chọn đúng checkpoint đã được kiểm thử cùng image, JDK và môi trường tương thích thay vì chọn một file chỉ có tên gần giống.

## 2. Mô hình định danh cho toàn bộ chuỗi phát hành

Mỗi tầng cần có định danh không thay đổi sau khi artifact được phát hành.

| Thành phần | Định danh nên lưu | Ví dụ |
|---|---|---|
| Source | Git commit SHA | a1b2c3... |
| Source tree | Tree SHA và trạng thái clean/dirty | tree:..., clean=true |
| Release | Release ID | orders-api-2026.11.13.2 |
| CI build | Pipeline run ID và attempt | build-84721/1 |
| Build toolchain | Gradle/Maven, compiler và builder image digest | gradle-8.x, sha256:... |
| Dependency graph | Lockfile checksum | sha256:... |
| Application artifact | JAR SHA-256 | sha256:... |
| Container image | OCI image digest | sha256:... |
| JDK | Vendor, version, build và image digest | Exact distribution/build |
| Native runtime | libc, OpenSSL, JNI library versions | Package/version/digest |
| Runtime config | JVM flags và config profile version | runtime-profile-v7 |
| Warm-up | Scenario set và dataset version | warmup-profile-v4 |
| Checkpoint | Checkpoint ID và file digests | checkpoint-... |
| Restore target | Node pool, arch, kernel, CRIU | linux-x86-pool-a |
| Restore attempt | Pod UID và attempt ID | podUID/restore-2 |

Tên tag như latest, stable hoặc production có thể hữu ích cho người dùng, nhưng không nên là bằng chứng duy nhất về danh tính artifact. Tag có thể được trỏ sang nội dung khác. Digest, commit SHA và build ID mới là những giá trị phù hợp để truy vết.

### 2.1. Release ID và checkpoint ID có vai trò khác nhau

Release ID nhận diện một phiên bản ứng dụng được phát hành. Checkpoint ID nhận diện một lần tạo ảnh cụ thể.

Ví dụ:

- Release: orders-api-2026.11.13.2
- Source commit: a1b2c3d4...
- Checkpoint: orders-api-2026.11.13.2-jdk21crac-x86-pool-a-warm4-01

Một release có thể có nhiều checkpoint:

| Release | Checkpoint | Lý do |
|---|---|---|
| orders-api-2026.11.13.2 | cp-x86-pool-a-001 | CPU baseline A |
| orders-api-2026.11.13.2 | cp-x86-pool-b-001 | Kernel/runtime pool B |
| orders-api-2026.11.13.2 | cp-x86-pool-a-002 | Warm-up profile mới |

Các checkpoint này cùng trỏ về một source release nhưng có lineage môi trường khác nhau.

## 3. Truy vết từ Git source

Điểm đầu tiên là xác định chính xác source tree được dùng để build.

Thông tin nên lưu:

- Repository URL hoặc repository identity.
- Commit SHA đầy đủ.
- Branch và tag tại thời điểm build.
- Git tree SHA.
- Trạng thái working tree.
- Submodule commit nếu có.
- Git LFS object identity nếu sử dụng.
- Patch hoặc generated source có tham gia build.
- Thời điểm build và danh tính CI workflow.

### 3.1. Không build từ working tree không xác định

Build từ working tree có thay đổi chưa commit làm cho commit SHA không còn mô tả đầy đủ nội dung đã build.

CI nên kiểm tra working tree sạch hoặc ghi rõ patch/diff được dùng. Với build production, cách dễ truy vết nhất là build từ một commit bất biến trong CI checkout sạch.

Các lệnh Git thường dùng:

~~~bash
git rev-parse HEAD
git rev-parse HEAD^{tree}
git status --porcelain
git submodule status --recursive
git describe --tags --always --dirty
~~~

Lệnh git status --porcelain không có output thường cho biết working tree sạch. Nếu có thay đổi, build provenance cần ghi nhận chính xác thay đổi đó hoặc pipeline nên dừng trước khi tạo release artifact.

### 3.2. Commit SHA phải đi cùng repository identity

Commit SHA chỉ có ý nghĩa khi biết repository nào chứa commit đó. Hai repository khác nhau có thể có object SHA giống nhau về mặt lý thuyết hoặc cùng dùng một commit được mirror.

Nên lưu repository URL chuẩn hóa, organization/project identity và commit SHA. Nếu dùng mirror, ghi cả upstream identity và mirror build source.

### 3.3. Source tag không thay thế commit SHA

Tag có thể bị di chuyển hoặc xóa nếu repository cho phép. Hãy lưu tag để dễ đọc nhưng dùng commit SHA làm định danh chính. Release tag nên được bảo vệ theo quy trình quản trị repository.

## 4. Truy vết build và dependency

Cùng một source commit vẫn có thể tạo artifact khác nhau nếu toolchain hoặc dependency thay đổi.

Các đầu vào build cần ghi nhận:

- Gradle hoặc Maven version.
- JDK dùng để chạy build.
- Java compiler version và options.
- Plugin versions.
- Dependency lockfiles.
- Repository/mirror được dùng để tải dependency.
- Build container image digest.
- Build arguments và environment variables không nhạy cảm.
- Test result và test suite version.
- Build script revision.
- Generated code và code generator versions.

### 4.1. Dependency locking

Dependency declaration dạng version range hoặc dynamic version có thể resolve ra kết quả khác ở hai lần build. Dùng dependency locking hoặc dependency verification để giảm thay đổi không kiểm soát.

Với Gradle, cần lưu các file lock và verification metadata trong source control theo chính sách dự án. Với Maven, có thể dùng dependency management và repository policy để kiểm soát phiên bản.

### 4.2. Build toolchain cũng là đầu vào

Cùng source và dependency nhưng khác compiler hoặc build plugin có thể tạo bytecode hoặc resource khác nhau. Vì vậy, build provenance nên lưu:

- Build tool version.
- JDK vendor/version/build của build runner.
- OS/architecture của runner.
- Build image digest.
- Compiler flags.
- Plugin versions.

### 4.3. Kiểm tra JAR sau build

Tính digest của artifact và ghi vào release metadata:

~~~bash
sha256sum build/libs/orders-api.jar
jar --describe-module --file build/libs/orders-api.jar
unzip -l build/libs/orders-api.jar
~~~

Các lệnh là ví dụ cho Linux runner. Trên Windows có thể dùng Get-FileHash để tính SHA-256. Digest phải được tính trên đúng file sẽ được đóng gói và phát hành.

Không nên tính checksum một file rồi sau đó thay đổi nội dung file trước khi build container. Nếu artifact được transform hoặc repackage, cần tính digest ở từng tầng.

## 5. SBOM và build provenance

SBOM (Software Bill of Materials) mô tả các thành phần phần mềm có trong một artifact. Build provenance mô tả artifact được tạo ra như thế nào và từ đầu vào nào.

Hai loại thông tin này bổ sung cho nhau:

- SBOM trả lời: “Artifact chứa những package/library nào?”
- Provenance trả lời: “Artifact được build từ source, toolchain và workflow nào?”

### 5.1. SBOM cho application artifact

SBOM nên ghi nhận dependency trực tiếp và gián tiếp, bao gồm version và package identity. Các định dạng phổ biến gồm SPDX và CycloneDX.

Với Java application, SBOM có thể bao gồm:

- Maven/Gradle dependencies.
- Framework và library.
- Native package được đóng gói trong image.
- JNI library.
- Các package hệ điều hành trong container image.

SBOM của JAR chưa mô tả toàn bộ JDK và OS package nếu chúng nằm ở base image. Có thể cần SBOM riêng cho image hoặc một báo cáo hợp nhất.

### 5.2. Provenance cho build

Provenance nên gắn artifact digest với:

- Source repository và commit.
- Build invocation.
- Builder identity.
- Build environment.
- Dependency resolution.
- Build parameters.
- Kết quả kiểm tra cần thiết.

Có thể sử dụng các mô hình attestation như in-toto/SLSA provenance. Mục tiêu không phải chỉ tạo một file JSON, mà là tạo một bằng chứng có nguồn phát hành đáng tin cậy, có thể xác minh và liên kết đến artifact digest.

### 5.3. SBOM không phải checkpoint manifest

SBOM mô tả phần mềm. Checkpoint manifest còn phải mô tả runtime và môi trường tạo ảnh:

- JDK CRaC build.
- JVM flags.
- Kernel và CRIU.
- CPU architecture/baseline.
- libc và native libraries.
- Container image digest.
- Warm-up profile.
- Checkpoint file digests.
- Restore compatibility constraints.

Nên liên kết SBOM và provenance của image vào checkpoint manifest thay vì cố nhét toàn bộ thông tin package vào một trường không có cấu trúc.

## 6. Xác định chính xác JDK tạo checkpoint

JDK là một trong những mắt xích quan trọng nhất. Chỉ ghi Java 21 hoặc JDK 21 là chưa đủ.

Cần lưu:

- Vendor/distribution.
- Java runtime version.
- Full build string.
- VM name và VM version.
- CRaC support/patch level.
- JDK image digest.
- JDK package checksum nếu cài bằng package.
- JVM flags.
- GC và compiler configuration.
- Java modules/providers quan trọng.

### 6.1. Thu thập thông tin runtime

Các lệnh sau ghi lại thông tin Java trong môi trường tạo checkpoint:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Có thể ghi các system property quan trọng từ ứng dụng:

~~~java
public final class RuntimeIdentity {

    public static void print() {
        System.out.println("java.version="
                + System.getProperty("java.version"));
        System.out.println("java.vendor="
                + System.getProperty("java.vendor"));
        System.out.println("java.vm.name="
                + System.getProperty("java.vm.name"));
        System.out.println("java.vm.version="
                + System.getProperty("java.vm.version"));
        System.out.println("os.name="
                + System.getProperty("os.name"));
        System.out.println("os.version="
                + System.getProperty("os.version"));
        System.out.println("os.arch="
                + System.getProperty("os.arch"));
    }

    private RuntimeIdentity() {}
}
~~~

Các property này hữu ích cho quan sát runtime, nhưng không thay thế JDK image digest hoặc build provenance. Một số thông tin CRaC/CRIU cần được thu thập từ pipeline và host vì không phải tất cả đều được Java system property cung cấp.

### 6.2. Ghi JVM flags

JVM flags ảnh hưởng đến heap, GC, JIT, code cache và hành vi runtime. Nên lưu chính xác effective flags thay vì chỉ lưu một phần lệnh khởi chạy.

Có thể ghi nhận bằng công cụ JVM phù hợp, ví dụ:

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
~~~

PID là process ID của JVM trên host/container. Các lệnh cần được chạy trong môi trường có quyền truy cập process. Không đưa secret hoặc giá trị nhạy cảm vào manifest nếu chúng có thể xuất hiện trong command line.

### 6.3. JDK image digest là định danh mạnh hơn tag

Nếu dùng container base image chứa JDK, ghi OCI digest thay vì chỉ ghi tag như jdk:21-crac. Tag có thể thay đổi nội dung theo thời gian. Digest giúp xác định đúng image đã được dùng.

Nếu JDK được cài bằng package, ghi package version, repository identity và checksum của package hoặc nguồn cài đặt. Với build tùy biến, lưu source/build recipe và digest của output.

### 6.4. Tạo checkpoint mới khi JDK thay đổi

Khi thay JDK build, CRaC patch, JVM flags hoặc native runtime, không nên tiếp tục gắn checkpoint cũ với release mới mà không kiểm thử. Cần tạo checkpoint bằng runtime mới, restore trong môi trường mục tiêu và chạy smoke test.

## 7. Truy vết container image và native runtime

Checkpoint thường được tạo trong một container image cụ thể hoặc một runtime filesystem cụ thể. Image digest là mắt xích quan trọng giữa application artifact, JDK và OS package.

Nên lưu:

- OCI repository và digest.
- Base image digest.
- JAR digest bên trong image.
- JDK distribution/build.
- libc và dynamic linker.
- OpenSSL và các native package.
- JNI library và checksum.
- User/group và security configuration.
- Entrypoint, command và environment profile version.

### 7.1. Không chỉ lưu image tag

Ví dụ:

~~~text
registry.example.com/orders-api:2026.11
~~~

Tag này có thể được publish lại hoặc trỏ sang image khác. Trong manifest nên lưu digest:

~~~text
registry.example.com/orders-api@sha256:<image-digest>
~~~

Khi deploy, nên tham chiếu digest hoặc xác nhận tag đã resolve đúng digest được phát hành.

### 7.2. Native dependency cần checksum

Với JNI library hoặc native package quan trọng, lưu version và checksum. Điều này giúp phát hiện trường hợp cùng tên file nhưng nội dung đã thay đổi.

Các lệnh Linux hữu ích:

~~~bash
file /opt/app/lib/libexample.so
sha256sum /opt/app/lib/libexample.so
ldd /opt/app/lib/libexample.so
readelf -h /opt/app/lib/libexample.so
~~~

Không phải mọi native dependency đều nằm trong thư mục ứng dụng. SBOM image và package inventory cần bổ sung thông tin về thư viện hệ thống.

### 7.3. Ghi lại cấu hình môi trường không nhạy cảm

Một số cấu hình ảnh hưởng đến checkpoint:

- JAVA_TOOL_OPTIONS.
- JVM flags.
- Timezone và locale.
- Library search path.
- Memory limits.
- CPU limits.
- Mount layout.
- User ID và group ID.
- Security profile identity.

Chỉ lưu tên hoặc version của secret/config profile, không lưu giá trị credential vào manifest. Secret nên được resolve lại từ secret manager sau restore nếu có thể thay đổi.

## 8. Warm-up profile cũng là một phần của lineage

Checkpoint được tạo sau khi ứng dụng đã warm-up. Warm-up workload ảnh hưởng đến class loading, JIT profile, cache và live heap. Vì vậy, cần ghi lại cách warm-up đã được thực hiện.

Nên lưu:

- Warm-up profile ID và version.
- Danh sách scenario hoặc endpoint đã chạy.
- Số vòng và concurrency.
- Dataset version hoặc test tenant.
- Thời gian warm-up.
- Tiêu chí kết thúc warm-up.
- Cache policy và cache generation.
- Kết quả kiểm tra sau warm-up.
- Phiên bản script hoặc test harness.

### 8.1. Warm-up profile cần version hóa

Không nên chỉ ghi “warm-up completed”. Hai checkpoint cùng release có thể được tạo bằng workload khác nhau và có hiệu năng sau restore khác nhau.

Ví dụ:

| Profile | Nội dung |
|---|---|
| warmup-v1 | Khởi tạo framework và endpoint health |
| warmup-v2 | Thêm các endpoint đọc phổ biến |
| warmup-v3 | Thêm serializer và cache critical |
| warmup-v4 | Workload đại diện theo traffic profile mới |

Nếu profile thay đổi, tạo checkpoint mới và ghi rõ version.

### 8.2. Warm-up phải có thể giải thích và tái tạo

Lưu script, test harness hoặc scenario definition cùng source control. Nếu warm-up dùng dữ liệu, lưu dataset version hoặc input digest, không nhất thiết lưu dữ liệu nhạy cảm.

Khi điều tra latency sau restore, có thể đối chiếu checkpoint được tạo với profile nào và biết đường code nào đã được chạy trước checkpoint.

## 9. Checkpoint manifest

Checkpoint manifest là tài liệu mô tả danh tính và điều kiện tạo một checkpoint cụ thể. Nó liên kết source, build, image, JDK, native runtime, warm-up và artifact checkpoint.

Ví dụ YAML:

~~~yaml
schemaVersion: 1

release:
  id: "orders-api-2026.11.13.2"
  application: "orders-api"
  source:
    repository: "https://git.example.com/platform/orders-api"
    commit: "a1b2c3d4e5f6..."
    tree: "f1e2d3c4b5a6..."
    clean: true
    tag: "v2026.11.13.2"

build:
  id: "ci-84721-attempt-1"
  builderImage: "registry.example.com/builders/java@sha256:..."
  tool: "Gradle"
  toolVersion: "8.x"
  buildJdk: "vendor-version-build"
  dependencyLockDigest: "sha256:..."
  artifact:
    path: "orders-api.jar"
    sha256: "..."
  sbom:
    format: "CycloneDX"
    digest: "sha256:..."
  provenance:
    format: "in-toto"
    digest: "sha256:..."

container:
  image: "registry.example.com/orders-api@sha256:..."
  baseImage: "registry.example.com/jdk-crac@sha256:..."
  architecture: "amd64"

runtime:
  jdkVendor: "Exact vendor"
  javaRuntimeVersion: "Exact version and build"
  vmVersion: "Exact VM build"
  cracSupport: "Exact CRaC build"
  jvmFlagsDigest: "sha256:..."
  libc: "glibc exact package version"
  nativeLibraries:
    - name: "libexample.so"
      version: "1.8.2"
      sha256: "..."
    - name: "libssl.so"
      version: "exact-package-version"
      sha256: "..."

warmup:
  profile: "warmup-v4"
  scenarioDigest: "sha256:..."
  datasetVersion: "catalog-fixture-v12"
  durationSeconds: 75
  completed: true

checkpoint:
  id: "orders-api-2026.11.13.2-x86-poola-warm4-001"
  createdAt: "2026-11-13T08:30:00Z"
  files:
    - path: "checkpoint.img"
      sha256: "..."
    - path: "pages-1.img"
      sha256: "..."
  totalBytes: 123456789
  signature:
    artifact: "checkpoint-manifest.sig"
    identity: "release-ci"

platform:
  os: "Linux"
  architecture: "x86_64"
  kernelRelease: "exact-kernel-release"
  criuVersion: "exact-version"
  containerRuntime: "containerd exact-version"
  cgroupMode: "v2"
  cpuBaseline: "x86-64-v2"
  nodePoolProfile: "crac-linux-x86-pool-a"

restoreConstraints:
  allowedImageDigest: "sha256:..."
  allowedJdkBuild: "Exact version and build"
  allowedArchitecture: "x86_64"
  allowedNodePoolProfiles:
    - "crac-linux-x86-pool-a"
  requiresResourceReinitialization: true
~~~

Các giá trị là placeholder. Manifest thực tế cần được sinh từ CI/CD và checkpoint job. Không điền giá trị bằng tay nếu pipeline có thể thu thập tự động.

### 9.1. Manifest phải mô tả đúng các file checkpoint

Một checkpoint có thể gồm nhiều file. Nên lưu đường dẫn tương đối, kích thước và SHA-256 của từng file, cùng tổng dung lượng. Nếu công cụ đóng gói checkpoint thành archive, lưu digest của archive và digest của các file trước khi đóng gói nếu cần.

Không chỉ ghi checksum của một file chính nếu ảnh còn có các file memory page hoặc metadata khác.

### 9.2. Không nhúng secret vào manifest

Manifest có thể được chia sẻ rộng hơn checkpoint. Chỉ lưu secret reference, version ID hoặc provider path nếu cần truy vết. Không ghi password, token, private key hoặc nội dung credential.

Checkpoint có thể chứa heap và object nhạy cảm. Quyền đọc artifact, manifest và chữ ký cần được quản lý theo cùng chính sách bảo vệ release artifact.

## 10. Checkpoint không nhất thiết reproducible như JAR

Một build Java có thể hướng tới reproducible build: cùng source, dependency và toolchain tạo ra artifact giống nhau. Checkpoint thường khó tái tạo byte-for-byte vì chứa trạng thái runtime thay đổi theo thời điểm.

Các yếu tố có thể làm checkpoint khác nhau:

- Timestamp và metadata runtime.
- JIT compilation timing.
- Heap layout và object allocation.
- Thread state.
- Random state.
- Cache content.
- File descriptor và resource state.
- Host-specific mapping.
- Warm-up execution order.

Do đó, nên phân biệt:

- **Reproducible application build:** khả năng tạo lại JAR/image có cùng nội dung từ cùng đầu vào.
- **Repeatable checkpoint procedure:** có thể lặp lại quy trình tạo ảnh với cùng profile và điều kiện đã mô tả.
- **Checkpoint byte reproducibility:** hai lần tạo ảnh có digest giống hệt nhau; không nên mặc định đạt được.

Ngay cả khi checkpoint digest khác nhau, lineage vẫn có thể chứng minh cả hai ảnh được tạo từ cùng release và cùng runtime profile.

### 10.1. So sánh đầu vào thay vì kỳ vọng checkpoint giống byte-for-byte

Khi tạo lại checkpoint, so sánh:

- Source commit.
- JAR và image digest.
- JDK build.
- JVM flags.
- Native dependency.
- Warm-up profile.
- Kernel/CRIU/CPU profile.
- Restore test result.

Nếu đầu vào tương thích nhưng checkpoint digest khác, điều đó không tự động chứng minh có lỗi. Hãy kiểm tra hành vi restore, smoke test và performance baseline.

## 11. Tạo provenance và ký artifact

Checksum phát hiện thay đổi nội dung nếu checksum gốc được tin cậy. Chữ ký số và attestation giúp xác minh ai phát hành artifact và artifact gắn với provenance nào.

Một quy trình có thể gồm:

1. CI build JAR và container image.
2. Tạo SBOM và build provenance.
3. Ký image hoặc artifact digest.
4. Tạo checkpoint từ image đã xác minh.
5. Tạo checkpoint manifest.
6. Tính digest cho toàn bộ checkpoint.
7. Ký manifest hoặc attestation chứa checkpoint digest.
8. Lưu artifact và metadata trong registry/storage có kiểm soát.

Có thể dùng công cụ ký container/artifact như Cosign hoặc hệ thống ký nội bộ. Cách tích hợp phụ thuộc registry và chính sách tổ chức.

### 11.1. Ký manifest và liên kết với checkpoint digest

Một chữ ký chỉ trên manifest có ý nghĩa khi manifest chứa digest của artifact. Khi xác minh, hệ thống cần:

- Xác minh chữ ký manifest.
- Đọc danh sách file trong manifest.
- Tính lại digest từng file hoặc archive.
- So sánh digest thực tế với digest đã ký.
- Xác nhận release ID và image digest phù hợp.

Nếu chỉ ký tên file mà không ràng buộc nội dung bằng digest, file có thể bị thay đổi mà tên vẫn giữ nguyên.

### 11.2. Attestation của checkpoint

Checkpoint có thể được xem như một artifact riêng với subject digest. Attestation nên tham chiếu:

- Checkpoint digest.
- Checkpoint manifest digest.
- Source commit.
- Application image digest.
- JDK build.
- Builder identity.
- Restore test evidence.

Như vậy, hệ thống có thể kiểm tra một checkpoint cụ thể đã được tạo từ release nào và bởi pipeline nào.

### 11.3. Kiểm soát danh tính CI

Provenance chỉ đáng tin khi danh tính builder được xác thực. Nên dùng CI identity có thể xác minh, quyền phát hành tối thiểu và log không thể sửa đổi tùy tiện.

Không dùng credential ký chung được lưu trong repository. Tốt hơn là dùng workload identity, key management service hoặc signing service được quản lý.

## 12. Ví dụ kiểm tra digest và chữ ký

Với file artifact đơn:

~~~bash
sha256sum orders-api.jar
sha256sum checkpoint-manifest.yml
~~~

Với image OCI, lấy digest từ registry sau khi push và lưu digest trả về. Không chỉ ghi tag được dùng lúc build.

Ví dụ lệnh ký/xác minh image với Cosign (cú pháp và phương thức xác thực tùy phiên bản, registry và chính sách tổ chức):

~~~bash
cosign sign registry.example.com/orders-api@sha256:<image-digest>
cosign verify registry.example.com/orders-api@sha256:<image-digest>
~~~

Với checkpoint manifest, có thể ký chính file manifest hoặc tạo attestation theo subject digest của checkpoint. Hãy dùng signing policy phù hợp và lưu public verification identity cùng metadata.

Không ký checkpoint trước khi toàn bộ file đã được ghi xong và digest đã được tính. Nếu artifact thay đổi sau khi ký, phải tạo manifest và chữ ký mới.

## 13. Gắn release identity vào ứng dụng đang chạy

Thông tin build có thể được đóng gói vào resource trong JAR để ứng dụng tự báo cáo release identity. Ví dụ resource build-info.properties:

~~~properties
application.name=orders-api
application.version=2026.11.13.2
source.commit=a1b2c3d4e5f6
build.id=ci-84721-attempt-1
artifact.sha256=...
image.digest=sha256:...
warmup.profile=warmup-v4
~~~

Các giá trị này nên được sinh tự động trong CI. Không sửa tay sau build vì điều đó làm thay đổi artifact và khiến digest không còn khớp.

### 13.1. Đọc build identity trong Java

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class BuildIdentity {

    private final Properties properties = new Properties();

    public BuildIdentity() throws IOException {
        try (InputStream input =
                BuildIdentity.class.getResourceAsStream(
                    "/build-info.properties")) {

            if (input == null) {
                throw new IllegalStateException(
                    "build-info.properties is missing"
                );
            }

            properties.load(input);
        }
    }

    public String get(String key) {
        return properties.getProperty(key, "unknown");
    }

    public String releaseId() {
        return get("application.version");
    }

    public String sourceCommit() {
        return get("source.commit");
    }

    public String buildId() {
        return get("build.id");
    }
}
~~~

Có thể expose các trường an toàn qua endpoint nội bộ hoặc log lúc startup. Không expose toàn bộ JVM flags, environment variables hoặc secret cho endpoint public.

### 13.2. Runtime identity bổ sung

Build identity cho biết ứng dụng được build từ đâu. Runtime identity cho biết process đang chạy trên nền tảng nào.

Có thể ghi thêm:

- java.vendor.
- java.runtime.version.
- java.vm.name.
- java.vm.version.
- os.name.
- os.version.
- os.arch.
- Container image digest được inject từ deployment metadata.
- Checkpoint ID được inject hoặc mount từ restore controller.

Build identity và runtime identity nên được hiển thị riêng để phát hiện trường hợp JAR đúng nhưng JDK hoặc checkpoint không đúng.

## 14. Truy vết checkpoint trong CI/CD

Một pipeline có thể chia thành các stage:

~~~mermaid
flowchart TD
    A["Checkout immutable Git commit"] --> B["Verify clean tree and submodules"]
    B --> C["Resolve locked dependencies"]
    C --> D["Build and test JAR"]
    D --> E["Generate SBOM and build provenance"]
    E --> F["Build OCI image with exact JDK"]
    F --> G["Sign image and publish digest"]
    G --> H["Run CRaC warm-up job"]
    H --> I["Create checkpoint"]
    I --> J["Generate checkpoint manifest"]
    J --> K["Hash and sign checkpoint"]
    K --> L["Restore validation"]
    L --> M{"Restore tests pass?"}
    M -->|No| N["Reject checkpoint artifact"]
    M -->|Yes| O["Promote checkpoint to release channel"]
~~~

### 14.1. Build stage

- Checkout commit bất biến.
- Xác nhận source tree sạch.
- Resolve dependency theo lockfile.
- Build và chạy test.
- Tính JAR digest.
- Sinh SBOM và build provenance.

### 14.2. Image stage

- Dùng JDK/base image đã pin theo digest.
- Cài native package với version cố định.
- Đóng gói JAR đã kiểm tra digest.
- Tạo OCI image.
- Lấy image digest sau push.
- Ký image và lưu SBOM image.

### 14.3. Checkpoint stage

- Chạy container đúng image digest.
- Ghi runtime identity.
- Chạy warm-up profile đã version hóa.
- Dừng hoặc tái lập resource theo CRaC lifecycle.
- Tạo checkpoint.
- Tính digest các file.
- Sinh manifest.
- Ký manifest/attestation.

### 14.4. Restore validation stage

- Chọn node pool tương thích.
- Xác minh image/JDK/manifest.
- Restore checkpoint.
- Chạy smoke test.
- Xác nhận dependency và readiness.
- Ghi restore duration, time to ready và first response.
- Chỉ promote artifact khi các điều kiện release đạt yêu cầu.

## 15. Promotion giữa các môi trường

Không nên copy một checkpoint qua môi trường chỉ dựa trên tên release. Mỗi môi trường cần kiểm tra các điều kiện restore.

Một flow promotion có thể:

| Môi trường | Hoạt động | Điều kiện đi tiếp |
|---|---|---|
| Build | Tạo JAR và image | Test, SBOM, provenance và signature thành công |
| Checkpoint factory | Warm-up và tạo ảnh | Manifest hoàn chỉnh, digest hợp lệ |
| Validation pool | Restore thử | Smoke test và compatibility pass |
| Staging | Restore trong workload gần production | Readiness và performance đạt mục tiêu |
| Production canary | Restore một nhóm nhỏ | Error rate và dependency load ổn định |
| Production rollout | Mở rộng theo batch | Không vượt ngưỡng vận hành |

### 15.1. Không promote checkpoint chưa restore thử

Việc tạo checkpoint thành công không chứng minh restore sẽ thành công trên node pool mục tiêu. Cần ít nhất một lần restore validation trong môi trường tương thích và lưu kết quả cùng checkpoint ID.

### 15.2. Mỗi môi trường có thể cần checkpoint profile riêng

Nếu staging và production dùng CPU baseline, kernel hoặc native runtime khác nhau, có thể cần checkpoint riêng cho từng nhóm tương thích. Không nên đổi metadata để làm một checkpoint có vẻ phù hợp với môi trường khác.

### 15.3. Lưu kết quả validation

Kết quả validation nên chứa:

- Checkpoint ID và digest.
- Node pool profile.
- JDK và CRIU version.
- Restore result.
- Application smoke test result.
- Dependency readiness.
- Time to ready.
- First-request latency.
- Test run ID và thời điểm.
- Người hoặc pipeline đã phê duyệt.

## 16. Truy vết trong Kubernetes runtime

Khi Pod chạy, cần biết chính xác nó đang dùng release và checkpoint nào. Có thể đưa metadata không nhạy cảm vào Pod labels, annotations và environment variables.

Ví dụ:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  labels:
    app: orders-api
    release-id: orders-api-2026-11-13-2
spec:
  replicas: 4
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
        release-id: orders-api-2026-11-13-2
      annotations:
        release.source-commit: "a1b2c3d4e5f6"
        release.image-digest: "sha256:..."
        release.checkpoint-id: "orders-api-2026.11.13.2-x86-poola-warm4-001"
        release.jdk-build: "exact-jdk-build"
        release.warmup-profile: "warmup-v4"
    spec:
      containers:
        - name: app
          image: registry.example.com/orders-api@sha256:<image-digest>
          env:
            - name: RELEASE_ID
              value: "orders-api-2026.11.13.2"
            - name: SOURCE_COMMIT
              value: "a1b2c3d4e5f6"
            - name: CHECKPOINT_ID
              value: "orders-api-2026.11.13.2-x86-poola-warm4-001"
~~~

Giá trị trong ví dụ là placeholder. Kubernetes label có giới hạn định dạng và độ dài; các digest hoặc metadata dài phù hợp hơn với annotation hoặc external release record.

### 16.1. Gắn Pod UID và restore attempt

Một checkpoint có thể được restore bởi nhiều Pod. Do đó, log cần phân biệt:

- Release ID: bản phát hành.
- Checkpoint ID: artifact được restore.
- Pod UID: instance cụ thể.
- Restore attempt ID: lần restore của instance.
- Node name/pool: môi trường restore.

Không dùng checkpoint ID làm định danh duy nhất của instance vì nhiều Pod có thể dùng chung một checkpoint.

### 16.2. Log structured

Một log event có thể có dạng:

~~~json
{
  "event": "application_ready",
  "releaseId": "orders-api-2026.11.13.2",
  "sourceCommit": "a1b2c3d4e5f6",
  "imageDigest": "sha256:...",
  "jdkBuild": "exact-jdk-build",
  "checkpointId": "orders-api-2026.11.13.2-x86-poola-warm4-001",
  "restoreAttemptId": "restore-02",
  "podUid": "pod-uid",
  "nodePool": "crac-linux-x86-pool-a"
}
~~~

Các trường giúp truy vấn log theo release hoặc checkpoint khi điều tra sự cố. Không đưa secret, token hoặc credential vào log.

## 17. Đối chiếu runtime với manifest trước khi phục vụ

Khi restore, ứng dụng hoặc startup coordinator có thể kiểm tra một tập điều kiện bắt buộc:

- Release ID khớp với manifest.
- Application image digest khớp.
- JDK build nằm trong danh sách được phép.
- CPU architecture phù hợp.
- Node pool profile được chấp nhận.
- Checkpoint digest đã được xác minh.
- Các resource cần tái lập đã được tạo.
- Warm-up profile đúng với release.

Một số kiểm tra nên do deployment controller thực hiện trước khi process restore; một số khác có thể thực hiện trong startup hoặc afterRestore. Không nên đợi đến khi request thật thất bại mới phát hiện image hoặc checkpoint sai.

### 17.1. Compatibility policy

Có thể mô tả policy bằng file version hóa:

~~~yaml
compatibilityPolicy:
  application: "orders-api"
  releaseId: "orders-api-2026.11.13.2"
  checkpointId: "orders-api-2026.11.13.2-x86-poola-warm4-001"
  required:
    imageDigest: "sha256:..."
    jdkBuild: "exact-jdk-build"
    architecture: "x86_64"
    nodePoolProfile:
      - "crac-linux-x86-pool-a"
    criuVersionRange: "validated-range"
  resourceChecks:
    database: required
    redis: required
    messageBroker: optional
~~~

Đây là policy minh họa. Phạm vi version của CRIU hoặc kernel chỉ nên cho phép khi đã có bằng chứng kiểm thử. Tránh dùng range quá rộng mà không có compatibility matrix.

### 17.2. Fail closed với sai khác bắt buộc

Nếu checkpoint digest không khớp hoặc JDK/architecture nằm ngoài policy, không nên tiếp tục restore như thể không có vấn đề. Hãy từ chối artifact hoặc chuyển sang cold start theo một fallback được thiết kế và kiểm thử trước.

Fallback cold start có thể hữu ích khi checkpoint không phù hợp nhưng application image vẫn hợp lệ. Tuy nhiên, phải ghi nhận startup mode để metric và log không trộn lẫn cold start với restore.

## 18. Quản lý nhiều checkpoint và rollback

Một release có thể tạo nhiều checkpoint. Cần một registry hoặc catalog lưu metadata để chọn đúng ảnh.

Thông tin catalog nên gồm:

- Release ID.
- Source commit.
- Application image digest.
- JDK build.
- Checkpoint ID.
- Checkpoint digest.
- Warm-up profile.
- Platform compatibility profile.
- Validation status.
- Created time.
- Signature/attestation reference.
- Retention state.

### 18.1. Không ghi đè checkpoint đã phát hành

Checkpoint đã được promote nên là immutable. Nếu tạo lại checkpoint, cấp ID mới. Không ghi đè file cũ dưới cùng tên vì các Pod hoặc rollback workflow có thể đang tham chiếu artifact đó.

### 18.2. Rollback phải chọn đúng cặp image và checkpoint

Nếu rollback về release trước, cần rollback cả:

- Application image.
- JDK/base image.
- Checkpoint được tạo từ image/JDK tương ứng.
- Runtime configuration profile.
- Warm-up profile.
- Compatibility policy.

Không dùng checkpoint của release mới với image cũ chỉ vì hai bản dùng cùng tên ứng dụng.

### 18.3. Retention và garbage collection

Checkpoint thường có kích thước lớn. Có thể đặt retention theo release và trạng thái promotion:

- Giữ checkpoint production hiện tại.
- Giữ một số release trước đã được kiểm chứng.
- Giữ checkpoint đang được Pod tham chiếu.
- Xóa artifact hết hạn sau khi không còn deployment hoặc rollback policy tham chiếu.

Trước khi xóa, kiểm tra catalog và deployment reference. Không xóa checkpoint chỉ dựa vào tuổi file.

## 19. Bảo mật chuỗi cung ứng và checkpoint

Checkpoint có thể chứa heap, object và trạng thái runtime. Nếu ứng dụng giữ token, credential, session hoặc dữ liệu người dùng trong memory, checkpoint có thể chứa những thông tin đó.

Cần bảo vệ:

- Checkpoint files.
- Checkpoint manifest.
- SBOM và provenance.
- Signing key hoặc signing identity.
- CI logs và build artifacts.
- Registry/storage access.
- Restore node và temporary extraction directory.

### 19.1. Quyền truy cập tối thiểu

Chỉ pipeline và workload được phép mới nên đọc checkpoint. Người dùng không cần truy cập trực tiếp vào memory image để vận hành ứng dụng.

### 19.2. Mã hóa khi lưu trữ và truyền tải

Dùng storage và transport có mã hóa, quản lý key theo chính sách tổ chức. Khi restore, đảm bảo artifact được xác minh trước khi đưa vào runtime.

### 19.3. Không để secret trong build provenance

Provenance có thể được lưu lâu và chia sẻ với nhiều hệ thống. Chỉ ghi tên biến, secret reference hoặc version ID. Không ghi giá trị secret, token hay private key.

### 19.4. Chữ ký không thay thế kiểm soát quyền

Một checkpoint có chữ ký hợp lệ vẫn có thể chứa dữ liệu nhạy cảm. Chữ ký xác nhận tính toàn vẹn và nguồn phát hành theo trust policy; nó không tự cấp quyền đọc hoặc giải mã artifact.

## 20. Điều tra sự cố bằng release lineage

Khi một Pod restore lỗi, hãy bắt đầu từ Pod UID và checkpoint ID rồi lần ngược qua catalog.

Một trình tự điều tra:

1. Xác định Pod UID, node và restore attempt.
2. Lấy release ID và checkpoint ID từ log/annotation.
3. Đọc checkpoint manifest.
4. Xác minh checkpoint digest và chữ ký.
5. Đối chiếu image digest với Pod spec.
6. Đối chiếu JDK build và JVM flags.
7. Kiểm tra node pool, kernel, CRIU và CPU baseline.
8. Kiểm tra warm-up profile và runtime configuration.
9. Đọc restore log và CRIU log.
10. So sánh với checkpoint validation record.
11. Xác định sai khác đầu tiên trong lineage.

Nếu checkpoint digest hợp lệ, image và JDK khớp, nhưng restore thất bại chỉ trên một node pool, cần tập trung vào kernel/CRIU/CPU/runtime difference. Nếu mọi node đều thất bại sau một source release mới, kiểm tra build và application resource lifecycle.

### 20.1. Phân biệt lỗi artifact và lỗi môi trường

| Triệu chứng | Mắt xích cần kiểm tra đầu tiên |
|---|---|
| Checksum không khớp | Storage, transfer hoặc artifact mutation |
| Signature không hợp lệ | Signing identity, manifest hoặc trust policy |
| Sai source commit | CI checkout và release metadata |
| JAR digest không khớp | Build output hoặc packaging |
| JDK build không đúng | Base image digest và runtime selection |
| Native library thiếu symbol | Image package/ABI |
| Restore chỉ lỗi trên một pool | Kernel, CRIU, CPU, namespace |
| Restore thành công nhưng readiness lỗi | Resource reinitialization và dependency |
| Request đầu tiên chậm | Warm-up profile, cache và JIT |
| Rollback dùng nhầm checkpoint | Catalog mapping và deployment reference |

## 21. Ví dụ truy vấn release identity trong ứng dụng

Một endpoint nội bộ có thể trả về metadata không nhạy cảm:

~~~json
{
  "application": "orders-api",
  "releaseId": "orders-api-2026.11.13.2",
  "sourceCommit": "a1b2c3d4e5f6",
  "buildId": "ci-84721-attempt-1",
  "jdkVendor": "Example Vendor",
  "javaRuntimeVersion": "exact-version",
  "checkpointId": "orders-api-2026.11.13.2-x86-poola-warm4-001",
  "warmupProfile": "warmup-v4",
  "startupMode": "crac-restore"
}
~~~

Endpoint này hữu ích cho support và deployment verification. Có thể bảo vệ bằng internal network hoặc authentication nếu metadata không nên public. Không trả JVM command line hoặc environment dump vì có thể chứa secret.

### 21.1. Ghi nhận startup mode

Một ứng dụng có thể chạy theo hai đường:

- cold-start
- crac-restore

Ghi startup mode giúp phân nhóm metric. Nếu một Pod fallback sang cold start do checkpoint không phù hợp, hệ thống quan sát phải thể hiện điều đó thay vì ghi nhận như restore thành công.

## 22. Checklist truy vết từ source tới checkpoint

### Source và build

- [ ] Repository identity và commit SHA được ghi lại.
- [ ] Source tree sạch hoặc patch được ghi rõ.
- [ ] Submodule/LFS identity được ghi lại nếu có.
- [ ] Build tool, build JDK và builder image digest được ghi lại.
- [ ] Dependency lock và verification metadata được lưu.
- [ ] JAR digest được tính sau build.
- [ ] Test result gắn với build ID.

### Image và runtime

- [ ] OCI image được tham chiếu bằng digest.
- [ ] Base image và JDK distribution/build được ghi lại.
- [ ] JVM flags và GC/compiler configuration được lưu.
- [ ] libc, OpenSSL và native dependency được kiểm kê.
- [ ] SBOM application và image được tạo.
- [ ] Build provenance được phát hành và xác minh.

### Warm-up và checkpoint

- [ ] Warm-up profile có ID/version.
- [ ] Scenario và dataset version được ghi lại.
- [ ] Checkpoint có ID riêng.
- [ ] Manifest liên kết checkpoint với source, image và JDK.
- [ ] Mọi file checkpoint đều có digest.
- [ ] Manifest hoặc checkpoint attestation được ký.
- [ ] Checkpoint artifact được lưu immutable và có access control.

### Restore và promotion

- [ ] Node pool/kernel/CRIU/CPU profile được ghi lại.
- [ ] Restore environment được đối chiếu với manifest.
- [ ] Signature và digest được xác minh trước restore.
- [ ] Restore validation và smoke test đã chạy.
- [ ] Kết quả validation gắn với checkpoint ID.
- [ ] Deployment lưu release ID, image digest và checkpoint ID.
- [ ] Rollback chọn đúng image/checkpoint pair.

### Bảo mật và vận hành

- [ ] Checkpoint được bảo vệ như artifact có thể chứa secret trong memory.
- [ ] Manifest không chứa credential.
- [ ] Signing identity được quản lý an toàn.
- [ ] Log có Pod UID và restore attempt ID.
- [ ] Startup mode được ghi nhận.
- [ ] Retention không xóa checkpoint còn được tham chiếu.

## 23. Câu hỏi thường gặp

### Chỉ lưu Git commit SHA có đủ truy vết checkpoint không?

Không. Commit SHA xác định source nhưng không xác định build toolchain, dependency, JDK, image, native library, warm-up profile hoặc môi trường tạo ảnh. Cần liên kết tất cả các thành phần đó trong provenance và checkpoint manifest.

### Vì sao phải lưu JDK build nếu đã lưu Java major version?

Cùng major version có thể có vendor, build, CRaC patch và native runtime khác nhau. Checkpoint phụ thuộc runtime cụ thể hơn bytecode Java thông thường. Hãy lưu vendor, full version/build và image digest.

### Checkpoint có thể dùng cho mọi image của cùng một release không?

Không nên giả định. Image có thể khác JDK, native package, filesystem hoặc runtime configuration. Chỉ dùng checkpoint với image/runtime đã được xác nhận tương thích trong manifest và restore validation.

### Có cần SBOM cho checkpoint không?

SBOM thường mô tả phần mềm trong application artifact và container image. Checkpoint cần thêm manifest mô tả runtime state và platform. Hãy liên kết SBOM/provenance của image vào checkpoint manifest.

### Hai checkpoint từ cùng commit có phải giống nhau không?

Không nhất thiết. Warm-up timing, heap layout, JIT state, cache content và host state có thể khác. Cần truy vết từng checkpoint bằng ID và digest riêng; không mặc định checkpoint reproducible byte-for-byte.

### Có thể chỉ lưu image tag thay vì digest không?

Không nên. Tag có thể được cập nhật để trỏ sang image khác. Digest xác định nội dung image cụ thể và phù hợp để đối chiếu khi restore.

### Làm sao biết Pod đang dùng checkpoint nào?

Gắn checkpoint ID, release ID và image digest vào Pod annotation hoặc environment metadata, rồi ghi các giá trị đó trong log structured. Kết hợp Pod UID và restore attempt ID để phân biệt các instance dùng chung một checkpoint.

### Khi nâng cấp JDK có phải tạo checkpoint mới không?

Nên tạo và kiểm thử checkpoint mới bằng JDK build mới. Không nên gắn checkpoint cũ với runtime mới nếu chưa có bằng chứng tương thích từ tài liệu và restore validation.

### Có cần ký cả checkpoint không?

Cần một cơ chế xác minh tính toàn vẹn và nguồn phát hành. Có thể ký manifest hoặc attestation chứa digest của toàn bộ checkpoint files. Khi restore, xác minh chữ ký và tính lại digest trước khi sử dụng.

### Có nên lưu secret trong checkpoint manifest để dễ truy vết không?

Không. Chỉ lưu secret reference hoặc version ID. Checkpoint và manifest cần được bảo vệ vì checkpoint có thể chứa secret trong heap, còn manifest nên tránh lưu giá trị credential.

### Nếu checkpoint không phù hợp với node thì có thể fallback cold start không?

Có thể, nếu deployment được thiết kế và kiểm thử cho fallback đó. Hãy ghi rõ startup mode, lý do từ chối checkpoint và metric riêng. Không được ghi nhận cold start như một lần CRaC restore thành công.

## Kết luận

Truy vết bản phát hành CRaC cần đi xuyên suốt từ source commit đến build toolchain, JAR, OCI image, JDK/CRaC build, native dependency, warm-up profile và checkpoint artifact. Mỗi tầng cần định danh bất biến, digest và provenance để có thể xác minh mối liên hệ giữa các thành phần.

Hãy tạo checkpoint manifest tự động, ký hoặc attestation manifest cùng digest của toàn bộ ảnh, lưu SBOM và build provenance, ghi release/checkpoint identity vào Pod và log, rồi xác minh môi trường restore trước khi mở readiness. Khi có lineage đầy đủ, nhóm phát triển có thể xác định chính xác checkpoint được tạo từ đâu, chạy trên runtime nào, đã được kiểm thử ở môi trường nào và cần chọn artifact nào khi triển khai hoặc rollback.
