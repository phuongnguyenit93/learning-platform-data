# Xác thực giữa các dịch vụ bằng danh tính workload

Trong kiến trúc serverless, một Java function thường gọi database, queue, object storage hoặc một HTTP service khác. Dịch vụ nhận request cần biết caller là ai và caller được phép làm gì. Nếu mọi function dùng chung một API key hoặc credential tĩnh, khi một thành phần bị lộ thì phạm vi ảnh hưởng có thể lan sang toàn hệ thống.

Workload identity giải quyết vấn đề này bằng cách cấp danh tính cho chính workload đang chạy. Nền tảng xác minh workload thông qua runtime, service account, execution role hoặc cơ chế federation, rồi cung cấp credential ngắn hạn để workload gọi dịch vụ khác. Danh tính được gắn với function, service hoặc Kubernetes workload, không phụ thuộc vào một người dùng đang đăng nhập.

Bài học này tập trung vào xác thực service-to-service cho Java serverless: phân biệt xác thực và phân quyền, lấy credential an toàn từ runtime, gọi dịch vụ đích, xác minh token inbound, giới hạn quyền và xử lý lỗi danh tính.

## 1. Workload identity là gì?

Workload identity là danh tính đại diện cho một ứng dụng hoặc process đang chạy. Ví dụ:

- Lambda function dùng execution role để gọi S3 hoặc DynamoDB.
- Cloud Run service chạy với một Google service account để truy cập Pub/Sub.
- Azure Function dùng managed identity để đọc Key Vault.
- Pod Kubernetes dùng service account và có thể liên kết với cloud identity thông qua workload identity federation.
- Một Java service dùng client certificate hoặc token OIDC để gọi service nội bộ.

Danh tính này cho phép hệ thống bảo mật trả lời: workload nào đang gọi, workload đó thuộc môi trường hoặc project nào, và nó có quyền gì?

Một workload identity thường có các thành phần:

1. **Subject/principal:** định danh workload, service account, role hoặc principal.
2. **Trust mechanism:** cách nền tảng chứng minh process đang chạy thuộc principal đó.
3. **Credential:** token, signed request hoặc certificate được dùng khi gọi dịch vụ.
4. **Policy:** quyền mà principal được phép thực hiện.
5. **Resource boundary:** tài nguyên đích chấp nhận principal nào.
6. **Audit trail:** log ghi nhận principal đã thực hiện hành động gì.

Credential không nhất thiết là một secret dài hạn. Nhiều nền tảng cấp token hoặc credential ngắn hạn qua metadata service, identity endpoint hoặc security token service.

## 2. Authentication và authorization

Hai khái niệm thường bị nhầm lẫn:

- **Authentication (xác thực):** xác minh caller là ai.
- **Authorization (phân quyền):** quyết định caller đó được phép thực hiện hành động nào trên tài nguyên nào.

Ví dụ, Java worker gọi service inventory-api:

1. Worker lấy danh tính workload từ runtime.
2. Worker trình credential cho inventory-api.
3. inventory-api xác minh issuer, chữ ký, audience và thời hạn của credential.
4. Service xác định principal tương ứng với worker.
5. Authorization policy kiểm tra worker có quyền invoice.read hay không.
6. Service trả kết quả hoặc từ chối.

Một token hợp lệ không đồng nghĩa có quyền truy cập mọi endpoint. Ngược lại, network connection thành công cũng không chứng minh caller được phép đọc dữ liệu.

| Lớp | Câu hỏi | Cơ chế ví dụ |
|---|---|---|
| Network | Có thể kết nối đến đích không? | VPC, firewall, network policy |
| Transport security | Kênh truyền có được mã hóa và xác minh peer không? | TLS, mTLS |
| Authentication | Caller là principal nào? | IAM role, service account, OIDC token |
| Authorization | Principal được làm gì? | IAM policy, RBAC, application permission |
| Application validation | Dữ liệu và ngữ cảnh nghiệp vụ có hợp lệ không? | Tenant check, ownership check, schema validation |

