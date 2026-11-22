# Giữ sẵn artifact và cấu hình đã được xác minh

Rollback chỉ thực hiện được nhanh và an toàn khi nhóm còn giữ đúng phiên bản đã từng hoạt động tốt cùng cấu hình tương ứng. Nếu artifact cũ đã bị xóa khỏi registry, tag đã trỏ sang image mới, file cấu hình đã bị sửa tại production hoặc secret version cũ không còn dùng được, lệnh quay lui ứng dụng có thể thất bại hoặc đưa hệ thống về một trạng thái không tương thích.

Vì vậy, mỗi lần phát hành cần để lại một **release record** có thể tái sử dụng: artifact bất biến, digest, cấu hình đã được xác minh, tham chiếu secret theo phiên bản, metadata nguồn build và kết quả kiểm tra. Nhóm phải giữ các release gần nhất theo chính sách retention, bảo vệ chúng khỏi bị ghi đè/xóa ngoài ý muốn và định kỳ thử khôi phục trên môi trường đại diện.

Mục tiêu là khi xảy ra sự cố, người vận hành có thể xác định release tốt gần nhất, lấy lại đúng artifact và cấu hình, xác minh chúng rồi triển khai lại trong thời gian phục hồi đã đặt ra. Việc giữ sẵn không có nghĩa là lưu bí mật trong bundle; secret vẫn được lấy từ secret manager theo danh tính và phiên bản được phép.

## 1. Rollback cần nhiều hơn một file binary

Một release đang chạy là kết quả của nhiều đầu vào phối hợp:

- Artifact: JAR, ZIP, binary, package hoặc container image.
- Cấu hình ứng dụng: endpoint, timeout, feature setting, resource limit và tham số runtime.
- Cấu hình hạ tầng: Deployment, Service, ingress, autoscaling, policy và IaC state tương ứng.
- Feature flags: trạng thái bật/tắt tính năng tại thời điểm phát hành.
- Secret references: tên secret, phiên bản hoặc version ID cần lấy từ secret manager.
- Database schema và migration level: cấu trúc dữ liệu mà artifact yêu cầu.
- Runtime/toolchain: JDK, base image, sidecar hoặc agent có ảnh hưởng tới hành vi.
- Bằng chứng: digest, chữ ký, provenance, test report, approval và deployment record.

Nếu chỉ lưu artifact mà không lưu cấu hình, rollback có thể chạy code cũ với cấu hình mới. Nếu chỉ lưu cấu hình mà không giữ secret version hoặc schema compatibility, ứng dụng cũ vẫn có thể không khởi động. Do đó, cần quản lý một release như một tập hợp có định danh, không phải một tên version đơn lẻ.

### Ví dụ một release record

Giả sử production đang chạy `orders-api` release `2026.11.18.3`. Release record cần xác định được chính xác image, config revision và schema level:

```json
{
  "service": "orders-api",
  "releaseId": "2026.11.18.3",
  "source": {
    "repository": "https://git.example.com/platform/orders-api",
    "commit": "<full-commit-sha>"
  },
  "artifact": {
    "uri": "registry.example.com/platform/orders-api",
    "digest": "sha256:<64-hex-characters>"
  },
  "configuration": {
    "repository": "https://git.example.com/platform/orders-config",
    "revision": "<config-commit-sha>",
    "renderedBundleDigest": "sha256:<64-hex-characters>"
  },
  "secretReferences": [
    {"name": "orders-db-credentials", "version": "42"},
    {"name": "payment-client-certificate", "version": "17"}
  ],
  "database": {
    "minimumSchemaVersion": "2026_11_12_01",
    "maximumSchemaVersion": "2026_11_18_02"
  },
  "verification": {
    "signature": "verified",
    "provenance": "verified",
    "smokeTest": "passed"
  }
}
```

Các giá trị trong ví dụ là placeholder. Manifest thực tế phải được tạo từ metadata của build và deployment, không ghi tay digest hoặc trạng thái kiểm tra. Không đưa password, token, private key hay nội dung secret vào manifest; chỉ lưu tham chiếu và version ID nếu chính sách cho phép.

## 2. Xác định release nào cần giữ

Không phải mọi lần build đều cần được giữ vô thời hạn. Hãy xác định chính sách dựa trên thời gian cần rollback, tần suất phát hành, mức độ quan trọng của dịch vụ, yêu cầu kiểm toán và khả năng phục hồi từ backup.

Một chính sách có thể phân loại:

| Nhóm | Ví dụ | Cách lưu |
|---|---|---|
| Release đang chạy | Phiên bản production hiện tại | Giữ artifact, config và manifest; bảo vệ khỏi xóa tự động |
| Known-good release | Một hoặc nhiều phiên bản trước đã được xác nhận ổn định | Giữ trong registry/storage có thể truy xuất nhanh |
| Candidate đã duyệt | Release đã qua gate nhưng chưa rollout toàn bộ | Giữ trong thời gian triển khai và rollback window |
| Build thử nghiệm | Build PR, nightly hoặc branch không phát hành | Retention ngắn, quyền truy cập hạn chế |
| Release đã thu hồi | Artifact có lỗi bảo mật hoặc không còn được phép dùng | Cách ly/đánh dấu revoked; không đưa vào danh sách rollback hợp lệ |

### Giữ theo rollback window và RTO

Retention phải dài hơn khoảng thời gian mà tổ chức cam kết có thể rollback. Nếu nhóm cần có khả năng quay lại một trong ba release gần nhất, artifact và cấu hình của ba release đó phải còn sẵn trong thời gian tương ứng. Với hệ thống có job theo tháng hoặc phụ thuộc phê duyệt kéo dài, cửa sổ rollback có thể lớn hơn chu kỳ deploy thông thường.

Hãy xem xét:

- RTO: thời gian tối đa cho phép để khôi phục dịch vụ.
- RPO: mức mất dữ liệu có thể chấp nhận; artifact retention không thay thế backup dữ liệu.
- Thời gian phát hiện lỗi sau deploy: lỗi có thể chỉ xuất hiện sau vài ngày hoặc một chu kỳ nghiệp vụ.
- Thời gian cần điều tra và phê duyệt: có thể cần giữ release trong lúc xác định nguyên nhân.
- Thời hạn hỗ trợ của runtime, dependency và base image.
- Yêu cầu pháp lý, kiểm toán và chính sách lưu trữ nội bộ.

Giữ quá ít release làm rollback phụ thuộc vào việc build lại trong sự cố. Giữ mọi artifact mãi mãi làm tăng chi phí và mở rộng bề mặt lưu trữ. Chính sách nên nêu rõ số lượng hoặc thời gian tối thiểu, ngoại lệ cho release quan trọng và quy trình xóa có kiểm soát.

### Giữ đủ các thành phần phụ thuộc

Giữ file JAR nhưng xóa dependency repository, base image, Helm chart, deployment manifest hoặc IaC module cần thiết vẫn có thể làm rollback không tái tạo được môi trường. Release record cần liệt kê các thành phần mà quy trình khôi phục phụ thuộc.

Với container image, giữ cả manifest/index và các layer theo digest. Với ứng dụng Java, bảo đảm package và dependency cần thiết vẫn có thể tải lại hoặc được đóng gói trong distribution. Với triển khai Kubernetes, giữ chart/manifests đã render hoặc source revision cùng phiên bản công cụ cần thiết để tái áp dụng cấu hình.

## 3. Artifact phải bất biến và có định danh rõ

Artifact đã được duyệt không nên bị ghi đè bằng nội dung khác. Cùng một tên hoặc version phải luôn đại diện cho cùng một nội dung trong suốt vòng đời release.

### Dùng digest thay vì tag di động

Tag như `latest`, `stable`, `production` hoặc `1.8` có thể được cập nhật để trỏ sang nội dung khác. Với container image, hãy ghi lại digest:

```text
registry.example.com/platform/orders-api@sha256:<image-digest>
```

Tag vẫn hữu ích cho con người, nhưng quyết định triển khai và rollback nên dùng digest bất biến. Nếu một tag bị di chuyển, release record cũ vẫn trỏ tới đúng image.

Với package hoặc file archive, dùng version bất biến và lưu SHA-256. Không publish lại nội dung khác dưới cùng tọa độ Maven/package version. Nếu cần phát hành sửa lỗi, tạo version mới.

### Xác minh trước khi lưu và trước khi dùng

Sau build, pipeline nên:

1. Tính digest của artifact.
2. Tạo chữ ký hoặc attestation theo policy.
3. Lưu provenance gắn với source commit và builder identity.
4. Upload artifact vào registry/storage có quyền ghi hạn chế.
5. Đọc lại artifact hoặc inspect registry digest để xác nhận nội dung đã lưu đúng.
6. Ghi digest và URI vào release manifest.

Trước rollback, pipeline lấy đúng digest từ release record, xác minh chữ ký/provenance và kiểm tra trạng thái thu hồi. Không chỉ kiểm tra tag có tồn tại rồi triển khai.

Ví dụ kiểm tra image bằng Cosign với public key đã được phân phối qua trust store đáng tin cậy:

```bash
cosign verify --key release.pub \
  registry.example.com/platform/orders-api@sha256:<image-digest>
```

Đối với blob hoặc package file, xác minh digest và detached signature tương ứng. Chữ ký hợp lệ không tự chứng minh release vẫn được phép sử dụng; policy cần kiểm tra thêm trạng thái thu hồi, source revision và builder identity.

