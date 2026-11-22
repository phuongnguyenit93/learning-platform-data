# Phạm vi quyền, impersonation và token trong Java client

## 1. Bài toán xác thực khi Java gọi Google Cloud APIs

Một ứng dụng Java hoặc Spring Boot có thể chạy trên Cloud Run, GKE, Compute Engine, máy phát triển cá nhân hoặc một nền tảng bên ngoài Google Cloud. Ở mỗi môi trường, ứng dụng cần chứng minh danh tính của mình khi gọi Google Cloud APIs, đồng thời chỉ được phép thực hiện những thao tác cần thiết.

Ba câu hỏi phải được trả lời riêng:

1. **Ứng dụng đang là ai?** Đây là xác thực (authentication), thường được thực hiện bằng Application Default Credentials (ADC), service account hoặc workload identity.
2. **Danh tính đó được phép làm gì trên tài nguyên nào?** Đây là phân quyền (authorization), chủ yếu do IAM quyết định.
3. **Credential hoặc token được cấp cho mục đích nào và tồn tại bao lâu?** Đây là nơi OAuth scopes, access token, ID token, impersonation và token lifetime tham gia.

Các khái niệm này liên quan nhưng không thay thế nhau. Có access token hợp lệ không có nghĩa ứng dụng có quyền đọc bucket. Có quyền IAM cũng không giúp một request thiếu credential được xác thực. Một OAuth scope rộng không tự cấp thêm IAM permission.

Trong module **CLOUD_PROVIDERS_GCP**, người học đã gặp tổ chức và project, IAM, VPC, Cloud Run, GKE, Compute Engine, Storage và cơ sở dữ liệu. Bài này nối các thành phần đó với cách Java client tìm credential, dùng danh tính service account, mượn danh tính có kiểm soát và gửi đúng loại token đến API đích.

## 2. Authentication và authorization

### 2.1. Authentication: xác định principal

Principal là danh tính thực hiện request. Trong Google Cloud, principal có thể là:

- Google Account của người dùng.
- Service account đại diện cho ứng dụng hoặc workload.
- Principal từ Workload Identity Federation hoặc Workforce Identity Federation.
- Một workload identity được liên kết với service account hoặc được cấp quyền trực tiếp theo mô hình được hỗ trợ.

Khi Java client gửi request có credential, Google Cloud xác định principal từ token. Ví dụ, một Cloud Run service có thể chạy dưới danh tính **orders-api@PROJECT_ID.iam.gserviceaccount.com**. Request từ ứng dụng khi đó được đánh giá theo danh tính service account này.

### 2.2. Authorization: IAM quyết định quyền

IAM kiểm tra principal có permission cần thiết trên resource hay không. Permission thường được cấp thông qua role:

- **Basic roles:** Owner, Editor, Viewer; phạm vi rất rộng và nên tránh trong ứng dụng production.
- **Predefined roles:** tập permission được Google quản lý theo chức năng, ví dụ **roles/storage.objectViewer**.
- **Custom roles:** tập permission do tổ chức định nghĩa khi predefined role chưa đáp ứng yêu cầu.

Ví dụ, một service account chỉ cần đọc object trong bucket có thể nhận **roles/storage.objectViewer** trên bucket đó. Không cần cấp **roles/storage.admin** ở cấp project nếu ứng dụng không cần quản trị bucket.

IAM policy có thể được gắn ở organization, folder, project hoặc resource. Quyền ở cấp cha có thể được kế thừa xuống cấp con. Khi điều tra quyền, cần kiểm tra cả binding được gắn trực tiếp và quyền kế thừa; một binding ở project có thể rộng hơn ý định của nhóm phát triển.

### 2.3. Mô hình tổng quát

~~~mermaid
flowchart LR
    A[Java / Spring Boot workload] --> B[ADC hoặc credential source]
    B --> C[Principal và token]
    C --> D[Google Cloud API]
    D --> E{IAM và policy cho phép?}
    E -- Có --> F[Thực hiện thao tác trên resource]
    E -- Không --> G[401 hoặc 403]
    H[OAuth scope / audience] --> C
~~~

ADC giúp Java client tìm credential và lấy token. Token thể hiện danh tính và loại quyền xác thực phù hợp. API kiểm tra thêm scope hoặc audience theo giao thức, sau đó IAM đánh giá quyền trên resource.

## 3. IAM policy và phạm vi quyền của service account

### 3.1. Service account là danh tính của workload

Service account không phải một máy chủ hoặc một key file. Đây là principal đại diện cho ứng dụng, job hoặc tài nguyên chạy code. Khi một VM, Cloud Run service hoặc GKE workload dùng service account, request từ workload được xác thực dưới danh tính đó.

Tách service account theo workload và trách nhiệm:

| Workload | Quyền tham khảo | Phạm vi nên xem xét |
|---|---|---|
| API đọc object | **roles/storage.objectViewer** | Bucket cần đọc |
| Job ghi object | **roles/storage.objectCreator** | Bucket cần ghi |
| API đọc secret | **roles/secretmanager.secretAccessor** | Secret cụ thể |
| Service gọi Cloud Run nội bộ | **roles/run.invoker** | Cloud Run service đích |
| Job đọc metadata tài nguyên | Role đọc phù hợp của Cloud Asset API | Project hoặc folder cần kiểm kê |
| Pipeline triển khai | Role triển khai theo dịch vụ và target | Project/environment được giao |

