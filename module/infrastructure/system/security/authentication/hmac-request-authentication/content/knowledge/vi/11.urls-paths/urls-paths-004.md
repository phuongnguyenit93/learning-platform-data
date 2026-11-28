# Path parameter trong xác thực HMAC cho HTTP request

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **path parameter** (tham số đường dẫn) với route template, query parameter, HTTP method và HTTP body.
- Giải thích tại sao giá trị path parameter **phải được ràng buộc với dữ liệu đã ký**, nếu nó quyết định tài nguyên mà API đọc hoặc cập nhật.
- Xác định chính xác **raw path/request-target** sẽ được client và verifier sử dụng trong `canonical request`.
- Nhận diện lỗi do percent-encoding, encoded slash, dấu chấm, slash kép, Unicode, route normalization và reverse proxy/API gateway rewrite.
- Thiết kế hợp đồng ký HMAC-SHA256 cho một endpoint có path parameter, kiểm tra chữ ký bằng Java/JCA và chuyển danh tính đã xác thực cho backend.
- Phân biệt **HMAC authentication** với **authorization theo tài nguyên trong path**, đồng thời kiểm soát timestamp/nonce chống replay và vòng đời secret/key rotation.
- Lập bộ kiểm thử end-to-end phát hiện khác biệt giữa đường dẫn **được ký**, đường dẫn **được xác minh** và tài nguyên **thực sự được xử lý**.

> **Phạm vi:** Bài thuộc chương **URL và path** của module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Module thiết kế xác thực HTTP bằng shared secret, canonical request gồm method, URI, header hoặc body, kết hợp xác minh chữ ký, replay protection, key rotation và kiểm thử gateway. Chủ đề trực tiếp ở đây là **path parameter**; những phần còn lại được sử dụng để làm rõ cách bảo vệ nó. Hợp đồng ký trong ví dụ là quy ước cho bài học, không phải chuẩn tương thích với mọi API.

## 1. Path parameter là gì?

**Path parameter** là một giá trị động nằm **bên trong đường dẫn URL**, thường dùng để xác định tài nguyên cụ thể. Khi thiết kế route, lập trình viên viết một **route template**; khi client gửi request, client dùng **đường dẫn thật đã thay các placeholder**.

Ví dụ:

```text
Route template: PUT /v1/warehouses/{warehouseId}/settings
Request thật:   PUT /v1/warehouses/WH-17/settings
Path parameter: warehouseId = WH-17
```

Trong template, `{warehouseId}` biểu thị một vị trí động. Nó **không phải** chuỗi literal mà client gửi. Nếu client cập nhật kho khác, request-target thay đổi:

```text
PUT /v1/warehouses/WH-17/settings
PUT /v1/warehouses/WH-99/settings
```

Hai request hướng đến **hai tài nguyên khác nhau**. Nếu server chỉ ký body, chữ ký có thể không phân biệt kho `WH-17` với `WH-99`. Trong hệ thống HMAC, đây là ranh giới bảo mật quan trọng.

### Path parameter khác query parameter thế nào?

```http
PUT /v1/warehouses/WH-17/settings?mode=replace HTTP/1.1
Host: api.example.test
```

| Thành phần | Giá trị | Vai trò |
|---|---|---|
| HTTP method | `PUT` | Hành động muốn thực hiện |
| Path | `/v1/warehouses/WH-17/settings` | Định vị endpoint và tài nguyên |
| Path parameter | `warehouseId = WH-17` | Định danh tài nguyên lấy từ một segment của path |
| Query string | `mode=replace` | Tham số sau `?`, không thuộc path segment |
| Route template | `/v1/warehouses/{warehouseId}/settings` | Quy tắc router dùng để ghép route; **không phải request-target gửi trên mạng** |
| Body | Ví dụ JSON settings | Representation hoặc dữ liệu nghiệp vụ gửi kèm |

**Không có quy tắc rằng chỉ path parameter mới đáng ký còn query thì không.** Nếu query ảnh hưởng tới hành động, tài nguyên, quyền, bộ lọc hoặc kết quả nghiệp vụ, query cũng cần được ràng buộc bởi HMAC hoặc cơ chế bảo vệ tương đương.

## 2. Vì sao path parameter là dữ liệu nhạy cảm về mặt an ninh?

Xét API:

```http
PUT /v1/warehouses/WH-17/settings HTTP/1.1
Content-Type: application/json

{"allowBackorder":false}
```

Client được phép sửa kho `WH-17`. Giả sử client chỉ tính:

```text
signature = HMAC-SHA256(K, SHA256(rawBody))
```

Một bên có khả năng sửa request mà **không biết `K`** vẫn có thể giữ nguyên body và signature nhưng đổi path:

```text
/v1/warehouses/WH-17/settings
        thành
/v1/warehouses/WH-99/settings
```

Vì path không được ký nên HMAC của body vẫn không đổi. Nếu backend lại tin rằng “chữ ký đúng nên được sửa kho đích”, kẻ tấn công có thể tác động tài nguyên ngoài dự kiến.

**Cách khắc phục:** ký cả HTTP method, **request-target chứa path parameter thực tế**, các header/bộ phận nghiệp vụ có ý nghĩa và digest của body:

```text
signature = HMAC-SHA256(K, canonical(
    method, actualRequestTarget, signedHeaders, bodyDigest, timestamp, nonce
))
```

Khi `WH-17` bị thay thành `WH-99`, `actualRequestTarget` thay đổi và chữ ký cũ không còn khớp. Tuy nhiên, điều này **chỉ bảo vệ tính toàn vẹn của path đã ký**. Nếu chính client sở hữu secret của mình và cố ý ký một request nhắm kho khác, HMAC vẫn có thể hợp lệ; backend **phải kiểm tra quyền trên kho được chỉ định**.

### Hai bất biến cần tách bạch

1. **Bất biến mật mã:** path chứa `warehouseId` mà verifier đưa vào HMAC phải đại diện cho đúng target client đã ký; một thay đổi trái hợp đồng làm chữ ký không hợp lệ.
2. **Bất biến phân quyền:** principal đã xác thực phải có quyền thực hiện method đó đối với **tài nguyên được xác định từ path thực thi**.

Một hệ thống có thể thỏa bất biến (1) nhưng vẫn thiếu (2). Đó là lý do authentication và authorization phải là hai bước riêng.

## 3. Route template, raw path, decoded path và request-target

Trong thực tế, một request có nhiều **biểu diễn đường dẫn**. Khi canonical hóa, trộn lẫn chúng là nguyên nhân phổ biến của mismatch hoặc bypass.

| Biểu diễn | Ví dụ | Lưu ý |
|---|---|---|
| **Route template** | `/v1/warehouses/{warehouseId}/settings` | Mẫu trong mã nguồn router; không chứa giá trị kho cụ thể |
| **Raw path / encoded path** | `/v1/warehouses/WH-17/settings` | Biểu diễn path trước khi URL-decoding theo hợp đồng |
| **Raw path có percent-encoding** | `/v1/warehouses/%57H-17/settings` | `%57` có thể giải mã thành chữ `W`, nhưng **raw bytes khác** |
| **Decoded path** | `/v1/warehouses/WH-17/settings` | Có thể đã bị thư viện/proxy giải mã; không tự thay thế raw path |
| **Request-target dạng origin-form** | `/v1/warehouses/WH-17/settings?mode=replace` | Bao gồm **path + query**; không gồm scheme/host/fragment |
| **URI/URL đầy đủ** | `https://api.example.test/v1/warehouses/WH-17/settings` | Có scheme và authority; khác origin-form của request-target |

HTTP/1.1 có nhiều dạng request-target tùy ngữ cảnh (như origin-form và absolute-form), còn HTTP/2 sử dụng các pseudo-header tương ứng, trong đó có `:path`. Hợp đồng ký phải quy định rõ cách chuyển **dữ liệu thực nhận ở từng phiên bản giao thức** sang biểu diễn ký chung. Không giả định `request.getPathInfo()`, `request.getRequestURI()`, `URI.getPath()` và `URI.getRawPath()` luôn tương đương qua mọi container và proxy.

### Ký template hay ký path thực tế?

Không ký:

```text
PUT
/v1/warehouses/{warehouseId}/settings
```

Vì mọi kho cùng dùng một template, phần path được ký **không ràng buộc giá trị `warehouseId`**.

Hãy ký biểu diễn **đường dẫn thực tế của request** đã thống nhất:

```text
PUT
/v1/warehouses/WH-17/settings
```

Nếu contract chuẩn hóa path parameter thành một giá trị đã giải mã thay vì raw path, cần quy định byte-level normalization **chính xác**, bảo đảm router và handler cùng diễn giải. Với một endpoint bảo mật cao, chọn ID chỉ gồm ký tự URL-safe và **không cho phép encoding nhập nhằng** thường đơn giản hơn.

## 4. Percent-encoding và những biến thể dễ gây lỗi

Percent-encoding biểu diễn byte trong URI bằng `%HH`, với `HH` là hai chữ số hệ 16. Trong đường dẫn, khác biệt giữa **các byte được ký** và **route được thực thi** có thể dẫn đến lỗi bảo mật.

