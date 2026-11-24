# Phân biệt tham số cấu hình, bí mật và định danh tài nguyên

Khi tích hợp Spring Boot với dịch vụ managed của **AWS, Azure và Google Cloud**, một ứng dụng thường cần ít nhất ba loại thông tin: cách ứng dụng vận hành, địa chỉ hoặc tên của tài nguyên cloud, và dữ liệu cho phép xác thực. Các loại thông tin này đều có thể xuất hiện dưới dạng chuỗi trong YAML hoặc biến môi trường, nhưng **ý nghĩa, cách lưu trữ, quyền truy cập và vòng đời của chúng khác nhau**.

Ví dụ, tính năng tải tài liệu lên cloud có thể dùng `operation-timeout: 8s`, tên bucket `documents-prod` và một credential để ghi file. Timeout là **tham số cấu hình**; tên bucket là **định danh tài nguyên**; credential là **bí mật xác thực** nếu credential chứa token, mật khẩu hoặc khóa riêng. Việc đưa cả ba vào cùng một tệp Git, hoặc coi tên bucket là một dạng mật khẩu, đều khiến thiết kế khó quản lý và bảo vệ.

Bài học thuộc phần **Cấu hình ứng dụng** của mô-đun `SPRING_CLOUD_PROVIDER_INTEGRATION`, tập trung vào cách phân loại thông tin trước khi kết nối storage, messaging và dữ liệu trên nhiều cloud provider.

## 1. Ba nhóm thông tin và chức năng của từng nhóm

| Nhóm | Trả lời câu hỏi | Ví dụ | Cách quản lý thông thường |
| --- | --- | --- | --- |
| **Tham số cấu hình** (*configuration parameter*) | Ứng dụng **nên vận hành như thế nào**? | Timeout, số lần retry, batch size, tên profile, chế độ bật/tắt tính năng | Tệp cấu hình theo môi trường, biến môi trường, dịch vụ quản lý cấu hình |
| **Định danh tài nguyên** (*resource identifier*) | Ứng dụng **phải thao tác với tài nguyên nào**? | S3 bucket, Azure Blob container, GCS bucket, SQS queue URL, Pub/Sub topic name, database host | Configuration theo deployment; kiểm soát quyền xem khi chứa thông tin hạ tầng |
| **Bí mật** (*secret*) | Thông tin nào **chứng minh quyền truy cập hoặc cần giữ kín để tránh bị lạm dụng**? | Password, API token, client secret, private key, SAS token, signed URL mang quyền | Secret manager, workload identity, vùng lưu trữ bảo mật; hạn chế ghi log và phân phối |

Định danh tài nguyên **không tự cấp quyền**. Người biết tên bucket S3 không mặc nhiên có quyền ghi bucket đó. Tương tự, người biết endpoint Azure Blob vẫn cần được cấp quyền bằng Microsoft Entra ID, SAS hoặc một cơ chế xác thực khác.

Ngược lại, một bí mật có thể trông giống địa chỉ tài nguyên: URL kèm token truy cập, chuỗi kết nối có shared key hoặc URL ký sẵn có khả năng cấp quyền theo thời hạn. Cần xem xét **nội dung và khả năng sử dụng** thay vì chỉ dựa vào tên field.

### Quy tắc phân loại nhanh

```mermaid
flowchart TD
    A["Đang xem xét một giá trị cấu hình"] --> B{"Giá trị có thể dùng để xác thực, ký yêu cầu hoặc truy cập như bearer token?"}
    B -->|Có| S["BÍ MẬT: bảo vệ như credential"]
    B -->|Không| C{"Giá trị chọn hoặc chỉ tới một tài nguyên cloud cụ thể?"}
    C -->|Có| R["ĐỊNH DANH TÀI NGUYÊN"]
    C -->|Không| P["THAM SỐ CẤU HÌNH hoặc metadata"]
    R --> D["Kiểm soát việc tiết lộ topology nếu cần"]
    P --> V["Kiểm tra kiểu và ràng buộc nghiệp vụ"]
    S --> K["Secret manager / workload identity / chính sách xoay vòng"]
```

Sơ đồ trên là quy tắc thực hành, không phải bảng phân loại pháp lý. Có những giá trị **không phải secret nhưng vẫn nhạy cảm**: ID tài khoản cloud, hostname nội bộ, tên dự án, địa chỉ môi trường production hoặc thông tin mô tả kiến trúc. Chúng không cần xử lý như mật khẩu, song vẫn nên giới hạn người xem theo chính sách tổ chức.

