# Triển khai từ source code và từ container image trên Cloud Run

> **Chương:** Cloud Run  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Cloud Run cho phép triển khai một ứng dụng HTTP vào môi trường chạy container được Google Cloud quản lý, không phải tự vận hành máy ảo hoặc Kubernetes node. Có hai cách phổ biến: **triển khai trực tiếp thư mục mã nguồn** bằng **gcloud run deploy --source**, hoặc **triển khai container image có sẵn** bằng **gcloud run deploy --image**. Cả hai đều tạo **Cloud Run service/revision**, nhưng khác trách nhiệm build, định danh artifact và cách tích hợp CI/CD.

Bài học dùng cùng một ứng dụng Python Flask nhỏ để thực hành hai đường triển khai; cách tư duy áp dụng tương tự cho Java (Maven/Gradle, Spring Boot), Node.js và các runtime được hỗ trợ. Các ví dụ giới hạn trong project lab được cấp quyền, không tạo hạ tầng thật khi chỉ đọc tài liệu.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích luồng **source → Cloud Build/buildpacks hoặc Dockerfile → Artifact Registry → Cloud Run** và luồng **image → Cloud Run**.
2. Chuẩn bị API, project, region, danh tính và quyền IAM cần thiết cho từng đường.
3. Viết ứng dụng đáp ứng **container runtime contract**, nghe trên **0.0.0.0** và cổng **PORT**.
4. Triển khai source và image, kiểm tra revision, URL, logs, IAM và traffic.
5. Chọn cách triển khai theo nhu cầu kiểm soát build, tính tái tạo, chuỗi cung ứng phần mềm và CI/CD.
6. Phát hiện lỗi build, image pull, port, health, 401/403 và điều tra bằng gcloud/Cloud Logging.
7. Ước lượng các nguồn chi phí, thiết lập guardrails và dọn tài nguyên lab an toàn.

## 1. Khái niệm và kiến trúc

Cloud Run **service** là endpoint có thể phục vụ HTTP/HTTPS/gRPC theo cấu hình. Mỗi lần deploy image mới hoặc thay revision configuration tạo một **revision bất biến**; traffic có thể được chia giữa những revision còn tồn tại. Cloud Run tự quản lý số container instances theo lưu lượng và các thiết lập autoscaling.

~~~mermaid
flowchart TB
    SRC["Mã nguồn: main.py + requirements.txt"] --> BUILD["Cloud Build\nBuildpacks hoặc Dockerfile"]
    BUILD --> AR["Artifact Registry\nContainer image"]
    CUSTOM["CI / Docker build\nImage đã kiểm tra"] --> AR
    AR --> RUN["Cloud Run service\nImmutable revisions"]
    RUN --> ROUTE["Traffic routing\n100% hoặc split"]
    ROUTE --> USER["HTTP client"]
~~~

### 1.1. Hai cách triển khai

| Tiêu chí | **Deploy từ source** | **Deploy từ image** |
|---|---|---|
| Lệnh | **gcloud run deploy SERVICE --source .** | **gcloud run deploy SERVICE --image IMAGE_URL** |
| Đầu vào | Source directory | Image reference từ registry |
| Ai build? | Cloud Run điều phối **Cloud Build** (mặc định) | CI/CD, Docker hoặc Cloud Build đã build trước |
| Cách tạo image | Buildpacks nếu không có Dockerfile; Dockerfile nếu có | Theo Dockerfile/build pipeline do đội kiểm soát |
| Artifact Registry | Dùng để lưu image được build, có thể tự tạo repository nguồn | Image phải tồn tại/truy cập được trong registry hỗ trợ |
| Mức tùy biến | Nhanh, ít bước nhưng giới hạn cấu hình build tiện ích | Chủ động test, cache, provenance, SBOM, đa môi trường |
| Phù hợp | Prototype, dev, ứng dụng đơn giản | Production CI/CD, artifact promotion, release cần kiểm toán |

**Điểm then chốt:** source deploy **vẫn tạo image**, không có nghĩa Cloud Run chạy trực tiếp source files mà không cần môi trường container. Tài liệu này xét chế độ **deploy from source with build** thông thường; tùy chọn **prebuilt source không qua Cloud Build** hiện là tính năng Preview riêng và không được nhầm với luồng mặc định.

### 1.2. Khi source directory có Dockerfile

- **Có Dockerfile:** deploy source dùng **Dockerfile** trong source directory để build.
- **Không có Dockerfile:** buildpacks dò ngôn ngữ, giải dependencies và tạo container image theo khả năng hỗ trợ.
- Vì vậy việc bổ sung Dockerfile có thể làm **thay đổi cách build** dù lệnh deploy --source vẫn giữ nguyên.
- Source deploy thường dùng repository **cloud-run-source-deploy** trong region nếu repository đó chưa tồn tại; Cloud Run có thể đề nghị/tự tạo nó tùy quyền và cấu hình.

Artifact Registry là nơi lưu image, còn Cloud Run import image khi triển khai và giữ bản được phục vụ theo cơ chế của revision. Việc một service đã chạy không chứng minh repository/image cũ có thể xóa mà không ảnh hưởng **lần deploy tiếp theo, rollback ngoài Cloud Run hoặc kiểm toán**.

### 1.3. Service, revision, instance và URL

| Khái niệm | Ý nghĩa |
|---|---|
| **Service** | Tên và cấu hình chung, URL ổn định cho client |
| **Revision** | Bản snapshot bất biến của container và revision configuration |
| **Instance** | Container instance phục vụ request, có thể được tạo/hủy khi autoscale |
| **Traffic** | Phần trăm request được hướng tới các revisions |
| **Service identity** | Service account mà code trong container dùng khi gọi Google APIs |
| **Deployer** | Người/service account thực hiện deploy; không nhất thiết là runtime identity |
| **Build identity** | Service account dùng để build source/upload image; quyền riêng với runtime |

