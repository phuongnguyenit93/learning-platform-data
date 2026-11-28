# Theo dõi trạng thái credential trong vòng đời xác thực HMAC

## 1. Vì sao phải theo dõi trạng thái credential?

Trong hệ thống xác thực HTTP request bằng HMAC, mỗi client được cấp một **credential** gồm định danh khóa (key ID) và một bí mật chia sẻ (shared secret). Client tạo chữ ký từ một canonical request theo hợp đồng ký; server tìm credential tương ứng để xác minh chữ ký. Chữ ký hợp lệ chỉ chứng minh người gửi đang sở hữu secret tương ứng tại thời điểm kiểm tra. Server còn phải xác định **credential đó có được phép sử dụng hay không**.

Ví dụ, đối tác thanh toán gửi request với key ID còn tồn tại và chữ ký đúng, nhưng quản trị viên đã thu hồi key do nghi ngờ bị lộ. Nếu server chỉ xác minh HMAC mà không kiểm tra trạng thái credential, request vẫn được chấp nhận. Tương tự, key đã hết hạn hoặc đang tạm khóa không được phép ký request mới dù secret chưa thay đổi.

Theo dõi trạng thái credential có hai nhiệm vụ gắn liền nhau:

1. **Thực thi chính sách tại lúc xác thực:** quyết định một key ID có còn đủ điều kiện để được dùng xác minh request hay không.
2. **Quan sát vòng đời khi vận hành:** biết key nào đang hoạt động, sắp hết hạn, bị tạm khóa, được xoay vòng, bị thu hồi; phát hiện trạng thái không đồng nhất giữa các instance và lưu bằng chứng thay đổi.

Bài này tập trung vào vòng đời credential của cơ chế HMAC request authentication. Các kiểm tra canonical request, timestamp/nonce chống replay và phân quyền vẫn cần thực hiện nhưng có trách nhiệm khác với kiểm tra trạng thái credential.

## 2. Phân biệt trạng thái cấu hình và trạng thái hiệu lực

Không nên gói mọi thông tin vào một trường trạng thái duy nhất. Một credential có thể được ghi nhận là ACTIVE trong cơ sở dữ liệu nhưng đã vượt quá thời điểm hết hạn. Cách thiết kế rõ ràng là phân biệt:

- **Trạng thái cấu hình (lifecycle state):** do thao tác cấp phát, tạm khóa, mở khóa, nghỉ sử dụng hoặc thu hồi thay đổi.
- **Trạng thái hiệu lực (effective state):** kết quả đánh giá trạng thái cấu hình **cùng** thời gian hiệu lực và các điều kiện bảo mật tại thời điểm server xử lý.

Một tập trạng thái cấu hình mẫu:

| Trạng thái | Ý nghĩa | Cho phép xác thực request? |
| --- | --- | --- |
| PENDING | Đã tạo bản ghi nhưng chưa kích hoạt/cấp phát hoàn tất | Không |
| ACTIVE | Được phép dùng nếu đang trong khoảng hiệu lực | Có điều kiện |
| SUSPENDED | Tạm dừng để điều tra hoặc chờ xử lý | Không |
| REVOKED | Thu hồi do mất tin cậy, rò rỉ hoặc quyết định bảo mật | Không; trạng thái kết thúc |
| RETIRED | Ngừng sử dụng theo kế hoạch, thường sau key rotation | Không; trạng thái kết thúc |

Ngoài các trạng thái trên, **NOT_YET_VALID** và **EXPIRED** là kết quả đánh giá theo thời gian. Với quy ước khoảng hiệu lực nửa mở:

> Credential có hiệu lực về thời gian khi valid_from ≤ thời gian server hiện tại và (expires_at chưa đặt hoặc thời gian server hiện tại < expires_at).

Tại đúng mốc expires_at, credential **đã hết hạn**. Không cần một tác vụ nền đổi ACTIVE thành EXPIRED để chặn xác thực: server phải kiểm tra expires_at ngay trong luồng xử lý request. Một tác vụ định kỳ có thể đánh dấu hoặc tổng hợp các credential hết hạn để phục vụ báo cáo, nhưng tác vụ đó không được trở thành điều kiện bắt buộc để ngăn key hết hạn.

