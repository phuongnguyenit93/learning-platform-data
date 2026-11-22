# Chứng thực nguồn gốc build và liên kết artifact với đầu vào

Một file JAR được tạo ra sau khi chạy Gradle thường được chuyển qua nhiều bước: lưu trong CI, tải lên repository, đưa vào container image, triển khai lên môi trường thử nghiệm rồi phát hành production. Khi có sự cố bảo mật hoặc cần điều tra một phiên bản, chỉ biết tên file và version là chưa đủ. Nhóm cần trả lời được những câu hỏi như: artifact này được tạo từ commit nào, bằng workflow nào, dùng JDK và Gradle nào, dependency nào đã được resolve, builder nào thực hiện build, và file đang triển khai có đúng là file đã được kiểm tra hay không.

**Build provenance** là thông tin có cấu trúc mô tả nguồn gốc và quá trình tạo ra artifact. **Attestation** là một lời chứng thực có thể được xác minh, thường gắn với artifact bằng digest và được ký bởi một danh tính hoặc khóa tin cậy. Khi provenance được tạo và ký đúng cách, hệ thống phát hành có thể kiểm tra artifact có đến từ source, workflow, builder và đầu vào được cho phép hay không.

Bài học này giải thích cách liên kết artifact với đầu vào build, cách tạo và ký chứng thực, cách xác minh trong pipeline và những giới hạn cần hiểu khi sử dụng provenance.

## 1. Vì sao cần chứng thực nguồn gốc build?

Giả sử pipeline tạo ra:

~~~text
order-service-2.4.1.jar
~~~

Tên file cho biết project và version theo quy ước đặt tên. Nó không chứng minh:

- File được build từ commit đã review.
- Build chạy trong workflow chính thức của repository.
- Dependency đúng với lockfile đã được phê duyệt.
- JDK và Gradle đúng phiên bản mà tổ chức yêu cầu.
- Artifact không bị thay thế sau khi test.
- File được tải về từ repository là file CI đã tạo.
- Một người hoặc một workflow có quyền hợp lệ đã phát hành file.

Nếu một JAR bị thay thế trong lúc upload, cache hoặc copy sang hệ thống khác, tên file có thể vẫn giống hệt. Nếu một pipeline chạy từ branch không đáng tin nhưng có quyền publish, version artifact cũng không cho người nhận biết nguồn build.

Provenance tạo ra một bản ghi có thể kiểm chứng về mối liên hệ giữa artifact và quá trình đã tạo nó. Người nhận có thể kiểm tra digest của file, chữ ký của attestation, danh tính builder và các input được ghi trong statement.

~~~mermaid
flowchart TD
    A[Source commit and build inputs] --> B[Trusted CI builder]
    B --> C[Build and test]
    C --> D[Artifact]
    D --> E[Compute artifact digest]
    B --> F[Build provenance]
    E --> F
    F --> G[Sign attestation]
    G --> H[Publish artifact and attestation]
    H --> I[Verify before promotion or deployment]
~~~

Attestation cần liên kết với đúng artifact bằng digest. Nếu chỉ có một file JSON nói rằng build thành công nhưng không xác định artifact cụ thể, người nhận không thể biết lời chứng thực đó áp dụng cho file nào.

## 2. Phân biệt provenance, attestation, signature và SBOM

Các khái niệm này bổ sung cho nhau nhưng không thay thế nhau.

| Khái niệm | Câu hỏi trả lời | Nội dung điển hình |
|---|---|---|
| Build provenance | Artifact được tạo ra như thế nào và từ đầu vào nào? | Source revision, builder, workflow, parameters, dependencies, thời điểm |
| Attestation | Có lời chứng thực nào về một subject cụ thể không? | Subject digest, loại predicate, nội dung được chứng thực |
| Digital signature | Ai ký nội dung này và nội dung có bị thay đổi không? | Chữ ký gắn với payload, danh tính hoặc public key |
| SBOM | Artifact chứa hoặc phụ thuộc vào những thành phần phần mềm nào? | Package, version, supplier, license, dependency relationship |
| Checksum | File hiện tại có đúng các byte đã được băm không? | SHA-256 hoặc digest khác |
| Build log | Task nào đã chạy và log ghi lại điều gì? | Output console, task outcome, warning, error |
| Build Scan | Build quan sát được có đặc điểm và hiệu năng ra sao? | Task timeline, dependency resolution, environment data tùy cấu hình |

Một SBOM có thể liệt kê thư viện Jackson, JUnit và Spring Boot trong artifact. Nó không tự chứng minh artifact được tạo từ commit nào hoặc workflow nào. Provenance có thể ghi nhận các dependency/material đã dùng, nhưng không nhất thiết cung cấp inventory chi tiết như SBOM.

Checksum giúp so sánh nội dung file. Nó không nói ai tạo file. Chữ ký chứng minh payload được ký bởi danh tính/khóa tương ứng và không bị thay đổi sau khi ký, nhưng ý nghĩa của lời chứng thực vẫn phụ thuộc vào việc người xác minh có tin danh tính đó và policy của nó hay không.

Build log là bằng chứng vận hành hữu ích, nhưng log thông thường có thể bị thiếu, bị chỉnh sửa hoặc không gắn mật mã với artifact. Attestation được ký và ràng buộc bằng digest có thể được chuyển cùng artifact qua các hệ thống mà vẫn kiểm tra được tính toàn vẹn.

## 3. Artifact cần được nhận diện bằng digest

Tên artifact, version hoặc đường dẫn repository không phải định danh nội dung đủ mạnh. Một file có thể bị thay nội dung trong khi tên vẫn giữ nguyên. Digest mật mã nhận diện nội dung byte của artifact.

Ví dụ SHA-256:

~~~bash
sha256sum build/libs/order-service-2.4.1.jar
~~~

PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'build/libs/order-service-2.4.1.jar'
~~~

Kết quả có dạng:

~~~text
Algorithm : SHA256
Hash      : <64-hex-character-digest>
Path      : .../order-service-2.4.1.jar
~~~

