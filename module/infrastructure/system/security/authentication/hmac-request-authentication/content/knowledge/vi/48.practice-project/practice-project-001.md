# Dự án thực hành: Thiết kế signature scheme cho HMAC HTTP Request Authentication

## 1. Bối cảnh và yêu cầu của dự án

Bạn phụ trách thiết kế cơ chế ký request cho một API đơn hàng nhận tích hợp từ các đối tác. Mỗi client được cấp một **shared secret** và một `keyId` để tạo mã xác thực thông điệp HMAC. API xử lý cả yêu cầu đọc đơn hàng và yêu cầu tạo đơn hàng; một số request đi qua CDN, API gateway và reverse proxy trước khi đến ứng dụng Java/Spring Security.

Bài thực hành thuộc module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**: thiết kế xác thực HTTP request bằng HMAC dựa trên **canonical request** gồm HTTP method, URI, header và body theo hợp đồng ký; xác minh chữ ký, ngăn replay bằng timestamp/nonce, quản lý key rotation và kiểm thử nhiều tuyến proxy/gateway. Sau khi xác thực thành công, backend vẫn phải kiểm tra **phân quyền**.

Nhiệm vụ của bạn là xây dựng và bảo vệ một **signature scheme phiên bản đầu tiên**, gọi là `HMAC-HTTP-V1`, đủ chính xác để hai nhóm viết SDK khác ngôn ngữ có thể tạo **cùng MAC từ cùng request** mà không trao đổi mã nguồn với nhau.

### Mục tiêu đầu ra

Hoàn thành dự án khi có thể chứng minh được:

1. Có tài liệu giao thức chỉ rõ **byte nào được ký**, thứ tự trường, encoding, cách parse và cách xử lý trường hợp không hợp lệ.
2. Một client Java tạo chữ ký HMAC-SHA-256 và gửi request theo định dạng đã công bố.
3. Một verifier độc lập xây dựng lại canonical request, kiểm tra MAC, timestamp, nonce, trạng thái credential và tạo principal đã xác thực.
4. Các request bị sửa method, path, query, header đã ký hoặc body bị từ chối; request dùng lại nonce cũng bị từ chối.
5. Gateway và backend không diễn giải khác nhau cùng một request; hệ thống không chấp nhận header trùng hay canonicalization mơ hồ.
6. Sau xác thực, ứng dụng vẫn từ chối những client không đủ quyền nghiệp vụ; key bị thu hồi không còn được chấp nhận.

**Phạm vi giả định:** Hai API `GET /v1/orders` và `POST /v1/orders`, HTTPS bắt buộc, client không phải ứng dụng JavaScript công khai trên trình duyệt. Scheme mẫu bên dưới là **hợp đồng do dự án định nghĩa**, không phải một chuẩn HTTP HMAC mặc định của Spring Security hoặc một tiêu chuẩn có thể tự suy từ tên header.

## 2. Threat model và các thuộc tính bảo mật cần giữ

Trước khi code, hãy trả lời: attacker có thể kiểm soát những thành phần nào, hệ thống tin những gì, và điều gì xảy ra nếu một thành phần bị sửa đổi?

| Tác nhân / tình huống | Khả năng | Thuộc tính cần bảo vệ |
| --- | --- | --- |
| Người ngoài không biết secret | Tạo request, sửa URL/query/header/body, gửi chữ ký giả | Không thể tạo request được xác thực cho client hợp pháp |
| Kẻ quan sát được request hợp lệ | Gửi lại request hoặc điều chỉnh một phần request | Timestamp/nonce giới hạn replay; sửa byte đã ký làm MAC sai |
| Proxy/gateway | Rewrite path, đổi thứ tự query, đổi `Host`, thêm/xóa header | Client và verifier dùng cùng hợp đồng canonical hóa ở ranh giới tin cậy |
| Client hoặc secret bị lộ | Ký request tùy ý bằng secret bị lộ | Thu hồi key, chặn client, rate limit, điều tra; HMAC không tự giải quyết lộ secret |
| Một client hợp lệ nhưng ít quyền | Ký request truy cập đơn hàng của tenant khác | Authorization từ chối theo principal, route và resource |
| Các instance chạy song song | Xử lý hai request có cùng nonce gần như đồng thời | Nonce được claim nguyên tử qua kho dùng chung |
| Vận hành đang xoay key | Cho phép key cũ và mới trong cửa sổ chuyển tiếp | Mỗi `keyId` chỉ đúng secret/profile; key revoked luôn bị từ chối |

HMAC cung cấp bằng chứng rằng bên gửi **có khả năng sử dụng shared secret** và nội dung đã ký không bị sửa đổi ngoài khả năng tính lại tag. Nó **không mã hóa body**, không tự cấp quyền truy cập, không thay thế TLS và không ngăn được kẻ có secret bị đánh cắp tạo chữ ký mới.

Các bất biến cần kiểm tra trong review:

- **Cùng ngữ nghĩa đã được cho phép → cùng representation ký** đối với các biến thể được profile tuyên bố tương đương, chẳng hạn thứ tự tham số query đơn trị.
- **Khác ngữ nghĩa bảo mật → khác byte được ký** hoặc input bị từ chối sớm. Không có tình huống verifier dùng tham số đầu tiên nhưng controller dùng tham số cuối.
- **Một request chọn một profile.** Không thử nhiều cách tạo MAC đến khi có một cách khớp.
- **Chữ ký hợp lệ không đồng nghĩa được phân quyền.** Principal được tạo sau MAC/replay checks, còn quyết định truy cập thực hiện ở bước riêng.

## 3. Đóng băng bản thiết kế `HMAC-HTTP-V1`

### 3.1. Thuật toán, key và tag

| Thuộc tính | Quy ước cho bài thực hành |
| --- | --- |
| Signature profile | `HMAC-HTTP-V1`, không đổi quy tắc trong cùng version |
| MAC | HMAC-SHA-256; tên thuật toán JCA là `HmacSHA256` |
| Secret | 32 byte ngẫu nhiên từ CSPRNG cho từng client/key; lưu qua secret manager/KMS |
| MAC tag | Đủ 32 byte, không cho rút ngắn |
| Wire encoding | Base64 chuẩn RFC 4648 có padding; với 32 byte là 44 ký tự |
| Key identifier | Header `X-HMAC-Key-Id`, giá trị ASCII `[A-Za-z0-9._-]` từ 1 đến 64 ký tự |
| Timestamp | Header `X-HMAC-Timestamp` là số giây Unix UTC ở dạng decimal tối giản, không dấu cộng hoặc số 0 thừa |
| Nonce | Header `X-HMAC-Nonce`, 16 byte ngẫu nhiên biểu diễn bằng **32 chữ số hex thường** |
| Signature | Header `X-HMAC-Signature`, chỉ chứa Base64 của tag |
| Clock skew | Chấp nhận khi `abs(serverNowSeconds - timestamp) <= 300` |
| Replay | Chỉ một lần claim cho cùng `keyId + nonce`; lưu trong kho chia sẻ, TTL ít nhất 660 giây trong bài thực hành |
| Audience | Hằng số `orders-api.prod` tại cả client và verifier; tách môi trường staging/prod |

**Vì sao chọn HMAC-SHA-256?** Thuật toán có thư viện hỗ trợ rộng, tag 32 byte đủ cho thiết kế này khi secret có entropy tốt, dễ kiểm thử trên nhiều SDK. Không dùng `SHA256(secret + request)` hoặc hash request không có khóa như một MAC tự chế.

**Vì sao ký `keyId` và audience?** `keyId` đưa định danh credential vào nội dung ký; audience là domain separator ràng buộc signature với API đích. Nếu cùng server có hai môi trường/ứng dụng mang ý nghĩa bảo mật khác nhau, mỗi nơi phải dùng audience hoặc secret riêng, tránh replay xuyên hệ thống.

Khi key rotation, phát hành `keyId` và secret mới; key cũ có thể còn active trong một thời gian **được phê duyệt**. Khi secret bị lộ, thu hồi key ngay, không kéo dài thời gian chấp nhận vì đang migration.

### 3.2. Cú pháp header

Một request đã ký phải có **chính xác một** giá trị cho mỗi header HMAC:

~~~http
X-HMAC-Key-Id: partner-demo-k1
X-HMAC-Timestamp: 1795860000
X-HMAC-Nonce: 00112233445566778899aabbccddeeff
X-HMAC-Signature: JNnP/SRwQQP9QlRekAGdtXSONTJX+YN8jqH85cJOvo8=
~~~

Các tên này là ví dụ cho dự án. HTTP header name không phân biệt chữ hoa/chữ thường; verifier phải đối xử `x-hmac-nonce` và `X-HMAC-Nonce` như cùng tên. Giá trị phải qua **strict parsing**: không có CR/LF, khoảng trắng bất thường, giá trị trùng hoặc giá trị bị gộp không hợp lệ. Không âm thầm lấy giá trị đầu tiên khi request cung cấp hai header cùng tên.

Không cho client tự chọn `alg=none`, `HMAC-SHA1` hay thuật toán tùy ý. Profile `V1` đã cố định HMAC-SHA-256. Thay đổi thuật toán là một profile mới, được server cho phép qua chính sách key/client.

### 3.3. Định dạng canonical request chính xác

Canonical request là một chuỗi UTF-8 gồm **10 dòng**, nối bằng đúng byte LF (`0A`), **không có LF cuối**. Dòng có thể có nội dung rỗng (ví dụ `Content-Type` của GET); thứ tự tuyệt đối không thay đổi.

| Dòng | Giá trị |
| ---: | --- |
| 1 | Hằng số `HMAC-HTTP-V1` |
| 2 | Hằng số audience `orders-api.prod` |
| 3 | HTTP method chữ hoa, chỉ `GET` hoặc `POST` trong bài |
| 4 | Canonical path |
| 5 | Canonical query; chuỗi rỗng nếu không có query |
| 6 | Canonical `Content-Type`; GET là chuỗi rỗng, POST là `application/json` |
| 7 | SHA-256 của **raw body bytes**, dạng hex chữ thường 64 ký tự |
| 8 | `keyId` |
| 9 | Timestamp decimal Unix seconds |
| 10 | Nonce hex thường |

