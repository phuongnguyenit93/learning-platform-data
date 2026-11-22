# Chuỗi cung ứng phần mềm, ảnh container và nguồn triển khai đáng tin

Một ứng dụng cloud không chỉ được tạo từ mã nguồn của đội phát triển. Nó còn phụ thuộc thư viện bên thứ ba, package manager, base image, compiler, build runner, CI/CD workflow, artifact registry, deployment controller, IaC module và nhiều dịch vụ tự động hóa khác. Mỗi mắt xích có thể đưa mã hoặc cấu hình vào môi trường production. Nếu một dependency bị chiếm quyền, token CI bị đánh cắp, image bị thay thế hoặc pipeline tải artifact không rõ nguồn, hệ thống có thể triển khai phần mềm đã bị sửa dù repository chính vẫn sạch.

Đó là rủi ro của **chuỗi cung ứng phần mềm (software supply chain)**. Mục tiêu bảo mật không chỉ là quét lỗ hổng trong source code mà còn phải chứng minh artifact được tạo từ nguồn nào, bởi workflow nào, với dependency và công cụ nào; bảo vệ artifact khỏi bị thay đổi; xác minh chữ ký và provenance trước khi triển khai; và giới hạn quyền của hệ thống build/deploy. Với container, cần xác định image digest bất biến, base image đáng tin, SBOM, provenance attestation, signature verification và runtime policy.

Bài học thuộc chương **Kiến trúc bảo mật** của module **CLOUD_ARCHITECTURE**. Trọng tâm là xây dựng đường đi đáng tin từ source đến production, đồng thời cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả các thành phần và ranh giới tin cậy trong software supply chain.
2. Phân biệt source integrity, build integrity, artifact integrity, provenance và deployment authorization.
3. Thiết kế CI/CD với quyền tối thiểu, runner cô lập, secret ngắn hạn và approval theo môi trường.
4. Quản lý dependency, package, base image và container image theo phiên bản/digest.
5. Giải thích SBOM, vulnerability scanning, provenance attestation và chữ ký artifact.
6. Thiết lập admission policy để chỉ cho phép workload sử dụng image/artifact đạt yêu cầu.
7. Bảo vệ IaC, manifest và cấu hình triển khai khỏi thay đổi trái phép.
8. Xử lý image bị thu hồi, dependency compromise, signing key compromise và build pipeline incident.
9. Đo mức bao phủ, thời gian khắc phục và chất lượng kiểm soát supply chain.

## 2. Chuỗi cung ứng phần mềm là gì?

### 2.1. Các mắt xích của một lần phát hành

Một luồng điển hình:

~~~mermaid
flowchart LR
    SRC[Source repository] --> REVIEW[Review and protected branch]
    REVIEW --> CI[CI workflow]
    CI --> DEPS[Dependencies and toolchain]
    DEPS --> BUILD[Build and test]
    BUILD --> SBOM[SBOM and provenance]
    SBOM --> SIGN[Sign artifact]
    SIGN --> REG[Artifact registry]
    REG --> VERIFY[Verify signature and policy]
    VERIFY --> DEPLOY[CD / deployment controller]
    DEPLOY --> RUN[Production runtime]
    RUN --> MON[Monitor and respond]
~~~

Mỗi bước nhận đầu vào và tạo ra một đầu ra có thể ảnh hưởng tới bước tiếp theo. Ví dụ, source commit được review nhưng build workflow chạy từ một action bên thứ ba bị chiếm quyền; image tạo ra có thể chứa mã độc. Hoặc build an toàn nhưng registry cho phép ghi đè tag khiến deploy lấy image khác với image đã kiểm thử.

### 2.2. Những tài sản cần bảo vệ

- Source code, branch, tag, commit và review metadata.
- Package/dependency, package registry và lockfile.
- Compiler, build tool, base image, build script và runner.
- CI workflow, reusable action, plugin và credential.
- Binary, package, container image, Helm chart và IaC module.
- SBOM, provenance, test result, vulnerability report và chữ ký.
- Artifact registry, signing service, key và identity.
- Deployment manifest, GitOps repository, admission policy và cluster credential.
- Runtime image, node, workload identity và secret được workload sử dụng.

### 2.3. Threat model theo từng ranh giới

| Thành phần | Rủi ro | Ví dụ hậu quả |
|---|---|---|
| Source repository | Account/branch bị chiếm, review bị bypass | Mã độc được merge |
| Dependency | Package bị typosquatting hoặc maintainer bị compromise | Mã độc chạy lúc build hoặc runtime |
| Build workflow | Workflow injection, action không pin, runner bị chiếm | Artifact bị sửa |
| Secret | Token dài hạn bị lộ trong log hoặc runner | Attacker publish image/deploy |
| Registry | Tag bị ghi đè, quyền push quá rộng | Image production bị thay |
| Provenance | Attestation giả hoặc không được kiểm tra | Artifact không rõ nguồn được tin |
| Deployment | Manifest/cluster credential bị chiếm | Workload trái phép được chạy |
| Runtime | Image dễ bị khai thác, quyền container quá rộng | Lateral movement và data exfiltration |

## 3. Nguyên tắc xây dựng chuỗi cung ứng đáng tin

### 3.1. Xác định nguồn gốc trước khi tin

Một artifact không đáng tin chỉ vì nó nằm trong registry nội bộ. Cần biết artifact:

- Được tạo từ repository và commit nào.
- Được build bởi workflow và identity nào.
- Dùng builder/toolchain và dependency nào.
- Có được test/scan theo policy không.
- Có SBOM và provenance được gắn với đúng digest không.
- Có chữ ký hợp lệ từ identity được phép không.
- Được phê duyệt cho môi trường nào.

### 3.2. Bảo vệ từng bước

Defense in depth áp dụng từ source đến runtime:

- Bảo vệ repository và branch.
- Pin dependency và build action.
- Dùng runner cô lập, ephemeral khi có thể.
- Không cấp credential production cho build job thông thường.
- Ký artifact và lưu evidence.
- Verify trước deploy và ở admission layer.
- Runtime dùng non-root, read-only filesystem và quyền tối thiểu.
- Theo dõi thay đổi và khả năng thu hồi artifact.

### 3.3. Fail closed ở ranh giới quan trọng

Nếu production policy yêu cầu image đã ký bởi identity được phê duyệt, hệ thống không nên tự bỏ qua lỗi xác minh vì registry chậm hoặc attestation thiếu. Có thể có luồng break-glass riêng với thời hạn, người phê duyệt và audit; không biến ngoại lệ thành mặc định.

### 3.4. Phân tách build và deploy

Build system tạo artifact. Deployment system quyết định artifact nào được đưa tới môi trường nào. Tách hai quyền này làm giảm khả năng một dependency trong build job tự lấy quyền deploy production. Artifact được chuyển qua registry hoặc channel có kiểm soát, kèm digest và evidence.

## 4. Bảo vệ source repository

### 4.1. Branch và review protection

Repository quan trọng nên có:

- Protected default/release branch.
- Pull request bắt buộc thay vì push trực tiếp.
- Required review và code owner cho thư mục nhạy cảm.
- Required status checks và policy test.
- Signed commit/tag khi phù hợp với workflow.
- Giới hạn quyền tạo/sửa release và repository settings.
- Audit lịch sử branch protection, webhook và token.

Không phải mọi dự án đều cần nhiều tầng approval. Mức kiểm soát nên dựa trên criticality, khả năng ảnh hưởng và quy mô đội ngũ.

### 4.2. CODEOWNERS và kiểm soát workflow

Các file pipeline, deployment, IaC, policy và build script có quyền đặc biệt. Thay đổi các file này có thể làm lộ secret hoặc bỏ qua kiểm tra. Đặt code owner/review bắt buộc cho các đường dẫn nhạy cảm; test workflow trong môi trường không có production credential trước khi merge.

### 4.3. Token repository

Giới hạn token theo repository, scope và thời gian. Tránh token cá nhân lâu dài cho automation; ưu tiên workload identity/OIDC federation hoặc ứng dụng tích hợp có quyền tối thiểu. Thu hồi token không sử dụng, audit lần truy cập và phát hiện secret bị commit.

## 5. Quản lý dependency và package

### 5.1. Dependency trực tiếp và bắc cầu

Ứng dụng có dependency trực tiếp do nhóm khai báo và dependency bắc cầu được kéo theo. Một package nhỏ ở sâu trong graph vẫn có thể được thực thi lúc build hoặc runtime. SBOM và scanner cần nhìn toàn bộ cây dependency, không chỉ file manifest cấp cao.

### 5.2. Lockfile và phiên bản có thể tái tạo

Lockfile ghi phiên bản dependency được giải quyết và thường kèm integrity/hash. Build production nên dùng chế độ cài đặt tái lập từ lockfile, tránh cập nhật dependency ngầm giữa hai lần build. Khi update, thực hiện có chủ đích, review thay đổi và chạy test.

~~~text
Package manifest:
  khai báo range phiên bản cần dùng

Lockfile:
  ghi phiên bản cụ thể đã resolve
  ghi integrity/hash nếu package manager hỗ trợ

CI:
  cài dependency theo lockfile
  không tự resolve phiên bản mới ngoài dự kiến
~~~

Lockfile giảm độ bất định nhưng không chứng minh package an toàn. Package độc hại vẫn có thể được khóa ở một phiên bản cụ thể.

### 5.3. Package confusion và typosquatting

Rủi ro thường gặp:

- Tên package gần giống package phổ biến.
- Dependency confusion giữa package nội bộ và public registry.
- Repository giả mạo hoặc maintainer account bị chiếm.
- Package có install script thực thi lệnh.
- Typosquatting hoặc package không còn được duy trì.

Biện pháp:

- Dùng namespace/private registry cho package nội bộ.
- Cấu hình registry scope rõ ràng.
- Allowlist nguồn package khi cần.
- Kiểm tra maintainer, repository, lịch phát hành và hành vi install script.
- Dùng lockfile, integrity verification và dependency review.
- Theo dõi package bị đánh dấu độc hại hoặc bị thu hồi.

### 5.4. Dependency update policy

Không nên chọn một trong hai cực: đóng băng dependency mãi mãi hoặc tự động cập nhật mọi package vào production. Xác định:

- Mức criticality của dependency.
- Mức độ nghiêm trọng và khả năng khai thác lỗ hổng.
- Release cadence và thời gian hỗ trợ.
- Tương thích API/schema.
- Test coverage và rollback path.
- Deadline xử lý security advisory.

Tự động tạo pull request cập nhật dependency có thể tốt; tự động merge/deploy mọi cập nhật mà không có policy và test không phải là bảo đảm an toàn.

### 5.5. Secret trong dependency install

Package install script có thể thực thi trong build runner. Không cấp quyền truy cập production secret cho giai đoạn tải/cài package. Giới hạn network egress, scope token và quyền ghi registry; tách build job untrusted (ví dụ pull request từ fork) khỏi job release có quyền ký/publish.

