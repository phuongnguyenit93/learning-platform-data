# Lập phương án quay lại phiên bản trước với sản phẩm đã lưu và định danh rõ ràng

Một kế hoạch rollback đáng tin cậy phải trả lời ba câu hỏi: **bản nào đang chạy, bản tốt gần nhất nằm ở đâu, và làm thế nào triển khai lại đúng những bytes đã được kiểm tra trước đó**. Chỉ nhớ version như `2.4.0` hoặc chạy lại source code của release cũ chưa đủ. Dependencies, build tool, builder image, cấu hình và dữ liệu có thể đã thay đổi kể từ lần build đầu tiên.

Với ứng dụng Spring Boot, rollback nên dựa trên **artifact đã lưu bất biến**, có định danh kiểm chứng được và đủ metadata để tái triển khai. Với JAR, định danh thường là Maven coordinates kết hợp SHA-256. Với container image, định danh đáng tin cậy là repository cộng OCI digest. Release manifest liên kết artifact với Git commit, build run, SBOM, cấu hình và mức schema database tương ứng.

Bài này trình bày cách lưu giữ sản phẩm đã build, xác định đúng phiên bản, rollback bằng Maven/Gradle artifact repository, Docker/OCI registry, Kubernetes và Helm; đồng thời xử lý tương thích database, configuration, feature flags và dữ liệu đang chạy.

## 1. Rollback là khôi phục một release đã được xác minh

Một release Spring Boot thường gồm nhiều thành phần:

- Executable JAR hoặc OCI image.
- Dependency graph và runtime/toolchain versions.
- Builder/run image nếu sản phẩm được tạo bằng Cloud Native Buildpacks.
- Helm chart hoặc Kubernetes manifests.
- Configuration revision và feature-flag state.
- Database schema/migration level.
- SBOM, checksum, signature và build provenance.

Rollback code chỉ khôi phục một phần trong hệ thống. Nếu phiên bản mới đã thay đổi database schema, format message, cache key hoặc external API contract thì triển khai lại JAR cũ có thể vẫn không hoạt động.

```text
                Release 2.4.1
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
       App JAR     OCI image    Config/chart
          |           |           |
          +-----------+-----------+
                      |
                      v
             Release manifest
                      |
                      v
        Durable artifact repository
                      |
             deployment reference
                      |
                      v
             Production runtime

Nếu 2.4.1 gặp lỗi:
                      |
                      v
       Chọn manifest 2.4.0 đã xác minh
                      |
                      v
       Lấy đúng JAR/image theo digest
                      |
                      v
       Kiểm tra schema/config compatibility
                      |
                      v
             Deploy lại 2.4.0
                      |
                      v
       Health check + smoke test + metrics
```

**Rollback không phải build lại source của release cũ.** Hãy lấy đúng sản phẩm đã được build, test, scan và publish trước đó. Nếu build lại, dependency repository, toolchain, base image hoặc buildpack có thể đã khác, khiến output không còn là artifact đã được kiểm tra.

## 2. Phân biệt version, release, build và artifact identity

| Định danh | Ví dụ | Trả lời câu hỏi |
| --- | --- | --- |
| Product version | `2.4.1` | Người dùng gọi phiên bản ứng dụng là gì? |
| Release ID | `orders-api-2026-11-09.3` | Lần phát hành cụ thể nào? |
| Git commit | `9f31c2a...` | Source code được build từ commit nào? |
| CI run ID | `845201` | Pipeline/build run nào tạo sản phẩm? |
| Maven coordinates | `com.acme:orders-api:2.4.1` | Artifact JAR được lưu dưới tọa độ nào? |
| SHA-256 | `sha256:...` | Bytes của file JAR có đúng bản đã lưu không? |
| OCI image digest | `registry.example.com/team/orders-api@sha256:...` | Image manifest/index chính xác nào được chạy? |
| Chart version | `orders-api chart 2.4.1` | Deployment templates nào được dùng? |
| Config revision | Git SHA của config repo | Cấu hình không chứa secret nào được triển khai? |
| Schema version | `V42` hoặc migration ID | Database đã ở mức thay đổi nào? |
| Deployment revision | Kubernetes/Helm revision | Lần cập nhật runtime nào đã xảy ra? |

**Product version không đồng nghĩa với artifact identity.** Hai build có thể cùng version `2.4.1` nhưng được tạo từ commit, dependency, build environment hoặc file bytes khác nhau. Release production cần có cả version dễ đọc và identity kỹ thuật không nhập nhằng.

### 2.1. Maven coordinates cho JAR

Một artifact Maven thường được xác định bởi:

```text
groupId : artifactId : version : packaging : classifier
```

Ví dụ:

```text
com.acme : orders-api : 2.4.1 : jar
```

Repository path Maven-compatible thường có dạng:

```text
com/acme/orders-api/2.4.1/orders-api-2.4.1.jar
com/acme/orders-api/2.4.1/orders-api-2.4.1.pom
```

Nếu project publish executable Spring Boot JAR với classifier riêng, ghi classifier đúng vào release manifest. Không đoán tên file từ tên project; hãy lưu đường dẫn và checksum của file thực tế đã publish.

### 2.2. OCI image digest cho container

