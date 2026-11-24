# Truyền cấu hình, secret và danh tính vào container

Container image nên chứa ứng dụng và các dependency cần để chạy, còn thông tin thay đổi theo môi trường cần được cung cấp khi triển khai. Cùng một image có thể chạy ở development, staging và production nếu endpoint, feature flag, giới hạn tài nguyên và thông tin kết nối được truyền từ môi trường bên ngoài. Mật khẩu, token, private key và certificate riêng cần được bảo vệ như secret. Ứng dụng cũng cần một danh tính riêng để gọi database, object storage, queue hoặc API khác với đúng quyền được cấp.

Nếu đưa cấu hình production hoặc credential vào image, mỗi lần đổi môi trường hay xoay vòng secret có thể buộc phải build image mới. Secret bị ghi trong image layer, source repository, log build hoặc lệnh inspect cũng có thể tồn tại lâu sau khi ứng dụng đã được cập nhật. Vì vậy, cần tách rõ cấu hình, secret và danh tính, rồi chọn cơ chế truyền phù hợp với nền tảng container.

Bài học này thuộc chương **Nền tảng container** của module **CLOUD_CORE_SERVICES_COMPUTE**. Module giúp người học tìm hiểu các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless; cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật; triển khai ứng dụng, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành. Trong bối cảnh đó, quản lý cấu hình, secret và danh tính giúp container chạy nhất quán giữa các môi trường, kết nối đúng dependency và giảm rủi ro lộ thông tin truy cập.

## 1. Phân biệt cấu hình, secret và danh tính

### 1.1. Cấu hình ứng dụng (configuration)

Cấu hình mô tả cách ứng dụng hoạt động trong một môi trường. Ví dụ:

- Địa chỉ endpoint của database, cache hoặc API nội bộ.
- Tên queue, bucket hoặc schema.
- Port mà ứng dụng lắng nghe.
- Feature flag và chế độ hoạt động.
- Log level, timeout và số worker.
- Giới hạn batch, concurrency và retry.
- Tên region, environment hoặc tenant.
- Đường dẫn file cấu hình và chứng thư công khai.

Cấu hình thường không cần giữ bí mật, nhưng vẫn cần tính toàn vẹn và kiểm soát thay đổi. Một endpoint sai có thể khiến ứng dụng gửi dữ liệu tới nhầm hệ thống; một log level quá chi tiết có thể làm tăng chi phí hoặc vô tình ghi dữ liệu nhạy cảm.

### 1.2. Secret

Secret là thông tin mà người không được phép biết có thể dùng để truy cập hệ thống hoặc giả mạo danh tính. Ví dụ:

- Mật khẩu database.
- API token và OAuth client secret.
- Private key, signing key và certificate có khóa riêng.
- Credential của registry hoặc package repository.
- Encryption key và key-encryption key.
- Token của dịch vụ bên ngoài.
- Thông tin xác thực dùng trong một tác vụ triển khai.

Không phải mọi giá trị cấu hình đều là secret. Tên database, địa chỉ service hay port thường không phải secret, nhưng có thể vẫn là thông tin nội bộ cần hạn chế công bố. Phân loại đúng giúp tránh lưu mọi thứ trong secret store và cũng tránh xem credential là một biến môi trường bình thường.

### 1.3. Danh tính workload (workload identity)

Danh tính xác định workload là ai khi truy cập tài nguyên khác. Nó trả lời câu hỏi “container nào đang gọi dịch vụ?” và được hệ thống đích dùng để xác thực, sau đó áp dụng quyền.

Ví dụ:

- Một API chỉ được đọc một nhóm object trong bucket.
- Worker được nhận và xác nhận message từ một queue cụ thể.
- Job backup được tạo snapshot nhưng không được xóa vault.
- Container triển khai được pull image từ registry nhưng không được truy cập database production.

Danh tính workload thường được gắn với service account, task role, managed identity hoặc cơ chế workload identity của nền tảng. Ưu tiên credential ngắn hạn do nền tảng cấp thay cho access key tĩnh được nhúng vào image hoặc lưu lâu dài trong file.

### 1.4. Authentication và authorization

- **Authentication (xác thực):** xác định workload hoặc người gọi là ai.
- **Authorization (phân quyền):** quyết định danh tính đó được phép làm gì trên tài nguyên nào.

Có token hợp lệ không có nghĩa workload nên có quyền quản trị. Sau khi xác thực, hệ thống cần kiểm tra policy theo nguyên tắc quyền tối thiểu.

### 1.5. Bảng so sánh

| Loại | Ví dụ | Nơi quản lý phù hợp | Cách truyền phổ biến |
|---|---|---|---|
| Cấu hình không bí mật | Port, endpoint, log level | Config file, ConfigMap, deployment config | Environment variable hoặc file mount |
| Secret | DB password, API token | Secret manager, vault hoặc secret store của nền tảng | File mount, volume, secret reference hoặc env khi cần |
| Danh tính workload | Service account, task role | Identity provider và control plane của cloud/cluster | Token ngắn hạn hoặc credential được cấp tự động |
| Artifact | Image, package, certificate công khai | Registry, artifact repository, PKI | Pull theo digest hoặc mount theo policy |
| Chính sách quyền | IAM/RBAC policy | Control plane, IaC và policy repository | Gắn với workload identity, không nhúng vào image |

## 2. Nguyên tắc thiết kế

### 2.1. Một image, nhiều môi trường

Image nên được build một lần và promote qua các môi trường. Cấu hình riêng của môi trường được truyền lúc deploy.

Ví dụ cùng một image API có thể dùng:

- Development: database và queue thử nghiệm.
- Staging: dependency gần production để kiểm thử.
- Production: endpoint và resource production.

Không tạo image riêng chỉ để thay URL, log level hoặc tên queue. Điều này làm tăng số artifact và có thể khiến các môi trường chạy code khác nhau.

### 2.2. Không đóng gói secret vào image

Không đặt secret trong:

- Dockerfile bằng lệnh ENV hoặc ARG.
- Source code, file .env được commit hoặc script khởi động.
- Image layer được tạo bằng COPY.
- Build log hoặc command line.
- Label, annotation hoặc metadata của image.
- Test fixture được đưa vào production image.

