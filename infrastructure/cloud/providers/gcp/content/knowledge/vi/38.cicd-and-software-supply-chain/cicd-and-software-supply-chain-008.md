# Cloud Deploy delivery pipelines, targets và releases

Cloud Deploy là dịch vụ triển khai liên tục được quản lý trên Google Cloud. Dịch vụ điều phối việc đưa một phiên bản ứng dụng qua các môi trường như development, staging và production, đồng thời lưu lại release, rollout, trạng thái từng bước và kết quả phê duyệt.

Trong một quy trình CI/CD, Cloud Build hoặc hệ thống CI khác có thể build và kiểm thử ứng dụng, đóng gói image rồi đẩy lên Artifact Registry. Cloud Deploy tiếp nhận source cùng cấu hình triển khai, render manifest bằng Skaffold, tạo release và triển khai release đó đến các target theo thứ tự pipeline.

Ba khái niệm cốt lõi cần phân biệt:

- **Delivery pipeline** mô tả luồng phát hành và thứ tự các môi trường.
- **Target** mô tả đích triển khai, chẳng hạn một GKE cluster hoặc một khu vực Cloud Run.
- **Release** đại diện cho một phiên bản ứng dụng cùng cấu hình và artifact triển khai đã được chuẩn bị. Khi release được triển khai đến một target, Cloud Deploy tạo một **rollout** để theo dõi tiến trình thực hiện.

Bài học này hướng dẫn thiết kế pipeline, khai báo target, tạo release, promote giữa các môi trường, kiểm soát approval, theo dõi rollout và vận hành Cloud Deploy an toàn cho GKE và Cloud Run.

## 1. Kiến trúc và vòng đời phát hành

Cloud Deploy tách việc build artifact khỏi việc triển khai artifact. CI pipeline chịu trách nhiệm tạo image có thể triển khai, chạy kiểm thử và lưu image vào Artifact Registry. Cloud Deploy dùng Skaffold để render và deploy cấu hình đến target.

~~~mermaid
flowchart TD
    A[Source repository] --> B[Cloud Build or CI]
    B --> C[Build and test]
    C --> D[Artifact Registry image]
    D --> E[Create Cloud Deploy release]
    E --> F[Render with Skaffold]
    F --> G[Delivery pipeline]
    G --> H[Staging target]
    H --> I[Review and approval]
    I --> J[Production target]
    J --> K[Verify rollout and service health]
~~~

Luồng phát hành điển hình:

1. Developer merge thay đổi vào nhánh phát hành.
2. CI chạy test, scan dependency và build container image.
3. CI đẩy image lên Artifact Registry, tốt nhất tham chiếu bằng digest.
4. CI hoặc người phát hành tạo release trong Cloud Deploy.
5. Cloud Deploy render manifest cho release và target tương ứng.
6. Rollout đầu tiên triển khai release đến target đầu tiên trong pipeline.
7. Sau khi kiểm tra staging, release được promote sang target tiếp theo.
8. Target có yêu cầu phê duyệt sẽ chờ approver trước khi triển khai.
9. Nhóm theo dõi rollout, xác minh ứng dụng và ghi lại kết quả.

Cloud Deploy quản lý quá trình triển khai, nhưng không thay thế kiểm thử ứng dụng, quản lý source, build, quét lỗ hổng hoặc quản trị artifact. Các bước này nên hoàn thành trước khi tạo release.

## 2. Các đối tượng chính của Cloud Deploy

| Đối tượng | Vai trò | Ví dụ |
|---|---|---|
| Delivery pipeline | Mô tả luồng target và chiến lược triển khai | orders-pipeline |
| Target | Đại diện cho môi trường hoặc đích triển khai | orders-staging, orders-prod |
| Skaffold configuration | Mô tả cách render manifest và deploy ứng dụng | skaffold.yaml |
| Release | Phiên bản phát hành được tạo từ source và artifact | orders-v1-8-0 |
| Rollout | Một lần triển khai release đến một target | rollout đến staging |
| Job | Một đơn vị công việc trong rollout | render, deploy, verify |
| Phase | Giai đoạn triển khai của rollout | canary hoặc stable |
| Approval | Quyết định cho phép tiếp tục rollout khi target yêu cầu | production approval |

