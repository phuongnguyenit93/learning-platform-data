# Query không có giá trị trong canonicalization và xác thực HMAC

> **Chương:** Query canonicalization  
> **Đề bài:** Query không có giá trị  
> **Phạm vi module:** Xác thực HTTP request bằng HMAC với shared secret và canonical request gồm phương thức, URI, header hoặc body theo hợp đồng ký. Bài học tập trung vào tham số query không có value, cách chuẩn hóa rõ nghĩa, kiểm thử gateway và mối liên hệ với timestamp/nonce, key rotation và phân quyền.

## 1. Query không có giá trị là gì?

Một URI có thể chứa query parameter `name=value` nhưng cũng có những dạng không có phần value hoặc có value là chuỗi rỗng:

~~~text
/v1/orders?dryRun          # Có tên dryRun, KHÔNG có dấu "="
/v1/orders?dryRun=         # Có dấu "=", value là chuỗi rỗng
/v1/orders?                # Có dấu "?", query dài 0 ký tự
/v1/orders                 # Không có "?", query vắng mặt
/v1/orders?note=&dryRun    # Cùng lúc có value rỗng và flag
/v1/orders?=x             # Có dấu "=", tên parameter rỗng
~~~

Những kiểu này cần được gọi đúng:

- **Valueless parameter / presence-only flag:** `?dryRun`. Parameter xuất hiện nhưng không có dấu `=`; ứng dụng có thể định nghĩa sự xuất hiện của tên là Boolean `true`.
- **Empty-value parameter:** `?dryRun=` hoặc `?note=`. Có dấu bằng và chuỗi value có **0 ký tự**.
- **Empty query:** `/v1/orders?`. Dấu hỏi có mặt nhưng không có cặp parameter nào.
- **Absent query:** `/v1/orders`. Không tồn tại dấu hỏi hay thành phần query trong request target.
- **Empty-name parameter:** `?=x`, tên rỗng; không tương đương với valueless flag.

**Không có quy tắc HTTP tổng quát nào bắt buộc `flag` và `flag=` phải có cùng ý nghĩa nghiệp vụ.** RFC 3986 xác định cấu trúc query của URI; việc dùng dấu `&` và `=` để parse tham số, và việc diễn giải một tên không value thành Boolean, null hoặc chuỗi rỗng, là **quy tắc của ứng dụng hoặc framework**.

### 1.1. Vì sao sự khác biệt này liên quan đến HMAC?

Giả sử request:

~~~http
POST /v1/orders?dryRun HTTP/1.1
Host: api.example.test
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Signature: <hmac-base64url>

{"orderId":"o-123"}
~~~

Trong nghiệp vụ mẫu, `dryRun` nghĩa là **kiểm tra đơn hàng nhưng không lưu**. Nếu gateway xóa `dryRun`, chuyển nó thành `dryRun=` hoặc controller diễn giải nó khác verifier, request có thể chuyển từ **kiểm tra thử** thành **thao tác ghi thực**.

Nếu HMAC chỉ ký body mà bỏ qua query, attacker có thể sửa `dryRun` mà chữ ký vẫn khớp. Nếu HMAC ký query nhưng verifier coi `dryRun` và `dryRun=` giống nhau trong khi business handler phân biệt, một MAC đúng vẫn **không bảo đảm hành động đã được ký chính là hành động được thực thi**.

**Mục tiêu cốt lõi:** sender, verifier, gateway và business handler phải dùng **cùng một định nghĩa byte và cùng một ngữ nghĩa** về “không có value”.

### 1.2. Sau bài này người học làm được gì?

1. Phân biệt `?flag`, `?flag=`, `?`, query absent và `?=x`.
2. Chọn chính sách rõ ràng: reject, coi valueless như empty hoặc giữ khác biệt.
3. Viết signing contract cho Boolean flags, empty string, duplicate keys, dấu cộng, UTF-8 và percent-encoding.
4. Tạo canonical bytes và dùng JCA HMAC-SHA-256 để ký/xác minh HTTP request.
5. Test parser và gateway bằng golden fixtures có expected độc lập, không chỉ test tự ký/tự verify.
6. Giải thích vì sao timestamp/nonce, key rotation và authorization không thuộc chức năng canonical query.

## 2. Đọc đúng raw query trước khi parse

Ví dụ URL:

~~~text
https://api.example.test/v1/orders?dryRun&note=#receipt
        authority       path         query     fragment
~~~

- **Path:** `/v1/orders`, chọn tài nguyên/route.
- **Raw query:** `dryRun&note=`, là dữ liệu đầu vào cho canonicalizer.
- **Fragment:** `receipt`; không được gửi trong HTTP request target thông thường.
- **Request target (HTTP/1.1 origin-form):** `/v1/orders?dryRun&note=`.
- **HTTP/2/3:** pseudo-header `:path` thông thường chứa path và query tương ứng.

Trong Java Servlet, `getRequestURI()` cung cấp URI path tại điểm container nhìn thấy; `getQueryString()` cung cấp query string, không kèm dấu hỏi. **Không mặc nhiên giả định hai giá trị này còn đúng với raw bytes ở phía ngoài gateway**, vì proxy/container có thể đã rewrite hoặc normalize.

### 2.1. Query string không phải `Map<String,String>`

Một parser/framework có thể biến:

~~~text
dryRun  -> ("dryRun", null)
dryRun= -> ("dryRun", "")
~~~

nhưng cũng có thể biến **cả hai** thành chuỗi rỗng, bỏ flag hoặc áp dụng quy tắc form-urlencoded. Nếu ký một query được dựng lại từ parameter map, có thể đã mất thông tin “có hay không có dấu bằng”, thứ tự cặp, encoded name và duplicate keys.

Một mô hình typed rõ ràng hơn:

~~~text
Flag(name="dryRun")           # không có dấu "="
Value(name="note", value="")  # có "=" nhưng value dài 0
Value(name="page", value="2")
~~~

Khi có thể, chuyển **typed query đã được verifier kiểm tra** sang business handler, thay vì để controller parse lại raw query bằng parser khác.

### 2.2. Những trường hợp phải quyết định từ trước