Xóa file secret ở layer sau không loại bỏ dữ liệu khỏi layer trước. Image history, cache, registry và bản image cũ có thể vẫn giữ nội dung đó.

Nếu secret từng được đưa vào image hoặc repository, cần coi là đã lộ: thu hồi hoặc rotate credential, kiểm tra quyền truy cập và dọn artifact theo quy trình. Chỉ xóa dòng cấu hình trong phiên bản mới không vô hiệu hóa secret cũ.

### 2.3. Cấp cấu hình tại runtime

Cấu hình nên được cung cấp bởi hệ thống triển khai, orchestrator hoặc secret manager. Ứng dụng đọc cấu hình lúc khởi động và xác thực giá trị trước khi nhận traffic.

Một ứng dụng tốt nên:

- Có schema hoặc danh sách cấu hình được hỗ trợ.
- Phân biệt giá trị bắt buộc và tùy chọn.
- Có default an toàn cho cấu hình không nhạy cảm.
- Fail fast khi thiếu secret hoặc endpoint bắt buộc.
- Không in giá trị secret khi báo lỗi.
- Có cách kiểm tra cấu hình mà không tiết lộ nội dung bí mật.

### 2.4. Ưu tiên danh tính thay cho credential tĩnh

Nếu cloud hoặc orchestrator hỗ trợ workload identity, dùng danh tính gắn với workload để nhận token ngắn hạn. Tránh tạo access key lâu dài rồi copy vào mọi replica.

Credential tĩnh làm tăng rủi ro khi image, log, backup hoặc máy phát triển bị lộ. Token ngắn hạn và quyền tối thiểu giúp giới hạn thời gian và phạm vi ảnh hưởng.

### 2.5. Tách trách nhiệm

Nên phân tách các vai trò:

- Người build image không cần quyền đọc secret production.
- Pipeline triển khai chỉ có quyền cấp cấu hình cho môi trường được phép.
- Workload chỉ có quyền truy cập dependency cần thiết.
- Người vận hành có thể yêu cầu rotate nhưng không mặc nhiên đọc giá trị secret.
- Backup/recovery identity có quyền khôi phục theo quy trình riêng.

Tách trách nhiệm giúp một lỗi trong build pipeline không tự động trở thành quyền truy cập vào dữ liệu production.

## 3. Truyền cấu hình qua environment variable

### 3.1. Cách hoạt động

Environment variable là cặp tên/giá trị được truyền vào process khi container khởi chạy. Ứng dụng đọc chúng thông qua API của runtime hoặc thư viện cấu hình.

Ví dụ tên cấu hình:

~~~text
APP_ENV=production
HTTP_PORT=8080
LOG_LEVEL=info
DB_HOST=db.internal
DB_PORT=5432
REQUEST_TIMEOUT_SECONDS=5
~~~

Các giá trị trên chỉ minh họa cấu hình không bí mật. Không dùng ví dụ này để truyền mật khẩu database.

Ưu điểm:

- Dễ tích hợp với nhiều ngôn ngữ và framework.
- Phù hợp các giá trị nhỏ, đơn giản.
- Có thể thay đổi theo deployment mà không build lại image.
- Dễ dùng với container orchestrator và CI/CD.

Hạn chế:

- Process và tiến trình con có thể kế thừa environment.
- Người có quyền phù hợp trên host hoặc control plane có thể xem cấu hình.
- Environment thường không tự cập nhật trong process đang chạy.
- Giá trị nhiều dòng hoặc cấu trúc phức tạp khó quản lý.
- Log, crash dump, diagnostic bundle hoặc lệnh inspect có thể vô tình làm lộ giá trị.

Environment variable không phải secret manager. Nếu buộc phải dùng env cho một secret, hãy giới hạn quyền xem metadata, tránh in environment, kiểm soát host/debug access và ưu tiên cơ chế file/identity khi phù hợp.

### 3.2. Đọc cấu hình và kiểm tra khi khởi động

Ví dụ Python chỉ minh họa cách đọc cấu hình không bí mật:

~~~python
import os

app_env = os.getenv("APP_ENV", "development")
port_value = os.getenv("HTTP_PORT", "8080")
log_level = os.getenv("LOG_LEVEL", "info")

try:
    http_port = int(port_value)
except ValueError as exc:
    raise RuntimeError("HTTP_PORT must be an integer") from exc

if not 1 <= http_port <= 65535:
    raise RuntimeError("HTTP_PORT is outside the valid range")

print(f"Starting service in {app_env} on port {http_port}")
~~~

Không in toàn bộ environment để debug. Khi cấu hình không hợp lệ, thông báo lỗi nên nêu tên biến và quy tắc, không nêu giá trị secret.

### 3.3. Thứ tự ưu tiên cấu hình

Ứng dụng có thể nhận cấu hình từ nhiều nguồn:

1. Default trong ứng dụng.
2. File cấu hình mặc định trong image.
3. File cấu hình được mount.
4. Environment variable.
5. Tham số khởi chạy hoặc cấu hình được control plane truyền vào.

Không có thứ tự chuẩn áp dụng cho mọi framework. Phải ghi rõ precedence của ứng dụng để tránh cùng một thuộc tính có giá trị khác nhau ở hai nguồn mà người vận hành không biết nguồn nào thắng.

### 3.4. Khi nào nên dùng env và khi nào nên dùng file?

| Tình huống | Environment variable | File mount |
|---|---|---|
| Port, log level, feature flag nhỏ | Phù hợp | Có thể dùng |
| Endpoint hoặc tên queue | Phù hợp | Phù hợp nếu có nhiều cấu hình |
| JSON/YAML nhiều dòng | Khó quản lý | Thường phù hợp hơn |
| Private key hoặc certificate bundle | Không ưu tiên | Thường phù hợp hơn với quyền file rõ ràng |
| Secret cần rotate | Cần restart process hoặc cơ chế riêng | Có thể cập nhật file, ứng dụng vẫn phải reload |
| Cấu hình lớn | Không phù hợp | Phù hợp hơn |

File mount cũng cần bảo vệ. Đặt quyền file, quyền thư mục, mount read-only và nguồn lưu trữ đúng cách; không giả định rằng file secret tự động an toàn chỉ vì không nằm trong environment.

