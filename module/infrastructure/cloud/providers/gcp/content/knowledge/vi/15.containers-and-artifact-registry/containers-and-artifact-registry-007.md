# Image tags, digests và chính sách bất biến

> **Chương:** Container và Artifact Registry  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một nhóm phát triển đóng gói dịch vụ Java thành container image, đẩy lên **Artifact Registry**, rồi triển khai tới **Google Kubernetes Engine (GKE)** hoặc **Cloud Run**. Trong lần phát hành đầu, mọi thứ ổn định. Một tuần sau, pipeline tái sử dụng tag `orders-api:production` cho một build khác. Một số Pod mới chạy mã mới, một số Pod cũ vẫn chạy mã cũ. Câu hỏi khó trả lời lúc xử lý sự cố là: **“Artifact chính xác nào đang chạy?”**

Vấn đề không chỉ là tên Docker image. Cần hiểu ba cơ chế:

- **Image tag** là tên dễ đọc, chẳng hạn `v1.4.2` hoặc `build-2841-a1b2c3d`. Với repository mặc định, cùng một tag có thể trỏ tới image khác theo thời gian.
- **Image digest** là định danh nội dung của **manifest** hoặc **image index**, có dạng `sha256:<64 ký tự hex>`. Tham chiếu bằng digest xác định artifact cần tải, miễn nó còn tồn tại và caller có quyền truy cập.
- **Immutable image tags** là chính sách của Docker-format repository trong Artifact Registry, ngăn một tag đã có chuyển sang digest khác; đồng thời chặn gỡ tag và xóa image vẫn có tag.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ/cơ sở dữ liệu, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Bài thuộc chương **Container và Artifact Registry**, tập trung vào truy vết điều được build, lưu trữ và deploy.

**Sau bài học, bạn có thể:**

1. Đọc đúng reference theo tag và digest trong Google Artifact Registry.
2. Giải thích mutable tag, immutable tag, digest, manifest, layer và multi-platform image index.
3. Đặt tag cho CI/CD, release, hotfix, staging và production mà không ghi đè nhầm.
4. Bật, kiểm tra và vận hành chính sách **immutable image tags** trên Docker-format standard repository.
5. Dùng `docker` và `gcloud artifacts` để build, push, list digests, thêm tag, pull và kiểm thử.
6. Pin digest khi deploy GKE hoặc Cloud Run; hiểu hành vi resolution của hai nền tảng.
7. Kết hợp IAM, vulnerability scanning, provenance, Binary Authorization (khi phù hợp) và cleanup policies.
8. Thiết kế rollback, monitoring, xử lý lỗi và tối ưu chi phí không làm mất release artifacts.

## 1. Mô hình Artifact Registry: repository, image, version và tag

**Artifact Registry** quản lý artifacts như Docker/OCI container images, Maven/JAR, npm, Python packages và những định dạng khác. Một **repository** chọn format, location, mode và các chính sách vòng đời/bảo mật.

Cú pháp Docker image:

~~~text
LOCATION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE:TAG

Ví dụ:
asia-southeast1-docker.pkg.dev/acme-lab-123/orders-repo/orders-api:v1.4.2
\___________________/ \__________/\_________/ \________/ \____/
      registry host      project    repository    image      tag
~~~

Cùng version có thể tham chiếu bằng **digest**:

~~~text
LOCATION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE@sha256:<FULL_HEX_DIGEST>

Ví dụ minh họa, digest BỊ RÚT NGẮN và KHÔNG dùng để pull:
asia-southeast1-docker.pkg.dev/acme-lab-123/orders-repo/orders-api@sha256:ab12cd34...
~~~

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Registry host | Endpoint Docker và location của repository | `asia-southeast1-docker.pkg.dev` |
| Project | Project chứa repository | `acme-lab-123` |
| Repository | Nơi lưu nhiều image names/versions | `orders-repo` |
| Image name | Tập hợp các versions của một app | `orders-api` |
| Tag | Nhãn con người đọc được, tham chiếu một version | `v1.4.2` |
| Digest | Hash của manifest hoặc image index | `sha256:...` |
| Layer | Blob chứa thay đổi filesystem hoặc nội dung image | Dependencies, JAR... |
| Image version | Manifest/index định danh theo digest | Có thể có nhiều tags hoặc không có tag |

**Một image version có thể có nhiều tags; một tag tại một thời điểm trỏ tới đúng một image version**. Ngược lại, untagged version có thể vẫn truy cập bằng digest cho tới khi nó bị xóa.

### 1.1. Ví dụ nhiều tags trỏ đến một digest

~~~text
Image: orders-api

Digest D1 = sha256:aaa... (minh họa)
   ├── v1.4.2
   ├── build-a1b2c3d
   └── release-20261119-01

Digest D2 = sha256:bbb... (minh họa)
   ├── v1.5.0-rc1
   └── build-e5f6a7b

Digest D3 = sha256:ccc... (minh họa)
   └── (untagged)
~~~

Nhiều tags không nghĩa là nhiều copies dữ liệu độc lập. Các tags là tên tham chiếu; registry có thể sử dụng content blobs/layers với cơ chế quản lý riêng.

### 1.2. Các repository modes

| Mode | Mục đích | Phạm vi bài |
| --- | --- | --- |
| **Standard** | Đội phát triển push/pull trực tiếp | **Trọng tâm** tag immutability, retag, quản trị versions |
| **Remote** | Cache artifacts từ upstream như Docker Hub | Phụ thuộc upstream và cache, không giống push vào standard |
| **Virtual** | Endpoint tổng hợp các upstream repositories | Không phải nơi push trực tiếp release artifacts |

Bài lab dùng **Docker-format standard repository**. Không suy mọi thao tác quản trị trên standard repository đều có hiệu lực tương tự với remote/virtual.

## 2. Tag là tên tham chiếu, không phải định danh nội dung

Trong repository **mutable tags**:

1. Pipeline build image A, push `orders-api:staging` → tag `staging` trỏ digest A.
2. Pipeline build image B, push lại `orders-api:staging` → tag được **chuyển sang digest B**.
3. Image A có thể còn tại registry nhưng thành **untagged** nếu không còn tag khác.
4. Máy deploy `:staging` ở thời điểm khác nhau có thể nhận các digests khác nhau.

~~~mermaid
flowchart LR
    T["Tag staging"] --> A["Digest A\nBuild cũ"]
    PUSH["Push build B với :staging"] -. "Mutable repository" .-> T
    T -. "Sau lần push" .-> B["Digest B\nBuild mới"]
    A -. "Có thể vẫn được lưu" .-> OLD["A chưa tự biến mất\nCó thể pull theo digest"]
~~~

### 2.1. Tag `latest` không tự xác định bản mới nhất

Nếu reference không chỉ định tag, Docker workflows thường ngầm sử dụng `latest`:

~~~bash
docker pull LOCATION-docker.pkg.dev/PROJECT/REPO/orders-api
# Thường tương đương:
docker pull LOCATION-docker.pkg.dev/PROJECT/REPO/orders-api:latest
~~~

Nhưng tag `latest` **không có thuật toán tìm version lớn nhất**. Nếu pipeline chỉ push `:v2.0.0`, tag `latest` có thể vẫn trỏ vào digest cũ. Trong immutable repository, `latest` **cũng bất biến**, không thể cập nhật để trỏ sang build mới.

**Không dùng `latest` làm release identifier production.** Dùng unique version/build tags để truy vết và digest khi triển khai.

### 2.2. Các quy ước tag hữu ích

| Tag | Ví dụ | Lợi ích | Hạn chế |
| --- | --- | --- | --- |
| Semantic version | `v1.4.2` | Dễ đối chiếu release notes | Phải không rebuild ghi đè version đã công bố |
| Commit-derived | `git-a1b2c3d4` | Gắn với source | Một commit có thể có nhiều build/digest |
| CI run/build ID | `build-28451` | Có thể duy nhất qua pipeline | Cần lưu provenance để tra source |
| Release ID | `release-20261119-01` | Có lịch audit | Cần liên kết digest |
| Environment alias | `staging`, `prod` | Tiện khi mutable | Không thích hợp để pin bất biến |
| `latest` | `latest` | Dễ thử local | Không chứng minh release hiện tại |

**Commit SHA khác image digest**: commit hash mô tả source Git, image digest mô tả manifest/index sau build. Hai builds từ cùng commit có thể khác nhau vì base image, dependencies, metadata, timestamp, build args hay CPU architecture.

Quy ước tốt là **tag release không đổi ý nghĩa**, tag build có **build ID độc nhất**, không đặt secrets/PII trong tags và không coi hậu tố `-prod` là quyền truy cập hoặc bằng chứng được phê duyệt.

