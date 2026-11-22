# Kết hợp Cognito, Secrets Manager và Parameter Store

Một Java Lambda function thường cần giải quyết đồng thời ba việc: xác định người dùng đang gọi API là ai, kiểm tra người đó được phép thực hiện thao tác nào, và lấy cấu hình hoặc thông tin xác thực để truy cập dịch vụ phía sau. AWS cung cấp các dịch vụ chuyên biệt cho từng việc: **Amazon Cognito** quản lý danh tính người dùng và token, **AWS Secrets Manager** lưu trữ secret, còn **AWS Systems Manager Parameter Store** quản lý tham số cấu hình và giá trị SecureString.

Các dịch vụ này có thể phối hợp trong cùng một luồng request, nhưng chúng không thay thế quyền của nhau. Token Cognito giúp xác thực người dùng; Lambda execution role cho phép mã function đọc secret hoặc parameter; API Gateway hoặc resource policy quyết định ai được gọi function. Thiết kế đúng ranh giới giúp tránh đưa mật khẩu vào mã nguồn, tránh tin dữ liệu nhận từ client và giới hạn quyền truy cập theo đúng nhiệm vụ.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt Cognito User Pools và Identity Pools.
- Mô tả cách API Gateway xác thực JWT do Cognito phát hành trước khi gọi Lambda.
- Phân biệt xác thực danh tính với phân quyền nghiệp vụ trong Java handler.
- Chọn giữa Secrets Manager và Parameter Store cho từng loại dữ liệu.
- Dùng AWS SDK for Java 2.x để đọc secret và parameter.
- Cấp quyền tối thiểu cho Lambda execution role, bao gồm quyền giải mã KMS khi cần.
- Thiết kế cache, TTL, rotation và xử lý lỗi khi secret thay đổi.
- Tránh ghi lộ token, password, API key hoặc dữ liệu nhạy cảm vào log và event.

## 1. Vai trò của ba dịch vụ

| Dịch vụ | Trách nhiệm chính | Ví dụ dữ liệu hoặc năng lực |
|---|---|---|
| **Amazon Cognito** | Đăng ký, đăng nhập, quản lý user và phát hành token | User Pool, access token, ID token, refresh token, nhóm người dùng |
| **AWS Secrets Manager** | Lưu trữ, kiểm soát truy cập và hỗ trợ rotation cho secret | Database password, API key, credential của dịch vụ bên ngoài |
| **AWS Systems Manager Parameter Store** | Lưu tham số cấu hình theo tên và phân cấp; hỗ trợ SecureString | Feature flag đơn giản, endpoint, tên queue, cấu hình theo môi trường, giá trị được mã hóa |

Một request có thể đi qua các bước sau:

~~~mermaid
flowchart TD
    A["Client đăng nhập Cognito"] --> B["Nhận JWT"]
    B --> C["Gọi API Gateway với Bearer token"]
    C --> D["Cognito User Pool / JWT authorizer xác thực token"]
    D --> E["API Gateway gọi Java Lambda"]
    E --> F["Lambda kiểm tra quyền nghiệp vụ từ claims"]
    F --> G["Lambda execution role đọc Secrets Manager / Parameter Store"]
    G --> H["Lambda truy cập database hoặc API phía sau"]
    H --> I["Trả response"]
~~~

Cognito không tự cấp quyền cho Lambda đọc Secrets Manager. Secrets Manager cũng không xác thực người dùng đang gọi API. Mỗi bước cần đúng cơ chế xác thực và phân quyền riêng.

## 2. Cognito User Pools và Identity Pools

Hai loại pool trong Cognito có mục đích khác nhau.

### User Pool: quản lý người dùng và token

**Cognito User Pool** là user directory có khả năng đăng ký, đăng nhập, xác thực và quản lý tài khoản. Sau khi người dùng xác thực thành công, Cognito có thể phát hành các token sau. ID token và access token là JWT; refresh token là credential riêng để xin token mới, không phải JWT dùng để gọi API nghiệp vụ:

- **ID token:** chứa các claim mô tả danh tính người dùng, ví dụ subject, email hoặc các thuộc tính đã xác minh.
- **Access token:** đại diện cho quyền truy cập được cấp trong phạm vi ứng dụng, có thể chứa scope và nhóm.
- **Refresh token:** dùng để xin token mới theo chính sách của app client; không gửi refresh token đến API nghiệp vụ như access token.

API thường nhận access token trong header:

~~~http
Authorization: Bearer <access-token>
~~~

