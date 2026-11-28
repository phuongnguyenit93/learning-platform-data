# Secret rotation

Secret rotation là quá trình thay một giá trị bí mật đang được hệ thống sử dụng bằng một giá trị mới, phân phối giá trị mới tới các consumer, xác minh chúng đã chuyển đổi và vô hiệu hóa giá trị cũ tại nơi cấp phát. Secret có thể là API token, client secret, database password, webhook signing secret, shared secret giữa hai service, pepper hoặc một mẩu cấu hình nhạy cảm.

Trong thực tế, secret thường được lưu trong secret manager và được nhiều workload đọc qua SDK, agent, volume mount hoặc pipeline triển khai. Chỉ cập nhật giá trị trong secret manager chưa đủ để hoàn tất rotation: ứng dụng có thể đang cache giá trị cũ, một batch job chưa chạy, một region chưa được cập nhật hoặc hệ thống đích vẫn chấp nhận secret cũ vô thời hạn.

Bài học tập trung vào vòng đời secret, versioning, consumer rollout, overlap, thu hồi, tự động hóa và kiểm toán. Nội dung phân biệt secret rotation với cryptographic key rotation để chọn đúng thao tác cho từng loại dữ liệu trong hệ thống quản lý khóa.

## 1. Mục tiêu và phạm vi

Sau bài học, người đọc cần có khả năng:

- Giải thích secret là gì và phân biệt secret với cryptographic key, credential, token và certificate.
- Nhận diện secret tĩnh, secret động, secret dẫn xuất và secret có chứa key material.
- Xác định trigger, owner, consumer, scope và thời hạn cho từng secret.
- Thiết kế quy trình tạo version mới, phân phối, cutover, xác minh và revoke version cũ.
- Quản lý overlap window, cache, reload, connection pool và workload chạy không liên tục.
- Dùng secret manager đúng cách, hiểu version, lease, alias và trạng thái provider.
- Tự động hóa rotation với idempotency, concurrency control và approval phù hợp.
- Xử lý rotation bình thường, khẩn cấp và tình huống provider không hỗ trợ overlap.
- Tránh lộ secret qua source code, log, environment, image, backup và pipeline.
- Kiểm thử consumer coverage, xác minh secret cũ bị từ chối và lưu audit evidence.

Phạm vi chính là secret được dùng để xác thực hoặc cấu hình hệ thống. Khi secret chứa DEK, KEK, signing key hoặc MAC key, cần áp dụng thêm chính sách key lifecycle tương ứng; thay secret reference không đồng nghĩa đã thay key material hoặc chuyển đổi dữ liệu mật mã.

## 2. Secret là gì?

Secret là dữ liệu nhạy cảm mà việc tiết lộ hoặc sử dụng trái phép có thể làm lộ thông tin, cho phép truy cập hoặc tạo ra hành động không được phép.

| Nhóm secret | Ví dụ | Tác động nếu bị lộ |
|---|---|---|
| Service authentication secret | API key, client secret | Kẻ tấn công có thể gọi API dưới danh tính service |
| Database secret | Password, connection credential | Truy cập hoặc sửa dữ liệu |
| Shared authentication secret | HMAC secret, webhook secret | Giả mạo message hoặc request |
| Infrastructure secret | Cloud access token, deployment token | Chiếm quyền tài nguyên hoặc pipeline |
| Application secret | Encryption passphrase, pepper | Ảnh hưởng bảo mật dữ liệu hoặc password verifier |
| Bootstrap secret | Secret dùng để enroll workload | Mở đường cấp phát credential dài hạn |
| Recovery secret | Recovery token, escrow secret | Vượt qua quy trình khôi phục nếu bị lộ |

Secret thường là bytes hoặc chuỗi có entropy cao. Một secret có thể đại diện cho credential xác thực, nhưng cũng có thể là key material được một API mật mã sử dụng. Vì vậy, inventory phải ghi rõ loại và purpose thay vì chỉ gắn nhãn chung là “password” hoặc “key”.

Secret không nhất thiết là dữ liệu cần giải mã. Ví dụ API key thường được gửi tới dịch vụ xác thực để chứng minh quyền truy cập; password người dùng nên được lưu dưới dạng password hash; symmetric key là bytes dùng trực tiếp hoặc gián tiếp trong phép mã hóa.

## 3. Phân biệt secret, key, credential, token và certificate

| Khái niệm | Bản chất | Rotation thường thay gì? |
|---|---|---|
| Secret | Giá trị bí mật cần bảo vệ | Giá trị secret hoặc version |
| Cryptographic key | Key material có thuật toán, purpose và key usage | Key material hoặc key version; có thể kéo theo rewrap/re-encrypt/re-sign |
| Credential | Bằng chứng xác thực hoặc quyền truy cập | Password, API key, certificate hoặc token |
| Token | Giá trị mang claim/quyền, thường có expiry | Token/session hoặc signing key tùy kiến trúc |
| Certificate | Tài liệu X.509 gắn public key với danh tính và policy | Certificate renewal hoặc rekey; có thể cần revoke |

Một số secret chính là credential; một số secret chứa key material. Nhưng thao tác rotation khác nhau:

- Thay API client secret thường cần tạo secret mới ở authorization server, cập nhật client và revoke secret cũ.
- Thay KEK có thể cần rewrap các DEK được bọc bởi KEK cũ.
- Thay DEK thường cần re-encrypt dữ liệu phụ thuộc.
- Thay JWT signing key cần công bố public key mới trước khi signer chuyển sang key mới.
- Thay password verifier có thể cần password do người dùng nhập lại hoặc reset flow.