Các lớp này bổ sung cho nhau. Private network không thay thế authentication; TLS không tự cấp quyền nghiệp vụ; JWT hợp lệ không thay thế kiểm tra quyền trên từng tài nguyên.

## 3. Luồng gọi giữa hai workload

Giả sử orders-worker cần gọi inventory-api để giữ hàng. Một luồng an toàn có thể diễn ra như sau:

~~~mermaid
sequenceDiagram
    participant W as orders-worker
    participant I as Identity Provider / Runtime
    participant A as inventory-api
    participant P as Authorization Policy
    W->>I: Yêu cầu credential cho inventory-api
    I-->>W: Credential ngắn hạn
    W->>A: HTTPS request + credential
    A->>A: Xác minh issuer, signature, audience, expiry
    A->>P: Kiểm tra quyền principal trên action/resource
    P-->>A: Allow hoặc Deny
    A-->>W: Response
~~~

Credential cần được cấp cho đúng đích. Nếu token được phát cho inventory-api, không nên dùng token đó để gọi một service khác có audience khác. Việc ràng buộc audience giảm khả năng token bị dùng lại ở nơi không dự định.

Workload identity giúp tránh phải nhúng API key hoặc service account private key vào source code, container image hay file cấu hình. Runtime hoặc identity provider quản lý quá trình cấp và làm mới credential.

## 4. Danh tính outbound và inbound

Cần thiết kế cả hai phía của kết nối:

- **Outbound identity:** Java service chứng minh danh tính của mình khi gọi một dịch vụ khác.
- **Inbound identity:** Java service xác minh danh tính của caller khi nhận request.

Ví dụ orders-api gọi payment-service:

- orders-api cần credential có audience phù hợp với payment-service.
- payment-service cần xác minh credential và ánh xạ principal sang policy.
- Policy chỉ cho orders-api gọi các thao tác cần thiết, ví dụ tạo payment intent.
- orders-api không được mặc định có quyền refund, xem mọi giao dịch hoặc quản trị payment service.

Nếu chỉ cấu hình outbound credential mà service đích không xác minh caller, endpoint có thể vẫn bị gọi bởi principal khác. Nếu chỉ xác minh inbound mà caller không có cách lấy credential đáng tin cậy, request sẽ thất bại.

### 4.1. Service identity và end-user identity

Một request có thể mang cả danh tính service và danh tính người dùng:

- Service identity cho biết workload nào đang thực hiện lời gọi.
- End-user identity cho biết người dùng nào khởi tạo nghiệp vụ.

Ví dụ, API gateway xác thực người dùng Alice rồi gọi orders-service. Service identity là api-gateway; user identity là Alice. orders-service cần biết cả hai khi policy yêu cầu: gateway được phép gọi endpoint, nhưng Alice chỉ được đọc đơn hàng của chính mình.

Không nên thay thế end-user identity bằng service identity. Nếu mọi request đều được xử lý như cùng một service account mà không giữ user context đã xác minh, authorization theo người dùng có thể bị bỏ qua.

Khi chuyển user context giữa service, chỉ chuyển token hoặc claim theo thiết kế tin cậy, có audience và thời hạn rõ ràng. Không tin một header X-User-Id do client công khai tự gửi.

## 5. Credential ngắn hạn và vòng đời

Credential dài hạn như API key hoặc private key có thể tồn tại nhiều tháng. Nếu bị lộ, attacker có thể sử dụng cho đến khi credential bị thu hồi hoặc hết hạn.

Credential ngắn hạn giảm khoảng thời gian rủi ro:

1. Runtime chứng minh workload thuộc một principal.
2. Identity provider cấp token hoặc credential với thời hạn ngắn.
3. SDK hoặc ứng dụng dùng credential để ký request.
4. Credential được làm mới khi cần.
5. Policy có thể thay đổi mà không cần thay key trong image.

