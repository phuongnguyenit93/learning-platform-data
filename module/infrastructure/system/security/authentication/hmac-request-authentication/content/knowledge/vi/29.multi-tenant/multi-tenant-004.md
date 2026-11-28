# Canonical tenant context trong xác thực HMAC đa tenant

## 1. Vấn đề: chữ ký HMAC đúng nhưng ngữ cảnh tenant sai

Một API đa tenant phục vụ nhiều tổ chức trên cùng hạ tầng. Mỗi tổ chức (tenant) có dữ liệu, chính sách, quota và quyền truy cập riêng. Trong hệ thống **HMAC request authentication**, client ký một **canonical request** bằng shared secret; server xác minh chữ ký để xác định ai sở hữu credential. Nhưng **xác minh HMAC thành công chưa tự chứng minh request được phép truy cập tenant nào**.

Ví dụ, ứng dụng `billing-agent-a` chỉ được phép xử lý dữ liệu của tenant A. Request gửi:

~~~http
POST /v1/invoices HTTP/1.1
Host: api.example.test
X-Key-Id: key-billing-a-07
X-Tenant-Id: tenant-b
X-Timestamp: 2026-11-28T04:30:00Z
X-Nonce: c49d4b47-c12e-4d22-9fd2-e62a927bfcb3
X-Signature: <base64-hmac-sha256>

{"invoiceId":"inv-420","amount":180000}
~~~

Nếu server chỉ kiểm tra chữ ký với secret của `key-billing-a-07`, sau đó **tin ngay `X-Tenant-Id: tenant-b` để chọn database/schema**, một client thuộc A có thể yêu cầu xử lý dữ liệu B. Ngay cả khi `X-Tenant-Id` đã nằm trong chuỗi HMAC được ký, người sở hữu secret A vẫn có thể ký giá trị `tenant-b`; chữ ký chỉ bảo vệ dữ liệu khỏi bị **sửa đổi trên đường truyền**, không cấp quyền chọn tenant tùy ý.

**Canonical tenant context** là ngữ cảnh tenant được chuẩn hóa và xác định có cơ sở tin cậy, nhất quán qua các tầng xác thực, phân quyền và xử lý nghiệp vụ. Nó gồm ít nhất:

1. **Tenant được yêu cầu (requested tenant):** giá trị trong path/header/host theo hợp đồng API; lúc nhận request đây chỉ là một **claim**, chưa đáng tin.
2. **Tenant gắn với credential (credential owner tenant):** quan hệ được registry đáng tin cậy lưu cho key ID/client đã xác thực.
3. **Tenant được phép (authorized target tenant):** tenant mà principal đã xác thực thực sự có quyền thao tác; thường trùng owner tenant, hoặc khác khi có ủy quyền rõ ràng.
4. **Tenant hiệu lực (effective tenant):** giá trị chuẩn cuối cùng dùng để chọn dữ liệu, tạo audit, chọn policy và truyền qua các service.

Không được đồng nhất bốn khái niệm này trước khi kiểm tra. Điểm mấu chốt: **effective tenant phải được thiết lập từ bằng chứng xác thực cùng quyết định phân quyền**, rồi không bị ghi đè bởi input tùy ý của client ở các tầng sau.

## 2. Ngữ cảnh tenant có những thuộc tính nào?

Một cấu trúc nội bộ tham khảo:

| Trường | Ví dụ | Nguồn đáng tin cậy / cách dùng |
| --- | --- | --- |
| tenantId | `tenant-a` | Giá trị canonical đã xác thực và được cho phép |
| principalId | `billing-agent-a` | Danh tính liên kết với credential trong registry |
| credentialId | `key-billing-a-07` | Key ID từ request, sau khi tra cứu và xác minh HMAC |
| credentialOwnerTenant | `tenant-a` | Mapping lưu ở registry, không lấy từ header tự khai |
| requestedTenant | `tenant-a` | Input người gọi, sau khi kiểm tra định dạng và ràng buộc vào chữ ký |
| authorizationMode | `OWN_TENANT` | Chính sách được server đánh giá, hoặc `DELEGATED` có grant rõ ràng |
| requestId | `req-8f1b` | ID phục vụ truy vết, không phải dữ liệu quyết định tenant |
| canonicalContractVersion | `HMAC-REQUEST-V1` | Hợp đồng ký đã được server phê duyệt |

Ở thời điểm vừa đọc header, chỉ có **candidate context**. Sau khi kiểm tra chữ ký, trạng thái credential/client, thời hạn, timestamp/nonce và chính sách tenant, mới được tạo **authenticated/authorized tenant context**.

Không nên tin tenantId lấy từ:

- Header `X-Tenant-Id` chưa được xác thực.
- Query `?tenant=...` hoặc field `tenantId` trong JSON chỉ vì client gửi nó.
- HTTP Host hoặc subdomain do người gửi điều khiển, nếu chưa đối chiếu với mapping tenant tin cậy.
- Header `X-Forwarded-Host`, `X-Original-URI`, `X-Authenticated-Tenant` đến trực tiếp từ Internet.
- Bản ghi cache chỉ được khóa theo key ID khi key ID có thể trùng giữa các tenant hoặc cache thiếu điều kiện namespace.

**Một tenant ID chuẩn** nên là định danh nội bộ ổn định, bất biến về mặt tham chiếu và không chứa dữ liệu có ý nghĩa bảo mật tự thân. Ví dụ có thể dùng UUID chuẩn lowercase hoặc mã ASCII được cấp phát và kiểm soát chặt. Tên hiển thị của tổ chức, domain tùy chỉnh và tên schema không nên dùng thay tenant ID nếu có thể đổi hoặc có nhiều cách viết.

