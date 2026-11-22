# Chọn chiến lược CI cho Java toolchain

Continuous Integration (CI) tự động lấy thay đổi từ source control, dựng môi trường build có kiểm soát, compile, test, kiểm tra chất lượng và tạo artifact để nhóm nhận phản hồi sớm. Chiến lược CI xác định **khi nào chạy, chạy ở đâu, dùng JDK nào, kiểm tra những gì, lưu bằng chứng ra sao và ai được phép phát hành artifact**.

Một pipeline tốt phải phát hiện lỗi sớm, tái lập được kết quả giữa developer và CI, bao phủ đúng JDK/OS mà sản phẩm hỗ trợ, bảo vệ secrets và tạo artifact có thể truy vết. Chiến lược quá nhẹ sẽ bỏ sót lỗi tương thích; chiến lược quá rộng cho mọi commit sẽ làm feedback chậm, tốn runner và khiến developer tìm cách bỏ qua CI.

Bài này trình bày cách chọn nền tảng và thiết kế pipeline Java dùng Maven hoặc Gradle, từ pull request đến release. Ví dụ dùng GitHub Actions và Jenkins; nguyên tắc về build, test, artifact và bảo mật cũng áp dụng cho GitLab CI, Azure Pipelines, Buildkite hoặc hệ thống CI khác.

## 1. Chiến lược CI giải quyết những quyết định nào?

Trước khi viết YAML hoặc Jenkinsfile, nhóm cần thống nhất:

- **Trigger:** commit, pull request, merge queue, nightly hay tag release nào sẽ chạy pipeline?
- **Toolchain:** JDK vendor/version nào chạy build, compiler, test và packaging?
- **Runner:** dùng hosted, self-hosted, container hay agent chuyên dụng?
- **Quality gates:** compile, unit test, integration test, static analysis và security scan nào bắt buộc?
- **Matrix:** cần kiểm tra JDK, OS và architecture nào ở mỗi giai đoạn?
- **Caching:** dependency và build output nào có thể tái sử dụng an toàn?
- **Artifact:** file nào được giữ, ký, publish và promote?
- **Security:** job nào được đọc secrets, cấp token hoặc deploy?
- **Feedback:** lỗi được hiển thị ở đâu và trong bao lâu?
- **Ownership:** ai duy trì workflow, runner, plugin, JDK và policy?

CI là một phần của Java toolchain. Nếu project pin JDK nhưng CI tự động dùng version khác, hoặc build tool thay đổi giữa local và runner, quyết định toolchain chưa được thực thi đầy đủ.

## 2. Thu thập yêu cầu trước khi chọn nền tảng

| Nhóm yêu cầu | Câu hỏi cần trả lời |
|---|---|
| Repository | Source nằm trên GitHub, GitLab, Bitbucket hay máy chủ nội bộ? |
| Quy mô | Bao nhiêu repository, module, commit và build đồng thời? |
| Java support | Sản phẩm hỗ trợ những Java release nào? |
| Platform | Có cần Windows, Linux, macOS, x64, ARM64 hoặc native build không? |
| Network | Runner cần truy cập artifact repository, database, private network hay license server nào? |
| Security | Có yêu cầu isolated runner, audit log, secret manager, signing hoặc OIDC không? |
| Compliance | Cần lưu build log, test report, SBOM và provenance trong bao lâu? |
| Cost | Chi phí runner, storage, cache và bảo trì được tính thế nào? |
| Operations | Ai vá runner, nâng plugin, xử lý queue và khôi phục CI khi lỗi? |
| Developer experience | Developer có thể chạy cùng lệnh trên local và CI không? |

Ghi hard constraints trước khi chấm điểm. Nếu artifact phải được build trong mạng nội bộ, hosted runner không có quyền truy cập private repository có thể không đáp ứng. Nếu cần installer Windows và macOS, pipeline phải có runner trên các hệ điều hành đích.

## 3. Chọn mô hình CI phù hợp

| Mô hình | Phù hợp khi | Chi phí/rủi ro cần tính |
|---|---|---|
| Managed/hosted runners | Cần bắt đầu nhanh, build phổ thông và không cần mạng nội bộ | Giới hạn thời gian/compute, queue, network access, OS image thay đổi |
| Self-hosted runners | Cần private network, phần cứng riêng, license hoặc tool native đặc biệt | Nhóm phải vá, cô lập, giám sát, làm sạch và bảo vệ máy build |
| Hybrid | Build/test phổ thông chạy hosted; package hoặc integration nội bộ chạy self-hosted | Phải quản lý ranh giới trust, artifact transfer và quyền runner |

