# Đầu vào Unicode và lựa chọn UTF-8 khi mã hóa dữ liệu biểu mẫu (Java 10+)

## 1. Vấn đề: Unicode không thể gửi nguyên dạng trong chuỗi `application/x-www-form-urlencoded`

Khi một biểu mẫu, truy vấn HTTP hay tham số chứa tên người dùng, tiếng Việt, ký tự châu Á hoặc emoji, ứng dụng Java cần biến **dữ liệu văn bản Unicode** thành dạng mã hóa phù hợp với giao thức. Với định dạng **`application/x-www-form-urlencoded`**, hai phương thức tiêu chuẩn là:

~~~java
URLEncoder.encode(String input, Charset charset);
URLDecoder.decode(String encoded, Charset charset);
~~~

Hai overload nhận trực tiếp `Charset` này có từ **Java 10** và vẫn là API chuẩn ở Java hiện đại. Phương án dễ đọc, tránh phụ thuộc cấu hình máy và được khuyến nghị cho dữ liệu biểu mẫu hiện đại là:

~~~java
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

// Ví dụ trong một phương thức:
String original = "Café Việt";
String encoded = URLEncoder.encode(
        original, StandardCharsets.UTF_8);
String decoded = URLDecoder.decode(
        encoded, StandardCharsets.UTF_8);
~~~

Với dữ liệu trên:

~~~text
original: Café Việt
encoded : Caf%C3%A9+Vi%E1%BB%87t
decoded : Café Việt
~~~

**Điểm phải hiểu:** `URLEncoder` **không biến một ký tự Unicode thành một mã `%XXXX` theo code point**. Nó trước tiên dùng **charset** để chuyển ký tự cần escape thành **các byte**, rồi biểu diễn **mỗi byte** thành `%HH` (hai chữ số thập lục phân). Với UTF-8, một ký tự Unicode có thể tạo **một đến bốn byte**.

Chọn UTF-8 nhất quán ở **phía mã hóa và phía giải mã** giúp giữ đúng tiếng Việt và nhiều ngôn ngữ trong trường hợp dữ liệu Unicode đầu vào hợp lệ.

## 2. Mã hóa biểu mẫu là gì?

Tên đầy đủ `application/x-www-form-urlencoded` là một định dạng biểu diễn các **cặp tên–giá trị** trong biểu mẫu. Với Java `URLEncoder`, những quy tắc cơ bản là:

| Dữ liệu đầu vào | Kết quả | Giải thích |
| --- | --- | --- |
| Chữ cái ASCII `A–Z`, `a–z` | Giữ nguyên | Nằm trong nhóm an toàn |
| Chữ số `0–9` | Giữ nguyên | Nằm trong nhóm an toàn |
| `.`, `-`, `*`, `_` | Giữ nguyên | Các ký hiệu an toàn theo `URLEncoder` |
| Dấu cách thông thường `" "` | `+` | Quy tắc riêng của định dạng biểu mẫu |
| Dấu cộng thật `+` | `%2B` | Để không bị nhầm với khoảng trắng khi giải mã |
| Dấu `&` | `%26` | Không nhầm với ký tự phân tách các tham số |
| Dấu `=` | `%3D` | Không nhầm với dấu phân tách tên và giá trị |
| Chữ `é` với UTF-8 | `%C3%A9` | Hai byte UTF-8: `C3 A9` |
| Chữ `ệ` với UTF-8 | `%E1%BB%87` | Ba byte UTF-8: `E1 BB 87` |
| Emoji 🙂 với UTF-8 | `%F0%9F%99%82` | Bốn byte UTF-8 |

Các byte được biểu diễn bằng dạng `%HH`, với `HH` là giá trị hex. `URLEncoder` giữ lại nhóm ký tự an toàn và biến những ký tự không an toàn thành các dãy escape phù hợp.

**Không có chuyện mọi ký tự đều được biến thành một escape.** Ví dụ `a` và `1` được giữ nguyên; dấu cách được đổi thành `+`; trong khi `é` phải trải qua mã hóa UTF-8 thành hai byte trước khi được viết thành hai dãy `%HH`.

**Không nhầm với mã hóa toàn bộ URL.** `URLEncoder` được thiết kế cho **giá trị/tên thành phần biểu mẫu**, không phải công cụ để biến toàn bộ `https://host/path?x=...` thành một URL hợp lệ.

## 3. API Java 10: truyền đối tượng `Charset` thay vì tên chuỗi

Chữ ký đầy đủ đáng nhớ:

~~~java
public static String encode(String s, Charset charset);
public static String decode(String s, Charset charset);
~~~

Đây là **chữ ký của thư viện `java.net`**, không phải phương thức bạn cần tự triển khai.

Các import cần thiết:

~~~java
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
~~~

### Mã hóa Unicode thành dữ liệu biểu mẫu

~~~java
String name = "Café Việt";

String parameterValue =
        URLEncoder.encode(name, StandardCharsets.UTF_8);

System.out.println(parameterValue);
// Caf%C3%A9+Vi%E1%BB%87t
~~~

### Giải mã đúng với cùng charset

~~~java
String recovered =
        URLDecoder.decode(parameterValue, StandardCharsets.UTF_8);

System.out.println(recovered.equals(name)); // true
~~~

**Vì sao dùng `StandardCharsets.UTF_8`?**

