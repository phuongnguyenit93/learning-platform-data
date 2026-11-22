# Build một lần và chuyển cùng artifact qua các môi trường

> **Chương:** Phân phối phần mềm  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Bài học tập trung vào việc tạo artifact bất biến một lần, kiểm chứng nguồn gốc và chất lượng, rồi promote đúng artifact qua development, staging và production; đồng thời quản lý cấu hình, secret, phê duyệt, triển khai và phục hồi theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích nguyên tắc build một lần, promote nhiều môi trường và lý do phải định danh artifact bằng version/digest bất biến.
2. Phân biệt source code, build output, package, container image, deployment bundle, configuration và runtime state.
3. Thiết kế pipeline tạo artifact có thể tái lập, có provenance, SBOM, chữ ký và bằng chứng kiểm thử.
4. Tách cấu hình môi trường và secret khỏi artifact, đồng thời xác minh compatibility trước khi deploy.
5. Thiết kế luồng promotion, release gate, approval, progressive delivery và kiểm soát quyền.
6. Xử lý database migration, feature flag, dependency và thay đổi cấu hình mà không phá tính nhất quán giữa các môi trường.
7. Lập chiến lược rollback/roll-forward, kiểm tra artifact đang chạy và quản lý ngoại lệ có thể kiểm toán.

## 1. Nguyên tắc build một lần, promote cùng artifact

Một phần mềm thường được triển khai qua nhiều môi trường: development, test, staging, pre-production và production. Mỗi môi trường giúp kiểm tra một nhóm giả định khác nhau trước khi phần mềm phục vụ người dùng thật.

Nguyên tắc **build once, promote the same artifact** yêu cầu:

- Build artifact từ một source revision bằng pipeline được kiểm soát.
- Định danh artifact bằng version bất biến hoặc digest.
- Kiểm thử và kiểm tra chính artifact đó.
- Promote cùng artifact qua các môi trường, không build lại ở mỗi môi trường.
- Chỉ thay đổi cấu hình và secret theo môi trường thông qua cơ chế runtime/configuration được quản lý.
- Lưu bằng chứng về source, build, test, approval và deployment.

Ví dụ: pipeline tạo container image booking-api với digest sha256:abc.... Staging và production phải chạy image có cùng digest đó. Production không được tạo một image khác từ cùng tag hoặc chạy lại Docker build với bộ dependency mới.

Điều này giúp trả lời câu hỏi sau khi có sự cố: chính xác artifact nào đã được kiểm thử, phê duyệt và chạy trong production?

### 1.1. Vì sao build lại ở mỗi môi trường nguy hiểm?

Nếu mỗi môi trường chạy build riêng, đầu ra có thể khác do:

- Dependency hoặc base image được cập nhật giữa các lần build.
- Build tool, compiler, plugin hoặc runner khác version.
- Environment variable vô tình ảnh hưởng vào compile/bundle.
- Package registry trả về phiên bản mới hoặc artifact đã bị thay thế.
- Build script lấy thời gian hiện tại, dữ liệu ngoài hoặc kết quả không xác định.
- Patch thủ công chỉ được áp dụng ở một môi trường.
- Người vận hành chạy lệnh khác với pipeline đã kiểm thử.

Source commit giống nhau không đảm bảo binary giống nhau. Cùng tag image cũng không đảm bảo nội dung image không đổi nếu tag có thể bị ghi đè.

### 1.2. Build once không có nghĩa một binary dùng mọi cấu hình

Một artifact bất biến vẫn cần cấu hình phù hợp môi trường: endpoint database, hostname, replica count, resource limits, logging level, feature flags và secret reference.

Điểm cốt lõi là không đóng các giá trị phụ thuộc môi trường vào binary/image nếu có thể cung cấp chúng lúc deploy hoặc runtime. Artifact phải giữ nguyên; cấu hình được version hóa hoặc quản lý riêng, có policy và audit.

## 2. Phân biệt các thành phần của software release

| Thành phần | Nội dung | Có thay đổi khi promote không? |
| --- | --- | --- |
| Source revision | Commit/tag và nội dung source | Là đầu vào build, không thay cho release đã build |
| Build recipe | Toolchain, dependency lock, compiler, build instructions | Cố định và có version |
| Artifact | Binary, package, image hoặc deployment bundle | **Không** |
| Artifact digest | Định danh nội dung bằng hash | Không đổi nếu artifact không đổi |
| Configuration | Endpoint, feature setting, resource profile, non-secret values | Có thể khác theo môi trường |
| Secret | Password, token, key, certificate private key | Khác theo môi trường; lấy từ secret manager |
| Deployment manifest | Cách triển khai artifact vào nền tảng | Có thể có overlay theo môi trường, phải version hóa |
| Runtime state | Database, cache, queue, session, volume | Thay đổi khi ứng dụng hoạt động |
| Release metadata | Approval, test evidence, provenance và deployment history | Bổ sung theo mỗi lần promotion |