Không đặt token thật trong URL query string vì URL có thể xuất hiện trong access log, browser history hoặc telemetry. Client phải bảo vệ token và gửi qua HTTPS.

### Identity Pool: cấp AWS credentials tạm thời

**Cognito Identity Pool** cho phép đổi danh tính đã xác thực hoặc khách ẩn danh thành AWS credentials tạm thời thông qua IAM role. Cách này hữu ích khi ứng dụng client cần truy cập trực tiếp một số tài nguyên AWS được giới hạn, ví dụ upload object vào một prefix riêng.

Identity Pool không thay thế User Pool. Một ứng dụng có thể dùng User Pool để đăng nhập và Identity Pool để cấp AWS credentials khi có nhu cầu truy cập tài nguyên AWS trực tiếp.

Đối với backend Java Lambda, mô hình phổ biến là:

- Client đăng nhập bằng User Pool và gửi access token đến API.
- API Gateway xác thực token.
- Lambda nhận request cùng claims đã được authorizer xác thực.
- Lambda dùng execution role của chính function để truy cập database, Secrets Manager và Parameter Store.

Không nên cấp AWS credentials rộng cho client chỉ để backend có thể đọc secret. Secret dùng bởi backend cần nằm trong quyền của execution role và không được trả về client.

### Bảng lựa chọn

| Nhu cầu | Thành phần phù hợp |
|---|---|
| Đăng ký, đăng nhập và quản lý tài khoản | Cognito User Pool |
| Xác thực request API bằng JWT | API Gateway Cognito authorizer hoặc JWT authorizer |
| Cấp AWS credentials tạm thời cho client | Cognito Identity Pool |
| Backend lấy database password | Secrets Manager |
| Backend lấy endpoint hoặc cấu hình theo môi trường | Parameter Store |
| Backend đọc SecureString | Parameter Store cùng IAM/KMS permissions |

## 3. Xác thực JWT Cognito trước khi gọi Lambda

Có thể để API Gateway xác thực JWT trước khi chuyển request đến Lambda. Điều này giúp loại request có token không hợp lệ khỏi luồng xử lý nghiệp vụ.

### API Gateway REST API

REST API hỗ trợ **Cognito User Pool authorizer**. Cấu hình authorizer với User Pool và gắn vào method cần bảo vệ. Nếu method có authorization scopes, API Gateway xử lý token như access token và kiểm tra các scope tương ứng. Nếu không cấu hình scope, API Gateway xử lý token như ID token. Hãy dùng access token cho route cần kiểm tra scope và cấu hình app client để phát hành đúng resource server scopes.

### API Gateway HTTP API

HTTP API hỗ trợ **JWT authorizer**. Với Cognito User Pool, issuer thường có dạng:

~~~text
https://cognito-idp.<region>.amazonaws.com/<user-pool-id>
~~~

Cấu hình JWT authorizer gồm:

- Identity source, thường là `$request.header.Authorization`.
- Issuer URL của User Pool.
- Audience là app client ID phù hợp; Cognito ID token thường dùng claim `aud`, còn access token dùng `client_id`.
- Authorization scopes trên route nếu API yêu cầu scope cụ thể.

API Gateway kiểm tra chữ ký JWT bằng public keys của issuer, issuer, audience/client, thời hạn và các điều kiện token cần thiết. Khi route yêu cầu scope, token phải chứa scope phù hợp. Chi tiết cấu hình khác nhau giữa REST API và HTTP API, vì vậy cần chọn đúng loại API trước khi làm theo hướng dẫn.

Với HTTP API, hãy cấu hình scope riêng cho route cần access token; không dựa riêng vào việc audience khớp để phân biệt ID token và access token. Nếu ứng dụng tự xác thực JWT trong Lambda, kiểm tra thêm `token_use=access` cho API nghiệp vụ.

### Token đã được xác thực vẫn cần kiểm tra quyền nghiệp vụ

Xác thực token trả lời câu hỏi “token có hợp lệ và thuộc về danh tính nào?”. Phân quyền nghiệp vụ trả lời “danh tính này được phép xem hoặc sửa tài nguyên nào?”.

Ví dụ, access token hợp lệ không có nghĩa người dùng được đọc mọi đơn hàng. Java service vẫn phải kiểm tra owner, tenant, role hoặc quyền trên resource. Không tin `tenantId`, `userId` hoặc `role` do client gửi trong request body nếu các giá trị đó có thể được giả mạo. Hãy lấy subject và claims từ ngữ cảnh authorizer đã xác thực, rồi đối chiếu với dữ liệu nghiệp vụ phía server.

