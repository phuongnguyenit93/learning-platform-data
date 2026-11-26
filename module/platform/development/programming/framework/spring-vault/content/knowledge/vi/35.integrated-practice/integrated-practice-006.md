# Tích hợp một phương thức xác thực cloud phù hợp môi trường giả lập

## 1. Bài toán và mục tiêu

Một ứng dụng Java tên `orders-service` chạy trên hạ tầng cloud cần đọc một số cấu hình nhạy cảm từ HashiCorp Vault. Thay vì nhúng Vault root token hoặc token dài hạn vào biến môi trường, ứng dụng nên sử dụng **danh tính của workload** để đăng nhập, nhận Vault token ngắn hạn gắn policy, sau đó truy cập những secret được phép qua Spring Vault.

Trong chương **Thực hành tổng hợp** của module **SPRING_VAULT**, bài này kết nối kiến thức về `VaultTemplate`/`VaultOperations`, xác thực workload, ACL policy, KV v2, token/lease lifecycle, xử lý lỗi, quan sát và kiểm thử tích hợp. Bài mở rộng cũng chỉ ra cách giới hạn quyền Transit encryption và PKI cho cùng kiến trúc workload.

Ta chọn **AWS IAM authentication**, cụ thể biến thể `auth_type=iam`, vì HashiCorp Vault hỗ trợ xác thực một yêu cầu AWS Signature Version 4 đã ký tới STS `GetCallerIdentity`. Trong lab, có thể kết hợp **Vault test** với **LocalStack IAM/STS** để thử đường đi của thông điệp mà không cần cấp quyền truy cập tài khoản AWS production.

**Lưu ý về độ tin cậy:** LocalStack là trình giả lập AWS, không đương nhiên xác minh chữ ký SigV4, quyền IAM, identity canonicalization và tất cả hành vi STS giống AWS thật. Các tính năng có thể thay đổi theo phiên bản LocalStack/gói dịch vụ. Kết quả lab chỉ xác minh những gì thực sự đã quan sát; trước production phải kiểm tra lại AWS STS thật trong tài khoản staging được ủy quyền.

### 1.1. Sau bài học, bạn có thể

- Giải thích sự khác nhau giữa AWS credential để ký STS request, ARN của IAM principal, Vault token và dữ liệu secret.
- Tạo một IAM identity thử nghiệm, dùng `GetCallerIdentity` để xác nhận ARN chính xác.
- Cấu hình AWS IAM auth role phía Vault với `sts_endpoint`, `sts_region`, server ID và policy giới hạn KV v2.
- Dùng `AwsIamAuthentication` trong Spring Vault 4.1+ với AWS SDK v2 credentials provider và `VaultTemplate`.
- Thử đăng nhập thành công, từ chối khi sai identity hoặc ACL, và mô phỏng lỗi mạng/STS.
- Thiết kế token lifecycle, cleanup, quan sát lỗi và tiêu chí phân biệt lab emulator với AWS production.

## 2. Lựa chọn AWS IAM so với phương thức cloud khác

| Phương thức | Bằng chứng danh tính | Khả năng giả lập | Điều cần thận trọng |
| --- | --- | --- | --- |
| **AWS IAM** | SigV4-signed `STS GetCallerIdentity`, Vault so principal ARN với role. | Có thể kết hợp Vault và STS/IAM emulator. | Emulator có thể bỏ qua xác minh chữ ký hoặc trả root ARN mặc định. |
| AWS EC2 | Instance identity document và chữ ký/instance metadata. | Khó giả lập nguyên vẹn trust chain và metadata. | Mock identity document không chứng minh EC2 auth thật. |
| Azure Managed Identity | Identity token từ metadata service và Azure identity. | Có thể mock endpoint để unit test. | Mock không chứng minh token thực sự được Azure phát hành. |
| GCP Compute/IAM | GCP JWT/service account và kiểm tra chữ ký. | Có mock/emulator hạn chế. | Phải kiểm issuer, audience và IAM binding trên GCP thật. |
| Kubernetes auth | ServiceAccount JWT + TokenReview và Vault role. | Dễ lab với KinD/k3d. | Không phải IAM auth của một cloud provider dù chạy trên EKS/GKE. |
| JWT/OIDC | JWT đã ký, issuer, audience và bound claims. | Có thể dùng identity provider test. | Là cơ chế chung, không tự chứng minh cloud IAM. |

Trong bối cảnh AWS workload, IAM auth phù hợp vì role của EC2/ECS/Lambda có thể cung cấp AWS temporary credentials qua credential provider; ứng dụng không cần lưu một Vault token cố định. Trong lab, ta dùng IAM user/credentials giả chỉ để làm rõ giao thức, **không đề xuất IAM access key tĩnh cho production**.

## 3. Luồng giao tiếp và các ranh giới tin cậy

~~~mermaid
sequenceDiagram
    autonumber
    participant Java as Spring Vault / Java
    participant Vault as Vault AWS auth
    participant STS as AWS STS / LocalStack
    participant KV as Vault KV v2
    Java->>Java: AWS credentials provider + SigV4 signer
    Java->>Vault: POST auth/aws-ci/login với signed STS request
    Vault->>STS: Chuyển tiếp GetCallerIdentity đã ký
    STS-->>Vault: Account, Arn, UserId
    Vault->>Vault: Kiểm ARN và role/policy
    Vault-->>Java: Vault token ngắn hạn
    Java->>KV: GET kv-ci/data/orders/config + Vault token
    KV-->>Java: Secret hoặc permission denied
~~~