## 6. Bảo vệ CI/CD và build environment

### 6.1. Pipeline là một tài sản bảo mật

CI/CD có thể đọc source, package, secret, ký artifact và triển khai production. Nếu pipeline bị chiếm, attacker có thể vượt qua nhiều lớp bảo vệ ứng dụng. Bảo vệ:

- Workflow definition và reusable pipeline.
- Runner image, runner host và cache.
- Plugin/action và phiên bản.
- Secret/identity cấp cho từng job.
- Network egress và quyền gọi API.
- Artifact output và log.
- Approval và môi trường deploy.

### 6.2. Runner cô lập

Ưu tiên runner ephemeral hoặc được làm sạch sau mỗi job. Không chia sẻ workspace, credential hoặc Docker daemon giữa job có mức tin cậy khác nhau. Job chạy code từ fork/untrusted pull request cần sandbox riêng và không có secret release.

### 6.3. Pin action và toolchain

Tham chiếu action/plugin theo tag có thể nhận nội dung thay đổi. Với pipeline nhạy cảm, pin commit digest/hash bất biến theo khả năng nền tảng, review update và ghi rõ nguồn tin cậy. Pin không loại bỏ lỗ hổng trong phiên bản đã pin; vẫn cần cập nhật có kiểm soát.

### 6.4. OIDC và credential ngắn hạn

Thay vì lưu cloud access key dài hạn trong CI secret, có thể dùng OIDC federation:

1. CI workload nhận identity token có audience và claim.
2. Cloud IAM kiểm tra issuer, subject, repository, branch/environment và audience.
3. Nếu thỏa policy, cấp credential ngắn hạn với role giới hạn.
4. Credential hết hạn tự động sau job/session.

Policy phải giới hạn đúng repository và workflow. Nếu trust policy chỉ kiểm tra issuer chung mà không ràng buộc subject/audience, nhiều workflow ngoài dự kiến có thể xin role.

### 6.5. Least privilege theo job

Không cấp tất cả quyền cho toàn pipeline. Ví dụ:

| Job | Quyền cần | Quyền không nên có |
|---|---|---|
| Lint/test từ pull request | Đọc source, tải dependency | Publish release, deploy production |
| Build candidate | Đọc source/dependency, ghi artifact staging | Sửa IAM hoặc đọc production secret |
| Sign release | Đọc artifact đã duyệt, dùng signing identity | Sửa source hoặc tự phê duyệt thay đổi |
| Deploy staging | Đọc artifact, cập nhật staging | Ghi production |
| Deploy production | Đọc artifact đã ký, quyền deploy hẹp | Phát hành/chỉnh sửa artifact |

### 6.6. Build reproducibility và hermetic build

Reproducible build hướng tới cùng source, dependency và môi trường sẽ cho artifact giống nhau theo tiêu chí byte-for-byte hoặc mức có thể kiểm chứng. Hermetic build giới hạn đầu vào để build không lấy dữ liệu tùy ý từ network trong lúc chạy.

Lợi ích:

- Dễ xác định thay đổi artifact đến từ đâu.
- Giảm phụ thuộc bất ngờ vào dịch vụ ngoài.
- Hỗ trợ đối chiếu build độc lập.
- Dễ điều tra khi artifact bị nghi ngờ.

Đánh đổi là quản lý cache, toolchain, dependency mirror và build environment phức tạp hơn. Không phải mọi hệ thống hiện tại đều cần reproducible build tuyệt đối; hãy chọn mức tương ứng risk.

## 7. Container image đáng tin

### 7.1. Image là artifact bất biến theo digest

Container image thường được truy cập bằng tag như release-2026-11 hoặc latest, nhưng tag có thể bị ghi đè. Digest xác định nội dung image cụ thể:

~~~text
registry.example.com/booking/api@sha256:<image-digest>
~~~

Production manifest nên tham chiếu digest đã kiểm thử/phê duyệt. Tag vẫn hữu ích cho con người, nhưng không nên là định danh duy nhất của nội dung cần triển khai.

### 7.2. Chọn base image

Chọn base image từ nguồn chính thức hoặc registry được kiểm soát, pin digest, cập nhật theo security advisory và giữ thành phần ở mức cần thiết. Image nhỏ hơn thường giảm bề mặt tấn công và thời gian tải, nhưng không thay thế scanning hay runtime controls.

Ưu tiên:

- Base image có lịch cập nhật và hỗ trợ rõ.
- Distroless/minimal image nếu workload tương thích.
- Không nhúng compiler, package manager hoặc debug utility không cần thiết vào runtime image.
- Không chạy package upgrade tùy ý trong lúc container khởi động.
- Có quy trình rebuild khi base image có CVE.

### 7.3. Multi-stage build

~~~dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/dist ./dist
COPY --from=build /app/node_modules ./node_modules
USER 10001:10001
EXPOSE 8080
CMD ["node", "dist/server.js"]
~~~

Đây là ví dụ minh họa; trong production cần pin base image theo digest, cân nhắc chỉ copy production dependencies, kiểm tra file permission, health check và build metadata. Không đưa .env, private key, token hoặc file cấu hình môi trường vào image layer.

### 7.4. Không để secret trong image layer

Lệnh xóa secret ở layer sau không đảm bảo secret biến mất khỏi các layer trước. Dùng build secret mechanism của builder hoặc lấy secret lúc runtime từ secret manager bằng workload identity. Kiểm tra build context và .dockerignore để tránh copy file local nhạy cảm.