Nếu tự xác thực JWT trong code thay vì dùng authorizer, phải kiểm tra chữ ký theo JWKS, issuer, thời hạn (`exp`), `nbf` nếu có, app client/audience và loại token phù hợp. Không chỉ decode Base64 rồi tin payload. Với Cognito, cần phân biệt ID token và access token; claim `token_use` giúp xác định loại token khi ứng dụng tự kiểm tra.

### Java handler: lấy principal từ ngữ cảnh authorizer

Cấu trúc event khác nhau giữa REST API và HTTP API. Adapter nên chuyển claims đã được API Gateway xác thực thành một mô hình nội bộ rõ ràng, ví dụ. Các đoạn code dùng Java record, yêu cầu Java 16 trở lên (có sẵn trên runtime Java 17/21 của Lambda):

~~~java
public record AuthenticatedPrincipal(
        String subject,
        String tenantId,
        java.util.Set<String> scopes) {
}

public record GetOrderCommand(String orderId) {
}

public final class GetOrderService {
    public OrderView get(
            AuthenticatedPrincipal principal,
            GetOrderCommand command) {

        // Repository phải kiểm tra order thuộc tenant/owner được phép.
        return loadVisibleOrder(
                principal.subject(),
                principal.tenantId(),
                command.orderId());
    }

    private OrderView loadVisibleOrder(
            String subject,
            String tenantId,
            String orderId) {
        // Minh họa ranh giới truy vấn; triển khai repository ở tầng persistence.
        return new OrderView(orderId, "PROCESSING");
    }
}

public record OrderView(String orderId, String status) {
}
~~~

Adapter đọc claims từ đúng cấu trúc request context của loại API Gateway đang dùng và tạo AuthenticatedPrincipal. Không lấy claims từ header tùy ý do client tự đặt; API Gateway authorizer context là nguồn tin cậy khi integration và mapping được cấu hình đúng.

Nếu dùng group hoặc custom claim để phân quyền, cần kiểm soát ai có quyền thay đổi thuộc tính đó, thời gian token có hiệu lực và cách thu hồi quyền. Claim `tenantId` trong ví dụ chỉ tồn tại nếu ứng dụng chủ động đưa nó vào token qua cơ chế được kiểm soát; nếu không, hãy tra tenant membership từ dữ liệu phía server dựa trên subject. Token đã phát hành có thể tiếp tục hợp lệ cho đến khi hết hạn theo chính sách; thay đổi quyền ở User Pool không nhất thiết lập tức sửa nội dung token cũ.

## 4. Secrets Manager và Parameter Store khác nhau thế nào?

Cả hai dịch vụ đều có thể lưu dữ liệu cấu hình, và Parameter Store có thể lưu giá trị được mã hóa. Tuy vậy, chúng được tối ưu cho các nhu cầu khác nhau.

| Tiêu chí | Secrets Manager | Parameter Store |
|---|---|---|
| Mục tiêu chính | Quản lý secret | Quản lý tham số cấu hình và SecureString |
| Loại dữ liệu | Credential, password, API key, token | String, StringList, SecureString |
| Mã hóa | Mã hóa bằng AWS KMS | SecureString được mã hóa bằng AWS KMS |
| Rotation | Có cơ chế rotation, thường phối hợp Lambda hoặc tích hợp được hỗ trợ | Không có quy trình rotation secret tương đương tích hợp sẵn |
| Version | Secret versions và staging labels như AWSCURRENT, AWSPREVIOUS, AWSPENDING | Parameter versions và labels |
| Phân cấp | Secret name/ARN | Hierarchical path, ví dụ `/prod/orders/database/host` |
| Lựa chọn phù hợp | Secret cần kiểm soát vòng đời và rotation | Cấu hình vận hành, tham số theo môi trường, SecureString đơn giản |

Quy tắc lựa chọn thực tế:

- Dùng Secrets Manager cho password database, credential và API key cần rotation hoặc quy trình quản lý secret chuyên biệt.
- Dùng Parameter Store cho endpoint, tên queue, giới hạn nghiệp vụ, feature configuration đơn giản và SecureString khi không cần lifecycle/rotation của Secrets Manager.
- Không chọn Parameter Store chỉ vì giá hoặc cấu hình đơn giản nếu yêu cầu nghiệp vụ cần rotation và quản lý secret chuyên biệt.
- Không lưu dữ liệu có thể công khai trong secret store chỉ để thay thế một hệ thống quản lý cấu hình có cấu trúc.