| Raw target | Phân loại | Câu hỏi cần được hợp đồng trả lời |
|---|---|---|
| `/v1/orders` | Query vắng mặt | Có được chấp nhận không? |
| `/v1/orders?` | Query rỗng | Reject hay đồng nhất với absent? |
| `/v1/orders?dryRun` | Valueless flag | Có phải Boolean true? |
| `/v1/orders?dryRun=` | Empty value | Có nghĩa giống flag không? |
| `/v1/orders?dryRun=false` | Value nonempty | Flag-only có được phép nhận value? |
| `/v1/orders?note=` | Empty string | Có chấp nhận? |
| `/v1/orders?=x` | Empty name | Chấp nhận hay reject? |
| `/v1/orders?dryRun&dryRun=` | Trùng tên dưới hai dạng | Parser chọn giá trị đầu/cuối hay reject? |
| `/v1/orders?dry%52un` | Encoded name | Có cùng nghĩa với dryRun không? |

Không tự suy từ tên tham số rằng `?token`, `?admin` hoặc `?delete` phải được coi là true. Loại parameter, phạm vi giá trị và tác động của nó phải được khai báo theo từng endpoint.

## 3. Ba chiến lược canonical hóa tham số không có value

### 3.1. Chiến lược A: từ chối valueless parameter

~~~text
?note=     -> accept
?note      -> reject
?dryRun    -> reject
~~~

Ưu điểm là schema đơn giản, mọi parameter đều có dấu `=`. Hạn chế là không thể dùng syntax presence-only flag. Phù hợp với API chỉ nhận cặp name/value và không muốn hỗ trợ nhiều cách diễn giải.

### 3.2. Chiến lược B: coi valueless và empty tương đương

~~~text
?flag   -> canonical "flag="
?flag=  -> canonical "flag="
~~~

Chỉ an toàn nếu **business parser cũng thực sự coi hai dạng tương đương trong mọi trường hợp**. Nếu handler xem `?flag` là true nhưng `?flag=` là false hoặc absent, hai request có hành vi khác nhau có thể bị gộp thành **cùng HMAC input**.

Đừng chọn chiến lược này chỉ vì một thư viện tự trả `""` cho cả hai loại.

### 3.3. Chiến lược C: giữ khác biệt và áp schema

~~~text
?dryRun   -> canonical "dryRun"  (flag)
?note=    -> canonical "note="  (empty value)
?dryRun=  -> REJECT nếu dryRun chỉ cho phép flag
?note     -> REJECT nếu note yêu cầu name=value
~~~

**Bài này dùng chiến lược C**, để minh họa đầy đủ bài toán “query không có giá trị”. Chấp nhận flag được khai báo, cho phép empty value ở đúng parameter và từ chối dạng khác.

| Tiêu chí | Reject valueless | Gộp thành empty | Giữ khác biệt + schema |
|---|---|---|---|
| Hỗ trợ `?flag` | Không | Có | Có, khi tên nằm trong allowlist |
| `?flag` và `?flag=` cho cùng chữ ký | Không áp dụng | Có | Không |
| Cần xác minh semantics downstream | Có | **Đặc biệt quan trọng** | Có, theo typed schema |
| Độ phức tạp | Thấp | Thấp | Trung bình |
| Rủi ro bỏ sót kiểu flag | Không | Có | Giảm khi reject ngoài schema |

## 4. Những vấn đề định dạng phải xử lý cùng valueless query

### 4.1. Duplicate parameter và HTTP parameter pollution

~~~text
dryRun&dryRun
dryRun&dryRun=
dryRun&dry%52un
note=&note=hello
~~~

`%52` là ký tự `R` sau percent-decoding, vì vậy `dryRun` và `dry%52un` trùng tên canonical. Nếu gateway chỉ lấy first value nhưng backend lấy last value, kẻ tấn công có thể khiến **verifier và handler hiểu hai request khác nhau**.

Hợp đồng minh họa sẽ **reject duplicate canonical names**, kể cả khi raw names khác encoding. Với API cần multi-value như `tag=a&tag=b`, cần quy tắc riêng về lưu đủ giá trị, thứ tự/sorting, signing và parsing nghiệp vụ.

### 4.2. Dấu cộng và khoảng trắng

~~~text
note=hello+world
note=hello%20world
note=1%2B2
~~~

Trong `application/x-www-form-urlencoded`, `+` thường mang nghĩa khoảng trắng. Trong URI query tổng quát, `+` có thể là dấu cộng thật. Ví dụ bài học **từ chối dấu cộng thô**; client phải dùng `%20` cho khoảng trắng và `%2B` cho dấu cộng.

Không dùng `URLEncoder`/`URLDecoder` một cách máy móc cho canonical query dựa trên RFC 3986 khi những API đó dùng form semantics. Nếu tích hợp đối tác dùng form encoding, phải theo **hợp đồng đối tác** thay vì áp quy tắc bài học.

### 4.3. Percent-encoding và double decoding

~~~text
dry%52un          -> canonical dryRun
note=%41          -> canonical note=A
note=%2f          -> canonical note=%2F
note=%252F        -> canonical note=%252F
note=caf%C3%A9    -> canonical note=caf%C3%A9
~~~

Quy tắc: raw component chỉ nhận **ASCII unreserved** (`A-Z a-z 0-9 - . _ ~`) hoặc `%HH`. Decode byte escape **một lần**, giải mã UTF-8 **strict**, sau đó encode lại byte không phải ASCII unreserved thành `%HH` chữ hoa. Không tự Unicode normalize và không double-decode. `%252F` phải giữ biểu diễn percent-encoded của ký tự `%`, không bị chuyển thành `/`.

Byte UTF-8 không hợp lệ, `%ZZ`, `%A` hoặc ký tự điều khiển phải bị reject. Không “sửa” đầu vào lỗi bằng ký tự thay thế vì sender và receiver có thể tạo chuỗi ký khác nhau.

### 4.4. Query absent và dấu hỏi cuối

~~~text
/v1/orders      -> rawQuery = null  -> canonical query ""
/v1/orders?     -> rawQuery = ""    -> REJECT
/v1/orders?note=-> rawQuery = "note=" -> canonical "note="
~~~