Hosted runner giảm công việc quản trị máy build. Kiểm tra cách nhà cung cấp quản lý image, OS version, dung lượng disk, CPU/RAM, thời gian tối đa và cache. Không giả định label như ubuntu-latest luôn trỏ tới cùng một image theo thời gian.

Self-hosted runner phù hợp khi build cần private network, hardware đặc biệt, license server, signing hardware hoặc dữ liệu không được phép rời khỏi môi trường kiểm soát. Runner phải được cô lập:

- Không chạy code pull request không tin cậy trên runner persistent có secrets hoặc quyền nội bộ.
- Ưu tiên runner ephemeral hoặc workspace mới và xóa sau mỗi job.
- Tách runner build thông thường khỏi runner ký/phát hành.
- Giới hạn network egress, quyền filesystem và service account.
- Cập nhật OS, JDK, agent và plugin theo lịch.
- Không dùng chung workspace hoặc Maven local repository giữa các build đồng thời nếu không có cách cô lập an toàn.

Mô hình hybrid thường hợp lý khi phần lớn công việc là compile/test phổ thông nhưng một số bước cần Windows, macOS, thiết bị, license hoặc private network. Chuyển đúng artifact đã tạo sang job đặc quyền; không build lại một source khác trong job phát hành.

## 4. Chọn nền tảng theo hệ sinh thái và năng lực vận hành

| Nền tảng | Điểm mạnh thường gặp | Cần đánh giá |
|---|---|---|
| GitHub Actions | Workflow nằm trong repository, tích hợp pull request, matrix và hosted runner | Quản lý action, token permissions, runner cost và chính sách bảo mật |
| Jenkins | Linh hoạt với agent, plugin, private infrastructure và hệ thống lâu năm | Nâng cấp controller, plugin, credentials, agent và pipeline libraries |
| GitLab CI | Pipeline gắn với repository, merge request, runner và registry | Runner topology, permissions, cache và tích hợp hệ sinh thái |
| Azure Pipelines | Tích hợp Azure DevOps, hosted/self-hosted agent và environment | Agent pool, service connection, permission và template governance |
| Buildkite/CI khác | Có thể tách orchestration khỏi hạ tầng runner theo nhu cầu | Chi phí vận hành, plugin/integration và khả năng truy vết |

Chọn nền tảng đã được tổ chức hỗ trợ nếu nó đáp ứng yêu cầu. Chi phí chuyển CI thường bao gồm migration pipeline, secrets, runner, artifact repository, approval, audit và đào tạo. Không chuyển nền tảng chỉ vì một ví dụ YAML trông ngắn hơn.

Đánh giá total cost of ownership: compute, storage, network, license, thời gian bảo trì, thời gian developer chờ build và chi phí xử lý sự cố.

## 5. Chuẩn hóa Java toolchain trước khi thiết kế pipeline

CI chỉ tái lập được khi project khai báo rõ toolchain. Phân biệt các version:

| Thành phần | Vai trò |
|---|---|
| Build JVM | JVM chạy Maven hoặc Gradle |
| Compiler toolchain | JDK cung cấp javac cho task compile |
| Release target | API và bytecode mà compiler phải tạo tương thích |
| Test runtime | JDK chạy unit/integration test |
| Production runtime | JDK/runtime mà sản phẩm hỗ trợ |
| Packaging JDK | JDK dùng cho jlink, jpackage hoặc native packaging |

Pin Maven/Gradle Wrapper trong repository. Ghi JDK vendor và version; với release build cần độ tái lập cao, pin distribution và image digest hoặc bản cài có checksum được xác minh.

Ví dụ project hỗ trợ Java 17 làm baseline và muốn kiểm tra tương thích trên JDK 25:

- Compiler release target: 17.
- CI runtime matrix: JDK 17 và JDK 25.
- Build tool: Maven Wrapper hoặc Gradle Wrapper đã pin.
- Dependencies và plugins: version cụ thể, tránh version động trong release.
- Packaging: chạy trên OS/architecture mà artifact thực sự hỗ trợ.

JDK mới hơn dùng để chạy build không tự động nâng release target. Ngược lại, release target 17 không chứng minh tất cả dependency đều chạy được trên Java 17; phải kiểm tra runtime thực tế.

## 6. Chia pipeline thành các lane theo tốc độ và rủi ro

Không cần chạy toàn bộ test matrix, performance test và release scan cho mỗi lần lưu file. Chia công việc thành các lane:

| Lane | Trigger | Nội dung | Mục tiêu |
|---|---|---|---|
| Local feedback | Developer trước khi push | Wrapper, compile, unit test, formatter | Tìm lỗi nhanh ngay trên máy |
| Pull request | Mỗi PR/update commit | Compile, unit test, lint, test quan trọng, dependency policy | Quyết định có thể merge hay chưa |
| Main/integration | Push hoặc merge vào main | Full unit/integration, package, smoke test, quality/security gates | Xác nhận trạng thái tích hợp |
| Nightly/scheduled | Theo lịch | JDK/OS matrix rộng, compatibility, performance, full scan | Tìm lỗi ít gặp và regression dài hạn |
| Release | Tag hoặc release approval | Build artifact, sign, SBOM, provenance, publish và deploy | Phát hành artifact đã xác minh |

Một PR lane tốt nên nhanh và ổn định. Mục tiêu 5–10 phút có thể hữu ích cho một số project, nhưng ngưỡng thực tế phải dựa trên thời gian build và quy mô test. Không bỏ test quan trọng chỉ để đạt thời gian mục tiêu; tách test chậm sang integration/nightly lane và xác định điều kiện release phải chờ kết quả nào.

## 7. Thiết kế trigger và branch policy

Các trigger thường dùng:

- Pull request: chạy required checks trước merge.
- Push vào main: xác nhận trạng thái sau merge và tạo candidate artifact.
- Merge queue: chạy kiểm tra trên tổ hợp commit sẽ được merge.
- Nightly: chạy matrix rộng, full integration và scan định kỳ.
- Tag/release: tạo artifact bất biến, ký và publish.
- Manual dispatch: chạy lại workflow hoặc profile có kiểm soát để điều tra.

Nếu dùng trunk-based development, giữ main luôn build được và yêu cầu CI xanh trước khi merge. Branch protection nên yêu cầu đúng những status checks quan trọng; không tạo quá nhiều check trùng lặp.

Path filter có thể giảm build không liên quan trong monorepo, nhưng nếu required check bị bỏ qua do filter, branch policy có thể chờ check không bao giờ được tạo. Dùng một check tổng hợp luôn chạy nếu repository yêu cầu status cố định.

Với PR validation, có thể hủy run cũ khi commit mới thay thế. Với deploy hoặc release cần thứ tự, xếp hàng hoặc giới hạn một lần chạy; không hủy một release đang phát hành chỉ vì có tag mới.

## 8. Chọn test matrix có chủ đích

Matrix có thể gồm Java version, OS, architecture, database, profile hoặc build mode. Nếu nhân mọi trục với nhau, số job tăng rất nhanh. Ví dụ 3 JDK × 3 OS × 2 architecture × 2 database tạo 36 tổ hợp.

### Matrix tối thiểu cho PR

- Compile bằng JDK/toolchain chuẩn.
- Chạy unit test trên Java baseline.
- Chạy integration test thiết yếu trên môi trường mặc định.
- Chạy lint/static checks và dependency policy.
- Chỉ thêm OS khác nếu code hoặc packaging có khác biệt liên quan.

### Matrix rộng cho main/nightly

- Runtime thấp nhất được hỗ trợ.
- Runtime mới nhất được hỗ trợ.
- OS/architecture đích.
- Database hoặc service version quan trọng.
- Native library và packaging test trên platform tương ứng.

### Phân biệt compile matrix và runtime matrix

Nếu project compile bằng JDK 17 với release 17, test runtime trên JDK 17 và 25 giúp kiểm tra tương thích. Nếu muốn kiểm tra compiler mới hơn, thêm job compile riêng bằng JDK 25 với cùng release target.

Không nhầm một job chạy trên JDK 25 với việc compiler toolchain chắc chắn dùng JDK 25 nếu Gradle/Maven đã chọn toolchain riêng.

Với compatibility matrix, đặt fail-fast false nếu muốn thấy tất cả JDK/OS legs thất bại trong cùng lượt. Đánh dấu job experimental khi không thuộc baseline được hỗ trợ. Giới hạn max-parallel để cân bằng queue, chi phí và tải lên artifact repository.

## 9. Chọn runner và môi trường build

Runner cần có đúng OS/architecture, JDK distribution/version, Wrapper và shell, native compiler/library nếu có JNI hoặc packaging, CA certificates/locale/timezone/fonts nếu ứng dụng cần, network route tới dependency repository và disk đủ cho cache/test/package.

Đối với Java service thuần, Linux hosted runner thường đủ cho compile và test. Nếu sản phẩm phát hành Windows installer hoặc macOS package, chạy jpackage trên runner OS đích. Native package phụ thuộc SDK và toolchain của platform; không giả định một Linux job có thể tạo đúng installer cho mọi OS.

Dùng container build image khi muốn pin OS/JDK/build utilities. Ghi image digest thay vì chỉ tag mutable. Cập nhật image có kế hoạch để nhận security patch; pin digest không có nghĩa giữ image cũ vô thời hạn.

## 10. Thiết kế các stage và quality gates

Một pipeline Java phổ biến có thể gồm:

1. Checkout đúng commit.
2. Kiểm tra JDK, Wrapper và build metadata.
3. Resolve dependencies.
4. Compile và kiểm tra warning.
5. Unit test.
6. Static analysis, formatting và policy.
7. Integration/contract test.
8. Package JAR/WAR hoặc application image.
9. Kiểm tra dependency, license, vulnerability và secret.
10. Smoke test artifact đã đóng gói.
11. Sinh checksum, SBOM và provenance.
12. Archive/publish artifact.
13. Deploy qua environment được bảo vệ nếu release.

| Gate | Khi nào cần | Điều kiện pass |
|---|---|---|
| Compile | Mọi PR | Không có compile error |
| Unit tests | Mọi PR | Test bắt buộc pass |
| Formatting/lint | Mọi PR | Quy tắc code được đáp ứng |
| Integration tests | PR thiết yếu hoặc main | Dependency service và contract pass |
| Dependency/SCA scan | PR và release | Không có finding vượt policy |
| Secret scan | PR/push | Không phát hiện secret bị commit |
| License policy | PR/release | Dependency phù hợp policy |
| SBOM | Artifact release | Đủ inventory và version |
| Smoke test | Artifact/package | Artifact chạy được trên runtime mục tiêu |
| Signature/provenance | Release | Nguồn, digest và chữ ký hợp lệ |

Định nghĩa severity, exception, owner và thời hạn xử lý. Một scan không có policy rõ ràng chỉ tạo thêm báo cáo mà không giúp quyết định merge/release.

## 11. Maven và Gradle trong CI

### Maven

Dùng Maven Wrapper:

~~~bash
./mvnw --batch-mode --no-transfer-progress verify
~~~

Windows:

~~~powershell
.\mvnw.cmd --batch-mode --no-transfer-progress verify
~~~

Pin Maven distribution trong Wrapper properties. Ghi JDK chạy Maven và nếu dùng Maven Toolchains, ghi JDK compiler mà plugin thực sự chọn. Với release target, cấu hình maven.compiler.release và pin version compiler plugin đã được kiểm thử.

Trong CI verification thông thường, verify thường là điểm kết thúc phù hợp. Chỉ dùng deploy trong job phát hành có quyền publish và điều kiện bảo vệ riêng.

### Gradle

Dùng Gradle Wrapper:

~~~bash
./gradlew --no-daemon clean check
~~~

Windows:

~~~powershell
.\gradlew.bat --no-daemon clean check
~~~

check thường bao gồm các verification task được project cấu hình. Không giả định mọi project đều có cùng task graph; kiểm tra build logic.

Gradle có hai cache khác nhau:

- Build Cache lưu output của task để tái sử dụng khi input tương ứng không đổi.
- Configuration Cache lưu kết quả configuration/task graph để giảm công việc cấu hình ở lần chạy sau.

Chúng giải quyết hai phần khác nhau của build và có thể phối hợp. Bật cache sau khi xác nhận task/plugin tương thích và output được khai báo đúng. Cache không thay thế kiểm thử hoặc artifact verification.

## 12. Caching mà không làm mất tính đúng đắn

Cache giúp giảm thời gian tải dependency, JDK và build output. Cache là tối ưu hiệu năng, không phải nguồn sự thật cho release artifact.

Maven thường cache local repository, Wrapper distribution và các file cấu hình dùng làm cache key. Key nên thay đổi khi POM, Wrapper properties, extension hoặc dependency inputs thay đổi. Không dùng chung một Maven local repository đang được nhiều build đồng thời ghi nếu không có cách cô lập an toàn.

Gradle có dependency cache, Wrapper cache, Build Cache và Configuration Cache. Mỗi loại có nội dung và invalidation riêng. Remote Build Cache nên có access control và policy cho phép chỉ trusted CI ghi cache nếu output có thể ảnh hưởng build khác.

Quy tắc cache:

- Bao gồm OS/architecture và Wrapper/build configuration.
- Bao gồm lockfile, version catalog hoặc dependency declaration.
- Không cache secrets, signing key, credential file hay workspace nhạy cảm.
- Cẩn trọng với cache được tạo từ untrusted pull request.
- Dùng read-only cache cho PR/matrix fan-out khi phù hợp.
- Xóa cache theo policy khi nghi ngờ poisoned hoặc dữ liệu không tương thích.

Cache hit không chứng minh build tái lập. Cần có clean build định kỳ hoặc release build không phụ thuộc vào output cache không đáng tin.

## 13. Bảo mật workflow và runner

CI có thể truy cập source, token, artifact repository, signing credential và môi trường deploy. Workflow là một phần của supply chain.

