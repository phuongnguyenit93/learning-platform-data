# Secrets Manager và lưu trữ bí mật ứng dụng

Một ứng dụng Spring Boot cần kết nối tới Amazon RDS, gọi API của đối tác và ký request tới một dịch vụ nội bộ. Nếu username/password, API key hoặc token được ghi thẳng trong source code, file cấu hình, Docker image hay biến môi trường dài hạn, bí mật có thể bị lộ qua Git, CI logs, image registry, process inspection hoặc bản sao lưu.

**AWS Secrets Manager** là dịch vụ quản lý secret tập trung. Ứng dụng có thể lấy secret khi chạy bằng IAM role; Secrets Manager mã hóa giá trị bằng AWS KMS, quản lý các phiên bản secret và hỗ trợ rotation tự động. Secret có thể được chia sẻ có kiểm soát giữa service, account và Region.

Với Java, cách tích hợp thường là AWS SDK for Java 2.x hoặc thư viện caching Java của Secrets Manager. Không nên gọi API lấy secret cho mọi request; cache trong process giúp giảm latency và API cost. Tuy nhiên, cache phải được thiết kế cùng chu kỳ rotation để ứng dụng không tiếp tục dùng credential cũ quá lâu.

Bài học thuộc chương **Mã hóa, secret và chứng chỉ** của module **CLOUD_PROVIDERS_AWS**. Nội dung tập trung vào vòng đời secret, version/staging labels, IAM/KMS, rotation, Java integration, caching, private connectivity, cross-account access, multi-Region replication và quy trình vận hành an toàn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt secret với configuration thông thường.
2. Mô tả thành phần của một secret và cách Secrets Manager lưu các phiên bản.
3. Giải thích vai trò của `AWSCURRENT`, `AWSPREVIOUS` và `AWSPENDING`.
4. Tạo secret dạng JSON hoặc binary và quản lý version.
5. Lấy secret bằng AWS Console, CLI và AWS SDK for Java 2.x.
6. Tích hợp Secrets Manager với Spring Boot bằng IAM role.
7. Dùng Java caching client và chọn TTL phù hợp.
8. Giải thích envelope encryption bằng AWS KMS.
9. Cấp quyền `GetSecretValue` và `kms:Decrypt` theo least privilege.
10. Phân biệt AWS managed key với customer managed KMS key.
11. Thiết lập automatic rotation và hiểu bốn bước của rotation Lambda.
12. So sánh single-user rotation với alternating-users rotation.
13. Thiết kế ứng dụng chịu được credential rotation.
14. Cấu hình VPC interface endpoint cho Secrets Manager.
15. Cấp quyền truy cập secret giữa các AWS accounts.
16. Replicate secret tới nhiều AWS Regions và theo dõi replication status.
17. Dùng CloudTrail để audit mà không ghi lộ secret value.
18. Quản lý deletion recovery window, version quota và chi phí.
19. Chẩn đoán lỗi IAM, KMS, rotation, cache và network.
20. Xây dựng checklist bảo vệ secret trong production.

## 2. Secret là gì và khi nào nên dùng?

Secret là dữ liệu nhạy cảm mà ứng dụng hoặc người vận hành cần để xác thực, cấp quyền hoặc truy cập một tài nguyên. Ví dụ:

- Username/password của database.
- API key của đối tác.
- OAuth client secret.
- Private token dùng cho service-to-service authentication.
- Credential của hệ thống bên ngoài AWS.
- Thông tin xác thực cho một workload hoặc automation.

Không phải mọi cấu hình đều là secret. Region, log level, feature flag không nhạy cảm thường phù hợp với AWS Systems Manager Parameter Store hoặc AppConfig. Credential và key cần kiểm soát truy cập, mã hóa, rotation và audit thường phù hợp với Secrets Manager.

| Nhu cầu | Lựa chọn thường gặp |
|---|---|
| Database password cần rotation | Secrets Manager |
| API key cần quản lý version và rotation | Secrets Manager |
| Feature flag hoặc cấu hình không nhạy cảm | AWS AppConfig |
| Giá trị cấu hình phân cấp, có thể là SecureString | Systems Manager Parameter Store |
| Private key/certificate lifecycle chuyên biệt | AWS Certificate Manager hoặc giải pháp PKI phù hợp |
| AWS workload credentials tạm thời | IAM role/STS, không tạo access key dài hạn để lưu trong secret |

Secrets Manager không thay thế IAM role. Nếu ứng dụng chỉ cần gọi AWS APIs, hãy dùng temporary credentials từ task role, instance profile hoặc workload identity. Không tạo access key cho IAM user rồi lưu lại trong Secrets Manager nếu role có thể đáp ứng nhu cầu.

## 3. Kiến trúc lưu trữ và truy xuất

Một ứng dụng chạy trên ECS task cần database credential:

    Spring Boot application
            |
            | IAM task role
            v
      AWS Secrets Manager
            |
            | KMS envelope encryption
            v
       Encrypted secret value

Khi ứng dụng lấy secret:

1. AWS SDK lấy temporary credentials từ task role.
2. SDK gọi `GetSecretValue` tới Secrets Manager.
3. Secrets Manager kiểm tra IAM/resource policy.
4. Secrets Manager yêu cầu AWS KMS giải mã data key.
5. Secrets Manager giải mã secret value và trả về qua TLS.
6. Ứng dụng parse secret và sử dụng để kết nối database.

Ứng dụng cần quyền đọc secret cụ thể. Nó không cần quyền tạo, sửa, xóa hoặc cấu hình rotation secret nếu nhiệm vụ chỉ là runtime retrieval.

### 3.1. Secret value và metadata

Một secret gồm các phần:

| Thành phần | Ví dụ | Có được mã hóa như secret value? |
|---|---|---|
| Secret value | JSON username/password | Có |
| Secret name | `prod/orders/database` | Không |
| Description | Credential for orders database | Không |
| Tags | `Environment=prod` | Không |
| Rotation configuration | Lambda ARN/schedule | Không |
| KMS key reference | ARN của key | Không |

Không đặt password, token hoặc thông tin nhạy cảm trong name, description hay tags. Những trường metadata này có thể xuất hiện trong inventory, API response hoặc audit logs.

### 3.2. SecretString và SecretBinary

Secrets Manager hỗ trợ:

- `SecretString`: chuỗi UTF-8, thường là JSON hoặc text.
- `SecretBinary`: dữ liệu nhị phân, chẳng hạn một blob credential hoặc material được mã hóa ở tầng ứng dụng.

Với database credentials, JSON giúp lưu username, password, host, port, engine và database name trong cùng một secret. Với binary, ứng dụng phải tự xử lý định dạng và giải mã ở tầng phù hợp.

Ví dụ JSON minh họa:

~~~json
{
  "engine": "mysql",
  "host": "orders-db.example.ap-southeast-1.rds.amazonaws.com",
  "port": 3306,
  "dbname": "orders",
  "username": "orders_app",
  "password": "REPLACE_WITH_SECRET_VALUE"
}
~~~

Đây là cấu trúc minh họa. Không lưu giá trị thực vào source code hoặc tài liệu. Secrets Manager chỉ bảo vệ secret value; metadata vẫn cần được đặt tên an toàn.

## 4. Secret versions và staging labels

Khi secret value thay đổi, Secrets Manager tạo một version mới. Mỗi version có VersionId và có thể gắn staging labels để thể hiện vai trò trong lifecycle.

| Staging label | Ý nghĩa |
|---|---|
| `AWSCURRENT` | Phiên bản ứng dụng nên dùng mặc định |
| `AWSPREVIOUS` | Phiên bản từng là current trước đó |
| `AWSPENDING` | Phiên bản mới đang được chuẩn bị trong rotation |

