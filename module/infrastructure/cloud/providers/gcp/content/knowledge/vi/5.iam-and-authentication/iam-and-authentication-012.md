# Kiểm soát và thay thế service account keys

Trong Google Cloud, một ứng dụng chạy trên Compute Engine, GKE, Cloud Run hay hệ thống CI/CD có thể cần gọi Cloud Storage, Pub/Sub, Cloud SQL hoặc API quản trị. Ứng dụng phải chứng minh **danh tính** của mình, còn IAM quyết định danh tính đó có quyền thực hiện hành động hay không. Một cách từng được dùng rộng rãi là tải **service account key dạng JSON** xuống máy rồi cấp cho ứng dụng. Tuy tiện lợi, cách này tạo ra bí mật dài hạn mà nếu bị lộ có thể bị sử dụng từ bên ngoài môi trường kiểm soát của doanh nghiệp.

Bài học thuộc chương **IAM và xác thực** trong mô-đun `CLOUD_PROVIDERS_GCP`. Trong quá trình học tổ chức project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu, người học cần biết khi nào một workload phải sử dụng danh tính, cách bảo vệ tài nguyên, triển khai tự động an toàn và kiểm soát rủi ro về độ tin cậy cũng như chi phí. Trọng tâm bài này là **hạn chế tạo key mới, kiểm kê và xử lý key đang tồn tại, chuyển ứng dụng sang phương thức xác thực không cần private key**.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **service account**, **service account key** và **access token**; hiểu vì sao key không chứa sẵn vai trò IAM.
2. Nhận diện rủi ro khi private key nằm trong repository, container image, máy phát triển hoặc CI/CD secret.
3. Kiểm kê user-managed keys, đọc trạng thái và xác định những workload phụ thuộc vào mỗi key.
4. Thiết kế phương án thay key bằng **attached service account**, **Application Default Credentials (ADC)**, **Workload Identity Federation (WIF)** hoặc **service account impersonation**.
5. Hiểu cách Organization Policy hạn chế tạo và tải lên key mới.
6. Thực hiện kế hoạch chuyển đổi có kiểm chứng: cấu hình danh tính mới, thử quyền, đổi workload, vô hiệu hóa key cũ, theo dõi rồi mới xóa.
7. Xử lý sự cố lộ key mà không nhầm thao tác tắt key với thu hồi mọi token đã phát hành.

## 1. Service account, key và token khác nhau như thế nào?

**Service account** là danh tính dành cho workload, automation hoặc ứng dụng. Nó được tạo trong một Google Cloud project và có email định danh dạng:

~~~text
orders-api@atlas-commerce-dev.iam.gserviceaccount.com
~~~

Email trên chỉ là ví dụ. Bạn có thể cấp cho service account những vai trò cần thiết đối với một project, bucket, topic hoặc tài nguyên phù hợp. Ví dụ, dịch vụ chỉ đọc object có thể được cấp `roles/storage.objectViewer` ở phạm vi bucket cần truy cập.

**Service account key** là một cặp khóa mật mã để ứng dụng chứng minh nó được phép đại diện service account. Với **user-managed key**, người quản trị/ứng dụng có quyền có thể tạo hoặc tải lên cặp khóa theo cơ chế được hỗ trợ; phần **private key** phải được bảo vệ đặc biệt. Google Cloud thường chỉ lưu phần public key của user-managed key và không thể cho bạn tải lại private key đã tạo trước đó.

**Access token** là credential có thời hạn, được dùng trong lời gọi API. Ứng dụng có thể dùng private key để tạo bằng chứng và xin token đại diện service account; hoặc nhận token bằng các cơ chế không cần tải private key xuống ứng dụng.

~~~mermaid
flowchart LR
    A["Service account<br/>Danh tính workload"] --> B["IAM role/binding<br/>Quyền hiệu lực"]
    C["User-managed private key<br/>Bí mật dài hạn"] --> D["Chứng minh quyền đại diện SA"]
    E["Attached identity / Federation / Impersonation"] --> D
    D --> F["Access token ngắn hạn"]
    F --> G["Lời gọi Google Cloud API"]
    B --> G
~~~

> **Phân biệt:** Một key không “mang” vai trò IAM. Nếu service account đột ngột được cấp thêm quyền, người sở hữu private key cũ có thể được hưởng khả năng truy cập rộng hơn thông qua danh tính đó. Ngược lại, xóa vai trò IAM làm giảm quyền của danh tính, nhưng không tự làm key hết hiệu lực.

### 1.1. Key do Google quản lý và key do người dùng quản lý

| Loại | Ai quản lý private key? | Điều cần làm |
| --- | --- | --- |
| **Google-managed key** | Google quản lý vòng đời/khóa nội bộ cho các cơ chế xác thực thích hợp | Thông thường ứng dụng không cần tải, xoay vòng hay lưu private key |
| **User-managed key** | Người tạo/vận hành chịu trách nhiệm bảo quản phần private key và vòng đời key | Hạn chế sử dụng; kiểm kê, thu hồi quyền khi không cần, vô hiệu hóa/xóa key |
| **Credential ngắn hạn qua impersonation/WIF/runtime** | Hạ tầng xác thực phát hành token có thời hạn từ danh tính đã được tin cậy | Quản lý trust, IAM, thời hạn token và audit thay vì quản lý private key JSON lâu dài |

Đừng nhầm **service account key** với **API key** (khóa nhận diện một số dự án/ứng dụng khi gọi API), khóa SSH của Compute Engine, khóa mã hóa Cloud KMS hay mật khẩu người dùng. Các loại credential này có mục đích và cơ chế bảo vệ khác nhau.

## 2. Vì sao user-managed service account keys là rủi ro lớn?

Một user-managed key JSON thường chứa thông tin như `client_email`, `private_key_id` và `private_key`. **Không cần biết mật khẩu của developer**: bất kỳ người nào lấy được private key còn hiệu lực và có thể gọi API phù hợp đều có cơ hội xác thực với danh tính service account đó.