### 7.5. Container runtime hardening

- Chạy non-root với UID/GID rõ.
- Read-only root filesystem khi ứng dụng cho phép.
- Bỏ Linux capabilities không cần.
- Không dùng privileged mode.
- Giới hạn CPU, memory, PID và ephemeral storage.
- Seccomp/AppArmor/SELinux profile theo nền tảng.
- Không mount Docker socket hoặc host path tùy tiện.
- Dùng network policy và workload identity theo least privilege.
- Chỉ dùng image đã được scan/verify theo policy.

## 8. SBOM: biết phần mềm chứa những gì

### 8.1. SBOM là gì?

Software Bill of Materials (SBOM) là danh mục thành phần của một phần mềm hoặc artifact. Nó có thể ghi:

- Package/component name và version.
- Package URL (PURL), supplier, license.
- Dependency relationship.
- Hash hoặc identifier nếu định dạng hỗ trợ.
- Metadata về tool sinh SBOM và thời điểm.

Các định dạng phổ biến gồm SPDX và CycloneDX. Chọn định dạng phù hợp công cụ, đối tác và yêu cầu compliance.

### 8.2. SBOM không phải chứng nhận an toàn

SBOM cho biết phần mềm chứa gì, không khẳng định mọi component đều an toàn. Giá trị của nó phụ thuộc độ đầy đủ, độ chính xác, khả năng gắn với đúng artifact digest và việc cập nhật khi dependency thay đổi.

Một SBOM sinh từ source nhưng không tương ứng image cuối cùng có thể bỏ sót OS package hoặc runtime layer. Nên tạo/đối chiếu SBOM ở giai đoạn build artifact và gắn với digest cụ thể.

### 8.3. Sử dụng SBOM khi có lỗ hổng mới

Khi một dependency bị công bố CVE:

1. Xác định package, version và phạm vi bị ảnh hưởng.
2. Tra SBOM để tìm artifact chứa component.
3. Xác định image digest và workload đang chạy.
4. Ưu tiên exposure, exploitability và criticality.
5. Rebuild/release artifact đã vá.
6. Theo dõi rollout và xác minh image cũ không còn chạy.

Nếu không có SBOM, đội ứng cứu thường phải scan lại nhiều artifact hoặc suy luận từ lockfile hiện tại, trong khi image cũ vẫn có thể đang chạy.

## 9. Provenance và attestation

### 9.1. Provenance là gì?

Provenance mô tả artifact được tạo ra như thế nào và từ đâu. Nó có thể chứa:

- Source repository và commit.
- Builder/workflow identity.
- Build invocation và tham số có ý nghĩa.
- Dependency/material reference.
- Thời điểm và loại build.
- Subject artifact và digest.

Provenance giúp người nhận kiểm chứng mối liên hệ giữa source, build process và output. Nó không tự chứng minh source không có lỗ hổng; nó chứng minh nguồn gốc và quy trình theo mức evidence được khai báo.

### 9.2. Attestation

Attestation là tuyên bố có cấu trúc về một subject (ví dụ image digest) do một identity phát hành. Có thể dùng để mang provenance, SBOM, test result hoặc policy evidence. Attestation cần:

- Subject digest xác định chính xác artifact.
- Predicate/type chỉ rõ loại tuyên bố.
- Issuer/builder identity đáng tin.
- Chữ ký hoặc cơ chế integrity được xác minh.
- Thời điểm và context.
- Verification policy phía nhận.

### 9.3. Không tin metadata chỉ vì nó đi cùng image

Attacker có thể tạo file SBOM/provenance giả nếu không có chữ ký hoặc issuer đáng tin. Consumer phải xác minh attestation cryptographically và kiểm tra nội dung policy; không chỉ kiểm tra file tồn tại.

## 10. Ký và xác minh artifact

### 10.1. Vì sao cần ký?

Chữ ký số ràng buộc một artifact/digest với identity có quyền ký. Khi verify, hệ thống kiểm tra:

- Artifact có bị thay đổi sau khi ký không.
- Chữ ký được tạo bởi identity/key nào.
- Key/certificate có được tin cậy và còn hiệu lực không.
- Signature có đúng subject digest không.
- Identity có quyền phát hành cho loại artifact/môi trường đó không.

### 10.2. Cosign và ký container (ví dụ)

Một luồng tham khảo với Cosign:

~~~bash
# Sign an image digest with an approved signing identity
cosign sign registry.example.com/booking/api@sha256:IMAGE_DIGEST

# Verify the signature against the expected identity/issuer
cosign verify \
  --certificate-identity "https://example.com/ci/release" \
  --certificate-oidc-issuer "https://token.actions.example" \
  registry.example.com/booking/api@sha256:IMAGE_DIGEST
~~~

Đây là lệnh minh họa; identity, issuer, keyless/key-based mode và version công cụ phải khớp hệ thống thật. Chỉ chạy verify thành công là chưa đủ nếu policy cần kiểm tra provenance, SBOM hoặc vulnerability threshold.

### 10.3. Quản lý signing key

Signing key là tài sản quan trọng. Bảo vệ bằng KMS/HSM hoặc keyless signing có identity federation phù hợp; giới hạn quyền ký; audit mọi lần ký; rotate theo policy; chuẩn bị quy trình revoke/deny identity sau compromise.

Không để cùng một build job untrusted vừa sửa source vừa có quyền ký release production. Tách bước sign sau khi artifact được kiểm tra và phê duyệt.