Đừng dựa vào filesystem local của một instance để lưu dữ liệu nghiệp vụ bền vững: instance có thể bị thay hoặc scale về zero. Sử dụng Cloud SQL, Cloud Storage, Firestore hoặc dịch vụ phù hợp và thiết kế retry/idempotency khi cần.

## 2. Container runtime contract: điều kiện để Cloud Run chạy được

Ứng dụng service cần **nghe HTTP request trên 0.0.0.0 và cổng được cung cấp qua biến PORT** (mặc định thường 8080). Nghe trên **127.0.0.1** trong container có thể khiến Cloud Run không kết nối được.

- Container ingress phải start và lắng nghe cổng tương ứng trong thời gian khởi động được phép.
- Cloud Run kết thúc TLS ở phía nền tảng; code thường nhận HTTP tới container.
- Response phải hoàn tất trong request timeout đã cấu hình.
- Với Cloud Run **service**, HTTP listener là cần thiết; Cloud Run **job** xử lý tác vụ đến kết thúc và không cần HTTP listener.
- Container có thể chạy nhiều instances; dữ liệu trong RAM/cache local và socket kết nối không mặc nhiên được chia sẻ.
- Tham số PORT, CPU, memory, concurrency, timeout và health probes phải phù hợp với ứng dụng thực.

### 2.1. Ứng dụng lab duy nhất cho hai luồng