## 3. Image digest thực sự hash đối tượng nào?

**Digest** là hash nội dung, ví dụ SHA-256 của OCI/Docker manifest hoặc image index. Với reference `orders-api@sha256:...`, client yêu cầu manifest/index xác định.

Digest này **không phải**:

- Hash của tên tag hoặc Git commit.
- Docker local image ID trong mọi trường hợp.
- Hash của chỉ một layer, hoặc toàn bộ source tree.
- Bằng chứng tác giả, chữ ký hoặc kết quả quét bảo mật.
- Cam kết artifact sẽ được lưu mãi mãi.

### 3.1. Manifest, config và layers

~~~mermaid
flowchart TD
    REF["IMAGE@sha256:D_MANIFEST"] --> MAN["OCI image manifest"]
    MAN --> CFG["Config blob\nEntrypoint, env, architecture"]
    MAN --> L1["Layer 1 digest\nBase filesystem"]
    MAN --> L2["Layer 2 digest\nDependencies"]
    MAN --> L3["Layer 3 digest\nApp JAR"]
    TAG["Tag v1.4.2"] -. "Tên tham chiếu" .-> MAN
~~~

Manifest chứa tham chiếu đến config và layers. Thay đổi bytes của manifest, thứ tự annotations, loại serialization hoặc digest của layer đều có thể làm **manifest digest thay đổi**. Docker local image ID thường là hash của config JSON nên có thể **khác** registry manifest digest.

### 3.2. Multi-platform: index digest và child manifest digest

Một tag có thể trỏ tới **OCI image index / Docker manifest list** để hỗ trợ nhiều architectures:

~~~text
orders-api:v1.4.2
       |
       v
Index digest: sha256:INDEX...
       |
       +-- linux/amd64 -> Manifest digest: sha256:AMD...
       |
       +-- linux/arm64 -> Manifest digest: sha256:ARM...
~~~

Khi pull image multi-platform, runtime chọn manifest phù hợp OS/CPU. Vì vậy:

- **Pin image index digest** giữ cố định tập child manifests được liệt kê.
- Với điều tra binary trên node cụ thể, ghi cả **platform** và **child manifest digest**.
- Scan/provenance/signature có thể tham chiếu index hoặc child manifest tùy công cụ; phải kiểm tra đúng phạm vi.
- Không so index digest với child digest rồi kết luận image bị thay đổi.

### 3.3. Tính lặp lại của build

~~~text
Source commit A -> Build 42 -> Manifest D1
Source commit A -> Build 43 -> Manifest D2 (có thể khác)
Source commit B -> Build 44 -> Manifest D3

Tag v1.0.0 -> D1
Tag rc-2   -> D2
Deploy IMAGE@D1 -> yêu cầu đúng D1 khi artifact còn sẵn
~~~

Digest giúp cố định **artifact**, không tự làm build reproducible. Nếu cần reproducible build, phải kiểm soát base images theo digest, dependencies, toolchain, build args, môi trường, timestamp và output comparison.

## 4. Mutable và immutable tags trong Artifact Registry

Artifact Registry cho phép Docker-format repository dùng **mutable** hoặc **immutable image tags**. Cài đặt này là **thuộc tính của repository**, không phải một cờ riêng tùy ý gắn cho mỗi tag.

### 4.1. Mutable: hành vi mặc định

Khi `Immutable image tags` **tắt**, có thể:

- Chuyển một tag cũ từ D1 sang D2 khi push/retag image mới.
- Gỡ tag khỏi image version.
- Xóa image có tag theo quyền và quy trình xác nhận.
- Giữ image version cũ không có tag; version đó vẫn có thể pull bằng digest nếu chưa xóa.

Mutable tags hỗ trợ aliases như `dev` hoặc `staging`, nhưng gây rủi ro không tái lập được kết quả deploy.

### 4.2. Immutable: những điều bị chặn

| Thao tác | Mutable repository | Immutable repository |
| --- | --- | --- |
| Push D1 với tag mới `v1` | Cho phép | Cho phép |
| Push D2 với tag `v1` đang trỏ D1 | Chuyển tag sang D2 | **Từ chối** |
| Thêm tag **chưa được sử dụng** vào D1 | Cho phép | **Cho phép** |
| Gỡ `v1` khỏi D1 | Cho phép theo quyền | **Từ chối** |
| Xóa D1 khi vẫn có `v1` | Có thể theo quyền/`--delete-tags` | **Từ chối** |
| Xóa một untagged image version | Có thể | Có thể |
| Chuyển `latest` từ D1 sang D2 | Cho phép | **Từ chối** |
| Cleanup policy xóa tagged versions | Có thể nếu rule khớp | **Không thể xóa tagged versions** |
| Thay labels repository khi immutable bật | Cho phép theo quyền | Bị hạn chế theo update settings |

**Bất biến là khi chính sách có hiệu lực.** Người đủ quyền quản trị repository có thể chuyển cài đặt về mutable bằng `--no-immutable-tags`. Đây **không phải WORM storage hoặc retention lock**. Chính sách không ngăn mọi administrator chỉnh cấu hình rồi xóa artifact.

### 4.3. Vì sao chặn xóa tagged image?

Image được pin theo digest vẫn cần **còn tồn tại** để GKE scale-out hoặc Cloud Run triển khai revision mới/rollback. Chặn xóa tagged version giúp tránh thao tác xóa nhầm một artifact đã được đặt release tag.

Tuy nhiên, image vẫn có thể biến mất nếu repository bị xóa, quản trị viên tắt immutable trước khi xóa, hoặc cơ chế quản trị ngoài phạm vi rule can thiệp. Một image độc hại được push với tag mới vẫn có thể trở thành “bất biến”. Do đó **IAM, scanning, provenance và audit** là các lớp bắt buộc.

### 4.4. Cập nhật chính sách trên repository hiện có

~~~bash
# Thay đổi repository, ảnh hưởng mọi tags:
gcloud artifacts repositories update REPOSITORY \
  --location=LOCATION \
  --project=PROJECT_ID \
  --immutable-tags

# Chỉ dùng khi có phê duyệt để tắt policy:
gcloud artifacts repositories update REPOSITORY \
  --location=LOCATION \
  --project=PROJECT_ID \
  --no-immutable-tags
~~~

Nếu pipeline đang tái sử dụng `:latest` hoặc xóa tags sau mỗi build, bật immutable sẽ khiến lần push/cleanup tiếp theo thất bại. Đây là giới hạn có chủ đích; cần **sửa pipeline sang unique tags** thay vì tự động tắt chính sách.

### 4.5. Phân loại môi trường

| Môi trường | Gợi ý | Lý do |
| --- | --- | --- |
| Local developer | Mutable local tags | Thử nhanh, không liên quan release registry |
| Dev repository | Có thể mutable, unique build tags vẫn tốt | Dễ cleanup, kiểm soát rủi ro |
| Staging/release candidate | Unique tags, cân nhắc immutable | Giảm nhầm lẫn artifact qua test |
| Production repository | Immutable tags + IAM chặt + deploy digest | Truy vết, hạn chế retag/xóa nhầm |
| High-assurance | Thêm attestation, verification, backup | Immutable tags chưa chứng minh artifact tin cậy |

Nếu tách repo dev/release, cần **promote artifact đã kiểm thử** sang repository đích và xác minh digest cuối cùng; thao tác sao chép có thể ảnh hưởng manifest/index tùy công cụ.

## 5. Quy ước tag trong CI/CD và phát hành

Một pipeline release nên lưu **hai tham chiếu**:

1. **Tên con người đọc:** một unique version/build tag.
2. **Định danh máy chạy:** digest của manifest/index sau khi push.

~~~mermaid
flowchart LR
  GIT["Source commit"] --> BUILD["Cloud Build / CI"]
  BUILD --> IMG["Artifact Registry\nUnique build tag"]
  IMG --> DIG["Resolve manifest digest"]
  DIG --> TEST["Scan, test, approval, attestation"]
  TEST --> DEPLOY["Deploy GKE/Cloud Run\nIMAGE@sha256:..."]
  DIG --> RECORD["Release manifest\nCommit + build ID + digest"]
  DEPLOY --> OBS["Logs, errors, rollout/rollback"]
~~~

### 5.1. Quy ước gợi ý

| Loại | Tag | Nguyên tắc |
| --- | --- | --- |
| CI build | `build-002841-a1b2c3d` | Unique theo pipeline run |
| Release candidate | `rc-1.5.0-2` | Không tái dùng cho candidate mới |
| Release chính thức | `v1.5.0` | Gắn sau approval, không đổi ý nghĩa |
| Hotfix | `v1.5.1` | **Tag mới**, không push đè `v1.5.0` |
| Rollback | **Digest của release cũ** | Đổi deployment config, không move `prod` tag |