| Biến thể người gọi gửi | Nguy cơ nếu các tầng diễn giải khác nhau | Lựa chọn bảo vệ |
|---|---|---|
| `WH-17` so với `%57H-17` | Cùng ID sau decode nhưng raw path khác; ký một kiểu, route kiểu khác | Xác định ký raw path hoặc quy tắc chuẩn hóa duy nhất |
| `A%2FB` | `%2F` thành `/`, có thể biến **một segment thành hai** | Reject encoded slash hoặc quy định/kiểm chứng xử lý nhất quán |
| `%252F` | Decode lần đầu ra `%2F`, decode hai lần thành `/` | Không decode hai lần; reject ambiguous/double encoding |
| `.%2E` hoặc `..` | Tạo dot-segment sau decode, có thể thay đổi path sau normalize | Reject dot-segments nếu endpoint không cho phép |
| `//` hoặc slash cuối | Proxy/router có thể gộp slash hoặc chuyển hướng | Quy định rõ trailing/multiple slash; reject nếu không thuộc grammar |
| `%5C` hoặc dấu `\` | Framework hoặc proxy có thể xem backslash như separator | Reject trong ID nếu không có nhu cầu |
| `;` trong path | Một số framework xử lý matrix parameter/path parameter sau dấu `;` | Quy định từ đầu; reject nếu không hỗ trợ |
| Unicode thường và dạng kết hợp | Có thể hiển thị giống nhưng byte UTF-8 khác | Hợp đồng Unicode normalization hoặc dùng opaque ID URL-safe |
| Chữ hoa/thường trong `WH-17` | Router, DB hoặc client có thể coi ID khác nhau | Chốt tính case-sensitive và enforce nhất quán |

**Không có một hàm “normalize mọi URI cho an toàn” thích hợp cho tất cả API.** Việc tự sort query, decode `%2F`, thay dấu slash hoặc chuẩn hóa Unicode có thể đổi nghĩa resource. Một hệ thống phải chọn **một policy cụ thể**, phát hành policy đó như một phần contract và thử nó qua hạ tầng thực tế.

### Profile đơn giản cho bài thực hành

Để loại bỏ phần lớn ambiguity, ta quy định endpoint minh họa chỉ chấp nhận:

```text
/v1/warehouses/{warehouseId}/settings
warehouseId = [A-Za-z0-9][A-Za-z0-9_-]{0,63}
```

Nghĩa là ID dài **1–64 ký tự ASCII**, không chứa dấu slash, dấu phần trăm, dấu chấm hay khoảng trắng. Hợp đồng này **không chấp nhận query string** cho endpoint `PUT` đang xét. Raw path bắt buộc trùng chính xác mẫu, nên `%57H-17`, `WH%2D17`, `WH%2F17`, dấu slash thừa hoặc `?mode=...` đều bị từ chối.

Đây là một **lựa chọn có chủ đích** cho một endpoint minh họa, không phải quy tắc bắt buộc cho mọi URL. Nếu ứng dụng cần UUID có dấu chấm, Unicode hoặc query, hãy định nghĩa và kiểm thử một phiên bản hợp đồng rộng hơn thay vì “lén” nới parser.

## 5. Hợp đồng HMAC-SHA256 cho một path parameter

Ví dụ: đối tác `partner-17` cập nhật settings của kho `WH-17` bằng `PUT`. Client và server cùng giữ secret tương ứng `(clientId=partner-17, keyId=k2, environment=production)`.

Để giữ trọng tâm path parameter, hợp đồng `hmac-warehouse-v1` quy định:

| Vị trí | Dòng canonical | Nguồn dữ liệu |
|---|---|---|
| 1 | `PUT` | Method thật; cấm method override ở endpoint |
| 2 | `/v1/warehouses/WH-17/settings` | **Raw request-target thực tế**, match route grammar; không có query |
| 3 | `host:api.example.test` | Host public tin cậy; chuẩn hóa theo contract |
| 4 | `content-type:application/json` | Media type bắt buộc, đúng một giá trị |
| 5 | `x-client-id:partner-17` | Client ID, có format/length bound |
| 6 | `x-key-id:k2` | Phiên bản key, được ký |
| 7 | `x-timestamp:<unix-seconds>` | Unix timestamp thập phân, được ký |
| 8 | `x-nonce:<random-nonce>` | Nonce ngẫu nhiên, được ký |
| 9 | `body-sha256:<base64url-digest>` | Base64URL không padding của SHA-256 trên raw body bytes |

Quy tắc byte-level:

- Mỗi dòng phân tách bằng **LF** (byte `0x0a`), không có newline sau dòng cuối.
- Mã hóa canonical string bằng **UTF-8** trước khi tính HMAC.
- Method luôn là `PUT` trong profile này; raw request-target phải match chính xác route grammar và **giữ nguyên từng ký tự của `warehouseId`**.
- Các header bắt buộc được kiểm tra **đúng một lần**, không có CR/LF hoặc giá trị nhập nhằng. Không tự tin header từ client trước khi verify.
- Body digest tính bằng `SHA-256` trên **chính raw body bytes** client sẽ gửi; không parse rồi serialize lại JSON.
- Tag là 32 byte `HMAC-SHA256(secret, canonicalBytes)`, sau đó encode **Base64URL không padding** và gửi trong `X-Signature`. Bản thân header `X-Signature` không nằm trong chuỗi ký.
- Vì method, path, query profile, content type và metadata đã được chốt, nếu hệ thống thêm `If-Match`, `Idempotency-Key` hoặc header quyết định quyền, hợp đồng phải được **nâng phiên bản và ký những trường mới** hoặc ràng buộc bằng context đáng tin khác.

### Request được ký

```http
PUT /v1/warehouses/WH-17/settings HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-17
X-Key-Id: k2
X-Timestamp: <unix-seconds-hien-tai>
X-Nonce: <nonce-128-bit>
X-Signature: <base64url-hmac-tag>

