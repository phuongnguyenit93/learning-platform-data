# Phân biệt lỗi xác thực, thiếu quyền và API chưa bật

Khi ứng dụng Java/Spring trên Google Cloud gọi Cloud Storage, Secret Manager, BigQuery hay Cloud Run, lỗi thường xuất hiện dưới dạng **401 UNAUTHENTICATED**, **403 PERMISSION_DENIED**, **SERVICE_DISABLED** hoặc một thông báo ngắn như "The caller does not have permission". Tuy cùng ngăn ứng dụng hoàn thành công việc, chúng có nguyên nhân và cách sửa hoàn toàn khác nhau. Nếu chỉ cấp thêm role Owner hoặc bật hàng loạt API để "thử", người vận hành vừa có thể không sửa được sự cố vừa tạo rủi ro bảo mật.

Bài học hướng dẫn cách xác định danh tính thực sự gửi yêu cầu, phân biệt authentication với authorization, tìm project tiêu thụ API, kiểm tra chính sách IAM theo đúng tài nguyên và đọc thông tin lỗi chi tiết. Các ví dụ sử dụng Google Cloud CLI, Cloud Audit Logs và Java client libraries; áp dụng cho Compute Engine, GKE, Cloud Run cũng như môi trường local. Trọng tâm là **thu thập bằng chứng, chỉ sửa nguyên nhân đã xác minh và giữ quyền tối thiểu**.

## 1. Ba nhóm lỗi cần tách riêng

| Nhóm lỗi | Câu hỏi gốc | Triệu chứng thường gặp | Hướng điều tra đầu tiên |
| --- | --- | --- | --- |
| Xác thực (authentication) | Google có xác minh được danh tính của caller không? | Thiếu token, token hết hạn, audience sai, 401 | Nguồn credential, loại token, thời hạn, audience |
| Thiếu quyền (authorization) | Caller đã xác thực có được phép thực hiện thao tác lên resource không? | 403, permission denied, IAM denial | Principal thực, permission cần thiết, IAM policy tại resource |
| API chưa bật (service enablement) | Dịch vụ API có được enable ở consumer project cần thiết không? | 403 kèm SERVICE_DISABLED, API has not been used/enabled | Service name, consumer project, trạng thái Service Usage |

Một lỗi 403 **không đủ** để kết luận thiếu IAM role. Một số API cũng trả 403 khi API chưa bật, VPC Service Controls chặn hoặc organization policy không cho phép thao tác. Cần đọc thông tin lỗi cụ thể, đặc biệt trường reason trong **google.rpc.ErrorInfo** nếu response có cung cấp.

Tương tự, không phải mọi lỗi 401 đều là do "chưa đăng nhập gcloud": runtime chạy trên Cloud Run, GKE hoặc VM có danh tính riêng và có thể hoàn toàn không sử dụng phiên đăng nhập CLI trên laptop.

## 2. Luồng kiểm tra quyết định

~~~mermaid
flowchart TD
  A["Một lời gọi Google API thất bại"] --> B{"DNS / TCP / TLS tới endpoint hoạt động?"}
  B -->|"Không"| NET["Điều tra mạng, DNS, firewall, NAT, proxy"]
  B -->|"Có"| C{"Có status hoặc ErrorInfo?"}
  C -->|"401 / UNAUTHENTICATED"| AUTH["Kiểm tra credential, token và audience"]
  C -->|"403 / SERVICE_DISABLED"| API["Kiểm tra API và consumer project"]
  C -->|"403 / PERMISSION_DENIED"| IAM["Kiểm tra principal, permission và IAM"]
  C -->|"403 / perimeter"| VPC["Kiểm tra VPC Service Controls và chính sách"]
  C -->|"429 / 5xx"| QUOTA["Kiểm tra quota, retry và tình trạng dịch vụ"]
  C -->|"Không rõ"| DETAIL["Đọc error details, log và request metadata"]
  AUTH --> VERIFY["Sửa tối thiểu và thử lại"]
  API --> VERIFY
  IAM --> VERIFY
  VPC --> VERIFY
  QUOTA --> VERIFY
  DETAIL --> VERIFY
~~~

Nếu ứng dụng không thể kết nối TCP/TLS, hãy điều tra đường mạng trước; cấp thêm IAM role không thể sửa DNS timeout. Ngược lại, khi đã nhận một response lỗi có cấu trúc từ Google API, nhiều khả năng request đã tới tầng API, nên cần tìm danh tính, service enablement hoặc policy đúng chỗ.

## 3. Đọc mã lỗi cùng thông tin chi tiết

| HTTP / gRPC | Ý nghĩa thường gặp | Không nên suy đoán |
| --- | --- | --- |
| 401 / UNAUTHENTICATED | Không có credential hợp lệ hoặc token không được chấp nhận | Chưa chắc cần IAM role mới |
| 403 / PERMISSION_DENIED | Yêu cầu bị từ chối bởi quyền hoặc chính sách | Không khẳng định chỉ do thiếu role |
| 403 + SERVICE_DISABLED | API chưa được enable cho consumer tương ứng | Không sửa bằng cách thêm quyền trên bucket/secret |
| 404 / NOT_FOUND | Resource không tồn tại, sai tên hoặc một số API cố ý hạn chế tiết lộ sự tồn tại | Không mặc định là resource thật sự bị xóa |
| 429 / RESOURCE_EXHAUSTED | Quota/rate limit hoặc giới hạn năng lực | Không sửa bằng cách đăng nhập lại |
| 5xx / UNAVAILABLE | Dịch vụ hoặc hạ tầng trung gian gặp lỗi | Không tự kết luận IAM sai |
| DEADLINE_EXCEEDED | Không hoàn tất trong deadline | Cần phân tích mạng, server, retry và thời gian chờ |