Parameter Store có các tier và giới hạn khác nhau về kích thước, throughput, tính năng và chi phí. Hãy kiểm tra tier phù hợp với số lượng, kích thước và tần suất đọc tham số của ứng dụng.

## 5. Lưu secret an toàn bằng Secrets Manager

Một secret database có thể lưu dưới dạng JSON:

~~~json
{
  "username": "orders_app",
  "password": "<secret-value>",
  "host": "orders-db.example.internal",
  "port": 5432,
  "dbname": "orders"
}
~~~

Ví dụ chỉ minh họa cấu trúc. Không đưa giá trị password thật vào source code, file cấu hình được commit, Docker image, Lambda event, log hoặc tài liệu triển khai.

Function thường chỉ cần biết ARN hoặc tên secret, ví dụ cấu hình environment variable:

~~~text
DB_SECRET_ARN=arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:prod/orders/database-AbCdEf
~~~

ARN là tham chiếu đến secret, không phải secret value. Tuy vậy, ARN và tên secret vẫn có thể tiết lộ cấu trúc hệ thống, nên chỉ chia sẻ trong phạm vi cần thiết.

### Đọc secret bằng AWS SDK for Java 2.x

Ví dụ sau lấy SecretString từ Secrets Manager:

~~~java
import software.amazon.awssdk.services.secretsmanager.SecretsManagerClient;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueRequest;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueResponse;

public final class SecretReader {
    private final SecretsManagerClient client;

    public SecretReader(SecretsManagerClient client) {
        this.client = client;
    }

    public String read(String secretArn) {
        GetSecretValueResponse response = client.getSecretValue(
                GetSecretValueRequest.builder()
                        .secretId(secretArn)
                        .build());

        String value = response.secretString();
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Secret does not contain a SecretString");
        }
        return value;
    }
}
~~~

Để dùng trong Lambda, tạo SDK client một lần theo vòng đời execution environment nếu client thread-safe, sau đó tái sử dụng. Không tạo và đóng client ở mỗi request nếu không cần thiết. Dùng default credential provider chain để SDK nhận credentials từ execution role; không ghi access key/secret key vào code.

Nếu secret là SecretBinary, code cần đọc trường binary thay vì giả định luôn có SecretString. Với JSON secret, parse vào một record hoặc object đã định nghĩa, kiểm tra field bắt buộc và không log object chứa password.

### IAM permissions cho Secrets Manager

Execution role của Lambda cần quyền `secretsmanager:GetSecretValue` trên đúng secret ARN. Ví dụ policy tối giản:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:prod/orders/database-*"
    }
  ]
}
~~~

Nếu secret dùng customer-managed KMS key, role còn cần quyền `kms:Decrypt` trên key đó và key policy phải cho phép. Với AWS managed key của Secrets Manager, cách cấp quyền có thể khác; không cấp quyền KMS rộng nếu không cần.

Resource policy của secret có thể được dùng cho cross-account access hoặc kiểm soát bổ sung. Khi đó cần xem xét cả identity policy của caller, resource policy của secret và KMS key policy. Không dùng wildcard cho toàn bộ secret trong account nếu function chỉ cần một secret.

## 6. Parameter Store: cấu hình phân cấp và SecureString

Parameter Store tổ chức tham số theo tên, thường dùng path phân cấp để tách môi trường, ứng dụng và thành phần:

~~~text
/prod/orders/api/base-url
/prod/orders/feature/new-checkout
/prod/orders/database/host
/prod/orders/database/password
/staging/orders/api/base-url
/staging/orders/database/host
~~~

Ví dụ:

- `String`: endpoint hoặc tên queue không nhạy cảm.
- `StringList`: danh sách giá trị đơn giản.
- `SecureString`: giá trị cần mã hóa như một mật khẩu hoặc token có yêu cầu bảo vệ.

SecureString dùng KMS để mã hóa. Khi đọc với `WithDecryption=true`, SSM trả về giá trị đã giải mã nếu caller có quyền cần thiết. Với customer-managed key, cần quyền `kms:Decrypt` và key policy phù hợp.

### Đọc parameter bằng AWS SDK for Java 2.x

~~~java
import software.amazon.awssdk.services.ssm.SsmClient;
import software.amazon.awssdk.services.ssm.model.GetParameterRequest;
import software.amazon.awssdk.services.ssm.model.GetParameterResponse;

