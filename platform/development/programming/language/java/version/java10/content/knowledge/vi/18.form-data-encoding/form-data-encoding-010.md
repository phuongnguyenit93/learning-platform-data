# Kiểm thử ký tự tiếng Việt, ký tự phân cách và dữ liệu rỗng khi mã hóa biểu mẫu

**Chủ đề:** Mã hóa dữ liệu biểu mẫu — Java 10 trở lên.

Khi gửi dữ liệu có dấu tiếng Việt, các ký tự như `+`, `&`, `=`, `?`, `#`, `/`, `%` hoặc các trường có giá trị rỗng, mã hóa sai có thể làm máy chủ đọc nhầm **giá trị thành nhiều tham số**, làm mất dấu, biến dấu cộng thành khoảng trắng, hoặc không phân biệt được **trường rỗng** với **trường hoàn toàn vắng mặt**. Bài học này cung cấp các ca kiểm thử có thể chạy thật bằng Java, theo đúng định dạng `application/x-www-form-urlencoded`.

Từ **Java 10**, có thể dùng `java.net.URLEncoder.encode(String, Charset)` và `java.net.URLDecoder.decode(String, Charset)`. Chỉ định `StandardCharsets.UTF_8` để kết quả nhất quán và phù hợp với phần lớn giao thức hiện đại. Các overload này **vẫn là API hiện hành**, không phải tính năng đã lỗi thời. Năm chương trình Java hoàn chỉnh dưới đây đã được biên dịch với `javac --release 10` và chạy đối chiếu stdout.

## 1. Mã hóa biểu mẫu khác với mã hóa một URL hoàn chỉnh

`URLEncoder` tạo **một thành phần khóa hoặc giá trị biểu mẫu** theo quy tắc `application/x-www-form-urlencoded`. Nó **không phải** phương thức tổng quát để mã hóa cả đường dẫn URL, cả chuỗi query, hay toàn bộ URL.

Ví dụ, muốn gửi cặp dữ liệu:

~~~text
Tên trường: name
Giá trị:    Hà Nội & Đà Nẵng
~~~

thì cần mã hóa phần **giá trị** theo UTF-8, giữ dấu `=` nối khóa–giá trị và dấu `&` nối **các trường** ở tầng xây dựng form:

~~~java
String value = URLEncoder.encode("Hà Nội & Đà Nẵng", StandardCharsets.UTF_8);
String body = "name=" + value;
~~~

Đây là **đoạn mã đặt trong một phương thức**, có import `URLEncoder` và `StandardCharsets`. Dấu `&` **nằm trong dữ liệu** phải được mã hóa thành `%26`, không được giữ nguyên như dấu phân tách hai trường.

Cần phân biệt ba tầng:

| Tầng | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| Dữ liệu ứng dụng | `"a&b"`, `"Hà Nội"` | Giữ nội dung gốc đúng Unicode |
| Thành phần đã mã hóa | `"a%26b"`, `"H%C3%A0+N%E1%BB%99i"` | `URLEncoder.encode(value, UTF_8)` |
| Body biểu mẫu | `"name=H%C3%A0+N%E1%BB%99i&tag=a%26b"` | Nối các cặp **đã mã hóa riêng** bằng `=` và `&` |

Với một HTTP POST form-encoded, phần thân thường được gửi với `Content-Type: application/x-www-form-urlencoded; charset=UTF-8`, và sau khi xây body dạng String có thể chuyển thành byte bằng `body.getBytes(StandardCharsets.UTF_8)`. Tùy framework, lớp HTTP client có thể tự mã hóa tham số; **không mã hóa thêm lần nữa** nếu client đã làm việc đó.

## 2. Quy tắc chính của `URLEncoder.encode(..., UTF_8)`

Các quy tắc từ Javadoc Java hiện hành:

- Chữ Latin không dấu `a–z`, `A–Z` và chữ số `0–9` được giữ nguyên.
- Bốn ký tự `.`, `-`, `*`, `_` được giữ nguyên.
- **Khoảng trắng U+0020** trở thành dấu cộng `+`.
- Các ký tự khác phải được chuyển thành byte theo charset đã chọn (ở đây UTF-8), rồi mỗi byte được biểu diễn bằng `%HH` với hai chữ số thập lục phân.
- Dấu cộng `+` là **dữ liệu gốc** phải thành `%2B` để không bị đọc nhầm thành khoảng trắng.
- Dấu `&` thành `%26`, dấu `=` thành `%3D`, dấu `?` thành `%3F`, dấu `#` thành `%23`, dấu `/` thành `%2F`, dấu `%` thành `%25`.
- **Chuỗi rỗng `""` được mã hóa thành chuỗi rỗng**, không thành `null`, dấu `+`, hoặc `%00`.
- `~` thường được giữ nguyên trong một số kiểu percent-encoding URL khác, nhưng **`URLEncoder` Java chuyển `~` thành `%7E`**. Đừng dùng tập ký tự an toàn của URI path để phỏng đoán kết quả của form-encoding.

Quy tắc giải mã đối ứng của `URLDecoder`: `+` trở thành khoảng trắng và `%HH` được đọc thành byte; các byte nhiều phần của cùng chuỗi escape được giải mã theo `Charset` đã cung cấp.

### Bảng vector kiểm thử quan trọng