Secrets Manager không giữ lịch sử theo dạng một danh sách tuyến tính với trạng thái cố định. Labels được di chuyển giữa các version. Mỗi secret luôn có một version `AWSCURRENT`; khi gọi `GetSecretValue` mà không chỉ định version, service trả version hiện hành.

Ví dụ:

    Version A: AWSPREVIOUS
    Version B: AWSCURRENT
    Version C: AWSPENDING

Trong rotation, Lambda tạo version pending, cập nhật credential tại database, kiểm tra credential mới rồi chuyển `AWSCURRENT` sang version đó.

### 4.1. VersionId và staging label

- VersionId xác định một version cụ thể.
- Staging label xác định vai trò của version trong lifecycle.
- Một version có thể có nhiều labels.
- Một label chỉ được gắn vào một version tại một thời điểm.
- Có thể tạo custom labels cho quy trình nội bộ, tối đa 20 labels trên một secret.

Ứng dụng production thường nên yêu cầu `AWSCURRENT` thay vì hard-code VersionId. Nếu hard-code VersionId, ứng dụng có thể tiếp tục dùng credential cũ sau khi rotation thành công.

### 4.2. Di chuyển staging label

Khi `AWSCURRENT` được chuyển sang version mới, Secrets Manager tự động chuyển `AWSPREVIOUS` sang version vừa bị thay thế. Điều này cho phép rollback về version trước nếu cần, miễn credential cũ vẫn còn hợp lệ tại hệ thống đích.

Không tự ý gỡ `AWSPENDING` giữa một rotation đang chạy. Rotation function dựa vào label này để nhận diện tiến trình và tính idempotency.

### 4.3. Giới hạn version

Secrets Manager giữ tối đa 100 version gần nhất và không xóa version được tạo trong 24 giờ gần nhất. Các version không còn staging labels được xem là deprecated và có thể được dọn dẹp khi vượt quota.

AWS khuyến nghị không gọi `PutSecretValue` hoặc `UpdateSecret` liên tục với tần suất cao hơn một lần mỗi 10 phút. Nếu cập nhật quá thường xuyên, số version mới có thể tăng nhanh hơn tốc độ dọn dẹp và chạm quota.

Không dùng Secrets Manager như một database để ghi trạng thái thường xuyên. Secret phù hợp với credential và giá trị nhạy cảm có vòng đời tương đối ổn định.

## 5. Tạo secret và đặt tên

Đặt tên theo service, môi trường và mục đích:

    prod/orders/database
    prod/payment/provider-api
    staging/inventory/database
    shared/partner-x/oauth-client

Một convention tốt giúp IAM policy, inventory và audit dễ đọc. Tên secret không nên chứa username/password hoặc PII.

Nên chuẩn hóa environment, service, purpose, owner/team tag, data classification và rotation owner nếu tổ chức có taxonomy.

### 5.1. Tạo secret bằng Console

1. Mở AWS Secrets Manager trong đúng Region.
2. Chọn Store a new secret.
3. Chọn loại secret phù hợp, ví dụ credentials for Amazon RDS database.
4. Nhập secret value.
5. Chọn KMS key.
6. Đặt secret name và description an toàn.
7. Thêm tags không nhạy cảm.
8. Cấu hình rotation nếu loại secret và target hỗ trợ.
9. Review quyền truy cập và tạo secret.

Sau khi tạo, kiểm tra ARN, KMS key, version stage và policy. Đừng chia sẻ secret value qua ảnh chụp màn hình hoặc ticket.

### 5.2. Tạo secret bằng AWS CLI

Có thể dùng `create-secret` và đọc value từ file được bảo vệ:

~~~bash
aws secretsmanager create-secret \
  --name "prod/orders/database" \
  --description "Database credentials for orders service" \
  --secret-string file://secret.json \
  --region ap-southeast-1
~~~

File `secret.json` phải được tạo với quyền filesystem hạn chế, không đưa vào Git, CI artifact hoặc log. Xóa file theo quy trình bảo vệ dữ liệu sau khi thao tác hoàn tất.

Không truyền password thật trực tiếp trong command line như `--secret-string '{"password":"..."}'`. Shell history, process inspection hoặc CI command logging có thể làm lộ tham số.

### 5.3. Cập nhật secret value

Dùng `PutSecretValue` để tạo version mới:

~~~bash
aws secretsmanager put-secret-value \
  --secret-id "prod/orders/database" \
  --secret-string file://secret-next.json \
  --region ap-southeast-1
~~~

Nếu không chỉ định VersionStages, Secrets Manager gắn `AWSCURRENT` vào version mới và chuyển `AWSPREVIOUS` theo quy tắc version stage.

Không cập nhật cùng secret liên tục cho từng lần deploy. Nếu credential chưa thay đổi, ứng dụng chỉ cần đọc secret hiện tại; không tạo version mới.

## 6. IAM: quyền đọc secret theo least privilege

Một ứng dụng chỉ cần lấy secret thường cần:

- `secretsmanager:GetSecretValue` trên ARN secret cụ thể.
- `kms:Decrypt` trên customer managed key nếu secret dùng key do bạn quản lý và key policy yêu cầu quyền này.

Ví dụ identity policy tối giản cho ứng dụng:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrdersDatabaseSecret",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:prod/orders/database-AbCdEf"
    }
  ]
}
~~~

Nếu dùng customer managed KMS key, bổ sung quyền `kms:Decrypt` cho key ARN tương ứng và bảo đảm key policy cho phép principal đó. Không cần cấp `secretsmanager:PutSecretValue`, `DeleteSecret` hoặc `RotateSecret` cho runtime application nếu ứng dụng chỉ đọc.

### 6.1. Dùng IAM role thay access key

| Nền tảng | Identity nên dùng |
|---|---|
| Amazon EC2 | Instance profile |
| Amazon ECS | Task role |
| Amazon EKS | EKS Pod Identity hoặc IRSA theo kiến trúc |
| AWS Lambda | Execution role |
| On-premises | IAM Roles Anywhere hoặc credential federation phù hợp |

Không đưa access key/secret key vào `application.properties`, Docker ENV, Kubernetes Secret tĩnh hoặc AMI. Runtime credentials nên được cấp tự động và có thời hạn.

### 6.2. Secrets Manager resource policy

Resource policy gắn trực tiếp vào secret để xác định principal được phép truy cập. Nó hữu ích khi nhiều role/account cần dùng cùng một secret.

Khi gắn policy:

- Dùng `BlockPublicPolicy` khi gọi `PutResourcePolicy`.
- Dùng `ValidateResourcePolicy` hoặc console validation.
- Tránh Principal `*` nếu không có điều kiện giới hạn chặt.
- Không cấp `PutResourcePolicy` cho application role.
- Review cả identity policy, resource policy và KMS key policy.

Một resource policy không tự động thay thế identity policy trong mọi tình huống. Quyền truy cập cuối cùng phụ thuộc toàn bộ authorization model, explicit deny, SCP/RCP, permissions boundary và KMS.

## 7. Mã hóa secret bằng AWS KMS

Secrets Manager dùng **envelope encryption**. KMS không trực tiếp mã hóa toàn bộ secret value; KMS tạo và bảo vệ data key dùng để mã hóa giá trị.

Quy trình ghi:

1. Secrets Manager gọi KMS `GenerateDataKey` để lấy plaintext data key và encrypted data key.
2. Secrets Manager dùng AES để mã hóa secret value bằng plaintext data key.
3. Plaintext data key được loại bỏ khỏi bộ nhớ khi không còn cần.
4. Encrypted data key được lưu cùng metadata của secret.

Quy trình đọc:

1. Secrets Manager lấy encrypted data key.
2. Gọi KMS `Decrypt` để giải mã data key.
3. Dùng data key giải mã secret value.
4. Trả secret cho caller qua TLS.

Secret value được mã hóa at rest. Tên secret, description, tags, rotation settings và KMS key ARN không được mã hóa như secret value.