### Bảo vệ registry và storage

Artifact store là một phần của hạ tầng phục hồi. Hãy:

- Tách quyền publish, pull, delete và quản trị retention.
- Chỉ pipeline phát hành được phép ghi vào namespace release.
- Bật versioning hoặc immutable retention/lock nếu nền tảng hỗ trợ.
- Hạn chế xóa artifact đang được tham chiếu bởi release đang chạy hoặc known-good.
- Ghi audit log cho thao tác publish, overwrite, delete và thay đổi retention.
- Sao lưu hoặc replicate artifact quan trọng theo yêu cầu khả dụng.
- Kiểm tra khả năng truy cập khi registry chính gặp sự cố.

Nếu registry hỗ trợ retention lock/WORM, cấu hình cho release quan trọng để ngăn xóa trước hạn. Cần phân biệt tính bất biến của artifact với quyền xóa quản trị; policy và credential quản trị vẫn phải được bảo vệ.

## 4. Giữ cấu hình dưới dạng phiên bản có thể phục hồi

Cấu hình thường thay đổi độc lập với code: endpoint, timeout, resource limit, autoscaling, route, policy, feature flags và tham số nghiệp vụ. Nếu chỉnh trực tiếp trên production mà không ghi lại revision, nhóm có thể không biết cấu hình nào đã tạo ra hành vi đang gặp lỗi.

### Version hóa cấu hình

Các cách phổ biến:

- Lưu cấu hình trong Git và dùng commit SHA làm revision.
- Đóng gói config thành bundle có digest và chữ ký.
- Dùng GitOps controller để reconcile môi trường từ revision được khai báo.
- Lưu bản snapshot cấu hình đã render cùng release record.
- Ghi lại phiên bản chart, manifest, policy và IaC module.

Không dùng branch hoặc tag mutable làm định danh duy nhất. Manifest nên ghi commit SHA hoặc digest của bundle. Nếu có template và giá trị theo môi trường, cần ghi cả phiên bản template lẫn revision của values dùng để render.

Ví dụ cấu trúc repository cấu hình:

```text
orders-config/
├── base/
│   ├── deployment.yaml
│   └── service.yaml
├── overlays/
│   ├── staging/
│   │   └── values.yaml
│   └── production/
│       └── values.yaml
└── policy/
    └── resource-limits.yaml
```

Release record có thể ghi revision của repository này và digest của output đã render cho production. Khi rollback, lấy đúng revision và render bằng phiên bản tool đã được ghi nhận hoặc dùng bundle đã render, đã xác minh.

### Lưu cấu hình hiệu lực, không chỉ cấu hình nguồn

Template có thể tạo ra output khác nhau tùy biến môi trường, phiên bản chart, biến CI hoặc secret reference. Để điều tra và rollback, cần biết cấu hình hiệu lực sau render.

Có thể lưu:

- Commit SHA của config repository.
- Phiên bản Helm/Kustomize/Terraform hoặc renderer.
- Digest của bundle/manifests đã render.
- Environment và release ID.
- Feature flag snapshot hoặc revision của hệ thống feature flag.
- Tham chiếu secret và version ID, không phải secret value.
- Các biến runtime được phép ảnh hưởng tới cấu hình.

Snapshot cần được làm sạch trước khi lưu. Một số renderer có thể nội suy secret trực tiếp vào manifest; không upload bản render chứa secret vào artifact công khai hoặc log. Tốt hơn là dùng secret reference được platform resolve lúc runtime.

### Phát hiện cấu hình drift

Drift xảy ra khi cấu hình đang chạy khác với cấu hình được khai báo. Ví dụ người vận hành sửa replica count trực tiếp, thay timeout trên console hoặc cập nhật environment variable ngoài Git.

Hãy định kỳ so sánh desired configuration với effective configuration, ghi nhận thay đổi ngoài quy trình và quyết định reconcile hoặc chấp nhận thay đổi có kiểm soát. Trước rollback, cần biết có thay đổi khẩn cấp nào phải giữ lại để không vô tình xóa một bản sửa cần thiết.

Không phải mọi thay đổi runtime đều nên bị tự động ghi đè. Một số tham số vận hành như scale tạm thời có thể được quản lý riêng. Policy cần phân loại cấu hình nguồn, cấu hình vận hành và thay đổi khẩn cấp.

## 5. Quản lý secret theo tham chiếu và phiên bản

Release bundle không nên chứa password, API token, private key hoặc certificate private. Các giá trị này có thể bị sao chép khi artifact được tải, lưu, replicate hoặc chia sẻ.

Thay vào đó, lưu tham chiếu tới secret manager:

```yaml
database:
  usernameSecret:
    name: orders-db-username
    version: "42"
  passwordSecret:
    name: orders-db-password
    version: "42"
```

Đây là cấu trúc minh họa. Cú pháp thật phụ thuộc secret manager và runtime platform. Nếu hệ thống không hỗ trợ pin version, cần lưu policy rotation và bảo đảm phiên bản mới có thể đọc credential hiện tại.

### Secret version và khả năng rollback

Rollback về artifact cũ nhưng dùng secret mới có thể hoạt động hoặc thất bại tùy khả năng tương thích. Ví dụ, certificate mới có thể không được runtime cũ hỗ trợ; password database đã rotate có thể không còn hợp lệ với connection config cũ.

Hãy xác định:

- Secret nào cần version pin để tái lập release.
- Secret nào phải luôn lấy phiên bản hiện hành vì lý do bảo mật.
- Secret rotation có giai đoạn overlap hay không.
- Runtime cũ có thể sử dụng credential mới không.
- Có thể khôi phục secret version cũ an toàn hay phải tạo credential mới.
- Ai có quyền đọc secret khi rollback và trong môi trường nào.

Không khôi phục một credential đã bị thu hồi hoặc nghi ngờ bị lộ chỉ để làm release cũ chạy lại. Khi secret cũ không còn an toàn, hãy cập nhật cấu hình của release rollback để dùng credential mới tương thích.

### Không đóng gói secret đã render

Nếu config renderer đưa giá trị secret vào file YAML, JSON hoặc environment file, không lưu file đó trong release archive. Có thể lưu cấu hình đã render sau khi thay secret bằng reference hoặc redaction, sau đó để runtime lấy secret theo workload identity.

Nếu bắt buộc phải lưu cấu hình nhạy cảm để phục hồi, cần dùng kho mã hóa riêng với quyền truy cập rất hẹp, audit đầy đủ, encryption key tách biệt và quy trình truy cập break-glass. Đây là ngoại lệ có kiểm soát, không phải lý do để đưa secret vào artifact thông thường.

## 6. Release manifest liên kết artifact và cấu hình

Một manifest thống nhất giúp pipeline và người vận hành biết những thành phần nào thuộc cùng một release. Manifest nên bất biến sau khi được ký và lưu ở vị trí có thể truy xuất ngay cả khi CI system gặp sự cố.

Ví dụ manifest YAML:

```yaml
apiVersion: delivery.example.com/v1
kind: ReleaseRecord
metadata:
  service: orders-api
  releaseId: "2026.11.18.3"
source:
  repository: platform/orders-api
  commit: "<full-commit-sha>"
artifact:
  type: oci-image
  reference: registry.example.com/platform/orders-api@sha256:<image-digest>
  signature: registry.example.com/platform/orders-api-signature
configuration:
  repository: platform/orders-config
  revision: "<config-commit-sha>"
  environment: production
  renderedBundleDigest: "sha256:<config-bundle-digest>"
secrets:
  references:
    - name: orders-db-credentials
      version: "42"
database:
  schemaVersion: "2026_11_18_02"
  compatibility: "supports-previous-and-current"
verification:
  provenance: verified
  signature: verified
  smokeTest: passed
```

Các giá trị `verified` trong manifest là kết quả được pipeline ghi lại sau khi kiểm tra thật. Manifest không được dùng làm nguồn tự chứng thực cho chính nó; hãy ký manifest hoặc lưu trong release store có kiểm soát và xác minh chữ ký trước khi sử dụng.

Manifest nên ghi rõ environment vì cùng một artifact có thể được triển khai với cấu hình staging và production khác nhau. Không gộp secret value vào manifest. Có thể có một manifest gốc của artifact và một deployment record riêng cho mỗi environment, liên kết bằng release ID và digest.

### Tách release manifest và deployment record

Release manifest mô tả thứ được build và kiểm tra. Deployment record mô tả lần áp dụng vào môi trường:

| Record | Thông tin chính |
|---|---|
| Release manifest | Source commit, artifact digest, signature, provenance, dependency và test evidence |
| Environment config record | Config revision, rendered bundle digest, secret references/version, feature flag revision |
| Deployment record | Environment, release ID, thời điểm, actor, approval, rollout strategy và kết quả |
| Recovery record | Release được chọn để rollback, lý do, digest/config revision và kết quả xác minh sau rollback |

Tách record giúp cùng một artifact được promote qua nhiều môi trường mà vẫn truy vết được cấu hình hiệu lực ở từng nơi.

## 7. Lưu danh sách known-good releases

Một registry có thể chứa nhiều artifact nhưng không tự biết release nào là known-good. Cần có metadata hoặc deployment ledger ghi nhận trạng thái.

Ví dụ danh sách:

| Release | Artifact digest | Config revision | Production state | Có thể rollback? |
|---|---|---|---|---|
| `2026.11.18.3` | `sha256:aaa...` | `cfg-91ab...` | Current | Không cần rollback về chính nó |
| `2026.11.16.2` | `sha256:bbb...` | `cfg-73cd...` | Previous known-good | Có, nếu schema/secret tương thích |
| `2026.11.12.5` | `sha256:ccc...` | `cfg-5e21...` | Older known-good | Có điều kiện, cần kiểm tra compatibility |
| `2026.11.18.4-rc1` | `sha256:ddd...` | `cfg-b104...` | Candidate | Chưa được coi là known-good |

Không chọn release rollback chỉ dựa trên số version lớn/nhỏ hoặc thời điểm gần nhất. Candidate có thể chưa được xác minh ở production; release cũ hơn có thể không tương thích schema hiện tại.

### Đánh dấu release bị thu hồi

Nếu phát hiện artifact có lỗ hổng nghiêm trọng, chữ ký sai hoặc dependency bị xâm phạm, đánh dấu release đó là revoked/quarantined. Release record vẫn nên được giữ cho kiểm toán, nhưng pipeline rollback phải từ chối sử dụng.

Trạng thái known-good cần được cập nhật sau khi post-deployment validation đạt, không phải ngay khi upload artifact. Một release chỉ được thêm vào danh sách rollback khi có bằng chứng đã phục vụ ổn định theo tiêu chí của tổ chức.

## 8. Quy trình rollback dùng artifact và cấu hình đã giữ

Khi cần rollback, quy trình nên tự động lấy đúng cặp artifact/config đã biết và kiểm tra tương thích trước khi thay đổi production.

### Các bước vận hành

1. **Chặn rollout hiện tại:** dừng bước tăng traffic hoặc deployment đang lỗi để tránh tiếp tục thay đổi.
2. **Chọn release:** xác định known-good release phù hợp với schema, dependency và trạng thái bảo mật hiện tại.
3. **Lấy release record:** lấy manifest đã ký hoặc record từ release ledger có kiểm soát.
4. **Tải artifact:** dùng immutable digest, không resolve tag mutable.
5. **Xác minh:** kiểm tra digest, signature, provenance, trạng thái thu hồi và nguồn builder.
6. **Lấy cấu hình:** checkout đúng config revision hoặc tải bundle có digest đã ghi.
7. **Kiểm tra secret:** resolve secret reference theo policy hiện tại; không phục hồi credential đã thu hồi.
8. **Kiểm tra tương thích:** schema, API, feature flags, runtime và dependency phải hỗ trợ release được chọn.
9. **Triển khai:** dùng chiến lược canary/rolling/blue-green phù hợp và giữ bản hiện tại để quay lại nếu cần.
10. **Xác minh sau rollback:** smoke test, health, metrics, log và chỉ số nghiệp vụ.
11. **Ghi recovery record:** lưu actor, lý do, release/digest/config, approval và kết quả.

Nếu artifact hoặc cấu hình không thể xác minh, dừng rollback và chuyển sang phương án phục hồi đã được phê duyệt. Không tự bỏ qua chữ ký hoặc dùng bản build mới tạo trong lúc sự cố nếu mục tiêu là quay về một release đã biết.

### Ví dụ kiểm tra release trước khi deploy

Script khái niệm dưới đây minh họa các điều kiện bắt buộc. Các lệnh `release-tool` và `deploy-tool` là tên giả định của công cụ nội bộ, cần thay bằng CLI/API thực tế:

```bash
#!/usr/bin/env bash
set -euo pipefail

release_id="${1:?usage: rollback.sh <release-id> <environment>}"
environment="${2:?usage: rollback.sh <release-id> <environment>}"

# Fetch a signed release record from the trusted release ledger.
release-tool fetch-record "$release_id" --output release-record.json
release-tool verify-record release-record.json

# Resolve immutable artifact and config bundle references.
artifact_digest="$(release-tool field release-record.json artifact.digest)"
config_digest="$(release-tool field release-record.json configuration.renderedBundleDigest)"

# Verify the exact content before use.
release-tool verify-artifact "$artifact_digest"
release-tool verify-config "$config_digest"
release-tool assert-not-revoked "$release_id"
release-tool check-compatibility "$release_id" "$environment"

# Resolve secret references at runtime; never export secret values to the bundle.
release-tool resolve-secret-references "$release_id" "$environment"

# Deploy the exact approved release pair.
deploy-tool apply \
  --release-record release-record.json \
  --artifact-digest "$artifact_digest" \
  --config-digest "$config_digest" \
  --environment "$environment"

deploy-tool verify "$release_id" "$environment"
release-tool record-recovery "$release_id" "$environment" --result success
```

