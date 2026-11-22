# Đẩy, kéo và phân quyền truy cập container images trong Artifact Registry

Một nhóm phát triển đóng gói API đơn hàng thành **Docker container image**, dùng **Cloud Run** để phục vụ yêu cầu HTTP, **GKE** cho các worker chạy nhiều bản sao và **Compute Engine** để chạy tác vụ quản trị. Nếu mỗi môi trường tự build lại image từ mã nguồn, rất khó khẳng định chúng đang chạy cùng một phiên bản. Nếu cấp quyền registry quá rộng, một tài khoản bị lộ có thể ghi đè hoặc xóa image quan trọng. Nếu cấu hình pull không đúng, deployment có thể dừng ở lỗi `ImagePullBackOff`, `PERMISSION_DENIED` hoặc không tìm thấy image.

**Artifact Registry** là dịch vụ quản lý kho artifact của Google Cloud. Với container, nó cung cấp **Docker repository** để lưu, phân phối và quản trị image theo **tag** hoặc **digest**, kết hợp với **IAM** để quyết định ai được đọc, đẩy, quản trị hay xóa artifact. Một quy trình chuẩn là **build một image → push vào repository → kiểm chứng digest → triển khai đúng artifact đó** vào GKE, Cloud Run hoặc nơi chạy container khác.

Bài học thuộc chương **Container và Artifact Registry**, trong mô-đun **CLOUD_PROVIDERS_GCP**. Nội dung kết nối cách quản lý project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và dữ liệu với quy trình phát hành có thể tái lập, bảo vệ artifact, kiểm soát độ tin cậy và chi phí. Phạm vi chính là **đẩy, kéo và phân quyền truy cập container images**, không phải hướng dẫn toàn bộ Kubernetes hay Docker từ đầu.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **image, repository, tag và digest**; đọc đúng tên image trên Artifact Registry.
2. Tạo và kiểm tra một **standard Docker repository** tại location được chọn.
3. Xác thực Docker bằng **gcloud credential helper** hoặc **access token ngắn hạn**, rồi build, tag, push và pull image.
4. Gán **IAM role tối thiểu** cho người phát triển, CI/CD, GKE nodes và các danh tính liên quan khi deploy Cloud Run.
5. Phân biệt **quyền push/pull artifact** với **quyền chạy, cập nhật và sử dụng runtime service account**.
6. Ưu tiên triển khai theo **image digest**, xây kiểm soát phát hành, provenance, vulnerability scanning và rollback.
7. Khoanh vùng lỗi mạng, xác thực, phân quyền, repository, tag, digest và nền tảng runtime.

## 2. Những thành phần cốt lõi

### 2.1. Image là gì?

**Container image** là tập artifact đóng gói filesystem layers, metadata, thông tin khởi chạy và các cấu phần cần thiết để chạy container. Nó thường được xây từ `Dockerfile` hoặc công cụ build tương đương.

~~~text
Mã nguồn + Dockerfile
       |
       v
    docker build
       |
       v
Container image (layers + manifest)
       |
       v
Artifact Registry Docker repository
       |
       +--> Cloud Run
       +--> GKE
       +--> Compute Engine + container runtime
~~~

**Repository** chứa nhiều images/versions trong một địa điểm và định dạng được quản lý. **Tag** là tên tham chiếu thuận tiện, ví dụ `v1.3.0`, `staging` hoặc `latest`. **Digest** là định danh nội dung của manifest, thường ở dạng `sha256:<hex>`.

Một tag có thể được cập nhật để trỏ đến digest khác nếu repository cho phép; digest gắn với nội dung manifest cụ thể. Vì vậy, với production, **pin bằng digest** giúp xác định artifact chính xác hơn chỉ dựa vào tag.

### 2.2. Cấu trúc URI Artifact Registry

Docker image trong Artifact Registry thường có dạng:

~~~text
LOCATION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE:TAG
LOCATION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE@sha256:DIGEST
~~~

Ví dụ:

~~~text
asia-southeast1-docker.pkg.dev/retail-lab/retail-containers/orders-api:v1.0.0
~~~

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `LOCATION` | `asia-southeast1` | Location của repository và hostname Docker Registry tương ứng. |
| `PROJECT_ID` | `retail-lab` | Project sở hữu Artifact Registry repository. |
| `REPOSITORY` | `retail-containers` | Docker repository được quản lý trong project/location. |
| `IMAGE` | `orders-api` | Tên image hoặc đường dẫn image bên trong repository. |
| `TAG` | `v1.0.0` | Nhãn tham chiếu đến phiên bản nội dung. |
| `sha256:DIGEST` | Chuỗi digest thật sau khi push | Tham chiếu bất biến đến manifest tương ứng. |

**Điểm dễ nhầm:** repository `retail-containers` và image `orders-api` là **hai cấp khác nhau**. Trong đường dẫn trên, `retail-containers` là tài nguyên repository có IAM policy/location; `orders-api` là image trong repository đó. Ghi thiếu tên repository hoặc dùng sai location có thể dẫn đến `not found` dù tag đúng.

### 2.3. Container Registry và Artifact Registry

Các hướng dẫn cũ có thể dùng tên miền `gcr.io`, `us.gcr.io` hoặc thuật ngữ **Container Registry**. Artifact Registry là giải pháp quản lý artifact được khuyến nghị cho workflow mới, hỗ trợ các hostname `LOCATION-docker.pkg.dev` và một số mô hình **gcr.io repositories được Artifact Registry lưu trữ**. Không suy rằng mọi image `gcr.io` cũ tự động nằm trong một repository `*.pkg.dev` hay có cùng IAM.

Khi nâng cấp pipeline, hãy xác minh **loại registry thực tế, repository, quyền, địa chỉ image** và quy trình migration. Bài này dùng `asia-southeast1-docker.pkg.dev` để minh họa trực tiếp Artifact Registry.

### 2.4. Repository mode

Artifact Registry có những mô hình repository phục vụ nhu cầu khác nhau:

| Loại | Mục đích | Lưu ý với push/pull |
| --- | --- | --- |
| **Standard repository** | Lưu artifact do nhóm tự build/push. | Là lựa chọn chính để `docker push` image nội bộ. |
| **Remote repository** | Cache/proxy artifact từ nguồn upstream được hỗ trợ. | Không coi là nơi đẩy image nội bộ như standard repo. |
| **Virtual repository** | Cung cấp một điểm truy cập tổng hợp tới các repository upstream được cấu hình. | Chủ yếu phục vụ truy xuất; không thay thế standard repository cho push. |

Để học quy trình build–push–pull và quản lý IAM rõ ràng, ta dùng **standard Docker repository**. Những loại repository khác có chính sách upstream, quyền, cache và giới hạn định tuyến riêng cần đối chiếu với tài liệu hiện hành.

## 3. Kiến trúc luồng phát hành image

### 3.1. Chỉ build một lần cho các môi trường

~~~mermaid
flowchart LR
    SRC["Git source / Dockerfile"] --> CI["CI: test + build"]
    CI --> AUTH["Identity ngắn hạn + quyền Writer"]
    AUTH --> REG["Artifact Registry: standard Docker repo"]
    REG --> META["Image digest + metadata phát hành"]
    META --> RUN["Cloud Run revision"]
    META --> GKE["GKE Deployment"]
    META --> VM["Compute Engine worker"]
    IAM["IAM repo-level"] -. "Writer cho CI; Reader cho consumer" .-> REG
    SEC["Scan / policy / provenance"] -. "Đánh giá artifact" .-> META
~~~

Luồng này tách rõ:

1. **Build identity** tạo và kiểm thử artifact.
2. **Publisher identity** cần quyền push vào repository.
3. **Deployer identity** cần quyền triển khai Cloud Run/GKE/VM và, tùy sản phẩm, quyền đọc image.
4. **Pulling identity** được nền tảng sử dụng để tải image tại thời điểm deploy/khởi chạy.
5. **Runtime identity** bên trong ứng dụng có quyền truy cập dữ liệu như Cloud Storage, Cloud SQL, Pub/Sub hoặc Secret Manager.