1. Charset được xác định rõ ngay trong mã.
2. Không phụ thuộc charset mặc định của hệ điều hành/JVM.
3. Hỗ trợ đầy đủ các Unicode code point hợp lệ.
4. Không cần tự nhập tên charset và tra cứu tên mỗi lần.
5. Hai overload nhận `Charset` **không khai báo checked `UnsupportedEncodingException`**, khác các overload nhận tên charset `String`.

### So sánh những API thường thấy

| Lời gọi | Đặc điểm | Cách dùng |
| --- | --- | --- |
| `URLEncoder.encode(s, StandardCharsets.UTF_8)` | Java 10+, charset tường minh, không cần checked exception tên charset | **Ưu tiên** |
| `URLDecoder.decode(s, StandardCharsets.UTF_8)` | Java 10+, giải mã theo cùng charset | **Ưu tiên** |
| `URLEncoder.encode(s, "UTF-8")` | API còn hợp lệ, dùng tên charset `String`; khai báo `UnsupportedEncodingException` | Dùng khi phải tương thích API kiểu cũ |
| `URLEncoder.encode(s)` | Dùng charset mặc định, **đã deprecated** | **Không chọn cho mã mới** |
| `URLDecoder.decode(s)` | Dùng charset mặc định, **đã deprecated** | **Không chọn cho mã mới** |

Việc default charset thường là UTF-8 trong các phiên bản Java mới theo JEP 400 **không phải lý do để bỏ tham số charset** khi dữ liệu cần một hợp đồng trao đổi rõ ràng. Mã Java có thể chạy trên nhiều cấu hình, hoặc cần giao tiếp với hệ thống đã định chuẩn UTF-8.

## 4. Từng bước chuyển `"Café Việt"` thành `Caf%C3%A9+Vi%E1%BB%87t`

Tách chuỗi theo ký tự:

~~~text
C  a  f  é     V  i  ệ  t
~~~

Những chữ ASCII `C`, `a`, `f`, `V`, `i` và `t` thuộc tập an toàn của `URLEncoder` nên được giữ lại. Khoảng trắng ở giữa chuyển thành `+`.

Hai chữ có dấu phải biến thành byte theo UTF-8:

| Ký tự | Unicode code point | Byte UTF-8 | Biểu diễn biểu mẫu |
| --- | --- | --- | --- |
| `é` | U+00E9 | `C3 A9` | `%C3%A9` |
| `ệ` | U+1EC7 | `E1 BB 87` | `%E1%BB%87` |

Sau khi ghép theo thứ tự:

~~~text
Caf%C3%A9+Vi%E1%BB%87t
~~~

Khi phía nhận gọi `URLDecoder.decode(..., UTF_8)`:

1. Dấu `+` được hiểu là khoảng trắng.
2. `%C3%A9` trở về hai byte `C3 A9`, rồi UTF-8 giải mã thành `é`.
3. `%E1%BB%87` trở về ba byte `E1 BB 87`, rồi UTF-8 giải mã thành `ệ`.
4. Các chữ ASCII an toàn giữ nguyên.

Kết quả là **`"Café Việt"`**, không bị mất dấu.

**Đơn vị đếm khác nhau:**

~~~java
String name = "Caf\u00E9 Vi\u1EC7t";

System.out.println(name.length()); // 9 đơn vị UTF-16
System.out.println(
        name.getBytes(StandardCharsets.UTF_8).length); // 12 byte
~~~

Chuỗi có 9 đơn vị `char` UTF-16 nhưng 12 byte UTF-8. Số ký tự trong chuỗi mã hóa biểu mẫu lại khác, vì **mỗi byte được escape chiếm ba ký tự ASCII** trong chuỗi kết quả.

## 5. Emoji và ký tự Unicode bổ sung: bốn byte UTF-8

Các ký tự Unicode ngoài Basic Multilingual Plane (BMP) được biểu diễn bằng **hai đơn vị UTF-16 `char`** trong `String` Java. Ví dụ emoji 🙂 là U+1F642, mã hóa UTF-8 thành **`F0 9F 99 82`**.

Có thể tạo emoji bằng code point để mã nguồn Java không phụ thuộc việc editor hiển thị biểu tượng:

~~~java
String smile = new String(Character.toChars(0x1F642));
String input = "A" + smile + "B";

String encoded =
        URLEncoder.encode(input, StandardCharsets.UTF_8);

System.out.println(encoded); // A%F0%9F%99%82B
~~~

So sánh:

~~~java
System.out.println(input.length()); // 4 đơn vị UTF-16

System.out.println(
        input.codePointCount(0, input.length())); // 3 code point

System.out.println(
        input.getBytes(StandardCharsets.UTF_8).length); // 6 byte
~~~

`A` và `B` dùng hai byte ASCII; emoji ở giữa dùng bốn byte UTF-8. Vì thế dữ liệu mã hóa sẽ chứa **bốn escape `%HH`** cho emoji, không phải một escape `%1F642`.

**Không tự duyệt từng `char` rồi mã hóa riêng** nếu muốn chuyển đổi Unicode hợp lệ: một cặp surrogate cần được xử lý thành cùng một code point. `URLEncoder.encode(String, UTF_8)` thực hiện việc sử dụng charset thay bạn.

### Nếu chuỗi chứa surrogate không hợp lệ?

Đặc tả `URLEncoder.encode(String, Charset)` hiện hành nói rằng **đầu vào malformed** hoặc ký tự không thể biểu diễn bằng charset đã chọn sẽ được thay bằng giá trị thay thế theo `Charset`. Vì vậy, không nên hứa phép round-trip bảo toàn một chuỗi có **surrogate lỗi** hoặc dùng charset không hỗ trợ ký tự đó.

