# Header name lowercase: Chuẩn hóa tên header khi ký HTTP request bằng HMAC

Trong HTTP, **tên trường header (*field name*) không phân biệt chữ hoa và chữ thường**. Vì vậy `X-Key-Id`, `x-key-id` và `X-KEY-ID` là những cách viết của **cùng một tên trường** trong ngữ nghĩa HTTP. Nhưng hàm HMAC chỉ nhận **chuỗi byte**: nếu client ghép `X-Key-Id:...` vào canonical request còn server ghép `x-key-id:...`, hai bên sẽ tính ra hai MAC khác nhau dù cùng shared secret, HTTP method, URI và body.

**Header name lowercase** là quy tắc canonicalization giúp loại bỏ sai khác không có ý nghĩa ở **tên header**: chuyển tên về chữ thường ASCII trước khi dựng chuỗi ký. Quy tắc này **không có nghĩa** tự đổi chữ hoa/thường, xóa khoảng trắng hoặc sắp xếp lại **giá trị header**. Quan trọng hơn, nó phải đi cùng chính sách về **danh sách header được ký, header trùng, thứ tự và nguồn dữ liệu tin cậy**.

Bài thuộc chương **Header canonicalization** của module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Trong module này, người học thiết kế xác thực HTTP bằng **HMAC với shared secret**, canonical request chứa phương thức, URI, header hoặc body theo hợp đồng ký; xác minh chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt xác thực với phân quyền. Ở đây, điểm trọng tâm là **tên header ở dạng lowercase** và các điều kiện để quy tắc đó thực sự bảo vệ request.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích tính **case-insensitive** của HTTP header field names, phân biệt với tính **case-sensitive** của byte trong HMAC và nhiều **header values**.
2. Chuẩn hóa tên header về **lowercase ASCII**, không phụ thuộc locale và không sửa giá trị ngoài hợp đồng.
3. Xây dựng tập header được ký theo thứ tự xác định; phát hiện header **trùng tên sau khi lowercase** và từ chối dạng nhập nhằng.
4. Phân tích HTTP/1.1 so với HTTP/2/HTTP/3, pseudo-header, `Host`/`:authority`, OWS và những thay đổi do proxy/gateway.
5. Viết ví dụ Java 17 sử dụng `javax.crypto.Mac`, xử lý nhiều biến thể chữ hoa của header name và xác minh full HMAC-SHA256.
6. Đặt header canonicalization vào quy trình kiểm tra timestamp/nonce, key rotation, authorization và kiểm thử end-to-end.

## 2. Header field name là gì?

Ví dụ một HTTP request:

```http
POST /v1/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a-202611
X-Timestamp: 2026-11-28T02:00:00Z
X-Nonce: Zq8DxKtUokcwPGNj3d_yvQ

{"sku":"BK-42","quantity":2}
```

Trong dòng `X-Key-Id: partner-a-202611`:

- `X-Key-Id` là **tên header field**.
- Dấu `:` phân cách tên và giá trị trong cú pháp HTTP/1.1.
- `partner-a-202611` là **giá trị** của trường đó. Giá trị này có thể là định danh credential cần khớp chính xác với registry.
- Khoảng trắng sau dấu `:` thuộc cú pháp biểu diễn HTTP; cách nó được xử lý khi canonicalization **phải có quy tắc riêng**.

Theo ngữ nghĩa HTTP, **field names là case-insensitive**. Các cách viết sau có cùng tên trường:

```http
X-Key-Id: partner-a-202611
x-key-id: partner-a-202611
X-KEY-ID: partner-a-202611
```

Ba dòng trên **không phải ví dụ nên gửi cả ba trong một request**. Nếu cùng xuất hiện, chúng là **nhiều lần xuất hiện của cùng field name**; đối với trường bảo mật như `x-key-id`, bài này sẽ **từ chối duplicate**, kể cả khi các giá trị giống nhau.

### So sánh tên với giá trị

| Dữ liệu | Có thể lowercase để canonicalize? | Giải thích |
| --- | --- | --- |
| `Content-Type` → `content-type` | **Có**, ở phần **field name**. | Tên header không phân biệt case. |
| `X-Key-ID` → `x-key-id` | **Có**, ở phần **field name**. | `ID` trong **tên** chỉ là ký tự của tên trường. |
| `partner-A-202611` → `partner-a-202611` | **Không**, trừ khi credential contract quy định như vậy. | Đây là **giá trị key ID**; đổi case có thể chọn credential khác. |
| `X-Nonce` → `x-nonce` | **Có**, ở phần **field name**. | Giữ nguyên nonce ở phần value. |
| `AbCd_9+/==` (giá trị chữ ký/Base64) | **Không**. | Base64 phân biệt chữ hoa/thường; đổi case tạo bytes khác. |
| `"order-42-v7"` (giá trị `If-Match`) | **Không**. | ETag là token opaque; không được tùy tiện biến đổi. |
| `Content-Type: Application/JSON` | **Không tự lowercase toàn bộ value**. | Một số cú pháp giá trị có quy tắc case-insensitive riêng, nhưng canonical contract V1 có thể yêu cầu đúng `application/json` và từ chối dạng khác. |

**Nguyên tắc:** Hãy phân biệt **chuẩn hóa tên header theo cú pháp HTTP** và **chuẩn hóa giá trị theo từng header cụ thể**. Không thể áp dụng cùng một hàm lowercase cho cả hai.

## 3. Vì sao lowercase tên header giúp HMAC ổn định?

Giả sử client và server cùng dùng secret và thông điệp có một dòng header:

```text
X-Key-Id:partner-a-202611
```

```text
x-key-id:partner-a-202611
```