**Short commit SHA một mình chưa chắc unique** khi cùng commit được build nhiều lần. Nên lưu Git SHA, CI run ID, digest, timestamp, nguồn base image và kết quả scan/approval trong release record.

### 5.2. Promotion không cần rebuild

~~~text
Build 2841 -> orders-api:build-2841-a1b2c3d -> digest D1
       |
       +-- test + scan + release approval
       |
       +-- thêm tag v1.5.0 vào D1 (tag chưa từng dùng)
       |
       +-- deploy orders-api@D1
       |
       +-- release record: project/location/repo/name, digest, build, approver
~~~

**Thêm tag mới không rebuild.** Nhờ vậy, artifact D1 đã vượt kiểm thử chính là artifact production yêu cầu. Rebuild cùng commit có thể tạo D2 khác D1 dù bản ứng dụng có vẻ tương đương.

### 5.3. Nếu cần aliases `staging` và `production`?

Immutable repository không phù hợp việc “mỗi deploy chuyển `production` sang image mới”. Thay bằng:

- GitOps/Kubernetes manifest chứa `IMAGE@sha256:...` và pull request cập nhật.
- Release database ghi mapping `environment → digest` với audit/approval.
- Cloud Run traffic giữa **revisions** hoặc release aliases ở tầng ứng dụng.
- Nếu bắt buộc có mutable alias, giữ ở môi trường/repository riêng, không coi đó là release evidence.

## 6. Digest không thay thế bảo mật chuỗi cung ứng

**Pin digest** xác định artifact có hash cụ thể, nhưng không xác định artifact **được ai tạo, có đáng tin hay có CVE chưa được xử lý**.

| Lớp | Mục tiêu | Biện pháp |
| --- | --- | --- |
| Source control | Ai sửa mã? | Branch protection, review, signed commits nếu cần |
| Build | Mã/dependency nào tạo image? | CI logs, provenance, SBOM, pin base image |
| Artifact storage | Ai có thể push/retag/delete? | Artifact Registry IAM + immutable tags |
| Vulnerability | Có CVE và policy severity không? | Artifact Analysis/scanning, remediation |
| Authenticity | Image do pipeline tin cậy tạo? | Attestations/signatures và verification |
| Deploy approval | Digest có được phép chạy? | Binary Authorization hoặc policy gates được hỗ trợ |
| Runtime | Workload có quyền/network tối thiểu? | GKE/Cloud Run IAM, security context, network policies |
| Audit/rollback | Digest nào ở môi trường nào? | Release record, GitOps, audit logs, metrics |

### 6.1. Manifest digest bảo vệ điều gì?

Nếu client yêu cầu manifest D1, thay manifest bytes nhưng vẫn giữ digest D1 sẽ không còn khớp hash. Đây là ưu điểm **content-addressable identification**.

Tuy nhiên, hash không chứng minh source đã được review, base image không có lỗ hổng, người push là người được tin cậy hoặc runtime được cấu hình an toàn.

### 6.2. Vulnerability scanning

Artifact Registry có khả năng tích hợp vulnerability scanning/Artifact Analysis theo chế độ và điều kiện hỗ trợ. Scan nên gắn với **image digest/version**; kết quả có thể thay đổi theo thời gian khi dữ liệu CVE cập nhật. Một artifact từng “scan PASS” không có nghĩa không thể xuất hiện CVE mới.

### 6.3. Provenance, signatures và Binary Authorization

Một chính sách kiểm soát deploy có thể yêu cầu:

~~~text
Chỉ deploy nếu:
  - digest D có provenance từ CI pipeline được duyệt;
  - repository release có IAM phù hợp;
  - image đã qua scan và các attestations yêu cầu;
  - service identity có quyền pull tối thiểu;
  - manifest triển khai pin IMAGE@sha256:D;
  - change/release record được phê duyệt.
~~~

Đây là **quy trình đề xuất**, không phải hành vi tự bật bởi `--immutable-tags`. Binary Authorization và các cơ chế ký/kiểm tra phải được cấu hình riêng theo sản phẩm, vùng và policy hiện hành.

### 6.4. Quyền thay đổi immutability

Vì administrator có thể tắt policy, cần:

- Tách quyền **Writer** của CI service account và **Administrator** chỉ cấp cho nhóm quản trị được phê duyệt.
- Giới hạn IAM scope ở repository/project phù hợp.
- Theo dõi Audit Logs khi repository settings/IAM thay đổi.
- Không cấp `roles/artifactregistry.admin` cho pipeline chỉ cần push image.
- Đánh giá quyền delete repository, kế hoạch backup và khả năng khôi phục.
- Nếu dùng perimeter/organization policies, xác minh chúng áp dụng đúng tài nguyên.

**Immutable tag là lớp bảo vệ hành vi registry, không phải một cơ chế lưu trữ vĩnh viễn không thể xóa.**

## 7. Chuẩn bị lab: repository dành riêng cho phát hành

**Mục tiêu:** Tạo một Docker-format **standard repository** bật immutable tags. Build image mẫu, push với tag mới, đọc digest, thử push một digest khác với **cùng tag** và xác minh registry từ chối. Sau đó gắn một release tag **mới** lên version đã có và pull bằng digest.

**Không chạy trên repository production hoặc repository dùng chung.** Các lệnh create/update/delete có tác động thật và có thể phát sinh phí.

| Giá trị | Ví dụ |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| Location | `asia-southeast1` |
| Repository | `orders-release-lab` |
| Format/mode | Docker / Standard |
| Chính sách | Immutable image tags |
| Image name | `orders-api` |
| Tag đầu tiên | `v1.0.0` |
| Tag thứ hai | `v1.0.1` |
| Release tag | `release-20261119-01` |

### 7.1. IAM, mạng và công cụ

| Công việc | Vai trò thường dùng | Nguyên tắc |
| --- | --- | --- |
| Liệt kê/pull images, tags, versions | `roles/artifactregistry.reader` | Cấp trên đúng repository |
| Push image, thêm tag | `roles/artifactregistry.writer` | Build service account |
| Xóa image/gỡ tag khi policy cho phép | `roles/artifactregistry.repoAdmin` | Hạn chế cho người vận hành được phép |
| Tạo/sửa immutable setting, cleanup | `roles/artifactregistry.admin` | Chỉ đội quản trị hạ tầng |
| Bật Artifact Registry API | Service Usage permissions phù hợp | Phạm vi project |
| GKE/Cloud Run pull | Runtime identity có Reader | Không nhầm với quyền của máy developer |

Cần Google Cloud CLI có quyền, Docker CLI/daemon hoặc OCI builder thích hợp, kết nối tới `LOCATION-docker.pkg.dev` (nếu VM private, phải có đường egress được phê duyệt), billing/quota phù hợp và một repository chưa bị nhóm khác sử dụng.

Kiểm tra trước bằng lệnh **chỉ đọc**:

~~~bash
gcloud config get-value project
gcloud auth list
gcloud artifacts locations list

gcloud artifacts repositories list \
  --project=LAB_PROJECT_ID \
  --location=asia-southeast1

gcloud services list --enabled --project=LAB_PROJECT_ID
~~~

Nếu Artifact Registry API chưa bật, người quản trị có quyền có thể thực hiện trong **project lab**:

~~~bash
# Lệnh thay đổi project: chỉ dùng khi được phê duyệt
gcloud services enable artifactregistry.googleapis.com \
  --project=LAB_PROJECT_ID
~~~

CI chỉ cần quyền push **không nên có quyền thay immutable setting, xóa repository hoặc cấp thêm IAM**. Trong hệ thống nhiều projects, cấp Reader cho runtime service identity trên project **chứa repository**.

## 8. Tạo immutable repository và xác minh

### 8.1. Google Cloud Console

1. Mở **Artifact Registry → Repositories**, chọn project lab.
2. Chọn **Create Repository**, nhập tên `orders-release-lab`.
3. Chọn format **Docker**, repository mode **Standard**.
4. Chọn location `asia-southeast1` hoặc vùng được phép.
5. Bật **Immutable image tags**.
6. Xem encryption, vulnerability scanning, IAM và cleanup theo yêu cầu.
7. Tạo repository rồi mở lại metadata, kiểm tra cài đặt đã bật.

### 8.2. gcloud tạo repository

~~~bash
# Có tác động: tạo repository thử nghiệm, không dùng trong production
gcloud artifacts repositories create orders-release-lab \
  --repository-format=docker \
  --location=asia-southeast1 \
  --description="Lab immutable image tags" \
  --immutable-tags \
  --project=LAB_PROJECT_ID
~~~

Đọc lại cấu hình:

~~~bash
gcloud artifacts repositories describe orders-release-lab \
  --location=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