Một pipeline có thể tạo nhiều loại artifact cùng lúc: image API, image worker, frontend bundle, migration package, SBOM và deployment chart. Mỗi artifact cần định danh rõ và liên kết với cùng release/source context.

Không gộp secret vào artifact hoặc commit secret vào configuration repository. Configuration và deployment manifest có thể chứa endpoint nội bộ hoặc thông tin vận hành nhạy cảm nên cũng cần phân quyền phù hợp.

## 3. Mô hình luồng từ source tới production

~~~mermaid
flowchart LR
    SRC["Source commit"] --> BUILD["Controlled build"]
    BUILD --> ART["Immutable artifact"]
    BUILD --> META["Provenance + SBOM"]
    ART --> VERIFY["Scan / sign / verify"]
    META --> VERIFY
    VERIFY --> DEV["Deploy development"]
    DEV --> TEST1["Automated tests"]
    TEST1 --> STAGE["Promote same digest to staging"]
    STAGE --> TEST2["Integration / acceptance / performance"]
    TEST2 --> APPROVE["Release approval"]
    APPROVE --> PROD["Promote same digest to production"]
    PROD --> OBS["Health / SLO / audit"]
~~~

Luồng khái niệm:
1. Developer merge source revision vào nhánh được bảo vệ.
2. CI build artifact bằng toolchain và dependency đã khóa.
3. Pipeline tạo provenance, SBOM, checksum/digest và test report.
4. Artifact được scan, ký hoặc attest theo policy.
5. Artifact được deploy vào development để kiểm tra sớm.
6. Cùng digest được promote sang staging để kiểm tra tích hợp và acceptance.
7. Release gate xác minh test, change, approval và trạng thái production.
8. Cùng digest được promote vào production theo chiến lược rollout.
9. Runtime telemetry, release metadata và deployment record được lưu.

Thứ tự stage có thể khác theo tổ chức. Điều cần giữ là artifact được promote vẫn là artifact đã được kiểm tra và danh tính của nó có thể xác minh ở mọi bước.

## 4. Tạo artifact bất biến và định danh đúng

### 4.1. Version và digest

Version con người đọc được hữu ích cho release notes, nhưng không phải lúc nào cũng đủ để xác định nội dung.

Ví dụ:
- Semantic version: 1.8.2.
- Build version: 1.8.2+build.417.
- Container reference: registry.example.com/booking-api:1.8.2.
- Immutable reference: registry.example.com/booking-api@sha256:....

Tag giúp tìm artifact; digest xác định nội dung. Với production, nên deploy theo digest hoặc cơ chế tương đương bảo đảm immutable identity. Registry cần policy ngăn ghi đè artifact đã phát hành và lưu retention đủ cho rollback/audit.

### 4.2. Artifact promotion

Promotion là hành động cho phép một artifact đã tồn tại được sử dụng trong môi trường cao hơn sau khi đáp ứng gate. Nó không phải build lại artifact.

Một promotion record nên lưu:
- Artifact URI và digest.
- Source revision và build ID.
- Build recipe/toolchain reference.
- Provenance/attestation và SBOM reference.
- Test evidence của artifact.
- Môi trường đích, configuration revision và deployment manifest.
- Người yêu cầu, người phê duyệt, thời gian và lý do.
- Kết quả rollout, health check và rollback reference.

### 4.3. Immutable registry

Registry cần:
- Repository/project riêng hoặc policy phân quyền theo môi trường.
- Push chỉ từ trusted build identity.
- Pull từ deploy identity được cấp quyền.
- Immutable release tags hoặc deploy-by-digest.
- Scan và retention policy.
- Audit push/pull/delete/replication.
- Replicate artifact tới region/registry DR nếu yêu cầu recovery.
- Không cho phép operator sửa nội dung tag release đã được phê duyệt.

Private registry không tự động bảo đảm artifact đáng tin cậy. Cần kiểm chứng ai build, build từ source nào, dependency gì và có bị thay thế sau khi kiểm thử hay không.

## 5. Build có thể tái lập và kiểm soát dependency

### 5.1. Reproducible build

Một build có khả năng tái lập giúp cùng source và inputs đã định nghĩa tạo ra đầu ra có thể xác minh. Không phải mọi hệ thống đều đạt bit-for-bit reproducibility ngay, nhưng cần giảm nguồn biến đổi không được kiểm soát.

Các yếu tố:
- Pin compiler, runtime, build tool và plugin version.
- Dùng lockfile cho dependency và kiểm tra lockfile trong CI.
- Dùng base image theo digest hoặc version bất biến.
- Không tải dependency phiên bản nổi trong build production.
- Ghi lại build arguments và toolchain identity.
- Hạn chế dependency lấy từ nguồn không tin cậy.
- Kiểm soát clock, locale, timezone và bước generate có tính không xác định.
- Tách build khỏi deployment environment.
- Dùng runner chuẩn, được vá và có quyền tối thiểu.

