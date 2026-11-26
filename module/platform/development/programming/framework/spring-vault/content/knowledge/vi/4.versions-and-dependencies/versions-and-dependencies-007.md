# Phụ thuộc SDK riêng của từng phương thức xác thực cloud

Khi ứng dụng Java dùng **Spring Vault** để đọc KV secrets bằng `VaultTemplate`, quản lý token/lease, gọi Transit encryption hay PKI, câu hỏi đầu tiên là **ứng dụng lấy Vault token bằng danh tính workload nào?** Nếu chạy trên AWS, Azure hoặc Google Cloud, Spring Vault có thể sử dụng danh tính do môi trường cloud cung cấp để đăng nhập HashiCorp Vault. Tuy vậy, **mỗi phương thức xác thực cần loại thông tin và dependency khác nhau**: phương thức lấy identity document/JWT từ metadata service thường không cần SDK cloud, còn phương thức phải ký AWS STS request hoặc gọi Google IAM Credentials API cần thư viện tương ứng.

**Chương:** Phiên bản và phụ thuộc. Bài học tập trung vào việc chọn đúng SDK cho các phương thức xác thực cloud, phân biệt Spring Vault Core với Spring Cloud Vault starter và xác minh toàn bộ luồng từ workload identity đến Vault ACL.

Sau bài học, người học cần có thể:

- Nhận diện sự khác nhau giữa **AWS IAM và AWS EC2**, **GCP IAM và GCP GCE**, **Azure MSI**, **Kubernetes/JWT** và AppRole.
- Khai báo SDK **chỉ cho phương thức thực sự dùng**, tránh nạp SDK AWS/GCP/Azure hàng loạt.
- Phân biệt danh tính của cloud provider, **Vault login token**, **Vault policy** và các **lease của secret động**.
- Kiểm tra dependency tree, vòng đời token, ràng buộc Vault role và xử lý lỗi 401/403/metadata/SDK khi tích hợp.

> **Mốc tham chiếu: 25/11/2026.** Ví dụ Java hướng tới **Spring Vault 4.1.2**, Java 17+ và Spring Framework 7.0.11+. Có một chi tiết cần chú ý: một số đoạn văn/ví dụ trong trang *Authentication Methods* vẫn dùng tên lớp AWS SDK v1 hoặc phương thức Google IAM cũ, trong khi **Javadoc 4.1** đã công bố chữ ký mới. Đối với code Java, kiểm tra **Javadoc và kiểu tham số của artifact đang build** trước khi chọn SDK.

## 1. SDK cloud tham gia vào bước nào?

```text
                 AWS / Azure / GCP / Kubernetes
                       Workload Identity
                    (metadata, SDK, JWT)
                              │
                              ▼
               Spring Vault ClientAuthentication
                   + AuthenticationOptions
                              │
                  POST /v1/auth/<mount>/login
                              │
                              ▼
                     HashiCorp Vault
           Xác minh IAM/JWT/metadata + Vault role
                              │
                              ▼
                   Vault LoginToken / TTL
                              │
                              ▼
           SessionManager / VaultTemplate / VaultClient
                              │
                    Vault ACL policies
                              │
                              ▼
                KV · Transit · PKI · leases
```

Tách bốn khái niệm:

1. **Cloud identity:** IAM role, service account, managed identity hoặc Kubernetes ServiceAccount của workload. Nó giúp chứng minh ứng dụng *là ai*.
2. **Cloud SDK / metadata client:** chỉ là công cụ lấy credential hoặc tạo bằng chứng có chữ ký. Nó không tự cấp quyền đọc secret ở Vault.
3. **Vault auth role và token:** Vault xác minh bằng chứng, áp role để phát token có TTL và policy.
4. **Secret engine và lease:** policy của Vault token quyết định có được đọc KV, gọi Transit/PKI hay lấy dynamic credential. TTL token và TTL lease là hai vòng đời khác nhau.

Ví dụ một pod có IAM role AWS hợp lệ vẫn nhận `403` khi gọi `secret/data/orders` nếu Vault policy thiếu `read`. Việc thêm đủ AWS SDK sẽ không thay đổi ACL.

## 2. Ma trận dependency theo phương thức xác thực