Chỉ cấp permission mà job thực sự cần. Job compile/test thường chỉ cần đọc source. Job publish mới cần quyền ghi package hoặc phát hành. Không cấp write permission toàn workflow chỉ vì một bước release cần quyền đó.

Với GitHub Actions, pin action bằng full-length commit SHA hoặc dùng workflow dependency lockfile nếu tổ chức áp dụng. Tag giúp dễ đọc nhưng có thể thay đổi theo thời gian. Review source của action và cập nhật SHA qua pull request có kiểm soát.

Bảo vệ secrets:

- Không đưa secret vào file YAML, source, command line log hoặc artifact.
- Không cung cấp signing/deploy secret cho job xử lý code PR không tin cậy.
- Giới hạn secret theo environment/job và thời gian sử dụng.
- Mask dữ liệu nhạy cảm, nhưng không dựa vào redaction như biện pháp duy nhất.
- Rotate credential nếu bị lộ trong log hoặc artifact.
- Tách signing key khỏi runner build thông thường.

Nếu cloud provider hỗ trợ workload identity federation, OIDC có thể cấp token ngắn hạn theo identity/claim của workflow. Chỉ job cần lấy token mới được cấp id-token: write; quyền này cho phép yêu cầu token, không tự cấp quyền truy cập tài nguyên cloud. Cloud IAM vẫn phải kiểm tra subject, repository, branch, environment và audience.

Không chạy pull request từ fork hoặc source không tin cậy trên self-hosted runner có quyền truy cập nội bộ. Dùng runner ephemeral, phân nhóm runner, hạn chế network và xóa workspace sau job.

## 14. Tạo artifact có thể truy vết và promote

Một pipeline release đáng tin nên tạo artifact một lần rồi promote chính artifact đó qua môi trường. Không build lại source ở staging và production rồi giả định output giống nhau.

Lưu cùng artifact commit SHA và repository, build run ID/timestamp/workflow version, JDK vendor/version/build image digest/Wrapper version, dependency/plugin versions, test report/scan result/SBOM, SHA-256 digest/signature, provenance/attestation nếu hỗ trợ và target OS/architecture/runtime requirement.

Phân biệt build artifact, container image, installer và deployed artifact. Mỗi loại cần digest riêng. Tag như latest hoặc release name là nhãn dễ đọc; digest mới xác định chính xác nội dung.

Artifact repository nên có retention, immutability, access control và cleanup policy. Không dùng thư mục workspace của runner làm kho phát hành lâu dài.

## 15. Tách build, verify, sign và deploy

| Job | Input | Quyền cần có |
|---|---|---|
| Build | Source và dependency | Đọc repository, tải dependency |
| Verify | Artifact build | Đọc artifact, chạy test/scan |
| Sign | Artifact đã xác minh | Truy cập signing service/key theo policy |
| Publish | Artifact đã ký và metadata | Ghi artifact repository/package registry |
| Deploy | Digest đã publish | Quyền deploy đúng environment |

Tách job giúp giới hạn secrets và quyền ghi. Job sau phải nhận đúng artifact từ job trước và xác minh digest; không tự checkout lại branch mới rồi build một bản khác.

Release/deploy cần protected environment, reviewer/approval hoặc policy tương ứng với mức rủi ro. Không để pull request tự kích hoạt deploy production.

## 16. GitHub Actions example: Maven, Java 17/25 matrix

Ví dụ dưới đây chạy verify cho pull request và push vào main. Project đặt compiler release target 17; matrix chạy Maven trên JDK 17 và 25 để kiểm tra tương thích. Maven Wrapper được commit trong repository.

Tệp pom.xml cần có cấu hình tương ứng, đồng thời pin compiler plugin và các plugin build theo phiên bản đã kiểm thử:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

Workflow .github/workflows/java-ci.yml:

~~~yaml
name: Java CI

on:
  pull_request:
  push:
    branches:
      - main

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  verify:
    name: Verify on Java ${{ matrix.java }}
    runs-on: ubuntu-latest

    strategy:
      fail-fast: false
      max-parallel: 4
      matrix:
        java: ['17', '25']

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up JDK
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
          cache: maven
          cache-read-only: ${{ github.event_name == 'pull_request' }}

      - name: Record toolchain
        run: |
          java --version
          ./mvnw --version

      - name: Verify
        run: ./mvnw --batch-mode --no-transfer-progress verify
~~~

Thay các placeholder trong ví dụ bằng GitHub Actions expressions:

~~~text
${{ github.workflow }} -> github.workflow expression
${{ github.ref }} -> github.ref expression
${{ matrix.java }} -> matrix.java expression
${{ github.event_name == 'pull_request' }} -> github.event_name == 'pull_request' expression
~~~

Cách đọc cấu hình:

- pull_request và push main chạy cùng quality gate.
- permissions chỉ cấp contents: read cho job verify.
- concurrency hủy CI run cũ của cùng ref khi có commit mới; không dùng cấu hình này cho release cần chạy tuần tự.
- fail-fast false giúp thấy kết quả của cả hai JDK legs.
- setup-java cài JDK, đặt JAVA_HOME/PATH và cache Maven dependencies/Wrapper.
- PR dùng cache read-only để không ghi dữ liệu cache từ source không tin cậy.
- Maven Wrapper đảm bảo Maven distribution theo cấu hình repository.
- release target 17 giữ API/bytecode baseline dù test job chạy trên JDK 25.

Ví dụ dùng action tag để dễ đọc. Với repository yêu cầu supply-chain hardening, pin mỗi action vào full-length commit SHA đã xác minh hoặc dùng workflow dependency lockfile theo policy. Không sao chép một SHA chưa được kiểm tra từ ví dụ.

Đây là PR/main verification workflow. Release job nên tách riêng, chỉ chạy trên tag/approval, nhận artifact đã xác minh và được cấp quyền ký/publish cần thiết.

## 17. Biến thể cho Gradle

Với Gradle, dùng Wrapper và cấu hình Java toolchain/release trong build file. Ví dụ build.gradle.kts:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Một job verify cơ bản có thể chạy:

~~~yaml
- name: Set up JDK
  uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '17'
    cache: gradle

- name: Verify
  run: ./gradlew --no-daemon clean check
~~~

Nếu Gradle daemon chạy trên JDK 25 nhưng JavaCompile toolchain yêu cầu 17, compiler task vẫn cần chọn đúng JDK 17 toolchain. Ghi rõ build JVM và compiler toolchain trong build report. Kiểm tra Gradle version hỗ trợ JVM chạy Gradle và plugin tương thích trước khi nâng JDK.

Khi muốn tăng tốc, bật Build Cache hoặc Configuration Cache theo khả năng tương thích của project. Không bật hàng loạt flag chỉ vì một build khác đã dùng; trước tiên chạy test và kiểm tra task/plugin có cấu hình đúng input/output.

## 18. Ví dụ Jenkins Pipeline cho Maven

Jenkins dùng Jenkinsfile để mô tả pipeline dưới dạng code. Agent label chọn node có JDK và môi trường phù hợp. Ví dụ tối giản:

~~~groovy
pipeline {
    agent {
        label 'linux && jdk17'
    }

    options {
        timestamps()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Toolchain') {
            steps {
                sh 'java --version'
                sh './mvnw --version'
            }
        }

        stage('Verify') {
            steps {
                sh './mvnw --batch-mode --no-transfer-progress verify'
            }
        }
    }

    post {
        always {
            junit testResults: '**/target/surefire-reports/*.xml, **/target/failsafe-reports/*.xml',
                  allowEmptyResults: true

            archiveArtifacts artifacts: '**/target/*.jar',
                             allowEmptyArchive: true,
                             fingerprint: true
        }
    }
}
~~~

Agent phải có JDK phù hợp, quyền truy cập dependency repository và đủ disk. Wrapper giúp pin Maven distribution, nhưng JDK trên agent vẫn phải được quản lý. Trong Jenkins, credentials nên lấy từ Credentials store và chỉ bind trong stage cần dùng; không ghi secret vào Jenkinsfile.

Plugin như Pipeline Maven Integration có thể cấu hình Maven/JDK, settings và artifact fingerprinting. Plugin cần được pin, cập nhật và quản lý như một phần của toolchain CI.

## 19. Test report, log và failure diagnosis

Một pipeline hữu ích phải cho biết lỗi nằm ở đâu, không chỉ trả về exit code khác 0.

Giữ lại Surefire/Failsafe hoặc Gradle test reports, compiler warnings/errors, static analysis và dependency scan reports, build scan/timing report nếu được phép, JDK/Maven/Gradle/OS version, commit SHA/run ID/artifact digest và log của service/test container khi integration test thất bại.

| Nhóm lỗi | Cách xử lý |
|---|---|
| Code/test regression | Sửa code hoặc test; không retry để che lỗi |
| Dependency repository/network | Kiểm tra status, timeout và mirror; retry có giới hạn khi lỗi tạm thời |
| Runner infrastructure | Đối chiếu runner health, disk, memory và image |
| Flaky test | Tái hiện, ghi owner và sửa nguyên nhân; retry chỉ để thu thập bằng chứng |
| Cache corruption | Thử clean build hoặc bỏ cache; điều tra key/trust boundary |
| Environment mismatch | So sánh JDK, locale, timezone, architecture và environment variables |
| Security policy failure | Xử lý finding hoặc exception có owner/thời hạn |

