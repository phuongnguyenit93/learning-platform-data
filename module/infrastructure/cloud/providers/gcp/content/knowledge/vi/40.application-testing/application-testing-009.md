# Kiểm thử IAM, service identity và truy cập mạng riêng

Trong module `CLOUD_PROVIDERS_GCP`, người học khám phá Google Cloud từ project, IAM, VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Những tình huống triển khai giúp lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Ở chương **Kiểm thử ứng dụng GCP**, kiểm thử không chỉ xác minh chức năng của ứng dụng mà còn phải kiểm tra các ranh giới bảo mật khi ứng dụng chạy bằng danh tính và đường mạng thật.

Bài thực hành này hướng dẫn kiểm thử **IAM authorization**, **service identity** và **truy cập mạng riêng** trên GCP. Ví dụ xuyên suốt là ứng dụng Spring Boot `orders-api` chạy trên Cloud Run, đọc một object mẫu từ Cloud Storage và kết nối đến Cloud SQL PostgreSQL bằng private IP. Chúng ta xác minh cả trường hợp được phép và bị từ chối, đồng thời phân biệt lỗi IAM, authentication, DNS, route, firewall và database credentials.

## 1. Ba ranh giới cần kiểm thử

Một request có thể đi qua nhiều lớp kiểm soát:

| Lớp | Câu hỏi | Cơ chế thường gặp |
| --- | --- | --- |
| **Authentication** | Request đang sử dụng danh tính nào? | Application Default Credentials (ADC), OAuth access token, OIDC ID token, metadata server. |
| **IAM authorization** | Principal đó được thực hiện thao tác gì trên resource nào? | IAM allow/deny policies, roles, conditions, principal access boundary, service-specific policies. |
| **Network reachability** | Packet có đi được tới endpoint và port cần thiết? | Cloud Run Direct VPC egress, Shared VPC, subnet, DNS, route, firewall, private IP. |
| **Destination authorization** | Server đích có chấp nhận request/credentials không? | Cloud Run Invoker, database login, TLS, application RBAC. |

Một TCP connection thành công chỉ chứng minh socket đã được mở; nó chưa chứng minh user được phép truy vấn database. Một HTTP 403 từ Cloud Storage chứng minh Google API từ chối request nhưng chưa đủ để kết luận chỉ vì IAM thiếu quyền: API disabled, VPC Service Controls hoặc các chính sách khác cũng có thể ảnh hưởng.

~~~mermaid
flowchart LR
    CLIENT[Caller + ID token] --> INGRESS[Cloud Run ingress]
    INGRESS --> INVOKER[Cloud Run invoker IAM]
    INVOKER --> APP[orders-api + runtime SA]
    APP --> ADC[ADC + Google access token]
    ADC --> IAM[Cloud Storage IAM]
    IAM --> BUCKET[(Test bucket/object)]
    APP --> VPC[Direct VPC egress]
    VPC --> NET[DNS / route / firewall]
    NET --> SQL[(Cloud SQL private IP)]
    SQL --> DB[Database login + SQL privileges]
~~~

**Cloud Run ingress** là chính sách kiểm soát nguồn gọi vào service; **Direct VPC egress** là đường ra từ Cloud Run đến VPC. **Service identity** là service account mà code chạy trong Cloud Run dùng để gọi Google APIs; nó khác **deployer identity** dùng để triển khai Cloud Run và khác **invoker identity** gọi vào HTTP endpoint của service.

## 2. Thiết kế ma trận kiểm thử

Trước khi viết code, mô tả mỗi trường hợp theo cấu trúc: **principal + action + resource + network context + expected outcome**. Một ma trận kiểm thử tối thiểu:

| ID | Principal / nguồn | Thao tác | Network context | Kỳ vọng |
| --- | --- | --- | --- | --- |
| IAM-01 | `orders-runtime@PROJECT_ID` | Đọc object `fixtures/ping.json` | Cloud Run staging | ALLOW |
| IAM-02 | `orders-runtime@PROJECT_ID` | Xóa object mẫu | Cloud Run staging | DENY |
| IAM-03 | `denied-runtime@PROJECT_ID` | Đọc cùng object | Runner với cùng kết nối | DENY |
| ID-01 | Cloud Run revision mới | Gọi Storage bằng ADC | Staging | Caller là `orders-runtime` |
| ID-02 | Deployer CI | Attach runtime service account | Bước deploy | Chỉ deployer được duyệt mới có quyền `iam.serviceAccounts.actAs` |
| RUN-01 | SA có `roles/run.invoker` | Gọi Cloud Run private endpoint | Nguồn đi qua ingress | ALLOW |
| RUN-02 | SA không có Invoker | Gọi cùng endpoint | Cùng nguồn ingress | DENY |
| NET-01 | `orders-api` | TCP đến `10.20.4.5:5432` | VPC staging được phép | CONNECT |
| NET-02 | Workload bị firewall/routing chặn | TCP đến cùng địa chỉ | Mạng staging bị hạn chế | DENY |
| NET-03 | Caller Internet công cộng | Gọi service Cloud Run internal | Ngoài ingress hợp lệ | DENY |