Tag dễ đọc, ví dụ `orders-api:2.4.1`, thuận tiện để tìm kiếm nhưng có thể bị gán lại cho image khác. Digest là định danh content-addressed của manifest hoặc image index.

Dạng triển khai chính xác:

```text
registry.example.com/team/orders-api@sha256:<image-digest>
```

Tag `2.4.1` có thể giữ làm alias cho con người, nhưng deployment record nên ghi digest thực tế. Với multi-platform image, digest có thể định danh image index chứa nhiều platform manifests; ghi đúng index digest đã xác minh và platform mà runtime sử dụng.

Không dùng `latest` làm identity rollback. Tag có thể trỏ sang image mới trong khi Deployment/manifest lịch sử vẫn lưu chuỗi tag cũ.

## 3. Quy tắc tạo release identity rõ ràng

Một release ID nên duy nhất và có thể truy về source/build. Ví dụ:

```text
service       = orders-api
version       = 2.4.1
release-id    = orders-api-2.4.1-build-845201
git-commit    = 9f31c2a7...
git-tag       = v2.4.1
build-run     = 845201
artifact      = com.acme:orders-api:2.4.1:jar
image         = registry.example.com/team/orders-api@sha256:...
chart         = orders-api-2.4.1
config-rev    = 7bc12d0...
schema-level  = V42
```

Quy tắc thực tế:

1. Version release không được tái sử dụng cho bytes khác.
2. Release tag được bảo vệ và gắn với một Git commit cụ thể.
3. CI run ID/build number là metadata riêng, không dùng thay product version.
4. Mỗi artifact có checksum/digest được ghi sau khi package/publish.
5. Manifest liên kết source, build, artifact, chart/config và schema level.
6. Mọi lần deploy/rollback lưu lại release ID và digest thực tế.
7. Nếu phải sửa release đã phát hành, tạo version/release mới; không ghi đè artifact cũ.

Với Maven release repository, bật policy không cho ghi đè cùng release coordinates. Với OCI registry, dùng immutable tag policy nếu có và vẫn deploy bằng digest. Chỉ đổi tên tag không tạo ra artifact mới và không chứng minh nội dung image.

## 4. Lưu sản phẩm đã build ở nơi có thể khôi phục

Artifact phải nằm trong kho bền vững, có retention policy và quyền đọc dành cho quy trình rollback. Local Maven cache, Gradle cache, Docker cache của laptop hoặc GitHub Actions temporary artifact không phải nơi lưu release lâu dài.

| Sản phẩm | Nơi lưu phù hợp | Metadata cần lưu |
| --- | --- | --- |
| Spring Boot executable JAR | Maven-compatible release repository hoặc artifact store | GAV/classifier, POM, SHA-256, signature |
| OCI image | Container registry | Repository, tag alias, manifest/index digest, platforms |
| Helm chart | OCI registry hoặc chart repository | Chart name/version, digest, values/config revision |
| SBOM | Artifact store gắn release | SBOM format/version, checksum |
| Provenance/attestation | Artifact store hoặc attestation service | Builder identity, source, subject digest |
| Kubernetes manifests | Git/config repository | Commit SHA, release ID, rendered manifest |
| Runtime config | Config repository/secret manager | Revision/reference, không lưu secret plaintext |
| Database backup | Backup system riêng | Snapshot ID, timestamp, consistency/restore evidence |

### 4.1. Tách snapshot và release repository

- **Snapshot/dev:** có thể thay đổi hoặc được dọn theo tuổi đời; không dùng làm nguồn rollback production.
- **Release:** version bất biến, quyền publish hạn chế, retention dài hơn và được backup/replicate theo policy.
- **Quarantine:** artifact chưa được duyệt hoặc có finding cần điều tra.
- **Promotion:** cùng artifact được đưa từ môi trường test sang staging/production mà không rebuild.

Không đặt release và snapshot vào cùng cleanup rule dễ xóa nhầm. Release repository nên từ chối overwrite cùng tọa độ/version; rollback cần đọc artifact cũ bằng read identity.

### 4.2. Retention phải tính theo cửa sổ rollback

Định nghĩa retention theo yêu cầu vận hành, không chỉ theo dung lượng:

- Giữ tất cả artifact đang được deploy ở mọi môi trường.
- Giữ ít nhất các release cuối cùng được policy quy định.
- Giữ release trong thời gian tối thiểu bằng rollback window, cộng thời gian điều tra/audit cần thiết.
- Giữ chart, manifest, SBOM, signature và config revision tương ứng.
- Giữ database backup/snapshot theo lịch và quy định phục hồi riêng.
- Chỉ garbage-collect artifact không còn được release/deployment nào tham chiếu và đã hết retention.

Ví dụ một nhóm có thể giữ 10 release gần nhất và tối thiểu 90 ngày; đây chỉ là giá trị minh họa. Chọn con số theo RTO/RPO, tần suất release, dung lượng và nghĩa vụ lưu trữ của tổ chức.

**Retention chưa được kiểm chứng nếu chưa thử restore.** Định kỳ tải lại release cũ bằng đúng quyền mà rollback job sẽ sử dụng, kiểm tra checksum/digest và xác nhận artifact vẫn chạy được trong staging.

