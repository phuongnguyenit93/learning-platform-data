# Khoảng trắng, dấu cộng và ký tự phần trăm trong mã hóa dữ liệu biểu mẫu (Java 10+)

## 1. Mục tiêu bài học

Khi trình duyệt hoặc ứng dụng gửi dữ liệu biểu mẫu theo định dạng **`application/x-www-form-urlencoded`**, các ký tự trong tên trường và giá trị **không được giữ nguyên hoàn toàn**. Ba ký tự dễ gây nhầm lẫn nhất là **khoảng trắng (` `)**, **dấu cộng (`+`)** và **dấu phần trăm (`%`)**.

Quy tắc trọng tâm:

| Ký tự dữ liệu ban đầu | Biểu diễn sau *form encoding* UTF-8 | Giải mã theo *form decoding* |
| --- | --- | --- |
| Khoảng trắng ASCII ` ` | `+` | `+` trong dữ liệu mã hóa → khoảng trắng |
| Dấu cộng thật `+` | `%2B` | `%2B` → dấu cộng thật |
| Dấu phần trăm thật `%` | `%25` | `%25` → dấu phần trăm thật |

Ví dụ đầu tiên:

~~~java
String encoded = URLEncoder.encode("A+B 100%", StandardCharsets.UTF_8);
System.out.println(encoded); // A%2BB+100%25

String decoded = URLDecoder.decode(encoded, StandardCharsets.UTF_8);
System.out.println(decoded); // A+B 100%
~~~

Đây là **đoạn mã minh họa** trong một phương thức, cần import `java.net.URLEncoder`, `java.net.URLDecoder` và `java.nio.charset.StandardCharsets`. Một chương trình đầy đủ có `main` nằm ở mục 8.

Sau bài học, bạn sẽ:
1. Hiểu đúng vai trò của **`+`** và **`%HH`** trong form encoding.
2. Phân biệt khoảng trắng đã mã hóa với dấu cộng **vốn có trong dữ liệu gốc**.
3. Dùng `URLEncoder.encode(String, Charset)` và `URLDecoder.decode(String, Charset)` của **Java 10+** để tránh phụ thuộc bảng mã mặc định.
4. Giải thích kết quả mã hóa UTF-8 của tiếng Việt và một số ký tự đặc biệt.
5. Ghép và đọc các cặp `key=value` mà không phá vỡ dấu `&` hoặc `=` nằm trong giá trị.
6. Tránh lỗi **mã hóa hai lần**, **giải mã hai lần**, dùng nhầm API cho đường dẫn URL và xử lý `%` sai cú pháp.
7. Biết khi nào form encoding phù hợp với HTTP form body hoặc các query parameter có hợp đồng form-style.

**Phiên bản:** `URLEncoder`/`URLDecoder` là các lớp có từ lâu trong Java. Hai overload nhận trực tiếp một đối tượng `Charset` — `encode(String, Charset)` và `decode(String, Charset)` — được giới thiệu từ **Java 10**, vẫn được hỗ trợ trong Java hiện đại. Ví dụ chạy bằng **JDK 17+** và không dùng API đã lỗi thời.

## 2. Vì sao biểu mẫu không giữ nguyên dấu cách?

Với form encoding, một chuỗi dữ liệu phải có thể đặt trong định dạng dạng:

~~~text
name=value&other=value2
~~~

Trong định dạng này:
- **`=`** phân cách **tên trường** và **giá trị**.
- **`&`** phân cách các **cặp trường**.
- Các ký tự có ý nghĩa đặc biệt trong dữ liệu gốc phải được mã hóa khi nằm **bên trong tên hoặc giá trị**.
- Khoảng trắng ASCII được form encoding quy định thành **dấu cộng `+`**.

Ví dụ giá trị người dùng nhập:

~~~text
cà phê sữa
~~~

Khi mã hóa bằng UTF-8, các khoảng trắng trở thành dấu `+`, còn chữ tiếng Việt có dấu được chuyển thành các byte UTF-8 rồi viết dưới dạng `%HH`.

Mỗi `%HH` là một **byte**, trong đó `HH` gồm hai chữ số hệ thập lục phân. Một ký tự Unicode có thể cần **nhiều byte**, nên một ký tự có dấu có thể tạo nhiều cụm `%HH`. Đừng nhầm một cụm `%HH` với một ký tự Unicode độc lập.

**Đây là form encoding, không phải mọi cách biểu diễn URL.** Trong các phần khác của URI như path hoặc fragment, cú pháp và ý nghĩa của dấu `+` có thể khác. Vì vậy `URLEncoder` dù có tên “URL” thực chất được tài liệu Java mô tả là tiện ích dành cho định dạng **`application/x-www-form-urlencoded`**.

## 3. Quy tắc thứ nhất: khoảng trắng ASCII thành `+`

~~~java
System.out.println(URLEncoder.encode("a b", StandardCharsets.UTF_8));
// a+b

System.out.println(URLEncoder.encode("a  b", StandardCharsets.UTF_8));
// a++b

System.out.println(URLDecoder.decode("a+b", StandardCharsets.UTF_8));
// a b

System.out.println(URLDecoder.decode("a++b", StandardCharsets.UTF_8));
// a  b
~~~

Đây là **đoạn minh họa** trong một phương thức với các import thích hợp.