~~~mermaid
flowchart TD
    A["Private key bị sao chép"] --> B["Người không được phép giữ bí mật"]
    B --> C["Tạo bằng chứng xác thực / xin token"]
    C --> D["Đại diện service account gọi API"]
    D --> E{"Quyền IAM hiệu lực?"}
    E -->|Có| F["Đọc/sửa/xóa tài nguyên trong phạm vi được cấp"]
    E -->|Không| G["API từ chối theo IAM/chính sách"]
~~~

Rủi ro điển hình:

- **Lộ credential:** file JSON bị commit vào Git, đưa vào CI logs, lưu trên ổ đĩa chia sẻ, gửi email/chat hoặc đóng gói trong Docker image.
- **Credential sống lâu:** key có thể tiếp tục được dùng sau khi một nhân viên nghỉ việc hoặc pipeline đã ngừng hoạt động, nếu chưa bị xử lý.
- **Khó quy trách nhiệm:** nhật ký có thể xác định service account hoặc dấu vết key, nhưng không nhất thiết xác định được *ai* cầm và sử dụng private key.
- **Leo thang đặc quyền:** người có khả năng tạo key cho một service account nhiều quyền có thể truy cập tài nguyên bằng danh tính đó, ngay cả khi quyền trực tiếp của họ vốn hẹp hơn.
- **Khó xoay vòng:** một key có thể được sao chép sang nhiều máy/ứng dụng mà không có inventory; việc thay đổi có thể làm gián đoạn workload không ai biết còn chạy.
- **Rủi ro cấu hình xác thực độc hại:** ngay cả credential configuration cho federation cũng phải được lấy từ nguồn tin cậy; không nên dùng file cấu hình không rõ nguồn gốc.

Ví dụ nhóm Commerce tạo key cho service account `orders-api` để deploy từ laptop. File `orders-dev-key.json` được commit nhầm vào repository. Dù file nhanh chóng bị xóa khỏi commit mới, lịch sử Git, bản clone, cache và các bản sao vẫn có thể giữ private key. **Gỡ file khỏi repository chưa đủ để vô hiệu hóa key**; cần xử lý key và đánh giá quyền đã có thể bị lạm dụng.

## 3. Nguyên tắc chọn cơ chế xác thực theo môi trường

Nên chọn nguồn danh tính theo nơi ứng dụng thực sự chạy, với mục tiêu không phải phân phối private key dài hạn.

| Môi trường | Phương án ưu tiên | Ghi chú triển khai |
| --- | --- | --- |
| **Cloud Run** | Gắn **runtime service account** thích hợp cho service hoặc job | Client library dùng ADC để lấy credential từ môi trường Google Cloud |
| **Compute Engine** | Gắn service account cho VM | Cần IAM thích hợp; lưu ý access scopes nếu có cấu hình giới hạn |
| **GKE** | **Workload Identity Federation for GKE** | Phân biệt Kubernetes ServiceAccount và IAM service account; cấu hình trust/permission theo workload |
| **Laptop developer** | User ADC, hoặc **service account impersonation** khi cần kiểm tra bằng danh tính workload | `gcloud auth application-default login`; không chép key production về máy |
| **GitHub/GitLab CI/CD, Kubernetes ngoài GCP, AWS/Azure/on-prem** | **Workload Identity Federation** với nhà cung cấp danh tính phù hợp | Đổi identity của nền tảng ngoài GCP lấy credential ngắn hạn theo trust đã cấu hình |
| **Dịch vụ phải đại diện một service account khác** | **Service account impersonation**, IAM Credentials API | Cấp quyền impersonate riêng, giới hạn principal được phép |
| **Hệ thống cũ không thể dùng cơ chế trên** | Ngoại lệ dùng user-managed key được phê duyệt | Xác định chủ sở hữu, lưu giữ an toàn, giới hạn IAM, xoay vòng và thời hạn xử lý |

**ADC là cơ chế tìm credential**, không đồng nghĩa phải có key file. Thứ tự tìm nguồn của ADC thường là: biến `GOOGLE_APPLICATION_CREDENTIALS`, tệp ADC do CLI tạo trong môi trường phát triển, rồi credential từ môi trường Google Cloud (metadata server hoặc tích hợp runtime thích hợp). Khi client library sử dụng ADC, mã nguồn có thể giữ nguyên dù nguồn credential thay đổi.

### 3.1. Ví dụ Java dùng Cloud Storage không cần key

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public class ReadMetadata {
    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: ReadMetadata <BUCKET_NAME> <OBJECT_NAME>");
        }

        // Không chỉ định đường dẫn JSON private key.
        // Google Cloud Java client library tự tìm ADC.
        Storage storage = StorageOptions.getDefaultInstance().getService();
        Blob object = storage.get(BlobId.of(args[0], args[1]));

        if (object == null) {
            System.out.println("Không tìm thấy object.");
            return;
        }
        System.out.println("Name: " + object.getName());
        System.out.println("Size: " + object.getSize());
    }
}
~~~

Chương trình cần dependency `com.google.cloud:google-cloud-storage` tương thích với dự án. Với workload chạy Cloud Run, service account runtime có thể được cấp `roles/storage.objectViewer` tại đúng bucket. Với laptop, developer dùng ADC local hoặc impersonation. Nếu nhận `403 PERMISSION_DENIED`, hãy kiểm tra danh tính thực tế và IAM, thay vì tạo private key mới như một cách “sửa quyền”.

## 4. Cloud Run và Compute Engine: dùng attached service account

Khi ứng dụng chạy trong dịch vụ Google Cloud hỗ trợ gắn service account, nên để runtime xin credential từ hạ tầng Google Cloud. Thư viện ứng dụng gọi ADC và nhận access token có thời hạn mà không cần phân phối file JSON.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng Cloud Run
    participant ADC as Google Auth Library (ADC)
    participant Meta as Runtime/Metadata Server
    participant API as Cloud Storage API
    App->>ADC: Tạo client và gọi API
    ADC->>Meta: Yêu cầu credential ngắn hạn
    Meta-->>ADC: Access token của runtime identity
    ADC->>API: Request mang token
    API-->>ADC: Kết quả theo IAM/chính sách
