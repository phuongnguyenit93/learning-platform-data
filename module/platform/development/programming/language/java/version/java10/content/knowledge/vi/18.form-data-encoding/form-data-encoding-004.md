# Java 10 — Phân biệt mã hóa trường biểu mẫu với mã hóa toàn bộ URI

## 1. Mục tiêu và phạm vi

Java 10 bổ sung hai overload nhận trực tiếp đối tượng `Charset`:

- `URLEncoder.encode(String, Charset)`;
- `URLDecoder.decode(String, Charset)`.

Tên class `URLEncoder` dễ khiến người học hiểu lầm rằng đây là một **bộ mã hóa URL/URI tổng quát**. Thực tế, hợp đồng của class này là mã hóa dữ liệu theo định dạng **`application/x-www-form-urlencoded`**, dùng cho **tên trường và giá trị trường biểu mẫu**. `URLDecoder` thực hiện chiều ngược lại của **định dạng biểu mẫu đó**. Nó không phải bộ phân tích hay giải mã nguyên một URI.

Bài học này làm rõ sự khác nhau giữa:

1. **Mã hóa một trường biểu mẫu**: tên trường hoặc giá trị trước khi ghép cặp `key=value`.
2. **Ghép nội dung form/query**: kết hợp các cặp đã encode bằng dấu `=` và `&`, theo hợp đồng dữ liệu.
3. **Xây dựng một URI**: bảo toàn cấu trúc `scheme://authority/path?query#fragment`, nơi dấu `/`, `?`, `&`, `=` và `#` có vai trò khác nhau tùy thành phần.
4. **Mã hóa thành phần URI**: path, path segment, query, fragment, user-info có **tập ký tự hợp lệ và ý nghĩa dấu phân cách khác nhau**.
5. **Giải mã form** và **giải mã percent-encoding của URI**: đặc biệt khác nhau ở ký tự `+`.

Sau bài học, bạn có thể tạo form body và các query parameter an toàn, tránh double-encoding, dùng `URI` đúng vai trò, kiểm thử với tiếng Việt và ký tự đặc biệt, đồng thời nhận diện các rủi ro khi decode URL không đúng tầng.

**Phạm vi phiên bản:** `URLEncoder`, `URLDecoder` và `URI` không phải lớp mới của Java 10. Phần mới đáng chú ý là overload **`String, Charset`** của hai công cụ form encoding/decoding; chúng vẫn hoạt động trên Java 17, 21 và các JDK hiện đại. Ví dụ hoàn chỉnh được biên dịch bằng `javac --release 10` và cũng chạy trên Java mới.

## 2. Một URI có cấu trúc; một giá trị trường là dữ liệu

Ví dụ URI:

```text
https://example.org/search?q=C%2B%2B+%26+Java&page=2#results
|___|   |_________| |_____| |_______________________| |_____|
scheme   authority    path             query             fragment
```

Trong chuỗi trên:

- `https` là scheme.
- `example.org` là host trong phần authority.
- `/search` là path.
- `q=C%2B%2B+%26+Java&page=2` là **query ở dạng raw**. Trong **quy ước query form-style** của ví dụ, ký tự `&` phân tách các cặp và `=` phân tách tên–giá trị.
- `#results` là fragment, không thuộc query.

Một trường form có tên `q` và giá trị thực `C++ & Java`. Khi mã hóa đúng **riêng giá trị**, ta được `C%2B%2B+%26+Java`. Kết quả này là **dữ liệu bên trong query**, không phải một URI đầy đủ.

Nguyên tắc cốt lõi:

> **Mã hóa dữ liệu của từng thành phần theo quy tắc của thành phần đó, rồi mới ghép cấu trúc. Không mã hóa nguyên URL bằng `URLEncoder` và không giải mã nguyên URL bằng `URLDecoder`.**

Tại sao? Vì nếu coi dấu `:`, `/`, `?`, `#` của URL là “ký tự dữ liệu cần escape”, chúng mất vai trò phân cách. Ngược lại, nếu giải mã dữ liệu quá sớm thì những dấu `&`, `=` hay `/` vốn nằm **trong giá trị** có thể bị nhầm thành dấu phân cách cấu trúc.

### 2.1. Cùng một ký tự, vai trò khác nhau tùy chỗ

| Ký tự | Trong form field value | Trong URI |
|---|---|---|
| Dấu cách | `+` theo form-url-encoding | Thường percent-encode thành `%20` khi dùng trong URI |
| `+` thực sự | `%2B` để tránh bị hiểu là khoảng trắng | Có thể là ký tự `+` hợp lệ ở một số thành phần; URI percent-decoding **không** tự đổi `+` thành space |
| `/` | `%2F` nếu là dữ liệu của field | Dùng phân tách các segment của path; một slash trong **tên segment** lại có ý nghĩa riêng |
| `?` | `%3F` nếu là dữ liệu của field | Bắt đầu query khi ở đúng vị trí cú pháp |
| `#` | `%23` nếu là dữ liệu của field | Bắt đầu fragment |
| `&` | `%26` nếu là dữ liệu của field | Thường là dấu nối cặp trong query **form-style**, không phải quy tắc ngữ nghĩa bắt buộc của mọi query URI |
| `=` | `%3D` nếu là dữ liệu của field | Thường phân tách tên và giá trị trong một query form-style |
| `%` | `%25` nếu là phần trăm literal trong field | Dẫn nhập escape `%HH` trong URI |
| Ký tự tiếng Việt | Chuyển UTF-8 thành các byte rồi percent-encode | Có thể được percent-encode theo quy tắc thành phần; URI không phải lúc nào cũng là HTML form |

**Cần phân biệt:** `?`, `&` và `=` có thể xuất hiện hợp lệ trong những thành phần URI nhất định; cách ứng dụng diễn giải query thành các cặp không phải do bản thân class `URI` áp đặt. Một API có thể dùng query theo cú pháp khác với form encoding. Chỉ chọn `URLEncoder` khi đối tác **thực sự mong đợi cú pháp `application/x-www-form-urlencoded`** cho dữ liệu tương ứng.

## 3. Java 10: `URLEncoder.encode(String, Charset)` làm gì?

Chữ ký:

```java
public static String encode(String s, Charset charset)
```

Đây là chữ ký API để tham khảo, không phải một method cần tự định nghĩa.

Theo Javadoc, `URLEncoder` dùng quy tắc form-url-encoding:

- Chữ cái ASCII `A-Z`, `a-z` và chữ số `0-9` giữ nguyên.
- Dấu chấm `.`, gạch ngang `-`, dấu sao `*` và gạch dưới `_` giữ nguyên.
- Khoảng trắng ASCII được mã hóa thành dấu `+`.
- Các ký tự còn lại cần encode được chuyển thành byte theo `Charset` được cung cấp; mỗi byte trở thành escape dạng `%HH`.
- Charset nên được chỉ định tường minh. `StandardCharsets.UTF_8` là lựa chọn thông dụng và được Java hỗ trợ.

