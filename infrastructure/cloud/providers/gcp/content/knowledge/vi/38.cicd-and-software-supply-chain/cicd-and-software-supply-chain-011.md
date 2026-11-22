# Triển khai tự động lên Cloud Run và GKE

Sau khi Cloud Build kiểm thử và tạo container image, pipeline cần đưa đúng artifact đến môi trường chạy. Với Cloud Run, bước triển khai tạo một revision mới của service; với Google Kubernetes Engine (GKE), pipeline cập nhật Kubernetes workload trong cluster. Một quy trình triển khai tự động tốt liên kết source commit, build, image digest và lần phát hành, đồng thời kiểm soát danh tính, quyền truy cập, kiểm tra sức khỏe và khả năng rollback.

Bài học thuộc module **CLOUD_PROVIDERS_GCP**. Module giúp người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Trong phạm vi bài này, chúng ta tập trung xây dựng pipeline Cloud Build để triển khai ứng dụng Java lên Cloud Run và GKE, quản lý môi trường, kiểm tra sau triển khai và khôi phục khi phát hành có vấn đề.

## Mục tiêu

Sau bài học, bạn có thể:

- Mô tả luồng CI/CD từ commit đến deployment trên Cloud Run và GKE.
- Phân biệt build service account, runtime service account và danh tính của Kubernetes workload.
- Tạo pipeline Cloud Build để build, push image và triển khai tự động.
- Dùng substitutions để chọn project, region, cluster, service và image.
- Triển khai Cloud Run revision, kiểm soát traffic và xác minh revision mới.
- Cập nhật Kubernetes Deployment lên GKE và theo dõi rollout.
- Thiết kế trigger, phê duyệt và ranh giới quyền giữa staging và production.
- Thêm smoke test, health checks, canary và rollback vào quy trình phát hành.
- Truy vết artifact bằng commit SHA, image digest và build metadata.

## 1. Bức tranh tổng thể: từ source đến runtime

CI (Continuous Integration) kiểm tra thay đổi mã nguồn và tạo artifact. CD (Continuous Delivery hoặc Continuous Deployment) đưa artifact đã được kiểm tra đến môi trường đích theo quy trình đã định. Cloud Build có thể thực hiện cả hai phần: build image, chạy kiểm thử, push image lên Artifact Registry và gọi lệnh triển khai đến Cloud Run hoặc GKE.

~~~mermaid
flowchart TD
    A["Commit vào repository"]
    B["Cloud Build trigger"]
    C["Compile, unit tests và kiểm tra"]
    D["Build container image"]
    E["Push Artifact Registry"]
    F{"Môi trường đích"}
    G["Deploy Cloud Run revision"]
    H["Deploy Kubernetes workload lên GKE"]
    I["Smoke test và kiểm tra sức khỏe"]
    J["Theo dõi metrics, logs và rollout"]
    A --> B --> C --> D --> E --> F
    F --> G --> I
    F --> H --> I
    I --> J
~~~

Artifact Registry lưu image để pipeline và runtime có thể tham chiếu. Cloud Run tạo revision mới từ image; GKE cập nhật Pod thông qua Kubernetes Deployment hoặc workload controller khác. Cả hai nền tảng đều nên nhận cùng một image đã build và kiểm thử, thay vì build lại từ source riêng cho từng môi trường.

### Các môi trường và ranh giới phát hành

Một quy trình thường có:

- **Development:** kiểm tra nhanh khi lập trình.
- **Staging:** xác minh image, cấu hình, tích hợp và smoke test gần production.
- **Production:** phát hành có kiểm soát, theo dõi tác động và có kế hoạch rollback.

Có thể dùng cùng một build config với substitutions hoặc trigger riêng cho từng môi trường. Tuy nhiên, tên branch hoặc giá trị substitution không phải ranh giới bảo mật. Quyền deploy production phải được bảo vệ bằng IAM, service account, trigger policy và approval phù hợp.

## 2. Chuẩn bị Artifact Registry và danh tính triển khai

Trước khi tạo pipeline, cần xác định project, region, repository, service hoặc cluster và service account mà build sẽ sử dụng. Tạo các tài nguyên hạ tầng qua quy trình quản trị của tổ chức, không để build production tự ý tạo project, cluster hoặc quyền IAM mỗi lần chạy.

### Bật API cần thiết

Ví dụ bật các API cho một project thử nghiệm:

~~~bash
export PROJECT_ID="your-project-id"
export REGION="asia-southeast1"

gcloud config set project "$PROJECT_ID"

gcloud services enable \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  container.googleapis.com \
  --project="$PROJECT_ID"
~~~

Chỉ bật API của nền tảng thực sự sử dụng. Nếu pipeline chỉ triển khai Cloud Run thì không cần bật Kubernetes Engine API cho riêng luồng đó.

### Tạo Docker repository

~~~bash
gcloud artifacts repositories create app-images \
  --repository-format=docker \
  --location="$REGION" \
  --description="Container images for application deployments" \
  --project="$PROJECT_ID"
~~~

Đường dẫn image Artifact Registry có dạng:

~~~text
REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE:TAG
~~~

Ví dụ:

~~~text
asia-southeast1-docker.pkg.dev/my-project/app-images/orders-api:BUILD_ID
~~~

Build pipeline cần quyền ghi image vào repository. Runtime cần quyền đọc image nếu repository nằm ở project khác hoặc cấu hình mặc định không cấp quyền phù hợp. Không cấp quyền quản trị toàn project chỉ để push hoặc pull image.

### Tách build identity và runtime identity

Có ít nhất hai danh tính cần phân biệt:

1. **Build service account:** Cloud Build dùng để chạy các bước build, push image và gọi API deploy.
2. **Runtime service account:** Cloud Run service hoặc workload sử dụng khi ứng dụng đang chạy để truy cập Secret Manager, database, Pub/Sub và các dịch vụ khác.

Với GKE còn có danh tính Kubernetes ServiceAccount của Pod. Nếu workload cần gọi Google Cloud API, hãy dùng Workload Identity Federation for GKE để ánh xạ Kubernetes ServiceAccount với quyền Google Cloud phù hợp.

Không dùng build service account làm runtime identity. Build có thể cần quyền deploy hoặc ghi artifact; ứng dụng khi chạy chỉ nên có quyền nghiệp vụ tối thiểu.

## 3. Pipeline Cloud Build: build một image dùng chung

Một pipeline triển khai nên tạo image một lần, push image lên Artifact Registry rồi dùng chính image đó cho môi trường đích. Dùng BUILD_ID hoặc commit SHA làm tag để nhận diện lần build. Khi phát hành production, lưu lại image digest để xác định chính xác nội dung đã chạy.

### Ví dụ cloudbuild.yaml

Giả sử repository có ứng dụng Java Maven, Dockerfile ở thư mục gốc và Maven tạo file target/app.jar.

~~~yaml
substitutions:
  _REGION: asia-southeast1
  _AR_REPOSITORY: app-images
  _IMAGE: orders-api

steps:
  - id: test-and-package
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - verify

  - id: build-image
    name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - $_REGION-docker.pkg.dev/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$BUILD_ID
      - .
    waitFor:
      - test-and-package

  - id: push-image
    name: gcr.io/cloud-builders/docker
    args:
      - push
      - $_REGION-docker.pkg.dev/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$BUILD_ID
    waitFor:
      - build-image

options:
  logging: CLOUD_LOGGING_ONLY

timeout: 1200s
~~~

Trong ví dụ:

- Maven chạy verify để compile, test và thực hiện các kiểm tra được cấu hình trong dự án.
- Docker build tạo image từ Dockerfile sau khi kiểm thử thành công.
- Docker push tải image lên Artifact Registry.
- Trường images khai báo image đầu ra của build.
- BUILD_ID tạo tag riêng cho lần build, giúp tránh dùng tag mutable như latest làm định danh duy nhất.

Dockerfile cần khớp với artifact do Maven tạo:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY target/app.jar app.jar

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Với production, nên pin base image theo version hoặc digest, quét image và dependency, đồng thời quản lý Dockerfile như mã nguồn cần review. Hãy xác nhận tên JAR thực tế hoặc cấu hình Maven finalName để tránh lỗi COPY khi build.

### Chạy build

~~~bash
gcloud builds submit . \
  --config=cloudbuild.yaml \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

Khi build thành công, ghi lại image URI và digest trong build output hoặc metadata phát hành. Tag giúp con người nhận diện phiên bản; digest là định danh bất biến của image manifest và phù hợp để truy vết artifact đã triển khai.

## 4. Triển khai tự động lên Cloud Run

Cloud Run chạy container dưới dạng service. Mỗi lần deploy image hoặc thay đổi cấu hình sẽ tạo một revision mới. Traffic có thể được chuyển đến revision mới ngay, giữ revision mới không nhận traffic, hoặc chia tỷ lệ giữa nhiều revision để kiểm thử và phát hành dần.

### Quyền cần có

Build service account triển khai Cloud Run thường cần:

- Quyền quản lý Cloud Run service, thường là roles/run.admin ở phạm vi phù hợp.
- Quyền iam.serviceAccounts.actAs trên runtime service account được gắn cho service.
- Quyền đọc hoặc ghi Artifact Registry phù hợp với thao tác của pipeline.
- Quyền ghi log build nếu dùng Cloud Logging.

Vai trò chính xác phụ thuộc kiến trúc và phạm vi tài nguyên. Tránh cấp Owner hoặc Editor cho build service account. Runtime service account của ứng dụng được chỉ định riêng và không cần quyền deploy.

### Thêm step deploy Cloud Run

Sau bước push-image, thêm step:

~~~yaml
  - id: deploy-cloud-run
    name: gcr.io/google.com/cloudsdktool/google-cloud-cli:stable
    entrypoint: gcloud
    args:
      - run
      - deploy
      - $_SERVICE
      - --image
      - $_REGION-docker.pkg.dev/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$BUILD_ID
      - --region
      - $_REGION
      - --project
      - $PROJECT_ID
      - --platform
      - managed
      - --service-account
      - $_RUNTIME_SERVICE_ACCOUNT
      - --quiet
    waitFor:
      - push-image