Vault IAM auth không tin chuỗi ARN do client tự khai báo. Client ký yêu cầu POST tới STS; Vault kiểm tra yêu cầu bằng cách gửi nó tới STS, lấy IAM principal từ kết quả xác minh, rồi đối chiếu principal với `bound_iam_principal_arn` trong Vault role. Vì vậy **Vault server phải truy cập được STS endpoint**; Java client cần có AWS credentials để ký và truy cập Vault.

| Thông tin | Do ai cấp? | Dùng vào việc gì? |
| --- | --- | --- |
| AWS AccessKeyId, SecretAccessKey, tùy trường hợp SessionToken | IAM/STS hoặc emulator trong lab. | Ký `GetCallerIdentity` theo SigV4. |
| ARN và Account | STS phản hồi cho request đã ký. | Vault xác định IAM identity có khớp role. |
| Vault token | Vault AWS auth cấp khi login hợp lệ. | Gọi Vault KV/Transit/PKI theo policy. |
| `orders/config` trong KV | Được bootstrap bằng admin/fixture writer riêng. | Dữ liệu mà application đọc sau khi login. |

AWS credentials **không phải Vault token**, và token Vault cũng không phải API key của các dịch vụ AWS. Chỉ đăng nhập thành công chưa chứng minh có quyền đọc mọi secrets engine.

### 3.1. Signed Host và server ID

Request SigV4 bao gồm các thành phần như method, URL/Host, body, timestamp, region và signed headers. Với Vault IAM auth, header `X-Vault-AWS-IAM-Server-ID` có thể được yêu cầu ký cùng request để chống replay một thông điệp đăng nhập từ môi trường này sang môi trường khác. Phía Java và Vault phải đặt **cùng server ID**.

Nếu Java ký request tới `http://localhost:4566` nhưng Vault trong container cần gửi request tới `http://localstack:4566`, việc tự đổi URL/Host sau khi ký có thể làm SigV4 không hợp lệ. Thiết kế mạng cho hai phía dùng URI/Host nhất quán.

## 4. Điều kiện và sơ đồ triển khai lab

Bài giả định có **Vault dev/test**, **LocalStack IAM+STS** và một Java test app trong cùng mạng Docker riêng.

| Dịch vụ | Từ máy host | Từ container chung network |
| --- | --- | --- |
| Vault dev | `http://127.0.0.1:8200` | `http://vault:8200` |
| LocalStack | `http://127.0.0.1:4566` | `http://localstack:4566` |
| Java app | IDE hoặc test container. | `http://vault:8200` và `http://localstack:4566` khi chạy trong Docker. |

Yêu cầu: Docker/Compose, Vault CLI, AWS CLI, JDK 17+ khi dùng Spring Vault 4.1, và LocalStack version/gói có hỗ trợ IAM và STS. **Kiểm tra phiên bản/giới hạn LocalStack đang sử dụng trước khi chạy**; một số bản yêu cầu authentication token hoặc thay đổi cách bật dịch vụ. Để lặp lại lab, pin image tags đã kiểm chứng, không dùng `latest` mặc định.

Mẫu Compose định hướng (thay `<PIN>` bằng tag đã xác nhận và bổ sung credential LocalStack theo hướng dẫn phiên bản):

~~~yaml
services:
  vault:
    image: hashicorp/vault:<PIN>
    command: ["server", "-dev"]
    environment:
      VAULT_DEV_ROOT_TOKEN_ID: "dev-root-lab-only"
      VAULT_DEV_LISTEN_ADDRESS: "0.0.0.0:8200"
    ports:
      - "127.0.0.1:8200:8200"
    cap_add:
      - IPC_LOCK

  localstack:
    image: localstack/localstack:<PIN>
    environment:
      SERVICES: "iam,sts"
      AWS_DEFAULT_REGION: "us-east-1"
    ports:
      - "127.0.0.1:4566:4566"
~~~

Hai container Compose cùng một network mặc định, có thể resolve hostname `vault` và `localstack`. Nếu chạy app ngoài Docker, URI ký STS phải giữ được cùng Host để Vault server truy cập endpoint; phương án đơn giản nhất là chạy ứng dụng test trong cùng network.

**Giới hạn bảo mật:** Vault dev mode có root token test xác định trước, có thể dùng HTTP và không lưu state bền vững. Chỉ chạy trong mạng thử nghiệm cô lập, không mở cổng public, không dùng token/CA/secret production. Mọi lệnh bootstrap dưới root token chỉ được chạy bởi admin của lab, không truyền root token sang app.

## 5. Tạo IAM user trong LocalStack và kiểm tra identity

Từ máy host sau khi emulator hoạt động, dùng AWS CLI chỉ tới **LocalStack endpoint**:

~~~bash
# Credentials mặc định chỉ phục vụ bootstrap emulator.
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1

aws --endpoint-url http://127.0.0.1:4566 \
  iam create-user --user-name ci-orders

# Không in secret key được trả về vào terminal hoặc CI log.
umask 077
aws --endpoint-url http://127.0.0.1:4566 \
  iam create-access-key --user-name ci-orders \
  > /tmp/ci-orders-access.json
~~~

File JSON chứa `AccessKeyId` và `SecretAccessKey` **vừa tạo cho ci-orders**. Test harness phải inject cặp này vào Java container theo cơ chế secret injection hoặc environment riêng, không commit file, không in nội dung file. Nếu tiếp tục dùng key `test/test` mặc định, LocalStack có thể xem request thuộc **root identity** thay vì user vừa tạo.

Xác nhận STS bằng **đúng cặp key mới**:

~~~bash
# Chạy sau khi harness đã đưa access key của ci-orders vào môi trường CLI.
aws --endpoint-url http://127.0.0.1:4566 \
  sts get-caller-identity \
  --query '{Account:Account,Arn:Arn,UserId:UserId}' \
  --output json
~~~

Một phản hồi minh họa:

~~~json
{
  "Account": "000000000000",
  "Arn": "arn:aws:iam::000000000000:user/ci-orders",
  "UserId": "<identity-id-from-emulator>"
}
~~~

**Không tự điền ARN như một giả định.** Dùng ARN *thực tế* từ `GetCallerIdentity` để ràng buộc Vault role. Nếu phản hồi là `arn:aws:iam::000000000000:root`, credential source đang sai. Nếu phản hồi là STS assumed-role ARN, phải hiểu cách Vault chuẩn hóa về IAM role ARN trước khi bind; không thay tùy tiện cả ARN bằng wildcard.

Việc LocalStack trả ARN không chứng minh nó kiểm SigV4 như AWS thật. Test sai key/chữ ký ở cuối bài để nhận diện giới hạn emulator, rồi kiểm lại bảo mật bằng AWS STS thật trên staging.

## 6. Tạo Vault KV v2, fixture và policy tối thiểu

Dùng Vault CLI từ host trong môi trường test:

~~~bash
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=dev-root-lab-only

# Engine và dữ liệu giả chỉ dùng trong lab.
vault secrets enable -path=kv-ci -version=2 kv
vault kv put -mount=kv-ci orders/config \
  service=orders environment=local-lab feature_flag=enabled

# Tạo một fixture khác có tồn tại để kiểm tra bị từ chối.
vault kv put -mount=kv-ci finance/config \
  service=finance environment=local-lab
~~~

Policy chỉ cho phép app `orders` đọc một path:

~~~hcl
# ci-orders-kv.hcl
path "kv-ci/data/orders/config" {
  capabilities = ["read"]
}
~~~

Nạp policy:

~~~bash
vault policy write ci-orders-kv ci-orders-kv.hcl
~~~

KV version 2 cần `data/` trong ACL path. Tuy nhiên phía Java sẽ dùng `opsForKeyValue("kv-ci", KV_2).get("orders/config")`, nên không tự thêm `data/` vào argument của `get`.

Không cho app quyền `list` tất cả KV metadata, `create/update/delete` fixture, hoặc `sys/mounts` và `auth/*` chỉ để lab chạy. Danh tính setup là **bootstrap admin**; danh tính Java app là **workload**.

## 7. Cấu hình AWS IAM auth mount phía Vault

Bật auth mount riêng và hướng Vault đến emulator theo hostname trong mạng Docker:

~~~bash
vault auth enable -path=aws-ci aws

vault write auth/aws-ci/config/client \
  sts_endpoint="http://localstack:4566" \
  sts_region="us-east-1" \
  iam_endpoint="http://localstack:4566" \
  iam_server_id_header_value="vault-ci.internal"
~~~

| Tham số | Vai trò |
| --- | --- |
| `sts_endpoint` | STS mà **Vault server** gửi lại signed `GetCallerIdentity`. |
| `sts_region` | Region của STS custom endpoint; cần nhất quán với SigV4 signature. |
| `iam_endpoint` | Endpoint IAM giả lập nếu Vault cần query IAM metadata/Unique ID. |
| `iam_server_id_header_value` | Bắt buộc client ký header chống replay có giá trị `vault-ci.internal`. |

Tạo role cho đúng IAM user ARN đã xác minh ở bước 5:

~~~bash
vault write auth/aws-ci/role/ci-orders-role \
  auth_type=iam \
  bound_iam_principal_arn="arn:aws:iam::000000000000:user/ci-orders" \
  resolve_aws_unique_ids=false \
  token_policies="ci-orders-kv" \
  token_ttl="10m" \
  token_max_ttl="30m"
~~~

**Chỉ trong lab**, `resolve_aws_unique_ids=false` giúp giảm phụ thuộc vào IAM `GetUser/GetRole` mà emulator có thể chưa triển khai đầy đủ. Trong production, việc resolve AWS principal sang Unique ID (mặc định true cho nhiều trường hợp) giúp chống rủi ro **xóa rồi tạo lại cùng tên IAM user/role**; nên giữ chế độ này và cấu hình IAM permissions hợp lệ.

Không đổi `bound_iam_principal_arn` thành `arn:aws:iam::000000000000:*` nếu login fail. Wildcard này cho nhiều identity cùng đăng nhập, khiến negative test mất ý nghĩa. Cũng không tắt server ID chỉ để qua lỗi mismatch; kiểm Signed Host, region, header và endpoint trước.

### 7.1. Kiểm tra ranh giới role và policy

Sau login thành công, Vault phát token ngắn hạn có policies theo role; role xác thực **ai** là AWS principal, còn Vault policy xác định **token làm được gì**. Token của app chỉ được đọc `kv-ci/data/orders/config`, không được đọc `finance/config`, tạo token quản trị, sửa auth role hoặc bật secrets engine.

Chạy một lệnh `vault token capabilities` bằng **token workload** mới thể hiện quyền ứng dụng; chạy bằng root token bootstrap chỉ cho biết quyền của root.

## 8. Tích hợp Spring Vault 4.1+ với AWS SDK v2

Ví dụ bên dưới sử dụng `VaultClient` và `AwsIamAuthentication` trong Spring Vault 4.1+, với kiểu `AwsCredentialsProvider` thuộc AWS SDK Java v2. Spring Vault 3.x có những khác biệt về constructor và một số ví dụ dùng AWS SDK v1; không trộn `com.amazonaws.auth.BasicAWSCredentials` với `software.amazon.awssdk.auth.credentials.AwsBasicCredentials`.