### 5.2. Ví dụ Dockerfile multi-stage

~~~dockerfile
# syntax=docker/dockerfile:1
FROM node:22-alpine@sha256:REPLACE_WITH_VERIFIED_DIGEST AS build
WORKDIR /src

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run test
RUN npm run build

FROM nginx:stable-alpine@sha256:REPLACE_WITH_VERIFIED_DIGEST AS runtime
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
USER 101
CMD ["nginx", "-g", "daemon off;"]
~~~

Digest trong ví dụ phải được thay bằng digest đã xác minh từ registry tin cậy. Cấu hình nginx, quyền đọc/ghi, cổng non-root, health check và logging cần điều chỉnh phù hợp ứng dụng. Ví dụ minh họa khóa base image và dùng lockfile; chưa phải Dockerfile production hoàn chỉnh cho mọi workload.

### 5.3. Build không nên phụ thuộc cấu hình production

Không truyền production database password vào build. Không tải dữ liệu production để compile hoặc tạo image. Không gắn environment-specific endpoint vào source ở bước build. Nếu frontend cần cấu hình API endpoint, cân nhắc runtime configuration file hoặc config endpoint được bảo vệ để cùng một static bundle có thể promote.

## 6. Provenance, SBOM và chữ ký artifact

### 6.1. Provenance

Provenance mô tả nguồn gốc và quá trình tạo artifact, chẳng hạn:
- Source repository và revision.
- Builder/workflow identity.
- Build process và parameters.
- Dependency/source materials.
- Artifact digest và thời điểm build.
- Liên kết tới build logs và test evidence.

Provenance giúp xác minh artifact thực sự được tạo bởi pipeline tin cậy từ source được chấp thuận. Nó có giá trị khi điều tra supply-chain incident hoặc so sánh môi trường đang chạy.

### 6.2. SBOM

Software Bill of Materials liệt kê thành phần phần mềm và dependency trong artifact. SBOM hỗ trợ:
- Xác định sản phẩm bị ảnh hưởng khi thư viện có lỗ hổng.
- Theo dõi dependency trực tiếp và bắc cầu.
- Kiểm tra license và nguồn gốc package.
- Hỗ trợ risk assessment và audit.

SBOM cần liên kết chính xác với artifact digest. Một SBOM tạo từ source revision khác hoặc image khác không chứng minh nội dung image đang chạy.

### 6.3. Signing và verification

Pipeline có thể ký artifact hoặc attestation bằng signing identity được bảo vệ. Deployment gate xác minh:
- Signature hợp lệ và key/identity tin cậy.
- Digest trong signature trùng artifact được deploy.
- Provenance do builder được chấp thuận tạo.
- Build source/branch/workflow đáp ứng policy.
- SBOM và scan evidence đáp ứng tiêu chí.
- Artifact chưa bị revoke hoặc quarantined.

~~~mermaid
flowchart TD
    A["Artifact + digest"] --> B["Generate provenance / SBOM"]
    B --> C["Sign artifact or attestation"]
    C --> D["Store in trusted registry"]
    D --> E["Deployment verifier"]
    E --> F{"Identity, digest and policy valid?"}
    F -->|"Yes"| G["Allow promotion"]
    F -->|"No"| H["Block and emit finding"]
~~~

Signature chỉ chứng minh artifact được ký bởi identity tương ứng và nội dung phù hợp với digest đã ký. Nó không chứng minh code an toàn hoặc không có lỗ hổng. Cần kết hợp source review, test, scanning, policy và runtime monitoring.

## 7. Kiểm thử chính artifact sẽ được promote

Test report cần liên kết với digest/build ID để chứng minh đối tượng nào đã được kiểm thử.

Các lớp kiểm thử:
- Unit và component tests.
- Static analysis, lint và type checks.
- Dependency/vulnerability scanning.
- Container/image scanning.
- Integration tests với service/database/broker tương thích.
- Contract tests giữa producer/consumer.
- End-to-end và acceptance tests.
- Performance/load tests ở mức rủi ro phù hợp.
- Security tests và policy checks.
- Smoke test sau deploy.
- Migration/restore/rollback test khi artifact có thay đổi dữ liệu.

### 7.1. Test trên đúng artifact

Một cách làm an toàn:
1. Build image/package một lần.
2. Chạy unit test trong pipeline với source/build outputs.
3. Scan và ký artifact.
4. Deploy image digest vào môi trường test.
5. Chạy integration/E2E trên image được tham chiếu đúng digest.
6. Promote digest đã test sang staging.
7. Kiểm thử acceptance/performance trên cùng digest.
8. Sau deploy production, xác minh runtime image digest và health.

