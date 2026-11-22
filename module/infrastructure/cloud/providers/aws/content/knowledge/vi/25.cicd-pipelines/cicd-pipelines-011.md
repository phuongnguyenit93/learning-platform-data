# Quản lý artifact, chữ ký image và truy vết phiên bản phát hành

Một pipeline có thể build thành công, chạy đủ tests và deploy ứng dụng lên production, nhưng vẫn để lại những câu hỏi quan trọng: binary đang chạy được build từ commit nào, image có bị thay đổi sau khi scan không, ai đã ký image, signature có hợp lệ không, và có thể khôi phục đúng artifact của release trước hay không?

**Artifact management, image signing và release traceability** giúp trả lời các câu hỏi đó. Artifact cần được lưu trữ có kiểm soát và giữ nguyên nội dung sau build. Image cần được định danh bằng digest, có thể được ký bằng một identity đáng tin cậy và được xác minh trước khi triển khai. Release metadata cần nối source commit, build execution, test results, SBOM, provenance, signature, artifact digest và deployment record thành một chuỗi có thể audit.

Bài học thuộc chương **CI/CD trên AWS** của mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung kết hợp Amazon S3, Amazon ECR, AWS CodeBuild, AWS CodePipeline, AWS Signer, AWS KMS, AWS CloudTrail và các cơ chế triển khai ECS/EKS/Lambda để quản lý artifact an toàn, có khả năng truy vết và phục hồi.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt source artifact, build artifact, container image, deployment package, SBOM và provenance attestation.
2. Thiết kế artifact repository bằng S3, ECR và CodeArtifact với encryption, versioning, retention và least privilege.
3. Phân biệt image tag với immutable image digest và triển khai bằng digest.
4. Tạo release manifest nối source commit, build ID, artifact digest và deployment version.
5. Tạo SBOM theo SPDX hoặc CycloneDX và gắn SBOM với đúng artifact.
6. Giải thích chữ ký số, signing identity, trust store, signature verification và key lifecycle.
7. Sử dụng AWS Signer với Notation hoặc một giải pháp ký image tương thích như Cosign/AWS KMS.
8. Xác minh image signature trước khi deploy và tại Kubernetes admission boundary.
9. Phân biệt encryption-at-rest bằng KMS với signing để chứng minh integrity/provenance.
10. Promotion cùng một artifact qua dev, staging và production mà không rebuild.
11. Quản lý ECR replication, S3 Object Lock, lifecycle và rollback retention.
12. Audit release bằng CodePipeline, CodeBuild, CloudTrail, CloudWatch và deployment records.

## 2. Artifact trong quy trình CI/CD

**Artifact** là đầu ra được tạo hoặc sử dụng trong quá trình build/release. Mỗi loại artifact có mục đích và cách lưu trữ khác nhau.

| Loại artifact | Ví dụ | Nơi lưu phù hợp |
|---|---|---|
| Source snapshot | Source ZIP, Git commit tree | Git provider, CodePipeline source artifact |
| Java package | JAR/WAR | S3, CodeArtifact package repository hoặc artifact repository được quản lý |
| Container image | OCI/Docker image | Amazon ECR |
| IaC package | CloudFormation template, CDK synthesized template, SAM package | S3 artifact store |
| Test evidence | JUnit XML, coverage report, scan report | CodeBuild reports, S3 |
| SBOM | SPDX JSON, CycloneDX JSON | S3 hoặc OCI artifact/referrer trong registry |
| Provenance | in-toto/SLSA attestation, build metadata | S3 hoặc OCI artifact/referrer |
| Signature | Notation signature, Cosign signature | Registry/referrer hoặc signature service theo định dạng |
| Release manifest | JSON ghi digest, commit, build ID và môi trường | S3, release metadata store hoặc Git release record |

Artifact của pipeline và artifact được deploy không nhất thiết là cùng một file. CodePipeline có thể dùng ZIP làm input/output giữa actions, trong khi ECS chạy image từ ECR và Lambda chạy ZIP deployment package. Cần nối các artifact bằng digest/checksum và release manifest.

### 2.1. Build once, promote many times

Một nguyên tắc quan trọng là **build một lần, promote cùng artifact qua nhiều môi trường**:

1. Build từ source commit cụ thể.
2. Chạy tests, scan và tạo SBOM/provenance.
3. Publish artifact/image bất biến.
4. Ký artifact hoặc image.
5. Verify signature và policy trước khi deploy test.
6. Promote chính digest đó lên staging và production.
7. Chỉ thay environment configuration, secret references và IAM role.

Nếu rebuild ở mỗi môi trường, JAR/image có thể khác nhau do dependency resolution, build time, toolchain hoặc base image thay đổi. Khi đó kết quả staging không còn chứng minh chính xác artifact production.

~~~mermaid
flowchart TD
    SRC["Source commit"] --> BUILD["Isolated build"]
    BUILD --> TEST["Tests + security scans"]
    TEST --> SBOM["SBOM + provenance"]
    SBOM --> IMAGE["Immutable artifact / image digest"]
    IMAGE --> SIGN["Sign digest"]
    SIGN --> VERIFY["Verify signature + policy"]
    VERIFY --> DEV["Deploy dev"]
    DEV --> STAGE["Promote same digest to staging"]
    STAGE --> APPROVE["Release approval"]
    APPROVE --> PROD["Promote same digest to production"]
    PROD --> TRACE["Deployment record + audit trail"]
~~~

### 2.2. Artifact phải có owner và lifecycle

Mỗi artifact repository cần owner, retention period, access policy, encryption policy và quy trình xóa. Không giữ tất cả build artifacts vô thời hạn; cũng không xóa artifact còn được production hoặc rollback plan tham chiếu.

## 3. Định danh phiên bản: version, tag, digest và checksum

Một version label dễ đọc không nhất thiết là định danh nội dung bất biến.

| Định danh | Ví dụ | Đặc điểm |
|---|---|---|
| Semantic version | 2.4.1 | Dễ đọc, thể hiện release compatibility theo convention |
| Git commit SHA | 4f31c8... | Xác định source revision |
| Build ID | codebuild:orders-api:1842 | Xác định một lần build |
| Image tag | orders-api:2.4.1 | Nhãn tra cứu; có thể mutable nếu registry cho phép |
| Image digest | sha256:... | Hash của image manifest; xác định chính xác nội dung |
| File checksum | SHA-256 của JAR/ZIP | Kiểm tra file có thay đổi hay không |

### 3.1. Tag không phải digest

Ví dụ:

~~~text
444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:2.4.1
~~~

Đây là image tag. Nếu tag mutable, một lần push sau có thể làm tag trỏ sang image khác. URI dùng digest:

~~~text
444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api@sha256:0123456789abcdef...
~~~

Digest xác định manifest bytes và là định danh nên dùng cho deployment, signature verification và release records. Nếu image manifest thay đổi, digest cũng thay đổi.

### 3.2. Tag strategy

Một repository có thể dùng:

- Version tag: 2.4.1.
- Commit tag: sha-4f31c8a.
- Build tag: build-1842.
- Environment label: production chỉ để tra cứu, không dùng làm deployment identity.

Không nên dùng latest làm version duy nhất. Tag production hoặc stable có thể được cập nhật để tiện tra cứu, nhưng deployment manifest cần pin digest cụ thể.

### 3.3. Semantic version và commit identity

Semantic version thường có dạng MAJOR.MINOR.PATCH:

- MAJOR: thay đổi có thể phá vỡ compatibility.
- MINOR: thêm functionality tương thích ngược.
- PATCH: sửa lỗi tương thích ngược.

Semantic version là quy ước release, không tự chứng minh source hoặc artifact. Gắn version với commit SHA, build ID và digest để có identity đầy đủ.

### 3.4. Kiểm tra checksum cho JAR/ZIP

Tạo checksum sau khi build:

~~~bash
sha256sum target/orders-api.jar > target/orders-api.jar.sha256
cat target/orders-api.jar.sha256
~~~

Xác minh khi tải artifact:

~~~bash
sha256sum --check orders-api.jar.sha256
~~~

Checksum giúp phát hiện nội dung file thay đổi so với checksum đã lưu. Nếu attacker có thể thay cả artifact và checksum cùng lúc, checksum không chứng minh nguồn gốc đáng tin cậy. Để chứng minh provenance, cần chữ ký số hoặc attestation được xác minh bằng trust policy độc lập.

## 4. Lưu trữ artifact trên Amazon S3

Amazon S3 thường lưu CodePipeline artifacts, Lambda deployment packages, IaC templates, test reports, SBOM, provenance và release manifests.

### 4.1. Thiết kế artifact bucket

Một artifact bucket production nên:

- Block Public Access ở account/bucket.
- Bật versioning để hỗ trợ recovery và audit.
- Mã hóa mặc định bằng SSE-KMS khi yêu cầu key ownership/audit rõ.
- Bucket policy giới hạn CodePipeline/CodeBuild/deploy roles và accounts cần thiết.
- Bật logging/audit phù hợp.
- Dùng lifecycle policies để quản lý noncurrent versions và temporary artifacts.
- Bật Object Lock khi có yêu cầu WORM/compliance và đã thiết kế retention.
- Phân tách release artifacts với build scratch/intermediate files.

### 4.2. SSE-S3 và SSE-KMS

| Cơ chế | Ý nghĩa | Khi chọn |
|---|---|---|
| SSE-S3 | S3 quản lý encryption keys | Nhu cầu encryption-at-rest cơ bản |
| SSE-KMS | Mã hóa qua AWS KMS key | Cần key policy, audit, cross-account control hoặc customer-managed key |
| DSSE-KMS | Dual-layer server-side encryption bằng KMS theo hỗ trợ | Yêu cầu bảo vệ dữ liệu đặc thù/compliance |

Encryption-at-rest bảo vệ nội dung lưu trữ theo mô hình kiểm soát key. Nó **không chứng minh ai đã build artifact**, không thay signature và không bảo đảm artifact không bị overwrite bởi principal có quyền ghi.

### 4.3. S3 versioning và object key

Đặt key có cấu trúc:

~~~text
releases/orders-api/2.4.1/orders-api.jar
releases/orders-api/2.4.1/orders-api.jar.sha256
releases/orders-api/2.4.1/sbom.cdx.json
releases/orders-api/2.4.1/provenance.intoto.jsonl
releases/orders-api/2.4.1/release-manifest.json
~~~

