# Che thông tin nhạy cảm trong khóa, giá trị, log và dấu vết của Spring Data Redis

## 1. Một key Redis cũng có thể là dữ liệu nhạy cảm

Khi tích hợp Redis với ứng dụng Spring Boot, developer thường tập trung bảo vệ password kết nối hoặc mã hóa đường truyền. Nhưng thông tin nhạy cảm có thể xuất hiện ngay cả khi kết nối đã dùng TLS và Redis đã bật ACL.

Ví dụ một ứng dụng cache hồ sơ khách hàng bằng key:

```text
customer:email:alice.nguyen@example.org
```

Payload có thể là một object JSON chứa địa chỉ và số điện thoại. Service ghi log mỗi lần cache miss:

```text
Cache miss for key customer:email:alice.nguyen@example.org
```

Tracing tự động tạo một Redis span gắn command và key, trong khi một nhân viên vận hành dùng `MONITOR` để điều tra latency. Lúc này cùng một địa chỉ email có thể tồn tại trong **Redis keyspace, log tập trung, trace backend, ticket sự cố và các bản sao lưu**.

Ngay cả khi xóa cache key, dữ liệu đã được đưa vào log hoặc trace có thể còn tồn tại theo retention riêng của từng hệ thống.

> Nguyên tắc trung tâm: **Đừng đặt thông tin nhạy cảm vào Redis, key name, metric label, log hoặc trace nếu ứng dụng không thực sự cần nó.** Bảo vệ mật khẩu Redis là cần thiết nhưng không thay thế thiết kế bảo mật dữ liệu.

Bài này giải thích cách giảm rò rỉ tại bốn bề mặt chính:

1. **Tên khóa và field/index:** dữ liệu nào bị lộ qua key names, channel names và metadata.
2. **Giá trị Redis:** dữ liệu nào tồn tại trong String, Hash, Stream, Set, cache entries, snapshot và backup.
3. **Log:** điều gì được ứng dụng, driver, Redis server hoặc hệ thống vận hành ghi lại.
4. **Dấu vết phân tán (*distributed traces*) và metrics:** thông tin nào bị đưa vào span attributes, events, baggage, exemplars hoặc labels.

Mục tiêu không chỉ là thay email bằng chuỗi `***` ở log cuối cùng. Một giải pháp tốt giảm dữ liệu ngay từ thiết kế và kiểm soát từng điểm mà dữ liệu đi qua.

## 2. Xác định dữ liệu nhạy cảm trong ngữ cảnh Redis

Thông tin nhạy cảm phụ thuộc miền nghiệp vụ, nhưng có thể bắt đầu từ những nhóm sau:

| Nhóm | Ví dụ | Rủi ro nếu lộ |
|---|---|---|
| Định danh cá nhân | Email, điện thoại, địa chỉ, số giấy tờ | Nhận diện và liên hệ người dùng |
| Bí mật xác thực | Password, API key, bearer token, refresh token, OTP | Truy cập trái phép |
| Dữ liệu tài chính | Thẻ thanh toán, số tài khoản, thông tin giao dịch | Gian lận, mất quyền riêng tư |
| Hồ sơ riêng tư | Dữ liệu sức khỏe, nội dung cá nhân, vị trí | Tiết lộ đời sống cá nhân |
| Định danh nội bộ có khả năng liên kết | User ID, tenant ID, session ID, order ID | Theo dõi/correlation, lộ hoạt động |
| Dữ liệu kinh doanh | Giá riêng khách hàng, chiết khấu, kế hoạch nội bộ | Rò rỉ thông tin thương mại |
| Credential hạ tầng | Redis URI, password, private key, certificate key | Chiếm quyền hệ thống |
| Nội dung event | Payload Stream/Pub/Sub và DLQ | Sao chép thông tin nghiệp vụ sang nhiều hệ thống |

Không phải mọi ID đều bí mật ở cùng mức độ. Tuy nhiên, một ID tưởng như "vô hại" có thể trở thành dữ liệu nhạy cảm nếu có thể đối chiếu với khách hàng hoặc sử dụng làm token truy cập.

### 2.1. Phân loại theo hậu quả

Một nhóm phát triển có thể ghi rõ cho từng dữ liệu:

- **Public:** có thể hiển thị cho người không xác thực.
- **Internal:** chỉ nên dùng trong nội bộ ứng dụng.
- **Confidential:** phải giới hạn người đọc và các kênh truyền.
- **Secret:** nếu lộ có thể cấp quyền hoặc gây tổn thất trực tiếp.

Đây là **ví dụ mô hình phân loại**, không phải một tiêu chuẩn bắt buộc cho mọi doanh nghiệp. Quy tắc thực sự cần lấy từ policy của tổ chức và các nghĩa vụ pháp lý liên quan.

### 2.2. Hãy kiểm tra bề mặt dữ liệu, không chỉ class Java

Một field như `Customer.email` có thể được đưa vào:

```text
Customer.email
   ├─ @Cacheable SpEL key="#email"
   ├─ Redis String key name
   ├─ Redis Hash field / secondary index
   ├─ JSON object cached value
   ├─ Stream record / Pub/Sub message
   ├─ Logger.debug("customer={}", customer)
   ├─ Exception.getMessage()
   ├─ OpenTelemetry span attribute
   ├─ Micrometer tag customer_id=...
   ├─ SLOWLOG / MONITOR khi bật quan sát lệnh
   └─ RDB/AOF, replica và backup
```

Một tính năng có thể rất an toàn ở HTTP layer nhưng lại rò qua các kênh vận hành này.

## 3. Phân tích threat model: ai có thể nhìn thấy gì?

Không phải tất cả người có quyền đọc Redis data node đều có quyền đọc log, và cũng không phải ai truy cập Grafana đều có quyền xem raw payload.

| Bề mặt | Ai có thể nhìn thấy | Dữ liệu có thể lộ | Kiểm soát |
|---|---|---|---|
| Redis key names | User Redis có quyền đọc/list phù hợp, vận hành | Email/ID/token được nhúng vào key | Key naming và ACL |
| Redis values | Client có quyền GET/HGET/XRANGE... | JSON, token, hồ sơ | Tối thiểu hóa, ACL, encryption |
| Redis Pub/Sub | Subscriber được phép subscribe | Channel và message body | Channel ACL, không gửi secret |
| Redis Streams | Consumer/reader, exporter, backup | Event fields, payload và DLQ | Schema, retention, ACL |
| Application log | Developer, support, log backend | Key, value, exception, user context | Redaction tại nguồn, RBAC, retention |
| Tracing backend | Người có quyền xem trace | Span attributes, db statement, exception | Attribute allowlist, sampling |
| Metrics backend | Người xem dashboards | Tags, cardinality, correlation IDs | Low-cardinality tag policy |
| Redis MONITOR | Operator có quyền lệnh | Redis commands và arguments được giám sát | Least privilege, runbook |
| Persistence/backup | Backup service, operator, storage admin | Dataset và metadata | Encryption, access, retention |
| Memory dump / diagnostic | Operator, crash collector | Secret có thể tồn tại trong bộ nhớ | Quy trình thu thập hạn chế |

Một key name trông không nhạy cảm nhưng chứa ID nội bộ cũng có thể giúp người xem log liên kết nhiều hành động của cùng một tài khoản. **Pseudonymization không đồng nghĩa anonymization tuyệt đối**: mã giả ổn định vẫn có thể dùng để liên kết các bản ghi.

### 3.1. Bảo vệ ở nhiều lớp

- **Application design:** quyết định có cần lưu dữ liệu không và lưu dạng nào.
- **Application security:** kiểm tra tenant, authorization, input validation và serializer.
- **Redis security:** TLS, ACL, topology, backup permissions.
- **Observability security:** log/trace/tag allowlist, sampling, quyền truy cập và retention.
- **Operations:** incident response, debug procedures, secret rotation.

Nếu ứng dụng tự ghi bearer token vào log, TLS giữa Spring và Redis **không thể sửa được** lỗi ấy.

## 4. Đừng đặt email, token hoặc thông tin cá nhân trực tiếp trong key

### 4.1. Những mẫu key không an toàn

```text
user:alice@example.org:profile
phone:+84123456789:otp
session:eyJhbGciOi...:state
reset-password:raw-reset-token
customer:123456789:medical-history
search:nguyen van a 0912345678:results
```

Chúng có thể xuất hiện trong:

- `SCAN`, `KEYS` và các công cụ khám phá keyspace.
- `MONITOR`/diagnostic và lệnh được log.
- Keyspace notifications khi key hết hạn.
- Một số exception hoặc debug statement.
- Backup, RDB/AOF và các công cụ phân tích.
- Redis Cluster hash tags nếu nhúng identifier.
- Dashboard/metric labels nếu ứng dụng xuất key dưới dạng tag.

Ngay cả khi payload đã mã hóa, **key name vẫn có thể lộ danh tính hoặc mối quan hệ nghiệp vụ**.

### 4.2. Thiết kế key có prefix chức năng và identifier an toàn

Thay vì:

```text
profile:alice@example.org
```

có thể dùng:

```text
customer:profile:v2:yZgtK5H3eC0y...
```

Ở đây phần cuối là **định danh suy ra bằng HMAC với secret** hoặc một random ID không liên kết trực tiếp với PII. Prefix cho biết namespace và schema version, không chứa dữ liệu cá nhân.

Một mẫu key tốt thường có:

```text
<domain>:<purpose>:<schema-version>:<opaque-id>
```

Ví dụ:

```text
customer:profile:v2:<opaque-id>
auth:session:v1:<opaque-id>
rate-limit:account:v3:<opaque-id>
cache:product-summary:v4:<opaque-id>
```

**Opaque ID không tự nhiên an toàn nếu có thể đảo hoặc đoán trực tiếp.** Mã hóa Base64 của email là encoding, không phải bảo mật. Hash SHA-256 của số điện thoại hoặc email cũng có thể bị dictionary attack vì không gian đầu vào dễ đoán.

## 5. Hash, HMAC, mã hóa và random ID khác nhau thế nào?

| Cách tạo ID | Tính chất | Khi phù hợp | Giới hạn |
|---|---|---|---|
| Raw email/phone | Dễ đối chiếu | Chỉ trong tầng đã cho phép đọc PII | Lộ trực tiếp |
| Base64(email) | Có thể giải mã ngay | Encoding/transport | **Không che dữ liệu** |
| SHA-256(email) | Không lưu plaintext | Fingerprint dữ liệu entropy cao | Email/phone dễ đoán offline |
| HMAC-SHA-256(secret, canonical ID) | Deterministic, khó kiểm tra giả thuyết nếu không biết secret | Lookup key ổn định mà tránh raw PII | Vẫn có khả năng liên kết qua cùng digest |
| Random UUID/ULID | Không suy ra PII từ ID nếu sinh đủ ngẫu nhiên | Khi có mapping ở nguồn khác | Phải lưu mapping và quản lý vòng đời |
| Encryption (AEAD) | Có thể giải mã khi có key | Payload cần lấy lại chính xác | Cần key management/nonce/rotation |

### 5.1. Tại sao hash không khóa dễ bị đoán?

Giả sử key chứa:

```text
customer:email-sha256:<sha256(email)>
```

Kẻ tấn công biết một tập email phổ biến có thể tính SHA-256 cho từng email, đối chiếu với digest quan sát được và xác định chủ thể. Điều này không cần giải ngược hàm hash.

Với HMAC, việc thử một email giả thuyết đòi hỏi **secret HMAC**. Tuy nhiên nếu secret bị lộ, khả năng kiểm tra giả thuyết quay trở lại; HMAC output cũng vẫn là một identifier có thể dùng để theo dõi.

### 5.2. Không coi HMAC ID là authorization token

HMAC key name là cách che định danh, **không phải chứng minh người gọi có quyền đọc dữ liệu**. Một client có quyền rộng vào Redis vẫn có thể đọc value của key mà nó nhìn thấy.

Luôn kiểm tra quyền dựa trên tenant/user/role ở business layer, đồng thời hạn chế Redis ACL theo service. Không dùng một digest "khó đoán" thay thế authorization.

## 6. Ví dụ Java tạo Redis key bằng HMAC-SHA-256

Một factory tạo key ổn định cho cặp tenant/customer. Nó không lưu raw ID vào tên key.

```java
package com.example.security.redis;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class PrivateRedisKeyFactory {

    private static final String ALGORITHM = "HmacSHA256";
    private final byte[] hmacSecret;

    public PrivateRedisKeyFactory(
            @Value("${app.redis.keys.hmac-secret-base64}")
            String secretBase64) {

        this.hmacSecret = Base64.getDecoder()
                .decode(secretBase64);

        if (hmacSecret.length < 32) {
            throw new IllegalArgumentException(
                    "HMAC key material is too short"
            );
        }
    }

    public String customerProfileKey(
            String tenantId,
            String customerId) {

        if (tenantId == null || tenantId.isBlank()
                || customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                    "tenantId and customerId are required"
            );
        }

        // Length-prefix tránh nhập nhằng giữa hai thành phần.
        String canonical =
                tenantId.length() + ":" + tenantId
                + customerId.length() + ":" + customerId;

        byte[] digest = hmac(canonical);

        return "customer:profile:v2:"
                + Base64.getUrlEncoder()
                        .withoutPadding()
                        .encodeToString(digest);
    }

    private byte[] hmac(String input) {
        try {
            // Tạo Mac mới mỗi lần: Mac không mặc định thread-safe.
            Mac mac = Mac.getInstance(ALGORITHM);
            mac.init(new SecretKeySpec(
                    hmacSecret, ALGORITHM));

            return mac.doFinal(
                    input.getBytes(StandardCharsets.UTF_8));
        } catch (GeneralSecurityException ex) {
            // Không đưa identifier hoặc secret vào exception.
            throw new IllegalStateException(
                    "Cannot derive Redis cache identifier"
            );
        }
    }
}
```

Ý nghĩa thiết kế:

- `tenantId` và `customerId` đi vào HMAC để hai tenant không vô tình dùng chung key.
- `HmacSHA256` dùng secret thay vì raw hash.
- Input phải được **canonicalize nhất quán** giữa các phiên bản service; nếu email không phân biệt hoa/thường theo chính sách của ứng dụng, hãy chuẩn hóa ở domain layer theo quy tắc được duyệt.
- Prefix `v2` là một version độc lập giúp triển khai thay đổi định dạng/HMAC key; nó không tự quản lý việc di trú dữ liệu.
- Secret phải được inject từ secret manager hoặc cơ chế deployment bảo mật. Ví dụ property chỉ định tên cấu hình; không commit key thực vào source.
- Tránh log `canonical`, `customerId` hoặc digest đầy đủ khi không cần; digest ổn định vẫn là dữ liệu có thể liên kết.

**Lưu ý về HMAC rotation:** đổi secret tạo ra key mới cho cùng customer, nên cache cũ có thể bị bỏ lại tới TTL hoặc cần migration. Nếu dùng Redis làm nguồn dữ liệu không thể tái tạo, việc đổi key bí mật mà không có kế hoạch tìm/migrate key cũ có thể dẫn tới mất khả năng truy cập dữ liệu.

### 6.1. HMAC không bảo vệ value

Key:

```text
customer:profile:v2:<hmac-digest>
```

không còn chứa email plaintext, nhưng value có thể vẫn là:

```json
{"email":"alice@example.org","phone":"+84000000000"}
```

Ai được quyền đọc value vẫn nhìn thấy dữ liệu. Phải áp dụng **data minimization, authorization và encryption khi yêu cầu** cho phần value độc lập với việc che key.

## 7. Spring Cache: @Cacheable có thể vô tình biến tham số thành key

Ví dụ dễ viết nhưng có rủi ro:

```java
@Cacheable(cacheNames = "customerProfiles", key = "#email")
public CustomerProfile findByEmail(String email) {
    return repository.findByEmail(email);
}
```

Nếu RedisCacheManager dùng tên cache làm prefix và String key serializer, Redis key có thể chứa email:

```text
customerProfiles::alice@example.org
```

Rủi ro không chỉ đến từ SpEL. Nếu để key generation mặc định, Spring Cache có thể dựa trên các method arguments và `toString()`/serializer của chúng. Một object tham số chứa email/phone có thể bị đưa vào Redis key representation theo cấu hình.

### 7.1. Dùng KeyGenerator sinh key an toàn

```java
package com.example.security.redis;

import java.lang.reflect.Method;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class PrivateCacheKeyConfiguration {

    @Bean("privateCustomerKeyGenerator")
    public KeyGenerator privateCustomerKeyGenerator(
            PrivateRedisKeyFactory factory) {

        return (Object target, Method method, Object... params) -> {
            if (params.length != 2
                    || !(params[0] instanceof String tenant)
                    || !(params[1] instanceof String customerId)) {
                throw new IllegalArgumentException(
                        "Unexpected private cache key arguments"
                );
            }

            return factory.customerProfileKey(
                    tenant, customerId);
        };
    }
}
```

Sau đó:

```java
@Service
public class CustomerProfileQueryService {

    private final CustomerRepository repository;

    public CustomerProfileQueryService(
            CustomerRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
            cacheNames = "customerProfiles",
            keyGenerator = "privateCustomerKeyGenerator"
    )
    public CustomerProfile find(
            String tenantId, String customerId) {

        // Authorization/tenant scope cần được thực hiện
        // tại ranh giới dịch vụ phù hợp.
        return repository.findForTenant(
                tenantId, customerId);
    }
}
```

Đây là mô hình minh họa trong đó method nhận đúng hai String arguments theo thứ tự đã định. Các kiểu `CustomerRepository` và `CustomerProfile` là domain types của ứng dụng.

Khi chọn key generator chung cho nhiều method, cần đưa **method identity/cache region** vào input HMAC nếu có nguy cơ các methods khác nhau sinh cùng khóa. Trong ví dụ, `customerProfiles` và key factory dành riêng cho một loại lookup giúp giới hạn phạm vi.

### 7.2. Một cache key đúng chưa đủ để chống truy cập chéo tenant

Nếu cache key không chứa hoặc không suy ra tenant, hai tenant có cùng customer ID có thể bị trùng key. Nếu authorization chỉ được thực hiện **bên trong method `@Cacheable`**, khi cache hit Spring có thể **không gọi method** và bỏ qua bước kiểm tra đó.

Vì vậy:

- Thực hiện authorization ở lớp được gọi trước khi cache interception trả dữ liệu, ví dụ service facade/security boundary hoặc method security được cấu hình đúng thứ tự.
- Dùng tenant identity được xác thực, không tùy tiện tin một header do client khai báo.
- Đưa tenant vào key derivation.
- Thử nghiệm truy cập chéo tenant với cache hit và cache miss.
- Không xem opaque key là một cơ chế phân quyền.

## 8. Key names xuất hiện trong nhiều nơi khó nhận thấy

Ngay cả khi service không log key, một key chứa PII vẫn có thể bị lộ qua:

### 8.1. Keyspace notifications