**Quy tắc ưu tiên:** nếu credential đồng thời bị thu hồi và hết hạn, trả kết luận nội bộ REVOKED để giữ nguyên thông tin thu hồi; nếu ACTIVE nhưng chưa tới valid_from thì NOT_YET_VALID; nếu ACTIVE và quá expires_at thì EXPIRED. Bất kể mã lý do nội bộ, phía client chỉ nhận phản hồi xác thực đã được chuẩn hóa, tránh tiết lộ chi tiết về sự tồn tại của key.

### Sơ đồ vòng đời

~~~mermaid
flowchart LR
    P[PENDING] -->|Kích hoạt| A[ACTIVE]
    A -->|Tạm khóa| S[SUSPENDED]
    S -->|Mở khóa có kiểm soát| A
    A -->|Thu hồi| R[REVOKED]
    S -->|Thu hồi| R
    A -->|Kết thúc rotation| T[RETIRED]
    S -->|Ngừng sử dụng| T
    A -.->|Qua expires_at| E[EXPIRED - trạng thái hiệu lực]
~~~

Đây là **một chính sách ví dụ**, không phải danh sách trạng thái bắt buộc của giao thức HMAC. Dự án có thể chọn tập trạng thái ít hơn hoặc thêm quy trình phê duyệt, nhưng phải định nghĩa rõ trạng thái nào chấp nhận request và trạng thái nào không thể khôi phục. Với chính sách minh họa này, không chuyển trực tiếp REVOKED hoặc RETIRED về ACTIVE; nếu cần dùng lại dịch vụ, phát hành credential mới với key ID và secret mới.

## 3. Dữ liệu cần lưu để có thể kiểm tra và giám sát

Một bản ghi credential thường cần các thuộc tính sau:

| Trường | Mục đích |
| --- | --- |
| credential_id | Định danh nội bộ ổn định của bản ghi |
| key_id | Định danh client gửi cùng request để server tra cứu key |
| principal_id | Danh tính ứng dụng/đối tác mà credential thuộc về |
| secret_ref | Tham chiếu đến secret trong hệ thống quản lý bí mật |
| lifecycle_state | PENDING, ACTIVE, SUSPENDED, REVOKED hoặc RETIRED |
| valid_from, expires_at | Khoảng thời gian có hiệu lực; dùng thời gian server |
| revoked_at | Dấu mốc thu hồi phục vụ kiểm tra và kiểm toán |
| state_changed_at, version | Thời điểm và phiên bản thay đổi trạng thái |
| created_at | Thời điểm phát hành bản ghi |
| rotated_from_id | Liên hệ với credential cũ, nếu được cấp qua rotation |

Ví dụ lược đồ PostgreSQL giản lược:

~~~sql
CREATE TABLE hmac_credentials (
    credential_id UUID PRIMARY KEY,
    key_id VARCHAR(96) NOT NULL UNIQUE,
    principal_id UUID NOT NULL,
    secret_ref VARCHAR(256) NOT NULL,
    lifecycle_state VARCHAR(16) NOT NULL
        CHECK (lifecycle_state IN (
            'PENDING', 'ACTIVE', 'SUSPENDED', 'REVOKED', 'RETIRED'
        )),
    valid_from TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    state_changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,
    rotated_from_id UUID REFERENCES hmac_credentials(credential_id),
    CHECK (expires_at IS NULL OR expires_at > valid_from)
);
~~~

Lược đồ này dùng secret_ref để trỏ đến secret được bảo vệ trong vault/KMS hoặc kho bí mật tương đương; **không lưu secret dạng rõ trong nhật ký, sự kiện hay API quản trị**. Nếu triển khai cho phép expires_at rỗng, phải có chính sách riêng về thời hạn tối đa và rà soát credential không có hạn dùng. key_id cần duy nhất, không được âm thầm tái sử dụng cho một secret khác; tránh việc cache tra cứu hoặc log lịch sử quy chiếu nhầm credential.