Một số loại credential:

| Credential | Dùng để | Lưu ý |
|---|---|---|
| OAuth 2.0 access token | Gọi API được bảo vệ | Có expiry, scope/audience tùy hệ thống |
| OIDC ID token | Chứng minh identity với một audience cụ thể | Không mặc định dùng thay access token cho mọi API |
| AWS temporary credentials | Ký AWS API request bằng SigV4 | Có access key, secret key và session token tạm thời |
| X.509 client certificate | Xác thực peer trong mTLS | Cần quản lý cấp phát, rotation và trust chain |
| Kubernetes projected service account token | Chứng minh identity của Pod | Có audience và thời hạn, có thể dùng federation |

Không nhầm access token và ID token. Access token thường đại diện quyền truy cập API; ID token mang identity assertion dành cho audience. Dịch vụ đích phải xác minh đúng loại credential theo giao thức mà nó hỗ trợ.

## 6. Các mô hình workload identity trên cloud

Mỗi cloud provider có cách triển khai riêng, nhưng nguyên tắc chung là dùng danh tính gắn với runtime và credential ngắn hạn.

| Nền tảng | Danh tính workload | Cơ chế thường dùng |
|---|---|---|
| AWS Lambda | Execution role | STS temporary credentials qua runtime credential provider |
| Google Cloud Run / Functions | Service account gắn với workload | Application Default Credentials và metadata server |
| Azure Functions | Managed identity | Azure Identity library và token credential |
| Kubernetes | ServiceAccount | Projected token, OIDC federation hoặc cloud workload identity integration |

Tên API và quyền cụ thể khác nhau theo dịch vụ. Không sao chép policy của một nền tảng sang nền tảng khác. Hãy dùng cơ chế identity native của runtime và SDK chính thức.

### 6.1. AWS Lambda execution role

Mỗi Lambda function có thể gắn execution role riêng. Khi function chạy, AWS cung cấp temporary credentials cho role thông qua runtime credential provider. AWS SDK for Java v2 có thể tự tìm credential theo default credentials provider chain.

Ví dụ gọi S3 bằng Java:

~~~java
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

public final class ReportReader {

    private final S3Client s3 = S3Client.create();

    public String readReport(String bucket, String key) {
        var request = GetObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build();

        return s3.getObjectAsBytes(request).asUtf8String();
    }
}
~~~

S3Client.create() dùng credential provider mặc định của AWS SDK. Trong Lambda, SDK lấy temporary credentials của execution role. Local development có thể dùng profile hoặc credential provider khác theo môi trường.

Không tạo access key IAM user rồi đóng gói vào Lambda environment variables. Cấp quyền s3:GetObject trên đúng bucket/prefix cần đọc. Nếu function chỉ cần đọc report, không cấp quyền xóa bucket hoặc quản trị S3.

### 6.2. Google Cloud service account

Cloud Run service hoặc Cloud Functions có thể chạy dưới một user-managed service account. Ứng dụng Java dùng Application Default Credentials (ADC) để lấy credential từ môi trường runtime.

Ví dụ khởi tạo client Google Cloud Storage:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public final class StorageAccess {

    private final Storage storage =
            StorageOptions.getDefaultInstance().getService();

    public byte[] readObject(String bucket, String objectName) {
        return storage.readAllBytes(bucket, objectName);
    }
}
~~~

Trong môi trường Google Cloud được cấu hình đúng, ADC tìm credential do runtime cung cấp cho service account. Không cần tải service account JSON key vào container.

Nếu gọi một Cloud Run service khác được bảo vệ bằng IAM, caller thường cần lấy OIDC ID token có audience là URL/service audience đích và có quyền roles/run.invoker trên service đó. Token dùng để xác thực caller với Cloud Run; nó không thay thế access token dùng cho các API Google Cloud khác.

### 6.3. Azure managed identity