UTF-8 hỗ trợ Unicode hợp lệ rộng hơn các bộ mã một byte như ISO-8859-1, nhưng **UTF-8 không tự sửa lỗi dữ liệu Unicode đã bị hỏng trước khi mã hóa**. Nếu ứng dụng cần từ chối dữ liệu malformed thay vì thay thế, phải xây quy trình kiểm tra và chính sách lỗi có chủ đích.

## 6. Khoảng trắng, dấu cộng, dấu `&` và `=` trong dữ liệu biểu mẫu

Với input:

~~~java
String input = "a b+c&d=é";

String encoded =
        URLEncoder.encode(input, StandardCharsets.UTF_8);

System.out.println(encoded);
// a+b%2Bc%26d%3D%C3%A9
~~~

Giải nghĩa:

| Thành phần gốc | Thành phần mã hóa |
| --- | --- |
| `a` | `a` |
| Dấu cách | `+` |
| `b` | `b` |
| Dấu cộng thật `+` | `%2B` |
| `c` | `c` |
| Dấu ampersand `&` | `%26` |
| `d` | `d` |
| Dấu bằng `=` | `%3D` |
| `é` | `%C3%A9` |

Khi giải mã bằng `URLDecoder` cùng UTF-8:

~~~java
String restored = URLDecoder.decode(
        "a+b%2Bc%26d%3D%C3%A9",
        StandardCharsets.UTF_8);

System.out.println(restored.equals(input)); // true
~~~

**Phân biệt dấu `+`:**

- Trong chuỗi **đã mã hóa**, dấu `+` được giải mã thành **dấu cách**.
- Nếu người dùng gõ một dấu cộng thực sự, `URLEncoder` mã hóa thành **`%2B`**, rồi `URLDecoder` khôi phục dấu `+`.
- Không thay thế thủ công mọi dấu `+` thành khoảng trắng **trước khi mã hóa**; hãy để API xử lý.

Quy tắc này khác việc mã hóa đường dẫn URL. Ở đường dẫn, dấu `+` không có nghĩa chung là dấu cách theo cách `application/x-www-form-urlencoded` định nghĩa.

## 7. Tạo tham số truy vấn hoặc body biểu mẫu đúng cách

Một chuỗi biểu mẫu có thể gồm nhiều cặp `name=value`, được nối bằng `&`. Khi ghép thủ công, **mã hóa riêng từng tên và từng giá trị**, còn các dấu phân tách cấu trúc `=` và `&` được chèn sau đó.

~~~java
String search = "Café Việt";
String note = "a b+c&d=é";

String query = "q="
        + URLEncoder.encode(search, StandardCharsets.UTF_8)
        + "&note="
        + URLEncoder.encode(note, StandardCharsets.UTF_8);

System.out.println(query);
// q=Caf%C3%A9+Vi%E1%BB%87t&note=a+b%2Bc%26d%3D%C3%A9
~~~

Vì `&` và `=` **nằm trong giá trị `note`** đã được chuyển thành `%26` và `%3D`, chúng không bị nhầm với dấu chia cặp tham số.

### Mã hóa cả tên tham số khi tên có ký tự đặc biệt

Ví dụ, tên field do ứng dụng định nghĩa là `"tên"`:

~~~java
String key = URLEncoder.encode("tên", StandardCharsets.UTF_8);
String value = URLEncoder.encode("An", StandardCharsets.UTF_8);

String pair = key + "=" + value;
// key là t%C3%AAn
~~~

Tên tham số cũng có thể chứa Unicode; quy tắc mã hóa áp dụng tương tự như với giá trị. Với key ASCII đơn giản như `"q"` hay `"note"` thì `URLEncoder` thường giữ nguyên.

### Không mã hóa nguyên chuỗi query đã ghép

Sai:

~~~java
String query = "q=Café Việt&note=a+b";
String wronglyEncodedWholeQuery =
        URLEncoder.encode(query, StandardCharsets.UTF_8);

// Dấu = và & cấu trúc bị escape.
// Người nhận có thể không còn nhận được 2 cặp name=value.
~~~

Đúng: encode **từng thành phần dữ liệu**, sau đó mới ghép dấu `=` và `&`. Nếu dùng thư viện HTTP hỗ trợ query/form parameters, nên ưu tiên API quản lý tham số của thư viện đó, tránh ghép chuỗi thủ công và vô tình encode hai lần.

### Gắn vào URL hay gửi bằng POST?

- Với **query** trên URL, có thể gắn chuỗi `q=...&note=...` đã mã hóa đúng vào phần query của một URL thích hợp.
- Với **HTTP POST có `Content-Type: application/x-www-form-urlencoded`**, body có thể mang chuỗi cặp name–value có cùng kiểu biểu diễn.

**Không coi `URLEncoder` là API mã hóa đường dẫn `/users/...`, fragment `#...`, userinfo hoặc toàn bộ địa chỉ URL.** Mỗi thành phần URI có quy tắc riêng; dùng API xử lý URI/HTTP theo đúng ngữ cảnh.

## 8. Bộ mã ở hai phía phải thống nhất: Unicode và lỗi mojibake

Giả sử phía gửi mã hóa `"Café Việt"` thành:

~~~text
Caf%C3%A9+Vi%E1%BB%87t
~~~

Các `%HH` chứa **byte UTF-8**. Nếu phía nhận cố giải mã chuỗi đó bằng `ISO_8859_1` thay vì UTF-8, một số byte riêng lẻ có thể được hiểu thành các ký tự khác nhau. Kết quả không còn bằng văn bản gốc (*mojibake*).