Hợp đồng bài chọn **reject dấu hỏi cuối** để không phải đồng nhất absent query với present-but-empty query. Một API khác có thể quy định hai loại tương đương; điều quan trọng là không để verifier và business handler tự đưa ra quyết định khác nhau.

### 4.5. Query order

~~~text
page=2&dryRun&note=
note=&page=2&dryRun
~~~

Hợp đồng bài sẽ sort theo **canonical encoded name**, vì vậy hai chuỗi có thể cùng canonical thành `dryRun&note=&page=2`. Điều này **chỉ đúng** khi thứ tự tham số không có nghĩa nghiệp vụ. Nếu controller xử lý repeated values theo thứ tự, hoặc query là một chuỗi truy vấn chuyên biệt, đừng tự sort: cần hợp đồng raw query hoặc quy tắc khác.

## 5. Hợp đồng minh họa `hmac-flag-v1`

Đây là **ví dụ ứng dụng để học**, không mặc nhiên tương thích RFC 9421, AWS SigV4 hay API đối tác.

### 5.1. Schema cho endpoint /v1/orders

| Tên parameter | Loại | Dạng hợp lệ | Dạng không hợp lệ | Nghĩa minh họa |
|---|---|---|---|---|
| `dryRun` | Presence-only flag | `dryRun` | `dryRun=`, `dryRun=true` | Thử xử lý, không ghi đơn |
| `includeMeta` | Presence-only flag | `includeMeta` | `includeMeta=` | Yêu cầu thêm metadata |
| `note` | Value, cho phép rỗng | `note=`, `note=hello` | `note` | Ghi chú, empty khác absent |
| `page` | Value số dương | `page=2` | `page`, `page=`, `page=0` | Phân trang |

Parameter không thuộc schema sẽ bị reject, thay vì bị âm thầm bỏ qua. Điều này tránh một parameter nghiệp vụ vô tình không được xác thực.

### 5.2. Thuật toán canonical query

1. Nhận **raw query không có dấu `?`**, hoặc `null` khi query absent.
2. `null` ⇒ canonical query `""`; raw query `""` ⇒ reject.
3. Giới hạn 8.192 ký tự ASCII và 50 parameters trong ví dụ.
4. Split bằng `&`, **giữ phần tử rỗng** để reject `&&`/`&` cuối.
5. Segment **không có dấu `=`** phải là flag thuộc allowlist.
6. Segment có **đúng một dấu `=`** phải là value parameter thuộc schema. Empty value chỉ hợp lệ với `note`.
7. Canonicalize từng name/value bằng percent-decode một lần, UTF-8 strict, encode lại với percent hex chữ hoa.
8. Reject empty name và duplicate name **sau canonicalization**.
9. Sắp xếp theo canonical name tăng dần và nối bằng `&`. Flag giữ dạng `name`; value giữ dạng `name=value`.
10. Chuyển **chính typed values đã parse** sang business handler hoặc dùng parser khác được chứng minh tương thích.

### 5.3. Golden fixtures cho hợp đồng

| Raw query | Canonical / kết quả | Lý do |
|---|---|---|
| `dryRun` | `dryRun` | Flag giữ không có `=` |
| `dry%52un` | `dryRun` | Encoded name được chuẩn hóa |
| `note=` | `note=` | Value rỗng |
| `page=2&dryRun&note=` | `dryRun&note=&page=2` | Sort, vẫn giữ loại |
| `note=&page=2&dry%52un` | `dryRun&note=&page=2` | Tương đương theo contract |
| `includeMeta&dryRun` | `dryRun&includeMeta` | Sort flags |
| `note=caf%C3%A9` | `note=caf%C3%A9` | UTF-8 |
| `note=%41` | `note=A` | Encoded unreserved |
| `note=%2f` | `note=%2F` | Hex uppercase |
| `note=1%2B2` | `note=1%2B2` | Encoded plus |
| `note=%252F` | `note=%252F` | Không double-decode |
| Query absent (`null`) | `""` | Không có query |
| `""` sau dấu hỏi | **Reject** | Empty query |
| `dryRun=` | **Reject** | Flag bị truyền như value |
| `note` | **Reject** | Value thiếu dấu `=` |
| `dryRun&dry%52un` | **Reject** | Duplicate canonical name |
| `note=&note=x` | **Reject** | Duplicate value parameter |
| `page=0` | **Reject** | Value không đúng schema |
| `debug` | **Reject** | Flag không nằm trong allowlist |
| `=x` | **Reject** | Empty name |
| `note=hello+world` | **Reject** | Raw plus |
| `note=%C3%28` | **Reject** | UTF-8 hỏng |

**Điểm cốt lõi:** `dryRun` và `dryRun=` không bị canonical về cùng biểu diễn. `dryRun=` bị reject vì sai schema. `note=` được accept nhưng `note` bị reject. Những quy tắc này phải phù hợp với parser ở tầng nghiệp vụ.

## 6. Đưa query vào canonical request HMAC

Canonical query chỉ là một thành phần của canonical request. Hợp đồng `hmac-flag-v1` quy định **10 dòng**:

| Dòng | Trường | Cách biểu diễn |
|---|---|---|
| 1 | Version | Literal `hmac-flag-v1` |
| 2 | Method | `GET` hoặc `POST` theo request thật |
| 3 | Path | Raw encoded path, ví dụ `/v1/orders` |
| 4 | Canonical query | Từ thuật toán mục 5 |
| 5 | Content-Type | Một signed header; trim, lowercase bằng `Locale.ROOT`, vắng mặt là `""` |
| 6 | Client ID | `X-Client-Id` |
| 7 | Key ID | `X-Key-Id` |
| 8 | Timestamp | `X-Timestamp`, Unix epoch seconds thập phân canonical |
| 9 | Nonce | `X-Nonce`, Base64URL không padding của 16–32 byte CSPRNG |
| 10 | Body digest | SHA-256 raw request body, lowercase hex |

Các dòng nối bằng LF (`\n`), **không có LF cuối**; canonical string được mã hóa UTF-8. Tag ký bằng **HMAC-SHA-256 đầy đủ 32 byte** và truyền qua `X-Signature` bằng Base64URL không padding. Secret là khóa CSPRNG đủ mạnh được cấp riêng cho client/audience, **không đưa trong HTTP request**.