Ví dụ:

```java
var utf8 = StandardCharsets.UTF_8;

String a = URLEncoder.encode("C++", utf8);    // C%2B%2B
String b = URLEncoder.encode("C C", utf8);    // C+C
String c = URLEncoder.encode("a/b", utf8);    // a%2Fb
String d = URLEncoder.encode("a&b=c", utf8);  // a%26b%3Dc
```

Đây là mảnh code trong phương thức, cần import `java.net.URLEncoder` và `java.nio.charset.StandardCharsets`.

### 3.1. Dấu `+` có hai ý nghĩa cần tách bạch

Giả sử:

```text
Giá trị gốc    Form encoded
C++            C%2B%2B
C C            C+C
C+C            C%2BC
```

Trong `application/x-www-form-urlencoded`:
- `+` trong chuỗi **đã encode** biểu diễn **space**.
- `%2B` biểu diễn dấu cộng **thật**.

Nếu ghép giá trị `"C++"` trực tiếp vào query form-style mà **không encode**, đầu nhận dùng `URLDecoder` có thể hiểu `C++` là `C  `, tức hai khoảng trắng. Đó là một lỗi truyền dữ liệu thực tế, không phải một vấn đề trình bày đơn thuần.

### 3.2. Tại sao `*` và `~` cũng đáng lưu ý?

`URLEncoder` giữ lại `*` nhưng có thể percent-encode `~`. Trong cú pháp URI theo RFC 3986, `~` là một trong các ký tự unreserved, còn `*` thuộc nhóm reserved/sub-delims. Đây là một dấu hiệu nữa cho thấy **form-url-encoding không đồng nhất với một bộ percent-encoder dành cho mọi thành phần URI**.

Đừng tự cho rằng mọi công cụ “encode URL” ở mọi framework đều cho kết quả giống nhau theo byte. Hãy áp dụng **hợp đồng của định dạng đang sử dụng**, rồi test các ký tự đặc biệt có liên quan.

### 3.3. Không dùng overload không khai báo charset

`URLEncoder.encode(String)` là overload cũ được đánh dấu **deprecated** vì phụ thuộc default charset của nền tảng/JVM và có thể dẫn tới kết quả khác nhau theo môi trường. Không dùng nó cho code mới.

```java
// Nên dùng:
String encoded = URLEncoder.encode(value, StandardCharsets.UTF_8);

// Không chọn overload thiếu charset chỉ để tiết kiệm vài ký tự:
// URLEncoder.encode(value);
```

Đây là mảnh code, `value` giả định là String. `encode(String, String charsetName)` vẫn là API hợp lệ nếu cần tên encoding, nhưng overload Java 10 `encode(String, Charset)` rõ nghĩa hơn khi đã có `StandardCharsets.UTF_8` và không cần lookup tên encoding lúc chạy.

Ngay cả khi JDK 18+ dùng UTF-8 làm default charset trong nhiều API theo JEP 400, điều đó **không** khiến việc dựa vào default trở thành quy tắc tốt cho dữ liệu trao đổi; hãy khai báo charset theo hợp đồng giữa hai đầu.

## 4. Chiều ngược lại: `URLDecoder.decode(String, Charset)`

Chữ ký:

```java
public static String decode(String s, Charset charset)
```

`URLDecoder` có mục đích **giải mã chuỗi đã được tạo theo `application/x-www-form-urlencoded`**, cụ thể:

- `+` trở lại ký tự space;
- các escape `%HH` được diễn giải thành byte, rồi thành ký tự theo charset đã cho;
- ký tự không cần giải mã được giữ nguyên;
- chuỗi escape `%` sai cú pháp có thể dẫn tới `IllegalArgumentException`, không được coi là dữ liệu đã xác thực.

Ví dụ:

```java
String keyword = URLDecoder.decode(
        "C%2B%2B+%26+Java", StandardCharsets.UTF_8);
// keyword = "C++ & Java"

String wrong = URLDecoder.decode("C++", StandardCharsets.UTF_8);
// wrong = "C  " (hai dấu cách sau C)
```

Đây là mảnh code trong phương thức, cần import `URLDecoder` và `StandardCharsets`.

**Điểm rất quan trọng:** `URLDecoder` **không phải** “giải mã URI bất kỳ”. Nếu một URI có `+` literal trong path hay query không áp dụng form semantics, gọi `URLDecoder` sẽ có thể làm thay đổi dữ liệu không đúng.

### 4.1. Lỗi escape và chất lượng dữ liệu

Ví dụ:

```java
URLDecoder.decode("%G1", StandardCharsets.UTF_8);
// IllegalArgumentException: chuỗi % không có hai chữ số hex hợp lệ
```

Đây là mảnh code cố tình gây ngoại lệ. `URLDecoder` không thay thế một **trình phân tích URI đầy đủ** hoặc một **trình xác thực dữ liệu**. Một percent-escape hợp lệ về cú pháp chưa chắc tương ứng byte UTF-8 hợp lệ; trong một số trường hợp byte lỗi có thể được thay thế bằng replacement character theo charset. Nếu dữ liệu bắt buộc là UTF-8 chuẩn và không có lỗi, hãy quy định quy trình validation phù hợp (ví dụ decoder cấu hình `CodingErrorAction.REPORT`) ở đúng tầng.

### 4.2. Cặp encode/decode cần cùng charset

```java
String raw = "Xin chào";
String encoded = URLEncoder.encode(raw, StandardCharsets.UTF_8);
String restored = URLDecoder.decode(encoded, StandardCharsets.UTF_8);

boolean same = raw.equals(restored); // true
```

Đây là mảnh code trong một method. Nếu bên ghi dùng UTF-8 còn bên đọc dùng charset khác, các ký tự ngoài ASCII có thể bị biến dạng dù dấu `%` vẫn hợp lệ về cú pháp.

## 5. Cách đúng để tạo `application/x-www-form-urlencoded`

Một body dạng form thường có cấu trúc:

```text
encodedName1=encodedValue1&encodedName2=encodedValue2
```

**Chỉ encode các tên và giá trị trường**; những dấu `=` và `&` dùng để ghép cấu trúc **được thêm vào sau khi encode**.

Quy tắc ghép:

1. Lấy tên trường nguyên bản.
2. `URLEncoder.encode(name, utf8)`.
3. Lấy giá trị trường nguyên bản.
4. `URLEncoder.encode(value, utf8)`.
5. Ghép `nameEncoded + "=" + valueEncoded`.
6. Nối các cặp bằng `&`.
7. Bên nhận tách theo dấu `&` và dấu `=` **còn ở dạng raw**; sau đó mới giải mã riêng từng tên/giá trị theo form semantics.