Tạo một thư mục dự án học tập **cloud-run-hello/** ở môi trường thực hành riêng của người học (không phải trong repository bài học đang được worker cập nhật). Ban đầu có hai file, **chưa tạo Dockerfile**.

**main.py**

~~~python
import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.get("/")
def hello():
    return jsonify(
        message="Xin chao tu Cloud Run",
        release=os.getenv("RELEASE", "dev"),
        revision=os.getenv("K_REVISION", "local"),
    )

@app.get("/healthz")
def health():
    return "ok", 200

if __name__ == "__main__":
    # Chỉ dùng server phát triển khi chạy python main.py.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
~~~

**requirements.txt**

~~~text
Flask==3.1.2
gunicorn==23.0.0
~~~

Lệnh local (giả sử Python 3, virtual environment và dependencies đã được cài đúng):

~~~bash
python -m pip install -r requirements.txt
PORT=8080 RELEASE=local python main.py
# Terminal khác: curl -fsS http://127.0.0.1:8080/healthz
~~~

Flask development server chỉ để thử local. Khi triển khai source Python, buildpack có thể dùng **Gunicorn** làm production HTTP server; nếu cần tùy biến start command, có thể dùng **Procfile** hoặc cấu hình buildpack, thay vì bật debug=True trong production.

**Đối với Java:** Spring Boot có thể chạy sau buildpacks/Dockerfile khi đã cấu hình Maven/Gradle và plugin đóng gói phù hợp; đặt server port theo biến môi trường Cloud Run (ví dụ cấu hình **server.port** đọc PORT), health endpoints chính xác và JVM memory phù hợp. Không copy nguyên cú pháp Flask sang Java.

## 3. Preflight: project, API, IAM, region

Đây là bước cần làm **trước mọi lệnh deploy**, đặc biệt khi người vận hành có nhiều project.

### 3.1. Chỉ đọc: xác minh ngữ cảnh

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
REGION="asia-southeast1"
SRC_SERVICE="hello-src-lab"
IMG_SERVICE="hello-img-lab"
REPOSITORY="cloud-run-images-lab"

gcloud auth list
gcloud config list
gcloud projects describe "$PROJECT_ID"

# Các API hiện đang bật trong project.
gcloud services list --enabled --project="$PROJECT_ID" \
  --filter="name:(run.googleapis.com OR cloudbuild.googleapis.com OR artifactregistry.googleapis.com)"

# Các Cloud Run services đã tồn tại trong region.
gcloud run services list --project="$PROJECT_ID" --region="$REGION"
~~~

Project phải có **billing** và API phù hợp được enable: **Cloud Run Admin API**, **Cloud Build API** với source/Cloud Build pipeline, **Artifact Registry API** khi thao tác repository/images. Việc bật API là thay đổi project và cần quyền **serviceusage.services.enable**; không tự bật ở production để thử.

### 3.2. Quyền theo từng vai trò

| Chủ thể | Quyền điển hình | Tại sao |
|---|---|---|
| Người deploy source | **roles/run.sourceDeveloper**, **roles/serviceusage.serviceUsageConsumer**, **roles/iam.serviceAccountUser** trên service identity | Được build/deploy từ source |
| Cloud Build service account | **roles/run.builder** trên project theo hướng dẫn source deploy; thêm quyền theo pipeline cụ thể | Build và lưu image |
| Người deploy image | **roles/run.developer**, **roles/iam.serviceAccountUser** và **roles/artifactregistry.reader** trên repo image | Deploy image đã tồn tại |
| Build CI đẩy image | Artifact Registry **Writer** trên repository, cùng quyền Cloud Build cần thiết | Push image, không cần Cloud Run Admin |
| Cloud Run service agent | Quyền truy cập image của project khác khi cross-project | Import image trong quá trình deploy |
| Runtime service identity | Chỉ quyền GCP APIs ứng dụng thật sự cần | Không dùng Admin chỉ để chạy HTTP hello world |
| Client gọi service riêng tư | **roles/run.invoker** hoặc quyền tương đương và ID token hợp lệ | Gọi HTTP endpoint đã bật IAM authentication |

Các vai trò thực tế có thể phụ thuộc tổ chức, loại service account dùng build và chính sách bảo mật. **Build identity không phải runtime identity**. Nếu image nằm ở project khác, thường cần cấp Reader cho **Cloud Run service agent của project chạy service** và deployer trên repository nguồn; không chỉ cấp cho runtime service account rồi cho rằng pull sẽ thành công.

### 3.3. Bật API — thay đổi có điều kiện

~~~bash
# THAY ĐỔI PROJECT — chỉ người có quyền và trong lab được phép.
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --project="$PROJECT_ID"
~~~

Đối với source deploy, quản trị viên phải kiểm tra **Cloud Build service account thực tế** và vai trò **Cloud Run Builder** của nó. Không cấp Owner để xử lý lỗi 403. Một số project/organization dùng build account riêng thay vì mặc định.

### 3.4. Phân biệt ingress và quyền gọi

- **--no-allow-unauthenticated** yêu cầu xác thực theo IAM đối với Cloud Run service.
- **--allow-unauthenticated** cho phép client không có principal Cloud Run IAM invoke khi cấu hình và organization policy cho phép; chỉ dùng khi **chủ ý cung cấp dịch vụ public**.
- **--ingress** kiểm soát nguồn/đường đi được phép vào service; không phải thay cho authentication.
- Với private service, người học có thể thử qua **gcloud run services proxy** hoặc **ID token** có quyền Invoker.

Lab này mặc định dùng **private service** để tránh vô tình công khai endpoint.

## 4. Lab A — Triển khai trực tiếp source code

**Điều kiện:** đang ở thư mục **cloud-run-hello/** có **main.py** và **requirements.txt**, **chưa có Dockerfile**; các biến **PROJECT_ID, REGION, SRC_SERVICE** đã đặt như phần 3. Các lệnh deploy tạo tài nguyên và phát sinh chi phí, chỉ thực hiện trong lab được cho phép.

### 4.1. Từ source tới revision

~~~mermaid
sequenceDiagram
    participant DEV as Developer CLI
    participant CB as Cloud Build / Buildpacks
    participant AR as Artifact Registry
    participant CR as Cloud Run
    DEV->>CR: gcloud run deploy --source .
    CR->>CB: Yêu cầu build source
    CB->>CB: Detect Python, install dependencies
    CB->>AR: Push container image
    AR-->>CR: Image reference
    CR->>CR: Tạo immutable revision
    CR-->>DEV: Service URL và trạng thái deploy
~~~

~~~bash
# THAY ĐỔI HẠ TẦNG — chỉ chạy trong source directory của lab.
gcloud run deploy "$SRC_SERVICE" \
  --source . \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --no-allow-unauthenticated

# CHỈ ĐỌC — kiểm tra đã có URL, image/revision.
gcloud run services describe "$SRC_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(metadata.name,status.url,status.latestReadyRevisionName,spec.template)"
~~~

Lệnh **--source .** tự điều phối build bằng Cloud Build; **không cần** chạy docker build hoặc gcloud builds submit trước. Với Python app không có Dockerfile, buildpacks nhận diện requirements.txt và có thể dùng Gunicorn với **main:app** làm entrypoint. Dòng **app = Flask(__name__)** trong ví dụ là đối tượng WSGI mà Gunicorn cần.

Cloud Run dùng Artifact Registry để lưu image. Repository nguồn có tên thường là **cloud-run-source-deploy** ở region triển khai, có thể được tạo lần đầu. Đừng xóa repository này chỉ vì đã deploy xong, vì có thể có nhiều source builds hoặc pipeline khác sử dụng nó.

### 4.2. Đọc kết quả và kiểm thử private service

~~~bash
# CHỈ ĐỌC: URL và revision mới nhất.
gcloud run services describe "$SRC_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="value(status.url)"

gcloud run revisions list \
  --service="$SRC_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

Để thử private service qua tunnel có authentication, ở terminal 1:

~~~bash
# Lệnh chạy tại chỗ, cần quyền Invoke; dùng Linux/macOS/WSL.
gcloud run services proxy "$SRC_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --port=8080
~~~

Ở terminal 2:

~~~bash
curl -i http://127.0.0.1:8080/
curl -fsS http://127.0.0.1:8080/healthz
~~~

**Kỳ vọng:** HTTP 200, JSON có **message**, **release=dev** và **revision** thực tế; **/healthz** trả **ok**. Proxy chỉ dành cho developer có danh tính/quyền phù hợp, không tự biến service thành public.

Có thể gọi trực tiếp bằng một **ID token** phát sinh từ gcloud khi thử dev:

~~~bash
SERVICE_URL="$(gcloud run services describe "$SRC_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format='value(status.url)')"

curl -i \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$SERVICE_URL/"
~~~

ID token cho user do gcloud sinh phù hợp để kiểm thử theo tài liệu, nhưng với **service-to-service production** phải dùng ID token có **audience** phù hợp, được cấp cho service account có quyền Invoker. Không đặt access token thay ID token vào header rồi kỳ vọng Cloud Run IAM chấp nhận.

### 4.3. Thay source, deploy lần hai

Sửa message trong **main.py** thành một thông điệp phiên bản 2, lưu lại rồi chạy:

~~~bash
# THAY ĐỔI: build mới, image mới, tạo revision mới.
gcloud run deploy "$SRC_SERVICE" \
  --source . \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --no-allow-unauthenticated

# CHỈ ĐỌC.
gcloud run revisions list \
  --service="$SRC_SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

Mỗi lần deploy tạo một revision mới với artifact và cấu hình tại thời điểm đó. Đổi code **không tự kích hoạt triển khai** nếu chưa có CI/CD trigger hoặc lệnh deploy. Bản mới được route traffic theo thiết lập deploy/traffic của service; cần **kiểm tra traffic allocation**, không mặc định mọi deploy đều chuyển 100% nếu service đang áp dụng traffic splitting.