Digest trong ví dụ là placeholder. Khi tạo provenance thực tế, pipeline cần tính digest từ chính file artifact cuối cùng sau khi build và đóng gói hoàn tất.

Ví dụ nội dung subject trong một attestation có thể chứa:

~~~json
{
  "name": "order-service-2.4.1.jar",
  "digest": {
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  }
}
~~~

Giá trị trên chỉ minh họa định dạng. Digest thực tế phải được tính từ chính file được chứng thực.

### Vì sao dùng digest thay vì chỉ dùng version?

Hai file có thể cùng tên order-service-2.4.1.jar nhưng có nội dung khác. Nếu attestation ràng buộc tới SHA-256, người xác minh có thể tính lại digest của file đang nhận và so sánh với subject trong attestation.

- Digest giống nhau: file có cùng nội dung byte với subject được chứng thực, với giả định thuật toán băm vẫn an toàn.
- Digest khác nhau: file không phải đúng nội dung được attestation tham chiếu.
- Tên giống nhau nhưng digest khác nhau: không được coi là cùng artifact.

Digest là cầu nối giữa file vật lý và statement provenance. Tên/version vẫn hữu ích cho con người, nhưng không nên thay thế digest trong xác minh.

## 4. Provenance cần mô tả những gì?

Một bản provenance hữu ích thường ghi nhận bốn nhóm thông tin:

1. **Subject:** artifact cụ thể được tạo, nhận diện bằng tên và digest.
2. **Builder:** hệ thống hoặc danh tính thực hiện build.
3. **Build definition/invocation:** loại build, workflow, tham số và cấu hình liên quan.
4. **Materials:** source revision, dependency, plugin, toolchain và các đầu vào khác được sử dụng.

Ví dụ các trường thông tin:

| Nhóm | Thông tin cần ghi |
|---|---|
| Artifact | Tên, loại, SHA-256, version, media type nếu có |
| Source | Repository URI, commit SHA, source ref, subdirectory hoặc source tree digest |
| Builder | CI platform, builder identity, workflow identity, runner/image |
| Build definition | Build type, workflow file, target task, parameters |
| Dependencies | Gradle distribution, plugins, library coordinates, resolved versions |
| Toolchain | JDK vendor/version, compiler version, OS/architecture, external tools |
| Invocation | Run ID, attempt, trigger, start/end time |
| Output | Artifact digest, file path, publication coordinate, image digest nếu có |
| Verification | Chữ ký, certificate identity, issuer hoặc key identifier |

Không phải mọi hệ thống đều hỗ trợ hoặc có thể ghi tất cả trường. Hãy phân biệt dữ liệu thực sự được quan sát với dữ liệu chỉ được suy đoán. Nếu pipeline không biết JDK vendor hoặc không ghi lại dependency graph, đừng tự tạo giá trị có vẻ chính xác.

### Materials và parameters

Materials thường mô tả các đầu vào được resolve hoặc dùng trong build, ví dụ source commit, dependency artifact và build tool distribution. Parameters mô tả các giá trị ảnh hưởng cách build được thực hiện, chẳng hạn task được yêu cầu, build target, feature flags hoặc tùy chọn cấu hình.

Không nên đưa secret vào provenance. Ghi nhận tên biến hoặc loại credential nếu cần kiểm toán, nhưng không ghi token, password, private key hay nội dung bí mật. Provenance có thể được phân phối rộng hơn log nội bộ; hãy xem nó như metadata có thể bị nhiều bên đọc.

## 5. Liên kết provenance với source revision

Để chứng minh artifact được tạo từ một phiên bản source xác định, provenance cần ghi nhận repository và revision cụ thể.

Thông tin thường dùng:

- Repository URI hoặc định danh source repository.
- Commit SHA đầy đủ, không chỉ branch name.
- Ref/branch/tag tại thời điểm build.
- Source tree hoặc archive digest nếu có.
- Subdirectory hoặc path nếu build chỉ sử dụng một phần monorepo.
- Submodule revision hoặc source dependency được lấy từ Git nếu chúng ảnh hưởng build.

Branch như main là một tên tham chiếu có thể di chuyển. Sau một thời gian, main có thể trỏ tới commit khác. Commit SHA xác định nội dung lịch sử cụ thể hơn.

Ví dụ lệnh lấy revision:

~~~bash
git rev-parse HEAD
git status --short
git submodule status
~~~

Trước khi phát hành, pipeline có thể yêu cầu working tree sạch hoặc ghi nhận thay đổi nếu build từ source archive có patch. Một build từ checkout có file sửa cục bộ chưa commit không nên được mô tả như thể nó được tạo chỉ từ commit sạch mà không có input bổ sung.

Với monorepo, chỉ ghi commit repository có thể chưa đủ để giải thích phần source thực sự ảnh hưởng artifact. Có thể bổ sung path/module được build và digest của source tree con hoặc danh sách source inputs do build system quản lý.

## 6. Liên kết provenance với dependency và build tools

Artifact Java phụ thuộc vào nhiều đầu vào ngoài source code:

- Gradle Wrapper distribution.
- Gradle plugins và convention plugins.
- JDK/toolchain và compiler options.
- Maven artifacts hoặc Gradle module metadata.
- BOM, platform, dependency constraints và lockfiles.
- Annotation processors và code generators.
- Công cụ ngoài như protoc, Node, Docker hoặc native compiler.
- Build scripts và version catalog.

Provenance nên mô tả những đầu vào quan trọng đủ để người xác minh hiểu artifact được tạo ra từ môi trường nào.

### Gradle dependency locking

Lockfile ghi lại version được resolve cho configuration đã bật locking:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau khi resolve dependency:

~~~bash
./gradlew build --write-locks
~~~

Lockfile giúp tái tạo lựa chọn version. Nó không chứng minh nội dung JAR tải về là đáng tin hoặc không bị thay thế.

### Dependency verification

Gradle có thể xác minh checksum/chữ ký dependency theo metadata:

~~~bash
./gradlew --write-verification-metadata sha256 help
~~~

Metadata được tạo cần được kiểm tra và quản lý trong version control. Verification kiểm tra artifact dependency tải về có khớp giá trị tin cậy đã cấu hình hay không.

### Toolchain và Wrapper

Provenance có thể ghi lại Gradle version và JDK được sử dụng:

~~~bash
./gradlew --version
java -version
~~~

java -version cho biết Java trong PATH của tiến trình shell; nó không nhất thiết là JDK toolchain mà JavaCompile sử dụng. Khi dùng Gradle toolchain, provenance cần lấy thông tin từ cấu hình/task/toolchain thực tế, không suy ra chỉ từ Java mặc định của runner.

Một provenance mạnh không chỉ ghi “Java 21”. Nếu chính sách yêu cầu, hãy ghi vendor, runtime/build image digest, architecture và compiler implementation. Mức độ chi tiết nên phù hợp với khả năng quan sát thực tế.

## 7. Attestation và cấu trúc in-toto Statement

Một cách phổ biến để biểu diễn attestation là dùng **in-toto Statement**. Statement có một subject và một predicate.

- subject nhận diện artifact hoặc đối tượng được chứng thực.
- predicateType xác định loại thông tin mà predicate chứa.
- predicate chứa dữ liệu theo schema tương ứng.

Ví dụ minh họa rút gọn:

~~~json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [
    {
      "name": "order-service-2.4.1.jar",
      "digest": {
        "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
      }
    }
  ],
  "predicateType": "https://slsa.dev/provenance/v1",
  "predicate": {
    "buildDefinition": {
      "buildType": "https://example.com/gradle-build/v1",
      "externalParameters": {
        "repository": "https://example.com/acme/order-service",
        "revision": "0123456789abcdef0123456789abcdef01234567",
        "tasks": [":app:build"]
      },
      "resolvedDependencies": [
        {
          "uri": "https://services.gradle.org/distributions/gradle-8.10.2-bin.zip",
          "digest": {
            "sha256": "<verified-distribution-digest>"
          }
        }
      ]
    },
    "runDetails": {
      "builder": {
        "id": "https://ci.example.com/builders/production"
      },
      "metadata": {
        "invocationId": "run-12345",
        "startedOn": "2026-11-13T08:00:00Z",
        "finishedOn": "2026-11-13T08:04:30Z"
      }
    }
  }
}
~~~

Đây là ví dụ cấu trúc để giải thích mối liên hệ giữa subject, build definition và run details; không phải một file provenance hoàn chỉnh có thể dùng ngay. Một triển khai SLSA cần tuân thủ schema và yêu cầu của predicate version tương ứng, bao gồm các trường bắt buộc và kiểu dữ liệu hợp lệ.

### Vì sao predicate type quan trọng?

Một statement có thể chứng thực nhiều điều khác nhau: build provenance, SBOM, kết quả kiểm thử hoặc kết quả quét bảo mật. predicateType cho người xác minh biết phải diễn giải nội dung theo schema nào.

Không nên dùng một predicate type chung rồi tự thêm trường tùy ý mà không tài liệu hóa. Hãy dùng predicate chuẩn khi phù hợp; nếu cần schema nội bộ, định nghĩa version, semantics và policy xác minh rõ ràng.

## 8. SLSA provenance và cấp độ tin cậy của builder

SLSA (Supply-chain Levels for Software Artifacts) là một khung thực hành để cải thiện bảo mật chuỗi cung ứng phần mềm. SLSA provenance mô tả quan hệ giữa artifact, build definition, builder và materials.

Các khái niệm quan trọng:

- **Build platform/builder:** hệ thống thực hiện build và tạo provenance.
- **Build definition:** cách build được xác định, bao gồm build type và tham số.
- **Resolved dependencies/materials:** đầu vào được resolve và dùng trong build.
- **Run details:** thông tin về lần chạy cụ thể và builder identity.
- **Provenance authenticity:** khả năng xác minh provenance thực sự đến từ builder được tin cậy.

Cấp độ SLSA mô tả các yêu cầu về cách build được kiểm soát và mức độ tin cậy của provenance. Chỉ thêm một JSON có trường builder không làm hệ thống tự đạt một cấp độ SLSA. Cần đáp ứng yêu cầu của phiên bản specification và cấp độ mục tiêu, đồng thời dùng builder có khả năng tạo provenance đáng tin.

Không nên tự tuyên bố cấp độ SLSA chỉ dựa trên việc pipeline có ký một file JSON. Hãy xác định phiên bản specification, phạm vi áp dụng và bằng chứng mà builder cung cấp.

### Build service đáng tin cậy

Một builder đáng tin cậy cần có khả năng chứng minh:

- Workflow được xác định bởi cấu hình được kiểm soát.
- Source revision và build parameters được ghi nhận.
- Build chạy trong môi trường có danh tính rõ.
- Provenance được tạo bởi hệ thống build, không phải bởi một script tùy ý sau khi artifact được tạo.
- Người dùng không thể tùy ý giả mạo danh tính builder hoặc thay nội dung provenance.
- Artifact được liên kết bằng digest chính xác.
- Quá trình phát hành có thể xác minh provenance theo policy.

Nếu developer tự tạo một file provenance trên máy local và tự ký nó bằng khóa cá nhân, đó có thể là một attestation do developer phát hành, nhưng không tương đương bằng chứng từ CI builder được tổ chức tin cậy.

## 9. DSSE và cách bảo vệ attestation

DSSE (Dead Simple Signing Envelope) là một định dạng envelope để ký payload theo cách có thể xác định loại payload và nội dung được ký. Nó thường được dùng cùng in-toto attestation.

Về khái niệm, envelope chứa:

- Payload: statement, thường được mã hóa Base64.
- Payload type: loại nội dung được ký.
- Signatures: một hoặc nhiều chữ ký trên payload theo quy tắc DSSE.

