# `URLEncoder.encode(String, Charset)` — mã hóa dữ liệu biểu mẫu trong Java 10+

## 1. Vấn đề: dữ liệu biểu mẫu không phải là URL nguyên vẹn

Khi gửi dữ liệu theo định dạng **`application/x-www-form-urlencoded`**, các tên trường và giá trị trường phải được biểu diễn sao cho dấu cách, ký tự có dấu, dấu cộng, dấu `&`, dấu `=` và các ký tự đặc biệt khác **không bị nhầm thành cú pháp phân tách**.

Từ **Java 10**, Java cung cấp overload nhận trực tiếp `Charset`:

```java
String encoded = URLEncoder.encode(
        "Cà phê & trà",
        StandardCharsets.UTF_8);

// encoded: C%C3%A0+ph%C3%AA+%26+tr%C3%A0
```

Đây là mã minh họa đặt trong phương thức, cần import `java.net.URLEncoder` và `java.nio.charset.StandardCharsets`.

**Ý nghĩa:**

- Khoảng trắng được biểu diễn bằng `+` theo quy tắc **form encoding**.
- Dấu `&` **là dữ liệu** trong giá trị, nên được chuyển thành `%26`.
- Ký tự `à` và `ê` trở thành chuỗi escape dựa trên **các byte UTF-8**, không phải dựa trên một “mã Unicode” thập phân tùy ý.
- Kết quả là một **chuỗi đã mã hóa dùng cho một trường form**, không phải một địa chỉ URL hoàn chỉnh.

Tên chính thức của lớp là `java.net.URLEncoder`, nhưng theo Javadoc, lớp này dành cho **HTML form encoding**, không phải bộ mã hóa URI chung cho mọi vị trí trong một URL. Phân biệt này rất quan trọng để tránh lỗi dữ liệu.

## 2. Chữ ký và thời điểm xuất hiện

Chữ ký của overload cần học:

```java
public static String encode(String s, Charset charset)
```

Đây là **chữ ký API**, không phải đoạn mã ứng dụng cần tự cài đặt. Javadoc đánh dấu overload này **Since: 10**. Nó hiện vẫn có trong Java SE mới.

Tham số:

- `s`: chuỗi **chưa mã hóa** cần chuyển sang dạng `application/x-www-form-urlencoded`.
- `charset`: charset dùng để đổi những ký tự cần escape thành **byte**; mỗi byte sau đó biểu diễn bằng `%HH`.
- Giá trị trả về: một `String` biểu diễn phần dữ liệu đã được form-encode.

Ví dụ:

```java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String item = URLEncoder.encode(
        "A+B & C", StandardCharsets.UTF_8);
// A%2BB+%26+C
```

Trong ví dụ này, `+` ban đầu là một **ký tự dữ liệu** và phải được escape thành `%2B`; dấu cách giữa `B` và `&` trở thành `+` mới. Vì vậy không thể chỉ thay tất cả dấu cách thành `+` mà bỏ qua các ký tự đặc biệt khác.

### Vì sao truyền `Charset` thay cho tên String?

So sánh:

```java
String a = URLEncoder.encode(text, StandardCharsets.UTF_8);
String b = URLEncoder.encode(text, "UTF-8");
```

`text` là một biến String minh họa đã có.

- `a` dùng object `Charset` có sẵn, dễ đọc, được hỗ trợ đầy đủ từ Java 10 và **không cần xử lý `UnsupportedEncodingException` chỉ vì truyền một tên**.
- `b` là overload có từ Java trước đó; nó phải tra tên encoding và có thể ném checked `UnsupportedEncodingException` khi tên không được hỗ trợ.
- Khi biết chắc dữ liệu dùng UTF-8, cách viết với `StandardCharsets.UTF_8` thể hiện hợp đồng rõ ràng hơn.

**Không chọn overload `URLEncoder.encode(String)` không tham số charset.** API này đã được đánh dấu deprecated vì kết quả phụ thuộc charset mặc định và không diễn đạt được encoding của dữ liệu. Đây là điểm cần tránh trong Java hiện hành, không phải một cú pháp nên tiếp tục học để dùng mới.

## 3. Các quy tắc mã hóa chính xác

Javadoc của `URLEncoder` mô tả cách chuyển đổi:

| Dữ liệu đầu vào | Kết quả form-encode | Lý do |
| --- | --- | --- |
| Chữ cái ASCII `A–Z`, `a–z`, chữ số `0–9` | Giữ nguyên | Nhóm ký tự an toàn |
| `.`, `-`, `*`, `_` | Giữ nguyên | Bốn ký tự đặc biệt không escape của form encoding |
| Một khoảng trắng ` ` | `+` | Quy tắc biểu diễn khoảng trắng của form |
| Dấu cộng thật `+` | `%2B` | Tránh bị bộ giải mã hiểu là khoảng trắng |
| Phần trăm `%` | `%25` | Tránh bị hiểu là tiền tố một escape đã có |
| Dấu và `&` | `%26` | Không nhầm với dấu phân cách các cặp key/value |
| Dấu bằng `=` | `%3D` | Không nhầm với dấu phân cách key và value |
| Dấu gạch chéo `/` | `%2F` | Dữ liệu cần escape trong form |
| Dấu hỏi `?` | `%3F` | Dữ liệu cần escape trong form |
| Dấu ngã `~` | `%7E` | Không nằm trong tập bốn ký tự đặc biệt được giữ nguyên theo Javadoc form encoding |
| Ký tự ngoài ASCII | `%HH` cho từng byte của charset | Ví dụ `à` ở UTF-8 thành `%C3%A0` |

Các kết quả trên là cách biểu diễn theo `URLEncoder.encode(s, StandardCharsets.UTF_8)`. **Không suy luận rằng cùng tập ký tự escape này áp dụng y nguyên cho URI path, fragment hoặc mọi tiêu chuẩn URL.**

Ví dụ cụ thể:

```java
URLEncoder.encode("a b", StandardCharsets.UTF_8);   // a+b
URLEncoder.encode("a+b", StandardCharsets.UTF_8);   // a%2Bb
URLEncoder.encode("50%", StandardCharsets.UTF_8);   // 50%25
URLEncoder.encode("a&b=c", StandardCharsets.UTF_8); // a%26b%3Dc
URLEncoder.encode("Az09-._*", StandardCharsets.UTF_8); // Az09-._*
```

Một lỗi rất thường gặp là **đánh đồng dấu `+` của output với dấu cộng nguyên bản**. Cần nhìn từ góc độ **giải mã**: output `a+b` biểu diễn chuỗi `a b`, còn output `a%2Bb` biểu diễn chuỗi `a+b`.

## 4. UTF-8: một ký tự có thể tương ứng nhiều byte `%HH`

Unicode mô tả ký tự; charset UTF-8 mô tả cách biểu diễn ký tự thành byte. Ví dụ:

- `à` có code point `U+00E0`, được mã hóa UTF-8 thành hai byte `C3 A0`, nên chuỗi form-encoded là `%C3%A0`.
- `ê` có code point `U+00EA`, byte UTF-8 là `C3 AA`, nên kết quả `%C3%AA`.
- Một ký tự ngoài vùng BMP có thể cần nhiều byte UTF-8; `URLEncoder` biểu diễn **từng byte** bằng dạng `%HH` chứ không chép nguyên ký tự vào output.

Mã minh họa:

```java
String text = "Cà phê & trà";

String encoded = URLEncoder.encode(
        text, StandardCharsets.UTF_8);

System.out.println(encoded);
// C%C3%A0+ph%C3%AA+%26+tr%C3%A0
```

Mỗi byte sau dấu `%` được viết dạng hai ký tự hexadecimal. Ký tự khoảng trắng ` ` khác: nó được biểu diễn bằng `+` trực tiếp theo quy tắc form. Dấu `&` trở thành `%26`; nếu không làm vậy, nó có thể bị bộ phân tích form hiểu thành bắt đầu **cặp tham số mới**.

**Tránh dùng charset không khớp ở hai phía.** Ví dụ `Café` được mã hóa theo ISO-8859-1 thành `Caf%E9`, còn UTF-8 thành `Caf%C3%A9`. Nếu client encode theo ISO-8859-1 nhưng server decode theo UTF-8, kết quả có thể bị sai; đây là lỗi thỏa thuận về encoding chứ không thể chữa bằng cách sửa dấu cộng.

## 5. Mã hóa cả tên trường lẫn giá trị, rồi mới nối cú pháp biểu mẫu

Giả sử muốn tạo dữ liệu gồm hai trường:

- Tên trường `name` có giá trị `"An Đức"`.
- Tên trường `note` có giá trị `"A+B & C"`.

Cách đúng là **mã hóa từng name và từng value**, sau đó nối bằng dấu `=` và `&` do chính ứng dụng tạo:

```java
String body = "name="
        + URLEncoder.encode("An Đức", StandardCharsets.UTF_8)
        + "&note="
        + URLEncoder.encode("A+B & C", StandardCharsets.UTF_8);
```

Khi tên trường động:

```java
static String pair(String name, String value) {
    return URLEncoder.encode(name, StandardCharsets.UTF_8)
            + "="
            + URLEncoder.encode(value, StandardCharsets.UTF_8);
}
```

Đây là **phương thức minh họa** trong lớp, cần import `URLEncoder`/`StandardCharsets`.

**Không viết:**

