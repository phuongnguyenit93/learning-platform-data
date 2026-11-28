# Secret key trong HMAC request authentication

## Mục tiêu bài học

Trong chương **HMAC**, *secret key* (khóa bí mật dùng chung, hay *shared secret*) là nền tảng của xác thực HTTP request bằng HMAC. Client dùng khóa để tạo mã xác thực thông điệp từ **canonical request**; server dùng khóa tương ứng để tính lại và kiểm tra. Nếu khóa bị lộ, một bên thứ ba có thể tạo chữ ký hợp lệ và giả mạo client, ngay cả khi thuật toán HMAC-SHA256 được triển khai đúng.

Bài này thuộc module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, nơi người học thiết kế hợp đồng ký gồm method, URI, các header và/hoặc body; thực hành xác minh chữ ký, chống replay bằng timestamp/nonce, key rotation và kiểm thử qua proxy/gateway. Trọng tâm riêng của bài là **vòng đời, ranh giới tin cậy và cách sử dụng secret key**.

Sau bài học, bạn có thể:

- Phân biệt `clientId`, `keyId`, shared secret, chữ ký HMAC và danh tính client đã được xác thực.
- Tạo khóa có entropy cao bằng bộ sinh ngẫu nhiên mật mã; nhận biết lỗi mã hóa, lưu trữ và cấp phát khóa.
- Thiết kế cách chọn đúng khóa ở server cho một request, kể cả khi có nhiều client và nhiều phiên bản key.
- Xoay/thu hồi khóa theo quy trình rõ ràng, không làm gián đoạn toàn bộ tích hợp.
- Giải thích vì sao khóa đúng vẫn chưa đủ để ngăn replay hoặc cấp quyền truy cập.

## 1. Secret key làm gì trong HMAC?

**HMAC** (*Hash-based Message Authentication Code*) là một thuật toán sử dụng khóa đối xứng và hàm băm mật mã. Với HMAC-SHA256:

```text
signatureBytes = HMAC-SHA256(secretKeyBytes, UTF8(canonicalRequest))
signatureHeader = Base64URL_NoPadding(signatureBytes)
```

Trong đó:

- `secretKeyBytes` là **dãy byte bí mật** đã cấp cho client, đồng thời được server giữ hoặc truy xuất an toàn.
- `canonicalRequest` là chuỗi được client và server tạo theo cùng một **hợp đồng ký**: thường gồm method, raw URI/path + query, các header cần bảo vệ, hash của byte body, timestamp, nonce và định danh khóa.
- `signatureBytes` là MAC 32 byte khi dùng HMAC-SHA256; chuyển sang Base64URL không padding thường có **43 ký tự** để đặt vào header.
- Server không nhận secret trong mỗi request; server tra secret từ bản ghi credential đáng tin cậy rồi tính MAC độc lập.

### 1.1. Secret key khác mật khẩu, chữ ký và API key thế nào?

| Thành phần | Vai trò | Có đi cùng mỗi HTTP request? |
| --- | --- | --- |
| `clientId` | Định danh công khai của tích hợp để server tra registry. | Có thể có trong header. Chỉ là **lời khai** cho đến khi HMAC hợp lệ. |
| `keyId` | Chỉ định phiên bản credential đang dùng. | Thường có; không cần giữ bí mật. |
| **HMAC secret key** | Bí mật đối xứng dùng để tính/xác minh MAC. | **Không** gửi trực tiếp. |
| **HMAC signature** | Kết quả tính MAC trên canonical request. | Thường có trong header `X-Signature`. |
| **Bearer API key** | Chuỗi bí mật được gửi trực tiếp, ai cầm được thì dùng được theo cơ chế bearer. | Có trong request theo thiết kế bearer; khác với cơ chế HMAC request. |
| **Password của con người** | Chuỗi người dùng ghi nhớ, thường có entropy thấp và cần cơ chế bảo vệ riêng. | Không dùng làm HMAC secret trực tiếp trong thiết kế M2M. |

**Chữ ký không phải secret key.** MAC có thể xuất hiện trong bản ghi HTTP phục vụ điều tra, nhưng không được suy từ MAC rằng người ngoài có thể khôi phục secret. Dù vậy, MAC của một request còn hợp lệ **có thể bị phát lại** nếu hệ thống không kiểm soát timestamp và nonce.

**HMAC không mã hóa nội dung.** Body vẫn đọc được với bên có quyền nhìn thấy HTTP plaintext. Để bảo mật dữ liệu trên đường truyền, dùng HTTPS/TLS. HMAC bảo vệ tính toàn vẹn của **những trường đã ký** và chứng minh phía gửi biết shared secret, trong giới hạn mô hình tin cậy.

### 1.2. HMAC là cơ chế khóa đối xứng

Client và server cùng có khả năng tính MAC hợp lệ vì đều biết khóa. Điều này phù hợp với machine-to-machine giữa các bên đã đăng ký, nhưng kéo theo ba giới hạn:

1. **Khóa bị lộ ở một trong hai phía đều nguy hiểm.** Mật mã HMAC không giúp phân biệt request do client thật tạo với request do kẻ tấn công biết cùng secret tạo.
2. **Server cũng có thể tạo MAC.** HMAC không tạo bằng chứng chống chối bỏ (*non-repudiation*) kiểu chữ ký số bất đối xứng.
3. **Danh tính được xác thực là client đã đăng ký, không mặc nhiên là người dùng cuối.** Nếu request thay mặt một người dùng, cần kiểm tra user identity và authorization bằng cơ chế bổ sung.

## 2. Sinh secret key có entropy cao

Khả năng chống giả mạo phụ thuộc trực tiếp vào độ khó đoán của secret. Trong tích hợp HMAC-SHA256, lựa chọn thực tế là **khóa 32 byte được sinh bằng CSPRNG** (*cryptographically secure pseudorandom number generator*), tương đương 256 bit dữ liệu ngẫu nhiên.

Không tạo khóa từ tên ứng dụng, email, ngày tháng, `UUID.randomUUID()` ghép tùy tiện, `Random`, một password ngắn hoặc chuỗi tự nghĩ. Độ dài nhìn thấy của chuỗi **không** bảo đảm entropy: `"aaaaaaaa..."` dù dài vẫn dễ đoán.

### 2.1. Ví dụ Java: sinh khóa đúng cách

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class GenerateHmacKey {
    private GenerateHmacKey() {}

    public static byte[] generateKey() {
        byte[] secret = new byte[32]; // 256 bit ngẫu nhiên
        new SecureRandom().nextBytes(secret);
        return secret;
    }

    public static String encodeForSecureProvisioning(byte[] secret) {
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(secret);
    }

    // Chỉ chuyển secret qua quy trình cấp phát an toàn.
    // Không in ra terminal/log hoặc commit vào repository.
}
```

**Base64URL chỉ biến đổi cách biểu diễn byte**, không mã hóa bảo mật. Một khóa 32 byte được Base64URL không padding thành chuỗi dài 43 ký tự; khi sử dụng phải **decode về đúng 32 byte ban đầu**:

```text
32 random bytes --Base64URL encode--> 43 ký tự để cấp phát/lưu trữ
43 ký tự       --Base64URL decode--> 32 random bytes để khởi tạo Mac
```

Không thay decode bằng `encodedSecret.getBytes(UTF_8)`; cách đó dùng **byte của chuỗi Base64**, tạo một khóa khác. Nếu hệ thống dùng hex thay cho Base64URL, cũng phải chuyển hex thành byte trước khi tính HMAC. Hai bên phải thống nhất định dạng credential được cấp.

### 2.2. Vì sao chọn 32 byte cho HMAC-SHA256?

SHA-256 cho kết quả 256 bit; khóa ngẫu nhiên 256 bit có biên an toàn tốt cho cơ chế HMAC-SHA256. Chuẩn HMAC cho phép khóa dài khác nhau và xử lý nội bộ các khóa dài hơn kích thước block của hàm băm, nhưng **không có lợi ích thực tế khi tự tạo khóa dài mà entropy thấp**. Dùng đúng 32 byte sinh ngẫu nhiên bằng CSPRNG là quy tắc triển khai đơn giản, dễ kiểm thử.

Không lấy password người dùng rồi đặt trực tiếp làm HMAC secret. Nếu có nhu cầu dẫn xuất khóa từ một bí mật đầu vào, phải có thiết kế KDF chuyên biệt và đánh giá entropy, tách mục đích sử dụng; với secret M2M thông thường, **sinh ngẫu nhiên và cấp phát riêng** là phù hợp hơn.

## 3. Gắn secret với client ID, key ID và audience

Trong hệ thống có nhiều client, server cần biết **dùng khóa nào để xác minh request** nhưng không yêu cầu client gửi khóa. Một registry có thể lưu:

```text
ClientRegistration
  clientId: warehouse-sync-prod
  status: ACTIVE
  allowedAudiences: [inventory-api-prod]
  allowedScopes: [stock:update]
  allowedTenants: [merchant-42]
  credentials:
    - keyId: hmac-2026-08
      status: RETIRING
      secretRef: secret-manager/warehouse-sync/2026-08
    - keyId: hmac-2026-11
      status: ACTIVE
      secretRef: secret-manager/warehouse-sync/2026-11
```

Các bản ghi `secretRef` là **tham chiếu** tới nơi quản lý secret, không phải giá trị secret thực. Đây là mô hình dữ liệu minh họa; hệ thống cụ thể có thể tổ chức storage khác.

Để chọn khóa:

```text
request.X-Client-Id = warehouse-sync-prod
request.X-Key-Id    = hmac-2026-11

