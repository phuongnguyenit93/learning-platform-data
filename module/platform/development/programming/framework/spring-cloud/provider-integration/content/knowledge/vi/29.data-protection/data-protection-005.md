# Giới hạn thời gian, phạm vi và quyền của URL hoặc token chia sẻ

Một URL tải file có chữ ký hoặc bearer token giúp người nhận truy cập tài nguyên mà không cần cấp tài khoản cloud. Cơ chế này tiện để chia sẻ hợp đồng, ảnh, báo cáo hoặc nhận file upload từ đối tác. Nhưng **ai có URL/token đều có thể sử dụng nó trong phạm vi được cấp**. Nếu link bị chuyển tiếp, ghi vào log, lưu trong lịch sử trình duyệt hoặc xuất hiện trong analytics, người khác có thể dùng nó như người nhận ban đầu.

Thiết kế an toàn cần giới hạn đồng thời **thời gian**, **tài nguyên**, **hành động**, **đối tượng sử dụng** và **khả năng thu hồi**. Một link chỉ cho đọc một object trong 5 phút có rủi ro thấp hơn link cho phép đọc/ghi cả container trong nhiều ngày. Token có audience và scope rõ ràng tốt hơn token có quyền rộng. Thời hạn ngắn không bù được quyền quá rộng hoặc URL bị lộ.

Bài thuộc chương **Bảo vệ dữ liệu** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud, bao gồm danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Trọng tâm bài là tạo liên kết chia sẻ có thời hạn và quyền tối thiểu, dùng signed URL/SAS đúng cách, bảo vệ bearer token, quản lý thu hồi và kiểm tra audit.

## 1. Mục tiêu học tập và tình huống thực tế

Sau bài học, bạn có thể:

1. Phân biệt URL chia sẻ có chữ ký, SAS, presigned URL, signed URL và OAuth access token.
2. Giải thích vì sao URL/token chia sẻ là bearer credential và người giữ nó có thể sử dụng.
3. Thiết kế TTL, resource scope, HTTP method, permission, audience và giới hạn mạng.
4. Tạo presigned URL cho S3, user delegation SAS cho Azure Blob và signed URL cho Google Cloud Storage.
5. Thiết kế share-link service trong Spring Boot có expiry, revoke, audit và quota.
6. Phân biệt link có thể thu hồi với link chỉ hết hạn theo chữ ký.
7. Bảo vệ URL/token khỏi log, browser history, referrer, analytics, ticket và chat.
8. Kiểm thử hết hạn, sai quyền, sai object, replay, revoke và upload vượt giới hạn.

Tình huống xuyên suốt: **document-service** lưu hợp đồng trong object storage. Người dùng đã đăng nhập yêu cầu chia sẻ một hợp đồng cho đối tác trong thời gian ngắn. Đối tác không có tài khoản cloud. Hệ thống cần tạo link chỉ đọc đúng object, hết hạn sau một khoảng thời gian, có thể thu hồi theo yêu cầu và ghi lại ai đã tạo link.

~~~mermaid
flowchart TD
    U["Người dùng đã đăng nhập"] --> API["Spring Boot Share API"]
    API --> AUTH["Xác thực + kiểm tra quyền với object"]
    AUTH --> POLICY["Tạo grant: object, action, TTL, recipient"]
    POLICY --> SIGN["Cloud signer: S3 / SAS / GCS"]
    SIGN --> URL["URL có chữ ký ngắn hạn"]
    URL --> R["Người nhận"]
    R --> STORE["Managed object storage"]
    API --> AUDIT["Audit: creator, object, expiry, permission"]
    STORE --> LOG["Access log / monitoring"]
~~~

**Nguyên tắc quan trọng:** signed URL không chứng minh danh tính người bấm link. Nó chứng minh request có chữ ký hợp lệ. Nếu cần biết chính xác người nhận, phải xác thực họ qua ứng dụng hoặc một cơ chế identity khác trước khi cấp quyền tải.

## 2. Phân biệt các loại URL và token

### 2.1. Signed URL, presigned URL và SAS

Đây là URL chứa thông tin xác thực/chữ ký trong query string hoặc cấu trúc URL. Người nhận có thể gọi trực tiếp dịch vụ lưu trữ:

- AWS S3 presigned URL: chữ ký SigV4 cho một HTTP method và object cụ thể.
- Azure Storage SAS: token query string xác định resource, permission và khoảng thời gian.
- Google Cloud Storage signed URL: chữ ký V4 cho method, object, thời gian và các header đã ký.

Đặc điểm chung:

- Không cần chia sẻ access key/secret key của cloud với người nhận.
- Người tạo link phải có quyền cần thiết để thực hiện thao tác đã ký.
- Ai có link đều có thể dùng trong giới hạn chữ ký.
- Link có thể bị copy, forward, lưu trong browser history hoặc log.
- Thời gian hết hạn là giới hạn quan trọng nhưng không phải cơ chế duy nhất.

### 2.2. OAuth access token và bearer token

Access token thường được gửi trong HTTP Authorization header:

~~~http
Authorization: Bearer eyJhbGciOi...
~~~

Token đại diện quyền của subject/client đối với audience, scope và thời gian hiệu lực nhất định. Resource server xác minh token và kiểm tra quyền cho mỗi request.

Không nên đặt OAuth bearer token vào URL query parameter. URL thường xuất hiện trong browser history, reverse proxy log, analytics, referer header và hệ thống quan sát. RFC 6750 khuyến nghị gửi bearer token trong Authorization header hoặc request body được bảo vệ bằng TLS, không đưa vào page URL.

### 2.3. Application share link

Ứng dụng có thể tự tạo link dạng:

~~~text
https://share.example.com/s/opaque-random-token
~~~

Token ngẫu nhiên được tra cứu trong database để xác định:

- Resource/object được chia sẻ.
- Người tạo và người nhận dự kiến.
- Quyền được phép.
- Thời hạn và thời điểm thu hồi.
- Giới hạn số lần dùng hoặc trạng thái đã dùng.
- Yêu cầu xác minh danh tính, OTP hoặc email.

Đây là mô hình phù hợp khi cần thu hồi từng link, giới hạn số lần truy cập hoặc yêu cầu người nhận xác thực. Ứng dụng kiểm tra token trước khi stream nội dung hoặc cấp một URL cloud ngắn hạn.