~~~

Khai báo thêm các substitutions ở cấp build:

~~~yaml
substitutions:
  _REGION: asia-southeast1
  _AR_REPOSITORY: app-images
  _IMAGE: orders-api
  _SERVICE: orders-api
  _RUNTIME_SERVICE_ACCOUNT: orders-runtime@my-project.iam.gserviceaccount.com
~~~

Đây là đoạn bổ sung cho pipeline ở phần trước. Hãy hợp nhất các trường substitutions vào cùng một khối, không tạo hai khóa substitutions trong cùng tệp YAML. Thay project, region, repository, service và runtime service account bằng giá trị của môi trường thực tế.

Lệnh deploy ở ví dụ không tự mở quyền truy cập công khai. Nếu service cần truy cập công khai, hãy quyết định riêng và cấu hình IAM invoker theo chính sách của tổ chức. Với service nội bộ, giữ yêu cầu xác thực và cấu hình ingress phù hợp.

### Cấu hình runtime

Có thể khai báo cấu hình khi deploy:

~~~bash
gcloud run deploy orders-api \
  --image="asia-southeast1-docker.pkg.dev/my-project/app-images/orders-api:BUILD_ID" \
  --region=asia-southeast1 \
  --service-account="orders-runtime@my-project.iam.gserviceaccount.com" \
  --set-env-vars="APP_ENV=production,LOG_LEVEL=INFO" \
  --min=1 \
  --max=20 \
  --concurrency=80
~~~

Các giá trị này là ví dụ và cần được điều chỉnh theo tải, chi phí và hành vi ứng dụng. Không truyền password hoặc token qua --set-env-vars; hãy dùng Secret Manager integration của Cloud Run hoặc cơ chế đọc secret phù hợp. Hãy quản lý cấu hình theo môi trường để một lần deploy không vô tình ghi đè cấu hình cần thiết của service.

### Xác minh revision mới

Sau khi deploy:

~~~bash
gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --format="value(status.latestReadyRevisionName,status.url)"
~~~

Có thể xem danh sách revision:

~~~bash
gcloud run revisions list \
  --service=orders-api \
  --region=asia-southeast1
~~~

Smoke test nên kiểm tra endpoint health hoặc luồng nghiệp vụ tối thiểu. Nếu service yêu cầu authentication, dùng danh tính test có quyền invoker và lấy identity token theo cách an toàn. Không đánh giá deployment thành công chỉ vì lệnh gcloud trả về thành công; cần xác nhận revision Ready và request thực tế hoạt động.

### Phát hành không nhận traffic ngay

Với thay đổi rủi ro cao, có thể tạo revision mới mà chưa chuyển traffic:

~~~bash
gcloud run deploy orders-api \
  --image="asia-southeast1-docker.pkg.dev/my-project/app-images/orders-api:BUILD_ID" \
  --region=asia-southeast1 \
  --no-traffic \
  --tag=candidate
~~~

Revision được gắn tag candidate có URL riêng để kiểm tra trước khi nhận traffic chính. Sau khi smoke test và xác minh metrics đạt yêu cầu, có thể chuyển traffic bằng lệnh update-traffic:

~~~bash
gcloud run services update-traffic orders-api \
  --region=asia-southeast1 \
  --to-revisions=orders-api-00042-abc=90,orders-api-00043-def=10
~~~

Ví dụ trên chuyển 90% traffic đến revision ổn định và 10% đến revision mới. Thay tên revision bằng giá trị thực tế. Khi muốn đưa toàn bộ traffic đến revision mới nhất đã sẵn sàng, có thể dùng --to-latest. Trước khi chạy lệnh, hãy kiểm tra danh sách revision và tỷ lệ traffic hiện tại.

### Rollback Cloud Run

Nếu revision mới gây lỗi, có thể chuyển traffic về revision ổn định trước đó:

~~~bash
gcloud run services update-traffic orders-api \
  --region=asia-southeast1 \
  --to-revisions=orders-api-00042-abc=100
~~~

Tên revision trong ví dụ chỉ minh họa. Hãy lấy revision thực tế từ Cloud Run trước khi rollback. Rollback traffic không tự hoàn tác thay đổi database schema hoặc dữ liệu; cần đánh giá khả năng tương thích ngược của ứng dụng và migration trước mỗi lần phát hành.

## 5. Triển khai tự động lên Google Kubernetes Engine

GKE chạy ứng dụng trong Kubernetes cluster. Pipeline thường build và push image lên Artifact Registry, sau đó cập nhật manifest hoặc image của Deployment để Kubernetes tạo ReplicaSet và Pod mới. Deployment controller theo dõi trạng thái rollout và duy trì số replica mong muốn.

### Chuẩn bị cluster và namespace

