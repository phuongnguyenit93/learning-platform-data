# Key version trong HMAC request authentication

## 1. Key version giải quyết vấn đề gì?

Trong hệ thống xác thực HTTP request bằng HMAC, client và server chia sẻ một secret để tính và kiểm tra chữ ký trên **canonical request** theo hợp đồng ký. Secret cần được thay theo chu kỳ hoặc khi nghi ngờ lộ. Trong thời gian chuyển đổi, một client có thể còn gửi request bằng khóa cũ trong khi các instance mới đã chuyển sang khóa mới.

**Key version** là nhãn định danh một thế hệ khóa cụ thể của cùng một client hoặc cùng một tích hợp. Nó giúp server xác định **đúng secret** cần dùng để xác minh một request và giúp vận hành phân biệt lưu lượng dùng khóa cũ, khóa mới. Ví dụ:

| Client | Key version | Secret thực tế | Trạng thái | Vai trò |
| --- | ---: | --- | --- | --- |
| partner-a | 3 | Bí mật riêng K3 trong secret manager | ACTIVE | Khóa đang dùng trước rotation |
| partner-a | 4 | Bí mật riêng K4 trong secret manager | ACTIVE | Khóa mới trong giai đoạn chuyển tiếp |
| partner-a | 2 | Bí mật cũ K2, không còn dùng | RETIRED | Lịch sử, bị từ chối khi xác thực |

Từ bảng này, request khai báo client = partner-a và version = 4 phải được xác minh **chỉ với K4**, rồi kiểm tra K4 có còn hợp lệ hay không. Server không thử lần lượt tất cả secret còn lưu để tìm ra chữ ký khớp.

Key version **không phải secret**, không được coi là yếu tố bảo mật, không tự tạo ra độ mạnh mật mã và không thay thế kiểm tra trạng thái credential. Chữ ký HMAC chỉ được tin cậy sau khi server tái tạo canonical request chính xác, dùng đúng key, kiểm tra freshness/replay và hoàn tất quyết định xác thực.

## 2. Phân biệt các loại version dễ bị nhầm

Trong một hệ thống HMAC có thể xuất hiện nhiều trường mang tên “version”:

| Thuộc tính | Ví dụ | Chức năng |
| --- | --- | --- |
| **Key version** | 4 | Xác định thế hệ secret dùng để ký và xác minh |
| **Key ID** | partner-a-k4 | Định danh một credential cụ thể; có thể thay cho cặp client + key version |
| **Canonical contract version** | HMAC-REQUEST-V1 | Xác định quy tắc tạo canonical request, thứ tự và chuẩn hóa trường |
| **HMAC algorithm** | HmacSHA256 | Xác định hàm MAC; không có nghĩa version = 256 |
| **Record revision / row version** | 12 | Chống ghi đè khi hai tác vụ quản trị cập nhật metadata đồng thời |
| **API version** | /v2/payments | Phiên bản giao diện nghiệp vụ; không quyết định secret được dùng |

Cần tách key version và record revision: key version 4 có thể trải qua nhiều lần sửa metadata (ACTIVE → SUSPENDED → REVOKED), nhưng vẫn là **cùng một secret K4** và vẫn là key version 4. Không tăng key version chỉ vì sửa trạng thái, đổi tên hiển thị hoặc cập nhật ngày hết hạn; tăng key version khi phát hành một thế hệ secret mới.

Tương tự, thay key version không mặc định thay canonical contract version. Một hệ thống có thể xác minh K3 và K4 cùng bằng hợp đồng HMAC-REQUEST-V1. Nếu thay cả format canonical request, cần một kế hoạch tương thích và kiểm thử riêng để tránh nhầm lỗi canonicalization thành lỗi rotation.

## 3. Hai mô hình định danh khóa hợp lệ

### 3.1. Key ID duy nhất cho từng thế hệ

Mỗi secret mới có một key ID bất biến, ví dụ partner-a-k3, partner-a-k4. Request gửi key ID; server tra cứu đúng credential. Trường key_version trong registry chủ yếu phục vụ hiển thị, đối chiếu và chính sách rotation. Khi sử dụng cách này, key ID đã đủ định danh secret; nếu request còn gửi key version thì **hai giá trị phải khớp metadata**.

