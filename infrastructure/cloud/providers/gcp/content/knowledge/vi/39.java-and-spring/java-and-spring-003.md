# Xác thực Java bằng ADC trong máy cá nhân và runtime GCP

Một ứng dụng Java có thể chạy trên máy lập trình viên, trong Cloud Run, Google Kubernetes Engine (GKE), Compute Engine hoặc một hệ thống CI/CD. Mỗi môi trường có cách cung cấp danh tính khác nhau. Nếu ứng dụng nhúng đường dẫn khóa service account trực tiếp vào mã, việc chuyển môi trường trở nên khó quản lý và tăng nguy cơ lộ thông tin xác thực.

**Application Default Credentials (ADC)** là cơ chế mà các thư viện Google Cloud sử dụng để tự tìm danh tính phù hợp với môi trường đang chạy. Với ADC, ứng dụng có thể sử dụng cùng một đoạn Java để gọi Cloud Storage, Pub/Sub, Secret Manager hoặc các Google Cloud APIs khác; danh tính thực tế được cấu hình từ bên ngoài ứng dụng.

Bài học này hướng dẫn cách xác thực Java bằng ADC khi phát triển trên máy cá nhân và khi triển khai lên runtime GCP, đồng thời giải thích cách kết hợp IAM, service account, Workload Identity Federation và quản lý quota project để tránh các lỗi thường gặp.

## 1. ADC giải quyết vấn đề gì?

Trước khi gọi API Google Cloud, một client cần có thông tin xác thực (credentials). Thông tin này cho phép thư viện lấy OAuth 2.0 access token thích hợp và gửi token cùng request. Dịch vụ Google Cloud sau đó kiểm tra quyền IAM và các điều kiện liên quan.

Ví dụ, cùng một ứng dụng `orders-api` có thể:

- Đọc object từ Cloud Storage.
- Publish message lên Pub/Sub.
- Đọc một phiên bản secret từ Secret Manager.
- Gửi logs và metrics đến Cloud Logging và Cloud Monitoring.

Ứng dụng cần một danh tính được cấp quyền tương ứng. Trên máy cá nhân, danh tính có thể đến từ phiên đăng nhập phát triển hoặc impersonation của service account. Trên Cloud Run, Compute Engine và GKE, danh tính nên do nền tảng cung cấp cho workload.

ADC giúp tách biệt **mã ứng dụng**, **danh tính**, **quyền truy cập** và **môi trường chạy**.

| Thành phần | Vai trò |
|---|---|
| Java Google Cloud client library | Gọi API dịch vụ, tự xử lý token khi được cấu hình ADC |
| ADC | Tìm nguồn credentials từ môi trường |
| Google Auth Library for Java | Cung cấp các lớp credentials và quản lý refresh token |
| IAM | Quyết định principal được phép thực hiện thao tác nào |
| OAuth scope | Giới hạn phạm vi truy cập token khi dịch vụ dùng scope |
| Project/quota project | Xác định tài nguyên mục tiêu hoặc dự án dùng để tính quota/billing theo API |
| Service account | Danh tính cho ứng dụng và workload |
| Metadata server | Cung cấp thông tin xác thực ngắn hạn cho runtime GCP thích hợp |

**ADC không tự cấp quyền IAM.** Tìm được credential chỉ có nghĩa là ứng dụng có nguồn danh tính để xác thực. Nếu principal không có quyền trên tài nguyên đích, API vẫn có thể trả lỗi `PERMISSION_DENIED`.

## 2. Thứ tự tìm credentials của ADC

Đối với nhiều thư viện Google Cloud Java, ADC tìm nguồn credentials theo thứ tự ưu tiên chính sau:

1. Tệp được trỏ đến bởi biến môi trường `GOOGLE_APPLICATION_CREDENTIALS`.
2. Tệp ADC cục bộ do Google Cloud CLI tạo bằng lệnh `gcloud auth application-default login`.
3. Credentials từ metadata server của môi trường Google Cloud hỗ trợ tính năng này.

~~~mermaid
flowchart TD
    A[Java Google Cloud client] --> B[Application Default Credentials]
    B --> C{GOOGLE_APPLICATION_CREDENTIALS set?}
    C -->|Yes| D[Load credential configuration file]
    C -->|No| E{Local ADC file exists?}
    E -->|Yes| F[Load local user or impersonated credentials]
    E -->|No| G{GCP metadata server available?}
    G -->|Yes| H[Use attached workload identity]
    G -->|No| I[Credential discovery fails]
    D --> J[Obtain access token]
    F --> J
    H --> J
    J --> K[Google Cloud API]
    K --> L[IAM and API authorization checks]
~~~

Thứ tự này dẫn đến những tình huống quan trọng:

- Nếu `GOOGLE_APPLICATION_CREDENTIALS` đã đặt, tệp được chỉ định có thể được ưu tiên ngay cả khi chương trình chạy trên Cloud Run hoặc GKE.
- Nếu đường dẫn biến môi trường sai hoặc tệp không hợp lệ, quá trình tìm ADC có thể thất bại; không nên giả định thư viện luôn bỏ qua lỗi rồi tự chuyển sang metadata server.
- Khi phát triển trên máy cá nhân, tệp ADC thường được dùng nếu biến môi trường không chỉ định nguồn khác.
- Trong runtime GCP, nên sử dụng identity gắn với workload, lấy token từ metadata server, thay vì sao chép một khóa JSON vào container.

ADC có thể nạp nhiều loại credential configuration file: user credentials, service account credentials hoặc external account configuration dùng cho Workload Identity Federation. Không phải mọi tệp JSON đều là khóa riêng.

### Vị trí tệp ADC cục bộ

Đường dẫn thường gặp:

| Hệ điều hành | Đường dẫn |
|---|---|
| Linux/macOS | `~/.config/gcloud/application_default_credentials.json` |
| Windows | `%APPDATA%\\gcloud\\application_default_credentials.json` |

Các tệp này chứa dữ liệu xác thực và không nên được commit vào Git, chép vào container image hoặc gửi qua chat. Không cần mở tệp để kiểm tra token; dùng lệnh quản lý ADC của `gcloud`.

## 3. Phân biệt gcloud CLI login và ADC login

Google Cloud CLI và Java client libraries không nhất thiết dùng cùng bộ credentials.

| Lệnh hoặc cấu hình | Dùng cho |
|---|---|
| `gcloud auth login` | Đăng nhập tài khoản để `gcloud` thực hiện lệnh CLI |
| `gcloud auth application-default login` | Tạo ADC cục bộ để ứng dụng dùng qua client libraries |
| `gcloud config set project PROJECT_ID` | Chọn project mặc định cho nhiều lệnh CLI |
| `gcloud auth application-default set-quota-project PROJECT_ID` | Đặt quota project cho ADC cục bộ |
| `GOOGLE_CLOUD_PROJECT` | Gợi ý project cho ứng dụng/thư viện hỗ trợ biến này |
| `GOOGLE_APPLICATION_CREDENTIALS` | Chỉ định nguồn credential ưu tiên cho ADC |

Một lỗi hay gặp là `gcloud storage ls` chạy thành công nhưng ứng dụng Java lại báo không tìm thấy credentials. Nguyên nhân thường là developer đã đăng nhập CLI nhưng chưa tạo ADC cục bộ.

Một lỗi khác là CLI đang chọn project A, trong khi Java client kết nối đến project B. **Danh tính dùng để xác thực và project chứa tài nguyên là hai khái niệm riêng.** Để tránh nhầm, nên truyền project ID rõ ràng cho client ở các luồng nghiệp vụ cần tính xác định.

## 4. Thiết lập ADC trên máy cá nhân

### Bước 1 — Đăng nhập ADC

Trong môi trường phát triển đã cài Google Cloud CLI:

~~~bash
gcloud auth application-default login
~~~

Lệnh này mở luồng xác thực người dùng và lưu ADC cục bộ. Nó không tự chuyển quyền IAM của user sang service account của production.

### Bước 2 — Đặt quota project

~~~bash
gcloud auth application-default set-quota-project PROJECT_ID
~~~

Một số Google APIs yêu cầu quota project hợp lệ. Principal được dùng để tính quota cần có quyền sử dụng dịch vụ/quota tương ứng, thường bao gồm permission `serviceusage.services.use` trên quota project. Nếu thiếu quyền này, client có thể xác thực thành công nhưng API vẫn trả lỗi liên quan quota project.

### Bước 3 — Xác định project mục tiêu

~~~bash
gcloud config set project PROJECT_ID
~~~

Lệnh trên thiết lập project mặc định cho CLI. Đối với ứng dụng Java, vẫn nên khai báo project ID tường minh hoặc dùng biến môi trường đã được ứng dụng đọc.

Linux/macOS:

~~~bash
export GOOGLE_CLOUD_PROJECT="PROJECT_ID"
~~~

Windows PowerShell:

~~~powershell
$env:GOOGLE_CLOUD_PROJECT = "PROJECT_ID"
~~~

### Bước 4 — Kiểm tra ứng dụng

Chạy chương trình Java bằng client library hỗ trợ ADC và thao tác đọc an toàn trên tài nguyên thử nghiệm. Nếu gặp lỗi `403`, hãy kiểm tra IAM, API và quota project trước khi đăng nhập đi đăng nhập lại.

### Bước 5 — Thu hồi ADC khi cần

Khi đổi tài khoản hoặc không còn dùng ADC cục bộ:

~~~bash
gcloud auth application-default revoke
~~~

Lệnh này xóa/thu hồi credentials ADC cục bộ do Cloud SDK quản lý. Nó không đồng nghĩa với việc đăng xuất toàn bộ các tài khoản mà `gcloud auth login` đã lưu cho CLI.

