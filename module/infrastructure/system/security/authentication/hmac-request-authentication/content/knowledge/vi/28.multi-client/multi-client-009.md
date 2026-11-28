# Client disabled trong hệ thống HMAC xác thực nhiều client

## 1. Client disabled có nghĩa là gì?

Một dịch vụ API có thể tiếp nhận request từ nhiều ứng dụng nội bộ, đối tác hoặc tenant khác nhau. Với **HMAC request authentication**, mỗi client thường sở hữu ít nhất một credential gồm **key ID** và **shared secret** để tạo chữ ký từ canonical request. Server dùng key ID để tra cứu secret, dựng lại canonical request theo hợp đồng ký và xác minh chữ ký.

Tuy nhiên, một client có thể đã bị **vô hiệu hóa (disabled)** vì ngừng hợp đồng, vi phạm chính sách, bị nghi xâm nhập, vượt qua quy trình xử lý sự cố hoặc bị quản trị viên tạm ngừng quyền truy cập. Khi đó, **không credential nào thuộc client ấy được phép xác thực request mới**, kể cả khi:

- Key ID vẫn tồn tại trong registry;
- Secret vẫn tính ra HMAC chính xác;
- Một hoặc nhiều key version còn ACTIVE và chưa hết hạn;
- Timestamp nằm trong cửa sổ chấp nhận, nonce chưa từng sử dụng;
- Client từng có quyền gọi endpoint này.

Nói cách khác, chữ ký HMAC hợp lệ chứng minh khả năng sở hữu secret gắn với một credential; **trạng thái client** quyết định danh tính ứng dụng đó có còn được hệ thống tiếp nhận hay không. Xác thực thành công vẫn chưa đủ để được truy cập tài nguyên: **authorization** phải kiểm tra quyền của client đối với từng hành động nghiệp vụ.

Ví dụ, hệ thống có ba client:

| Client ID | Trạng thái client | Credential | Trạng thái credential | Kết quả |
| --- | --- | --- | --- | --- |
| partner-a | ENABLED | a-k5 | ACTIVE | Có thể tiếp tục xác minh HMAC và quyền |
| partner-a | ENABLED | a-k4 | REVOKED | Từ chối credential a-k4 |
| partner-b | DISABLED | b-k7 | ACTIVE | Từ chối mọi request của partner-b |
| partner-b | DISABLED | b-k8 | ACTIVE | Vẫn từ chối dù đã chuyển sang key mới |
| partner-c | ENABLED | c-k2 | ACTIVE | Hoạt động độc lập, không bị ảnh hưởng bởi partner-b |

Nếu chỉ vô hiệu hóa một key của partner-b mà để key khác ACTIVE, client vẫn có thể gửi request bằng key còn lại. Đó là lý do **client disabled** phải là một điều kiện riêng, có phạm vi **toàn bộ credential của client**.

## 2. Phân biệt client disabled, credential revoked và quyền truy cập

Các chính sách này thường cùng xuất hiện nhưng có phạm vi và hậu quả khác nhau:

| Cơ chế | Phạm vi | Nguyên nhân phổ biến | Chặn request bằng key khác cùng client? |
| --- | --- | --- | --- |
| Client DISABLED | Toàn bộ định danh client | Dừng tích hợp, nghi xâm nhập, khóa thủ công | **Có** |
| Credential SUSPENDED | Một credential hoặc key version | Tạm dừng một khóa để kiểm tra | Không, trừ khi có quy tắc bổ sung |
| Credential REVOKED | Một credential/key version | Secret lộ hoặc khóa không còn đáng tin | Không, nếu client còn key khác hợp lệ |
| Credential EXPIRED | Một credential tại thời điểm kiểm tra | Hết thời hạn đã cấp | Không |
| Authorization DENIED | Một hành động hoặc tài nguyên | Thiếu role, scope, tenant ownership | Tùy hành động; không quyết định tình trạng credential |
| Rate limit exceeded | Client/request theo quota | Lưu lượng vượt hạn mức | Thường chỉ từ chối theo cửa sổ giới hạn |

Một tổ chức có thể đặt thêm trạng thái SUSPENDED hoặc CLOSED ở cấp client. Để tránh mơ hồ, bài này dùng hai trạng thái cấu hình tối thiểu:

- **ENABLED:** client được xét tiếp nếu credential, chữ ký, thời gian, nonce và quyền truy cập đều hợp lệ.
- **DISABLED:** client bị từ chối tại cổng xác thực bất kể credential nào được gửi.

Hệ thống có thể lưu lý do vô hiệu hóa như SECURITY_INCIDENT, CONTRACT_TERMINATED, ADMINISTRATIVE hoặc POLICY_VIOLATION. **Lý do là metadata nội bộ**, không nên được phản hồi nguyên văn cho người gửi request chưa được xác thực, vì nó có thể làm lộ trạng thái tài khoản đối tác.

### Một client, nhiều key version