## 4. Truyền cấu hình và secret với Docker

### 4.1. Dockerfile: ENV và ARG

Dockerfile hỗ trợ hai cơ chế thường gặp:

- **ARG:** biến có phạm vi trong quá trình build.
- **ENV:** biến mặc định được lưu trong image và có mặt khi container chạy.

Ví dụ cấu hình không bí mật:

~~~dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV HTTP_PORT=8080
ENV LOG_LEVEL=info

USER 10001:10001
EXPOSE 8080

CMD ["python", "-m", "src.server"]
~~~

HTTP_PORT và LOG_LEVEL là default không bí mật. Có thể override lúc chạy container. Không thêm DB_PASSWORD, API_TOKEN hoặc private key bằng ENV.

ARG cũng không phải nơi an toàn để truyền password hoặc token. Build argument có thể xuất hiện trong metadata, build history, cache hoặc log tùy builder và cách dùng.

### 4.2. Build secret với BuildKit

Nếu bước build cần truy cập private package registry, dùng cơ chế secret mount của BuildKit thay vì ARG/ENV hoặc COPY credential vào image.

Ví dụ:

~~~dockerfile
# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS build

WORKDIR /app
COPY package*.json ./

RUN --mount=type=secret,id=npmrc,target=/root/.npmrc \
    npm ci

COPY . .
RUN npm run build
~~~

Secret mount chỉ được cung cấp cho lệnh RUN tương ứng và không được thêm vào image layer theo cơ chế mount. Tuy vậy, script build có thể đọc hoặc in secret; cần tin cậy dependency, kiểm soát log và không chạy mã build không tin cậy với credential nhạy cảm.

Build secret dành cho credential cần trong quá trình build. Nó không thay thế secret runtime mà ứng dụng cần sau khi container khởi chạy.

Có thể truyền file secret cho BuildKit bằng lệnh build, ví dụ:

~~~bash
docker build --secret id=npmrc,src=./secrets/npmrc -t my-api:build .
~~~

Đường dẫn nguồn phải được bảo vệ và không cần được COPY vào image. Có thể thêm các mục sau vào .dockerignore để giảm nguy cơ đưa file local vào build context:

~~~text
.env
.env.*
secrets/
*.pem
*.key
~~~

### 4.3. Truyền cấu hình lúc chạy

Ví dụ truyền cấu hình không nhạy cảm:

~~~bash
docker run --rm \
  -p 8080:8080 \
  -e APP_ENV=staging \
  -e HTTP_PORT=8080 \
  -e LOG_LEVEL=debug \
  my-api:1.0
~~~

Không đưa secret trực tiếp vào câu lệnh shell hoặc lịch sử terminal. Command line có thể bị lưu trong shell history, process listing, CI log hoặc hệ thống audit.

Trong môi trường thử nghiệm, có thể dùng file env được bảo vệ và không commit. Với production, nên dùng secret manager, orchestrator secret hoặc workload identity thay vì file env tĩnh.

### 4.4. Docker Compose

Compose hỗ trợ khai báo environment và file secret cho service. Ví dụ sau dùng file secret được quản lý ngoài repository:

~~~yaml
services:
  api:
    image: registry.example.com/team/api:1.0
    environment:
      APP_ENV: production
      HTTP_PORT: "8080"
      DB_HOST: db.internal
      DB_PORT: "5432"
    secrets:
      - db_password
    read_only: true
    user: "10001:10001"

secrets:
  db_password:
    file: ./secrets/db_password.txt
~~~

Trong container, secret được mount dưới đường dẫn mặc định của Compose, thường là /run/secrets/db_password. Ứng dụng cần đọc file đó và không in nội dung ra log.

Ví dụ này không tự làm cho file nguồn an toàn. File ./secrets/db_password.txt phải được cấp quyền phù hợp, không commit vào Git, không đưa vào build context và được quản lý bởi quy trình secret an toàn. Cách triển khai secret của Docker Compose local cũng khác với secret manager hoặc Docker Swarm; hãy kiểm tra bảo đảm thực tế của nền tảng đang dùng.

### 4.5. Docker Swarm secrets

Docker Swarm có cơ chế secret riêng cho service. Secret được phân phối tới node được phép chạy task và được mount trong container, thường dưới /run/secrets. Cơ chế này giúp tránh truyền secret qua environment variable và có thể quản lý vòng đời secret ở cấp service.

Cần phân biệt Swarm secrets với file secret của Compose local. Không giả định hai cơ chế có cùng control plane, mã hóa, replication hoặc quyền truy cập. Chọn theo mô hình triển khai thực tế.

### 4.6. Giảm bề mặt lộ thông tin trên Docker host

- Chạy container bằng user không phải root nếu ứng dụng cho phép.
- Không cấp quyền Docker socket cho ứng dụng.
- Giới hạn quyền truy cập Docker daemon; quyền điều khiển daemon thường tương đương quyền rất cao trên host.
- Không dùng lệnh inspect hoặc debug dump có thể in environment chứa secret.
- Không truyền secret trong command line.
- Mount secret read-only và giới hạn đúng service cần dùng.
- Không copy thư mục secret vào image build context.
- Dùng .dockerignore để loại file local và secret khỏi build context.

## 5. Kubernetes ConfigMap và Secret

### 5.1. ConfigMap cho cấu hình không bí mật

ConfigMap lưu cấu hình không nhạy cảm và có thể được đưa vào container qua environment variable hoặc volume.

Ví dụ:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: api-config
data:
  APP_ENV: "production"
  HTTP_PORT: "8080"
  LOG_LEVEL: "info"
  DB_HOST: "postgres.database.svc"
~~~

Deployment có thể tham chiếu ConfigMap:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: registry.example.com/team/api:1.0
          ports:
            - containerPort: 8080
          envFrom:
            - configMapRef:
                name: api-config
~~~

Ví dụ rút gọn để minh họa. Manifest production cần bổ sung resource requests/limits, probes, security context, service account và các chính sách triển khai phù hợp.

### 5.2. Secret của Kubernetes

Kubernetes Secret lưu dữ liệu nhạy cảm theo cấu trúc key/value. Dữ liệu trong manifest YAML thường được biểu diễn Base64; Base64 chỉ là encoding, không phải mã hóa.