```java
String rawBody = "name=An Đức&note=A+B & C";
// SAI nếu muốn giữ các dấu = và & làm cú pháp:
String wrong = URLEncoder.encode(
        rawBody, StandardCharsets.UTF_8);
```

Cách sai escape **toàn bộ** dấu `=` và `&`, khiến chuỗi kết quả không còn cấu trúc gồm hai cặp trường như dự định. Các dấu phân cách **thuộc cú pháp** phải do mã lập trình nối vào *sau khi* các thành phần dữ liệu đã được encode.

Nếu một giá trị chứa `&` hoặc `=`, chúng được escape **bên trong giá trị**, không phải được phép tạo thêm trường. Đây chính là lý do quan trọng để mã hóa các thành phần riêng biệt.

## 6. Định dạng khi đưa vào query string

`application/x-www-form-urlencoded` cũng thường được dùng để biểu diễn **tên và giá trị tham số truy vấn**, tùy hợp đồng của server/framework:

```java
String query = "q="
        + URLEncoder.encode("a+b & c", StandardCharsets.UTF_8)
        + "&page="
        + URLEncoder.encode("2", StandardCharsets.UTF_8);

System.out.println(query);
// q=a%2Bb+%26+c&page=2
```

Đoạn trên là mã minh họa trong phương thức. Mỗi giá trị được mã hóa riêng; các dấu `&` và `=` tạo cấu trúc **không bị mã hóa**.

Khi ghép đường dẫn:

```java
String url = "https://example.com/search?" + query;
```

Cách nối này minh họa khi **base URL cố định đã hợp lệ** và tham số đều đã form-encode đúng. Trong ứng dụng thực tế, nếu URL đã có query/fragment hay các thành phần động, nên dùng công cụ xây dựng URI/HTTP client thích hợp và phải biết công cụ đó có tự mã hóa thành phần hay không, tránh mã hóa hai lần.

**Không dùng `URLEncoder` cho cả chuỗi URL**:

```java
// SAI: escape luôn dấu : / ? & = tạo cấu trúc URL
URLEncoder.encode(
        "https://example.com/search?q=a b",
        StandardCharsets.UTF_8);
```

Kết quả của lời gọi sai là **một chuỗi form-encoded** biểu diễn cả URL như *một giá trị dữ liệu*, chứ không còn là URL có scheme, host, path và query như ý định ban đầu.

## 7. Form encoding khác với percent-encoding tổng quát của URI

Theo cú pháp URI của RFC 3986, vị trí của một ký tự quyết định nó có cần escape hay không. Một ký tự có thể là **dấu phân cách URI** trong thành phần này nhưng là **dữ liệu** ở thành phần khác.

Đặc biệt:

- Form encoding dùng `+` để biểu diễn **khoảng trắng**.
- Percent-encoding URI thông thường biểu diễn khoảng trắng bằng `%20`.
- Dấu `+` **không tự động có nghĩa là khoảng trắng ở mọi loại URI component**; việc chuyển `+` → khoảng trắng thuộc quy tắc form decoding.
- `URLEncoder` escape `/` thành `%2F`. Điều đó **không phù hợp** nếu bạn muốn giữ dấu `/` làm delimiter giữa các path segment.
- `URLEncoder` có thể escape cả `~`, dù `~` nằm trong tập unreserved của RFC 3986.

Ví dụ phân biệt bằng constructor của `URI`:

```java
URI uri = new URI(
        "https",
        "example.com",
        "/a b",
        "q=a b",
        null);

System.out.println(uri.toASCIIString());
// https://example.com/a%20b?q=a%20b
```

Đoạn cần import `java.net.URI` và phải khai báo hoặc xử lý `URISyntaxException`. Với input đã cho, constructor xây **các thành phần URI** và ký tự khoảng trắng được percent-encode thành `%20`, không phải `+`.

**Cẩn trọng:** constructor `URI` không tự hiểu các cặp form key/value của ứng dụng và không thay cho việc encode dữ liệu biểu mẫu. Ngược lại, nếu đưa một giá trị **đã chứa `%HH`** vào constructor coi là thành phần raw chưa mã hóa, dấu `%` có thể bị escape tiếp thành `%25`. Hãy quyết định ở mỗi tầng dữ liệu đang là **raw** hay **encoded**.

Quy tắc an toàn là **xác định ngữ cảnh trước khi mã hóa**: form value, query field theo hợp đồng form, path segment, path đầy đủ, fragment, hoặc một URI hoàn chỉnh.

## 8. Giải mã trở lại bằng `URLDecoder.decode(String, Charset)`

Java 10 cũng có overload giải mã theo `Charset`:

```java
String raw = URLDecoder.decode(
        "C%C3%A0+ph%C3%AA+%26+tr%C3%A0",
        StandardCharsets.UTF_8);

System.out.println(raw);
// Cà phê & trà
```

