# Mã hóa từng khóa và giá trị trước khi ghép truy vấn

## 1. Tại sao phải mã hóa từng thành phần?

Khi tạo chuỗi truy vấn (*query string*) hoặc phần thân biểu mẫu theo định dạng `application/x-www-form-urlencoded`, dữ liệu thường được biểu diễn thành các cặp:

~~~text
key1=value1&key2=value2&key3=value3
~~~

Trong định dạng này, ký tự `&` được dùng để ngăn cách các cặp; `=` ngăn cách khóa với giá trị. Nếu dữ liệu thực sự chứa `&`, `=`, khoảng trắng, dấu cộng `+`, dấu phần trăm `%` hoặc chữ Unicode, **không được ghép dữ liệu thô trực tiếp** vào cấu trúc trên.

Ví dụ, người dùng nhập:

~~~text
Khóa:  q
Giá trị: Hà Nội & Java+?
~~~

**Cách sai:**

~~~java
// Ví dụ sai về mặt dữ liệu, không dùng trong ứng dụng thực:
String query = "q=" + "Hà Nội & Java+?";
~~~

Kết quả chứa một `&` chưa được mã hóa. Một bộ xử lý tham số dạng form có thể hiểu nhầm `& Java+?` là phần tiếp theo của truy vấn thay vì thuộc **giá trị** của khóa `q`. Dấu cộng cũng dễ bị diễn giải thành dấu cách.

**Cách đúng:** mã hóa **mỗi khóa và mỗi giá trị**, sau đó mới ghép các dấu phân cách có nghĩa cấu trúc.

~~~java
// Java 10+; mã minh họa trong một phương thức.
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String key = "q";
String value = "Hà Nội & Java+?";

String query = URLEncoder.encode(key, StandardCharsets.UTF_8)
        + "="
        + URLEncoder.encode(value, StandardCharsets.UTF_8);

System.out.println(query);
// q=H%C3%A0+N%E1%BB%99i+%26+Java%2B%3F
~~~

Hai dòng `import` trong khối trên là **minh họa các import cần dùng**; khi viết file Java thực tế, đặt import ở đầu file, không đặt bên trong phương thức. Mục 9 có chương trình hoàn chỉnh chạy được.

**Công thức cần nhớ:**

~~~text
encode(key1) + "=" + encode(value1)
       + "&" +
encode(key2) + "=" + encode(value2)
       + "&" + ...
~~~

Không dùng `encode(key1 + "=" + value1 + "&" + ...)`: khi mã hóa cả chuỗi đã ghép, các dấu `=` và `&` dùng làm **cấu trúc** cũng bị mã hóa, khiến bộ phân tích phía nhận không còn tách đúng các cặp.

## 2. API chuẩn từ Java 10: URLEncoder.encode(String, Charset)

`java.net.URLEncoder` là lớp tiện ích để **mã hóa dữ liệu biểu mẫu HTML** theo định dạng `application/x-www-form-urlencoded`, không phải bộ mã hóa chung cho mọi phần của URL.

Java 10 bổ sung overload:

~~~java
// Chữ ký API, không phải phương thức cần tự khai báo:
public static String encode(String s, Charset charset)
~~~

Ví dụ Java 17+:

~~~java
String encoded = URLEncoder.encode(
        "a&b=c + 100%",
        StandardCharsets.UTF_8
);

System.out.println(encoded); // a%26b%3Dc+%2B+100%25
~~~

Theo quy tắc form encoding:

| Dữ liệu thô | Dữ liệu đã mã hóa bằng `URLEncoder` / UTF-8 | Giải thích |
| --- | --- | --- |
| `a b` | `a+b` | Dấu cách thành `+` |
| `a+b` | `a%2Bb` | Dấu cộng thật phải được mã hóa thành `%2B` |
| `a&b` | `a%26b` | `&` là dữ liệu, không phải dấu phân cách cặp |
| `a=b` | `a%3Db` | `=` là dữ liệu, không phải dấu phân cách khóa–giá trị |
| `100%` | `100%25` | `%` được mã hóa, tránh nhầm với chuỗi `%HH` |
| `a/b` | `a%2Fb` | Dấu `/` được mã hóa theo quy tắc form |
| `a?b#c` | `a%3Fb%23c` | `?` và `#` trở thành dữ liệu |
| `Hà Nội` | `H%C3%A0+N%E1%BB%99i` | Chữ Unicode qua byte UTF-8 rồi percent-encoding |

Trong form encoding, chữ/số ASCII và các ký tự `. - * _` được giữ nguyên. Phần lớn các ký tự khác được chuyển qua byte của charset, sau đó biểu diễn bằng `%` và hai chữ số hex trên mỗi byte. Vì thế, chữ Unicode nhiều byte thường tạo nhiều cụm `%HH`.

### Tại sao dùng StandardCharsets.UTF_8?

~~~java
URLEncoder.encode(value, StandardCharsets.UTF_8);
~~~

- `StandardCharsets.UTF_8` là hằng số chuẩn, sẵn có trên các JDK hiện đại.
- UTF-8 phù hợp với văn bản Unicode, tiếng Việt và thông lệ xử lý biểu mẫu trên web.
- Việc chỉ định charset giúp kết quả xác định trên cả Java 10, Java 17 và các JDK mới hơn.
- Overload nhận `Charset` **không cần** xử lý `UnsupportedEncodingException` như overload nhận tên charset dưới dạng `String`.
- `URLEncoder.encode(String, Charset)` ném `NullPointerException` nếu chuỗi cần mã hóa hoặc đối tượng Charset là `null`; cần có chính sách dữ liệu trước khi gọi.