Thông tin **sử dụng thực tế** nên lưu ở luồng telemetry/audit riêng, chẳng hạn last_successful_use_at, số lần xác thực thất bại, thời điểm sử dụng cuối cùng và nhóm nguyên nhân thất bại. Không nên cập nhật một hàng hmac_credentials trong mỗi request thành công: cách này tạo tranh chấp ghi, tăng tải cơ sở dữ liệu và khiến đường xác thực phụ thuộc vào hệ thống thống kê. Nếu last_successful_use_at được cập nhật bất đồng bộ, giao diện quản trị phải ghi rõ độ trễ dữ liệu và không coi đó là bằng chứng rằng credential vẫn ACTIVE.

## 4. Kiểm tra trạng thái trong luồng xác thực request

Một luồng xử lý HMAC điển hình:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway / API
    participant R as Credential registry
    participant N as Replay store
    C->>G: HTTP request + keyId + timestamp + nonce + signature
    G->>R: Lấy credential theo keyId
    R-->>G: Trạng thái, thời hạn, tham chiếu secret, version
    G->>G: Kiểm tra trạng thái hiệu lực
    G->>G: Kiểm tra hợp đồng canonical request và HMAC
    G->>G: Kiểm tra timestamp trong cửa sổ chấp nhận
    G->>N: Ghi nonce nếu chưa tồn tại (atomic)
    N-->>G: Thành công / đã sử dụng
    G->>G: Phân quyền principal cho tài nguyên
    G-->>C: Chấp nhận hoặc từ chối request
~~~

Cần giữ các ranh giới sau:

1. **Tra cứu theo key ID:** nếu không tìm thấy credential hoặc đọc trạng thái thất bại mà không có nguồn đáng tin cậy, từ chối xác thực theo chính sách fail closed.
2. **Kiểm tra hiệu lực:** chỉ cho credential ở ACTIVE và còn trong khoảng valid_from/expires_at được đi tiếp. Không dùng dữ liệu “key từng ACTIVE” trong cache quá giới hạn freshness đã định.
3. **Xác minh chữ ký:** lấy secret qua secret_ref, tái tạo canonical request theo hợp đồng ký đã thống nhất (method, URI, query, header, body hoặc digest body tùy thiết kế), rồi so sánh HMAC theo cách không phụ thuộc vào độ dài tiền tố khớp. Chữ ký sai luôn bị từ chối dù credential ACTIVE.
4. **Chống replay:** kiểm tra timestamp theo đồng hồ server và đăng ký nonce bằng thao tác nguyên tử chỉ nhận lần đầu (ví dụ Redis SET với NX và TTL) trên kho dùng chung giữa các instance. Bố trí kiểm tra và ghi nonce sau khi chữ ký được xác thực để client không thể tùy ý tiêu tốn nonce hợp lệ của người khác. TTL phải bao phủ toàn bộ cửa sổ timestamp chấp nhận, kể cả độ lệch đồng hồ được cho phép.
5. **Phân quyền:** principal xác thực thành công vẫn có thể không được phép gọi một API cụ thể. Đây là quyết định authorization độc lập với trạng thái credential.

Trong triển khai thực tế, có thể kiểm tra cú pháp và độ lệch timestamp sớm để tiết kiệm tài nguyên, nhưng chỉ ghi nonce vào kho chống replay sau khi xác thực chữ ký. Một request có credential bị khóa phải bị từ chối ngay cả khi chữ ký, timestamp và nonce đều hợp lệ.

**Lưu ý về HTTP:** 401 thường phù hợp với xác thực thất bại do thiếu, sai, hết hạn hoặc bị thu hồi credential; 403 dành cho trường hợp đã xác thực nhưng thiếu quyền. API cần áp dụng hợp đồng phản hồi nhất quán và tránh cung cấp thông tin giúp đối thủ dò xem một key ID có tồn tại hay đã bị khóa. Mã lý do chi tiết nên nằm trong log bảo mật nội bộ có kiểm soát quyền truy cập.

## 5. Ví dụ Java: đánh giá hiệu lực credential