Cần import `java.net.URLDecoder` và `java.nio.charset.StandardCharsets`. Đây là đoạn minh họa trong phương thức.

Javadoc của `URLDecoder` quy định:

- `+` trong chuỗi **form-encoded** trở thành khoảng trắng.
- `%HH` được chuyển thành byte; các byte escape liên tiếp được giải mã theo charset chỉ định.
- Những ký tự an toàn không escape được giữ nguyên.
- Escape không hợp lệ như `%GG` có thể gây `IllegalArgumentException`.
- `s` hoặc `charset` bằng `null` gây `NullPointerException`.

Ví dụ bắt buộc phân biệt:

```java
URLDecoder.decode("a+b", StandardCharsets.UTF_8);   // "a b"
URLDecoder.decode("a%2Bb", StandardCharsets.UTF_8); // "a+b"
```

**Không dùng `URLDecoder` tùy tiện cho một đường dẫn URI không mang ngữ nghĩa form.** Nếu path thực sự chứa dấu `+`, giải mã path bằng form decoder có thể biến nó thành khoảng trắng, làm sai nội dung. Nếu cần xử lý URI, hãy phân tách URI thành các component thích hợp rồi dùng công cụ giải mã đúng cho từng component.

## 9. Round-trip chỉ đúng khi hai phía thống nhất charset và định dạng

Một phép kiểm tra hữu ích là:

```java
String original = "Cà phê & trà";
String encoded = URLEncoder.encode(
        original, StandardCharsets.UTF_8);
String decoded = URLDecoder.decode(
        encoded, StandardCharsets.UTF_8);

boolean same = original.equals(decoded); // true
```

Khi đầu vào là một Java String hợp lệ, charset có thể biểu diễn mọi ký tự cần thiết, và cả hai phía dùng cùng quy tắc form encoding/decoding, phép round-trip khôi phục nội dung.

**Đừng biến phát biểu này thành “mọi chuỗi luôn giữ nguyên”**:

- Một charset hạn chế như US-ASCII hoặc ISO-8859-1 không biểu diễn được mọi ký tự Unicode.
- Javadoc `URLEncoder.encode(String,Charset)` ghi rõ: nếu đầu vào malformed hoặc không ánh xạ được thành chuỗi byte hợp lệ theo charset, dữ liệu lỗi được thay bằng replacement của charset.
- `URLDecoder` cũng có thể thay thế dữ liệu byte lỗi theo charset.
- Unicode có những cách biểu diễn khác nhau nhưng tương đương về mặt thị giác/chuẩn hóa, ví dụ ký tự dựng sẵn và tổ hợp dấu; `URLEncoder` không tự chuẩn hóa chúng thành một dạng duy nhất.

Nếu cần **kiểm tra encoding nghiêm ngặt, không chấp nhận thay thế âm thầm**, nên dùng `CharsetEncoder`/`CharsetDecoder` với `CodingErrorAction.REPORT` hoặc validation phù hợp trước/sau bước mã hóa. `URLEncoder` thuận tiện cho form encoding, nhưng không phải một trình kiểm tra Unicode nghiêm ngặt dành cho dữ liệu có yêu cầu chuẩn hóa hoặc chữ ký số.

## 10. Vì sao mã hóa lặp lại sẽ sai?

Giả sử dữ liệu gốc là `"a b"`:

```java
String once = URLEncoder.encode(
        "a b", StandardCharsets.UTF_8);       // a+b

String twice = URLEncoder.encode(
        once, StandardCharsets.UTF_8);        // a%2Bb
```

Ở lần thứ hai, `URLEncoder` nhìn `+` là **dấu cộng dữ liệu trong chuỗi đầu vào mới**, không biết nó từng đại diện cho dấu cách, nên escape nó thành `%2B`.

Khi giải mã **một lần**:

```java
URLDecoder.decode("a%2Bb", StandardCharsets.UTF_8); // a+b
```

Kết quả **không còn là** `"a b"`. Nếu server giải mã thêm lần nữa thì có thể thành `"a b"`, nhưng việc phụ thuộc nhiều bước giải mã như vậy vừa không ổn định vừa tiềm ẩn sai lệch phân tích dữ liệu.

Với chuỗi gốc đã chứa `%20`:

```java
URLEncoder.encode("%20", StandardCharsets.UTF_8);
// %2520
```

`%` bị escape thành `%25`. Đó là hành vi đúng cho **dữ liệu raw mang ký tự phần trăm**, nhưng sai khi mã nguồn vô tình coi chuỗi đã encode là raw lần nữa.

**Nguyên tắc:** với mỗi ranh giới dữ liệu, hãy phân biệt raw và encoded, encode **đúng một lần** trước khi gửi và decode **đúng một lần** tại tầng phân tích form tương ứng. Không nối escape thủ công xen kẽ rồi gọi thêm encoder.