Không dùng cùng key để ghi đè artifact release đã công bố. S3 versioning cho phép lưu nhiều object versions, nhưng người tiêu thụ vẫn có thể lấy latest version nếu không pin VersionId. Release manifest nên ghi object key, version ID khi phù hợp và SHA-256.

### 4.4. S3 Object Lock

S3 Object Lock cung cấp WORM retention với governance hoặc compliance mode và legal hold. Bucket phải bật versioning. Governance mode cho phép principal có quyền đặc biệt bypass retention; compliance mode có ràng buộc chặt hơn và không thể xóa/ghi đè version trước khi hết retention.

Dùng Object Lock cho release evidence/audit archives khi yêu cầu lưu giữ bất biến. Không bật retention dài hạn tùy tiện cho mọi build output; nó có thể làm tăng chi phí và khiến cleanup không thể thực hiện trong thời gian giữ.

### 4.5. Cross-account và cross-Region artifact access

Khi pipeline chạy nhiều accounts/Regions, kiểm tra đồng thời:

- S3 bucket policy cho principal đích.
- KMS key policy/grants cho encrypt/decrypt.
- IAM permissions của pipeline/action role.
- Artifact store đúng Region cho actions.
- Data transfer và replication costs.
- Version ID/checksum sau khi copy.

S3 replication không thay thế kiểm tra integrity/provenance. Sau khi copy, verify checksum và signature ở destination account/Region.

## 5. Amazon ECR: quản lý container images

Amazon Elastic Container Registry (ECR) là registry lưu OCI/Docker images và các image artifacts liên quan. ECR hỗ trợ private repositories, repository policies, image tag mutability, lifecycle policies, scanning và replication.

### 5.1. Repository strategy

Có thể tổ chức repository theo service:

~~~text
orders-api
payments-api
inventory-worker
notification-service
~~~

Hoặc phân tách theo môi trường/account nếu yêu cầu access boundary khác nhau. Tránh tạo quá nhiều repositories theo từng commit; dùng tag/digest để quản lý versions.

### 5.2. Bật tag immutability

Tag immutability ngăn một tag đã tồn tại bị overwrite bằng image khác. Đây là guardrail hữu ích cho release tags như version hoặc commit SHA.

Ví dụ tạo repository với immutable tags:

~~~bash
aws ecr create-repository \
  --repository-name orders-api \
  --image-tag-mutability IMMUTABLE \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256 \
  --region ap-southeast-1
~~~

Ví dụ này dùng AES256 encryption option của ECR; nếu cần customer-managed KMS key, chọn KMS encryption configuration và cấp key permissions tương ứng. Repository đã tồn tại thì dùng update-repository hoặc cấu hình qua IaC. Scan-on-push chỉ là một cấu hình scanning; kiểm tra ECR scanning mode và Amazon Inspector coverage theo yêu cầu.

Tag immutability không thay digest pinning và không ngăn image bị xóa bởi IAM principal hoặc lifecycle policy. Khi dùng image signing, kiểm tra behavior của signing mode/OCI reference format đang triển khai. ECR hiện có managed signing và manual signing; với registry/signing integration cũ, có thể có giới hạn về tag immutability. Production deployment luôn nên dùng digest.

Lưu ý về tương thích: tài liệu AWS đời trước cho luồng signature dựa trên OCI 1.0 có ghi nhận hạn chế với tag immutability. ECR hiện hỗ trợ OCI 1.1 reference types và managed signing. Khi chọn manual signing hoặc phiên bản Notation/plugin cụ thể, kiểm thử tag immutability cùng signature flow trên repository test trước khi áp dụng production.

### 5.3. Login và push image

~~~bash
aws ecr get-login-password --region ap-southeast-1 |
  docker login --username AWS --password-stdin 444455556666.dkr.ecr.ap-southeast-1.amazonaws.com

docker build -t orders-api:2.4.1 .
docker tag orders-api:2.4.1 444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:2.4.1
docker push 444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:2.4.1
~~~

Đăng nhập vào registry hostname, không phải repository URI. Trong CodeBuild, role cần ECR authorization token và các upload actions trên repository; không lưu Docker password trong buildspec.

### 5.4. Lấy digest sau khi push

~~~bash
aws ecr describe-images \
  --repository-name orders-api \
  --image-ids imageTag=2.4.1 \
  --region ap-southeast-1 \
  --query 'imageDetails[0].{Digest:imageDigest,Tags:imageTags,PushedAt:imagePushedAt}' \
  --output json
~~~

Lưu imageDigest trả về vào release manifest và deployment input. Nếu image có multi-architecture manifest list, digest của manifest list là định danh image được tham chiếu; cần hiểu platform-specific child manifests khi kiểm tra runtime.

### 5.5. Tag immutability và digest cùng nhau

Tag immutability giúp ngăn overwrite một tag; digest pinning giúp consumer tham chiếu nội dung cụ thể. Dùng cả hai:

- Release tag bất biến để người vận hành tra cứu.
- Digest trong task definition/Kubernetes manifest để deploy.
- Signature/attestation gắn với digest.
- Release manifest nối digest với source/build/test evidence.

Tag immutability không ngăn image bị xóa bởi principal có quyền xóa hoặc lifecycle policy. IAM/repository policy và retention vẫn cần thiết.

### 5.6. ECR lifecycle policies

Lifecycle policy có thể expire untagged images hoặc images cũ theo tag prefixes/age/count. Cần bảo vệ:

- Release tags đang được production sử dụng.
- Digests được rollback plan tham chiếu.
- Images có signature/SBOM/provenance cần audit.
- Base images đang được downstream builds sử dụng.

Trước khi áp dụng lifecycle policy, dùng preview và kiểm tra rules priority/tag status. Một policy sai có thể xóa image cần phục hồi production.

### 5.7. ECR replication

ECR replication có thể sao chép images giữa repositories, accounts hoặc Regions theo cấu hình. Dùng replication để đưa image tới deployment account/Region mà không rebuild.

Sau replication:

1. Xác minh repository đích và digest.
2. Xác minh tag mapping và image manifest.
3. Kiểm tra signature/OCI referrers có sẵn ở destination.
4. Nếu signature artifact không được chuyển theo cách registry/client mong đợi, thực hiện copy/reattach/re-sign theo quy trình có provenance.
5. Xác minh trust policy và verification tại destination trước deploy.

Không giả định replication image đồng nghĩa mọi external SBOM/provenance objects và trust configuration cũng được replicate.

### 5.8. Signature artifacts và quota/lifecycle

Signature được lưu trong ECR repository cũng tiêu thụ quota số images/artifacts của repository. Khi subject image bị xóa bởi lifecycle policy, ECR có thể tự dọn các reference artifacts liên quan trong vòng 24 giờ theo behavior của ECR. Vì vậy:

- Tính signature artifacts vào repository quota.
- Không xóa subject image nếu cần giữ signature để verify/rollback.
- Thiết kế lifecycle theo subject image và rollback retention.
- Nếu lưu SBOM/provenance ngoài ECR, áp dụng retention độc lập cho các evidence objects đó.

## 6. AWS CodeArtifact cho package dependencies

CodeArtifact là package repository service hỗ trợ các formats như Maven, npm, PyPI, NuGet và Swift theo tài liệu dịch vụ. Với ứng dụng Java, CodeArtifact có thể proxy public Maven repositories và lưu internal libraries.

### 6.1. Tách dependency package khỏi release image

CodeArtifact lưu package inputs của build, ví dụ internal Java SDK; ECR lưu container image được deploy. S3 có thể lưu JAR, SBOM, reports và release metadata. Mỗi repository có IAM access và retention policy riêng.

### 6.2. Maven settings và authentication

CodeArtifact có thể cấp Maven repository endpoint và authorization token. Build role cần quyền đọc package repository và lấy token. Token có thời hạn; dùng CLI/credential helper hoặc cơ chế tự refresh trong build environment thay vì hard-code token trong settings.xml.

### 6.3. Dependency pinning

- Pin dependency versions trong pom.xml/Gradle build.
- Kiểm soát repositories và upstream sources.
- Không dùng dynamic versions/SNAPSHOT trong release production nếu không có quy trình rõ.
- Scan dependencies và lưu SBOM.
- Tách quyền publish package khỏi quyền read dependency.

CodeArtifact giúp kiểm soát nguồn packages nhưng không tự chứng minh dependency an toàn. Vẫn cần SCA, signature/provenance khi có, license review và vulnerability policy.

## 7. Software Bill of Materials (SBOM)

**SBOM** là danh sách có cấu trúc các components trong một phần mềm: libraries, modules, package versions và metadata liên quan. SBOM giúp xác định ứng dụng có dùng dependency bị ảnh hưởng bởi CVE hoặc license issue hay không.

### 7.1. Các định dạng phổ biến

| Format | Đặc điểm | Use case |
|---|---|---|
| SPDX | Chuẩn ISO/IEC cho software package/component/license metadata | License compliance, inventory và supply chain |
| CycloneDX | Chuẩn SBOM tập trung software/hardware components và vulnerability-related data | Dependency inventory, security analysis |

Chọn một format làm canonical output cho release, hoặc tạo cả hai khi consumers yêu cầu. Ghi rõ format version/tool version để parser có thể xử lý chính xác.

### 7.2. Tạo SBOM cho Java

Ví dụ Maven CycloneDX plugin:

~~~xml
<plugin>
  <groupId>org.cyclonedx</groupId>
  <artifactId>cyclonedx-maven-plugin</artifactId>
  <version>2.9.1</version>
  <executions>
    <execution>
      <phase>package</phase>
      <goals>
        <goal>makeAggregateBom</goal>
      </goals>
    </execution>
  </executions>
</plugin>
~~~

Ví dụ plugin version chỉ để minh họa; chọn version đã được tổ chức kiểm duyệt và pin trong build. Tạo BOM:

~~~bash
mvn -B clean verify
mvn -B cyclonedx:makeAggregateBom
~~~

File thường được tạo trong target, ví dụ bom.json hoặc bom.xml tùy plugin configuration. Xác minh output thực tế và bảo đảm BOM mô tả đúng artifact/package được release, không chỉ source dependencies chưa được package.

### 7.3. Tạo SBOM cho container image

Có thể dùng Syft hoặc công cụ SBOM đã được duyệt để scan image theo digest:

~~~bash
syft 444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api@sha256:REPLACE_WITH_DIGEST \
  -o cyclonedx-json=orders-api.cdx.json
~~~

