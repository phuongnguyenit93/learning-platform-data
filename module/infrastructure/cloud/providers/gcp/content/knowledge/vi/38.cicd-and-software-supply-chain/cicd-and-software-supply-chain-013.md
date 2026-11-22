# Binary Authorization và attestation trong chuỗi phát hành

Một container image đã được build thành công chưa chắc đã đủ điều kiện chạy trong production. Tổ chức có thể yêu cầu image phải được build từ pipeline tin cậy, vượt qua kiểm thử, được QA phê duyệt hoặc đáp ứng một quy trình bảo mật trước khi phát hành. Nếu chỉ dựa vào tên tag như latest hoặc một bước kiểm tra thủ công, nền tảng triển khai khó xác minh độc lập image đang được yêu cầu có thực sự đi qua các bước đó hay không.

**Binary Authorization** là cơ chế kiểm soát tại thời điểm triển khai trên Google Cloud. Dịch vụ đánh giá image theo policy và có thể chặn image không đáp ứng điều kiện. Một mô hình phổ biến là dùng **attestation**: một tuyên bố được ký số, gắn với digest của image, xác nhận một quy trình hoặc người có thẩm quyền đã chấp thuận image đó.

Trong module **CLOUD_PROVIDERS_GCP**, Binary Authorization kết nối quy trình CI/CD với các nền tảng chạy container như Google Kubernetes Engine (GKE) và Cloud Run. Nó giúp đội phát triển tự động hóa phát hành, đội bảo mật quản lý người ký và attestor, còn đội vận hành kiểm soát image được phép đi vào môi trường production.

Sau bài học, bạn có thể:

- Phân biệt image digest, signer, attestor, attestation, Artifact Analysis note và policy.
- Mô tả luồng build, ký attestation, xác minh và triển khai.
- Tạo attestor và liên kết khóa công khai với attestor.
- Tạo attestation cho một image digest bằng Cloud KMS.
- Cấu hình policy yêu cầu attestation và kiểm tra policy bằng dry-run.
- Tổ chức quyền IAM theo mô hình tách biệt trách nhiệm.
- Áp dụng Binary Authorization cho GKE, Cloud Run và tích hợp với Cloud Build.
- Điều tra deployment bị từ chối và xử lý breakglass theo quy trình.

## 1. Binary Authorization giải quyết vấn đề gì?

Một chuỗi phát hành container thường đi qua nhiều bước:

1. Nhà phát triển đẩy source code lên repository.
2. CI kiểm tra code, chạy unit test, scan dependency và build container image.
3. Image được đẩy lên Artifact Registry.
4. QA hoặc pipeline bảo mật kiểm tra image và kết quả build.
5. CD triển khai image vào dev, staging, canary rồi production.

Nếu một người có thể tự build image, đổi tag và triển khai thẳng lên production, các bước kiểm tra trước đó có thể bị bỏ qua. Binary Authorization tạo một cổng kiểm soát tại nền tảng triển khai: image chỉ được phép deploy khi policy của project cho phép.

Binary Authorization không tự quyết định một image có an toàn hay không. Tổ chức xác định điều kiện cần đáp ứng, ai có quyền xác nhận và quy trình nào được xem là đủ tin cậy. Binary Authorization kiểm tra các bằng chứng được policy yêu cầu trước khi cho phép image được triển khai.

Ví dụ, policy production có thể yêu cầu đồng thời:

- Image được build bởi Cloud Build hoặc một CI pipeline được tin cậy.
- Image đã vượt qua kiểm thử tích hợp.
- Image đã được QA hoặc security team phê duyệt.

Một image thiếu bất kỳ attestation bắt buộc nào sẽ không được triển khai khi policy ở chế độ enforce.

## 2. Các khái niệm cốt lõi

| Khái niệm | Vai trò | Cách hiểu |
|---|---|---|
| Container image | Đối tượng được kiểm soát | Image được lưu trong Artifact Registry hoặc registry tương thích |
| Digest | Định danh bất biến của nội dung image | Chuỗi dạng sha256:... xác định chính xác manifest image |
| Signer | Chủ thể tạo chữ ký và tuyên bố | Người, pipeline CI hoặc hệ thống QA có quyền ký |
| Attestation | Tuyên bố được ký số | Xác nhận một image digest đã hoàn thành một quy trình |
| Artifact Analysis note | Metadata mô tả attestor | Tài nguyên note được gắn với attestor |
| Attestor | Cơ quan xác minh | Lưu note và public key để Binary Authorization xác minh chữ ký |
| Artifact Analysis occurrence | Bản ghi attestation | Bản ghi được tạo khi attestation được gắn với note |
| Policy | Quy tắc triển khai | Xác định image nào được phép hoặc bị từ chối |
| Deployer | Nền tảng hoặc project yêu cầu triển khai | Ví dụ GKE cluster hoặc Cloud Run service |