### 10.4. Keyless signing

Một số hệ thống dùng OIDC identity ngắn hạn thay vì giữ private signing key lâu dài. Signing service phát certificate gắn với identity/workload và log transparency có thể cung cấp bằng chứng bổ sung. Dù keyless giảm rủi ro lưu private key, policy vẫn phải kiểm tra issuer, subject, audience và workflow identity. Một workflow bị chiếm quyền nhưng được cấp identity hợp lệ vẫn có thể ký artifact độc hại nếu điều kiện phê duyệt yếu.

## 11. Vulnerability scanning và policy triage

### 11.1. Quét ở nhiều lớp

| Lớp | Nội dung | Công cụ/kiểm soát điển hình |
|---|---|---|
| Source | SAST, secret scanning, IaC scan | Phân tích code, phát hiện credential và config nguy hiểm |
| Dependency | SCA và license review | Phân tích package graph và advisory |
| Build | Toolchain, workflow, runner | Pin action, runner image scan, workflow review |
| Image | OS package, language library, malware | Container scanner, SBOM |
| Artifact | Provenance, signature, integrity | Attestation verification |
| Deployment | Manifest, policy và permission | IaC/Kubernetes policy validation |
| Runtime | Behavior, process, network, file | Runtime detection và workload policy |

### 11.2. Severity không phải toàn bộ quyết định

Không nên chỉ dùng CVSS score. Cần cân nhắc:

- Có exploit đã biết hoặc đang bị khai thác không.
- Package vulnerable có thực sự hiện diện và được load không.
- Attack path có thể truy cập từ network/user không.
- Workload có đặc quyền hoặc giữ dữ liệu nhạy cảm không.
- Có mitigation hoặc feature không sử dụng thành phần đó không.
- SLA khắc phục theo criticality và hợp đồng.

### 11.3. Policy ví dụ

Một policy cho production có thể yêu cầu:

- Không có vulnerability critical chưa được chấp nhận ngoại lệ.
- High severity có deadline remediation và owner.
- Không có secret bị phát hiện trong image.
- SBOM và provenance gắn đúng digest.
- Image được ký bởi release identity được phép.
- Base image không hết hỗ trợ.
- Ngoại lệ có lý do, phạm vi, expiration và approver.

Threshold cụ thể phải theo risk appetite và công cụ. Nếu chặn mọi CVE bất kể exploitability hoặc khả năng khắc phục, pipeline có thể bị tắc; nếu bỏ qua mọi finding do quá nhiều false positive, policy mất tác dụng.

## 12. Artifact registry và promotion giữa môi trường

### 12.1. Registry là ranh giới tin cậy

Registry nên hỗ trợ:

- Private repository và authentication.
- Quyền pull/push riêng theo team, project và environment.
- Immutable tag hoặc policy hạn chế overwrite.
- Digest, retention, replication và audit.
- Vulnerability scan/integration.
- Artifact quarantine và deletion/deny policy.

Không cấp quyền push production image cho mọi developer hoặc mọi CI workflow.

### 12.2. Build once, promote the same digest

Một thực hành tốt là build artifact một lần, sau đó promote cùng digest qua staging, pre-production và production:

~~~mermaid
flowchart LR
    BUILD[Build candidate] --> TEST[Test and scan]
    TEST --> SIGN[Sign and attest]
    SIGN --> REG[Immutable registry digest]
    REG --> STAGE[Deploy staging]
    STAGE --> APPROVE[Approval / policy gate]
    APPROVE --> PROD[Deploy same digest to production]
~~~

Không rebuild riêng cho production nếu muốn giữ bằng chứng rằng artifact đã test chính là artifact được triển khai. Cấu hình môi trường có thể khác, nhưng image digest nên được giữ nguyên.

### 12.3. Promotion manifest

Manifest triển khai nên ghi:

- Image digest.
- Release/source commit.
- SBOM và provenance reference.
- Signature verification result.
- Target environment/region.
- Configuration version.
- Approval/change record.

Manifest cũng cần version control và integrity check để ngăn thay digest hoặc target trái phép.

## 13. Admission control và xác minh trước runtime

### 13.1. Admission là lớp xác minh cuối trước khi workload chạy

Admission controller/policy engine có thể kiểm tra yêu cầu tạo hoặc cập nhật workload:

- Registry có nằm trong allowlist không.
- Image được tham chiếu bằng digest không.
- Signature và issuer identity có hợp lệ không.
- Provenance subject có trùng digest không.
- SBOM và scan evidence đáp ứng policy không.
- Namespace/service account có được phép chạy image không.
- Workload có vi phạm policy runtime như privileged/root/hostPath không.

### 13.2. Ví dụ policy dạng khái niệm

~~~yaml
apiVersion: policy.example/v1
kind: ImageTrustPolicy
metadata:
  name: production-image-trust
spec:
  namespaces:
    - production
  requireDigest: true
  allowedRegistries:
    - registry.example.com
  signature:
    required: true
    trustedIssuer: https://token.actions.example
    trustedIdentity: https://example.com/ci/release
  provenance:
    required: true
    sourceRepository: https://example.com/org/booking
  sbom:
    required: true
  vulnerability:
    denyCritical: true
~~~

Đây là policy minh họa, không phải CRD chuẩn của Kubernetes. Schema, engine và cách xác minh phụ thuộc giải pháp được chọn. Cần test policy với image hợp lệ, image không ký, signer sai, digest sai và attestation thiếu.