Response thực tế có thể khác giữa REST và gRPC. Một Java client có thể ném exception với mã tương ứng thay vì in nguyên JSON HTTP. Đừng chỉ ghi log "call failed"; phải có **service/method, status code, reason, project và resource** để lần theo nguyên nhân.

## 4. Ví dụ ErrorInfo: lỗi API chưa bật

Một response REST có thể chứa cấu trúc tương tự:

~~~json
{
  "error": {
    "code": 403,
    "message": "API has not been used in the consumer project or is disabled.",
    "status": "PERMISSION_DENIED",
    "details": [
      {
        "@type": "type.googleapis.com/google.rpc.ErrorInfo",
        "reason": "SERVICE_DISABLED",
        "domain": "googleapis.com",
        "metadata": {
          "service": "secretmanager.googleapis.com",
          "consumer": "projects/123456789"
        }
      }
    ]
  }
}
~~~

Đây là **ví dụ minh họa**, không phải bản ghi sự cố thực tế. Khi thấy reason là SERVICE_DISABLED, cần xác định **dịch vụ** đang bị từ chối và **consumer** được response chỉ ra. Giá trị consumer có thể là project number chứ không phải project ID dễ đọc.

Không nên bỏ qua các trường này để chỉ nhìn mã 403. Một lỗi IAM permission denied có thể cũng là 403 nhưng không có SERVICE_DISABLED; cách xử lý là khác.

## 5. Xác định caller đang sử dụng danh tính nào

Trên Google Cloud có nhiều nguồn credential. Mỗi nguồn có thể trỏ tới một principal và một project khác nhau:

| Nơi chạy | Danh tính thường dùng | Cạm bẫy |
| --- | --- | --- |
| Laptop, dùng gcloud CLI | Tài khoản đang active trong cấu hình gcloud hoặc service account impersonation | CLI thành công nhưng chương trình Java dùng ADC khác |
| Laptop, dùng Application Default Credentials | Credential do ADC tìm thấy trong môi trường | Credential local cũ, quota project khác |
| Compute Engine | Service account gắn vào VM qua metadata server | VM dùng service account mặc định hoặc OAuth scopes hạn chế |
| Cloud Run | Runtime service account của revision/service | Nhầm với danh tính người deploy hoặc Cloud Build |
| GKE | Workload Identity Federation for GKE hoặc cơ chế credential của workload | Nhầm Kubernetes service account với Google IAM principal |
| CI/CD ngoài GCP | Workload Identity Federation hoặc credential được cấp hợp lệ | Dùng sai audience/provider hoặc impersonation chain |

**Danh tính phát triển** không đồng nghĩa **danh tính runtime**. Ví dụ, người deploy có quyền quản trị Secret Manager nhưng Cloud Run runtime service account chỉ được phép đọc bucket; khi ứng dụng đọc secret, nó vẫn nhận 403.

Trước khi cấp role, phải trả lời: **request thất bại đang được ký bởi principal nào?**

## 6. gcloud auth và ADC là hai hệ thống credential khác nhau

Google Cloud CLI sử dụng cấu hình đăng nhập để gọi API từ các lệnh gcloud. Google Cloud client libraries thường sử dụng **Application Default Credentials (ADC)** theo cơ chế tìm credential của thư viện.

Kiểm tra CLI:

~~~bash
gcloud auth list
gcloud config list
~~~

Hai lệnh trên đọc trạng thái đăng nhập và cấu hình gcloud. Chúng **không chứng minh** một chương trình Java chạy tại cùng máy đang dùng credential đó.

ADC có thể tìm credential theo thứ tự phụ thuộc thư viện và môi trường, thường bao gồm:

1. Biến môi trường **GOOGLE_APPLICATION_CREDENTIALS**, nếu được thiết lập tới credential configuration phù hợp.
2. Tệp ADC được tạo ở môi trường phát triển.
3. Credential do runtime cung cấp qua metadata service khi chạy trên Google Cloud được hỗ trợ.

Không được mặc định mọi giá trị của GOOGLE_APPLICATION_CREDENTIALS là một service account JSON key; nó cũng có thể trỏ tới cấu hình Workload Identity Federation. Tránh sử dụng khóa service account dài hạn nếu có thể dùng identity liên kết hoặc impersonation ngắn hạn.

Một bài kiểm tra có giá trị là chạy chính đoạn code xác định credential trong cùng container/VM hoặc environment đang lỗi, nhưng **không in access token hay nội dung credential ra log**.

## 7. OAuth access token, ID token và API key

Ba kiểu thông tin thường bị lẫn:

| Loại | Dùng cho | Sai lầm thường gặp |
| --- | --- | --- |
| OAuth 2.0 access token | Gọi Google APIs yêu cầu OAuth, theo scopes và quyền của principal | Gửi token hết hạn hoặc không có scope thích hợp |
| OpenID Connect ID token | Chứng minh danh tính cho đối tượng nhận có kiểm tra audience, ví dụ một service Cloud Run yêu cầu xác thực | Dùng ID token gọi Google API cần access token |
| API key | Một số API hỗ trợ định danh project/ứng dụng và quota hoặc kiểu truy cập cho phép key | Coi API key là quyền IAM đọc dữ liệu riêng |

Một ID token có thể hợp lệ về chữ ký nhưng bị từ chối vì **audience** không khớp dịch vụ nhận. Một access token có thể hợp lệ nhưng caller thiếu permission trên resource. API key không thay thế IAM cho những thao tác riêng tư cần xác thực user/service account.

Không đưa bất kỳ token, API key hay private key nào vào screenshot, ticket hoặc log công khai. Khi kiểm tra token, ưu tiên thông tin trạng thái và principal an toàn thay vì xuất credential nguyên văn.