## 5. Phát triển cục bộ bằng service account impersonation

Dùng user ADC trên máy cá nhân thuận tiện, nhưng quyền của user có thể rộng hơn quyền của workload trên production. Một cách kiểm thử sát production hơn là **impersonate service account** được cấp quyền hạn chế.

Ví dụ có service account `orders-dev@PROJECT_ID.iam.gserviceaccount.com` chỉ được đọc object trong bucket thử nghiệm.

Người phát triển cần có quyền tạo token thay mặt service account, thường cấp qua role:

`roles/iam.serviceAccountTokenCreator`

Tạo local ADC theo cơ chế impersonation:

~~~bash
gcloud auth application-default login \
  --impersonate-service-account="orders-dev@PROJECT_ID.iam.gserviceaccount.com"
~~~

Google Auth Library for Java hỗ trợ cấu hình ADC impersonation được CLI tạo trong các môi trường hỗ trợ. Khi dùng cách này, chương trình Java vẫn gọi `GoogleCredentials.getApplicationDefault()`, còn token truy cập được tạo dưới danh tính service account thay mặt user đã được phép impersonate.

Ưu điểm:

- Không cần tải service account key JSON về máy cá nhân.
- Quyền chạy thử có thể gần với quyền của runtime.
- Có thể quản lý, thu hồi và kiểm toán quyền impersonation.
- Giảm nguy cơ developer vô tình sử dụng quyền rộng của tài khoản cá nhân.

Lưu ý:

- User vẫn phải có quyền impersonate service account.
- Service account phải được cấp quyền trên tài nguyên đích; quyền impersonation của user không tự cấp quyền cho service account.
- Một số thư viện hoặc luồng xác thực đặc biệt có thể có yêu cầu bổ sung; kiểm thử với phiên bản Google Auth Library đang dùng.
- Không dùng service account production có quyền rộng chỉ để chạy thử trên laptop.

Với nhóm nhiều thành viên, nên tạo service account riêng theo môi trường dev/staging/prod và có quy trình cấp quyền impersonation theo nhu cầu.

## 6. Sử dụng ADC trong ứng dụng Java

Một ứng dụng Java thường không cần truyền đường dẫn khóa service account trực tiếp vào client builder. Thư viện Google Cloud sẽ dùng ADC khi không có credentials khác được cấu hình.

### Maven dependencies

Ví dụ sử dụng Google Cloud Java Libraries BOM để đồng bộ phiên bản:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.google.cloud</groupId>
      <artifactId>libraries-bom</artifactId>
      <version>REPLACE_WITH_VERIFIED_BOM_VERSION</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-storage</artifactId>
  </dependency>
</dependencies>
~~~

Thay `REPLACE_WITH_VERIFIED_BOM_VERSION` bằng phiên bản BOM tương thích với JDK và hệ sinh thái build đang dùng. Không ghim một phiên bản mẫu chưa được xác minh vào dự án production.

### Ví dụ kiểm tra quyền đọc object

Đoạn Java dưới đây dùng ADC và kiểm tra metadata của một object trong bucket lab. Nó không tải nội dung object và không in access token:

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public final class AdcStorageCheck {
    public static void main(String[] args) throws Exception {
        String projectId = requiredEnv("GOOGLE_CLOUD_PROJECT");
        String bucket = requiredEnv("CHECK_BUCKET");
        String objectName = requiredEnv("CHECK_OBJECT");

        GoogleCredentials credentials = GoogleCredentials.getApplicationDefault();

        Storage storage = StorageOptions.newBuilder()
                .setProjectId(projectId)
                .setCredentials(credentials)
                .build()
                .getService();

        Blob object = storage.get(BlobId.of(bucket, objectName));
        System.out.println(object == null
                ? "Object not found"
                : "Object metadata is readable");
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing environment variable: " + name);
        }
        return value;
    }
}
~~~

Ứng dụng cần quyền đọc object, ví dụ `roles/storage.objectViewer` được cấp trên bucket thích hợp. Nếu object không tồn tại, chương trình có thể in `Object not found`; nếu principal không có quyền, API thường trả lỗi phân quyền.

Thư viện chịu trách nhiệm lấy token và làm mới token khi cần. Không tự đọc tệp ADC, không giải mã JSON credential bằng tay và không ghi token ra log.

### Dùng client mặc định khi không cần cấu hình riêng

Trong ứng dụng ngắn gọn:

~~~java
Storage storage = StorageOptions.getDefaultInstance().getService();
~~~

Khi không truyền credentials tường minh, thư viện sử dụng cơ chế phát hiện ADC. Tuy nhiên, ứng dụng nhiều project nên cố định project ID để tránh nhầm tài nguyên và ngữ cảnh quota.

### Access token và ID token khác nhau