## 5. Tạo release manifest cho mỗi lần publish

Release manifest là bản ghi liên kết mọi thứ cần để xác định và triển khai lại release. Nên sinh tự động từ CI sau khi build/publish thành công, lưu cạnh artifact hoặc trong release metadata store.

Ví dụ `release-manifest.yaml` dưới đây dùng giá trị minh họa; digest/checksum phải được CI điền bằng giá trị thực:

```yaml
schemaVersion: 1
service: orders-api

release:
  version: 2.4.1
  releaseId: orders-api-2.4.1-build-845201
  gitTag: v2.4.1
  gitCommit: 9f31c2a7f6e1
  buildRunId: "845201"
  createdAt: "2026-11-09T03:15:00Z"

build:
  javaVersion: "17"
  springBootVersion: "3.3.13"
  buildTool: maven
  mavenVersion: "3.9.9"
  builderImage: "paketobuildpacks/builder-jammy-base@sha256:<builder-digest>"

artifacts:
  jar:
    coordinates: "com.acme:orders-api:2.4.1:jar"
    repository: "company-releases"
    sha256: "<jar-sha256>"
  image:
    reference: "registry.example.com/team/orders-api@sha256:<image-digest>"
    platforms:
      - linux/amd64
      - linux/arm64
  sbom:
    uri: "artifact-store://orders-api/2.4.1/sbom.cdx.json"
    sha256: "<sbom-sha256>"
  provenance:
    uri: "artifact-store://orders-api/2.4.1/provenance.json"

deployment:
  chart: "orders-api"
  chartVersion: "2.4.1"
  configRepository: "platform-config"
  configRevision: "7bc12d0e4a91"

database:
  migrationLevel: "V42"
  compatibility: "backward-compatible"
```

Các giá trị `<builder-digest>`, `<image-digest>`, `<jar-sha256>` và `<sbom-sha256>` là trường cần thay bằng kết quả thật, không phải giá trị để copy vào production. Không đưa token, password, private key hoặc secret plaintext vào manifest. Chỉ lưu reference/version của secret trong secret manager nếu cần truy vết.

### 5.1. Manifest phải được kiểm tra trước deploy

Release/deploy job nên từ chối manifest nếu:

- Git commit không khớp tag/release source được duyệt.
- Artifact coordinate hoặc digest không tồn tại trong repository/registry.
- Checksum của JAR/SBOM không khớp.
- Image không có platform mà target runtime yêu cầu.
- Chart/config revision không còn truy cập được.
- Schema compatibility không cho phép chạy version được chọn.
- Signature/attestation bắt buộc bị thiếu hoặc không hợp lệ.

Manifest là index có cấu trúc, không tự bảo đảm tính xác thực. Với release có yêu cầu cao, ký manifest/attestation và xác minh builder identity cùng subject digest trước khi triển khai.

## 6. Build một lần, lưu một lần, promote cùng artifact

Pipeline tốt tách ba hoạt động:

1. **Build:** compile, test, scan, package và tính checksum/digest.
2. **Publish:** lưu artifact đã kiểm tra vào release repository/registry với version bất biến.
3. **Promote/deploy:** lấy đúng artifact theo identity và triển khai ở môi trường đích.

```text
Source commit
     |
     v
Build + tests + security scan
     |
     v
Create JAR / OCI image
     |
     v
Calculate checksum / image digest
     |
     v
Publish immutable artifact
     |
     +---------------------+
     |                     |
     v                     v
   Staging              Production
     |                     |
     +----------+----------+
                |
                v
      Same artifact digest
```

Không build lại ở staging/production từ cùng Git tag rồi giả định output giống nhau. Compare digest của artifact được tải ở từng môi trường với release manifest.

### 6.1. Maven: lưu và lấy lại executable JAR

Một release pipeline Maven có thể chạy:

```bash
./mvnw -B -ntp clean verify
./mvnw -B -ntp deploy
```

`deploy` chạy lifecycle tới phase deploy sau các phase trước đó; repository đích được cấu hình bằng `distributionManagement` hoặc deployment settings. Sau khi publish, ghi tọa độ chính xác và SHA-256 của executable JAR.

Khi cần lấy lại JAR `com.acme:orders-api:2.4.1:jar` từ Maven-compatible repository:

```bash
./mvnw -B -ntp \
  org.apache.maven.plugins:maven-dependency-plugin:3.8.1:get \
  -Dartifact=com.acme:orders-api:2.4.1:jar
```

Maven Dependency Plugin tải artifact theo coordinates vào local repository của user. Với groupId `com.acme`, artifactId `orders-api` và version `2.4.1`, đường dẫn mặc định thường là:

```text
~/.m2/repository/com/acme/orders-api/2.4.1/orders-api-2.4.1.jar
```

Nếu có classifier, packaging khác hoặc local repository được cấu hình riêng, đường dẫn sẽ thay đổi. Hãy dùng coordinates và repository settings trong manifest.

Kiểm tra checksum trước khi chạy:

```bash
sha256sum ~/.m2/repository/com/acme/orders-api/2.4.1/orders-api-2.4.1.jar
```

