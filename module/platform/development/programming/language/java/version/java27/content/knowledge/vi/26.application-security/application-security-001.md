# Ranh giới tin cậy, kiểm tra đầu vào và giới hạn dữ liệu

## 1. Vì sao ứng dụng phải xác định ranh giới tin cậy?

Một API Java có thể nhận cùng lúc nhiều nguồn dữ liệu: JSON body, query parameter, HTTP header, dữ liệu tải lên, kết quả từ cơ sở dữ liệu, thông điệp hàng đợi, cấu hình, tập tin và phản hồi từ dịch vụ bên ngoài. Tất cả có thể chứa giá trị bất thường, sai định dạng, không phù hợp nghiệp vụ hoặc được tạo với chủ ý khai thác hệ thống.

**Ranh giới tin cậy (trust boundary)** là nơi dữ liệu đi từ một miền mà ứng dụng **không kiểm soát hoàn toàn** sang một thành phần được trao quyền xử lý nó. Việc dữ liệu đã đi qua HTTPS, từ một hệ thống nội bộ hoặc đã được lưu trong database **không tự bảo đảm** dữ liệu có dạng và quyền sử dụng phù hợp với thao tác hiện tại.

Ví dụ một endpoint nhận yêu cầu tạo đơn hàng:

~~~text
POST /orders
Authorization: Bearer ...
Content-Type: application/json

{
  "productId": "PEN-01",
  "quantity": 2,
  "comment": "Giao buổi sáng"
}
~~~

Trước khi thực hiện nghiệp vụ, hệ thống cần biết:

- Body có nằm trong kích thước cho phép và đúng mã hóa/định dạng không?
- Các trường có đúng kiểu, được phép xuất hiện và nằm trong giới hạn không?
- **productId** có tồn tại và thuộc loại sản phẩm cho phép đặt không?
- Người gửi đã được xác thực và **được phép** tạo đơn cho tài khoản được yêu cầu chưa?
- Thao tác tạo đơn có vượt hạn mức, điều kiện tồn kho hoặc tài nguyên hệ thống không?
- Khi hiển thị comment, ghi log hoặc lưu database, dữ liệu được xử lý đúng **ngữ cảnh đầu ra** chưa?

Trong Java 27, các API ổn định như **java.time**, **java.nio.charset**, **java.io**, **java.net**, **java.nio.file**, **java.util.regex** và **java.sql** cung cấp nền tảng để xây các ranh giới này. Những biện pháp an ninh thực tế cần kết hợp nhiều lớp, không dựa vào một regex hay một hàm “sanitize” tổng quát.

## 2. Sơ đồ luồng dữ liệu và điểm kiểm soát

~~~mermaid
flowchart TD
    A["Client / service / file / message queue"] --> B["Ingress: byte limit, timeout, media type"]
    B --> C["Decode / parse đúng định dạng"]
    C --> D["Schema + field allowlist + range/depth/count"]
    D --> E["Chuẩn hóa theo chính sách của trường"]
    E --> F["Bất biến nghiệp vụ"]
    F --> G["Authentication + authorization"]
    G --> H["Application/domain object đáng tin ở phạm vi hợp đồng"]
    H --> I["SQL / filesystem / HTTP / HTML / logs"]
    I --> J["Parameterized API / output encoding / egress limits"]
~~~

Sơ đồ không có nghĩa mọi ứng dụng đều bắt buộc đặt **authorization sau validation** trong thứ tự tuyệt đối. Chẳng hạn, việc xác thực cần diễn ra sớm để ngăn truy cập trái phép hoặc dùng tài nguyên quá mức; kiểm tra kích thước request nên thực hiện **trước khi** phân tích body; kiểm tra quyền truy cập đối tượng phải áp dụng **trước khi** trả dữ liệu nhạy cảm.

Điều quan trọng là **mỗi bước có hợp đồng rõ ràng**:

1. Kiểm soát tài nguyên trước khi cấp phát lớn.
2. Parse thành dữ liệu có cấu trúc.
3. Kiểm tra cú pháp, kiểu, phạm vi và cấu trúc.
4. Chuẩn hóa **chỉ khi** quy tắc nghiệp vụ cần và sau đó kiểm tra lại các giới hạn.
5. Kiểm tra trạng thái nghiệp vụ và quyền truy cập.
6. Sử dụng API an toàn cho từng nơi tiêu thụ dữ liệu.

Một dữ liệu đã được “validated” trong tầng A vẫn có thể phải được kiểm tra lại khi được dùng trong ngữ cảnh B: tên file hợp lệ cho giao diện **không tự trở thành** một filesystem path được phép; tên sản phẩm hợp lệ **không tự trở thành** một fragment SQL an toàn.

## 3. Inventory các nguồn dữ liệu không được tin cậy mặc định

| Nguồn | Ví dụ | Rủi ro điển hình |
|---|---|---|
| HTTP request body | JSON/XML/form | Payload lớn, sai kiểu, nesting sâu, trường thừa |
| URL path và query | **/users/123**, **page=...** | Giá trị vượt giới hạn, canonicalization khác nhau |
| HTTP headers | Host, Content-Type, forwarded headers | Spoofing, ký tự điều khiển, giá trị dài |
| Webhook/callback | JSON từ nhà cung cấp | Replay, chữ ký không hợp lệ, schema thay đổi |
| Database | Tên, mô tả, cấu hình đã lưu | Stored XSS, dữ liệu từ hệ thống cũ, thay đổi ngoài luồng |
| File upload | Filename, MIME, file bytes | Quá dung lượng, định dạng giả, mã độc, archive bomb |
| Message broker | Sự kiện và metadata | Producer không cùng hợp đồng, payload trùng, quá kích thước |
| Remote HTTP | Dữ liệu JSON, ZIP, HTML | Schema giả, SSRF, dữ liệu giải nén phình lớn |
| Environment/config | Đường dẫn, giới hạn tài nguyên | Misconfiguration, quyền chạy cao hơn dự kiến |
| CLI arguments | Lệnh, đường dẫn, tên file | Injection, argument confusion, workload bất thường |

“Internal” không đồng nghĩa “trusted”. Dữ liệu ở database hoặc message queue có thể do người dùng từng nhập, phiên bản service khác ghi, hoặc bị thay đổi bởi bộ phận vận hành.

**Tin cậy là theo từng thuộc tính**, không phải tem dán lên toàn bộ object. Ví dụ sau khi xác thực token, danh tính chủ thể có thể được tin cậy trong ngữ cảnh xác thực, nhưng **quantity** do chính chủ thể đó gửi vẫn phải được kiểm tra.

## 4. Viết hợp đồng chấp nhận cho từng trường

Một validator tốt không hỏi “chuỗi này có trông nguy hiểm không?”, mà hỏi **“giá trị nào được chấp nhận cho đúng trường này?”**.

Ví dụ cho endpoint tạo đơn:

| Trường | Kiểu sau parse | Quy tắc |
|---|---|---|
| **productId** | String | Bắt buộc, dài 1–32 ký tự ASCII theo mẫu ID đã định nghĩa |
| **quantity** | Integer | Số nguyên, từ 1 đến 100 |
| **comment** | String/null | Không bắt buộc, tối đa 500 Unicode code points và 2 KiB UTF-8 |
| **deliveryDate** | LocalDate | Ngày ISO, trong một khoảng cho phép |
| **deliveryType** | Enum | Một trong **STANDARD**, **EXPRESS** |
| **items** | List | Tối đa 50 phần tử, mỗi phần tử được kiểm tra độc lập |
| **metadata** | Object | Chỉ cho các key đã công bố, giới hạn số lượng và độ sâu |

**Chính sách phải nêu rõ:** null có hợp lệ không, chuỗi trắng được xử lý như thế nào, ký tự Unicode nào được phép, khoảng thời gian nào hợp lệ và giới hạn lớn nhất ở từng lớp.