Đây là pseudo-code, không phải script có thể chạy nguyên trạng. Công cụ thực tế cần kiểm tra chữ ký và provenance, xác thực input, bảo vệ output của lệnh, không in secret và chỉ cho phép environment được phê duyệt. Các trường lấy từ manifest phải được parse an toàn; không `eval` nội dung JSON/YAML hoặc ghép trực tiếp dữ liệu không tin cậy vào shell command.

### Không bỏ qua phê duyệt khi rollback

Rollback thường cần nhanh, nhưng vẫn phải có authorization. Có thể định nghĩa quyền break-glass cho on-call hoặc incident commander, giới hạn environment và ghi audit. Approval không nhất thiết làm quy trình chậm nếu policy đã xác định trước người có quyền và release nào đủ điều kiện.

## 9. Ví dụ GitHub Actions giữ artifact và release metadata

Workflow sau minh họa cách lưu gói distribution cùng checksum và manifest trong một lần build. Với hệ thống production, artifact store hoặc package registry nên có retention/immutability policy riêng; GitHub Actions artifact chỉ là một ví dụ lưu trữ ngắn hạn.

```yaml
name: Build release bundle

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Build and test
        run: ./gradlew --no-daemon clean check distZip

      - name: Prepare release bundle
        env:
          SOURCE_COMMIT: ${{ github.sha }}
          RELEASE_TAG: ${{ github.ref_name }}
        run: |
          mkdir -p release-bundle
          cp build/distributions/*.zip release-bundle/
          cd release-bundle
          sha256sum *.zip > SHA256SUMS
          printf 'release=%s\nsource_commit=%s\n' "$RELEASE_TAG" "$SOURCE_COMMIT" > release-metadata.txt

      - name: Upload release bundle
        uses: actions/upload-artifact@v4
        with:
          name: release-${{ github.ref_name }}-${{ github.sha }}
          path: release-bundle/
          if-no-files-found: error
          retention-days: 90
```

Workflow này minh họa build/test, tạo checksum và lưu metadata. Trước khi dùng cho phát hành thật, cần bổ sung:

- Pin các GitHub Action theo full commit SHA theo policy chuỗi cung ứng.
- Xác minh tag được bảo vệ và release chỉ được tạo từ nguồn/branch được phép.
- Ký artifact, checksum manifest và release metadata; tạo provenance attestation.
- Lưu config revision và rendered config digest trong deployment record riêng.
- Publish vào registry có version bất biến và retention phù hợp với rollback window.
- Cấu hình secret và signing identity ở job riêng có quyền tối thiểu.
- Không xem retention 90 ngày trong ví dụ là mặc định phù hợp cho mọi hệ thống.

Một release bundle có thể chứa binary, checksum, SBOM, provenance reference và manifest đã ký. Cấu hình environment nên được quản lý trong repository hoặc config store riêng, sau đó được liên kết bằng revision/digest. Không đưa secret production vào artifact.

## 10. Bảo đảm cấu hình có thể phục hồi độc lập

Nếu cấu hình nằm trong GitOps, rollback config có thể là revert hoặc redeploy revision trước. Tuy nhiên, thao tác này phải có kiểm soát để tránh vô tình xóa thay đổi khẩn cấp hoặc áp dụng cấu hình cũ không tương thích.

### Lưu revision và diff

Deployment record nên lưu:

- Config repository và commit SHA.
- Environment overlay hoặc values file đã sử dụng.
- Phiên bản renderer và tham số render.
- Digest của output đã render.
- Diff giữa release hiện tại và release trước.
- Người hoặc automation đã phê duyệt.

Trước rollback, xem diff để biết thay đổi nào sẽ bị đảo ngược. Một số cấu hình có thể đã được cập nhật độc lập để sửa sự cố bảo mật, ví dụ TLS minimum version hoặc endpoint đã chuyển. Không nên khôi phục toàn bộ config cũ mà không đánh giá những thay đổi này.

### Feature flags

Feature flag có thể quyết định code path được bật. Nếu artifact cũ được khôi phục nhưng flag vẫn ở trạng thái mới, ứng dụng có thể tiếp tục đi vào code path gây lỗi. Lưu revision hoặc snapshot của flag state theo release và định nghĩa flag nào được phép rollback cùng code.

Không phải mọi flag nên bị khôi phục tự động. Flag vận hành hoặc kill switch có thể được bật trong incident để bảo vệ hệ thống và cần giữ trạng thái mới ngay cả khi code rollback. Phân loại flag theo ownership và hành vi khi rollback.

### Cấu hình runtime và dynamic configuration

