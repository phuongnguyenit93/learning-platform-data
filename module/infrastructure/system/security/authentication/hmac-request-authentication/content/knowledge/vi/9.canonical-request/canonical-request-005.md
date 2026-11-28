# Canonical query: chuẩn hóa query string để ký HMAC

> **Chương:** Canonical request  
> **Đề bài:** Canonical query  
> **Phạm vi:** Thiết kế xác thực HTTP request bằng HMAC với shared secret. Sender và receiver phải tái tạo chính xác canonical request gồm phương thức, URI, header hoặc body theo hợp đồng ký. Bài này tập trung vào **canonical query**: biểu diễn query thành chuỗi byte có thể ký và xác minh nhất quán, kể cả khi thứ tự tham số hoặc cách percent-encode thay đổi. Các yêu cầu về timestamp/nonce chống replay, key rotation, proxy/gateway và phân quyền vẫn là lớp bảo vệ độc lập.

## 1. Canonical query là gì?

**Query** là phần của URI nằm sau ký tự `?` đầu tiên của request target. Query thường mang các tham số lọc, phân trang, định danh hoặc quyết định hành vi của endpoint:

~~~http
GET /v1/orders?status=PAID&page=2&sort=createdAt HTTP/1.1
Host: api.example.test
~~~

Trong ví dụ này:

~~~text
Method:         GET
Path:           /v1/orders
Raw query:      status=PAID&page=2&sort=createdAt
Request target: /v1/orders?status=PAID&page=2&sort=createdAt
~~~

**Canonical query** là biểu diễn query sau khi áp dụng **một tập quy tắc cố định, được sender và receiver cùng hiểu**. Các quy tắc có thể bao gồm parse tham số, percent-decode theo đúng chuẩn, encode lại từng byte UTF-8, sắp xếp theo thứ tự xác định và định nghĩa cách xử lý tham số trùng.

Nếu hai chuỗi query khác biểu diễn nhưng có cùng ý nghĩa theo hợp đồng:

~~~text
page=2&status=PAID
status=PAID&page=2
~~~

thì một hợp đồng **có bước sắp xếp tham số** có thể biến cả hai thành:

~~~text
page=2&status=PAID
~~~

Ngược lại, hợp đồng **ký raw query** sẽ xem hai chuỗi đầu là khác byte. **Không có một chuẩn canonical query duy nhất cho mọi HMAC HTTP API**: quy tắc phải được ghi rõ, kiểm thử và áp dụng thống nhất. Hãy dùng chính hợp đồng của nhà cung cấp khi tích hợp hệ thống bên ngoài, không thay bằng thuật toán “tự chuẩn hóa” của ứng dụng.

### 1.1. Vì sao query phải nằm trong chữ ký?

Giả sử client gửi:

~~~http
GET /v1/payments?merchantId=17&limit=20 HTTP/1.1
X-Client-Id: partner-17
X-Signature: <hmac-tag>
~~~

Nếu ứng dụng chỉ ký method và path nhưng bỏ qua query, attacker có thể thay `merchantId=17` thành `merchantId=42` hoặc nâng `limit` lên giá trị lớn mà MAC vẫn kiểm tra thành công. **Query có ảnh hưởng đến dữ liệu được đọc hoặc hành động được thực thi thì phải được bảo vệ** bằng chữ ký hoặc cơ chế kiểm soát tương đương được giao thức quy định.

Việc ký query giúp **phát hiện sửa đổi** nhưng không tự chứng minh client có quyền xem giao dịch của merchant 42. Sau khi HMAC hợp lệ, server vẫn phải kiểm tra **authorization** trên tài nguyên thật.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt path, query, raw query, decoded query, canonical query và query parameter map của framework.
2. Giải thích tác động của thứ tự tham số, percent-encoding, ký tự `+`, tham số rỗng, trùng key và Unicode đến chữ ký HMAC.
3. Định nghĩa một hợp đồng canonical query đủ chính xác về byte, có test vector và chính sách từ chối đầu vào mơ hồ.
4. Viết ví dụ Java 17 thực hiện strict percent-decode → UTF-8 validation → canonical encode → sort, rồi ký bằng `Mac.getInstance("HmacSHA256")`.
5. Thiết kế kiểm thử qua gateway/proxy, phân tách lỗi canonical query với lỗi thuật toán, secret, replay và phân quyền.

## 2. Query không phải path, fragment hay parameter map

Theo mô hình URI, phần query bắt đầu sau dấu `?` và kéo dài tới trước fragment `#` nếu có. Fragment thường chỉ được client sử dụng, **không** nằm trong HTTP request target thông thường.

~~~text
https://api.example.test/v1/orders?status=PAID&page=2#latest
        authority        path       query          fragment
~~~

Trong HTTP/1.1 origin-form, request line thường truyền **path + dấu ? + query**. Trong HTTP/2/3, pseudo-header `:path` cũng chứa path và query tương ứng. Query **không** bao gồm tên host, scheme hoặc fragment.

| Đối tượng | Ví dụ | Điểm cần nhớ khi ký |
|---|---|---|
| Path | `/v1/orders` | Chọn tài nguyên/route; cần ký theo quy tắc path riêng |
| Raw query | `z=9&a=1` | Chuỗi đúng như bên nhận nhìn thấy ở điểm xác minh |
| Decoded query parameter | `a` → `1` | Giá trị sau khi parse và decode theo một grammar |
| Canonical query | `a=1&z=9` | Biểu diễn xác định theo hợp đồng |
| Query map | `Map<String,String>` hoặc multi-map | Có thể mất thứ tự, key trùng hoặc phân biệt `x` với `x=` |
| Fragment | `#latest` | Không mặc nhiên được gửi đến origin server |
| Full URL | `https://.../v1/orders?x=1` | Có scheme, authority; không tự coi là raw query |

**Đừng lấy query map của framework làm dữ liệu ký nếu chưa xác minh semantics.** Một số framework:

- Dùng quy tắc form-urlencoded: dấu `+` thành khoảng trắng.
- Gom nhiều giá trị trùng key thành một danh sách, lấy giá trị đầu hoặc giá trị cuối.
- Decode phần trăm một lần hay xử lý character set theo cấu hình.
- Bỏ phân biệt `flag`, `flag=` hoặc tham số có tên rỗng.
- Có thể normalize hoặc rewrite request target trước khi business code nhìn thấy.