### 13.3. Fail open hay fail closed?

Production thường cần fail closed với policy nguồn gốc/signature thiết yếu. Tuy nhiên, nếu admission service là dependency tập trung, nó có thể trở thành điểm lỗi triển khai. Cần HA, cache trust metadata có kiểm soát, timeout rõ và quy trình break-glass được audit. Không để một fallback tự động cho phép mọi image khi verifier mất kết nối.

## 14. Bảo vệ IaC và cấu hình triển khai

### 14.1. IaC là một phần của supply chain

Terraform module, Helm chart, Kubernetes manifest, policy file và deployment script có thể mở network, cấp IAM, tắt logging hoặc chạy workload đặc quyền. Cần review và kiểm thử như code:

- Pin provider/module và dependency.
- Scan misconfiguration trước apply.
- Review plan và diff.
- Yêu cầu approval cho production.
- Tách state và identity theo environment.
- Chặn thay đổi IAM/network/storage nhạy cảm nếu không có approval phù hợp.
- Lưu audit của apply và identity thực hiện.

### 14.2. Protect deployment repository

Nếu dùng GitOps, deployment repository trở thành control surface của production. Dùng branch protection, CODEOWNERS, signed commit/tag nếu phù hợp, least privilege cho bot và audit thay đổi. Không để một pull request ứng dụng tự sửa production manifest ngoài quy trình.

### 14.3. Drift detection

So sánh trạng thái thực tế với declarative config để phát hiện thay đổi ngoài quy trình. Drift không phải lúc nào cũng là malicious; có thể do incident response hoặc thao tác khẩn cấp. Cần xác định owner, reason, cách reconcile và audit.

## 15. Runtime verification và phản ứng sau triển khai

### 15.1. Kiểm chứng image đang chạy

Đối chiếu image digest trong workload runtime với promotion manifest và release record. Theo dõi image chạy ngoài allowlist, image tag mutable hoặc workload được tạo bằng service account bất thường.

### 15.2. Runtime controls

- Workload identity ngắn hạn, không nhúng cloud key vào image.
- Network egress allowlist theo nhu cầu.
- Read-only filesystem/non-root và capability tối thiểu.
- Resource limit và seccomp/AppArmor tương ứng.
- Runtime threat detection cho process/network bất thường.
- Audit Kubernetes API hoặc control plane deployment.
- Segmentation giữa workload và namespace.

### 15.3. Khi phát hiện image bị compromise

1. Xác định digest, signer, provenance, source commit và thời điểm phát hành.
2. Tìm mọi workload đang chạy digest bị ảnh hưởng.
3. Đánh giá secret, token, data access và network mà workload có thể đã dùng.
4. Quarantine/deny image và ngăn deploy mới.
5. Revoke signing identity/token nếu bị compromise.
6. Xây artifact sạch từ source/dependency đã xác minh.
7. Deploy bản thay thế và kiểm tra runtime.
8. Rotate credential có nguy cơ bị lộ và điều tra persistence.
9. Bảo toàn evidence, SBOM, log và audit.

Không chỉ xóa image khỏi registry rồi kết thúc sự cố; cluster có thể vẫn chạy image đã pull về node, hoặc deployment controller vẫn giữ manifest cũ.

## 16. Quản lý ngoại lệ và khả năng khôi phục

### 16.1. Security exception

Ngoại lệ cho finding hoặc artifact phải có:

- Finding/policy cụ thể.
- Artifact digest và môi trường bị ảnh hưởng.
- Lý do và business owner.
- Biện pháp giảm thiểu.
- Approver và ngày hết hạn.
- Kế hoạch khắc phục.

Không tạo wildcard exception kiểu “bỏ qua image từ registry này” cho mọi dự án.

### 16.2. Signing key compromise

Nếu signing key bị lộ:

- Thu hồi hoặc deny key/identity theo cơ chế verifier.
- Xác định khoảng thời gian artifact có thể đã được ký giả.
- Liệt kê artifact theo signer và thời điểm.
- Tạm dừng promotion liên quan.
- Tạo identity/key mới và cập nhật trust policy.
- Ký lại artifact từ pipeline sạch sau khi xác minh source.
- Xác minh image đang chạy và manifest đã được cập nhật.

Verifier cần hỗ trợ key revocation/identity deny theo policy. Signature hợp lệ về mặt toán học không có nghĩa vẫn được tin sau khi signer bị compromise.

### 16.3. Registry hoặc CI outage

DR cho supply chain cần bảo vệ:

- Mirror source và artifact ở failure domain phù hợp.
- Cache dependency đã xác minh.
- Pin image digest trong deployment manifest.
- Lưu provenance/SBOM/signature evidence cùng artifact hoặc store độc lập.
- Có quy trình khẩn cấp sử dụng artifact đã được phê duyệt.

Không bỏ verify chữ ký chỉ vì signing service tạm ngừng. Có thể dùng evidence đã lưu và verifier dự phòng nếu tính hợp lệ/thu hồi vẫn kiểm tra được.

## 17. Quan sát và đo hiệu quả

### 17.1. Chỉ số nên theo dõi

