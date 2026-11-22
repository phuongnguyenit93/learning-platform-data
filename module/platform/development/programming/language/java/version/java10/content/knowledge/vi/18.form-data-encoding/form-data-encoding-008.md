# Tránh mã hóa lặp hoặc giải mã quá số lần quy định trong dữ liệu biểu mẫu Java

## Mục tiêu bài học

Khi truyền dữ liệu biểu mẫu theo định dạng `application/x-www-form-urlencoded`, ứng dụng cần **mã hóa (encode)** các tên và giá trị tham số trước khi gửi, và **giải mã (decode)** tại đúng ranh giới tiếp nhận. Mã hóa hoặc giải mã **nhiều lần không có chủ đích** có thể làm sai dữ liệu, gây lỗi tương thích và tạo ra lỗ hổng khi các tầng của hệ thống hiểu dữ liệu theo cách khác nhau.

Từ Java 10, hai phương thức sau hỗ trợ truyền trực tiếp `Charset`:

~~~java
URLEncoder.encode(String s, Charset charset)
URLDecoder.decode(String s, Charset charset)
~~~

Chúng vẫn được hỗ trợ trong Java hiện đại. Bài viết dùng **JDK 17+** và `StandardCharsets.UTF_8`, không dùng các overload không tham số charset đã lỗi thời.

Sau bài học, bạn sẽ:

- Hiểu quy tắc mã hóa biểu mẫu, đặc biệt `space` ↔ `+`, dấu cộng thực ↔ `%2B`, dấu phần trăm ↔ `%25`.
- Phân biệt **giá trị gốc**, **thành phần đã mã hóa** và **giá trị đã được framework giải mã**.
- Nhận biết lỗi **double encoding** và **double decoding**, kể cả khi dữ liệu có dấu `%` hợp lệ.
- Thiết kế pipeline mà mỗi tầng biết rõ nhiệm vụ, không tự “thử giải mã tiếp” hoặc “mã hóa nếu có vẻ chưa mã hóa”.
- Biết khi nào `URLEncoder` **không** thích hợp, ví dụ để mã hóa nguyên một URL hoặc một path.
- Viết và chạy ví dụ Java 17+ với stdout xác định.

## 1. `URLEncoder`/`URLDecoder` dùng cho định dạng nào?

`java.net.URLEncoder` và `java.net.URLDecoder` xử lý **HTML form encoding**, tức `application/x-www-form-urlencoded`; tên lớp không có nghĩa chúng là bộ xử lý chung cho mọi dạng URI.

Với `URLEncoder.encode(s, StandardCharsets.UTF_8)`:

| Ký tự đầu vào | Kết quả trong thành phần biểu mẫu | Giải thích |
| --- | --- | --- |
| Các chữ cái ASCII, chữ số | Giữ nguyên | Nhóm ký tự được phép |
| `.`, `-`, `*`, `_` | Giữ nguyên | Nhóm ký tự an toàn trong form encoding |
| Dấu cách ASCII ` ` | `+` | Quy ước riêng của form encoding |
| Dấu cộng thực `+` | `%2B` | Không nhầm dấu cộng của dữ liệu với dấu cách |
| Dấu phần trăm `%` | `%25` | Dấu `%` mở đầu một chuỗi percent-escape |
| Dấu bằng `=` | `%3D` | Không bị xem thành dấu chia khóa–giá trị |
| Dấu và `&` | `%26` | Không bị xem thành dấu phân cách các tham số |
| Dấu gạch chéo `/` | `%2F` | Bảo vệ ký tự dữ liệu trong một thành phần |
| Chữ `à` với UTF-8 | `%C3%A0` | Một ký tự có thể gồm nhiều byte UTF-8 |

`URLDecoder.decode(s, StandardCharsets.UTF_8)` thực hiện quá trình ngược: chuyển `+` thành dấu cách, chuyển `%HH` thành byte và dùng charset để giải mã byte thành ký tự.

Ví dụ:

~~~java
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

String raw = "A+B & C";
String encoded = URLEncoder.encode(raw, StandardCharsets.UTF_8);
// encoded = "A%2BB+%26+C"

String decoded = URLDecoder.decode(encoded, StandardCharsets.UTF_8);
// decoded = "A+B & C"
~~~

Đoạn trên là mã **minh họa trong một phương thức**, không phải chương trình độc lập.

**Nguyên tắc:** `URLEncoder` dùng cho **một tên hoặc một giá trị tham số**, không dùng để mã hóa cả chuỗi URL đã có `https://`, `?`, `&`, `=` và các dấu phân cách khác.

## 2. Mã hóa một lần là thế nào?

Giả sử người dùng nhập nội dung gốc:

~~~text
cà phê + 50%
~~~

Đây là giá trị **chưa mã hóa**. Với UTF-8, dạng form-encoded tương ứng là:

~~~text
c%C3%A0+ph%C3%AA+%2B+50%25
~~~

Khi gắn giá trị vào một tham số `q`:

~~~java
String raw = "cà phê + 50%";
String encodedValue = URLEncoder.encode(raw, StandardCharsets.UTF_8);

String query = "q=" + encodedValue;
// q=c%C3%A0+ph%C3%AA+%2B+50%25
~~~

Chỉ **giá trị** được đưa qua `URLEncoder` một lần; dấu `=` giữa khóa và giá trị là dấu phân cách do chương trình **chủ động thêm** ở tầng xây dựng query.

Tại đầu nhận, một parser biểu mẫu phù hợp xử lý thành phần đã mã hóa và trả về giá trị gốc. Nếu framework đã làm việc này, code ứng dụng dùng **giá trị đã giải mã** mà không gọi `URLDecoder` thêm lần nữa.

### Mô hình ba trạng thái dữ liệu

| Trạng thái | Ví dụ | Có nên gọi API nào? |
| --- | --- | --- |
| **Raw/plain value** — dữ liệu gốc | `"A+B"` | `URLEncoder.encode` **một lần** khi chuyển thành thành phần biểu mẫu |
| **Encoded form component** — dữ liệu trong query/body | `"A%2BB"` | Gửi nguyên dạng; **không encode lại** |
| **Decoded value** — dữ liệu sau parser | `"A+B"` | Xử lý nghiệp vụ; **không decode lần nữa** |

Bằng cách theo dõi trạng thái ở mỗi ranh giới, bạn tránh được việc hai lớp cùng nghĩ rằng mình là nơi chịu trách nhiệm mã hóa/giải mã.

## 3. Double encoding: vì sao mã hóa hai lần làm sai dữ liệu?

Ví dụ:

~~~java
String raw = "A+B";
String once = URLEncoder.encode(raw, StandardCharsets.UTF_8);
// once = "A%2BB"

String twice = URLEncoder.encode(once, StandardCharsets.UTF_8);
// twice = "A%252BB"
~~~

Lần đầu chuyển dấu cộng của dữ liệu thành `%2B`. Lần hai coi ký tự `%` **trong chuỗi đã mã hóa** là một ký tự dữ liệu mới, nên chuyển nó thành `%25`.

Đầu nhận giải mã **đúng một lần** sẽ thấy:

~~~java
String received = URLDecoder.decode(twice, StandardCharsets.UTF_8);
// received = "A%2BB" thay vì "A+B"
~~~

Dữ liệu đến tầng nghiệp vụ vẫn chứa cú pháp percent-escape, dù người dùng vốn nhập dấu cộng. Đây là một nguyên nhân phổ biến của lỗi tìm kiếm, chữ ký request, khóa cache hoặc lưu trữ giá trị sai.

### Double encoding với dấu cách và Unicode

Ví dụ chuỗi `"cà phê + 50%"`:

| Giai đoạn | Nội dung |
| --- | --- |
| Gốc | `cà phê + 50%` |
| Encode một lần | `c%C3%A0+ph%C3%AA+%2B+50%25` |
| Encode hai lần | `c%25C3%25A0%2Bph%25C3%25AA%2B%252B%2B50%2525` |
| Decode một lần từ chuỗi encode hai lần | `c%C3%A0+ph%C3%AA+%2B+50%25` — vẫn là dạng đã mã hóa |

**Không nên sửa bằng cách luôn decode hai lần.** Có thể dữ liệu thực tế đã được mã hóa đúng một lần và chứa một chuỗi giống escape như `"%2B"` **một cách có chủ đích**. Giải mã thêm sẽ thay đổi ý nghĩa của dữ liệu đó.

## 4. Double decoding: một chuỗi hợp lệ có thể bị biến dạng

Giả sử **nội dung thực mà người dùng nhập** là năm ký tự:

~~~text
%2B
~~~

Đây hoàn toàn có thể là một mã sản phẩm, mã định danh, mẫu tìm kiếm hoặc chuỗi người dùng muốn giữ nguyên. Để truyền đúng nội dung này trong biểu mẫu:

~~~java
String raw = "%2B";
String encoded = URLEncoder.encode(raw, StandardCharsets.UTF_8);
// encoded = "%252B"
~~~

Đầu nhận phải decode **một lần**:

~~~java
String once = URLDecoder.decode("%252B", StandardCharsets.UTF_8);
// once = "%2B"  — đúng dữ liệu gốc

String twice = URLDecoder.decode(once, StandardCharsets.UTF_8);
// twice = "+"   — đã thay đổi dữ liệu!
~~~

Vì vậy **`URLDecoder.decode` không có tính idempotent**: nói chung `decode(decode(x))` **không bằng** `decode(x)`. Một hệ thống không thể tùy tiện “decode đến khi không còn dấu `%`” mà vẫn bảo toàn dữ liệu hợp lệ.