~~~java
String input = "Café Việt";

String encoded = URLEncoder.encode(
        input, StandardCharsets.UTF_8);

String wrong = URLDecoder.decode(
        encoded, StandardCharsets.ISO_8859_1);

System.out.println(wrong.equals(input)); // false
~~~

**Không chỉ đúng charset ở phía gửi:** bên nhận, server hoặc framework xử lý request cũng cần **cùng hợp đồng UTF-8**. Khi dùng HTTP, hãy kiểm soát cấu hình giải mã tham số của framework/HTTP stack và `Content-Type` thích hợp đối với form body theo đặc tả môi trường. Không tự mặc định rằng mọi server hay thư viện sẽ đọc theo đúng charset mình muốn trong mọi trường hợp.

Nếu dùng charset không biểu diễn được một ký tự, `URLEncoder.encode` hiện hành có thể dùng byte thay thế theo charset thay vì tạo lại được ký tự ấy. Ví dụ các chữ tiếng Việt không thuộc ISO-8859-1 không thể được biểu diễn đầy đủ bằng bộ mã đó.

**Khuyến nghị:** trong hệ thống mới dùng Unicode, chọn UTF-8 theo hợp đồng ở **mọi bước** và xác minh mã hóa/giải mã bằng kiểm thử có dữ liệu tiếng Việt, ký tự bổ sung và ký hiệu đặc biệt.

## 9. Chuẩn hóa Unicode: hai chuỗi trông giống nhau vẫn có byte khác

Unicode cho phép một số nội dung hiển thị tương đương được biểu diễn bằng **các dãy code point khác nhau**.

Ví dụ hai cách viết chữ `é`:

- **Precomposed:** code point `U+00E9`.
- **Decomposed:** chữ `e` (`U+0065`) theo sau là dấu sắc kết hợp `U+0301`.

~~~java
String composed = "\u00E9";
String decomposed = "e\u0301";

String encodedComposed =
        URLEncoder.encode(composed, StandardCharsets.UTF_8);

String encodedDecomposed =
        URLEncoder.encode(decomposed, StandardCharsets.UTF_8);

System.out.println(encodedComposed);   // %C3%A9
System.out.println(encodedDecomposed); // e%CC%81
~~~

Hai biểu diễn có thể trông giống nhau trên màn hình nhưng **khác chuỗi code point**, nên chúng tạo ra các byte UTF-8 và chuỗi mã hóa khác nhau. `URLEncoder` **không tự chuẩn hóa Unicode**.

Nếu hệ thống cần các chuỗi tương đương theo quy tắc chuẩn hóa thành một dạng chung, có thể chuẩn hóa **trước khi mã hóa**:

~~~java
import java.text.Normalizer;

String normalized =
        Normalizer.normalize(decomposed, Normalizer.Form.NFC);

String encodedNormalized =
        URLEncoder.encode(normalized, StandardCharsets.UTF_8);

System.out.println(encodedNormalized); // %C3%A9
~~~

**Quan trọng:** chuẩn hóa là một **quyết định nghiệp vụ**, không phải bước bắt buộc trong mọi biểu mẫu. Với dữ liệu định danh, chữ ký số, nội dung người dùng cần giữ nguyên từng code point hoặc giao thức có quy tắc canonicalization riêng, phải tuân thủ đặc tả của hệ thống. Không tự thay đổi input chỉ để chuỗi “trông giống nhau” khi không được yêu cầu.

## 10. Chương trình hoàn chỉnh: Unicode, UTF-8, round-trip và lỗi thường gặp

Lưu chương trình sau thành **`FormUnicodeDemo.java`**. Mã dùng các API `URLEncoder.encode(String, Charset)`/`URLDecoder.decode(String, Charset)` từ Java 10 và chạy được trên **JDK 17+**.

~~~java
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

public class FormUnicodeDemo {
    public static void main(String[] args) {
        var utf8 = StandardCharsets.UTF_8;

        // Dùng Unicode escapes để ví dụ không phụ thuộc editor.
        String name = "Caf\u00E9 Vi\u1EC7t";

        String encoded = URLEncoder.encode(name, utf8);
        System.out.println("nameEncoded=" + encoded);
        System.out.println("nameRoundTrip="
                + URLDecoder.decode(encoded, utf8).equals(name));

        System.out.println("nameUtf16=" + name.length());
        System.out.println("nameUtf8Bytes="
                + name.getBytes(utf8).length);

        // Ký tự ngoài BMP: một code point, hai UTF-16 units,
        // bốn byte UTF-8.
        String emoji =
                "A" + new String(Character.toChars(0x1F642)) + "B";

        System.out.println("emojiEncoded="
                + URLEncoder.encode(emoji, utf8));
        System.out.println("emojiUtf16=" + emoji.length());
        System.out.println("emojiCodePoints="
                + emoji.codePointCount(0, emoji.length()));
        System.out.println("emojiRoundTrip="
                + URLDecoder.decode(
                        URLEncoder.encode(emoji, utf8), utf8)
                        .equals(emoji));

        // Các dấu +, & và = là DỮ LIỆU người dùng.
        String special = "a b+c&d=\u00E9";
        String encodedSpecial = URLEncoder.encode(special, utf8);

        System.out.println("specialEncoded=" + encodedSpecial);
        System.out.println("specialRoundTrip="
                + URLDecoder.decode(encodedSpecial, utf8)
                        .equals(special));

        String query = "q=" + encoded
                + "&note=" + encodedSpecial;
        System.out.println("query=" + query);

        // Đọc byte UTF-8 theo ISO-8859-1 làm sai nội dung.
        String wrong = URLDecoder.decode(
                encoded, StandardCharsets.ISO_8859_1);

        System.out.println("charsetMismatch="
                + !wrong.equals(name));

        // Hai biểu diễn Unicode tương đương về hình dạng,
        // nhưng chuỗi byte mã hóa ban đầu khác nhau.
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("precomposed="
                + URLEncoder.encode(composed, utf8));
        System.out.println("decomposed="
                + URLEncoder.encode(decomposed, utf8));

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("normalizedEqual="
                + URLEncoder.encode(composed, utf8)
                        .equals(URLEncoder.encode(normalized, utf8)));

        // Không mã hóa một thành phần đã được mã hóa.
        String once = URLEncoder.encode("a b", utf8);
        String twice = URLEncoder.encode(once, utf8);

        System.out.println("once=" + once);
        System.out.println("twice=" + twice);
        System.out.println("twiceDecodedOnce="
                + URLDecoder.decode(twice, utf8));

        // Đối số input null là không hợp lệ.
        try {
            URLEncoder.encode(null, utf8);
        } catch (NullPointerException ex) {
            System.out.println("nullInput=NPE");
        }

        // Escape % không hợp lệ.
        try {
            URLDecoder.decode("%G0", utf8);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalidPercent=IAE");
        }
    }
}
~~~