### 7.1. AWS managed key và customer managed key

| Tiêu chí | `aws/secretsmanager` | Customer managed KMS key |
|---|---|---|
| Quản trị key policy | AWS quản lý | Khách hàng quản lý |
| Chi phí key | Không tính phí key | Có phí KMS key/API theo pricing |
| Cross-account access | Không phù hợp | Có thể cấu hình |
| Key rotation policy | AWS quản lý | Có thể bật automatic rotation |
| Kiểm soát điều kiện KMS | Hạn chế | Có thể tùy chỉnh key policy/grants |

Với phần lớn secret trong một account, AWS khuyến nghị dùng `aws/secretsmanager`. Dùng customer managed key khi cần cross-account access, key policy riêng hoặc yêu cầu quản trị khóa cụ thể.

### 7.2. Giới hạn quyền KMS bằng ViaService và encryption context

Có thể giới hạn key chỉ được dùng qua Secrets Manager bằng condition `kms:ViaService` với hostname theo Region:

    secretsmanager.ap-southeast-1.amazonaws.com

Có thể kết hợp encryption context, chẳng hạn SecretARN, để giới hạn key operations cho một secret cụ thể. Điều này giảm khả năng dùng key ngoài mục đích dự kiến.

Không tự viết key policy quá rộng chỉ để khắc phục `AccessDenied`. Xác định principal, KMS action, ViaService, encryption context và explicit deny trước khi sửa.

## 8. Lấy secret bằng AWS SDK for Java 2.x

AWS SDK for Java 2.x cung cấp `SecretsManagerClient` và `GetSecretValueRequest`.

Maven dependency:

~~~xml
<dependency>
  <groupId>software.amazon.awssdk</groupId>
  <artifactId>secretsmanager</artifactId>
  <version>AWS_SDK_VERSION</version>
</dependency>
~~~

Giá trị `AWS_SDK_VERSION` nên được quản lý tập trung bằng AWS SDK BOM để các module dùng cùng version tương thích.

Ví dụ Java:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.secretsmanager.SecretsManagerClient;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueRequest;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueResponse;

public final class DatabaseSecretLoader {
    private final SecretsManagerClient client;
    private final ObjectMapper mapper = new ObjectMapper();

    public DatabaseSecretLoader(Region region) {
        this.client = SecretsManagerClient.builder()
                .region(region)
                .build();
    }

    public DatabaseCredentials load(String secretId) throws Exception {
        GetSecretValueRequest request = GetSecretValueRequest.builder()
                .secretId(secretId)
                .versionStage("AWSCURRENT")
                .build();

        GetSecretValueResponse response = client.getSecretValue(request);
        JsonNode json = mapper.readTree(response.secretString());

        return new DatabaseCredentials(
                json.path("host").asText(),
                json.path("port").asInt(),
                json.path("dbname").asText(),
                json.path("username").asText(),
                json.path("password").asText()
        );
    }

    public void close() {
        client.close();
    }
}
~~~

`DatabaseCredentials` là DTO do ứng dụng định nghĩa. Ví dụ lược bỏ validation và error mapping để tập trung vào API. Trong production, kiểm tra field bắt buộc, kiểu dữ liệu, port range và xử lý secret format sai.

### 8.1. Reuse client và credentials provider

Không tạo `SecretsManagerClient` mới cho mỗi HTTP request. AWS SDK client là thread-safe và nên được tái sử dụng trong application lifecycle.

Khi chạy trên AWS, SDK default credentials provider chain có thể lấy credentials từ task role, instance profile hoặc Lambda execution role. Không truyền access key trực tiếp vào source code.

Ví dụ Spring configuration:

~~~java
@Configuration
public class SecretsConfiguration {
    @Bean(destroyMethod = "close")
    SecretsManagerClient secretsManagerClient() {
        return SecretsManagerClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();
    }
}
~~~

Trong ứng dụng lớn, inject client/secret provider vào service thay vì gọi builder ở nhiều nơi.

### 8.2. Lấy secret dạng binary

Nếu secret dùng `SecretBinary`, đọc `response.secretBinary()` và xử lý byte buffer theo format đã thỏa thuận. Không giả định mọi secret đều có `secretString()`.

### 8.3. BatchGetSecretValue

Nếu ứng dụng cần nhiều secret, API `BatchGetSecretValue` có thể giảm số lần gọi riêng lẻ. Cần kiểm tra quota, filter và quyền của từng secret; một batch không có nghĩa mọi secret đều được phép đọc. Với ứng dụng thông thường, cache từng secret theo lifecycle thường dễ kiểm soát hơn.

## 9. Java client-side caching

AWS khuyến nghị cache secret ở client để giảm latency và chi phí API calls. Nếu mỗi request HTTP đều gọi `GetSecretValue`, ứng dụng sẽ phụ thuộc trực tiếp vào latency/availability của Secrets Manager và tạo lượng request không cần thiết.

Java caching client giữ secret trong memory của process, dùng LRU cache và refresh theo TTL.

Maven dependency của AWS Secrets Manager Java caching client:

~~~xml
<dependency>
  <groupId>com.amazonaws.secretsmanager</groupId>
  <artifactId>aws-secretsmanager-caching-java</artifactId>
  <version>2.2.0</version>
</dependency>
~~~

Kiểm tra release hiện hành trên repository chính thức trước khi pin version. Dòng v2 của thư viện dùng AWS SDK for Java 2.x.

Ví dụ:

~~~java
import com.amazonaws.secretsmanager.caching.SecretCache;
import com.amazonaws.secretsmanager.caching.SecretCacheConfiguration;
import java.util.concurrent.TimeUnit;

public final class CachedSecretProvider implements AutoCloseable {
    private final SecretCache cache;

    public CachedSecretProvider() {
        SecretCacheConfiguration config =
                new SecretCacheConfiguration()
                        .withCacheItemTTL(TimeUnit.MINUTES.toMillis(5));

        this.cache = new SecretCache(config);
    }

    public String getSecretJson(String secretId) {
        return cache.getSecretString(secretId);
    }

    @Override
    public void close() {
        cache.close();
    }
}
~~~

Khởi tạo cache một lần cho application process và đóng khi shutdown. Không tạo cache mới trong từng controller request.

### 9.1. TTL và rotation

Java caching client mặc định refresh secret khoảng mỗi giờ. Có thể cấu hình TTL ngắn hơn. TTL càng ngắn:

- Ứng dụng nhận credential mới nhanh hơn sau rotation.
- Số API calls tới Secrets Manager tăng.
- Phụ thuộc network/service nhiều hơn.
- Cache refresh có thể tạo tải đồng thời nếu nhiều instance refresh cùng lúc.

Chọn TTL dựa trên rotation interval, thời gian credential cũ còn được chấp nhận, số application instances và mức độ rủi ro. TTL 5 phút trong ví dụ chỉ là giá trị minh họa, không phải mặc định bắt buộc.

### 9.2. Cache không phải kho bí mật an toàn tuyệt đối

Tài liệu AWS lưu ý Java caching client không được thiết kế như một cache bảo mật chuyên dụng:

- Secret tồn tại trong process memory dưới dạng ứng dụng có thể sử dụng.
- Cache không tự force garbage collection khi reference được giải phóng.
- Implementation không có cache invalidation API tổng quát.
- Nếu refresh đồng bộ thất bại, cache có thể trả về secret cũ.
- Cache mặc định tập trung vào LRU/TTL, không tự mã hóa dữ liệu trong heap.

Bảo vệ heap dump, core dump, debug endpoint, memory inspection và quyền truy cập host. Nếu yêu cầu bảo vệ cache cao hơn, dùng hook/interface hoặc cache riêng có mã hóa và lifecycle phù hợp.

### 9.3. Thiết kế cache cùng connection pool