Ví dụ minh họa cấu trúc, không chứa credential thật:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: api-db-credentials
type: Opaque
data:
  username: <BASE64_USERNAME>
  password: <BASE64_PASSWORD>
~~~

Không commit secret thật vào manifest hoặc Git chỉ vì giá trị đã được Base64. Người có quyền đọc Secret có thể decode nội dung.

Với production, cần:

- Bật encryption at rest cho Kubernetes Secret bằng cơ chế được cluster hỗ trợ.
- Giới hạn RBAC quyền get/list/watch Secret theo namespace và workload.
- Hạn chế quyền tạo Pod tùy ý trong namespace có secret nhạy cảm.
- Tách secret theo ứng dụng và môi trường.
- Audit truy cập và thay đổi Secret.
- Cân nhắc external secret manager hoặc CSI driver.
- Bảo vệ backup của etcd/cluster và khóa mã hóa tương ứng.

### 5.3. Đưa Secret vào environment

Có thể tham chiếu một key của Secret:

~~~yaml
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: api-db-credentials
        key: password
~~~

Cách này tiện cho ứng dụng chỉ đọc environment lúc khởi động. Giá trị đã được đưa vào process environment thường không tự đổi khi Secret được cập nhật. Cần rollout/restart Pod hoặc có cơ chế refresh riêng.

Nếu ứng dụng ghi environment vào log, crash dump hoặc diagnostic endpoint, secret có thể bị lộ. Chỉ dùng cách này khi đã đánh giá rủi ro và giới hạn quyền debug.

### 5.4. Mount Secret dưới dạng file

Ví dụ:

~~~yaml
volumes:
  - name: db-credentials
    secret:
      secretName: api-db-credentials
      defaultMode: 0440

containers:
  - name: api
    volumeMounts:
      - name: db-credentials
        mountPath: /var/run/secrets/app
        readOnly: true
~~~

Đây là đoạn trích bên trong Pod spec, nơi volumes và containers là các trường cùng cấp dưới spec. Trong Deployment đầy đủ, chúng nằm trong spec.template.spec.

Ứng dụng có thể đọc file /var/run/secrets/app/password. File mount giúp tránh đưa giá trị vào environment và cho phép áp dụng quyền file rõ ràng.

Cần kiểm tra UID/GID của process và quyền đọc file. Secret volume được cập nhật theo cơ chế eventual propagation của Kubernetes; ứng dụng phải mở lại hoặc theo dõi file để nạp giá trị mới. Mount qua subPath không nhận cập nhật Secret tự động như volume projection thông thường. Không giả định file đã thay đổi nghĩa là ứng dụng đã dùng secret mới.

### 5.5. Không để mọi container đều thấy secret

Trong một Pod, volume có thể được mount riêng vào container cần dùng. Không nên mount credential database vào sidecar logging hoặc proxy nếu chúng không cần quyền đó.

Tách workload có mức tin cậy khác nhau thành Pod hoặc service riêng khi cần. Một container cùng Pod không nên được xem là ranh giới bảo mật mạnh đối với container khác nếu chúng chia sẻ namespace, volume hoặc quyền truy cập.

## 6. Secret manager và external secret

### 6.1. Secret manager là nguồn quản lý trung tâm

Secret manager hoặc vault có thể cung cấp:

- Lưu trữ secret được mã hóa.
- Kiểm soát truy cập theo identity.
- Audit việc đọc, ghi và rotate.
- Phiên bản secret.
- Thời hạn hoặc chính sách rotation.
- Credential động cho một số database/service.
- Replication hoặc khả năng phục hồi tùy sản phẩm.

Container không nên cần biết mật khẩu quản trị của secret manager. Nó nên xác thực bằng workload identity và chỉ được đọc đúng secret hoặc path được cấp.

### 6.2. Hai mô hình tích hợp phổ biến

**Mô hình đồng bộ secret vào orchestrator:** controller được cấp quyền đọc secret manager và tạo/cập nhật Kubernetes Secret. Pod tham chiếu Secret như bình thường.

Ưu điểm là tích hợp đơn giản với ứng dụng hiện có. Rủi ro là secret có thêm bản sao trong Kubernetes API/etcd, do đó cần bảo vệ cả secret manager lẫn cluster.

**Mô hình mount trực tiếp qua CSI hoặc agent:** workload nhận secret dưới dạng file thông qua driver/agent, theo policy của nền tảng.

Ưu điểm là có thể giảm việc lưu secret dưới dạng Kubernetes Secret. Tuy nhiên, driver, node plugin, identity và đường kết nối tới vault trở thành dependency cần bảo vệ và kiểm thử.

Không có mô hình nào tự động an toàn hơn trong mọi trường hợp. Cần xem quyền, audit, caching, rotation, availability và cách secret được lưu trên node.

### 6.3. Không lấy secret ở bước build để dùng runtime

Build pipeline và runtime có mục tiêu khác nhau:

- Build có thể cần token đọc package registry.
- Runtime có thể cần credential truy cập database.
- Deployment controller có thể cần quyền tạo resource.
- Workload chỉ cần quyền gọi service của chính nó.

Không dùng một credential dùng chung cho cả bốn vai trò. Thu hồi và rotate từng credential theo vòng đời của nó.

## 7. Workload identity và quyền truy cập cloud

### 7.1. Vì sao không nên nhúng access key vào container?

Một cách cũ là tạo access key lâu dài rồi đặt trong biến môi trường hoặc file cấu hình. Khi image hoặc Pod bị sao chép, credential cũng bị sao chép. Nếu nhiều workload dùng chung key, khó xác định ai đã truy cập tài nguyên và khó thu hồi một workload riêng lẻ.

Workload identity cho phép nền tảng xác định Pod/task/instance và cấp credential có thời hạn hoặc token exchange. Ứng dụng không cần chứa private key dài hạn trong image.

### 7.2. Mô hình cấp danh tính

Một luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant W as Container workload
    participant P as Platform identity
    participant I as Identity provider
    participant S as Cloud service
    W->>P: Request workload identity token
    P->>I: Validate workload identity / exchange token
    I-->>P: Short-lived credential
    P-->>W: Credential scoped to workload
    W->>S: Call API with credential
    S->>S: Authenticate and authorize
    S-->>W: Response if policy allows
