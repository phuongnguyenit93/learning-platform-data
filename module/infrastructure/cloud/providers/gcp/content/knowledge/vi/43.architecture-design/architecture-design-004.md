# Kiến trúc microservices và service-to-service authentication

Một ứng dụng thương mại điện tử chạy trên Google Cloud có thể bắt đầu như một dịch vụ Java/Spring Boot duy nhất. Khi hệ thống phát triển, chức năng quản lý đơn hàng, thanh toán, tồn kho, thông báo và báo cáo có nhịp thay đổi và yêu cầu mở rộng khác nhau. Tách chúng thành microservices giúp các nhóm triển khai độc lập, nhưng đồng thời làm tăng số kết nối giữa các thành phần và tạo thêm bề mặt tấn công: dịch vụ nào được phép gọi dịch vụ nào, bằng danh tính gì, trong hoàn cảnh nào và cách xử lý khi một dependency lỗi?

**Service-to-service authentication** là cơ chế xác minh danh tính của dịch vụ gọi trước khi chấp nhận yêu cầu từ dịch vụ khác. Trên Google Cloud, mô hình này thường sử dụng **workload identity**, service accounts, IAM, Google-signed OpenID Connect ID tokens, và trong một số kiến trúc GKE, mutual TLS (mTLS) qua service mesh. Để an toàn, cần kết hợp thêm **authorization**, bảo vệ network, quản lý secrets và quan sát được hành vi giữa các dịch vụ.

Bài học hướng dẫn thiết kế microservices, triển khai xác thực Cloud Run-to-Cloud Run bằng ID token trong Java, giải thích lựa chọn GKE Workload Identity Federation và mTLS, đồng thời đặt các thành phần vào một kiến trúc có khả năng vận hành trên GCP.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Đánh giá khi nào nên tách microservices, khi nào modular monolith hợp lý hơn.
- Thiết kế ranh giới dịch vụ theo domain, quyền sở hữu dữ liệu và hợp đồng API.
- Chọn synchronous HTTP/gRPC hoặc asynchronous Pub/Sub/Cloud Tasks theo nghiệp vụ.
- Phân biệt authentication, authorization, network ingress và encryption in transit.
- Cấu hình Cloud Run IAM và Google-signed ID token có audience đúng để gọi service khác.
- Viết Java caller dùng Application Default Credentials (ADC) và IdTokenCredentials.
- Hiểu GKE Workload Identity Federation, Kubernetes ServiceAccount và IAM service account.
- Giải thích mTLS, service mesh và các giới hạn của mỗi phương án xác thực.
- Áp dụng least privilege, token lifecycle, retry, deadline, tracing và incident response.
- Xây dựng checklist kiểm chứng trước khi mở traffic production.

## 1. Từ monolith đến microservices

Microservices là cách tổ chức hệ thống thành những dịch vụ nhỏ có trách nhiệm nghiệp vụ rõ ràng, giao tiếp qua hợp đồng API hoặc sự kiện. Mỗi dịch vụ có thể được phát hành và mở rộng tương đối độc lập.

Một ứng dụng đặt hàng có thể có các thành phần:

| Dịch vụ | Trách nhiệm | Dữ liệu do dịch vụ sở hữu |
|---|---|---|
| Checkout | Nhận yêu cầu mua hàng và điều phối quy trình | Checkout session và workflow state |
| Orders | Tạo và quản lý vòng đời đơn hàng | Order records |
| Inventory | Kiểm tra và giữ tồn kho | Stock, reservations |
| Payments | Gọi đối tác thanh toán và ghi nhận trạng thái | Payment attempts và ledger references |
| Notifications | Gửi email, SMS hoặc push notification | Notification preferences và delivery status |

### Khi nào microservices mang lại giá trị?

- Các nhóm cần phát hành độc lập, với mức thay đổi khác nhau.
- Một số chức năng cần scale khác nhau.
- Ranh giới nghiệp vụ và ownership đã rõ.
- Hệ thống có telemetry, CI/CD và năng lực vận hành phân tán.
- Yêu cầu an toàn hoặc dữ liệu cần phân vùng quyền rõ ràng.

### Khi nào chưa nên tách?

Nếu đội ngũ còn nhỏ, ứng dụng có domain chưa ổn định hoặc nhiều module luôn thay đổi cùng nhau, **modular monolith** có thể đơn giản hơn. Tách quá sớm dẫn tới nhiều network calls, distributed transactions, schema versioning và sự cố khó chẩn đoán mà không tạo lợi ích tương xứng.

**Không đồng nhất microservice với một container.** Một dịch vụ có thể có nhiều instance; một container vẫn có thể chứa nhiều module nghiệp vụ. Ranh giới service nên bắt đầu từ domain và ownership, không chỉ từ số lượng Docker images.

## 2. Bounded context và quyền sở hữu dữ liệu

Áp dụng Domain-Driven Design (DDD) để tách các **bounded contexts**:

- Orders quyết định trạng thái đơn hàng hợp lệ.
- Inventory quyết định khả năng đặt giữ hàng.
- Payments quyết định trạng thái thanh toán.
- Notifications chỉ được biết nội dung cần gửi, không cần quyền đọc mọi bảng nghiệp vụ.

Mỗi service là owner của dữ liệu thuộc domain. Các service khác tương tác qua API hoặc event, thay vì cùng sửa bảng của nhau.

### Vì sao không dùng chung database tùy tiện?

Nếu Checkout trực tiếp UPDATE bảng Payments, boundary của Payments mất ý nghĩa. Một thay đổi schema có thể phá hỏng nhiều service cùng lúc, đồng thời khó áp dụng IAM và audit theo trách nhiệm.

Mô hình khuyến nghị:

~~~text
             Client
                |
                v
           Checkout API
            /        \
           v          v
      Orders API   Inventory API
          |              |
          v              v
      Orders DB      Inventory DB
          |
          v
       OrderPlaced event
          |
          v
      Notification Worker
~~~

Không nhất thiết mỗi service phải có một database engine hoặc instance vật lý riêng. Có thể chia sẻ nền tảng quản lý nhưng cần ranh giới schema, credentials, permission và lifecycle rõ ràng. Tránh cho nhiều service cùng quyền ghi vào một bảng nghiệp vụ.

### Hợp đồng giữa các service

Một hợp đồng cần quy định:

- Endpoint, method và version hoặc event type.
- Schema request/response, required fields và backward compatibility.
- Authentication mechanism và danh tính caller được phép.
- Authorization ở mức chức năng, resource và tenant.
- Deadline, retry và idempotency.
- Error semantics và behavior khi dependency không sẵn sàng.
- Ownership, SLI/SLO, documentation và deprecation policy.