| Nhóm | Metric | Ý nghĩa |
|---|---|---|
| Source | Protected branch coverage, review bypass | Mức bảo vệ source |
| Dependency | Dependency update age, critical advisory age | Tốc độ xử lý rủi ro |
| CI/CD | Runner ephemeral ratio, workflow privilege, secret exposure | Mức bảo vệ pipeline |
| Build | Reproducibility rate, trusted builder coverage | Khả năng tin cậy build |
| Artifact | Signed artifact coverage, provenance/SBOM coverage | Bằng chứng nguồn gốc |
| Registry | Immutable digest usage, unauthorized push attempts | Integrity và access control |
| Admission | Rejected unsigned/untrusted image, exception count | Policy enforcement |
| Runtime | Unknown digest workload, vulnerable image age | Mức phơi nhiễm production |
| Response | Time to quarantine, time to redeploy patched image | Hiệu quả ứng cứu |

### 17.2. Tránh metric cardinality và log lộ dữ liệu

Không đưa toàn bộ commit, user, package hoặc image ID thành label metric có cardinality không giới hạn. Dùng metric tổng hợp và structured event có retention/access phù hợp. Log không được chứa token, signing secret hoặc credential.

### 17.3. Dashboard theo release

Một dashboard hữu ích nối từ release tới runtime:

Source commit → workflow run → build identity → artifact digest → SBOM/provenance → signature → approval → deployment → running digest.

Khi có incident, người trực có thể lần theo chuỗi này để xác định phạm vi thay vì tìm thủ công trong nhiều hệ thống.

## 18. Ví dụ end-to-end: phát hành Booking API

### 18.1. Pipeline đề xuất

~~~mermaid
sequenceDiagram
    participant Dev as Developer
    participant Git as Source repository
    participant CI as Trusted CI
    participant Reg as Artifact registry
    participant Gate as Verification / admission
    participant K8s as Production cluster
    Dev->>Git: Pull request
    Git->>Git: Review and required checks
    Git->>CI: Merge approved commit
    CI->>CI: Build, test, scan
    CI->>CI: Generate SBOM and provenance
    CI->>CI: Sign image digest
    CI->>Reg: Push immutable image
    Reg->>Gate: Candidate digest and evidence
    Gate->>Gate: Verify signer, provenance, policy
    Gate->>K8s: Approve deployment
    K8s->>K8s: Admission verifies image
    K8s->>K8s: Run exact approved digest
~~~

### 18.2. Release record

~~~yaml
release:
  service: booking-api
  sourceCommit: 8f31a7c
  image: registry.example.com/booking/api@sha256:IMAGE_DIGEST
  sbom: sbom://booking-api/sha256:IMAGE_DIGEST
  provenance: attestation://booking-api/sha256:IMAGE_DIGEST
  signerIdentity: https://example.com/ci/release
  environment: production
  approval: change-4821
~~~

Đây là release record minh họa. Trong triển khai thực tế, các reference phải trỏ tới evidence có integrity control; không dùng giá trị tượng trưng và không đưa secret vào manifest.

### 18.3. Kịch bản incident

Một dependency trong image được phát hiện có lỗ hổng nghiêm trọng sau khi production triển khai. Nhóm dùng SBOM để xác định image digest có package bị ảnh hưởng; tra release record để biết commit và builder; tìm workload chạy digest đó; build phiên bản dependency đã vá; chạy test/scan; ký và attestation artifact mới; promotion cùng digest; admission kiểm tra; runtime dashboard xác nhận image cũ đã biến mất.

Nếu phát hiện source hoặc workflow bị compromise, cần mở rộng điều tra tới các artifact được ký bởi cùng identity trong khoảng thời gian liên quan, không chỉ sửa package và rebuild.

## 19. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Tin mọi image nằm trong registry nội bộ | Image có thể bị push trái phép | Signature, provenance và registry ACL |
| Deploy bằng tag mutable | Tag có thể trỏ sang image khác | Pin digest |
| Chỉ scan source | Bỏ sót OS package và runtime layer | Quét image và tạo SBOM cho artifact cuối |
| Không lock dependency | Build thay đổi ngoài dự kiến | Lockfile và integrity verification |
| CI job có production secret | Dependency độc hại có thể lấy credential | Runner cô lập và OIDC ngắn hạn |
| Dùng action theo tag không pin | Nội dung pipeline có thể đổi | Pin commit digest và review update |
| Build và deploy cùng quyền | Compromise build có thể tự deploy | Tách identity và approval |
| SBOM không gắn digest | Không biết nó mô tả image nào | Bind SBOM/attestation với subject digest |
| Chữ ký hợp lệ được coi là đủ | Signer có thể bị compromise hoặc không được phép | Verify identity, issuer, provenance và policy |
| Quét xong nhưng không có admission | Workload không đạt policy vẫn có thể chạy | Enforce trước deploy và ở cluster |
| Rebuild production riêng | Artifact đã test khác artifact deploy | Build once, promote same digest |
| Xóa image registry là xong incident | Node vẫn có image và workload đang chạy | Quarantine, rollout thay thế và runtime inventory |
| Ngoại lệ không hết hạn | Policy dần bị vô hiệu hóa | Exception có owner, scope và expiry |

## 20. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Biện pháp và đánh đổi |
|---|---|---|
| **Operational Excellence** | Có truy vết từ commit tới image đang chạy và runbook thu hồi không? | Release record, dashboard và automation; cần duy trì evidence |
| **Security** | Ai có thể sửa source, build, ký, push và deploy? | Least privilege, OIDC, runner isolation, signing và admission |
| **Reliability** | Artifact có thể tái tạo và phục hồi khi CI/registry lỗi không? | Mirror, immutable artifact, recovery procedure; tốn storage và công vận hành |
| **Performance Efficiency** | Scan/verify có làm chậm pipeline hoặc runtime startup quá mức? | Scan song song, cache đã xác minh, admission HA và policy tối ưu |
| **Cost Optimization** | Có lưu quá nhiều image/SBOM/log hay scan trùng lặp không? | Retention theo criticality, dedup và chia sẻ evidence |
| **Sustainability** | Có rebuild, truyền image và scan lặp không cần thiết? | Build cache đáng tin, artifact promotion, incremental scanning khi hỗ trợ |

