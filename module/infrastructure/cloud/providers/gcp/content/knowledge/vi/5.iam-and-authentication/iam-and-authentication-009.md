# Workload Identity Federation cho hệ thống bên ngoài GCP

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Giải thích vì sao **Workload Identity Federation (WIF)** giúp workload ở bên ngoài Google Cloud truy cập API Google Cloud mà không phải lưu service account key dài hạn.
2. Phân biệt **Identity Provider (IdP)**, **Workload Identity Pool**, **Provider**, **Security Token Service (STS)**, **federated principal**, **service account impersonation** và quyền IAM trên tài nguyên.
3. Thiết kế ranh giới tin cậy bằng issuer, audience, attribute mapping, attribute condition và chính sách phân quyền tối thiểu.
4. Thực hiện một luồng xác thực mẫu từ **GitHub Actions** vào Google Cloud, biết cách áp dụng tương tự cho AWS, Azure, GitLab và hệ thống Kubernetes/on-premises.
5. Nhận diện lỗi xác thực hoặc phân quyền, xây dựng quy trình kiểm thử và vận hành WIF an toàn cho Compute Engine, Cloud Run, GKE, Cloud Storage và CI/CD.

## 1. Bài toán: ứng dụng nằm ngoài Google Cloud cần truy cập tài nguyên GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá cách quản lý project, IAM và VPC; triển khai Compute Engine, GKE, Cloud Run; chọn dịch vụ lưu trữ, cơ sở dữ liệu; tự động hóa phát hành, bảo vệ tài nguyên, quan sát độ tin cậy và kiểm soát chi phí. Không phải mọi thành phần trong một hệ thống đa môi trường đều chạy trên Google Cloud.

Các tình huống phổ biến:

- Pipeline **GitHub Actions** build ứng dụng Java và phát hành phiên bản lên **Cloud Run**.
- Runner **GitLab CI** ở ngoài GCP đọc artifact từ **Cloud Storage** hoặc đẩy image lên **Artifact Registry**.
- Ứng dụng chạy trên **AWS EC2** hoặc **Azure VM** gọi **BigQuery** hay API Google Cloud.
- Container trong **Kubernetes ngoài GKE** cần lấy dữ liệu từ một bucket hoặc gửi sự kiện lên Pub/Sub.
- Một hệ thống chạy tại **trung tâm dữ liệu doanh nghiệp** cần truy cập Google Cloud thông qua danh tính do IdP nội bộ cấp.

Một cách triển khai cũ là tạo **IAM service account**, tải **JSON private key** và lưu key trong secret của CI hoặc server bên ngoài. Key đó có thể tồn tại lâu, dễ bị sao chép và đòi hỏi cơ chế cấp phát, xoay vòng, kiểm kê và thu hồi riêng.

**Workload Identity Federation** giải quyết vấn đề bằng cách thiết lập quan hệ tin cậy giữa Google Cloud và danh tính bên ngoài. Workload dùng bằng chứng danh tính ngắn hạn do hệ thống đang chạy cấp; Google Cloud xác thực bằng chứng này, sau đó cấp token ngắn hạn với phạm vi quyền IAM tương ứng. Cách này giảm nhu cầu phân phát **service account key dài hạn**.

> WIF không có nghĩa một dịch vụ bên ngoài được tự động tin cậy. Người quản trị phải cấu hình đúng **nguồn phát hành**, **đối tượng nhận token**, **thuộc tính danh tính**, **điều kiện được phép** và **quyền đối với tài nguyên**.

## 2. Những thành phần của Workload Identity Federation

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **External workload** | Chương trình hoặc pipeline cần gọi API Google Cloud | Job GitHub Actions triển khai Java API |
| **External Identity Provider (IdP)** | Hệ thống phát hành bằng chứng xác thực mà Google Cloud có thể kiểm chứng | GitHub OIDC, Microsoft Entra ID, AWS, IdP OIDC/SAML nội bộ |
| **Subject token / assertion** | Bằng chứng danh tính bên ngoài, thường có thời hạn ngắn | JWT OIDC có issuer, subject, audience, expiry, claims |
| **Workload Identity Pool** | Không gian quản lý danh tính liên kết; nơi tập hợp các provider | github-prod |
| **Workload Identity Pool Provider** | Quy định nguồn tin cậy, loại token, issuer, audience và cách chuyển claims | github-main sử dụng GitHub OIDC |
| **Attribute mapping** | Biến claims của IdP thành các thuộc tính mà Google Cloud hiểu | google.subject, attribute.repository_id |
| **Attribute condition** | Lọc những danh tính được phép đi qua provider | Chỉ repository ID xác định trên nhánh main |
| **Google Cloud STS** | Kiểm chứng bằng chứng bên ngoài và trao đổi lấy federated access token | Security Token Service API |
| **IAM principal / principalSet** | Biểu diễn danh tính hoặc tập danh tính liên kết trong chính sách IAM | Tài khoản ngoài GCP được định danh bởi subject hoặc attribute |
| **IAM service account (tùy chọn)** | Danh tính Google Cloud mà workload có thể được phép mạo danh | cloud-deployer@shop-prod-001.iam.gserviceaccount.com |

### Phân biệt project, pool và provider

**Project chứa pool** thường là một project quản lý danh tính riêng; **project chứa tài nguyên** có thể là project khác. Không nên suy rằng project ID của API đích cũng chính là project ID của WIF pool.

Một pool có thể chứa nhiều provider, nhưng các danh tính trong cùng pool chia sẻ một không gian nhận diện. Nếu dùng nhiều nguồn IdP hoặc môi trường có rủi ro khác nhau, hãy cân nhắc **tách pool** để tránh các thuộc tính được ánh xạ từ nguồn khác nhau vô tình được xem là cùng một nhóm có quyền.

Ví dụ cấu trúc:

~~~text
Project identity-hub-001
└── Workload Identity Pool: github-prod
    └── OIDC Provider: github-main
        └── GitHub Actions từ một repository/nhánh được cho phép

Project shop-prod-001
├── Cloud Run application
├── Artifact Registry repository
└── IAM service account: cloud-deployer
    └── Có thể được danh tính GitHub liên kết mạo danh theo IAM