- **OAuth access token** được dùng cho các Google APIs như Cloud Storage hoặc Pub/Sub.
- **OIDC ID token** thường dùng khi một dịch vụ HTTP xác minh danh tính người gọi dựa trên audience, ví dụ gọi Cloud Run service yêu cầu xác thực.
- Không dùng access token thay ID token chỉ vì cả hai đều là chuỗi token.
- Với HTTP service dùng ID token, nên dùng API của Google Auth Library như `IdTokenCredentials` và đặt audience đúng với service đích.

## 7. Tích hợp ADC với Spring Boot

Một ứng dụng Spring Boot có thể sử dụng Google Cloud Java client library trực tiếp hoặc dùng Google Cloud Spring starters hỗ trợ auto-configuration.

Nếu dùng client library trực tiếp, khai báo một Spring bean:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CloudStorageConfiguration {
    @Bean
    public Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Service nghiệp vụ có thể nhận `Storage` qua constructor injection:

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import org.springframework.stereotype.Service;

@Service
public class ObjectMetadataService {
    private final Storage storage;

    public ObjectMetadataService(Storage storage) {
        this.storage = storage;
    }

    public boolean exists(String bucket, String objectName) {
        return storage.get(BlobId.of(bucket, objectName)) != null;
    }
}
~~~

Khi chạy local, bean dùng local ADC hoặc impersonated ADC. Khi triển khai vào Cloud Run/GKE/Compute Engine, nó dùng workload credentials do môi trường cung cấp, miễn là không có cấu hình credential khác ghi đè.

### Google Cloud Spring starters

Google Cloud Spring có thể auto-configure một số client và project settings. Nếu starter đã tạo bean `Storage`, không nên khai báo thêm bean cùng loại mà chưa xác minh cấu hình để tránh trùng bean hoặc dùng nhầm credentials.

Một số ứng dụng có thể đặt project ID và credentials location bằng properties của Google Cloud Spring. Khi đã có lựa chọn dùng ADC làm mặc định, tránh trỏ thẳng tới một JSON key trong `application.yml` hay `application.properties`.

Nên phân biệt ba loại cấu hình:

| Thuộc tính | Nơi quản lý |
|---|---|
| Project ID hoặc bucket name | Environment variable hoặc cấu hình ứng dụng |
| Danh tính workload | Cloud Run service account, GKE workload identity, Compute Engine attached service account |
| Quyền truy cập | IAM của project, bucket, topic hoặc secret |

Một cấu hình Spring có thể đặt tên bucket nhưng **không nên chứa private key hoặc refresh token**.

### Kiểm thử Spring

Với unit test, mock bean `Storage` hoặc inject một adapter/repository được mock. Không buộc mọi unit test phải đăng nhập ADC và kết nối GCP. Với integration test, dùng một project/bucket lab, service identity có quyền tối thiểu và dữ liệu thử nghiệm.

## 8. ADC trên Cloud Run

Cloud Run cho phép gắn một service account làm **runtime service identity** của service hoặc job. Google Cloud cung cấp access token ngắn hạn qua metadata server cho các client libraries trong container.

Ví dụ cập nhật danh tính của Cloud Run service:

~~~bash
gcloud run services update orders-api \
  --service-account="orders-api-runtime@PROJECT_ID.iam.gserviceaccount.com" \
  --region="asia-southeast1" \
  --project="PROJECT_ID"
~~~

Trước khi thay đổi service identity, kiểm tra quyền của người triển khai (bao gồm quyền sử dụng service account) và quyền của runtime identity. Cấu hình service identity là thao tác triển khai có thể ảnh hưởng ứng dụng nếu tài khoản mới thiếu IAM.

Ví dụ cấp quyền đọc object trên bucket riêng:

~~~bash
gcloud storage buckets add-iam-policy-binding gs://ORDERS_ASSETS_BUCKET \
  --member="serviceAccount:orders-api-runtime@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
~~~

Luồng xác thực:

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant Auth as Google Auth Library
    participant Meta as Cloud Run metadata server
    participant API as Cloud Storage API
    App->>Auth: Create Storage client with ADC
    Auth->>Meta: Request workload access token
    Meta-->>Auth: Short-lived token
    Auth->>API: Call API with token
    API-->>App: Result or authorization error
~~~

Ưu điểm là container không cần chứa private key. Thư viện tự quản lý token và refresh. Nếu cần thay đổi quyền, chỉnh IAM của runtime service account và kiểm chứng ứng dụng thay vì tạo key mới.

**Không đặt `GOOGLE_APPLICATION_CREDENTIALS` trong Cloud Run để trỏ đến một JSON key** khi ứng dụng có thể dùng attached service account. Biến này có thể ghi đè nguồn credentials của metadata server và tạo rủi ro vận hành.

### Cloud Run jobs

Cloud Run Jobs cũng hỗ trợ service identity. Mỗi job nên có quyền đúng với công việc riêng, ví dụ job xử lý batch có quyền đọc một bucket hoặc ghi vào một topic. Không chia sẻ một service account có quyền quá rộng cho mọi job và service chỉ vì thuận tiện.

## 9. ADC trên GKE với Workload Identity Federation

Trên GKE, ứng dụng Java thường chạy trong Pod. Cách xác thực nên dùng là **Workload Identity Federation for GKE**, cho phép workload nhận danh tính mà không phải mount service account key JSON.

Mô hình cơ bản:

1. GKE cluster hỗ trợ Workload Identity Federation for GKE.
2. Workload dùng một Kubernetes ServiceAccount (KSA).
3. IAM cấp quyền cho principal của KSA trên tài nguyên GCP, hoặc ánh xạ KSA đến IAM service account khi cần.
4. Pod gọi metadata server của GKE để lấy credentials.
5. Java client library dùng ADC như bình thường.

### Khai báo Kubernetes ServiceAccount

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
~~~

Trong Deployment:

~~~yaml
spec:
  template:
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:VERSION
~~~

Đây là trích đoạn `spec.template.spec` để minh họa. Deployment hoàn chỉnh vẫn cần selector, Pod labels và những trường Kubernetes bắt buộc khác.

### Cấp IAM trực tiếp cho KSA principal

Với mô hình direct resource access, có thể cấp quyền đọc bucket cho KSA principal:

~~~bash
gcloud storage buckets add-iam-policy-binding gs://ORDERS_ASSETS_BUCKET \
  --member="principal://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/PROJECT_ID.svc.id.goog/subject/ns/orders/sa/orders-api" \
  --role="roles/storage.objectViewer"
~~~

Thay `PROJECT_NUMBER` bằng project number, `PROJECT_ID` bằng project ID chứa workload identity pool của cluster và bucket bằng tài nguyên thực tế. Cluster, node pool và metadata server phải được cấu hình phù hợp. Trên GKE Standard, kiểm tra node pool có bật GKE metadata server; Autopilot có cơ chế quản lý tương ứng.

Không cần tải khóa service account về Pod. `StorageOptions.getDefaultInstance().getService()` vẫn hoạt động nhờ ADC.

### Liên kết KSA với IAM service account

Một số yêu cầu hoặc dịch vụ có thể cần mô hình KSA impersonate một IAM service account. Khi đó, cần:

- Gắn annotation `iam.gke.io/gcp-service-account` trên KSA.
- Cấp `roles/iam.workloadIdentityUser` cho principal KSA trên IAM service account.
- Cấp quyền tài nguyên cho IAM service account.

Ví dụ annotation:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
  annotations:
    iam.gke.io/gcp-service-account: orders-gke@PROJECT_ID.iam.gserviceaccount.com
~~~

Chọn direct resource access khi API và chính sách cho phép; dùng liên kết IAM service account khi thực sự cần. Không cấu hình cả hai cơ chế tùy tiện, vì sẽ khó xác định principal nào thực sự có quyền.

### Giới hạn cần kiểm chứng

- Pod phải dùng đúng KSA đã cấp quyền.
- Workload Identity Federation for GKE phải được bật và tương thích với node đang chạy.
- Kubernetes RBAC và Google Cloud IAM là hai lớp phân quyền riêng.
- Một số APIs có yêu cầu xác thực hoặc tên principal khác nhau; kiểm tra trường hợp cụ thể.
- NetworkPolicy và mạng cluster không được chặn đường truy cập cần thiết tới metadata server và Google APIs.

## 10. ADC trên Compute Engine

Compute Engine cho phép gắn service account vào VM. Client libraries trên VM có thể lấy token từ metadata server, tương tự Cloud Run.

Các điểm cần thiết kế:

- Gắn service account riêng cho workload, không dùng service account mặc định có quyền rộng.
- Cấp IAM cho service account trên các tài nguyên mà ứng dụng thực sự cần.
- Kiểm tra **access scopes** của VM. Scopes trên Compute Engine là một lớp giới hạn bổ sung bên cạnh IAM; một API call có thể bị từ chối dù IAM đã đủ nếu scope VM không cho phép.
- Khi sử dụng mô hình IAM hiện đại, VM thường dùng scope `cloud-platform` kết hợp với IAM tối thiểu để quản lý quyền chi tiết bằng IAM.
- Không chép service account key vào VM; dùng metadata server và token ngắn hạn.

Ví dụ xem cấu hình instance:

~~~bash
gcloud compute instances describe "VM_NAME" \
  --zone="ZONE" \
  --project="PROJECT_ID" \
  --format="yaml(serviceAccounts)"
~~~

Một VM có scope phù hợp nhưng service account thiếu IAM vẫn không được phép đọc bucket. Ngược lại, service account có IAM đọc bucket nhưng VM bị giới hạn scope cũng có thể thất bại.

Nếu ứng dụng Java chạy trong container trên VM, cần kiểm tra đường truy cập metadata server và danh tính VM. Đừng mặc định container đó có danh tính riêng nếu chưa cấu hình cơ chế phân tách phù hợp.

## 11. Chạy Java ngoài GCP bằng Workload Identity Federation

Ứng dụng có thể chạy trên GitHub Actions, GitLab, môi trường Kubernetes bên ngoài hoặc data center riêng. Với workload ngoài GCP, nên cân nhắc **Workload Identity Federation (WIF)** để trao đổi danh tính bên ngoài lấy credentials ngắn hạn, thay cho service account key tĩnh.

Luồng khái quát:

1. Nhà cung cấp danh tính bên ngoài cấp token cho workload.
2. Google Security Token Service xác minh token theo workload identity pool/provider đã cấu hình.
3. Workload nhận Google credentials qua federation hoặc service account impersonation được ủy quyền.
4. Java client library dùng external account credential configuration thông qua ADC.
5. Google Cloud API áp dụng IAM như bình thường.

Một external account credential configuration JSON có thể được trỏ đến bởi:

~~~bash
export GOOGLE_APPLICATION_CREDENTIALS="/secure/path/wif-credential-config.json"
~~~

Tệp cấu hình WIF không chứa service account private key như một key JSON, nhưng vẫn cần bảo vệ vì nó chỉ định nguồn token, audience và các thông số xác thực. Không tự chỉnh sửa endpoint hoặc chạy executable credential source không đáng tin cậy.

### Phân biệt WIF ngoài GCP và WIF for GKE

- **WIF ngoài GCP** kết nối danh tính của một identity provider bên ngoài tới Google Cloud.
- **Workload Identity Federation for GKE** cung cấp danh tính cho Pod trong cluster GKE.
- Cả hai giảm nhu cầu sử dụng khóa service account dài hạn, nhưng cách cấu hình principal, metadata server và IAM không hoàn toàn giống nhau.

## 12. IAM, quota project và quyền truy cập

Để một lệnh Java gọi API thành công, cần phân biệt từng lớp kiểm tra:

| Lớp | Câu hỏi | Lỗi điển hình |
|---|---|---|
| ADC discovery | Thư viện tìm được nguồn credentials không? | Không tìm thấy default credentials |
| Token issuance | Có lấy được token hợp lệ không? | Token refresh hoặc metadata server error |
| API enablement | API cần thiết đã bật chưa? | Service/API disabled |
| IAM | Principal có quyền trên resource không? | `PERMISSION_DENIED`, HTTP 403 |
| OAuth scope | Token có scope phù hợp không? | Insufficient authentication scopes |
| Quota project | Project dùng cho quota/billing có hợp lệ không? | User project hoặc service usage permission error |
| Resource address | Project, bucket, topic, secret có đúng không? | `NOT_FOUND`, HTTP 404 |
| Network | Runtime có thể kết nối tới Google APIs không? | Timeout, DNS hoặc proxy error |

### Ví dụ phân quyền tối thiểu

Một service account chỉ đọc object trong bucket:

~~~bash
gcloud storage buckets add-iam-policy-binding gs://ORDERS_ASSETS_BUCKET \
  --member="serviceAccount:orders-api-runtime@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
~~~

Nếu ứng dụng còn cần publish Pub/Sub, cấp thêm quyền phù hợp trên topic cụ thể thay vì `roles/editor` ở cấp project.

Không cấp `roles/owner`, `roles/editor` hoặc quyền IAM admin chỉ để giải quyết lỗi 403. Nên đọc thông báo lỗi, xác định API method và permission cần thiết, rồi cấp quyền hẹp nhất có thể.

### IAM và OAuth scopes

IAM thể hiện **được phép làm gì trên tài nguyên nào**. OAuth scopes mô tả phạm vi thao tác mà access token có thể thực hiện. Trên Compute Engine, cả scope và IAM có thể ảnh hưởng kết quả. Với nhiều client library Google Cloud Java, thư viện tự yêu cầu scope phù hợp.

Nếu tạo credential thủ công hoặc gọi API HTTP trực tiếp, cần hiểu scope cụ thể của API. Không thêm scope rộng một cách vô điều kiện cho mọi ứng dụng chỉ vì một lần gọi bị lỗi.

## 13. Bảo mật credentials và giảm nguy cơ lộ khóa

Những thói quen nên áp dụng:

- Dùng ADC và attached workload identity trên Cloud Run, GKE và Compute Engine.
- Dùng local ADC impersonation hoặc user ADC có quyền giới hạn cho phát triển.
- Dùng WIF cho workload ngoài GCP.
- Không tạo service account key JSON nếu có giải pháp không cần khóa dài hạn.
- Không commit `application_default_credentials.json`, JSON keys, refresh tokens hoặc access tokens.
- Không in `Authorization` header, token hoặc nội dung credential file ra log.
- Cấp IAM ở cấp bucket, topic, secret hoặc resource cụ thể khi có thể.
- Đặt danh tính khác nhau cho dev, staging và production.
- Rà soát quyền impersonation và service account đang có quyền rộng.
- Bật Cloud Audit Logs và giám sát hoạt động truy cập quan trọng.
- Dùng Secret Manager cho API key hoặc secret nghiệp vụ; không dùng nó để lưu service account key nếu có thể dùng workload identity.

### Tại sao không nên tải key JSON về máy?

Service account key JSON thường chứa private key dài hạn. Ai có bản sao key và có đường truy cập API có thể giả mạo service account đến khi key bị vô hiệu hóa hoặc hết hiệu lực theo chính sách. Key có thể bị lộ qua Git history, log build, image layer hoặc máy cá nhân bị xâm nhập.

ADC sử dụng metadata server hoặc federation giúp lấy token ngắn hạn mà không cần phân phối private key đến từng workload. Điều này giảm bề mặt rủi ro và đơn giản hóa việc thay đổi danh tính.

### Cảnh giác với biến môi trường ưu tiên cao

`GOOGLE_APPLICATION_CREDENTIALS` là cấu hình hữu ích trong một số môi trường đặc biệt nhưng cũng là nguyên nhân phổ biến khiến runtime dùng nhầm credentials. Trước khi deploy, kiểm tra image, manifest, Helm values, Cloud Run environment variables và cấu hình Spring để không vô tình ghi đè danh tính runtime.

## 14. Chẩn đoán lỗi ADC trong Java

Có thể tiếp cận theo thứ tự từ nguồn danh tính đến quyền truy cập.

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| "Your default credentials were not found" | Local ADC chưa tạo, không có metadata server | Chạy local ADC login hoặc kiểm tra runtime identity |
| Java dùng nhầm tài khoản | `GOOGLE_APPLICATION_CREDENTIALS` trỏ tệp khác | Kiểm tra env và nguồn credentials thực tế |
| CLI chạy được, Java không chạy | CLI login và ADC login khác nhau | Tạo local ADC bằng `gcloud auth application-default login` |
| HTTP 401 | Token thiếu, hết hạn hoặc không hợp lệ | Kiểm tra credential source, refresh và metadata server |
| HTTP 403 | Thiếu IAM, scope hoặc API/quota permission | Đọc permission/API trong error và cấp đúng quyền |
| "insufficient authentication scopes" | Compute Engine VM scope thiếu | Kiểm tra VM scopes và IAM |
| ADC local báo quota project | Thiếu quota project hoặc `serviceusage.services.use` | Đặt quota project và cấp quyền phù hợp |
| GKE Pod không nhận credentials | Sai KSA, WIF không bật hoặc metadata server không khả dụng | Kiểm tra KSA, node pool, IAM principal |
| Cloud Run dùng nhầm principal | Service account gắn sai hoặc credential override | Kiểm tra service identity và environment |
| Resource 404 | Sai project, bucket hoặc resource name | Đối chiếu resource ID và project mục tiêu |

### Trình tự kiểm tra có kiểm soát

1. Xác nhận chương trình đang chạy local, Cloud Run, GKE, Compute Engine hay ngoài GCP.
2. Kiểm tra có đặt `GOOGLE_APPLICATION_CREDENTIALS` hay không, nhưng không in nội dung tệp.
3. Nếu local, xác nhận đã tạo ADC bằng lệnh application-default login.
4. Nếu runtime, xác nhận đúng service account hoặc KSA và metadata server.
5. Xác nhận project, quota project và API enablement.
6. Xác định principal thực tế trong audit logs hoặc thông tin cấu hình của workload.
7. Kiểm tra IAM trên resource đích và scopes nếu nền tảng yêu cầu.
8. Thực hiện một request đọc an toàn để xác minh sau khi chỉnh cấu hình.

Không in access token hoặc toàn bộ credentials object để tìm lỗi. Có thể log loại credentials, project ID không nhạy cảm và một mã trace/correlation ID theo chính sách tổ chức.

### Trường hợp lỗi do quota project

Đối với user ADC cục bộ, một số thư viện cần quota project đã cấu hình:

~~~bash
gcloud auth application-default set-quota-project PROJECT_ID
~~~

Nếu lệnh bị từ chối, người dùng cần được cấp quyền `serviceusage.services.use` trên quota project hoặc sử dụng project được tổ chức cho phép. Việc set quota project không cấp quyền đọc tài nguyên của project đích.

### Trường hợp lỗi 403 trên Cloud Run

Nếu `orders-api` đọc bucket nhưng nhận 403:

- Xem service đang gắn service account nào.
- Kiểm tra `GOOGLE_APPLICATION_CREDENTIALS` có ghi đè identity không.
- Kiểm tra IAM bucket cấp `storage.objects.get` cho principal đó hay chưa.
- Xác minh bucket/project/object thực tế.
- Kiểm tra policy tổ chức hoặc VPC Service Controls nếu có.
- Kiểm tra API response và Cloud Audit Logs khi có.

Đừng sửa bằng cách cấp Owner cho Cloud Run runtime service account.

## 15. Tình huống thực hành: một ứng dụng Java chạy ở ba môi trường

Giả sử nhóm phát triển `orders-api` cần đọc `healthcheck.txt` trong bucket `orders-assets-lab` và publish sự kiện lên một Pub/Sub topic. Cùng mã Java phải chạy trên máy cá nhân, Cloud Run và GKE.

### Môi trường A — Local development

1. Developer tạo local ADC bằng `gcloud auth application-default login`.
2. Đặt quota project và project mục tiêu.
3. Khi cần kiểm thử đúng quyền workload, dùng impersonation với service account dev.
4. Chạy chương trình `AdcStorageCheck` với bucket và object lab.
5. Xác nhận thao tác đọc thành công mà không đưa credentials vào mã nguồn.

### Môi trường B — Cloud Run

1. Tạo service account runtime riêng `orders-api-runtime`.
2. Cấp quyền đọc bucket lab và publish topic cụ thể.
3. Gắn service account vào Cloud Run service.
4. Không mount JSON key, không đặt biến môi trường trỏ đến key.
5. Deploy image và chạy integration test.
6. Theo dõi Cloud Logging và Cloud Audit Logs để xác minh các call.

### Môi trường C — GKE

1. Bật hoặc xác nhận Workload Identity Federation for GKE.
2. Tạo KSA `orders-api` trong namespace `orders`.
3. Cấp IAM quyền trên bucket/topic cho KSA principal hoặc ánh xạ KSA sang IAM service account nếu cần.
4. Cấu hình `serviceAccountName` trong Deployment.
5. Deploy cùng image và chạy integration test.
6. Kiểm tra log, quyền IAM và hành vi metadata server.

### So sánh kết quả

| Yếu tố | Máy cá nhân | Cloud Run | GKE |
|---|---|---|---|
| Credential source | Local ADC hoặc impersonated ADC | Metadata server và runtime service account | GKE metadata server và workload identity |
| Cần khóa JSON dài hạn? | Không | Không | Không |
| Cấp quyền vào bucket | User hoặc service account dev | Runtime service account | KSA principal hoặc IAM service account liên kết |
| Mã Java | Không đổi | Không đổi | Không đổi |
| Điều cần xác minh | Quota project và principal dev | Service identity được gắn đúng | KSA, node/pool và WIF được cấu hình đúng |

Mục tiêu thành công là ba môi trường dùng cùng business logic, nhưng mỗi môi trường có identity, IAM và phạm vi dữ liệu riêng.

## 16. Checklist triển khai ADC cho Java

### Local development

- [ ] Đã cài Google Cloud CLI và đăng nhập bằng `gcloud auth application-default login`.
- [ ] Đã chọn project và quota project phù hợp.
- [ ] Kiểm tra local ADC không bị ghi đè bởi tệp không mong muốn.
- [ ] Dùng impersonation khi cần thử đúng quyền service account.
- [ ] Không commit ADC file hoặc service account key.
- [ ] Có project/tài nguyên lab để integration test.

### Java và Spring Boot

- [ ] Client library sử dụng ADC thay vì đường dẫn khóa hardcoded.
- [ ] Project ID được xác định rõ khi cần.
- [ ] Không in token hoặc secret trong logs.
- [ ] Unit tests có thể mock client, không phụ thuộc ADC thật.
- [ ] Spring auto-configuration không tạo bean trùng hoặc chọn nhầm credentials.
- [ ] Xử lý lỗi 401, 403 và 404 riêng theo nguyên nhân.

### Runtime GCP

- [ ] Cloud Run/Compute Engine có service account đúng trách nhiệm.
- [ ] GKE dùng Workload Identity Federation for GKE và KSA đúng.
- [ ] IAM được cấp tối thiểu trên resource.
- [ ] Compute Engine access scopes phù hợp.
- [ ] Metadata server và Google APIs có thể truy cập từ runtime.
- [ ] Không đưa service account private key vào image hoặc manifest.

### Vận hành và bảo mật

- [ ] Rà soát quyền service account và impersonation định kỳ.
- [ ] Tách danh tính dev, staging và production.
- [ ] Quản lý quota/billing project đúng chính sách.
- [ ] Theo dõi audit logs và lỗi xác thực.
- [ ] Ưu tiên WIF cho CI/CD ngoài GCP.
- [ ] Có hướng xử lý khi credentials bị thu hồi hoặc quyền IAM thay đổi.

ADC là nền tảng xác thực quan trọng cho Java trên Google Cloud vì nó cho phép sử dụng cùng client library ở nhiều môi trường mà không cần đóng gói khóa riêng trong ứng dụng. Khi nhóm kết hợp ADC với service identity đúng, IAM tối thiểu, quota project và kiểm tra runtime phù hợp, việc phát triển, triển khai và vận hành ứng dụng Java hoặc Spring Boot trở nên nhất quán và an toàn hơn.