Azure Functions có thể bật system-assigned hoặc user-assigned managed identity. Java SDK dùng Azure Identity library để lấy token mà không lưu client secret trong ứng dụng.

Ví dụ truy cập Key Vault:

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

public final class VaultAccess {

    private final SecretClient client =
            new SecretClientBuilder()
                    .vaultUrl("https://example-vault.vault.azure.net/")
                    .credential(new DefaultAzureCredentialBuilder().build())
                    .buildClient();

    public String readSecret(String name) {
        return client.getSecret(name).getValue();
    }
}
~~~

DefaultAzureCredential chọn credential phù hợp với môi trường. Trong Azure runtime có managed identity, SDK có thể lấy token từ identity endpoint. Local development có thể dùng developer credential đã đăng nhập.

Managed identity vẫn cần role assignment hoặc access policy đúng trên Key Vault. Có identity không có nghĩa mặc định được đọc mọi secret.

## 7. Kubernetes service account và workload identity federation

Khi Java workload chạy trên Kubernetes, Pod có thể được gắn Kubernetes ServiceAccount. Pod nhận token projected từ service account theo cấu hình cluster. Token này có thể được dùng để xác thực với Kubernetes API hoặc trao đổi với cloud identity provider thông qua OIDC federation.

Luồng federation khái quát:

1. Pod nhận projected service account token.
2. Token chứng minh namespace, service account và audience.
3. Cloud Security Token Service hoặc identity provider xác minh token dựa trên OIDC issuer của cluster.
4. Policy trust ánh xạ subject/service account được phép sang cloud principal.
5. Workload nhận credential ngắn hạn để gọi cloud API.

~~~mermaid
flowchart TD
    P["Java Pod + Kubernetes ServiceAccount"] --> T["Projected OIDC token"]
    T --> S["Cloud STS / Identity Provider"]
    S --> V["Validate issuer, subject, audience"]
    V --> R["Federated role / service account"]
    R --> C["Short-lived cloud credentials"]
    C --> A["Cloud API"]
~~~

Federation tránh phải lưu cloud private key trong Kubernetes Secret. Tuy nhiên, trust policy cần giới hạn đúng issuer, namespace, service account và audience. Nếu trust policy cho phép mọi service account trong cluster, một Pod bị xâm nhập có thể lấy credential rộng hơn dự định.

Không gắn cùng một service account quyền admin cho toàn bộ workload. Tạo identity riêng cho từng ứng dụng hoặc nhóm trách nhiệm và cấp quyền theo nguyên tắc least privilege.

## 8. OIDC token, issuer và audience

OIDC ID token thường là JWT có chữ ký. Khi nhận token, service đích cần kiểm tra tối thiểu:

- **Signature:** chữ ký hợp lệ theo key của issuer tin cậy.
- **Issuer (iss):** đúng identity provider được cấu hình.
- **Audience (aud):** token được phát cho service hiện tại.
- **Expiry (exp):** token chưa hết hạn.
- **Not before (nbf):** token đã có hiệu lực.
- **Subject (sub):** principal phù hợp với policy.
- **Authorized party (azp) hoặc client ID:** kiểm tra khi giao thức yêu cầu.
- **Key rotation:** lấy signing key theo kid từ JWKS của issuer và xử lý cache/rotation an toàn.

Không chỉ decode JWT rồi tin payload. Decode không xác minh chữ ký. Không chấp nhận thuật toán chữ ký tùy ý do header token tự khai báo; cấu hình thuật toán và issuer được tin cậy ở server.

Audience là một ranh giới quan trọng. Token có aud=inventory-api không nên được chấp nhận bởi payment-api chỉ vì cùng issuer. Mỗi service nên có audience ổn định, rõ ràng và chỉ chấp nhận token được phát cho nó.

Nếu token chứa scope hoặc roles, service vẫn phải ánh xạ các claim đó vào policy cụ thể. Không dùng một claim tùy ý từ token chưa được xác minh để quyết định quyền.