Nếu staging chạy mutable tag, test pass không chứng minh production đang chạy cùng image. Nếu production build lại, test trước đó có thể không còn áp dụng chính xác cho artifact mới.

### 7.2. Test evidence và release gate

| Gate | Điều kiện mẫu | Bằng chứng |
| --- | --- | --- |
| Source | Review, branch protection và commit được phép | PR/commit metadata |
| Build | Build thành công bằng builder tin cậy | Build ID, logs, provenance |
| Artifact | Digest, signature, SBOM hợp lệ | Registry metadata, attestation |
| Security | Không có finding vượt ngưỡng policy | Scan report, exception reference |
| Functional | Test bắt buộc pass | Test report gắn digest |
| Integration | Contract và dependency tương thích | Integration test result |
| Performance | Không vượt regression threshold đã duyệt | Benchmark report |
| Change | Kế hoạch, owner, risk và approval đầy đủ | Change record |
| Deployment | Health, SLI/SLO và runtime digest đúng | Deployment/telemetry record |

Gate cần có policy cụ thể, không chỉ trạng thái xanh/đỏ. Ngoại lệ security phải liên kết với exception record và đúng authority; không bỏ qua finding bằng cách sửa nhãn scan.

## 8. Tách configuration và secrets khỏi artifact

### 8.1. Configuration theo môi trường

Cùng một artifact có thể chạy trong nhiều môi trường bằng cấu hình khác nhau:

| Thuộc tính | Development | Staging | Production |
| --- | --- | --- | --- |
| API endpoint | Dev service URL | Staging URL | Production URL |
| Database | Database test | Dataset staging | Database production |
| Replicas | Ít | Gần cấu hình production | Theo capacity/SLO |
| Logging | Debug có giới hạn | Info/diagnostic | Policy production |
| Feature flag | Thử nghiệm | Theo kế hoạch release | Rollout theo approval |
| External provider | Sandbox | Sandbox/pre-prod | Live provider |
| Secret | Secret dev | Secret staging | Secret production riêng |
| Data | Synthetic/test | Masked hoặc synthetic | Data production theo policy |

Cấu hình nên có schema, type, validation, owner, version và audit. Không dùng một file cấu hình copy thủ công giữa môi trường mà không có kiểm soát.

### 8.2. Runtime configuration

Một ứng dụng có thể đọc configuration lúc khởi động hoặc qua config service. Cần quyết định:
- Khi config thay đổi, ứng dụng reload hay cần restart?
- Config version nào đang được dùng?
- Làm sao rollback config riêng khỏi artifact?
- Có validate config trước deploy không?
- Nếu config service unavailable thì dùng config đã cache hay fail?
- Cấu hình nhạy cảm có bị log trong startup message không?

Configuration drift giữa staging và production có thể giải thích vì sao cùng image hoạt động khác nhau. Cần lưu config revision và so sánh các thuộc tính ảnh hưởng behavior, đồng thời cho phép endpoint/secret thực sự khác nhau.

### 8.3. Secrets

Secret phải được quản lý riêng theo environment:
- Dùng secret manager/vault; không đưa secret vào source, image layer hoặc build argument.
- Cấp quyền đọc bằng workload identity tại runtime.
- Mỗi môi trường có secret riêng; staging không dùng credential production.
- Rotation và revocation có quy trình.
- Tránh in environment variables hoặc config nhạy cảm vào logs.
- Audit secret retrieval và giới hạn export.
- Cân nhắc cách inject secret để tránh lưu không cần thiết trên filesystem.

Một secret reference có thể nằm trong deployment config; giá trị secret không được đóng gói vào artifact. Secret rotation không nên buộc build lại ứng dụng nếu runtime có cơ chế đọc secret an toàn.

## 9. Deployment manifest và môi trường

Cùng artifact không có nghĩa mọi môi trường phải dùng manifest giống tuyệt đối. Replica count, ingress, service account, resource requests, network policy và storage có thể khác; nhưng phần thay đổi phải được quản lý, review và kiểm tra.

Có thể dùng:
- Helm chart với values riêng từng môi trường.
- Kustomize overlays.
- Terraform/Pulumi hoặc IaC tương đương.
- GitOps desired state.
- Configuration management có version.

### 9.1. Ví dụ Kubernetes Deployment theo digest

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: booking-api
  namespace: production
spec:
  replicas: 4
  selector:
    matchLabels:
      app: booking-api
  template:
    metadata:
      labels:
        app: booking-api
    spec:
      serviceAccountName: booking-api
      containers:
        - name: api
          image: registry.example.com/booking-api@sha256:REPLACE_WITH_APPROVED_DIGEST
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: APP_ENV
              value: production
            - name: CONFIG_REF
              value: booking-api/production/42
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
~~~

Digest là placeholder và cần được thay bằng digest đã qua release gate. Config reference không chứa secret. Manifest cần được kiểm tra user, volume, filesystem write path, network policy, probes, rollout strategy và resource values theo workload.