Pipeline cần biết project, cluster, location và namespace. Cluster có thể là regional hoặc zonal; dùng đúng cờ --region hoặc --zone khi lấy thông tin cluster. Namespace giúp phân chia workload theo môi trường hoặc nhóm ứng dụng, nhưng không thay thế IAM và Kubernetes RBAC.

Ví dụ tạo namespace:

~~~bash
kubectl create namespace production
~~~

Trong môi trường production, namespace thường được quản lý bằng manifest hoặc GitOps thay vì tạo thủ công trong từng lần build.

### Manifest Kubernetes

Ví dụ Deployment cho ứng dụng Java:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: REGION-docker.pkg.dev/PROJECT_ID/app-images/orders-api:IMAGE_TAG
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
          startupProbe:
            httpGet:
              path: /actuator/health
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 3
~~~

Manifest này giả định ứng dụng Spring Boot có các endpoint health tương ứng và lắng nghe cổng 8080. Nếu dùng framework khác, hãy thay path và port bằng endpoint thực tế. Startup probe cho ứng dụng thời gian khởi động; readiness probe quyết định Pod có nhận traffic hay chưa; liveness probe phát hiện container không còn hoạt động đúng để kubelet khởi động lại.

Requests và limits cần dựa trên kiểm thử tải và quan sát thực tế. Requests ảnh hưởng scheduling; limits giới hạn tài nguyên container. Cấu hình quá thấp có thể gây throttling hoặc OOMKilled; cấu hình quá cao có thể lãng phí capacity.

### Cấp quyền cho build service account

Để triển khai vào GKE, build service account cần quyền lấy cluster credentials và quyền Kubernetes API tương ứng. IAM role như roles/container.developer có thể cung cấp quyền quản lý workload ở mức phù hợp, nhưng Kubernetes RBAC trong cluster vẫn có thể giới hạn những hành động được phép. Một số thao tác quản trị cluster cần quyền cao hơn; không cấp quyền cluster-admin cho pipeline ứng dụng nếu chỉ cần cập nhật Deployment trong namespace riêng.

Build service account cũng cần quyền push image vào Artifact Registry. Pod runtime dùng Kubernetes ServiceAccount orders-api trong ví dụ; nếu workload gọi Google Cloud API, cấu hình Workload Identity Federation for GKE để danh tính này chỉ nhận các quyền cần thiết.

### Triển khai bằng gke-deploy builder

Cloud Build cung cấp builder gke-deploy để triển khai manifest lên GKE. Sau khi image đã được push, thêm step:

~~~yaml
  - id: deploy-gke
    name: gcr.io/cloud-builders/gke-deploy
    args:
      - run
      - --filename=k8s/
      - --image=$_REGION-docker.pkg.dev/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$BUILD_ID
      - --location=$_GKE_LOCATION
      - --cluster=$_GKE_CLUSTER
      - --namespace=$_GKE_NAMESPACE
    waitFor:
      - push-image
~~~

Thêm substitutions phù hợp:

~~~yaml
substitutions:
  _REGION: asia-southeast1
  _AR_REPOSITORY: app-images
  _IMAGE: orders-api
  _GKE_LOCATION: asia-southeast1
  _GKE_CLUSTER: production-cluster
  _GKE_NAMESPACE: production
~~~

Đây là step bổ sung cho pipeline build/push ở phần trước. Hãy hợp nhất substitutions vào một khối duy nhất. Thư mục k8s/ cần chứa manifest hợp lệ. Builder dùng image được truyền qua --image để cập nhật image tham chiếu trong manifest theo cơ chế của gke-deploy, sau đó áp dụng manifest lên cluster.

### Triển khai bằng kubectl builder

Một cách khác là dùng kubectl builder khi muốn kiểm soát rõ các lệnh Kubernetes:

~~~yaml
  - id: apply-manifests
    name: gcr.io/cloud-builders/kubectl
    args:
      - apply
      - -f
      - k8s/
    env:
      - CLOUDSDK_COMPUTE_REGION=asia-southeast1
      - CLOUDSDK_CONTAINER_CLUSTER=production-cluster
    waitFor:
      - push-image
~~~

Builder cần biết cluster và location để lấy credentials. Cách này chỉ áp dụng manifest như nội dung đang có; pipeline phải cập nhật image tag hoặc manifest trước đó. Có thể dùng substitutions để tạo manifest đã render hoặc chạy kubectl set image sau khi apply, nhưng phải bảo đảm Deployment không chạy image cũ trong khoảng thời gian giữa hai lệnh. Với pipeline đơn giản, gke-deploy thường giúp gắn image được build vào manifest rõ ràng hơn.

Không dùng đồng thời gke-deploy và kubectl apply cho cùng một manifest nếu không có lý do, vì có thể tạo hai lần cập nhật và làm khó truy vết rollout.

### Theo dõi rollout và kiểm tra Pod

Sau khi apply:

~~~bash
kubectl rollout status deployment/orders-api \
  --namespace=production \
  --timeout=5m
~~~

Xem các Pod:

~~~bash
kubectl get pods \
  --namespace=production \
  -l app=orders-api
~~~

Xem trạng thái Deployment:

~~~bash
kubectl describe deployment orders-api \
  --namespace=production
~~~

Nếu rollout không hoàn tất, kiểm tra events, readiness probe, image pull, resource requests, quota, node capacity và log container. Không tiếp tục bước smoke test nếu rollout vẫn đang thất bại hoặc Pod chưa Ready.

### Rollback GKE

Kubernetes Deployment lưu lịch sử rollout nếu revision history được giữ lại. Có thể quay lại revision trước:

~~~bash
kubectl rollout history deployment/orders-api \
  --namespace=production

kubectl rollout undo deployment/orders-api \
  --namespace=production
~~~

Sau rollback, xác nhận rollout hoàn tất và Pod chạy image đúng. Rollback Deployment không tự hoàn tác migration database hoặc thay đổi resource khác được áp dụng trong cùng pipeline. Với thay đổi schema, cần chiến lược expand-and-contract để ứng dụng cũ và mới có thể cùng hoạt động trong giai đoạn chuyển đổi.

## 6. Một pipeline có thể triển khai Cloud Run hoặc GKE

Cùng một image có thể được phát hành đến một trong hai nền tảng bằng substitution hoặc trigger riêng. Không nên để một biến đầu vào tùy ý quyết định production target mà không có kiểm soát quyền.

Ví dụ cách tổ chức:

| Trigger | Source | Build | Deploy target |
|---|---|---|---|
| Pull request | Branch feature | Test, scan, build thử | Không deploy production |
| Merge vào main | Branch main | Test, build, push image | Cloud Run staging hoặc GKE staging |
| Release tag | Tag phiên bản | Xác minh artifact và provenance | Production qua approval |

Có thể dùng một build config chung với các substitutions như _TARGET, _REGION, _SERVICE hoặc _GKE_CLUSTER. Tuy nhiên, nếu Cloud Run và GKE có quyền hoặc quy trình khác nhau đáng kể, hai trigger hoặc hai config tách biệt thường dễ review và giới hạn quyền hơn.

### Ví dụ kiểm tra target

Một step shell có thể xác thực biến bắt buộc trước khi deploy:

~~~yaml
  - id: validate-deploy-input
    name: bash
    entrypoint: bash
    args:
      - -ceu
      - |
        test -n "$_TARGET"
        case "$_TARGET" in
          cloud-run|gke) ;;
          *) echo "Unsupported deployment target" >&2; exit 1 ;;
        esac
    waitFor:
      - push-image
~~~

Ví dụ minh họa cách kiểm tra target; cần escape biến shell nếu script sử dụng biến môi trường do shell mở rộng. Với Cloud Build substitutions, giá trị custom bắt đầu bằng dấu gạch dưới và được thay trước khi step chạy. Hãy khai báo rõ default hoặc dùng MUST_MATCH cho biến bắt buộc để tránh chuỗi rỗng.

## 7. Cloud Build triggers và quy trình phê duyệt

Cloud Build trigger có thể khởi chạy khi có push branch, push tag hoặc pull request. Với phát hành production, nên dùng trigger riêng gắn với tag release hoặc quy trình release được bảo vệ.

Một quy trình điển hình:

1. Pull request chạy compile, unit test, static analysis và dependency scan.
2. Merge vào main tạo image, push Artifact Registry và triển khai staging.
3. Smoke test, integration test và kiểm tra SLI xác nhận staging hoạt động.
4. Release tag hoặc thao tác phê duyệt khởi chạy pipeline production.
5. Pipeline production dùng image digest đã được kiểm tra ở staging.
6. Sau deploy, pipeline kiểm tra revision hoặc rollout và chạy smoke test.
7. Theo dõi metrics trong khoảng thời gian quan sát trước khi đóng phát hành.

Cloud Build approval có thể yêu cầu người được ủy quyền phê duyệt build trước khi các bước tiếp theo tiếp tục. Hãy cấu hình quyền phê duyệt cho nhóm phù hợp và giữ log của quyết định phát hành.

Không để pull request từ fork hoặc nguồn không đáng tin cậy chạy với service account có quyền deploy production hay đọc secret. Một build script có thể thực thi lệnh tùy ý; do đó, mức tin cậy của source phải quyết định danh tính và quyền được cấp cho build.

## 8. Kiểm tra sau triển khai

Một lệnh deploy thành công chỉ xác nhận API chấp nhận cấu hình. Nó chưa chứng minh ứng dụng sẵn sàng phục vụ người dùng. Pipeline nên có bước xác minh theo từng nền tảng.

### Cloud Run

- Revision mới ở trạng thái Ready.
- Service URL hoặc endpoint nội bộ có thể truy cập bằng danh tính phù hợp.
- Smoke test trả kết quả mong đợi.
- Logs không có lỗi khởi động, thiếu secret hoặc kết nối dependency.
- Request count, error rate và latency không suy giảm bất thường.
- Traffic đang trỏ đến revision dự kiến.

### GKE