Khi database password rotate, connection pool có thể giữ kết nối đã xác thực bằng credential cũ. Rotation không tự động đóng tất cả database sessions.

Một chiến lược thực tế:

1. Cache secret với TTL được xác định.
2. Khi cache refresh, phát hiện version/credential mới theo cơ chế của ứng dụng.
3. Tạo hoặc cập nhật datasource/pool bằng credential mới.
4. Cho kết nối mới hoạt động và kiểm tra health.
5. Drain pool cũ rồi đóng connection.
6. Giữ retry có giới hạn cho lỗi authentication trong khoảng chuyển đổi.

Không tạo lại pool trên mọi request. Thực hiện refresh qua một cơ chế đồng bộ hóa và tránh nhiều thread cùng rebuild pool.

## 10. Rotation là gì?

Rotation là quá trình thay credential tại hệ thống đích và cập nhật secret tương ứng. Ví dụ, đổi password database và lưu password mới vào Secrets Manager.

Rotation giúp giảm thời gian một credential bị lộ vẫn có thể được sử dụng. Tuy nhiên, rotation chỉ an toàn khi ứng dụng, database và rotation function phối hợp đúng.

Secrets Manager hỗ trợ managed rotation cho một số AWS services, Lambda-based rotation cho nhiều loại database/service, single-user rotation, alternating-users rotation và rotation theo lịch `rate()` hoặc `cron()`.

Không phải mọi secret đều tự động rotate được. Với API key bên thứ ba hoặc credential do vendor quản lý, cần API/automation riêng hoặc quy trình đổi key theo khả năng của provider.

## 11. Rotation bằng Lambda: bốn bước

Với Lambda-based rotation, Secrets Manager gọi rotation function theo bốn bước:

    createSecret
        |
        v
    setSecret
        |
        v
    testSecret
        |
        v
    finishSecret
        |
        v
    AWSCURRENT moves to new version

| Bước | Công việc |
|---|---|
| `createSecret` | Tạo version mới và gắn `AWSPENDING` |
| `setSecret` | Cập nhật credential tại database/service |
| `testSecret` | Dùng credential mới để kiểm tra truy cập |
| `finishSecret` | Chuyển `AWSCURRENT` sang version mới |

### 11.1. createSecret

Rotation function kiểm tra version token đã tồn tại chưa. Nếu chưa, tạo secret value mới và lưu với `AWSPENDING`.

Việc dùng ClientRequestToken/version ID giúp rotation idempotent. Nếu Lambda được gọi lại do retry, function không nên tạo vô hạn các version khác nhau cho cùng một rotation request.

### 11.2. setSecret

Function dùng credential `AWSCURRENT` để xác thực tới database/service, sau đó thay credential đích bằng value `AWSPENDING`.

Đây là bước có quyền mạnh. Function phải xác minh current và pending secrets cùng trỏ tới đúng resource. Ví dụ, username và database host phải khớp với resource dự kiến. Nếu không, function có thể trở thành confused deputy và sửa credential của tài nguyên ngoài ý muốn.

Dùng query parameterization khi gửi statement tới database. Không ghi password vào CloudWatch Logs.

### 11.3. testSecret

Function dùng credential `AWSPENDING` để kết nối và kiểm tra quyền truy cập. Chỉ khi credential mới thực sự hoạt động mới hoàn tất rotation.

Test nên đủ để xác nhận authentication và quyền tối thiểu cần thiết, không thực hiện mutation nghiệp vụ không cần thiết.

### 11.4. finishSecret

Function chuyển `AWSCURRENT` sang version mới. Secrets Manager chuyển `AWSPREVIOUS` sang version vừa bị thay thế.

Không xóa `AWSPENDING` trước khi hoàn thành bước này. Nếu rotation thất bại, xem staging labels và CloudWatch Logs để xác định bước hỏng; không tự ý di chuyển labels khi chưa hiểu trạng thái.

## 12. Single-user và alternating-users rotation

### 12.1. Single-user rotation

Chiến lược single-user thay password của một database user. Đây là cách đơn giản và phù hợp với nhiều trường hợp.

Điểm cần lưu ý: có khoảng thời gian ngắn credential ở database và secret có thể chưa đồng bộ hoàn toàn. Ứng dụng có thể nhận authentication failure trong lúc chuyển đổi. Thiết kế retry hợp lý và refresh connection pool.

### 12.2. Alternating-users rotation

Chiến lược alternating-users dùng hai database users. Rotation function tạo hoặc duy trì user clone, rồi luân phiên credential giữa hai user.

    Rotation 1:
      orders_app       -> active
      orders_app_clone -> prepared

    Rotation 2:
      orders_app       -> prepared
      orders_app_clone -> active

Một user có thể tiếp tục hoạt động trong khi user còn lại được cập nhật. Điều này tăng khả năng availability nếu ứng dụng có thể chấp nhận hai user tương đương.

Cần một secret chứa admin credentials để clone user và đổi password. Admin credential phải được bảo vệ chặt hơn application credential. Một số dịch vụ/kiến trúc có giới hạn; ví dụ RDS Proxy không hỗ trợ alternating-users strategy theo tài liệu AWS.

| Tiêu chí | Single user | Alternating users |
|---|---|---|
| Số database users | Một | Hai |
| Độ phức tạp | Thấp | Cao hơn |
| Credential availability | Có khoảng chuyển đổi cần xử lý | Có user còn lại để phục vụ |
| Quyền cần cho rotation | Đổi password user | Clone/manage users |
| Phù hợp | Credential đơn giản, chấp nhận retry | Workload cần giảm gián đoạn |

## 13. Managed rotation cho AWS services

Một số AWS services có thể quản lý rotation trực tiếp hoặc tích hợp với Secrets Manager. Ví dụ có dịch vụ hỗ trợ quản lý password cho RDS/Aurora, Redshift hoặc DocumentDB tùy engine và cấu hình.

Managed rotation giúp giảm phần Lambda code mà khách hàng phải tự vận hành. Tuy vậy, ứng dụng vẫn phải lấy secret mới theo version stage, cache với TTL phù hợp, refresh connection pool, retry lỗi authentication tạm thời, dùng database user với quyền tối thiểu và kiểm tra lịch rotation.

Đối với các loại secret không có managed rotation, dùng Lambda rotation template hoặc custom rotation function theo hướng dẫn AWS.

## 14. Rotation schedule và rotation window

Secrets Manager hỗ trợ `rate()` và `cron()` expressions. Schedule sử dụng UTC.

Ví dụ:

~~~text
rate(7 days)
~~~

Rotate mỗi 7 ngày.

Ví dụ cron chạy 10:00 UTC mỗi ngày:

~~~text
cron(0 10 * * ? *)
~~~

Rotation có thể được lên lịch thường xuyên tới mỗi 4 giờ. Rotation window bắt đầu trên giờ; window duration mặc định phụ thuộc kiểu schedule và có thể cấu hình.

Khi chọn lịch, cân nhắc credential có được ứng dụng dùng liên tục không, maintenance window, database load, Lambda timeout/concurrency, replica propagation và khả năng on-call phản ứng khi rotation fail.

Không chọn rotation schedule chỉ theo yêu cầu “càng thường xuyên càng tốt”. Cần cân bằng risk, operational load và khả năng refresh credential của application.

## 15. Java application và rotation: tránh credential cũ

Một lỗi thường gặp là rotation đã thành công nhưng ứng dụng vẫn kết nối bằng password cũ do cache hoặc connection pool.

Thiết kế nên gồm:

1. Secret được đọc theo `AWSCURRENT`.
2. Cache TTL ngắn hơn mức chấp nhận stale credential.
3. Connection factory có thể tạo datasource/pool mới.
4. Khi authentication failure, ứng dụng có retry giới hạn và refresh secret theo cách an toàn.
5. Connection pool cũ được drain sau khi pool mới healthy.
6. Có metric/log chỉ ghi secret version ID hoặc stage, không ghi secret value.