Điều cần chú ý:
- Một dấu cách ASCII `U+0020` trở thành **một dấu `+`**.
- Hai dấu cách liền nhau trở thành **hai dấu `+`**.
- Khi dùng **`URLDecoder` cho form-encoded text**, mỗi dấu `+` được diễn giải là **khoảng trắng**.
- Dấu `+` nhìn thấy trong **văn bản đã mã hóa** không có nghĩa chắc chắn người dùng nhập dấu cộng.

### Có thể dùng `%20` thay `+` không?

`URLDecoder` cũng hiểu chuỗi escape `%20` là byte `0x20`, tương ứng khoảng trắng ASCII trong UTF-8:

~~~java
System.out.println(URLDecoder.decode("a%20b", StandardCharsets.UTF_8));
// a b
~~~

Tuy nhiên, **`URLEncoder.encode` của Java cho form encoding sẽ tạo dấu `+` cho khoảng trắng ASCII**, không chọn `%20` như cách một số bộ mã hóa URI chung biểu diễn dấu cách.

**Cẩn thận với khoảng trắng Unicode:** các ký tự như *non-breaking space* (`U+00A0`) hoặc những khoảng trắng khác không phải ASCII `U+0020` không mặc nhiên chuyển thành `+`. Chúng được xử lý qua bước mã hóa ký tự thành byte, rồi thành `%HH`. Không nên xóa hoặc thay mọi loại khoảng trắng chỉ vì form encoding có quy tắc cho ASCII space.

## 4. Quy tắc thứ hai: dấu cộng thật `+` thành `%2B`

Đây là lỗi logic phổ biến: nhiều người thấy dấu `+` trong chuỗi dữ liệu và tưởng rằng có thể giữ nguyên nó khi gửi form.

Ví dụ người dùng nhập một biểu thức toán:

~~~text
1+2
~~~

Nếu gửi thẳng `value=1+2` và bên nhận giải mã theo form encoding, dấu `+` sẽ thành khoảng trắng:

~~~java
System.out.println(URLDecoder.decode("1+2", StandardCharsets.UTF_8));
// 1 2
~~~

**Cách đúng:** mã hóa **dấu cộng thật** thành `%2B` trước khi đưa vào tên/giá trị biểu mẫu:

~~~java
String encoded = URLEncoder.encode("1+2", StandardCharsets.UTF_8);
System.out.println(encoded); // 1%2B2

String decoded = URLDecoder.decode(encoded, StandardCharsets.UTF_8);
System.out.println(decoded); // 1+2
~~~

Điều này cho ra bảng phân biệt:

| Chuỗi được gửi theo form-style | Kết quả `URLDecoder.decode(..., UTF_8)` |
| --- | --- |
| `a+b` | `a b` |
| `a%2Bb` | `a+b` |
| `a%20b` | `a b` |
| `a%2Bb+c` | `a+b c` |
| `%2B` | `+` |
| `+` | Một khoảng trắng ASCII |

**Không tự thay `+` thành dấu cách trước khi giải mã** rồi tiếp tục dùng một bộ giải mã khác. Để `URLDecoder` xử lý đúng cả hai trường hợp `+` và `%2B` trong **một lần giải mã**. Phần mã hóa `%2B` cần được giữ nguyên cho tới lúc giải mã; sau khi biến thành dấu cộng thật thì không được giải mã lần thứ hai.

### Dấu cộng trong URI thông thường có phải lúc nào cũng là khoảng trắng?

**Không.** Quy tắc `+` → khoảng trắng là quy tắc của **`application/x-www-form-urlencoded`** (và cách nhiều hệ thống xử lý query parameters theo form-style). Trong các thành phần URI khác hoặc với một giao thức không sử dụng quy ước form-style, dấu `+` có thể là **ký tự cộng nguyên nghĩa**.

Đừng gọi `URLDecoder.decode` trên toàn bộ địa chỉ URL một cách máy móc. Hãy chọn parser theo **thành phần URI** và **hợp đồng định dạng** của hệ thống.

## 5. Quy tắc thứ ba: dấu phần trăm thật `%` thành `%25`

Trong chuỗi form-encoded, `%` báo hiệu **một byte đã được viết thành cặp chữ số hex**. Vì vậy, nếu dữ liệu gốc chứa chính dấu phần trăm, nó phải được escape:

~~~java
System.out.println(URLEncoder.encode("100%", StandardCharsets.UTF_8));
// 100%25

System.out.println(URLDecoder.decode("100%25", StandardCharsets.UTF_8));
// 100%
~~~

Tại sao là `%25`?

- Dấu `%` có mã byte ASCII (và UTF-8) là **0x25**.
- Khi cần viết chính byte đó trong form-encoded text, ta biểu diễn nó bằng **`%` + `25`**.
- `URLDecoder` đọc `%25` và khôi phục lại dấu `%`.

### Dấu `%` nằm trong dữ liệu không giống dấu `%` mở đầu escape

~~~text
Dữ liệu gốc:       20% giảm giá
Mã hóa form:       20%25+gi%E1%BA%A3m+gi%C3%A1
Giải mã:           20% giảm giá
~~~

Các cụm `%E1%BA%A3` và `%C3%A1` đến từ byte UTF-8 của chữ tiếng Việt, còn `%25` đến từ **dấu phần trăm thật**.