Overload cũ `URLEncoder.encode(String)` **không nên dùng**: nó đã được đánh dấu deprecated vì phụ thuộc default charset. Overload nhận `String encodingName` vẫn tồn tại, nhưng có thể yêu cầu xử lý `UnsupportedEncodingException` và dễ sai tên charset hơn. Dùng `StandardCharsets.UTF_8` khi giao thức quy định UTF-8.

## 3. Thứ tự thao tác đúng: mã hóa dữ liệu trước, ghép dấu phân cách sau

Với một danh sách cặp khóa–giá trị `(kᵢ, vᵢ)`, quy trình chuẩn gồm ba bước:

1. Nhận khóa và giá trị **ở dạng dữ liệu gốc**, chưa được mã hóa.
2. Gọi `URLEncoder.encode(kᵢ, UTF_8)` và `URLEncoder.encode(vᵢ, UTF_8)` **riêng biệt**.
3. Ghép một cặp bằng ký tự `=` chưa mã hóa, sau đó ghép các cặp bằng `&` chưa mã hóa.

Ví dụ:

~~~java
// Trong phương thức, có import URLEncoder, StandardCharsets.
String name = URLEncoder.encode("full name", StandardCharsets.UTF_8);
String value = URLEncoder.encode("An & Bình", StandardCharsets.UTF_8);
String tag = URLEncoder.encode("tag", StandardCharsets.UTF_8);
String tagValue = URLEncoder.encode("a+b", StandardCharsets.UTF_8);

String query = name + "=" + value + "&" + tag + "=" + tagValue;
System.out.println(query);
// full+name=An+%26+B%C3%ACnh&tag=a%2Bb
~~~

Các phần `full+name`, `An+%26+B%C3%ACnh`, `tag` và `a%2Bb` đều đã được mã hóa riêng. Ký tự `&` nằm giữa **hai cặp** là dấu phân cách có chủ đích; ký tự `&` bên trong giá trị `An & Bình` được giữ dưới dạng `%26`.

### Vì sao phải mã hóa cả khóa?

Khóa thường có dạng đơn giản như `q` hoặc `page`, nhưng không có bảo đảm rằng mọi hệ thống chỉ dùng ký tự chữ/số:

~~~java
String key = "filter[a&b]";
String value = "x=y";

String pair = URLEncoder.encode(key, StandardCharsets.UTF_8)
        + "="
        + URLEncoder.encode(value, StandardCharsets.UTF_8);

System.out.println(pair);
// filter%5Ba%26b%5D=x%3Dy
~~~

Nếu mã hóa **chỉ giá trị**, khóa có chứa `&` hoặc `=` vẫn có thể phá cấu trúc. Một số framework hỗ trợ khóa kiểu `filter[name]` hoặc mảng bằng các dấu ngoặc vuông; mã hóa khóa vẫn đúng với form encoding. Phía server cần giải mã trước khi áp dụng quy tắc đặt tên khóa của ứng dụng.

### Không mã hóa hai lần

~~~java
// Đã mã hóa:
String once = URLEncoder.encode("a&b", StandardCharsets.UTF_8);
System.out.println(once); // a%26b

// Mã hóa LẦN NỮA làm dấu % trở thành %25:
String twice = URLEncoder.encode(once, StandardCharsets.UTF_8);
System.out.println(twice); // a%2526b
~~~

Nếu phía nhận chỉ giải mã một lần, `a%2526b` trở thành `a%26b` thay vì `a&b`. Đừng đưa giá trị đã mã hóa trở lại vào hàm encoding. Duy trì ranh giới rõ: **dữ liệu thô → encode đúng một lần → ghép form**.

## 4. Đừng nhầm form encoding với việc mã hóa toàn bộ URL

`URLEncoder` thường được gọi là “URL encoder”, nhưng Javadoc nêu chính xác công dụng là **HTML form encoding**. Nó dùng quy tắc `space → +`, khác với nhiều cách percent-encode thành phần URI theo RFC 3986.

**Không dùng:**

~~~java
String baseUrl = "https://example.com/search";
String entireUrl = baseUrl + "?q=Java & Kotlin";

// Sai: biến cả scheme, dấu :, /, ?, &, = thành dữ liệu form.
String wrong = URLEncoder.encode(
        entireUrl, StandardCharsets.UTF_8);
~~~

Kết quả `wrong` sẽ không còn là URL với cấu trúc `https://.../search?q=...` ban đầu.

**Cách đúng:** giữ nguyên phần URL đáng tin đã xác định, chỉ form-encode các key/value:

~~~java
String baseUrl = "https://example.com/search"; // Chưa có query/fragment.
String query = URLEncoder.encode("q", StandardCharsets.UTF_8)
        + "="
        + URLEncoder.encode("Java & Kotlin", StandardCharsets.UTF_8);

java.net.URI uri = java.net.URI.create(baseUrl + "?" + query);
System.out.println(uri.getRawQuery().equals(query)); // true
~~~