| Dữ liệu gốc | Kết quả `URLEncoder.encode(input, UTF_8)` | Mục tiêu kiểm tra |
| --- | --- | --- |
| `Tiếng Việt` | `Ti%E1%BA%BFng+Vi%E1%BB%87t` | Dấu tiếng Việt, Unicode UTF-8, khoảng trắng |
| `Hà Nội` | `H%C3%A0+N%E1%BB%99i` | Dấu huyền, dấu nặng, khoảng trắng |
| `A🚀B` | `A%F0%9F%9A%80B` | Unicode ngoài BMP: 4 byte UTF-8 |
| `a b` | `a+b` | Khoảng trắng → `+` |
| `a+b` | `a%2Bb` | Dấu cộng thực → `%2B` |
| `a+b&c=d?e#f/g%h` | `a%2Bb%26c%3Dd%3Fe%23f%2Fg%25h` | Dữ liệu có nhiều dấu phân cách |
| `AZaz09-._*` | `AZaz09-._*` | Tập ký tự được giữ nguyên |
| `~` | `%7E` | Khác một số cơ chế mã hóa URI |
| Chuỗi rỗng `""` | Chuỗi rỗng `""` | Không tự tạo sentinel |
| `?` | `%3F` | Dấu mở query khi nằm trong dữ liệu |
| `#` | `%23` | Dấu phân tách fragment khi nằm trong dữ liệu |

Các giá trị ở bảng là **golden test vectors**: kết quả cụ thể phải khớp chính xác, không chỉ kiểm tra rằng một chương trình giải mã lại được dữ liệu ban đầu.

## 3. Chương trình chạy được 1 — Dấu tiếng Việt và Unicode ngoài BMP

Lưu đầy đủ tệp **`VietnameseFormEncodingDemo.java`**:

~~~java
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