### 2.4. So sánh

| Cơ chế | Quyền được quyết định ở đâu? | Có thể thu hồi riêng từng link? | Người nhận cần cloud identity? |
| --- | --- | --- | --- |
| S3 presigned URL | Chữ ký, IAM principal và bucket/object policy | Không có thao tác revoke từng URL riêng; có thể chặn qua credential/policy/resource | Không |
| Azure SAS | SAS permission, resource, expiry và key/policy ký | Tùy loại SAS; stored access policy hỗ trợ một số service SAS | Không |
| GCS signed URL | Chữ ký, quyền của signer và object policy | Thường phải revoke key/signing identity hoặc chặn resource; không có nút revoke từng URL | Không |
| OAuth access token | Authorization server cấp scope/audience; resource server xác minh | Phụ thuộc token format, introspection/revocation và thời hạn | Có identity/token |
| Application share link | Database/policy của ứng dụng | Có, nếu mỗi request đi qua share service | Không nhất thiết; có thể yêu cầu OTP/login |

Signed URL là một dạng bearer capability: quyền được trao cho người giữ link. Không gửi link trong kênh công khai hoặc xem nó như một URL thông thường.

## 3. Thiết kế giới hạn thời gian

### 3.1. TTL ngắn theo mục đích

Thời hạn phải dựa trên thời gian người nhận cần để hoàn thành công việc:

| Use case | TTL khởi điểm để cân nhắc | Ghi chú |
| --- | --- | --- |
| Xem trước tài liệu trong phiên | 1–5 phút | Có thể cấp lại khi người dùng vẫn được phép |
| Tải hợp đồng cho đối tác | 5–15 phút | Xác minh recipient trước khi phát link |
| Upload một file từ browser | 5–15 phút | Ràng buộc method, object key và header |
| Tải báo cáo tạm thời | 5–30 phút | Xóa file tạm theo retention |
| Tích hợp batch với đối tác | Theo lịch chạy, thường ngắn hơn credential dài hạn | Cân nhắc workload identity thay link dài hạn |

Đây là ví dụ thiết kế, không phải giới hạn bắt buộc của cloud. Cần cân bằng thời gian truyền file, mạng chậm, retry và trải nghiệm người dùng. Với file lớn, request bắt đầu trước expiry có thể tiếp tục sau thời điểm hết hạn tùy dịch vụ; lần kết nối lại sau expiry thường sẽ bị từ chối.

### 3.2. Không nhầm TTL URL với TTL credential ký

Thời hạn hiệu lực thực tế thường là giới hạn nhỏ nhất trong các giới hạn:

- Expiry ghi trong URL/token.
- Expiry của credential/session đã ký URL.
- Key hoặc signing identity bị disable/rotate.
- Resource policy hoặc network policy từ chối request.
- Application share grant bị thu hồi nếu request đi qua app.

Ví dụ, AWS S3 URL yêu cầu hiệu lực 60 phút nhưng được ký bằng temporary role credentials còn 20 phút thì link chỉ hoạt động tối đa đến khi credentials hết hạn. Đặt expiry 7 ngày không kéo dài session role lên 7 ngày.

### 3.3. Đồng hồ và thời gian bắt đầu

Cloud signer và storage service dựa vào thời gian UTC. Đồng hồ máy signer lệch có thể khiến URL chưa có hiệu lực hoặc hết hạn sớm.

- Đồng bộ thời gian bằng NTP trên node/VM.
- Dùng UTC/Instant trong Java.
- Không lấy thời gian từ browser để quyết định expiry.
- Nếu cần start time, cân nhắc clock skew nhỏ theo hướng dẫn provider.
- Không đặt start time quá xa trong quá khứ vì nó mở rộng cửa sổ sử dụng.
- Kiểm thử boundary tại thời điểm ngay trước, đúng lúc và sau expiry.

### 3.4. Thời hạn tối đa theo provider

| Provider | Mốc quan trọng |
| --- | --- |
| Amazon S3 | SigV4 presigned URL qua SDK/CLI có thể đặt tối đa 7 ngày; nếu dùng temporary credentials thì URL hết hiệu lực khi credentials hết hạn hoặc bị thu hồi sớm hơn |
| Azure Storage | User delegation SAS có thời hạn tối đa 7 ngày; account SAS/service SAS có quy tắc khác và chịu cấu hình account/policy |
| Google Cloud Storage | V4 signed URL tối đa 604800 giây (7 ngày); chữ ký dựa trên key/signing identity và có thể mất hiệu lực sớm nếu key bị rotate |

Không nên lấy mức tối đa làm TTL mặc định. Với chia sẻ cho con người, vài phút hoặc vài giờ thường phù hợp hơn nhiều ngày.

## 4. Giới hạn phạm vi tài nguyên và hành động

### 4.1. Chỉ định một resource cụ thể

Một share grant nên chỉ rõ:

- Bucket/container.
- Object key hoặc blob name.
- Object version/generation nếu nghiệp vụ cần cố định phiên bản.
- HTTP method được phép: GET, PUT hoặc HEAD.
- Content type và checksum nếu upload.
- Response disposition nếu cần download thay vì inline.
- Tenant và business object ID.
- Thời gian bắt đầu/hết hạn.

Tránh tạo link cho cả bucket/container nếu người nhận chỉ cần một file. Không đưa prefix rộng vào URL nếu không có yêu cầu thực tế.

### 4.2. Chỉ cấp permission cần thiết

| Use case | Permission |
| --- | --- |
| Tải file | GET/read |
| Upload file mới | PUT/create/write cho một object |
| Xem metadata | HEAD/read properties nếu cần |
| Xóa file | DELETE chỉ khi nghiệp vụ yêu cầu rõ |
| Liệt kê bucket/container | Không cấp cho link tải một file |
| Ghi đè object hiện hữu | Tránh nếu không cần; dùng object key ngẫu nhiên hoặc điều kiện tạo mới |

Một URL upload không nên đồng thời cho phép đọc, xóa và liệt kê. Một URL download không nên được ký cho PUT/DELETE.

### 4.3. Giới hạn request upload

Khi tạo link upload:

- Sinh object key phía server; không để client chọn key tùy ý.
- Ràng buộc HTTP method và Content-Type/header cần thiết vào chữ ký.
- Kiểm tra checksum hoặc integrity header nếu provider hỗ trợ.
- Kiểm tra kích thước file sau upload trước khi chuyển sang trạng thái chính thức.
- Quét malware/content type theo pipeline phù hợp.
- Dùng quarantine prefix/container cho file chưa kiểm tra.
- Ngăn ghi đè object đã có bằng unique key hoặc precondition nếu dịch vụ hỗ trợ.
- Không cấp quyền list/delete.

Một số signed PUT không thể biểu diễn đầy đủ policy kích thước như form upload có policy. Nếu cần giới hạn kích thước cứng trước khi lưu, dùng presigned POST policy (AWS), proxy upload qua backend hoặc cơ chế upload có policy tương đương; đừng giả định chỉ ký URL PUT là đủ.

### 4.4. Ràng buộc người nhận

Signed URL thuần thường không gắn với email/người nhận cụ thể. Bất kỳ ai có link đều có thể dùng. Nếu cần ràng buộc người nhận:

1. Người nhận mở application share link.
2. Ứng dụng yêu cầu đăng nhập hoặc OTP tới kênh đã xác minh.
3. Server kiểm tra recipient, tenant, expiry, revoke và permission.
4. Server stream file hoặc tạo signed URL mới với TTL rất ngắn.
5. Audit sự kiện cấp link và tải file.

OTP cần rate limit, thời hạn ngắn, chống brute-force và không log giá trị. Không dùng email address do client gửi mỗi lần truy cập làm bằng chứng danh tính.

### 4.5. Ràng buộc mạng và thiết bị

Một số provider cho phép hạn chế IP/range hoặc endpoint:

- Azure SAS có thể hỗ trợ signed IP range và protocol HTTPS.
- AWS IAM/bucket policy có thể giới hạn aws:SourceIp, aws:SourceVpc hoặc aws:SourceVpce theo kịch bản.
- GCP signed URL thường không phải công cụ ràng buộc người dùng theo IP; cân nhắc proxy/application gateway nếu cần.

IP restriction có thể gây lỗi cho mobile, NAT hoặc mạng đối tác thay đổi. Chỉ áp dụng khi có yêu cầu vận hành rõ và đã kiểm thử.

## 5. Application share-link service trong Spring Boot

### 5.1. Tách share grant khỏi signed URL

Một kiến trúc linh hoạt lưu metadata của quyền chia sẻ trong database. Signed URL chỉ được tạo khi người nhận thực sự cần truy cập:

~~~mermaid
sequenceDiagram
    participant Owner as Owner
    participant API as Spring Boot
    participant DB as Share Grant DB
    participant Signer as Cloud signer
    participant Recipient as Recipient
    Owner->>API: POST /shares
    API->>API: Authenticate + authorize object
    API->>DB: Save grant (token hash, scope, expiry)
    API-->>Owner: Share link
    Recipient->>API: GET /shares/{token}
    API->>DB: Validate expiry, revoke, recipient, usage
    API->>Signer: Sign exact object/method for short TTL
    Signer-->>API: Short-lived signed URL
    API-->>Recipient: Redirect or stream
~~~

Không lưu URL cloud đầy đủ trong database nếu không cần. URL chứa chữ ký là credential; lưu lại làm tăng bề mặt rò rỉ. Lưu grant ID, resource, permission, expiry, signer reference và audit metadata.

### 5.2. Schema gợi ý