Digest là placeholder. Gắn SBOM với đúng image digest, không chỉ tag. Nếu image được rebuild/rebase, tạo SBOM mới vì operating system packages và layers có thể thay đổi.

### 7.4. SBOM không phải security scan

SBOM mô tả thành phần; nó không tự khẳng định các thành phần không có vulnerabilities. Dùng SBOM làm input cho vulnerability scanners, license analysis và incident response. Một SBOM có thể hợp lệ về schema nhưng thiếu components nếu scanner không phân tích được layer/runtime dependencies.

### 7.5. Gắn SBOM với artifact

Lưu:

- Subject digest của image/package.
- SBOM format/version.
- Tool và tool version đã tạo.
- Source commit/build ID.
- Timestamp.
- SBOM file digest.

Có thể lưu SBOM trong S3 với release manifest hoặc publish như OCI artifact/referrer cạnh image nếu registry/client hỗ trợ. Consumer phải kiểm tra subject digest để không đọc nhầm SBOM của image tag khác.

## 8. Build provenance và attestations

**Provenance** ghi lại artifact được tạo ra như thế nào: source repository/revision, builder identity, build invocation, materials/dependencies và output digest. Attestation là statement có cấu trúc được ký hoặc bảo vệ integrity để consumer xác minh.

### 8.1. SBOM và provenance khác nhau

| | SBOM | Provenance |
|---|---|---|
| Câu hỏi | Artifact chứa những components nào? | Artifact được build từ đâu và bằng quy trình nào? |
| Dữ liệu | Package/component/version/license | Source, builder, invocation, materials, output digest |
| Người dùng | Security, license, incident response | Release engineering, platform security, compliance |
| Liên kết | Subject artifact digest | Subject artifact digest |

Hai tài liệu bổ sung cho nhau. SBOM không chứng minh build pipeline đáng tin cậy; provenance không thay việc phân tích vulnerability/license.

### 8.2. Provenance cần ghi gì?

- Source repository URL và immutable commit SHA.
- Build system/project/pipeline identity.
- Build execution ID và invocation parameters đã lọc secret.
- Builder image/toolchain versions.
- Dependency/material references và checksums.
- Output artifact digest.
- Timestamp và build environment metadata.
- Test/scan evidence references.

Không đưa secrets, access tokens, private environment variables hoặc dữ liệu khách hàng vào attestation.

### 8.3. SLSA và in-toto

SLSA (Supply-chain Levels for Software Artifacts) cung cấp framework đánh giá mức độ bảo đảm supply chain. in-toto cung cấp mô hình metadata/attestation cho steps và materials. Có thể tạo provenance theo SLSA/in-toto formats và ký attestation bằng trusted signing identity.

Không tự tuyên bố đạt một SLSA level chỉ vì có JSON provenance. Mức bảo đảm phụ thuộc builder isolation, source controls, build service identity, tamper resistance, reproducibility và verification policy theo yêu cầu level.

### 8.4. Release manifest

Release manifest nối artifact với bằng chứng build:

~~~json
{
  "schemaVersion": "1.0",
  "service": "orders-api",
  "releaseVersion": "2.4.1",
  "source": {
    "repository": "https://github.com/example-org/orders-api",
    "commit": "4f31c8a0123456789abcdef0123456789abcdef01"
  },
  "build": {
    "provider": "AWS CodeBuild",
    "project": "orders-api-release",
    "buildId": "orders-api-release:1842"
  },
  "artifact": {
    "type": "oci-image",
    "uri": "444455556666.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api",
    "digest": "sha256:REPLACE_WITH_REAL_DIGEST"
  },
  "evidence": {
    "sbom": "s3://orders-release-evidence/releases/2.4.1/sbom.cdx.json",
    "provenance": "s3://orders-release-evidence/releases/2.4.1/provenance.intoto.jsonl"
  }
}
~~~

Các giá trị là placeholder. Trong release thật, digest phải là digest thực tế; object keys phải trỏ đến evidence đã upload và checksum của evidence nên được ghi trong manifest/attestation. Manifest không tự đáng tin cậy nếu không được ký hoặc bảo vệ integrity.

## 9. Chữ ký số cho container images

Image signature giúp consumer kiểm tra image được ký bởi identity mà tổ chức tin cậy và nội dung được ký không bị thay đổi. Signature thường gắn với image digest, không phải một tag mutable.

### 9.1. Signature chứng minh điều gì?

Khi verification thành công, consumer có thể xác minh:

- Signature hợp lệ theo thuật toán và trust chain.
- Signature bao phủ đúng digest được yêu cầu.
- Signer certificate/profile được trust policy chấp nhận.
- Signature đáp ứng policy về signer, repository và thời gian theo cấu hình.

Signature **không tự chứng minh** source code an toàn, tests đã pass, SBOM đầy đủ hoặc build environment không bị compromise. Những điều đó cần provenance, test evidence, scanner và build controls.

### 9.2. Vì sao ký digest thay vì tag?

Tag có thể thay đổi để trỏ tới image khác. Digest là content-addressable identifier của manifest. Nếu ký tag mutable, consumer có thể lấy nội dung khác với nội dung mà signer đã xem xét. Pipeline cần resolve tag thành digest, ký digest và deploy đúng digest đó.

### 9.3. Signing và encryption là hai cơ chế khác nhau

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| Encryption | Bảo mật nội dung khỏi người không có key | ECR/S3 encryption, SSE-KMS |
| Hash/checksum | Phát hiện nội dung khác với digest đã biết | SHA-256 |
| Digital signature | Xác minh integrity và signing identity | AWS Signer + Notation |
| Provenance attestation | Mô tả source/builder/materials/output | in-toto/SLSA |
| SBOM | Liệt kê components | SPDX/CycloneDX |

KMS key dùng mã hóa artifact không tự động là signing key. Nếu dùng KMS asymmetric key để ký bằng Cosign, phải cấu hình signing workflow, key usage và verification tương ứng.

## 10. AWS Signer và Notation

AWS Signer là managed code-signing service. Với container images, AWS Signer có thể tích hợp với **Notation** thông qua Notation plugin của AWS Signer. Notation là công cụ ký và xác minh OCI artifacts theo mô hình trust store/trust policy.

### 10.1. Thành phần trong luồng ký

| Thành phần | Vai trò |
|---|---|
| AWS Signer signing profile | Cấu hình profile dùng để ký |
| AWS Signer plugin for Notation | Kết nối Notation CLI với AWS Signer |
| Notation CLI | Ký và verify OCI image/signature |
| ECR repository | Lưu image và signature artifacts/referrers theo hỗ trợ registry |
| Trust store | Lưu certificate chain/trust anchors mà verifier tin cậy |
| Trust policy | Quy định signer/identity và verification requirements |
| CI signing role | Quyền gọi signing profile theo least privilege |
| Deployment verifier | Kiểm tra signature trước khi cho phép image chạy |

### 10.2. Signing profile và signer identity

Tạo signing profile theo quy trình tổ chức và chọn platform phù hợp với Notation/OCI image signing. Signing profile xác định signing identity/certificate và validity period theo cấu hình AWS Signer. Quyền sử dụng profile cần được giới hạn cho pipeline signing role được phê duyệt.

Không cho mọi developer hoặc mọi CodeBuild project quyền ký production image. Tách build/test role khỏi signing role để chỉ artifact vượt qua required gates mới được ký.

### 10.2.1. ECR managed signing

Amazon ECR hiện hỗ trợ **managed signing**, được AWS khuyến nghị cho đa số trường hợp. Khi signing configuration được thiết lập cho private registry, ECR tự động tạo signature bằng AWS Signer khi image được push. Signing configuration tham chiếu một hoặc nhiều signing profiles và có thể lọc repositories bằng tên/pattern.

Đặc điểm cần nhớ:

- Cấu hình managed signing ở cấp private registry, không cần cài Notation plugin trong mỗi build job chỉ để ký.
- Có thể tạo nhiều signing rules để giới hạn repository nào được ký bằng profile nào.
- Principal push image cần ECR upload permissions và signer:SignPayload trên signing profile phù hợp.
- ECR managed signing dùng identity của principal thực hiện push image làm signing identity cho operation.
- Signing profile phải ở cùng Region với ECR registry; managed signing hỗ trợ cross-account signing theo cấu hình/trust phù hợp.
- Managed signing ký image khi push; pipeline vẫn phải scan/verify và chặn deployment nếu quality gates không đạt.

Ví dụ signing configuration:

~~~json
{
  "rules": [
    {
      "signingProfileArn": "arn:aws:signer:ap-southeast-1:444455556666:/signing-profiles/orders-image-profile",
      "repositoryFilters": [
        {
          "filter": "orders-*",
          "filterType": "WILDCARD_MATCH"
        }
      ]
    }
  ]
}
~~~

Áp dụng cấu hình:

~~~bash
aws ecr put-signing-configuration \
  --region ap-southeast-1 \
  --signing-configuration file://signing-config.json

aws ecr get-signing-configuration --region ap-southeast-1
~~~

Tên profile, account và filter là ví dụ. Trước khi áp dụng, review rule scope và permissions; signing configuration có thể ảnh hưởng mọi repository khớp filter trong registry.

Managed signing không đồng nghĩa image đã pass vulnerability scan hoặc approval. Nếu policy yêu cầu chỉ ký sau khi scan hoàn tất, dùng manual signing sau quality gates hoặc thiết kế pipeline gate bổ sung; không cho deployment chỉ vì ECR đã tạo signature.

### 10.2.2. ECR manual signing

Manual signing dùng Notation CLI và AWS Signer plugin để ký image đã tồn tại trong ECR. Chọn cách này khi cần điều khiển thời điểm ký, ví dụ sau khi scan, SBOM và approval đã pass. Manual signing cần client tools, registry authentication, signer permissions và ECR permissions.

### 10.3. Cài Notation và AWS Signer plugin

Cài Notation CLI và AWS Signer Notation plugin theo hướng dẫn release chính thức. Pin version của CLI/plugin trong build image hoặc tool container; không tải binary/plugin không kiểm chứng trong mỗi build. Xác minh plugin được cài và phiên bản đúng trước khi ký.

Ví dụ kiểm tra:

~~~bash
notation version
notation plugin ls
~~~

Tên plugin và installation method phụ thuộc release được AWS hỗ trợ. Dùng đúng package/checksum/release artifact từ tài liệu AWS Signer; không giả định plugin có sẵn trên mọi CodeBuild image.

### 10.4. Ký image với Notation