Nếu sender, verifier, gateway và router không thống nhất, MAC có thể sai dù secret đúng, hoặc nguy hiểm hơn: **verifier ký một cách hiểu còn business handler xử lý cách hiểu khác**.

## 3. Những quy tắc dễ gây nhập nhằng

### 3.1. Thứ tự tham số

~~~text
a=1&b=2
b=2&a=1
~~~

Nếu hợp đồng sắp xếp theo tên rồi giá trị, hai chuỗi chuẩn hóa có thể giống nhau. Nếu hợp đồng ký raw query, chúng khác nhau. **Tự sắp xếp tham số khi nhà cung cấp yêu cầu ký raw query sẽ làm chữ ký không hợp lệ.**

### 3.2. Percent-encoding

URI percent-encoding biểu diễn một byte dưới dạng dấu `%` và hai chữ số hex:

~~~text
q=caf%C3%A9    # Chuỗi UTF-8 của "café", các byte é được encode
path=%2Fv1     # Giá trị parameter chứa slash đã encode
x=%41          # Byte 0x41, tương ứng ký tự A
x=A            # Ký tự A ở dạng unreserved
~~~

Một hợp đồng canonical có thể quy định **decode percent-escape đúng một lần**, xác minh UTF-8 hợp lệ, rồi encode lại: ký tự *unreserved* không cần escape, các byte khác trở thành `%HH` với hex **chữ hoa**. Khi đó `x=%41` và `x=A` cùng canonical thành `x=A`.

Không tự ý **double-decode**: `%252F` (encoded percent sign theo sau “2F”) khác `%2F`. Decode một lần rồi encode lại một lần theo hợp đồng phải giữ sự khác nhau này.

### 3.3. Dấu cộng và khoảng trắng

Đây là một trong những nguồn lỗi HMAC phổ biến nhất:

~~~text
q=hello+world
q=hello%20world
q=1%2B2
~~~

Trong `application/x-www-form-urlencoded`, dấu `+` thường biểu diễn khoảng trắng. Trong cú pháp query URI tổng quát, dấu `+` có thể là dấu cộng thật. **Không được mặc định `+` và `%20` tương đương trong mọi hợp đồng ký.**

Ví dụ học tập ở mục 4 **không chấp nhận dấu + thô**; phải dùng:

- Khoảng trắng: `%20`.
- Dấu cộng trong giá trị: `%2B`.

Do đó `q=hello+world` bị từ chối thay vì tự biến thành `q=hello%20world`. Nếu hệ thống tích hợp dùng form semantics, hãy thiết kế một hợp đồng **riêng** và bảo đảm verifier cùng business parser dùng đúng semantics đó.

### 3.4. Tham số không có giá trị và tham số trùng

~~~text
flag
flag=
flag=&page=2
role=user&role=admin
role=user&%72ole=admin
~~~

Các kiểu này cần chính sách tường minh:

- `flag` không chứa dấu `=`: có thể được hiểu là `flag=` ở một số hệ thống, nhưng ví dụ của bài **từ chối** để tránh mơ hồ.
- `flag=`: tham số tồn tại với giá trị rỗng, **được phép**.
- `role=user&role=admin`: duplicate key; framework có thể chọn giá trị đầu/cuối hoặc toàn bộ danh sách.
- `role=user&%72ole=admin`: hai tên raw khác nhau nhưng cùng decoded name `role`; cũng là duplicate.

Với các API nhạy cảm, một chính sách chặt là **từ chối duplicate parameter name sau canonical hóa**. Nếu endpoint cần multi-value như `tag=a&tag=b`, hợp đồng và backend parser phải thống nhất rõ liệu thứ tự có ý nghĩa, cách sort name/value và cách xác thực đầy đủ **tất cả** giá trị. Không thể tự nới lỏng quy tắc test của bài.

### 3.5. Query vắng mặt và query rỗng

~~~text
/v1/orders       # Không có dấu ?
/v1/orders?      # Có dấu ? nhưng không có nội dung query
/v1/orders?a=    # Có tham số a với giá trị rỗng
~~~

Đây là ba biểu diễn khác nhau ở raw request target. Ví dụ bên dưới quy định:

- **Không có query**: canonical query là chuỗi rỗng.
- **Có dấu ? nhưng query rỗng**: từ chối.
- **Có `a=`**: canonical query là `a=`.

Một giao thức khác có thể coi hai trường hợp đầu tương đương; nhưng phải quyết định từ trước, không tự suy từ `null`/empty string của framework.

### 3.6. Unicode và ký tự điều khiển

Unicode có thể có nhiều biểu diễn khác nhau ở cấp code point, ví dụ chữ có dấu dạng **ký tự dựng sẵn** hoặc dạng **base letter + combining mark**. Một hợp đồng có thể yêu cầu Unicode NFC, hoặc **không áp dụng Unicode normalization**. Bài này chọn **không normalize Unicode**: chỉ decode UTF-8 hợp lệ và encode lại đúng các code point đã nhận. Vì vậy hai biểu diễn Unicode tương tự về hình thức có thể có canonical query khác nhau.

Từ chối percent-encoding không hợp lệ (ví dụ `%G1`, `%A`), byte sequence UTF-8 sai, ký tự điều khiển và các chuỗi quá dài. Không tự thay byte lỗi bằng ký tự thay thế `�`: nếu receiver và sender có cách “sửa” dữ liệu khác nhau, hợp đồng ký mất tính nhất quán.

## 4. Định nghĩa một hợp đồng canonical query có thể kiểm thử

Hợp đồng sau mang tên **`hmac-v1-query`** và chỉ dùng cho bài học. Đây **không** phải RFC 9421, không mặc nhiên tương thích AWS SigV4 hay chuẩn API bên thứ ba.

### 4.1. Nguyên tắc