~~~

Tên API và cơ chế cụ thể khác nhau theo nền tảng. Có thể dùng service account token projection, task role, managed identity hoặc workload identity federation. Điểm chung là danh tính gắn với workload và quyền được cấp theo policy.

### 7.3. Kubernetes ServiceAccount

Pod có thể chạy dưới một Kubernetes ServiceAccount. ServiceAccount xác định danh tính của workload trong cluster và có thể được dùng cho RBAC hoặc tích hợp với identity provider bên ngoài.

Ví dụ:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: api-reader
  namespace: production
automountServiceAccountToken: false
~~~

Pod tham chiếu service account:

~~~yaml
spec:
  serviceAccountName: api-reader
  automountServiceAccountToken: false
  containers:
    - name: api
      image: registry.example.com/team/api:1.0
~~~

Ví dụ tắt tự động mount token khi ứng dụng không cần gọi Kubernetes API bằng token mặc định. Nếu workload identity federation yêu cầu token projected với audience cụ thể, cấu hình token projection theo hướng dẫn của nền tảng thay vì bật token mặc định rộng rãi.

### 7.4. RBAC và IAM

ServiceAccount không tự động có quyền truy cập mọi tài nguyên. Cần cấp quyền theo phạm vi:

- Namespace và resource cần thiết.
- Verb tối thiểu: get/list/watch/create/update/delete.
- Resource name hoặc label scope khi nền tảng hỗ trợ.
- Cloud resource cụ thể như bucket, queue hoặc secret path.
- Điều kiện theo environment, cluster hoặc workload identity.

Tránh cấp cluster-admin, quyền wildcard hoặc quyền xóa dữ liệu cho workload chỉ cần đọc. Cần rà soát cả quyền Kubernetes RBAC và IAM của cloud; hai hệ thống này kiểm soát các tài nguyên khác nhau.

### 7.5. Token ngắn hạn và rotation

Token ngắn hạn giảm thời gian credential bị sử dụng nếu lộ. Ứng dụng hoặc SDK cần có khả năng refresh token trước khi hết hạn và retry an toàn khi nhận lỗi xác thực do token cũ.

Không cache credential lâu hơn thời hạn hoặc bỏ qua lỗi refresh. Đồng hồ hệ thống sai cũng có thể làm token bị coi là chưa có hiệu lực hoặc đã hết hạn.

### 7.6. Danh tính giữa các môi trường

Dùng danh tính riêng cho development, staging và production. Không cho workload staging dùng role production chỉ để tiện kiểm thử.

Nếu cần test quyền production, dùng quy trình phê duyệt và tài khoản test có dữ liệu giới hạn. Tách account/project/subscription hoặc namespace giúp giảm khả năng credential ở môi trường thấp truy cập tài nguyên nhạy cảm.

## 8. Quyền truy cập trong container

### 8.1. Chạy non-root

Container process nên chạy bằng UID/GID không đặc quyền nếu ứng dụng không cần quyền root.

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --chown=10001:10001 app.jar /app/app.jar
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Cần bảo đảm thư mục ghi dữ liệu, temporary directory và certificate có quyền phù hợp. Không chuyển sang root chỉ để giải quyết lỗi permission mà chưa xác định file/path nào cần quyền ghi.

### 8.2. Read-only filesystem và mount có chọn lọc

Có thể đặt root filesystem read-only và chỉ mount các thư mục cần ghi:

~~~yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
~~~

Đặt khối trên trong trường securityContext của container, tức spec.containers[].securityContext. Ứng dụng cần có writable volume cho temporary data nếu cần. Secret volume nên read-only. Không bật privileged mode hoặc mount host path chỉ để làm ứng dụng hoạt động khi chưa hiểu tác động.

### 8.3. UID, GID và file permission

Khi secret được mount vào container, cần kiểm tra:

- Process chạy với UID/GID nào.
- File owner/group và mode.
- Có cần fsGroup hoặc cơ chế permission tương đương không.
- Container có thể đọc thư mục cha không.
- Sidecar có cùng volume mount không.
- Secret có bị copy sang filesystem ghi được không.

Quyền quá rộng như 0777 làm tăng số process có thể đọc secret. Quyền quá chặt có thể khiến ứng dụng không khởi động; nên kiểm thử bằng đúng user production.

## 9. Rotation và thu hồi secret

### 9.1. Vì sao cần rotation?

Secret có thể bị lộ, nhân sự hoặc vendor thay đổi, policy yêu cầu thay định kỳ, hoặc credential có thời hạn. Rotation thay secret cũ bằng secret mới và thu hồi giá trị cũ sau khi các consumer đã chuyển đổi.

Rotation cần có kế hoạch chuyển tiếp. Nếu thay password database ngay lập tức trong khi một số replica còn dùng password cũ, một phần request sẽ lỗi.

### 9.2. Quy trình rotation an toàn

1. Xác định secret, owner, consumer và mức độ ảnh hưởng.
2. Tạo credential mới hoặc phiên bản mới theo cơ chế dịch vụ.
3. Cấp quyền sử dụng credential mới cho workload.
4. Cập nhật secret manager hoặc orchestrator.
5. Yêu cầu ứng dụng reload hoặc rollout có kiểm soát.
6. Xác minh mọi replica đã dùng phiên bản mới.
7. Theo dõi lỗi xác thực và hoạt động dependency.
8. Thu hồi credential cũ sau khi xác nhận không còn consumer.
9. Ghi nhận thời gian, phiên bản và bằng chứng rotation.

Với database chỉ hỗ trợ một password tại một thời điểm, có thể cần tạo user thứ hai, chuyển workload, rồi vô hiệu hóa user cũ. Cách này giúp tránh khoảng thời gian một số replica không thể xác thực.

### 9.3. Reload secret trong ứng dụng

Environment variable thường được chụp tại thời điểm process khởi động. Cập nhật Kubernetes Secret không thay đổi environment của process đang chạy. Thường cần rollout Pod để process đọc giá trị mới.