Ví dụ lệnh minh họa sau khi plugin và signing profile đã được cấu hình:

~~~bash
aws ecr get-login-password --region "$AWS_REGION" |
  notation login --username AWS --password-stdin "$ECR_REGISTRY"

notation sign "$IMAGE_URI" \
  --plugin com.amazonaws.signer.notation.plugin \
  --id "$SIGNING_PROFILE_ARN"
~~~

IMAGE_URI phải trỏ tới image digest đã push vào registry; SIGNING_PROFILE_ARN là profile được phê duyệt; ECR_REGISTRY là registry hostname. Notation cần registry credentials để push signature và đọc image khi verify. Có thể dùng ECR Docker credential helper thay cho lệnh notation login nếu đã cấu hình helper đúng. Không ký mutable tag rồi sau đó rebuild hoặc retag nội dung khác.

### 10.5. Signature lưu ở registry

Notation tạo signature artifact gắn với subject image theo OCI artifact/referrer model. Registry cần hỗ trợ lưu và trả về signature artifacts. Amazon ECR hỗ trợ OCI 1.1 reference artifacts/referrers; ECR replication hỗ trợ sao chép referrers cùng images khi luồng và cấu hình tương thích.

Sau replication, vẫn phải kiểm tra signature/referrer ở destination repository và chạy verify trong account/Region đích. Khi dùng registry hoặc công cụ copy khác ECR replication, xác minh signature được chuyển theo; nếu thiếu thì re-publish/copy signature theo quy trình, không bỏ qua verification.

### 10.6. Trust store và trust policy

Verifier cần trust anchor/certificate chain và policy xác định signer nào được chấp nhận. Trust policy có thể giới hạn registry/repository scope và signer identity. Không dùng một trust policy chấp nhận mọi signer cho mọi production repository.

Trust configuration là một phần của deployment security policy; version hóa và review thay đổi trust roots/policy như code.

### 10.7. Verify image

Ví dụ:

~~~bash
notation verify "$IMAGE_URI"
~~~

IMAGE_URI nên là digest reference. Lệnh verify sử dụng trust store/trust policy được cấu hình trong Notation environment. Nếu verification thất bại, pipeline phải dừng deployment và lưu error reason; không bypass signature check bằng một flag tùy tiện trong production.

### 10.8. AWS Signer và CodeBuild IAM

CodeBuild signing role chỉ cần quyền AWS Signer phù hợp với plugin/API workflow và quyền truy cập ECR image/referrer. ECR read/write permissions cũng cần scope theo repository. Kiểm tra plugin documentation để cấp actions chính xác; không gán signer:* hoặc ecr:* trên toàn account nếu chỉ ký một repository.

## 11. Cosign và AWS KMS như một lựa chọn khác

Cosign là công cụ thuộc hệ sinh thái Sigstore, hỗ trợ ký container images và attestations. Cosign có thể sử dụng AWS KMS asymmetric keys làm signing backend.

### 11.1. Khi chọn Cosign

Cosign phù hợp khi tổ chức đã có policy/tooling dựa trên Sigstore, cần ký/verify image và attestations theo định dạng Cosign, hoặc muốn tích hợp với admission controllers hỗ trợ Cosign. AWS Signer + Notation phù hợp khi muốn dùng managed signing profile và Notation OCI workflow của AWS.

Không trộn hai signature formats mà không định nghĩa verifier/trust policy cho từng format. Consumer phải biết cách xác minh đúng signature type.

### 11.2. Ký bằng AWS KMS

Cosign hỗ trợ KMS URI cho AWS KMS asymmetric key. Ví dụ cú pháp minh họa:

~~~bash
cosign sign \
  --key "awskms://arn:aws:kms:ap-southeast-1:444455556666:key/REPLACE_WITH_KEY_ID" \
  "$IMAGE_URI"
~~~

Thay ARN bằng asymmetric KMS key có key usage phù hợp cho signing; image URI phải pin digest. Xác minh bằng public key/KMS-aware verification configuration theo version Cosign đang dùng. Cú pháp KMS URI và algorithm support cần đối chiếu tài liệu Cosign/AWS KMS hiện hành.

### 11.3. KMS key policy và separation of duties

- Signing role được phép ký bằng đúng key ARN.
- Verification systems có quyền đọc public key/metadata cần thiết.
- Key administrators không đồng nghĩa với release approvers.
- Key deletion/disable actions cần controls và audit.
- Rotation/replacement key cần trust policy chấp nhận cả signature cũ trong retention window nếu còn cần verify.

KMS key dùng cho signature không nên dùng chung tùy tiện với S3 encryption key. Tách key purpose giúp giảm blast radius và làm policy rõ hơn.

## 12. Verify signature ở đâu?

Signature chỉ có tác dụng khi có bước verification trước khi artifact được tin cậy.

### 12.1. Verify trong pipeline

Pipeline có thể verify sau signing và trước khi deploy:

1. Resolve release image digest.
2. Tìm signature/referrer của digest.
3. Verify certificate chain/trust policy.
4. Verify signer identity và repository scope.
5. Verify SBOM/provenance attestation nếu policy yêu cầu.
6. Chỉ khi tất cả required checks pass mới cho phép deployment action chạy.

### 12.2. Verify tại deployment boundary

| Runtime | Cách enforcement thường dùng |
|---|---|
| ECS | CodePipeline/CodeDeploy pre-deploy verification action hoặc deployment wrapper kiểm tra digest/signature trước khi cập nhật task definition |
| EKS | Admission controller/policy engine verify image signature trước khi Pod được tạo |
| Lambda container image | Verify image/signature trong release pipeline trước khi update function; Lambda execution không tự thay thế release verification |
| EC2/container host | Deployment agent/orchestrator verify trước khi pull/run image theo policy của nền tảng |

Không giả định ECS hoặc Lambda tự động reject mọi unsigned images chỉ vì image nằm trong ECR. Cần thiết kế enforcement point phù hợp.

### 12.3. EKS admission policy

Trên EKS, admission controller như Kyverno có thể verify image signatures/attestations theo version và plugin support. Admission policy nên:

- Yêu cầu image tham chiếu bằng digest hoặc enforce digest resolution.
- Giới hạn registry/repository được phép.
- Chấp nhận signer identity/trust roots đã duyệt.
- Yêu cầu attestation/SBOM policy khi phù hợp.
- Chặn unsigned/untrusted images ở production namespaces.
- Có audit mode/test namespace trước khi chuyển sang enforce mode.

Policy ví dụ phụ thuộc Kyverno version và signature format; không áp dụng manifest chung mà chưa kiểm thử trên cluster.

### 12.4. Fail closed hay fail open?

Với production workloads có yêu cầu supply-chain assurance, verification failure thường phải fail closed: không deploy image. Trong môi trường migration, có thể chạy audit-only trong thời gian ngắn, có owner/expiry và scope rõ. Không để exception vĩnh viễn làm mất ý nghĩa của signing policy.

## 13. Lambda code signing cho deployment packages

Với Lambda ZIP deployment packages, AWS có cơ chế **Lambda Code Signing** tích hợp AWS Signer. Đây là luồng ký code package, khác với Notation image signing cho OCI container images.

### 13.1. Code signing configuration

Lambda code signing configuration chỉ định signing profiles được tin cậy và policy xử lý package không hợp lệ:

- **Warn:** ghi nhận lỗi validation nhưng cho phép deployment tiếp tục theo behavior cấu hình.
- **Enforce:** từ chối deployment package không đáp ứng validation.

Production nên dùng Enforce khi signing workflow đã được triển khai và kiểm thử. Nếu dùng Warn trong migration, đặt thời hạn chuyển sang Enforce.

### 13.2. Phân biệt ba luồng

| Artifact | Signing approach | Verification boundary |
|---|---|---|
| Container image trên ECR | AWS Signer + Notation hoặc Cosign/KMS | Pipeline, EKS admission hoặc deployment wrapper |
| Lambda ZIP package | AWS Signer Lambda code signing | Lambda code signing configuration |
| JAR/WAR lưu ở S3 | JAR signing/checksum/provenance theo toolchain | Pipeline/deployment agent/application packaging |

Không dùng Lambda code signing configuration để giả định ECR container image đã được ký. Chọn signing format và enforcement mechanism phù hợp với artifact type.

## 14. Pipeline end-to-end: build, evidence, sign và publish

Một pipeline có thể chia thành các stages sau:

| Stage | Hành động | Output |
|---|---|---|
| Source | Checkout immutable commit | Source revision |
| Build | Compile/package/container build | JAR/image |
| Test | Unit/integration/contract tests | Test reports |
| Scan | SCA/SAST/container/IaC/secret scan | Scan reports |
| SBOM | Generate SPDX/CycloneDX | SBOM tied to digest |
| Provenance | Record builder/source/materials | Provenance attestation |
| Publish | Push image/publish package/upload S3 artifact | Immutable artifact digest |
| Sign | Sign exact digest | Signature/referrer |
| Verify | Verify signature, provenance and policy | Verification evidence |
| Promote | Deploy same digest to environments | Deployment record |

### 14.1. Thứ tự ký

Ký sau khi artifact hoàn chỉnh và sau các gates bắt buộc:

1. Build final image.
2. Push image để registry tạo digest.
3. Scan image theo digest.
4. Tạo SBOM và provenance cho digest.
5. Ký digest và/hoặc ký attestation.
6. Verify signature và evidence.
7. Publish release manifest đã gắn digest/evidence.
8. Deploy.

Nếu thay đổi image sau signing, digest mới sẽ khác và signature cũ không còn xác minh cho image mới. Rebuild/rebase phải tạo evidence và signature mới.

### 14.2. Không để build job tự ký mọi output

Tách signing stage thành action/job có điều kiện:

- Chỉ nhận artifact từ build execution đã được xác định.
- Kiểm tra test/scan status.
- Chỉ ký repository/digest được cho phép.
- Dùng signing role riêng.
- Ghi lại profile/key ARN và signing request ID.
- Không cho pull request từ fork dùng production signing role.

### 14.3. Buildspec minh họa tạo evidence

~~~yaml
version: 0.2

phases:
  build:
    commands:
      - mvn -B clean verify
      - mvn -B cyclonedx:makeAggregateBom
      - sha256sum target/orders-api.jar > target/orders-api.jar.sha256
  post_build:
    commands:
      - mkdir -p release-evidence
      - cp target/orders-api.jar release-evidence/
      - cp target/orders-api.jar.sha256 release-evidence/
      - cp target/bom.json release-evidence/sbom.cdx.json
      - printf '%s\n' "$CODEBUILD_RESOLVED_SOURCE_VERSION" > release-evidence/source-commit.txt

