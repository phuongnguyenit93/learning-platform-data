# Artifact Provenance cho Java build

## 1. Artifact provenance là gì?

**Artifact provenance** là tập thông tin có thể kiểm chứng cho biết một artifact phần mềm được tạo ra từ đâu, bởi quy trình nào, trên build platform nào và với những đầu vào nào.

Với một file JAR, provenance giúp người nhận trả lời:

- Artifact này thuộc project, version và release nào?
- Nó được build từ repository và commit nào?
- Workflow, Maven/Gradle, JDK và compiler nào đã chạy?
- Dependency, plugin, toolchain và build image nào đã tham gia?
- Artifact có bị thay đổi sau khi build hoặc sau khi phát hành không?
- Ai hoặc hệ thống nào đã xác nhận các thông tin đó?

Provenance hữu ích trong release engineering, kiểm toán, điều tra sự cố, quản lý lỗ hổng dependency và kiểm soát software supply chain. Nó giúp người dùng xác định artifact đang chạy có đúng là bản build được phê duyệt hay không.

Một tên file như \`service-1.2.3.jar\` hoặc Maven coordinate \`com.example:service:1.2.3\` chỉ mô tả danh tính logic. Để định danh chính xác từng byte, cần digest mật mã như SHA-256.

## 2. Phân biệt checksum, signature, SBOM và provenance

Các loại metadata này giải quyết những câu hỏi khác nhau:

| Thành phần | Câu hỏi trả lời | Điều nó chứng minh |
|---|---|---|
| Checksum | File hiện tại có cùng bytes với digest đã biết không? | Tính toàn vẹn so với một digest đáng tin. |
| Digital signature | Ai hoặc hệ thống nào đã ký bytes này? | Tính xác thực của chữ ký và tính toàn vẹn của payload. |
| SBOM | Artifact chứa hoặc phụ thuộc vào những component nào? | Danh mục component và dependency trong phạm vi SBOM. |
| Build provenance | Artifact được tạo từ source, builder và quy trình nào? | Các claim về nguồn và cách build, nếu attestation được xác thực. |
| Reproducible build | Build lại với cùng inputs có tạo ra cùng bytes không? | Khả năng tái lập của output trong điều kiện đã kiểm soát. |

Không thành phần nào thay thế hoàn toàn thành phần khác.

Checksum không nói ai tạo artifact. Signature không tự nói artifact được build từ commit nào. SBOM không chứng minh artifact đã được build bởi CI đáng tin. Provenance không tự bảo đảm dependency an toàn. Reproducible build không chứng minh build process đã dùng source được phê duyệt.

Một release đáng tin thường kết hợp artifact digest, SBOM và attestation có chữ ký, rồi áp dụng chính sách xác minh trước khi sử dụng.

## 3. Định danh artifact bằng Maven coordinates và digest

Maven coordinates gồm:

- \`groupId\`: nhóm hoặc namespace của project.
- \`artifactId\`: tên artifact.
- \`version\`: phiên bản phát hành.
- \`classifier\`: phân loại bổ sung nếu có.
- \`type/extension\`: loại file, ví dụ jar, pom hoặc war.

Ví dụ:

~~~text
com.example:payment-service:1.2.3
com.example:payment-service:1.2.3:tests
com.example:payment-service:1.2.3:jar
~~~

Coordinates giúp tìm artifact trong repository. Tuy nhiên, một repository không được quản lý đúng có thể cho phép ghi đè cùng một coordinate. Vì vậy, consumer cần xác minh SHA-256 của file thực tế.

Ví dụ trên Linux:

~~~bash
sha256sum target/payment-service-1.2.3.jar
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 target\payment-service-1.2.3.jar
~~~

Digest là dấu vân tay của bytes. Nếu chỉ một byte thay đổi, SHA-256 gần như chắc chắn thay đổi.

Trong attestation, artifact được đặt trong trường \`subject\` cùng digest. Verifier phải tính digest của file nhận được và so sánh với digest đã ký. Không nên chỉ tin vào filename hoặc version string.

## 4. Những dữ liệu cần ghi nhận cho một build

Một provenance hữu ích thường chứa các nhóm thông tin sau:

| Nhóm | Dữ liệu nên lưu |
|---|---|
| Artifact | Tên, Maven coordinates, loại file, SHA-256. |
| Source | Repository URI, commit SHA, tag/ref, trạng thái source tree. |
| Build definition | Workflow path, POM/Gradle files, build type, build parameters. |
| Builder | CI platform identity, runner hoặc build image, builder version. |
| Toolchain | JDK vendor/version, Maven/Gradle Wrapper, compiler và plugin versions. |
| Dependencies | Dependency URI, version, package URL, digest khi có. |
| Invocation | Run ID, thời gian bắt đầu/kết thúc, workflow URL hoặc log reference. |
| Outputs | JAR/WAR, SBOM, checksum file, provenance bundle và các byproducts cần giữ. |

Không phải mọi field đều được mọi build platform ghi tự động. Hãy phân biệt dữ liệu được platform xác thực với dữ liệu do script trong repository tự khai báo.

Không đưa password, access token, private key, credential hoặc biến môi trường bí mật vào provenance. Các parameter bên ngoài phải được kiểm tra bởi consumer vì chúng có thể chịu ảnh hưởng từ người gọi workflow.

## 5. Source identity: repository, ref và commit

Tên branch như \`main\` có thể thay đổi. Tag cũng có thể bị di chuyển nếu repository không bảo vệ tag. Để truy nguyên một build cụ thể, cần ghi commit SHA bất biến.

Trong local repository:

~~~bash
git rev-parse HEAD
git status --short
git submodule status
~~~

Một release build nên xác nhận source tree sạch hoặc ghi rõ các thay đổi chưa commit nếu chính sách cho phép. Không nên build release từ working tree có file chưa được commit mà provenance chỉ ghi commit HEAD.

Trong GitHub Actions, \`GITHUB_SHA\` cung cấp commit liên quan tới workflow event. Có thể truyền vào Maven:

~~~bash
./mvnw -B -ntp -Dsource.revision="$GITHUB_SHA" clean verify
~~~

Với tag release, hãy xác minh tag trỏ đúng commit đã review. Lưu cả repository URI, ref và commit digest trong provenance. Commit SHA giúp xác định chính xác source revision; ref giúp hiểu build được kích hoạt từ branch hoặc tag nào.

Nếu project dùng Git submodule, source bundle hoặc generated code được tải từ nơi khác, cần ghi nhận những source inputs đó trong resolved dependencies hoặc byproducts phù hợp.

## 6. Phân biệt build JVM, compiler và runtime trong provenance

Một Java build có thể dùng nhiều JDK:

- Build JVM chạy Maven hoặc Gradle.
- Compiler toolchain chạy \`javac\`.
- Test launcher chạy unit/integration tests.
- Runtime JDK chạy ứng dụng sau khi deploy.

Ghi một dòng \`java -version\` chưa đủ để mô tả toàn bộ build. Cần ghi JDK toolchain mà compiler và test task thực sự dùng.

Các dữ liệu nên lưu gồm:

~~~text
Build JVM: Azul Zulu 24.0.2
Compiler toolchain: Amazon Corretto 17.0.15
Java release: 17
Maven Wrapper: 3.9.12
Maven Compiler Plugin: 3.13.0
~~~

Đây là ví dụ về các trường riêng biệt, không phải cấu hình bắt buộc. Giá trị phải được lấy từ log/toolchain thực tế của từng build.

Tương tự, nếu dùng container, ghi image digest thay vì chỉ ghi tag như \`maven:3.9-eclipse-temurin-17\`. Tag có thể được cập nhật; digest xác định image bytes.

## 7. SBOM là gì?

**Software Bill of Materials (SBOM)** là danh mục có cấu trúc về các component tạo nên một software product. Với ứng dụng Java, SBOM thường ghi:

- Component gốc của project.
- Dependency trực tiếp.
- Dependency bắc cầu.
- Version và package URL (PURL).
- License và supplier khi dữ liệu có sẵn.
- Hash của component nếu công cụ thu thập được.
- Quan hệ dependency giữa các component.

SBOM hỗ trợ vulnerability scanning, license review, dependency impact analysis và incident response. Khi một thư viện có lỗ hổng được công bố, đội vận hành có thể tìm những artifact có chứa phiên bản bị ảnh hưởng.

SBOM không tự chứng minh artifact đã được build từ dependency list đó. Cần gắn SBOM với artifact bằng digest và ký/attest SBOM để consumer xác minh nó thuộc đúng release.

## 8. CycloneDX và SPDX

Hai định dạng SBOM phổ biến:

| Định dạng | Đặc điểm |
|---|---|
| CycloneDX | Tập trung vào component, dependency, vulnerability và use case supply chain. |
| SPDX | Chuẩn ISO/IEC, mạnh về thông tin package, file, license và software composition. |

Chọn định dạng theo hệ thống nhận SBOM và chính sách tổ chức. Tránh tạo hai SBOM khác nhau cho cùng artifact nếu không có quy trình đồng bộ và kiểm tra.

Một SBOM nên ghi rõ:

- Phiên bản schema.
- Metadata của component gốc.
- Tool đã tạo SBOM.
- Thời điểm tạo.
- Phạm vi dependency được đưa vào.
- Các dependency bị loại trừ và lý do nếu cần.

Ví dụ, SBOM ứng dụng có thể loại test-scope dependencies. Nếu cần inventory cho build environment hoặc test supply chain, tạo thêm SBOM với scope phù hợp. SBOM ứng dụng không tự bao gồm tất cả Maven plugins, JDK và công cụ CI.

## 9. Tạo CycloneDX SBOM bằng Maven

CycloneDX Maven Plugin có thể tạo SBOM từ dependency tree của Maven project. Plugin hỗ trợ từng module và aggregate BOM cho multi-module build.

Ví dụ cấu hình:

~~~xml
<plugin>
  <groupId>org.cyclonedx</groupId>
  <artifactId>cyclonedx-maven-plugin</artifactId>
  <version>2.9.3</version>
  <executions>
    <execution>
      <phase>package</phase>
      <goals>
        <goal>makeAggregateBom</goal>
      </goals>
    </execution>
  </executions>
  <configuration>
    <outputFormat>json</outputFormat>
    <outputName>bom</outputName>
    <includeTestScope>false</includeTestScope>
  </configuration>
</plugin>
~~~

Sau khi chạy:

~~~bash
./mvnw -B -ntp clean package
~~~

Plugin tạo:

~~~text
target/bom.json
~~~

Với plugin 2.9.3, lần kiểm chứng trong bài này tạo CycloneDX schema 1.6. Plugin mới hơn có thể hỗ trợ schema mới hơn; hãy kiểm tra compatibility với consumer trước khi nâng version.

Goal \`makeBom\` tạo BOM theo từng Maven module. Goal \`makeAggregateBom\` tạo BOM tổng hợp ở root reactor và có thể tạo BOM theo module. Chọn goal phù hợp với cấu trúc project.

Mặc định, plugin gắn SBOM như artifact bổ sung khi install/deploy. Có thể tắt attach nếu pipeline quản lý SBOM riêng, nhưng phải bảo đảm SBOM được lưu cùng release và không mất liên kết với artifact.

## 10. Đọc và kiểm tra SBOM

Kiểm tra metadata của CycloneDX JSON:

~~~bash
jq '{bomFormat, specVersion, metadata, componentCount: (.components | length)}' target/bom.json
~~~

Liệt kê dependency:

~~~bash
jq -r '.components[] | [.name, .version, .purl] | @tsv' target/bom.json
~~~

Tìm một component cụ thể:

~~~bash
jq -r '.components[] | select(.name == "commons-lang3")' target/bom.json
~~~

Trên Windows PowerShell:

~~~powershell
$sbom = Get-Content target\bom.json -Raw | ConvertFrom-Json
$sbom.bomFormat
$sbom.specVersion
$sbom.components | Select-Object name, version, purl
~~~

Kiểm tra SBOM không chỉ là xác nhận file tồn tại. Hãy kiểm tra đúng project/version, dependency quan trọng, scope, schema và component count. Với multi-module, xác nhận BOM tổng hợp có đủ module.

Nếu dependency được tải hoặc thêm ngoài Maven dependency graph, ví dụ script tự tải binary trong build, SBOM mặc định có thể không chứa nó. Bổ sung dữ liệu bằng công cụ phù hợp và ghi rõ phạm vi coverage.

## 11. SLSA Build Provenance

SLSA là framework để mô tả và đánh giá mức độ bảo vệ software supply chain. Build provenance là một attestation mô tả artifact được tạo như thế nào.

Trong SLSA provenance:

- \`subject\`: artifact output và digest của nó.
- \`buildDefinition\`: cách build được khởi tạo và các input.
- \`buildType\`: định nghĩa loại build process.
- \`externalParameters\`: tham số do bên ngoài build platform cung cấp.
- \`resolvedDependencies\`: source, dependency và input artifacts đã được resolve.
- \`runDetails.builder.id\`: định danh build platform đáng tin.
- \`metadata.invocationId\`: định danh lần chạy build.
- \`startedOn\`, \`finishedOn\`: thời gian build.

Predicate type của SLSA Build Provenance là:

~~~text
https://slsa.dev/provenance/v1
~~~

URI này giữ major version trong khi minor specification có thể cập nhật tương thích. Tài liệu hiện hành là **SLSA v1.2**.

SLSA provenance cho consumer biết nơi, thời điểm và cách artifact được tạo. Độ tin cậy của thông tin phụ thuộc vào builder và cách platform tạo, ký, bảo vệ provenance. Một JSON do chính script trong repository tự ghi ra không tự động trở thành trusted provenance.

## 12. In-toto Attestation Framework

in-toto Attestation Framework định nghĩa cách ràng buộc metadata với artifact.

Framework có bốn lớp:

| Lớp | Vai trò |
|---|---|
| Predicate | Nội dung metadata theo một schema cụ thể, ví dụ SLSA provenance hoặc SBOM. |
| Statement | Liên kết subject artifact với predicate type và predicate. |
| Envelope | Đóng gói và xác thực attestation, thường qua chữ ký. |
| Bundle | Gom các attestation và dữ liệu xác minh liên quan. |

Một statement v1 dùng:

~~~text
https://in-toto.io/Statement/v1
~~~

Một attestation cần liên kết rõ subject và digest. Nếu predicate nói về artifact A nhưng consumer đang nhận artifact B, digest mismatch phải khiến xác minh thất bại.

SLSA provenance là một loại predicate có schema cụ thể trong in-toto framework. SBOM cũng có thể được đóng gói thành một attestation riêng. Nhờ vậy, provenance và inventory có thể được kiểm tra bằng các policy khác nhau.

## 13. Cấu trúc SLSA statement minh họa

Ví dụ dưới đây minh họa các field quan trọng. Các giá trị minh họa phải được builder đáng tin thay bằng dữ liệu thật của build; không ký hoặc phát hành nguyên văn ví dụ này.

~~~json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [
    {
      "name": "provenance-demo-1.0.0.jar",
      "digest": {
        "sha256": "DIGEST_SHA256_CUA_JAR"
      }
    }
  ],
  "predicateType": "https://slsa.dev/provenance/v1",
  "predicate": {
    "buildDefinition": {
      "buildType": "https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1",
      "externalParameters": {
        "repository": "https://github.com/example/provenance-demo",
        "ref": "refs/tags/v1.0.0"
      },
      "resolvedDependencies": [
        {
          "uri": "git+https://github.com/example/provenance-demo@refs/tags/v1.0.0",
          "digest": {
            "gitCommit": "COMMIT_SHA_DA_RESOLVE"
          }
        }
      ]
    },
    "runDetails": {
      "builder": {
        "id": "BUILDER_ID_DO_PLATFORM_CONG_BO"
      },
      "metadata": {
        "invocationId": "CI_RUN_ID",
        "startedOn": "2026-11-10T14:00:00Z",
        "finishedOn": "2026-11-10T14:02:00Z"
      }
    }
  }
}
~~~

Các điểm cần lưu ý:

- \`subject.digest.sha256\` phải là digest của file JAR phát hành.
- \`resolvedDependencies\` phải xác định commit thực tế, không chỉ branch name.
- \`builder.id\` phải là identity do CI platform công bố và mô tả.
- \`buildType\` phải mô tả đúng workflow hoặc build template.
- \`invocationId\` phải liên kết được tới build log cụ thể.
- Timestamp nên ở UTC và theo định dạng timestamp của spec.

Không tự đặt một builder ID rồi xem đó là danh tính đã được xác thực. Consumer cần có danh sách builder identity được tin cậy.

## 14. Builder identity và signer identity

Builder và signer là hai vai trò khác nhau.

**Builder identity** cho biết hệ thống nào thực hiện build và chịu trách nhiệm về độ chính xác của provenance.

**Signer identity** cho biết ai hoặc dịch vụ nào đã ký attestation.

Một signer có thể ký provenance cho nhiều builder. Vì vậy, verifier phải kiểm tra cặp signer-builder được policy cho phép. Chữ ký hợp lệ từ một identity không được tin cậy không làm artifact trở nên đáng tin.

Với hosted CI, builder identity thường được platform định nghĩa. Với self-hosted runner, cần đánh giá ai quản lý runner, cách cô lập job, cách cấp credential và khả năng runner bị lưu trạng thái từ build trước.

Không cấp quyền ký provenance cho mọi workflow hoặc branch. Release workflow cần quyền tối thiểu, protected environment và quy trình review phù hợp.

## 15. Hash và chữ ký số

SHA-256 giúp phát hiện artifact thay đổi:

~~~bash
sha256sum target/provenance-demo-1.0.0.jar > target/SHA256SUMS
sha256sum -c target/SHA256SUMS
~~~

Trên Windows:

~~~powershell
Get-FileHash -Algorithm SHA256 target\provenance-demo-1.0.0.jar
~~~

Nếu checksum và artifact được tải từ cùng một nguồn đã bị xâm nhập, kẻ tấn công có thể thay cả hai. Do đó, checksum nên được xác thực qua một chữ ký hoặc attestation có trust root độc lập.

Chữ ký số (digital signature) gắn một signer identity với bytes hoặc attestation. Consumer cần kiểm tra:

1. Chữ ký có hợp lệ không?
2. Certificate/key có được cấp bởi trust root mong đợi không?
3. Signer identity có đúng repository, workflow hoặc tổ chức không?
4. OIDC issuer có đúng không?
5. Subject digest trong payload có khớp artifact không?
6. Transparency log proof và timestamp có hợp lệ không nếu hệ thống dùng transparency log?

Chỉ kiểm tra chữ ký mà không kiểm tra identity có thể chấp nhận artifact do workflow hoặc tổ chức không mong muốn ký.

## 16. Keyless signing với Sigstore

Sigstore hỗ trợ ký artifact bằng identity được xác thực qua OpenID Connect (OIDC), thường gọi là keyless signing.

Luồng tổng quát:

1. CI nhận OIDC identity token từ identity provider.
2. Fulcio cấp certificate ngắn hạn gắn public key tạm thời với identity.
3. Cosign ký artifact bằng private key tạm thời.
4. Chữ ký và certificate được lưu trong bundle.
5. Rekor transparency log ghi nhận sự kiện ký.
6. Consumer xác minh bundle, certificate, identity, issuer và digest.

Ví dụ ký một file:

~~~bash
cosign sign-blob --yes --bundle artifact.sigstore.json target/provenance-demo-1.0.0.jar
~~~

Xác minh:

~~~bash
cosign verify-blob target/provenance-demo-1.0.0.jar \
  --bundle artifact.sigstore.json \
  --certificate-identity="https://github.com/OWNER/REPOSITORY/.github/workflows/release.yml@refs/heads/main" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com"
~~~

Thay OWNER, REPOSITORY và workflow identity bằng giá trị thực. Identity phải khớp certificate trong bundle. Không dùng wildcard quá rộng nếu policy yêu cầu chỉ chấp nhận release workflow cụ thể.

Keyless signing giảm nhu cầu lưu private key dài hạn trong CI secret. Tuy nhiên, quyền lấy OIDC token và quyền chạy release workflow vẫn cần được bảo vệ.

## 17. Tạo artifact provenance trên GitHub Actions

GitHub Actions có thể tạo artifact attestation sau khi build. Workflow cần các quyền:

~~~yaml
permissions:
  contents: read
  id-token: write
  attestations: write
~~~

Sau bước build, thêm:

~~~yaml
- name: Attest release JAR
  uses: actions/attest@v4
  with:
    subject-path: target/provenance-demo-1.0.0.jar
~~~

Attestation liên kết artifact với workflow, repository, organization, environment, commit SHA và thông tin từ OIDC token.

Có thể tạo thêm SBOM attestation:

~~~yaml
- name: Attest CycloneDX SBOM
  uses: actions/attest@v4
  with:
    subject-path: target/provenance-demo-1.0.0.jar
    sbom-path: target/bom.json
~~~

Artifact provenance và SBOM attestation là hai claim có predicate khác nhau. Cả hai đều liên kết với cùng artifact subject, giúp consumer xác minh nguồn build và inventory component riêng biệt.

Trong repository production, nên pin GitHub Actions bằng full commit SHA đã được review thay vì chỉ dùng version tag như \`@v4\`. Chỉ cấp \`id-token: write\` và \`attestations: write\` cho job thực sự cần ký.

Theo tài liệu GitHub hiện hành, artifact attestations có trên các plan hiện tại; Free, Pro và Team chỉ hỗ trợ repository public, còn private/internal repository cần GitHub Enterprise Cloud. Kiểm tra điều kiện plan và visibility trước khi thiết kế release pipeline.

## 18. Ví dụ workflow Maven hoàn chỉnh

Workflow minh họa build Java 17, tạo JAR và SBOM, sau đó attest cả hai:

~~~yaml
name: Java release

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
      attestations: write

    steps:
      - uses: actions/checkout@v4

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
          cache: maven

      - name: Verify source and toolchain
        run: |
          test -z "$(git status --porcelain)"
          java -version
          javac -version
          ./mvnw -version
          git rev-parse HEAD

      - name: Build JAR and SBOM
        run: |
          ./mvnw -B -ntp \
            -Dsource.revision="$(git rev-parse HEAD)" \
            clean verify

      - name: Generate JAR provenance
        uses: actions/attest@v4
        with:
          subject-path: target/provenance-demo-1.0.0.jar

      - name: Generate SBOM attestation
        uses: actions/attest@v4
        with:
          subject-path: target/provenance-demo-1.0.0.jar
          sbom-path: target/bom.json

      - name: Publish build outputs
        uses: actions/upload-artifact@v4
        with:
          name: java-release
          path: |
            target/provenance-demo-1.0.0.jar
            target/bom.json
~~~

Đây là workflow minh họa; tên artifact, version, branch policy và release path cần khớp project thực tế. Trong môi trường production, pin các action theo commit SHA và kiểm tra workflow chỉ chạy từ tag/branch đã được bảo vệ.

Không dùng artifact từ job untrusted pull request để tạo release attestation. Release job nên build từ commit đã được phê duyệt trong môi trường CI có trust boundary rõ ràng.

## 19. Xác minh GitHub artifact attestation

Cài GitHub CLI và đăng nhập bằng identity có quyền đọc repository/attestation. Xác minh JAR:

~~~bash
gh attestation verify target/provenance-demo-1.0.0.jar \
  -R OWNER/REPOSITORY
~~~

Xác minh SBOM attestation gắn với cùng JAR:

~~~bash
gh attestation verify target/provenance-demo-1.0.0.jar \
  -R OWNER/REPOSITORY \
  --predicate-type https://cyclonedx.org/bom
~~~

Có thể xem predicate đã xác minh:

~~~bash
gh attestation verify target/provenance-demo-1.0.0.jar \
  -R OWNER/REPOSITORY \
  --format json
~~~

Consumer cần xác minh repository, workflow, source ref/commit, builder identity và subject digest theo policy của tổ chức. Một attestation hợp lệ nhưng được tạo bởi repository hoặc workflow không được phép vẫn phải bị từ chối.

Attestation verification cần chạy trên đúng file nhận được. Không xác minh một file khác rồi chỉ tin filename tương tự.

## 20. Kiểm tra SBOM và artifact có cùng release

Một quy trình release nên liên kết JAR và SBOM bằng digest.

Ví dụ file release directory:

~~~text
release/
  provenance-demo-1.0.0.jar
  bom.json
  SHA256SUMS
  provenance.sigstore.json
~~~

Checksum:

~~~bash
sha256sum provenance-demo-1.0.0.jar bom.json > SHA256SUMS
sha256sum -c SHA256SUMS
~~~

Trong thực tế, SBOM attestation nên nêu artifact subject và ký claim về file SBOM. Không chỉ ký SBOM độc lập mà bỏ qua liên kết tới artifact mà nó mô tả.

Nếu tạo SBOM sau khi JAR đã được shade, repackage hoặc sign, hãy chắc chắn SBOM mô tả đúng final artifact và dependency set của nó. Pipeline nên có một bước duy nhất xác định release artifact cuối cùng trước khi tính digest và attest.

## 21. Reproducible build và provenance

Reproducible build là khả năng tạo lại cùng artifact bytes từ cùng source và build inputs. Artifact provenance ghi lại inputs và builder để người khác có thể kiểm tra hoặc thử tái tạo build.

Hai khái niệm bổ sung cho nhau:

- Reproducibility kiểm tra output có thể được tạo lại hay không.
- Provenance giải thích output đã được tạo bằng source, tool và môi trường nào.
- Signature/attestation bảo vệ tính xác thực của claim và liên kết claim với artifact digest.

Với Maven, có thể dùng:

~~~xml
<properties>
  <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Giá trị timestamp phải ổn định giữa các lần build. Trong release pipeline, có thể lấy một timestamp ổn định từ source revision theo chính sách dự án.

Không nhúng build start time, random invocation ID hoặc dữ liệu thay đổi theo từng lần chạy vào JAR nếu mục tiêu là tạo artifact reproducible. Để thông tin invocation và thời gian trong provenance sidecar.

## 22. Ví dụ project Maven có manifest, SBOM và executable JAR

Cấu trúc:

~~~text
provenance-demo/
  pom.xml
  src/
    main/
      java/
        example/
          ProvenanceDemo.java
~~~

File \`ProvenanceDemo.java\`:

~~~java
package example;

import org.apache.commons.lang3.StringUtils;

public class ProvenanceDemo {
    public static void main(String[] args) {
        System.out.println("message=" + StringUtils.capitalize("artifact provenance"));
    }
}
~~~

POM ví dụ:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example.provenance</groupId>
  <artifactId>provenance-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    <source.revision>local-demo</source.revision>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.apache.commons</groupId>
      <artifactId>commons-lang3</artifactId>
      <version>3.17.0</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration>
          <release>17</release>
          <encoding>UTF-8</encoding>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
        <configuration>
          <archive>
            <manifest>
              <mainClass>example.ProvenanceDemo</mainClass>
            </manifest>
            <manifestEntries>
              <Implementation-Title>__DOLLAR__{project.groupId}:__DOLLAR__{project.artifactId}</Implementation-Title>
              <Implementation-Version>__DOLLAR__{project.version}</Implementation-Version>
              <Build-Revision>__DOLLAR__{source.revision}</Build-Revision>
              <Build-Jdk-Spec>17</Build-Jdk-Spec>
            </manifestEntries>
          </archive>
        </configuration>
      </plugin>

      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.6.0</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals>
              <goal>shade</goal>
            </goals>
            <configuration>
              <createDependencyReducedPom>false</createDependencyReducedPom>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <mainClass>example.ProvenanceDemo</mainClass>
                </transformer>
              </transformers>
            </configuration>
          </execution>
        </executions>
      </plugin>

      <plugin>
        <groupId>org.cyclonedx</groupId>
        <artifactId>cyclonedx-maven-plugin</artifactId>
        <version>2.9.3</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals>
              <goal>makeAggregateBom</goal>
            </goals>
          </execution>
        </executions>
        <configuration>
          <outputFormat>json</outputFormat>
          <outputName>bom</outputName>
          <includeTestScope>false</includeTestScope>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Trong release pipeline, truyền source commit thật qua \`-Dsource.revision\`. Giá trị mặc định \`local-demo\` chỉ để chạy ví dụ ở máy phát triển và không phải source identity đáng tin cậy.

## 23. Build, chạy và kiểm tra artifact

Build bằng Maven Wrapper:

~~~bash
./mvnw -B -ntp -Dsource.revision="$(git rev-parse HEAD)" clean verify
~~~

Chạy JAR:

~~~bash
java -jar target/provenance-demo-1.0.0.jar
~~~

Stdout:

~~~text
message=Artifact provenance
~~~

Kiểm tra manifest:

~~~bash
unzip -p target/provenance-demo-1.0.0.jar META-INF/MANIFEST.MF
~~~

Manifest có các entry như:

~~~text
Main-Class: example.ProvenanceDemo
Build-Jdk-Spec: 17
Build-Revision: <source-commit-sha>
Implementation-Title: example.provenance:provenance-demo
Implementation-Version: 1.0.0
~~~

Kiểm tra digest:

~~~bash
sha256sum target/provenance-demo-1.0.0.jar target/bom.json
~~~

Kiểm tra SBOM:

~~~bash
jq '{bomFormat, specVersion, component: .metadata.component, components}' target/bom.json
~~~

Build-Revision trong manifest hữu ích cho traceability nhưng có thể bị sửa cùng JAR. Nó không thay thế chữ ký hoặc provenance attestation do trusted builder phát hành.

## 24. Kết quả kiểm chứng project

Project mẫu đã được build trên Windows 11 bằng Maven 3.9.12, chạy trên Azul JDK 24.0.2 và biên dịch với release 17.

Kết quả:

~~~text
BUILD SUCCESS
message=Artifact provenance
bomFormat=CycloneDX
specVersion=1.6
component=provenance-demo:1.0.0
dependencyComponents=1
commons-lang3-present=True
~~~

Manifest ghi:

~~~text
Main-Class: example.ProvenanceDemo
Build-Jdk-Spec: 17
Build-Revision: 0123456789abcdef0123456789abcdef01234567
Implementation-Title: example.provenance:provenance-demo
Implementation-Version: 1.0.0
~~~

Đã chạy hai clean build với cùng source revision và cùng \`project.build.outputTimestamp\`. SHA-256 của JAR ở cả hai lần giống nhau:

~~~text
77e29ade3aad27f034aea9d9790dfaa8b52d50b35ed6807a344f9c7fc4365f9b
artifact.reproducible=True
~~~

Đây là kết quả của project demo và môi trường kiểm thử cụ thể. Nó chứng minh cấu hình mẫu tạo JAR ổn định trong lần kiểm tra này, không chứng minh mọi Maven project hoặc mọi máy đều reproducible.

CycloneDX plugin có in cảnh báo JSON schema validator về một số meta keyword không nhận diện, nhưng vẫn tạo BOM, validate output và kết thúc build thành công.

## 25. Phát hành artifact an toàn

Khi phát hành, hãy lưu artifact và metadata trong cùng một release record:

1. JAR/WAR hoặc container image.
2. SHA-256 digest.
3. SBOM tương ứng với artifact cuối cùng.
4. Build provenance attestation.
5. SBOM attestation nếu policy yêu cầu.
6. Release notes và source commit.
7. Build logs hoặc invocation ID cần thiết cho điều tra.

Dùng immutable release version và không ghi đè artifact đã phát hành. Nếu cần sửa lỗi, phát hành version mới và tạo provenance mới.

Với Maven repository, có thể deploy JAR, POM và SBOM classifier. Với container registry, attestation thường liên kết trực tiếp image digest. Dù dùng repository nào, consumer cần xác minh đúng digest của artifact nhận được.

Lưu attestation lâu ít nhất bằng thời gian artifact còn được sử dụng. Khi artifact đã được triển khai ở nhiều môi trường, provenance còn cần thiết cho vulnerability response và forensic investigation.

## 26. Xác minh provenance theo policy

Một verifier nên thực hiện các bước:

1. Tính SHA-256 của artifact nhận được.
2. Xác minh envelope/chữ ký của attestation.
3. Kiểm tra certificate, signer identity và OIDC issuer.
4. So sánh subject digest trong attestation với artifact.
5. Kiểm tra builder ID có nằm trong danh sách tin cậy.
6. Kiểm tra build type và workflow path.
7. Kiểm tra repository, ref và commit SHA được phép.
8. Kiểm tra build parameters không chứa giá trị ngoài policy.
9. Kiểm tra dependency/SBOM theo vulnerability và license policy.
10. Lưu kết quả verification để phục vụ audit.

Verifier không nên chấp nhận mọi builder chỉ vì signature hợp lệ. Policy phải xác định rõ signer-builder pair, repository, workflow và source branch/tag được phép.

Nếu attestation hợp lệ nhưng commit không nằm trong release được phê duyệt, artifact vẫn phải bị từ chối. Tương tự, artifact có SBOM đầy đủ nhưng chứa dependency bị cấm vẫn có thể không được phép triển khai.

## 27. Artifact provenance trong multi-module và container build

Với Maven multi-module, nên tạo aggregate SBOM ở root reactor và liên kết từng output với module coordinates/digest tương ứng. Một BOM tổng hợp không nên làm mất khả năng xác định artifact nào phụ thuộc component nào.

Với container build, provenance cần xác định image digest, base image digest, build context, Dockerfile hoặc build recipe, build args và platform/architecture. Tag image không đủ vì tag có thể thay đổi.

Nếu JAR được đóng gói vào container, có thể có hai lớp provenance:

- Provenance của JAR: source commit, Maven, JDK, dependency và compiler.
- Provenance của container: base image, Dockerfile, layers, build tool và image digest.

SBOM của JAR và SBOM của container có phạm vi khác nhau. SBOM container có thể bao gồm OS packages và runtime libraries mà SBOM Maven project không ghi nhận.

## 28. Những rủi ro thường gặp

| Sai lầm | Rủi ro | Cách xử lý |
|---|---|---|
| Chỉ phát hành SHA-256 | Attacker thay cả file và checksum. | Ký checksum hoặc dùng signed attestation. |
| Chỉ ký artifact | Không biết source và builder nào đã tạo file. | Kèm build provenance. |
| Tạo SBOM nhưng không gắn digest | Không chắc SBOM mô tả đúng artifact nào. | Attest SBOM với artifact subject và digest. |
| Dùng branch name làm source identity | Branch có thể thay đổi. | Ghi commit SHA bất biến. |
| Tin manifest Build-Revision | Manifest có thể sửa cùng JAR. | Xác minh signed provenance. |
| Dùng self-hosted runner không cô lập | Build trước có thể để lại trạng thái hoặc credential. | Runner ephemeral, least privilege và kiểm soát workspace. |
| Chấp nhận bất kỳ signer nào | Attacker có thể dùng identity khác để ký artifact. | Kiểm tra issuer và signer identity cụ thể. |
| Chấp nhận mọi builder ID | Provenance từ builder yếu có thể được tin nhầm. | Allowlist builder và signer-builder pair. |
| SBOM chỉ có compile dependencies | Bỏ sót test/build/native tools hoặc runtime packages. | Ghi rõ scope và tạo inventory bổ sung khi cần. |
| Ghi đè cùng Maven release version | Consumer không biết bytes nào là bản chính thức. | Immutable release và version mới khi thay đổi. |
| Đưa secret vào provenance | Lộ credential hoặc thông tin nội bộ. | Chỉ ghi parameter cần thiết và loại bỏ secret. |
| Tự ghi JSON rồi gọi đó là trusted provenance | Không có bảo đảm về builder hoặc chữ ký. | Dùng CI platform tạo và ký attestation. |

## 29. Điều tra sự cố bằng provenance

Khi một dependency có lỗ hổng hoặc artifact bị nghi ngờ:

1. Xác định artifact bằng SHA-256.
2. Lấy provenance và SBOM gắn với digest đó.
3. Kiểm tra repository, commit, workflow, builder và invocation ID.
4. Tìm version/PURL của dependency bị ảnh hưởng trong SBOM.
5. Xác định artifact/release/container nào chứa dependency đó.
6. So sánh với build trước và sau để tìm thay đổi.
7. Xác minh chữ ký và transparency record.
8. Thu thập build logs, dependency resolution và release history.
9. Rebuild từ source đã được phê duyệt nếu cần.
10. Phát hành version mới, SBOM mới và attestation mới.

Provenance giúp thu hẹp phạm vi điều tra. Nó không thay thế vulnerability scanning, code review, runtime monitoring hoặc incident response.

## 30. Checklist cho Java artifact release

- [ ] Artifact có Maven coordinates và version bất biến.
- [ ] Source repository URI và commit SHA được ghi nhận.
- [ ] Source tree sạch hoặc thay đổi được kiểm soát.
- [ ] JDK build JVM và compiler toolchain được ghi rõ.
- [ ] Maven/Gradle Wrapper và plugin versions được pin.
- [ ] Build image/base image digest được ghi nhận khi dùng container.
- [ ] Dependency tree được inventory bằng SBOM.
- [ ] SBOM schema, scope và root component đã được kiểm tra.
- [ ] SHA-256 được tính trên final artifact sau khi package/sign/shade.
- [ ] Provenance subject chứa digest của đúng artifact phát hành.
- [ ] Builder ID và signer identity nằm trong trust policy.
- [ ] Attestation envelope/chữ ký được xác minh.
- [ ] Repository, workflow, ref và commit được kiểm tra.
- [ ] SBOM attestation liên kết đúng artifact subject.
- [ ] Artifact và metadata được lưu ở nơi immutable.
- [ ] Không có secret trong manifest, SBOM, provenance hoặc logs.
- [ ] Consumer có thể xác minh lại artifact sau khi tải xuống.

## 31. Tài liệu tham khảo

- SLSA v1.2 — Build Provenance: https://slsa.dev/spec/v1.2/build-provenance
- SLSA — Verifying Artifacts: https://slsa.dev/spec/v1.2/verifying-artifacts
- in-toto Attestation Framework: https://github.com/in-toto/attestation
- CycloneDX Maven Plugin: https://cyclonedx.github.io/cyclonedx-maven-plugin/
- CycloneDX Maven Plugin source and schema support: https://github.com/CycloneDX/cyclonedx-maven-plugin
- GitHub — Artifact Attestations: https://docs.github.com/en/actions/concepts/security/artifact-attestations
- GitHub — Generate and verify build provenance: https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations
- Sigstore Cosign Quickstart: https://docs.sigstore.dev/quickstart/quickstart-cosign/
- Sigstore — Verifying Signatures: https://docs.sigstore.dev/cosign/verifying/verify/

Artifact provenance cho phép consumer truy ngược JAR về source, dependency, build workflow và builder. Để claim đó có giá trị bảo mật, hãy gắn artifact bằng digest, tạo attestation trên CI đáng tin, ký bằng identity có thể xác minh và kiểm tra policy trước khi triển khai.