Dependency logic:

~~~text
org.springframework.vault:spring-vault-core
software.amazon.awssdk:auth
software.amazon.awssdk:regions
org.springframework:spring-context
org.springframework:spring-web
org.springframework.boot:spring-boot-starter-test  (nếu dùng Boot test)
~~~

Pin version Spring Vault/Spring Boot/Framework và AWS SDK theo BOM/tổ hợp được hỗ trợ. Từ Java container cần môi trường:

~~~text
LAB_VAULT_URL=http://vault:8200
LAB_STS_URL=http://localstack:4566
AWS_ACCESS_KEY_ID=<AccessKeyId của ci-orders>
AWS_SECRET_ACCESS_KEY=<SecretAccessKey của ci-orders>
AWS_REGION=us-east-1
~~~

Đây là **placeholder**, không phải credential để commit vào file cấu hình. Khi ứng dụng chạy trong container, cả `vault` và `localstack` phải resolve cùng network. Nếu chạy từ host, đổi URL có thể làm Host ký và đường mạng Vault gọi khác nhau; phải kiểm lại chữ ký, không chỉ thay `localhost` rồi thử may rủi.

### 8.1. JavaConfig với Cloud IAM workload authentication

~~~java
import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.AwsIamAuthentication;
import org.springframework.vault.authentication.AwsIamAuthenticationOptions;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

import software.amazon.awssdk.auth.credentials.EnvironmentVariableCredentialsProvider;
import software.amazon.awssdk.regions.Region;

@Configuration(proxyBeanMethods = false)
public class AwsIamVaultLabConfiguration {

    @Bean
    VaultClient vaultClient(
            @Value("${LAB_VAULT_URL}") URI vaultUrl) {
        return VaultClient.create(VaultEndpoint.from(vaultUrl));
    }

    @Bean
    ClientAuthentication awsIamAuthentication(
            VaultClient client,
            @Value("${LAB_STS_URL}") URI stsUrl) {

        AwsIamAuthenticationOptions options =
                AwsIamAuthenticationOptions.builder()
                        .path("aws-ci")
                        .role("ci-orders-role")
                        .region(Region.US_EAST_1)
                        .endpointUri(stsUrl)
                        .serverId("vault-ci.internal")
                        .credentialsProvider(
                                EnvironmentVariableCredentialsProvider.create())
                        .build();

        return new AwsIamAuthentication(options, client);
    }

    @Bean
    VaultOperations vaultOperations(
            VaultClient client, ClientAuthentication authentication) {
        return new VaultTemplate(client, authentication);
    }
}
~~~

`endpointUri` của Spring Vault quyết định URL STS **được ký bởi Java**; `sts_endpoint` của Vault quyết định đích STS **Vault dùng để xác minh**. Lab này chủ động đặt cả hai là `http://localstack:4566`. `serverId("vault-ci.internal")` khớp với `iam_server_id_header_value` trong cấu hình Vault.

`EnvironmentVariableCredentialsProvider` chỉ đọc credentials từ environment, phù hợp lab và không tìm đến metadata endpoint ngoài ý muốn. **Production nên dùng provider chain theo workload** (instance profile, ECS task role, Lambda role hoặc web identity) với temporary credentials được refresh tự động; không dùng IAM access key tĩnh dài hạn như cách lab.

`VaultTemplate` được tạo với `ClientAuthentication` sẽ dùng token có được sau AWS IAM login. Cần xác minh token/session lifecycle của version đang dùng; với ứng dụng lâu dài, dùng session manager hỗ trợ renewal/re-login hoặc auto-configuration phù hợp, không cache token vĩnh viễn.

### 8.2. Dùng VaultOperations đọc KV v2 sau login

~~~java
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public final class OrdersVaultSettings {

    private final VaultOperations vault;

    public OrdersVaultSettings(VaultOperations vault) {
        this.vault = vault;
    }

    public Map<String, Object> load() {
        VaultResponse response = vault.opsForKeyValue(
                "kv-ci", KeyValueBackend.KV_2).get("orders/config");

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Thiếu cấu hình KV của orders");
        }

        return Map.copyOf(response.getData());
    }
}
~~~

Phương thức này dùng **Vault token** theo policy đã được AWS IAM login cấp. Nó không gửi AWS access key để đọc KV. Đọc path logic `orders/config` ứng với API thật `GET /v1/kv-ci/data/orders/config`.

Nếu Spring Cloud Vault auto-config đồng thời tạo `VaultOperations` khác bằng token tĩnh, phải xác nhận bean/identity thực sự được inject; test dùng token root từ cấu hình cũ không chứng minh IAM auth đã hoạt động.
## 9. Integration test: chứng minh đúng IAM identity và Vault ACL

Một bài test hợp lệ phải kiểm được **hai ranh giới khác nhau**:

- **Authentication:** AWS credentials có tạo được signed `GetCallerIdentity` và Vault AWS auth có cấp token cho role phù hợp hay không?
- **Authorization:** Token đó có đọc được KV path được phép, đồng thời **không đọc được** một secret khác đã tồn tại hay không?

Không dùng root token, bootstrap token, hoặc mock `VaultOperations` để tuyên bố “IAM auth đã chạy thành công”. Mock có ích cho unit test, nhưng không chứng minh Vault gửi request tới STS hoặc thực thi ACL thật.

### 9.1. Test tích cực với fixture