Bảng đối chiếu:

| Chuỗi tại ranh giới | Decode 1 lần | Decode thêm lần 2 | Rủi ro |
| --- | --- | --- | --- |
| `A%2BB` | `A+B` | `A B` | Dấu cộng thật biến thành dấu cách |
| `%252B` | `%2B` | `+` | Chuỗi literal `%2B` bị đổi nghĩa |
| `%252F` | `%2F` | `/` | Có thể tạo ra ký tự phân cách đường dẫn |
| `%2526` | `%26` | `&` | Có thể tạo ra dấu phân tách tham số nếu tiếp tục xử lý sai |
| `%2525` | `%25` | `%` | Làm mất một tầng escape được dùng để giữ dữ liệu literal |

Đây là các ví dụ về biến đổi văn bản, **không phải chỉ dẫn phải decode hai lần**. Cột “decode thêm lần 2” chỉ để chỉ ra hậu quả khi một tầng xử lý lặp không đúng.

## 5. Dấu cộng `+`: trường hợp dễ gây lỗi khi decode nhầm

Trong `application/x-www-form-urlencoded`, `+` mang ý nghĩa **dấu cách**. Nhưng trong dữ liệu gốc, người dùng cũng có thể nhập dấu cộng thật.

~~~java
String literalPlus = "A+B";
String encoded = URLEncoder.encode(literalPlus, StandardCharsets.UTF_8);
// encoded = "A%2BB"
~~~

Ở đầu nhận:

~~~java
URLDecoder.decode("A%2BB", StandardCharsets.UTF_8); // "A+B"
URLDecoder.decode("A+B", StandardCharsets.UTF_8);   // "A B"
~~~

Nếu một framework đã decode `"A%2BB"` thành `"A+B"`, rồi bạn gọi `URLDecoder.decode` thêm một lần, dấu cộng thật **sẽ thành dấu cách**. Lỗi này có thể xảy ra ngay cả khi chuỗi sau lần decode đầu tiên **không còn dấu `%` nào**.

Vì thế quy tắc “chỉ decode thêm khi còn `%`” **không đủ** và dễ làm sai dữ liệu. Cách đúng là theo dõi rõ dữ liệu đã được decode hay chưa ở ranh giới API.

## 6. Tách cú pháp tham số trước, decode thành phần sau

Một query biểu mẫu có cấu trúc:

~~~text
key1=value1&key2=value2
~~~

Ký tự `&` phân tách các tham số và ký tự `=` đầu tiên phân tách tên với giá trị (tùy hợp đồng parser). Nhưng dữ liệu gốc của tên/giá trị **cũng có thể chứa** `&` hoặc `=`. Hai ký tự này phải được mã hóa bên trong từng thành phần.

Ví dụ:

~~~java
String name = "filter&mode";
String value = "a=b & c";

String pair = URLEncoder.encode(name, StandardCharsets.UTF_8)
        + "="
        + URLEncoder.encode(value, StandardCharsets.UTF_8);

// pair = "filter%26mode=a%3Db+%26+c"
~~~

Khi **xây dựng** query, hãy encode **riêng từng tên và từng giá trị**, rồi mới nối các dấu phân cách `=` và `&` giữa các cặp đã mã hóa.

Khi **phân tích** một chuỗi query raw, parser cần nhận diện đúng các dấu phân cách cấu trúc trước khi giải mã nội dung của từng thành phần. Nếu decode **toàn bộ raw query** trước khi phân tích dấu `&`, có thể tạo ra `&` từ `%26` vốn là **dữ liệu** chứ không phải dấu phân cách.

Ví dụ:

~~~text
Raw query:              q=a%26b
Phân tách đúng:         tên "q", giá trị được mã hóa "a%26b"
Sau decode thành phần:  tên "q", giá trị "a&b"
~~~

Nếu giải mã toàn bộ `q=a%26b` thành `q=a&b` rồi mới chia theo `&`, bạn đã tự tạo ra một tham số giả.

**Trong ứng dụng web thực tế**, hãy ưu tiên parser của framework/HTTP library được cấu hình đúng, thay vì tự viết parser bằng cách `split("&")` không xét trường hợp lặp khóa, dấu `=`, dữ liệu rỗng, charset và body encoding. Nếu framework đã trả tham số **được decode**, không decode tiếp trong controller/service.

## 7. `URLEncoder` không mã hóa một URL hoàn chỉnh

Không dùng:

~~~java
String url = "https://example.test/search?q=java&lang=vi";
// Sai mục đích: URLEncoder.encode(url, StandardCharsets.UTF_8)
~~~