So sánh output với `jar.sha256` đã lưu trong release manifest/metadata độc lập. Nếu mismatch, dừng rollback và điều tra; không tự cập nhật expected checksum từ file vừa tải.

`mvn deploy` ở bước build đầu tiên publish sản phẩm của lần build đó. Khi rollback, lấy artifact cũ đã lưu; không chạy `clean verify deploy` từ source cũ để tạo file mới rồi coi đó là cùng sản phẩm.

### 6.2. Gradle: publish và retrieve artifact

Gradle Maven Publish Plugin cho phép khai báo publication có `groupId`, `artifactId`, `version` và artifact được publish vào Maven-compatible repository. Với Spring Boot application, phải cấu hình publication để lưu đúng **executable `bootJar`** nếu đó là sản phẩm runtime; không mặc định publication từ Java component sẽ là đúng Boot executable archive trong mọi cấu hình.

Ví dụ pipeline khi project đã cấu hình publication cho Boot JAR:

```bash
./gradlew --no-daemon clean check bootJar publish
```

Ghi lại artifact path, Maven coordinates, SHA-256 và repository URL trong release manifest. Khi rollback, tải đúng tọa độ/version đã lưu từ repository bằng client/repository API được tổ chức hỗ trợ, rồi kiểm tra checksum trước khi chạy.

Gradle cache hoặc thư mục `build/libs` trên runner không phải release archive lâu dài. Bảo đảm artifact được publish ra kho bền vững và policy không xóa version còn trong rollback window.

### 6.3. OCI image: publish và pin digest

Sau khi tạo image, publish tag release duy nhất:

```bash
docker push registry.example.com/team/orders-api:2.4.1
```

Lưu digest mà registry trả về sau push và ghi vào manifest. Đọc lại image bằng digest:

```bash
docker pull registry.example.com/team/orders-api@sha256:<image-digest>
```

Kiểm tra digest/manifest từ registry bằng công cụ được hỗ trợ:

```bash
docker buildx imagetools inspect registry.example.com/team/orders-api:2.4.1
```

Khi deploy, dùng reference `repository@sha256:digest` thay vì tag mutable. Không retag image cũ thành `latest` rồi dùng `latest` làm định danh rollback. Tag chỉ là alias; digest là identity của manifest/index cụ thể.

## 7. Lưu cả chart, config và các dependency runtime

Khôi phục đúng image vẫn chưa đủ nếu lần deploy trước sử dụng chart/config khác. Mỗi release nên lưu:

- Helm chart package và chart version/digest.
- Rendered Kubernetes manifests hoặc commit GitOps chứa manifest.
- Non-secret configuration revision.
- Feature flag snapshot/export nếu hệ thống hỗ trợ.
- Secret references/version trong secret manager, không lưu secret values.
- Ingress/API routing và service contract version khi có thay đổi.
- Database migration level và backup/snapshot reference.
- Runtime requirements như Java version, environment variables bắt buộc, port, volume path và resource constraints.

Không rollback secret version tự động nếu rotation là phản ứng bảo mật. Nếu credential bị thu hồi/compromise, rollback ứng dụng phải dùng secret hiện hành tương thích hoặc forward-fix; không khôi phục secret đã bị vô hiệu hóa.

### 7.1. Tách app release và config release

Có thể version hóa app và config độc lập, nhưng release manifest phải ghi cặp version đã chạy cùng nhau. Khi rollback app, chọn config revision tương thích; không mặc định config hiện tại có thể chạy với app cũ.

| Release | App image | Config revision | DB schema |
| --- | --- | --- | --- |
| 2.4.0 | digest A | config `c120...` | V41 |
| 2.4.1 | digest B | config `c811...` | V42 |

Nếu rollback về app 2.4.0, cần biết app đó có chạy được với config `c811...` và schema V42 hay phải khôi phục config tương thích. Thay đổi cấu hình cũng cần review/test như code.

## 8. Database migration: điều kiện quan trọng nhất của rollback

Rollback application không tự rollback database. Schema và dữ liệu có thể đã thay đổi trong lúc phiên bản mới chạy.

Ví dụ nguy hiểm:

1. App 2.4.1 đổi tên cột `customer_name` thành `display_name` rồi xóa cột cũ.
2. App 2.4.1 ghi dữ liệu theo schema mới.
3. Team triển khai lại app 2.4.0 vốn chỉ đọc `customer_name`.
4. App cũ lỗi vì cột đã bị xóa.

### 8.1. Dùng expand-and-contract

Chia thay đổi schema thành nhiều release:

```text
Release A: EXPAND
  - Add new column/table/index
  - Keep old schema
  - Old app continues working

Release B: MIGRATE
  - New app reads/writes compatible format
  - Backfill data
  - Validate old/new values

Release C: CONTRACT
  - Confirm no old app/client depends on old schema
  - Remove old column/API only in a later release
```

Rollback app ở giai đoạn expand/migrate có thể vẫn chạy vì schema cũ còn tồn tại. Chỉ contract sau khi rollback window của app cũ đã hết và xác nhận không còn consumer phụ thuộc.

### 8.2. Quy tắc cho migration