### 8.1. Xác minh JWT trong Java

Có thể dùng thư viện OIDC/JWT đã được duy trì thay vì tự viết thuật toán xác minh. Với Spring Security Resource Server, ứng dụng có thể cấu hình issuer URI để framework tải metadata và JWKS, kiểm tra chữ ký, issuer, thời hạn và audience theo cấu hình.

Ví dụ cấu hình Spring Security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/health").permitAll()
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Cấu hình trên minh họa bật JWT resource server. Ứng dụng cần cấu hình issuer-uri hoặc jwk-set-uri trong application config. Audience validation có thể cần validator bổ sung theo issuer và framework version; không mặc định rằng chỉ cấu hình issuer đã kiểm tra audience theo yêu cầu của service.

Ví dụ properties:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://identity.example.com/
~~~

Sau khi xác thực token, cần authorization ở tầng method hoặc service để kiểm tra principal có quyền gọi operation và truy cập tài nguyên cụ thể hay không.

## 9. Gọi Cloud Run service bằng OIDC ID token

Một Cloud Run service có thể yêu cầu IAM authentication. Service gọi cần có quyền invoke trên service đích và tạo ID token có audience phù hợp. Audience thường là URL gốc của service hoặc audience tùy chỉnh đã cấu hình.

Ví dụ Java dùng Google Auth Library để lấy ID token từ ADC:

~~~java
import com.google.auth.oauth2.IdTokenCredentials;
import com.google.auth.oauth2.IdTokenProvider;
import com.google.auth.oauth2.GoogleCredentials;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public final class CloudRunCaller {

    private final HttpClient httpClient = HttpClient.newHttpClient();

    public HttpResponse<String> call(
            String targetUrl,
            String audience) throws Exception {

        GoogleCredentials credentials =
                GoogleCredentials.getApplicationDefault();

        if (!(credentials instanceof IdTokenProvider idTokenProvider)) {
            throw new IllegalStateException(
                    "The runtime credential provider cannot mint ID tokens");
        }

        IdTokenCredentials idTokenCredentials =
                IdTokenCredentials.newBuilder()
                        .setIdTokenProvider(idTokenProvider)
                        .setTargetAudience(audience)
                        .build();

        var idToken = idTokenCredentials.refreshAccessToken();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(targetUrl))
                .header("Authorization", "Bearer " + idToken.getTokenValue())
                .GET()
                .build();

        return httpClient.send(
                request, HttpResponse.BodyHandlers.ofString());
    }
}
~~~

Đây là ví dụ minh họa; credential provider của môi trường phải hỗ trợ cấp ID token. Trong một số môi trường hoặc phiên bản thư viện, có thể cần dùng IdTokenProvider trực tiếp từ ADC hoặc API credential tương ứng. Đảm bảo dependency Google Auth Library đúng phiên bản và test trong runtime thật.

Audience phải khớp cấu hình xác thực của service đích. Caller cũng cần role roles/run.invoker trên service đó. Nếu token sai audience hoặc caller thiếu quyền, request thường bị từ chối dù URL có thể truy cập qua mạng.

Không gửi ID token đến URL tùy ý do input người dùng cung cấp. Nếu attacker điều khiển target URL, ứng dụng có thể vô tình gửi bearer token đến server của attacker. Dùng allowlist cho service đích và audience.

## 10. AWS service-to-service authentication

Trong AWS, nhiều API dịch vụ được bảo vệ bằng IAM và chữ ký SigV4 thay vì bearer ID token. Java service dùng AWS SDK với credential provider lấy temporary credentials từ execution role hoặc role được assume.

Một function gọi service AWS khác thường cần:

1. Execution role riêng.
2. Permission trên action và resource cụ thể.
3. Resource policy của dịch vụ đích nếu dịch vụ yêu cầu.
4. SDK ký request bằng SigV4.
5. Audit bằng CloudTrail hoặc log tương ứng.