**Vì sao cần encode cả tên trường?** Tên trường cũng có thể chứa khoảng trắng, `&`, `=` hoặc Unicode. Nếu không encode, parser có thể nhầm một phần tên với dấu phân cách.

### 5.1. Sai và đúng

Giả sử:
- name = `"full name"`;
- value = `"An & Bình + 50%"`.

Ghép thẳng là sai:

```text
full name=An & Bình + 50%
```

Dấu `&` trong giá trị có thể bị hiểu là bắt đầu cặp thứ hai, `+` bị hiểu là space và dấu `%` không tạo thành escape hợp lệ. Dấu cách cũng không theo đúng quy tắc form.

Mã hóa đúng:

```text
full+name=An+%26+B%C3%ACnh+%2B+50%25
```

Trong kết quả:
- `full name` → `full+name`;
- dấu cách trong giá trị → `+`;
- `&` là **dữ liệu** → `%26`;
- chữ `ì` trong `Bình` được chuyển UTF-8 thành `%C3%AC`;
- `+` thật → `%2B`;
- `%` thật → `%25`.

Nếu chuỗi gốc có dấu `=`, nó cũng phải được encode thành `%3D` **trong giá trị**, để không bị nhầm với dấu phân cách giữa tên và giá trị.

## 6. Chương trình hoàn chỉnh 1: mã hóa từng trường biểu mẫu

Tệp **`FormFieldDemo.java`**:

```java
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

public class FormFieldDemo {
    public static void main(String[] args) {
        var utf8 = StandardCharsets.UTF_8;
        String name = "full name";
        String value = "An & Bình + 50%";

        String body = URLEncoder.encode(name, utf8)
                + "=" + URLEncoder.encode(value, utf8);
        String[] parts = body.split("=", 2);

        System.out.println("body=" + body);
        System.out.println("decodedName="
                + URLDecoder.decode(parts[0], utf8));
        System.out.println("decodedValue="
                + URLDecoder.decode(parts[1], utf8));
        System.out.println("plusEncoded="
                + URLEncoder.encode("C++", utf8));
        System.out.println("spaceEncoded="
                + URLEncoder.encode("C C", utf8));

        try {
            URLDecoder.decode("%G1", utf8);
        } catch (IllegalArgumentException ex) {
            System.out.println("badPercentRejected=true");
        }
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac --release 10 -encoding UTF-8 FormFieldDemo.java
java FormFieldDemo
```

**Stdout chính xác:**

```text
body=full+name=An+%26+B%C3%ACnh+%2B+50%25
decodedName=full name
decodedValue=An & Bình + 50%
plusEncoded=C%2B%2B
spaceEncoded=C+C
badPercentRejected=true
```

**Giải thích:**

- `body` là chuỗi form encoded gồm **một cặp**. Dấu `=` nằm giữa hai phần **đã được encode**, nên có thể tách theo dấu bằng xuất hiện đầu tiên.
- `String.split("=", 2)` giới hạn tối đa hai phần trong bài minh họa; một hệ thống có nhiều trường phải tách các cặp theo `&` trước.
- Cả tên và giá trị được giải mã **riêng** sau bước tách.
- Phép thử `C++` xác nhận dấu cộng thật phải là `%2B`; `C C` xác nhận dấu cách thành `+`.
- `URLDecoder.decode("%G1", utf8)` cố ý đưa escape không hợp lệ, và chương trình chỉ xác nhận loại ngoại lệ, không phụ thuộc vào message mặc định.

**Lưu ý:** ví dụ này tự xây **một cặp** để làm rõ quy tắc. Nó không phải một thư viện parser HTTP hoàn chỉnh; trong ứng dụng nhiều giá trị cùng tên, hoặc cần kiểm soát duplicate keys, trật tự trường, empty fields, số lượng trường và giới hạn kích thước, hãy dùng parser/form framework có hợp đồng phù hợp hoặc viết logic xử lý riêng có test đầy đủ.

## 7. Query parameter có thể dùng form-style encoding, nhưng toàn bộ URI thì không

Nhiều dịch vụ HTTP diễn giải phần query theo quy ước các cặp tên–giá trị tương tự form encoding:

```text
https://example.org/search?q=C%2B%2B+%26+Java&page=2
                           |______________|
                           giá trị của q đã encode
```

Trong ví dụ này:
- `https://example.org/search?` là **cấu trúc URI**.
- `q=` và `&page=2` là **dấu phân cách được thêm có chủ đích**.
- `URLEncoder.encode("C++ & Java", utf8)` chỉ áp dụng cho **giá trị của `q`**.
- Bên nhận tách từng cặp, rồi dùng form decoding cho **tên/giá trị**.

Nếu API dùng query grammar khác, không được tự giả định mọi ký tự `+` trong query đều có nghĩa space. `java.net.URI` chỉ hỗ trợ biểu diễn/phân tách URI; nó không định nghĩa mọi query phải tuân theo cặp `key=value`.

### 7.1. `URI.create` nhận một chuỗi URI đã có escape phù hợp

Khi query đã được encode và ghép chính xác:

```java
String encodedTerm = URLEncoder.encode(
        "C++ & Java", StandardCharsets.UTF_8);
URI uri = URI.create(
        "https://example.org/search?q=" + encodedTerm + "&page=2");
```

Đây là mảnh code cần import `URI`, `URLEncoder`, `StandardCharsets`. `URI.create(String)` phân tích **một URI string đã được chuẩn bị đúng cú pháp**. Những `%2B`, `%26` được giữ làm escape trong raw URI, không tự chuyển thành `%252B`.

**Không ghép dữ liệu người dùng vào scheme, host hoặc path một cách tùy tiện.** Mẫu này dùng base URL được code kiểm soát và chỉ ghép **giá trị query đã encode**. Với host hoặc các thành phần khác do input điều khiển, nên dùng thư viện URI builder có API phân biệt từng loại thành phần và các quy tắc validation/allowlist phù hợp.

## 8. `URI.getRawQuery()` khác `URI.getQuery()` như thế nào?

`java.net.URI` cung cấp hai phương thức:

- `getRawQuery()`: phần query **giữ nguyên escape** dạng `%HH`.
- `getQuery()`: trả query sau khi **percent-decoding** các escape theo quy tắc URI; **không** áp dụng quy tắc form `+` → space.

Đây là khác biệt cực kỳ quan trọng khi query chứa `%26` (dấu `&` là dữ liệu) hoặc `%3D` (dấu `=` là dữ liệu).

Ví dụ:

```text
Raw query:
q=C%2B%2B+%26+Java&page=2

URI.getQuery():
q=C+++&+Java&page=2

Giá trị q sau khi tách raw query rồi form-decode:
C++ & Java
```

Nếu lấy `getQuery()` rồi mới tách bằng `&`, dấu `%26` vốn là dữ liệu đã bị giải mã thành `&`, khiến parser tưởng có một tham số mới. Thứ tự **split trước, decode sau** là thiết yếu.