Kiểm tra trường **`dockerConfig.immutableTags`** trong metadata hoặc cột Immutable image tags trên Console. Nếu không thấy trong bảng rút gọn, xem output JSON/YAML đầy đủ trước khi kết luận.

**Giới hạn:** `--immutable-tags` không tạo chữ ký image, không tự làm vulnerability scan, không ngăn administrator thay cài đặt và không biến repository thành WORM storage.

### 8.3. Xác thực Docker

~~~bash
# Ghi thiết lập credential helper trên máy thực hành
gcloud auth configure-docker asia-southeast1-docker.pkg.dev
~~~

Lệnh trên cấu hình credential helper **trên máy chạy Docker**, không cấp IAM. Nếu push báo 403, kiểm tra identity đang active, quyền Writer trên đúng repo, API/network và scope của CI. Không chép service account JSON key hoặc access token vào source code để “sửa” lỗi quyền.

## 9. Build, push và ghi nhận digest

### 9.1. Dockerfile nhỏ cho bài lab

Người học tạo một thư mục lab riêng, có file `Dockerfile` sau:

~~~dockerfile
FROM alpine:3.20

ARG BUILD_MESSAGE=first
LABEL lab.build.message="${BUILD_MESSAGE}"

CMD ["sh", "-c", "echo Immutable tag lab; sleep 3600"]
~~~

Dockerfile này minh họa cách làm hai builds có metadata khác nhau, **không phải production image**. Base tag `alpine:3.20` có thể thay đổi theo thời gian; release thật cần xét base digest, dependency scanning, minimal image và SBOM/provenance.

### 9.2. Biến Bash/Cloud Shell

~~~bash
export PROJECT_ID=LAB_PROJECT_ID
export LOCATION=asia-southeast1
export REPO=orders-release-lab
export IMAGE=orders-api

export IMAGE_PATH="${LOCATION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE}"
echo "${IMAGE_PATH}"
~~~

Trên PowerShell, cú pháp biến và cách nối lệnh khác. Các ví dụ sau giả định **Bash**, hãy đổi theo môi trường thật.

### 9.3. Build D1, push `v1.0.0`

~~~bash
# Chạy tại thư mục có Dockerfile lab
docker build \
  --build-arg BUILD_MESSAGE=first \
  -t "${IMAGE_PATH}:v1.0.0" .

docker push "${IMAGE_PATH}:v1.0.0"
~~~

Vì tag `v1.0.0` chưa tồn tại, immutable repository chấp nhận push. Docker có thể hiển thị digest sau khi push; hãy đối chiếu metadata Artifact Registry, không sao chép hash layer bất kỳ.

### 9.4. Đọc digests và tags trên Artifact Registry

~~~bash
# Danh sách image names
gcloud artifacts docker images list \
  "${LOCATION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

# Image versions cùng manifest digests và tags
gcloud artifacts docker images list "${IMAGE_PATH}" \
  --include-tags

# Dành cho quy trình kiểm tra/ghi nhận có cấu trúc
gcloud artifacts docker images list "${IMAGE_PATH}" \
  --include-tags \
  --format=json
~~~

Lưu lại **đầy đủ digest 64 ký tự hex**, không chỉ phần viết tắt hiển thị trong bảng. Một release record nên có:

~~~text
Project/repository/location: LAB_PROJECT_ID / orders-release-lab / asia-southeast1
Image name: orders-api
Tag: v1.0.0
Digest: sha256:<FULL_64_HEX>
Commit: <GIT_COMMIT>
Build run: <CI_RUN_ID>
Builder: <SERVICE_IDENTITY>
Test/scan result: <LINK_OR_ID>
Approval: <CHANGE_REQUEST>
~~~

**Không dùng hash rút ngắn, Docker local image ID hoặc Git commit SHA thay cho registry manifest digest.**

### 9.5. Docker pull và RepoDigests

~~~bash
docker pull "${IMAGE_PATH}:v1.0.0"

docker image inspect "${IMAGE_PATH}:v1.0.0" \
  --format='{{json .RepoDigests}}'
~~~

`RepoDigests` cho biết tham chiếu repo@digest Docker daemon đã biết. Với multi-platform image, index digest và platform-specific manifest digest có thể khác; cần ghi nhận đúng định danh mà nền tảng deploy sử dụng.

## 10. Thử push trùng tag để chứng minh immutability

### 10.1. Build D2 với cùng tag `v1.0.0`

~~~bash
# Build local image với label khác D1
docker build \
  --build-arg BUILD_MESSAGE=second \
  -t "${IMAGE_PATH}:v1.0.0" .

# Dự kiến THẤT BẠI vì tag remote v1.0.0 đã gắn với D1
docker push "${IMAGE_PATH}:v1.0.0"
~~~

**Kỳ vọng:** Registry từ chối vì immutable tags không cho chuyển `v1.0.0` từ D1 sang D2. D1 trên registry không bị ghi đè.

- Image **local** với tag `v1.0.0` có thể đã trỏ D2; không nhầm với **remote**.
- Nếu push được chấp nhận, kiểm tra hai image có thật sự khác digest không và policy có thật sự bật không.
- Không tắt policy chỉ để làm bài thử vượt qua.
- Một push lại **cùng digest** không minh họa việc chuyển tag sang version khác.

### 10.2. Push D2 dưới tag mới

~~~bash
# Đặt tag mới cho image local D2
docker tag "${IMAGE_PATH}:v1.0.0" "${IMAGE_PATH}:v1.0.1"

# Tag v1.0.1 chưa được dùng, nên có thể push D2
docker push "${IMAGE_PATH}:v1.0.1"

# Xác minh hai versions
gcloud artifacts docker images list "${IMAGE_PATH}" --include-tags
~~~

Kỳ vọng:

~~~text
:v1.0.0 -> D1
:v1.0.1 -> D2
~~~

**Bài học:** Mỗi hotfix/rebuild dẫn tới digest mới phải có **tag mới** nếu image nằm trong immutable repository. Hãy sửa pipeline sang unique build IDs thay vì dựa vào aliases như `:latest`/`:prod`.

### 10.3. Các câu hỏi sau bài thử

1. Việc Docker build local D2 có làm thay tag remote không? **Không**.
2. Push D2 với tag chưa dùng có được phép không? **Có** nếu IAM, quota và policy khác cho phép.
3. Image D1 có biến mất khi D2 được push không? **Không tự động**.
4. Nếu muốn triển khai D1, nên dùng gì? **Digest D1** hoặc tag bất biến đã được xác minh.
5. Có nên tắt immutability để sửa lỗi “tag exists” trên production không? **Không**, cần tạo tag mới và kiểm tra workflow phát hành.

## 11. Thêm release tag mới vào digest đã được kiểm chứng

Sau khi D1 vượt integration tests và security gate, cần gắn tag release cho con người. **Không rebuild** cùng source rồi coi image mới là artifact đã kiểm thử.

### 11.1. Thêm tag từ tag hiện có

~~~bash
# Thao tác thay đổi tags trên registry, target tag CHƯA từng tồn tại:
gcloud artifacts docker tags add \
  "${IMAGE_PATH}:v1.0.0" \
  "${IMAGE_PATH}:release-20261119-01"
~~~

Lệnh có dạng `gcloud artifacts docker tags add IMAGE_VERSION TARGET_TAG`, cho phép IMAGE_VERSION sử dụng **tag hoặc full digest**. Với pipeline sản xuất, nên dùng digest nguồn đã vượt release gates:

~~~bash
# Ví dụ cú pháp, phải thay FULL_64_HEX_DIGEST bằng digest thật
gcloud artifacts docker tags add \
  "${IMAGE_PATH}@sha256:FULL_64_HEX_DIGEST" \
  "${IMAGE_PATH}:release-20261119-01"
~~~

Đây là **placeholder**, không thể chạy nguyên văn khi digest chưa hợp lệ. Một tag **chưa tồn tại** có thể được thêm vào D1 trong immutable repository. Nếu `release-20261119-01` đã trỏ D2, việc chuyển sang D1 sẽ bị từ chối.

### 11.2. Xác minh release tags

~~~bash
gcloud artifacts docker images list "${IMAGE_PATH}" --include-tags
gcloud artifacts docker tags list "${IMAGE_PATH}"
~~~

Trong Console, mở Repositories → image → version list và xem cả **Tags** và **Image digest**. Kiểm tra `v1.0.0` và `release-20261119-01` cùng trỏ D1, không chỉ vì tên “release” nghe đúng.

### 11.3. Pull chính xác bằng digest

~~~bash
# Chỉ có thể chạy sau khi thay digest thật lấy từ Artifact Registry
docker pull "${IMAGE_PATH}@sha256:FULL_64_HEX_DIGEST"
~~~