Signer và attestor là hai vai trò khác nhau. Signer dùng private key để ký tuyên bố. Attestor giữ public key tương ứng để xác minh chữ ký khi triển khai. Private key không cần và không nên được phân phối cho nền tảng triển khai.

Artifact Analysis note là nơi định danh metadata của attestor. Khi tạo attestation, hệ thống tạo một occurrence gắn với note đó. Binary Authorization tra cứu attestation và dùng public key trong attestor để kiểm tra chữ ký.

### Attestation xác nhận điều gì?

Attestation là một tuyên bố có chủ đích. Ví dụ:

- Image digest X đã được build bởi pipeline release-prod.
- Image digest X đã vượt qua integration test suite 2026.11.
- Image digest X đã được QA phê duyệt để triển khai production.

Binary Authorization xác minh chữ ký và attestor theo policy. Nó không tự chạy lại test, scan source code hoặc kiểm tra nội dung tuyên bố. Chất lượng của attestation phụ thuộc vào độ tin cậy của signer và quy trình đã cấp quyền cho signer.

## 3. Vì sao phải dùng image digest?

Tag như latest, stable hoặc release-2026-11 có thể được gán lại cho image khác. Nếu ký một tag rồi triển khai tag đó sau khi tag đã đổi, hệ thống có thể chạy image khác với image đã được phê duyệt.

Digest là định danh nội dung của image manifest. Khi build và push image, hãy lấy digest thực tế từ Artifact Registry, sau đó tạo attestation cho image theo dạng:

~~~text
asia-southeast1-docker.pkg.dev/company-app-prod/runtime/checkout-api@sha256:IMAGE_DIGEST
~~~

Binary Authorization dùng digest để tìm attestation tại thời điểm deploy. Vì vậy, manifest triển khai nên dùng digest thay vì tag có thể thay đổi.

Một attestation có thể áp dụng cho cùng một image digest được lưu ở nhiều vị trí hoặc registry khác nhau. Đường dẫn image vẫn xuất hiện trong payload tạo chữ ký, nhưng digest là thông tin quyết định nội dung image được xác thực. Điều này hữu ích khi một image đã được kiểm chứng được mirror sang registry khác mà nội dung không thay đổi.

Không nên tạo attestation cho một image chỉ vì tên repository hoặc tag có vẻ đúng. Hãy lấy digest từ kết quả build/push, kiểm tra digest đó thuộc đúng artifact của pipeline, rồi ký digest đó.

## 4. Kiến trúc và luồng xác minh

Một kiến trúc cơ bản có thể triển khai trong một project. Khi cần tách nhiệm vụ bảo mật, hãy dùng các project riêng cho môi trường triển khai, attestor và attestation.

~~~mermaid
flowchart TD
    A["Source repository"] --> B["Cloud Build: build, test, scan"]
    B --> C["Artifact Registry: image + digest"]
    C --> D["Signer / release pipeline"]
    D --> E["Ký attestation bằng private key"]
    E --> F["Artifact Analysis: occurrence"]
    G["Attestor: note + public key"] --> H["Binary Authorization policy"]
    F --> H
    H --> I["GKE hoặc Cloud Run yêu cầu deploy"]
    I --> J{"Policy và chữ ký hợp lệ?"}
    J -->|Đạt| K["Cho phép triển khai"]
    J -->|Không đạt| L["Từ chối và ghi audit log"]
~~~

Quy trình theo thứ tự:

1. CI build image và đẩy image lên registry.
2. CI lấy digest của image vừa tạo.
3. Các bước kiểm tra được thực hiện trên artifact đó.
4. Signer tạo attestation cho digest bằng private key được quản lý an toàn.
5. Attestation được lưu dưới dạng occurrence gắn với Artifact Analysis note.
6. Khi deploy, Binary Authorization đọc policy của project và các attestation được yêu cầu.
7. Attestor xác minh chữ ký bằng public key đã đăng ký.
8. Nếu image đáp ứng policy, nền tảng cho phép triển khai; nếu không, request bị từ chối và lý do được ghi log.

Binary Authorization hỗ trợ GKE, Cloud Run, Cloud Service Mesh và Google Distributed Cloud. Cách bật enforcement và loại rule cụ thể có thể khác nhau theo nền tảng.

## 5. Tạo attestor và quản lý khóa ký

### 5.1. Bật các API cần thiết

Trong project thử nghiệm, bật Binary Authorization, Artifact Analysis và các API của nền tảng triển khai. Nếu dùng Artifact Registry và Cloud KMS, bật thêm API tương ứng.

~~~bash
gcloud services enable \
  binaryauthorization.googleapis.com \
  containeranalysis.googleapis.com \
  artifactregistry.googleapis.com \
  cloudkms.googleapis.com \
  --project=PROJECT_ID
~~~

Với GKE, bật thêm container.googleapis.com. Với Cloud Build, bật cloudbuild.googleapis.com. Người thực hiện cần quyền bật service, thường qua serviceusage.services.enable.