## 11. Null, cấu hình charset và ngoại lệ

`URLEncoder.encode(String, Charset)` có hợp đồng rõ:

```java
// Các lời gọi dưới đây sẽ ném NullPointerException khi chạy:
URLEncoder.encode(null, StandardCharsets.UTF_8);
URLEncoder.encode("x", (Charset) null);
```

Cần import `java.nio.charset.Charset` và `StandardCharsets`, `java.net.URLEncoder`. Nếu một trường có giá trị nullable, quyết định chính sách trước khi mã hóa:

- **Bắt buộc có giá trị:** kiểm tra bằng `Objects.requireNonNull(value, "fieldName")` hoặc validator nghiệp vụ.
- **Không có thì bỏ tham số:** đừng tạo cặp key/value đó.
- **Không có thì dùng chuỗi rỗng:** dùng `""` nhưng chỉ khi hợp đồng **thực sự** định nghĩa null tương đương giá trị rỗng.

Không tự dùng `String.valueOf(null)` để sinh chuỗi `"null"` trừ khi đó đúng là dữ liệu bạn muốn gửi.

Một số lỗi ở khâu giải mã:

```java
// URLDecoder.decode("%GG", StandardCharsets.UTF_8);
// IllegalArgumentException do escape không hợp lệ
```

Khác với overload `encode(String,String)` dựa trên tên charset, overload nhận `Charset` **không có checked `UnsupportedEncodingException` chỉ vì cấu hình tên**. Với charset đến từ người dùng, `Charset.forName(name)` có thể ném exception cấu hình trước khi gọi encoder; hãy validate danh sách charset cho phép.

## 12. Ví dụ Java 17+ chạy được và có output xác định