1. **Input:** raw query tại điểm xác minh; không lấy query map đã parse sẵn. Không có query được biểu diễn bằng `null`.
2. **Độ dài:** ví dụ giới hạn raw query tối đa **8.192 ký tự ASCII**, số parameter tối đa **100**; hệ thống thật có thể chọn giới hạn khác.
3. **Tách cặp:** dùng dấu `&`; mỗi cặp phải có đúng một dấu `=` literal. Ký tự `=` hoặc `&` là dữ liệu phải được percent-encode.
4. **Tên:** không được rỗng; **giá trị:** cho phép rỗng. Từ chối cặp rỗng do `&&` hoặc dấu `&` cuối.
5. **Raw component:** chỉ chấp nhận ký tự `A-Z a-z 0-9 - . _ ~` và `%HH`. Những ký tự khác muốn dùng làm dữ liệu (dấu cộng, khoảng trắng, slash, `&`, `=`) phải percent-encode.
6. **Decode:** đổi các `%HH` thành byte, rồi giải mã toàn bộ component bằng **UTF-8 strict**, không thay thế byte lỗi. Không double-decode, không Unicode normalize.
7. **Canonical encode:** ký tự ASCII unreserved được ghi nguyên dạng; mọi byte UTF-8 còn lại ghi `%HH` với chữ số hex **viết hoa**.
8. **Duplicate:** từ chối các parameter trùng **canonical name**, kể cả nếu raw name khác (`name` và `%6Eame`).
9. **Sắp xếp:** theo canonical encoded name tăng dần; nếu triển khai hỗ trợ multi-value, cần thêm quy tắc sắp xếp canonical value và semantics riêng. Ví dụ vẫn định nghĩa thứ tự so sánh (name, value) nhưng từ chối key trùng.
10. **Ghép:** từng cặp là `name=value`, nối bằng dấu `&`, không có `&` cuối. Không có query ⇒ canonical query là chuỗi rỗng; `?` với query rỗng ⇒ từ chối.

Các quy tắc **nghiêm hơn** ngữ pháp URI tổng quát nhằm làm input có thể kiểm chứng. Ví dụ sẽ từ chối raw `q=a/b` dù URI query tổng quát cho phép slash; client phải gửi `q=a%2Fb`. Điều này là lựa chọn của **signing contract**, không phải phát biểu rằng mọi URI chứa slash trong query đều sai.

### 4.2. Pseudocode thuật toán

~~~text
canonicalQuery(rawQuery):
    nếu rawQuery không tồn tại:
        trả ""
    kiểm tra rawQuery không rỗng, giới hạn kích thước
    split bằng "&", giữ cả phần tử rỗng để phát hiện lỗi
    cho mỗi segment:
        bắt buộc có chính xác một dấu "="
        rawName  = phần trước "="
        rawValue = phần sau "="
        name  = canonicalComponent(rawName)
        value = canonicalComponent(rawValue)
        tên không rỗng; name chưa từng xuất hiện
        thêm (name, value)
    sort theo name, sau đó value
    join các cặp dạng "name=value" bằng "&"

canonicalComponent(raw):
    đọc ASCII unreserved nguyên dạng
    đọc %HH thành đúng một byte
    từ chối raw char khác, escape lỗi, UTF-8 lỗi, control chars
    giải mã UTF-8 strict đúng một lần
    encode lại từng byte UTF-8:
        unreserved ASCII -> literal
        byte khác        -> %HH viết hoa
~~~

Không dựa vào thứ tự iteration của `HashMap`. Không dùng `URLEncoder.encode` một cách trực tiếp cho hợp đồng RFC 3986 ở đây vì `URLEncoder` dùng các quy tắc form encoding (chẳng hạn khoảng trắng thành `+`). Nếu dùng thư viện URI, phải xác minh **chính xác** cách encode/decode của thư viện đó bằng golden fixtures.

### 4.3. Các ví dụ đầu vào và kết quả

| Raw query | Canonical query / kết quả | Lý do |
|---|---|---|
| `z=9&a=1` | `a=1&z=9` | Sort tên |
| `a=1&z=9` | `a=1&z=9` | Đã theo thứ tự |
| `item=caf%C3%A9&z=9` | `item=caf%C3%A9&z=9` | UTF-8 được giữ, hex viết hoa |
| `x=%41` | `x=A` | Encoded unreserved trở về literal |
| `x=%2f` | `x=%2F` | Chuẩn hóa chữ hoa của hex |
| `q=hello%20world` | `q=hello%20world` | Khoảng trắng là %20 |
| `q=1%2B2` | `q=1%2B2` | Dấu cộng dữ liệu encoded |
| `q=hello+world` | **Reject** | Dấu cộng raw không được phép |
| `flag=` | `flag=` | Cho phép giá trị rỗng |
| `flag` | **Reject** | Không có dấu bằng |
| `a=1&a=2` | **Reject** | Trùng canonical name |
| `a=1&%61=2` | **Reject** | Trùng name sau decode/canonicalize |
| `x=%C3%28` | **Reject** | UTF-8 malformed |
| `x=%252F` | `x=%252F` | Không double-decode |
| Không có query (`null`) | Chuỗi rỗng | Quy tắc trường vắng mặt |
| Query rỗng (`""` sau `?`) | **Reject** | Không chấp nhận dấu hỏi cuối |

**Lưu ý quan trọng:** Hai request có canonical query giống nhau **chỉ nên được xem tương đương** nếu endpoint nghiệp vụ cũng hiểu chúng tương đương. Nếu downstream phân biệt thứ tự parameter hoặc raw escape, không được dùng hợp đồng sort/decode này cho endpoint đó.

## 5. Đưa canonical query vào canonical request để ký

Một signing contract phải bảo vệ nhiều thành phần của request, không chỉ query. Ví dụ `hmac-v1-query` có mười dòng theo thứ tự:

| Dòng | Thành phần | Quy tắc |
|---|---|---|
| 1 | Version | Literal `hmac-v1-query` |
| 2 | Method | Token HTTP, ví dụ `GET` |
| 3 | Path | **Raw encoded path** tại điểm verify, theo hợp đồng path độc lập |
| 4 | Canonical query | Kết quả thuật toán mục 4 |
| 5 | Content-Type | Header đơn, trim và lowercase theo `Locale.ROOT`; vắng mặt ⇒ chuỗi rỗng |
| 6 | Client ID | `X-Client-Id`, được ký |
| 7 | Key ID | `X-Key-Id`, được ký |
| 8 | Timestamp | `X-Timestamp`, epoch seconds canonical |
| 9 | Nonce | `X-Nonce`, Base64URL không padding của 16–32 byte CSPRNG |
| 10 | Body digest | SHA-256 của **raw body bytes**, hex chữ thường |

Các dòng ghép bằng **LF** (`\n`), không có LF cuối cùng, dùng byte UTF-8. Chữ ký là **HMAC-SHA-256 đủ 32 byte** của canonical bytes, truyền dưới dạng Base64URL không padding trong `X-Signature`. Chính `X-Signature` không nằm trong chuỗi ký của ví dụ.

### 5.1. HTTP request minh họa

~~~http
GET /v1/orders?z=9&note=hello%20world&item=caf%C3%A9 HTTP/1.1
Host: api.example.test
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <base64url-hmac-tag>

~~~

Body ở đây **rỗng**, không gửi `Content-Type`. Canonical query là:

~~~text
item=caf%C3%A9&note=hello%20world&z=9
~~~

Canonical request có **một dòng trống** dành cho `Content-Type`:

~~~text
hmac-v1-query
GET
/v1/orders
item=caf%C3%A9&note=hello%20world&z=9

merchant-17
key-2026-11
1795824000
b75sZVQmhTBcfnX-bNbGqw
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Dòng cuối là **SHA-256 của body rỗng**; ví dụ không có LF sau dòng này. `<base64url-hmac-tag>` là chỗ giữ chỗ, không phải tag đã tính. Trong production, receiver phải tra secret tương ứng với client/key ID từ key store và audience được cấu hình đáng tin, **không lấy secret từ HTTP request**.

### 5.2. Vì sao cần ký path cùng query?

Nếu chỉ ký canonical query mà bỏ path, một request từ `/v1/orders?status=PAID` có thể bị chuyển đến `/v1/refunds?status=PAID`. Nếu chỉ ký path mà bỏ query, attacker có thể đổi filter, ID, limit hoặc dữ liệu target. Thiết kế này ký **method + path + canonical query + headers và digest body**. Tuy nhiên, ứng dụng thực còn cần quy tắc rõ về **Host/authority hoặc audience**: nếu một secret dùng cho nhiều dịch vụ, có thể xảy ra cross-service replay. Nên tách secret theo audience hoặc ký audience/authority đã được xác định đáng tin theo hợp đồng.

## 6. Java 17: canonical query strict và kiểm tra HMAC

Ví dụ Java 17 dưới đây có thể chạy độc lập. Nó triển khai đúng **hợp đồng hmac-v1-query** ở mục 4 (đây là một quy ước học tập, không mặc nhiên tương thích mọi HTTP API). Nó minh họa strict UTF-8, percent encoding chuẩn, sorting, kiểm tra duplicate, ký và xác minh HMAC.

Để ngắn gọn mà rõ ràng, path ví dụ chỉ cho phép `/v1/...` với các segment ASCII an toàn; adapter HTTP thật phải kiểm tra request framing, duplicate signed headers, raw body size và ký đúng representation tại điểm verify.

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
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

public final class CanonicalQueryDemo {
    private CanonicalQueryDemo() {}

    private record Pair(String name, String value) {}

    public record Request(
            String method,
            String rawPath,
            String rawQuery,
            String contentType,
            String clientId,
            String keyId,
            String timestamp,
            String nonce,
            byte[] rawBody) {}

    public static String canonicalQuery(String rawQuery) {
        if (rawQuery == null) return ""; // Không có dấu hỏi.
        if (rawQuery.isEmpty() || rawQuery.length() > 8192) {
            throw new IllegalArgumentException("Invalid query size");
        }
        String[] segments = rawQuery.split("&", -1);
        if (segments.length > 100) {
            throw new IllegalArgumentException("Too many parameters");
        }
        List<Pair> pairs = new ArrayList<>(segments.length);
        Set<String> seenNames = new HashSet<>();
        for (String segment : segments) {
            int eq = segment.indexOf('=');
            if (eq <= 0 || segment.indexOf('=', eq + 1) >= 0) {
                throw new IllegalArgumentException("Invalid name=value pair");
            }
            String name = canonicalComponent(segment.substring(0, eq));
            String value = canonicalComponent(segment.substring(eq + 1));
            if (name.isEmpty() || !seenNames.add(name)) {
                throw new IllegalArgumentException("Duplicate/empty name");
            }
            pairs.add(new Pair(name, value));
        }
        pairs.sort(Comparator.comparing(Pair::name)
                .thenComparing(Pair::value));
        List<String> encoded = new ArrayList<>(pairs.size());
        for (Pair pair : pairs) {
            encoded.add(pair.name() + "=" + pair.value());
        }
        return String.join("&", encoded);
    }