## 8. Lỗi xác thực 401: quy trình điều tra

Khi nhận 401 hoặc UNAUTHENTICATED:

1. Xác định API endpoint và phương thức gọi: REST, gRPC, client library hay proxy.
2. Xác định thư viện đang sử dụng ADC, credential cấu hình tường minh hay một API key.
3. Kiểm tra runtime có tiếp cận được nguồn credential hợp lệ không; ví dụ metadata service trên VM/Cloud Run.
4. Xác minh loại token phù hợp: access token cho Google API hoặc ID token với audience chính xác cho service nhận.
5. Kiểm tra token expiry, clock skew và cơ chế refresh; tránh cache token thủ công vượt thời hạn.
6. Với Workload Identity Federation, xem audience, provider, subject mapping và chuỗi impersonation nếu có.
7. Thử lại cùng một thao tác nhỏ, không phá dữ liệu; sau đó mới kiểm tra quyền trên resource nếu xuất hiện 403.

Nếu ứng dụng không lấy được token, root cause có thể xuất hiện **trước khi request đến Google API**. Ví dụ lỗi ADC không tìm thấy credential sẽ thành exception ở Java; API có thể chưa nhận request nào. Đừng ghi nhận đó là "Google API trả 401" nếu thực tế chưa có HTTP response.

## 9. Lỗi thiếu quyền 403: cần biết permission chính xác

IAM hoạt động theo mô hình principal, permission, resource và chính sách. Role là tập hợp permission; thiếu một permission cụ thể không có nghĩa cần cấp role rất rộng.

Ví dụ:

| Tác vụ | Permission tiêu biểu | Phạm vi cấp quyền cần xem |
| --- | --- | --- |
| Đọc object Cloud Storage | storage.objects.get | Bucket hoặc phạm vi tài nguyên phù hợp |
| Liệt kê object | storage.objects.list | Bucket hoặc phạm vi phù hợp |
| Đọc phiên bản secret | secretmanager.versions.access | Secret, project hoặc phạm vi phù hợp |
| Tạo BigQuery query job | bigquery.jobs.create | Project chạy job |
| Đọc dữ liệu BigQuery | Permission đọc table/dataset phù hợp | Dataset/table hoặc IAM model của dịch vụ |
| Triển khai Cloud Run | Các quyền quản trị Cloud Run phù hợp | Service/project cùng quyền sử dụng runtime identity |

Đây là các permission minh họa; một SDK operation có thể cần thêm permission để lấy metadata, liệt kê hoặc tạo tài nguyên khác. Cần tra quyền chính xác theo method và đọc thông điệp lỗi trước khi sửa IAM.

**Resource boundary quan trọng.** Người dùng có role trên project A không mặc nhiên có quyền đọc bucket thuộc project B. Một tài nguyên có policy riêng có thể không hiển thị đầy đủ khi chỉ xem IAM policy tại project.

## 10. Quan hệ giữa IAM allow, deny, conditions và boundary

Một permission có thể vẫn bị từ chối dù người dùng thấy một role liên quan:

- Role được gán cho **principal khác** hoặc group membership chưa áp dụng như dự kiến.
- Role gán trên **project khác**, bucket khác hoặc service account khác.
- Binding có **IAM Condition** không thỏa mãn (thời gian, resource, thuộc tính).
- **IAM Deny policy** áp dụng ở phạm vi liên quan và từ chối permission.
- **Principal Access Boundary** hoặc một giới hạn truy cập có liên quan hạn chế tài nguyên.
- Organization policy hoặc quy tắc của chính dịch vụ chặn thao tác dù IAM allow.
- Resource đã thay đổi, sai tên, hoặc API trả lỗi không đầy đủ để tránh tiết lộ thông tin.

Hãy đánh giá **effective access** thay vì chỉ tìm tên role trong một bảng. Trên Google Cloud có công cụ **Policy Troubleshooter for IAM** để phân tích một principal, permission và resource theo phạm vi hỗ trợ. Kết quả của nó cần được đối chiếu với điều kiện thời điểm xảy ra sự cố, group membership, policies và error details.

Không gỡ Deny/Condition hay thêm Owner chỉ vì có một role "có vẻ đúng". Cần xác định policy đang có hiệu lực và lý do nó từ chối.

## 11. API chưa bật: phân biệt quyền sử dụng và quyền bật API

Để gọi nhiều Google APIs, dịch vụ tương ứng phải được **enable** cho project tiêu thụ API theo quy tắc của dịch vụ. Việc có permission trên một bucket/secret không thay thế bước bật API.

Kiểm tra các API đã bật trong consumer project:

~~~bash
gcloud services list --enabled \
  --project=CONSUMER_PROJECT_ID
~~~

Ví dụ service names thường gặp:

~~~text
storage.googleapis.com
secretmanager.googleapis.com
run.googleapis.com
bigquery.googleapis.com
artifactregistry.googleapis.com
compute.googleapis.com
~~~

Đây là tên dịch vụ để đối chiếu, **không phải** danh sách yêu cầu bật toàn bộ cho mọi ứng dụng. Bật API nào phụ thuộc việc ứng dụng thực sự sử dụng API đó và yêu cầu tổ chức.

Quyền **gọi API** khác quyền **bật API**. Việc bật một API thường yêu cầu permission như serviceusage.services.enable hoặc role phù hợp, ví dụ Service Usage Admin, theo phạm vi kiểm soát của tổ chức. Không cấp quyền quản trị Service Usage cho runtime chỉ để ứng dụng tự bật API khi chạy.

Khi xác định đúng API chưa bật, tạo yêu cầu thay đổi và để người có thẩm quyền enable ở đúng consumer project. Sau đó xác nhận trạng thái đã thay đổi và thử lại. Không dùng một project bất kỳ trong CLI chỉ vì nó là project mặc định trên laptop.

