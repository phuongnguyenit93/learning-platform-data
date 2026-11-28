# Client compromise — ứng phó sự cố client bị xâm nhập trong xác thực HMAC

## 1. Bối cảnh: vì sao client bị xâm nhập là sự cố nghiêm trọng?

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client sử dụng **shared secret** để tạo chữ ký HMAC cho HTTP request. Server xác minh chữ ký trên **canonical request** theo hợp đồng: phương thức HTTP, URI/path/query, một số header, timestamp, nonce và/hoặc body digest. Khi chữ ký hợp lệ, server biết bên gửi **có khả năng sử dụng secret của credential tương ứng** và các thành phần được ký không bị sửa đổi.

Đảm bảo này có một giới hạn rất quan trọng: **HMAC không chứng minh rằng máy client vẫn an toàn**. Nếu kẻ tấn công kiểm soát máy client, đánh cắp shared secret hoặc chiếm quyền chạy tiến trình ký, họ có thể tạo **request mới có chữ ký hợp lệ**. Timestamp và nonce có thể ngăn phát lại nguyên vẹn request cũ, nhưng không ngăn đối tượng đang sở hữu secret tạo timestamp mới, nonce mới và HMAC mới.

Ví dụ: hệ thống đối tác `merchant-a` gọi API chuyển tiền. Kẻ tấn công truy cập được vào container của merchant, đọc secret từ biến môi trường, rồi gửi:

~~~http
POST /v1/transfers HTTP/1.1
X-HMAC-Key-Id: merchant-a-k1
X-HMAC-Timestamp: 1795834800
X-HMAC-Nonce: 719d85c5-8b8f-42bc-b4e3-cc7f6ca87162
X-HMAC-Signature: <valid-HMAC-for-request>

{"toAccount":"attacker-account","amount":900000}
~~~

Nếu payload, timestamp, nonce và canonical request đều tuân thủ hợp đồng ký, chữ ký HMAC vẫn có thể chính xác. **Đây không phải lỗi của thuật toán HMAC; đây là sự cố tin cậy credential và môi trường client.**

**Client compromise** trong chương **Incident response** là quy trình phát hiện, giới hạn ảnh hưởng, điều tra, khôi phục và ngăn tái diễn khi có căn cứ rằng client, môi trường thực thi, khóa bí mật hoặc quyền dùng khóa đã bị xâm nhập.

Sau bài này, người học có thể:

- Phân biệt **secret bị lộ**, **host/client bị chiếm quyền**, **request bị phát lại** và **lỗi canonicalization/proxy**.
- Xác định phạm vi ảnh hưởng theo `clientId`, `keyId`, tenant, principal, quyền API và khoảng thời gian.
- Thực hiện **revoke/suspend credential**, chặn quyền gọi API trên nhiều instance và xác nhận hiệu lực.
- Xây dựng kế hoạch **key rotation** an toàn, tránh phát secret mới vào môi trường client còn bị kiểm soát.
- Bảo toàn chứng cứ, rà soát các request HMAC đã chấp nhận và hành động nghiệp vụ phát sinh.
- Viết test fail-closed, kiểm thử gateway và kiểm tra sự khác biệt giữa **xác thực** với **phân quyền**.

> **Nguyên tắc cốt lõi:** Khi secret hoặc khả năng ký bị chiếm quyền, không có phép kiểm tra HMAC nào tự phân biệt được request hợp lệ do chủ sở hữu gửi và request được kẻ tấn công ký bằng cùng secret. Cần quyết định cô lập/thu hồi theo **danh tính credential và client**, sau đó điều tra log và hành vi nghiệp vụ.

## 2. Định nghĩa sự cố và phạm vi tác động

Không phải mọi cảnh báo "signature invalid" đều là bằng chứng client bị xâm nhập. Phân loại ban đầu giúp chọn biện pháp tương xứng, nhưng **không nên chờ đủ bằng chứng tuyệt đối mới cô lập khi nguy cơ hiện tại cao**.

| Hiện tượng | Khả năng liên quan | Điều cần xác minh |
|---|---|---|
| Nhiều request HMAC **hợp lệ** từ vị trí bất thường, endpoint nhạy cảm | Secret bị lộ hoặc tiến trình client bị điều khiển | `keyId`, client, thời điểm, hành động và bằng chứng máy client |
| Secret xuất hiện trong repo, log, artifact CI hoặc hệ thống thứ ba | Rò rỉ bí mật | Ai có thể truy cập, secret còn hoạt động không, thời điểm phơi lộ |
| Host/container của client bị chiếm quyền | Attacker có thể đọc secret **hoặc sử dụng signer** mà không biết secret thô | Scope quyền trên host, thời gian tồn tại, nguồn credential |
| Request hợp lệ được gửi lại **cùng nonce** | Replay/bug retry client | Nonce store, TTL, timestamp, chính sách idempotency |
| Chữ ký lỗi tăng sau deploy gateway | Canonicalization bị thay đổi | Method, path, query, header/body đã ký trước/sau proxy |
| Nhiều request có timestamp quá cũ/tương lai | Lệch clock hoặc replay attempt | NTP, thời điểm server, cách parse epoch |
| Một client truy cập tài nguyên tenant khác dù HMAC đúng | Authorization issue hoặc credential lạm dụng | Principal, quyền đối với resource, lịch sử thao tác |