registration = registry.findClient(clientId)
credential   = registry.findCredential(clientId, keyId)
secretBytes  = secretStore.read(credential.secretRef)
```

Ngay tại thời điểm lookup, các header từ request vẫn **chưa được tin cậy**. Chỉ sau khi server xác minh HMAC bằng đúng credential đã đăng ký, kiểm tra hiệu lực, audience và replay, client ID mới được chuyển thành **authenticated client principal**.

Các nguyên tắc quan trọng:

- **Client ID là danh tính ổn định** của một tích hợp; **key ID là phiên bản credential** và có thể thay đổi khi rotation.
- `keyId` không bí mật, nhưng phải được **ký trong canonical request** cùng `clientId` để chống thay/tráo metadata.
- Server chỉ chấp nhận credential **thuộc đúng clientId** đã đăng ký, còn hiệu lực và được phép sử dụng ở API/audience hiện tại. Không thử vô hạn khóa của client khác để tìm khóa vô tình khớp.
- Một secret riêng cho từng client, từng môi trường và/hoặc audience giúp giới hạn phạm vi thiệt hại. Không tái sử dụng chung secret giữa staging và production.
- Quyền (scope, tenant, resource) lấy từ registry đã được quản lý, **không** từ header tự khai như `X-Role: admin`.

### 3.1. Có nên ký clientId và keyId?

**Có**, trong hợp đồng minh họa. Nếu client ID hoặc key ID chỉ dùng để lookup mà không nằm trong dữ liệu ký, kẻ tấn công có thể gây ra nhầm lẫn định danh/credential trong những thiết kế registry thiếu ràng buộc. Khi chúng được ký, thay `X-Client-Id` hoặc `X-Key-Id` sau khi client ký sẽ thay đổi canonical request và làm chữ ký không còn khớp.

Dù đã ký, server **vẫn bắt buộc** kiểm tra quan hệ `(clientId, keyId)` trong registry; không được dùng MAC hợp lệ của credential A để gán quyền của client B.

## 4. Cấp phát, lưu trữ và truy cập secret key

Secret thường có hai bản sao logic: một bản phía client để ký và một bản phía server để xác minh. Tùy kiến trúc, phía server có thể lưu byte secret được mã hóa khi lưu, truy xuất từ secret manager hoặc dùng một dịch vụ có khả năng tính/xác minh HMAC thay cho việc xuất khóa vào process. Phía client vẫn cần khả năng thực hiện phép HMAC tương ứng.

### 4.1. Quy trình cấp phát

1. **Đăng ký client:** chỉ rõ hệ thống sở hữu, môi trường, audience, scopes, tenant, đầu mối vận hành và thời hạn credential.
2. **Sinh khóa:** sử dụng CSPRNG tạo secret độc lập, ví dụ 32 byte cho HMAC-SHA256; gắn `keyId` không bí mật.
3. **Chuyển giao:** cấp secret một lần qua kênh an toàn có kiểm soát danh tính người/ứng dụng nhận. Không đưa secret vào email thường, chat công khai, ticket hay file nằm trong source control.
4. **Lưu và sử dụng:** client dùng secret manager/credential store phù hợp. Server giới hạn quyền truy cập secret theo service account, môi trường và mục đích; theo dõi thao tác đọc/cập nhật.
5. **Xác nhận hoạt động:** chạy request ký thử qua môi trường tích hợp; chỉ ghi trạng thái, client/key ID và lỗi chung, **không** ghi secret hoặc canonical request chứa dữ liệu nhạy cảm.
6. **Rotation và thu hồi:** có thể thay credential theo từng client mà không cần đổi toàn bộ danh tính hay phân quyền.

### 4.2. Phân loại nơi lưu giữ

| Vị trí / kỹ thuật | Đánh giá |
| --- | --- |
| Secret manager/Vault có RBAC, audit và mã hóa khi lưu | **Ưu tiên** cho ứng dụng production; chỉ cấp quyền đọc cho workload cần sử dụng. |
| KMS/HSM có API HMAC phù hợp | Server có thể yêu cầu tính/xác minh MAC mà không xuất raw key vào process **nếu** khả năng và quy trình cấp phát cho phía client tương thích. |
| Biến môi trường do nền tảng cấp phát từ secret store | Có thể dùng theo chính sách, nhưng lưu ý bí mật vẫn có thể lộ qua quyền xem môi trường, crash dump, công cụ chẩn đoán hoặc cấu hình triển khai. |
| File cấu hình cục bộ có quyền truy cập hạn chế | Chỉ phù hợp trong môi trường cho phép; cần bảo vệ file, backup, quyền đọc và không commit vào repo. |
| `application.yml`, repo, test fixture có secret production | **Không chấp nhận**: dễ lộ qua commit, CI, artifact và lịch sử Git. |
| Mobile app, JavaScript trình duyệt, public frontend | Không giữ được shared secret bền vững trước người kiểm soát thiết bị/mã client; đặt việc ký phía backend đáng tin cậy hoặc dùng mô hình xác thực phù hợp hơn. |
| Log, traces, exception, dashboard, telemetry | Không lưu secret, header mang secret, dump vùng nhớ hay nội dung request nhạy cảm. |

Khi dùng secret manager, hãy ràng buộc quyền theo **least privilege**, tách quyền tạo/xoay/thu hồi khỏi quyền chỉ đọc nếu có thể. Tránh “cả cluster dùng một credential quản trị” và đảm bảo bản sao dự phòng/backup được bảo vệ giống bản chính.

Trong Java, secret có thể xuất hiện dưới dạng `byte[]`. Hạn chế tạo bản sao hoặc chuyển thành `String` không cần thiết; có thể xóa nội dung mảng bằng `Arrays.fill` khi không còn dùng, nhưng **không được xem đó là xóa bảo đảm** vì JVM, provider mật mã hoặc các bản sao nội bộ có thể đã giữ byte ở nơi khác. Quan trọng hơn là quyền tiến trình, quản lý heap dump, thời hạn lưu trong bộ nhớ và khả năng thu hồi.

### 4.3. Bảo vệ secret trên đường đi

HTTPS bảo vệ HTTP request khi truyền giữa các điểm kết nối TLS, nhưng không thay thế bảo vệ khóa ở hai đầu. Khi TLS kết thúc tại gateway, cần xem rõ gateway có được đọc request, header hay secret không; **shared secret không bao giờ nên xuất hiện như một HTTP header gửi đến API**. Nếu có header nội bộ chứa principal đã xác thực sau khi gateway xác minh, phải chặn header giả từ internet và bảo vệ kết nối gateway–backend (ví dụ mTLS).

## 5. Secret được dùng thế nào để ký một request?

Không có một định dạng canonical request HMAC phổ quát cho mọi API. Hai bên phải ký **cùng byte**, cùng thuật toán, cùng cách xử lý method, raw URI/path+query, header/body và encoding.

Hợp đồng ví dụ `v1` dưới đây dùng:

- Thuật toán: `HMAC-SHA256` trên UTF-8 của canonical request.
- Có **11 dòng**: thuật toán, phiên bản, audience, client ID, key ID, method, raw target, Content-Type, body hash, timestamp, nonce.
- Mỗi dòng phân tách bằng **một** ký tự LF (`\n`), không có LF cuối; các trường không được chứa CR/LF.
- HTTP method viết hoa; raw target gồm **path và query nguyên dạng** đã thống nhất ở điểm xác minh. Không tự sắp xếp query, decode/re-encode phần trăm hoặc thay đổi dấu slash.
- Content-Type bỏ space/tab ở hai đầu; body hash là SHA-256 của **byte body thực tế**, được mã hóa Base64URL không padding. Không parse rồi serialize lại JSON để tính hash.
- Timestamp là epoch theo giây UTC; nonce chứa tối thiểu 128 bit ngẫu nhiên. Audience là định danh API đích đã được cấu hình đáng tin cậy.
- Signature và secret **không nằm** trong canonical request. Các header liên quan đến ký phải có đúng một giá trị và được kiểm tra cú pháp/độ dài.
- Trong hợp đồng mẫu, chỉ chấp nhận `Content-Encoding` vắng mặt hoặc `identity` để tránh mơ hồ byte khi proxy giải nén.

Ví dụ HTTP:

```http
POST /v1/stock?warehouse=central HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: warehouse-sync-prod
X-Key-Id: hmac-2026-11
X-Timestamp: 1795800000
X-Nonce: J1ngj12Ar6DCmm9IFgI1Rw
X-Content-SHA256: <base64url-sha256-body>
X-Signature: <base64url-hmac>