Chạy từ terminal trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 FormUnicodeDemo.java
java FormUnicodeDemo
~~~

**`stdout` đã kiểm thử trên JDK 24:**

~~~text
nameEncoded=Caf%C3%A9+Vi%E1%BB%87t
nameRoundTrip=true
nameUtf16=9
nameUtf8Bytes=12
emojiEncoded=A%F0%9F%99%82B
emojiUtf16=4
emojiCodePoints=3
emojiRoundTrip=true
specialEncoded=a+b%2Bc%26d%3D%C3%A9
specialRoundTrip=true
query=q=Caf%C3%A9+Vi%E1%BB%87t&note=a+b%2Bc%26d%3D%C3%A9
charsetMismatch=true
precomposed=%C3%A9
decomposed=e%CC%81
normalizedEqual=true
once=a+b
twice=a%2Bb
twiceDecodedOnce=a+b
nullInput=NPE
invalidPercent=IAE
~~~

Phân tích kết quả:

1. **`nameEncoded`:** `é` thành hai escape, `ệ` thành ba escape, khoảng trắng thành dấu `+`.
2. **`nameRoundTrip=true`:** cùng UTF-8 ở hai phía bảo toàn chuỗi hợp lệ.
3. **`nameUtf16=9`, `nameUtf8Bytes=12`:** ký tự Java và byte UTF-8 không phải cùng đại lượng.
4. **`emojiEncoded=A%F0%9F%99%82B`:** ký tự ngoài BMP thành bốn byte UTF-8.
5. **`emojiUtf16=4`, `emojiCodePoints=3`:** hai cách đếm Unicode khác nhau.
6. **`specialEncoded`:** các dấu `+`, `&`, `=` trong dữ liệu được escape, tránh nhầm với cấu trúc form.
7. **`query`:** cặp tham số được ghép **sau khi** từng giá trị đã được mã hóa.
8. **`charsetMismatch=true`:** cùng byte nhưng dùng charset khác để giải mã làm sai chuỗi.
9. **`precomposed` và `decomposed`:** dữ liệu nhìn tương đương nhưng khác dãy code point có biểu diễn `%HH` khác.
10. **`normalizedEqual=true`:** bước chuẩn hóa NFC có chủ đích đưa chúng về cùng dạng mã hóa.
11. **`once`, `twice`:** mã hóa hai lần biến `+` của lần đầu thành `%2B`; giải mã một lần cho ra chuỗi đã mã hóa lần đầu, chưa phải dữ liệu gốc.
12. **`nullInput=NPE` và `invalidPercent=IAE`:** hai loại đầu vào sai khác nhau.

Kết quả được in dưới dạng ASCII/boolean để không phụ thuộc khả năng hiển thị emoji và tiếng Việt của console.

## 11. Tránh mã hóa hai lần và giải mã hai lần

Giả sử dữ liệu gốc là `"a b"`:

~~~java
String once = URLEncoder.encode(
        "a b", StandardCharsets.UTF_8); // a+b

String twice = URLEncoder.encode(
        once, StandardCharsets.UTF_8); // a%2Bb
~~~

Giải mã **một lần** từ `"a%2Bb"`:

~~~java
System.out.println(
        URLDecoder.decode(twice, StandardCharsets.UTF_8));
// a+b
~~~

Đây **không phải** `"a b"`. Dấu `+` ở kết quả giải mã là dấu cộng thật trong chuỗi biểu diễn sau một tầng; nếu có lớp thứ hai giải mã nữa mới thành khoảng trắng.

**Rủi ro khi tích hợp hệ thống:** một tầng framework có thể đã tự mã hóa parameter, còn code ứng dụng lại gọi `URLEncoder` trước đó, dẫn tới double encoding. Ngược lại, giải mã nhiều lần có thể làm các dấu phân cách hoặc ký tự đặc biệt xuất hiện ngoài dự tính của tầng kiểm tra đầu vào.

Nguyên tắc:

- Biết rõ dữ liệu ở trạng thái **raw Unicode** hay **đã được percent-encoded**.
- Quy định **một nơi chịu trách nhiệm mã hóa**, và một nơi chịu trách nhiệm giải mã khi parsing request.
- Khi thư viện HTTP có API thêm query parameter/form field, truyền **giá trị raw** theo hợp đồng của thư viện, không mặc định phải tự encode trước.
- Đừng gọi `URLDecoder.decode` lên toàn bộ URL hoặc chuỗi đã được framework giải mã mà không biết cấu trúc và trạng thái dữ liệu.

## 12. Dùng `URLDecoder` đúng ngữ cảnh

`URLDecoder.decode` là phép giải mã **`application/x-www-form-urlencoded`**, không phải một parser tự tách URL thành host, đường dẫn, query, fragment.

Ví dụ:

~~~java
String encodedValue = "a+b%2Bc%26d%3D%C3%A9";

String decoded = URLDecoder.decode(
        encodedValue, StandardCharsets.UTF_8);
// a b+c&d=é
~~~

Nếu bạn có một query gồm nhiều cặp, **phải xác định ranh giới cặp trước khi giải mã giá trị**, nếu tự viết parser. Lý do: một dấu `&` được người dùng nhập trong giá trị sẽ được biểu diễn là `%26`; nếu giải mã toàn bộ query trước, `%26` trở thành `&` và có thể bị nhầm thành một dấu phân cách cặp.

Ví dụ query:

~~~text
q=Caf%C3%A9+Vi%E1%BB%87t&note=a+b%2Bc%26d%3D%C3%A9
~~~

Cách hiểu đúng:

- Cặp `q` có giá trị sau giải mã `"Café Việt"`.
- Cặp `note` có giá trị sau giải mã `"a b+c&d=é"`.

Nếu ứng dụng cần xử lý query thực tế có key lặp, giá trị trống, dấu `=` bổ sung, giới hạn kích thước và lỗi malformed, hãy dùng parser đáng tin cậy của HTTP framework thay vì tự chia chuỗi theo nhiều quy tắc không đầy đủ.

### Không dùng `URLDecoder` cho mọi phần của URI

Đặc biệt, trong đường dẫn `/a+b`, dấu `+` thường được hiểu là dấu cộng đúng nghĩa, nhưng `URLDecoder.decode("a+b", UTF_8)` chuyển nó thành `"a b"`. Đó là một lý do quan trọng để không giải mã tùy tiện **URI path** bằng công cụ dành riêng cho biểu mẫu.

## 13. Lỗi đầu vào: null, escape hỏng và dữ liệu byte không hợp lệ

### Đối số `null`

Hai overload Java 10 nhận `Charset` quy định:

~~~java
// Các lời gọi dưới đây minh họa lỗi, đừng chạy khi muốn program thành công:
URLEncoder.encode(null, StandardCharsets.UTF_8); // NPE
URLEncoder.encode("A", null);                     // NPE
URLDecoder.decode(null, StandardCharsets.UTF_8); // NPE
URLDecoder.decode("A", null);                     // NPE
~~~

Tất cả đều ném `NullPointerException` vì input hoặc charset là null. Nếu lấy giá trị từ form có thể thiếu, phải xác định xem “thiếu” khác với **chuỗi rỗng `""`** thế nào. Không tự chuyển `null` thành `""` nếu nghiệp vụ không cho phép.

### Escape `%` không hợp lệ

Các dãy `%xy` hợp lệ phải có đủ hai chữ số hex. Ví dụ `"%G0"` có `G` không thuộc tập hex.

~~~java
try {
    URLDecoder.decode("%G0", StandardCharsets.UTF_8);
} catch (IllegalArgumentException ex) {
    System.out.println("Malformed escape");
}
~~~

Theo Javadoc, decoder có thể ném `IllegalArgumentException` khi gặp escape malformed; chương trình kiểm thử trên JDK 24 xác nhận trường hợp này. **Không kiểm thử bằng văn bản thông điệp ngoại lệ** vì thông điệp cụ thể có thể thay đổi.

### Percent escapes có byte không phải UTF-8 hợp lệ

Đừng nhầm lỗi cú pháp escape với lỗi giải mã byte:

- `%G0` là dãy escape **sai cú pháp hex**.
- `%FF` là byte escape **đúng cú pháp**, nhưng byte đơn lẻ `FF` không phải chuỗi UTF-8 hợp lệ.

`URLDecoder.decode(String, Charset)` hiện hành mô tả rằng **các byte lỗi** được thay bằng **giá trị replacement** của charset khi giải mã. Không nên hứa rằng mọi percent sequence đúng cú pháp đều tạo Unicode gốc hợp lệ.

Nếu một giao thức yêu cầu **từ chối dữ liệu byte UTF-8 hỏng** thay vì thay thế, hãy dùng bước kiểm tra phù hợp ở tầng bytes/decoder với `CodingErrorAction.REPORT` và quy tắc parsing đã được xác định. Đừng chỉ dựa vào việc `URLDecoder` trả về một `String` để kết luận input ban đầu không có lỗi.

## 14. UTF-8 là lựa chọn bộ mã, không phải toàn bộ bài toán bảo mật

Mã hóa biểu mẫu giải quyết **đại diện dữ liệu khi truyền**. Nó **không đồng nghĩa** với việc:

- Làm sạch HTML để chống XSS.
- Chuẩn bị câu SQL an toàn để chống SQL injection.
- Kiểm tra hợp lệ độ dài, định dạng hoặc quyền truy cập của một tham số.
- Bảo vệ dữ liệu riêng tư khỏi người quan sát mạng.

