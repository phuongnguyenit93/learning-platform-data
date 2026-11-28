# Unicode path trong canonical HTTP request dùng HMAC

**Unicode path** là đường dẫn URL có thành phần tên chứa ký tự ngoài ASCII, chẳng hạn `/v1/profiles/café`, `/v1/khach-hang/Đà-Nẵng` hoặc tên tài liệu viết bằng tiếng Nhật. Khi dùng **HMAC request authentication**, vấn đề không chỉ là hiển thị đúng ký tự: **client và verifier phải ký cùng chính xác dãy byte của đường dẫn** mà router/backend thực sự xử lý.

Bài thuộc chương **URL và path** của module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Module này xây dựng cơ chế xác thực HTTP request dùng shared secret và canonical request chứa method, URI, header và/hoặc body theo hợp đồng ký. Chủ đề trực tiếp là **Unicode path**: cách chuyển Unicode thành byte UTF-8, percent-encode để truyền qua HTTP, quyết định có/không chuẩn hóa NFC, bảo vệ raw path khỏi thay đổi bởi proxy/gateway, và liên kết việc xác minh URI với timestamp/nonce, key rotation và phân quyền.

**Thông điệp trọng tâm:** Hai path có thể **trông giống nhau**, hoặc cùng được ứng dụng diễn giải thành một tên, nhưng có **byte khác nhau**. HMAC không biết “ý nghĩa của Unicode”; nó chỉ xác thực byte của canonical request. Cần thiết kế **một biểu diễn hợp lệ duy nhất** hoặc từ chối các biểu diễn mơ hồ, thay vì để signer, verifier và router tự suy đoán.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt ký tự Unicode, mã điểm (code point), byte UTF-8, URL percent-encoding, raw path và decoded path.
2. Giải thích khác biệt giữa Unicode NFC/NFD, mã hóa `%C3%A9` và `e%CC%81`, cũng như trường hợp `%2F`, `%252F` và dấu `+`.
3. Thiết kế một hợp đồng canonical path có chính sách Unicode/percent-encoding rõ ràng, được thực thi nhất quán tại signer, verifier và router.
4. Tạo Java 17 client ký request bằng HMAC-SHA256 trên method, raw target, signed headers và body digest; kiểm tra Unicode path bằng parser chặt chẽ.
5. Kiểm thử lỗi reverse proxy, HTTP/1.1 ↔ HTTP/2, gateway rewrite, double decoding, path traversal, Unicode confusables và replay.
6. Giải thích vì sao HMAC hợp lệ **không** thay thế kiểm tra key scope, tenant, tài nguyên và authorization.

## 2. Path trong HTTP request là gì?

Xét một API trả thông tin hồ sơ có tên hiển thị “café”:

~~~text
URL dùng trong trình duyệt (dạng dễ đọc):
https://api.example.test/v1/profiles/café?include=orders

Request target đã percent-encode UTF-8:
/v1/profiles/caf%C3%A9?include=orders
~~~

Ví dụ HTTP/1.1:

~~~http
GET /v1/profiles/caf%C3%A9?include=orders HTTP/1.1
Host: api.example.test
X-Client-Id: partner-42
X-Timestamp: {epoch-seconds}
X-Nonce: {random-nonce}
X-Signature: {hmac-tag}
~~~

Trong HTTP/2 hoặc HTTP/3, method và request target được biểu diễn qua các pseudo-header tương ứng, chẳng hạn:

~~~text
:method: GET
:scheme: https
:authority: api.example.test
:path: /v1/profiles/caf%C3%A9?include=orders
~~~

Các khái niệm cần phân biệt:

| Khái niệm | Ví dụ | Vai trò với chữ ký |
| --- | --- | --- |
| **Unicode text** | `café` | Dữ liệu ứng dụng muốn hiển thị hoặc định danh. |
| **UTF-8 bytes** | `63 61 66 C3 A9` | Byte của chuỗi `café` theo một cách biểu diễn Unicode. |
| **Percent-encoded path segment** | `caf%C3%A9` | Biểu diễn ASCII trên URI cho byte ngoài tập unreserved. |
| **Raw path** | `/v1/profiles/caf%C3%A9` | Đầu vào có thể đưa trực tiếp vào canonical request nếu contract chọn raw form. |
| **Decoded path** | `/v1/profiles/café` | Chuỗi sau bước percent-decode UTF-8; có thể đã mất thông tin về biểu diễn URI ban đầu. |
| **Raw query** | `include=orders` | Phần sau dấu `?`, không thuộc path nhưng thường cũng phải được ký. |
| **Authority** | `api.example.test` | Host/port dịch vụ; cần bảo vệ hoặc ràng buộc audience theo chính sách riêng. |

URL đầy đủ có thể chứa scheme, authority, path, query và fragment. **Fragment** (phần sau `#`) không được gửi như một phần của HTTP request target thông thường, do đó không thể xem fragment trong URL của trình duyệt là dữ liệu đã được HMAC bảo vệ theo hợp đồng ký request target.

Path dùng ký **không phải** tên thư mục trong hệ điều hành và không nhất thiết giống giá trị `getPath()` mà framework trả về sau nhiều bước decode/normalize. Với hệ thống có reverse proxy, cần xác định rõ **ở hop nào lấy path** và liệu backend có đang thực thi trên chính path đó hay không.

## 3. Unicode, UTF-8 và percent-encoding

### 3.1. Chuyển ký tự thành byte

Một ký tự nhìn thấy được có thể gồm một hoặc nhiều Unicode code point. Với `é` ở dạng dựng sẵn (precomposed), UTF-8 có hai byte `C3 A9`. Khi nằm trong URI ASCII, hai byte được percent-encode thành `%C3%A9`:

~~~text
Chuỗi Unicode NFC: "café"
Code points: U+0063 U+0061 U+0066 U+00E9
UTF-8:       63 61 66 C3 A9
URI segment: caf%C3%A9
~~~

Một chuỗi khác có thể hiển thị gần như tương tự:

~~~text
Chuỗi Unicode dạng phân rã: "cafe" + combining acute accent
Code points: U+0063 U+0061 U+0066 U+0065 U+0301
UTF-8:       63 61 66 65 CC 81
URI segment: cafe%CC%81
~~~