Tất cả tên, IP, bucket và project ID trong bài đều là giá trị minh họa. Dùng **staging**, test object và database có dữ liệu giả. Negative test phải có positive control để chứng minh resource đích tồn tại và hoạt động; nếu không, một `404`, timeout hoặc DNS error có thể là lỗi fixture chứ không phải hiệu lực chính sách bảo mật.

### 2.1. Chọn đúng mức kiểm thử

- **Policy/static test:** đọc Terraform plan, cấu hình IAM bindings, service account, ingress/egress và firewall. Phát hiện drift cấu hình trước khi deploy; không mô phỏng đầy đủ behavior.
- **Integration test:** thực hiện Google API call hoặc TCP probe từ workload/runner có danh tính và network tương đương production.
- **End-to-end test:** caller gửi request đến Cloud Run; code đi qua IAM và private network để truy cập dịch vụ downstream; kiểm tra kết quả và audit evidence.

Unit test với mock Google Cloud client kiểm tra logic Java, nhưng không chứng minh IAM hoặc private networking thực tế. Cần môi trường GCP thật cho phần kiểm thử này.

## 3. Chuẩn bị môi trường thử nghiệm

### 3.1. Test fixtures

Chuẩn bị trước các tài nguyên trong một project staging có quyền kiểm soát:

| Thành phần | Mục đích |
| --- | --- |
| `PROJECT_ID`, `REGION` | Project/region staging. |
| `orders-runtime@PROJECT_ID.iam.gserviceaccount.com` | Runtime SA được phép đọc object. |
| `denied-runtime@PROJECT_ID.iam.gserviceaccount.com` | Runtime SA không được cấp quyền đọc object. |
| `test-caller@PROJECT_ID.iam.gserviceaccount.com` | Caller được quyền invoke service. |
| `denied-caller@PROJECT_ID.iam.gserviceaccount.com` | Caller không có quyền invoke. |
| `TEST_BUCKET/fixtures/ping.json` | Object test tồn tại và không chứa dữ liệu nhạy cảm. |
| `test-vpc` và `test-subnet` | VPC/subnet đã cấu hình Direct VPC egress. |
| PostgreSQL test instance | Cloud SQL private IP và account test readonly. |

Nếu object không tồn tại, test đọc có thể nhận `404` thay vì kết quả chứng minh IAM. Hãy kiểm tra fixture bằng principal kiểm soát có quyền đọc trước khi chạy negative test.

Cấp `roles/storage.objectViewer` cho `orders-runtime` trên bucket hoặc phạm vi hẹp hơn theo yêu cầu; không cấp quyền đọc cho `denied-runtime`. Không sử dụng bucket production hoặc object có nội dung người dùng để thử permission.

### 3.2. Các identity trong Cloud Run

Có ba danh tính khác nhau cần kiểm tra:

1. **Deployer:** principal gọi Cloud Run Admin API. Muốn attach một service account runtime, deployer phải có `iam.serviceAccounts.actAs` trên service account đó; role thường dùng là `roles/iam.serviceAccountUser`.
2. **Runtime service identity:** service account gắn vào revision. Cloud Run metadata server cung cấp short-lived access token và Google Client Libraries dùng ADC để gọi Google APIs.
3. **HTTP caller / invoker:** principal gửi OIDC ID token khi gọi Cloud Run yêu cầu authentication. Principal này phải có quyền `run.routes.invoke`, thường được cấp qua `roles/run.invoker`.

Role `roles/iam.serviceAccountTokenCreator` để tạo access/ID token bằng impersonation khác với `roles/iam.serviceAccountUser` dùng để attach danh tính. Tránh cấp Token Creator rộng chỉ để một test chạy được.

Kiểm tra service configuration:

~~~bash
gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=REGION \
  --format=export
~~~

Kiểm tra `serviceAccountName`, `ingress`, network/subnet và VPC egress trong cấu hình. Revision phải dùng đúng `orders-runtime@PROJECT_ID.iam.gserviceaccount.com`, không vô tình trở về Compute Engine default service account. Mỗi lần deploy cần xác minh lại vì identity là cấu hình của revision.

### 3.3. ADC và nguyên tắc không dùng key JSON

Trên máy phát triển, `gcloud auth application-default login` tạo ADC của người phát triển; tài khoản đó có thể có quyền mạnh hơn runtime SA. Vì vậy, test trên laptop thành công **không chứng minh** ứng dụng production có quyền tương đương.

Trong Cloud Run, dùng user-managed service account gắn với workload và Google Client Libraries sử dụng ADC. Không đặt `GOOGLE_APPLICATION_CREDENTIALS` để trỏ tới service account key JSON trong container. Trong GKE dùng Workload Identity Federation for GKE; trong Compute Engine dùng service account gắn vào VM cùng API scopes phù hợp khi cần. Với CI, ưu tiên Workload Identity Federation hoặc service account impersonation ngắn hạn thay vì key file dài hạn.

## 4. Kiểm thử IAM allow/deny

### 4.1. Kiểm tra permission bằng Policy Troubleshooter

Mở **IAM & Admin → Policy Troubleshooter**. Cung cấp:

- Principal: `orders-runtime@PROJECT_ID.iam.gserviceaccount.com`.
- Resource: fixture bucket/object được chọn.
- Permission: `storage.objects.get`.
- Expected decision: **Allow** cho runtime SA; **Deny** khi kiểm tra `storage.objects.delete` hoặc `storage.objects.get` bằng `denied-runtime`.

Policy Troubleshooter xét những allow/deny policies, IAM Conditions và principal access boundaries được hỗ trợ. Kết quả **Unknown** có thể xuất hiện nếu người chạy không có quyền xem chính sách hoặc thiếu condition context. Không đổi Unknown thành Deny. Công cụ này cũng không mô phỏng VPC Service Controls, và có giới hạn với một số service-level bindings/ACL.

Ví dụ minh họa cú pháp CLI bằng một permission ở cấp project:

~~~bash
gcloud policy-intelligence troubleshoot-policy iam \
  //cloudresourcemanager.googleapis.com/projects/PROJECT_ID \
  --principal-email=orders-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --permission=resourcemanager.projects.get
~~~