Không retry mọi test thất bại một cách tự động. Retry có thể làm một flaky test trông như pass và giảm độ tin cậy của required check. Nếu có retry, lưu kết quả lần đầu và đánh dấu test flaky.

## 20. Đo hiệu quả chiến lược CI

| Metric | Ý nghĩa |
|---|---|
| Queue time | Thời gian chờ runner |
| PR feedback time | Từ push đến required checks hoàn tất |
| Build duration | Thời gian từng stage/job |
| Success rate | Tỷ lệ run pass theo lane |
| Flaky test rate | Tỷ lệ test không ổn định |
| Cache hit rate | Cache có giúp giảm tải không |
| Failure classification | Lỗi code, infra, dependency hay environment |
| Artifact reproducibility | Cùng source/toolchain có tạo digest mong đợi không |
| Deployment failure rate | Tỷ lệ deploy lỗi sau release |
| Change lead time | Thời gian từ thay đổi đến khi được tích hợp/phát hành |

Đừng tối ưu chỉ số tổng thời gian pipeline bằng cách giảm test quan trọng. Phân tích thời gian theo stage: dependency download, configuration, compile, unit, integration, packaging, queue và artifact upload.

## 21. Các quyết định đặc biệt cho monorepo và multi-module

Với monorepo, không phải thay đổi ở module nào cũng cần build mọi module. Có thể dùng dependency graph hoặc path filter để chạy phần bị ảnh hưởng, nhưng phải xử lý đúng dependency bắc cầu.

Chiến lược nên có một lệnh root để chạy toàn bộ verification, quy tắc xác định module bị ảnh hưởng có thể kiểm tra, job integration cho các module liên kết, cache key bao gồm Wrapper/build logic/version catalog, nightly full build để phát hiện lỗi do path filter bỏ sót và release job xác minh toàn bộ dependency graph trước khi publish.

Không để path filter biến một thay đổi trong shared build logic thành PR không chạy kiểm tra. Các file như parent POM, settings.gradle, convention plugin, version catalog và workflow template thường ảnh hưởng nhiều module.

## 22. Chiến lược cho jlink, jpackage và native artifact

Nếu project tạo custom runtime hoặc installer, CI phải kiểm tra cả runtime image và application payload:

- Chạy jdeps để review module dependency.
- Dùng jlink tạo runtime từ JDK/toolchain đã pin.
- Chạy java --list-modules và --validate-modules trên image.
- Dùng jpackage trên OS đích.
- Kiểm thử launcher, resource, TLS, locale, native library và service binding.
- Lưu digest của runtime image, application image và installer.
- Kiểm tra signature/checksum trước khi publish.

Không tạo installer Windows/macOS bằng cách chỉ đổi tên file từ Linux. Dùng runner phù hợp với target OS và architecture. Tách native packaging matrix khỏi PR fast lane nếu thời gian và chi phí lớn; chạy smoke check nhanh trên PR và đầy đủ platform matrix trước release.

## 23. Những anti-pattern CI thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Dùng JDK mặc định của runner | Build thay đổi khi image cập nhật | Cài/pin JDK rõ ràng |
| Dùng system Maven/Gradle | Version khác nhau giữa local và CI | Dùng Wrapper |
| Chỉ test một JDK dù support nhiều version | Bỏ sót runtime incompatibility | Matrix theo baseline và runtime được hỗ trợ |
| Matrix mọi tổ hợp ở mỗi PR | Queue lâu và tốn compute | Chia fast lane và nightly/release matrix |
| Cache không có key rõ | Stale/poisoned cache hoặc kết quả khó lặp | Hash dependency inputs và tách trust boundary |
| Cache build output mà không khai báo task inputs | Có thể tái sử dụng output sai | Sửa task input/output và test cache |
| Mọi job đều có deploy secret | Tăng blast radius | Tách job và cấp quyền tối thiểu |
| Action/plugin dùng tag mutable mà không review | Supply-chain risk | Pin SHA/lockfile và audit source |
| Build lại ở từng môi trường | Artifact có thể khác nhau | Build once, promote same digest |
| Retry mọi test fail | Che flaky test và regression | Phân loại lỗi, retry có giới hạn |
| Dùng self-hosted runner persistent cho PR ngoài | Rủi ro lộ secrets/workspace | Runner ephemeral và trust isolation |
| Release workflow dùng concurrency cancel | Có thể hủy release đang chạy | Queue/serialize release job |
| Không lưu test report | Khó điều tra sau khi job kết thúc | Archive reports/logs có retention |
| Required check bị bỏ qua bởi path filter | Merge queue/branch protection bị kẹt hoặc thiếu gate | Dùng aggregate check và filter có kiểm soát |

