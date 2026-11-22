# Xác thực Terraform bằng danh tính ngắn hạn

> **Chương:** Hạ tầng bằng mã với Terraform · **Phạm vi:** Google Cloud (GCP)

## 1. Vì sao Terraform cần danh tính ngắn hạn?

Terraform đọc trạng thái hạ tầng (state), so sánh với cấu hình và gọi API Google Cloud để tạo, sửa hoặc xóa tài nguyên. Nếu pipeline giữ một tệp khóa JSON của service account trong nhiều tháng, bất kỳ ai lấy được khóa đều có thể sử dụng danh tính ấy cho đến khi khóa bị thu hồi. Khóa còn dễ lọt vào lịch sử Git, nhật ký CI, artifact hoặc máy của người phát triển.

**Danh tính ngắn hạn** nghĩa là Terraform lấy thông tin xác thực tạm thời từ một danh tính gốc đã được tin cậy, thường qua **service account impersonation** hoặc **Workload Identity Federation (WIF)**. Access token của service account thường có thời hạn mặc định tối đa **1 giờ**; khi hết hạn, công cụ dùng chuỗi xác thực hợp lệ để xin token mới, thay vì mang theo khóa riêng của service account. Thời hạn token ngắn **không** tự thay thế việc cấp quyền tối thiểu, giới hạn nguồn danh tính và kiểm soát nơi lưu state.

Trong hành trình triển khai hạ tầng Google Cloud, từ IAM/VPC đến Compute Engine, GKE, Cloud Run và dịch vụ dữ liệu, cùng một nguyên tắc được dùng để Terraform có quyền vừa đủ trong từng môi trường và có thể truy vết thao tác.

### Sau bài này, bạn có thể

- Giải thích sự khác nhau giữa **Application Default Credentials (ADC)**, **service account impersonation**, **WIF** và khóa JSON dài hạn.
- Dùng tài khoản người phát triển để xin token ngắn hạn của service account mà Terraform sử dụng trên máy cục bộ.
- Thiết lập luồng **GitHub Actions OIDC → Google Cloud WIF → service account** mà không tạo khóa service account.
- Cấu hình **Google provider** và **GCS backend**, nhận biết hai nơi cần quyền truy cập riêng.
- Phân tích lỗi 401/403 và kiểm tra giới hạn quyền mà không in access token vào log.

## 2. Luồng danh tính: ai chứng minh, ai được cấp quyền?

```text
Máy phát triển                       GitHub Actions / CI                 Runner trên GCP
Tài khoản người dùng                 OIDC token của job                  Service account gắn vào runtime
         |                                   |                                  |
         | ADC + impersonation               | WIF: STS + IAM Credentials API  | Metadata server
         v                                   v                                  v
                 Nguồn ADC hoặc thông tin xác thực ngắn hạn
                                      |
                             Terraform CLI
                         /                        \
                  GCS backend                Google provider
                đọc/ghi/khóa state          quản lý tài nguyên GCP
```

Có ba khái niệm không nên đánh đồng:

| Thành phần | Nhiệm vụ | Điểm cần nhớ |
| --- | --- | --- |
| **Danh tính gốc** | Chứng minh người/job/runtime là ai, ví dụ Google user hoặc GitHub OIDC. | Chỉ danh tính gốc được cho phép mới có thể yêu cầu mạo danh. |
| **Service account đích** | Danh tính mà Terraform dùng để thao tác API; được gán các IAM role trên tài nguyên cần quản lý. | Quyền của service account quyết định phạm vi thay đổi được phép. |
| **Access token** | Bằng chứng OAuth tạm thời khi gọi API. | Token có thời hạn; không đưa vào mã HCL, log hay file state. |

**ADC** là cơ chế thư viện Google tìm nguồn xác thực; ADC không đồng nghĩa với một loại token. Thứ tự tìm kiếm điển hình: (1) đường dẫn trong `GOOGLE_APPLICATION_CREDENTIALS`; (2) tệp ADC cục bộ tại vị trí chuẩn; (3) danh tính được gắn vào môi trường Google Cloud qua metadata server. Vì vậy, một biến môi trường cũ trỏ đến khóa JSON có thể làm Terraform dùng nhầm danh tính dù bạn vừa đăng nhập bằng `gcloud`.