Hai chuỗi khác byte (ký tự `X` và `x` có mã byte khác nhau); HMAC-SHA256 sẽ tạo hai tag khác nhau. Nhưng theo HTTP, chúng biểu diễn cùng tên trường, nên việc bị từ chối chỉ vì cách viết hoa tên là lỗi tương thích không cần thiết.

Với quy tắc lowercase ASCII, cả hai bên tạo ra cùng dạng:

```text
x-key-id:partner-a-202611
```

Cần áp dụng quy tắc này **trước khi nối các header vào canonical request**. Các bước cơ bản:

1. HTTP parser tin cậy cung cấp từng **field name** và **field value** đã được phân tích đúng cú pháp.
2. Kiểm tra field name hợp lệ theo token grammar của HTTP; tên không được chứa khoảng trắng, dấu `:` hoặc ký tự điều khiển.
3. Chuyển **chỉ tên** sang lowercase ASCII; tên chuẩn này dùng làm khóa tra cứu trường.
4. Phát hiện trường bắt buộc bị thiếu hoặc xuất hiện **nhiều lần dưới bất kỳ cách viết hoa nào**.
5. Kiểm tra **giá trị** theo hợp đồng riêng (độ dài, loại ký tự, định dạng, OWS, CR/LF).
6. Ghép các cặp `lowercase-name:value` vào canonical request theo **thứ tự cố định được công bố**, rồi mã hóa UTF-8 và tính HMAC.

### Chọn cách lowercase an toàn

Tên trường HTTP được định nghĩa bằng tập ký tự token ASCII; không nên dùng phép biến đổi Unicode tùy ý để chấp nhận tên không hợp lệ. Có thể làm một trong hai cách:

- Xác thực tên chỉ chứa ký tự `tchar` của HTTP, rồi áp dụng `name.toLowerCase(Locale.ROOT)`.
- Hoặc chuyển trực tiếp từng ký tự ASCII `A`–`Z` thành `a`–`z`; giữ nguyên các ký tự token ASCII khác và **từ chối** đầu vào ngoài token grammar.

Tại sao không dùng `toLowerCase()` không đối số? Nó phụ thuộc **default locale** của JVM. Với locale có cách viết hoa đặc biệt, ví dụ Turkish, ký tự `I` có thể biến thành ký tự Unicode ngoài ASCII, khiến canonical bytes khác nhau giữa các môi trường. Dùng `Locale.ROOT` sau khi validate ASCII, hoặc dùng phép lowercase ASCII tường minh, để tránh lỗi này.

## 4. HTTP/1.1, HTTP/2 và HTTP/3 khác nhau thế nào?

| Giao thức | Quy tắc tên header | Tác động với canonical request |
| --- | --- | --- |
| **HTTP/1.1** | Field names không phân biệt case; trên wire có thể viết `X-Key-Id` hoặc `x-key-id`. | Canonicalizer lowercase tên sau khi parser đọc, không coi khác case là tên khác. |
| **HTTP/2** | Field names **phải dùng lowercase** khi mã hóa trong HTTP/2; tên có chữ hoa làm message malformed. Có pseudo-header như `:method`, `:path`, `:authority`. | Gateway cần từ chối message không hợp lệ ở tầng HTTP/2; HMAC contract dùng giá trị field hợp lệ và pseudo-header theo quy tắc rõ. |
| **HTTP/3** | Field names trên HTTP/3 cũng dùng lowercase và có các pseudo-header liên quan. | Cần bảo toàn ngữ nghĩa khi gateway chuyển giữa HTTP/3 và HTTP/1.1. |

Việc tên header bắt buộc lowercase trong HTTP/2/3 **không thay thế** contract HMAC. Một request HTTP/1.1 vẫn có thể tới gateway, và server vẫn cần xây canonical bytes ổn định. Ngược lại, server không được “sửa chữa” một HTTP/2 message malformed có tên chữ hoa rồi bỏ qua validation giao thức.

### Header thông thường và pseudo-header

`:method` và `:path` là **pseudo-header** trong HTTP/2/3, không phải field name thông thường để client tự tạo dưới tên `:method` trong HTTP/1.1. Contract HMAC phải xác định method và request target được lấy từ **thành phần HTTP đáng tin cậy**, không từ một header bất kỳ có tên giống như vậy.

`Host` trong HTTP/1.1 và `:authority` trong HTTP/2/3 có thể liên quan đến host/virtual routing. Nếu host quyết định tenant hoặc resource, một giao thức ký phải ràng buộc **authority tin cậy** hoặc audience phù hợp theo quy tắc rõ ràng. Chỉ lowercase **tên** `host` không quyết định cách chuẩn hóa **giá trị host**, cổng, IDN hoặc TLS termination.

Trong ví dụ V1 ở bài này, canonical request chứa audience cố định `orders-api-prod` và gateway kiểm tra host/authority được route đúng dịch vụ trước khi xác thực. Nếu một secret được dùng ở nhiều host có ngữ nghĩa khác nhau, phải mở rộng hợp đồng ký để bảo vệ host/authority có ý nghĩa, không dựa vào lowercase tên để chống cross-service replay.

## 5. Danh sách header được ký và thứ tự canonical

Để tránh việc thay đổi header có ảnh hưởng đến bảo mật mà chữ ký vẫn hợp lệ, giao thức nên **liệt kê chính xác các header được ký**. Hợp đồng minh họa **HMAC-SHA256-V1** cho endpoint `POST /v1/orders` dùng:

| Tên chuẩn lowercase | Giá trị kỳ vọng trong ví dụ | Tại sao phải ký? |
| --- | --- | --- |
| `content-type` | `application/json` | Gắn chữ ký với cách diễn giải request body. |
| `x-key-id` | `partner-a-202611` | Gắn request với credential version dùng để tra secret. |
| `x-timestamp` | `2026-11-28T02:00:00Z` | Ngăn attacker thay timestamp mà giữ tag. |
| `x-nonce` | `Zq8DxKtUokcwPGNj3d_yvQ` | Ngăn attacker thay nonce mà giữ tag; hỗ trợ chống replay. |