## 3. Xác định tenant trong các mô hình credential

### 3.1. Credential chỉ thuộc một tenant (mô hình mặc định dễ kiểm soát)

Registry gắn mỗi key ID với đúng một principal và tenant sở hữu:

| key_id | principal_id | owner_tenant | key_state | client_state |
| --- | --- | --- | --- | --- |
| key-billing-a-07 | billing-agent-a | tenant-a | ACTIVE | ENABLED |
| key-billing-b-03 | billing-agent-b | tenant-b | ACTIVE | ENABLED |

Với request khai `X-Key-Id: key-billing-a-07` và `X-Tenant-Id: tenant-b`, server tra credential theo key ID rồi thấy **requested tenant != owner tenant**. Request phải bị từ chối theo chính sách mô hình một tenant, dù chữ ký bằng key A là hoàn toàn chính xác.

Trong mô hình này, **tenantId hiệu lực = ownerTenant của credential** sau khi HMAC hợp lệ và các điều kiện xác thực thỏa mãn. Trường tenant do client gửi có thể là một thông tin ràng buộc bổ sung và phải khớp; nó **không được dùng để đổi chủ sở hữu**.

Nếu key ID chỉ duy nhất trong phạm vi tenant thay vì duy nhất toàn hệ thống, request có thể cần cặp (tenant ID được khai, key ID) để tìm candidate credential. Khi đó tenant ID được khai **chỉ là chỉ số tra cứu chưa đáng tin**. Phải xác minh HMAC bằng key tìm được, đối chiếu mapping owner tenant, đánh giá trạng thái và chính sách, rồi mới chấp nhận tenant đó. Không được vì đã lookup thành công mà coi tenant là xác thực.

### 3.2. Một client có quyền phục vụ nhiều tenant

Ví dụ một nền tảng thanh toán `payment-processor` có thể xử lý hóa đơn cho tenant A và B theo hợp đồng ủy quyền. Việc dùng một credential để phục vụ nhiều tenant chỉ an toàn khi:

- Principal từ credential được xác thực trước khi cho phép thao tác.
- Tenant đích được chỉ định rõ ràng và **nằm trong canonical request được ký**.
- Registry/policy lưu grant cụ thể: principal nào được thao tác ở tenant nào, với những action/resource nào và trong khoảng thời gian nào.
- Effective tenant chính là tenant đích **đã qua authorization**, không mặc định là owner tenant.
- Việc thu hồi grant hoặc disable tenant/client có hiệu lực trên mọi đường xử lý, bao gồm cache và các service phía sau.

Ví dụ, principal `payment-processor` sở hữu credential dưới tenant dịch vụ `tenant-processor`, nhưng có grant `CREATE_INVOICE` tại `tenant-a`. Request chọn `tenant-b` phải bị từ chối nếu không có grant phù hợp, kể cả khi HMAC hợp lệ.

Chính sách đa tenant này không thể thay bằng điều kiện đơn giản “principal có role ADMIN” mà không xét tenant đích. Quyền cần được kiểm tra trên bộ `(principalId, effectiveTenant, action, resource)`.

## 4. Thiết kế quy tắc canonical hóa tenant ID

Từ “canonical” ở đây có **hai lớp** cần phân biệt:

- **Canonical tenant identifier:** một cách biểu diễn thống nhất cho tenant, tránh cùng một tenant có nhiều chuỗi tương đương hoặc hai tenant khác nhau bị hợp nhất nhầm.
- **Canonical request:** chuỗi byte được tạo theo hợp đồng ký HMAC; mọi trường ảnh hưởng đến quyết định bảo mật (đặc biệt tenant đích) phải được ràng buộc đúng quy tắc.

### 4.1. Định dạng và chuẩn hóa

Giả sử hệ thống dùng mã tenant ASCII lowercase có dạng:

~~~text
tenant-a
tenant-b
tenant-internal-01
~~~

Hợp đồng có thể yêu cầu regex `[a-z0-9][a-z0-9-]{0,62}` và **từ chối** ký tự hoa, khoảng trắng đầu/cuối, ký tự Unicode giống nhau và giá trị rỗng. Chọn cách **từ chối biểu diễn không chuẩn** thường dễ kiểm toán hơn việc tự sửa chuỗi vào phút cuối rồi hy vọng client và server chuẩn hóa giống nhau.

| Dữ liệu nhận được | Kết quả theo hợp đồng ví dụ |
| --- | --- |
| `tenant-a` | Hợp lệ |
| `Tenant-A` | Từ chối; không tự hạ chữ hoa nếu giao thức chưa định nghĩa |
| ` tenant-a ` | Từ chối, tránh khác biệt giữa framework và signer |
| `tenant-a,tenant-b` | Từ chối, không chấp nhận nhiều tenant trong một header |
| Hai header `X-Tenant-Id` | Từ chối trước khi canonicalize |
| `tenant/a` hoặc `tenant%2Fa` | Từ chối theo định dạng tenant ID hiện hành |
| Tenant ID không có trong registry | Không cấp quyền; không tiết lộ sự tồn tại qua phản hồi công khai |

Nếu tenant ID là UUID, có thể bắt buộc dạng `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` lowercase chuẩn. Dù chọn kiểu nào, parser, signer, gateway và verifier phải thống nhất **chuỗi UTF-8 và thứ tự byte**. Không dựa vào việc một framework tự trim, tự đổi case hoặc ghép header trùng để tạo ra giá trị ký khác nhau.

### 4.2. Chọn một nguồn tenant chính thức

Một API có thể truyền tenant trong path, host hoặc header:

~~~http
GET /tenants/tenant-a/orders/123 HTTP/1.1
Host: api.example.test
X-Tenant-Id: tenant-a
~~~