**Impersonation** dùng danh tính đã đăng nhập để gọi IAM Service Account Credentials API xin access token của service account. Tài khoản người dùng thường cần `roles/iam.serviceAccountTokenCreator` **trên service account đích**, không cần role này trên toàn dự án.

**WIF** tiếp nhận token OIDC từ nhà cung cấp danh tính bên ngoài, kiểm tra issuer, audience và thuộc tính, rồi trao đổi qua Security Token Service (STS). WIF có thể được cấp quyền trực tiếp vào tài nguyên; với Terraform, ví dụ dưới đây chọn **WIF qua service account** để dùng IAM role hiện có và tăng khả năng tương thích dịch vụ. Principal bên ngoài cần `roles/iam.workloadIdentityUser` trên service account muốn sử dụng. Hai role `workloadIdentityUser` và `serviceAccountTokenCreator` phục vụ hai hình thức ủy quyền khác nhau; không cấp cả hai một cách mặc định.

| Nơi chạy | Cách khuyến nghị | Có khóa JSON service account? |
| --- | --- | --- |
| Máy phát triển | ADC cục bộ kết hợp impersonation | Không |
| GitHub Actions, GitLab hoặc CI ngoài GCP | WIF nhận OIDC của job; tùy nhu cầu mạo danh service account | Không |
| Compute Engine/runner trên Google Cloud | Gắn user-managed service account vào runtime và dùng ADC | Không |
| Khóa JSON tải xuống | Chỉ cân nhắc khi các lựa chọn trên bất khả thi và phải kiểm soát vòng đời khóa | Có, rủi ro cao hơn |

> **Lưu ý:** ADC của người dùng trên máy phát triển vẫn có thể lưu thông tin đăng nhập/refresh token ở máy. “Không có khóa service account” không có nghĩa “máy hoàn toàn không có thông tin xác thực lâu dài”. Bảo vệ máy, tài khoản và tệp ADC vẫn rất quan trọng.

## 3. Thực hành tại máy phát triển: ADC với service account impersonation

Giả sử nhóm có một dự án minh họa `my-project`, một bucket state `my-terraform-state` đã được tạo sẵn và service account `tf-deploy@my-project.iam.gserviceaccount.com`. **Mọi ID, email, bucket và số dự án trong bài đều là ví dụ phải thay bằng giá trị thực.**

Điều kiện trước khi thực hành:

1. Có Terraform và Google Cloud CLI; người thực hành đã đăng nhập bằng danh tính cá nhân hoặc danh tính doanh nghiệp.
2. Quản trị viên đã bật **IAM Service Account Credentials API** khi dùng impersonation và cấp `roles/iam.serviceAccountTokenCreator` cho người thực hành trên service account `tf-deploy`.
3. Service account `tf-deploy` có quyền **đọc/ghi các object trong bucket state** và quyền cần thiết cho tài nguyên Google Cloud mà Terraform quản lý. Ví dụ bucket state thường dùng `roles/storage.objectAdmin` ở phạm vi **bucket**, còn dự án chỉ cấp những role tương ứng với loại tài nguyên, không cấp `Owner`/`Editor` theo thói quen.
4. Bucket backend GCS tồn tại trước khi chạy `terraform init`. Nên bật **Object Versioning** để có đường phục hồi state khi xóa hoặc ghi nhầm.

### Bước 1: tạo ADC có khả năng mạo danh

```bash
gcloud auth login
gcloud auth application-default login --impersonate-service-account=tf-deploy@my-project.iam.gserviceaccount.com
```

Lệnh đầu xác thực người dùng cho **gcloud CLI**; lệnh thứ hai tạo **tệp ADC** để thư viện/Terraform sử dụng và tự xin access token của service account đích. `gcloud auth login` đơn lẻ không đồng nghĩa đã có ADC cho Terraform.

Không đưa `--impersonate-service-account` cùng một private key vào repository. Nếu `GOOGLE_APPLICATION_CREDENTIALS` đang trỏ đến tệp khác, hãy kiểm tra và loại bỏ cấu hình gây xung đột trước khi dùng ADC cục bộ.