Đưa quy tắc quyết định vào một hàm riêng giúp API gateway, service xác thực và tác vụ kiểm tra vận hành dùng cùng một định nghĩa. Ví dụ Java 17 sau dùng Instant và dữ liệu snapshot đã được tra cứu; hàm chỉ quyết định trạng thái, chưa xác minh HMAC:

~~~java
import java.time.Instant;

public final class CredentialEligibility {
    enum State {
        PENDING, ACTIVE, SUSPENDED, REVOKED, RETIRED
    }

    enum Decision {
        ALLOW,
        UNKNOWN,
        NOT_ACTIVE,
        SUSPENDED,
        REVOKED,
        RETIRED,
        NOT_YET_VALID,
        EXPIRED
    }

    record Snapshot(
        String keyId,
        State state,
        Instant validFrom,
        Instant expiresAt,
        Instant revokedAt,
        long version
    ) {}

    static Decision decide(Snapshot credential, Instant serverNow) {
        if (credential == null) {
            return Decision.UNKNOWN;
        }

        // Thu hồi luôn được ưu tiên, kể cả khi bản ghi vẫn ghi ACTIVE.
        if (credential.state() == State.REVOKED
                || credential.revokedAt() != null) {
            return Decision.REVOKED;
        }

        if (credential.state() == State.RETIRED) {
            return Decision.RETIRED;
        }
        if (credential.state() == State.SUSPENDED) {
            return Decision.SUSPENDED;
        }
        if (credential.state() != State.ACTIVE) {
            return Decision.NOT_ACTIVE;
        }
        if (serverNow.isBefore(credential.validFrom())) {
            return Decision.NOT_YET_VALID;
        }
        if (credential.expiresAt() != null
                && !serverNow.isBefore(credential.expiresAt())) {
            return Decision.EXPIRED;
        }
        return Decision.ALLOW;
    }

    public static void main(String[] args) {
        Snapshot credential = new Snapshot(
            "partner-a-2026-11",
            State.ACTIVE,
            Instant.parse("2026-11-20T00:00:00Z"),
            Instant.parse("2026-12-01T00:00:00Z"),
            null,
            4L
        );
        System.out.println(decide(
            credential, Instant.parse("2026-11-28T09:00:00Z")
        )); // ALLOW
        System.out.println(decide(
            credential, Instant.parse("2026-12-01T00:00:00Z")
        )); // EXPIRED: hết hạn ngay tại mốc expiresAt
    }
}
~~~

Ứng dụng thực tế nên tiêm Clock hoặc một nguồn thời gian server đáng tin cậy vào service gọi hàm này để kiểm thử các mốc thời gian chính xác. Không dùng timestamp do client gửi để đánh giá valid_from/expires_at: timestamp của request chỉ phục vụ kiểm tra cửa sổ chống replay. Không để hàm decide trả ALLOW trở thành điều kiện duy nhất để chấp nhận request; HMAC, nonce và quyền truy cập vẫn phải được kiểm tra.

Cũng không nên cache đơn thuần kết quả ALLOW cho key ID đến vô hạn. Quyết định đó gắn với **phiên bản trạng thái và thời điểm đánh giá**, nên có thể hết đúng sau một giây hoặc ngay khi key bị thu hồi.

## 6. Thay đổi trạng thái an toàn và có thể truy vết

Mỗi thay đổi nên xuất phát từ một tác vụ quản trị có quyền rõ ràng, lý do và dấu vết kiểm toán. Một chính sách chuyển trạng thái minh họa:

| Hành động | Điều kiện trước | Trạng thái sau |
| --- | --- | --- |
| Kích hoạt | PENDING, đã cấp phát secret và principal hợp lệ | ACTIVE |
| Tạm khóa | ACTIVE, có yêu cầu điều tra/ứng phó | SUSPENDED |
| Mở khóa | SUSPENDED, được phê duyệt và chưa hết hạn | ACTIVE |
| Thu hồi khẩn cấp | ACTIVE hoặc SUSPENDED | REVOKED |
| Ngừng dùng theo rotation | ACTIVE hoặc SUSPENDED | RETIRED |