OpenAPI, protobuf hoặc schema registry giúp kiểm tra tương thích. Contract tests bổ sung cho unit/integration tests; chúng không thay thế kiểm thử luồng nghiệp vụ end-to-end.

## 3. Chọn mô hình giao tiếp: synchronous và asynchronous

| Giao tiếp | Công nghệ phổ biến trên GCP | Phù hợp khi | Rủi ro |
|---|---|---|---|
| HTTP/REST đồng bộ | Cloud Run, GKE, Load Balancing | Cần kết quả ngay, API đơn giản | Chờ dependency và lỗi lan truyền |
| gRPC đồng bộ/streaming | Cloud Run, GKE | Contract chặt, hiệu năng, streaming | Deadline, connection, proxy và debugging |
| Pub/Sub bất đồng bộ | Pub/Sub + worker Cloud Run/GKE | Fan-out, event-driven, xử lý không đồng bộ | Eventual consistency, duplicate, ordering |
| Task queue | Cloud Tasks + HTTP worker | Giao việc một-một, retry theo lịch | Queue backlog, deadline, duplicate |
| Workflow điều phối | Workflows hoặc orchestrator ứng dụng | Nhiều bước, điều kiện và trạng thái | Chuyển trạng thái phức tạp |

### Ví dụ chọn đúng đường giao tiếp

Checkout cần biết còn hàng ngay lúc xác nhận đơn: có thể gọi Inventory đồng bộ với deadline ngắn.

Sau khi đơn đã tạo thành công, hệ thống gửi event OrderPlaced đến Pub/Sub để Notifications và Analytics xử lý độc lập. Không nên giữ HTTP checkout request chờ email gửi xong nếu gửi email không thuộc critical path.

Nếu Inventory không phản hồi, Checkout phải có chính sách cụ thể: trả trạng thái thử lại, đặt đơn ở trạng thái chờ hoặc từ chối; không tự giả định còn hàng.

### Eventual consistency và idempotency

Một event có thể được giao lặp lại. Consumer cần xử lý duplicate bằng event ID, transaction key hoặc idempotent upsert. Nếu event ghi sau một transaction database, cân nhắc transactional outbox để tránh tình trạng commit đơn hàng nhưng không publish được event.

Microservices không tự bảo đảm exactly-once execution trên toàn bộ workflow. Phải thiết kế retry, deduplication và bù trừ nghiệp vụ nếu tác vụ có side effects.

## 4. Authentication, authorization, encryption và ingress là bốn lớp khác nhau

| Cơ chế | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication (AuthN) | Ai đang gọi? | Caller là service account checkout-caller |
| Authorization (AuthZ) | Caller được phép thực hiện gì? | Chỉ được invoke Inventory; chỉ được đọc tồn kho |
| Encryption in transit | Dữ liệu có được bảo vệ trên đường truyền? | HTTPS/TLS, hoặc mTLS trong mesh |
| Network ingress | Traffic từ đâu được phép đến endpoint? | Cloud Run ingress internal hoặc load balancer nội bộ |

Một request dùng HTTPS không đồng nghĩa caller được ủy quyền. Tương tự, có role Invoker nhưng bị chặn bởi ingress network vẫn không truy cập được. Mỗi lớp phải được cấu hình và kiểm tra riêng.

**Zero Trust** yêu cầu không tự tin cậy một caller chỉ vì nằm cùng VPC, namespace hoặc cluster. Danh tính workload, quyền và phạm vi truy cập phải được xác minh ở ranh giới thích hợp.

## 5. Threat model cho service-to-service

Trước khi chọn cơ chế, hãy xác định tài sản cần bảo vệ và các đường tấn công có thể có.

| Nguy cơ | Tình huống | Kiểm soát |
|---|---|---|
| Caller giả mạo | Một workload gửi request bằng danh tính không được phép | Token được ký, xác thực issuer/audience, IAM |
| Token bị tái sử dụng sai đích | Token của Inventory được dùng gọi Payments | Token có audience riêng cho từng đích |
| Service account dùng chung | Xâm nhập một service cho phép gọi mọi service | Identity và quyền tối thiểu theo workload |
| Token/secret bị lộ | Log ghi bearer token hoặc private key | Không ghi secret, dùng short-lived credentials |
| Lateral movement | Workload bị xâm nhập gọi dịch vụ nội bộ khác | AuthN/AuthZ riêng cho từng hop, ingress và network policy |
| Bypass API gateway | Client nội bộ gọi trực tiếp privileged service | Enforce authorization tại receiver/service boundary |
| Confused deputy | Service dùng quyền cao xử lý yêu cầu chưa được xác minh của user | Ràng buộc quyền user, tenant và operation |
| Replay/duplicate request | Retry thanh toán tạo nhiều giao dịch | Idempotency key và validation |
| Denial of service | Caller hợp lệ gọi quá nhiều request | Quota, rate limit, concurrency, backpressure |
| Cross-environment access | Staging gọi nhầm Payments production | Project/identity isolation, endpoint allowlist và IAM |

**Caller identity không đồng nghĩa end-user identity.** Checkout có thể được xác thực là một service account hợp lệ, nhưng receiver vẫn cần kiểm tra Checkout có được thực hiện giao dịch thay cho người dùng hoặc tenant cụ thể hay không.

## 6. Service accounts và workload identity trên Google Cloud

Service account là danh tính dành cho workload. Cloud Run service hoặc VM có thể chạy dưới một IAM service account, sau đó dùng Application Default Credentials (ADC) để yêu cầu credential ngắn hạn.

Ví dụ phân quyền:

~~~text
checkout Cloud Run
  runtime identity: checkout-caller@PROJECT.iam.gserviceaccount.com
                   |
                   | Cloud Run Invoker trên Inventory
                   v
inventory Cloud Run (private)
  runtime identity: inventory-runtime@PROJECT.iam.gserviceaccount.com
                   |
                   | chỉ được đọc inventory data
                   v
Cloud SQL / Cloud Storage / other resources
~~~

### Một service account cho mỗi vai trò

Không dùng cùng một service account có quyền Owner cho tất cả dịch vụ. Thay vào đó:

- Checkout có quyền invoke Inventory và publish order event nếu cần.
- Inventory có quyền truy cập dữ liệu tồn kho, không cần quyền thanh toán.
- Payments có quyền gọi payment provider và dùng secrets cần thiết.
- Notifications chỉ có quyền đọc subscription và gửi thông báo.