Với secret được mount dưới dạng file, nền tảng có thể cập nhật nội dung volume theo cơ chế của nó, nhưng ứng dụng cần mở lại file hoặc theo dõi thay đổi. Một số cách mount như subPath không nhận cập nhật tự động. Cần kiểm thử hành vi thực tế của runtime và CSI driver.

### 9.4. Thu hồi khi nghi ngờ bị lộ

Khi credential có dấu hiệu bị lộ:

- Thu hồi hoặc disable credential bị ảnh hưởng.
- Cấp credential mới qua kênh an toàn.
- Xem audit log để xác định phạm vi sử dụng.
- Kiểm tra image, registry, repository, CI log và backup liên quan.
- Xác minh workload đang chạy không còn dùng credential cũ.
- Xem xét rotate credential phụ thuộc hoặc token đã phát hành.
- Ghi nhận incident và cập nhật policy.

Không chỉ xóa secret khỏi manifest hoặc Git. Lịch sử Git, image layer, cache, log và bản backup có thể vẫn giữ giá trị cũ.

## 10. Quản lý cấu hình khi rollout và autoscaling

### 10.1. Replica phải nhận cùng cấu hình mong muốn

Khi autoscaler tạo thêm container, instance mới phải nhận đúng version cấu hình, secret reference và workload identity như các replica hiện có.

Cần quản lý cấu hình theo version hoặc checksum. Khi cấu hình thay đổi, hệ thống có thể tạo rollout mới để mọi replica hội tụ về cùng trạng thái.

Không để mỗi container tự tải một cấu hình không kiểm soát hoặc dùng cache local khác nhau. Điều đó có thể tạo hành vi khác nhau trong cùng một service.

### 10.2. Config change và rollout

Một thay đổi cấu hình có thể ảnh hưởng ứng dụng như một lần deploy code:

- Thay endpoint có thể chuyển traffic sang dependency khác.
- Thay pool size có thể làm database quá tải.
- Thay timeout có thể tăng thời gian giữ request.
- Thay feature flag có thể bật một luồng chưa được kiểm thử.
- Thay secret có thể làm một số replica xác thực thất bại.

Nên review, version hóa, kiểm thử staging và rollout theo canary hoặc rolling update. Có phương án quay về version cấu hình trước nếu lỗi tăng.

### 10.3. ConfigMap/Secret update có tự restart Pod không?

Kubernetes không tự động restart Pod chỉ vì ConfigMap hoặc Secret được cập nhật. Volume projection có thể được cập nhật sau một khoảng trễ, nhưng environment variable không đổi và ứng dụng có thể không reload file.

Một pattern phổ biến là thêm checksum/version của ConfigMap hoặc Secret vào Pod template annotation. Khi version thay đổi, Deployment tạo ReplicaSet mới và rollout Pod. Cần tránh ghi giá trị secret thô vào annotation; chỉ dùng version identifier hoặc checksum được thiết kế để không làm lộ dữ liệu.

### 10.4. Tránh cấu hình lệch phiên bản

Có thể áp dụng:

- Config version gắn với release.
- Deployment manifest tham chiếu version cụ thể.
- Rollout theo nhóm và theo dõi health.
- Kiểm tra cấu hình khi container start.
- Alert khi replica dùng config version khác nhau.
- Tự động rollback nếu health check không đạt.

Với secret rotation, version reference có thể được cập nhật theo quy trình riêng và cần bảo đảm credential cũ còn hiệu lực trong thời gian chuyển tiếp.

## 11. Cấu hình mạng và TLS liên quan tới secret

### 11.1. Certificate và private key

Container có thể cần certificate để cung cấp HTTPS hoặc xác thực mutual TLS. Certificate công khai không nhất thiết là secret, nhưng private key phải được bảo vệ.

Nên:

- Lấy certificate/private key từ PKI hoặc secret manager.
- Mount read-only vào đúng container.
- Giới hạn UID/GID và quyền file.
- Theo dõi ngày hết hạn.
- Rotate certificate trước khi hết hạn.
- Tránh đưa private key vào image hoặc repository.

### 11.2. Trust store

Trust store chứa CA certificate được dùng để xác minh peer. CA công khai thường không bí mật, nhưng thay đổi trust store có thể thay đổi hệ thống nào được tin cậy.

Nên version hóa trust bundle và kiểm thử khi cập nhật. Không tắt TLS verification để “sửa” lỗi certificate; cần xác định hostname, chain, thời gian hệ thống và CA đúng.

### 11.3. Proxy và endpoint

Proxy URL, no_proxy và endpoint có thể là cấu hình không bí mật. Proxy password hoặc token là secret. Tránh ghép username/password trực tiếp vào URL được log.

Cần kiểm tra cấu hình proxy trong cả process và sidecar. Một container có thể dùng proxy trong khi container khác gọi trực tiếp, tạo khác biệt về đường mạng và policy.

## 12. Quan sát và audit

### 12.1. Không log giá trị secret

Log có thể ghi:

- Tên secret hoặc secret reference.
- Version identifier.
- Thời điểm load/refresh.
- Kết quả thành công/thất bại.
- Mã lỗi đã được làm sạch.

Không ghi password, token, private key, authorization header hoặc toàn bộ environment. Khi debug, mask giá trị nhạy cảm và kiểm soát quyền truy cập log.

### 12.2. Theo dõi trạng thái cấu hình

Các chỉ số hữu ích:

- Config version đang chạy theo replica.
- Secret version và thời điểm refresh gần nhất.
- Số lần lỗi đọc secret manager.
- Token refresh failure.
- Lỗi authentication/authorization tới dependency.
- Certificate expiry.
- Pod restart do cấu hình không hợp lệ.
- Số workload dùng credential sắp hết hạn.

Không gắn secret value vào metric label hoặc trace attribute. Chỉ dùng identifier không nhạy cảm.

### 12.3. Audit quyền

Theo dõi:

- Ai tạo hoặc sửa Secret.
- Workload identity nào đọc secret.
- Policy nào được thay đổi.
- Khi nào token được cấp hoặc thu hồi.
- Ai dùng break-glass access.
- Secret nào chưa rotate theo policy.
- Workload nào có quyền rộng hơn nhu cầu.

Audit log cần được bảo vệ khỏi sửa/xóa bởi chính workload đang được giám sát.

## 13. Quy trình triển khai từ development tới production