{"sku":"A-123","quantity":120}
```

Canonical request tương ứng:

```text
HMAC-SHA256
v1
inventory-api-prod
warehouse-sync-prod
hmac-2026-11
POST
/v1/stock?warehouse=central
application/json
<base64url-sha256-body>
1795800000
J1ngj12Ar6DCmm9IFgI1Rw
```

Các chuỗi `<...>` là placeholder, không phải chữ ký thật. Timestamp trên chỉ để minh họa: request thực tế phải tạo timestamp hiện tại, vì server sẽ từ chối thời gian quá cũ/quá xa trong tương lai. Client lấy secret theo `hmac-2026-11`, tính MAC; server tra **đúng key đó**, dựng cùng canonical request từ dữ liệu đã nhận, rồi đối chiếu.

### 5.1. Điều gì làm chữ ký sai dù secret đúng?

- Client ký `/v1/stock?b=2&a=1` nhưng server xác minh `/v1/stock?a=1&b=2`.
- JSON được parse/serialize lại, làm thay đổi khoảng trắng, thứ tự key hoặc biểu diễn ký tự.
- Proxy rewrite `/public/v1/stock` thành `/v1/stock` trước khi backend lấy raw target.
- Một bên dùng Base64URL không padding; bên kia dùng hex cho body hash hoặc decode nhầm secret.
- Header `Content-Type` bị framework thêm `charset=UTF-8` sau khi ký.
- Hai phía khác nhau về dấu xuống dòng (`CRLF` so với `LF`), bảng mã UTF-8 hoặc dấu LF cuối.

Đây là lỗi **hợp đồng ký**, không thể sửa bằng cách tăng độ dài khóa. Cần kiểm thử end-to-end qua client library, proxy/gateway và HTTP server.

## 6. Ví dụ Java: một secret, hai phía dùng cùng byte khóa

Đây là ví dụ JDK 17+ **tự chứa** về việc cấp khóa, biểu diễn Base64URL, ký và kiểm tra MAC. Nó minh họa phần mật mã của HMAC; adapter HTTP production cần bổ sung xác minh header, raw target, timestamp, nonce, registry, giới hạn kích thước request và quyền.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacSecretKeyDemo {
    private static final Base64.Encoder B64 =
            Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder B64_DECODER =
            Base64.getUrlDecoder();

    private HmacSecretKeyDemo() {}

    static byte[] randomBytes(int size) {
        byte[] result = new byte[size];
        new SecureRandom().nextBytes(result);
        return result;
    }

    static String encodeKey(byte[] key) {
        return B64.encodeToString(key);
    }

    static byte[] decodeKey(String encoded) {
        // Quy tắc cấp khóa của ví dụ: đúng 32 byte / 43 ký tự Base64URL.
        if (encoded == null || !encoded.matches("[A-Za-z0-9_-]{43}")) {
            throw new IllegalArgumentException("Invalid key format");
        }
        byte[] key = B64_DECODER.decode(encoded);
        if (key.length != 32 || !encodeKey(key).equals(encoded)) {
            throw new IllegalArgumentException("Non-canonical key encoding");
        }
        return key;
    }

    static byte[] sha256(byte[] input) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(input);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }

    static byte[] mac(byte[] secret, String canonicalRequest) {
        try {
            Mac hmac = Mac.getInstance("HmacSHA256");
            hmac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return hmac.doFinal(
                    canonicalRequest.getBytes(StandardCharsets.UTF_8));
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(ex);
        }
    }

    static boolean verify(
            byte[] secret, String canonicalRequest, String receivedSignature) {
        if (receivedSignature == null
                || !receivedSignature.matches("[A-Za-z0-9_-]{43}")) {
            return false;
        }
        byte[] supplied;
        try {
            supplied = B64_DECODER.decode(receivedSignature);
        } catch (IllegalArgumentException ex) {
            return false;
        }
        byte[] expected = mac(secret, canonicalRequest);
        // So sánh byte MAC, hạn chế rò rỉ thời gian do so sánh sớm thoát.
        return MessageDigest.isEqual(expected, supplied);
    }

    public static void main(String[] args) {
        // Mô phỏng một bước cấp phát an toàn. Không log keyEncoded!
        String keyEncoded = encodeKey(randomBytes(32));
        byte[] clientSecret = decodeKey(keyEncoded);
        byte[] serverSecret = decodeKey(keyEncoded);

        byte[] body = "{\"sku\":\"A-123\",\"quantity\":120}"
                .getBytes(StandardCharsets.UTF_8);
        String bodyHash = B64.encodeToString(sha256(body));
        String timestamp = Long.toString(Instant.now().getEpochSecond());
        String nonce = B64.encodeToString(randomBytes(16)); // 128 bit

        String canonical = String.join("\n",
                "HMAC-SHA256", "v1",
                "inventory-api-prod", "warehouse-sync-prod", "hmac-2026-11",
                "POST", "/v1/stock?warehouse=central", "application/json",
                bodyHash, timestamp, nonce);

        String signature = B64.encodeToString(mac(clientSecret, canonical));
        System.out.println("Valid signature: "
                + verify(serverSecret, canonical, signature));

        // Đổi dữ liệu đã ký thì MAC phải không khớp.
        String tampered = canonical.replace("warehouse=central",
                                            "warehouse=other");
        System.out.println("Tampered request accepted: "
                + verify(serverSecret, tampered, signature));

        // Nỗ lực dọn mảng có thể kiểm soát; JVM có thể giữ bản sao.
        Arrays.fill(clientSecret, (byte) 0);
        Arrays.fill(serverSecret, (byte) 0);
    }
}
```