    private static String canonicalComponent(String raw) {
        // Raw component chỉ nhận ASCII unreserved hoặc %HH.
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        for (int i = 0; i < raw.length(); i++) {
            char ch = raw.charAt(i);
            if (unreserved(ch)) {
                bytes.write((byte) ch);
            } else if (ch == '%') {
                if (i + 2 >= raw.length()) {
                    throw new IllegalArgumentException("Broken percent escape");
                }
                int hi = Character.digit(raw.charAt(i + 1), 16);
                int lo = Character.digit(raw.charAt(i + 2), 16);
                if (hi < 0 || lo < 0
                        || raw.charAt(i + 1) > 127
                        || raw.charAt(i + 2) > 127) {
                    throw new IllegalArgumentException("Invalid hex escape");
                }
                bytes.write((hi << 4) | lo);
                i += 2;
            } else {
                throw new IllegalArgumentException(
                        "Raw query character must be percent-encoded");
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
            throw new IllegalArgumentException("Invalid UTF-8", ex);
        }
        if (decoded.codePoints().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException("Control character in query");
        }

        StringBuilder result = new StringBuilder();
        for (byte b : decoded.getBytes(StandardCharsets.UTF_8)) {
            int v = b & 0xff;
            if (unreserved((char) v)) {
                result.append((char) v);
            } else {
                result.append('%');
                result.append("0123456789ABCDEF".charAt(v >>> 4));
                result.append("0123456789ABCDEF".charAt(v & 0x0f));
            }
        }
        return result.toString();
    }

    private static boolean unreserved(char c) {
        return (c >= 'A' && c <= 'Z')
                || (c >= 'a' && c <= 'z')
                || (c >= '0' && c <= '9')
                || c == '-' || c == '.' || c == '_' || c == '~';
    }

    public static byte[] canonicalRequest(Request r)
            throws GeneralSecurityException {
        if (r == null || r.rawBody() == null
                || !safe(r.method(), 16)
                || !r.method().matches("[A-Z]+")
                || !safe(r.rawPath(), 2048)
                || !r.rawPath().matches("/v1/[A-Za-z0-9_-]+"
                        + "(?:/[A-Za-z0-9_-]+)*")
                || !safe(r.clientId(), 64)
                || !r.clientId().matches("[A-Za-z0-9_-]+")
                || !safe(r.keyId(), 64)
                || !r.keyId().matches("[A-Za-z0-9_-]+")
                || !safe(r.timestamp(), 20)
                || !r.timestamp().matches("[1-9][0-9]{0,18}")
                || !safe(r.nonce(), 43)) {
            throw new IllegalArgumentException("Invalid signed fields");
        }
        String ct = r.contentType() == null ? ""
                : line(r.contentType(), 128).trim()
                        .toLowerCase(Locale.ROOT);
        String bodyHash = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                        .digest(r.rawBody()));
        String text = String.join("\n",
                "hmac-v1-query", r.method(), r.rawPath(),
                canonicalQuery(r.rawQuery()), ct,
                r.clientId(), r.keyId(), r.timestamp(),
                r.nonce(), bodyHash);
        return text.getBytes(StandardCharsets.UTF_8);
    }

    private static String line(String s, int max) {
        if (!safe(s, max)) {
            throw new IllegalArgumentException("Unsafe canonical field");
        }
        return s;
    }

    private static boolean safe(String s, int max) {
        return s != null && !s.isEmpty() && s.length() <= max
                && s.chars().noneMatch(c -> c < 0x20 || c == 0x7f);
    }

    public static byte[] hmac(byte[] secret, byte[] data)
            throws GeneralSecurityException {
        if (secret == null || secret.length != 32) {
            throw new IllegalArgumentException("Secret must be 32 bytes");
        }
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(data);
    }

    public static String sign(Request r, byte[] secret)
            throws GeneralSecurityException {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(hmac(secret, canonicalRequest(r)));
    }

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
        byte[] expected = hmac(secret, canonicalRequest(r));
        return MessageDigest.isEqual(expected, received);
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected validation failure");
        } catch (IllegalArgumentException expected) {
            // Pass: query bị từ chối đúng hợp đồng.
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        String q1 = "z=9&note=hello%20world&item=caf%C3%A9";
        String q2 = "item=caf%C3%A9&z=9&note=hello%20world";
        String sorted = "item=caf%C3%A9&note=hello%20world&z=9";
        require(canonicalQuery(q1).equals(sorted), "Sort + UTF-8");
        require(canonicalQuery(q2).equals(sorted), "Order equivalence");
        require(canonicalQuery("x=%41").equals("x=A"), "Unreserved");
        require(canonicalQuery("x=%2f").equals("x=%2F"), "Uppercase hex");
        require(canonicalQuery("q=1%2B2").equals("q=1%2B2"), "Plus");
        require(canonicalQuery("x=").equals("x="), "Empty value");
        require(canonicalQuery(null).isEmpty(), "Absent query");

        expectInvalid(() -> canonicalQuery("x"));
        expectInvalid(() -> canonicalQuery(""));
        expectInvalid(() -> canonicalQuery("a=1&a=2"));
        expectInvalid(() -> canonicalQuery("a=1&%61=2"));
        expectInvalid(() -> canonicalQuery("q=hello+world"));
        expectInvalid(() -> canonicalQuery("q=%C3%28"));
        expectInvalid(() -> canonicalQuery("x=%G1"));

        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret); // Key test.
        Request original = new Request(
                "GET", "/v1/orders", q1, null,
                "merchant-17", "key-2026-11", "1795824000",
                "b75sZVQmhTBcfnX-bNbGqw", new byte[0]);
        Request reordered = new Request(
                original.method(), original.rawPath(), q2,
                original.contentType(), original.clientId(),
                original.keyId(), original.timestamp(),
                original.nonce(), original.rawBody());
        String signature = sign(original, secret);
        require(verifyMac(reordered, secret, signature),
                "Sorted query must produce same MAC");

        Request changed = new Request(
                original.method(), original.rawPath(),
                "z=9&note=hello%21world&item=caf%C3%A9",
                original.contentType(), original.clientId(),
                original.keyId(), original.timestamp(),
                original.nonce(), original.rawBody());
        require(!verifyMac(changed, secret, signature),
                "Query modification must fail");
        System.out.println("PASS canonical query / HMAC checks");
    }
}
~~~

Lưu nội dung chương trình thành `CanonicalQueryDemo.java`, chạy bằng JDK 17 trở lên:

~~~bash
javac CanonicalQueryDemo.java
java CanonicalQueryDemo
~~~

Kết quả mong đợi:

~~~text
PASS canonical query / HMAC checks
~~~

### 6.1. Phạm vi của chương trình

Ví dụ chủ yếu **chứng minh canonical query và MAC tương thích khi đảo thứ tự tham số**, đồng thời từ chối dữ liệu mơ hồ. Nó **không** là HMAC HTTP filter hoàn chỉnh:

- `Request` không phải object bất biến sâu vì `byte[]` có thể bị thay đổi qua tham chiếu; adapter phải snapshot buffer đúng thời điểm.
- `canonicalRequest` chưa xác minh nonce thực sự có định dạng Base64URL và chưa kiểm tra timestamp theo clock server. Trong production phải kiểm tra cả hai theo hợp đồng.
- Chưa giới hạn `rawBody` ở mức HTTP; adapter phải chặn request quá lớn trước khi buffer/hash.
- Không tự đảm bảo path/query có cùng ý nghĩa với router downstream; điểm lấy `rawPath` và `rawQuery` phải được kiểm tra qua gateway và container.
- Tên/giá trị query sau canonicalization chưa được gắn vào parser nghiệp vụ; **business handler phải dùng một parser có semantics tương thích và không tái diễn giải dữ liệu theo form-urlencoded trái hợp đồng**.
- `verifyMac` chỉ kiểm tra tag; receiver còn phải tra khóa, trạng thái `ACTIVE/VERIFY_ONLY/REVOKED`, audience, timestamp, nonce và authorization.
- Secret sinh bằng `SecureRandom` ở `main` chỉ dành cho test; trong production khóa được cấp và lưu qua secret manager/KMS.

Để kiểm chứng thuật toán mật mã **độc lập** với cả sender và receiver mẫu, nên chạy thêm test vector RFC 4231 cho HMAC-SHA-256. Một test tự ký rồi tự verify chỉ chứng minh hai lời gọi đồng ý với nhau, không chứng minh hợp đồng byte đúng với hệ thống bên ngoài.

## 7. Kiểm thử canonical query theo từng nhóm

### 7.1. Golden fixtures

| Test đầu vào | Canonical mong đợi | Ý nghĩa |
|---|---|---|
| `b=2&a=1` | `a=1&b=2` | Sắp xếp |
| `a=1&b=2` | `a=1&b=2` | Idempotence |
| `name=%41lice` | `name=Alice` | Decoding unreserved |
| `path=%2fadmin` | `path=%2Fadmin` | Hex uppercase |
| `q=hello%20world` | `q=hello%20world` | Khoảng trắng |
| `q=%E1%BA%A1` | `q=%E1%BA%A1` | UTF-8 hợp lệ |
| `q=%25` | `q=%25` | Dấu phần trăm được encode |
| `id=` | `id=` | Giá trị rỗng |
| Query absent | Chuỗi rỗng | Không có query |

**Cần tạo golden fixture độc lập** thay vì tạo expected bằng cùng helper đang kiểm tra. Nếu client và server dùng chung một lỗi sort hoặc encode, test sign–verify vẫn có thể pass.

### 7.2. Negative test: các chuỗi phải bị từ chối

| Đầu vào | Lý do |
|---|---|
| `a` | Thiếu dấu bằng |
| `=1` | Tên rỗng |
| `a=1=2` | Dấu bằng thô thứ hai |
| `a=1&&b=2` | Segment rỗng |
| `a=1&` | Dấu ampersand cuối |
| `a=1&a=2` | Duplicate name |
| `a=1&%61=2` | Duplicate sau decode |
| `q=hello+world` | Dấu cộng thô ngoài grammar |
| `q=hello world` | Khoảng trắng thô |
| `q=%ZZ` | Escape không hợp lệ |
| `q=%A` | Escape thiếu chữ số hex |
| `q=%C3%28` | UTF-8 lỗi |
| `q=%00` | Ký tự điều khiển NUL |
| Query rỗng sau `?` | Ngoài hợp đồng |
| Query vượt giới hạn length/parameter count | Chống tài nguyên tiêu thụ quá mức |

### 7.3. Negative test: giả mạo sau khi ký

Từ request đã có MAC hợp lệ, thay **một** tham số quan trọng rồi giữ nguyên chữ ký:

~~~text
Original: amount=150000&currency=VND
Changed:  amount=900000&currency=VND
Expected: invalid_signature
~~~

Các trường hợp khác: thêm `admin=true`, bỏ `tenantId`, đổi encoding `%2F` thành chuỗi dữ liệu khác, đổi method/path, thay body hoặc metadata `X-Client-Id/X-Key-Id`. Nếu thay **chỉ thứ tự** query mà contract sắp xếp tham số, MAC nên **vẫn hợp lệ**; đó là hành vi chủ đích, không phải lỗi. Nếu ứng dụng **phụ thuộc thứ tự** tham số, cần đổi hợp đồng sang giữ thứ tự hoặc quy định một grammar khác.

### 7.4. Property-based và fuzz testing

Ngoài fixtures cố định, một số tính chất có thể test với input hợp lệ:

1. **Determinism:** cùng query → cùng canonical bytes.
2. **Idempotence với query hợp lệ:** canonical query khi đưa qua chính canonicalizer lại phải giữ nguyên, ví dụ `C(C(q)) = C(q)`.
3. **Order independence trong hợp đồng này:** đảo thứ tự các cặp tên duy nhất không đổi output.
4. **Percent-encoding normalization:** các escape tương đương cho unreserved cho cùng output.
5. **Không chấp nhận malformed input:** percent escape sai, UTF-8 sai, duplicate sau decode phải reject.
6. **MAC binding:** đổi canonical query làm MAC khác với xác suất áp đảo, trừ khi hai input khác raw bytes nhưng **cùng canonical query** theo hợp đồng.

Fuzzer có thể sinh byte/chuỗi độc hại hoặc dữ liệu quá dài; chỉ chạy trong môi trường test có giới hạn CPU, RAM, request size và thời gian. Không dùng production secret.

## 8. Gateway/proxy: khi nào canonical query bị đổi?

Trong hệ thống phân tán, request đi qua nhiều lớp:

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant G as Gateway / Proxy
    participant V as HMAC verifier
    participant R as Router / Business
    S->>S: Canonicalize query và ký request
    S->>G: HTTPS path?rawQuery + signature
    G->>G: Có thể rewrite URI, query, header
    G->>V: Request tại ranh giới verifier
    V->>V: Canonicalize cùng hợp đồng
    V->>V: Kiểm tra MAC, timestamp, nonce
    V->>R: Authenticated principal + request
    R->>R: Parse tham số và kiểm tra quyền
~~~