Delivery pipeline và target là tài nguyên cấu hình của Cloud Deploy. Release và rollout là đối tượng phát sinh trong quá trình phát hành.

Một pipeline có thể triển khai đến nhiều target. Một target có thể được dùng trong một hoặc nhiều pipeline nếu thiết kế và quyền truy cập cho phép. Tuy nhiên, nên đặt tên và ranh giới target rõ ràng để tránh deploy nhầm môi trường.

## 3. Chuẩn bị project và dịch vụ

Trước khi tạo pipeline, xác định project chứa Cloud Deploy, region của delivery pipeline, project chứa Artifact Registry và project hoặc cluster đích. Cloud Deploy control plane có region riêng; target có thể nằm ở project hoặc location khác nếu đã cấu hình quyền và kết nối phù hợp.

Bật các API cần thiết, ví dụ:

~~~bash
gcloud services enable clouddeploy.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  container.googleapis.com \
  --project="PROJECT_ID"
~~~

Nếu triển khai Cloud Run, bật thêm Cloud Run API:

~~~bash
gcloud services enable run.googleapis.com \
  --project="PROJECT_ID"
~~~

Người thực hiện cần quyền bật service API. Project cũng cần có Artifact Registry repository, image đã build và các target GKE hoặc Cloud Run sẵn sàng.

### Chọn region

Region của Cloud Deploy là nơi quản lý pipeline, release và rollout. Region của target là vị trí workload chạy. Hai giá trị này không nhất thiết phải giống nhau, nhưng cần xem xét:

- Độ trễ và chi phí truyền artifact.
- Yêu cầu data residency.
- Kết nối từ môi trường triển khai đến target.
- Chính sách tổ chức về region được phép.
- Tính sẵn sàng của dịch vụ Cloud Deploy tại region đã chọn.

Không đặt region của pipeline theo thói quen mà không đối chiếu với kiến trúc và chính sách của tổ chức.

## 4. Khai báo delivery pipeline và GKE targets

Cloud Deploy dùng file cấu hình YAML để định nghĩa pipeline và target. Ví dụ dưới đây tạo pipeline có hai target: staging và production.

~~~yaml
apiVersion: deploy.cloud.google.com/v1
kind: DeliveryPipeline
metadata:
  name: orders-pipeline
description: Deploy orders-api through staging and production
serialPipeline:
  stages:
    - targetId: orders-staging
    - targetId: orders-prod
---
apiVersion: deploy.cloud.google.com/v1
kind: Target
metadata:
  name: orders-staging
description: Staging GKE cluster
gke:
  cluster: projects/PROJECT_ID/locations/asia-southeast1/clusters/orders-staging
---
apiVersion: deploy.cloud.google.com/v1
kind: Target
metadata:
  name: orders-prod
description: Production GKE cluster
requireApproval: true
gke:
  cluster: projects/PROJECT_ID/locations/asia-southeast1/clusters/orders-prod
~~~

Trong ví dụ:

- `metadata.name` của DeliveryPipeline là tên pipeline.
- `serialPipeline.stages` xác định thứ tự triển khai.
- `targetId` phải trùng với tên target được khai báo.
- `gke.cluster` là đường dẫn đầy đủ đến GKE cluster.
- `requireApproval: true` yêu cầu phê duyệt khi rollout đến production target.

Đăng ký cấu hình với Cloud Deploy:

~~~bash
gcloud deploy apply \
  --file="clouddeploy.yaml" \
  --region="asia-southeast1" \
  --project="PROJECT_ID"
~~~

Kiểm tra tài nguyên đã đăng ký:

~~~bash
gcloud deploy delivery-pipelines list \
  --region="asia-southeast1" \
  --project="PROJECT_ID"

gcloud deploy targets list \
  --region="asia-southeast1" \
  --project="PROJECT_ID"
~~~

Nếu target nằm ở project khác, cần xác nhận quyền của Cloud Deploy service agent và execution service account tại project đích. Việc khai báo đúng cluster path không tự cấp quyền triển khai vào cluster.

## 5. Khai báo Skaffold và manifest ứng dụng

Cloud Deploy dùng Skaffold để render manifest và gọi công cụ deploy phù hợp. Skaffold giúp tách cấu hình ứng dụng khỏi cơ chế điều phối release.

Ví dụ cấu hình cho ứng dụng GKE dùng Kubernetes manifests:

~~~yaml
apiVersion: skaffold/v4beta7
kind: Config
metadata:
  name: orders-api
manifests:
  rawYaml:
    - kubernetes/deployment.yaml
    - kubernetes/service.yaml
deploy:
  kubectl: {}
~~~

Deployment manifest có thể tham chiếu image placeholder để Cloud Deploy thay bằng image được cung cấp khi tạo release:

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
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: orders-api
          ports:
            - containerPort: 8080
~~~

Khi tạo release, ánh xạ image placeholder sang image trong Artifact Registry. Skaffold sẽ render manifest cho release và ghi nhận kết quả để Cloud Deploy sử dụng ở các rollout.

Với Helm hoặc Kustomize, Skaffold có thể dùng renderer tương ứng. Hãy chọn một cơ chế rõ ràng và kiểm tra output đã render trước khi triển khai. Không để các giá trị môi trường quan trọng phụ thuộc vào biến không được kiểm soát trong pipeline.

### Cấu hình theo target

Skaffold profiles có thể tùy chỉnh manifest cho staging và production, ví dụ số replica, tài nguyên, ingress hoặc tên namespace. Delivery pipeline có thể gắn profile với stage:

~~~yaml
serialPipeline:
  stages:
    - targetId: orders-staging
      profiles:
        - staging
    - targetId: orders-prod
      profiles:
        - production
~~~

Profile phải được khai báo trong Skaffold configuration. Tránh để profile production vô tình trỏ đến project, database hoặc secret của staging. Review manifest sau render để phát hiện sai cấu hình môi trường.

## 6. Tạo release và triển khai đến target đầu tiên

Sau khi pipeline, target và Skaffold config đã được đăng ký, tạo release từ source directory:

~~~bash
gcloud deploy releases create orders-v1-8-0 \
  --delivery-pipeline="orders-pipeline" \
  --region="asia-southeast1" \
  --source="." \
  --images="orders-api=asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api@sha256:IMAGE_DIGEST" \
  --project="PROJECT_ID"
~~~

Trong ví dụ, `orders-api` là tên image placeholder trong manifest; giá trị bên phải là image đã lưu ở Artifact Registry. Dùng digest giúp cố định chính xác image được triển khai, tránh trường hợp tag có thể bị trỏ sang nội dung khác.

Release thường tạo rollout đến target đầu tiên của pipeline. Theo dõi trạng thái:

~~~bash
gcloud deploy releases describe orders-v1-8-0 \
  --delivery-pipeline="orders-pipeline" \
  --region="asia-southeast1" \
  --project="PROJECT_ID"

gcloud deploy rollouts list \
  --delivery-pipeline="orders-pipeline" \
  --release="orders-v1-8-0" \
  --region="asia-southeast1" \
  --project="PROJECT_ID"
~~~

Một release lưu thông tin source, image, cấu hình Skaffold và kết quả render. Nếu tạo release mới, hãy dùng tên duy nhất theo quy ước phiên bản hoặc build number. Không dùng lại tên release để đại diện cho nội dung khác.

### Render và deploy

Cloud Deploy chia rollout thành các công việc. Render chuẩn bị manifest cho target; deploy áp dụng manifest đã render lên đích. Nhờ tách hai bước, nhóm có thể kiểm tra cấu hình đã render trước khi rollout tiếp tục.

Nếu render thành công nhưng deploy thất bại, xem job và log tương ứng để xác định nguyên nhân: quyền IAM, kết nối cluster, quota, manifest sai, image không truy cập được hoặc tài nguyên không hợp lệ.

## 7. Promote release qua các target

Sau khi release triển khai thành công lên staging và vượt qua kiểm thử, promote release đến production:

~~~bash
gcloud deploy releases promote \
  --release="orders-v1-8-0" \
  --delivery-pipeline="orders-pipeline" \
  --region="asia-southeast1" \
  --to-target="orders-prod" \
  --project="PROJECT_ID"
~~~

Promote tạo rollout mới đến target tiếp theo. Release vẫn là cùng một phiên bản ứng dụng; target-specific render hoặc profile có thể tạo cấu hình triển khai phù hợp môi trường.

Trước khi promote, xác nhận:

- Smoke test và integration test trên staging đã thành công.
- Image digest đúng với artifact đã kiểm tra.
- Database migration tương thích với phiên bản trước và phiên bản mới.
- Metrics, logs và alert không có dấu hiệu suy giảm.
- Release notes và change request đầy đủ.
- Target production có capacity và quyền triển khai phù hợp.

Không promote chỉ vì rollout staging có trạng thái Succeeded. Cần kiểm tra hành vi nghiệp vụ và các dependency quan trọng.

## 8. Approval, rollout và theo dõi trạng thái

Target có `requireApproval: true` sẽ chờ approver trước khi rollout tiếp tục. Đây là cơ chế tách người tạo release khỏi người phê duyệt triển khai đến môi trường nhạy cảm.

Liệt kê rollout:

~~~bash
gcloud deploy rollouts list \
  --delivery-pipeline="orders-pipeline" \
  --release="orders-v1-8-0" \
  --region="asia-southeast1" \
  --project="PROJECT_ID"
~~~

Xem chi tiết rollout:

~~~bash
gcloud deploy rollouts describe "ROLLOUT_NAME" \
  --delivery-pipeline="orders-pipeline" \
  --release="orders-v1-8-0" \
  --region="asia-southeast1" \
  --project="PROJECT_ID"
~~~

Phê duyệt rollout production:

~~~bash
gcloud deploy rollouts approve "ROLLOUT_NAME" \
  --delivery-pipeline="orders-pipeline" \
  --release="orders-v1-8-0" \
  --region="asia-southeast1" \
  --approve \
  --project="PROJECT_ID"
~~~

Tên rollout cần lấy từ danh sách hoặc chi tiết rollout thực tế. Không đoán tên rollout theo release vì tên có thể được tạo tự động.

### Các trạng thái cần theo dõi

- Pending approval: đang chờ approver.
- In progress: rollout đang chạy job hoặc phase.
- Succeeded: các bước triển khai đã hoàn tất.
- Failed: một job hoặc phase thất bại.
- Cancelled/abandoned: rollout đã bị hủy hoặc bỏ theo thao tác vận hành.

Tên trạng thái hiển thị có thể phụ thuộc trạng thái rollout và giao diện CLI. Khi gặp lỗi, kiểm tra job cụ thể, execution log và target health thay vì chỉ nhìn trạng thái tổng.

Approval là một quyết định có trách nhiệm. Approver cần xem release, target, image digest, kết quả kiểm thử, policy và tác động dự kiến trước khi cho phép rollout.

## 9. Progressive delivery, canary và verification

Không phải lúc nào cũng nên chuyển toàn bộ traffic sang phiên bản mới ngay lập tức. Progressive delivery chia quá trình phát hành thành các bước nhỏ để giới hạn tác động.

### Canary deployment

Canary triển khai phiên bản mới cho một phần workload hoặc traffic trước, quan sát kết quả rồi mới mở rộng. Ví dụ:

1. Đưa 5% traffic hoặc một nhóm replica sang phiên bản mới.
2. Theo dõi error rate, latency, saturation và chỉ số nghiệp vụ.
3. Tăng lên 25% hoặc 50% nếu các chỉ số đạt tiêu chí.
4. Chuyển toàn bộ traffic sau khi canary ổn định.
5. Dừng hoặc quay lại phiên bản cũ nếu SLO bị vi phạm.

Cloud Deploy hỗ trợ chiến lược canary cho các runtime được hỗ trợ. Cấu hình cụ thể phụ thuộc loại target và runtime configuration. Với GKE, cần cấu hình service networking hoặc cơ chế phân chia traffic phù hợp. Không giả định chỉ thêm phần trăm vào pipeline là có thể chia traffic nếu ứng dụng và cluster chưa được cấu hình để định tuyến canary.

### Verify jobs

Verification giúp chạy kiểm tra sau khi deploy, chẳng hạn smoke test, gọi health endpoint hoặc kiểm tra một truy vấn nghiệp vụ. Với Cloud Deploy, verification được cấu hình trong chiến lược triển khai được hỗ trợ và dùng execution environment phù hợp.

Một verify job nên:

- Kiểm tra health endpoint và readiness.
- Thực hiện một số request nghiệp vụ an toàn.
- Xác minh kết nối database hoặc dependency quan trọng.
- Kiểm tra error rate và latency trong cửa sổ quan sát.
- Trả kết quả rõ ràng để rollout tiếp tục hoặc thất bại.