## 5. Lab B — Build container image trước rồi triển khai

Luồng này cho phép **tách build khỏi deploy**: CI tạo image, chạy test/scan và publish một artifact có digest rõ ràng; Cloud Run triển khai chính artifact đó.

### 5.1. Thêm Dockerfile sau Lab A

Đặt tệp **Dockerfile** trong cùng source directory với main.py và requirements.txt:

~~~dockerfile
# Demo: production cần pin base image theo digest và quét CVE.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py ./

# User số không đặc quyền; ứng dụng không cần ghi vào /app.
USER 65532
EXPOSE 8080

# Cloud Run cấp PORT; shell chỉ mở rộng biến tại thời điểm container start.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 main:app"]
~~~

**Cần hiểu:**

- **EXPOSE 8080** là metadata của image, không tự bảo đảm server lắng nghe cổng.
- **0.0.0.0:$PORT** đáp ứng runtime contract; nếu chạy local, cần cấp biến PORT.
- **USER 65532** giảm quyền của process; image phải hỗ trợ chạy mà không cần root.
- Base image tag và dependencies cần scan/pin trong production; Dockerfile này dành cho lab.
- Dùng **.dockerignore** để loại **.git, .env, credentials, virtualenv, cache và file không cần** khỏi build context. Không ghi secret vào Dockerfile ENV/ARG hoặc image layers.

### 5.2. Tạo standard Docker repository

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
REGION="asia-southeast1"
REPOSITORY="cloud-run-images-lab"
IMG_SERVICE="hello-img-lab"

# THAY ĐỔI: chỉ khi repository chưa tồn tại và có quyền.
gcloud artifacts repositories create "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Cloud Run image deployment lab"

# CHỈ ĐỌC: xác nhận repo đúng format và location.
gcloud artifacts repositories describe "$REPOSITORY" \
  --project="$PROJECT_ID" --location="$REGION"
~~~

Nếu repo đã tồn tại, không tạo lại. Repository nên nằm cùng region runtime khi phù hợp để giảm độ trễ/pull transfer và đáp ứng data residency.

### 5.3. Build, tag và push

~~~bash
IMAGE_BASE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/hello-api"
IMAGE_URL="$IMAGE_BASE:1.0.0"

# Cập nhật Docker credential helper trên máy build (không cấp IAM).
gcloud auth configure-docker "$REGION-docker.pkg.dev"

# THAY ĐỔI local: build Docker image từ Dockerfile.
docker build -t "$IMAGE_URL" .

# THAY ĐỔI Artifact Registry: push image.
docker push "$IMAGE_URL"

# CHỈ ĐỌC metadata image/digest.
gcloud artifacts docker images list \
  "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY" \
  --include-tags
~~~

CI phải có quyền **Artifact Registry Writer** trên repo đích. Nếu máy không có Docker daemon, có thể dùng Cloud Build từ source directory (cần quyền build và push phù hợp):

~~~bash
# THAY ĐỔI: build và push trên Cloud Build.
gcloud builds submit . \
  --tag="$IMAGE_URL" \
  --project="$PROJECT_ID"
~~~

Chọn **một** đường build, không nhất thiết chạy cả Docker và Cloud Build. Ghi lại **commit SHA, build ID, image digest, scan/SBOM** cho release; tag chỉ là nhãn thuận tiện.

### 5.4. Chạy image local trước khi deploy

~~~bash
# THAY ĐỔI local: chạy container image trong Docker.
docker run --rm -p 8080:8080 -e PORT=8080 \
  -e RELEASE=image-lab "$IMAGE_URL"

# Terminal khác, CHỈ ĐỌC:
curl -fsS http://127.0.0.1:8080/
curl -fsS http://127.0.0.1:8080/healthz
~~~

Nếu local không trả HTTP 200, kiểm tra app entrypoint, image architecture, port và dependencies trước khi deploy. Với Apple Silicon hoặc CI dùng ARM64, cần build một image Linux architecture được Cloud Run hỗ trợ (theo image manifest và runtime contract), không mặc định image local nào cũng chạy được trên cloud.

### 5.5. Deploy image lên Cloud Run

~~~bash
# THAY ĐỔI: image đã push phải tồn tại và deployer có quyền Reader.
gcloud run deploy "$IMG_SERVICE" \
  --image="$IMAGE_URL" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --no-allow-unauthenticated \
  --set-env-vars="RELEASE=1.0.0"

# CHỈ ĐỌC: image thực tế của revision mới.
gcloud run services describe "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(status.url,status.latestReadyRevisionName,spec.template)"
~~~

**Nên deploy bằng digest trong CI production.** Lấy digest thật từ output push/Artifact Registry, rồi thay image reference thành:

~~~text
asia-southeast1-docker.pkg.dev/PROJECT_ID/REPOSITORY/hello-api@sha256:FULL_DIGEST
~~~

Nếu deploy bằng tag, Cloud Run **resolve tag sang digest tại thời điểm deploy** và revision đó phục vụ bản image cụ thể, không tự đổi chỉ vì tag về sau bị push lại. Tuy vậy, để pipeline audit và rollback dễ kiểm chứng, dùng digest đầy đủ trong manifest/deployment records.

### 5.6. Quy trình image khi cần CI/CD

~~~mermaid
flowchart LR
    SRC["Git commit"] --> TEST["Lint + Unit/Integration tests"]
    TEST --> BLD["Build OCI image"]
    BLD --> AR["Artifact Registry: image@digest"]
    AR --> SEC["CVE/SBOM/provenance checks"]
    SEC --> STAGE["Deploy staging by digest"]
    STAGE --> OK{"Smoke test / SLO PASS?"}
    OK -- "Không" --> FIX["Chặn promotion"]
    OK -- "Có" --> PROD["Promote same digest to production"]