## 2. Ví dụ phân loại trên AWS, Azure và Google Cloud

Các provider dùng tên tài nguyên và mô hình danh tính khác nhau. Bảng sau giúp tách rõ các nhóm ngay khi thiết kế file cấu hình Spring Boot.

| Dịch vụ | Tham số cấu hình | Định danh tài nguyên | Bí mật hoặc credential cần bảo vệ |
| --- | --- | --- | --- |
| **AWS S3** | Timeout upload, số lần retry, chiến lược mã hóa | Tên bucket, object key, bucket ARN, AWS region | AWS secret access key, session token, presigned URL chưa hết hạn |
| **AWS SQS/SNS** | Batch size, visibility timeout, retry | Queue URL, queue ARN, topic ARN | Token/khóa dùng để xác thực nếu ứng dụng đang dùng credential tĩnh |
| **Azure Blob Storage** | Kích thước block, timeout, retry | Storage account name, tên container, blob name, endpoint | Account key, SAS token, connection string chứa shared key |
| **Azure Service Bus** | Prefetch count, mức concurrency | Namespace, queue, topic, subscription name | Shared access key, connection string chứa SAS key |
| **Google Cloud Storage** | Timeout và cấu hình retry của client | Project ID, bucket name, object name | Private key trong service account JSON, access token |
| **Google Cloud Pub/Sub** | Flow control, ack deadline, batch settings | Resource name `projects/{project}/topics/{topic}`, subscription ID | Private key của service account hoặc token truy cập |
| **Managed database** | Pool size, timeout, migration mode | Host, port, database name, instance/cluster ID | Password, client certificate private key, DSN chứa password |

Một số trường hợp cần xét kỹ:

- **AWS access key ID** là một *định danh của access key*, khác với **secret access key**. Tuy nhiên, cặp thông tin cùng session token (nếu có) tạo thành credential; trong luồng vận hành, nên xử lý cả bộ như dữ liệu xác thực nhạy cảm và không log bừa bãi.
- **Azure tenant ID** và **client ID** thường là định danh; **client secret** mới là bí mật. `subscriptionId` và resource group là định danh phạm vi tài nguyên, không phải mật khẩu.
- **Google Cloud service account email** là định danh của principal; nội dung trường `private_key` trong JSON key là bí mật. `GOOGLE_CLOUD_PROJECT` là project ID, không phải credential.
- **Secret ARN, Key Vault secret URI, Secret Manager resource name** thường là *tham chiếu tới secret*, không phải **giá trị secret**. Dù vậy, tham chiếu có thể tiết lộ môi trường hoặc tài nguyên nội bộ nên vẫn cần quản lý truy cập thích hợp.
- **URL ký sẵn/SAS URL** có thể cho phép người sở hữu URL truy cập tài nguyên trong thời hạn hiệu lực. Hãy phân loại **toàn bộ URL là bí mật**, kể cả phần đầu chỉ trông như một URL bình thường.

### Ví dụ một giao dịch upload tài liệu

```mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Config as App config
    participant Identity as Workload identity / credential provider
    participant Storage as Cloud Storage
    App->>Config: Đọc timeout, provider, target
    Config-->>App: 8s, AWS, documents-prod
    App->>Identity: Yêu cầu credential được cấp phù hợp
    Identity-->>App: Credential xử lý an toàn
    App->>Storage: Upload object vào documents-prod
    Storage-->>App: Kết quả hoặc lỗi IAM/network/resource
```

Ở đây, **tên bucket** được dùng để tạo request; **credential** được SDK dùng để ký hoặc xác thực request; **timeout** điều chỉnh cách client chờ. Ba giá trị có ba trách nhiệm khác nhau.

## 3. Định danh tài nguyên, danh tính workload và credential không giống nhau

Từ *identity* xuất hiện nhiều khi làm việc với cloud. Cần phân biệt ba khái niệm:

1. **Resource identifier:** tên, đường dẫn, URI hoặc ID của đối tượng cần thao tác. Ví dụ `documents-prod` là tên bucket; `projects/example-prod/topics/events` là tên tài nguyên Pub/Sub.
2. **Workload identity / principal:** danh tính được gán cho ứng dụng đang chạy. Ví dụ AWS IAM Role, Azure Managed Identity, GCP service account thông qua Workload Identity.
3. **Credential:** bằng chứng xác thực được hệ thống chấp nhận, chẳng hạn token có hạn, khóa bí mật, client certificate private key hoặc access key.

