# Ghi nhận nguồn và thời điểm tạo

> **Chương:** Key generation  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Vì sao phải ghi nhận nguồn và thời điểm tạo khóa?

Khi một khóa mật mã được tạo, hệ thống không chỉ cần **key material** để mã hóa, ký số hoặc dẫn xuất khóa. Nó còn cần **bằng chứng về nguồn gốc và lịch sử sinh khóa**: khóa được sinh ở đâu, bằng cơ chế nào, vào thời điểm nào, theo chính sách nào và dưới trách nhiệm của ai. Tập hợp thông tin này thường được gọi là **key generation provenance** hoặc **bằng chứng nguồn gốc của khóa**.

Giả sử cơ sở dữ liệu chứa bản mã được bảo vệ bằng khóa `billing-kek/v7`. Ba tháng sau, nhóm an ninh phát hiện một phiên bản thư viện sinh số ngẫu nhiên có vấn đề. Nếu key inventory chỉ có hai trường `keyId` và `algorithm`, tổ chức sẽ khó xác định **những khóa nào được sinh bởi provider bị ảnh hưởng**, chúng được sinh trong khoảng thời gian nào, dịch vụ nào sử dụng và dữ liệu nào cần thay khóa.

Ngược lại, một bản ghi có **provenance đáng tin**, thời gian được xác minh và liên kết với **key version, policy, owner và bằng chứng thao tác** giúp:

- **Truy vết sự cố:** tìm khóa được sinh trong giai đoạn RNG/provider/HSM có rủi ro.
- **Kiểm tra tuân thủ:** chứng minh quá trình sinh phù hợp chính sách thuật toán, vùng bảo vệ và quyền.
- **Quản trị cryptoperiod:** phân biệt thời điểm sinh với **thời điểm bắt đầu/đến hạn sử dụng**.
- **Rotation và revocation:** xác định đúng key version, phạm vi ảnh hưởng và thời gian thay thế.
- **Đối chiếu inventory:** phát hiện key đã được tạo trong KMS/HSM nhưng chưa được đăng ký.
- **Điều tra lịch sử:** trả lời ai yêu cầu, ai phê duyệt, thao tác nào đã thực sự hoàn tất.

**Nguyên tắc:** ghi nhận metadata của quá trình sinh là **một kiểm soát bổ sung**. Một log ghi `generatedBy=HSM` không tự chứng minh khóa thật sự được sinh trong HSM; trường `generatedAt` cũng không tự là timestamp đáng tin nếu do client gửi tùy ý.

### Mục tiêu học tập

Sau bài này, bạn có thể phân biệt **nguồn entropy, thuật toán RNG, provider, nơi sinh, nguồn sở hữu khóa, nguồn nhập khóa**, thiết kế các timestamp đúng nghĩa, xây dựng metadata inventory, kết nối bằng chứng với KMS/HSM và audit, xử lý khi key generation thành công nhưng lưu metadata thất bại, cũng như triển khai ví dụ Java 17 **không làm lộ vật liệu bí mật**.

## 2. “Nguồn tạo” của khóa có nhiều lớp

Câu “khóa được sinh từ đâu?” có thể chỉ **nhiều thông tin khác nhau**. Nếu chỉ lưu một chuỗi `source=secure`, ta không biết chính xác đang nói về điều gì.

| Lớp nguồn gốc | Câu hỏi cần trả lời | Ví dụ metadata |
| --- | --- | --- |
| **Nguồn entropy** | Entropy đầu vào cho CSPRNG/DRBG đến từ đâu? | Nguồn hệ điều hành, phần cứng bảo mật, entropy service được phê duyệt |
| **RNG/DRBG** | Cơ chế sinh byte giả ngẫu nhiên mật mã nào đã được sử dụng? | JCA `SecureRandom`, DRBG của provider, RNG nội bộ HSM |
| **Crypto provider / module** | Thư viện hoặc module nào thực thi tạo khóa? | JDK security provider, KMS key-generation service, HSM module |
| **Generation boundary** | Key material lần đầu được tạo trong ranh giới nào? | JVM process, HSM partition, managed KMS, thiết bị khách |
| **Generation method** | Sinh mới hay nhập từ bên ngoài? | `GENERATED`, `IMPORTED`, `DERIVED`, `AGREED` |
| **Người/hệ thống khởi tạo** | Ai yêu cầu, ai được phép và ai thực thi? | Workload identity, key operator, automation, approved role |
| **Policy quyết định** | Profile nào đã cho phép thao tác? | `policyId`, `policyRevision`, approval reference |
| **Nguồn bằng chứng** | Dữ liệu nào xác nhận thao tác thật sự diễn ra? | Provider key reference, signed audit event, HSM operation receipt |

Ví dụ, `SecureRandom.getAlgorithm()` và `getProvider().getName()` cho biết **thuật toán/provider được trình bày qua Java API**, nhưng **không đủ để chứng minh chi tiết nguồn entropy ở tầng hệ điều hành**, trạng thái FIPS hoặc chứng nhận của toàn bộ môi trường. Muốn khẳng định những thuộc tính đó phải dựa vào **cấu hình, tài liệu/assurance của provider và bằng chứng triển khai phù hợp**.

### 2.1. Generation source khác key storage location

Một private key có thể được **sinh trong JVM** rồi **import vào HSM**. Nếu chỉ ghi `storedIn=HSM`, người đọc có thể hiểu sai rằng private key **chưa từng tồn tại ngoài HSM**.

Ngược lại, một private signing key **sinh bên trong HSM và không xuất được** sẽ có provenance khác. Đường sinh/lưu có thể ảnh hưởng tới các yêu cầu về **non-extractability, chủ quyền khóa, rủi ro bản sao và đáp ứng chính sách**.

Do đó nên có các trường độc lập như:

- `generationMethod`: `GENERATE`, `IMPORT`, `DERIVE`, `KEY_AGREEMENT`.
- `generationBoundary`: nơi key material được tạo lần đầu, nếu biết.
- `storageLocation`: nơi material hiện được giữ, nếu phù hợp.
- `providerKeyReference`: định danh do KMS/HSM trả về.
- `originEvidenceRef`: tham chiếu chứng cứ xác thực nguồn.

**Đừng ghi một tuyên bố không kiểm chứng được là chứng cứ đã xác nhận.** Nếu không có quyền quan sát nguồn entropy, có thể ghi `entropyEvidence=NOT_EXPOSED_BY_PROVIDER` và tham chiếu hồ sơ provider, thay vì tự điền `HARDWARE_ENTROPY_VERIFIED`.

## 3. Phân biệt các thời điểm trong quá trình tạo khóa

**Creation time** không phải một khái niệm duy nhất nếu hệ thống có nhiều lớp điều phối. Một request có thể được tiếp nhận, xếp hàng, được provider thực thi, được đăng ký trong inventory và chỉ sau đó mới kích hoạt.

| Thời điểm | Ý nghĩa | Ai có thể xác nhận? |
| --- | --- | --- |
| **`requestedAt`** | Hệ thống nhận yêu cầu tạo khóa | API/approval service |
| **`approvedAt`** | Yêu cầu được duyệt theo workflow | Approval service đã xác thực |
| **`generationStartedAt`** | Worker bắt đầu thao tác gọi generator/provider | Worker/trusted execution broker |
| **`generationCompletedAt`** | Thao tác sinh đã trả kết quả thành công cho bên gọi | Worker và provider response |
| **`providerCreatedAt`** | Timestamp tạo đối tượng do KMS/HSM trả về, nếu có | Provider; cần hiểu đúng semantics |
| **`inventoryRecordedAt`** | Bản ghi key được ghi thành công vào inventory | Inventory service |
| **`activationAt`** | Mốc sớm nhất khóa được phép dùng theo policy | Key lifecycle policy |
| **`actualActivatedAt`** | Chuyển trạng thái kích hoạt thực tế được xác nhận | Controller/KMS/registry |
| **`firstUsedAt`** | Lần thao tác mật mã hợp lệ đầu tiên được quan sát | KMS/HSM/application audit |
| **`retiredAt` / `revokedAt`** | Ngừng dùng mới hoặc rút quyền/tin cậy | Key owner/security workflow |
| **`destroyedAt`** | Xác nhận key material bị hủy theo semantics của nền tảng | Provider/key custodian |