Quyền invoke Inventory được cấp **trên resource Inventory**, không phải role Editor ở project cho Checkout.

### Vì sao tránh service account key JSON?

Private key dài hạn có thể bị sao chép, rò rỉ qua Git, image hoặc hệ thống build. Trên Cloud Run, GKE hay Compute Engine, ưu tiên identity của runtime và credential ngắn hạn qua metadata server hoặc federation. Không đặt GOOGLE_APPLICATION_CREDENTIALS trỏ tới key file trong production nếu không có yêu cầu đặc biệt được đánh giá bảo mật.

## 7. Cloud Run-to-Cloud Run authentication: tổng quan

Giả sử hai service chạy trên Cloud Run:

- **checkout**: nhận HTTP request từ frontend và cần gọi Inventory.
- **inventory**: API nội bộ, yêu cầu Cloud Run IAM authentication.

Luồng chuẩn:

~~~text
Checkout container
  |
  | ADC gắn với checkout-caller service account
  v
Metadata server / Google auth library
  |
  | Google-signed OIDC ID token
  | aud = Inventory service URL
  v
HTTP Authorization: Bearer ID_TOKEN
  |
  v
Inventory Cloud Run ingress check
  |
  v
Cloud Run IAM authentication/Invoker check
  |
  v
Inventory application authorization
  |
  v
Business operation
~~~

### Ba điều kiện trước khi gọi

1. **Runtime identity**: Checkout chạy bằng service account riêng.
2. **Invoker permission**: Service account Checkout được cấp roles/run.invoker trên Inventory.
3. **Valid token**: Request mang Google-signed ID token có audience đúng, gửi qua HTTPS.

Ngoài ra, nếu Inventory dùng ingress internal hoặc internal-and-cloud-load-balancing, đường mạng từ Checkout phải được phép. Cùng project không có nghĩa mọi đường Cloud Run-to-Cloud Run tự được nhận diện là internal khi ingress bị hạn chế; có thể phải cấu hình Direct VPC egress, connector, Private Google Access, Private Service Connect hoặc internal load balancer theo topology.

### ID token khác access token

| Loại credential | Mục đích điển hình | Điểm cần chú ý |
|---|---|---|
| OAuth 2.0 access token | Gọi Google Cloud APIs dựa trên scopes/IAM | Không dùng thay ID token một cách tùy tiện |
| OIDC ID token | Chứng minh identity của caller cho service đích | Có audience để ràng buộc đích |
| API key | Nhận diện project/ứng dụng trong một số API | Không phải xác thực workload có đặc quyền |
| Service account key | Private credential tồn tại lâu | Tránh dùng khi có ADC/workload identity |
| mTLS certificate | Xác thực hai phía transport | Có thể cần service mesh/CA/certificate lifecycle |

Cloud Run IAM có thể chấp nhận một số loại Google-signed OAuth token trong những trường hợp được tài liệu hỗ trợ, nhưng **luồng service-to-service khuyến nghị là Google-signed ID token** với audience khớp service.

## 8. Thực hành IAM cho hai Cloud Run services

Các lệnh dưới đây là ví dụ để thiết kế và review trước khi áp dụng. Thay placeholder bằng project, region, image và service account thực tế. Chạy lệnh triển khai có thể thay đổi production.

### Bước 1 – Tạo runtime identities

~~~bash
gcloud iam service-accounts create checkout-caller \
  --project=PROJECT_ID \
  --display-name="Checkout caller"

gcloud iam service-accounts create inventory-runtime \
  --project=PROJECT_ID \
  --display-name="Inventory runtime"
~~~

### Bước 2 – Triển khai Inventory yêu cầu xác thực

~~~bash
gcloud run deploy inventory \
  --project=PROJECT_ID \
  --region=REGION \
  --image=REGION-docker.pkg.dev/PROJECT_ID/services/inventory:VERSION \
  --service-account=inventory-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --no-allow-unauthenticated
~~~

Cấu hình **không cho phép unauthenticated invocation** là phần bắt buộc trong ví dụ. Nếu dùng Terraform/IaC, giữ chính sách này trong code và kiểm tra policy drift.

### Bước 3 – Cấp role Invoker chỉ trên service Inventory

~~~bash
gcloud run services add-iam-policy-binding inventory \
  --project=PROJECT_ID \
  --region=REGION \
  --member="serviceAccount:checkout-caller@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
~~~

Không cấp roles/run.invoker cho allUsers hoặc allAuthenticatedUsers với service cần bảo vệ. Cũng không cấp ở phạm vi project rộng khi quyền chỉ cần trên Inventory.

### Bước 4 – Triển khai Checkout với identity riêng

~~~bash
gcloud run deploy checkout \
  --project=PROJECT_ID \
  --region=REGION \
  --image=REGION-docker.pkg.dev/PROJECT_ID/services/checkout:VERSION \
  --service-account=checkout-caller@PROJECT_ID.iam.gserviceaccount.com
~~~

Checkout có thể có public ingress hoặc nằm sau load balancer/API Gateway tùy kiến trúc. Việc Checkout công khai không làm Inventory công khai. Cần tách ingress policy và IAM policy của mỗi dịch vụ.

### Bước 5 – Lấy URL của Inventory

~~~bash
gcloud run services describe inventory \
  --project=PROJECT_ID \
  --region=REGION \
  --format="value(status.url)"
~~~

Giả sử URL trả về là:

~~~text
https://inventory-abc123-uc.a.run.app
~~~

Giá trị này chỉ minh họa. Với Cloud Run IAM, audience mặc định là **URL gốc của receiving service** hoặc một custom audience đã được cấu hình hợp lệ, không phải đường dẫn chi tiết /v1/stock.

## 9. ID token: audience, headers và thời hạn

Cloud Run nhận Google-signed ID token trong:

~~~http
Authorization: Bearer ID_TOKEN
~~~

Hoặc khi ứng dụng cần giữ Authorization cho token nghiệp vụ khác:

~~~http
X-Serverless-Authorization: Bearer ID_TOKEN
~~~

Nếu gửi cả hai, Cloud Run ưu tiên X-Serverless-Authorization cho cơ chế IAM authentication. Thiết kế rõ cách xử lý Authorization ở tầng ứng dụng để không có xung đột giữa workload token và end-user token.

### Chọn audience

Nếu gọi:

~~~text
https://inventory-abc123-uc.a.run.app/v1/stock/SKU-001
~~~

thì ID token nên có audience:

~~~text
https://inventory-abc123-uc.a.run.app
~~~