### 6.1. Ví dụ request có flag và value rỗng

~~~http
POST /v1/orders?page=2&dryRun&note= HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <base64url-hmac-tag>

{"orderId":"o-123"}
~~~

Canonical query:

~~~text
dryRun&note=&page=2
~~~

Canonical request:

~~~text
hmac-flag-v1
POST
/v1/orders
dryRun&note=&page=2
application/json
merchant-17
key-2026-11
1795824000
b75sZVQmhTBcfnX-bNbGqw
<sha256-hex-cua-raw-body>
~~~

Dòng cuối trong dấu ngoặc nhọn góc chỉ là **placeholder**: phải tính SHA-256 thật từ byte body. Nếu body rỗng, digest SHA-256 là:

~~~text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Khi request không có query, **dòng thứ tư trống**; khi có dấu hỏi nhưng query rỗng, request **bị từ chối** trước phép ký. Bên nhận tra secret theo `(clientId, keyId, audience)` và kiểm tra các trường đã ký, không tin secret do client gửi.

### 6.2. Vì sao phải ký cả method, path, header và body?

Nếu chỉ ký query `dryRun&note=` mà bỏ method, attacker có thể thử chuyển từ `GET` sang `POST`. Nếu bỏ path, attacker có thể chuyển query sang endpoint khác. Nếu bỏ body digest, nội dung order có thể bị thay. Chính sách ký phải ràng buộc **những thành phần thực sự ảnh hưởng tới hành động nghiệp vụ**.

Chỉ thay đổi thứ tự query (giữ đủ cặp name/value đã duyệt) được chấp nhận theo contract có sort. **Mọi thay đổi làm khác canonical query phải làm HMAC tag không còn hợp lệ với xác suất áp đảo.**


## 7. Java 17: giữ đúng flag và empty value khi ký HMAC

Ví dụ JDK 17+ dưới đây là mã Java tự chạy. Mục tiêu không phải xây một HTTP server hoàn chỉnh mà là **giữ sự khác nhau giữa một tham số không có dấu bằng và một tham số có value rỗng**, percent-decode chính xác, kiểm tra schema, sort rồi đưa canonical bytes vào HMAC-SHA-256.