{"allowBackorder":false,"reorderThreshold":20}
```

Các mục nằm trong `<...>` là **placeholder**, phải thay bằng dữ liệu thật trước khi gửi. Với body UTF-8 như trên và **không thêm newline cuối**, canonical string là:

```text
PUT
/v1/warehouses/WH-17/settings
host:api.example.test
content-type:application/json
x-client-id:partner-17
x-key-id:k2
x-timestamp:<unix-seconds-hien-tai>
x-nonce:<nonce-128-bit>
body-sha256:<base64url-sha256-cua-dung-raw-body>
```

**Điểm quan trọng:** chuỗi được ký có `WH-17` thật, không phải `{warehouseId}`. Đổi path sang `/v1/warehouses/WH-99/settings` sau bước ký làm canonical request khác và chữ ký cũ không còn hợp lệ.

## 6. Luồng xử lý ở client, gateway, verifier và backend

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as Gateway / reverse proxy
    participant V as HMAC verifier
    participant K as Kho khóa
    participant N as Shared nonce store
    participant A as Backend
    C->>C: Chọn warehouseId=WH-17, dựng rawTarget đúng grammar
    C->>C: Chốt method, header, raw body; timestamp và nonce mới
    C->>C: HMAC-SHA256 trên canonical bytes chứa rawTarget
    C->>G: HTTPS PUT /v1/warehouses/WH-17/settings + signature
    G->>V: Chuyển request theo contract, không làm sai signed fields
    V->>V: Kiểm tra rawTarget/header/format/timestamp
    V->>K: Tra (environment, clientId, keyId)
    K-->>V: Secret và principal đúng owner, còn hiệu lực
    V->>V: Dựng canonical từ request thật; so HMAC
    alt Key hoặc signature không hợp lệ
        V-->>G: Authentication failure
        G-->>C: Reject
    else HMAC hợp lệ
        V->>N: Atomic insert-if-absent(clientId, nonce)
        alt Nonce trùng hoặc store unavailable
            V-->>G: Replay rejection / fail closed
            G-->>C: Reject
        else Nonce mới
            N-->>V: Inserted
            V->>A: Principal đã xác thực và request/route target
            A->>A: Trích warehouseId=WH-17, kiểm tra quyền resource
            A->>A: Validation, concurrency, transaction
            A-->>G: Business response
            G-->>C: HTTPS response
        end
    end
```

Ở đây có **ba ranh giới phải kiểm soát**:

1. **Client → verifier:** path thật mà client ký phải tương ứng với path verifier nhận và chuẩn hóa. Không dùng route template làm thông điệp ký.
2. **Verifier → router/backend:** path/resource mà backend xử lý phải là **cùng ý nghĩa** với path đã xác minh. Nếu gateway rewrite hay backend decode khác, cần fail closed hoặc hợp đồng biến đổi có bảo vệ.
3. **Authentication → authorization:** verifier xác nhận request sử dụng đúng key; backend mới xác nhận principal có quyền trên **`warehouseId` đã chọn**.

Nếu backend nhận một header kiểu `X-Warehouse-Id` hoặc `X-Authenticated-Principal` từ client, không được dùng nó để thay thế dữ liệu route/identity đã được xác minh. Gateway phải xóa/ghi đè những header nội bộ từ request public và ngăn truy cập trực tiếp backend bỏ qua verifier.

## 7. Java 17+: ràng buộc `warehouseId` vào chữ ký HMAC