~~~

### 4.1. Chọn service account có quyền tối thiểu

Ví dụ ứng dụng `orders-api` chỉ cần đọc dữ liệu từ bucket `atlas-orders-dev`. Hãy:

1. Chọn service account riêng cho ứng dụng, ví dụ `orders-reader@atlas-commerce-dev.iam.gserviceaccount.com`.
2. Cấp quyền cần thiết tại bucket; tránh `roles/editor` hoặc `roles/owner` trên cả project chỉ để đọc object.
3. Cấu hình Cloud Run service sử dụng danh tính đó.
4. Triển khai chương trình dùng ADC; kiểm tra request thực tế.
5. Giám sát lỗi `401`/`403` và Cloud Audit Logs thích hợp.

Với Compute Engine, cần xem thêm các **access scopes** của VM nếu được áp dụng; IAM đầy đủ nhưng scope quá hẹp vẫn có thể khiến lời gọi API bị chặn. Một service account được gắn vào VM cũng có thể được nhiều tiến trình trên VM sử dụng tùy bề mặt kiểm soát nội bộ; tránh xem đó là danh tính riêng cho từng tiến trình.

### 4.2. Cạm bẫy khi chuyển khỏi key

Một workload có thể đang đặt:

~~~bash
export GOOGLE_APPLICATION_CREDENTIALS="/secrets/orders-service-account-key.json"
~~~

Nếu chỉ gắn service account vào Cloud Run hoặc VM mà **vẫn giữ biến môi trường trỏ tới key**, ADC tiếp tục ưu tiên file đó. Sau khi đã xác minh attached identity hợp lệ, loại bỏ đường dẫn và cơ chế mount key khỏi cấu hình runtime để client library thật sự dùng nguồn credential mới.

Không “kiểm tra” bằng cách in access token hoặc private key ra log.

## 5. GKE: Workload Identity Federation for GKE

GKE có hai loại service account dễ bị nhầm:

- **Kubernetes ServiceAccount (KSA)** là danh tính của workload trong Kubernetes.
- **IAM service account** là tài nguyên danh tính trong Google Cloud.

**Workload Identity Federation for GKE** giúp pod truy cập Google Cloud API mà không cần đặt private key JSON vào Kubernetes Secret. Tùy cấu hình và API đích, IAM có thể cấp quyền trực tiếp cho danh tính workload Kubernetes hoặc workload có thể sử dụng cơ chế đại diện một IAM service account được phép.

~~~mermaid
flowchart LR
    P["Pod chạy ứng dụng"] --> K["Kubernetes ServiceAccount"]
    K --> M["GKE metadata server / Federation"]
    M --> T["Credential ngắn hạn"]
    T --> A["Cloud Storage / Pub/Sub / API"]
    I["IAM bindings theo principal"] --> A
~~~

Công việc triển khai bao gồm:

1. Xác minh chế độ GKE và Workload Identity Federation đã được bật/cấu hình ở cluster và node pool khi cần.
2. Tạo KSA riêng cho ứng dụng, không dùng danh tính mặc định của mọi pod khi cần phân quyền khác nhau.
3. Thiết lập IAM bindings ở phạm vi tài nguyên thích hợp cho workload principal hoặc cơ chế impersonation.
4. Chạy pod bằng KSA đó, bỏ cơ chế mount user-managed key nếu trước đây có.
5. Thử lời gọi thực tế và xem lỗi/xác thực ở workload.

**Bật federation không tự cấp quyền IAM.** Nếu thiếu binding phù hợp, việc lấy được danh tính workload vẫn có thể dẫn tới `403`. Với các phiên bản/cấu hình GKE khác nhau, cách bật và ánh xạ cần làm theo hướng dẫn phù hợp với cluster.

## 6. Ứng dụng ngoài Google Cloud: Workload Identity Federation

Một pipeline CI/CD trên GitHub, GitLab hoặc workload chạy ở AWS, Azure hay trung tâm dữ liệu có thể có **danh tính của nền tảng hiện tại**. Thay vì tạo một key JSON cho Google Cloud rồi lưu trong CI secrets, bạn có thể tạo **Workload Identity Pool**, cấu hình **Identity Provider** và điều kiện tin cậy cho nguồn danh tính bên ngoài.

Một mô hình đơn giản:

~~~mermaid
sequenceDiagram
    participant CI as Pipeline CI/CD
    participant IdP as Identity Provider bên ngoài
    participant STS as Google Cloud STS
    participant IAM as IAM / Service Account
    participant API as Google Cloud API
    CI->>IdP: Nhận token danh tính workload
    IdP-->>CI: OIDC/SAML assertion phù hợp
    CI->>STS: Đổi token qua federation
    STS-->>CI: Federated token ngắn hạn
    CI->>IAM: Dùng quyền trực tiếp hoặc impersonation (nếu cấu hình)
    IAM-->>CI: Credential thích hợp
    CI->>API: Truy cập tài nguyên theo IAM
~~~

**Hai cách cấp quyền thường gặp:**

- **Direct resource access:** cấp IAM role trực tiếp cho federated principal nếu API/tài nguyên đích hỗ trợ.
- **Service account impersonation:** cho federated principal quyền phù hợp để đại diện một service account, rồi dùng quyền IAM của service account đó để truy cập API.

Federation không tự an toàn nếu trust cấu hình quá rộng. Ví dụ, thay vì tin mọi pipeline trong một nhà cung cấp CI, nên giới hạn **repository, branch/environment, issuer, audience, attributes** và các ràng buộc hỗ trợ. Danh tính ngoài GCP được chấp nhận phải là danh tính do hệ thống tin cậy cấp, không phải dữ liệu người dùng tùy ý có thể giả mạo.