Ví dụ, nếu người dùng nhập `"<script>..."`, `URLEncoder` có thể percent-encode ký tự `<`/`>` để đưa qua query/form an toàn về mặt **cú pháp truyền**, nhưng **sau khi decode**, nội dung vẫn là HTML/JavaScript text do người dùng cung cấp. Khi chèn vào trang HTML, phải dùng **escaping theo ngữ cảnh đầu ra** (hoặc API template có cơ chế bảo vệ), không dùng URL encoding để thay thế.

Tương tự, khi tạo câu SQL, vẫn phải dùng **parameterized queries**. Một giá trị đã được URL-encoded hoặc URL-decoded không tự biến thành dữ liệu hợp lệ/bảo mật.

**Phần mã hóa không cung cấp tính bí mật.** Dữ liệu người dùng qua URL query vẫn có thể xuất hiện trong lịch sử, log hoặc hệ thống quan sát; nên dùng cơ chế truyền và thiết kế API phù hợp để tránh đưa dữ liệu nhạy cảm vào query.

## 15. Cách chọn UTF-8 trong thực tế

Khi xây dựng một request có đầu vào Unicode:

1. **Hiểu hợp đồng nguồn:** dữ liệu đã là `String` Java, hay là byte chưa được giải mã? Nếu đang giữ byte, phải giải mã đúng charset tại nơi nhận byte trước khi xử lý.
2. **Giữ dữ liệu raw Unicode** trong phần xử lý nghiệp vụ, không encode quá sớm khi chưa biết nơi sẽ sử dụng.
3. **Chọn `StandardCharsets.UTF_8` tường minh** tại bước chuyển sang `application/x-www-form-urlencoded`.
4. **Mã hóa riêng từng field name/value**, không mã hóa nguyên URL, không encode lặp.
5. **Ghép/để thư viện HTTP quản lý cấu trúc** cặp tên–giá trị.
6. **Phía nhận dùng cùng quy tắc UTF-8**; tránh giải mã thêm lần nữa khi framework đã xử lý.
7. **Đánh giá Unicode normalization** nếu ứng dụng thật sự cần so sánh các dạng tương đương, và quy định một chuẩn cho toàn hệ thống.
8. **Kiểm thử không chỉ ASCII:** thêm tiếng Việt, emoji, dấu cách, `+`, `&`, `=`, ký tự kết hợp và dữ liệu malformed.

### Kiểm thử tối thiểu có ích

Một bộ kiểm thử tốt sẽ xác nhận:

| Trường hợp | Kiểm tra cần đạt |
| --- | --- |
| `"hello"` | ASCII an toàn giữ nguyên |
| `"a b"` | Dấu cách thành `+` |
| `"a+b"` | Dấu cộng thật thành `%2B` |
| `"Café Việt"` | `Caf%C3%A9+Vi%E1%BB%87t` |
| `"A" + 🙂 + "B"` | `A%F0%9F%99%82B` |
| `"x&y=z"` | `x%26y%3Dz` |
| Chuỗi Unicode hợp lệ | `decode(encode(s, UTF_8), UTF_8).equals(s)` |
| Hai dạng `é` khác nhau | Escape khác trước normalizing; có thể cùng escape sau NFC |
| Charset giải mã khác UTF-8 | Có nguy cơ mất/đổi nội dung |
| `null`/percent escape hỏng | Xử lý ngoại lệ theo hợp đồng |
| Encode hai lần | Phát hiện qua `%2B`/`%25` thay vì silently nhận |

Với các ký tự Unicode có surrogate hỏng, round-trip tuyệt đối có thể không đạt do quy tắc replacement của encoder, nên kiểm thử phải xác định rõ dữ liệu đầu vào nào hợp lệ theo hợp đồng.

## 16. Các lỗi thường gặp

| Hiểu nhầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “`URLEncoder` mã hóa mỗi Unicode code point thành một `%HH`.” | UTF-8 có thể dùng nhiều byte cho một code point. | Xem byte UTF-8 trước khi hiểu percent encoding. |
| “Chữ có dấu chỉ cần thêm dấu `%` trước mã Unicode.” | `%HH` biểu diễn **byte**, không phải `U+XXXX`. | Dùng `URLEncoder.encode(input, UTF_8)`. |
| “Dấu cách phải luôn thành `%20`.” | Với `application/x-www-form-urlencoded`, Java đổi dấu cách thành `+`. | Dùng đúng quy tắc của form; không đánh đồng URI path. |
| “Dấu `+` của người dùng cũng để nguyên.” | Decoder sẽ hiểu `+` thành khoảng trắng. | Mã hóa dấu cộng dữ liệu thành `%2B`. |
| “Encode toàn bộ `?q=...&note=...` một lần.” | Dấu cấu trúc `=`/`&` cũng bị escape. | Encode riêng từng key/value rồi ghép. |
| “Cứ có UTF-8 ở bên gửi là phía nhận đọc đúng.” | Phía nhận có thể dùng charset khác. | Thiết lập hợp đồng charset hai phía. |
| “Java 10 cần dùng tên charset `String`.” | Overload nhận `Charset` đã có từ Java 10. | Ưu tiên `StandardCharsets.UTF_8`. |
| “Hai chữ nhìn giống nhau luôn cho cùng escape.” | Unicode có các dạng code point khác nhau. | Xác định chính sách normalization nếu cần. |
| “Encode hai lần không gây vấn đề.” | Dấu `%` và `+` của lần trước bị encode lần nữa. | Encode chính xác một lần tại ranh giới truyền. |
| “URL encoding chống XSS/SQL injection.” | Chỉ là biểu diễn cho truyền tải, không phải bảo mật đầu ra hay truy vấn. | Escape/parameterize theo đúng ngữ cảnh. |
| “`URLDecoder` dùng cho toàn URL/path.” | Nó áp dụng quy tắc form, đặc biệt `+` → space. | Sử dụng URI/HTTP parser theo thành phần. |