Không retry vô hạn với password cũ. Không refresh secret cho mọi lỗi database; phân biệt authentication error với network timeout, SQL error hoặc database unavailable.

### 15.1. Race condition trong rotation

Nếu nhiều app instances refresh cùng thời điểm, chúng có thể tạo lượng lớn `GetSecretValue` calls và đồng thời reconnect database. Dùng jitter, backoff, single-flight refresh hoặc staggered refresh để giảm stampede.

Nếu database không chấp nhận hai credential đồng thời, phối hợp rotation window và connection pool rollout để tránh outage.

## 16. Rotation Lambda trong VPC

Rotation Lambda cần kết nối tới cả Secrets Manager và database/service đích. Nếu database ở private subnet, Lambda phải có network path tới database. Nếu Lambda không có Internet egress, cần interface VPC endpoint cho Secrets Manager để API calls không phải đi qua public endpoint/NAT.

Kiểm tra:

- Lambda security group outbound tới database port.
- Database security group inbound từ Lambda security group.
- Secrets Manager VPC endpoint và private DNS.
- Lambda role có quyền đọc/ghi secret, gọi rotation APIs và KMS nếu cần.
- Timeout/concurrency phù hợp.
- CloudWatch Logs không ghi secret value.

Không đặt Lambda rotation function trong subnet chỉ có route tới database nhưng thiếu endpoint/NAT cho Secrets Manager; rotation có thể timeout ở bước đầu.

## 17. Truy cập Secrets Manager qua VPC endpoint

Ứng dụng trong private subnet có thể dùng interface VPC endpoint:

    com.amazonaws.<region>.secretsmanager

Endpoint được triển khai qua AWS PrivateLink. Khi bật Private DNS, ứng dụng tiếp tục dùng regional hostname chuẩn của Secrets Manager nhưng DNS phân giải tới endpoint ENI.

Cần kiểm tra VPC DNS resolution/hostnames, endpoint subnet/AZ, endpoint security group inbound TCP 443 từ application security group, application egress TCP 443, endpoint policy, resolver và TLS. Không cần NAT Gateway chỉ để ứng dụng gọi Secrets Manager nếu interface endpoint đã hoạt động; ứng dụng vẫn có thể cần NAT hoặc endpoint khác cho các dịch vụ ngoài Secrets Manager.

## 18. Cross-account access tới secret

Để application role ở Account B đọc secret trong Account A, cần phối hợp:

1. Identity policy của role Account B cho phép `secretsmanager:GetSecretValue` trên secret ARN Account A.
2. Resource policy của secret Account A cho phép role Account B.
3. KMS key policy/permissions cho phép principal Account B giải mã.
4. Secret phải dùng customer managed KMS key; AWS managed key `aws/secretsmanager` không dùng được cho cross-account access.
5. SCP/RCP, permissions boundary và explicit deny không chặn request.

Ví dụ resource policy rút gọn:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOrdersRuntimeRead",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::444455556666:role/orders-runtime"
      },
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "*"
    }
  ]
}
~~~

Resource policy gắn vào một secret nên Resource `*` trong statement này vẫn được giới hạn theo resource mà policy đang đính kèm. Trong identity policy của caller, chỉ định secret ARN đầy đủ.

Không cấp `secretsmanager:PutResourcePolicy` cho application role. Quyền thay đổi resource policy có thể cho phép mở rộng quyền truy cập secret.

### 18.1. BlockPublicPolicy và Access Analyzer

Khi gọi `PutResourcePolicy`, bật `BlockPublicPolicy` để Secrets Manager kiểm tra policy không cấp quyền rộng/public. Có thể dùng IAM Access Analyzer để review cross-account access.

Đừng chỉ kiểm tra resource policy. Identity policies và KMS key policies liên quan cũng có thể tạo đường truy cập ngoài ý muốn.

## 19. Replication secret qua nhiều Regions

Multi-Region replication tạo replica secret ở các Region khác để workload vùng khác có thể đọc local endpoint, giảm latency và hỗ trợ DR.

    Primary secret
    ap-southeast-1
          |
          | Replication
          +-------------------+
          |                   |
          v                   v
    Replica secret       Replica secret
    ap-southeast-2       ap-northeast-1

Khi primary secret value thay đổi, Secrets Manager truyền version mới tới các replica. Replication là asynchronous và eventually consistent; không giả định replica đã nhận value mới ngay sau khi rotation kết thúc.

### 19.1. KMS key tại replica Region

Mỗi replica được mã hóa bằng KMS key tại Region đích. Có thể chọn AWS managed key hoặc customer managed key theo yêu cầu. Nếu dùng customer managed key, cấu hình quyền cần thiết cho replication và decryption.

### 19.2. Rotation và replication

Nếu bật rotation cho primary, Secrets Manager rotate ở primary Region rồi truyền secret value mới tới các replica. Không cần bật rotation độc lập trên từng replica của cùng một multi-Region secret.

Ứng dụng ở mỗi Region nên dùng secret ARN của replica local để giảm cross-Region dependency. Kiểm tra replication status và thiết kế fallback nếu replica chưa `InSync`.

### 19.3. Replication status

| Status | Ý nghĩa |
|---|---|
| `Pending` | Quan hệ replica đã được tạo nhưng chưa bắt đầu copy |
| `InProgress` | Đang sao chép dữ liệu |
| `InSync` | Replica đang có cùng secret value với primary |
| `Failed` | Sao chép thất bại |
| `Detached` | Quan hệ replication đã bị dừng |

Khi `Failed`, kiểm tra status message, KMS permissions, Region đã enable, secret name collision và CloudTrail events.

## 20. Cross-account replication khác cross-account access

Hai cơ chế này giải quyết mục tiêu khác nhau:

| Cơ chế | Mục đích |
|---|---|
| Cross-account access | Application ở account khác gọi GetSecretValue trên secret gốc |
| Cross-account replication | Tạo một replica secret độc lập trong account khác và đồng bộ value |

Cross-account access cần resource policy, identity policy và KMS authorization trên secret gốc. Cross-account replication cần quy trình phối hợp giữa hai account và customer managed KMS key cho replica.

Cross-account replica có lifecycle, resource policy, tags và KMS key riêng. Replication là asynchronous. Không giả định replica account có toàn quyền giống primary account.

## 21. Audit bằng AWS CloudTrail

Secrets Manager tạo CloudTrail events cho các API operations như:

- `GetSecretValue`
- `CreateSecret`
- `PutSecretValue`
- `UpdateSecret`
- `RotateSecret`
- `PutResourcePolicy`
- `ReplicateSecretToRegions`
- `DeleteSecret`
- `RestoreSecret`

CloudTrail giúp trả lời principal nào gọi API, thời điểm, Region và secret resource liên quan. Secret value không nên được ghi vào log của ứng dụng hoặc rotation function.

### 21.1. Không log secret value

Không làm các việc sau:

- `System.out.println(secretJson)`.
- Log toàn bộ `GetSecretValueResponse`.
- Log password khi parse JSON.
- Log rotation event kèm `AWSPENDING` value.
- Ghi secret vào exception message.
- Đưa secret vào metric dimensions, tracing attributes hoặc CI output.

Có thể log secret ARN/name đã được chuẩn hóa, version ID, stage, operation result và correlation ID nếu chính sách cho phép. Metadata cũng có thể nhạy cảm, nên vẫn cần review.

### 21.2. Phát hiện truy cập bất thường

Có thể dùng CloudTrail Lake/EventBridge/SIEM để phát hiện role không thường dùng gọi GetSecretValue, secret bị truy cập từ Region/account lạ, tần suất API tăng đột biến, resource policy thay đổi, secret bị lên lịch deletion, rotation fail liên tục hoặc cross-Region replication chuyển sang Failed.