Ví dụ Redis keyevent expired:

```text
Channel: __keyevent@0__:expired
Message: session:alice@example.org
```

Body chứa tên key đã hết hạn. Subscriber hợp lệ sẽ nhận toàn bộ chuỗi tên key, không chỉ phần prefix. Tắt logging trong application chính chưa xóa nguy cơ nếu keyspace notifications được bật cho ứng dụng khác.

### 8.2. SCAN, KEYS và Redis Insight / admin tooling

```redis
SCAN 0 MATCH customer:* COUNT 100
```

Kết quả có thể tiết lộ toàn bộ pattern key. Vì vậy không đặt email, số điện thoại, token hoặc password trong key names kể cả khi ứng dụng chỉ có quyền đọc một key cụ thể.

`SCAN` tránh một số vấn đề của `KEYS` trên dataset lớn nhưng **không tạo lớp bảo mật**; một user đủ quyền vẫn có thể xem tên các key phù hợp.

### 8.3. Redis Cluster hash tags

Ví dụ:

```text
profile:{alice@example.org}:data
profile:{alice@example.org}:settings
```

Hash tag làm hai key cùng slot, nhưng cũng đưa email vào key. Một lựa chọn ít lộ hơn là dùng digest HMAC hoặc opaque group identifier theo thiết kế phân vùng:

```text
profile:{hmac-opaque-identifier}:data
profile:{hmac-opaque-identifier}:settings
```

Đừng gom mọi key vào một hash tag chung như `{all}` chỉ để che thông tin; điều đó có thể tạo hotspot một slot trong Redis Cluster.

### 8.4. Redis command arguments và URI

Khi Redis client gửi `GET key`, tên key nằm trong Redis command argument. Nếu người có quyền phù hợp ghi nhận commands qua các công cụ debug, key có thể xuất hiện ở tầng vận hành, bất kể application log đã được redact.

Bài học: **che tại cấu trúc dữ liệu**, không chỉ che lúc render log.

## 9. Giảm dữ liệu trong Redis value trước khi nghĩ đến mã hóa

Lưu toàn bộ entity Java bằng JSON rất tiện, nhưng một cache endpoint có thể chỉ cần vài trường.

Ví dụ object:

```json
{
  "customerId": "c-42",
  "displayName": "A. Nguyen",
  "email": "alice@example.org",
  "phone": "+84000000000",
  "address": "...",
  "accountSecret": "REDACTED_EXAMPLE",
  "marketingSegment": "standard"
}
```

Nếu endpoint chỉ cần `displayName` và `marketingSegment`, cache cả `accountSecret` và `address` sẽ tăng bề mặt tấn công mà không mang lại lợi ích.

Một thiết kế an toàn hơn là **DTO projection**:

```java
public record CustomerCardCacheValue(
        String displayName,
        String marketingSegment,
        long profileVersion
) {}
```

Chỉ cache các field được phép và cần để đáp ứng request. Bản dữ liệu đầy đủ nên nằm ở nơi có access controls, retention và encryption phù hợp.

### 9.1. @JsonIgnore không phải chính sách bảo mật tổng quát

`@JsonIgnore` có thể giúp loại field khỏi một đường JSON serialization sử dụng Jackson, nhưng:

- Serializer khác có thể không tôn trọng annotation đó.
- Redis Hash mapping của Repository không nhất thiết dùng cùng đường Jackson.
- Logging `toString()` có thể vẫn in field.
- Một code path khác có thể lưu trực tiếp String payload.
- Tracing có thể ghi arguments riêng.
- Một object không được cache chưa chắc không bị đưa vào Stream/DLQ.

Nên định nghĩa **kiểu dữ liệu cache riêng**, kèm kiểm thử field được serialize, thay vì kỳ vọng một annotation chặn mọi con đường rò rỉ.

### 9.2. TTL không phải cơ chế xóa sạch mọi bản sao

`EXPIRE` hoặc `@TimeToLive` có thể xóa key khỏi Redis sau thời hạn, nhưng dữ liệu có thể còn ở:

- Replica đã nhận write trước đó.
- RDB/AOF hoặc snapshot/backup trong cửa sổ lưu giữ.
- Log, traces hoặc hệ thống support.
- DLQ, event archive hoặc một Redis key bản sao.
- Crash dump hay công cụ chẩn đoán đã thu thập từ trước.

TTL hỗ trợ **giảm thời gian tồn tại trên live Redis**, không đồng nghĩa thực hiện một yêu cầu xóa dữ liệu ở mọi nơi trong hệ thống. Retention policy phải bao trùm các bản sao phù hợp.

## 10. Mã hóa Redis value: phân biệt TLS và application encryption

Ba cơ chế dễ bị nhầm:

| Cơ chế | Bảo vệ | Không bảo vệ |
|---|---|---|
| TLS giữa Spring và Redis | Dữ liệu trên đường truyền | Người có quyền đọc plaintext tại Redis/client |
| Encryption at rest phía hạ tầng | Dữ liệu ở storage media/snapshot theo phạm vi provider | Redis command readers, process memory, nhiều công cụ vận hành |
| Application-level encryption trước khi SET | Nội dung value khi người đọc Redis không có key giải mã | Key names, metadata, kích thước/tần suất, dữ liệu trước encrypt ở app |

Nếu một yêu cầu bảo mật đặt mục tiêu **không cho người chỉ có quyền đọc Redis nhìn thấy PII plaintext**, mã hóa ở ứng dụng trước khi lưu có thể là một thành phần phù hợp. Nó không thể một mình giải quyết access control hoặc leakage qua key names.

### 10.1. AEAD thay vì encryption không kiểm tra toàn vẹn

Khi mã hóa payload, cần bảo vệ cả **tính bí mật** và **tính toàn vẹn**. Một lựa chọn phổ biến trong Java là `AES/GCM/NoPadding`:

- Dùng AES key có đủ entropy, lưu ở secret manager/KMS.
- Tạo nonce/IV **mới** cho mỗi lần encryption bằng CSPRNG.
- Không tái sử dụng nonce với cùng key.
- Dùng tag kiểm tra toàn vẹn, thường 128 bit.
- Gắn *Additional Authenticated Data (AAD)* như key name hoặc tenant context đã kiểm soát để chống việc di chuyển ciphertext sai ngữ cảnh.
- Ghi định dạng/version và quản lý key rotation.

**Không dùng AES/ECB**, không tự tạo thuật toán mã hóa, không tự tạo IV cố định và không copy key AES vào source code.

## 11. Ví dụ Java mã hóa String value bằng AES-GCM

Ví dụ sau chủ yếu minh họa format payload có version, nonce ngẫu nhiên và AAD. Production còn cần quản lý key version/KMS, giới hạn kích thước, lỗi/rotation và security review tương ứng.

```java
package com.example.security.redis;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class RedisValueProtector {

    private static final int FORMAT_VERSION = 1;
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    private final SecretKeySpec encryptionKey;
    private final SecureRandom random = new SecureRandom();

    public RedisValueProtector(
            @Value("${app.redis.values.aes-key-base64}")
            String base64Key) {

        byte[] keyBytes = Base64.getDecoder().decode(base64Key);

        if (keyBytes.length != 32) {
            throw new IllegalArgumentException(
                    "Expected 256-bit AES key"
            );
        }

        this.encryptionKey =
                new SecretKeySpec(keyBytes, "AES");
    }

    public String encrypt(String redisKey, String plaintext) {
        try {
            byte[] nonce = new byte[NONCE_BYTES];
            random.nextBytes(nonce);

            Cipher cipher =
                    Cipher.getInstance("AES/GCM/NoPadding");

            cipher.init(
                    Cipher.ENCRYPT_MODE,
                    encryptionKey,
                    new GCMParameterSpec(TAG_BITS, nonce)
            );

            // Buộc ciphertext gắn với đúng Redis key.
            cipher.updateAAD(
                    redisKey.getBytes(StandardCharsets.UTF_8)
            );

            byte[] ciphertext = cipher.doFinal(
                    plaintext.getBytes(StandardCharsets.UTF_8)
            );

            ByteBuffer payload = ByteBuffer.allocate(
                    1 + NONCE_BYTES + ciphertext.length
            );

            payload.put((byte) FORMAT_VERSION);
            payload.put(nonce);
            payload.put(ciphertext);

            return Base64.getEncoder()
                    .encodeToString(payload.array());

        } catch (GeneralSecurityException ex) {
            // Không log plaintext, secret hoặc raw payload.
            throw new IllegalStateException(
                    "Redis value encryption failed"
            );
        }
    }

    public String decrypt(String redisKey, String encoded) {
        try {
            byte[] bytes = Base64.getDecoder()
                    .decode(encoded);

            if (bytes.length < 1 + NONCE_BYTES + TAG_BITS / 8) {
                throw new IllegalArgumentException(
                        "Invalid encrypted payload"
                );
            }

            ByteBuffer payload = ByteBuffer.wrap(bytes);
            int version = Byte.toUnsignedInt(payload.get());

            if (version != FORMAT_VERSION) {
                throw new IllegalArgumentException(
                        "Unsupported encrypted payload version"
                );
            }

            byte[] nonce = new byte[NONCE_BYTES];
            payload.get(nonce);

            byte[] ciphertext = new byte[payload.remaining()];
            payload.get(ciphertext);

            Cipher cipher =
                    Cipher.getInstance("AES/GCM/NoPadding");

            cipher.init(
                    Cipher.DECRYPT_MODE,
                    encryptionKey,
                    new GCMParameterSpec(TAG_BITS, nonce)
            );

            cipher.updateAAD(
                    redisKey.getBytes(StandardCharsets.UTF_8)
            );

            byte[] plaintext = cipher.doFinal(ciphertext);

            return new String(
                    plaintext, StandardCharsets.UTF_8);

        } catch (GeneralSecurityException
                 | IllegalArgumentException ex) {
            // Không trả lỗi chứa ciphertext/key/PII.
            throw new IllegalStateException(
                    "Cannot read encrypted Redis value"
            );
        }
    }
}
```