Ở đây `baseUrl` được đặt trước và **không chứa query hoặc fragment**. `URI.create(...)` nhận một URI string đã hoàn chỉnh, trong đó phần query đã được percent-encode hợp lệ. `getRawQuery()` cho phần query ở dạng đã mã hóa mà không giải mã các `%HH`.

### Nếu URL gốc đã có query hoặc fragment

Không nối `"?" + query` một cách mù quáng:

- URL đã có `?a=1` thì cần quy tắc ghép bằng `&` cho thêm tham số.
- URL có fragment `#section` thì query phải nằm **trước dấu #**, không phải sau nó.
- Tham số trong query cũ có thể đã được mã hóa; mã hóa lại toàn bộ `getRawQuery()` sẽ làm các ký hiệu `%` thành `%25`.
- Một số phương thức tạo `URI` nhận **thành phần chưa mã hóa** và có thể tự escape `%`; không truyền bừa phần query **đã mã hóa** vào API rồi để nó encode thêm lần nữa.

Trong ứng dụng thật, ưu tiên một URI/query builder hiểu đúng **raw versus decoded components** và form encoding mà framework sử dụng. Nếu tự xây, phải phân biệt các phần scheme/authority/path/query/fragment, chọn quy tắc cho query đã tồn tại và viết test cho trường hợp chứa dấu `?`, `&`, `%` và `#`.

### Không dùng URLEncoder cho đường dẫn URL

~~~text
https://example.com/products/a/b?filter=x
                    ^^^^^ path     ^ query
~~~

Dấu `/` trong đường dẫn thường có vai trò phân cách các segment. `URLEncoder.encode("a/b", UTF_8)` cho `a%2Fb`, nhưng quy tắc form `space → +` **không phải** quy tắc chung cho path segment. Các phương thức path/URI builder có hợp đồng percent-encoding riêng; chọn API đúng với **thành phần URI** đang xây.

Đặc biệt, khi dữ liệu từ người dùng là path segment, không ghép thẳng ký tự `/`, `?`, `#` hoặc chuỗi `..` vào đường dẫn nếu chưa có quy tắc parse/validate phù hợp.

## 5. Tạo nhiều cặp: dùng cấu trúc lưu được khóa lặp

Trong các biểu mẫu, cùng một khóa có thể xuất hiện nhiều lần:

~~~text
tag=java&tag=unicode&tag=form
~~~

Ví dụ bộ lọc cho nhiều tag hoặc form có nhiều giá trị cùng tên trường. Một `Map<String,String>` thông thường **không lưu nhiều entry có cùng key**. Nếu gọi `put("tag", ...)` nhiều lần, các giá trị cũ có thể bị ghi đè.

Muốn bảo toàn **thứ tự và số lần xuất hiện**, nên dùng một danh sách cặp:

~~~java
// Java 17+: record đơn giản cho dữ liệu chưa encode.
record Pair(String key, String value) {}

var pairs = List.of(
        new Pair("tag", "Java 10"),
        new Pair("tag", "UTF-8"),
        new Pair("sort", "newest")
);
~~~

`record Pair` là khai báo kiểu minh họa. Nó có thể là nested record trong class chứa hàm xử lý, như chương trình runnable ở mục 9.

### Dùng StringJoiner để ghép

~~~java
// Bên trong phương thức có List<Pair> pairs từ ví dụ trên.
var joiner = new java.util.StringJoiner("&");

for (Pair pair : pairs) {
    String k = URLEncoder.encode(
            pair.key(), StandardCharsets.UTF_8);
    String v = URLEncoder.encode(
            pair.value(), StandardCharsets.UTF_8);
    joiner.add(k + "=" + v);
}

System.out.println(joiner.toString());
// tag=Java+10&tag=UTF-8&sort=newest
~~~

`StringJoiner("&")` chỉ thêm `&` **giữa** các cặp, không tự thêm `&` ở đầu/cuối. Dữ liệu giá trị không được chèn trực tiếp. Việc dùng `List<Pair>` giúp caller kiểm soát thứ tự cặp và giữ tên lặp; server/framework nào nhận tên lặp theo kiểu danh sách hay chọn một giá trị phải được kiểm tra ở phía nhận.

**Không có quy tắc Java rằng giá trị đầu/giá trị cuối của khóa lặp sẽ được server giữ:** đó là chính sách của bộ giải mã request hoặc framework.

### Giá trị rỗng và không có giá trị

~~~java
String emptyValue = URLEncoder.encode("", StandardCharsets.UTF_8);
System.out.println("empty=" + emptyValue); // empty=
~~~

`"empty="` thể hiện một cặp có khóa `empty` và **giá trị là chuỗi rỗng**. Nó có thể khác với việc không gửi tham số `empty`, và tùy parser có thể khác với một phần tử `"empty"` không có ký tự `=`.

Do đó, nếu API cần phân biệt các trạng thái:

- **Không có tham số:** không thêm cặp.
- **Giá trị chuỗi rỗng:** thêm `encode(key) + "="`.
- **Giá trị null:** cần chính sách rõ; `URLEncoder.encode(null, UTF_8)` ném `NullPointerException`. Không tùy tiện chuyển null thành `""` nếu nghiệp vụ coi đó là trạng thái khác.

## 6. Giải mã ở phía nhận: tách cặp trước, URLDecoder sau