| Môi trường / phương thức | API trong Spring Vault Core | Nguồn bằng chứng | SDK bổ sung khi dùng API đó | Ghi chú |
| --- | --- | --- | --- | --- |
| **AWS IAM** | `AwsIamAuthentication` | AWS credentials ký request STS `GetCallerIdentity` | **AWS SDK v2**: `software.amazon.awssdk:auth` và các dependency AWS SDK liên quan theo BOM | Chọn credentials provider cho EC2/ECS/Lambda/IRSA; Vault xác minh request đã ký |
| **AWS EC2** | `AwsEc2Authentication` | PKCS#7 instance identity document từ EC2 metadata | **Không bắt buộc AWS SDK** chỉ để đọc metadata | IMDSv2/nonce và ràng buộc EC2 instance/AMI/Vault role cần kiểm tra |
| **Azure MSI** | `AzureMsiAuthentication` | Managed identity token và thông tin VM từ Azure IMDS | **Không bắt buộc Azure SDK** cho phương thức có sẵn | Không tự thêm `azure-identity` chỉ vì ứng dụng chạy trên Azure VM |
| **GCP GCE** | `GcpComputeAuthentication` | Signed instance JWT từ Google metadata server | **Không bắt buộc Google IAM Credentials SDK** | Cần môi trường GCE/metadata hợp lệ và role Vault GCP phù hợp |
| **GCP IAM** | `GcpIamCredentialsAuthentication` | JWT được ký bằng `projects.serviceAccounts.signJwt` | **Google IAM Credentials SDK**: `com.google.cloud:google-cloud-iamcredentials` cùng dependency đi kèm | Cần `iam.serviceAccounts.signJwt`; API này dùng luồng đồng bộ |
| **Kubernetes** | `KubernetesAuthentication` | ServiceAccount JWT trong pod | **Không bắt buộc Kubernetes Java client** chỉ để login | Vault xác minh qua TokenReview hoặc cơ chế cấu hình của auth mount |
| **JWT/OIDC token đã cấp** | `JwtAuthentication` | JWT do hệ thống identity cung cấp | **Không bắt buộc SDK cloud** nếu đã có JWT supplier | Vault role xác minh issuer/audience/claims |
| **AppRole** | `AppRoleAuthentication` | Role ID + Secret ID hoặc wrapped token | **Không bắt buộc SDK cloud** | Phải phân phối Secret ID an toàn và quản lý TTL/usage |
| **TLS certificate** | `ClientCertificateAuthentication` | Client certificate và private key | **Không bắt buộc SDK cloud**; cần TLS keystore/truststore | Vault role dựa trên cert/CA |

**Đây là ma trận cho Spring Vault Core 4.1.** Nếu chỉ cấu hình **Spring Cloud Vault** qua starter và properties, các thư viện SDK có thể được starter/BOM quản lý theo cách riêng; kiểm tra **phiên bản thực tế trên classpath**. Không suy rằng một artifact SDK có thể thay thế cho tất cả các API hoặc thế hệ Spring Vault.

### Quy tắc chọn nhanh

- Muốn đăng nhập Vault từ **AWS ECS/EKS/EC2 bằng AWS IAM role** và dùng `AwsIamAuthentication`: chuẩn bị **AWS SDK credential/signing** phù hợp với API bản đang chạy.
- Muốn chứng minh **EC2 instance identity** qua PKCS#7: xét `AwsEc2Authentication` và IMDS, không mặc định cần AWS SDK IAM.
- Trên **Azure VM** có managed identity: xét `AzureMsiAuthentication` và Azure metadata endpoint; chưa cần cài Azure Java SDK riêng chỉ để login.
- Trên **GCE VM**: xét `GcpComputeAuthentication` và instance JWT từ metadata.
- Khi cần gọi **Google IAM Credentials `signJwt`**: chọn `GcpIamCredentialsAuthentication` và SDK IAM Credentials.
- Trên **Kubernetes đa cloud**: thường có thể chọn Kubernetes/JWT auth, giảm phụ thuộc vào SDK của cloud provider. Quyết định vẫn dựa trên threat model và auth mount của Vault.

Nguồn: [Spring Vault 4.1.2 – Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html), [Spring Vault 4.1 – Authentication API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/package-summary.html).

## 3. AWS IAM: vì sao cần AWS SDK, và phải là thế hệ nào?

### 3.1. Cơ chế `GetCallerIdentity`

`AwsIamAuthentication` dùng AWS credentials của workload để tạo **request STS `GetCallerIdentity` đã ký bằng AWS Signature Version 4**. Request được gửi tới Vault; Vault thực thi/xác minh request với AWS STS, đối chiếu IAM principal với Vault role và cấp Vault token. Credentials có thể đến từ instance profile, ECS task role, IRSA hoặc môi trường AWS hỗ trợ provider chain, **không phải access key hard-code**.

```text
AWS workload identity
    └─ AwsCredentialsProvider (AWS SDK)
             └─ ký request STS GetCallerIdentity
                       └─ gửi signed request đến Vault
                               └─ Vault xác minh với AWS STS
                                    └─ Vault role → Vault token
```