- Migration additive (thêm cột nullable, bảng mới, index tương thích) thường dễ rollback app hơn destructive migration.
- Tránh rename/drop/alter kiểu phá tương thích trong cùng release với app.
- Backfill dữ liệu nên idempotent, có checkpoint và có thể tiếp tục an toàn.
- Không tự chạy down migration khi rollback app nếu chưa đánh giá data loss và consumer dependencies.
- Nếu migration không thể đảo ngược, chuẩn bị backup/restore và kiểm tra thời gian phục hồi trước release.
- Ghi migration level vào release manifest.
- Test app version cũ trên schema sau migration mới trong staging.

**Rollback binary và rollback data là hai quyết định riêng.** Nếu dữ liệu đã được ghi theo format mới hoặc migration destructive đã chạy, forward-fix có thể an toàn hơn cố ép schema quay ngược.

## 9. Rollback với Kubernetes Deployment

Kubernetes lưu lịch sử ReplicaSet của Deployment và cung cấp `kubectl rollout history`/`kubectl rollout undo` để xem và quay lại Pod template trước. Trường `revisionHistoryLimit` điều chỉnh số ReplicaSets cũ được giữ; giá trị 0 tắt khả năng rollback qua lịch sử Deployment.

### 9.1. Xem revision hiện tại và lịch sử

```bash
kubectl rollout history deployment/orders-api -n production
kubectl rollout history deployment/orders-api --revision=12 -n production
kubectl rollout status deployment/orders-api -n production
```

Ghi nhận revision, image reference, annotations/change-cause và manifest tương ứng. Không suy ra product version chỉ từ số revision: Kubernetes revision là số lần Pod template thay đổi, không phải SemVer của ứng dụng.

### 9.2. Rollback về revision trước

```bash
kubectl rollout undo deployment/orders-api -n production
kubectl rollout status deployment/orders-api -n production --timeout=5m
```

Rollback về revision xác định:

```bash
kubectl rollout undo deployment/orders-api \
  --to-revision=11 \
  -n production

kubectl rollout status deployment/orders-api -n production --timeout=5m
```

Lệnh `rollout undo` khôi phục Pod template của revision đã lưu. Nó không tự khôi phục database, Secret/ConfigMap độc lập, external feature flags hoặc resource không nằm trong Pod template. Nếu các thành phần đó đã đổi, phải khôi phục phiên bản tương thích riêng.

### 9.3. Triển khai trực tiếp image theo digest

Nếu dùng GitOps/manifest làm nguồn sự thật, sửa manifest về digest cũ rồi để controller reconcile. Với thao tác imperative có kiểm soát, có thể đặt image theo digest:

```bash
kubectl set image deployment/orders-api \
  orders-api=registry.example.com/team/orders-api@sha256:<previous-image-digest> \
  -n production

kubectl rollout status deployment/orders-api -n production --timeout=5m
```

Tên container `orders-api` phải khớp container name trong Pod template. Sau thao tác, cập nhật GitOps source/release record để tránh controller tự ghi đè thay đổi thủ công.

### 9.4. Giữ lịch sử đủ lâu

Ví dụ Deployment manifest:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  revisionHistoryLimit: 20
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: registry.example.com/team/orders-api@sha256:<image-digest>
```

`revisionHistoryLimit: 20` chỉ là giá trị minh họa. Chọn số revision theo release frequency, dung lượng và rollback window. ReplicaSet history không thay thế artifact retention trong registry: nếu image digest đã bị xóa khỏi registry, rollback template vẫn có thể thất bại khi node cần pull image.

## 10. Rollback bằng Helm

Helm quản lý release revisions của chart và values. Trước khi rollback, xem lịch sử:

```bash
helm history orders-api -n production
```

Kiểm tra values của revision cần khôi phục:

```bash
helm get values orders-api --revision 11 -n production
```

Rollback về revision 11:

```bash
helm rollback orders-api 11 \
  -n production \
  --wait \
  --timeout 5m