Việc kiểm tra độ dài một chuỗi không có nghĩa cần cấm dấu nháy đơn, dấu ngoặc nhọn hoặc ký tự tiếng Việt. Với mô tả tự do, có thể cần hỗ trợ Unicode rộng, còn với **mã định danh kỹ thuật** có thể chọn tập ký tự nhỏ và cố định.

## 5. Allowlist tốt hơn việc chỉ chặn chuỗi bị coi là nguy hiểm

**Allowlist validation** định nghĩa tập đầu vào chấp nhận được. **Denylist validation** cố tìm và chặn các trường hợp không mong muốn, thường thiếu bao phủ và dễ gây lỗi khi có biến thể mới.

Ví dụ mã sản phẩm chỉ cho chữ Latin không dấu viết hoa, số và dấu gạch ngang:

~~~java
import java.util.regex.Pattern;

private static final Pattern PRODUCT_ID =
    Pattern.compile("[A-Z0-9](?:[A-Z0-9-]{0,30}[A-Z0-9])?");

static String requireProductId(String raw) {
    if (raw == null || raw.length() > 32
            || !PRODUCT_ID.matcher(raw).matches()) {
        throw new IllegalArgumentException("Invalid product ID");
    }
    return raw;
}
~~~

**matches()** yêu cầu toàn bộ chuỗi khớp pattern, không chỉ một đoạn. Kiểm tra chiều dài **trước khi chạy regex** giúp giảm tài nguyên xử lý đầu vào cực dài.

Với trường tự do như **displayName** hay **comment**, một regex ASCII hạn chế sẽ loại bỏ dữ liệu hợp lệ. Hãy dùng quy tắc phù hợp về độ dài, mã hóa, ký tự điều khiển, ngữ nghĩa và chuẩn hóa Unicode khi cần.

**Validation không phải sanitizer đa năng**: chặn dấu nháy đơn trong username không thay được PreparedStatement; loại dấu **<** khỏi comment không thay được output encoding theo HTML context.

## 6. Parse, validation và authorization là ba vấn đề riêng

Xem xét một yêu cầu:

~~~text
GET /accounts/8021/orders
~~~

Có ít nhất ba loại kiểm tra khác nhau:

1. **Parse:** đoạn **8021** có chuyển thành mã tài khoản đúng định dạng không?
2. **Validation:** mã tài khoản có nằm trong phạm vi và tồn tại trong dữ liệu hệ thống không?
3. **Authorization:** principal đã xác thực **có quyền** xem đơn hàng của tài khoản 8021 không?

Ngay cả một mã tài khoản hoàn toàn hợp lệ vẫn có thể là dữ liệu của người khác. Validation **không** giải quyết bài toán **broken object-level authorization (BOLA/IDOR)**.

~~~java
long accountId = parseAccountId(rawAccountId);

// accountId hợp lệ về kiểu và phạm vi.
// Vẫn phải kiểm tra quyền theo chủ thể từ phiên xác thực:
authorization.requireCanReadOrders(principal, accountId);

// Sau đó mới truy vấn/trả dữ liệu theo phạm vi quyền.
~~~

Các tên **parseAccountId**, **authorization** và **principal** chỉ minh họa lớp nghiệp vụ của ứng dụng. Không lấy **userId** từ request body rồi coi là danh tính đã được xác thực.

## 7. Kiểm tra số nguyên, số thập phân và phạm vi

Đừng chỉ gọi **Integer.parseInt** rồi mặc định giá trị phù hợp với nghiệp vụ. Sau khi parse thành công, số vẫn có thể âm, bằng 0 hoặc quá lớn.

~~~java
static int requireQuantity(String raw) {
    if (raw == null || raw.length() > 3
            || !raw.matches("[1-9][0-9]{0,2}")) {
        throw new IllegalArgumentException("Invalid quantity format");
    }

    int value = Integer.parseInt(raw);

    if (value > 100) {
        throw new IllegalArgumentException("Quantity exceeds limit");
    }
    return value;
}
~~~

Ví dụ này cố ý từ chối số có dấu, chữ số không thuộc ASCII và số có số 0 ở đầu. **Đó là lựa chọn hợp đồng**, không phải quy tắc duy nhất cho mọi API.

Với tiền tệ, **BigDecimal** giúp tránh lỗi biểu diễn nhị phân thường gặp của float/double:

~~~java
import java.math.BigDecimal;

static BigDecimal requirePrice(String raw) {
    if (raw == null || raw.length() > 12
            || !raw.matches("(?:0|[1-9][0-9]{0,7})\\.[0-9]{2}")) {
        throw new IllegalArgumentException("Invalid price");
    }

    BigDecimal value = new BigDecimal(raw);

    if (value.compareTo(new BigDecimal("1000000.00")) > 0) {
        throw new IllegalArgumentException("Price too high");
    }
    return value;
}
~~~

Một số ứng dụng cho phép dấu âm, thập phân không đủ hai chữ số hoặc định dạng số theo locale; nên điều chỉnh chính sách và loại dữ liệu thay vì sao chép regex của ví dụ một cách máy móc. Hãy kiểm tra cả **overflow**, độ lớn, precision/scale và dữ liệu parse ngoài phạm vi.

## 8. Thời gian: parse không đồng nghĩa hợp lệ theo nghiệp vụ

**LocalDate.parse** kiểm tra định dạng và lịch trong trường hợp thông thường, nhưng không quyết định được ngày giao hàng có phù hợp chính sách hay không.

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

static LocalDate requireDeliveryDate(
        String raw, LocalDate today) {

    if (raw == null || raw.length() != 10) {
        throw new IllegalArgumentException("Expected ISO date");
    }

    final LocalDate date;
    try {
        date = LocalDate.parse(raw);
    } catch (DateTimeParseException invalid) {
        throw new IllegalArgumentException("Invalid date", invalid);
    }

    if (date.isBefore(today) || date.isAfter(today.plusDays(30))) {
        throw new IllegalArgumentException("Date outside delivery window");
    }

    return date;
}
~~~

Trong ví dụ, **today** được truyền vào để việc kiểm thử không phụ thuộc thời điểm thực. Trong service thật, có thể inject **Clock** và chọn **ZoneId** theo hợp đồng.

Nếu yêu cầu là *timestamp tuyệt đối*, dùng **Instant** hoặc kiểu có offset phù hợp, không nhận LocalDateTime rồi tự đoán múi giờ hệ thống.

## 9. Giới hạn chuỗi: UTF-16, code point và byte

Java **String.length()** trả về số **UTF-16 code units**, không phải số byte UTF-8 và cũng không luôn bằng số Unicode code points.

~~~java
import java.nio.charset.StandardCharsets;

String value = "A€😀";

System.out.println(value.length()); // 4 UTF-16 code units
System.out.println(value.codePointCount(0, value.length())); // 3
System.out.println(value.getBytes(StandardCharsets.UTF_8).length); // 8
~~~

Cần chọn đúng giới hạn:

| Loại giới hạn | Cách đo | Ví dụ dùng |
|---|---|---|
| UTF-16 code units | **String.length()** | Ràng buộc API Java/kiểu dữ liệu cụ thể |
| Unicode code points | **codePointCount(0, length())** | Một mức giới hạn văn bản có ý nghĩa hơn |
| UTF-8 byte length | **getBytes(UTF_8).length** | Quota lưu trữ/giao thức tính theo byte |
| Grapheme clusters | Thư viện phân đoạn Unicode phù hợp | Độ dài ký tự hiển thị trong giao diện |

**Code point không đồng nghĩa ký tự người dùng nhìn thấy**: một chữ có dấu có thể được tạo bởi base letter + combining mark; emoji cũng có thể gồm nhiều code points ghép thành một hình hiển thị.