`java.net.URLDecoder.decode(String, Charset)` (cũng được bổ sung từ **Java 10**) thực hiện phép đảo ngược của `URLEncoder` đối với dữ liệu `application/x-www-form-urlencoded`:

- `+` trong dữ liệu đã mã hóa → dấu cách.
- `%HH` → byte rồi giải mã theo Charset.
- `%2B` → dấu cộng thật.
- `%26` → `&` bên trong key/value, không phải ký tự tách cặp.

~~~java
// Trong phương thức với import java.net.URLDecoder.
String encodedValue = "H%C3%A0+N%E1%BB%99i+%26+Java%2B%3F";

String decoded = URLDecoder.decode(
        encodedValue, StandardCharsets.UTF_8);

System.out.println(decoded); // Hà Nội & Java+?
~~~

### Thứ tự giải mã quan trọng

**Sai:** giải mã toàn bộ raw query, rồi mới tách theo `&`:

~~~java
// Phản mẫu:
String query = "q=a%26b&tag=x+y";
String prematurelyDecoded = URLDecoder.decode(
        query, StandardCharsets.UTF_8);
// prematurelyDecoded = "q=a&b&tag=x y"
// Nếu split("&") ở đây, giá trị "a&b" sẽ bị tách sai.
~~~

**Đúng:** tách raw query theo `&`, tìm **dấu `=` đầu tiên** trong mỗi cặp, sau đó decode riêng key và value:

~~~java
// Trong phương thức, minh họa một cặp:
String rawPair = "q=a%26b";
int equals = rawPair.indexOf('=');

String key = URLDecoder.decode(
        rawPair.substring(0, equals), StandardCharsets.UTF_8);
String value = URLDecoder.decode(
        rawPair.substring(equals + 1), StandardCharsets.UTF_8);

System.out.println(key);   // q
System.out.println(value); // a&b
~~~

`indexOf('=')` tách ở dấu bằng cấu trúc **đầu tiên**. Những dấu `=` thuộc dữ liệu được mã hóa thành `%3D` nên không xung đột. Nếu parser chấp nhận raw dấu `=` trong value, cũng cần quyết định chính sách phù hợp; ví dụ code ở mục 9 yêu cầu mỗi cặp có ký tự `=`.

### Decode đúng một lần

~~~java
String encoded = "q=100%25";

String value = URLDecoder.decode(
        encoded.substring(encoded.indexOf('=') + 1),
        StandardCharsets.UTF_8);

System.out.println(value); // 100%
~~~

Đừng tự động gọi `URLDecoder.decode` lần thứ hai trên `"100%"`: dấu `%` ở đây là **dữ liệu thật**, không còn là escape hợp lệ để decode tiếp. Double decoding có thể làm thay đổi ý nghĩa ký tự điều khiển và làm sai validation.

### Dữ liệu escape sai phải được xử lý

~~~java
try {
    URLDecoder.decode("x%ZZ", StandardCharsets.UTF_8);
} catch (IllegalArgumentException expected) {
    System.out.println("invalid escape");
}
// invalid escape
~~~

Một chuỗi `%` không đi cùng hai chữ số hex hợp lệ có thể làm `URLDecoder` ném `IllegalArgumentException`. Khi nhận dữ liệu từ HTTP request, hãy xử lý lỗi parse rõ ràng thay vì bỏ qua rồi cho rằng tham số vắng mặt.

## 7. Form body POST và query string GET: cùng cấu trúc, khác nơi truyền

**Query string GET:**

~~~text
GET /search?q=Java+10&tag=UTF-8 HTTP/1.1
~~~

Phần sau `?` trong URI mang các cặp truy vấn. Nếu server dùng quy ước biểu mẫu, nó giải mã `+` thành dấu cách và `%HH` thành byte tương ứng. Không tự động áp quy tắc form decoding lên **mọi URI query của mọi giao thức**: RFC 3986 không định nghĩa `+` có nghĩa là khoảng trắng chung cho mọi truy vấn.

**Form body POST:**

~~~http
POST /submit HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

name=An+%26+B%C3%ACnh&tag=Java+10
~~~

Header `Content-Type` cho biết body có định dạng `application/x-www-form-urlencoded`. Phần body dùng cách ghép cặp tương tự như query form, nhưng **không** có dấu `?` hoặc fragment `#...`; nó là nội dung request body. Các thư viện HTTP/framework có thể tự mã hóa form khi bạn đưa dữ liệu cấu trúc vào API; không encode thủ công thêm một lần nếu thư viện đã làm việc đó.

### Java 17 HttpClient: gửi đúng form body khi cần

~~~java
// Đoạn minh họa, KHÔNG thực hiện network request ở đây.
String formBody = "name=An+%26+B%C3%ACnh&tag=Java+10";

var request = java.net.http.HttpRequest.newBuilder(
        java.net.URI.create("https://example.com/submit"))
        .header("Content-Type",
                "application/x-www-form-urlencoded; charset=UTF-8")
        .POST(java.net.http.HttpRequest.BodyPublishers.ofString(
                formBody, StandardCharsets.UTF_8))
        .build();
~~~

`BodyPublishers.ofString(..., UTF_8)` chuyển **chuỗi đã form-encode** thành byte UTF-8 để gửi. Nó không tự biến dữ liệu thô thành các cặp `key=value`. Vì vậy, chỉ mã hóa đúng một lần ở bước dựng form body. Ví dụ này **chỉ dựng HttpRequest**, không gọi `HttpClient.send`.