Hai dãy byte **khác nhau**. Cùng nhìn giống “café” không đồng nghĩa hai URI có cùng biểu diễn. Một verifier băm raw URI sẽ tạo HMAC khác cho hai chuỗi này, nếu mọi phần còn lại giống nhau.

### 3.2. NFC và NFD không phải cùng một dãy byte

**Unicode normalization** có các dạng như NFC (Normalization Form C) và NFD (Normalization Form D):

- **NFC** thường dùng thành phần ký tự đã ghép khi có thể, ví dụ `U+00E9` cho `é`.
- **NFD** biểu diễn theo chuỗi phân rã, ví dụ `U+0065 U+0301`.
- Normalization giúp thống nhất các chuỗi **tương đương theo Unicode**, nhưng không giải quyết toàn bộ ký tự **giống hình** hoặc cùng ý nghĩa trong nghiệp vụ.

Một API có thể chọn:

1. **Ký raw URI nguyên vẹn** và xem mọi khác biệt byte là khác nhau. Client/verifier vẫn phải đồng ý điểm capture và router phải xử lý khớp với URI đã ký.
2. **Yêu cầu biểu diễn canonical duy nhất**, ví dụ normalize text của từng path segment sang NFC **trước percent-encode**, sau đó signer tạo URI chuẩn và verifier **từ chối** mọi raw URI không đúng form đó.

Trong bài này dùng **cách 2** cho một path segment định danh cụ thể, nhằm thực hành hợp đồng chặt chẽ. Không tự suy ra rằng mọi giao thức ký HTTP khác cũng phải normalize NFC; nhiều giao thức yêu cầu giữ nguyên raw request target theo quy tắc riêng.

### 3.3. Percent-encoding có phân biệt hoa/thường ở byte biểu diễn

Hex trong percent escape không cần phân biệt chữ hoa/thường để đại diện byte:

~~~text
%C3%A9 và %c3%a9   -> cùng hai byte C3 A9 sau percent-decode
~~~

Tuy nhiên, **raw URI text khác nhau**. Nếu hợp đồng ký trên raw request target, `%C3%A9` và `%c3%a9` cho **canonical bytes khác nhau**. Hợp đồng mẫu ở đây yêu cầu **hex chữ hoa A–F trong percent escape**, từ chối chữ thường ở escape thay vì âm thầm đổi representation khi verify.

Tương tự, percent-encode một byte unreserved vốn có thể viết trực tiếp thường làm URL vẫn có cùng ý nghĩa sau decode:

~~~text
A     và %41       -> cùng chữ A nếu được decode một lần
~     và %7E       -> cùng byte 7E nếu được decode
~~~

Để tránh nhiều representation, hợp đồng mẫu **bắt buộc ký tự unreserved dùng ASCII trực tiếp**, còn byte ngoài unreserved được percent-encode với hex chữ hoa.

## 4. Những trường hợp path nguy hiểm hơn việc “khác chữ có dấu”

| Cặp hoặc dạng URI | Vì sao cần cảnh giác? | Chính sách nên cân nhắc |
| --- | --- | --- |
| `caf%C3%A9` / `cafe%CC%81` | NFC/NFD khác byte; router có thể chuẩn hóa một phía | Chọn NFC cố định rồi reject raw segment không canonical. |
| `%C3%A9` / `%c3%a9` | Percent escape khác text dù giải mã cùng byte | Quy định chữ hoa A–F, reject escape không chuẩn. |
| `A` / `%41` | Unreserved encoded vs unencoded | Không cho percent-encode unreserved trong contract mẫu. |
| `/a/b` / `/a%2Fb` | Encoded slash có thể bị một hop decode thành dấu phân tách segment | Reject encoded slash trong segment ID, hoặc có protocol định nghĩa chặt cách route. |
| `%5C` | Backslash có thể được một số stack coi như separator | Reject trong segment định danh nếu không có lý do cần. |
| `%252F` | Double encoding của `%2F`; decode hai lần có thể sinh dấu `/` | Không cho percent ký tự dữ liệu trong segment ID ở policy mẫu; không double-decode. |
| `/a/./b`, `/a/../b` | Dot segments có thể được proxy/URI library làm gọn khác nhau | Reject dot segments và đường dẫn đã normalize không nhất quán. |
| `//` hoặc dấu slash cuối | Một số router gộp slash hay tự redirect | Chọn một route representation, reject hoặc chuyển hướng trước signing với contract rõ. |
| `+` / `%20` trong path | Dấu cộng **không** mặc định có nghĩa space trong path như form query | Percent-encode space và plus theo quy tắc từng segment; không dùng form encoder cho path. |
| Byte UTF-8 không hợp lệ | Decoder có thể thay bằng ký tự `U+FFFD`, tạo nhiều input thành cùng text | Dùng decoder strict, reject byte invalid/malformed. |
| Unicode bidi control/confusable | Ký tự hiển thị gây hiểu nhầm định danh, log hoặc quyền truy cập | Chính sách identifier riêng; NFC không ngăn homograph, phải kiểm tra quyền trên resource ID chuẩn. |

**Đặc biệt:** `%2F` là byte “/” được encode. Nếu signer nghĩ đó là dữ liệu *bên trong một segment* nhưng backend decode trước khi route, một path có thể đổi từ `/v1/files/a%2Fb` thành `/v1/files/a/b`. HMAC vẫn có thể hợp lệ đối với raw URI đã ký, nhưng **server có thể xử lý tài nguyên khác** nếu route trên dạng đã decode không khớp hợp đồng. Vì vậy phải phối hợp **ký và routing**, không chỉ tính hash.

**Path traversal:** Chuỗi `..` và các dạng percent-encoded/double-encoded có thể được một tầng xử lý coi là di chuyển lên thư mục cha. Không nên dùng path URL chưa được kiểm soát để trực tiếp ghép thành đường dẫn filesystem. HMAC bảo vệ input đã ký, **không biến một input nguy hiểm thành an toàn** nếu client có key và gửi traversal hợp lệ theo chữ ký.

## 5. Hợp đồng canonical Unicode path cho API minh họa