### 8.1. Quy tắc parse query form-style

Đối với một raw query đã xác định sử dụng form-style encoding:

1. Lấy `uri.getRawQuery()`, **không** lấy `getQuery()`.
2. Tách các cặp bằng dấu `&` còn ở dạng raw.
3. Trong mỗi cặp, tách tại dấu `=` **đầu tiên**. Các `=` thật bên trong giá trị phải được encode thành `%3D` khi tạo form.
4. `URLDecoder.decode(rawName, utf8)` và `URLDecoder.decode(rawValue, utf8)`.
5. Quy định chính sách cho duplicate keys, tham số trống, cặp không có dấu `=` và lỗi escape.
6. Kiểm soát số lượng/độ dài input nếu dữ liệu đến từ bên ngoài.

**Chỉ áp dụng các bước trên cho một query được giao thức quy định là form-style.** Một URI có thể chứa query không theo key-value form; `URI.getRawQuery()` không có chức năng tự suy đoán grammar của ứng dụng.

## 9. Chương trình hoàn chỉnh 2: query, path và double-encoding

Tệp **`QueryUriDemo.java`**:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

public class QueryUriDemo {
    static Map<String, String> parseFormQuery(String rawQuery) {
        var values = new LinkedHashMap<String, String>();

        for (String part : rawQuery.split("&", -1)) {
            int equalIndex = part.indexOf('=');
            if (equalIndex < 0) {
                throw new IllegalArgumentException("Missing equals sign");
            }

            String key = URLDecoder.decode(
                    part.substring(0, equalIndex),
                    StandardCharsets.UTF_8);

            String value = URLDecoder.decode(
                    part.substring(equalIndex + 1),
                    StandardCharsets.UTF_8);

            if (values.putIfAbsent(key, value) != null) {
                throw new IllegalArgumentException("Duplicate query key");
            }
        }
        return values;
    }