Trong key rotation, partner-a có thể dùng đồng thời a-k5 và a-k6 trong cửa sổ chuyển tiếp. Khi partner-a được ENABLED, cả hai key có thể hợp lệ tùy trạng thái của từng credential. Nếu quản trị viên chuyển partner-a sang DISABLED, **cả a-k5 và a-k6 lập tức thuộc phạm vi bị chặn theo chính sách**. Kích hoạt key mới, thay key version hay thay shared secret **không tự mở lại client**.

Với sự cố lộ secret, có thể cần **cả hai** biện pháp: DISABLED ở cấp client để ngăn mọi đường đăng nhập và REVOKED ở cấp credential bị lộ để bảo đảm không thể tiếp tục sử dụng khi client được kích hoạt lại. Chỉ bật ENABLED khi nguy cơ xâm nhập đã được xử lý và người có thẩm quyền cho phép.

## 3. Xác định đúng client trong môi trường multi-client

Một request có thể gửi header X-Client-Id và X-Key-Id hoặc X-Key-Version:

~~~http
POST /v1/orders?region=vn HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-b
X-Key-Id: partner-b-k7
X-Timestamp: 2026-11-28T03:20:00Z
X-Nonce: 8d9cf2a7-a2dc-4e88-89f1-ef48ce53f119
X-Signature: <gia-tri-base64-chu-ky>

{"orderId":"ord-841"}
~~~

Đây là request minh họa, không phải test vector HMAC hoàn chỉnh. Server phải coi **X-Client-Id và X-Key-Id là dữ liệu do người gửi tự khai** cho đến khi xác minh chữ ký. Không được dùng riêng X-Client-Id để gán danh tính đã xác thực, thực thi thao tác nhạy cảm hoặc ghi nhận “partner-b đã đăng nhập”.

Thiết kế tra cứu nên đảm bảo:

1. **Key ID định danh đúng một credential**. Bản ghi credential có client_id chủ sở hữu bất biến.
2. Khi request khai cả client ID và key ID, **hai giá trị phải khớp** với client_id của credential; nếu khác, từ chối. Không tự sửa một giá trị dựa trên giá trị kia.
3. Nếu hệ thống dùng cặp (client_id, key_version), cặp ấy phải xác định duy nhất một secret và không được tái sử dụng.
4. Không cho cùng một credential thuộc nhiều client khác nhau. Không dùng key của partner-a để xác thực partner-b dù vô tình có cùng secret hoặc dữ liệu cấu hình bị lỗi.
5. Định danh client/key ID có độ dài, charset, chuẩn hóa rõ ràng và không chấp nhận header trùng, chứa nhiều giá trị hoặc biểu diễn mơ hồ.

Khi hệ thống nhiều tenant, có thể cần xét thêm **trạng thái tenant** bên cạnh trạng thái client. Ví dụ một tenant bị khóa thì tất cả client trong tenant bị chặn; đồng thời một client bị DISABLED không làm ảnh hưởng client thuộc tenant khác. Quy tắc này phải được thể hiện trực tiếp trong đường xác thực, thay vì chỉ nằm trong giao diện quản trị.

## 4. Đưa trạng thái client vào đường xác thực HMAC

Một bộ xác minh HMAC trong hệ thống nhiều client có thể thực hiện các bước sau:

~~~mermaid
flowchart TD
    A["Nhận HTTP request"] --> B["Parse và kiểm tra key ID, client ID, header ký"]
    B --> C["Tra cứu credential và client sở hữu"]
    C --> D{"Client ENABLED và registry đủ mới?"}
    D -->|Không| X["Từ chối xác thực"]
    D -->|Có| E{"Credential ACTIVE và còn hiệu lực?"}
    E -->|Không| X
    E -->|Có| F["Dựng canonical request theo hợp đồng"]
    F --> G{"HMAC đúng với secret đã chọn?"}
    G -->|Không| X
    G -->|Có| H{"Timestamp hợp lệ?"}
    H -->|Không| X
    H -->|Có| I{"Nonce mới được ghi nguyên tử?"}
    I -->|Không| X
    I -->|Có| J["Thiết lập danh tính đã xác thực"]
    J --> K{"Có quyền gọi endpoint?"}
    K -->|Không| Y["Từ chối phân quyền"]
    K -->|Có| L["Thực hiện nghiệp vụ"]
~~~

Phần **client ENABLED** là điều kiện bắt buộc. Nó không được chỉ kiểm tra khi client đăng nhập lần đầu, chỉ trong chức năng quản trị, hoặc chỉ khi cấp credential mới. HMAC request authentication thường là xác thực **trên từng request**, nên mỗi quyết định chấp nhận phải dựa trên trạng thái đủ mới của client tương ứng.