## 12. Ba khái niệm project dễ bị nhầm

Trong một lời gọi API có thể xuất hiện nhiều project:

| Project | Vai trò | Ví dụ |
| --- | --- | --- |
| Resource project | Chứa tài nguyên được truy cập | Bucket/secret/dataset thuộc project dữ liệu |
| Credential project | Liên quan đến principal hoặc nguồn credential | Project tạo service account |
| Consumer/quota project | Project dùng cho việc nhận diện consumer, quota/billing/service enablement theo API | Project được yêu cầu trong ErrorInfo |

Chúng có thể giống nhau, nhưng không bắt buộc. Ví dụ, ứng dụng Cloud Run ở project ứng dụng gọi Secret Manager secret nằm trong project bảo mật, bằng runtime service account thuộc project ứng dụng. API có thể dùng project tiêu thụ xác định theo credential/request/quota project tùy dịch vụ.

Khi ErrorInfo có metadata consumer, **ưu tiên kiểm tra đúng project đó** thay vì đoán từ project chứa tài nguyên. Đừng tự chuyển quota project để "né" API enable hoặc chính sách; thay đổi consumer có thể làm thay đổi quota, billing và yêu cầu IAM.

## 13. Quota project trong Application Default Credentials

Credential ADC của người dùng local có thể có **quota project** riêng. Một lỗi trong quá trình gọi API có thể liên quan đến project được dùng cho quota/billing hoặc quyền sử dụng project đó, không phải quyền đọc tài nguyên chính.

Những dấu hiệu:

- Lời gọi gcloud thành công nhưng Java client local lỗi, hoặc ngược lại.
- Thông báo nhắc đến consumer project hoặc quota project không đúng môi trường mong đợi.
- Một số API yêu cầu quota project rõ ràng khi dùng user ADC.
- Principal thiếu quyền sử dụng project để tính quota, chẳng hạn serviceusage.services.use khi áp dụng.

Trước khi điều chỉnh, hãy ghi nhận cấu hình hiện tại và xác định project nào được cấp phép làm consumer. Có thể sử dụng cấu hình ADC quota project theo hướng dẫn của Google Cloud, nhưng thao tác này làm thay đổi môi trường phát triển và phải được thực hiện có chủ đích.

Không tải service account key để né lỗi quota project. Cách an toàn hơn thường là dùng identity được quản lý, impersonation hoặc Workload Identity Federation phù hợp với chính sách.

## 14. Compute Engine: service account và OAuth scopes

VM có thể gắn service account và OAuth access scopes. Tại một số đường gọi API từ VM, **quyền hữu hiệu** bị giới hạn bởi cả IAM permissions và scopes đã cấu hình.

Lệnh xem VM (chỉ đọc):

~~~bash
gcloud compute instances describe VM_NAME \
  --project=PROJECT_ID \
  --zone=ZONE \
  --format="yaml(name,serviceAccounts,networkInterfaces)"
~~~

Ví dụ một VM có role cho phép đọc Cloud Storage nhưng scopes giới hạn hơn mức cần thiết; caller vẫn có thể gặp lỗi. Ngược lại, scope cloud-platform rộng **không tự cấp Owner**: IAM vẫn quyết định quyền trên resource.

Kiểm tra đúng danh tính thực thi ứng dụng, vì một chương trình có thể dùng GOOGLE_APPLICATION_CREDENTIALS thay vì service account của VM. Không tự động thay scopes hoặc cấp role rộng trước khi xác nhận đường credential mà code đang sử dụng.

## 15. Cloud Run: tách danh tính deploy, build và runtime

Cloud Run thường có ít nhất ba nhóm principal:

1. Người hoặc pipeline **deploy** revision/service.
2. Danh tính **build** image (ví dụ service account của Cloud Build nếu build bằng Cloud Build).
3. **Runtime service account** được gắn với Cloud Run service/revision khi container chạy.

Khi một Java API trên Cloud Run không đọc được secret, hãy kiểm tra runtime service account trước. Service account của người deploy hay Cloud Build có quyền đọc secret không đồng nghĩa runtime có quyền đó.

Xem cấu hình service:

~~~bash
gcloud run services describe SERVICE_NAME \
  --project=PROJECT_ID \
  --region=REGION \
  --format=yaml
~~~

Đối chiếu revision hiện đang nhận traffic và danh tính được dùng trong revision đó. Nếu ứng dụng sử dụng ADC mặc định, nó thường lấy credential qua runtime metadata service theo cơ chế Cloud Run; nếu code đặt credential tường minh, phải kiểm tra đường đó.

**Lỗi deploy với iam.serviceAccounts.actAs** là vấn đề khác lỗi runtime đọc secret. Quyền Service Account User/actAs cho phép deployer gán service account trong điều kiện hỗ trợ; nó không tự cấp quyền Secret Manager cho danh tính runtime. Quyền impersonation tạo token cũng có cơ chế permission riêng, không nên đánh đồng.

## 16. GKE: Kubernetes service account và Google IAM principal

Trên GKE, Pod có thể sử dụng **Workload Identity Federation for GKE** để truy cập Google Cloud APIs mà không cần phân phối service account key. Tùy mô hình, workload có thể được nhận diện trực tiếp bằng principal liên kết với Kubernetes service account (KSA) hoặc dùng mô hình impersonation một IAM service account (GSA) được cấu hình hợp lệ.

Khi Pod nhận 401/403:

1. Xác định namespace, tên Pod và Kubernetes service account được gắn vào Pod.
2. Kiểm tra Workload Identity Federation đang được bật/cấu hình phù hợp cho cluster và node pool khi áp dụng.
3. Xác định principal thực tế gọi API là KSA identity hay GSA được impersonate.
4. Kiểm tra điều kiện liên kết/cho phép impersonation và role trên tài nguyên đích.
5. Kiểm tra API enable ở consumer project và VPC Service Controls nếu có.
6. Đối chiếu Pod mới/cũ sau thay đổi cấu hình và cách SDK lấy credential.

Lệnh chỉ đọc:

~~~bash
kubectl get pod POD_NAME -n NAMESPACE \
  -o jsonpath="{.spec.serviceAccountName}"

kubectl get serviceaccount KSA_NAME -n NAMESPACE -o yaml
~~~

Một annotation của KSA (nếu mô hình đó dùng annotation) không tự bảo đảm việc impersonation và IAM binding đã chính xác. Cần xác minh token flow và permission thực tế.

Không chép service account JSON key vào Kubernetes Secret để chữa lỗi Workload Identity nếu chưa đánh giá rủi ro và không có yêu cầu bắt buộc. Credential ngắn hạn và liên kết danh tính thường an toàn hơn.

## 17. Java client: phân loại exception thay vì nuốt lỗi

Các Java client libraries thường tự tìm ADC. Ví dụ đoạn mã đọc metadata object Cloud Storage và phân loại response:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageException;
import com.google.cloud.storage.StorageOptions;

public class InspectStorageAccess {
  public static void inspect(String bucket, String objectName) {
    Storage storage = StorageOptions.getDefaultInstance().getService();
    try {
      Blob blob = storage.get(BlobId.of(bucket, objectName));
      if (blob == null) {
        System.out.println("Không tìm thấy object hoặc response rỗng");
        return;
      }
      System.out.println("Object size: " + blob.getSize());
    } catch (StorageException e) {
      int code = e.getCode();
      if (code == 401) {
        System.err.println("AUTHENTICATION: kiểm tra ADC/token");
      } else if (code == 403) {
        System.err.println("FORBIDDEN: cần phân tích ErrorInfo, IAM, API enable và VPC SC");
      } else if (code == 429) {
        System.err.println("QUOTA/RATE LIMIT: kiểm tra giới hạn và retry");
      } else {
        System.err.println("Cloud Storage error code: " + code);
      }
    }
  }
}
~~~

Ví dụ minh họa cách nhóm lỗi, **không phải ứng dụng hoàn chỉnh**. StorageException có thể không cung cấp toàn bộ ErrorInfo dưới dạng dễ đọc; khi cần xác định SERVICE_DISABLED so với IAM denial, kiểm tra exception details, response được thư viện hỗ trợ hoặc log phía dịch vụ.

Nếu ADC thất bại trước khi tạo request, có thể xuất hiện exception từ quá trình tạo/lấy credentials mà không đi qua catch StorageException trong đoạn mã trên. Production code cần log root cause an toàn, không ghi token hoặc nội dung JSON key; cần thiết kế retry theo loại lỗi và không retry liên tục 401/403.

## 18. Cloud Audit Logs giúp xác minh principal và permission

Audit logs có thể ghi:

- **authenticationInfo:** danh tính caller mà dịch vụ quan sát được.
- **authorizationInfo:** những permission/resource được kiểm tra và kết quả cho phép/từ chối khi có.
- **serviceName, methodName:** API và phương thức.
- **status:** kết quả hoặc mã lỗi.
- **resourceName:** tài nguyên được truy cập theo phạm vi hỗ trợ.

Bộ lọc tham khảo trong Logs Explorer:

~~~text
protoPayload.serviceName="secretmanager.googleapis.com"
protoPayload.status.code=7
~~~

Ở đây status code 7 theo gRPC tương ứng PERMISSION_DENIED trong những bản ghi sử dụng trường status như vậy. Tùy API, resource type, log type và phiên bản, tên trường/mã có thể khác; hãy xem một log thực tế thay vì giả định bộ lọc này bao phủ mọi lỗi.

**Data Access audit logs có thể cần được bật** cho loại dịch vụ và hoạt động tương ứng, đồng thời người điều tra cần có quyền xem log. Không thấy log không chứng minh request chưa từng được gửi: có thể bị lỗi trước API, log chưa bật, quyền xem thiếu hoặc đang nhìn sai project.

## 19. Kiểm tra IAM policy với CLI mà không sửa quyền

Ví dụ kiểm tra project IAM:

~~~bash
gcloud projects get-iam-policy RESOURCE_PROJECT_ID \
  --format=yaml
~~~

Kết quả có thể dài. Hãy tìm role, principal và condition liên quan, đồng thời tránh chia sẻ toàn bộ policy ngoài phạm vi cho phép. **Project IAM không thể hiện đầy đủ mọi IAM binding cấp bucket/secret/dataset hoặc mọi deny/condition ở cấp cha**.

Xem thông tin service account:

~~~bash
gcloud iam service-accounts describe \
  RUNTIME_SA@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID
~~~

Đây chỉ xác nhận service account tồn tại và một số metadata; nó **không chứng minh** service account có quyền trên resource đích.

Đối với một principal/permission/resource cụ thể, sử dụng Policy Troubleshooter hoặc các công cụ kiểm tra quyền theo dịch vụ để tìm policy được kế thừa, conditions và deny. Không chỉ grep tên role rồi kết luận đã đủ quyền.

## 20. Phân biệt thiếu IAM permission với VPC Service Controls

**VPC Service Controls (VPC SC)** tạo thêm ranh giới truy cập với các dịch vụ được hỗ trợ, nhằm giảm nguy cơ đưa dữ liệu vượt khỏi phạm vi cho phép. Một caller có IAM permission đầy đủ vẫn có thể bị VPC SC từ chối nếu request không đáp ứng ingress/egress rules hoặc những điều kiện khác của perimeter.