~~~sql
CREATE TABLE share_grant (
    id UUID PRIMARY KEY,
    token_hash BYTEA NOT NULL UNIQUE,
    tenant_id UUID NOT NULL,
    resource_type VARCHAR(40) NOT NULL,
    resource_id UUID NOT NULL,
    object_key VARCHAR(1024) NOT NULL,
    permission VARCHAR(16) NOT NULL,
    recipient_hash BYTEA,
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    max_uses INTEGER,
    use_count INTEGER NOT NULL DEFAULT 0,
    require_recipient_auth BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

Bảng chỉ minh họa. Có thể tách audit event sang bảng riêng; không lưu raw token, signed URL, OTP hoặc access token. Hash token được tạo từ token ngẫu nhiên entropy cao, không phải hash password yếu.

### 5.3. Tạo token ngẫu nhiên an toàn

Dùng CSPRNG để tạo token có entropy cao, ví dụ 32 byte ngẫu nhiên rồi encode URL-safe Base64:

~~~java
@Component
public class ShareTokenGenerator {
    private final SecureRandom secureRandom = new SecureRandom();

    public String generate() {
        byte[] bytes = new byte[32];
        secureRandom.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
~~~

32 byte tương đương 256 bit entropy trước encoding. Không dùng UUID v4 làm secret token nếu muốn có entropy tối đa; UUID vẫn hữu ích làm ID công khai nhưng nên tách khỏi token bí mật.

Hash token để lưu:

~~~java
public byte[] sha256(String token) throws GeneralSecurityException {
    MessageDigest digest = MessageDigest.getInstance("SHA-256");
    return digest.digest(token.getBytes(StandardCharsets.US_ASCII));
}
~~~

Vì token ngẫu nhiên đủ entropy, SHA-256 phù hợp để tra cứu hash mà không cần password KDF chậm. Với password do con người chọn, phải dùng password hashing chuyên dụng; không áp dụng cùng cách này.

### 5.4. Kiểm tra grant ở server

Mỗi lần truy cập cần xác minh:

- Token đúng và chưa hết hạn.
- Grant chưa bị revoke.
- Resource vẫn tồn tại và owner/tenant còn hợp lệ.
- Permission phù hợp với request.
- Recipient đã xác thực nếu grant yêu cầu.
- Usage quota chưa vượt giới hạn.
- Resource classification cho phép chia sẻ ra ngoài.
- Không có legal hold hoặc trạng thái nghiệp vụ cấm tải.

Không chỉ kiểm tra token một lần khi tạo link. Quyền của owner hoặc trạng thái tài liệu có thể thay đổi trước khi người nhận sử dụng.

### 5.5. Atomic one-time use

Nếu ứng dụng yêu cầu một lần sử dụng, cập nhật trạng thái phải atomic. Ví dụ SQL:

~~~sql
UPDATE share_grant
SET use_count = use_count + 1
WHERE token_hash = :tokenHash
  AND revoked_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP
  AND (max_uses IS NULL OR use_count < max_uses)
RETURNING id, tenant_id, resource_id, object_key, permission;
~~~

Trong transaction, chỉ request cập nhật thành công mới được phép tiếp tục. Không làm kiểu đọc use_count, kiểm tra trong Java rồi update riêng vì hai request đồng thời có thể cùng vượt qua điều kiện.

**Lưu ý:** nếu server redirect người nhận tới một presigned URL còn hiệu lực 10 phút, người nhận có thể dùng URL cloud đó nhiều lần trong 10 phút. Việc consume application token một lần không biến signed URL thành one-time URL. Nếu cần one-time thực sự, backend phải proxy/stream nội dung và kiểm soát mỗi request, hoặc dùng một cơ chế storage có semantics one-time được hỗ trợ.

### 5.6. Thời hạn grant và signed URL

Có hai mốc thời gian:

- Thời điểm application share link hết quyền.
- Thời điểm URL trực tiếp tới cloud hết quyền.

Khi tạo signed URL, chọn expiry là giá trị nhỏ hơn giữa TTL cấu hình và thời gian còn lại của grant:

~~~java
Instant signedExpiry = min(
        clock.instant().plus(configuredSignedUrlTtl),
        grant.expiresAt());
~~~

Không phát signed URL có thời hạn dài hơn grant gốc. Nếu người nhận được cấp signed URL rồi grant bị revoke, URL trực tiếp có thể vẫn hoạt động tới expiry nếu provider không có revoke riêng; vì vậy dùng TTL ngắn hoặc proxy cho yêu cầu revoke tức thời.

## 6. Tạo AWS S3 presigned URL

### 6.1. Cơ chế

S3 presigned URL ký một request gồm bucket, object key, HTTP method, thời gian hết hạn và các thành phần request đã ký. Quyền của URL bị giới hạn bởi quyền của IAM principal ký URL và các bucket/access point policy áp dụng.

- Người nhận không cần AWS credentials.
- URL có thể được sử dụng nhiều lần cho tới khi hết hạn.
- URL không vượt quá quyền của principal ký.
- Với temporary credentials, URL hết hạn khi credentials hết hạn, kể cả expiry khai báo dài hơn.
- AWS SDK/CLI SigV4 cho phép tối đa 7 ngày; không nên dùng mức này làm mặc định.

### 6.2. Spring Boot với AWS SDK for Java 2.x

Ví dụ tạo URL GET cho một object:

~~~java
@Service
public class S3ShareUrlService {
    private final S3Presigner presigner;

    public S3ShareUrlService(S3Presigner presigner) {
        this.presigner = presigner;
    }

    public URL createDownloadUrl(String bucket, String objectKey) {
        Duration ttl = Duration.ofMinutes(10);

        GetObjectRequest getRequest = GetObjectRequest.builder()
                .bucket(bucket)
                .key(objectKey)
                .responseContentDisposition("attachment")
                .build();

        GetObjectPresignRequest presignRequest =
                GetObjectPresignRequest.builder()
                        .signatureDuration(ttl)
                        .getObjectRequest(getRequest)
                        .build();

        return presigner.presignGetObject(presignRequest).url();
    }
}
~~~

Đoạn code cần dependency AWS SDK S3 và module presigner phù hợp. S3Presigner nên được cấu hình bằng default credential provider chain để workload dùng IAM role/temporary credentials; không nhúng access key vào source code.

### 6.3. Presigned PUT và upload

Ví dụ ký PUT:

~~~java
PutObjectRequest putRequest = PutObjectRequest.builder()
        .bucket(bucket)
        .key(serverGeneratedObjectKey)
        .contentType("application/pdf")
        .build();

PutObjectPresignRequest presignRequest =
        PutObjectPresignRequest.builder()
                .signatureDuration(Duration.ofMinutes(10))
                .putObjectRequest(putRequest)
                .build();

PresignedPutObjectRequest signed =
        presigner.presignPutObject(presignRequest);

URL uploadUrl = signed.url();
Map<String, List<String>> requiredHeaders = signed.signedHeaders();
~~~

Client phải gửi đúng method và các signed header theo kết quả signer. Không ký quyền list bucket hoặc delete object khi chỉ cần upload một file. Với upload lớn hoặc cần policy kích thước/content type chặt, đánh giá S3 presigned POST policy hoặc upload proxy.

### 6.4. Siết tuổi chữ ký và thu hồi

Có thể dùng bucket policy với condition key s3:signatureAge để từ chối presigned request có chữ ký cũ hơn ngưỡng, ví dụ 10 phút:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyOldPresignedRequests",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": "arn:aws:s3:::example-bucket/shared/*",
      "Condition": {
        "NumericGreaterThan": {
          "s3:signatureAge": 600000
        }
      }
    }
  ]
}
~~~

Giá trị là milliseconds. Policy này là guardrail ở bucket/access point; cần kiểm thử phạm vi resource và tác động tới ứng dụng. Nó có thể chặn URL trước expiry đã ghi trong query nhưng không kéo dài URL.

Không có API thu hồi một presigned URL riêng lẻ. Các cách chặn có phạm vi rộng hơn gồm:

- Disable/revoke credentials hoặc session đã ký URL.
- Thay đổi IAM/bucket policy để deny resource hoặc request.
- Xóa/di chuyển object hoặc thay đổi quyền truy cập.
- Áp dụng s3:signatureAge để giới hạn tuổi chữ ký.

Các cách này có thể ảnh hưởng nhiều URL hoặc workload cùng dùng credential/policy. Thiết kế link ngắn hạn và cấp lại khi cần thường dễ vận hành hơn.

### 6.5. Hạn chế và audit

- Không gửi URL vào log hoặc chat.
- Chỉ cho phép signer role truy cập bucket/prefix cần thiết.
- Có thể audit request và xác định IAM principal/role session ký URL qua log phù hợp.
- Với upload, object cùng key có thể bị thay thế; dùng key riêng cho từng lần upload và kiểm tra object sau upload.
- Download bắt đầu trước expiry có thể tiếp tục; retry sau expiry có thể thất bại.
- Presigned URL vẫn chịu các policy network/IP/VPC endpoint được áp dụng.