~~~

Trong định danh IAM của danh tính liên kết, phải dùng **project number** của project chứa pool, chẳng hạn **123456789012**, không dùng tên project **identity-hub-001**.

## 3. Cơ chế xác thực: từ token bên ngoài đến quyền Google Cloud

~~~mermaid
sequenceDiagram
    participant W as Workload ngoài GCP
    participant I as External IdP
    participant S as Google Cloud STS
    participant A as IAM Credentials API
    participant R as Google Cloud API
    W->>I: Yêu cầu bằng chứng danh tính
    I-->>W: Token/assertion ngắn hạn
    W->>S: Trao đổi token theo pool/provider
    Note over S: Kiểm tra issuer, audience,<br/>chữ ký, thời hạn, mapping, condition
    S-->>W: Federated access token
    alt Truy cập trực tiếp
        W->>R: Gọi API bằng federated token
        Note over R: Kiểm tra IAM của principal liên kết
        R-->>W: Kết quả hoặc từ chối
    else Qua service account
        W->>A: Yêu cầu mạo danh service account
        Note over A: Kiểm tra roles/iam.workloadIdentityUser
        A-->>W: Access token ngắn hạn của service account
        W->>R: Gọi API bằng token của service account
        Note over R: Kiểm tra IAM của service account
        R-->>W: Kết quả hoặc từ chối
    end
~~~

### Bước 1: workload nhận danh tính tại nơi đang chạy

Ví dụ GitHub Actions phát hành OIDC token cho job đã được cấp quyền **id-token: write**. Token thường chứa:

- **iss (issuer)**: địa chỉ nguồn phát hành, với GitHub Actions là **https://token.actions.githubusercontent.com**.
- **sub (subject)**: danh tính gắn với workflow, repository, nhánh hoặc môi trường theo quy tắc của IdP.
- **aud (audience)**: bên nhận token dự kiến, giúp chống việc tái sử dụng token cho mục đích khác.
- **exp/iat**: thời hạn và thời điểm phát hành.
- **Các claim bổ sung**: repository ID, repository owner ID, ref, workflow và các thông tin ngữ cảnh do IdP cung cấp.

Một token từ GitHub **không tự động là token của Google Cloud**. Token phải được phía Google Cloud chấp nhận theo cấu hình provider.

### Bước 2: STS kiểm chứng và trao đổi token

Workload gửi subject token qua **Security Token Service**. Provider đối chiếu nhà phát hành, chữ ký, audience, thời hạn, attribute mapping và attribute condition. Nếu xác thực hợp lệ, STS trả về **federated access token** ngắn hạn. Nếu kiểm tra thất bại, quá trình dừng tại đây trước khi xét quyền truy cập dịch vụ.

### Bước 3: IAM quyết định truy cập tài nguyên

**Xác thực thành công không có nghĩa được cấp quyền**. Sau STS còn phải có IAM policy cấp đúng quyền, chẳng hạn đọc object trong một bucket hoặc xem Cloud Run services. Hai phương án cấp quyền sẽ được phân tích ở phần sau.

## 4. Hai mô hình phân quyền: trực tiếp và service account impersonation

### 4.1. Direct resource access

Khi API/tài nguyên hỗ trợ **federated principal** trong IAM, quản trị viên có thể cấp role trực tiếp cho danh tính ngoài GCP.

Ví dụ một ứng dụng ngoài GCP chỉ cần đọc object từ một bucket cụ thể. IAM binding ở **bucket** có thể cấp **roles/storage.objectViewer** cho danh tính liên kết đã được ánh xạ từ một repository hoặc subject.

Hai dạng thành viên IAM thường dùng:

~~~text
# Một subject được ánh xạ:
principal://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/github-prod/subject/SUBJECT

# Nhóm các danh tính có cùng thuộc tính repository_id:
principalSet://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/github-prod/attribute.repository_id/987654321
~~~

**Ưu điểm:** không cần tạo và quản lý service account trung gian; vai trò IAM được gán trực tiếp trên tài nguyên cho đối tượng đã được liên kết. **Giới hạn:** một số API hoặc thao tác chưa hỗ trợ danh tính liên kết trực tiếp, cần xác minh tương thích của dịch vụ.

### 4.2. Service account impersonation

Nếu cần sử dụng service account làm danh tính thao tác:

1. Tạo hoặc chọn **IAM service account** theo từng mục đích và môi trường.
2. Cấp **roles/iam.workloadIdentityUser** trên **chính service account đó** cho federated principal/principalSet phù hợp.
3. Cấp quyền truy cập tài nguyên tối thiểu cho **service account**, chẳng hạn quyền xem Cloud Run hoặc thao tác trên một repository Artifact Registry cụ thể.
4. Workload dùng federated token yêu cầu **IAM Credentials API** phát hành token ngắn hạn của service account, rồi gọi dịch vụ đích.

**Không cần tạo service account key** trong đường đi này. Quyền impersonation và quyền truy cập tài nguyên là hai lớp riêng biệt.

| Tiêu chí | Direct resource access | Service account impersonation |
|---|---|---|
| Danh tính được API đích nhìn thấy | Federated principal | IAM service account |
| Vai trò IAM trên tài nguyên | Cấp trực tiếp cho principal/principalSet | Cấp cho service account |
| Cần roles/iam.workloadIdentityUser | Không | Có, trên service account |
| Có service account trung gian | Không | Có |
| Phù hợp | Dịch vụ hỗ trợ danh tính federated trực tiếp | Công cụ/API cần service account hoặc kiến trúc đang sử dụng service account |
| Đánh đổi | Cần kiểm tra hỗ trợ của từng API và cách cấp policy | Thêm quyền impersonation và vận hành service account; nhiều nguồn có thể dùng chung một identity nếu cấu hình rộng |

**Nguyên tắc lựa chọn:** ưu tiên direct resource access khi dịch vụ hỗ trợ và cách cấp quyền đáp ứng yêu cầu; dùng impersonation khi cần tương thích hoặc phù hợp với quy trình phân quyền. Không cấp đồng thời hai đường rộng hơn nhu cầu.