### 2.1. Phân biệt các tình huống đánh mất niềm tin

1. **Secret exposure:** Chuỗi secret có khả năng đã bị sao chép, ví dụ bị đẩy vào source control. Không thể chứng minh "chưa ai dùng" chỉ bằng việc không thấy log đáng ngờ. Giả định secret **có thể bị lạm dụng**, quyết định thu hồi theo mức độ nhạy cảm.
2. **Client runtime compromise:** Máy/ứng dụng có khả năng đang bị điều khiển. Đổi secret ngay trên host đó có thể khiến secret mới bị lấy tiếp. Phải khôi phục môi trường đáng tin trước khi cấp lại credential.
3. **Signer compromise:** Attacker có quyền gọi dịch vụ ký, HSM/KMS operation hoặc sidecar signer. Secret có thể chưa bị xuất ra nhưng attacker vẫn có thể tạo chữ ký đúng. Cần thu hồi quyền dùng signer và credential liên quan.
4. **Replay only:** Attacker chỉ có request cũ đã ký. Timestamp giới hạn cửa sổ; nonce được đăng ký atomic có thể chặn dùng lại. Nếu không có bằng chứng secret bị lộ, phạm vi xử lý có thể khác.
5. **Protocol mismatch:** Các lớp client, gateway và server ký/canonical hóa URI, query, header hoặc body khác nhau. Chữ ký không khớp có thể là lỗi tương thích, không đủ để kết luận xâm nhập.

### 2.2. Những câu hỏi phải trả lời

- Ai là **principal** đằng sau `keyId`? Có dùng chung secret cho nhiều client, tenant, môi trường hay service không?
- Credential có quyền gọi endpoint nào? Có quyền ghi, chuyển tiền, xóa dữ liệu hay tạo token phụ không?
- Credential còn hoạt động, đang rotation hay đã bị thu hồi? Có key cũ còn nằm trong thời gian overlap?
- Secret được cấp qua kênh nào và lưu ở đâu? Server nhận diện client qua `keyId`, certificate hay metadata nào?
- Có request lạ nào được **chấp nhận**, và hành động nghiệp vụ nào đã **thực thi thành công**? Hai tập sự kiện này khác nhau: xác thực qua HMAC không đồng nghĩa giao dịch đã commit.
- Có bao nhiêu gateway, vùng triển khai, bản sao cache và hàng đợi xử lý bất đồng bộ phải được cập nhật khi cô lập?

## 3. Chuỗi hành động ứng phó: nhận diện → cô lập → điều tra → khôi phục

Quy trình có thể được vận hành theo playbook sau. Mốc thời gian là **mục tiêu vận hành do tổ chức đặt**, không phải SLA chung cho mọi hệ thống; với quyền nhạy cảm, ưu tiên cô lập càng sớm càng tốt theo quy trình trực sự cố.

~~~mermaid
flowchart TD
    A["Cảnh báo / báo cáo client compromise"] --> B["Xác nhận keyId, clientId, phạm vi, mức độ"]
    B --> C["Cô lập: disable client / revoke credential"]
    C --> D["Xác minh chặn tại mọi gateway và instance"]
    D --> E["Bảo toàn chứng cứ và truy vấn hoạt động"]
    E --> F["Rà soát giao dịch, quyền và mức độ ảnh hưởng"]
    F --> G["Khôi phục môi trường client đáng tin"]
    G --> H["Cấp credential mới qua kênh an toàn"]
    H --> I["Kiểm thử HMAC, nonce, timestamp, authorization"]
    I --> J["Khôi phục theo dõi chặt, hậu kiểm và cải tiến"]
~~~

### Giai đoạn A — nhận diện và kích hoạt xử lý

Nguồn tín hiệu có thể gồm báo cáo từ đối tác, cảnh báo từ secret scanner, đăng nhập đáng ngờ vào kho bí mật, egress bất thường của client, HMAC thành công từ dải IP chưa từng thấy, đột biến số giao dịch hoặc thay đổi pattern hành vi. Không dùng duy nhất IP để khẳng định tấn công: NAT, proxy, roaming và cloud egress có thể tạo false positive.

Khi tiếp nhận, lập **incident ID**, ghi thời điểm phát hiện bằng UTC, người trực nhận, độ tin cậy ban đầu, các `clientId/keyId` nghi vấn, scope API và mức độ rủi ro nghiệp vụ. Chỉ lưu **tham chiếu bí mật**, tuyệt đối không paste giá trị secret vào ticket, chat hay email.

### Giai đoạn B — cô lập ngay nguồn ký đáng ngờ

Thứ tự hành động theo rủi ro:

1. **Chặn `clientId` hoặc principal** trên API nếu có nguy cơ nhiều credential của cùng client bị ảnh hưởng. Chặn ở tầng identity/auth policy giúp bao phủ cả key cũ và key mới đang active.
2. **Chuyển credential nghi vấn sang `SUSPENDED` hoặc `REVOKED`** trong kho quản lý có thẩm quyền. `SUSPENDED` có thể dùng để tạm dừng theo quy trình; `REVOKED` là quyết định thu hồi và không tự kích hoạt lại.
3. **Phát tán thay đổi đến mọi verifier, gateway, vùng/cluster và cache**. Nếu cache credential có TTL, đừng chỉ đợi TTL hết; cần cơ chế push invalidation, version/fencing hoặc tra cứu trạng thái online cho endpoint quan trọng. Nếu không xác minh được trạng thái mới, chính sách phản hồi phải **fail closed**.
4. **Chặn các kênh ký liên quan**: quyền gọi signer, token IAM của client, secret manager access, API gateway credential khác cùng môi trường nếu bị ảnh hưởng.
5. **Đóng băng hoặc đưa vào hàng đợi xử lý có kiểm soát** các thao tác nguy hiểm còn đang chạy. Kiểm tra queue, retry scheduler, long-running job và webhook đã lên lịch; chỉ thu hồi credential có thể chưa chặn được việc commit của request đã qua bước auth.
6. **Xác nhận cô lập bằng request kiểm thử âm tính** từ từng tuyến kết nối, không dựa riêng vào trạng thái hiển thị trên control plane.

Nếu client còn thiết bị/instance sạch và có key tách biệt, có thể giữ các credential độc lập sau khi **đánh giá bằng chứng**. Không mặc định thu hồi toàn bộ tenant nếu scope đã xác định hẹp; nhưng khi không chứng minh được ranh giới, cần cô lập rộng hơn.

> **Cẩn trọng với độ trễ:** Server có thể lấy trạng thái credential ở đầu request, sau đó mất vài giây để thực hiện chuyển tiền. Nếu thu hồi diễn ra sau bước authenticate, request đang xử lý có thể vẫn commit. Với thao tác nghiêm trọng, cần cơ chế kiểm tra trạng thái quyền/incident hold tại **điểm commit** hoặc cơ chế fencing/transaction gate; chỉ kiểm tra tại auth filter không bảo đảm dừng mọi thao tác đang bay.

### Giai đoạn C — bảo toàn chứng cứ và đánh giá tổn thất

Cô lập và điều tra phải phối hợp để không làm mất chứng cứ. Ghi lại thông tin có thể xác minh:

| Nhóm chứng cứ | Ví dụ | Lưu ý |
|---|---|---|
| Quản lý credential | `keyId`, clientId, thuật toán, trạng thái, thời điểm cấp/rotation/revocation, operator | Không xuất secret thô |
| Gateway/API ingress | Request ID, dấu thời gian, nguồn mạng ở mức cho phép, route, status, lý do auth nội bộ | Áp dụng retention và kiểm soát truy cập |
| Xác minh HMAC | Kết quả signature/timestamp/nonce, policy version, keyId, canonicalization version | Không log chữ ký đầy đủ, body hoặc canonical bytes nhạy cảm |
| Hành động nghiệp vụ | Transfer ID, order ID, principal, resource owner, kết quả commit, idempotency key | Dùng nguồn giao dịch làm bằng chứng về tác động |
| Secret access | Audit cấp/đọc secret, IAM role, lần rotate, KMS/signer invocation | Bảo vệ log truy cập |
| Client runtime | Container image, deployment event, host audit, process metadata, mạng outbound | Thu thập qua kênh điều tra an toàn |
| Hàng đợi/bất đồng bộ | Message ID, retry count, thời điểm enqueue/dequeue, worker identity | Đánh giá thao tác đã qua auth nhưng xử lý muộn |
| Quản trị và khắc phục | Ai disable/revoke, lúc nào, trạng thái propagation, kết quả probe | Lưu changelog theo incident ID |

**Lưu ý về nonce:** Nonce store thường có TTL chỉ đủ bao phủ cửa sổ replay; nó không phải hệ thống audit đầy đủ. Việc nonce không còn trong Redis **không chứng minh request chưa từng được nhận**. Dùng request log, trace và transaction ledger có retention phù hợp để điều tra lịch sử.

**Lưu ý về chữ ký:** Một chữ ký hợp lệ chỉ xác nhận rằng signer biết secret trong thời điểm tạo request. Nếu secret bị sao chép, không thể suy ra request do client thật gửi. Thông tin địa chỉ mạng, user agent và hành vi chỉ là tín hiệu hỗ trợ, không thay thế bằng chứng quyền sở hữu key.

### Giai đoạn D — khắc phục nguyên nhân gốc

Một số nguyên nhân thường gặp:

- Secret nằm trong source control, artifact build, log, error report hoặc bản sao lưu được phân quyền quá rộng.
- Secret lưu thành plaintext ở client có môi trường không an toàn; file permission yếu, dependency bị chiếm quyền hoặc host bị xâm nhập.
- Một secret dùng chung giữa nhiều dịch vụ/môi trường khiến blast radius lớn.
- HMAC signer được gọi từ tiến trình hoặc tài khoản IAM có phạm vi rộng hơn cần thiết.
- Rotation key nhưng credential cũ không bị thu hồi, các verifier có cache trạng thái lỗi thời.
- Kiểm tra signature đúng nhưng **authorization** sai: principal được phép truy cập tài nguyên của tenant khác.

Tùy nguyên nhân, biện pháp phục hồi có thể gồm rebuild client từ image/artifact đã xác minh, vá lỗ hổng, xóa persistence trái phép, thay đổi IAM và secret store policy, giới hạn egress, tách credential theo môi trường, kiểm tra dependency, thiết lập scanner và rà soát các bản sao log chứa bí mật.

**Không cấp shared secret mới cho máy client vẫn có dấu hiệu bị điều khiển.** Nếu cần cấp khẩn cấp, dùng một môi trường khởi tạo độc lập, danh tính nhận key đã xác minh và kênh phân phối có kiểm soát; ghi rõ rủi ro còn lại cùng người phê duyệt ngoại lệ.

### Giai đoạn E — khôi phục và theo dõi tăng cường

Khi môi trường client đã đáng tin trở lại:

1. Sinh **secret mới** bằng CSPRNG hoặc hệ thống quản lý khóa phù hợp; dùng **`keyId` mới**. Không chỉ đổi tên `keyId` rồi giữ secret cũ.
2. Gắn policy rõ ràng cho credential: `clientId`, thuật toán HMAC cho phép, scope, trạng thái, thời gian cấp và kế hoạch thu hồi.
3. Phân phối secret qua kênh bảo mật đến client đã được xác minh; không đưa secret vào ticket hoặc log.
4. Test request HMAC với canonical method, URI, header/body, timestamp, nonce qua **gateway thực**. Xác nhận request hợp lệ được nhận và request ký bằng key cũ bị từ chối.
5. Test một request **timestamp hết hạn**, một request **nonce lặp**, một request **sửa body/query**, một request **không đủ quyền**. Khôi phục credential không đồng nghĩa vô hiệu các kiểm soát khác.
6. Mở lại từng luồng nghiệp vụ cần thiết và theo dõi chặt tần suất request, hành vi nhạy cảm, lỗi auth và dấu hiệu lạm dụng.

Trong sự cố đã xác nhận **secret bị lộ**, không dùng giai đoạn overlap chấp nhận cả key cũ và key mới như một cuộc rotation thông thường, trừ trường hợp ngoại lệ được đánh giá rủi ro và kiểm soát cụ thể. Để key cũ hoạt động trong overlap cho phép attacker tiếp tục ký request hợp lệ.

## 4. Thiết kế credential lifecycle phục vụ incident response

Một sơ đồ trạng thái rõ ràng giúp lập trình và vận hành nhất quán:

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONED
    PROVISIONED --> ACTIVE: client onboard
    ACTIVE --> SUSPENDED: incident hold
    SUSPENDED --> ACTIVE: resume after verified false alarm
    ACTIVE --> REVOKED: confirmed compromise / retirement
    SUSPENDED --> REVOKED: confirmed compromise
    REVOKED --> [*]
~~~

Trong trường hợp **REVOKED**, không cho phép kích hoạt lại cùng secret/keyId. Sau phục hồi, cấp một credential mới. Trạng thái `SUSPENDED` nên đi cùng client-level block nếu chưa xác định key nào bị lộ, vì một client có thể có nhiều key đang active.

| Hành động | Ý nghĩa | Điểm cần kiểm tra |
|---|---|---|
| `suspendCredential(keyId)` | Tạm ngừng xác thực với một key | Tất cả verifier từ chối key này |
| `blockClient(clientId)` | Chặn mọi credential thuộc một client | Các key cũ/mới và mọi thuật toán đều bị chặn |
| `revokeCredential(keyId)` | Thu hồi không thể tái kích hoạt | Key không được chấp nhận sau propagation |
| `provisionNewCredential(clientId)` | Cấp secret mới cho client sạch | Kênh cấp an toàn, scope ít quyền, thuật toán policy |
| `unblockClient(clientId)` | Mở lại sau khi xác nhận phục hồi | Chỉ credential mới/được cho phép hoạt động |
| `invalidateAuthCache(version)` | Đồng bộ tình trạng trên các node | Không có node giữ credential bị thu hồi |
| `holdSensitiveOperations(clientId)` | Dừng side effect nghiệp vụ | Không còn giao dịch đáng ngờ đang xử lý |

**Điểm nguy hiểm khi scale:** cache credential chạy trên nhiều ứng dụng hoặc vùng có thể giữ `ACTIVE` sau khi record nguồn đã thành `REVOKED`. Với endpoint quan trọng, giải pháp có thể dùng denylist phân tán tra cứu theo request, sự kiện invalidation có xác nhận, cache có policy version được xác minh hoặc một authorization gate tập trung. Cần đo **độ trễ thu hồi thực tế** từ thời điểm thao tác điều hành đến lúc mọi đường dữ liệu từ chối request.