Ví dụ tự chứa sau chủ đích sử dụng **profile path hẹp**: một endpoint duy nhất, không query, ID ASCII URL-safe. Class minh họa việc lấy path parameter từ **request-target thật** và đưa nguyên giá trị này vào canonical request trước khi dùng `javax.crypto.Mac`. Nó **không tự làm HTTP parsing**.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SignedWarehousePathV1 {
    // Hợp đồng chỉ cho phép /v1/warehouses/{id}/settings, không query.
    private static final Pattern TARGET = Pattern.compile(
            "^/v1/warehouses/([A-Za-z0-9][A-Za-z0-9_-]{0,63})/settings$");
    private static final Pattern SIGNATURE =
            Pattern.compile("[A-Za-z0-9_-]{43}");
    private static final Base64.Encoder B64 =
            Base64.getUrlEncoder().withoutPadding();

    private SignedWarehousePathV1() {}

    public record RequestParts(
            String method, String rawTarget, String publicHost,
            String contentType, String clientId, String keyId,
            String timestamp, String nonce, byte[] rawBody) {}

    /** Chỉ trích path param nếu rawTarget đúng toàn bộ route grammar. */
    public static String warehouseId(String rawTarget) {
        Matcher m = TARGET.matcher(Objects.requireNonNull(rawTarget));
        if (!m.matches()) {
            throw new IllegalArgumentException("Unsupported request-target");
        }
        return m.group(1);
    }

    /** Canonical request theo đúng thứ tự và dấu LF đã công bố. */
    public static String canonical(RequestParts r)
            throws GeneralSecurityException {
        Objects.requireNonNull(r);
        if (!"PUT".equals(r.method())) {
            throw new IllegalArgumentException("Expected PUT");
        }
        warehouseId(r.rawTarget()); // Reject encoded slash, query, dot, ...
        if (!"application/json".equals(r.contentType())) {
            throw new IllegalArgumentException("Invalid content type");
        }

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(Objects.requireNonNull(r.rawBody()));
        String bodyHash = B64.encodeToString(digest);

        return String.join("\n",
                "PUT",
                r.rawTarget(),  // RAW target chứa warehouseId đã chọn!
                "host:" + r.publicHost().toLowerCase(Locale.ROOT),
                "content-type:" + r.contentType(),
                "x-client-id:" + r.clientId(),
                "x-key-id:" + r.keyId(),
                "x-timestamp:" + r.timestamp(),
                "x-nonce:" + r.nonce(),
                "body-sha256:" + bodyHash);
    }

    private static byte[] mac(byte[] secret, RequestParts r)
            throws GeneralSecurityException {
        Mac instance = Mac.getInstance("HmacSHA256");
        instance.init(new SecretKeySpec(secret, "HmacSHA256"));
        return instance.doFinal(
                canonical(r).getBytes(StandardCharsets.UTF_8));
    }

    public static String sign(byte[] secret, RequestParts r)
            throws GeneralSecurityException {
        return B64.encodeToString(mac(secret, r));
    }

    public static boolean verify(
            byte[] secret, RequestParts received, String signature)
            throws GeneralSecurityException {

        if (signature == null ||
                !SIGNATURE.matcher(signature).matches()) {
            return false;
        }
        final byte[] supplied;
        try {
            supplied = Base64.getUrlDecoder().decode(signature);
        } catch (IllegalArgumentException malformed) {
            return false;
        }
        if (supplied.length != 32 ||
                !B64.encodeToString(supplied).equals(signature)) {
            return false;
        }

        byte[] expected = mac(secret, received);
        return MessageDigest.isEqual(expected, supplied);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        // Chỉ để mô phỏng: provisioning thực tế phải lưu/cấp secret
        // an toàn; verifier không sinh khóa mới cho mỗi request.
        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret);
        byte[] nonceBytes = new byte[16];
        new SecureRandom().nextBytes(nonceBytes);
        String nonce = B64.encodeToString(nonceBytes);

        RequestParts original = new RequestParts(
                "PUT", "/v1/warehouses/WH-17/settings",
                "api.example.test", "application/json",
                "partner-17", "k2",
                Long.toString(Instant.now().getEpochSecond()),
                nonce,
                "{\"allowBackorder\":false,\"reorderThreshold\":20}"
                        .getBytes(StandardCharsets.UTF_8));

        String signature = sign(secret, original);
        if (!verify(secret, original, signature)) {
            throw new AssertionError("Valid request rejected");
        }

        RequestParts changedPath = new RequestParts(
                original.method(),
                "/v1/warehouses/WH-99/settings",
                original.publicHost(), original.contentType(),
                original.clientId(), original.keyId(),
                original.timestamp(), original.nonce(),
                original.rawBody());

        if (verify(secret, changedPath, signature)) {
            throw new AssertionError("Changed path accepted!");
        }
        System.out.println("Path-bound HMAC checks: PASS");
    }
}
```

### Điều gì được bảo đảm bởi ví dụ?

- `warehouseId()` chỉ chấp nhận một dạng route **không nhập nhằng**. `WH-17` và `WH-99` là hai target khác nhau; `%57H-17`, `WH%2F17` và `?mode=replace` không được chấp nhận trong profile này.
- `canonical()` đưa **rawTarget đã chứa giá trị path parameter thật** vào HMAC cùng method, content type, client ID, key ID, timestamp, nonce và body digest.
- `verify()` yêu cầu tag HMAC-SHA256 Base64URL không padding **43 ký tự**; sau decode phải đúng **32 byte**, encode lại phải khớp, rồi so tag bytes bằng `MessageDigest.isEqual`.
- Client có thể chứng minh rằng chỉ thay `WH-17` thành `WH-99` thì không thể tái sử dụng chữ ký cũ với secret không đổi.

### Những việc mã chưa làm

Mã trên minh họa **mật mã và một route grammar**. Một production verifier còn phải kiểm tra: đúng một giá trị cho mỗi header, định dạng và cửa sổ timestamp, nonce store chia sẻ/nguyên tử, key lookup theo `(environment, clientId, keyId)`, trạng thái thu hồi, host public đáng tin, kích thước dữ liệu, phương thức/URI thực thi, quyền tenant và giao dịch. Không được tạo `RequestParts` từ một chuỗi canonical do client tự khai; server phải lấy từ **HTTP request thực nhận** và từ metadata mà ingress đã xác thực nguồn.

Phương thức `warehouseId()` chỉ cho phép trích ID từ biểu diễn mà hợp đồng ký sử dụng. Backend không nên parse lại cùng URI bằng một bộ quy tắc decode khác rồi chọn tài nguyên mới. Có thể chuyển **resource ID đã xác định theo parser đáng tin**, gắn với principal đã xác thực, qua context nội bộ được bảo vệ.

## 8. Gateway và router: nơi path có thể bị đổi nghĩa

Ở production, client có thể gửi:

```text
PUT https://api.example.test/public/v1/warehouses/WH-17/settings
```

Nhưng reverse proxy chuyển vào backend:

```text
PUT /v1/warehouses/WH-17/settings
```

Nếu client ký `/public/v1/warehouses/WH-17/settings` mà verifier sau proxy lại ký `/v1/warehouses/WH-17/settings`, HMAC sẽ khác. Nếu verifier dùng “original path” từ một header không được bảo vệ nhưng router lại dùng path đã rewrite, có thể phát sinh **khác biệt ý nghĩa** chứ không đơn thuần lỗi chữ ký.

### Hai thiết kế phổ biến

**A. Xác minh tại edge trước rewrite.** Edge verifier dùng request-target public theo hợp đồng; sau khi xác minh, nó chuyển principal và resource identity đã xác minh qua kênh nội bộ tin cậy. Backend không được nhận request đi vòng ngoài edge và không được tin header danh tính do client tự chèn.

**B. Xác minh ở service sau rewrite.** Ingress phải cung cấp biểu diễn ký tương ứng với request public theo một cơ chế đáng tin và **không cho client giả mạo**. Hợp đồng phải ràng buộc path gốc với route thật mà backend sẽ thực thi; mọi sự biến đổi phải được xác định và kiểm thử nhất quán.

Không dùng tùy tiện `X-Original-URI`, `X-Rewrite-URL` hoặc `X-Forwarded-*` từ request Internet: client có thể tự thêm các header này. Nếu phải dùng, ingress được ủy quyền phải xóa/ghi đè chúng, bảo vệ hop nội bộ và chỉ truyền các giá trị đã chuẩn hóa theo contract.

### Những thử nghiệm proxy cần thiết

- Request có hai dấu `//`, slash cuối và path có `.`/`..`.
- `%2F`, `%2f`, `%252F`, `%5C` và chuỗi ký tự percent-encoded không hợp lệ.
- Path parameter phân biệt chữ hoa/thường: `WH-17` so với `wh-17`.
- Header `Host` public so với internal, HTTP/2 `:authority`, đường đi qua CDN/LB.
- Prefix rewrite, path normalization và việc router thực thi một tài nguyên khác `warehouseId` đã xác minh.
- Request đi vào backend trực tiếp bỏ qua verifier; header identity giả do client gửi.