**Cần định nghĩa rõ một trường `createdAt` trong schema:** nó là `providerCreatedAt`, `generationCompletedAt` hay `inventoryRecordedAt`? Ba mốc có thể khác nhau hàng giây, phút hoặc lâu hơn khi có queue/retry.

### 3.1. Ví dụ timeline có độ trễ

~~~text
2026-11-28T02:00:00Z  requestedAt
2026-11-28T02:03:12Z  approvedAt
2026-11-28T02:03:20Z  generationStartedAt
2026-11-28T02:03:22Z  providerCreatedAt (nếu provider có)
2026-11-28T02:03:23Z  generationCompletedAt
2026-11-28T02:03:28Z  inventoryRecordedAt
2026-12-01T00:00:00Z  activationAt theo policy
2026-12-01T00:00:02Z  actualActivatedAt
2026-12-01T00:02:10Z  firstUsedAt
~~~

Các số liệu là **ví dụ**, không phải SLA chuẩn. Một API có thể tạo key object trước khi tài nguyên được **enabled** hoặc sẵn sàng cho mọi operation; một HSM có thể chỉ trả event time thay vì timestamp từng bước. Ghi nhận đúng những gì nguồn đáng tin thực sự cung cấp, **không tạo timestamp giả định để lấp chỗ trống**.

### 3.2. Thời điểm sinh khác cryptoperiod

Khóa được sinh trước một tuần **không mặc nhiên bị sử dụng ngay trong tuần đó**. `activationAt` là điều kiện bắt đầu dùng theo chính sách; `newUseUntil` là thời điểm kết thúc **tạo bảo vệ mới**; `oldUseUntil` có thể dài hơn để giải mã/unwrap dữ liệu cũ. Khi chuyển primary version, không được dùng `createdAt` để chọn phiên bản thay cho **state/usage/activation policy**.

## 4. Ghi nhận thời gian theo UTC và độ tin cậy của đồng hồ

Trong Java, **`java.time.Instant`** thích hợp để biểu diễn mốc tuyệt đối. Lưu timestamp theo **ISO 8601 với `Z` (UTC)** hoặc một định dạng có timezone rõ ràng. Ví dụ:

~~~text
2026-11-28T02:03:23Z  (UTC)
2026-11-28T09:03:23+07:00  (cùng một mốc tại UTC+07)
~~~

Không lưu `2026-11-28 09:03:23` mà **không ghi timezone** rồi cho hệ thống đa vùng tự hiểu. Một node ở châu Âu và một node ở Việt Nam có thể diễn giải khác nhau.

### 4.1. Client time không phải nguồn tin cậy

Nếu client gửi `createdAt` trong payload, nó chỉ là **thông tin client khai báo**, không chứng minh thời điểm tạo khóa. Dấu thời gian của server gần thao tác tạo khóa có giá trị vận hành hơn; **provider timestamp** hoặc audit được xác thực có thể là bằng chứng độc lập hữu ích.

Nên phân biệt:

- `clientRequestedAt`: **untrusted claim** nếu cần lưu cho mục đích tương quan.
- `serverReceivedAt`: do trusted API service ghi nhận.
- `providerCreatedAt`: do provider cung cấp, nếu có và semantics rõ.
- `recordedAt`: do inventory/audit service ghi nhận.

### 4.2. Clock skew và tính thứ tự

Hai service có thể có **clock skew**. Worker gọi KMS tại node A và audit writer ghi log tại node B; timestamp có thể lệch vài giây, thậm chí xuất hiện `inventoryRecordedAt < generationCompletedAt` theo đồng hồ của từng node dù sự kiện thực tế theo thứ tự khác.

Để kiểm soát:

1. Đồng bộ đồng hồ hệ thống bằng hạ tầng time synchronization được quản trị.
2. Lưu **nguồn và mức tin cậy timestamp**, không chỉ giá trị.
3. Dùng **request ID, operation ID, sequence/event ID** để tương quan thứ tự.
4. Theo dõi clock drift, NTP/PTP alarms nếu môi trường yêu cầu.
5. Có thể dùng monotonic clock để đo **thời lượng trong cùng tiến trình**, nhưng không lấy nó làm timestamp lịch tuyệt đối liên máy.
6. Nếu thứ tự và tính chính xác pháp lý quan trọng, cần **trusted timestamp/secure audit** theo yêu cầu, không chỉ dựa vào `Instant.now()`.

**`Instant.now()` không chứng minh một sự kiện không thể bị sửa hoặc backdate.** Nó là giá trị thời gian từ clock của runtime. Khả năng chống sửa lịch sử phụ thuộc **identity, integrity, trusted storage, event chain và chính sách quyền**.

## 5. Key inventory cần ghi những trường nào?

**Key inventory** là hệ thống quản trị **metadata và trạng thái của khóa**, không phải bảng chứa raw secret key. Một record nên đủ để trả lời: **đúng key nào, của ai, được sinh bằng cách nào và vào khi nào, dùng làm gì, còn hợp lệ không, dữ liệu nào phụ thuộc**.

| Nhóm | Trường gợi ý | Ý nghĩa |
| --- | --- | --- |
| Định danh | `keyId`, `keyVersion`, `keyClass` | Không nhập nhằng logical key với vật liệu cụ thể |
| Mục đích | `purpose`, `algorithm`, `sizeBits/curve` | Kiểm tra key usage và profile |
| Phạm vi | `ownerTeam`, `tenantScope`, `environment` | Hạn chế dùng sai miền bảo vệ |
| **Nguồn sinh** | `generationMethod`, `generationBoundary`, `providerId`, `rngEvidenceRef` | Truy vết xuất xứ |
| **Thời gian** | `requestedAt`, `generationStartedAt`, `generationCompletedAt`, `providerCreatedAt` | Xác định quá trình tạo |
| Inventory | `inventoryRecordedAt`, `metadataRevision` | Kiểm tra đăng ký và cập nhật |
| Chính sách | `policyId`, `policyRevision`, `approvalRef` | Chứng minh điều kiện cho phép |
| Lifecycle | `state`, `activationAt`, `newUseUntil`, `oldUseUntil` | Không dùng khóa sai thời điểm |
| Vật liệu | `providerKeyRef`, `exportability`, `storageBoundary` | Theo dõi nơi giữ key và quyền xuất |
| Bằng chứng | `requestId`, `operationId`, `auditEventRef`, `evidenceStatus` | Kết nối các hệ thống |
| Phụ thuộc | `wrappedDekCount`, `dependentSystems`, `backupRefs` | Chuẩn bị rotation và hủy |

**Không phải mọi nhà cung cấp đều cung cấp mọi trường.** Chỉ ghi `providerCreatedAt` khi provider thật sự trả timestamp có định nghĩa rõ; nếu không có, để trống hoặc ghi `UNAVAILABLE` trong trường chứng cứ, không gán `Instant.now()` rồi gọi nó là thời gian của HSM.

### 5.1. Record JSON mẫu