~~~

Cần tách danh tính **CI builder**, **deployer**, **Cloud Run service agent** và **runtime service account**. Không cấp Project Editor/Owner cho tất cả chỉ vì pipeline phải vừa build vừa deploy.

## 6. So sánh kết quả thực tế của hai lab

| Quan sát | Source deploy | Image deploy |
|---|---|---|
| Input mà deployer cần | Source directory và build permissions | Image URL/digest và deploy permissions |
| Dockerfile | Không bắt buộc; nếu có thì được dùng | Pipeline build có thể dùng Dockerfile |
| Cloud Build được gọi ở deploy? | Có với luồng source-with-build mặc định | Không: deploy chỉ dùng image đã build |
| Artifact Registry | Có image đầu ra; repo nguồn có thể tự tạo | Repo image được quản lý riêng |
| Thay source có tạo revision ngay? | Không, phải deploy/CI trigger | Không, phải build/push/deploy theo pipeline |
| Immutable revision | Có | Có |
| Kiểm soát SBOM, signer, promotion | Có thể bổ sung build pipeline | Thuận tiện hơn khi CI tách build và deploy |
| Khả năng bảo vệ service bằng IAM/ingress | Như nhau | Như nhau |
| Runtime scaling, network, logs | Như nhau ở cấu hình tương đương | Như nhau ở cấu hình tương đương |

**Quy tắc chọn:** dùng **--source** khi ưu tiên nhanh và build đơn giản; dùng **--image** khi cần artifact đã được test/scan, tái sử dụng qua nhiều môi trường, pin digest và phân quyền build/deploy rõ ràng. Không cần coi đây là hai “nền tảng” khác nhau: cuối cùng đều triển khai Cloud Run revisions từ container images.

## 7. Revision, traffic splitting và rollback

Mỗi lần deploy một image/cấu hình revision mới, Cloud Run tạo một **revision bất biến**. Điều này cho phép chuyển traffic dần từ bản cũ sang bản mới mà không phải overwrite image đang chạy.

### 7.1. Xem revisions và traffic

~~~bash
# CHỈ ĐỌC.
gcloud run revisions list \
  --service="$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION"

gcloud run services describe "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(status.traffic,status.latestReadyRevisionName,status.url)"
~~~

Khi kiểm tra một thay đổi, phải biết **revision nào đã Ready** và **revision nào đang nhận traffic**. Một revision Ready không có nghĩa đang phục vụ 100% request; service có thể đang giữ traffic ở bản cũ hoặc áp dụng canary split.

### 7.2. Rollback bằng traffic, không bằng push đè tag

Giả sử danh sách trả hai revision đã được kiểm chứng: **hello-img-lab-old** và **hello-img-lab-new** (tên minh họa; phải thay bằng tên revision thật).

~~~bash
# THAY ĐỔI TRAFFIC — chỉ trong service lab và khi đã chọn đúng revision.
gcloud run services update-traffic "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --to-revisions="hello-img-lab-old=100"

# CHỈ ĐỌC — xác minh traffic sau rollback.
gcloud run services describe "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(status.traffic)"
~~~

Rollback này **chuyển traffic về revision cũ**, không rollback tự động schema database, Secret Manager versions, dữ liệu nghiệp vụ hoặc các Google APIs mà service gọi. Nếu môi trường có migration database, cần chiến lược backward-compatible riêng.

### 7.3. Canary 10% traffic

~~~bash
# THAY ĐỔI — chỉ sau khi cả hai revisions có thật và đã smoke test.
gcloud run services update-traffic "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --to-revisions="hello-img-lab-old=90,hello-img-lab-new=10"
~~~

Theo dõi error rate, latency, request count của **từng revision**. Canary ít traffic có thể chưa đủ mẫu đánh giá; cần traffic/SLO thích hợp. Nếu mọi kiểm tra đạt, có thể dồn 100% vào revision đã duyệt. Lệnh:

~~~bash
# THAY ĐỔI: route 100% vào revision mới nhất và những lần deploy
# mới sau này theo chính sách 'to-latest'; không dùng nếu cần fixed split.
gcloud run services update-traffic "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --to-latest
~~~

**Phân biệt:** tự động theo latest khác với pin một revision name cụ thể. CI/GitOps cần biết đang quản lý traffic theo cách nào để không ghi đè canary/rollback của SRE.

## 8. Bảo mật khi triển khai và khi chạy

### 8.1. Ba ranh giới quyền

~~~mermaid
flowchart LR
    DEV["Deployer IAM"] -->|"Tạo revision"| RUN["Cloud Run"]
    BUILD["Build SA + registry Writer"] -->|"Đẩy image"| AR["Artifact Registry"]
    RUN -->|"Service identity"| API["Cloud SQL / Storage / Pub/Sub"]
    CALLER["Invoker ID token"] -->|"HTTP request"| RUN
    AR -->|"Image access"| RUN
~~~

- **Build permission** cho phép tạo và publish image, không tự trao quyền gọi Cloud SQL.
- **Deploy permission** cho phép thay Cloud Run revision/config, không nhất thiết được gọi API nghiệp vụ.
- **Runtime service identity** cần vai trò tối thiểu cho Google APIs thực sự được code sử dụng.
- **Invoke permission** kiểm soát client gọi Cloud Run private service. Với service-to-service, dùng **ID token có audience là service URL hoặc custom audience phù hợp**, không dùng access token của Google APIs.

Trong cross-project image deploy, Cloud Run **service agent** của runtime project có thể cần **roles/artifactregistry.reader** trên repository nguồn bên cạnh quyền đọc của deployer. Đừng đặt repository public để khắc phục lỗi 403.