**Kỳ vọng chung:** request bị từ chối nếu không thuộc hợp đồng, hoặc đi qua đầy đủ các tầng với **cùng một định danh tài nguyên**. Không chấp nhận trạng thái “signature hợp lệ đối với ID A nhưng backend cập nhật ID B”.

## 9. Authentication, authorization và sở hữu tài nguyên path

Giả sử `partner-17` có secret hợp lệ và gửi:

```http
PUT /v1/warehouses/WH-99/settings HTTP/1.1
X-Client-Id: partner-17
X-Key-Id: k2
X-Signature: <hmac-hop-le-do-partner-17-tao>
```

Nếu `WH-99` thuộc đối tác khác, HMAC **vẫn có thể hợp lệ**: `partner-17` thực sự là bên tạo request bằng khóa của họ. Do đó backend phải đối chiếu:

```text
principal = partner-17       // Sinh ra sau khi HMAC hợp lệ
warehouseId = WH-99         // Từ path đã xác minh và route nhất quán

authorization.canUpdateSettings(principal, warehouseId) == false
=> 403 Forbidden (hoặc phản hồi theo chính sách công khai của API)
```

Đây là ví dụ của vấn đề **object-level authorization**: quyền truy cập từng đối tượng phải được kiểm tra theo *quan hệ principal–resource*. Một route có tên `warehouseId` không tự bảo đảm caller sở hữu kho ấy.