Kết quả kỳ vọng:

```text
Valid signature: true
Tampered request accepted: false
```

Trong ứng dụng thực tế, client và server chạy ở hai nơi khác nhau. Biến `keyEncoded` chỉ mô phỏng **một secret được cấp qua kênh an toàn**; không dùng cách truyền secret bằng log, stdout, HTTP hay source code. Không gộp dữ liệu HTTP từ client và server vào cùng một biến như demo: server phải tự dựng canonical request từ **request thực nhận**.

Khi xác minh, server phải lấy secret từ registry theo `(clientId, keyId)`, kiểm tra client/key/audience hợp lệ, xác minh HMAC và replay rồi **mới** gắn principal vào security context. Một lời khai `X-Client-Id` không đủ để chứng minh danh tính.

## 7. Key rotation: đổi credential nhưng giữ nguyên client identity

Không nên để một shared secret tồn tại vô thời hạn hoặc chờ đến khi xảy ra sự cố mới có khả năng thay khóa. Với HMAC, client cần biết key đang dùng để ký; server cần có khả năng **xác minh đúng key ID**, kể cả trong giai đoạn chuyển tiếp.

### 7.1. Quy trình rotation theo phiên bản key

Giả sử client `warehouse-sync-prod` đang dùng `hmac-2026-08`:

1. **Tạo key mới:** server sinh secret ngẫu nhiên riêng, tạo `hmac-2026-11`; đăng ký trạng thái `ACTIVE` và cấp an toàn cho client.
2. **Cho phép chồng lấn hữu hạn:** server chấp nhận MAC với key cũ (`RETIRING`) và key mới (`ACTIVE`) theo đúng key ID. Không thay khóa của phiên bản cũ bằng byte key mới.
3. **Chuyển phía client:** client cấu hình dùng key mới cho những request ký tiếp theo; mỗi request mang đúng `X-Key-Id` tương ứng.
4. **Quan sát sử dụng:** theo dõi lượng request còn dùng key cũ qua key ID, không log secret hoặc chữ ký đầy đủ.
5. **Thu hồi key cũ:** sau khi client chuyển xong và hết khoảng chuyển tiếp, chuyển `hmac-2026-08` sang `REVOKED`; mọi request ký bằng key này bị từ chối, kể cả MAC khớp.
6. **Dọn kho bí mật:** thu hồi quyền đọc và xóa bản secret đã hết thời gian giữ theo chính sách; xử lý cache khóa theo thời hạn phù hợp để việc thu hồi có hiệu lực.

| Trạng thái | Có được client dùng để ký request mới? | Server có thể xác minh? |
| --- | --- | --- |
| `PENDING` | Chưa. | Chưa, cho đến lúc kích hoạt theo chính sách. |
| `ACTIVE` | Có. | Có, nếu còn hiệu lực và đúng audience. |
| `RETIRING` | Nên chuyển khỏi trạng thái này. | Có tạm thời trong cửa sổ migration hữu hạn. |
| `REVOKED` | Không. | Không, dù phép HMAC toán học đúng. |
| `EXPIRED` | Không. | Không, theo thời hạn đã thiết lập. |

**Rotation không tự sửa được việc lộ secret.** Khi xác định có khả năng bị xâm nhập, cần thu hồi key bị lộ càng sớm càng phù hợp với kế hoạch ứng phó sự cố; không mặc định duy trì giai đoạn overlap kéo dài. Khóa mới phải là **byte ngẫu nhiên mới**, không tạo bằng cách thay một vài ký tự của khóa cũ.

### 7.2. Nhiều key đang dùng và tính nhất quán

Server nên tra key bằng `(clientId, keyId)`, kiểm tra thuật toán theo chính sách server, trạng thái và thời hạn. Không dựa vào trường `algorithm` do client tự chọn để chuyển sang thuật toán yếu. Khi có cache credential, cần có cách thu hồi/giảm TTL để key vừa bị khóa không tiếp tục được chấp nhận quá lâu.

Không cần tạo client ID mới mỗi lần đổi secret: quyền, tenant và audit gắn với **client principal**; chỉ credential thay đổi. Nếu muốn tách hai workload có quyền khác nhau, tạo **hai client identity** ngay từ thiết kế thay vì dùng một secret chung.

## 8. Secret đúng vẫn chưa đủ để chống replay hoặc phân quyền

Chữ ký HMAC có thể vẫn hợp lệ khi một attacker **gửi lại nguyên request đã ký**, vì họ không cần biết secret để replay. Do đó, hợp đồng ký cần chứa timestamp và nonce được MAC bảo vệ.

Một luồng xác minh nên thực hiện:

1. Đọc, kiểm tra cú pháp và giới hạn kích thước của request; lấy raw target và body bytes ở đúng trust boundary.
2. Kiểm tra timestamp theo đồng hồ server, ví dụ chênh lệch không quá **±300 giây**; sử dụng clock được đồng bộ. Chưa tin timestamp cho tới khi MAC hợp lệ.
3. Tra credential theo `(clientId, keyId)`; kiểm tra trạng thái, thời hạn, audience và client.
4. Xác minh body hash và HMAC bằng secret tương ứng. So sánh **byte MAC** bằng cơ chế phù hợp như `MessageDigest.isEqual`.
5. Sau MAC hợp lệ, ghi nonce theo khóa `(audience, clientId, keyId, nonce)` bằng thao tác **put-if-absent nguyên tử** trong kho chia sẻ giữa các node.
6. Chỉ chấp nhận request đầu tiên claim nonce; lần phát lại trong cửa sổ bị từ chối. Nếu nonce store lỗi, không bỏ qua kiểm tra như một hành vi fallback mặc định.
7. Tạo authenticated principal từ registry và kiểm tra authorization trên API, tenant, scope và tài nguyên thực tế.

Ví dụ giả mã:

```text
if abs(nowSeconds - timestampSeconds) > 300: reject 401
credential = registry.get(clientId, keyId, expectedAudience)
if credential not active: reject 401
if not hmacVerify(credential.secret, canonicalRequest, signature): reject 401
if not replayStore.claimOnce(audience, clientId, keyId, nonce, ttl=610s): reject 401
principal = buildAuthenticatedPrincipal(registry.getClient(clientId))
if not authorize(principal, action, resource, tenant): reject 403
executeOperation()
```

Với timestamp được cho phép lệch trong khoảng ±300 giây, nonce có thể cần được giữ **ít nhất 600 giây từ lúc request được chấp nhận** để bao phủ lúc gửi gần sát ranh giới thời gian tương lai; TTL 610 giây là một ví dụ có biên. Một hệ thống phân tán cần kho nonce chung và thao tác nguyên tử (ví dụ lệnh Redis `SET ... NX EX`); không dùng `GET` rồi `SET` riêng rẽ hoặc map cục bộ theo từng instance.