### 8.2. Environment variables và secrets

Biến cấu hình không bí mật như **RELEASE**, log level hoặc feature flag có thể được truyền bằng **--set-env-vars** khi deploy, nhưng thao tác này thay thế tập biến cấu hình theo semantics của cờ; khi cập nhật từng biến có thể dùng cờ **--update-env-vars** theo tài liệu.

**Không dùng environment variables hay Dockerfile để nhúng service account key hoặc password** dưới dạng plain text trong scripts/Git. Với credentials, ưu tiên **Cloud Secret Manager integration** (secret environment variable hoặc mounted volume) và cấp quyền **Secret Manager Secret Accessor** đúng secret cho runtime identity.

Không in danh sách env nếu có secrets ra logs/ticket. Thay đổi service account, secret references, CPU/memory hoặc timeout thường tạo revision mới; cần kế hoạch rollout giống thay image.

### 8.3. Ingress, TLS và mạng riêng

| Yêu cầu | Thiết kế phù hợp |
|---|---|
| API public | Ingress và IAM/public policy theo phê duyệt; auth ứng dụng, WAF/Cloud Armor qua LB khi cần |
| Private endpoint theo Cloud Run IAM | Require authentication; Invoker + ID token |
| Chỉ nhận qua internal VPC / load balancer | Cloud Run ingress settings và kiến trúc LB được hỗ trợ |
| Service gọi private database trong VPC | **Direct VPC egress** hoặc connector theo kiến trúc |
| Service gọi Cloud Storage/Google APIs | Runtime IAM + network route theo cấu hình |

**Ingress và IAM là hai lớp độc lập.** Ingress internal không mặc nhiên cho phép bất kỳ caller nào được truy cập nếu service còn yêu cầu Invoker. Ngược lại, cho phép public invocation không tự vượt qua ingress restrictions.

### 8.4. Container image và phát hành an toàn

Trong production:

1. Kiểm tra dependencies/base image và CVE.
2. Dùng version/digest bất biến, ghi commit SHA, build ID, SBOM/provenance.
3. Không lưu secret trong source, build context hoặc image layers.
4. Tách SA cho build, deploy và runtime.
5. Deploy image đã kiểm tra vào staging, smoke/load test rồi promote **cùng digest**.
6. Hạn chế quyền đổi traffic, delete revisions và chỉnh IAM.
7. Cấu hình Cloud Logging/Monitoring và giữ rollback window phù hợp.

## 9. Troubleshooting: xác định lỗi ở đúng tầng

| Triệu chứng | Tầng liên quan | Điều cần kiểm tra |
|---|---|---|
| Source build fail | Cloud Build/buildpack/Dockerfile | Build logs, runtime/dependencies, file bị ignore, Build SA |
| Lệnh --source báo permission denied | IAM/API | run.sourceDeveloper, run.builder, serviceUsage, SA user |
| Build image push 403 | Artifact Registry | Repo path/region, Writer IAM, Docker helper/Cloud Build SA |
| Deploy image không tìm thấy | Image registry | URL chính xác, tag/digest tồn tại, repo format và location |
| Cross-project image deploy 403 | Service agent/repo IAM | Reader trên repository nguồn cho principal cần thiết |
| Revision không Ready | Container startup | PORT, bind 0.0.0.0, startup errors, env/secret, memory |
| Service trả HTTP 401/403 | Invoke IAM hoặc app auth | ID token/audience, roles/run.invoker, ingress |
| HTTP 404 | Sai path hoặc URL/service | Service URL, route app, revision traffic |
| HTTP 503 | Instance startup/capacity/health | Revision status, logs, concurrency/max instances |
| HTTP 504 | Request timeout / dependency | Latency, downstream, timeout, worker behavior |
| App chỉ nghe 127.0.0.1 | Container runtime | Bind 0.0.0.0:$PORT |
| Local chạy, Cloud Run lỗi | Architecture/env/resource | Linux image, PORT, dependencies, memory, stdout logs |
| Deploy xong nhưng response cũ | Traffic/revision/cache | status.traffic, revision name, image digest, cache |
| Phí vẫn phát sinh khi ít request | min instances, build, registry, logs, egress | Billing SKU và service settings |

### 9.1. Các lệnh điều tra chỉ đọc

~~~bash
gcloud run services describe "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format=yaml

gcloud run revisions list \
  --service="$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION"

gcloud run services logs read "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --limit=50

gcloud artifacts docker images list \
  "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY" \
  --include-tags
~~~

**Phân biệt build logs với runtime logs.** Nếu Cloud Build thất bại trước deploy, Cloud Run revision có thể chưa được tạo; xem Cloud Build execution logs. Nếu deploy đã tạo revision nhưng startup lỗi, xem **Cloud Run revision/container logs** và error details. Tránh đưa access tokens, headers Authorization và secrets vào ticket.

### 9.2. Bốn bước xác minh lỗi port

1. Trong **Dockerfile/CMD**, entrypoint có khởi động server thật không?
2. Server có bind **0.0.0.0** thay vì **127.0.0.1** không?
3. Port server đọc từ **PORT**, có tương ứng port Cloud Run cấu hình không?
4. Có lỗi import/runtime, thiếu dependencies hoặc OOM trước khi server mở cổng không?

Không tăng memory vô điều kiện khi nguyên nhân chỉ là ứng dụng nghe sai port.

## 10. Scaling, độ tin cậy và chi phí

Cloud Run tự quản lý autoscaling; service có thể scale về zero khi không có request và không cấu hình minimum instances khác. Mỗi instance có CPU/memory/concurrency và request timeout, tác động tới latency lẫn hóa đơn.