### URL query không thích hợp cho dữ liệu nhạy cảm

Dữ liệu trong URL có thể xuất hiện trong lịch sử duyệt web, log máy chủ, hệ thống phân tích, thông tin diagnostic và các ngữ cảnh chia sẻ URL. Đừng đưa mật khẩu, token bí mật hoặc dữ liệu cá nhân nhạy cảm vào query string chỉ vì chúng đã được percent-encode. **Encoding không phải mã hóa bảo mật (encryption)** và không thay thế HTTPS, xác thực, phân quyền hoặc chính sách lưu log.

## 8. Những lỗi thường gặp với dấu cộng, phần trăm và ký tự Unicode

### Dấu cách khác dấu cộng thật

~~~java
String space = URLEncoder.encode("a b", StandardCharsets.UTF_8);
String plus = URLEncoder.encode("a+b", StandardCharsets.UTF_8);

System.out.println(space); // a+b
System.out.println(plus);  // a%2Bb
~~~

Nếu xây chuỗi form bằng cách nối trực tiếp `"a+b"` như giá trị, parser chuẩn sẽ giải mã dấu `+` thành **dấu cách**, dẫn tới `"a b"`. Muốn lưu dấu cộng thật phải gửi `%2B`.

### Dấu phần trăm phải được encode

~~~java
System.out.println(
        URLEncoder.encode("100%", StandardCharsets.UTF_8)
); // 100%25
~~~

Khi `%25` được giải mã **một lần**, nó thành `%`. Không tự giải mã hai lần hoặc xem chuỗi `100%` là một giá trị còn encoded.

### Unicode mã hóa theo byte UTF-8

~~~java
System.out.println(
        URLEncoder.encode("Hà Nội", StandardCharsets.UTF_8)
); // H%C3%A0+N%E1%BB%99i
~~~

Ký tự `à` có hai byte UTF-8 (`C3 A0`), và `ộ` có ba byte (`E1 BB 99`); vì vậy chúng được thể hiện bằng nhiều cụm `%HH`. Dấu cách nằm giữa hai từ được form-encode thành `+`.

Nếu đầu nhận dùng charset khác, có thể mất khả năng khôi phục dữ liệu. Chọn cùng charset hai đầu là điều kiện của round-trip. Với đầu vào chứa Unicode không hợp lệ (như surrogate bị lỗi), cần quy tắc validation/encoding riêng; không mặc nhiên khẳng định mọi chuỗi UTF-16 hỏng đều round-trip hoàn hảo.

### Ký tự có ý nghĩa trong URL phải là dữ liệu sau khi encode

~~~java
var special = "x=y&z+%#?";
var encoded = URLEncoder.encode(
        special, StandardCharsets.UTF_8);

System.out.println(encoded); // x%3Dy%26z%2B%25%23%3F
~~~

Mỗi `=`, `&`, `+`, `%`, `#`, `?` ở đây đều thuộc giá trị thật, nên đã được mã hóa. Sau khi ghép vào query, chỉ dấu `=` và `&` **do builder thêm** mới có vai trò phân cách.

## 9. Chương trình Java 17+ hoàn chỉnh: mã hóa, ghép và giải mã

Chương trình này tự tạo nhiều cặp khóa–giá trị, bao gồm:
- Khóa lặp `tag`.
- Khóa chứa dấu `%`.
- Giá trị chứa `&`, `=`, khoảng trắng, dấu cộng, dấu `/` và tiếng Việt.
- Giá trị chuỗi rỗng.
- Kiểm tra raw query của `URI`.
- Giải mã đúng từng cặp theo thứ tự.
- Thử bộ giải mã với dấu cộng và escape không hợp lệ.

Lưu tệp **`FormQueryPairsDemo.java`** dưới dạng UTF-8:

~~~java
import java.net.URI;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.StringJoiner;

public class FormQueryPairsDemo {

    record Param(String key, String value) {}

    static String encodePairs(List<Param> params) {
        Objects.requireNonNull(params, "params");
        var joiner = new StringJoiner("&");

        for (Param param : params) {
            Objects.requireNonNull(param, "param");
            String key = URLEncoder.encode(
                    Objects.requireNonNull(param.key(), "key"),
                    StandardCharsets.UTF_8);
            String value = URLEncoder.encode(
                    Objects.requireNonNull(param.value(), "value"),
                    StandardCharsets.UTF_8);

            joiner.add(key + "=" + value);
        }

        return joiner.toString();
    }