Không đặt audience thành URL có path hoặc query trừ khi một custom audience tương ứng đã được cấu hình. Khi gọi traffic tag URL, audience mặc định vẫn là URL gốc của receiving service. Custom domain không tự là audience hợp lệ; nếu cần giá trị khác, cấu hình custom audience trên receiving Cloud Run service.

Audience giới hạn nơi token được sử dụng; không tạo token không ràng buộc đích để tái sử dụng toàn hệ thống.

### Token expiry và refresh

ID token thường có thời gian sống ngắn (khoảng một giờ trong nhiều luồng metadata), không nên hardcode hoặc lưu lâu. Google authentication libraries hỗ trợ refresh token khi cần. Nếu tự gọi metadata server, cần kiểm tra trường exp hoặc yêu cầu token mới theo chính sách an toàn.

Không log bearer token, không đưa token vào URL query string và không truyền token tới những endpoint không tin cậy.

## 10. Thực hành Java: gọi Inventory bằng IdTokenCredentials

Google authentication library cung cấp IdTokenCredentials và IdTokenProvider. Ví dụ sau dùng ADC của runtime Cloud Run, tạo token có audience là URL Inventory và gắn vào HTTP request.

~~~java
import com.google.api.client.http.GenericUrl;
import com.google.api.client.http.HttpRequest;
import com.google.api.client.http.HttpRequestFactory;
import com.google.api.client.http.HttpResponse;
import com.google.api.client.http.javanet.NetHttpTransport;
import com.google.auth.http.HttpCredentialsAdapter;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.auth.oauth2.IdTokenCredentials;
import com.google.auth.oauth2.IdTokenProvider;

import java.io.IOException;

public final class InventoryHttpCaller {
    private final HttpRequestFactory requestFactory;
    private final String inventoryServiceUrl;

    public InventoryHttpCaller(String inventoryServiceUrl) throws IOException {
        GoogleCredentials adc = GoogleCredentials.getApplicationDefault();
        if (!(adc instanceof IdTokenProvider)) {
            throw new IllegalStateException(
                "Runtime credentials cannot provide Google-signed ID tokens");
        }

        IdTokenCredentials idCredentials =
            IdTokenCredentials.newBuilder()
                .setIdTokenProvider((IdTokenProvider) adc)
                .setTargetAudience(inventoryServiceUrl)
                .build();

        this.inventoryServiceUrl = inventoryServiceUrl;
        this.requestFactory = new NetHttpTransport()
            .createRequestFactory(new HttpCredentialsAdapter(idCredentials));
    }

    public int readStockStatus(String sku) throws IOException {
        // Encode SKU thành path segment bằng thư viện URL phù hợp.
        String url = inventoryServiceUrl + "/v1/stock/" + sku;
        HttpRequest request = requestFactory.buildGetRequest(new GenericUrl(url));
        request.setConnectTimeout(2000);
        request.setReadTimeout(5000);

        HttpResponse response = request.execute();
        try {
            return response.getStatusCode();
        } finally {
            response.disconnect();
        }
    }
}
~~~

Đoạn mã là ví dụ về **lấy ID token cho Cloud Run IAM**. Trong ứng dụng production cần thêm URL encoding cho sku, parse response body, error mapping, timeout tổng, retry policy và kiểm tra quyền theo người dùng/tenant ở phía Inventory.

### Spring bean dùng chung

Nếu mỗi HTTP request tạo một bộ credentials, token client và HTTP transport mới, ứng dụng có thể tốn tài nguyên và tạo thêm latency. Nên tạo caller dùng chung theo vòng đời Spring:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class InventoryClientConfig {
    @Bean
    InventoryHttpCaller inventoryHttpCaller(
        @Value("${inventory.service-url}") String inventoryServiceUrl
    ) throws java.io.IOException {
        return new InventoryHttpCaller(inventoryServiceUrl);
    }
}
~~~

Đoạn trên dùng property **inventory.service-url** từ Spring Boot configuration. Trong hệ thống lớn, nên dùng @ConfigurationProperties đã validation để truyền URL thay vì phân tán nhiều @Value. Chỉ chấp nhận HTTPS service URL từ cấu hình tin cậy. Khi ứng dụng cần nhiều đích, mỗi đích có audience riêng.

**Local ADC thường không giống runtime ADC.** Developer user credentials từ gcloud auth application-default login có thể không hỗ trợ IdTokenProvider. Khi test locally, dùng phương án service account impersonation hoặc cơ chế ID token được hỗ trợ; không tạo key JSON chỉ để đoạn mã chạy.

### Khi cần end-user Authorization header

Nếu Checkout phải chuyển token nghiệp vụ ở Authorization, có thể lấy Google-signed ID token thông qua auth library nhưng gắn nó vào X-Serverless-Authorization để Cloud Run kiểm tra IAM, còn Authorization phục vụ cơ chế xác thực của ứng dụng. Không giả định tự động có hai header nếu chỉ dùng HttpCredentialsAdapter; muốn dùng cả hai cần client HTTP/interceptor được cấu hình có chủ đích.

## 11. Kiểm thử thủ công bằng metadata server

Trên Cloud Run runtime, có thể lấy ID token từ metadata server bằng endpoint identity (không hoạt động tương tự trên máy local):

~~~bash
curl -fsS \
  -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=TARGET_SERVICE_URL"
~~~

Giá trị TARGET_SERVICE_URL phải được URL-encode đúng trong query khi cần. Lệnh trả về token nhạy cảm: **không paste kết quả vào ticket, log hoặc chat**. Để kiểm thử tự động, dùng Google auth library và giới hạn log thay vì in token ra terminal.

Yêu cầu test cần kiểm tra ít nhất:

1. Checkout với đúng identity và audience gọi Inventory thành công.
2. Caller không có roles/run.invoker bị từ chối.
3. Token có audience của service khác bị từ chối.
4. Request không có token bị từ chối khi IAM auth được bật.
5. Ingress network không hợp lệ bị chặn kể cả khi caller có IAM role.
6. Inventory không cho truy cập stock của tenant khác chỉ vì caller là service hợp lệ.

## 12. Ingress restriction và IAM là hai lớp độc lập

Cloud Run cung cấp các lựa chọn ingress như:

- **All**: endpoint có thể được gọi từ internet; IAM authentication vẫn có thể bảo vệ.
- **Internal**: giới hạn nguồn được coi là internal theo quy tắc Cloud Run.
- **Internal and Cloud Load Balancing**: hỗ trợ các đường qua load balancer được cấu hình.