**Điểm dễ nhầm trong tài liệu:**

- Javadoc Spring Vault **4.1** định nghĩa `AwsIamAuthenticationOptions.Builder.credentialsProvider(software.amazon.awssdk.auth.credentials.AwsCredentialsProvider)` và `credentials(software.amazon.awssdk.auth.credentials.AwsCredentials)`, tức **AWS SDK v2**.
- Trang hướng dẫn prose tại thời điểm viết vẫn có ví dụ `BasicAWSCredentials` và `InstanceProfileCredentialsProvider` của **SDK v1**, cùng lời nhắc `com.amazonaws:aws-java-sdk-core`. **Không sao chép nguyên các kiểu v1 ấy vào ví dụ 4.1**: chúng không khớp chữ ký Javadoc 4.1.
- Khi duy trì nhánh Spring Vault cũ, phải đối chiếu **Javadoc của đúng nhánh**: nếu kiểu API thực sự là `com.amazonaws.auth.*` thì sử dụng SDK v1 tương ứng; nếu là `software.amazon.awssdk.*` thì dùng v2. Không đưa cả hai thế hệ vào classpath chỉ để “phòng thiếu”.

**Dependency AWS SDK v2**, khi dự án đã import AWS SDK BOM tương thích:

```xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>auth</artifactId>
</dependency>
```

`auth` chứa `DefaultCredentialsProvider`; `AwsIamAuthenticationOptions` còn dùng kiểu `software.amazon.awssdk.regions.Region`, do đó phải bảo đảm các module AWS SDK phụ thuộc liên quan được resolve đồng bộ. **Nếu không có AWS SDK BOM/dependency management, Maven cần phiên bản cụ thể cho dependency này**.

Ví dụ Spring Vault 4.1, dùng provider chain thay vì khóa tĩnh:

```java
import org.springframework.vault.authentication.AwsIamAuthentication;
import org.springframework.vault.authentication.AwsIamAuthenticationOptions;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultClient;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;

class AwsVaultAuth {
    static ClientAuthentication create(VaultClient vaultClient) {
        var options = AwsIamAuthenticationOptions.builder()
                .role("orders-aws-role")
                .serverId("vault.internal.example")
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();

        return new AwsIamAuthentication(options, vaultClient);
    }
}
```

`vaultClient` ở đây là client Vault đã cấu hình HTTPS/TLS và endpoint đúng, được tạo ở tầng hạ tầng. `orders-aws-role`, `vault.internal.example` chỉ là giá trị minh họa; `serverId` phải nhất quán với `iam_server_id_header_value` của Vault auth mount nếu được bật, nhằm giảm replay. AWS credentials provider phải nhận đúng role của workload khi chạy thực tế.

**Không gọi `DefaultCredentialsProvider` như một đảm bảo bảo mật mặc định.** Nó tìm credentials theo chuỗi nguồn có thứ tự; trong CI/local có thể lấy môi trường/profile của nhà phát triển thay vì IAM role dự kiến của production. Cần xác minh principal thực tế và giới hạn quyền của IAM role.

Nguồn API: [AwsIamAuthenticationOptions.Builder Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AwsIamAuthenticationOptions.AwsIamAuthenticationOptionsBuilder.html), [AwsIamAuthentication Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AwsIamAuthentication.html).

### 3.2. AWS EC2: instance identity không đồng nghĩa AWS IAM

`AwsEc2Authentication` dùng **PKCS#7 instance identity document**, truy xuất qua EC2 metadata, không cần tạo AWS SigV4 STS request. Từ Spring Vault 3.2, đường lấy metadata có hỗ trợ IMDSv1 và IMDSv2. **Ưu tiên IMDSv2** tại hạ tầng AWS; không mở IMDSv1 chỉ để hợp thức hóa cấu hình cũ.

Vault áp dụng **nonce** mặc định để bảo vệ kiểu Trust On First Use. Nonce lưu trong bộ nhớ và mất khi JVM restart, vì vậy cần hiểu tác động của restart/redeployment đối với cơ chế phát hiện bản sao. Không dùng AWS EC2 auth cho container ngoài EC2 có metadata giả lập rồi coi đó là xác thực production.

Ví dụ hướng cấu hình mức cao:

```java
// aws-ec2: không cần com.amazonaws / software.amazon.awssdk
// chỉ để tải instance identity document qua metadata.
ClientAuthentication auth = new AwsEc2Authentication(vaultClient);
```

Đoạn code giả định đã import các lớp Spring Vault và truyền client Vault hợp lệ; thêm `AwsEc2AuthenticationOptions` khi cần role, mount path hoặc chế độ metadata cụ thể.