Một số hệ thống lấy cấu hình từ remote config service hoặc database. Chỉ lưu commit Git là chưa đủ nếu giá trị hiệu lực đã thay đổi sau deploy. Cần ghi revision hoặc version của config object, thời điểm snapshot và cách phục hồi. Nếu hệ thống không hỗ trợ versioning, hãy bổ sung audit log và export snapshot đã làm sạch.

Không tự động ghi đè cấu hình runtime có thể chứa trạng thái nghiệp vụ. Chỉ rollback các tham số thuộc phạm vi cấu hình phát hành đã xác định.

## 11. Kiểm tra tương thích trước khi chọn release cũ

Release gần nhất không phải lúc nào cũng là release có thể quay lại. Trước khi chọn, cần kiểm tra các ràng buộc:

| Thành phần | Câu hỏi tương thích |
|---|---|
| Database schema | Artifact cũ có đọc được schema hiện tại không? Migration đã contract hoặc xóa cột cũ chưa? |
| Dữ liệu | Dữ liệu mới có được ghi theo format mà code cũ hiểu không? |
| API | Client và service phụ thuộc có còn tương thích với contract cũ không? |
| Message schema | Consumer cũ có hiểu message mới đã được publish vào queue không? |
| Config | Cấu hình hiện tại có chứa key mới hoặc bỏ key cũ mà artifact cũ cần không? |
| Secret | Credential version hiện tại có tương thích với runtime cũ và còn hợp lệ không? |
| Runtime | Base image, JDK, OS library hoặc sidecar cần thiết còn được giữ không? |
| Security | Artifact có bị thu hồi hoặc chứa dependency đã bị cấm không? |
| External services | API/endpoint bên ngoài có còn hỗ trợ protocol mà release cũ dùng không? |

Nếu schema đã tiến tới contract và không còn tương thích với artifact cũ, không nên cố rollback code đơn thuần. Có thể cần forward fix, migration bổ sung hoặc phục hồi database theo quy trình riêng. Release ledger nên ghi minimum/maximum schema compatibility để công cụ rollback có thể loại candidate không phù hợp trước khi deploy.

### Giữ lại cấu hình cũ không đồng nghĩa giữ lại mọi dữ liệu cũ

Artifact/config retention không thay thế backup database, object storage hoặc message log. Nếu release cũ cần dữ liệu đã bị xóa hoặc chuyển đổi, phải có backup/PITR hoặc khả năng replay/compensate phù hợp. Các bài toán phục hồi dữ liệu cần được quản lý như một phần riêng của recovery plan.

## 12. Quyền truy cập và bảo vệ release đã lưu

Release đã xác minh có thể trở thành mục tiêu hấp dẫn vì ai thay được artifact hoặc manifest có thể ảnh hưởng trực tiếp tới rollback. Hãy áp dụng quyền tối thiểu cho cả write và delete.

Các vai trò nên được tách:

- Builder: tạo artifact và metadata, chỉ ghi vào namespace build được phép.
- Signer: ký artifact/manifest theo policy; không nhận mã không tin cậy.
- Release manager: phê duyệt và đánh dấu release đủ điều kiện.
- Deployer: đọc release đã duyệt và triển khai vào environment được cấp quyền.
- Storage administrator: quản lý retention, replication và phục hồi; thao tác được audit.
- Incident responder: có quyền break-glass theo thời hạn và ghi nhận lý do.

Không cấp quyền xóa registry cho job deploy thông thường. Không để pull request từ fork có quyền ghi vào namespace release hoặc sửa retention policy. Manifest và config revision phải được bảo vệ tương tự artifact vì thay đổi chúng có thể làm sai mục tiêu rollback.

## 13. Diễn tập khả năng lấy lại release

Một release chỉ thật sự sẵn sàng cho rollback khi nhóm đã chứng minh có thể lấy và sử dụng nó. Việc thấy artifact còn trong registry không đủ; quyền truy cập có thể hết hạn, signature key có thể thay đổi, dependency có thể biến mất hoặc config renderer có thể không còn cài đặt.

### Bài diễn tập định kỳ

Chọn một known-good release cũ và thực hiện trên staging hoặc môi trường phục hồi:

1. Tra cứu release record bằng release ID.
2. Tải artifact theo digest và xác minh signature/provenance.
3. Lấy config revision/bundle và xác minh digest.
4. Resolve secret reference bằng identity của môi trường thử nghiệm.
5. Kiểm tra schema compatibility và dependency availability.
6. Triển khai release cũ vào môi trường thử nghiệm.
7. Chạy smoke test và kiểm tra metrics.
8. Ghi thời gian từng bước, lỗi và kết quả vào recovery drill record.

Không dùng secret production trong diễn tập nếu không cần. Dùng credential thử nghiệm có scope tương đương và có thể thu hồi.

### Đo thời gian phục hồi thực tế