Với trường text tự do, thường nên kết hợp **số code points** và **số byte**, không đặt một con số rồi kỳ vọng nó bảo vệ cả memory, database column và trải nghiệm giao diện.

## 10. Charset và strict UTF-8 decoding

Nếu byte đầu vào không phải UTF-8 hợp lệ, việc giải mã với chính sách *replacement* có thể thay byte lỗi bằng ký tự **�**; điều đó làm thay đổi dữ liệu trước khi validation.

Với giao thức yêu cầu **UTF-8 hợp lệ**, dùng **CharsetDecoder** ở chế độ báo lỗi:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8Strict(byte[] payload)
        throws CharacterCodingException {

    var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

    return decoder.decode(ByteBuffer.wrap(payload)).toString();
}
~~~

~~~java
byte[] invalid = {(byte) 0xC3, (byte) 0x28};

try {
    decodeUtf8Strict(invalid);
    throw new AssertionError("Expected invalid UTF-8 to fail");
} catch (CharacterCodingException expected) {
    System.out.println("Invalid UTF-8 rejected");
}
~~~

**Chỉ rõ charset ở ranh giới byte ↔ text**. Java hiện mặc định UTF-8 trong nhiều API, nhưng việc chỉ rõ **StandardCharsets.UTF_8** làm hợp đồng dễ kiểm tra, đặc biệt khi hệ thống tích hợp nguồn dữ liệu cũ hoặc một thư viện có quy tắc khác.

Nếu đã kiểm tra giới hạn bytes rồi mới giải mã, tránh trường hợp payload quá lớn bị đưa vào parser hoặc decoder trước khi giới hạn. Đồng thời cần lưu ý dữ liệu sau chuẩn hóa có thể đổi độ dài, nên một số giới hạn cần kiểm tra lại sau bước đó.

## 11. Unicode normalization và canonicalization

Hai chuỗi có thể hiển thị giống nhau nhưng có mã Unicode khác nhau:

~~~java
String composed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(composed.equals(decomposed)); // false
~~~

Nếu một **mã định danh hiển thị** cần so sánh nhất quán, có thể chọn chính sách **Unicode NFC**:

~~~java
import java.text.Normalizer;

static String normalizeDisplayName(String raw) {
    return Normalizer.normalize(raw, Normalizer.Form.NFC);
}
~~~

~~~java
String a = normalizeDisplayName(composed);
String b = normalizeDisplayName(decomposed);

System.out.println(a.equals(b)); // true
~~~

Nhưng **normalization không phải sanitizer**. Nó không bảo vệ SQL, HTML, shell, filesystem hoặc authorization. **NFKC** và các dạng tương thích có thể thay đổi những phân biệt có ý nghĩa; không áp dụng một cách mù quáng cho password, chữ ký số, token, hash input hoặc nội dung cần bảo toàn byte gốc.

**Quy tắc:** Xác định thứ tự giải mã/canonicalization và chính sách normalization **cho từng trường**, sau đó áp dụng nhất quán ở mọi nơi so sánh, lưu trữ và lập khóa duy nhất.

## 12. Vì sao phải giới hạn trước khi dùng regex?

Một validator chỉ dùng regex có thể bị lạm dụng khi input cực dài hoặc pattern có backtracking tốn kém. Với **java.util.regex.Pattern**, cần quan tâm cả độ phức tạp của biểu thức và kích thước dữ liệu.

~~~java
import java.util.regex.Pattern;

private static final Pattern SLUG =
    Pattern.compile("[a-z0-9][a-z0-9-]{0,39}");

static String requireSlug(String raw) {
    if (raw == null || raw.length() > 40) {
        throw new IllegalArgumentException("Slug too long");
    }
    if (!SLUG.matcher(raw).matches()) {
        throw new IllegalArgumentException("Invalid slug");
    }
    return raw;
}
~~~

Ở ví dụ này, regex có cấu trúc đơn giản và được giới hạn trước bởi số lượng ký tự. **Không chỉ thêm timeout cho regex mà vẫn giữ các pattern nguy hiểm**; nên thiết kế pattern tránh những lựa chọn chồng lấn có thể backtrack quá mức.

Một anti-pattern là dùng nhiều lượng tử lồng nhau trên đầu vào không giới hạn, ví dụ **(a+)+** khi kiểm tra một chuỗi rất dài gần khớp. Đây là rủi ro **Regular Expression Denial of Service (ReDoS)**.

Không dùng regex để phân tích những ngôn ngữ phức tạp mà Java đã có parser chuẩn hoặc thư viện chuyên dụng, như **URI**, **JSON**, **HTML**, **XML** hoặc các định dạng ngày giờ.

## 13. Schema và giới hạn cho JSON hoặc dữ liệu có cấu trúc

Một body JSON hợp lệ về cú pháp vẫn có thể sai hợp đồng:

~~~json
{
  "quantity": 2,
  "items": [
    {"sku": "PEN-01", "quantity": 1}
  ],
  "role": "ADMIN",
  "unexpected": {"nested": {"more": []}}
}
~~~

Các kiểm tra cần xác định khi cấu hình parser hoặc lớp binding:

1. **Kích thước body tối đa** trước parse.
2. **Số cấp lồng nhau tối đa**, tránh cấu trúc sâu gây stack/memory exhaustion.
3. **Số phần tử của array tối đa**.
4. **Số thuộc tính của object tối đa** nếu phù hợp.
5. **Giới hạn chiều dài key và string value**.
6. **Danh sách field được phép**, required fields và cách xử lý unknown fields.
7. **Kiểu dữ liệu chính xác**: số nguyên không bị chấp nhận nhầm thành chuỗi hoặc số thực.
8. **Hành vi đối với duplicate keys** như hai thuộc tính cùng tên.
9. **Ràng buộc chéo** giữa các trường: tổng số lượng, ngày bắt đầu/kết thúc, trạng thái.

**JDK không có một JSON schema validator tích hợp phổ quát** cho các ứng dụng thông thường. Hãy chọn một thư viện parser/validator được bảo trì và thiết lập giới hạn qua API của đúng phiên bản đang dùng; đừng đoán tên method của framework.

**Mass assignment/overposting:** Không bind trực tiếp mọi trường người dùng gửi vào entity có những thuộc tính nhạy cảm như **role**, **ownerId**, **approved**, **priceOverride**. Chỉ tạo DTO với những trường input được phép, và cấp giá trị nhạy cảm từ server/domain.

## 14. Giới hạn dữ liệu ở tầng HTTP ingress

Trước khi đọc toàn bộ request body vào RAM, hệ thống cần giới hạn kích thước đã nhận. Một số công tắc có thể nằm ở load balancer, reverse proxy, web server, servlet container hoặc HTTP framework.

~~~text
Internet
  |
  v
Reverse proxy: total request size / header size / timeout / rate limit
  |
  v
Application server: body size / parser depth / field count / concurrency
  |
  v
Endpoint: schema / field value / business quota / authorization
~~~

Những quy tắc nền tảng:

- **Content-Length là metadata do phía gửi cung cấp**: hữu ích để từ chối sớm, nhưng không thay thế việc **đếm byte thực sự được đọc**, vì có thể vắng mặt hoặc không phản ánh toàn bộ tình huống truyền dữ liệu.
- Hạn chế **HTTP headers** cả kích thước tổng và kích thước từng trường.
- Đặt **request-read timeout** và giới hạn kết nối, tránh client gửi dữ liệu nhỏ giọt giữ tài nguyên quá lâu.
- Giới hạn số request đồng thời hoặc queue backlog; giới hạn byte không ngăn một số lượng request nhỏ quá lớn.
- Trả status như **413 Content Too Large** khi phù hợp với HTTP boundary, nhưng giữ chi tiết kỹ thuật ở phía server.