Ưu điểm: có thể tra cứu một bước; dễ thu hồi riêng từng credential. Lưu ý: **không tái sử dụng key ID** cho secret khác, kể cả khi secret cũ đã bị RETIRED.

### 3.2. Client ID ổn định kết hợp key version

Client gửi hai trường, ví dụ:

~~~http
X-Client-Id: partner-a
X-Key-Version: 4
~~~

Server dùng khóa tra cứu tổng hợp **(client_id, key_version)**. Với cùng client, version 3 và 4 trỏ đến hai secret khác nhau. Đây là mô hình được dùng để minh họa trong phần tiếp theo.

Cả hai mô hình đều hợp lệ nếu có hợp đồng rõ ràng. Không nên mơ hồ lúc thì hiểu key ID là client ID, lúc lại hiểu key ID là một credential riêng. Một khi giao thức chọn định danh nào, client, gateway, server và registry đều phải dùng chung định nghĩa.

### Những bất biến cần giữ

1. **Một cặp (client_id, key_version) ánh xạ đến tối đa một secret qua toàn bộ lịch sử.** Nếu lộ secret, phát hành version mới và không “thay secret dưới cùng version”.
2. **Mỗi version có secret độc lập, đủ entropy**, tạo bằng nguồn ngẫu nhiên mật mã; không dùng lại secret cũ hoặc suy ra K4 bằng phép ghép chuỗi với K3.
3. Version được tăng đơn điệu trong phạm vi một client và không tái sử dụng sau khi xóa/hủy bản ghi; việc tăng số không làm key trở nên an toàn hơn, nhưng giúp quản lý rõ ràng.
4. Số version mới **không mặc nhiên là version đang được phép sử dụng**. Server phải kiểm tra trạng thái, thời gian hiệu lực và chính sách cho phép đồng thời.
5. Client phải chỉ định version rõ ràng khi ký. Server chỉ truy xuất secret của version được yêu cầu, không tự động fallback sang version khác.

## 4. Khai báo key version trong request và canonical request

Giả sử hợp đồng HMAC-REQUEST-V1 quy định client gửi:

~~~http
POST /v1/transfers?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-a
X-Key-Version: 4
X-Timestamp: 2026-11-28T03:00:00Z
X-Nonce: 80696fe4-963b-41f8-8e08-e07fe2cccf74
X-Signature: <base64-cua-hmac-sha256>

{"amount":125000}
~~~

Ví dụ này dùng ký hiệu ở giá trị chữ ký để minh họa, không phải chữ ký HMAC có thể kiểm chứng. Hợp đồng ký phải định nghĩa chính xác cách tạo canonical request, ví dụ chuỗi UTF-8 gồm các dòng theo thứ tự cố định:

~~~text
HMAC-REQUEST-V1
POST
/v1/transfers?currency=VND
partner-a
4
2026-11-28T03:00:00Z
80696fe4-963b-41f8-8e08-e07fe2cccf74
<sha256-hex-cua-body-nguyen-ban>
~~~

Giá trị ở dòng cuối phải được thay bằng digest SHA-256 thực tế của body bytes; nội dung trên là **mẫu cấu trúc**, chưa phải vector chữ ký hoàn chỉnh. Các bên phải chốt quy tắc method viết hoa, encode và thứ tự query parameter, dấu gạch chéo, ký tự Unicode, normalization, newline, body rỗng và proxy rewrite. Header được ký phải có cách lấy giá trị nhất quán; nếu có duplicate header hoặc giá trị mơ hồ, áp dụng quy tắc chuẩn hóa hoặc từ chối theo hợp đồng.

Công thức:

\[
\text{signature} = \operatorname{Base64}\bigl(\operatorname{HMAC\mbox{-}SHA256}(K_4,\ \operatorname{UTF8}(\text{canonicalRequest}))\bigr)
\]