Nếu hệ thống cho phép nhiều nguồn cùng tồn tại, phải có **quy tắc đối chiếu rõ ràng**. Ví dụ: path là định danh tenant đích của resource, header là giá trị bắt buộc để ký; chúng phải bằng nhau sau khi parse theo hợp đồng. Nếu không khớp, **từ chối**, không chọn theo thứ tự ưu tiên ngầm.

Đối với subdomain `tenant-a.api.example.test`, đừng mặc định host chính là tenant đáng tin. Kiểm tra host trên cấu hình gateway đáng tin, mapping domain → tenant trong registry, và ký hoặc ràng buộc thông tin host nếu nó ảnh hưởng đến quyết định tenant. Header forwarded phải được gateway **xóa rồi thiết lập lại** qua kết nối đã xác thực, không nhận trực tiếp giá trị người dùng khai báo.

## 5. Đưa tenant context vào canonical request HMAC

Một hợp đồng ký ví dụ `HMAC-REQUEST-V1` quy định:

1. HTTP method viết hoa đúng format.
2. Canonical path và query theo quy tắc URI đã thống nhất.
3. Tenant ID chính tắc.
4. Key ID của credential.
5. Timestamp chính tắc UTC.
6. Nonce có format cố định.
7. SHA-256 hex lowercase của **body bytes thực tế**.

Ví dụ request:

~~~http
POST /v1/invoices?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: key-billing-a-07
X-Tenant-Id: tenant-a
X-Timestamp: 2026-11-28T04:30:00Z
X-Nonce: c49d4b47-c12e-4d22-9fd2-e62a927bfcb3
X-Signature: <base64-hmac-sha256>

{"invoiceId":"inv-420","amount":180000}
~~~

Canonical request được định nghĩa bằng chuỗi UTF-8 gồm các dòng kết thúc bằng `LF` (không thêm dòng trống cuối nếu hợp đồng không yêu cầu):

~~~text
HMAC-REQUEST-V1
POST
/v1/invoices?currency=VND
tenant-a
key-billing-a-07
2026-11-28T04:30:00Z
c49d4b47-c12e-4d22-9fd2-e62a927bfcb3
<sha256-hex-cua-body-bytes>
~~~

Dòng digest chỉ là chỗ giữ chỗ để trình bày cấu trúc; phải thay bằng giá trị SHA-256 thực của body để tạo vector kiểm thử. Nếu path hoặc query cũng chứa tenant, nội dung đó vẫn phải được ký và kiểm tra nhất quán với `X-Tenant-Id`. Hợp đồng ký cần nói rõ URL trước/sau proxy rewrite, cách encode path/query, thứ tự tham số, ký tự Unicode, dấu gạch chéo và body rỗng.

Chữ ký được tính:

\[
\text{signature} =
\operatorname{Base64}\left(
  \operatorname{HMAC\mbox{-}SHA256}
    (K_{\text{key-billing-a-07}},\ \operatorname{UTF8}(\text{canonicalRequest}))
\right)
\]

**Kết quả khi kẻ tấn công sửa X-Tenant-Id:** nếu một người trung gian đổi `tenant-a` thành `tenant-b`, canonical request server dựng lại sẽ khác và HMAC không khớp. Nhưng nếu **client hợp lệ của A** tự chọn `tenant-b` và ký lại bằng K_A, chữ ký có thể vẫn đúng. Vì vậy server phải tiếp tục đối chiếu tenant mục tiêu với **registry và quyết định phân quyền**.

Đây là khác biệt căn bản giữa **bảo vệ tính toàn vẹn dữ liệu đã ký** và **quyền hoạt động trong tenant đích**.

### Vì sao key ID hoặc tenant ID cần được ràng buộc vào chữ ký?

Key ID là chỉ dẫn server chọn secret; tenant ID chọn ranh giới dữ liệu. Nếu một trong hai có thể bị thay đổi mà không làm thay đổi dữ liệu được ký, request có thể gặp lỗi định tuyến hoặc xác minh bằng context khác với context mà client tưởng mình đã ký.

Hợp đồng nên ký các định danh có ý nghĩa bảo mật và dùng các giá trị đã được parse nhất quán, không cho phép header trùng, prefix mơ hồ hoặc các alias tùy tiện. Việc ký không thay thế kiểm tra **mối quan hệ key → principal → tenant và policy**.

## 6. Luồng xây dựng tenant context tin cậy

~~~mermaid
sequenceDiagram
    participant C as HMAC Client
    participant G as Gateway / Verifier
    participant R as Credential + Tenant Registry
    participant N as Nonce Store
    participant A as Authorization
    participant S as Business Service
    C->>G: HTTP + keyId + requestedTenant + signature
    G->>G: Kiểm tra định dạng, duplicate headers
    G->>R: Tra keyId và client/tenant sở hữu
    R-->>G: Principal, ownerTenant, state, secretRef
    G->>G: Kiểm tra client/tenant/key còn enabled
    G->>G: Canonicalize các trường được ký
    G->>G: Xác minh HMAC bằng secret của đúng keyId
    G->>G: Kiểm tra timestamp server
    G->>N: Đăng ký nonce nguyên tử nếu chưa dùng
    N-->>G: Kết quả chống replay
    G->>A: Principal + requestedTenant + action + resource
    A-->>G: Cho phép / từ chối
    G->>G: Tạo effective TenantContext tin cậy
    G->>S: Truyền tenant context qua kênh xác thực
    S->>S: Truy vấn dữ liệu đúng tenant và kiểm tra quyền
    S-->>C: Kết quả nghiệp vụ
~~~

Các bước thực thi quan trọng:

**Bước 1 – Parse request như dữ liệu không đáng tin.** Kiểm tra độ dài/charset của key ID và tenant ID, thiếu header, duplicate header, timestamp/nonce và định dạng signature. Không gán `TenantContext` tin cậy vào thread-local ngay từ header.

**Bước 2 – Tra đúng credential và kiểm tra trạng thái.** Key ID hoặc cặp (tenant candidate, key ID) phải trỏ tới một bản ghi cụ thể. Xác minh credential thuộc principal/owner tenant phù hợp; client chưa bị DISABLED, tenant còn hoạt động, key version ACTIVE và trong khoảng `valid_from <= serverNow < expires_at`. Nếu dữ liệu trạng thái không thể đọc đủ tin cậy, từ chối theo chính sách fail closed.

**Bước 3 – Xác minh chữ ký với đúng secret.** Dựng canonical request theo **contract phiên bản được server cho phép**, với trường tenant yêu cầu đã được định nghĩa. Chỉ dùng secret của credential tra được, không thử các key khác cho đến khi có chữ ký khớp. So sánh byte chữ ký bằng cách không tiết lộ mức độ khớp qua timing.

**Bước 4 – Chống replay.** Kiểm tra timestamp nằm trong cửa sổ cho phép bằng thời gian server; ghi nonce bằng thao tác atomic insert-if-absent trên kho dùng chung giữa các verifier **sau khi HMAC hợp lệ**. Replay key có thể là `(credentialId, nonce)` hoặc `(credentialId, tenantId, nonce)` nếu hợp đồng giới hạn nonce theo tenant; lựa chọn phải nhất quán giữa các node và TTL bao phủ toàn bộ cửa sổ timestamp được chấp nhận. Dùng `(credentialId, nonce)` là cách đơn giản hơn để ngăn tái sử dụng nonce trên nhiều tenant.

**Bước 5 – Phân quyền theo tenant đích.** Trong chế độ `OWN_TENANT`, yêu cầu `requestedTenant == ownerTenant`. Trong chế độ `DELEGATED`, kiểm tra grant chính xác giữa principal, tenant đích, action và resource; kiểm tra cả trạng thái tenant đích. Không nhận một claim “isAdmin=true” trong request thay cho policy.

**Bước 6 – Tạo context bất biến và truyền xuống service.** Sau khi có kết quả xác thực và phân quyền mới tạo `AuthenticatedTenantContext`. Service nghiệp vụ phải dùng `context.effectiveTenantId` để truy vấn dữ liệu và audit, không đọc lại header/query tenant chưa tin cậy.

Nếu hệ thống xác minh chữ ký trước khi kiểm tra trạng thái hoặc chính sách tenant, thứ tự kỹ thuật có thể thay đổi. **Điều kiện bắt buộc** là không có đường chấp nhận request hoặc thực thi nghiệp vụ trước khi tất cả kiểm tra liên quan hoàn tất.

## 7. Ví dụ Java 17: phân giải tenant chỉ sau khi xác thực

Ví dụ sau minh họa policy xây dựng **tenant context tin cậy** từ thông tin đã xác minh HMAC và principal trong registry. Phần tra cứu, lấy secret, xác minh chữ ký, kiểm tra timestamp/nonce được mô tả qua interface để không làm lẫn trách nhiệm.

~~~java
import java.time.Instant;
import java.util.Objects;

public final class CanonicalTenantContextResolver {
    enum ClientState { ENABLED, DISABLED }
    enum CredentialState { ACTIVE, SUSPENDED, REVOKED, RETIRED }

    record Credential(
        String keyId,
        String principalId,
        String ownerTenantId,
        String secretRef,
        ClientState clientState,
        CredentialState credentialState,
        Instant validFrom,
        Instant expiresAt
    ) {}

    record RequestClaim(
        String keyId,
        String requestedTenantId,
        String canonicalRequest,
        String signatureBase64,
        String timestamp,
        String nonce
    ) {}

    // Chỉ phát hành sau khi xác minh; không expose public constructor
    // qua HTTP deserialization hoặc bind trực tiếp từ header.
    record AuthenticatedTenantContext(
        String principalId,
        String credentialId,
        String ownerTenantId,
        String effectiveTenantId,
        String authorizationMode
    ) {}

    interface CredentialRegistry {
        Credential findByKeyId(String keyId);
        boolean isTenantEnabled(String tenantId);
    }

    interface HmacVerifier {
        // Phải dùng đúng secretRef và canonical bytes theo hợp đồng.
        boolean validSignature(
            String secretRef,
            String canonicalRequest,
            String signatureBase64
        );
    }

    interface ReplayGuard {
        // Kiểm tra timestamp server và atomically nhận nonce mới,
        // trả false nếu timestamp sai hoặc nonce đã xuất hiện.
        boolean accept(String credentialId, String timestamp, String nonce);
    }

    interface Authorizer {
        boolean mayAct(
            String principalId,
            String targetTenantId,
            String action,
            String resourceId
        );
    }