| Thay đổi ở proxy/framework | Tác động lên chữ ký hoặc nghiệp vụ | Cách xử lý |
|---|---|---|
| Sắp xếp lại thứ tự cặp query | Hợp đồng sort có thể giữ MAC; raw-query contract thì không | Chốt rõ thuật toán; test qua proxy thật |
| Đổi `%2f` thành `%2F` | Với hợp đồng này có thể giữ canonical query | Xác nhận downstream hiểu cùng giá trị |
| Đổi `%2F` thành literal `/` | Ví dụ này reject literal slash ở component | Không bỏ kiểm tra; verify trước biến đổi |
| Đổi `+` thành khoảng trắng | Khác biệt form vs URI query | Reject raw plus hoặc dùng contract form rõ ràng |
| Gộp duplicate param, chỉ lấy last value | Có thể bỏ qua tham số attacker chèn | Reject duplicate name trước business parser |
| Gỡ/thêm tham số tracking hoặc rewrite `page` | Nội dung đã ký thay đổi | Verify trước rewrite hoặc ký representation được chỉ rõ |
| Thay đổi encoded path | Canonical query đúng nhưng canonical request vẫn khác | Ký path và query đúng điểm verify |
| HTTP/2 → HTTP/1.1 | Giá trị `:path` được chuyển thành request target | Kiểm tra việc bảo toàn path/query ở edge |

**Không tin `X-Original-URI` hoặc `X-Forwarded-*` do internet client tự gửi.** Khi cần truyền nguyên request target trước rewrite, proxy đáng tin phải **strip các header do client khai, tự thêm metadata được kiểm soát** và chuyển qua kết nối nội bộ có xác thực. Cân nhắc verify HMAC tại edge **trước khi normalize** để giảm rủi ro sai khác.

### 8.1. Hai lớp phải hiểu cùng một query

Một lỗi nguy hiểm:

~~~text
Verifier parse: role=user&role=admin -> chỉ lấy role=user
Business parse: role=user&role=admin -> chỉ lấy role=admin
~~~

Nếu verifier ký/trừu tượng hóa một giá trị nhưng handler sử dụng giá trị khác, attacker có thể nhắm vào **HTTP parameter pollution** hoặc lỗi phân quyền dù HMAC được tính đúng cho chuỗi mà verifier nhìn thấy. Quy tắc bài này **reject duplicate name sau canonicalization** để loại bỏ trường hợp đơn giản. Với endpoint có tham số nhiều giá trị, cần bảo đảm **tất cả giá trị được ký và diễn giải đúng**.

Đừng chỉ kiểm tra rằng MAC vẫn pass sau proxy: cần kiểm thử **giá trị cuối cùng mà business handler nhận**. Nếu query được dùng làm ID tenant/tài nguyên, authorization phải dựa trên ID đã parse ở tầng xử lý thực, không dựa vào bản ghi query khác.

## 9. Timestamp, nonce và key rotation: canonical query không thay thế chúng

Một query được ký đúng vẫn có thể bị **replay**:

~~~text
Attacker ghi lại request + tag hợp lệ
Attacker gửi lại cùng path, canonical query, timestamp và nonce
HMAC vẫn khớp nếu receiver chỉ tính MAC
~~~

Receiver nên áp dụng một pipeline:

~~~mermaid
flowchart TD
    A["Nhận request"] --> B["Validate URI/query/header/body framing"]
    B --> C["Lookup key theo clientId/keyId/audience"]
    C --> D{"Key được phép VERIFY?"}
    D -- Không --> X["Reject auth"]
    D -- Có --> E["Kiểm tra timestamp trong cửa sổ"]
    E --> F{"Timestamp hợp lệ?"}
    F -- Không --> X
    F -- Có --> G["Canonical path + query + headers + body"]
    G --> H["HMAC-SHA-256 và so tag"]
    H --> I{"MAC đúng?"}
    I -- Không --> X
    I -- Có --> J["Atomic reserve nonce có TTL"]
    J --> K{"Nonce chưa dùng?"}
    K -- Không --> X
    K -- Có --> L["Authenticated principal"]
    L --> M["Authorization theo action/resource/tenant"]
~~~

Một chính sách ví dụ:

~~~text
nowSeconds - 300 <= signedTimestamp <= nowSeconds + 300
nonceScope = (clientId, keyId, nonce)
reserve atomically bằng SET nonceKey 1 NX EX 600
~~~

Kho nonce phải chia sẻ giữa các verifier node; nếu không thể kiểm tra tính mới, hệ thống nên **fail closed** theo chính sách. Chỉ ghi nhận nonce sau khi chữ ký hợp lệ để attacker không chiếm nonce bằng MAC giả. TTL phải đủ bao phủ thời gian timestamp còn có thể hợp lệ. Người đã biết secret vẫn có thể ký request mới với timestamp/nonce mới, nên cần giữ secret đủ mạnh và quản lý khóa an toàn.

**Key rotation** cũng là bước riêng: mỗi `X-Key-Id` chọn đúng secret của client/audience; `ACTIVE` được verify; `VERIFY_ONLY` chỉ verify trong cửa sổ chuyển tiếp; `REVOKED` bị từ chối kể cả MAC đúng. Không thử khóa mặc định hoặc khóa của tất cả tenant khi lookup thất bại.

## 10. Authentication khác authorization đối với query

Ví dụ:

~~~http
GET /v1/payments?merchantId=42&status=PAID HTTP/1.1
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <valid-hmac-for-this-exact-request>
~~~

Giả sử merchant 17 **thực sự biết secret** của mình và đã ký đúng cả `merchantId=42`:

~~~text
Authentication:
    principal = merchant-17
    canonicalQuery = merchantId=42&status=PAID
    MAC = valid

Authorization:
    requestedMerchant = 42
    principalMerchant = 17
    policy = merchant chỉ đọc dữ liệu thuộc quyền của mình
    decision = DENY
~~~

HMAC đúng nghĩa là **nội dung query được bảo toàn**, không có nghĩa nội dung query được **cho phép**. Server phải kiểm tra quyền theo tài nguyên thực, tenant, action và dữ liệu đã parse. Nếu business code tin rằng HMAC hợp lệ tức có quyền đọc mọi `merchantId`, đó là lỗi phân quyền.

Đối với request tạo giao dịch, nên có **idempotency key** do business quản lý để tránh retry hợp lệ (với nonce mới) tạo giao dịch lặp. Trường idempotency ảnh hưởng hành vi cần nằm trong dữ liệu ký theo hợp đồng.