Không coi mọi secret rotation là thao tác thay một dòng trong secret manager.

## 4. Secret tĩnh và secret động

**Secret tĩnh** tồn tại cho đến khi được thay hoặc thu hồi. Ví dụ API key lâu dài, database password, client secret và webhook signing secret.

**Secret động** được cấp phát theo yêu cầu, có lease hoặc thời hạn ngắn, thường gắn với identity và policy. Ví dụ database credential cấp theo lease, cloud token ngắn hạn hoặc credential được federation.

| Đặc điểm | Secret tĩnh | Secret động |
|---|---|---|
| Cấp phát | Thường do admin hoặc automation tạo | Provider tạo theo request và policy |
| Thời hạn | Có thể dài hoặc không có expiry rõ | Có TTL/lease |
| Rotation | Thường cần phối hợp consumer và issuer | Có thể cấp mới/renew lease tự động |
| Thu hồi | Gọi API revoke/disable hoặc đổi giá trị ở issuer | Revoke lease hoặc để lease hết hạn theo policy |
| Rủi ro | Tồn tại lâu, khó xác định nơi sao chép | Phụ thuộc availability, clock, lease renewal và provider |
| Vận hành | Cần inventory và lịch rotation | Cần theo dõi lease, renewal, expiry và revoke |

Secret động giảm thời gian tồn tại của giá trị bí mật, nhưng không loại bỏ nhu cầu quản lý. Consumer vẫn phải xử lý refresh, lỗi provider, clock skew, connection pool và trường hợp lease bị thu hồi trước khi workload dừng dùng secret.

## 5. Vì sao cần rotation?

Rotation giới hạn khoảng thời gian một secret có thể bị sử dụng sau khi bị lộ, bị sao chép hoặc không còn cần thiết.

Các trigger phổ biến:

- Secret có dấu hiệu xuất hiện trong log, repository, ticket hoặc artifact.
- Nhà cung cấp thông báo credential bị ảnh hưởng.
- Nhân sự, vendor hoặc workload không còn quyền.
- Secret đã vượt thời hạn theo policy.
- Secret được dùng chung giữa nhiều consumer và cần tách identity.
- Scope hoặc quyền của secret thay đổi.
- Hệ thống chuyển môi trường, tenant hoặc trust boundary.
- Provider yêu cầu thay client secret hoặc API token.
- Secret động không còn lease hợp lệ hoặc bị thu hồi.
- Có incident khiến độ tin cậy của secret không còn được bảo đảm.

Rotation không xóa được dữ liệu đã bị đọc hoặc hành động đã thực hiện bằng secret cũ. Khi có compromise, phải kiểm tra log truy cập, quyền bị lạm dụng, dữ liệu bị tác động, session và secret liên quan.

## 6. Secret inventory và ownership

Không thể rotate an toàn nếu không biết secret nào đang tồn tại và ai đang sử dụng nó.

Mỗi record inventory nên có:

| Trường | Mục đích |
|---|---|
| Secret ID | Định danh ổn định, không phải giá trị secret |
| Secret type | API key, DB password, webhook secret, pepper... |
| Owner | Team hoặc service chịu trách nhiệm |
| Issuer/provider | Nơi tạo và xác thực secret |
| Consumer | Workload, job, region và deployment sử dụng |
| Purpose/scope | Operation và tài nguyên được phép |
| Environment/tenant | Phạm vi triển khai |
| Version | Phiên bản secret đang dùng |
| Created/last rotated | Theo dõi vòng đời |
| Expiry/rotation trigger | Điều kiện thay mới |
| Last used | Bằng chứng consumer còn hoạt động |
| Revocation method | Cách vô hiệu hóa ở issuer |
| Recovery dependency | Backup, DR, restore hoặc bootstrap liên quan |

Không ghi secret value vào inventory. Có thể lưu reference tới secret manager và metadata không nhạy cảm. Quyền đọc giá trị phải tách khỏi quyền xem metadata để giảm nguy cơ lộ bí mật.

Secret không có owner hoặc không rõ consumer cần được điều tra trước khi xóa. Một secret có vẻ không được dùng trong traffic thường ngày vẫn có thể được dùng bởi cron job, DR, migration tool hoặc quy trình khôi phục hiếm khi chạy.

## 7. Secret version và trạng thái vòng đời

Secret manager thường hỗ trợ nhiều version của một secret. Cần phân biệt tên/alias logic với version bất biến.

Ví dụ:

~~~~json
{
  "secretId": "payments/provider-api",
  "activeVersion": "v8",
  "versions": [
    {
      "version": "v7",
      "state": "VERIFY_ONLY",
      "createdAt": "2026-10-01T00:00:00Z"
    },
    {
      "version": "v8",
      "state": "ACTIVE",
      "createdAt": "2026-11-28T00:00:00Z"
    }
  ]
}
~~~~

Các trạng thái ứng dụng có thể gồm:

| Trạng thái | Ý nghĩa |
|---|---|
| PREPARED | Đã tạo version mới nhưng chưa phân phối |
| DISTRIBUTED | Consumer được cấp quyền đọc version mới |
| ACTIVE | Được dùng cho operation mới |
| OVERLAP | Version cũ và mới tạm thời cùng được chấp nhận |
| VERIFY_ONLY | Chỉ dùng xác minh hoặc đọc trong phạm vi hạn chế |
| REVOKED | Issuer/provider không còn chấp nhận |
| RETIRED | Không còn hoạt động thường xuyên nhưng metadata còn để audit |
| DESTROYED | Giá trị bí mật đã bị hủy theo semantics của provider |