Trong ví dụ, **client ID và key version nằm trong canonical request** cùng timestamp, nonce và digest body. Vì vậy, chỉnh X-Key-Version từ 4 thành 3 sẽ thay dữ liệu được ký. Tuy nhiên, kiểm tra chữ ký vẫn phải luôn dùng secret được định danh bởi **cặp client ID + version của request**; không tin vào header chỉ vì nó xuất hiện trong chuỗi ký.

Nếu gateway xử lý TLS, route hoặc rewrite path trước khi server xác minh, phải thống nhất điểm lấy URI chính tắc. Không sử dụng bừa header chuyển tiếp do người gọi tự cung cấp để dựng canonical request. Với một endpoint đã ký, thay đổi cách chuẩn hóa cần được kiểm thử tương thích giữa client, gateway và server.

### Tránh version mơ hồ

Version cần có một dạng biểu diễn chuẩn. Ví dụ yêu cầu số thập phân dương, không có dấu cộng, số 0 đầu chuỗi hoặc khoảng trắng:

| Header | Xử lý đề xuất |
| --- | --- |
| X-Key-Version: 4 | Hợp lệ về cú pháp |
| X-Key-Version: 04 | Từ chối, tránh hai cách biểu diễn của cùng version |
| X-Key-Version: +4 | Từ chối |
| X-Key-Version: 4, 5 hoặc nhiều header trùng tên | Từ chối vì mơ hồ |
| Không gửi X-Key-Version | Từ chối theo hợp đồng yêu cầu version tường minh |
| X-Key-Version: latest | Từ chối; client không được yêu cầu server tự chọn |

Có thể dùng version dạng chuỗi thay vì số, nhưng vẫn cần quy tắc duy nhất về ký tự, chuẩn hóa và tính bất biến. Các giá trị key ID/version mang tính định tuyến nên đặt giới hạn độ dài và format trước khi gọi registry.

## 5. Mô hình dữ liệu cho nhiều key version

Một registry HMAC nên lưu được nhiều phiên bản của cùng client đồng thời và quản lý từng credential độc lập. Ví dụ PostgreSQL:

~~~sql
CREATE TABLE hmac_key_versions (
    client_id       VARCHAR(128) NOT NULL,
    key_version     INTEGER NOT NULL CHECK (key_version > 0),
    secret_ref      VARCHAR(255) NOT NULL,
    lifecycle_state VARCHAR(16) NOT NULL
        CHECK (lifecycle_state IN
            ('PENDING', 'ACTIVE', 'SUSPENDED', 'RETIRED', 'REVOKED')),
    valid_from      TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    canonical_contract_version VARCHAR(32) NOT NULL,
    algorithm_id    VARCHAR(32) NOT NULL,
    row_version     BIGINT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (client_id, key_version),
    CHECK (expires_at > valid_from)
);

CREATE INDEX hmac_key_versions_active_idx
    ON hmac_key_versions (client_id, lifecycle_state, expires_at);
~~~

Trong đó:

- **secret_ref** trỏ đến kho secret được bảo vệ; không đặt secret dạng rõ vào bản ghi hoặc log. Hạn chế quyền đọc theo nhu cầu tối thiểu.
- **key_version** là định danh thế hệ secret; chỉ tăng khi phát hành key mới. Không cập nhật key_version của một bản ghi hiện hữu.
- **row_version** phục vụ optimistic locking khi thay đổi trạng thái. Không xuất trường này thay cho X-Key-Version.
- **valid_from / expires_at** giới hạn thời gian hiệu lực của từng version bằng thời gian server.
- **canonical_contract_version / algorithm_id** ghi hợp đồng ký và thuật toán được hỗ trợ, phải được ràng buộc bằng cấu hình tin cậy. Không nhận giá trị thuật toán tùy ý từ request rồi thực thi.