## 7. Tạo Azure Storage SAS

### 7.1. Chọn đúng loại SAS

Azure Storage có ba loại chính:

| Loại | Cách ký | Phạm vi |
| --- | --- | --- |
| User delegation SAS | User delegation key dựa trên Microsoft Entra credentials | Resource được hỗ trợ, khuyến nghị cho Blob Storage |
| Service SAS | Storage account key | Một storage service/resource |
| Account SAS | Storage account key | Một hoặc nhiều storage service và một số service-level operation |

Microsoft khuyến nghị **user delegation SAS** cho nhiều kịch bản Blob Storage vì dựa trên Microsoft Entra credentials thay cho account key. Hạn chế quyền người tạo SAS và không phát account SAS rộng nếu chỉ cần một blob.

### 7.2. Tạo user delegation SAS trong Java

Ví dụ khái niệm với Azure Storage Blob SDK:

~~~java
BlobServiceClient blobServiceClient = new BlobServiceClientBuilder()
        .endpoint(storageEndpoint)
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildClient();

Instant now = Instant.now();
OffsetDateTime startsOn = OffsetDateTime.ofInstant(
        now.minus(Duration.ofMinutes(5)), ZoneOffset.UTC);
OffsetDateTime expiresOn = OffsetDateTime.ofInstant(
        now.plus(Duration.ofMinutes(10)), ZoneOffset.UTC);

UserDelegationKey delegationKey =
        blobServiceClient.getUserDelegationKey(startsOn, expiresOn);

BlobSasPermission permission = new BlobSasPermission()
        .setReadPermission(true);

BlobServiceSasSignatureValues values =
        new BlobServiceSasSignatureValues(expiresOn, permission)
                .setStartTime(startsOn)
                .setProtocol(SasProtocol.HTTPS_ONLY);

BlobClient blobClient = blobServiceClient
        .getBlobContainerClient(containerName)
        .getBlobClient(blobName);

String sas = blobClient.generateUserDelegationSas(
        values, delegationKey);

URI shareUri = URI.create(blobClient.getBlobUrl() + "?" + sas);
~~~

Tên constructor/method có thể khác nhẹ theo version Azure Storage SDK for Java; dùng Azure SDK BOM đồng bộ. Identity tạo delegation key cần quyền data-plane phù hợp để lấy user delegation key và tạo SAS. Người dùng SAS không cần nhận Entra token của ứng dụng.

### 7.3. Chỉ cấp permission và resource cần thiết

Permission SAS có các ký tự như read, add, create, write, delete, list tùy loại resource. Với link tải blob, chỉ cấp read. Không cấp write/delete/list nếu use case không cần.

- Giới hạn blob/container đúng phạm vi.
- Chọn protocol HTTPS only.
- Thiết lập expiry ngắn.
- Dùng IP range khi recipient có địa chỉ ổn định và policy yêu cầu.
- Không cấp permission rộng cho account SAS.
- Dùng user delegation SAS thay cho account-key SAS khi phù hợp.

### 7.4. Expiration policy và thu hồi

Storage account có thể cấu hình SAS expiration policy để khuyến nghị hoặc chặn SAS vượt quá khoảng thời gian cho phép. Có hai action:

- **Log:** cho phép request nhưng ghi nhận SAS ngoài policy khi diagnostic logging được cấu hình.
- **Block:** từ chối request ngoài policy.

User delegation SAS có giới hạn tối đa 7 ngày; user delegation key có expiry riêng và nếu key hết hạn thì SAS được ký bằng key đó cũng mất hiệu lực. Stored access policy không hỗ trợ user delegation SAS hoặc account SAS.

Với service SAS gắn stored access policy, có thể revoke bằng cách xóa hoặc thay đổi policy được tham chiếu. Ad hoc service SAS không gắn policy thường chỉ có thể thu hồi tức thời bằng cách regenerate account key đã ký nó, tác động tới các ứng dụng khác cùng dùng key đó. User delegation SAS không có stored access policy; thu hồi phụ thuộc user delegation key/identity và các biện pháp chặn resource.

**Không giả định mọi SAS đều có cùng cơ chế revoke.** Lưu loại SAS, key/policy reference và cách thu hồi dự kiến trong thiết kế.

### 7.5. Vận hành an toàn

- Bật Azure Storage diagnostic logs để điều tra request dùng SAS.
- Hạn chế quyền tạo SAS; thao tác tạo SAS không phải lúc nào cũng có audit event riêng dễ truy vết như một API thông thường.
- Cân nhắc disallow Shared Key authorization nếu workload không còn cần service/account SAS.
- Không lưu SAS query string trong application log.
- Khi SAS bị lộ, xác định loại SAS và key/policy đã ký để chọn cách thu hồi phù hợp.
- Dùng Entra ID/Managed Identity cho ứng dụng server-to-server; chỉ phát SAS khi cần delegated access cho client bên ngoài.

## 8. Tạo Google Cloud Storage signed URL

### 8.1. Cơ chế

GCS signed URL chứa chữ ký và query parameters xác định credential, thời gian, method/header và object. Ai có URL đều có thể thực hiện request trong thời gian hiệu lực, không cần Google account riêng.

Một số điểm cần nhớ:

- V4 signed URL có thời hạn tối đa 604800 giây (7 ngày).
- Signed URL chỉ dùng truy cập Cloud Storage qua XML API endpoints.
- Quyền của signer phải đủ để thực hiện thao tác.
- URL có thể bị vô hiệu hóa sớm nếu signing key bị rotate hoặc identity/permission liên quan bị thay đổi.
- Header đã ký phải được gửi đúng khi dùng URL.

### 8.2. Tạo signed URL với Java client

Ví dụ GET:

~~~java
Storage storage = StorageOptions.getDefaultInstance().getService();

BlobInfo blobInfo = BlobInfo.newBuilder(bucketName, objectName).build();

URL signedUrl = storage.signUrl(
        blobInfo,
        10,
        TimeUnit.MINUTES,
        Storage.SignUrlOption.withV4Signature(),
        Storage.SignUrlOption.httpMethod(HttpMethod.GET));