```

Kiểm tra sau rollback:

```bash
helm history orders-api -n production
kubectl rollout status deployment/orders-api -n production --timeout=5m
```

Helm tạo một revision mới để ghi nhận thao tác rollback; revision mới không đồng nghĩa với app version mới. Có thể dùng `--dry-run` để mô phỏng thao tác trước khi thực hiện. Hooks có thể chạy trong rollback; cần hiểu hook behavior và side effects trước khi dùng `--no-hooks` hoặc `--force`.

Nếu chart revision cũ trỏ tới image tag mutable, Helm có thể triển khai image khác với image ban đầu của revision đó. Tốt nhất chart values lưu image digest hoặc tag bất biến được registry enforce. Lưu chart package và values/config revision cùng release manifest.

## 11. Rollback theo từng kiểu deployment

| Chiến lược | Cách rollback | Điều cần chú ý |
| --- | --- | --- |
| Rolling update | Revert Pod template hoặc rollout undo | ReplicaSet history, readiness và capacity |
| Blue-green | Chuyển traffic về environment trước đó | Database/schema và state dùng chung |
| Canary | Dừng tăng traffic, đưa weight về stable version | Metrics/traffic routing và background jobs |
| Helm release | Dùng Helm rollback về revision cụ thể | Chart, values, hooks và image digest |
| VM/JAR service | Lấy JAR cũ theo coordinates + checksum rồi restart service | systemd config, Java runtime, config/secret compatibility |
| Container service | Deploy lại image theo digest cũ | Registry retention, platform manifest |
| GitOps | Revert config commit về release manifest cũ | Controller reconciliation và source-of-truth |

Với canary/blue-green, rollback traffic nhanh có thể giảm impact, nhưng không sửa được side effects đã ghi vào database hoặc message broker. Cần dừng background workers/consumers nếu chúng đang ghi dữ liệu không tương thích.

## 12. Runbook rollback có thể thực hiện trong sự cố

Một runbook tốt phải đủ cụ thể để người trực có thể thực hiện khi áp lực cao.

### 12.1. Trigger và khoanh vùng

Rollback có thể được kích hoạt khi:

- Error rate vượt ngưỡng release policy.
- Latency/timeout tăng đáng kể sau deploy.
- Pod crash loop hoặc readiness không ổn định.
- Business metrics cho thấy giao dịch thất bại.
- Security incident yêu cầu rút release mới.
- Regression tái hiện được và bản cũ đã được xác nhận ổn định.

Ghi release đang chạy, thời điểm deploy, phạm vi ảnh hưởng và bằng chứng metrics/logs. Nếu có thể, pause promotion/traffic increase để ngăn rollout lan rộng.

### 12.2. Chọn đúng bản tốt gần nhất

1. Mở release manifest của bản đang chạy và các bản trước.
2. Chọn release cuối cùng có trạng thái known-good và đã được xác nhận ở production/staging.
3. Xác minh JAR checksum hoặc OCI digest còn tồn tại và có thể pull.
4. Kiểm tra chart/config revision, platform và runtime requirements.
5. Xác nhận schema/migration level hiện tại tương thích với app cũ.
6. Xác nhận artifact signature/provenance nếu policy yêu cầu.

Không chọn “version thấp hơn một số” theo cảm tính. Release liền trước có thể cũng lỗi, chưa từng chạy production hoặc không tương thích schema hiện tại.

### 12.3. Thực hiện rollback

1. Freeze release mới và dừng auto-promotion.
2. Chọn rollback target bằng release ID/manifest.
3. Nếu dùng Kubernetes/Helm, cập nhật Pod template/chart về đúng digest và config revision.
4. Nếu dùng JAR trên VM, tải artifact theo coordinates và kiểm tra SHA-256 trước khi thay file đang chạy.
5. Giữ backup/snapshot và không chạy down migration tùy tiện.
6. Chờ rollout/restart hoàn tất và readiness đạt.
7. Chạy smoke test, kiểm tra endpoint chính và luồng nghiệp vụ trọng yếu.
8. Theo dõi logs, error rate, latency, resource usage và business metrics.
9. Xác minh traffic/background workers đang chạy đúng release.
10. Ghi lại release ID, artifact digest, deployment revision, thời điểm và người thực hiện.

### 12.4. Sau rollback

- Thông báo trạng thái dịch vụ và phạm vi ảnh hưởng theo quy trình incident.
- Giữ lại logs, manifests, release manifest và deployment events.
- Xác định regression và điều kiện đã để lọt qua release gate.
- Tạo fix trong release mới; không sửa/ghi đè artifact cũ.
- Chạy lại đầy đủ tests/security gates và kiểm thử rollback nếu thay schema/config.
- Xác nhận release mới được promote từ artifact đã kiểm tra.

## 13. Kiểm chứng sau rollback

Rollback command trả thành công chỉ cho biết controller/repository chấp nhận thao tác. Nó không chứng minh ứng dụng hoạt động đúng.

Checklist kiểm chứng:

- [ ] Deployment/Helm release đạt trạng thái rollout complete.
- [ ] Image digest hoặc JAR checksum đang chạy khớp rollback manifest.
- [ ] Số replica ready/available đạt yêu cầu.
- [ ] Readiness/liveness và smoke tests pass.
- [ ] Luồng nghiệp vụ quan trọng thực hiện được.
- [ ] Database queries và migration compatibility ổn định.
- [ ] Message consumers/background jobs hoạt động bình thường.
- [ ] Logs không xuất hiện lỗi lặp lại.
- [ ] Error rate/latency/resource metrics trở lại ngưỡng chấp nhận.
- [ ] Config/feature flags đúng revision tương thích.
- [ ] Release record và incident timeline được cập nhật.

Nếu rollback đã hoàn tất nhưng error rate vẫn cao, có thể lỗi nằm ở database, external dependency, config, secret hoặc dữ liệu đã bị thay đổi. Đừng lặp đi lặp lại rollback cùng một binary khi evidence cho thấy nguyên nhân nằm ngoài application artifact.

## 14. Khi nào rollback, khi nào forward-fix?

| Tình huống | Hướng xử lý thường phù hợp |
| --- | --- |
| Regression trong code, schema vẫn backward-compatible | Rollback app về artifact known-good |
| Cấu hình mới sai, config revision cũ còn tương thích | Rollback config cùng app release |
| Image mới bị lỗi build/runtime, image cũ còn trong registry | Deploy digest cũ |
| Database đã drop/rename cột và app cũ không tương thích | Forward-fix hoặc restore dữ liệu theo kế hoạch; không rollback app mù quáng |
| Dữ liệu đã chuyển đổi một chiều | Đánh giá restore/compensating migration; có thể cần forward-fix |
| Release cũ có lỗ hổng bảo mật nghiêm trọng | Không rollback về bản vulnerable; phát hành fix an toàn |
| Artifact cũ đã bị xóa/không verify được | Dừng rollback tự động; khôi phục từ backup/replica đáng tin hoặc build release mới có kiểm soát |
| External API/queue contract đã đổi | Phối hợp rollback consumer/producer hoặc forward compatibility fix |
| Secret cũ đã bị revoke | Không khôi phục secret đã revoke; dùng credential mới tương thích |

**Rollback không phải lúc nào cũng là hành động an toàn nhất.** Nếu release cũ chứa lỗ hổng đang bị khai thác hoặc không thể đọc dữ liệu hiện tại, forward-fix có thể là cách giảm rủi ro tốt hơn.

## 15. Lỗi phổ biến khi thiết kế rollback

| Lỗi | Hậu quả | Phòng tránh |
| --- | --- | --- |
| Chỉ lưu Git tag, không lưu artifact | Không chắc tái tạo đúng binary cũ | Lưu JAR/image cùng manifest |
| Dùng image tag mutable | Tag có thể trỏ sang bytes mới | Deploy bằng digest |
| Ghi đè Maven release coordinates | Version cũ không còn là sản phẩm cũ | Enforce immutable release repository |
| Chỉ giữ vài Docker layers local | Runner/node mới không pull được artifact | Registry retention/replication và restore test |
| Xóa image cũ theo cleanup policy | Không thể rollback đúng digest | Exclude deployed/rollback-window artifacts khỏi GC |
| Không lưu chart/values/config | Image cũ chạy với cấu hình mới không tương thích | Version hóa và lưu config/chart revision |
| Không ghi DB migration level | Chọn app cũ không tương thích schema | Ghi migration level và test old-app/new-schema |
| Chạy down migration tự động | Có thể mất dữ liệu hoặc làm app khác lỗi | Đánh giá migration riêng, backup/restore có kiểm chứng |
| Dùng Kubernetes revision làm app version | Nhầm deployment history với release identity | Gắn release ID, Git SHA và digest vào annotations |
| `revisionHistoryLimit: 0` | Deployment không giữ history để undo | Đặt retention phù hợp và lưu manifest bên ngoài |
| Helm rollback nhưng tag mutable | Chart cũ có thể pull image mới | Pin digest trong values |
| Không thử khôi phục định kỳ | Phát hiện artifact thiếu đúng lúc sự cố | Diễn tập restore ở staging |
| Rollback traffic nhưng workers vẫn chạy bản mới | Background processing tiếp tục tạo dữ liệu không tương thích | Điều phối worker/consumer cùng release |
| Secret cũ bị thu hồi nhưng rollback config cũ | App cũ không kết nối được hoặc vi phạm security | Tách secret lifecycle và kiểm tra compatibility |

## 16. Thử nghiệm rollback trước khi cần dùng

Rollback phải được diễn tập như một hoạt động vận hành định kỳ.

Một bài diễn tập staging có thể:

1. Deploy release A bằng image digest A.
2. Ghi release manifest, chart/config revision và schema level.
3. Deploy release B bằng digest B với thay đổi tương thích schema.
4. Cố ý kích hoạt điều kiện rollback đã định, ví dụ smoke test fail trong staging.
5. Lấy manifest A từ artifact store.
6. Pull lại image A bằng digest, kiểm tra signature/checksum.
7. Rollback chart/Deployment về A và config tương thích.
8. Chạy smoke/integration tests và xác minh metrics.
9. Đo thời gian từ quyết định đến khi dịch vụ ổn định.
10. Kiểm tra artifact retention, quyền đọc và runbook có đủ thông tin không.

Ghi lại RTO thực tế, bước thủ công, quyền còn thiếu, artifact nào không tải được và schema compatibility issue. Cập nhật runbook sau diễn tập. Không dùng production làm nơi thử nghiệm rollback lần đầu.

## 17. Bài tập tự kiểm tra

**Tình huống A.** Git tag `v2.4.0` còn tồn tại nhưng image `orders-api:2.4.0` đã bị xóa. Có thể rollback chỉ từ tag?

*Đáp án:* Không đảm bảo. Git tag xác định source commit, không phải image bytes đã publish. Cần artifact đã lưu hoặc quy trình rebuild có kiểm soát; rebuild không tương đương exact artifact cũ.

**Tình huống B.** Release manifest ghi version 2.4.0 nhưng registry tag đang trỏ sang image mới. Dùng gì để khôi phục đúng image?

*Đáp án:* OCI repository@sha256:digest đã ghi trong manifest, sau khi xác minh digest và artifact còn tồn tại.

**Tình huống C.** Maven repository có JAR version 2.4.0 nhưng SHA-256 không khớp release manifest. Có nên chạy?

*Đáp án:* Không. Dừng rollback và điều tra artifact/repository; không cập nhật expected checksum chỉ để làm kiểm tra pass.

**Tình huống D.** Kubernetes rollout undo về revision trước nhưng app vẫn lỗi vì ConfigMap đã đổi. Vì sao?

*Đáp án:* Deployment revision chủ yếu khôi phục Pod template; ConfigMap độc lập cần được version hóa/khôi phục riêng hoặc được quản lý cùng release bằng Helm/GitOps.

**Tình huống E.** App 2.4.1 đã drop cột mà app 2.4.0 cần. Có nên rollback binary ngay?

*Đáp án:* Không trước khi đánh giá schema/data. Có thể cần forward-fix hoặc restore dữ liệu; expand-and-contract giúp giữ app cũ tương thích trong rollback window.

**Tình huống F.** Helm history cho thấy revision 8 là bản tốt. Lệnh rollback tạo revision 9. Bản app có phải version 9 không?

*Đáp án:* Không. Helm revision là thứ tự release operation; app version vẫn là version được ghi trong chart/image manifest.

**Tình huống G.** JAR cũ còn trong local Maven cache của một developer. Có đủ để làm nguồn rollback production?

*Đáp án:* Không. Cache cá nhân không phải artifact store bền vững có retention, access control, checksum/provenance và audit.

**Tình huống H.** Release cũ có CVE nghiêm trọng đã được xác nhận. Có nên rollback về nó khi release mới gặp regression?

*Đáp án:* Không tự động. Cần cân nhắc security risk; có thể forward-fix hoặc chọn một release khác đã known-good và không có vulnerability bị chặn.

## 18. Checklist nghiệm thu phương án rollback

**Artifact và định danh:**

- Mỗi release có product version, release ID, Git commit/tag và CI run ID.
- Maven JAR có coordinates/classifier chính xác và SHA-256.
- OCI image có repository/digest, platform manifest và registry location.
- Builder/run image, toolchain, SBOM và provenance được lưu khi policy yêu cầu.
- Release manifest liên kết app, image, chart, config và database migration level.
- Release coordinates/tags không bị ghi đè.

**Retention và truy cập:**

- Release artifacts được lưu trong durable repository/registry.
- Snapshot cleanup không ảnh hưởng release repository.
- Retention bao phủ rollback window và artifact đang deploy.
- Chart, config manifest, SBOM và metadata tương ứng cũng được giữ.
- Rollback identity có quyền read/pull cần thiết nhưng không cần quyền publish.
- Diễn tập restore xác nhận artifact cũ vẫn tải được và checksum/digest khớp.

**Database và runtime compatibility:**

- Migration dùng expand-and-contract khi cần rollback app.
- Old app được test trên schema sau migration mới.
- Down migration không tự chạy nếu có nguy cơ mất dữ liệu.
- Config/feature flags/secrets có version/reference và compatibility rõ.
- Message/API/cache contracts được đánh giá.
- Background workers/consumers được điều phối cùng app release.

**Thực thi và kiểm chứng:**

- Runbook chọn target theo release manifest, không chỉ theo version label.
- Kubernetes/Helm revision history được giữ đủ lâu.
- Image được deploy theo digest; không dựa vào mutable `latest`.
- Rollout/restart có timeout và health checks.
- Smoke test, business metrics và logs được kiểm tra sau rollback.
- Incident/release record lưu artifact digest, config revision, schema level và kết quả.
- Nhóm đã diễn tập rollback ở staging và biết RTO thực tế.

**Kết luận:** Một phương án rollback có thể tin cậy khi nhóm lưu được **đúng sản phẩm đã build**, định danh bằng Maven coordinates hoặc OCI digest, giữ release manifest cùng source/build/config/schema metadata và kiểm tra được tính toàn vẹn trước khi triển khai lại. Kubernetes/Helm giúp khôi phục deployment revision, nhưng không tự hoàn nguyên database, external configuration hoặc dữ liệu. Hãy thiết kế compatibility và retention trước release, rồi diễn tập lấy artifact cũ, deploy lại và xác minh health để rollback có thể thực hiện đúng lúc cần.

### Tài liệu chính thức

- Docker Docs — Pull an image by digest: https://docs.docker.com/reference/cli/docker/image/pull/
- Docker Docs — Validate image inputs and require digest references: https://docs.docker.com/build/policies/validate-images/
- Apache Maven Deploy Plugin — Usage: https://maven.apache.org/plugins/maven-deploy-plugin/usage.html
- Apache Maven Dependency Plugin — dependency:get: https://maven.apache.org/plugins/maven-dependency-plugin/get-mojo.html
- Gradle — The Maven Publish Plugin: https://docs.gradle.org/current/userguide/publishing_maven.html
- Kubernetes — Update a Deployment Without Downtime and roll back: https://kubernetes.io/docs/tasks/run-application/update-deployment/
- Kubernetes — kubectl rollout undo: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/kubectl_rollout_undo/
- Kubernetes — Deployment revision history: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- Helm — helm history: https://helm.sh/docs/helm/helm_history/
- Helm — helm rollback: https://helm.sh/docs/helm/helm_rollback/
- Spring Boot 3.3 — Maven Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/
- Spring Boot 3.3 — Gradle Plugin: https://docs.spring.io/spring-boot/3.3/gradle-plugin/