Lược đồ minh họa chưa bao gồm bảng chủ sở hữu client, RBAC, audit log và outbox phát sự kiện. Cần bảo đảm thao tác cấp version mới được **tuần tự hóa theo client**, ví dụ giữ row client làm điểm cấp phát version trong transaction, hoặc retry có kiểm soát khi vi phạm khóa chính. Không tính MAX(key_version) + 1 rồi ghi một cách ngây thơ trong nhiều tác vụ song song, vì hai tác vụ có thể cùng chọn một version. Khi có chính sách chỉ cho tối đa hai version đồng thời ACTIVE, kiểm tra và cập nhật phải thực hiện nguyên tử theo client.

Registry cũng phải giữ lịch sử version hoặc một bộ đếm không quay lại, để việc xóa bản ghi cũ không khiến version cũ được tái sử dụng.

## 6. Luồng xác minh sử dụng đúng version

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway / Verifier
    participant R as Key registry
    participant V as Secret manager
    participant N as Replay store
    C->>G: Request + clientId + version=4 + HMAC
    G->>R: Lookup (clientId, 4)
    R-->>G: Metadata K4, trạng thái, secretRef
    G->>G: Kiểm tra hiệu lực K4
    G->>V: Lấy secret của K4
    V-->>G: Secret K4
    G->>G: Canonicalize và verify HMAC bằng K4
    G->>G: Kiểm tra timestamp từ request
    G->>N: Đăng ký nonce theo client/version (atomic)
    N-->>G: Nonce mới hoặc trùng
    G->>G: Xác thực principal, sau đó phân quyền
    G-->>C: Kết quả
~~~

Quy trình chuẩn:

1. Parse client ID và version theo đúng format, từ chối request có header trùng hoặc giá trị mơ hồ.
2. Tra cứu **duy nhất** bản ghi có (client_id, key_version) chính xác. Không lấy “version mới nhất” khi client đã khai báo một version khác.
3. Chỉ tiếp tục nếu bản ghi ở ACTIVE, valid_from ≤ giờ server < expires_at, không bị thu hồi. Không tin vào thời gian do client gửi để xác định key còn hiệu lực.
4. Lấy secret của đúng version, tạo canonical request theo contract được cho phép và tính HMAC. So sánh chữ ký trên cùng độ dài bằng hàm so sánh an toàn về timing.
5. Kiểm tra timestamp nằm trong cửa sổ chấp nhận. Ghi nonce vào kho dùng chung bằng phép **insert-if-absent nguyên tử** sau khi chữ ký đã được xác minh, với TTL bao phủ toàn bộ thời gian request đó có thể được chấp nhận.
6. Xác định principal đã xác thực và kiểm tra phân quyền cho tài nguyên/action. Một HMAC đúng bằng version ACTIVE **không tự cấp thêm quyền**.

**Không thử K4 → K3 → K2** khi chữ ký với K4 sai. Fallback như vậy khiến lỗi client bị che khuất, tăng số phép HMAC, làm chính sách thu hồi khó kiểm soát và có thể cho phép dùng secret đã nghỉ sử dụng. Nếu cần hỗ trợ key cũ trong cửa sổ rotation, cho client chỉ rõ version cũ **còn ACTIVE**; server kiểm tra chính xác version đó.

### Mẫu Java 17: chỉ chọn một key version