Đây là state model ở tầng ứng dụng. Secret manager có thể dùng tên trạng thái khác hoặc chỉ cung cấp enabled/disabled/version stages. Phải ánh xạ đúng semantics của provider.

**Xóa một version khỏi secret manager không nhất thiết thu hồi secret ở issuer.** Nếu API provider vẫn chấp nhận API key cũ, xóa bản lưu trong secret manager không ngăn kẻ tấn công dùng bản sao đã lấy trước đó. Rotation phải vô hiệu hóa secret tại nơi xác thực.

## 8. Secret rotation khác cryptographic key rotation

Đây là ranh giới quan trọng trong module quản lý khóa.

| Tình huống | Secret rotation | Key rotation |
|---|---|---|
| API key của đối tác | Tạo API key mới, chuyển client, revoke key cũ | Không nhất thiết có key encryption |
| Database password | Đổi secret tại database và cập nhật consumer | Không nhất thiết thay DEK/KEK |
| Webhook HMAC secret | Phát hành shared secret mới, verifier chấp nhận theo overlap | Cần phối hợp cả signer và verifier; quản lý MAC key usage |
| KEK lưu trong KMS | Có thể chỉ đổi secret reference không đủ | Phải tạo key version và xử lý wrapped DEK |
| DEK trong envelope | Thay secret blob có thể làm dữ liệu không đọc được | Cần re-encrypt hoặc thiết kế versioned DEK |
| JWT signing key | Secret store chứa private key reference hoặc handle | Rekey và phân phối public key mới; giữ public key cũ để verify |

Khi secret chỉ là tham chiếu đến key trong KMS, rotation alias không tự chứng minh key material đã đổi. Hãy ghi nhận key ID/version thật và semantics của provider.

Nếu secret là private key hoặc symmetric key bytes, không sao chép nó sang một secret store mới rồi gọi đó là key rotation. Cần xác định key generation, key usage, cryptoperiod, key version, backup, revocation và dữ liệu phụ thuộc.

## 9. Chính sách rotation theo loại secret

Không có một chu kỳ duy nhất phù hợp cho mọi secret. Policy cần dựa trên threat model, mức quyền, khả năng phát hiện lộ secret, thời gian rollout và khả năng revoke.

| Secret | Trigger hoặc policy cần xét |
|---|---|
| API key | Compromise, quyền thay đổi, vendor policy, tuổi thọ và overlap |
| OAuth client secret | Provider policy, expiry, client rollout và token/session lifetime |
| Database password | Secret policy, principal overlap, pool lifecycle và job inventory |
| Webhook secret | Khả năng signer/verifier cùng hỗ trợ hai version, event retry window |
| Cloud access token | TTL ngắn, federation và lease renewal |
| Service bootstrap secret | Thời gian tồn tại ngắn, chỉ dùng enrollment và thu hồi sau bootstrap |
| Password pepper | Key lifecycle riêng, migration verifier và password availability |
| KMS credential | IAM/workload identity, provider policy, recovery dependency |
| HMAC shared secret | Hai phía cùng chuyển version, message verification window và replay controls |

Một lịch rotation định kỳ có thể là một lớp kiểm soát, nhưng không thay thế event-driven rotation khi có compromise. Với secret động có TTL ngắn, việc renew lease là một cơ chế khác với tạo secret tĩnh mới theo lịch.

## 10. Chuẩn bị trước khi rotate

Trước khi tạo secret mới, cần hiểu tác động của cutover.

Checklist preflight:

1. Xác định Secret ID và version hiện hành.
2. Xác định issuer xác thực secret và API revoke.
3. Liệt kê consumer theo service, region, environment, cron job và DR.
4. Xác định consumer đọc secret qua SDK, environment, file mount hay sidecar.
5. Kiểm tra cache TTL và cơ chế reload.
6. Xác định issuer có cho phép hai secret cùng active không.
7. Xác định overlap window và deadline.
8. Kiểm tra quyền tạo, phân phối và revoke.
9. Xác định rollback có an toàn không.
10. Thiết lập metric và tiêu chí thành công.
11. Xác định ai phê duyệt rotation và ai thực hiện revoke.
12. Chuẩn bị phương án khẩn cấp nếu secret cũ đã compromise.

Nếu không thể xác định consumer hoặc cách revoke secret, chưa nên tự động xóa version cũ. Cần điều tra dependency và thống nhất owner.

## 11. Quy trình Secret rotation chuẩn

~~~~mermaid
flowchart TD
    A[Inventory và preflight]
    B[Tạo secret version mới]
    C[Lưu trong secret manager]
    D[Phân phối quyền cho consumer]
    E[Consumer load version mới]
    F[Canary và kiểm tra operation]
    G[Theo dõi usage cũ/mới]
    H[Revoke secret cũ tại issuer]
    I[Verify secret cũ bị từ chối]
    J[Retire metadata và đóng audit]
    A --> B --> C --> D --> E --> F --> G --> H --> I --> J
~~~~

Các bước cần có:

**Tạo:** sinh secret mới bằng cơ chế ngẫu nhiên hoặc issuer đáng tin cậy. Không tự tạo secret bằng timestamp, UUID không phù hợp hoặc password dễ đoán.