### 5.2. Tạo Artifact Analysis note

Note mô tả metadata của attestor. Ví dụ tạo note có tên release-approval-note trong project attestor:

~~~json
{
  "name": "projects/ATTESTOR_PROJECT_ID/notes/release-approval-note",
  "attestation": {
    "hint": {
      "human_readable_name": "Release approval attestor"
    }
  }
}
~~~

Lưu nội dung trên vào file note_payload.json, sau đó gọi Artifact Analysis API:

~~~bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  --data-binary @note_payload.json \
  "https://containeranalysis.googleapis.com/v1/projects/ATTESTOR_PROJECT_ID/notes/?noteId=release-approval-note"
~~~

Binary Authorization dùng Artifact Analysis global endpoint. Không cấu hình note trong regional storage hoặc gọi regional endpoint cho luồng attestation này.

### 5.3. Tạo attestor

Tạo attestor trong project chứa note:

~~~bash
gcloud --project=ATTESTOR_PROJECT_ID \
  container binauthz attestors create release-approval \
  --attestation-authority-note=release-approval-note \
  --attestation-authority-note-project=ATTESTOR_PROJECT_ID
~~~

Attestor hiện đã tham chiếu note nhưng chưa thể xác minh chữ ký cho đến khi có public key.

### 5.4. Dùng Cloud KMS để giữ private key

Trong production, nên dùng Cloud KMS để giữ private key và thực hiện thao tác ký. Private key không cần được tải xuống máy build. Tạo key ring và asymmetric signing key:

~~~bash
gcloud kms keyrings create binauthz-keyring \
  --location=global \
  --project=KMS_PROJECT_ID

gcloud kms keys create release-signing-key \
  --location=global \
  --keyring=binauthz-keyring \
  --purpose=asymmetric-signing \
  --default-algorithm=ec-sign-p256-sha256 \
  --protection-level=software \
  --project=KMS_PROJECT_ID
~~~

Ví dụ dùng thuật toán ECDSA P-256 với SHA-256. Tổ chức có thể chọn protection level và cơ chế quản lý khóa phù hợp với chính sách bảo mật.

Thêm public key tương ứng vào attestor:

~~~bash
gcloud --project=ATTESTOR_PROJECT_ID \
  container binauthz attestors public-keys add \
  --attestor=release-approval \
  --keyversion-project=KMS_PROJECT_ID \
  --keyversion-location=global \
  --keyversion-keyring=binauthz-keyring \
  --keyversion-key=release-signing-key \
  --keyversion=1
~~~

Lệnh trả về public key ID. Có thể lấy lại ID bằng:

~~~bash
gcloud --project=ATTESTOR_PROJECT_ID \
  container binauthz attestors describe release-approval \
  --format="value(userOwnedGrafeasNote.publicKeys[0].id)"
~~~

Public key ID là định danh của khóa trong attestor. Khi tạo attestation bằng lệnh sign-and-create, Binary Authorization dùng thông tin key version của Cloud KMS và attestor để ký, lưu và kiểm tra chữ ký.

Giới hạn quyền cloudkms.cryptoKeyVersions.useToSign cho danh tính pipeline cần ký. Không cấp quyền ký khóa cho mọi developer hoặc mọi job build. Đội bảo mật nên quản lý public key của attestor, còn signer chỉ nhận quyền sử dụng key version theo nhiệm vụ.

## 6. Tạo attestation cho image digest

Giả sử Cloud Build đã tạo image checkout API và push lên Artifact Registry. Kết quả build cung cấp digest:

~~~bash
IMAGE_PATH=asia-southeast1-docker.pkg.dev/company-app-prod/runtime/checkout-api
IMAGE_DIGEST=sha256:REPLACE_WITH_REAL_DIGEST
IMAGE_TO_ATTEST=$IMAGE_PATH@$IMAGE_DIGEST
~~~

Không dùng chuỗi digest minh họa trong lệnh production. Hãy lấy digest thực tế từ kết quả push hoặc Artifact Registry.

Dùng Cloud KMS key version để ký và tạo attestation:

~~~bash
gcloud container binauthz attestations sign-and-create \
  --project=ATTESTATION_PROJECT_ID \
  --artifact-url="$IMAGE_TO_ATTEST" \
  --attestor=release-approval \
  --attestor-project=ATTESTOR_PROJECT_ID \
  --keyversion-project=KMS_PROJECT_ID \
  --keyversion-location=global \
  --keyversion-keyring=binauthz-keyring \
  --keyversion-key=release-signing-key \
  --keyversion=1 \
  --validate
~~~

Cờ --validate yêu cầu kiểm tra attestation vừa tạo có thể được xác minh bởi attestor đã cấu hình. Nếu dùng nhiều project, danh tính tạo attestation cần:

- roles/containeranalysis.notes.attacher trên Artifact Analysis note của attestor.
- roles/containeranalysis.occurrences.editor trên project lưu attestation.
- Quyền ký phù hợp trên Cloud KMS key version.

Có thể kiểm tra danh sách attestation:

~~~bash
gcloud --project=ATTESTATION_PROJECT_ID \
  container binauthz attestations list \
  --attestor=release-approval \
  --attestor-project=ATTESTOR_PROJECT_ID
~~~

Attestation được gắn với digest. Nếu image được build lại, dù source code không đổi, digest có thể khác và cần một attestation mới. Không tái sử dụng attestation cũ cho artifact có digest khác.

## 7. Cấu hình policy yêu cầu attestation

Mỗi Google Cloud project có đúng một Binary Authorization policy. Policy phải được cấu hình ở project nơi nền tảng triển khai chạy. Trong mô hình một project, policy, attestor và attestation có thể cùng nằm trong project đó. Trong mô hình nhiều project, policy vẫn ở deployer project và tham chiếu attestor ở project bảo mật.

Policy có hai thành phần quan trọng:

- evaluationMode: điều kiện image cần đáp ứng, ví dụ cho phép tất cả, từ chối tất cả hoặc yêu cầu attestation.
- enforcementMode: hành động khi image không đáp ứng điều kiện, ví dụ chặn deployment hoặc chỉ ghi audit log.

Ví dụ policy yêu cầu attestation từ attestor release-approval:

~~~yaml
globalPolicyEvaluationMode: ENABLE
defaultAdmissionRule:
  evaluationMode: REQUIRE_ATTESTATION
  enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
  requireAttestationsBy:
    - projects/ATTESTOR_PROJECT_ID/attestors/release-approval
name: projects/DEPLOYER_PROJECT_ID/policy
~~~

globalPolicyEvaluationMode: ENABLE cho phép các image hệ thống do Google quản lý được xử lý theo cơ chế global policy evaluation. Điều này giúp tránh chặn các image hệ thống cần thiết cho nền tảng.

Xuất policy hiện tại, chỉnh sửa file YAML rồi import lại:

~~~bash
gcloud --project=DEPLOYER_PROJECT_ID \
  container binauthz policy export > policy.yaml

# Chỉnh policy.yaml, kiểm tra các rule và image exemptions.

gcloud --project=DEPLOYER_PROJECT_ID \
  container binauthz policy import policy.yaml
~~~

Policy có thể mất vài phút để có hiệu lực. Không ghi đè policy production bằng file tối giản nếu chưa kiểm tra các rule cụ thể, image exemptions và cấu hình đang có. Hãy export, review thay đổi, lưu bản policy trước đó và import theo quy trình change management.

Nếu policy yêu cầu nhiều attestor, image phải có attestation hợp lệ từ tất cả attestor được liệt kê. Có thể dùng nhiều signer để đại diện cho các cổng kiểm tra khác nhau, ví dụ built-by-ci, security-scanned và qa-approved.

Policy có một default rule và có thể có specific rules tùy nền tảng. GKE hỗ trợ rule theo cluster, Kubernetes namespace và Kubernetes service account. Cloud Run chỉ hỗ trợ default rule, không có specific rule theo service. Hãy kiểm tra đúng loại rule được nền tảng hỗ trợ trước khi thiết kế policy.

## 8. Dry-run trước khi enforce

Không nên bật policy chặn production ngay khi chưa quan sát tác động. Dry-run giúp đánh giá policy mà vẫn cho phép deployment không đáp ứng điều kiện tiếp tục chạy. Các vi phạm được ghi vào Cloud Logging hoặc Cloud Audit Logs để đội vận hành phát hiện false positive và image chưa được cấp attestation.

Trong policy YAML, đổi enforcementMode thành:

~~~yaml
enforcementMode: DRYRUN_AUDIT_LOG_ONLY
~~~

Khi đã xác minh policy hoạt động đúng, chuyển sang:

~~~yaml
enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
~~~

Quy trình rollout nên thực hiện theo các bước:

1. Export policy hiện tại và lưu bản kiểm soát.
2. Thêm attestor và rule yêu cầu attestation ở chế độ dry-run.
3. Triển khai các workload đại diện ở dev/staging và quan sát log.
4. Kiểm tra các image hệ thống, sidecar, init container và image do dịch vụ quản lý.
5. Xác nhận pipeline tạo attestation cho đúng digest.
6. Chuyển policy sang enforce sau khi đã xử lý các image hợp lệ còn thiếu attestation.

Dry-run không kiểm chứng rằng toàn bộ quy trình bảo mật đã tốt. Nó chỉ cho biết request triển khai có đáp ứng policy hay không. Hãy kiểm tra signer, quyền IAM, nguồn digest và nội dung tuyên bố trước khi tin cậy attestation.

## 9. Tích hợp với Cloud Build