Một quy trình tham khảo:

1. Khai báo schema cấu hình và phân loại giá trị không bí mật/secret.
2. Build image không chứa credential runtime.
3. Quét image và kiểm tra Dockerfile/build context.
4. Tạo config riêng cho development, staging và production.
5. Tạo secret trong secret manager hoặc hệ thống được phê duyệt.
6. Gắn workload identity và cấp quyền tối thiểu.
7. Deploy vào staging bằng đúng cách truyền cấu hình của production.
8. Kiểm thử đọc config, đọc secret, truy cập dependency và lỗi khi thiếu cấu hình.
9. Rollout production theo canary hoặc rolling update.
10. Theo dõi config version, auth errors, secret refresh và application health.
11. Kiểm thử rotation và thu hồi credential.
12. Ghi nhận owner, version, audit và runbook vận hành.

~~~mermaid
flowchart TD
    A["Source code và schema config"]
    B["Build image không chứa runtime secret"]
    C["Scan image và kiểm tra artifact"]
    D["Tạo config và secret theo môi trường"]
    E["Gắn workload identity và policy"]
    F["Deploy staging, kiểm tra dependency"]
    G["Canary / rolling rollout production"]
    H["Monitor config, identity và secret refresh"]
    I["Rotate, revoke và audit"]
    A --> B --> C --> D --> E --> F --> G --> H --> I
~~~

## 14. Ví dụ tổng hợp: API đọc database và object storage

Một API container cần:

- Cấu hình không bí mật: port, log level, database host và bucket name.
- Secret: database password hoặc credential tương đương nếu database chưa hỗ trợ identity.
- Danh tính: quyền đọc object từ một bucket cụ thể.
- Certificate: trust bundle để xác thực kết nối TLS tới database.

Thiết kế:

| Thành phần | Cơ chế |
|---|---|
| HTTP_PORT, LOG_LEVEL | Environment variable |
| DB_HOST, DB_NAME | ConfigMap hoặc deployment config |
| DB_PASSWORD | Secret manager, mount file read-only |
| Object storage access | Workload identity với quyền đọc đúng bucket |
| CA bundle | File mount read-only từ artifact/PKI được quản lý |
| Secret rotation | Cập nhật version, rollout hoặc reload, sau đó revoke bản cũ |
| Audit | Ghi identity, secret reference/version và kết quả truy cập, không ghi giá trị |

Khi container khởi động:

1. Kiểm tra cấu hình bắt buộc và kiểu dữ liệu.
2. Đọc password từ file secret nếu cơ chế database yêu cầu.
3. Nhận credential ngắn hạn qua workload identity để gọi object storage.
4. Kiểm tra kết nối database và TLS.
5. Chỉ chuyển readiness sang healthy sau khi dependency thiết yếu sẵn sàng.
6. Khi secret được rotate, reload hoặc rollout theo quy trình.
7. Nếu identity không được cấp quyền, fail closed và báo lỗi đã làm sạch.

Không nên cấp access key quản trị object storage cho API chỉ để đọc một bucket. Không nên cho ứng dụng tiếp tục chạy với password mặc định khi secret không đọc được.

## 15. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Container khởi động nhưng kết nối DB thất bại | Thiếu env, sai endpoint, secret sai hoặc network policy | Kiểm tra tên config, secret version, DNS, route và quyền |
| Pod báo permission denied khi đọc secret file | UID/GID hoặc file mode không phù hợp | Kiểm tra securityContext, owner, group và mode |
| Secret mới đã tạo nhưng ứng dụng vẫn dùng giá trị cũ | Env không refresh hoặc ứng dụng không reload file | Kiểm tra rollout, volume projection và file watcher |
| Workload identity không nhận token | ServiceAccount/role binding hoặc federation sai | Kiểm tra audience, subject, issuer, trust policy và thời gian |
| Gọi cloud API bị AccessDenied | Identity xác thực được nhưng thiếu quyền | Kiểm tra IAM/RBAC scope và resource policy |
| Chỉ một số replica lỗi sau config change | Replica dùng config version khác hoặc rollout chưa hoàn tất | So sánh Pod template, version và rollout status |
| Secret lộ trong log | Debug in environment/header hoặc exception chứa credential | Mask log, thu hồi secret, audit và rotate |
| Build pipeline truy cập registry thất bại | Build secret mount hoặc quyền registry sai | Kiểm tra secret ID, mount target, token scope và log đã làm sạch |
| Certificate hết hạn | Rotation không đồng bộ hoặc thiếu alert | Kiểm tra chain, expiry, volume reload và rollout |
| Pod không truy cập Kubernetes API | Token không được mount hoặc RBAC thiếu | Kiểm tra ServiceAccount, projected token và policy |

Khi điều tra, không chạy lệnh dump toàn bộ environment hoặc xuất toàn bộ Secret ra terminal. Dùng lệnh chỉ kiểm tra tên key, version, quyền và trạng thái khi có thể.

## 16. Những sai lầm thường gặp

**Đưa password vào Dockerfile ENV hoặc ARG.** Giá trị có thể tồn tại trong metadata, history hoặc build cache. Dùng secret manager hoặc cơ chế secret mount phù hợp.

**Commit file .env vào Git.** File local có thể chứa credential production. Dùng mẫu .env.example chỉ có placeholder và loại file thật khỏi repository.

**Nghĩ Base64 là mã hóa.** Kubernetes Secret ở dạng Base64 vẫn có thể decode. Cần encryption at rest, RBAC và audit.

**Dùng một access key cho mọi workload.** Khó giới hạn quyền và thu hồi riêng. Dùng workload identity và role riêng.

**Cấp quyền admin cho service account.** Một lỗi trong ứng dụng có thể trở thành quyền kiểm soát cluster hoặc account. Cấp quyền tối thiểu theo resource và verb.

**Cho mọi container trong Pod mount cùng secret.** Sidecar không cần credential có thể trở thành đường lộ thông tin. Chỉ mount vào container cần dùng.

**Tin rằng secret volume tự cập nhật ứng dụng.** File projection và process reload là hai việc khác nhau. Cần kiểm thử reload hoặc rollout.