Tên role ở bảng là ví dụ. Hãy kiểm tra danh mục role và permission hiện hành của dịch vụ trước khi cấp quyền. Một workload thường cần nhiều role nhỏ trên các resource khác nhau, không nhất thiết một role lớn ở cấp project.

### 3.2. Gắn service account vào tài nguyên: actAs

Một người hoặc service account tạo VM, Cloud Run service hay tài nguyên có thể chạy code cần quyền gắn service account vào tài nguyên đó. Permission quan trọng là **iam.serviceAccounts.actAs**. Role thường dùng để cung cấp permission này là **Service Account User**:

**roles/iam.serviceAccountUser**

Role này cho phép principal gắn service account vào một resource. Nó không tự cho phép principal tạo access token ngắn hạn để impersonate service account bằng IAM Credentials API.

Ví dụ: một kỹ sư triển khai Cloud Run service và chọn **orders-runtime@PROJECT_ID.iam.gserviceaccount.com**. Kỹ sư cần quyền tạo/cập nhật Cloud Run service và quyền actAs trên service account đó. Khi service chạy, ứng dụng dùng danh tính orders-runtime; kỹ sư không vì thế tự động nhận toàn bộ quyền của runtime service account.

### 3.3. Tạo credential ngắn hạn: Service Account Token Creator

**Service Account Token Creator**:

**roles/iam.serviceAccountTokenCreator**

Role này cho phép principal tạo credential ngắn hạn cho service account, bao gồm:

- OAuth 2.0 access token.
- OpenID Connect (OIDC) ID token.
- Chữ ký blob và JWT thông qua các permission ký tương ứng.
- Delegation giữa service account trong một chuỗi impersonation.

Một số permission quan trọng:

| Permission | Tác dụng |
|---|---|
| **iam.serviceAccounts.getAccessToken** | Tạo OAuth access token cho service account |
| **iam.serviceAccounts.getOpenIdToken** | Tạo OIDC ID token |
| **iam.serviceAccounts.signBlob** | Ký dữ liệu nhị phân, có thể dùng trong luồng signed URL |
| **iam.serviceAccounts.signJwt** | Ký JWT |
| **iam.serviceAccounts.implicitDelegation** | Hỗ trợ delegation chain |

Đây là quyền nhạy cảm. Principal có thể tạo token mang danh tính của service account đích và sử dụng những quyền mà service account đó đang có. Hãy cấp role trên đúng service account đích, tránh cấp ở cấp project hoặc folder nếu chỉ cần impersonate một tài khoản.

Nếu chỉ cần tạo OIDC ID token, có thể xem xét role hẹp hơn:

**roles/iam.serviceAccountOpenIdTokenCreator**

Role này chỉ cung cấp permission tạo ID token. Không cấp Service Account Token Creator rộng hơn nếu workload chỉ cần chức năng đó.

### 3.4. Workload Identity User cho GKE

Với GKE Workload Identity Federation, Kubernetes service account có thể được liên kết với Google service account để workload nhận danh tính phù hợp. Role thường dùng trên service account đích là:

**roles/iam.workloadIdentityUser**

Role này cho phép workload identity của GKE impersonate service account trong phạm vi được cấu hình. Đây là mô hình dành cho GKE workload; không nhầm nó với **roles/iam.serviceAccountUser** dùng để gắn service account vào tài nguyên, hoặc **roles/iam.serviceAccountTokenCreator** dùng trong các luồng impersonation khác.

### 3.5. So sánh các role thường bị nhầm

| Role | Dùng khi nào? | Không có nghĩa là |
|---|---|---|
| **roles/iam.serviceAccountUser** | Gắn service account vào VM, Cloud Run hoặc resource hỗ trợ | Được quyền mint access token để impersonate |
| **roles/iam.serviceAccountTokenCreator** | Tạo access token, ID token hoặc ký JWT/blob cho service account | Được quyền đọc mọi resource của service account |
| **roles/iam.serviceAccountOpenIdTokenCreator** | Chỉ cần tạo OIDC ID token | Có quyền tạo access token hoặc ký blob |
| **roles/iam.workloadIdentityUser** | Liên kết workload identity của GKE với service account | Là role truy cập bucket, secret hoặc database |

Các role trên kiểm soát cách principal sử dụng danh tính service account. Quyền truy cập tài nguyên nghiệp vụ vẫn cần được cấp cho service account đích.

## 4. OAuth scopes và IAM permissions

### 4.1. Hai lớp kiểm soát khác nhau

OAuth scope là phạm vi mà access token được phép yêu cầu khi gọi API. IAM role chứa permission để thực hiện hành động trên resource. Một request thường phải thỏa mãn cả yêu cầu scope của API và IAM permission.

Ví dụ:

- Token có scope **https://www.googleapis.com/auth/cloud-platform**.
- Service account chỉ có **roles/storage.objectViewer** trên bucket reports.
- Ứng dụng có thể đọc object trong phạm vi IAM cho phép; scope rộng không biến service account thành Storage Admin.

Một scope hẹp có thể giảm phạm vi sử dụng token, nhưng không thay thế least privilege trong IAM. Ngược lại, cấp role IAM không làm token thiếu scope phù hợp tự động trở nên hợp lệ.