    static AuthenticatedTenantContext resolve(
        RequestClaim request,
        String action,
        String resourceId,
        Instant serverNow,
        CredentialRegistry registry,
        HmacVerifier verifier,
        ReplayGuard replayGuard,
        Authorizer authorizer
    ) {
        String tenant = requireCanonicalTenant(request.requestedTenantId());
        Credential key = registry.findByKeyId(request.keyId());

        if (key == null
                || !Objects.equals(key.keyId(), request.keyId())
                || key.clientState() != ClientState.ENABLED
                || key.credentialState() != CredentialState.ACTIVE
                || serverNow.isBefore(key.validFrom())
                || !serverNow.isBefore(key.expiresAt())
                || !registry.isTenantEnabled(key.ownerTenantId())
                || !registry.isTenantEnabled(tenant)) {
            throw new SecurityException("authentication_failed");
        }

        // canonicalRequest là dữ liệu do VERIFIER dựng từ request gốc,
        // không nhận một chuỗi canonical tự khai từ HTTP client.
        if (!verifier.validSignature(
                key.secretRef(), request.canonicalRequest(),
                request.signatureBase64())) {
            throw new SecurityException("authentication_failed");
        }

        if (!replayGuard.accept(
                key.keyId(), request.timestamp(), request.nonce())) {
            throw new SecurityException("authentication_failed");
        }

        // Chế độ mặc định: một credential chỉ phục vụ owner tenant.
        // Nếu hỗ trợ delegation, authorizer cần kiểm tra grant tường minh.
        boolean ownTenant = tenant.equals(key.ownerTenantId());
        if (!ownTenant
                || !authorizer.mayAct(
                    key.principalId(), tenant, action, resourceId)) {
            throw new SecurityException("access_denied");
        }

        return new AuthenticatedTenantContext(
            key.principalId(),
            key.keyId(),
            key.ownerTenantId(),
            tenant,
            "OWN_TENANT"
        );
    }

    private static String requireCanonicalTenant(String value) {
        if (value == null
                || !value.matches("[a-z0-9][a-z0-9-]{0,62}")) {
            throw new SecurityException("invalid_request");
        }
        return value;
    }
}
~~~

**Phạm vi của ví dụ:** `RequestClaim.canonicalRequest` là một giá trị **do lớp verifier tạo từ HTTP request gốc**, theo hợp đồng ký và bao gồm đúng `keyId`, `requestedTenantId`, timestamp, nonce, method, URI và body digest. Constructor của Java record vẫn public trong phạm vi hiển thị tương ứng; ứng dụng cần bảo đảm class này chỉ được tạo bởi một thành phần kiểm soát nội bộ, không bind trực tiếp từ dữ liệu client. Cần kiểm tra sự nhất quán giữa các trường `RequestClaim` và các thành phần trong canonical request; production nên có một kiểu dữ liệu nội bộ không thể bị tách rời hoặc giả mạo bởi caller.

`ReplayGuard.accept` là interface minh họa cho hai bước kiểm tra timestamp và đăng ký nonce bằng thao tác atomic. TTL cần được tính theo cửa sổ chấp nhận timestamp, bảo đảm không xóa nonce khi request cũ vẫn còn có thể được nhận. Nếu hệ thống chọn delegated tenant, phải thay đoạn `!ownTenant` bằng kiểm tra grant thực sự; không được xóa điều kiện rồi chấp nhận mọi tenant.

**Cảnh báo quan trọng về thứ tự xử lý:** Đừng tạo context kết luận `tenant-a` chỉ dựa vào việc `key.ownerTenantId()` là `tenant-a` mà chưa xác minh HMAC và chống replay. Thông tin owner tenant là metadata đáng tin, nhưng **request hiện tại** vẫn chưa được xác thực.

## 8. Registry và quan hệ tenant – client – credential

Một sơ đồ tối giản có thể tách tenant, principal/client và credential:

~~~sql
CREATE TABLE tenants (
    tenant_id VARCHAR(63) PRIMARY KEY,
    state VARCHAR(16) NOT NULL
        CHECK (state IN ('ENABLED', 'DISABLED'))
);

CREATE TABLE hmac_clients (
    client_id VARCHAR(128) PRIMARY KEY,
    owner_tenant_id VARCHAR(63) NOT NULL
        REFERENCES tenants(tenant_id),
    state VARCHAR(16) NOT NULL
        CHECK (state IN ('ENABLED', 'DISABLED'))
);

CREATE TABLE hmac_credentials (
    key_id VARCHAR(128) PRIMARY KEY,
    client_id VARCHAR(128) NOT NULL
        REFERENCES hmac_clients(client_id),
    secret_ref VARCHAR(256) NOT NULL,
    state VARCHAR(16) NOT NULL
        CHECK (state IN
            ('PENDING', 'ACTIVE', 'SUSPENDED', 'REVOKED', 'RETIRED')),
    valid_from TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    key_version INTEGER NOT NULL CHECK (key_version > 0),
    UNIQUE (client_id, key_version),
    CHECK (expires_at > valid_from)
);
~~~

Từ bảng trên, quan hệ tin cậy là `key_id → client_id → owner_tenant_id`. Request khai tenant nào phải được đối chiếu với quan hệ đó theo mô hình cho phép. **Không** thiết kế dữ liệu để user tự chọn một `tenant_id` không thuộc client chỉ bằng cách truyền thêm query parameter.

Với ủy quyền liên tenant, nên có bảng grant riêng, chẳng hạn `client_tenant_grants(client_id, target_tenant_id, action, valid_from, expires_at, state)`, với khóa ngoại, uniqueness, phiên bản chính sách và lịch sử kiểm toán. Không tạo grant mặc định theo wildcard `*` nếu không có yêu cầu nghiệp vụ và cơ chế phê duyệt rõ ràng.

Trong hệ thống database dùng chung, mọi truy vấn dữ liệu tenant phải thêm điều kiện `tenant_id = :effectiveTenantId` từ context tin cậy; nếu dùng schema/database riêng, resolver phải chọn schema/database dựa trên mapping tenant đã được quản trị, không ghép tên schema tùy ý từ header.

Ví dụ repository:

~~~sql
SELECT invoice_id, amount, status
FROM invoices
WHERE tenant_id = :effective_tenant_id
  AND invoice_id = :invoice_id;
~~~