Khi verify, công cụ kiểm tra chữ ký trên đúng payload type và bytes được ký. Điều này giúp tránh việc diễn giải cùng một payload dưới ngữ nghĩa khác mà không được ràng buộc trong chữ ký.

Chữ ký bảo vệ tính toàn vẹn và xác thực nguồn ký theo trust configuration. Nó không tự chứng minh mọi trường trong payload là đúng. Nếu một builder không đáng tin tạo provenance sai rồi ký bằng danh tính mà verifier chấp nhận, chữ ký vẫn hợp lệ về mặt mật mã nhưng lời chứng thực không đáng tin về mặt quy trình.

Do đó, xác minh attestation gồm hai phần:

1. Xác minh mật mã: chữ ký hợp lệ và payload không bị thay đổi.
2. Xác minh policy: signer/builder có được phép chứng thực loại artifact này và các claim trong predicate có đáp ứng yêu cầu không.

## 10. Ký provenance: khóa quản lý và keyless signing

Có hai cách triển khai phổ biến.

### Ký bằng khóa được quản lý

Tổ chức tạo và quản lý cặp khóa:

- Private key dùng để ký.
- Public key được phân phối tới verifier.
- Key identifier hoặc certificate giúp chọn khóa.
- Quy trình rotation, backup, revoke và access control.

Private key cần được giữ trong secret manager, HSM hoặc hệ thống ký chuyên dụng. Không commit private key vào source repository, không ghi vào log và không đưa vào Docker image build.

Ưu điểm là tổ chức kiểm soát vòng đời khóa. Đổi lại, cần vận hành bảo mật khóa, rotation, phân quyền và thu hồi.

### Keyless signing

Keyless signing dùng danh tính workload được cấp trong phiên CI, thường thông qua OIDC identity token. Công cụ ký trao đổi token để nhận certificate ngắn hạn gắn với identity claim. Chữ ký và certificate có thể được ghi vào transparency log tùy hệ sinh thái.

Verifier cần kiểm tra:

- Certificate chain được tin cậy.
- OIDC issuer đúng.
- Certificate identity đúng repository/workflow/organization theo policy.
- Chữ ký hợp lệ.
- Transparency evidence được kiểm tra theo cấu hình.
- Artifact digest trùng với subject.

Keyless không có nghĩa là không cần trust. Verifier vẫn phải quyết định issuer và identity nào được chấp nhận. Nếu policy chỉ kiểm tra “chữ ký hợp lệ” mà không kiểm tra signer identity, một workflow không được phép có thể phát hành attestation mà verifier vẫn chấp nhận.

## 11. Tạo digest và provenance trong pipeline Gradle

Gradle tạo artifact, còn CI thường là nơi có đủ thông tin về source checkout, workflow identity và lần chạy để tạo provenance đáng tin cậy.

Ví dụ task build:

~~~bash
./gradlew clean :app:build
~~~

Giả sử JAR nằm tại:

~~~text
app/build/libs/order-service-2.4.1.jar
~~~

Sau khi build thành công, pipeline tính digest:

~~~bash
sha256sum app/build/libs/order-service-2.4.1.jar
~~~

Trên PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'app/build/libs/order-service-2.4.1.jar'
~~~

Tiếp theo, hệ thống CI tạo provenance statement từ thông tin thực tế:

- Commit SHA đã checkout.
- Repository và source ref.
- Workflow file và workflow revision.
- Builder identity.
- Gradle Wrapper version.
- JDK/toolchain thực tế.
- Task/target được chạy.
- Lockfile và resolved dependencies.
- Digest của artifact vừa tạo.

Điểm quan trọng là digest được tính sau khi artifact cuối cùng đã được tạo. Nếu pipeline sửa JAR, thêm metadata hoặc repack archive sau khi tính digest, subject sẽ không còn khớp file cuối cùng. Vì vậy, hãy xác định ranh giới rõ ràng: build hoàn tất, artifact đóng băng, digest được tính, provenance được tạo và ký, sau đó mới publish.

## 12. Ví dụ pipeline CI ở mức khái niệm

Một workflow có thể gồm các bước:

~~~yaml
name: Build and attest

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@<pinned-commit>

      - name: Set up JDK
        uses: actions/setup-java@<pinned-commit>
        with:
          distribution: temurin
          java-version: "21"

      - name: Build
        run: ./gradlew clean :app:build

      - name: Create artifact digest
        run: sha256sum app/build/libs/order-service.jar

      - name: Generate and sign provenance
        run: |
          # Invoke the organization's trusted provenance generator.
          # Bind the statement subject to the exact JAR digest.
          # Sign using the CI workload identity.
          echo "Generate and attest with approved tooling"
~~~

Các giá trị <pinned-commit> và lệnh placeholder cần được thay bằng action/tool version và cách tích hợp đã được tổ chức phê duyệt. Không dùng tag action có thể di chuyển nếu policy yêu cầu pin action theo commit SHA.

Trong ví dụ, id-token: write chỉ minh họa quyền thường cần cho keyless identity flow trên một số CI platform. Quyền thực tế phụ thuộc công cụ ký và nền tảng. Hãy cấp quyền tối thiểu và chỉ cho job cần ký.

### Vì sao build và attest nên nằm trong cùng trusted workflow?

Nếu một job build artifact, upload file rồi một workflow khác tải file về và tự tạo provenance mà không kiểm tra nguồn, mối liên hệ giữa build và artifact có thể bị mất. Workflow attest cần xác minh digest của artifact nhận được, nguồn artifact, run identity và các metadata của lần build.

Tốt nhất là provenance được tạo bởi builder hoặc một bước được kiểm soát chặt trong cùng pipeline. Nếu dùng separate attestor, phải có cơ chế xác thực nguồn artifact và run metadata đáng tin cậy.

## 13. Dùng Cosign để ký và xác minh blob attestation

Cosign trong hệ sinh thái Sigstore có thể ký artifact và attestation. Với file JAR, cách làm tổng quát là:

1. Tạo predicate/provenance document.
2. Gắn subject digest với JAR.
3. Tạo attestation envelope và ký.
4. Lưu bundle/attestation cùng artifact hoặc trong transparency/registry service.
5. Xác minh chữ ký và signer identity trước khi dùng artifact.