Ví dụ sau giả định framework đã lấy method và canonical URI theo hợp đồng đáng tin cậy, body là byte gốc thực tế, và không có header trùng. Nó minh họa quyết định dùng đúng key version và xác minh chữ ký. Các dịch vụ registry, secret manager và replay store phải được triển khai với cơ chế truy cập, timeout, cache và lỗi phù hợp.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Objects;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class VersionedHmacVerifier {
    enum State { PENDING, ACTIVE, SUSPENDED, RETIRED, REVOKED }

    record Credential(
        String clientId,
        int keyVersion,
        String secretRef,
        State state,
        Instant validFrom,
        Instant expiresAt,
        boolean revoked
    ) {}

    record SignedRequest(
        String clientId,
        String keyVersionHeader,
        String method,
        String canonicalTarget,
        String timestampHeader,
        String nonceHeader,
        byte[] body,
        String signatureBase64
    ) {}

    interface KeyRegistry {
        Credential findExactly(String clientId, int version);
    }

    interface SecretManager {
        byte[] load(String secretRef);
    }

    // Một hàm kiểm tra chữ ký; timestamp, nonce và authorization được
    // xử lý tại các bước riêng sau khi kết quả chữ ký thành công.
    static boolean verifySignature(
        SignedRequest request,
        Instant serverNow,
        KeyRegistry registry,
        SecretManager secrets
    ) throws Exception {
        String rawVersion = request.keyVersionHeader();
        if (rawVersion == null || !rawVersion.matches("[1-9][0-9]{0,8}")) {
            return false;
        }

        int version = Integer.parseInt(rawVersion);
        Credential credential =
            registry.findExactly(request.clientId(), version);

        if (credential == null
                || !Objects.equals(credential.clientId(), request.clientId())
                || credential.keyVersion() != version
                || credential.state() != State.ACTIVE
                || credential.revoked()
                || serverNow.isBefore(credential.validFrom())
                || !serverNow.isBefore(credential.expiresAt())) {
            return false;
        }

        byte[] bodyDigest =
            MessageDigest.getInstance("SHA-256").digest(request.body());

        String canonical = String.join("\n",
            "HMAC-REQUEST-V1",
            request.method(),
            request.canonicalTarget(),
            request.clientId(),
            rawVersion,
            request.timestampHeader(),
            request.nonceHeader(),
            HexFormat.of().formatHex(bodyDigest)
        );

        byte[] secret = secrets.load(credential.secretRef());
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        byte[] expected = mac.doFinal(
            canonical.getBytes(StandardCharsets.UTF_8)
        );

        byte[] provided;
        try {
            provided = Base64.getDecoder().decode(request.signatureBase64());
        } catch (IllegalArgumentException invalidSignature) {
            return false;
        }
        return provided.length == expected.length
            && MessageDigest.isEqual(provided, expected);
    }
}
~~~

Đoạn code được cố ý giới hạn ở **xác minh chữ ký bằng version được chỉ định**. Hệ thống thật cần kiểm tra phương thức, canonical target và các header trên request gốc (không lấy thông tin được client tự gán “đã chuẩn hóa”), giới hạn kích thước body, xác thực cú pháp timestamp/nonce, chống replay, quản lý secret bytes an toàn và ánh xạ lỗi nội bộ thành phản hồi chuẩn. Khi registry hoặc secret manager không thể chứng minh credential đang hợp lệ, chính sách xác thực an toàn phải từ chối (fail closed).

Nếu registry lấy từ cache, cần cơ chế cập nhật/thu hồi trạng thái có độ mới được kiểm soát. Việc hàm verifySignature trả true dựa trên một snapshot ACTIVE đã cũ không chứng minh key còn được phép sử dụng ở nguồn tại cùng thời điểm.

## 7. Phát hành version mới và chuyển tiếp an toàn

Giả sử client partner-a đang ký bằng K3 (version = 3), cần chuyển sang K4 (version = 4).

| Giai đoạn | K3 | K4 | Hành động |
| --- | --- | --- | --- |
| Trước rotation | ACTIVE | Chưa tồn tại | Chỉ chấp nhận version 3 |
| Chuẩn bị | ACTIVE | PENDING | Sinh secret mới, lưu ref, phân phối bằng kênh an toàn |
| Kích hoạt | ACTIVE | ACTIVE | Server sẵn sàng nhận cả version 3 và 4 |
| Client chuyển dần | ACTIVE | ACTIVE | Client bắt đầu ký version 4, theo dõi lưu lượng còn dùng version 3 |
| Kết thúc cửa sổ | RETIRED | ACTIVE | Dừng chấp nhận version 3 |
| Sự cố lộ K3 | REVOKED | ACTIVE nếu vẫn an toàn | Thu hồi K3 ngay; không chờ ngày kết thúc |

### Trình tự triển khai khuyến nghị