public final class ParameterReader {
    private final SsmClient ssm;

    public ParameterReader(SsmClient ssm) {
        this.ssm = ssm;
    }

    public String read(String parameterName, boolean secure) {
        GetParameterResponse response = ssm.getParameter(
                GetParameterRequest.builder()
                        .name(parameterName)
                        .withDecryption(secure)
                        .build());

        return response.parameter().value();
    }
}
~~~

Với parameter thường, truyền `secure=false`; với SecureString, truyền `secure=true`. Không ghi giá trị trả về vào log. Khi đọc nhiều parameter, có thể dùng API batch phù hợp để giảm số request, nhưng cần xử lý danh sách parameter không tìm thấy hoặc bị từ chối quyền.

### IAM permissions cho Parameter Store

Ví dụ role chỉ được đọc các parameter dưới path production của ứng dụng:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:GetParametersByPath"
      ],
      "Resource": "arn:aws:ssm:ap-southeast-1:123456789012:parameter/prod/orders/*"
    }
  ]
}
~~~

Nếu chỉ cần một parameter, hãy cấp quyền trên ARN parameter cụ thể và chỉ action cần thiết. Khi dùng `GetParametersByPath` với chế độ recursive, quyền đọc path cha có thể bao phủ các parameter con; đừng cấp path rộng nếu có tham số nhạy cảm ở nhánh con. Nếu đọc SecureString dùng customer-managed KMS key, thêm `kms:Decrypt` giới hạn trên key đó. Cần kiểm tra key policy, vì IAM allow đơn lẻ chưa chắc đã đủ nếu key policy không cho phép principal sử dụng key.

### Chọn một nguồn chuẩn cho mỗi cấu hình

Tránh lưu cùng một giá trị ở cả environment variable, Parameter Store và Secrets Manager rồi để ứng dụng tự chọn. Điều đó tạo ra câu hỏi về nguồn nào mới nhất và cách xử lý khi các giá trị khác nhau.

Một quy ước dễ vận hành:

- Environment variable chứa tên/ARN secret, parameter path, region hoặc cấu hình không nhạy cảm cần cố định theo deployment.
- Parameter Store giữ cấu hình vận hành có thể thay đổi độc lập với code.
- Secrets Manager giữ credential và secret cần quản lý vòng đời.
- Database hoặc dịch vụ nghiệp vụ giữ dữ liệu nghiệp vụ chuẩn.

## 7. Kết hợp Cognito, Lambda và secret trong một request

Giả sử API `GET /orders/{id}` cần xác thực người dùng Cognito và đọc database bằng credential lưu trong Secrets Manager.

Luồng xử lý:

1. Client đăng nhập Cognito User Pool và nhận access token.
2. Client gọi API Gateway với header Authorization Bearer.
3. API Gateway authorizer kiểm tra token và route scope.
4. API Gateway chuyển request cùng authorizer context đến Java Lambda.
5. Adapter tạo AuthenticatedPrincipal từ claims đã xác thực.
6. Service kiểm tra người dùng có quyền xem order thuộc tenant của họ.
7. Repository lấy credential từ cache secret hoặc Secrets Manager bằng execution role.
8. Repository truy vấn database.
9. Lambda trả response đã loại bỏ thông tin nhạy cảm.

Phân quyền ở bước 6 phải dựa trên claims đáng tin cậy và dữ liệu nghiệp vụ. Không trả database password, secret value hoặc token Cognito về client.

### Phân biệt ba loại quyền

| Quyền | Ai sử dụng? | Ví dụ |
|---|---|---|
| Quyền gọi API | Người dùng/client | Access token Cognito có scope `orders/read` |
| Quyền invoke Lambda | API Gateway hoặc caller | Lambda resource policy cho phép API Gateway gọi function/alias |
| Quyền truy cập secret và database | Java Lambda code | Execution role có `secretsmanager:GetSecretValue`, `ssm:GetParameter` và quyền database ở tầng mạng/credential |

Một request có thể qua xác thực Cognito thành công nhưng Lambda vẫn bị từ chối đọc secret do execution role thiếu quyền. Ngược lại, Lambda có quyền đọc secret không có nghĩa mọi người dùng đều được phép gọi API. Hãy quan sát và xử lý hai loại lỗi độc lập.

## 8. Cache secret và parameter trong Lambda

Đọc Secrets Manager hoặc Parameter Store ở mỗi invocation làm tăng network call, latency và chi phí. Có thể cache giá trị trong execution environment với TTL có giới hạn.