Không dùng verify job để thực hiện migration dữ liệu không thể đảo ngược nếu chưa có kế hoạch riêng. Verification cần có timeout, quyền tối thiểu và log không chứa secret.

## 10. Cloud Run targets

Cloud Deploy cũng có thể triển khai Cloud Run service. Target Cloud Run chỉ định location của Cloud Run resource:

~~~yaml
apiVersion: deploy.cloud.google.com/v1
kind: Target
metadata:
  name: orders-run-prod
description: Production Cloud Run region
requireApproval: true
run:
  location: projects/PROJECT_ID/locations/asia-southeast1
~~~

Với Cloud Run, Skaffold dùng Cloud Run deployer và manifest service phù hợp:

~~~yaml
apiVersion: skaffold/v4beta7
kind: Config
metadata:
  name: orders-run
manifests:
  rawYaml:
    - cloudrun/service.yaml
deploy:
  cloudrun: {}
~~~

Cloud Run service manifest mô tả service, container image, port, tài nguyên và service account. Không đưa secret value trực tiếp vào manifest; tham chiếu Secret Manager hoặc cơ chế quản lý secret phù hợp.

Cloud Deploy tạo rollout đến Cloud Run target theo pipeline. Sau deploy, kiểm tra revision mới, traffic allocation, startup/readiness, log và metrics. Nếu dùng traffic splitting, xác minh revision cũ vẫn được giữ để có thể chuyển traffic lại khi cần.

### GKE và Cloud Run khác nhau ở target

| Khía cạnh | GKE target | Cloud Run target |
|---|---|---|
| Đích | Kubernetes cluster | Cloud Run location |
| Manifest | Kubernetes YAML, Helm hoặc Kustomize qua Skaffold | Cloud Run service manifest |
| Quyền triển khai | Quyền truy cập cluster và Kubernetes API | Quyền triển khai Cloud Run service |
| Kiểm chứng | Pod, Deployment, Service, ingress và cluster health | Revision, traffic, instance, request và service health |
| Rollback | Triển khai manifest/release trước hoặc điều chỉnh rollout | Chuyển traffic về revision ổn định hoặc triển khai release trước |

## 11. IAM và danh tính triển khai

Cloud Deploy sử dụng service agent do Google quản lý và danh tính thực thi để render/deploy. Người tạo release, người phê duyệt và service account triển khai có trách nhiệm khác nhau.

Một cách phân tách:

| Danh tính | Trách nhiệm |
|---|---|
| CI build identity | Build, test, scan và push image lên Artifact Registry |
| Release creator | Tạo release từ source và image đã được kiểm tra |
| Approver | Phê duyệt rollout đến target yêu cầu approval |
| Cloud Deploy service agent | Thực hiện các thao tác dịch vụ được cấp cho service agent |
| Execution service account | Chạy render/deploy job và truy cập target theo cấu hình |
| Runtime service account | Danh tính ứng dụng sử dụng khi chạy trên GKE hoặc Cloud Run |

Các IAM role Cloud Deploy phổ biến có thể gồm:

- `roles/clouddeploy.releaser`: tạo release và thao tác phát hành theo quyền của role.
- `roles/clouddeploy.approver`: phê duyệt rollout.
- `roles/clouddeploy.viewer`: xem tài nguyên Cloud Deploy.
- `roles/clouddeploy.operator`: thao tác vận hành được role cho phép.
- `roles/clouddeploy.admin`: quản trị Cloud Deploy rộng hơn.

Kiểm tra quyền chính xác theo tài liệu IAM và phạm vi project đang sử dụng. Không cấp Cloud Deploy Admin cho mọi developer chỉ để họ tạo release hoặc xem trạng thái.

### Quyền tại target

Execution service account cần quyền tương ứng tại đích:

- Với GKE, cần quyền truy cập cluster và quyền Kubernetes để áp dụng manifest.
- Với Cloud Run, cần quyền triển khai service và quyền sử dụng runtime service account nếu gắn service identity.
- Với Artifact Registry, cần quyền đọc image cần deploy.
- Với Cloud Storage staging bucket, cần quyền truy cập artifact theo cấu hình.