### 4.3. WIF khác các cơ chế xác thực gần tên

- **Workload Identity Federation (bài này)**: kết nối workload **ở ngoài Google Cloud** với Google Cloud IAM.
- **Workload Identity Federation for GKE**: cơ chế riêng giúp pod trên **GKE** dùng danh tính workload; có khái niệm liên quan nhưng cách thiết lập khác với provider của GitHub hoặc AWS.
- **Workforce Identity Federation**: liên kết danh tính **người dùng**, phục vụ tương tác của lực lượng lao động; khác mục tiêu máy/chương trình.
- **Service account key**: khóa riêng dài hạn được tải xuống; không phải cơ chế token exchange của WIF.
- **gcloud auth login** của người dùng: đăng nhập tương tác, không phải mô hình xác thực chuẩn cho job CI bên ngoài.

## 5. Thiết kế ranh giới tin cậy trước khi tạo pool

### 5.1. Tại sao chỉ tin issuer là chưa đủ?

GitHub Actions OIDC có **issuer chung** cho nhiều tổ chức và repository. Nếu provider chỉ chấp nhận mọi token của issuer GitHub, một workflow không thuộc tổ chức của bạn có thể cố gắng trao đổi token. Muốn giới hạn rõ ràng phải dùng **attribute condition** và IAM policy.

Đối với GitHub, tài liệu Google Cloud khuyến nghị dùng **repository_id** và **repository_owner_id** dạng ID ổn định. Các tên repository và owner có thể được tái sử dụng hoặc bị chiếm lại sau khi xóa/đổi tên; ID số giúp giảm rủi ro nhầm danh tính.

Ví dụ điều kiện CEL:

~~~text
assertion.repository_owner_id == '24681012'
  && assertion.repository_id == '987654321'
  && assertion.ref == 'refs/heads/main'
~~~

Điều kiện trên chỉ chấp nhận token có đúng owner, repository và ref dự kiến. Nếu production chỉ triển khai từ một **GitHub Environment** đã được bảo vệ bằng phê duyệt, có thể bổ sung điều kiện dựa trên claim tương ứng sau khi kiểm tra nội dung token thực tế.

**Điều kiện trên provider** giới hạn danh tính được trao đổi token; **IAM binding** lại quyết định họ được làm gì. Cả hai đều cần được thiết kế theo phạm vi tối thiểu.

### 5.2. Các lớp kiểm soát chính

| Lớp | Câu hỏi cần trả lời | Ví dụ hành động |
|---|---|---|
| **Issuer** | Ai thực sự phát hành token? | Chỉ chấp nhận OIDC issuer đã xác minh |
| **Audience** | Token có được tạo riêng cho WIF provider này? | Ưu tiên audience mặc định là URL/định danh provider |
| **Subject** | Một thực thể bên ngoài được nhận diện thế nào? | Ánh xạ google.subject từ claim phù hợp |
| **Mapped attributes** | Những thuộc tính nào dùng trong policy? | repository_id, repository_owner_id, ref |
| **Attribute condition** | Danh tính nào được phép tham gia federation? | Chỉ repo ID và nhánh main |
| **IAM permission** | Danh tính đó có thể thao tác trên tài nguyên nào? | Quyền xem Cloud Run trong project hoặc đọc một bucket |
| **Pipeline protection** | Ai được sửa workflow, trigger và code triển khai? | Protected branch, review, bảo vệ environment, hạn chế quyền token |
| **Lifecycle/review** | Khi đổi repo, tách môi trường hoặc thu hồi quyền, ai cập nhật? | Inventory, chủ sở hữu, audit log, định kỳ rà soát |

### 5.3. Phân tách môi trường

Một kiến trúc đơn giản:

~~~text
GitHub repository A, branch develop
  → WIF provider cho dev
  → principalSet dev
  → service account deploy-dev
  → shop-dev-001

GitHub repository A, branch main và environment được bảo vệ
  → WIF provider cho prod
  → principalSet prod
  → service account deploy-prod
  → shop-prod-001
~~~

Không cấp quyền triển khai production cho mọi job có quyền đọc repository. Khi cân nhắc cấu trúc pool/provider, cần đặt ranh giới theo **nguồn tin cậy, môi trường và độ nhạy**. Cấp principalSet cho cả pool với ký tự đại diện có thể trao quyền cho nhiều danh tính hơn dự kiến.

## 6. Thực hành mẫu: GitHub Actions truy cập Google Cloud

Tình huống: nhóm phát triển muốn dùng một workflow trong repository được phê duyệt để kiểm tra trạng thái dịch vụ **Cloud Run** ở production, sau đó mới bổ sung bước phát hành. Mục tiêu đầu tiên là chứng minh **OIDC → STS → service account → API Google Cloud** hoạt động.

Các tên và ID sau đây chỉ là **giả định**, phải thay bằng dữ liệu thực:

| Biến mẫu | Giá trị giả định | Ý nghĩa |
|---|---|---|
| Project giữ pool | identity-hub-001 | Quản lý ranh giới federation |
| Project number của pool | 123456789012 | Bắt buộc trong resource name và principalSet |
| Pool ID | github-prod | Pool cho luồng production |
| Provider ID | github-main | Provider OIDC tin GitHub Actions |
| GitHub repository owner ID | 24681012 | ID số của organization được phép |
| GitHub repository ID | 987654321 | ID số của repo được phép |
| Project tài nguyên | shop-prod-001 | Chứa Cloud Run service |
| Service account | cloud-deployer@shop-prod-001.iam.gserviceaccount.com | Danh tính dùng bởi workflow |

### Bước 0 — Chuẩn bị quyền và API

Người quản trị cần đủ quyền để quản lý Workload Identity Pool/Provider, IAM service account và IAM policy trên tài nguyên đích. Có thể tách vai trò quản trị IdP, quản trị IAM và người sở hữu workload.

Các API cần thiết theo kịch bản gồm **IAM API**, **Security Token Service API**, **Service Account Credentials API** và những API tài nguyên đích như Cloud Run. Kiểm tra trạng thái API trước khi chạy. Lệnh mẫu dưới đây là hành động quản trị và chỉ thực hiện ở project được phép:

~~~bash
gcloud services enable \
  iam.googleapis.com \
  sts.googleapis.com \
  iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project=identity-hub-001

# Xác nhận PROJECT NUMBER thực; không tự suy từ project ID
gcloud projects describe identity-hub-001 \
  --format="value(projectNumber)"
~~~

Lệnh tiếp theo dùng **123456789012** làm ví dụ về project number đã đọc được từ kết quả. Không thể thay bằng chuỗi project ID.

### Bước 1 — Tạo Workload Identity Pool

~~~bash
gcloud iam workload-identity-pools create github-prod \
  --project=identity-hub-001 \
  --location=global \
  --display-name="GitHub production" \
  --description="OIDC federation cho workflow production"

gcloud iam workload-identity-pools describe github-prod \
  --project=identity-hub-001 \
  --location=global
~~~

Với cấu hình WIF thông thường cho GitHub, **location** của pool là **global**. Tên pool là tài nguyên thuộc project quản lý danh tính, không phải tên một service account.

### Bước 2 — Tạo GitHub OIDC provider với điều kiện chặt

~~~bash
gcloud iam workload-identity-pools providers create-oidc github-main \
  --project=identity-hub-001 \
  --location=global \
  --workload-identity-pool=github-prod \
  --issuer-uri="https://token.actions.githubusercontent.com/" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository_owner_id=='24681012' && assertion.repository_id=='987654321' && assertion.ref=='refs/heads/main'"

gcloud iam workload-identity-pools providers describe github-main \
  --project=identity-hub-001 \
  --location=global \
  --workload-identity-pool=github-prod
~~~

**Ý nghĩa cấu hình:**

- **issuer-uri** xác định nguồn OIDC của GitHub.
- **google.subject** là ánh xạ bắt buộc để nhận diện subject (giới hạn chiều dài và tính ổn định của claim cần được kiểm tra).
- **attribute.repository_id** và **attribute.repository_owner_id** cho phép IAM và điều kiện dựa vào ID số.
- **attribute.ref** giúp phân biệt nhánh; chỉ chấp nhận main trong ví dụ.
- **Không chỉ định allowed-audiences** khiến provider dùng quy tắc audience mặc định của Google Cloud. Token phải được yêu cầu cho provider phù hợp; không tùy tiện nới rộng audience để làm cho một token không đúng mục đích vượt qua kiểm tra.

**Chú ý:** Điều kiện GitHub chỉ đúng nếu các claim và giá trị thực sự khớp với workflow, repository, tổ chức và event. Khi thay branch, GitHub Environment hoặc trigger, kiểm tra nội dung claim và điều chỉnh policy qua quy trình review.

### Bước 3 — Cấp quyền impersonation cho federated principal

Giả sử service account đã được tạo trong **shop-prod-001** và chủ sở hữu đã phê duyệt việc cho GitHub Actions mạo danh nó. Trên **chính service account**:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  cloud-deployer@shop-prod-001.iam.gserviceaccount.com \
  --project=shop-prod-001 \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/github-prod/attribute.repository_id/987654321"
~~~

Binding này cho phép tập danh tính đã được ánh xạ với **repository_id=987654321** mạo danh service account, **nếu** token đi qua provider hợp lệ và đáp ứng attribute condition. Trong một pool có nhiều provider, phải rà soát khả năng thuộc tính từ provider khác cũng khớp principalSet. Dùng pool riêng cho biên giới tin cậy nhạy cảm giúp giảm rủi ro này.

### Bước 4 — Gán quyền Google Cloud tối thiểu cho service account

Để kiểm thử chỉ **liệt kê Cloud Run services**, ví dụ có thể cấp quyền chỉ đọc phù hợp ở project hoặc tài nguyên đích:

~~~bash
# Ví dụ cấp quyền xem Cloud Run ở project đích
gcloud projects add-iam-policy-binding shop-prod-001 \
  --member="serviceAccount:cloud-deployer@shop-prod-001.iam.gserviceaccount.com" \
  --role="roles/run.viewer"
~~~

Nếu chuyển từ kiểm tra sang **triển khai**, cần thiết kế thêm quyền đúng thao tác: chẳng hạn quyền phát hành Cloud Run, quyền đọc image trong Artifact Registry và quyền **iam.serviceAccounts.actAs** với runtime service account khi cần. Chỉ cấp trong phạm vi resource và môi trường thật sự cần. **roles/iam.workloadIdentityUser** không tự cấp quyền deploy ứng dụng.

### Bước 5 — Cấu hình workflow GitHub Actions

Tạo workflow tại repository mà organization sở hữu và đang cho phép federation. Nội dung mẫu chỉ dùng lệnh **đọc trạng thái**, chưa phát hành hay sửa tài nguyên:

~~~yaml
name: Verify Google Cloud WIF

on:
  workflow_dispatch:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write

jobs:
  verify-identity:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Authenticate to Google Cloud
        id: auth
        uses: google-github-actions/auth@v3
        with:
          workload_identity_provider: projects/123456789012/locations/global/workloadIdentityPools/github-prod/providers/github-main
          service_account: cloud-deployer@shop-prod-001.iam.gserviceaccount.com
          project_id: shop-prod-001

      - name: Set up gcloud
        uses: google-github-actions/setup-gcloud@v2

      - name: Verify target
        run: |
          gcloud projects describe shop-prod-001 --format="value(projectId)"
          gcloud run services list --project=shop-prod-001 --region=asia-southeast1
~~~

Giải thích:

1. **id-token: write** cho phép job yêu cầu OIDC token từ GitHub; từ **write** ở đây không hàm ý cấp quyền ghi lên Google Cloud. Quyền Google Cloud là do IAM quyết định.
2. **google-github-actions/auth** nhận token và cấu hình việc liên kết qua provider. Khi chỉ định **service_account**, action dùng đường đi impersonation đã cấp quyền.
3. **setup-gcloud** chuẩn bị CLI cho bước tiếp theo.
4. Các lệnh đọc project và Cloud Run giúp kiểm tra ngữ cảnh. Bài này chưa yêu cầu thực hiện triển khai thật.