### 4.2. Các scope thường gặp

| Scope | Mục đích |
|---|---|
| **https://www.googleapis.com/auth/cloud-platform** | Scope tổng quát cho Google Cloud APIs |
| **https://www.googleapis.com/auth/devstorage.read_only** | Truy cập Cloud Storage theo phạm vi đọc |
| **https://www.googleapis.com/auth/devstorage.read_write** | Truy cập Cloud Storage theo phạm vi đọc/ghi |
| **https://www.googleapis.com/auth/iam** | Gọi các chức năng IAM phù hợp, ví dụ luồng impersonation |
| **https://www.googleapis.com/auth/userinfo.email** | Truy cập thông tin email người dùng trong các luồng hỗ trợ |

API method cụ thể quyết định scope nào được chấp nhận. Kiểm tra API reference khi chọn scope; không sao chép scope của một API sang API khác.

### 4.3. Access scopes trên Compute Engine

Compute Engine VM có access scopes gắn với service account. Đây là một lớp giới hạn bổ sung cho token được cấp qua metadata server. Trong thực tế, cách cấu hình phổ biến là dùng scope cloud-platform trên VM rồi kiểm soát quyền bằng IAM role hẹp.

Nếu VM chỉ có scope Cloud Storage read-only, dù service account có role IAM ghi object, token có thể vẫn bị giới hạn bởi access scope. Nếu VM có scope cloud-platform, điều đó không cấp thêm quyền IAM; service account vẫn chỉ được thực hiện những thao tác mà IAM cho phép.

Không nhầm access scopes của VM với IAM role. Khi gặp 403, kiểm tra cả IAM policy và access scopes của VM nếu ứng dụng chạy trên Compute Engine. Cloud Run và các môi trường khác có mô hình credential riêng, không áp dụng nguyên xi cấu hình access scope của VM.

## 5. Application Default Credentials trong Java

### 5.1. ADC giúp giữ nguyên code giữa các môi trường

Application Default Credentials (ADC) là cơ chế để Google Auth Library tự tìm credential phù hợp với môi trường chạy. Cloud Client Libraries for Java có thể dùng ADC mà không cần ứng dụng tự đọc key hoặc tự gọi token endpoint.

Trong môi trường production trên Google Cloud, ưu tiên gắn **user-managed service account** với resource chạy code:

- Cloud Run service hoặc job dùng service account được cấu hình cho revision/job.
- Compute Engine VM dùng service account gắn với instance.
- GKE workload dùng Workload Identity Federation for GKE.
- Workload bên ngoài Google Cloud dùng Workload Identity Federation với external identity provider.

Không dựa vào default service account có quyền quá rộng. Tạo service account riêng và cấp role tối thiểu theo workload.

### 5.2. ADC tìm credential theo thứ tự

Google Auth Library for Java tìm credential theo các nguồn chính:

1. File được trỏ bởi biến môi trường **GOOGLE_APPLICATION_CREDENTIALS**.
2. File local ADC được tạo bằng **gcloud auth application-default login**.
3. Credential của môi trường Google Cloud thông qua metadata server hoặc nguồn credential tích hợp tương ứng.

File trong GOOGLE_APPLICATION_CREDENTIALS có thể là service account key, external account configuration cho Workload Identity Federation hoặc Workforce Identity Federation. Nếu biến môi trường trỏ đến file cũ, ứng dụng có thể dùng credential khác với service account được gắn vào Cloud Run/VM. Khi debug, kiểm tra nguồn ADC thực tế trước.

Lệnh tạo local ADC cho người dùng:

~~~bash
gcloud auth application-default login
~~~

**gcloud auth login** và **gcloud auth application-default login** phục vụ hai cấu hình credential khác nhau. Việc đăng nhập gcloud CLI không tự động có nghĩa Java client đang dùng cùng credential.

### 5.3. Ví dụ Java client dùng ADC