Bản thân **IAM Role ARN**, **Managed Identity client ID** hay **service account email** có thể là định danh của một principal, nhưng **biết định danh không tương đương sở hữu credential**. Việc xác thực phụ thuộc cơ chế runtime (AWS credential provider chain, Azure Identity, Google Application Default Credentials, v.v.).

Thực tế triển khai cloud thường ưu tiên:

| Cloud | Danh tính khuyến nghị cho ứng dụng | Ví dụ quyền cần cấp khi ghi storage |
| --- | --- | --- |
| AWS | IAM Role gắn với môi trường chạy (EC2/ECS/EKS hoặc workload federation) | `s3:PutObject` cho đúng bucket/prefix |
| Azure | Managed Identity hoặc workload identity qua Microsoft Entra ID | Data role phù hợp, ví dụ **Storage Blob Data Contributor** khi yêu cầu ghi |
| Google Cloud | Service account qua Workload Identity hoặc Application Default Credentials | Quyền `storage.objects.create` trên bucket đích, thông qua role phù hợp |

Ứng dụng có thể dùng credential ngắn hạn do SDK lấy tự động mà **không cần khai báo access key, mật khẩu hay private key trong `application.yml`**. Quyền cần được cấp cho principal ở phía IAM/RBAC; việc đổi `app.storage.target` sang tên bucket khác không tự cấp quyền trên bucket mới.

## 4. Thiết kế namespace cấu hình riêng của ứng dụng

Một ứng dụng tích hợp storage và messaging có thể sử dụng namespace **do chính ứng dụng định nghĩa** như sau:

```yaml
# src/main/resources/application.yml
app:
  integration:
    storage:
      target: ${STORAGE_TARGET}
    messaging:
      destination: ${MESSAGING_DESTINATION}
    operation-timeout: 8s
    retry:
      max-attempts: 3
```

Ở đây:

- `operation-timeout` và `retry.max-attempts` là **tham số cấu hình**.
- `storage.target` và `messaging.destination` là **định danh tài nguyên**.
- Không có field chứa **access key, token hoặc private key**; SDK dự kiến sử dụng cơ chế danh tính được cấu hình cho môi trường chạy.
- `${STORAGE_TARGET}` là **placeholder tham chiếu tới biến môi trường**. Bản thân placeholder trong file Git không chứa secret; giá trị runtime của biến phải được phân loại riêng theo nội dung.

Có thể chọn provider bằng file profile:

**`application-aws.yml`**

```yaml
app:
  integration:
    provider: aws
```

**`application-azure.yml`**

```yaml
app:
  integration:
    provider: azure
```

**`application-gcp.yml`**

```yaml
app:
  integration:
    provider: gcp
```

Khi triển khai, đặt `SPRING_PROFILES_ACTIVE` tương ứng và cung cấp tên tài nguyên thích hợp. Ví dụ:

| Profile | `STORAGE_TARGET` | `MESSAGING_DESTINATION` | Adapter diễn giải |
| --- | --- | --- | --- |
| `aws` | `documents-prod-asia` | URL queue SQS của môi trường production | S3 bucket và SQS queue URL |
| `azure` | `uploads` | `documents-created` | Blob container và Service Bus queue/topic trong namespace được cấu hình riêng |
| `gcp` | `documents-prod-asia` | `projects/example-prod/topics/documents-created` | GCS bucket và Pub/Sub topic resource name |

Các giá trị là **ví dụ minh họa**, không phải tên tài nguyên được tạo sẵn. Không gán cùng một ý nghĩa kỹ thuật cho mọi field: SQS queue URL khác với Service Bus entity name; adapter của từng provider phải chuyển đổi/kiểm tra định danh theo SDK tương ứng.

Cần lưu ý rằng `app.integration.*` **không phải** namespace tự cấu hình chính thức của Spring Cloud AWS, Azure hoặc GCP. Khi khởi tạo client, vẫn phải cung cấp những property mà từng starter yêu cầu, hoặc dùng API cấu hình client của SDK thích hợp. Các namespace thực tế thay đổi theo thế hệ thư viện, nên kiểm tra tài liệu của BOM/phiên bản đang dùng.

## 5. Binding và validation bằng `@ConfigurationProperties`

Trong Spring Boot 3.x và Java 17+, có thể định nghĩa một hợp đồng có kiểu thay vì để các adapter tự đọc chuỗi từ `Environment`:

```java
package example.cloud.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

import java.time.Duration;

@Validated
@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        @NotNull Provider provider,
        @Valid @NotNull Storage storage,
        @Valid @NotNull Messaging messaging,
        @DefaultValue("8s") Duration operationTimeout,
        @Valid @DefaultValue Retry retry
) {
    public enum Provider { AWS, AZURE, GCP }

    public record Storage(@NotBlank String target) {}

    public record Messaging(@NotBlank String destination) {}

    public record Retry(
            @Min(1) @Max(10) @DefaultValue("3") int maxAttempts
    ) {}
}
```

Đăng ký cấu hình bằng `@ConfigurationPropertiesScan` trên lớp khởi động hoặc `@EnableConfigurationProperties(IntegrationProperties.class)`. Nếu dùng `jakarta.validation.*`, cần dependency `spring-boot-starter-validation`. Với Java record, Spring Boot 3 hỗ trợ constructor binding cho record một constructor.

Bốn điểm quan trọng:

1. **Phân loại thể hiện trong tên và kiểu dữ liệu:** `operationTimeout` là `Duration`, `maxAttempts` là số, `storage.target` và `messaging.destination` là các định danh có nghĩa nghiệp vụ.
2. **Validation sớm:** `@NotBlank` chặn tên tài nguyên rỗng, `@Min`/`@Max` chặn retry bất thường. Các adapter có thể thêm validation theo quy tắc đặt tên của từng cloud.
3. **Không dùng chung một regex cho mọi provider:** bucket S3/GCS và Azure container có quy tắc tên khác nhau; Queue URL SQS lại có định dạng khác Pub/Sub topic. Validation ngữ nghĩa theo provider nên nằm ở tầng adapter hoặc validator có điều kiện.
4. **Không chứa secret trong record cấu hình dùng rộng rãi:** Java record tự sinh `toString()`. Nếu bỏ token, mật khẩu hoặc private key vào record rồi log `properties`, dữ liệu có thể rò rỉ. Nếu một tích hợp bắt buộc nhận secret qua binding, phải có mô hình bảo vệ và che log riêng.

Ví dụ tầng AWS nhận cấu hình ứng dụng và `S3Client` đã được cấu hình bằng cơ chế credential thích hợp:

```java
package example.cloud.storage;

import example.cloud.config.IntegrationProperties;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Component
@ConditionalOnProperty(
        prefix = "app.integration",
        name = "provider",
        havingValue = "aws"
)
public class AwsDocumentStorage {
    private final S3Client s3Client;
    private final IntegrationProperties properties;

    public AwsDocumentStorage(S3Client s3Client,
                              IntegrationProperties properties) {
        this.s3Client = s3Client;
        this.properties = properties;
    }

    public void upload(String objectKey, byte[] payload) {
        var request = PutObjectRequest.builder()
                .bucket(properties.storage().target()) // Định danh tài nguyên
                .key(objectKey)
                .build();
        s3Client.putObject(request, RequestBody.fromBytes(payload));
    }
}
```

Ví dụ trên giả định dependency tích hợp AWS S3 phù hợp đã cung cấp bean `S3Client`. Adapter **không đọc bí mật từ `IntegrationProperties`**: SDK/client chịu trách nhiệm tìm credentials qua cơ chế được cấu hình. `operationTimeout` và `retry.maxAttempts` cũng **chưa tự tác động tới AWS SDK**; nếu muốn áp dụng, cần cấu hình timeout/retry trong client hoặc tầng gọi API và tránh retry chồng lớp.

## 6. Đặt từng nhóm vào nguồn cấu hình phù hợp

| Loại dữ liệu | Nguồn phù hợp | Ví dụ | Điều cần tránh |
| --- | --- | --- | --- |
| Tham số chung, không nhạy cảm | `application.yml` trong repository | Timeout mặc định, feature flag phi nhạy cảm | Ghi cứng giá trị production vào mã Java |
| Tham số khác nhau giữa môi trường | Profile, external Config Data, Config Server/App Configuration | Retry theo môi trường, endpoint regional | Nhầm default dev thành cấu hình production |
| Định danh tài nguyên theo deployment | Environment, file ngoài JAR, config service | Tên S3 bucket, Azure Service Bus namespace, GCP project ID | Trộn resource của staging với production |
| Tham chiếu tới secret | Cấu hình runtime có giới hạn quyền xem | Secret ARN, Key Vault URI, Secret Manager resource name | Nhầm đường dẫn tham chiếu với nội dung secret |
| Giá trị secret | Secret manager hoặc cơ chế cấp credential được bảo vệ | Database password, API token, client private key | Commit plaintext vào Git, image, log, artifact build |
| Danh tính ứng dụng | Role/identity được gắn ở hạ tầng triển khai | AWS IAM Role, Azure Managed Identity, GCP Workload Identity | Tạo khóa tĩnh chỉ để SDK đăng nhập khi runtime có identity |