- Deployment rollout hoàn tất.
- Số replica Ready đạt desired replicas.
- Pod không bị CrashLoopBackOff, ImagePullBackOff hoặc OOMKilled.
- Readiness probe thành công trước khi Pod nhận traffic.
- Service và Ingress/Gateway trỏ đến endpoint đúng.
- Metrics, logs và events không cho thấy lỗi bất thường.

### Smoke test

Ví dụ kiểm tra một endpoint health công khai:

~~~bash
curl --fail --silent --show-error \
  "https://orders-api-EXAMPLE.run.app/actuator/health"
~~~

Nếu endpoint yêu cầu xác thực, cần lấy identity token từ danh tính test được cấp quyền invoker. Không tắt authentication chỉ để làm cho smoke test đơn giản hơn. Với GKE service nội bộ, chạy test từ một runner có network access phù hợp hoặc dùng job kiểm thử trong cluster.

Smoke test nên kiểm tra một số luồng quan trọng và nhanh. Integration test sâu, kiểm thử tải hoặc kiểm tra dữ liệu nên được thiết kế thành stage riêng, tránh làm cho mỗi lần deploy kéo dài không cần thiết.

## 9. Chiến lược rollout và giảm blast radius

Không phải mọi release đều nên chuyển 100% traffic ngay lập tức. Chọn chiến lược theo rủi ro thay đổi, khả năng quan sát và khả năng tương thích dữ liệu.

### Cloud Run revisions và traffic splitting

Cloud Run tạo revision bất biến cho mỗi lần deploy cấu hình mới. Có thể:

- Chuyển toàn bộ traffic sang revision mới.
- Deploy revision mới với --no-traffic để kiểm tra trước.
- Gắn tag cho revision candidate để truy cập URL riêng.
- Chia traffic theo tỷ lệ giữa các revision.
- Quay traffic về revision ổn định khi metrics xấu đi.

Khi tăng traffic theo từng bước, hãy quan sát error ratio, latency, saturation và các chỉ số nghiệp vụ. Không chỉ dựa vào một request health thành công.

### GKE rolling update

Kubernetes Deployment hỗ trợ RollingUpdate với maxSurge và maxUnavailable. maxSurge giới hạn số Pod vượt số replica mong muốn trong quá trình cập nhật; maxUnavailable giới hạn số Pod có thể không sẵn sàng. Cấu hình maxUnavailable bằng 0 giúp duy trì số Pod sẵn sàng trong rollout nếu cluster có đủ capacity và readiness probe phản ánh đúng trạng thái.

Rolling update thay thế Pod theo từng bước nhưng không mặc định cung cấp weighted traffic split giữa hai phiên bản. Nếu cần canary theo phần trăm traffic, dùng Gateway, service mesh hoặc progressive delivery controller phù hợp và kiểm tra cách định tuyến thực tế.

### Điều kiện dừng rollout

Xác định trước các tín hiệu cần dừng hoặc rollback:

- Error rate vượt ngưỡng trong một khoảng thời gian.
- P95/P99 latency tăng vượt SLO hoặc baseline đã xác định.
- Pod liên tục restart hoặc revision không Ready.
- Queue age hoặc backlog tăng bất thường.
- Lỗi nghiệp vụ như thanh toán thất bại hoặc đơn hàng bị xử lý trùng tăng.
- Smoke test hoặc synthetic check thất bại.

Alert và điều kiện rollout nên dùng metric phản ánh tác động người dùng. CPU cao có thể là dấu hiệu cần điều tra, nhưng không phải lúc nào cũng đồng nghĩa release thất bại.

## 10. Database migration và tương thích ngược

Rollback ứng dụng chỉ an toàn khi phiên bản trước có thể hoạt động với trạng thái dữ liệu hiện tại. Nếu release xóa cột hoặc đổi kiểu dữ liệu ngay lập tức, revision cũ có thể không khởi động được sau rollback.

Dùng chiến lược expand-and-contract:

1. **Expand:** thêm bảng, cột hoặc cấu trúc mới theo cách vẫn tương thích với ứng dụng cũ.
2. **Deploy compatible code:** phát hành code có thể đọc/ghi theo cả cấu trúc cũ và mới khi cần.
3. **Migrate data:** chuyển dữ liệu theo batch và xác minh.
4. **Switch reads/writes:** chuyển dần ứng dụng sang cấu trúc mới.
5. **Contract:** chỉ xóa cấu trúc cũ sau khi mọi revision và consumer đã chuyển đổi.

Migration có thể cần chạy một lần như bước riêng trước hoặc sau deploy. Không chạy migration không idempotent trong mọi replica khởi động. Dùng job hoặc stage có kiểm soát, log kết quả và phương án phục hồi.

## 11. Bảo mật trong pipeline triển khai

Pipeline có quyền deploy production là một thành phần có đặc quyền. Cần bảo vệ source, build config, image và danh tính thực thi.