Cloud Build có thể tạo attestation cho image do Cloud Build build và push. Trong cùng project, attestor mặc định có tên built-by-cloud-build. Có thể cấu hình policy yêu cầu attestation này để chỉ cho phép image được build bởi Cloud Build đủ điều kiện.

Một cấu hình build minh họa:

~~~yaml
steps:
  - name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - asia-southeast1-docker.pkg.dev/$PROJECT_ID/runtime/checkout-api:$SHORT_SHA
      - .

images:
  - asia-southeast1-docker.pkg.dev/$PROJECT_ID/runtime/checkout-api:$SHORT_SHA
~~~

Cloud Build cần nhận diện image output thông qua trường images. Nếu build dùng một step docker push tường minh thay cho trường images, Cloud Build không tạo Binary Authorization attestation theo luồng này.

Với build chạy trong private pool, mặc định Cloud Build không tạo Binary Authorization attestation. Bổ sung requestedVerifyOption: VERIFIED:

~~~yaml
options:
  requestedVerifyOption: VERIFIED
~~~

Tùy chọn này bật và xác minh việc tạo attestation cùng provenance metadata. Build chỉ được đánh dấu thành công nếu attestation và provenance được tạo theo yêu cầu.

Sau build, pipeline cần lấy digest của image đã push, lưu lại digest trong output hoặc metadata release và dùng digest đó ở bước deploy. Không tự dựng digest từ tag hoặc suy luận từ tên image.

### Tách build pipeline và deploy pipeline

Cloud Build tạo attestation sau khi build pipeline hoàn tất thành công. Vì vậy, hãy tách pipeline build khỏi pipeline deploy:

- Build pipeline: checkout source, build, test, scan, push image và tạo provenance/attestation.
- Release pipeline: lấy image digest đã được xác nhận, kiểm tra các attestation cần thiết, tạo deployment manifest và yêu cầu nền tảng triển khai.

Policy tham chiếu attestor built-by-cloud-build có thể được export/import bằng CLI. Ví dụ rule:

~~~yaml
defaultAdmissionRule:
  evaluationMode: REQUIRE_ATTESTATION
  enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
  requireAttestationsBy:
    - projects/BUILD_PROJECT_ID/attestors/built-by-cloud-build
name: projects/DEPLOYER_PROJECT_ID/policy
~~~

Đối với cấu hình nhiều project, Binary Authorization service agent của deployer project cần được cấp quyền xác minh attestor từ build project. Không giả định rằng policy ở deployer project tự động có quyền đọc attestor hoặc Artifact Analysis note ở project khác.

## 10. Tách biệt trách nhiệm bằng nhiều project

Trong tổ chức lớn, nên phân chia quyền quản trị theo ba project:

| Project | Trách nhiệm | Ai quản lý |
|---|---|---|
| Deployer project | GKE/Cloud Run và Binary Authorization policy | Platform / DevOps |
| Attestor project | Attestor, note và public key | Security Operations |
| Attestation project | Artifact Analysis occurrences chứa attestation | CI/CD signer hoặc release approver |

Cách tách này giúp developer không thể tự tạo attestor, thay public key hoặc tự phê duyệt image production. Đội bảo mật quản lý danh tính tin cậy, còn pipeline release chỉ có quyền tạo attestation theo quy trình được giao.

Các vai trò IAM phổ biến:

| Hoạt động | Project | Vai trò |
|---|---|---|
| Tạo attestor và quản lý note | Attestor | roles/containeranalysis.notesEditor, roles/binaryauthorization.attestorsAdmin |
| Cấu hình policy | Deployer | roles/binaryauthorization.policyEditor |
| Đọc attestor để policy xác minh | Attestor | roles/binaryauthorization.attestorsViewer |
| Bật Binary Authorization và quản lý cluster | Deployer | roles/serviceusage.serviceUsageAdmin, roles/container.clusterAdmin |
| Tạo attestation | Attestor note | roles/containeranalysis.notes.attacher |
| Ghi occurrence | Attestation | roles/containeranalysis.occurrences.editor |

Ngoài vai trò người dùng, cần cấp quyền cho service agent của Binary Authorization ở deployer project để xác minh attestor trong attestor project. Tài khoản dịch vụ có dạng:

~~~text
service-DEPLOYER_PROJECT_NUMBER@gcp-sa-binaryauthorization.iam.gserviceaccount.com
~~~

Trên tài nguyên attestor, cấp quyền roles/binaryauthorization.attestorsVerifier cho service agent này. Note của Artifact Analysis cần quyền đọc roles/containeranalysis.notes.occurrences.viewer cho các service agent liên quan. Hãy làm theo hướng dẫn multi-project setup của Google Cloud để cấu hình đầy đủ IAM bindings cho note, attestor và occurrence.

Không cấp roles/binaryauthorization.admin hoặc Owner cho pipeline chỉ để tạo attestation. Cấp đúng quyền trên note, occurrence và key version. Đặc biệt, quyền ký Cloud KMS nên chỉ dành cho signer được phê duyệt.