~~~json
{
  "keyId": "payments-kek",
  "keyVersion": "v7",
  "keyClass": "KEY_ENCRYPTION_KEY",
  "algorithm": "AES-256",
  "purpose": ["WRAP", "UNWRAP"],
  "ownerTeam": "payments-security",
  "tenantScope": "production/payments",
  "generationMethod": "GENERATED",
  "generationBoundary": "MANAGED_HSM",
  "providerId": "approved-kms-provider",
  "providerKeyRef": "kms://example/payments-kek/v7",
  "entropyEvidenceRef": "provider-assurance-profile-2026",
  "requestedAt": "2026-11-28T02:00:00Z",
  "generationStartedAt": "2026-11-28T02:03:20Z",
  "generationCompletedAt": "2026-11-28T02:03:23Z",
  "providerCreatedAt": "2026-11-28T02:03:22Z",
  "inventoryRecordedAt": "2026-11-28T02:03:28Z",
  "activationAt": "2026-12-01T00:00:00Z",
  "newUseUntil": "2027-03-01T00:00:00Z",
  "oldUseUntil": "2027-09-01T00:00:00Z",
  "lifecycleState": "PRE_ACTIVE",
  "policyId": "payments-kek-generation",
  "policyRevision": 12,
  "approvalRef": "KEY-CHANGE-208",
  "operationId": "gen-req-20261128-001",
  "auditEventRef": "audit-key-gen-000981",
  "evidenceStatus": "PROVIDER_CONFIRMED"
}
~~~

Đây là **ví dụ dữ liệu**, không phải schema/API chuẩn của cloud provider nào. `kms://...` là tham chiếu giả lập. `MANAGED_HSM` và `PROVIDER_CONFIRMED` chỉ nên xuất hiện khi thực tế có **evidence tương ứng**; không được tự khai các thuộc tính này vì ứng dụng chỉ gọi một endpoint mang chữ “KMS”.

**Tính nhất quán trong ví dụ:** khóa được tạo ngày 28/11 nhưng `activationAt` là 01/12, vì vậy trạng thái hiện tại vẫn là **`PRE_ACTIVE`**, không được dùng để wrap dữ liệu mới trước khi điều kiện activation đạt.

## 6. Workflow tạo khóa và ghi provenance

Một workflow tốt ghi **ý định, quyết định, thực thi và bằng chứng** như những sự kiện khác nhau.

~~~mermaid
sequenceDiagram
    participant App as Workload / owner
    participant Policy as Policy + IAM
    participant Broker as Key generation broker
    participant KMS as KMS / HSM
    participant Inventory as Key inventory
    participant Audit as Secure audit
    App->>Broker: Generation request + requestId + purpose
    Broker->>Policy: Authorize profile, tenant, environment
    Policy-->>Broker: Policy revision + decision
    Broker->>Audit: REQUESTED / APPROVED + timestamp
    Broker->>KMS: GenerateKey với idempotency khi hỗ trợ
    KMS-->>Broker: Key reference + provider evidence
    Broker->>Audit: GENERATION_CONFIRMED + evidence reference
    Broker->>Inventory: Register key version + provenance + PRE_ACTIVE
    Inventory-->>Broker: Inventory revision / confirmation
    Broker->>Audit: INVENTORY_REGISTERED + result
    Broker-->>App: Key reference, state, policy revision
    Note over Broker,Inventory: Activation là bước riêng, không tự suy từ creation
~~~

**Hai điểm then chốt:** 

1. **Provider tạo key thành công** và **inventory ghi metadata thành công** là **hai sự kiện riêng**, có thể thất bại độc lập.
2. Không được đánh dấu `ACTIVE` chỉ vì nhận được `KeyReference`. Phải đi qua **provisioning/activation** và quyền dùng thực tế.

### 6.1. Các bước thực thi

**Bước 1 — Tiếp nhận và xác thực yêu cầu.** Workload identity được xác minh. Yêu cầu phải có owner, tenant, environment, purpose, algorithm profile và `requestId`. Không tin mọi trường do client tự nhập, nhất là quyền tạo root KEK hoặc private signing key.

**Bước 2 — Kiểm tra policy trước generation.** Chỉ cho phép thuật toán/key size/provider đã duyệt, đường sinh/nhập đúng security boundary và quyền IAM phù hợp. Nếu workflow yêu cầu quorum approval, mọi approval phải ràng buộc **exact request/key class/parameters**.

**Bước 3 — Ghi `generationStartedAt`.** Chụp mốc thời gian từ trusted execution broker gần khi gọi provider, kèm `operationId`. Không gọi đây là `providerCreatedAt`.

**Bước 4 — Tạo khóa.** Gọi **KMS/HSM** hoặc JCA/JCE API theo loại khóa. Không cần và không nên xuất key bytes chỉ để kiểm tra thời gian/nguồn sinh.

**Bước 5 — Xác nhận kết quả.** Ghi `generationCompletedAt`, key reference, thuật toán, trạng thái thực và provider metadata nếu có. Khi provider trả lỗi không rõ kết quả, phải **reconcile trước khi retry**, vì khóa có thể đã được tạo.

**Bước 6 — Đăng ký inventory.** Lưu key ID/version, owner, source, timestamp, policy và audit refs trong giao dịch có kiểm soát. Khóa mới thường ở trạng thái **pre-active/quarantine**.

**Bước 7 — Activation và sử dụng.** Chỉ sau khi đạt `activationAt`, key state, IAM, dependency checks và approval mới cho use đúng purpose; audit thao tác theo version.

## 7. Java 17: sinh AES-256 trong JVM và ghi metadata an toàn

Ví dụ sau minh họa một **đường sinh khóa cục bộ cho môi trường demo** bằng `SecureRandom` và `KeyGenerator`. Nó ghi lại **provider/thuật toán được Java API báo cáo**, mốc thời gian server, key ID/version và thông tin chính sách; **không ghi raw key**.

**Giới hạn quan trọng:** đây **không phải bản ghi xác nhận KMS/HSM**. Tên provider từ JCA **không phải bằng chứng đủ để khẳng định entropy source thực tế, FIPS, non-extractability hay hardware provenance**. Trong production, nếu policy yêu cầu khóa tạo **bên trong HSM**, phải dùng đường sinh trong HSM thay vì code local này.

~~~java
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class KeyCreationMetadataDemo {
    record Request(
            String keyId, String version, String owner,
            String environment, long policyRevision) {
        Request {
            if (keyId == null || keyId.isBlank()
                    || version == null || version.isBlank()
                    || owner == null || owner.isBlank()
                    || environment == null || environment.isBlank()
                    || policyRevision < 1) {
                throw new IllegalArgumentException("Invalid key request");
            }
        }
    }

    // Các trường này là observations tại tầng JVM, không phải HSM attestation.
    record Receipt(
            String keyId, String version, String owner,
            String generationMethod, String boundary,
            String keyAlgorithm, int keySizeBits,
            String rngAlgorithm, String rngProvider,
            String generatorProvider, long policyRevision,
            Instant generationStartedAt, Instant generationCompletedAt) {}

    // Demo giữ key trong RAM chỉ để chứng minh có generation thành công.
    record Result(SecretKey key, Receipt receipt) {}

    static Result generateDemoKey(Request request, Clock clock)
            throws Exception {
        Objects.requireNonNull(request);
        Objects.requireNonNull(clock);

        // Production không được dùng local keygen cho HSM-required keys.
        if (!"development".equals(request.environment())) {
            throw new SecurityException("Local generation is dev-only");
        }

        SecureRandom rng = new SecureRandom();
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, rng);

        // Mốc gần thao tác bắt đầu; không phải timestamp bên trong provider.
        Instant started = clock.instant();
        SecretKey key = generator.generateKey();
        Instant completed = clock.instant();

        // Generator đã được cấu hình AES-256; không export raw key
        // chỉ để kiểm tra kích thước trong demo metadata này.
        if (key == null || !"AES".equalsIgnoreCase(key.getAlgorithm())) {
            throw new IllegalStateException("Unexpected demo key");
        }

        Receipt receipt = new Receipt(
                request.keyId(), request.version(), request.owner(),
                "GENERATED", "LOCAL_JVM_DEMO",
                key.getAlgorithm(), 256,
                rng.getAlgorithm(), rng.getProvider().getName(),
                generator.getProvider().getName(),
                request.policyRevision(), started, completed);

        return new Result(key, receipt);
    }

    public static void main(String[] args) throws Exception {
        Request req = new Request(
                "demo-dek", "v1", "training-service", "development", 7);
        Result result = generateDemoKey(req, Clock.systemUTC());

        Receipt metadata = result.receipt();
        System.out.println("Key: " + metadata.keyId()
                + "/" + metadata.version());
        System.out.println("Boundary: " + metadata.boundary());
        System.out.println("RNG API: " + metadata.rngAlgorithm()
                + " / " + metadata.rngProvider());
        System.out.println("Generator provider: "
                + metadata.generatorProvider());
        System.out.println("Started: " + metadata.generationStartedAt());
        System.out.println("Completed: " + metadata.generationCompletedAt());

        // Không in key.getEncoded(), không lưu khóa vào log hay file YAML.
        // Đây chỉ là metadata local; không có evidence từ KMS/HSM.
        // Đối với key thực, phải có storage/retention/zeroization policy.

        // Dùng Clock cố định để viết test mốc thời gian ổn định;
        // không dùng clock test làm nguồn entropy hay thời gian production.
        Clock testClock = Clock.fixed(
                Instant.parse("2026-11-28T02:00:00Z"), ZoneOffset.UTC);
        Result testResult = generateDemoKey(req, testClock);
        if (!testResult.receipt().generationStartedAt()
                .equals(Instant.parse("2026-11-28T02:00:00Z"))) {
            throw new AssertionError("Clock injection failed");
        }
        System.out.println("Metadata recording demo: PASS");
    }
}
~~~