## 4. GCP: phân biệt `GcpComputeAuthentication` và `GcpIamCredentialsAuthentication`

### 4.1. GCP GCE nhận JWT từ metadata

`GcpComputeAuthentication` lấy **JWT chứng minh danh tính instance** từ metadata service GCE. Ứng dụng không trực tiếp gọi `projects.serviceAccounts.signJwt` để ký JWT; vì vậy **không cần thêm Google IAM Credentials SDK** cho chính phương thức này.

Điều kiện triển khai: workload chạy trong môi trường có metadata service hợp lệ, instance/service account gắn đúng role và Vault đã bật/cấu hình auth mount GCP với role tương ứng. Test local hoặc Docker thông thường không tự có GCE metadata, nên lỗi metadata `404`/timeout là khác với lỗi thiếu thư viện.

```java
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.GcpComputeAuthentication;
import org.springframework.vault.authentication.GcpComputeAuthenticationOptions;
import org.springframework.vault.client.VaultClient;

class GceVaultAuth {
    static ClientAuthentication create(VaultClient vaultClient) {
        var options = GcpComputeAuthenticationOptions.builder()
                .role("orders-gce-role")
                .build();
        return new GcpComputeAuthentication(options, vaultClient);
    }
}
```

### 4.2. GCP IAM gọi `signJwt`: cần SDK riêng

`GcpIamCredentialsAuthentication` sử dụng Google IAM Credentials API **`projects.serviceAccounts.signJwt`**. Google credentials có thể đến từ Application Default Credentials (ADC), service account đã được ủy quyền hoặc môi trường cloud; principal gọi API phải có quyền `iam.serviceAccounts.signJwt` trên service account mục tiêu.

**Dependency chính** cho đường Spring Vault Core 4.1:

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-iamcredentials</artifactId>
    <!-- Phiên bản lấy từ Google Cloud libraries BOM / dependency management -->
</dependency>
```

SDK có các thư viện bắc cầu như Google Auth/gRPC/GAX; giữ chúng cùng bộ phiên bản, tránh ép `google-auth-library-oauth2-http` hoặc gRPC xuống bản quá cũ.

Ví dụ API 4.1:

```java
import java.io.IOException;
import com.google.auth.oauth2.GoogleCredentials;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.GcpIamCredentialsAuthentication;
import org.springframework.vault.authentication.GcpIamCredentialsAuthenticationOptions;
import org.springframework.vault.client.VaultClient;

class GcpIamVaultAuth {
    static ClientAuthentication create(VaultClient vaultClient) throws IOException {
        var options = GcpIamCredentialsAuthenticationOptions.builder()
                .role("orders-gcp-role")
                .credentials(GoogleCredentials.getApplicationDefault())
                .build();
        return new GcpIamCredentialsAuthentication(options, vaultClient);
    }
}
```

**Chú ý chữ ký phương thức:** Javadoc 4.1 khai báo **`credentials(GoogleCredentials)`** và `credentialsSupplier(...)`. Một số ví dụ prose cũ dùng `credential(...)` số ít; hãy chọn theo **Javadoc của bản đang build**. Không đẩy JSON key chứa private key vào source code hoặc artifact; ưu tiên ADC/workload identity và quyền hạn hẹp.

**Giới hạn reactive:** tài liệu Spring Vault xác nhận `GcpIamCredentialsAuthentication` dùng Google API **đồng bộ** và **không hỗ trợ `AuthenticationSteps`** cho đường xác thực reactive thông thường. Ứng dụng dùng `ReactiveVaultTemplate` không nên mặc định nó có thể tự chuyển cơ chế này thành non-blocking. Cần chọn cơ chế xác thực được hỗ trợ cho reactive hoặc thiết kế rõ bước lấy credential bên ngoài, caching và cách ly blocking I/O nếu có.

Nguồn: [GcpIamCredentialsAuthenticationOptions.Builder Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/GcpIamCredentialsAuthenticationOptions.GcpIamCredentialsAuthenticationOptionsBuilder.html), [GcpIamCredentialsAuthentication Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/GcpIamCredentialsAuthentication.html), [Spring Vault – GCP IAM](https://docs.spring.io/spring-vault/reference/vault/authentication.html).

## 5. Azure MSI: dùng metadata, chưa cần Azure Java SDK

`AzureMsiAuthentication` sử dụng **Managed Service Identity token** và thông tin Azure VM từ Instance Metadata Service (IMDS) để đăng nhập Vault. Chương trình phải chạy trong môi trường được cấp managed identity và Vault auth role đã cấu hình đúng subscription, resource group, VM name hoặc ràng buộc cần thiết.

```java
import org.springframework.vault.authentication.AzureMsiAuthentication;
import org.springframework.vault.authentication.AzureMsiAuthenticationOptions;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultClient;