artifacts:
  files:
    - release-evidence/**/*
~~~

Buildspec là fragment; đường dẫn SBOM phải khớp output thực tế của plugin. Buildspec này chưa push image, chưa ký và chưa tạo provenance chuẩn SLSA. Các bước đó cần action/tool tương ứng sau khi digest đã được xác định.

## 15. Release manifest và deployment records

Release manifest là metadata trung tâm nối artifact với evidence và deployment. Nó nên được tạo một lần cho release candidate rồi được bổ sung deployment records theo từng environment mà không thay đổi artifact identity.

### 15.1. Trường nên có

| Nhóm | Trường |
|---|---|
| Release | service, version, release ID, timestamp |
| Source | repository, commit SHA, branch/tag |
| Build | CodeBuild project/build ID, builder image/toolchain |
| Artifact | type, repository URI, digest, checksum, size |
| Evidence | SBOM URI/digest, provenance URI/digest, scan report |
| Signature | signer profile/key identity, signature reference, verification result |
| Deployment | account, Region, cluster/service/function, image digest, deployment ID |
| Approval | change ticket, approver, approval timestamp |

### 15.2. Một artifact, nhiều deployment records

Không sửa digest trong release manifest để phản ánh từng environment. Tạo deployment record riêng tham chiếu release ID/digest:

~~~json
{
  "releaseId": "orders-api-2.4.1-1842",
  "environment": "staging",
  "account": "444455556666",
  "region": "ap-southeast-1",
  "artifactDigest": "sha256:REPLACE_WITH_REAL_DIGEST",
  "deploymentTarget": "ecs/orders-staging",
  "deploymentId": "d-EXAMPLE",
  "status": "SUCCEEDED",
  "deployedAt": "2026-11-20T04:00:00Z"
}
~~~

Các giá trị là ví dụ. Deployment record nên append-only hoặc được bảo vệ versioning/retention; không ghi đè record staging thành production. Một release có thể có nhiều records cho nhiều accounts/Regions.

### 15.3. Không ghi secret vào manifest

Manifest có thể ghi ARN/reference của secret hoặc parameter path nếu được phép, nhưng không ghi SecretString/password/token. Tránh ghi thông tin customer data, private environment variables hoặc build command có secret.

### 15.4. Lưu manifest ở đâu?

- S3 release evidence bucket với SSE-KMS/versioning/retention.
- Git release tag/release metadata nếu manifest không chứa thông tin nhạy cảm.
- Artifact repository hoặc OCI referrer gắn với image.
- Deployment system metadata/CloudWatch logs với release ID.

Có thể lưu nhiều bản sao phục vụ audit, nhưng phải có canonical source và checksum để tránh các manifest mâu thuẫn.

## 16. Promotion qua accounts và Regions

Promotion là việc đưa cùng artifact đã được xác minh từ môi trường thấp hơn lên môi trường cao hơn. Promotion không phải rebuild.

### 16.1. Promotion flow

~~~mermaid
flowchart TD
    BUILD["Build once in CI account"] --> PUSH["Publish image digest"]
    PUSH --> SB["SBOM + provenance + signature"]
    SB --> VERIFY["Verify evidence"]
    VERIFY --> DEV["Dev account"]
    DEV --> STAGE["Staging account"]
    STAGE --> APPROVE["Production approval"]
    APPROVE --> COPY["Replicate/copy exact image digest"]
    COPY --> VERIFY2["Verify digest + signature at destination"]
    VERIFY2 --> PROD["Production account"]
    PROD --> RECORD["Append deployment record"]
~~~

### 16.2. ECR replication và destination verification

ECR replication giúp copy images tới destination repositories. Destination deployment cần:

- Digest giống source release.
- Repository policy cho phép deployment role pull.
- Signature/referrer có thể được truy cập và verify.
- Trust store/policy chấp nhận signer identity.
- Scan policy đáp ứng security requirements ở destination.
- KMS/encryption và replication configuration đúng account/Region.

Nếu signature referrer không có ở destination, không bỏ qua verification; xử lý replication/copy signature theo định dạng registry và công cụ đang dùng.

### 16.3. Cross-account KMS và IAM

Pipeline account có thể ký bằng AWS Signer profile hoặc KMS key. Target account cần đủ quyền đọc image/evidence và verify trust chain. Nếu dùng KMS public key verification, phân phối public key/certificate và trust metadata theo kênh được kiểm soát; verifier không cần quyền ký.

### 16.4. Promotion có approval

Production approval nên hiển thị:

- Release version, commit SHA, build ID.
- Image digest và registry URI.
- Signature verification result và signer identity.
- SBOM/provenance/scan report links.
- Staging deployment ID và test results.
- Change ticket, target account/Region và rollback plan.

Không approve chỉ dựa vào image tag hoặc trạng thái pipeline xanh.

## 17. Retention, rollback và disaster recovery của artifacts

Artifact retention là một phần của recovery strategy. Nếu production rollback cần image cũ nhưng lifecycle policy đã xóa image, team không thể phục hồi đúng phiên bản.

### 17.1. Định nghĩa retention theo loại dữ liệu

| Artifact | Retention decision |
|---|---|
| Temporary build workspace | Ngắn, cleanup sau build |
| Failed build logs/reports | Theo debugging/audit policy |
| Release JAR/image | Ít nhất bằng rollback window và compliance period |
| SBOM/provenance/signatures | Giữ cùng hoặc lâu hơn release evidence |
| IaC templates/change set evidence | Theo change management/audit policy |
| Deployment records | Theo compliance/incident investigation needs |
| Signing certificates/trust metadata | Giữ đủ để verify signatures lịch sử |

### 17.2. Retain artifacts đang chạy

Trước khi ECR lifecycle expire image:

- Kiểm tra digest đang được ECS task definitions hoặc EKS manifests tham chiếu.
- Kiểm tra Lambda container image version nếu có.
- Kiểm tra rollback window và release history.
- Kiểm tra signatures/SBOM/provenance có còn truy cập được.
- Kiểm tra cross-account/Region copies.

### 17.3. S3 lifecycle và noncurrent versions

Lifecycle có thể chuyển object sang storage class rẻ hơn, expire temporary artifacts hoặc noncurrent versions. Đảm bảo retention không xóa evidence cần audit hoặc release package cần restore. S3 Object Lock retention/legal hold có thể ngăn lifecycle xóa object trước hạn.

### 17.4. ECR backup/copy strategy

ECR replication không thay thế backup policy cho mọi failure mode. Xem xét:

- Cross-account/Region replication.
- Repository policies và lifecycle rules.
- Image digest inventory.
- Signature/referrer retention.
- Rebuild reproducibility và base image availability.
- Runbook phục hồi repository/account bị xóa hoặc quyền truy cập bị mất.

Nếu copy image qua registry khác, verify digest và signature ở destination. Không giả định registry migration luôn giữ nguyên mọi OCI referrers.

### 17.5. Rollback đúng artifact

Rollback record cần trỏ tới release digest đã từng deploy và được verify. Không dùng tag production/stable nếu tag có thể đã được cập nhật. Trước rollback:

1. Xác định release version và digest trước đó.
2. Xác minh image còn trong registry và signature còn verify được.
3. Xác minh runtime config/IAM roles tương thích.
4. Kiểm tra database schema và event compatibility.
5. Deploy digest cũ theo rollback runbook.
6. Ghi deployment record mới với action type ROLLBACK.

## 18. Quản lý signing key, certificate và trust policy

Signing identity chỉ đáng tin khi lifecycle được quản lý. Cần xác định ai được tạo profile/key, ai được ký, ai được thay trust roots và ai được verify.

### 18.1. Separation of duties

| Vai trò | Trách nhiệm | Không nên mặc định có quyền |
|---|---|---|
| Build role | Build/test/scan/publish image | Ký production release hoặc thay trust policy |
| Signing role | Ký digest đã được approved | Thay đổi source/build output |
| Release approver | Duyệt promotion | Quản trị signing keys |
| Deployment role | Deploy digest đã verify | Ký image hoặc sửa trust store |
| Trust administrator | Quản lý trust roots/policies | Tự phê duyệt release |
| Auditor | Đọc evidence/logs | Sửa artifact/signature |

Tách quyền giúp tránh một pipeline compromise vừa thay artifact vừa tự ký và deploy mà không có kiểm soát độc lập.

### 18.2. AWS Signer profile lifecycle

Quản lý signing profile như production security asset:

- Profile name/ARN và signing platform được version hóa trong IaC/change records.
- Chỉ signing role được quyền gọi signing operations trên profile.
- Theo dõi profile status, certificate validity và expiration.
- Thay profile/certificate theo rotation plan.
- Giữ trust chain cũ trong khoảng thời gian cần verify release lịch sử.
- Thu hồi trust khi phát hiện compromise theo incident response.

### 18.3. Certificate expiration và historical verification

Signature có thể được tạo khi certificate còn hiệu lực nhưng được verify nhiều tháng sau. Trust policy cần xác định cách xử lý timestamp, certificate expiration và revocation theo signing format/tool. Giữ signing metadata, certificates và verification evidence để audit lịch sử.

Không tự động xóa trust anchor cũ ngay khi phát hành certificate mới nếu release cũ còn cần verify/rollback. Ngược lại, nếu key compromise, cần thu hồi trust ngay theo incident policy và đánh giá lại artifacts đã ký trong thời gian bị ảnh hưởng.

### 18.4. KMS key rotation

KMS automatic rotation hỗ trợ các key types/configurations nhất định; không áp dụng giống nhau cho mọi asymmetric signing key. Đối với asymmetric signing, thực hiện key/profile rotation theo quy trình tạo key mới, phân phối public key/certificate mới, cập nhật trust policy và giữ khả năng verify signature cũ. Không giả định bật automatic rotation cho encryption key sẽ tự xử lý signing key.

### 18.5. Incident khi signing identity bị compromise

1. Dừng pipeline/job đang sử dụng signer identity.
2. Disable/revoke profile/key hoặc quyền signing theo runbook.
3. Xác định time window, repositories và digests đã được ký.
4. Kiểm tra CloudTrail/Signer audit records và pipeline logs.
5. Thu hồi signer khỏi trust policy nếu cần.
6. Rebuild và re-sign release cần thiết bằng identity mới.
7. Reverify/redeploy artifacts; cân nhắc redeploy toàn bộ workloads có risk.
8. Lưu incident evidence và cập nhật trust policy/controls.