1. **Tạo K4 riêng biệt.** Cấp version 4 một cách nguyên tử, tạo secret có đủ độ ngẫu nhiên từ CSPRNG và lưu ở secret manager. Ghi nhận K4 là PENDING và mối liên hệ với K3. Không ghi secret mới vào log, issue hoặc hệ thống giám sát.
2. **Đồng bộ verifier trước.** Đảm bảo các instance/gateway đã có khả năng tra cứu version 4 và hợp đồng canonical request đã được kiểm thử. Việc đăng ký key server-side phải hoàn tất trước khi client bắt đầu gửi lưu lượng dùng K4.
3. **Kích hoạt K4 và phân phối secret.** Chỉ gửi qua kênh cấp phát có xác thực, bảo mật; xác nhận client sở hữu secret đúng. Duy trì K3 ACTIVE trong thời gian chồng lấp đã phê duyệt.
4. **Chuyển client theo từng nhóm.** Mỗi request ký bằng secret tương ứng với version ghi trong header. Không dùng secret K3 nhưng gửi version 4, và không cố “tự sửa” version sau khi tính chữ ký.
5. **Quan sát số request theo version.** Kiểm tra client nào còn gửi version 3, lý do thất bại, số lỗi xác minh chữ ký và các instance có lệch trạng thái. Đặt ngưỡng/điều kiện kết thúc chuyển tiếp trước khi chuyển K3 sang RETIRED.
6. **Đóng vòng đời K3.** Sau khi đạt điều kiện, ngừng chấp nhận K3 và giữ metadata/audit theo chính sách lưu trữ. Hủy secret K3 khỏi kho khi phù hợp chính sách khôi phục và kiểm toán. Nếu nghi lộ, REVOKED ngay, không chờ cửa sổ chuyển tiếp.

Version **tăng theo thứ tự cấp phát**, còn việc sử dụng có thể không liên tục: K4 có thể bị phát hành lỗi rồi REVOKED, sau đó tạo K5. Không được đổi tên K5 thành K4 để “liền dãy số”.

### Rollback được phép đến đâu?

Trong quá trình chuyển tiếp, nếu K4 gặp lỗi triển khai và K3 vẫn ACTIVE, client có thể quay về ký bằng K3 theo quy trình phê duyệt. Đây là rollback **chỉ trong cửa sổ mà K3 còn được tin cậy**.

Một khi K3 đã REVOKED do lộ key hoặc RETIRED theo chính sách trạng thái kết thúc, không mở lại K3 chỉ để sửa lỗi rollout. Phát hành K5 với secret mới và khắc phục lỗi client. Cần nêu rõ quyết định này trong runbook vận hành, bởi việc “khôi phục nhanh” bằng khóa cũ có thể làm mất ý nghĩa thu hồi.

## 8. Những lỗi thường gặp khi dùng key version

### Lỗi 1: Header version mới nhưng ký bằng secret cũ

Một client cache secret K3 nhưng config version đã chuyển thành 4. Chữ ký sẽ sai nếu K3 và K4 khác nhau như yêu cầu. Server phải ghi mã lỗi nội bộ đủ để đội vận hành điều tra (ví dụ SIGNATURE_MISMATCH đối với version 4), nhưng không tiết lộ secret hay trạng thái các version của client khác.

### Lỗi 2: Server lấy “latest” thay vì version trong request

Server thấy version mới nhất là 4 và dùng K4 xác minh cả request khai version 3. Kết quả là client chưa chuyển bị từ chối không cần thiết; nếu server còn tự fallback, hệ thống mất khả năng xác định key đã dùng. Cần lookup đúng cặp (client, version) và chỉ tin vào kết quả HMAC với key đó.

### Lỗi 3: Thay secret ngay dưới version hiện có

K3 bị ghi đè bằng secret mới nhưng version vẫn là 3. Các instance giữ cache secret cũ có kết quả trái ngược nhau; audit không thể xác định thế hệ khóa nào ký request. **Phát hành K4** là thao tác đúng; K3 giữ danh tính và lịch sử bất biến.

### Lỗi 4: Version được ký nhưng proxy thay đổi thành phần canonical request