- Dùng build service account riêng theo môi trường hoặc mục đích.
- Cấp quyền deploy Cloud Run hoặc GKE ở phạm vi nhỏ nhất.
- Giới hạn iam.serviceAccounts.actAs vào runtime service account được phép.
- Cấp Artifact Registry writer cho repository cần push; cấp reader cho runtime principal khi cần.
- Không lưu credential trong substitutions, Dockerfile hoặc source.
- Đọc secret qua Secret Manager và chỉ cấp cho step cần dùng.
- Tách trigger từ pull request không tin cậy khỏi trigger release.
- Yêu cầu approval cho production nếu quy trình cần kiểm soát thủ công.
- Dùng image digest để bảo đảm staging và production chạy cùng artifact.
- Quét image, dependency và tạo/kiểm tra provenance theo chính sách supply chain.
- Ghi lại ai đã khởi chạy, phê duyệt và triển khai release.

Với GKE, phân biệt quyền IAM truy cập cluster với Kubernetes RBAC trong cluster. Một principal có thể lấy credentials nhưng vẫn không có quyền tạo Deployment trong namespace. Cấp Role và RoleBinding cho namespace khi phù hợp, thay vì cluster-admin.

## 12. Theo dõi deployment bằng Cloud Monitoring và Cloud Logging

Sau mỗi lần phát hành, cần liên kết deployment với tín hiệu vận hành:

- Ghi build ID, commit SHA, image tag và digest vào metadata phát hành.
- Ghi revision Cloud Run hoặc image version của GKE workload.
- Theo dõi request count, error rate, latency và instance/Pod health.
- Theo dõi CPU, memory, restart count, queue depth và dependency latency.
- Dùng structured logs có service, environment, revision và trace context.
- Tạo dashboard release để so sánh baseline trước và sau deploy.
- Tạo alert cho lỗi ảnh hưởng người dùng, không chỉ alert cho trạng thái tài nguyên.

Khi có sự cố, các thông tin này giúp xác định release nào tạo ra thay đổi, môi trường nào bị ảnh hưởng và có nên rollback hay không. Không đưa token hoặc dữ liệu cá nhân vào build metadata hay log.

## 13. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Cloud Run deploy bị permission denied | Build service account thiếu run.admin hoặc actAs | Kiểm tra IAM trên service và runtime service account |
| Cloud Run revision không Ready | Container không khởi động, sai port hoặc thiếu cấu hình | Xem revision condition và logs |
| Cloud Run không pull được image | Sai image URI hoặc thiếu Artifact Registry reader | Kiểm tra repository location và runtime service agent |
| GKE lấy cluster credentials thất bại | Sai project/location/cluster hoặc thiếu IAM | Kiểm tra cluster và quyền container |
| kubectl apply bị Forbidden | Thiếu Kubernetes RBAC | Kiểm tra RoleBinding trong namespace |
| Pod ImagePullBackOff | Sai image path, tag hoặc quyền pull | Xem Pod events và image URI |
| Pod CrashLoopBackOff | App lỗi khởi động hoặc cấu hình thiếu | Xem container logs, secret và dependency |
| Rollout bị treo | Readiness probe thất bại hoặc thiếu capacity | Xem rollout status, Pod conditions và events |
| Smoke test trả 401/403 | Endpoint yêu cầu xác thực | Dùng danh tính test có quyền phù hợp |
| Rollback app nhưng lỗi vẫn còn | Database migration hoặc side effect không tương thích | Kiểm tra schema, dữ liệu và dependency state |

Không giải quyết lỗi permission bằng cách cấp Owner hoặc cluster-admin ngay lập tức. Xác định chính xác API hoặc Kubernetes resource bị từ chối rồi cấp quyền cần thiết ở phạm vi nhỏ nhất.

## 14. Bài tập thực hành: triển khai Java service lên Cloud Run và GKE

Giả sử repository có ứng dụng Java tên orders-api. Nhóm cần build một image và triển khai cùng artifact lên Cloud Run staging và GKE staging.

Thực hiện:

1. Tạo Artifact Registry repository trong region đã chọn.
2. Tạo runtime service account cho Cloud Run và Kubernetes workload.
3. Tạo build service account có quyền test/build/push và deploy đúng phạm vi.
4. Viết Cloud Build config chạy Maven verify, build Docker image và push với tag BUILD_ID.
5. Lưu image URI và digest của build.
6. Thêm step deploy Cloud Run staging bằng gcloud run deploy.
7. Kiểm tra revision Ready và chạy smoke test bằng danh tính phù hợp.
8. Chuẩn bị manifest Kubernetes Deployment có resource requests/limits và startup/readiness/liveness probes.
9. Thêm step gke-deploy hoặc kubectl để cập nhật workload trên cluster staging.
10. Theo dõi kubectl rollout status và xác nhận replica Ready.
11. Chạy smoke test cho service GKE từ mạng có thể truy cập endpoint.
12. Mô phỏng một image có lỗi khởi động trong môi trường thử nghiệm; quan sát revision hoặc rollout không đạt health.
13. Thực hiện rollback về revision/image ổn định và xác minh lại.
14. Tạo trigger riêng cho main và release tag; kiểm tra trigger production có approval và quyền riêng.
15. Xác nhận Cloud Run và GKE dùng cùng image digest đã được kiểm thử.

### Tiêu chí hoàn thành