Ví dụ sử dụng:

```java
String key = privateRedisKeyFactory
        .customerProfileKey(tenantId, customerId);

String encryptedValue =
        redisValueProtector.encrypt(key, jsonPayload);

stringRedisTemplate.opsForValue()
        .set(key, encryptedValue, Duration.ofMinutes(10));

String stored = stringRedisTemplate.opsForValue().get(key);

if (stored != null) {
    String json = redisValueProtector.decrypt(key, stored);
    // Chỉ deserialize và dùng tại authorized code path.
}
```

**Lưu ý triển khai:**

- Không đặt key AES hoặc key HMAC trong `application.yml` đã commit; cấu hình tên property trỏ tới secret do platform cấp.
- AES-GCM nonce 96 bit sinh ngẫu nhiên phù hợp nhiều mô hình nhưng phải đánh giá giới hạn số lần mã hóa với cùng key và chính sách rotation khi lưu lượng rất lớn.
- `redisKey` được dùng làm AAD nên đổi tên key hoặc chuyển ciphertext sang key khác sẽ làm decrypt thất bại có chủ đích. Migration phải decrypt/re-encrypt dưới context mới.
- Trường version trong ví dụ là **format version**, không thay thế key identifier cho rotation. Production thường cần version/key ID và bộ giải mã tương thích dữ liệu cũ.
- Đầu vào plaintext đang là Java `String` có thể nằm trong JVM memory; mã hóa trước Redis không tự giải quyết bảo vệ heap dumps hoặc logging trước khi encrypt.
- Mã hóa toàn bộ value làm Redis không thể trực tiếp thực hiện `INCR`, `HINCRBY` hoặc query/filter trên những trường plaintext. Cần chọn mô hình dữ liệu thích hợp.

Không copy ví dụ mật mã vào production mà bỏ qua threat modeling, key management và security review. Ưu tiên thư viện/mẫu mã hóa đã được tổ chức chấp thuận khi có.

## 12. Khi nào nên mã hóa toàn payload, từng field hoặc không lưu?

| Nhu cầu | Cách tiếp cận | Đánh đổi |
|---|---|---|
| Cache giá public, sản phẩm public | Không cần mã hóa từng value chỉ vì dùng Redis; vẫn dùng TLS/ACL | Ít overhead, không che data với người có quyền Redis |
| Cache hồ sơ có PII nhưng chỉ cần 2 field | DTO tối thiểu + HMAC key | Giảm dữ liệu hơn mã hóa toàn entity |
| Cache chứa field thật sự confidential | Field-level hoặc whole-value AEAD | Key management, tăng CPU/bytes |
| Cần Redis `INCR`/`HINCRBY` trên giá trị | Giữ counter không nhạy cảm hoặc đưa calculation sang lớp phù hợp | Không thể thao tác số học trực tiếp trên AES-GCM ciphertext |
| Cần tìm kiếm theo email | Token/HMAC index thiết kế riêng ở ranh giới domain | Equality/frequency leakage, rotation, index consistency |
| Cần tìm kiếm full-text trên dữ liệu riêng tư | Cân nhắc hệ tìm kiếm với security model phù hợp | Mã hóa toàn payload không hỗ trợ search trong Redis |
| Token/password không cần lưu bản gốc | Lưu fingerprint/hash chuyên biệt theo mục đích | Không thể lấy lại token, thường là điều mong muốn |
| Dữ liệu không cần cache | Không lưu vào Redis | Loại bỏ hoàn toàn bề mặt rò rỉ Redis |

**Không cần lưu thì không nên mã hóa rồi vẫn lưu.** Data minimization luôn là biện pháp giảm rủi ro mạnh mẽ.

### 12.1. Password và token không giống dữ liệu cần giải mã

Password của người dùng thường nên được xử lý bằng một password hashing scheme phù hợp (Argon2id/bcrypt/scrypt theo chính sách hệ thống), không đơn giản mã hóa để giải mã lại. Token ngẫu nhiên có thể được đối chiếu qua hash/HMAC tùy threat model và đặc điểm token.

Với refresh/access token có giá trị như bearer credential, việc nhúng raw token vào Redis key, log hoặc trace đặc biệt nguy hiểm. Cách bảo vệ phải xét khả năng token replay, thời gian sống, rotation và revocation.

### 12.2. Compression không phải encryption

`GZIP`, `LZ4` hoặc các cơ chế compression chỉ thu nhỏ payload. Người có dữ liệu vẫn có thể giải nén. Base64 hay Java serialization cũng **không** che thông tin. Không coi "Redis đọc không ra chữ ở CLI" là bằng chứng dữ liệu được bảo mật.

## 13. RedisCacheManager, serializer và dữ liệu được lưu thực tế

Spring Boot có thể tự tạo `RedisCacheManager` và `RedisTemplate` với serializer khác nhau. Một Java object được đặt vào cache có thể:

- Chuyển thành JSON với field names dễ đọc.
- Chuyển thành binary format khó đọc bằng mắt nhưng vẫn có thể decode.
- Chứa type metadata, class names hoặc thông tin domain bổ sung.
- Có nhiều key phụ do framework, index hoặc TTL logic.

### 13.1. Đừng giả định serializer che dữ liệu

Ví dụ:

```java
@Cacheable(cacheNames = "customerProfile")
public CustomerProfile findProfile(String customerId) {
    return repository.findById(customerId);
}
```

Nếu `CustomerProfile` chứa phone/address, Redis vẫn giữ dữ liệu đó theo serializer. Java serialization, JDK binary hoặc JSON không phải encryption.

Muốn cache một dạng an toàn hơn, tạo **projection DTO** và trả về từ method được cache. Nếu cần mã hóa, tích hợp serializer/protector đã được thiết kế và kiểm thử với `RedisCacheConfiguration` phù hợp.

### 13.2. Giá trị null, exception và negative caching

Một service có thể cache marker cho trường hợp không có khách hàng. Marker cũng không nên chứa input thô:

```text
customerNotFound:alice@example.org
```

Thay bằng opaque key và một value marker không tiết lộ PII. Lưu ý negative caching cần TTL ngắn và đúng ngữ nghĩa dữ liệu nguồn; nếu không, việc người dùng được tạo sau đó vẫn có thể bị hệ thống trả kết quả "không tồn tại" cũ.

Exception message chứa truy vấn tìm kiếm hoặc input của người dùng không nên được cache hoặc log nguyên văn theo cách không kiểm soát.

## 14. Redis Repository và các key phụ dễ bị bỏ qua

Spring Data Redis Repository với `@RedisHash`, `@Indexed`, `@TimeToLive` có thể tạo nhiều Redis keys và cấu trúc phụ để duy trì mapping/index.

Ví dụ entity:

```java
@RedisHash("customer")
public class CustomerEntity {
    @Id
    private String id;

    @Indexed
    private String email;
}
```

Các Redis key/Set hỗ trợ index có thể chứa **giá trị email** trong cách tổ chức index tùy framework/version. Vì vậy dùng HMAC chỉ ở primary ID nhưng vẫn khai báo `@Indexed email` có thể để lộ email ở secondary index.

Cần xem xét:

1. Những key chính do Repository tạo.
2. Những key và Set phụ do indexed fields tạo.
3. Phantom/shadow copies liên quan TTL.
4. Keyspace notifications và expired events chứa ID hoặc object.
5. Serializer cho Hash fields và values.
6. Cơ chế cleanup/rebuild index sau missed expiry notifications.

Nếu cần tìm theo email mà không muốn lưu raw email vào key/index, có thể lưu **deterministic HMAC lookup token** ở một field/index chuyên biệt, trong khi dữ liệu email thật được bảo vệ ở nơi phù hợp.

### 14.1. Equality leakage của deterministic token

Nếu cùng email luôn có cùng HMAC token:

- Người xem index có thể thấy các record trùng token.
- Có thể quan sát tần suất truy cập hoặc mối liên hệ.
- Khi biết secret và tập input, có thể đối chiếu.
- Rotation secret đòi rebuild/migration index.

Không mô tả deterministic HMAC index như một cơ chế ẩn danh hoàn toàn.

## 15. Logging an toàn: dùng allowlist thay vì cố sửa mọi String

Logging thường là nguồn rò rỉ nhanh nhất vì dữ liệu từ nhiều service được tập trung về một hệ thống và lưu lâu.

### 15.1. Những câu lệnh log không nên dùng

```java
log.debug("Redis GET key={}", redisKey);

log.info("Customer cache value: {}", customerProfile);

log.warn("Invalid input {}", requestBody);

log.error("Redis failed for email={} value={}",
        email, jsonPayload, exception);

log.trace("Redis connection {}", redisUri);

log.info("Received Stream event: {}", record.getValue());
```

Vì sao nguy hiểm:

- `redisKey` có thể chứa email/token.
- `CustomerProfile.toString()` có thể tự in toàn bộ fields.
- Request body có thể có password/OTP.
- `exception.getMessage()` hoặc stack trace có thể chứa command arguments/URI tùy thư viện.
- Redis URI có thể chứa credential.
- Stream event body có thể chứa PII hoặc thông tin tài chính.