Cách trên còn mã hóa cả `:`, `/`, `?`, `=` và `&` có vai trò **cấu trúc URI**, nên kết quả không còn là một URL tương đương.

Một cách xây đơn giản khi biết sẵn endpoint và tên tham số:

~~~java
String endpoint = "https://example.test/search";
String userQuery = "Java + Spring";

String url = endpoint + "?q="
        + URLEncoder.encode(userQuery, StandardCharsets.UTF_8);

// https://example.test/search?q=Java+%2B+Spring
~~~

Chỉ thành phần **giá trị q** được form-encode. Nếu cần xây URI phức tạp có path segment, query parameter, fragment hoặc nhiều cấp encoding, hãy dùng **URI builder của HTTP library/framework** và tuân theo đúng hợp đồng API của builder đó. Có những builder tự mã hóa tham số khi nhận dữ liệu gốc; encode trước khi truyền vào builder như vậy có thể lại gây **double encoding**.

**Không dùng `URLDecoder` như một bộ giải mã đường dẫn chung.** Trong đường dẫn URI, dấu cộng thường là ký tự `+` literal, không mang quy ước dấu cách của form encoding. Các quy tắc percent encoding/decoding cho từng phần URI phải được xử lý bằng API phù hợp với chính phần đó.

## 8. Chương trình Java 17+ chạy độc lập

Chương trình dưới đây tạo và đọc dữ liệu form với `StandardCharsets.UTF_8`; kiểm tra cả mã hóa lặp, giải mã lặp, ký tự `+`, dấu `%`, cấu trúc tham số và chuỗi percent-escape không hợp lệ.

Để mã nguồn có thể sao chép ngay cả khi terminal có charset hiển thị khác nhau, các ký tự có dấu trong `raw` được biểu diễn bằng Unicode escape của Java. Chương trình chỉ in dạng mã hóa ASCII và các kết quả kiểm tra.

Lưu vào file **FormOnceDemo.java**:

~~~java
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