class AzureVaultAuth {
    static ClientAuthentication create(VaultClient vaultClient) {
        var options = AzureMsiAuthenticationOptions.builder()
                .role("orders-azure-role")
                .build();
        return new AzureMsiAuthentication(options, vaultClient);
    }
}
```

Với `AzureMsiAuthentication`, SDK `com.azure:azure-identity` **không phải dependency bắt buộc** chỉ để gọi Azure IMDS theo cách Spring Vault mô tả. Chỉ thêm Azure SDK khi ứng dụng còn sử dụng **Azure API khác**, hoặc khi một giải pháp lấy identity riêng có API yêu cầu SDK đó.

Nếu chạy ngoài Azure VM/host có managed identity, không nên giả lập metadata endpoint công khai như một phương thức production. Với địa chỉ link-local `169.254.169.254`, phải giới hạn đường truy cập và bảo đảm chỉ workload tin cậy có quyền lấy token.

Nguồn: [Azure MSI – Spring Vault](https://docs.spring.io/spring-vault/reference/vault/authentication.html), [AzureMsiAuthentication Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AzureMsiAuthentication.html).

## 6. Kubernetes, JWT và AppRole: lựa chọn giảm phụ thuộc SDK cloud

Trong nhiều hệ thống, Spring Vault có thể đăng nhập Vault mà **không cài SDK AWS/GCP/Azure**:

### Kubernetes auth

Pod có **ServiceAccount JWT**, thường tại `/var/run/secrets/kubernetes.io/serviceaccount/token`. `KubernetesAuthentication` gửi JWT cùng Vault role đến auth mount Kubernetes. Vault kiểm tra ràng buộc service account/namespace và TokenReview hoặc cấu hình xác minh tương ứng.

Với Spring Cloud Vault starter, ví dụ cấu hình:

```yaml
spring:
  application:
    name: orders-api
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.internal.example:8200"
      authentication: KUBERNETES
      kubernetes:
        role: orders-k8s-role
        service-account-token-file: /var/run/secrets/kubernetes.io/serviceaccount/token
```

Đây là cấu hình minh họa: cần CA/TLS, Vault auth mount, policy và JWT thực. **Không cần Kubernetes Java client** chỉ để đọc token từ file và đăng nhập. Nếu ứng dụng còn gọi Kubernetes API để quản lý pod/Secret, đó là nhu cầu khác và có thể cần Kubernetes SDK.

### JWT auth

`JwtAuthentication` dùng JWT từ issuer/JWKS hoặc hệ thống identity được Vault tin cậy. Không nhất thiết dùng cloud SDK nếu JWT đã được cung cấp qua môi trường an toàn. Cần xác minh `aud`, `iss`, thời gian hết hạn, role và claims. Dùng JWT của một hệ thống khác không tự trở thành JWT hợp lệ cho Vault auth mount.

### AppRole auth

`AppRoleAuthentication` nhận role ID và secret ID/response wrapping. SDK cloud không bắt buộc, nhưng **vấn đề bootstrap secret** chuyển sang cách phân phối và làm mới Secret ID an toàn. Không hard-code `secret_id` trong Git hay log. Nếu đang chạy trên Kubernetes hoặc cloud identity đáng tin cậy, cân nhắc dùng danh tính workload để giảm gánh nặng phân phối bí mật ban đầu.

**Không có phương thức nào tự tạo Vault policy.** KV v1/v2, Transit encryption, PKI và lease hoạt động theo policy của Vault token sau khi login, không theo việc đã có AWS/GCP/Azure SDK hay chưa.

## 7. Spring Vault Core và Spring Cloud Vault starter: không trộn phụ thuộc tùy tiện

**Spring Vault Core** (`org.springframework.vault:spring-vault-core`) cung cấp các lớp `ClientAuthentication` và `VaultTemplate`, còn **Spring Cloud Vault** (`org.springframework.cloud:spring-cloud-starter-vault-config`) hỗ trợ **Config Data** (`spring.config.import: vault://`), property binding và auto-configuration trong Spring Boot.

Ở thời điểm viết, tài liệu **Spring Cloud Vault 5.1.0** ghi AWS IAM dùng **AWS SDK v2 `software.amazon.awssdk:auth`**. Javadoc Spring Vault Core 4.1 cũng dùng kiểu AWS SDK v2. Tuy nhiên trang prose Spring Vault Core còn chứa ví dụ SDK v1, và trang Spring Cloud Vault có một số mô tả GCP IAM theo API Google cũ. Vì thế:

1. Chọn **Spring Boot BOM + Spring Cloud release train tương thích** nếu dùng starter. Không ép ngẫu nhiên phiên bản Core khác thế hệ với Cloud Vault.
2. Đọc **Javadoc chữ ký chính xác** của API đang gọi, ví dụ `AwsIamAuthenticationOptions` hay `GcpIamCredentialsAuthenticationOptions`.
3. Xem `mvn dependency:tree` / Gradle `dependencyInsight` để biết **artifact SDK/phiên bản cuối cùng** sau BOM và override.
4. Chỉ khai báo trực tiếp SDK tùy chọn khi **phương thức xác thực đã chọn thực sự cần**, không ép mọi SDK cloud vào production image.
5. Khi cập nhật Spring Vault, chạy lại test xác thực, cấp Vault token và truy cập KV/Transit/PKI; build thành công chưa chứng minh đường IAM/metadata hoạt động.

Mẫu Maven tối thiểu dùng Core 4.1.2 và JSON mapper, giả định dự án đã dùng **Spring Boot 4.x BOM**:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.vault</groupId>
        <artifactId>spring-vault-core</artifactId>
        <version>4.1.2</version>
    </dependency>
    <dependency>
        <groupId>tools.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
    </dependency>
</dependencies>
```

Nếu lựa chọn **AWS IAM**, thêm `software.amazon.awssdk:auth` và import **AWS SDK BOM** phù hợp; nếu lựa chọn **GCP IAM**, thêm `com.google.cloud:google-cloud-iamcredentials` và quản lý phiên bản qua Google Cloud libraries BOM. Không thêm cả hai khi chỉ triển khai một phương thức.

Mẫu Gradle Kotlin DSL cho dự án **đã nhập các BOM cần thiết**:

```kotlin
dependencies {
    implementation("org.springframework.vault:spring-vault-core:4.1.2")
    implementation("tools.jackson.core:jackson-databind")

    // Chỉ chọn một dòng theo cơ chế đăng nhập thực tế:
    // implementation("software.amazon.awssdk:auth")              // AWS IAM
    // implementation("com.google.cloud:google-cloud-iamcredentials") // GCP IAM
}
```

Để sử dụng trực tiếp các đoạn trên, cần cấu hình **đúng BOM hoặc phiên bản** cho Jackson/AWS/GCP; Spring Boot BOM **không được giả định** luôn quản lý mọi SDK cloud. Các ví dụ về Cloud Vault starter dùng dependency management của Spring Cloud release train, khác với việc chỉ thêm Core vào một ứng dụng Spring Framework thuần.

Nguồn: [Spring Vault – Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html), [Spring Cloud Vault – Authentication](https://docs.spring.io/spring-cloud-vault/reference/authentication.html), [Spring Cloud Vault – Quick Start](https://docs.spring.io/spring-cloud-vault/reference/quickstart.html).

## 8. Xác thực reactive, vòng đời token và SDK đồng bộ

`AuthenticationStepsFactory` là hợp đồng cho các bước đăng nhập có thể tổ hợp trong reactive flow. Đa số cơ chế đăng nhập Spring Vault hỗ trợ kiểu này, nhưng **không phải tất cả**:

| Cơ chế | Reactive consideration |
| --- | --- |
| AWS IAM | `AwsIamAuthentication` có `AuthenticationStepsFactory`. Javadoc lưu ý credential được lấy sớm khi tạo steps, vì AWS credentials provider có thể thực hiện I/O/blocking |
| AWS EC2, Azure MSI, GCP GCE | Xác thực dựa metadata có thể biểu diễn thành steps; HTTP metadata vẫn cần timeout và xử lý lỗi |
| GCP IAM Credentials | **Không có `AuthenticationStepsFactory`** do Google IAM Credentials SDK sử dụng API đồng bộ; không mặc định nó hoạt động với reactive auth configuration |
| Kubernetes/JWT/AppRole | Thường là lựa chọn phù hợp với reactive, nhưng phải cấu hình supplier/token đúng và kiểm tra hỗ trợ của phiên bản cụ thể |

Ứng dụng dùng `ReactiveVaultTemplate`/`ReactiveVaultClient` vẫn cần `ReactiveSessionManager`/`VaultTokenSupplier` để lấy và lưu token. Việc tự đặt `Mono.just(blockingAuthentication.login())` **không biến thao tác login thành non-blocking**; lời gọi blocking đã chạy trước khi Publisher được subscribe.

Với runtime đồng bộ, `LifecycleAwareSessionManager` có thể theo dõi Vault token TTL và renewal/re-login. Đối với KV secrets và dynamic credentials có lease, việc cập nhật password/certificate cho ứng dụng là một chu trình riêng, không tự xảy ra chỉ vì token login đã được renew.

## 9. Phát hiện thiếu SDK và xung đột classpath

### Maven

```bash
mvn -version
mvn help:effective-pom
mvn dependency:tree
```

### Gradle

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-vault-core
./gradlew dependencyInsight --configuration runtimeClasspath --dependency auth
./gradlew dependencyInsight --configuration runtimeClasspath --dependency google-cloud-iamcredentials
./gradlew dependencyInsight --configuration runtimeClasspath --dependency google-auth-library
```