Đừng mặc định bật log level `DEBUG`/`TRACE` chỉ trong thời gian ngắn sẽ an toàn: dữ liệu có thể đã được gửi sang backend với retention dài.

### 15.2. Log event type và trạng thái đã chuẩn hóa

Ví dụ an toàn hơn:

```java
package com.example.customer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class CustomerCacheObserver {

    private static final Logger log =
            LoggerFactory.getLogger(CustomerCacheObserver.class);

    public void cacheHit() {
        log.debug(
                "redis_cache_lookup cache={} result={}",
                "customerProfile",
                "hit"
        );
    }

    public void cacheMiss() {
        log.debug(
                "redis_cache_lookup cache={} result={}",
                "customerProfile",
                "miss"
        );
    }

    public void cacheFailure(RuntimeException failure) {
        // Không log key, value hoặc exception message
        // lên một kênh log không được phép chứa dữ liệu nhạy cảm.
        log.warn(
                "redis_cache_lookup_failed cache={} exceptionType={}",
                "customerProfile",
                failure.getClass().getSimpleName()
        );
    }
}
```

Ví dụ không nhằm cấm mọi stack trace: log exception đầy đủ có thể cần thiết trong một kênh chẩn đoán được kiểm soát, sau khi đã xác định framework/driver có thể đưa dữ liệu nhạy cảm vào throwable hay không. Với log chia sẻ rộng, cần ưu tiên **event code, trạng thái, latency và exception class** thay vì raw arguments.

### 15.3. Redact tại nguồn tốt hơn regex sau khi log

Một log collector có thể dùng regex để thay email/số điện thoại bằng `[REDACTED]`. Nhưng biện pháp đó có giới hạn:

- Không bắt được mọi định dạng dữ liệu hoặc secret.
- Dữ liệu có thể đi qua agent/file trước khi được redact.
- Một field khác vẫn chứa nguyên payload.
- Exception stack, object formatter hoặc nested JSON có thể vượt qua pattern.
- Hash/token/ID nội bộ không luôn có format dễ nhận diện.
- Thay đổi schema có thể làm bộ lọc cũ bỏ sót.

Cách an toàn hơn là **allowlist field được log ngay trong application**:

```text
Cho phép: eventType, cacheName, commandType, outcome,
           durationMs, service, environment, requestCorrelationId.

Không log mặc định: Redis key, value, request body,
                   access token, email, phone, query text,
                   exception message chưa đánh giá.
```

Bộ lọc ở log collector vẫn hữu ích như **lớp phòng vệ thứ hai**, không thay thế thiết kế tại nguồn.

## 16. Structured logging và correlation ID

Structured logs thường ở dạng JSON:

```json
{
  "event": "redis_cache_lookup",
  "cache": "customerProfile",
  "result": "miss",
  "duration_ms": 12,
  "trace_id": "generated-trace-id"
}
```

Ví dụ trên tránh nhúng email hoặc Redis key vào message. Để điều tra một request, log có thể giữ correlation ID không trực tiếp suy ra PII.

### 16.1. Không dùng email hoặc bearer token làm correlation ID

Sai:

```text
correlationId = request.getHeader("Authorization")
correlationId = customer.email()
traceId = user.phoneNumber()
```

Đúng hơn:

- Dùng trace ID do tracer sinh ngẫu nhiên.
- Dùng request ID do ứng dụng hoặc gateway tin cậy tạo theo chính sách.
- Kiểm tra format/length nếu chấp nhận ID từ header bên ngoài.
- Đừng để client đặt một chuỗi có newline hoặc JSON làm field log không được validate.

Nếu người dùng gửi một `X-Request-ID` tuỳ ý, ứng dụng nên giới hạn độ dài và ký tự cho phép hoặc thay bằng ID nội bộ. Một "opaque ID" do client cấp vẫn có thể chứa PII nếu không validate.

### 16.2. MDC phải được quản lý vòng đời

`MDC` có thể giúp gắn trace/request correlation vào log:

```java
try (var ignored = org.slf4j.MDC.putCloseable(
        "operation", "customerProfileLookup")) {
    log.info("redis_cache_lookup result={}", "hit");
}
```

MDC theo luồng có thể bị **rò context giữa request** trong thread pool nếu không được cleanup đúng cách. Với async/reactive pipelines, cần dùng cơ chế context propagation phù hợp framework thay vì tự giả định ThreadLocal luôn theo request.

Không đặt email, token, session ID hoặc toàn bộ security principal vào MDC vì mọi log trong luồng có thể vô tình mang dữ liệu đó.

## 17. Redis driver, exceptions và log cấu hình

Spring Data Redis thường sử dụng Lettuce hoặc Jedis. Dù application log không in key, driver/framework có thể có logging ở các mức khác nhau.

### 17.1. Cẩn thận khi bật TRACE/DEBUG để điều tra

Ví dụ cấu hình bình thường có thể giữ mức log driver ở WARN:

```yaml
logging:
  level:
    io.lettuce.core: WARN
    org.springframework.data.redis: WARN
```

Đây là **ví dụ giảm độ chi tiết**, không phải một cơ chế kiểm soát bảo mật hoàn chỉnh. Việc một driver/version có log raw command arguments hay không cần được xác nhận theo chính cấu hình và phiên bản triển khai.

Khi mở DEBUG/TRACE:

- Có chính sách thời gian bật ngắn và owner phê duyệt.
- Dùng môi trường thử nghiệm với synthetic data nếu có thể.
- Kiểm tra log sample trước khi bật trên production.
- Hạn chế người xem và thời gian retention.
- Thu hồi debug sau khi chẩn đoán.
- Không lưu credential trong connection URL hoặc command line.

**Mã hóa trên đường truyền không ngăn ứng dụng logging dữ liệu trước khi gửi.**

### 17.2. Exception có thể mang ngữ cảnh nhạy cảm

Một đoạn code:

```java
log.error("Failed to write {}", redisKey, ex);
```

lộ key trực tiếp. Nhưng ngay cả:

```java
log.error("Redis request failed", ex);
```

cũng cần đánh giá vì throwable message có thể chứa endpoint, command hoặc URI tùy lỗi/driver.

Không khuyến khích che mọi exception đến mức không thể vận hành. Thay vào đó:

1. Phân loại lỗi và gán error code an toàn.
2. Log ở kênh thường những trường cho phép.
3. Khi cần stack trace, dùng kênh diagnostic được bảo vệ, xem xét redaction và quyền truy cập.
4. Không đưa secret/PII vào exception message do ứng dụng tự tạo.
5. Gắn trace ID để tìm lại bối cảnh mà không cần log raw payload.

### 17.3. Log Redis URI có thể lộ password

Ví dụ connection URI dạng:

```text
redis://username:password@redis.internal:6379
```

Nếu cấu hình này bị đưa vào log, password có thể lộ. Tốt hơn dùng Spring Boot property binding kết hợp secret injection, không tự in toàn bộ configuration object hoặc environment.

`spring.data.redis.password` phải được cung cấp từ nguồn bí mật, không đưa vào status endpoint tự thiết kế. Dù Spring Boot Actuator có cơ chế sanitization cho một số property, **không nên mặc định mọi endpoint/custom actuator/log đều loại bỏ hết secret**.

## 18. Redis MONITOR và SLOWLOG là kênh chẩn đoán nhạy cảm

### 18.1. MONITOR

`MONITOR` cho phép một client đủ quyền quan sát luồng command được Redis server xử lý, phục vụ debug. Vì command arguments có thể chứa key và value, đây là bề mặt dễ lộ dữ liệu.

Ví dụ command ứng dụng:

```redis
SET session:alice@example.org "token-or-json-payload"
```

Một công cụ theo dõi command có thể thấy dữ liệu tương ứng, tùy Redis version và các cơ chế bảo vệ/lọc nhạy cảm của server. **Không coi cơ chế lọc một số command nhạy cảm của Redis là bảo đảm mọi key/value nghiệp vụ được che**.

Chỉ dùng `MONITOR` theo runbook, trên môi trường được phép, với thời gian ngắn, quyền admin tối thiểu và dữ liệu synthetic khi có thể. Lệnh này cũng có chi phí hiệu năng; không nên bật vô thời hạn như công cụ monitoring chính.

### 18.2. SLOWLOG

`SLOWLOG` ghi nhận thông tin về các command chậm theo tiêu chí server và các arguments liên quan, có các giới hạn/truncation theo cấu hình Redis. Một key chứa PII có thể xuất hiện trong bản ghi slowlog.

`SLOWLOG` đo thời gian Redis thực hiện command, không đo toàn bộ RTT của application, và **truncation không phải data masking**. Một argument bị cắt còn 128 byte vẫn có thể chứa trọn email/token.

Khi thu thập slowlog vào hệ thống log tập trung:

- Giới hạn quyền đọc slowlog.
- Giảm thông tin nhạy cảm trong key/value ngay từ ứng dụng.
- Đánh giá quy trình export/redact.
- Cấu hình retention phù hợp.
- Tránh đưa raw arguments vào dashboard công khai.

### 18.3. INFO, CLIENT LIST và endpoint chẩn đoán

Một số command quản trị có thể lộ metadata về kết nối, địa chỉ client, tên client hoặc thông tin topology. Đặt tên client bằng PII như `clientName=alice@example.org` là không phù hợp.

Tên client nên là service/instance identifier, ví dụ `catalog-service-pod-a3`, thay vì email hoặc access token.

## 19. Tracing: một span có thể làm lộ Redis key và payload

Distributed tracing giúp theo dõi request đi qua HTTP service, database, Redis và message broker. Nhưng span có thể chứa:

- `db.system`, `db.operation.name`, Redis command type.
- Statement hoặc command arguments tùy instrumentation.
- Span name do ứng dụng tự tạo.
- Error status/exception message và stack trace.
- HTTP request parameters/header nếu được capture.
- Baggage hoặc custom attributes được propagate qua service.
- Messaging payload attributes nếu app tự gắn.

Ví dụ rủi ro:

```java
Span.current().setAttribute(
        "redis.key", "profile:" + email);

Span.current().setAttribute(
        "redis.value", jsonPayload);
```

Khi trace được gửi tới tracing backend, thông tin đó có thể tồn tại ngoài Redis và ngoài log system.

### 19.1. Span metadata theo allowlist

Một span an toàn hơn mô tả **loại thao tác**, không phải đối tượng nhạy cảm:

```text
name: redis.customer-profile.lookup
attributes:
  db.system.name: redis
  db.operation.name: GET
  cache.name: customerProfile
  cache.result: miss
  service.name: customer-service
  app.tenant.tier: enterprise
```

Đừng tự đưa `customer.email`, `session.token`, full Redis key hoặc raw JSON vào span attributes. Ngay cả tenant ID cũng cần phân loại trước khi dùng làm attribute.

### 19.2. Ví dụ Micrometer Observation an toàn

```java
package com.example.customer;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class CustomerCacheMetrics {

    private final ObservationRegistry registry;

    public CustomerCacheMetrics(
            ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> T observeLookup(
            java.util.function.Supplier<T> action) {

        return Observation.createNotStarted(
                        "redis.customer.profile.lookup",
                        registry)
                .lowCardinalityKeyValue(
                        "cache.name", "customerProfile")
                .lowCardinalityKeyValue(
                        "operation", "lookup")
                .observe(action::get);
    }
}
```

Cách dùng:

```java
CustomerProfile result = customerCacheMetrics.observeLookup(
        () -> customerProfileService.find(tenantId, customerId)
);
```

Observation ở đây thêm tên thao tác và metadata allowlisted. Nó không tự chèn customer ID vào span. Tuy vậy, các instrumentation khác có thể thêm attributes; cần kiểm tra pipeline observability tổng thể.

### 19.3. Baggage và MDC có thể lan sang nhiều service

Baggage là thông tin có thể được truyền qua nhiều hop. Đừng đặt email, token hoặc hồ sơ khách hàng vào baggage để "dễ debug", vì nó có thể đi sang downstream và được ghi ở log/tracing của những service khác.

Dùng trace ID, request ID hoặc một opaque operation reference phù hợp. Đánh giá các header được propagate và nơi tracing exporter lưu dữ liệu.

### 19.4. Sampling không phải redaction

Sampling 1% có thể giảm số trace được lưu, nhưng **1% trace còn lại vẫn có thể chứa secret nguyên vẹn**. Mọi span được thu thập phải an toàn theo chính sách trước khi xét sampling.

## 20. Micrometer metrics và cardinality: không dùng key/ID làm tag

Một sai lầm:

```java
Counter.builder("redis.cache.miss")
        .tag("customerId", customerId)
        .tag("redisKey", redisKey)
        .register(meterRegistry)
        .increment();
```

Nếu có một triệu khách hàng, có thể có một triệu tổ hợp label. Ngoài nguy cơ tiết lộ identifier, điều này làm tăng chi phí memory/storage và khiến metrics backend khó vận hành.

Một cách khác:

```java
Counter.builder("redis.cache.miss")
        .tag("cache", "customerProfile")
        .tag("service", "customer-service")
        .register(meterRegistry)
        .increment();
```

**Low-cardinality labels** phù hợp:

- Tên nhóm cache đã biết trước.
- Tên loại Redis command (GET/SET/MGET...).
- Result (hit/miss/error).
- Environment/service.
- Nhóm lỗi đã chuẩn hóa.
- Tenant **tier** hoặc phân khúc đã được duyệt thay vì raw tenant ID.

**High-cardinality/sensitive labels** nên tránh:

- Redis key đầy đủ.
- Customer/user/session/order ID.
- Email, số điện thoại, token.
- Query string.
- Request/trace ID làm nhãn đại trà.
- Payload hash nếu có thể liên kết từng user.

Lưu ý: ngay cả HMAC digest không chứa plaintext vẫn có thể tạo high cardinality và cho phép theo dõi cá thể, nên **không tự động an toàn để dùng làm tag**.

## 21. Streams, Pub/Sub, keyspace notifications và DLQ cũng phải được che

Redis không chỉ lưu cache values.

### 21.1. Redis Streams

Một Stream event:

```redis
XADD events:orders * eventId evt-42 email alice@example.org type CREATED
```

lưu email trực tiếp trong entry field. Consumer, admin tooling, `XRANGE` và các bản backup có thể xem payload. Khi event xử lý lỗi được copy sang dead-letter stream, dữ liệu bị **nhân bản**.

Nếu downstream chỉ cần order ID, dùng:

```redis
XADD events:orders * eventId evt-42 orderRef order-42 type CREATED
```

và để consumer có quyền phù hợp tự lấy thông tin cần thiết từ nguồn dữ liệu bền vững.

Khi event thực sự phải mang PII, cần schema, retention, ACL, encryption và quyền consumer phù hợp. Đừng đưa raw payload vào `log.error("failed message {}", record)` khi handler lỗi.

### 21.2. Pub/Sub

Pub/Sub không lưu message để replay, nhưng người có quyền subscribe vẫn có thể đọc body của message khi đang online. Một channel:

```text
notify:customer:alice@example.org
```

lộ email trong channel name. Thay bằng channel theo loại sự kiện:

```text
notify:customer-updated
```

và gửi opaque reference hoặc payload đã được thiết kế an toàn. Channel ACL có thể giới hạn nhóm subscriber, nhưng **không thay thế việc tối thiểu hóa thông tin**.

### 21.3. Keyspace notifications

Khi bật `notify-keyspace-events`, event expired/delete có thể chứa tên key. Nếu Redis key đã được tạo từ email/token, việc subscribe `__keyevent@0__:expired` có thể trở thành một kênh phát tán PII.

Do đó:

- Thiết kế key an toàn **trước** khi bật keyspace notifications.
- Giới hạn ACL subscribe theo channel pattern.
- Không log mọi event body mặc định.
- Chấp nhận rằng Pub/Sub event có thể mất khi listener offline; không dùng event này để thực hiện công việc nhạy cảm bắt buộc nếu không có nguồn bền vững.

### 21.4. DLQ và retry payload

Một DLQ thường giữ message lỗi lâu hơn luồng thông thường để điều tra. Nếu DLQ copy nguyên request chứa secret, nó có thể có retention dài và nhiều người có quyền xem.

Nên lưu:

- Event ID/correlation ID.
- Event type và schema version.
- Error category/attempt count.
- Opaque reference tới payload ở nơi có quyền/retention thích hợp.
- Nội dung tối thiểu đủ cho replay.

Nếu cần full payload trong DLQ, áp dụng encryption/access control/retention và quy trình xóa rõ ràng.

## 22. TLS, Redis ACL và network isolation: bảo vệ truy cập nhưng không che dữ liệu

Một ứng dụng có thể cấu hình Redis TLS:

```yaml
spring:
  data:
    redis:
      ssl:
        enabled: true
      username: customer-cache-service
      password: ${REDIS_PASSWORD}
```

Đây là ví dụ Spring Boot hiện đại; property prefix và TLS options có thể thay đổi giữa phiên bản. Secret nên đến từ secret manager hoặc biến môi trường được quản lý, không lưu nguyên giá trị trong Git.

### 22.1. TLS

TLS bảo vệ dữ liệu **đang truyền** giữa ứng dụng và Redis trên các đoạn mạng được cấu hình. Nó không làm key/value trở thành unreadable đối với Redis server hoặc client đã được phép đọc.

Không bỏ kiểm tra certificate/hostname chỉ để giảm lỗi khi triển khai. Nếu dùng Redis Sentinel/Cluster, phải kiểm soát TLS trên các kết nối liên quan theo topology của provider.

### 22.2. ACL

Redis ACL có thể giới hạn user được gọi command nào, truy cập key pattern nào và dùng Pub/Sub channel nào theo khả năng phiên bản.

Ví dụ một user của cache customer không cần:

- `CONFIG SET`, `FLUSHALL` hoặc command quản trị toàn instance.
- `MONITOR`.
- Quyền đọc key của service khác.
- Quyền subscribe mọi channel.
- Quyền đọc/ghi một namespace secret không liên quan.

ACL phải phù hợp Redis commands thực tế của Spring Cache/Template/Repository; không chỉ cho `GET` nếu framework còn dùng `MGET`, `SET`, `DEL`, `SCAN` hoặc Lua.

### 22.3. Mã hóa ở ứng dụng bổ sung gì?

Nếu cần bảo vệ value ngay cả trước người chỉ có Redis read permission, application-level encryption có thể giúp. Nhưng nó tạo thêm gánh nặng key management và có thể làm Redis commands không thực thi trực tiếp trên giá trị mã hóa.

Đừng nghĩ rằng một deployment "đã bật TLS và ACL" có nghĩa an toàn khi developer log nguyên token ở HTTP layer.

## 23. RDB, AOF, replicas và backup kéo dài vòng đời dữ liệu

Redis có thể sử dụng RDB snapshots, Append Only File (AOF), replication và backup ngoài node. Nếu key/value chứa dữ liệu nhạy cảm, những lớp này cũng chứa dữ liệu hoặc bản sao của nó.