Phiên bản **auth@v3** trong ví dụ là phiên bản chính của action được tài liệu repository công bố ở thời điểm biên soạn; khi áp dụng production, xác nhận phiên bản phù hợp với runner/Node và **pin action theo commit SHA được kiểm duyệt** theo chính sách bảo vệ chuỗi cung ứng phần mềm.

**Cần kiểm tra ngay sau khi tạo:** action, pool/provider và IAM có thể mất một khoảng thời gian để các thay đổi lan truyền. Không nới quyền IAM hoặc bỏ attribute condition chỉ vì lần chạy đầu gặp lỗi tạm thời.

### Bước 6 — Xác nhận danh tính và quyền truy cập

Các điều cần quan sát trong job:

- Bước auth hoàn thành: GitHub đã cung cấp token với **aud/iss/claims** đúng và STS trao đổi thành công.
- Lệnh đọc Cloud Run hoạt động trên **shop-prod-001**, không phải project chứa pool.
- Nếu không đủ quyền IAM, lỗi **PERMISSION_DENIED** sẽ xuất hiện ở API đích dù bước auth đã thành công.
- Thử chạy trên branch khác **main** trong môi trường kiểm thử: attribute condition dự kiến phải từ chối.
- Thử dùng một repository không nằm trong điều kiện cho phép: token phải không được chấp nhận.
- Kiểm tra audit log liên quan trong Google Cloud và lịch sử job của GitHub, không ghi nguyên token ra log.

Sau khi xác minh, nhóm có thể bổ sung bước deploy với quyền hạn và cơ chế phê duyệt riêng. Tránh lấy kết quả từ một lệnh chỉ đọc làm bằng chứng rằng workflow đã có đủ quyền và an toàn để triển khai production.

## 7. Dùng WIF với AWS, Azure, GitLab và hệ thống tự quản

WIF không chỉ dành cho GitHub Actions. Nguyên lý chung vẫn là **IdP → bằng chứng ngắn hạn → STS → quyền IAM**; khác nhau chủ yếu ở loại bằng chứng, nơi lấy token và cách kiểm chứng thuộc tính.

| Nguồn workload | Danh tính nguồn | Hướng triển khai |
|---|---|---|
| **AWS EC2 / workload AWS** | AWS identity hoặc OIDC token do AWS phát hành theo cơ chế được hỗ trợ | Provider AWS hoặc OIDC, ràng buộc AWS account/role và quyền Google Cloud |
| **Azure VM / hệ thống dùng Microsoft Entra ID** | Azure managed identity hoặc token ứng dụng Entra | Provider Azure/OIDC, giới hạn tenant, application hoặc object ID |
| **GitLab CI/CD** | GitLab OIDC ID token chứa project ID, namespace ID, ref/environment | Provider OIDC; giới hạn namespace/project/ref |
| **Azure DevOps** | OIDC token của service connection | Provider OIDC; ràng buộc đúng service connection/application |
| **Kubernetes bên ngoài GKE** | ServiceAccount token qua OIDC issuer của cluster | Provider OIDC; phân quyền theo cluster, namespace và ServiceAccount |
| **On-premises IdP** | OIDC token, SAML assertion hoặc cơ chế được hỗ trợ | Xác minh issuer, public keys/certificate, subject, audience và phạm vi tin cậy |

### 7.1. AWS và Azure

Với AWS hoặc Azure, quản trị viên tạo pool/provider theo hướng dẫn của nhà cung cấp, sau đó cấu hình file **external account credentials** cho workload. Đây là file chỉ dẫn thư viện/CLI **lấy credential của nền tảng nguồn** và thực hiện token exchange; nó **không phải JSON private key** của Google Cloud.

Ví dụ file cấu hình được tạo cho workload trên **AWS EC2** có IMDSv2 (đường dẫn, pool, account và service account là ví dụ):

~~~bash
gcloud iam workload-identity-pools create-cred-config \
  projects/123456789012/locations/global/workloadIdentityPools/aws-prod/providers/aws-ec2 \
  --service-account=reader@shop-prod-001.iam.gserviceaccount.com \
  --aws \
  --enable-imdsv2 \
  --output-file=/opt/app/google-wif.json
~~~

Lệnh này **chỉ tạo file cấu hình** sau khi pool/provider và IAM đã được chuẩn bị. Nó không tự tạo IAM role, không cấp quyền Google Cloud và không phát hành một Google service account key. Khi chạy trong workload AWS thật, thư viện cần truy cập thông tin danh tính AWS hợp lệ để thực hiện trao đổi.

Với Azure, CLI hỗ trợ chế độ **--azure** và thông số **--app-id-uri** tương ứng với ứng dụng được cấu hình. Phải kiểm tra managed identity, audience và tenant thay vì sao chép máy móc cài đặt AWS.

### 7.2. OIDC token lấy từ file hoặc endpoint tự quản

Với một IdP có thể phát hành OIDC JWT ngắn hạn cho workload, có thể tạo credential configuration trỏ đến **file token** hoặc **endpoint** nội bộ đã kiểm soát:

~~~bash
# Ví dụ: hệ thống ngoài GCP đã có OIDC token luân phiên tại đường dẫn này
gcloud iam workload-identity-pools create-cred-config \
  projects/123456789012/locations/global/workloadIdentityPools/onprem-prod/providers/onprem-oidc \
  --service-account=reader@shop-prod-001.iam.gserviceaccount.com \
  --credential-source-file=/var/run/workload/tokens/oidc.jwt \
  --output-file=/opt/app/google-wif.json
~~~

**Điều kiện tiên quyết:** file chứa subject token đang còn hiệu lực, được làm mới trước khi hết hạn, chỉ tiến trình thích hợp đọc được; token phải có issuer/audience/claims đúng với provider. Một file cũ chứa JWT hết hạn sẽ khiến token exchange thất bại.

Khi ứng dụng Java dùng thư viện Google Cloud được hỗ trợ, có thể cấu hình:

~~~bash
# Linux/macOS
export GOOGLE_APPLICATION_CREDENTIALS=/opt/app/google-wif.json
~~~

~~~powershell
# Windows PowerShell, nếu dùng một file cấu hình phù hợp với môi trường
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\app\google-wif.json"
~~~

File **external account credentials** không chứa private key Google Cloud và thường không phải bí mật theo nghĩa service account key. Tuy vậy, **nguồn token, file cấu hình và các đường dẫn executable/URL do nó tham chiếu vẫn phải được tin cậy**. Không dùng cấu hình từ nguồn không kiểm chứng, không để một workload khác có thể thay đổi nơi lấy credential và không in token thô ra log.

### 7.3. Kubernetes ngoài GKE

Ở Kubernetes bên ngoài GKE, **Kubernetes ServiceAccount** có thể có projected token với audience dành cho một provider tin cậy. Google Cloud cần xác minh OIDC issuer/JWKS của cluster, ánh xạ subject ổn định và giới hạn theo namespace/ServiceAccount.

Đừng nhầm:

- **Kubernetes ServiceAccount (KSA)** là định danh của workload trong cluster.
- **Google Cloud IAM service account** là định danh IAM của Google Cloud, dùng khi chọn impersonation.
- **Workload Identity Federation for GKE** là phương án riêng cho workload chạy trong GKE; ví dụ này áp dụng cho cluster nằm **ngoài** GKE.

Nếu cluster bị xâm nhập hoặc token bị cấp quá rộng, WIF không thể thay thế các biện pháp bảo vệ Kubernetes như RBAC, pod security, quản lý secret, network policy và bảo vệ issuer.

## 8. Ứng dụng Java/Spring và Google Cloud Client Libraries

Một ứng dụng Java chạy trên AWS hoặc on-premises thường không cần tự viết HTTP request đến STS. **Google Auth Library** và các **Google Cloud Client Libraries** hỗ trợ external account credentials có thể thực hiện việc đọc credential source, token exchange và refresh.