## 5. Mẫu Java 17: chặn credential trước khi xác thực

Đoạn code sau minh họa *policy gate*, tách khỏi thuật toán tính HMAC. Nó cho thấy cách kiểm tra tình trạng credential và toàn client trước khi verifier làm việc. Đây **không** phải implementation hoàn chỉnh của toàn bộ HTTP HMAC authentication.

**`CredentialIncidentGate.java`**

~~~java
import java.util.Objects;
import java.util.Optional;

public final class CredentialIncidentGate {

    public enum CredentialStatus {
        ACTIVE, SUSPENDED, REVOKED
    }

    public record CredentialSnapshot(
            String keyId,
            String clientId,
            CredentialStatus status,
            long policyVersion) {

        public CredentialSnapshot {
            Objects.requireNonNull(keyId);
            Objects.requireNonNull(clientId);
            Objects.requireNonNull(status);
        }
    }

    public interface PolicyStore {
        // Bản production phải cung cấp dữ liệu trạng thái tin cậy,
        // nhất quán với yêu cầu propagation của hệ thống.
        Optional<CredentialSnapshot> findByKeyId(String keyId);
        boolean isClientBlocked(String clientId);
    }

    public enum Decision {
        ALLOW_TO_VERIFY_HMAC,
        DENY_UNKNOWN_KEY,
        DENY_CREDENTIAL_INACTIVE,
        DENY_CLIENT_BLOCKED
    }

    private final PolicyStore policyStore;

    public CredentialIncidentGate(PolicyStore policyStore) {
        this.policyStore = Objects.requireNonNull(policyStore);
    }

    public Decision check(String keyId) {
        if (keyId == null || !keyId.matches("[A-Za-z0-9_-]{1,96}")) {
            return Decision.DENY_UNKNOWN_KEY;
        }

        Optional<CredentialSnapshot> snapshot =
                policyStore.findByKeyId(keyId);

        if (snapshot.isEmpty()) {
            return Decision.DENY_UNKNOWN_KEY;
        }

        CredentialSnapshot credential = snapshot.get();
        if (credential.status() != CredentialStatus.ACTIVE) {
            return Decision.DENY_CREDENTIAL_INACTIVE;
        }

        if (policyStore.isClientBlocked(credential.clientId())) {
            return Decision.DENY_CLIENT_BLOCKED;
        }

        return Decision.ALLOW_TO_VERIFY_HMAC;
    }
}
~~~

**Cách tích hợp:** Tại HTTP verifier, lấy `keyId` từ header đã kiểm tra cú pháp/duplicate; gọi `CredentialIncidentGate.check(keyId)`; chỉ khi gate cho phép mới lấy secret từ kho bí mật và xác minh HMAC, timestamp, nonce. Sau khi xác thực, ánh xạ credential sang principal và tiếp tục authorization. Nếu read policy store lỗi hoặc timeout, phải **từ chối/đặt on-hold**, không mặc định coi client là ACTIVE.

Lưu ý: mã mẫu không ném exception khi `PolicyStore` bị lỗi. Trong ứng dụng thật, tầng gọi phải chuyển lỗi phụ thuộc này sang **fail closed**; không biến lỗi thành `ALLOW_TO_VERIFY_HMAC`. Đừng đưa thông tin `keyId` có tồn tại hay không ra công khai: các kết quả `DENY_*` là phân loại **nội bộ**, phản hồi API nên tuân thủ một chính sách lỗi nhất quán.

Với hệ thống phân tán, hai lời gọi `findByKeyId` và `isClientBlocked` có thể quan sát trạng thái ở các phiên bản khác nhau. Đối với quyền có rủi ro cao, cần snapshot policy nhất quán, epoch/version và kiểm tra lại tại điểm commit, hoặc thực hiện một truy vấn gate tập trung để giảm race condition. Đoạn code trên thể hiện **điểm chặn cần có**, không tự giải quyết mọi race condition.

### Kiểm thử policy gate bằng JUnit 5

**`CredentialIncidentGateTest.java`**

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import org.junit.jupiter.api.Test;

class CredentialIncidentGateTest {
    static class FakePolicyStore implements CredentialIncidentGate.PolicyStore {
        final Map<String, CredentialIncidentGate.CredentialSnapshot> keys =
                new HashMap<>();
        final Set<String> blockedClients = new HashSet<>();

        @Override
        public Optional<CredentialIncidentGate.CredentialSnapshot>
                findByKeyId(String keyId) {
            return Optional.ofNullable(keys.get(keyId));
        }

        @Override
        public boolean isClientBlocked(String clientId) {
            return blockedClients.contains(clientId);
        }

        void put(String keyId, String clientId,
                 CredentialIncidentGate.CredentialStatus status) {
            keys.put(keyId, new CredentialIncidentGate.CredentialSnapshot(
                    keyId, clientId, status, 1L));
        }
    }