### 23.1. Hậu quả sau khi xóa key

Giả sử ứng dụng chạy:

```redis
DEL customer:profile:v1:<opaque-id>
```

Live Redis có thể không còn entry, nhưng:

- Một bản RDB trước thời điểm xóa vẫn chứa dữ liệu.
- AOF hoặc backup chứa nội dung/commands theo thời điểm.
- Replica và snapshot phụ có thể tồn tại.
- Application/driver logs và traces có thể đã sao chép key/value.
- Monitoring exports hoặc support tickets có thể lưu bản trích.

Cần một **data retention/deletion policy** cho các nơi đó, không chỉ `DEL` trên Redis. Đừng tuyên bố "đã xóa sạch mọi bản sao" chỉ vì Redis GET trả nil.

### 23.2. Các biện pháp

- Encryption at rest cho storage/snapshot khi provider hỗ trợ.
- Backup encryption keys nằm ở hệ thống quản lý secret phù hợp.
- Quyền đọc backup rất hạn chế; có audit truy cập.
- Thời gian lưu snapshot/backup và log tương ứng chính sách.
- Xóa hoặc vô hiệu hóa bản sao theo quy trình được duyệt.
- Chỉ thu heap dumps/crash dumps khi cần, giữ trong kho hạn chế.
- Kiểm tra khả năng phục hồi của encrypted payload khi rotate key: **mất key giải mã có thể làm backup không dùng được**.

Không nên chỉ mã hóa value rồi để key chứa email, hoặc mã hóa backup rồi để AOF/log export plaintext trong môi trường khác.

## 24. Thiết kế logging khi Redis lỗi mà vẫn chẩn đoán được

Vấn đề thực tế: khi Redis timeout, người vận hành cần biết endpoint nào lỗi, command nào, độ trễ bao lâu, tỷ lệ lỗi và trace nào liên quan — nhưng không nhất thiết cần biết email hay token trong key.

Một event có cấu trúc:

```json
{
  "event": "redis_operation_failed",
  "service": "customer-service",
  "operation": "GET",
  "cache": "customerProfile",
  "errorCategory": "TIMEOUT",
  "elapsedMs": 3000,
  "traceId": "opaque-trace-id"
}
```

Không cần các field:

```json
{
  "email": "alice@example.org",
  "redisKey": "profile:alice@example.org",
  "redisValue": "full-customer-json",
  "authorization": "Bearer example"
}
```

### 24.1. Spring CacheErrorHandler và việc xử lý key

Một `CacheErrorHandler` tùy chỉnh thường nhận cả object key:

```java
@Override
public void handleCacheGetError(
        RuntimeException exception,
        Cache cache,
        Object key) {
    // KHÔNG: log.warn("Cache GET failed key={}", key, exception);

    log.warn(
            "Cache GET failed cache={} errorType={}",
            cache.getName(),
            exception.getClass().getSimpleName()
    );

    // Quyết định có throw hay fail-open phải theo
    // hợp đồng nghiệp vụ và kiến trúc cache.
}
```

Ví dụ này chỉ minh họa **redaction của log**, không phải cách triển khai toàn bộ CacheErrorHandler. Khi xây handler thật cần xử lý đủ các phương thức lỗi GET/PUT/EVICT/CLEAR theo giao diện Spring version.

Nếu Redis chỉ là cache có thể bỏ, có thể thiết kế fail-open trong những tình huống thích hợp; nếu Redis đang giữ dữ liệu authoritative, nuốt mọi lỗi và coi như miss có thể gây **mất tính đúng đắn**. Logging an toàn không đồng nghĩa bỏ qua exception.

### 24.2. Phân loại lỗi

Một tập error category gọn:

```text
CONNECT_TIMEOUT
COMMAND_TIMEOUT
AUTHENTICATION
PERMISSION
SERIALIZATION
WRONGTYPE
UNAVAILABLE
UNKNOWN_REDIS_ERROR
```

Những category này có thể làm metric tag/log field mà không chứa PII. Nên tránh đưa `exception.getMessage()` vào label vì message có thể thay đổi vô hạn và chứa nội dung nhạy cảm.

## 25. Kiểm thử chống rò rỉ: kiểm tra key, value, log và trace

Các test bảo mật nên dùng **giá trị nhạy cảm giả**, không dùng token hoặc dữ liệu khách hàng thật.

### 25.1. Unit test cho key derivation

```java
package com.example.security.redis;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Base64;

import org.junit.jupiter.api.Test;

class PrivateRedisKeyFactoryTest {

    @Test
    void derivedKeyDoesNotContainRawIdentity() {
        String fakeSecret = Base64.getEncoder()
                .encodeToString(new byte[32]);

        PrivateRedisKeyFactory factory =
                new PrivateRedisKeyFactory(fakeSecret);

        String email = "alice@example.org";

        String first = factory.customerProfileKey(
                "test-tenant", email);

        String second = factory.customerProfileKey(
                "test-tenant", email);

        String other = factory.customerProfileKey(
                "other-tenant", email);

        assertThat(first)
                .startsWith("customer:profile:v2:")
                .doesNotContain(email);

        assertThat(first).isEqualTo(second);
        assertThat(first).isNotEqualTo(other);
    }
}
```

Đây là unit test minh họa deterministic key derivation, **không** chứng minh secret đủ entropy trong production. Mảng zero bytes chỉ dùng như test fixture công khai; không dùng làm key bảo mật thật.

### 25.2. Integration test Redis keyspace với dữ liệu tổng hợp

Có thể dùng Testcontainers + `StringRedisTemplate`:

1. Tạo HMAC key từ synthetic tenant và synthetic email.
2. Ghi cache data được phép.
3. Dùng `SCAN` trong namespace test để kiểm tra key names không chứa fake email/phone/token.
4. Đọc value bằng quyền/test serializer và xác nhận field bị loại không tồn tại.
5. Xóa key test trong `finally`.
6. Không dùng `KEYS *` trên production; việc scan này thuộc môi trường test cách ly.

Một integration test nên kiểm tra cả Spring Cache prefix, không chỉ key trả về từ key factory: `customerProfiles::<safe-key>` là key thực trong Redis khi dùng CacheManager tương ứng.

### 25.3. Test logging bằng CapturedOutput

Spring Boot Test có `OutputCaptureExtension` giúp kiểm tra output từ logging/stdout trong phạm vi phù hợp.

```java
package com.example.customer;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

@ExtendWith(OutputCaptureExtension.class)
class SafeCacheLogTest {

    private final CustomerCacheObserver observer =
            new CustomerCacheObserver();

    @Test
    void shouldNotPrintSensitiveIdentity(
            CapturedOutput output) {

        String syntheticEmail = "secret-fixture@example.org";

        // Dùng dữ liệu tổng hợp trong test; observer chỉ
        // ghi metadata allowlisted.
        observer.cacheMiss();

        assertThat(output.getAll())
                .doesNotContain(syntheticEmail)
                .doesNotContain("Authorization")
                .doesNotContain("Bearer ");
    }
}
```

Cần đảm bảo mức log test thực sự capture được event muốn kiểm tra. Test chỉ gọi một phương thức không nhận email là **kiểm tra tối giản**, chưa bao trùm toàn bộ service/driver/error paths. Để phát hiện rò rỉ thực, hãy gọi cả code path có synthetic secret, kích hoạt cache miss/error/exception và kiểm tra log thu được.

### 25.4. Tracing test

Với một in-memory span exporter/test observation handler, có thể assert:

- Span name thuộc một danh sách được cho phép.
- Attributes chỉ gồm command/cache/outcome/latency đã chuẩn hóa.
- Không có email/phone/token/raw Redis key.
- Exception events không chứa payload nhạy cảm.
- Baggage không chứa header bí mật.
- Sampling policy không phải cơ chế redaction.

Các API cụ thể phụ thuộc Micrometer Tracing/OpenTelemetry version; mục tiêu test là kiểm tra **dữ liệu thực được export**, không chỉ đoạn code thêm attribute bằng tay.

### 25.5. Secret scanning và synthetic canary

Có thể đặt một synthetic canary token đặc trưng trong dữ liệu test:

```text
SYNTHETIC_SECRET_SHOULD_NOT_APPEAR_IN_LOGS
```

Cho workflow chạy qua Redis, log, metrics và tracing test exporter rồi quét tìm chính chuỗi canary. Đây là phép thử hữu ích để phát hiện rò rỉ qua đường bất ngờ, nhưng **không chứng minh mọi dạng PII đã được loại bỏ**.

Không dùng credential production làm canary.

## 26. Incident response khi phát hiện log/trace chứa dữ liệu nhạy cảm

Ví dụ phát hiện distributed trace có `redis.key="session:<raw-token>"`.

Cần phân biệt **dừng rò rỉ tiếp diễn** với **xử lý dữ liệu đã bị sao chép**.

Một runbook phù hợp:

1. **Phân loại mức độ:** dữ liệu gì bị lộ, ở môi trường nào, có thể bị sử dụng để truy cập không?
2. **Dừng nguồn rò rỉ:** tắt attribute/debug setting, triển khai key naming an toàn hoặc tạm dừng feature theo mức rủi ro.
3. **Giới hạn quyền xem:** log/trace backend, dashboards, exporters, tickets, links chia sẻ.
4. **Xác định phạm vi:** thời gian, số records, services, traces, backups liên quan.
5. **Thay/thu hồi secret** nếu token/password/API key có khả năng bị lộ; không chỉ redact UI.
6. **Xử lý dữ liệu lịch sử:** retention/deletion theo chính sách và khả năng thực tế của backend.
7. **Đánh giá nghĩa vụ thông báo** với đội bảo mật/pháp chế theo quy định liên quan.
8. **Phòng ngừa tái diễn:** allowlist, static/dynamic tests, code review patterns và guardrails cho logging/tracing.