Khi dùng Spring Boot Test cùng JavaConfig ở mục 8:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class AwsIamVaultIntegrationIT {

    @Autowired
    OrdersVaultSettings settings;

    @Test
    void loginAsIamUserAndReadAllowedKvSecret() {
        Map<String, Object> config = settings.load();

        assertNotNull(config);
        assertEquals("orders", config.get("service"));
        assertEquals("local-lab", config.get("environment"));
        assertEquals("enabled", config.get("feature_flag"));
    }
}
~~~

Test này chỉ PASS đáng tin khi harness đảm bảo:

1. `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` là cặp của `ci-orders`, không phải key bootstrap LocalStack.
2. `VaultOperations` được tạo từ `AwsIamAuthentication`, không từ `TokenAuthentication` với root token.
3. `kv-ci` chạy KV v2, fixture đã được admin tạo trước test.
4. LocalStack STS trả đúng ARN và Vault role bind vào ARN đó.
5. Response khớp dữ liệu giả mong đợi, không được phép đọc secret khác.

### 9.2. Test âm: không đọc được secret ngoài policy

Fixture `finance/config` đã tồn tại nhưng policy `ci-orders-kv` chỉ cho đọc `orders/config`. Một test đơn giản:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.vault.VaultException;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;

@SpringBootTest
class AwsIamVaultNegativeIT {

    @Autowired
    VaultOperations vault;

    @Test
    void iamWorkloadCannotReadFinanceSecret() {
        assertThrows(VaultException.class, () ->
                vault.opsForKeyValue("kv-ci", KeyValueBackend.KV_2)
                        .get("finance/config"));
    }
}
~~~

**Chưa đủ để nghiệm thu phân quyền nếu chỉ có `assertThrows`.** Lỗi timeout, mount không tồn tại hoặc server sealed cũng có thể làm test ném exception. Trong bài test thực, bổ sung assertion HTTP status/exception type **permission denied** theo phiên bản Spring Vault (thường 403) và xác nhận fixture `finance/config` tồn tại từ bootstrap. Nếu emulator/Vault bị lỗi mạng, negative test phải FAIL vì không chứng minh được ACL.

### 9.3. Test âm về principal, signature và server ID

| Trường hợp | Cách tạo lỗi trong Vault test | Kỳ vọng |
| --- | --- | --- |
| Principal sai | Cung cấp key khiến STS trả IAM principal khác `ci-orders`. | Vault từ chối role `ci-orders-role`. |
| Role binding sai | Bind role vào ARN không khớp principal thực. | Login thất bại; không “fallback” sang root. |
| Client server ID sai | Đổi `serverId` nhưng giữ `iam_server_id_header_value` cố định. | Header không hợp lệ → bị Vault từ chối. |
| Signed request bị sửa | Sửa Host/region/body sau khi ký hoặc dùng secret key sai. | Với AWS STS thật phải bị từ chối; kết quả LocalStack được ghi riêng vì emulator có thể thiếu kiểm tra. |
| STS unreachable | Chặn network giữa **Vault container** và LocalStack. | Vault không xác minh được caller; login thất bại có kiểm soát. |
| Vault unreachable | Chặn network giữa **Java** và Vault. | Không login được; retry/backoff giới hạn, không tự dùng root token. |
| Token Vault hết hạn | Rút ngắn TTL trong lab hoặc revoke token từ admin. | Không tiếp tục dùng token cũ; re-login theo policy khi kết nối cho phép. |
| Đọc path ngoài policy | `finance/config` đã tồn tại. | Token IAM được cấp đúng vẫn bị Vault ACL từ chối. |

Nếu LocalStack chấp nhận một signed request **đã bị chỉnh sửa**, kết luận phải là **EMULATOR_SECURITY_LIMITATION**, không phải tính năng anti-forgery của AWS đã được xác nhận. Các case cần chứng minh chữ ký thực tế phải chạy với AWS STS staging và quyền được phê duyệt.

### 9.4. Không đánh đồng lỗi identity với lỗi policy

Lỗi có thể xảy ra ở bốn giai đoạn:

~~~text
AWS credentials provider
   │  sai access key / region / expired temporary credentials
   ▼
SigV4 request + STS verification
   │  sai signed Host / signature / server ID / emulator limitation
   ▼
Vault AWS auth role binding
   │  principal ARN khác bound ARN, policy mapping sai
   ▼
Vault token + KV operations
      thiếu capability read trên kv-ci/data/orders/config
~~~

STS login thành công nhưng KV đọc 403 **thường là lỗi authorization phía Vault**, không phải bằng chứng IAM login thất bại. Ngược lại, tự sửa policy `ci-orders-kv` rộng hơn không giải quyết chữ ký SigV4 hoặc IAM principal bị sai.

## 10. Lưu ý token lifecycle và credential rotation

AWS credentials dùng để ký login request có vòng đời **khác** Vault token. Trong production, ứng dụng trên EC2/ECS/Lambda hoặc hạ tầng tương thích thường nhận temporary credentials và session token từ cloud credentials provider. Chúng phải được refresh đủ sớm trước lần AWS IAM login tiếp theo.

Vault token có `token_ttl`/`token_max_ttl` theo Vault auth role và còn chịu revocation/policy. Một token có TTL 10 phút có thể được renew hoặc phải re-login tùy token type/auth method và cấu hình. Spring Vault hỗ trợ session manager để quản lý lifecycle token; không nên chỉ gọi `authentication.login()` một lần rồi giữ chuỗi token bất biến suốt nhiều ngày.

Trong ví dụ Java:

- `EnvironmentVariableCredentialsProvider` chỉ phù hợp với **lab** dùng cặp IAM user test; nó không tự truy vấn metadata của AWS workload để có temporary credentials mới.
- Đối với production, chọn credential provider chain do AWS SDK hỗ trợ cho loại workload tương ứng, đảm bảo có thể lấy credentials mới khi instance role/STS session rotate.
- Nếu dùng `LifecycleAwareSessionManager`, cần cấu hình và quản lý bean scheduler/lifecycle đúng phiên bản Spring Vault hoặc dùng auto-configuration của Spring Cloud Vault khi phù hợp.
- Khi Vault unreachable, không coi token TTL được đóng băng. Nếu token hết hạn, ứng dụng phải fail closed đối với operation cần Vault.
- Nếu sử dụng KV tĩnh, việc renew token **không** tự cập nhật một secret đã được cache trong application.
- Nếu có dynamic DB secrets, cần quản lý **lease TTL của DB credential** độc lập với Vault token và chuyển connection pool sau rotation.
- Nếu ứng dụng dùng Transit encrypt/decrypt, các operation đó chạy ở Vault; không lấy Transit key về local để cố duy trì dịch vụ khi Vault mất kết nối.

### 10.1. Tách readiness khỏi liveness

Một ứng dụng vẫn “sống” trong lúc mất kết nối Vault, nhưng có thể không đủ quyền/credential để tiếp tục xử lý request nghiệp vụ. Liveness kiểm tiến trình; readiness kiểm liệu chức năng cần Vault đã có token/secret hợp lệ và consumer đã nhận đúng cấu hình hay chưa.

Không làm mọi pod restart liên tục chỉ vì lỗi STS tạm thời. Dùng backoff/jitter, timeout, cảnh báo và degraded readiness thay vì bão re-login. Không retry vô hạn request tạo dynamic credential, issue PKI hoặc thay Transit keys vì timeout có thể xảy ra sau khi server đã thực thi.

## 11. Mở rộng lab với Transit và PKI mà không nới policy mặc định

Sau khi xác minh AWS IAM login và KV read, bài thực hành có thể mở rộng quyền *theo suite test riêng*, không cộng mọi quyền vào role `ci-orders-role`.

| Bài mở rộng | Capability phù hợp | Cần kiểm chứng |
| --- | --- | --- |
| Transit encrypt-only | `update` trên `transit-ci/encrypt/orders-key`. | Có thể encrypt; không thể decrypt/export key. |
| Transit encrypt/decrypt | `update` trên `encrypt` và `decrypt` của key test. | Round trip với context/algorithm theo key type. |
| PKI issue | `update` trên `pki-ci/issue/orders-client`. | Chỉ issue role đúng và SAN/TTL được cho phép. |
| Database dynamic credentials | `read` trên `database-ci/creds/orders-readonly`. | Credential có lease, chỉ quyền DB cần thiết, cleanup/revoke. |

Policy Transit chỉ encrypt:

~~~hcl
path "transit-ci/encrypt/orders-key" {
  capabilities = ["update"]
}
~~~

Policy PKI issue theo một role riêng:

~~~hcl
path "pki-ci/issue/orders-client" {
  capabilities = ["update"]
}
~~~

Các mount, key, CA, role phải được admin tạo trong **Vault test**. App không có quyền quản trị issuer hoặc thay Transit key configuration. Đừng cấp quyền PKI hoặc Transit chỉ vì cloud IAM login đã thành công.

**Tách authentication khỏi authorization:** AWS role/STS xác minh người gọi, Vault role cấp token, còn policy mới quyết định thao tác. Một role có thể login thành công nhưng chỉ được đọc KV; đó chính là kết quả thiết kế quyền tối thiểu đúng.

## 12. LocalStack lab không tương đương AWS production

| Điều đánh giá | Vault + LocalStack | AWS STS thật + Vault staging |
| --- | --- | --- |
| Java tạo SigV4 request | Test được cách cấu hình credentials provider, STS URI, region. | Kiểm thực với AWS SDK và STS endpoint thật. |
| GetCallerIdentity | Emulator có thể trả ARN để Vault kiểm role. | STS xác nhận identity từ AWS credentials thật. |
| Chữ ký sai bị từ chối | **Không mặc định bảo đảm**; tùy emulator. | Phải bị từ chối theo AWS STS SigV4 contract. |
| Role ARN và Unique ID | Có thể dùng `resolve_aws_unique_ids=false` trong lab. | Ưu tiên true/identity bindings theo khuyến nghị Vault và IAM permissions. |
| Credential source | IAM user/key thử nghiệm trong emulator. | Instance profile, task role, Lambda role, web identity hoặc provider chain thích hợp. |
| Vault ACL và KV | Có thể kiểm path read/deny thật trên Vault test. | Phải kiểm lại bằng Vault staging token đúng workload. |
| Anti-replay server ID | Kiểm được cấu hình/header; thành công phụ thuộc emulator. | Cần kiểm signed header trên STS thật và Vault config chuẩn. |
| IAM role rotation | Emulator không bảo đảm mọi chính sách AWS. | Kiểm role/session lifecycle, trust policy, permission và audience. |
| Kết luận | **FUNCTIONAL_LAB_PASS**, hoặc FAIL/UNKNOWN. | Chỉ đánh dấu **CLOUD_AUTH_VERIFIED** sau kiểm thực tế. |