Một **credential configuration file** của WIF có thể được ADC đọc qua `GOOGLE_APPLICATION_CREDENTIALS`; đây là cấu hình dùng để lấy token ngắn hạn từ nguồn danh tính bên ngoài, khác với một service account private key JSON. Tuy nhiên, credential configuration phải được nhận từ nguồn đáng tin cậy vì cấu hình độc hại có thể chuyển hướng quá trình lấy credential.

### 6.1. Khi nào nên chọn federation?

- Hệ thống ngoài GCP đã có IdP hỗ trợ và có thể phát hành token OIDC/SAML hoặc dạng được Google Cloud hỗ trợ.
- CI/CD cần deploy nhiều lần nhưng không muốn duy trì khóa dài hạn.
- Quản trị viên cần ràng buộc chính xác nguồn workload được phép tiếp cận project.
- Doanh nghiệp ưu tiên phiên xác thực ngắn hạn, audit và khả năng thu hồi quyền tập trung.

Cần có quyền tạo pool/provider, quyền IAM, cấu hình token exchange và tài liệu triển khai cho nhà cung cấp CI cụ thể. Không tạo WIF provider với trust rộng chỉ để làm cho pipeline “chạy được”.

## 7. Laptop developer và service account impersonation

Trong môi trường phát triển, người dùng thường có thể tạo ADC bằng:

~~~bash
gcloud auth application-default login
~~~

Khi cần kiểm thử bằng quyền của một service account thay vì quyền cá nhân, có thể dùng service account impersonation với SDK tương thích:

~~~bash
gcloud auth application-default login \
  --impersonate-service-account=orders-reader@atlas-commerce-dev.iam.gserviceaccount.com
~~~

Đây là ví dụ; tài khoản developer phải có quyền impersonate service account, thường thông qua `roles/iam.serviceAccountTokenCreator` được cấp ở phạm vi phù hợp. IAM Credentials API và các điều kiện liên quan cần được thiết lập. Service account đích **vẫn phải có** quyền truy cập tài nguyên: có thể tạo token không có nghĩa được phép đọc mọi bucket.

Nếu chỉ muốn thao tác CLI bằng một service account, có thể cấu hình impersonation cho lệnh `gcloud`:

~~~bash
gcloud storage ls \
  --impersonate-service-account=orders-reader@atlas-commerce-dev.iam.gserviceaccount.com
~~~

Lệnh này không tự biến cấu hình ADC local của mọi ứng dụng thành impersonation. **CLI credentials và ADC credentials có thể khác nhau.** Kiểm tra đường dẫn tệp/biến môi trường đang được thư viện sử dụng thay vì suy đoán từ kết quả của CLI.

## 8. Kiểm kê service account keys đang tồn tại

Trước khi xóa key, cần biết nó thuộc service account nào, đang ở project nào, còn hiệu lực hay đã bị vô hiệu hóa, và những workload nào có thể phụ thuộc vào nó. Việc kiểm kê cũng giúp ưu tiên những service account có quyền quá rộng hoặc key đã tồn tại lâu.

### 8.1. Xem service accounts và user-managed keys bằng gcloud

Các lệnh sau **chỉ đọc**. Chạy với tài khoản có IAM permission cần thiết; thay tất cả giá trị ví dụ bằng project/email thật.

~~~bash
# Xem tài khoản CLI và project đang chọn
gcloud auth list
gcloud config get-value project

# Liệt kê service account trong một project
gcloud iam service-accounts list --project=atlas-commerce-dev

# Liệt kê user-managed keys của một service account cụ thể
gcloud iam service-accounts keys list \
  --iam-account=orders-reader@atlas-commerce-dev.iam.gserviceaccount.com \
  --managed-by=user \
  --project=atlas-commerce-dev
~~~

Kết quả thường có key ID và metadata như ngày tạo, hạn dùng hoặc trạng thái disabled khi được trả về. `--managed-by=user` giúp tập trung vào **user-managed keys**; danh sách mặc định có thể hiển thị cả những key do Google quản lý. Không xóa Google-managed keys như thể đó là private key do ứng dụng tự phát hành.

**Lưu ý:** thông tin key không cho biết file JSON đã được sao chép sang bao nhiêu nơi. Không thể khẳng định key không ai dùng chỉ vì không tìm thấy một file trong repository. Cần kết hợp khảo sát owner, pipeline, secret store, image, máy vận hành và thông tin sử dụng key nếu có.

### 8.2. Lập bảng kiểm kê vận hành

| Trường | Mẫu minh họa | Mục đích |
| --- | --- | --- |
| Project / service account | `atlas-commerce-dev / orders-reader@...` | Xác định danh tính và phạm vi |
| Key ID | ID lấy từ metadata, **không phải private key** | Xác định chính xác key cần thao tác |
| Trạng thái | Enabled / Disabled | Biết key có thể dùng để xác thực hay không |
| Thời điểm tạo / hạn dùng | Theo metadata thực tế | Phân loại key lâu năm hoặc sắp hết hạn |
| Workload phụ thuộc | Batch job cũ, CI pipeline | Tránh ngắt hệ thống khi chuyển đổi |
| IAM privilege | Quyền đọc bucket hay quyền rộng hơn | Ưu tiên rủi ro cao |
| Owner / kế hoạch thay thế | Nhóm Commerce / WIF | Ai chịu trách nhiệm chuyển đổi |
| Hạn hoàn tất | Theo kế hoạch nội bộ | Tránh key tồn tại vô thời hạn |

Các thay đổi IAM và trạng thái key là công việc nhạy cảm. Chỉ người có quyền được cấp mới nên thực hiện.

## 9. Kiểm soát việc tạo và tải lên key bằng Organization Policy

Google Cloud cung cấp **Organization Policy constraints** để giảm phát hành credential dài hạn:

- `iam.managed.disableServiceAccountKeyCreation`: managed constraint ngăn tạo mới user-managed service account keys khi áp dụng.
- `iam.managed.disableServiceAccountKeyUpload`: managed constraint ngăn tải public key ngoài vào service account.
- Các legacy constraints tương ứng: `iam.disableServiceAccountKeyCreation` và `iam.disableServiceAccountKeyUpload`, có thể xuất hiện trong cấu hình hiện hữu.