Một lệnh minh họa với keyless signing cho blob:

~~~bash
cosign attest-blob \
  --yes \
  --predicate provenance.json \
  --type slsaprovenance \
  order-service.jar
~~~

Tùy phiên bản Cosign và cách lưu bundle, có thể cần chỉ định đường dẫn bundle hoặc output tương ứng. Hãy kiểm tra CLI help của version đã pin và quy trình lưu attestation trong tổ chức.

Với khóa được quản lý, quy trình ký có thể chỉ định private key:

~~~bash
cosign attest-blob \
  --key cosign.key \
  --predicate provenance.json \
  --type slsaprovenance \
  order-service.jar
~~~

Không đặt private key thật trong repository. Ví dụ chỉ minh họa luồng lệnh; private key cần đến từ secret manager hoặc signing service có kiểm soát.

Khi xác minh blob attestation, cần chỉ định trust policy phù hợp, chẳng hạn certificate identity và OIDC issuer trong keyless flow, hoặc public key được tin cậy trong key-based flow. Cú pháp tùy version Cosign và kiểu bundle:

~~~bash
cosign verify-blob-attestation \
  --bundle order-service.jar.bundle \
  --type slsaprovenance \
  --certificate-identity "https://ci.example.com/workflows/release.yml@refs/tags/v2.4.1" \
  --certificate-oidc-issuer "https://token.actions.example" \
  order-service.jar
~~~

Các giá trị identity và issuer ở đây là placeholder minh họa. Dùng đúng claim do CI issuer thực tế cấp và policy của tổ chức. Chỉ kiểm tra rằng lệnh verify trả thành công là chưa đủ nếu identity selector quá rộng.

Với artifact container image, Cosign có luồng ký/attest image riêng; không nên dùng lệnh blob cho image reference nếu công cụ yêu cầu image-specific workflow.

## 14. Kiểm tra artifact sau khi tải từ repository

Provenance cần được xác minh tại nơi artifact được tiêu thụ, không chỉ ngay sau khi build.

Giả sử CI publish:

~~~text
com.example:order-service:2.4.1
~~~

Một deployment job tải JAR về. Trước khi chạy, job nên:

1. Tính lại SHA-256 của file tải về.
2. Tải attestation/bundle tương ứng.
3. Xác minh chữ ký và identity.
4. Xác minh subject digest khớp file.
5. Kiểm tra source repository và commit được cho phép.
6. Kiểm tra builder/workflow identity được cho phép.
7. Kiểm tra build parameters, materials và policy bắt buộc.
8. Chỉ sau đó mới đưa artifact vào môi trường tiếp theo.

~~~mermaid
flowchart TD
    A[Download artifact] --> B[Compute SHA-256]
    C[Retrieve attestation] --> D[Verify signature and signer]
    B --> E[Compare subject digest]
    D --> F[Evaluate provenance policy]
    E --> F
    F --> G{All checks pass?}
    G -->|Yes| H[Promote or deploy exact artifact]
    G -->|No| I[Reject and record evidence]
~~~

Không nên rebuild ở bước deploy để “lấy lại đúng file”. Rebuild có thể tạo output khác do thời gian, dependency, toolchain hoặc environment. Hãy promote chính artifact đã được build, kiểm tra và chứng thực.

## 15. Xây dựng policy xác minh provenance

Một policy có ý nghĩa cần kiểm tra nhiều claim, không chỉ chữ ký.

Ví dụ policy cho release JAR:

- Subject digest phải bằng digest của file đang triển khai.
- Predicate type phải là provenance schema được tổ chức chấp nhận.
- Signer identity phải là workflow release chính thức.
- OIDC issuer hoặc key phải thuộc trust root đã phê duyệt.
- Source repository phải đúng repository của sản phẩm.
- Source revision phải là commit được release tag tham chiếu.
- Build phải chạy từ protected branch/tag hoặc release workflow hợp lệ.
- Builder phải thuộc nhóm CI được quản trị.
- Gradle Wrapper và JDK/toolchain phải thuộc version được hỗ trợ.
- Materials quan trọng phải có digest hoặc version được ghi nhận.
- Không được dùng dependency source hoặc repository bị cấm.
- Artifact phải được tạo trong invocation đã hoàn tất thành công.
- Nếu policy yêu cầu, phải có SBOM và scan attestation tương ứng.

Policy có thể biểu diễn bằng quy tắc logic:

~~~text
ACCEPT artifact IF
    signature_is_valid
    AND signer_identity IN approved_release_workflows
    AND predicate_type == approved_provenance_type
    AND subject.sha256 == downloaded_artifact.sha256
    AND source.repository == expected_repository
    AND source.revision == approved_release_commit
    AND builder.id IN approved_builders
    AND required_materials_are_present
    AND build_parameters_satisfy_policy
~~~

Đây là pseudocode để mô tả policy, không phải ngôn ngữ policy của một công cụ cụ thể. Khi triển khai, dùng verifier và schema policy phù hợp, đồng thời kiểm tra kiểu dữ liệu và trường bắt buộc.

### Policy phải kiểm tra identity cụ thể

Nếu chỉ kiểm tra issuer, nhiều workflow khác nhau có thể cùng dùng issuer đó. Nếu chỉ kiểm tra tên repository, một workflow không được bảo vệ trong cùng repository có thể có quyền tạo attestation. Hãy ràng buộc identity đủ cụ thể: organization, repository, workflow path, ref/environment hoặc claim tương đương mà CI cấp.

## 16. Provenance không tự chứng minh source an toàn

Provenance trả lời artifact được tạo từ đâu và bằng cách nào theo những thông tin builder chứng thực. Nó không tự chứng minh:

- Source code không có lỗ hổng.
- Dependency không có CVE.
- Build script không độc hại.
- Test bao phủ đầy đủ chức năng.
- Builder không bị xâm nhập.
- Người có quyền merge đã review đúng.
- Artifact đáp ứng mọi policy của tổ chức.