~~~

Ví dụ này minh họa API Java Cloud Storage client. Môi trường chạy cần có signer phù hợp, thường là service account identity với quyền ký qua IAM Credentials API hoặc cơ chế key được tổ chức phê duyệt. Tránh lưu service account private key JSON trong container.

### 8.3. Signed upload URL

Với upload, chỉ định method PUT và ràng buộc Content-Type/header nếu client library hỗ trợ:

~~~java
URL uploadUrl = storage.signUrl(
        blobInfo,
        10,
        TimeUnit.MINUTES,
        Storage.SignUrlOption.withV4Signature(),
        Storage.SignUrlOption.httpMethod(HttpMethod.PUT),
        Storage.SignUrlOption.withContentType());
~~~

Client phải gửi Content-Type đã ký. Có thể cần signed headers khác cho checksum hoặc precondition. Kiểm tra object sau upload, giới hạn size/content type bằng pipeline xác minh hoặc dùng signed policy document khi cần policy upload linh hoạt hơn.

### 8.4. Thu hồi và key rotation

GCS signed URL không có thao tác revoke riêng cho từng URL. Các cách giảm quyền gồm:

- Chờ URL hết hạn.
- Rotate/revoke signing key hoặc service account key có liên quan.
- Thay đổi quyền signer hoặc quyền truy cập object.
- Xóa/di chuyển object hoặc áp dụng policy chặn request.

Các cách này có phạm vi rộng và có thể ảnh hưởng signed URL khác. Với quyền cần revoke tức thời theo từng share, dùng application share link/proxy để kiểm tra grant trước mỗi lần tải.

## 9. OAuth access token và token chia sẻ

### 9.1. Access token phải có scope và audience

Access token cần giới hạn:

- Issuer tin cậy.
- Subject/client được đại diện.
- Audience là resource server được phép nhận token.
- Thời điểm hết hạn và thời điểm bắt đầu hiệu lực.
- Scope/permission được phép.
- Token ID nếu cần theo dõi/revoke theo kiến trúc.

Không tự tin tưởng claim chỉ vì token là JWT. Resource server phải xác minh chữ ký, issuer, audience, thời hạn và thuật toán theo cấu hình tin cậy. Nếu dùng opaque token, resource server có thể introspect với authorization server.

### 9.2. Đặt bearer token trong Authorization header

Đúng:

~~~http
GET /api/documents/123 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
~~~

Không dùng:

~~~text
https://api.example.com/documents/123?access_token=...
~~~

Token trong query string dễ xuất hiện trong browser history, proxy/access log, analytics, copied link và Referer. URL query cũng có thể bị ghi lại bởi hệ thống quan sát dù request được bảo vệ bằng HTTPS.

### 9.3. Spring Security Resource Server

Ví dụ cấu hình JWT resource server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
~~~

Bảo vệ endpoint:

~~~java
@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('SCOPE_document:read')")
    public DocumentView get(@PathVariable UUID id) {
        return documentService.readAuthorized(id);
    }
}
~~~

Authority mapping phụ thuộc claim và converter được cấu hình. issuer-uri không tự đảm bảo mọi scope mapping phù hợp; cần xác minh audience và quyền của API theo chính sách hệ thống. Không dùng cùng một access token cho nhiều audience không liên quan.

### 9.4. Refresh token

Refresh token thường có tuổi thọ dài hơn access token và quyền cấp access token mới. Vì vậy:

- Lưu refresh token an toàn ở client; với browser, cân nhắc Backend-for-Frontend và cookie HttpOnly/Secure/SameSite theo threat model.
- Dùng rotation/one-time use nếu authorization server hỗ trợ.
- Phát hiện reuse và revoke token family theo cơ chế provider.
- Không đưa refresh token vào URL, log hoặc analytics.
- Thu hồi khi logout, đổi mật khẩu, phát hiện compromise hoặc kết thúc phiên theo policy.

## 10. Thu hồi và xử lý khi link/token bị lộ

### 10.1. Ma trận thu hồi

| Loại | Thu hồi một link cụ thể | Biện pháp thực tế |
| --- | --- | --- |
| Application share token | Có | Đánh dấu grant revoked; mọi request tiếp theo bị app từ chối |
| AWS S3 presigned URL | Không trực tiếp | Revoke signing credentials/session, deny bằng bucket policy, chặn object hoặc giới hạn signature age |
| Azure service SAS có stored access policy | Có thể qua policy | Xóa/thay stored access policy; xác minh các SAS cùng policy |
| Azure ad hoc service/account SAS | Không trực tiếp | Regenerate account key đã ký hoặc chặn resource; có thể ảnh hưởng nhiều workload |
| Azure user delegation SAS | Không có stored policy | Thu hồi/disable delegation key hoặc identity theo khả năng, chặn resource, chờ expiry |
| GCS signed URL | Không trực tiếp | Rotate signing key/identity hoặc chặn object/resource, chờ expiry |
| OAuth opaque token | Có thể nếu introspection/revocation hỗ trợ | Revoke tại authorization server |
| JWT self-contained | Không mặc định có revoke tức thời | TTL ngắn, denylist token ID, token version hoặc introspection/gateway policy |

### 10.2. Incident response

Khi nghi link bị lộ:

1. Xác định loại credential: application token, S3 URL, SAS, GCS URL hay OAuth token.
2. Xác định resource, method, expiry, signer, tenant và recipient dự kiến.
3. Thu hồi grant ở application layer nếu có.
4. Dùng cơ chế revoke/policy/resource của provider phù hợp.
5. Nếu cần, tạm chặn object/prefix hoặc ngừng share API.
6. Kiểm tra access log, IP, user agent, thời gian, số lần tải và request bất thường.
7. Đánh giá dữ liệu đã tải xuống; thu hồi URL không xóa bản copy của người đã tải.
8. Rotate credential/key nếu có nguy cơ compromise.
9. Cấp link mới với scope/TTL hẹp hơn sau khi xác minh owner và recipient.
10. Ghi incident, nguyên nhân và cải tiến guardrail.

Không khẳng định đã thu hồi được dữ liệu đã tải xuống. Thu hồi link chỉ ngăn truy cập tương lai theo cơ chế provider/app.