Đừng gửi secret value vào alert payload. Alert chỉ cần ARN, principal, operation và timestamp.

## 22. Cập nhật, restore và xóa secret

### 22.1. Restore secret

Khi secret được lên lịch xóa, nó không thể được đọc cho tới khi restore. Dùng `RestoreSecret` trước khi ứng dụng lấy lại secret value.

### 22.2. Deletion recovery window

Secrets Manager không xóa secret ngay lập tức theo mặc định. Recovery window:

- Tối thiểu 7 ngày.
- Mặc định 30 ngày.
- Tối đa 30 ngày.

Trong recovery window, secret không truy xuất được nhưng có thể restore. Sau khi hết thời gian, service xóa vĩnh viễn ở background.

### 22.3. Force delete

`ForceDeleteWithoutRecovery` bỏ qua recovery window và không thể khôi phục. Chỉ dùng trong tình huống đã có phê duyệt và xác nhận không còn consumer/replica phụ thuộc.

Primary secret đang replicate không thể bị xóa trước khi xử lý replica. Với cross-account replication, cần dừng/disassociate replication theo API tương ứng.

### 22.4. Xóa version

Không xóa trực tiếp một secret version. Gỡ toàn bộ staging labels bằng `UpdateSecretVersionStage` để đánh dấu version deprecated; Secrets Manager có thể dọn version đó theo quy tắc lifecycle.

## 23. Chi phí và quota

Chi phí Secrets Manager phụ thuộc số secret được lưu, API calls, replica secrets và các tài nguyên bổ sung như KMS customer managed keys, Lambda rotation và network endpoints.

Các cách tối ưu:

- Dùng cache để giảm `GetSecretValue` calls.
- Không tạo secret riêng cho từng request/user nếu không cần.
- Dùng naming/ownership để dọn secret không còn dùng.
- Đặt rotation schedule phù hợp risk.
- Chỉ replicate tới Regions thực sự có workload/DR requirement.
- Chọn KMS key theo nhu cầu quản trị, không mặc định tạo CMK cho mọi secret.
- Theo dõi API call volume và secret count.
- Dùng recovery window khi xóa để tránh outage do xóa nhầm.

Về version quota, AWS khuyến nghị tránh gọi `PutSecretValue` hoặc `UpdateSecret` liên tục hơn một lần mỗi 10 phút. Secrets Manager giữ 100 version gần nhất và không xóa version mới hơn 24 giờ. Đây là lý do không dùng secret để lưu trạng thái cập nhật liên tục.

Xem AWS Secrets Manager pricing theo Region để tính chi phí thực tế; không dùng số liệu giá cố định trong tài liệu vận hành dài hạn.

## 24. So sánh Secrets Manager với Parameter Store

| Tiêu chí | Secrets Manager | Parameter Store |
|---|---|---|
| Mục tiêu chính | Secret lifecycle và credential management | Configuration và parameter hierarchy |
| Rotation tích hợp | Có, gồm Lambda/managed rotation theo loại | Không có workflow rotation secret tương đương |
| Version/staging labels | Có | Có parameter versions nhưng semantics khác |
| Cache client | Có Java/Python/.NET/Go/Rust components | Có AWS Parameters and Secrets Lambda Extension/Powertools integration |
| Cross-Region replication | Có secret replication | Có khả năng chia sẻ/replication tùy tier và cấu hình |
| Giá | Secret/API/replication theo pricing | Standard/Advanced parameter pricing |
| Phù hợp | Database password, API key, token | App config, feature values, SecureString |

Chọn dịch vụ theo vòng đời và cách sử dụng dữ liệu. Không chuyển mọi config vào Secrets Manager chỉ vì dữ liệu có thể được mã hóa; điều đó làm tăng chi phí và phức tạp vận hành.

## 25. Troubleshooting thường gặp

### 25.1. AccessDenied khi GetSecretValue

Kiểm tra application role có `secretsmanager:GetSecretValue` trên đúng ARN không, secret resource policy có explicit deny không, SCP/RCP hoặc permissions boundary có chặn không, secret dùng customer managed KMS key hay không, KMS key policy có cho phép principal decrypt không và Region/secret ARN có đúng không.

Không giải quyết bằng `secretsmanager:*` trên `*`.

### 25.2. KMS DecryptionFailure

Kiểm tra KMS key enabled, key policy, IAM permissions, grants, encryption context và ViaService condition. Nếu key đã bị disable/deleted, các version được mã hóa bằng key đó có thể không giải mã được.

### 25.3. Rotation timeout

Kiểm tra Lambda có network tới database không, Lambda có gọi được Secrets Manager endpoint không, timeout/concurrency có đủ không, security groups/NACL có cho phép database port không, CloudWatch Logs có chỉ ra bước createSecret/setSecret/testSecret/finishSecret bị lỗi không và AWSPENDING có bị bỏ lại từ lần rotation trước không.

### 25.4. Rotation thành công nhưng application login fail

Ứng dụng có thể dùng cache cũ hoặc connection pool giữ connection cũ. Kiểm tra TTL, secret stage, pool refresh và thời gian propagation. Đảm bảo ứng dụng không hard-code VersionId.

### 25.5. Lambda không gọi được Secrets Manager trong VPC

Nếu Lambda ở private subnet không có Internet egress, tạo Secrets Manager interface endpoint hoặc cấu hình NAT/egress phù hợp. Kiểm tra private DNS và endpoint security group inbound TCP 443.

### 25.6. Secret replica không InSync

Kiểm tra Region đã enable, KMS key permissions ở primary/replica, name collision, replication status message và CloudTrail. Replication là asynchronous nên cho phép thời gian đồng bộ; không giả định update tức thời.

### 25.7. Too many versions

Kiểm tra automation có gọi PutSecretValue quá thường xuyên hay không. Dùng idempotency token cho retry và chỉ tạo version khi giá trị thực sự thay đổi.

### 25.8. Secret scheduled for deletion

Ứng dụng không thể đọc secret đang ở trạng thái deletion pending. Nếu xóa nhầm và vẫn trong recovery window, gọi `RestoreSecret`; sau đó xác minh version stage và application access.

## 26. Runbook: đưa database password vào Secrets Manager

1. Tạo secret JSON chứa host, port, dbname, username và password.
2. Chọn KMS key phù hợp.
3. Gắn tag owner/environment/data classification.
4. Tạo IAM role cho ứng dụng chỉ có GetSecretValue trên secret ARN.
5. Cấu hình Spring Boot dùng SDK v2 và Region chính xác.
6. Dùng Java cache với TTL theo rotation policy.
7. Parse JSON và validate schema.
8. Tạo datasource/connection pool bằng credential vừa đọc.
9. Kiểm tra kết nối read-only tới database.
10. Bật rotation nếu database/strategy hỗ trợ.
11. Kiểm tra Lambda/managed rotation network và IAM.
12. Thử rotation trong staging.
13. Xác minh application refresh pool và tiếp tục phục vụ request.
14. Bật CloudTrail monitoring và session/application logging an toàn.
15. Gỡ credential cũ khỏi source code, CI variables, image và config file sau khi xác nhận không còn consumer.

Không xóa credential cũ khỏi database hoặc secret store cũ trước khi rollout mới được xác minh. Thực hiện migration theo batch và có rollback plan.

## 27. Tình huống thực tế

### Tình huống A — Password nằm trong application.properties

Ứng dụng Spring Boot có `spring.datasource.password` hard-coded trong Git.

**Cách xử lý:** chuyển value vào Secrets Manager, cấp task/instance role chỉ đọc secret, lấy runtime bằng SDK và xóa credential khỏi repository theo quy trình xử lý secret đã lộ. Nếu credential từng được commit, rotate nó; xóa khỏi Git history không làm credential cũ an toàn trở lại.