    static List<Param> decodePairs(String rawQuery) {
        Objects.requireNonNull(rawQuery, "rawQuery");
        if (rawQuery.isEmpty()) {
            return List.of();
        }

        var result = new ArrayList<Param>();

        for (String part : rawQuery.split("&", -1)) {
            int pos = part.indexOf('=');
            if (pos < 0) {
                throw new IllegalArgumentException(
                        "Missing '=' in query pair");
            }

            String key = URLDecoder.decode(
                    part.substring(0, pos),
                    StandardCharsets.UTF_8);
            String value = URLDecoder.decode(
                    part.substring(pos + 1),
                    StandardCharsets.UTF_8);
            result.add(new Param(key, value));
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        var params = List.of(
                new Param("q", "Hà Nội & Java+?"),
                new Param("tag", "a&b=c"),
                new Param("tag", "x y"),
                new Param("empty", ""),
                new Param("100%", "5/10")
        );

        String query = encodePairs(params);
        System.out.println("query=" + query);

        List<Param> restored = decodePairs(query);
        System.out.println("roundTrip=" + params.equals(restored));
        System.out.println("pairCount=" + restored.size());
        System.out.println("firstTag=" + restored.get(1).value());
        System.out.println("secondTag=" + restored.get(2).value());
        System.out.println("emptyValue="
                + restored.get(3).value().isEmpty());

        URI target = URI.create(
                "https://example.com/search?" + query);
        System.out.println("rawQueryMatch="
                + query.equals(target.getRawQuery()));

        System.out.println("space="
                + URLEncoder.encode("a b", StandardCharsets.UTF_8));
        System.out.println("literalPlus="
                + URLEncoder.encode("a+b", StandardCharsets.UTF_8));
        System.out.println("literalPercent="
                + URLEncoder.encode("100%", StandardCharsets.UTF_8));
        System.out.println("unicode="
                + URLEncoder.encode("Hà Nội", StandardCharsets.UTF_8));

        System.out.println("decodeSpace="
                + URLDecoder.decode("a+b", StandardCharsets.UTF_8));
        System.out.println("decodePlus="
                + URLDecoder.decode("a%2Bb", StandardCharsets.UTF_8));

        try {
            URLDecoder.decode("bad%ZZ", StandardCharsets.UTF_8);
        } catch (IllegalArgumentException expected) {
            System.out.println("malformedRejected=true");
        }

        try {
            encodePairs(List.of(new Param("x", null)));
        } catch (NullPointerException expected) {
            System.out.println("nullRejected=true");
        }

        System.out.println("noPairs=" + encodePairs(List.of()).isEmpty());
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 --release 17 FormQueryPairsDemo.java
java FormQueryPairsDemo
~~~

**Stdout chính xác:**

~~~text
query=q=H%C3%A0+N%E1%BB%99i+%26+Java%2B%3F&tag=a%26b%3Dc&tag=x+y&empty=&100%25=5%2F10
roundTrip=true
pairCount=5
firstTag=a&b=c
secondTag=x y
emptyValue=true
rawQueryMatch=true
space=a+b
literalPlus=a%2Bb
literalPercent=100%25
unicode=H%C3%A0+N%E1%BB%99i
decodeSpace=a b
decodePlus=a+b
malformedRejected=true
nullRejected=true
noPairs=true
~~~

### Phân tích kết quả

1. Phần `query=...` có dấu `&` chỉ để **ngăn năm cặp**, và mỗi cặp chỉ có một dấu `=` phân cách. Dấu `&`, `=` và `+` thuộc giá trị đầu vào đã được percent-encode riêng.
2. Chữ tiếng Việt `"Hà Nội"` được mã hóa UTF-8. Dấu cách của form trở thành `+`, dấu cộng thật trong `"Java+?"` thành `%2B`, dấu hỏi thành `%3F`.
3. Hai cặp `tag` được giữ nguyên thứ tự bởi `List<Param>`. Bộ giải mã không ghi đè giá trị đầu tiên như một `Map<String,String>` đơn giản.
4. `empty=` giữ trạng thái giá trị chuỗi rỗng. `decodePairs` có quy tắc yêu cầu mỗi cặp có dấu bằng, vì vậy không tự đồng nhất `empty` không dấu bằng với `empty=`.
5. `roundTrip=true` kiểm rằng sau khi encode, ghép, tách và decode, danh sách record giống hệt dữ liệu gốc (theo `record.equals`).
6. `target.getRawQuery()` giữ phần raw query. Chương trình không dùng `getQuery()` để thử phân tích các cặp, tránh giải mã sớm các `%26` thành dấu `&` gây nhầm dấu phân cách.
7. `decodeSpace` chứng minh dấu cộng thô của form được hiểu là khoảng trắng; `decodePlus` chứng minh `%2B` cho dấu cộng thật.
8. Escape `%ZZ` không có hex hợp lệ nên `URLDecoder` báo `IllegalArgumentException`.
9. `URLEncoder.encode` từ chối một value null, được hàm `encodePairs` kiểm rõ qua `Objects.requireNonNull`. Không âm thầm chuyển null thành chuỗi `"null"` hoặc giá trị trống.
10. Với danh sách cặp rỗng, `StringJoiner` trả chuỗi rỗng. Khi tích hợp vào URI, chỉ thêm `?` khi thật sự có tham số và giao thức yêu cầu điều đó.

Chương trình chỉ tạo URI local trong bộ nhớ, không gửi HTTP request. Đầu ra ASCII ở những chỗ có percent-encoding là xác định bởi bộ mã hóa chuẩn; chương trình không dựa vào thời gian, mạng hoặc thứ tự của hash map.

## 10. Quy trình đọc và viết truy vấn trong ứng dụng thực tế

### 10.1. Phía tạo request

1. Lưu key/value dưới dạng dữ liệu thô có kiểu rõ ràng; không lưu một phần key đã mã hóa và phần value chưa mã hóa lẫn lộn.
2. Validate ý nghĩa dữ liệu: kiểu ID, dải giá trị, độ dài, số lượng tham số và chính sách null.
3. Dùng `URLEncoder.encode(key, StandardCharsets.UTF_8)` và `URLEncoder.encode(value, StandardCharsets.UTF_8)` cho từng cặp **theo quy ước form encoding**.
4. Nối `=` giữa key/value, `&` giữa các cặp, giữ nguyên thứ tự hoặc các khóa lặp khi nghiệp vụ cần.
5. Đặt chuỗi đã ghép vào vị trí phù hợp: query của URI hoặc body `application/x-www-form-urlencoded`.
6. Dùng cùng chuẩn charset/format với bên nhận. Tránh mã hóa lặp bằng framework hoặc URI builder.

### 10.2. Phía nhận request

1. Xác định đầu vào thật: raw query trong URI hay body form; đừng nối lẫn chúng nếu API không yêu cầu.
2. Với raw query theo quy ước form, tách các cặp theo `&` **trước khi** giải mã.
3. Với mỗi cặp, tách key/value ở dấu `=` đầu tiên, áp dụng chính sách cho cặp thiếu dấu bằng hoặc cặp rỗng.
4. Gọi `URLDecoder.decode(key, UTF_8)` và `URLDecoder.decode(value, UTF_8)` **riêng**.
5. Giữ các khóa lặp bằng danh sách hoặc multi-value map nếu cần, thay vì âm thầm chỉ giữ giá trị đầu/cuối.
6. Validate **giá trị sau giải mã**: encoding không làm input an toàn để sử dụng trong SQL, HTML, lệnh shell, đường dẫn file hay điều kiện truy cập.
7. Có giới hạn số cặp, tổng độ dài và kích thước giá trị để phòng việc parser phải xử lý dữ liệu quá lớn.

**Quan trọng về framework:** một HTTP framework thường đã phân tích query/body và trả về các giá trị **đã giải mã**. Không tự động gọi `URLDecoder` lần nữa trên giá trị được framework trả về; việc giải mã hai lần là nguyên nhân thường gặp của lỗi xử lý dấu `%` hoặc ký tự phân cách.

## 11. Lỗi phổ biến và cách sửa

| Cách làm sai | Tác hại | Cách đúng |
| --- | --- | --- |
| Ghép `"q=" + rawValue` | `&`, `=`, `+`, `#` từ value có thể bị hiểu sai | `URLEncoder.encode(rawValue, UTF_8)` rồi ghép |
| Mã hóa cả `"q=...&tag=..."` | Dấu phân cách cấu trúc thành `%3D`/`%26` | Mã hóa riêng key và value, để `&`/`=` giữa cặp |
| Chỉ encode value, không encode key | Key chứa ký tự đặc biệt vẫn có thể phá query | Encode từng key và từng value |
| Dùng `URLEncoder.encode(String)` không charset | Overload deprecated, kết quả phụ thuộc default charset | Dùng overload `(String, Charset)` với UTF-8 |
| Dùng `URLEncoder` cho cả URL/path | Scheme/path/query delimiter bị biến thành dữ liệu | Chỉ form-encode các thành phần key/value của form |
| Gửi dấu cộng thô trong giá trị | `+` bị URLDecoder hiểu thành khoảng trắng | Encode `+` thành `%2B` |
| Encode lần nữa một value đã encoded | `%26` thành `%2526`, decode một lần không khôi phục | Encode đúng một lần |
| Decode toàn raw query trước khi split | `%26` trở thành `&` rồi bị tách thành cặp sai | Split raw query trước, decode riêng từng thành phần |
| Decode hai lần sau khi đã parse | Thay đổi ý nghĩa `%` và delimiter, có thể phá validation | Chỉ decode theo đúng một lớp encoding |
| Dùng `Map<String,String>` cho tham số trùng | Mất các giá trị cũ theo cách put/parse | Dùng `List<Pair>` hoặc multi-value map |
| Dùng `null` rồi mặc định thành `""` | Trộn trạng thái null, empty và missing | Đặt chính sách explicit cho mỗi trường hợp |
| Ghép `?` vào URL đã có `?` hoặc `#` | URL sai ranh giới query/fragment | Dùng URI builder đúng hợp đồng hoặc xử lý thành phần |
| Tin rằng URL encoding chặn mọi injection | Encoding chỉ bảo vệ cú pháp của form | Validate, dùng prepared statements, escaping theo ngữ cảnh output |
| Đưa token bí mật vào query | URL dễ xuất hiện trong log/lịch sử | Chọn phương thức truyền phù hợp, không để secret trong URL |
| Không kiểm charset của bên nhận | Unicode bị giải mã sai | Thỏa thuận UTF-8/charset giữa hai đầu |

## 12. Checklist và bài tập tự kiểm tra

### Checklist code review

- [ ] Mỗi key và value đều được encode riêng trước khi ghép `=` / `&`?
- [ ] Charset được chỉ định tường minh bằng `StandardCharsets.UTF_8` hoặc theo hợp đồng?
- [ ] Biến đầu vào là raw text, chưa encode lần nào?
- [ ] Có xử lý đúng dấu cách, `+`, `&`, `=`, `%` và Unicode?
- [ ] Khóa lặp có được giữ khi cần? Giá trị rỗng có được phân biệt với missing/null?
- [ ] URL base có query/fragment sẵn không? Có nguy cơ double encoding do URI builder không?
- [ ] Phía nhận có tách raw query trước khi decode, và decode đúng một lần?
- [ ] HTTP client/framework có tự form-encode hoặc decode rồi không?
- [ ] Có validation, giới hạn kích thước và xử lý escape malformed?
- [ ] Có dữ liệu nhạy cảm vô tình được đưa vào query hoặc log không?
- [ ] Có test round-trip bằng văn bản tiếng Việt, ký tự phân cách và khóa lặp không?

### Câu 1

`URLEncoder.encode("a b", StandardCharsets.UTF_8)` trả gì?

**Đáp án:** `a+b`. Đây là quy tắc **form encoding**: dấu cách thành dấu cộng.

### Câu 2

Muốn lưu dấu cộng thật trong giá trị `"a+b"`, chuỗi đã mã hóa cần có gì?

**Đáp án:** `a%2Bb`. Nếu ghi thô `a+b` thì `URLDecoder` sẽ giải mã thành `a b`.

### Câu 3

Có nên gọi `URLEncoder.encode("a=1&b=2", UTF_8)` để tạo query cho hai tham số không?

**Đáp án:** Không. Nó mã hóa cả `=` và `&` thành dữ liệu, làm mất cấu trúc hai cặp. Phải encode từng `a`, `1`, `b`, `2` rồi thêm dấu phân cách rõ.

### Câu 4

Khóa `"x&y"` và giá trị `"a=b"` được ghép thế nào?

**Đáp án:** `x%26y=a%3Db`. Dấu `&` bên trong khóa và `=` bên trong giá trị đều thuộc dữ liệu thật.

### Câu 5

Tại sao không giải mã cả raw query trước khi `split("&")`?

**Đáp án:** Vì `%26` bên trong giá trị sẽ trở thành `&`, có thể bị hiểu sai là dấu phân cách giữa cặp.

### Câu 6

`URLEncoder.encode("100%", UTF_8)` trả gì và nên decode mấy lần?

**Đáp án:** `100%25`; decode **đúng một lần** cho giá trị `100%`.

### Câu 7

Vì sao `Map<String,String>` không phù hợp với `tag=java&tag=form` nếu cần giữ cả hai?

**Đáp án:** Map chỉ chứa một value trên mỗi key; thao tác ghi key lặp có thể làm mất một giá trị. Dùng danh sách cặp hoặc multi-value map.

### Câu 8

Có thể dùng `URLEncoder` để mã hóa nguyên `https://example.com/a/b?q=x` không?

**Đáp án:** Không. Nó là form encoder, không phải phép encode toàn URL. Các dấu `:`, `/`, `?`, `=` của cấu trúc URL sẽ bị mã hóa không đúng mục đích.

### Câu 9

Có nên gửi secret/token trong query sau khi percent-encode không?

**Đáp án:** Không chỉ vì đã encode. Percent-encoding có thể đảo ngược, **không** bảo vệ bí mật; cân nhắc cơ chế truyền và lưu log phù hợp.

### Câu 10

Khi nào dùng `URLDecoder.decode(String, Charset)` thay vì parser của HTTP framework?

**Đáp án:** Khi đang xử lý **dữ liệu raw** theo định dạng `application/x-www-form-urlencoded` và tự chịu trách nhiệm parsing. Nếu framework đã decode, không decode lần nữa.

## 13. Tham khảo chính thức còn áp dụng

- [Oracle Java SE 17 — `URLEncoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html): hợp đồng `application/x-www-form-urlencoded`, dấu cách thành `+`, escape `%HH`, overload `encode(String, Charset)` từ Java 10 và null handling.
- [Oracle Java SE 26 — `URLEncoder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URLEncoder.html): xác nhận API vẫn được hỗ trợ, khuyến nghị chỉ định UTF-8 và phân biệt overload deprecated không charset.
- [Oracle Java SE 17 — `URLDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLDecoder.html): giải mã dấu cộng, các cụm `%HH`, xử lý escape không hợp lệ; overload `decode(String, Charset)` có từ Java 10.
- [Oracle Java SE 17 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): hằng số UTF-8 luôn có sẵn.
- [Oracle Java SE 17 — `URI`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html): phân biệt scheme, path, query, fragment và raw query.
- [Oracle Java SE 17 — `HttpRequest.BodyPublishers`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): `ofString(String, Charset)` dùng để chuyển chuỗi body sang byte khi gửi HTTP.
- [RFC 3986 — URI Generic Syntax, mục 2 và 3](https://www.rfc-editor.org/rfc/rfc3986): quy tắc percent-encoding, reserved characters và tách query khỏi những thành phần URI khác.
- [WHATWG HTML Standard — Form submission](https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#url-encoded-form-data): định dạng `application/x-www-form-urlencoded` trong ngữ cảnh biểu mẫu web.

**Ghi nhớ:** **Mã hóa từng khóa và từng giá trị bằng `URLEncoder.encode(..., StandardCharsets.UTF_8)` trước; chỉ sau đó mới ghép `key=value` với `&` giữa các cặp.** Khi đọc raw query dạng form, làm ngược lại: **tách cặp trước, giải mã từng thành phần sau**, và chỉ giải mã đúng một lần. Cách này bảo vệ ranh giới dữ liệu có chứa `&`, `=`, `+`, `%` và Unicode, nhưng không thay thế validation hay các cơ chế bảo mật khác.