Công thức:

~~~text
canonicalBytes = UTF8(joinWithLF(
  "HMAC-HTTP-V1",
  "orders-api.prod",
  method,
  canonicalPath,
  canonicalQuery,
  canonicalContentType,
  lowerHex(SHA256(rawBodyBytes)),
  keyId,
  timestamp,
  nonce
))  // không thêm newline cuối

signature = Base64WithPadding(HMAC_SHA256(sharedSecret, canonicalBytes))
~~~

Cấm ký tự CR/LF và giá trị bất hợp lệ ở mọi trường đầu vào; việc giữ **số dòng cố định** và validate đầu vào ngăn hai tổ hợp trường bị ghép thành cùng một chuỗi ký. Không chỉ nói “ký URL, body và header” mà bỏ qua thứ tự, delimiter hoặc encoding.

### 3.4. Canonical path, query và body

**Path** cho dự án là request path ở ranh giới verifier tin cậy, hỗ trợ chính xác `/v1/orders` hoặc `/v1/orders/{orderId}` với `orderId` chỉ chứa ASCII unreserved (chữ, số, `-._~`). Không cho encoded slash `%2F`, dot-segment `..`, double slash hay path được proxy viết lại thiếu quy tắc. Có thể chọn canonical path RFC 3986 phong phú hơn trong sản phẩm thực tế, nhưng phải ghi thành **profile version có test vector**. Không lấy đường dẫn đã được router giải mã theo kiểu khác với dữ liệu đã ký.

**Query** trong bài dùng tham số **đơn trị, không phụ thuộc thứ tự**, với quy tắc:

1. Lấy raw query (không gồm `?`); query thiếu hoặc rỗng có canonical query là chuỗi rỗng.
2. Tách theo `&` thô; mỗi thành phần phải là `name=value`, tên không rỗng; cho phép value rỗng nhưng không cho thiếu dấu `=` hay dấu phân cách thừa.
3. Chỉ cho phép ký tự ASCII unreserved xuất hiện trực tiếp; các byte khác phải được percent-encode dưới dạng `%HH`. Dấu `+` thô không hợp lệ; dấu cộng literal phải là `%2B`.
4. Percent-decode đúng một lần; kiểm tra UTF-8 nghiêm ngặt, từ chối byte lỗi và control characters. Không tự áp dụng Unicode NFC/NFD trong profile ví dụ.
5. Percent-encode lại byte UTF-8: unreserved giữ nguyên, byte khác ghi `%HH` với **hex chữ hoa**.
6. Từ chối tên lặp **sau khi decode/encode chuẩn hóa**, kể cả `a` và `%61`.
7. Sắp xếp cặp theo tên đã encode, so sánh ASCII từ điển; ghép `name=value` bằng `&`.

Ví dụ:

| Raw query | Canonical query / kết quả |
| --- | --- |
| `status=paid&page=2` | `page=2&status=paid` |
| `page=2&status=paid` | `page=2&status=paid` |
| `q=a%20b` | `q=a%20b` |
| `x=%7e` | `x=~` |
| `x=%2f` | `x=%2F` |
| `x=a+b` | **Reject**: dấu `+` thô |
| `id=1&id=2` | **Reject**: duplicate |
| `id=1&%69d=2` | **Reject**: duplicate sau normalize |
| `flag=` | `flag=` |
| `flag` hoặc `a=1&` | **Reject**: cú pháp không hợp lệ |

**Body:** ký **SHA-256 trên byte body nguyên vẹn**, không parse rồi serialize lại JSON. Dấu cách, thứ tự key JSON, charset hay newline thay đổi trong body đều làm digest thay đổi. GET phải có body rỗng; POST bắt buộc có `Content-Type: application/json` đúng giá trị và body JSON được ứng dụng chấp nhận. Verifier không được chỉ tin body digest do header bên ngoài tự khai: phải tự tính digest từ **byte thực nhận**.

Trong dự án, dòng Content-Type là `application/json` cho POST và rỗng cho GET. Không chấp nhận `application/json; charset=utf-8` ở V1; muốn mở rộng tham số header phải công bố quy tắc canonicalization ở profile mới hoặc bản hợp đồng có tương thích được chứng minh.

## 4. Golden vector bắt buộc của dự án

Đây là test vector có thể chạy độc lập để kiểm tra mã tạo MAC. **Secret là dữ liệu thử nghiệm công khai**, tuyệt đối không dùng cho production.

| Trường | Giá trị |
| --- | --- |
| Key hex (32 byte) | `000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f` |
| Method | `GET` |
| Raw path | `/v1/orders` |
| Raw query | `status=paid&page=2` |
| Canonical query | `page=2&status=paid` |
| Body | Chuỗi byte rỗng |
| Content-Type | Không gửi; dòng canonical rỗng |
| Key ID | `partner-demo-k1` |
| Timestamp | `1795860000` = `2026-11-28T10:00:00Z` |
| Nonce | `00112233445566778899aabbccddeeff` |
| Audience | `orders-api.prod` |