Một API có giới hạn field nhỏ không thể bảo vệ khỏi body 1 GB nếu framework đã đọc cả 1 GB trước khi chạy validation.

## 15. Đọc InputStream có giới hạn bằng Java chuẩn

Với payload nhỏ, có thể dùng **InputStream.readNBytes(n)** để đọc **tối đa n byte**, không đọc vô hạn.

~~~java
import java.io.IOException;
import java.io.InputStream;

static byte[] readBounded(InputStream input, int maxBytes)
        throws IOException {

    if (maxBytes < 0 || maxBytes > 1_048_576) {
        throw new IllegalArgumentException("Unsupported byte limit");
    }

    byte[] data = input.readNBytes(maxBytes + 1);

    if (data.length > maxBytes) {
        throw new IllegalArgumentException("Payload exceeds byte limit");
    }

    return data;
}
~~~

**Vì sao đọc maxBytes + 1?** Nếu chỉ đọc đúng maxBytes, không phân biệt payload vừa chạm giới hạn với payload còn dữ liệu ở phía sau. Byte thứ **maxBytes + 1** là dấu hiệu từ chối.

Đoạn mã trên phù hợp **giới hạn nhỏ và đã kiểm tra**, không phải giải pháp cho mọi upload lớn:

- **readNBytes** vẫn có thể chờ dữ liệu của một nguồn chậm; cần **timeout và giới hạn tốc độ đọc ở tầng mạng**.
- Nó chỉ bảo vệ kích thước byte **trước giải nén/parse**, không bảo vệ dữ liệu nở sau giải nén.
- Hàm không tự đóng InputStream: caller phải sở hữu và đóng stream theo hợp đồng.
- Nếu cần ghi file lớn theo stream, phải đếm **tổng byte đã đi qua** và từ chối khi vượt quota thay vì tích lũy vào một byte[].
- Không dùng giá trị **Integer.MAX_VALUE** do client truyền để tạo limit; mọi quota phải do server định nghĩa.

## 16. Đếm byte khi xử lý theo luồng

Khi không muốn giữ toàn bộ payload trong RAM, có thể dùng một vòng lặp với bộ đệm cố định:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

static long copyLimited(
        InputStream source,
        OutputStream target,
        long maxBytes) throws IOException {

    if (maxBytes < 0) {
        throw new IllegalArgumentException("Negative limit");
    }

    byte[] buffer = new byte[8192];
    long total = 0;

    while (true) {
        int n = source.read(buffer);
        if (n == -1) {
            return total;
        }
        if (n == 0) {
            continue;
        }

        if (n > maxBytes - total) {
            throw new IllegalArgumentException("Payload too large");
        }

        target.write(buffer, 0, n);
        total += n;
    }
}
~~~

Đoạn code kiểm tra **n > maxBytes - total** trước khi tăng để tránh một dạng overflow khi cộng tổng, với giả định **maxBytes** không âm và tổng luôn nằm trong quota.

**Quan trọng về dữ liệu ghi dở:** Nếu limit bị vượt giữa chừng, một phần dữ liệu có thể đã được ghi vào target. Với file upload hoặc import dữ liệu, hãy dùng **staging file**, rồi chỉ xác nhận/di chuyển vào vị trí chính thức khi mọi kiểm tra hoàn tất. Bảo đảm cleanup và transaction tùy loại lưu trữ.

Trong hệ thống production, cần giới hạn thêm **thời gian xử lý, số stream đồng thời, dung lượng tạm và kích thước kết quả giải nén**, không chỉ số byte đầu vào.

## 17. Timeout, độ sâu, số lượng và chi phí tính toán

Một request nhỏ về số byte vẫn có thể gây chi phí lớn do các tham số điều khiển thuật toán.

| Giới hạn | Ví dụ | Điều gì được bảo vệ? |
|---|---|---|
| **Tổng byte request** | 1 MiB cho JSON | Bộ nhớ/network ingress |
| **String length** | 500 code points | Field dài bất thường |
| **Số item** | 50 items/order | Vòng lặp và DB operations |
| **JSON nesting depth** | 20 cấp | Parser/stack |
| **Page size** | 1–100 kết quả | DB/query cost, response size |
| **Batch size** | 100 tác vụ | Queue/thread pool |
| **Request timeout** | Theo SLO | Tài nguyên bị giữ quá lâu |
| **Concurrency limit** | Semaphore/pool | Saturation |
| **Decompressed bytes** | Quota riêng | Zip/gzip bomb |
| **Archive entries** | Giới hạn số entry | CPU, metadata và file count |
| **Rate limit** | Theo principal/tenant | Lạm dụng tài nguyên theo thời gian |

Giới hạn này phải do hệ thống sở hữu, điều chỉnh theo đo lường thực tế. **Không lấy con số ví dụ thành chuẩn phổ quát** cho mọi sản phẩm.

Một điểm hay bị bỏ sót: **timeout chỉ giới hạn thời gian chờ của một phía**, không tự bảo đảm công việc server đã dừng hay side effect được rollback. Cần cơ chế hủy hợp tác, transaction hoặc idempotency cho thao tác ghi.

## 18. Rate limiting và quota khác input validation

Validation kiểm tra một request có hợp lệ trong phạm vi đơn lẻ; quota và rate limit kiểm tra **mức sử dụng tích lũy**.

Ví dụ: request lấy 100 kết quả là hợp lệ về page size, nhưng một client gửi 100.000 request/giây vẫn có thể gây quá tải.

Những giới hạn có thể áp dụng:

- **Per request:** số byte, số item, thời gian tối đa.
- **Per identity/tenant:** số request/phút, tác vụ chạy đồng thời, dung lượng upload/ngày.
- **Per resource:** số kết nối DB, số tác vụ chờ, số lần retry.
- **Global:** bộ nhớ, disk, network bandwidth và CPU.

Không nên tin IP address là định danh duy nhất của người dùng: proxy, NAT và môi trường chia sẻ có thể khiến nhiều người dùng chung IP; ngược lại, một actor có thể dùng nhiều IP. Các quota thường cần phối hợp **principal, tenant, API key và tín hiệu hạ tầng**.

Khi từ chối do rate limit, tầng HTTP có thể sử dụng **429 Too Many Requests** theo hợp đồng; retry/backoff phải được kiểm soát để không tạo thêm tải.

## 19. Bảo vệ khi nhận file upload

Tên file, Content-Type và extension đều là **metadata đến từ phía upload** và không đủ để xác định nội dung thật.

Ví dụ chính sách nhận ảnh:

1. Xác thực người tải và quyền sử dụng chức năng.
2. Giới hạn total request size và file size trước khi ghi.
3. Allowlist kiểu file thật sự cần, không mở rộng tùy tiện.
4. Kiểm tra cấu trúc file bằng parser/decoder phù hợp; MIME header và magic bytes chỉ là một phần.
5. Giới hạn kích thước sau decode và chi phí xử lý ảnh.
6. Sinh tên lưu trữ **từ server**, không dùng tên file người gửi để quyết định vị trí.
7. Lưu trong vùng không tự động được web server thực thi hoặc public serve.
8. Kiểm tra malware hoặc dùng cơ chế scanning/sandbox phù hợp với mức rủi ro.
9. Phân quyền truy cập file đã lưu và đặt Content-Type khi trả nội dung.

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

// uploadDirectory do ứng dụng cấu hình và bảo vệ bằng quyền OS.
Path target = Files.createTempFile(
    uploadDirectory,
    "upload-",
    ".bin"
);
~~~

Tệp tạm do server tạo giúp giảm phụ thuộc vào client filename. Tuy nhiên, phải bảo vệ **thư mục đích**, kiểm soát quyền truy cập và xóa file khi validation thất bại.