## 19. Traceability và audit trail

Traceability phải đi theo cả hai chiều:

- Từ source commit đến mọi artifact và environment đang chạy.
- Từ production digest ngược về source, build, tests, signer và approvals.

### 19.1. Chuỗi truy vết

~~~mermaid
flowchart LR
    COMMIT["Git commit"] --> BUILD["CodeBuild execution"]
    BUILD --> TEST["Test / scan evidence"]
    BUILD --> DIGEST["Artifact digest"]
    DIGEST --> SBOM["SBOM"]
    DIGEST --> PROV["Provenance"]
    DIGEST --> SIG["Signature"]
    SBOM --> MANIFEST["Release manifest"]
    PROV --> MANIFEST
    SIG --> MANIFEST
    MANIFEST --> DEPLOY["Deployment record"]
    DEPLOY --> RUNTIME["ECS / EKS / Lambda runtime"]
~~~

### 19.2. Dùng CloudTrail

CloudTrail có thể audit API actions liên quan:

- CodePipeline create/update/start execution.
- CodeBuild start build/project changes.
- ECR push/delete image và repository policy changes theo event coverage.
- AWS Signer profile/signing API actions.
- KMS key policy/administration events.
- IAM role/policy/trust changes.
- ECS/EKS/Lambda/CloudFormation deployments.
- S3 artifact object operations theo management/data event configuration.

Không giả định mọi S3 object read/write hoặc mọi ECR data-plane action đều được ghi nếu chưa bật event type phù hợp. Kiểm tra CloudTrail event selectors, data events, organization trail, retention và access controls.

### 19.3. CloudWatch logs và metrics

CodeBuild logs ghi build phases, commands và errors; pipeline execution history ghi action status; deployment service ghi deployment events. Dùng correlation IDs:

- Pipeline execution ID.
- CodeBuild build ID.
- Source commit SHA.
- Image digest.
- Signing profile/key identity.
- Deployment ID.
- ECS task definition revision/EKS rollout revision/Lambda version.

Không ghi secret values, access tokens, signing private material hoặc customer payloads vào logs.

### 19.4. Deployment inventory

Nên có cách truy vấn:

- Service/environment hiện chạy digest nào?
- Digest đó được build từ commit nào?
- SBOM/provenance/signature ở đâu?
- Ai/role nào ký?
- Signature được verify bằng trust policy version nào?
- Release đã deploy vào account/Region nào?
- Deployment ID và rollback target là gì?

Có thể tổng hợp từ release manifests, deployment records, ECR image metadata, ECS task definitions, Kubernetes manifests và Lambda versions. Không dựa vào tag mutable hoặc tên image hiển thị trong dashboard.

### 19.5. Evidence retention

Giữ evidence theo policy:

- Release manifest và digest.
- SBOM/provenance/signature reference.
- Test/security scan reports.
- Approval/change ticket.
- Pipeline/build/deployment IDs.
- Verification result và trust policy version.
- CloudTrail/CloudWatch references.

Evidence phải đủ để điều tra sau khi source branch bị xóa hoặc build project thay đổi.

## 20. Bảo mật artifact repository và signing workflow

### 20.1. Access control

- Developer có quyền đọc release artifacts cần thiết; write chỉ dành cho build/publish roles.
- Signing role chỉ ký artifacts từ trusted pipeline.
- Deployment role chỉ pull/verify artifact, không overwrite.
- Repository administrators tách khỏi release approvers.
- S3 bucket/ECR repository policies scope theo account, role và repository.
- Cross-account permissions chỉ mở cho pipeline/deployment accounts được duyệt.

### 20.2. Protect build environment

Artifact signature không cứu được pipeline nếu build environment bị compromise trước khi ký. Cần:

- Isolate untrusted pull request builds khỏi production secrets/signing roles.
- Pin CodeBuild images và toolchain.
- Restrict network egress khi có thể.
- Review buildspec changes như code có đặc quyền.
- Không chạy shell scripts từ dependency không tin cậy với quyền signer.
- Scan build images và rotate build environment khi có incident.
- Dùng short-lived credentials và IAM role.

### 20.3. Artifact overwrite và deletion

Tag immutability, S3 versioning, bucket policies và Object Lock bổ sung nhau:

| Control | Giảm rủi ro |
|---|---|
| ECR immutable tags | Tag release bị ghi đè |
| Digest pinning | Deployment lấy nhầm nội dung qua mutable tag |
| S3 versioning | Mất object do overwrite/delete |
| S3 Object Lock | Xóa/ghi đè object version trong retention window |
| IAM/bucket/repository policies | Principal không phù hợp sửa/xóa artifact |
| CloudTrail | Khả năng audit ai thực hiện action |

Không control đơn lẻ nào thay thế toàn bộ các control còn lại.

### 20.4. Encryption và access to signing material

Private signing keys không được export hoặc commit vào source. AWS Signer quản lý signing operation theo service model; với KMS, key material được quản lý bởi KMS. Verifier cần public key/certificate/trust metadata, không cần private signing key.

### 20.5. Image scanning và signing policy

Một image chỉ được ký khi đã vượt qua required quality gates. Tuy nhiên, vulnerability database thay đổi theo thời gian; image đã ký hôm qua có thể có CVE mới hôm nay. Có thể định kỳ rescan images đang chạy và áp dụng remediation policy. Signature chứng minh identity/integrity tại thời điểm ký, không chứng minh image luôn an toàn mãi mãi.

## 21. Kiểm thử verification và policy

Verification policy phải được test với cả trường hợp hợp lệ và không hợp lệ.

### 21.1. Test cases tối thiểu

| Test | Kết quả mong đợi |
|---|---|
| Image digest có signature từ signer được duyệt | Verify pass |
| Image unsigned | Reject ở production gate |
| Signature từ signer không tin cậy | Reject |
| Signature subject digest khác image được deploy | Reject |
| Image bị thay đổi sau khi ký | Digest mismatch/verify fail |
| Signature artifact bị xóa | Reject hoặc policy báo missing signature |
| SBOM subject digest không khớp image | Reject nếu policy yêu cầu SBOM |
| Provenance từ builder không được duyệt | Reject |
| Image copy sang account khác nhưng signature thiếu | Reject, yêu cầu phục hồi evidence |
| Certificate/trust anchor hết hạn hoặc bị revoke | Xử lý theo trust policy, không tự bỏ qua |

### 21.2. Test negative path

Không chỉ test image đúng. Đưa image unsigned hoặc signature giả vào test repository để chứng minh deployment gate thật sự chặn. Nếu dùng EKS admission policy, kiểm tra Pod bị từ chối trước khi container chạy. Nếu dùng ECS/Lambda, test pipeline pre-deploy verification action.

### 21.3. Test trust policy changes

Thay đổi trust store/policy có thể làm một số release cũ không còn verify được. Test:

- Thêm signer mới nhưng giữ signer cũ trong migration window.
- Thu hồi signer cũ.
- Đổi repository scope.
- Verify artifact ở destination Region/account.
- Rollback về digest cũ sau key rotation.

### 21.4. Không có signature bypass không kiểm soát

Emergency bypass cần:

- Incident/change ticket.
- Người phê duyệt độc lập.
- Scope repository/digest/environment cụ thể.
- Expiry time.
- Audit log.
- Remediation/re-sign plan.

Không tạo environment variable như SKIP_SIGNATURE_VERIFY=true cho production pipeline mà không có guardrails và approval.

## 22. Thực hành: publish, sign, verify và trace một ECR image

Lab này minh họa quy trình từ image đã build đến release evidence. Cần một AWS test account, ECR repository, CodeBuild/CLI identity có quyền phù hợp, Notation CLI và AWS Signer plugin. Không dùng production signing profile trong lab.

### 22.1. Tạo repository test

~~~bash
aws ecr create-repository \
  --repository-name orders-api-lab \
  --image-tag-mutability IMMUTABLE \
  --image-scanning-configuration scanOnPush=true \
  --region ap-southeast-1
~~~

Nếu repository đã tồn tại, kiểm tra repository configuration thay vì tạo lại. Với lab có thể dùng encryption mặc định của ECR; production cần chọn encryption/KMS theo policy.

### 22.2. Build và push image

~~~bash
REGISTRY="444455556666.dkr.ecr.ap-southeast-1.amazonaws.com"
REPOSITORY="$REGISTRY/orders-api-lab"
TAG="lab-$(git rev-parse --short HEAD)"

aws ecr get-login-password --region ap-southeast-1 |
  docker login --username AWS --password-stdin "$REGISTRY"

docker build -t "orders-api-lab:$TAG" .
docker tag "orders-api-lab:$TAG" "$REPOSITORY:$TAG"
docker push "$REPOSITORY:$TAG"
~~~

Account ID là placeholder. Repository đã bật tag immutability; nếu TAG đã tồn tại, push sẽ bị từ chối. Dùng tag mới theo commit/build ID.

### 22.3. Resolve digest

~~~bash
IMAGE_DIGEST="$(aws ecr describe-images \
  --repository-name orders-api-lab \
  --image-ids imageTag="$TAG" \
  --region ap-southeast-1 \
  --query 'imageDetails[0].imageDigest' \
  --output text)"

IMAGE_URI="$REPOSITORY@$IMAGE_DIGEST"
printf '%s\n' "$IMAGE_URI"
~~~

Kiểm tra IMAGE_DIGEST không rỗng và bắt đầu bằng sha256:. Từ thời điểm này, dùng IMAGE_URI cho scan, SBOM, signing, verification và deployment.

### 22.4. Scan và tạo SBOM

Chờ ECR scan hoàn tất và kiểm tra findings theo severity policy. Tạo SBOM từ đúng digest:

~~~bash
syft "$IMAGE_URI" -o cyclonedx-json=orders-api-lab.cdx.json
sha256sum orders-api-lab.cdx.json > orders-api-lab.cdx.json.sha256
~~~

Lưu SBOM/checksum vào release evidence bucket hoặc publish OCI artifact/referrer. Ghi subject digest vào metadata.

### 22.5. Sign và verify

Sau khi signing profile, Notation plugin, trust store và trust policy đã được cấu hình, đăng nhập Notation vào ECR và ký đúng digest:

~~~bash
aws ecr get-login-password --region ap-southeast-1 |
  notation login --username AWS --password-stdin "$REGISTRY"

notation sign "$IMAGE_URI" \
  --plugin com.amazonaws.signer.notation.plugin \
  --id "$SIGNING_PROFILE_ARN"

notation verify "$IMAGE_URI"
~~~

Ví dụ trên dùng manual signing. REGISTRY là registry hostname; signing profile và plugin Region phải khớp Region của ECR registry. Có thể dùng ECR Docker credential helper thay lệnh notation login. Không deploy nếu sign hoặc verify thất bại. Ghi signing profile identity và verification result vào release manifest.

### 22.6. Tạo release manifest

~~~bash
cat > release-manifest.json <<EOF
{
  "service": "orders-api",
  "releaseVersion": "$TAG",
  "sourceCommit": "$(git rev-parse HEAD)",
  "imageUri": "$IMAGE_URI",
  "sbom": "orders-api-lab.cdx.json",
  "signatureVerified": true,
  "signingProfile": "$SIGNING_PROFILE_ARN"
}
EOF
~~~

Đây là lab script; trong production cần serialize JSON bằng tool/library phù hợp để tránh lỗi escaping, kiểm tra fields và ký/bảo vệ manifest. Không đưa secret values vào file. Lưu manifest cùng SBOM/provenance và deployment records.

### 22.7. Deploy cùng digest

Trong ECS task definition hoặc EKS manifest, đặt image URI bằng IMAGE_URI. Không resolve tag lần nữa ở production. Sau deploy, đọc task definition/Pod spec để xác nhận runtime đang dùng đúng digest.

## 23. Troubleshooting artifact và signature

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| ECR push bị denied | Build role thiếu upload actions hoặc repository policy chặn | Caller identity, repository ARN, ECR permissions |
| Tag already exists | Repository bật IMMUTABLE và tag bị dùng lại | Tạo tag duy nhất theo commit/build ID |
| Digest khác giữa staging/prod | Rebuild, mutable tag hoặc copy sai image | Release manifest, source/destination digest |
| Signature không tìm thấy | Sign chưa hoàn tất, referrer không được copy hoặc repository client không hỗ trợ | ECR referrers, notation inspect/list, replication behavior |
| Notation plugin không load | Plugin chưa cài, version/OS mismatch | notation plugin list, plugin release/checksum |
| AWS Signer AccessDenied | Signing role thiếu action/profile access hoặc trust config sai | CloudTrail, role policy, profile ARN/Region |
| Notation verify fail | Trust store/policy không khớp, cert expired/revoked, subject digest sai | Verification error, trust policy, signature metadata |
| Cosign verify fail | KMS key ARN/public key/trust configuration không đúng | Cosign version, key URI, certificate/identity claims |
| SBOM subject không khớp | SBOM tạo từ tag khác hoặc image đã rebuild | SBOM metadata, image digest, build ID |
| Provenance không được chấp nhận | Builder/source identity không thuộc allowlist hoặc attestation sai schema | Attestation subject, predicate, trust policy |
| ECS deploy unsigned image | Pipeline verification action bị bỏ qua hoặc deploy được thực hiện ngoài pipeline | ECS task definition, IAM permissions, release logs |
| EKS admission reject Pod | Policy không tin signer/repository hoặc signature thiếu | Admission events, policy report, trust store |
| Rollback image không pull được | ECR lifecycle xóa digest hoặc cross-account policy đổi | ECR describe-images, lifecycle, repository policy |
| S3 artifact checksum mismatch | Object bị thay đổi/copy sai hoặc manifest trỏ sai version | S3 VersionId, checksum, CloudTrail data events |
| Signature hết hạn/không verify lịch sử | Trust root/certificate bị xóa hoặc policy thay đổi | Historical trust chain, timestamp, revocation policy |

### 23.1. Điều tra sai digest

1. Đọc digest trong release manifest.
2. Kiểm tra ECR describe-images theo tag và digest.
3. Kiểm tra source/destination replication.
4. Đọc task definition/Pod spec đang chạy.
5. Kiểm tra pipeline artifact mapping và parallel executions.
6. Không sửa manifest để khớp image sai; xác định artifact đúng và deploy lại bằng digest chính xác.

### 23.2. Điều tra signature verification

Kiểm tra theo thứ tự:

1. Image digest có đúng digest được ký?
2. Signature/referrer còn ở repository/Region hiện tại?
3. Notation plugin hoặc Cosign version có hỗ trợ signature format?
4. Trust store có certificate chain/public key cần thiết?
5. Trust policy có chấp nhận signer identity và repository scope?
6. Certificate validity, timestamp và revocation status có thỏa policy?
7. IAM/network permissions có cho verifier đọc metadata/signature?

Không giải quyết lỗi bằng cách tắt verification. Sửa trust configuration hoặc republish evidence đúng cách.

### 23.3. Artifact bị xóa

Nếu image cần rollback không còn trong ECR:

- Xác định digest từ release manifest/deployment record.
- Kiểm tra replica repositories hoặc backup/copy.
- Nếu có bản sao, verify digest/signature trước khi dùng.
- Nếu không có bản sao, đánh giá rebuild reproducibly từ source và dependencies đã pin; artifact rebuild sẽ có digest mới và phải được scan/sign lại.
- Cập nhật retention policy và diễn tập restore.

Không tuyên bố artifact rebuild là byte-identical nếu chưa chứng minh reproducible build.

## 24. Chi phí và tối ưu retention

Artifact management có thể tạo chi phí lưu trữ lâu dài và data transfer. Cần cân bằng retention, rollback window, audit requirements và chi phí.

| Thành phần | Yếu tố chi phí | Cách tối ưu |
|---|---|---|
| S3 artifact store | Storage, requests, replication, KMS API usage | Lifecycle, tiering, cleanup temporary artifacts |
| S3 Object Lock | Retained object versions không thể xóa trước hạn | Chỉ áp dụng cho evidence cần WORM |
| ECR | Image layers, replication, scan features, transfer | Deduplicate layers, lifecycle rules, retain releases |
| CodeArtifact | Package storage, requests, upstream data transfer | Cache và retention cho obsolete package versions |
| AWS Signer/KMS | Signing operations, KMS requests/key usage theo pricing | Ký release artifacts cần thiết, right-size key/profile usage |
| CodeBuild | Build minutes cho SBOM/scan/sign stages | Cache dependencies, tránh chạy trùng stage |
| CloudWatch/CloudTrail | Logs, data events, metrics, retention | Chọn event coverage và retention theo risk |
| Cross-Region | Image/evidence replication và transfer | Replicate tới Regions thực sự cần |

### 24.1. Retention theo release policy

Định nghĩa:

- Bao nhiêu releases gần nhất phải giữ online?
- Rollback window là bao lâu?
- Evidence nào phải giữ theo compliance?
- Artifact nào có thể chuyển storage class?
- Khi nào có thể xóa failed/temporary build artifacts?
- Ai phê duyệt xóa release đã deploy?

### 24.2. Không xóa image đang được tham chiếu

Lifecycle policy cần tính đến ECS task definitions cũ, EKS manifests/rollout history, Lambda versions, blue/green deployment windows và release rollback targets. Có thể duy trì allowlist/tag prefix cho releases cần giữ, nhưng deployment identity vẫn là digest.

### 24.3. Cost of signing and scanning

Không cần ký mọi intermediate build image nếu chúng không được deploy. Có thể scan ở nhiều điểm nhưng chỉ ký release candidate đã pass gates. Nếu policy yêu cầu sign every build, tách signing profiles cho non-production và production để quản lý trust boundary.

## 25. Bài tập tình huống

### Tình huống A — Tag production bị overwrite

Một build mới push tag production lên ECR. ECS service vẫn dùng image URI theo tag, nên task replacement kéo image khác với image đã test staging.

**Câu hỏi:** cần đổi cơ chế release thế nào?

**Gợi ý:** bật tag immutability cho release repository, lưu digest trong manifest và deploy digest. Tag production chỉ là nhãn tra cứu, không làm deployment identity.

### Tình huống B — Signature hợp lệ nhưng image có CVE critical

Image được ký bởi AWS Signer và verify thành công, nhưng ECR scan phát hiện critical vulnerability sau khi CVE database cập nhật.

**Câu hỏi:** có thể tiếp tục tin image chỉ vì signature hợp lệ?

**Gợi ý:** signature chỉ chứng minh identity/integrity theo trust policy. Cần rescan, vulnerability policy và remediation. Signature không chứng minh image luôn an toàn.

### Tình huống C — SBOM thuộc image khác

Release manifest trỏ tới image digest B nhưng SBOM được tạo từ image tag trước khi rebuild, digest A.

**Câu hỏi:** phát hiện và ngăn thế nào?

**Gợi ý:** tạo SBOM sau khi final digest được push hoặc gắn subject digest chính xác; kiểm tra SBOM subject trong pipeline gate. Không dùng tag mutable làm liên kết.

### Tình huống D — Ký image trước khi scan

Pipeline ký image ngay sau docker push. Sau đó vulnerability scan fail nhưng deploy stage vẫn chạy do dependency giữa stages bị cấu hình sai.

**Câu hỏi:** sắp xếp pipeline ra sao?

**Gợi ý:** scan và required quality gates phải pass trước signing/approval; deployment chỉ nhận artifact từ stage verification thành công. Signing role tách khỏi build role và không được gọi từ untrusted PR job.

### Tình huống E — Image replicate nhưng signature không có

Image digest đã được replicate sang production account, nhưng Notation verify báo không tìm thấy signature.

**Câu hỏi:** có thể bỏ qua verify vì digest giống source không?

**Gợi ý:** không. Kiểm tra OCI referrers/signature replication và repository support. Copy/reattach signature theo quy trình, sau đó verify ở destination; digest giống nhau không thay thế bằng chứng signer.

### Tình huống F — AWS Signer certificate đã rotate

Team phát hành signing profile/certificate mới nhưng xóa trust anchor cũ ngay lập tức. Một incident yêu cầu rollback về image đã ký bằng certificate cũ.

**Câu hỏi:** cần quản lý trust rotation thế nào?

**Gợi ý:** giữ trust chain cũ trong retention/rollback window và kiểm thử historical verification. Khi compromise thì revoke theo incident policy, còn rotation bình thường cần overlap có kiểm soát.

### Tình huống G — Checksum và artifact đều bị thay

Một actor có quyền ghi S3 thay JAR và file .sha256 cùng lúc. Checksum verification vẫn pass.