Để tránh hai quản trị viên cập nhật đồng thời làm mất trạng thái, dùng **optimistic locking** qua trường version. Ví dụ cú pháp SQL minh họa với named parameter do lớp truy cập dữ liệu cung cấp:

~~~sql
UPDATE hmac_credentials
SET lifecycle_state = 'SUSPENDED',
    state_changed_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE credential_id = :credential_id
  AND lifecycle_state = 'ACTIVE'
  AND version = :expected_version
RETURNING credential_id, lifecycle_state, version;
~~~

Nếu không có hàng nào được cập nhật, tác vụ phải đọc lại trạng thái và báo xung đột hoặc xử lý idempotency theo hợp đồng; không tự động ghi đè. Trong **cùng giao dịch** với thay đổi trạng thái, ghi audit event gồm credential_id/key_id, phiên bản, trạng thái trước/sau, thời điểm, người thao tác, lý do, mã yêu cầu và correlation ID. Tuyệt đối không ghi shared secret hoặc chữ ký request vào audit event.

Nếu gateway dùng cache, thay đổi còn phải phát hành sự kiện vô hiệu hóa cache. Có thể dùng transactional outbox để lưu sự kiện trong cùng giao dịch và gửi sau commit, giúp tránh trường hợp database đã đổi trạng thái nhưng mất thông báo. Consumer nên kiểm tra version và bỏ qua sự kiện đến muộn có version cũ.

**Thu hồi tức thời có giới hạn thực tế:** sau khi REVOKED được commit, các instance còn giữ snapshot cũ vẫn có thể chấp nhận request trong khoảng thời gian cache chưa cập nhật. Với API nhạy cảm, cần thiết kế điểm kiểm tra có độ mới cao (đọc nhất quán từ nguồn trạng thái có thẩm quyền, invalidation đáng tin cậy, hoặc cơ chế danh sách thu hồi cập nhật rất nhanh), xác định rõ độ trễ thu hồi tối đa chấp nhận được và đo nó. Một request đã vượt qua điểm quyết định trước khi thu hồi có thể còn đang xử lý; phải định nghĩa riêng việc hủy request đang chạy nếu nghiệp vụ yêu cầu.

## 7. Quan sát trạng thái trong sản phẩm và vận hành

Một giao diện quản trị hữu ích cần tách **trạng thái hiện tại** khỏi **hoạt động gần đây**:

- Trạng thái cấu hình, trạng thái hiệu lực được tính tại thời điểm xem, thời điểm tạo/kích hoạt/hết hạn/thu hồi và version.
- Principal và ứng dụng sở hữu, key ID, quan hệ key mới/cũ khi rotation; không hiển thị secret.
- Thời điểm thành công gần nhất và tỷ lệ xác thực thất bại theo khoảng thời gian; ghi nhãn độ trễ tổng hợp.
- Lịch sử thay đổi trạng thái: ai thao tác, lý do gì, thay đổi từ phiên bản nào sang phiên bản nào.
- Các credential sắp hết hạn, đang SUSPENDED kéo dài, hoặc tiếp tục xuất hiện request sau khi REVOKED/RETIRED.

Ví dụ phản hồi **API quản trị chỉ dành cho người được cấp quyền**:

~~~json
{
  "credentialId": "8db45986-5efa-49f1-a877-2835537d764c",
  "keyId": "partner-a-2026-11",
  "principalId": "7ceacfe8-540a-40e9-aaca-51e80212b5ff",
  "configuredState": "ACTIVE",
  "effectiveState": "EXPIRED",
  "evaluatedAt": "2026-12-02T09:00:00Z",
  "validFrom": "2026-11-20T00:00:00Z",
  "expiresAt": "2026-12-01T00:00:00Z",
  "lastSuccessfulUseAt": "2026-11-30T18:42:00Z",
  "version": 4
}
~~~

Trường effectiveState phải được tính dựa trên evaluatedAt ở phía server và trạng thái hiện hành; lastSuccessfulUseAt là dữ liệu quan sát có thể cập nhật trễ, **không** chứng minh credential còn hợp lệ. Nếu client cần tra cứu trạng thái credential của chính nó, phải ràng buộc với principal đã được xác thực và giới hạn dữ liệu trả về, không để endpoint biến thành công cụ dò key ID của đối tác khác.