Tách execution identity khỏi runtime identity. Service account triển khai có quyền cập nhật workload; service account runtime chỉ có quyền ứng dụng cần khi chạy. Không dùng một danh tính có quyền Owner trên toàn project cho cả hai vai trò.

## 12. Bảo vệ chuỗi cung ứng phần mềm và artifact

Cloud Deploy nhận artifact để triển khai, vì vậy chất lượng và nguồn gốc artifact cần được kiểm soát từ trước khi tạo release.

Các thực hành nên áp dụng:

- Dùng image digest thay cho tag mutable như `latest`.
- Build image trong pipeline đáng tin cậy và giới hạn quyền push.
- Quét lỗ hổng container và dependency trước khi release.
- Lưu SBOM và build provenance theo chính sách tổ chức.
- Xác minh nguồn image, commit SHA và kết quả test.
- Dùng Binary Authorization trên GKE nếu kiến trúc yêu cầu xác minh attestation trước khi workload được phép chạy.
- Không đưa credential hoặc secret vào image layer.
- Giới hạn quyền đọc artifact và thời hạn lưu trữ.
- Ghi lại release name, digest, commit, pipeline và target đã triển khai.

Một release có thể được triển khai nhiều lần đến các target. Việc tái sử dụng cùng image digest giúp staging và production chạy cùng một binary, trong khi manifest hoặc tham số môi trường có thể khác nhau theo target.

### Cloud Deploy deploy parameters

Deploy parameters có thể truyền các giá trị cấu hình cho target hoặc stage trong các trường hợp được hỗ trợ. Dùng chúng cho các giá trị như tên namespace, số replica hoặc endpoint không nhạy cảm. Không dùng deploy parameter làm kho lưu secret; bí mật cần được lấy từ Secret Manager hoặc hệ thống quản lý bí mật phù hợp.

## 13. Rollback, retry và xử lý rollout thất bại

Khi rollout thất bại, cần xác định job nào lỗi và trạng thái target trước khi chọn hành động tiếp theo.

### Chẩn đoán

Kiểm tra:

1. Release và rollout đúng pipeline/target chưa.
2. Render job có thành công không.
3. Deploy job có lỗi IAM, manifest, quota hoặc API không.
4. Image digest có tồn tại và execution identity có quyền pull không.
5. GKE workload có Pod Pending, ImagePullBackOff, CrashLoopBackOff hoặc readiness failure không.
6. Cloud Run revision có khởi động được và nhận traffic không.
7. Verification job có thất bại do ứng dụng hay do test environment không.

Dùng Cloud Deploy rollout detail và execution logs để tìm lỗi cụ thể. Kiểm tra thêm Cloud Build logs, Cloud Logging, GKE events hoặc Cloud Run revision logs khi phù hợp.

### Retry và rollback

Retry phù hợp với lỗi tạm thời sau khi đã hiểu nguyên nhân, ví dụ API timeout hoặc một dependency tạm thời không sẵn sàng. Không retry vô hạn khi manifest sai, thiếu quyền hoặc image không tồn tại.

Rollback thường được thực hiện bằng cách triển khai lại một release đã biết tốt hoặc chuyển traffic về revision ổn định, tùy target. Khi dùng Cloud Deploy, tạo rollout để đưa release đã biết tốt đến target cần khôi phục theo quy trình của pipeline. Xác minh image digest, manifest, database compatibility và traffic sau rollback.

Rollback container không tự đảo ngược schema database hoặc dữ liệu đã ghi bởi phiên bản mới. Thiết kế database migration theo hướng tương thích ngược, tách migration phá hủy khỏi rollout ứng dụng và chuẩn bị phương án phục hồi dữ liệu riêng.

### Khi nào không nên retry?

- Policy hoặc approval gate chưa đạt.
- Image không đúng nguồn hoặc có lỗ hổng bị chặn.
- Manifest render ra sai project/namespace.
- Target production đang có sự cố rộng.
- Migration dữ liệu có thể đã chạy một phần.
- Retry có thể tạo tài nguyên trùng hoặc thao tác nghiệp vụ lặp.

Trong các trường hợp này, dừng rollout, ghi nhận trạng thái và tạo release mới sau khi sửa lỗi hoặc khôi phục.

## 14. Tình huống thực hành: phát hành orders-api từ staging lên production