Nếu một Lambda gọi API Gateway private hoặc service HTTP tùy chỉnh, có thể dùng IAM authorization/SigV4 nếu endpoint hỗ trợ, hoặc OIDC/mTLS theo thiết kế của hệ thống. Không giả định mọi HTTP service trên AWS tự động xác thực bằng execution role.

Khi cần truy cập tài khoản AWS khác, có thể dùng STS AssumeRole với trust policy giới hạn principal được phép assume và session policy nếu cần thu hẹp quyền. Không dùng một role xuyên tài khoản có quyền rộng cho mọi function.

## 11. Azure managed identity và service-to-service

Với Azure, managed identity cho phép workload lấy access token cho resource/audience đích. Service đích cần xác minh token qua Microsoft Entra ID và áp dụng authorization phù hợp.

Một mô hình thường gặp:

1. Function A có managed identity.
2. Identity được cấp quyền gọi API hoặc resource của service B.
3. Function A dùng Azure Identity SDK lấy token cho scope/resource tương ứng.
4. Function A gửi token qua HTTPS.
5. Service B xác minh token và kiểm tra quyền.

System-assigned identity gắn với vòng đời resource; user-assigned identity có thể được gắn vào nhiều resource và tồn tại độc lập. Chọn theo yêu cầu lifecycle, reuse và quyền. Nếu dùng chung identity cho nhiều workload, một workload bị xâm nhập có thể kế thừa phạm vi quyền của identity đó.

## 12. Least privilege và phân tách danh tính

Một nguyên tắc quan trọng là mỗi workload chỉ có danh tính và quyền cần thiết cho nhiệm vụ của nó.

Ví dụ:

| Workload | Quyền cần | Không nên có |
|---|---|---|
| orders-api | Ghi order, publish order-created | Quản trị payment hoặc đọc mọi secret |
| payment-worker | Gọi payment provider, cập nhật payment state | Xóa order hoặc quản trị cluster |
| report-job | Đọc dữ liệu báo cáo, ghi file kết quả | Ghi dữ liệu giao dịch gốc |
| notification-worker | Gửi email/SMS qua provider | Đọc payment credential nếu không cần |
| deployment pipeline | Triển khai đúng service và version | Runtime access đến dữ liệu khách hàng |

Tách service account hoặc role theo workload giúp giới hạn blast radius. Khi một function bị xâm nhập, attacker chỉ có thể sử dụng quyền của function đó, thay vì quyền chung của cả ứng dụng.

Không cấp quyền theo kiểu wildcard nếu có thể chỉ rõ action và resource. Review cả identity policy lẫn resource-based policy, vì quyền hiệu lực có thể đến từ nhiều nơi và bị ảnh hưởng bởi explicit deny, permission boundary hoặc organization policy.

### 12.1. Phân quyền theo tài nguyên và tenant

Service identity chỉ trả lời workload nào đang gọi. Nếu service phục vụ nhiều tenant, cần kiểm tra tenant/resource ở tầng ứng dụng.

Ví dụ orders-worker có quyền gọi orders-api, nhưng không có nghĩa nó được phép truy cập mọi tenant. Request cần mang tenant context đã được xác thực từ nguồn tin cậy. Service đích phải kiểm tra order thuộc tenant nào trước khi đọc hoặc thay đổi.

Không lấy tenant ID từ một header tùy ý mà không xác minh. Với event, kiểm tra producer được phép phát event cho tenant đó và dữ liệu liên kết với bản ghi nguồn có thẩm quyền.

## 13. mTLS và service mesh

Một lựa chọn khác cho service-to-service authentication là mutual TLS (mTLS). Trong TLS thông thường, client xác minh server certificate. Với mTLS, server cũng yêu cầu client certificate để xác minh danh tính client.

mTLS có thể được triển khai ở:

- Service mesh như Istio hoặc Linkerd.
- Sidecar proxy.
- API gateway hoặc ingress.
- HTTP client/server trực tiếp bằng certificate.