**Lưu:** ghi secret vào secret manager với version mới, policy đọc tối thiểu và audit.

**Phân phối:** consumer chỉ nhận quyền đọc version mới khi cần. Không gửi giá trị qua chat, email hoặc log.

**Cutover:** consumer chuyển sang version mới theo rollout có kiểm soát.

**Xác minh:** kiểm tra operation thực tế, không chỉ kiểm tra rằng secret manager trả về giá trị.

**Thu hồi:** vô hiệu hóa secret cũ tại issuer sau khi đủ bằng chứng và hết overlap. Nếu secret đã compromise, thu hồi ngay theo incident plan.

**Đóng:** cập nhật inventory, audit, version state và kết quả kiểm tra.

## 12. Overlap window và dual-secret acceptance

Overlap window là khoảng thời gian secret cũ và mới cùng được chấp nhận để consumer chuyển đổi.

Ví dụ webhook verifier có thể chấp nhận cả secret v7 và v8 trong thời gian ngắn:

~~~~text
Signer                         Verifier
  |                               |
  |---- request + signature(v7) ->| Verify v7
  |                               |
  |---- request + signature(v8) ->| Verify v8
  |                               |
  |      deploy signer v8         |
  |                               |
  |---- request + signature(v8) ->| Verify v8
  |                               |
  |       revoke v7 at issuer     |
  |                               |
  |---- request + signature(v7) ->| Reject
~~~~

Overlap chỉ an toàn khi có thời hạn, scope và điều kiện kết thúc. Nếu secret cũ bị lộ, việc tiếp tục chấp nhận nó có thể cho kẻ tấn công thêm thời gian khai thác. Khi đó ưu tiên revoke/containment, không duy trì overlap chỉ để rollout thuận tiện.

Overlap cũng không phải lúc nào cũng khả thi. Một số issuer chỉ cho phép một client secret active. Có thể cần tạo client identity thứ hai, tạo database principal song song hoặc dùng maintenance window.

## 13. Consumer rollout, cache và reload

Secret manager có thể trả về version mới nhưng consumer vẫn tiếp tục dùng giá trị cũ do cache hoặc process lifecycle.

Các kiểu phân phối phổ biến:

| Cách phân phối | Điểm cần chú ý |
|---|---|
| SDK/API call | Cache TTL, retry, rate limit, IAM và provider outage |
| Environment variable | Thường chỉ đọc lúc process start; cần restart/redeploy |
| Mounted file | Cần theo dõi file replacement, inode, symlink và reload semantics |
| Sidecar/agent | Health, synchronization, cache và version visibility |
| CSI secret volume | Driver refresh semantics và application reload |
| CI/CD injection | Artifact/log masking, build-time exposure và deploy rollout |

Không giả định thay file mount sẽ khiến ứng dụng tự reload. Một số runtime chỉ đọc file một lần lúc khởi động; một số framework giữ secret trong singleton hoặc connection pool.

Quy trình cần xác minh:

- Consumer đã đọc đúng version.
- Process mới đã dùng secret mới.
- Request/connection mới thành công.
- Job chạy theo lịch đã được kiểm tra.
- Mọi region và replica đã chuyển đổi.
- Consumer không còn cache secret cũ sau thời hạn.
- Rollback không khôi phục secret đã bị compromise.

## 14. Java example: lấy secret theo version

Ứng dụng nên làm việc với secret reference và provider abstraction. Ví dụ sau định nghĩa interface để lấy giá trị secret từ một implementation được kết nối với secret manager.

~~~~java
import java.util.Objects;

public interface SecretProvider {
    SecretValue read(String secretId, String version)
            throws SecretAccessException;

    record SecretValue(
            String secretId,
            String version,
            char[] value
    ) {
        public SecretValue {
            Objects.requireNonNull(secretId);
            Objects.requireNonNull(version);
            Objects.requireNonNull(value);
        }
    }

    final class SecretAccessException extends Exception {
        public SecretAccessException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~~

Implementation thật phải xác thực workload identity, giới hạn quyền đọc theo secret ID/version, không log response body và xử lý timeout/retry theo provider. Không tạo một implementation giả lập bằng cách hard-code secret trong source code.

### Dùng secret trong một thao tác

~~~~java
import java.util.Arrays;

public final class ApiClientCredential {
    private final SecretProvider secretProvider;

    public ApiClientCredential(SecretProvider secretProvider) {
        this.secretProvider = secretProvider;
    }

    public void callProvider() throws Exception {
        SecretProvider.SecretValue secret =
                secretProvider.read("payments/provider-api", "v8");

        char[] value = secret.value();
        try {
            authenticateAndCall(value);
        } finally {
            Arrays.fill(value, '\0');
        }
    }