SHA-256 của body rỗng:

~~~text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Canonical request chính xác, **có một dòng trống ngay sau `page=2&status=paid`** và không có LF cuối:

~~~text
HMAC-HTTP-V1
orders-api.prod
GET
/v1/orders
page=2&status=paid

e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
partner-demo-k1
1795860000
00112233445566778899aabbccddeeff
~~~

Kết quả HMAC-SHA-256 đã tính từ **188 ký tự ASCII / 188 byte UTF-8** của canonical request trên:

~~~text
MAC hex:
24d9cffd24704103fd42545e90019db5748e353257f9837c8ea1fce5c24ebe8f

MAC Base64 (giá trị header X-HMAC-Signature):
JNnP/SRwQQP9QlRekAGdtXSONTJX+YN8jqH85cJOvo8=
~~~

Để chạy kiểm thử e2e với timestamp cố định này, **cố định clock của verifier ở `2026-11-28T10:00:00Z`** và xóa nonce test trước lần đầu; ở thời gian thực ngoài cửa sổ ±300 giây, request này phải bị từ chối vì đã hết hạn, dù MAC đúng. Gửi lại lần thứ hai với nonce đã claim phải bị từ chối do replay.

Ví dụ request HTTP:

~~~http
GET /v1/orders?status=paid&page=2 HTTP/1.1
Host: api.example.test
X-HMAC-Key-Id: partner-demo-k1
X-HMAC-Timestamp: 1795860000
X-HMAC-Nonce: 00112233445566778899aabbccddeeff
X-HMAC-Signature: JNnP/SRwQQP9QlRekAGdtXSONTJX+YN8jqH85cJOvo8=
~~~

Dù `Host` trong HTTP có thể là `api.example.test`, chính sách v1 ràng buộc request với audience cố định `orders-api.prod`. Nếu hệ thống chạy nhiều virtual hosts có cùng audience nhưng quyền khác nhau, phải tách audience/secret hoặc bổ sung canonical authority được định nghĩa chính xác; không để khác biệt host tạo ra một đường replay ngoài dự kiến.

## 5. Thiết kế luồng xử lý client, gateway và server

~~~mermaid
sequenceDiagram
    autonumber
    participant SDK as Client SDK
    participant GW as Gateway / WAF
    participant AUTH as HMAC verifier
    participant KEYS as Credential store
    participant NONCE as Shared nonce store
    participant API as Orders API

    SDK->>SDK: Chuẩn hóa URI, header, raw body
    SDK->>SDK: Tạo canonical bytes và HMAC
    SDK->>GW: HTTPS request + keyId/timestamp/nonce/signature
    GW->>AUTH: Chuyển tiếp request theo trust boundary
    AUTH->>AUTH: Strict parse profile, header, path và query
    AUTH->>KEYS: Tra keyId, trạng thái và secret
    KEYS-->>AUTH: Credential, clientId, scopes
    AUTH->>AUTH: Tự tính body hash, MAC, timestamp
    AUTH->>NONCE: Claim keyId + nonce nguyên tử
    NONCE-->>AUTH: Accepted hoặc duplicate
    alt Xác thực thất bại / replay
        AUTH-->>SDK: 401 với thông báo chung
    else Xác thực hợp lệ
        AUTH->>API: Trusted principal đã xác thực
        API->>API: Kiểm tra quyền route/tenant
        alt Thiếu quyền
            API-->>SDK: 403 Forbidden
        else Có quyền
            API-->>SDK: Kết quả nghiệp vụ
        end
    end
~~~

Luồng trên là thiết kế logic. Trong thực tế Spring Security có thể kiểm tra một số điều kiện về key/timestamp trước khi tính MAC để giảm chi phí, nhưng không được tạo authenticated principal hay quy trách nhiệm cho client **chỉ** từ keyId/header tự khai.

**Điểm đặt verifier:** Chọn gateway hoặc backend làm ranh giới xác minh. Nếu đặt ở backend, gateway phải giữ đúng representation cần ký hoặc chuyển request-target gốc qua metadata đã chứng thực và đã làm sạch header từ bên ngoài. Nếu gateway đã xác thực rồi gửi principal xuống backend, kết nối gateway–backend cần tin cậy (ví dụ mTLS và ACL phù hợp), backend không tin header định danh giả do client tự thêm.

**Bất biến xử lý:** Chặn request sai HMAC/replay **trước khi** controller tạo đơn, ghi dữ liệu hay đưa job vào queue. Nếu request đã được enqueue trước khi block client, cần chính sách riêng cho job đang chờ; kiểm tra HTTP không tự hủy các side effect đã phát sinh.

## 6. Hiện thực tham khảo bằng Java 17