### Bước 2: khai báo provider và backend

Ví dụ `main.tf` tối thiểu, dành cho bài học quản lý một VPC thử nghiệm:

```hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source = "hashicorp/google"
    }
  }

  backend "gcs" {
    bucket = "my-terraform-state"
    prefix = "dev/network"
  }
}

provider "google" {
  project = "my-project"
  region  = "asia-southeast1"
}

resource "google_compute_network" "lab" {
  name                    = "tf-short-lived-lab"
  auto_create_subnetworks = false
}
```

Trong ví dụ này, **cả backend và provider đều lấy credentials theo ADC**. Khi ADC đã được cấu hình để mạo danh `tf-deploy`, không cần thêm `impersonate_service_account` vào cả hai block. Dự án phải bật Compute Engine API và service account phải có quyền tạo VPC, chẳng hạn role phù hợp với quản lý mạng theo phạm vi được phê duyệt.

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan
```

Chạy `terraform apply` **chỉ khi** có môi trường thử nghiệm, quyền thay đổi tài nguyên và đã xem kỹ kế hoạch; có thể phát sinh chi phí hoặc thay đổi hạ tầng. Sau khi thực hành, hủy tài nguyên thử nghiệm theo quy trình của nhóm.

### Cách thay thế: mạo danh ngay trong cấu hình Terraform

Nếu ADC đang là **danh tính nguồn** (ví dụ `gcloud auth application-default login` bằng user, chưa mạo danh), có thể chọn service account riêng cho từng môi trường bằng tham số ở **cả hai nơi**:

```hcl
terraform {
  backend "gcs" {
    bucket                      = "my-terraform-state"
    prefix                      = "dev/network"
    impersonate_service_account = "tf-deploy@my-project.iam.gserviceaccount.com"
  }
}

provider "google" {
  project                     = "my-project"
  region                      = "asia-southeast1"
  impersonate_service_account = "tf-deploy@my-project.iam.gserviceaccount.com"
}
```

Đây là **phương án thay thế** cho cách ADC đã impersonate ở trên, không chèn thêm vào mẫu `main.tf` như một cấu hình thứ hai. Danh tính nguồn cần `roles/iam.serviceAccountTokenCreator` trên service account đích. Có thể chọn **hai** service account khác nhau nếu muốn tách quyền thao tác state khỏi quyền tạo hạ tầng.

**Vì sao phải đặt ở hai nơi?** Terraform khởi tạo **GCS backend trong `terraform init`**, trước khi cấu hình Google provider được dùng để quản lý tài nguyên. Thiết lập impersonation ở provider không tự truyền sang backend. Nếu backend chỉ có quyền đọc state nhưng provider được cấp đủ quyền tạo VPC, `init` vẫn có thể thất bại với 403; trường hợp ngược lại, `init` thành công nhưng `plan`/`apply` bị từ chối khi gọi API dịch vụ.

## 4. CI/CD: GitHub Actions dùng Workload Identity Federation

Một job chạy ở GitHub có OIDC token chứng minh tổ chức, repository, nhánh và ngữ cảnh thực thi. Thay vì lưu JSON key trong GitHub Secrets, ta cấu hình Google Cloud **tin cậy đúng claim** của job đó. Action `google-github-actions/auth` tạo tệp cấu hình credentials tạm thời rồi xuất `GOOGLE_APPLICATION_CREDENTIALS` để Terraform sử dụng.

### Bước 1: thiết lập WIF trước khi chạy pipeline

Các thao tác bootstrap sau do **người quản trị** có quyền tạo pool/provider, cập nhật IAM và service account thực hiện. Dùng dự án chứa pool là `my-project`, **project number** là `123456789012`, GitHub **owner ID** là `111111` và **repository ID** là `222222`. Phải thay bằng ID thật của tổ chức/repository; số ID ổn định hơn tên có thể bị đổi hoặc tái sử dụng.

Tạo service account chuyên dụng cho CI nếu chưa có:

```bash
gcloud iam service-accounts create tf-deploy --project=my-project --display-name="Terraform deployment"
```

Tạo pool WIF và OIDC provider. Các tham số ở cùng một dòng để dễ sao chép và nhìn thấy điều kiện tin cậy; không chạy bằng ID giả:

```bash
gcloud iam workload-identity-pools create github-ci --project=my-project --location=global --display-name="GitHub Terraform"