    public static void main(String[] args) throws Exception {
        String term = "C++ & Java";
        String query = "q=" + URLEncoder.encode(
                term, StandardCharsets.UTF_8) + "&page=2";

        URI uri = URI.create("https://example.org/search?" + query);

        System.out.println("uri=" + uri.toASCIIString());
        System.out.println("rawQuery=" + uri.getRawQuery());
        System.out.println("uriQueryDecoded=" + uri.getQuery());

        var parsed = parseFormQuery(uri.getRawQuery());
        System.out.println("termRoundTrip="
                + term.equals(parsed.get("q")));
        System.out.println("page=" + parsed.get("page"));

        URI path = new URI(
                "https", "example.org", "/docs/a b", null);
        System.out.println("pathUri=" + path.toASCIIString());

        System.out.println("formEncodedPath="
                + URLEncoder.encode(
                    "/docs/a b", StandardCharsets.UTF_8));

        URI doubleQuoted = new URI(
                "https", "example.org", "/search",
                "q=" + URLEncoder.encode(
                    "C++", StandardCharsets.UTF_8),
                null);
        System.out.println("doubleQuoted="
                + doubleQuoted.toASCIIString());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 10 -encoding UTF-8 QueryUriDemo.java
java QueryUriDemo
```

**Stdout chính xác:**

```text
uri=https://example.org/search?q=C%2B%2B+%26+Java&page=2
rawQuery=q=C%2B%2B+%26+Java&page=2
uriQueryDecoded=q=C+++&+Java&page=2
termRoundTrip=true
page=2
pathUri=https://example.org/docs/a%20b
formEncodedPath=%2Fdocs%2Fa+b
doubleQuoted=https://example.org/search?q=C%252B%252B
```

### 9.1. Điều gì được chứng minh?

**A — Form parameter đúng:**
- `q` có giá trị gốc `C++ & Java`.
- Encode **giá trị** thành `C%2B%2B+%26+Java`.
- Ghép `q=...&page=2` vào URL đã biết.
- `getRawQuery()` giữ escape để tách đúng cặp và giải mã từng phần.
- `termRoundTrip=true` xác nhận nhận lại đúng chuỗi gốc.

**B — `URI.getQuery()` không phải form decoder:**
- Kết quả `q=C+++&+Java&page=2` đã percent-decode `%26` thành `&`.
- Những dấu `+` vẫn là `+`, vì URI decoding không áp dụng quy ước space của form.
- Nếu code dùng `getQuery()` rồi split `&`, dữ liệu của `q` có thể bị chia sai.

**C — URI path dùng quy tắc khác:**
- Constructor `new URI("https", "example.org", "/docs/a b", null)` nhận một path chưa được escape đầy đủ và quote ký tự space thành `%20`.
- `URLEncoder.encode("/docs/a b", utf8)` lại cho `%2Fdocs%2Fa+b`: slash bị escape, space thành `+`.
- Vì vậy `URLEncoder` không thể được sử dụng như một hàm “encode nguyên path” theo cách tổng quát.

**D — Double encoding:**
- Constructor `new URI(scheme, authority, path, query, fragment)` với các thành phần chưa escape sẽ xử lý quotation cho các thành phần.
- Nếu truyền vào tham số `query` một chuỗi đã chứa escape `%2B` từ `URLEncoder`, dấu `%` có thể bị quote lần nữa thành `%25`.
- Kết quả `C%252B%252B` là một **URI bị double-encoded** so với giá trị query mong muốn.

**Quy ước sử dụng API:** hoặc cung cấp **các thành phần chưa escape** cho constructor URI có hợp đồng tự quote, hoặc xây **một URI string đã escape đúng** để truyền vào `URI.create(...)`. Không trộn hai giai đoạn và kỳ vọng constructor tự nhận biết phần nào đã được encode.

### 9.2. Parser minh họa có giới hạn rõ

`parseFormQuery` trong ví dụ được viết để minh họa chính sách: bắt buộc mỗi cặp có dấu `=` và **từ chối duplicate key** bằng `IllegalArgumentException`. Nó không phải parser HTTP hoàn chỉnh:
- Không xử lý raw query `null`;
- Không cho phép cặp không có `=`, dù một số server/framework có quy ước riêng cho kiểu đó;
- Không lưu nhiều giá trị cùng key;
- Không giới hạn số lượng trường/kích thước dữ liệu;
- Không thực hiện validation bổ sung cho key hoặc charset lỗi.

Ứng dụng thực tế nên dùng parser được framework hỗ trợ hoặc mở rộng đúng theo hợp đồng đối tác, kiểm thử cả duplicate key, empty field, input quá dài và escape sai. **Đừng sao chép parser tối giản và quảng bá nó là thư viện bảo mật.**

## 10. Path, path segment, query, fragment không có một bộ encoder chung

`URI` có các thành phần mang ngữ nghĩa khác nhau. Việc encode phải theo đúng **vị trí dữ liệu**.

### 10.1. Path và slash

Ví dụ:

```text
https://example.org/files/a/b
                         ^ slash phân tách segment
```

Nếu tên một file hoặc một mã định danh là **chuỗi đơn** `"a/b"`, thì dấu slash **là dữ liệu của một segment**, không phải ranh giới giữa hai segment. Một path builder chỉ nhận một `String path` có thể coi slash này là phân cách.

Vì vậy:
- **Encode toàn bộ path bằng `URLEncoder`:** sai vì slash cấu trúc trở thành `%2F` và space thành `+`.
- **Ghép trực tiếp một segment chưa encode vào path:** có thể sai vì dấu slash trong segment trở thành phân cách.
- **Dùng một path-segment encoder/builder có hợp đồng riêng:** là lựa chọn phù hợp khi thực sự cần truyền một segment có ký tự đặc biệt.

Không giả định rằng `new URI(..., path, ...)` luôn bảo vệ một dấu slash **trong dữ liệu segment**. Nó nhận **toàn bộ thành phần path**, nên slash có thể vẫn là dấu phân cách hợp lệ. Các framework có API `pathSegment(...)`, `addPathSegment(...)` hoặc một tên tương đương thường giúp phân biệt dữ liệu segment với chuỗi path cấu trúc; cần đọc tài liệu framework và chú ý cách server xử lý `%2F`.

### 10.2. Query

Trong query form-style, dữ liệu từng trường được mã hóa riêng bằng `URLEncoder`; dấu `&` và `=` giữa các trường được giữ làm **cấu trúc**. Nhưng không phải mọi giao thức query dùng `application/x-www-form-urlencoded`. Nếu query được mô tả bằng cú pháp khác, dùng encoder/builder theo giao thức đó.

### 10.3. Fragment

`#` đánh dấu phần fragment. Nếu một trường form có ký tự `#`, cần encode thành `%23` **bên trong giá trị**. Nhưng fragment của URI không tự động là một trường form; nó có quy tắc khác, và cũng không được gửi trong request-target HTTP theo nghĩa thông thường.

### 10.4. Scheme và host

Không dùng `URLEncoder.encode("https://example.org", utf8)` để tạo scheme hoặc host. Scheme được định nghĩa bằng ký tự và cú pháp URI; host có các quy tắc DNS/IDN/IP riêng. Nếu host đến từ đầu vào không tin cậy, phải validate/allowlist theo bài toán bảo mật, không chỉ gọi một hàm encode chuỗi.

**Tóm lại:** một giá trị trong query, một path segment, một authority và một fragment không thể xử lý bằng cách “encode URL một lần cho tất cả”.

## 11. Chương trình hoàn chỉnh 3: nhìn thấy lỗi khi encode/decode nguyên URI

Tệp **`UriPitfallDemo.java`**:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

public class UriPitfallDemo {
    public static void main(String[] args) throws Exception {
        URI uri = URI.create(
                "https://example.org/api/a%2Fb?q=a%2Bb+c");

        System.out.println("rawPath=" + uri.getRawPath());
        System.out.println("decodedPath=" + uri.getPath());
        System.out.println("rawQuery=" + uri.getRawQuery());
        System.out.println("uriDecodedQuery=" + uri.getQuery());

        System.out.println("formValue="
                + URLDecoder.decode(
                    uri.getRawQuery().substring(2),
                    StandardCharsets.UTF_8));

        System.out.println("wholeFormEncoded="
                + URLEncoder.encode(
                    uri.toASCIIString(),
                    StandardCharsets.UTF_8));

        System.out.println("wholeFormDecoded="
                + URLDecoder.decode(
                    uri.toASCIIString(),
                    StandardCharsets.UTF_8));

        System.out.println("literalPlusValue="
                + URLDecoder.decode(
                    "C%2B%2B", StandardCharsets.UTF_8));

        System.out.println("plusMeansSpace="
                + URLDecoder.decode(
                    "C++", StandardCharsets.UTF_8));
    }
}
```

```bash
javac --release 10 -encoding UTF-8 UriPitfallDemo.java
java UriPitfallDemo
```

**Stdout chính xác** (hai khoảng trắng cuối trong dòng cuối được thể hiện bởi chuỗi bên dưới):

```text
rawPath=/api/a%2Fb
decodedPath=/api/a/b
rawQuery=q=a%2Bb+c
uriDecodedQuery=q=a+b+c
formValue=a+b c
wholeFormEncoded=https%3A%2F%2Fexample.org%2Fapi%2Fa%252Fb%3Fq%3Da%252Bb%2Bc
wholeFormDecoded=https://example.org/api/a/b?q=a+b c
literalPlusValue=C++
plusMeansSpace=C  
```

### 11.1. `getRawPath()` và `getPath()` có thể khác về dấu slash

`getRawPath()` là `/api/a%2Fb`, còn `getPath()` là `/api/a/b`. Phép percent-decoding đã chuyển `%2F` thành slash literal và làm mất thông tin rằng dấu slash ở giữa `a` và `b` vốn xuất phát từ byte được escape.

Nếu routing, phân quyền hoặc validation dựa trên ranh giới path segment, cần quyết định làm việc trên raw hay decoded path theo hợp đồng của framework/server, và tránh lối xử lý decode nhiều lần. Không có quy tắc chung rằng mọi server đều chấp nhận/giữ nguyên `%2F` trong path.

### 11.2. `getQuery()` không chuyển `+` thành space

Với raw query `q=a%2Bb+c`:
- `URI.getQuery()` trả `q=a+b+c`: nó percent-decode `%2B`, nhưng dấu cộng còn giữ như dấu cộng.
- Nếu biết giá trị này theo **form-style semantics**, phải lấy `getRawQuery()`, tách `q=` rồi dùng `URLDecoder` trên phần value; kết quả là `a+b c`.

`URI.getQuery()` **không phải** vật thay thế tương đương `URLDecoder.decode(...)`.

### 11.3. Encode cả URI làm biến dạng cấu trúc

Dòng:

```java
URLEncoder.encode(uri.toASCIIString(), StandardCharsets.UTF_8)
```

cho `https%3A%2F%2F...`, trong đó `:`, `/` và `?` cấu trúc bị percent-encode như **dữ liệu biểu mẫu**. Đó không còn là một URI đầy đủ có cùng cấu trúc để trình duyệt hoặc HTTP client sử dụng theo ý định ban đầu.

### 11.4. Decode cả URI cũng gây sai dữ liệu

Dòng:

```java
URLDecoder.decode(uri.toASCIIString(), StandardCharsets.UTF_8)
```

biến `%2F` trong path thành `/`, `%2B` trong query thành `+` và `+` literal thành space. Kết quả `https://example.org/api/a/b?q=a+b c` vừa đánh mất ranh giới dữ liệu vừa có dấu cách không hợp lệ khi đưa nguyên chuỗi vào một URI chưa escape.

**Kết luận:** chỉ giải mã **phần đã được xác định là form encoded**, tại đúng tầng parse. Không “decode URL cho dễ nhìn” rồi tái sử dụng chuỗi đó để routing hay ký request.

## 12. Hai tầng percent-encoding và double-encoding

### 12.1. `%` là ký tự quan trọng

Trong URI/form encoded data, escape `%2B` biểu diễn dấu `+`. Nếu chuỗi `%2B` được coi là **dữ liệu thô** và encode thêm lần nữa, dấu `%` thành `%25` và kết quả `%252B`.

```text
Giá trị thô:            C++
Encode form lần 1:      C%2B%2B
Encode lại lần 2:       C%252B%252B
Decode một lần:         C%2B%2B
Decode hai lần:         C++
```

Các bước này không phải tất cả đều nên có. Mã hóa hai lần có thể làm bên nhận một lần decode nhận sai chuỗi dữ liệu; giải mã hai lần có thể khiến dữ liệu ban đầu chứa `%xx` biến thành ký tự có ý nghĩa cú pháp.

**Quy ước:** mỗi tầng cần biết rõ **đầu vào là raw text hay đã encoded**, và bộ builder có tự quote hay không. Không để hai tầng cùng thực hiện form encoding cho cùng value.

### 12.2. Constructor nhiều thành phần của URI không phải là chỗ chứa escape đã tạo sẵn

Hai pattern cần phân biệt:

```java
// Truyền query có dấu %2B đã escape cho URI.create từ URI string:
URI good = URI.create(
    "https://example.org/search?q=" +
    URLEncoder.encode("C++", StandardCharsets.UTF_8));

// Truyền query đã escape cho constructor URI có chức năng quote:
URI doubleEncoded = new URI(
    "https", "example.org", "/search",
    "q=" + URLEncoder.encode("C++", StandardCharsets.UTF_8), null);
```

Mảnh code cần import `URI`, `URLEncoder` và `StandardCharsets`, đặt trong method khai báo/giải quyết `URISyntaxException` cho constructor thứ hai.

`good.toASCIIString()` là `https://example.org/search?q=C%2B%2B`; `doubleEncoded.toASCIIString()` là `https://example.org/search?q=C%252B%252B`.

Một URI builder của framework có thể cho phép tùy chọn “already encoded”, “encode values” hoặc encode riêng path segment; tên API và hành vi khác nhau. Không copy một chuỗi escape vào builder mà không xem nó chờ **raw value** hay **encoded value**.

## 13. Mã hóa form body không đồng nghĩa với xây URI

Một request HTTP POST gửi form body `application/x-www-form-urlencoded` có thể chứa:

```text
POST /submit HTTP/1.1
Host: example.org
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

full+name=An+%26+B%C3%ACnh+%2B+50%25
```

Đây là **ví dụ định dạng request mô tả**, không phải code Java tự mở socket. Body là dữ liệu biểu mẫu được mã hóa; URI đích là `/submit`, **không** phải `URLEncoder.encode("https://example.org/submit", ...)`.

Một query `?q=...` và một form body có thể cùng dùng quy tắc mã hóa tên/giá trị nếu API quy định như vậy, nhưng chúng **ở vị trí khác nhau** trong request:
- Query thuộc request URI.
- Body là phần nội dung request.
- Header `Content-Type` dùng cho media type của **body**, không tự động biến query thành một body form.
- Server/backend có thể có quy tắc parse, giới hạn kích thước, duplicate values và charset khác nhau giữa query và body.

Không nên chuyển mọi dữ liệu form sang query chỉ để tiện dựng URL, đặc biệt với dữ liệu nhạy cảm: query thường xuất hiện trong lịch sử trình duyệt, proxy logs hoặc công cụ giám sát. Việc bảo vệ dữ liệu còn phụ thuộc TLS, thiết kế endpoint và chính sách ghi log; form encoding **không phải cơ chế mã hóa bảo mật**.

### 13.1. Ví dụ Java 11+: tạo request POST form bằng HTTP Client chuẩn

Java 11 giới thiệu `java.net.http.HttpClient` và `HttpRequest` như API chuẩn. Ví dụ dưới đây là **mảnh code Java 11+**, không phải tính năng Java 10:

```java
String body = URLEncoder.encode("full name", StandardCharsets.UTF_8)
        + "="
        + URLEncoder.encode("An & Bình", StandardCharsets.UTF_8);

var request = java.net.http.HttpRequest.newBuilder(
        URI.create("https://example.org/submit"))
    .header("Content-Type",
            "application/x-www-form-urlencoded; charset=UTF-8")
    .POST(java.net.http.HttpRequest.BodyPublishers.ofString(
            body, StandardCharsets.UTF_8))
    .build();
```

Mảnh code cần import `URI`, `URLEncoder`, `StandardCharsets` và nằm trong một method. Nó **chỉ tạo** request, không gửi. Việc gửi cần `HttpClient` và phải xử lý kết nối, timeout, lỗi mạng và HTTP response theo yêu cầu ứng dụng.

Điểm chính: `URLEncoder` chỉ xử lý hai trường `"full name"` và `"An & Bình"`. URI `https://example.org/submit` được tạo riêng; không truyền nguyên URI vào `URLEncoder`.

## 14. Vì sao không thể xử lý mọi URI bằng URLDecoder?

### 14.1. Dấu `+` của query có thể là ký tự thật

Trong URI grammar, `+` có thể xuất hiện như ký tự được phép ở những thành phần nhất định. `URLDecoder` lại quy định `+` thành space vì đó là quy tắc **form**. Do đó:

```java
String formResult =
        URLDecoder.decode("a+b", StandardCharsets.UTF_8);
// "a b"
```

Đây chỉ đúng khi đầu vào **theo form encoding**. Nếu một API định nghĩa token `a+b` với dấu cộng literal, bạn sẽ làm biến dạng token nếu gọi `URLDecoder`.

### 14.2. Dấu phân cách có thể nằm trong dữ liệu đã encode

Ví dụ `q=x%26y%3Dz` là **một giá trị form** có nội dung `x&y=z`. Nếu giải mã cả query trước rồi split, bạn sẽ có `q=x&y=z` và dễ hiểu nhầm thành hai tham số.

**Thứ tự an toàn cho form query là split raw → decode từng component.** Đừng đảo thứ tự.

### 14.3. URI raw và URI decoded phục vụ mục đích khác nhau

`URI.getRawPath()`/`getRawQuery()`/`getRawFragment()` giữ escape; `getPath()`/`getQuery()`/`getFragment()` trả phần đã được percent-decode. Các accessor decoded hữu ích khi logic ứng dụng cần dạng ký tự, nhưng việc chuyển đổi có thể làm mất thông tin cấu trúc raw.

Khi thực thi validation/canonicalization hoặc routing, lựa chọn raw/decoded phải theo hợp đồng hệ thống. Đặc biệt, không **vừa decode ở tầng web server vừa tự decode lần thứ hai** nếu điều đó khiến ký tự cấu trúc xuất hiện sau lớp decode thứ hai.

### 14.4. URL encoding không phải escaping cho HTML, JSON hay SQL

`URLEncoder` không bảo vệ trang HTML khỏi XSS, không escape chuỗi JSON và không thay thế prepared statements trong SQL. Mỗi nơi sử dụng dữ liệu có **bộ quy tắc encoding riêng**. Dùng form encoding đúng vị trí trong URL/body, rồi dùng HTML escaping/JSON serialization/SQL parameters đúng ngữ cảnh tiếp theo.

## 15. Vấn đề Unicode, charset, normalization

### 15.1. UTF-8 chuyển ký tự thành byte trước khi tạo `%HH`

Một ký tự không thuộc ASCII có thể được biểu diễn bằng nhiều byte UTF-8. Ví dụ chữ `ì` trong `"Bình"` chuyển thành hai byte `C3 AC`, nên form encoded chứa `%C3%AC`. Điều đó không phải “hai ký tự” ở văn bản gốc.

Do vậy, độ dài `String.length()` **không** phải số byte của UTF-8, và số dấu `%` trong kết quả encode không bằng số ký tự Unicode. Nếu hệ thống có giới hạn độ dài query/body theo byte, cần kiểm tra độ dài **sau khi mã hóa** theo đúng quy tắc và hợp đồng server.

### 15.2. Unicode normalization không được `URLEncoder` tự giải quyết

Hai chuỗi nhìn giống nhau có thể có các chuỗi code point khác nhau (ví dụ ký tự có dấu tạo sẵn so với ký tự nền cộng combining mark). `URLEncoder` chuyển các ký tự của **đầu vào hiện có** thành byte; không bảo đảm tự chuẩn hóa mọi chuỗi về một Unicode normalization form.

Nếu ứng dụng dùng key Unicode để xác định duplicate hoặc ký nội dung, hãy xác định normalization policy (ví dụ NFC nếu phù hợp) **trước khi encode** và áp dụng nhất quán ở cả hai đầu. Tuy nhiên, không tự normalize các mã định danh có quy tắc bảo toàn byte riêng.

### 15.3. Input hỏng và malformed percent sequences

`URLDecoder` có thể ném `IllegalArgumentException` khi chuỗi escape sai cú pháp như `%G1` hoặc `%` không đủ chữ số hex. Ngoài ra, escape có cú pháp hợp lệ nhưng chứa byte không hợp lệ theo charset vẫn cần chính sách xử lý nếu dữ liệu từ nguồn không tin cậy.

Đừng dùng `decode` như một “bộ lọc xác thực tất cả dữ liệu”. Hãy giới hạn độ dài, định dạng, tên trường được phép, số lần xuất hiện của key và nội dung value ở **sau bước parse/normalize phù hợp**.

### 15.4. Không dùng default charset tùy môi trường

`StandardCharsets.UTF_8` là hằng số dễ hiểu và ổn định. Overload Java 10 nhận `Charset` giúp tránh overload `URLEncoder.encode(String)` deprecated do phụ thuộc default charset. Lựa chọn charset phải thống nhất giữa client và server; việc JDK 18+ thường mặc định UTF-8 không thay thế thỏa thuận giao thức.

## 16. Dữ liệu lặp và tên trường trùng

Một request có thể có các cặp lặp lại:

```text
tag=java&tag=backend&tag=api
```

Điều này không nhất thiết là lỗi: một số HTML form hoặc API cho phép một tên trường có nhiều giá trị. Một `Map<String, String>` **không lưu được cả ba** nếu chỉ đặt một value cho mỗi key. Hãy chọn chính sách rõ:

- `Map<String, List<String>>` khi cần giữ mọi giá trị theo thứ tự nhận.
- Từ chối duplicate keys nếu contract nói mỗi key chỉ xuất hiện một lần.
- Chọn first/last một cách chủ đích **chỉ khi contract cho phép**, thay vì âm thầm ghi đè dữ liệu.
- Xử lý trường rỗng (`name=`), tên rỗng (`=value`), cặp không có `=`, hoặc dấu `&` liên tiếp theo định dạng mà server thực sự hỗ trợ.

Parser demo ở mục 9 **từ chối duplicate key**; đó là một lựa chọn minh họa, không phải luật chung của mọi form/query. Trong ứng dụng thực tế có multi-value parameter, đừng dùng parser một-giá-trị này vì có thể làm mất dữ liệu.

Nếu giá trị chứa `&` hoặc `=` nguyên bản, phải encode từng value để phép tách cặp không làm sai cấu trúc:

```text
Giá trị nguyên bản:       a&b=c
Giá trị đã form-encode:   a%26b%3Dc
Cặp hoàn chỉnh:          note=a%26b%3Dc
```

Tách raw tại dấu `=` của cặp, rồi decode `a%26b%3Dc` mới khôi phục `a&b=c`.

## 17. Checklist code review cho form/query/URI

Khi xem một thay đổi có `URLEncoder` hoặc `URLDecoder`:

- [ ] Đầu vào của `URLEncoder` là **một tên trường/giá trị trường**, không phải cả URI, nguyên path hay host?
- [ ] Nếu tạo query form-style, các name/value được encode **riêng trước khi ghép** `=` và `&`?
- [ ] API phía nhận thực sự yêu cầu `application/x-www-form-urlencoded` hay một loại query khác?
- [ ] Dấu cách cần `+` (form) hay `%20` (URI path)?
- [ ] Dấu cộng literal `+` đã được giữ bằng `%2B` trong form data?
- [ ] Dấu `&`, `=`, `#`, `/` nằm trong **dữ liệu** có được xử lý đúng theo component không?
- [ ] Mọi bước cùng khai báo `StandardCharsets.UTF_8` hoặc charset đúng hợp đồng?
- [ ] Có chỗ nào dùng `URI.getQuery()` rồi `split("&")` khi value có `%26`?
- [ ] Có decode cả URL hoặc cả raw query trước khi tách thành phần không?
- [ ] Có truyền giá trị `%XX` đã escape vào constructor/builder đang tự quote dẫn tới `%25XX` không?
- [ ] Path có cần encode riêng **path segment** thay vì toàn bộ path?
- [ ] Duplicate query keys, empty fields, malformed escape và input quá dài đã có chính sách?
- [ ] Có giữ nguyên raw URI cần thiết cho routing, validation hoặc chữ ký request không?
- [ ] Có nhầm form encoding với mã hóa bảo mật hoặc với HTML/JSON/SQL escaping?
- [ ] Test có bao gồm tiếng Việt, dấu cộng, space, `&`, `=`, `%` và `/`?

Một nhận xét review có cơ sở:

> “Biến `url` hiện đã chứa `https://...?...`. Gọi `URLEncoder.encode(url, UTF_8)` sẽ mã hóa `:`, `/` và `?` của URI như dữ liệu form. Hãy mã hóa `q` và các giá trị query riêng rồi ghép vào base URI đúng quy tắc.”

Nhận xét chưa đủ căn cứ:

> “Cứ URL-encode lại toàn bộ chuỗi một lần nữa cho an toàn.”

Mã hóa sai tầng có thể tạo lỗi dữ liệu và double-encoding, chứ không làm URL an toàn hơn.

## 18. Bài tập tự kiểm tra và đáp án

**1.** `URLEncoder.encode("C++", StandardCharsets.UTF_8)` trả gì?

**Đáp án:** `C%2B%2B`. Hai dấu cộng thật đều phải escape để không bị hiểu là space trong form decoding.

**2.** `URLEncoder.encode("C C", StandardCharsets.UTF_8)` trả gì?

**Đáp án:** `C+C`. Khoảng trắng trong form-urlencoded được chuyển thành `+`.

**3.** Mã hóa `https://example.org/search?q=a b` bằng `URLEncoder` có tạo một URI hoàn chỉnh đúng ý định không?

**Đáp án:** Không. Các dấu `:`, `/`, `?`, `=` sẽ bị encode như dữ liệu. Chỉ mã hóa đúng tên/giá trị form/query rồi ghép cấu trúc URI.

**4.** `URI.getQuery()` có tự chuyển `+` thành khoảng trắng theo quy tắc form không?

**Đáp án:** Không. Nó percent-decode URI escapes, còn form `+` → space là logic của `URLDecoder`.

**5.** Vì sao `URI.getRawQuery()` phù hợp hơn `getQuery()` trước khi tách query form-style?

**Đáp án:** `getRawQuery()` giữ `%26`/`%3D` đang nằm trong giá trị, tránh biến chúng thành delimiter `&`/`=` trước khi parse.

**6.** Giá trị `"a&b=c"` phải được đưa vào form như thế nào?

**Đáp án:** `a%26b%3Dc`, sau đó ghép thành `note=a%26b%3Dc`. Không ghép raw value trước rồi encode cả form body.

**7.** `new URI("https","example.org","/docs/a b",null)` có thể tạo path space dạng nào?

**Đáp án:** `/docs/a%20b` trong URI ASCII. Khác `URLEncoder.encode("/docs/a b",utf8)` cho `%2Fdocs%2Fa+b`.

**8.** Vì sao `new URI(..., "q="+URLEncoder.encode("C++",utf8), ...)` có thể tạo `%252B`?

**Đáp án:** Constructor nhận component đang cần quote. Phần `%2B` đã encode bị quote dấu `%` lần nữa thành `%25` → double-encoding.

**9.** `URLDecoder.decode("a+b", UTF_8)` trả gì?

**Đáp án:** `"a b"` khi coi input là form encoded. Nếu `+` là ký tự literal theo grammar khác, không áp dụng decoder này.

**10.** `URI.getRawPath()` là `/api/a%2Fb`, còn `getPath()` là gì?

**Đáp án:** `/api/a/b`. Percent-decoding có thể làm mất thông tin rằng dấu slash thứ hai vốn nằm trong dữ liệu đã escape.

**11.** Khi API nhận nhiều giá trị `tag=java&tag=backend`, có nên lưu vào `Map<String,String>` rồi ghi đè key `tag` không?

**Đáp án:** Chỉ nếu contract rõ cho phép chọn một giá trị. Nếu cần đầy đủ, dùng `Map<String,List<String>>` hoặc parser framework hỗ trợ multi-value parameter.

**12.** `URLDecoder.decode("%G1", UTF_8)` có thể ném gì?

**Đáp án:** `IllegalArgumentException` vì percent-escape sai cú pháp.

**13.** `URLEncoder.encode(String, Charset)` và `URLDecoder.decode(String, Charset)` xuất hiện từ Java mấy?

**Đáp án:** Java 10. Bản thân hai class cùng các overload khác đã có từ trước.

**14.** Nếu muốn encode một path segment có dấu slash là dữ liệu, có thể dùng `URLEncoder` cho toàn bộ URI không?

**Đáp án:** Không. Phải dùng bộ xây dựng/encode **theo từng path segment** với hợp đồng đúng và xem cách server xử lý escape slash.

**15.** Dùng HTTPS cộng `URLEncoder` có đủ để ngăn XSS hoặc SQL injection không?

**Đáp án:** Không. HTTPS bảo vệ truyền tải theo cấu hình, form encoding phục vụ cấu trúc trường; HTML escaping, JSON serialization và SQL prepared statements vẫn cần được dùng đúng vị trí.

## 19. Tài liệu chính thức để tham khảo

- [Oracle JDK 10 — `URLEncoder`](https://docs.oracle.com/javase/10/docs/api/java/net/URLEncoder.html): định nghĩa **HTML form encoding**, quy tắc space thành `+`, ký tự không an toàn thành `%HH` và overload `encode(String, Charset)` ghi `Since: 10`.
- [Oracle JDK 10 — `URLDecoder`](https://docs.oracle.com/javase/10/docs/api/java/net/URLDecoder.html): giải mã `application/x-www-form-urlencoded`, xử lý `+` và `%HH`, overload `decode(String, Charset)` ghi `Since: 10`.
- [Oracle Java SE 21 — `URLEncoder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLEncoder.html): hợp đồng còn áp dụng trên Java hiện đại.
- [Oracle Java SE 21 — `URLDecoder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLDecoder.html): hợp đồng hiện đại của form decoder, xử lý escape lỗi và charset.
- [Oracle Java SE 21 — `URI`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html): scheme, authority, path, query, fragment; khác biệt giữa các accessor raw/decoded và cơ chế quote thành phần.
- [Oracle Java SE 21 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset tiêu chuẩn, đặc biệt `UTF_8`.
- [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986): URI components, reserved/unreserved characters và percent-encoding.
- [WHATWG URL Standard — application/x-www-form-urlencoded](https://url.spec.whatwg.org/#application/x-www-form-urlencoded): quy tắc form-style percent-encode và diễn giải query/form trong ngữ cảnh web.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): bối cảnh default charset từ JDK 18; không thay thế việc chọn charset đúng hợp đồng.
- [Oracle Java SE 21 — `HttpRequest`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.html): ví dụ mở rộng Java 11+ về tạo HTTP request có form body.

**Ghi nhớ:** `URLEncoder`/`URLDecoder` trong Java 10 xử lý **tên và giá trị theo `application/x-www-form-urlencoded`**, không phải mã hóa hay giải mã **toàn bộ URI**. Với query form-style, hãy **encode từng field, ghép delimiter, parse raw query trước, decode từng field sau**. Dùng `URI` hoặc URI builder đúng hợp đồng cho scheme/host/path/fragment, cảnh giác với dấu `+`, `%2F`, `%26` và double-encoding `%25`.