## 11. Bật enforcement trên nền tảng triển khai

### 11.1. Google Kubernetes Engine

Khi tạo GKE cluster, bật Binary Authorization evaluation:

~~~bash
gcloud container clusters create app-prod-cluster \
  --project=DEPLOYER_PROJECT_ID \
  --region=asia-southeast1 \
  --binauthz-evaluation-mode=PROJECT_SINGLETON_POLICY_ENFORCE
~~~

Cluster sử dụng policy của project deployer. Khi một Pod được tạo hoặc cập nhật, Binary Authorization kiểm tra image theo policy tương ứng. Nếu policy yêu cầu attestation mà không tìm thấy attestation hợp lệ, admission request bị từ chối.

Khi deploy, dùng digest:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: checkout-api
  template:
    metadata:
      labels:
        app: checkout-api
    spec:
      containers:
        - name: checkout-api
          image: asia-southeast1-docker.pkg.dev/company-app-prod/runtime/checkout-api@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - containerPort: 8080
~~~

Khi bị từ chối, xem Kubernetes events và Binary Authorization audit logs để biết image bị rule nào chặn và attestor nào thiếu attestation.

### 11.2. Cloud Run

Cloud Run hỗ trợ policy cho service và job. Có thể bật policy mặc định bằng CLI:

~~~bash
gcloud run services update checkout-api \
  --project=DEPLOYER_PROJECT_ID \
  --region=asia-southeast1 \
  --binary-authorization=default
~~~

Với Cloud Run job:

~~~bash
gcloud run jobs update nightly-reconcile \
  --project=DEPLOYER_PROJECT_ID \
  --region=asia-southeast1 \
  --binary-authorization=default
~~~

Đối với service, Cloud Run kiểm tra policy mỗi khi tạo revision mới. Nếu image không đạt policy, deployment thất bại và revision mới không được triển khai. Các revision đang tồn tại không bị kiểm tra lại chỉ vì policy thay đổi.

Đối với job, việc cập nhật cấu hình job có thể thành công ngay cả khi image không đạt policy; lần thực thi job sẽ thất bại khi policy không cho phép image. Policy thay đổi cũng không áp dụng hồi tố cho các execution đang chạy.

Nên dùng Organization Policy để yêu cầu Binary Authorization cho Cloud Run. Nếu chỉ bật trên từng service mà không có chính sách cấp tổ chức, người có quyền triển khai có thể tắt Binary Authorization trong cấu hình service.

Cloud Run có cơ chế breakglass để bypass policy trong tình huống khẩn cấp. Breakglass tạo log entry để kiểm toán. Chỉ sử dụng khi có incident, ghi nhận người phê duyệt, lý do, image digest, thời hạn và kế hoạch khắc phục. Sau khi xử lý, loại bỏ bypass và triển khai image đã đáp ứng policy.

Đối với Cloud Run functions, một số repository nguồn do nền tảng quản lý cần được cấu hình exempt theo hướng dẫn của Google Cloud, ví dụ cloud-run-source-deploy hoặc gcf-artifacts tùy API triển khai. Không tạo allowlist rộng cho toàn bộ registry nếu chỉ cần miễn trừ repository phục vụ quá trình build/deploy của functions.

### 11.3. Continuous Validation

Binary Authorization còn có Continuous Validation (CV) để định kỳ kiểm tra image gắn với Pod đang chạy có tiếp tục đáp ứng policy hay không. CV là cơ chế giám sát liên tục, khác với deploy-time enforcement. CV ghi log khi phát hiện workload không còn phù hợp; nó không thay thế cổng kiểm tra khi admission.

Tài liệu hiện hành đánh dấu check-based platform policies cho CV là Preview. Hãy kiểm tra giai đoạn phát hành và giới hạn của tính năng trước khi đưa vào yêu cầu kiểm soát production.

## 12. Điều tra và xử lý lỗi

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Deployment bị từ chối với No attestations found | Chưa tạo attestation hoặc attestation lưu ở project khác | Kiểm tra digest, attestor, project lưu occurrence và danh sách attestation |
| Attestation tồn tại nhưng chữ ký không hợp lệ | Public key ID không khớp, sai key version hoặc payload khác digest | Kiểm tra public key của attestor và chạy tạo attestation với validate |
| Image có attestation nhưng vẫn bị chặn | Policy yêu cầu nhiều attestor hoặc đang dùng digest khác | Đối chiếu requireAttestationsBy và image digest trong manifest |
| Cloud Build build thành công nhưng thiếu attestation | Dùng private pool mà thiếu requestedVerifyOption: VERIFIED, hoặc push bằng step riêng | Kiểm tra build config, trường images và build result |
| Policy dry-run vẫn cho image deploy | Enforcement mode đang là audit-only | Kiểm tra enforcementMode trong policy YAML |
| Deployer không xác minh được attestor | Thiếu IAM trên attestor hoặc Artifact Analysis note | Kiểm tra service agent của deployer project và IAM bindings |
| Cloud Run update job thành công nhưng execution thất bại | Job chỉ kiểm tra policy khi thực thi | Kiểm tra execution log và image digest |
| Image tag được phê duyệt nhưng deployment bị chặn | Tag đã trỏ sang digest khác hoặc manifest dùng tag | Triển khai bằng image digest và tạo attestation cho digest đó |