gcloud iam workload-identity-pools providers create-oidc github --project=my-project --location=global --workload-identity-pool=github-ci --issuer-uri="https://token.actions.githubusercontent.com/" --attribute-mapping="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id" --attribute-condition="assertion.repository_owner_id=='111111' && assertion.repository_id=='222222' && assertion.ref=='refs/heads/main'"
```

Điều kiện ở provider giới hạn **đúng tổ chức, đúng repository và nhánh `main`**. Thuộc tính dùng để cấp quyền `attribute.repository_id` phải được map trước. Nếu sau này chạy từ tag, môi trường hoặc nhánh khác, phải thiết kế lại điều kiện **có chủ đích**; tránh mở toàn bộ issuer GitHub vì issuer này dùng chung cho nhiều tổ chức.

Cho phép **duy nhất repository đã chọn** mạo danh service account bằng role WIF thích hợp:

```bash
gcloud iam service-accounts add-iam-policy-binding tf-deploy@my-project.iam.gserviceaccount.com --project=my-project --role=roles/iam.workloadIdentityUser --member="principalSet://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/github-ci/attribute.repository_id/222222"
```

Tiếp theo, cấp cho `tf-deploy` quyền cần thiết trên bucket state và những tài nguyên thực sự được khai báo trong Terraform. Chẳng hạn, quyền object trên **bucket state** là một khoản cấp quyền riêng; quyền quản lý VPC ở **dự án đích** là khoản cấp quyền khác. Thao tác thiết lập trust, role và bucket thường thuộc bootstrap IAM do người quản trị kiểm soát, không nên yêu cầu Terraform của chính pipeline tự cấp quyền ban đầu cho mình.

Đảm bảo Security Token Service API và IAM Service Account Credentials API cần thiết đã được kích hoạt theo tài liệu thiết lập WIF/impersonation. Các cập nhật IAM/WIF đôi khi cần vài phút để có hiệu lực.

### Bước 2: workflow chỉ lập kế hoạch

Đặt workflow GitHub Actions dưới `.github/workflows/terraform-plan.yml`. Ví dụ chủ động chỉ chạy bằng `workflow_dispatch`, với quyền GitHub tối thiểu cho việc lấy OIDC token; định nghĩa tài nguyên Terraform ở thư mục gốc repository.

```yaml
name: Terraform plan with short-lived identity

on:
  workflow_dispatch:

permissions:
  contents: read
  id-token: write

jobs:
  terraform-plan:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v3
        with:
          project_id: my-project
          workload_identity_provider: projects/123456789012/locations/global/workloadIdentityPools/github-ci/providers/github
          service_account: tf-deploy@my-project.iam.gserviceaccount.com
          create_credentials_file: true
          export_environment_variables: true

      - name: Install Terraform
        uses: hashicorp/setup-terraform@v4

      - name: Initialize backend
        run: terraform init -input=false

      - name: Check HCL
        run: terraform fmt -check

      - name: Validate configuration
        run: terraform validate

      - name: Show plan
        run: terraform plan -input=false -lock-timeout=5m