**Không nhầm internal ingress với roles/run.invoker.** Ingress quyết định traffic có được đến endpoint; IAM quyết định identity có được invoke service.

### Cloud Run-to-Cloud Run với internal ingress

Nếu Inventory có ingress internal và Checkout là một Cloud Run service khác, việc gọi URL trực tiếp không luôn được phân loại internal. Theo cấu hình network, cần:

- Direct VPC egress hoặc Serverless VPC Access connector từ caller.
- Định tuyến traffic qua VPC được Cloud Run công nhận là internal.
- Private Google Access và DNS/endpoint phù hợp.
- Hoặc Private Service Connect/internal Application Load Balancer nếu kiến trúc yêu cầu.

Kiểm tra topology trong tài liệu Cloud Run private networking hiện hành. Trong một số trường hợp, chỉ yêu cầu IAM authentication có thể đủ cho threat model và dễ triển khai hơn; chọn ingress internal khi có yêu cầu network boundary rõ ràng và đã kiểm thử luồng.

### Chỉ dùng URL đúng không phải bằng chứng private networking

Một URL run.app được gọi qua HTTPS không tự chứng minh đường đi qua private VPC. Network controls, VPC Service Controls, ingress settings, load balancer và logging cần được kiểm chứng theo kiến trúc cụ thể.

## 13. GKE Workload Identity Federation: danh tính cho Pod

GKE có Kubernetes ServiceAccounts (KSA) đại diện cho workload trong cluster. **Workload Identity Federation for GKE** cho phép dùng principal của workload để gọi Google Cloud APIs mà không quản lý key JSON tĩnh.

Luồng khái quát:

~~~text
Pod với Kubernetes ServiceAccount
          |
          v
Kubernetes projected service account token
          |
          v
GKE metadata server
          |
          v
Security Token Service / federation
          |
          v
IAM principal hoặc IAM service account impersonation
          |
          v
Google Cloud API / service
~~~

Bật Workload Identity Federation không tự cấp IAM permissions. Phải grant role cụ thể trên tài nguyên đích.

### Hai mô hình cấp quyền

**Direct resource access**: IAM policy của resource GCP cấp quyền trực tiếp cho principal định danh KSA/namespace trong workload identity pool. Phù hợp khi Google Cloud API hỗ trợ trực tiếp và muốn giảm bước impersonation.

**IAM service account impersonation**: KSA được phép impersonate một IAM service account, và IAM service account đó mang quyền cần thiết. Dùng khi API hoặc flow yêu cầu danh tính service account theo hình thức mà direct federation chưa hỗ trợ đầy đủ, sau khi review giới hạn hiện hành.

### Ví dụ KSA và liên kết IAM service account

Tạo KSA:

~~~bash
kubectl create namespace checkout
kubectl create serviceaccount checkout-ksa --namespace checkout
~~~

Cho KSA quyền impersonate IAM service account trên GKE project đã bật Workload Identity:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  checkout-caller@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID \
  --role=roles/iam.workloadIdentityUser \
  --member="serviceAccount:PROJECT_ID.svc.id.goog[checkout/checkout-ksa]"
~~~

Gắn annotation:

~~~bash
kubectl annotate serviceaccount checkout-ksa \
  --namespace checkout \
  iam.gke.io/gcp-service-account=checkout-caller@PROJECT_ID.iam.gserviceaccount.com
~~~

Trong Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout
  namespace: checkout
spec:
  replicas: 2
  selector:
    matchLabels:
      app: checkout
  template:
    metadata:
      labels:
        app: checkout
    spec:
      serviceAccountName: checkout-ksa
      containers:
        - name: checkout
          image: REGION-docker.pkg.dev/PROJECT_ID/apps/checkout@sha256:IMAGE_DIGEST
          ports:
            - containerPort: 8080
~~~

Ví dụ yêu cầu cluster/node pool hỗ trợ GKE metadata server và thiết lập Workload Identity đúng. Không trộn KSA mặc định của namespace với KSA riêng nếu muốn ranh giới quyền rõ ràng.

### Gọi Cloud Run từ GKE

Để invoke một Cloud Run service yêu cầu IAM:

1. Xác định workload identity hoặc service account dùng làm caller.
2. Grant roles/run.invoker cho identity phù hợp trên receiving Cloud Run service.
3. Lấy Google-signed ID token với audience tương ứng bằng phương án mà credential flow đó hỗ trợ.
4. Gửi request qua HTTPS và kiểm tra network ingress.

**Không giả định token access từ Workload Identity Federation tự động là ID token gọi Cloud Run.** Khi thư viện Java cần IdTokenProvider, xác nhận credentials thực tế hỗ trợ ID token generation; nếu cần, dùng IAM service account impersonation hoặc API tạo ID token được cho phép với quyền phù hợp. Kiểm thử flow trên cluster, không chỉ giả định từ tài liệu cấu hình KSA.

## 14. Mutual TLS (mTLS) và Cloud Service Mesh

TLS thông thường giúp client xác minh server và bảo vệ dữ liệu trên đường truyền. **mTLS** yêu cầu cả client và server xuất trình certificate, từ đó hai phía cùng xác thực workload identity ở lớp transport.

Cloud Service Mesh có thể cung cấp các cơ chế identity, mTLS, authorization và telemetry cho traffic service-to-service trong mô hình hỗ trợ.

| Khía cạnh | Cloud Run IAM + ID token | Service mesh mTLS |
|---|---|---|
| Danh tính | Google-signed ID token của caller | Identity gắn với certificate workload |
| Nơi kiểm tra | Cloud Run platform trước khi vào container | Proxy/mesh data plane |
| Audience | Có, cho service đích | Không dùng cùng cơ chế aud của OIDC |
| Chính sách | Cloud Run Invoker + application AuthZ | Mesh AuthorizationPolicy + application AuthZ |
| Certificate lifecycle | Không cần app tự quản lý cert cho IAM | Mesh/CA quản lý issuance và rotation |
| Phù hợp | Cloud Run service-to-service | GKE và kiến trúc mesh được hỗ trợ |

Mô hình này không phải lựa chọn loại trừ nhau. Một hệ thống đa nền tảng có thể dùng Cloud Run IAM ở ranh giới serverless và mesh mTLS cho một số dịch vụ trong GKE.

### Ví dụ chính sách mTLS trong Istio-compatible mesh

Nếu namespace Inventory đã được onboard vào mesh, một policy minh họa:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: inventory-strict-mtls
  namespace: inventory
spec:
  mtls:
    mode: STRICT