Vì Lambda có thể warm reuse, cache static có thể tồn tại qua nhiều invocation trên cùng environment. Nhưng cache đó:

- Không được chia sẻ giữa các execution environment.
- Có thể mất khi Lambda thu hồi environment.
- Có thể chứa giá trị cũ sau khi secret rotation hoặc parameter update.
- Phải an toàn nếu nhiều thread trong cùng JVM cùng truy cập.

Có thể dùng AWS Secrets Manager caching library cho Java hoặc tự xây cache có TTL và đồng bộ phù hợp. AWS Parameters and Secrets Lambda Extension cũng là một lựa chọn để đọc qua local HTTP endpoint và cache trong execution environment. Extension cần cấu hình, IAM role và TTL; cache của mỗi environment vẫn độc lập.

### Ví dụ cache secret có TTL

Đoạn code minh họa cache một giá trị secret trong một JVM. Trong production, cân nhắc dùng caching library được hỗ trợ và bổ sung metric/timeout theo yêu cầu.

Đoạn code này cũng dùng Java record, yêu cầu Java 16 trở lên.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class TtlSecretCache {
    private final SecretReader reader;
    private final String secretArn;
    private final Clock clock;
    private final Duration ttl;
    private final Object refreshLock = new Object();

    private volatile CachedValue cached;

    public TtlSecretCache(
            SecretReader reader,
            String secretArn,
            Clock clock,
            Duration ttl) {
        this.reader = reader;
        this.secretArn = secretArn;
        this.clock = clock;
        this.ttl = ttl;
    }

    public String get() {
        CachedValue current = cached;
        if (isFresh(current)) {
            return current.value();
        }

        synchronized (refreshLock) {
            current = cached;
            if (isFresh(current)) {
                return current.value();
            }

            String value = reader.read(secretArn);
            CachedValue refreshed = new CachedValue(
                    value, clock.instant().plus(ttl));
            cached = refreshed;
            return refreshed.value();
        }
    }

    private boolean isFresh(CachedValue value) {
        return value != null && clock.instant().isBefore(value.expiresAt());
    }

    private record CachedValue(String value, Instant expiresAt) {
    }
}
~~~

TTL phải được chọn dựa trên yêu cầu rotation và mức chấp nhận dữ liệu cũ. Không cache secret vô thời hạn. Khi secret hết hạn trong cache và Secrets Manager không khả dụng, ứng dụng cần fail theo chính sách đã định nghĩa; không âm thầm chuyển sang credential cũ vô thời hạn.

Nếu nhiều invocation cùng refresh cache, synchronized ở ví dụ chỉ phối hợp thread trong một JVM. Các execution environment khác vẫn có thể cùng gọi Secrets Manager. Nếu cần giảm tải trên toàn hệ thống, dùng cache service hoặc extension/library có hành vi phù hợp, nhưng vẫn phải kiểm soát TTL và quyền truy cập.

## 9. Rotation secret và kết nối database

Secrets Manager hỗ trợ quản lý version của secret với staging labels như:

- `AWSCURRENT`: phiên bản hiện hành mà consumer thường đọc.
- `AWSPREVIOUS`: phiên bản trước đó.
- `AWSPENDING`: phiên bản đang được chuẩn bị trong quá trình rotation.

Quy trình rotation phổ biến gồm các bước tạo credential mới, áp dụng credential ở hệ thống đích, kiểm tra credential mới và chuyển label current sang version mới. Với rotation dựa trên Lambda, các bước thường được biểu diễn qua các phase createSecret, setSecret, testSecret và finishSecret.

Rotation chỉ hoạt động khi đã cấu hình rotation schedule và cơ chế phù hợp cho loại secret/dịch vụ đích. Không phải mọi API key hoặc database đều tự động xoay được chỉ bằng cách tạo secret.

### Ứng dụng cần chịu được rotation

Giả sử database password được xoay:

1. Secrets Manager tạo hoặc nhận credential mới.
2. Database bắt đầu chấp nhận credential mới.
3. Secret current chuyển sang phiên bản mới sau khi rotation hoàn tất theo quy trình.
4. Lambda environment đang cache password cũ có thể tiếp tục dùng đến khi cache hết TTL.
5. Connection pool có thể còn các connection được tạo bằng credential cũ.

Vì vậy:

- TTL cache nên ngắn hơn khoảng thời gian nghiệp vụ cho phép giữ credential cũ.
- Khi nhận lỗi xác thực database, có thể evict cache, đọc lại secret và thử lại một lần có giới hạn nếu thao tác an toàn.
- Connection pool cần có chính sách đóng/recycle connection cũ; đổi password trong cache không tự thay credential của connection đã mở.
- Không retry vô hạn khi database từ chối credential.
- Rotation cần được kiểm thử với function đang warm và có connection pool hoạt động.

Với thao tác ghi có thể bị lặp, không tự động chạy lại nghiệp vụ chỉ vì lần kết nối đầu tiên lỗi xác thực. Hãy phân biệt lỗi xác thực trước khi transaction bắt đầu với lỗi xảy ra sau khi server đã commit nhưng response bị mất.

## 10. Cache Parameter Store và cập nhật cấu hình

Parameter Store có version cho mỗi parameter. Khi cập nhật giá trị, version mới được tạo. Ứng dụng có thể đọc parameter hiện hành hoặc tham chiếu version/label theo nhu cầu.

Nếu function cache parameter, thay đổi trong Parameter Store không nhất thiết có hiệu lực ngay trên các environment đang chạy. Cần chọn một trong các cách:

- TTL ngắn để function tự đọc lại sau một khoảng thời gian.
- Phát event khi cấu hình thay đổi và yêu cầu consumer invalidation.
- Dùng version/label trong cấu hình deployment để pin giá trị đã kiểm thử.
- Redeploy/restart environment khi thay đổi cần được áp dụng đồng bộ.

Không dùng TTL cực ngắn cho mọi request nếu cấu hình ít thay đổi; điều đó làm tăng API calls và latency. Ngược lại, không cache lâu nếu thay đổi cấu hình cần có hiệu lực nhanh.

Với cấu hình có ảnh hưởng bảo mật hoặc hành vi quan trọng, cần có quy trình phê duyệt, audit và rollback parameter version. Parameter Store là kho tham số, không thay thế quy trình quản lý thay đổi ứng dụng.

## 11. Bảo mật, logging và xử lý lỗi

Các nguyên tắc sau nên áp dụng cho toàn bộ luồng:

- Không ghi access token, refresh token, password, API key hoặc secret JSON vào log, trace, metric hay exception message.
- Không truyền secret trong event payload giữa các function; truyền secret ARN hoặc resource identifier nếu cần tham chiếu.
- Không đưa secret value vào Lambda environment variable nếu có thể lấy trực tiếp từ secret store.
- Dùng HTTPS cho API và TLS cho kết nối đến dịch vụ hỗ trợ.
- Dùng IAM execution role thay cho access key tĩnh.
- Giới hạn secret/parameter theo đúng ARN hoặc path mà function cần.
- Bật CloudTrail/audit logging phù hợp để theo dõi thao tác quản lý secret và policy.
- Phân biệt lỗi token không hợp lệ, lỗi thiếu quyền, secret không tồn tại, KMS decrypt denied và dịch vụ tạm thời không khả dụng.
- Dùng timeout và retry có giới hạn; không retry lỗi authorization hoặc cấu hình sai như lỗi tạm thời.
- Redact dữ liệu nhạy cảm trước khi ghi log, kể cả khi exception từ SDK chứa request context.

Không trả lỗi nội bộ như secret ARN đầy đủ, tên database hoặc thông tin KMS cho client. Client chỉ cần mã lỗi nghiệp vụ và correlation ID để hỗ trợ điều tra.

### Ví dụ phân loại lỗi

| Lỗi | Nơi xử lý | Hướng xử lý |
|---|---|---|
| JWT hết hạn hoặc sai chữ ký | API Gateway authorizer | Từ chối request, client xác thực lại |
| Token hợp lệ nhưng thiếu scope | Authorizer/route hoặc service | Trả 403 theo hợp đồng API |
| User không sở hữu order | Service nghiệp vụ | Từ chối truy cập resource |
| Secrets Manager AccessDenied | Execution role/resource policy | Sửa IAM hoặc resource policy; không retry vô hạn |
| KMS Decrypt denied | IAM/key policy | Kiểm tra quyền trên đúng KMS key |
| Secret tạm thời không khả dụng | Secret provider | Retry có backoff và giới hạn; dùng cache còn hạn nếu chính sách cho phép |
| Database credential cũ | Connection/provider layer | Refresh secret có kiểm soát, recycle connection và thử lại an toàn |

## 12. Kiểm thử tích hợp

Một bài kiểm thử chỉ gọi Lambda trực tiếp bằng test event không chứng minh toàn bộ luồng Cognito và quyền secret hoạt động đúng.