    @Test
    void compromiseBlocksOnlyAffectedKeyWhenScopeIsNarrow() {
        FakePolicyStore store = new FakePolicyStore();
        store.put("clientA-old", "clientA",
                CredentialIncidentGate.CredentialStatus.REVOKED);
        store.put("clientA-new", "clientA",
                CredentialIncidentGate.CredentialStatus.ACTIVE);
        store.put("clientB-key", "clientB",
                CredentialIncidentGate.CredentialStatus.ACTIVE);

        var gate = new CredentialIncidentGate(store);

        assertEquals(
                CredentialIncidentGate.Decision.DENY_CREDENTIAL_INACTIVE,
                gate.check("clientA-old"));
        assertEquals(
                CredentialIncidentGate.Decision.ALLOW_TO_VERIFY_HMAC,
                gate.check("clientA-new"));
        assertEquals(
                CredentialIncidentGate.Decision.ALLOW_TO_VERIFY_HMAC,
                gate.check("clientB-key"));
    }

    @Test
    void blockingEntireClientStopsEveryCredentialImmediatelyInStore() {
        FakePolicyStore store = new FakePolicyStore();
        store.put("clientA-old", "clientA",
                CredentialIncidentGate.CredentialStatus.ACTIVE);
        store.put("clientA-new", "clientA",
                CredentialIncidentGate.CredentialStatus.ACTIVE);
        store.put("clientB-key", "clientB",
                CredentialIncidentGate.CredentialStatus.ACTIVE);

        var gate = new CredentialIncidentGate(store);
        store.blockedClients.add("clientA");

        assertEquals(CredentialIncidentGate.Decision.DENY_CLIENT_BLOCKED,
                gate.check("clientA-old"));
        assertEquals(CredentialIncidentGate.Decision.DENY_CLIENT_BLOCKED,
                gate.check("clientA-new"));
        assertEquals(CredentialIncidentGate.Decision.ALLOW_TO_VERIFY_HMAC,
                gate.check("clientB-key"));
    }

    @Test
    void unknownOrSuspendedCredentialsAreDenied() {
        FakePolicyStore store = new FakePolicyStore();
        store.put("clientA-key", "clientA",
                CredentialIncidentGate.CredentialStatus.SUSPENDED);

        var gate = new CredentialIncidentGate(store);

        assertEquals(CredentialIncidentGate.Decision.DENY_CREDENTIAL_INACTIVE,
                gate.check("clientA-key"));
        assertEquals(CredentialIncidentGate.Decision.DENY_UNKNOWN_KEY,
                gate.check("unknown"));
        assertEquals(CredentialIncidentGate.Decision.DENY_UNKNOWN_KEY,
                gate.check(null));
    }
}
~~~

Các test ở đây chứng minh logic **trên fake store cục bộ**. Chúng **không** chứng minh cache đa vùng đã invalidated hoặc request đang xử lý đã dừng. Phải bổ sung integration test kiểm tra propagation, concurrency và điểm commit.

## 6. Kiểm chứng hiệu lực cô lập trên API thật

Khi xử lý sự cố, chỉ nhìn thấy `status = REVOKED` trong database là chưa đủ. Cần xác nhận cả **control plane** (cập nhật policy) và **data plane** (mọi đường gọi API) đồng thuận.

| Test | Cách tạo request | Kỳ vọng |
|---|---|---|
| IR-01 | Request ký đúng bằng `keyId` bị revoke, timestamp mới, nonce mới | Từ chối xác thực |
| IR-02 | Request ký đúng bằng key khác của **cùng client đang blocked** | Từ chối xác thực |
| IR-03 | Request hợp lệ từ client khác không bị ảnh hưởng | Hoạt động theo policy thông thường |
| IR-04 | Request đã verify HMAC ngay trước lúc revoke, chuẩn bị thực hiện side effect | Bị dừng tại operation/commit gate nếu policy yêu cầu |
| IR-05 | Request đi qua gateway/node/region khác nhau sau revoke | Tất cả từ chối credential bị ảnh hưởng |
| IR-06 | Key cũ thuộc giai đoạn rotation overlap, vừa bị revoke do compromise | Không còn được nhận |
| IR-07 | Key mới trên client đã khôi phục, timestamp/nonce hợp lệ | Xác thực thành công, sau đó kiểm tra authorization |
| IR-08 | Key mới với nonce đã dùng hoặc timestamp quá hạn | Từ chối do replay/freshness |
| IR-09 | Key mới với method, URI/query hoặc body bị sửa sau khi ký | Từ chối do HMAC không khớp |
| IR-10 | Key mới HMAC đúng nhưng principal không được phép truy cập tài nguyên khác tenant | Từ chối ở authorization |

**Cẩn trọng khi kiểm thử trên production:** dùng endpoint kiểm tra không gây side effect hoặc fixture nghiệp vụ được ủy quyền, tránh phát sinh giao dịch thật. Với IR-04 nên dùng môi trường staging có barrier/fault injection để tái hiện race giữa revoke và commit. Ghi incident ID, request ID và kết quả probe, không lưu secret hay signature đầy đủ.

### 6.1. Tương tác với timestamp, nonce và canonicalization