Lưu ý kỹ thuật: một giá trị đã xuất hiện trong downstream log hoặc backup **không thể được coi là chưa từng lộ** chỉ vì sửa code hoặc đặt TTL cho Redis key.

## 27. Quy trình thiết kế an toàn từ đầu

### Bước 1: lập inventory

Ghi rõ từng Redis dataset:

```text
Dataset: customerProfile
Key pattern: customer:profile:v2:<HMAC>
Value: CustomerCardCacheValue (không có email/phone)
TTL: 15 phút
Source of truth: PostgreSQL
Logging: cacheName, outcome, duration; không log key/value
Tracing: redis operation + cache category; không raw ID
Metrics: cacheName, result, errorType
Backup: theo policy Redis deployment
Access: service user chỉ được namespace liên quan
```

### Bước 2: tránh lưu dữ liệu không cần

Chọn projection nhỏ, loại secret và thông tin nhạy cảm không phục vụ trực tiếp việc đọc nhanh.

### Bước 3: thiết kế key an toàn

Dùng random ID hoặc HMAC keyed derivation. Bảo đảm tenant scope, canonicalization, schema version và phương án rotation.

### Bước 4: chọn bảo vệ value

Phân loại plaintext được phép lưu, field-level encryption hoặc whole-value encryption nếu cần; giữ key management tách code ứng dụng.

### Bước 5: cấu hình ACL/TLS/retention

Giới hạn client theo namespace/commands, bảo vệ network và backup, đặt TTL đúng mục đích, không coi TTL là xóa mọi bản sao.

### Bước 6: kiểm soát log và trace

Dùng allowlist cho event code, cache name, outcome, latency, trace ID. Không gắn raw Redis keys, payload, token, email/phone vào spans, MDC, metric tags hoặc exception messages.

### Bước 7: kiểm thử đường rò rỉ

Dùng synthetic secrets để kiểm tra:

- Redis keyspace thực.
- Serialized cache values.
- Driver/application logs ở cấu hình vận hành.
- Exported span attributes và events.
- Metrics labels và cardinality.
- Stream/DLQ/PubSub notifications.

### Bước 8: chuẩn bị rollback, migration và xử lý dữ liệu cũ

Khi đổi từ raw email key sang HMAC key:

- Có thể cần đọc cả key cũ và mới trong thời gian chuyển tiếp.
- Dừng tạo key cũ ngay khi có thể.
- Không log key cũ trong quá trình migrate.
- Đặt TTL/cleanup cho key cũ theo chính sách.
- Xác định cache có thể rebuild hay dữ liệu bắt buộc phải migrate.
- Phối hợp xóa/sửa dữ liệu đã lưu trong log/trace/backup nếu yêu cầu.

## 28. Những lỗi thường gặp

| Sai lầm | Rủi ro | Hướng cải thiện |
|---|---|---|
| Dùng email/phone trong Redis key | PII lộ qua SCAN, keyevent, logs | Opaque/HMAC key |
| Base64 email rồi gọi là đã mã hóa | Có thể decode ngay | HMAC hoặc random identifier |
| SHA-256 email không secret | Dictionary attack | Keyed HMAC nếu cần lookup |
| Dùng HMAC digest làm metric label | Linkability và cardinality cao | Low-cardinality labels |
| Đặt tenant ngoài key derivation | Cache key collision và rò dữ liệu chéo tenant | Tenant-scoped key và authorization |
| Chỉ mã hóa payload nhưng key còn raw ID | Lộ PII qua metadata | Bảo vệ cả key và value |
| Dùng GZIP/Java serialization làm bảo mật | Không che plaintext khỏi người đọc | AEAD khi cần |
| Dùng IV/nonce cố định cho AES-GCM | Phá bảo mật encryption | Nonce độc nhất theo key |
| Cache entity đầy đủ chỉ để đọc hai field | Lưu dư dữ liệu | Cache DTO projection |
| `@Indexed email` trong Repository | Index có thể chứa email | HMAC lookup/index được thiết kế |
| Log `Object.toString()` | In nhiều field nhạy cảm | Log metadata được duyệt |
| Log raw Redis URI/exception | Credential/arguments rò rỉ | Cấu hình secret và safe error categories |
| Bật TRACE driver trên production vô hạn | Command details vào log | Quy trình debug hạn chế |
| Đặt key/value vào span attributes | Rò qua tracing backend | Attribute allowlist |
| Gửi userId/traceId làm tag mọi metric | High cardinality/privacy | Tag service/cache/outcome |
| Dựa vào sampling để che secret | Trace sample vẫn còn secret | Redaction trước export |
| Dựa vào TLS để bảo vệ log | TLS không bảo vệ log plaintext | Logging policy riêng |
| Dựa vào Redis TTL để xóa backup | Backup có retention độc lập | Data lifecycle xuyên hệ thống |
| Ghi raw Stream payload vào DLQ/log | Nhân bản dữ liệu nhạy cảm | Opaque reference / encrypted DLQ |
| Log key trong CacheErrorHandler | Lộ PII khi Redis lỗi | Không log key/value |
| Dùng một secret HMAC cho mọi mục đích | Khó rotation và domain separation | Key separation, scoped derivation |
| Đổi HMAC secret không migrate | Cache miss hoặc mất truy cập dữ liệu chính | Key version, dual-read/migration |
| Dùng "ẩn key" thay phân quyền | Người đọc Redis vẫn có thể lấy value | ACL + application authorization |

## 29. Bảng quyết định nhanh

| Dữ liệu | Redis key | Redis value | Logging/tracing |
|---|---|---|---|
| Giá sản phẩm công khai | `product:price:<publicId>` | Giá + version | Command type, cache name, duration |
| Hồ sơ người dùng | `customer:profile:v2:<HMAC>` | DTO ít field, encryption khi cần | Không email/phone/key |
| Session/token | Opaque random ID hoặc HMAC phù hợp | Hạn chế token plaintext, TTL ngắn, quyền chặt | Không token, không session ID có thể replay |
| OTP | Opaque lookup key | Hash/verification state theo cơ chế phù hợp, TTL | Attempt result, error category |
| Redis Stream thanh toán | `events:payments` | Opaque event ref hoặc payload bảo vệ | Event type, event ID theo policy |
| HMAC lookup index | `customer:index:v1:<HMAC>` | Opaque record reference | Không digest per-user dưới dạng label |
| Rate-limit counter | `rate-limit:v1:<opaque-id>` | Counter/TTL | Policy name, allow/deny aggregate |
| Cache query tìm kiếm | Hash/HMAC từ canonical query khi cần | Kết quả tối thiểu | Không raw search query |

Cả key, value và observability payload phải được đánh giá **theo cùng một data classification policy**. Không nên quyết định rằng một field là confidential trong database nhưng public trong Redis logs chỉ vì nó dùng cho caching.

## 30. Kết luận

Trong Spring Data Redis, **bảo vệ thông tin nhạy cảm không dừng ở việc đặt password cho Redis hoặc bật TLS**. Tên key có thể tiết lộ email, số điện thoại và token qua command arguments, SCAN hoặc keyspace notifications; serialized value có thể chứa nguyên entity và bị sao chép sang replica, RDB/AOF hoặc backup; log và distributed traces có thể làm thông tin rò ra khỏi Redis trong thời gian dài.

Một chiến lược đúng gồm:

- **Không đưa raw PII/secret vào Redis key names.** Dùng opaque identifier, HMAC có secret và tenant scope khi phù hợp.
- **Không lưu những field không cần.** Cache DTO tối thiểu; mã hóa payload bằng cơ chế AEAD đã được quản lý nếu threat model đòi hỏi.
- **Log và trace theo allowlist.** Chỉ giữ command category, cache name, outcome, duration và correlation ID an toàn; không ghi key, value, token hay raw exception data khi chưa đánh giá.
- **Giới hạn quyền truy cập và thời gian lưu.** Redis ACL, TLS, backup controls, retention và monitoring permissions có phạm vi khác nhau.
- **Kiểm thử đường rò rỉ trước khi phát hành.** Kiểm tra cả Redis keyspace, serializer, log, trace, metrics, Streams/PubSub và DLQ với dữ liệu synthetic.
- **Có kế hoạch rotation/migration và incident response.** Một raw key đã lọt vào log/trace không biến mất khỏi mọi bản sao khi ứng dụng chỉ đổi key format.

Quy tắc thực dụng nhất: **đặt càng ít thông tin có thể nhận diện hoặc cấp quyền vào những nơi chỉ cần một định danh và một tín hiệu vận hành càng tốt**. Đó là cách giảm bề mặt rủi ro từ gốc, trong khi vẫn giữ được khả năng debug và quan sát hiệu năng của hệ thống Redis.

## Tài liệu tham khảo

- [Redis — Security](https://redis.io/docs/latest/operate/oss_and_stack/management/security/)
- [Redis — Access Control Lists](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/)
- [Redis — Encryption](https://redis.io/docs/latest/operate/oss_and_stack/management/security/encryption/)
- [Redis — MONITOR](https://redis.io/docs/latest/commands/monitor/)
- [Redis — SLOWLOG](https://redis.io/docs/latest/commands/slowlog/)
- [Redis — Keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Spring Data Redis — Redis cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [OpenTelemetry — Semantic conventions](https://opentelemetry.io/docs/specs/semconv/)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