Dấu hiệu nên kiểm tra:

- Response nhắc đến service perimeter, VPC Service Controls hoặc violation identifier khi được cung cấp.
- Chỉ request từ môi trường ngoài perimeter thất bại, còn từ workload trong perimeter hoạt động.
- Caller và resource đều đúng IAM nhưng yêu cầu cross-project/cross-perimeter bị từ chối.
- Audit logs hoặc violation logs có thông tin tương ứng theo khả năng logging và quyền xem.

Để sửa, xác định perimeter, service, source, target, identity, ingress/egress policy và yêu cầu nghiệp vụ. Phân tích violation và xây dựng thay đổi nhỏ nhất, có review bảo mật. **Không tắt VPC SC hoặc đổi sang endpoint khác để né perimeter** khi đó là kiểm soát bắt buộc.

VPC SC và IAM cùng phải thỏa mãn; một cái cho phép không đồng nghĩa cái còn lại tự cho phép.

## 21. API disabled so với permission denied: một tình huống thực tế

**Bối cảnh:** ứng dụng Cloud Run ở project app-prod dùng runtime service account để đọc phiên bản secret trong project sec-prod.

Kịch bản A — API disabled:

- Error details chứa SERVICE_DISABLED với consumer project cụ thể.
- Service Usage tại consumer cho thấy Secret Manager API chưa bật.
- Dù runtime có role Secret Manager Secret Accessor trên secret, lời gọi vẫn bị chặn trước khi thao tác được thực hiện.
- Cách xử lý: xác nhận consumer và xin người được ủy quyền bật API, rồi thử lại.

Kịch bản B — thiếu quyền:

- API đã bật cho consumer nhưng request bị từ chối do principal không có secretmanager.versions.access tại secret tương ứng.
- Audit/error details xác nhận danh tính runtime và resource.
- Cách xử lý: cấp permission/role phù hợp ở phạm vi nhỏ nhất được tổ chức cho phép, rồi thử lại.

Kịch bản C — xác thực thất bại:

- App bị thay credential config hoặc sử dụng ID token sai loại khi gọi Secret Manager API.
- Client không có access token hợp lệ hoặc không thể refresh credential.
- Cách xử lý: sửa đường ADC/token flow, không bắt đầu bằng thêm IAM role.

Kịch bản D — VPC SC:

- Credential hợp lệ, role đúng, API đã bật nhưng request đi từ nguồn không đáp ứng perimeter rules.
- Cách xử lý: điều tra violation và thiết kế ingress/egress rule đúng chính sách.

Đây là **bốn tình huống độc lập**, dù người dùng cuối có thể chỉ nhìn thấy một thông báo chung "Không tải được cấu hình".

## 22. Case study: CLI thành công, chương trình Java thất bại

Một kỹ sư chạy lệnh gcloud thành công trên laptop, nhưng Java application dùng cùng bucket lại nhận 403.

Những giả thuyết cần kiểm chứng:

1. gcloud CLI dùng tài khoản A, Java ADC dùng tài khoản B hoặc một file credential khác.
2. Java ADC có quota project không đúng, hoặc API enable ở consumer của Java khác consumer của CLI.
3. Chương trình chạy trong IDE/Docker và GOOGLE_APPLICATION_CREDENTIALS khác terminal.
4. SDK gọi một operation khác với CLI, cần permission bổ sung.
5. Java program truy cập bucket khác, project khác hoặc resource path sai.
6. Có VPC SC, IAM condition hoặc proxy theo môi trường khác nhau.

**Quy trình:** ghi danh tính CLI đang active, môi trường thực thi Java, đường credential ADC, consumer/quota project, cùng API method và resource. So sánh các yếu tố này trước khi sửa IAM. Không kết luận Java client library bị lỗi chỉ vì hai cách gọi khác kết quả.

## 23. Case study: deploy Cloud Run thành công, runtime lỗi

Pipeline triển khai Cloud Run service thành công; khi request đầu tiên đến, ứng dụng trả 500 vì không lấy được secret.

Điều tra:

- Build và deploy logs cho thấy pipeline hoàn tất nhưng không chứng minh quyền runtime.
- Xem runtime service account của revision đang nhận traffic.
- Từ lỗi Java, xác định 401/403/SERVICE_DISABLED hoặc lỗi network.
- Nếu 403, kiểm tra role trên **secret đích**, không chỉ IAM tại project chứa Cloud Run.
- Nếu SERVICE_DISABLED, kiểm tra consumer project được ErrorInfo chỉ ra.
- Nếu lỗi thay đổi theo revision, so sánh runtime identity, environment, secret references và cấu hình ADC.

Sửa đúng runtime principal hoặc cấu hình môi trường, sau đó kiểm tra một revision canary trước khi chuyển toàn bộ traffic. Không cấp quyền Secret Manager cho service account Cloud Build để chữa lỗi runtime nếu đó không phải principal gọi API.

## 24. Case study: GKE chỉ một namespace bị 403

Hai namespace trong cùng cluster gọi một Google API; namespace A thành công, namespace B bị 403.

Gợi ý kiểm tra:

- Hai Pod có thực sự dùng cùng Kubernetes service account không?
- Principal liên kết với KSA/GSA có giống nhau không?
- IAM binding có giới hạn theo namespace, principal hoặc resource không?
- Namespace B có NetworkPolicy hoặc egress khác (nếu request thực sự timeout thì đây là hướng đáng kiểm tra)?
- Trường ErrorInfo báo IAM denial, API disabled hay policy perimeter?
- Cấu hình Workload Identity Federation có nhất quán giữa node pools và workload không?