## 11. Checklist thiết kế và kiểm thử

| Nhóm | Câu hỏi kiểm tra |
|---|---|
| **Contract** | Query ký raw hay canonical? Có sort, decode, NFC, duplicate, empty và multi-value rules không? |
| **Bytes** | UTF-8, percent-encoding, chữ hoa hex và `+`/`%20` có được định nghĩa chính xác không? |
| **URI** | Path, query, Host/audience có được ràng buộc đúng hay chỉ ký body? |
| **Input validation** | Có từ chối malformed percent escape, UTF-8 sai, duplicate key, query quá dài hoặc header ký trùng không? |
| **Cryptography** | Dùng chuẩn HMAC-SHA-256, secret ngẫu nhiên đủ entropy, MAC đủ 32 byte, so tag an toàn không? |
| **Key lookup** | Client ID/key ID/audience có đúng record và trạng thái rotation không? |
| **Replay** | Timestamp đã ký, nonce mới, kho nonce atomic và fail closed qua nhiều node không? |
| **Gateway** | Proxy có rewrite target/query, dùng form parser hay đổi encoding không? |
| **Business** | Parser sau verifier có diễn giải query giống contract không? |
| **Authorization** | Principal có quyền với resource/tenant được chọn bằng query không? |
| **Golden fixture** | Expected canonical query có được viết độc lập với code sign/verify không? |

### 11.1. Những lỗi triển khai thường gặp

1. **Chỉ hash query bằng SHA-256:** hash không khóa không chứng minh người gửi.
2. **Không ký query:** thay limit/filter/resource ID mà HMAC body vẫn khớp.
3. **Sắp xếp khi contract yêu cầu raw query:** chữ ký sai với đối tác.
4. **Dùng `URLEncoder`/`URLDecoder` nhưng không xét form semantics:** `+` bị biến thành space.
5. **Double-decode percent encoding:** `%252F` có thể bị hiểu nhầm thành slash.
6. **Chấp nhận duplicate keys mà parser khác nhau:** verifier và handler kiểm tra giá trị khác nhau.
7. **Sort raw encoding thay vì canonical encoded name:** `%41` và `A` có thể ra thứ tự hoặc cách so không mong đợi.
8. **Tự normalize Unicode không có trong contract:** hai phía tính byte khác nhau.
9. **Lấy request target sau gateway rewrite mà không có kế hoạch:** chữ ký thất bại hoặc ký nhầm request.
10. **Kết luận MAC hợp lệ là được phép truy cập:** bỏ qua phân quyền theo tenant/tài nguyên.

## 12. Bài tập vận dụng

**Bài 1 — Sort và encode:** Với raw query `b=hello%20world&z=9&a=%41`, hãy tìm canonical query theo `hmac-v1-query`, giải thích vì sao `%41` trở thành `A`.

**Bài 2 — Dấu cộng:** Phân tích `q=1+2`, `q=1%2B2` và `q=1%202`. Chuỗi nào bị từ chối trong contract của bài, và hai chuỗi còn lại có cùng giá trị không?

**Bài 3 — Duplicate:** Server nhận `role=user&%72ole=admin`. Hãy trình bày tên sau percent decode, lý do phải reject và nguy cơ nếu gateway chọn first value nhưng service chọn last value.

**Bài 4 — Dấu hỏi cuối:** Với `/v1/orders`, `/v1/orders?`, `/v1/orders?x=`, hãy nêu canonical query hoặc lý do reject.

**Bài 5 — Cross-language:** Client Java ký `name=caf%C3%A9`, backend ngôn ngữ khác parse theo form-urlencoded và normalize Unicode. Hãy xác định những byte nào cần so bằng golden fixture, và chọn quy tắc nào để hai bên tương thích.

**Bài 6 — Gateway rewrite:** Client ký `POST /external/payments?b=2&a=1`; gateway bỏ prefix và reorder query. Theo hợp đồng sắp xếp query, biến đổi nào có thể giữ canonical query, biến đổi nào làm canonical request khác? Bạn sẽ đặt verifier ở đâu?

**Bài 7 — Replay:** Một request có canonical query và HMAC hoàn toàn đúng nhưng timestamp cũ. Receiver phải làm gì? Vì sao canonical query không thay thế nonce store?

**Bài 8 — Phân quyền:** Merchant A ký request `GET /payments?merchantId=B` bằng secret của A. MAC vẫn đúng. Kiểm tra nào quyết định trả `403`?

## 13. Kết luận

**Canonical query** là quy tắc biến các tham số query thành **một chuỗi byte xác định** trước khi đưa vào chữ ký HMAC. Quy tắc cần nói rõ thứ tự, percent-encoding, UTF-8, dấu cộng, dấu bằng, tham số rỗng, duplicate và giới hạn đầu vào; đồng thời phải **khớp semantics của router/business handler**. Một ví dụ sort-and-encode có thể làm các raw query khác nhau nhưng tương đương cùng một MAC, còn các biến đổi ảnh hưởng tài nguyên phải khiến chữ ký không hợp lệ. Khi triển khai HMAC request authentication, canonical query phải được sử dụng cùng method/path/header/body, quản lý secret/key rotation, timestamp/nonce chống replay, kiểm thử proxy/gateway và **authorization độc lập**.

**Tài liệu tham khảo:**

- [RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986): query, percent-encoding và ký tự unreserved.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): target URI, phương thức và HTTP request semantics.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): request target và intermediary.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): pseudo-header `:path`.
- [RFC 2104 — HMAC](https://www.rfc-editor.org/rfc/rfc2104): keyed-hash message authentication.
- [RFC 4231 — HMAC-SHA-256 test vectors](https://www.rfc-editor.org/rfc/rfc4231): bộ giá trị tham khảo để kiểm tra MAC độc lập.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): tham khảo chuẩn ký các thành phần HTTP. Hợp đồng `hmac-v1-query` là **ví dụ riêng**, không tự nhận tuân thủ RFC 9421 hoặc bất cứ đặc tả chữ ký nhà cung cấp nào.