Theo tài liệu Google Cloud, những organization được tạo từ **ngày 03/05/2024** có các hạn chế legacy về key creation/upload được bật mặc định. Trên organization cũ hoặc môi trường đã tùy chỉnh, hãy kiểm tra **effective organization policy** thực tế; không giả định tất cả project luôn bị khóa giống nhau.

### 9.1. Vì sao phải chặn cả creation và upload?

Ngăn hệ thống tự tạo private key JSON mới là chưa đủ nếu người có quyền vẫn có thể **tự tạo cặp khóa bên ngoài rồi upload public key** để Google chấp nhận private key họ đang giữ. Hai ràng buộc xử lý hai đường tạo credential dài hạn khác nhau.

### 9.2. Phạm vi policy và ngoại lệ

Organization Policy có thể được cấu hình ở cấp organization, folder hoặc project theo cơ chế của từng constraint. Người quản trị nên:

1. Đánh giá hiện trạng key và các workload cần chuyển đổi.
2. Áp dụng policy tại cấp phù hợp để bảo vệ project trong tương lai.
3. Kiểm tra hiệu lực kế thừa và policy đang có trên parent/child.
4. Nếu hệ thống cũ chưa chuyển được, thiết kế **ngoại lệ hẹp, có thời hạn và người chịu trách nhiệm** theo cơ chế policy hỗ trợ.
5. Định kỳ kiểm tra những project còn ngoại lệ.

**Chặn tạo key mới không tự vô hiệu hóa các key đã tồn tại.** Phải kiểm kê và xử lý key cũ theo quy trình chuyển đổi. Organization Policy cũng không thay thế IAM: người có quyền quản trị policy, tạo key hay cấp vai trò cần được giới hạn theo trách nhiệm.

### 9.3. Không dùng vai trò quá rộng làm lối tắt

`roles/editor` hoặc `roles/owner` có thể cấp nhiều permission vượt nhu cầu ứng dụng. Hãy tách:

- Quyền vận hành workload (deploy Cloud Run, chạy GKE, đọc bucket).
- Quyền quản trị service account và cấp IAM.
- Quyền tạo/xóa service account keys.
- Quyền impersonate service account để xin token ngắn hạn.

Nhà phát triển được phép triển khai ứng dụng **không đương nhiên cần** quyền tạo private key của service account. Giới hạn quyền này làm giảm nguy cơ leo thang đặc quyền và rò rỉ bí mật.

## 10. Quy trình chuyển một workload khỏi service account key

Giả sử một GitHub Actions workflow đang deploy ứng dụng vào Cloud Run bằng secret chứa JSON key của service account `deploy-bot`. Mục tiêu là chuyển sang WIF, sau đó xóa key cũ mà không làm ngừng pipeline.

~~~mermaid
flowchart TD
    A["Inventory key, quyền IAM và nơi sử dụng"] --> B["Chọn phương án mới: WIF / attached identity / impersonation"]
    B --> C["Cấu hình trust, IAM và credential mới"]
    C --> D["Chạy thử trong môi trường kiểm soát"]
    D --> E{"Deploy và quyền tối thiểu đã đúng?"}
    E -->|Không| C
    E -->|Có| F["Chuyển workload sang danh tính mới"]
    F --> G["Quan sát các lần chạy và audit logs"]
    G --> H["Disable key cũ"]
    H --> I{"Có workload hợp lệ bị ảnh hưởng?"}
    I -->|Có| J["Khôi phục có kiểm soát, sửa cấu hình phụ thuộc"]
    J --> F
    I -->|Không| K["Delete key cũ, kiểm kê và đóng thay đổi"]
~~~

### Bước 1: Xác định phụ thuộc và phạm vi quyền

- Key ID, service account, project, người sở hữu và nơi đã triển khai.
- Permissions service account thật sự cần; loại bỏ vai trò quá rộng trước hoặc trong quá trình chuyển đổi theo kế hoạch.
- Mọi ứng dụng/pipeline sử dụng chung key; nếu không biết, phải điều tra trước khi disable.
- Các chính sách organization/folder/project có thể ảnh hưởng WIF hoặc impersonation.
- Kế hoạch kiểm thử, cửa sổ thay đổi và người quyết định hoàn tất.

### Bước 2: Chuẩn bị phương án thay thế

Với GitHub Actions, cấu hình identity provider có trust giới hạn cho đúng repository và workflow/environment; cấp quyền impersonation hoặc direct IAM cho danh tính đã được xác thực. Thay secret JSON bằng bước nhận federated credential được công cụ hỗ trợ. Mức quyền của danh tính triển khai phải đủ cho đúng dịch vụ/đích, nhưng không tự động có quyền quản trị toàn project.

Với Cloud Run, Compute Engine hoặc GKE, áp dụng cơ chế danh tính native/federation tương ứng. Khi chuyển đổi, bỏ `GOOGLE_APPLICATION_CREDENTIALS` nếu biến này còn trỏ đến file private key cũ.

### Bước 3: Kiểm thử trước khi cắt key cũ

- Chạy pipeline hoặc workload ở môi trường dev/staging.
- Thực hiện API call đại diện cho công việc thực tế.
- Kiểm tra quyền tối thiểu, thời gian cấp token, error code, khả năng làm mới credential.
- Xem logs và trace/audit phù hợp; không đưa token/private key vào log.
- Bảo đảm các job định kỳ, retry và rollback vẫn dùng cơ chế mới.

### Bước 4: Vô hiệu hóa key cũ trước khi xóa

**Disable key** ngăn key đó tiếp tục được dùng để xác thực tới Google APIs. Đây là bước **có thể khôi phục** trong quá trình kiểm chứng, khác với xóa vĩnh viễn.

~~~bash
# Chỉ thực hiện sau khi đã chuyển workload và có quyền được cấp.
gcloud iam service-accounts keys disable KEY_ID \
  --iam-account=deploy-bot@atlas-commerce-dev.iam.gserviceaccount.com \
  --project=atlas-commerce-dev