Để tìm credential đang ACTIVE và sẽ hết hạn trong bảy ngày tới:

~~~sql
SELECT credential_id, key_id, principal_id, expires_at
FROM hmac_credentials
WHERE lifecycle_state = 'ACTIVE'
  AND revoked_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP
  AND expires_at <= CURRENT_TIMESTAMP + INTERVAL '7 days'
ORDER BY expires_at;
~~~

Các tín hiệu vận hành nên có:

| Tín hiệu | Cách hiểu/hành động |
| --- | --- |
| Số credential ACTIVE sắp hết hạn | Nhắc chủ sở hữu thực hiện rotation trước hạn |
| Yêu cầu bằng key đã REVOKED/RETIRED | Điều tra client chưa cập nhật key hoặc khả năng lạm dụng |
| Tỷ lệ từ chối vì trạng thái/expiry tăng | Kiểm tra đợt rotation, đồng bộ dữ liệu và cấu hình triển khai |
| Số credential SUSPENDED quá thời hạn xử lý | Nhắc người chịu trách nhiệm đóng sự cố hoặc phê duyệt mở khóa |
| Độ trễ lan truyền event thu hồi và version cache | Kiểm soát cửa sổ key bị thu hồi vẫn có thể được chấp nhận |
| Lỗi đọc registry/vault và lỗi nonce store | Xác định sự cố xác thực và tỷ lệ từ chối theo fail closed |

Metrics nên dùng nhãn hữu hạn như service, môi trường, loại trạng thái hoặc mã từ chối. Không đưa key ID, principal ID có số lượng lớn hay secret vào nhãn Prometheus vì tạo cardinality cao và làm lộ thông tin. Khi cần điều tra từng key, dùng log bảo mật có kiểm soát quyền truy cập với correlation ID, mã lý do nội bộ và định danh đã che hoặc được bảo vệ thích hợp. Không log header chứa secret/chữ ký, canonical request có dữ liệu nhạy cảm hoặc toàn bộ body nghiệp vụ.

## 8. Ví dụ rotation có thời gian chuyển tiếp

Giả sử đối tác A đang dùng credential cũ K1, sẽ chuyển sang K2 trong một tuần. Quy trình điển hình:

1. **Ngày 1:** tạo K2 với key ID và secret riêng, gắn cùng principal; đặt PENDING trong khi xác nhận quá trình phân phối bí mật và kiểm thử ký request.
2. **Ngày 2:** chuyển K2 sang ACTIVE. K1 vẫn ACTIVE trong cửa sổ chuyển tiếp có hạn rõ ràng, nên cả hai key ID có thể được chấp nhận theo từng secret tương ứng.
3. **Ngày 3–6:** quan sát request thành công theo key ID để xác nhận client đã chuyển dần sang K2. Trạng thái “K2 đang ACTIVE” không chứng minh rằng mọi instance client đã chuyển.
4. **Ngày 7:** sau khi hết cửa sổ chuyển tiếp và kiểm tra các client còn dùng K1, chuyển K1 sang RETIRED; từ đó mọi request ký bằng K1 bị từ chối.
5. **Nếu K1 bị nghi lộ vào ngày 4:** chuyển K1 sang REVOKED ngay và kích hoạt cơ chế cập nhật trạng thái khẩn cấp; không chờ hết thời gian chuyển tiếp.

Không dùng cùng một secret cho K1 và K2. Replay store nên ràng buộc nonce với key ID cùng khoảng thời gian xác minh và dùng thao tác atomic toàn cụm. Khi hai key cùng ACTIVE, kiểm tra trạng thái trên **đúng key ID trong request**, tránh lỗi chọn đại một secret của principal khiến chữ ký được xác minh bằng key không dự kiến.