Khi điều tra, thực hiện theo thứ tự:

1. Lấy image digest thực tế mà nền tảng đang yêu cầu triển khai.
2. Kiểm tra digest đó có nằm trong Artifact Registry và có đúng kết quả build mong đợi không.
3. Kiểm tra attestation được tạo ở project nào và gắn với attestor nào.
4. Xác minh public key ID và key version có khớp với attestor.
5. Đọc policy của đúng deployer project; xác định rule nào áp dụng.
6. Kiểm tra enforcement mode và các image exemptions.
7. Kiểm tra IAM của deployer service agent, signer và người quản lý policy.
8. Đọc Binary Authorization logs, Cloud Audit Logs, GKE events hoặc Cloud Run deployment events.

Có thể xem policy hiện tại bằng:

~~~bash
gcloud --project=DEPLOYER_PROJECT_ID \
  container binauthz policy export
~~~

Và liệt kê attestor:

~~~bash
gcloud --project=ATTESTOR_PROJECT_ID \
  container binauthz attestors list
~~~

Không xử lý lỗi bằng cách chuyển policy production sang allow-all hoặc thêm wildcard exemption. Hãy tìm nguyên nhân thiếu attestation, sai digest hoặc IAM trước.

## 13. Tình huống thực tế: đưa checkout API lên production

Một tổ chức triển khai checkout-api qua dev, staging và production. Security team yêu cầu mọi image production phải được build bởi CI và được QA phê duyệt.

Luồng release:

1. Developer merge code vào nhánh release.
2. Cloud Build build image, chạy unit test, integration test và scan.
3. Image được push vào Artifact Registry; pipeline lưu digest thực tế.
4. Cloud Build tạo build attestation hoặc signer tạo attestation ci-build-approved.
5. QA kiểm thử image theo digest ở staging.
6. QA signer tạo attestation qa-approved cho cùng digest.
7. Release pipeline tạo manifest production dùng digest đó.
8. Binary Authorization policy yêu cầu cả ci-build-approved và qa-approved.
9. GKE hoặc Cloud Run kiểm tra attestation trước khi chấp nhận deployment.
10. Khi deployment thành công, pipeline ghi lại digest, source commit, build ID, attestor và thời điểm phát hành.

Policy có thể liệt kê hai attestor bắt buộc:

~~~yaml
defaultAdmissionRule:
  evaluationMode: REQUIRE_ATTESTATION
  enforcementMode: ENFORCED_BLOCK_AND_AUDIT_LOG
  requireAttestationsBy:
    - projects/SECURITY_PROJECT_ID/attestors/ci-build-approved
    - projects/SECURITY_PROJECT_ID/attestors/qa-approved
name: projects/PROD_PROJECT_ID/policy
~~~

Nếu QA chưa ký attestation, image sẽ bị từ chối dù build thành công. Điều này biến bước QA từ một quy trình thủ công thành một cổng có thể xác minh tự động tại thời điểm triển khai.

Nếu có sự cố cần rollback, pipeline cần triển khai lại digest của image cũ đã có đủ attestation. Không chỉ đổi tag stable về tag trước đó vì tag có thể thay đổi và không thể hiện rõ artifact đã được phê duyệt.

## 14. Nguyên tắc vận hành tốt

- Dùng digest thay vì tag cho attestation và deployment production.
- Tách quyền build, sign, quản lý attestor và deploy để một cá nhân hoặc một service account không tự phê duyệt mọi bước.
- Dùng Cloud KMS để giữ private key; giới hạn quyền ký và theo dõi việc sử dụng key version.
- Chỉ tạo attestation sau khi pipeline đã xác minh đúng image digest và hoàn tất các bước kiểm tra.
- Mỗi attestor đại diện cho một quy trình hoặc nhóm có trách nhiệm rõ ràng.
- Dùng policy dry-run trước khi bật block-and-audit-log.
- Lưu bằng chứng build, test, scan, source commit và người/phần mềm ký để hỗ trợ điều tra.
- Bảo vệ Artifact Analysis note, occurrence, attestor và policy bằng IAM tối thiểu.
- Quản lý image exemptions hẹp và có lý do; tránh wildcard quá rộng.
- Theo dõi Binary Authorization audit logs và các lần sử dụng breakglass.
- Kiểm tra lại policy, signer và attestation khi thay đổi CI/CD, key version, registry hoặc nền tảng deploy.
- Kết hợp Binary Authorization với vulnerability scanning, SBOM và build provenance. Attestation chỉ xác nhận tuyên bố của signer; nó không tự chứng minh image không có lỗ hổng.