## 24. Quy trình triển khai chiến lược CI từng bước

1. Ghi rõ Java release baseline, JDK vendor/version và OS/architecture support.
2. Chuẩn hóa Maven/Gradle Wrapper, compiler release và toolchain.
3. Chọn CI platform theo source control, runner, network, security và năng lực vận hành.
4. Xây một PR lane nhỏ: checkout, toolchain, compile, unit test và lint.
5. Thiết lập required checks và branch protection.
6. Thêm main integration lane với integration test, package và smoke test.
7. Thêm JDK/runtime matrix dựa trên support policy.
8. Thêm nightly scan, full platform matrix và performance test nếu có giá trị.
9. Thiết lập cache key, cache permissions và clean-build schedule.
10. Tách build, sign, publish và deploy theo trust boundary.
11. Lưu test reports, SBOM, checksum, provenance và artifact digest.
12. Đo queue time, feedback time, flaky rate và failure category.
13. Review workflow/plugin/runner/JDK định kỳ và sau mỗi thay đổi policy.
14. Tạo tài liệu runbook cho lỗi CI, cache, runner và release.

Bắt đầu với pipeline đơn giản nhưng đáng tin. Thêm matrix, cache, runner đặc biệt và release automation khi có yêu cầu được đo lường.

## 25. Checklist review CI strategy

- [ ] CI platform phù hợp repository và năng lực vận hành.
- [ ] Hosted/self-hosted/hybrid runner được chọn theo network, OS và trust boundary.
- [ ] JDK vendor/version, build JVM, compiler toolchain và release target được phân biệt.
- [ ] Maven/Gradle Wrapper được commit và pin.
- [ ] Pull request có compile, unit test và required quality gates.
- [ ] Main/integration chạy integration test và package.
- [ ] JDK/OS matrix bám theo support policy.
- [ ] Matrix không tạo tổ hợp thừa và có fail-fast policy rõ.
- [ ] Nightly/release chạy các kiểm tra rộng cần thiết.
- [ ] Cache key dựa trên dependency/build inputs và không chứa secrets.
- [ ] Cache từ source không tin cậy không được ghi vào trusted cache.
- [ ] Workflow permission theo least privilege.
- [ ] Action/plugin được review và pin theo policy.
- [ ] Secrets chỉ có trong job cần chúng.
- [ ] OIDC/short-lived credential được dùng khi nền tảng hỗ trợ và policy cho phép.
- [ ] Self-hosted runner được cô lập, vá và làm sạch.
- [ ] Artifact được tạo một lần, checksum và promote cùng digest.
- [ ] Test report, scan report và build metadata được lưu.
- [ ] Release job có approval/environment protection thích hợp.
- [ ] Có metric, owner và lịch review cho pipeline.

## 26. Ghi nhớ

- CI strategy quyết định trigger, toolchain, runner, test, cache, artifact, security và feedback.
- Chọn nền tảng dựa trên repository, network, compliance, runner và chi phí vận hành.
- Hosted runner giảm việc quản trị; self-hosted runner cần isolation, patching và cleanup.
- Dùng Wrapper và pin JDK/toolchain để giảm khác biệt giữa local và CI.
- Chia PR, main, nightly và release lane theo tốc độ và mức rủi ro.
- Matrix phải phản ánh support policy; tránh nhân mọi trục ở mọi commit.
- Build Cache và Configuration Cache của Gradle giải quyết hai loại công việc khác nhau.
- Cache là tối ưu hiệu năng; clean build và artifact verification vẫn cần thiết.
- Cấp quyền tối thiểu, pin action và bảo vệ secret.
- Tách build, verify, sign, publish và deploy theo trust boundary.
- Build once, promote cùng artifact digest qua các môi trường.
- Lưu report, checksum, SBOM, provenance và build metadata.
- Theo dõi queue time, feedback time, flaky rate và failure category để cải tiến.

## Tài liệu tham khảo chính thức

- [GitHub Actions: actions/setup-java](https://github.com/actions/setup-java)
- [GitHub Actions: Workflow syntax and matrix](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [GitHub Actions: Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)
- [GitHub Actions: OpenID Connect](https://docs.github.com/en/actions/reference/security/oidc)
- [GitHub Actions: Concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency)
- [Gradle: Best Practices for Performance](https://docs.gradle.org/current/userguide/best_practices_performance.html)
- [Gradle: Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle: Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Apache Maven: Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
- [Jenkins: Pipeline Syntax](https://www.jenkins.io/doc/book/pipeline/syntax/)
- [Jenkins: Pipeline Maven Integration](https://www.jenkins.io/doc/pipeline/steps/pipeline-maven/)
- [Jenkins: Archive Artifacts](https://www.jenkins.io/doc/pipeline/steps/core/)