### 7.1. Đọc kết quả cho đúng

- `rngAlgorithm`, `rngProvider`: **những gì đối tượng `SecureRandom` cho biết**; không phải chuỗi bằng chứng đầy đủ về mọi bước lấy entropy.
- `generatorProvider`: provider được chọn cho `KeyGenerator` AES, có thể khác provider của `SecureRandom`.
- `generationStartedAt` và `generationCompletedAt`: timestamp **do tiến trình Java ghi gần thao tác**, không tự được chứng nhận bởi HSM.
- `key.getEncoded()`: không được gọi trong demo vì có thể trả bản sao **key material ở dạng rõ**. Production cần hạn chế số bản sao, giảm thời gian giữ secret và không in/serialize. Nếu dùng key không xuất được của HSM, `getEncoded()` có thể trả `null` theo provider.
- `Clock.fixed()`: giúp test không phụ thuộc thời gian thực; **không phải nguồn ngẫu nhiên** và không được dùng làm timestamp production.

Đoạn mã là **ví dụ JCA/JCE**, không thực hiện encryption hay key storage thực tế. Việc `generateKey()` trả đối tượng `SecretKey` trong JVM đồng nghĩa **ứng dụng đã có quyền truy cập material**; không thể gắn nhãn `nonExtractable=true` rồi coi như HSM.

### 7.2. Nếu policy yêu cầu HSM/KMS thì sao?

Thay thao tác `KeyGenerator` local bằng **API provider phù hợp**. Một adapter production nên trả **key reference, thuật toán/key type, thời điểm provider cung cấp (nếu có), trạng thái, reference tới audit và mã kết quả**; không nhất thiết trả raw key. Với API có thể trả plaintext DEK tạm thời cho envelope encryption, cần **quy tắc bảo vệ bộ nhớ/đường truyền và hạn chế thời gian sống của DEK**.

### 7.3. Vì sao không kiểm chứng randomness bằng cách in key?

Một vài key sinh khác nhau hoặc có vẻ phân bố đều **không chứng minh CSPRNG/entropy an toàn**. Để đánh giá nguồn sinh, dựa vào **algorithms/providers được duyệt, entropy/DRBG design, cấu hình và evidence vận hành**. In khóa để “so sánh hash” còn tạo thêm rủi ro lộ material qua console, CI, log hoặc hệ thống giám sát.

## 8. Sinh khóa trong KMS/HSM: ghi nhận những gì?

Khi khóa được tạo trong **KMS (Key Management Service)** hoặc **HSM (Hardware Security Module)**, hệ thống cần xác định **đâu là thông tin nhà cung cấp thực sự xác nhận** và **đâu là metadata ứng dụng tự khai báo**.

### 8.1. Những dữ liệu nên đối chiếu

| Nhóm | Dữ liệu / bằng chứng |
| --- | --- |
| **Lệnh tạo** | API/operation name, request/operation ID, authenticated principal |
| **Loại khóa** | Symmetric/asymmetric, algorithm, curve/size, permitted operations |
| **Key reference** | Provider key ID, version hoặc object handle tùy nền tảng |
| **Generation boundary** | HSM partition / managed provider boundary được mô tả trong tài liệu/bằng chứng |
| **Key origin** | Generated in provider / Imported / External / Derived theo semantics provider |
| **Exportability** | Có thể xuất private/secret key hay không, theo key type và policy thực tế |
| **Thời gian provider** | Creation timestamp khi nhà cung cấp trả về và có định nghĩa rõ |
| **Audit** | Provider operation event, actor, result, resource, request correlation |
| **State** | Enabled/Disabled/PendingActivation/PendingDeletion hay trạng thái thực của sản phẩm |

**Không suy diễn:** nếu SDK không trả thời điểm tạo nội bộ, đừng sao chép `generationCompletedAt` của caller vào trường `providerCreatedAt`. Nếu HSM chỉ có object label và key handle, cũng không nên tự tuyên bố “hardware-generated” mà thiếu bằng chứng về operation/nguồn.

### 8.2. Non-extractability không đồng nghĩa không bị lạm dụng

Private signing key sinh trong HSM và không export được vẫn có thể bị lạm dụng nếu một service account có quyền gọi `Sign` mà không có **authorization theo giao dịch**. Generation provenance xác nhận **cách khóa ra đời**, còn IAM/operation policy kiểm soát **ai được phép dùng nó**.

Một record tốt cần kết nối:

- **Owner**: ai chịu trách nhiệm mục đích và vòng đời khóa?
- **Custodian**: ai vận hành KMS/HSM và backup?
- **Requester/executor**: ai đã yêu cầu và thực hiện lệnh tạo?
- **Consumer**: workloads nào có quyền `Encrypt/Decrypt/Wrap/Unwrap/Sign`?
- **Auditor**: ai có quyền kiểm tra bằng chứng mà không cần raw key?

### 8.3. Về FIPS và chứng nhận

Một hệ thống ghi `providerName=HSM` hoặc `SecureRandom` **không đủ** để chứng minh FIPS compliance. Cần biết **module được đánh giá, phiên bản firmware/software, mode hoạt động, thuật toán/operation trong phạm vi đánh giá và cấu hình triển khai**. Các thông tin này có thể được tham chiếu bằng **assurance profile/version** thay vì sao chép tài liệu vào mọi key record.

## 9. BYOK và key import: không được ghi sai nguồn tạo

**BYOK (Bring Your Own Key)** hoặc một quy trình nhập khóa có thể cho phép tổ chức sinh key material ở nơi khác rồi **import** vào KMS/HSM. Đây là một dòng provenance khác hoàn toàn với **KMS-generated**.

### 9.1. Các mốc cần ghi cho import

- `externalGeneratedAt`: thời điểm do nguồn ngoài cung cấp; chỉ xem là xác nhận khi có evidence tương ứng.
- `externalGeneratorId` / `sourceBoundary`: nơi khóa **thực sự được sinh**.
- `importRequestedAt`, `importCompletedAt`: thời điểm nhập vào đích.
- `wrappingMechanism`, `transferProtocolRef`: cách bảo vệ key khi chuyển giao.
- `importAttestationRef`: bằng chứng nhận dạng, thuật toán/độ mạnh/exportability khi có.
- `sourceCopyDisposition`: chính sách xử lý bản sao ở nguồn sau khi nhập.
- `providerKeyRef`: định danh mới ở KMS/HSM đích.

**`importCompletedAt` không phải `generatedAt`**. Một khóa được sinh năm trước, import hôm nay và được kích hoạt tuần sau có ba mốc khác nhau.

### 9.2. Ví dụ timeline BYOK

~~~text
2026-10-01  External HSM sinh key X (sourceGeneratedAt)
2026-11-28  KMS đích nhận và hoàn tất import (importCompletedAt)
2026-12-01  KMS policy cho phép use (activationAt)