Một số hệ thống xác minh HMAC trước rồi mới kiểm tra trạng thái client để giảm khác biệt về thời gian phản hồi hoặc thuận tiện kết hợp pipeline. Điều này có thể được thiết kế an toàn nếu **mọi đường chấp nhận request đều kiểm tra trạng thái client trước khi xác thực hoàn tất và trước khi thực thi nghiệp vụ**. Thứ tự cụ thể cần được kiểm tra về nguy cơ tiết lộ thông tin và tải tính toán; không có phép kiểm tra HMAC nào tự thay thế bước kiểm tra DISABLED.

### Tại sao key rotation không được bỏ qua client disabled?

Giả sử partner-b đang DISABLED nhưng đối tác tiếp tục gửi HMAC đúng bằng key mới b-k8. Nếu server chỉ kiểm tra b-k8 ACTIVE và chưa hết hạn rồi xác thực thành công, việc vô hiệu hóa client đã bị bỏ qua hoàn toàn. Hệ thống cần tính **hiệu lực tổng hợp**:

> Client được ENABLED **và** credential thuộc client đó được ACTIVE **và** còn thời hạn **và** request đáp ứng hợp đồng ký, chống replay; sau đó mới xét phân quyền.

Các điều kiện này không thể dùng phép OR. Một credential ACTIVE không “ghi đè” trạng thái client DISABLED.

### Chú ý canonical request qua proxy/gateway

Một hợp đồng ký có thể quy định canonical request gồm method, path/query, những header được chọn, timestamp, nonce và body hash. Ví dụ:

~~~text
HMAC-REQUEST-V1
POST
/v1/orders?region=vn
partner-b
partner-b-k7
2026-11-28T03:20:00Z
8d9cf2a7-a2dc-4e88-89f1-ef48ce53f119
<sha256-hex-cua-body-bytes>
~~~

Ví dụ chỉ mô tả cấu trúc; cần thay dòng cuối bằng digest thực tế và xác định rõ ký tự phân cách/newline trước khi thử nghiệm. Client ID và key ID nên được ràng buộc vào dữ liệu ký theo hợp đồng, tránh việc người gửi sửa header chọn credential mà không làm thay đổi canonical bytes.

Khi proxy rewrite URL, chuẩn hóa query, chuyển mã ký tự hoặc thay header, client và server phải thống nhất đúng dạng canonical request. **SIGNATURE_MISMATCH** do proxy không đồng nghĩa client đang DISABLED. Hệ thống cần tách lý do lỗi nội bộ để điều tra đúng nguyên nhân nhưng không lộ chi tiết vào phản hồi công khai.

## 5. Thiết kế registry trạng thái client và credential

Tách bảng client và credential giúp thao tác DISABLED ở cấp client có hiệu lực với mọi key version, không phải cập nhật hàng loạt key theo cách dễ bỏ sót:

~~~sql
CREATE TABLE hmac_clients (
    client_id VARCHAR(128) PRIMARY KEY,
    tenant_id VARCHAR(128) NOT NULL,
    lifecycle_state VARCHAR(16) NOT NULL
        CHECK (lifecycle_state IN ('ENABLED', 'DISABLED')),
    disabled_at TIMESTAMPTZ,
    disabled_reason_code VARCHAR(64),
    state_changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    row_version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE hmac_credentials (
    key_id VARCHAR(128) PRIMARY KEY,
    client_id VARCHAR(128) NOT NULL
        REFERENCES hmac_clients(client_id),
    secret_ref VARCHAR(256) NOT NULL,
    lifecycle_state VARCHAR(16) NOT NULL
        CHECK (lifecycle_state IN
            ('PENDING', 'ACTIVE', 'SUSPENDED', 'REVOKED', 'RETIRED')),
    valid_from TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    key_version INTEGER NOT NULL CHECK (key_version > 0),
    row_version BIGINT NOT NULL DEFAULT 0,
    UNIQUE (client_id, key_version),
    CHECK (expires_at > valid_from)
);

CREATE INDEX hmac_credentials_owner_idx
    ON hmac_credentials(client_id, lifecycle_state);
~~~

Đây là lược đồ minh họa. Trong sản phẩm thực tế, tenant_id cần khóa ngoại, trạng thái tenant cần cơ chế riêng và các ràng buộc bất biến có thể được thực thi bằng transaction/quyền cập nhật phù hợp. Secret không nằm trong bảng dưới dạng rõ: **secret_ref** tham chiếu tới kho bí mật có quyền truy cập giới hạn. Khi client DISABLED, **không cần đổi từng credential thành REVOKED** nếu mục tiêu chỉ là tạm ngừng client; nhưng nếu có secret bị lộ, vẫn phải thu hồi credential đó.

Một cách tra cứu phục vụ xác thực:

~~~sql
SELECT
    k.key_id,
    k.client_id,
    k.secret_ref,
    k.lifecycle_state AS credential_state,
    k.valid_from,
    k.expires_at,
    k.revoked_at,
    c.lifecycle_state AS client_state,
    c.row_version AS client_row_version
FROM hmac_credentials AS k
JOIN hmac_clients AS c ON c.client_id = k.client_id
WHERE k.key_id = :key_id
  AND k.client_id = :claimed_client_id;
~~~

Kết quả phải được đánh giá **đúng tại điểm xác thực**, với thời gian server. Khi trả về 0 hàng, kết luận không có credential hợp lệ cho request; không dò key khác hay tự động chọn key mới nhất. Tránh sử dụng snapshot của client và credential từ các nguồn/cache không nhất quán mà chưa có chính sách xử lý rõ ràng.

Nếu dữ liệu client bị đổi DISABLED trong khi nhiều gateway đang xử lý, việc database đã cập nhật chưa bảo đảm mọi instance thấy ngay; đó là vấn đề lan truyền trạng thái được phân tích ở phần 8.

## 6. Ví dụ Java 17: quyết định client và credential có đủ điều kiện không

Đưa quy tắc vào một policy rõ ràng giúp tránh lỗi ở những endpoint quên kiểm tra trạng thái client. Ví dụ Java 17 sau chỉ đánh giá **điều kiện được phép tiếp tục kiểm tra HMAC**. Mã này không tự xác minh chữ ký, timestamp, nonce hoặc phân quyền.

~~~java
import java.time.Instant;
import java.util.Objects;

public final class MultiClientCredentialPolicy {
    enum ClientState {
        ENABLED, DISABLED
    }

    enum KeyState {
        PENDING, ACTIVE, SUSPENDED, REVOKED, RETIRED
    }

    enum Decision {
        ELIGIBLE_FOR_HMAC,
        UNKNOWN_OR_MISMATCHED,
        CLIENT_DISABLED,
        KEY_NOT_ACTIVE,
        KEY_REVOKED,
        KEY_NOT_YET_VALID,
        KEY_EXPIRED
    }

    record ClientSnapshot(
        String clientId,
        ClientState state,
        long rowVersion
    ) {}

    record CredentialSnapshot(
        String keyId,
        String ownerClientId,
        KeyState state,
        Instant validFrom,
        Instant expiresAt,
        Instant revokedAt
    ) {}

    static Decision evaluate(
        String claimedClientId,
        String requestedKeyId,
        ClientSnapshot client,
        CredentialSnapshot credential,
        Instant serverNow
    ) {
        Objects.requireNonNull(serverNow, "serverNow");

        if (client == null || credential == null
                || claimedClientId == null || requestedKeyId == null
                || !claimedClientId.equals(client.clientId())
                || !requestedKeyId.equals(credential.keyId())
                || !client.clientId().equals(credential.ownerClientId())) {
            return Decision.UNKNOWN_OR_MISMATCHED;
        }

        // Trạng thái client phủ lên mọi credential thuộc client đó.
        if (client.state() != ClientState.ENABLED) {
            return Decision.CLIENT_DISABLED;
        }

        if (credential.state() == KeyState.REVOKED
                || credential.revokedAt() != null) {
            return Decision.KEY_REVOKED;
        }

        if (credential.state() != KeyState.ACTIVE) {
            return Decision.KEY_NOT_ACTIVE;
        }

        if (serverNow.isBefore(credential.validFrom())) {
            return Decision.KEY_NOT_YET_VALID;
        }

        // Khoảng hiệu lực [validFrom, expiresAt).
        if (!serverNow.isBefore(credential.expiresAt())) {
            return Decision.KEY_EXPIRED;
        }

        return Decision.ELIGIBLE_FOR_HMAC;
    }

    public static void main(String[] args) {
        var client = new ClientSnapshot(
            "partner-b", ClientState.DISABLED, 9L
        );
        var activeKey = new CredentialSnapshot(
            "partner-b-k8",
            "partner-b",
            KeyState.ACTIVE,
            Instant.parse("2026-11-01T00:00:00Z"),
            Instant.parse("2027-02-01T00:00:00Z"),
            null
        );
        var result = evaluate(
            "partner-b",
            "partner-b-k8",
            client,
            activeKey,
            Instant.parse("2026-11-28T04:00:00Z")
        );
        System.out.println(result); // CLIENT_DISABLED
    }
}
~~~

Đoạn code thể hiện ba bất biến:

1. **Không cho request mượn key của client khác.** claimedClientId, client snapshot và credential owner phải khớp; không lấy client_id khai trong header làm danh tính tin cậy trước khi HMAC được xác minh.
2. **Client DISABLED chặn tất cả key, kể cả key ACTIVE.** Nếu thay b-k8 bằng b-k9 nhưng client vẫn DISABLED, kết quả không đổi.
3. **Điều kiện thời gian dùng đồng hồ server.** Timestamp trong request phục vụ chống replay, không quyết định thời điểm hết hạn credential.

Hệ thống thực tế còn phải tra cứu client/credential với mức độ mới phù hợp; chỉ tiếp tục khi policy trả ELIGIBLE_FOR_HMAC, sau đó lấy secret từ secret manager để tính HMAC theo hợp đồng ký, so sánh chữ ký an toàn về timing, kiểm tra timestamp/nonce và cuối cùng xác định quyền truy cập. Không đưa các mã Decision nội bộ trực tiếp vào phản hồi công khai nếu chúng tạo ra oracle dò key ID hoặc trạng thái client.

Nếu kho registry hoặc secret manager không truy cập được, không được tự coi client là ENABLED. Khi không chứng minh được trạng thái cho một request, áp dụng chính sách **fail closed**.

## 7. Thao tác disable/enable an toàn và có kiểm toán

Không nên cho client tự gọi một endpoint HMAC thông thường để tự kích hoạt lại khi đã bị vô hiệu hóa. Thao tác quản trị này cần **kênh xác thực quản trị riêng**, phân quyền tương ứng, ghi lý do, và trong trường hợp nhạy cảm cần phê duyệt hoặc cơ chế kiểm soát bổ sung.

### Vô hiệu hóa một client

Một cách cập nhật có optimistic locking trong PostgreSQL:

~~~sql
UPDATE hmac_clients
SET lifecycle_state = 'DISABLED',
    disabled_at = CURRENT_TIMESTAMP,
    disabled_reason_code = :reason_code,
    state_changed_at = CURRENT_TIMESTAMP,
    row_version = row_version + 1
WHERE client_id = :client_id
  AND lifecycle_state = 'ENABLED'
  AND row_version = :expected_row_version
RETURNING client_id, lifecycle_state, disabled_at, row_version;
~~~

Ứng dụng phải xác nhận UPDATE trả **đúng một hàng**. Nếu không có hàng được cập nhật, phải đọc lại bản ghi và phân biệt không tồn tại, đã DISABLED hoặc xung đột phiên bản. Không tự ghi đè trạng thái mới do thao tác khác vừa cập nhật.

Nên ghi **audit record** và một **outbox event** trong cùng transaction với thay đổi trạng thái, ví dụ sự kiện CLIENT_DISABLED gồm client_id, version trạng thái mới, actor, reason_code, timestamp, incident/correlation ID. Phần gửi event sang message bus có thể xử lý sau commit; consumer kiểm tra row_version để không áp dụng lại sự kiện ENABLED cũ hơn.

### Kích hoạt lại client

Việc chuyển DISABLED → ENABLED phải là **quyết định riêng**, yêu cầu:

- Người có quyền xác nhận lý do tạm ngừng đã được xử lý;
- Nếu nghi xâm nhập, đã điều tra môi trường client và đường cấp phát secret;
- Credential bị lộ đã REVOKED và đã có credential mới an toàn;
- Client vẫn thuộc tenant/chủ sở hữu hợp lệ và chính sách cho phép hoạt động;
- Các verifier/cache có cơ chế cập nhật trạng thái mới một cách nhất quán;
- Thao tác, phê duyệt và thời gian được lưu trong audit.

**Enable client không tự động enable credential.** Nếu b-k7 bị REVOKED trong sự cố, sau khi partner-b ENABLED trở lại, b-k7 vẫn phải bị từ chối. Chỉ key còn ACTIVE và hợp lệ mới có thể được dùng.

### Bài toán nhiều thao tác cùng lúc

Quản trị viên A disable client trong lúc quản trị viên B enable theo một ticket cũ. Nếu chỉ dùng UPDATE không có version và tiền điều kiện, B có thể vô tình bật lại client vừa bị khóa vì sự cố. row_version và kiểm tra trạng thái cần được kết hợp với quyền hạn, yêu cầu phê duyệt và version của quyết định bảo mật. Với lệnh disable khẩn cấp, một cơ chế khóa ở cấp principal/tenant có thể được ưu tiên và chỉ gỡ khi được phê duyệt.

## 8. Lan truyền trạng thái disabled tới nhiều gateway

Trạng thái client có thể được cache để giảm độ trễ tra cứu. Đây là nguồn rủi ro lớn nhất khi yêu cầu vô hiệu hóa có hiệu lực nhanh.

Giả sử:

- 10:00:00, gateway A đọc partner-b=ENABLED và lưu cache 60 giây.
- 10:00:10, hệ thống quản trị ghi partner-b=DISABLED vào registry.
- 10:00:15, client gửi request mới có HMAC đúng qua gateway A.

Nếu gateway A chỉ dùng snapshot cũ đến 10:01:00, request **có thể bị chấp nhận sai**. TTL 60 giây không đáp ứng yêu cầu chặn ngay sau thời điểm disable.

~~~mermaid
sequenceDiagram
    participant O as Operator
    participant R as Client registry
    participant E as Event/Outbox
    participant A as Gateway A
    participant B as Gateway B
    O->>R: DISABLE partner-b
    R->>R: Commit DISABLED, rowVersion=10
    R-->>O: Đã ghi trạng thái nguồn
    R-->>E: Outbox event version 10
    E->>A: Invalidate partner-b
    E--xB: B tạm mất kết nối
    A->>R: Reload trạng thái mới
    R-->>A: DISABLED version 10
    Note over B: Cache cũ ENABLED version 9
    B->>B: Phải kiểm tra freshness hoặc fail closed
~~~

Các lựa chọn thiết kế:

| Cơ chế | Ưu điểm | Điểm cần kiểm soát |
| --- | --- | --- |
| TTL ngắn | Giới hạn thời gian snapshot cũ trong tình huống thường | Vẫn tồn tại cửa sổ sai; không bảo đảm tức thì |
| Event invalidation + version | Giảm độ trễ cập nhật, tránh event cũ ghi đè event mới | Node mất event vẫn có thể dùng cache cũ |
| Denylist client ở gateway | Chặn nhanh client cụ thể | Phải áp dụng trên mọi đường vào, có độ mới đo được |
| Registry đọc nhất quán ở điểm xác thực | Có thể đáp ứng yêu cầu trạng thái rất mới | Tăng tải/độ trễ, phải xử lý downtime và tính nhất quán |
| Chính sách freshness và fail closed | Không tin snapshot cũ quá ngưỡng | Có thể từ chối request hợp lệ khi phụ trợ lỗi |
| Client status epoch / revision | Giúp nhận biết sự kiện bị đảo thứ tự | Revision cao không chứng minh node đã biết revision mới nhất |

**Yêu cầu bảo đảm cần phát biểu chính xác.** Nếu sản phẩm cam kết “mọi request bắt đầu sau commit DISABLED đều bị từ chối”, mỗi verifier phải có cách đọc/truyền đạt trạng thái đủ mới để không bỏ sót commit đó, hoặc từ chối khi không thể xác minh. Chỉ có pub/sub và TTL không chứng minh được cam kết này. Cũng phải xác định request đã qua điểm xác thực **trước** commit có được phép xử lý nốt hay không; với thao tác nhạy cảm có thể cần kiểm tra lại trạng thái ở trước điểm commit nghiệp vụ.

Nếu hệ thống dùng JWT/session được cấp sau HMAC, cần làm rõ client DISABLED có phải vô hiệu hóa luôn session/token đang tồn tại hay không. Chỉ chặn các request HMAC mới không tự động thu hồi token đã phát hành. Trong kiến trúc như vậy, các điểm chấp nhận token cũng cần kiểm tra epoch/trạng thái hoặc cơ chế thu hồi riêng theo hợp đồng bảo mật.

## 9. Phản hồi HTTP, log và an toàn thông tin

Một request gửi key ID không tồn tại và một request thuộc client DISABLED có thể cần trả **cùng dạng phản hồi xác thực thất bại** để tránh việc bên ngoài dò được danh tính nào đang được đăng ký hoặc đang bị khóa.

Ví dụ thông báo công khai:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{"error":"authentication_failed"}
~~~

Lựa chọn HTTP 401 hay mã khác phải theo hợp đồng API và cách dùng challenge của cơ chế xác thực; cần nhất quán. **403 Forbidden** thường dành cho principal đã được xác thực nhưng không được phép thực hiện hành động. Trong nhiều thiết kế, client DISABLED được xem là **không đủ điều kiện xác thực**, nên có thể dùng cùng phản hồi 401 như credential không hợp lệ. Không cung cấp thông tin kiểu “client partner-b tồn tại nhưng đã bị vô hiệu hóa” trong response dành cho đối tượng chưa được xác thực.

Bên trong hệ thống, có thể log nguyên nhân theo mã cố định như CLIENT_DISABLED, KEY_REVOKED, SIGNATURE_MISMATCH, REPLAY_DETECTED, CLIENT_KEY_MISMATCH, REGISTRY_UNAVAILABLE. Ghi correlation ID, environment, verifier ID, client/key ID ở định dạng được bảo vệ và timestamp server; hạn chế quyền đọc, thời gian lưu và mức chi tiết theo quy định.

Không log shared secret, chữ ký HMAC, toàn bộ canonical request chứa dữ liệu nhạy cảm hay body nghiệp vụ. Không để key ID có cardinality lớn thành nhãn metric vô hạn; với dashboard tổng hợp nên dùng các nhãn hữu hạn như environment, service, result_code, region. Audit chi tiết có kiểm soát riêng cho từng client.

### Tránh làm lộ trạng thái qua timing

Nếu key không tồn tại bị từ chối ngay trong vài microsecond nhưng client DISABLED buộc server đọc nhiều dữ liệu, độ trễ có thể giúp suy đoán về sự tồn tại của client. Hệ thống nên đánh giá bề mặt side-channel, hạn chế tốc độ request, không để lỗi khác biệt quá rõ và chuẩn hóa phản hồi. Không nên tạo lời hứa “constant-time cho cả pipeline” vì truy cập DB và cache vốn không có thời gian hằng; việc so sánh HMAC đúng độ dài vẫn cần thực hiện với hàm so sánh an toàn về timing.

## 10. Giám sát client disabled và thao tác điều tra

Một giao diện quản trị có ích nên phân biệt **trạng thái cấu hình tại registry** và **trạng thái đang được các verifier áp dụng**.

| Thông tin | Ý nghĩa sử dụng |
| --- | --- |
| Client ID, tenant ID, owner | Xác định chính xác đối tượng và ranh giới trách nhiệm |
| ENABLED/DISABLED, disabled_at, reason_code | Biết quyết định hiện tại và lý do có kiểm soát |
| state_changed_at, row_version | Phân biệt sự kiện mới/cũ, hỗ trợ audit |
| Danh sách credential, key version và trạng thái | Kiểm tra mọi key liên quan có bị ảnh hưởng |
| Số request bị từ chối do CLIENT_DISABLED | Phát hiện client vẫn đang gửi sau khi bị khóa |
| Độ trễ áp dụng trạng thái theo gateway/region | Xác minh kết quả chặn trong thực tế |
| Thao tác bật/tắt, actor, ticket và phê duyệt | Truy vết thay đổi và phục vụ hậu kiểm |
| Request bằng key đã REVOKED | Điều tra sử dụng secret cũ hoặc bất thường |

Khi client bị disabled do nghi xâm nhập, số lượng request bị chặn cao không tự chứng minh có tấn công: ứng dụng cũ có thể tiếp tục retry. Cần đối chiếu timestamp, nguồn, endpoint, key ID và các dấu hiệu khác mà không làm lộ dữ liệu bí mật.

Một ví dụ truy vấn danh sách client đang disabled:

~~~sql
SELECT client_id, tenant_id, disabled_at,
       disabled_reason_code, row_version
FROM hmac_clients
WHERE lifecycle_state = 'DISABLED'
ORDER BY disabled_at DESC;
~~~

Hệ thống có thể phát cảnh báo cho các tình huống: gateway vẫn chấp nhận request của client sau thời điểm disabled theo cam kết; một node bỏ lỡ event; client bị enable lại ngoài quy trình; nhiều request tiếp tục dùng key bị thu hồi; hoặc độ trễ cập nhật vượt ngưỡng vận hành.

## 11. Sai lầm dễ xảy ra trong hệ thống nhiều client

### Chỉ disable key version hiện tại

Client còn version cũ ACTIVE trong cửa sổ rotation và tiếp tục gọi API. Giải pháp: kiểm tra trạng thái **client** cho mọi key version, đồng thời xử lý key bị lộ bằng trạng thái REVOKED riêng.

### Tin client ID trong header trước khi xác minh HMAC

Kẻ tấn công tự ghi X-Client-Id: partner-a để giả danh một đối tác. Giải pháp: dùng giá trị này chỉ làm khóa tra cứu có kiểm soát; sau khi chữ ký đúng mới gán authenticated principal, và bắt buộc credential.owner_client_id khớp.

### Endpoint A kiểm tra disabled nhưng endpoint B quên

Các API dùng middleware khác nhau, một endpoint nội bộ hoặc đường truyền trực tiếp vào service không qua gateway chính. Giải pháp: tập trung lớp quyết định xác thực hoặc policy dùng chung ở tất cả đường truy cập; kiểm thử cả các đường bypass và nội bộ.

### Registry đã cập nhật nhưng cache vẫn ENABLED

Bảng quản trị hiển thị DISABLED trong khi một node không nhận invalidation. Giải pháp: đo độ trễ áp dụng thực tế, dùng revision và chính sách freshness; từ chối khi không chứng minh trạng thái hiện hành.

### Disable client đồng nghĩa xóa mọi dữ liệu

Nếu xóa credential/client khi tạm ngừng, mất bằng chứng kiểm toán, khó phân biệt request dùng key cũ, khó khôi phục an toàn. Giải pháp: giữ trạng thái và lịch sử theo chính sách lưu trữ, hạn chế quyền, xóa/hủy bí mật theo lịch và yêu cầu bảo mật được xác định.

### Enable lại client đồng thời phục hồi key bị lộ

Nếu thao tác ENABLED tự chuyển tất cả credential về ACTIVE, một secret đã REVOKED có thể được dùng lại. Giải pháp: tách vòng đời client và credential; REVOKED là trạng thái kết thúc theo chính sách.

### Tắt kiểm tra nonce/timestamp để giảm lỗi client

Client bị disabled do sự cố và khi phục hồi API bỏ qua nonce do replay store chậm. Điều này làm mất cơ chế chống replay. Giải pháp: tiếp tục yêu cầu timestamp trong cửa sổ đã định và nonce được ghi atomically trong kho dùng chung giữa các verifier. Chỉ ghi nonce sau khi chữ ký đã được xác minh để hạn chế việc chiếm chỗ trước nonce của người gửi hợp lệ.

## 12. Bộ tình huống kiểm thử

| Tình huống | Kỳ vọng |
| --- | --- |
| Client ENABLED, credential ACTIVE, HMAC đúng, timestamp/nonce mới | Qua xác thực; tiếp tục kiểm tra quyền |
| Client DISABLED, credential ACTIVE, HMAC đúng | Từ chối xác thực |
| Client DISABLED, có hai key version ACTIVE | Cả hai phiên bản đều bị chặn |
| Client DISABLED, cấp thêm key mới ACTIVE | Vẫn từ chối; không thể bỏ qua disabled bằng rotation |
| Client ENABLED, credential REVOKED | Từ chối key đã thu hồi |
| Client vừa ENABLED lại, credential cũ vẫn REVOKED | Key cũ tiếp tục bị từ chối |
| claimedClientId = partner-a, key thuộc partner-b | Từ chối mismatch, không gán danh tính partner-a |
| Client ID không tồn tại | Từ chối với phản hồi công khai không tiết lộ registry |
| HMAC sai cho client ENABLED | Từ chối mà không ghi danh tính đã xác thực |
| HMAC đúng nhưng nonce trùng ở instance khác | Từ chối replay |
| Header X-Client-Id trùng, chứa nhiều giá trị | Từ chối cú pháp mơ hồ |
| Client A DISABLED, client C ENABLED | Chỉ A bị chặn; C tiếp tục hoạt động độc lập |
| Client DISABLED qua gateway A, request tới gateway B cache cũ | B phải tuân theo cam kết freshness hoặc fail closed |
| Event ENABLED revision 8 đến sau DISABLED revision 9 | Không cho cache quay về ENABLED revision 8 |
| Hai quản trị viên thay trạng thái với cùng row_version | Chỉ một thao tác cập nhật thành công; còn lại thấy xung đột |
| Registry/secret manager/nonce store không khả dụng | Không chấp nhận thiếu kiểm tra; fail closed theo chính sách |
| Client ENABLED và HMAC đúng nhưng thiếu quyền API | Từ chối authorization; không phải lỗi trạng thái client |
| Proxy rewrite URI làm HMAC mismatch | Từ chối chữ ký, tách mã nguyên nhân khỏi CLIENT_DISABLED |
| Token/session được cấp trước lúc disable còn hiệu lực | Phải đáp ứng chính sách thu hồi token/session riêng nếu hệ thống yêu cầu |
| Request đã xác thực trước khi commit disable | Áp dụng chính sách xử lý in-flight, kiểm tra lại trước hành động nhạy cảm nếu cần |

### Bài tập tình huống

Hệ thống có ba khách hàng A, B, C. Mỗi khách hàng có hai key version đang ACTIVE do rotation. Lúc 09:30:00, quản trị viên disable B sau khi phát hiện rủi ro. Registry ghi B=DISABLED, row_version=15. Gateway 1 nhận event lập tức; Gateway 2 bị ngắt event bus 45 giây và vẫn giữ B=ENABLED version 14. Trong lúc đó, client B gửi một request có chữ ký đúng bằng key mới B-k8.

Hãy trả lời:

1. Vì sao B-k8 ACTIVE và HMAC đúng vẫn không đủ điều kiện xác thực?
2. Nếu Gateway 2 chỉ sử dụng cache đến hết TTL 60 giây, nguy cơ cụ thể là gì?
3. Muốn cam kết không chấp nhận request mới của B sau thời điểm disable, Gateway 2 phải có khả năng nào khi mất kết nối event bus?
4. Gateway 2 có được dùng key B-k7 để kiểm tra dự phòng nếu B-k8 ký sai không?
5. Điều gì bảo đảm A và C không bị disable nhầm? Nếu B được enable lại, các key B-k7/B-k8 đã REVOKED có tự phục hồi không?

**Gợi ý:** (1) Trạng thái client DISABLED phủ lên mọi credential. (2) Snapshot ENABLED cũ có thể cho phép request trái chính sách. (3) Phải kiểm tra trạng thái đủ mới ở nguồn đáng tin cậy hoặc từ chối khi không thể chứng minh freshness. (4) Không: luôn tra cứu đúng key version được chỉ định và không fallback. (5) Thao tác khóa theo đúng client ID, ràng buộc credential với chủ sở hữu, cô lập dữ liệu tenant và kiểm thử từng client; enable client không được chuyển credential REVOKED thành ACTIVE.

## 13. Nguyên tắc triển khai

Trong xác thực HMAC nhiều client, **client disabled là một quyết định kiểm soát quyền tham gia hệ thống ở cấp định danh client**, độc lập với trạng thái và khóa bí mật của từng credential. Muốn bảo đảm client thực sự bị chặn, hệ thống phải ràng buộc đúng key với client, kiểm tra trạng thái client tại mọi đường xác thực với dữ liệu đủ mới, duy trì xác minh HMAC và chống replay đầy đủ, đồng thời quan sát việc áp dụng DISABLED trên mọi gateway.

Nhờ tách bạch trạng thái client, credential và authorization, một sự cố ở đối tác B có thể được cô lập mà không làm gián đoạn đối tác A/C; và việc cấp key mới hoặc bật lại client đều phải đi qua các điều kiện bảo mật riêng, có thể kiểm toán.