Client ký target /v1/transfers?currency=VND, proxy sửa thứ tự query hoặc decode đường dẫn, server dựng canonical bytes khác. Đây là lỗi hợp đồng ký qua gateway, không nhất thiết là lỗi key version. Cần test xuyên proxy với URI, query, header và body thực tế trước rotation.

### Lỗi 5: Cache vẫn cho dùng version cũ sau thu hồi

Registry đã REVOKED K3 nhưng một gateway vẫn giữ ACTIVE trong cache. Nếu hệ thống yêu cầu thu hồi gần như tức thời, phải thiết kế invalidation có version/revision, giới hạn TTL và xác minh freshness ở đường xác thực quan trọng. Không cho cache phục hồi trạng thái cũ khi nhận event đến sai thứ tự.

### Lỗi 6: Cho phép client chọn thuật toán yếu hơn theo version

Key version dùng để chọn secret, không là tín hiệu “chấp nhận mọi thuật toán ghi trong request”. Hợp đồng ký và thuật toán được phép phải đến từ chính sách server. Không hỗ trợ downgrade sang một thuật toán yếu hoặc bỏ kiểm tra chữ ký khi không tìm được version.

### Lỗi 7: Bỏ quên nonce khi hai version cùng ACTIVE

Trong cửa sổ rotation, request ký K3 và K4 đều cần timestamp/nonce. Kho nonce nên dùng định danh đủ phân biệt (client_id, key_version, nonce), dùng thao tác atomic giữa tất cả verifier. TTL phải bao phủ thời gian chấp nhận replay dựa trên timestamp. Chỉ ghi nonce sau khi xác minh chữ ký đúng để hạn chế kẻ tấn công giữ trước nonce của client.

## 9. Nhật ký, metric và kiểm soát vận hành theo version

Key version giúp hiểu chính xác tiến độ chuyển đổi, nhưng cũng làm tăng lượng metadata cần bảo vệ. Một dashboard hữu ích có thể hiển thị:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Tổng request xác thực thành công theo key version | Client đã thật sự chuyển qua K4 hay chưa |
| Request với K3 sau hạn chuyển tiếp | Client đang kẹt bản cũ hoặc có lưu lượng đáng ngờ |
| Lỗi SIGNATURE_MISMATCH theo key version | Sai secret, cấu hình version, hoặc khác canonicalization |
| Request dùng REVOKED/RETIRED version | Nhận biết key bị dùng sau khi mất hiệu lực |
| Độ trễ đồng bộ trạng thái và phiên bản cache | Đo cửa sổ có thể chấp nhận key đã thu hồi |
| Thời gian còn lại trước expires_at của version đang ACTIVE | Chuẩn bị rotation kế tiếp đúng hạn |

Không đặt client ID/version có cardinality cao tùy ý vào nhãn metric toàn cục. Dùng nhãn hữu hạn cho dashboard tổng quát; chi tiết theo client và version nằm trong log bảo mật/audit có kiểm soát truy cập và chính sách lưu trữ. Không log secret, byte của HMAC key, body nhạy cảm hay header chứa chữ ký.

Một audit event cho phát hành version mới có thể chứa client ID, version cũ/mới, actor, thời gian, lý do, ticket/correlation ID, trạng thái trước/sau và bản ghi phiên bản metadata. Đảm bảo kết quả thay đổi registry và sự kiện thông báo có thể đối chiếu được, ví dụ transactional outbox.

Báo cáo “mọi client đã dùng K4” phải dựa trên dữ liệu **sử dụng thực tế** và độ trễ của hệ thống log. Sự vắng mặt của request bằng K3 trong vài phút không chứng minh một batch job chỉ chạy hằng ngày đã cập nhật; thời gian chuyển tiếp cần dựa vào chu kỳ hoạt động của tất cả client được hỗ trợ.