~~~

Một policy authorization minh họa:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: allow-checkout-to-inventory
  namespace: inventory
spec:
  selector:
    matchLabels:
      app: inventory
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/checkout/sa/checkout-ksa"
      to:
        - operation:
            methods: ["GET"]
            paths: ["/v1/stock/*"]
~~~

Các ví dụ chỉ áp dụng khi phiên bản mesh/CRD và mode triển khai hỗ trợ các trường đó. Trust domain và principal format có thể khác; cần xác minh bằng cấu hình thực tế. Nếu áp chính sách STRICT lên workload chưa có mesh identity, traffic có thể bị từ chối. Hãy thử ở staging và rollout từng namespace.

**mTLS xác thực workload, không tự xác minh quyền người dùng cuối.** Inventory vẫn cần kiểm tra authorization ở mức SKU, order hoặc tenant khi nghiệp vụ yêu cầu.

## 15. Pub/Sub push và Cloud Tasks: xác thực HTTP bất đồng bộ

Không phải mọi lời gọi service-to-service đều do một container chủ động gửi HTTP. Với Pub/Sub push subscription hoặc Cloud Tasks HTTP task, dịch vụ trung gian gửi request đến worker.

### Pub/Sub push có OIDC authentication

Một mô hình:

~~~text
Orders -> Publish OrderPlaced -> Pub/Sub subscription
                                     |
                                     | authenticated push
                                     | OIDC ID token của push SA
                                     v
                              Notifications Cloud Run
~~~

Để bảo vệ Notifications:

- Tạo hoặc chọn service account cho push authentication.
- Cấp roles/run.invoker cho service account đó trên receiving Cloud Run service.
- Cấu hình push subscription sử dụng service account và audience phù hợp.
- Kiểm tra quyền để Pub/Sub service agent có thể tạo token đại diện cho push service account theo tài liệu.
- Không mở public unauthenticated invocation chỉ để push hoạt động.

Pub/Sub có thể redeliver message. Handler cần idempotency và chỉ trả trạng thái thành công khi xử lý đủ bền theo hợp đồng subscription.

### Cloud Tasks HTTP target có OIDC

Cloud Tasks hỗ trợ gắn OIDC token cho HTTP task gọi Cloud Run. Service account dùng để phát token cần được ủy quyền invoke receiving service; principal tạo task cần quyền sử dụng service account theo cơ chế Cloud Tasks quy định.

Không dùng access token thay OIDC token khi target là Cloud Run IAM-protected HTTP service, trừ khi tài liệu flow cụ thể hỗ trợ và được kiểm thử.

### Async không loại bỏ authorization

Một message hợp lệ đi qua Pub/Sub không tự bảo đảm mọi hành động trong payload được phép. Consumer vẫn cần kiểm tra schema, source, tenant, idempotency và business rules. Không cho phép người gửi message tự gán quyền cao bằng cách ghi role=admin trong payload.

## 16. Tổ chức service-to-service authorization theo business capabilities

IAM role Invoker thường xác định **ai được gọi endpoint service**. Nó không tự biết caller chỉ được xem tồn kho hay được điều chỉnh tồn kho.

Ví dụ Inventory có:

~~~text
GET  /v1/stock/{sku}
POST /v1/reservations
POST /v1/stock-adjustments
~~~

Nếu Checkout cần hai endpoint đầu, không nên mặc định cho nó quyền nghiệp vụ điều chỉnh tồn kho.

### Chính sách hai tầng

1. **Platform authorization**: Cloud Run IAM bảo đảm caller là identity hợp lệ và có quyền invoke.
2. **Application authorization**: Inventory kiểm tra operation, tenant, resource và hành vi theo business policy.

Có thể tách API nhạy cảm thành service riêng để IAM boundary đủ hẹp, hoặc bổ sung policy enforcement ở application/service mesh/gateway đã được thiết kế. Chỉ dựa vào một header X-Caller-Name tự khai báo là không an toàn.

### Propagate end-user identity đúng cách

Nếu user đăng nhập frontend và Checkout gọi Orders:

- Checkout xác thực và ủy quyền user cho thao tác checkout.
- Orders có thể cần user context để kiểm tra tenant/ownership.
- User context nên được chuyển qua một token có issuer, signature, audience, expiry và claims phù hợp, hoặc một cơ chế delegation được thiết kế rõ.
- Không truyền đơn giản X-User-Id rồi tin rằng caller trung thực trong mọi trường hợp.
- Không forward access token của user sang service không phải audience của nó.

Khi dùng hai lớp token, phân biệt workload token bảo vệ hop và end-user token/biz context phục vụ authorization. Thiết kế không để token có quyền rộng bị lưu trong logs.

## 17. Resilience: deadline, retry và failure isolation

Microservices tăng số remote calls. Một HTTP request có thể đi qua Checkout, Inventory và Payments; nếu mỗi hop đặt timeout 10 giây, tổng latency có thể vượt SLO của người dùng.

### Deadline budgets

Ví dụ checkout SLO latency ở mức dưới 2 giây:

| Thành phần | Budget tham khảo |
|---|---|
| API gateway và Checkout validation | 200 ms |
| Inventory reservation | 400 ms |
| Payment authorization | 700 ms |
| DB commit và response | 300 ms |
| Headroom network/retry | 400 ms |

Bảng minh họa, phải đo trên traffic thật. Các bước có thể song song hoặc nối tiếp; tính budget dựa trên critical path, không chỉ cộng cơ học.

### Retry có giới hạn

- Chỉ retry lỗi tạm thời được phép.
- Dùng exponential backoff và jitter.
- Giới hạn số lần và tổng deadline.
- Dùng idempotency key cho thao tác tạo đơn, giữ kho và thanh toán.
- Tránh retry cùng lúc ở mọi tầng gây **retry amplification**.
- Dùng circuit breaker, bulkhead, concurrency limit khi downstream suy giảm.

### Graceful degradation

Nếu Notifications lỗi, Checkout vẫn có thể hoàn tất đơn và gửi event để retry sau. Nếu Payments lỗi, không nên ghi đơn là đã thanh toán. Mỗi dependency cần quyết định rõ có thuộc critical path hay không.

## 18. Observability giữa các microservices

Một lỗi 503 tại Checkout không cho biết ngay Inventory bị timeout, IAM token sai hay payment provider trả lỗi. Cần các tín hiệu liên kết được nhiều hop.