### Tình huống B — Rotation đã hoàn thành nhưng ứng dụng vẫn dùng password cũ

Secrets Manager đã chuyển `AWSCURRENT`, nhưng HikariCP vẫn giữ connection pool cũ.

**Cách xử lý:** giảm TTL phù hợp, refresh secret và tạo pool mới, health-check pool mới rồi drain pool cũ. Không chỉ restart toàn bộ fleet nếu có thể rollout có kiểm soát.

### Tình huống C — Ứng dụng bị throttling khi đọc secret

Mỗi request HTTP đều gọi GetSecretValue.

**Cách xử lý:** reuse SDK client, thêm in-process cache, chọn TTL phù hợp, dùng jitter và monitor API call volume.

### Tình huống D — AccessDenied dù IAM role đã có GetSecretValue

Secret dùng customer managed KMS key nhưng key policy không cho phép decrypt.

**Cách xử lý:** kiểm tra cả identity policy và KMS key policy; cấp `kms:Decrypt` tối thiểu với ViaService/encryption context phù hợp.

### Tình huống E — Rotation Lambda timeout

Database ở private subnet; Lambda không có route tới DB hoặc Secrets Manager.

**Cách xử lý:** sửa security groups, route và Secrets Manager VPC endpoint/NAT. Kiểm tra cả hai kết nối, không chỉ Lambda execution role.

### Tình huống F — Cross-account role không đọc được secret

Account B có identity policy nhưng resource policy ở Account A chưa cho phép role đó; secret còn dùng AWS managed key.

**Cách xử lý:** thêm resource policy giới hạn principal, đổi sang customer managed KMS key và cấu hình key policy/identity permission.

### Tình huống G — Replica Region chưa nhận credential mới

Primary đã rotate nhưng replica vẫn có version cũ.

**Cách xử lý:** kiểm tra replication status; chờ eventual consistency hoặc xử lý Failed status/KMS permission. Ứng dụng nên dùng local replica và có chiến lược xử lý credential version trong thời gian đồng bộ.

### Tình huống H — Secret bị lên lịch xóa

Một automation xóa nhầm secret production với recovery window 7 ngày.

**Cách xử lý:** restore secret trước khi ứng dụng cần truy cập, kiểm tra IAM/version/rotation và điều tra CloudTrail event. Không dùng force-delete trong production cleanup thông thường.

### Tình huống I — CloudWatch log chứa password

Rotation Lambda ghi toàn bộ secret JSON để debug.

**Cách xử lý:** xóa logging payload khỏi function, xử lý log theo data incident policy, rotate credential nếu có khả năng bị lộ và thêm kiểm tra code review để chặn log secret.

### Tình huống J — Secret version quota tăng nhanh

CI pipeline gọi PutSecretValue mỗi lần build dù value không đổi.

**Cách xử lý:** chuyển build pipeline sang đọc secret runtime, chỉ ghi version khi credential thay đổi và tránh update liên tục hơn một lần mỗi 10 phút.

## 28. Bài tập tình huống

### Bài A — Chọn dịch vụ

Ứng dụng cần lưu database password và tự động đổi password mỗi tuần.

**Đáp án:** Secrets Manager với rotation phù hợp; Parameter Store không có workflow rotation tương đương.

### Bài B — IAM role tối thiểu

Spring Boot chỉ cần đọc một secret.

**Đáp án:** cấp `secretsmanager:GetSecretValue` trên secret ARN; thêm `kms:Decrypt` nếu customer managed key yêu cầu. Không cấp quyền quản trị secret.

### Bài C — KMS key

Secret chỉ dùng trong một account, không cần key policy riêng.

**Đáp án:** `aws/secretsmanager` thường là lựa chọn phù hợp; customer managed key khi cần cross-account hoặc kiểm soát key policy.

### Bài D — Version stage

Rotation đang chạy, version mới có `AWSPENDING`.

**Đáp án:** không dùng pending trong production trước khi test; ứng dụng tiếp tục dùng `AWSCURRENT` cho tới khi finishSecret chuyển label.

### Bài E — Cache stale

Java cache TTL một giờ, rotation mỗi 15 phút.

**Đáp án:** giảm TTL hoặc có refresh mechanism để phù hợp rotation; đánh giá API cost và connection pool refresh.

### Bài F — Rotation Lambda

Rotation thất bại ở setSecret.

**Đáp án:** kiểm tra quyền và network tới database, current credential validity, resource match và log của rotation function.

### Bài G — High availability

Database password rotation gây gián đoạn ngắn khi single user đổi password.

**Đáp án:** cân nhắc alternating users nếu database/service hỗ trợ và có admin secret để clone user.

### Bài H — Private subnet

Ứng dụng private không có NAT cần gọi Secrets Manager.

**Đáp án:** tạo interface VPC endpoint `com.amazonaws.<region>.secretsmanager`, private DNS và endpoint SG inbound 443.

### Bài I — Cross-account access

Role Account B đọc secret Account A.

**Đáp án:** cần identity policy và resource policy, đồng thời customer managed KMS key và key policy/permissions cho cross-account.

### Bài J — Multi-Region DR

Ứng dụng chạy ở hai Regions cần cùng secret.

**Đáp án:** replicate primary secret sang Region thứ hai, dùng replica local, theo dõi status và tính eventual consistency.

### Bài K — Xóa secret

Một secret không còn dùng và cần xóa an toàn.

**Đáp án:** dùng recovery window 7–30 ngày, mặc định 30 ngày; restore nếu xóa nhầm. Force delete không thể khôi phục.

### Bài L — Version quota

Automation tạo version mỗi phút.

**Đáp án:** ngừng cập nhật liên tục; chỉ ghi khi value thay đổi và dùng idempotency token. AWS khuyến nghị không duy trì PutSecretValue/UpdateSecret thường xuyên hơn một lần mỗi 10 phút.

## 29. Câu hỏi ôn tập

1. Secret khác configuration thông thường ở điểm nào?
2. Khi nào nên dùng Secrets Manager thay Parameter Store?
3. SecretString và SecretBinary khác nhau thế nào?
4. Secret metadata nào không được mã hóa như secret value?
5. VersionId và staging label khác nhau ra sao?
6. AWSCURRENT có ý nghĩa gì?
7. AWSPREVIOUS được dùng khi nào?
8. AWSPENDING được dùng trong bước nào?
9. Vì sao ứng dụng nên đọc AWSCURRENT?
10. Secrets Manager giữ bao nhiêu version gần nhất?
11. Vì sao không nên gọi PutSecretValue liên tục?
12. IAM action nào cần để runtime lấy secret?
13. Khi nào cần thêm kms:Decrypt?
14. Envelope encryption hoạt động ra sao?
15. AWS managed key khác customer managed key thế nào?
16. kms:ViaService giúp giới hạn gì?
17. Java SDK v2 dùng client nào để lấy secret?
18. Vì sao nên reuse SecretsManagerClient?
19. Java cache mặc định refresh khoảng bao lâu?
20. Cache TTL ảnh hưởng freshness và cost thế nào?
21. Vì sao cache có thể trả secret cũ?
22. Rotation Lambda có bốn bước nào?
23. setSecret cần kiểm tra gì để tránh confused deputy?
24. Single-user và alternating-users rotation khác nhau thế nào?
25. Vì sao ứng dụng cần refresh connection pool sau rotation?
26. Rotation schedule dùng timezone nào?
27. VPC endpoint Secrets Manager có service name dạng gì?
28. Cross-account access cần những policy nào?
29. Vì sao cross-account secret cần customer managed KMS key?
30. Multi-Region replication có đồng bộ tức thời không?
31. InSync biểu thị điều gì?
32. CloudTrail ghi nhận hoạt động nào?
33. CloudTrail có nên chứa secret value không?
34. Recovery window mặc định khi xóa secret là bao nhiêu ngày?
35. ForceDeleteWithoutRecovery có thể restore không?