Các giải pháp thường gặp:

- **AWS:** IAM Roles cho workload; Secrets Manager hoặc Systems Manager Parameter Store cho secret/parameter thích hợp.
- **Azure:** Managed Identity; Azure Key Vault cho secret, Azure App Configuration cho key/value cấu hình.
- **Google Cloud:** Workload Identity hoặc Application Default Credentials; Secret Manager cho secret, các nguồn config phù hợp với môi trường chạy cho tham số thông thường.

Tùy phiên bản, starter Spring Cloud có thể nạp dữ liệu từ kho remote thành Spring `PropertySource`, hỗ trợ `spring.config.import`, hoặc chỉ cung cấp SDK để truy vấn khi chạy. Không tự suy đoán cú pháp import: cần kiểm tra starter/version thực sự hỗ trợ.

### Tham chiếu secret khác giá trị secret

Ví dụ cấu hình chỉ giữ tên tham chiếu:

```yaml
app:
  integration:
    third-party-api:
      credential-secret-ref: ${API_CREDENTIAL_SECRET_REF}
```

`credential-secret-ref` có thể là tên/URI của mục bí mật ở kho secret. Đây là **định danh của một tài nguyên bí mật**; nó không phải token thực tế. Mã tích hợp hoặc thư viện chuyên trách dùng tham chiếu đó và danh tính workload để đọc giá trị trong runtime.

```mermaid
flowchart LR
    A["Cấu hình: tên/URI secret"] --> C["Secret client"]
    B["Workload identity"] --> C
    C --> D["Secret manager"]
    D --> E["Giá trị secret được trả qua kênh được bảo vệ"]
    E --> F["SDK / đối tác cần xác thực"]
```

Nếu thư viện cloud đã tự cung cấp credential cho SDK bằng role/managed identity, **không cần tạo secret chỉ để lưu một khóa mà SDK có thể lấy an toàn và tự động**.

### Trường hợp vẫn phải cấp password qua cấu hình

Một số hệ thống chưa hỗ trợ identity-based authentication, như database hoặc API bên thứ ba chỉ nhận password. Khi đó cần thiết kế đường cấp secret rõ ràng. Ví dụ placeholder:

```yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

Tệp trên không chứa mật khẩu thật, nhưng **giá trị `DB_PASSWORD` khi chạy vẫn là secret**. Biến môi trường có thể bị nhìn thấy qua công cụ quản trị container, bản dump hoặc cấu hình triển khai. Nếu có thể, ưu tiên secret store, file mount có phân quyền và cơ chế identity để giảm nguy cơ rò rỉ; tránh truyền mật khẩu thật bằng command-line argument vì có thể xuất hiện trong process list hoặc shell history.

## 7. Những trường hợp dễ phân loại nhầm

### 7.1. “Connection string” có thể là secret

Hai chuỗi trông tương tự nhau:

```text
# Chỉ là endpoint và tên database
jdbc:postgresql://db.internal.example:5432/inventory