Đây **không nhất thiết là cùng một service account**. Nguyên tắc quyền tối thiểu yêu cầu chỉ cấp quyền trên đúng tài nguyên cần thiết cho mỗi bước.

### 3.2. Vì sao không build lại trong production?

Nếu GKE dùng `docker build .` trên nhánh `main` hôm nay, còn Cloud Run build lại ngày mai, nội dung dependency có thể khác ngay cả khi tag của ứng dụng giống nhau. Một quy trình tốt:

- Build một lần trong CI từ commit/version cụ thể.
- Ghi **digest được push thành công** và kết quả kiểm thử.
- Promote **cùng digest** qua dev, staging, production theo cơ chế được tổ chức duyệt.
- Khi rollback, đưa runtime về **digest đã từng được xác minh**, không phụ thuộc tag `latest` đang thay đổi.

Việc pin digest giúp kiểm soát nội dung image; nó **không tự bảo đảm image không có lỗ hổng, không chứa secret hoặc hoạt động đúng**. Cần thêm kiểm tra bảo mật và chất lượng trước phát hành.

## 4. Chuẩn bị project, location và Docker repository

### 4.1. Kiểm kê đầu vào

Trước khi thao tác, xác định:

| Thông số | Giá trị ví dụ | Câu hỏi thiết kế |
| --- | --- | --- |
| Project sở hữu repository | `retail-lab` | Ai quản trị IAM và Billing của artifact? |
| Location | `asia-southeast1` | Có gần GKE/Cloud Run/VM và phù hợp residency không? |
| Repository | `retail-containers` | Đội nào có quyền đọc, ghi và dọn artifact? |
| Image name | `orders-api` | Có quy ước tên đủ để truy vết dịch vụ không? |
| Version tag | `v1.0.0` | Có dễ bị ghi đè và quy trình release chấp nhận không? |
| Publisher principal | CI service account | Chỉ cần `artifactregistry.writer` hay cần thêm quyền? |
| Consumer principals | GKE node SA / Cloud Run service agent, v.v. | Ai thực sự pull image? |
| Network path | DNS/TCP 443 tới registry | Workload không có external IP có route đến registry không? |

**Repository location** là thuộc tính của tài nguyên repository. Không tự giả định có thể đổi trực tiếp location của repository sau khi tạo. Nếu cần chuyển vùng, chuẩn bị repository mới, chuyển artifact, cấp quyền và cập nhật URI của nơi triển khai theo hướng dẫn dịch vụ.

### 4.2. Xác nhận API và phiên bản công cụ

Ví dụ dùng Bash. Các lệnh `describe`, `list` là **read-only**; `enable`, `create`, `add-iam-policy-binding`, `push`, `delete` thay đổi tài nguyên thật.

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"
REPOSITORY="retail-containers"
IMAGE_NAME="orders-api"
IMAGE_TAG="v1.0.0"
HOST="${LOCATION}-docker.pkg.dev"
IMAGE_URI="${HOST}/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${IMAGE_TAG}"

# READ-ONLY: tài khoản và project CLI đang sử dụng.
gcloud auth list
gcloud config get-value project
gcloud --version
docker --version
~~~