Nếu image tồn tại và IAM/network đúng, Docker yêu cầu manifest/index cụ thể đó. Một deployment ở thời điểm tương lai vẫn cần registry **giữ artifact**; pin digest không bảo đảm image có thể pull mãi mãi.

### 11.4. Đóng băng evidence ngoài tag

Release record nên lưu: full image URI by digest, human tag, Git commit, build ID, test/scan evidence, SBOM, signing/attestation reference, người duyệt, môi trường và timestamp. Đây mới là bản ghi “đã approve gì” thay vì chỉ một tag string.

## 12. Triển khai GKE bằng digest

Kubernetes hỗ trợ image reference trực tiếp theo digest:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
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
          image: asia-southeast1-docker.pkg.dev/PROJECT_ID/orders-release-lab/orders-api@sha256:FULL_64_HEX_DIGEST
          ports:
            - containerPort: 8080
~~~

Manifest trên chỉ để học; digest placeholder **không thể triển khai**. Khi dùng production cần resources requests/limits, probes, securityContext, serviceAccount, secret delivery và network policies theo workload.

### 12.1. Rủi ro khi Kubernetes dùng tag mutable

Giả sử một Deployment có `image: orders-api:v1.0.0` trong mutable repository:

1. Pod A được tạo 09:00 và pull digest D1.
2. Pipeline vô tình push digest D2 dưới cùng tag lúc 09:10.
3. Pod B được scheduler tạo sau scale-out lúc 09:15, có thể pull D2.
4. Hai Pods thuộc **cùng Deployment, cùng image string** nhưng chạy artifacts khác nhau.

Với `orders-api@sha256:D1`, Pod mới sẽ yêu cầu D1. Đây là lý do Google Cloud khuyến nghị dùng **image digests** cho deployment ổn định và tái lập.

### 12.2. `imagePullPolicy` không thay thế digest

Kubernetes có các giá trị như `Always` và `IfNotPresent`:

- Với tag mutable, `Always` có thể khiến node resolve/pull tag khi container được tạo; `IfNotPresent` có thể dùng image đã cache.
- Với reference by digest, cả hai vẫn trỏ tới **cùng artifact identity**, nếu object còn tồn tại.
- Pod đang chạy không tự đổi image khi tag registry đổi. Cần rollout/restart/replace được quản lý.
- Node có image cache không chứng minh node **mới** có thể pull nếu image bị xóa khỏi repository.

**Không dùng `latest` và trông chờ `Always` giúp mọi replica luôn chạy cùng phiên bản.** Cần quản lý rollout rõ ràng.

### 12.3. Xem image digest của Pods

~~~bash
# Chỉ đọc, chọn đúng cluster context và namespace
kubectl get deployment orders-api -n NAMESPACE -o yaml
kubectl get pods -n NAMESPACE -l app=orders-api -o wide

kubectl get pods -n NAMESPACE -l app=orders-api \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .status.containerStatuses[*]}{.name}{": "}{.imageID}{"\n"}{end}{end}'
~~~

Khi xem `imageID`, container runtime có thể hiển thị **platform-specific child digest** thay vì image index digest. Phải xem OS/architecture, manifest list và digest gốc trước khi suy rằng image bị thay thế.

### 12.4. Rollout bằng digest mới

~~~bash
# Có tác động thay đổi Deployment; chỉ dùng khi đã được phê duyệt
kubectl set image deployment/orders-api \
  orders-api=LOCATION-docker.pkg.dev/PROJECT/REPO/orders-api@sha256:FULL_NEW_DIGEST \
  -n NAMESPACE

kubectl rollout status deployment/orders-api -n NAMESPACE
~~~

Trong mô hình GitOps, thay manifest/Helm values trong Git bằng **digest đã kiểm duyệt**, để controller áp dụng có audit. Rollback cũng chọn digest release cũ, không move tag `:production`.

### 12.5. Runtime identity và quyền pull

Node/identity đang kéo image phải có quyền đọc Artifact Registry repository, thường là `roles/artifactregistry.reader` trên repository đích. Với **cross-project pull**, quyền trên project triển khai GKE không tự tạo quyền trên project lưu image; kiểm tra service account/node identity và grant đúng scope. Nếu thiếu quyền, có thể gặp `ErrImagePull` hoặc `ImagePullBackOff` dù digest hoàn toàn hợp lệ.

## 13. Cloud Run: image tag được resolve lúc deploy revision

Cloud Run cho phép deploy bằng tag hoặc exact digest. Một khác biệt quan trọng: khi deploy bằng **tag**, Cloud Run **resolve tag sang digest tại thời điểm deploy**, và **revision được tạo sẽ sử dụng digest đã resolve**. Tag thay đổi sau đó **không tự biến revision đang chạy thành image khác**.

~~~mermaid
flowchart LR
  T["Deploy orders-api:v1.0.0"] --> RES["Cloud Run resolve tag"]
  RES --> D1["Revision R1: digest D1"]
  NEXT["Deploy orders-api@D2"] --> D2["Revision R2: digest D2"]
  D1 --> TRAF["Traffic routing giữa revisions"]
  D2 --> TRAF
~~~

### 13.1. Deploy minh họa bằng digest

~~~bash
# TẠO/CẬP NHẬT Cloud Run service; chỉ thực hiện trong project lab
gcloud run deploy orders-api \
  --image=LOCATION-docker.pkg.dev/PROJECT_ID/REPOSITORY/orders-api@sha256:FULL_64_HEX_DIGEST \
  --region=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --no-allow-unauthenticated
~~~

**Quan trọng:** Dockerfile Alpine ở lab chỉ chạy `sleep`, không phải web server tuân thủ **Cloud Run container runtime contract**. Không dùng image lab này để kỳ vọng một Cloud Run service phục vụ HTTP thành công; hãy thay bằng image ứng dụng thật có listener đúng port/host và readiness.

### 13.2. Vì sao vẫn nên pin digest khi Cloud Run đã khóa revision?

- Lặp lệnh deploy theo **mutable tag** ở thời điểm khác có thể tạo revision mới với digest khác.
- Release evidence cần ghi rõ artifact đã test và artifact đã deploy là **một**.
- So sánh rollback/incident dễ hơn khi release record dùng full digest.
- Các công cụ CD, promotion hay deploy scripts có thể không cùng quy tắc resolution với Cloud Run.

### 13.3. Rollback đúng ở tầng Cloud Run

Rollback thường chuyển traffic về một revision đã biết hoặc deploy lại digest đã phê duyệt, **không** cần sửa tag trong Artifact Registry.

Cần kiểm tra schema database, secrets, environment, IAM và dependencies của revision cũ. **Revision bất biến không đồng nghĩa mọi hệ thống bên ngoài revision đều bất biến.** Image digest của revision cũng cần còn trong registry cho những hoạt động deploy/pull liên quan.

## 14. Một pipeline build → kiểm chứng → deploy có kiểm soát

### 14.1. Cloud Build với unique build tag

Ví dụ file `cloudbuild.yaml` của một dự án thực hành **riêng**:

~~~yaml
steps:
  - name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - asia-southeast1-docker.pkg.dev/$PROJECT_ID/orders-release-lab/orders-api:build-$BUILD_ID
      - .
images:
  - asia-southeast1-docker.pkg.dev/$PROJECT_ID/orders-release-lab/orders-api:build-$BUILD_ID
~~~

Cloud Build cung cấp những substitutions như `$PROJECT_ID` và `$BUILD_ID` theo ngữ cảnh build. Tham chiếu dùng **build ID riêng** thay vì đè tag `:latest`. Trong build thật cần bảo đảm service account có quyền push **trên repository**, có quyền truy cập base image, dependencies và đạt security checks.

**Không deploy tự động chỉ vì bước `docker build` thành công.** Sau khi image được push, pipeline cần lấy **full digest từ Artifact Registry**, xác minh đúng tag/build/version, lưu provenance, chạy tests/scans, kiểm tra phê duyệt rồi mới cập nhật deployment bằng digest. Bước đó được mô tả như **quy trình**, vì cách parse digest từ Cloud Build output/JSON phụ thuộc CI và chế độ artifact.

### 14.2. Phân tách pipeline build và pipeline release

| Giai đoạn | Đầu vào | Đầu ra/kiểm tra |
| --- | --- | --- |
| Checkout source | Commit SHA, branch policy | Source được review |
| Build | Source + pinned dependencies | OCI manifest/index digest D |
| Push | Unique build tag | Version D trong Artifact Registry |
| Verify | D + build metadata | Scan/SBOM/provenance/attestations |
| Approve | Evidence và release request | Cho phép D tới môi trường |
| Promote | D đã phê duyệt | Tag release mới hoặc copy artifact có kiểm tra digest |
| Deploy | **Repo/image@D** | GKE Deployment/Cloud Run revision |
| Observe | Request/error/SLO | Go/no-go, rollback |
| Retain | Release metadata | Keep policy + đảm bảo D còn pull được |