Không được ghi: "key X generated in target KMS on 2026-11-28".
~~~

Nếu policy yêu cầu khóa **được tạo bên trong HSM đích**, việc sinh ở laptop rồi import vào HSM **không đáp ứng điều kiện đó**, dù khóa sau import có được lưu an toàn. Phải đánh giá **đường sinh ban đầu, quyền xuất, bản sao còn tồn tại và trách nhiệm xóa**.

### 9.3. Khóa derived/agreed cũng cần provenance phù hợp

Key derivation qua **HKDF** hoặc một KDF khác không giống **random key generation**. Shared secret từ (EC)DH cũng không phải khóa được “import từ peer” khi hai bên độc lập tính toán. Ghi đúng `DERIVED` hoặc `KEY_AGREEMENT` khi cần inventory; với ephemeral TLS secrets, đôi khi chỉ cần quản lý **giao thức và key policy**, không ghi từng traffic secret vào danh mục dài hạn.

**Không bao giờ ghi raw DH shared secret, KDF input keying material hay session keys vào log provenance.**

## 10. Bằng chứng về nguồn sinh: không biến lời khai thành sự thật

**Evidence (bằng chứng)** là điều hỗ trợ một khẳng định có thể kiểm tra, không chỉ là một trường JSON. Có nhiều mức độ:

| Loại bằng chứng | Khẳng định có thể hỗ trợ | Giới hạn |
| --- | --- | --- |
| **Application log** | Ứng dụng đã yêu cầu `GenerateKey` tại một mốc | Ứng dụng có thể sai/đã bị chiếm; chưa chứng minh provider làm gì |
| **KMS API response** | Provider trả key reference và loại/trạng thái cụ thể | Không tự chứng minh entropy nội bộ ngoài assurance của provider |
| **Provider audit event** | Operation được xử lý dưới principal và key ID nhất định | Cần kiểm tra tính xác thực, clock và retention |
| **HSM attestation/key attributes** | Một số thuộc tính/key origin trong ranh giới được hỗ trợ | Mỗi thiết bị/provider chỉ chứng nhận một tập thuộc tính riêng |
| **Signed/append-only audit log** | Khó sửa lịch sử mà không để lại dấu vết theo mô hình bảo vệ | Không chứng minh mọi input đã đúng nếu event gốc giả |
| **Formal ceremony record** | Quy trình nhiều vai trò/approval đã được chứng kiến | Cần ràng buộc tới đúng provider key reference |
| **Trusted timestamp** | Bằng chứng thời gian độc lập ở mức assurance phù hợp | Không tự chứng minh thuật toán RNG hoặc non-extractability |

### 10.1. Phân loại độ tin cậy

Một mô hình đơn giản cho `evidenceStatus`:

~~~text
DECLARED_ONLY       — chỉ metadata do requester/app tự khai
CALLER_OBSERVED     — worker ghi nhận gần thao tác, có operation ID
PROVIDER_CONFIRMED  — provider key reference và audit/response khớp
INDEPENDENTLY_AUDITED — đã kiểm tra evidence và policy độc lập
UNKNOWN / MISSING  — chưa có bằng chứng đủ
~~~

Đây **không phải thang đo chuẩn của mọi KMS**; nên định nghĩa rõ trong governance. Cần tránh nâng mức evidence chỉ bằng một cập nhật thủ công không được kiểm soát.

### 10.2. Liên kết bằng chứng với đúng vật liệu khóa

Nếu receipt chỉ ghi `keyAlias=current`, alias có thể chuyển sang version khác. Bằng chứng phải ràng buộc **exact key ID/version hoặc object reference ổn định**, policy revision và operation ID. Với public key, có thể dùng **fingerprint public key** theo định dạng được phê duyệt; với secret key **không cần và không nên tùy ý xuất material để hash làm fingerprint**.

## 11. Audit provenance: toàn vẹn, bất biến và chống sửa lịch sử

Một record dễ sửa trong database không đủ để bảo vệ **lịch sử nguồn sinh khóa**. Hệ thống cần tách:

1. **Trạng thái hiện tại** trong inventory để trả lời nhanh.
2. **Lịch sử sự kiện** có thể đối chiếu để trả lời điều gì đã thay đổi.
3. **Evidence ngoài ứng dụng** như provider audit, approval/quorum record hoặc attestation.

~~~mermaid
flowchart LR
    Req[Request + policy decision] --> Broker[Key generation broker]
    Broker --> Provider[KMS/HSM hoặc JCA]
    Provider --> Receipt[Key reference + response/evidence]
    Receipt --> Audit[Protected append-only audit]
    Broker --> Audit
    Audit --> Inventory[Inventory hiện tại]
    Inventory --> Lifecycle[Activation / rotation / revoke]
    Lifecycle --> Audit
    Independent[Independent reviewer] --> Audit
    Independent --> Receipt
~~~

### 11.1. Chống sửa timestamp và source

- **Append-only log** với kiểm soát ghi/xóa, retention/immutability theo mức rủi ro.
- **Digital signatures hoặc MAC trên event** khi kiến trúc yêu cầu, với key quản lý riêng và chính sách rotation.
- **Hash chain / Merkle structure** có thể hỗ trợ phát hiện sửa đổi trong mô hình triển khai phù hợp; cần bảo vệ điểm neo tin cậy.
- **Sequence ID** hoặc event offset để phát hiện thiếu, lặp và đổi thứ tự.
- **Independent audit/monitoring** để phát hiện key creation ngoài workflow.
- **Access review** cho người sửa owner, policy revision, timestamp hoặc state.

**Băm một event bằng SHA-256 không tự làm log bất biến.** Nếu attacker có thể thay event và thay luôn digest, không còn bằng chứng phát hiện sửa; cần một **trust anchor, signature, log store hoặc bên kiểm chứng độc lập**.

### 11.2. Không để audit làm lộ bí mật

Log chỉ cần:

- `keyId/version`, `algorithm`, `purpose`, `providerKeyRef`.
- `operationId`, `requestId`, `principal`, `policyRevision`.
- Timestamp và **nguồn timestamp**.
- `result`, `reasonCode`, `evidenceRef`.

**Không ghi** private key, raw DEK/KEK, HMAC/PSK, password, pepper, KDF secrets, plaintext hay session token. Base64/hex của secret vẫn là **secret**, không phải dữ liệu an toàn để audit.

## 12. Generation provenance nối với key lifecycle như thế nào?

Nguồn và thời gian sinh giúp giải thích **khóa bắt đầu tồn tại như thế nào**, nhưng không thay những quy tắc về **khi nào khóa được dùng, thay thế hoặc hủy**.

~~~mermaid
flowchart TD
    Source[Entropy / provider / generation method] --> Create[Generation + evidence timestamps]
    Owner[Key owner + generation policy] --> Create
    Create --> Inventory[Key ID/version + provenance + PRE_ACTIVE]
    Inventory --> Activate[Activation policy + IAM/KMS state]
    Activate --> Active[Active: đúng purpose / cryptoperiod]
    Active --> Rotate[Rotation / new material]
    Active --> Incident[Suspected compromise / revoke]
    Rotate --> Old[Retired: xử lý dữ liệu cũ theo policy]
    Incident --> Assess[Assess ciphertext + signing trust + backups]
    Old --> Destroy[Destroy khi hết phụ thuộc]
    Assess --> Destroy
    Active --> Audit[Usage audit: actual key version]
    Destroy --> Audit
~~~

### 12.1. Những mốc thời gian có liên hệ nhưng không thay nhau

**Created/Generated:** nguồn sinh, key material bắt đầu tồn tại.  
**Pre-active:** đăng ký, kiểm thử và cấp phát nhưng chưa cho phép thao tác theo policy.  
**Active:** vừa đúng state, vừa `now >= activationAt` và chưa vượt cryptoperiod cho operation.  
**Retired/Deactivated:** không dùng tạo bảo vệ mới; có thể còn xử lý dữ liệu cũ tùy khả năng provider.  
**Revoked/Compromised:** không được tiếp tục tin cậy/dùng như trước; điều tra và thay khóa.  
**Destroyed:** material bị hủy theo assurance của nền tảng; không kết luận backup cũng không còn bản sao nếu chưa kiểm tra.