Một nhóm có ứng dụng orders-api chạy trên GKE. Source được build bởi Cloud Build, image lưu ở Artifact Registry và Cloud Deploy điều phối qua hai target.

### Bước 1 — Chuẩn bị artifact

CI chạy unit test, integration test, dependency scan và container scan. Sau đó build image và push lên Artifact Registry. Lưu commit SHA, image digest, SBOM và kết quả kiểm thử.

### Bước 2 — Đăng ký pipeline

Tạo file clouddeploy.yaml với hai target staging và production. Production bật `requireApproval: true`. Chạy `gcloud deploy apply` ở đúng region của Cloud Deploy.

### Bước 3 — Tạo release

~~~bash
gcloud deploy releases create orders-v2-1-0 \
  --delivery-pipeline="orders-pipeline" \
  --region="asia-southeast1" \
  --source="." \
  --images="orders-api=asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api@sha256:IMAGE_DIGEST" \
  --project="PROJECT_ID"
~~~

Cloud Deploy render manifest và tạo rollout đến staging target.

### Bước 4 — Kiểm tra staging

- Theo dõi rollout và deploy job.
- Xác nhận Deployment có đủ replica Ready.
- Chạy smoke test và kiểm tra các luồng nghiệp vụ.
- Theo dõi error rate, p95 latency và log.
- Ghi lại kết quả kiểm thử cùng release name và image digest.

### Bước 5 — Promote và approval

~~~bash
gcloud deploy releases promote \
  --release="orders-v2-1-0" \
  --delivery-pipeline="orders-pipeline" \
  --region="asia-southeast1" \
  --to-target="orders-prod" \
  --project="PROJECT_ID"
~~~

Khi rollout production chờ approval, approver kiểm tra change request, test result, digest, policy và phạm vi ảnh hưởng. Sau khi phê duyệt, Cloud Deploy tiếp tục deploy.

### Bước 6 — Xác minh production

Kiểm tra rollout Succeeded, revision hoặc Deployment mới nhận traffic, request success ratio và latency nằm trong SLO. Nếu có dấu hiệu suy giảm, dừng promote tiếp theo và thực hiện rollback theo release đã biết tốt.

## 15. Checklist vận hành Cloud Deploy

### Trước khi tạo pipeline

- [ ] Đã xác định project, region và ranh giới môi trường.
- [ ] API Cloud Deploy, Cloud Build, Artifact Registry và target đã bật.
- [ ] Delivery pipeline và target ID được đặt tên rõ ràng.
- [ ] GKE cluster hoặc Cloud Run location đúng.
- [ ] Skaffold config và manifest đã được kiểm tra.
- [ ] Execution service account có quyền tối thiểu.

### Trước khi tạo release

- [ ] CI test và scan đã thành công.
- [ ] Image được lưu trong Artifact Registry.
- [ ] Release dùng image digest đã xác minh.
- [ ] Source commit và release name được ghi nhận.
- [ ] Rendered manifest không chứa secret hoặc cấu hình sai môi trường.
- [ ] Policy và kiểm soát chuỗi cung ứng đã đạt.

### Trước khi promote

- [ ] Rollout target trước đã thành công.
- [ ] Smoke test và integration test đã đạt.
- [ ] Metrics, logs và alert không có bất thường.
- [ ] Database migration tương thích với phiên bản đang chạy.
- [ ] Change request và approver đã sẵn sàng.
- [ ] Production target yêu cầu approval khi cần.

### Sau khi deploy

- [ ] Rollout và job status đã được xác minh.
- [ ] Workload/revision mới nhận traffic đúng.
- [ ] SLI nằm trong SLO.
- [ ] Release, image digest, commit và approval được lưu.
- [ ] Có release ổn định để rollback.
- [ ] Quyền IAM, pipeline và target được rà soát định kỳ.

Cloud Deploy giúp chuẩn hóa quá trình phát hành qua nhiều môi trường bằng delivery pipeline, target, release và rollout. Khi pipeline dùng artifact bất biến, target được phân quyền đúng, approval gắn với kết quả kiểm thử và rollout được giám sát đến khi SLO ổn định, nhóm có thể triển khai ứng dụng lên GKE hoặc Cloud Run một cách nhất quán, có thể truy vết và phục hồi khi cần.