### 7.1. Mã nguồn Java

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Comparator;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class ValuelessQueryHmacDemo {
    private static final String ALGORITHM = "HmacSHA256";
    private static final String VERSION = "hmac-flag-v1";
    private static final Set<String> FLAGS =
            Set.of("dryRun", "includeMeta");
    private static final Set<String> VALUES =
            Set.of("note", "page");

    private ValuelessQueryHmacDemo() {}

    // null ở value biểu diễn flag; "" là empty value.
    public record Param(String name, String value, boolean flag) {}

    public record ParsedQuery(String canonical, List<Param> params) {}

    public record Request(
            String method, String rawPath, String rawQuery,
            String contentType, String clientId, String keyId,
            String timestamp, String nonce, byte[] rawBody) {
        public Request {
            if (rawBody == null) {
                throw new IllegalArgumentException("Missing body");
            }
            rawBody = rawBody.clone();
        }
        @Override
        public byte[] rawBody() {
            return rawBody.clone();
        }
    }

    private static boolean unreserved(char c) {
        return (c >= 'A' && c <= 'Z')
                || (c >= 'a' && c <= 'z')
                || (c >= '0' && c <= '9')
                || c == '-' || c == '.' || c == '_' || c == '~';
    }

    private static String canonicalComponent(String raw) {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        for (int i = 0; i < raw.length(); i++) {
            char c = raw.charAt(i);
            if (unreserved(c)) {
                bytes.write((byte) c);
            } else if (c == '%') {
                if (i + 2 >= raw.length()) {
                    throw new IllegalArgumentException("Broken escape");
                }
                char hi = raw.charAt(i + 1);
                char lo = raw.charAt(i + 2);
                if (hi > 127 || lo > 127
                        || Character.digit(hi, 16) < 0
                        || Character.digit(lo, 16) < 0) {
                    throw new IllegalArgumentException("Invalid %HH");
                }
                bytes.write((Character.digit(hi, 16) << 4)
                        | Character.digit(lo, 16));
                i += 2;
            } else {
                throw new IllegalArgumentException(
                        "Non-ASCII/raw symbols must be percent-encoded");
            }
        }

        final String decoded;
        try {
            decoded = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes.toByteArray()))
                    .toString();
        } catch (CharacterCodingException ex) {
            throw new IllegalArgumentException("Bad UTF-8", ex);
        }
        if (decoded.codePoints().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException("Control char");
        }

        String hex = "0123456789ABCDEF";
        StringBuilder canonical = new StringBuilder();
        for (byte rawByte : decoded.getBytes(StandardCharsets.UTF_8)) {
            int b = rawByte & 0xFF;
            if (unreserved((char) b)) {
                canonical.append((char) b);
            } else {
                canonical.append('%')
                        .append(hex.charAt(b >>> 4))
                        .append(hex.charAt(b & 0x0F));
            }
        }
        return canonical.toString();
    }

    public static ParsedQuery parseQuery(String query) {
        if (query == null) return new ParsedQuery("", List.of());
        if (query.isEmpty() || query.length() > 8192) {
            throw new IllegalArgumentException("Invalid query size");
        }

        String[] segments = query.split("&", -1);
        if (segments.length > 50) {
            throw new IllegalArgumentException("Too many parameters");
        }
        List<Param> params = new ArrayList<>();
        Set<String> unique = new HashSet<>();

        for (String segment : segments) {
            int equal = segment.indexOf('=');
            boolean isFlag = equal < 0;
            String name;
            String value = null;

            if (isFlag) {
                name = canonicalComponent(segment);
                if (!FLAGS.contains(name)) {
                    throw new IllegalArgumentException("Unknown flag");
                }
            } else {
                if (segment.indexOf('=', equal + 1) >= 0) {
                    throw new IllegalArgumentException("Extra raw equals");
                }
                name = canonicalComponent(segment.substring(0, equal));
                value = canonicalComponent(segment.substring(equal + 1));
                if (!VALUES.contains(name)) {
                    throw new IllegalArgumentException("Wrong value form");
                }
                if ("page".equals(name)
                        && !value.matches("[1-9][0-9]{0,3}")) {
                    throw new IllegalArgumentException("Bad page number");
                }
            }

            if (name.isEmpty() || !unique.add(name)) {
                throw new IllegalArgumentException(
                        "Duplicate or empty parameter name");
            }
            params.add(new Param(name, value, isFlag));
        }
        params.sort(Comparator.comparing(Param::name));
        List<String> pairs = new ArrayList<>();
        for (Param p : params) {
            pairs.add(p.flag()
                    ? p.name()
                    : p.name() + "=" + p.value());
        }
        return new ParsedQuery(
                String.join("&", pairs), List.copyOf(params));
    }

    private static String asciiField(String value, int max) {
        if (value == null || value.isEmpty()
                || value.length() > max
                || value.chars().anyMatch(c -> c < 0x21 || c > 0x7E)) {
            throw new IllegalArgumentException("Bad signed field");
        }
        return value;
    }

    public static byte[] canonicalBytes(Request r)
            throws GeneralSecurityException {
        if (r == null
                || (!"POST".equals(r.method())
                        && !"GET".equals(r.method()))
                || !"/v1/orders".equals(r.rawPath())) {
            throw new IllegalArgumentException("Bad method/path");
        }
        String client = asciiField(r.clientId(), 64);
        String keyId = asciiField(r.keyId(), 64);
        String time = asciiField(r.timestamp(), 20);
        String nonce = asciiField(r.nonce(), 43);
        if (!client.matches("[A-Za-z0-9_-]+")
                || !keyId.matches("[A-Za-z0-9_-]+")
                || !time.matches("[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException("Bad identity/time");
        }

        final byte[] nonceRaw;
        try {
            nonceRaw = Base64.getUrlDecoder().decode(nonce);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Bad nonce", ex);
        }
        if (nonceRaw.length < 16 || nonceRaw.length > 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(nonceRaw).equals(nonce)) {
            throw new IllegalArgumentException("Bad nonce encoding");
        }

        String ct = r.contentType() == null ? "" : r.contentType();
        if (ct.length() > 128
                || ct.chars().anyMatch(c -> c < 0x20 || c > 0x7E)) {
            throw new IllegalArgumentException("Bad Content-Type");
        }
        ct = ct.trim().toLowerCase(Locale.ROOT);
        if (r.contentType() != null && ct.isEmpty()) {
            throw new IllegalArgumentException("Empty Content-Type");
        }

        String bodyHash = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                        .digest(r.rawBody()));
        String canonical = String.join("\n",
                VERSION,
                r.method(),
                r.rawPath(),
                parseQuery(r.rawQuery()).canonical(),
                ct,
                client,
                keyId,
                time,
                nonce,
                bodyHash);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] hmac(byte[] secret, byte[] data)
            throws GeneralSecurityException {
        if (secret == null || secret.length != 32 || data == null) {
            throw new IllegalArgumentException("Bad HMAC input");
        }
        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(new SecretKeySpec(secret, ALGORITHM));
        return mac.doFinal(data);
    }

    public static String sign(Request r, byte[] secret)
            throws GeneralSecurityException {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(hmac(secret, canonicalBytes(r)));
    }

    // Lõi MAC, chưa thực hiện key lookup, replay check, authorization.
    public static boolean verifyMac(Request r, byte[] secret, String sig)
            throws GeneralSecurityException {
        if (sig == null || sig.length() != 43) return false;
        final byte[] received;
        try {
            received = Base64.getUrlDecoder().decode(sig);
        } catch (IllegalArgumentException ex) {
            return false;
        }
        if (received.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(received).equals(sig)) {
            return false;
        }
        return MessageDigest.isEqual(
                hmac(secret, canonicalBytes(r)), received);
    }

    private static void require(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    private static void rejected(Runnable action) {
        boolean failed = false;
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            failed = true;
        }
        require(failed, "Expected rejection");
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        String a = "page=2&dryRun&note=";
        String b = "note=&page=2&dry%52un";
        String canonical = "dryRun&note=&page=2";
        require(parseQuery(a).canonical().equals(canonical),
                "Flag + empty + sort");
        require(parseQuery(b).canonical().equals(canonical),
                "Equivalent encoded query");
        require(parseQuery("dryRun").canonical().equals("dryRun"),
                "Valueless flag");
        require(parseQuery("note=").canonical().equals("note="),
                "Explicit empty");
        require(parseQuery(null).canonical().isEmpty(), "Absent query");
        require(parseQuery("note=%41").canonical().equals("note=A"),
                "Unreserved escape");
        require(parseQuery("note=%2f").canonical().equals("note=%2F"),
                "Hex uppercase");
        require(parseQuery("note=%252F").canonical()
                .equals("note=%252F"), "No double-decode");
        rejected(() -> parseQuery(""));
        rejected(() -> parseQuery("dryRun="));
        rejected(() -> parseQuery("note"));
        rejected(() -> parseQuery("page="));
        rejected(() -> parseQuery("dryRun&dry%52un"));
        rejected(() -> parseQuery("note=&note=hello"));
        rejected(() -> parseQuery("dryRun&&page=2"));
        rejected(() -> parseQuery("note=%C3%28"));
        rejected(() -> parseQuery("note=hello+world"));
        rejected(() -> parseQuery("debug"));
        rejected(() -> parseQuery("=x"));

        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret); // Demo only.
        byte[] nonceBytes = new byte[16];
        new SecureRandom().nextBytes(nonceBytes);
        String nonce = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(nonceBytes);
        String timestamp = Long.toString(Instant.now().getEpochSecond());
        Request r = new Request(
                "POST", "/v1/orders", a, "application/json",
                "merchant-17", "key-2026-11", timestamp, nonce,
                "{\"orderId\":\"o-123\"}"
                        .getBytes(StandardCharsets.UTF_8));
        String tag = sign(r, secret);
        require(verifyMac(r, secret, tag), "Valid MAC");

        Request reordered = new Request(
                r.method(), r.rawPath(), b, r.contentType(),
                r.clientId(), r.keyId(), r.timestamp(),
                r.nonce(), r.rawBody());
        require(verifyMac(reordered, secret, tag),
                "Equivalent order/encoding");

        Request modified = new Request(
                r.method(), r.rawPath(),
                "dryRun&note=changed&page=2", r.contentType(),
                r.clientId(), r.keyId(), r.timestamp(),
                r.nonce(), r.rawBody());
        require(!verifyMac(modified, secret, tag), "Tampered query");

        Request methodChanged = new Request(
                "GET", r.rawPath(), r.rawQuery(), r.contentType(),
                r.clientId(), r.keyId(), r.timestamp(),
                r.nonce(), r.rawBody());
        require(!verifyMac(methodChanged, secret, tag), "Method binding");
        System.out.println("PASS valueless query canonicalization/HMAC");
    }
}
~~~