- Build và test hoàn tất trước khi deploy.
- Image được push lên đúng Artifact Registry repository.
- Build ID, commit và digest có thể truy vết.
- Cloud Run revision Ready và smoke test thành công.
- GKE rollout hoàn tất và số replica Ready đúng mong muốn.
- Runtime identity khác build identity và có quyền tối thiểu.
- Rollback đã được thử trong môi trường staging.
- Trigger production có ranh giới quyền và phê duyệt rõ ràng.

## Checklist trước khi tự động triển khai production

- [ ] Build tạo artifact một lần và dùng cùng artifact qua các môi trường.
- [ ] Image được lưu trong Artifact Registry và có digest để truy vết.
- [ ] Build service account và runtime service account được tách riêng.
- [ ] Quyền Cloud Run, Artifact Registry, GKE IAM và Kubernetes RBAC được giới hạn.
- [ ] Trigger pull request không có quyền production hoặc secret nhạy cảm.
- [ ] Production release có approval hoặc kiểm soát tương đương.
- [ ] Cloud Run revision được kiểm tra Ready trước khi chuyển traffic.
- [ ] GKE Deployment có readiness probe và rollout status được xác minh.
- [ ] Smoke test chạy bằng danh tính và network phù hợp.
- [ ] Rollout có điều kiện dừng và phương án rollback.
- [ ] Database migration tương thích với phiên bản cũ trong giai đoạn chuyển đổi.
- [ ] Metrics, logs và trace có thông tin revision/image để điều tra.
- [ ] Secret không xuất hiện trong build config, substitutions hoặc log.
- [ ] Artifact, build và deployment có thể truy ngược đến source commit.

## Câu hỏi tự kiểm tra

**1. Vì sao nên build image một lần rồi dùng cùng image cho staging và production?**

Điều đó giúp bảo đảm artifact đã được kiểm thử chính là artifact được phát hành, đồng thời hỗ trợ truy vết bằng image digest.

**2. Build service account khác runtime service account như thế nào?**

Build service account thực hiện build, push và deploy. Runtime service account là danh tính ứng dụng dùng khi chạy để truy cập các dịch vụ cần thiết.

**3. Cloud Run revision có ích gì cho rollout và rollback?**

Mỗi revision giữ một phiên bản cấu hình và image. Có thể kiểm tra revision mới, chia traffic theo tỷ lệ và chuyển traffic về revision ổn định.

**4. readiness probe trong GKE ảnh hưởng thế nào đến rollout?**

Probe xác định Pod đã sẵn sàng nhận traffic hay chưa. Deployment controller dùng trạng thái readiness để điều phối rolling update.

**5. Vì sao lấy được GKE credentials chưa chắc đã deploy được workload?**

IAM cho phép truy cập cluster, nhưng Kubernetes RBAC vẫn có thể từ chối thao tác trên Deployment hoặc namespace.

**6. Vì sao rollback ứng dụng có thể không đủ sau database migration?**

Schema hoặc dữ liệu có thể đã thay đổi theo cách phiên bản ứng dụng cũ không còn tương thích. Cần migration theo chiến lược expand-and-contract và kế hoạch phục hồi dữ liệu.

**7. Điều kiện nào nên dừng rollout?**

Ví dụ error rate vượt ngưỡng, latency vượt SLO, revision không Ready, Pod restart liên tục, queue age tăng bất thường hoặc smoke test thất bại.

## Tài liệu tham khảo

- [Cloud Build: Deploying to Cloud Run](https://cloud.google.com/build/docs/deploying-builds/deploy-cloud-run)
- [Cloud Build: Deploying to GKE](https://cloud.google.com/build/docs/deploying-builds/deploy-gke)
- [Cloud Run: Deploying services](https://cloud.google.com/run/docs/deploying)
- [Cloud Run: Managing revisions and traffic](https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)
- [Cloud Run: Service identity](https://cloud.google.com/run/docs/securing/service-identity)
- [GKE: Deploying applications](https://cloud.google.com/kubernetes-engine/docs/how-to/deploying-workloads)
- [Kubernetes: Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes: Configure liveness, readiness and startup probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Google Cloud: Workload Identity Federation for GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity)
- [Artifact Registry: Configure access control](https://cloud.google.com/artifact-registry/docs/access-control)

## Kết luận

Triển khai tự động lên Cloud Run và GKE cần một chuỗi bước có thể truy vết từ source commit đến image và runtime. Cloud Build kiểm thử, tạo và push artifact; build service account thực hiện deploy với quyền tối thiểu; runtime identity được tách riêng cho ứng dụng. Cloud Run dùng revision và traffic management để phát hành dần, còn GKE dùng Deployment rollout, probes và Kubernetes RBAC để kiểm soát workload. Smoke test, metrics, logs, trace và kế hoạch rollback xác nhận rằng release thực sự hoạt động. Khi pipeline kết hợp artifact bất biến, approval phù hợp và kiểm tra sức khỏe sau deploy, nhóm có thể phát hành thường xuyên mà vẫn kiểm soát rủi ro.