# Có password được nhúng vào URL: phải bảo vệ toàn bộ chuỗi
postgresql://inventory_user:super-secret@example.internal:5432/inventory
```

Dòng thứ hai chỉ là **minh họa cấu trúc nhạy cảm**, không phải một credential thật. Cách phân loại đúng phụ thuộc **nội dung chuỗi**, không phụ thuộc tên `connection-string` hay `url`. Azure Storage connection string có `AccountKey=...` hoặc Service Bus connection string có `SharedAccessKey=...` là credential và phải xử lý như secret.

### 7.2. URI vừa là địa chỉ vừa mang quyền truy cập

- URL public không chứa token thường là định danh/endpoint.
- URL có query parameter `sig`, `token`, `X-Amz-Signature` hoặc các thông số ký truy cập phải được coi là **bí mật trong thời gian có hiệu lực**, vì người nhận URL có thể sử dụng quyền mà nó mang theo.
- Không ghi nguyên URL ký sẵn vào access log, message error, tracing span, dashboard hoặc email hỗ trợ khách hàng.

### 7.3. Secret đã mã hóa vẫn cần được bảo vệ

Ciphertext được mã hóa **không mặc nhiên có thể công khai**. Cần cân nhắc khả năng giải mã, vị trí key, phạm vi người đọc và chính sách tổ chức. Ngay cả khi giữ ciphertext trong Git, ứng dụng vẫn cần cơ chế cấp khóa giải mã an toàn; không nên đặt ciphertext và khóa giải mã cạnh nhau.

Một **hash mật khẩu** cũng không tương đương tham số vô hại: có thể bị khai thác nếu thuật toán hoặc chính sách lưu trữ yếu. Phân loại phải xét rủi ro, không dựa vào việc giá trị có “trông như mật khẩu” hay không.

### 7.4. Tên tài nguyên không phải quyền truy cập

Gán `STORAGE_TARGET=prod-financial-documents` chỉ khiến adapter hướng tới bucket/container đó. Nếu principal của ứng dụng không có quyền ghi, API trả lỗi phân quyền. Ngược lại, ứng dụng có quyền rộng bất thường có thể ghi nhầm vào tài nguyên khác nếu cấu hình sai.

Vì thế cần **cả validation định danh lẫn giới hạn IAM/RBAC**: tên/resource phải đúng môi trường, và workload identity chỉ được phép thao tác trên phạm vi cần thiết.

## 8. Vòng đời và người chịu trách nhiệm cho từng loại

| Hoạt động | Tham số cấu hình | Định danh tài nguyên | Bí mật |
| --- | --- | --- | --- |
| Tạo mới | Developer/ops định nghĩa giá trị và default | IaC/infra tạo resource, xuất ra tên/ID | Identity hoặc secret manager cấp credential |
| Lưu trữ | Git, config repo, external config | Deployment config, IaC outputs | Secret manager, secure mount, credential provider |
| Kiểm tra | Type conversion, range, business rules | Resource name/URI format, môi trường, tồn tại | Quyền đọc, hiệu lực, hết hạn, scope |
| Thay đổi | Config rollout/refresh nếu hỗ trợ | Cập nhật deployment và quyền truy cập | Rotation, revoke, cấp lại token và refresh client |
| Ghi log | Chỉ log các giá trị không nhạy cảm khi cần | Có thể log ID đã rút gọn theo chính sách | Không log plaintext, token hoặc private key |
| Sự cố phổ biến | Timeout quá ngắn | Sai bucket/topic/project/namespace | Token hết hạn, sai credential, bị thu hồi |

Một thay đổi **định danh tài nguyên** có thể kéo theo thay đổi **quyền**. Ví dụ đổi destination sang queue SQS khác có thể yêu cầu `sqs:SendMessage` trên queue ARN mới; đổi Pub/Sub topic có thể yêu cầu `roles/pubsub.publisher` tại topic mới. Đây là hai việc vận hành khác nhau, dù cùng xuất hiện trong một đợt deploy.

Một thay đổi **secret** có thể cần khởi tạo lại connection pool, HTTP client hoặc SDK client đang giữ credential cũ. Cập nhật Secret Manager không bảo đảm mọi bean Spring Boot tự refresh tức thời. Chọn cơ chế refresh, restart hoặc rollout theo thư viện và yêu cầu dịch vụ.

## 9. Logging, Actuator và xử lý lỗi không làm lộ bí mật

Trong Spring Boot, cấu hình có thể bị tiết lộ ngoài ý muốn qua:

- Log toàn bộ `Environment`, bean `@ConfigurationProperties` hoặc object sinh `toString()`.
- Endpoint Actuator như `/actuator/env` và `/actuator/configprops` khi cấu hình quyền truy cập và che giá trị không chặt chẽ.
- Exception chứa cả connection string, URL ký sẵn hoặc request header.
- Metrics tag, trace attributes, message payload, health check response hoặc crash dump.
- CI/CD log, artifact build, container metadata và cấu hình cloud deployment.

Thực hành an toàn:

1. **Không log secret hoặc giá trị có thể đóng vai trò credential.** Với lỗi xác thực, log mã lỗi, loại provider, thao tác và correlation ID thay vì token.
2. **Phân biệt metadata với secret trong thông báo lỗi.** Có thể ghi `provider=aws` và `operation=PutObject`; chỉ ghi tên bucket/ARN nếu chính sách quan sát cho phép.
3. **Che giá trị cả ở lớp ứng dụng lẫn hạ tầng.** Không trông chờ một regex che `password` là đủ vì secret có thể mang tên `token`, `authorization`, `sas`, `sig` hoặc nằm trong URL.
4. **Bảo vệ Actuator** bằng authentication, authorization, mạng nội bộ và cấu hình hiển thị phù hợp. Đừng bật chế độ xuất toàn bộ giá trị trong production.
5. **Giới hạn quyền đọc secret của workload** và quyền xem secret trong CI/CD. Quyền ứng dụng đọc một mục secret không đồng nghĩa nhân viên hoặc toàn bộ pipeline được xem nội dung đó.

Một thông báo lỗi hữu ích mà không lộ credential:

```text
Storage upload failed:
  provider=aws
  operation=PutObject
  resourceAlias=document-archive
  reason=AccessDenied
  requestId=<provider-request-id>