public class FormOnceDemo {
    private static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    private static String decode(String value) {
        return URLDecoder.decode(value, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) {
        String raw = "c\u00E0 ph\u00EA + 50%";
        String encoded = encode(raw);
        String twice = encode(encoded);

        System.out.println("encoded: " + encoded);
        System.out.println("encoded twice: " + twice);
        System.out.println(
                "one roundtrip: " + raw.equals(decode(encoded))
        );
        System.out.println(
                "one decode of twice still encoded: "
                        + decode(twice).equals(encoded)
        );

        System.out.println("literal plus encoded: " + encode("A+B"));
        System.out.println("encoded plus decoded: " + decode("A%2BB"));
        System.out.println("unescaped plus decoded: " + decode("A+B"));

        System.out.println("percent once: " + decode("%252B"));
        System.out.println(
                "percent twice: " + decode(decode("%252B"))
        );

        System.out.println(
                "plain percent text roundtrip: "
                        + "%2B".equals(decode(encode("%2B")))
        );

        System.out.println(
                "encoded pair: " + encode("filter&mode")
                        + "=" + encode("a=b & c")
        );
        System.out.println(
                "split then decode: " + decode("a%26b")
        );

        try {
            decode("bad%2");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "bad escape: IllegalArgumentException"
            );
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac FormOnceDemo.java
java FormOnceDemo
~~~

**Stdout chính xác:**

~~~text
encoded: c%C3%A0+ph%C3%AA+%2B+50%25
encoded twice: c%25C3%25A0%2Bph%25C3%25AA%2B%252B%2B50%2525
one roundtrip: true
one decode of twice still encoded: true
literal plus encoded: A%2BB
encoded plus decoded: A+B
unescaped plus decoded: A B
percent once: %2B
percent twice: +
plain percent text roundtrip: true
encoded pair: filter%26mode=a%3Db+%26+c
split then decode: a&b
bad escape: IllegalArgumentException
~~~

**Diễn giải:**

1. `raw` chứa `à`, `ê`, dấu cách, dấu cộng và dấu phần trăm. UTF-8 mã hóa các chữ có dấu thành hai byte, rồi thể hiện bằng các chuỗi `%HH`.
2. Encode hai lần khiến `%C3` thành `%25C3`, còn `+` của form-encoding bị encode thành `%2B`. Một lần decode chuỗi encode hai lần vẫn còn ở trạng thái encoded.
3. `decode(encode(raw))` trả lại đúng chuỗi đầu vào hợp lệ, nên `one roundtrip` là `true`.
4. Dấu cộng literal `"A+B"` phải được gửi thành `"A%2BB"`. Decode `"A+B"` trực tiếp lại tạo `"A B"`.
5. `"%252B"` decode một lần thành **chuỗi literal `"%2B"`**, nhưng decode lần nữa thành **dấu cộng**: đây là minh họa điển hình về lỗi double decoding.
6. Ghép `filter%26mode=a%3Db+%26+c` cho thấy `&`, `=` của dữ liệu đã được mã hóa, không làm thay đổi cú pháp phân tách tham số.
7. `"bad%2"` chứa percent-escape thiếu hai chữ số hex; implementation của `URLDecoder` trên JDK minh họa ném `IllegalArgumentException`.

Chương trình không phụ thuộc mạng hoặc thư viện bên ngoài. Các kết quả `true` kiểm tra chính xác nội dung Unicode mà không dựa vào khả năng hiển thị chữ có dấu của console.

## 9. Ranh giới xử lý: ai được phép encode, ai được phép decode?

Trong một hệ thống web, dữ liệu có thể đi qua nhiều tầng:

~~~text
Biểu mẫu hoặc dữ liệu người dùng
      |
      v
Giá trị gốc (raw/plain)
      |
      | Encode MỘT LẦN nếu tự xây form body hoặc query component
      v
Form/query đã mã hóa
      |
      | Gửi qua HTTP
      v
HTTP server / framework form parser
      |
      | Decode MỘT LẦN theo hợp đồng của parser
      v
Giá trị gốc dành cho controller / service
      |
      | Validate, xử lý nghiệp vụ, lưu trữ
      v
Dữ liệu ứng dụng (không tự decode lại)
~~~

Nếu client HTTP library tự encode các tham số được cung cấp dạng plain text, hãy giao nhiệm vụ encode cho **client library**, không gọi `URLEncoder` thêm ở code nghiệp vụ. Ngược lại, nếu API yêu cầu bạn cung cấp nguyên một **form body đã mã hóa**, bạn phải encode từng thành phần đúng một lần trước khi ghép body.

Ở đầu nhận, các hàm kiểu `request.getParameter(...)` của nhiều web framework/Servlet API thường trả về giá trị **đã được parse và decode** theo cấu hình. Không viết:

~~~java
// Cần tránh nếu query đã được framework decode:
String rawValue = request.getParameter("q");
// String wronglyDecodedAgain = URLDecoder.decode(
//         rawValue, StandardCharsets.UTF_8);
~~~

Đoạn trên là minh họa **trong ngữ cảnh Servlet**, không phải chương trình Java SE độc lập. Hợp đồng cụ thể của request API, thứ tự middleware và charset cấu hình vẫn cần được xác nhận ở framework đang dùng; **không suy luận chỉ từ tên biến**.

### Thiết kế API rõ trạng thái

Có thể làm rõ kiểu dữ liệu ở ranh giới:

~~~java
record PlainFormValue(String text) {}
record EncodedFormComponent(String text) {}

static EncodedFormComponent encodeForm(PlainFormValue plain) {
    return new EncodedFormComponent(
            URLEncoder.encode(plain.text(), StandardCharsets.UTF_8)
    );
}
~~~

Đoạn này là mã **minh họa đặt trong class**, không phải file độc lập. Những kiểu wrapper mang nghĩa **trạng thái dữ liệu**, giúp tránh nhầm `String` đã được encode với `String` gốc. Nếu dùng wrapper, vẫn cần đặt chính sách ở điểm tiếp nhận dữ liệu bên ngoài, vì Java type system không tự xác thực rằng một chuỗi bất kỳ đã thực sự ở dạng form-encoded hợp lệ.

Một lựa chọn đơn giản hơn là tên biến và tên hàm có chủ ý: `rawValue`, `encodedComponent`, `decodedParameter` thay vì tất cả đều là `String value`.

## 10. Vì sao không thể “đoán” một chuỗi đã được mã hóa chưa?

Một số đoạn code cố né encode lặp bằng cách kiểm tra:

~~~java
// Không phải chiến lược an toàn:
// if (text.contains("%")) return text;
// return URLEncoder.encode(text, StandardCharsets.UTF_8);
~~~

Vấn đề là **dữ liệu gốc hợp lệ có thể chứa `%`**. Chuỗi `"50%"` là dữ liệu thường, cần mã hóa dấu `%` thành `%25`. Ngược lại, một chuỗi đã mã hóa có thể **không chứa `%`** nếu chỉ có chữ số/chữ cái. Tương tự, việc xuất hiện dấu `+` cũng không chứng minh nó là dấu cách đã mã hóa hay một dấu cộng literal bị nhập sai định dạng.

Không tồn tại phép kiểm tra chuỗi đơn giản nào suy ra chắc chắn “raw” hay “encoded” cho **mọi dữ liệu có thể có**, vì nhiều chuỗi hợp lệ ở cả hai cách hiểu.

**Hướng đúng:** quyết định theo **provenance (nguồn gốc)** và hợp đồng của API:

- Hàm nhận dữ liệu người dùng dạng plain → encode đúng một lần tại điểm tạo form/query.
- Hàm nhận encoded component → sử dụng nguyên dạng theo hợp đồng; không encode lại.
- Hàm nhận giá trị framework đã parse → dùng như plain value; không decode lại.
- Hàm nhận raw HTTP request → dùng parser có cấu hình charset và giới hạn rõ ràng, không tự decode lặp.

Nếu một hệ thống cũ lưu lẫn raw và encoded string, cần **migration có kiểm soát dựa trên metadata/nguồn dữ liệu**, không chữa bằng một vòng lặp encode/decode heuristics.

## 11. Mã hóa/giải mã lặp và vấn đề an toàn

Double decoding không chỉ làm sai văn bản; trong một pipeline thiếu thống nhất, nó còn khiến các bước **kiểm tra bảo mật** và **bước sử dụng dữ liệu** nhìn thấy những giá trị khác nhau.

Ví dụ một chuỗi đầu vào có dạng:

~~~text
%252F
~~~

Giải mã lần một cho `%2F` và giải mã lần hai cho `/`. Nếu một tầng lọc dựa trên giá trị sau lần đầu, nhưng một tầng phía sau lại decode thêm và coi `/` là dấu phân cách đường dẫn, quyết định kiểm tra có thể không còn áp dụng đúng cho dữ liệu thực sự được dùng.

Tương tự, `%2526` có thể thành `%26` rồi `&`: rủi ro xuất hiện khi một tầng đã phân tích thành phần nhưng tầng khác lại xử lý `&` được tạo ra như cú pháp tham số mới. Đây là lý do các tài liệu bảo mật như OWASP nhấn mạnh nguy cơ **double encoding** và **mismatched decoding/canonicalization** giữa các lớp hệ thống.

Các nguyên tắc phòng tránh:

1. Xác định rõ **định dạng đầu vào**: raw query, form body, path hay giá trị ứng dụng đã decode.
2. Sử dụng parser đáng tin cậy của HTTP library/framework; chỉ decode theo **số lần và thứ tự được hợp đồng quy định**.
3. **Phân tách cú pháp và giá trị dữ liệu đúng giai đoạn**, không decode toàn bộ URL một cách tùy ý.
4. Kiểm tra dữ liệu ở **biểu diễn chuẩn mà thành phần cuối cùng sẽ sử dụng**; tránh kiểm tra một dạng rồi âm thầm decode tiếp trước thao tác nhạy cảm.
5. Không triển khai “decode cho tới khi không còn `%`” như cách chuẩn hóa chung.
6. Nếu nhiều proxy, gateway, router hoặc middleware cùng tham gia, xác nhận rõ **tầng nào decode**, tài liệu hóa và kiểm thử những chuỗi chứa `%`, `+`, `%2F`, `%26`.
7. Với đường dẫn tệp hoặc tài nguyên, không coi `URLDecoder` là công cụ kiểm soát traversal; chuẩn hóa và xác thực path theo API đường dẫn phù hợp của hệ điều hành/framework, sau khi xác định đúng biểu diễn đầu vào.

**Lưu ý:** “giải mã đúng một lần” ở đây là quy ước cho **một lớp form encoding duy nhất**. Một giao thức thực sự có nhiều lớp mã hóa độc lập (ví dụ một form chứa nội dung mã hóa theo định dạng khác) có thể cần nhiều bước biến đổi, nhưng mỗi bước phải tương ứng với **một lớp định dạng được định nghĩa rõ**, chứ không phải tự động gọi lại `URLDecoder` cùng một ý nghĩa.

## 12. Charset và cách xử lý input sai định dạng

Cặp Java 10 nên dùng:

~~~java
String encoded = URLEncoder.encode(raw, StandardCharsets.UTF_8);
String decoded = URLDecoder.decode(encoded, StandardCharsets.UTF_8);
~~~

Chọn UTF-8 ở cả hai phía, trừ khi giao thức nêu rõ charset khác. Không dùng overload `URLEncoder.encode(String)` hoặc `URLDecoder.decode(String)` không có charset: chúng đã **deprecated** vì phụ thuộc charset mặc định và không phù hợp cho giao thức cần kết quả nhất quán.

Đừng nhầm `URLDecoder` với bộ xác thực hoàn chỉnh:

- Với chuỗi percent-escape sai như `bad%2` hoặc `%GG`, implementation có thể ném `IllegalArgumentException`; trên các JDK hiện hành, API công bố hành vi ném cho input không hợp lệ.
- Đối với những byte escape tạo thành dãy ký tự sai ở charset được chọn, hành vi thay thế ký tự hoặc báo lỗi có thể phụ thuộc bộ giải mã và hợp đồng liên quan. Không coi “decode không ném ngoại lệ” là bằng chứng input hợp lệ về mặt nghiệp vụ hay bảo mật.
- `encode` hoặc `decode` nhận chuỗi hay charset là `null` sẽ ném `NullPointerException`.
- Percent-encoding chỉ biến đổi hình thức truyền dữ liệu; nó **không phải mã hóa bảo mật**, không cung cấp bí mật, chữ ký hay xác thực.

Nếu có yêu cầu từ chối dãy byte UTF-8 sai, hãy xem xét **bộ giải mã CharsetDecoder cấu hình báo lỗi**, hoặc parser/giao thức có chế độ xác thực nghiêm ngặt, thay vì chỉ dựa vào `URLDecoder` để thực hiện tất cả các phép kiểm tra.

## 13. Kiểm thử theo ranh giới, không chỉ theo kết quả cuối

Một bộ kiểm thử cho form encoding nên phân biệt **đầu vào raw** và **đầu vào đã encoded**. Những trường hợp đặc biệt sau có giá trị cao:

| Giá trị raw | Dạng sau encode một lần | Sau decode một lần |
| --- | --- | --- |
| `"hello world"` | `hello+world` | `"hello world"` |
| `"A+B"` | `A%2BB` | `"A+B"` |
| `"50%"` | `50%25` | `"50%"` |
| `"%2B"` | `%252B` | `"%2B"` |
| `"a&b"` | `a%26b` | `"a&b"` |
| `"x=y"` | `x%3Dy` | `"x=y"` |
| `"cà phê"` | `c%C3%A0+ph%C3%AA` | `"cà phê"` |
| `""` | `""` | `""` |

Bài kiểm thử hợp đồng nên chứng minh:

- `decode(encode(raw))` trả lại `raw` cho bộ dữ liệu Unicode hợp lệ được định nghĩa, với cùng charset.
- Hàm **xây query** chỉ encode từng name/value một lần.
- Hàm **nhận tham số đã parse** không tự decode.
- Giá trị literal `+` và `%2B` được giữ nguyên ý nghĩa.
- Parser không nhầm `%26` hoặc `%3D` với separator.
- Các trường hợp percent-escape thiếu chữ số hoặc sai hex được xử lý theo hợp đồng API/framework.
- Qua proxy/gateway/router, dữ liệu không bị decode thêm ở tầng khác trước khi validate hoặc dùng làm đường dẫn, khóa tài nguyên, tên file.

Với dữ liệu form chứa Unicode, kiểm tra cả các ký tự ngoài ASCII, ký tự kết hợp và những ký tự nằm ngoài BMP khi cần. Không suy ra an toàn của mọi input chỉ từ kiểm thử chữ cái ASCII.

## 14. Các lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Encode cùng một giá trị ở cả service và HTTP client | Dấu `%` chuyển thành `%25`, tham số đến nơi vẫn encoded | Chỉ một tầng chịu trách nhiệm encode |
| Decode giá trị lấy từ form parser thêm lần nữa | `+` thật thành dấu cách; `%2B` literal đổi nghĩa | Dùng trực tiếp giá trị đã parse |
| Lặp `URLDecoder.decode` đến khi không còn `%` | Biến đổi dữ liệu literal, nguy cơ lệch validation | Decode đúng lớp form encoding |
| Decode nguyên query rồi mới chia `&` | `%26` trong dữ liệu biến thành separator | Parse cấu trúc trước rồi decode từng component |
| Encode nguyên URL bằng `URLEncoder` | Làm hỏng `https://`, dấu `?`, `&`, `=` | Encode riêng query parameter; dùng URI builder khi phù hợp |
| Dùng `URLDecoder` để decode path | Quy ước dấu `+` và phân cách path khác form | Dùng xử lý URI path của framework/URI API |
| Đoán “đã encode” chỉ bằng kiểm tra `%` | Raw hợp lệ có thể chứa `%`, encoded có thể không chứa `%` | Theo dõi trạng thái dữ liệu qua API/type |
| Dùng charset mặc định | Dữ liệu Unicode có thể thay đổi giữa môi trường | Chọn `StandardCharsets.UTF_8` |
| Coi form encoding là cơ chế an toàn dữ liệu | Không có bí mật hoặc xác thực; dữ liệu có thể bị giải mã bởi bất cứ ai | Sử dụng TLS, validation và kiểm soát truy cập phù hợp |
| Dựa vào `URLDecoder` để loại mọi dữ liệu độc hại | Giải mã không thay cho validation của nghiệp vụ | Validate sau khi biểu diễn chuẩn đã rõ |
| Gửi chuỗi encode sẵn cho một API tự encode | Double encoding | Kiểm tra contract của HTTP client/framework |

## 15. Tự kiểm tra

### Bài 1 — mã hóa trùng

~~~java
String a = URLEncoder.encode("A+B", StandardCharsets.UTF_8);
String b = URLEncoder.encode(a, StandardCharsets.UTF_8);

// a = ?
// b = ?
// URLDecoder.decode(b, StandardCharsets.UTF_8) = ?
~~~

**Đáp án:** `a = "A%2BB"`; `b = "A%252BB"`; decode `b` một lần trả `"A%2BB"`, **không** phải dữ liệu gốc.

### Bài 2 — giải mã trùng

~~~java
String originalText = "%2F";
String sent = URLEncoder.encode(originalText, StandardCharsets.UTF_8);
String parsed = URLDecoder.decode(sent, StandardCharsets.UTF_8);

// sent = ?
// parsed = ?
// Điều gì xảy ra nếu decode(parsed) thêm một lần?
~~~

**Đáp án:** `sent = "%252F"`; `parsed = "%2F"` — đúng dữ liệu gốc. Decode thêm lần nữa sẽ tạo `"/"`, làm thay đổi ý nghĩa dữ liệu.

### Bài 3 — framework đã parse

Một HTTP framework nhận query `q=A%2BB` và trả về `request.getParameter("q") == "A+B"`. Code ứng dụng có nên gọi `URLDecoder.decode` thêm không?

**Đáp án:** **Không**, nếu hợp đồng của framework đã trả giá trị form-decoded. Gọi lại sẽ biến `"A+B"` thành `"A B"`.

### Bài 4 — ký tự phân cách

Người dùng tìm `a&b`. Một query hợp lệ cho tên tham số `q` sẽ là:

~~~text
q=a%26b
~~~

**Đáp án:** Parser phải nhận một tham số `q` với giá trị `"a&b"`. Nếu decode nguyên query trước rồi chia theo dấu `&`, có thể nhầm nội dung thành hai phần.

### Bài 5 — đánh giá kiến trúc

Một service nhận chuỗi **đã form-encoded** từ client library và lưu nguyên chuỗi đó vào cơ sở dữ liệu như tên hiển thị. Khi hiển thị lại, service gọi `URLDecoder` mỗi lần. Có vấn đề gì?

**Đáp án:** Cần xác định rõ service muốn lưu **dữ liệu gốc** hay **biểu diễn truyền tải**. Nếu trường là tên hiển thị, thông thường nên lưu giá trị gốc sau khi parser giải mã đúng một lần. Tránh lưu một chuỗi encoded rồi decode tùy ý ở nhiều đầu ra; trạng thái dữ liệu khó kiểm soát và dễ gây nhầm khi tên hợp lệ có `%` hoặc `+`.

## 16. Ghi nhớ và tài liệu chính thức

- `URLEncoder.encode(String, Charset)` và `URLDecoder.decode(String, Charset)` có từ **Java 10**, vẫn được hỗ trợ hiện nay.
- Định dạng là **`application/x-www-form-urlencoded`**: dấu cách thành `+`; dấu cộng thật thành `%2B`; dấu `%` thành `%25`.
- **Encode một lần** khi biến dữ liệu gốc thành tên/giá trị form được truyền đi. **Decode một lần** ở tầng parser của cùng lớp form encoding. Không mã hóa/giải mã lặp do suy đoán.
- **`encode(encode(x))` và `decode(decode(x))` không idempotent** nói chung; chỉ một phép decode thêm cũng có thể làm sai giá trị hợp lệ.
- Không decode lại giá trị mà framework đã trả về ở dạng plain text; không encode lại tham số mà HTTP library đã mã hóa.
- Không dùng `URLEncoder` để encode cả URL, và không dùng `URLDecoder` như decoder chung cho URI path.
- Khi kiểm tra dữ liệu nhạy cảm, các tầng phải thống nhất **biểu diễn chuẩn** và không có bước decode bất ngờ sau validation.
- Tránh overload không charset đã deprecated; dùng `StandardCharsets.UTF_8` khi định dạng yêu cầu UTF-8.

Tài liệu tham khảo hiện hành:

- [Java SE 17 — `URLEncoder`, quy tắc `application/x-www-form-urlencoded`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html)
- [Java SE 17 — `URLDecoder`, dấu `+`, percent-decoding và ngoại lệ](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLDecoder.html)
- [Java SE 17 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [OWASP — Double Encoding](https://owasp.org/www-community/Double_Encoding)

**Kết luận:** Lỗi mã hóa/giải mã lặp xuất phát từ **không phân biệt dữ liệu gốc với dữ liệu đã mã hóa và không xác định tầng nào chịu trách nhiệm biến đổi**. Hãy dùng `URLEncoder`/`URLDecoder` đúng phạm vi form, chọn UTF-8 rõ ràng, xử lý đúng một lớp encoding tại một ranh giới và kiểm thử kỹ `+`, `%`, `&`, `=` cùng các dấu phân cách có thể bị thay đổi qua nhiều lần decode.