### 10.3. Thu hồi theo từng grant bằng proxy

Nếu cần revoke từng share ngay, để mọi request đi qua share service:

~~~text
GET https://share.example.com/s/{opaque-token}
             |
             v
Check grant status + recipient + expiry
             |
             +---- revoked/expired -> 404/410
             |
             +---- allowed -> stream from storage
~~~

Proxy giữ quyền kiểm soát ở mỗi request, nhưng tăng bandwidth, latency và chi phí backend. Có thể dùng gateway/CDN có authorization callback nếu hỗ trợ. Nếu proxy chỉ redirect tới signed URL, URL cloud vẫn có thể được dùng lại tới expiry; không coi redirect là revoke tức thời.

## 11. Bảo vệ URL và token khỏi rò rỉ

### 11.1. Không log toàn bộ URL

Signed URL chứa signature và các query credential. Application share token đặt ở path cũng là credential; không ghi full URL, raw token hoặc request target vào:

- Application log.
- Reverse proxy/access log.
- APM/tracing span.
- Analytics event.
- Error report.
- Support ticket hoặc chat.
- Audit event.

Thay bằng metadata an toàn:

~~~json
{
  "event": "share_url_issued",
  "shareId": "sh_8a7f...",
  "resourceRef": "doc_204",
  "permission": "READ",
  "expiresAt": "2026-11-24T10:30:00Z",
  "actorRef": "user_91"
}
~~~

Không ghi token hash nếu không cần; token hash vẫn là dữ liệu nhạy cảm có thể hỗ trợ correlation hoặc offline guessing nếu token entropy yếu. Dùng opaque grant ID trong audit.

### 11.2. Browser và Referer

Nếu trang có chứa signed URL hoặc redirect tới tài nguyên chia sẻ:

- Dùng HTTPS.
- Đặt Referrer-Policy là no-referrer trên trang chia sẻ.
- Tránh tải third-party analytics, font, image hoặc script trên trang có token trong URL.
- Không nhúng signed URL vào HTML có thể bị cache công khai.
- Dùng Cache-Control là no-store cho trang cấp link và response chứa credential.
- Không để URL xuất hiện trong client-side error telemetry.
- Xóa query string khỏi access log hoặc redact các tham số signature.

Referrer-Policy giảm rò URL qua Referer nhưng không xóa browser history hoặc ngăn người dùng copy link. Token vẫn phải có TTL và scope hẹp.

### 11.3. Email, chat và clipboard

- Chỉ gửi link qua kênh đã xác minh recipient.
- Tránh gửi link trong mailing list hoặc ticket công khai.
- Không đưa URL vào subject line.
- Nếu link nhạy cảm, gửi thông báo riêng và yêu cầu người nhận đăng nhập/OTP.
- Không log nội dung clipboard hoặc URL trong telemetry.
- Có thể gửi application share link thay vì cloud signed URL để kiểm tra recipient và revoke.

### 11.4. CORS không phải authorization

CORS kiểm soát browser JavaScript từ origin nào được đọc response. CORS không ngăn người dùng copy signed URL sang curl, browser khác hoặc server. Không dùng CORS như biện pháp thu hồi hoặc xác thực người giữ URL.

## 12. Kiểm thử và quan sát

### 12.1. Test ma trận thời gian

| Test | Kết quả mong đợi |
| --- | --- |
| Request trước start time | Bị từ chối |
| Request trong TTL | Thành công nếu mọi policy cho phép |
| Request ngay sau expiry | Bị từ chối |
| Temporary credentials hết hạn trước URL | Bị từ chối từ lúc credential hết hạn |
| URL bị revoke/policy deny | Request mới bị từ chối |
| Download bắt đầu sát expiry | Hành vi theo provider; retry sau expiry phải kiểm tra riêng |
| Clock lệch | Test phát hiện start/expiry boundary bất thường |

Dùng Clock có thể inject trong Spring service để test thời gian mà không phải chờ thật.

### 12.2. Test phạm vi và quyền

- GET link không dùng được cho PUT/DELETE.
- Link object A không truy cập object B.
- Link của tenant A không truy cập tenant B.
- Link read không thể list container/bucket.
- Upload link không thể overwrite object khác.
- Signed header/content type sai bị từ chối.
- User không có quyền owner không tạo share.
- Recipient không đúng bị app từ chối nếu grant ràng buộc recipient.

### 12.3. Test replay và one-time

- Gọi cùng signed URL nhiều lần để xác nhận hành vi provider (thường là có thể dùng lại).
- Gọi application one-time token đồng thời từ hai request; chỉ một request được consume.
- Nếu app redirect sang signed URL, test URL đích có thể replay tới expiry.
- Nếu yêu cầu one-time thực sự, kiểm tra proxy stream từ storage và không trả credential trực tiếp.

### 12.4. Test revoke

- Revoke application grant rồi gọi lại link.
- Xóa stored access policy của service SAS và xác minh kết quả.
- Thử bucket policy s3:signatureAge với URL cũ.
- Thử signer credential bị disable trong môi trường test.
- Thử GCS signing key rotation trên test bucket.
- Xác minh các biện pháp rộng không làm gián đoạn workload không liên quan.

### 12.5. Audit và metrics

Theo dõi:

- Số share link được tạo theo actor, tenant và resource classification.
- TTL trung bình và số link vượt policy.
- Lượt truy cập thành công/thất bại, IP và user agent theo privacy policy.
- Số lần revoke, expiry và recipient verification failure.
- Upload vượt size/type/checksum.
- Access sau revoke hoặc sau expiry.
- Các request bất thường từ nhiều IP/region hoặc tần suất cao.

Không đưa raw URL, SAS token, signature, bearer token hoặc plaintext object metadata nhạy cảm vào metrics/log.