### 9.2. So sánh cấu hình môi trường

Có thể sinh manifest cuối cùng trước deploy và lưu checksum/commit của cấu hình. Review diff giữa staging và production để phát hiện khác biệt ngoài dự kiến: service account, ingress exposure, database migration setting, feature flags hoặc resource limit.

Không nên ép production dùng nguyên cấu hình staging nếu điều đó làm sai sizing hoặc bảo mật. Mục tiêu là mọi khác biệt đều có chủ đích, owner và có thể giải thích.

## 10. Promotion pipeline và release gate

### 10.1. Luồng promotion

~~~mermaid
flowchart TD
    A["Commit được review"] --> B["Build once"]
    B --> C["Artifact + digest + provenance"]
    C --> D["Scan / sign / test"]
    D --> E["Development"]
    E --> F["Functional / component tests"]
    F --> G["Staging"]
    G --> H["Integration / acceptance / performance"]
    H --> I{"All release gates pass?"}
    I -->|"No"| J["Block / investigate / rebuild from new source if changed"]
    I -->|"Yes"| K["Approval / change window"]
    K --> L["Production canary"]
    L --> M{"Health and SLO pass?"}
    M -->|"No"| N["Rollback or halt rollout"]
    M -->|"Yes"| O["Progressive rollout"]
    O --> P["Verify deployed digest and record release"]
~~~

Khi source code thay đổi để sửa lỗi, artifact mới cần build lại và kiểm thử theo mức phù hợp. Không sửa trực tiếp image hoặc package đã được ký rồi tiếp tục dùng digest cũ.

### 10.2. Promotion policy

Release gate có thể yêu cầu:
- Artifact thuộc release train/branch được phép.
- Digest nằm trong trusted registry.
- Signature và provenance hợp lệ.
- Scan report còn trong thời hạn phù hợp và không có finding vượt ngưỡng.
- Test evidence gắn đúng digest.
- Config/manifest validation thành công.
- Database migration tương thích.
- Change approval còn hiệu lực và đúng scope.
- Production capacity và maintenance constraints được đáp ứng.

### 10.3. Separation of duties

Người viết code không nên có quyền tự sửa release evidence hoặc deploy trực tiếp production ngoài quy trình. Có thể tách:
- Developer: source change.
- CI builder: build và attest.
- Release manager/change approver: chấp thuận promotion theo policy.
- Deploy identity: thực thi deployment.
- Security gate: xác minh artifact và policy.
- SRE/validator: xác minh health và release outcome.

Đội nhỏ có thể dùng kiểm soát thay thế, nhưng cần rõ quyền, audit và giới hạn phạm vi.

## 11. Database migration và compatibility

Build once/promote same artifact không có nghĩa mọi thứ liên quan release phải bất biến tuyệt đối. Database schema và dữ liệu runtime thay đổi theo migration, do đó phải được quản lý riêng và tương thích với rollout.

### 11.1. Expand-and-contract

Với ứng dụng cần rolling deployment, một chiến lược phổ biến là:

1. **Expand:** thêm field/table/index mới, giữ cấu trúc cũ hoạt động.
2. Deploy phiên bản ứng dụng mới đọc/ghi tương thích với cả schema cũ và mới.
3. Backfill dữ liệu theo batch có kiểm soát.
4. Xác minh mọi instance/consumer đã chuyển sang field mới.
5. **Contract:** xóa field cũ trong release sau, khi không còn consumer sử dụng.

~~~mermaid
flowchart LR
    A["Schema v1"] --> B["Expand: add new field"]
    B --> C["App v2 reads old + new"]
    C --> D["Backfill and verify"]
    D --> E["All consumers use new field"]
    E --> F["Contract: remove old field"]
~~~

Migration không nên giả định rollback code tự động rollback database. Xóa cột hoặc đổi semantics có thể không đảo ngược an toàn. Cần backup, compatibility test, migration lock, timeout và forward recovery.

### 11.2. Migration là một release input có version

Migration script/version nên được version hóa và phát hành kèm release metadata. Tuy nhiên migration thực thi trên trạng thái dữ liệu của từng môi trường, nên side effect khác nhau. Cần lưu:
- Migration package/version và checksum.
- Schema version trước/sau.
- Người hoặc workflow thực hiện.
- Kết quả và thời gian.
- Backfill state/checkpoint.
- Recovery/forward-fix plan.

Không chạy migration production bằng script khác với bản đã review/test ở staging mà không có change record.

## 12. Feature flags và progressive delivery

Một artifact có thể chứa chức năng mới nhưng chỉ bật ở một nhóm user/tenant bằng feature flag. Điều này giúp tách deploy code khỏi release tính năng.