**Không coi phần mở rộng .jpg hoặc Content-Type: image/jpeg là bằng chứng file chắc chắn là ảnh hợp lệ.** Những file đa dạng và parser phức tạp cần lớp phòng thủ phù hợp.

## 20. Zip bomb, decompression bomb và XML/entity expansion

Một payload nén vài KB có thể giải nén thành hàng trăm MB hoặc hơn. Giới hạn kích thước byte **trước giải nén** không bảo vệ đủ.

Khi xử lý ZIP/gzip và các định dạng tương tự:

- Giới hạn **compressed input bytes**.
- Giới hạn **tổng decompressed bytes** và **bytes mỗi entry**.
- Giới hạn **số entries, độ sâu của cấu trúc lồng nhau, thời gian CPU**.
- Kiểm soát **đường dẫn entry** nếu giải nén ra filesystem.
- Từ chối dữ liệu lỗi/trùng/không phù hợp với định dạng và hợp đồng.

~~~text
compressed bytes (giới hạn A)
   |
   v
decompressor / parser
   |
   v
expanded bytes (giới hạn B) + entry count + timeout
   |
   v
staging storage, chỉ commit khi hợp lệ
~~~

Với XML, đặc biệt cần cấu hình parser ngăn **XXE (XML External Entity)** và entity expansion theo API parser cụ thể. Việc chỉ kiểm tra XML text bằng regex không thay thế cấu hình parser an toàn.

Đừng chạy giải nén hoặc xử lý ảnh/pdf không kiểm soát ngay trên request thread với quyền hệ điều hành rộng. Với nội dung không đáng tin và công việc có rủi ro cao, cân nhắc cô lập xử lý và hạn mức tài nguyên ở hạ tầng.

## 21. SQL Injection: dữ liệu phải là parameter, không phải cú pháp

Validation về chiều dài và định dạng giúp dữ liệu nhất quán, nhưng **không phải biện pháp chống SQL injection chính**. Dữ liệu được chèn vào SQL phải được truyền qua **PreparedStatement**:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

static boolean hasOrder(
        Connection connection,
        long authenticatedAccountId,
        String orderId) throws SQLException {

    String sql = """
        SELECT 1
          FROM orders
         WHERE account_id = ?
           AND order_id = ?
        """;

    try (PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setLong(1, authenticatedAccountId);
        statement.setString(2, orderId);

        try (ResultSet rows = statement.executeQuery()) {
            return rows.next();
        }
    }
}
~~~

Sử dụng **account_id** lấy từ principal đã xác thực, kết hợp với kiểm tra quyền nghiệp vụ để giới hạn phạm vi dữ liệu. Dùng parameter binding cho **data values**, kể cả khi chúng đã vượt qua validation.

Các thành phần cấu trúc như **tên table, tên column, ASC/DESC** thường không thể được parameterize như giá trị. Nếu cần lựa chọn động, **ánh xạ từ danh sách lựa chọn cố định sang câu SQL thuộc sở hữu ứng dụng**:

~~~java
static String sortColumn(String requested) {
    return switch (requested) {
        case "created" -> "created_at";
        case "total" -> "total_amount";
        default -> throw new IllegalArgumentException("Unsupported sort");
    };
}
~~~

**Không nối trực tiếp requested vào SQL**. Việc tự escape dấu nháy hoặc cấm chuỗi có từ khóa SQL không thay được parameterization.

## 22. Path traversal và filesystem boundary