**Câu hỏi:** cần thêm control nào?

**Gợi ý:** checksum không xác thực nguồn gốc nếu attacker thay được cả hai. Dùng signature/provenance với trust root độc lập, S3 bucket policies/Object Lock, separate write/sign roles và CloudTrail audit.

### Tình huống H — Production deploy lại tag đã đổi

Staging và production dùng cùng tag 2.4.1 nhưng registry tag đã được cập nhật ngoài ý muốn giữa hai lần deploy.

**Câu hỏi:** vì sao “same tag” không chứng minh “same artifact”?

**Gợi ý:** tag có thể mutable. Release manifest cần digest; promotion dùng digest đã test. Bật immutable tags và xác minh digest ở mọi destination.

### Tình huống I — Build role tự ký artifact không qua approval

Một CodeBuild project chạy pull request có quyền Signer profile production. Attacker sửa buildspec để ký image của mình.

**Câu hỏi:** tách quyền ra sao?

**Gợi ý:** PR build role không có signer permissions; signing stage chỉ nhận artifact từ protected pipeline sau tests/scans/approval. Giới hạn profile/repository và audit signing operations.

### Tình huống J — S3 Object Lock làm cleanup thất bại

Lifecycle policy cố xóa release evidence nhưng object đang trong compliance retention.

**Câu hỏi:** xử lý thế nào?

**Gợi ý:** retention compliance không thể bypass trước hạn. Thiết kế retention trước khi bật Object Lock, tách temporary artifacts và WORM evidence, theo dõi storage costs và expiry.

### Tình huống K — Rollback image không còn trong ECR

Lifecycle policy xóa image cũ sau 14 ngày, nhưng production incident xảy ra ngày thứ 30 và cần rollback.

**Câu hỏi:** cần thay đổi retention?

**Gợi ý:** giữ image ít nhất bằng rollback window và compliance requirements, replicate backup repository, bảo vệ digest đang chạy/được tham chiếu và diễn tập restore.

### Tình huống L — EKS admission policy chỉ kiểm tra tag

Admission policy cho phép mọi image tag bắt đầu bằng production-, nhưng tag có thể bị overwrite.

**Câu hỏi:** tăng độ tin cậy ra sao?

**Gợi ý:** yêu cầu digest pinning, verify signature/referrer và signer identity/repository scope. Tag prefix không phải trust identity.

### Tình huống M — Provenance có nhưng builder không đáng tin

Attestation ghi đúng source commit và digest nhưng được tạo bởi một build host có thể bị developer tùy ý sửa.

**Câu hỏi:** provenance có đủ để approve?

**Gợi ý:** cần đánh giá builder identity/isolation, access controls, immutable build image, source protections và attestation signing. Metadata đúng cú pháp không chứng minh builder an toàn.

### Tình huống N — KMS encryption key bị nhầm với signing key

Team bật SSE-KMS cho ECR/S3 và cho rằng artifact đã được ký.

**Câu hỏi:** thiếu điều gì?

**Gợi ý:** encryption-at-rest bảo vệ storage; cần signing workflow riêng, signature gắn digest và verifier trust policy. Chỉ asymmetric KMS signing flow có cấu hình phù hợp mới thực hiện ký.

### Tình huống O — Signature verify pass ở staging nhưng fail production

Production account không có trust anchor mới và ECR destination repository không chứa signature referrer.

**Câu hỏi:** promotion checklist cần thêm gì?

**Gợi ý:** phân phối trust roots/policy tới destination, xác minh referrer sau replication, kiểm tra IAM/network và chạy verification trong chính target account/Region trước deploy.

## 26. Checklist production

- [ ] Mỗi release có source commit SHA, build ID, semantic version và artifact digest.
- [ ] Build một lần và promote cùng artifact qua môi trường.
- [ ] JAR/ZIP có checksum; checksum không được xem là thay thế chữ ký số.
- [ ] S3 artifact bucket block public access, có versioning, encryption, bucket policy và lifecycle.
- [ ] S3 Object Lock chỉ bật khi retention/compliance đã được thiết kế.
- [ ] ECR release repository bật immutable tags phù hợp.
- [ ] ECS/EKS/Lambda container deployments pin image digest, không dùng latest/tag mutable làm identity.
- [ ] ECR scanning/Inspector findings được xử lý theo severity policy.
- [ ] ECR lifecycle không xóa images đang chạy hoặc trong rollback window.
- [ ] ECR replication được kiểm tra digest và signature/referrers ở destination.
- [ ] CodeArtifact package versions/upstream sources được kiểm soát.
- [ ] SBOM theo SPDX/CycloneDX được tạo từ artifact/image cuối và gắn subject digest.
- [ ] Provenance ghi source, builder, invocation, materials và output digest.
- [ ] SBOM/provenance artifacts có checksum, retention và access policy.
- [ ] AWS Signer/Notation hoặc Cosign signing profile/key được quản lý qua IaC/change control.
- [ ] Signing role tách khỏi build, approval và deployment roles.
- [ ] Signing chỉ chạy sau required tests/scans và trên digest đã publish.
- [ ] Signature gắn đúng digest và có thể verify bằng trust policy.
- [ ] Trust store/policy giới hạn signer identity và repository scope.
- [ ] EKS admission policy verify signature trước khi Pod chạy nếu kiến trúc yêu cầu.
- [ ] ECS/Lambda có pipeline verification gate trước deploy.
- [ ] Lambda ZIP code signing dùng Lambda Code Signing Configuration đúng policy.
- [ ] KMS encryption keys và signing keys có purpose/permissions riêng.
- [ ] Certificate/key rotation giữ historical verification trong rollback window.
- [ ] Có incident response khi signer/key compromise.
- [ ] Release manifest nối digest, SBOM, provenance, signature và deployment records.
- [ ] Deployment record được append theo environment/account/Region.
- [ ] CloudTrail audit coverage phù hợp với S3/ECR/Signer/KMS/IAM operations.
- [ ] Logs/manifest không chứa secrets, tokens hoặc customer data.
- [ ] Artifact retention đủ cho rollback, audit và compliance.
- [ ] Đã test unsigned image, untrusted signer, wrong digest, missing referrer và revoked trust.
- [ ] Đã diễn tập artifact restore, cross-account promotion, signature verification và rollback.

## 27. Ghi nhớ

**Artifact là thứ được build và deploy; digest định danh nội dung; signature xác minh signer và integrity; SBOM mô tả components; provenance giải thích artifact được tạo ra như thế nào; release manifest nối tất cả bằng chứng đó với deployment.**

Trên AWS, dùng S3 cho pipeline/release evidence, ECR cho container images, CodeArtifact cho packages, KMS cho encryption/key operations và AWS Signer với Notation hoặc Cosign/KMS cho image signing theo trust model. Bật ECR tag immutability, deploy bằng digest, tạo SBOM/provenance từ đúng artifact cuối và verify signature trước khi release. Với Lambda ZIP, dùng Lambda Code Signing Configuration; với EKS, cân nhắc admission verification; với ECS/Lambda container, đặt verification gate trong deployment pipeline.

Giữ cùng artifact digest qua dev/staging/prod, lưu release manifest và deployment records, quản lý trust/key lifecycle, giữ artifact đủ lâu cho rollback và audit. Encryption không thay signing, checksum không thay provenance, signature không chứng minh code không có vulnerability và rollback code không tự phục hồi data. Một chuỗi supply-chain đáng tin cậy cần build isolation, least privilege, immutable artifacts, signed evidence, verification enforcement và audit trail xuyên suốt.

### Tài liệu AWS và chuẩn chính thức để đối chiếu

- [Amazon ECR User Guide](https://docs.aws.amazon.com/AmazonECR/latest/userguide/what-is-ecr.html) — repositories, images và registry.
- [ECR image tag mutability](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-tag-mutability.html) — immutable/mutable tags.
- [ECR lifecycle policies](https://docs.aws.amazon.com/AmazonECR/latest/userguide/LifecyclePolicies.html) — retention và image expiration.
- [ECR replication](https://docs.aws.amazon.com/AmazonECR/latest/userguide/replication.html) — cross-account/Region replication.
- [ECR image scanning](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-scanning.html) — scan configuration và findings.
- [AWS Signer User Guide](https://docs.aws.amazon.com/signer/latest/developerguide/Welcome.html) — signing profiles và code signing.
- [AWS Signer container image signing](https://docs.aws.amazon.com/signer/latest/developerguide/image-signing-steps.html) — signing profile, Notation plugin, sign và verify.
- [Amazon ECR image signing](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-signing.html) — managed signing và manual signing.
- [Amazon ECR managed signing](https://docs.aws.amazon.com/AmazonECR/latest/userguide/managed-signing.html) — tự động ký image khi push và repository filters.
- [Amazon ECR manual signing](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-signing-manual.html) — ký client-side bằng Notation.
- [AWS Signer image-signing prerequisites](https://docs.aws.amazon.com/signer/latest/developerguide/image-signing-prerequisites.html) — cài Notation/plugin, registry authentication và IAM permissions.
- [Notation documentation](https://notaryproject.dev/docs/) — signing, verification, trust stores và policies.
- [Amazon S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html) — WORM retention và legal hold.
- [Amazon S3 Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html) — object versions và recovery.
- [AWS KMS key types](https://docs.aws.amazon.com/kms/latest/developerguide/concepts.html) — symmetric/asymmetric keys và key usage.
- [AWS CodeArtifact User Guide](https://docs.aws.amazon.com/codeartifact/latest/ug/welcome.html) — package repositories.
- [AWS Lambda code signing](https://docs.aws.amazon.com/lambda/latest/dg/governance-code-signing.html) — signing profiles và enforcement khi deploy ZIP packages.
- [Amazon EKS image verification](https://docs.aws.amazon.com/eks/latest/userguide/security.html) — workload security context; admission policy được triển khai theo toolchain cluster.
- [SPDX specification](https://spdx.github.io/spdx-spec/) — SBOM format.
- [CycloneDX specification](https://cyclonedx.org/specification/overview/) — SBOM format.
- [SLSA specification](https://slsa.dev/spec/v1.0/) — supply-chain levels và provenance.
- [in-toto attestation framework](https://github.com/in-toto/attestation) — attestation model.
- [Sigstore Cosign](https://docs.sigstore.dev/cosign/overview/) — container image signing and verification.
- [AWS CloudTrail User Guide](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html) — API audit and event history.