Lưu mã thành `ValuelessQueryHmacDemo.java` và chạy trên JDK 17+:

~~~bash
javac ValuelessQueryHmacDemo.java
java ValuelessQueryHmacDemo
~~~

Kết quả mong đợi:

~~~text
PASS valueless query canonicalization/HMAC
~~~

### 7.2. Typed representation và giới hạn của ví dụ

Khi gọi `parseQuery("dryRun&note=")`, kết quả có dạng:

~~~text
ParsedQuery:
  canonical = dryRun&note=
  params:
    Param(name=dryRun, value=null, flag=true)
    Param(name=note, value="", flag=false)
~~~

Đây là khác biệt **có chủ đích**. Internal null chỉ đánh dấu flag, không phải chuỗi ký tự `null` hoặc JSON null. Empty value là chuỗi dài 0, không phải valueless.

Các giới hạn cần ghi nhớ:

- `verifyMac` là **lõi mật mã**, chưa phải HMAC request authentication filter production.
- Code ký timestamp và nonce, kiểm tra định dạng nonce, **chưa kiểm tra độ lệch đồng hồ hoặc nonce đã dùng trong kho chia sẻ**.
- Ví dụ chỉ hỗ trợ path `/v1/orders` và một schema query đóng. Endpoint thật cần quy tắc path, method, query và quyền truy cập tương ứng.
- Signed headers phải được kiểm tra **duy nhất**, raw body/framing phải được giới hạn trước khi băm. Byte array của request được snapshot nhưng HTTP adapter vẫn phải bảo vệ dữ liệu gốc.
- `MessageDigest.isEqual` so **raw MAC bytes**; `String.equals` chỉ dùng cho encoding Base64URL canonical và các fixtures công khai.
- Một test tự sign rồi verify có thể cùng mắc lỗi ở hai phía. Cần **golden fixtures độc lập** và test vector RFC 4231 để xác nhận HMAC-SHA-256 giữa các implementation.

## 8. Servlet/Spring: tránh mất thông tin có hoặc không có dấu bằng

Với một HTTP Servlet:

~~~java
String pathAtServlet = request.getRequestURI();
String rawQueryAtServlet = request.getQueryString();
String targetAtServlet = pathAtServlet
        + (rawQueryAtServlet == null ? "" : "?" + rawQueryAtServlet);

ValuelessQueryHmacDemo.ParsedQuery parsed =
        ValuelessQueryHmacDemo.parseQuery(rawQueryAtServlet);
~~~

`getRequestURI()` và `getQueryString()` mô tả request **tại điểm container quan sát**, không bảo đảm byte còn nguyên từ trước gateway. Cần kiểm thử cụ thể với container, reverse proxy, ingress và các rules normalize/query parsing.

**Không lấy `getParameter("dryRun")` hoặc `getParameterMap()` làm nguồn canonical** nếu parser có thể coi `?dryRun` và `?dryRun=` giống nhau, đổi `+` thành space hoặc gộp duplicate. Spring MVC có thể bind Boolean/Optional/Map theo quy tắc riêng tùy version; phải kiểm thử thực tế với schema.

Một thiết kế dễ kiểm soát:

~~~text
Request adapter:
    lấy raw target tại điểm tin cậy
    parse query, từ chối dữ liệu ngoài schema
    xác minh HMAC, timestamp, nonce và key record
    chuyển typed ParsedQuery cùng principal cho handler

Business handler:
    dùng typed params đã xác minh
    không parse lại bằng form semantics khác
    kiểm tra authorization theo action/resource/tenant
~~~

Nếu muốn sử dụng `dryRun=true` hoặc `dryRun=false` thay vì presence-only flag, cần **định nghĩa schema và phiên bản hợp đồng khác** hoặc thay đổi giao thức có kiểm soát; không tự nhập nhằng với `dryRun`.

## 9. Gateway, HTTP/2 và HTTP parameter pollution

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant V as HMAC Verifier
    participant N as Nonce Store
    participant B as Business
    C->>C: Ký canonical query + request
    C->>G: POST /v1/orders?dryRun&note=
    G->>V: Raw target có thể bị normalize
    V->>V: Validate flag/empty/duplicate và HMAC
    V->>V: Kiểm tra timestamp
    V->>N: Reserve nonce nguyên tử
    N-->>V: Nonce mới
    V->>B: Authenticated principal + typed query
    B->>B: Authorization và xử lý dryRun
~~~

| Tình huống | Rủi ro | Test/biện pháp |
|---|---|---|
| `?dryRun` thành `?dryRun=` | Flag thành empty value | Reject sai schema, không rewrite |
| `?note=` thành `?note` | Giá trị rỗng thành valueless | Bảo toàn raw query |
| Proxy bỏ tham số valueless | Mất cờ nghiệp vụ | Verify trước biến đổi |
| Proxy bỏ cặp `note=` vì rỗng | Mất thông tin signed | Không filter tùy ý |
| Reorder các tên khác nhau | Hợp đồng có sort có thể cùng HMAC | Business không được phụ thuộc order |
| Gộp `dryRun&dryRun=` | HTTP parameter pollution | Reject duplicate sau canonicalization |
| Đổi `+` thành space | Form vs URI semantics | Strict parser reject raw plus |
| HTTP/2 `:path` → HTTP/1.1 target | Có thể mất representation | Test end-to-end qua gateway |