| Thiết lập | Tác động |
|---|---|
| **Min instances** | Giữ instance sẵn sàng, giảm cold start nhưng có thể tăng chi phí |
| **Max instances** | Giới hạn quy mô để bảo vệ downstream/budget, nhưng có thể bị vượt ngắn hạn và tạo 429/503 khi hết capacity |
| **Concurrency** | Số requests đồng thời/instance; quá cao có thể làm Java thread/DB pool quá tải |
| **CPU / Memory** | Sizing theo profiling; thấp quá gây OOM/latency |
| **Request timeout** | Kiểm soát thời gian request; không thay cơ chế async job |
| **Billing setting** | Chi phí theo request/instance lifecycle tùy cấu hình hiện hành |
| **Region** | Latency, data residency, network transfer và available features |

### 10.1. Điều chỉnh cần có số liệu

Ví dụ trong một service có Java API, 1 instance với concurrency 80 có thể làm tăng đồng thời DB queries, trong khi đặt concurrency=1 có thể tạo nhiều instances với phí và cold starts cao hơn. Không chọn một con số “tối ưu chung”; đo **p95/p99 latency, CPU/memory usage, số DB connections, 5xx, cold starts và cost per successful request**.

**Cảnh báo về max instances:** đây là guardrail về scale, **không phải hard cap của hóa đơn**. Cloud Run có thể vượt giới hạn trong một số giai đoạn ngắn theo cơ chế autoscaling; build/storage/logging/egress cũng có thể tính phí riêng.

### 10.2. Những nguồn chi phí khi so sánh hai luồng

| Khoản | Source deploy | Image deploy |
|---|---|---|
| Cloud Build | Có trong luồng build mặc định | Có nếu pipeline dùng Cloud Build |
| Artifact Registry | Lưu image được sinh | Lưu image đã build, có thể chia sẻ nhiều services |
| Cloud Run compute/requests | Theo cấu hình service/revision | Theo cấu hình service/revision |
| Network egress | Theo luồng request/downstream | Tương tự |
| Logs/metrics | Theo sản lượng/retention | Tương tự |
| Secret Manager/KMS/Cloud SQL | Theo dịch vụ tích hợp | Tương tự |

Không so sánh phí chỉ theo số lần deploy. Hãy dùng **Cloud Billing Reports** theo service/SKU và thời gian, tính cost/request hoặc cost/job trên workload tương đương. Source deploy có thể tiện hơn nhưng không đồng nghĩa runtime rẻ hơn.

## 11. Case study: từ Java source đến phát hành theo image digest

**Bối cảnh:** nhóm thương mại điện tử có API **checkout** viết bằng Java, dự định dùng Cloud Run để giảm vận hành VM/GKE cho một service HTTP stateless.

### 11.1. Giai đoạn phát triển

Developer dùng **gcloud run deploy --source .** trên project dev. Buildpacks phát hiện Maven/Gradle hoặc Dockerfile nếu có; Cloud Build tạo image và Cloud Run tạo revision. Nhóm kiểm tra:

- App nghe đúng PORT và health endpoint trả HTTP 200.
- Runtime service account chỉ có quyền trên tài nguyên dev cần dùng.
- Không đưa DB password vào source image hoặc biến được commit trong Git.
- Cloud Logging hiện exception/latency; scaling đáp ứng traffic.

### 11.2. Giai đoạn production

CI dựng image từ commit đã merge, chạy test và vulnerability scans, ghi digest cùng build provenance rồi push vào Artifact Registry. Pipeline tách biệt triển khai tới staging, sau đó **deploy cùng digest** sang production bằng **--image**.

Đội SRE chia traffic 10% cho revision mới, theo dõi p95, 5xx, số DB connections. Nếu metrics vượt SLO, dùng **update-traffic --to-revisions** để quay về revision cũ. Dữ liệu đơn hàng vẫn ở Cloud SQL/Firestore hoặc nơi bền vững nên rollback không phụ thuộc filesystem container.

### 11.3. Quyết định kiến trúc

| Quyết định | Lý do |
|---|---|
| Source deploy cho dev | Nhanh, không cần quản lý Docker local |
| Image deploy cho prod | Cùng digest đã test/scan, dễ audit/rollback |
| Private service + service-to-service ID token | Không mở public endpoint nếu không có yêu cầu |
| Runtime SA riêng | Phân quyền GCP APIs tối thiểu |
| Secrets trong Secret Manager | Tách credential khỏi image và source |
| Traffic split có quan sát SLO | Giảm rủi ro release |
| Cloud Billing/Budget alerts | Kiểm soát phí build, registry và runtime |

Không bắt buộc mọi tổ chức dùng source ở dev và image ở prod; điều quan trọng là chọn **một quy trình có thể tái tạo và kiểm toán** phù hợp yêu cầu. Nếu source deploy được tích hợp CI với kiểm soát provenance, nó vẫn có thể phục vụ production.

## 12. Dọn lab và bài tập

### 12.1. Dọn đúng tài nguyên đã tạo

Trước khi xóa, xác minh project, region, hai tên service và repository **đúng do người học sở hữu**, không có traffic hoặc pipeline khác đang dùng.

~~~bash
# CHỈ ĐỌC.
gcloud run services list --project="$PROJECT_ID" --region="$REGION"
gcloud artifacts repositories list \
  --project="$PROJECT_ID" --location="$REGION"
~~~

Chỉ khi được phép và đã xác nhận tài nguyên lab:

~~~bash
# XÓA TÀI NGUYÊN THẬT — chỉ với hai services của lab.
gcloud run services delete "$SRC_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION"

gcloud run services delete "$IMG_SERVICE" \
  --project="$PROJECT_ID" --region="$REGION"
~~~