Cần quản lý:
- Flag key, owner, purpose và expiry/removal date.
- Default state an toàn.
- Rule theo tenant/region/cohort đã được phê duyệt.
- Audit ai bật/tắt flag.
- Dependency và compatibility nếu flag thay đổi schema/API.
- Kill switch cho chức năng có rủi ro.
- Kiểm thử cả flag on/off và kết hợp flag.

Flag không thay thế quyền truy cập. Không dùng flag như cơ chế authorization nếu việc bật/tắt không được ràng buộc với identity và policy.

### 12.1. Progressive rollout

Có thể rollout theo:
- Internal/canary users.
- 1% → 5% → 25% → 50% → 100% traffic.
- Một nhóm tenant hoặc region có blast radius nhỏ.
- Blue/green hoặc rolling deployment.

Mỗi bước cần thời gian quan sát đủ dài, metric guardrail và điều kiện tự dừng. Nếu p95, error rate, business success hoặc data correctness vi phạm ngưỡng, pipeline phải halt hoặc rollback theo runbook.

## 13. Rollback, roll-forward và artifact retention

### 13.1. Rollback phải dùng artifact đã biết tốt

Registry cần giữ digest cũ phù hợp chính sách retention và thời gian recovery. Rollback nghĩa là deploy lại artifact đã được kiểm chứng, cùng configuration/migration state tương thích.

Không rollback bằng cách rebuild source tag cũ. Dependency có thể đã thay đổi và artifact mới tạo không còn giống artifact lịch sử.

### 13.2. Khi nào roll-forward tốt hơn?

Rollback có thể không an toàn nếu:
- Database migration đã xóa/biến đổi dữ liệu không tương thích.
- API/event schema mới đã được consumer khác sử dụng.
- Side effect bên ngoài đã xảy ra.
- Security vulnerability khiến artifact cũ không được phép chạy.
- Rollback làm mất dữ liệu đã ghi bởi phiên bản mới.

Khi đó, có thể cần roll-forward bằng release sửa lỗi, tắt feature flag, phục hồi data hoặc chạy compensation. Quyết định dựa trên trạng thái dữ liệu và business semantics, không chỉ việc deploy tool có lệnh rollback.

### 13.3. Artifact retention

Chính sách lưu artifact phải cân bằng:
- Thời gian audit và điều tra.
- Nhu cầu rollback và DR.
- Dung lượng registry và cost.
- Lỗ hổng mới phát hiện sau release.
- Nghĩa vụ license, provenance và SBOM retention.

Artifact có lỗ hổng nghiêm trọng có thể cần quarantine/revoke khỏi promotion dù được giữ để phục vụ điều tra. Phải phân biệt giữ bằng chứng với cho phép triển khai lại.

## 14. Bảo mật chuỗi cung ứng và môi trường triển khai

Artifact đi qua nhiều trust boundary: source repository, build runner, package registry, image registry, artifact store, deployment controller và runtime.

Kiểm soát cần có:
- MFA, branch protection và code review cho repository.
- Build runner cô lập; credential ngắn hạn và scope hẹp.
- Dependency pinning, scanning và policy.
- SBOM/provenance và signing.
- Registry private, immutable và audit.
- Promotion chỉ theo digest đã xác minh.
- Deploy identity riêng từng environment.
- Admission/runtime verification khi nền tảng hỗ trợ.
- Quản lý secret ngoài artifact.
- Audit config và release changes.
- Incident process để revoke signing identity, quarantine artifact và redeploy known-good version.

### 14.1. Bảo vệ artifact khi sao chép/promote

Khi artifact được replicate giữa region hoặc registry:
- Verify digest sau replication.
- Kiểm tra permission, retention và encryption ở registry đích.
- Ghi lại nguồn/đích và thời điểm copy.
- Không tạo tag mới bằng cách build lại.
- Nếu registry đích biến đổi nội dung do conversion/packaging, phải định danh và kiểm thử artifact mới như artifact riêng.

## 15. Quan sát release và xác nhận môi trường đang chạy đúng artifact

Release thành công không chỉ là deployment controller báo rollout complete.

Cần xác minh:
- Pod/task/VM thực sự chạy đúng digest.
- Desired replicas bằng available replicas.
- Config revision đúng với môi trường và release record.
- Secret reference có thể đọc; không cần tiết lộ giá trị secret.
- Readiness, startup và smoke test pass.
- SLI/SLO không suy giảm.
- Error rate, latency, saturation và dependency health ổn định.
- Queue/schema/data consistency không phát sinh lỗi.
- Audit log gắn release ID, actor và approval.

Dashboard release có thể hiển thị:
- Source commit/build ID.
- Artifact digest và signature status.
- Environment/config revision.
- Deployment time và rollout status.
- Test/scan evidence.
- Feature flag state.
- Change/approval reference.
- Error budget hoặc SLO signals sau deploy.
- Rollback target và deployment history.

Không log giá trị secret hoặc dữ liệu cá nhân để chứng minh cấu hình đúng; chỉ lưu version/reference và trạng thái kiểm tra.