Nếu promotion qua một repository khác làm digest thay đổi, cần **scan/xác minh lại digest đích**, gắn evidence phù hợp và bảo đảm release record không chỉ giữ digest nguồn.

### 14.3. Tránh TOCTOU khi resolve tag

*Time-of-check/time-of-use* là lỗi khi “kiểm tra tag hôm trước, deploy tag hôm sau” nhưng mutable tag đã đổi.

~~~text
Sai:
  Test :staging -> D1
  Người khác repush :staging -> D2
  Deploy :staging -> D2

Tốt hơn:
  Test digest D1
  Approve D1
  Deploy IMAGE@sha256:D1
~~~

Immutable tags giảm khả năng tag bị chuyển khi policy đang bật, nhưng **digest pinning** tạo bằng chứng rõ ràng hơn ở điểm triển khai và không phụ thuộc vào giả định trạng thái repository setting về sau.

### 14.4. Hotfix và rollback thực tế

Giả sử production đang chạy D1/`v1.5.0`, phát hiện lỗi:

1. Tạo hotfix từ source, chạy CI lần mới → D2/`build-2842`.
2. Scan/test D2, gắn tag `v1.5.1` **mới**, không ghi đè `v1.5.0`.
3. Deploy bằng D2 theo rollout strategy.
4. Nếu lỗi, chuyển về **D1** bằng GitOps/Cloud Run traffic hoặc deployment approval.
5. Kiểm tra state/schema backward compatibility và người dùng thực.

**Rollback ≠ retag `v1.5.0` sang D2 hoặc xóa D2 để ép runtime chạy D1.** Artifact và release history phải vẫn tra được.

## 15. Kiểm soát IAM, service identity và truy cập riêng tư

### 15.1. Đúng danh tính cho đúng thao tác

Trong cùng một hệ thống có thể có:

- **Developer:** đọc/tra cứu images, hoặc push vào dev repository.
- **CI build service account:** Writer tới repository build/release tùy quy trình.
- **Release approver/service account:** đủ quyền gắn **tag mới** hoặc promote artifact, không mặc nhiên quản trị toàn project.
- **GKE node/Cloud Run service agent/runtime identity:** quyền pull image phù hợp.
- **Repository administrator:** đổi immutable setting, IAM và cleanup policy theo phê duyệt.
- **Security reviewer:** xem digests, scan reports, audit logs mà không cần quyền delete.

Một “Permission denied” ở `docker push` thường liên quan **Writer**, còn `ImagePullBackOff` liên quan **Reader/runtime identity**, network hay tên/digest sai. Đừng giải quyết hai lỗi này bằng một quyền Owner rộng.

### 15.2. Môi trường Shared VPC, nhiều project

Ví dụ:

~~~text
Project A: shared-artifacts
  └── Artifact Registry: orders-release-lab (immutable)

Project B: staging-cluster
  └── GKE cluster: pulls digest D

Project C: production-service
  └── Cloud Run service: deploys digest D
~~~

Quyền Reader cần được cấp trên repository ở **Project A** cho các service identities thực sự pull. Chỉ cấp Reader trong Project B/C **không nhất thiết đủ**. Đồng thời xác nhận kết nối network đến hostname registry và cơ chế Private Google Access/Private Service Connect/NAT nếu workloads nằm trong subnet private.

### 15.3. Không đưa credentials vào image

Không thêm JSON key, access token hay Docker credentials vào image layer hoặc Dockerfile `ARG`/`ENV` theo cách có thể nằm trong history. Khi build cần secrets, dùng cơ chế CI/build secrets thích hợp và kiểm tra layer/provenance.

**Immutable tag không xóa được bí mật đã bị đóng gói vào image.** Nếu lỡ phát hành image chứa secret, phải thu hồi/rotate credentials, điều tra truy cập, dùng quy trình incident response và xử lý artifact theo phê duyệt; không chờ thay tag mới tự xử lý lộ lọt.

### 15.4. IAM và điều kiện tin cậy khi đổi chính sách

Việc tắt immutable tag là **thao tác governance quan trọng**, vì có thể mở đường cho tag movement/delete tagged artifacts. Nên:

- Chỉ người/quy trình được uỷ quyền có `roles/artifactregistry.admin`.
- Yêu cầu change approval, audit và lý do nghiệp vụ rõ ràng.
- Ưu tiên **tạo tag mới** thay vì tắt immutable để sửa release.
- Thiết lập cảnh báo/đánh giá Audit Logs khi repository policy thay đổi.
- Định kỳ kiểm tra IAM drift và service account keys.

## 16. Cleanup policies: vì sao immutable tags ảnh hưởng chi phí?

**Artifact Registry cleanup policies** có thể tự động giữ hoặc xóa artifact versions dựa vào **tuổi, trạng thái tag, prefix và số versions cần giữ**. Tuy nhiên, khi repository **bật immutable tags**, **tagged image versions không thể bị xóa** bằng cleanup policies. Đó là sự đánh đổi quan trọng giữa bảo vệ release history và giảm chi phí lưu trữ.

### 16.1. Untagged version và tagged version khác nhau

~~~text
Mutable repository:
  :staging -> D1
  Push D2 với :staging
  :staging -> D2
  D1 có thể thành untagged, có thể bị cleanup khi đủ điều kiện

Immutable repository:
  :v1.0.0 -> D1
  :v1.0.1 -> D2
  Không thể gỡ/chuyển tag.
  Cleanup rule Delete tagged KHÔNG xóa D1/D2.

Version không có tag trong immutable repo:
  Có thể bị cleanup khi thỏa policy.
~~~

Không phải mọi artifact đều được bảo vệ chỉ vì repository bật immutable tags; **untagged versions vẫn có thể bị xóa**. Ngược lại, tagged versions có thể tích lũy nhiều năm nếu đội phát triển tạo một release tag cho mọi CI run.

### 16.2. Thuộc tính cleanup policy

| Thuộc tính | Ví dụ | Lưu ý |
| --- | --- | --- |
| Tag state | `tagged`, `untagged`, `any` | Immutable repo ngăn xóa tagged versions |
| Tag prefix | `release`, `rc`, `build` | Chỉ có ý nghĩa khi lọc các tag phù hợp |
| Package prefix | `orders-` | Khác full registry URI |
| Version prefix | `v1` | Cần phân biệt version name với tag |
| Tuổi version | `olderThan: 30d` | Không phải tuổi source commit |
| Keep most recent | `keepCount: 5` | Giữ những versions gần nhất theo phạm vi |
| Dry run | Thử chính sách | Chạy background, không đưa ngay danh sách đầy đủ |

Cleanup policies chủ yếu dành cho **standard repositories** được hỗ trợ, không mặc định áp dụng tương tự cho virtual repository hay upstream cache của remote repositories.

### 16.3. Ví dụ JSON cho repository lab

Giữ **ít nhất 5 phiên bản mới nhất** của mỗi package và xóa **untagged** versions cũ hơn 30 ngày nếu không có keep rule:

~~~json
[
  {
    "name": "delete-untagged-after-30d",
    "action": { "type": "Delete" },
    "condition": {
      "tagState": "untagged",
      "olderThan": "30d"
    }
  },
  {
    "name": "keep-latest-five",
    "action": { "type": "Keep" },
    "mostRecentVersions": {
      "keepCount": 5
    }
  }
]
~~~

Đây là cấu hình minh họa cho file `cleanup-lab.json` trên **máy lab**. Keep rule được xét để bảo vệ những versions phù hợp; immutable tags vẫn chặn việc xóa tagged version.

### 16.4. Dry run trước khi bật xóa thật

~~~bash
# Cập nhật cleanup policy settings; chỉ DRY RUN, chưa xóa artifacts
gcloud artifacts repositories set-cleanup-policies orders-release-lab \
  --location=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --policy=cleanup-lab.json \
  --dry-run
~~~

Dry run vẫn cập nhật **cấu hình repository**, dù không xóa artifacts. Artifact Registry chạy đánh giá theo background job định kỳ, thường cần khoảng **một ngày** để xem kết quả. Muốn xem dry-run audit events có thể cần bật **Artifact Registry Data Access / Data Write logs** và quyền đọc logs tương ứng.

Chỉ khi đã xem kết quả và có phê duyệt mới áp dụng:

~~~bash
# THAO TÁC CÓ THỂ XÓA ARTIFACTS: chỉ sau review/phê duyệt
gcloud artifacts repositories set-cleanup-policies orders-release-lab \
  --location=asia-southeast1 \
  --project=LAB_PROJECT_ID \
  --policy=cleanup-lab.json \
  --no-dry-run