Cloud Client Libraries for Java thường tự sử dụng ADC:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public class StorageAccess {
    public Storage createClient() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Cùng đoạn code có thể chạy local với ADC của developer, trên Cloud Run với service account gắn vào revision, hoặc trên GKE với Workload Identity Federation. Điều thay đổi là credential source và IAM policy của principal, không phải cách gọi Storage.

### 5.4. Dùng ADC trong Spring Boot

Spring Boot nên khởi tạo client ở tầng cấu hình và inject vào service. Không tạo client hoặc gọi metadata server ở mỗi request.

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GoogleCloudClientConfig {

    @Bean
    Storage storageClient() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Service nghiệp vụ nhận client qua constructor injection:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.Storage;
import org.springframework.stereotype.Service;

@Service
public class ReportStorageService {

    private final Storage storage;

    public ReportStorageService(Storage storage) {
        this.storage = storage;
    }

    public Blob findReport(String bucket, String objectName) {
        return storage.get(bucket, objectName);
    }
}
~~~

Không truyền access token vào constructor của service nghiệp vụ. Hãy inject client hoặc Credentials có khả năng refresh. Client library chịu trách nhiệm gắn credential vào request và làm mới token khi cần.

## 6. Service account impersonation

### 6.1. Impersonation là gì?

Service account impersonation cho phép một principal đã được xác thực yêu cầu Google Cloud cấp credential ngắn hạn cho một service account khác. Principal ban đầu gọi là **source principal**; service account được mượn danh tính gọi là **target service account**.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant Source as Source credential
    participant IAM as IAM Credentials API
    participant Target as Target service account
    participant API as Google Cloud API
    App->>Source: Lấy credential ban đầu qua ADC
    App->>IAM: generateAccessToken(target, scopes, lifetime)
    IAM->>IAM: Kiểm tra Token Creator và delegation
    IAM-->>App: Access token ngắn hạn của target
    App->>API: Gửi request bằng token
    API->>Target: Xác định principal của token
    API->>API: Kiểm tra IAM trên resource
    API-->>App: Kết quả
~~~

Source principal không cần có quyền trực tiếp trên resource nghiệp vụ nếu nó chỉ được phép impersonate target service account. Target service account phải có các IAM role cần thiết trên resource mà ứng dụng muốn truy cập.

Impersonation hữu ích khi:

- Developer cần kiểm thử ứng dụng với quyền gần giống production.
- Một pipeline cần dùng danh tính triển khai riêng.
- Một workload cần truy cập tài nguyên bằng service account khác theo ranh giới bảo mật.
- Tổ chức muốn cấp quyền tạm thời mà không phát hành service account key.

Impersonation tạo credential ngắn hạn và không yêu cầu tải private key của target về máy.

### 6.2. Điều kiện để impersonate

Trước khi dùng ImpersonatedCredentials trong Java:

1. Bật **Service Account Credentials API** (iamcredentials.googleapis.com) trong project nguồn thực hiện yêu cầu impersonation.
2. Cấp **roles/iam.serviceAccountTokenCreator** cho source principal trên target service account.
3. Cấp IAM role nghiệp vụ cho target service account trên resource đích.
4. Chọn OAuth scope phù hợp cho token được tạo.
5. Đặt lifetime ngắn và phù hợp với thời gian xử lý.

Role Token Creator nên được gắn trực tiếp trên target service account nếu chỉ cần impersonate một tài khoản. Tránh cấp ở cấp project hoặc folder khi không cần thiết.

### 6.3. Ví dụ Java với ImpersonatedCredentials

Ví dụ dưới đây cho phép credential hiện tại trong ADC impersonate một service account chỉ đọc Cloud Storage. Source credential cần quyền Token Creator trên target service account; target service account cần **roles/storage.objectViewer** trên bucket cần đọc.

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.ImpersonatedCredentials;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

import java.io.IOException;
import java.util.Arrays;

public class ImpersonatedStorageClient {

    public Storage createClient() throws IOException {
        GoogleCredentials sourceCredentials =
            GoogleCredentials.getApplicationDefault()
                .createScoped(
                    Arrays.asList("https://www.googleapis.com/auth/iam")
                );

        ImpersonatedCredentials targetCredentials =
            ImpersonatedCredentials.newBuilder()
                .setSourceCredentials(sourceCredentials)
                .setTargetPrincipal(
                    "report-reader@PROJECT_ID.iam.gserviceaccount.com"
                )
                .setScopes(
                    Arrays.asList(
                        "https://www.googleapis.com/auth/devstorage.read_only"
                    )
                )
                .setLifetime(1800)
                .build();

        return StorageOptions.newBuilder()
            .setProjectId("PROJECT_ID")
            .setCredentials(targetCredentials)
            .build()
            .getService();
    }
}
~~~

Trong ví dụ:

- sourceCredentials là danh tính ban đầu được ADC cung cấp.
- Scope iam cho phép source credential thực hiện luồng gọi IAM Credentials API theo cấu hình phù hợp.
- targetPrincipal là service account muốn impersonate.
- Scope devstorage.read_only giới hạn mục đích OAuth của token vào truy cập đọc Storage.
- setLifetime(1800) yêu cầu token sống 1.800 giây, tức 30 phút.

Đoạn mã là ví dụ cho một client đọc Storage. Thay project, email và scope theo hệ thống thực tế. Không dùng danh sách scope này cho một API khác nếu chưa kiểm tra tài liệu method.

### 6.4. Impersonation trong local development

Developer có thể tạo local ADC để client library tự impersonate service account:

~~~bash
gcloud auth application-default login \
  --impersonate-service-account=report-reader@PROJECT_ID.iam.gserviceaccount.com
~~~

Java client sau đó vẫn dùng:

~~~java
GoogleCredentials credentials =
    GoogleCredentials.getApplicationDefault();
~~~

Cách này hữu ích để kiểm tra quyền của target service account mà không tải key JSON xuống máy. Developer cần được cấp Token Creator trên service account đích; target service account cần role nghiệp vụ cần thiết.

### 6.5. Delegation chain

Một số tổ chức cần chuỗi danh tính A → B → C → target thay vì source principal impersonate target trực tiếp. Java Auth Library hỗ trợ danh sách delegates qua setDelegates.

Mỗi bước trong chuỗi phải cấp quyền Token Creator cho principal đứng trước trên service account tiếp theo. Ví dụ, source có Token Creator trên B, B có Token Creator trên C, và C có Token Creator trên target. Cấu hình chuỗi dài làm tăng độ phức tạp khi audit và debug; chỉ dùng khi có ranh giới quản trị thực sự cần thiết.

Không cấu hình self-impersonation để service account tự tạo token mới cho chính nó từ short-lived token. Google Cloud chặn một số kiểu self-impersonation vì có thể tạo vòng làm mới credential vô hạn nếu token bị đánh cắp.

## 7. Access token, ID token và token ký

Không phải mọi token đều dùng để gọi cùng một loại endpoint.

### 7.1. OAuth 2.0 access token

Access token là bearer credential thường dùng để gọi Google Cloud APIs. Client gửi token trong header:

~~~http
Authorization: Bearer ACCESS_TOKEN
~~~

Token đại diện cho principal và mang scope được yêu cầu. API tiếp tục kiểm tra IAM permission của principal trên resource. Không đưa access token vào query string vì URL dễ bị ghi vào log, proxy hoặc browser history.

### 7.2. OIDC ID token

ID token là JWT do Google ký, chứa thông tin danh tính và claim aud (audience). Nó dùng để xác thực với một service hoặc ứng dụng cụ thể, ví dụ:

- Gọi Cloud Run service yêu cầu authentication.
- Gọi Cloud Run functions.
- Gọi ứng dụng bảo vệ bởi Identity-Aware Proxy (IAP).
- Gọi API Gateway hoặc Cloud Endpoints trong mô hình hỗ trợ.

aud phải khớp audience mà service đích mong đợi. Với Cloud Run, thường dùng URL service; với IAP, audience có thể là OAuth client ID theo cấu hình IAP.

Để gọi Cloud Run service riêng tư, service account thể hiện trong ID token còn cần được cấp **roles/run.invoker** trên Cloud Run service đích. Token hợp lệ chỉ chứng minh danh tính; IAM quyết định danh tính đó có được invoke service hay không.

Nếu ứng dụng chạy trên Cloud Run, Compute Engine hoặc GKE với service account được gắn/liên kết, metadata server có thể cung cấp ID token cho workload. Khi dùng chính danh tính workload đó, ứng dụng không cần tự cấp Token Creator cho service account của mình; service account vẫn cần quyền Invoker trên service đích. Nếu cần impersonate một service account khác để tạo ID token, cấp role tạo ID token trên service account đích cho source principal.

### 7.3. Signed JWT và signed blob

IAM Credentials API có thể ký JWT hoặc dữ liệu nhị phân bằng private key được Google quản lý. Private key không được tải xuống ứng dụng. Các luồng này phù hợp với giao thức hoặc tính năng cần chữ ký, chẳng hạn signed URL hoặc một số luồng xác thực liên kết.

Không dùng signed JWT thay cho access token thông thường nếu API yêu cầu OAuth access token. Chọn credential theo hợp đồng xác thực của endpoint.

### 7.4. Downscoped access token

Credential Access Boundary (CAB) cho phép tạo downscoped token từ một credential nguồn có quyền rộng hơn, giới hạn quyền truy cập vào một tập tài nguyên và permission cụ thể. Một trường hợp điển hình là token broker cấp token đọc object trong một bucket hoặc prefix cho workload khác.

Downscoping đặc biệt hữu ích khi một dịch vụ trung gian cần cấp quyền tạm thời cho consumer. Consumer chỉ nhận token có phạm vi nhỏ, thay vì credential nguồn có quyền rộng. Kiểm tra giới hạn hỗ trợ của Credential Access Boundary và dịch vụ mục tiêu; không giả định CAB áp dụng cho mọi Google Cloud API.

## 8. Token lifetime, refresh và quản lý vòng đời

### 8.1. Lifetime của token

Access token tạo qua service account impersonation có lifetime tối đa mặc định là **1 giờ (3.600 giây)**. Tổ chức có thể cho phép tối đa **12 giờ (43.200 giây)** đối với service account được chỉ định trong Organization Policy constraint:

**constraints/iam.allowServiceAccountCredentialLifetimeExtension**

Chỉ tăng lifetime khi có yêu cầu vận hành cụ thể. Token càng sống lâu thì khoảng thời gian token bị lộ có thể bị sử dụng càng dài. Thông thường nên dùng lifetime ngắn phù hợp với công việc, ví dụ 15–60 phút, và để client library refresh khi cần.

ID token tạo bằng IAM Credentials API có thời hạn ngắn; tài liệu generateIdToken mô tả token hợp lệ trong 1 giờ. Với metadata server hoặc các loại workload identity khác, hãy dựa vào credential provider và tài liệu của môi trường.

### 8.2. Refresh token trong Java client

Không nên lấy access token một lần lúc ứng dụng khởi động rồi giữ chuỗi token đó cho toàn bộ vòng đời process. Token có thời hạn; nếu token hết hạn, request tiếp theo có thể nhận 401 UNAUTHENTICATED.

Hãy giữ đối tượng GoogleCredentials, ImpersonatedCredentials hoặc IdTokenCredentials và truyền đối tượng đó vào client library hoặc HTTP credentials adapter. Google Auth Library quản lý trạng thái token và refresh theo loại credential khi client gửi request.

Ví dụ với một credential được nạp rõ ràng, refreshIfExpired() có thể được dùng trước khi đọc token. Tuy nhiên, Cloud Client Libraries thường tự gọi cơ chế credential khi cần; ứng dụng không cần tự viết vòng lặp refresh cho từng request.

Nếu bạn tạo GoogleCredentials từ một AccessToken tĩnh, credential đó không có thông tin để tự xin token mới. Khi cần refresh, hãy cung cấp credential provider có khả năng làm mới hoặc quay lại nguồn ADC/impersonation.

### 8.3. Bảo vệ token

- Không log access token, ID token, refresh token hoặc Authorization header.
- Không ghi token vào database, source code, Docker image, build artifact hoặc URL.
- Không gửi token qua kênh không mã hóa.
- Không chia sẻ token giữa người dùng hoặc workload khác nhau.
- Không giữ token trong cache lâu hơn expiry.
- Không dùng toString() của credential để debug trong production; một số implementation có thể chứa raw token trong request metadata.
- Khi credential bị lộ, xác định principal và resource bị ảnh hưởng, loại bỏ quyền impersonation nếu cần, xoay vòng nguồn credential và theo dõi audit logs.

Token ngắn hạn giảm rủi ro tồn tại lâu, nhưng không thay thế việc bảo vệ source credential và giới hạn IAM.

## 9. Ví dụ Java: gọi Cloud Run bằng ID token

Giả sử một Spring Boot service cần gọi một Cloud Run service nội bộ có authentication. Ứng dụng dùng service account gắn với workload hoặc một impersonated service account có quyền invoke service đích.

Ví dụ dùng IdTokenCredentials và HttpCredentialsAdapter:

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.IdTokenCredentials;
import com.google.auth.oauth2.IdTokenProvider;
import com.google.auth.http.HttpCredentialsAdapter;
import com.google.api.client.http.GenericUrl;
import com.google.api.client.http.HttpRequest;
import com.google.api.client.http.HttpRequestFactory;
import com.google.api.client.http.HttpResponse;
import com.google.api.client.http.javanet.NetHttpTransport;

public class InternalCloudRunClient {

    public String call(String serviceUrl) throws Exception {
        GoogleCredentials credentials =
            GoogleCredentials.getApplicationDefault();

        if (!(credentials instanceof IdTokenProvider)) {
            throw new IllegalStateException(
                "Credential provider does not support ID tokens"
            );
        }

        IdTokenCredentials idTokenCredentials =
            IdTokenCredentials.newBuilder()
                .setIdTokenProvider((IdTokenProvider) credentials)
                .setTargetAudience(serviceUrl)
                .build();

        HttpRequestFactory requestFactory =
            new NetHttpTransport().createRequestFactory(
                new HttpCredentialsAdapter(idTokenCredentials)
            );

        HttpRequest request =
            requestFactory.buildGetRequest(new GenericUrl(serviceUrl));

        try (HttpResponse response = request.execute()) {
            return response.parseAsString();
        }
    }
}
~~~

HttpCredentialsAdapter gắn credential vào request. IdTokenCredentials lấy ID token phù hợp audience; client không cần tự nối chuỗi bearer token. Trong production, nên dùng HTTP transport/client được quản lý và cấu hình timeout, connection pooling, retry theo yêu cầu dịch vụ.

Service account được thể hiện trong ID token cần có **roles/run.invoker** trên Cloud Run service đích. Nếu token được tạo bằng impersonation, source principal còn cần quyền mint ID token cho target service account. Nếu chỉ tạo ID token, role **roles/iam.serviceAccountOpenIdTokenCreator** là lựa chọn hẹp hơn khi đáp ứng luồng sử dụng.

## 10. Spring Boot: cấu hình credential theo môi trường

Một ứng dụng nên tách phần tạo credential khỏi logic nghiệp vụ. Có thể cấu hình một bean Credentials hoặc tạo client bean trực tiếp. Với Cloud Client Libraries, cách đơn giản nhất là để ADC tự chọn nguồn credential.

Nếu cần impersonation, có thể xây dựng ImpersonatedCredentials trong lớp Configuration và inject client đã cấu hình vào service. Target service account email nên lấy từ cấu hình môi trường; không hard-code credential hoặc token.

Ví dụ bean Storage dùng ADC:

~~~java
@Configuration
public class GcpStorageConfiguration {

    @Bean
    public Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Ví dụ bean Storage dùng impersonation:

~~~java
@Configuration
public class GcpImpersonationConfiguration {

    @Bean
    public Storage storage(
        @Value("${gcp.auth.target-service-account}") String targetServiceAccount
    ) throws IOException {

        GoogleCredentials source =
            GoogleCredentials.getApplicationDefault()
                .createScoped(
                    Collections.singletonList(
                        "https://www.googleapis.com/auth/iam"
                    )
                );

        ImpersonatedCredentials target =
            ImpersonatedCredentials.newBuilder()
                .setSourceCredentials(source)
                .setTargetPrincipal(targetServiceAccount)
                .setScopes(
                    Collections.singletonList(
                        "https://www.googleapis.com/auth/devstorage.read_only"
                    )
                )
                .setLifetime(1800)
                .build();

        return StorageOptions.newBuilder()
            .setCredentials(target)
            .build()
            .getService();
    }
}
~~~

Ví dụ cần các import tương ứng như GoogleCredentials, ImpersonatedCredentials, Storage, StorageOptions, Value, Bean, Configuration, Collections và java.io.IOException. Cấu hình target service account nên được cung cấp bằng environment-specific configuration hoặc secret/config management phù hợp. Email service account không phải secret, nhưng việc chọn target là một quyết định quyền cần review.

Không khởi tạo client trong từng method nghiệp vụ. Tái sử dụng client theo vòng đời ứng dụng giúp tận dụng connection pooling và credential refresh. Nếu ứng dụng có nhiều target service account với quyền khác nhau, tạo client bean tách biệt theo nhiệm vụ thay vì thay đổi credential dùng chung giữa các request.

## 11. Tình huống thực hành: Spring Boot trên Cloud Run đọc Storage và gọi service nội bộ

Một ứng dụng invoice-api chạy trên Cloud Run cần:

- Đọc file PDF từ bucket invoice-private.
- Gọi pdf-renderer là một Cloud Run service riêng tư.
- Ghi log metadata xử lý và trả kết quả cho người dùng.

### Thiết kế danh tính

Tạo service account runtime:

**invoice-api-runtime@PROJECT_ID.iam.gserviceaccount.com**

Cấp các quyền:

| Resource | Role | Lý do |
|---|---|---|
| Bucket invoice-private | **roles/storage.objectViewer** | Đọc file PDF |
| Cloud Run service pdf-renderer | **roles/run.invoker** | Gọi service nội bộ |

Gắn service account này vào Cloud Run revision của invoice-api. Java client dùng ADC để nhận credential từ môi trường. Không cần tải service account JSON key vào container.

### Luồng gọi

1. Cloud Run khởi chạy revision với service account invoice-api-runtime.
2. Java Storage client dùng ADC để lấy credential và đọc object trong bucket.
3. Khi gọi pdf-renderer, ứng dụng lấy ID token với audience là URL service pdf-renderer.
4. pdf-renderer xác thực ID token và kiểm tra quyền roles/run.invoker của invoice-api-runtime.
5. Ứng dụng ghi log request ID, tên service và trạng thái xử lý; không ghi token hoặc nội dung nhạy cảm.

### Phát triển local

Developer có thể dùng ADC cá nhân nếu được cấp quyền trực tiếp vào tài nguyên thử nghiệm. Nếu muốn kiểm tra chính xác quyền runtime service account, developer có thể impersonate invoice-api-runtime bằng local ADC. Khi đó:

- Developer cần Token Creator trên service account đích.
- Service account runtime cần các role Storage Viewer và Cloud Run Invoker tương ứng.
- Java code vẫn dùng GoogleCredentials.getApplicationDefault().

Tách project hoặc bucket thử nghiệm khỏi production để developer không cần nhận quyền đọc dữ liệu thật. Dùng impersonation giúp kiểm thử quyền của runtime identity mà không phải sao chép private key.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| 401 UNAUTHENTICATED | Thiếu token, token hết hạn, credential source sai hoặc token không được API chấp nhận | Kiểm tra ADC source, refresh flow, thời gian hệ thống và loại token |
| 403 PERMISSION_DENIED | Principal xác thực được nhưng thiếu IAM permission | Xác định principal thực tế, kiểm tra IAM policy trên resource và quyền kế thừa |
| 403 dù có role IAM | OAuth scope hoặc Compute Engine access scope không phù hợp | Kiểm tra scope được yêu cầu và access scopes trên VM |
| iam.serviceAccounts.getAccessToken bị từ chối | Source principal thiếu Token Creator trên target service account hoặc IAM Credentials API chưa bật | Kiểm tra role trên đúng target và API ở source project |
| Không thể attach service account | Thiếu iam.serviceAccounts.actAs | Kiểm tra roles/iam.serviceAccountUser trên service account |
| Gọi Cloud Run nhận 401/403 | Dùng access token thay ID token, audience sai hoặc thiếu Invoker | Dùng ID token đúng audience và kiểm tra roles/run.invoker |
| GKE workload không nhận danh tính mong muốn | Workload Identity Federation for GKE hoặc liên kết KSA/GSA chưa đúng | Kiểm tra KSA, provider, binding roles/iam.workloadIdentityUser và metadata server |
| Java chạy local nhưng lỗi trên Cloud Run | Local ADC khác service account runtime | Xác minh service account gắn vào revision và role trên tài nguyên |
| Request đầu chạy được, request sau lỗi | Ứng dụng giữ token tĩnh đã hết hạn | Dùng credential object có refresh thay vì cache chuỗi token |
| Impersonation hoạt động nhưng API đích từ chối | Target service account chưa có role nghiệp vụ hoặc token scope không phù hợp | Kiểm tra IAM của target và scope của token |

Không suy luận principal chỉ từ tên ứng dụng. Trong môi trường có nhiều service account, hãy xác minh danh tính thực tế bằng credential configuration, metadata của workload hoặc audit log phù hợp.

## 13. Kiểm tra audit và quản trị impersonation

Impersonation làm thay đổi principal được dùng để truy cập resource. Vì vậy, tổ chức cần theo dõi cả hai danh tính: source principal nào được phép impersonate và target service account nào được sử dụng.

Các kiểm soát nên có:

- Cấp Token Creator trực tiếp trên service account đích, tránh grant quá rộng.
- Rà soát định kỳ danh sách principal có thể impersonate service account nhạy cảm.
- Giới hạn người có quyền sửa IAM policy của service account.
- Theo dõi audit logs liên quan đến IAM Credentials API và thao tác tài nguyên.
- Ghi nhận lý do, owner và thời hạn cho các quyền impersonation đặc biệt.
- Dùng service account riêng cho từng workload hoặc môi trường.
- Thu hồi quyền impersonation khi không còn nhu cầu.
- Kiểm tra service account key và loại bỏ key không cần thiết.

Service account là ranh giới bảo mật của workload. Người có thể thay đổi IAM policy của service account hoặc impersonate service account đó có thể ảnh hưởng trực tiếp đến tài nguyên mà workload truy cập được.

## 14. Checklist trước khi đưa Java client vào production

### Danh tính và ADC

- [ ] Ứng dụng dùng ADC hoặc credential provider phù hợp với môi trường.
- [ ] Cloud Run/Compute Engine gắn user-managed service account có quyền tối thiểu.
- [ ] GKE workload dùng Workload Identity Federation for GKE.
- [ ] Workload ngoài Google Cloud ưu tiên Workload Identity Federation thay cho key JSON.
- [ ] Không để file key cũ trong GOOGLE_APPLICATION_CREDENTIALS che khuất credential runtime mong muốn.

### IAM và scope

- [ ] IAM role được cấp ở phạm vi resource nhỏ nhất có thể.
- [ ] Đã phân biệt actAs, Token Creator và Workload Identity User.
- [ ] OAuth scopes được chọn theo API method.
- [ ] Không coi cloud-platform scope là quyền Owner hoặc Editor.
- [ ] Nếu chạy trên Compute Engine, access scopes được kiểm tra cùng IAM policy.

### Impersonation và token

- [ ] Source principal chỉ có quyền impersonate target service account cần thiết.
- [ ] IAM Credentials API được bật trong project nguồn.
- [ ] Target service account có role nghiệp vụ trên resource đích.
- [ ] Access token và ID token được dùng đúng mục đích.
- [ ] ID token có audience chính xác và principal có Invoker khi gọi Cloud Run.
- [ ] Token lifetime ngắn và phù hợp với công việc.
- [ ] Java client giữ credential object có khả năng refresh.
- [ ] Không log, lưu hoặc truyền token qua URL.
- [ ] Không dùng self-impersonation hoặc delegation chain nếu không có yêu cầu rõ ràng.

### Spring và vận hành

- [ ] Credential/client được cấu hình và inject qua Spring bean.
- [ ] Client được tái sử dụng thay vì tạo mới mỗi request.
- [ ] Local, staging và production dùng danh tính và resource scope phù hợp.
- [ ] Audit logs và quy trình review IAM được duy trì.
- [ ] Có hướng dẫn xử lý 401, 403, scope mismatch và token expiry.

## 15. Câu hỏi tự kiểm tra

1. Authentication và authorization khác nhau như thế nào khi Java gọi Cloud Storage?
2. Vì sao OAuth scope cloud-platform không cấp cho service account quyền roles/storage.admin?
3. roles/iam.serviceAccountUser khác roles/iam.serviceAccountTokenCreator ở permission và mục đích nào?
4. Khi một Cloud Run service gọi một Cloud Run service riêng tư khác, vì sao thường cần ID token thay vì access token?
5. Trong ImpersonatedCredentials, source principal và target service account đại diện cho điều gì?
6. Vì sao target service account cần IAM role trên resource đích dù source đã có Token Creator?
7. Khi nào nên dùng roles/iam.serviceAccountOpenIdTokenCreator thay cho Token Creator?
8. Vì sao không nên giữ một access token dạng String trong singleton Spring bean suốt vòng đời ứng dụng?
9. Nếu Java chạy trên VM, vì sao cần kiểm tra cả IAM role và access scopes?
10. Workload Identity Federation giúp giảm rủi ro nào so với service account key JSON?

## Tài liệu tham khảo

- [Authentication for Google Cloud APIs and services](https://docs.cloud.google.com/docs/authentication)
- [How Application Default Credentials works](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
- [Authenticate your requests with Java](https://docs.cloud.google.com/java/docs/authentication)
- [Get started with Google Auth Library for Java](https://docs.cloud.google.com/java/getting-started/getting-started-with-google-auth-library)
- [Roles for service account authentication](https://docs.cloud.google.com/iam/docs/service-account-permissions)
- [Use service account impersonation](https://docs.cloud.google.com/docs/authentication/use-service-account-impersonation)
- [Service account impersonation](https://docs.cloud.google.com/iam/docs/service-account-impersonation)
- [Create short-lived credentials for a service account](https://docs.cloud.google.com/iam/docs/create-short-lived-credentials-direct)
- [Restrict service account usage and token lifetime](https://docs.cloud.google.com/organization-policy/restrict-service-accounts)
- [Get an ID token](https://docs.cloud.google.com/docs/authentication/get-id-token)
- [IdTokenCredentials Java reference](https://docs.cloud.google.com/java/docs/reference/google-auth-library/latest/com.google.auth.oauth2.IdTokenCredentials)
- [ImpersonatedCredentials Java reference](https://docs.cloud.google.com/java/docs/reference/google-auth-library/latest/com.google.auth.oauth2.ImpersonatedCredentials)
- [Credential Access Boundary and downscoped tokens](https://docs.cloud.google.com/iam/docs/downscoping-short-lived-credentials)
- [Workload Identity Federation for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)