## 16. Tình huống thực tế: promote booking API từ development tới production

### 16.1. Bối cảnh

Một nền tảng đặt chỗ có:
- Booking API và Notification worker đóng gói dạng container.
- Git repository và CI pipeline.
- Private container registry.
- Development, staging và production trên cloud.
- Database migration riêng và secret manager theo môi trường.
- Release cần kiểm thử chức năng, contract, performance và security.

### 16.2. Quy trình đề xuất

| Bước | Hành động | Artifact/config/evidence |
| --- | --- | --- |
| 1. Commit | Merge commit đã review | Source revision |
| 2. Build | CI build API và worker một lần | Image digests |
| 3. Verify | Unit test, scan, SBOM, provenance, signing | Test report, attestation |
| 4. Dev | Deploy digest vào dev với config dev | Deployment record |
| 5. Staging | Promote cùng digest với config staging | Integration/acceptance test |
| 6. Approve | Review change, migration, capacity và risk | Approval record |
| 7. Canary | Deploy cùng digest cho cohort nhỏ | SLI/SLO, error rate, traces |
| 8. Expand | Tăng traffic theo gate | Rollout history |
| 9. Verify | Kiểm tra runtime digest/config/health | Release evidence |
| 10. Close | Gắn release với change và rollback reference | Audit trail |

### 16.3. Minh họa identity của artifact

| Thuộc tính | Development | Staging | Production |
| --- | --- | --- | --- |
| Image digest | sha256:abc... | sha256:abc... | sha256:abc... |
| Source revision | commit-417 | commit-417 | commit-417 |
| Build ID | build-417 | build-417 | build-417 |
| Config revision | dev-12 | stg-29 | prod-83 |
| Secret set | Dev vault references | Staging vault references | Production vault references |
| Release approval | Team policy | Test gate | Production change approval |

Digest và revision giống nhau; config/secret references khác nhau theo môi trường. Các giá trị là ví dụ giả định.

### 16.4. Kiểm tra nếu production khác staging

Nếu staging pass nhưng production lỗi, trước tiên so sánh:
- Artifact digest thực tế.
- Config revision và feature flags.
- Secret version/reference và quyền runtime.
- Network route, DNS, certificate và firewall.
- Database schema/version, data volume và query plan.
- Quota, replica, resource limits và autoscaling.
- External provider mode và rate limits.

Không kết luận artifact bị lỗi trước khi xác định khác biệt môi trường. Nhưng nếu digest không giống nhau, release đã vi phạm nguyên tắc promotion và cần điều tra pipeline.

## 17. Tình huống thứ hai: hotfix khẩn cấp

Một lỗ hổng trong thư viện HTTP ảnh hưởng booking API đang chạy production. Đội phát triển đã có patch và cần phát hành nhanh.

Quy trình:
1. Xác định source revision và dependency được cập nhật.
2. Tạo build mới; không sửa image đang lưu hoặc dùng lại digest cũ.
3. Chạy test bảo mật và regression tối thiểu theo risk, scan dependency và tạo SBOM/provenance mới.
4. Ký artifact mới, gắn security finding và incident/change reference.
5. Deploy vào staging hoặc môi trường xác minh tương đương.
6. Phê duyệt emergency release đúng authority.
7. Canary/rollout theo blast radius và theo dõi SLI.
8. Xác minh production thực chạy digest mới.
9. Quarantine/revoke artifact bị ảnh hưởng theo policy.
10. Sau incident, hoàn thiện test, review và evidence còn thiếu; không bỏ qua audit.

Khẩn cấp rút ngắn thời gian và thay đổi approval path theo policy; không làm mất danh tính artifact, traceability và trách nhiệm người phê duyệt.

## 18. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Build riêng cho từng environment | Binary khác nhau dù source giống | Build một lần, promote cùng digest |
| Deploy bằng tag mutable | Tag có thể trỏ sang nội dung mới | Deploy theo digest hoặc immutable version |
| Dùng latest trong production | Khó xác định artifact thực tế | Pin digest và ghi release metadata |
| Đưa endpoint/secret production vào build | Artifact gắn với environment và có thể lộ secret | Runtime config và secret manager |
| Test source nhưng deploy image khác | Test evidence không chứng minh artifact đang chạy | Gắn test report với digest |
| Build lại khi promote staging sang production | Mất tính đồng nhất và provenance | Promote registry artifact đã có |
| Không pin dependency/base image | Build không tái lập | Lockfile, digest và toolchain pinning |
| Scan source nhưng không scan artifact | Bỏ sót package/runtime layer | Scan image/package thực tế |
| SBOM không gắn digest | Không biết SBOM mô tả artifact nào | Artifact-bound SBOM/attestation |
| Sửa image sau khi ký | Signature/evidence không còn đúng | Rebuild, resign và retest artifact mới |
| Copy config staging sang production không review | Sai endpoint, quyền hoặc feature flag | Config schema, version và diff review |
| Migration không tương thích rolling release | App cũ/mới lỗi khi cùng chạy | Expand-and-contract và compatibility test |
| Rollback code nhưng schema không rollback được | Mất dữ liệu hoặc service lỗi | Forward-compatible schema và recovery plan |
| Không giữ artifact cũ | Không thể rollback đúng binary | Registry retention và DR copy |
| Không xác minh runtime digest | Controller báo deploy xong nhưng chạy sai image | Runtime inventory và digest verification |
| Approval chung chung | Không biết ai duyệt artifact/scope nào | Approval gắn digest, environment và change |
| Hotfix bỏ qua provenance | Khó điều tra và tin cậy supply chain | Emergency pipeline có gate tối thiểu và audit |