Trong quá trình chuyển production, không giữ `sts_endpoint=http://localstack:4566`, access key test hoặc `resolve_aws_unique_ids=false` chỉ vì lab đã PASS. Cấu hình thật cần TLS, DNS, AWS STS/IAM endpoint được tổ chức phê duyệt, role ARN chính xác, signed server ID phân biệt staging/prod và workload identity không chứa secret tĩnh dài hạn.

## 13. Giám sát và xử lý lỗi

| Triệu chứng | Khả năng | Hành động |
| --- | --- | --- |
| STS trả `root` thay vì `ci-orders` | Provider dùng key mặc định `test/test`. | Kiểm `GetCallerIdentity` với key ứng dụng, không bind Vault role vào root. |
| Vault không truy cập LocalStack | Config `sts_endpoint` là `localhost` nhìn từ Vault container hoặc Docker DNS lỗi. | Dùng tên dịch vụ `localstack` trên mạng đúng và kiểm region/URI. |
| App không truy cập Vault | `LAB_VAULT_URL` sai, container DNS/TLS/port lỗi. | Kiểm network, TLS, server health mà không log token. |
| Login thất bại do server ID | Header ký khác `iam_server_id_header_value`. | So client `serverId` và Vault config, không tắt kiểm tra. |
| Login 400/403 | IAM ARN khác role binding, body/header SigV4 sai, role/mount không tồn tại. | Kiểm STS principal, signed request method/path và Vault auth role. |
| Login OK, KV 403 | ACL thiếu `read` ở KV v2 `data/` path. | Kiểm policy thực tế và Vault token identity. |
| KV 404 | Fixture/mount không tồn tại hoặc nhầm KV v1/v2. | Kiểm `vault secrets list -detailed` và path. |
| Java compile fail | Spring Vault 3.x hoặc thiếu AWS SDK v2 dependency. | Kiểm dependency tree/Javadoc đúng version. |
| Token hết hạn | Session manager không renew/re-login hoặc AWS provider không còn credential hợp lệ. | Quan sát TTL, auth errors và rotation. |
| Test sai chữ ký vẫn PASS | Emulator không thực thi signature verification tương đương AWS. | Ghi limitation và test lại với STS thật. |
| Request chậm/429/5xx | Vault/STS emulator quá tải, network hoặc HA issue. | Backoff, rate limit, timeout, không retry vô hạn. |

Metric nên có login success/failure theo error class, thời gian STS/Vault, số lần re-login, tuổi token và KV read denial. Không dùng AWS secret key, Vault token, `iam_request_headers` chứa chữ ký, plaintext KV, key PKI hoặc wrapping token trong log/trace/metrics labels.

Không bật full HTTP wire logs khi debug IAM login: request headers/body có chữ ký và thông tin nhạy cảm; request có thể bị replay trong cửa sổ thời gian thích hợp nếu biện pháp phòng replay không hiệu quả.

## 14. Checklist thực hành end-to-end

~~~text
PREPARE
  [ ] Pin Vault/LocalStack/Spring Vault/AWS SDK/JDK versions
  [ ] Vault dev + LocalStack IAM/STS trong Docker network cô lập
  [ ] IAM user ci-orders và một AccessKeyId/SecretAccessKey test riêng
  [ ] AWS CLI GetCallerIdentity trả đúng ARN user, không phải root

PROVISION VAULT (chỉ admin lab)
  [ ] KV v2 kv-ci và fixtures orders/config, finance/config
  [ ] Policy ci-orders-kv chỉ read kv-ci/data/orders/config
  [ ] AWS auth tại aws-ci, cấu hình STS endpoint, region, server ID
  [ ] IAM role bind đúng ARN, Vault token TTL ngắn

RUN JAVA
  [ ] AwsIamAuthenticationOptions đúng role, path, region, STS URI
  [ ] serverId trùng giá trị Vault yêu cầu, signed Host nhất quán
  [ ] AWS SDK v2 provider lấy đúng IAM user test credentials
  [ ] VaultTemplate/Operations sử dụng IAM login, không dùng root token

ASSERT
  [ ] Positive read orders/config thành công
  [ ] Negative read finance/config trả permission denied
  [ ] Principal sai, role sai, server ID sai bị từ chối
  [ ] STS/network failure không làm fallback sang quyền cao
  [ ] Ghi rõ test chữ ký nào emulator không bảo đảm

CLEANUP
  [ ] Revoke Vault tokens/leases test và data/policies khi phù hợp
  [ ] Xóa IAM access key trước khi xóa IAM user emulator
  [ ] Hủy container/volume test, dọn file credential tạm
  [ ] Không còn secret trong logs/CI artifacts
~~~

### 14.1. Dọn tài nguyên

Nếu có một Vault dev container và LocalStack stack dành riêng cho mỗi CI job, hủy chúng sau test là cách cleanup đơn giản. Nếu dùng shared staging, chỉ dọn đúng role/policy/path/run-id của suite; không xóa mount đang được test khác sử dụng.

Khi xóa IAM user, hãy vô hiệu hóa/xóa access key trước. Xóa file JSON credential tạm ở host không thay thế việc revoke key tại IAM provider. Với KV v2, delete metadata có thể xóa toàn bộ versions – chỉ dùng trên fixture test thuộc run hiện tại.

Không để AWS credentials vào GitHub Actions/Jenkins output, Gradle/Maven build logs, test snapshots, exception hoặc container image.

## 15. Bài tập nâng cao và tiêu chí nghiệm thu

### 15.1. Nhiệm vụ bắt buộc