Bài chọn **thứ tự cố định** của các field được ký là:

```text
content-type
x-key-id
x-timestamp
x-nonce
```

Đây là quyết định của protocol V1; cũng có thể chọn sắp xếp từ điển (lexicographic order) nếu hợp đồng quy định, nhưng **không được mỗi client tự chọn một thứ tự**. Thứ tự xuất hiện trên HTTP wire **không quyết định** thứ tự trong canonical request V1.

**Header signature** `X-Signature` được kiểm tra định dạng và tính duy nhất, nhưng không tự xuất hiện trong dữ liệu ký: nếu ký chính nó sẽ tạo vòng phụ thuộc. Vì vậy signed header set và các header cần validation không nhất thiết là một tập giống hệt nhau.

### Ví dụ case và order

Hai request (giả sử các phần khác hoàn toàn giống nhau) phải tạo **cùng canonical header block**:

```http
Content-Type: application/json
X-Key-ID: partner-a-202611
X-Timestamp: 2026-11-28T02:00:00Z
X-Nonce: Zq8DxKtUokcwPGNj3d_yvQ
```

```http
x-NONCE: Zq8DxKtUokcwPGNj3d_yvQ
x-timestamp: 2026-11-28T02:00:00Z
content-TYPE: application/json
x-key-id: partner-a-202611
```

Cả hai tạo cùng block:

```text
content-type:application/json
x-key-id:partner-a-202611
x-timestamp:2026-11-28T02:00:00Z
x-nonce:Zq8DxKtUokcwPGNj3d_yvQ
```

**Chú ý:** Header names lowercase và thứ tự cố định là hai quy tắc **riêng biệt**. Nếu đổi giá trị của `x-key-id` hay `x-nonce`, MAC phải thay đổi dù tên vẫn như cũ.

## 6. Duplicate header, OWS và giá trị nhập nhằng

Một hợp đồng bảo mật không thể chỉ chạy `toLowerCase()` rồi gọi là hoàn tất. Ví dụ request:

```http
X-Key-Id: partner-a-202611
x-key-id: partner-b-202611
```

Hai dòng trên là **duplicate của cùng header name**, không phải hai credential độc lập. Nếu gateway chọn giá trị đầu, còn backend lấy giá trị cuối, hệ thống có thể xác minh một client nhưng thực thi dưới danh tính khác.

### Vì sao map thông thường có thể che mất duplicate?

Đoạn Java sau **không thích hợp** làm nguồn bằng chứng cho việc header không bị trùng:

```java
// SAI nếu nguồn đã bị chuyển thành map trước khi kiểm tra duplicate:
Map<String, String> receivedHeaders = requestAsMap;
// "X-Key-Id" và "x-key-id" có thể thành hai key khác nhau
// hoặc một key ghi đè key kia, tùy cách dựng map.
```

Kể cả `TreeMap<>(String.CASE_INSENSITIVE_ORDER)` cũng có thể **ghi đè** một giá trị khi hai tên chỉ khác case, làm mất bằng chứng rằng client gửi duplicate. Nên dùng danh sách **từng lần xuất hiện của field** hoặc API HTTP cho phép phát hiện multiple values **trước khi** chuyển sang map canonical.

Một số header được HTTP cho phép biểu diễn bằng nhiều field line hoặc danh sách phân tách dấu phẩy. Nhưng **không phải header nào cũng có quy tắc kết hợp giống nhau**. Với các field bảo mật V1 như `x-key-id`, `x-timestamp`, `x-nonce` và `x-signature`, chính sách đơn giản là **bắt buộc xuất hiện đúng một lần**, không tự ghép bằng dấu phẩy, không “lấy first/last”. Nếu HTTP framework đã gộp duplicate thành một chuỗi mà không thể phát hiện nguồn gốc, cần phát hiện và từ chối tại gateway/parser trước đó.

### OWS (optional whitespace)

Trong HTTP/1.1, OWS thường là khoảng trắng ngang hoặc tab ở vị trí được ngữ pháp cho phép. Ví dụ:

```http
X-Key-Id: partner-a-202611
X-Key-Id:    partner-a-202611
```

Nếu tầng A loại bỏ OWS còn tầng B giữ nguyên chuỗi khác nhau, chữ ký có thể thất bại. Hợp đồng phải nêu rõ cách xử lý: **trim OWS đúng một lần theo định nghĩa** rồi ký, hoặc **từ chối** những biểu diễn không theo dạng được phép. V1 minh họa trong bài chọn **giá trị canonical không có leading/trailing whitespace**, và adapter phải làm cho việc kiểm tra đó có ý nghĩa ở ingress. Không được âm thầm `trim()` tất cả value, nhất là những giá trị mà khoảng trắng có ý nghĩa.

### Header name có whitespace, CR/LF hoặc obs-fold

Các chuỗi như `X-Key-Id : value` (khoảng trắng trước dấu hai chấm) hay xuống dòng nằm trong tên/giá trị không được phép “sửa” bằng hàm lowercase. Các vấn đề **header injection, HTTP request smuggling và obsolete line folding (obs-fold)** phải được HTTP parser/gateway xử lý đúng chuẩn, thường bằng cách từ chối dạng không phù hợp. Canonicalizer ở tầng ứng dụng **không thay thế** việc parse/framing HTTP an toàn.

### Giá trị nào có thể được canonicalize?