## 19. Bài tập thực hành

Một nhóm phát triển booking API có ba môi trường development, staging và production. Hiện CI build image ở mỗi môi trường; tag stable được dùng ở mọi nơi; staging đôi khi pass nhưng production khác hành vi. Secret được truyền vào một bước build frontend. Release cần có kiểm tra security và database migration.

Hãy thực hiện:

1. Vẽ pipeline hiện tại và chỉ ra mọi điểm có thể làm artifact/config khác nhau.
2. Đề xuất build once/promote same artifact, cách tạo digest và policy immutable registry.
3. Xây build recipe có dependency lock, base image pinning, provenance, SBOM và signing.
4. Thiết kế test gate gắn với artifact digest; xác định test chạy ở build, dev, staging và production canary.
5. Tách config và secret khỏi artifact; lập bảng khác biệt hợp lệ giữa ba môi trường.
6. Thiết kế promotion record và approval policy; nêu cách xử lý security exception.
7. Lập chiến lược database migration expand-and-contract và kiểm thử backward compatibility.
8. Đề xuất feature flag/progressive rollout, metric guardrail và điều kiện halt.
9. Viết rollback/roll-forward plan khi migration đã chạy nhưng phiên bản mới lỗi.
10. Thiết kế cách xác minh runtime digest, config revision và provenance sau production deployment.
11. Viết ADR có đánh đổi, owner, risk và điều kiện xem xét lại.

**Tiêu chí tự đánh giá:** giải pháp chứng minh staging và production chạy cùng artifact đã được test; cấu hình và secret khác nhau có chủ đích; artifact có nguồn gốc xác minh được; release có gate, approval, rollout và recovery; không build lại hoặc sửa artifact sau khi ký.

## 20. Checklist trước khi promote artifact lên production

- [ ] Source revision được review và branch protection đã đáp ứng.
- [ ] Build recipe/toolchain/dependency được khóa và ghi nhận.
- [ ] Artifact được tạo một lần cho release và lưu ở trusted registry.
- [ ] Artifact có version/digest bất biến; không deploy bằng mutable tag.
- [ ] Provenance/SBOM/signature gắn đúng digest và verifier đã kiểm tra.
- [ ] Test, scan và acceptance evidence gắn với đúng artifact.
- [ ] Không có secret hoặc production-specific config trong artifact.
- [ ] Config theo môi trường có schema, version, owner và validation.
- [ ] Secret references lấy từ secret manager với workload identity phù hợp.
- [ ] Manifest/IaC được review; khác biệt giữa staging và production có lý do.
- [ ] Migration có version, compatibility, backup và forward/rollback plan.
- [ ] Feature flags có owner, default state, audit và expiry.
- [ ] Release gate, change approval và separation of duties được đáp ứng.
- [ ] Rollout có canary/progressive strategy, stop condition và SLO guardrail.
- [ ] Registry retention đủ cho rollback/audit; artifact cũ có thể truy xuất.
- [ ] Production runtime digest được xác minh sau deploy.
- [ ] Config revision, release ID, actor, approver và evidence được lưu.
- [ ] Có kế hoạch quarantine/revoke artifact nếu phát hiện supply-chain issue.
- [ ] TCO gồm build, registry, scanning, evidence, replication và operations.
- [ ] Có owner và runbook cho release, rollback, hotfix và incident.

## Ghi nhớ

**Build một lần, promote cùng artifact** giúp các môi trường kiểm tra và chạy đúng một nội dung phần mềm có danh tính bất biến. Artifact phải gắn với source revision, build process, digest, provenance, SBOM, signature và test evidence. Cấu hình cùng secret được quản lý riêng theo môi trường, có version, quyền và audit.

Một quy trình release đáng tin cậy đi theo chuỗi **source được review → build có kiểm soát → artifact bất biến → verify/test → promote → approve → rollout → xác minh runtime → quan sát và phục hồi**. Khi source thay đổi, tạo artifact mới và kiểm thử lại; không sửa hoặc build lại artifact đã được phê duyệt rồi coi đó là cùng release.