~~~

**Xóa image không thể hoàn tác bằng cách đổi cleanup policy.** Đừng đưa `--no-dry-run` vào pipeline production trước khi người sở hữu artifacts xác nhận retention và rollback window.

### 16.5. Tag delete và image delete bị chặn

Ví dụ immutable repo có `v1.0.0`:

~~~bash
# Cú pháp minh họa; DỰ KIẾN lỗi do immutable policy
gcloud artifacts docker tags delete "${IMAGE_PATH}:v1.0.0"

# DỰ KIẾN bị từ chối: image còn tag trong immutable repo
gcloud artifacts docker images delete \
  "${IMAGE_PATH}@sha256:FULL_64_HEX_DIGEST" \
  --delete-tags
~~~

Cờ `--delete-tags` **không phải cách vượt immutable policy**. Khi phải đáp ứng retention hữu hạn, cần thiết kế chính sách repo layout và quyền quản trị phù hợp trước khi tạo hàng trăm nghìn release tags.

### 16.6. Tách repository để quản lý chi phí

| Repository | Cách dùng | Retention |
| --- | --- | --- |
| `orders-dev` | Builds thử, mutable tags khi cần | Xóa untagged/old dev versions theo policy |
| `orders-candidate` | RCs có tags độc nhất | Giữ theo giai đoạn kiểm thử |
| `orders-release` | Approved releases, immutable | Giữ tagged images theo yêu cầu audit/rollback |
| `orders-archive` | Artifacts cần bảo lưu dài hạn | Chính sách DR/backup/provenance riêng |

Một policy “Delete tagged releases sau 90 ngày” sẽ **không thực hiện được khi immutable tags vẫn bật**. Đây là giới hạn phải được quyết định từ bước thiết kế, không phải sửa trong lúc chi phí tăng.

## 17. Quan sát và tổng chi phí

### 17.1. Các tín hiệu nên theo dõi

| Tín hiệu | Mục tiêu |
| --- | --- |
| Số versions theo image | Phát hiện release repository tăng ngoài dự kiến |
| Tagged/untagged counts | Biết cleanup có khả thi |
| Storage bytes và chi phí | Theo location/repository và thời gian |
| Docker push failures | Đánh giá tag collisions và IAM |
| Pull failures/404 | Phát hiện thiếu Reader hoặc version đã mất |
| Repository setting changes | Cảnh báo immutability bị tắt hoặc IAM rộng |
| Scan/provenance results | Phục vụ security gates |
| CI run → digest mapping | Phân biệt builds từ cùng commit |
| GKE imageIDs / Cloud Run revisions | So runtime artifact với release record |
| Cleanup dry run logs | Kiểm tra các versions có nguy cơ bị xóa |

### 17.2. Những khoản chi phí có thể phát sinh

Artifact Registry có thể thu phí storage của manifests/layers/packages, network transfer, vulnerability scanning và một số dịch vụ liên quan. CI/Cloud Build, audit logs và monitoring cũng có chi phí riêng. Khi image version bị xóa, **unreferenced layers không nhất thiết biến mất ngay**; registry xử lý dọn dữ liệu theo chu kỳ.

Đừng đánh đồng “500 tags” với “500 copies đầy đủ của một filesystem”: layers có thể được tái sử dụng. Tuy nhiên, **500 tagged versions bất biến vẫn có thể tăng storage và khiến cleanup không thể xóa chúng**, nhất là khi mỗi build tạo layer ứng dụng mới. Hãy quan sát **billed bytes** và sử dụng Cloud Billing Reports/Budgets thay vì ước lượng chỉ qua tên tag.

### 17.3. Vì sao cần lưu release evidence?

Sáu tháng sau sự cố, nhóm SRE cần biết: digest production, digest trước đó, CI run, source commit, build config, identity push, scanning/attestations, người phê duyệt, deployment events và đường dẫn artifact.

Nếu chỉ giữ digest string nhưng **image bytes đã bị xóa khỏi registry**, không thể pull lại chỉ từ hash. Retention phải bảo đảm image tồn tại trong cửa sổ rollback, forensic và yêu cầu tuân thủ.

## 18. Bảng chẩn đoán các sự cố thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra / xử lý |
| --- | --- | --- |
| Push báo `tag immutability enabled` | Tag cũ đã trỏ sang version khác | Dùng unique tag mới, đừng tắt policy |
| Push báo `permission denied` / 403 | Không có Writer hoặc repo/project sai | Kiểm tra identity, IAM scope, API/network |
| Docker báo `unauthorized` | Credential helper/token không hợp lệ | Chạy cấu hình đúng registry host; tránh khóa dài hạn |
| Push thành công nhưng tag không thấy | Nhầm location/repository/image name | Kiểm tra full URI và `--include-tags` |
| Pull by digest báo `manifest unknown` | Digest sai, artifact đã xóa hoặc sai path | Kiểm tra full hash và sự tồn tại version |
| Pull `:latest` nhận bản cũ | Latest không tự cập nhật | Pin digest và version mới |
| Không thể gỡ tag | Immutable policy chặn | Thiết kế lại retention, không ép xóa |
| `--delete-tags` vẫn lỗi | Tagged image không thể xóa khi immutable bật | Không thể bypass bằng flag |
| Cleanup không xóa tagged images | Immutable protection hoặc keep rule | Đọc dry-run logs và policy |
| GKE `ImagePullBackOff` | Reader, path, network, architecture | Xem Pod events, runtime service identity, registry |
| Pods trong cùng Deployment khác digest | Tag mutable, lịch pull/cache khác | Pin digest, rollout có kiểm soát |
| Cloud Run revision không đổi sau khi retag | Revision khóa digest khi deploy | Deploy revision mới hoặc traffic routing |
| Image chạy sai kiến trúc | Multiarch index thiếu child manifest phù hợp | Kiểm tra platform/architecture |
| Digest khác local image ID | Hash của manifest khác hash config | So đúng loại digest |
| Repo immutable nhưng artifact không đáng tin | Immutable tag không phải scan/provenance | Áp dụng verification gates |
| Cross-project pull 403 | Reader chưa cấp trên repo ở project chứa artifact | Cấp quyền đúng repo cho service identity |
| Không rollback được | Digest cũ bị xóa hoặc schema không tương thích | Retention, DR và rollback plan |

### 18.1. Quy trình chẩn đoán theo tầng

~~~mermaid
flowchart TD
  S["Push/Pull/Deploy lỗi"] --> URI["Xác minh full project/repo/image/tag/digest"]
  URI --> K{"Lỗi push hay pull?"}
  K -- "Push" --> P{"Tag đã tồn tại trong immutable repo?"}
  P -- "Có" --> TAG["Dùng tag mới; không move tag cũ"]
  P -- "Không" --> IAM["Kiểm tra Writer/API/credentials/quota"]
  K -- "Pull" --> V{"Version còn tồn tại?"}
  V -- "Không" --> RET["Kiểm tra cleanup/retention hoặc sai URI"]
  V -- "Có" --> READER["Kiểm tra Reader, egress, runtime architecture"]
  TAG --> TEST["Xác minh digests, release evidence và thử lại"]
  IAM --> TEST
  RET --> TEST
  READER --> TEST
~~~

**Không tự động mở IAM công khai, xóa mọi tags hoặc tắt immutable** chỉ để CI trở lại màu xanh.

## 19. Case study: phát hành API Java qua GKE và Cloud Run

**Bối cảnh:** Công ty vận hành API đặt hàng Java, staging chạy trên GKE, production trên Cloud Run. Image được build từ Git qua CI và lưu Artifact Registry. Đội bảo mật yêu cầu khả năng biết **chính xác binary đã qua review** và có thể rollback.

Một quy trình tham khảo:

~~~text
Source commit: a1b2c3d
CI run: build-2841
Build repository:
  orders-api:build-2841-a1b2c3d -> digest D1

CI:
  unit/integration/security/contract tests -> approve D1