~~~

Sau khi disable, theo dõi đủ chu kỳ chạy của ứng dụng, đặc biệt job theo lịch hiếm chạy hoặc quy trình chỉ xuất hiện khi sự cố. Nếu phát hiện phụ thuộc hợp lệ chưa chuyển, điều tra và sửa trước khi quyết định tiếp.

### Bước 5: Xóa key sau khi xác nhận không còn phụ thuộc

~~~bash
# Thao tác xóa là vĩnh viễn: xác nhận chính xác KEY_ID và owner trước khi chạy.
gcloud iam service-accounts keys delete KEY_ID \
  --iam-account=deploy-bot@atlas-commerce-dev.iam.gserviceaccount.com \
  --project=atlas-commerce-dev
~~~

Key bị xóa **không thể được khôi phục**. Cần kiểm kê lại và loại bỏ những bản sao local, CI secrets, file backup hoặc cấu hình không còn dùng, nhưng việc xóa bản sao không thay thế thao tác vô hiệu hóa/xóa key ở Google Cloud.

### Bước 6: Hoàn thành kiểm soát

Cập nhật tài liệu và owner, rà soát IAM, xác nhận không còn job dùng private key, áp dụng chính sách ngăn tạo key không cần thiết và theo dõi sự cố xác thực sau chuyển đổi. Với workload thực tế, đừng coi một lần chạy thành công duy nhất là bằng chứng tất cả phụ thuộc đã chuyển xong.

## 11. Khi không thể bỏ key ngay: quản lý ngoại lệ an toàn

Một số hệ thống cũ không hỗ trợ ADC, WIF, token exchange hoặc impersonation phù hợp. Khi đã xác minh **không có phương án khả thi**, có thể cần một user-managed key trong thời gian chuyển đổi. Đây nên là ngoại lệ có phê duyệt.

Checklist tối thiểu:

1. **Lý do ngoại lệ rõ ràng:** hệ thống nào, môi trường nào, vì sao không dùng keyless authentication.
2. **Chủ sở hữu và hạn chót:** nhóm chịu trách nhiệm, ngày đánh giá lại, thời điểm dự kiến thay thế.
3. **Quyền IAM tối thiểu:** hạn chế tài nguyên và hành động; không dùng role rộng vì thuận tiện.
4. **Lưu giữ bảo mật:** tránh nhúng key vào source code, Git history, build artifact hoặc image. Kiểm soát quyền đọc, truy vết và bảo vệ nơi lưu.
5. **Tránh phân phối qua người dùng:** không gửi private key bằng email/chat, không copy thủ công giữa máy.
6. **Luân chuyển có kiểm thử:** tạo key thay thế theo quy trình phê duyệt, phân phối tới tất cả workload, thử, disable key cũ, theo dõi rồi delete.
7. **Phát hiện rò rỉ:** giám sát security findings, audit logs và thông tin sử dụng key; có quy trình xử lý khẩn cấp.
8. **Chính sách hạn chế tạo mới:** giữ ngoại lệ ở phạm vi hẹp, không nới lỏng toàn organization chỉ để phục vụ một ứng dụng.

### Vì sao “đặt key trong Secret Manager” không tự giải quyết bài toán?

Secret Manager có thể quản lý bí mật ứng dụng, nhưng để ứng dụng truy cập Secret Manager, nó **đã phải có một cơ chế xác thực**. Nếu runtime có identity hợp lệ để đọc Secret Manager, nhiều trường hợp runtime có thể dùng chính identity đó để gọi Google Cloud API mà không cần key. Vì vậy, không mặc định “đưa service account key vào Secret Manager” là phương án ưu tiên thay cho attached identity hoặc federation.

### Xoay vòng không đồng nghĩa đã loại bỏ rủi ro

Nếu chỉ đổi key A thành key B nhưng tiếp tục copy B vào repository hoặc nhiều máy, rủi ro vẫn còn. Xoay vòng chỉ là biện pháp giảm thời gian tiếp xúc; mục tiêu dài hạn là giảm hoặc loại bỏ user-managed key.

## 12. Nếu private key bị lộ thì xử lý thế nào?

Giả sử có cảnh báo về key `orders-reader` xuất hiện trong repository công khai. Đây là **sự cố credential**, không phải lỗi cấu hình đơn thuần.

### 12.1. Hành động khẩn cấp

1. Xác định chính xác **key ID**, service account, project và phạm vi quyền. Không sao chép private key vào hệ thống ticket/chat.
2. Theo quy trình ứng phó sự cố, **disable hoặc delete key** bị lộ để ngăn sử dụng tiếp; với sự cố đã xác nhận, ưu tiên giảm thời gian cửa sổ lạm dụng.
3. Xem IAM của service account và mọi tài nguyên có thể đã bị truy cập; thu hẹp quyền rủi ro khi thích hợp.
4. Điều tra Cloud Audit Logs, sự kiện tạo/xóa key, hoạt động API, thay đổi IAM, truy cập dữ liệu và tín hiệu bất thường theo khả năng ghi log.
5. Chuyển workload hợp lệ sang danh tính keyless; nếu chưa làm được, xử lý credential thay thế theo quy trình sự cố riêng và theo dõi sát.
6. Loại bỏ bản sao file ở repository, artifact, image và môi trường liên quan; đánh giá lịch sử Git và cache.
7. Ghi nhận thời điểm, ảnh hưởng, hành động, xác minh và biện pháp ngăn tái diễn.

**Điểm giới hạn quan trọng:** Disable/delete một key ngăn dùng key đó để xác thực mới, nhưng **không tự thu hồi ngay những short-lived credentials đã được phát hành dựa trên key**. Khi cần chặn token đã phát hành, Google Cloud hướng dẫn xem xét disable/delete **service account** đại diện token; hành động này có thể làm ngừng mọi workload hợp lệ sử dụng service account, vì vậy cần phối hợp xử lý sự cố với owner và đánh giá tác động.