Ví dụ khởi tạo Cloud Storage client bằng cơ chế **Application Default Credentials (ADC)**:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public final class StorageClientFactory {
    private StorageClientFactory() {}

    public static Storage create() {
        // ADC sẽ đọc GOOGLE_APPLICATION_CREDENTIALS trong môi trường chạy.
        // File bên ngoài GCP có thể là external-account configuration cho WIF.
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Yêu cầu triển khai:

1. Dùng phiên bản thư viện Java hỗ trợ external account credentials phù hợp với nguồn token.
2. Đặt **GOOGLE_APPLICATION_CREDENTIALS** đến file cấu hình WIF hợp lệ; ứng dụng cần có quyền đọc file và nguồn token tương ứng.
3. Đảm bảo IdP phát hành token đúng audience/issuer và có cơ chế refresh khi token hết hạn.
4. Phân quyền IAM trên **bucket hoặc tài nguyên cụ thể** cho federated principal hoặc service account được impersonate.
5. Xác định project, bucket, dataset hoặc API đích trong cấu hình ứng dụng; credential **không thay thế cấu hình tài nguyên**.
6. Ghi log lỗi và latency đủ để chẩn đoán, nhưng không ghi access token, JWT hoặc thông tin nhạy cảm.

Một kiểm thử tốt có cả **positive case** (đúng danh tính, đọc được tài nguyên cho phép) và **negative case** (sai subject, sai môi trường hoặc truy cập tài nguyên ngoài phạm vi phải bị từ chối).

## 9. Vận hành an toàn: bảo mật, độ tin cậy và chi phí

### 9.1. Rủi ro thường gặp

| Rủi ro | Tác động | Kiểm soát đề xuất |
|---|---|---|
| Provider nhận toàn bộ token từ issuer chung | Job/tổ chức khác có thể được chấp nhận nếu IAM quá rộng | Attribute condition theo ID tổ chức/repository/workload |
| Cho phép audience tùy tiện | Token được phát hành cho mục đích khác có thể bị lạm dụng | Dùng audience dành riêng cho WIF provider |
| PrincipalSet quá rộng | Nhiều workload có quyền vượt nhu cầu | Bind theo subject/attribute cụ thể; tách pool khi cần |
| Service account có role Owner/Editor rộng | Tác động lớn nếu pipeline bị chiếm | Least privilege, role/resource phù hợp |
| Dùng cùng service account cho dev và prod | Dev có thể ảnh hưởng prod | Tách identity, provider và IAM policy |
| Token source nằm trong nơi nhiều tiến trình đọc được | Token có thể bị tái sử dụng khi chưa hết hạn | Quyền file/endpoint, token lifetime ngắn, giám sát |
| Phụ thuộc IdP không sẵn sàng | Workload không lấy được token mới | Theo dõi lỗi STS, token refresh, kế hoạch xử lý sự cố |
| Thay đổi tên repository mà không cập nhật policy | Đứt hoặc sai phạm vi trust | Ưu tiên ID số ổn định; review mapping và điều kiện |
| Quyền sửa workflow quá rộng | Kẻ tấn công có thể chạy job với identity được tin cậy | Protected branch, review, protected environment, kiểm soát actions |

### 9.2. Độ tin cậy của việc lấy token

WIF thay thế khóa tĩnh bằng chuỗi phụ thuộc động. Ở giờ cao điểm, nếu IdP, STS hoặc IAM Credentials API không trả token mới, chương trình có thể thất bại khi gọi API dù service đích đang bình thường.

Thiết kế cần:

- Thư viện xác thực phù hợp với cơ chế cache/refresh token.
- Đồng hồ hệ thống chính xác; token hết hạn hoặc chưa có hiệu lực có thể bị từ chối.
- Kiểm soát retry/backoff với lỗi tạm thời, không lặp vô hạn hoặc in token để debug.
- Alert trên lỗi xác thực, tỉ lệ 401/403, thời gian xác thực và ảnh hưởng tới SLO nghiệp vụ.
- Quy trình khi provider/issuer đổi JWKS, tenant, audience, branch hoặc claim.

### 9.3. IAM và khả năng truy vết

Đảm bảo nhóm có thể đối chiếu thông tin **job/repository/source principal** và tài nguyên bị truy cập. Theo dõi **Cloud Audit Logs** của dịch vụ liên quan theo chế độ log và chính sách áp dụng; trong impersonation, cần xem thông tin service account và dấu vết delegation nếu log cung cấp. Nhật ký mặc định khác nhau giữa các loại hoạt động, vì vậy phải kiểm tra log đã bật và retention đủ cho nhu cầu điều tra.

### 9.4. Kiểm soát chi phí

WIF giúp quản lý danh tính, **không đặt ngân sách hoặc quota** cho tài nguyên. Một workflow được phép triển khai vẫn có thể làm tăng chi phí Compute Engine, Cloud Run, GKE, Cloud Storage hoặc dữ liệu. Kết hợp IAM tối thiểu với kiểm thử pipeline, ngân sách cảnh báo, quota và theo dõi sử dụng. Đừng đồng nhất “đăng nhập an toàn” với “thay đổi được phê duyệt” hoặc “chi phí đã được kiểm soát”.

## 10. Chẩn đoán lỗi phổ biến

Lỗi của WIF thường xảy ra tại **ba lớp khác nhau**: nhận token bên ngoài, token exchange qua STS, hoặc cấp quyền IAM tới tài nguyên. Xác định lớp trước khi sửa cấu hình.

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Job không lấy được GitHub OIDC token | Thiếu **id-token: write**, runner/action không hỗ trợ, workflow bị hạn chế | Kiểm tra workflow permissions và log action |
| **invalid_grant**, lỗi issuer hoặc chữ ký | Token không do IdP được cấu hình phát hành, hết hạn, JWKS/issuer sai | Xác minh issuer, exp/iat, JWKS và nguồn token |
| **Audience mismatch** | Token hướng đến audience khác với provider | Cấu hình đúng audience, không bỏ kiểm tra để xử lý tạm |
| **Attribute condition rejected** | Owner ID, repo ID, ref, namespace hoặc claim khác không khớp | Kiểm tra claim thực tế an toàn, sửa mapping/condition qua review |
| **Cannot find pool/provider** | Dùng sai project number, location, pool/provider ID hoặc chưa lan truyền | Đọc lại resource name và mô tả pool/provider |
| Impersonation trả **PERMISSION_DENIED** | Thiếu **roles/iam.workloadIdentityUser** hoặc principalSet sai | Rà soát IAM policy trên service account, không cấp quyền dự án quá rộng |
| Đã lấy token nhưng Cloud Run/Storage trả **403** | Danh tính đích thiếu role trên tài nguyên hoặc policy khác chặn | Kiểm tra API đích, IAM role, project và điều kiện IAM |
| Java không lấy được credentials | Sai **GOOGLE_APPLICATION_CREDENTIALS**, thư viện cũ, không đọc được token source | Kiểm tra đường dẫn, phiên bản thư viện, môi trường chạy |
| Chạy vài phút rồi lỗi | Subject token không được refresh, đồng hồ sai, job dài hơn vòng đời token | Tự động làm mới token nguồn, kiểm tra clock và retry |
| Một môi trường có quyền cao hơn dự kiến | Dev/prod dùng cùng account hoặc principalSet quá rộng | Tách provider, service account, resource policy; rà soát IAM |
| Xác thực GitHub thành công nhưng deploy thất bại | Quyền đọc khác quyền deploy; thiếu **actAs** trên runtime SA hoặc quyền Artifact Registry | Thiết kế đúng role cho từng bước và tài nguyên |

### Quy trình điều tra gợi ý

1. **Kiểm tra nguồn:** workload đang chạy ở đâu, IdP nào phát token, audience/issuer/subject là gì?
2. **Kiểm tra cấu hình WIF:** project number, pool, provider, mapping, condition, loại token và thời hạn.
3. **Kiểm tra nhánh phân quyền:** direct principal hay impersonation? IAM binding thuộc resource hay service account nào?
4. **Kiểm tra API đích:** tài nguyên, project, region, IAM role, các policy có điều kiện và API đã bật.
5. **Xác minh âm tính:** job/repository không được phép phải nhận lỗi; không chỉ kiểm tra đường đi thành công.
6. **Kiểm tra sự lan truyền cấu hình:** quyền IAM và provider mới tạo đôi khi cần thời gian để có hiệu lực.

Không khắc phục lỗi bằng cách thêm role **Owner/Editor** hoặc bỏ mọi attribute condition để “chạy cho được”. Những thay đổi đó có thể tạo một quan hệ tin cậy rộng ngoài ý muốn.

## 11. Tình huống tổng hợp: pipeline triển khai Cloud Run từ GitHub

Doanh nghiệp **An Bình** có ba project:

- **shop-dev-001**: nhóm phát triển kiểm thử nhanh.
- **shop-stg-001**: thử nghiệm tích hợp Cloud Run và Cloud SQL.
- **shop-prod-001**: dịch vụ bán hàng thực và dữ liệu sản xuất.

Code được lưu trong GitHub; build runner ở ngoài Google Cloud. Trước đây, nhóm dùng một service account key chung có quyền deploy lên cả staging và production.

### 11.1. Thiết kế mục tiêu

| Thành phần | Dev / staging | Production |
|---|---|---|
| Nguồn tin cậy | Repo ID xác định, nhánh phát triển hoặc workflow test phù hợp | Repo ID xác định, nhánh main và environment được bảo vệ |
| Pool/provider | Tách theo ranh giới rủi ro hoặc provider riêng có condition | Provider production được giới hạn rõ ràng |
| Danh tính Google Cloud | service account deploy-stg quyền tối thiểu | service account deploy-prod quyền tối thiểu |
| Quyền tài nguyên | Deploy đến shop-stg-001 | Chỉ tài nguyên được phép trong shop-prod-001 |
| Bảo vệ pipeline | Review và kiểm thử tự động | Phê duyệt môi trường, protected branch, review thay đổi |
| Kiểm chứng | Build/test, thử quyền và từ chối truy cập ngoài scope | Kiểm tra release artifact, canary/rollback, audit log |

**Tác dụng:** sự cố trong job staging khó lan sang production hơn vì có ranh giới danh tính, điều kiện và IAM riêng. Việc không lưu JSON private key giảm nguy cơ lộ bí mật tồn tại lâu; tuy nhiên nguồn mã, workflow và quyền sửa workflow vẫn phải được bảo vệ.

### 11.2. Kịch bản kiểm thử bắt buộc

| Kiểm thử | Kỳ vọng |
|---|---|
| Workflow hợp lệ trên main, repo đã đăng ký | Token exchange thành công; chỉ thao tác trong phạm vi IAM được cấp |
| Fork hoặc repository khác cố dùng provider production | Bị từ chối ở attribute condition hoặc không có quyền IAM |
| Workflow từ branch không được phép | Bị từ chối theo điều kiện ref |
| Token source hết hạn | STS từ chối; hệ thống phải làm mới token |
| Service account chưa có quyền resource | Auth có thể thành công nhưng thao tác API bị 403 |
| Service account có quyền staging thử truy cập production | Bị từ chối |
| Người dùng thay đổi provider/role trái quy trình | Có kiểm soát quyền quản trị và dấu vết thay đổi |

### 11.3. Tiêu chí đưa production

Chỉ triển khai khi có bằng chứng rằng cấu hình trust đúng, IAM tối thiểu, các trường hợp bị cấm thật sự bị từ chối, workflow được bảo vệ và cơ chế giám sát/khôi phục đáp ứng yêu cầu dịch vụ. Sau triển khai, định kỳ rà soát các repository, pool, provider và service account không còn được sử dụng để giảm bề mặt tấn công.

## 12. Bài tập thực hành

**Tình huống:** một nhóm có hệ thống Java chạy trên AWS EC2; đồng thời dùng GitHub Actions build và phát hành lên Cloud Run. Java chỉ cần đọc bucket chứa ảnh sản phẩm; pipeline cần đọc trạng thái Cloud Run và phát hành phiên bản mới sau khi có phê duyệt.

1. Vẽ hai luồng xác thực riêng cho **Java trên AWS** và **GitHub Actions**, nêu IdP, pool/provider và IAM principal.
2. Với Java đọc Cloud Storage, phân tích có nên cấp **direct resource access** hay dùng service account impersonation. Nêu lý do dựa trên hỗ trợ của API và yêu cầu kiểm toán.
3. Đề xuất mapping/condition cho GitHub để giới hạn **repo ID**, **owner ID** và **branch main**. Giải thích vì sao chỉ kiểm tra issuer GitHub là không đủ.
4. Tách quyền service account của pipeline khỏi quyền ứng dụng Java. Nhóm quyền nào chỉ cần đọc object, nhóm quyền nào có thể deploy?
5. Mô tả kiểm thử âm tính: repository không được phép, token quá hạn, dùng nhầm audience và service account thiếu IAM role.
6. Khi pipeline báo **403** sau bước auth thành công, hãy xác định cần kiểm tra lớp nào trước khi thay đổi cấu hình.
7. Liệt kê những bằng chứng về logging, bảo vệ workflow, quản lý token và người chịu trách nhiệm cần có trước production.

### Gợi ý đánh giá kết quả

- Câu trả lời nêu được **hai lớp riêng**: IdP/provider quyết định ai được federation; IAM trên tài nguyên hoặc service account quyết định được làm gì.
- Không dùng JSON private key cho workflow nếu WIF đáp ứng yêu cầu.
- Không gán role rộng cho tất cả danh tính trong pool hoặc cho cả repository khi chỉ một workflow cần quyền.
- Chỉ rõ **project number** trong principal URI và **project ID** của tài nguyên đích; không đánh đồng hai giá trị.
- Giải thích lỗi theo **nguồn token → STS → impersonation/IAM → API tài nguyên** và có phương án thử trường hợp bị từ chối.

## 13. Ghi nhớ và tài liệu tham khảo

**Năm ý chính:**

1. **WIF** cho phép workload bên ngoài Google Cloud trao đổi danh tính tại nơi chạy lấy token Google Cloud ngắn hạn, giảm nhu cầu giữ service account key.
2. **Pool và provider** định nghĩa nguồn tin cậy; **issuer, audience, claims, mapping và condition** quyết định token nào được chấp nhận.
3. **Direct resource access** và **service account impersonation** là hai hướng cấp quyền hợp lệ; chọn theo API hỗ trợ và yêu cầu quản trị.
4. **IAM theo nguyên tắc quyền tối thiểu** luôn bắt buộc: token exchange thành công không tự cho phép deploy hoặc đọc dữ liệu.
5. Bảo mật WIF phụ thuộc cả **IdP, pipeline, policy, refresh token, logging và vận hành**; kiểm thử âm tính quan trọng ngang kiểm thử thành công.

**Nguồn tham khảo chính thức:**

1. [Workload Identity Federation — Google Cloud IAM](https://docs.cloud.google.com/iam/docs/workload-identity-federation) — tổng quan, đối tượng sử dụng, direct access và impersonation.
2. [Configure Workload Identity Federation with deployment pipelines](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines) — GitHub Actions, GitLab, Azure DevOps và HCP Terraform.
3. [Best practices for using Workload Identity Federation](https://docs.cloud.google.com/iam/docs/best-practices-for-using-workload-identity-federation) — issuer, audience, attribute conditions và ranh giới tin cậy.
4. [Configure Workload Identity Federation with AWS or Azure VMs](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-clouds) — identity từ AWS/Azure và credential configuration.
5. [Configure Workload Identity Federation with other identity providers](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-providers) — OIDC/SAML, file và endpoint token source.
6. [Configure Workload Identity Federation with Kubernetes](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-kubernetes) — workload ở cluster Kubernetes ngoài GKE.
7. [gcloud iam workload-identity-pools create-cred-config](https://docs.cloud.google.com/sdk/gcloud/reference/iam/workload-identity-pools/create-cred-config) — cú pháp tạo file external account credentials.
8. [google-github-actions/auth — GitHub](https://github.com/google-github-actions/auth) — action xác thực GitHub và các ví dụ workflow.