### 12.2. Quy định thời hạn theo tính chất khóa

Một KEK có thể được sinh tuần này và active tháng sau. Một DEK ngắn hạn có thể được sinh/active gần cùng thời điểm. Một TLS traffic key có thể sinh ra từ key schedule và tồn tại trong phiên rất ngắn. Một private signing key có thể được tạo trước thời gian chứng thư X.509 `notBefore` để chuẩn bị phân phối public key.

**Không áp một `createdAt + 90 ngày` cho mọi loại key.** Owner phải định nghĩa **cryptoperiod theo thuật toán, purpose, dữ liệu được bảo vệ, policy và mức rủi ro**, đồng thời giữ record nguồn sinh để điều tra.

## 13. Đặc thù theo loại khóa: DEK, KEK, ký số, PSK và khóa phiên

| Loại khóa | Provenance đáng lưu | Lưu ý về vòng đời |
| --- | --- | --- |
| **DEK AES-GCM** | Sinh từ CSPRNG/KMS nào, scope tenant/object, version, key policy | Giới hạn (key, nonce), encrypt/decrypt, re-encrypt khi DEK lộ |
| **KEK / wrapping key** | KMS/HSM key origin, key reference, quyền export, createdAt/evidence | Wrapped DEK và backup phụ thuộc; rotation/rewrap |
| **Private signing key** | Generation boundary, algorithm/curve, provider, non-extractability, audit | Chứng thư/public key binding, sign period, revoke và chữ ký lịch sử |
| **HMAC/PSK** | CSPRNG/generation boundary, những bên được cấp, policy/version | Key separation, provisioning, rotate/revoke hàng loạt khi một PSK chung lộ |
| **ECDHE/X25519 private key** | Thường ghi profile/giao thức/provider chứ không cần raw per-session material | Ephemeral; KDF, peer authentication, forward secrecy |
| **Password-derived key** | KDF algorithm, salt, cost/profile, nguồn password theo policy | Không xem password là random DEK; xử lý entropy thấp |
| **Root/CA key** | HSM/key ceremony, quorum, attestation, provenance/approval chặt | Trust anchor, high-impact rotation, archival và destruction |

### 13.1. Private signing key và public key

Private key được tạo trong HSM không có nghĩa **chứng thư đã được phát hành** hoặc public key đã được các verifier tin cậy. Nên có metadata riêng:

- `keyGeneratedAt`: thời điểm sinh key.
- `certificateIssuedAt`: thời điểm chứng thư được CA phát hành nếu có.
- `certificateNotBefore`/`NotAfter`: thời hạn hiệu lực PKI.
- `signingActivationAt`: thời điểm chính sách cho phép tạo chữ ký mới.
- `revokedAt`: thời điểm thu hồi niềm tin hoặc quyền ký, nếu xảy ra.

Một phép `Signature.verify() == true` không chứng minh chữ ký được tạo **trong thời hạn cho phép** hoặc trước khi key bị compromise. Cần **trust binding, trạng thái chứng thư, trusted timestamp** và chính sách nghiệp vụ phù hợp.

### 13.2. Khóa sinh từ key agreement

Với ECDHE, hai phía trao đổi **public key tạm thời**, cùng tính raw shared secret, sau đó qua KDF/key schedule để có traffic keys. Thông tin nguồn sinh có thể ở **giao thức, JDK/provider profile, cấu hình cipher suite và phiên bản TLS/SSH**, thay vì ghi từng traffic key vào inventory dài hạn.

Không lưu raw shared secret trong log chỉ để chứng minh hai phía tính được cùng byte. Nếu cần xác minh handshake, dựa vào **kết quả handshake/identity/audit đã được giao thức bảo vệ**.

## 14. Envelope encryption: provenance đến từ hai tầng khóa

Trong **envelope encryption**, khóa **DEK** mã hóa dữ liệu; **KEK** bảo vệ DEK. Cả hai cần metadata nguồn tạo và version nếu muốn điều tra chính xác.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Policy as Key policy / IAM
    participant KMS as KMS/HSM
    participant DB as Storage
    App->>Policy: Xin tạo/nhận DEK theo tenant và purpose
    Policy-->>App: Permission + profile được duyệt
    App->>KMS: Create/GenerateDataKey hoặc Wrap DEK
    KMS-->>App: DEK tạm thời theo API + wrapped DEK + key ref
    App->>App: AEAD encrypt với nonce không trùng theo DEK
    App->>DB: Ciphertext + tag + nonce + wrapped DEK + metadata
    App->>DB: Audit refs/key version/provenance ID (không lưu raw DEK)
    Note over App,KMS: API cụ thể và khả năng export DEK tùy provider
~~~

**Không phải mọi KMS đều trả plaintext DEK.** Sơ đồ là mô hình cho những kiến trúc có API sinh DEK và cung cấp bản rõ tạm thời; có hệ thống thực hiện phép mã hóa trực tiếp bên trong HSM/KMS hoặc hỗ trợ cách bọc khác. Cần hiểu **vật liệu sinh lần đầu tại đâu** và **đã xuất hiện trong boundary nào**.

### 14.1. Metadata cần lưu với ciphertext

Một bản mã có thể lưu **`algorithmVersion`, `dekRef` hoặc wrapped DEK, `kekKeyId/version`, `nonce/IV`, `tag`, AAD context cần thiết và `provenanceId`**. Không lưu plaintext DEK hoặc KEK.

Để giải mã, ứng dụng phải kiểm tra **đúng tenant/resource**, chọn key version phù hợp và xác minh AEAD tag. **Metadata provenance không được dùng thay authentication/authorization của bản ghi**.

### 14.2. Khi provider RNG bị nghi lỗi

Nếu một lô DEK được tạo trong khoảng provider bị ảnh hưởng, dữ liệu provenance giúp tìm **những key version và ciphertext cần đánh giá**, nhưng không đảm bảo mọi bản mã vẫn an toàn. Nếu DEK có entropy yếu/bị lộ, cần đánh giá **DEK mới và re-encrypt**; chỉ rewrap dưới KEK mới không làm DEK cũ mạnh hơn.

Với KEK bị lộ, nếu attacker đã thu thập **wrapped DEK cũ**, rewrap bản hiện tại không xóa bản sao cũ mà họ có. Phạm vi điều tra phải dựa vào key version/provenance và dữ liệu phụ thuộc.

## 15. Khi generation thành công nhưng ghi metadata thất bại

Đây là một lỗi quan trọng ở hệ thống phân tán. Ví dụ:

1. Broker gửi `CreateKey` vào KMS.
2. Provider tạo khóa thành công nhưng response timeout.
3. Broker không biết operation đã hoàn tất chưa.
4. Retry ngay mà không kiểm tra có thể **tạo thêm khóa thứ hai**.
5. Hoặc broker nhận được key reference nhưng inventory database gặp lỗi, tạo **orphan key** chưa có owner/policy.

Không nên **coi mọi lỗi mạng là “khóa chưa được tạo”**.

### 15.1. Quy trình phục hồi đề xuất

~~~mermaid
flowchart TD
    Req[Generation request + idempotency/operation ID] --> Call[Gọi provider]
    Call --> Status{Có xác nhận kết quả?}
    Status -->|Có| Register[Đăng ký key reference + provenance]
    Status -->|Timeout/không rõ| Reconcile[Tra cứu provider audit hoặc operation status]
    Reconcile --> Exists{Khóa đã tồn tại?}
    Exists -->|Có| Register
    Exists -->|Chưa rõ| Quarantine[Giữ request chưa hoàn tất, alert và điều tra]
    Exists -->|Chắc chắn chưa| Retry[Retry theo policy/idempotency]
    Retry --> Call
    Register --> Inv{Inventory commit thành công?}
    Inv -->|Có| Pre[PRE_ACTIVE + audit receipt]
    Inv -->|Không| Orphan[Quarantine key / hạn chế permission / reconcile]