Tạo tệp `FormEncodingDemo.java`:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public class FormEncodingDemo {

    static final Charset UTF8 = StandardCharsets.UTF_8;

    static String form(String s) {
        return URLEncoder.encode(s, UTF8);
    }

    static void check(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + "=none");
        } catch (NullPointerException | IllegalArgumentException ex) {
            System.out.println(name + "="
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        // "Cà phê & trà", viết Unicode escape để kiểm thử độc lập console.
        String vietnamese = "C\u00E0 ph\u00EA & tr\u00E0";
        String encoded = form(vietnamese);

        System.out.println("utf8=" + encoded);
        System.out.println("roundTrip="
                + vietnamese.equals(
                        URLDecoder.decode(encoded, UTF8)));

        System.out.println("safe=" + form("Az09-._*"));
        System.out.println("space=" + form("a b"));
        System.out.println("plus=" + form("a+b"));
        System.out.println("percent=" + form("50%"));
        System.out.println("delimiters=" + form("a&b=c"));

        System.out.println("query=q="
                + form("a+b & c")
                + "&page=" + form("2"));

        System.out.println("decodePlus="
                + URLDecoder.decode("a+b", UTF8));
        System.out.println("decodeLiteralPlus="
                + URLDecoder.decode("a%2Bb", UTF8));

        String once = form("a b");
        System.out.println("double=" + form(once));

        String latin1 = URLEncoder.encode(
                "Caf\u00E9", StandardCharsets.ISO_8859_1);
        System.out.println("latin1=" + latin1);
        System.out.println("latin1RoundTrip="
                + "Caf\u00E9".equals(URLDecoder.decode(
                        latin1, StandardCharsets.ISO_8859_1)));
        System.out.println("wrongCharsetSame="
                + "Caf\u00E9".equals(
                        URLDecoder.decode(latin1, UTF8)));

        System.out.println("uri="
                + new URI("https", "example.com",
                        "/a b", "q=a b", null).toASCIIString());

        check("nullText", () -> URLEncoder.encode(
                (String) null, UTF8));
        check("nullCharset", () -> URLEncoder.encode(
                "x", (Charset) null));
        check("badEscape", () -> URLDecoder.decode(
                "%GG", UTF8));
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac FormEncodingDemo.java
java FormEncodingDemo
```

Kết quả:

```text
utf8=C%C3%A0+ph%C3%AA+%26+tr%C3%A0
roundTrip=true
safe=Az09-._*
space=a+b
plus=a%2Bb
percent=50%25
delimiters=a%26b%3Dc
query=q=a%2Bb+%26+c&page=2
decodePlus=a b
decodeLiteralPlus=a+b
double=a%2Bb
latin1=Caf%E9
latin1RoundTrip=true
wrongCharsetSame=false
uri=https://example.com/a%20b?q=a%20b
nullText=NullPointerException
nullCharset=NullPointerException
badEscape=IllegalArgumentException
```

**Giải thích các kết quả quan trọng:**

1. `utf8=...` ghi rõ UTF-8 percent bytes cho `à`, `ê`, `&` và khoảng trắng.
2. `roundTrip=true`: encode/decode cùng UTF-8 khôi phục chuỗi gốc.
3. `safe=Az09-._*`: các ký tự an toàn của form giữ nguyên.
4. `space=a+b` và `plus=a%2Bb`: dấu cách và dấu cộng là **hai ý nghĩa khác nhau**.
5. `percent=50%25`, `delimiters=a%26b%3Dc`: escape các ký tự có thể gây nhầm cú pháp.
6. `query=...&page=2`: giá trị được encode riêng, dấu phân cách giữa các cặp vẫn là cú pháp.
7. `decodePlus=a b` so với `decodeLiteralPlus=a+b`: giải mã form phân biệt `+` và `%2B`.
8. `double=a%2Bb`: một chuỗi đã form-encode không nên đưa lại vào encoder như raw.
9. `latin1=...` và `wrongCharsetSame=false`: charset mã hóa/giải mã phải khớp; UTF-8 không tự đọc đúng byte ISO-8859-1.
10. `uri=...%20...`: URI component encoding có thể dùng `%20` cho khoảng trắng thay vì `+` của form.
11. Ba dòng lỗi minh họa tham số null và escape không hợp lệ; helper `check` ghi lại **tên lớp exception**, không phụ thuộc message của JDK.

Chương trình chỉ thao tác với String trong bộ nhớ: không gửi network request, không tạo file phụ và không dựa trên bảng mã hiển thị tiếng Việt của console. Kết quả có thể được kiểm tra bằng stdout ASCII.

## 13. Kiểm thử nên bao phủ những gì?

Khi viết unit test cho logic xây form/query, hãy kiểm tra cả **giá trị encoded** và **ngữ nghĩa decode**:

### Trường hợp thông thường

```java
String a = URLEncoder.encode("hello world",
        StandardCharsets.UTF_8);
// assertEquals("hello+world", a)
```

### Dấu phân cách và dấu cộng

```java
String a = URLEncoder.encode("A+B & C",
        StandardCharsets.UTF_8);
// assertEquals("A%2BB+%26+C", a)
```

### Unicode đa byte

```java
String input = "C\u00E0 ph\u00EA";
String encoded = URLEncoder.encode(input,
        StandardCharsets.UTF_8);
// assertEquals("C%C3%A0+ph%C3%AA", encoded)
```

### Round-trip

```java
String restored = URLDecoder.decode(encoded,
        StandardCharsets.UTF_8);
// assertEquals(input, restored)
```

Đây là các đoạn minh họa; `assertEquals` là cách viết phổ biến trong JUnit Jupiter khi dự án đã cấu hình thư viện test.

Thêm các test:

- Chuỗi trống `""` → kết quả `""`; không giống null.
- Chuỗi chỉ ASCII không cần escape → không đổi.
- Dấu `%` gốc → `%25`; không vô tình “decode trước rồi encode lại”.
- Raw chứa `+` → `%2B`, decode trở lại dấu cộng.
- Dữ liệu có nhiều trường → dấu `&` và `=` giữa **các cặp** vẫn nguyên; trong giá trị phải được encode.
- `encode(null, UTF_8)`, `encode(value, null)` → `NullPointerException`.
- `decode("%GG", UTF_8)` → `IllegalArgumentException`.
- Chuỗi có ký tự ngoài ASCII → dùng chung charset encode/decode.
- Input có ký tự Unicode ở hai dạng chuẩn hóa khác nhau → nếu nghiệp vụ cần so sánh canonical, chuẩn hóa riêng trước khi encode.

Không viết test dựa vào charset mặc định của môi trường nếu giao thức dữ liệu đã định nghĩa rõ UTF-8.

## 14. Đưa dữ liệu vào HTTP POST `application/x-www-form-urlencoded`

Với Java HTTP Client hiện hành (từ Java 11), một request có thể dùng body đã được form-encode. Ví dụ:

```java
String body = "name="
        + URLEncoder.encode("An Đức", StandardCharsets.UTF_8)
        + "&note="
        + URLEncoder.encode("A+B & C", StandardCharsets.UTF_8);

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/form"))
        .header("Content-Type",
                "application/x-www-form-urlencoded; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                body, StandardCharsets.UTF_8))
        .build();
```

Đây là **đoạn minh họa tạo request**, không thực sự gửi đi. Cần import `java.net.URI`, `java.net.URLEncoder`, `java.nio.charset.StandardCharsets` và `java.net.http.HttpRequest`. `example.com` chỉ là địa chỉ ví dụ, không phải API thật được xác nhận.

Ở đây có hai lớp mã hóa:

1. `URLEncoder` tạo **cú pháp form** cho từng tên/giá trị, chứa các chuỗi ASCII như `%C3%A0` và `+`.
2. `BodyPublishers.ofString(..., UTF_8)` chuyển chuỗi body thành **byte gửi qua HTTP**; vì body đã là ASCII sau form encoding, nội dung các escape vẫn giữ nguyên.

Header `Content-Type` mô tả định dạng body; header không tự encode các field. Nếu dùng framework HTTP, hãy xem framework đã tự tạo/encode form fields hay chưa để không vô tình encode hai lần.

Với GET query, cách truyền dữ liệu còn phụ thuộc server có diễn giải query theo form semantics không. Đừng mặc định mọi hệ thống đọc `+` thành khoảng trắng trong mọi thành phần URI; phải theo hợp đồng endpoint.

## 15. Lỗi thường gặp khi dùng `URLEncoder.encode(String, Charset)`

| Hiểu nhầm / cách viết | Vấn đề | Cách đúng |
| --- | --- | --- |
| `URLEncoder.encode(fullUrl, UTF_8)` | Encode luôn `:`, `/`, `?` và dấu phân cách, mất cấu trúc URI | Encode **từng trường dữ liệu**, xây URI theo component |
| `URLEncoder.encode("a b", UTF_8)` mà kỳ vọng `a%20b` | Nhầm form encoding với URI percent encoding | Form dùng `a+b`; URI có quy tắc riêng |
| Đưa dữ liệu `a+b` nguyên bản vào form | Bộ giải mã form hiểu `+` là khoảng trắng | Encode dấu cộng thành `%2B` |
| Encode `"a=1&b=2"` như một khối | Dấu `=`, `&` trong **cú pháp** bị escape | Encode key/value trước rồi nối bằng `=` và `&` |
| Mã hóa hai lần `a b` | `a+b` trở thành `a%2Bb`, sai ý nghĩa nếu decode một lần | Theo dõi raw/encoded và encode một lần |
| Dùng `encode(String)` mặc định | Overload này deprecated, phụ thuộc charset mặc định | `encode(text, StandardCharsets.UTF_8)` |
| Encode UTF-8, decode ISO-8859-1 | Ký tự ngoài ASCII bị sai | Hai phía thống nhất charset |
| Decode toàn bộ path bằng `URLDecoder` | Có thể biến dấu `+` của path thành space | Dùng parser/decoder URI phù hợp component |
| Cho rằng encoder là HTML escaping | Có thể không bảo vệ khi dùng text trong HTML/JS | Áp dụng escaping/encoding riêng theo ngữ cảnh đầu ra |
| Cho rằng form encoding bảo vệ khỏi SQL injection | Không liên quan cơ chế query SQL | Dùng prepared statements/parameterized queries |
| Dùng `String.valueOf(null)` không suy nghĩ | Biến null thành chữ `"null"` | Chính sách omit/reject/default rõ |
| Kỳ vọng đầu vào Unicode lỗi sẽ luôn ném exception | Javadoc cho phép replacement khi không encode được | Kiểm tra/encode nghiêm ngặt bằng CharsetEncoder khi cần |
| Xem `URI` và `URLEncoder` là cùng một API | URI quản lý cấu trúc thành phần; form encoding quản lý field data | Chọn công cụ đúng ngữ cảnh |

## 16. Bài tập tự kiểm tra

### Câu 1: khoảng trắng và dấu cộng

```java
var a = URLEncoder.encode("x y", StandardCharsets.UTF_8);
var b = URLEncoder.encode("x+y", StandardCharsets.UTF_8);
```

Kết quả?

**Đáp án:** `a` là `x+y`; `b` là `x%2By`. Form decoder đảo `+` thành space và `%2B` thành dấu cộng dữ liệu.

### Câu 2: vì sao không encode cả query?

```java
URLEncoder.encode("q=java&lang=vi", StandardCharsets.UTF_8);
```

Có phù hợp nếu muốn hai tham số `q` và `lang`?

**Đáp án:** Không. `=` và `&` bị escape như dữ liệu, khiến cấu trúc không còn được phân tách thành hai cặp. Hãy encode riêng `q`, `java`, `lang`, `vi` rồi nối bằng delimiter.

### Câu 3: round-trip dữ liệu UTF-8

```java
String value = "C\u00E0 ph\u00EA";
String encoded = URLEncoder.encode(value, StandardCharsets.UTF_8);
String restored = URLDecoder.decode(encoded, StandardCharsets.UTF_8);
```

`restored.equals(value)` có đúng không?

**Đáp án:** Đúng cho chuỗi mẫu này. Cùng charset UTF-8 ở hai phía, chuỗi Unicode hợp lệ được khôi phục sau một lần encode và một lần decode.

### Câu 4: khi đầu vào là một URL hoàn chỉnh

```java
String url = "https://example.com/a b?q=x+y";
```

Có nên gọi `URLEncoder.encode(url, UTF_8)` để “sửa URL” không?

**Đáp án:** Không. Đây là chuỗi có nhiều thành phần URI. Cần xử lý scheme/host/path/query theo cấu trúc của chúng; dấu cộng trong query cần được hiểu theo hợp đồng của endpoint. Không áp đặt form encoder lên toàn URL.

### Câu 5: Unicode khó biểu diễn bằng charset khác

Dùng ISO-8859-1 để form-encode một ký tự tiếng Việt mà charset này không biểu diễn được. Có phải encoder luôn ném một ngoại lệ được kiểm tra không?

**Đáp án:** Không. Javadoc của `encode(String,Charset)` mô tả việc thay thế đầu vào malformed hoặc ký tự không mã hóa được bằng replacement values của charset. Nếu bắt buộc phát hiện lỗi dữ liệu, hãy kiểm tra charset/Unicode với cơ chế nghiêm ngặt riêng.

### Câu 6: tính đúng đắn của URL decode

```java
URLDecoder.decode("a+b", StandardCharsets.UTF_8);
URLDecoder.decode("a%2Bb", StandardCharsets.UTF_8);
```

Hai kết quả có giống nhau không?

**Đáp án:** Không. Kết quả lần lượt là `"a b"` và `"a+b"`. Bước decode phải phù hợp định dạng form, không áp dụng bừa cho mọi URI component.

## 17. Checklist áp dụng cho dữ liệu biểu mẫu

Trước khi gọi `URLEncoder.encode(String,Charset)`, hãy xác nhận:

1. **Đây là một tên/giá trị trường form hay một URI component khác?** Không encode cả URL.
2. **Đầu vào còn raw hay đã được encode?** Tránh double encoding.
3. **Charset của hai phía là gì?** Ưu tiên UTF-8 nếu giao thức/endpoint quy định như vậy.
4. **Có ký tự ngoài ASCII trong test không?** Nếu không, khó phát hiện lỗi charset.
5. **Giá trị có dấu cách, `+`, `%`, `&`, `=` không?** Kiểm thử đầy đủ các ký tự dễ gây nhầm.
6. **Tên field có động không?** Encode cả tên lẫn giá trị.
7. **Có giá trị null không?** Quyết định reject, omit hoặc default trước encode.
8. **Sau encode, ai nối các delimiter `&` và `=`?** Chỉ tầng xây form mới thêm delimiter.
9. **Framework/HTTP client đã tự encode trường chưa?** Không encode thêm nếu đã xử lý đúng.
10. **Bên nhận có dùng URLDecoder/form parser tương ứng không?** Không diễn giải `+` như space trong path tùy tiện.
11. **Có yêu cầu Unicode normalization hay byte-exact signature không?** Xác định chuẩn hóa và charset trước khi mã hóa.
12. **Có kiểm tra input và output security theo đúng ngữ cảnh không?** Form encoding không thay thế validation, HTML escaping hay parameterized SQL.

## Kết luận

`URLEncoder.encode(String, Charset)` là API **Java 10+** dùng để chuyển **một trường dữ liệu biểu mẫu** sang dạng `application/x-www-form-urlencoded`, với charset xác định. Không phải mọi dấu trong URL đều được xử lý giống form: đặc biệt **space → `+`**, **literal `+` → `%2B`**, các ký tự đặc biệt được escape dựa trên **byte của charset** và dữ liệu Unicode thường dùng UTF-8.

Mã đúng cần encode **từng key/value**, ghép `=` và `&` như cú pháp, chỉ encode **một lần**, và dùng `URLDecoder.decode(String,Charset)` ở nơi nhận dữ liệu form khi cần. Không dùng `URLEncoder` để encode toàn bộ URL hoặc đường dẫn URI. Đây là các kiến thức còn nguyên giá trị trong Java hiện hành.

## Tài liệu tham khảo chính thức

- [Java SE 26 — `URLEncoder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URLEncoder.html): ngữ nghĩa `application/x-www-form-urlencoded`, rules cho `+`/`%HH`, overload `encode(String,Charset)` từ Java 10, xử lý null và ký tự không mã hóa được.
- [Java SE 26 — `URLDecoder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URLDecoder.html): giải mã `+`/`%HH`, overload `decode(String,Charset)` từ Java 10, ngoại lệ malformed escape.
- [Java SE 26 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html): hằng số `UTF_8` và `ISO_8859_1`.
- [Java SE 26 — `CharsetEncoder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetEncoder.html): kiểm soát xử lý ký tự không mã hóa được.
- [Java SE 26 — `java.net.URI`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URI.html): biểu diễn và xây dựng các thành phần URI.
- [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986): quy tắc URI và khác biệt với form-url-encoding.
- [Java SE 26 — `HttpRequest.BodyPublishers`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): chuyển chuỗi body thành bytes theo charset khi gửi HTTP.