Một workflow đáng tin vẫn có thể build source chứa lỗ hổng. Một dependency đã được pin vẫn có thể chứa mã độc. Một attestation có chữ ký hợp lệ vẫn có thể mô tả một build không an toàn nếu builder hoặc workflow được tin cậy nhưng cấu hình yếu.

Provenance là một phần của chuỗi bằng chứng. Cần kết hợp với code review, branch protection, dependency verification, SBOM, vulnerability scanning, test results, signing policy và kiểm soát quyền phát hành.

## 17. Liên kết SBOM với đúng artifact

SBOM mô tả thành phần phần mềm có trong hoặc được sử dụng bởi một artifact. Để tránh nhầm lẫn, SBOM cũng nên được liên kết với artifact bằng digest.

Một quy trình có thể là:

1. Build JAR.
2. Tính digest của JAR.
3. Tạo SBOM cho chính JAR đó.
4. Tạo attestation cho SBOM với subject là digest JAR.
5. Ký attestation.
6. Lưu SBOM và attestation cùng release.
7. Xác minh digest và chữ ký trước khi dùng SBOM cho scanning/compliance.

Có thể dùng định dạng SBOM như SPDX hoặc CycloneDX. Chọn schema và version phù hợp với công cụ trong tổ chức.

Cần phân biệt:
- SBOM cho dependency graph được resolve.
- SBOM cho nội dung thực sự đóng gói trong artifact.
- SBOM cho container image chứa JAR và các package hệ điều hành.

Ba inventory này có thể khác nhau. Ví dụ, runtime-only dependency có thể được đóng gói trong executable JAR, còn test dependency không có trong sản phẩm. Container image còn có thêm OS packages và native libraries. Hãy ghi rõ SBOM mô tả đối tượng nào.

## 18. Chữ ký artifact khác chữ ký provenance

Một số hệ thống ký trực tiếp artifact; một số hệ thống ký attestation; release có thể cần cả hai.

| Chữ ký | Nội dung được ký | Mục đích |
|---|---|---|
| Artifact signature | File JAR, ZIP, image hoặc digest của nó | Xác nhận nội dung artifact và signer |
| Provenance attestation signature | Statement/envelope chứa subject digest và predicate | Xác nhận lời chứng thực về nguồn gốc build |
| SBOM attestation signature | Statement liên kết SBOM với artifact | Xác nhận inventory được tạo cho artifact cụ thể |
| Release manifest signature | Manifest gồm nhiều artifact/digest | Xác nhận tập artifact được phát hành cùng nhau |

Gradle Signing Plugin có thể ký publication artifact bằng PGP hoặc cơ chế tương ứng. Điều đó hữu ích cho xác minh publisher và tính toàn vẹn artifact, nhưng chữ ký JAR đơn lẻ không chứa thông tin đầy đủ về source commit, builder và materials.

Nếu tổ chức cần cả artifact signature và provenance attestation, hãy xác định rõ hai bước và hai policy. Không coi một file .asc là bằng chứng build provenance nếu nó chỉ ký artifact.

## 19. Không để mất liên kết khi đóng gói hoặc publish

Artifact có thể thay đổi sau khi build:

- Thêm manifest hoặc metadata vào JAR.
- Repack archive để đổi timestamp hoặc thứ tự entry.
- Shading/relocation dependency.
- Tạo executable/fat JAR.
- Đưa JAR vào container image.
- Nén hoặc mã hóa file.
- Ký trực tiếp archive.

Mỗi thay đổi tạo nội dung byte khác và do đó digest khác. Nếu provenance được tạo trước bước cuối cùng, subject có thể trỏ tới artifact trung gian thay vì artifact phát hành.

Hãy xác định từng ranh giới artifact:

~~~mermaid
flowchart LR
    A[Compiled classes] --> B[Application JAR]
    B --> C[Signed JAR]
    C --> D[Container image]
    D --> E[Deployment digest]
~~~

Nếu pipeline tạo nhiều artifact dẫn xuất, mỗi artifact có thể cần subject/attestation riêng hoặc provenance liên kết các artifact theo quy trình được hỗ trợ. Ví dụ JAR có provenance build; container image có provenance packaging/image build, với JAR digest là một material của image build.

Không dùng digest của JAR để đại diện cho container image. Chúng là hai đối tượng khác nhau.

## 20. Build provenance trong multi-module Gradle build

Một Gradle build có thể tạo nhiều JAR từ các project khác nhau. Cần xác định artifact nào được chứng thực và materials nào ảnh hưởng đến nó.

~~~text
order-system/
├── domain/
│   └── build/libs/domain-2.4.1.jar
├── persistence/
│   └── build/libs/persistence-2.4.1.jar
└── app/
    └── build/libs/order-service-2.4.1.jar
~~~

app có thể phụ thuộc domain và persistence. Provenance của order-service nên phản ánh source revision/build invocation và những project dependency đã được dùng để tạo ứng dụng.

Nếu CI publish cả ba JAR, có thể tạo subject riêng cho từng artifact. Một statement có thể chứa nhiều subject nếu predicate và quy trình cho phép, nhưng người xác minh cần biết policy áp dụng cho từng subject.

Không nên tạo một attestation chung chỉ ghi tên root project mà không liên kết digest từng artifact. Người nhận cần xác định chính xác file nào được chứng thực.

## 21. Provenance của build logic và plugin

Build script và plugin có thể thực thi code trong quá trình cấu hình hoặc task execution. Vì vậy, chúng cũng là đầu vào quan trọng.

Một bản provenance cho Java artifact có thể ghi nhận:

- Gradle Wrapper distribution và checksum.
- Plugin IDs và versions.
- Included build hoặc convention plugin source revision.
- Version catalog.
- Build logic dependencies.
- Settings repository policy.
- Task path và build parameters.
- Java toolchain/compiler version.
- Annotation processor versions.
- Dependency lock state.