```

Ở đây `resourceAlias` là nhãn vận hành được phép log, không nhất thiết là tên bucket thật. Khi điều tra, kết hợp request ID với cloud audit logs để xác định principal và phạm vi resource được truy cập.

## 10. Kiểm thử cấu hình, định danh và secret tách theo trách nhiệm

Ba nhóm dữ liệu dẫn đến ba loại kiểm thử khác nhau:

| Mục tiêu | Cách kiểm tra | Không thể kết luận chỉ từ kết quả này |
| --- | --- | --- |
| Tham số đúng kiểu và khoảng giá trị | Unit test binding + Bean Validation với `ApplicationContextRunner` | Cloud SDK đã dùng timeout/retry đúng |
| Định danh đúng cú pháp | Validation theo adapter, test mapping tên bucket/container/topic | Resource đang tồn tại hoặc đã có quyền |
| Tài nguyên đúng môi trường | Integration test ở môi trường test, so sánh ID được cấp qua IaC | Credential sẽ còn hiệu lực sau rotation |
| Danh tính và quyền phù hợp | Integration test với workload identity test được cấp quyền tối thiểu | Secret không bị lộ qua log hoặc telemetry |
| Secret được lấy an toàn | Test secret store/mount với dữ liệu giả, test refresh/rotation | Production secret có thể được dùng trong unit test |
| Không lộ dữ liệu | Test log redaction và kiểm tra endpoint vận hành trong môi trường kiểm soát | Toàn bộ hệ thống giám sát bên ngoài đều an toàn |

### Ví dụ các tình huống cần thử

**Tình huống A — lỗi tham số:** `app.integration.retry.max-attempts=0`. Spring Boot nên phát hiện lỗi Bean Validation trong startup, chưa cần kết nối cloud.

**Tình huống B — lỗi định danh:** `STORAGE_TARGET` là tên bucket có ký tự không hợp lệ với provider được chọn. Adapter nên từ chối trước request nếu có thể; SDK/provider cũng có thể trả validation error.

**Tình huống C — lỗi quyền:** bucket/container tồn tại nhưng workload identity thiếu quyền ghi. Dù property binding thành công, thao tác upload phải thất bại với lỗi phân quyền rõ ràng.

**Tình huống D — secret không truy cập được:** tham chiếu secret đúng cú pháp nhưng runtime không có quyền đọc. Ứng dụng không được tự dùng placeholder/default credential giả để tiếp tục gọi dịch vụ có yêu cầu bảo mật.

**Tình huống E — rotation:** thay credential ở secret store. Kiểm tra ứng dụng đọc phiên bản mới khi nào, SDK/client có cache hay không, và có cần restart/rollout.

### Bài tập phân loại

Hãy phân loại các giá trị sau, sau đó so sánh với lời giải:

| Giá trị | Nhóm chính | Giải thích |
| --- | --- | --- |
| `app.storage.operation-timeout=5s` | Tham số | Điều chỉnh hành vi chờ của ứng dụng |
| `AWS_REGION=ap-southeast-1` | Tham số/phạm vi triển khai | Chọn khu vực chạy hoặc kết nối; không chứng minh quyền |
| `STORAGE_TARGET=documents-prod` | Định danh tài nguyên | Tên bucket/container |
| `AZURE_STORAGE_ACCOUNT=storageprod` | Định danh tài nguyên | Tên storage account |
| `GOOGLE_CLOUD_PROJECT=example-prod` | Định danh tài nguyên/phạm vi | Project ID |
| `projects/example-prod/topics/orders` | Định danh tài nguyên | Tên Pub/Sub topic |
| `AZURE_CLIENT_ID` (giá trị là UUID) | Định danh principal | Không phải client secret |
| `AZURE_CLIENT_SECRET` | Bí mật | Dùng để chứng minh danh tính của client |
| Service account JSON có `private_key` | Bí mật | Chứa khóa riêng |
| URI của một mục trong Key Vault | Tham chiếu tài nguyên | Chỉ là địa chỉ secret, trừ khi URI kèm token có quyền |
| S3 presigned URL còn hiệu lực | Bí mật | Người có URL có thể sử dụng quyền đã ký |

Các ví dụ nhấn mạnh một giá trị có thể là **tham số hoặc metadata không bí mật** về mặt kỹ thuật, nhưng vẫn có mức độ nhạy cảm tùy tổ chức. Khi không chắc liệu URL/connection string có chứa credential hay không, hãy **xử lý như secret cho đến khi đã kiểm tra thành phần của nó**.

## 11. Bài thực hành tích hợp ba cloud

Một đội phát triển triển khai cùng tính năng “lưu hóa đơn và gửi sự kiện” trên AWS, Azure và GCP. Hãy xây dựng một hợp đồng cấu hình cho ứng dụng Spring Boot theo các bước:

1. **Xác định các nhóm dữ liệu.** Đặt `provider`, `operation-timeout` và `retry.max-attempts` vào nhóm tham số; `storage.target` và `messaging.destination` vào nhóm định danh tài nguyên; không đưa credential thật vào các nhóm này.
2. **Tách file và nguồn theo môi trường.** Dùng `application.yml` cho default phi nhạy cảm; profile để chọn provider; environment hoặc external config để nhận tên bucket/container/topic theo deployment.
3. **Cấu hình danh tính workload.** Với AWS dùng IAM Role, Azure dùng Managed Identity/Workload Identity, GCP dùng Workload Identity hoặc ADC phù hợp. Xác nhận runtime không yêu cầu hardcode long-lived credential.
4. **Tạo adapter riêng.** Adapter S3 đọc tên bucket; adapter Azure Blob đọc tên container; adapter GCS đọc tên bucket. Adapter messaging chuyển `destination` thành định danh queue/topic đúng SDK.
5. **Kiểm thử sai lệch.** Thử thiếu `STORAGE_TARGET`, tên resource không hợp lệ, resource không tồn tại, thiếu quyền ghi và secret store không truy cập được. Ghi nhận lỗi phát hiện ở giai đoạn binding hay khi gọi provider.
6. **Rà soát thông tin nhạy cảm.** Kiểm tra log, thông báo lỗi, Actuator, CI/CD và tracing; xác nhận không xuất hiện token, password, private key hoặc signed URL.
7. **Kiểm thử vận hành.** Thay bucket/topic của môi trường test để xác nhận adapter và IAM/RBAC cùng cập nhật; xoay vòng credential của một dịch vụ bên thứ ba để kiểm tra refresh/restart.

**Kết quả mong đợi:** từ bất kỳ key cấu hình nào, người học giải thích được **nó là chính sách vận hành, tên tài nguyên, danh tính hay bí mật**, ai cung cấp giá trị, nơi lưu trữ phù hợp và loại kiểm thử cần thiết. Khi thay cloud provider, phần nghiệp vụ có thể giữ hợp đồng cấu hình chung trong khi adapter, định danh tài nguyên và cơ chế xác thực thay đổi theo nền tảng.

## 12. Ghi nhớ

- **Tham số cấu hình** điều chỉnh hành vi; **định danh tài nguyên** chỉ tới nơi ứng dụng thao tác; **bí mật** chứa khả năng chứng minh quyền hoặc truy cập. Tên biến giống nhau không bảo đảm cùng cách phân loại.
- **Định danh không phải credential**. Bucket name, project ID, tenant ID và service account email thường là identifier; private key, client secret, token và URL ký sẵn mang quyền phải được bảo vệ.
- Tận dụng **workload identity và quyền tối thiểu** thay cho khóa tĩnh khi có thể. Sự tồn tại của tài nguyên và cú pháp hợp lệ không chứng minh workload đã có quyền.
- Dùng `@ConfigurationProperties` và validation để kiểm tra tham số/định danh; để secret manager hoặc credential provider xử lý bí mật, tránh đưa giá trị nhạy cảm vào Git và log.
- Mỗi lần đổi môi trường, resource hoặc secret cần kiểm tra **cấu hình hiệu lực, quyền IAM/RBAC, khả năng refresh/rotation và dấu vết dữ liệu nhạy cảm** trong hệ thống vận hành.