Xóa service **không tự xóa** Artifact Registry images, Cloud Build logs, Cloud Logging data, reserved IP, Secret Manager hoặc dịch vụ khác. Repository **cloud-run-images-lab** chỉ xóa riêng khi chắc chắn nó được tạo riêng cho bài lab, không còn version/consumer cần giữ và có phê duyệt. **Không xóa cloud-run-source-deploy mặc định** vì có thể được dùng chung cho nhiều source deployments.

### 12.2. Câu hỏi trắc nghiệm nhanh

1. Khi source directory **không có Dockerfile**, lệnh deploy từ source mặc định dùng công cụ nào để tạo image?
2. Nếu source directory **có Dockerfile**, --source có bỏ qua Dockerfile không?
3. Dùng --image có yêu cầu Cloud Run tự build lại source không?
4. Service private gọi bằng curl cần loại token nào?
5. Revision đã deploy từ tag **:stable** có tự đổi image khi tag stable bị push đè không?
6. Vì sao chạy ứng dụng ở **127.0.0.1:8080** có thể thất bại trên Cloud Run?
7. Khi cần rollback một HTTP release, nên đổi traffic hay push đè tag?
8. Quyền **roles/run.invoker** có tự cho CI push image vào Artifact Registry không?
9. Vì sao min instances có thể tăng hóa đơn dù traffic gần bằng không?
10. Deploy code mới có tự rollback database schema hoặc Secret Manager version không?

**Đáp án:** (1) Cloud Build + buildpacks; (2) không, Dockerfile được dùng; (3) không; (4) ID token hợp lệ với quyền Invoker và audience phù hợp; (5) không, revision đã resolve digest; (6) phải nghe **0.0.0.0:$PORT**; (7) chuyển traffic về revision đã kiểm tra; (8) không; (9) giữ instance sẵn sàng; (10) không.

### 12.3. Bài tập thực hành có kiểm chứng

**Bài A — Source:** từ hai file Python lab, triển khai **hello-src-lab** private; ghi URL, latest Ready revision, response của **/healthz**, source build logs, nơi Artifact Registry lưu image.

**Bài B — Image:** thêm Dockerfile, build/push một tag **1.0.0**, ghi digest, triển khai **hello-img-lab** từ image. Chứng minh service chạy đúng digest đã push và so sánh thời gian/các bước với Lab A.

**Bài C — Rollback:** triển khai một version 2 với thông điệp mới, kiểm tra hai revisions; chia traffic 90/10 trong lab rồi đưa 100% về version 1. Ghi p95, HTTP errors và cấu hình traffic trước/sau.

**Bài D — Quyết định:** một nhóm phải phát hành tới staging và production, có yêu cầu SBOM, phê duyệt bảo mật và không được build lại khi promote. Chọn source hay image? Nêu thiết kế IAM, digest/provenance và rollback.

Báo cáo cần tối thiểu:

~~~text
PROJECT / REGION / OWNER:
SOURCE_SERVICE / READY_REVISION:
SOURCE_BUILD_ID / ARTIFACT_REGISTRY_LOCATION:
IMAGE_REPOSITORY / IMAGE_TAG / IMAGE_DIGEST:
IMAGE_SERVICE / READY_REVISION:
IAM_AUTHENTICATION / INGRESS:
PORT / HEALTH_CHECK_RESULT:
TRAFFIC_SPLIT / ROLLBACK_RESULT:
LOGS / ERRORS:
BILLING_GUARDRAILS:
CLEANUP_RESULT / OPEN_ISSUES:
~~~

Ghi kết quả **thực tế**; không đánh dấu PASS nếu chưa chạy. Không đưa credentials, ID tokens hoặc secrets vào báo cáo.

## 13. Tài liệu chính thức và checklist

- [Cloud Run: Deploy services from source code](https://docs.cloud.google.com/run/docs/deploying-source-code)
- [Cloud Run: Deploy container images](https://docs.cloud.google.com/run/docs/deploying)
- [Cloud Run: Deployment options](https://docs.cloud.google.com/run/docs/deployment-options-for-services)
- [Cloud Run: Container runtime contract](https://docs.cloud.google.com/run/docs/container-contract)
- [Cloud Run: Set build service account](https://docs.cloud.google.com/run/docs/configuring/services/build-service-account)
- [Cloud Run: Service identity](https://docs.cloud.google.com/run/docs/configuring/services/service-identity)
- [Cloud Run: Authenticate developers](https://docs.cloud.google.com/run/docs/authenticating/developers)
- [Cloud Run: Traffic splitting and rollback](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)
- [Buildpacks: Python build](https://docs.cloud.google.com/docs/buildpacks/python)
- [Cloud Run: Troubleshooting](https://docs.cloud.google.com/run/docs/troubleshooting)
- [Artifact Registry: Docker authentication](https://docs.cloud.google.com/artifact-registry/docs/docker/authentication)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)

**Checklist triển khai:** xác định project/region/identity → kiểm tra API/quyền → build source hoặc image có thể truy vết → bảo đảm **0.0.0.0:$PORT** → deploy private hoặc public có chủ đích → kiểm tra revision/URL/auth/health → theo dõi logs/SLO → quản lý traffic, digest và rollback → xác minh chi phí và dọn lab.

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** Cloud Run giúp triển khai dịch vụ HTTP mà không phải trực tiếp quản lý node GKE/Compute Engine. **Source deploy** giúp bắt đầu nhanh, **image deploy** giúp quản trị artifact và release theo CI/CD. Với cả hai, cần kết hợp **Artifact Registry, IAM, VPC/network, lưu trữ/dữ liệu bền vững, Cloud Monitoring và Cloud Billing** để triển khai an toàn, đáng tin cậy và kiểm soát chi phí.