Nếu B trả 403 từ API, chỉ khác NetworkPolicy thường không phải nguyên nhân trực tiếp của quyền truy cập; ưu tiên kiểm tra principal, IAM và policy. Nếu B timeout trước HTTP, quay lại DNS/egress. Không thay network policy và role cùng lúc.

## 25. Phân quyền tối thiểu khi sửa lỗi

Một quyết định sửa quyền nên được viết dưới dạng:

> Principal P cần permission X để thực hiện method M trên resource R trong khoảng điều kiện C.

Thay vì:

> Ứng dụng bị 403, cấp Owner để hết lỗi.

Quy trình sửa:

1. Lấy principal thực từ lỗi/log và xác nhận nguồn credential.
2. Xác định API method, resource và permission bị từ chối.
3. Xem quyền đã có và policy cấp cha, resource-level, conditions, deny.
4. Chọn predefined role nhỏ nhất đáp ứng yêu cầu; dùng custom role khi có quy trình phù hợp.
5. Cấp đúng resource scope, ghi ticket/phê duyệt và thời hạn nếu là quyền tạm.
6. Thử lại operation thật, kiểm tra log và hiệu lực của policy.
7. Không giữ role rộng tạm thời sau khi incident được đóng.

Nếu có lỗi do API chưa bật, người sửa nên là chủ sở hữu cấu hình Service Usage, không phải runtime service account. Tương tự, nếu token sai audience thì đổi role không tạo access token hợp lệ.

## 26. Không retry vô hạn lỗi 401/403

Lỗi xác thực và phân quyền thường không phải lỗi tạm thời có thể sửa bằng retry dồn dập. Retry vô hạn có thể gây:

- Tăng log và chi phí quan sát, che khuất request gây lỗi gốc.
- Tăng tải hệ thống phụ trợ và latency người dùng.
- Lặp lại side effect trong các luồng có thao tác ghi.
- Khó phân biệt lỗi đã được sửa với lỗi do credential cache chưa làm mới.

Nên phân loại:

| Lỗi | Hướng xử lý |
| --- | --- |
| Token hết hạn, thư viện có thể refresh | Để SDK refresh theo cơ chế hỗ trợ, giới hạn retry |
| Credential bị sai cấu hình | Sửa credential source, không retry vô hạn |
| IAM permission denied | Dừng/quản lý lỗi; chỉ thử lại sau khi policy hợp lệ |
| API disabled | Đợi quy trình enable hợp lệ, xác nhận trạng thái rồi thử lại |
| 429 hoặc 5xx tạm thời | Retry có giới hạn với backoff/jitter nếu API operation an toàn |

Ghi rõ error category trong metrics để một đợt permission denied không bị tính nhầm là sự cố mạng. Với những operation có side effect, áp dụng idempotency hoặc cơ chế kiểm soát trùng lặp khi được dịch vụ hỗ trợ.

## 27. Kịch bản kiểm thử sau khi khắc phục

Khi điều chỉnh IAM hoặc enable API, không chỉ thử một lệnh đơn giản rồi kết luận ứng dụng đã hồi phục. Xác minh theo những tầng:

1. **Credential:** ứng dụng lấy được credential hợp lệ và không phải credential local vô tình được gắn vào runtime.
2. **API enabled:** service phù hợp được bật trong consumer project đã xác định.
3. **Authorization:** principal có permission đúng resource và điều kiện.
4. **API response:** operation thực tế thành công, không phải chỉ kết nối TCP/TLS.
5. **Nghiệp vụ:** giá trị trả về đúng, không có dữ liệu riêng tư bị cấp quyền ngoài dự kiến.
6. **Giám sát:** 401/403 không tiếp tục tăng, không xuất hiện lỗi mới do thay đổi policy.
7. **Hồi quy:** một workflow liên quan vẫn hoạt động và audit logs đủ để điều tra lại.

Với nhiều revision/pod/VM, cần xác minh danh tính ở từng nhóm đang phục vụ traffic. Một instance cũ có thể vẫn dùng credential/config khác với instance vừa khởi động.

## 28. Bảng runbook điều tra 401/403/SERVICE_DISABLED

| Bước | Câu hỏi | Bằng chứng mong đợi | Nếu thất bại |
| --- | --- | --- | --- |
| 1. Xác định request | API, method, resource nào? | Endpoint, timestamp, request/correlation ID | Thu thập log ứng dụng trước |
| 2. Phân loại lỗi | 401, 403, 429, 5xx hay network? | HTTP/gRPC status, ErrorInfo | Đừng sửa policy khi chưa biết nhóm |
| 3. Xác định credential | ADC, runtime SA, WIF hay user token? | Principal và loại credential | Sửa auth flow khi sai |
| 4. Kiểm tra consumer | Project nào tiêu thụ API/quota? | ErrorInfo, client config | Đối chiếu project |
| 5. Kiểm tra API enable | Đúng service có enabled không? | Service Usage status | Xin enable đúng project nếu thiếu |
| 6. Kiểm tra IAM | Permission trên đúng resource có hiệu lực không? | IAM allow/deny, condition, Policy Troubleshooter | Cấp role tối thiểu hoặc sửa policy có căn cứ |
| 7. Chính sách bổ sung | VPC SC, org policy, scopes có chặn không? | Violation/error details | Sửa trong quy trình security |
| 8. Verify | Operation và chức năng đã hồi phục? | Response, log và test nghiệp vụ | Tiếp tục phân tích root cause |
| 9. Đóng incident | Có để lại quyền rộng hay secret? | Change record, IaC, audit | Thu hồi quyền tạm và cập nhật runbook |

## 29. Bài thực hành: ba lỗi trên Secret Manager

**Tình huống:** một ứng dụng Spring Boot cần đọc secret thuộc một project thử nghiệm. Hãy phân biệt ba dạng sự cố bằng môi trường được phê duyệt, không thay đổi project production.