Nonce chống replay **không thay thế idempotency**. Nếu client gửi lại một thao tác thanh toán với nonce mới sau khi mất response, HMAC vẫn có thể hợp lệ và giao dịch có thể bị thực thi hai lần; cần cơ chế idempotency gắn với ý nghĩa nghiệp vụ.

### 8.1. Authentication khác authorization

Ví dụ client `warehouse-sync-prod` có shared secret hợp lệ và scope `stock:update` cho tenant `merchant-42`. Request hợp lệ đòi cập nhật kho của `merchant-99`:

- **Authentication:** HMAC đúng, nonce mới, credential hợp lệ ⇒ xác thực được client `warehouse-sync-prod`.
- **Authorization:** Client không được cấp quyền trên `merchant-99` ⇒ API trả `403 Forbidden`.
- Một request có chữ ký sai/khóa bị thu hồi sẽ bị từ chối ở bước xác thực (thường là `401 Unauthorized`) trước khi đánh giá quyền.

Đừng gán quyền theo `X-Scope` hoặc `X-Tenant-Id` do client tự khai nếu không kiểm tra với quyền lưu ở server. Ký một giá trị do client tự khai chỉ chứng minh **client đã ký giá trị đó**, chứ không chứng minh giá trị đã được hệ thống cấp phép.

## 9. Nguy cơ phổ biến và cách phòng tránh

| Nguy cơ | Triệu chứng | Biện pháp |
| --- | --- | --- |
| Khóa yếu hoặc dự đoán được | Có thể dò/đoán key từ danh sách phổ biến. | 32 byte CSPRNG; đánh giá nơi tạo key và entropy. |
| Dùng Base64 text như raw bytes | Client/server tính MAC khác nhau dù “chuỗi khóa” nhìn giống. | Decode Base64URL/hex về cùng byte gốc; test vector chung. |
| Secret lộ trong repo/log/CI | Người có quyền xem bản ghi có thể ký request mới. | Secret manager, masking, redaction, kiểm soát job và xử lý thu hồi. |
| Dùng chung key cho mọi client | Một key bị lộ ảnh hưởng mọi tích hợp; không thu hồi riêng được. | Secret riêng mỗi client/môi trường/audience. |
| Chọn khóa bằng key ID mà bỏ qua client ID | Confusion giữa hai client, có thể gán nhầm principal. | Lookup cặp `(clientId, keyId)` và ký cả hai giá trị. |
| Rotation không có trạng thái | Client đang dùng key cũ đột ngột lỗi hoặc key bị thu hồi vẫn sống. | Trạng thái ACTIVE/RETIRING/REVOKED và thời hạn chuyển tiếp, cache invalidation. |
| Không ràng buộc audience | Request hợp lệ được chuyển sang dịch vụ/môi trường khác. | Ký audience và ràng buộc credential với API đích. |
| Replay khi timestamp còn hiệu lực | Một request đã ký được chấp nhận nhiều lần. | Timestamp + nonce ký kèm, lưu nonce nguyên tử. |
| Gateway rewrite method/URI/body | Chữ ký sai không rõ nguyên nhân; hoặc lớp xác minh nhìn dữ liệu khác lớp xử lý. | Chọn trust boundary xác minh, kiểm thử raw request-target và byte body qua các hop. |
| Dùng browser/mobile làm nơi giữ secret lâu dài | Người dùng thiết bị có thể trích xuất key hoặc mã ký. | Ký ở backend kiểm soát được hoặc dùng mô hình định danh phù hợp thiết bị không tin cậy. |
| Tin header principal do internet gửi | Client bỏ qua HMAC và mạo danh service có quyền cao. | Xóa/chặn header nội bộ tại edge, xác minh HMAC trước khi tạo context. |
| Chữ ký đúng bị coi là đủ quyền | Client hợp lệ đọc/sửa dữ liệu tenant khác. | Authorization độc lập theo scope, tenant và resource. |

### 9.1. Khi nghi secret đã bị lộ

Một quy trình ứng phó tối thiểu:

1. Xác định `clientId`, `keyId`, hệ thống và audience có nguy cơ; bảo vệ bằng chứng sự cố **không kèm secret lộ thêm**.
2. Thu hồi hoặc vô hiệu hóa credential nghi lộ theo mức khẩn cấp; cắt các đường truy cập bí mật bất thường.
3. Sinh **key mới độc lập**, cấp cho client bằng kênh tin cậy và cập nhật trạng thái/kiểm tra cache thu hồi.
4. Kiểm tra request bất thường, lưu lượng ký MAC hợp lệ nhưng sai phạm vi, nonce/replay và tác động nghiệp vụ; làm sạch secret lộ trong artifact, log, backup hoặc repo theo chính sách xử lý.
5. Xem lại nguyên nhân gốc: secret hiển thị ở CI, tài khoản secret manager quá rộng quyền, log request, file cấu hình công khai hoặc code front-end.

Nếu chỉ thay `keyId` nhưng giữ **cùng byte secret**, đó **không phải rotation mật mã**. Người đã biết secret cũ vẫn có thể giả mạo request bằng key mới nếu biết hoặc đoán metadata tương ứng.