## 10. Kiểm thử bắt buộc

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Request version 3, chữ ký K3 đúng, K3 ACTIVE | Xác thực có thể thành công sau khi qua timestamp/nonce và các kiểm tra khác |
| Request version 4, chữ ký K4 đúng, K4 ACTIVE | Tương tự; sử dụng riêng K4 |
| Header version 4 nhưng tính HMAC bằng K3 | Từ chối SIGNATURE_MISMATCH |
| Header version 03 | Từ chối vì biểu diễn version không chuẩn |
| Header version không tồn tại hoặc thiếu | Từ chối, không dò thử các khóa khác |
| Version 3 RETIRED, chữ ký K3 vẫn đúng | Từ chối do trạng thái |
| Version 3 REVOKED, chưa hết expires_at | Từ chối ngay theo yêu cầu freshness của hệ thống |
| Version 4 ACTIVE nhưng chưa tới valid_from | Từ chối |
| ServerNow đúng bằng expires_at của K4 | Từ chối; khoảng hiệu lực là nửa mở |
| Version 4 ACTIVE, HMAC đúng nhưng nonce đã dùng | Từ chối replay trên mọi instance |
| Hai tác vụ cùng cấp version 5 | Chỉ một tác vụ thành công với cặp (client, 5); tác vụ còn lại retry hoặc báo xung đột |
| Revoke K3 và sự kiện cache đến không đúng thứ tự | Không hồi sinh K3 ở một node khác |
| Client gửi version 4 qua proxy biến đổi URI | Phát hiện mismatch canonical request và xử lý theo hợp đồng ký |
| Registry hoặc secret manager không khả dụng | Fail closed; có cảnh báo nhưng không thử version khác |

Nên bổ sung kiểm thử phân tán: trong khi K3 và K4 cùng ACTIVE, phát request song song tới nhiều gateway/region, sau đó RETIRE hoặc REVOKE K3 và đo thời gian cho tới khi tất cả node đều từ chối. Kiểm tra riêng trường hợp client chạy chậm, nhiều instance có bản cấu hình khác nhau, duplicate header, version số quá lớn, ký tự lạ, body thay đổi và đồng hồ lệch.

**Phân biệt xác thực với phân quyền:** sau khi K4 được xác minh, server chỉ biết request đến từ principal sở hữu K4 theo chính sách xác thực. Principal đó vẫn cần được kiểm tra quyền truy cập vào thao tác chuyển tiền, xem dữ liệu hoặc tài nguyên cụ thể. K4 mới hơn K3 không có nghĩa quyền cao hơn.

## 11. Bài tập tự kiểm tra

Một đối tác có K8 ACTIVE, K9 PENDING. Client đã cập nhật cấu hình X-Key-Version: 9 nhưng vẫn giữ secret K8 trong bộ nhớ. Gateway A có metadata K9; gateway B chỉ có cache của K8. Hãy phân tích:

1. Request version 9 ký bằng K8 có được chấp nhận tại A không? Nếu B không tìm thấy K9 thì phải xử lý ra sao?
2. Thứ tự triển khai nào giúp tránh downtime khi chuyển từ K8 sang K9?
3. Nếu K8 bị lộ ngay trước khi K9 được kích hoạt, có được cho K8 tiếp tục dùng trong giai đoạn chồng lấp không?
4. Những chỉ số vận hành nào cho biết client đã thực sự chuyển sang K9?

**Gợi ý:** A phải từ chối vì K9 chưa ACTIVE và chữ ký không khớp với secret K9; B phải từ chối an toàn vì không tìm thấy version 9. Cần chuẩn bị registry/verifier, phân phối secret K9, kích hoạt K9 rồi mới chuyển client; giữ K8 ACTIVE chỉ khi vẫn tin cậy, và REVOKE ngay nếu K8 đã bị lộ. Theo dõi request thành công/thất bại theo version, lưu ý cả các client ít gửi request và độ trễ log.

Key version phát huy giá trị khi **định danh bất biến một secret cụ thể**, được truyền và ràng buộc rõ ràng trong hợp đồng ký, được chọn chính xác lúc xác minh, và có trạng thái vòng đời riêng. Nhờ vậy, HMAC request authentication có thể chuyển khóa với cửa sổ tương thích có kiểm soát mà vẫn thực thi chính xác việc hết hạn và thu hồi credential.