Tham số `:effective_tenant_id` phải lấy từ authenticated tenant context **sau** khi xác thực và phân quyền, không lấy từ body hoặc query string. Với nghiệp vụ cập nhật, `UPDATE/DELETE` cũng cần điều kiện tenant trong `WHERE`; dùng transaction và kiểm soát quyền ở cấp database (ví dụ row-level security khi phù hợp) để tạo lớp bảo vệ bổ sung.

## 9. Bảo toàn ngữ cảnh tenant qua gateway và các service

Trong kiến trúc microservice, HMAC có thể được xác minh tại gateway rồi kết quả được truyền tới service xử lý. Đường truyền tin cậy này có rủi ro **confused deputy**: service nhận nhầm tenant do header bị giả mạo hoặc context bị mất.

Một sơ đồ luồng tin cậy:

~~~mermaid
flowchart LR
    C["Client: claim tenant-a"] --> G["Gateway: verify HMAC + policy"]
    G --> T["Authenticated tenant context"]
    T --> S1["Orders service"]
    S1 --> S2["Billing service"]
    S1 --> DB[("Tenant-scoped data")]
    S2 --> DB
    U["Header X-Authenticated-Tenant do client tự gửi"] -.-> G
~~~

Biện pháp vận hành:

- Gateway phải **loại bỏ mọi header nội bộ giả mạo** từ kết nối bên ngoài và chỉ tạo header/context do mình kiểm soát.
- Service chỉ tin context từ gateway qua kênh đã xác thực và được ủy quyền, ví dụ mTLS hoặc token nội bộ có chữ ký, thời hạn, audience và tenant claim rõ ràng. Header plaintext tự gửi trên mạng nội bộ chưa xác thực là chưa đủ.
- Không cho truy cập trực tiếp bypass gateway vào endpoint yêu cầu tenant context, trừ khi service đó có lớp xác thực/ủy quyền tương đương.
- Truyền context qua tác vụ bất đồng bộ bằng envelope có nguồn gốc đáng tin và tenant ID đã được kiểm tra; consumer vẫn xác minh quyền/tenant phù hợp công việc của mình.
- Khi dùng thread-local/MDC/reactive context, phải dọn context sau request để tránh một tenant bị “rò” sang request khác do reuse thread hoặc callback.
- Nếu service đích có thông tin tenant từ path/body, phải **đối chiếu** với effective tenant đã xác thực, không ưu tiên giá trị người gọi chỉ định.

Ví dụ lỗi nguy hiểm: gateway xác thực tenant A, nhưng downstream đọc `X-Tenant-Id: tenant-b` (header client gửi) và dùng B để truy vấn. Chữ ký HMAC đúng ở gateway **không bảo vệ bước nhầm context tại downstream**. Hợp đồng giữa gateway và service phải yêu cầu dùng một context duy nhất, có nguồn gốc xác thực, cho toàn bộ đường xử lý.

### Ký dữ liệu sau proxy rewrite

Nếu client ký `/tenants/tenant-a/orders` nhưng gateway rewrite thành `/orders`, service xác minh HMAC bằng target đã rewrite có thể tạo chữ ký khác. Hãy quyết định **điểm xác minh** và **canonical URI mà hợp đồng ký định nghĩa**; nếu bắt buộc xác minh sau proxy, chỉ dùng giá trị original URI được truyền qua kênh đáng tin từ proxy và không nhận header original URI do client tự khai. Kiểm thử end-to-end với method, path, query, header và body thực tế.

## 10. Cache, key rotation và khả năng thu hồi theo tenant

Trong hệ thống nhiều tenant, cache là nguồn lỗi tách biệt cần kiểm soát:

| Cache | Khóa/namespace khuyến nghị | Rủi ro |
| --- | --- | --- |
| Credential cache | key ID toàn cục; hoặc tenant + key ID khi key chỉ unique theo tenant | Trả nhầm secret/principal khác tenant |
| Tenant-state cache | tenant ID và phiên bản trạng thái | Dùng dữ liệu tenant đã DISABLED |
| Authorization cache | principal + target tenant + action + resource + policy revision | Áp quyền của A cho B |
| Response/business cache | tenant ID + resource key + permission context thích hợp | Rò dữ liệu giữa tenant |
| Replay nonce | credential ID + nonce (hoặc tenant-scoped theo hợp đồng) | Cho request bị phát lại được chấp nhận tại node khác |

Không cache `authorized = true` chỉ theo `principalId`: cùng principal có thể được ủy quyền ở A nhưng không có quyền ở B. Tương tự, không cache một `TenantContext` theo connection/thread rồi tái dùng cho request khác.

**Key rotation:** nhiều key version của một principal có thể đồng thời ACTIVE. Key mới phải gắn đúng owner tenant và dùng secret mới độc lập. Việc cấp key mới không làm thay đổi tenant context của client hoặc tạo grant liên tenant. Nếu tenant đã DISABLED, key mới dù HMAC đúng vẫn bị từ chối.

**Thu hồi:** khi client, tenant, credential hoặc delegated grant bị thu hồi, mọi verifier phải biết trạng thái mới với độ trễ phù hợp cam kết bảo mật. Cần outbox/event, revision chống event đến sai thứ tự, giám sát lag và điểm xác thực fail closed khi không chứng minh được freshness. Một cache có TTL 60 giây có thể vẫn chấp nhận request trong 60 giây sau thu hồi nếu chỉ dựa vào TTL; tuyệt đối không gọi đó là “thu hồi tức thời”.

## 11. Tình huống tấn công và lỗi cấu hình thường gặp

### 11.1. Thay tenant sau khi ký