Lệnh minh họa ở trên kiểm tra `resourcemanager.projects.get`, **không** chứng minh `storage.objects.get\). Với Storage, chọn full resource name và permission thích hợp, sau đó kiểm chứng bằng Storage API integration test. Nếu IAM Condition dùng timestamp, resource tags hoặc thuộc tính request, cung cấp context tương ứng để tránh kết luận sai.

### 4.2. Phân biệt với testIamPermissions

Nhiều Google Cloud APIs có `testIamPermissions`, trả về các permission mà **caller hiện tại** được cấp trên resource. Phương thức này hữu ích cho UI hoặc self-check, nhưng nó không cho phép kiểm tra một principal tùy ý bằng cách truyền email của principal đó. Để điều tra một principal khác, dùng Policy Troubleshooter và test chạy dưới chính danh tính đó.

### 4.3. Kiểm tra bằng Google Cloud Storage Java client

Dùng Google Cloud Storage client được quản lý phiên bản theo BOM của dự án và JUnit 5. Ví dụ trong Spring Boot Gradle project đã cấu hình dependencies phù hợp:

~~~groovy
dependencies {
    implementation "com.google.cloud:google-cloud-storage"
    testImplementation "org.springframework.boot:spring-boot-starter-test"
}
~~~

Lưu ý `google-cloud-storage` cần phiên bản từ `com.google.cloud:libraries-bom` hoặc cấu hình dependency management tương đương; không để dependency thiếu phiên bản khi project chưa import BOM.

Positive integration test, chạy **trong job/revision sử dụng runtime SA hợp lệ**:

~~~java
package com.example.orders.it;

import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@Tag("gcp-integration")
class StorageAllowedIT {
    @Test
    void canReadExistingFixtureObject() {
        String bucket = System.getenv("TEST_BUCKET");
        Storage storage = StorageOptions.getDefaultInstance().getService();

        Blob blob = storage.get(
            BlobId.of(bucket, "fixtures/ping.json"));

        assertNotNull(blob, "Fixture must exist and be readable");
    }
}
~~~

Negative test, chạy trong **job riêng sử dụng `denied-runtime`**:

~~~java
package com.example.orders.it;

import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageException;
import com.google.cloud.storage.StorageOptions;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Tag("gcp-integration-negative")
class StorageDeniedIT {
    @Test
    void cannotReadFixtureWithoutIamPermission() {
        String bucket = System.getenv("TEST_BUCKET");
        Storage storage = StorageOptions.getDefaultInstance().getService();

        StorageException exception = assertThrows(
            StorageException.class,
            () -> storage.get(BlobId.of(bucket, "fixtures/ping.json")));

        assertEquals(403, exception.getCode());
    }
}
~~~

Hai test chỉ xác thực allow/deny nếu CI thực sự chạy dưới **hai principal khác nhau** và object tồn tại. Nếu cùng ADC cá nhân được sử dụng cho cả hai, test không có giá trị. Khi status code không đúng kỳ vọng, lưu mã lỗi, principal, resource, request ID và Cloud Audit Log liên quan; tuyệt đối không lưu access token.

## 5. Kiểm thử danh tính thực thi (service identity)

### 5.1. Kiểm tra principal thực tế trong workload

Cloud Run sử dụng metadata server để cấp token ngắn hạn cho runtime service account. Trong một debug job có quyền hợp lệ, kiểm tra email của runtime service identity:

~~~bash
curl -fsS \
  -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
~~~

Chỉ gọi metadata server **bên trong** workload GCP. Endpoint đó không thể truy cập trực tiếp từ laptop. Không ghi hoặc trả về cho client nội dung `.../token`, vì đó là access token đang hoạt động. Ghi log chẩn đoán về email service account và revision ID ở mức độ được phép để xác định sai lệch.

Trên GKE, Kubernetes ServiceAccount không nhất thiết trùng với email IAM service account; có thể dùng principal Workload Identity trực tiếp hoặc cơ chế impersonation. Xác minh binding/annotation và principal thực tế trên audit log. Trên Compute Engine, kiểm tra cả service account lẫn API access scopes nếu VM được tạo với scopes giới hạn.

### 5.2. Một lỗi thường gặp

Một phiên bản `orders-api` mới gắn nhầm Compute Engine default service account. Health endpoint vẫn trả 200 vì không truy cập tài nguyên ngoài, nhưng Storage API trả `PERMISSION_DENIED`. Quy trình kiểm tra:

1. So sánh `serviceAccountName` giữa revision tốt và revision lỗi.
2. Xác minh ứng dụng đang dùng ADC, không dùng key JSON được mount từ nơi khác.
3. Chạy lại `StorageAllowedIT` bằng chính revision/job có cấu hình runtime identity đó.
4. Dùng Policy Troubleshooter và audit logs đối chiếu principal, permission và resource.
5. Khôi phục đúng service identity theo quy trình release; không cấp role Owner/Editor cho default SA để xử lý tạm.
6. Thêm gate CI kiểm tra expected service account trên revision staging trước khi chuyển traffic.

## 6. Kiểm thử Cloud Run invoker identity

Cloud Run có thể yêu cầu caller gửi **Google-signed OIDC ID token** với `aud` bằng URL của service đích (hoặc custom audience đã cấu hình). **OAuth access token** dùng để gọi Google API không thay thế ID token dành cho Cloud Run service-to-service invocation.

### 6.1. Test allow/deny từ cùng một nguồn ingress

Chuẩn bị hai caller principals:

- `test-caller` được cấp `roles/run.invoker` trên chính Cloud Run service.
- `denied-caller` không có role đó.

Dùng một runner có **đường vào được Cloud Run ingress policy cho phép**. Ví dụ dành cho operator được cấp quyền impersonation có kiểm soát, trong Cloud Shell hoặc runner phù hợp khi ingress cho phép:

~~~bash
SERVICE_URL="https://orders-api-EXAMPLE.a.run.app"
TOKEN="$(gcloud auth print-identity-token \
  --impersonate-service-account=test-caller@PROJECT_ID.iam.gserviceaccount.com \
  --audiences="$SERVICE_URL")"

curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "$SERVICE_URL/health"

unset TOKEN
~~~

Với caller hợp lệ và endpoint khỏe, kỳ vọng HTTP 200. Lặp lại bằng `denied-caller` trong **cùng network context** và kiểm tra request bị từ chối tại lớp auth/authorization. Để mint ID token bằng impersonation, operator cần `roles/iam.serviceAccountTokenCreator` hoặc permission tương ứng trên caller SA; vai trò này phục vụ test, không nên cấp mặc định cho mọi nhân viên.

### 6.2. Ingress có thể chặn trước IAM

Nếu Cloud Run service được cấu hình `ingress=internal`, request từ Internet công cộng có thể bị chặn **trước** IAM. Do đó, không thể lấy HTTP 404/403 từ laptop để chứng minh IAM Invoker bị từ chối. Chạy hai test Invoker từ nguồn được Cloud Run nhận diện là internal, ví dụ Cloud Run service/job trong mạng và phạm vi phù hợp với cấu hình ingress. Test riêng một request Internet để xác minh ingress chặn như thiết kế.

Audience thường là **URL service chính**, kể cả khi request tới một traffic-tag URL, trừ khi đã cấu hình custom audience hợp lệ. Token sai audience, token hết hạn và thiếu Invoker đều có thể làm request thất bại; log và policy giúp phân loại.

## 7. Kiểm thử mạng riêng cho Cloud Run → Cloud SQL

### 7.1. Các điều kiện cần đúng đồng thời

Để Cloud Run truy cập PostgreSQL bằng **private IP**, xác minh:

1. Cloud SQL instance tồn tại, có private IP và phục vụ kết nối TCP `5432`.
2. Cloud Run được cấu hình **Direct VPC egress** hoặc Serverless VPC Access connector phù hợp.
3. VPC/subnet có đường đi đến Cloud SQL (bao gồm Private Service Access/peering hoặc mô hình kết nối được thiết kế).
4. Route và firewall rules cho phép nguồn Cloud Run đến đúng đích/port.
5. DNS resolve tên DB đến đúng địa chỉ private, nếu ứng dụng dùng hostname.
6. Database user/IAM DB authentication và TLS được cấu hình đúng.

Direct VPC egress kiểm soát **outbound traffic** của Cloud Run; nó không tự làm HTTP endpoint Cloud Run chỉ nhận private ingress. Nếu cần khóa đầu vào, kiểm tra `ingress` và phương án load balancer phù hợp riêng.

### 7.2. Xác minh cấu hình VPC egress

~~~bash
gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=REGION

gcloud compute networks subnets describe TEST_SUBNET \
  --project=NETWORK_HOST_PROJECT_ID \
  --region=REGION

gcloud sql instances describe TEST_SQL_INSTANCE \
  --project=SQL_PROJECT_ID
~~~

Trong output, kiểm tra network/subnet, egress setting và địa chỉ private của Cloud SQL. Trên Shared VPC, network host project có thể khác service project và quyền dùng subnet cần được kiểm tra ở đúng project.

| Chế độ | Ý nghĩa |
| --- | --- |
| `private-ranges-only` | Lưu lượng đến địa chỉ private/internal phù hợp đi qua VPC; một số lưu lượng ra public API có thể theo đường mặc định Cloud Run. |
| `all-traffic` | Toàn bộ lưu lượng outbound đi qua VPC; nếu cần kết nối Internet, phải có Cloud NAT hoặc đường egress được cấu hình phù hợp. |

Đừng kết luận “đã có private egress” chỉ vì container truy cập được `storage.googleapis.com`: kết nối Google API có thể đi bằng cơ chế mạng khác. Kiểm tra route, DNS và egress config để chứng minh đường đi.

### 7.3. TCP probe trong chính workload

Một TCP probe trong Java có thể xác nhận endpoint private đang mở port. Chạy test **bên trong Cloud Run Job hoặc runner có cùng service identity và VPC egress**, không chạy từ laptop để suy ra đường mạng Cloud Run.

~~~java
package com.example.orders.it;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("gcp-private-network")
class PrivateSqlPathIT {
    @Test
    void canConnectToPostgresPort() throws IOException {
        String host = System.getenv("PRIVATE_DB_HOST");
        int port = Integer.parseInt(
            System.getenv().getOrDefault("PRIVATE_DB_PORT", "5432"));

        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), 5000);
            assertTrue(socket.isConnected());
        }
    }
}
~~~

Nếu test pass, mới khẳng định rằng **TCP port reachable**. Tiếp tục test JDBC (PostgreSQL driver + test DB credentials) mở connection rồi thực hiện `SELECT 1`, đồng thời dùng DB user readonly và kết nối TLS theo cấu hình. IAM `roles/cloudsql.client`, nếu dùng Cloud SQL Auth Proxy/connector, không tự tạo quyền SQL trên bảng. Database login/privileges và network reachability phải được kiểm chứng riêng.

### 7.4. Negative network test

Negative test phải gọi **cùng một private IP và port** từ workload không được phép (bị firewall, thiếu đường route hoặc nằm ngoài VPC). Kỳ vọng không mở được socket. Tuy nhiên, **timeout** có nhiều nguyên nhân: route sai, firewall deny, destination down, không có listener. Vì vậy cần positive control từ mạng được phép, kiểm tra service đích hoạt động và đối chiếu Connectivity Tests hoặc firewall logs.

| Kết quả | Diễn giải |
| --- | --- |
| DNS lookup thất bại | Kiểm tra private DNS zone, forwarding và hostname; chưa kết luận firewall. |
| TCP timeout | Kiểm tra route, firewall, VPC configuration và destination health. |
| Connection refused | Có thể đã đến host nhưng port không có listener, hoặc policy reject. |
| TCP connected nhưng JDBC auth failed | Mạng tới DB đã thông; lỗi ở credentials/TLS/DB permissions. |
| JDBC query bị permission denied | DB user không có quyền dữ liệu; không liên quan `roles/run.invoker`. |

Không dùng `ping` làm bằng chứng chính: nhiều endpoint không trả ICMP. Test từ Internet tới private IP không đủ để chứng minh firewall rules của workload cho phép/deny theo dự kiến, vì Internet thường vốn không có route đến private IP.

## 8. Dùng Connectivity Tests, firewall và DNS để điều tra

### 8.1. Connectivity Tests

**Network Intelligence Center → Connectivity Tests** phân tích đường đi cấu hình giữa các endpoint, bao gồm một số trường hợp VPC firewall, route, peering, VPN và load balancer. Với một số kịch bản, công cụ thực hiện data-plane probes. Chọn source, destination và port sát với test rồi kiểm tra hop bị drop.

Connectivity Tests có giới hạn theo loại endpoint và không thay thế integration test mở socket hoặc JDBC. Trong môi trường có mạng ngoài Google Cloud, công cụ không nhất thiết phân tích được toàn bộ thiết bị ngoài GCP.

### 8.2. Kiểm tra firewall và routing

Khi TCP bị chặn, hỏi tuần tự:

- Cloud Run egress có dùng đúng network/subnet và network tags không?
- VPC routes có đường tới private IP đích và đường trở về không?
- Firewall egress tại nguồn và ingress tại đích có cho phép TCP 5432 không?
- Priority của deny rule có thắng allow rule được kỳ vọng không?
- Với Shared VPC, Cloud Run service project có liên kết host VPC và identity có quyền cần thiết không?
- Có điều kiện Private Service Access, peering, Network Connectivity hoặc VPC Service Controls khác cần xét không?
- DNS trả về private IP mong muốn hay public IP?

Dùng **Firewall Rules Logging** khi cần quan sát firewall allow/deny trên phạm vi được hỗ trợ. **VPC Flow Logs** giúp phân tích traffic ở interface/subnet nhưng không nhất thiết ghi mọi packet bị chặn. Giữ kết quả Connectivity Tests và log ở phạm vi staging để điều tra, không in secrets.

### 8.3. Private Google Access không thay IAM

Private Google Access giúp tài nguyên không có external IP truy cập Google APIs bằng đường mạng phù hợp. Nó không tự thay thế IAM và cũng không tạo đường private đến tất cả hệ thống ứng dụng. DNS cho `private.googleapis.com` hoặc `restricted.googleapis.com` cần đúng kiến trúc và policy đã phê duyệt; đừng đổi DNS chỉ để một test pass.

Khi thử truy cập Google API qua private path, ghi lại DNS answer, route, VPC egress, firewall và kết quả IAM riêng. Việc API trả 200 không chứng minh lưu lượng đã đi theo đường private mong muốn.

## 9. Test runner và CI/CD

### 9.1. Chia test jobs theo principal và network

Một pipeline có thể gồm:

~~~mermaid
flowchart TD
  PLAN[Review IaC: IAM/VPC configuration] --> DEPLOY[Deploy staging revision]
  DEPLOY --> IA[Identity & ADC checks]
  DEPLOY --> POS[Allowed IAM test]
  DEPLOY --> NEG[Denied IAM test]
  DEPLOY --> INGRESS[Cloud Run Invoker/ingress tests]
  DEPLOY --> NET[Private TCP/JDBC tests]
  IA --> REPORT[Collect evidence]
  POS --> REPORT
  NEG --> REPORT
  INGRESS --> REPORT
  NET --> REPORT
  REPORT --> GATE{Expected outcomes met?}
  GATE -->|Yes| PROMOTE[Eligible for promotion]
  GATE -->|No| STOP[Block and investigate]
~~~

Mỗi job cần có danh tính và kết nối rõ ràng:

- **IAM-positive:** job chạy dưới `orders-runtime`, object fixture tồn tại và có thể đọc.
- **IAM-negative:** job khác chạy dưới `denied-runtime`, cùng object nhưng không có quyền.
- **Invoker:** hai caller SA khác nhau từ cùng nguồn mạng hợp lệ.
- **Network-positive:** runner trong VPC được phép, kết nối private DB thành công.
- **Network-negative:** runner trong vùng mạng bị từ chối, kiểm tra cùng private DB và port.

Dùng Workload Identity Federation hoặc service accounts gắn vào runner; hạn chế `roles/iam.serviceAccountTokenCreator` nếu phải impersonate. Không cấp Owner/Editor cho test runners chỉ để tránh lỗi.

### 9.2. Điều kiện tiên quyết và tính ổn định

1. Kiểm tra project, region và test fixtures trước khi chạy.
2. Ghi nhận principal thực tế, revision và VPC configuration của runner.
3. Đợi revision sẵn sàng và IAM policy propagation bằng retry có giới hạn.
4. Chạy positive control trước để xác nhận resource đích hoạt động.
5. Chạy negative test, phân loại status/network error thay vì chỉ pass/fail.
6. Thu thập log/audit evidence; dọn fixture được phép sau test.

Nếu negative test bất ngờ được phép, hãy xem IAM role kế thừa từ folder/organization, group binding, IAM condition hoặc danh tính chạy thật. Đừng thay đổi expected outcome để làm pipeline xanh.

### 9.3. Lưu bằng chứng không chứa credential

Ví dụ artifact JSON:

~~~json
{
  "testId": "IAM-03",
  "environment": "staging",
  "principal": "denied-runtime@PROJECT_ID.iam.gserviceaccount.com",
  "resource": "gs://TEST_BUCKET/fixtures/ping.json",
  "action": "storage.objects.get",
  "expected": "DENY",
  "actualHttpStatus": 403,
  "result": "PASS",
  "revision": "orders-api-00012",
  "timestamp": "2026-11-19T10:00:00Z"
}
~~~

Có thể ghi request ID/correlation ID, nhưng không lưu access token, ID token, service account keys, database password hoặc nội dung object nhạy cảm. Cloud Audit Logs có thể cần bật Data Access logs mới thấy một số thao tác đọc Storage; kiểm tra chính sách log và quyền đọc phù hợp.

## 10. Tình huống điều tra: deploy mới bị 403 và timeout

Một revision mới của `orders-api` trả `200` tại health endpoint, nhưng xử lý đơn hàng báo Storage `403` và Cloud SQL `timeout`.

Điều tra theo thứ tự:

1. So sánh service identity của revision cũ và mới. Nếu mới gắn nhầm default SA, xác minh bằng metadata server hoặc Cloud Audit Logs.
2. Gọi Storage test bằng chính revision mới. Dùng Policy Troubleshooter để kiểm tra principal/permission trên fixture.
3. Xem audit log để phân biệt IAM deny, VPC Service Controls hoặc lỗi API.
4. Kiểm tra Direct VPC egress, VPC/subnet, DNS và private IP của Cloud SQL bằng cấu hình thật.
5. Chạy TCP probe từ job cùng network; chạy Connectivity Tests nếu mất kết nối.
6. Chỉ khi TCP thông mới kiểm tra JDBC credentials, TLS và database permissions.
7. Rollback revision hoặc sửa identity/network config theo quy trình release, chạy lại cả positive và negative tests trước khi chuyển traffic.

Hai lỗi cùng xuất hiện sau deploy không có nghĩa chúng có cùng nguyên nhân. IAM trên Storage và đường TCP đến Cloud SQL là hai ranh giới phải được kiểm tra độc lập.

## 11. Troubleshooting nhanh

| Triệu chứng | Nguyên nhân thường gặp | Hành động |
| --- | --- | --- |
| Local test pass, Cloud Run 403 | Local ADC mạnh hơn runtime SA. | So sánh principal và IAM của revision. |
| Deploy được nhưng không đọc Storage | Runtime thiếu `storage.objects.get`. | Kiểm tra bucket/object policy và audit log. |
| Không attach được service account | Deployer thiếu `iam.serviceAccounts.actAs`. | Kiểm tra Service Account User tại đúng SA. |
| Cloud Run Invoker có role nhưng request bị chặn | Ingress internal, token thiếu/sai audience, hoặc IAM condition. | Test từ ingress hợp lệ rồi kiểm tra ID token và policy. |
| Policy Troubleshooter trả Unknown | Không xem được toàn bộ policies/roles hoặc thiếu condition context. | Xin quyền review phù hợp, bổ sung context. |
| IAM-negative test bất ngờ pass | Role kế thừa hoặc dùng sai principal. | Kiểm tra hierarchy, group và ADC. |
| Storage test 404 | Fixture sai bucket/object hoặc bị ẩn. | Xác minh bằng principal kiểm soát. |
| TCP private DB timeout | Route, firewall, subnet, egress setting, destination down. | Connectivity Tests, firewall logs, VPC config. |
| TCP thành công nhưng JDBC fail | Database authentication, TLS hoặc SQL privileges. | Kiểm tra credentials/DB roles riêng. |
| GKE workload lỗi IAM | Workload Identity Federation mapping sai. | Kiểm tra KSA/principal binding và caller thực tế. |
| Google API pass nhưng private path chưa được chứng minh | DNS hoặc route khác kỳ vọng. | Kiểm tra private DNS, egress, routing. |

## 12. Checklist hoàn thành

- [ ] Có ma trận principal × action × resource × network × expected outcome.
- [ ] Fixture staging tồn tại, có dữ liệu giả và không ảnh hưởng production.
- [ ] Có runtime SA được cấp quyền tối thiểu và denied SA riêng.
- [ ] Phân biệt deployer, runtime và invoker identities.
- [ ] Không dùng key JSON dài hạn trong Cloud Run/CI.
- [ ] Policy Troubleshooter kiểm tra allow/deny/conditions đúng resource.
- [ ] Storage positive test thành công dưới runtime SA hợp lệ.
- [ ] Storage negative test nhận lỗi dưới denied SA.
- [ ] Kiểm tra serviceAccountName của revision và principal thực tế.
- [ ] Invoker tests chạy từ nguồn vượt qua ingress policy.
- [ ] VPC egress, subnet, route, DNS và firewall khớp thiết kế.
- [ ] TCP probe chạy từ chính workload/runner có đường mạng tương đương.
- [ ] Có negative network test trên cùng destination với positive control.
- [ ] Phân biệt TCP reachability và database authentication/JDBC.
- [ ] Có Connectivity Tests/firewall log cho trường hợp network failure.
- [ ] CI phân tách job identities, giữ evidence và có timeout/retry hợp lý.
- [ ] Test không ghi token, password, private keys hoặc dữ liệu người dùng.

## Tài liệu tham khảo

- [Cloud Run service identity](https://docs.cloud.google.com/run/docs/securing/service-identity) — deployer identity, runtime identity, ADC và metadata server.
- [Configure service identity](https://docs.cloud.google.com/run/docs/configuring/services/service-identity) — gắn runtime SA và IAM.
- [Policy Troubleshooter](https://docs.cloud.google.com/policy-intelligence/docs/troubleshoot-access) — kiểm tra IAM allow/deny/conditions và các giới hạn.
- [Test IAM permissions](https://docs.cloud.google.com/iam/docs/testing-permissions) — self-check `testIamPermissions`.
- [Cloud Run service-to-service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service) — ID tokens và Invoker.
- [Cloud Run ingress](https://docs.cloud.google.com/run/docs/securing/ingress) — phân loại nguồn internal và network checks.
- [Cloud Run Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc) — network/subnet, egress modes và firewall.
- [Cloud SQL PostgreSQL from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run) — private IP và TCP connectivity.
- [Connectivity Tests overview](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview) — phân tích đường đi và data plane.
- [Private Google Access](https://docs.cloud.google.com/vpc/docs/private-google-access) — truy cập Google APIs từ mạng riêng.
- [Google Cloud Storage Java client](https://cloud.google.com/java/docs/reference/google-cloud-storage/latest/overview) — gọi Storage bằng ADC.