Khi `warehouseId` là định danh có thể đoán được, attacker là client hợp pháp vẫn có thể thử hàng loạt ID. Vì vậy:

- Dùng principal được **server thiết lập sau HMAC**, không lấy từ `X-Client-Id` chưa verify hay header `X-Authenticated-User` do client gửi.
- Ánh xạ warehouse ID tới tenant/owner ở phía backend, kiểm tra permission theo method/operation **trước khi thay đổi state**.
- Không chỉ dựa vào ID khó đoán để thay cho authorization; ID ngẫu nhiên không cấp quyền.
- Với `PUT` cập nhật đồng thời, có thể dùng `ETag/If-Match` để chống lost update. Nếu header `If-Match` ảnh hưởng nghiệp vụ, phải **ký nó trong hợp đồng riêng**; ví dụ `hmac-warehouse-v1` ở đây chưa có header đó và không được ngầm thêm mà vẫn nhận chữ ký cũ.
- Áp dụng rate limit và audit phù hợp, nhưng tránh làm lộ danh sách ID hay thông tin tenant qua lỗi công khai.

## 10. Replay protection và key rotation không phụ thuộc vào cách viết path

Dù path đã được ký, attacker vẫn có thể **phát lại nguyên request có path, body và signature không đổi** nếu không có replay protection. HMAC chỉ ràng buộc dữ liệu, không tự xác nhận rằng đây là lần gửi đầu tiên.

### Timestamp và nonce

- Ký `x-timestamp` (ví dụ Unix seconds) và `x-nonce` vào canonical request.
- Verifier kiểm tra cửa sổ chấp nhận, ví dụ ±300 giây theo chính sách và đồng hồ đồng bộ.
- **Sau khi HMAC hợp lệ**, ghi `(clientId, nonce)` vào kho chia sẻ giữa mọi replica bằng **atomic insert-if-absent**; không dùng `GET` rồi `SET` tách biệt hoặc cache RAM từng pod.
- Giữ nonce tới khi timestamp của request không còn được chấp nhận, tính cả trường hợp request đến rất sớm trong cửa sổ.
- Khi nonce store lỗi, endpoint nhạy cảm phải có chính sách an toàn; **fail closed** là lựa chọn mặc định hợp lý.

Nếu client retry cùng thao tác nhưng tạo timestamp/nonce/chữ ký mới, replay gate có thể coi là request mới. Với `PUT`, tính idempotent **không** giải quyết mọi side effect, concurrency hoặc retry sau timeout; cần kiểm soát điều kiện cập nhật và idempotency nghiệp vụ khi cần.

### Key ID và rotation

Client gửi `x-key-id=k2` trong dữ liệu được ký. Verifier tra **đúng khóa theo `(environment, clientId, keyId)`**, có thể tạm chấp nhận `k1` và `k2` trong giai đoạn chuyển tiếp hữu hạn. Sau khi thu hồi `k1`, request dùng nó phải bị từ chối ngay theo hiệu lực chính sách, kể cả khi một replica còn cache cũ.

**Key ID không phải secret**; secret là khóa HMAC thực. Nếu secret bị lộ, attacker có thể ký **request path mới với nonce mới**, và replay protection không ngăn được. Cần thu hồi key, rotation, cô lập tenant và audit.

## 11. Ma trận kiểm thử path parameter trong HMAC