1. Dựng Vault dev và IAM/STS emulator trong mạng thử nghiệm đã pin version.
2. Tạo IAM user test, lấy access key mới và kiểm ARN bằng `GetCallerIdentity`.
3. Cấu hình Vault `aws-ci` với server ID và STS URI; bind role chỉ vào ARN của user test.
4. Ghi KV v2 fixture `orders/config` và `finance/config`, gắn policy chỉ đọc một key.
5. Tạo Spring Vault `AwsIamAuthentication` với `VaultClient`, ký STS request bằng AWS SDK v2 provider.
6. Chạy positive KV read, negative ACL read và một negative auth case.
7. Kiểm tra lỗi mạng/ST​S và giới hạn emulator; không mở rộng policy để ép test thành công.
8. Ghi báo cáo có dependency version, ARN, auth path, role, policy, pass/fail và bằng chứng cleanup.

### 15.2. Bài tập mở rộng

- Đổi IAM user lab sang STS assumed-role credentials nếu phiên bản LocalStack hỗ trợ; đối chiếu ARN assumed-role với IAM role ARN canonical.
- Tích hợp `LifecycleAwareSessionManager` và mô phỏng token hết TTL trong khi Vault unavailable; kiểm readiness/fail closed.
- Dùng policy Transit encrypt-only, xác nhận mã hóa được nhưng không thể decrypt hoặc export key.
- Tạo PKI role riêng trong Vault test, issue leaf certificate đúng SAN và kiểm từ chối SAN ngoài policy.
- Dùng Testcontainers để dựng môi trường ephemeral trên mỗi CI run và thu hồi leases, tokens, certificates, keys khi teardown.

### 15.3. Rubric nghiệm thu

| Hạng mục | Bằng chứng PASS |
| --- | --- |
| IAM identity đúng | STS trả ARN `ci-orders` từ credential riêng, không phải root. |
| AWS IAM login | Vault đối chiếu principal vào role và cấp token TTL ngắn. |
| Signed server ID | Vault và Java dùng đúng `vault-ci.internal`; mismatch bị từ chối theo test. |
| Vault ACL | `orders/config` đọc được, `finance/config` có fixture nhưng bị deny. |
| Spring Vault wiring | `VaultTemplate`/`VaultOperations` dùng auth của workload, không dùng root token. |
| Resilience | STS/Vault errors và token expiry được phân loại, retry giới hạn. |
| Emulator limitation | Kết quả security signature/IAM Unique ID không được tuyên bố vượt khả năng emulator. |
| Cleanup | Không có AWS/Vault production credentials và đã revoke/dọn tài nguyên. |

Nếu một emulator không hỗ trợ STS signed request hoặc principal mapping đúng, **không thay Vault role binding bằng wildcard**. Hãy ghi `PARTIAL/UNKNOWN` về cloud auth, giữ những test KV/policy đã được chứng minh riêng, rồi xác minh IAM login trên AWS staging thật trước rollout.

## 16. Câu hỏi tự đánh giá

1. Vì sao AWS access key và Vault token là hai credential khác nhau?
2. Vault sử dụng `STS GetCallerIdentity` để xác minh điều gì?
3. Vì sao STS trả root ARN làm bài test mất ý nghĩa?
4. `AwsIamAuthenticationOptions.endpointUri` khác `auth/aws-ci/config/client sts_endpoint` như thế nào?
5. Signed Host, SigV4 region và `X-Vault-AWS-IAM-Server-ID` liên quan ra sao?
6. Vì sao `resolve_aws_unique_ids=false` chỉ phù hợp để giới hạn lab emulator?
7. KV v2 `get("orders/config")` tương ứng HTTP/ACL path nào?
8. Vì sao Vault login thành công nhưng KV trả 403 không nhất thiết là lỗi AWS authentication?
9. Tại sao LocalStack test chưa đủ chứng minh chống giả mạo SigV4 của AWS?
10. Vault token TTL khác AWS temporary credentials expiration thế nào?
11. Nếu role bind wildcard ARN toàn account, negative auth test còn ý nghĩa không?
12. Khi chuyển từ lab IAM user sang EC2/ECS/EKS role thực, cần đổi credentials provider và kiểm trust gì?
13. Những trường nào có thể rò credential nếu bật HTTP wire logging?
14. Khi nào cần fail closed thay vì dùng KV snapshot cũ?
15. Vì sao không nên cấp sẵn Transit/PKI quyền cho mọi role cloud auth?

## Tài liệu tham khảo

- [HashiCorp Vault — AWS auth method](https://developer.hashicorp.com/vault/docs/auth/aws)
- [HashiCorp Vault — AWS auth HTTP API: STS endpoint, server ID, role](https://developer.hashicorp.com/vault/api-docs/auth/aws)
- [Spring Vault — Authentication Methods, AWS IAM](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault 4.1 — AwsIamAuthentication](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AwsIamAuthentication.html)
- [Spring Vault 4.1 — AwsIamAuthenticationOptions.Builder](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AwsIamAuthenticationOptions.AwsIamAuthenticationOptionsBuilder.html)
- [Spring Vault 4.1 — VaultClient](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultClient.html)
- [Spring Vault 4.1 — VaultTemplate](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html)
- [Spring Vault 4.1 — LifecycleAwareSessionManager](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/LifecycleAwareSessionManager.html)
- [AWS — STS GetCallerIdentity API](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html)
- [LocalStack — IAM service](https://docs.localstack.cloud/aws/services/iam/)
- [LocalStack — STS service](https://docs.localstack.cloud/aws/services/sts/)
- [HashiCorp Vault — KV v2 engine](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)
- [HashiCorp Vault — Policies](https://developer.hashicorp.com/vault/docs/concepts/policies)