**Đáp án nhanh:** (1) secret là dữ liệu xác thực/nhạy cảm; (2) khi cần lifecycle/rotation secret; (3) text và binary; (4) name, description, tags, rotation settings và key ARN; (5) ID định danh version, label mô tả vai trò; (6) version hiện hành; (7) last known previous version; (8) version mới đang rotation; (9) tự theo version mới; (10) 100 gần nhất; (11) tạo quá nhiều versions và chạm quota; (12) GetSecretValue; (13) khi dùng customer managed key và policy yêu cầu; (14) KMS bảo vệ data key, data key mã hóa secret; (15) AWS quản lý so với khách hàng quản lý policy/key; (16) chỉ dùng KMS qua Secrets Manager service; (17) SecretsManagerClient; (18) giảm overhead và reuse connection; (19) khoảng một giờ; (20) TTL ngắn tăng freshness/API calls; (21) refresh lỗi hoặc TTL chưa hết; (22) createSecret, setSecret, testSecret, finishSecret; (23) current/pending cùng resource và destination đúng; (24) một user so với hai user luân phiên; (25) pool có thể giữ connection/credential cũ; (26) UTC; (27) com.amazonaws.<region>.secretsmanager; (28) identity policy, resource policy và KMS key policy/permission; (29) AWS managed key không hỗ trợ cross-account; (30) không, eventual consistency; (31) replica đang đồng bộ với primary; (32) API activity; (33) không; (34) 30 ngày; (35) không.

## 30. Checklist production

- [ ] Secret được đặt tên theo service/environment/purpose, không chứa dữ liệu nhạy cảm.
- [ ] Secret value có schema rõ ràng và được validate khi đọc.
- [ ] Không lưu credential trong source code, AMI, container image hoặc CI logs.
- [ ] Application dùng IAM role/temporary credentials.
- [ ] Runtime role chỉ có GetSecretValue trên secret cần thiết.
- [ ] KMS key policy và kms:Decrypt được giới hạn đúng.
- [ ] Secret dùng AWSCURRENT, không hard-code VersionId.
- [ ] Không gọi PutSecretValue liên tục khi value không đổi.
- [ ] Java SDK client được reuse theo application lifecycle.
- [ ] Java cache TTL phù hợp rotation interval và freshness requirement.
- [ ] Cache/heap dump/debug endpoint được bảo vệ.
- [ ] Database connection pool có quy trình refresh sau rotation.
- [ ] Rotation Lambda idempotent và kiểm tra current/pending cùng resource.
- [ ] Rotation function có network tới cả database và Secrets Manager.
- [ ] Rotation schedule dùng UTC và có owner/on-call.
- [ ] Single-user/alternating-users strategy được chọn theo availability.
- [ ] Không log secret value, password hoặc token.
- [ ] CloudTrail monitoring được cấu hình cho secret API activity.
- [ ] Resource policy dùng BlockPublicPolicy và được review.
- [ ] Cross-account access có identity/resource/KMS policies phù hợp.
- [ ] Cross-Region replica có KMS key và replication status monitoring.
- [ ] VPC endpoint/private DNS/security group được kiểm tra.
- [ ] Secret deletion dùng recovery window; force delete cần phê duyệt.
- [ ] Version count, API calls, rotation failures và cost được theo dõi.
- [ ] Có runbook cho AccessDenied, KMS failure, rotation timeout và stale cache.

## 31. Tổng kết

AWS Secrets Manager giúp quản lý secret tập trung, mã hóa bằng KMS, theo dõi version và hỗ trợ rotation cho ứng dụng:

- Secret value có thể là text/JSON hoặc binary; metadata như name, description và tags không được mã hóa như value.
- Version labels AWSCURRENT, AWSPREVIOUS và AWSPENDING điều khiển lifecycle; ứng dụng nên đọc current stage.
- KMS dùng envelope encryption; AWS managed key phù hợp đa số trường hợp, customer managed key cần thiết cho cross-account hoặc key policy riêng.
- Runtime application dùng IAM role với GetSecretValue; tránh static access keys và quyền quản trị secret.
- AWS SDK for Java 2.x tích hợp với SecretsManagerClient; Java caching client giảm latency/API calls nhưng TTL phải khớp rotation.
- Lambda rotation gồm createSecret, setSecret, testSecret và finishSecret; custom function phải idempotent và kiểm tra đúng resource.
- Single-user đơn giản; alternating users có thể tăng availability nếu service hỗ trợ.
- VPC interface endpoint cho phép truy cập Secrets Manager qua PrivateLink trong private subnet.
- Cross-account access cần identity policy, resource policy và KMS authorization; multi-Region replication là asynchronous.
- CloudTrail hỗ trợ audit API activity nhưng application/rotation logs tuyệt đối không ghi secret value.
- Recovery window giúp khôi phục secret xóa nhầm; force delete không thể undo.
- Cache, IAM, KMS, network, rotation, connection pool và audit phải được thiết kế cùng nhau.

Một secret an toàn không chỉ là giá trị đã mã hóa. Ứng dụng cần lấy đúng version bằng identity tối thiểu, giữ cache trong khoảng thời gian chấp nhận được, thay credential mà không làm gián đoạn kết nối và tránh để secret xuất hiện trong log hoặc artifact.

### Tài liệu AWS và Java chính thức

1. AWS Secrets Manager best practices: https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html
2. What's in a secret and secret versions: https://docs.aws.amazon.com/secretsmanager/latest/userguide/whats-in-a-secret.html
3. Get a secret using Java AWS SDK: https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets-java-sdk.html
4. Get a secret using Java with client-side caching: https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets_cache-java.html
5. AWS Secrets Manager Java caching client: https://github.com/aws/aws-secretsmanager-caching-java
6. AWS SDK for Java 2.x Secrets Manager examples: https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_secrets-manager_code_examples.html
7. Secret encryption and decryption: https://docs.aws.amazon.com/secretsmanager/latest/userguide/security-encryption.html
8. Authentication and access control: https://docs.aws.amazon.com/secretsmanager/latest/userguide/auth-and-access.html
9. Resource-based policies: https://docs.aws.amazon.com/secretsmanager/latest/userguide/auth-and-access_resource-policies.html
10. Lambda rotation functions: https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_lambda-functions.html
11. Managed rotation: https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_managed.html
12. Rotation schedules: https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_schedule.html
13. Rotation strategy: alternating users: https://docs.aws.amazon.com/secretsmanager/latest/userguide/tutorials_rotation-alternating.html
14. Troubleshoot rotation: https://docs.aws.amazon.com/secretsmanager/latest/userguide/troubleshoot_rotation.html
15. Using a Secrets Manager VPC endpoint: https://docs.aws.amazon.com/secretsmanager/latest/userguide/vpc-endpoint-overview.html
16. Replicate secrets across Regions: https://docs.aws.amazon.com/secretsmanager/latest/userguide/replicate-secrets.html
17. Cross-account access: https://docs.aws.amazon.com/secretsmanager/latest/userguide/auth-and-access_examples_cross.html
18. Cross-account replication: https://docs.aws.amazon.com/secretsmanager/latest/userguide/cross-account-replicate-secrets.html
19. Monitor replication status: https://docs.aws.amazon.com/secretsmanager/latest/userguide/cross-account-replicate-status.html
20. Delete and restore a secret: https://docs.aws.amazon.com/secretsmanager/latest/userguide/manage_delete-secret.html
21. Secrets Manager quotas: https://docs.aws.amazon.com/secretsmanager/latest/userguide/reference_limits.html
22. AWS Secrets Manager pricing: https://aws.amazon.com/secrets-manager/pricing/