| Ca kiểm thử | Thao tác | Kết quả kỳ vọng |
|---|---|---|
| Happy path | `PUT /v1/warehouses/WH-17/settings`, signature đúng, key hợp lệ, nonce mới | Authn pass; nếu có quyền thì handler cập nhật đúng `WH-17` |
| Sửa path parameter sau ký | Ký `WH-17` rồi thay target thành `WH-99` | HMAC mismatch, handler không chạy |
| Chuyển method | Ký `PUT` nhưng gửi `POST` cùng target và body | Từ chối theo hợp đồng |
| Ký route template | HMAC trên `/v1/warehouses/{warehouseId}/settings` | Test phải phát hiện và loại cách thiết kế này |
| Percent-encoded ID | `%57H-17`, `WH%2D17` | Reject trong profile ASCII không-encoding |
| Encoded slash | `WH%2F17` hoặc `WH%2f17` | Reject; không được biến thành hai segment |
| Double encoding | `WH%252F17` | Reject; không decode hai lần |
| Dot-segment/slash kép | `../`, `./`, `//` trong raw path | Reject hoặc theo một contract nhất quán trước verifier/router |
| Query string ngoài hợp đồng | Thêm `?mode=replace` | Reject với profile `hmac-warehouse-v1` không-query |
| Header trùng | Hai `X-Key-Id` hoặc `X-Signature` | Reject ở ingress/verifier |
| Body thay sau khi ký | Đổi `reorderThreshold` hoặc thêm whitespace | HMAC mismatch vì raw-body hash đã ký |
| Sai client/key scope | Gửi key của client A với `clientId` B | Không xác thực thành B |
| Key đã revoke | HMAC có thể tính đúng bằng secret cũ | Từ chối theo key state |
| Replay lần hai | Gửi lại cùng path/nonce/tag đã dùng | Chặn trước nghiệp vụ |
| Replay nhiều replica | Gửi hai request cùng nonce đồng thời | Nhiều nhất một request qua nonce gate |
| Đúng chữ ký, sai chủ kho | Client A tự ký request tới kho B | Authentication có thể pass, authorization phải deny |
| Rewrite qua proxy | Thay prefix/Host hoặc decode path trên gateway | Hoặc đúng theo contract và cùng resource, hoặc reject |
| Backend nhận header giả | Client gửi `X-Authenticated-Principal: admin` | Không ảnh hưởng danh tính/quyền nội bộ |

Ma trận cần chạy cả **unit test** cho HMAC/route grammar và **integration test** qua đúng cấu hình CDN, proxy, gateway, HTTP framework và backend. Kiểm thử trực tiếp hàm Java là chưa đủ để chứng minh không có mismatch giữa raw path và route thực thi.

## 12. Bài tập thực hành

Một API có endpoint:

```text
PUT /v1/teams/{teamId}/projects/{projectId}/settings
```

Client ký request bằng HMAC-SHA256 và gửi qua reverse proxy. Backend phục vụ nhiều tenant; verifier có hai replica; khóa được xoay vòng từ `k1` sang `k2`.

Hãy thiết kế:

1. **Grammar cho path parameter:** xác định ký tự hợp lệ, độ dài, phân biệt chữ hoa/thường, xử lý slash/percent-encoding và Unicode đối với `teamId`, `projectId`.
2. **Hợp đồng canonical:** method `PUT`, **actual raw path** chứa cả hai giá trị thật, các header có ý nghĩa, timestamp/nonce và digest raw body, cùng quy tắc UTF-8/LF.
3. **Giải pháp proxy:** chỉ rõ verifier nhận đường dẫn public hay internal, và làm sao chứng minh handler dùng cùng `teamId/projectId` mà verifier đã kiểm tra.
4. **Java verifier:** từ chối path nhập nhằng, tra đúng key theo `(env, clientId, keyId)`, tính lại HMAC, so tag bytes, kiểm tra nonce chung và tạo principal.
5. **Authorization:** principal phải có quyền cập nhật project thuộc team đó; cả `teamId` và `projectId` cần được kiểm tra về quan hệ sở hữu, không chỉ có chữ ký hợp lệ.
6. **Thử nghiệm âm tính:** thay team/project ID sau ký; thêm `%2F` hoặc `%252F`; đảo method; prefix rewrite; replay trên hai replica; dùng khóa bị thu hồi; gọi thẳng backend.
7. **Retry và concurrency:** mô tả vì sao `PUT` idempotent vẫn cần ETag/điều kiện cập nhật hoặc cơ chế idempotency riêng khi phù hợp.

**Tiêu chí hoàn thành:** Bạn phải chứng minh được ba sự trùng khớp: **path client đã ký**, **path verifier đã xác thực** và **resource backend thực sự xử lý**. Ngoài ra, chữ ký hợp lệ không được bỏ qua **quyền của principal trên từng tài nguyên**.

---

## Ghi nhớ

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, **path parameter là phần của đường dẫn thực tế dùng để xác định tài nguyên**, không phải tên placeholder trong route template. Khi xác thực bằng HMAC, hãy ràng buộc **method và request-target thật chứa path parameter** vào canonical request, thống nhất percent-encoding/normalization qua proxy, chặn diễn giải nhập nhằng và kiểm tra quyền đối với **resource sau khi xác thực**. Timestamp/nonce, key rotation, TLS và kiểm thử gateway vẫn là những thành phần cần thiết của bảo vệ HTTP request hoàn chỉnh.