Trên Windows dùng `gradlew.bat` nếu cần. Tìm phiên bản **thực được resolve**, kể cả dependency bắc cầu hoặc SDK bị exclude. Kiểm tra cả JDK và các dependency Spring Framework trong packaged image.

| Dấu hiệu | Cần kiểm tra trước |
| --- | --- |
| `NoClassDefFoundError` với `software.amazon.awssdk.*` | AWS SDK v2 thiếu trên runtime classpath; có đang dùng snippet SDK v1 với Spring Vault 4.1 không? |
| Lỗi compile `AwsCredentialsProvider` không khớp | Chữ ký builder giữa các thế hệ AWS SDK, Spring Vault Javadoc đúng version |
| `NoClassDefFoundError` cho Google IAM Credentials/GAX/gRPC | SDK IAM Credentials thiếu hoặc module bắc cầu bị exclude; BOM Google Cloud bị trộn |
| Compile không tìm thấy `credential(...)` | Với Javadoc 4.1, builder sử dụng `credentials(...)` số nhiều |
| Metadata endpoint timeout/`404` | Workload không ở môi trường cloud hỗ trợ; IMDS bị chặn, sai metadata version/route |
| AWS IAM login `400/403` | IAM principal, STS signature/region, role Vault, STS endpoint hoặc server ID header không phù hợp |
| GCP IAM login lỗi `signJwt` | IAM Credentials API chưa bật, service account/`iam.serviceAccounts.signJwt`, ADC hoặc project sai |
| Azure MSI login không nhận token | Managed identity chưa gán, sai subscription/resource group/VM/Vault role hoặc Azure IMDS lỗi |
| Vault login thành công nhưng đọc KV `403` | Vault policy thiếu capability/path; kiểm tra mount KV v1/v2 và token nhận được |
| Secret đọc được nhưng Transit/PKI bị từ chối | Policy cần quyền riêng theo engine và role; không liên quan SDK xác thực cloud |
| Token sau một thời gian hết hạn | Session manager không renew/re-login đúng, hoặc Vault role/TTL/policy có thay đổi |

**Không log** AWS credentials, Google JWT, Azure identity token, Kubernetes ServiceAccount JWT hay Vault token để chẩn đoán. Với lỗi cần ghi nhận method, loại endpoint (đã lược thông tin nhạy cảm), thời gian, HTTP status, request correlation và nguyên nhân được phân loại.

## 10. Kiểm thử tích hợp theo phương thức đã chọn

Một bài kiểm thử auth hoàn chỉnh nên xác minh **hai lần cấp quyền tách biệt**:

1. **Cloud identity → Vault token**: workload login bằng đúng role/mount; token Vault có TTL và policies kỳ vọng.
2. **Vault token → secrets engines**: chỉ đọc được KV path đã cấp, gọi Transit/PKI theo policy và bị từ chối trên path không thuộc phạm vi.

Đề xuất ma trận test:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| AWS IAM với workload role đúng | Đăng nhập thành công; không có access key hard-code |
| AWS IAM đổi sang role không được bind | Vault từ chối; không thử fallback sang root token |
| AWS EC2 sau restart | Kiểm tra hành vi nonce và xác minh EC2 identity |
| GCP IAM thiếu `signJwt` | Login thất bại có thể chẩn đoán; không gán nhầm là thiếu quyền KV |
| GCP GCE/Azure MSI ngoài môi trường metadata | Lỗi định danh/metadata được báo rõ, không giả lập thành login hợp lệ |
| Kubernetes JWT đổi namespace/ServiceAccount | Vault role từ chối khi không khớp ràng buộc |
| Token còn hợp lệ nhưng KV path bị cấm | Nhận `403` tại engine; chứng minh least privilege |
| Vault token hết hạn và được gia hạn/lấy mới | Ứng dụng tiếp tục hoạt động theo session policy đã chọn |
| Vault không sẵn sàng/TLS sai | Timeout hoặc TLS error đúng tầng, có metric và không lộ credential |