Service mesh có thể tự động cấp và rotate certificate cho workload, áp dụng policy giữa namespace/service account và mã hóa traffic nội bộ.

mTLS xác thực peer ở tầng transport. Ứng dụng vẫn cần authorization nghiệp vụ: một service certificate hợp lệ không đồng nghĩa có quyền gọi mọi operation. Kết hợp mTLS với policy theo service identity và authorization trong ứng dụng khi cần.

Nếu dùng mTLS, cần quản lý CA trust, certificate rotation, expiry, SAN identity và hành vi khi proxy/control plane không khả dụng. Không tự tạo một CA dùng chung rồi phân phối private key của CA cho mọi container.

## 14. Rotation, cache và xử lý credential hết hạn

Credential ngắn hạn cần được làm mới trước khi hết hạn. SDK chính thức thường có credential provider tự refresh. Tránh tự cache access token trong static field đến khi hết hạn mà không có cơ chế refresh.

Các nguyên tắc:

- Ưu tiên SDK credential provider mặc định của nền tảng.
- Không log access token, refresh token, session token hoặc private key.
- Cache token theo audience/scope phù hợp và tôn trọng expiry.
- Làm mới trước khi token hết hạn, có jitter để tránh nhiều instance refresh cùng lúc.
- Khi nhận 401 do token hết hạn, refresh theo cơ chế thư viện và retry có giới hạn.
- Không retry vô hạn với 403 vì lỗi thường là permission/policy.
- Khi rotate certificate hoặc key, hỗ trợ giai đoạn overlap giữa credential cũ và mới nếu hệ thống cho phép.

Nếu nhiều function khởi động đồng thời và cùng refresh credential, có thể tạo burst đến identity provider. SDK provider có thể quản lý refresh/cache ở phạm vi process; vẫn cần quan sát latency và lỗi identity endpoint.

## 15. Network, private endpoint và danh tính

Một service có thể nằm trong private network nhưng vẫn cần xác thực workload. Network policy giúp giới hạn nơi có thể kết nối; identity giúp xác định ai đang kết nối.

Ví dụ, chỉ workload trong VPC mới kết nối được database, nhưng database user hoặc IAM database authentication vẫn cần xác minh quyền. Tương tự, một internal HTTP API chỉ có private IP vẫn cần mTLS, JWT hoặc IAM authorization nếu dữ liệu có rủi ro.

Không dùng allowlist IP làm danh tính duy nhất. IP có thể thay đổi khi autoscaling, NAT hoặc triển khai lại. Dùng identity principal ổn định để policy theo service, và dùng network controls như một lớp bổ sung.

Nếu service gọi qua private endpoint, DNS và TLS hostname cần khớp với certificate. Không tắt certificate verification để vượt lỗi hostname. Sửa DNS, SAN hoặc endpoint configuration đúng cách.

## 16. Audit và quan sát danh tính

Khi có sự cố truy cập, cần trả lời:

- Workload nào đã gọi?
- Principal hoặc service account nào được dùng?
- Gọi resource và action nào?
- Credential issuer và audience là gì?
- Policy nào cho phép hoặc từ chối?
- Request đến từ revision/version nào?
- Có thay đổi IAM hoặc trust policy gần thời điểm lỗi không?

Nên log principal name, service name, target service, operation, result, request/trace ID và policy decision code. Không log raw token, private key, session credential hoặc full Authorization header.

Cloud audit logs có thể ghi lại principal và hành động ở tầng cloud. Application log bổ sung ngữ cảnh nghiệp vụ. Trace context giúp nối outbound call với inbound request.

Các chỉ số hữu ích:

- Tỷ lệ 401 và 403 theo target service.
- Token acquisition latency và error rate.
- Credential refresh failure.
- mTLS handshake failure và certificate expiry.
- IAM denied action theo principal.
- Outbound call latency theo service.
- Số lần retry do auth failure.