Proxy/gateway còn có thể chuẩn hóa URI, query string hoặc header khác nhau giữa điểm ký và điểm xác minh. Lỗi canonicalization thường biểu hiện dưới dạng HMAC mismatch, không phải EXPIRED/SUSPENDED. Vì vậy cần phân tách mã lý do nội bộ để vận hành không “mở khóa nhầm” một credential khi nguyên nhân là gateway đã rewrite request.

## 9. Các tình huống cần kiểm thử

| Tình huống | Kỳ vọng |
| --- | --- |
| ACTIVE, đã tới valid_from, chưa tới expires_at, HMAC đúng, nonce mới | Chấp nhận bước xác thực; tiếp tục kiểm tra quyền |
| ACTIVE nhưng thời điểm server đúng bằng expires_at | Từ chối với lý do nội bộ EXPIRED |
| PENDING hoặc chưa đến valid_from | Từ chối, kể cả chữ ký đúng |
| SUSPENDED, secret còn đúng | Từ chối; mở khóa chỉ qua thao tác có quyền |
| REVOKED, bản ghi vẫn có expires_at tương lai | Từ chối; không thể dùng lại bằng cách sửa thời hạn |
| RETIRED sau rotation, client vẫn dùng key cũ | Từ chối và quan sát lượng request tồn đọng |
| ACTIVE, HMAC sai | Từ chối vì chữ ký, không đổi trạng thái credential |
| ACTIVE, chữ ký đúng nhưng nonce trùng | Từ chối replay trên mọi instance |
| K1 REVOKED, K2 ACTIVE cùng principal | K1 bị từ chối; K2 được xét độc lập |
| Hai tác vụ chuyển trạng thái dùng cùng version | Chỉ một cập nhật thành công, tác vụ còn lại thấy xung đột |
| Sự kiện invalidation version cũ đến sau version mới | Cache không quay ngược về trạng thái cũ |
| Registry/vault/nonce store không khả dụng | Từ chối theo chính sách fail closed và phát tín hiệu sự cố |

Đặc biệt cần kiểm thử **khác biệt giữa node**: thu hồi K1 ở một nơi, lập tức gửi request qua nhiều gateway/region và đo xem node nào còn chấp nhận. Việc “database hiển thị REVOKED” chỉ xác nhận trạng thái nguồn; chưa đủ chứng minh mọi điểm xác thực đã áp dụng. Kiểm thử với đồng hồ server lệch trong giới hạn cho phép để tách vấn đề expires_at của credential khỏi cửa sổ timestamp chống replay.

## 10. Bài tập áp dụng

Một hệ thống có ba instance gateway, cache trạng thái credential trong 60 giây. Lúc 10:00:00, quản trị viên thu hồi credential K1 vì nghi lộ. Lúc 10:00:10, client ký request bằng K1 với HMAC đúng, timestamp mới và nonce chưa từng dùng. Gateway thứ hai vẫn giữ snapshot ACTIVE từ 09:59:50.

Hãy xác định ba kết quả riêng biệt: **trạng thái nguồn** của K1, **kết quả có thể xảy ra** trên gateway thứ hai khi chỉ dùng cache, và **điều kiện cần bổ sung** nếu hệ thống yêu cầu mọi request bắt đầu sau commit thu hồi phải bị từ chối. Lời giải định hướng: K1 đã REVOKED ở nguồn; gateway thứ hai vẫn có thể chấp nhận vì snapshot cũ; muốn đạt bảo đảm mạnh hơn phải thiết kế điểm quyết định đọc trạng thái đủ mới hoặc cơ chế đồng bộ thu hồi có xác nhận, kể cả khi một node mất kết nối. Cần nêu rõ giới hạn của hệ thống phân tán và chính sách fail closed khi không thể chứng minh trạng thái hiện tại.

Khi thiết kế tính năng theo dõi trạng thái credential, tiêu chí hoàn thành là: mỗi request chỉ được chấp nhận bằng credential còn hiệu lực; mỗi thay đổi trạng thái có bằng chứng kiểm toán; dữ liệu quản trị không lộ secret; và độ trễ lan truyền việc tạm khóa/thu hồi được đo, kiểm thử, đưa vào cam kết vận hành.