```

Trong workflow này:

1. `id-token: write` cho phép job nhận OIDC token từ GitHub; `contents: read` phục vụ checkout. Đây là quyền phía **GitHub**, chưa phải quyền IAM phía Google Cloud.
2. `auth@v3` trao đổi danh tính qua provider WIF và mạo danh service account. Action tạo credentials configuration tạm cho ADC; không cần `credentials_json`, không lưu khóa JSON vào Secrets.
3. `setup-terraform@v4` cung cấp Terraform CLI. `terraform init` dùng credentials vừa được xuất cho **GCS backend**; `plan` dùng cùng ADC cho **Google provider** ở ví dụ phần 3.
4. Điều kiện WIF yêu cầu nhánh `main`: hãy chạy workflow từ nhánh đó. Job này **không gọi `terraform apply`**; triển khai thật cần quy trình duyệt và kiểm soát môi trường riêng.

Action tạo tệp `gha-creds-*.json` tạm trong workspace và sẽ dọn bằng post-action. Đưa mẫu sau vào các quy tắc ignore để tránh vô tình đưa credentials configuration vào commit hoặc artifact:

```gitignore
gha-creds-*.json
.terraform/
*.tfstate
*.tfstate.backup
```

**Đừng** bỏ qua `.terraform.lock.hcl`: lock file phiên bản provider thường nên được commit để các lần chạy tái lập được. Nếu dùng runner tự quản lý, cần bảo đảm workspace được làm sạch đúng cách sau job.

### Có cần service account trong WIF không?

Không phải lúc nào cũng cần. Google Cloud cho phép cấp IAM role **trực tiếp** cho WIF principal khi dịch vụ hỗ trợ; cách này bỏ bước mạo danh và có thể giảm số danh tính phải quản trị. Tuy nhiên một số API chưa hỗ trợ tất cả kiểu federated principal. Ví dụ này chọn mạo danh service account để Terraform làm việc ổn định với nhiều loại tài nguyên; quyết định cuối cùng phụ thuộc API và ranh giới quyền của môi trường.

## 5. Phân quyền và bảo vệ state

| Điểm cấp quyền | Cấp cho ai | Mục đích | Sai lầm thường gặp |
| --- | --- | --- | --- |
| Service account `tf-deploy` | Người phát triển: `roles/iam.serviceAccountTokenCreator` **trên SA** | Xin access token impersonation khi làm cục bộ | Cấp Token Creator ở cấp dự án quá rộng. |
| Service account `tf-deploy` | WIF `principalSet`: `roles/iam.workloadIdentityUser` **trên SA** | Cho job GitHub mạo danh SA | Cho mọi repo hoặc toàn bộ pool dùng SA. |
| Bucket `my-terraform-state` | SA `tf-deploy`: quyền object đọc/ghi/xóa cần cho state/locking, ví dụ `roles/storage.objectAdmin` trên bucket | `terraform init`, đọc/ghi state và khóa state | Quên quyền backend hoặc cấp Storage Admin toàn dự án. |
| Tài nguyên GCP | SA `tf-deploy`: role đúng cho dịch vụ/tài nguyên, ví dụ quyền quản lý VPC trong bài | `plan`/`apply` lên tài nguyên | Cấp `roles/owner` hoặc `roles/editor` để “chữa” lỗi 403. |

GCS backend hỗ trợ **state locking**; state là dữ liệu nhạy cảm vì có thể chứa thuộc tính bí mật của tài nguyên ngay cả khi output được đánh dấu `sensitive`. Hãy giới hạn IAM bucket, bật versioning, dùng cơ chế mã hóa thích hợp và bảo vệ lịch sử phiên bản. **Không** nhét access token, JSON private key hoặc nội dung credential vào `.tf`, `.tfvars`, `-backend-config`, log build hay artifact. Nếu cấu hình backend đổi, chạy lại `terraform init -reconfigure` có chủ đích và kiểm tra ảnh hưởng tới state hiện có.

Để tăng khả năng truy vết, cấp service account theo **môi trường** (dev/staging/prod) và tách runner/permission tương ứng; theo dõi **Cloud Audit Logs** cho thao tác trên tài nguyên và việc sử dụng IAM Credentials API khi áp dụng impersonation. Một service account không nên có khả năng quản lý tất cả project chỉ vì nó dùng cho Terraform.

## 6. Chẩn đoán lỗi xác thực thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra và hướng xử lý |
| --- | --- | --- |
| `terraform init` trả `403` với GCS | Danh tính backend thiếu quyền object, bucket sai, IAM chưa kịp cập nhật | Xác minh bucket tồn tại, SA/ADC mà backend dùng và IAM **trên bucket**; đợi propagation nếu vừa đổi policy. |
| `init` thành công nhưng `plan` trả `403` | Google provider dùng danh tính khác hoặc SA thiếu quyền API dịch vụ | Kiểm tra project/provider, role trên resource, dịch vụ API đã bật; không suy luận rằng init PASS nghĩa provider PASS. |
| `iam.serviceAccounts.getAccessToken denied` | Danh tính gốc không được mạo danh service account | Với user ADC kiểm tra `roles/iam.serviceAccountTokenCreator`; với WIF kiểm tra `roles/iam.workloadIdentityUser` và principal set. |
| `invalid_grant` hoặc token hết hạn | Phiên đăng nhập cục bộ bị thu hồi/hết hạn, nguồn OIDC không còn hợp lệ, hoặc clock sai | Đăng nhập ADC lại hoặc chạy mới CI job; tránh tái dùng token sao chép thủ công. |
| GitHub báo không lấy được OIDC token | Thiếu `id-token: write`, thứ tự bước auth không đúng, job không có quyền OIDC | Kiểm tra `permissions` và thứ tự `checkout → auth → terraform`. |
| WIF trả lỗi issuer/audience/attribute condition | Sai project **number**, tên pool/provider, claim repository/owner ID, nhánh hoặc audience | So sánh tên provider đầy đủ và claim trong OIDC với mapping/condition; không nới condition chỉ để job chạy. |
| Terraform vẫn dùng khóa cũ | `GOOGLE_APPLICATION_CREDENTIALS` trỏ sang file không đúng | Kiểm tra đường dẫn biến môi trường và ưu tiên ADC; loại bỏ cấu hình cũ. |

Khi kiểm tra, dùng các lệnh **không in token** như `gcloud auth list`, `gcloud config list account`, `terraform version` và kiểm tra chính sách IAM/bucket. `gcloud auth list` chỉ phản ánh tài khoản của **gcloud CLI**, không chứng minh Terraform đang dùng cùng ADC. Tránh chạy `gcloud auth application-default print-access-token` vào log CI: đây là token có thể bị sử dụng nếu lộ.

## 7. Tình huống áp dụng: tách dev và production

Một nhóm triển khai VPC dev rồi mở rộng Terraform cho GKE và Cloud Run ở production. Thiết kế hợp lý là:

- Nhà phát triển chỉ mạo danh `tf-dev` để đọc/đề xuất thay đổi trong dev.
- Pipeline production lấy OIDC token từ workflow được bảo vệ, WIF giới hạn đúng repository, nhánh và ngữ cảnh, sau đó mạo danh `tf-prod` với role phù hợp.
- Backend state dev và production tách bucket hoặc prefix cùng quyền IAM tương ứng; người có quyền dev không tự động đọc/ghi được production state.
- Bước `plan` và bước `apply` được kiểm soát theo quy trình phê duyệt; không dùng một khóa JSON cố định chung cho các môi trường.
- Nhật ký IAM và Cloud Audit Logs cho phép điều tra người/job khởi tạo lệnh cũng như service account đã thực hiện API call.

**Tiêu chí hoàn thành thực hành:** Có thể giải thích danh tính nào tạo token, IAM role nào cho phép impersonation, IAM role nào cho phép thay đổi tài nguyên, backend đang dùng credentials nào và vì sao máy chạy CI không cần khóa service account tải xuống.

## Tài liệu chính thức và tham khảo

1. Google Cloud — [Authentication for Terraform](https://docs.cloud.google.com/docs/terraform/authentication).
2. Google Cloud — [How Application Default Credentials works](https://docs.cloud.google.com/docs/authentication/application-default-credentials).
3. Google Cloud — [Use service account impersonation](https://docs.cloud.google.com/docs/authentication/use-service-account-impersonation) và [Service account credentials](https://docs.cloud.google.com/iam/docs/service-account-creds).
4. Google Cloud — [Configure Workload Identity Federation with deployment pipelines](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines).
5. HashiCorp — [Terraform GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs).
6. GitHub Actions — [google-github-actions/auth](https://github.com/google-github-actions/auth) và [hashicorp/setup-terraform](https://github.com/hashicorp/setup-terraform).

*Ví dụ phản ánh cú pháp công khai tại thời điểm biên soạn. Trước khi triển khai production, đối chiếu phiên bản action/CLI, chính sách IAM và tính năng dịch vụ đang dùng.*