Nếu plugin được resolve từ plugin portal hoặc repository nội bộ, provenance nên cho phép truy vết tọa độ/version và digest khi hệ thống hỗ trợ.

Không nhất thiết nhúng toàn bộ nội dung build script vào attestation. Có thể liên kết tới commit source và ghi build type/workflow definition. Điều quan trọng là người xác minh có thể truy xuất và kiểm tra đúng cấu hình build đã được dùng.

## 22. Lưu trữ và phân phối attestation

Attestation cần được phân phối cùng artifact hoặc trong một hệ thống có thể truy xuất bằng digest.

Một số lựa chọn:

- Lưu bundle/attestation cạnh file artifact trong release storage.
- Đính kèm attestation vào OCI registry theo digest image/artifact khi registry/tool hỗ trợ.
- Lưu trong transparency log và truy vấn theo subject digest.
- Publish vào artifact repository nội bộ cùng metadata.
- Lưu provenance như CI artifact bất biến với quyền truy cập phù hợp.

Không nên chỉ lưu attestation trong log console của CI. Log có thể hết retention, khó tìm và không nhất thiết có định dạng máy đọc được.

Cần đảm bảo:
- Artifact và attestation có thể được truy xuất cùng nhau.
- Attestation không bị ghi đè âm thầm.
- Subject digest vẫn khớp file hiện tại.
- Retention đủ dài theo yêu cầu audit.
- Quyền ghi attestation bị giới hạn.
- Verifier có thể lấy trust root/certificate metadata cần thiết.
- Có quy trình revoke hoặc xử lý khi key/builder identity bị xâm nhập.

## 23. Kiểm tra provenance trước khi promote artifact

Một pipeline phát hành có thể chia thành build, verify và promote:

~~~mermaid
flowchart TD
    A[Build from protected source] --> B[Create artifact]
    B --> C[Generate provenance and SBOM]
    C --> D[Sign attestations]
    D --> E[Verify signature and policy]
    E --> F{Approved?}
    F -->|Yes| G[Promote same artifact digest]
    F -->|No| H[Reject release]
    G --> I[Deploy exact digest]
~~~

Một số nguyên tắc quan trọng:

1. Không build lại ở mỗi môi trường nếu mục tiêu là promote cùng artifact.
2. Dùng digest để xác định file/container image.
3. Xác minh provenance trước khi cấp quyền deploy.
4. Kiểm tra source ref và workflow identity, không chỉ chữ ký.
5. Ghi lại kết quả verification để phục vụ audit.
6. Nếu artifact được repack hoặc transform, tạo provenance/attestation cho artifact mới.
7. Chỉ cấp deploy credentials sau khi verification policy thành công.

Việc xác minh nên được thực hiện ở ranh giới tin cậy, ví dụ release gate hoặc deployment controller, để artifact không thể bỏ qua kiểm tra chỉ bằng cách gọi một task Gradle khác.

## 24. Điều tra khi attestation không khớp

Một số lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Digest trong subject khác file tải về | Artifact bị thay đổi sau khi attest hoặc tải nhầm file | Tính lại digest ở cả hai đầu, kiểm tra tên/path và pipeline steps |
| Chữ ký không hợp lệ | Payload bị sửa, bundle hỏng hoặc sai trust root | Kiểm tra bundle, signature và certificate chain |
| Certificate identity không khớp | Workflow/ref/repository khác identity policy | Xem certificate claims và so sánh policy |
| OIDC issuer không được tin cậy | Dùng issuer khác hoặc trust configuration sai | Xác minh issuer thực tế của CI |
| Provenance thiếu source revision | Generator không nhận được checkout metadata | Kiểm tra build invocation và source checkout step |
| Dependency/materials không đầy đủ | Builder không thu thập hoặc build dùng nguồn không được mô tả | Kiểm tra Gradle resolution, lockfiles và build definition |
| Attestation đúng nhưng policy từ chối | Builder/source/ref/parameters không được phép | Xem từng predicate claim bị policy từ chối |
| JAR đúng nhưng container image không đúng | Image được build từ JAR khác hoặc layer bị thay đổi | Kiểm tra JAR digest là material của image build và image digest |
| Attestation không tìm thấy | Chưa publish, sai lookup digest hoặc retention | Kiểm tra storage/registry và digest truy vấn |

Không nên giải quyết bằng cách bỏ qua verification hoặc chấp nhận mọi certificate. Hãy xác định chính xác claim nào không khớp và sửa nguồn dữ liệu hoặc policy theo quy trình.

## 25. Những giới hạn và rủi ro cần hiểu

Provenance là bằng chứng có cấu trúc, nhưng chất lượng của nó phụ thuộc vào builder và quy trình.

### Builder bị xâm nhập

Nếu attacker kiểm soát builder, họ có thể tạo artifact độc hại và provenance có chữ ký hợp lệ từ builder đó. Cần bảo vệ runner, workflow permissions, CI secrets, build image và quyền thay đổi pipeline.

### Workflow được tin cậy quá rộng

Một policy chấp nhận mọi workflow trong một repository có thể vô tình tin cả workflow thử nghiệm hoặc branch không được bảo vệ. Hãy kiểm tra workflow identity và ref cụ thể.

### Input bị bỏ sót

Nếu task đọc file hoặc gọi dịch vụ không được khai báo, provenance có thể thiếu material quan trọng. Build provenance không tự khám phá mọi input ẩn; builder cần thu thập dữ liệu đúng và task cần mô tả input/output chính xác.

### Chữ ký hợp lệ không đồng nghĩa nội dung an toàn

Chữ ký xác thực người ký và bảo vệ nội dung sau khi ký. Nó không chứng minh source không có lỗi, dependency không có lỗ hổng hoặc test đầy đủ.

### Metadata có thể tiết lộ thông tin

Provenance có thể chứa repository URI, tên workflow, commit, package coordinates, environment labels và cấu trúc nội bộ. Tránh ghi secret, thông tin cá nhân hoặc đường dẫn máy nhạy cảm. Xem xét quyền truy cập nếu provenance được publish công khai.