Cách xử lý phụ thuộc vào từng field. Chẳng hạn, media type có một số thành phần được định nghĩa case-insensitive, trong khi key ID, nonce, ETag và Base64 có thể phân biệt case. Để đơn giản, V1 yêu cầu chính xác `Content-Type: application/json` về **giá trị sau khi adapter xử lý cú pháp HTTP**. Nếu muốn chấp nhận `Application/JSON`, phải đặc tả cách chuẩn hóa **media type value** riêng và kiểm thử; đừng lowercase tất cả các value.

## 7. Canonical request V1 có header name lowercase

HTTP request mẫu:

```http
POST /v1/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-ID: partner-a-202611
X-Timestamp: 2026-11-28T02:00:00Z
X-Nonce: Zq8DxKtUokcwPGNj3d_yvQ
X-Signature: v1=<BASE64_HMAC>

{"sku":"BK-42","quantity":2}
```

Canonical request được xây theo hợp đồng V1, trong đó tên header lowercase:

```text
HMAC-SHA256-V1
orders-api-prod
POST
/v1/orders
content-type:application/json
x-key-id:partner-a-202611
x-timestamp:2026-11-28T02:00:00Z
x-nonce:Zq8DxKtUokcwPGNj3d_yvQ
sha256:<LOWERCASE_HEX_SHA256_OF_RAW_BODY>
```

Dòng body digest là **SHA-256 của raw body bytes**, không phải HMAC; nó được đưa vào canonical request để ký. Chuỗi `<...>` là placeholder cần thay bằng digest thật; `X-Signature` cũng là placeholder chứ không phải chữ ký hợp lệ.

Quy tắc byte:

1. Hai dòng đầu chính xác `HMAC-SHA256-V1` và audience `orders-api-prod`.
2. Method chính xác `POST`; request target chính xác `/v1/orders` tại điểm xác minh đáng tin cậy.
3. Các header được ký xuất hiện **một lần mỗi field**, được định dạng `lowercase-name:value` **không có dấu cách sau `:`**, theo thứ tự đã công bố.
4. Các giá trị header phải thỏa hợp đồng riêng, không dùng `toLowerCase` cho value.
5. Body digest viết hex chữ thường, từ **bytes body thực nhận**; không parse/serialize lại JSON.
6. Dùng `\n` (LF) để nối các dòng, **không có LF ở cuối**, rồi UTF-8 encode canonical string.
7. Client tính `HMAC-SHA256(secret, canonicalBytes)`, lấy **đầy đủ 32 byte** và chuyển thành Base64 chuẩn có padding, prefix `v1=`.

Nếu client chọn `x-key-id` còn server thấy `X-Key-Id`, hai bên vẫn tạo một dòng `x-key-id:...`. Nếu một value thay đổi, kể cả `partner-a` → `partner-A`, chữ ký cũ không còn hợp lệ.

## 8. Java 17: canonical lowercase, chặn duplicate, tính HMAC

Ví dụ dưới đây sử dụng Java 17 và JCA. Để tập trung vào header names, nó áp dụng **một endpoint minh họa duy nhất**: `POST /v1/orders`, `Content-Type` phải đúng `application/json`, các field bảo mật phải xuất hiện đúng một lần. Những field ngoài danh sách ký được phép tồn tại nếu HTTP adapter đã parse đúng, nhưng không có tác động đến canonical string V1.