### 12.2. Những giả định sai cần tránh

| Giả định | Thực tế cần nhớ |
| --- | --- |
| “Tôi đã xóa file JSON khỏi nhánh main là an toàn.” | Bản sao/private key có thể còn trong lịch sử Git, bản clone và artifact; phải xử lý key gốc. |
| “Tài khoản người tạo key đã nghỉ thì key hết quyền.” | Key còn hoạt động vẫn đại diện service account cho đến khi bị xử lý hoặc quyền service account thay đổi. |
| “Disable key thu hồi ngay mọi access token.” | Token ngắn hạn đã phát hành có thể còn hiệu lực trong thời hạn của chúng. |
| “Tạo key mới là cách sửa mọi lỗi 403.” | Lỗi 403 thường liên quan IAM/chính sách/quota; key mới không tự cấp quyền. |
| “Chặn tạo key bằng Organization Policy đã xóa key cũ.” | Policy chủ yếu ngăn hành động tạo/upload mới; phải xử lý key tồn tại riêng. |
| “Ai cũng có thể nhận ra người dùng key từ log.” | Dùng chung private key làm khó quy trách nhiệm cá nhân. |

## 13. Chẩn đoán lỗi khi chuyển sang cơ chế không dùng key

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `Could not load the default credentials` | Không có nguồn ADC hợp lệ hoặc biến môi trường đang trỏ sai | Kiểm tra thứ tự ADC, file cấu hình WIF, identity runtime |
| `401 UNAUTHENTICATED` | Token không hợp lệ, hết hạn, không refresh hoặc trust không phù hợp | Kiểm tra loại credential, issuer/audience, đồng hồ, cấu hình federation |
| `403 PERMISSION_DENIED` | Thiếu IAM hoặc có policy/deny chặn | Kiểm tra principal hiệu lực, roles, resource scope và policy |
| `iam.serviceAccounts.getAccessToken denied` | Principal không được quyền impersonate hoặc sai service account | Kiểm tra IAM binding trên service account và IAM Credentials API |
| CI/CD không nhận được federated token | Provider không chấp nhận claim hoặc trust quá hẹp/sai | Kiểm tra issuer, attribute mapping, condition, audience và quyền nền tảng CI |
| GKE pod lỗi 403 sau khi bỏ Kubernetes Secret | KSA/workload principal chưa có IAM thích hợp | Kiểm tra Workload Identity Federation và binding ở tài nguyên |
| Cloud Run vẫn dùng key cũ | `GOOGLE_APPLICATION_CREDENTIALS` hoặc mount key còn tồn tại | Bỏ override sau khi attached identity sẵn sàng |
| Ứng dụng dừng sau khi disable key | Còn dependency sử dụng key chưa được chuyển | Dùng kế hoạch khôi phục có kiểm soát, sửa cấu hình, chạy lại |
| Thấy system-managed keys trong danh sách | CLI trả nhiều loại key | Lọc `--managed-by=user` khi kiểm kê key do người dùng quản lý |

Một lỗi xác thực thường có nhiều lớp. Cách điều tra hiệu quả là tách **credential source → danh tính thực tế → quyền impersonation (nếu có) → IAM đích → chính sách dịch vụ và dự án**, thay vì tạo thêm một key để thử.

## 14. Tình huống tổng hợp: thay key trong hệ thống thương mại điện tử

Công ty Atlas vận hành:

- `orders-api` trên Cloud Run, cần đọc object từ Cloud Storage.
- `event-worker` trên GKE, cần nhận và xử lý Pub/Sub.
- Pipeline CI/CD ngoài Google Cloud, cần deploy một bản phát hành.
- Một batch job legacy chạy ngoài Google Cloud, hiện chỉ hỗ trợ file JSON service account key.

### 14.1. Thiết kế đề xuất

| Thành phần | Phương án | Quyền cần xét |
| --- | --- | --- |
| `orders-api` / Cloud Run | Attached runtime service account + ADC | Đọc bucket được chỉ định; IAM trên Cloud Run runtime |
| `event-worker` / GKE | Workload Identity Federation for GKE | Principal/KSA phù hợp được phép dùng Pub/Sub subscription |
| Pipeline CI/CD | WIF với identity từ nền tảng CI | Trust giới hạn theo repository/workflow; quyền deploy tối thiểu |
| Batch job legacy | Lộ trình chuyển sang WIF hoặc impersonation; ngoại lệ key có kiểm soát nếu cần | Quyền tối thiểu, inventory key, owner, hạn chuyển đổi |

### 14.2. Kế hoạch thực hiện theo giai đoạn

**Giai đoạn A — Khảo sát:** Liệt kê service accounts và user-managed keys, xác định quyền IAM, nơi lưu bản sao, owner và các hệ thống có thời điểm chạy khác nhau.

**Giai đoạn B — Chuyển workload hiện đại:** Gắn runtime service account cho Cloud Run; bật/cấu hình WIF cho GKE; thiết lập trust cho CI/CD. Dùng ADC trong client library và bỏ biến môi trường trỏ key.

**Giai đoạn C — Kiểm chứng:** Chạy thử dev/staging, theo dõi log, độ tin cậy, latency cấp token, khả năng refresh và các quyền theo nguyên tắc tối thiểu.

**Giai đoạn D — Thu hồi key:** Disable key cũ sau khi tất cả consumer đã chuyển; theo dõi những job theo lịch; xóa key khi xác minh không còn phụ thuộc.

**Giai đoạn E — Phòng tái diễn:** Bật các constraint hạn chế key creation/upload tại phạm vi phù hợp, đưa kiểm tra key vào quy trình bảo mật repository và CI/CD, kiểm kê định kỳ ngoại lệ đang tồn tại.

### 14.3. Tiêu chí hoàn thành