Một tên file do người dùng gửi có thể chứa **../**, dấu phân cách hệ điều hành hoặc các dạng encoding khác nhau. Không cho đầu vào bên ngoài quyết định đường dẫn filesystem tùy ý.

Cách đơn giản nhất cho upload: **server sinh tên file**. Nếu nghiệp vụ thực sự cần một **tên tệp logic**, hãy giới hạn nó thành một ID hoặc basename có grammar cố định:

~~~java
import java.nio.file.Path;
import java.util.regex.Pattern;

private static final Pattern FILE_KEY =
    Pattern.compile("[a-zA-Z0-9_-]{1,40}");

static Path resolveFileKey(Path trustedDirectory, String key) {
    if (key == null || !FILE_KEY.matcher(key).matches()) {
        throw new IllegalArgumentException("Invalid file key");
    }

    Path base = trustedDirectory.toAbsolutePath().normalize();
    Path target = base.resolve(key + ".data").normalize();

    if (!target.startsWith(base)) {
        throw new IllegalArgumentException("Outside storage root");
    }

    return target;
}
~~~

**Đây chỉ là minh họa một tập tên rất hẹp**. Trong hệ thống thực, kiểm tra lexical bằng normalize/startsWith không bảo vệ đầy đủ trước **symbolic links, symlink races, hard links, mount points** hoặc việc thay đổi thư mục giữa kiểm tra và mở file.

Với thao tác nhạy cảm, cần bảo vệ thư mục bằng quyền OS, dùng API hỗ trợ kiểm soát symlink và atomic create/move phù hợp; nơi cần chống TOCTOU nghiêm ngặt có thể xem xét **SecureDirectoryStream** khi filesystem provider hỗ trợ. Không xem một kiểm tra Path đơn lẻ là sandbox bảo mật.

## 23. OS command và argument injection

Nếu ứng dụng phải khởi động một chương trình ngoài, **không ghép input vào chuỗi lệnh shell**.

~~~java
// Không dùng:
// Runtime.getRuntime().exec("sh -c 'tool " + userInput + "'");
// hoặc tạo "cmd /c ..." với dữ liệu người dùng nối thẳng.
~~~

Đối với chương trình có mục tiêu rõ ràng, nên truyền **danh sách đối số tách biệt** bằng ProcessBuilder và chỉ dùng executable được cấu hình tin cậy:

~~~java
import java.util.List;

ProcessBuilder builder = new ProcessBuilder(
    List.of(
        "/opt/app/bin/report-tool",
        "--format",
        "json",
        "--request-id",
        trustedRequestId
    )
);

// Không chạy trong ví dụ này.
~~~

**ProcessBuilder tránh một lớp shell tokenization khi không gọi shell**, nhưng không tự chống **argument/option injection** nếu chương trình đích diễn giải giá trị đối số như một option, path, pattern hoặc script. Hãy dùng grammar/allowlist cho từng đối số, dấu chấm dứt option **--** khi chương trình hỗ trợ và tách dữ liệu khỏi lệnh.

Hạn chế quyền tiến trình, tài nguyên, thời gian chạy và nội dung stdout/stderr được lưu/log. Nếu có thể gọi một Java API trực tiếp, thường an toàn và dễ kiểm thử hơn việc gọi shell.

## 24. SSRF: URL hợp lệ chưa chắc là đích được phép

Một URI HTTPS hợp lệ về cú pháp vẫn có thể trỏ đến host không được phép hoặc bị chuyển hướng đến dịch vụ nội bộ. Khi server tải tài nguyên theo địa chỉ người dùng cung cấp, cần phòng **Server-Side Request Forgery (SSRF)**.

Những điều kiện phòng vệ quan trọng:

- Chỉ cho scheme cần thiết, thường **https**, và chỉ những đích có **allowlist rõ ràng** khi nghiệp vụ cho phép.
- Kiểm tra host/port theo hợp đồng, không dùng so hậu tố thiếu ranh giới.
- Kiểm soát các địa chỉ IPv4/IPv6 thực sự được kết nối, kể cả loopback, link-local và địa chỉ mạng riêng theo chính sách.
- Chặn **DNS rebinding** và trường hợp kiểm tra DNS một lần nhưng HTTP client phân giải lại khi connect.
- Không tự động theo redirect đến host/port mới mà không áp lại chính sách.
- Đặt timeout, giới hạn response bytes và số kết nối đồng thời.
- Duy trì kiểm tra TLS hostname/certificate; không tắt để “cho qua” lỗi.

**Chỉ gọi InetAddress.getAllByName trước rồi kiểm tra một IP là chưa đủ**, vì client có thể phân giải lại giữa thời điểm kiểm tra và kết nối. Với tải nội dung từ bên ngoài, nên có **egress proxy/gateway hoặc transport thực thi chính sách tới IP đích khi kết nối**.

Đây là lý do validation ở tầng URI cần kết hợp **network-layer controls**. Một API riêng lẻ như **URI.create** không phải bộ lọc SSRF.

## 25. Output encoding: dữ liệu hợp lệ vẫn có thể gây XSS

Một comment hợp lệ có thể chứa dấu **<**, **>**, **&** hoặc dấu nháy vì người dùng đang viết nội dung tự nhiên. Khi hiển thị comment dưới dạng HTML, **môi trường HTML** có quy tắc diễn giải khác với Java String.

Vì vậy, khi đưa dữ liệu không tin cậy vào trình duyệt:

- HTML text node → encode theo HTML text context.
- HTML attribute → encode theo attribute context và luôn quote attribute đúng quy tắc.
- JavaScript string / DOM → không chèn trực tiếp input vào script; dùng JSON serialization/API DOM an toàn.
- URL → kiểm tra scheme và encode đúng URI component.
- CSS → không chèn input thành cấu trúc CSS tùy ý.

**Không có một hàm escape duy nhất an toàn cho mọi context.** Hãy dùng template engine có auto-escaping đúng context hoặc thư viện output encoding được bảo trì.

Ví dụ minh họa **chỉ cho HTML text node**, không dùng làm một hàm XSS universal:

~~~java
static String escapeHtmlText(String value) {
    return value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;");
}
~~~

~~~java
System.out.println(escapeHtmlText("<b>Hello</b>"));
// &lt;b&gt;Hello&lt;/b&gt;
~~~

Không dùng hàm này cho **href, onclick, style, JSON hoặc SQL**. Nếu sản phẩm cho phép rich HTML do người dùng nhập, cần **HTML sanitizer phù hợp**, kết hợp chính sách phần tử/thuộc tính, thay vì regex loại vài tag.

## 26. Logging an toàn và tránh log injection

Khi validation thất bại, một sai lầm thường gặp là ghi nguyên văn input và exception message vào log. Input có thể chứa **newline, ký tự điều khiển, token hoặc thông tin cá nhân**.

~~~java
// Tránh ghi trực tiếp toàn bộ input:
// logger.warning("Bad value: " + rawRequestBody);
~~~

Một sự kiện log nên mang metadata có cấu trúc:

~~~text
event=input_rejected
field=productId
reason=invalid_format
requestId=...
receivedLength=...
~~~

Không cần ghi lại toàn bộ **Authorization header**, session cookie, password, token hoặc dữ liệu nhận dạng nhạy cảm. Nếu thực sự phải ghi một giá trị người dùng, hãy đặt giới hạn độ dài và escape ký tự điều khiển theo định dạng log, đồng thời tuân thủ chính sách lưu trữ dữ liệu.

**Log không phải một kênh miễn phí**: request bị từ chối liên tục cũng có thể gây quá tải disk/CPU hoặc tạo quá nhiều metric labels. Cần sampling/rate limiting cho sự kiện phù hợp và theo dõi lỗi logging.

## 27. Thông điệp lỗi công khai và lỗi nội bộ

Một hệ thống nên phân biệt:

- **400 Bad Request:** cú pháp/kiểu/field sai theo hợp đồng nhận.
- **413 Content Too Large:** body vượt giới hạn được áp dụng.
- **401/403:** vấn đề xác thực hoặc phân quyền, tùy hoàn cảnh.
- **409/422:** xung đột trạng thái hoặc vi phạm quy tắc nghiệp vụ, theo API contract.
- **429:** vượt giới hạn tốc độ.
- **500/503:** lỗi nội bộ hoặc dependency không sẵn sàng.

Không được mặc định mọi IllegalArgumentException từ mọi tầng đều có nghĩa client gửi sai. Một IllegalArgumentException xảy ra trong thuật toán nội bộ cũng có thể là bug.

Ví dụ response có cấu trúc:

~~~java
record PublicError(
    String code,
    String message,
    String requestId
) {}
~~~

API có thể trả **code = INVALID_PRODUCT_ID** và câu thông báo đủ giúp sửa yêu cầu, nhưng **không trả stack trace, SQL statement, local path, secret, parser internals** cho client.

Tại tầng server, giữ cause chain và metadata an toàn để điều tra. Với định dạng HTTP Problem Details được hệ thống chọn, cần giữ tính ổn định và phân loại đúng các trường công khai.

## 28. Không dựa vào một cờ “validated = true”

Một object đã được validate ở tầng transport có thể vẫn chứa thông tin cần thêm kiểm tra trước khi dùng vào một hành động cụ thể.

Ví dụ:

~~~text
Input: valid product ID
   |
   v
Domain: sản phẩm có tồn tại không?
   |
   v
Authorization: tài khoản này được phép đặt sản phẩm đó không?
   |
   v
Business: có đủ hạn mức và tồn kho không?
   |
   v
Storage: PreparedStatement + transaction
~~~

Hãy phân biệt các kiểu ở từng bước:

- **RawRequest**: dữ liệu do client gửi.
- **ValidatedCommand**: đã thỏa schema và giới hạn đầu vào.
- **AuthorizedAction**: có principal và resource scope phù hợp.
- **DomainResult**: kết quả nghiệp vụ đã áp dụng transaction và bất biến.

Không nhất thiết phải tạo một class cho từng trạng thái trong mọi ứng dụng. Điều quan trọng là **không trộn** dữ liệu tự khai của người dùng với thông tin đáng tin cậy của server và không có một hàm validator nào được xem là cấp mọi loại quyền truy cập.

## 29. Thiết kế DTO chỉ nhận đúng dữ liệu cần thiết

Records cung cấp một cách diễn đạt dữ liệu yêu cầu gọn và hiện đại trong Java:

~~~java
import java.util.Objects;

record CreateOrderRequest(String productId, int quantity, String comment) {
    CreateOrderRequest {
        Objects.requireNonNull(productId, "productId");

        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException("Quantity out of range");
        }
    }
}
~~~

Tuy nhiên, constructor ở đây **chưa đủ** để bảo đảm toàn bộ security contract: cần kiểm tra grammar productId, độ dài comment, điều kiện quyền và giới hạn body trước khi binding.

Nên có những lớp riêng cho **field do server sở hữu** như user role, tenant ID hoặc trạng thái phê duyệt; không tự nhận chúng từ JSON client mà không có cơ chế mapping/authorization rõ ràng.

Với dữ liệu bất biến, nhớ rằng record chỉ **shallow immutable**. Nếu một component chứa List mutable, cần sao chép với **List.copyOf** và kiểm tra các phần tử; tránh để external code sửa danh sách sau khi validation.

## 30. Ví dụ hoàn chỉnh không cần mạng: bounded UTF-8 + command validation

Ví dụ dưới đây chỉ dùng API Java chuẩn và chạy độc lập với JDK 27. Nó minh họa **giới hạn byte trước decode**, **strict UTF-8**, **Unicode NFC**, **allowlist product ID**, **quantity range** và **giới hạn title sau chuẩn hóa**.

Lưu thành **InputBoundaryDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.regex.Pattern;

public class InputBoundaryDemo {
    static final int MAX_BODY_BYTES = 1024;
    static final int MAX_TITLE_CODE_POINTS = 60;
    static final int MAX_TITLE_BYTES = 240;

    private static final Pattern PRODUCT_ID =
        Pattern.compile("[A-Z0-9](?:[A-Z0-9-]{0,30}[A-Z0-9])?");

    record OrderCommand(String productId, int quantity, String title) {}

    static byte[] readBounded(InputStream input, int maxBytes)
            throws IOException {

        if (maxBytes < 0 || maxBytes > MAX_BODY_BYTES) {
            throw new IllegalArgumentException("Invalid byte limit");
        }

        byte[] bytes = input.readNBytes(maxBytes + 1);

        if (bytes.length > maxBytes) {
            throw new IllegalArgumentException("Body too large");
        }
        return bytes;
    }

    static String decodeUtf8Strict(byte[] bytes)
            throws CharacterCodingException {

        var decoder = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);

        return decoder.decode(ByteBuffer.wrap(bytes)).toString();
    }

    static String requireProductId(String raw) {
        if (raw == null || raw.length() > 32
                || !PRODUCT_ID.matcher(raw).matches()) {
            throw new IllegalArgumentException("Invalid product ID");
        }
        return raw;
    }

    static int requireQuantity(String raw) {
        if (raw == null || raw.length() > 3
                || !raw.matches("[1-9][0-9]{0,2}")) {
            throw new IllegalArgumentException("Invalid quantity");
        }

        int quantity = Integer.parseInt(raw);
        if (quantity > 100) {
            throw new IllegalArgumentException("Quantity too high");
        }
        return quantity;
    }

    static String requireTitle(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Missing title");
        }

        String title = Normalizer.normalize(raw, Normalizer.Form.NFC);

        if (title.isBlank()
                || title.codePointCount(0, title.length())
                    > MAX_TITLE_CODE_POINTS
                || title.getBytes(StandardCharsets.UTF_8).length
                    > MAX_TITLE_BYTES
                || title.codePoints().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException("Invalid title");
        }

        return title;
    }

    static OrderCommand validate(
            String productId, String quantity, String title) {

        return new OrderCommand(
            requireProductId(productId),
            requireQuantity(quantity),
            requireTitle(title)
        );
    }

    public static void main(String[] args) throws Exception {
        OrderCommand accepted = validate(
            "PEN-01", "12", "Ca\u0300 phê"
        );

        System.out.println(
            accepted.productId() + " x" + accepted.quantity()
                + ": " + accepted.title()
        );

        byte[] validBody = "Xin chào".getBytes(
            StandardCharsets.UTF_8
        );

        try (InputStream input = new ByteArrayInputStream(validBody)) {
            String decoded = decodeUtf8Strict(
                readBounded(input, MAX_BODY_BYTES)
            );
            System.out.println("Decoded: " + decoded);
        }

        try {
            validate("PEN-01", "101", "Sản phẩm");
            throw new AssertionError("Expected rejection");
        } catch (IllegalArgumentException expected) {
            System.out.println("Oversized quantity rejected");
        }

        try (InputStream input = new ByteArrayInputStream(
                new byte[] {(byte) 0xC3, (byte) 0x28})) {
            decodeUtf8Strict(readBounded(input, MAX_BODY_BYTES));
            throw new AssertionError("Expected malformed UTF-8");
        } catch (CharacterCodingException expected) {
            System.out.println("Malformed UTF-8 rejected");
        }

        try (InputStream input = new ByteArrayInputStream(
                new byte[MAX_BODY_BYTES + 1])) {
            readBounded(input, MAX_BODY_BYTES);
            throw new AssertionError("Expected byte-limit rejection");
        } catch (IllegalArgumentException expected) {
            System.out.println("Oversized body rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 InputBoundaryDemo.java
java InputBoundaryDemo
~~~

Kết quả mong đợi:

~~~text
PEN-01 x12: Cà phê
Decoded: Xin chào
Oversized quantity rejected
Malformed UTF-8 rejected
Oversized body rejected
~~~

**Giới hạn của demo:** Nó chưa triển khai một HTTP server, JSON parser, authentication, authorization, rate limiter hoặc hệ thống lưu trữ. Nó cũng chưa giới hạn thời gian đọc InputStream và chưa xử lý file streaming phức tạp. Trong ứng dụng thật, những phần đó phải được đặt ở đúng ranh giới hạ tầng và được kiểm thử tích hợp.

## 31. Kiểm thử input boundaries theo hướng tấn công và sai sót

Để tránh chỉ kiểm tra happy path, nên chia test theo nhóm:

**Kích thước và cấu trúc:** body 0 byte, body đúng giới hạn, vượt 1 byte, mảng rỗng, array quá dài, object quá sâu, duplicate keys, unknown fields, trường null/missing, string cực dài, nhiều request đồng thời.

**Kiểu dữ liệu:** số âm, số 0, số vượt max, số vượt long/int, số thập phân tại trường integer, NaN/Infinity nếu parser cho phép, ngày không tồn tại, ngày ngoài phạm vi, enum không được công bố.

**Text/Unicode:** UTF-8 malformed, surrogate lẻ, tên có combining marks, NFC/NFD, emoji nhiều code points, newline/CR/LF, ký tự định hướng hiển thị và những giá trị hợp lệ bằng tiếng Việt.

**Cross-context:** dấu nháy trong SQL value, chuỗi HTML trong comment, path có dấu phân cách, URL có redirect, argument bắt đầu bằng **-**, giá trị log có newline. Mục tiêu là bảo đảm **API an toàn ở sink**, không chỉ “validator không nhận chuỗi lạ”.

**Resource exhaustion:** upload lớn, zip phình dữ liệu, regex đầu vào dài gần khớp, request gửi chậm, retry vô hạn, fan-out nhiều tác vụ và giới hạn disk tạm.

**Authorization:** tài nguyên thuộc user/tenant khác, token thiếu quyền, trường ownerId do client tự sửa và thao tác có trạng thái không phù hợp.

Kiểm thử nên xác nhận **cách từ chối rõ ràng**, không chỉ chờ một exception bất kỳ. Với các ranh giới nhạy cảm, có thể bổ sung property-based testing, fuzz testing và quan sát mức tiêu thụ tài nguyên trong môi trường kiểm soát.

## 32. Các anti-pattern cần tránh

| Anti-pattern | Tác hại | Phương án đúng hơn |
|---|---|---|
| “Frontend đã validate rồi” | Client có thể bị sửa/bỏ qua | Validate ở server |
| Tin dữ liệu nội bộ vô điều kiện | Stored malicious data, schema drift | Validate tại mỗi ranh giới tiếp nhận |
| Regex chặn vài từ “nguy hiểm” | Thiếu bao phủ, loại dữ liệu hợp lệ | Field-specific allowlist + safe sink API |
| Đọc toàn body rồi mới kiểm tra byte count | Memory/CPU exhaustion đã xảy ra | Limit trước parse/đọc, có streaming quota |
| Tin Content-Length hoàn toàn | Header có thể thiếu/không đủ | Đếm byte thực nhận |
| Chỉ kiểm tra số ký tự Java | Sai với UTF-8, emoji | Giới hạn codepoints và bytes theo mục tiêu |
| Normalize mọi dữ liệu vô điều kiện | Đổi ý nghĩa/chữ ký/token | Chính sách Unicode theo trường |
| Regex unbounded/backtracking phức tạp | ReDoS | Bound input và pattern đơn giản |
| Bind request trực tiếp vào entity nhạy cảm | Overposting | DTO riêng với field allowlist |
| SQL string concatenation sau validation | Injection khi sink diễn giải cú pháp | PreparedStatement / binding |
| Ghép URL từ input rồi gọi HTTP | SSRF, redirect tới mạng nội bộ | Host allowlist + connection-time egress control |
| Chỉ chuẩn hóa Path rồi coi an toàn | Symlink/race vẫn có | Server-owned name, OS permissions, safe file operations |
| Tin filename/MIME từ upload | File format giả hoặc thực thi nguy hiểm | Server-generated name + parser/quotas |
| Chỉ giới hạn ZIP bytes nén | Decompression bomb | Limit compressed và expanded bytes |
| Ghi log full body khi bị từ chối | Lộ secret, log injection và DoS | Structured metadata + redaction |
| Báo client stack trace/SQL lỗi | Rò rỉ triển khai | Stable public error code |
| Dùng validation thay authorization | IDOR/BOLA | Object-level authorization theo principal |
| “Đã qua validate = mọi nơi đều an toàn” | Bối cảnh đầu ra khác nhau | Contextual encoding/parameterized APIs |
| Chỉ đặt per-request limit | Lạm dụng nhiều request nhỏ | Rate limit/concurrency/quota theo identity |

## 33. Bài tập thực hành

**Bài tập 1 — Field contract.** Thiết kế DTO cho yêu cầu đặt hàng có 20 sản phẩm tối đa. Ghi rõ trường nào nhận từ client, trường nào do server cấp, giới hạn số item, giá trị quantity và điều kiện nghiệp vụ.

**Bài tập 2 — Unicode.** Với chuỗi có tiếng Việt, emoji và combining marks, in **String.length()**, **codePointCount** và byte UTF-8. Đặt giới hạn phù hợp cho display name, rồi kiểm thử cả NFC và NFD.

**Bài tập 3 — Streaming byte limit.** Viết hàm chỉ nhận tối đa 8 KiB, từ chối payload dài hơn đúng 1 byte, rồi giải mã UTF-8 ở chế độ REPORT. Giải thích vì sao vẫn cần network read timeout.

**Bài tập 4 — JSON parser.** Với thư viện JSON mà dự án đang sử dụng, cấu hình giới hạn nesting depth, string length, number length và array size theo khả năng API của thư viện. Thêm test duplicate keys và unknown fields.

**Bài tập 5 — SQL.** Viết truy vấn lọc đơn theo account ID đã xác thực và product ID từ request bằng PreparedStatement. Cho lựa chọn sort theo hai cột cố định; tuyệt đối không nối text sort của client vào SQL.

**Bài tập 6 — File upload.** Xây workflow staging có server-generated filename, byte quota, parser định dạng và cleanup khi lỗi. Xem xét symlink, đường dẫn ngoài thư mục và quyền OS.

**Bài tập 7 — SSRF.** Thiết kế dịch vụ tải ảnh từ host được quản trị viên cấu hình. Mô tả cách xử lý DNS rebinding, IPv4/IPv6, redirects, giới hạn dung lượng, timeout và egress policies.

**Bài tập 8 — Output encoding.** Cùng một chuỗi comment, chứng minh cách xử lý khác nhau khi đặt vào HTML text, HTML attribute, JSON body, SQL parameter và log event. Không dùng một hàm escape chung.

**Bài tập 9 — Resource quota.** Một tenant gửi 5.000 request hợp lệ mỗi giây, mỗi request chỉ 1 KiB nhưng mở 100 công việc nền. Thiết kế chính sách rate, concurrency và queue limits không khiến hệ thống phình vô hạn.

## 34. Checklist bảo mật ranh giới đầu vào cho Java 27

- [ ] Đã xác định đầy đủ các nguồn và **ranh giới tin cậy**.
- [ ] Không tự coi HTTPS, internal service hoặc database là chứng chỉ dữ liệu đáng tin hoàn toàn.
- [ ] Có hợp đồng kiểu, format, null, range, count và field allowlist cho từng input.
- [ ] Giới hạn **request bytes trước parser/deserialize**.
- [ ] Kiểm soát header size, body size, read timeout và concurrency.
- [ ] Chọn chính sách charset; từ chối malformed UTF-8 khi yêu cầu chính xác.
- [ ] Không nhầm UTF-16 length, Unicode codepoints, grapheme và byte length.
- [ ] Có chính sách Unicode normalization rõ ràng cho từng trường nếu cần.
- [ ] Giới hạn chiều dài trước regex và tránh cấu trúc dễ ReDoS.
- [ ] Cấu hình parser limit cho nesting depth, array/object size và number/string length.
- [ ] Từ chối trường không được phép, tránh mass assignment vào các entity nhạy cảm.
- [ ] Có giới hạn tổng số task, batch size, memory, disk và tài nguyên sau giải nén.
- [ ] Tách validation khỏi **authentication và authorization** theo principal/resource.
- [ ] Dùng **PreparedStatement** và binding cho SQL data values.
- [ ] Sử dụng output encoding đúng ngữ cảnh khi hiển thị nội dung người dùng.
- [ ] Với filesystem, dùng server-owned filename, quyền OS và bảo vệ symlink/race phù hợp.
- [ ] Với command execution, tránh shell string concatenation và kiểm soát options/arguments.
- [ ] Với outbound HTTP, có SSRF policy tại thời điểm kết nối, revalidation redirects và timeout.
- [ ] Không tin file extension, MIME header hoặc một magic byte là đủ để chấp nhận file.
- [ ] Không log token, password, full request body hay dữ liệu nhạy cảm không cần thiết.
- [ ] Có mã lỗi công khai ổn định, không trả stack trace hoặc thông tin kỹ thuật nhạy cảm.
- [ ] Kiểm thử đúng giới hạn, vượt 1 đơn vị, dữ liệu null, Unicode bất thường và malformed input.
- [ ] Có kiểm thử tích hợp cho tải lớn, timeout, concurrency, authorization và các sink nguy hiểm.
- [ ] Giám sát rejection rate, memory, queue, I/O và tài nguyên được sử dụng.

**Kết luận:** Bảo mật đầu vào trong Java 27 không phải là viết một hàm lọc ký tự nguy hiểm. Cần xác định **ai kiểm soát dữ liệu**, **thao tác nào sắp sử dụng dữ liệu đó** và **hệ thống được phép tiêu thụ bao nhiêu tài nguyên**. Validation theo từng trường, hạn mức trước parse, ranh giới xác thực/phân quyền và các API xử lý đầu ra đúng ngữ cảnh tạo nên một hệ thống phòng thủ nhiều lớp. Ngay cả khi dữ liệu hợp lệ về cú pháp, các quyết định bảo mật và giới hạn ở nơi tiêu thụ vẫn phải được thực thi.

## Tài liệu tham khảo

- [OWASP — Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html): field allowlist, syntax/semantic validation, Unicode, input limits.
- [OWASP — Denial of Service Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html): request size, parser/regex complexity, timeout, rate/concurrency limits.
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): filename, Content-Type, storage, file type và quotas.
- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): parameterized queries và allowlist SQL identifiers.
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): output encoding theo context và HTML sanitization.
- [OWASP — Server Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): allowlist, IP validation, DNS rebinding.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): logging an toàn và dữ liệu cần tránh ghi.
- [Java SE 27 — InputStream](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/InputStream.html): readNBytes và streaming I/O.
- [Java SE 27 — CharsetDecoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/CharsetDecoder.html): malformed/unmappable input và CodingErrorAction.
- [Java SE 27 — Pattern](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/regex/Pattern.html): regex và kiểm tra cú pháp.
- [Java SE 27 — Normalizer](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/text/Normalizer.html): các dạng Unicode normalization.
- [Java SE 27 — PreparedStatement](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/PreparedStatement.html): binding cho SQL parameters.
- [Java SE 27 — Files](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html), [Path](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Path.html): thao tác filesystem và kiểm soát ranh giới file.
- [Java SE 27 — HttpClient](https://docs.oracle.com/en/java/javase/27/docs/api/java.net.http/java/net/http/HttpClient.html): request/response và timeout.
- [CWE-20 — Improper Input Validation](https://cwe.mitre.org/data/definitions/20.html): định nghĩa và rủi ro kiểm tra đầu vào không đầy đủ.