## 13. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| URL vừa tạo đã 403 | Credential signer hết hạn, start time/clock skew hoặc thiếu permission | Kiểm tra signer identity, UTC, policy và resource |
| URL hết hạn sớm hơn cấu hình | Temporary credentials/session hết hạn trước | Dùng session phù hợp hoặc TTL URL ngắn hơn |
| S3 URL bị từ chối sau vài phút | Bucket policy s3:signatureAge hoặc policy network | Kiểm tra policy guardrail và signer |
| S3 URL GET dùng được nhiều lần | Đây là hành vi bình thường của presigned URL | Dùng application proxy nếu cần one-time |
| Azure SAS không thể revoke qua stored policy | Có thể là user delegation SAS/account SAS hoặc SAS không gắn policy | Xác định SAS type và dùng cơ chế revoke đúng |
| Azure SAS hết hạn nhưng key delegation còn hiệu lực | SAS expiry và user delegation key expiry là hai mốc khác nhau | Kiểm tra cả hai mốc và policy account |
| GCS signed URL 403 | Signer thiếu quyền, signed header sai, hết hạn hoặc endpoint không đúng | Kiểm tra identity, canonical request, XML API và expiry |
| OAuth API nhận token từ query string | Client đang dùng sai cách truyền token | Chuyển sang Authorization header |
| Link bị lộ trong log | Query string được log nguyên vẹn | Redact ở app/proxy/APM trước khi lưu |
| Link bị dùng sau khi owner revoke | Signed URL trực tiếp còn hiệu lực tới expiry | Dùng proxy/revoke provider credential hoặc policy/resource |
| One-time link vẫn tải lại được | App redirect tới signed URL reusable | Proxy/stream và consume grant ở mỗi request |
| Người nhận không mở được link | TTL quá ngắn, mạng chậm hoặc required headers thiếu | Điều chỉnh TTL, cung cấp header và cơ chế cấp lại an toàn |

## 14. Bài tập thực hành tổng hợp

**document-service** cho phép chủ tài liệu chia sẻ hợp đồng PDF với đối tác trong 10 phút. Người nhận không có cloud identity. Chủ tài liệu có thể thu hồi link ngay. Một số tài liệu Restricted phải yêu cầu OTP trước khi tải.

**Nhiệm vụ:**

1. Thiết kế bảng share_grant lưu hash token, tenant, resource, permission, expiry, recipient và revoke state.
2. Tạo token ngẫu nhiên 256 bit và chỉ lưu SHA-256 hash.
3. Kiểm tra quyền owner và classification trước khi tạo share.
4. Chọn một provider và tạo signed GET URL chỉ cho một object với TTL ngắn.
5. Giải thích giới hạn revoke của presigned URL/SAS/signed URL theo provider.
6. Thiết kế proxy download để revoke từng grant và enforce one-time use nếu cần.
7. Thêm OTP/login cho tài liệu Restricted.
8. Bảo vệ URL khỏi log, trace, browser referrer, analytics và ticket.
9. Viết test expiry, wrong method, wrong object, replay, revoke và concurrent one-time consume.
10. Viết incident runbook khi link bị chuyển tiếp ra ngoài.

**Câu hỏi tự đánh giá:**

- Vì sao signed URL là bearer credential?
- Presigned URL S3 có tự động dùng được một lần không?
- Vì sao temporary AWS credentials có thể làm URL hết hạn trước expiry đã cấu hình?
- Azure user delegation SAS khác service SAS ở đâu?
- Stored access policy có áp dụng cho mọi loại SAS không?
- GCS V4 signed URL có thời hạn tối đa bao lâu và dùng API endpoint nào?
- Vì sao không đặt OAuth access token trong query string?
- Khi redirect tới signed URL, application one-time token có bảo đảm one-time download không?
- CORS có thể ngăn người khác dùng URL đã bị copy không?
- Khi cần revoke từng link tức thời, kiến trúc nào phù hợp?
- Vì sao không thể thu hồi dữ liệu mà recipient đã tải về?

**Đáp án định hướng:** người giữ link có thể dùng quyền trong chữ ký; S3 presigned URL có thể dùng nhiều lần tới expiry; temporary credentials có expiry riêng; user delegation SAS dựa trên Entra credentials còn service SAS dùng account key; stored access policy chỉ hỗ trợ service SAS; GCS V4 tối đa 604800 giây và chỉ Cloud Storage XML API; bearer token phải gửi trong Authorization header; redirect vẫn để lộ URL cloud reusable; CORS không phải authorization; proxy/application grant kiểm tra từng request cho phép revoke; dữ liệu đã tải về nằm ngoài quyền kiểm soát của link.

## 15. Tài liệu tham khảo chính thức

- [AWS S3 – Download and upload objects with presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html): signer permissions, expiration, temporary credentials, replay và giới hạn URL.
- [AWS – Additional guardrails for presigned URLs](https://docs.aws.amazon.com/prescriptive-guidance/latest/presigned-url-best-practices/additional-guardrails.html): dùng s3:signatureAge để siết tuổi chữ ký và các giới hạn guardrail.
- [Azure Storage – Grant limited access with SAS](https://learn.microsoft.com/en-us/azure/storage/common/storage-sas-overview): user delegation/service/account SAS, permission và stored access policy.
- [Azure Storage – SAS expiration policy](https://learn.microsoft.com/en-us/azure/storage/common/sas-expiration-policy): giới hạn thời hạn SAS, Log/Block action và user delegation key.
- [Azure Storage REST – Create a service SAS](https://learn.microsoft.com/en-us/rest/api/storageservices/create-service-sas): lifetime và cách thu hồi SAS theo stored access policy/account key.
- [Google Cloud Storage – Signed URLs](https://docs.cloud.google.com/storage/docs/access-control/signed-urls): bearer behavior, XML API, expiry và signer.
- [Google Cloud – Create signatures](https://docs.cloud.google.com/storage/docs/authentication/creating-signatures): signing identity và key rotation.
- [RFC 6750 – OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền bearer token bằng Authorization header, TLS và không đặt token trong URL.
- [RFC 9700 – OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ token, audience, sender constraints và refresh token.
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): cấu hình issuer, xác minh JWT và authority mapping.

**Ghi nhớ:** một link chia sẻ an toàn phải có **TTL ngắn, resource cụ thể, method/permission tối thiểu, signer có quyền hẹp và kế hoạch revoke**. Signed URL trực tiếp thường là bearer link có thể replay; nếu cần kiểm soát recipient, thu hồi từng link hoặc one-time use, hãy để Spring Boot kiểm tra grant trên mỗi request và chỉ cấp quyền storage trong khoảng thời gian thật ngắn.