~~~

**Tùy API, idempotency key có thể được provider hỗ trợ hoặc không.** Nếu không hỗ trợ, broker cần thiết kế **định danh operation, kiểm tra key references và cơ chế reconcile**; không tự giả định mọi `CreateKey` là idempotent.

### 15.2. Nguyên tắc “không active trước khi inventory nhất quán”

Khóa mới có thể tồn tại trong provider nhưng chưa có record quản trị hoàn chỉnh. Khi đó:

- Giới hạn quyền sử dụng hoặc đặt trạng thái **quarantine/pre-active** nếu nền tảng cho phép.
- Ghi **operation ID và provider key reference** vào audit/đường phục hồi đáng tin.
- Không để workload bắt đầu sử dụng key như một primary mới.
- Reconcile metadata, owner, policy, thuật toán, timestamp và backup plan.
- Nếu quyết định xóa object lỗi, kiểm tra **không có dữ liệu phụ thuộc**, tuân thủ quy trình hủy.

Không tự tạo một bản **raw key copy** trong file tạm để “backup nhanh” khi inventory lỗi. Đây là cách biến sự cố metadata thành sự cố lộ bí mật.

## 16. Audit và observability khi ghi nhận nguồn/thời điểm

Một tổ chức nên theo dõi cả **request event**, **provider event**, **inventory event** và **lifecycle event**; những luồng này bổ sung cho nhau.

### 16.1. Audit event mẫu

~~~json
{
  "eventType": "KEY_GENERATION_CONFIRMED",
  "operationId": "gen-req-20261128-001",
  "keyId": "payments-kek",
  "keyVersion": "v7",
  "ownerTeam": "payments-security",
  "principal": "approved-key-generation-broker",
  "generationMethod": "GENERATED",
  "generationBoundary": "MANAGED_HSM",
  "providerKeyRef": "kms://example/payments-kek/v7",
  "policyRevision": 12,
  "generationStartedAt": "2026-11-28T02:03:20Z",
  "generationCompletedAt": "2026-11-28T02:03:23Z",
  "providerCreatedAt": "2026-11-28T02:03:22Z",
  "providerEvidenceRef": "audit-provider-req-8001",
  "outcome": "SUCCESS"
}
~~~

Event chỉ là **mẫu minh họa**. Nó cần cơ chế xác thực nguồn, integrity, audit retention và quyền đọc được kiểm soát trước khi có giá trị chứng cứ.

### 16.2. Những chỉ số nên giám sát

| Chỉ số / cảnh báo | Ý nghĩa |
| --- | --- |
| **Unknown origin** | Key không có đủ provenance, nguồn entropy/provider chưa xác định |
| **Unmanaged key** | Provider tồn tại key không có inventory/owner |
| **Creation time mismatch** | Timestamp từ broker/provider/inventory lệch vượt ngưỡng giải thích được |
| **Unapproved generation** | Tạo key ngoài policy/approval, sai environment hoặc tenant |
| **Unexpected provider** | JCA/KMS provider đổi ngoài change plan |
| **Deprecated algorithm** | Key mới được tạo với algorithm/size không còn được duyệt |
| **Import misclassified** | Imported key bị gắn nhãn `GENERATED_IN_HSM` |
| **Orphan generation** | API thành công nhưng inventory commit thất bại |
| **Pre-active key used** | Có `Encrypt/Wrap/Sign` trước activation |
| **Duplicate operation** | Retry tạo nhiều key refs từ cùng operation |
| **Missing provider audit** | Inventory khai provider confirmed nhưng thiếu evidence |
| **Stale successor** | Key sắp hết new-use period nhưng key mới chưa được tạo/kích hoạt |

**Không nên phát cảnh báo chỉ vì timestamp lệch vài mili-giây** nếu đã biết provider và broker có clock/semantics khác nhau. Đặt ngưỡng dựa trên độ chính xác và bảo đảm thực tế, kèm đường điều tra bằng request ID/sequence.

## 17. Trường hợp thực tế: điều tra lô khóa có nguồn RNG rủi ro

Giả sử một nền tảng đa tenant sinh DEK trong các worker Java; KEK dài hạn do KMS/HSM quản lý. Nhóm vận hành phát hiện một phiên bản image đã cấu hình provider RNG không đúng **generation policy** trong một giai đoạn triển khai.

### Giai đoạn A — Tìm phạm vi

Nhóm an ninh truy vấn inventory theo `generationBoundary=LOCAL_JVM`, `rngProvider`, `runtimeImageVersion`, `generationStartedAt/CompletedAt`, `environment` và `owner`. Họ **không cần xuất tất cả DEK** để biết DEK nào có nguy cơ.

Trong hệ thống thật, có thể không ghi `runtimeImageVersion` trên từng key mà liên kết với **deployment/operation ID**. Điều quan trọng là traceability đầy đủ, không nhồi mọi loại metadata vào mỗi dòng.

### Giai đoạn B — Phân loại rủi ro

Phân biệt **provider không được phê duyệt** với **bằng chứng entropy thực sự yếu**. Cả hai cần xem xét, nhưng mức độ và phương án khắc phục khác nhau. Kiểm tra xem có raw DEK/ciphertext bị lấy, key lengths, nonce policy, mức truy cập và thời điểm bắt đầu/sửa cấu hình.

### Giai đoạn C — Containment

Ngừng tạo khóa mới từ image lỗi; triển khai generator/provider đã được phê duyệt; ngăn tiếp tục mã hóa bằng các key version có nguy cơ nếu policy quyết định. Không **tự thay nhãn provenance** của key cũ thành provider mới sau khi deploy.

### Giai đoạn D — Migration dữ liệu

Đối với DEK được đánh giá có thể yếu hoặc bị lộ, tạo DEK mới từ nguồn tin cậy rồi **re-encrypt dữ liệu** theo quy trình kiểm tra toàn vẹn. **Rewrap DEK cũ dưới KEK mới không làm tăng entropy DEK**. Với dữ liệu đã bị đối thủ đọc, rotation không thể đảo ngược việc lộ đó.

### Giai đoạn E — Đóng sự cố

Đối chiếu key refs, records/backups, dấu thời gian, owner và migration status. Chạy negative tests chống dùng lại key không được phép; giữ audit nguyên vẹn, lập lịch revoke/destroy theo retention.

**Bài học:** giá trị của việc ghi nguồn và thời điểm tạo xuất hiện rõ nhất lúc **điều tra một sự cố không thể mô phỏng lại**. Metadata đáng tin biến một quyết định “thay tất cả khóa để chắc chắn” thành một kế hoạch đánh giá phạm vi có cơ sở; tuy nhiên không được dùng độ chính xác giả của log để **đánh giá thấp rủi ro chưa biết**.