Chuỗi cung ứng đáng tin không phải chỉ là mua scanner hoặc bật ký image. Cần nối identity, source, builder, artifact, policy và runtime thành một chuỗi bằng chứng có thể kiểm tra.

## 21. Bài tập áp dụng

### Bài tập A — Tag bị ghi đè

Staging đã kiểm thử image tag release-42. Trước khi deploy production, tag bị ghi đè bằng image khác nhưng vẫn cùng tên.

**Câu hỏi:** Làm sao ngăn tình huống này?

**Gợi ý:** Dùng immutable digest trong promotion manifest, registry policy hạn chế overwrite và verify signature/provenance của đúng digest trước deploy.

### Bài tập B — CI secret bị lộ

Một pull request từ fork chạy workflow có quyền đọc cloud access key dài hạn.

**Câu hỏi:** Ranh giới trust bị vi phạm ở đâu?

**Gợi ý:** Untrusted code được thực thi trong job có secret đặc quyền. Tách workflow, không cấp secret cho fork job, dùng runner cô lập và OIDC identity giới hạn theo repository/branch/environment.

### Bài tập C — SBOM không khớp image

Pipeline tạo SBOM từ source dependency manifest nhưng image runtime chứa thêm OS packages từ base image.

**Câu hỏi:** Vì sao evidence chưa đầy đủ?

**Gợi ý:** SBOM không bao phủ artifact cuối. Tạo/đối chiếu SBOM trên image digest sau build và gắn subject digest vào attestation.

### Bài tập D — Signer bị compromise

Một signing identity bị lộ nhưng image đã ký trước đó vẫn verify thành công về mặt chữ ký.

**Câu hỏi:** Có nên tiếp tục tin mọi image đã ký?

**Gợi ý:** Không. Thu hồi/deny identity theo thời gian và policy, xác định artifact trong khoảng ảnh hưởng, điều tra workflow và phát hành lại artifact sạch.

### Bài tập E — Admission service unavailable

Cluster không kết nối được verifier khi cần deploy hotfix.

**Câu hỏi:** Có nên tắt signature verification toàn cluster?

**Gợi ý:** Không nên tạo fail-open mặc định. Dự phòng verifier, cache evidence có integrity và validity policy, hoặc break-glass có phạm vi/thời hạn/approval/audit; chỉ dùng artifact đã được xác minh trước đó.

### Bài tập F — CVE mới trong dependency bắc cầu

Một package ở sâu trong dependency tree bị công bố lỗ hổng. Nhóm không biết image nào đang chứa package này.

**Câu hỏi:** Evidence nào giúp xác định phạm vi nhanh?

**Gợi ý:** SBOM gắn digest, inventory workload đang chạy, release provenance và dependency advisory mapping. Từ đó ưu tiên workload exposure, rebuild/promotion và xác minh digest cũ đã được thay.

## 22. Checklist trước khi đưa supply chain controls vào production

- [ ] Đã lập inventory source, dependency, builder, runner, registry, artifact và deployment controller.
- [ ] Branch/release protection và review owner áp dụng cho source, workflow, IaC và deployment config.
- [ ] Dependency được lock, kiểm tra integrity và lấy từ registry/namespace đáng tin.
- [ ] Build runner được cô lập, ephemeral khi phù hợp và không chia sẻ secret giữa trust level.
- [ ] CI job có quyền tối thiểu; production access dùng identity ngắn hạn/OIDC khi khả thi.
- [ ] Action/plugin/toolchain được pin và cập nhật qua review.
- [ ] Build không nhúng secret vào source, image layer, artifact hay log.
- [ ] Container base image có nguồn tin cậy, digest/version rõ và được cập nhật.
- [ ] Runtime image tối giản, non-root, read-only/capability hạn chế khi phù hợp.
- [ ] Artifact được định danh bằng digest và registry có ACL/immutability/audit.
- [ ] SBOM mô tả artifact cuối và gắn với đúng digest.
- [ ] Provenance chứng minh source, builder và build context theo policy.
- [ ] Signature được tạo bởi identity được phép và có quy trình revoke/rotation.
- [ ] Deployment verify digest, signature, issuer, provenance và policy.
- [ ] Admission control chặn image không tin cậy và có HA/break-glass audit.
- [ ] IaC/deployment manifest được review, scan, version hóa và phát hiện drift.
- [ ] Dashboard nối source commit tới image digest đang chạy.
- [ ] Có quy trình quarantine, rebuild, rotate credential và thu hồi signer khi compromise.
- [ ] Exception có owner, lý do, phạm vi, mitigation và expiry.
- [ ] Restore/mirror CI, artifact registry, signing evidence và runbook đã được diễn tập.

**Điểm cốt lõi:** phần mềm chỉ đáng tin khi tổ chức có thể chứng minh artifact production bắt nguồn từ source và builder được phép, chứa dependency đã biết, có SBOM/provenance phù hợp, được ký bởi identity đáng tin và được policy xác minh trước khi chạy. Pin digest, bảo vệ CI/CD, tách quyền build/deploy, admission control và runtime monitoring tạo thành các lớp liên tục từ commit đến production.