Không tin `X-Original-URI` hay `X-Forwarded-*` do client tự đặt. Nếu phải đưa original request target từ gateway đến verifier, gateway đáng tin phải xóa header do client khai, thiết lập giá trị nội bộ và bảo vệ kết nối (mTLS/network policy khi phù hợp). Cân nhắc xác minh HMAC ở edge **trước** normalize.

Một ví dụ parameter pollution:

~~~text
Raw query:       dryRun&dryRun=
Verifier parser: lấy first -> dryRun=true
Handler parser:  lấy last  -> dryRun=false/empty
~~~

Một HMAC trên dữ liệu bị chọn lọc có thể bỏ sót giá trị handler sẽ xử lý. Contract của bài reject cả `dryRun=` và duplicate canonical name; **typed params đã xác minh** cần được dùng nhất quán cho policy và nghiệp vụ.

## 10. Chống replay và key rotation

**Canonical query không tự chống replay.** Một request có method/path/query/body và MAC hoàn toàn đúng vẫn có thể bị gửi lại nguyên trạng.

### 10.1. Timestamp và nonce

Quy tắc minh họa:

~~~text
nowSeconds - 300 <= signedTimestamp <= nowSeconds + 300
HMAC đúng với secret theo client/key/audience
nonceScope = (clientId, keyId, audience, nonce)
atomic reserve nonce sau khi MAC hợp lệ
TTL đủ che phủ cửa sổ chấp nhận timestamp
~~~

Với cửa sổ ±300 giây, kho nonce dùng chung có thể dùng Redis primitive tương đương `SET key 1 NX EX 600` theo chính sách đã thiết kế. Không dùng `GET` rồi `SET` vì hai node có thể cùng chấp nhận nonce. Không reserve trước MAC đúng: attacker có thể chiếm nonce của request thật bằng signature giả. Nếu kho nonce không khả dụng mà anti-replay là bắt buộc, **fail closed**.

Với request tạo đơn hàng, một retry hợp lệ với **nonce mới** vẫn có thể gây ghi dữ liệu hai lần. Cần thêm **idempotency key**; nếu nó ảnh hưởng hành vi, hãy đưa vào dữ liệu ký theo hợp đồng.

### 10.2. Key ID và rotation

| Key state | Receiver phải làm gì? |
|---|---|
| `ACTIVE` | Có thể verify với secret được cấp |
| `VERIFY_ONLY` | Chỉ verify trong cửa sổ overlap có deadline |
| `REVOKED` | Reject dù query/canonical bytes/MAC đúng |
| Không thuộc client/audience | Reject, không thử secret của tenant khác |
| Key ID không tồn tại | Reject, không fallback secret mặc định |

Secret được cấp qua secret manager/KMS hoặc kho bảo vệ thích hợp, nên có entropy cao và tách theo môi trường/đối tác/audience. Mỗi lần đổi key, `Mac.init` phải nạp **khóa đúng cho request đó**; `mac.reset()` không thực hiện rotation.

## 11. Authentication không thay thế authorization

Giả sử merchant 17 biết secret của mình và ký `POST /v1/orders?includeMeta&note=` hợp lệ, nhưng nghiệp vụ định truy cập metadata thuộc merchant 42:

~~~text
Authentication:
    principal = merchant-17
    MAC = valid
    canonicalQuery = includeMeta&note=
    timestamp = valid
    nonce = new

Authorization:
    action = orders:metadata:read
    owner = merchant-42
    principal = merchant-17
    decision = DENY
~~~

HMAC cho biết bên gửi nắm secret tương ứng, không tự cấp quyền dùng `includeMeta`, đọc tài nguyên khác tenant hoặc ghi đơn hàng. Authorization phải dùng **principal, hành động, tài nguyên thật và tenant**, dù query đã ký hoàn toàn đúng.

## 12. Ma trận kiểm thử

### 12.1. Query fixtures

| Raw query | Expected |
|---|---|
| `null` | Canonical rỗng, không có param |
| `""` | Reject |
| `dryRun` | Flag=true, value=null |
| `note=` | Flag=false, value rỗng |
| `dryRun=` | Reject |
| `note` | Reject |
| `page=2&dryRun&note=` | `dryRun&note=&page=2` |
| `dry%52un` | `dryRun` |
| `dryRun&dry%52un` | Reject duplicate |
| `note=&note=x` | Reject duplicate |
| `dryRun&dryRun=` | Reject schema/duplicate |
| `=x` | Reject empty name |
| `dryRun&&note=` | Reject empty segment |
| `note=%C3%28` | Reject malformed UTF-8 |
| `note=%00` | Reject control char |
| `note=hello+world` | Reject raw plus |
| `note=1%2B2` | Accept percent-encoded plus |
| `page=0` / `page=` | Reject invalid page |
| 51 parameters | Reject theo giới hạn |

### 12.2. Tampering với chữ ký đã tạo

Từ một chữ ký hợp lệ của `POST /v1/orders?dryRun&note=&page=2`:

| Thay đổi sau ký | Kỳ vọng |
|---|---|
| Bỏ `dryRun` | HMAC fail |
| Đổi `dryRun` thành `dryRun=` | Reject query |
| Đổi `note=` thành `note=x` | HMAC fail |
| Đổi `note=` thành `note` | Reject query |
| Thêm `includeMeta` | HMAC fail |
| Đổi `page=2` thành `page=3` | HMAC fail |
| Đảo thứ tự query theo contract sort | MAC vẫn hợp lệ |
| Đổi `POST` thành `GET` | HMAC fail |
| Đổi path, client ID, key ID hoặc body/header đã ký | HMAC fail hoặc reject key/route |
| Phát lại cùng timestamp/nonce | Nonce store reject |
| MAC đúng nhưng resource khác tenant | Authorization deny |

Các ca bị từ chối ngay ở validation không bắt buộc phải cho kết quả `invalid_signature`; hãy assert **không vào business handler** và mã lỗi tương ứng với hợp đồng API.

### 12.3. Gateway integration tests

Gửi cùng dữ liệu qua HTTP/1.1 và HTTP/2, gateway và container thực tế:

~~~text
GET /v1/orders
GET /v1/orders?
GET /v1/orders?dryRun
GET /v1/orders?dryRun=
GET /v1/orders?note=
GET /v1/orders?dryRun&note=
GET /v1/orders?dry%52un&note=
GET /v1/orders?dryRun&dry%52un
GET /v1/orders?note=hello%20world
GET /v1/orders?note=hello+world
~~~

Đối chiếu ba lớp: **raw target tại verifier**, **typed canonical query** và **giá trị cuối cùng controller/authorization sử dụng**. Kiểm tra thêm cache hit/miss, route rewrite, duplicate signed headers và nhiều verifier nodes nếu production sử dụng chúng.

### 12.4. Property-based tests

- Determinism: cùng raw query hợp lệ → cùng canonical bytes.
- Idempotence: canonicalize kết quả lần nữa không đổi output.
- Order independence: hoán vị tên khác nhau không đổi canonical.
- Flag preservation: `dryRun` không bị biến thành `dryRun=`.
- Empty value preservation: `note=` không bị biến thành `note`.
- Strict decoding: reject malformed percent, UTF-8 và duplicate after decode.
- MAC binding: thay canonical bytes đáng kể → tag thay đổi với xác suất áp đảo.

Sử dụng **golden fixtures độc lập**, test vector RFC 4231 cho HMAC và dữ liệu thử nghiệm thay vì production secrets. Fuzz phải có giới hạn thời gian, kích thước và tài nguyên.

## 13. Checklist triển khai

1. **Định nghĩa schema:** tên nào là flag, tên nào có value; empty value có hợp lệ không?
2. **Quyết định dấu hỏi cuối:** `/path` và `/path?` tương đương hay reject?
3. **Validate raw input:** duplicate sau decode, tên rỗng, dấu cộng, percent/UTF-8 lỗi, giới hạn size.
4. **Định nghĩa tương đương:** sắp xếp hay ký raw query; Unicode và encoding dùng quy tắc nào?
5. **Bảo toàn semantics:** verifier và handler dùng typed params nhất quán.
6. **Ký đủ thành phần:** method, path, query, header và raw body digest; ràng buộc audience đáng tin.
7. **Bảo vệ secret:** lookup đúng client/key/audience, rotation, revoke, không fallback.
8. **Chống replay:** timestamp, nonce ngẫu nhiên, kho chung ghi nguyên tử, fail closed.
9. **Phân quyền:** kiểm tra action/resource/tenant cho cả flag như `includeMeta`.
10. **Kiểm thử toàn tuyến:** gateway, servlet/Spring, business controller, cache và multi-node.
11. **Quan sát an toàn:** phân loại `invalid_query`, `invalid_signature`, `replayed_nonce`, `permission_denied`; không log secret, expected tag hay body nhạy cảm.

Có thể trả `400` cho malformed query, `401` cho authentication sai, `403` khi thiếu quyền, `413` cho body quá lớn, `503` khi dependency xác thực bắt buộc không sẵn sàng; chính sách thực tế tùy API contract và yêu cầu hạn chế lộ thông tin.

## 14. Bài tập

**Bài 1 — Phân loại:** Hãy xác định kết quả của `/orders`, `/orders?`, `/orders?dryRun`, `/orders?dryRun=`, `/orders?note=` và `/orders?=x` theo contract của bài.

**Bài 2 — Parser mismatch:** Một parser trả `""` cho cả `?dryRun` và `?dryRun=`. Vì sao việc dùng nó để dựng HMAC là không phù hợp? Đề xuất typed representation giữ được dấu bằng.

**Bài 3 — Sort:** So sánh `page=2&dryRun&note=` với `note=&page=2&dryRun`. Khi nào chúng cùng canonical, khi nào không?

**Bài 4 — Duplicate:** Vì sao `dryRun&dry%52un` phải bị reject? Hãy mô tả cách first-value/last-value giữa proxy và handler có thể tạo lỗ hổng.

**Bài 5 — Dấu cộng:** Khác biệt giữa `note=1+2`, `note=1%2B2` và `note=1%202` là gì?

**Bài 6 — Gateway:** Gateway chuyển `?dryRun` thành `?dryRun=` vì “tối ưu query”. Thiết kế nào bảo đảm request không bị diễn giải sai mà không tắt HMAC?

**Bài 7 — Replay:** Request có canonical query và MAC đúng được phát lại cùng timestamp/nonce. Thành phần nào phải reject, và vì sao?

**Bài 8 — Phân quyền:** Merchant A ký `?includeMeta` để xem dữ liệu của merchant B. Vì sao MAC đúng không đủ và tầng nào phải từ chối?

## 15. Kết luận

**Query không có giá trị** là một sự khác biệt về **biểu diễn và ngữ nghĩa**, không đơn giản chỉ là empty string. `?flag`, `?flag=`, `?` và không có query có thể có tác dụng khác nhau. Signing contract phải **chọn và kiểm thử một chính sách duy nhất**: reject, gộp có chủ đích hoặc bảo toàn sự khác biệt. Chữ ký HMAC phải ràng buộc đúng method/path/query/header/body theo hợp đồng, đồng thời verifier và business handler phải **hiểu cùng một typed query**. Secret/key rotation, timestamp/nonce chống replay, gateway compatibility và **authorization trên hành động/tài nguyên cuối cùng** vẫn là các bước bảo mật độc lập.

**Tài liệu tham khảo:**

- [RFC 3986 — URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986): query, percent-encoding, unreserved characters.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): target URI và HTTP method semantics.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): request target và parsing.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): pseudo-header `:path`.
- [RFC 2104 — HMAC](https://www.rfc-editor.org/rfc/rfc2104): keyed-hash message authentication.
- [RFC 4231 — HMAC test vectors](https://www.rfc-editor.org/rfc/rfc4231): tham khảo kết quả HMAC-SHA-256 độc lập.
- [Java SE 17 — javax.crypto.Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): `getInstance`, `init` và `doFinal`.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): một chuẩn tham khảo ký HTTP components. Hợp đồng `hmac-flag-v1` là **ví dụ học tập riêng**, không tự nhận tương thích RFC 9421.