| Telemetry | Thông tin nên ghi nhận |
|---|---|
| Metrics | Request rate, p95/p99 latency, error rate, saturation theo service/dependency |
| Traces | Trace/span ID qua Checkout -> Inventory -> Payments |
| Logs | Structured logs có trace ID, service name, revision và error category |
| Audit logs | Thay đổi IAM, deploy, policy và một số hành động quản trị |
| SLO | Availability/latency của user journey, không chỉ health VM/pod |
| Security events | 401/403, principal, audience mismatch, policy deny |

Dùng OpenTelemetry instrumentation phù hợp cho Java/Spring Boot và hệ thống observability đã chọn. Tránh label chứa user ID hoặc token vì cardinality, quyền riêng tư và chi phí.

### Phân biệt các lỗi xác thực

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| 401 / unauthenticated | Thiếu token, token hết hạn hoặc signature/audience sai | Kiểm tra cách mint token, audience và request header |
| 403 / permission denied | Identity có token nhưng không có quyền invoke, hoặc policy khác từ chối | Kiểm tra IAM policy trên receiving service, service account và ingress |
| Connection timeout | Routing/VPC, DNS, firewall hoặc upstream không phản hồi | Kiểm tra network path, ingress và latency |
| 404 hoặc service unavailable | Sai URL, route, revision hoặc method | Kiểm tra endpoint, deployments và logs |
| 429 / resource exhausted | Quota, concurrency hoặc rate limit | Kiểm tra metrics và retry budget |

Mã lỗi có thể khác theo API/proxy. Không dùng riêng HTTP status để kết luận nguyên nhân; đối chiếu platform logs, application logs, audit logs và networking.

### Không ghi token vào logs

Khi debug authentication, chỉ ghi thông tin an toàn như service name, request ID, expected audience, exception type, token expiry **không kèm token value**, và identity đã được platform xác minh nếu có. Không dump Authorization hoặc X-Serverless-Authorization.

## 19. CI/CD, IAM as Code và triển khai an toàn

Nên quản lý service account, Cloud Run IAM bindings, ingress settings và deploy configuration qua Terraform hoặc IaC có review. Không để test chạy bằng Owner nhưng production chạy bằng service account khác mà không có kiểm thử tương đương.

Một pipeline triển khai đáng tin cậy:

~~~text
Commit
  |
  v
Build + unit tests + contract tests
  |
  v
Security scan + provenance + image digest
  |
  v
Provision/verify IAM + target configuration
  |
  v
Deploy staging with service identities
  |
  v
Negative auth tests + functional integration tests
  |
  v
Canary production + SLO checks
  |
  v
Promotion hoặc rollback
~~~

### Tách build identity và runtime identity

Build service account chỉ cần quyền build/push artifact và triển khai theo phạm vi được cấp. Runtime service account chỉ cần quyền gọi các dịch vụ phụ thuộc hoặc truy cập dữ liệu cần thiết. Không chạy container production bằng một CI/CD administrator service account.

### Chính sách phát hành

- Mọi thay đổi IAM phải có review.
- Tránh grant wildcard cho toàn bộ project nếu chỉ một service cần quyền.
- Bật audit và cảnh báo khi policy thay đổi.
- Kiểm tra regression của service-to-service auth sau khi đổi URL/custom audience.
- Khi rotate/revoke service account, đánh giá ảnh hưởng tới các callers.
- Dùng canary và rollback để giảm rủi ro nếu token/auth configuration đổi.

## 20. Tình huống thực tế: Checkout gọi Inventory và Payments

Một công ty triển khai:

- Frontend đi qua external Application Load Balancer hoặc API Gateway.
- Checkout chạy Cloud Run, nhận request người dùng.
- Inventory chạy Cloud Run, IAM-protected.
- Payments chạy Cloud Run hoặc GKE, IAM/mTLS protection theo runtime.
- Order events gửi qua Pub/Sub đến Notifications.
- Mỗi service có identity và data store riêng.

### Bước 1 – Xác định security boundaries

| Thành phần | Gọi tới | Quyền cần thiết |
|---|---|---|
| Frontend | Checkout | End-user auth và nghiệp vụ checkout |
| Checkout SA | Inventory | Cloud Run Invoker trên Inventory |
| Checkout SA | Payments | Chỉ invoke payment endpoint đã phê duyệt |
| Orders SA | Pub/Sub topic | Publisher trên topic cụ thể |
| Pub/Sub push SA | Notifications | Invoker trên Notifications |
| Inventory runtime SA | Inventory DB | Chỉ quyền truy cập dữ liệu tồn kho |
| Payments runtime SA | Payment secrets | Secret Manager Accessor cho secret cụ thể |

Không tạo một role Owner duy nhất cho tất cả service.

### Bước 2 – Thiết kế request flow

~~~text
User
  |
  v
Checkout (user auth + business validation)
  |
  +-- [OIDC ID token aud=Inventory URL] --> Inventory
  |
  +-- [OIDC ID token aud=Payments URL] --> Payments
  |
  v
Commit order / outbox event
  |
  v
Pub/Sub -> Notifications (authenticated push)
~~~

Mỗi downstream có audience khác nhau. ID token của Inventory không được tái sử dụng cho Payments.

### Bước 3 – Negative tests

- Gọi Inventory bằng service account Notifications: phải bị chặn nếu không được cấp Invoker.
- Gọi Inventory bằng token có Payments audience: phải bị từ chối.
- Gọi Payments với đơn hàng thuộc tenant khác: phải bị chặn ở business authorization.
- Thử Pub/Sub push mà không có identity được cấp: phải bị từ chối.
- Thử request quá hạn hoặc duplicate event: phải được xử lý theo deadline/idempotency policy.
- Kiểm tra logs không chứa bearer token.

### Bước 4 – Reliability checks

- Inventory timeout: Checkout trả trạng thái an toàn, không ghi nhận stock reservation giả.
- Payments timeout: giao dịch có idempotency key và trạng thái chờ xác minh nếu cần.
- Pub/Sub redelivery: Notifications không gửi trùng ngoài quy tắc chấp nhận.
- Scale out: service account, connection pools và downstream quota đủ cho số Cloud Run instances.
- Revision rollout: IAM, audience và ingress tiếp tục hoạt động trên revision mới.

### Bước 5 – Vận hành và incident response

Có runbook cho lỗi authentication tăng đột biến:

1. Xác định receiving service và caller identity thực tế.
2. Kiểm tra thay đổi IAM/ingress, service account và deployment gần nhất.
3. Kiểm tra token audience, expiry, issuer và header name.
4. Kiểm tra kết nối network nếu ingress internal.
5. Rollback cấu hình hoặc revision khi có bằng chứng lỗi do thay đổi mới.
6. Xác minh SLO, security logs và negative tests sau khôi phục.