## 15. Checklist trước khi enforce production

- [ ] Image được push lên registry và digest được lấy từ kết quả build thực tế.
- [ ] Attestor có Artifact Analysis note và public key hợp lệ.
- [ ] Private key được giữ trong Cloud KMS hoặc cơ chế bảo vệ tương đương.
- [ ] Chỉ signer được phê duyệt có quyền tạo attestation.
- [ ] Attestation được tạo cho đúng digest và có thể validate.
- [ ] Policy nằm trong deployer project và tham chiếu đúng attestor.
- [ ] IAM service agent của deployer có quyền xác minh attestor/note.
- [ ] Attestation project và quyền occurrence được cấu hình đúng.
- [ ] GKE cluster hoặc Cloud Run service/job đã bật Binary Authorization.
- [ ] Policy đã chạy dry-run và các false positive đã được xử lý.
- [ ] Production manifest dùng digest thay vì tag.
- [ ] Image exemptions đã được review.
- [ ] Có quy trình breakglass, audit và rollback bằng digest đã được phê duyệt.
- [ ] Có dashboard/log alert để phát hiện deployment bị từ chối và thay đổi policy.

## 16. Tự kiểm tra

1. Vì sao attestation cần gắn với image digest thay vì chỉ gắn với tag?
2. Signer và attestor có vai trò gì khác nhau?
3. Artifact Analysis note và occurrence tham gia vào quy trình attestation như thế nào?
4. REQUIRE_ATTESTATION và ENFORCED_BLOCK_AND_AUDIT_LOG giải quyết hai phần nào của policy?
5. Vì sao nên dùng dry-run trước khi enforce?
6. Trong mô hình ba project, deployer, attestor và attestation project giữ trách nhiệm gì?
7. Vì sao Cloud Build private pool cần requestedVerifyOption: VERIFIED?
8. Cloud Run job kiểm tra Binary Authorization ở thời điểm nào?
9. Attestation có chứng minh image không chứa lỗ hổng bảo mật không?

**Gợi ý đáp án**

1. Tag có thể được gán lại cho image khác; digest xác định nội dung image cụ thể và không đổi khi tag thay đổi.
2. Signer dùng private key để ký tuyên bố; attestor lưu public key và xác minh chữ ký khi deploy.
3. Note mô tả metadata của attestor; occurrence lưu attestation đã được ký và gắn với note.
4. REQUIRE_ATTESTATION định nghĩa điều kiện image phải có chữ ký hợp lệ từ attestor; ENFORCED_BLOCK_AND_AUDIT_LOG quyết định chặn image không đạt và ghi audit log.
5. Dry-run cho phép quan sát vi phạm và false positive mà chưa chặn workload, giảm rủi ro rollout policy.
6. Deployer project giữ policy và nền tảng chạy; attestor project giữ note/attestor/public key; attestation project lưu các occurrence.
7. Cloud Build không mặc định tạo Binary Authorization attestation cho build trong private pool; requestedVerifyOption: VERIFIED bật và xác minh việc tạo attestation/provenance.
8. Cloud Run job kiểm tra policy khi job được thực thi; việc update job có thể thành công dù image không đạt policy.
9. Không. Attestation chỉ là tuyên bố được ký bởi signer. Muốn đánh giá lỗ hổng cần scan và policy kiểm soát riêng.

## Tài liệu tham khảo

- [Google Cloud: Binary Authorization overview](https://docs.cloud.google.com/binary-authorization/docs/overview)
- [Google Cloud: Binary Authorization concepts and policy model](https://docs.cloud.google.com/binary-authorization/docs/key-concepts)
- [Google Cloud: Get started using the Google Cloud CLI for GKE](https://docs.cloud.google.com/binary-authorization/docs/getting-started-cli)
- [Google Cloud: Create attestations](https://docs.cloud.google.com/binary-authorization/docs/making-attestations)
- [Google Cloud: Create attestors using the gcloud CLI](https://docs.cloud.google.com/binary-authorization/docs/creating-attestors-cli)
- [Google Cloud: Configure a multi-project setup](https://docs.cloud.google.com/binary-authorization/docs/multi-project-setup-cli)
- [Google Cloud: Separation of duties and IAM roles](https://docs.cloud.google.com/binary-authorization/docs/reference/organizational-and-iam-roles)
- [Google Cloud: Secure image deployments with Cloud Build](https://docs.cloud.google.com/build/docs/securing-builds/secure-deployments-to-run-gke)
- [Google Cloud: Binary Authorization for Cloud Run](https://docs.cloud.google.com/binary-authorization/docs/run/overview)
- [Google Cloud: Use Binary Authorization on Cloud Run](https://docs.cloud.google.com/run/docs/securing/binary-authorization)