Đoạn code dưới đây là thành phần tính canonical bytes và HMAC có thể đưa vào cả SDK và test verifier. Nó **không phải một HTTP filter hoàn chỉnh**; parser, canonical path/query, credential lookup, nonce store và phân quyền cần bổ sung theo các bước của dự án.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacHttpV1 {
    private static final String PROFILE = "HMAC-HTTP-V1";
    private static final String AUDIENCE = "orders-api.prod";
    private static final String JCA_MAC = "HmacSHA256";
    private static final int TAG_BYTES = 32;

    private HmacHttpV1() {}

    public static byte[] canonicalBytes(
            String method,
            String canonicalPath,
            String canonicalQuery,
            String contentType,
            byte[] rawBody,
            String keyId,
            long timestampSeconds,
            String nonce) throws GeneralSecurityException {

        // Caller phải validate mọi field và dùng canonicalQuery
        // từ parser v1; rawBody tuyệt đối không được serialize lại.
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(rawBody);
        String bodySha256 = HexFormat.of().formatHex(digest);

        String canonical = String.join("\n",
                PROFILE,
                AUDIENCE,
                method,
                canonicalPath,
                canonicalQuery,
                contentType,
                bodySha256,
                keyId,
                Long.toString(timestampSeconds),
                nonce);

        // Không thêm LF ở cuối.
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    public static byte[] mac(byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {
        Mac hmac = Mac.getInstance(JCA_MAC);
        hmac.init(new SecretKeySpec(secret, JCA_MAC));
        // Mac có trạng thái: tạo mới hoặc cấp riêng theo request/luồng.
        return hmac.doFinal(canonicalBytes);
    }

    public static String signBase64(byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {
        return Base64.getEncoder().encodeToString(
                mac(secret, canonicalBytes));
    }

    public static boolean verifyBase64(
            byte[] secret,
            byte[] canonicalBytes,
            String signature) throws GeneralSecurityException {

        if (signature == null || signature.length() != 44) {
            return false;
        }

        final byte[] received;
        try {
            received = Base64.getDecoder().decode(signature);
        } catch (IllegalArgumentException malformed) {
            return false;
        }
        // Kiểm tra tag đủ 32 byte và Base64 là dạng chuẩn duy nhất.
        if (received.length != TAG_BYTES
                || !Base64.getEncoder().encodeToString(received)
                        .equals(signature)) {
            return false;
        }

        byte[] expected = mac(secret, canonicalBytes);
        return MessageDigest.isEqual(expected, received);
    }
}
~~~

**Cách dùng với golden vector:**

~~~java
import java.util.HexFormat;

byte[] testSecret = HexFormat.of().parseHex(
        "000102030405060708090a0b0c0d0e0f"
      + "101112131415161718191a1b1c1d1e1f");

byte[] canonical = HmacHttpV1.canonicalBytes(
        "GET",
        "/v1/orders",
        "page=2&status=paid",
        "",
        new byte[0],
        "partner-demo-k1",
        1795860000L,
        "00112233445566778899aabbccddeeff");

String signature = HmacHttpV1.signBase64(testSecret, canonical);
assert signature.equals("JNnP/SRwQQP9QlRekAGdtXSONTJX+YN8jqH85cJOvo8=");
~~~

**Lưu ý triển khai:** Code cố ý nhận các giá trị đã chuẩn hóa và secret thử nghiệm; ứng dụng cần kiểm tra giới hạn body, header, cấu trúc query và validation trước khi gọi. Verifier lấy secret từ credential store theo keyId, kiểm tra profile/status, rồi dựng canonical bytes từ **request thực nhận**. Không nhận trực tiếp `canonicalBytes` do client tự gửi.

### 6.1. Giả mã verifier end-to-end

~~~text
require HTTPS at public boundary
rateLimitUntrustedSourceIfNecessary(request)
envelope = parseStrictHmacV1Headers(request)          // cấm duplicate/mixed
credential = credentialStore.lookup(envelope.keyId)
require credential exists and status == ACTIVE
require credential.allowedProfiles contains "HMAC-HTTP-V1"

path = validateCanonicalPath(getTrustedRawPath(request))
query = canonicalizeRawQuery(getTrustedRawQuery(request))
contentType = validateContentType(request)
rawBody = readBodyWithSizeLimit(request)
require method/body/contentType agree with route contract
canonical = canonicalBytes(method, path, query, contentType,
                           rawBody, envelope.keyId,
                           envelope.timestamp, envelope.nonce)

expected = HMAC_SHA256(credential.secret, canonical)
provided = strictDecodeFullBase64Tag(envelope.signature)
require constantTimeEqual(expected, provided)
require timestampWithinWindow(envelope.timestamp, serverClock, 300s)
require nonceStore.claimOnce(credential.keyId, envelope.nonce, ttl=660s)

principal = authenticatedClient(credential.clientId, credential.scopes)
require client is not blocked
require principal is authorized for route and business resource
execute business operation
~~~

Đây là **giả mã thuật toán**, không phải chính sách HTTP response hoặc đoạn chương trình có thể chạy nguyên dạng. Có thể từ chối timestamp rõ ràng không hợp lệ từ sớm, nhưng chỉ ghi nhận nonce **sau khi MAC hợp lệ** để tránh attacker làm cạn khóa nonce của client khác bằng request ký sai.

## 7. Timestamp, nonce và key lifecycle

### 7.1. Chống replay nhiều instance

Scheme chấp nhận timestamp trong cửa sổ ±300 giây, nghĩa là một request có timestamp `T` có thể được chấp nhận sớm nhất ở `T - 300` và muộn nhất ở `T + 300`. Vì vậy nonce claim tại thời điểm sớm phải được giữ ít nhất **600 giây**, cộng margin cho xử lý/độ trễ. Bài thực hành chọn **660 giây**, không phải TTL 300 giây.

Có thể hiện thực bằng thao tác Redis nguyên tử tương đương:

~~~text
SET hmac:nonce:<key-id>:<nonce> 1 NX EX 660
~~~

Chỉ chấp nhận khi thao tác trả thành công; kết quả duplicate hoặc lỗi truy cập nonce store phải ngăn xử lý nghiệp vụ. Với hệ thống có nhiều region, cần cùng một miền chống replay hoặc thiết kế điều phối nhất quán; các cache nonce độc lập theo region sẽ tạo đường replay.

**Không dùng timestamp làm duy nhất khóa replay**, vì attacker có thể phát lại cùng nonce và tạo các timestamp hợp lệ khác nếu họ có khả năng ký; chính sách của dự án là mỗi `keyId + nonce` được claim một lần trong TTL. Nonce phải được sinh bằng CSPRNG cho mỗi request mới. Khi client retry một giao dịch cần tránh thực thi trùng, kết hợp **idempotency key** ở lớp nghiệp vụ; replay protection và idempotency giải quyết hai vấn đề khác nhau.

### 7.2. Quản lý credential

Thiết kế dữ liệu credential tối thiểu:

~~~yaml
# Dữ liệu minh họa của dự án, không phải metadata bài học
keyId: partner-demo-k1
clientId: partner-demo
profile: HMAC-HTTP-V1
status: ACTIVE
notBefore: "2026-11-01T00:00:00Z"
notAfter: "2027-01-01T00:00:00Z"
scopes:
  - orders:read
  - orders:create
secretReference: "secret-manager://example/partner-demo-k1"
~~~

- **Cấp key:** sinh 32 byte ngẫu nhiên từ CSPRNG, giao bằng kênh bí mật được kiểm soát, không gửi lại secret qua log/ticket.
- **Rotate:** cấp `keyId` và secret mới, kiểm tra client đã chuyển, rút thời gian chấp nhận key cũ theo lịch; key bị lộ phải revoke ngay.
- **Revoke/block:** key revoked không được tạo principal dù MAC vẫn tính đúng. Nếu toàn client bị chặn, phải áp dụng cho cả key cũ lẫn key mới.
- **Audit:** lưu keyId/clientId đáng tin, request ID, policy version, reason nội bộ; không lưu secret, MAC đầy đủ hay body nhạy cảm trong log.
- **Authorization:** kiểm tra `orders:read` với GET và `orders:create` với POST; kiểm tra quyền tenant/resource độc lập nếu API có dữ liệu nhiều tổ chức.

### 7.3. Các mã phản hồi và hành vi lỗi

| Điều kiện | Hành vi mong đợi |
| --- | --- |
| Thiếu/không hợp lệ credential, MAC sai, timestamp quá cửa sổ, nonce trùng | Trả `401 Unauthorized` với thông điệp lỗi chung; không chạy nghiệp vụ |
| Đã xác thực nhưng thiếu scope/quyền resource hoặc bị đình chỉ | Trả `403 Forbidden`; ghi reason nội bộ |
| Vượt giới hạn tốc độ | `429 Too Many Requests` theo chính sách gateway/ứng dụng |
| Nonce store hoặc hệ thống xác minh trọng yếu không khả dụng | Từ chối xử lý request bảo vệ, trả mã lỗi hạ tầng phù hợp như `503`; không tự cho qua |
| Query hoặc header có cấu trúc sai | Trả mã lỗi thống nhất theo API contract (`400` hoặc `401`), tránh tiết lộ thông tin credential |

Tránh phân biệt công khai “key tồn tại nhưng secret sai” với “key không tồn tại”, vì có thể hỗ trợ dò danh sách khách hàng. Hệ thống vẫn cần audit reason cụ thể trong kênh nội bộ có quyền truy cập hạn chế.

## 8. Kế hoạch triển khai dự án theo milestone

### Milestone A — Khóa hợp đồng trước khi lập trình

Viết một trang đặc tả gồm phiên bản, header, thuật toán, 10 dòng canonical request, body digest, cách xử lý query/path, quy tắc sai định dạng, cửa sổ timestamp và chính sách nonce. Gắn golden vector từ mục 4. Một người chưa biết code phía client phải tái tạo được kết quả MAC.

**Điều kiện đạt:** Reviewer trả lời được 5 câu hỏi: body rỗng ký như thế nào; timestamp tính theo giây hay mili giây; query trùng xử lý ra sao; chuỗi có LF cuối không; thuật toán có bị client chọn tùy ý không.

### Milestone B — Client signer

Viết SDK tạo raw body bytes và query theo contract, sinh nonce mới, lấy timestamp từ clock, dựng canonical bytes, tính HMAC và đưa tag vào header. Không ký một đối tượng JSON rồi serialize lần nữa để gửi request.

**Điều kiện đạt:** SDK cho ra đúng chữ ký golden vector; trường hợp dữ liệu ngẫu nhiên có thể được verifier độc lập xác minh.

### Milestone C — Server verifier

Viết parser nghiêm ngặt, credential lookup, canonicalizer dùng dữ liệu **nhận thực**, so MAC byte, kiểm tra clock và claim nonce nguyên tử. Chạy trong filter/security chain trước controller; tạo principal gắn clientId/scopes khi thành công.

**Điều kiện đạt:** Không xử lý side effect khi MAC sai, replay, key revoked hoặc policy block client. Test 401/403 thể hiện rõ sự phân biệt xác thực và phân quyền.

### Milestone D — Gateway và kiểm thử liên hệ thống

Chạy thử qua tuyến client → gateway → backend. Ghi log có kiểm soát về profile và reason; xác nhận proxy không viết lại path, query hoặc body theo cách làm sai dữ liệu ký. Nếu gateway xác thực tập trung, chuyển principal đã được chứng thực tới backend và chặn header giả mạo từ Internet.

**Điều kiện đạt:** Cùng request cho ra cùng MAC qua HTTP/1.1, HTTP/2 và các instance/region theo điều kiện gateway hỗ trợ; hai request tranh chấp một nonce chỉ được một request chấp nhận.

### Milestone E — Vận hành và bảo trì

Tạo runbook key rotation, thu hồi, xử lý clock skew, theo dõi tỷ lệ `INVALID_MAC`, `REPLAY`, `KEY_REVOKED`, cảnh báo tăng lỗi sau thay đổi proxy. Xác định cách rollback mà vẫn giữ key revoked ở trạng thái revoked.

**Điều kiện đạt:** Có minh chứng tạo key mới, chuyển SDK, key cũ hết hiệu lực và phát hiện request đã ký bằng key cũ sau khi revoke.

## 9. Ma trận kiểm thử và tiêu chí nghiệm thu

| ID | Bài kiểm thử | Kết quả bắt buộc |
| --- | --- | --- |
| T01 | Golden vector GET ở mục 4 | MAC Base64 khớp chính xác |
| T02 | GET query thứ tự đảo ngược nhưng semantics giống | Cùng canonical query, verify thành công với signature tương ứng |
| T03 | Thay `GET` thành `POST`, giữ chữ ký | Bị từ chối |
| T04 | Đổi `/v1/orders` thành route khác | Bị từ chối hoặc route bị cấm theo grammar |
| T05 | Đổi `page=2` thành `page=200` | MAC sai |
| T06 | Thêm `id=1&id=2` hoặc `id=1&%69d=2` | Từ chối duplicate |
| T07 | Gửi `q=a+b`, escape malformed hoặc query UTF-8 lỗi | Từ chối trước nghiệp vụ |
| T08 | POST body bị đổi 1 byte so với lúc ký | MAC sai |
| T09 | POST Content-Type khác `application/json` | Từ chối theo contract |
| T10 | Thay timestamp hoặc nonce đã ký, giữ signature | MAC sai |
| T11 | MAC đúng, timestamp ngoài ±300 giây | Bị từ chối |
| T12 | Replay request đã chấp nhận với cùng nonce | Bị từ chối lần hai |
| T13 | Hai instance cùng nhận một nonce gần đồng thời | Một claim thành công, claim còn lại từ chối |
| T14 | Gửi hai header chữ ký/timestamp trùng | Từ chối; không lấy ngẫu nhiên giá trị đầu |
| T15 | Chữ ký Base64 sai dạng, sai padding hoặc tag ngắn | Từ chối |
| T16 | `keyId` không tồn tại hoặc revoked | Bị từ chối; không cấp principal |
| T17 | Key mới hoạt động khi key cũ đã revoked | Request mới hợp lệ; key cũ bị từ chối |
| T18 | Client có MAC hợp lệ nhưng thiếu `orders:create` | `403`; không tạo đơn |
| T19 | Client bị block với nhiều key còn hoạt động | Mọi key thuộc client bị từ chối |
| T20 | Proxy thay đổi representation path/query/body | Phát hiện mismatch hoặc cấu hình trust boundary đúng |
| T21 | Attacker tự gửi `X-Forwarded-Host`, `X-Original-URI` | Verifier không tin metadata từ nguồn không được cấu hình |
| T22 | Nonce store mất kết nối | Không xử lý API nhạy cảm; báo lỗi hạ tầng |
| T23 | Client gửi lại cùng giao dịch bằng request mới | Idempotency nghiệp vụ quyết định chống tạo đơn trùng |
| T24 | Key thuộc staging ký request production | Không xác thực nhờ tách audience/credential |
| T25 | Load test và request body lớn | Không vượt giới hạn bộ nhớ; bảo toàn body cho controller; đạt SLO đã định |

Ngoài bảng, chạy **fuzz/property-based tests** cho query, trường header, percent-encoding và Unicode: nếu hai query có canonical bytes giống nhau, verifier và handler phải thống nhất semantics; nếu không chứng minh được, phải từ chối dạng query đó.

Kiểm thử bảo mật không chỉ nhìn HTTP status; cần xác nhận **không có side effect**, key/secret không xuất hiện trong log và các metrics không chứa label cardinality cao từ keyId do bên ngoài tự khai.

## 10. Những lỗi thiết kế cần tránh khi bảo vệ đồ án

1. **Dùng `SHA256(secret + request)` như MAC.** Chọn primitive MAC tiêu chuẩn HMAC-SHA-256 và test vector độc lập.
2. **Ký `Map.toString()` của query hoặc JSON object.** Quyết định chính xác raw bytes và canonical encoding; không phụ thuộc thứ tự của map hay serializer.
3. **Bỏ query/body khỏi chữ ký để “sửa lỗi gateway”.** Điều này làm mất toàn vẹn của tham số nghiệp vụ; cần sửa canonical contract và xử lý proxy.
4. **Ký URL thấy ở client, verify URL đã rewrite mà không có trust boundary.** Xác định request-target hợp lệ tại verifier hoặc truyền metadata gốc được bảo vệ.
5. **Dùng `clientId` từ header làm principal khi chưa verify MAC.** Chỉ dùng keyId ban đầu để tra credential; tạo principal sau khi xác thực đủ.
6. **Chỉ so vài byte đầu của chữ ký hoặc so chữ ký bằng `String.equals`.** Decode Base64 nghiêm ngặt, yêu cầu đủ 32 byte và so MAC theo byte.
7. **Lưu nonce trong memory của từng pod.** Một request có thể replay ở pod khác. Sử dụng kho shared với insert nguyên tử.
8. **Lưu nonce TTL 300 giây dù clock window ±300.** Request có thể hợp lệ trong cửa sổ 600 giây từ sớm nhất đến muộn nhất. Chọn TTL đủ phủ cửa sổ và margin.
9. **Nhầm MAC hợp lệ với quyền truy cập.** Kiểm tra scope, tenant/resource và block policy sau khi đã tạo principal tin cậy.
10. **Dùng chung secret cho production và staging.** Tách key và audience, có vòng đời và thu hồi riêng.
11. **Cho phép fallback sang version/algorithm khác khi MAC sai.** Duy trì một profile hợp lệ theo chính sách credential, migration có phiên bản và ngày sunset.
12. **Log secret, raw Authorization/signature hoặc dữ liệu khách hàng.** Cần redaction, audit reason nội bộ và giữ quyền truy cập log tối thiểu.

## 11. Checklist bàn giao đồ án

- [ ] Có tài liệu signature scheme tự chứa, kèm version và danh sách thành phần được ký.
- [ ] Chốt được 10 dòng canonical, encoding UTF-8, LF và không có newline cuối.
- [ ] Đã triển khai client signer và verifier độc lập cho HMAC-SHA-256.
- [ ] Golden vector ở mục 4 khớp đúng cả MAC hex và Base64.
- [ ] Strict parser chặn duplicate header, query trùng, percent-encoding mơ hồ, path ngoài grammar.
- [ ] Body digest tính từ byte payload thực nhận; GET body rỗng và POST Content-Type tuân thủ profile.
- [ ] Timestamp ±300 giây và nonce claim nguyên tử dùng chung giữa instance; TTL phù hợp.
- [ ] Credential metadata có key ID, owner, profile, trạng thái và lịch rotate/revoke.
- [ ] HMAC authentication và business authorization được kiểm thử độc lập.
- [ ] Test chạy xuyên proxy/gateway, HTTP/1.1/HTTP/2 và các trường hợp key rotation.
- [ ] Không có side effect khi xác thực lỗi; secret và MAC không rò qua log hoặc response.
- [ ] Có runbook xử lý lỗi signature, replay, clock skew và sự cố lộ key.

### Gợi ý đánh giá

| Tiêu chí | Tỷ trọng gợi ý | Minh chứng |
| --- | ---: | --- |
| Giao thức rõ ràng, không mơ hồ | 30% | Đặc tả byte-level, canonicalization, header/parser |
| Xác thực và replay an toàn | 25% | MAC verification, timestamp, nonce store, revocation |
| Khả năng tích hợp đa môi trường | 20% | Vector, gateway/proxy, key rotation và test nhiều client |
| Kiểm thử và xử lý lỗi | 15% | Positive/negative matrix, no-side-effect, audit |
| Phân quyền và vận hành | 10% | Scopes, block policy, logs và incident runbook |

Bài thực hành kết thúc khi một nhóm có thể viết client mới **chỉ từ đặc tả** và tạo chữ ký trùng với verifier; một request thay đổi ý nghĩa nghiệp vụ phải bị từ chối hoặc tạo MAC khác, replay phải bị ngăn và quyền truy cập vẫn được kiểm tra độc lập. Đó là thước đo của một signature scheme triển khai được trong thực tế, không chỉ là đoạn code gọi `Mac.getInstance("HmacSHA256")`.