## 18. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ ghi `createdAt` không định nghĩa nguồn | Không biết đó là thời điểm KMS, broker hay inventory | Tách timestamp theo sự kiện và chủ thể ghi |
| Nhận `createdAt` từ client làm bằng chứng | Có thể backdate/sửa lịch sử | Ghi server/provider timestamp, provenance của timestamp |
| Dùng `LocalDateTime` không có timezone | Sai lệch đa vùng | `Instant` UTC hoặc timezone rõ |
| Coi JCA provider name là chứng nhận entropy/FIPS | Khẳng định độ tin cậy không có bằng chứng | Provider assurance, cấu hình và chứng cứ vận hành |
| Ghi `GENERATED_IN_HSM` cho key import từ JVM | Sai nguồn gốc và export risk | Tách generation boundary với storage boundary |
| Ghi `getEncoded()` của key vào audit | Rò rỉ secret | Chỉ ghi key reference/metadata |
| Xuất private key để hash fingerprint | Tăng bề mặt lộ key và có thể vi phạm non-extractability | Provider key ref, public-key fingerprint khi phù hợp |
| Sinh key bằng `Math.random()` rồi log timestamp đầy đủ | Key vẫn có entropy yếu | CSPRNG/KMS/HSM generation policy đúng |
| Dùng một `createdAt` thay activation time | Khóa được dùng khi chưa phê duyệt | Tách generation, provisioning, activation và cryptoperiod |
| Đổi alias sau rotation nhưng không lưu version | Không truy vết được material thực tế | Audit exact key ID/version |
| KMS timeout thì retry `CreateKey` ngay | Có thể tạo key trùng ngoài dự kiến | Idempotency/reconciliation theo API |
| Key tồn tại nhưng inventory commit lỗi | Orphan key không được quản trị | Quarantine, điều tra, không Active trước khi reconcile |
| Log hash của event nhưng ai cũng sửa được cả event và hash | Audit không chống sửa | Protected/append-only audit với trust anchor |
| Chỉ rewrap DEK yếu và tuyên bố đã thay khóa | DEK cũ vẫn yếu | DEK mới và re-encrypt khi cần |
| Xóa KEK sớm vì “đã hơn 90 ngày từ createdAt” | Không giải mã được backup | Xét recipient period, retention và restore tests |
| Quên nguồn import/BYOK | Không biết khóa từng nằm ngoài HSM | Ghi external origin, import timestamp và source-copy policy |
| Tin `providerCreatedAt` do caller tự điền | Không có bằng chứng provider | Chỉ set khi lấy từ response/audit có nghĩa rõ |
| Log đầy đủ principal/tenant ở nơi công khai | Lộ metadata quản trị | Phân loại, phân quyền và giữ audit tối thiểu |

## 19. Checklist triển khai

- [ ] Có **key ID/version** ổn định và owner/tenant/environment rõ ràng cho mỗi key quan trọng?
- [ ] Phân biệt **generation method, entropy source, RNG/DRBG, provider, boundary và storage location**?
- [ ] Có chính sách loại bỏ `Math.random()`/`Random` cho key/secret và kiểm soát provider được duyệt?
- [ ] Tách **`requestedAt`, `generationStartedAt`, `generationCompletedAt`, `providerCreatedAt`, `inventoryRecordedAt`** khi phù hợp?
- [ ] `createdAt` trong schema đã được định nghĩa chính xác, không nhập nhằng với `activationAt`?
- [ ] Timestamp dùng `Instant`/UTC hoặc định dạng có timezone rõ, lưu nguồn và mức tin cậy?
- [ ] Đã kiểm tra clock skew, time synchronization và cách tương quan thứ tự event bằng ID/sequence?
- [ ] Có lưu **`policyId/revision`, approval reference, requester/executor, key usage**?
- [ ] Key sinh trong HSM/KMS được đối chiếu **provider key reference, source assertions và audit evidence**?
- [ ] Khóa import/BYOK có `externalGeneratedAt`, source boundary, import time và chính sách bản sao?
- [ ] Mức `evidenceStatus` có định nghĩa, không tự nâng lên `PROVIDER_CONFIRMED` khi thiếu evidence?
- [ ] Key inventory **không chứa raw key** và log/trace/metrics không in private key/DEK/PSK?
- [ ] Có request/operation ID, idempotency và đường reconcile khi provider response không rõ?
- [ ] Khóa chưa đăng ký inventory đầy đủ phải **pre-active/quarantine**, không được dùng ngay?
- [ ] Activation, new-use, old-use, revoke và destruction được quản lý **độc lập với createdAt**?
- [ ] Payload mã hóa có wrapped DEK/key version, nonce/tag/AAD metadata phù hợp để restore?
- [ ] Audit có integrity/retention/access control và đối chiếu được sự kiện với provider?
- [ ] Có cảnh báo unexpected provider, orphan key, creation-time mismatch và key generation ngoài policy?
- [ ] Đã thử sự cố provider RNG không phù hợp, timeout, backup dependency và rollback?
- [ ] Đã đánh giá khả năng truy xuất lô key theo nguồn và khoảng thời gian **mà không xuất secret**?

## 20. Câu hỏi tự kiểm tra

**1. Tại sao phải lưu nguồn và thời điểm tạo khóa ngoài key ID?**  
Để kiểm tra quy trình sinh, xác định khóa bị ảnh hưởng bởi sự cố RNG/provider, quản trị cryptoperiod và hỗ trợ rotation, thu hồi, audit.

**2. `generatedAt`, `importCompletedAt` và `activationAt` có giống nhau không?**  
Không. Chúng thể hiện thời điểm sinh ở nguồn, nhập vào đích và bắt đầu được phép dùng; ba thời điểm có thể rất khác nhau.

**3. Nếu Java in `SecureRandom.getProvider().getName()`, có đủ chứng minh FIPS hoặc entropy phần cứng không?**  
Không. Đó chỉ là thông tin provider của API; cần hồ sơ/cấu hình và evidence đánh giá đúng phạm vi.

**4. Private key sinh trong JVM rồi import vào HSM có được ghi `GENERATED_IN_HSM` không?**  
Không. Nơi lưu hiện tại khác nơi key material được sinh lần đầu; nên ghi `IMPORTED` cùng nguồn ban đầu.

**5. Tại sao timestamp từ client không được xem là thời điểm provider tạo khóa?**  
Vì client có thể gửi giá trị tùy ý; cần mốc từ server/provider và nguồn chứng cứ được xác thực phù hợp.

**6. Khi KMS trả timeout, có thể gọi tạo key lại ngay không?**  
Không nên khi chưa xác định kết quả cũ. Provider có thể đã tạo key; phải reconcile bằng operation ID/audit và idempotency nếu hỗ trợ.

**7. Khi inventory ghi lỗi sau khi HSM sinh key, nên làm gì?**  
Giữ key không active hoặc quarantine, lưu operation/key reference ở đường kiểm toán tin cậy, reconcile rồi mới dùng; không tạo raw key copy ở file tạm.

**8. Nếu một lô DEK được sinh bởi nguồn entropy yếu, rewrap dưới KEK mới có đủ chưa?**  
Không. DEK vẫn yếu; phải đánh giá sinh DEK mới và re-encrypt dữ liệu, đồng thời xử lý ciphertext đã có thể bị lộ.

**9. `createdAt` có chứng minh chữ ký số được tạo tại thời điểm đó không?**  
Không. Nó ghi thời điểm sinh khóa, không phải thời điểm ký. Chữ ký lịch sử có thể cần trusted timestamp, certificate trust và trạng thái revocation.

**10. Log SHA-256 của một event có đủ chống sửa lịch sử không?**  
Không. Nếu attacker sửa cả event và digest, không phát hiện được. Cần trust anchor, protected audit store, signature/hash chaining hoặc kiểm chứng độc lập.

## Ghi nhớ

**Ghi nhận nguồn và thời điểm tạo khóa là nền tảng của provenance và key inventory đáng tin cậy.** Hãy tách rõ **nguồn entropy, RNG/provider, generation boundary, cách tạo/import/derive, thời điểm yêu cầu/bắt đầu/hoàn tất/provider/đăng ký**, gắn chúng với **key ID/version, owner, policy revision, audit evidence và trạng thái vòng đời**. Không biến tên provider hoặc timestamp do ứng dụng khai báo thành chứng nhận mật mã; không log **raw secret key** để chứng minh nguồn sinh. Quy trình đúng phải xử lý **UTC/clock skew, KMS/HSM evidence, BYOK, idempotency, orphan keys và audit chống sửa**, đồng thời liên kết với **activation, cryptoperiod, rotation, revocation, destruction, DEK/KEK, envelope encryption, chữ ký số/PKI, IAM và kiểm soát dữ liệu phụ thuộc**. Khóa chỉ thật sự được quản lý khi tổ chức không những biết *nó đang ở đâu*, mà còn biết **nó được tạo ra thế nào, khi nào, bởi ai và dựa trên bằng chứng gì**.