Một đợt tăng 403 thường là dấu hiệu policy hoặc resource permission sai; tăng 401 có thể do token thiếu, issuer/audience sai, chữ ký không hợp lệ hoặc token hết hạn. Không xử lý cả hai bằng cách cấp quyền rộng hơn.

## 17. Kiểm thử service identity

Cần kiểm tra cả trường hợp được phép và bị từ chối:

1. Workload đúng principal gọi đúng service và đúng operation.
2. Workload khác principal gọi cùng operation phải bị từ chối.
3. Token có issuer không tin cậy.
4. Token có audience sai.
5. Token hết hạn hoặc chưa đến thời điểm hiệu lực.
6. Token có chữ ký sai hoặc key ID không còn hợp lệ.
7. Principal hợp lệ nhưng thiếu IAM permission.
8. Caller có quyền invoke service nhưng không có quyền trên tenant/resource.
9. Credential refresh khi token gần hết hạn.
10. Identity provider tạm thời không khả dụng.
11. Resource policy và identity policy xung đột.
12. Workload được triển khai ở môi trường test không thể truy cập secret production.
13. mTLS certificate hết hạn hoặc không có SAN phù hợp.
14. Log và trace không chứa credential nhạy cảm.

Integration test cần chạy trong môi trường có identity thực hoặc test identity provider tương đương. Unit test có thể mock credential provider và authorization service, nhưng không chứng minh IAM trust policy hoặc audience cấu hình đúng.

## 18. Quy trình thiết kế workload identity cho Java

1. **Liệt kê luồng gọi.** Xác định service nào gọi service nào, API/resource nào được truy cập.
2. **Chọn principal riêng.** Gắn role hoặc service account cho từng workload hoặc nhóm trách nhiệm.
3. **Dùng credential ngắn hạn.** Ưu tiên execution role, managed identity, ADC hoặc federation.
4. **Cấu hình trust.** Giới hạn issuer, subject, namespace, service account và audience.
5. **Cấp quyền tối thiểu.** Chỉ cho phép action và resource cần thiết.
6. **Xác minh inbound.** Kiểm tra chữ ký, issuer, audience, expiry và principal.
7. **Kiểm tra authorization nghiệp vụ.** Xác minh operation, tenant và ownership của tài nguyên.
8. **Dùng SDK chính thức.** Để SDK quản lý credential acquisition, signing và refresh.
9. **Bảo vệ network.** Dùng TLS/mTLS, private endpoint và network policy khi phù hợp.
10. **Audit và cảnh báo.** Theo dõi 401/403, token refresh, IAM deny và certificate expiry.
11. **Kiểm thử negative cases.** Xác minh workload trái phép bị từ chối và secret không bị lộ.

Workload identity giúp mỗi Java function hoặc service có danh tính riêng và credential ngắn hạn. Khi kết hợp trust policy, audience validation, IAM least privilege và authorization nghiệp vụ, các service có thể gọi nhau an toàn mà không cần chia sẻ một key tĩnh cho toàn hệ thống.

## 19. Câu hỏi tự kiểm tra

- Workload identity đại diện cho ai trong hệ thống?
- Authentication khác authorization như thế nào?
- Vì sao network private không thay thế service authentication?
- Outbound identity và inbound identity khác nhau ở đâu?
- Vì sao access token và ID token không thể dùng thay thế tùy ý?
- Audience claim ngăn token bị dùng sai đích như thế nào?
- AWS Lambda execution role cung cấp credential cho Java SDK ra sao?
- Google ADC và Cloud Run service account giúp tránh service account key như thế nào?
- Azure managed identity khác client secret ở điểm nào?
- Kubernetes workload identity federation xác minh Pod bằng những claim nào?
- Vì sao mTLS vẫn cần authorization ở tầng ứng dụng?
- Cần log gì để điều tra 401/403 mà không làm lộ token?
- Làm thế nào để một service không thể truy cập dữ liệu của tenant khác?