Promotion sang release repository (immutable):
  orders-api:v1.6.0 -> digest D1'
  (phải xác minh D1' ở registry đích; có thể khác D1 nếu manifest bị đổi)

Staging GKE:
  image = release-repo/orders-api@D1'

Production Cloud Run:
  revision from release-repo/orders-api@D1'

Release record:
  Git SHA + build ID + destination digest + evidence + approval
~~~

### 19.1. Vì sao không rebuild khi promote?

Nếu production rebuild từ cùng commit nhưng base image đã thay đổi, kết quả có thể là D2 dù staging kiểm thử D1. **Promote artifact đã được xác minh** giúp kiểm soát artifact identity. Nếu công cụ copy sang repo khác thay đổi manifest/index digest, cần giải thích và xác minh digest đích cùng evidence, không dùng tag để che khuất khác biệt.

### 19.2. Hotfix và rollback

Khi D1 có lỗi, tạo hotfix build mới → D2, kiểm tra scan/test, gắn **tag release mới**, deploy D2 bằng digest. Nếu lỗi, chuyển cấu hình/traffic về D1 theo change approval. Không retag `v1.6.0` sang D2 và không xóa D2 để “ép” runtime dùng D1.

Rollback còn phụ thuộc dữ liệu, schema migration, secrets, IAM và external dependencies; không phải chỉ đổi một image string.

## 20. Bài tập ôn tập và đáp án định hướng

1. **Tag có phải digest không?** Không. Tag là tham chiếu có thể mutable; digest xác định manifest/index.
2. **Hai tags cùng digest là hai image binaries khác nhau?** Không. Có thể chỉ là hai names cho một version.
3. **Hai builds cùng Git commit có digest khác nhau được không?** Có, do build inputs/metadata thay đổi.
4. **Bật immutable rồi có thể push D2 với tag D1 đã dùng không?** Không khi digest khác.
5. **Thêm tag chưa dùng vào D1 được không?** Có trong standard repository khi có quyền.
6. **`latest` có tự trỏ bản mới nhất không?** Không.
7. **Immutable có ngăn người có quyền Admin tắt policy không?** Không. Cần IAM/audit/change control.
8. **Digest pinning tự bảo đảm không có CVE không?** Không. Cần scanning/provenance.
9. **GKE Pods cùng tag mutable có thể chạy khác digest không?** Có.
10. **Cloud Run revision đang chạy tự đổi khi tag mutable thay đổi không?** Không; revision resolve digest lúc deploy.
11. **Một multi-platform index digest khác child digest có là dấu hiệu bị tấn công?** Không mặc nhiên; đó là hash của các đối tượng khác nhau.
12. **Cleanup Delete tagged olderThan=30d có xóa tagged image trong immutable repo không?** Không.
13. **Bị `ImagePullBackOff` thì có nên tắt immutable không?** Không; kiểm tra IAM/URI/network/digest/platform.
14. **Release record chỉ có digest có khôi phục được khi image đã bị xóa không?** Không; phải bảo lưu artifact bytes.
15. **Hotfix D2 thay thế D1 bằng cách push lại `v1.0.0` hợp lệ?** Không theo workflow immutable; dùng tag mới và deploy D2 theo digest.

### Bài thực hành tự đánh giá

Điền bảng dưới đây sau lab:

| Câu hỏi | Kết quả cần ghi |
| --- | --- |
| Repository có immutable bật? | Trường `dockerConfig.immutableTags` hoặc Console |
| `v1.0.0` trỏ digest nào? | Full digest D1 |
| Push D2 với `v1.0.0` thành công không? | Không nếu D2 khác D1 |
| Push D2 với `v1.0.1`? | Thành công khi quyền/config hợp lệ |
| Release tag mới trỏ digest nào? | Cùng D1 |
| Pull by digest có thành công? | Có nếu artifact/identity/network hợp lệ |
| D1/D2 có khác ở manifest hash? | Kiểm tra từ registry |
| Có thể cleanup tagged versions khi immutable? | Không |
| Runtime GKE/Cloud Run sẽ dùng gì? | Digest đúng release đã phê duyệt |

## 21. Checklist trước khi triển khai production

- [ ] Đã xác nhận project, location, repository mode và format đúng.
- [ ] Image tag policy được kiểm tra trên repository release.
- [ ] CI dùng unique tags, không reuse `latest`, `staging` hoặc released versions.
- [ ] Release record lưu full manifest/index digest thay vì commit SHA hoặc short digest.
- [ ] Multi-platform images được kiểm tra platform/child manifests khi cần.
- [ ] Test/scan/provenance/approval gắn với đúng digest.
- [ ] Promotion không rebuild artifact đã test; xác minh digest ở registry đích.
- [ ] GKE sử dụng `IMAGE@sha256:FULL_DIGEST` trong manifest/GitOps.
- [ ] Cloud Run release record gắn với revision và resolved digest.
- [ ] Runtime identity có Reader trên đúng repo, kể cả cross-project.
- [ ] CI Writer không có quyền admin/delete không cần thiết.
- [ ] Có audit khi repository immutable setting hoặc IAM thay đổi.
- [ ] Cleanup policies thử dry run, đã tính tag immutability và keep rules.
- [ ] Release retention đáp ứng thời gian rollback/incident/DR.
- [ ] Đã kiểm tra chi phí storage, egress, scanning, CI và logs.
- [ ] Có runbook xử lý tag collision, 403, `ImagePullBackOff`, manifest unknown.
- [ ] Không dùng cách tắt immutable để xử lý nhanh một release lỗi.

## 22. Dọn tài nguyên lab và giới hạn của việc xóa

Nếu đã tạo **một repository riêng** `orders-release-lab` cho bài này, hãy đọc lại contents và xác nhận **không có GKE/Cloud Run service nào dùng image của repository**. Tagged versions trong immutable repository không thể xóa riêng lẻ khi policy còn bật.

~~~bash
# Chỉ đọc trước khi quyết định cleanup
gcloud artifacts repositories describe orders-release-lab \
  --location=asia-southeast1 --project=LAB_PROJECT_ID

gcloud artifacts docker images list \
  asia-southeast1-docker.pkg.dev/LAB_PROJECT_ID/orders-release-lab/orders-api \
  --include-tags
~~~

Nếu **toàn bộ repository** là dữ liệu lab của chính bạn, đã hết thời gian lưu và được cho phép dọn, người có quyền quản trị có thể xóa repository. Đây là **thao tác phá hủy khác** với xóa một tagged version; không dùng nó để vượt retention production.

~~~bash
# PHÁ HỦY toàn bộ repository lab, chỉ khi đã kiểm tra ownership
gcloud artifacts repositories delete orders-release-lab \
  --location=asia-southeast1 \
  --project=LAB_PROJECT_ID
~~~

Một image bị xóa có thể khiến lần pull/scale-out/redeploy/rollback về sau thất bại. Không mặc định `kubectl rollout undo` hoặc `git revert` sẽ phục hồi bytes khi artifact đã không còn.

## 23. Tài liệu Google Cloud chính thức

Cú pháp CLI, khả năng hỗ trợ và mô hình giá có thể thay đổi. Khi triển khai thật, đối chiếu các tài liệu:

- [Artifact Registry: Container concepts](https://docs.cloud.google.com/artifact-registry/docs/container-concepts) — versions, manifests, layers, tags.
- [Repository and image names](https://docs.cloud.google.com/artifact-registry/docs/docker/names) — định dạng tham chiếu bằng tag/digest.
- [Create standard repositories](https://docs.cloud.google.com/artifact-registry/docs/repositories/create-repos) — Docker repository, `--immutable-tags`.
- [Update repository settings](https://docs.cloud.google.com/artifact-registry/docs/repositories/update-repo-settings) — bật/tắt immutable policy.
- [Manage images](https://docs.cloud.google.com/artifact-registry/docs/docker/manage-images) — list, tag, untag, delete.
- [Push and pull images](https://docs.cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling) — build/push/pull và auth.
- [Artifact Registry access control](https://docs.cloud.google.com/artifact-registry/docs/access-control) — Reader/Writer/Admin roles.
- [Configure cleanup policies](https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy) — Delete/Keep/dry run và immutable.
- [Troubleshoot container image issues](https://docs.cloud.google.com/artifact-registry/docs/docker/troubleshoot) — errors, permissions, pull issues.
- [About container image digests in GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/about-container-images) — lợi ích pin digest.
- [Deploy container images to Cloud Run](https://docs.cloud.google.com/run/docs/deploying) — revision resolve tag sang digest.
- [Artifact Analysis](https://docs.cloud.google.com/artifact-analysis/docs/overview) — vulnerabilities/metadata.
- [Binary Authorization](https://docs.cloud.google.com/binary-authorization/docs/overview) — deploy admission.
- [Cloud Build: build container images](https://docs.cloud.google.com/build/docs/building/build-containers) — CI/build/push.
- [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing) — storage và data transfer.

**Điểm cần ghi nhớ:** **Tag** là tên tham chiếu, **digest** là danh tính manifest/index, còn **immutable tags** là chính sách repository ngăn chuyển tag và xóa tagged image khi policy còn hiệu lực. Phát hành đáng tin nên **build một lần, kiểm chứng theo digest, gắn unique release tag rồi deploy bằng digest**; đồng thời kiểm soát IAM, provenance, scanning, cleanup, chi phí và khả năng rollback.