API mẫu cho phép truy xuất/tạo thông tin profile bằng một **segment định danh Unicode** (để thực hành; ở hệ thống nhạy cảm, ID ASCII bất biến thường dễ quản lý hơn tên hiển thị).

Hợp đồng **HMAC-UNICODE-PATH-V1** định nghĩa:

| Quy tắc | Giá trị của bài |
| --- | --- |
| HTTP method | `POST` chữ hoa chính xác. |
| Path prefix | `/v1/profiles/`, không có slash cuối sau ID. |
| Unicode identifier | Normalize **NFC** tại signer, rồi encode UTF-8 strict. |
| Percent encoding | ASCII unreserved `A–Z a–z 0–9 - . _ ~` giữ nguyên; các byte còn lại dùng `%HH` hex **chữ hoa**. |
| Identifier không hợp lệ | Segment rỗng, `.`, `..`, slash, backslash, dấu phần trăm dữ liệu, `?`, `#`, control/format code point theo chính sách ví dụ. |
| Raw query | Chỉ `?include=orders`; không reorder/decode/re-encode. |
| Signed headers | Client ID, key ID, timestamp, nonce, Content-Type. |
| Body | SHA-256 trên **byte[] UTF-8 thực gửi**; digest 64 hex chữ thường. |
| Audience | `profiles-api` từ cấu hình verifier, không từ forwarded header tùy ý. |
| HMAC | `HmacSHA256` với shared secret, tag đầy đủ 32 byte, Base64 chuẩn có padding. |
| Canonical format | Các dòng nối bằng **LF byte 0A**, không có LF cuối, mã hóa UTF-8. |

Ví dụ client nhận tên `cafe` + combining acute accent, normalize thành `café` NFC rồi tạo request target chính tắc:

~~~text
/v1/profiles/caf%C3%A9?include=orders
~~~

Canonical request:

~~~text
HMAC-UNICODE-PATH-V1
POST
/v1/profiles/caf%C3%A9?include=orders
audience:profiles-api
x-client-id:partner-42
x-key-id:key-2026-11
x-timestamp:<unix-epoch-seconds>
x-nonce:<32-lowercase-hex-characters>
content-type:application/json
x-content-sha256:<64-lowercase-hex-characters>
~~~

Các giá trị trong dấu `<...>` là placeholder. Khi ký request thật, các dòng chứa **giá trị cụ thể** đã kiểm tra. Các phép tính:

~~~text
identifierNFC = NormalizeNFC(identifierUnicode)
encodedId     = PercentEncodeUpperHex(UTF8Strict(identifierNFC))
rawTarget     = "/v1/profiles/" + encodedId + "?include=orders"
bodyHash      = lowerHex(SHA256(actualBodyBytes))
canonical     = JoinWithLF(contractVersion, method, rawTarget, signedFields...)
signature     = Base64(HMAC_SHA256(sharedSecret, UTF8(canonical)))
~~~

**Không có bước server tự “sửa” raw target trước khi xác minh.** Verifier cần **parse nghiêm ngặt** raw target, xác nhận nó đã đúng canonical form, sau đó dùng **chính raw target đã chấp nhận** để dựng canonical HMAC. Router phải xử lý theo cùng phân đoạn/giá trị resource đã được kiểm tra. Nếu raw target không đúng quy tắc, **reject** thay vì tính HMAC trên URI đã normalize rồi route trên URI ban đầu.

### 5.1. Nếu hợp đồng muốn ký raw URI mà không normalize NFC

Đó cũng là một thiết kế có thể dùng, nhưng signer và verifier phải thống nhất rằng `caf%C3%A9` và `cafe%CC%81` là **hai dãy byte khác nhau** và ứng dụng không được route hai biểu diễn vào các tài nguyên khác nhau theo cách làm sai lệch authorization. Chọn NFC trong bài là **một quyết định thiết kế được ghi rõ**, không phải bước mọi verifier HMAC được phép thực hiện tùy tiện.

### 5.2. Phân biệt path và query

`?` bắt đầu query, không thuộc path. Ví dụ:

~~~text
/v1/profiles/caf%C3%A9?include=orders

raw path  = /v1/profiles/caf%C3%A9
raw query = include=orders
~~~

Nếu backend dùng query để quyết định thông tin trả về hoặc thao tác, phải ký cả query. Không được chỉ ký path rồi để proxy tự đổi `include=orders` thành tham số có quyền cao hơn. Query có các quy tắc escaping/duplicate riêng; không được áp dụng mù quáng quy tắc path segment cho `application/x-www-form-urlencoded`, nhất là dấu `+`, `%20` và tham số trùng.

## 6. Java 17: Unicode path encoder và verifier nghiêm ngặt

Ví dụ sau cho phép client nhận một tên Unicode, chuẩn hóa NFC, tạo **path segment dạng ASCII percent-encoded**, đưa raw target vào canonical HMAC và mô phỏng verifier trên request thực nhận. Code sử dụng:

- `Normalizer.Form.NFC` để xử lý các dạng Unicode tương đương.
- `CharsetEncoder`/`CharsetDecoder` có `CodingErrorAction.REPORT` để từ chối Unicode/UTF-8 lỗi thay vì âm thầm thay byte.
- `URI.getRawPath()` và `URI.getRawQuery()` để lấy biểu diễn encoded; **không** dùng `getPath()` cho hợp đồng ký raw URI.
- `MessageDigest` cho SHA-256 body, `Mac` cho HMAC-SHA256 và `MessageDigest.isEqual` để so sánh tag.
- `SecureRandom` sinh nonce 16 byte; `Clock` giúp test thời gian cố định.

Code **không gửi request ra mạng** và sử dụng secret test sinh ngay trong chương trình. Một verifier production cần parser HTTP/gateway thực tế, key store, nonce store nguyên tử có TTL và authorization riêng.