Trường hợp "key đã revoke nhưng request vẫn được nhận" phải được thử bằng **request ký đúng** trên key cũ với timestamp và nonce mới. Nếu chỉ tái phát nguyên request cũ, server có thể từ chối vì nonce lặp hoặc timestamp hết hạn; test đó **không chứng minh** thu hồi key đã có hiệu lực.

Tương tự, nếu thay đổi URL, header hoặc body sau khi ký, lỗi HMAC có thể che giấu lỗi revocation. Mỗi test cần kiểm soát biến độc lập để biết kết quả từ chối xuất phát từ **policy gate**, **signature**, **freshness** hay **authorization**.

Khi đi qua proxy, cần test cả request-target nguyên bản, quy tắc query/path normalization và header casing. Gateway có thể rewrite URI hoặc làm khác thứ tự query, gây lỗi chữ ký nhưng không liên quan client compromise. Chẩn đoán theo mã nội bộ, không suy diễn mọi `401` là "key revoked".

### 6.2. Tương tác với key rotation

Một khách hàng có thể đồng thời có `key-old` và `key-new` theo kế hoạch rotation. Khi nghi ngờ secret cũ bị lộ:

- Thu hồi `key-old`, xác minh nó không còn được chấp nhận ở mọi verifier.
- Đánh giá môi trường cấp key mới: nếu client runtime còn bị chiếm quyền, cả `key-new` cũng có thể đang lộ.
- Không tự động dùng fallback sang key khác nếu chữ ký không khớp. Mỗi `keyId` phải trỏ tới credential/secret/algorithm được quản lý server-side.
- Nếu thay đổi thuật toán HMAC, policy allowlist và algorithm binding theo key phải được kiểm tra song song với trạng thái revoke.
- Nếu nhiều service dùng chung secret, lập danh sách phụ thuộc và thu hồi/rotate trên **mọi điểm sử dụng** tương ứng.

## 7. Thiết kế monitoring và tiêu chí đánh giá sự cố

### 7.1. Metrics hữu ích

| Metric hoặc sự kiện | Ý nghĩa |
|---|---|
| `hmac_auth_attempts_total{result,reason}` | Xu hướng pass/reject, phân loại lỗi nội bộ |
| `hmac_revoked_key_attempts_total` | Sau revoke có còn request dùng credential cũ không |
| `client_blocked_attempts_total` | Đường truy cập tiếp tục dùng client bị chặn |
| `credential_revocation_propagation_seconds` | Độ trễ giữa revoke và mọi đường dữ liệu áp dụng |
| `hmac_nonce_replay_total` | Request trùng nonce, có thể là replay hoặc retry lỗi |
| `hmac_timestamp_out_of_window_total` | Lệch đồng hồ hoặc replay attempt |
| `sensitive_actions_total{client,action,result}` | Hành vi nghiệp vụ quan trọng để rà soát |
| `credential_secret_access_events` | Hoạt động truy cập/quản trị secret bất thường |

**Không đưa raw secret, full signature, nonce hoặc `keyId` dạng cardinality quá cao vào metric labels.** Dùng nhãn tập hợp có kiểm soát và đặt chi tiết cần điều tra vào hệ thống audit bảo mật với quyền truy cập giới hạn. Những hệ thống giao dịch nhạy cảm nên bảo đảm log/audit có time synchronization và retention đủ dài.

### 7.2. Tín hiệu đã cô lập thành công

Một incident có thể coi là **đã được kiểm soát ở lớp xác thực** khi:

1. Mọi gateway/instance xác nhận đang dùng policy mới.
2. Probe bằng credential bị revoke (signature đúng, timestamp/nonce mới) đều bị từ chối.
3. Không có luồng nghiệp vụ nhạy cảm nào tiếp tục commit dưới principal bị block, theo tiêu chí nhất quán của hệ thống.
4. Các job/queue/retry liên quan đã bị kiểm soát.
5. Hoạt động audit đủ để đánh giá sự kiện trước và sau thời điểm cô lập.

Điều này **không đồng nghĩa** sự cố đã kết thúc. Vẫn cần xác định tác động lên dữ liệu, giao dịch, đối tác và nguyên nhân gốc; đồng thời theo quy trình pháp lý/vận hành áp dụng nếu có yêu cầu thông báo.

### 7.3. Tình huống bàn giao ca trực

Ví dụ bản tóm tắt sự cố không chứa bí mật:

~~~text
Incident: IR-HMAC-2026-017
Affected client: merchant-a
Affected credentials: merchant-a-k1 (REVOKED)
Client-level block: ENABLED
Detected at (UTC): 2026-11-28T03:00:00Z
Containment action (UTC): 2026-11-28T03:06:00Z
Propagation verified: 3 regions, 12 auth instances
Signed requests under review: 48 accepted requests in scoped interval
Business transactions under review: 5 completed, 2 pending review
Open items: client endpoint rebuild; ledger reconciliation; new key issuance
Evidence references: secure audit case IDs only
~~~

Các số liệu trên **hoàn toàn minh họa**. Trong thực tế phải rút số liệu từ monitoring, audit và transaction ledger, lưu dấu nguồn và xác định đâu là nhận định chưa được xác minh.