## 10. Kiểm thử secret key và hệ thống HMAC

Các test nên dùng **secret giả chỉ phục vụ kiểm thử**, không dùng key production. Với mỗi test vector, ghi byte key kiểm thử, chuỗi canonical theo UTF-8, hash body và MAC mong đợi trong fixture được kiểm soát. Sử dụng cùng vector ở các client SDK Java/Node.js/Go nếu có.

| Ca thử | Kết quả kỳ vọng |
| --- | --- |
| Client và server dùng cùng raw key byte, cùng canonical request | Chữ ký hợp lệ; server tạo principal đúng. |
| Một bên dùng byte UTF-8 của chuỗi Base64 thay vì decode secret | Chữ ký sai, xác định lỗi định dạng key. |
| Thay một byte trong secret | Chữ ký sai. |
| Khác method, URI, query order, Content-Type hoặc body byte sau khi ký | Chữ ký sai; trường nào được ký phải được bảo vệ. |
| Tráo `clientId` hoặc `keyId` sau khi ký | Xác minh thất bại. |
| Dùng key của client A để khai client B | Từ chối, không fallback sang key khác. |
| Dùng request của audience prod để gọi staging | Từ chối nếu audience khác theo hợp đồng. |
| Sử dụng key `REVOKED` | Từ chối dù MAC tự tính theo key đó có thể đúng. |
| Chuyển từ key cũ sang mới trong giai đoạn overlap | Cả hai hợp lệ theo thời hạn; principal vẫn cùng client ID. |
| Replay cùng nonce trong cửa sổ; hai request đồng thời tới hai node | Chỉ một request claim nonce thành công. |
| Timestamp quá cũ/quá xa tương lai | Từ chối. |
| Chữ ký đúng nhưng không đủ scope hoặc sai tenant | Xác thực được, phân quyền trả 403. |
| Gateway thay đổi raw path hoặc byte body trước khi xác minh | Test phát hiện sai canonical; xác minh ở điểm thích hợp theo hợp đồng. |
| Secret manager tạm thời không phản hồi hoặc cache key bị thu hồi | Hệ thống xử lý fail-closed theo chính sách; không tự dùng key không xác định hoặc bỏ qua xác thực. |

Ngoài test logic, kiểm tra cấu hình giám sát: log nên chứa mã lỗi và `clientId/keyId` ở mức phù hợp, nhưng không chứa secret, body nhạy cảm hoặc toàn bộ canonical request nếu có dữ liệu riêng tư. Kiểm tra cả quyền xem log, backup và artifact CI/CD.

## 11. Bài thực hành

Tạo client `warehouse-sync-prod` gọi API `POST /v1/stock` qua HMAC-SHA256:

1. Sinh **32 byte CSPRNG** bằng Java và cấp phát an toàn cho hai phía. Mỗi bên decode về raw byte và kiểm tra MAC trên một test vector chung; không in secret thật ra log.
2. Cài registry chứa `clientId`, `keyId`, `secretRef`, trạng thái, audience và scopes. Client gửi client ID/key ID; server chỉ dùng chúng để chọn credential, sau đó xác minh MAC.
3. Định nghĩa canonical request ký method, raw target, Content-Type, body hash, audience, client ID, key ID, timestamp, nonce. Tạo request hợp lệ và lần lượt thay đổi body, path hoặc key ID để quan sát lỗi.
4. Thêm nonce store dùng thao tác nguyên tử, thử replay hai request giống nhau đến hai instance và xác nhận chỉ một request được chấp nhận.
5. Cấp `hmac-2026-12` và thực hiện rotation từ `hmac-2026-11`, sau đó thu hồi khóa cũ. Xác minh principal không đổi nhưng key bị thu hồi không dùng được.
6. Đặt gateway rewrite `/external/v1/stock` thành `/v1/stock` và thử xác minh trước/sau rewrite; bảo đảm đường dẫn dùng trong MAC giống hợp đồng của client.
7. Gửi request ký hợp lệ đến tenant không được cấp quyền, kiểm tra API từ chối ở tầng **authorization**, không đánh đồng chữ ký đúng với cho phép thao tác.

**Câu hỏi tự đánh giá:** Vì sao `keyId` có thể công khai nhưng secret phải giữ kín? Khi chuyển secret từ Base64URL sang byte, vì sao không dùng `getBytes(UTF_8)` trên chuỗi Base64? Nếu hai client cùng dùng một secret, hậu quả khi một client bị xâm nhập là gì? Tại sao rotation cần sinh secret hoàn toàn mới? Nếu request có MAC hợp lệ nhưng đã được gửi trước đó, server dựa vào yếu tố nào để từ chối? Nếu request hợp lệ muốn sửa dữ liệu tenant khác, ai ra quyết định từ chối?

Một thiết kế HMAC request auth đáng tin cậy bắt đầu từ **secret key đủ mạnh và được quản lý an toàn**, nhưng chỉ hoàn chỉnh khi kết hợp hợp đồng canonical request nhất quán, xác minh đúng credential, chống replay, kiểm thử gateway và phân quyền độc lập theo tài nguyên thực tế.