    private void authenticateAndCall(char[] secret) {
        // Pass the secret directly to the HTTP client authentication layer.
        // Never log it or convert it to a diagnostic string.
    }
}
~~~~

Đoạn code minh họa ownership của char array và thao tác best-effort clearing. Một số SDK hoặc HTTP client có thể yêu cầu String/byte array và tạo bản sao nội bộ; việc xóa một mảng không bảo đảm mọi bản sao trong heap đã biến mất. Ưu tiên API provider/client có thể giữ secret trong vùng xử lý được kiểm soát và không để secret tồn tại lâu hơn cần thiết.

Trong production, version không nên được hard-code tùy tiện trong source. Một control plane có thể cập nhật active version reference sau khi đã chuẩn bị và kiểm tra version mới.

## 15. Java example: kiểm soát cutover theo version

Ví dụ dưới đây quản lý reference tới version hiện hành. Nó không lưu secret bytes và không thực hiện thao tác revoke ở issuer.

~~~~java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class SecretVersionPointer {
    public record Reference(String secretId, String version) {
        public Reference {
            Objects.requireNonNull(secretId);
            Objects.requireNonNull(version);
            if (secretId.isBlank() || version.isBlank()) {
                throw new IllegalArgumentException("Invalid secret reference");
            }
        }
    }

    private final AtomicReference<Reference> active;

    public SecretVersionPointer(Reference initial) {
        active = new AtomicReference<>(Objects.requireNonNull(initial));
    }

    public Reference current() {
        return active.get();
    }

    public boolean cutover(Reference expected, Reference prepared) {
        Objects.requireNonNull(expected);
        Objects.requireNonNull(prepared);

        if (expected.equals(prepared)) {
            throw new IllegalArgumentException(
                    "Prepared version must differ from active version"
            );
        }

        return active.compareAndSet(expected, prepared);
    }
}
~~~~

AtomicReference chỉ bảo vệ trạng thái trong một JVM. Với nhiều instance, cần control plane hoặc storage transaction có version/compare-and-set để tránh hai controller đồng thời thay active version. Phải có audit event và operation ID để xử lý retry.

Không xóa secret cũ sau khi đổi pointer. Trước hết cần xác minh consumer, connection, cache, batch job và issuer acceptance.

## 16. Secret động và lease rotation

Secret động thường được cấp theo lease. Consumer có thể renew lease trước khi hết hạn hoặc yêu cầu secret mới.

Một vòng đời đơn giản:

~~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> ISSUED
    ISSUED --> ACTIVE
    ACTIVE --> RENEWED: Renew lease
    RENEWED --> ACTIVE
    ACTIVE --> REVOKED: Revoke lease
    ACTIVE --> EXPIRED: TTL elapsed
    ISSUED --> REVOKED: Revoke before use
    REVOKED --> [*]
    EXPIRED --> [*]
~~~~

Consumer phải xử lý:

- Lease ID và expiry.
- Renewal trước một khoảng an toàn.
- Retry có backoff và jitter.
- Clock skew giữa client và provider.
- Provider unavailable.
- Lease đã bị revoke.
- Credential đã hết hạn nhưng connection cũ còn mở.
- Tạo credential mới và chuyển connection pool.
- Xóa credential khỏi cache sau khi hết hạn.

Renew lease không nhất thiết tạo secret value mới. Một số provider gia hạn cùng credential; một số workflow phải cấp credential mới. Phải hiểu semantics cụ thể.

Nếu provider không thể renew, consumer cần fail theo policy và không tiếp tục sử dụng secret đã hết hạn chỉ vì connection cũ còn hoạt động.

## 17. Secret trong webhook và shared authentication

Webhook thường dùng shared secret để tạo HMAC trên request body hoặc signing input. Rotation cần phối hợp sender và receiver.

Một thiết kế có version identifier:

~~~~json
{
  "eventId": "evt-2026-00421",
  "timestamp": "2026-11-28T10:30:00Z",
  "signatureVersion": "v8",
  "signature": "BASE64_OR_HEX_MAC"
}
~~~~

Verifier có thể tra secret version v8 theo registry và xác minh MAC. Trong overlap, nó có thể tạm chấp nhận v7 và v8. Tuy nhiên:

- Version identifier không phải secret.
- Không tin version do sender chọn nếu version đó ngoài allowlist.
- Signing input phải ràng buộc timestamp, method/path hoặc context theo protocol.
- Phải chống replay bằng timestamp window, event ID hoặc idempotency store.
- Phải có deadline kết thúc overlap.
- Sau revoke, kiểm thử request ký bằng secret cũ bị từ chối.

Nếu dùng HMAC, hai phía cùng có khả năng tạo MAC. Quyền giữ shared secret phải được giới hạn; không dùng cùng secret cho nhiều integration nếu cần cô lập blast radius.

## 18. Secret có chứa key material

Một secret manager có thể lưu bytes của symmetric key hoặc private key. Điều này tiện cho một số ứng dụng, nhưng có thể làm mờ ranh giới giữa secret management và key management.

Nếu secret là DEK/KEK/signing key:

- Ghi algorithm, purpose, key type, size và version.
- Xác định key generation và nguồn entropy.
- Bảo vệ export, access và backup theo key policy.
- Kiểm soát operation được phép: encrypt, decrypt, sign, verify, wrap, unwrap.
- Xác định ciphertext hoặc signature nào phụ thuộc key.
- Lập kế hoạch rewrap/re-encrypt/re-sign khi rekey.
- Giữ public key cũ nếu cần verify lịch sử.
- Xác định điều kiện retire/destroy sau khi dependency được xử lý.

Một secret version mới chỉ là một bản lưu mới. Nó không tự cập nhật ciphertext đã được mã hóa bằng key cũ. Nếu key không exportable trong HSM/KMS, consumer nên dùng key handle hoặc provider API thay vì tải raw key material.

## 19. Rotation với secret manager và KMS

Secret manager và KMS có thể cùng tham gia nhưng có trách nhiệm khác nhau:

- Secret manager lưu, version và phân phối secret value.
- KMS/HSM quản lý key material và thực hiện cryptographic operation.
- IAM/workload identity quyết định ai được đọc secret hoặc gọi key operation.
- Issuer/provider bên ngoài quyết định secret nào còn được chấp nhận.

Một luồng có thể như sau:

~~~~mermaid
sequenceDiagram
    participant R as Rotation controller
    participant S as Secret manager
    participant I as Issuer/API provider
    participant C as Application consumer
    R->>I: Create secret v8
    I-->>R: New secret value + identifier
    R->>S: Store version v8
    S-->>R: Version reference
    R->>C: Publish active version reference
    C->>S: Read v8 using workload identity
    S-->>C: Secret v8
    C->>I: Authenticate using v8
    I-->>C: Success
    R->>I: Revoke v7 after cutover
    I-->>R: Revocation result
~~~~

Một số provider tạo secret mới trong secret manager; một số API issuer tạo credential trước rồi mới lưu secret value. Thứ tự cần bảo đảm không mất secret value trước khi lưu thành công. Nếu issuer chỉ trả secret một lần, rotation controller phải ghi an toàn trước khi đánh dấu operation hoàn tất.

Không coi alias KMS hoặc secret manager label là key version bất biến. Lưu immutable version ID trong metadata của ciphertext hoặc record phụ thuộc khi cần đọc lại dữ liệu cũ.

## 20. Rotation khẩn cấp khi secret bị lộ

Khi secret bị lộ, ưu tiên ngăn việc sử dụng tiếp tục. Overlap thông thường có thể không phù hợp.

Runbook tham khảo:

1. Xác định secret ID, version, issuer, owner và scope.
2. Xác định nơi secret bị lộ và khoảng thời gian có thể bị truy cập.
3. Revoke/disable secret tại issuer hoặc provider.
4. Thu hồi session/token được cấp bằng secret đó nếu có thể.
5. Tạo secret mới qua kênh tin cậy.
6. Cập nhật consumer và xác minh operation.
7. Tìm bản sao trong source history, CI/CD, logs, container image, backup và local cache.
8. Kiểm tra request hoặc hành động trái phép trước khi revoke.
9. Xoay các secret liên quan có thể cùng bị lộ.
10. Cập nhật inventory, audit và incident record.

Không chỉ xóa secret khỏi repository hoặc log rồi tiếp tục dùng nó. Kẻ tấn công có thể đã sao chép secret. Việc xóa dấu vết không làm credential cũ mất hiệu lực.

## 21. Rollback và các điều kiện an toàn

Rollback trong rotation nghĩa là đưa consumer trở lại version trước đó hoặc khôi phục cấu hình trước cutover. Việc này chỉ an toàn nếu secret cũ vẫn đáng tin cậy và issuer còn chấp nhận.

Có thể rollback khi:

- Secret mới sai cấu hình nhưng chưa compromise.
- Secret cũ chưa bị revoke.
- Issuer vẫn chấp nhận secret cũ.
- Rollback không vi phạm policy hoặc tạo downgrade.
- Consumer và provider có thể quay lại nhất quán.

Không rollback khi:

- Secret cũ đã bị lộ.
- Issuer đã revoke secret cũ.
- Credential cũ thuộc nhân sự/vendor đã mất quyền.
- Secret cũ bị policy cấm hoặc đã hết hạn.
- Kẻ tấn công có thể tiếp tục dùng secret cũ.

Nếu không thể rollback, cần sửa consumer để dùng secret mới hoặc phát hành version mới khác. Không bật lại secret bị compromise để khôi phục availability.

## 22. Tự động hóa và concurrency control

Rotation controller có thể tự động hóa phát hiện, tạo, phân phối, cutover, revoke và audit. Tuy nhiên, nó cần các thuộc tính vận hành rõ ràng.

| Thuộc tính | Mục đích |
|---|---|
| Idempotency key | Retry không tạo nhiều secret version ngoài ý muốn |
| Durable state | Restart tiếp tục đúng phase |
| Compare-and-set | Ngăn hai controller cùng cutover |
| Lease/lock | Điều phối rotation cho một Secret ID |
| Approval gate | Bảo vệ secret có quyền cao |
| Least privilege | Chỉ cấp quyền cần thiết cho đúng secret |
| Rate limit | Tránh rotation hàng loạt gây outage |
| Circuit breaker | Dừng rollout khi lỗi vượt ngưỡng |
| Observability | Theo dõi consumer và version |
| Reconciliation | So sánh state control plane với issuer/provider thực tế |

Không để một controller có quyền đọc tất cả secret và revoke toàn bộ credential trong môi trường. Phân tách quyền theo namespace, team, service và operation.

Nếu issuer tạo secret thành công nhưng secret manager ghi thất bại, controller phải có trạng thái recovery. Có thể cần retry lưu an toàn hoặc revoke secret vừa tạo nếu không thể lưu và không có consumer nào nhận nó. Không đánh dấu rotation hoàn tất khi secret value chưa được lưu và xác minh.

## 23. Audit và monitoring

Rotation cần bằng chứng để trả lời: ai thay secret, version nào, consumer nào đã chuyển đổi và secret cũ đã bị revoke ở đâu.

Metric hữu ích:

- Số secret đến hạn hoặc quá hạn.
- Số secret không có owner hoặc consumer.
- Số rotation đang ở từng state.
- Thời gian từ PREPARED đến ACTIVE.
- Số consumer theo version.
- Request authentication thành công/thất bại theo version.
- Last-used timestamp của version cũ.
- Số lease sắp hết hạn và renewal thất bại.
- Số lần retry, rollback và emergency revoke.
- Secret version bị issuer từ chối sau cutover.
- Số secret tồn tại trong nơi lưu trữ ngoài policy.

Audit event nên ghi:

- Secret ID và version, không ghi secret value.
- Actor/workload và issuer/provider.
- Operation, purpose và lý do.
- Thời điểm tạo, phân phối, cutover và revoke.
- Approval reference và rotation operation ID.
- Consumer coverage và kết quả xác minh.
- Error category và trạng thái cuối.

Không ghi raw secret, Authorization header, password, private key, token hoặc plaintext vào log. Không ghi hash của secret nếu không có nhu cầu rõ ràng và đánh giá nguy cơ dò đoán/correlation.

## 24. Kiểm thử Secret rotation

Bộ kiểm thử nên bao phủ thành công, lỗi phân phối, consumer cũ và sự cố provider.

| Test | Tình huống | Kết quả mong đợi |
|---|---|---|
| Happy path | Tạo v2, cutover, revoke v1 | Consumer dùng v2; v1 bị từ chối |
| Wrong version | Consumer yêu cầu version không tồn tại | Từ chối rõ ràng, không fallback ngầm |
| Stale cache | Consumer giữ v1 sau cutover | Phát hiện qua metric và xử lý theo overlap |
| Issuer outage | Không thể tạo secret mới | Dừng rotation, giữ trạng thái an toàn |
| Secret store outage | Issuer tạo v2 nhưng không lưu được | Recovery/revoke có kiểm soát; không đánh dấu hoàn tất |
| Consumer offline | Batch job chưa chạy | Không revoke trước khi xử lý dependency hoặc deadline |
| Expired lease | Secret động hết TTL | Consumer renew hoặc fail theo policy |
| Revoked lease | Provider revoke lease | Consumer dừng sử dụng và xử lý connection/session |
| Duplicate request | Controller retry cùng operation | Idempotent, không tạo version trùng |
| Concurrent rotation | Hai controller cùng chạy | Một operation thắng; operation kia reconcile |
| Compromised old secret | Secret cũ bị lộ | Revoke khẩn cấp, không rollback |
| Wrong tenant | Workload tenant A đọc secret tenant B | Authorization từ chối |
| Log inspection | Rotation thất bại và ghi lỗi | Không có secret value trong log |
| Rollback | Secret mới không hoạt động, cũ còn an toàn | Quay lại theo policy và audit |
| Post-revoke test | Consumer gửi secret cũ | Issuer từ chối |

Test phải chạy với provider sandbox hoặc test identity riêng. Không dùng secret production trong unit test, fixture hoặc pipeline log.

## 25. Tình huống thực tế

### Tình huống A: API key của payment provider

Một service thanh toán dùng API key v4. Nhà cung cấp cho phép hai key active cùng lúc. Đội vận hành tạo v5, lưu trong secret manager, cấp quyền cho payment service và triển khai canary.

Sau khi request bằng v5 thành công trên mọi instance, cron job và region, đội vận hành theo dõi traffic v4 trong overlap window. Khi không còn consumer hợp lệ dùng v4, họ revoke v4 tại provider và chạy negative test. Xóa version v4 trong secret manager chỉ là cleanup; thao tác revoke ở provider mới ngăn bản sao v4 bị sử dụng.

### Tình huống B: Webhook secret

Một hệ thống nhận webhook từ đối tác. Sender và receiver cần chuyển shared HMAC secret cùng nhau. Receiver triển khai hỗ trợ v6 và v7, sau đó đối tác chuyển signer sang v7. Khi retry window và event queue đã xử lý xong, hai bên ngừng chấp nhận v6.

Nếu v6 bị lộ, hai bên phối hợp revoke sớm, thu hồi event/session có liên quan và kiểm tra request giả mạo. Không kéo dài overlap chỉ vì còn webhook retry không được quản lý.

### Tình huống C: Database secret trong Kubernetes

Một workload đọc database password từ mounted secret volume. Secret manager đã cập nhật version mới nhưng ứng dụng chỉ đọc file khi startup. Pod hiện tại vẫn giữ password cũ trong memory và connection pool.

Giải pháp là triển khai reload hoặc rolling restart có kiểm soát, tạo pool mới, health check, chuyển traffic và drain pool cũ. Sau khi mọi pod và job đã chuyển, revoke password cũ ở database.

### Tình huống D: Secret động của service

Một service nhận database credential theo lease 30 phút. Nó phải renew trước khi hết hạn, cập nhật pool khi provider cấp credential mới và xử lý trường hợp lease bị revoke. Nếu service chỉ giữ password trong cache mà không theo dõi expiry, nó có thể tiếp tục dùng credential không còn hợp lệ hoặc mất kết nối khi tạo connection mới.

## 26. Checklist vận hành

### Inventory và policy

- [ ] Mỗi secret có Secret ID, owner, purpose và issuer.
- [ ] Consumer inventory bao gồm region, batch job và DR.
- [ ] Có version ID và trạng thái vòng đời.
- [ ] Xác định rõ secret là credential, token, shared secret hay key material.
- [ ] Có trigger, overlap window, expiry và revoke method.
- [ ] Quyền đọc metadata tách khỏi quyền đọc secret value.

### Rotation

- [ ] Preflight consumer và issuer trước khi tạo version mới.
- [ ] Secret mới được sinh bởi nguồn tin cậy.
- [ ] Secret được lưu an toàn trước khi phân phối.
- [ ] Consumer đã đọc đúng version.
- [ ] Cache, file mount, environment và connection pool được xử lý.
- [ ] Có telemetry chứng minh consumer đã chuyển đổi.
- [ ] Overlap có deadline và owner.
- [ ] Secret cũ được revoke tại issuer.
- [ ] Negative test xác nhận secret cũ bị từ chối.

### Vận hành và audit

- [ ] Automation có idempotency và concurrency control.
- [ ] Provider outage không làm rotation dở dang bị đánh dấu thành công.
- [ ] Rollback không bật lại secret bị compromise.
- [ ] Không log hoặc commit secret value.
- [ ] Secret không có owner/consumer được điều tra.
- [ ] Backup, restore và bootstrap dependency được kiểm tra.
- [ ] Audit lưu version và actor, không lưu secret.
- [ ] Có runbook emergency rotation và contact issuer.

## 27. Câu hỏi tự kiểm tra

**1. Secret rotation là gì?**

Thay giá trị secret đang dùng bằng version mới, chuyển consumer sang version mới, xác minh và thu hồi secret cũ tại issuer.

**2. Secret có luôn là cryptographic key không?**

Không. Secret có thể là API key, password hoặc token; một số secret mới chứa key material.

**3. Vì sao xóa secret cũ khỏi secret manager chưa đủ?**

Bản sao có thể vẫn tồn tại và issuer vẫn có thể chấp nhận giá trị cũ. Cần revoke ở nơi xác thực.

**4. Secret tĩnh khác secret động thế nào?**

Secret tĩnh tồn tại cho đến khi thay/revoke; secret động thường được cấp theo lease và TTL.

**5. Overlap window là gì?**

Khoảng thời gian có giới hạn mà secret cũ và mới cùng được chấp nhận để chuyển consumer.

**6. Có nên duy trì overlap khi secret cũ bị lộ không?**

Không nếu việc tiếp tục chấp nhận secret cũ tạo rủi ro. Cần containment và revoke khẩn cấp.

**7. Vì sao cần Secret ID và version ID?**

Để định danh secret và phiên bản bất biến, hỗ trợ audit, rollout và rollback có kiểm soát.

**8. Alias active có phải version bất biến không?**

Không. Alias có thể trỏ sang version khác; cần lưu version ID khi cần tái tạo hoặc đọc dữ liệu cũ.

**9. Consumer đọc secret qua environment variable có tự cập nhật khi secret manager đổi version không?**

Thông thường không. Process thường chỉ nhận environment khi khởi động; cần restart hoặc cơ chế reload khác.

**10. Vì sao cần kiểm tra connection pool khi rotate database secret?**

Pool có thể giữ connection cũ trong khi connection mới cần secret mới; cần tạo pool, chuyển traffic và drain.

**11. Renew lease có luôn tạo secret value mới không?**

Không. Semantics phụ thuộc provider; renew có thể chỉ kéo dài lease hiện tại.

**12. Webhook HMAC rotation cần phối hợp ai?**

Cả sender tạo MAC và receiver xác minh MAC phải chuyển version theo cùng protocol.

**13. Secret version mới có tự thay DEK trong ciphertext không?**

Không. Nếu secret chứa DEK, cần xử lý ciphertext phụ thuộc theo key lifecycle, thường là re-encrypt.

**14. Rotation secret chứa KEK có thể cần thao tác gì?**

Rewrap các DEK phụ thuộc và giữ version KEK cũ trong thời gian cần thiết cho recovery.

**15. Khi nào rollback sang secret cũ không được phép?**

Khi secret cũ bị compromise, revoked, hết hạn hoặc policy không còn cho phép.

**16. Idempotency giúp gì cho rotation controller?**

Ngăn retry tạo nhiều secret version hoặc thực hiện cutover/revoke lặp ngoài ý muốn.

**17. Provider tạo secret mới nhưng secret manager lưu thất bại thì sao?**

Rotation phải đi vào recovery state, retry lưu hoặc revoke secret vừa tạo theo policy; không được đánh dấu hoàn tất.

**18. Có nên log secret value để debug lỗi xác thực không?**

Không. Chỉ log Secret ID/version, operation, issuer và error category phù hợp.

**19. Secret động có loại bỏ hoàn toàn rotation không?**

Không. Nó giảm thời gian tồn tại nhưng vẫn cần lease renewal, revoke, consumer reload và xử lý provider outage.

**20. Khi nào secret rotation được coi là hoàn tất?**

Khi consumer dùng version mới, issuer đã revoke version cũ, negative test xác nhận secret cũ bị từ chối và audit evidence được lưu.

## 28. Tài liệu tham khảo

- NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management: key lifecycle và cryptoperiod khi secret chứa key material.
- NIST SP 800-63B-4 — Digital Identity Guidelines: Authentication and Authenticator Management.
- OWASP Secrets Management Cheat Sheet — inventory, storage, rotation và access control cho secrets.
- RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.
- RFC 6749 — The OAuth 2.0 Authorization Framework: client authentication và client credentials.
- RFC 7517 — JSON Web Key (JWK), liên quan phân phối public key cho token verification.
- Tài liệu chính thức của secret manager, cloud provider, database engine và identity provider đang triển khai; đặc biệt về versioning, lease, cache, revoke và automatic rotation.