## 26. Quy trình triển khai provenance cho một dự án Java

Có thể bắt đầu từ một artifact release và mở rộng dần:

1. **Chọn artifact:** xác định JAR, WAR, ZIP hoặc image nào cần chứng thực.
2. **Xác định builder tin cậy:** chọn CI workflow và identity được phép phát hành.
3. **Ghi source revision:** repository URI, commit SHA, ref và trạng thái checkout.
4. **Ghi build definition:** Gradle Wrapper, task paths, plugin versions, build logic và parameters.
5. **Thu thập materials:** lockfiles, dependency versions, toolchain, external tools và các input quan trọng.
6. **Build artifact:** chạy task cần thiết trong workflow đã kiểm soát.
7. **Đóng băng artifact:** hoàn tất mọi bước transform/packaging trước khi tính digest.
8. **Tính digest:** dùng SHA-256 hoặc thuật toán được policy chấp nhận.
9. **Tạo statement:** gắn subject digest và provenance predicate theo schema chuẩn.
10. **Ký attestation:** dùng key được quản lý hoặc workload identity phù hợp.
11. **Lưu và publish:** phân phối artifact cùng attestation/bundle.
12. **Xác minh:** kiểm tra signature, signer identity, subject digest và policy claims.
13. **Promote cùng artifact:** đưa chính digest đã được chấp thuận sang môi trường tiếp theo.
14. **Lưu evidence:** giữ attestation, SBOM, verification result và release metadata theo retention policy.

Bắt đầu từ một workflow release có thể kiểm soát tốt thường dễ hơn việc triển khai provenance cho mọi build local. Sau khi quy trình ổn định, mở rộng cho các artifact và repository khác.

## 27. Checklist thông tin provenance tối thiểu

Trước khi phát hành, hãy xác nhận hệ thống có thể trả lời:

- [ ] Artifact có tên và digest SHA-256.
- [ ] Subject trong attestation khớp digest của artifact cuối cùng.
- [ ] Repository và commit SHA được ghi nhận.
- [ ] Builder/CI identity được ghi nhận và có thể xác minh.
- [ ] Workflow/build type và invocation được nhận diện.
- [ ] Gradle Wrapper version và Java toolchain được ghi nhận.
- [ ] Plugin và dependency versions quan trọng có thể truy vết.
- [ ] Lockfile và dependency verification metadata được quản lý.
- [ ] Provenance dùng predicate schema có version xác định.
- [ ] Attestation được ký bằng identity/key được tin cậy.
- [ ] Verifier kiểm tra cả chữ ký và policy claims.
- [ ] Artifact và attestation có thể được truy xuất sau khi publish.
- [ ] Deployment dùng đúng artifact digest đã được xác minh.
- [ ] Secret không xuất hiện trong provenance.
- [ ] Có quy trình xử lý khi digest, identity hoặc policy không khớp.

Checklist này là hướng dẫn triển khai, không phải chứng nhận đạt một cấp độ SLSA hoặc tiêu chuẩn tuân thủ cụ thể. Cần đối chiếu yêu cầu của framework và tổ chức đang áp dụng.

## 28. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Tên JAR và version đủ để chứng minh nguồn gốc | Tên có thể giữ nguyên dù nội dung file bị thay; cần digest và attestation. |
| Checksum chứng minh ai đã tạo artifact | Checksum chỉ nhận diện nội dung byte; nó không xác thực builder. |
| Chữ ký artifact đồng nghĩa với build provenance | Chữ ký artifact xác thực file; provenance mô tả source, builder, invocation và materials. |
| SBOM cho biết artifact được build từ commit nào | SBOM là inventory thành phần; source/build origin cần provenance. |
| Có JSON provenance là đủ | Cần subject digest, schema, nguồn tạo đáng tin, chữ ký và verification policy. |
| Chữ ký hợp lệ nghĩa là artifact an toàn | Chữ ký chỉ xác thực signer/payload; policy và kiểm tra bảo mật vẫn cần thiết. |
| Provenance có thể được tạo từ bất kỳ log nào | Log có thể hỗ trợ nhưng builder cần tạo statement đáng tin và liên kết đúng artifact. |
| Branch name là định danh source bất biến | Branch có thể di chuyển; ghi commit SHA cụ thể. |
| Có thể ký artifact trước rồi sửa JAR sau | Mọi thay đổi byte làm digest thay đổi; ký/attest artifact cuối cùng. |
| Build provenance của JAR tự áp dụng cho container image | Image là artifact khác và cần subject digest/provenance phù hợp. |
| Keyless signing không cần kiểm tra identity | Verifier vẫn phải kiểm tra OIDC issuer và certificate identity theo policy. |
| SLSA level đạt được chỉ vì có attestation | Cấp độ đòi hỏi các yêu cầu cụ thể về builder, provenance và quy trình. |

## 29. Nguyên tắc cần ghi nhớ

Build provenance mô tả artifact được tạo từ source, materials, build definition và builder nào. Attestation đóng gói lời chứng thực đó theo một schema có thể đọc bằng máy; chữ ký và trust identity giúp người nhận xác minh nguồn phát hành và tính toàn vẹn của payload. Artifact phải được liên kết bằng digest, không chỉ bằng tên hoặc version.

Trong dự án Gradle, hãy ghi nhận commit SHA, Wrapper, JDK/toolchain, plugin, dependency và task invocation thực tế. Tạo digest sau khi artifact cuối cùng đã được đóng gói, tạo provenance statement có subject tương ứng, ký bằng key hoặc CI workload identity được quản lý và lưu attestation cùng artifact. Ở bước promote/deploy, xác minh chữ ký, signer identity, digest và policy claims rồi dùng đúng artifact đã được kiểm tra.

Provenance không thay thế SBOM, dependency verification, code review, testing hoặc vulnerability scanning. Nó bổ sung một lớp bằng chứng để nhóm có thể truy vết và kiểm soát mối liên hệ giữa đầu vào build, hệ thống tạo build và artifact được phát hành.