**Quan trọng:** `List<Header>` trong ví dụ là **các field occurrence sau khi HTTP parser tin cậy phân tích**, chưa bị map hoặc merge mất duplicate. Ở production phải lấy chúng từ API/adapter có khả năng phân biệt duplicate hoặc chặn tại ingress. Nếu framework đã xóa bằng chứng duplicate, class Java này không thể tự khôi phục.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.HashMap;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HeaderNameLowercaseHmacV1 {
    private static final String ALG = "HmacSHA256";
    private static final String PREFIX = "v1=";
    private static final Set<String> TRACKED = Set.of(
            "content-type", "x-key-id", "x-timestamp",
            "x-nonce", "x-signature");

    private HeaderNameLowercaseHmacV1() {}

    public record Header(String name, String value) {}
    public record Request(
            String method, String rawTarget,
            List<Header> headers, byte[] rawBody) {}

    private static boolean tokenChar(char c) {
        return (c >= 'A' && c <= 'Z')
                || (c >= 'a' && c <= 'z')
                || (c >= '0' && c <= '9')
                || "!#$%&'*+-.^_\u0060|~".indexOf(c) >= 0;
    }

    /** Chỉ lowercase ASCII field name, KHÔNG sửa field value. */
    public static String lowerName(String name) {
        if (name == null || name.isEmpty()) {
            throw new IllegalArgumentException("Missing header field name");
        }
        StringBuilder result = new StringBuilder(name.length());
        for (int i = 0; i < name.length(); i++) {
            char c = name.charAt(i);
            if (!tokenChar(c)) {
                throw new IllegalArgumentException("Invalid field name");
            }
            result.append((c >= 'A' && c <= 'Z')
                    ? (char) (c + ('a' - 'A')) : c);
        }
        return result.toString();
    }

    /** Phát hiện duplicate dù cùng header khác kiểu viết hoa/thường. */
    private static Map<String, String> trackedValues(List<Header> headers) {
        if (headers == null) {
            throw new IllegalArgumentException("Missing headers");
        }
        Map<String, String> result = new HashMap<>();
        for (Header header : headers) {
            if (header == null || header.value() == null) {
                throw new IllegalArgumentException("Invalid header");
            }
            String lower = lowerName(header.name());

            // HTTP parser vẫn phải chặn obs-fold/request smuggling sớm hơn.
            if (header.value().indexOf('\r') >= 0
                    || header.value().indexOf('\n') >= 0) {
                throw new IllegalArgumentException("Unsafe header value");
            }

            if (TRACKED.contains(lower)) {
                // V1 yêu cầu ASCII không có OWS cho các value được chọn.
                for (int i = 0; i < header.value().length(); i++) {
                    char c = header.value().charAt(i);
                    if (c < 0x21 || c > 0x7e) {
                        throw new IllegalArgumentException(
                                "Noncanonical signed header value");
                    }
                }
                if (result.putIfAbsent(lower, header.value()) != null) {
                    throw new IllegalArgumentException(
                            "Duplicate signed/security header");
                }
            }
        }
        return result;
    }

    private static String required(Map<String, String> headers, String name) {
        String value = headers.get(name);
        if (value == null || value.isEmpty()) {
            throw new IllegalArgumentException("Missing signed header: " + name);
        }
        return value;
    }

    public static byte[] canonicalBytes(Request request)
            throws GeneralSecurityException {
        if (request == null || !"POST".equals(request.method())
                || !"/v1/orders".equals(request.rawTarget())
                || request.rawBody() == null || request.rawBody().length > 65536) {
            throw new IllegalArgumentException("Unsupported request");
        }

        Map<String, String> fields = trackedValues(request.headers());
        String type = required(fields, "content-type");
        String keyId = required(fields, "x-key-id");
        String timestamp = required(fields, "x-timestamp");
        String nonceText = required(fields, "x-nonce");

        if (!"application/json".equals(type)
                || !keyId.matches("[A-Za-z0-9_-]{1,80}")
                || !timestamp.matches(
                    "[0-9]{4}-[0-9]{2}-[0-9]{2}T"
                    + "[0-9]{2}:[0-9]{2}:[0-9]{2}Z")) {
            throw new IllegalArgumentException("Invalid signed header value");
        }
        try {
            Instant.parse(timestamp); // Chỉ parse, chưa check clock skew.
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException("Invalid timestamp", ex);
        }

        // Nonce 128-bit được mã hóa Base64URL không padding.
        try {
            byte[] nonce = Base64.getUrlDecoder().decode(nonceText);
            if (nonce.length != 16
                    || !Base64.getUrlEncoder().withoutPadding()
                            .encodeToString(nonce).equals(nonceText)) {
                throw new IllegalArgumentException("Invalid nonce");
            }
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Invalid nonce", ex);
        }

        String bodyHash = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                        .digest(request.rawBody()));
        String canonical = String.join("\n",
                "HMAC-SHA256-V1",
                "orders-api-prod",
                request.method(),
                request.rawTarget(),
                "content-type:" + type,
                "x-key-id:" + keyId,
                "x-timestamp:" + timestamp,
                "x-nonce:" + nonceText,
                "sha256:" + bodyHash);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] hmac(byte[] secret, byte[] canonical)
            throws GeneralSecurityException {
        // Quy tắc provisioning của API ví dụ, không phải độ dài JCA bắt buộc.
        if (secret == null || secret.length < 32) {
            throw new IllegalStateException("Invalid HMAC credential");
        }
        Mac mac = Mac.getInstance(ALG);
        mac.init(new SecretKeySpec(secret, ALG));
        return mac.doFinal(canonical);
    }

    public static String sign(byte[] secret, Request unsigned)
            throws GeneralSecurityException {
        return PREFIX + Base64.getEncoder().encodeToString(
                hmac(secret, canonicalBytes(unsigned)));
    }

    public static boolean verify(byte[] activeSecret, Request received)
            throws GeneralSecurityException {
        if (received == null) {
            return false;
        }
        // Lấy signature qua cùng phép lowercase và kiểm tra duplicate.
        Map<String, String> values = trackedValues(received.headers());
        String header = values.get("x-signature");
        if (header == null || !header.startsWith(PREFIX)) {
            return false;
        }
        String encoded = header.substring(PREFIX.length());
        byte[] supplied;
        try {
            supplied = Base64.getDecoder().decode(encoded);
        } catch (IllegalArgumentException ex) {
            return false;
        }
        if (supplied.length != 32
                || !Base64.getEncoder().encodeToString(supplied)
                        .equals(encoded)) {
            return false;
        }

        byte[] expected = hmac(activeSecret, canonicalBytes(received));
        return MessageDigest.isEqual(expected, supplied);
    }

    public static void main(String[] args) throws Exception {
        byte[] testKey = new byte[32]; // Chỉ dùng làm dữ liệu test.
        Arrays.fill(testKey, (byte) 0x5a);
        byte[] body = "{\"sku\":\"BK-42\",\"quantity\":2}"
                .getBytes(StandardCharsets.UTF_8);

        List<Header> mixed = List.of(
                new Header("Content-Type", "application/json"),
                new Header("X-Key-ID", "partner-a-202611"),
                new Header("X-Timestamp", "2026-11-28T02:00:00Z"),
                new Header("X-Nonce", "Zq8DxKtUokcwPGNj3d_yvQ"));
        Request unsigned = new Request("POST", "/v1/orders", mixed, body);
        String signature = sign(testKey, unsigned);

        List<Header> receivedHeaders = new ArrayList<>(mixed);
        receivedHeaders.add(new Header("x-signature", signature));
        Request received = new Request(
                "POST", "/v1/orders", receivedHeaders, body);
        if (!verify(testKey, received)) {
            throw new AssertionError("Valid request rejected");
        }

        // Cùng HTTP fields, đảo thứ tự và thay cách viết hoa tên:
        Request differentlyCased = new Request(
                "POST", "/v1/orders", List.of(
                    new Header("X-NONCE", "Zq8DxKtUokcwPGNj3d_yvQ"),
                    new Header("x-tIMESTAMP", "2026-11-28T02:00:00Z"),
                    new Header("content-TYPE", "application/json"),
                    new Header("x-key-id", "partner-a-202611"),
                    new Header("X-Signature", signature)), body);
        if (!verify(testKey, differentlyCased)) {
            throw new AssertionError("Header name case changed the MAC");
        }

        // Đổi VALUE: không được lowercase/normalize giá trị để khớp.
        Request changedValue = new Request(
                "POST", "/v1/orders", List.of(
                    new Header("content-type", "application/json"),
                    new Header("x-key-id", "partner-B-202611"),
                    new Header("x-timestamp", "2026-11-28T02:00:00Z"),
                    new Header("x-nonce", "Zq8DxKtUokcwPGNj3d_yvQ"),
                    new Header("x-signature", signature)), body);
        if (verify(testKey, changedValue)) {
            throw new AssertionError("Tampered header value accepted");
        }

        // Case-insensitive duplicate phải bị từ chối, không lấy first/last.
        List<Header> dup = new ArrayList<>(receivedHeaders);
        dup.add(new Header("x-key-id", "partner-a-202611"));
        try {
            verify(testKey, new Request("POST", "/v1/orders", dup, body));
            throw new AssertionError("Duplicate security header accepted");
        } catch (IllegalArgumentException expected) {
            // Đúng chính sách: duplicate dù khác case.
        }
        System.out.println("Header canonicalization checks passed");
    }
}
```

### Ý nghĩa của các bước trong code

- `lowerName` chỉ chuyển `A`–`Z` sang `a`–`z`, từ chối ký tự không thuộc HTTP field-name token. Nó không phụ thuộc locale.
- `trackedValues` xử lý **từng field occurrence** từ adapter, kiểm tra duplicate **sau khi lowercase**; các giá trị không bị ép sang chữ thường.
- Canonical headers được ghép theo **thứ tự cố định**, không phải thứ tự nhận trên mạng. Vì vậy `X-Key-ID` và `x-key-id` khi xuất hiện **đơn lẻ** sẽ cho cùng MAC, dù vị trí các header trên wire khác nhau.
- Header `x-signature` được kiểm tra duy nhất nhưng không nằm trong `canonicalBytes`. Thêm một signature thứ hai khác case bị từ chối.
- `MessageDigest.isEqual` so raw HMAC bytes sau khi Base64 được giải mã; full tag phải dài **32 byte**.
- Ví dụ yêu cầu secret production ≥32 byte vì **chính sách provisioning**, không phải vì mọi JCA provider đều bắt buộc khóa HMAC có độ dài này.

**Ranh giới của code:** đây là phần lõi để học header canonicalization, **không phải middleware production đầy đủ**. Nó giả định HTTP adapter đã xác thực cấu trúc request-line/framing, đã bảo toàn số lần xuất hiện của các header cần kiểm soát và giá trị được cung cấp có ý nghĩa như trên wire. Một API HTTP có thể tự loại OWS hoặc gộp header; nếu vậy gateway cần chặn nhập nhằng trước khi dữ liệu tới class Java. Code chưa chứng minh nonce thực sự ngẫu nhiên, chưa kiểm tra freshness bằng đồng hồ, chưa ghi nonce vào store, chưa tra credential registry và chưa kiểm tra quyền nghiệp vụ.

## 9. Tích hợp với Java Servlet, framework và gateway

Trong Java web, các API như `HttpServletRequest.getHeader("X-Key-Id")` thường hỗ trợ tìm tên theo kiểu case-insensitive. Nhưng việc đó **không bảo đảm** đã xử lý duplicate theo hợp đồng bảo mật.

Ví dụ sai:

```java
// Lấy một value rồi ký: có thể bỏ sót duplicate tên khác case
// hoặc các field line đã được container combine.
String keyId = request.getHeader("X-Key-Id");
```

Cần xác minh hành vi cụ thể của HTTP container về:

1. Cách parser xử lý các field name với case khác nhau.
2. `getHeaders(name)`, danh sách field values và khả năng giữ **từng lần xuất hiện**.
3. Duplicate header có bị gộp dấu phẩy hoặc chọn giá trị trước/sau không.
4. Có xảy ra normalization/trim OWS hoặc loại CRLF/obs-fold trước khi security filter chạy không.
5. HTTP/2/3 pseudo-header và HTTP/1.1 `Host` được ánh xạ qua gateway như thế nào.
6. Thứ tự filter/middleware: việc xác thực phải dựa vào cùng giá trị mà route và business logic sẽ dùng.

Nếu container không cho phát hiện duplicate đáng tin cậy, **đặt phép kiểm tra ở gateway/ingress sớm hơn**. Không dùng bản đồ header đã bị gộp làm bằng chứng rằng request an toàn. Cũng không tin một header như `X-Authenticated-Client` do client ngoài tự gửi: gateway phải loại nó và chỉ truyền principal đã xác thực qua kênh nội bộ tin cậy.

### Trường hợp chuyển đổi giao thức

Giả sử client HTTP/1.1 gửi `X-Key-ID`, proxy HTTP/2 chuyển thành `x-key-id`. Đây là thay đổi về **cách viết tên** phù hợp với ngữ nghĩa HTTP; V1 lowercase tên giúp signature không đổi, miễn là **value không bị thay**, field occurrence được giữ đúng chính sách và canonical method/URI/body cũng không đổi.

Ngược lại, nếu proxy gộp hai `x-key-id` thành một, thay thứ tự giá trị của header dạng list, tự trim/normalize giá trị không theo hợp đồng hoặc sửa raw URI, chỉ lowercase tên không thể cứu việc xác thực. Cần integration test qua đúng proxy và HTTP version đang triển khai.

## 10. Chống replay: timestamp và nonce là header được ký

Hai field `x-timestamp` và `x-nonce` là ví dụ lý tưởng cho thấy **lowercase name không làm giảm yêu cầu bảo vệ value**.

- `X-Timestamp` hoặc `x-timestamp` đều canonical thành tên `x-timestamp`.
- Giá trị `2026-11-28T02:00:00Z` được giữ nguyên, parse theo một định dạng UTC đã thống nhất và kiểm tra cửa sổ (ví dụ ±300 giây).
- `X-Nonce` hoặc `x-nonce` đều canonical thành `x-nonce`.
- Giá trị nonce phải được tạo bằng bộ sinh số ngẫu nhiên mật mã (ví dụ 128 bit, Base64URL không padding), được ký **đúng bytes** và chỉ sử dụng một lần cho credential tương ứng.

Sau khi xác minh MAC, server claim `(keyId, nonce)` bằng thao tác **nguyên tử** trong kho nonce dùng chung giữa các instance, rồi mới thực thi nghiệp vụ. Với cửa sổ ±5 phút, timestamp nhanh hơn server 5 phút có thể còn hợp lệ tối đa khoảng **10 phút từ thời điểm nhận sớm nhất**. Vì thế nonce phải được giữ đến khi `timestamp + window` không còn hợp lệ, cộng biên an toàn; TTL cố định 5 phút từ khi nhận có thể không đủ.

Nếu nonce store lỗi và endpoint yêu cầu chống replay, hệ thống phải **fail closed**. Việc có HMAC đúng không tự ngăn gửi lại nguyên request; lowercase tên header không liên quan đến tính mới của nonce.

Khi client retry một thao tác tạo đơn, cần timestamp/nonce mới và tính lại chữ ký. Để tránh tác dụng nghiệp vụ bị lặp, dùng thêm **idempotency key** hoặc chính sách deduplication; nếu header idempotency ảnh hưởng quyết định xử lý, nó cũng phải thuộc tập header được ký trong phiên bản hợp đồng tương ứng.

## 11. Key rotation và phân biệt xác thực với phân quyền

Header `X-Key-Id` có thể được viết thành `x-key-id` trên wire mà không đổi ý nghĩa tên; nhưng **giá trị `keyId` phải chọn đúng secret**.

| Key ID | Credential | Secret | Trạng thái |
| --- | --- | --- | --- |
| `partner-a-202611` | Client `partner-a` | Secret A | ACTIVE trong thời gian overlap. |
| `partner-a-202702` | Client `partner-a` | Secret B | ACTIVE mới. |
| `partner-a-202608` | Client `partner-a` | Đã thu hồi | REVOKED; từ chối. |

Server dùng **một** secret theo `keyId`, không thử tất cả khóa khi MAC sai. Khi key bị revoke, các gateway/cache phải cập nhật trạng thái kịp thời. Việc lowercase **tên** `X-Key-ID` không cho phép lowercase hoặc tự sửa **giá trị** key ID. Nếu key ID mới khác chỉ một ký tự hoa, chính sách registry phải định nghĩa có khác credential hay không; không đoán từ cách viết của header name.

### Authentication và authorization

- **Authentication:** một request với `x-key-id` đã được tra cứu hợp lệ, chữ ký HMAC được kiểm tra trên method, raw target, signed headers và raw body digest, timestamp/nonce đúng.
- **Authorization:** principal `clientId` đã xác thực có quyền gọi method, resource, tenant và nghiệp vụ tương ứng hay không.

Ví dụ `partner-a` ký đúng `POST /v1/orders` nhưng thiếu quyền `orders:create`: authentication có thể thành công, **authorization phải từ chối**. Đừng dùng `X-Key-Id` chưa được xác minh để cấp quyền; cũng đừng coi mọi field `X-Authenticated-Client` từ mạng ngoài là principal đáng tin.

## 12. Ma trận kiểm thử header name lowercase

| Tình huống | Kết quả mong đợi |
| --- | --- |
| `X-Key-Id`, `x-key-id` và `X-KEY-ID` được gửi **riêng lẻ** với cùng value. | Tạo cùng canonical name `x-key-id`, cùng signature nếu các phần khác giống nhau. |
| Header xuất hiện theo thứ tự khác trên wire. | Canonical signed-header order vẫn cố định, MAC không đổi. |
| Đổi chữ hoa/thường **giá trị** `partner-a-202611` thành `partner-A-202611`. | MAC cũ không khớp hoặc registry từ chối credential theo contract. |
| `Content-Type` và `content-type` cùng xuất hiện. | Từ chối duplicate theo policy V1. |
| `X-Key-ID` và `x-key-id` cùng xuất hiện với **giá trị khác nhau**. | Từ chối trước khi dùng value để gắn principal. |
| Hai `X-Signature` hoặc `X-Signature` + `x-signature`. | Từ chối duplicate; không chọn first/last. |
| Header name chứa khoảng trắng, dấu `:` hoặc ký tự Unicode ngoài token grammar. | HTTP parser/canonicalizer từ chối; không tự lowercase rồi sửa. |
| Value có CR, LF hoặc obs-fold, hoặc OWS không phù hợp policy. | Từ chối ở parser/ingress; không chấp nhận header injection. |
| `content-type:Application/JSON` thay cho `application/json`. | V1 từ chối vì chính sách value yêu cầu dạng chính xác. |
| `X-Nonce` đổi tên sang `x-nonce` nhưng giữ value. | MAC không đổi; vẫn phải kiểm tra freshness và nonce store. |
| Nonce value thay đổi nhưng giữ chữ ký. | MAC không khớp. |
| Timestamp quá cũ/quá xa tương lai dù MAC đúng. | Từ chối theo cửa sổ freshness. |
| Gửi lại cùng nonce đến hai gateway đồng thời. | Claim nguyên tử chỉ cho một request tiếp tục. |
| Key ID đã REVOKED hoặc thuộc audience khác. | Từ chối, không thử secret khác. |
| HTTP/2 client gửi header name có chữ hoa. | HTTP/2 layer từ chối malformed message. |
| Gateway HTTP/1.1 → HTTP/2 chuyển tên về lowercase mà giữ value. | V1 xác minh được nếu các phần khác không đổi và duplicate được kiểm soát. |
| Proxy gộp/trộn field duplicate trước khi verifier nhận. | Test phải phát hiện và chặn ở ingress; không dựa vào map đã mất dữ liệu gốc. |
| HMAC hợp lệ nhưng client thiếu quyền tạo đơn. | Authentication có thể thành công, authorization từ chối. |

Để kiểm thử liên ngôn ngữ, hãy duy trì **test vector** gồm byte secret thử nghiệm, HTTP method, raw target, danh sách field occurrences, canonical lowercase name/value, signed-header order, raw body bytes, digest body, canonical UTF-8 string, MAC output dạng hex và signature Base64. Đừng dùng secret production trong các test vector hay log.

## 13. Bài tập thực hành

### Bài tập 1 — Cùng tên hay hai tên?

Trong cùng request có:

```http
X-Key-Id: partner-a-202611
x-key-id: partner-a-202611
```

Có nên chuyển thành một entry trong `Map` rồi xác minh như bình thường?

**Gợi ý đáp án:** Không. Đây là **hai occurrence của cùng field name** theo HTTP. Chính sách V1 yêu cầu đúng một occurrence cho field bảo mật, nên phải từ chối. Gộp map trước khi kiểm tra làm mất bằng chứng duplicate.

### Bài tập 2 — Vì sao lowercasing value là lỗi?

Client gửi `X-Key-Id: Partner-A` nhưng server tự biến toàn dòng thành `x-key-id:partner-a` để canonicalize. Rủi ro gì?

**Gợi ý đáp án:** Server đã thay **giá trị** key ID, có thể chọn secret/credential khác. Lowercase chỉ được phép áp dụng với **header name**; value phải theo contract riêng và có thể phân biệt chữ hoa/thường.

### Bài tập 3 — HTTP/2 có cần canonical header names nữa không?

Một gateway nhận request HTTP/2 với tên header đã lowercase, sau đó chuyển sang HTTP/1.1 và backend xây HMAC từ `Content-Type`. Client ký `content-type`. Có thể mismatch không?

**Gợi ý đáp án:** Có nếu backend đưa tên gốc `Content-Type` thay vì canonical lowercase vào chuỗi ký. HTTP/2 yêu cầu lowercase trên wire, nhưng mọi bên vẫn phải dùng cùng hợp đồng canonicalization khi ký/xác minh.

### Bài tập 4 — Signed header order và wire order

Client gửi `X-Nonce` trước `Content-Type`. Server nhận `Content-Type` trước `X-Nonce` do proxy đổi thứ tự. Có nên dùng thứ tự wire để dựng canonical request?

**Gợi ý đáp án:** Không theo V1. Hợp đồng quy định thứ tự canonical cố định `content-type`, `x-key-id`, `x-timestamp`, `x-nonce`. Thứ tự wire không làm thay chữ ký nếu từng value còn nguyên và không có duplicate.

### Bài tập 5 — Header khác case có đủ chống replay không?

Attacker ghi lại một request ký hợp lệ chứa `X-Nonce: ...`, rồi phát lại với tên `x-nonce` và cùng value. Nếu HMAC hợp lệ, hệ thống có được thực hiện nghiệp vụ lần hai không?

**Gợi ý đáp án:** Không. Hai tên canonical thành cùng `x-nonce`, và **nonce value không đổi**. Kho nonce nguyên tử phải phát hiện đã dùng và từ chối request, dù HMAC hợp lệ.

## 14. Checklist triển khai và tổng kết

Trước khi đưa HMAC header canonicalization vào production:

- [ ] Đã định nghĩa rõ danh sách **signed headers** và thứ tự canonical theo **phiên bản giao thức**.
- [ ] Field names được validate là HTTP token và lowercase **ASCII** ổn định, không phụ thuộc locale.
- [ ] Chỉ lowercase **tên**, không tự sửa **giá trị**; từng value có chính sách rõ ràng.
- [ ] Phát hiện duplicate **case-insensitively** trước khi dữ liệu bị gộp vào map, đặc biệt `keyId`, timestamp, nonce và signature.
- [ ] Giá trị header được ký được xử lý OWS, CR/LF, obs-fold và dạng không hợp lệ theo đúng hợp đồng ở ingress.
- [ ] Method, raw URI/path/query, body bytes, authority/audience và header values có cùng ý nghĩa tại verifier và backend.
- [ ] HTTP/1.1, HTTP/2/3 và proxy/gateway chuyển đổi tên header đúng quy tắc, không làm mất duplicate hoặc thay value ngoài contract.
- [ ] HMAC dùng secret của key ID ACTIVE, full tag được so sánh an toàn; credential không được ghi ra log.
- [ ] Timestamp/nonce được ký và kiểm tra replay bằng kho dùng chung, key rotation có chính sách thu hồi.
- [ ] Danh tính chỉ được gắn sau authentication; resource/tenant/scope vẫn cần authorization riêng.
- [ ] Có unit test cùng test vector và **integration test qua HTTP stack thật**, không chỉ gọi `toLowerCase` với một chuỗi mẫu.

**Ghi nhớ:** *Header name lowercase* là một phép chuẩn hóa **tên trường HTTP**, giúp các biến thể `X-Key-Id`, `x-key-id` và `X-KEY-ID` tạo cùng tên `x-key-id` trong canonical request. Bản thân phép lowercase không giải quyết **duplicate headers**, **OWS**, **giá trị header**, **proxy rewrite**, **replay** hay **phân quyền**. Hợp đồng an toàn phải xác định cả **field nào được ký, thứ tự ký, cách kiểm tra value và ranh giới nơi request được diễn giải**.