public class VietnameseFormEncodingDemo {
    public static void main(String[] args) {
        String vietnamese = "Ti\u1EBFng Vi\u1EC7t";
        String encoded = URLEncoder.encode(vietnamese, StandardCharsets.UTF_8);

        System.out.println("encoded=" + encoded);
        System.out.println("matches=" +
                encoded.equals("Ti%E1%BA%BFng+Vi%E1%BB%87t"));
        System.out.println("roundtrip=" +
                vietnamese.equals(
                        URLDecoder.decode(encoded, StandardCharsets.UTF_8)));

        String phrase = "H\u00E0 N\u1ED9i";
        String encodedPhrase = URLEncoder.encode(phrase, StandardCharsets.UTF_8);
        System.out.println("city=" + encodedPhrase);
        System.out.println("city-roundtrip=" +
                phrase.equals(
                        URLDecoder.decode(encodedPhrase, StandardCharsets.UTF_8)));

        String emoji = "A\uD83D\uDE80B";
        String encodedEmoji = URLEncoder.encode(emoji, StandardCharsets.UTF_8);
        System.out.println("emoji=" + encodedEmoji);
        System.out.println("emoji-roundtrip=" +
                emoji.equals(
                        URLDecoder.decode(encodedEmoji, StandardCharsets.UTF_8)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 VietnameseFormEncodingDemo.java
java VietnameseFormEncodingDemo
~~~

**Stdout chính xác:**

~~~text
encoded=Ti%E1%BA%BFng+Vi%E1%BB%87t
matches=true
roundtrip=true
city=H%C3%A0+N%E1%BB%99i
city-roundtrip=true
emoji=A%F0%9F%9A%80B
emoji-roundtrip=true
~~~

Giải thích:

1. Java source dùng các Unicode escape cho các chữ có dấu và emoji để việc biên dịch không phụ thuộc vào cách terminal hiển thị tiếng Việt. Giá trị runtime tương ứng là `"Tiếng Việt"`, `"Hà Nội"` và `"A🚀B"`.
2. Chữ `ế` của `"Tiếng"` chuyển thành UTF-8 `E1 BA BF`, nên được mã hóa `%E1%BA%BF`; chữ `ệ` trong `"Việt"` thành `%E1%BB%87`. Khoảng trắng đứng giữa hai từ thành `+`.
3. Chữ `à` thành `%C3%A0`; chữ `ộ` thành `%E1%BB%99`.
4. Emoji `🚀` có code point U+1F680, mã UTF-8 `F0 9F 9A 80`; do đó có `%F0%9F%9A%80`.
5. Các phép so sánh `roundtrip=true` xác nhận việc giải mã bằng **cùng UTF-8** lấy lại chuỗi Unicode gốc. Dùng cả golden string và roundtrip giúp phát hiện sai bảng mã hoặc sai cách viết phần trăm.
6. Không dùng `String.length()` để dự đoán số byte: một chữ có dấu hoặc emoji có thể chiếm nhiều byte UTF-8.

**Giới hạn của roundtrip:** `decode(encode(text, UTF_8), UTF_8)` đúng khi đầu vào là chuỗi Unicode hợp lệ đối với quá trình mã hóa đang dùng. Dữ liệu Java có surrogate không hợp lệ hoặc charset không thể biểu diễn ký tự có thể bị thay thế theo chính sách encoder. Vì vậy roundtrip là kiểm thử cần thiết nhưng không thay thế kiểm thử golden vector và validation dữ liệu.

## 4. Chương trình chạy được 2 — Ký tự phân cách, dấu cộng và chuỗi rỗng

Lưu tệp **`FormSeparatorsDemo.java`**:

~~~java
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

public class FormSeparatorsDemo {
    static String encode(String input) {
        return URLEncoder.encode(input, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) {
        String input = "a+b&c=d?e#f/g%h";
        System.out.println("separators=" + encode(input));
        System.out.println("roundtrip=" +
                input.equals(URLDecoder.decode(
                        encode(input), StandardCharsets.UTF_8)));

        System.out.println("space=" + encode("a b"));
        System.out.println("literal-plus=" + encode("a+b"));
        System.out.println("safe=" + encode("AZaz09-._*"));
        System.out.println("tilde=" + encode("~"));
        System.out.println("empty=" + encode("").isEmpty());
        System.out.println("question=" + encode("?"));
        System.out.println("hash=" + encode("#"));
    }
}
~~~

Chạy:

~~~bash
javac --release 10 FormSeparatorsDemo.java
java FormSeparatorsDemo
~~~

**Stdout chính xác:**

~~~text
separators=a%2Bb%26c%3Dd%3Fe%23f%2Fg%25h
roundtrip=true
space=a+b
literal-plus=a%2Bb
safe=AZaz09-._*
tilde=%7E
empty=true
question=%3F
hash=%23
~~~

Điểm cốt lõi:

- Nếu giá trị là `"a+b"`, biểu diễn form phải là `a%2Bb`, vì decoder sẽ đọc `a+b` thành `"a b"`. Đây là lỗi “mất dấu cộng” rất thường gặp trong kiểm thử.
- Dấu `&` trong giá trị được mã hóa thành `%26` để không thành dấu tách field; dấu `=` trong giá trị thành `%3D` để không bị hiểu là ranh giới khóa–giá trị.
- Dấu `?`/`#` rất quan trọng với URL nhưng trong **form field** cũng phải được mã hóa nếu thuộc nội dung dữ liệu; `/` và `%` cũng tương tự.
- `encode("")` trả chuỗi rỗng. Phương thức này **không quyết định** một field có được gửi hay không: đó là quyết định của tầng xây dựng form.
- Tập ký tự `AZaz09-._*` và `~` là test nhỏ giúp phân biệt chính xác ngữ nghĩa của `URLEncoder` với các bộ mã hóa URI khác.

## 5. Xây dựng một body form: mã hóa **riêng** key và value

Một biểu mẫu có thể chứa nhiều cặp khóa–giá trị:

~~~text
tên  = Nguyễn An
tag  = a&b
tag  = (chuỗi rỗng)
note = a+b = 100%
empty = (chuỗi rỗng)
~~~

Yêu cầu:

- Khóa `"tên"` cũng có Unicode, vì vậy **key phải được encode**, không chỉ value.
- `"Nguyễn An"` có dấu và khoảng trắng; `"a&b"` có dấu phân cách; `"a+b = 100%"` có cộng, bằng, khoảng trắng, phần trăm.
- Tên `"tag"` xuất hiện **hai lần**, đại diện cho hai trường hợp cùng tên. **Không chuyển tùy tiện sang `Map<String,String>`** nếu yêu cầu bảo toàn nhiều giá trị cho một tên trường.
- `tag=` và `empty=` là hai cặp có **giá trị rỗng được gửi thật**, khác với trường không có mặt trong body.
- Dấu `=` dùng để nối key đã encode với value đã encode; `&` chỉ nối các cặp hoàn chỉnh. Hai dấu này được thêm **sau khi** đã encode từng thành phần.

Cách ghép một tập cặp form:

~~~java
String body = fields.stream()
        .map(e -> URLEncoder.encode(e.getKey(), StandardCharsets.UTF_8)
                + "="
                + URLEncoder.encode(e.getValue(), StandardCharsets.UTF_8))
        .collect(Collectors.joining("&"));
~~~

Đây là **đoạn minh họa bên trong một phương thức**; `fields` là một `List<Map.Entry<String,String>>` theo thứ tự mong muốn và không chứa null key/value. Nó giữ các cặp lặp tên vì danh sách cho phép phần tử nhiều lần.

**Không viết:**

~~~java
String wrong = URLEncoder.encode(
        "name=An&tag=a+b", StandardCharsets.UTF_8);
~~~

Nếu mục tiêu là body có hai cặp key/value, câu trên **sai** vì nó encode cả dấu phân cách `=` và `&` thành `%3D`/`%26`. Cách đúng là encode mỗi key/value rồi tự nối `name=An&tag=a%2Bb`.

## 6. Chương trình chạy được 3 — Tiếng Việt, trường lặp tên và value rỗng

Lưu tệp **`FormFieldsDemo.java`**:

~~~java
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.AbstractMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class FormFieldsDemo {
    static String encode(String s) {
        return URLEncoder.encode(s, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) {
        List<Map.Entry<String, String>> fields = List.of(
                Map.entry("t\u00EAn", "Nguy\u1EC5n An"),
                Map.entry("tag", "a&b"),
                Map.entry("tag", ""),
                Map.entry("note", "a+b = 100%"),
                Map.entry("empty", "")
        );

        String body = fields.stream()
                .map(e -> encode(e.getKey()) + "=" + encode(e.getValue()))
                .collect(Collectors.joining("&"));

        System.out.println("body=" + body);
        System.out.println("bytes=" +
                body.getBytes(StandardCharsets.UTF_8).length);

        String[] parts = body.split("&", -1);
        boolean matches = parts.length == fields.size();
        int empty = 0;
        int tags = 0;

        for (int i = 0; i < parts.length; i++) {
            int separator = parts[i].indexOf('=');
            if (separator < 0) {
                matches = false;
                continue;
            }
            String key = URLDecoder.decode(
                    parts[i].substring(0, separator), StandardCharsets.UTF_8);
            String value = URLDecoder.decode(
                    parts[i].substring(separator + 1), StandardCharsets.UTF_8);

            matches &= key.equals(fields.get(i).getKey())
                    && value.equals(fields.get(i).getValue());
            if (value.isEmpty()) {
                empty++;
            }
            if (key.equals("tag")) {
                tags++;
            }
        }

        System.out.println("roundtrip-all=" + matches);
        System.out.println("tag-fields=" + tags);
        System.out.println("empty-values=" + empty);
        System.out.println("empty-present=" + body.contains("&empty="));
    }
}
~~~

Chạy:

~~~bash
javac --release 10 FormFieldsDemo.java
java FormFieldsDemo
~~~

**Stdout chính xác:**

~~~text
body=t%C3%AAn=Nguy%E1%BB%85n+An&tag=a%26b&tag=&note=a%2Bb+%3D+100%25&empty=
bytes=70
roundtrip-all=true
tag-fields=2
empty-values=2
empty-present=true
~~~

Chương trình dùng `List.of(Map.entry(...), ...)` có từ Java 9, nên chạy được với `--release 10`. Các entry này không nhận null key/value; **chuỗi rỗng `""` hoàn toàn hợp lệ**.

Tại sao `bytes=70`? Toàn bộ body sau form-encoding chỉ chứa ký tự ASCII in được, nên `getBytes(UTF_8).length` bằng số ký tự ASCII của chính body. Đây là số bytes của **body đã encode**, không phải số byte của các chuỗi gốc chưa encode.

### Ý nghĩa phép kiểm tra

- `roundtrip-all=true`: cách decode **từng cặp đã tách đúng ranh giới** phục hồi cả tiếng Việt, dấu `&` trong value, dấu `+` thực và các value rỗng.
- `tag-fields=2`: tên trùng được giữ nguyên, không làm rơi field thứ hai.
- `empty-values=2`: `tag=` và `empty=` đều là value rỗng thực sự.
- `empty-present=true`: body có cặp `empty=`, khác với việc bỏ hoàn toàn field đó.
- Không dựa vào một `Map` thông thường để test số lượng field lặp, bởi một Map chỉ có một mapping cho mỗi khóa.
- Trong ví dụ, thứ tự cặp được bảo toàn vì `fields` là một `List` được stream tuần tự. Nếu dùng một map không bảo đảm iteration order, không nên viết test đòi body có thứ tự cụ thể mà không chủ động kiểm soát.

## 7. Rỗng, không có field, chỉ có khoảng trắng và giá trị `"null"`

Không đánh đồng những trạng thái sau:

| Tình trạng nghiệp vụ | Ví dụ biểu diễn | Ý nghĩa cần test |
| --- | --- | --- |
| **Không có field** | Body không xuất hiện cặp `note` nào | Caller không gửi tham số đó |
| **Field có value rỗng** | `note=` | Gửi tham số `note` với chuỗi rỗng |
| **Field chỉ có key, không có `=`** | `note` | Một số parser coi như value rỗng, nhưng không áp đặt hành vi đồng nhất cho mọi server |
| **Value có một khoảng trắng** | `note=+` | Sau `URLDecoder`, value là `" "`, **không** phải `""` |
| **Value là dấu cộng thật** | `note=%2B` | Sau decode, value là `"+"` |
| **Value là chuỗi ký tự `null`** | `note=null` | Sau decode, value là chuỗi `"null"`, **không phải Java `null`** |
| **Value là ký tự NUL U+0000** | `note=%00` | Là ký tự điều khiển trong chuỗi sau decode, **không đồng nghĩa Java null** |
| **Key rỗng** | `=value` | Trường có tên rỗng, tùy hợp đồng server có chấp nhận không |
| **Body hoàn toàn rỗng** | `""` | Không có cặp key/value được biểu diễn |

`URLEncoder.encode("")` không tự thêm dấu `=`. **Lớp ghép body** có trách nhiệm tạo `key=` nếu cần biểu diễn field rỗng. Quy tắc “empty value có khác absent parameter không” thuộc về API đích, không được suy luận từ một phương thức encode chuỗi.

Nếu đầu vào của một field là `null` trong Java, hãy có chính sách rõ: **bỏ field**, **chuyển thành chuỗi rỗng** hoặc **từ chối dữ liệu**. `URLEncoder.encode((String) null, UTF_8)` ném `NullPointerException`; nó không mặc định coi null là rỗng.

### Vì sao `String.split` cũng dễ làm mất thông tin?

Trong một parser đơn giản dùng để **kiểm thử** body:

~~~java
String[] pairs = body.split("&", -1);
~~~

Dùng `-1` để giữ các phần tử rỗng ở cuối nếu cấu trúc body có chúng. Khi tách riêng một cặp `key=value`, chỉ lấy **vị trí `=` đầu tiên**; value đã được encode đúng sẽ không chứa literal `=`, nhưng cách lấy vị trí đầu tiên vẫn là thói quen parser rõ ràng.

Với ứng dụng HTTP thật, nên ưu tiên parser biểu mẫu của framework đã được kiểm chứng và tuân thủ giới hạn kích thước, chính sách duplicate key, charset, và quy tắc lỗi. Ví dụ parser thủ công ở bài chỉ phục vụ **chứng minh mã hóa/giải mã của các ca kiểm thử xác định**.

## 8. Decode **sau khi tách cặp**, không decode cả body trước

Một sai lầm quan trọng: decode toàn bộ body trước rồi mới tách dấu `&`. Khi đó `%26` trong một value sẽ biến thành `&` và **bị nhầm thành field separator**.

Ví dụ form body:

~~~text
note=a%26b%3Dc&space=a+b&plus=a%2Bb&empty=
~~~

Cách đúng: trước tiên tách theo dấu `&` raw của form, sau đó với mỗi cặp, xác định dấu `=` raw rồi decode **riêng key và value**.

~~~text
note  -> a&b=c
space -> a b
plus  -> a+b
empty -> "" (chuỗi rỗng)
~~~

Nếu decode nguyên body trước, bạn sẽ có một chuỗi kiểu `note=a&b=c&...`, không còn phân biệt được dấu `&` do data với dấu `&` làm separator.

**Tuyệt đối tránh decode hai lần một cách mặc định.** Ví dụ value chứa chuỗi literal `"%26"` được encode thành `%2526`. Decode **một lần** được `"%26"` đúng nguyên dữ liệu; decode thêm lần nữa thành `"&"` và làm sai ý nghĩa. Nếu một hệ thống có nhiều tầng encode/decode, quy định rõ tầng nào sở hữu bước giải mã duy nhất để tránh bug và sự khác biệt giữa proxy, gateway và server.

### Chương trình chạy được 4 — Phân biệt ký tự cộng và separator

Lưu **`ComponentDecodingDemo.java`**:

~~~java
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

public class ComponentDecodingDemo {
    public static void main(String[] args) {
        String body = "note=a%26b%3Dc&space=a+b&plus=a%2Bb&empty=";

        String[] parts = body.split("&", -1);
        for (String part : parts) {
            int equal = part.indexOf('=');
            String key = URLDecoder.decode(
                    part.substring(0, equal), StandardCharsets.UTF_8);
            String value = URLDecoder.decode(
                    part.substring(equal + 1), StandardCharsets.UTF_8);
            System.out.println(key + "=[" + value + "]");
        }

        String wronglyDecoded =
                URLDecoder.decode(body, StandardCharsets.UTF_8);
        System.out.println("whole-decode-before-split=" + wronglyDecoded);

        System.out.println("raw-plus=" +
                URLDecoder.decode("a+b", StandardCharsets.UTF_8));
        System.out.println("escaped-plus=" +
                URLDecoder.decode("a%2Bb", StandardCharsets.UTF_8));

        try {
            URLDecoder.decode("bad%GG", StandardCharsets.UTF_8);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid-percent=" +
                    expected.getClass().getSimpleName());
        }

        System.out.println("empty-decode=" +
                URLDecoder.decode("", StandardCharsets.UTF_8).isEmpty());
    }
}
~~~

Lệnh:

~~~bash
javac --release 10 ComponentDecodingDemo.java
java ComponentDecodingDemo
~~~

**Stdout chính xác:**

~~~text
note=[a&b=c]
space=[a b]
plus=[a+b]
empty=[]
whole-decode-before-split=note=a&b=c&space=a b&plus=a+b&empty=
raw-plus=a b
escaped-plus=a+b
invalid-percent=IllegalArgumentException
empty-decode=true
~~~

Ý nghĩa:

- `note=[a&b=c]` xác nhận `&` và `=` thuộc value được phục hồi đúng khi decode thành phần sau khi tách.
- `space=[a b]` và `plus=[a+b]` cho thấy `+` dùng để biểu diễn khoảng trắng, còn `%2B` dùng cho dấu cộng thật.
- `empty=[]` cho thấy một cặp `empty=` vẫn tồn tại với value rỗng.
- `whole-decode-before-split` chứng minh vì sao decode cả body ở thời điểm sai sẽ phá ranh giới parser.
- `URLDecoder.decode("bad%GG", UTF_8)` trong ví dụ ném `IllegalArgumentException` vì cú pháp escape không hợp lệ; dữ liệu `%HH` hợp lệ về cú pháp nhưng tạo byte UTF-8 sai là một vấn đề khác và có thể được decoder thay ký tự theo chính sách Charset.

`URLDecoder` phục vụ **form-encoding**; không dùng nó tùy tiện để “decode nguyên URL” vì `+` trong các thành phần URI khác không nhất thiết có cùng ngữ nghĩa khoảng trắng.

## 9. Unicode có thể trông giống nhau nhưng byte khác nhau

Một ca kiểm thử nâng cao với tiếng Việt và các ngôn ngữ có dấu là **Unicode normalization**. Ví dụ chữ `é` có thể được biểu diễn theo hai cách:

- **Dạng dựng sẵn:** `é` = U+00E9.
- **Dạng phân tách:** `e` = U+0065 và dấu sắc kết hợp U+0301.

Người đọc có thể nhìn hai chuỗi như giống nhau, nhưng các code point khác nhau. `URLEncoder.encode(text, UTF_8)` **mã hóa nội dung được cung cấp**, không tự chuẩn hóa cả hai thành một dạng Unicode duy nhất:

~~~text
café      -> caf%C3%A9
cafe + ◌́ -> cafe%CC%81
~~~

Do đó, nếu hệ thống yêu cầu tìm kiếm, dedup, chữ ký, hoặc so sánh định danh dựa trên một dạng normalization, nên **chọn chính sách ở tầng dữ liệu**, ví dụ `Normalizer.Form.NFC`, rồi encode giá trị đã chuẩn hóa. Không tự ý normalize mọi dữ liệu trước gửi nếu protocol yêu cầu giữ nguyên byte/string gốc.

### Chương trình chạy được 5 — Null và Unicode normalization

Lưu **`FormValidationDemo.java`**:

~~~java
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

public class FormValidationDemo {
    static void check(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + "=accepted");
        } catch (RuntimeException expected) {
            System.out.println(name + "=" +
                    expected.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        check("null-text", () ->
                URLEncoder.encode((String) null, StandardCharsets.UTF_8));
        check("null-charset", () ->
                URLEncoder.encode("text", (Charset) null));
        check("decode-null-text", () ->
                URLDecoder.decode((String) null, StandardCharsets.UTF_8));
        check("decode-null-charset", () ->
                URLDecoder.decode("text", (Charset) null));

        String composed = "caf\u00E9";
        String decomposed = "cafe\u0301";
        String a = URLEncoder.encode(composed, StandardCharsets.UTF_8);
        String b = URLEncoder.encode(decomposed, StandardCharsets.UTF_8);

        System.out.println("composed=" + a);
        System.out.println("decomposed=" + b);
        System.out.println("same-encoding=" + a.equals(b));

        String normalized =
                Normalizer.normalize(decomposed, Normalizer.Form.NFC);
        System.out.println("normalized-equal=" +
                composed.equals(normalized));
        System.out.println("normalized-encoding-equal=" +
                a.equals(URLEncoder.encode(
                        normalized, StandardCharsets.UTF_8)));
    }
}
~~~

Chạy:

~~~bash
javac --release 10 FormValidationDemo.java
java FormValidationDemo
~~~

Stdout:

~~~text
null-text=NullPointerException
null-charset=NullPointerException
decode-null-text=NullPointerException
decode-null-charset=NullPointerException
composed=caf%C3%A9
decomposed=cafe%CC%81
same-encoding=false
normalized-equal=true
normalized-encoding-equal=true
~~~

Chương trình xác nhận:

1. `URLEncoder.encode` và `URLDecoder.decode` phiên bản nhận `Charset` không chấp nhận giá trị `String` đầu vào null hoặc `Charset` null; chúng ném `NullPointerException`. Đây là lỗi **khác hoàn toàn** với chuỗi rỗng `""` hợp lệ.
2. Hai cách viết `café` khác nhau về code point được mã hóa thành hai chuỗi phần trăm khác nhau.
3. `Normalizer.normalize(..., NFC)` chủ động chuẩn hóa dữ liệu; sau đó hai chuỗi trong ví dụ trở thành bằng nhau và cho kết quả form-encoding giống nhau.
4. Việc normalization phải được quyết định theo hợp đồng nghiệp vụ. `URLEncoder` không tự normalize dữ liệu Unicode để “sửa” một đầu vào không thống nhất.

Nếu đầu vào chứa **surrogate UTF-16 lỗi** hoặc ký tự không thể biểu diễn trong charset chỉ định, encoder có thể dùng ký tự/byte thay thế. Khi yêu cầu bảo toàn tuyệt đối dữ liệu, cần validation input và chính sách encoding thích hợp; không suy luận rằng một vòng `encode/decode` sẽ phục hồi được mọi chuỗi Java bất kỳ.

## 10. Chọn ca kiểm thử nào cho biểu mẫu thực tế?

### Nhóm A — Quốc tế hóa và tiếng Việt

Kiểm thử ít nhất các trường hợp:

- Chữ có dấu ở **key** và **value**: `tên`, `Nguyễn An`, `Tiếng Việt`, `Hà Nội`.
- Tổ hợp dấu khác nhau: `à`, `ế`, `ộ`, `ễ`, `ư`, `đ`; đảm bảo code point và UTF-8 đúng.
- Chữ ngoài BMP như emoji `🚀` khi domain cho phép; đảm bảo nhiều byte không bị cắt hoặc thay ngẫu nhiên.
- Dạng Unicode dựng sẵn và kết hợp nếu hệ thống có yêu cầu normalization. Chỉ normalize khi hợp đồng quy định.
- Chuỗi chỉ ASCII làm baseline, để phân biệt lỗi Unicode với lỗi delimiter.

**Không chỉ test `"hello"`**: ASCII thường không giúp phát hiện sai charset hoặc sai codepoint.

### Nhóm B — Phân cách và chuỗi có ký tự đặc biệt

- Khoảng trắng giữa từ: `"a b"` → `a+b`.
- Dấu cộng thật: `"a+b"` → `a%2Bb`.
- `&` và `=` xuất hiện bên trong value: phải giữ nguyên dữ liệu sau khi decode đúng.
- `?`, `#`, `/`, `%`: mã hóa khi là dữ liệu form; không dùng luật của URI path để bỏ qua.
- Ký tự `~` và `*` để nhận diện đúng bộ quy tắc `URLEncoder`.
- Chuỗi đã chứa `"%20"` hay `"%26"` như **text literal**: encode dấu phần trăm thành `%25` và decode đúng **một lần**.

### Nhóm C — Dữ liệu rỗng và missing

- Value là `""`: `encode("")` trả `""`.
- Một field có giá trị rỗng được đưa vào body thành `key=`; không tự bỏ.
- Field **không có mặt**: khác với field có value rỗng; server có thể áp dụng default khác nhau.
- Value chỉ có một khoảng trắng: form-encoded `+`, decode thành `" "`, khác `""`.
- Value là `"+"`: form-encoded `%2B`, decode thành `"+"`.
- Hai field cùng key, một value có dữ liệu và một value rỗng: bảo toàn cả hai nếu API cần repeated parameters.
- `null` trong ứng dụng: xử lý rõ là omit/empty/error; không pass thẳng vào `URLEncoder.encode`.

### Nhóm D — Lỗi và tính nhất quán end-to-end

- Kiểm tra percent escape không hợp lệ, như `%GG` hoặc `%` cuối chuỗi; `URLDecoder` có thể ném `IllegalArgumentException`.
- Kiểm tra hệ thống **không decode cả body trước khi split**.
- Kiểm tra **không double-encode hoặc double-decode** giữa tầng ứng dụng và HTTP client/server framework.
- Kiểm tra Content-Type/charset ở phía nhận tương thích UTF-8.
- Kiểm tra giới hạn kích thước form, số field và chính sách trùng key của server/framework.
- Kiểm tra mọi tầng cùng định nghĩa “empty vs missing”, không chỉ mỗi bộ mã hóa.
- Không suy ra rằng encoding đủ bảo đảm an toàn ứng dụng: server vẫn phải validate dữ liệu, giới hạn đầu vào và escape output theo ngữ cảnh khi hiển thị.

### Mẫu kiểm thử bằng golden vector và roundtrip

Nếu dùng JUnit trong dự án, một unit test có thể so sánh kết quả encode với **chuỗi kỳ vọng cố định** và thêm một assertion về roundtrip:

~~~java
String input = "Hà Nội";
String encoded = URLEncoder.encode(input, StandardCharsets.UTF_8);

// Ví dụ trong hàm test (tùy JUnit/framework):
assertEquals("H%C3%A0+N%E1%BB%99i", encoded);
assertEquals(input, URLDecoder.decode(encoded, StandardCharsets.UTF_8));
~~~

Đây là **đoạn minh họa test**, không phải một chương trình Java thuần độc lập; `assertEquals` cần import từ thư viện kiểm thử mà dự án sử dụng. Các chương trình đầy đủ trong bài đều sử dụng Java standard library và có thể chạy không cần dependency.

**Vì sao cần cả hai dạng assertion?** Roundtrip có thể **vẫn đúng** dù encoder và decoder cùng tuân theo một quy tắc sai so với bên ngoài; golden vector kiểm tra **khả năng tương thích định dạng**. Ngược lại, golden test chỉ vài chuỗi không bao phủ mọi Unicode; roundtrip giúp kiểm tra giá trị được phục hồi.

## 11. Khi nào không dùng `URLEncoder`?

### Không mã hóa cả URL

~~~java
// SAI khi url là URL hoàn chỉnh:
String result = URLEncoder.encode(url, StandardCharsets.UTF_8);
~~~

Đây là **đoạn mã minh họa trong method**, `url` là chuỗi giả định. Cách này sẽ encode cả dấu `:`, `/`, `?`, `&` và `=`, phá cấu trúc URL. Đối với URI, dùng API xử lý URI/HTTP client phù hợp và mã hóa đúng **thành phần** theo hợp đồng của nó.

### Không dùng form-encoding thay cho path encoding

Dấu cách form-encoded thành `+`, nhưng một URI path segment không mặc nhiên diễn giải `+` là khoảng trắng. `URLEncoder` được mô tả chuyên cho `application/x-www-form-urlencoded`; không dùng thay thế tùy tiện cho path segment hoặc filename trong đường dẫn URL.

### Không áp dụng cho upload file/binary

Với dữ liệu file, ảnh hoặc nội dung nhị phân, không biến byte[] thành `String` rồi gọi `URLEncoder`. Các biểu mẫu tải file thường dùng `multipart/form-data` và API upload chuyên biệt; nếu API chấp nhận base64 hay một chuỗi biểu diễn khác, đó là hợp đồng dữ liệu riêng.

### Không tin tưởng rằng form-encoding là validation hoặc escaping toàn diện

Mã hóa thành phần giúp phân biệt **dấu phân cách dữ liệu và dấu phân cách định dạng**, nhưng không thay thế kiểm soát đầu vào. Một value sau decode vẫn có thể chứa ký tự `<`, `>`, dấu nháy, chuỗi SQL hoặc giá trị nằm ngoài miền nghiệp vụ. Xử lý SQL bằng parameterized query, render HTML bằng escaping đúng ngữ cảnh, và áp dụng validation theo API đích.

## 12. Những lỗi phổ biến và hướng sửa

| Lỗi thường gặp | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng bộ mã hóa mặc định theo môi trường | Tiếng Việt có thể khác kết quả giữa hệ thống | `URLEncoder.encode(value, StandardCharsets.UTF_8)` |
| Ghép body trước rồi encode toàn bộ | Dấu `=`/`&` của form cũng bị encode, mất cấu trúc | Encode từng key và value rồi ghép |
| Giữ dấu `+` nguyên trong value | Decoder đọc `+` thành khoảng trắng | Encode dấu cộng thật thành `%2B` |
| Không encode `&` trong value | Parser thấy một field bổ sung sai | Để `URLEncoder` biến thành `%26` |
| Không encode `=` trong value | Parser có thể hiểu sai khóa–giá trị | Encode giá trị đầy đủ rồi nối dấu `=` raw |
| Trả `null` trực tiếp cho `encode` | Ném `NullPointerException` | Quyết định rõ omit, empty hoặc reject |
| Tưởng `encode("")` tạo `key=` | `encode("")` chỉ trả chuỗi rỗng | Tầng ghép form phải thêm `key=` |
| Dùng `Map<String,String>` cho repeated parameters | Mất các lần xuất hiện trước của cùng key | Dùng danh sách các cặp hoặc multi-value map |
| Decode cả body rồi mới tách `&` | `%26` trong value biến thành delimiter | Tách raw trước, decode từng component |
| Decode hai lần | `%2526` có thể thành `&`, thay đổi ý nghĩa | Quy định một tầng sở hữu decode |
| Dùng luật URI path để đoán `~`/`+` | Kết quả không khớp form-encoding | Test theo Javadoc `URLEncoder` |
| Chỉ test ASCII | Không phát hiện sai UTF-8/Unicode | Thêm tiếng Việt, dấu kết hợp, emoji |
| Chỉ test roundtrip | Hai bên cùng sai nhưng vẫn roundtrip | Thêm golden vector kỳ vọng cố định |
| Tưởng Java `null` và `""` là một | Sai nghiệp vụ, NPE hoặc mất field | Test từng trạng thái riêng |
| Bỏ qua Unicode normalization khi domain cần | Hai chuỗi nhìn giống nhau nhưng key/bytes khác | Chuẩn hóa có chủ đích trước encode |
| Dùng bộ giải mã form cho URL nguyên vẹn | Dấu `+` có thể bị hiểu sai; phá cấu trúc URI | Dùng API giải mã đúng loại thành phần |

## 13. Bài tập tự kiểm tra

1. `URLEncoder.encode("a b", UTF_8)` trả gì? Khác `URLEncoder.encode("a+b", UTF_8)` như thế nào?
2. Vì sao giá trị `"a&b"` phải mã hóa dấu `&`? Nếu không, có rủi ro gì khi server tách tham số?
3. `URLEncoder.encode("", UTF_8)` có sinh `%00` hoặc `+` không?
4. Body có `note=` khác gì body không có `note`?
5. Nếu `body` có value `a%26b%3Dc`, nên tách cặp trước hay decode trước?
6. Hai tên trường `tag` xuất hiện trong một form: dùng `Map<String,String>` có lưu cả hai không?
7. Tại sao tiếng Việt cần golden test UTF-8 thay vì chỉ test ASCII?
8. `URLEncoder.encode("~", UTF_8)` trả gì? `*` được xử lý thế nào?
9. Vì sao `URLDecoder.decode("a+b", UTF_8)` và `URLDecoder.decode("a%2Bb", UTF_8)` khác nhau?
10. Khi Java string là `null`, điều gì xảy ra nếu gọi overload `encode(String, Charset)`?
11. Hai chuỗi `café` ở dạng composed và decomposed có thể tạo percent string giống nhau mà không normalize không?
12. Vì sao không nên gọi `URLEncoder.encode` trên một URL đầy đủ?

**Đáp án:**

1. `a+b` và `a%2Bb`; khoảng trắng khác dấu cộng thật.
2. `&` là dấu phân cách cặp field ở tầng form; phải thành `%26` trong dữ liệu để không tạo field giả.
3. Không. Chuỗi rỗng vẫn rỗng; tầng ghép body tự quyết định viết `key=`.
4. `note=` là field hiện diện với value rỗng; không có `note` là field vắng mặt, có thể được server xử lý khác.
5. Tách body raw theo `&`, tìm `=` của từng cặp, rồi decode key/value riêng.
6. Không bảo đảm; Map thông thường chỉ có một mapping cho mỗi key. Dùng danh sách cặp hoặc cấu trúc multi-value.
7. ASCII có thể cho kết quả giống nhau dưới nhiều bảng mã; tiếng Việt giúp phát hiện lỗi UTF-8 và cách percent-encoding byte.
8. `%7E`; `*` được giữ nguyên.
9. `+` raw thành khoảng trắng; `%2B` thành dấu cộng thật.
10. `NullPointerException`; phải xử lý null theo hợp đồng domain.
11. Có thể khác nhau; nếu muốn thống nhất, chủ động normalize theo một form như NFC.
12. Vì nó mã hóa luôn dấu cấu trúc `:`, `/`, `?`, `&`, `=`; chỉ dùng cho thành phần form phù hợp.

## 14. Tài liệu Java chính thức, đang áp dụng hiện nay

- **Oracle Javadoc — `URLEncoder` Java SE 10, ghi `encode(String, Charset)` từ Java 10:** https://docs.oracle.com/javase/10/docs/api/java/net/URLEncoder.html
- **Oracle Javadoc — `URLDecoder` Java SE 10, ghi `decode(String, Charset)` từ Java 10:** https://docs.oracle.com/javase/10/docs/api/java/net/URLDecoder.html
- **Oracle Javadoc — `URLEncoder` Java SE 26, quy tắc form-encoding, UTF-8, null và replacement:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URLEncoder.html
- **Oracle Javadoc — `URLDecoder` Java SE 26, dấu cộng, percent escape và lỗi decode:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URLDecoder.html
- **Oracle Javadoc — `StandardCharsets`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html
- **Oracle Javadoc — `Normalizer`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/Normalizer.html

**Kết luận:** Hãy kiểm thử mã hóa biểu mẫu bằng **golden vectors tiếng Việt**, **các dấu phân cách được encode đúng**, và **các trường rỗng vẫn tồn tại**. Với Java 10+, chọn `URLEncoder.encode(value, StandardCharsets.UTF_8)` và `URLDecoder.decode(value, StandardCharsets.UTF_8)` cho **từng thành phần** form. Khi ghép body, chỉ dùng `=` và `&` làm delimiter sau khi đã encode key/value riêng. Phân biệt rạch ròi `null`, chuỗi rỗng, giá trị chỉ có khoảng trắng và field vắng mặt; không tự nhận dạng charset, không double-decode và không dùng form encoder để mã hóa cả URL.