- Các workload hiện đại không cần private key JSON và vẫn truy cập API đúng quyền.
- Không còn file key trong repository, artifact hoặc image deploy mới.
- Những user-managed keys được thay thế đã disable rồi delete; danh sách kiểm kê được cập nhật.
- Batch job legacy có owner, rủi ro, thời hạn ngoại lệ và lộ trình loại bỏ key.
- Bản ghi vận hành đủ để biết **ai cấp quyền, workload nào được sử dụng và cách thu hồi truy cập**.
- Thay đổi không làm suy giảm chức năng, độ tin cậy hoặc khả năng quan sát của hệ thống.

## 15. Bài tập tự kiểm tra

**Câu 1.** Service account `etl-reader` chỉ có quyền đọc một bucket. Nếu JSON private key của nó bị lộ, người lấy được key có “tự động là Owner của project” không?

*Gợi ý:* Không. Người đó có thể xác thực với service account và sử dụng những quyền IAM hiệu lực của danh tính đó, không tự có mọi quyền. Dù vậy, lộ key vẫn nghiêm trọng vì có thể truy cập dữ liệu trong phạm vi quyền.

**Câu 2.** Pipeline GitHub Actions đang dùng JSON key lâu dài để triển khai Cloud Run. Phương án keyless nào phù hợp?

*Gợi ý:* Workload Identity Federation với trust giới hạn đúng identity của workflow, cấp quyền trực tiếp hoặc impersonate service account phù hợp; dùng credential ngắn hạn và kiểm tra chức năng deploy.

**Câu 3.** Cloud Run service đã gắn runtime service account mới nhưng code vẫn xác thực bằng key cũ. Vì sao?

*Gợi ý:* ADC có thể đang ưu tiên `GOOGLE_APPLICATION_CREDENTIALS` trỏ tới key JSON. Phải xác minh rồi gỡ cấu hình đó để ứng dụng dùng attached identity.

**Câu 4.** Sau khi bật policy chặn tạo key, nhóm có thể kết luận mọi key cũ đều bị vô hiệu hóa không?

*Gợi ý:* Không. Policy ngăn các thao tác tạo/upload theo ràng buộc được cấu hình; key cũ cần được kiểm kê và xử lý riêng.

**Câu 5.** Vì sao nên disable key và kiểm thử trước khi delete trong một đợt chuyển đổi có kế hoạch?

*Gợi ý:* Disable có thể khôi phục nếu phát hiện job phụ thuộc chưa chuyển, còn delete là vĩnh viễn. Với key đã bị lộ, đáp ứng sự cố có thể phải ưu tiên chặn nhanh hơn quy trình chuyển đổi thường lệ.

**Câu 6.** Một GKE pod đã chuyển sang Workload Identity Federation nhưng bị `403` khi gọi Pub/Sub. Có nên tạo key JSON cho pod không?

*Gợi ý:* Cần kiểm tra Kubernetes ServiceAccount, IAM principal, mapping/impersonation, quyền trên subscription và policy. Federation không tự cấp vai trò IAM.

**Câu 7.** Nếu đã disable một private key bị lộ, token ngắn hạn đã phát hành từ key có bị vô hiệu hóa ngay không?

*Gợi ý:* Không nhất thiết. Cần đánh giá thời hạn/token đã phát hành và yêu cầu ứng phó sự cố; disable service account có thể cần thiết trong tình huống đặc biệt nhưng ảnh hưởng workload hợp lệ.

**Câu 8.** Đội ứng dụng đưa service account key vào Secret Manager và cho Cloud Run đọc secret. Việc này có loại bỏ nhu cầu private key không?

*Gợi ý:* Chưa. Cloud Run đã cần một identity để đọc Secret Manager; trong nhiều trường hợp có thể dùng identity đó trực tiếp để gọi Google Cloud APIs, tránh phải dùng private key thêm một lần nữa.

## 16. Những điểm ghi nhớ

- **Service account là danh tính; private key là bí mật có thể dùng để đại diện danh tính đó.**
- **Không lưu user-managed key khi có lựa chọn xác thực không cần khóa dài hạn.**
- **Cloud Run/Compute Engine:** dùng attached service account; **GKE:** dùng Workload Identity Federation for GKE; **CI/CD ngoài Google Cloud:** dùng WIF; **laptop:** dùng ADC hoặc impersonation.
- **IAM tối thiểu và trust federation hẹp** quan trọng không kém việc bỏ key.
- **Organization Policy** hạn chế key creation/upload nhưng không tự xử lý key đã tồn tại.
- **Chuyển đổi theo quy trình:** inventory → thiết lập phương án mới → kiểm thử → chuyển workload → disable → theo dõi → delete.
- **Khi bị lộ:** xử lý key và xác minh các token đã phát hành; xóa file khỏi Git chưa đủ để thu hồi credential.
- **Quan sát vận hành:** kiểm tra 401/403, token refresh, audit logs và tác động tới ứng dụng trước khi đóng thay đổi.

Khi tiếp tục các phần triển khai GKE, Cloud Run, VPC, lưu trữ, cơ sở dữ liệu, CI/CD và chi phí của mô-đun GCP, hãy đặt câu hỏi: **“Workload nào đang xác thực, qua danh tính nào, vì sao cần quyền đó và có thể hoạt động mà không phải giữ private key dài hạn hay không?”** Đây là nền tảng để triển khai dịch vụ an toàn và vận hành ổn định.

## Tài liệu tham khảo chính thức

- [Best practices for managing service account keys — IAM](https://cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys)
- [Best practices for using service accounts securely](https://cloud.google.com/iam/docs/best-practices-service-accounts)
- [Create and delete service account keys](https://cloud.google.com/iam/docs/keys-create-delete)
- [Disable and enable service account keys](https://cloud.google.com/iam/docs/keys-disable-enable)
- [List and get service account keys](https://cloud.google.com/iam/docs/keys-list-get)
- [Service account key rotation](https://cloud.google.com/iam/docs/key-rotation)
- [Restrict service account usage with Organization Policy](https://cloud.google.com/organization-policy/restrict-service-accounts)
- [Service account impersonation](https://cloud.google.com/iam/docs/service-account-impersonation)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Workload Identity Federation for GKE](https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)