## 8. Bài tập thực hành: diễn tập client compromise

**Bối cảnh:** API sử dụng HMAC-SHA256. `client-a` có key `a-old` và `a-new` đang active trong quá trình rotation; `client-b` dùng `b-key`. Cảnh báo phát hiện secret của `a-old` trong artifact CI public. `client-a` có quyền tạo thanh toán, `client-b` chỉ đọc đơn hàng.

### Nhiệm vụ 1 — xác định phạm vi

Lập sơ đồ từ `keyId` đến `clientId`, principal, tenant, endpoint, thuật toán, môi trường và nơi cấp secret. Trả lời liệu `a-new` có bị ảnh hưởng không, dựa trên dữ liệu về nơi lưu/triển khai chứ không đoán.

### Nhiệm vụ 2 — cô lập

Chặn `client-a` nếu chưa xác định phạm vi rò rỉ, revoke `a-old` và xác minh trên gateway/service. Kiểm tra rằng `client-b` vẫn thực hiện được request theo quyền của mình. Không cấp thêm secret cho container của `client-a` khi chưa làm sạch.

### Nhiệm vụ 3 — kiểm thử với HMAC thật

Viết integration test gửi những request sau:

1. `a-old` + HMAC đúng + timestamp hiện tại + nonce duy nhất → **401/deny authentication**.
2. `a-new` + HMAC đúng nhưng `client-a` đang blocked → **deny authentication**.
3. `b-key` + HMAC đúng + nonce duy nhất + endpoint đọc được phép → **pass authentication; authorized action**.
4. `b-key` + HMAC đúng nhưng gọi API thanh toán không được cấp quyền → **pass authentication; deny authorization**.
5. `a-old` + request cũ/nonce lặp → bị từ chối, nhưng **không dùng kết quả này** để chứng minh revoke đã hoạt động.

Sau khi client được rebuild, cấp `a-recovered` qua kênh an toàn, xác nhận positive path cho key mới và negative path cho key cũ. Đo độ trễ propagation từ thời điểm revoke đến khi tất cả node từ chối.

### Nhiệm vụ 4 — rà soát tác động

Xây dựng truy vấn (trên tập audit đã được phân quyền) để lấy request đã xác thực dưới `a-old` trong khoảng từ **thời điểm có khả năng bị lộ sớm nhất** đến khi cô lập thành công. Ghép request ID với transaction ID và ledger, phân loại: rejected, accepted nhưng không commit, committed, pending hoặc cần xác minh thêm. Chỉ kết luận tác động từ nguồn dữ liệu nghiệp vụ đáng tin.

### Nhiệm vụ 5 — hậu kiểm

Ghi lại nguyên nhân, phạm vi, thời gian phát hiện/cô lập, độ trễ propagation, các chốt kiểm soát thiếu, kế hoạch loại bỏ secret khỏi CI artifact, quy trình rotation mới và chủ sở hữu từng action item. Lặp lại diễn tập với tình huống **signer bị chiếm quyền nhưng secret không bị xuất ra** để bảo đảm playbook không phụ thuộc vào chứng cứ "secret đã lộ".

## 9. Checklist runbook khi đóng sự cố

- [ ] Có incident ID, timeline UTC, owner và mô tả mức độ tin cậy của bằng chứng.
- [ ] Đã xác định phạm vi `clientId`, `keyId`, tenant, quyền API, môi trường và key đang rotation.
- [ ] Credential nghi vấn đã suspend/revoke; client-level block đã áp dụng nếu cần.
- [ ] Đã xác minh **mọi instance/gateway/region** từ chối request có HMAC đúng nhưng key bị thu hồi.
- [ ] Các giao dịch đang xử lý, job bất đồng bộ, retry và idempotency workflow đã được kiểm soát.
- [ ] Đã bảo toàn audit/log/transaction evidence cần thiết mà không sao chép secret thô.
- [ ] Đã đánh giá request được chấp nhận, hành động đã commit và tác động lên tài nguyên/tenant.
- [ ] Đã xử lý nguyên nhân gốc và khôi phục môi trường client đủ tin cậy.
- [ ] Key mới được cấp qua kênh an toàn với scope ít quyền; key cũ không thể tái kích hoạt.
- [ ] Đã kiểm thử canonical request, chữ ký, timestamp, nonce, key rotation và gateway.
- [ ] Authorization được kiểm thử độc lập sau authentication.
- [ ] Có theo dõi sau khôi phục, hậu kiểm và action item có owner/hạn xử lý.

**Ghi nhớ:** Trong mô hình HMAC, sự an toàn của **shared secret và môi trường sử dụng nó** quan trọng ngang với thuật toán ký. Khi client bị xâm nhập, chữ ký hợp lệ không còn đủ để tin tưởng hành động. Năng lực ứng phó được thể hiện qua việc **thu hồi có hiệu lực, xác minh toàn tuyến, điều tra tác động thực tế và chỉ cấp lại credential cho môi trường đã phục hồi**.