### `%` sai cú pháp có thể gây ngoại lệ

~~~java
try {
    URLDecoder.decode("100%", StandardCharsets.UTF_8);
} catch (IllegalArgumentException ex) {
    System.out.println("invalid percent escape");
}
~~~

Kết quả:

~~~text
invalid percent escape
~~~

Chuỗi `"100%"` không phải form-encoded text hợp lệ để giải mã bởi `%` không được theo sau bởi **hai chữ số hex**. Những chuỗi như `"%2"` hoặc `"%GG"` cũng không phải escape byte hợp lệ.

**Lưu ý về byte không hợp lệ:** khác với một escape **sai cú pháp**, các chuỗi `%HH` có chữ số hex hợp lệ nhưng tạo byte **không hợp lệ theo UTF-8** có thể được thay thế bằng ký tự replacement khi `URLDecoder.decode(..., UTF_8)` giải mã. Không nên coi việc không ném ngoại lệ là bằng chứng dữ liệu đầu vào đúng encoding. Nếu cần xác thực UTF-8 nghiêm ngặt, hãy có bước kiểm định phù hợp.

## 6. Một `%HH` tương ứng một byte; tiếng Việt cần UTF-8

Mã hóa form bao gồm **hai quá trình liên tiếp**:
1. Biến các ký tự ngoài nhóm được giữ nguyên thành **byte theo `Charset`**, thường là UTF-8.
2. Viết mỗi byte cần escape thành `%HH`.

Ví dụ:

~~~java
String original = "cà phê";
String encoded = URLEncoder.encode(original, StandardCharsets.UTF_8);

System.out.println(encoded); // c%C3%A0+ph%C3%AA
System.out.println(URLDecoder.decode(encoded, StandardCharsets.UTF_8));
// cà phê
~~~

Giải thích:
- `c`, `a`, `p`, `h` và các ký tự chữ Latin ASCII được giữ nguyên.
- Chữ `à` có byte UTF-8 `C3 A0`, trở thành `%C3%A0`.
- Khoảng trắng ASCII trở thành `+`.
- Chữ `ê` có byte UTF-8 `C3 AA`, trở thành `%C3%AA`.

Nếu bên gửi mã hóa theo UTF-8 nhưng bên nhận giải mã bằng một charset khác, chuỗi tiếng Việt có thể bị sai nội dung. Vì vậy phải nhất quán bảng mã ở hai phía.

### Quy tắc ký tự được giữ nguyên bởi `URLEncoder`

Theo tài liệu Java API, nhóm ký tự thường được giữ nguyên là:
- `a`–`z`, `A`–`Z`, `0`–`9`;
- dấu chấm `.`, dấu gạch ngang `-`, dấu sao `*` và dấu gạch dưới `_`.

Một số ký tự thông dụng khác phải escape:

| Ký tự trong value | Kết quả UTF-8 form encoding |
| --- | --- |
| `/` | `%2F` |
| `?` | `%3F` |
| `&` | `%26` |
| `=` | `%3D` |
| `#` | `%23` |
| `+` | `%2B` |
| `%` | `%25` |
| `~` | `%7E` |
| Khoảng trắng ASCII | `+` |

Đây là nhóm quy tắc **của Java `URLEncoder` cho HTML form encoding**, không phải danh sách “ký tự phải escape trong mọi thành phần URL” của RFC 3986.

## 7. Java 10: dùng overload nhận `Charset`

Trong Java hiện đại, cách viết khuyến nghị cho form encoding là:

~~~java
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

String encoded = URLEncoder.encode(value, StandardCharsets.UTF_8);
String decoded = URLDecoder.decode(encoded, StandardCharsets.UTF_8);
~~~

`StandardCharsets.UTF_8` là một đối tượng `Charset` được cung cấp sẵn.

| Cách gọi | Trạng thái/ý nghĩa |
| --- | --- |
| `URLEncoder.encode(s, StandardCharsets.UTF_8)` | **Java 10+**, chọn UTF-8 qua `Charset` trực tiếp |
| `URLDecoder.decode(s, StandardCharsets.UTF_8)` | **Java 10+**, chọn UTF-8 qua `Charset` trực tiếp |
| `URLEncoder.encode(s, "UTF-8")` | Overload cũ với tên charset dạng `String`; vẫn dùng được |
| `URLDecoder.decode(s, "UTF-8")` | Overload cũ với tên charset dạng `String`; vẫn dùng được |
| `URLEncoder.encode(s)` | Overload không chỉ định encoding đã **deprecated**, phụ thuộc charset mặc định |
| `URLDecoder.decode(s)` | Overload không chỉ định encoding đã **deprecated**, phụ thuộc charset mặc định |

Ưu điểm của overload `Charset`:
- Loại bỏ việc tự gõ tên charset dạng chuỗi.
- Không phụ thuộc cấu hình charset mặc định.
- Không yêu cầu xử lý checked `UnsupportedEncodingException` chỉ để dùng hằng UTF-8 chuẩn.
- Diễn đạt rõ **encoding contract** với cả client và server.

**Cảnh báo:** Hai phương thức nhận `Charset` ném `NullPointerException` nếu chuỗi đầu vào hoặc charset là `null`. `URLEncoder` không phải phương thức biến `null` thành chuỗi rỗng. Hãy xử lý sự vắng mặt của dữ liệu theo hợp đồng nghiệp vụ trước khi mã hóa.