Máy thực hành cần Docker Engine hoặc môi trường Docker tương thích, có quyền thực thi Docker CLI và kết nối mạng. Với Windows PowerShell, cú pháp khai báo biến và nối dòng khác Bash; không sao chép nguyên `$VAR="..."` hoặc dấu `\` sang PowerShell.

### 4.3. Bật Artifact Registry API

~~~bash
# WRITE: thực hiện trên project được phép.
gcloud services enable artifactregistry.googleapis.com \
  --project="$PROJECT_ID"
~~~

Việc bật API yêu cầu quyền quản trị dịch vụ thích hợp, không phải chỉ cần `roles/artifactregistry.reader`. Nếu project đã bật API, có thể bỏ qua thao tác ghi này.

### 4.4. Tạo standard Docker repository

~~~bash
# WRITE: tạo repository mới; không chạy lại nếu repo đã tồn tại.
gcloud artifacts repositories create "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --repository-format=docker \
  --location="$LOCATION" \
  --description="Container images for retail workloads"

# READ-ONLY: xác minh loại, vị trí và metadata repository.
gcloud artifacts repositories describe "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

# READ-ONLY: liệt kê repositories trong location.
gcloud artifacts repositories list \
  --project="$PROJECT_ID" \
  --location="$LOCATION"
~~~

Không ghi dữ liệu thật vào project chỉ dùng để đọc hoặc chưa được phê duyệt. Với production, có thể cấu hình **cleanup policies**, tag immutability (nếu áp dụng), CMEK và các kiểm soát khác ngay từ quy trình IaC thay vì thêm tùy tiện sau khi artifact đã có người sử dụng.

## 5. Xác thực Docker với Artifact Registry

### 5.1. Docker cần registry credentials

`gcloud auth login` xác thực Google Cloud CLI nhưng **không tự động khiến mọi lần `docker push`/`pull` đều dùng đúng token**. Docker cần phương án credential phù hợp cho hostname `LOCATION-docker.pkg.dev`.

Có hai cách phổ biến:

1. **gcloud credential helper:** Docker sử dụng thông tin xác thực từ gcloud khi truy cập hostname đã cấu hình.
2. **Access token ngắn hạn:** Docker đăng nhập bằng token được cấp cho Google principal và hết hạn theo chính sách.

Không dùng **service account key JSON dài hạn** làm lựa chọn mặc định cho máy cá nhân hoặc CI/CD. Ưu tiên danh tính người dùng hợp lệ hoặc **Workload Identity Federation/short-lived credentials** trong automation. Không in token vào build logs hoặc commit file Docker config chứa secret.

### 5.2. Dùng gcloud Docker credential helper

~~~bash
# WRITE trên cấu hình Docker của máy đang chạy lệnh.
gcloud auth configure-docker "${LOCATION}-docker.pkg.dev"

# Xem cấu hình credentials helper nếu cần chẩn đoán.
# Docker đọc file config ở vị trí được xác định theo DOCKER_CONFIG
# hoặc thư mục cấu hình mặc định của người dùng.
~~~

Lệnh trên cấu hình Docker để gọi credential helper cho **hostname đã chỉ định**. Nó không cấp quyền IAM cho tài khoản gcloud. Nếu gcloud đang dùng principal sai hoặc repository chưa cho phép principal đó ghi, `docker push` vẫn bị từ chối.

**Cảnh báo `sudo docker`:** trên Linux, lệnh `sudo docker` có thể dùng Docker config của root thay vì người dùng đã chạy `gcloud auth configure-docker`. Ưu tiên cấu hình Docker nhất quán với user thực thi; không sửa bằng cách sao chép token lung tung giữa các tài khoản.

### 5.3. Dùng access token ngắn hạn

Trong môi trường cho phép dùng access token CLI, có thể đăng nhập như sau:

~~~bash
gcloud auth print-access-token | docker login \
  -u oauth2accesstoken \
  --password-stdin "https://${LOCATION}-docker.pkg.dev"
~~~

Ví dụ này giả định gcloud đã được xác thực bằng danh tính đúng và token có quyền phù hợp. Token ngắn hạn **sẽ hết hạn**, vì vậy pipeline cần cơ chế cấp mới theo phiên thay vì phụ thuộc token lưu lâu.

Trong CI/CD chạy ngoài Google Cloud, **Workload Identity Federation** có thể cho phép đổi danh tính từ nhà cung cấp CI lấy thông tin xác thực Google Cloud ngắn hạn, giảm nhu cầu quản lý private keys của service account. Quy trình thiết lập cụ thể tùy CI provider và chính sách tổ chức.

### 5.4. Xác thực khác phân quyền

| Trạng thái | Kết quả có thể gặp |
| --- | --- |
| Không có credential/token hợp lệ | `401 Unauthorized`, yêu cầu xác thực hoặc không pull/push được. |
| Credential hợp lệ nhưng thiếu IAM permission | `403 Permission denied`, `denied: Permission ...` hoặc thông báo tương tự. |
| Có quyền nhưng sai URI/repository/image/tag | `not found`, `manifest unknown` hoặc lỗi path. |
| IAM, URI đúng nhưng mạng không đến được registry | DNS timeout, TLS timeout, proxy/firewall error. |

**Không xử lý `403` bằng cách đổi tag, và không xử lý timeout bằng cách cấp quyền Owner.** Phải xác định lớp lỗi trước.

## 6. Build, tag và push một container image

### 6.1. Mẫu ứng dụng nhỏ

Để có một ví dụ tự chứa, người học có thể tạo hai file `app.py` và `Dockerfile` **trong thư mục thực hành riêng do mình kiểm soát**. Hai khối mã sau là ví dụ, không phải yêu cầu sửa thêm file nào của mô-đun học này.

`app.py`:

~~~python
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/healthz", "/"):
            body = b"orders-api demo OK\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

port = int(os.environ.get("PORT", "8080"))
HTTPServer(("0.0.0.0", port), Handler).serve_forever()
~~~

`Dockerfile`:

~~~dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY app.py /app/app.py
ENV PORT=8080
EXPOSE 8080
CMD ["python", "/app/app.py"]
~~~

Đây là ứng dụng tối giản cho lab, không phải web server production. Với ứng dụng thật, dùng base image được duyệt, chạy non-root khi phù hợp, pin dependency/base image, xây image đa kiến trúc nếu cần, quét lỗ hổng và không đưa credentials vào Docker layers.

### 6.2. Build và kiểm thử cục bộ

~~~bash
# READ LOCAL SOURCE + WRITE LOCAL IMAGE:
docker build -t orders-api:local .

# RUN LOCAL: mở container để thử nghiệm.
docker run --rm -p 8080:8080 orders-api:local

# Trong terminal khác, kiểm tra HTTP.
curl -fsS http://127.0.0.1:8080/healthz
~~~

Kết quả mong muốn của `curl` là `orders-api demo OK`. Sau kiểm tra, dừng container. Nếu môi trường host đã dùng port `8080`, chọn một cổng host khác như `-p 18080:8080` và cập nhật URL thử nghiệm.

**Build thành công không đồng nghĩa image có thể chạy trên mọi nền tảng.** Image architecture, entrypoint, cổng lắng nghe và runtime permissions phải tương thích với Cloud Run/GKE/VM dự kiến.

### 6.3. Tag image theo URI của repository

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"
REPOSITORY="retail-containers"
IMAGE_NAME="orders-api"
VERSION="v1.0.0"

IMAGE_URI="${LOCATION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${VERSION}"

# WRITE LOCAL TAG: gắn tên registry cho image đã build.
docker tag orders-api:local "$IMAGE_URI"

# READ LOCAL: xác nhận image tag.
docker image ls
~~~

`docker tag` không upload bytes lên registry, chỉ tạo tham chiếu tên khác trong Docker local image store. Tên registry phải trùng location của repo và project sở hữu artifact.

### 6.4. Push lên Artifact Registry

~~~bash
# WRITE REMOTE: upload layers/manifest vào repository.
# Cần Docker credentials hợp lệ và quyền artifactregistry.writer.
docker push "$IMAGE_URI"

# READ-ONLY REMOTE: liệt kê images/tags hiện tại.
gcloud artifacts docker images list \
  "${LOCATION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}" \
  --project="$PROJECT_ID" \
  --include-tags
~~~

Docker có thể **chỉ upload các layers chưa có trên registry** do cơ chế content addressing, nhưng mỗi lần push phải có quyền ghi phù hợp và manifest/tag hợp lệ. Khi mạng yếu, retry có thể cần thiết; không chạy nhiều pipeline ghi cùng một tag release nếu chưa có quy tắc tránh race.

### 6.5. Kiểm chứng digest và ghi nhận release artifact

Sau push, output của Docker thường có dòng chứa digest. Có thể kiểm tra thêm image trong registry:

~~~bash
# READ-ONLY REMOTE: xem các versions, digests và tags.
gcloud artifacts docker images list \
  "${LOCATION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}" \
  --project="$PROJECT_ID" \
  --include-tags
~~~

Sử dụng digest thực tế đọc được từ output/registry, ví dụ:

~~~text
asia-southeast1-docker.pkg.dev/retail-lab/retail-containers/orders-api@sha256:<DIGEST_THUC_TE>
~~~

`<DIGEST_THUC_TE>` là **placeholder**, không phải digest hợp lệ để chạy lệnh. Trong release manifest nên lưu `git_commit`, image URI theo digest, pipeline run ID, thời điểm build, kết quả kiểm thử và chính sách phê duyệt.

**Tag không phải chữ ký bảo mật.** Nếu nhiều người có quyền Writer và repository không đặt kiểm soát ghi đè phù hợp, tag `v1.0.0` có thể bị thay đổi trong tương lai. Digest giúp phát hiện đúng artifact, còn chính sách bảo mật cần thêm quyền tối thiểu và kiểm tra nguồn gốc.

## 7. Pull image và chạy từ repository

### 7.1. Pull theo tag hoặc digest

Trên máy đã có Docker credentials hợp lệ và quyền Reader:

~~~bash
# READ REMOTE + WRITE LOCAL IMAGE CACHE:
docker pull \
  asia-southeast1-docker.pkg.dev/retail-lab/retail-containers/orders-api:v1.0.0

# Ưu tiên digest trong workflow production, thay bằng giá trị thật.
# docker pull \
#   asia-southeast1-docker.pkg.dev/retail-lab/retail-containers/orders-api@sha256:...
~~~

Docker tải manifest và layers cần thiết về local image store. **Pull không chạy container**, và quyền pull không cấp quyền truy cập dữ liệu bên trong Cloud SQL hay Cloud Storage.

### 7.2. Chạy image đã pull

~~~bash
docker run --rm -p 8080:8080 \
  asia-southeast1-docker.pkg.dev/retail-lab/retail-containers/orders-api:v1.0.0
~~~

Nếu ứng dụng thực cần database credential hoặc service identity, dùng cơ chế runtime phù hợp. **Không lưu service account key trong image hoặc biến môi trường bị in ra logs**. Nếu container chạy trong Compute Engine, GKE hoặc Cloud Run, ưu tiên danh tính workload được quản lý thay vì chia sẻ khóa tĩnh.

### 7.3. Pull không thành công: kiểm tra thứ tự nào?

1. URI có đúng **hostname location, project, repository, image và tag/digest** không?
2. Máy gọi có DNS/TCP/TLS tới `LOCATION-docker.pkg.dev` không?
3. Docker đang dùng credentials của user/service account nào?
4. Principal đó có quyền đọc repository không?
5. Image/digest đã được push và chưa bị xóa bởi cleanup policy chưa?
6. Runtime architecture/manifest có tương thích với môi trường triển khai không?

Không nên chỉ kiểm tra `docker login` rồi kết luận mọi pull sẽ thành công; mỗi repository có thể có IAM policy khác nhau.

## 8. IAM: ai được đọc, ghi hoặc quản trị artifact?

### 8.1. Vai trò phổ biến

| Role | Mục đích điển hình | Không nên cấp cho |
| --- | --- | --- |
| `roles/artifactregistry.reader` | Xem và tải artifact từ repository được phép. | Người không có nhu cầu sử dụng image. |
| `roles/artifactregistry.writer` | Đẩy hoặc cập nhật artifact trong repository theo permission của role. | Runtime chỉ cần pull; không nên có khả năng sửa image. |
| `roles/artifactregistry.repoAdmin` | Quản trị repository/artifacts theo phạm vi quyền của role. | CI chỉ cần push một image. |
| `roles/artifactregistry.admin` | Quyền quản trị Artifact Registry rộng hơn trên phạm vi gán. | Ứng dụng runtime hoặc mọi developer mặc định. |

**Tên role không thay thế việc đọc permissions và scope thực tế.** Đối với hoạt động xóa artifact, cleanup policy, tạo repository hoặc chỉnh IAM, cần kiểm tra quyền chính xác đang được yêu cầu. Role Writer không có nghĩa nên được xem như quyền quản trị mọi tài nguyên và cũng không cần cấp Admin để thực hiện một thao tác push thông thường.

### 8.2. Phạm vi phân quyền

IAM có thể được gán ở **repository**, **project** hoặc phạm vi tổ tiên phù hợp. Mức rộng hơn có thể dẫn đến quyền với nhiều repositories:

~~~text
Organization
└── Project: retail-lab
    ├── Repository: retail-containers
    │   ├── orders-api
    │   └── catalog-api
    └── Repository: platform-tools
        └── diagnostics
~~~

Nếu nhóm ứng dụng chỉ cần push vào `retail-containers`, hãy ưu tiên **repo-level Writer** thay vì project-wide Admin. Tuy nhiên trong **một repository**, role Reader/Writer thường áp dụng theo cấp repository cho các artifact bên trong, không tự chia quyền đến từng tag. Nếu `orders-api` và `catalog-api` có yêu cầu bảo mật/owner khác nhau, có thể cần tách thành hai repositories.

### 8.3. Cấp quyền Reader cho người dùng hoặc service account

Ví dụ repository đã tồn tại:

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"
REPOSITORY="retail-containers"

# READ-ONLY: xem IAM allow policy trực tiếp của repository.
gcloud artifacts repositories get-iam-policy "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

# WRITE: chỉ cấp quyền đọc cho một service account minh họa.
gcloud artifacts repositories add-iam-policy-binding "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --member="serviceAccount:gke-pull@retail-lab.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"
~~~

Service account `gke-pull@retail-lab.iam.gserviceaccount.com` chỉ là tên giả định; tài khoản phải tồn tại, được cấu hình đúng trên node/workload và là **principal thực sự thực hiện pull**. Lệnh thêm binding không tự tạo service account hoặc tự thay cấu hình node pool.

### 8.4. Cấp quyền Writer cho CI/CD

~~~bash
# WRITE: CI publisher có quyền ghi artifact trong đúng repository.
gcloud artifacts repositories add-iam-policy-binding "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --member="serviceAccount:ci-publisher@retail-lab.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
~~~

Pipeline `ci-publisher` có thể build và push image theo phạm vi role. Nhưng để **triển khai Cloud Run hoặc thay GKE Deployment**, pipeline còn cần quyền của dịch vụ đích (ví dụ Cloud Run Admin/Developer, quyền quản trị Kubernetes cluster phù hợp, quyền sử dụng runtime service account khi cần). **Artifact Registry Writer không tự cấp quyền triển khai.**

### 8.5. Thu hồi quyền

~~~bash
# WRITE: xóa một binding Reader đã cấp trực tiếp.
gcloud artifacts repositories remove-iam-policy-binding "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --member="serviceAccount:gke-pull@retail-lab.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"
~~~

Thu hồi một binding có thể **chưa đủ** nếu principal còn có role từ project, folder/organization, group hoặc binding khác. Cần xem quyền hiệu lực và các cơ chế IAM Conditions/deny policy có áp dụng. Thu hồi Reader cũng không nhất thiết xóa image đã nằm trong local cache hoặc ngắt ngay các container đang chạy.

### 8.6. Chia sẻ cross-project

Một kiến trúc phổ biến:

~~~text
Project: platform-images
  Repository: prod-images
    orders-api@sha256:...

Project: retail-prod
  Cloud Run service / GKE cluster
    cần pull image từ platform-images
~~~

**Đúng project của image** phải cấp quyền đọc cho danh tính thực sự pull, cho dù workload chạy trong project khác. Cần xem service agent/node service account của sản phẩm tiêu thụ, vị trí repository, hỗ trợ cross-project và IAM policy.

Không cấp `allUsers` hoặc project Editor chỉ để “chia sẻ nhanh” image giữa hai project. Nếu nhóm muốn kiểm soát vòng đời khác nhau, có thể dùng repository riêng cho mỗi môi trường/đội, nhưng phải quản lý việc promote đúng digest và kiểm soát artifact được phép triển khai.

## 9. GKE, Cloud Run và Compute Engine pull bằng danh tính nào?

### 9.1. GKE: node service account thường là principal pull

Với nhiều cấu hình GKE, **kubelet/container runtime trên node** lấy credentials để kéo image từ Artifact Registry thông qua **node service account** của Compute Engine node. Đừng nhầm **Kubernetes ServiceAccount** hay **Workload Identity Federation for GKE** của Pod (dùng gọi Google APIs khi ứng dụng đang chạy) với danh tính mà node dùng trong quy trình pull image.

~~~mermaid
flowchart LR
    DEP["Kubernetes Deployment: image URI"] --> SCHED["GKE scheduler / node"]
    SCHED --> NODE["Node runtime + node service account"]
    NODE --> REG["Artifact Registry"]
    REG --> POD["Image được tải; Pod khởi chạy"]
    WIF["Pod workload identity"] -. "Quyền gọi Cloud APIs trong runtime" .-> POD
~~~

Để pull thành công, kiểm tra:

- Node service account thực tế (có thể là custom node SA hoặc default Compute Engine SA tùy cấu hình).
- IAM `roles/artifactregistry.reader` trên repository nguồn; đặc biệt quan trọng khi image ở **project khác**.
- **OAuth access scopes** của node nếu cấu hình node vẫn giới hạn quyền API.
- Kết nối mạng, DNS và egress từ node đến hostname Artifact Registry.
- Image URI, tag/digest, architecture và quyền của Kubernetes controller.

Ví dụ Deployment tham chiếu image theo digest:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: retail
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
          image: asia-southeast1-docker.pkg.dev/retail-lab/retail-containers/orders-api@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
~~~

`REPLACE_WITH_REAL_DIGEST` là placeholder, không phải một digest có thể pull. Phải thay bằng digest hợp lệ lấy từ registry. **Không dùng image tag `latest` làm cách quản lý phiên bản production** khi cần biết chính xác artifact nào đã triển khai.

Khi thấy `ImagePullBackOff`, xem `kubectl describe pod`, các events như `ErrImagePull`, danh tính node, IAM repo và mạng. Một Pod có service account gắn nhãn quyền truy cập Cloud Storage đúng không chứng minh node được phép pull image.

### 9.2. Cloud Run: phân biệt deployer, service agent và runtime SA

Khi deploy image lên **Cloud Run**, có ít nhất ba danh tính cần phân biệt:

| Danh tính | Vai trò |
| --- | --- |
| **Deployer user/CI** | Gửi yêu cầu tạo/cập nhật Cloud Run service; cần quyền deploy và có thể cần quyền đọc image cùng quyền dùng service account runtime. |
| **Cloud Run service agent** của project chạy dịch vụ | Danh tính hệ thống của Cloud Run tham gia lấy image/quản lý tài nguyên cần thiết; khi image ở project khác, thường cần được cấp quyền Reader trên repository nguồn. |
| **Runtime service account** | Danh tính mà code của Cloud Run dùng để gọi Cloud SQL, Cloud Storage, Secret Manager, Pub/Sub... sau khi container chạy. |

Với image thuộc **cùng project**, quyền mặc định của service agent có thể đáp ứng yêu cầu; với **cross-project repository**, cần cấp quyền rõ ràng theo hướng dẫn chính thức. Tên service agent của Cloud Run thường có dạng:

~~~text
service-PROJECT_NUMBER@serverless-robot-prod.iam.gserviceaccount.com
~~~

Chỉ thay `PROJECT_NUMBER` bằng số project thực của **Cloud Run consumer**, không lấy project ID chữ để điền vào mẫu. Cần kiểm tra đúng principal từ trang IAM/service agents trước khi cấp quyền.

Ví dụ deploy sau khi đã thay digest thật:

~~~bash
# WRITE: tạo/cập nhật Cloud Run service.
# URI digest phải tồn tại, người deploy phải có các quyền thích hợp.
gcloud run deploy orders-api \
  --project=retail-prod \
  --region=asia-southeast1 \
  --image="asia-southeast1-docker.pkg.dev/platform-images/prod-images/orders-api@sha256:REPLACE_WITH_REAL_DIGEST"
~~~

Lệnh minh họa không thiết lập ingress/auth của Cloud Run, không cấu hình environment/secrets và không cấp IAM cho runtime service account. Đối với production, phải định nghĩa các thành phần đó trong cấu hình đã review, tránh mặc nhiên mở quyền gọi công khai.

### 9.3. Compute Engine: VM chủ động gọi Docker pull

Một VM chạy Docker container không tự có một registry controller như GKE. Người vận hành hoặc automation trên VM cần:

1. Cài Docker/container runtime phù hợp.
2. Xác thực với Artifact Registry bằng danh tính người dùng hoặc **service account gắn VM** theo phương án được hỗ trợ.
3. Có quyền `artifactregistry.reader` trên repository.
4. Đảm bảo OAuth scopes của VM nếu chúng giới hạn quyền API.
5. Có đường mạng/DNS tới Artifact Registry và chính sách egress hợp lệ.

Không nhúng JSON key của service account vào Docker image. Với VM không có external IP, cần thiết kế **Private Google Access, Cloud NAT hoặc đường kết nối Google APIs phù hợp** theo hostname và topology sử dụng. `*.pkg.dev` có yêu cầu DNS/endpoint riêng trong một số mô hình private access; không nên áp mọi quy tắc `*.googleapis.com` cho hostname registry mà chưa kiểm tra tài liệu.

### 9.4. Nhiều nền tảng dùng chung một artifact

| Nền tảng | Điểm kiểm soát image | Cơ chế scale/runtime |
| --- | --- | --- |
| **GKE** | Node pull image, Pod spec tham chiếu tag/digest. | Kubernetes Deployments/Jobs, node pools và autoscaling theo kiến trúc. |
| **Cloud Run** | Deployer + service agent có quyền liên quan tới image; revision gắn image. | Cloud Run quản lý instances/concurrency và revision traffic. |
| **Compute Engine** | VM/automation tự xác thực Docker pull và chạy container. | VM/MIG/systemd hoặc công cụ điều phối do đội vận hành chọn. |

Không suy rằng quyền của một nền tảng tự động chuyển sang nền tảng khác. Cùng image digest có thể chạy được ở nhiều nơi, nhưng **environment variables, ingress, secrets, danh tính, volume và network** vẫn khác nhau.

## 10. Thiết kế CI/CD không dùng khóa dài hạn

### 10.1. Tách nhiệm vụ build, publish và deploy

Một pipeline có thể gồm:

~~~mermaid
flowchart TD
    S["Commit / pull request"] --> T["Lint, unit/integration tests"]
    T --> B["Build container image"]
    B --> SEC["Scan, SBOM, provenance/policy"]
    SEC --> P["CI publisher: push to Artifact Registry"]
    P --> DG["Ghi digest + release metadata"]
    DG --> ST["Deploy staging theo digest"]
    ST --> QA{"Kiểm thử/approval đạt?"}
    QA -- "Có" --> PR["Deploy production theo cùng digest"]
    QA -- "Không" --> BL["Block release và điều tra"]
~~~

Quy trình này phải xác định rõ principal ở từng bước, repository phù hợp, quyền CI, môi trường triển khai và cách log/audit. **Chỉ một tài khoản có quyền Admin cho toàn bộ pipeline** sẽ làm tăng phạm vi ảnh hưởng khi token bị lộ.

### 10.2. Quyền CI publisher

CI cần:

- Quyền đọc source và truy cập build environment theo công cụ CI.
- Credential Google Cloud ngắn hạn, ví dụ qua **Workload Identity Federation** nếu CI chạy bên ngoài Google Cloud.
- `roles/artifactregistry.writer` trên repository được phép push.
- Quyền deploy Cloud Run/GKE ở môi trường đích **chỉ nếu** pipeline đảm nhiệm deploy.
- Quyền đọc secrets theo nguyên tắc tối thiểu, tránh in secrets vào build logs/layers.

Một service account chạy Cloud Build cũng cần được gán quyền tương ứng; **không giả định mọi project mặc định cho Cloud Build quyền ghi Artifact Registry trên mọi repository**. Hãy xác định chính xác service account của build (default hoặc custom) và IAM policy hiện hành.

### 10.3. Tag theo commit và phát hành theo digest

Ví dụ chiến lược tag:

~~~text
orders-api:commit-9a71c3d
orders-api:release-2026-11-19
orders-api:v1.3.0
~~~

Tags hỗ trợ con người và tooling tìm image, nhưng **digest mới là tham chiếu chính xác của artifact**. Khi CI kết thúc push:

1. Đọc digest thật của image/manifest vừa push.
2. Ghi digest vào release metadata; liên kết với Git commit và test result.
3. Deploy staging bằng URI digest.
4. Khi đạt điều kiện phát hành, deploy production bằng **chính digest đó**.
5. Rollback về digest được duyệt trước đó, không nhất thiết build lại.

Với multi-architecture image, **manifest list/index** và từng platform manifest có thể có digest khác nhau; cần ghi tham chiếu phù hợp với chính image mà runtime triển khai. Kiểm thử architecture mục tiêu trước khi phát hành.

### 10.4. Kiểm soát lỗ hổng và nguồn gốc image

Artifact Registry có thể được tích hợp với những khả năng **Artifact Analysis/vulnerability scanning**, policy và công cụ kiểm soát phát hành như **Binary Authorization** trong môi trường hỗ trợ. Khi đặt quality gate, cân nhắc:

- Base image đến từ nguồn nào, có pin digest và cập nhật định kỳ không?
- Image có lỗ hổng nghiêm trọng chưa được xử lý hoặc không có ngoại lệ được duyệt không?
- Có **SBOM**, chữ ký/attestation hoặc provenance để truy nguồn build không?
- Image đã được test trong đúng môi trường/architecture chưa?
- Runtime chỉ dùng những digest đã được phê duyệt hay còn pull `latest` tùy ý?

**Quét lỗ hổng không chứng minh image hoàn toàn an toàn**: kết quả phụ thuộc dữ liệu phát hiện, gói được nhận diện và thời điểm scan. Cũng không nên ngăn cập nhật bảo mật chỉ vì chính sách tag immutability bị cấu hình quá cứng; phát hành image mới với tag/version/digest mới và chuyển deployment theo quy trình.

## 11. Bảo mật repository và nguyên tắc tối thiểu

### 11.1. Repository riêng cho phạm vi nhạy cảm

Có thể chia:

~~~text
Project: platform-images
  Repository: dev-images
    CI dev → Writer
    Dev GKE nodes → Reader

  Repository: prod-images
    Release publisher → Writer
    Production Cloud Run/GKE pull identities → Reader
    Developer thông thường → không có Writer
~~~

Ranh giới repository giúp phân quyền dễ kiểm toán hơn việc cho mọi người quyền push vào một repository chứa tất cả image production. Tuy vậy, separation chỉ có giá trị khi **IAM không bị gán quá rộng ở project/folder** và workflow promotion được thực thi thật.

### 11.2. Tránh public repository ngoài chủ đích

Container image có thể chứa source, config, runtime dependency và thông tin nội bộ. Không cấp quyền `allUsers`/`allAuthenticatedUsers` nếu chưa có quy trình công bố artifact rõ ràng. Nếu cần image public, thiết kế repository chuyên biệt và review nội dung, license, secrets cùng lifecycle.

**Artifact Registry reader không phải quyền đọc dữ liệu ứng dụng**, nhưng khả năng xem/pull image có thể làm lộ IP nội bộ của tổ chức (mã nguồn, dependency, endpoint). Vì vậy IAM Reader cũng cần được cấp theo nhu cầu.

### 11.3. Secrets và thông tin nhạy cảm trong image

Không lưu:

- Private keys, token đăng nhập registry hoặc service account JSON keys.
- Mật khẩu database trong `ENV`, Dockerfile hoặc file được `COPY` vào layers.
- `.env`, `.npmrc`, credentials cache hoặc output debug chứa secrets.

Ngay cả khi xóa file trong Dockerfile ở một layer sau đó, secret **có thể vẫn tồn tại trong layer trước**. Dùng build secrets được công cụ hỗ trợ, `.dockerignore`, runtime secret injection và IAM của Secret Manager khi phù hợp.

### 11.4. Retention, tag immutability và cleanup

| Cơ chế | Mục tiêu | Rủi ro nếu thiết kế sai |
| --- | --- | --- |
| **Tag policy/immutability** | Ngăn hoặc kiểm soát việc ghi đè tag quan trọng theo khả năng hỗ trợ. | Pipeline cũ cố push đè tag sẽ thất bại; cần chiến lược version mới. |
| **Cleanup policy** | Tự động dọn artifact không còn cần theo điều kiện được hỗ trợ. | Xóa digest đang phục vụ hoặc cần rollback nếu không bảo vệ đúng. |
| **Release metadata** | Liên kết digest, commit, môi trường, thời điểm và kết quả kiểm thử. | Không xác định được artifact nào cần phục hồi. |
| **IAM audit** | Theo dõi quyền Writer/Admin và thay đổi repository. | Quyền rộng từ project làm vô hiệu sự phân tách repo. |

Trước khi bật cleanup tự động, liệt kê những **digests đang được dùng** bởi Cloud Run revisions, GKE Deployments và VM/MIG; định nghĩa thời gian giữ cho các bản rollback, những tags cần bảo vệ và cách xử lý image untagged. Nếu công cụ hỗ trợ dry-run, dùng nó trong quá trình review. **Tag bị xóa** và **image digest bị xóa** không luôn có cùng hệ quả; kiểm tra đúng đối tượng trước khi thực thi lệnh phá hủy.

### 11.5. Repository encryption và vị trí lưu trữ

Artifact Registry mã hóa dữ liệu theo mô hình của dịch vụ; với một số trường hợp có thể dùng **customer-managed encryption keys (CMEK)** khi tạo repository theo điều kiện hỗ trợ. Cần xem location/key policy, quyền KMS, hậu quả khi key bị vô hiệu hóa và quy trình rotation. Không tự suy rằng chọn `asia-southeast1` cho repository sẽ khiến mọi dữ liệu phụ trợ của pipeline luôn bị giới hạn trong region đó; yêu cầu residency phải xét logs, build output, scanners và artifacts liên quan.

## 12. Troubleshooting theo lớp

### 12.1. Bảng lỗi phổ biến

| Dấu hiệu | Nguyên nhân có thể | Kiểm tra đầu tiên |
| --- | --- | --- |
| `denied: Permission ...` khi push | CI/user thiếu Writer trên repository, IAM Conditions hoặc policy. | Principal đang xác thực, IAM allow policy của repo/project. |
| `401 Unauthorized` khi pull | Docker không có credential hợp lệ, token hết hạn hoặc helper sai user. | `gcloud auth list`, Docker credential helper và thời hạn token. |
| `403 Permission denied` dù đã `docker login` | Token hợp lệ nhưng principal không được phép truy cập repo. | Role `artifactregistry.reader` trên repo đúng project/location. |
| `manifest unknown` hoặc `not found` | Sai tag/digest, image đã bị xóa hoặc dùng sai repository. | Liệt kê images/tags trong repo và so sánh URI. |
| `lookup ... docker.pkg.dev` lỗi | DNS, proxy hoặc môi trường không có đường phân giải. | DNS resolver, egress policy. |
| `connection timed out` | VPC route, NAT/PGA/endpoint, firewall hoặc proxy chặn. | DNS → TCP 443 → policy → network path. |
| Push thành công nhưng GKE `ImagePullBackOff` | Node SA thiếu Reader/cross-project, sai image URI hoặc scopes/network. | Pod events, node service account, repository IAM. |
| Cloud Run báo không truy cập được image | Sai digest, service agent/deployer thiếu permission, repo khác project. | Artifact path, Cloud Run service agent và deployer IAM. |
| Container chạy local nhưng Cloud Run fail startup | Sai port, bind `127.0.0.1`, architecture, command/entrypoint. | Cloud Run revision logs và runtime config. |
| Tag `v1.0.0` chạy code khác hôm qua | Tag đã được cập nhật hoặc nhiều pipeline push cùng tag. | Digest trước/sau, audit và release metadata. |
| Disk/cache VM hết dung lượng | Nhiều image/layers cũ, cache chưa dọn. | Docker disk usage và chính sách dọn local. |
| Chi phí lưu image tăng | Nhiều versions/layers, image lớn, cleanup chưa tối ưu. | Artifact inventory và Cloud Billing. |

### 12.2. Lệnh kiểm tra read-only

~~~bash
PROJECT_ID="retail-lab"
LOCATION="asia-southeast1"
REPOSITORY="retail-containers"

# Đúng project và danh tính?
gcloud auth list
gcloud config get-value project

# Repository có tồn tại đúng location/format?
gcloud artifacts repositories describe "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

# IAM bindings trực tiếp trên repository?
gcloud artifacts repositories get-iam-policy "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

# Những image/tag nào đang hiện hữu?
gcloud artifacts docker images list \
  "${LOCATION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}" \
  --project="$PROJECT_ID" \
  --include-tags
~~~

Không nhìn thấy binding Reader trên repository **chưa chắc người dùng không có quyền**, vì có thể được cấp từ project, folder, organization hoặc qua group; cũng có thể có IAM deny/condition. Cần đánh giá quyền hiệu lực trong từng trường hợp.

### 12.3. Chẩn đoán GKE ImagePullBackOff

~~~bash
# READ-ONLY: chạy từ môi trường có kubeconfig đúng cluster/namespace.
kubectl -n retail get pods
kubectl -n retail describe pod orders-api-EXAMPLE-POD
kubectl -n retail get deployment orders-api -o yaml
~~~

Tên Pod `orders-api-EXAMPLE-POD` là placeholder. Trong `describe`, đọc **Events** và thông báo pull cụ thể:

1. `Failed to pull image` kèm `403`: xem quyền **node service account**.
2. `not found`/`manifest unknown`: xem URI và digest/tag có tồn tại.
3. `i/o timeout`: xem DNS/egress và network node.
4. `no matching manifest`: kiểm tra architecture.
5. Pull thành công nhưng `CrashLoopBackOff`: đã qua lớp registry, cần điều tra container process/config.

GKE có thể sử dụng image cache và cơ chế pull khác nhau theo runtime. Một Pod chạy được không tự chứng minh quyền pull của node sẽ tiếp tục hoạt động nếu IAM bị thu hồi và node phải tải lại image từ đầu.

### 12.4. Chẩn đoán Cloud Run

~~~bash
# READ-ONLY: xem image URI đã gắn với service/revision.
gcloud run services describe orders-api \
  --project=retail-prod \
  --region=asia-southeast1 \
  --format=yaml
~~~

Nếu deployment thất bại vì image:

- Kiểm tra repository/project/location và image digest có thật.
- Xác định principal **deployer** và **Cloud Run service agent** tại project chạy service.
- Với image cross-project, kiểm tra Reader binding tại **repository nguồn** cho service agent thích hợp.
- Nếu image đã được pull nhưng revision không sẵn sàng, chuyển sang logs khởi chạy, biến `PORT`, timeout, entrypoint, memory và phụ thuộc runtime.

**Không cấp quyền `artifactregistry.admin` cho runtime service account** như một cách sửa chung; việc runtime gọi Cloud APIs và việc nền tảng pull image là hai luồng khác nhau.

## 13. Tình huống tổng hợp: một image cho GKE và Cloud Run

### 13.1. Bối cảnh

Doanh nghiệp bán lẻ có:

- Project `platform-images` giữ các image đã kiểm thử ở Artifact Registry.
- Project `retail-dev` chạy GKE cho các worker xử lý đơn hàng.
- Project `retail-prod` chạy Cloud Run API đơn hàng.
- Cloud SQL lưu đơn hàng, Cloud Storage lưu ảnh và report.
- CI tạo image `orders-api` khi có commit, còn đội phát hành duyệt digest lên production.

Mục tiêu là **không build lại image** giữa dev/staging/prod, quyền ghi chỉ thuộc CI, runtime chỉ được quyền gọi API và dịch vụ dữ liệu cần thiết, đồng thời có thể rollback nhanh khi revision lỗi.

### 13.2. Thiết kế repo và IAM

| Đối tượng | Phạm vi quyền | Lý do |
| --- | --- | --- |
| CI publisher | `roles/artifactregistry.writer` trên repo phát hành. | Đẩy image và manifest mới. |
| Developer thông thường | `roles/artifactregistry.reader` trên repo dev hoặc repo được phép. | Xem/pull để kiểm thử, không tự sửa image production. |
| GKE node service account của `retail-dev` | Reader trên repository chứa image. | Node có thể pull image dù repo ở project khác. |
| Cloud Run service agent của `retail-prod` | Reader trên repo `platform-images` khi cần theo cross-project. | Nền tảng có thể truy xuất image triển khai. |
| CI deployer | Quyền triển khai Cloud Run/GKE phù hợp cùng các quyền cần thiết trên image/runtime SA. | Triển khai nhưng không phải Admin mọi repository. |
| Runtime SA | Quyền Cloud SQL/Storage/Secret Manager tối thiểu. | Ứng dụng xử lý nghiệp vụ sau khi chạy. |
| Platform security team | Quyền audit và quản trị policy phù hợp. | Kiểm tra nguồn gốc và việc thay đổi artifact. |

### 13.3. Sơ đồ trách nhiệm

~~~mermaid
flowchart TB
    CI["CI: build + test + push"] --> REPO["Artifact Registry\nplatform-images/prod-images"]
    REPO --> MAN["Release manifest: image digest"]
    MAN --> D["Deployer: staging / production"]
    D --> G["GKE workload trong retail-dev"]
    D --> C["Cloud Run service trong retail-prod"]
    REPO -. "Reader: GKE node SA" .-> G
    REPO -. "Reader: Cloud Run service agent" .-> C
    R["Runtime service identities"] -. "Cloud SQL / Storage / secrets" .-> G
    R -.-> C
    AUD["Audit + policy + scan"] -. "Release gate" .-> MAN
~~~

### 13.4. Quy trình phát hành an toàn

1. CI lấy đúng Git commit, chạy kiểm thử rồi build image.
2. CI xác thực Google Cloud bằng phương án ngắn hạn và push vào standard Docker repo.
3. Pipeline đọc digest, ghi build metadata và chạy policy/scan cần thiết.
4. Deploy vào staging theo digest; kiểm tra readiness, request logs và integration tests.
5. Release approver phê duyệt digest, không đẩy lại image dưới cùng tag.
6. GKE Deployment/Cloud Run revision production tham chiếu digest đã duyệt.
7. Cloud Monitoring theo dõi tỷ lệ lỗi, latency và chỉ số nghiệp vụ; nếu lỗi, rollback về digest/revision được lưu trước đó.
8. Cleanup policy giữ lại những digests còn dùng và một số phiên bản rollback theo quy định.

**Quan trọng:** Cloud Run và GKE có thể cần những thông số runtime khác nhau (cổng, startup, security context, kết nối DB). Cùng artifact giúp kiểm soát nguồn build, nhưng không thay thế việc kiểm thử trong từng nền tảng.

### 13.5. Kiểm thử kịch bản lỗi

| Sự cố mô phỏng trong môi trường thử | Điều cần chứng minh |
| --- | --- |
| Thu hồi Writer của CI | Push bị từ chối, artifact cũ vẫn được consumer Reader sử dụng khi quyền chưa bị đổi. |
| Thu hồi Reader của GKE node SA | Node mới không còn pull được nếu không có quyền khác; Pod đang chạy có thể tiếp tục cho tới khi cần pull lại. |
| Thay image tag sang digest mới | Deployment pin digest cũ không tự trôi theo tag, rollback rõ ràng. |
| Chuyển image sang project khác | Cập nhật URI, repo IAM, service agent/node SA và deployer permissions. |
| Xóa nhầm digest release | Phát hiện qua audit, đánh giá cách phục hồi từ artifact đã lưu/cache/backup nếu có. |
| Registry egress bị chặn | Phân biệt DNS/TCP timeout với lỗi IAM 403. |

## 14. Giám sát và quản lý chi phí

### 14.1. Theo dõi những gì?

**Tầng artifact:**

- Số repositories, images và versions theo đội/môi trường.
- Dung lượng layers/artifacts và xu hướng lưu trữ theo thời gian.
- Tags/digests đang được triển khai và những artifact không còn được tham chiếu.
- Thay đổi IAM, cleanup policy, repository settings và các lần push/delete.
- Kết quả scanning/policy checks và tuổi của base image.

**Tầng deploy/runtime:**

- Tỷ lệ deployment lỗi vì không pull được image.
- Thời gian tạo Pod mới hoặc Cloud Run revision mới; lỗi startup.
- Thời gian phục hồi/rollback sau khi image lỗi.
- Tỷ lệ request thành công, latency và SLO của dịch vụ ứng dụng.

Số lần `docker push` thành công không chứng minh dịch vụ đã sẵn sàng. Với GKE, phải kiểm tra Pod health/rollout; với Cloud Run, kiểm tra revision readiness và lưu lượng thực.

### 14.2. Chi phí Artifact Registry không chỉ là lưu trữ

Chi phí có thể gồm:

- Lưu trữ image layers/versions theo dung lượng và chính sách giá.
- Data transfer khi pull image qua vị trí/đường truyền có tính phí.
- Chi phí compute khi build (ví dụ Cloud Build runners, VM, CI provider).
- Các dịch vụ quét bảo mật, logging hoặc tính năng bổ sung nếu áp dụng.
- Phí network và số lần deployment nếu kéo nhiều image lớn.

Không giả định cứ dùng registry “nội bộ Google Cloud” thì **toàn bộ image pull và data transfer đều miễn phí**. Giá phụ thuộc vùng, nguồn/đích, tier sử dụng và bảng giá có hiệu lực. Theo dõi chi phí trong Billing theo project/repository và lưu lượng thực tế.

### 14.3. Giảm chi phí mà vẫn giữ rollback

1. Dùng base image phù hợp, loại bỏ dependency và file build không cần thiết.
2. Áp multi-stage build, `.dockerignore`, cache/build strategy thích hợp.
3. Không push nhiều bản sao image cùng nội dung vào nhiều repository nếu không có nhu cầu governance.
4. Cấu hình cleanup có **keep rules** cho digest/tag đang triển khai và các bản rollback được duyệt.
5. Định kỳ audit image tồn đọng, release đã hết hạn và môi trường thử nghiệm.
6. Tránh xóa vội image đang được Cloud Run/GKE tham chiếu; kiểm thử trước khi áp dụng cleanup rule rộng.

Một image nhỏ có thể giúp giảm thời gian pull, nhưng tối ưu kích thước không quan trọng bằng việc **image hợp lệ, được bảo vệ và có thể rollback** trong tình huống production.

## 15. Bài tập thực hành

### Bài 1 — Đọc URI

Cho image:

~~~text
europe-west1-docker.pkg.dev/finance-prod/app-images/invoice-worker:v2.5.1
~~~

Hãy xác định **location, project ID, repository, image name và tag**. Nếu muốn triển khai bất biến, còn cần thông tin nào? Vì sao không thể lấy digest giả định từ tên tag?

**Gợi ý:** cần digest thật sau khi push hoặc tra cứu registry, không suy từ version label.

### Bài 2 — Phân quyền tối thiểu

Một CI pipeline chỉ cần push image `orders-api`, còn ba node GKE chỉ cần pull. Hãy chọn role và scope IAM phù hợp. Nếu repository còn chứa `payments-api` nhạy cảm, có cần tách repository không?

**Gợi ý:** Writer cho CI, Reader cho node SA, repo-level binding; tách repo nếu nhu cầu quyền giữa các image khác nhau.

### Bài 3 — Debug `ImagePullBackOff`

Pod GKE báo `ErrImagePull`, nhưng Pod đã được gắn Kubernetes ServiceAccount có quyền gọi Cloud Storage. Giải thích vì sao Pod vẫn không pull được image từ repo ở project khác. Lập danh sách các bước xác minh quyền **node service account**, URI, scopes và network.

### Bài 4 — Cloud Run cross-project

Cloud Run tại project `retail-prod` tham chiếu image trong repo thuộc `platform-images`. Nêu vai trò của **deployer**, **Cloud Run service agent** và **runtime service account**. Principal nào thường phải được cấp Reader trên source repository, và vì sao không đủ nếu chỉ cấp Reader cho runtime SA?

### Bài 5 — Tag hay digest?

Một pipeline đã push tag `v1.0.0`; tuần sau một pipeline khác push nội dung mới vào cùng tag. Những deployment nào có thể thay đổi khi pull/redeploy theo tag, và deployment pin digest có gì khác? Hãy đề xuất quy tắc release và rollback.

### Bài 6 — Khắc phục lỗi 403

Một developer đã chạy:

~~~bash
gcloud auth configure-docker asia-southeast1-docker.pkg.dev
docker push asia-southeast1-docker.pkg.dev/retail-lab/retail-containers/orders-api:v1.0.0
~~~

Lệnh push báo `PERMISSION_DENIED`. Hãy nêu trình tự kiểm tra danh tính gcloud, Docker config/user, project/repo, IAM policy và các role hiệu lực. Vì sao không cần cấp `roles/artifactregistry.admin` để sửa vấn đề này nếu chỉ thiếu quyền Writer?

### Bài 7 — Kiểm soát image có secret

Một developer đã `COPY .env /app/.env` vào Dockerfile rồi xóa file trong layer tiếp theo, image đã được push. Có thể coi bí mật đã biến mất khỏi image không? Hãy đề xuất quy trình thay khóa, tạo lại image sạch, kiểm tra layer, chặn build sai và audit ai đã pull.

### Bài 8 — Chọn nơi lưu và ước lượng chi phí

GKE cluster ở Singapore, Cloud Run production ở châu Âu, CI ở một vùng khác. Bạn chọn một repository hay nhiều repository? Cần cân nhắc **location, data residency, transfer cost, IAM, tốc độ pull và yêu cầu kiểm soát phát hành** như thế nào?

### Bài 9 — Dọn image cũ

Đội hạ tầng có 300 image versions, muốn xóa những bản cũ hơn 60 ngày. Hãy mô tả cách xác định digests còn được GKE/Cloud Run sử dụng, keep rules cho rollback, review/dry-run khi được hỗ trợ và quy trình phê duyệt trước khi bật cleanup.

## 16. Checklist production

| Hạng mục | Điều cần đạt |
| --- | --- |
| **Repository** | Standard Docker repo đúng project/location, có owner và tài liệu định danh. |
| **Image naming** | URI có location/project/repository/image rõ ràng, tag/version theo quy ước. |
| **Digest** | Ghi digest thật sau push; production triển khai theo digest khi phù hợp. |
| **Build** | Test, base image đã duyệt, không nhúng credentials, architecture đúng. |
| **Publisher identity** | CI dùng credentials ngắn hạn, Writer trên repo cần thiết, không Admin rộng. |
| **Pull identities** | GKE node SA, Cloud Run service agent/deployer, VM principal đúng với từng mô hình. |
| **Cross-project IAM** | Repository nguồn cấp Reader đúng principal của project tiêu thụ. |
| **Networking** | DNS/TCP 443 tới registry; VPC egress/Private Google Access/NAT theo topology hỗ trợ. |
| **Runtime identity** | Quyền gọi Cloud SQL/Storage/secrets tách khỏi quyền pull image. |
| **Security gate** | Vulnerability scan, provenance/SBOM/signature/policy theo mức bảo mật. |
| **Release management** | Staging kiểm thử, approval, ghi digest/commit, rollback đã diễn tập. |
| **Tag/cleanup policy** | Không ghi đè tag release ngoài chủ đích, giữ digests đang dùng. |
| **Audit** | Theo dõi thay IAM, push/delete, policy và danh tính deployer. |
| **Observability** | Có cảnh báo pull/deploy failure, runtime startup, 5xx và SLO. |
| **Cost** | Dự toán storage/layers/transfer/build/scanning, giám sát Billing. |

## 17. Tài liệu chính thức và ghi nhớ

Các định dạng repository, khả năng hỗ trợ theo location, danh tính service agent và quy định IAM có thể thay đổi. Khi triển khai trên Google Cloud, đối chiếu:

- [Artifact Registry overview](https://cloud.google.com/artifact-registry/docs/overview)
- [Repository types and formats](https://cloud.google.com/artifact-registry/docs/repositories)
- [Create a Docker repository](https://cloud.google.com/artifact-registry/docs/repositories/create-repos)
- [Configure authentication for Docker](https://cloud.google.com/artifact-registry/docs/docker/authentication)
- [Push and pull Docker images](https://cloud.google.com/artifact-registry/docs/docker/pushing-and-pulling)
- [Control access with IAM](https://cloud.google.com/artifact-registry/docs/access-control)
- [Artifact Registry cleanup policies](https://cloud.google.com/artifact-registry/docs/repositories/cleanup-policy)
- [Deploy images to Cloud Run](https://cloud.google.com/run/docs/deploying)
- [GKE and Artifact Registry image pulling](https://cloud.google.com/artifact-registry/docs/integrate-gke)
- [Vulnerability scanning in Artifact Registry](https://cloud.google.com/artifact-analysis/docs/on-demand-scanning-overview)
- [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing)
- [gcloud artifacts reference](https://cloud.google.com/sdk/gcloud/reference/artifacts)

**Điểm cần nhớ:** Artifact Registry quản lý **nơi lưu và phân phối image**; Docker credentials xác định **ai đang yêu cầu truy cập**; IAM quyết định **được pull, push hay quản trị repository**; nền tảng GKE/Cloud Run/Compute Engine quyết định **ai thực sự tải image và chạy nó**. Khi kết hợp đúng URI, IAM, danh tính runtime, mạng, digest và quy trình CI/CD, nhóm có thể phát hành một container image đã kiểm chứng tới nhiều môi trường mà vẫn giữ được khả năng audit, rollback, bảo mật và kiểm soát chi phí.