Client ký cho `tenant-a`; người trung gian sửa `X-Tenant-Id` thành `tenant-b`. Nếu tenant ID nằm trong canonical request và được chuẩn hóa nhất quán, HMAC phải sai. Nếu tenant ID **không** được ký nhưng được dùng chọn dữ liệu, đây là lỗi thiết kế nghiêm trọng: giá trị ảnh hưởng đến ranh giới dữ liệu có thể thay đổi mà không bị phát hiện.

### 11.2. Client A cố tình ký request tới tenant B

Client A sở hữu K_A và tự ký `tenant-b`. HMAC vẫn có thể đúng. Registry và authorization phải từ chối vì A không có quyền ở B. **Ký tenant ID không thay thế quyền tenant**.

### 11.3. Trùng key ID ở nhiều tenant

Tenant A và B đều có `key-1`, server chỉ cache theo chuỗi `key-1`. Kết quả có thể lấy secret/owner sai. Hệ thống nên cấp key ID duy nhất toàn cục hoặc khóa cache/lookup theo cặp tenant + key ID, rồi đối chiếu owner sau xác minh.

### 11.4. Hai nguồn tenant xung đột

Path chứa `/tenants/tenant-a/` nhưng header `X-Tenant-Id: tenant-b`. Nếu API yêu cầu cả hai, phải từ chối. Đừng chọn path ở gateway nhưng chọn header ở service vì dễ dẫn tới định tuyến một tenant và truy vấn dữ liệu tenant khác.

### 11.5. Gateway tin header nội bộ do client gửi

Kẻ tấn công gửi `X-Authenticated-Tenant: tenant-b` cùng request HMAC cho A. Nếu gateway chuyển tiếp header này mà không xóa, service phía sau có thể bỏ qua context đã xác minh. Cần xóa header ngoài và tạo lại thông tin nội bộ qua trust boundary được bảo vệ.

### 11.6. Replay store bị phân vùng theo tenant sai

Một request hợp lệ vào tenant A có nonce N, kẻ tấn công phát lại tới vùng khác dùng cache nonce riêng. Nếu mỗi vùng chấp nhận nonce cục bộ, request có thể được xử lý hai lần. Kho nonce cần ghi nguyên tử và có tính nhất quán đủ mạnh trên các điểm xác minh chấp nhận cùng credential; phạm vi khóa nonce phải theo hợp đồng. Chống replay vẫn bắt buộc kể cả tenant đã nằm trong HMAC.

### 11.7. Phân quyền dựa vào owner tenant thay vì target tenant

Một nền tảng được phép xử lý dữ liệu tenant A qua grant, nhưng service phân quyền bằng owner tenant của nền tảng và không kiểm tra target tenant A. Kết quả có thể tạo quyền quá rộng. Với delegation, authorization luôn phải xét **target tenant, action và resource cụ thể**, cùng hạn sử dụng grant.

## 12. Phản hồi lỗi, audit và giám sát

Server nên trả phản hồi xác thực thất bại nhất quán cho các trường hợp key ID không tồn tại, credential bị thu hồi hoặc client/tenant bị vô hiệu hóa, tránh cung cấp thông tin giúp dò tenant hoặc key. 401 thường dùng cho thiếu/sai xác thực theo hợp đồng API; 403 dành cho trường hợp đã xác thực nhưng không đủ quyền tại tenant/tài nguyên đích. Không trả thông báo “tenant B tồn tại nhưng client A không có quyền” cho bên chưa được xác thực.

Log nội bộ và audit nên tách mã lỗi:

| Mã nội bộ | Diễn giải |
| --- | --- |
| INVALID_TENANT_FORMAT | Tenant ID không đúng dạng canonical |
| TENANT_CLAIM_MISMATCH | Tenant từ path/header hoặc credential không khớp |
| CREDENTIAL_NOT_ACTIVE | Key chưa kích hoạt, hết hạn hoặc bị thu hồi |
| CLIENT_OR_TENANT_DISABLED | Client/tenant không được phép tiếp tục |
| SIGNATURE_MISMATCH | HMAC không hợp lệ theo canonical request |
| REPLAY_DETECTED | Timestamp/nonce không hợp lệ hoặc đã sử dụng |
| TENANT_ACCESS_DENIED | Principal đã xác thực nhưng thiếu grant/quyền tại tenant đích |
| CONTEXT_PROPAGATION_FAILURE | Không nhận được context tin cậy ở downstream |

Một audit event hữu ích gồm request/correlation ID, principal sau xác thực, key ID được bảo vệ thích hợp, owner tenant, requested tenant, effective tenant (nếu đã được chấp nhận), action/resource, policy revision, verifier ID và mã kết quả. **Không log shared secret, HMAC signature, body nhạy cảm hoặc toàn bộ canonical request**. Chi tiết tenant/client có thể nhạy cảm, cần phân quyền đọc log; tránh dùng tenant ID cardinality cao làm label Prometheus đại trà.

Các chỉ số nên theo dõi: số lần mismatch tenant, lỗi HMAC theo gateway/route, lỗi authorization liên tenant, số request bị từ chối do tenant/client disabled, độ trễ cập nhật trạng thái, dấu hiệu bypass gateway và truy vấn dữ liệu thiếu tenant filter. Số liệu hỗ trợ điều tra nhưng không thay thế kiểm thử phân lập tenant thực tế.

## 13. Bộ kiểm thử cần thực hiện