Không sửa lỗi 403 bằng cách cấp allUsers Invoker hoặc tạm bỏ IAM check trên production.

## 21. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Cho mọi service dùng một service account | Một service bị xâm nhập có quyền rộng | Identity theo workload và least privilege |
| Dùng API key làm xác thực nội bộ | Không ràng buộc workload/permission đúng mức | Google-signed ID token hoặc mTLS phù hợp |
| Dùng OAuth access token như OIDC ID token | Audience/validation không đúng flow | Dùng Google auth library ID token cho Cloud Run |
| Dùng URL có path làm audience mặc định | Token bị từ chối | Dùng URL gốc receiving service |
| Gọi traffic tag rồi dùng tag URL làm audience | Audience mismatch | Vẫn dùng service URL gốc hoặc custom audience |
| Nghĩ Cloud Run cùng project là internal mặc định | Ingress internal từ chối request | Kiểm tra VPC routing theo docs |
| Chỉ bật HTTPS mà bỏ IAM | Caller bất kỳ có thể gọi endpoint | Require authentication và grant Invoker cụ thể |
| Chỉ bật IAM mà bỏ business authorization | Service hợp lệ gọi thao tác không được phép | Check operation, resource và tenant |
| Dùng key JSON trong image | Nguy cơ rò rỉ credential dài hạn | Runtime identity/ADC/federation |
| Gửi end-user token tới mọi downstream | Token bị lộ hoặc sai audience | Delegation và token separation |
| Mesh mTLS nhưng không có authz policy | Mọi workload trong mesh có thể gọi quá rộng | Enforce workload-level authorization |
| Retry mọi lỗi 401/403 | Tăng tải và che lỗi cấu hình | Phân loại lỗi; không retry lỗi quyền cố định |
| Không có negative auth tests | Policy sai không bị phát hiện trước production | Test thiếu token/sai role/sai audience |
| Ghi Authorization header vào logs | Lộ bearer credential | Redaction và structured logging |

## 22. Checklist triển khai production

### Thiết kế kiến trúc

- [ ] Service boundaries dựa trên bounded contexts rõ ràng.
- [ ] Mỗi service có owner, API/event contract và SLO.
- [ ] Dữ liệu và quyền ghi được phân định theo service.
- [ ] Đã xác định synchronous/asynchronous path cùng semantics retry.
- [ ] Đã đánh giá eventual consistency, idempotency và failure modes.

### Identity và bảo mật

- [ ] Mỗi workload có identity riêng, không dùng key JSON dài hạn khi có ADC.
- [ ] Caller được cấp đúng Invoker role trên receiving Cloud Run service.
- [ ] ID token là Google-signed và có audience đúng receiving service.
- [ ] Application không log token và có cơ chế refresh.
- [ ] Ingress network được cấu hình, thử nghiệm độc lập với IAM.
- [ ] GKE workloads dùng Workload Identity Federation và grant quyền theo phạm vi.
- [ ] Nếu dùng mesh, mTLS và AuthorizationPolicy có rollout an toàn.
- [ ] Receiver có business authorization cho operation/resource/tenant.
- [ ] Secrets dùng Secret Manager và quyền IAM tối thiểu.
- [ ] Có negative tests cho thiếu/sai token, audience và identity.

### Vận hành và phát hành

- [ ] Timeout, retry, backpressure và circuit breaker phù hợp từng dependency.
- [ ] Có tracing/correlation ID và metrics theo hop.
- [ ] Audit logs ghi nhận IAM/policy changes quan trọng.
- [ ] Service account và IAM policies nằm trong IaC có review.
- [ ] Build identity và runtime identity được tách.
- [ ] Canary kiểm tra cả chức năng lẫn authentication/authorization.
- [ ] Có runbook cho 401/403, token issuance, routing và mesh policy.
- [ ] Có kế hoạch rollback khi thay đổi ingress, identity hoặc audience.
- [ ] Không mở rộng quyền tạm thời để chữa lỗi production mà không có đánh giá và phê duyệt.

## Kết luận

Kiến trúc microservices trên Google Cloud không chỉ là chia một monolith thành nhiều container. Giá trị nằm ở ranh giới nghiệp vụ, quyền sở hữu dữ liệu, hợp đồng giao tiếp và khả năng vận hành độc lập. Khi các dịch vụ gọi nhau, cần thiết kế **danh tính workload, xác thực, quyền truy cập và network controls** theo từng hop. Với Cloud Run, mô hình phổ biến là service account riêng, role Invoker và Google-signed OIDC ID token có audience đúng; với GKE, Workload Identity Federation và mTLS/service mesh là các lựa chọn phù hợp tùy mục tiêu. Kết hợp chúng với application-level authorization, observability, deadline, idempotency và CI/CD có kiểm soát sẽ giúp hệ thống vừa mở rộng được vừa giảm rủi ro truy cập trái phép.

## Tài liệu tham khảo

- [Cloud Run: Authenticating service-to-service](https://docs.cloud.google.com/run/docs/authenticating/service-to-service)
- [Cloud Run: Java service-to-service authentication sample](https://docs.cloud.google.com/run/docs/samples/cloudrun-service-to-service-auth)
- [Cloud Run: Configure custom audiences](https://docs.cloud.google.com/run/docs/configuring/custom-audiences)
- [Cloud Run: Security overview](https://docs.cloud.google.com/run/docs/securing/security)
- [Cloud Run: Ingress restrictions](https://docs.cloud.google.com/run/docs/securing/ingress)
- [Cloud Run: Private networking](https://docs.cloud.google.com/run/docs/securing/private-networking)
- [Google Cloud: Workload identities](https://docs.cloud.google.com/iam/docs/workload-identities)
- [GKE: Workload Identity Federation overview](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [GKE: Configure Workload Identity Federation](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-identity)
- [Java: IdTokenCredentials reference](https://docs.cloud.google.com/java/docs/reference/google-auth-library/latest/com.google.auth.oauth2.IdTokenCredentials)
- [Google Cloud: Get an ID token](https://docs.cloud.google.com/docs/authentication/get-id-token)
- [Cloud Service Mesh documentation](https://docs.cloud.google.com/service-mesh/docs)
- [Cloud Tasks: Authenticate HTTP target tasks](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks)
- [Pub/Sub: Authenticate push subscriptions](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions)
- [Google Cloud Architecture Framework: Security](https://docs.cloud.google.com/architecture/framework/security)