## 17. Bài tập tự kiểm tra

### Bài 1 — Dấu cách và dấu cộng

~~~java
String value = "A B+C";
String encoded = URLEncoder.encode(
        value, StandardCharsets.UTF_8);

System.out.println(encoded);
~~~

**Đáp án:** `A+B%2BC`. Khoảng trắng thành `+`, còn dấu cộng thật thành `%2B`.

### Bài 2 — Chữ có dấu

~~~java
String value = "\u00E9";
System.out.println(
        URLEncoder.encode(value, StandardCharsets.UTF_8));
~~~

**Đáp án:** `%C3%A9`. Chữ `é` là Unicode U+00E9, được UTF-8 mã hóa thành hai byte `C3 A9`.

### Bài 3 — Emoji ngoài BMP

~~~java
String face = new String(Character.toChars(0x1F642));

System.out.println(
        URLEncoder.encode(face, StandardCharsets.UTF_8));
~~~

**Đáp án:** `%F0%9F%99%82`. Không phải `%1F642`.

### Bài 4 — Đúng/sai về Charset

Bạn mã hóa một trường bằng `URLEncoder.encode(value, StandardCharsets.UTF_8)`, nhưng người nhận giải mã bằng `ISO_8859_1`. Có được bảo đảm văn bản tiếng Việt giữ nguyên không?

**Đáp án:** Không. `%HH` biểu diễn byte UTF-8, nên phía nhận cần giải mã đúng UTF-8. Bộ mã khác có thể làm sai chữ có dấu.

### Bài 5 — Form data và query

Người dùng nhập `"a&b=c"`. Có nên nối trực tiếp `"note=" + value` để thành query không?

**Đáp án:** Không. Cần mã hóa giá trị riêng: `note=a%26b%3Dc`. Nếu không, `&` và `=` có thể bị parser hiểu là dấu cấu trúc.

### Bài 6 — Unicode normalization

`"\u00E9"` và `"e\u0301"` có được bảo đảm cho cùng kết quả `URLEncoder.encode(..., UTF_8)` không?

**Đáp án:** Không. Kết quả lần lượt là `%C3%A9` và `e%CC%81`. Chỉ khi có bước normalization theo quy tắc cần thiết, hai biểu diễn mới có thể được chuyển về cùng dạng trước khi mã hóa.

### Bài 7 — Mã hóa lặp

~~~java
String original = "a b";
String once = URLEncoder.encode(
        original, StandardCharsets.UTF_8);
String twice = URLEncoder.encode(
        once, StandardCharsets.UTF_8);
~~~

**Đáp án:** `once` là `a+b`, `twice` là `a%2Bb`. Giải mã `twice` đúng một lần chỉ cho `a+b`, chưa khôi phục `"a b"`.

### Bài 8 — Ngoại lệ

`URLEncoder.encode(null, UTF_8)` và `URLDecoder.decode("%G0", UTF_8)` lần lượt gây lỗi gì?

**Đáp án:** `NullPointerException` cho input null; với JDK chuẩn khi gặp `%G0`, `IllegalArgumentException` do escape không hợp lệ.

## 18. Tổng kết

- **`URLEncoder.encode(String, Charset)` và `URLDecoder.decode(String, Charset)` đã có từ Java 10 và vẫn hiện hành.**
- **Chọn `StandardCharsets.UTF_8` rõ ràng** cho dữ liệu biểu mẫu Unicode, và bảo đảm bên nhận dùng cùng charset.
- Chuỗi Unicode được mã hóa thành **byte theo charset**, sau đó các byte không an toàn thành **`%HH`**. Một emoji có thể thành bốn escape vì UTF-8 dùng bốn byte.
- Với `application/x-www-form-urlencoded`, **dấu cách → `+`**, còn **dấu cộng thật → `%2B`**; `&`, `=` trong dữ liệu cũng phải escape.
- **Encode riêng tên/giá trị từng tham số**, không encode nguyên URL hoặc toàn chuỗi đã ghép.
- **Không encode/decode lặp** và không nhầm form decoder với URI path decoder.
- **Chuẩn hóa Unicode là bước tùy chọn theo hợp đồng nghiệp vụ**, không phải hành vi mặc định của `URLEncoder`.
- **URL encoding không thay thế xác thực dữ liệu và các biện pháp bảo vệ XSS, SQL injection hoặc bảo mật truyền tải.**

### Nguồn chính thức

- [Java SE 26 — `URLEncoder.encode(String, Charset)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URLEncoder.html): ký tự an toàn, dấu cách, UTF-8, quy tắc byte/`%HH`, xử lý malformed, overload từ Java 10.
- [Java SE 26 — `URLDecoder.decode(String, Charset)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URLDecoder.html): quy tắc giải mã `+`/`%HH`, charset, ngoại lệ, overload từ Java 10.
- [Java SE 26 — `StandardCharsets.UTF_8`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html): charset UTF-8 tiêu chuẩn.
- [Java SE 26 — `Normalizer`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html): chuẩn hóa Unicode theo NFC và các dạng khác.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): bối cảnh charset mặc định; vì sao vẫn nên truyền charset tường minh theo giao thức.