| Trường hợp | Kỳ vọng |
| --- | --- |
| Key A, requested tenant A, HMAC đúng, trạng thái hợp lệ | Qua xác thực; tiếp tục authorization |
| Key A, requested tenant B, HMAC đúng, không có grant | Từ chối, không truy vấn dữ liệu B |
| Key A, requested tenant B, có grant đúng action/resource | Có thể tạo context B nếu qua tất cả kiểm tra |
| Key A, tenant trong header bị sửa sau khi ký | HMAC không khớp |
| Path tenant A nhưng header tenant B | Từ chối mismatch nguồn |
| Thiếu header tenant bắt buộc | Từ chối |
| Hai header X-Tenant-Id | Từ chối, không chọn một giá trị tùy ý |
| Tenant ID viết hoa hoặc có khoảng trắng ngoài hợp đồng | Từ chối định dạng |
| Tenant hợp lệ nhưng không có trong registry | Không cấp quyền; phản hồi công khai không tiết lộ chi tiết |
| Tenant bị DISABLED, key vẫn ACTIVE | Từ chối |
| Client bị DISABLED, tenant còn ENABLED | Từ chối |
| Credential REVOKED, client/tenant ENABLED | Từ chối |
| Key ID lặp ở hai tenant khi lookup/cache sai namespace | Phát hiện và từ chối; không lẫn secret/owner |
| Key rotation A có K3 và K4 cùng ACTIVE | Cả hai vẫn chỉ có quyền tenant A theo chính sách |
| Tạo key mới cho tenant A nhưng ký request tenant B | Không mặc nhiên cấp quyền tới B |
| HMAC hợp lệ nhưng nonce trùng ở gateway khác | Từ chối replay |
| HMAC hợp lệ nhưng timestamp ngoài cửa sổ | Từ chối |
| HMAC hợp lệ nhưng principal không được xem resource tại tenant | Từ chối authorization |
| Gateway rewrite path/query gây sai canonical bytes | Phát hiện HMAC mismatch, không đổi tenant ngầm |
| Client gửi X-Authenticated-Tenant giả | Gateway xóa và service không tin header ngoài |
| Service có thread pool, request A xử lý trước B | Context A không rò sang B |
| Tác vụ async mang context A tới worker của B | Worker kiểm tra nguồn gốc context và tenant đúng |
| Tenant A vừa bị DISABLED nhưng gateway cache ENABLED cũ | Tuân thủ freshness/fail closed theo cam kết |
| Event trạng thái version cũ đến sau version mới | Cache không quay về state cũ |
| Registry hoặc nonce store không khả dụng | Không bỏ qua bước an toàn; fail closed |

### Bài tập phân tích

Một nền tảng SaaS có tenant `tenant-a` và `tenant-b`. Client `collector-a` sở hữu key `key-a-12`, chỉ có quyền trong A. API gateway xác minh chữ ký HMAC thành công cho request `POST /tenants/tenant-a/reports`, nhưng header `X-Tenant-Id` lại là `tenant-b`. Gateway đang chuyển tiếp `X-Tenant-Id` nguyên vẹn tới report service, nơi lựa chọn database bằng header này.

Hãy tự trả lời:

1. Vì sao HMAC thành công chưa chứng minh `tenant-b` là tenant được phép?
2. Gateway phải đối chiếu những định danh tenant nào trước khi tạo context?
3. Report service phải nhận tenant ID từ nguồn nào? Nếu thiếu context đáng tin thì xử lý ra sao?
4. Nếu `collector-a` được ủy quyền thao tác B trong tương lai, những điều kiện nào phải có trước khi cấp quyền?
5. Trong key rotation, cấp `key-a-13` có làm thay đổi tenant được phép của client không?

**Định hướng:** (1) HMAC chứng minh sở hữu secret, không cấp quyền vượt tenant. (2) Path/header/credential owner và grant theo chính sách, từ chối nếu các nguồn không khớp theo hợp đồng. (3) Từ `AuthenticatedTenantContext` được gateway hoặc verifier đáng tin thiết lập; thiếu thì fail closed. (4) Grant cụ thể cho principal–tenant–action–resource, request ký tenant B, kiểm tra trạng thái và chống replay. (5) Không; key mới vẫn phải gắn chủ sở hữu và quyền theo policy.

## 14. Checklist triển khai canonical tenant context

Trước khi vận hành production, kiểm tra rằng:

- Định dạng tenant ID và nguồn tenant đích duy nhất được định nghĩa; mọi giá trị không chuẩn hoặc xung đột bị từ chối.
- Tenant đích và key ID được ràng buộc vào canonical request theo hợp đồng ký nhất quán ở client, proxy và server.
- Mỗi key tra về đúng principal/owner tenant; không tái sử dụng key ID hoặc cache thiếu namespace.
- Client/tenant/credential có trạng thái hợp lệ; thay key version không bỏ qua trạng thái DISABLED hay REVOKED.
- HMAC được xác minh với đúng secret; timestamp/nonce chống replay hoạt động nguyên tử trên mọi verifier.
- Authorization dùng principal, **effective tenant**, action và resource; delegated grant được quản lý riêng, có hạn và có thể thu hồi.
- Downstream chỉ nhận tenant context qua kênh đã xác thực; không đọc lại header tenant tự khai và không để context rò giữa request.
- Truy vấn/ghi dữ liệu dùng tenant đã xác thực; gateway và storage cùng bảo vệ ranh giới tenant.
- Cache trạng thái, grant và key rotation có chính sách freshness, revision, invalidation và fail closed.
- Audit và kiểm thử end-to-end bao gồm mismatched tenant, proxy rewrite, nhiều gateway, dữ liệu chéo tenant và request đang xử lý khi bị thu hồi.

**Canonical tenant context** chỉ thực sự đáng tin khi giá trị tenant dùng để thực thi nghiệp vụ được liên kết với **credential đã xác minh**, **chính sách phân quyền** và **canonical request có ràng buộc tenant**. HMAC bảo vệ tính toàn vẹn request; việc xác định tenant hiệu lực và cô lập dữ liệu đòi hỏi kiểm tra chủ sở hữu, grant và propagation nhất quán từ gateway tới từng service.