Nhiệm vụ:

1. Ghi tên service, project, secret giả và runtime service account của ứng dụng.
2. Chạy baseline thành công và ghi mã response, thời gian, principal (không lưu token).
3. Tạo một trường hợp credential không hợp lệ **trong môi trường test cô lập**, xác nhận lỗi authentication hoặc thất bại trước request.
4. Khôi phục credential, dùng identity hợp lệ nhưng thiếu quyền đọc secret; ghi lại permission denied.
5. Kiểm tra service enablement trên consumer project thử nghiệm; nếu môi trường cho phép mô phỏng API disabled, dùng đúng quy trình thay đổi được duyệt thay vì tắt API chung của đội.
6. Với mỗi trường hợp, điền HTTP/gRPC code, ErrorInfo reason nếu có, principal, consumer và biện pháp khắc phục tối thiểu.
7. Thử lại bằng ứng dụng Java để đảm bảo ADC, network và IAM đều đúng.
8. Kiểm tra log/audit và xác minh không còn binding tạm hoặc credential thử nghiệm sau bài.

Không chủ động vô hiệu hóa một API được các ứng dụng khác dùng. Khi không thể mô phỏng SERVICE_DISABLED an toàn, dùng một ví dụ response giả lập để thực hành phân loại lỗi, nêu rõ đó là mock.

**Kết quả cần nộp:** ma trận ba lỗi, bảng xác định principal/consumer/resource, output gcloud kiểm tra chỉ đọc đã ẩn dữ liệu nhạy cảm, quyết định IAM hoặc API enable và runbook rollback.

## 30. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Thấy 403 là thêm Owner | Vượt quyền, vẫn có thể lỗi API disabled/VPC SC | Đọc ErrorInfo và tìm đúng policy |
| Gộp 401 và 403 thành "thiếu quyền" | Sửa sai lớp, credential vẫn không hợp lệ | Kiểm tra xác thực trước, phân quyền sau |
| Chỉ kiểm tra gcloud account | Java ADC/runtime dùng danh tính khác | Kiểm tra credential ở đúng process |
| Bật API trong project chứa resource theo phỏng đoán | Consumer thực vẫn chưa enabled | Dùng consumer từ error/config |
| Không xét quota project | Lỗi serviceusage.services.use hoặc dùng consumer sai | Xác định quota project và quyền tương ứng |
| Cho rằng scope cloud-platform cấp tất cả quyền | API vẫn từ chối IAM | Phân biệt scope và resource permissions |
| Cho người deploy quyền đọc secret thay runtime SA | Cloud Run vẫn lỗi khi chạy | Tách deploy/build/runtime identities |
| Xem KSA là GSA trong mọi GKE cluster | Gán quyền cho sai principal | Xác định WIF identity và cách ánh xạ thực |
| Bỏ qua IAM deny/conditions | Role nhìn có vẻ đúng nhưng request vẫn bị chặn | Dùng effective access và policy troubleshooting |
| Tắt VPC SC để sửa 403 | Phá ranh giới bảo mật dữ liệu | Phân tích violation và điều chỉnh policy tối thiểu |
| Ghi token vào log để debug | Lộ credential | Chỉ ghi metadata an toàn |
| Retry 401/403 vô hạn | Tăng chi phí, không giải quyết lỗi cấu hình | Phân loại, dừng và sửa nguyên nhân |

## 31. Checklist trước khi đóng sự cố

- Đã ghi API/method, project, resource, thời gian và mã lỗi chính xác.
- Đã đọc ErrorInfo reason/metadata hoặc thông tin tương đương nếu API cung cấp.
- Đã phân biệt lỗi network với response từ Google API.
- Đã xác định đúng principal ở runtime, không suy đoán từ gcloud auth list.
- Đã kiểm tra loại token, expiry, audience và credential source khi là lỗi 401.
- Đã phân biệt CLI credentials, ADC, metadata service và Workload Identity Federation.
- Đã xác định resource project, credential project và consumer/quota project.
- Đã kiểm tra API enable ở consumer thực, không bật hàng loạt API không dùng.
- Đã kiểm tra permission tối thiểu, scope của binding và điều kiện IAM khi là lỗi 403.
- Đã đối chiếu deny, Principal Access Boundary, organization policy, VPC SC khi liên quan.
- Đã phân biệt service account của người deploy, Cloud Build và runtime Cloud Run.
- Đã xác minh KSA/GSA/Workload Identity trên GKE theo mô hình đang dùng.
- Đã kiểm tra OAuth scopes trên VM khi phù hợp, không xem chúng thay IAM.
- Đã sử dụng audit logs/Policy Troubleshooter đúng phạm vi và biết giới hạn log.
- Không cấp Owner/Editor hoặc tắt perimeter để "thử nhanh".
- Sau khi sửa, operation thật và hành trình nghiệp vụ đã hoạt động ổn định.
- Không còn token, khóa hoặc IAM binding tạm thời không được phép.
- Có bản ghi root cause, thay đổi IaC, kiểm thử hồi quy và người chịu trách nhiệm.

Để xử lý lỗi Google APIs hiệu quả, hãy đi theo thứ tự **credential hợp lệ → API được enable cho consumer phù hợp → IAM permission và các chính sách cho phép → kết quả nghiệp vụ đúng**. Cùng là lỗi 403 nhưng SERVICE_DISABLED, thiếu IAM và VPC Service Controls denial đòi hỏi những người xử lý và thay đổi khác nhau. Khi thu thập đúng principal, project, permission và ErrorInfo trước khi sửa, đội vận hành có thể khôi phục hệ thống nhanh hơn mà không đánh đổi bảo mật, khả năng kiểm toán hay tính ổn định của hạ tầng Google Cloud.