Có thể dùng **Testcontainers Vault** để kiểm thử Vault auth role/policy, KV v2/Transit/PKI và response lỗi. Tuy nhiên container Vault **không tự tạo danh tính AWS/Azure/GCP thật**. Để xác minh metadata/IAM provider, dùng môi trường cloud test có giới hạn quyền hoặc test riêng bước ký JWT/metadata qua client giả lập có kiểm soát; không công bố rằng mock đã chứng minh trust chain với cloud provider.

**Ví dụ tình huống:** dịch vụ Java `orders-api` chạy trên EKS và chỉ cần đọc `secret/data/orders/config` cùng `transit/encrypt/orders-key`. Nhóm có thể chọn Vault Kubernetes auth hoặc AWS IAM (IRSA) theo chính sách tổ chức. Nếu dùng Kubernetes auth, không cần thêm AWS SDK chỉ vì EKS vận hành trên AWS. Nếu dùng AWS IAM, dùng provider chain SDK v2, kiểm tra Vault role bind đúng IAM principal; cả hai trường hợp vẫn cần Vault ACL cho KV/Transit.

## 11. Checklist trước khi phát hành

- [ ] Đã xác định **phương thức auth** cụ thể theo workload, không chỉ xác định cloud provider.
- [ ] SDK tùy chọn chỉ được thêm nếu API Spring Vault tương ứng thực sự cần; Javadoc khớp với thế hệ SDK.
- [ ] Không lẫn AWS SDK v1/v2 hay Google IAM API cũ/mới trong code vì sao chép snippet từ nhánh khác.
- [ ] BOM Spring Boot/Spring Cloud và BOM cloud SDK tương thích; dependency tree xác nhận runtime classpath.
- [ ] Vault auth mount, role, identity binding, region/project/namespace và `serverId` được cấu hình đúng.
- [ ] Credential lấy từ workload identity/metadata/ADC, không đưa access key, service account private key hoặc root token vào Git.
- [ ] TLS và CA trust được thiết lập; HTTP timeout, retry có giới hạn, Vault HA và metadata endpoint được kiểm thử.
- [ ] Reactive auth không gọi nhầm SDK đồng bộ trên event loop; session/token renewal hoặc re-login có test.
- [ ] Vault policy quyền tối thiểu cho KV/Transit/PKI và vòng đời lease được kiểm thử độc lập.
- [ ] Nhật ký, metric và trace không ghi token, JWT, secret hoặc key.

**Ghi nhớ:** **AWS IAM cần SDK ký SigV4; AWS EC2/GCP GCE/Azure MSI thường dùng metadata; GCP IAM cần IAM Credentials SDK; Kubernetes/JWT/AppRole thường không cần cloud SDK.** Khi code Spring Vault 4.1, **ưu tiên chữ ký Javadoc của phiên bản đang build**, rồi chọn artifact phù hợp. Có SDK đúng chỉ giải quyết phần lấy bằng chứng danh tính; Vault role, session và policy mới quyết định ứng dụng có thể truy cập secret an toàn hay không.

### Tài liệu chính thức

1. [Spring Vault 4.1.2 – Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
2. [Spring Vault 4.1.2 – Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html)
3. [Spring Vault 4.1 – AWS IAM options builder Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AwsIamAuthenticationOptions.AwsIamAuthenticationOptionsBuilder.html)
4. [Spring Vault 4.1 – AwsIamAuthentication Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AwsIamAuthentication.html)
5. [Spring Vault 4.1 – GCP IAM options builder Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/GcpIamCredentialsAuthenticationOptions.GcpIamCredentialsAuthenticationOptionsBuilder.html)
6. [Spring Vault 4.1 – GcpIamCredentialsAuthentication Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/GcpIamCredentialsAuthentication.html)
7. [Spring Vault 4.1 – AzureMsiAuthentication Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AzureMsiAuthentication.html)
8. [Spring Vault – Authentication package reference](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/package-summary.html)
9. [Spring Cloud Vault 5.1 – Authentication Methods](https://docs.spring.io/spring-cloud-vault/reference/authentication.html)
10. [Spring Cloud Vault – Quick Start](https://docs.spring.io/spring-cloud-vault/reference/quickstart.html)
11. [HashiCorp Vault – Authentication methods](https://developer.hashicorp.com/vault/docs/auth)
12. [AWS – IAM auth with Vault](https://developer.hashicorp.com/vault/docs/auth/aws)
13. [Google Cloud – IAM Credentials signJwt](https://cloud.google.com/iam/docs/reference/credentials/rest/v1/projects.serviceAccounts/signJwt)
14. [Kubernetes – ServiceAccount tokens](https://kubernetes.io/docs/concepts/configuration/secret/#serviceaccount-token-secrets)