## 8. Chương trình Java 17+ hoàn chỉnh

Tạo tệp **FormSpacePlusPercentDemo.java**:

~~~java
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class FormSpacePlusPercentDemo {

    static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    static String decode(String value) {
        return URLDecoder.decode(value, StandardCharsets.UTF_8);
    }

    // Mã hóa tên và giá trị RIÊNG, không mã hóa dấu = phân cách.
    static String pair(String key, String value) {
        return encode(key) + "=" + encode(value);
    }

    // Parser minh họa cho các cặp form đơn giản.
    // Hỗ trợ lặp tên trường, giá trị rỗng và dấu = trong value.
    static Map<String, List<String>> parseForm(String form) {
        var result = new LinkedHashMap<String, List<String>>();

        if (form.isEmpty()) {
            return result;
        }

        // Tách trên dấu & CHƯA giải mã.
        for (String field : form.split("&", -1)) {
            int equals = field.indexOf('=');

            String rawKey = equals < 0
                    ? field
                    : field.substring(0, equals);

            String rawValue = equals < 0
                    ? ""
                    : field.substring(equals + 1);

            String key = decode(rawKey);
            String value = decode(rawValue);

            result.computeIfAbsent(key, ignored -> new ArrayList<>())
                    .add(value);
        }

        return result;
    }

    public static void main(String[] args) {
        // Ba quy tắc dễ nhầm nhất.
        System.out.println("space encoded = " + encode("a b"));
        System.out.println("plus encoded = " + encode("a+b"));
        System.out.println("percent encoded = " + encode("a%b"));

        System.out.println("raw plus decoded = " + decode("a+b"));
        System.out.println("escaped plus decoded = " + decode("a%2Bb"));
        System.out.println("escaped percent decoded = " + decode("a%25b"));

        // Tiếng Việt được mã hóa qua byte UTF-8.
        System.out.println("unicode encoded = " + encode("cà phê"));
        System.out.println("unicode decoded = "
                + decode(encode("cà phê")));

        // Escape dấu = và & nếu chúng là DỮ LIỆU.
        String specialField = pair("note", "x=y&z");
        System.out.println("encoded separators = " + specialField);
        System.out.println("decoded separators = "
                + parseForm(specialField).get("note").get(0));

        // Tạo form với dấu + thật, dấu %, tên trường lặp và value rỗng.
        String form = pair("q", "a+b 100%")
                + "&" + pair("tag", "cà phê")
                + "&" + pair("tag", "trà")
                + "&" + pair("empty", "");

        Map<String, List<String>> parsed = parseForm(form);

        System.out.println("form q raw = "
                + form.substring(0, form.indexOf('&')));
        System.out.println("form q decoded = "
                + parsed.get("q").get(0));
        System.out.println("form tags = " + parsed.get("tag"));
        System.out.println("form empty value = "
                + parsed.get("empty").get(0).isEmpty());

        // Chứng minh %25 không được decode thêm lần hai.
        System.out.println("encoded literal escape = " + encode("%2B"));
        System.out.println("decode once = " + decode("%252B"));

        // Dấu % đơn độc là escape sai cú pháp.
        try {
            decode("100%");
        } catch (IllegalArgumentException ex) {
            System.out.println("malformed percent = rejected");
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac FormSpacePlusPercentDemo.java
java FormSpacePlusPercentDemo
~~~

**Đầu ra chính xác:**

~~~text
space encoded = a+b
plus encoded = a%2Bb
percent encoded = a%25b
raw plus decoded = a b
escaped plus decoded = a+b
escaped percent decoded = a%b
unicode encoded = c%C3%A0+ph%C3%AA
unicode decoded = cà phê
encoded separators = note=x%3Dy%26z
decoded separators = x=y&z
form q raw = q=a%2Bb+100%25
form q decoded = a+b 100%
form tags = [cà phê, trà]
form empty value = true
encoded literal escape = %252B
decode once = %2B
malformed percent = rejected
~~~

### Giải thích kết quả

1. `encode("a b")` tạo `a+b`: khoảng trắng ASCII được biểu diễn bởi `+`.
2. `encode("a+b")` tạo `a%2Bb`: dấu cộng là dữ liệu gốc, phải được giữ bằng `%2B`.
3. `encode("a%b")` tạo `a%25b`: dấu phần trăm thật trở thành `%25`.
4. `decode("a+b")` là `a b`, trong khi `decode("a%2Bb")` là `a+b`. **Đây là hai chuỗi mã hóa khác nhau**.
5. `cà phê` được chuyển qua UTF-8, trong đó `à` trở thành `%C3%A0`, `ê` thành `%C3%AA`.
6. `pair("note","x=y&z")` chỉ mã hóa **dữ liệu**, nên các dấu `=` và `&` bên trong value thành `%3D` và `%26`.
7. Parser tách các cặp trên **dấu `&` chưa giải mã**, rồi tách **dấu `=` đầu tiên**. Vì thế `x=y&z` vẫn được khôi phục đúng khi parse.
8. `tag` xuất hiện hai lần và được lưu thành `List<String>`, tránh làm mất giá trị khi một trường có nhiều phần tử.
9. Giá trị rỗng trong `empty=` được giữ là chuỗi rỗng, không bị bỏ mất vì `split(...,-1)` cho phép giữ phần rỗng.
10. Chuỗi gốc `%2B` khi encode thành `%252B`, decode một lần mới trở lại `%2B`, không tự biến thành `+`.
11. `decode("100%")` ném `IllegalArgumentException` do escape không đủ hai chữ số hex; chương trình bắt lỗi và in một thông điệp xác định, không lệ thuộc nội dung exception của JDK.

Đây là **chương trình hoàn chỉnh, biên dịch được**, không gửi yêu cầu mạng. Cấu trúc `parseForm` là parser minh họa cho các cặp đơn giản; khi xử lý HTTP thật hãy ưu tiên parser của framework hoặc thư viện hỗ trợ đầy đủ yêu cầu của giao thức và giới hạn dữ liệu.

## 9. Ghép dữ liệu biểu mẫu: encode từng key và value

Giả sử form có hai trường:

~~~text
q = A+B 100%
note = x=y&z
~~~

Nếu nối chuỗi dữ liệu thô thành:

~~~text
q=A+B 100%&note=x=y&z
~~~

thì sẽ có nhiều lỗi:
- `+` trong `A+B` có thể bị giải mã thành khoảng trắng.
- `%` trong `100%` là escape chưa hợp lệ.
- `&` bên trong `x=y&z` có thể bị hiểu nhầm là bắt đầu trường mới.
- Dấu `=` bên trong value không phải lúc nào cũng được giữ nguyên bởi những parser tự viết không đúng.

**Cách đúng:** mã hóa **tên** và **giá trị** của từng trường; chỉ sau đó mới nối bằng các delimiter `=` và `&`:

~~~java
String body = URLEncoder.encode("q", StandardCharsets.UTF_8)
        + "="
        + URLEncoder.encode("A+B 100%", StandardCharsets.UTF_8)
        + "&"
        + URLEncoder.encode("note", StandardCharsets.UTF_8)
        + "="
        + URLEncoder.encode("x=y&z", StandardCharsets.UTF_8);

System.out.println(body);
// q=A%2BB+100%25&note=x%3Dy%26z
~~~

Đây là đoạn minh họa trong phương thức. Nếu gọi `URLEncoder.encode` **cho toàn bộ chuỗi form đã ghép**, cả các dấu `=`/`&` dùng làm delimiter cấu trúc sẽ bị escape; phía nhận sẽ không còn phân tách được các trường như mong muốn.

### Dấu `+` có hai ý nghĩa tùy giai đoạn

Hãy tách rõ:

~~~text
Giá trị gốc:      A+B C
Mã hóa value:     A%2BB+C
Đặt vào form:     q=A%2BB+C
Giải mã value:    A+B C
~~~

- `%2B` là dấu `+` **thuộc dữ liệu gốc**.
- `+` sau `B` là **khoảng trắng** thuộc dữ liệu gốc.
- Không được đánh đồng chúng ở bước xử lý dữ liệu mã hóa.

## 10. Parse đúng thứ tự: tách form trước, giải mã sau

Giả sử có một form-encoded string:

~~~text
note=x%3Dy%26z&name=A%2BB+C
~~~

Trình tự xử lý đúng:
1. Tách các cặp bằng dấu `&` **chưa giải mã**.
2. Trong từng cặp, tìm dấu `=` **chưa giải mã** đầu tiên làm ranh giới key/value.
3. Dùng `URLDecoder.decode(..., UTF_8)` riêng cho **key** và **value**.
4. Thực hiện xác thực nghiệp vụ, xử lý tên trường lặp và giới hạn đầu vào theo schema.

Ví dụ một cặp:

~~~java
String encodedValue = "x%3Dy%26z";
System.out.println(URLDecoder.decode(
        encodedValue, StandardCharsets.UTF_8));
// x=y&z
~~~

**Sai nếu giải mã toàn bộ form trước rồi mới tách:** khi `%26` biến thành `&`, parser có thể hiểu nhầm dấu `&` vốn là **nội dung của value** thành **delimiter cấu trúc**. Khi `%3D` trở thành `=`, cách tách key/value tự viết cũng có thể sai.

**Sử dụng nhiều giá trị cùng tên:** một form có thể gồm `tag=java&tag=io`. Nếu dùng `Map<String,String>` với mỗi key chỉ một value, bạn có thể vô tình ghi đè một `tag`. Hãy quyết định rõ hợp đồng: giữ nhiều value trong `Map<String,List<String>>`, hoặc chỉ nhận một value và báo lỗi khi trùng.

**Lưu ý về parser minh họa:** các câu hỏi như cặp không có dấu `=`, dấu `&` thừa, tham số trùng tên hoặc chuỗi `key=` rỗng cần được quy định trong hệ thống. Ví dụ ở mục 8 chọn giá trị rỗng cho cặp thiếu `=`; không khẳng định mọi framework HTTP áp dụng đúng chính sách ấy.

## 11. Phân biệt form encoding với đường dẫn URI và các thành phần khác

Tên class `URLEncoder` có thể gây hiểu nhầm. **Đừng dùng `URLEncoder.encode` để mã hóa nguyên cả URL**:

~~~java
String entireUrl = "https://example.com/a b?q=x+y";
// URLEncoder.encode(entireUrl, StandardCharsets.UTF_8)
// sẽ escape cả : / ? = & ... và KHÔNG phải cách sửa URL tổng thể.
~~~

Đây là đoạn minh họa.

### Form-encoded body

Khi gửi một HTTP form body:

~~~text
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

q=A%2BB+C&note=100%25
~~~

Dấu `+` trong `q` và dấu `%` trong `note` được diễn giải theo form encoding.

Với **Java 17+**, có thể xây dựng request mà **chưa gửi**:

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

String body = "q=" + URLEncoder.encode(
        "A+B C", StandardCharsets.UTF_8);

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.invalid/submit"))
        .header("Content-Type",
                "application/x-www-form-urlencoded; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                body, StandardCharsets.UTF_8))
        .build();
~~~

Đây là **đoạn minh họa trong phương thức**, không thực hiện `send`. `example.invalid` là tên miền ví dụ, không phải endpoint thực. `HttpClient` thuộc Java 11+; còn overload `URLEncoder.encode(String,Charset)` thuộc Java 10+.

### Query parameter theo quy ước form-style

Nhiều hệ thống dùng quy tắc form encoding khi truyền query parameters:

~~~java
String queryValue = URLEncoder.encode(
        "A+B C", StandardCharsets.UTF_8);

String url = "https://example.invalid/search?q=" + queryValue;
// q=A%2BB+C
~~~

Trong trường hợp này, phần `q` được mã hóa đúng theo giao kèo **form-style query parameter**. Nhưng URI path, fragment và các thành phần khác **có quy tắc escaping riêng**; đừng áp dụng `+` → khoảng trắng một cách tổng quát cho toàn bộ URI.

Nếu dùng `java.net.URI`, hãy phân biệt:
- `uri.getRawQuery()`: dạng query **chưa decode percent escapes**, phù hợp hơn khi bạn thực sự cần xử lý percent escapes của query theo form-style.
- `uri.getQuery()`: dạng query đã xử lý percent escapes theo ngữ nghĩa của `URI`. Tránh tiếp tục đưa chuỗi này vào một bộ form decoder mà không hiểu tác động của **giải mã lặp**.

**Ưu tiên thư viện HTTP/framework đáng tin cậy** để quản lý query parameters khi có thể, vì chúng thường cung cấp API xây dựng URI và phân tích tham số đúng ngữ cảnh hơn việc tự nối/giải mã chuỗi.

## 12. Mã hóa hai lần và giải mã hai lần: vì sao dễ mất dấu `+`?

Ví dụ dữ liệu gốc chính là bốn ký tự:

~~~text
%2B
~~~

Dữ liệu này **không phải dấu cộng**; đó là một chuỗi ký tự chứa dấu phần trăm, chữ số 2 và chữ B.

Khi encode:

~~~java
System.out.println(URLEncoder.encode("%2B", StandardCharsets.UTF_8));
// %252B
~~~

Nếu decode **một lần**:

~~~java
System.out.println(URLDecoder.decode("%252B", StandardCharsets.UTF_8));
// %2B
~~~

Nếu decode **lần thứ hai**:

~~~java
System.out.println(URLDecoder.decode("%2B", StandardCharsets.UTF_8));
// +
~~~

Lúc này thông tin gốc đã bị biến đổi: `%2B` (chuỗi dữ liệu) thành `+` (ký tự khác). Nếu code lại giải mã lần thứ ba trên dấu cộng vừa tạo, nó còn có thể bị biến thành **khoảng trắng**.

**Quy tắc an toàn:** tại mỗi ranh giới, hãy biết dữ liệu đang là **raw value** hay **encoded value**. Chỉ encode khi cần đặt raw value vào một thành phần form; chỉ decode một lần theo hợp đồng của nguồn. Không dùng nhiều lớp decoder chồng nhau không kiểm soát.

Lỗi này không chỉ ảnh hưởng hiển thị: dữ liệu có thể bị xử lý sai khi xác thực đường dẫn, chữ ký, filter, mã sản phẩm hoặc dữ liệu đầu vào ứng dụng. Nếu ứng dụng cần xử lý URL từ nguồn không tin cậy, hãy sử dụng một pipeline parse/normalize/validate được định nghĩa rõ và kiểm thử trường hợp có nhiều lớp escape.

### Vì sao thay tay bằng `String.replace` không đủ?

Một cách làm nguy hiểm:

~~~java
String encoded = raw.replace(" ", "+");
~~~

Nó **không xử lý dấu `+` gốc**, dấu `%`, dấu `&`, dấu `=`, hoặc ký tự Unicode. Khi đến phía nhận, thông tin có thể bị hiểu sai.

Một cách sai khác:

~~~java
String decoded = form.replace("+", " ");
~~~

Cách này chỉ xử lý dấu cộng nhưng **không giải mã `%2B`, `%25` và các byte UTF-8 `%HH`**. Vì thế, không dùng thay thế chuỗi đơn giản làm một bộ form encoder/decoder tổng quát.

**Dùng đúng `URLEncoder`/`URLDecoder` cho form fields**, và dùng parser chuyên dụng cho URI/HTTP khi dữ liệu nằm trong một ngữ cảnh phức tạp hơn.

## 13. Các lỗi thường gặp

### Lỗi 1 — Nối value thô có dấu `+` vào form

~~~text
Sai:  q=1+2
Đúng: q=1%2B2
~~~

Nếu phía nhận dùng form decoding, câu sai cho ra `1 2` thay vì `1+2`.

### Lỗi 2 — Gửi dấu phần trăm thô

~~~text
Sai:  discount=20%
Đúng: discount=20%25
~~~

Dấu `%` thô có thể khiến decoder coi phần còn lại là escape không hoàn chỉnh và ném `IllegalArgumentException`.

### Lỗi 3 — Coi mọi `+` trong URL là khoảng trắng

Quy tắc ấy thuộc định dạng form, không tự áp dụng cho path hoặc mọi phần của URI. Trước khi decode, phải biết đang xử lý **form body**, **form-style query value** hay **thành phần URI khác**.

### Lỗi 4 — Encode cả query string sau khi đã nối delimiter

Nếu encode `q=a+b&tag=java` như một giá trị duy nhất, các dấu `=` và `&` cấu trúc sẽ bị escape, làm mất dạng nhiều trường. Hãy encode riêng key/value trước, rồi mới ghép các cặp.

### Lỗi 5 — Decode toàn bộ form trước khi split

`%26` nằm trong value sẽ trở thành dấu `&` và có thể bị chia nhầm thành trường mới. Tách theo delimiter raw trước, decode từng thành phần sau.

### Lỗi 6 — Decode hai lần

`%252B` decode một lần thành `%2B`; decode lần nữa thành `+`. Kết quả không còn đúng với dữ liệu gốc ban đầu.

### Lỗi 7 — Dùng overload không chỉ định charset

`URLEncoder.encode(String)` và `URLDecoder.decode(String)` không chỉ định encoding đã bị deprecated và phụ thuộc charset mặc định. Trong Java 10+, hãy dùng overload nhận `StandardCharsets.UTF_8` rõ ràng.

### Lỗi 8 — Cho rằng `%HH` luôn là một ký tự Unicode

Một `%HH` đại diện cho **một byte**. Ký tự `à` trong UTF-8 cần `%C3%A0`, không phải một escape duy nhất.

### Lỗi 9 — Kỳ vọng decoder chặn mọi dữ liệu mã hóa sai

Decoder có thể báo lỗi với escape **không đúng cú pháp**, nhưng byte hợp lệ về dạng `%HH` vẫn có thể là chuỗi byte lỗi theo charset đã chọn và được thay bằng ký tự thay thế. Cần xác thực dữ liệu sau decode hoặc dùng bộ giải mã nghiêm ngặt khi hệ thống yêu cầu.

### Lỗi 10 — Không xác thực dữ liệu đã decode

Mã hóa không phải bước **kiểm tra tính hợp lệ**. Một value chứa ký tự `&`, `/`, khoảng trắng hoặc emoji có thể được chuyển qua form encoding hợp lệ, nhưng nó vẫn cần được kiểm tra theo định dạng nghiệp vụ sau khi decode.

### Lỗi 11 — Nhầm giá trị rỗng với trường không xuất hiện

`name=` biểu thị **có trường `name` nhưng giá trị rỗng** trong nhiều giao thức form; một yêu cầu không hề có trường `name` là một trường hợp khác. Parser và nghiệp vụ phải quyết định cách phân biệt. `URLDecoder.decode("")` trả về chuỗi rỗng, không phải `null`.

### Lỗi 12 — Dựa vào thứ tự/định dạng do framework không cam kết

Các framework có thể chuẩn hóa, giải mã và trả dữ liệu theo API riêng. Không tự giải mã lặp chuỗi đã được framework chuyển thành raw value. Nếu cần so sánh chữ ký hoặc log byte-level, phải chỉ rõ phần dữ liệu được ký hoặc ghi lại là **encoded form** hay **decoded value**.

## 14. Checklist xây dựng form encoding an toàn

Trước khi triển khai, hãy lần lượt trả lời:

1. **Nguồn dữ liệu là gì?** Raw string từ ứng dụng, hay chuỗi đã được mã hóa bởi framework?
2. **Dữ liệu sẽ đặt ở đâu?** HTTP form body, query parameter theo form-style, URI path hay nội dung khác?
3. **Charset đã thống nhất chưa?** Với text thông thường, hãy sử dụng `StandardCharsets.UTF_8`.
4. **Tên và value đã được encode riêng chưa?** Chỉ ghép `=` và `&` sau khi encode.
5. **Khoảng trắng được encode thành `+` chưa?** Và dấu cộng gốc thành `%2B` chưa?
6. **Dấu `%` trong raw data đã thành `%25` chưa?** Không truyền percent escape thô nếu nó là dữ liệu gốc.
7. **Phía nhận đang parse ở đúng tầng chưa?** Tách raw pairs trước khi decode từng key/value.
8. **Chỉ decode một lần chưa?** Tránh biến `%252B` thành dấu `+` ngoài ý muốn.
9. **Có xử lý tên trường lặp, giá trị rỗng và dữ liệu sai cú pháp không?** Đừng âm thầm làm mất bản ghi.
10. **Đã kiểm tra dữ liệu nghiệp vụ sau decode chưa?** Charset và form decoder không thay thế validation.
11. **Đã có giới hạn kích thước và bộ lọc phù hợp chưa?** Đầu vào không tin cậy có thể rất dài hoặc chứa nhiều chuỗi escape.
12. **Đã kiểm thử tiếng Việt và ba ký tự đặc biệt chưa?** Các ca tối thiểu: `"a b"`, `"a+b"`, `"100%"`, `"cà phê"`, `"x=y&z"`.

## 15. Tự kiểm tra kiến thức

**Câu 1.** `URLEncoder.encode("a b", UTF_8)` trả chuỗi nào?

**Đáp án:** `a+b`. Khoảng trắng ASCII được encode thành dấu `+` trong form encoding.

**Câu 2.** `URLEncoder.encode("a+b", UTF_8)` trả chuỗi nào?

**Đáp án:** `a%2Bb`. Dấu cộng là dữ liệu gốc nên phải encode thành `%2B`.

**Câu 3.** `URLEncoder.encode("100%", UTF_8)` trả gì?

**Đáp án:** `100%25`. Dấu `%` thật phải thành `%25`.

**Câu 4.** `URLDecoder.decode("x+y", UTF_8)` cho kết quả gì?

**Đáp án:** `x y`, vì dấu cộng trong form-encoded text có nghĩa là khoảng trắng ASCII.

**Câu 5.** `URLDecoder.decode("x%2By", UTF_8)` cho kết quả gì?

**Đáp án:** `x+y`, vì `%2B` là byte của dấu cộng thật.

**Câu 6.** Vì sao `URLDecoder.decode("100%", UTF_8)` có thể ném ngoại lệ?

**Đáp án:** Dấu `%` không đi kèm hai chữ số hex để tạo escape `%HH`. Đây là lỗi cú pháp percent encoding.

**Câu 7.** Mã hóa `"cà phê"` theo UTF-8 form encoding là gì?

**Đáp án:** `c%C3%A0+ph%C3%AA`. Các chữ có dấu được biểu diễn bằng byte UTF-8, còn dấu cách thành `+`.

**Câu 8.** Tại sao không giải mã toàn bộ chuỗi `note=x%3Dy%26z` trước khi xác định các trường?

**Đáp án:** `%26` sẽ thành `&` thuộc dữ liệu của value, dễ bị parser nhầm thành dấu phân tách trường. Nên tách cặp trên raw text rồi decode key/value.

**Câu 9.** Nếu input raw là chuỗi `%2B`, sau một lượt encode và một lượt decode phải nhận lại gì?

**Đáp án:** Encode thành `%252B`, rồi decode một lần trở lại **chuỗi `%2B`**. Không được decode tiếp thành dấu cộng.

**Câu 10.** `URLEncoder.encode(String, Charset)` thuộc phiên bản Java nào?

**Đáp án:** Java 10+, tương tự `URLDecoder.decode(String, Charset)`.

**Câu 11.** Có nên dùng `URLEncoder` để encode đường dẫn `/users/A B` nguyên khối không?

**Đáp án:** Không. `URLEncoder` là tiện ích form encoding và sẽ mã hóa cả dấu `/`. Dùng API xây dựng URI hoặc encoder dành cho từng path segment đúng hợp đồng.

**Câu 12.** Nếu một framework đã trả cho code chuỗi `A+B` **đã decode** từ `A%2BB`, có nên gọi `URLDecoder.decode("A+B")` lần nữa?

**Đáp án:** Không. Lượt decode thứ hai sẽ biến dấu cộng thật thành khoảng trắng, làm sai dữ liệu.

## 16. Ghi nhớ cuối bài

1. **Form encoding dùng `+` cho khoảng trắng ASCII**; đừng nhầm `+` trong encoded text với dấu cộng thật.
2. **Dấu cộng thật `+` phải encode thành `%2B`**; **dấu phần trăm thật `%` phải encode thành `%25`**.
3. **`%HH` biểu diễn một byte**, không nhất thiết một ký tự. Dùng UTF-8 thống nhất để hỗ trợ tiếng Việt và Unicode.
4. **`URLEncoder.encode(s, StandardCharsets.UTF_8)` và `URLDecoder.decode(s, StandardCharsets.UTF_8)` có từ Java 10**, giúp chỉ định charset bằng object thay vì charset mặc định.
5. **Encode từng key/value riêng**, sau đó mới ghép `=` và `&`; khi parse, tách theo delimiter raw **trước**, giải mã key/value **sau**.
6. **Không decode hai lần**, không dùng `URLDecoder` cho toàn bộ URL, path hoặc fragment một cách tùy tiện.
7. `URLDecoder` phát hiện nhiều dạng percent escape sai cú pháp nhưng **không thay thế bước xác thực encoding và dữ liệu nghiệp vụ**.
8. Ưu tiên API HTTP/framework theo ngữ cảnh cụ thể, và thử nghiệm các ca có khoảng trắng, `+`, `%`, dấu tiếng Việt, ký tự `&`/`=`, giá trị rỗng và tham số lặp.

**Tài liệu tham khảo chính thức còn áp dụng:**
- [Oracle Java SE 10 — `URLEncoder`, overload `encode(String, Charset)`](https://docs.oracle.com/javase/10/docs/api/java/net/URLEncoder.html).
- [Oracle Java SE 17 — `URLEncoder` và quy tắc form encoding](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html).
- [Oracle Java SE 17 — `URLDecoder`, plus và percent escapes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLDecoder.html).
- [Oracle Java SE 17 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).