**Chỉ rotate ở secret manager.** Consumer có thể vẫn dùng credential cũ. Cần theo dõi version đang chạy và thu hồi sau khi chuyển đổi hoàn tất.

**In environment hoặc authorization header khi debug.** Log và diagnostic bundle có thể tồn tại lâu, được sao chép rộng. Mask dữ liệu và chỉ ghi metadata cần thiết.

**Dùng credential runtime trong build pipeline.** Build code có thể truy cập secret không cần thiết. Tách credential theo vai trò và thời điểm.

**Không kiểm thử khi secret manager mất kết nối.** Cần xác định ứng dụng fail closed hay dùng cache có thời hạn; không giữ credential cũ vô hạn.

## 17. Checklist triển khai

### Cấu hình

- [ ] Phân loại cấu hình thường, thông tin nội bộ và secret.
- [ ] Một image có thể promote qua các môi trường.
- [ ] Có schema, default an toàn và kiểm tra cấu hình lúc khởi động.
- [ ] Xác định rõ precedence giữa default, file, env và tham số runtime.
- [ ] Không in toàn bộ environment trong log.

### Secret

- [ ] Không đưa secret vào source, Dockerfile, image layer hoặc build log.
- [ ] Dùng secret manager hoặc secret store được phê duyệt.
- [ ] Mount file read-only khi phù hợp và giới hạn UID/GID.
- [ ] Bảo vệ file nguồn, build context, registry, cache và backup.
- [ ] Có version, owner, rotation và revoke process.
- [ ] Kiểm thử secret refresh và credential expiry.
- [ ] Không coi Base64 là encryption.

### Danh tính và quyền

- [ ] Dùng workload identity khi nền tảng hỗ trợ.
- [ ] Dùng danh tính riêng theo workload và môi trường.
- [ ] Cấp quyền tối thiểu cho cloud resource và Kubernetes API.
- [ ] Tránh access key tĩnh và quyền wildcard.
- [ ] Giới hạn quyền đọc Secret, tạo Pod và truy cập host.
- [ ] Có audit và quy trình break-glass được kiểm soát.

### Triển khai và vận hành

- [ ] Chạy container non-root nếu có thể.
- [ ] Dùng read-only root filesystem và mount có chọn lọc.
- [ ] Kiểm thử config/secret/identity ở staging.
- [ ] Rollout cấu hình và secret theo version.
- [ ] Theo dõi token refresh, auth errors và certificate expiry.
- [ ] Kiểm thử rotation, thu hồi và sự cố secret manager.
- [ ] Có runbook xử lý khi credential bị lộ.

## 18. Ghi nhớ

- Cấu hình mô tả cách ứng dụng chạy; secret là dữ liệu xác thực nhạy cảm; workload identity xác định container là ai khi gọi tài nguyên.
- Một image nên được build một lần và nhận cấu hình theo môi trường khi triển khai.
- Không đưa secret runtime vào Dockerfile, source, image layer, command line hoặc log.
- Environment variable phù hợp với cấu hình nhỏ, nhưng không phải secret manager và thường không tự cập nhật trong process.
- File mount giúp quản lý quyền và nhiều dòng dữ liệu; vẫn cần read-only, UID/GID và kiểm soát nguồn file.
- Docker Compose file secrets, Docker Swarm secrets và Kubernetes Secret có cơ chế bảo vệ khác nhau.
- Kubernetes Secret Base64 không phải encryption; cần RBAC, encryption at rest và audit.
- Workload identity cùng token ngắn hạn giúp tránh access key tĩnh trong container.
- Rotation cần chuyển consumer, xác minh phiên bản mới rồi mới thu hồi credential cũ.
- Config/secret update cần reload hoặc rollout có kiểm soát; file đổi không có nghĩa ứng dụng đã dùng giá trị mới.
- Chạy non-root, giới hạn quyền và chỉ mount secret cho container cần dùng.
- Kiểm thử cả trường hợp secret manager, identity provider hoặc dependency tạm thời không khả dụng.

## Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Configuration | Các giá trị điều khiển hành vi của ứng dụng theo môi trường. |
| Secret | Dữ liệu xác thực nhạy cảm như password, token hoặc private key. |
| Workload identity | Danh tính được gắn với ứng dụng hoặc workload đang chạy. |
| Authentication | Quá trình xác định danh tính của người gọi hoặc workload. |
| Authorization | Quá trình quyết định danh tính được phép làm gì. |
| Environment variable | Biến môi trường được truyền cho process khi khởi chạy. |
| Dockerfile ARG | Biến dùng trong quá trình build image. |
| Dockerfile ENV | Biến môi trường mặc định được lưu trong image. |
| BuildKit secret mount | Cơ chế cấp secret tạm thời cho một bước build mà không thêm secret vào image layer theo cơ chế mount. |
| ConfigMap | Đối tượng Kubernetes lưu cấu hình không nhạy cảm. |
| Kubernetes Secret | Đối tượng Kubernetes lưu dữ liệu nhạy cảm theo key/value; cần cấu hình thêm để bảo vệ đầy đủ. |
| Secret manager | Dịch vụ quản lý, phân phối, audit và rotate secret. |
| ServiceAccount | Danh tính cho process hoặc workload trong Kubernetes. |
| RBAC | Role-Based Access Control, cơ chế phân quyền dựa trên vai trò. |
| IAM | Identity and Access Management, hệ thống quản lý danh tính và quyền truy cập. |
| Workload identity federation | Cơ chế trao đổi danh tính workload lấy credential của identity provider/cloud mà không cần key dài hạn. |
| Token rotation | Thay token theo thời hạn hoặc policy để giới hạn rủi ro credential bị lộ. |
| Secret rotation | Quy trình thay secret, chuyển consumer và thu hồi giá trị cũ. |
| Least privilege | Nguyên tắc chỉ cấp quyền tối thiểu cần thiết. |
| CSI Secret Store | Cơ chế CSI cho phép mount secret từ external secret provider vào workload. |
| Read-only filesystem | Root filesystem không cho process ghi, ngoại trừ volume được mount cho mục đích cụ thể. |
| Break-glass access | Quyền truy cập khẩn cấp được kiểm soát và audit. |
| Config drift | Chênh lệch cấu hình thực tế giữa các replica hoặc so với trạng thái mong muốn. |