Đo thời gian từ lúc incident commander chọn release tới khi dịch vụ vượt qua post-deployment validation. So sánh với RTO. Nếu thời gian chủ yếu nằm ở bước tải image, tìm config hoặc chờ approval, hãy cải thiện release ledger, mirror, quyền truy cập hoặc quy trình break-glass.

Diễn tập cũng cần kiểm tra trường hợp xấu:

- Registry chính không truy cập được.
- Artifact có digest nhưng signature không còn xác minh được do trust policy đổi.
- Config revision bị xóa hoặc không còn quyền đọc.
- Secret version cũ đã bị thu hồi.
- Release cũ không tương thích schema hiện tại.
- Artifact bị đánh dấu revoked.

Kết quả diễn tập phải nêu rõ fallback nào có thể dùng và trường hợp nào buộc phải forward fix hoặc phục hồi dữ liệu.

## 14. Những cách làm dễ làm mất khả năng rollback

| Cách làm | Rủi ro | Cách cải thiện |
|---|---|---|
| Chỉ giữ tag `latest` | Tag có thể trỏ tới nội dung mới | Lưu digest bất biến trong release record |
| Rebuild phiên bản cũ khi incident xảy ra | Toolchain/dependency đã thay đổi nên artifact khác | Giữ artifact đã phát hành và xác minh |
| Lưu binary nhưng không lưu config revision | Code cũ chạy với cấu hình không tương thích | Liên kết artifact và config bằng release manifest |
| Lưu config đã render có secret | Credential bị sao chép vào artifact/store | Lưu config đã làm sạch và secret reference/version |
| Xóa release cũ theo retention ngắn | Không còn known-good khi lỗi được phát hiện muộn | Retention dựa trên rollback window và RTO |
| Dùng cùng registry quyền ghi rộng | Artifact tốt có thể bị thay thế hoặc xóa | Tách write/delete, immutable policy và audit |
| Chỉ giữ release record trong CI log | Log có thể hết hạn hoặc hệ thống CI gặp sự cố | Lưu release ledger độc lập, có backup |
| Không giữ dependency/base image | Không thể tái tạo runtime cũ | Giữ các dependency cần thiết hoặc mirror có kiểm soát |
| Rollback code nhưng không kiểm tra schema | Code cũ lỗi trên schema mới | Ghi schema compatibility và kiểm tra trước deploy |
| Khôi phục secret cũ đã bị thu hồi | Tái mở rủi ro bảo mật | Dùng credential mới tương thích với artifact cũ |
| Không diễn tập restore | Chỉ phát hiện thiếu quyền hoặc thiếu file khi incident | Thực hiện rollback drill định kỳ |

## 15. Checklist giữ sẵn release có thể rollback

Trước khi đánh dấu một release là known-good, hãy kiểm tra:

- [ ] Artifact được lưu trong registry/storage có quyền ghi và xóa được kiểm soát.
- [ ] Artifact có immutable digest; không phụ thuộc tag di động.
- [ ] Digest, signature và provenance đã được xác minh.
- [ ] Release manifest liên kết source commit, artifact digest và builder identity.
- [ ] Config repository revision và digest của bundle đã render được ghi lại.
- [ ] Feature flag revision/snapshot được lưu theo policy.
- [ ] Secret chỉ được lưu dưới dạng reference/version; không có secret value trong bundle.
- [ ] Schema compatibility và migration level của release được ghi rõ.
- [ ] Dependency, base image, chart hoặc IaC module cần cho rollback còn truy cập được.
- [ ] Release retention dài hơn rollback window và phù hợp RTO/chính sách lưu trữ.
- [ ] Release bị thu hồi được đánh dấu và không thể được chọn làm rollback candidate.
- [ ] Có deployment record và danh sách known-good releases.
- [ ] Quyền deploy, publish, sign và delete được tách biệt.
- [ ] Có audit log cho thay đổi artifact, manifest, config và retention.
- [ ] Có bản sao/replica hoặc phương án truy cập khi registry chính gặp sự cố.
- [ ] Quy trình rollback xác minh lại artifact/config trước khi triển khai.
- [ ] Đã diễn tập lấy lại release, khôi phục config và đo thời gian thực tế.

Giữ sẵn artifact và cấu hình đã xác minh biến rollback từ một thao tác ứng biến thành quy trình có thể dự đoán. Artifact bất biến cho biết chính xác code nào được chạy; config revision cho biết môi trường đã được cấu hình ra sao; secret reference và schema compatibility giúp xác nhận release cũ còn dùng được. Khi release record, retention, quyền truy cập và diễn tập phục hồi được quản lý cùng nhau, nhóm có thể quay lại một trạng thái đã biết mà không phải build lại hoặc đoán cấu hình trong lúc sự cố.