~~~java
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.text.Normalizer;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class UnicodePathHmacExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String PREFIX = "/v1/profiles/";
    private static final String QUERY = "include=orders";
    private static final String CLIENT_ID = "partner-42";
    private static final String KEY_ID = "key-2026-11";
    private static final String CONTENT_TYPE = "application/json";
    private static final String HEX = "0123456789ABCDEF";

    record SignedRequest(
        String method, String rawTarget, String clientId, String keyId,
        String timestamp, String nonce, String bodyHash,
        String signature, byte[] body
    ) {}

    // Demo trong một JVM: không có TTL và không dùng chung giữa replica.
    static final class DemoNonceStore {
        private final Set<String> seen = ConcurrentHashMap.newKeySet();

        boolean claim(String clientId, String nonce) {
            return seen.add(clientId + ":" + nonce);
        }
    }

    static boolean unreserved(int b) {
        return (b >= 'A' && b <= 'Z') ||
               (b >= 'a' && b <= 'z') ||
               (b >= '0' && b <= '9') ||
               b == '-' || b == '.' || b == '_' || b == '~';
    }

    static void validateIdentifier(String text) {
        if (text.isEmpty() || text.equals(".") || text.equals("..")) {
            throw new IllegalArgumentException("ID rỗng hoặc dot segment");
        }
        // Chính sách dành riêng cho ID của endpoint minh họa.
        for (int cp : text.codePoints().toArray()) {
            if (cp == '/' || cp == '\\' || cp == '%' ||
                cp == '?' || cp == '#' ||
                Character.isISOControl(cp) ||
                Character.getType(cp) == Character.FORMAT) {
                throw new IllegalArgumentException(
                    "Ký tự không được phép trong profile ID"
                );
            }
        }
    }

    static String encodeSegmentNfc(String input)
            throws CharacterCodingException {
        String normalized = Normalizer.normalize(
            input, Normalizer.Form.NFC
        );
        validateIdentifier(normalized);

        ByteBuffer utf8 = StandardCharsets.UTF_8.newEncoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .encode(CharBuffer.wrap(normalized));
        StringBuilder out = new StringBuilder();
        while (utf8.hasRemaining()) {
            int b = utf8.get() & 0xff;
            if (unreserved(b)) {
                out.append((char) b);
            } else {
                out.append('%')
                   .append(HEX.charAt(b >>> 4))
                   .append(HEX.charAt(b & 15));
            }
        }
        return out.toString();
    }

    static boolean upperHex(char ch) {
        return (ch >= '0' && ch <= '9') ||
               (ch >= 'A' && ch <= 'F');
    }

    static String decodeCanonicalSegment(String raw)
            throws CharacterCodingException {
        if (raw == null || raw.isEmpty() || raw.length() > 256) {
            throw new IllegalArgumentException("Segment rỗng/quá dài");
        }
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        for (int i = 0; i < raw.length(); i++) {
            char ch = raw.charAt(i);
            if (ch == '%') {
                if (i + 2 >= raw.length() ||
                    !upperHex(raw.charAt(i + 1)) ||
                    !upperHex(raw.charAt(i + 2))) {
                    throw new IllegalArgumentException(
                        "Percent escape không canonical"
                    );
                }
                int hi = Character.digit(raw.charAt(i + 1), 16);
                int lo = Character.digit(raw.charAt(i + 2), 16);
                bytes.write((hi << 4) | lo);
                i += 2;
            } else if (ch <= 127 && unreserved(ch)) {
                bytes.write((byte) ch);
            } else {
                throw new IllegalArgumentException(
                    "Raw segment chứa byte/ký tự không hợp đồng"
                );
            }
        }

        String decoded = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes.toByteArray()))
            .toString();

        validateIdentifier(decoded);
        if (!Normalizer.isNormalized(decoded, Normalizer.Form.NFC) ||
            !raw.equals(encodeSegmentNfc(decoded))) {
            throw new IllegalArgumentException(
                "Path phải ở dạng NFC + percent encoding canonical"
            );
        }
        return decoded;
    }

    static boolean canonicalTarget(String rawTarget) {
        String suffix = "?" + QUERY;
        if (rawTarget == null ||
            !rawTarget.startsWith(PREFIX) ||
            !rawTarget.endsWith(suffix)) {
            return false;
        }
        String encoded = rawTarget.substring(
            PREFIX.length(), rawTarget.length() - suffix.length()
        );
        try {
            decodeCanonicalSegment(encoded);
            return true;
        } catch (IllegalArgumentException | CharacterCodingException bad) {
            return false;
        }
    }

    static String sha256Hex(byte[] body)
            throws GeneralSecurityException {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(body);
        return HexFormat.of().formatHex(digest); // hex chữ thường
    }

    static byte[] hmac(byte[] key, String canonical)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8));
    }

    static String canonical(String method, String rawTarget,
            String clientId, String keyId, String timestamp,
            String nonce, String bodyHash) {
        if (!"POST".equals(method) || !canonicalTarget(rawTarget) ||
            !CLIENT_ID.equals(clientId) || !KEY_ID.equals(keyId) ||
            timestamp == null ||
            !timestamp.matches("[1-9][0-9]{0,18}") ||
            nonce == null || !nonce.matches("[0-9a-f]{32}") ||
            bodyHash == null || !bodyHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Canonical request sai format");
        }
        return String.join("\n",
            "HMAC-UNICODE-PATH-V1",
            method,
            rawTarget,  // Giữ đúng raw bytes/ASCII representation đã kiểm tra.
            "audience:profiles-api",
            "x-client-id:" + clientId,
            "x-key-id:" + keyId,
            "x-timestamp:" + timestamp,
            "x-nonce:" + nonce,
            "content-type:" + CONTENT_TYPE,
            "x-content-sha256:" + bodyHash
        );
    }

    static SignedRequest sign(byte[] key, Clock clientClock)
            throws Exception {
        // Input có 'e' và combining acute accent (NFD-like).
        String profileName = "cafe\u0301";
        String encodedId = encodeSegmentNfc(profileName); // caf%C3%A9
        String rawTarget = PREFIX + encodedId + "?" + QUERY;
        byte[] body = "{\"status\":\"active\"}"
            .getBytes(StandardCharsets.UTF_8);

        byte[] nonceBytes = new byte[16];
        RANDOM.nextBytes(nonceBytes);
        String nonce = HexFormat.of().formatHex(nonceBytes);
        String timestamp = Long.toString(
            clientClock.instant().getEpochSecond()
        );
        String bodyHash = sha256Hex(body);
        String requestToSign = canonical(
            "POST", rawTarget, CLIENT_ID, KEY_ID,
            timestamp, nonce, bodyHash
        );
        String signature = Base64.getEncoder().encodeToString(
            hmac(key, requestToSign)
        );
        return new SignedRequest(
            "POST", rawTarget, CLIENT_ID, KEY_ID,
            timestamp, nonce, bodyHash, signature, body
        );
    }

    static boolean verify(SignedRequest request, byte[] key,
            Clock serverClock, DemoNonceStore replayStore)
            throws GeneralSecurityException {
        if (request == null || request.body() == null ||
            request.signature() == null) {
            return false;
        }
        final String expectedCanonical;
        try {
            String computedBodyHash = sha256Hex(request.body());
            if (!computedBodyHash.equals(request.bodyHash())) {
                return false;
            }
            expectedCanonical = canonical(
                request.method(), request.rawTarget(),
                request.clientId(), request.keyId(),
                request.timestamp(), request.nonce(), computedBodyHash
            );
        } catch (IllegalArgumentException badFormat) {
            return false;
        }

        final long timestamp;
        try {
            timestamp = Long.parseLong(request.timestamp());
        } catch (NumberFormatException invalidNumber) {
            return false;
        }
        long now = serverClock.instant().getEpochSecond();
        if (timestamp < now - 300 || timestamp > now + 60) {
            return false;
        }

        final byte[] suppliedTag;
        try {
            suppliedTag = Base64.getDecoder().decode(request.signature());
        } catch (IllegalArgumentException invalidBase64) {
            return false;
        }
        if (suppliedTag.length != 32 ||
            !Base64.getEncoder().encodeToString(suppliedTag)
                .equals(request.signature())) {
            return false;
        }

        byte[] expectedTag = hmac(key, expectedCanonical);
        if (!MessageDigest.isEqual(expectedTag, suppliedTag)) {
            return false;
        }
        // Chỉ claim sau HMAC; production dùng atomic store chung có TTL.
        return replayStore.claim(request.clientId(), request.nonce());
    }

    public static void main(String[] args) throws Exception {
        byte[] secret = new byte[32];
        RANDOM.nextBytes(secret); // Key demo, không dùng cho production.
        Clock fixed = Clock.fixed(
            Instant.parse("2026-11-28T02:00:00Z"), ZoneOffset.UTC
        );
        SignedRequest request = sign(secret, fixed);
        String expectedTarget = "/v1/profiles/caf%C3%A9?include=orders";
        if (!expectedTarget.equals(request.rawTarget())) {
            throw new AssertionError("NFC percent-encode sai");
        }

        URI uri = URI.create(
            "https://api.example.test" + request.rawTarget()
        );
        String fromUri = uri.getRawPath() + "?" + uri.getRawQuery();
        if (!request.rawTarget().equals(fromUri)) {
            throw new AssertionError("Raw URI ở client không trùng");
        }
        HttpRequest httpRequest = HttpRequest.newBuilder(uri)
            .header("Content-Type", CONTENT_TYPE)
            .header("X-Client-Id", request.clientId())
            .header("X-Key-Id", request.keyId())
            .header("X-Timestamp", request.timestamp())
            .header("X-Nonce", request.nonce())
            .header("X-Content-SHA256", request.bodyHash())
            .header("X-Signature", request.signature())
            .POST(HttpRequest.BodyPublishers.ofByteArray(request.body()))
            .build();

        if (!verify(request, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Request chuẩn phải hợp lệ");
        }
        DemoNonceStore replay = new DemoNonceStore();
        if (!verify(request, secret, fixed, replay) ||
            verify(request, secret, fixed, replay)) {
            throw new AssertionError("Replay phải bị từ chối");
        }

        SignedRequest lowercaseEscapes = new SignedRequest(
            request.method(),
            request.rawTarget().replace("%C3%A9", "%c3%a9"),
            request.clientId(), request.keyId(),
            request.timestamp(), request.nonce(),
            request.bodyHash(), request.signature(), request.body()
        );
        if (verify(lowercaseEscapes, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Percent escape chữ thường phải bị từ chối");
        }
        SignedRequest nfdPath = new SignedRequest(
            request.method(),
            request.rawTarget().replace("caf%C3%A9", "cafe%CC%81"),
            request.clientId(), request.keyId(),
            request.timestamp(), request.nonce(),
            request.bodyHash(), request.signature(), request.body()
        );
        if (verify(nfdPath, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("NFD path phải bị từ chối theo contract");
        }

        if (canonicalTarget("/v1/profiles/a%2Fb?include=orders") ||
            canonicalTarget("/v1/profiles/a%252Fb?include=orders")) {
            throw new AssertionError("Encoded/double-encoded slash phải bị chặn");
        }
        System.out.println("PASS: " + httpRequest.method()
            + " " + request.rawTarget() + ", HMAC, replay, Unicode");
    }
}
~~~

### 6.1. Vì sao đoạn mã cố tình tách encoder và decoder?

**Client** làm việc với Unicode text từ ứng dụng, normalize **NFC** rồi encode ra một segment trên URI. **Verifier** làm việc với **raw URI có thật** sau khi HTTP stack nhận request: nó decode UTF-8 bằng chế độ **REPORT**, reject input không hợp lệ, kiểm tra NFC và **encode lại chỉ để so sánh** với raw segment. Nếu raw input không có đúng một biểu diễn canonical, nó bị từ chối.

Quan trọng là verifier **không dùng giá trị encode lại thay thế raw URI rồi âm thầm chấp nhận**. Nó chỉ xác minh tính canonical của raw URI, sau đó dùng **chính raw target ban đầu đã kiểm tra** để tính HMAC. Như vậy một proxy đổi `%C3%A9` thành `%c3%a9` hoặc đổi NFC thành NFD sẽ gây từ chối theo hợp đồng, kể cả hai cách biểu diễn có thể tương đương sau decode.

### 6.2. Giới hạn cố ý của ví dụ

- `SignedRequest` mô phỏng dữ liệu server nhận, **không phải HTTP parser bảo mật**. Trong hệ thống thật phải lấy method, request target, signed headers và body từ thành phần server/gateway **đáng tin**, chặn header trùng, request smuggling và path ambiguity trước khi verify.
- `canonicalTarget` chỉ hỗ trợ một route với **một segment** và query cố định. Một router thực cần chính sách riêng cho mọi route/segment; không thể dùng hàm này như thư viện URL parser đầy đủ.
- Decoder minh họa giới hạn **256 ký tự raw segment** trước khi cấp phát và decode; ứng dụng thật còn phải giới hạn **toàn bộ URI, header và body** ngay tại ingress theo ngân sách tài nguyên của hệ thống.
- `validateIdentifier` cố tình cấm control/format code point, encoded slash, percent và một số ký tự dành riêng để bảo vệ **identifier** của endpoint minh họa. Đây **không phải** tập ký tự bắt buộc cho mọi Unicode path; những ứng dụng đa ngôn ngữ cần policy phù hợp với dữ liệu thực tế.
- `DemoNonceStore` chỉ có tính nguyên tử trong một JVM, không TTL, không chia sẻ giữa các replica. Production cần shared atomic nonce store với expiry phù hợp timestamp window.
- `CLIENT_ID`/`KEY_ID` được cố định để ví dụ rõ. Production tra secret từ key store theo đúng client ID/key ID và kiểm tra key active, algorithm, audience, thời hạn/rotation.
- Chương trình chỉ tạo `HttpRequest` để minh họa; không gửi thực sự qua proxy. Cần integration test để bảo đảm byte/request target được HTTP client phát ra phù hợp với giá trị `getRawPath()` đã ký.

## 7. Java URI: getRawPath khác getPath như thế nào?

Với URI tạo từ:

~~~java
URI uri = URI.create(
    "https://api.example.test/v1/profiles/caf%C3%A9?include=orders"
);
System.out.println(uri.getRawPath());  // /v1/profiles/caf%C3%A9
System.out.println(uri.getPath());     // /v1/profiles/café
System.out.println(uri.getRawQuery()); // include=orders
~~~

`getRawPath()` giữ representation percent-encoded, còn `getPath()` trả path đã decode. Với hợp đồng **ký raw request target**, ký `getPath()` là sai dãy byte: chữ `é` có byte UTF-8 `C3 A9`, trong khi URI gửi `%C3%A9` dưới dạng ASCII `25 43 33 25 41 39`.

Trường hợp ngược lại cũng đáng chú ý:

~~~java
URI uri = URI.create("https://api.example.test/v1/profiles/cafe%CC%81");
System.out.println(uri.getRawPath()); // /v1/profiles/cafe%CC%81
System.out.println(uri.getPath());    // có ký tự combining accent
~~~

Nếu server đọc decoded path rồi normalize NFC, nó có thể thu được một chuỗi **trông giống** biểu diễn đầu tiên và đánh mất bằng chứng rằng trên dây đã có NFD. Nếu hợp đồng ký yêu cầu **raw URL**, phải capture raw target trước những phép biến đổi không thể đảo ngược này.

### 7.1. Những lỗi thao tác URI trong Java

| Cách làm | Vấn đề | Cách phù hợp |
| --- | --- | --- |
| `uri.getPath()` để ký raw target | Path đã percent-decode | Dùng raw path/query được HTTP stack bảo toàn theo contract. |
| `URLDecoder.decode(path, UTF_8)` | URLDecoder dành cho form-style encoding, có thể hiểu `+` thành space | Không dùng nó để tùy tiện chuẩn hóa path; chọn parser percent-encoding dành cho URI path. |
| Xây URI từ thành phần đã percent-encode rồi lại dùng constructor encode component | Có thể biến `%` thành `%25` (double encode) | Chọn một điểm encode, kiểm tra raw target sau khi build. |
| Gọi `uri.normalize()` mà không thống nhất hợp đồng | Có thể thay cấu trúc dot segments | Reject input mơ hồ hoặc normalize có kiểm soát **trước khi ký** với mapping giống router. |
| Percent-decode bằng charset mặc định | Unicode sinh ra khác nhau giữa client/server | Dùng **UTF-8 strict**, xử lý invalid byte bằng reject. |
| Re-serialize JSON/body rồi ký cùng URL | Có thể sửa body bytes dù URI đúng | Hash body bytes thực gửi, ràng buộc digest trong HMAC. |

### 7.2. Chọn ID bất biến hay tên Unicode trong path?

Nếu endpoint quyết định quyền theo resource, nên cân nhắc dùng **opaque resource ID** bất biến (ví dụ UUID/ULID đã kiểm tra format) thay vì tên người/tên tài liệu có thể đổi, có bí danh hoặc có ký tự nhìn giống nhau. Unicode path vẫn hợp lệ trong nhiều ứng dụng, nhưng **Unicode normalization không giải quyết homograph/confusable**: chữ Latin `a` và một ký tự trông gần giống từ bảng chữ khác có thể đại diện hai tài nguyên khác nhau.

Vì vậy sau khi verify HMAC và parse identifier, hệ thống phải tra đúng **resource ID nội bộ** rồi kiểm tra **authorization**. Không xác định quyền chỉ bằng việc so sánh tên hiển thị nhìn giống nhau.

## 8. Proxy/gateway và ranh giới tin cậy của Unicode path

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy không tin cậy
    participant G as Gateway đáng tin
    participant V as HMAC verifier
    participant R as Router/backend
    C->>P: POST /v1/profiles/caf%C3%A9 + HMAC
    P->>G: Chuyển tiếp; có thể sửa percent-encoding
    G->>V: Raw target đã giữ đúng tại trust boundary
    V->>V: Validate canonical Unicode path và HMAC
    alt Raw target + HMAC hợp lệ, nonce mới
        V->>R: Route theo path đã xác minh
        R->>R: Kiểm tra authorization theo resource ID
    else Path bị đổi hoặc biểu diễn mơ hồ
        V-->>C: Từ chối request
    end
~~~

Những phép biến đổi có thể làm mất sự nhất quán:

| Tình huống | Hậu quả | Thiết kế phòng vệ |
| --- | --- | --- |
| Proxy đổi `%C3%A9` thành `%c3%a9` | Raw URI đổi, dù byte sau decode giống nhau | Hợp đồng kiểm tra percent escape chữ hoa; reject representation khác. |
| Proxy đổi `caf%C3%A9` thành `cafe%CC%81` | NFC thành NFD, raw path khác | Reject path không NFC canonical theo contract bài này. |
| Gateway decode `%2F` thành `/` trước verify | Một segment có thể thành hai segment | Từ chối encoded separator từ đầu, verify tại boundary giữ raw target. |
| Gateway decode `%252F` nhiều lần | Double-encoding có thể qua bộ lọc ở hop trước | Không double-decode, reject percent như dữ liệu identifier theo policy mẫu. |
| Gateway normalize dot segments/slashes | Router có thể xử lý route khác với URI được ký | Quy định một route representation; xác minh trước rewrite hoặc bảo vệ metadata gốc. |
| HTTP/2 `:path` chuyển sang HTTP/1.1 request target | Proxy có thể decode/re-encode hoặc thay query | Test translation end-to-end, lấy source canonical ở một trust boundary rõ. |
| Framework lấy decoded path nhưng verifier lấy raw path | Router/verifier có thể không cùng tài nguyên | Đồng bộ chính sách route trên dữ liệu đã được validate; từ chối input mơ hồ. |
| Client thêm header `X-Original-URI` hoặc `X-Verified` giả | Backend có thể nhầm metadata proxy là đáng tin | Ingress xóa header do ngoài cung cấp; hop gateway→backend xác thực, không có bypass. |

**Chú ý:** HMAC không mã hóa nội dung và không ngăn proxy chặn request. Một proxy không biết key thường không thể **sửa signed URI rồi tạo HMAC đúng**, nhưng vẫn có thể **phát lại nguyên request đã ký** trong cửa sổ thời gian. Cần HTTPS tới điểm tin cậy phù hợp, timestamp/nonce, rate limit và monitoring.

Nếu một gateway đáng tin thực hiện rewrite để phù hợp kiến trúc nội bộ, có hai phương án rõ ràng:

1. **Xác minh chữ ký tại ingress trước rewrite**, rồi chuyển identity đã xác minh và ngữ nghĩa tài nguyên đã được kiểm tra cho backend qua kênh nội bộ được xác thực; chặn mọi đường bypass verifier.
2. **Backend xác minh HMAC** và gateway chuyển raw target gốc qua cơ chế metadata được **xác thực và không bị client giả mạo**, đồng thời bảo đảm router/back-end dùng cùng đối tượng được ký. Header `X-Original-URI` thông thường do client tự gửi **không** đủ làm bằng chứng.

Không nên giải quyết lỗi chữ ký bằng cách **bỏ path khỏi canonical**, tự decode/re-encode cho đến khi tag khớp hoặc tin vào giá trị `X-Forwarded-*` chưa được kiểm soát.

## 9. Timestamp, nonce, key rotation và phân quyền

### 9.1. Unicode path được ký nhưng vẫn có replay

Giả sử client đã ký:

~~~text
POST /v1/profiles/caf%C3%A9?include=orders
timestamp=T, nonce=N, signature=HMAC(secret, canonical)
~~~

Nếu proxy gửi lại chính request đó, **raw URI vẫn canonical** và **HMAC vẫn đúng**. Verifier phải:

1. Kiểm tra timestamp đã ký trong cửa sổ freshness, ví dụ không quá cũ 300 giây và không vượt tương lai 60 giây theo chính sách riêng.
2. Kiểm tra nonce đã ký có định dạng và độ ngẫu nhiên phù hợp khi sinh ở client (ví dụ 16 byte từ `SecureRandom`).
3. Sau khi HMAC hợp lệ, **claim nonce nguyên tử** bằng store chia sẻ giữa replica, từ chối nonce trùng; TTL phải bao phủ **đến hết cửa sổ timestamp** cộng biên độ vận hành.
4. Với request có side effect, dùng **idempotency key đã được ký** để tránh thao tác lặp khi client retry bằng timestamp/nonce mới.

### 9.2. Key rotation và phạm vi tài nguyên

Client gửi key ID trong signed header để verifier chọn đúng shared secret. Verifier tra policy server theo **(client ID, key ID)**, kiểm tra key active, audience, thuật toán, thời hạn, allowed routes và giai đoạn rotation. Không chấp nhận key đã thu hồi chỉ vì timestamp vẫn hợp lệ. Key ID cần nằm trong canonical để proxy không tự đổi cách chọn key.

Một secret chỉ dùng cho `profiles-api` không nên được phép sử dụng ở dịch vụ thanh toán, kể cả khi hai dịch vụ dùng cùng format path. Đưa **audience** vào canonical và xác minh theo service policy giúp giảm nguy cơ dùng lại chữ ký ở sai nơi.

### 9.3. HMAC không phải authorization

Một chữ ký hợp lệ trên `/v1/profiles/caf%C3%A9` chỉ xác thực **bên có khả năng sử dụng secret** và **các byte được ký**. Nó không tự chứng minh client có quyền chỉnh sửa hồ sơ đó. Backend vẫn phải kiểm tra identity, scope, tenant, resource ID và hành động `POST` có được phép hay không.

Đặc biệt với Unicode confusable, hai tên hiển thị có thể dễ gây nhầm lẫn cho người đọc log hoặc UI. Điều này cần kiểm soát ở **data model và authorization**, không thể giải quyết chỉ bằng NFC và HMAC.

## 10. Ma trận kiểm thử Unicode path

Tạo integration test qua HTTP client, gateway và verifier; ghi lại thông tin an toàn như request ID, raw target đã kiểm tra, mã lỗi, nhưng **không log secret** hoặc body nhạy cảm. Mỗi ca độc lập dùng timestamp/nonce mới; riêng ca replay giữ nguyên nonce để test đúng mục tiêu.

| Ca kiểm thử | Input/thao tác | Kết quả mong đợi |
| --- | --- | --- |
| NFC hợp lệ | `/v1/profiles/caf%C3%A9?include=orders` | HMAC có thể hợp lệ nếu key/body/headers khớp. |
| Unicode text ở client | Tên dạng `cafe` + U+0301 | Encoder NFC tạo `caf%C3%A9` trước khi ký/gửi. |
| NFD trên raw URI | `/v1/profiles/cafe%CC%81?include=orders` | Từ chối theo hợp đồng chỉ nhận NFC. |
| Percent hex chữ thường | `caf%c3%a9` | Từ chối vì URI không theo percent encoding canonical. |
| Encoded unreserved | `%63af%C3%A9` thay `caf%C3%A9` | Từ chối representation không canonical. |
| Encoded slash | `/v1/profiles/a%2Fb?include=orders` | Reject segment có slash sau decode, không biến thành route khác. |
| Double-encoded slash | `/v1/profiles/a%252Fb?include=orders` | Reject theo policy ID không cho ký tự phần trăm. |
| Dot segments | `/v1/profiles/..`, `/v1/profiles/.` | Từ chối; không chấp nhận normalized route bất ngờ. |
| Slash cuối/gộp slash | `/v1/profiles/caf%C3%A9/` hoặc `//` | Từ chối nếu không khớp route canonical. |
| Raw Unicode chưa encode | `/v1/profiles/café` | Từ chối ở contract chỉ nhận raw ASCII percent-encoded. |
| Byte UTF-8 lỗi | Escape bytes không thể decode strict | Từ chối, không thay ký tự bằng U+FFFD. |
| Unicode bidi/confusable | Tên có bidi control hoặc ký tự nhìn giống | Bidi format bị policy ID ví dụ từ chối; confusable còn cần chính sách data model. |
| Path hợp lệ nhưng query khác | `include=orders` bị đổi thành tham số khác | HMAC không khớp hoặc reject theo query policy. |
| HTTP/2 → HTTP/1.1 | `:path` được gateway chuyển sang request target | Raw target hoặc metadata đáng tin phải giữ đúng hợp đồng ký. |
| Proxy decode/normalize | Proxy đổi `%2F`, NFC/NFD hoặc dot segment | Không cho pass qua verifier nếu dữ liệu/route đã đổi. |
| Body thay đổi | Giữ path, sửa JSON sau khi ký | Body SHA-256/HMAC sai. |
| Header trùng | Hai `Host`/`:authority` hoặc hai `X-Signature` mơ hồ | Từ chối tại trusted parser, không để các hop hiểu khác nhau. |
| Replay tuần tự/đồng thời | Gửi lại cùng raw path, timestamp và nonce | Claim nonce nguyên tử chỉ cho phép một request được chấp nhận. |
| Key rotation | Dùng key active/overlap/revoked | Chỉ key theo policy đúng audience và hiệu lực mới được xét HMAC. |
| Thiếu quyền | HMAC đúng trên path tài nguyên tenant khác | Authentication PASS, authorization DENY. |

### Câu hỏi tự kiểm tra

1. Vì sao `café` dạng NFC và chuỗi `cafe` + combining acute accent có thể nhìn giống nhưng cho percent-encoded URI khác nhau?
2. `URI.getRawPath()` và `URI.getPath()` khác nhau thế nào, và phải dùng giá trị nào khi contract ký raw request target?
3. Vì sao `%2F` và `%252F` có thể làm verifier và router hiểu khác tài nguyên dù HMAC vẫn tính đúng trên dãy byte đã ký?
4. Nếu proxy đổi `%C3%A9` thành `%c3%a9`, hệ thống dùng hợp đồng mẫu sẽ chấp nhận hay từ chối? Vì sao?
5. NFC có ngăn được toàn bộ Unicode homograph/confusable không? Cần kiểm tra gì sau khi giải mã path?
6. HMAC trên Unicode path đã đúng thì có cần timestamp, nonce và idempotency key nữa không?
7. Nếu request đã ký trỏ tới một hồ sơ ngoài tenant được cấp quyền, cơ chế nào quyết định kết quả?

## 11. Checklist triển khai

- [ ] Định nghĩa rõ path source: HTTP/1.1 request target hoặc HTTP/2/3 `:path` tại **trust boundary** đáng tin.
- [ ] Chọn rõ **raw-byte contract** hay **canonical Unicode contract**; không trộn các quy tắc và không normalize ngầm khi verifier tính HMAC.
- [ ] Với contract Unicode canonical: quy định NFC/NFD, UTF-8 strict, percent-encoding, hex case, unreserved, route segments và query riêng biệt.
- [ ] Từ chối percent encoding mơ hồ, encoded separator, double encoding, dot segments, malformed UTF-8 và path có nhiều cách hiểu giữa proxy/router.
- [ ] Signer xây URI từ byte/text đã normalize một lần; xác nhận raw target thực sự gửi giống target được ký.
- [ ] Verifier kiểm tra raw target canonical rồi mới dùng chính raw target đó dựng canonical request; không tin metadata `X-Original-URI` do ngoài tự khai báo.
- [ ] Ký method, raw path/query, signed headers, body bytes/hash và audience theo hợp đồng; timestamp/nonce nằm trong phần được HMAC bảo vệ.
- [ ] Thống nhất thứ tự field, LF, UTF-8, SHA-256 body digest, HMAC-SHA256 và cách encode signature.
- [ ] Kiểm thử HTTP/1.1 ↔ HTTP/2, reverse proxy, gateway rewrite, redirect, percent decode và Unicode normalization trên stack thực.
- [ ] Khóa bí mật từ key manager theo client ID/key ID; kiểm tra key rotation, thu hồi, audience và route scope.
- [ ] Server kiểm tra freshness, nonce store nguyên tử/TTL, idempotency cho side effect, HTTPS và giới hạn request.
- [ ] Sau khi xác thực, route tới resource ID đã kiểm tra và thực thi **authorization theo tenant/action/resource**; không dùng tên hiển thị Unicode làm bằng chứng quyền.

**Ghi nhớ:** **Unicode path chỉ an toàn trong HMAC request authentication khi signer, verifier và router thống nhất tuyệt đối về byte và ngữ nghĩa tài nguyên.** NFC, UTF-8 và percent-encoding là những lựa chọn cần ghi rõ trong hợp đồng; bản thân HMAC không tự sửa lỗi normalization, encoded slash, proxy rewrite hay confusable. Một chữ ký hợp lệ vẫn cần chống replay bằng timestamp/nonce, key rotation và kiểm tra phân quyền độc lập.