Hãy kiểm thử các tình huống:

| Tình huống | Điều cần xác minh |
|---|---|
| Access token hợp lệ và đủ scope | Request đến Lambda và xử lý đúng principal |
| Token hết hạn hoặc sai issuer | Authorizer từ chối trước khi chạy nghiệp vụ |
| Token hợp lệ nhưng thiếu scope | Request bị từ chối theo route policy |
| User A yêu cầu order của user B | Service kiểm tra owner/tenant và không trả dữ liệu |
| Lambda thiếu quyền GetSecretValue | Invocation thất bại có log an toàn và cảnh báo |
| Secret dùng customer-managed KMS key | Execution role và key policy cho phép decrypt đúng secret |
| Parameter SecureString | SDK đọc với decryption và đúng path |
| Secret rotation | Invocation warm đọc credential mới sau TTL hoặc refresh policy |
| Database connection pool giữ credential cũ | Pool recycle theo quy trình và request phục hồi an toàn |
| Parameter được cập nhật | Cache refresh theo TTL/event/version policy |
| Cache miss đồng thời | Không tạo request storm vượt khả năng secret store |
| Secret/parameter không tồn tại | Lỗi được phân loại, không lộ giá trị hoặc cấu hình nội bộ |

Dùng môi trường AWS test riêng và secret giả lập. Không dùng production credential trong unit test hoặc fixture. Với JWT, có thể mock adapter claims trong unit test, nhưng integration test cần xác minh authorizer thật đã kiểm tra token và scope.

## 13. Checklist triển khai

- [ ] Đã chọn User Pool cho đăng nhập và chỉ dùng Identity Pool khi client cần AWS credentials tạm thời.
- [ ] API Gateway authorizer được cấu hình đúng loại REST API hoặc HTTP API.
- [ ] Route nhạy cảm yêu cầu access token và scope phù hợp.
- [ ] Java handler chỉ tin claims đến từ authorizer đã xác thực.
- [ ] Service kiểm tra tenant, owner và quyền nghiệp vụ trên resource.
- [ ] Secret được lưu trong Secrets Manager hoặc SecureString phù hợp; không commit vào source.
- [ ] Cấu hình không nhạy cảm được tổ chức theo path Parameter Store rõ ràng.
- [ ] Lambda environment variable chỉ chứa ARN/path và cấu hình tham chiếu cần thiết.
- [ ] Execution role chỉ có GetSecretValue/GetParameter trên tài nguyên cần thiết.
- [ ] KMS IAM policy và key policy cho phép decrypt đúng key khi cần.
- [ ] Cache có TTL phù hợp với rotation và yêu cầu cập nhật cấu hình.
- [ ] Có quy trình refresh credential và recycle connection pool sau rotation.
- [ ] Không log token, secret value, password hoặc dữ liệu cá nhân không cần thiết.
- [ ] Có timeout, retry giới hạn, metric và cảnh báo cho lỗi secret/config.
- [ ] Đã kiểm thử token, scope, tenant isolation, IAM deny, KMS, rotation và cache expiry.

## Tự kiểm tra

1. Cognito User Pool khác Identity Pool ở mục đích và loại credential được cung cấp như thế nào?
2. Vì sao access token Cognito hợp lệ chưa đủ để cho phép người dùng đọc bất kỳ đơn hàng nào?
3. API Gateway authorizer và Lambda execution role bảo vệ hai ranh giới nào?
4. Khi nào nên chọn Secrets Manager thay vì Parameter Store SecureString?
5. Vì sao Lambda cần quyền `kms:Decrypt` trong một số cấu hình đọc secret hoặc SecureString?
6. Cache secret quá lâu có thể gây lỗi gì sau khi credential được rotation?
7. Vì sao thay password trong cache không tự cập nhật các connection database đã mở?
8. Nếu secret store tạm thời không khả dụng, cần cân nhắc điều gì trước khi dùng giá trị cache cũ?
9. Vì sao không nên đưa secret value hoặc refresh token vào log và event payload?

Cognito, Secrets Manager và Parameter Store giải quyết những phần khác nhau của một ứng dụng serverless: danh tính người dùng, secret và cấu hình vận hành. Khi API Gateway xác thực token, Java service kiểm tra quyền nghiệp vụ, execution role chỉ đọc đúng tài nguyên và cache/rotation được thiết kế có giới hạn, ứng dụng có thể tích hợp các dịch vụ này mà vẫn giữ được ranh giới bảo mật rõ ràng.

